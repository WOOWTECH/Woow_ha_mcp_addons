"""The add-on's one reply worker: a switched-on product's replies are processed off the event loop, one at a time,
the profiles taking turns (multi-profile plan 5.5; contract 6; §8.8 #17; invariant I8; HM-30; C2-MF-4, C1-M5; FM-129).

Why: every profile of an add-on shares one asyncio event loop, and the gateway parses, masks and re-serializes every
reply a child sends (strict_json, redact.redact_secrets, policy.filter_list, json.dumps). On the loop, one 8 MiB reply
stops every profile's requests and health checks for its whole processing (0.28 to 0.47 s on an EPYC 7713: C2's
loop_block_bench; several times that on a J1900), so one token holder's large replies made another profile's health
check time out and its tool calls be refused (C2's cross_profile_probe_sim).

What: one dedicated thread for the whole add-on, started and stopped by run_product (features.enabled products only;
a product that is not switched on never starts it, and its replies are processed on the loop as before). The gateway
reads on the loop what a reply needs (the profile's state, its masks) and hands the worker only pure functions of bytes
and values (gateway.make_apps reply_worker: a Lane, one profile's turn); the result, or the exception, goes back to
the loop that asked. Jobs wait in one queue per profile and the profiles take turns (round robin): a profile with a job
in process is out of turn until that job is done, so at most one job per profile is in process, and with one thread
at most one in all, as on the loop before: one reply is parsed (amplified in memory) at a time. A profile that sends
many large replies makes another profile's reply wait for at most the one job in process.

The GIL, and why the worker breathes. The thread holds the GIL while it runs. CPython hands the GIL to a waiting thread
after its switch interval (sys.getswitchinterval(), 5 ms), but only between bytecodes, and the event loop's thread lets
the GIL go at every system call it makes (each epoll_wait, socket send, file read: store.load alone makes five): a
CPU-bound worker takes it back at once, and the loop then waits again for its next bytecode boundary (the GIL convoy).
Measured in HM-30 (provenance note): while the worker ran back-to-back C calls of 10 ms, one small file read of the loop
took 30 to 60 ms instead of 0.02 ms, another profile's tools/call p99 was 4.5 s and the loop's longest stop 1.3 s. So
the worker breathes: at every checkpoint (between jobs, between a job's steps, and in the parser once per JSON object:
config.strict_json checkpoint), once it has run SLICE_SECONDS since its last breath, it sleeps BREATH_SECONDS, and goes
on sleeping in short steps while the loop is busy (callbacks ready to run in asyncio's own queue, or its thread
anywhere but waiting in its selector), up to YIELD_SECONDS: the loop has the GIL to itself meanwhile (the same file
reads: 0.03 to 0.05 ms at the median). Busy without a pause, the worker gives up about a third of its time to it; idle,
nothing. What no checkpoint can split is one C call: the loop waits until it returns, so its longest stop is a reply's
longest single C call, not its whole processing (contract 6 has the thresholds; the provenance note has what real 8 MiB
replies cost).

In pieces (D1, the user's decision of 2026-11-16, D1 (a); contract 6). One json.dumps of a whole 8 MiB value was such a
call (45 to 70 ms on the EPYC 7713, 0.1 s and more for many small objects), so the worker serializes in pieces
(encoded): byte for byte json.dumps(value, separators=(",", ":")).encode(), the bytes the loop writes, but no C call of
it encodes more than about PIECE_BYTES: a long string goes out STRING_PIECE code points at a time (json escapes each
code point on its own, so the pieces join into the same bytes) and a large list or dict member by member, in runs
whose most bytes fit PIECE_BYTES, with a checkpoint between the calls. The other long stops a large reply made on the
worker went the same way: it holds the cyclic collector off while it processes a job (gc.disable, given back when the
job ends, however it ends; left off when something else had it off: a full collection walks every object of the add-on,
the reply's hundreds of thousands among them, in one C call, 50 to 75 ms measured on an add-on's heap, and a reply
makes no reference cycle, so its objects go as soon as it is answered and push no collection after it; collections
resume between the jobs); it lets go of a reply's parsed and masked values in pieces once it is encoded (released:
freeing hundreds of thousands of objects at once is one C call, 15 to 35 ms); it breathes while it masks one
(redact.redact_secrets checkpoint) and while it costs one (_plan). Still one C call each: json.loads scanning one long
string (20 to 40 ms for 8 MiB, the most with many escapes), its decoding of the bytes (5 to 20 ms) and the final join of
the pieces (a copy).

Failures. A job's exception (any BaseException) is its caller's: it is re-raised on the loop, where the gateway
answers it as before; its frames are cleared first (nothing the job held stays alive with it), and the thread goes on.
Should the thread itself end (a fault of this module, never of a job), every queued job and every later one gets
WorkerStopped at once (a request is answered, never left waiting), ended is set, one WARNING names the exception's class,
and run_product stops the add-on, which the Supervisor then restarts (as for any component of the runtime that stops).
stop(): no new job; the queued ones get WorkerStopped at once; the job in process is waited for at most STOP_SECONDS
(HA stops an add-on within 30 s) and its result still reaches its caller when that caller still waits; the thread is a
daemon, so a job inside one long C call never holds up the process's exit. A caller that is cancelled (its client
left, its token changed: the gateway awaits under the token lease) withdraws its job if it is still queued; a job in
process runs to its end and its result is dropped.

The thread has a stack of its own (STACK_BYTES), so a reply nested past CPython's C recursion limit raises
RecursionError there as on the main thread (a 502), whatever stack the platform gives threads by default.

Nothing here logs a job's content or a profile's name: the WARNING carries the exception's class only.
"""
from __future__ import annotations

