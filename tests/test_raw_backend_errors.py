"""0.2.0 (owner decision 2026-10-15): backend errors reach the client with the backend's own text, as the PaaS servers
answer them (e.g. Odoo's AccessError message; it was a fixed code such as BACKEND_RPC_FAULT before). Every credential the
add-on holds (the add-on and child tokens, backend keys and passwords, their Basic Authorization forms) is replaced with
[REDACTED] in every reply the gateway relays. LOCAL/MOCK backends only.
"""
import asyncio
import base64
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import xmlrpc.client

import httpx
import pytest

from mcp_admin_core import redact
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductState, ProductStore, TOOLS, child_spec
from owned_runtime import Endpoint
from test_expansion_policy import call
from test_odoo_read_exists import initialize
from test_real_products import rpc

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'odoo-Secret-4711'
spec = importlib.util.spec_from_file_location('backend_policy_raw', ROOT / 'apps/runtime/backend_policy.py')
backend_policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_policy)


def state(product, connection, **changes):
    return ProductState(product=product, token='T' * 43, child_token='C' * 43, connection=connection, **changes)


def test_secret_values_cover_tokens_connection_secrets_and_basic_forms():
    nextcloud = state('nextcloud', {'url': 'https://cloud.example.test', 'username': 'alice', 'app_password': 'app-pass-123'})
    values = redact.secret_values(nextcloud)
    basic = base64.b64encode(b'alice:app-pass-123').decode()
    assert {'T' * 43, 'C' * 43, 'app-pass-123', basic, basic.rstrip('=')} <= set(values)
    assert 'alice' not in values  # a user name is not a credential
    emqx = state('emqx', {'url': 'https://emqx.example.test', 'api_key': 'key-1234', 'api_secret': 'secret-5678'})
    assert base64.b64encode(b'key-1234:secret-5678').decode() in redact.secret_values(emqx)
    assert list(redact.secret_values(emqx)) == sorted(redact.secret_values(emqx), key=len, reverse=True)
    short = state('odoo', {'url': 'https://odoo.example.test', 'database': 'db', 'username': 'u', 'password': 'abc'})
    assert 'abc' not in redact.secret_values(short)  # too short to replace in ordinary text


def test_redact_secrets_walks_every_string_of_a_json_value():
    value = {'content': [{'type': 'text', 'text': 'denied for odoo-Secret-4711 (Bearer ' + 'T' * 43 + ')'}],
             'odoo-Secret-4711': ['x', 1, None, True], 'structuredContent': {'error': 'odoo-Secret-4711'}}
    clean = redact.redact_secrets(value, (PASSWORD, 'T' * 43))
    text = json.dumps(clean)
    assert PASSWORD not in text and 'T' * 43 not in text and text.count('[REDACTED]') == 4
    assert clean['[REDACTED]'] == ['x', 1, None, True]


def test_backend_error_text_keeps_the_backend_text():
    assert backend_policy.backend_error_text(httpx.ConnectError('[Errno 111] Connection refused')) == \
        'BACKEND_UNAVAILABLE: [Errno 111] Connection refused'
    assert backend_policy.backend_error_text(ValueError('AccessError: not allowed')) == \
        'BACKEND_INVALID_RESPONSE: AccessError: not allowed'
    assert backend_policy.backend_error_text(httpx.TimeoutException('BACKEND_TIMEOUT: read timed out')) == \
        'BACKEND_TIMEOUT: read timed out'
    failure = backend_policy.BackendFailure(RuntimeError('boom'))
    assert str(failure) == 'BACKEND_UNAVAILABLE: boom' and backend_policy.backend_error_text(failure) == str(failure)
    assert backend_policy.public_backend_error(ValueError('x')) == 'BACKEND_INVALID_RESPONSE'  # the code-only hook


