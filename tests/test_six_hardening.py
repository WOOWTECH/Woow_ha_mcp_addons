"""Actual pinned children; only owned backends. conftest owns the port lock."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
import time
import xmlrpc.client

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from owned_runtime import Endpoint
from mcp_admin_core.products import PRODUCTS, PROBES, ProductStore, TOOLS, child_spec
from test_real_products import connection, rpc
import nextcloud_fixtures


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown(); server.server_close(); thread.join()


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def reply(self, payload, status=200):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


@asynccontextmanager
async def runtime(tmp_path, product, url, *, canary=None, json_response=False, write_grants=()):
    store = ProductStore(tmp_path / 'state', product)
    configured = connection(product, url)
    if canary:
        for key in ('password', 'api_key', 'api_secret', 'master_key', 'gateway_api_key', 'dashboard_password', 'app_password'):
            if key in configured:
                configured[key] = canary
    store.update(connection=configured, enabled_write_tools=list(write_grants))
    spec = child_spec(store.load(), store.directory)
    if json_response:
        # Test-only stock FastMCP option. No executable/admin bypass added.
        spec.env['FASTMCP_JSON_RESPONSE'] = 'true'
    endpoint = Endpoint(product)
    manager = endpoint.supervisor(spec)
    try:
        await manager.start()
        async with endpoint.client(timeout=15) as child:
            _, app = make_apps(store, TOOLS[product], child, child_url=endpoint.url)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary', timeout=15) as client:
                headers = {'Authorization': 'Bearer ' + store.load().token,
                           'Accept': 'application/json, text/event-stream'}
                init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-03-26', 'capabilities': {},
                    'clientInfo': {'name': 'hardening', 'version': '0'}}}
                for _ in range(100):
                    try:
                        await rpc(client, '/mcp', headers, init)
                        break
                    except (httpx.HTTPError, ValueError):
                        await asyncio.sleep(.1)
                else:
                    raise AssertionError('child not ready')
                await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                yield client, headers, store, manager, child
    finally:
        pid = manager.process.pid if manager.process else None
        await manager.stop()
        endpoint.close()
        store.close()
        if pid:
            assert not Path(f'/proc/{pid}').exists()


def call(name, arguments=None, id=2):
    return {'jsonrpc': '2.0', 'id': id, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments or {}}}


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
@pytest.mark.parametrize('location', ['cross-origin', 'same-origin', 'relative'])
async def test_odoo_never_replays_redirect(tmp_path, status, location):
    captured = []

    class Sink(Quiet):
        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            captured.append((method, params))
            value = 7 if method == 'authenticate' else ([1] if params[4] == 'search' else [{'model': 'res.partner'}])
            self.reply(xmlrpc.client.dumps((value,), methodresponse=True).encode())

    with serve(Sink) as sink:
        class Source(Sink):
            def do_POST(self):
                if self.path == '/capture':
                    return super().do_POST()
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(status)
                target = sink + '/capture' if location == 'cross-origin' else source + '/capture' if location == 'same-origin' else '/capture'
                self.send_header('location', target)
                self.send_header('Content-Length', '0')
                self.end_headers()

        with serve(Source) as source:
            async with runtime(tmp_path, 'odoo', source) as (client, headers, store, manager, child):
                result = await rpc(client, '/mcp', headers, call('list_models', {'limit': 1}))
                assert not captured, 'password-bearing XMLRPC body replayed'
                assert 'res.partner' not in json.dumps(result)
                from mcp_admin_core.health import HealthMonitor
                monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
                await monitor.check()
                assert monitor.backend == 'unreachable'
                assert not captured, 'health probe replayed redirect'


@pytest.mark.parametrize('product,json_response', [(p, False) for p in PRODUCTS] + [('litellm', True)])
async def test_error_bodies_never_enter_gateway_stream(tmp_path, product, json_response):
    mode = {'status': 200, 'shape': 'detail'}
    canary = 'DUMMY-CREDENTIAL-ECHO-CANARY'
    calls = []

    class Backend(Quiet):
        def do_GET(self):
            if product == 'nextcloud':
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.path == nextcloud_fixtures.OCS_PATH:  # account lookup succeeds: the tool's own request fails
                    return nextcloud_fixtures.respond(self, 200, {'Content-Type': 'application/json'},
                                                      b'{"ocs": {"data": {"id": "tester"}}}')
            calls.append(self.path)
            payload = {'detail': canary} if mode['shape'] == 'detail' else {'error': {'message': canary, 'nested': {'key': canary}}} if mode['shape'] == 'nested' else canary.encode()
            self.reply(payload, mode['status'])

        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(method)
            if mode['status'] != 200:
                if mode['shape'] == 'nested':
                    self.reply(xmlrpc.client.dumps(xmlrpc.client.Fault(1, canary)).encode())
                else:
                    self.reply({'detail': canary}, mode['status'])
                return
            value = {'server_version': '18.0', 'server_version_info': [18,0,0,'final',0]} if method == 'version' else 7 if method == 'authenticate' else [{'model': 'res.partner', 'name': 'Contact'}]
            self.reply(xmlrpc.client.dumps((value,), methodresponse=True).encode())

        do_PROPFIND = do_GET

    with serve(Backend) as url:
        async with runtime(tmp_path, product, url, canary=canary, json_response=json_response) as (client, headers, *_):
            name, arguments = PROBES[product]
            for status in (401, 403, 422, 500, 503):
                for shape in ('detail', 'text', 'nested'):
                    mode.update(status=status, shape=shape)
                    before = len(calls)
                    response = await client.post('/mcp', headers=headers, json=call(name, arguments))
                    assert response.status_code == 200
                    if json_response:
                        assert response.headers['content-type'].startswith('application/json')
                    else:
                        assert response.headers['content-type'].startswith('text/event-stream')
                    # Entire raw JSON/SSE: includes text, structuredContent and any notifications.
                    assert canary not in response.text, response.text
                    assert len(response.content) < 4096
                    assert 'BACKEND_' in response.text, response.text
                    assert len(calls) > before


@pytest.mark.parametrize('product,capacity', [('opendesign', 4), ('odoo', 1)])
async def test_slow_backend_does_not_starve_protocol(tmp_path, product, capacity):
    entered, release = threading.Event(), threading.Event()
    active = 0
    peak = 0
    lock = threading.Lock()

    class Slow(Quiet):
        def wait_backend(self):
            nonlocal active, peak
            with lock:
                active += 1; peak = max(peak, active)
            entered.set()
            release.wait(8)
            with lock:
                active -= 1

        def do_GET(self):
            self.wait_backend()
            self.reply({'status': 'ok'})

        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.wait_backend()
            value = 7 if method == 'authenticate' else [1] if params[4] == 'search' else [{'model': 'res.partner'}]
            self.reply(xmlrpc.client.dumps((value,), methodresponse=True).encode())

    with serve(Slow) as url:
        try:
            async with runtime(tmp_path, product, url) as (client, headers, store, manager, child):
                name, args = PROBES[product]
                tasks = [asyncio.create_task(rpc(client, '/mcp', headers, call(name, args, id=10+i))) for i in range(10)]
                try:
                    assert await asyncio.to_thread(entered.wait, 3)
                    started = time.monotonic()
                    assert await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 50, 'method': 'ping'}) == {}
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 51, 'method': 'tools/list'})
                    assert listed['tools']
                    assert time.monotonic() - started < .75
                    await asyncio.sleep(.2)
                    assert peak <= capacity
                    completed = [t.result() for t in tasks if t.done()]
                    assert len(completed) >= 10-capacity
                    assert all('BACKEND_BUSY' in json.dumps(item) for item in completed)
                    from mcp_admin_core.health import HealthMonitor
                    monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
                    await monitor.check()
                    assert monitor.backend == 'unreachable'
                    if product == 'odoo':
                        # 0.1.3: Odoo's probe has its own owned thread, never the full tool worker, so the hung
                        # backend sees one more call and the probe fails by the monitor's timeout, not BACKEND_BUSY.
                        assert peak == capacity + 1
                    else:
                        assert peak <= capacity
                    assert manager.starts == 1
                    pid = manager.process.pid
                    started = time.monotonic()
                    await manager.stop()  # backend still hung; owned group deadline
                    assert time.monotonic() - started < 5
                    assert not Path(f'/proc/{pid}').exists()
                finally:
                    release.set()
                    for task in tasks: task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            release.set()


def test_emqx_health_count_consistency():
    from mcp_admin_core.products import probe_success
    node = {'node': 'emqx@local', 'version': '5.fake'}
    assert probe_success('emqx', {'node_count': 1, 'nodes': [node]})
    for count, nodes in ((0, []), (True, [node]), (2, [node]), (1, []), (2, [node, node])):
        assert not probe_success('emqx', {'node_count': count, 'nodes': nodes})


async def test_emqx_real_health_requires_node_evidence(tmp_path):
    from mcp_admin_core.health import HealthMonitor
    response = {'value': {'success': True}}
    class Nodes(Quiet):
        def do_GET(self):
            assert self.path == '/api/v5/nodes'
            self.reply(response['value'])
    with serve(Nodes) as url:
        async with runtime(tmp_path, 'emqx', url) as (_, _, store, manager, child):
            monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
            _, app = make_apps(store, TOOLS['emqx'], child, health=monitor.snapshot, child_url=manager.endpoint.url)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                good = {'node': 'emqx@local', 'version': '5.fake'}
                for value in ({'success': True}, {}, {'error': 'offline'}, [], [None], [{}],
                              [{'node': 7, 'version': '5'}], [{'node': 'emqx@local'}],
                              [{'node': name, 'version': '5'} for name in ('@', 'emqx@', '@local', 'emqx@@local', ' emqx@local')],
                              [good, good], [{'node': 'emqx@local', 'version': '5', 'error': 'offline'}],
                              {'node_count': 1, 'nodes': []}, b'not-json'):
                    response['value'] = value
                    await monitor.check()
                    assert monitor.backend == 'unreachable', value
                    assert (await client.get('/health/ready')).status_code == 503
                    assert manager.ready and manager.starts == 1
                response['value'] = [good]
                await monitor.check()
                assert monitor.backend == 'reachable'
                assert (await client.get('/health/ready')).status_code == 200


async def test_hermes_dashboard_login_and_cookie_errors_are_safe(tmp_path):
    mode = {'login_error': True, 'status': 401}
    canary = 'DUMMY-DASHBOARD-SECRET-CANARY'
    cookies = []
    class Dashboard(Quiet):
        def do_POST(self):
            assert self.path == '/auth/password-login'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert payload['password'] == canary
            if mode['login_error']:
                self.reply({'detail': payload['password']}, mode['status'])
            else:
                self.send_response(200)
                self.send_header('Set-Cookie', f'hermes_session_at={canary}')
                self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
        def do_GET(self):
            assert self.path == '/api/status'
            cookies.append(self.headers['Cookie'])
            assert canary in cookies[-1]
            self.reply({'error': {'message': self.headers['Cookie']}}, mode['status'])
    with serve(Dashboard) as url:
        async with runtime(tmp_path, 'hermes', url, canary=canary) as (client, headers, *_):
            for phase in (True, False):
                mode['login_error'] = phase
                for status in (401, 403, 422, 500):
                    mode['status'] = status
                    response = await client.post('/mcp', headers=headers, json=call('hermes_inspect', {'target': 'status'}))
                    assert canary not in response.text
                    assert f'BACKEND_HTTP_ERROR status={status}' in response.text
            assert len(cookies) == 4
