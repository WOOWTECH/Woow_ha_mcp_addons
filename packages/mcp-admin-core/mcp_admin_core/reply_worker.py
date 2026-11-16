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
nothing. What no checkpoint can split is one C call (json.loads scanning one long string, json.dumps of a whole value,
str.replace on a long string): the loop waits until it returns, so its longest stop is a reply's longest single C
call, not its whole processing (contract 6 has the thresholds; the provenance note has what a real 8 MiB reply costs).

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

import asyncio
from collections import Counter, deque
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
                try:
                    result = job.function(*job.args)
                except BaseException as caught:  # the caller's, never the thread's
                    error = caught
                    traceback.clear_frames(caught.__traceback__)
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
