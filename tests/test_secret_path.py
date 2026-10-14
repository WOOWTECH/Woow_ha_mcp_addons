"""LOCAL/MOCK: 0.1.12 /private_<token>/mcp, the secret-path connection for Claude.ai custom connectors.

Claude.ai custom connectors cannot send an Authorization header. The same add-on token (rotate/revoke apply at
once) may instead be the path segment. A wrong, empty, revoked or rotated-away secret is the same 404 as an unknown
path; the request's own Authorization header is ignored there; Origin is allowed there and never forwarded. /mcp with
a Bearer header is unchanged (401 + WWW-Authenticate, Origin 403). Log records never show the secret.
"""
import asyncio
import io
import json
import logging
from pathlib import Path
import re

import httpx
import pytest
import uvicorn

from mcp_admin_core import redact
from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps, secret_valid
from n8n_adapter import TOOLS

ROOT = Path(__file__).resolve().parents[1]
INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude-ai-mock", "version": "0"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
PING = {"jsonrpc": "2.0", "id": 3, "method": "ping"}
RESULT = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "mock", "version": "0"}, "capabilities": {"tools": {}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


class Child:
    """Records exactly what reaches the child; answers like a stateful MCP server."""
    def __init__(self, on_request=None):
        self.seen = []
        self.on_request = on_request

    def __call__(self, request):
        self.seen.append(request)
        if self.on_request:
            self.on_request(request)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        if "id" not in body:
            return httpx.Response(202)
        if body["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "child-session"},
                                  json={"jsonrpc": "2.0", "id": body["id"], "result": RESULT})
        result = {"tools": [{"name": name, "inputSchema": {"type": "object"}} for name in TOOLS]} \
            if body["method"] == "tools/list" else {}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


async def call(store, child, verb, path, message=None, headers=None):
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            kwargs = {"headers": {**ACCEPT, **(headers or {})}}
            if message is not None:
                kwargs["json"] = message
            return await asyncio.wait_for(client.request(verb, path, **kwargs), 10)


def private(store):
    return "/private_" + store.load().token + "/mcp"


def bearer(store):
    return {"Authorization": "Bearer " + store.load().token}


async def not_found(store):
    """What an unknown path answers: the secret path must be indistinguishable from it."""
    response = await call(store, Child(), "POST", "/no-such-path/mcp", PING)
    assert response.status_code == 404
    return response


def same_as_unknown(response, reference):
    assert response.status_code == 404
    assert response.content == reference.content
    assert dict(response.headers) == dict(reference.headers)
    assert "www-authenticate" not in response.headers


async def test_initialize_list_and_delete_over_the_secret_path(store):
    child = Child()
    path = private(store)
    # A browser-like client: Origin present, and a wrong Authorization header that must be ignored, not used.
    noise = {"Origin": "https://claude.ai", "Authorization": "Bearer not-the-token"}
    answer = await call(store, child, "POST", path, INITIALIZE, noise)
    assert answer.status_code == 200, answer.content
    assert answer.headers["mcp-session-id"] == "child-session"
    assert answer.json()["result"]["serverInfo"]["name"] == "woow-mcp"
    session = {"Mcp-Session-Id": "child-session", **noise}
    assert (await call(store, child, "POST", path, INITIALIZED, session)).status_code == 202
    listed = await call(store, child, "POST", path, LIST, session)
    assert listed.status_code == 200
    assert {tool["name"] for tool in listed.json()["result"]["tools"]} <= set(TOOLS)
    assert (await call(store, child, "DELETE", path, None, session)).status_code == 200
    assert [r.method for r in child.seen] == ["POST", "POST", "POST", "DELETE"]
    for request in child.seen:
        # The child only ever gets the gateway's own credential and none of the client's Origin/Authorization.
        assert request.headers["authorization"] == "Bearer " + store.load().child_token
        assert "origin" not in request.headers
        assert store.load().token not in str(request.url)
        assert request.url.path == "/mcp"


@pytest.mark.parametrize("secret", ["wrong", "x" * 43, "A", "%41", "..", "private_", "a" * 4096])
async def test_wrong_secret_is_the_unknown_path_404(store, secret):
    reference = await not_found(store)
    child = Child()
    for verb, message in (("POST", INITIALIZE), ("GET", None), ("DELETE", None), ("PUT", None), ("OPTIONS", None)):
        # Before 405: a wrong secret never learns the method rule; a valid Bearer header does not help.
        same_as_unknown(await call(store, child, verb, f"/private_{secret}/mcp", message, bearer(store)), reference)
    assert child.seen == []


async def test_empty_and_near_miss_secrets_are_404(store):
    reference = await not_found(store)
    token = store.load().token
    child = Child()
    for path in ("/private_/mcp", f"/private_{token[:-1]}/mcp", f"/private_{token}x/mcp", f"/private_{token.upper()}/mcp",
                 f"/private_{token}/mcp/", f"/private_{token}", f"/private_{token}/sse", f"/Private_{token}/mcp"):
        response = await call(store, child, "POST", path, INITIALIZE)
        same_as_unknown(response, reference)
    assert child.seen == []


async def test_revoked_token_closes_the_secret_path(store):
    path = private(store)
    reference = await not_found(store)
    store.update(token=None)
    child = Child()
    same_as_unknown(await call(store, child, "POST", path, INITIALIZE), reference)
    # Bearer contract unchanged: 401 with WWW-Authenticate.
    response = await call(store, child, "POST", "/mcp", INITIALIZE, {"Authorization": "Bearer x"})
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
    assert child.seen == []


async def test_rotation_moves_the_secret_path(store):
    old = private(store)
    reference = await not_found(store)
    store.update(token="R" * 43)
    child = Child()
    same_as_unknown(await call(store, child, "POST", old, INITIALIZE), reference)
    assert child.seen == []
    assert (await call(store, child, "POST", private(store), INITIALIZE)).status_code == 200


async def test_revocation_after_the_first_check_is_also_404(store):
    """The revalidations after the child's answer use the same rule as the first check: 404, not 401."""
    path = private(store)
    reference = await not_found(store)
    child = Child(on_request=lambda _: store.update(token=None))
    same_as_unknown(await call(store, child, "POST", path, INITIALIZE), reference)
    # It reached the child, the answer was withheld, and the session the child opened for it was ended (0.1.6 R2).
    assert [r.method for r in child.seen] == ["POST", "DELETE"]
    store.update(token="B" * 43)
    child = Child(on_request=lambda _: store.update(token="C" * 43))
    response = await call(store, child, "POST", "/mcp", INITIALIZE, {"Authorization": "Bearer " + "B" * 43})
    assert response.status_code == 401


async def test_origin_allowed_only_on_the_secret_path(store):
    child = Child()
    origin = {"Origin": "https://claude.ai"}
    assert (await call(store, child, "POST", private(store), INITIALIZE, origin)).status_code == 200
    assert (await call(store, child, "POST", "/mcp", INITIALIZE, {**bearer(store), **origin})).status_code == 403
    assert len(child.seen) == 1


async def test_authorization_header_cannot_stand_in_for_the_secret(store):
    """A valid Bearer header does not open a wrong secret path, and a wrong one does not close a right one."""
    child = Child()
    reference = await not_found(store)
    same_as_unknown(await call(store, child, "POST", "/private_wrong/mcp", INITIALIZE, bearer(store)), reference)
    for value in ("Bearer wrong", "Basic eDp5", "", "Bearer " + store.load().token + " "):
        assert (await call(store, child, "POST", private(store), INITIALIZE, {"Authorization": value})).status_code == 200
    # Two Authorization headers make /mcp 401; the secret path does not read them at all.
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = make_apps(store, TOOLS, to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            doubled = httpx.Headers([("authorization", "Bearer a"), ("authorization", "Bearer b"), *ACCEPT.items()])
            assert (await client.post(private(store), headers=doubled, json=INITIALIZE)).status_code == 200


async def test_secret_path_keeps_the_query_method_and_session_rules(store):
    child = Child()
    path = private(store)
    assert (await call(store, child, "POST", path + "?token=x", INITIALIZE)).status_code == 400
    put = await call(store, child, "PUT", path)
    assert put.status_code == 405 and put.headers["allow"] == "GET, POST, DELETE"
    # Anything but initialize without a session: 400, never forwarded (0.1.8 GATEWAY-2), as on /mcp.
    assert (await call(store, child, "POST", path, PING)).status_code == 400
    assert (await call(store, child, "DELETE", path)).status_code == 400
    # Policy still applies: an unsupported tool is 403 before the child.
    denied = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}}
    assert (await call(store, child, "POST", path, denied, {"Mcp-Session-Id": "child-session"})).status_code == 403
    assert child.seen == []


