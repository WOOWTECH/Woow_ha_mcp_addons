"""LOCAL/MOCK health evidence is not backend E2E."""
import json

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.health import HealthMonitor


class Process:
    ready = False
    status = "running"
    starts = 1
    def health(self):
        return {"state": self.status, "transport_ready": self.ready, "starts": self.starts}


async def test_health_is_three_distinct_states_and_outage_never_restarts(tmp_path):
    store = Store(tmp_path / "state")
    process = Process()
    calls = []
    async def handler(request):
        calls.append(request)
        if request.url.host == "backend.test":
            return httpx.Response(503)
        if request.method == "DELETE":
            return httpx.Response(204)
        message = json.loads(request.content)
        if message["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "mock-session", "content-type": "text/event-stream"}, content='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{},"serverInfo":{"name":"MOCK","version":"0"}}}\n\n')
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": {}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monitor = HealthMonitor(store, process, client)
        await monitor.check()
        assert monitor.snapshot()["management"] == "alive"
        assert monitor.snapshot()["backend"] == "unconfigured"
        assert process.ready
        store.update(backend_url="http://backend.test", backend_key="MOCK")
        await monitor.check()
        assert monitor.snapshot()["backend"] == "unreachable"
        assert process.ready and process.starts == 1
        assert any(r.method == "DELETE" for r in calls)
    store.close()


@pytest.mark.parametrize("success", [True, False])
async def test_backend_health_uses_child_network_policy_not_direct_http(tmp_path, success):
    store = Store(tmp_path / "state")
    store.update(backend_url="http://backend.test", backend_key="DUMMY")
    calls = []
    async def handler(request):
        calls.append(request)  # checked after check(): the monitor contains exceptions raised here (0.1.2)
        if request.method == "DELETE":
            return httpx.Response(204)
        message = json.loads(request.content)
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = {}
        if message["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock"}}
        elif message["method"] == "tools/call":
            result = {"content": [{"type": "text", "text": json.dumps({"success": success})}]}
        return httpx.Response(200, headers={"mcp-session-id": "health"},
                              json={"jsonrpc": "2.0", "id": message["id"], "result": result})
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monitor = HealthMonitor(store, Process(), client)
            await monitor.check()
            assert monitor.backend == ("reachable" if success else "unreachable")
            assert any(r.method == "POST" and json.loads(r.content)["method"] == "tools/call" for r in calls)
            assert all(r.url.host == "127.0.0.1" for r in calls), "health bypassed child backend policy"
            assert all("x-n8n-api-key" not in r.headers for r in calls)
            assert [json.loads(r.content)["params"] for r in calls if r.method == "POST"
                    and json.loads(r.content)["method"] == "tools/call"] == [{"name": "n8n_list_workflows", "arguments": {"limit": 1}}]
    finally:
        store.close()


async def test_tcp_or_unconditional_health_is_not_protocol_readiness(tmp_path):
    store = Store(tmp_path / "state")
    process = Process()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True}))) as client:
        monitor = HealthMonitor(store, process, client)
        await monitor.check()
        assert not process.ready
    store.close()


@pytest.mark.parametrize("variant", ["session", "session-space", "session-long", "session-empty", "text-type", "no-text", "delete-raises"])
async def test_a_misbehaving_child_never_stops_the_monitor(tmp_path, variant):
    # Round 5: a non-ASCII session id made the cleanup DELETE raise outside the handled errors, and odd probe
    # payloads raised TypeError/KeyError; any of them ended HealthMonitor.run() and with it the add-on.
    store = Store(tmp_path / "state")
    store.update(backend_url="http://backend.test", backend_key="DUMMY")
    process = Process()
    deletes, requests = [], []

    async def handler(request):
        requests.append(request)
        if request.method == "DELETE":
            deletes.append(request)
            if variant == "delete-raises":
                raise RuntimeError("cleanup failed in an unexpected way")
            return httpx.Response(204)
        message = json.loads(request.content)
        session = {"session": "中".encode(), "session-space": b"a b", "session-long": b"x" * 300,
                   "session-empty": b""}.get(variant, b"ok-session")
        if message["method"] == "initialize":
            return httpx.Response(200, headers=[(b"mcp-session-id", session), (b"content-type", b"application/json")],
                                  content=json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
                                      "protocolVersion": "2025-03-26", "serverInfo": {"name": "x", "version": "0"}}}).encode())
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        if message["method"] == "ping":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": {}})
        item = {"type": "text", "text": 42} if variant == "text-type" else {"type": "text"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"content": [item]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monitor = HealthMonitor(store, process, client)
        await monitor.check()  # must not raise
    assert monitor.snapshot()["backend"] == "unreachable"
    if variant.startswith("session"):
        assert process.ready is False and deletes == []  # the bad session id is never reused
        assert all("mcp-session-id" not in r.headers for r in requests[1:])
    else:
        assert process.ready is True and len(deletes) == 1
    store.close()


async def test_an_unusable_protocol_version_closes_the_session(tmp_path):
    # 0.1.3: the child's protocolVersion is reused as a header only when it is a valid header value.
    store = Store(tmp_path / "state")
    process = Process()
    seen = []

    async def handler(request):
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, headers={"mcp-session-id": "ok-session", "content-type": "application/json"},
                              json={"jsonrpc": "2.0", "id": 1, "result": {
                                  "protocolVersion": "2025 03 26", "serverInfo": {"name": "x", "version": "0"}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await HealthMonitor(store, process, client).check()
    assert process.ready is False
    assert [r.method for r in seen] == ["POST", "DELETE"]  # no further request; the session is closed
    assert seen[1].headers["mcp-session-id"] == "ok-session"  # closes THAT session (RC review #3)
    assert "mcp-protocol-version" not in seen[1].headers
    store.close()
