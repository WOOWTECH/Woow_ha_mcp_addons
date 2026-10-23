"""Owned state and mock child only: no live HA/backend or subprocess children."""
from contextlib import closing
import copy
import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict
from typing import Literal

from mcp_admin_core.capabilities import tool_catalog
from mcp_admin_core.config import ConfigError
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import Tool, ToolCallRefused, authorize, filter_list
from mcp_admin_core.products import ProductState, ProductStore
from mcp_admin_core.surface import FULL_PRODUCTS, full_tools, listing

NAME = 'n8n_executions'
TOOLS = full_tools('n8n')
IDENTITY = {'x-remote-user-id': 'operation-review'}


@pytest.mark.parametrize('version', [2, 3])
def test_legacy_all_on_clears_valid_denies_but_never_repairs_invalid_denies(tmp_path, version):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        value = store.load().model_dump()
    value.update(schema_version=version, denied_operations={NAME: ['get']})
    if version == 2:
        del value['enabled_write_tools']
    store.path.write_text(json.dumps(value))
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.load()
        assert state.denied_operations == {} and state.schema_version == 4
        assert state.token == value['token'] and state.enabled_write_tools
    value['denied_operations'] = {NAME: ['get', 'get']}
    store.path.write_text(json.dumps(value))
    before = store.path.read_bytes()
    with pytest.raises(ConfigError):
        ProductStore(tmp_path, 'n8n')
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('product,name', [(product, name) for product in FULL_PRODUCTS
    for name, tool in full_tools(product).items() if tool.operations])
def test_audited_selectors_defaults_and_denies_for_every_mixed_tool(tmp_path, product, name):
    registry = full_tools(product)
    tool = registry[name]
    snapshot = next(item for item in listing(product) if item['name'] == name)
    field = snapshot['inputSchema']['properties'][tool.selector]
    assert field.get('default') == tool.default_operation
    if 'enum' in field:
        assert set(field['enum']) == set(tool.operations)
    with closing(ProductStore(tmp_path, product)) as store:
        denied = tool.default_operation or tool.read_operations[0]
        state = store.update(denied_operations={name: [denied]})
        with pytest.raises(ToolCallRefused):
            authorize(call({tool.selector: denied}, name), registry, state)
        # Either its audited default is denied or no audited default exists.
        with pytest.raises(ToolCallRefused):
            authorize(call({}, name), registry, state)
        allowed = next(op for op in tool.operations if op != denied)
        assert authorize(call({tool.selector: allowed}, name), registry, state) == 'tools/call'


def call(arguments, name=NAME):
    return {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}


