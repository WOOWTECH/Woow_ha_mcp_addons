"""Enabled n8n API branches, genuine handlers and owned runtime; no live backend."""
import asyncio
import json
import threading
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from batch2_owned_port import private_spec, reserve_port, request_guard, wait_owned_listener
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import ProductStore
from n8n_adapter import TOOLS, child_spec
from test_batch2_policy import GRAPH
from test_expansion_policy import call
from test_real_products import rpc

KEY = 'OWNED_N8N_READ_RECEIVED_DUMMY_KEY'
PRIVATE = 'OWNED_N8N_PRIVATE_DIAGNOSTIC'
MESSAGES = {
    'VALIDATION_ERROR': 'The n8n backend rejected the request.',
    'AUTHENTICATION_ERROR': 'Authentication with the n8n backend failed.',
    'FORBIDDEN': 'The n8n backend denied access to this operation.',
    'NOT_FOUND': 'The requested n8n resource or API route was not found.',
    'RATE_LIMIT_ERROR': 'The n8n backend rate limit was reached. Try again later.',
    'SERVER_ERROR': 'The n8n backend reported a server error.',
    'BACKEND_INVALID_RESPONSE': 'The n8n backend returned an invalid response.',
    'BACKEND_UNAVAILABLE': 'The n8n operation could not be completed.',
}

# Audited server.js dispatch -> manager handlers -> API methods, NOT inferred names.
BRANCHES = [
    ('n8n_list_workflows', {'limit': 1}, None, 'GET', '/api/v1/workflows'),
    ('n8n_get_workflow', {'id': 'owned1', 'mode': 'minimal'}, None, 'GET', '/api/v1/workflows/owned1'),
    ('n8n_manage_folders', {'action': 'list', 'projectId': 'project1'}, None, 'GET', '/api/v1/projects/project1/folders'),
    ('n8n_delete_workflow', {'id': 'owned1'}, 'n8n_delete_workflow', 'DELETE', '/api/v1/workflows/owned1'),
    ('n8n_manage_folders', {'action': 'create', 'projectId': 'project1', 'name': 'Owned'}, 'n8n_manage_folders:create', 'POST', '/api/v1/projects/project1/folders'),
    ('n8n_manage_folders', {'action': 'rename', 'projectId': 'project1', 'folderId': 'folder1', 'name': 'Owned'}, 'n8n_manage_folders:rename', 'PATCH', '/api/v1/projects/project1/folders/folder1'),
    ('n8n_create_workflow', GRAPH, 'n8n_create_workflow', 'POST', '/api/v1/workflows'),
]


@contextmanager
def backend():
    state = {'case': 404, 'calls': [], 'keys': [], 'failures': []}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def respond(self):
            try:
                self.connection.settimeout(3)
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                key = self.headers['X-N8N-API-KEY']
                state['keys'].append(key)
                state['calls'].append((self.command, self.path.split('?')[0], raw))
                case = state['case']
                private = PRIVATE + ':' + key
                status = case if type(case) is int else 400
                value = {'message': private, 'details': {'nested': [private]}, 'stack': private}
                if case == 'nested':
                    value = {'message': {'nested': [private]}, 'error': private}
                elif case == 'publish':
                    status = 403
                    value.update(reason='insufficient_api_key_scope', versionId=private)
                elif case == 'success':
                    status = 200
                    workflow = {'id': 'owned1', 'name': 'Business name', 'active': False,
                                'isArchived': False, 'tags': [], 'nodes': [{}, {}],
                                'createdAt': '2026-01-01', 'updatedAt': '2026-01-02',
                                'privateDiagnostics': private}
                    path = self.path.split('?')[0]
                    if '/folders' in path:
                        folder = {'id': 'folder1', 'name': 'Business name', 'parentFolderId': None}
                        value = {'data': [folder], 'count': 1} if self.command == 'GET' else folder
                    else:
                        value = {'data': [workflow]} if path == '/api/v1/workflows' and self.command == 'GET' else workflow
                elif case == 'malformed-success':
                    status, value = 200, None
                elif case == 'unknown-keys':
                    status, value = 200, {private: private}
                elif case == 'ambiguous-personal':
                    assert self.path.split('?')[0] == '/api/v1/projects'
                    status = 200
                    value = {'data': [{'id': private, 'name': private, 'type': 'personal'}] * 2}
                data = private.encode() if case == 'text' else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'text/plain' if case == 'text' else 'application/json')
                self.send_header('Retry-After', private)
                if status == 302:
                    self.send_header('Location', '/must-not-follow')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                state['failures'].append(type(exc).__name__)
                raise

        do_GET = do_POST = do_PATCH = do_DELETE = respond

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    assert server.server_port != 3000
    # Bounded handle_request loop avoids an unbounded server.shutdown() wait.
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


