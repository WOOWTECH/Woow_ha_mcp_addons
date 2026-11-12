"""Independent Headscale v0.29.4 wire fixtures and HA child authorization tests."""
import hashlib
import json
import logging
from pathlib import Path
import socket
import sys

import httpcore
import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/headscale"), str(ROOT / "apps/headscale/vendor"),
                str(ROOT / "apps/runtime"), str(ROOT / "packages/mcp-admin-core")]

from headscale_mcp_server.client import HeadscaleClient
from headscale_mcp_server.errors import HeadscaleError
from headscale_mcp_server.http_policy import Destination, HeadscaleTransport, PinnedNetwork
from headscale_mcp_server.native import NATIVE_OPERATIONS
from headscale_mcp_server.policy import SavedPolicy, WRITE_GRANTS
from headscale_mcp_server.registry import COVERAGE_MATRIX, TOOL_REGISTRY
from headscale_mcp_server.server import build_server, execute_tool

AUTH = "hskey-authreq-" + "a" * 24
EXPIRY = "2035-01-01T00:00:00Z"
API_SECRET = "fixture-upstream-credential"
LEGACY = "fixture-legacy-secret"
CREATED = "fixture-created-secret"
P0 = '{"acls":[]}'
P1 = '{"acls":[{"action":"accept","src":["*"],"dst":["*:*"]}]}'
DIGEST = hashlib.sha256(P0.encode()).hexdigest()
PREFIX = "AbCdEf012345"