@pytest.mark.parametrize('product', FULL_PRODUCTS)
def test_schema4_addition_preserves_every_existing_field_and_reload(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'n8n':
            store.update(mcp_access_token='DUMMY-preserved-instance-token')
        state = store.update(writes_enabled=False, disabled=[next(iter(full_tools(product)))],
                             enabled_write_tools=store.load().enabled_write_tools[:1])
        old = state.model_dump()
    del old['denied_operations']
    store.path.write_text(json.dumps(old))
    with closing(ProductStore(tmp_path, product)) as reopened:
        assert reopened.load().model_dump() == {**old, 'denied_operations': {}}
        assert json.loads(reopened.path.read_text()) == {**old, 'denied_operations': {}}
        saved = reopened.update(denied_operations={'retired_tool': ['retired_operation']})
    with closing(ProductStore(tmp_path, product)) as reopened:
        assert reopened.load() == saved


@pytest.mark.parametrize('change', [
    {'denied_operations': None}, {'denied_operations': []}, {'denied_operations': {NAME: 'get'}},
    {'denied_operations': {NAME: [1]}}, {'denied_operations': {NAME: ['get', 'get']}},
    {'denied_operations': {NAME: []}}, {'denied_operations': {'bad:tool': ['get']}},
    {'denied_operations': {NAME: ['bad:operation']}}, {'schema_version': '4'}, {'unexpected': True},
])
def test_corrupt_state_is_never_rewritten(tmp_path, change):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        value = store.load().model_dump()
    value.pop('denied_operations')
    value.update(change)
    raw = json.dumps(value).encode()
    store.path.write_bytes(raw)
    with pytest.raises(ConfigError):
        ProductStore(tmp_path, 'n8n')
    assert store.path.read_bytes() == raw


@pytest.mark.parametrize('missing', ['token', 'child_token', 'enabled_write_tools', 'disabled', 'writes_enabled', 'endpoint'])
def test_new_default_never_repairs_other_missing_fields(tmp_path, missing):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        value = store.load().model_dump()
    value.pop('denied_operations')
    value.pop(missing)
    store.path.write_text(json.dumps(value))
    before = store.path.read_bytes()
    with pytest.raises(ConfigError):
        ProductStore(tmp_path, 'n8n')
    assert store.path.read_bytes() == before


def test_missing_new_field_after_startup_is_not_silently_reset(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        value = store.update(denied_operations={NAME: ['get']}).model_dump()
        del value['denied_operations']
        store.path.write_text(json.dumps(value))
        with pytest.raises(ConfigError):
            store.load()


def test_read_denies_default_and_independent_write_grants(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.update(denied_operations={NAME: ['get', 'delete']})
        for args in ({'action': 'list'}, {}):
            assert authorize(call(args), TOOLS, state) == 'tools/call'
        for op in ('get', 'delete'):
            with pytest.raises(ToolCallRefused, match='operation not permitted'):
                authorize(call({'action': op}), TOOLS, state)
        assert f'{NAME}:delete' in state.enabled_write_tools
        state = store.update(denied_operations={NAME: ['list']}, enabled_write_tools=[])
        assert authorize(call({'action': 'get'}), TOOLS, state) == 'tools/call'
        for args in ({}, {'action': 'list'}, {'action': 'delete'}):
            with pytest.raises(ToolCallRefused):
                authorize(call(args), TOOLS, state)
        state = store.update(denied_operations={})
        with pytest.raises(ToolCallRefused):
            authorize(call({'action': 'delete'}), TOOLS, state)
        state = store.update(disabled=[NAME])
        with pytest.raises(ToolCallRefused, match='tool not permitted'):
            authorize(call({'action': 'list'}), TOOLS, state)


@pytest.mark.parametrize('operation', [None, '', 'GET', 'new_operation', ['list'], {'action': 'list'}, 1, True])
def test_restricted_tool_unknown_or_malformed_selector_fails_closed(tmp_path, operation):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.update(denied_operations={NAME: ['get']})
        with pytest.raises(ToolCallRefused, match='operation not permitted') as error:
            authorize(call({'action': operation}), TOOLS, state)
        assert 'new_operation' not in json.dumps(error.value.error())


def test_required_selector_and_stale_metadata_fail_closed(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        name = 'n8n_manage_credentials'
        state = store.update(denied_operations={name: ['get']})
        with pytest.raises(ToolCallRefused):
            authorize(call({}, name), TOOLS, state)
        # A removed selector cannot turn a retained restriction into permission.
        registry = {name: Tool(TOOLS[name].arguments, child_schema=True)}
        with pytest.raises(ToolCallRefused):
            authorize(call({'action': 'list'}, name), registry, state)
        assert tool_catalog(registry, None, None, state)['policy_enabled_count'] == 0


def test_bounded_model_applies_its_normalized_default(tmp_path):
    class Arguments(BaseModel):
        model_config = ConfigDict(strict=True, extra='forbid')
        action: Literal['list', 'get'] = 'list'
    tools = {NAME: Tool(Arguments, selector='action', read_operations=('list', 'get'), default_operation='list')}
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.update(denied_operations={NAME: ['list']})
        with pytest.raises(ToolCallRefused):
            authorize(call({}), tools, state)
        assert authorize(call({'action': 'get'}), tools, state) == 'tools/call'


def test_capability_counts_and_list_match_actual_policy(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        registry = {NAME: TOOLS[NAME]}
        pinned = [item for item in listing('n8n') if item['name'] == NAME]
        state = store.update(denied_operations={NAME: ['get', 'retired']}, enabled_write_tools=[])
        for observed in (None, pinned):
            catalog = tool_catalog(registry, pinned, observed, state)
            item = catalog['items'][0]
            assert catalog['policy_enabled_count'] == 1
            assert catalog['operation_count'] == 3 and catalog['policy_enabled_operation_count'] == 1
            assert item['default_operation'] == 'list' and item['stale_denied_operations'] == ['retired']
            operations = {op['name']: op for op in item['operations']}
            assert operations['get']['denied'] is True and operations['get']['effective'] is False
            assert operations['list']['effective'] is (None if observed is None else True)
        state = store.update(denied_operations={NAME: ['get', 'list']})
        catalog = tool_catalog(registry, pinned, pinned, state)
        assert catalog['policy_enabled_count'] == catalog['effective_count'] == 0
        assert catalog['items'][0]['reason'] == 'operations_not_permitted'
        message = {'jsonrpc': '2.0', 'id': 1, 'result': {'tools': copy.deepcopy(pinned)}}
        filter_list(message, registry, state)
        assert message['result']['tools'] == []


async def test_policy_api_optional_field_validation_and_stale_roundtrip(tmp_path):
    async def role(_): return True
    def forbidden(_): raise AssertionError('policy editing must not call child')
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as child:
            admin, _ = make_apps(store, TOOLS, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://owned') as client:
                bootstrap = (await client.get('/api/bootstrap', headers=IDENTITY)).json()
                headers = {**IDENTITY, 'x-csrf-token': bootstrap['csrf']}
                assert bootstrap['denied_operations'] == {}
                assert bootstrap['capabilities']['capabilities']['operation_denies'] is True
                assert bootstrap['tools'][NAME]['default_operation'] == 'list'
                base = {'disabled': [], 'writes_enabled': False, 'enabled_write_tools': []}
                assert (await client.put('/api/policy', headers=headers, json={**base, 'denied_operations': {NAME: ['get']}})).status_code == 200
                # Both historical request shapes retain saved restrictions.
                for old in (base, {'disabled': [], 'writes_enabled': True}):
                    assert (await client.put('/api/policy', headers=headers, json=old)).status_code == 200
                    assert store.load().denied_operations == {NAME: ['get']}
                for denies in (None, [], {NAME: []}, {NAME: ['get', 'get']}, {NAME: [False]},
                               {NAME: 'get'}, {NAME: ['unknown']}, {'hermes_session': ['get']},
                               {'n8n_list_workflows': ['list']}):
                    before = store.path.read_bytes()
                    response = await client.put('/api/policy', headers=headers, json={**base, 'denied_operations': denies})
                    assert response.status_code == 400, response.text
                    assert store.path.read_bytes() == before
                saved = {NAME: ['get', 'retired'], 'retired_tool': ['removed']}
                store.update(denied_operations=saved)
                assert (await client.put('/api/policy', headers=headers, json={**base, 'denied_operations': saved})).status_code == 200
                fresh = (await client.get('/api/bootstrap', headers=IDENTITY)).json()
                assert fresh['denied_operations'] == saved
                assert (await client.put('/api/policy', headers=headers, json={**base, 'denied_operations': {}})).status_code == 200
                assert store.load().denied_operations == {}


@pytest.mark.parametrize('private', [False, True])
@pytest.mark.parametrize('sse', [False, True])
async def test_gateway_rejects_before_child_for_json_sse_and_both_token_paths(tmp_path, private, sse):
    seen = []
    def answer(request):
        message = json.loads(request.content)
        seen.append(message)
        payload = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': []}}
        if sse:
            return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, content=f'data: {json.dumps(payload)}\n\n'.encode())
        return httpx.Response(200, json=payload)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.update(denied_operations={NAME: ['get']})
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as child:
            _, public = make_apps(store, TOOLS, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(public), base_url='http://owned') as client:
                path = f'/private_{state.token}/mcp' if private else '/mcp'
                headers = {'Accept': 'application/json, text/event-stream', 'Mcp-Session-Id': 'owned-session'}
                if not private: headers['Authorization'] = 'Bearer ' + state.token
                for args in ({'action': 'list'}, {}):
                    response = await client.post(path, headers=headers, json=call(args))
                    assert response.status_code == 200
                    assert response.headers['content-type'].startswith('text/event-stream' if sse else 'application/json')
                assert len(seen) == 2
                for args in ({'action': 'get'}, {'action': None}, {'action': ['list']}, {'action': 'unknown'}):
                    response = await client.post(path, headers=headers, json=call(args))
                    assert response.status_code == 200 and response.json()['error']['message'] == 'Operation not permitted'
                    assert response.headers['content-type'] == 'application/json'
                assert len(seen) == 2
                # Same session reads updated policy, including omitted default.
                store.update(denied_operations={NAME: ['list']})
                response = await client.post(path, headers=headers, json=call({}))
                assert response.json()['error']['message'] == 'Operation not permitted' and len(seen) == 2
                for legacy in ('/sse', '/messages'):
                    assert (await client.get(legacy, headers=headers)).status_code == 404
