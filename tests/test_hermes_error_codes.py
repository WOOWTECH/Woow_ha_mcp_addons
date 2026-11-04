"""Every MCP-visible Hermes error reads ``CODE: text`` through the real HA MCP child (same table as PaaS)."""

import json

import pytest
from test_hermes_safe_public_errors import _direct_call, _tool_text
from test_six_hardening import Quiet, runtime, serve

SENTINEL = "SYNTHETIC_UPSTREAM_SENTINEL_9137"
GATEWAY_REJECTED = (
    "BACKEND_AUTH_REJECTED status=403: Hermes Gateway 憑證被拒 (credentials rejected); "
    "update Connection > Gateway API Server in the MCP admin page and press Save & Restart."
)
LOOPBACK = "INVALID_INPUT: loopback MCP servers (localhost, 127.0.0.0/8, ::1) cannot be added"


def _handler(routes):
    """One server for Dashboard and Gateway: routes maps (METHOD, path) to (status, body or bytes)."""

    class Backend(Quiet):
        def _route(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            path = self.path.split("?", 1)[0]
            if method == "POST" and path.endswith("/auth/password-login"):
                self.send_response(200)
                self.send_header("Set-Cookie", "hermes_session_at=synthetic-cookie")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            status, body = routes.get((method, path), routes.get((method, "*"), (500, {"detail": "unrouted"})))
            if isinstance(body, str):
                body = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.reply(body, status)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_DELETE(self):
            self._route("DELETE")

        def do_PUT(self):
            self._route("PUT")

    return Backend


async def _text(tmp_path, tool, args, routes, grants=()):
    with serve(_handler(routes)) as base:
        async with runtime(tmp_path, "hermes", base, write_grants=tuple(grants)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, tool, args, 90)
    if tool == "hermes_inspect":  # sections report their own *_error fields
        assert reply["isError"] is True
        return reply, reply["content"][0]["text"], base
    return reply, _tool_text(reply, tool), base


@pytest.mark.parametrize("tool,args,path,method,grant", [
    ("hermes_cron", {"action": "delete", "job_id": "job-x"}, "/api/cron/jobs/job-x", "DELETE", "hermes_cron:delete"),
    ("hermes_session", {"action": "get", "session_id": "gone"}, "/api/sessions/gone", "GET", None),
    ("hermes_webhook", {"action": "delete", "name": "gone"}, "/api/webhooks/gone", "DELETE", "hermes_webhook:delete"),
    ("hermes_mcp", {"action": "remove", "name": "gone"}, "/api/mcp/servers/gone", "DELETE", "hermes_mcp:remove"),
])
async def test_missing_resource_is_not_found(tmp_path, tool, args, path, method, grant):
    routes = {(method, path): (404, {"detail": "No such thing"})}
    _, text, _ = await _text(tmp_path, tool, args, routes, [grant] if grant else [])
    assert text.startswith("NOT_FOUND: Hermes ") and "not found (不存在)" in text


@pytest.mark.parametrize("tool,args,grant", [
    ("hermes_mcp", {"action": "add", "name": "qa", "url": "stdio:cmd"}, "hermes_mcp:add"),
    ("hermes_mcp", {"action": "remove", "name": "../x"}, "hermes_mcp:remove"),
    ("hermes_session", {"action": "get", "session_id": "../config/raw"}, None),
    ("hermes_session", {"action": "get", "session_id": "ok", "request_id": "r1"}, None),
    ("hermes_session", {"action": "delete", "session_id": "ok", "request_id": "r1"}, "hermes_session:delete"),
])
async def test_input_guards_are_invalid_input(tmp_path, tool, args, grant):
    _, text, _ = await _text(tmp_path, tool, args, {}, [grant] if grant else [])
    assert text.startswith("INVALID_INPUT: "), text


@pytest.mark.parametrize("url", ["http://localhost:9/mcp", "http://127.0.0.1:9/mcp", "http://[::1]:9/mcp"])
async def test_loopback_mcp_url_has_one_wording(tmp_path, url):
    _, text, _ = await _text(tmp_path, "hermes_mcp", {"action": "add", "name": "qa", "url": url}, {},
                             ["hermes_mcp:add"])
    assert text == LOOPBACK


async def test_expensive_model_needs_confirmation(tmp_path):
    routes = {("GET", "/api/model/info"): (200, {"provider": "p"}),
              ("POST", "/api/model/set"): (200, {"confirm_required": True, "confirm_message": "Costly."})}
    _, text, _ = await _text(tmp_path, "hermes_model", {"action": "set", "model": "m", "provider": "p"}, routes,
                             ["hermes_model:set"])
    assert text.startswith("CONFIRMATION_REQUIRED: Hermes did not switch the model: Costly.")


async def test_config_write_not_applied(tmp_path):
    routes = {("GET", "/api/config"): (200, {"display": {"x": 1}}), ("PUT", "*"): (200, {"ok": True}),
              ("POST", "*"): (200, {"ok": True})}
    _, text, _ = await _text(tmp_path, "hermes_config", {"action": "set", "key": "display.x", "value": "2"},
                             routes, ["hermes_config:set"])
    assert text.startswith("CONFIG_NOT_APPLIED: Hermes accepted the write but 'display.x'"), text


@pytest.mark.parametrize("sse,expected", [
    ("event: response.created\ndata: {}\n\n", "BACKEND_UNEXPECTED_RESPONSE: Hermes Gateway ended the reply"),
    ('event: response.failed\ndata: {"response": {"status": "failed", "error": {"message": "boom"}}}\n\n',
     "CHAT_TURN_FAILED: Hermes could not complete the turn: boom"),
])
async def test_chat_gateway_internal_errors(tmp_path, sse, expected):
    routes = {("POST", "/v1/responses"): (200, sse)}
    _, text, _ = await _text(tmp_path, "hermes_chat", {"message": "hi"}, routes, ["hermes_chat"])
    assert text.startswith(expected), text


@pytest.mark.parametrize("tool,args", [
    ("hermes_chat", {"message": "hi"}),
    ("hermes_inspect", {"target": "capabilities"}),
])
async def test_gateway_403_is_fixed_safe_wording(tmp_path, tool, args):
    routes = {("POST", "/v1/responses"): (403, {"detail": SENTINEL}),
              ("GET", "*"): (403, {"detail": SENTINEL})}
    reply, text, base = await _text(tmp_path, tool, args, routes, ["hermes_chat"])
    if tool == "hermes_inspect":
        text = json.loads(text)["capabilities_error"]
    assert text == GATEWAY_REJECTED
    raw = json.dumps(reply, ensure_ascii=False)
    assert SENTINEL not in raw and base not in raw


@pytest.mark.parametrize("body,tool,args,path", [
    ([], "hermes_config", {"action": "get"}, "/api/config"),
    ([], "hermes_model", {"action": "info"}, "/api/model/info"),
    ([], "hermes_session", {"action": "list"}, "/api/sessions"),
    ({"x": 1}, "hermes_skill", {"action": "list"}, "/api/skills"),
    ([{"name": 7}], "hermes_skill", {"action": "list"}, "/api/skills"),
])
async def test_wrong_dashboard_shapes_are_unexpected_response(tmp_path, body, tool, args, path):
    _, text, _ = await _text(tmp_path, tool, args, {("GET", path): (200, body)})
    assert text.startswith("BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned a"), text


async def test_inspect_model_wrong_shape_is_reported_in_section(tmp_path):
    with serve(_handler({("GET", "/api/model/info"): (200, [])})) as base:
        async with runtime(tmp_path, "hermes", base) as (_client, _headers, _store, manager, child):
            reply = await _direct_call(child, manager.endpoint, "hermes_inspect", {"target": "model"}, 91)
    assert reply["isError"] is True
    section = json.loads(reply["content"][0]["text"])["model_info_error"]
    assert section.startswith("BACKEND_UNEXPECTED_RESPONSE: Hermes Dashboard returned a non-object")