# native, native arguments, task, task arguments, HTTP verb, path, query, JSON
CASES = [
 ("CreateUser", {"name":"mcp-test","displayName":"Test","email":"test@example.invalid","pictureUrl":""}, "users", {"operation":"create","name":"mcp-test","display_name":"Test","email":"test@example.invalid","picture_url":""}, "POST", "/user", {}, {"name":"mcp-test","displayName":"Test","email":"test@example.invalid","pictureUrl":""}),
 ("RenameUser", {"oldId":"101","newName":"mcp-new"}, "users", {"operation":"rename","user_id":"101","new_name":"mcp-new"}, "POST", "/user/101/rename/mcp-new", {}, None),
 ("DeleteUser", {"id":"101"}, "users", {"operation":"delete","user_id":"101"}, "DELETE", "/user/101", {}, None),
 ("ListUsers", {"id":"101"}, "users", {"operation":"list","user_id":"101"}, "GET", "/user", {"id":"101"}, None),
 ("CreatePreAuthKey", {"user":"101","reusable":False,"ephemeral":False,"expiration":EXPIRY,"aclTags":[]}, "preauth_keys", {"operation":"create","user_id":"101","expiration":EXPIRY,"reveal_once":True}, "POST", "/preauthkey", {}, {"user":"101","reusable":False,"ephemeral":False,"expiration":EXPIRY,"aclTags":[]}),
 ("ExpirePreAuthKey", {"id":"301"}, "preauth_keys", {"operation":"expire","key_id":"301"}, "POST", "/preauthkey/expire", {}, {"id":"301"}),
 ("DeletePreAuthKey", {"id":"301"}, "preauth_keys", {"operation":"delete","key_id":"301"}, "DELETE", "/preauthkey", {"id":"301"}, None),
 ("ListPreAuthKeys", {}, "preauth_keys", {"operation":"list"}, "GET", "/preauthkey", {}, None),
 ("DebugCreateNode", {"user":"mcp-test","key":AUTH,"name":"test-device","routes":[]}, "debug_node", {"user":"mcp-test","auth_id":AUTH,"name":"test-device","confirm":True}, "POST", "/debug/node", {}, {"user":"mcp-test","key":AUTH,"name":"test-device","routes":[]}),
 ("GetNode", {"nodeId":"201"}, "nodes", {"operation":"get","node_id":"201"}, "GET", "/node/201", {}, None),
 ("SetTags", {"nodeId":"201","tags":["tag:test"]}, "nodes", {"operation":"set_tags","node_id":"201","tags":["tag:test"]}, "POST", "/node/201/tags", {}, {"tags":["tag:test"]}),
 ("SetApprovedRoutes", {"nodeId":"201","routes":[]}, "routes_replace", {"node_id":"201","routes":[]}, "POST", "/node/201/approve_routes", {}, {"routes":[]}),
 ("RegisterNode", {"user":"mcp-test","key":AUTH}, "register", {"operation":"legacy","user":"mcp-test","auth_id":AUTH}, "POST", "/node/register", {"user":"mcp-test","key":AUTH}, None),
 ("DeleteNode", {"nodeId":"201"}, "nodes", {"operation":"delete","node_id":"201"}, "DELETE", "/node/201", {}, None),
 ("ExpireNode", {"nodeId":"201","disableExpiry":True}, "nodes", {"operation":"expire","node_id":"201","mode":"disable"}, "POST", "/node/201/expire", {"disableExpiry":"true"}, None),
 ("RenameNode", {"nodeId":"201","newName":"renamed"}, "nodes", {"operation":"rename","node_id":"201","new_name":"renamed"}, "POST", "/node/201/rename/renamed", {}, None),
 ("ListNodes", {"user":"mcp-test"}, "nodes", {"operation":"list","user":"mcp-test"}, "GET", "/node", {"user":"mcp-test"}, None),
 ("BackfillNodeIPs", {"confirmed":True}, "backfill_ips", {"confirm":True}, "POST", "/node/backfillips", {"confirmed":"true"}, None),
 ("AuthRegister", {"user":"mcp-test","authId":AUTH}, "register", {"operation":"register","user":"mcp-test","auth_id":AUTH}, "POST", "/auth/register", {}, {"user":"mcp-test","authId":AUTH}),
 ("AuthApprove", {"authId":AUTH}, "auth", {"operation":"approve","auth_id":AUTH}, "POST", "/auth/approve", {}, {"authId":AUTH}),
 ("AuthReject", {"authId":AUTH}, "auth", {"operation":"reject","auth_id":AUTH}, "POST", "/auth/reject", {}, {"authId":AUTH}),
 ("CreateApiKey", {"expiration":EXPIRY}, "api_keys", {"operation":"create","expiration":EXPIRY,"reveal_once":True}, "POST", "/apikey", {}, {"expiration":EXPIRY}),
 ("ExpireApiKey", {"id":"401"}, "api_keys", {"operation":"expire","key_id":"401"}, "POST", "/apikey/expire", {}, {"id":"401"}),
 ("ListApiKeys", {}, "api_keys", {"operation":"list"}, "GET", "/apikey", {}, None),
 ("DeleteApiKey", {"prefix":PREFIX}, "api_keys", {"operation":"delete","prefix":PREFIX}, "DELETE", "/apikey/"+PREFIX, {}, None),
 ("GetPolicy", {}, "policy", {"operation":"get"}, "GET", "/policy", {}, None),
 ("SetPolicy", {"policy":P1}, "policy", {"operation":"apply","policy":P1,"expected_digest":DIGEST}, "PUT", "/policy", {}, {"policy":P1}),
 ("CheckPolicy", {"policy":P1}, "policy", {"operation":"check","policy":P1}, "POST", "/policy/check", {}, {"policy":P1}),
 ("Health", {}, "health", {}, "GET", "/health", {}, None),
]


def response_for(native):
    node = {"id":"201", "givenName":"test-device", "preAuthKey":{"id":"301","key":LEGACY}, "tags":[]}
    field = NATIVE_OPERATIONS[native].response_field
    if not field:
        return {}
    return {field: {"node":node,"user":{"id":"101","name":"mcp-test"},"nodes":[node],
                   "users":[{"id":"101","name":"mcp-test"}],"preAuthKey":{"id":"301","key":CREATED},
                   "preAuthKeys":[{"id":"301","key":LEGACY}],"apiKey":CREATED,
                   "apiKeys":[{"id":"401","prefix":PREFIX}],"policy":P1 if native == "SetPolicy" else P0,
                   "changes":[],"databaseConnectivity":True}[field]}


