"""W2b negative invariants: no child dispatch on invalid/disabled operations."""
import asyncio
import json

import httpx
import pytest

from mcp_admin_core.config import ConfigError
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, ProductState, TOOLS, child_spec
from mcp_admin_core.policy import Denied, authorize
from mcp_admin_core.native_inventory import NAMES
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_policy import call
from test_expansion_runtime import READS, WRITES
from test_real_products import connection

CASES = [(p, name, args) for p in READS for name, args in READS[p] + WRITES[p]]


def state_for(product, grants=(), **kwargs):
    conn = connection(product, 'http://127.0.0.1:9999') if product != 'n8n' else None
    if product == 'odoo-manage': conn['mode'] = 'module'
    return ProductState(product=product, token='a'*43, child_token='b'*43,
                        connection=conn, enabled_write_tools=list(grants), **kwargs)


@pytest.mark.parametrize('product,name,args', CASES)
async def test_extras_and_disabled_have_zero_child_dispatch(product, name, args, tmp_path):
    store = ProductStore(tmp_path / 'state', product)
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    conn = state_for(product).connection
    store.update(connection=conn.model_dump() if conn else None,
                 enabled_write_tools=tools[name].grants(name), writes_enabled=True)
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, tools, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
            headers = {'Authorization': 'Bearer '+store.load().token, 'Mcp-Session-Id': 'existing'}
            for invalid in (call(name, {**args, 'unreviewed': True}), call('unknown', args)):
                assert (await client.post('/mcp', headers=headers, json=invalid)).status_code == 403
            store.update(disabled=[name])
            assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
    assert calls == []
    store.close()


@pytest.mark.parametrize('product,name,args', [(p,n,a) for p in WRITES for n,a in WRITES[p]])
def test_legacy_switch_never_grants_expansion_writes(product, name, args):
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    if tools[name].legacy_write:
        authorize(call(name, args), tools, state_for(product, writes_enabled=True))
    else:
        with pytest.raises(Denied):
            authorize(call(name, args), tools, state_for(product, writes_enabled=True))
        # A different operation or writer grant is never a blanket switch.
        other = [g for n,t in tools.items() for g in t.grants(n) if g not in tools[name].grants(name)]
        with pytest.raises(Denied):
            authorize(call(name, args), tools, state_for(product, other, writes_enabled=True))


@pytest.mark.parametrize('product,name,args', [
    ('odoo', 'read_record', {'model': 'ir.config_parameter', 'record_id': 1, 'fields': ['name']}),
    ('odoo', 'read_record', {'model': 'res.partner', 'record_id': True, 'fields': ['name']}),
    ('odoo-manage', 'get_record', {'model': 'res.partner', 'record_id': 1, 'fields': []}),
    ('odoo', 'search_records', {'model': 'res.partner', 'fields': ['name'], 'domain': [['password', '=', 'x']]}),
    ('odoo', 'search_records', {'model': 'res.partner', 'fields': ['name'], 'domain': [['id', '=', True]]}),
    ('odoo-manage', 'create_record', {'model': 'res.partner', 'values': {'name': 'x', 'password': 'x'}}),
    ('hermes', 'hermes_tools', {'action': 'enable', 'toolset': '../private'}),
    ('hermes', 'hermes_session', {'action': 'get', 'session_id': 'one'}),
    ('hermes', 'hermes_cron', {'action': 'trigger', 'job_id': 'one'}),
    ('hermes', 'hermes_cron', {'action': 'list', 'enabled': 1}),
    ('emqx', 'emqx_kick_client', {'clientid': 'x%2fy'}),
    ('emqx', 'emqx_client_subscribe', {'clientid': 'x', 'topic': 't', 'qos': True}),
    ('litellm', 'litellm_create_team', {'team_alias': 'x', 'members_with_roles': [{'role': 'admin'}]}),
    ('litellm', 'litellm_list_teams', {'page_size': 101}),
    ('n8n', 'get_node', {'nodeType': 'nodes-base.httpRequest', 'includeExamples': 0}),
    ('n8n', 'n8n_get_workflow', {'id': 'one', 'mode': 'full'}),
    ('n8n', 'n8n_manage_folders', {'action': 'delete', 'folderId': 'one'}),
    ('n8n', 'n8n_manage_folders', {'action': 'list', 'name': 'ignored'}),
])
def test_restricted_scopes_and_strict_types(product, name, args):
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    with pytest.raises(Denied):
        authorize(call(name, args), tools, state_for(product, tools[name].grants(name)))


