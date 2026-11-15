"""Bounded child supervision; backend failures never drive this restart loop.

HM-09 (multi-profile plan 5.4; contract 7; DQ-20 (b)): once a product is switched on (features.enabled), every
profile's Supervisor, the default profile's included, gets the PaaS watchdog (WATCHDOG: Pc/process.py
AUTO_RESTART_DELAYS and STABLE_SECONDS @69ac425, unchanged at cf3d0d5): an exit, a spawn failure or a refused start
backs off 2, 5, 15, 30, 60, 120, 300 s, then 300 s for ever (no attempt limit), and a run of STABLE_SECONDS or more
starts the table again. Before each spawn its preflight (the profile manager's spawn check) may refuse: status blocked
with the reason code (contract 3.6: child_port_conflict, child_port_in_use, memory_capacity), no process, and another
attempt after the backoff. An additional profile's child gets ChildResources (oom_score_adj 500, nice +5), which the
child writes itself before it execs the real command (EXEC_WRAPPER). ChildLog writes the lifecycle events (contract
7), at most one line per profile and situation a minute (LifecycleLog).

A Supervisor built without these options (every product that is not switched on: run_product's default profile and
n8n's runtime) is the one before HM-09: at most retries + 1 starts in one start, about 1, 2 and 4 s apart, no reset
however long a run lasted, then failed; no log line, no spawn check, no wrapper.
"""
import asyncio
from collections import OrderedDict
import ctypes
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import random
import shutil
import signal
import re
import sys
import time

import anyio

from .diagnostics import ChildLogs

logger = logging.getLogger(__name__)


async def _join_transition(operation):
    """Finish owned lifecycle work before propagating caller cancellation."""
    with anyio.CancelScope(shield=True):
        task = asyncio.create_task(operation)
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError


@dataclass(frozen=True)
class ChildSpec:
    argv: tuple[str, ...]
    env: dict[str, str] = field(repr=False)
    cwd: Path


# HM-04 (multi-profile plan 5.4): a child's loopback port is a parameter. The default profile's child keeps 3000, its
# argv, environment and URL exactly as before; an extra profile's child gets a port of its own (18000 and up).
CHILD_PORT = 3000


def child_port_text(port: int) -> str:
    """A child's port as its argv or environment carries it; anything but an int 1-65535 (a bool too) is refused."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid child port')
    return str(port)


def child_url(port: int = CHILD_PORT) -> str:
    """Where the gateway, the health monitor and the capability probe reach the child listening on port."""
    return f'http://127.0.0.1:{child_port_text(port)}/mcp'


CHILD_URL = child_url()  # the default profile's child


# ---- HM-09: the watchdog, the spawn check's reasons, child resources and lifecycle events ----

AUTO_RESTART_DELAYS = (2, 5, 15, 30, 60, 120, 300)  # PaaS process.AUTO_RESTART_DELAYS
STABLE_SECONDS = 120  # PaaS process.STABLE_SECONDS: a run this long starts the table again
WATCHDOG = {'delays': AUTO_RESTART_DELAYS, 'max_attempts': None, 'stable_seconds': STABLE_SECONDS}

# Why a child is not started (contract 3.6 blocked_reason; PaaS process.CHILD_PORT_CONFLICT, CHILD_PORT_IN_USE).
CHILD_PORT_CONFLICT = 'child_port_conflict'
CHILD_PORT_IN_USE = 'child_port_in_use'
MEMORY_CAPACITY = 'memory_capacity'
BLOCKED_REASONS = frozenset({CHILD_PORT_CONFLICT, CHILD_PORT_IN_USE, MEMORY_CAPACITY})

EVENT_SECONDS = 60  # one line per profile and situation this often (PaaS gateway_pool.REPORT_INTERVAL_SECONDS)
MAX_EVENT_KEYS = 256
RESOURCE_REPORT_SECONDS = 5  # how long the Supervisor waits for the wrapper's report


class LifecycleLog:
    """The add-on's lifecycle events: one WARNING per (profile, situation) an EVENT_SECONDS window, the first one
    written, the others counted, and the next line written ends with suppressed=N (the add-on log shows WARNING and
    above). text is complete fixed text: never a token, a URL, a label or a backend's own words. At most
    MAX_EVENT_KEYS situations are remembered (expired ones go first, then the oldest)."""

    def __init__(self):
        self.clock = time.monotonic
        self.state = OrderedDict()  # (profile key, situation) -> [when the next line may be written, suppressed]

    def warn(self, key, situation, text):
        now = self.clock()
        name = (key, situation)
        entry = self.state.get(name)
        if entry is not None and now < entry[0]:
            entry[1] += 1
            return
        suppressed = entry[1] if entry is not None else 0
        self.state.pop(name, None)
        if len(self.state) >= MAX_EVENT_KEYS:
            for stale in [item for item, value in self.state.items() if value[0] <= now]:
                del self.state[stale]
            while len(self.state) >= MAX_EVENT_KEYS:
                self.state.popitem(last=False)
        self.state[name] = [now + EVENT_SECONDS, 0]
        logger.warning(text + (f' suppressed={suppressed}' if suppressed else ''))

    def forget(self, key):
        """A deleted profile's situations (HM-10)."""
        for name in [item for item in self.state if item[0] == key]:
            del self.state[name]


