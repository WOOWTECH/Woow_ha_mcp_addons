"""Real pinned writer error paths; invented keys reflected by OWNED backends only."""
import json
import socket
import threading
import xmlrpc.client
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from batch2_owned_port import private_spec, reserve_port, request_guard, wait_owned_listener
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from n8n_adapter import TOOLS as N8N_TOOLS, child_spec as n8n_spec
from test_batch2_policy import GRAPH
from test_expansion_policy import call
from test_expansion_runtime import payload
from test_real_products import connection, rpc

KEY = 'OWNED_DUMMY_BACKEND_KEY_NOT_A_REAL_CREDENTIAL'
CANARY = 'OWNED_PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE'


@contextmanager
def writer_backend(product):
    state = {'case': 'exact', 'posts': [], 'commits': [], 'received_keys': [], 'failures': []}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            try:
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                case = state['case']
                status, mime = 200, 'application/json'
                if product == 'n8n':
                    assert (self.command, self.path) == ('POST', '/api/v1/workflows')
                    key = self.headers['X-N8N-API-KEY']
                    state['posts'].append(json.loads(raw))
                    state['received_keys'].append(key)
                    private = {'message': CANARY, 'diagnostics': {'received_backend_key': key}}
                    if case == 'exact':
                        status, value = 400, private
                    elif isinstance(case, int):
                        status, value = case, private
                    elif case == 'settings-fallback':
                        if 'saveExecutionProgress' in state['posts'][-1]['settings']:
                            status, value = 400, {**private,
                                'message': "body/settings Unrecognized key(s) in object: 'saveExecutionProgress' " + CANARY}
                        else:
                            state['commits'].append(case)
                            status, value = 500, private
                    elif case == 'text':
                        status, value = 400, CANARY + key
                    elif case == 'forbidden-publish':
                        status, value = 403, {**private, 'reason': 'insufficient_api_key_scope', 'versionId': key}
                    else:
                        # A response failure does NOT imply the POST had no effect.
                        state['commits'].append(case)
                        value = {'id': 'owned1', 'name': 'Owned draft', 'active': False,
                                 'nodes': [{}, {}], 'private': private}
                        if case == 'late-500':
                            status, value = 500, private
                        elif case == 'active':
                            value['active'] = True
                        elif case == 'missing-id':
                            del value['id']
                        elif case == 'null':
                            value = None
                        elif case == 'disconnect':
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            return
                    data = (value.encode() if case == 'text' else json.dumps(value).encode())
                elif '/xmlrpc/' in self.path:
                    params, method = xmlrpc.client.loads(raw)
                    if method == 'version':
                        value = {'server_version': '19.0', 'server_version_info': [19, 0, 0, 'final', 0]}
                    elif method == 'authenticate':
                        value = 7
                    else:
                        assert method == 'execute_kw' and params[3:5] == ('res.partner', 'message_post')
                        key = params[2]
                        state['received_keys'].append(key)
                        state['posts'].append(params[5:])
                        private = {'unexpected_private_response': CANARY, 'received_backend_key': key}
                        if case == 'fault':
                            value = xmlrpc.client.Fault(1, json.dumps(private))
                        else:
                            state['commits'].append(case)
                            value = {'exact': private, 'list': [private], 'text': CANARY + key,
                                     'null': None, 'true': True, 'false': False, 'zero': 0,
                                     'negative': -1, 'overflow': 2147483648, 'float': 2.5,
                                     'list-bool': [True], 'empty-list': [], 'list-extra': [2, private],
                                     'list-zero': [0], 'positive': 2, 'positive-list': [3]}[case]
                    # XML-RPC supports decoding i8 but the stdlib writer limits ints to i4.
                    if value == 2147483648:
                        data = b'<methodResponse><params><param><value><i8>2147483648</i8></value></param></params></methodResponse>'
                    else:
                        data = xmlrpc.client.dumps(value if isinstance(value, xmlrpc.client.Fault) else (value,),
                                                   methodresponse=True, allow_none=True).encode()
                    mime = 'text/xml'
                else:
                    assert self.headers['X-API-Key'] == KEY
                    if self.path == '/mcp/auth/validate':
                        detail = {'valid': True, 'user_id': 7}
                    else:
                        assert self.path == '/mcp/models/res.partner/access'
                        detail = {'model': 'res.partner', 'enabled': True,
                                  'operations': {op: True for op in ('read', 'create', 'write', 'unlink')}}
                    data = json.dumps({'success': True, 'data': detail}).encode()
                self.send_response(status)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                state['failures'].append(type(exc).__name__)
                raise

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    assert server.server_port != 3000
    server.daemon_threads = True
    server.timeout = .05
    stop = threading.Event()
    def serve():
        while not stop.is_set():
            server.handle_request()
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        stop.set()
        thread.join(2)
        server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize('product', ['n8n', 'odoo-manage'])
