"""HM-09 follow-up: every product's health monitor stops when it is cancelled, also when the HTTP stack swallowed the
cancellation (PR #103's checks, 2026-11-16: HM-20's end-to-end test waited the rig's 30 s for an additional profile's
monitor, which went on checking twice a second after the rig's cancel). The owner decided on 2026-11-16 (13:4x) to fix
it for every product, switched on or off (contract 1.2): only the stop changes, no answer does.

How the stop was lost (anyio 4.15.1 and CPython 3.13 as pinned; httpx 0.28.1 and httpcore 1.0.9 reach the child through
anyio):

- Every new connection goes through anyio.connect_tcp, whose happy-eyeballs task group cancels its own cancel scope once
  connected (anyio/_core/_sockets.py: try_connect calls tg.cancel_scope.cancel()); that cancellation reaches the
  connecting task at once, its waiter cancelled with anyio's message.
- A task.cancel() that comes before the task runs again finds the waiter already cancelled: CPython's Task.cancel()
  then only marks the task, which gets the CancelledError it already had, anyio's.
- The scope's exit swallows a CancelledError that carries its message (anyio/_backends/_asyncio.py CancelScope.__exit__
  looks at the message, not at Task.cancelling()): connect_tcp returns, the check goes on and so does the monitor's
  loop. Task.cancelling() still counts the request.
- httpcore's read deadline (anyio.fail_after) is the same: a stop right after it ends the check in a read timeout.

In the CI log every request of the real children's health checks opened a new connection (their event-stream answers
are closed unread after the JSON-RPC result), five windows per check. HealthMonitor.check() now raises CancelledError
when the task's cancelling() is higher at its end than at its start: every monitor's loop (switched off: a check, then
15 s), start_all's readiness wait and whoever waits for them (_stop_monitors, remove(), run_product's shutdown) end as
asked.

These tests make the race certain: a loopback child whose every answer closes its connection (each request connects
anew, as in the CI log) and a hook on anyio's backend connect that cancels the task in the next loop step, after
anyio's own cancellation reached it and before the task ran again (the CI timing). The add-on tests also hold the
production stop of one monitor back until its next connection (held_stop).
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

from anyio._backends import _asyncio as anyio_backend
import httpx
import pytest

from lifecycle_runtime import until
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import features, health, profile_runtime, run_product
from mcp_admin_core.config import Store
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import TOOLS, ProductStore, child_spec
from multi_profile_runtime import CLOSE_SECONDS, all_tokens, create_profile, ids, multi_profile_runtime
from test_health_backoff import Process, switched_on
from test_profile_runtime import product_options
from test_single_profile_golden import ADMIN, PROBE_ANSWERS, NoProcessSupervisor, configure

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B = ids(1)[0]
LABEL = 'Cancel Beta'
CONNECTIONS = ('initialize', 'initialized', 'ping', 'the readiness probe', 'DELETE')  # one check, one connection each


class ClosingChild:
    """A loopback MCP child on an ephemeral port: initialize (a session), notifications/initialized, ping, the product's
    readiness probe (its success shape) and DELETE, each answered at once and every answer closing its connection.
    requests: (time.monotonic(), HTTP method, JSON-RPC method) of each request read. hang: requests are read but get
    no answer until the child stops."""

    def __init__(self, product='n8n'):
        self.product = product
        self.requests = []
        self.hang = False
        self.released = asyncio.Event()
        self.server = self.port = None

    async def _serve(self, reader, writer):
        try:
            head = await reader.readuntil(b'\r\n\r\n')
            lines = head.decode('latin-1').split('\r\n')
            method = lines[0].split(' ', 1)[0]
            length = next((int(line.split(':', 1)[1]) for line in lines[1:]
                           if line.lower().startswith('content-length:')), 0)
            message = json.loads(await reader.readexactly(length)) if length else {}
            self.requests.append((time.monotonic(), method, message.get('method')))
            if self.hang:
                await self.released.wait()
                return
            status, extra, body = '200 OK', '', b''
            if method == 'POST' and 'id' not in message:
                status = '202 Accepted'
            elif method == 'POST':
                if message['method'] == 'initialize':
                    result = {'protocolVersion': message['params']['protocolVersion'],
                              'serverInfo': {'name': 'closing-child', 'version': '0'}}
                    extra = 'mcp-session-id: closing-child\r\n'
                elif message['method'] == 'ping':
                    result = {}
                else:
                    result = {'content': [{'type': 'text', 'text': json.dumps(PROBE_ANSWERS[self.product])}]}
                body = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}).encode()
            writer.write((f'HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {len(body)}\r\n'
                          f'connection: close\r\n{extra}\r\n').encode() + body)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def start(self):
        self.server = await asyncio.start_server(self._serve, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        assert self.port != 3000 and self.port not in range(18000, 18100)
        return self

    async def stop(self):
        self.released.set()
        self.server.close()

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *exc_info):
        await self.stop()


def cancel_in_anyio_s_window(monkeypatch, victim, *, port=None, nth=1):
    """Cancel the task victim() names (None: none yet) right after the nth connection anyio makes from then on (to port;
    any port when None): in the next loop step, when anyio's try_connect has cancelled its task group's scope (anyio's
    CancelledError is on its way to the task) and the task has not run again. Returns what happened: at
    (time.monotonic() of the cancel) and anyio_first (the task's waiter was already cancelled by anyio)."""
    original = anyio_backend.AsyncIOBackend.connect_tcp
    seen, made = {}, [0]

    async def connect_tcp(cls, host, remote_port, local_address=None):
        stream = await original(host, remote_port, local_address)
        task = victim()
        if task is not None and 'at' not in seen and port in (None, remote_port):
            made[0] += 1
            if made[0] == nth:
                def cancel():
                    waiter = task._fut_waiter  # what the task waits for: anyio's event, cancelled by anyio by now
                    seen.update(at=time.monotonic(), anyio_first=waiter is not None and waiter.cancelled())
                    asyncio.Task.cancel(task)
                asyncio.get_running_loop().call_soon(cancel)
        return stream
    monkeypatch.setattr(anyio_backend.AsyncIOBackend, 'connect_tcp', classmethod(connect_tcp))
    return seen


def monitored(tmp_path, child, *, timeout=None, **options):
    """A monitor on a real child client (as ProfileRuntime makes it) that reaches child; n8n's state."""
    store = Store(tmp_path / 'state')
    store.update(backend_url='https://backend.invalid', backend_key='DUMMY-cancel-key')
    client = httpx.AsyncClient(trust_env=False, follow_redirects=False,
                               timeout=timeout or httpx.Timeout(10, connect=3))
    monitor = HealthMonitor(store, Process(), client, child_url=f'http://127.0.0.1:{child.port}/mcp', **options)
    return store, client, monitor


async def administrator(user):
    return user == ADMIN['X-Remote-User-Id']


async def ended(task, seconds=1.0):
    """Wait up to seconds for task; a task still running then is cancelled again (outside any window) and waited for,
    so that a failed test leaves nothing behind."""
    await asyncio.wait({task}, timeout=seconds)
    running = not task.done()
    if running:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return not running


# ---- the monitor ----

@pytest.mark.parametrize('profile, connection', [('additional', n) for n in range(1, 6)] + [('default', 1)])
async def test_a_stop_anyio_s_connect_swallowed_still_ends_the_monitor(tmp_path, log_scan, monkeypatch, profile,
                                                                     connection):
    """The monitor's run() (an additional profile's start point, or the default profile's: at once), cancelled in
    anyio's window of the nth connection of its first check (CONNECTIONS): the rest of that check goes on (the stop was
    swallowed), then the monitor ends as cancelled. Before the fix it went on to its next check."""
    async with ClosingChild() as child:
        store, client, monitor = monitored(tmp_path, child, first_check_after=0.01 if profile == 'additional' else 0,
                                           **switched_on())
        log_scan.watch_state(store.load())
        box = {}
        seen = cancel_in_anyio_s_window(monkeypatch, lambda: box.get('task'), nth=connection)
        try:
            box['task'] = task = asyncio.create_task(monitor.run())
            await until(lambda: 'at' in seen, timeout=5)
            stopped = await ended(task)
            assert seen['anyio_first'], "the stop did not come in anyio's window"
            went_on = [request for request in child.requests if request[0] > seen['at']]
            assert len(went_on) == len(CONNECTIONS) - connection + 1, went_on  # the check went on: swallowed
            assert stopped and task.cancelled(), f'the monitor went on after a stop at its {CONNECTIONS[connection - 1]}'
        finally:
            await client.aclose()
            store.close()


async def test_a_stop_after_anyio_s_read_deadline_still_ends_the_monitor(tmp_path, log_scan, monkeypatch):
    """The other way anyio cancels its own scope on the way to the child: httpcore's read deadline (anyio.fail_after;
    the child client's 10 s, here 0.2 s, the child not answering). A stop right after the deadline fired joins anyio's
    CancelledError too: the check ends in a read timeout (recorded as a check the child did not answer), then the
    monitor ends as cancelled. Before the fix it went on."""
    original = anyio_backend.CancelScope.cancel
    box, seen = {}, {}

    def cancel(scope, reason=None):
        original(scope, reason)
        task = box.get('task')
        if task is not None and reason == 'deadline exceeded' and scope._host_task is task and 'at' not in seen:
            waiter = task._fut_waiter
            seen.update(at=time.monotonic(), anyio_first=waiter is not None and waiter.cancelled())
            task.cancel()
    async with ClosingChild() as child:
        child.hang = True
        store, client, monitor = monitored(tmp_path, child, timeout=httpx.Timeout(0.2, connect=3),
                                           first_check_after=0.01, **switched_on())
        log_scan.watch_state(store.load())
        monkeypatch.setattr(anyio_backend.CancelScope, 'cancel', cancel)
        try:
            box['task'] = task = asyncio.create_task(monitor.run())
            await until(lambda: 'at' in seen, timeout=5)
            stopped = await ended(task)
            assert seen['anyio_first'], "the stop did not come in anyio's window"
            assert stopped and task.cancelled(), 'the monitor went on after a stop at its read deadline'
            assert monitor.settled[1] is False  # the check itself ended: the child did not answer
        finally:
            await client.aclose()
            store.close()


async def test_start_all_s_readiness_wait_ends_when_anyio_swallowed_its_stop(tmp_path, log_scan, monkeypatch):
    """ProfileManager._started waits for a starting child with HealthMonitor.settle(): a check of its own when none
    runs. Stopped in anyio's window (start_all is cancelled when the manager's monitoring ends), it ends as cancelled;
    before the fix it returned as if nothing had happened, and start_all went on starting the next profiles."""
    async with ClosingChild() as child:
        store, client, monitor = monitored(tmp_path, child, first_check_after=0.01, **switched_on())
        log_scan.watch_state(store.load())
        box = {}
        seen = cancel_in_anyio_s_window(monkeypatch, lambda: box.get('task'))
        try:
            box['task'] = task = asyncio.create_task(monitor.settle())
            await until(lambda: 'at' in seen, timeout=5)
            stopped = await ended(task)
            assert seen['anyio_first'], "the stop did not come in anyio's window"
            assert stopped and task.cancelled(), 'the readiness wait returned after its stop'
            assert monitor.availability()['ready'] is True  # the check itself was done
        finally:
            await client.aclose()
            store.close()


async def test_a_switched_off_profile_s_monitor_ends_when_anyio_swallowed_its_stop(tmp_path, log_scan, monkeypatch):
    """Switched off (the owner's decision of 2026-11-16 13:4x: every product): the one profile's runtime as run_product
    builds it (ProfileRuntime without monitor options: a check at once, then every 15 s), its monitor run as
    run_product runs it and cancelled in anyio's window of its first connection: that check goes on (the stop was
    swallowed), then the monitor ends as cancelled. Before the fix it went on to its next check, 15 s later, and so
    on: run_product's shutdown waited for it."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with ClosingChild(PRODUCT) as child:
        store = ProductStore(data, PRODUCT)
        log_scan.watch_state(store.load())
        runtime = profile_runtime.ProfileRuntime(store, TOOLS[PRODUCT], child_spec, port=child.port,
                                                 app_options={**product_options(PRODUCT), 'verify_admin': administrator})
        box = {}
        seen = cancel_in_anyio_s_window(monkeypatch, lambda: box.get('task'))
        try:
            await runtime.open()
            assert not runtime.health.paced  # switched off: the monitor of before HM-09
            box['task'] = task = asyncio.create_task(runtime.monitor())
            await until(lambda: 'at' in seen, timeout=5)
            stopped = await ended(task)
            assert seen['anyio_first'], "the stop did not come in anyio's window"
            went_on = [request for request in child.requests if request[0] > seen['at']]
            assert len(went_on) == len(CONNECTIONS), went_on  # the whole check went on: swallowed
            assert stopped and task.cancelled(), "the switched-off profile's monitor went on after its stop"
        finally:
            await runtime.aclose()
            store.close()


# ---- the add-on's stop (run_product.run, real child clients) ----

@contextmanager
def held_stop(coroutine, stopper):
    """The first cancel() that stopper (the function that stops the task in production) makes of a task running
    coroutine (a __qualname__) is held back: the task goes on as if that stop had not come yet, and held['task'] names
    it. Deliver it with cancel_in_anyio_s_window(victim=lambda: held.get('task')). The loop's task factory makes such
    tasks while this runs."""
    held, code = {}, stopper.__code__

    class Held(asyncio.Task):
        def cancel(self, msg=None):
            if 'task' not in held and sys._getframe(1).f_code is code:
                held['task'] = self
                return True
            return super().cancel(msg)

    loop = asyncio.get_running_loop()
    previous = loop.get_task_factory()

    def factory(loop, coro, **kwargs):
        if getattr(coro, '__qualname__', None) == coroutine:
            return Held(coro, loop=loop, **kwargs)
        if previous is not None:
            return previous(loop, coro, **kwargs)
        return asyncio.Task(coro, loop=loop, **kwargs)
    loop.set_task_factory(factory)
    try:
        yield held
    finally:
        loop.set_task_factory(previous)


@asynccontextmanager
async def two_profiles(tmp_path, log_scan, monkeypatch):
    """The default profile and B configured, each child a ClosingChild on its port; checks every 0.05 s."""
    monkeypatch.setattr(health, 'HEALTH_INTERVAL', 0.05)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with ClosingChild(PRODUCT) as default, ClosingChild(PRODUCT) as extra:
        create_profile(data, PRODUCT, B, label=LABEL, port=extra.port)
        log_scan.watch(*all_tokens(data))
        log_scan.watch(LABEL, kind='name')
        yield data, default, extra


def serving(manager):
    """Every profile's child answered a health check and B's monitor runs."""
    return (manager is not None and manager.started.is_set() and B in manager._monitors
            and all(entry.runtime.health.availability()['ready'] for entry in manager.profiles()))


async def test_the_rig_s_close_is_not_held_by_a_monitor_whose_stop_anyio_swallowed(tmp_path, log_scan, monkeypatch):
    """PR #103's failure, made certain: run_product.run switched on (multi_profile_runtime with real child clients) is
    cancelled as the rig cancels it; the manager's _stop_monitors cancels B's monitor, and that cancel reaches B in
    anyio's window of B's next connection. Before the fix B's monitor went on and the close ran into the rig's 30 s
    (TimeoutError, the CI failure); now B's monitor ends after that check and the close takes moments."""
    async with two_profiles(tmp_path, log_scan, monkeypatch) as (data, default, extra):
        loop = asyncio.get_running_loop()
        with held_stop('ProfileManager._watched', profile_runtime.ProfileManager._stop_monitors) as held:
            seen = cancel_in_anyio_s_window(monkeypatch, lambda: held.get('task'), port=extra.port)
            async with multi_profile_runtime(PRODUCT, data, real_children=True, default_port=default.port) as runtime:
                await until(lambda: serving(runtime.manager), timeout=15)
                watched = runtime.manager._monitors[B]
                began = loop.time()
            took = loop.time() - began
    assert held.get('task') is watched and seen['anyio_first'], "B's stop did not come in anyio's window"
    assert watched.cancelled()
    assert took < 5, took


@asynccontextmanager
async def run_until_sigterm(data, default_port, *, switch=True):
    """run_product.run of PRODUCT, switched on (switch=False: every product off, as multi_profile_runtime's; HM-19a),
    served as multi_profile_runtime serves it with real
    child clients (no listener sockets, no child process: NoProcessSupervisor), but stopped as HA stops an add-on:
    SIGTERM. Yields the run task and what run_product built (switched on its ProfileManager, off its ProfileRuntime)
    once every profile serves."""
    listeners, made = [], []

    class Listener(run_product.Listener):
        def __init__(self, config):
            super().__init__(config)
            listeners.append(self)

        async def serve(self, sockets=None):
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(.01)

    class Manager(profile_runtime.ProfileManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    class Runtime(profile_runtime.ProfileRuntime):  # what run_product builds switched off
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    def serves(built):
        if isinstance(built, profile_runtime.ProfileManager):
            return serving(built)
        return built.health is not None and built.health.availability()['ready']

    with pytest.MonkeyPatch.context() as patch:
        # HM-19a: switch=False is every product off, not the repository's switch (PRODUCT is Odoo, on from 0.5.0).
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}) if switch else frozenset())
        patch.setattr(profile_runtime, 'Supervisor', NoProcessSupervisor)
        patch.setattr(profile_runtime, 'STAGGER_SECONDS', 0.05)
        patch.setattr(run_product, 'make_ha_admin_verifier', lambda: administrator)
        patch.setattr(run_product, 'Listener', Listener)
        patch.setattr(run_product, 'ProfileManager', Manager)
        patch.setattr(run_product, 'ProfileRuntime', Runtime)
        args = SimpleNamespace(data=Path(data), product=PRODUCT, host='127.0.0.1', admin_port=8099, mcp_port=8081)
        task = asyncio.create_task(run_product.run(args, child_port=default_port))
        try:
            await until(lambda: task.done() or (len(listeners) == 2 and all(item.started for item in listeners)
                                                and bool(made) and serves(made[0])), timeout=15)
            assert not task.done(), 'the runtime ended before it served'
            yield task, made[0]
        finally:
            if not task.done():
                task.cancel()
                await asyncio.wait({task}, timeout=CLOSE_SECONDS)


