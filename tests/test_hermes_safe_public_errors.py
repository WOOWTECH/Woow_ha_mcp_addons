"""Exact public Dashboard error contract through the real HA MCP child."""

import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import httpx
import pytest
import test_six_hardening as harness
from test_hermes_dashboard_error_guidance import ACCEPT, INIT
from test_real_products import rpc
from test_six_hardening import Quiet, call, runtime, serve

AUTH_403 = (
    "BACKEND_AUTH_REJECTED status=403: Hermes Dashboard 憑證被拒 "
    "(credentials rejected); update Connection > Dashboard REST API in the MCP "
    "admin page and press Save & Restart."
)
BODY_CANARY = "CANARY_UPSTREAM_403_BODY_PRIVATE_4817"
URL_CANARY = "CANARY_CONFIG_URL_PRIVATE_4817"
UNAVAILABLE = (
    "BACKEND_UNAVAILABLE: Hermes Dashboard 不可達 (unreachable): Check that the Hermes service is running "
    "and that Connection > Dashboard REST API in the MCP admin page has the right address."
)
INVALID_URL = (
    "BACKEND_UNAVAILABLE: dashboard_url must be a valid http:// or https:// URL - "
    "fix it in the admin GUI under Connection > Dashboard REST API"
)
UNREADABLE = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned an unreadable response; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)
NON_JSON = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned non-JSON; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)
BASE_INPUT_SCHEMA_MAP_SHA256 = "85ec47b65a6d274860e2167bec1d54afe3ad18453cfb77a67b573219bb18eae0"
BASE_OUTPUT_SCHEMA_MAP_SHA256 = "442e23b55b5db7a24604296aa51f46c286383232576383b69b662a727aa3b83e"


def _digest(value):
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _tool_text(reply, name):
    assert reply["isError"] is True
    text = reply["content"][0]["text"]
    prefix = f"Error executing tool {name}: "
    assert text.startswith(prefix), text
    return text[len(prefix):]


async def _direct_call(child, endpoint, name, arguments, ident):
    headers = ACCEPT.copy()  # rpc adds a session ID to this dict.
    await rpc(child, endpoint.url, headers, INIT)
    await rpc(child, endpoint.url, headers, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return await rpc(child, endpoint.url, headers, call(name, arguments, id=ident))


async def _direct_list(child, endpoint):
    headers = ACCEPT.copy()
    await rpc(child, endpoint.url, headers, INIT)
    await rpc(child, endpoint.url, headers, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return await rpc(child, endpoint.url, headers, {"jsonrpc": "2.0", "id": 34, "method": "tools/list"})


def _inject_legacy_url(monkeypatch, legacy_url):
    original_child_spec = harness.child_spec

    def child_spec_with_legacy_url(*args, **kwargs):
        spec = original_child_spec(*args, **kwargs)
        spec.env["HERMES_DASHBOARD_URL"] = legacy_url
        return spec

    monkeypatch.setattr(harness, "child_spec", child_spec_with_legacy_url)


async def test_dashboard_403_body_and_config_url_are_not_public(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            events.append(("POST", self.path))
            assert self.path.split("?", 1)[0].endswith("/auth/password-login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=test-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            events.append(("GET", self.path))
            assert self.path.split("?", 1)[0].endswith("/api/status")
            self.reply({"detail": BODY_CANARY}, 403)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, canary=URL_CANARY) as (client, headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 31)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 32)
            relayed = await rpc(client, "/mcp", headers, call("hermes_gateway", {"action": "status"}, id=33))
            listing = await _direct_list(child, manager.endpoint)

    assert _tool_text(gateway, "hermes_gateway") == AUTH_403
    assert _tool_text(relayed, "hermes_gateway") == AUTH_403
    assert inspect["isError"] is True
    text_json = json.loads(inspect["content"][0]["text"])
    structured_json = json.loads(inspect["structuredContent"]["result"])
    assert text_json == structured_json == {"status_error": AUTH_403}
    for reply in (gateway, inspect, relayed):
        raw = json.dumps(reply, ensure_ascii=False)
        assert BODY_CANARY not in raw and URL_CANARY not in raw and base not in raw
    assert sum(method == "POST" for method, _ in events) == 1  # 403 does not refresh login.
    assert sum(method == "GET" for method, _ in events) == 3
    tools = listing["tools"]
    assert len(tools) == len({tool["name"] for tool in tools}) == 11
    for kind, baseline_hash in (
        ("input", BASE_INPUT_SCHEMA_MAP_SHA256),
        ("output", BASE_OUTPUT_SCHEMA_MAP_SHA256),
    ):
        schema_hashes = {tool["name"]: _digest(tool[f"{kind}Schema"]) for tool in tools}
        assert _digest(schema_hashes) == baseline_hash


async def test_legacy_dashboard_url_is_denied_before_backend_without_public_leak(tmp_path, monkeypatch):
    events = []

    class Dashboard(Quiet):
        def do_GET(self):
            events.append("GET")
            self.reply({"detail": BODY_CANARY}, 403)

        def do_POST(self):
            events.append("POST")
            self.reply({"detail": BODY_CANARY}, 403)

    with serve(Dashboard) as base:
        # A saved ProductStore config rejects this legacy URL. Inject only into
        # the isolated child spec to test the runtime's destination guard.
        legacy_url = base.replace("http://", f"http://user:{URL_CANARY}@")
        legacy_url += f"/private/{URL_CANARY}?token={URL_CANARY}"
        _inject_legacy_url(monkeypatch, legacy_url)
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 35)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 36)

    assert _tool_text(gateway, "hermes_gateway") == "BACKEND_DESTINATION_DENIED"
    assert json.loads(inspect["structuredContent"]["result"]) == {
        "status_error": "BACKEND_DESTINATION_DENIED"
    }
    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert URL_CANARY not in raw and BODY_CANARY not in raw and base not in raw
    assert events == []


