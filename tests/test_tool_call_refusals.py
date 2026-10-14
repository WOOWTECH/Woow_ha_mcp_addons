"""LOCAL/MOCK: 0.1.14 a refused well-formed tools/call is answered as JSON-RPC, not HTTP 403.

2026-10-14 field record: through Claude.ai, an Odoo aggregate_records group_by other than 'active', schema_catalog
limit > 1, get_model_fields with a field outside its allowlist, litellm_model_info with '/' in the id and an n8n
validate_workflow without nodes were all answered HTTP 403, which the client shows only as a transport failure. The
four refusals of a well-formed call (unknown or disabled tool, invalid arguments, write operation not granted,
backend not configured) are now HTTP 200 application/json JSON-RPC errors the model can read and act on, inside a
session (a refused call without a usable session id stays 403, as in 0.1.13). The policy itself is unchanged: the same
calls are refused, never reach the child, take no slot and open no session; the token check comes first as before. Every other Denied (malformed JSON-RPC, id, _meta, params) stays 403.
Both connection paths (/mcp with Bearer, /private_<token>/mcp) behave the same.
"""
import asyncio
from contextlib import closing
import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import (ARGUMENT_ERROR_LIMIT, ARGUMENT_ERROR_TEXT, FIXED_ARGUMENT_ERROR, Denied,
                                   ToolCallRefused, UnknownMethod, argument_errors, authorize)
from mcp_admin_core.products import TOOLS as PRODUCT_TOOLS, ProductStore
from n8n_adapter import TOOLS

ACCEPT = {"Accept": "application/json, text/event-stream"}
SESSION = {"Mcp-Session-Id": "child-session"}
MARK = "ZQXMARK"  # in every invalid value and key below; never in an answer
READ_TOOL = "tools_documentation"
WRITER = next(name for name, tool in TOOLS.items() if tool.write)
OPERATION_TOOL, OPERATION = next((name, tool.write_operations[0]) for name, tool in TOOLS.items()
                                 if tool.write_operations)
BACKEND_TOOL = "n8n_health_check"
assert TOOLS[BACKEND_TOOL].requires_backend and not TOOLS[READ_TOOL].write
REASON = "write operation disabled by the add-on policy; an administrator can enable it in the add-on panel"


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


class Forbidden:
    """A child that must never be reached."""
    def __call__(self, request):
        raise AssertionError("forwarded to the child: " + request.content.decode())


async def call(store, child, path, message, headers=None):
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            return await asyncio.wait_for(client.post(path, headers={**ACCEPT, **(headers or {})}, json=message), 10)


def bearer_path(store):
    return "/mcp", {"Authorization": "Bearer " + store.load().token}


def private_path(store):
    return "/private_" + store.load().token + "/mcp", {}


PATHS = [bearer_path, private_path]