@dataclass(frozen=True)
class ChildLog:
    """How one profile's child events are written (contract 7; PaaS process._tag): `MCP child [profile=<name>
    port=<port> pid=<pid>]: <text>`. key: the profile id (never written); name: profiles.log_id (default or the id's
    first 8 characters)."""
    events: LifecycleLog
    key: str
    name: str
    port: int

    def tag(self, pid=None):
        return f'[profile={self.name} port={self.port}' + ('' if pid is None else f' pid={pid}') + ']'

    def __call__(self, situation, text, pid=None):
        self.events.warn(self.key, situation, f'MCP child {self.tag(pid)}: {text}')


@dataclass(frozen=True)
class ChildResources:
    """What an additional profile's child gets (plan 5.4; C2-SF-10): oom_score_adj written as this absolute value (the
    add-on's container is at 200, HA Core at -300: the kernel prefers to kill these children, not the management
    process; no guarantee, the score also weighs memory) and its nice value raised by nice. Raising either needs no
    privilege; what the platform refuses is not assumed (Supervisor.resource_state, one WARNING)."""
    oom_score_adj: int = 500
    nice: int = 5

    def __post_init__(self):
        if type(self.oom_score_adj) is not int or not -1000 <= self.oom_score_adj <= 1000:
            raise ValueError('invalid oom_score_adj')
        if type(self.nice) is not int or not -39 <= self.nice <= 39:
            raise ValueError('invalid nice increment')


EXTRA_CHILD_RESOURCES = ChildResources()

# The exec wrapper (python -I -S -c): a fresh single-threaded interpreter between the fork and the real command, so no
# Python runs in the forked child of the management process (it has threads: no preexec_fn; PaaS child_identity uses
# the same kind of wrapper). argv: the report pipe, oom_score_adj, the nice increment, the original LC_CTYPE ('-' for
# none, '=value' otherwise), the program to exec, then the real argv. It writes /proc/self/oom_score_adj and raises
# its nice value, reports 'o' and 'n' for what worked on the pipe and closes it, undoes what its own start changed
# (PEP 538's LC_CTYPE; SIGPIPE, SIGXFZ, SIGXFSZ ignored, which an exec would keep), and execs the real command with
# the environment it was given. 127: the real command cannot be executed.
EXEC_WRAPPER = r"""import os,signal,sys
fd=int(sys.argv[1]);adj=sys.argv[2].encode();inc=int(sys.argv[3]);lc=sys.argv[4];path=sys.argv[5]
done=b''
try:
 f=os.open('/proc/self/oom_score_adj',os.O_WRONLY|os.O_CLOEXEC)
 try:
  os.write(f,adj);done+=b'o'
 finally:os.close(f)
except OSError:pass
try:
 os.setpriority(os.PRIO_PROCESS,0,os.getpriority(os.PRIO_PROCESS,0)+inc);done+=b'n'
except OSError:pass
try:os.write(fd,done or b'-')
except OSError:pass
os.close(fd)
if lc=='-':os.environ.pop('LC_CTYPE',None)
else:os.environ['LC_CTYPE']=lc[1:]
for n in('SIGPIPE','SIGXFZ','SIGXFSZ'):
 if hasattr(signal,n):signal.signal(getattr(signal,n),signal.SIG_DFL)
try:os.execv(path,sys.argv[6:])
except OSError:
 os.write(2,b'woow-mcp: the MCP child cannot be executed\n');os._exit(127)
"""


def _resolve(program, env):
    """The program the real command runs, as Popen finds it (the environment's PATH), or None."""
    if not program:
        return None
    if os.sep in program:
        return program if os.path.isfile(program) and os.access(program, os.X_OK) else None
    return shutil.which(program, path=os.pathsep.join(os.get_exec_path(env)))


