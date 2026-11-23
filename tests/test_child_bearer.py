"""HM-06 (multi-profile plan 8.3; contract 7 and 9 #37; invariant I4): a Python child serves only its own child bearer.

products.child_spec gives the seven Python children (Odoo, Hermes, OpenDesign, EMQX, LiteLLM, Nextcloud, Headscale)
WOOW_MCP_CHILD_TOKEN, the state's child_token. apps/runtime/session_idle.install(), which each of them runs before its
server builds its session manager, refuses to start without a valid one and puts its ChildBearer gate in front of the
asgi_app of every StreamableHTTPSessionManager (mcp 2.3.0 sets it in __init__; the routes of MCPServer and of FastMCP
4.1.3 call it): exactly one Authorization header equal to "Bearer <child token>" (hmac.compare_digest) reaches the SDK,
anything else gets 401 with no body and no detail.

The gateway, its health check and its catalog probe have always sent that bearer. A gateway that holds another child
token (multi-profile: a child on the wrong port) gets the 401 and answers 502, and its health check reads the child as
not ready, so nothing runs with the other profile's backend identity. n8n's child has always checked AUTH_TOKEN, the
same child_token (unchanged); the retired Odoo Manage (no image since 0.1.5) gets no bearer and stays as it is.

Real children (each in its pinned venv, from child_spec on an owned private port, fake backends), started as the add-on
starts them: the direct 401/200 matrix, inside a session too; no other path or method of the port serving without the
bearer, and no refusal waiting for a body; the gateway's own path and the wrong child token; the start refusals
(missing, empty, malformed). The real n8n child gets the same matrix: it refuses every wrong and other profile's bearer,
and takes three more forms of its own one (N8N_ALSO_ACCEPTS). No token shows in the child's own output (read before the
Supervisor's scrub) or in any log record of this process (HM-01 log_scan). Every token here is generated at test time.
"""
import asyncio
import base64
from contextlib import closing, suppress
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import time

import httpx
import pytest

from batch2_owned_port import OwnershipError, owned_listener
from log_scan import TOKEN_WINDOW, log_scan  # noqa: F401  (fixture)
from switch_modes import switched_off  # noqa: F401  (fixture: HM-19a, the switch these tests pin)
from mcp_admin_core.diagnostics import ChildLogs
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor, protocol_reply
from mcp_admin_core.products import PRODUCTS, PROBES, TOOLS, ProductStore, child_spec
import n8n_adapter
from n8n_adapter import child_spec as n8n_spec
from owned_runtime import Endpoint
from test_real_products import backend, connection

# HM-19a: the child spec and the real children (loopback fake backends) of the switched-off add-on
# (tests/switch_modes.py); switched on, the spec adds WOOW_MCP_DENY_LOOPBACK=1 (HM-20, tests/test_backend_loopback.py).
pytestmark = pytest.mark.usefixtures('log_scan', 'switched_off')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
ENV = 'WOOW_MCP_CHILD_TOKEN'
REFUSED = 'child bearer: WOOW_MCP_CHILD_TOKEN is missing or not a child token'  # session_idle.REFUSED, fixed
CHILDREN = ('odoo', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud', 'headscale')  # the seven Python children
ACCEPT = 'application/json, text/event-stream'
PROTOCOL = '2025-06-18'
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'child-bearer', 'version': '0'}}}
INITIALIZED = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
BIG = {'jsonrpc': '2.0', 'id': 4, 'method': 'ping', 'params': {'_meta': {'padding': 'A' * (2 * 1024 * 1024)}}}
REFUSAL = [{'type': 'http.response.start', 'status': 401,
            'headers': [(b'www-authenticate', b'Bearer'), (b'content-length', b'0')]},
           {'type': 'http.response.body', 'body': b''}]