def tool_call(name, arguments, ident=7):
    return {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def assert_json_rpc(response, ident, error):
    assert response.status_code == 200, response.content
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert "mcp-session-id" not in response.headers
    assert response.json() == {"jsonrpc": "2.0", "id": ident, "error": error}


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("ident", [7, "call-7"])
async def test_four_refusals_are_json_rpc_errors(store, route, ident):
    path, auth = route(store)
    headers = {**auth, **SESSION}
    cases = [
        (tool_call("no_such_tool_" + MARK, {}, ident),
         {"code": -32602, "message": "Unknown tool", "data": {"tool": "no_such_tool_" + MARK}}),
        # A write tool without its grant is the same answer as a tool that does not exist.
        (tool_call(WRITER, {"id": "1"}, ident), {"code": -32602, "message": "Unknown tool", "data": {"tool": WRITER}}),
        (tool_call(READ_TOOL, {"topic": 5}, ident),
         {"code": -32602, "message": "Invalid params", "data": {"tool": READ_TOOL, "errors": [
             {"field": "topic", "message": "Input should be a valid string", "type": "string_type"}]}}),
        (tool_call(OPERATION_TOOL, {"action": OPERATION, "name": "x"}, ident),
         {"code": -32602, "message": "Operation not permitted", "data": {"tool": OPERATION_TOOL, "reason": REASON}}),
        (tool_call(BACKEND_TOOL, {}, ident),
         {"code": -32603, "message": "Backend not configured", "data": {"tool": BACKEND_TOOL}}),
    ]
    for message, error in cases:
        assert_json_rpc(await call(store, Forbidden(), path, message, headers), ident, error)


@pytest.mark.parametrize("route", PATHS)
async def test_unknown_tool_name_is_cut_to_128_characters(store, route):
    path, auth = route(store)
    response = await call(store, Forbidden(), path, tool_call("t" * 500, {}), {**auth, **SESSION})
    assert response.status_code == 200 and response.json()["error"]["data"] == {"tool": "t" * 128}


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("name, arguments", [
    (READ_TOOL, {MARK + "_key": MARK + "_value"}),
    (READ_TOOL, {"topic": {MARK: MARK}}),
    (OPERATION_TOOL, {"action": MARK}),
    ("validate_workflow", {"workflow": {MARK + "_k": MARK + "_v", "nodes": [{MARK: MARK}]}}),
    ("search_nodes", {"query": MARK * 200, "limit": MARK}),
    (READ_TOOL, [MARK]),
    (READ_TOOL, MARK),
])
async def test_invalid_params_never_echo_the_arguments(store, route, name, arguments):
    path, auth = route(store)
    response = await call(store, Forbidden(), path, tool_call(name, arguments), {**auth, **SESSION})
    assert response.status_code == 200, response.content
    error = response.json()["error"]
    assert error["code"] == -32602 and error["message"] == "Invalid params"
    assert error["data"]["tool"] == name and set(error["data"]) == {"tool", "errors"}
    assert 1 <= len(error["data"]["errors"]) <= ARGUMENT_ERROR_LIMIT
    for entry in error["data"]["errors"]:
        assert set(entry) == {"field", "message", "type"}
        assert len(entry["message"]) <= ARGUMENT_ERROR_TEXT
    assert MARK.casefold() not in response.text.casefold()


@pytest.mark.parametrize("route", PATHS)
async def test_refusal_without_a_session_stays_403(store, route):
    """The reason is only given inside a session (as any tools/call needs one); without a usable session id the
    refusal is the 0.1.13 answer, 403, and an allowed call the 0.1.8 400."""
    path, auth = route(store)
    for message in (tool_call("no_such_tool", {}), tool_call(READ_TOOL, {"topic": 5}), tool_call(BACKEND_TOOL, {}),
                    tool_call(OPERATION_TOOL, {"action": OPERATION, "name": "x"})):
        for session in ({}, {"Mcp-Session-Id": "bad id"}, {"Mcp-Session-Id": "x" * 257}):
            response = await call(store, Forbidden(), path, message, {**auth, **session})
            assert response.status_code == 403 and response.json() == {"error": "request denied"}, session
    allowed = await call(store, Forbidden(), path, tool_call(READ_TOOL, {}), auth)
    assert allowed.status_code == 400


async def test_refusal_needs_the_token_first(store):
    async with httpx.AsyncClient(transport=httpx.MockTransport(Forbidden())) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            reference = await client.post("/no-such-path/mcp", headers=ACCEPT, json=tool_call("x", {}))
            for message in (tool_call("no_such_tool", {}), tool_call(READ_TOOL, {"topic": 5})):
                for headers in ({}, {"Authorization": "Bearer wrong"}):
                    response = await client.post("/mcp", headers={**ACCEPT, **SESSION, **headers}, json=message)
                    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
                response = await client.post("/private_wrong/mcp", headers={**ACCEPT, **SESSION}, json=message)
                assert response.status_code == 404 and response.content == reference.content


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("message", [
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": READ_TOOL, "arguments": {}, "extra": 1}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": 5, "arguments": {}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"arguments": {}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call"},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": []},
    {"jsonrpc": "2.0", "id": None, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 1.5, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
    {"jsonrpc": "2.0", "id": True, "method": "tools/call", "params": {"name": READ_TOOL, "arguments": {"topic": 5}}},
    {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "no_such_tool", "_meta": []}},
    {"jsonrpc": "1.0", "id": 7, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
    {"jsonrpc": "2.0", "id": 7, "method": "notifications/initialized"},
])
async def test_other_refusals_stay_403(store, route, message):
    path, auth = route(store)
    response = await call(store, Forbidden(), path, message, {**auth, **SESSION})
    assert response.status_code == 403 and response.json() == {"error": "request denied"}


async def test_refusal_takes_no_slot(store):
    """Answered before the 32 request slots: it still answers while every slot is held by a stuck child request."""
    gate = asyncio.Event()

    async def stuck(request):
        body = json.loads(request.content)
        assert body["method"] == "ping", body  # no refused call reaches the child
        await gate.wait()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(stuck)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            headers = {**ACCEPT, **SESSION, "Authorization": "Bearer " + store.load().token}
            ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
            held = [asyncio.create_task(client.post("/mcp", headers=headers, json=ping)) for _ in range(32)]
            await asyncio.sleep(.2)
            try:
                assert (await client.post("/mcp", headers=headers, json=ping)).status_code == 503  # slots are full
                for message in (tool_call("no_such_tool", {}), tool_call(READ_TOOL, {"topic": 5}),
                                tool_call(BACKEND_TOOL, {})):
                    response = await asyncio.wait_for(client.post("/mcp", headers=headers, json=message), 5)
                    assert response.status_code == 200 and response.json()["error"]["code"] in (-32602, -32603)
            finally:
                gate.set()
                await asyncio.gather(*held)


async def test_policy_change_after_the_slot_is_answered_the_same_way(store, monkeypatch):
    """A call allowed before its slot and refused when re-authorized inside it (the policy changed meanwhile) gets the
    same JSON-RPC answer; the slot is released and the child is not reached."""
    from mcp_admin_core import gateway
    calls = []
    original = gateway.authorize

    def flaky(message, tools, state):
        calls.append(message["method"])
        if len(calls) == 2:  # the re-authorization inside the slot
            state = state.model_copy(update={"disabled": [READ_TOOL]})
        return original(message, tools, state)

    monkeypatch.setattr(gateway, "authorize", flaky)
    path, auth = bearer_path(store)
    response = await call(store, Forbidden(), path, tool_call(READ_TOOL, {}), {**auth, **SESSION})
    assert_json_rpc(response, 7, {"code": -32602, "message": "Unknown tool", "data": {"tool": READ_TOOL}})
    assert calls == ["tools/call", "tools/call"]


async def test_call_allowed_on_fresh_state_is_forwarded(store, monkeypatch):
    """A refusal is decided again on fresh state before it is answered: a call the policy now allows is dispatched."""
    from mcp_admin_core import gateway
    calls, seen = [], []
    original = gateway.authorize

    def first_refused(message, tools, state):
        calls.append(1)
        if len(calls) == 1:
            raise ToolCallRefused("unknown_tool", message["params"]["name"])
        return original(message, tools, state)

    def child(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 7, "result": {"content": []}})

    monkeypatch.setattr(gateway, "authorize", first_refused)
    path, auth = private_path(store)
    response = await call(store, child, path, tool_call(READ_TOOL, {}), {**auth, **SESSION})
    assert response.status_code == 200 and response.json()["result"] == {"content": []}
    assert [body["params"]["name"] for body in seen] == [READ_TOOL]