from array import array
import asyncio
from collections import Counter, deque
import gc
import json
import logging
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)

THREAD_NAME = 'mcp-reply-worker'
STOP_SECONDS = 5.0       # how long stop() waits for the job in process (HA's stop limit is 30 s)
STOP_POLL_SECONDS = 0.01
# The worker thread's own stack, whatever the process's default for threads is (glibc: RLIMIT_STACK, or 2 MiB when it
# is unlimited; a 1 MiB stack crashes json.loads on a reply nested 9,000 deep). With it a reply nested past CPython's C
# recursion limit raises RecursionError on the worker, as it does on the event loop's main thread: a 502, never a crash
# of the add-on (4 MiB was measured enough for json's limit; 16 MiB leaves room).
STACK_BYTES = 16 * 1024 * 1024
# The worker's breath (the module docstring): after a run of SLICE_SECONDS, at its next checkpoint, it lets the GIL go
# for BREATH_SECONDS, then in steps for as long as the loop is busy, up to YIELD_SECONDS in all. Measured (provenance
# note, CPU-starvation test): the loop's longest stop while the worker processed A's replies 17-27 ms (contract 6: at
# most 50 ms), the other profile's tools/call p99 0.38-0.44 s (at most 0.7 s).
SLICE_SECONDS = 0.005
BREATH_SECONDS = 0.002
YIELD_SECONDS = 0.010   # how long one checkpoint may wait in all while the loop has callbacks ready to run
YIELD_STEP_SECONDS = 0.0005
_breath = threading.local()  # set on the worker thread only: since (its last breath or wake-up), ready, loop_thread


def breathe():
    """A checkpoint (see the module docstring): on the worker thread, once it has run SLICE_SECONDS since its last breath
    or since it woke up, it sleeps BREATH_SECONDS, and goes on sleeping in steps while the event loop it serves is busy
    (_loop_busy), at most YIELD_SECONDS in all (the loop goes first; the worker still gets on). Anywhere else,
    nothing: the event loop's own processing (a product that is not switched on) never sleeps."""
    since = getattr(_breath, 'since', None)
    if since is None:
        return
    if time.perf_counter() - since < SLICE_SECONDS:
        return
    time.sleep(BREATH_SECONDS)
    waited = BREATH_SECONDS
    while waited < YIELD_SECONDS and _loop_busy():
        time.sleep(YIELD_STEP_SECONDS)
        waited += YIELD_STEP_SECONDS
    _breath.since = time.perf_counter()