READ_SECONDS = 30  # any one direct request: a child that never answers fails the test instead of hanging it
LIMIT = 16 * 1024 * 1024  # session_idle.BODY_BYTES: the SDK's body limit (413) in every child, behind the gate
# Requests around the child's one route (/mcp, every method behind the gate): other paths, the SDKs' usual extra routes
# (SSE, health, OAuth metadata, docs), every method on /mcp, a query, slashes, letter case and percent-encoding.
ROUTES = (('GET', '/'), ('POST', '/'), ('GET', '/mcp/'), ('POST', '/mcp/'), ('GET', '/sse'), ('GET', '/sse/'),
          ('POST', '/messages/'), ('POST', '/messages/?session_id=0'), ('GET', '/health'), ('GET', '/healthz'),
          ('GET', '/.well-known/oauth-protected-resource'), ('GET', '/.well-known/oauth-protected-resource/mcp'),
          ('GET', '/.well-known/oauth-authorization-server'), ('GET', '/docs'), ('GET', '/openapi.json'),
          ('OPTIONS', '/mcp'), ('HEAD', '/mcp'), ('PUT', '/mcp'), ('PATCH', '/mcp'), ('GET', '/mcp'),
          ('DELETE', '/mcp'), ('POST', '/mcp'), ('POST', '/mcp?x=1'), ('POST', '//mcp'), ('POST', '/MCP'),
          ('POST', '/mcp/x'), ('POST', '/mcp/..'), ('POST', '/%6dcp'), ('POST', '/mcp%2F'))

# Every variable each child gets: bb48449's set (child_spec of a configured state, default policy). HM-06 adds
# WOOW_MCP_CHILD_TOKEN to the seven Python children and nothing else (the env snapshot, review C4-SF-4).
BASE = {'HOME', 'PATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH', 'PYTHONUNBUFFERED'}
FASTMCP = {'FASTMCP_CHECK_FOR_UPDATES', 'FASTMCP_SHOW_SERVER_BANNER'}
ENV_KEYS = {
    'n8n': {'AUTH_TOKEN', 'DISABLE_CONSOLE_OUTPUT', 'HOME', 'HOST', 'LOG_LEVEL', 'MCP_MODE', 'N8N_API_KEY',
            'N8N_API_URL', 'N8N_MCP_MAX_SESSIONS', 'N8N_MCP_TELEMETRY_DISABLED', 'N8N_MCP_VERSION_CHECK_DISABLED',
            'NODE_ENV', 'PATH', 'PORT', 'SESSION_TIMEOUT_MINUTES', 'WEBHOOK_SECURITY_MODE'},
    'odoo': BASE | {'MCP_CHATTER_DIRECT', 'ODOO_DB', 'ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS',
                    'ODOO_MCP_ALLOW_DIRECT_WRITES', 'ODOO_MCP_ALLOW_UNKNOWN_METHODS', 'ODOO_MCP_ENABLE_WRITES',
                    'ODOO_PASSWORD', 'ODOO_TIMEOUT', 'ODOO_TRANSPORT', 'ODOO_URL', 'ODOO_USERNAME', 'ODOO_VERIFY_SSL'},
    'odoo-manage': BASE | {'ODOO_API_KEY', 'ODOO_DB', 'ODOO_MCP_ENABLE_METHOD_CALLS', 'ODOO_MCP_TRANSPORT', 'ODOO_URL',
                           'ODOO_USER', 'ODOO_YOLO'},
    'hermes': BASE | {'HERMES_DASHBOARD_PASSWORD', 'HERMES_DASHBOARD_URL', 'HERMES_DASHBOARD_USERNAME',
                      'HERMES_GATEWAY_API_KEY', 'HERMES_GATEWAY_URL'},
    'opendesign': BASE | {'OD_API_BASE'},
    'emqx': BASE | FASTMCP | {'EMQX_MCP_API_KEY', 'EMQX_MCP_API_SECRET', 'EMQX_MCP_BASE_URL', 'EMQX_MCP_DISABLED_TOOLS',
                              'EMQX_MCP_READONLY', 'EMQX_MCP_STATE_PATH'},
    'litellm': BASE | FASTMCP | {'LITELLM_MCP_BASE_URL', 'LITELLM_MCP_DISABLED_TOOLS', 'LITELLM_MCP_MASTER_KEY',
                                 'LITELLM_MCP_READONLY'},
    'nextcloud': BASE | FASTMCP | {'NEXTCLOUD_MCP_ALLOW_DELETE', 'NEXTCLOUD_MCP_APP_PASSWORD',
                                   'NEXTCLOUD_MCP_BASE_URL', 'NEXTCLOUD_MCP_DISABLED_TOOLS',
                                   'NEXTCLOUD_MCP_ERROR_CODES', 'NEXTCLOUD_MCP_READONLY', 'NEXTCLOUD_MCP_USERNAME'},
    'headscale': BASE | FASTMCP | {'HEADSCALE_MCP_API_KEY', 'HEADSCALE_MCP_BASE_URL', 'HEADSCALE_MCP_STATE_PATH'},
}