# ---- authorize() and argument_errors() ----

@pytest.mark.parametrize("product, name, arguments, field, message, kind", [
    ("odoo", "aggregate_records", {"model": "res.partner", "group_by": [MARK + "_country_id"]}, "group_by.0",
     "Input should be 'active'", "literal_error"),
    ("odoo", "schema_catalog", {"limit": 5}, "limit", "Input should be less than or equal to 1", "less_than_equal"),
    ("odoo", "get_model_fields", {"model": "res.partner", "field_names": [MARK + "_email"]}, "field_names.0",
     "Input should be 'id', 'name', 'display_name' or 'active'", "literal_error"),
    ("litellm", "litellm_model_info", {"litellm_model_id": MARK + "/openai/gpt"}, "litellm_model_id",
     "String should match pattern '^[A-Za-z0-9_-]+$'", "string_pattern_mismatch"),
])
def test_field_record_calls_explain_the_rule(tmp_path, product, name, arguments, field, message, kind):
    with closing(ProductStore(tmp_path, product)) as store:
        with pytest.raises(ToolCallRefused) as raised:
            authorize(tool_call(name, arguments), PRODUCT_TOOLS[product], store.load())
    error = raised.value.error()
    assert error == {"code": -32602, "message": "Invalid params", "data": {"tool": name, "errors": [
        {"field": field, "message": message, "type": kind}]}}
    assert str(raised.value) == "invalid tool arguments" and isinstance(raised.value, Denied)


