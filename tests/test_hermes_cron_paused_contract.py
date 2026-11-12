"""Hermes cron create keeps the backend's paused and legacy enabled flags consistent."""

import json

import pytest

from test_hermes_safe_public_errors import _direct_call
from test_six_hardening import Quiet, runtime, serve


CREATE = {"action": "create", "name": "synthetic-cron", "schedule": "0 9 * * *", "prompt": "hello"}


@pytest.mark.parametrize("enabled_arg,expected_enabled", [
    (False, False), (True, True), (None, True),
], ids=["disabled", "enabled", "default-enabled"])
async def test_cron_create_sends_consistent_pause_flags_through_ha_child(
    tmp_path, enabled_arg, expected_enabled
):
    events = []
    posted = []

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
            posted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.reply({"id": "synthetic-job", "name": "synthetic-cron"})

    arguments = CREATE.copy()
    if enabled_arg is not None:
        arguments["enabled"] = enabled_arg
    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", arguments, 101)

    assert reply["isError"] is False
    assert json.loads(reply["content"][0]["text"])["id"] == "synthetic-job"
    assert events == ["login", "create"]
    assert posted == [{
        "name": "synthetic-cron", "schedule": "0 9 * * *", "prompt": "hello",
        "paused": not expected_enabled, "enabled": expected_enabled,
    }]


async def test_cron_create_strict_legacy_rejection_does_not_retry_without_paused(tmp_path):
    events = []
    posted = []

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
            posted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.reply({"detail": "extra_forbidden"}, 422)

    with serve(Dashboard) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=("hermes_cron:create",)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, "hermes_cron", {
                **CREATE, "enabled": False,
            }, 102)

    assert reply["isError"] is True
    assert "status=422" in reply["content"][0]["text"]
    assert events == ["login", "create"]
    assert posted == [{
        "name": "synthetic-cron", "schedule": "0 9 * * *", "prompt": "hello",
        "paused": True, "enabled": False,
    }]
