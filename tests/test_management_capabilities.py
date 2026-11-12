"""New management routes use owned mock child sessions; never contact HA or a backend."""
from admin_write_headers import reviewed_headers
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from mcp_admin_core.capabilities import ManagementOptions, observe_tools, tool_catalog
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import ProductStore
from mcp_admin_core.surface import listing
from n8n_adapter import TOOLS
from test_health import Process
from mcp_admin_core.products import BOUNDED_TOOLS

IDENTITY = {'x-remote-user-id': 'human', 'x-ingress-path': '/api/hassio_ingress/DUMMY'}
READ = 'n8n_list_workflows'
WRITE = 'n8n_create_workflow'
SCHEMA = {'type': 'object', 'properties': {'limit': {'type': 'integer', 'maximum': 100}}, 'required': ['limit']}


def test_bounded_tool_schema_is_the_gateway_contract(tmp_path):
    store = ProductStore(tmp_path, 'opendesign')
    try:
        registry = BOUNDED_TOOLS['opendesign']
        name, tool = next(iter(registry.items()))
        observed = [{'name': name, 'inputSchema': {'type': 'object', 'additionalProperties': True}}]
        item = tool_catalog(registry, None, observed, store.load())['items'][0]
        assert item['inputSchema'] == tool.arguments.model_json_schema()
        assert item['schema_source'] == 'registry'
    finally: store.close()


@asynccontextmanager
async def setup(tmp_path, **options):
    store = ProductStore(tmp_path / 'state', 'n8n')
    record = {'allow': True, 'calls': [], 'restart': 0, 'failure': False, 'pages': False}
    async def verify(_): return record['allow']
    async def child_reply(request):
        record['calls'].append(request)
        if record['failure']: return httpx.Response(503)
        if request.method == 'DELETE': return httpx.Response(204)
        message = json.loads(request.content)
        method = message['method']
        if method == 'notifications/initialized': return httpx.Response(202)
        if method == 'initialize':
            result = {'serverInfo': {'name': 'mock'}, 'protocolVersion': '2025-03-26'}
        elif method == 'tools/list':
            result = {'tools': [{'name': name, 'description': 'Observed description', 'inputSchema': SCHEMA}
                                for name in (READ, WRITE, 'runtime_only')]}
            if record['pages']:
                if message.get('params', {}).get('cursor'):
                    result = {'tools': [{'name': 'last_page', 'inputSchema': {'type': 'object'}}]}
                else: result['nextCursor'] = 'next'
        elif method == 'tools/call':
            assert message['params'] == {'name': READ, 'arguments': {'limit': 1}}
            result = {'content': [{'type': 'text', 'text': '{"success":true}'}]}
        else: result = {}
        return httpx.Response(200, headers={'mcp-session-id': 'owned-session'}, json={
            'jsonrpc': '2.0', 'id': message['id'], 'result': result})
    async def restart(state):
        assert state == store.load()
        record['restart'] += 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(child_reply)) as child:
        health = HealthMonitor(store, Process(), child)
        admin, _ = make_apps(store, TOOLS, child, verify_admin=verify, listing=listing('n8n'),
                            health=health.snapshot, backend_check=health.test_saved,
                            restart_child=options.pop('restart_child', restart),
                            diagnostics=lambda: {'logs': {'entries': [], 'redacted': True}}, **options)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
            headers = dict(IDENTITY)
            bootstrap = (await client.get('/api/bootstrap', headers=headers)).json()
            headers = reviewed_headers(bootstrap, headers)
            try: yield store, record, client, headers, admin, bootstrap
            finally: store.close()


@pytest.mark.parametrize('method,path', [('GET','capabilities'), ('GET','diagnostics'), ('POST','backend/test'), ('POST','child/restart')])
async def test_protected_routes_fresh_role_peer_and_csrf(tmp_path, method, path):
    async with setup(tmp_path) as (store, record, client, headers, admin, bootstrap):
        before = store.path.read_bytes()
        record['allow'] = False
        assert (await client.request(method, '/api/' + path, headers=headers)).status_code == 403
        record['allow'] = True
        assert (await client.request(method, '/api/' + path)).status_code == 403
        if method == 'POST':
            assert (await client.post('/api/' + path, headers=IDENTITY)).status_code == 403
            assert (await client.post('/api/' + path, headers={**headers, 'sec-fetch-site': 'cross-site'})).status_code == 403
            assert (await client.post('/api/' + path, headers=headers, json={'unexpected': True})).status_code == 400
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=('127.0.0.1', 1)), base_url='http://admin') as outsider:
            assert (await outsider.request(method, '/api/' + path, headers=headers)).status_code == 403
        assert not record['calls'] and record['restart'] == 0
        assert store.path.read_bytes() == before


async def test_catalog_union_actual_schema_policy_counts_and_pagination(tmp_path):
    async with setup(tmp_path) as (store, record, client, headers, admin, bootstrap):
        store.update(disabled=[WRITE])
        record['pages'] = True
        response = await client.get('/api/capabilities', headers=headers)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        result = response.json()
        assert result['schema_version'] == 1 and result['deployment']['kind'] == 'ha-addon'
        assert result['health']['public_endpoint'] == 'unverified'
        catalog = result['tools']
        items = {item['name']: item for item in catalog['items']}
        assert catalog['status'] == 'observed' and catalog['effective_count'] == 1
        assert catalog['catalog_count'] == len(TOOLS) + 2
        assert items[READ]['inputSchema'] == SCHEMA and items[READ]['schema_source'] == 'child'
        assert items[READ]['effective'] is True
        assert items[WRITE]['effective'] is False and items[WRITE]['reason'] == 'policy_disabled'
        assert items['runtime_only']['effective'] is False and items['runtime_only']['reason'] == 'not_in_registry'
        assert items['last_page']['policy_enabled'] is False
        assert record['calls'][-1].method == 'DELETE'
        assert all(request.url.host == '127.0.0.1' for request in record['calls'])
        pinned = next(item for item in listing('n8n') if item['name'] == READ)
        assert bootstrap['tools'][READ]['inputSchema'] == pinned['inputSchema']


