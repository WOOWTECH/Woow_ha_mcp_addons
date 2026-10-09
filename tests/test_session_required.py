"""LOCAL/MOCK: 0.1.8 (0.1.6 RC GATEWAY-2): only initialize may come without an Mcp-Session-Id.

Every child is stateful. Forwarded without a session id, a request made the pinned Python SDK children (mcp 1.28.1,
FastMCP 3.4.5) open a new session before refusing it with 400, and they kept that session until they restarted: a
monitoring script pinging once a minute left about 1,440 sessions a day. The gateway now answers such a request itself
with a 400 shaped like a refusing child's relayed answer, carrying no session id, and the child never sees it. n8n-mcp
opened no session for these but accepted a notification without one (202); that notification now gets 400 as well.
"""
import asyncio
import json

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS

INITIALIZE = {"jsonrpc": "2.0", "id": 7, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}}}
RESULT = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock", "version": "0"}, "capabilities": {"tools": {}}}
PING = {"jsonrpc": "2.0", "id": 9, "method": "ping"}
LIST = {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
CALL = {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
        "params": {"name": "search_nodes", "arguments": {"query": "webhook"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


class Child:
    """A stateful child: counts what reaches it and, like the Python SDK, opens a session for anything without one."""
    def __init__(self):
        self.seen = []

    def __call__(self, request):
        self.seen.append((request.method, request.headers.get("mcp-session-id"),
                          json.loads(request.content) if request.content else None))
        if request.headers.get("mcp-session-id") is None:
            body = json.loads(request.content) if request.content else {}
            if body.get("method") == "initialize":
                return httpx.Response(200, headers={"mcp-session-id": "child-opened"},
                                      json={"jsonrpc": "2.0", "id": body["id"], "result": RESULT})
            return httpx.Response(400, headers={"mcp-session-id": "leaked-session"},
                                  json={"jsonrpc": "2.0", "id": "server-error",
                                        "error": {"code": -32600, "message": "Bad Request: Missing session ID"}})
        if request.method == "GET":
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b": open\n\n")
        if request.method == "DELETE" or "id" not in json.loads(request.content):
            return httpx.Response(202 if request.method == "POST" else 200)
        body = json.loads(request.content)
        result = {} if body["method"] == "ping" else (
            {"tools": []} if body["method"] == "tools/list" else {"content": [{"type": "text", "text": "ok"}]})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


async def send(store, child, verb, message=None, session=None, token=None):
    headers = {"Authorization": "Bearer " + (token or store.load().token), "Accept": "application/json, text/event-stream"}
    if session is not None:
        headers["Mcp-Session-Id"] = session
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            if message is not None:
                return await asyncio.wait_for(client.request(verb, "/mcp", headers=headers, json=message), 10)
            return await asyncio.wait_for(client.request(verb, "/mcp", headers=headers), 10)


@pytest.mark.parametrize("message", [PING, LIST, CALL], ids=["ping", "tools/list", "tools/call"])
async def test_request_without_a_session_is_400_and_never_reaches_the_child(store, message):
    child = Child()
    response = await send(store, child, "POST", message)
    assert response.status_code == 400
    assert response.json() == {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": "Bad Request"}}
    assert "mcp-session-id" not in response.headers and response.headers["cache-control"] == "no-store"
    assert child.seen == []


@pytest.mark.parametrize("verb,message", [("POST", INITIALIZED), ("DELETE", None)], ids=["notification", "DELETE"])
async def test_notification_or_delete_without_a_session_is_a_bare_400(store, verb, message):
    child = Child()
    response = await send(store, child, verb, message)
    assert response.status_code == 400 and response.content == b""
    assert "mcp-session-id" not in response.headers
    assert child.seen == []


async def test_get_without_a_session_is_400(store):
    child = Child()
    response = await send(store, child, "GET")
    assert response.status_code == 400
    assert response.json() == {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Bad Request"}}
    assert "mcp-session-id" not in response.headers and child.seen == []


async def test_many_pings_without_a_session_leave_no_child_session(store):
    child = Child()
    for _ in range(50):
        assert (await send(store, child, "POST", PING)).status_code == 400
    assert child.seen == []


async def test_initialize_without_a_session_is_still_forwarded(store):
    child = Child()
    response = await send(store, child, "POST", INITIALIZE)
    assert response.status_code == 200 and response.headers["mcp-session-id"] == "child-opened"
    assert [entry[:2] for entry in child.seen] == [("POST", None)]


@pytest.mark.parametrize("verb,message", [("POST", PING), ("POST", LIST), ("POST", CALL), ("POST", INITIALIZED),
                                          ("GET", None), ("DELETE", None)],
                         ids=["ping", "tools/list", "tools/call", "notification", "GET", "DELETE"])
async def test_with_a_session_everything_is_forwarded(store, verb, message):
    child = Child()
    response = await send(store, child, verb, message, session="client-session")
    assert response.status_code in (200, 202)
    assert [entry[:2] for entry in child.seen] == [(verb, "client-session")]


async def test_the_bearer_and_policy_checks_still_come_first(store):
    child = Child()
    assert (await send(store, child, "POST", PING, token="not-the-token")).status_code == 401
    denied = {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "n8n_delete_workflow", "arguments": {}}}
    assert (await send(store, child, "POST", denied)).status_code == 403
    assert child.seen == []
