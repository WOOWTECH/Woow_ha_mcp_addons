"""HM-08 test harness: one product's production runtime with its multi-profile switch on.

run_product.run serves the product exactly as tests/test_single_profile_golden.py's production_runtime serves it (the
real ProductStore, owner-defaults step, make_apps, HealthMonitor, ConfigurationState, child_spec and log redaction;
only the outside replaced), except that:

- features.MULTI_PROFILE_PRODUCTS names the product (monkeypatched for the test, whatever the repository switches on:
  Odoo from 0.5.0), so run_product builds a ProfileManager and 8081 is its token dispatcher
  (profile_router.McpDispatcher);
- additional profiles exist on disk (create_profile: ProductStore(create=profile_initial_state(...)) under
  /data/mcp/profiles/<id> and an entry in profiles.json, as HM-10 will make them);
- every profile's child sits behind its own port of one MockTransport (Children: the default profile's on 3000, an
  additional profile's on its index port), answering only that profile's child bearer; or, with real_children, the
  runtime's clients are real and reach loopback child servers (RealChild) on ephemeral ports the index names;
- the ProfileManager run_product made is kept (Runtime.manager), so a test reaches every profile's runtime; the
  additional profiles' children are started by the manager itself once the listeners serve (HM-09: monitor() runs
  start_all), and the harness waits until it is done (launch_extras). Unless a test asks for the planned 30 s
  (stagger), an additional child that does not answer its first health check frees its place at once
  (STAGGER_SECONDS 0.05): these tests start every profile as soon as they can, as the harness did before HM-09;
- HM-10: the management client (Runtime.admin) is the panel's: 8099 itself (the management dispatcher once switched
  on), every request naming its profile (X-MCP-Profile) as the panel does; verifier replaces the HA administrator
  check (the default: yes for the golden administrator, no for anyone else).

No socket is opened on 3000 or 18000-18099 (tests/owned_network.py): MockTransport opens none, and real children listen
on ephemeral ports.
"""
from __future__ import annotations

import asyncio
import collections
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import inspect
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from mcp_admin_core import features, profile_runtime, profiles, restore_detect, run_product
from mcp_admin_core.products import ProductStore, profile_initial_state
from test_profile_runtime import ProfileChild, connection_of
from test_single_profile_golden import (ADMIN, GENUINE_CLIENT, INGRESS, PROBE_ANSWERS, MockChild,
                                        NoProcessSupervisor, probe_name)

EXTRA_PORTS = range(18000, 18006)  # additional profiles' index ports behind MockTransport (never connected)
# Every product whose runtime is run_product and that has additional profiles (n8n: apps/n8n/run.py until HM-25;
# OpenDesign and Odoo Manage: none, DQ-28).
SWITCHABLE = ('odoo', 'hermes', 'emqx', 'litellm', 'nextcloud', 'headscale')


def ids(count):
    """Distinct additional profile ids in creation order (24 lowercase hex)."""
    assert count <= 6
    return [letter * 24 for letter in 'abcdef'[:count]]


def stored(directory):
    return json.loads((Path(directory) / 'state.json').read_text())


def all_tokens(data):
    """Every token and child token stored under data (the default profile's and every profile directory's)."""
    found = []
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        if path.exists():
            value = json.loads(path.read_text())
            found += [value['token'], value['child_token']]
    return [value for value in found if value]


