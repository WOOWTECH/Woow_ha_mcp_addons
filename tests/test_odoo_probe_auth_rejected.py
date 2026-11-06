"""LOCAL/MOCK: the Odoo readiness probe tells a refused login from an unreachable server (unreleased, 0.4.12 line).

Found on 2026-11-05 with a real Odoo 18 (HA 0.4.10 against PaaS 21ec3be8): with a wrong password the PaaS server answered a
tool call "Failed to authenticate with Odoo: Authentication failed: Invalid username or password", while HA refused every
tool, `health_check` included, with `-32603 Backend unreachable` and `data.reason` `BACKEND_UNAVAILABLE`: the same words
it uses for a server that is down. The probe now answers a login Odoo itself refused with BACKEND_AUTH_REJECTED (the code
the Hermes tools already use) and keeps BACKEND_UNAVAILABLE for everything else. The reason stays a fixed text: it never
carries the URL, the database, the user, the password or the exception text.

Genuine pinned Odoo child (the real odoo-mcp 1.3.0 OdooClient and the add-on's XML-RPC transport), an owned stdlib XML-RPC
peer that checks database, login and password the way Odoo answers authenticate, the real HealthMonitor and gateway.
"""
import asyncio
from contextlib import asynccontextmanager, closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import subprocess
import threading
import xmlrpc.client
from pathlib import Path

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec, health_probe
from mcp_admin_core.surface import listing
from owned_runtime import Endpoint
from test_expansion_policy import call
from test_odoo_read_exists import initialize
from test_real_products import connection, rpc
from tool_refusal import refusal

ROOT = Path(__file__).resolve().parents[1]
AUTH = ("BACKEND_AUTH_REJECTED: Odoo 憑證被拒 (credentials rejected); check the database, username and password in the "
        "add-on's connection settings.")
UNAVAILABLE = 'BACKEND_UNAVAILABLE'
ACCEPT = {'Accept': 'application/json, text/event-stream'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'probe-test', 'version': '0'}}}
POSTGRES_FAULT = ('Traceback (most recent call last):\n  File "/opt/odoo/odoo/service/model.py", line 80, in dispatch\n'
                  'psycopg2.OperationalError: connection to server at "db" (10.0.0.5), port 5432 failed: ')


