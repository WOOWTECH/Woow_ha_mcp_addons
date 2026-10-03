"""Real pinned handlers through the boundary; writes ONLY to this owned fake API."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit
import xmlrpc.client

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from test_real_products import connection, rpc
from test_expansion_policy import call
from n8n_adapter import TOOLS as N8N_TOOLS, child_spec as n8n_spec

PID = '12345678-1234-1234-1234-123456789abc'
READS = {
    'odoo': [('read_record', {'model': 'res.partner', 'record_id': 1, 'fields': ['id', 'name']}),
             ('search_records', {'model': 'res.partner', 'fields': ['id', 'name']}),
             ('get_model_fields', {'model': 'res.partner', 'field_names': ['name']})],
    'odoo-manage': [('get_record', {'model': 'res.partner', 'record_id': 1, 'fields': ['id', 'name']}),
                    ('search_records', {'model': 'res.partner', 'fields': ['id', 'name']})],
    'hermes': [('hermes_skill', {'action': 'list'}), ('hermes_tools', {}),
               ('hermes_session', {}), ('hermes_cron', {})],
    'opendesign': [('list_runs', {})],
    'emqx': [('emqx_list_clients', {}), ('emqx_list_topics', {}), ('emqx_list_subscriptions', {}),
             ('emqx_metrics_history', {}), ('emqx_list_alarms', {})],
    'litellm': [('litellm_list_teams', {})],
    'n8n': [('get_node', {'nodeType': 'nodes-base.httpRequest'}), ('n8n_get_workflow', {'id': 'one'}), ('n8n_manage_folders', {'action': 'list', 'projectId': 'project'})],
}
WRITES = {
    'odoo': [('chatter_post', {'model': 'res.partner', 'record_id': 1, 'body': 'Owned test comment'})],
    'odoo-manage': [('create_record', {'model': 'res.partner', 'values': {'name': 'New'}}),
                    ('update_record', {'model': 'res.partner', 'record_id': 1, 'values': {'name': 'Changed'}}),
                    ('delete_record', {'model': 'res.partner', 'record_id': 1})],
    'hermes': [('hermes_skill', {'action': 'disable', 'name': 'example'}),
               ('hermes_skill', {'action': 'enable', 'name': 'example'}),
               ('hermes_gateway', {'action': 'restart'}),
               ('hermes_session', {'action': 'delete', 'session_id': 'example'}),
               ('hermes_tools', {'action': 'enable', 'toolset': 'example'}),
               ('hermes_tools', {'action': 'disable', 'toolset': 'example'}),
               ('hermes_cron', {'action': 'pause', 'job_id': 'example'}),
               ('hermes_cron', {'action': 'delete', 'job_id': 'example'})],
    'opendesign': [('delete_project', {'project_id': PID})],
    'emqx': [('emqx_kick_client', {'clientid': 'device'}),
             ('emqx_client_subscribe', {'clientid': 'device', 'topic': 'owned/test'}),
             ('emqx_client_unsubscribe', {'clientid': 'device', 'topic': 'owned/test'})],
    'litellm': [('litellm_create_team', {'team_alias': 'Owned'}),
                ('litellm_update_team', {'team_id': 'one', 'team_alias': 'Changed'}),
                ('litellm_delete_team', {'team_ids': ['one']}),
                ('litellm_delete_model', {'model_id': 'one'})],
    'n8n': [('n8n_manage_folders', {'action': 'create', 'projectId': 'project', 'name': 'New'}),
            ('n8n_manage_folders', {'action': 'rename', 'projectId': 'project', 'folderId': 'one', 'name': 'Changed'})],
}


@contextmanager
def fake_api():
    events, mutations, failures = [], [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self): self.handle_api()
        def do_POST(self): self.handle_api()
        def do_PUT(self): self.handle_api()
        def do_PATCH(self): self.handle_api()
        def do_DELETE(self): self.handle_api()
        def handle_api(self):
            path = urlsplit(self.path).path
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            events.append((self.command, path))
            content_type = 'application/json'
            try:
                if 'xmlrpc' in path:
                    params, method = xmlrpc.client.loads(raw)
                    if method == 'version':
                        value = {'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]}
                    elif method == 'authenticate': value = 7
                    else:
                        assert method == 'execute_kw'
                        model, op = params[3:5]
                        assert model in ('ir.model', 'res.partner')
                        args, kwargs = params[5], params[6] if len(params) > 6 else {}
                        if op in ('create', 'write', 'unlink', 'message_post'):
                            mutations.append((model, op, args))
                            value = 2 if op in ('create', 'message_post') else True
                        elif op == 'fields_get':
                            value = {'id': {'type': 'integer', 'string': 'ID'}, 'name': {'type': 'char', 'string': 'Name'}, 'display_name': {'type': 'char'}, 'active': {'type': 'boolean'}}
                        elif op == 'search_count': value = 1
                        elif op == 'search': value = [1]
                        elif op in ('read', 'search_read'):
                            row = {'id': 1, 'name': 'Owned', 'display_name': 'Owned', 'active': True}
                            if model == 'ir.model': row = {'id': 1, 'model': 'res.partner', 'name': 'Contact'}
                            value = [{k: v for k, v in row.items() if k in kwargs.get('fields', row)}]
                        else: raise AssertionError(op)
                    data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
                    content_type = 'text/xml'
                else:
                    body = json.loads(raw) if raw else {}
                    if path == '/auth/password-login': value = {}
                    elif path == '/mcp/auth/validate': value = {'success': True, 'data': {'valid': True, 'user_id': 7}}
                    elif path == '/mcp/models': value = {'success': True, 'data': {'models': [{'model': 'res.partner', 'name': 'Contacts'}]}}
                    elif path == '/mcp/models/res.partner/access': value = {'success': True, 'data': {'model': 'res.partner', 'enabled': True, 'operations': {op: True for op in ('read', 'create', 'write', 'unlink')}}}
                    elif self.command != 'GET':
                        assert path in ('/api/skills/toggle', '/api/tools/toolsets/example', '/api/cron/jobs/example', '/api/cron/jobs/example/pause', '/api/gateway/restart', '/api/sessions/example', '/api/projects/'+PID,
                                        '/api/v5/clients/device', '/api/v5/clients/device/subscribe', '/api/v5/clients/device/unsubscribe',
                                        '/team/new', '/team/update', '/team/delete', '/model/delete',
                                        '/api/v1/projects/project/folders', '/api/v1/projects/project/folders/one'), path
                        mutations.append((self.command, path, body))
                        value = {'id': 'one', 'name': body.get('name', 'Owned'), 'team_id': 'one', 'team_alias': body.get('team_alias', 'Owned'), 'status': 'success', 'private_key': 'MUST_NOT_ESCAPE'}
                    else:
                        value = {
                            '/api/skills': [{'name': 'example', 'enabled': True}],
                            '/api/tools/toolsets': [{'name': 'example', 'enabled': True}],
                            '/api/sessions': {'sessions': [{'id': 'example', 'messages': ['MUST_NOT_ESCAPE']}]},
                            '/api/cron/jobs': [{'id': 'example', 'name': 'Owned', 'prompt': 'MUST_NOT_ESCAPE'}],
                            '/api/runs': {'runs': [{'id': 'one', 'projectId': PID, 'status': 'done', 'prompt': 'MUST_NOT_ESCAPE', 'path': '/private/key'}]},
                            '/api/v5/clients': {'data': [{'clientid': 'device', 'connected': True}], 'meta': {'count': 1}},
                            '/api/v5/topics': {'data': [{'topic': 'owned/test'}]},
                            '/api/v5/subscriptions': {'data': [{'clientid': 'device', 'topic': 'owned/test'}]},
                            '/api/v5/monitor': [{'time_stamp': 1, 'connections': 1}],
                            '/api/v5/alarms': {'data': []},
                            '/v2/team/list': {'teams': [{'team_id': 'one', 'team_alias': 'Owned', 'keys': ['MUST_NOT_ESCAPE'], 'metadata': {'secret': 'MUST_NOT_ESCAPE'}}]},
                            '/api/v1/workflows/one': {'id': 'one', 'name': 'Owned', 'active': False, 'nodes': [{'secret': 'MUST_NOT_ESCAPE'}]},
                            '/api/v1/projects/project/folders': {'data': [{'id': 'one', 'name': 'Owned'}], 'count': 1},
                        }[path]
                    data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                if path == '/auth/password-login': self.send_header('Set-Cookie', 'hermes_session_at=DUMMY; Path=/')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
            except Exception as exc:
                failures.append(repr(exc)); self.send_error(500)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}', events, mutations, failures
    finally: server.shutdown(); server.server_close(); thread.join()


def payload(reply):
    assert not reply.get('isError'), reply
    value = reply.get('structuredContent')
    if value is None:
        value = json.loads(next(c['text'] for c in reply['content'] if c['type'] == 'text'))
    if isinstance(value, dict) and set(value) == {'result'} and isinstance(value['result'], dict):
        value = value['result']
    assert value.get('success') is not False, value
    assert not value.get('error'), value
    return value


@pytest.mark.parametrize('product', list(READS))
async def test_real_expanded_reads_and_explicit_writes(tmp_path, product):
    with fake_api() as (url, events, mutations, failures):
        store = ProductStore(tmp_path / 'state', product)
        tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
        grants = sorted({g for name, tool in tools.items() for g in tool.grants(name)})
        if product == 'n8n': store.update(backend_url=url, backend_key='DUMMY', enabled_write_tools=grants)
        else:
            conn = connection(product, url)
            if product == 'odoo-manage': conn['mode'] = 'module'
            store.update(connection=conn, enabled_write_tools=grants)
        process = Supervisor((n8n_spec if product == 'n8n' else child_spec)(store.load(), store.directory), retries=0)
        try:
            await process.start()
            async with httpx.AsyncClient(trust_env=False) as child:
                _, app = make_apps(store, tools, child)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer '+store.load().token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'owned-test', 'version': '0'}}}
                    async with asyncio.timeout(25):
                        while True:
                            try:
                                result = await rpc(client, '/mcp', headers, init); break
                            except ValueError: await asyncio.sleep(.1)
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    store.update(enabled_write_tools=[])
                    for name, args in READS[product]:
                        before = len(events)
                        reply = await rpc(client, '/mcp', headers, call(name, args))
                        payload(reply)
                        assert 'MUST_NOT_ESCAPE' not in json.dumps(reply)
                        if name == 'get_node':
                            assert 'httpRequest' in json.dumps(reply)
                            assert len(events) == before  # pinned local node database only
                        else:
                            assert len(events) > before
                    assert mutations == []
                    for name, args in WRITES[product]:
                        tool = tools[name]
                        grant = name if tool.write else f'{name}:{args[tool.selector]}'
                        before = len(events)
                        assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                        assert len(events) == before
                        store.update(enabled_write_tools=[grant])
                        if product == 'odoo':
                            preview = payload(await rpc(client, '/mcp', headers, call(name, args)))
                            assert preview.get('mode') == 'preview', preview
                            args = {**args, 'approval': {'token': preview['approval']['token']}, 'confirm': True}
                        count = len(mutations)
                        reply = await rpc(client, '/mcp', headers, call(name, args))
                        payload(reply)
                        if product == 'litellm': assert 'MUST_NOT_ESCAPE' not in json.dumps(reply)
                        assert len(mutations) == count + 1, (product, name, reply, failures)
                        before = len(events)
                        store.update(disabled=[name])
                        assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                        assert len(events) == before
                        store.update(disabled=[], enabled_write_tools=[])
                    assert not failures, failures
                    await client.delete('/mcp', headers=headers)
        finally:
            await process.stop(); store.close()
