"""LOCAL/MOCK only: no Home Assistant identity or real n8n backend."""
import json
import os
import stat

import httpx
import pytest

from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS, child_spec


def rpc(method="tools/call", **params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


def test_bootstrap_persistence_and_secret_permissions(tmp_path):
    path = tmp_path / "state"
    store = Store(path)
    initial = store.load()
    assert len(initial.token) >= 43
    assert initial.token != initial.child_token
    assert not initial.writes_enabled
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    store.update(backend_url="http://127.0.0.1:4567", backend_key="test-only")
    store.close()
    reopened = Store(path)
    assert reopened.load().token == initial.token
    assert reopened.load().backend_key == "test-only"
    reopened.close()


@pytest.mark.parametrize("content", ['{', '{"schema_version":99}', '{}', '[]'])
def test_corrupt_future_config_is_never_replaced(tmp_path, content):
    path = tmp_path / "state"
    store = Store(path)
    file = store.path
    store.close()
    file.write_text(content)
    with pytest.raises(ConfigError):
        Store(path)
    assert file.read_text() == content


def test_symlink_and_second_writer_denied(tmp_path, store):
    with pytest.raises(ConfigError):
        Store(store.path.parent)
    target = tmp_path / "linked"
    target.symlink_to(store.path.parent, target_is_directory=True)
    with pytest.raises(ConfigError):
        Store(target)


@pytest.fixture
async def harness(store):
    calls = []

    async def upstream(request):
        calls.append(request)
        if request.method != "POST":
            return httpx.Response(204)
        message = json.loads(request.content)
        if message["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {
                "tools": [{"name": name} for name in [*TOOLS, "unknown_tool"]]}})
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, headers={"mcp-session-id": "test-session"}, json={
            "jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "MOCK"}]}})

    async def role(user):
        return user == "admin-test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        admin, mcp = make_apps(store, TOOLS, child, verify_admin=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=("172.30.32.2", 123)), base_url="http://admin") as a, httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp), base_url="http://mcp") as m:
            yield a, m, calls


def bearer(store):
    return {"Authorization": "Bearer " + store.load().token}


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic test"])
async def test_all_session_requests_authenticate(harness, method, authorization):
    _, m, calls = harness
    headers = {"mcp-session-id": "cached", "X-Remote-User-Id": "admin-test"}
    if authorization:
        headers["Authorization"] = authorization
    r = await m.request(method, "/mcp", headers=headers, json=rpc(name="tools_documentation"))
    assert r.status_code == 401
    assert calls == []


@pytest.mark.parametrize("message", [
    rpc(name="unknown"), rpc(name="n8n_delete_workflow", arguments={"id": "test"}),
    rpc(name="n8n_executions", arguments={"action": "delete"}),
    rpc(name="search_nodes", arguments=[]), rpc(name="search_nodes", arguments={}),
    rpc(name="search_nodes", arguments={"query": "x", "unreviewed": True}),
    {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "tools_documentation"}},
    [rpc(name="tools_documentation")], rpc("arbitrary/execute"),
    rpc("resources/list"), rpc("resources/read", uri="file:///not-accessed"),
    rpc("resources/templates/list"), rpc("prompts/list"), rpc("prompts/get", name="unknown"),
    rpc("logging/setLevel", level="debug"),
    {"jsonrpc": "2.0", "id": True, "method": "tools/call", "params": {"name": "tools_documentation"}},
])
async def test_denied_calls_never_forward(harness, store, message):
    _, m, calls = harness
    r = await m.post("/mcp", headers=bearer(store), json=message)
    assert r.status_code in (400, 403)
    assert calls == []


async def test_duplicate_keys_and_body_limit(harness, store):
    _, m, calls = harness
    auth = bearer(store)["Authorization"]
    assert (await m.get("/mcp", headers=[("Authorization", auth), ("Authorization", auth)])).status_code == 401
    for body in [b'{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/call"}', b" " * (262144 + 1)]:
        r = await m.post("/mcp", headers={**bearer(store), "Content-Type": "application/json"}, content=body)
        assert r.status_code in (400, 413)
    assert not calls


