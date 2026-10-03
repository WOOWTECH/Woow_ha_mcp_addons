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
