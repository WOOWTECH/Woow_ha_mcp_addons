"""n8n-only authenticated ingress bounds before policy or child dispatch."""
import asyncio
import json

import httpx
import pytest

from mcp_admin_core import gateway as gateway_module
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS as PRODUCT_TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_n8n_exposure_policy import MIXED


N8N_BODY_LIMIT = 4 * 1024 * 1024
SESSION = "owned-session"


class Child:
    def __init__(self):
        self.seen = []

    def __call__(self, request):
        self.seen.append(request)
        message = json.loads(request.content)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": message["id"],
            "result": {"content": [{"type": "text", "text": "ok"}]},
        })


@pytest.fixture
def n8n_store(tmp_path):
    store = ProductStore(tmp_path / "n8n", "n8n")
    yield store
    store.close()


@pytest.fixture
def emqx_store(tmp_path):
    store = ProductStore(tmp_path / "emqx", "emqx")
    store.update(connection={
        "url": "http://127.0.0.1:18083",
        "api_key": "DUMMY",
        "api_secret": "DUMMY",
    })
    yield store
    store.close()


def tool_call(arguments, *, name="search_nodes"):
    return {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def encoded_call_of_size(size):
    message = tool_call({"query": ""})
    empty = json.dumps(message, separators=(",", ":")).encode()
    message["params"]["arguments"]["query"] = "x" * (size - len(empty))
    encoded = json.dumps(message, separators=(",", ":")).encode()
    assert len(encoded) == size
    return encoded


def request_target(store, route, *, valid=True):
    if route == "bearer":
        token = store.load().token if valid else "wrong-token"
        return "/mcp", {"Authorization": "Bearer " + token}
    token = store.load().token if valid else "wrong-token"
    return "/private_" + token + "/mcp", {}


async def send(store, tools, child, content, route="bearer", *, valid=True, method="POST", app_options=None,
               extra_headers=None):
    path, auth = request_target(store, route, valid=valid)
    headers = {**auth, "Accept": "application/json, text/event-stream",
               "Content-Type": "application/json", "Mcp-Session-Id": SESSION, **(extra_headers or {})}
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, tools, to_child, **(app_options or {}))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://mcp") as client:
            return await asyncio.wait_for(client.request(method, path, headers=headers, content=content), 10)


def encoded(message):
    return json.dumps(message, separators=(",", ":")).encode()


def assert_rpc_error(response, status, ident, code, message):
    assert response.status_code == status
    assert response.json() == {
        "jsonrpc": "2.0", "id": ident,
        "error": {"code": code, "message": message},
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("route", ["bearer", "private"])
async def test_n8n_body_over_four_mib_is_json_rpc_413_before_child(n8n_store, route):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, encoded_call_of_size(N8N_BODY_LIMIT + 1), route)
    assert_rpc_error(response, 413, None, -32602, "MCP request exceeds 4194304 bytes")
    assert child.seen == []


async def test_n8n_chunked_body_over_four_mib_is_json_rpc_413_before_child(n8n_store):
    async def chunks():
        yield b'{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search_nodes","arguments":{"query":"'
        for _ in range(4):
            yield b"x" * (1024 * 1024)
        yield b'"}}}'

    child = Child()
    response = await send(
        n8n_store, N8N_TOOLS, child, chunks(), extra_headers={"Content-Length": "1"})
    assert_rpc_error(response, 413, None, -32602, "MCP request exceeds 4194304 bytes")
    assert child.seen == []


@pytest.mark.parametrize("route", ["bearer", "private"])
@pytest.mark.parametrize("arguments", [
    {"items": [0] * 10_001},
    {f"field_{index}": 0 for index in range(10_001)},
], ids=["flat-array", "flat-object"])
async def test_n8n_argument_element_budget_is_json_rpc_413_before_child(n8n_store, route, arguments):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, encoded(tool_call(arguments)), route)
    assert_rpc_error(response, 413, 7, -32602, "MCP tool arguments exceed 10000 elements")
    assert child.seen == []


@pytest.mark.parametrize("route", ["bearer", "private"])
async def test_n8n_argument_depth_over_64_is_parse_error_before_child(n8n_store, route):
    arguments = {}
    nested = arguments
    for _ in range(65):
        nested["next"] = {}
        nested = nested["next"]
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, encoded(tool_call(arguments)), route)
    assert_rpc_error(response, 413, None, -32602, "MCP JSON exceeds 64 levels of nesting")
    assert child.seen == []


