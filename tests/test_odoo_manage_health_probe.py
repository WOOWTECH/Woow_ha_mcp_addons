"""Odoo Manage readiness probe (0.1.4): a fresh connection authenticates on its own thread; never public.

0.1.3 HA regression: the probe was list_models, which needs ir.model read access, so the least-privilege test
account always read as unreachable (8081 readiness 503) although every read worked. Genuine pinned Odoo Manage
child, owned fake XMLRPC backend, real HealthMonitor and gateway.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import asyncio
import json
import xmlrpc.client

import httpx
import pytest

from owned_runtime import Endpoint
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec, health_probe
from test_b2_odoo_runtime import initialize
from test_expansion_policy import call
from test_real_products import connection, rpc


@contextmanager
def fake_odoo(module=False):
    """Like the HA test account: authenticates, but has no ir.model access. module: the Odoo MCP module's endpoints
    (standard mode, API key validated by GET /mcp/auth/validate) instead of plain XMLRPC (YOLO read mode)."""
    calls, failures = [], []
    state = {'deny': False, 'offline': False, 'hold': None, 'started': threading.Event(), 'release': threading.Event()}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def held(self, name):
            with lock:  # hold only the first matching request after arming (a slow Odoo)
                hit = state['hold'] == name
                if hit:
                    state['hold'] = None
            if hit:
                state['started'].set()
                assert state['release'].wait(20)

        def reply_json(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if state['offline']:
                self.send_error(503); return
            try:
                assert module and self.headers.get('X-API-Key') == 'DUMMY', self.path
                assert self.headers.get('X-Odoo-Database') == 'test'
                calls.append('GET ' + self.path)
                if self.path == '/mcp/auth/validate':
                    self.reply_json({'success': True, 'data': {'valid': not state['deny'], 'user_id': 7}})
                elif self.path == '/mcp/models':
                    self.reply_json({'success': True, 'data': {'models': []}})
                else:
                    self.send_error(404)
            except Exception as exc:
                failures.append(repr(exc))
                self.send_error(400)

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if state['offline']:
                self.send_error(503); return
            try:
                assert self.path.startswith('/mcp/xmlrpc/' if module else '/xmlrpc/2/'), self.path
                params, method = xmlrpc.client.loads(body)
                self.held(method)
                calls.append(method if method != 'execute_kw' else 'execute_kw ' + '.'.join(params[3:5]))
                if method == 'version':
                    value = {'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]}
                elif method == 'authenticate':
                    assert params[:3] == ('test', 'tester', 'DUMMY'), params[:3]
                    value = False if state['deny'] else 7
                else:
                    assert method == 'execute_kw', method
                    raise xmlrpc.client.Fault(4, 'AccessError')
                data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
            except xmlrpc.client.Fault as exc:
                data = xmlrpc.client.dumps(exc).encode()
            except Exception as exc:
                failures.append(repr(exc))
                data = xmlrpc.client.dumps(xmlrpc.client.Fault(1, 'fake assertion')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls, failures, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize('module', [False, True], ids=['yolo-read', 'module'])
async def test_odoo_manage_probe_authenticates_on_a_fresh_connection(tmp_path, module):
    with fake_odoo(module) as (url, calls, failures, state):
        store = ProductStore(tmp_path / 'state', 'odoo-manage')
        store.update(connection={**connection('odoo-manage', url), **({'mode': 'module'} if module else {})})
        endpoint = Endpoint('odoo-manage')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                health = HealthMonitor(store, process, child, child_url=endpoint.url)
                _, app = make_apps(store, TOOLS['odoo-manage'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    await initialize(client, headers)

                    # Reachable without ir.model access: the probe's own connection checks and authenticates, nothing else.
                    before = len(calls)
                    await health.check()
                    expected = ['version', 'GET /mcp/auth/validate'] if module else ['version', 'authenticate']
                    assert health.backend == 'reachable' and calls[before:] == expected, calls[before:]

                    # The probe runs off the child's event loop (RC review #4, mutant LM4): while a slow Odoo holds
                    # it, the child still answers.
                    state['started'].clear(); state['release'].clear(); state['hold'] = 'version'
                    probe = asyncio.create_task(health.check())
                    try:
                        assert await asyncio.to_thread(state['started'].wait, 10)
                        async with asyncio.timeout(2):
                            assert await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}) == {}
                    finally:
                        state['release'].set()
                    await probe
                    assert health.backend == 'reachable'

                    # Private: never listed or dispatched through the gateway.
                    name, arguments = health_probe('odoo-manage')
                    assert name not in TOOLS['odoo-manage']
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    assert name not in {t['name'] for t in listed['tools']}
                    before = len(calls)
                    assert (await client.post('/mcp', headers=headers, json=call(name, arguments))).status_code == 403
                    assert len(calls) == before

                    # Rejected credentials and an unavailable backend are not reachable; recovery is.
                    state['deny'] = True
                    await health.check()
                    assert health.backend == 'unreachable'
                    state['deny'] = False
                    state['offline'] = True
                    await health.check()
                    assert health.backend == 'unreachable'
                    state['offline'] = False
                    await health.check()
                    assert health.backend == 'reachable'
                    assert not failures, failures
        finally:
            await process.stop()
            store.close()