async def test_read_call_filter_policy_rotation_and_separate_child_secret(harness, store):
    a, m, calls = harness
    headers = bearer(store)
    r = await m.post("/mcp", headers={**headers, "x-n8n-url": "http://invalid", "x-n8n-key": "override"}, json=rpc(name="tools_documentation", arguments={}))
    assert r.status_code == 200
    assert r.headers["mcp-session-id"] == "test-session"
    assert calls[-1].headers["authorization"] == "Bearer " + store.load().child_token
    assert "x-n8n-url" not in calls[-1].headers
    listed = (await m.post("/mcp", headers=headers, json=rpc("tools/list"))).json()["result"]["tools"]
    assert {t["name"] for t in listed} == {k for k, v in TOOLS.items() if not v.write}
    store.update(disabled=["tools_documentation"])
    headers["Mcp-Session-Id"] = "test-session"
    count = len(calls)
    assert (await m.post("/mcp", headers=headers, json=rpc(name="tools_documentation"))).status_code == 403
    assert len(calls) == count
    # Rotation/revoke are privileged CSRF-protected routes, never ordinary GET settings.
    identity = {"X-Remote-User-Id": "admin-test", "X-Ingress-Path": "/api/hassio_ingress/opaque"}
    bootstrap = (await a.get("/api/bootstrap", headers=identity)).json()
    assert bootstrap["base_path"] == identity["X-Ingress-Path"]
    assert bootstrap["endpoint"] is None
    text = json.dumps(bootstrap)
    assert store.load().token not in text and store.load().child_token not in text
    assert (await a.post("/api/token/rotate", headers=identity)).status_code == 403
    identity["X-CSRF-Token"] = bootstrap["csrf"]
    rotated = await a.post("/api/token/rotate", headers=identity)
    assert rotated.status_code == 200
    assert rotated.json()["token"] != headers["Authorization"][7:]
    for method in ("GET", "POST", "DELETE"):
        assert (await m.request(method, "/mcp", headers=headers, json=rpc("ping"))).status_code == 401
    assert (await a.post("/api/token/revoke", headers=identity)).status_code == 204
    assert (await m.get("/mcp", headers={"Authorization": "Bearer " + rotated.json()["token"]})).status_code == 401


async def test_admin_write_enable_disable_and_no_generic_secrets(harness, store):
    a, m, calls = harness
    headers = {"X-Remote-User-Id": "admin-test"}
    headers["X-CSRF-Token"] = (await a.get("/api/bootstrap", headers=headers)).json()["csrf"]
    assert (await a.put("/api/policy", headers=headers, json={"writes_enabled": True, "disabled": []})).status_code == 200
    assert (await m.post("/mcp", headers=bearer(store), json=rpc(name="n8n_delete_workflow", arguments={"id": "MOCK"}))).status_code == 200
    assert (await a.put("/api/backend", headers=headers, json={"url": "http://127.0.0.1:4567", "key": "MOCK-secret"})).status_code == 200
    text = (await a.get("/api/bootstrap", headers=headers)).text
    assert "MOCK-secret" not in text
    assert (await a.get("/api/config", headers=headers)).status_code == 404
    assert (await a.put("/api/backend", headers=headers, json={"command": "anything"})).status_code == 400
    assert (await a.put("/api/endpoint", headers=headers, json={"endpoint": "http://mcp.example.test:8081/mcp"})).status_code == 200
    assert (await a.get("/api/bootstrap", headers=headers)).json()["endpoint"] == "http://mcp.example.test:8081/mcp"
    assert (await a.put("/api/backend", headers=headers, json={"url": None, "key": None})).status_code == 200
    assert store.load().backend_key is None
    assert (await a.post("/api/token/reveal", headers=headers)).json()["token"] == store.load().token
    assert (await a.post("/api/token/reveal", headers={**headers, "X-Ingress-Path": "/other"})).status_code == 403


async def test_admin_fails_closed_and_socket_peer_not_forwarded_header(store):
    async with httpx.AsyncClient() as child:
        async def yes(_): return True
        for peer, verifier, user in [("127.0.0.1", yes, "admin"), ("172.30.32.2", None, "admin"), ("172.30.32.2", yes, "")]:
            admin, mcp = make_apps(store, TOOLS, child, verify_admin=verifier)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=(peer, 1)), base_url="http://admin") as client:
                r = await client.get("/api/bootstrap", headers={"X-Remote-User-Id": user, "X-Forwarded-For": "172.30.32.2"})
                assert r.status_code == 403
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp), base_url="http://mcp") as client:
                assert (await client.get("/api/bootstrap", headers=bearer(store))).status_code == 404


@pytest.mark.parametrize("prefix", ["//evil", "/../evil", "/x%2fy", "/x?y", "https://evil", "/x\\y"])
async def test_bad_prefix_denied(harness, prefix):
    a, _, _ = harness
    assert (await a.get("/api/bootstrap", headers={"X-Remote-User-Id": "admin-test", "X-Ingress-Path": prefix})).status_code == 400


async def test_origin_query_and_nonadmin_denied(harness, store):
    a, m, calls = harness
    assert (await a.get("/api/bootstrap", headers={"X-Remote-User-Id": "not-admin"})).status_code == 403
    assert (await m.post("/mcp", headers={**bearer(store), "Origin": "http://evil"}, json=rpc("ping"))).status_code == 403
    assert (await m.post("/mcp?token=anything", headers=bearer(store), json=rpc("ping"))).status_code == 400
    assert not calls


def test_fixed_adapter_environment(store, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "must-not-inherit")
    monkeypatch.setenv("NODE_OPTIONS", "must-not-inherit")
    spec = child_spec(store.load(), store.path.parent)
    assert spec.argv[-1].endswith("n8n-mcp/dist/mcp/index.js")
    assert spec.env["HOST"] == "127.0.0.1"
    assert spec.env["AUTH_TOKEN"] == store.load().child_token
    assert spec.env["N8N_MCP_TELEMETRY_DISABLED"] == "true"
    assert "SUPERVISOR_TOKEN" not in spec.env and "NODE_OPTIONS" not in spec.env
    assert "N8N_API_KEY" not in spec.env