def save_state(path, **changes):
    state = {
        "schema_version": 4, "product": "headscale", "token": "a" * 43,
        "child_token": "b" * 43, "backend_url": None, "backend_key": None,
        "connection": {"url": "https://headscale.example.com/api/v1", "api_key": API_SECRET},
        "endpoint": None, "mcp_access_token": None, "writes_enabled": True,
        "disabled": [], "enabled_write_tools": sorted(WRITE_GRANTS),
        "denied_operations": {},
    }
    state.update(changes)
    temporary = path.with_name(".state-test")
    temporary.write_text(json.dumps(state))
    temporary.chmod(0o600)
    temporary.replace(path)
    return state


@pytest.fixture
def state_path(tmp_path):
    tmp_path.chmod(0o700)  # mirror HA ProductStore's protected /data/mcp
    path = tmp_path / "state.json"
    save_state(path)
    return path


def client_for(handler):
    return HeadscaleClient("https://headscale.example.com/api/v1", API_SECRET,
                           transport=httpx.MockTransport(handler))


def assert_wire(request, case):
    native, parameters, _, _, method, path, query, body = case
    assert request.method == method
    assert request.url.path == "/api/v1" + path
    assert dict(request.url.params) == query
    assert (json.loads(request.content) if request.content else None) == body
    assert request.headers["authorization"] == "Bearer " + API_SECRET
    assert request.url.host == "headscale.example.com"


def test_exact_native_surface():
    from mcp_admin_core.products import write_grants

    expected = {case[0] for case in CASES}
    assert len(CASES) == len(expected) == len(COVERAGE_MATRIX) == 29
    assert {row["operation_id"] for row in COVERAGE_MATRIX} == set(NATIVE_OPERATIONS) == expected
    assert len(TOOL_REGISTRY) == 11
    assert len(WRITE_GRANTS) == 21
    assert WRITE_GRANTS == write_grants("headscale")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
async def test_native_wire_and_default_secret_redaction(case):
    calls = []

    def handler(request):
        calls.append(request)
        assert_wire(request, case)
        return httpx.Response(200, json=response_for(case[0]))

    async with client_for(handler) as client:
        result = await client.request(case[0], **case[1])
    assert len(calls) == 1 and client.is_closed
    assert LEGACY not in json.dumps(result)
    assert CREATED not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
async def test_ha_task_dispatch_for_each_native_operation(case, state_path):
    calls = []

    def handler(request):
        calls.append(request)
        if case[0] == "SetPolicy" and request.method == "GET":
            return httpx.Response(200, json={"policy": P1 if any(r.method == "PUT" for r in calls) else P0})
        if case[0] == "SetPolicy" and request.url.path.endswith("/check"):
            return httpx.Response(200, json={})
        assert_wire(request, case)
        return httpx.Response(200, json=response_for(case[0]))

    async with client_for(handler) as client:
        result = await execute_tool("headscale_" + case[2], case[3], client, state_path=state_path)
    assert isinstance(result, dict)
    assert len(calls) == (5 if case[0] == "SetPolicy" else 1)
    assert LEGACY not in json.dumps(result)
    assert (CREATED in json.dumps(result)) == (case[0] in ("CreateApiKey", "CreatePreAuthKey"))
    if case[0] == "SetPolicy":
        assert [request.method for request in calls] == ["GET", "POST", "GET", "PUT", "GET"]
        assert result["readback_verified"] is True and result["atomic_cas"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [c for c in CASES if c[0] != "Health"], ids=lambda case: case[0])
async def test_saved_operation_deny_stops_each_task_before_io(case, state_path):
    name = "headscale_" + case[2]
    operation = case[3].get("operation") or next(s for s in TOOL_REGISTRY if s.name == name).operations[0]
    save_state(state_path, denied_operations={name: [operation]})
    calls = []
    async with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_DENIED"):
            await execute_tool(name, case[3], client, state_path=state_path)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [c for c in CASES if not NATIVE_OPERATIONS[c[0]].read_only])
async def test_missing_exact_write_grant_stops_io(case, state_path):
    name = "headscale_" + case[2]
    grant = name if "operation" not in case[3] else name + ":" + case[3]["operation"]
    save_state(state_path, enabled_write_tools=sorted(WRITE_GRANTS - {grant}))
    calls = []
    async with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_DENIED"):
            await execute_tool(name, case[3], client, state_path=state_path)
    assert calls == []