def load_session_idle():
    """apps/runtime/session_idle.py in this process (the children import it from apps/runtime)."""
    spec = importlib.util.spec_from_file_location('session_idle_under_test', ROOT / 'apps/runtime/session_idle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refused_values(token):
    """WOOW_MCP_CHILD_TOKEN values a child refuses to start with (from a token generated by the test)."""
    return {'empty': '', 'short': token[:-1], 'long': token + 'A', 'trailing newline': token + '\n',
            'trailing blank': token + ' ', 'leading blank': ' ' + token, 'dot': token[:-1] + '.',
            'base64 padding': token[:-1] + '=', 'base64 plus': token[:-1] + '+', 'base64 slash': token[:-1] + '/',
            'non-ASCII': token[:-1] + 'é', 'with the scheme': 'Bearer ' + token}


def refusals(own, other):
    """The Authorization headers of one request (a list; empty: none) a child holding own answers 401."""
    bearer = 'Bearer ' + own
    return {'none': [], 'other profile': ['Bearer ' + other], 'empty': [''], 'scheme only': ['Bearer'],
            'token only': [own], 'lower-case scheme': ['bearer ' + own], 'two blanks': ['Bearer  ' + own],
            'basic': ['Basic ' + base64.b64encode(('x:' + own).encode()).decode()], 'longer': [bearer + 'A'],
            'shorter': [bearer[:-1]], 'list in one header': [bearer + ', ' + bearer], 'twice': [bearer, bearer],
            'own then other': [bearer, 'Bearer ' + other], 'other then own': ['Bearer ' + other, bearer]}


def shows(text, token):
    """Any TOKEN_WINDOW-character piece of the token in the text: log_scan's rule (a partial token still leaks)."""
    return any(token[i:i + TOKEN_WINDOW] in text for i in range(len(token) - TOKEN_WINDOW + 1))


def run_all(commands, timeout=60):
    """Run every (argv, env, cwd) at once (each refusal is a separate interpreter start); [(returncode, stdout, stderr)]
    in order. A process still running when the shared timeout ends (a child that started instead of refusing) is killed
    and reported with returncode None and what it wrote until then."""
    processes = [subprocess.Popen(list(argv), env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for argv, env, cwd in commands]
    deadline = time.monotonic() + timeout
    try:
        results = []
        for process in processes:
            try:
                stdout, stderr = process.communicate(timeout=max(.1, deadline - time.monotonic()))
                results.append((process.returncode, stdout, stderr))
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                results.append((None, stdout, stderr))
        return results
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


class RawLogs(ChildLogs):
    """The Supervisor's buffer of the child's output, also keeping every line as the child wrote it: the buffer itself
    scrubs the spec's secrets, so it could not show that the child printed one."""

    def __init__(self):
        super().__init__()
        self.raw = []

    def append(self, stream, text, generation, secrets=()):
        self.raw.append(text)
        super().append(stream, text, generation, secrets)


# ---- child_spec: who gets the bearer ----

@pytest.mark.parametrize('product', ('n8n', *PRODUCTS))
def test_child_spec_gives_the_seven_python_children_their_child_token(tmp_path, log_scan, monkeypatch, product):
    # NODE_DB_PATH comes from a catalog copy prepare_catalog() made earlier in the same process (apps/n8n/run.py at
    # start-up): none here, whatever ran before this test.
    monkeypatch.setattr(n8n_adapter, '_catalog', None)
    with closing(ProductStore(tmp_path / 'state', product)) as store:
        if product == 'n8n':
            store.update(backend_url='https://n8n.invalid', backend_key='DUMMY-hm06-workflow-key')
            state = store.load()
            spec = n8n_spec(state, store.directory)
        else:
            store.update(connection=connection(product, 'https://backend.invalid'))
            state = store.load()
            spec = child_spec(state, store.directory)
    log_scan.watch_state(state)
    assert set(spec.env) == ENV_KEYS[product] | ({ENV} if product in CHILDREN else set())
    if product in CHILDREN:
        assert spec.env[ENV] == state.child_token
    elif product == 'n8n':
        assert spec.env['AUTH_TOKEN'] == state.child_token  # n8n-mcp checks it itself, as before
    assert state.token not in spec.env.values()  # the add-on token never reaches a child
    # Neither token is ever an argument: every local user can read a process's command line (/proc/<pid>/cmdline).
    assert not any(shows(argument, state.child_token) or shows(argument, state.token) for argument in spec.argv)


# ---- session_idle's gate in this process ----

def test_the_token_is_read_from_the_environment_or_the_child_refuses(monkeypatch):
    idle = load_session_idle()
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv(ENV, token)
    assert idle.bearer() == b'Bearer ' + token.encode()
    monkeypatch.delenv(ENV)
    cases = {'missing': None, **refused_values(token)}
    for case, value in cases.items():
        if value is not None:
            monkeypatch.setenv(ENV, value)
        with pytest.raises(RuntimeError) as refused:
            idle.bearer()
        # A fixed message: never the value, nor another exception (an encoding error, say) chained to it.
        assert str(refused.value) == idle.REFUSED == REFUSED, case
        assert refused.value.__cause__ is None and refused.value.__context__ is None, case


class Inner:
    """Stands in for the SDK's asgi_app: records what reaches it."""

    def __init__(self):
        self.scopes = []

    async def __call__(self, scope, receive, send):
        self.scopes.append(scope)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'served'})


