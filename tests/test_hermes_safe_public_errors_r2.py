"""Synthetic Dashboard parsing boundaries through the actual HA MCP child."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from test_hermes_safe_public_errors import _direct_call, _tool_text
from test_six_hardening import Quiet, runtime, serve

BODY_SENTINEL = "SYNTHETIC_PRIVATE_NESTED_BODY_2846"
DEEP_409 = b"[" * 16384 + json.dumps(BODY_SENTINEL).encode() + b"]" * 16384
GENERIC_409 = (
    "BACKEND_HTTP_ERROR status=409: Hermes Dashboard request failed; verify "
    "Connection > Dashboard REST API in the MCP admin page and the operation settings."
)
NON_OBJECT = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned a non-object JSON response; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)
NON_JSON = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned non-JSON; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)


async def test_deep_409_is_fixed_for_gateway_inspect_and_single_fenced_delete(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            assert self.path.endswith("/auth/password-login")
            events.append("login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            if self.path.endswith("/api/status"):
                events.append("status")
                self.reply(DEEP_409, 409)
            else:
                assert self.path.endswith("/api/sessions/synthetic-session/mutation-snapshot")
                events.append("snapshot")
                self.reply({
                    "session_id": "synthetic-session", "exists": True,
                    "runtime_revision": 7, "runtime_generation": 3,
                })

        def do_DELETE(self):
            parsed = urlsplit(self.path)
            assert parsed.path == "/api/sessions/synthetic-session"
            params = parse_qs(parsed.query)
            assert set(params) == {"request_id", "expected_revision", "expected_generation"}
            assert params["expected_revision"] == ["7"]
            assert params["expected_generation"] == ["3"]
            assert len(params["request_id"]) == 1 and params["request_id"][0]
            events.append("delete")
            self.reply(DEEP_409, 409)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_session:delete",)) as (
            _client, _headers, _store, manager, child
        ):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 61)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 62)
            deletion = await _direct_call(child, manager.endpoint, "hermes_session", {
                "action": "delete", "session_id": "synthetic-session",
            }, 63)

    assert _tool_text(gateway, "hermes_gateway") == GENERIC_409
    assert inspect["isError"] is True
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": GENERIC_409}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": GENERIC_409}
    assert _tool_text(deletion, "hermes_session") == GENERIC_409
    assert events.count("delete") == 1 and events.count("snapshot") == 1
    assert events.count("status") == 2
    assert events.count("login") == 1
    public = json.dumps([gateway, inspect, deletion], ensure_ascii=False)
    assert BODY_SENTINEL not in public and base not in public
    assert "RecursionError" not in public and "recursion" not in public.lower()


@pytest.mark.parametrize("payload,expected", [(b"null", NON_OBJECT), (DEEP_409, NON_JSON)],
                         ids=["null", "deep-json"])
async def test_invalid_status_shape_has_fixed_error_in_gateway_and_inspect(tmp_path, payload, expected):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            assert self.path.endswith("/auth/password-login")
            events.append("login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            assert self.path.endswith("/api/status")
            events.append("status")
            self.reply(payload)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            gateway = await _direct_call(child, manager.endpoint, "hermes_gateway", {"action": "status"}, 64)
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "status"}, 65)

    assert _tool_text(gateway, "hermes_gateway") == expected
    assert inspect["isError"] is True
    assert json.loads(inspect["content"][0]["text"]) == {"status_error": expected}
    assert json.loads(inspect["structuredContent"]["result"]) == {"status_error": expected}
    public = json.dumps([gateway, inspect], ensure_ascii=False)
    assert "AttributeError" not in public and "NoneType" not in public and base not in public
    assert events.count("status") == 2


async def test_json_null_config_has_fixed_shape_error_in_inspect(tmp_path):
    class Dashboard(Quiet):
        def do_POST(self):
            assert self.path.endswith("/auth/password-login")
            self.send_response(200)
            self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            assert self.path.endswith("/api/config")
            self.reply(b"null")

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            inspect = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "config"}, 66)

    assert inspect["isError"] is True
    assert json.loads(inspect["content"][0]["text"]) == {"config_error": NON_OBJECT}
    assert json.loads(inspect["structuredContent"]["result"]) == {"config_error": NON_OBJECT}
    assert base not in json.dumps(inspect, ensure_ascii=False)
