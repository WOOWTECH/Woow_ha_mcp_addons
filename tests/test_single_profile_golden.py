"""HM-01 golden regression: the default (single) profile of all eight products, as bb48449 serves it.

The production runtime runs (run_product.run, apps/n8n/run.py run): the real ProductStore, the owner-defaults startup
step, make_apps, HealthMonitor, ConfigurationState, child_spec and log redaction. Only the outside is replaced:

- the two listeners open no socket here; their ASGI apps are driven in process (tests/test_mcp_contract_freeze.py
  serves the same runtime on real loopback listeners);
- the Supervisor starts no process: a configured child is "running" at once (status, starts and readiness as the
  real one reports them);
- the child's HTTP is MockChild, a stateful MCP server that only answers the gateway's own child bearer and answers
  with headers of its own that the gateway must not relay;
- the HA administrator check answers yes for the golden administrator (ADMIN), no for anyone else (n8n: the node
  catalog copy is skipped).

These are the only injection points, all in production_runtime (module = run_product, or apps/n8n/run.py for n8n):
module.Supervisor (NoProcessSupervisor, or the subclass a test passes), module.httpx.AsyncClient (every client built
while the runtime runs gets MockTransport(MockChild) unless it names a transport; the tests' own clients are
GENUINE_CLIENT), module.make_ha_admin_verifier, module.Listener (CapturedListener) and, for n8n, module.prepare_catalog.
tests/test_admin_contract_freeze.py also replaces HealthMonitor.test_saved for one answer shape. HM-05 (the per-profile
runtime extraction) may move these lines when the names they patch move, and nothing else here.

Two states per product: "fresh" (a new installation, no backend) and "configured" (a backend saved, the child up and
its readiness check passed). Fixed values below were read in gateway.py, access.py, config.py, health.py and
configuration.py at bb48449 and confirmed by running them. The multi-profile slices (HM-04 to HM-30) must keep them,
byte for byte, for the default profile: both connection paths, the error answers (wrong token 401/404, query 400,
/mcp/ 404), /health/ready, the bootstrap fields, what the child gets (only the gateway's own headers: CHILD_HEADERS)
and what comes back from it (no child header beyond the four the gateway relays), and a state.json that start, reads
and listings never write (bytes, inode, mtime, mode, owner, links: stat_signature) in a data directory whose entries
and modes stay as they were.

tools/list is fixed by two digests per product: LISTING_SHA256, the packaged listing the gateway rewrites
(surface.listing: tool_snapshot.py, regenerated whenever a product's tool surface changes), and LISTED_SHA256, the
gateway's whole answer. When the listing changed the change is a deliberate tool-surface change: check the new answer
and update both digests of that product together. When the listing is unchanged and the answer changed, the gateway's
own rewrite changed (policy.filter_list, listed_tool, odoo_switch_listing, the product's tool registry): a regression
unless that change is deliberate.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from types import SimpleNamespace

import httpx
import pytest

import run as n8n_run
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import VERSION, run_product, version_for_product
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import INSTRUCTIONS, PROBES, ProductStore, health_probe
from mcp_admin_core.surface import listing

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ('odoo', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud', 'headscale')
MODES = ('fresh', 'configured')
PROTOCOL = '2025-06-18'
ACCEPT = {'Accept': 'application/json, text/event-stream'}
ADMIN = {'X-Remote-User-Id': 'golden-admin'}
INGRESS = ('172.30.32.2', 1)

# Synthetic backends (tests/fixtures/owner_defaults/README.md rules: DUMMY- credentials, .invalid hosts).
CONNECTIONS = {
    'odoo': {'url': 'https://odoo.invalid', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
             'password': 'DUMMY-golden-odoo-password'},
    'hermes': {'gateway_url': 'https://hermes.invalid', 'gateway_api_key': 'DUMMY-golden-hermes-key'},
    'opendesign': {'url': 'https://opendesign.invalid'},
    'emqx': {'url': 'https://emqx.invalid', 'api_key': 'DUMMY-golden-emqx-key',
             'api_secret': 'DUMMY-golden-emqx-secret'},
    'litellm': {'url': 'https://litellm.invalid', 'master_key': 'DUMMY-golden-litellm-key'},
    'nextcloud': {'url': 'https://nextcloud.invalid', 'username': 'DUMMY-user',
                  'app_password': 'DUMMY-golden-nextcloud-password'},
    'headscale': {'url': 'https://headscale.invalid', 'api_key': 'DUMMY-golden-headscale-key'},
}
N8N_BACKEND = {'backend_url': 'https://n8n.invalid', 'backend_key': 'DUMMY-golden-workflow-key'}
# The readiness probe's success shape per product (products.health_probe_success, probe_success; n8n: health.py).
PROBE_ANSWERS = {
    'odoo': {'uid': 2},
    'n8n': {'success': True, 'data': []},
    'hermes': {'capabilities': {}},
    'opendesign': {'ok': True, 'version': '0.21.1'},
    'emqx': {'node_count': 1, 'nodes': [{'node': 'emqx@golden.invalid', 'version': '5.8.0'}]},
    'litellm': {'data': []},
    'nextcloud': {'ok': True, 'user_id': 'DUMMY-user'},
    'headscale': {'databaseConnectivity': True},
}
TOOL_TEXT = 'golden tool result'
CHECKS = ('local-readiness', 'management-catalog')  # HealthMonitor's and the capabilities catalog's own sessions
# Headers MockChild adds to its answers. The gateway relays four (gateway.FORWARDED_HEADERS: mcp-session-id,
# mcp-protocol-version, retry-after, content-type), so a client never sees these. Not Set-Cookie: the gateway's child
# client would keep the cookie and send it back to the child.
CHILD_EXTRA = {'Location': 'https://child.invalid/elsewhere', 'WWW-Authenticate': 'Bearer', 'X-Child-Extra': '1'}
# The only headers the child gets (plan 8.8 #4, FM-29): the gateway's own client headers, its child bearer and the
# three session headers it forwards; never the client's Origin, Cookie, X-MCP-Profile or any other header.
CHILD_HEADERS = frozenset({'host', 'accept', 'accept-encoding', 'connection', 'user-agent', 'content-length',
                           'content-type', 'authorization', 'mcp-session-id', 'mcp-protocol-version', 'last-event-id'})


def probe_name(product):
    return 'n8n_list_workflows' if product == 'n8n' else health_probe(product)[0]


def public_read(product):
    """A public read tool that needs the backend, and its arguments."""
    return ('n8n_list_workflows', {'limit': 1}) if product == 'n8n' else PROBES[product]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stat_signature(path):
    """What any write alters besides the bytes (invariant I6: the default state is never written): a rewrite of the same
    bytes (mtime), a replace (inode), a mode, owner or link change."""
    info = os.stat(path)
    return {'sha256': sha256(path), 'ino': info.st_ino, 'mtime_ns': info.st_mtime_ns, 'mode': info.st_mode,
            'uid': info.st_uid, 'nlink': info.st_nlink}


def entries(directory):
    return sorted(str(path.relative_to(directory)) for path in Path(directory).rglob('*'))


def modes(directory):
    """Every entry of a directory tree with its mode (file type and permission bits)."""
    return {str(path.relative_to(directory)): path.lstat().st_mode for path in Path(directory).rglob('*')}


def stored(data):
    return json.loads((Path(data) / 'state.json').read_text())


def secrets_of(product):
    values = N8N_BACKEND if product == 'n8n' else CONNECTIONS[product]
    return [value for value in values.values() if value.startswith('DUMMY-golden')]


def configure(data, product):
    """A saved backend, as the panel saves it (Store.update), before the runtime starts."""
    store = ProductStore(data, product)
    try:
        if product == 'n8n':
            store.update(**N8N_BACKEND)
        else:
            store.update(connection=CONNECTIONS[product])
    finally:
        store.close()


class MockChild:
    """The child as the gateway reaches it: only the state's child bearer is answered (an HM-06 child's rule), every
    request is recorded. initialize opens a session; the readiness probe gets the product's success shape; tools/list
    the packaged listing; any other tools/call a fixed text. Every answer it gives also carries CHILD_EXTRA."""

    def __init__(self, product, data):
        self.product, self.state = product, Path(data) / 'state.json'
        self.requests = []
        self.sessions = {}  # session id -> the clientInfo name of its initialize

    def __call__(self, request):
        self.requests.append(request)
        if (request.headers.get_list('authorization') != ['Bearer ' + json.loads(self.state.read_text())['child_token']]
                or request.url.path != '/mcp'):
            return httpx.Response(401)
        if request.method == 'DELETE':
            return httpx.Response(200, headers=CHILD_EXTRA)
        message = json.loads(request.content)
        if 'id' not in message:
            return httpx.Response(202, headers=CHILD_EXTRA)
        method = message['method']
        if method == 'initialize':
            session = f'golden-child-{len(self.sessions) + 1}'
            self.sessions[session] = message['params']['clientInfo']['name']
            return httpx.Response(200, headers={**CHILD_EXTRA, 'mcp-session-id': session}, json={
                'jsonrpc': '2.0', 'id': message['id'], 'result': {
                    'protocolVersion': message['params']['protocolVersion'], 'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'mock-child', 'version': '0'}}})
        if method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': listing(self.product)}
        elif method == 'tools/call':
            name = message['params']['name']
            text = json.dumps(PROBE_ANSWERS[self.product]) if name == probe_name(self.product) else TOOL_TEXT
            result = {'content': [{'type': 'text', 'text': text}], 'isError': False}
        else:
            return httpx.Response(400)
        return httpx.Response(200, headers=CHILD_EXTRA, json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})

    def forwarded(self, since=0):
        """(HTTP method, JSON-RPC method or None) of the requests after index since that the gateway relayed for a
        client: the readiness check's and the capabilities catalog's own sessions are left out."""
        seen = []
        for request in self.requests[since:]:
            message = json.loads(request.content) if request.content else {}
            if message.get('method') == 'initialize':
                client = ((message.get('params') or {}).get('clientInfo') or {}).get('name')
            else:
                client = self.sessions.get(request.headers.get('mcp-session-id'))
            if client not in CHECKS:
                seen.append((request.method, message.get('method')))
        return seen


class NoProcessSupervisor(Supervisor):
    """The real Supervisor's state and reports, without a process: a configured spec is running at once."""

    def _start_child(self):
        if self.spec is None:
            self.status = 'unconfigured'
            return
        self.starts += 1
        self.status = 'running'

    async def _stop_child(self):
        self.ready = False
        self.status = 'stopped'