async def drive(gate, headers, kind='http'):
    sent = []

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message):
        sent.append(message)

    await gate({'type': kind, 'method': 'POST', 'path': '/mcp', 'headers': headers}, receive, send)
    return sent


async def test_the_gate_lets_only_the_child_bearer_through(monkeypatch):
    idle = load_session_idle()
    own, other = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    compared = []
    compare = idle.hmac.compare_digest
    monkeypatch.setattr(idle.hmac, 'compare_digest', lambda a, b: compared.append((a, b)) or compare(a, b))
    inner = Inner()
    gate = idle.ChildBearer(inner, b'Bearer ' + own.encode())
    assert not shows(repr(gate), own) and not hasattr(gate, '__dict__')
    for case, values in refusals(own, other).items():
        compared.clear()
        headers = [(b'authorization', value.encode()) for value in values]
        assert await drive(gate, headers) == REFUSAL, case
        assert inner.scopes == [], case
        # One value is compared in constant time against the whole bearer; none, or two, are never compared.
        assert compared == ([(values[0].encode(), b'Bearer ' + own.encode())] if len(values) == 1 else []), case
    # The header name in any letter case counts (ASGI servers send it lower case): two names that differ only in case
    # are two Authorization headers, whichever of them holds the own bearer.
    for first, second in ((b'Authorization', b'authorization'), (b'authorization', b'AUTHORIZATION')):
        assert await drive(gate, [(first, b'Bearer ' + other.encode()), (second, b'Bearer ' + own.encode())]) == REFUSAL
        assert await drive(gate, [(first, b'Bearer ' + own.encode()), (second, b'x')]) == REFUSAL
    assert inner.scopes == []
    sent = await drive(gate, [(b'host', b'127.0.0.1'), (b'authorization', b'Bearer ' + own.encode()),
                              (b'accept', b'*/*')])
    assert len(inner.scopes) == 1 and sent[-1] == {'type': 'http.response.body', 'body': b'served'}
    assert (await drive(gate, [(b'Authorization', b'Bearer ' + own.encode())]))[-1]['body'] == b'served'
    assert len(inner.scopes) == 2
    # Not an HTTP request: it never reaches the SDK and gets nothing.
    for kind in ('websocket', 'lifespan'):
        assert await drive(gate, [(b'authorization', b'Bearer ' + own.encode())], kind) == []
    assert len(inner.scopes) == 2
    with pytest.raises(ValueError):
        idle.ChildBearer(inner, own.encode())  # not "Bearer " + a child token