async def test_writer_errors_real_owned_runtime(tmp_path, product):
    with writer_backend(product) as (url, state):
        name = 'n8n_create_workflow' if product == 'n8n' else 'post_message'
        store = ProductStore(tmp_path / product, product)
        if product == 'n8n':
            store.update(backend_url=url, backend_key=KEY)
        else:
            store.update(connection={**connection(product, url), 'api_key': KEY, 'mode': 'module'})
        spec = (n8n_spec if product == 'n8n' else child_spec)(store.load(), store.directory)
        process = Supervisor(spec, retries=0)
        reservation = reserve_port()
        port = reservation.getsockname()[1]
        dispatches, wire = [], []
        async def dispatched(request):
            dispatches.append(request.method)
        async def capture(response):
            wire.append(await response.aread())
        try:
            process.spec = private_spec(spec, product, port)
            reservation.close()
            await process.start()
            proof = await wait_owned_listener(process, port)
            print('B1_WRITER_OWNED', product, port, *proof)
            async with httpx.AsyncClient(trust_env=False, timeout=8, event_hooks={
                    'request': [request_guard(process, port, proof), dispatched]}) as child:
                _, app = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child,
                                   child_url=f'http://127.0.0.1:{port}/mcp')
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary',
                                             event_hooks={'response': [capture]}) as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    init = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                   'clientInfo': {'name': 'owned-writer-errors', 'version': '0'}}})
                    headers['MCP-Protocol-Version'] = init['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    args = GRAPH if product == 'n8n' else {'model': 'res.partner', 'record_id': 1, 'body': 'Owned note'}
                    store.update(writes_enabled=True)
                    before = len(dispatches)
                    assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                    assert not state['posts'] and len(dispatches) == before
                    store.update(enabled_write_tools=[name])
                    cases = (['exact', 401, 403, 'forbidden-publish', 404, 429, 500, 502, 503, 'text',
                              'late-500', 'active', 'missing-id', 'null', 'disconnect', 'settings-fallback', 'positive'] if product == 'n8n'
                             else ['exact', 'list', 'text', 'null', 'true', 'false', 'zero', 'negative', 'overflow',
                                   'float', 'list-bool', 'empty-list', 'list-extra', 'list-zero', 'fault',
                                   'positive', 'positive-list'])
                    for case in cases:
                        state['case'] = case
                        before, committed = len(state['posts']), len(state['commits'])
                        wire.clear()
                        reply = await rpc(client, '/mcp', headers, call(name, args))
                        assert state['received_keys'][-1] == KEY
                        attempts = 2 if case == 'settings-fallback' else 1
                        assert len(state['posts']) == before + attempts, (case, state['posts'])
                        raw = b''.join(wire).decode()
                        assert CANARY not in raw and KEY not in raw, (product, case, raw)
                        assert CANARY not in json.dumps(reply) and KEY not in json.dumps(reply)
                        assert len(raw) < 4096, (product, case, len(raw))
                        if case in ('positive', 'positive-list'):
                            value = payload(reply)
                            assert len(state['commits']) == committed + 1
                            if product == 'n8n':
                                assert value['success'] is True and value['data'] == {
                                    'id': 'owned1', 'name': 'Owned draft', 'active': False, 'nodeCount': 2}
                            else:
                                assert value == {'success': True, 'message_id': 2 if case == 'positive' else 3}
                        else:
                            if product == 'n8n':
                                value = json.loads(next(c['text'] for c in reply['content'] if c['type'] == 'text'))
                                assert value['success'] is False
                                assert set(value) == {'success', 'error', 'code'}
                                assert len(value['error']) <= 256
                                expected = {401: 'AUTHENTICATION_ERROR', 403: 'FORBIDDEN', 404: 'NOT_FOUND',
                                            429: 'RATE_LIMIT_ERROR', 500: 'SERVER_ERROR', 502: 'SERVER_ERROR',
                                            503: 'SERVER_ERROR', 'exact': 'VALIDATION_ERROR', 'text': 'VALIDATION_ERROR',
                                            'forbidden-publish': 'FORBIDDEN', 'late-500': 'SERVER_ERROR',
                                            'settings-fallback': 'SERVER_ERROR',
                                            'disconnect': 'NO_RESPONSE'}.get(case, 'BACKEND_INVALID_RESPONSE')
                                assert value['code'] == expected, (case, value)
                            else:
                                assert reply.get('isError') is True
                                assert ('BACKEND_UNAVAILABLE' if case == 'fault' else 'BACKEND_INVALID_RESPONSE') in raw
                            # Malformed results / late failures follow a genuine owned write.
                            effect = (case not in ('fault',) if product == 'odoo-manage' else
                                      case in ('late-500', 'active', 'missing-id', 'null', 'disconnect', 'settings-fallback'))
                            assert len(state['commits']) == committed + int(effect)
                        print('B1_WRITER_CASE', product, case, 'posts=' + str(attempts),
                              'committed=' + str(len(state['commits']) - committed))
                    for policy in ({'disabled': [name]}, {'disabled': [], 'enabled_write_tools': []}):
                        store.update(**policy)
                        before, count = len(dispatches), len(state['posts'])
                        assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                        assert len(dispatches) == before and len(state['posts']) == count
                    assert not state['failures'], state['failures']
                    await client.delete('/mcp', headers=headers)
        finally:
            reservation.close()
            await process.stop()
            store.close()
