"""LOCAL/MOCK: initialize must yield the child's JSON-RPC reply or a clear BACKEND_UNAVAILABLE (0.1.1 HA test:
Odoo Manage answered 200 without a reply when its per-session lifespan could not reach the backend, then 404)."""
import asyncio
import json

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS

INITIALIZE = {"jsonrpc": "2.0", "id": 7, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}}}
RESULT = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock", "version": "0"},
          "capabilities": {"tools": {"listChanged": True}, "resources": {}, "logging": {}}}


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


class Chunks(httpx.AsyncByteStream):
    """Upstream body in pieces; optionally stays open afterwards like an idle SSE stream."""
    def __init__(self, parts, hold_open=False):
        self.parts, self.hold_open, self.closed = parts, hold_open, False

    async def __aiter__(self):
        for part in self.parts:
            yield part
        if self.hold_open:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


async def initialize(store, upstream, message=INITIALIZE):
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            return await asyncio.wait_for(client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                                      json=message), 10)


def sse(parts, hold_open=False):
    stream = Chunks(parts, hold_open)
    return stream, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "dead"},
                                            stream=stream)


@pytest.mark.parametrize("parts", [[], [b": heartbeat\n\n"], [b'data: {"jsonrpc":"2.0","method":"notifications/message"}\n\n'],
                                   [b'data: {"jsonrpc":"2.0","id":8,"result":{}}\n\n'], [b'data: {"jsonrpc":"2.0","id":7,"res']])
async def test_sse_without_the_reply_is_backend_unavailable_without_a_session(store, parts):
    stream, upstream = sse(parts)
    response = await initialize(store, upstream)
    assert response.status_code == 503
    assert response.json() == {"jsonrpc": "2.0", "id": 7, "error": {"code": -32000, "message": "BACKEND_UNAVAILABLE"}}
    assert response.headers["retry-after"] == "5" and "mcp-session-id" not in response.headers
    assert stream.closed


async def test_empty_json_reply_is_backend_unavailable(store):
    response = await initialize(store, lambda _: httpx.Response(200, headers={"mcp-session-id": "dead"}, content=b""))
    assert response.status_code == 503 and "mcp-session-id" not in response.headers


@pytest.mark.parametrize("upstream", [
    lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"data: {not json}\n\n"),
    lambda _: httpx.Response(200, content=b"{not json"),
    lambda _: httpx.Response(200, json=["not", "a", "message"])])
async def test_malformed_reply_stays_bad_gateway(store, upstream):
    assert (await initialize(store, upstream)).status_code == 502


async def test_sse_reply_is_returned_promptly_with_its_framing_and_filtered(store):
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": RESULT}).encode()
    parts = [b": heartbeat\r\n\r\n", b'data: {"jsonrpc":"2.0","method":"notifications/message","params":{}}\n\n',
             b"id: event-7\r\nevent: message\r\ndata: " + reply[:20], reply[20:] + b"\r\n\r\n"]
    stream, upstream = sse(parts, hold_open=True)  # the child keeps the stream open after replying
    response = await initialize(store, upstream)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["mcp-session-id"] == "dead"
    lines = response.text.splitlines()
    assert lines[:2] == ["id: event-7", "event: message"] and response.text.endswith("\n\n")
    value = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
    assert value["id"] == 7 and value["result"]["capabilities"] == {"tools": {}}
    assert value["result"]["serverInfo"] == {"name": "mock", "version": "0"}
    assert "notifications/message" not in response.text and stream.closed


async def test_json_reply_and_rpc_errors_pass_through(store):
    response = await initialize(store, lambda _: httpx.Response(200, headers={"mcp-session-id": "s"},
                                                               json={"jsonrpc": "2.0", "id": 7, "result": RESULT}))
    assert response.status_code == 200 and response.headers["mcp-session-id"] == "s"
    assert response.json()["result"]["capabilities"] == {"tools": {}}
    error = {"jsonrpc": "2.0", "id": 7, "error": {"code": -32602, "message": "Unsupported protocol version"}}
    _, upstream = sse([b"data: " + json.dumps(error).encode() + b"\n\n"])
    response = await initialize(store, upstream)
    assert response.status_code == 200
    assert json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))) == error


async def test_non_200_initialize_is_forwarded_unchanged(store):
    response = await initialize(store, lambda _: httpx.Response(429, json={"error": "Session limit reached"}))
    assert response.status_code == 429


async def test_revocation_while_waiting_for_the_reply_is_401(store):
    opened = asyncio.Event()

    class Waiting(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": opened\n\n"
            opened.set()
            await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Waiting()))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            pending = asyncio.create_task(client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                                      json=INITIALIZE))
            await asyncio.wait_for(opened.wait(), 5)
            store.update(token=None)
            response = await asyncio.wait_for(pending, 5)
    assert response.status_code == 401