@pytest.mark.asyncio
async def test_policy_apply_rechecks_revocation_between_upstream_calls(state_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "GET":
            save_state(state_path, denied_operations={"headscale_policy": ["check"]})
            return httpx.Response(200, json={"policy": P0})
        raise AssertionError("revoked policy must never be checked or written")

    async with client_for(handler) as client:
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_DENIED"):
            await execute_tool("headscale_policy", {"operation": "apply", "policy": P1,
                                                     "expected_digest": DIGEST}, client, state_path=state_path)
    assert [request.method for request in calls] == ["GET"]


@pytest.mark.asyncio
async def test_raw_mcp_tool_call_obeys_live_state_and_private_health(state_path):
    from fastmcp import Client

    save_state(state_path, disabled=["headscale_health"], enabled_write_tools=[])
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"databaseConnectivity": True})

    backend = client_for(handler)
    async with Client(build_server(backend, state_path)) as mcp:
        names = {tool.name for tool in await mcp.list_tools()}
        assert "headscale_health" in names  # parent probe still reaches it
        assert "headscale_auth" not in names  # no read operation or grant
        rejected = await mcp.call_tool("headscale_users", {"operation": "create", "name": "x"},
                                       raise_on_error=False)
        assert rejected.is_error and "HEADSCALE_POLICY_DENIED" in rejected.content[0].text
        health = await mcp.call_tool("headscale_health", {})
        assert health.structured_content == {"databaseConnectivity": True}
        assert not health.is_error
        save_state(state_path, disabled=["headscale_health", "headscale_users"], enabled_write_tools=[])
        rejected = await mcp.call_tool("headscale_users", {"operation": "list"}, raise_on_error=False)
        assert rejected.is_error and "HEADSCALE_POLICY_DENIED" in rejected.content[0].text
        assert "headscale_users" not in {tool.name for tool in await mcp.list_tools()}
    assert len(calls) == 1 and backend.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"product": "n8n"},
    {"connection": {"url": "https://other.example.com", "api_key": API_SECRET}},
    {"connection": {"url": "https://headscale.example.com", "api_key": "changed-key"}},
    {"enabled_write_tools": ["headscale_users:made_up"]},
    {"denied_operations": {"headscale_users": ["delete", "delete"]}},
])
async def test_invalid_or_mismatched_ha_state_fails_closed(state_path, changes):
    save_state(state_path, **changes)
    calls = []
    async with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_UNAVAILABLE"):
            await execute_tool("headscale_health", {}, client, state_path=state_path)
    assert calls == []


@pytest.mark.asyncio
async def test_missing_symlink_duplicate_and_wrong_mode_state_fail_closed(state_path, tmp_path):
    calls = []
    async with client_for(lambda request: calls.append(request)) as client:
        state_path.unlink()
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_UNAVAILABLE"):
            await execute_tool("headscale_health", {}, client, state_path=state_path)
        save_state(state_path)
        state_path.chmod(0o644)
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_UNAVAILABLE"):
            await execute_tool("headscale_health", {}, client, state_path=state_path)
        save_state(state_path)
        state_path.write_text('{"product":"headscale","product":"headscale"}')
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_UNAVAILABLE"):
            await execute_tool("headscale_health", {}, client, state_path=state_path)
        save_state(state_path)
        other = tmp_path / "other.json"
        state_path.replace(other)
        state_path.symlink_to(other)
        with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_UNAVAILABLE"):
            await execute_tool("headscale_health", {}, client, state_path=state_path)
    assert calls == []


@pytest.mark.parametrize("url,allowed", [
    ("http://10.43.1.2:8080", True), ("http://172.30.1.2", True),
    ("http://192.168.4.5", True), ("http://100.100.100.200", False),
    ("http://169.254.169.254", False), ("http://127.0.0.1:3000", False),
    ("http://[::1]", False), ("http://metadata.google.internal", False),
])
def test_ha_address_classes_and_headscale_loopback_deny(url, allowed):
    if allowed:
        assert Destination(url).base_url == url
    else:
        with pytest.raises(HeadscaleError, match="HEADSCALE_DESTINATION_DENIED"):
            Destination(url)


