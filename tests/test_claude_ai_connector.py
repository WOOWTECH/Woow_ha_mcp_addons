"""LOCAL/MOCK: 0.1.13 JSON-RPC shapes a real Claude.ai custom connector sends (2026-10-14 field record, key names only).

1. POST server/discover (MCP-Protocol-Version 2026-07-28) whose params hold only _meta (client capabilities, client
   info, protocol version, traceparent). The gateway answered 403; it now answers HTTP 200 with JSON-RPC -32601 itself,
   before the session check, without a slot or the child, so the client falls back to initialize.
2. initialize (2025-11-25) with params _meta (traceparent) and capabilities.extensions. _meta was refused (403); MCP
   reserves it on every request and notification, so it is now accepted (an object, at most 8 KiB) and removed before
   dispatch. Unknown notifications are 202 and never forwarded. Tool policy is unchanged.
Both connection paths (/mcp with Bearer, /private_<token>/mcp) behave the same; the token check still comes first.
"""
import asyncio
import json

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import META_LIMIT, Denied, UnknownMethod, authorize
from n8n_adapter import TOOLS

TRACE = {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"}
CLAUDE_INITIALIZE = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
    "_meta": TRACE, "protocolVersion": "2025-11-25",
    "capabilities": {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}},
    "clientInfo": {"name": "Anthropic/ClaudeAI", "version": "1.0.0"}}}
DISCOVER = {"jsonrpc": "2.0", "id": 0, "method": "server/discover", "params": {"_meta": {
    "io.modelcontextprotocol/clientCapabilities": {"extensions": {}},
    "io.modelcontextprotocol/clientInfo": {"name": "Anthropic/ClaudeAI", "version": "1.0.0"},
    "io.modelcontextprotocol/protocolVersion": "2026-07-28", **TRACE}}}
RESULT = {"protocolVersion": "2025-11-25", "serverInfo": {"name": "mock", "version": "0"}, "capabilities": {"tools": {}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}
SESSION = {"Mcp-Session-Id": "child-session"}
READ_TOOL = "tools_documentation"
assert READ_TOOL in TOOLS and not TOOLS[READ_TOOL].write


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


class Child:
    """Records the JSON bodies that reach the child; answers like a stateful MCP server (optionally initialize as SSE)."""
    def __init__(self, sse_initialize=False):
        self.seen = []
        self.sse_initialize = sse_initialize

    def __call__(self, request):
        if request.method == "DELETE":
            self.seen.append(("DELETE", None))
            return httpx.Response(200)
        body = json.loads(request.content)
        self.seen.append(("POST", body))
        if "id" not in body:
            return httpx.Response(202)
        if body["method"] == "initialize":
            reply = {"jsonrpc": "2.0", "id": body["id"], "result": RESULT}
            if self.sse_initialize:
                return httpx.Response(200, headers={"mcp-session-id": "child-session", "content-type": "text/event-stream"},
                                      content=b"event: message\ndata: " + json.dumps(reply).encode() + b"\n\n")
            return httpx.Response(200, headers={"mcp-session-id": "child-session"}, json=reply)
        if body["method"] == "tools/list":
            result = {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in TOOLS]}
        elif body["method"] == "tools/call":
            result = {"content": [{"type": "text", "text": "MOCK"}]}
        else:
            result = {}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def bodies(self):
        return [body for verb, body in self.seen if verb == "POST"]


class Forbidden:
    """A child that must never be reached."""
    def __call__(self, request):
        raise AssertionError("forwarded to the child: " + request.content.decode())


async def call(store, child, path, message, headers=None, accept=ACCEPT):
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            return await asyncio.wait_for(
                client.post(path, headers={**accept, **(headers or {})}, json=message), 10)


def bearer_path(store):
    return "/mcp", {"Authorization": "Bearer " + store.load().token}


def private_path(store):
    return "/private_" + store.load().token + "/mcp", {}


PATHS = [bearer_path, private_path]


@pytest.mark.parametrize("route", PATHS)
async def test_claude_ai_initialize_succeeds_and_meta_never_reaches_the_child(store, route):
    path, auth = route(store)
    child = Child()
    answer = await call(store, child, path, CLAUDE_INITIALIZE, auth)
    assert answer.status_code == 200, answer.content
    assert answer.headers["mcp-session-id"] == "child-session"
    result = answer.json()["result"]
    assert result["protocolVersion"] == "2025-11-25" and result["serverInfo"]["name"] == "woow-mcp"
    [forwarded] = child.bodies()
    assert forwarded["id"] == 0 and forwarded["method"] == "initialize"
    assert forwarded["params"] == {"protocolVersion": "2025-11-25", "capabilities": {},
                                   "clientInfo": {"name": "Anthropic/ClaudeAI", "version": "1.0.0"}}
    assert "_meta" not in json.dumps(forwarded)