def sigterm():
    """SIGTERM to this process, as HA's stop sends it to the add-on; only while run_product.run's handler is installed
    (the default action would end the test run)."""
    assert signal.getsignal(signal.SIGTERM) not in (signal.SIG_DFL, signal.SIG_IGN, None)
    os.kill(os.getpid(), signal.SIGTERM)


@pytest.mark.parametrize('swallowed', ['additional', 'default'])
async def test_sigterm_stops_a_switched_on_add_on_within_haos_limit_when_anyio_swallowed_a_monitor_s_stop(
        tmp_path, log_scan, monkeypatch, swallowed):
    """HA stops an add-on with SIGTERM and allows it 30 s (contract 7): run_product.run (switched on) cancels its
    monitoring, the default profile's monitor (run_product's monitor.cancel()), whose end cancels B's monitor
    (_stop_monitors), and then closes every profile. The stop of one of the two monitors (swallowed) reaches it in
    anyio's window of its next connection. run_product.run returns within HA's 30 s all the same, in moments; before
    the fix it never returned."""
    stopper, coroutine = ((profile_runtime.ProfileManager._stop_monitors, 'ProfileManager._watched')
                          if swallowed == 'additional' else (run_product.run, 'ProfileManager._monitor'))
    async with two_profiles(tmp_path, log_scan, monkeypatch) as (data, default, extra):
        loop = asyncio.get_running_loop()
        with held_stop(coroutine, stopper) as held:
            port = extra.port if swallowed == 'additional' else default.port
            seen = cancel_in_anyio_s_window(monkeypatch, lambda: held.get('task'), port=port)
            async with run_until_sigterm(data, default.port) as (task, manager):
                watched = manager._monitors[B]
                began = loop.time()
                sigterm()
                await asyncio.wait({task}, timeout=CLOSE_SECONDS)
                took = loop.time() - began
                assert task.done(), f'run_product.run did not stop within {CLOSE_SECONDS} s of SIGTERM'
                assert not task.cancelled() and task.exception() is None
    assert seen['anyio_first'], f"the {swallowed} profile's stop did not come in anyio's window"
    assert held['task'].cancelled() and watched.cancelled()
    assert took < 5, took