def _loop_busy():
    """Whether the event loop's thread has something to do: callbacks ready to run (asyncio's own queue of them), or it
    is anywhere but waiting for I/O in its selector (running a callback, in a system call, or waiting for the GIL after
    one). Its queue and its current frame (sys._current_frames) are read under the GIL; a loop the worker cannot see
    into counts as idle (then only the fixed breath). The frame alone would miss a loop that polls its selector with a
    zero timeout because callbacks are ready; the queue alone would miss the callback it runs now."""
    ready = getattr(_breath, 'ready', None)
    if ready:
        return True
    ident = getattr(_breath, 'loop_thread', None)
    frame = sys._current_frames().get(ident) if ident is not None else None
    return frame is not None and not (frame.f_code.co_name == 'select'
                                      and frame.f_code.co_filename.endswith('selectors.py'))


# In pieces (D1; the module docstring): the most code points of a long string one C call encodes (at most 12 bytes each
# once escaped: 96 KiB), and the most bytes (counted as the most they can encode to) one call encodes of a large list
# or dict. Measured (provenance note): the loop's longest stop on the worker's 8 MiB replies of seven shapes 7 to 31 ms.
STRING_PIECE = 8 * 1024
PIECE_BYTES = 64 * 1024
_encode = json.JSONEncoder(separators=(",", ":")).encode  # json.dumps(value, separators=(",", ":")), the loop's
_SMALL_INT = 10 ** 18


def _scalar_cost(value):
    """The most bytes a scalar encodes to: 24 (a float's repr, a small int, true, false, null), a larger int its
    digits."""
    if type(value) is int and not -_SMALL_INT < value < _SMALL_INT:
        return 24 + value.bit_length() // 3
    return 24


def _plan(value, limit, checkpoint=None):
    """{id(container): its members' costs} for every list and dict of value that may encode to more than limit bytes
    (large). A member's cost is the most bytes it can encode to: a string 12 bytes a code point (the longest escape json
    writes) and its quotes, a scalar _scalar_cost, a container its members' and a separator each, 2 brackets (a member
    over limit counts as limit + 1), a dict member its key as a string and a colon too. One pass, post-order and
    iterative: every container is costed once, however deep; checkpoint is called after every container."""
    plans = {}
    kind = type(value)
    if kind is not list and kind is not dict:
        return plans
    # a frame: [container, its members, keyed, their costs, its cost so far, the key cost of the member costed below]
    stack = [[value, iter(value.items()) if kind is dict else iter(value), kind is dict, array('q'), 2 + len(value), 0]]
    while stack:
        frame = stack[-1]
        members, keyed, costs = frame[1], frame[2], frame[3]
        below = False
        for member in members:
            if keyed:
                key, item = member
                extra = 12 * len(key) + 3 if type(key) is str else 24
            else:
                item, extra = member, 0
            kind = type(item)
            if kind is str:
                cost = 12 * len(item) + 2 + extra
            elif kind is list or kind is dict:
                frame[5] = extra
                stack.append([item, iter(item.items()) if kind is dict else iter(item), kind is dict, array('q'),
                              2 + len(item), 0])
                below = True
                break
            else:
                cost = _scalar_cost(item) + extra
            costs.append(cost)
            frame[4] += cost
        if below:
            continue
        stack.pop()
        if checkpoint is not None:
            checkpoint()
        total = frame[4]
        if total > limit:
            plans[id(frame[0])] = frame[3]
            total = limit + 1
        if stack:
            parent = stack[-1]
            cost = total + parent[5]
            parent[3].append(cost)
            parent[4] += cost
    return plans