class Supervisor:
    def __init__(self, spec: ChildSpec | None, *, retries=3, backoff=1.0, grace=3.0, delays=None, max_attempts=None,
                 stable_seconds=STABLE_SECONDS, preflight=None, log=None, resources=None):
        # Linux/HA runtime: adopt orphan grandchildren, then reap only OUR group.
        # This is unprivileged and does not replace the container's init process.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise RuntimeError("child subreaper unavailable")
        if delays is not None:
            delays = tuple(delays)
            if not delays or any(type(delay) not in (int, float) or not delay > 0 for delay in delays):
                raise ValueError('invalid watchdog delays')
            if max_attempts is not None and (type(max_attempts) is not int or max_attempts < 1):
                raise ValueError('invalid watchdog attempts')
            if type(stable_seconds) not in (int, float) or not stable_seconds > 0:
                raise ValueError('invalid stable run')
        if preflight is not None and not callable(preflight):
            raise ValueError('invalid spawn check')
        if resources is not None and not isinstance(resources, ChildResources):
            raise ValueError('invalid child resources')
        self.spec = spec
        self.retries, self.backoff, self.grace = retries, backoff, grace
        # HM-09: delays given, the watchdog (max_attempts None: no limit); left out, retries + 1 starts as before.
        self.delays, self.max_attempts, self.stable_seconds = delays, max_attempts, stable_seconds
        self.preflight, self.log, self.resources = preflight, log, resources
        self.process = None
        self.task = None
        self.status = "stopped"
        self.starts = 0
        self.last_exit = None
        self.ready = False
        self.blocked_reason = None  # why the child is not started (contract 3.6), while status is blocked
        self.failures = 0  # watchdog: failed attempts (exits, spawn failures, refusals) since the last stable run
        self.retry_in = None  # watchdog: the backoff being waited out now, in seconds
        self.resource_state = None  # what the wrapper applied: {'oom_score_adj': bool, 'nice': bool}
        self.clock = time.monotonic  # the watchdog's clock (a stable run); tests replace it
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._kick = asyncio.Event()
        self.logs = ChildLogs()

    def _event(self, situation, text, pid=None):
        if self.log is not None:
            self.log(situation, text, pid)

    def _refusal(self):
        """None, or (reason, detail) when the preflight refuses this start. A check that fails is a refusal too (fail
        closed: the next attempt checks again)."""
        if self.preflight is None:
            return None
        try:
            refusal = self.preflight()
        except Exception as error:
            return CHILD_PORT_IN_USE, f'the port check failed ({type(error).__name__})'
        if refusal is None:
            return None
        reason, detail = refusal
        if reason not in BLOCKED_REASONS or not isinstance(detail, str):
            raise ValueError('invalid spawn refusal')
        return reason, detail

    def _block(self, refusal):
        reason, detail = refusal
        self.status, self.blocked_reason, self.ready = 'blocked', reason, False
        self._event('blocked', (f'not started ({reason}): ' if reason else 'not started: ') + detail)

    def block(self, reason, detail):
        """HM-09: not started at all (a disabled profile, too little memory): status blocked with reason (one of
        BLOCKED_REASONS, or None when the profile list's disabled_reason says why), no process and no retry; the
        profile's runtime starts it again (a save, the panel's restart, an index change). The child must be stopped."""
        if self.task is not None or self.process is not None:
            raise RuntimeError('child cleanup required before blocking')
        if reason is not None and reason not in BLOCKED_REASONS:
            raise ValueError('invalid blocked reason')
        self._block((reason, detail))

    def _start_child(self):
        if self.task is None and self.process is not None:
            raise RuntimeError("child cleanup required before start")
        self.blocked_reason = None
        if self.spec is None:
            self.status = 'unconfigured'
            return
        if self.task is None:
            refusal = self._refusal()
            if refusal is not None:
                self._stop.clear()
                self._block(refusal)
                if self.delays is not None:
                    self.task = asyncio.create_task(self._watch(refused=True))
                return
            self.status = "starting"
            self._stop.clear()
            self.task = asyncio.create_task(self._run())

    async def start(self):
        async with self._lock:
            self._start_child()

    def retry_now(self):
        """End the backoff being waited out now (the profile manager after an index change)."""
        self._kick.set()

    @staticmethod
    def _signal(pid, sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    async def _terminate(self, process):
        # Always clean the group, even if its leader already exited.
        self._signal(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=self.grace)
        except TimeoutError:
            pass
        # Remaining descendants may outlive an already reaped leader.
        self._signal(process.pid, signal.SIGKILL)
        # Bound both the leader's post-KILL wait and group-scoped reaping.
        # Never use waitpid(-1), which could race unrelated subprocesses.
        async with asyncio.timeout(self.grace + 1):
            await process.wait()
            while True:
                try:
                    pid, _ = os.waitpid(-process.pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    await asyncio.sleep(0.01)

    def _spawn_plan(self):
        """(argv, extra create_subprocess_exec options, the read end of the wrapper's report pipe or None): through
        EXEC_WRAPPER when the child has resources, else the spec's argv as before."""
        if self.resources is None:
            return self.spec.argv, {}, None
        program = _resolve(self.spec.argv[0] if self.spec.argv else '', self.spec.env)
        if program is None:
            return self.spec.argv, {}, None  # spawned as before: a missing program fails as before
        if not sys.executable:
            # HM-09 review S-12: no interpreter to run the wrapper: the child starts as before, without its resources,
            # and says so (never assumed applied).
            self.resource_state = {'oom_score_adj': False, 'nice': False}
            self._event('resources', f'child resources not applied (oom_score_adj {self.resources.oom_score_adj}, '
                                     f'nice {self.resources.nice:+d}: no interpreter for the wrapper); it runs '
                                     'without them')
            return self.spec.argv, {}, None
        read, write = os.pipe()
        lc_ctype = '=' + self.spec.env['LC_CTYPE'] if 'LC_CTYPE' in self.spec.env else '-'
        argv = (sys.executable, '-I', '-S', '-c', EXEC_WRAPPER, str(write), str(self.resources.oom_score_adj),
                str(self.resources.nice), lc_ctype, program, *self.spec.argv)
        return argv, {'pass_fds': (write,)}, read

    async def _resources_applied(self, fd, pid):
        """Read what the wrapper applied (until it closes the pipe, at most RESOURCE_REPORT_SECONDS): resource_state,
        and one WARNING naming what was not applied (the child runs anyway)."""
        loop = asyncio.get_running_loop()
        data = bytearray()
        ended = loop.create_future()

        def readable():
            try:
                chunk = os.read(fd, 64)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                chunk = b''
            if chunk and len(data) < 64:
                data.extend(chunk)
                return
            if not ended.done():
                ended.set_result(None)
        try:
            os.set_blocking(fd, False)
            loop.add_reader(fd, readable)
            try:
                await asyncio.wait_for(ended, RESOURCE_REPORT_SECONDS)
            except TimeoutError:
                pass
            finally:
                loop.remove_reader(fd)
        finally:
            os.close(fd)
        applied = {'oom_score_adj': b'o' in data, 'nice': b'n' in data}
        self.resource_state = applied
        missing = ([] if applied['oom_score_adj'] else [f'oom_score_adj {self.resources.oom_score_adj}']) + (
            [] if applied['nice'] else [f'nice {self.resources.nice:+d}'])
        if missing:
            self._event('resources', 'child resources not applied (' + ', '.join(missing) + '); it runs without them',
                        pid)

    async def _attempt(self):
        """One spawn: the child runs until it exits or a stop is asked, then its group is cleaned up. Returns how long
        it ran (self.clock), None when it could not be spawned."""
        readers = []
        self.starts += 1
        self.status = "starting"
        ran = None
        report = None
        try:
            argv, options, report = self._spawn_plan()
            try:
                self.process = await asyncio.create_subprocess_exec(
                    *argv, env=self.spec.env, cwd=self.spec.cwd,
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True, **options,
                )
            finally:
                for fd in options.get('pass_fds', ()):
                    os.close(fd)  # the wrapper's end of the report pipe
            spawned = self.clock()
            # Freeze this generation's credentials. Old output cannot be scrubbed
            # against a replacement backend after restart/rotation.
            sensitive = tuple(value for key, value in self.spec.env.items()
                              if re.search(r"TOKEN|PASSWORD|PASSWD|SECRET|KEY|AUTH|COOKIE", key, re.I))
            readers = [asyncio.create_task(self.logs.collect(reader, stream, self.starts, sensitive))
                       for stream, reader in (("stdout", self.process.stdout), ("stderr", self.process.stderr))]
            self.status = "running"
            pid = getattr(self.process, 'pid', None)  # a test double may have none
            self._event('started', 'started', pid)
            if report is not None:
                fd, report = report, None
                await self._resources_applied(fd, pid)
            exited = asyncio.create_task(self.process.wait())
            stopped = asyncio.create_task(self._stop.wait())
            try:
                await asyncio.wait((exited, stopped), return_when=asyncio.FIRST_COMPLETED)
                if exited.done():
                    self.last_exit = exited.result()
            finally:
                for waiter in (exited, stopped):
                    waiter.cancel()
                await asyncio.gather(exited, stopped, return_exceptions=True)
            ran = self.clock() - spawned
            if not self._stop.is_set():
                self._event('exited', f'exited with code {self.last_exit}', pid)
        except OSError as error:
            self.last_exit = None
            self._event('spawn failed', f'could not be started ({type(error).__name__})')
        finally:
            if report is not None:
                os.close(report)
            self.ready = False
            if self.process is not None:
                try:
                    await self._terminate(self.process)
                    self.process = None
                finally:
                    # Pipes must drain during group cleanup. Only then join/cancel
                    # readers; inherited pipe descriptors cannot detach a task.
                    try:
                        async with asyncio.timeout(1):
                            await asyncio.gather(*readers)
                    except TimeoutError:
                        # Escaped descendants can keep pipes open after cleanup.
                        # Join the readers below, then resume the state machine.
                        pass
                    finally:
                        for reader in readers:
                            reader.cancel()
                        await asyncio.gather(*readers, return_exceptions=True)
        return ran

    async def _run(self):
        if self.delays is not None:
            return await self._watch(refused=False)
        try:
            for attempt in range(self.retries + 1):
                await self._attempt()
                if self._stop.is_set():
                    return
                if attempt < self.retries:
                    self.status = "backoff"
                    delay = min(30, self.backoff * 2 ** attempt) * random.uniform(1, 1.2)
                    try:
                        await asyncio.wait_for(self._stop.wait(), delay)
                        return
                    except TimeoutError:
                        pass
            self.status = "failed"
        except asyncio.CancelledError:
            raise

    async def _pause(self, delay):
        """Wait delay seconds, less when retry_now() is called; True when a stop was asked meanwhile."""
        self._kick.clear()
        waiters = (asyncio.ensure_future(self._stop.wait()), asyncio.ensure_future(self._kick.wait()))
        try:
            await asyncio.wait(waiters, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
        return self._stop.is_set()

    async def _watch(self, refused):
        """The watchdog (PaaS _schedule_auto_restart): after every failed attempt (an exit, a spawn failure, a refusal)
        the next delay of the table (the last one again once it is used up), the spawn check again, then a start; a run
        of stable_seconds or more starts the table again. max_attempts None: for ever."""
        attempts = 1 if refused else 0
        retry = refused
        while True:
            if retry:
                if self.max_attempts is not None and attempts >= self.max_attempts:
                    self.status, self.retry_in = 'failed', None
                    self._event('failed', f'failed after {attempts} starts; it starts again when saved or restarted')
                    return
                delay = self.delays[min(self.failures, len(self.delays) - 1)]
                self.failures += 1
                if self.status != 'blocked':
                    self.status = 'backoff'
                self.retry_in = delay
                self._event('backoff', f'next start in {delay:g} s (attempt {self.failures})')
                stopped = await self._pause(delay)
                self.retry_in = None
                if stopped:
                    return
                refusal = self._refusal()
                if refusal is not None:
                    self._block(refusal)
                    attempts += 1
                    continue
            attempts += 1
            self.blocked_reason = None
            ran = await self._attempt()
            if self._stop.is_set():
                return
            if ran is not None and ran >= self.stable_seconds:
                self.failures = 0
            retry = True

    async def _stop_child(self):
        try:
            if self.task is not None:
                # Cooperative stop cannot interrupt natural-exit group cleanup.
                self._stop.set()
                try:
                    await self.task
                finally:
                    self.task = None
            if self.process is not None:
                # A previous bounded cleanup failed. Retain the process handle
                # and retry cleanup before any replacement is allowed to start.
                await self._terminate(self.process)
                self.process = None
        except BaseException:
            self.ready = False
            self.status = "failed"
            raise
        self.ready = False
        self.status = "stopped"
        self.blocked_reason = self.retry_in = None

    async def stop(self):
        async with self._lock:
            # Keep the lock and join cleanup even on repeated caller cancellation.
            await _join_transition(self._stop_child())

    async def give_up(self):
        """HM-09 (DQ-21): stop the child and mark it failed; it starts again on a save or the panel's restart."""
        await self.stop()
        self.status = 'failed'

    async def restart(self, spec: ChildSpec | None):
        async def replace():
            await self._stop_child()
            self.spec = spec
            self._start_child()

        async with self._lock:
            # Stop + spec replacement + supervised start are one owned transition.
            await _join_transition(replace())

    def health(self):
        return {"state": self.status, "transport_ready": self.ready,
                "starts": self.starts, "last_exit": self.last_exit}

    def diagnostics(self):
        return {"child": self.health(), "logs": self.logs.snapshot()}
