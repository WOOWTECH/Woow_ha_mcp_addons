"""0.2.0 (owner decision 2026-10-15): the full add-on. Every shipped product serves its pinned child's complete tool
surface, with the child's own schemas and validation; every tool and write is on by default and can be turned off.

What stays the gateway's: the token (Bearer or secret path), sessions, slots, request size, the name allowlist (the
child's classified tools), `disabled`, write grants (tool, or tool:operation of a mixed tool), refusals as JSON-RPC
errors, provider-safe listed schemas and log redaction. LOCAL/MOCK children here; real children in
test_full_surface_runtime below and tests/test_expansion_runtime.py.
"""
import asyncio
from contextlib import closing
import copy
import json

import httpx
import pytest

from mcp_admin_core import gateway
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import TOP_LEVEL_REFUSED, ToolCallRefused, authorize, child_input_schema
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from mcp_admin_core.surface import FULL_PRODUCTS, MIXED, READ, UNCERTAIN, WRITE, full_tools
from n8n_adapter import TOOLS as N8N_TOOLS, child_spec as n8n_spec
from owned_runtime import Endpoint
from test_expansion_policy import call
from test_expansion_runtime import fake_api
from test_real_products import connection, rpc
from tool_refusal import refused

COUNTS = {'odoo': 41, 'n8n': 28, 'hermes': 11, 'opendesign': 15, 'emqx': 39, 'litellm': 40, 'nextcloud': 9}
ACCEPT = {'Accept': 'application/json, text/event-stream'}
SESSION = {'Mcp-Session-Id': 'child-session'}


def tools_of(product):
    return N8N_TOOLS if product == 'n8n' else TOOLS[product]


def test_every_child_tool_is_served():
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('inventory', root / 'scripts/tool_inventory.py')
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    sources, _ = inventory.source_inventory()
    for product in FULL_PRODUCTS:
        tools = tools_of(product)
        assert set(tools) == set(sources[product]), product  # the pinned sources' own names, no more, no less
        assert len(tools) == COUNTS[product], product
        assert all(tool.child_schema for tool in tools.values())
        classified = sum(len(m.get(product, '').split()) for m in (READ, WRITE, MIXED, UNCERTAIN))
        assert classified == COUNTS[product]
    assert full_tools('n8n').keys() == N8N_TOOLS.keys()


@pytest.fixture
def emqx_store(tmp_path):
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        yield store


def child(replies, seen):
    def answer(request):
        message = json.loads(request.content)
        seen.append(message)
        reply = replies(message) if callable(replies) else replies
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message.get('id'), 'result': reply})
    return answer