@asynccontextmanager
async def runtime(tmp_path):
    with backend() as (url, state):
        store = ProductStore(tmp_path / 'n8n', 'n8n')
        store.update(backend_url=url, backend_key=KEY)
        spec = child_spec(store.load(), store.directory)
        process = Supervisor(spec, retries=0)
        reservation = reserve_port()
        port = reservation.getsockname()[1]
        dispatches, wire = [], []
        async def dispatched(request):
            dispatches.append(request.method)
        async def capture(response):
            wire.append(await response.aread())
        try:
            process.spec = private_spec(spec, 'n8n', port)
            reservation.close()
            await process.start()
            proof = await wait_owned_listener(process, port)
            print('N8N_PUBLIC_ERRORS_OWNED', port, *proof)
            async with httpx.AsyncClient(trust_env=False, timeout=8, event_hooks={
                    'request': [request_guard(process, port, proof), dispatched]}) as child:
                _, app = make_apps(store, TOOLS, child, child_url=f'http://127.0.0.1:{port}/mcp')
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary',
                        timeout=8, event_hooks={'response': [capture]}) as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    init = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                   'clientInfo': {'name': 'owned-public-errors', 'version': '0'}}})
                    headers['MCP-Protocol-Version'] = init['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    yield store, state, client, headers, wire, dispatches
                    await client.delete('/mcp', headers=headers)
        finally:
            reservation.close()
            await process.stop()
            store.close()


def error_result(reply, wire, code, *, write=False):
    raw = b''.join(wire).decode()
    assert KEY not in raw and PRIVATE not in raw, raw
    assert KEY not in json.dumps(reply) and PRIVATE not in json.dumps(reply)
    assert len(raw) < 4096
    value = json.loads(next(c['text'] for c in reply['content'] if c['type'] == 'text'))
    assert set(value) == {'success', 'error', 'code'}
    assert value['success'] is False and value['code'] == code, value
    assert value['error'] == MESSAGES[code] + (
        ' Write outcome may be unknown; verify before retrying.' if write else '')
    assert 10 <= len(value['error']) <= 256
    return value


async def test_readonly_404_received_key_no_writer_grants(tmp_path):
    async with asyncio.timeout(50), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        assert not store.load().enabled_write_tools and not store.load().writes_enabled
        for name, args, grant, *_ in BRANCHES:
            if grant:
                before = len(dispatches)
                assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                assert len(dispatches) == before and not state['calls']
        wire.clear()
        reply = await rpc(client, '/mcp', headers, call('n8n_list_workflows', {'limit': 1}))
        assert state['keys'] == [KEY]
        assert [c[:2] for c in state['calls']] == [('GET', '/api/v1/workflows')]
        error_result(reply, wire, 'NOT_FOUND')
        assert not state['failures']


@pytest.mark.parametrize('branch', BRANCHES, ids=['list', 'minimal', 'folders-list', 'delete', 'folders-create', 'folders-rename', 'create'])
async def test_enabled_api_error_corpus(tmp_path, branch):
    name, args, grant, method, path = branch
    async with asyncio.timeout(60), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        if grant:
            store.update(enabled_write_tools=[grant])
        cases = [(400, 'VALIDATION_ERROR'), (401, 'AUTHENTICATION_ERROR'), (403, 'FORBIDDEN'),
                 (404, 'NOT_FOUND'), (429, 'RATE_LIMIT_ERROR'), (500, 'SERVER_ERROR'),
                 (502, 'SERVER_ERROR'), (599, 'SERVER_ERROR'), (418, 'BACKEND_UNAVAILABLE'),
                 (302, 'BACKEND_UNAVAILABLE'),
                 ('text', 'VALIDATION_ERROR'), ('nested', 'VALIDATION_ERROR'), ('publish', 'FORBIDDEN')]
        # Delete's native 200 empty-body success semantics are not changed here.
        if name != 'n8n_delete_workflow':
            cases.append(('malformed-success', 'BACKEND_INVALID_RESPONSE'
                          if name == 'n8n_create_workflow' else 'BACKEND_UNAVAILABLE'))
        if name == 'n8n_list_workflows':
            cases.append(('unknown-keys', 'BACKEND_UNAVAILABLE'))
        for case, code in cases:
            state['case'] = case
            before = len(state['calls'])
            wire.clear()
            reply = await rpc(client, '/mcp', headers, call(name, args))
            assert len(state['calls']) == before + 1
            assert state['calls'][-1][:2] == (method, path)
            assert state['keys'][-1] == KEY
            error_result(reply, wire, code, write=grant is not None)
            print('N8N_PUBLIC_CASE', name, args.get('action', ''), case, code)
        if grant:
            for policy in ({'disabled': [name]}, {'disabled': [], 'enabled_write_tools': []}):
                store.update(**policy)
                before, count = len(dispatches), len(state['calls'])
                assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                assert len(dispatches) == before and len(state['calls']) == count
        assert not state['failures'], state['failures']


async def test_readonly_success_projection_unchanged(tmp_path):
    async with asyncio.timeout(50), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        state['case'] = 'success'
        base = {'id': 'owned1', 'name': 'Business name', 'active': False, 'isArchived': False,
                'tags': [], 'createdAt': '2026-01-01', 'updatedAt': '2026-01-02'}
        for name, args, *_ in BRANCHES[:2]:
            wire.clear()
            reply = await rpc(client, '/mcp', headers, call(name, args))
            value = json.loads(reply['content'][0]['text'])
            expected = ({'workflows': [{**base, 'nodeCount': 2}], 'returned': 1, 'hasMore': False}
                        if name == 'n8n_list_workflows' else base)
            assert value == {'success': True, 'data': expected}
            assert KEY not in b''.join(wire).decode() and PRIVATE not in json.dumps(reply)
        assert len(state['calls']) == 2 and not state['failures']


async def test_folder_and_delete_successes_unchanged(tmp_path):
    async with asyncio.timeout(60), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        state['case'] = 'success'
        folder = {'id': 'folder1', 'name': 'Business name', 'parentFolderId': None}
        for name, args, grant, method, path in BRANCHES[2:6]:
            store.update(enabled_write_tools=[grant] if grant else [])
            before = len(state['calls'])
            reply = await rpc(client, '/mcp', headers, call(name, args))
            value = json.loads(reply['content'][0]['text'])
            if name == 'n8n_delete_workflow':
                expected = {'success': True, 'data': {'id': 'owned1', 'name': 'Business name', 'deleted': True},
                            'message': 'Workflow "Business name" deleted successfully.'}
            elif args['action'] == 'list':
                expected = {'success': True, 'data': {'folders': [folder], 'count': 1, 'projectId': 'project1'}}
            elif args['action'] == 'create':
                expected = {'success': True, 'data': folder,
                            'message': 'Folder "Business name" created with ID: folder1. Place workflows in it via n8n_create_workflow\'s parentFolderId or the moveToFolder operation of n8n_update_partial_workflow.'}
            else:
                expected = {'success': True, 'data': {'id': 'folder1', 'name': 'Business name'},
                            'message': 'Folder renamed to "Business name"'}
            assert value == expected
            assert len(state['calls']) == before + 1 and state['calls'][-1][:2] == (method, path)
        assert not state['failures']


@pytest.mark.parametrize('action', ['list', 'rename'])
async def test_personal_folder_resolution_errors(tmp_path, action):
    async with asyncio.timeout(60), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        args = {'action': action}  # genuine default projectId='personal'
        if action == 'rename':
            args.update(folderId='folder1', name='Owned')
            store.update(enabled_write_tools=['n8n_manage_folders:rename'])
        for case, expected in [(400, 'VALIDATION_ERROR'), (403, 'FORBIDDEN'),
                (404, 'NOT_FOUND'), (429, 'RATE_LIMIT_ERROR'), (500, 'SERVER_ERROR'),
                ('text', 'VALIDATION_ERROR'), ('nested', 'VALIDATION_ERROR'),
                (418, 'BACKEND_UNAVAILABLE'), ('ambiguous-personal', 'VALIDATION_ERROR')]:
            state['case'] = case
            state['calls'].clear()
            wire.clear()
            reply = await rpc(client, '/mcp', headers, call('n8n_manage_folders', args))
            # 403/404 projects errors trigger the REAL resolver's workflow fallback.
            paths = ['/api/v1/projects'] + (['/api/v1/workflows'] if case in (403, 404) else [])
            assert [c[:2] for c in state['calls']] == [('GET', p) for p in paths]
            assert all(key == KEY for key in state['keys'])
            error_result(reply, wire, expected, write=action == 'rename')
            print('N8N_PERSONAL_CASE', action, case, paths)
        assert not state['failures']