def test_validate_workflow_without_nodes_names_the_missing_fields(store):
    with pytest.raises(ToolCallRefused) as raised:
        authorize(tool_call("validate_workflow", {"workflow": {"name": MARK}}), TOOLS, store.load())
    errors = raised.value.error()["data"]["errors"]
    assert {"field": "workflow.nodes", "message": "Field required", "type": "missing"} in errors
    assert MARK not in json.dumps(errors)


def test_refusal_texts_are_unchanged_for_denied_callers(store):
    state = store.load()
    for message, kind, text in ((tool_call("nope", {}), "unknown_tool", "tool not permitted"),
                                (tool_call(READ_TOOL, {"topic": 5}), "invalid_params", "invalid tool arguments"),
                                (tool_call(OPERATION_TOOL, {"action": OPERATION, "name": "x"}),
                                 "operation_not_permitted", "operation not permitted"),
                                (tool_call(BACKEND_TOOL, {}), "backend_not_configured", "configured backend required")):
        with pytest.raises(ToolCallRefused) as raised:
            authorize(message, TOOLS, state)
        assert raised.value.kind == kind and str(raised.value) == text
        assert not isinstance(raised.value, UnknownMethod)


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = 0
    words: list[str] = Field(default=[], max_length=50)
    table: dict[str, int] = {}
    plain: str = ""
    parsed: str = ""

    @field_validator("plain")
    @classmethod
    def plain_rule(cls, value):
        if value:
            raise ValueError("plain must stay empty")
        return value

    @field_validator("parsed")
    @classmethod
    def parsed_rule(cls, value):
        if value:
            int(value)  # Python's own text quotes the value: "invalid literal for int() with base 10: '...'"
        return value


def probe(arguments):
    try:
        Probe.model_validate(arguments)
    except Exception as error:
        return argument_errors(Probe, error, arguments)
    raise AssertionError("valid")


def test_argument_errors_drop_values_keys_and_parser_text():
    errors = probe({"table": {MARK + "k": "x"}, MARK + "extra": 1, "parsed": MARK, "plain": "y"})
    assert {"field": "table.*", "message": "Input should be a valid integer, unable to parse string as an integer",
            "type": "int_parsing"} in errors
    assert {"field": "*", "message": "Extra inputs are not permitted", "type": "extra_forbidden"} in errors
    assert {"field": "parsed", "message": FIXED_ARGUMENT_ERROR, "type": "value_error"} in errors
    assert {"field": "plain", "message": "Value error, plain must stay empty", "type": "value_error"} in errors
    assert MARK not in json.dumps(errors)


def test_argument_errors_drop_a_message_that_contains_the_input():
    # A plain-looking validator text that happens to contain a caller string is replaced as well.
    errors = probe({"plain": "must stay"})
    assert errors == [{"field": "plain", "message": FIXED_ARGUMENT_ERROR, "type": "value_error"}]


def test_argument_errors_are_bounded():
    errors = probe({"words": [1] * 40})
    assert len(errors) == ARGUMENT_ERROR_LIMIT
    assert all(entry["field"].startswith("words.") for entry in errors)

    class Long(BaseModel):
        value: str = Field(pattern="^" + "a" * 400 + "$")

    try:
        Long.model_validate({"value": "b"})
    except Exception as error:
        [entry] = argument_errors(Long, error, {"value": "b"})
    assert len(entry["message"]) == ARGUMENT_ERROR_TEXT
