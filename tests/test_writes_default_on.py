"""Owner decision 2026-10-15: the full add-on, every tool and every write on by default.

A new state (first boot) and every state migrated to schema 4 (from a 0.1.x schema 3, or 1/2 through 3) hold every
write grant and writes_enabled true; the migration runs once and keeps the token, connection, endpoint and disabled
list. After that the panel's choices are kept: a revoked grant stays revoked across restarts.
"""
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import Denied, ToolCallRefused, authorize, enabled
from mcp_admin_core.products import PRODUCTS, ProductStore, TOOLS, fresh_write_grants, write_grants
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_policy import call
from test_real_products import connection

ROOT = Path(__file__).resolve().parents[1]
ALL = (*PRODUCTS, 'n8n')
FULL = tuple(p for p in ALL if p != 'odoo-manage')
# One representative write call per product (exact grant shown).
WRITE_CALLS = {
    'odoo': ('execute_method', {'model': 'res.partner', 'method': 'write', 'args': [[1], {'name': 'x'}]}),
    'hermes': ('hermes_config', {'action': 'set', 'key': 'model.default', 'value': 'x'}),
    'opendesign': ('send_message', {'project_id': '12345678-1234-1234-1234-123456789abc', 'message': 'x'}),
    'emqx': ('emqx_publish', {'topic': 'owned/test', 'payload': 'x'}),
    'litellm': ('litellm_generate_key', {}),
    'nextcloud': ('delete_file_checked', {'path': 'a.txt', 'expected_etag': '"e"'}),
    'n8n': ('n8n_manage_credentials', {'action': 'create', 'name': 'x', 'type': 'x', 'data': {}}),
}


def tools_of(product):
    return N8N_TOOLS if product == 'n8n' else TOOLS[product]


def grants_of(product):
    return {g for name, tool in tools_of(product).items() for g in tool.grants(name)}


def grant_of(product):
    name, arguments = WRITE_CALLS[product]
    tool = tools_of(product)[name]
    return name if tool.write else f'{name}:{arguments[tool.selector]}'


def test_grant_sets_match_the_full_tools():
    for product in ALL:
        assert write_grants(product) == grants_of(product), product
    assert {'hermes_config:set', 'hermes_mcp:add', 'hermes_cron:create', 'hermes_chat'} <= write_grants('hermes')
    assert {'n8n_manage_credentials:create', 'n8n_test_workflow', 'n8n_workflow_versions:rollback'} <= write_grants('n8n')
    assert {'execute_method', 'execute_approved_write', 'chatter_post'} <= write_grants('odoo')
    assert {'litellm_generate_key', 'litellm_chat_completion'} <= write_grants('litellm')
    assert {'emqx_publish', 'emqx_manage_authn_users:create'} <= write_grants('emqx')


