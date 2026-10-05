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
        calls.append(request)
        assert request.url.host == "127.0.0.1", "health bypassed child backend policy"
        assert "x-n8n-api-key" not in request.headers
        if request.method == "DELETE":
            return httpx.Response(204)
        message = json.loads(request.content)
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = {}
        if message["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock"}}
        elif message["method"] == "tools/call":
            assert message["params"] == {"name": "n8n_list_workflows", "arguments": {"limit": 1}}
            result = {"content": [{"type": "text", "text": json.dumps({"success": success})}]}
        return httpx.Response(200, headers={"mcp-session-id": "health"},
                              json={"jsonrpc": "2.0", "id": message["id"], "result": result})
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monitor = HealthMonitor(store, Process(), client)
            await monitor.check()
            assert monitor.backend == ("reachable" if success else "unreachable")
            assert any(r.method == "POST" and json.loads(r.content)["method"] == "tools/call" for r in calls)
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


@pytest.mark.parametrize("variant", ["session", "text-type", "no-text", "delete-raises"])
async def test_a_misbehaving_child_never_stops_the_monitor(tmp_path, variant):
    # Round 5: a non-ASCII session id made the cleanup DELETE raise outside the handled errors, and odd probe
    # payloads raised TypeError/KeyError; any of them ended HealthMonitor.run() and with it the add-on.
    store = Store(tmp_path / "state")
    store.update(backend_url="http://backend.test", backend_key="DUMMY")
    process = Process()
    deletes = []

    async def handler(request):
        if request.method == "DELETE":
            deletes.append(request)
            if variant == "delete-raises":
                raise RuntimeError("cleanup failed in an unexpected way")
            return httpx.Response(204)
        message = json.loads(request.content)
        session = "中".encode() if variant == "session" else b"ok-session"
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
    if variant == "session":
        assert process.ready is False and deletes == []  # the bad session id is never reused
    else:
        assert process.ready is True and len(deletes) == 1
    store.close()