async def test_gateway_redacts_credentials_in_results_and_errors(tmp_path):
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection={'url': 'https://odoo.example.test', 'database': 'db', 'username': 'u', 'password': PASSWORD})
        token = store.load().token
        child_token = store.load().child_token

        def child(request):
            message = json.loads(request.content)
            leak = f'login failed for password {PASSWORD}, token {token}, child {child_token}'
            if message['params']['name'] == 'read_record':
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {
                    'content': [{'type': 'text', 'text': leak}], 'isError': True}})
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'],
                                             'error': {'code': -32000, 'message': leak, 'data': {'detail': leak}}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
            _, app = make_apps(store, TOOLS['odoo'], to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
                headers = {'Authorization': 'Bearer ' + token, 'Mcp-Session-Id': 'child-session',
                           'Accept': 'application/json, text/event-stream'}
                for name in ('read_record', 'search_records'):
                    response = await client.post('/mcp', headers=headers, json=call(name, {'model': 'res.partner'}))
                    assert response.status_code == 200
                    text = response.text
                    assert PASSWORD not in text and token not in text and child_token not in text
                    assert 'login failed for password [REDACTED], token [REDACTED], child [REDACTED]' in text


@contextmanager
def faulting_odoo():
    """Authenticates, then answers every read with Odoo's own AccessError fault (which echoes the password)."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(method)
            if method == 'version':
                data = xmlrpc.client.dumps(({'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]},),
                                           methodresponse=True, allow_none=True)
            elif method == 'authenticate':
                data = xmlrpc.client.dumps((7,), methodresponse=True, allow_none=True)
            else:
                data = xmlrpc.client.dumps(xmlrpc.client.Fault(
                    4, f'AccessError: You are not allowed to access Contact (res.partner) records. ({PASSWORD})'))
            body = data.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def test_real_odoo_child_relays_the_access_error_text(tmp_path):
    with faulting_odoo() as (url, calls):
        store = ProductStore(tmp_path / 'state', 'odoo')
        store.update(connection={'url': url, 'database': 'test', 'username': 'tester', 'password': PASSWORD})
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _, app = make_apps(store, TOOLS['odoo'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    await initialize(client, headers)
                    # execute_method reports the failure as odoo-mcp does: {"success": false, "error": str(e)}.
                    reply = await rpc(client, '/mcp', headers, call(
                        'execute_method', {'model': 'res.partner', 'method': 'search_read', 'args': [[]]}))
                    text = json.dumps(reply)
                    assert 'You are not allowed to access Contact (res.partner) records.' in text, text
                    assert PASSWORD not in text and '[REDACTED]' in text
                    assert 'BACKEND_RPC_FAULT' not in text
                    assert 'execute_kw' in calls
        finally:
            await process.stop()
            endpoint.close()
            store.close()


@contextmanager
def refusing_litellm(master):
    """Answers every request 400 with LiteLLM's own error envelope, which echoes the master key."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_any(self):
            self.rfile.read(int(self.headers.get('Content-Length') or 0))
            body = json.dumps({'error': {'message': f'team_alias Owned already exists (auth {master})',
                                         'type': 'bad_request_error'}}).encode()
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = handle_any

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def test_real_litellm_child_relays_the_backend_error_body(tmp_path):
    master = 'sk-master-Owned-0815'
    with refusing_litellm(master) as url:
        store = ProductStore(tmp_path / 'state', 'litellm')
        store.update(connection={'url': url, 'master_key': master})
        endpoint = Endpoint('litellm')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _, app = make_apps(store, TOOLS['litellm'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    await initialize(client, headers)
                    reply = await rpc(client, '/mcp', headers, call('litellm_create_team', {'team_alias': 'Owned'}))
                    text = json.dumps(reply)
                    # The upstream server's own 400 message with LiteLLM's body (it was BACKEND_HTTP_ERROR status=400).
                    assert reply.get('isError') is True and 'team_alias Owned already exists' in text, text
                    assert master not in text and '[REDACTED]' in text
        finally:
            await process.stop()
            endpoint.close()
            store.close()