async def test_n8n_invalid_json_is_parse_error_before_child(n8n_store):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, b'{"jsonrpc":"2.0",')
    assert_rpc_error(response, 400, None, -32700, "Invalid or excessively nested JSON")
    assert child.seen == []


@pytest.mark.parametrize("content", [
    (b'{"jsonrpc":"2.0","id":7,"id":8,"method":"tools/call",'
     b'"params":{"name":"search_nodes","arguments":{"query":"x"}}}'),
    (b'{"jsonrpc":"2.0","id":7,"method":"tools/call",'
     b'"params":{"name":"search_nodes","arguments":{"query":NaN}}}'),
    (b'{"jsonrpc":"2.0","id":7,"method":"tools/call",'
     b'"params":{"name":"search_nodes","arguments":{"query":1e400}}}'),
    (b'{"jsonrpc":"2.0","id":7,"method":"tools/call",'
     b'"params":{"name":"search_nodes","arguments":{"query":"\\ud800"}}}'),
], ids=["duplicate-key", "nan", "overflowing-float", "lone-surrogate"])
async def test_n8n_strict_json_regressions_are_parse_errors_before_child(n8n_store, content):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, content)
    assert_rpc_error(response, 400, None, -32700, "Invalid or excessively nested JSON")
    assert child.seen == []


async def test_n8n_body_read_timeout_is_bounded_before_child(n8n_store, monkeypatch):
    async def slow_body():
        await asyncio.sleep(1)
        yield b"{}"

    monkeypatch.setattr(gateway_module, "BODY_SECONDS", 0.01)
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, slow_body())
    assert response.status_code == 408
    assert response.json() == {"error": "request denied"}
    assert child.seen == []


async def test_n8n_exact_body_and_argument_boundaries_reach_child(n8n_store):
    child = Child()
    body_response = await send(n8n_store, N8N_TOOLS, child, encoded_call_of_size(N8N_BODY_LIMIT))
    element_response = await send(
        n8n_store, N8N_TOOLS, child, encoded(tool_call({"items": [0] * 9_999})))
    arguments = {}
    nested = arguments
    # JSON message root + params + arguments consume three of the shared 64 levels.
    for _ in range(61):
        nested["next"] = {}
        nested = nested["next"]
    depth_response = await send(n8n_store, N8N_TOOLS, child, encoded(tool_call(arguments)))
    assert [body_response.status_code, element_response.status_code, depth_response.status_code] == [200, 200, 200]
    assert len(child.seen) == 3


def encoded_structure_case(kind, count):
    if kind == "output":
        decoded = {"query": "webhook", "extra": [0] * count}
        return tool_call({"output": json.dumps(decoded, separators=(",", ":"))})
    if kind == "schema-array":
        return tool_call({"fields": json.dumps(["id"] * count)}, name="search_templates")
    decoded = {f"field_{index}": 0 for index in range(count)}
    return tool_call({"nodeType": "nodes-base.noOp", "config": json.dumps(decoded, separators=(",", ":"))},
                     name="validate_node")


@pytest.mark.parametrize("kind,count", [
    ("output", 9_998),
    ("schema-array", 10_000),
    ("schema-object", 9_999),
])
async def test_n8n_child_decoded_structures_share_element_budget(n8n_store, kind, count):
    child = Child()
    message = encoded_structure_case(kind, count)
    response = await send(n8n_store, N8N_TOOLS, child, encoded(message))
    assert_rpc_error(response, 413, 7, -32602, "MCP tool arguments exceed 10000 elements")
    assert child.seen == []


@pytest.mark.parametrize("kind,count", [
    ("output", 9_997),
    ("schema-array", 9_999),
    ("schema-object", 9_998),
])
async def test_n8n_child_decoded_structures_allow_exact_boundary_with_canonical_output(
        n8n_store, kind, count):
    child = Child()
    message = encoded_structure_case(kind, count)
    response = await send(n8n_store, N8N_TOOLS, child, encoded(message))
    assert response.status_code == 200
    assert len(child.seen) == 1
    if kind == 'output':
        message['params']['arguments'] = json.loads(message['params']['arguments']['output'])
    assert json.loads(child.seen[0].content) == message