def test_secret_comparison_is_digest_based():
    class S:
        token = "T" * 43
    assert secret_valid("T" * 43, S())
    for guess in ("", "T" * 42, "T" * 44, "t" * 43, "T" * 42 + "\udc80", "é" * 43):
        assert not secret_valid(guess, S())
    S.token = None
    assert not secret_valid("", S()) and not secret_valid("None", S())
    source = (ROOT / "packages/mcp-admin-core/mcp_admin_core/gateway.py").read_text()
    body = source[source.index("def secret_valid"):source.index("async def error_handler")]
    assert "hmac.compare_digest" in body and "hashlib.sha256" in body and "==" not in body and "!=" not in body


# ---- log redaction ----

def test_scrub_redacts_message_args_exception_and_keeps_access_format():
    secret = "S" * 43
    path = f"/private_{secret}/mcp"
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:1", "POST", path + "?x=1", "1.1", 404), None)
    redact.scrub(record)
    assert record.args[2] == "/private_[REDACTED]/mcp?x=1" and record.args[4] == 404
    try:
        raise RuntimeError("failed on " + path)
    except RuntimeError:
        import sys
        failing = logging.LogRecord("x", logging.ERROR, __file__, 1, "Exception in %s", (path.encode(),), sys.exc_info())
    redact.scrub(failing)
    text = logging.Formatter("%(message)s").format(failing)
    assert secret not in text and "/private_[REDACTED]/mcp" in text
    obj = logging.LogRecord("x", logging.WARNING, __file__, 1, RuntimeError(path), None, None)
    redact.scrub(obj)
    assert secret not in obj.getMessage()
    for raw, expected in ((f"GET {path} 200", "GET /private_[REDACTED]/mcp 200"),
                          (f"'{path}'", "'/private_[REDACTED]/mcp'"), ("/private_/mcp", "/private_[REDACTED]/mcp"),
                          ("/mcp and /health/ready", "/mcp and /health/ready")):
        assert redact.redact(raw) == expected