async def test_invalid_dashboard_url_omits_legacy_sensitive_value(tmp_path, monkeypatch):
    events = []

    class Dashboard(Quiet):
        def do_GET(self):
            events.append("GET")
            self.reply({"detail": BODY_CANARY}, 403)

        def do_POST(self):
            events.append("POST")
            self.reply({"detail": BODY_CANARY}, 403)

    with serve(Dashboard) as base:
        _inject_legacy_url(monkeypatch, f"private-path?token={URL_CANARY}")
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 37)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 38)

    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert "dashboard_url must start with http:// or https://" in raw
    assert URL_CANARY not in raw and "private-path" not in raw and base not in raw
    assert events == []


async def test_invalid_dashboard_port_has_fixed_safe_mcp_error(tmp_path, monkeypatch):
    events = []

    class Dashboard(Quiet):
        def do_GET(self):
            events.append("GET")
            self.reply({"detail": BODY_CANARY}, 403)

        def do_POST(self):
            events.append("POST")
            self.reply({"detail": BODY_CANARY}, 403)

    with serve(Dashboard) as base:
        _inject_legacy_url(monkeypatch, f"http://127.0.0.1:invalid-{URL_CANARY}/private?token={URL_CANARY}")
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 39)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 40)

    assert _tool_text(gateway, "hermes_gateway") == INVALID_URL
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": INVALID_URL}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": INVALID_URL}
    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert URL_CANARY not in raw and BODY_CANARY not in raw and base not in raw
    assert events == []


async def test_bad_gzip_has_fixed_unreadable_mcp_error(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            events.append("login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=test-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            events.append("status")
            body = BODY_CANARY.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 43)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 44)

    assert _tool_text(gateway, "hermes_gateway") == UNREADABLE
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": UNREADABLE}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": UNREADABLE}
    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert BODY_CANARY not in raw and base not in raw
    assert events.count("login") == 1 and events.count("status") == 2


