"""Builtin-compatible management adds no grants and never changes its fixed backend."""
from contextlib import closing
import json
import httpx
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS


async def test_builtin_capabilities_and_diagnostics_keep_auth_csrf_and_state(tmp_path):
    seen = []
    def child_reply(request):
        if request.method == 'DELETE':
            seen.append('delete')
            return httpx.Response(200)
        message = json.loads(request.content)
        if 'id' not in message:
            return httpx.Response(202)
        result = {'serverInfo': {'name': 'fake', 'version': '1'}, 'protocolVersion': '2025-03-26'}
        if message['method'] == 'tools/list':
            result = {'tools': [{'name': 'health', 'description': 'backend health', 'inputSchema': {'type': 'object'}}]}
        return httpx.Response(200, headers={'mcp-session-id': 'owned'}, json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})
    async def role(_): return True
    async def check(state): return {'tested_configuration': 'saved', 'backend': 'reachable'}
    async def restart(state): seen.append('restart')
    with closing(ProductStore(tmp_path, 'opendesign')) as store:
        store.update(connection={'url': 'http://127.0.0.1:7456'}, disabled=['list_skills'])
        before = store.load().model_dump()
        async with httpx.AsyncClient(transport=httpx.MockTransport(child_reply)) as child:
            admin, _ = make_apps(store, TOOLS['opendesign'], child, verify_admin=role,
                management=ManagementOptions(kind='builtin', authority='ha-ingress', backend_mode='fixed', backend_can_edit=False),
                backend_check=check, restart_child=restart, diagnostics=lambda: {'logs': {'entries': []}})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://test') as c:
                identity = {'x-remote-user-id': 'a'*32}
                assert (await c.get('/api/capabilities')).status_code == 403
                b = (await c.get('/api/bootstrap', headers=identity)).json()
                headers = {**identity, 'x-csrf-token': b['csrf']}
                cap = (await c.get('/api/capabilities', headers=identity)).json()
                assert cap['deployment']['kind'] == 'builtin'
                assert cap['backend'] == {'mode': 'fixed', 'can_test': True, 'can_edit': False}
                assert cap['tools']['effective_count'] == 1
                assert 'delete' in seen
                assert (await c.post('/api/child/restart', headers=identity)).status_code == 403
                assert (await c.post('/api/child/restart', headers=headers)).status_code == 202
                assert 'restart' in seen
                checked = await c.post('/api/backend/test', headers=headers)
                assert checked.json()['backend'] == 'reachable'
                assert (await c.put('/api/backend', headers=headers, json={'connection': {'url': 'http://127.0.0.1:9999'}})).status_code == 409
                assert (await c.get('/api/diagnostics', headers=identity)).status_code == 200
        assert store.load().model_dump() == before