def create_profile(data, product, profile_id, *, label, port, configured=True, indexed=True):
    """An additional profile on disk as HM-10 will create it: profiles/<id> born with profile_initial_state (new tokens
    that no other profile here has, the default profile's policy now, no connection), with its own synthetic backend
    when configured, and its entry appended to profiles.json (indexed=False: an orphan). Returns the profile's state.
    The runtime must not run: this opens the default profile's store.

    HM-13b: only a switched-on add-on makes profiles, and its first start made the instance sentinel and its record
    (restore detection, HM-13a). Before the first profile, this makes them too (established): profile data without a
    record reads as a restore, and the boot guard of the next start would revoke every token."""
    data = Path(data)
    layout = profiles.Layout(data)
    default = ProductStore(data, product)
    try:
        current = default.load()
    finally:
        default.close()
    if not profiles.has_profile_data(data):
        restore_detect.detect(data, enabled=True)
    profiles.ensure_profiles_directory(layout)
    state = profile_initial_state(current, taken=set(all_tokens(data)))
    ProductStore(layout.profile(profile_id), product, create=state).close()
    if configured:
        store = ProductStore(layout.profile(profile_id), product, existing_only=True)
        try:
            name = 'p' + profile_id[:4]
            state = store.update(**(connection_of(product, name) if product == 'n8n'
                                    else {'connection': connection_of(product, name)}))
        finally:
            store.close()
    if indexed:
        view = profiles.read_index(layout.index)
        profiles.write_index(layout.index, [*view.entries, profiles.IndexEntry(profile_id, label, port)],
                             expected=view)
    return state


def update_profile(data, product, profile_id, **changes):
    """Store.update on a profile before the runtime starts ('default': the default profile)."""
    directory = Path(data) if profile_id == 'default' else profiles.Layout(Path(data)).profile(profile_id)
    store = ProductStore(directory, product) if profile_id == 'default' else ProductStore(directory, product,
                                                                                       existing_only=True)
    try:
        return store.update(**changes)
    finally:
        store.close()


class Children:
    """Every profile's child behind its own port of one MockTransport (the gateway's, the health monitor's and the
    capability probe's requests alike); a port nobody listens on is a refused connection. A child is any callable
    taking the request (sync or async), e.g. test_profile_runtime.ProfileChild or the golden MockChild."""

    def __init__(self):
        self.by_port = {}

    def add(self, port, child):
        self.by_port[port] = child
        return child

    def profile_child(self, port, name, product, directory):
        return self.add(port, ProfileChild(name, product, directory))

    async def route(self, request):
        child = self.by_port.get(request.url.port) if request.url.host == '127.0.0.1' else None
        if child is None:
            raise httpx.ConnectError('nothing listens on this port', request=request)
        result = child(request)
        return await result if inspect.isawaitable(result) else result

    def requests(self):
        return sum(len(child.requests) for child in self.by_port.values())


@dataclass
class Runtime:
    product: str
    data: Path
    manager: object
    admin_app: object
    mcp_app: object
    mcp_port: int | None
    children: Children
    listeners: list = field(default_factory=list)
    task: object = None  # run_product.run's task (HM-30: a test that lets the runtime stop by itself reads it)

    def mcp(self, **kwargs):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.mcp_app), base_url='http://mcp', **kwargs)

    def admin(self, profile_id='default'):
        """The panel's client of one profile: 8099 (HM-10: switched on, the management dispatcher), every request with
        X-MCP-Profile: profile_id (switched off: none, as the panel of today; the default profile only)."""
        headers = {} if self.manager is None else {'X-MCP-Profile': profile_id}
        if self.manager is None and profile_id != 'default':
            raise AssertionError('a switched-off product serves the default profile only')
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.admin_app, client=INGRESS),
                              base_url='http://admin', headers=headers)

    def directory(self, profile_id):
        return self.data if profile_id == 'default' else profiles.Layout(self.data).profile(profile_id)

    def token(self, profile_id):
        return stored(self.directory(profile_id))['token']

    def gate(self, profile_id):
        return self.manager.get(profile_id).gate

    def limits(self):
        """limit_concurrency of each listener: {'admin': n, 'mcp': n}."""
        return {('mcp' if listener.config.app is self.mcp_app else 'admin'): listener.config.limit_concurrency
                for listener in self.listeners}