async def test_invalid_utf8_json_has_fixed_safe_mcp_error(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            events.append("login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=test-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            events.append("status")
            body = b'{"version":"' + BODY_CANARY.encode() + b'\xff"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (client, headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 45)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 46)
            relayed = await rpc(client, "/mcp", headers, call("hermes_gateway", {"action": "status"}, id=47))

    assert _tool_text(gateway, "hermes_gateway") == NON_JSON
    assert _tool_text(relayed, "hermes_gateway") == NON_JSON
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": NON_JSON}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": NON_JSON}
    raw = json.dumps([gateway, inspect, relayed], ensure_ascii=False)
    assert BODY_CANARY not in raw and base not in raw
    assert "UnicodeDecodeError" not in raw and "invalid start byte" not in raw
    assert events.count("login") == 1 and events.count("status") == 3


@pytest.mark.parametrize("status,detail,expected", [
    (401, BODY_CANARY,
     ("BACKEND_AUTH_REJECTED status=401: Hermes Dashboard 憑證被拒 (credentials rejected); "
      "update Connection > Dashboard REST API in the MCP admin page and press Save & Restart.")),
    (307, BODY_CANARY,
     ("BACKEND_REDIRECT_REJECTED status=307: Hermes Dashboard returned a redirect; "
      "verify Connection > Dashboard REST API in the MCP admin page and press Save & Restart.")),
    (422, BODY_CANARY,
     ("BACKEND_HTTP_ERROR status=422: Hermes Dashboard request failed; verify "
      "Connection > Dashboard REST API in the MCP admin page and the operation settings.")),
    (409, "revision_conflict",
     ("BACKEND_HTTP_ERROR status=409 code=revision_conflict: Hermes Dashboard rejected the operation; "
      "check the session state and Connection > Dashboard REST API in the MCP admin page.")),
    (409, "admission_conflict",
     ("BACKEND_HTTP_ERROR status=409 code=admission_conflict: Hermes Dashboard rejected the operation; "
      "check the session state and Connection > Dashboard REST API in the MCP admin page.")),
    (409, "client_upgrade_required",
     ("BACKEND_HTTP_ERROR status=409 code=client_upgrade_required: Hermes Dashboard rejected the operation; "
      "check the session state and Connection > Dashboard REST API in the MCP admin page.")),
    (409, "revision_conflict" + BODY_CANARY,
     ("BACKEND_HTTP_ERROR status=409: Hermes Dashboard request failed; verify "
      "Connection > Dashboard REST API in the MCP admin page and the operation settings.")),
    (502, BODY_CANARY,
     ("BACKEND_UNAVAILABLE status=502: Hermes Dashboard 不可達 (unreachable); "
      "check that the Hermes service is running and verify Connection > Dashboard REST API in the MCP admin page.")),
])
async def test_dashboard_statuses_have_exact_safe_mcp_message(tmp_path, status, detail, expected):
    events = []
    sink_hits = []

    class Sink(Quiet):
        def do_GET(self):
            sink_hits.append(self.path)
            self.reply({"ok": True})

    with serve(Sink) as sink:
        class Dashboard(Quiet):
            def do_POST(self):
                events.append("login")
                self.send_response(200)
                self.send_header("Set-Cookie", "hermes_session_at=test-cookie")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def do_GET(self):
                events.append("status")
                if status == 307:
                    self.send_response(307)
                    self.send_header("Location", sink + "/" + BODY_CANARY)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self.reply({"detail": detail}, status)

        with serve(Dashboard) as base:
            async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
                gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 41)
                inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 42)

    assert _tool_text(gateway, "hermes_gateway") == expected
    assert inspect["isError"] is True
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": expected}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": expected}
    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert BODY_CANARY not in raw and base not in raw and sink not in raw
    assert sink_hits == []
    assert events.count("login") == (3 if status == 401 else 1)
    assert events.count("status") == (4 if status == 401 else 2)


async def test_dashboard_accepted_then_disconnected_is_fixed_and_has_no_exception_text(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            events.append("login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=test-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            events.append("status")
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 51)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 52)

    assert _tool_text(gateway, "hermes_gateway") == UNAVAILABLE
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": UNAVAILABLE}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": UNAVAILABLE}
    raw = json.dumps([gateway, inspect], ensure_ascii=False)
    assert base not in raw and "RemoteProtocolError" not in raw and "Server disconnected" not in raw
    assert events.count("login") == 1
    assert events.count("status") >= 2


def test_formatter_omits_synthetic_legacy_url_body_and_transport_text():
    # A legacy malformed URL cannot pass today's ProductStore validation, but
    # the error formatter itself must remain safe if such a value reaches it.
    path = Path(__file__).resolve().parents[1] / "apps/hermes/vendor/hermes_mcp_server/errors.py"
    spec = importlib.util.spec_from_file_location("hermes_safe_errors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = httpx.Request(
        "GET", f"http://user:{URL_CANARY}@example.invalid/private/{URL_CANARY}?token={URL_CANARY}"
    )
    response = httpx.Response(403, request=request, json={"detail": BODY_CANARY},
                              headers={"Location": "https://sink.invalid/" + BODY_CANARY})
    status_error = httpx.HTTPStatusError(BODY_CANARY, request=request, response=response)
    assert module.public_dashboard_error(status_error) == AUTH_403
    transport_error = httpx.RemoteProtocolError(BODY_CANARY, request=request)
    assert module.public_dashboard_error(transport_error) == UNAVAILABLE
    for status in (503, 504, 520, 521, 522, 523, 524, 525, 526, 530):
        response = httpx.Response(status, request=request, json={"detail": BODY_CANARY})
        status_error = httpx.HTTPStatusError(BODY_CANARY, request=request, response=response)
        assert module.public_dashboard_error(status_error) == (
            f"BACKEND_UNAVAILABLE status={status}: Hermes Dashboard 不可達 (unreachable); "
            "check that the Hermes service is running and verify Connection > Dashboard REST API "
            "in the MCP admin page."
        )
    timeout_error = httpx.ReadTimeout(BODY_CANARY, request=request)
    assert module.public_dashboard_error(timeout_error) == (
        "BACKEND_TIMEOUT: Hermes Dashboard timed out; check the Hermes service and "
        "Connection > Dashboard REST API in the MCP admin page."
    )
    decode_error = json.JSONDecodeError(BODY_CANARY, BODY_CANARY, 0)
    assert module.public_dashboard_error(decode_error) == (
        "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned non-JSON; verify "
        "Connection > Dashboard REST API in the MCP admin page."
    )