GENUINE_CLIENT = httpx.AsyncClient  # the runtime's own child client is replaced; the test's clients are not


@dataclass
class Runtime:
    product: str
    data: Path
    child: MockChild
    admin_app: object
    mcp_app: object
    mcp_port: int | None

    def mcp(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.mcp_app), base_url='http://mcp')

    def admin(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.admin_app, client=INGRESS),
                              base_url='http://admin')


@asynccontextmanager
async def production_runtime(product, data, *, sockets=False, supervisor=None):
    """run() of the product's own runtime module with only the outside replaced (see the module docstring); the
    replacements are undone when the runtime stops.

    sockets=True keeps the real listeners (uvicorn, h11) on ephemeral loopback ports; mcp_port is the MCP one.
    supervisor: a NoProcessSupervisor subclass to use instead (tests/test_admin_contract_freeze.py: a failing start)."""
    module = n8n_run if product == 'n8n' else run_product
    child = MockChild(product, data)
    listeners = []

    def child_client(*args, **kwargs):
        kwargs.setdefault('transport', httpx.MockTransport(child))
        return GENUINE_CLIENT(*args, **kwargs)

    class CapturedListener(module.Listener):
        def __init__(self, config):
            super().__init__(config)
            listeners.append(self)

        if not sockets:
            async def serve(self, sockets=None):
                self.started = True
                while not self.should_exit:
                    await asyncio.sleep(.01)

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, 'Supervisor', supervisor or NoProcessSupervisor)
        patch.setattr(module.httpx, 'AsyncClient', child_client)
        patch.setattr(module, 'make_ha_admin_verifier', lambda: administrator)
        patch.setattr(module, 'Listener', CapturedListener)
        if product == 'n8n':
            patch.setattr(module, 'prepare_catalog', lambda: None)  # a 70 MB copy outside /data, not under test
        args = SimpleNamespace(data=Path(data), product=product, host='127.0.0.1',
                               admin_port=0 if sockets else 8099, mcp_port=0 if sockets else 8081)
        task = asyncio.create_task(module.run(args))
        try:
            async with asyncio.timeout(15):
                while not (len(listeners) == 2 and all(listener.started for listener in listeners)):
                    if task.done():
                        task.result()
                        raise AssertionError('runtime ended before its listeners started')
                    await asyncio.sleep(.01)
            mcp_listener, = [listener for listener in listeners
                             if any(getattr(route, 'path', None) == '/mcp' for route in listener.config.app.routes)]
            admin_listener, = [listener for listener in listeners if listener is not mcp_listener]
            port = mcp_listener.servers[0].sockets[0].getsockname()[1] if sockets else None
            yield Runtime(product, Path(data), child, admin_listener.config.app, mcp_listener.config.app, port)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled(), 'the runtime stopped by itself while serving'