@asynccontextmanager
async def switched_on(*products):
    """features.MULTI_PROFILE_PRODUCTS for the test only (exactly *products*, whatever the repository switches on;
    features.enabled reads it at every call)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset(products))
        yield


# HM-09 review S-3: how long a switched-on add-on's shutdown (the manager's close: stop_all first) may take in a test,
# HA's stop limit (contract 7). A close that takes longer fails the test instead of holding the whole run.
CLOSE_SECONDS = 30


@asynccontextmanager
async def multi_profile_runtime(product, data, *, sockets=False, supervisor=None, real_children=False,
                                default_port=None, launch_extras=True, switch=True, children=None, resources=None,
                                stagger=None, verifier=None, may_stop=False):
    """run_product.run of *product* on *data* with the switch on (switch=False: every product off, whatever the
    repository switches on: HM-19a, tests/switch_modes.py), the outside replaced as production_runtime replaces it.
    children: a Children for MockTransport (left out: the default profile's golden MockChild on 3000, nobody else's);
    real_children: no MockTransport, the runtime's clients reach real loopback servers (default_port: the default
    profile's child port then). launch_extras: wait until the manager started every additional profile's child
    (start_all) once the listeners serve. resources: a stand-in for the resource module (the file limit). stagger:
    STAGGER_SECONDS for the test (left out: 0.05). verifier: the HA administrator check (HM-10; left out: administrator
    below). may_stop (HM-30): the runtime may end by itself while the test runs (the test reads Runtime.task);
    otherwise that fails the test."""
    if children is None:
        children = Children()
        children.add(3000, MockChild(product, data))
    listeners, made = [], []

    def child_client(*args, **kwargs):
        if not real_children:
            if kwargs.get('transport') is None or isinstance(kwargs['transport'], profile_runtime.ListenerGuard):
                kwargs['transport'] = httpx.MockTransport(children.route)
        return GENUINE_CLIENT(*args, **kwargs)

    class CapturedListener(run_product.Listener):
        def __init__(self, config):
            super().__init__(config)
            listeners.append(self)

        if not sockets:
            async def serve(self, sockets=None):
                self.started = True
                while not self.should_exit:
                    await asyncio.sleep(.01)

    class RecordedManager(profile_runtime.ProfileManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    with pytest.MonkeyPatch.context() as patch:
        # HM-19a: switch=False is every product off, not the repository's switch (Odoo is on from 0.5.0).
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({product}) if switch else frozenset())
        patch.setattr(profile_runtime, 'Supervisor', supervisor or NoProcessSupervisor)
        patch.setattr(profile_runtime.httpx, 'AsyncClient', child_client)
        patch.setattr(run_product, 'make_ha_admin_verifier', lambda: verifier or administrator)
        patch.setattr(run_product, 'Listener', CapturedListener)
        patch.setattr(run_product, 'ProfileManager', RecordedManager)
        if resources is not None:
            patch.setattr(profile_runtime, 'resource', resources)
        patch.setattr(profile_runtime, 'STAGGER_SECONDS', 0.05 if stagger is None else stagger)
        args = SimpleNamespace(data=Path(data), product=product, host='127.0.0.1',
                               admin_port=0 if sockets else 8099, mcp_port=0 if sockets else 8081)
        task = asyncio.create_task(run_product.run(args, **({} if default_port is None
                                                            else {'child_port': default_port})))
        try:
            async with asyncio.timeout(15):
                while not (len(listeners) == 2 and all(listener.started for listener in listeners)):
                    if task.done():
                        task.result()
                        raise AssertionError('runtime ended before its listeners started')
                    await asyncio.sleep(.01)
            manager = made[0] if made else None

            def is_mcp(listener):
                if manager is not None:
                    return listener.config.app is manager.mcp_app
                return any(getattr(route, 'path', None) == '/mcp' for route in listener.config.app.routes)
            mcp_listener, = [listener for listener in listeners if is_mcp(listener)]
            admin_listener, = [listener for listener in listeners if listener is not mcp_listener]
            port = mcp_listener.servers[0].sockets[0].getsockname()[1] if sockets else None
            if manager is not None and launch_extras:
                async with asyncio.timeout(15):
                    await manager.started.wait()
            yield Runtime(product, Path(data), manager, admin_listener.config.app, mcp_listener.config.app, port,
                          children, listeners, task)
        finally:
            task.cancel()
            async with asyncio.timeout(CLOSE_SECONDS):
                await asyncio.gather(task, return_exceptions=True)
        if not may_stop:
            assert task.cancelled(), 'the runtime stopped by itself while serving'


# ---- real loopback children (the quota tests' S5 and S6: every profile's own real httpx pool) ----

class RealChild:
    """A loopback MCP child on an ephemeral port: only its profile's child bearer is served (an HM-06 child's rule),
    any session id is accepted, initialize, ping and the product's readiness probe answer at once, every other tools/call
    waits while held (release() answers the waiting ones), a GET is an event stream that stays open while held. Counts
    the requests it answers at once (in_flight) and the most it ever had (peak)."""

    def __init__(self, directory, product):
        self.directory, self.product = Path(directory), product
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        assert self.sock.getsockname()[1] != 3000 and self.sock.getsockname()[1] not in range(18000, 18100)
        self.port = self.sock.getsockname()[1]
        self.held = False
        self.released = asyncio.Event()
        self.in_flight = self.peak = 0
        self.server = self.task = None

    def hold(self):
        self.held = True
        self.released = asyncio.Event()

    def release(self):
        self.held = False
        self.released.set()

    async def _answer(self, send, status, headers=(), body=b''):
        await send({'type': 'http.response.start', 'status': status, 'headers': list(headers)})
        await send({'type': 'http.response.body', 'body': body})

    async def app(self, scope, receive, send):
        if scope['type'] != 'http':
            return
        body = b''
        while True:
            message = await receive()
            body += message.get('body', b'')
            if not message.get('more_body'):
                break
        token = json.loads((self.directory / 'state.json').read_text())['child_token']
        if dict(scope['headers']).get(b'authorization') != ('Bearer ' + token).encode():
            return await self._answer(send, 401)
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            if scope['method'] == 'GET':
                await send({'type': 'http.response.start', 'status': 200,
                            'headers': [(b'content-type', b'text/event-stream')]})
                await send({'type': 'http.response.body', 'body': b': open\n\n', 'more_body': True})
                if self.held:
                    await self.released.wait()
                return await send({'type': 'http.response.body', 'body': b''})
            message = json.loads(body) if body else {}
            if scope['method'] == 'DELETE' or 'id' not in message:
                return await self._answer(send, 200 if scope['method'] == 'DELETE' else 202)
            method, headers = message.get('method'), [(b'content-type', b'application/json')]
            if method == 'initialize':
                result = {'protocolVersion': message['params']['protocolVersion'], 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'real-child', 'version': '0'}}
                headers.append((b'mcp-session-id', b'real-session'))
            elif method == 'ping':
                result = {}
            elif method == 'tools/call' and message['params']['name'] == probe_name(self.product):
                result = {'content': [{'type': 'text', 'text': json.dumps(PROBE_ANSWERS[self.product])}],
                          'isError': False}
            else:
                if self.held:
                    await self.released.wait()
                result = {'content': [{'type': 'text', 'text': 'real child result'}], 'isError': False}
            payload = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}).encode()
            await self._answer(send, 200, headers, payload)
        finally:
            self.in_flight -= 1

    async def start(self):
        self.server = uvicorn.Server(uvicorn.Config(self.app, interface='asgi3', lifespan='off', access_log=False,
                                                    log_level='warning', limit_concurrency=1000, timeout_keep_alive=30))
        self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
        async with asyncio.timeout(10):
            while not self.server.started:
                await asyncio.sleep(.01)

    async def stop(self):
        self.release()
        if self.server is not None:
            self.server.should_exit = True
            await asyncio.gather(self.task, return_exceptions=True)
        self.sock.close()


# The ports free_port handed out last (HM-09 recheck): two binds of port 0 in a row can draw the same port (5 times in
# 20,000 draws of three here), and two profiles of one rig on one port answer each other's checks: the default
# profile's readiness check reached another profile's mock child (401) and start_all waited its 30 s for the default.
HANDED_OUT = collections.deque(maxlen=256)


def free_port():
    """An ephemeral loopback port nobody listens on (never 3000 or 18000-18099), and none of the last ones it handed
    out, so the ports of one rig are distinct."""
    while True:
        port = _draw()
        if port != 3000 and port not in range(18000, 18100) and port not in HANDED_OUT:
            HANDED_OUT.append(port)
            return port


def _draw():
    """The port a bind of port 0 on 127.0.0.1 gets (the socket closed again)."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