async def post(store, tools, replies, message, path=None, headers=None):
    seen = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(child(replies, seen))) as to_child:
        _, app = make_apps(store, tools, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
            path = path or '/mcp'
            auth = {} if path != '/mcp' else {'Authorization': 'Bearer ' + store.load().token}
            response = await asyncio.wait_for(client.post(path, headers={**ACCEPT, **SESSION, **auth, **(headers or {})},
                                                          json=message), 10)
            return response, seen


async def test_tools_list_relays_the_child_schema_made_provider_safe(emqx_store):
    child_schema = {'type': 'object', 'properties': {'clientid': {'type': 'string', 'maxLength': 256}},
                    'required': ['clientid'], 'additionalProperties': False}
    combinator = {'anyOf': [{'type': 'object', 'properties': {'operation': {'const': 'read'}}, 'required': ['operation']},
                            {'type': 'object', 'properties': {'operation': {'const': 'create'}, 'user_id': {'type': 'string'}},
                             'required': ['operation', 'user_id']}]}
    listed = {'tools': [
        {'name': 'emqx_kick_client', 'description': 'Kick', 'inputSchema': child_schema,
         'outputSchema': {'$ref': 'https://example.invalid'}, 'icons': [{'src': 'https://example.invalid'}],
         'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'title': 'Kick'}},
        {'name': 'emqx_manage_authn_users', 'inputSchema': combinator},
        {'name': 'emqx_list_clients', 'inputSchema': 'not a schema', 'annotations': {'readOnlyHint': True}},
        {'name': 'emqx_new_upstream_tool', 'inputSchema': {'type': 'object'}},  # not classified here: never listed
    ]}
    response, seen = await post(emqx_store, TOOLS['emqx'], listed, {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert response.status_code == 200, response.text
    tools = {t['name']: t for t in response.json()['result']['tools']}
    assert set(tools) == {'emqx_kick_client', 'emqx_manage_authn_users', 'emqx_list_clients'}
    kick = tools['emqx_kick_client']
    assert kick['inputSchema'] == child_schema and 'outputSchema' not in kick and 'icons' not in kick
    # A write tool never relays the relaxing hints; a read tool does.
    assert kick['annotations'] == {'title': 'Kick'}
    assert tools['emqx_list_clients']['annotations'] == {'readOnlyHint': True}
    assert tools['emqx_list_clients']['inputSchema'] == {'type': 'object'}  # unreadable child schema
    flat = tools['emqx_manage_authn_users']['inputSchema']
    assert flat['type'] == 'object' and not TOP_LEVEL_REFUSED & flat.keys()
    assert 'operation' in flat['properties'] and 'operation' in flat.get('required', [])


def test_child_input_schema_never_raises():
    for schema in (None, [], 'x', {'$ref': '#/$defs/missing'}, {'oneOf': 'x'}, {'type': 'object', 'properties': []}):
        flat = child_input_schema(schema)
        assert flat.get('type') == 'object' and not TOP_LEVEL_REFUSED & flat.keys()
        json.dumps(flat)


async def test_arguments_reach_the_child_unchanged(emqx_store):
    arguments = {'topic': 'owned/test', 'payload': 'x' * 1000, 'qos': 1, 'retain': False,
                 'nested': {'any': ['shape', {'the': 'child decides'}]}, 'extra_key': None}
    message = call('emqx_publish', copy.deepcopy(arguments))
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, message)
    assert response.status_code == 200, response.text
    assert seen[-1]['params'] == {'name': 'emqx_publish', 'arguments': arguments}


async def test_a_large_request_within_the_new_limit_is_forwarded(emqx_store):
    # 0.2.0: 16 MiB (Nextcloud uploads up to 10 MiB as base64); the old 256 KiB limit refused this.
    payload = 'A' * (13 * 1024 * 1024)
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, call('emqx_publish', {'topic': 't', 'payload': payload}))
    assert response.status_code == 200 and seen[-1]['params']['arguments']['payload'] == payload
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []},
                                call('emqx_publish', {'topic': 't', 'payload': 'A' * (gateway.MAX_REQUEST + 1)}))
    assert response.status_code == 413 and seen == []


@pytest.mark.parametrize('arguments', [[], 'x', 1, None])
async def test_arguments_that_are_not_an_object_are_refused(emqx_store, arguments):
    message = call('emqx_list_clients', arguments)
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, message)
    assert refused(response, 'Invalid params') and seen == []
    assert response.json()['error']['data']['errors'][0]['type'] == 'dict_type'


async def test_unknown_disabled_and_ungranted_tools_never_reach_the_child(emqx_store):
    for name in ('emqx_new_upstream_tool', 'definitely_not_a_tool'):
        response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, call(name, {}))
        assert refused(response, 'Unknown tool') and seen == []
    emqx_store.update(disabled=['emqx_list_clients'])
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, call('emqx_list_clients', {}))
    assert refused(response, 'Unknown tool') and seen == []
    emqx_store.update(enabled_write_tools=[g for g in emqx_store.load().enabled_write_tools if g != 'emqx_publish'])
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, call('emqx_publish', {'topic': 't'}))
    assert refused(response, 'Unknown tool') and seen == []