@pytest.mark.parametrize('product', ALL)
def test_new_state_enables_every_tool_and_write(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.schema_version == 4 and state.writes_enabled is True and state.disabled == []
        if product == 'odoo-manage':
            # Retired; its writers require an existing MCP module connection (mode 'module'); a new state has none.
            assert state.enabled_write_tools == [] and fresh_write_grants(product) == []
            return
        assert state.enabled_write_tools == sorted(grants_of(product)) == fresh_write_grants(product)
        tools = tools_of(product)
        assert all(enabled(name, tools, state) for name in tools)
        stored = json.loads(store.path.read_text())
        assert stored['writes_enabled'] is True and stored['enabled_write_tools'] == state.enabled_write_tools


@pytest.mark.parametrize('product', sorted(WRITE_CALLS))
def test_a_write_is_allowed_by_default_and_a_revoked_grant_stays_revoked(tmp_path, product):
    name, arguments = WRITE_CALLS[product]
    tools = tools_of(product)
    grant = grant_of(product)
    with closing(ProductStore(tmp_path, product)) as store:
        message = call(name, arguments)
        assert authorize(message, tools, store.load()) == 'tools/call'
        assert message['params']['arguments'] == arguments  # forwarded unchanged: the child validates
        remaining = [g for g in store.load().enabled_write_tools if g != grant]
        store.update(writes_enabled=False, enabled_write_tools=remaining)  # what the panel saves
    for _ in range(2):  # restarts: a schema 4 state is loaded as stored, never re-seeded
        with closing(ProductStore(tmp_path, product)) as store:
            state = store.load()
            assert state.writes_enabled is False and state.enabled_write_tools == remaining
            with pytest.raises(ToolCallRefused):
                authorize(call(name, arguments), tools, state)


@pytest.mark.parametrize('product', ALL)
def test_disabled_closes_a_tool_even_with_its_grant(tmp_path, product):
    tools = tools_of(product)
    name = next(iter(tools))
    with closing(ProductStore(tmp_path, product)) as store:
        store.update(disabled=[name])
    with closing(ProductStore(tmp_path, product)) as store:
        assert store.load().disabled == [name]
        with pytest.raises(ToolCallRefused) as refused:
            authorize(call(name, {}), tools, store.load())
        assert refused.value.kind == 'unknown_tool'


def v3_state(store, product, **changes):
    """A schema 3 state as 0.1.x wrote it: exact grants of the bounded surface, the legacy switch, disabled."""
    value = {**store.load().model_dump(), 'schema_version': 3, **changes}
    store.path.write_text(json.dumps(value))
    return value


@pytest.mark.parametrize('product', FULL)
def test_a_0_1_state_migrates_once_to_every_write(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        if product != 'n8n':
            store.update(connection=connection(product, 'http://127.0.0.1:9'))
        else:
            store.update(backend_url='http://127.0.0.1:9', backend_key='DUMMY')
        old = v3_state(store, product, writes_enabled=False, enabled_write_tools=[], disabled=[next(iter(tools_of(product)))],
                       endpoint='https://mcp.example.test/mcp')
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.schema_version == 4 and state.writes_enabled is True
        assert state.enabled_write_tools == fresh_write_grants(product) == sorted(grants_of(product))
        for key in ('token', 'child_token', 'connection', 'backend_url', 'backend_key', 'endpoint', 'disabled'):
            assert state.model_dump()[key] == old[key], key  # kept, disabled tools stay disabled
        assert json.loads(store.path.read_text())['schema_version'] == 4  # migrated durably
        store.update(enabled_write_tools=[])  # the administrator revokes everything after the upgrade
    with closing(ProductStore(tmp_path, product)) as store:
        assert store.load().enabled_write_tools == []  # the migration ran once


@pytest.mark.parametrize('product', ['hermes', 'n8n'])
def test_older_states_migrate_through_3_to_every_write(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        old = store.load().model_dump()
    old.pop('enabled_write_tools')
    old.update(schema_version=2, writes_enabled=False)
    if product == 'n8n':
        old = {k: v for k, v in old.items() if k not in ('product', 'connection')}
        old['schema_version'] = 1
    store.path.write_text(json.dumps(old))
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.schema_version == 4 and state.enabled_write_tools == fresh_write_grants(product)
        assert state.writes_enabled is True and state.token == old['token']


def test_odoo_manage_keeps_its_grants_on_migration(tmp_path):
    with closing(ProductStore(tmp_path, 'odoo-manage')) as store:
        v3_state(store, 'odoo-manage', writes_enabled=False, enabled_write_tools=[])
    with closing(ProductStore(tmp_path, 'odoo-manage')) as store:
        state = store.load()
        assert state.schema_version == 4 and state.enabled_write_tools == [] and state.writes_enabled is False


def test_a_future_or_foreign_state_is_refused_not_rewritten(tmp_path):
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        value = {**store.load().model_dump(), 'schema_version': 5}
    store.path.write_text(json.dumps(value))
    raw = store.path.read_bytes()
    with pytest.raises(Exception):
        ProductStore(tmp_path, 'emqx')
    assert store.path.read_bytes() == raw


def test_plain_v1_store_is_unchanged(tmp_path):
    # Production always runs ProductStore; a plain v1 Store (migration source, test fixture) keeps writes off.
    with closing(Store(tmp_path)) as store:
        assert store.load().writes_enabled is False


@pytest.mark.parametrize('product,grant', [('n8n', 'n8n_delete_workflow'), ('hermes', 'hermes_cron:delete'),
                                          ('opendesign', 'delete_project'), ('odoo', 'execute_method')])
async def test_panel_shows_all_writes_on_and_unticking_one_survives_restart(tmp_path, product, grant):
    """The unmodified production UI serializers on a new state: every write is ticked; saving with one unticked
    stores exactly the rest and survives a restart; that write is then refused."""
    async def role(_): return True
    tools = tools_of(product)
    with closing(ProductStore(tmp_path, product)) as store:
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, tools, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://local') as client:
                identity = {'x-remote-user-id': 'a' * 32}
                bootstrap = (await client.get('/api/bootstrap', headers=identity)).json()
                assert bootstrap['writes_enabled'] is True
                assert sorted(bootstrap['enabled_write_tools']) == sorted(grants_of(product))
                assert set(bootstrap['tools']) == set(tools)
                probe = subprocess.run(['node', '--input-type=module', '-e', '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {granularPolicy, toolRows, effectiveGrant, policyPayload} from './packages/mcp-admin-ui/src/contracts.js';
const [b, off] = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.equal(granularPolicy(b), true);
const ticked = [];
for (const row of toolRows(b)) {
  const operations = row.operations.length ? row.operations : row.write ? [null] : [];
  for (const operation of operations) {
    assert.equal(effectiveGrant(b, row, operation), true, row.name);  // every write is shown as allowed
    if ((operation === null ? row.name : `${row.name}:${operation}`) !== off) ticked.push({tool: row.name, operation});
  }
}
console.log(JSON.stringify(policyPayload(b, [], ticked)));
'''], cwd=ROOT, input=json.dumps([bootstrap, grant]), text=True, capture_output=True, timeout=10,
                    env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
                assert probe.returncode == 0, probe.stderr
                payload = json.loads(probe.stdout)
                assert payload['writes_enabled'] is False and grant not in payload['enabled_write_tools']
                response = await client.put('/api/policy', headers={**identity, 'x-csrf-token': bootstrap['csrf']},
                                            json=payload)
                assert response.status_code == 200, response.text
        expected = sorted(grants_of(product) - {grant})
        assert sorted(store.load().enabled_write_tools) == expected
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.writes_enabled is False and sorted(state.enabled_write_tools) == expected
        name, _, operation = grant.partition(':')
        arguments = {'action': operation, 'job_id': 'example'} if operation else {}
        with pytest.raises(Denied):
            authorize(call(name, arguments), tools, state)