# Both SDK flavours (mcp 2.3.0 MCPServer: Odoo, Hermes, OpenDesign; FastMCP 4.1.3: EMQX, LiteLLM, Nextcloud,
# Headscale): install() refuses before it patches anything, else every manager's asgi_app is the gate.
UNIT = r'''
import json, sys
import session_idle
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager as Manager
original = Manager.__init__
try:
    session_idle.install()
except RuntimeError as exc:
    print(json.dumps({'refused': str(exc), 'patched': Manager.__init__ is not original})); sys.exit(0)
managers = [Manager(app=object()), Manager(app=object(), stateless=True), Manager(object(), None, False, False),
            Manager(app=object(), session_idle_timeout=5, max_request_body_size=1024)]
if sys.argv[1] == 'fastmcp':
    from fastmcp.server.http import FastMCPStreamableHTTPSessionManager
    managers.append(FastMCPStreamableHTTPSessionManager(app=object()))
else:
    from mcp.server.mcpserver import MCPServer
    server = MCPServer('t')
    server.streamable_http_app()
    managers.append(server.session_manager)
print(json.dumps({'gates': [type(m.asgi_app).__name__ for m in managers],
                  'inside': [type(m.asgi_app.app).__name__ for m in managers]}))
'''


@pytest.mark.parametrize('venv,flavour', [('hermes', 'sdk'), ('emqx', 'fastmcp')])
def test_install_gates_every_manager_or_refuses_before_patching(venv, flavour):
    token = secrets.token_urlsafe(32)
    values = (token, None, '', token[:-1] + '.')
    commands = []
    for value in values:
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'), 'PYTHONDONTWRITEBYTECODE': '1'}
        if value is not None:
            env[ENV] = value
        commands.append(([str(ROOT / 'apps' / venv / '.venv/bin/python'), '-c', UNIT, flavour], env, ROOT))
    found = []
    for returncode, stdout, stderr in run_all(commands, timeout=120):
        assert returncode == 0, stderr[-2000:]
        assert not shows(stdout + stderr, token)
        found.append(json.loads(stdout.splitlines()[-1]))
    # Stateful and stateless, positional and keyword, the SDK's own server and FastMCP's subclass: the gate is in
    # front of the SDK's app (its body limit inside), never instead of it.
    assert found[0] == {'gates': ['ChildBearer'] * 5, 'inside': ['RequestBodyLimitMiddleware'] * 5}
    assert found[1:] == [{'refused': REFUSED, 'patched': False}] * 3  # missing, empty, malformed


# ---- the real children ----

async def send(client, method, url, authorization, *, message=None, session=None):
    """One request with exactly these Authorization headers (a list; empty: none): the client adds none of its own.
    (response, result) for a 200 request answer, else (response, body). A GET answered 200 is an open event stream:
    it is returned unread (b''), so a child that wrongly serves one fails the 401 check at once instead of hanging the
    test; and no request takes longer than READ_SECONDS."""
    headers = [('Accept', ACCEPT)]
    if session is not None:
        headers += [('Mcp-Session-Id', session), ('MCP-Protocol-Version', PROTOCOL)]
    content = None
    if message is not None:
        headers.append(('Content-Type', 'application/json'))
        content = json.dumps(message).encode()
    headers += [('Authorization', value) for value in authorization]
    async with asyncio.timeout(READ_SECONDS), client.stream(method, url, headers=headers, content=content) as response:
        if response.status_code == 200 and message is not None and 'id' in message:
            return response, await protocol_reply(response, message['id'])
        if method == 'GET' and response.status_code == 200:
            return response, b''
        return response, await response.aread()


def assert_refused(response, body, case):
    assert response.status_code == 401, (case, response.status_code)
    assert body == b'' and response.headers.get('www-authenticate') == 'Bearer', case
    assert 'mcp-session-id' not in response.headers and 'content-type' not in response.headers, case


def owned(endpoint):
    """Raise unless the listener on the endpoint's private port is still its supervised child (owned_runtime's proof),
    for the requests the shared client does not take (its guard sends to /mcp only)."""
    if endpoint.proof is None or owned_listener(endpoint.manager, endpoint.port) != endpoint.proof:
        raise OwnershipError('owned child listener proof no longer valid')