def shorter_switched_off_interval(monkeypatch, seconds=0.05):
    """The switched-off monitor sleeps 15 s between checks (health.py: asyncio.sleep(15)); seconds here, in health.py
    only (its asyncio name is a copy of the module whose sleep shortens that one wait)."""
    copy = SimpleNamespace(**vars(asyncio))
    copy.sleep = lambda delay, *args, **kwargs: asyncio.sleep(seconds if delay == 15 else delay, *args, **kwargs)
    monkeypatch.setattr(health, 'asyncio', copy)


async def test_sigterm_stops_a_switched_off_add_on_within_haos_limit_when_anyio_swallowed_its_monitor_s_stop(
        tmp_path, log_scan, monkeypatch):
    """The same stop of a product not switched on (every product today): run_product.run builds the one profile's
    ProfileRuntime; on SIGTERM it cancels the monitor (monitor.cancel()), and that stop reaches the monitor in anyio's
    window of its next check's first connection (the 15 s between checks shortened). run_product.run returns within
    HA's 30 s, in moments; before the fix it never returned."""
    shorter_switched_off_interval(monkeypatch)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with ClosingChild(PRODUCT) as child:
        log_scan.watch(*all_tokens(data))
        loop = asyncio.get_running_loop()
        with held_stop('HealthMonitor.run', run_product.run) as held:
            seen = cancel_in_anyio_s_window(monkeypatch, lambda: held.get('task'), port=child.port)
            async with run_until_sigterm(data, child.port, switch=False) as (task, runtime):
                assert isinstance(runtime, profile_runtime.ProfileRuntime) and not runtime.health.paced
                began = loop.time()
                sigterm()
                await asyncio.wait({task}, timeout=CLOSE_SECONDS)
                took = loop.time() - began
                assert task.done(), f'run_product.run did not stop within {CLOSE_SECONDS} s of SIGTERM'
                assert not task.cancelled() and task.exception() is None
    assert seen['anyio_first'], "the monitor's stop did not come in anyio's window"
    assert held['task'].cancelled()
    assert took < 5, took