async def test_n8n_nested_encoded_strings_share_four_mib_decoding_budget(n8n_store):
    child = Child()
    inner = json.dumps({"blob": "x" * 1_100_000}, separators=(",", ":"))
    outer = json.dumps({"first": inner, "second": inner}, separators=(",", ":"))
    message = tool_call({"packed": outer})
    assert len(encoded(message)) < N8N_BODY_LIMIT
    response = await send(n8n_store, N8N_TOOLS, child, encoded(message))
    assert_rpc_error(response, 413, 7, -32602, "Encoded MCP arguments exceed decoding budget")
    assert child.seen == []


async def test_n8n_encoded_depth_error_preserves_parsed_request_id(n8n_store):
    child = Child()
    deep = "[" * 65 + "0" + "]" * 65
    response = await send(n8n_store, N8N_TOOLS, child, encoded(tool_call({"packed": deep})))
    assert_rpc_error(response, 413, 7, -32602, "MCP JSON exceeds 64 levels of nesting")
    assert child.seen == []


@pytest.mark.parametrize('route', ['bearer','private'])
@pytest.mark.parametrize('kind', ['elements','depth','decoded_bytes'])
async def test_exposure_wrapper_is_bounded_before_normalization(n8n_store, route, kind):
    inner = {'mode':'list','exposeToMcp':True}
    if kind == 'elements':
        inner['extra'] = [0] * 10_001
    elif kind == 'depth':
        inner['extra'] = '[' * 65 + '0' + ']' * 65
    else:
        inner['first'] = json.dumps({'blob':'x' * 1_100_000})
        inner['second'] = inner['first']
    message = tool_call({'output':json.dumps(inner)}, name='n8n_workflow_versions')
    child = Child()
    response = await send(n8n_store,N8N_TOOLS,child,encoded(message),route)
    assert response.status_code == 413
    assert response.json()['error']['code'] == -32602
    assert child.seen == []


@pytest.mark.parametrize('route', ['bearer','private'])
async def test_exposure_authorization_and_canonical_forwarding_over_both_routes(n8n_store, route):
    n8n_store.update(backend_url='https://offline.invalid',backend_key='synthetic',
                     enabled_write_tools=[],writes_enabled=False)
    args = {'mode':'list','source':'native','workflowId':'synthetic','exposeToMcp':True}
    message = tool_call({'mode':'list','exposeToMcp':False,'output':json.dumps(args)},
                        name='n8n_workflow_versions')
    child = Child()
    response = await send(n8n_store,N8N_TOOLS,child,encoded(message),route)
    assert response.json()['error']['code'] == -32602
    assert response.json()['error']['message'] == 'Operation not permitted'
    assert child.seen == []
    n8n_store.update(enabled_write_tools=['n8n_update_partial_workflow'])
    response = await send(n8n_store,N8N_TOOLS,child,encoded(message),route)
    assert response.status_code == 200 and 'error' not in response.json()
    assert len(child.seen) == 1
    assert json.loads(child.seen[0].content)['params']['arguments'] == args


@pytest.mark.parametrize('route', ['bearer','private'])
@pytest.mark.parametrize('name,selector,read,write', MIXED)
async def test_effective_write_selector_cannot_reach_transport_until_granted(
        n8n_store,route,name,selector,read,write):
    n8n_store.update(backend_url='https://offline.invalid',backend_key='synthetic',
                     enabled_write_tools=[],writes_enabled=False)
    inner = {selector:write,'workflowId':'synthetic','id':'synthetic'}
    message = tool_call({selector:read,'output':json.dumps(inner)},name=name)
    child = Child()
    for denied in (False,True):
        if denied:
            n8n_store.update(enabled_write_tools=[name+':'+write],denied_operations={name:[write]})
        response = await send(n8n_store,N8N_TOOLS,child,encoded(message),route)
        assert response.json()['error']['message'] == 'Operation not permitted'
        assert response.json()['error']['code'] == -32602
        assert child.seen == []
    n8n_store.update(enabled_write_tools=[name+':'+write],denied_operations={})
    response = await send(n8n_store,N8N_TOOLS,child,encoded(message),route)
    assert response.status_code == 200 and 'error' not in response.json()
    assert len(child.seen) == 1
    assert json.loads(child.seen[0].content)['params']['arguments'] == inner