async def assert_no_other_route(endpoint):
    """Without a bearer nothing on the child's port serves (ROUTES): no 2xx, no session. An SDK upgrade that adds a
    default HTTP route, or moves the route off the gated asgi_app, fails here. No answer's body is read."""
    async def check(request):
        assert (request.url.host, request.url.port) == ('127.0.0.1', endpoint.port)
        assert 'authorization' not in request.headers
        owned(endpoint)

    content = json.dumps(INIT).encode()
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=15,
                                 event_hooks={'request': [check]}) as plain:
        for method, path in ROUTES:
            async with asyncio.timeout(READ_SECONDS), plain.stream(
                    method, f'http://127.0.0.1:{endpoint.port}{path}',
                    headers={'Accept': ACCEPT, 'Content-Type': 'application/json'},
                    content=content if method in ('POST', 'PUT', 'PATCH') else None) as response:
                assert not 200 <= response.status_code < 300, (method, path, response.status_code)
                assert 'mcp-session-id' not in response.headers, (method, path)


async def unsent_body_answer(endpoint, authorization, declared):
    """POST /mcp on a fresh socket with these Authorization values, declaring a body of declared bytes and sending none
    of it: the answer's status code, or None when none comes within 5 seconds (something is waiting for the body)."""
    owned(endpoint)
    reader, writer = await asyncio.open_connection('127.0.0.1', endpoint.port)
    try:
        head = [b'POST /mcp HTTP/1.1', b'Host: 127.0.0.1:%d' % endpoint.port, b'Accept: ' + ACCEPT.encode(),
                b'Content-Type: application/json', b'Content-Length: %d' % declared, b'Connection: close']
        head += [b'Authorization: ' + value.encode() for value in authorization]
        writer.write(b'\r\n'.join(head) + b'\r\n\r\n')
        await writer.drain()
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
        except TimeoutError:
            return None
        assert line.startswith(b'HTTP/1.1 ') and line[9:12].isdigit(), line[:12]
        return int(line[9:12])
    finally:
        writer.close()
        with suppress(OSError, TimeoutError):
            await asyncio.wait_for(writer.wait_closed(), 2)