@pytest.mark.parametrize('arguments,allowed', [
    ({'operation': 'read'}, True),               # a read operation never needs a grant
    ({'operation': 'create', 'user_id': 'u'}, False),  # its own grant was revoked
    ({'operation': 'delete', 'user_id': 'u'}, True),   # another operation keeps its grant
    ({}, True),                                  # required selector left out: the child refuses it
    ({'operation': 'purge'}, False),             # not classified here: could be a new write, needs every grant
    ({'operation': ['create']}, False),
])
def test_mixed_tool_operation_grants(tmp_path, arguments, allowed):
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        store.update(enabled_write_tools=[g for g in store.load().enabled_write_tools
                                          if g != 'emqx_manage_authn_users:create'])
        message = call('emqx_manage_authn_users', arguments)
        if allowed:
            assert authorize(message, TOOLS['emqx'], store.load()) == 'tools/call'
        else:
            with pytest.raises(ToolCallRefused) as refusal:
                authorize(message, TOOLS['emqx'], store.load())
            assert refusal.value.kind == 'operation_not_permitted'


def test_an_omitted_selector_is_the_sources_default_read(tmp_path):
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        store.update(enabled_write_tools=[])
        for name in ('hermes_tools', 'hermes_session', 'hermes_cron', 'hermes_config', 'hermes_model', 'hermes_gateway'):
            assert authorize(call(name, {}), TOOLS['hermes'], store.load()) == 'tools/call', name
        with pytest.raises(ToolCallRefused):
            authorize(call('hermes_tools', {'action': 'enable', 'toolset': 'x'}), TOOLS['hermes'], store.load())


@pytest.mark.parametrize('secret', ['right', 'wrong', 'revoked'])
async def test_secret_path_serves_the_full_surface_and_still_hides_a_wrong_token(emqx_store, secret):
    token = emqx_store.load().token
    if secret == 'revoked':
        emqx_store.update(token=None)
    path = f'/private_{token if secret != "wrong" else "x" * 43}/mcp'
    response, seen = await post(emqx_store, TOOLS['emqx'], {'content': []}, call('emqx_publish', {'topic': 't'}), path=path)
    if secret == 'right':
        assert response.status_code == 200 and seen[-1]['params']['name'] == 'emqx_publish'
    else:
        assert response.status_code == 404 and seen == []
        assert token not in response.text


@pytest.mark.parametrize('product', FULL_PRODUCTS)
async def test_real_child_lists_its_complete_surface(tmp_path, product):
    """A new state against the real pinned child: tools/list through the gateway is every child tool, with
    provider-safe schemas (the private readiness probes stay unlisted)."""
    with fake_api() as (url, events, mutations, failures):
        store = ProductStore(tmp_path / 'state', product)
        if product == 'n8n':
            store.update(backend_url=url, backend_key='DUMMY')
        else:
            store.update(connection=connection(product, url))
        endpoint = Endpoint(product)
        process = endpoint.supervisor((n8n_spec if product == 'n8n' else child_spec)(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as to_child:
                _, app = make_apps(store, tools_of(product), to_child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, **ACCEPT}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'owned-test', 'version': '0'}}}
                    async with asyncio.timeout(25):
                        while True:
                            try:
                                result = await rpc(client, '/mcp', headers, init)
                                break
                            except ValueError:
                                await asyncio.sleep(.1)
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    names = [t['name'] for t in listed['tools']]
                    assert set(names) == set(tools_of(product)) and len(names) == COUNTS[product], (
                        product, sorted(set(tools_of(product)) - set(names)))
                    for tool in listed['tools']:
                        schema = tool['inputSchema']
                        assert schema.get('type') == 'object' and not TOP_LEVEL_REFUSED & schema.keys(), tool['name']
                    assert mutations == [] and not failures
                    await client.delete('/mcp', headers=headers)
        finally:
            await process.stop(); endpoint.close(); store.close()
