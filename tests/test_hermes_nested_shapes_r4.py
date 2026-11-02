"""PaaS 4eb public contract and nested write boundaries through the HA MCP child."""

import json

import pytest
from test_hermes_safe_public_errors import _direct_call, _tool_text
from test_six_hardening import Quiet, runtime, serve

CANARY = "SYNTHETIC_PRIVATE_R4_20261102"
NESTED_SHAPE = (
    "BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned an unexpected JSON shape; "
    "verify Connection > Dashboard REST API in the MCP admin page."
)
CRON_UNKNOWN = (
    "CRON_CREATE_OUTCOME_UNKNOWN: Hermes cron create outcome is unknown. "
    "No automatic retry was made. List scheduled jobs in Hermes before deciding to retry."
)
CREATE = {"action": "create", "name": "safe", "schedule": "* * * * *", "prompt": "hello"}


@pytest.mark.parametrize("tool,args,method,path,body,expected", [
    ("hermes_webhook", {"action": "list"}, "GET", "/api/webhooks",
     {"subscriptions": None, "private": CANARY}, NESTED_SHAPE),
    ("hermes_cron", CREATE, "POST", "/api/cron/jobs", b"null", CRON_UNKNOWN),
], ids=["nested-shape", "stage-free-cron"])
async def test_exact_paas_4eb_public_text(tmp_path, tool, args, method, path, body, expected):
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
            self.reply(body)

        def do_GET(self):
            assert method == "GET" and self.path == path
            events.append("read")
            self.reply(body)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, tool, args, 81)

    assert _tool_text(reply, tool) == expected
    assert CANARY not in json.dumps(reply, ensure_ascii=False)
    assert events == ["login", "write" if method == "POST" else "read"]


@pytest.mark.parametrize("job", [
    {"id": "j1", "schedule": {"expr": {"private": CANARY}}},
    {"id": True, "schedule": {"expr": "* * * * *"}},
    {"id": "j1", "next_run_at": True},
    {"id": "j1", "name": True},
    {"id": "j1", "state": True},
], ids=["private-schedule-expr", "bool-id", "bool-next-run", "bool-name", "bool-state"])
async def test_cron_list_rejects_invalid_projected_fields(tmp_path, job):
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
            assert self.path == "/api/cron/jobs"
            events.append("read")
            self.reply([job])

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", {"action": "list"}, 82)

    assert _tool_text(reply, "hermes_cron") == NESTED_SHAPE
    public = json.dumps(reply, ensure_ascii=False)
    assert CANARY not in public and base not in public
    assert events == ["login", "read"]


@pytest.mark.parametrize("case,body", [
    ("private-schedule-expr", {"id": "c1", "schedule": {"expr": {"private": CANARY}}}),
    ("ok-false", {"id": "c1", "ok": False}),
    ("bool-id", {"id": True}),
    ("bool-next-run", {"id": "c1", "next_run_at": True}),
    ("bad-gzip", b"not-a-gzip-stream"),
], ids=["private-schedule-expr", "ok-false", "bool-id", "bool-next-run", "bad-gzip"])
async def test_cron_create_unconfirmed_ack_is_unknown_without_replay(tmp_path, case, body):
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
            events.append("write")
            if case == "bad-gzip":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.reply(body)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", CREATE, 83)

    assert _tool_text(reply, "hermes_cron") == CRON_UNKNOWN
    public = json.dumps(reply, ensure_ascii=False)
    assert CANARY not in public and base not in public
    assert events == ["login", "write"]


@pytest.mark.parametrize("ident", [0, 17], ids=["zero", "seventeen"])
async def test_cron_create_accepts_nonnegative_integer_id(tmp_path, ident):
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
            events.append("write")
            self.reply({"id": ident, "name": "safe", "schedule": {"expr": "* * * * *"}})

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", CREATE, 84)

    assert reply["isError"] is False
    assert json.loads(reply["content"][0]["text"]) == {
        "ok": True, "id": ident, "name": "safe", "schedule": "* * * * *", "next_run": None,
    }
    assert events == ["login", "write"]