@pytest.mark.asyncio
async def test_mixed_dns_answers_deny_before_tcp(monkeypatch):
    attempted = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))
        for ip in ("10.43.1.2", "169.254.169.254")])

    async def connect(self, *args, **kwargs):
        attempted.append(args)

    monkeypatch.setattr("httpcore._backends.anyio.AnyIOBackend.connect_tcp", connect)
    destination = Destination("http://headscale.sandbox.svc:8080")
    with pytest.raises(HeadscaleError, match="HEADSCALE_DESTINATION_DENIED"):
        await PinnedNetwork(destination).connect_tcp(destination.host, destination.port)
    assert attempted == []


@pytest.mark.asyncio
async def test_dns_falls_back_to_next_validated_address_after_stale_first_answer(monkeypatch):
    addresses = ["10.43.1.2", "10.43.1.3"]
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))
        for address in addresses])
    attempts = []

    async def connect(self, host, port, **kw):
        attempts.append((host, kw["timeout"]))
        if host == addresses[0]:
            raise httpcore.ConnectTimeout("stale address")
        return "stream"

    monkeypatch.setattr("httpcore._backends.anyio.AnyIOBackend.connect_tcp", connect)
    destination = Destination("http://headscale.sandbox.svc:8080")
    assert await PinnedNetwork(destination).connect_tcp(destination.host, destination.port) == "stream"
    assert [host for host, _ in attempts] == addresses
    assert attempts[0][1] <= 2.6


def test_launch_contract_and_loopback_only(monkeypatch, state_path):
    import launch
    import session_idle
    import headscale_mcp_server.client as client_module
    import headscale_mcp_server.server as server_module

    events = []
    monkeypatch.setenv("HEADSCALE_MCP_BASE_URL", "https://headscale.example.com")
    monkeypatch.setenv("HEADSCALE_MCP_API_KEY", API_SECRET)
    monkeypatch.setenv("HEADSCALE_MCP_STATE_PATH", str(state_path))
    monkeypatch.setattr(session_idle, "install", lambda: events.append("idle"))

    class FakeServer:
        def run(self, **kwargs):
            events.append(("run", kwargs))

    monkeypatch.setattr(client_module, "HeadscaleClient", lambda url, key: events.append(("client", url, key)) or object())
    monkeypatch.setattr(server_module, "build_server", lambda client, path: events.append(("build", path)) or FakeServer())
    launch.main(["--host", "127.0.0.1", "--port", "3000"])
    assert events[0] == "idle"
    assert events[1][:2] == ("client", "https://headscale.example.com")
    assert events[2] == ("build", str(state_path))
    assert events[3] == ("run", {"transport": "streamable-http", "host": "127.0.0.1",
                                 "port": 3000, "path": "/mcp", "show_banner": False})
    with pytest.raises(SystemExit):
        launch.main(["--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        launch.main(["--port", "0"])
    with pytest.raises(SystemExit):
        launch.main(["--port", "65536"])


@pytest.mark.asyncio
async def test_reader_accepts_actual_ha_product_store_and_live_revocation(tmp_path):
    from mcp_admin_core.products import ProductStore

    store = ProductStore(tmp_path / "mcp", "headscale")
    calls = []
    try:
        store.update(connection={"url": "https://headscale.example.com/api/v1", "api_key": API_SECRET})
        assert store.path == tmp_path / "mcp/state.json"
        async with client_for(lambda request: calls.append(request) or
                              httpx.Response(200, json={"databaseConnectivity": True})) as client:
            result = await execute_tool("headscale_health", {}, client, state_path=store.path)
            assert result == {"databaseConnectivity": True}
            store.update(enabled_write_tools=[])
            with pytest.raises(HeadscaleError, match="HEADSCALE_POLICY_DENIED"):
                await execute_tool("headscale_routes_replace", {"node_id": "201", "routes": []},
                                   client, state_path=store.path)
    finally:
        store.close()
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,expected", [
    ("timeout", "HEADSCALE_POLICY_UNVERIFIED"),
    ("conflict", "HEADSCALE_POLICY_CONFLICT"),
    ("revoked", "HEADSCALE_POLICY_UNVERIFIED"),
])
async def test_postwrite_failure_is_unknown_and_never_replays_put(failure, expected, state_path):
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "PUT" and failure == "revoked":
            save_state(state_path, disabled=["headscale_policy"])
        if request.method == "GET" and "PUT" in calls and failure == "timeout":
            raise httpx.ReadTimeout(API_SECRET, request=request)
        return httpx.Response(200, json={"policy": P0} if request.method == "GET" else
                              {"policy": P1} if request.method == "PUT" else {})

    async with client_for(handler) as client:
        with pytest.raises(HeadscaleError) as error:
            await execute_tool("headscale_policy", {"operation": "apply", "policy": P1,
                                                    "expected_digest": DIGEST}, client, state_path=state_path)
    assert error.value.code == expected and error.value.outcome == "unknown"
    assert calls.count("PUT") == 1
    assert API_SECRET not in json.dumps(error.value.as_dict()) + str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("native,parameters", [
    ("ListUsers", {}), ("DeleteNode", {"nodeId": "201"}),
])
async def test_transport_failure_never_retries_or_leaks_credential(native, parameters):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(API_SECRET + str(request.url), request=request)

    async with client_for(handler) as client:
        with pytest.raises(HeadscaleError) as error:
            await client.request(native, **parameters)
    assert len(calls) == 1
    assert error.value.outcome == ("rejected" if native == "ListUsers" else "unknown")
    assert API_SECRET not in json.dumps(error.value.as_dict()) + str(error.value)