@pytest.mark.parametrize("route", PATHS)
async def test_session_requests_with_meta_are_forwarded_without_it(store, route):
    path, auth = route(store)
    child = Child()
    headers = {**auth, **SESSION}
    meta = {**TRACE, "progressToken": "p-1"}
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"_meta": TRACE}}
    assert (await call(store, child, path, initialized, headers)).status_code == 202
    listed = await call(store, child, path, {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                                             "params": {"_meta": meta, "cursor": "c1"}}, headers)
    assert listed.status_code == 200 and listed.json()["result"]["tools"]
    bare_list = await call(store, child, path, {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                                "params": {"_meta": TRACE}}, headers)
    assert bare_list.status_code == 200
    called = await call(store, child, path, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "_meta": meta, "name": READ_TOOL, "arguments": {}}}, headers)
    assert called.status_code == 200 and called.json()["result"]["content"][0]["text"] == "MOCK"
    pinged = await call(store, child, path, {"jsonrpc": "2.0", "id": "p", "method": "ping",
                                             "params": {"_meta": TRACE}}, headers)
    assert pinged.status_code == 200 and pinged.json() == {"jsonrpc": "2.0", "id": "p", "result": {}}
    bodies = child.bodies()
    assert "_meta" not in json.dumps(bodies) and "progressToken" not in json.dumps(bodies)
    # A params object that held only _meta is dropped altogether (as a client that sends no params).
    assert bodies[0] == {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert bodies[1]["params"] == {"cursor": "c1"}
    assert bodies[2] == {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    assert bodies[3]["params"]["name"] == READ_TOOL and set(bodies[3]["params"]) == {"name", "arguments"}
    assert bodies[3]["params"]["arguments"] == TOOLS[READ_TOOL].arguments.model_validate({}).model_dump(mode="json")
    assert bodies[4] == {"jsonrpc": "2.0", "id": "p", "method": "ping"}


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("meta", [[], "x", 1, None, True, [TRACE], {"blob": "x" * META_LIMIT}])
async def test_invalid_or_oversized_meta_is_refused(store, route, meta):
    path, auth = route(store)
    for message in ({**CLAUDE_INITIALIZE, "params": {**CLAUDE_INITIALIZE["params"], "_meta": meta}},
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}},
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"_meta": meta, "name": READ_TOOL, "arguments": {}}},
                    {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": meta}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"_meta": meta}}):
        response = await call(store, Forbidden(), path, message, {**auth, **SESSION})
        assert response.status_code == 403, (message["method"], response.content)


@pytest.mark.parametrize("route", PATHS)
async def test_tool_policy_is_unchanged_with_meta(store, route):
    path, auth = route(store)
    headers = {**auth, **SESSION}
    writer = next(name for name, tool in TOOLS.items() if tool.write)
    for params in ({"name": "no_such_tool", "arguments": {}}, {"name": writer, "arguments": {"id": "x"}},
                   {"name": READ_TOOL, "arguments": {"unreviewed": True}}, {"name": READ_TOOL, "arguments": []},
                   {"name": READ_TOOL, "arguments": {}, "extra": 1}, {}):
        message = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"_meta": TRACE, **params}}
        assert (await call(store, Forbidden(), path, message, headers)).status_code == 403, params
    for message in ({"jsonrpc": "2.0", "id": 5, "method": "ping", "params": {"_meta": TRACE, "x": 1}},
                    {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {"_meta": TRACE, "cursor": 1}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"_meta": TRACE, "x": 1}},
                    {"jsonrpc": "2.0", "id": 5, "method": "notifications/initialized", "params": {"_meta": TRACE}},
                    {"jsonrpc": "2.0", "method": "tools/call", "params": {"_meta": TRACE, "name": READ_TOOL}},
                    {**CLAUDE_INITIALIZE, "params": {"_meta": TRACE, "protocolVersion": "2025-11-25"}}):
        assert (await call(store, Forbidden(), path, message, headers)).status_code == 403, message


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("message", [
    DISCOVER, {**DISCOVER, "id": "discover-1"}, {"jsonrpc": "2.0", "id": 7, "method": "resources/list"},
    {"jsonrpc": "2.0", "id": 8, "method": "prompts/list", "params": {}},
    {"jsonrpc": "2.0", "id": 9, "method": "resources/read", "params": {"uri": "file:///etc/passwd"}},
    {"jsonrpc": "2.0", "id": 10, "method": "server/discover", "params": {"_meta": "not checked: never dispatched"}},
])
@pytest.mark.parametrize("session", [{}, SESSION])
async def test_unknown_request_is_method_not_found_without_the_child(store, route, message, session):
    path, auth = route(store)
    response = await call(store, Forbidden(), path, message, {**auth, **session,
                                                               "MCP-Protocol-Version": "2026-07-28"})
    assert response.status_code == 200, response.content
    assert response.headers["content-type"] == "application/json"
    assert "mcp-session-id" not in response.headers
    assert response.json() == {"jsonrpc": "2.0", "id": message["id"],
                               "error": {"code": -32601, "message": "Method not found"}}


@pytest.mark.parametrize("route", PATHS)
@pytest.mark.parametrize("method", ["notifications/cancelled", "notifications/roots/list_changed",
                                    "notifications/progress"])