@contextmanager
def fake_odoo():
    """Answers /xmlrpc/2/common authenticate as Odoo does: a false uid for a wrong password or an unknown login, a fault
    naming the database for one PostgreSQL does not know. `mode` switches in the failures of the server itself."""
    state = {'mode': 'normal', 'seen': [], 'release': threading.Event()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def answer(self, data, content_type='text/xml'):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            mode = state['mode']
            if mode == 'http_503':
                self.send_error(503)
                return
            if mode == 'redirect':
                self.send_response(302)
                self.send_header('Location', 'http://127.0.0.1:9/xmlrpc/2/common')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if mode == 'not_xml':
                self.answer(b'<html><body>Please sign in</body></html>', 'text/html')
                return
            if mode == 'slow':  # longer than the add-on's 5 s limit; the test sets the event on the way out
                state['release'].wait(9)
                return
            params, method = xmlrpc.client.loads(body)
            assert self.path == '/xmlrpc/2/common' and method == 'authenticate', (self.path, method)
            database, login, password = params[:3]
            state['seen'].append((database, login))
            try:
                if mode == 'denied_fault':
                    raise xmlrpc.client.Fault(3, 'Access Denied')
                if mode == 'postgres_down':
                    raise xmlrpc.client.Fault(1, POSTGRES_FAULT + 'Connection refused\n')
                if mode == 'other_fault':
                    raise xmlrpc.client.Fault(1, 'Traceback (most recent call last):\nZeroDivisionError: division by zero\n')
                if database != 'test':
                    raise xmlrpc.client.Fault(1, POSTGRES_FAULT + f'FATAL:  database "{database}" does not exist\n')
                value = 7 if (login, password) == ('tester', 'DUMMY') else False
                data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
            except xmlrpc.client.Fault as fault:
                data = xmlrpc.client.dumps(fault).encode()
            self.answer(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        state['release'].set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@asynccontextmanager
async def running_child(tmp_path, url, **overrides):
    store = ProductStore(tmp_path / 'state', 'odoo')
    store.update(connection={**connection('odoo', url), **overrides})
    endpoint = Endpoint('odoo')
    process = endpoint.supervisor(child_spec(store.load(), store.directory))
    try:
        await process.start()
        yield store, endpoint, process
    finally:
        await process.stop()
        store.close()


async def probe(store, endpoint):
    """woow_backend_probe on the genuine child, called as HealthMonitor calls it: (isError, text)."""
    async with endpoint.client(timeout=30) as child:  # the slow case answers after the add-on's own 5 s limit
        headers = {'Authorization': 'Bearer ' + store.load().child_token, **ACCEPT}
        async with asyncio.timeout(25):
            while True:
                try:
                    result = await rpc(child, endpoint.url, headers, INIT)
                    break
                except ValueError:
                    await asyncio.sleep(.1)
        headers['MCP-Protocol-Version'] = result['protocolVersion']
        await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        name, arguments = health_probe('odoo')
        reply = await rpc(child, endpoint.url, headers, call(name, arguments))
    return bool(reply.get('isError')), reply['content'][0]['text']


def failed(reason):
    return True, 'Error executing tool woow_backend_probe: ' + reason


def dead_url():
    with closing(socket.socket()) as holder:
        holder.bind(('127.0.0.1', 0))
        return f'http://127.0.0.1:{holder.getsockname()[1]}'  # nothing listens once the socket is closed


async def test_a_login_odoo_accepts_still_returns_the_uid(tmp_path):
    with fake_odoo() as (url, state):
        async with running_child(tmp_path, url) as (store, endpoint, _):
            is_error, text = await probe(store, endpoint)
            assert not is_error and json.loads(text) == {'uid': 7}
            assert state['seen'] == [('test', 'tester')]


@pytest.mark.parametrize('overrides', [
    pytest.param({'password': 'WRONG-pass'}, id='wrong-password'),
    pytest.param({'username': 'nobody'}, id='unknown-user'),
    pytest.param({'database': 'nowhere'}, id='unknown-database'),
])
async def test_a_login_odoo_refuses_is_auth_rejected(tmp_path, overrides):
    with fake_odoo() as (url, state):
        async with running_child(tmp_path, url, **overrides) as (store, endpoint, _):
            assert await probe(store, endpoint) == failed(AUTH)
            assert len(state['seen']) == 1  # one authenticate, nothing else
            for secret in (url, url.rsplit(':', 1)[1], 'DUMMY', 'WRONG-pass', 'nobody', 'nowhere', 'tester', 'Traceback'):
                assert secret not in AUTH  # the fixed text, whatever the connection holds


async def test_odoo_failures_other_than_a_refused_login_stay_unavailable(tmp_path):
    with fake_odoo() as (url, state):
        async with running_child(tmp_path, url) as (store, endpoint, _):
            expected = {
                'denied_fault': AUTH,           # Odoo's own AccessDenied fault: the same refusal
                'postgres_down': UNAVAILABLE,   # Odoo answered, but its database is down: not the credentials
                'other_fault': UNAVAILABLE,
                'http_503': UNAVAILABLE,        # a proxy or a dead worker, not XML-RPC
                'redirect': UNAVAILABLE,        # redirects are never followed
                'not_xml': UNAVAILABLE,         # a login page in front of Odoo, not XML-RPC
            }
            for mode, reason in expected.items():
                state['mode'] = mode
                assert await probe(store, endpoint) == failed(reason), mode
            state['mode'] = 'normal'  # every probe builds a fresh client: nothing sticks after the server recovers
            is_error, text = await probe(store, endpoint)
            assert not is_error and json.loads(text) == {'uid': 7}


async def test_a_slow_odoo_is_unavailable_not_rejected(tmp_path):
    with fake_odoo() as (url, state):
        async with running_child(tmp_path, url) as (store, endpoint, _):
            state['mode'] = 'slow'
            started = asyncio.get_running_loop().time()
            assert await probe(store, endpoint) == failed(UNAVAILABLE)
            assert 4 < asyncio.get_running_loop().time() - started < 9  # the transport's 5 s limit, not Odoo's answer


async def test_a_closed_port_is_unavailable_not_rejected(tmp_path):
    async with running_child(tmp_path, dead_url()) as (store, endpoint, _):
        assert await probe(store, endpoint) == failed(UNAVAILABLE)


async def test_the_health_check_and_the_gateway_carry_the_reason(tmp_path):
    async def refused_calls(store, endpoint, child, health):
        """tools/call through the real gateway: the refusal of a tool that needs the backend, and of health_check."""
        _, app = make_apps(store, TOOLS['odoo'], child, child_url=endpoint.url, listing=listing('odoo'),
                           availability=health.availability)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
            headers = {'Authorization': 'Bearer ' + store.load().token, **ACCEPT}
            await initialize(client, headers)  # the child answers initialize whatever the backend says
            return [refusal(await client.post('/mcp', headers=headers, json=call(name, {})))
                    for name in ('search_records', 'health_check')]

    async def check(name, url, **overrides):
        (tmp_path / name).mkdir()
        async with running_child(tmp_path / name, url, **overrides) as (store, endpoint, process):
            async with endpoint.client() as child:
                health = HealthMonitor(store, process, child, child_url=endpoint.url)
                await health.check()
                return health.availability(), await refused_calls(store, endpoint, child, health)

    def refusal_of(tool, reason):
        return {'code': -32603, 'message': 'Backend unreachable', 'data': {'tool': tool, 'reason': reason}}

    with fake_odoo() as (url, state):
        # A refused password: still "unreachable" by the readiness rules (as for Hermes), but with the right words.
        available, errors = await check('rejected', url, password='WRONG-pass')
        assert available == {'child': 'running', 'ready': True, 'backend': 'unreachable', 'reason': AUTH}
        # The gating is the 0.2.2 rule, unchanged: every Odoo tool is refused, health_check too; only the reason differs.
        assert errors == [refusal_of('search_records', AUTH), refusal_of('health_check', AUTH)]
        # A server that is down keeps the old words.
        available, errors = await check('down', dead_url())
        assert available == {'child': 'running', 'ready': True, 'backend': 'unreachable', 'reason': UNAVAILABLE}
        assert errors == [refusal_of('search_records', UNAVAILABLE), refusal_of('health_check', UNAVAILABLE)]
        # And a login Odoo accepts is reachable, with no reason: nothing is refused.
        available, errors = await check('reachable', url)
        assert available == {'child': 'running', 'ready': True, 'backend': 'reachable', 'reason': None}
        assert errors == [None, None]


def test_probe_failure_reads_the_exceptions_odoo_mcp_raises():
    """The classification itself, in the Odoo child's own interpreter, on the exception chains OdooClient builds: its
    ValueError('Failed to authenticate with Odoo: ...') is raised inside the except block that caught the cause."""
    script = r'''
import json, xmlrpc.client
import launch

def chain(inner, outer=ValueError, prefix='Failed to authenticate with Odoo: '):
    try:
        try:
            raise inner
        except Exception as caught:
            raise outer(prefix + str(caught))
    except Exception as new:
        return new

cycle = ValueError('a'); other = ValueError('b'); cycle.__context__ = other; other.__context__ = cycle
fault = xmlrpc.client.Fault
cases = {
    'false uid': chain(ValueError('Authentication failed: Invalid username or password')),
    'denied 3': chain(fault(3, 'Access Denied')),
    'denied old': chain(fault('AccessDenied', 'Access Denied')),
    'denied traceback': chain(fault(1, 'Traceback (most recent call last):\nodoo.exceptions.AccessDenied: Access Denied\n')),
    'database missing': chain(fault(1, 'Traceback\nFATAL:  database "x" does not exist\n')),
    'database down': chain(fault(1, 'Traceback\nconnection refused\n')),
    'other fault': chain(fault(2, "Object account.move.line doesn't exist")),
    'connect': chain(ConnectionError('BACKEND_UNAVAILABLE: refused'), ConnectionError, 'Failed to connect to Odoo server: '),
    'timeout': chain(TimeoutError('BACKEND_TIMEOUT: timed out'), ConnectionError, 'Failed to connect to Odoo server: '),
    'http 401': chain(ValueError('BACKEND_HTTP_ERROR status=401: Unauthorized')),
    'busy': ValueError('BACKEND_BUSY'),
    'cycle': cycle,
    'text only': ValueError('Authentication failed: Invalid username or password?'),
}
print(json.dumps({name: launch.probe_failure(exc) for name, exc in cases.items()}))
'''
    finished = subprocess.run(
        [str(ROOT / 'apps/odoo/.venv/bin/python'), '-B', '-c', script], cwd=ROOT / 'apps/odoo', capture_output=True, text=True,
        env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': f'{ROOT / "apps/runtime"}:{ROOT / "apps/odoo"}', 'PYTHONDONTWRITEBYTECODE': '1'},
        timeout=30, check=False)
    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == {
        'false uid': AUTH, 'denied 3': AUTH, 'denied old': AUTH, 'denied traceback': AUTH, 'database missing': AUTH,
        'database down': UNAVAILABLE, 'other fault': UNAVAILABLE, 'connect': UNAVAILABLE, 'timeout': UNAVAILABLE,
        'http 401': UNAVAILABLE, 'busy': UNAVAILABLE, 'cycle': UNAVAILABLE, 'text only': UNAVAILABLE}