@pytest.mark.asyncio
async def test_partial_write_response_closes_stream_without_retry():
    class BrokenStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'{"node":'
            raise httpx.ReadError(API_SECRET)

        async def aclose(self):
            self.closed = True

    stream, calls = BrokenStream(), []
    async with client_for(lambda request: calls.append(request) or
                          httpx.Response(200, stream=stream)) as client:
        with pytest.raises(HeadscaleError) as error:
            await client.request("RenameNode", nodeId="201", newName="renamed")
    assert stream.closed and len(calls) == 1 and error.value.outcome == "unknown"


@pytest.mark.asyncio
async def test_created_key_copies_are_masked_except_explicit_reveal():
    def handler(request):
        return httpx.Response(200, json={"apiKey": CREATED, "echo": "issued " + CREATED})

    async with client_for(handler) as client:
        hidden = await client.request("CreateApiKey", expiration=EXPIRY)
        revealed = await client.request("CreateApiKey", expiration=EXPIRY,
                                        reveal_created_secret=True)
    assert CREATED not in json.dumps(hidden)
    assert revealed["apiKey"] == CREATED
    assert CREATED not in revealed["echo"]


@pytest.mark.asyncio
async def test_production_transport_accepts_default_port_and_rejects_other_origins(monkeypatch):
    calls = []

    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json={"databaseConnectivity": True})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    async with HeadscaleTransport(Destination("https://headscale.example.com")) as transport:
        good = httpx.Request("GET", "https://headscale.example.com/api/v1/health")
        assert (await transport.handle_async_request(good)).status_code == 200
        for bad in (
            httpx.Request("GET", "https://other.example.com/api/v1/health"),
            httpx.Request("GET", "https://headscale.example.com/other"),
            httpx.Request("GET", "https://headscale.example.com:444/api/v1/health"),
        ):
            with pytest.raises(HeadscaleError, match="HEADSCALE_DESTINATION_DENIED"):
                await transport.handle_async_request(bad)
        override = httpx.Request("GET", "https://headscale.example.com/api/v1/health",
                                 extensions={"target": b"/other"})
        with pytest.raises(HeadscaleError, match="HEADSCALE_DESTINATION_DENIED"):
            await transport.handle_async_request(override)
    assert calls == [good]


def test_log_records_redact_upstream_api_key(caplog):
    from headscale_mcp_server.log_redaction import install, set_secrets

    install()
    set_secrets(API_SECRET)
    with caplog.at_level(logging.WARNING):
        logging.warning("upstream rejected %s", {"authorization": API_SECRET})
    assert API_SECRET not in caplog.text