def expected_apply_state(product, mode):
    """configuration.apply_state once the first readiness check has settled (configuration.py: no backend is
    'unconfigured'; n8n's child runs without one and its checked child is 'applied')."""
    return 'applied' if mode == 'configured' or product == 'n8n' else 'unconfigured'


async def settle(runtime, mode):
    """Until the readiness check that runs at start has settled (GET /api/configuration shows it)."""
    wanted = expected_apply_state(runtime.product, mode)
    async with runtime.admin() as admin:
        async with asyncio.timeout(10):
            while True:
                response = await admin.get('/api/configuration', headers=ADMIN)
                assert response.status_code == 200
                if response.json()['configuration']['apply_state'] == wanted:
                    return
                await asyncio.sleep(.02)


def header_pairs(response):
    return sorted((name.decode('latin-1').lower(), value.decode('latin-1')) for name, value in response.headers.raw)


def initialize_message(ident=1):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'initialize', 'params': {
        'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'golden-client', 'version': '0'}}}


def initialize_body(product, ident=1):
    """The gateway's own initialize result (gateway.py: local_initialize and the rebuilt child answer)."""
    result = {'protocolVersion': PROTOCOL, 'capabilities': {'tools': {}},
              'serverInfo': {'name': 'woow-mcp-' + product,
                             'version': VERSION if product == 'n8n' else version_for_product(product)}}
    if product in INSTRUCTIONS:
        result['instructions'] = INSTRUCTIONS[product]
    return json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': result}, separators=(',', ':')).encode()


# ---- fixed answers (bb48449) ----

NOT_FOUND = (404, [('content-length', '9'), ('content-type', 'text/plain; charset=utf-8')], b'Not Found')
BEARER_REQUIRED = (401, [('content-length', '0'), ('www-authenticate', 'Bearer')], b'')
DENIED_400 = (400, [('content-length', '26'), ('content-type', 'application/json')], b'{"error":"request denied"}')
ACCEPTED = (202, [('cache-control', 'no-store'), ('content-length', '0')], b'')
SESSION_DELETED = (200, [('cache-control', 'no-store'), ('content-length', '0')], b'')
READY = {True: (200, [('content-length', '14'), ('content-type', 'application/json')], b'{"ready":true}'),
         False: (503, [('content-length', '15'), ('content-type', 'application/json')], b'{"ready":false}')}
BOOTSTRAP_COMMON = frozenset({
    'api_base', 'backend_edit', 'backend_key_set', 'backend_url', 'base_path', 'capabilities', 'configuration',
    'connection_configured', 'csrf', 'denied_operations', 'disabled', 'enabled_write_tools', 'endpoint', 'health',
    'mcp_access_token_set', 'operation_contract', 'policy_contract', 'product', 'token_active', 'token_history',
    'token_masked', 'tools', 'writes_enabled'})
BOOTSTRAP_EXTRA = {'odoo': {'odoo_allowed_methods', 'odoo_allowed_methods_source', 'odoo_write_switches',
                            'odoo_write_switches_source'},
                   'n8n': {'n8n_session', 'n8n_session_effective_minutes', 'n8n_session_source'}}
# tools/list (see the module docstring). LISTING_SHA256: the packaged listing, surface.listing(product) as compact JSON,
# the input of the gateway's rewrite. LISTED_SHA256: the whole tools/list answer, byte for byte, the packaged listing
# after the gateway's own rewrite (policy.filter_list, listed_tool; Odoo: odoo_switch_listing); the same in both states
# and on both paths.
LISTING_SHA256 = {
    'odoo': 'a350ca0d63713aff504dc1c500d492252bbcca63b9894fee11ac0c5096077f34',
    'n8n': 'e59f7ef7f56b205a013a6a6e23f75b6d6f615ef6fceea15f19fe4c40c1573e6a',
    'hermes': '2430f369faa5b6ff9840af7823b3392a49ef6e5bde0b754b9036051171362bfc',
    'opendesign': 'f97a2cc4c89a9e1fb6c8a366cd4d42420a4623cb817d909cab7de728bc7e3931',
    'emqx': '646abdc0232dc9aa704be13adb72ecc0a032219875e5854c4e53b3715eb28ae3',
    'litellm': 'a0bc6b2a17c444d5d121d8d31e4ae47500c23d30a9926b1ddbba73e809a42c88',
    'nextcloud': 'b772d6d13efd4ba25e7b8669ee3e3dd5babb57dac1f5cdc85ca037e6417deee7',
    'headscale': '1c677e914fa988de04674ff15ec19448a02b37b495c06a3ba146b8446cb21974',
}
LISTED_SHA256 = {
    'odoo': 'e96e4a87d4d23015dec6f4f03426fd142a3175095764082bda9c2588e6fb0500',
    'n8n': 'b9a68727b86186323186cc3d550efcd2975d9d3f3a10b5438a94903ea8093a98',
    'hermes': '8461b58e8bc211abc5a007507ef9c9df3843784994f67cf486c9a9f2ae4a0942',
    'opendesign': '9d205ad353e0b229cc584b98a673cfd584b1d838eb70f90cfa3175309819c7d9',
    'emqx': '5140e30f2e6fb52e99fcabb946e3f069c33f9e85b976f574d11431c221474148',
    'litellm': '8ae286590903c522c73bcd33c05d1e682fa8175cb0b76b1e68f3212ce5ccf029',
    'nextcloud': '1d302a5cf36e703a7bfe7da610230aa645f8e53a3125c47af812649ab1504a87',
    'headscale': '335ae6d5295f88a6a363d7c09545f3500fb5cb537069a4cf71d6ef161248a5db',
}
CAPABILITIES = frozenset({'admin', 'backend', 'capabilities', 'deployment', 'health', 'product', 'schema_version',
                          'tools'})
CONFIGURATION = frozenset({'revision', 'saved_revision', 'applied_revision', 'apply_state', 'last_error_code'})


def answer(response):
    return response.status_code, header_pairs(response), response.content


def json_answer(body):
    return 200, [('cache-control', 'no-store'), ('content-length', str(len(body))),
                 ('content-type', 'application/json')], body


def compact(value):
    return json.dumps(value, separators=(',', ':')).encode()


def child_answers(product, mode):
    """Whether a child answers this default profile's clients: a configured backend, or n8n's documentation child."""
    return mode == 'configured' or product == 'n8n'


def expected_health(product, mode):
    running = child_answers(product, mode)
    return {'management': 'alive',
            'child': {'state': 'running' if running else 'unconfigured', 'transport_ready': running,
                      'starts': 1 if running else 0, 'last_exit': None},
            'backend': 'reachable' if mode == 'configured' else 'unconfigured'}


def expected_entries(product, mode):
    """The data directory after a start: the store's lock and state, and the child's own empty working directory
    (products.child_spec) once a product child has a backend; n8n's child works in the data directory itself."""
    return ['.writer.lock', 'child', 'state.json'] if mode == 'configured' and product != 'n8n' else [
        '.writer.lock', 'state.json']


async def connect(runtime, client, path, headers, mode):
    """A client's whole session on one connection path; returns what each step answered and what the child got."""
    product = runtime.product
    since = len(runtime.child.requests)
    init = await client.post(path, headers=headers, json=initialize_message())
    session = init.headers.get('mcp-session-id', '')
    if child_answers(product, mode):
        assert re.fullmatch(r'golden-child-[0-9]+', session) and runtime.child.sessions[session] == 'golden-client'
    else:
        assert re.fullmatch(r'woow-local-[0-9a-f]{32}', session), 'the gateway answers itself without a child'
    assert answer(init) == (200, sorted([*json_answer(initialize_body(product))[1], ('mcp-session-id', session)]),
                            initialize_body(product))
    in_session = {**headers, 'Mcp-Session-Id': session}
    assert answer(await client.post(path, headers=in_session, json={
        'jsonrpc': '2.0', 'method': 'notifications/initialized'})) == ACCEPTED
    listed = await client.post(path, headers=in_session, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
    assert answer(listed)[:2] == json_answer(listed.content)[:2] and set(listed.json()) == {'jsonrpc', 'id', 'result'}
    assert [tool['name'] for tool in listed.json()['result']['tools']] == [tool['name'] for tool in listing(product)]
    source = hashlib.sha256(compact(listing(product))).hexdigest()
    digest = hashlib.sha256(listed.content).hexdigest()
    assert source == LISTING_SHA256[product], (
        f'{product}: the packaged tool listing changed (surface.listing sha256 {source}): a deliberate tool-surface '
        f'change (tool_snapshot.py regenerated). Check the new tools/list answer (sha256 {digest}) and update '
        'LISTING_SHA256 and LISTED_SHA256 of this product together')
    assert digest == LISTED_SHA256[product], (
        f'{product}: the default profile tools/list answer changed (sha256 {digest}) while the packaged listing did '
        "not: the gateway's own rewrite changed (policy.filter_list, listed_tool, odoo_switch_listing, the tool "
        'registry); a regression unless that change is deliberate, which then updates LISTED_SHA256')
    tool, arguments = public_read(product)
    called = await client.post(path, headers=in_session, json={
        'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': tool, 'arguments': arguments}})
    if mode == 'configured':
        text = json.dumps(PROBE_ANSWERS[product]) if tool == probe_name(product) else TOOL_TEXT
        expected = {'jsonrpc': '2.0', 'id': 3,
                    'result': {'content': [{'type': 'text', 'text': text}], 'isError': False}}
    else:
        expected = {'jsonrpc': '2.0', 'id': 3, 'error': {'code': -32603, 'message': 'Backend not configured',
                                                          'data': {'tool': tool}}}
    assert answer(called) == json_answer(compact(expected))
    assert answer(await client.delete(path, headers=in_session)) == SESSION_DELETED
    return runtime.child.forwarded(since)


def test_every_shipped_product_is_covered():
    assert sorted(PRODUCTS) == sorted(json.loads((ROOT / 'packaging/inputs.json').read_text())['products'])


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('product', PRODUCTS)
async def test_default_profile_golden(tmp_path, log_scan, product, mode):
    data = tmp_path / 'data'
    log_scan.watch(*secrets_of(product), kind='secret')
    if mode == 'configured':
        configure(data, product)
        saved = stat_signature(data / 'state.json')
    # First start of this data directory: a new installation, or a saved backend that the start must not rewrite.
    async with production_runtime(product, data) as runtime:
        await settle(runtime, mode)
    if mode == 'configured':
        assert stat_signature(data / 'state.json') == saved
    assert entries(data) == expected_entries(product, mode)
    state = stored(data)
    token, child_token = state['token'], state['child_token']
    log_scan.watch(token, child_token)
    before, files = stat_signature(data / 'state.json'), modes(data)

    async with production_runtime(product, data) as runtime:
        await settle(runtime, mode)
        async with runtime.mcp() as client:
            assert answer(await client.get('/health/ready')) == READY[mode == 'configured']
            # The default token on both connection paths.
            relayed = [('POST', 'initialize'), ('POST', 'notifications/initialized'), ('POST', 'tools/list'),
                       ('POST', 'tools/call'), ('DELETE', None)]
            expected_child = relayed if mode == 'configured' else (
                [('POST', 'initialize'), ('POST', 'notifications/initialized'), ('DELETE', None)]
                if product == 'n8n' else [])
            for path, auth in (('/mcp', {'Authorization': 'Bearer ' + token}), (f'/private_{token}/mcp', {})):
                assert await connect(runtime, client, path, {**ACCEPT, **auth}, mode) == expected_child, path
            # The error answers: no request reaches the child.
            since = len(runtime.child.requests)
            bearer = {**ACCEPT, 'Authorization': 'Bearer ' + token}
            wrong = secrets.token_urlsafe(32)
            for path, headers, expected in (
                    ('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + wrong}, BEARER_REQUIRED),
                    ('/mcp', ACCEPT, BEARER_REQUIRED),
                    (f'/private_{wrong}/mcp', ACCEPT, NOT_FOUND),
                    (f'/private_{wrong}/mcp', bearer, NOT_FOUND),  # the secret path never reads Authorization
                    ('/no-such-path', bearer, NOT_FOUND),
                    ('/mcp?x=1', bearer, DENIED_400),
                    (f'/private_{token}/mcp?x=1', ACCEPT, DENIED_400),
                    ('/mcp/', bearer, NOT_FOUND),
                    (f'/private_{token}/mcp/', ACCEPT, NOT_FOUND)):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == expected, path.replace(token, '<token>').replace(wrong, '<wrong>')
            assert runtime.child.forwarded(since) == []  # the health monitor's own checks (every 15 s) aside
        async with runtime.admin() as admin:
            bootstrap = await admin.get('/api/bootstrap', headers=ADMIN)
            assert bootstrap.status_code == 200 and bootstrap.headers['cache-control'] == 'no-store'
            body = bootstrap.json()
            assert set(body) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA.get(product, set())
            n8n_backend = product == 'n8n' and mode == 'configured'
            assert {key: body[key] for key in (
                'base_path', 'api_base', 'endpoint', 'backend_url', 'backend_key_set', 'token_active', 'token_masked',
                'token_history', 'mcp_access_token_set', 'product', 'connection_configured', 'writes_enabled',
                'disabled', 'policy_contract')} == {
                'base_path': '', 'api_base': '/api', 'endpoint': None,
                'backend_url': N8N_BACKEND['backend_url'] if n8n_backend else None, 'backend_key_set': n8n_backend,
                'token_active': True, 'token_masked': token[:4] + '*' * 20 + token[-4:], 'token_history': [],
                'mcp_access_token_set': False, 'product': product, 'connection_configured': mode == 'configured',
                'writes_enabled': True, 'disabled': [], 'policy_contract': 'woow-v3-exact-grants'}
            assert re.fullmatch(r'[0-9a-f]{64}', body['csrf'])
            assert set(body['operation_contract']) == {'version', 'server_time_ms', 'retention_ms'}
            assert (body['operation_contract']['version'], body['operation_contract']['retention_ms']) == (1, 86400000)
            assert set(body['configuration']) == CONFIGURATION
            assert body['configuration']['apply_state'] == expected_apply_state(product, mode)
            assert body['health'] == expected_health(product, mode)
            assert set(body['tools']) == {tool['name'] for tool in listing(product)}
            assert set(body['capabilities']) == CAPABILITIES
            assert set(body['backend_edit']) == {'contract', 'values', 'withheld_fields', 'secret_set'}
            configuration = await admin.get('/api/configuration', headers=ADMIN)
            assert configuration.status_code == 200 and set(configuration.json()['configuration']) == CONFIGURATION
            # The capabilities catalog lists the child's tools through its own session.
            listed = await admin.get('/api/capabilities', headers=ADMIN)
            assert listed.status_code == 200 and set(listed.json()) == CAPABILITIES
        for request in runtime.child.requests:
            # The child only ever gets the gateway's own bearer (MockChild refuses any other), never the client's, and
            # only the gateway's own headers.
            assert token not in str(request.url) and token.encode() not in request.content
            assert all(token not in value for value in request.headers.values())
            assert request.headers.get_list('authorization') == ['Bearer ' + child_token]
            assert set(request.headers) <= CHILD_HEADERS, sorted(set(request.headers) - CHILD_HEADERS)
    # Starting, reading and listing left the default profile's data as it was: state.json not even rewritten.
    assert stat_signature(data / 'state.json') == before
    assert modes(data) == files