def encoded(value, checkpoint=None, *, prefix=b'', suffix=b'', release=False, twin=None):
    """json.dumps(value, separators=(",", ":")).encode(), byte for byte, in pieces (the module docstring): a large list
    or dict (_plan) is opened and its members written in runs that fit PIECE_BYTES, each one C call (json's own encoder
    on a list or dict of them, the brackets cut off), a member that does not fit alone (a large container opened in
    turn; a long string, or key, STRING_PIECE code points at a time); checkpoint is called between the calls. A value
    json.dumps converts in ways of its own (a dict with keys that are not strings, a tuple, a subclass) is
    encoded in one call, as json.dumps encodes it. A JSON value has no reference cycle (the gateway's values come from
    strict_json through redact_secrets, which would recurse forever on one first). prefix and suffix: bytes the answer
    starts and ends with, joined in the same one copy (an event's other lines and its end). release: once encoded,
    value (and twin) are let go of in pieces (released): only for a value whose containers nothing else holds."""
    plans = _plan(value, PIECE_BYTES, checkpoint)
    if not plans and not (type(value) is str and len(value) > STRING_PIECE):
        return prefix + _encode(value).encode() + suffix
    out = [prefix]
    put = out.append
    frames = []  # the large containers open now: [members, their costs, next member, closing, keyed, members written]

    def step():
        if checkpoint is not None:
            checkpoint()

    def string(text):
        put(b'"')
        for start in range(0, len(text), STRING_PIECE):
            put(_encode(text[start:start + STRING_PIECE])[1:-1].encode())
            step()
        put(b'"')

    def write(item):
        """A member that fits no run, or the value: a large list or dict opened (True), anything else written."""
        kind = type(item)
        if (kind is list or kind is dict) and id(item) in plans and (
                kind is list or all(type(key) is str for key in item)):
            if kind is dict:
                put(b'{')
                frames.append([iter(item.items()), plans[id(item)], 0, b'}', True, 0])
            else:
                put(b'[')
                frames.append([iter(item), plans[id(item)], 0, b']', False, 0])
            return True
        if kind is str and len(item) > STRING_PIECE:
            string(item)
        else:
            put(_encode(item).encode())
            step()
        return False

    def flush(frame, run):
        text = _encode(dict(run) if frame[4] else run)
        put((b',' if frame[5] else b'') + text[1:-1].encode())
        frame[5] += len(run)
        step()

    write(value)
    while frames:
        frame = frames[-1]
        members, costs, keyed = frame[0], frame[1], frame[4]
        run, size, opened = [], 2, False  # a run's bytes: its brackets, its members and a separator each
        for member in members:
            cost = costs[frame[2]] + 1
            frame[2] += 1
            if cost < PIECE_BYTES - 1:
                if size + cost > PIECE_BYTES:
                    flush(frame, run)
                    run, size = [], 2
                run.append(member)
                size += cost
                continue
            if run:
                flush(frame, run)
                run, size = [], 2
            put(b',' if frame[5] else b'')
            frame[5] += 1
            if keyed:
                key, member = member
                if type(key) is str and len(key) > STRING_PIECE:
                    string(key)
                    put(b':')
                else:
                    put(_encode(key).encode() + b':')
            if write(member):
                opened = True
                break
        if run:
            flush(frame, run)
        if opened:
            continue
        put(frame[3])
        frames.pop()
    put(suffix)
    body = b''.join(out)
    out = None
    if release:
        released(value, plans, checkpoint, twin)
    return body


def released(value, plans, checkpoint=None, twin=None):
    """Lets go of value in pieces once the worker is done with it (D1; the module docstring), and of twin with it, a
    tree of value's shape (what value was copied from: strict_json's parse, copied by redact_secrets). Every large list
    or dict of value (plans: _plan's) is emptied, its members dropped in runs whose costs fit PIECE_BYTES (each run's
    objects freed together; a checkpoint between the runs), its large members first set apart and emptied the same way
    after it; twin's container of the same place, when it has the same type and length, with it, member for member
    (its members dropped with value's). Dropping references only: an object something else still holds stays. Only for
    a value whose large containers nothing else holds (a reply the gateway made: strict_json's and redact_secrets'
    objects, never one filter_list rebuilt a tool list in, whose tools hold the policy's own schemas)."""
    if type(value) is not list and type(value) is not dict or id(value) not in plans:
        return
    stack = [(value, twin)]
    while stack:
        node, other = stack.pop()
        costs = plans[id(node)]
        keyed = type(node) is dict
        members = list(node.items()) if keyed else node[:]
        others = None
        if type(other) is type(node) and len(other) == len(node):
            others = list(other.items()) if keyed else other[:]
            other.clear()
        node.clear()
        node = other = None
        start = size = 0
        for index in range(len(members)):
            item = members[index][1] if keyed else members[index]
            if (type(item) is list or type(item) is dict) and id(item) in plans:
                twin_item = None
                if others is not None:
                    twin_item = others[index][1] if keyed else others[index]
                stack.append((item, twin_item))  # emptied after this one: held here until then
                continue
            size += costs[index]
            if size > PIECE_BYTES:
                members[start:index] = [None] * (index - start)
                if others is not None:
                    others[start:index] = [None] * (index - start)
                start, size = index, costs[index]
                if checkpoint is not None:
                    checkpoint()
        members = others = None
        if checkpoint is not None:
            checkpoint()