async def test_failed_observation_keeps_catalog_with_unknown_effective_count(tmp_path):
    async with setup(tmp_path) as (store, record, client, headers, *_):
        store.update(disabled=[WRITE])
        record['failure'] = True
        catalog = (await client.get('/api/capabilities', headers=headers)).json()['tools']
        assert catalog['status'] == 'unknown' and catalog['effective_count'] is None
        items = {item['name']: item for item in catalog['items']}
        assert items[READ]['effective'] is None and items[READ]['schema_source'] == 'pinned'
        assert items[WRITE]['effective'] is False


async def test_fixed_builtin_metadata_blocks_backend_mutation_and_version_override(tmp_path):
    async with setup(tmp_path, management=ManagementOptions(kind='builtin', authority='ha-ingress', backend_mode='fixed', backend_can_edit=False, product_version='0.2.2')) as (store, record, client, headers, admin, bootstrap):
        cap = bootstrap['capabilities']
        assert cap['deployment']['kind'] == 'builtin' and cap['admin']['authority'] == 'ha-ingress'
        assert cap['backend'] == {'mode': 'fixed', 'can_edit': False, 'can_test': True}
        assert cap['product']['version'] == '0.2.2'
        before = store.path.read_bytes()
        response = await client.put('/api/backend', headers=headers, json={'url': None, 'key': None})
        assert response.status_code == 409 and response.json()['error'] == 'backend_fixed'
        assert store.path.read_bytes() == before and record['restart'] == 0


async def test_saved_backend_check_and_restart_preserve_configuration(tmp_path):
    async with setup(tmp_path) as (store, record, client, headers, *_):
        store.update(backend_url='http://backend.test', backend_key='DUMMY-saved',
                     writes_enabled=False, enabled_write_tools=[], disabled=[WRITE], token=None,
                     endpoint='https://mcp.example.test/mcp')
        before = store.path.read_bytes()
        result = (await client.post('/api/backend/test', headers=headers)).json()
        assert result['backend'] == 'reachable' and result['tested_configuration'] == 'saved'
        assert store.path.read_bytes() == before and record['restart'] == 0
        headers = reviewed_headers((await client.get('/api/bootstrap', headers=headers)).json(), headers)
        reply = await client.post('/api/child/restart', headers=headers)
        assert reply.status_code == 202 and reply.json()['apply_state'] == 'pending'
        assert record['restart'] == 1 and store.path.read_bytes() == before
        assert 'DUMMY-saved' not in json.dumps(result)
        saved = store.load()
        assert saved.schema_version == 4
    reopened = ProductStore(tmp_path / 'state', 'n8n')
    try:
        assert reopened.load() == saved
        assert reopened.path.read_bytes() == before
    finally: reopened.close()


@pytest.mark.parametrize('cancel', ['disconnect', 'direct'])
async def test_restart_retains_lock_and_joins_on_cancellation(tmp_path, cancel):
    entered, finish, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def restart(state):
        entered.set()
        await finish.wait()
        completed.set()
    async with setup(tmp_path, restart_child=restart) as (store, record, client, headers, admin, bootstrap):
        before = store.path.read_bytes()
        events = asyncio.Queue()
        events.put_nowait({'type': 'http.request', 'body': b'', 'more_body': False})
        async def send(message): pass
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/child/restart', 'query_string': b'',
                 'headers': [(k.encode(), v.encode()) for k, v in headers.items()], 'client': ('172.30.32.2', 1),
                 'server': ('admin', 80), 'scheme': 'http', 'http_version': '1.1'}
        action = asyncio.create_task(admin(scope, events.get, send))
        await asyncio.wait_for(entered.wait(), 1)
        if cancel == 'disconnect': events.put_nowait({'type': 'http.disconnect'})
        else: action.cancel()
        await asyncio.sleep(.02)
        assert not action.done()
        pending = asyncio.create_task(client.post('/api/token/revoke', headers=headers))
        await asyncio.sleep(.02)
        assert not pending.done() and store.path.read_bytes() == before
        record['allow'] = False
        finish.set()
        await asyncio.gather(action, return_exceptions=True)
        assert completed.is_set() and (await pending).status_code == 403
        assert store.path.read_bytes() == before


async def test_catalog_session_is_closed_on_cancellation(tmp_path):
    store = ProductStore(tmp_path, 'n8n')
    entered, closed = asyncio.Event(), asyncio.Event()
    async def reply(request):
        if request.method == 'DELETE':
            closed.set()
            return httpx.Response(204)
        message = json.loads(request.content)
        if message['method'] == 'initialize':
            return httpx.Response(200, headers={'mcp-session-id': 'owned'}, json={'jsonrpc':'2.0', 'id':1, 'result': {'serverInfo':{}, 'protocolVersion':'2025-03-26'}})
        if message['method'] == 'notifications/initialized': return httpx.Response(202)
        entered.set()
        await asyncio.Event().wait()
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as child:
            task = asyncio.create_task(observe_tools(child, 'http://127.0.0.1:3000/mcp', store.load()))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert closed.is_set()
    finally: store.close()