async def test_unknown_notification_is_202_without_the_child(store, route, method):
    path, auth = route(store)
    for session in ({}, SESSION):
        message = {"jsonrpc": "2.0", "method": method, "params": {"requestId": 1, "_meta": TRACE}}
        response = await call(store, Forbidden(), path, message, {**auth, **session})
        assert response.status_code == 202 and response.content == b""


async def test_unknown_method_needs_the_token_first(store):
    """server/discover is no way around the token: 401 on /mcp, the unknown-path 404 on /private_<wrong>/mcp."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(Forbidden())) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            reference = await client.post("/no-such-path/mcp", headers=ACCEPT, json=DISCOVER)
            assert reference.status_code == 404
            note = {"jsonrpc": "2.0", "method": "notifications/cancelled"}
            for message in (DISCOVER, note):
                for headers in ({}, {"Authorization": "Bearer wrong"}):
                    response = await client.post("/mcp", headers={**ACCEPT, **headers}, json=message)
                    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
                token = store.load().token
                for secret in ("wrong", token[:-1], token + "x"):
                    response = await client.post(f"/private_{secret}/mcp", headers=ACCEPT, json=message)
                    assert response.status_code == 404
                    assert response.content == reference.content
                    assert dict(response.headers) == dict(reference.headers)
            store.update(token=None)
            response = await client.post(f"/private_{token}/mcp", headers=ACCEPT, json=DISCOVER)
            assert response.status_code == 404


async def test_unknown_method_takes_no_slot(store):
    """Answered before the 32 request slots: it still answers while every slot is held by a stuck child request."""
    gate = asyncio.Event()

    async def stuck(request):
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
                response = await asyncio.wait_for(client.post("/mcp", headers=headers, json=DISCOVER), 5)
                assert response.status_code == 200 and response.json()["error"]["code"] == -32601
            finally:
                gate.set()
                await asyncio.gather(*held)


@pytest.mark.parametrize("route", PATHS)
async def test_json_only_client_gets_initialize_as_json(store, route):
    path, auth = route(store)
    child = Child(sse_initialize=True)
    answer = await call(store, child, path, CLAUDE_INITIALIZE, auth, accept={"Accept": "application/json"})
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/json"
    assert answer.headers["mcp-session-id"] == "child-session"
    assert answer.json()["result"]["serverInfo"]["name"] == "woow-mcp"
    # A client that accepts SSE still gets the child's framing (unchanged).
    framed = await call(store, Child(sse_initialize=True), path, CLAUDE_INITIALIZE, auth)
    assert framed.headers["content-type"].startswith("text/event-stream")
    assert framed.text.startswith("event: message\ndata: ")


# ---- authorize() itself ----

def test_authorize_strips_meta_idempotently(store):
    state = store.load()
    message = json.loads(json.dumps(CLAUDE_INITIALIZE))
    assert authorize(message, TOOLS, state) == "initialize"
    assert "_meta" not in message["params"]
    once = json.dumps(message)
    assert authorize(message, TOOLS, state) == "initialize" and json.dumps(message) == once
    exact = {"k": "x" * (META_LIMIT - len('{"k":""}'))}
    assert len(json.dumps(exact, separators=(",", ":"))) == META_LIMIT
    assert authorize({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": exact}}, TOOLS, state) == "ping"
    with pytest.raises(Denied):
        authorize({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": {"k": exact["k"] + "x"}}}, TOOLS,
                  state)
    # Multi-byte text counts in UTF-8 bytes.
    with pytest.raises(Denied):
        authorize({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": {"k": "é" * (META_LIMIT // 2)}}},
                  TOOLS, state)


@pytest.mark.parametrize("message, request_like", [
    ({"jsonrpc": "2.0", "id": 1, "method": "server/discover"}, True),
    ({"jsonrpc": "2.0", "id": "x", "method": "completion/complete", "params": {}}, True),
    ({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}, False),
    ({"jsonrpc": "2.0", "method": "resources/list"}, False),
])
def test_unknown_methods_are_classified(store, message, request_like):
    with pytest.raises(UnknownMethod) as raised:
        authorize(message, TOOLS, store.load())
    assert raised.value.request is request_like


@pytest.mark.parametrize("message", [
    {"jsonrpc": "2.0", "id": None, "method": "server/discover"},
    {"jsonrpc": "2.0", "id": True, "method": "server/discover"},
    {"jsonrpc": "2.0", "id": 1.5, "method": "server/discover"},
    {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": []},
    {"jsonrpc": "1.0", "id": 1, "method": "server/discover"},
    {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "extra": 1},
    {"jsonrpc": "2.0", "id": 1, "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": READ_TOOL}},
    {"jsonrpc": "2.0", "method": "initialize", "params": {}},
])
def test_malformed_messages_stay_denied_not_unknown(store, message):
    with pytest.raises(Denied) as raised:
        authorize(message, TOOLS, store.load())
    assert not isinstance(raised.value, UnknownMethod)
