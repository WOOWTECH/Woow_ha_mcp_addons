"""Real six child environments + real boundary + disposable fake HTTP/XML-RPC.

The session conftest holds the documented port-3000 lock. No live credentials.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import xmlrpc.client

import httpx
import pytest

from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import PRODUCTS, PROBES, ProductStore, TOOLS, child_spec

ROOT = Path(__file__).resolve().parents[1]


def connection(product, url):
    return {
        'odoo': dict(url=url, database='test', username='tester', password='DUMMY'),
        'odoo-manage': dict(url=url, database='test', username='tester', api_key='DUMMY'),
        'hermes': dict(gateway_url=url, gateway_api_key='DUMMY', dashboard_url=url,
                       dashboard_username='tester', dashboard_password='DUMMY'),
        'opendesign': dict(url=url),
        'emqx': dict(url=url, api_key='DUMMY', api_secret='DUMMY'),
        'litellm': dict(url=url, master_key='DUMMY'),
    }[product]


@contextmanager
def backend(product):
    calls = []
    offline = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def respond(self, value, content_type='application/json'):
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            calls.append(('GET', self.path))
            if offline.is_set():
                self.send_error(503); return
            if product == 'emqx':
                assert self.headers.get('Authorization') == 'Basic RFVNTVk6RFVNTVk='
            if product in ('hermes', 'litellm') and self.path in ('/v1/models', '/v1/capabilities'):
                assert self.headers.get('Authorization') == 'Bearer DUMMY'
            values = {'/v1/capabilities': {'models': []}, '/api/health': {'status': 'ok'},
                      '/api/v5/nodes': [{'node': 'fake@local', 'version': '5.fake'}],
                      '/v1/models': {'data': [{'id': 'fake-model'}]}}
            if self.path not in values:
                self.send_error(404); return
            self.respond(values[self.path])

        def do_DELETE(self):
            calls.append(('DELETE', self.path))
            assert product == 'opendesign'
            assert self.path == '/api/projects/12345678-1234-1234-1234-123456789abc'
            self.respond({'deleted': True})

        def do_POST(self):
            data = self.rfile.read(int(self.headers['Content-Length']))
            if offline.is_set():
                self.send_error(503); return
            if not self.path.startswith('/xmlrpc/2/'):
                calls.append(('UNEXPECTED_POST', self.path)); self.send_error(400); return
            params, method = xmlrpc.client.loads(data)
            calls.append(('XMLRPC', method, params[3:5] if method == 'execute_kw' else ()))
            if method == 'version':
                result = {'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]}
            elif method == 'authenticate':
                assert params[:3] == ('test', 'tester', 'DUMMY')
                result = 7
            elif method == 'execute_kw':
                assert params[:3] == ('test', 7, 'DUMMY')
                model, operation = params[3:5]
                assert model == 'ir.model', (model, operation)
                assert operation in ('search', 'read', 'search_read'), operation
                result = [1] if operation == 'search' else [{'id': 1, 'model': 'res.partner', 'name': 'Contact'}]
            else:
                raise AssertionError(method)
            self.respond(xmlrpc.client.dumps((result,), methodresponse=True, allow_none=True).encode(), 'text/xml')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls, offline
    finally:
        server.shutdown(); server.server_close(); thread.join()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def rpc(client, url, headers, message):
    async with client.stream('POST', url, headers=headers, json=message) as response:
        if response.headers.get('mcp-session-id'):
            headers['Mcp-Session-Id'] = response.headers['mcp-session-id']
        if 'id' not in message:
            assert response.status_code in (200, 202, 204)
            return None
        return await protocol_reply(response, message['id'])


@pytest.mark.parametrize('product', PRODUCTS)
async def test_real_child_fake_backend_and_boundary(tmp_path, product):
    # Refuse to take over an unrelated listener, even with cooperative lock.
    with socket.socket() as check:
        # Match Uvicorn's reuse setting: TIME_WAIT isn't a live listener.
        # SO_REUSEADDR still refuses a bound/listening foreign TCP server.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(('127.0.0.1', 3000))
    with backend(product) as (url, calls, offline):
        store = ProductStore(tmp_path / 'state', product)
        store.update(connection=connection(product, url))
        state = store.load()
        spec = child_spec(state, store.directory)
        assert 'SUPERVISOR_TOKEN' not in spec.env and state.token not in spec.env.values()
        assert spec.cwd != store.directory and not list(spec.cwd.iterdir())
        store.close()
        port, admin_port = free_port(), free_port()
        endpoint = f'http://127.0.0.1:{port}/mcp'
        log_path = tmp_path / 'owned-runtime.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-m', 'mcp_admin_core.run_product', product,
                '--data', str(tmp_path / 'state'), '--host', '127.0.0.1', '--mcp-port', str(port), '--admin-port', str(admin_port)],
                cwd=ROOT, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core'),
                'PYTHONDONTWRITEBYTECODE': '1', 'SUPERVISOR_TOKEN': 'DUMMY-parent-must-not-inherit'},
                stdout=log, stderr=log)
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                    headers = {'Authorization': 'Bearer ' + state.token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'local-test', 'version': '0'}}}
                    started = time.monotonic()
                    last = None
                    while time.monotonic() - started < 25:
                        assert process.poll() is None, log_path.read_text()
                        try:
                            result = await rpc(client, endpoint, headers, init)
                            break
                        except (httpx.HTTPError, ValueError) as exc:
                            last = type(exc).__name__
                            await asyncio.sleep(.25)
                    else:
                        pytest.fail(f'{product}: initialization timed out ({last}); {log_path.read_text()}')
                    assert result['capabilities'] == {'tools': {}}
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, endpoint, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    listed = await rpc(client, endpoint, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    expected = {n for n, t in TOOLS[product].items() if not t.write}
                    assert {t['name'] for t in listed['tools']} == expected
                    # Same real child session, bypass ONLY for observing upstream inventory.
                    # Public requests still go through the authenticated boundary above.
                    raw_list = await rpc(client, 'http://127.0.0.1:3000/mcp', headers,
                        {'jsonrpc': '2.0', 'id': 20, 'method': 'tools/list'})
                    upstream_names = {t['name'] for t in raw_list['tools']}
                    manifest = json.loads((ROOT / 'docs/tool-surface.json').read_text())
                    inventoried = {t['name'] for t in manifest['products'][product]['tools']}
                    assert expected <= upstream_names <= inventoried
                    print(f'LOCAL {product}: raw runtime list {len(upstream_names)}; AST universe {len(inventoried)}')
                    name, arguments = PROBES[product]
                    reply = await rpc(client, endpoint, headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': arguments}})
                    assert not reply.get('isError'), reply
                    texts = [json.loads(t['text']) for t in reply['content'] if t['type'] == 'text']
                    from mcp_admin_core.products import probe_success
                    assert any(probe_success(product, text) for text in texts), texts
                    assert calls, 'no real backend call'
                    before = len(calls)
                    for denied in ('resources/list', 'resources/read', 'prompts/list', 'tasks/get'):
                        response = await client.post(endpoint, headers=headers, json={'jsonrpc': '2.0', 'id': 4, 'method': denied})
                        assert response.status_code == 403
                    for denied in ('unknown', 'hermes_chat', 'delete_project', 'emqx_publish', 'litellm_chat_completion', 'execute_method'):
                        response = await client.post(endpoint, headers=headers, json={'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': denied, 'arguments': {}}})
                        assert response.status_code == 403
                    for auth in ({}, {'Authorization': 'Bearer wrong'}):
                        response = await client.post(endpoint, headers=auth, json=init)
                        assert response.status_code == 401
                    assert len(calls) == before
                    assert (await client.get(f'http://127.0.0.1:{admin_port}/api/bootstrap', headers={'x-remote-user-id': 'admin'})).status_code == 403
                    # Health reads run every 15 seconds, not a backend-triggered restart.
                    async with asyncio.timeout(20):
                        while (await client.get(f'http://127.0.0.1:{port}/health/ready')).status_code != 200:
                            await asyncio.sleep(.25)
                    children_path = Path(f'/proc/{process.pid}/task/{process.pid}/children')
                    child_pids = children_path.read_text().split()
                    assert len(child_pids) == 1
                    offline.set()
                    async with asyncio.timeout(22):
                        while (await client.get(f'http://127.0.0.1:{port}/health/ready')).status_code != 503:
                            await asyncio.sleep(.25)
                    assert process.poll() is None
                    assert children_path.read_text().split() == child_pids, 'backend outage restarted child'
                    pong = await rpc(client, endpoint, headers, {'jsonrpc': '2.0', 'id': 6, 'method': 'ping'})
                    assert pong == {}
                    await client.delete(endpoint, headers=headers)
                    assert not any(c[0] == 'UNEXPECTED_POST' for c in calls)
                    print(f'LOCAL {product}: initialize/list/read/auth/denial/outage; {len(calls)} fake backend requests')
            finally:
                process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.to_thread(process.wait, 10)
                except subprocess.TimeoutExpired:
                    process.kill(); await asyncio.to_thread(process.wait)
            assert process.returncode == 0, log_path.read_text()
            assert all(not Path('/proc/' + pid).exists() for pid in child_pids), 'orphan child'