class WorkerStopped(Exception):
    """The reply worker processes no more jobs (it was stopped, or its thread ended)."""


class _Job:
    __slots__ = ('profile', 'function', 'args', 'loop', 'future')

    def __init__(self, profile, function, args, loop, future):
        self.profile, self.function, self.args, self.loop, self.future = profile, function, args, loop, future


def _settle(future, result, error):
    """On the caller's loop: the job's outcome, unless its caller is gone (the future was cancelled). A StopIteration
    (which a future refuses) reaches the caller as a RuntimeError, as asyncio does for a coroutine that raises one."""
    if future.done():
        return
    if isinstance(error, StopIteration):
        error = RuntimeError('a reply job raised StopIteration')
    if error is not None:
        future.set_exception(error)
    else:
        future.set_result(result)


class Lane:
    """One profile's turn on the add-on's reply worker (gateway.make_apps reply_worker)."""
    __slots__ = ('worker', 'profile')

    def __init__(self, worker, profile):
        self.worker, self.profile = worker, profile

    def run(self, function, *args):
        """function(*args) on the worker in this profile's turn (ReplyWorker.run)."""
        return self.worker.run(self.profile, function, *args)


class ReplyWorker:
    """The add-on's reply worker (see the module docstring). start() on the loop that will use it, run() or a lane's
    run() for each job, stop() when the listeners stopped. ended (an asyncio.Event of that loop) is set as the thread
    ends: the thread may still be returning then (alive turns False just after it; stop() waits for that); failure is
    what ended it when that was not stop(). processed and peak count the jobs done and the most in process at once
    (never more than one); handed counts the jobs each profile handed over."""

    def __init__(self):
        self._lock = threading.Lock()
        self._work = threading.Condition(self._lock)
        self._queues = {}        # profile -> deque of its queued jobs
        self._turns = deque()    # profiles with a queued job and none in process, in turn order
        self._running = {}       # profile -> its job in process
        self._accepting = False
        self._thread = None
        self._loop = self._loop_thread = None
        self.ended = None
        self.failure = None
        self.processed = 0
        self.peak = 0
        self.handed = Counter()  # jobs each profile handed over so far (the tests read it; nothing else does yet)

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self._thread is not None:
            raise RuntimeError('reply worker already started')
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.get_ident()
        self.ended = asyncio.Event()
        self._accepting = True
        previous = threading.stack_size(STACK_BYTES)  # for this thread only: the process's default comes back below
        try:
            self._thread = threading.Thread(target=self._main, name=THREAD_NAME, daemon=True)
            self._thread.start()
        finally:
            threading.stack_size(previous)
        return self

    def lane(self, profile):
        return Lane(self, profile)

    async def run(self, profile, function, *args):
        """function(*args) on the worker thread, in profile's turn; its result, or its exception raised here.
        WorkerStopped when the worker takes no more jobs."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        job = _Job(profile, function, args, loop, future)
        with self._lock:
            if not self._accepting:
                raise WorkerStopped()
            queue = self._queues.get(profile)
            if queue is None:
                queue = self._queues[profile] = deque()
            queue.append(job)
            self.handed[profile] += 1
            if len(queue) == 1 and profile not in self._running:
                self._turns.append(profile)
            self._work.notify()
        try:
            return await future
        except asyncio.CancelledError:
            self._withdraw(job)
            raise

    def _withdraw(self, job):
        """A cancelled caller's job leaves its queue if it is still there (a job in process runs to its end)."""
        with self._lock:
            queue = self._queues.get(job.profile)
            if queue is None or job not in queue:
                return
            queue.remove(job)
            if not queue:
                del self._queues[job.profile]
                try:
                    self._turns.remove(job.profile)
                except ValueError:
                    pass
        job.function = job.args = None

    # ---- the thread ----

    def _next(self):
        """The next job in turn, once there is one (the worker breathes first when it has been busy: a checkpoint);
        None when the worker stops and no job is queued."""
        breathe()
        with self._lock:
            idle = not self._turns
            while not self._turns and self._accepting:
                self._work.wait()
            if not self._turns:
                return None
            if idle:
                _breath.since = time.perf_counter()  # it waited: a new run starts now
            profile = self._turns.popleft()
            queue = self._queues[profile]
            job = queue.popleft()
            if not queue:
                del self._queues[profile]
            self._running[profile] = job
            self.peak = max(self.peak, len(self._running))
            return job

    def _done(self, job):
        with self._lock:
            del self._running[job.profile]
            self.processed += 1
            if job.profile in self._queues:
                self._turns.append(job.profile)

    def _deliver(self, job, result, error):
        try:
            job.loop.call_soon_threadsafe(_settle, job.future, result, error)
        except RuntimeError:
            pass  # its loop is closed: nobody waits for it any more

    def _main(self):
        _breath.since = time.perf_counter()
        # What _loop_busy reads: the loop's thread, and its queue of callbacks ready to run (asyncio's own deque; another
        # loop implementation may not have one: then only the loop thread's frame).
        _breath.loop_thread = self._loop_thread
        _breath.ready = getattr(self._loop, '_ready', None)
        try:
            while (job := self._next()) is not None:
                result = error = None
                # D1: the cyclic collector held off while the job runs (the module docstring), given back however it
                # ends; left as it is when something else had it off.
                held = gc.isenabled()
                if held:
                    gc.disable()
                try:
                    result = job.function(*job.args)
                except BaseException as caught:  # the caller's, never the thread's
                    error = caught
                    traceback.clear_frames(caught.__traceback__)
                finally:
                    if held:
                        gc.enable()
                job.function = job.args = None
                self._done(job)  # before the caller can see the outcome: processed and the turns are up to date
                self._deliver(job, result, error)
                result = error = None
        except BaseException as fault:
            self.failure = fault
            logger.warning('MCP reply worker: its thread stopped (%s); replies cannot be processed and the add-on '
                           'stops', type(fault).__name__)
        finally:
            self._end()

    def _end(self):
        """The thread ends: no job is taken any more; every job still queued or taken (a fault between taking and
        delivering) gets WorkerStopped; ended is set on the starting loop."""
        with self._lock:
            self._accepting = False
            jobs = [job for queue in self._queues.values() for job in queue] + list(self._running.values())
            self._queues.clear()
            self._turns.clear()
            self._running.clear()
        for job in jobs:
            self._deliver(job, None, WorkerStopped())
        try:
            self._loop.call_soon_threadsafe(self.ended.set)
        except RuntimeError:
            pass

    # ---- stopping ----

    async def stop(self):
        """No new job; the queued ones get WorkerStopped at once; the job in process is waited for at most STOP_SECONDS
        (the thread is a daemon: one that does not end then never holds up the process's exit). Never raises."""
        with self._lock:
            self._accepting = False
            jobs = [job for queue in self._queues.values() for job in queue]
            self._queues.clear()
            self._turns.clear()
            self._work.notify_all()
        for job in jobs:
            self._deliver(job, None, WorkerStopped())
            job.function = job.args = None
        thread = self._thread
        if thread is None:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STOP_SECONDS
        while thread.is_alive() and loop.time() < deadline:
            await asyncio.sleep(STOP_POLL_SECONDS)
        await asyncio.sleep(0)  # what the thread handed back before it ended (ended among it) reaches the loop first
        if not thread.is_alive():
            self.ended.set()

    async def __aenter__(self):
        return self.start()

    async def __aexit__(self, *exc_info):
        await self.stop()
