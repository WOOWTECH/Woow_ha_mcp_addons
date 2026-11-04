"""Actual HA MCP child probes for nested Dashboard shapes and cron writes."""

import json
import socket

import pytest
from test_hermes_safe_public_errors import _direct_call, _tool_text
from test_six_hardening import Quiet, runtime, serve

SENTINEL = "SYNTHETIC_PRIVATE_NESTED_6431"
SHAPE_ERROR = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned an unexpected JSON shape; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)
CREATE_UNKNOWN = (
    "CRON_CREATE_OUTCOME_UNKNOWN: Hermes cron create outcome is unknown. "
    "No automatic retry was made. List scheduled jobs in Hermes before deciding to retry."
)
AUTH_401 = (
    "BACKEND_AUTH_REJECTED status=401: Hermes Dashboard 憑證被拒 (credentials rejected); "
    "update Connection > Dashboard REST API in the MCP admin page and press Save & Restart."
)
CREATE_502 = (
    "CRON_CREATE_OUTCOME_UNKNOWN: Hermes cron create outcome is unknown. "
    "No automatic retry was made. List scheduled jobs in Hermes before deciding to retry."
)
CREATE_DISCONNECT = (
    "CRON_CREATE_OUTCOME_UNKNOWN: Hermes cron create outcome is unknown. "
    "No automatic retry was made. List scheduled jobs in Hermes before deciding to retry."
)


@pytest.mark.parametrize("tool,arguments,path,payload", [
    ("hermes_webhook", {"action": "list"}, "/api/webhooks",
     {"subscriptions": None, "private": SENTINEL}),
    ("hermes_model", {"action": "list_providers"}, "/api/model/options",
     {"providers": [{"models": 42}], "private": SENTINEL}),
    ("hermes_cron", {"action": "list"}, "/api/cron/jobs",
     [{"prompt": 42, "private": SENTINEL}]),
    ("hermes_cron", {"action": "list"}, "/api/cron/jobs",
     {"jobs": [{"prompt": 42}], "private": SENTINEL}),
], ids=["webhook-null-subscriptions", "model-numeric-models", "cron-numeric-prompt", "cron-object-passthrough"])
async def test_nested_read_shape_is_fixed_and_does_not_echo_private_fields(
    tmp_path, tool, arguments, path, payload
):
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
            assert self.path == path
            events.append("read")
            self.reply(payload)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            reply = await _direct_call(child, manager.endpoint, tool, arguments, 71)

    assert _tool_text(reply, tool) == SHAPE_ERROR
    public = json.dumps(reply, ensure_ascii=False)
    assert SENTINEL not in public and base not in public
    assert "TypeError" not in public and "NoneType" not in public
    assert events == ["login", "read"]


@pytest.mark.parametrize("status,expected", [(200, CREATE_UNKNOWN), (401, AUTH_401), (502, CREATE_502)],
                         ids=["null-ack", "fenced-401", "unknown-502"])
async def test_cron_create_never_retries_and_marks_unconfirmed_result(tmp_path, status, expected):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            if self.path.endswith("/auth/password-login"):
                events.append("login")
                self.send_response(200)
                self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            assert self.path == "/api/cron/jobs"
            events.append("create")
            self.reply(b"null" if status == 200 else {"detail": SENTINEL}, status)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", {
                "action": "create", "name": "synthetic-cron",
                "schedule": "* * * * *", "prompt": "hello",
            }, 72)

    assert _tool_text(reply, "hermes_cron") == expected
    public = json.dumps(reply, ensure_ascii=False)
    assert SENTINEL not in public and base not in public
    assert events == ["login", "create"]


async def test_cron_create_disconnect_after_accept_is_unknown_without_retry(tmp_path):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            if self.path.endswith("/auth/password-login"):
                events.append("login")
                self.send_response(200)
                self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            assert self.path == "/api/cron/jobs"
            events.append("create")
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", {
                "action": "create", "name": "synthetic-cron",
                "schedule": "* * * * *", "prompt": "hello",
            }, 74)

    assert _tool_text(reply, "hermes_cron") == CREATE_DISCONNECT
    assert events == ["login", "create"]
    assert base not in json.dumps(reply, ensure_ascii=False)


@pytest.mark.parametrize("tool,arguments,path,method,payload,expected", [
    ("hermes_webhook", {"action": "list"}, "/api/webhooks", "GET",
     {"enabled": True, "subscriptions": [{"name": "safe", "enabled": True, "prompt": "hello"}], "private": SENTINEL},
     {"total": 1, "platform_enabled": True}),
    ("hermes_model", {"action": "list_providers"}, "/api/model/options", "GET",
     {"model": "one", "provider": "safe", "providers": [{"slug": "safe", "models": ["one"]}], "private": SENTINEL},
     {"current": {"model": "one", "provider": "safe"}}),
    ("hermes_cron", {"action": "list"}, "/api/cron/jobs", "GET",
     [{"id": "c1", "prompt": "hello", "schedule": {"expr": "* * * * *"}, "private": SENTINEL}],
     {"total": 1}),
    ("hermes_cron", {"action": "create", "name": "safe", "schedule": "* * * * *", "prompt": "hello"},
     "/api/cron/jobs", "POST",
     {"id": "c1", "name": "safe", "schedule": {"expr": "* * * * *"}, "private": SENTINEL},
     {"ok": True, "id": "c1"}),
], ids=["webhook", "model", "cron-list", "cron-create"])
async def test_valid_dashboard_shapes_keep_success_projection(
    tmp_path, tool, arguments, path, method, payload, expected
):
    events = []

    class Dashboard(Quiet):
        def do_POST(self):
            if self.path.endswith("/auth/password-login"):
                events.append("login")
                self.send_response(200)
                self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            assert method == "POST" and self.path == path
            events.append("write")
            self.reply(payload)

        def do_GET(self):
            assert method == "GET" and self.path == path
            events.append("read")
            self.reply(payload)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, tool, arguments, 73)

    assert reply["isError"] is False
    result = json.loads(reply["content"][0]["text"])
    for key, value in expected.items():
        assert result[key] == value
    assert SENTINEL not in json.dumps(reply, ensure_ascii=False)
    assert events == ["login", "write" if method == "POST" else "read"]