@pytest.mark.parametrize('product', ['emqx', 'litellm'])
def test_native_gates_allow_exact_writer_and_disable_all_others(tmp_path, product):
    tool = 'emqx_kick_client' if product == 'emqx' else 'litellm_create_team'
    state = state_for(product, [tool])
    spec = child_spec(state, tmp_path)
    prefix = 'EMQX_MCP_' if product == 'emqx' else 'LITELLM_MCP_'
    assert spec.env[prefix+'READONLY'] == 'false'
    assert spec.env['FASTMCP_CHECK_FOR_UPDATES'] == 'off'
    assert spec.env['FASTMCP_SHOW_SERVER_BANNER'] == 'false'
    blocked = set(spec.env[prefix+'DISABLED_TOOLS'].split(','))
    assert tool not in blocked
    assert set(NAMES[product]) - set(TOOLS[product]) <= blocked
    assert {name for name,t in TOOLS[product].items() if t.write and name != tool} <= blocked
    state = state_for(product, [tool], disabled=[tool])
    assert child_spec(state, tmp_path).env[prefix+'READONLY'] == 'true'


@pytest.mark.parametrize('product', ['emqx', 'litellm'])
async def test_policy_api_commits_live_denial_before_owned_restart(tmp_path, product):
    store = ProductStore(tmp_path, product)
    started, finish = asyncio.Event(), asyncio.Event()
    callbacks, calls = [], []
    async def restart(state):
        callbacks.append(state.enabled_write_tools)
        started.set(); await finish.wait()
    async def role(_): return True
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={})
    tools = TOOLS[product]
    name, args = WRITES[product][0]
    store.update(enabled_write_tools=[name])
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        admin, app = make_apps(store, tools, child, verify_admin=role, backend_changed=restart)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as a:
            identity = {'x-remote-user-id': 'a'*32}
            bootstrap = (await a.get('/api/bootstrap', headers=identity)).json()
            assert name in bootstrap['tools'][name]['write_grants']
            assert bootstrap['enabled_write_tools'] == [name]
            task = asyncio.create_task(a.put('/api/policy', headers={**identity, 'x-csrf-token': bootstrap['csrf']},
                json={'writes_enabled': False, 'disabled': [name], 'enabled_write_tools': []}))
            await asyncio.wait_for(started.wait(), 2)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as c:
                denied = await c.post('/mcp', headers={'Authorization': 'Bearer '+store.load().token, 'Mcp-Session-Id': 'existing'}, json=call(name, args))
                assert denied.status_code == 403
            assert not calls and not task.done()
            finish.set()
            assert (await task).status_code == 200
            assert callbacks == [[]]
    store.close()


def test_manage_read_mode_cannot_accept_writer_grants(tmp_path):
    store = ProductStore(tmp_path, 'odoo-manage')
    store.update(connection=connection('odoo-manage', 'http://127.0.0.1:9999'))
    before = store.path.read_bytes()
    with pytest.raises(ConfigError): store.update(enabled_write_tools=['create_record'])
    assert store.path.read_bytes() == before
    store.close()


@pytest.mark.parametrize('product', ['n8n', 'opendesign'])
def test_v2_migration_preserves_only_old_writer_semantics(tmp_path, product):
    store = ProductStore(tmp_path, product)
    old = store.load().model_dump()
    old.pop('enabled_write_tools'); old['schema_version'] = 2; old['writes_enabled'] = True
    old['disabled'] = ['unknown_disabled']
    store.path.write_text(json.dumps(old)); store.close()
    store = ProductStore(tmp_path, product)
    actual = store.load().model_dump()
    assert actual == {**old, 'schema_version': 3, 'enabled_write_tools': []}
    store.close()


@pytest.mark.parametrize('bad', ['wrong_product', 'future', 'missing', 'corrupt_grant', 'duplicate_grant'])
def test_invalid_v3_never_rewritten(tmp_path, bad):
    store = ProductStore(tmp_path, 'hermes')
    data = store.load().model_dump(); store.close()
    if bad == 'wrong_product': data['product'] = 'emqx'
    if bad == 'future': data['schema_version'] = 4
    if bad == 'missing': data.pop('enabled_write_tools')
    if bad == 'corrupt_grant': data['enabled_write_tools'] = ['hermes_skill:typo']
    if bad == 'duplicate_grant': data['enabled_write_tools'] = ['hermes_skill:disable']*2
    raw = json.dumps(data).encode(); (tmp_path/'state.json').write_bytes(raw)
    with pytest.raises(ConfigError): ProductStore(tmp_path, 'hermes')
    assert (tmp_path/'state.json').read_bytes() == raw