async def through(app, token, message, session=None):
    """One request through a gateway's MCP app with the add-on token: (response, result or body)."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary', timeout=15) as client:
        headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT}
        if session is not None:
            headers.update({'Mcp-Session-Id': session, 'MCP-Protocol-Version': PROTOCOL})
        async with client.stream('POST', '/mcp', headers=headers, json=message) as response:
            if response.status_code == 200 and 'id' in message:
                return response, await protocol_reply(response, message['id'])
            return response, await response.aread()


@pytest.mark.parametrize('product', CHILDREN)
async def test_real_child_serves_only_its_own_child_bearer(tmp_path, log_scan, product):
    with backend(product) as (url, calls, _offline), \
            closing(ProductStore(tmp_path / 'own', product)) as own_store, \
            closing(ProductStore(tmp_path / 'other', product)) as other_store:
        for store in (own_store, other_store):  # two profiles of one product: the same backend, two child tokens
            store.update(connection=connection(product, url))
            log_scan.watch_state(store.load())
        own_state, other_state = own_store.load(), other_store.load()
        own, other = own_state.child_token, other_state.child_token
        bearer = 'Bearer ' + own
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(child_spec(own_state, own_store.directory))
        manager.logs = RawLogs()
        try:
            await manager.start()
            async with endpoint.client(bearer=False, timeout=15) as client:
                started = time.monotonic()
                while True:  # until the child serves its own bearer
                    try:
                        response, result = await send(client, 'POST', endpoint.url, [bearer], message=INIT)
                        break
                    except (httpx.HTTPError, ValueError):
                        if time.monotonic() - started > 40:
                            raise
                        await asyncio.sleep(.25)
                assert response.status_code == 200 and result['protocolVersion'] == PROTOCOL
                session = response.headers['mcp-session-id']
                # Direct requests to the child: 401 for anything but exactly one Authorization: Bearer <own>.
                for case, values in refusals(own, other).items():
                    assert_refused(*await send(client, 'POST', endpoint.url, values, message=INIT), case)
                # The refusal reads no body: a large one (beyond uvicorn's 64 KiB read buffer) is still refused at once
                # and the next request is served.
                assert_refused(*await send(client, 'POST', endpoint.url, [], message=BIG), 'large body')
                # Nothing else on the port serves without the bearer, and a refusal never waits for the body: one that
                # is declared and never sent is refused at once, beyond the SDK's own limit too (the gate is in front
                # of that limit, which buffers a body before the SDK reads it); the own bearer then meets the limit.
                before = len(calls)
                await assert_no_other_route(endpoint)
                answers = {}  # by case name only: a failure never shows a token
                for case, values, declared in (('none, 8 MiB', [], 8 * 1024 * 1024), ('none, over', [], LIMIT + 1),
                                               ('other profile, over', ['Bearer ' + other], LIMIT + 1),
                                               ('own, over', [bearer], LIMIT + 1)):
                    answers[case] = await unsent_body_answer(endpoint, values, declared)
                assert answers == {'none, 8 MiB': 401, 'none, over': 401, 'other profile, over': 401,
                                   'own, over': 413}, answers
                assert len(calls) == before
                response, _ = await send(client, 'POST', endpoint.url, [bearer], message=INITIALIZED, session=session)
                assert response.status_code == 202
                # Inside the session it opened: every method needs the bearer again; a refused DELETE ends nothing.
                for case in ('none', 'other profile', 'twice'):
                    values = refusals(own, other)[case]
                    assert_refused(*await send(client, 'POST', endpoint.url, values, message=LIST, session=session),
                                   case)
                    assert_refused(*await send(client, 'GET', endpoint.url, values, session=session), case)
                    assert_refused(*await send(client, 'DELETE', endpoint.url, values, session=session), case)
                response, listed = await send(client, 'POST', endpoint.url, [bearer], message=LIST, session=session)
                assert response.status_code == 200 and listed['tools']
                response, _ = await send(client, 'DELETE', endpoint.url, [bearer], session=session)
                assert response.status_code in (200, 204)
            # The gateway sends its state's child token: its own child serves it. A gateway holding another profile's
            # child token (that child's port taken by this one) gets 401 and answers 502: nothing reaches the backend.
            async with endpoint.client(timeout=15) as child:
                _, own_gateway = make_apps(own_store, TOOLS[product], child, child_url=endpoint.url)
                _, other_gateway = make_apps(other_store, TOOLS[product], child, child_url=endpoint.url)
                response, result = await through(own_gateway, own_state.token, INIT)
                assert response.status_code == 200 and result['protocolVersion'] == PROTOCOL
                session = response.headers['mcp-session-id']
                assert not session.startswith('woow-local-')  # the child's own session
                response, _ = await through(own_gateway, own_state.token, INITIALIZED, session)
                assert response.status_code == 202
                name, arguments = PROBES[product]
                call = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': arguments}}
                before = len(calls)
                response, called = await through(own_gateway, own_state.token, call, session)
                assert response.status_code == 200 and called.get('isError') is not True, called
                assert len(calls) > before  # the call ran against the backend
                before = len(calls)
                for message, opened in ((INIT, None), (call, session)):  # even with a session the child really opened
                    response, body = await through(other_gateway, other_state.token, message, opened)
                    assert response.status_code == 502 and 'mcp-session-id' not in response.headers, message['method']
                    assert json.loads(body) == {'error': 'request denied'}
                assert len(calls) == before
                # That profile's health check gets the same 401: its child is not ready and the backend is not
                # called. The own one still is ready and reaches the backend.
                other_health = HealthMonitor(other_store, manager, child, child_url=endpoint.url)
                await other_health.check()
                assert other_health.availability()['ready'] is False and other_health.backend == 'unreachable'
                assert len(calls) == before
                own_health = HealthMonitor(own_store, manager, child, child_url=endpoint.url)
                await own_health.check()
                assert own_health.availability()['ready'] is True and own_health.backend == 'reachable'
                assert len(calls) > before
                response, listed = await through(own_gateway, own_state.token, LIST, session)
                assert response.status_code == 200 and listed['tools']
        finally:
            await manager.stop()
            endpoint.close()
    output = '\n'.join(manager.logs.raw)
    assert manager.starts == 1 and manager.last_exit is None  # one child served everything above
    for token in (own, other, own_state.token, other_state.token):
        assert not shows(output, token)


# n8n's child (n8n-mcp, Node) has always checked AUTH_TOKEN, the same child_token, and HM-06 leaves it as it is (plan
# 8.3). Its check (http-server-single-session.js authenticateRequest) wants "Bearer " and compares the rest trimmed, and
# Node's http keeps only the first of repeated Authorization headers: so it also takes three forms a Python child
# refuses. Each of them still needs its own token first; no other profile's or wrong bearer gets through. Decided
# 2026-11-15 (HM-06 review MF-1, option (a); HM-06 provenance note, section 12.1): n8n stays as it is, and HM-00's
# T-23 (acceptance-matrix.md), threat-model I4 and contract 9 #37 say what it takes. The gateway only ever sends its
# own child bearer, in one header (the HM-01 golden regression pins it: a client cannot add a second one), and only
# processes in the add-on's container, the same uid (DQ-37's accepted trust boundary), reach the child's port directly.
N8N_ALSO_ACCEPTS = ('two blanks', 'twice', 'own then other')


async def test_real_n8n_child_serves_only_its_own_auth_token(tmp_path, log_scan):
    with closing(ProductStore(tmp_path / 'own', 'n8n')) as own_store, \
            closing(ProductStore(tmp_path / 'other', 'n8n')) as other_store:
        own_state, other_state = own_store.load(), other_store.load()
        for state in (own_state, other_state):
            log_scan.watch_state(state)
        own, other = own_state.child_token, other_state.child_token
        endpoint = Endpoint('n8n')
        manager = endpoint.supervisor(n8n_spec(own_state, own_store.directory))
        manager.logs = RawLogs()
        try:
            await manager.start()
            async with endpoint.client(bearer=False, timeout=15) as client:
                started = time.monotonic()
                while True:
                    try:
                        response, result = await send(client, 'POST', endpoint.url, ['Bearer ' + own], message=INIT)
                        break
                    except (httpx.HTTPError, ValueError):
                        if time.monotonic() - started > 40:
                            raise
                        await asyncio.sleep(.25)
                assert response.status_code == 200 and result['protocolVersion']
                for case, values in refusals(own, other).items():
                    response, _ = await send(client, 'POST', endpoint.url, values, message=INIT)
                    if case in N8N_ALSO_ACCEPTS:
                        assert response.status_code == 200, case
                    else:
                        assert response.status_code == 401 and 'mcp-session-id' not in response.headers, case
        finally:
            await manager.stop()
            endpoint.close()
    output = '\n'.join(manager.logs.raw)
    for token in (own, other, own_state.token, other_state.token):
        assert not shows(output, token)


@pytest.mark.parametrize('product', CHILDREN)
def test_a_child_without_a_valid_child_token_refuses_to_start(tmp_path, product):
    with backend(product) as (url, _calls, _offline):
        with closing(ProductStore(tmp_path / 'state', product)) as store:
            store.update(connection=connection(product, url))
            state = store.load()
            spec = child_spec(state, store.directory)
        endpoint = Endpoint(product)
        try:
            spec = endpoint.prepare(spec)  # an owned private port: a child that wrongly started would serve there
        finally:
            endpoint.close()
        token = secrets.token_urlsafe(32)
        cases = (('missing', None), ('empty', ''), ('malformed', token[:-1] + '.'))
        commands = []
        for _case, value in cases:
            env = {key: item for key, item in spec.env.items() if key != ENV}
            if value is not None:
                env[ENV] = value
            commands.append((spec.argv, env, spec.cwd))
        for (case, _value), (returncode, stdout, stderr) in zip(cases, run_all(commands)):
            assert returncode is not None, (case, 'the child started instead of refusing')
            assert returncode != 0 and REFUSED in stderr, (case, returncode, stderr[-2000:])
            assert 'Uvicorn running' not in stdout + stderr, case
            for secret in (token, state.child_token, state.token):
                assert not shows(stdout + stderr, secret), case