def test_launchers_keep_access_log_off_and_install_redaction():
    for launcher in ("packages/mcp-admin-core/mcp_admin_core/run_product.py", "apps/n8n/run.py"):
        source = (ROOT / launcher).read_text()
        assert source.count("uvicorn.Config(") == 1 and "access_log=False" in source, launcher
        assert "redact.install()" in source and "redact.guard_handlers(*redact.UVICORN_LOGGERS)" in source, launcher
        assert source.index("redact.install()") < source.index("server.serve()"), launcher


async def test_real_uvicorn_logs_never_show_the_secret(store):
    """A real listener with access logging deliberately ON (production keeps it off) and an application error whose
    message contains the request path: every captured line shows /private_[REDACTED]/ and never the token."""
    token = store.load().token
    buffers = []

    async with httpx.AsyncClient(transport=httpx.MockTransport(Child())) as to_child:
        _, app = make_apps(store, TOOLS, to_child)

        async def exploding(scope, receive, send):
            if scope["type"] == "http" and scope["path"].endswith("/boom"):
                raise RuntimeError("application failed on " + scope["path"])
            await app(scope, receive, send)

        config = uvicorn.Config(exploding, host="127.0.0.1", port=0, access_log=True, log_level="debug",
                                lifespan="off", proxy_headers=False, server_header=False)
        redact.install()
        redact.guard_handlers(*redact.UVICORN_LOGGERS)
        for name in redact.UVICORN_LOGGERS:
            for handler in logging.getLogger(name).handlers:
                buffer = io.StringIO()
                handler.setStream(buffer)
                buffers.append(buffer)
        root_buffer = io.StringIO()
        root_handler = logging.StreamHandler(root_buffer)
        logging.getLogger().addHandler(root_handler)
        buffers.append(root_buffer)
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(.02)
            port = server.servers[0].sockets[0].getsockname()[1]
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                assert (await client.post(f"/private_{token}/mcp", headers=ACCEPT, json=INITIALIZE)).status_code == 200
                assert (await client.post(f"/private_{token}/mcp?leak=1", headers=ACCEPT, json=INITIALIZE)).status_code == 400
                assert (await client.post(f"/private_{token[:-1]}/mcp", headers=ACCEPT, json=INITIALIZE)).status_code == 404
                assert (await client.get(f"/private_{token}/boom")).status_code == 500
                logging.getLogger("mcp_admin_core.test").warning("library echo %s", f"/private_{token}/mcp")
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
            logging.getLogger().removeHandler(root_handler)
    text = "".join(buffer.getvalue() for buffer in buffers)
    assert token not in text and token[:-1] not in text
    assert text.count("/private_[REDACTED]/") >= 5, text  # four access lines, the traceback and the library echo
    assert "application failed on /private_[REDACTED]/boom" in text
    assert re.search(r'"POST /private_\[REDACTED\]/mcp HTTP/1\.1" 200', text), text