async def test_n8n_nonidentity_content_encoding_is_415_without_reading_body(n8n_store):
    async def must_not_be_consumed():
        raise AssertionError("encoded request body was consumed")
        yield b"compressed"

    child = Child()
    response = await send(
        n8n_store, N8N_TOOLS, child, must_not_be_consumed(),
        extra_headers={"Content-Encoding": "gzip"})
    assert_rpc_error(response, 415, None, -32602, "Compressed MCP requests are not supported")
    assert child.seen == []


async def test_n8n_invalid_content_length_is_json_rpc_400_before_body(n8n_store):
    async def must_not_be_consumed():
        raise AssertionError("invalid-length request body was consumed")
        yield b"body"

    child = Child()
    response = await send(
        n8n_store, N8N_TOOLS, child, must_not_be_consumed(),
        extra_headers={"Content-Length": "not-a-number"})
    assert_rpc_error(response, 400, None, -32600, "Invalid Content-Length")
    assert child.seen == []


async def test_non_n8n_keeps_shared_sixteen_mib_body_limit(emqx_store):
    child = Child()
    message = tool_call({"padding": "x" * N8N_BODY_LIMIT}, name="emqx_list_clients")
    response = await send(emqx_store, PRODUCT_TOOLS["emqx"], child, encoded(message))
    assert response.status_code == 200
    assert len(child.seen) == 1


@pytest.mark.parametrize("route,expected", [("bearer", 401), ("private", 404)])
async def test_wrong_token_is_refused_without_consuming_or_echoing_body(n8n_store, route, expected):
    canary = "MUST_NOT_ECHO_N8N_REQUEST"

    async def must_not_be_consumed():
        raise AssertionError("unauthorized request body was consumed")
        yield canary.encode()

    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, must_not_be_consumed(), route, valid=False)
    assert response.status_code == expected
    assert canary not in response.text
    assert child.seen == []


@pytest.mark.parametrize("route", ["bearer", "private"])
async def test_unconfigured_backend_is_denied_before_child_on_both_auth_routes(n8n_store, route):
    child = Child()
    response = await send(
        n8n_store, N8N_TOOLS, child,
        encoded(tool_call({}, name="n8n_list_workflows")), route,
        app_options={
            "listing": [],
            "availability": lambda: {"child": "running", "ready": True,
                                     "backend": "unknown", "reason": None},
        },
    )
    assert response.status_code == 200
    assert response.json()["error"] == {
        "code": -32603, "message": "Backend not configured",
        "data": {"tool": "n8n_list_workflows"},
    }
    assert child.seen == []


async def test_n8n_json_rpc_batch_remains_wholly_denied_before_child(n8n_store):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, encoded([tool_call({}), tool_call({})]))
    assert response.status_code == 403
    assert response.json() == {"error": "request denied"}
    assert child.seen == []


async def test_n8n_json_rpc_batch_is_budgeted_before_whole_batch_denial(n8n_store):
    child = Child()
    response = await send(
        n8n_store, N8N_TOOLS, child,
        encoded([tool_call({"items": [0] * 10_001}), tool_call({})]))
    assert_rpc_error(response, 413, 7, -32602, "MCP tool arguments exceed 10000 elements")
    assert child.seen == []


async def test_n8n_string_arguments_are_budgeted_but_not_coerced_by_gateway(n8n_store):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, encoded(tool_call("{}")))
    assert response.status_code == 200
    assert response.json()["error"]["message"] == "Invalid params"
    assert child.seen == []


@pytest.mark.parametrize("route", ["bearer", "private"])
@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("content,expected", [
    (b"x", 400),
    (b"x" * (N8N_BODY_LIMIT + 1), 413),
], ids=["nonempty", "over-four-mib"])
async def test_n8n_other_mcp_methods_cannot_bypass_four_mib_body_bound(
        n8n_store, route, method, content, expected):
    child = Child()
    response = await send(n8n_store, N8N_TOOLS, child, content, route, method=method)
    assert response.status_code == expected
    if expected == 413:
        assert_rpc_error(response, 413, None, -32602, "MCP request exceeds 4194304 bytes")
    else:
        assert response.json() == {"error": "request denied"}
    assert child.seen == []
