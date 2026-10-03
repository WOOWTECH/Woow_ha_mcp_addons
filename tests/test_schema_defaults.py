"""Local schema/default contract; fake forwarding only, never backend writes."""
import json
import subprocess
import sys

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


@pytest.mark.parametrize("name,arguments,expected", [
    ("tools_documentation", {}, {"topic": "overview", "depth": "essentials"}),
    ("tools_documentation", {"topic": "search_nodes", "depth": "full"},
     {"topic": "search_nodes", "depth": "full"}),
    ("search_nodes", {"query": "webhook"}, {"query": "webhook", "limit": 20}),
    ("search_nodes", {"query": "webhook", "limit": 1}, {"query": "webhook", "limit": 1}),
    ("n8n_list_workflows", {}, {"limit": 20}),
    ("n8n_list_workflows", {"active": False}, {"limit": 20, "active": False}),
    ("n8n_list_workflows", {"active": True, "limit": 100}, {"limit": 100, "active": True}),
    ("n8n_delete_workflow", {"id": "MOCK-only"}, {"id": "MOCK-only"}),
])
async def test_forwarded_arguments_are_the_reviewed_defaults(store, name, arguments, expected):
    calls = []
    def upstream(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
    store.update(writes_enabled=True)  # MOCK transport only, no real writer.
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://local") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": name, "arguments": arguments}})
    assert response.status_code == 200
    assert calls[0]["params"]["arguments"] == expected


@pytest.mark.parametrize("name,arguments", [
    ("tools_documentation", {"topic": None}),
    ("tools_documentation", {"depth": None}),
    ("search_nodes", {"query": None}),
    ("search_nodes", {"query": "webhook", "limit": None}),
    ("n8n_list_workflows", {"active": None}),
    ("n8n_list_workflows", {"limit": None}),
    ("n8n_delete_workflow", {"id": None}),
])
async def test_explicit_null_never_reaches_child(store, name, arguments):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={})
    store.update(writes_enabled=True)  # Only to validate the writer's arguments.
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://local") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": name, "arguments": arguments}})
    assert response.status_code == 403
    assert not calls


def test_local_test_lock_excludes_other_processes(local_test_lock):
    result = subprocess.run([sys.executable, "-c", """
import fcntl, sys
with open(sys.argv[1], 'r') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    sys.exit(1)
""", str(local_test_lock)], timeout=5, check=False)
    assert result.returncode == 0, "another test process could enter the fixed-port suite"
