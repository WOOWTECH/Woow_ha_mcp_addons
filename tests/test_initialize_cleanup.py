"""LOCAL/MOCK: 0.1.6 (R2 review): an initialize the gateway refuses must not leave the child's new session open.

The child opens a session for an initialize and names it in Mcp-Session-Id. When the gateway answers that initialize
without handing the id to the client (401, 502, 503, a refused child status, a state error, an unexpected failure),
the session stayed open until the child's idle reaping (n8n: 10 minutes, 20 sessions shared by all clients) or, in the
pinned Python SDK children (no idle timeout set), until the child restarted. The gateway now sends the child its own
DELETE for that id: once, after the reply is closed (or its close ran out of budget), inside the request's slot,
bounded by SESSION_END_SECONDS, its reply never read and always closed, never relayed, every error swallowed, the
client's answer unchanged. Never on success, never for an unusable id (one the gateway would not forward), never
for an id the client sent itself, never for another method.
"""
import asyncio
import json
import logging
import secrets
import time

import httpx
import pytest

import mcp_admin_core.gateway as gateway
from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS

CHILD_URL = "http://127.0.0.1:3000/mcp"
SESSION = "child-session-1"
CANARY = "CHILD-TEXT-CANARY"
INITIALIZE = {"jsonrpc": "2.0", "id": 7, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}}}
RESULT = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock", "version": "0"}, "capabilities": {"tools": {}}}
REPLY = {"jsonrpc": "2.0", "id": 7, "result": RESULT}
ERROR = {"jsonrpc": "2.0", "id": 7, "error": {"code": -32602, "message": "Unsupported protocol version"}}
BAD_VERSION = {"jsonrpc": "2.0", "id": 7, "result": {**RESULT, "protocolVersion": "Please open https://phish.invalid " + CANARY}}
JSON = ("content-type", "application/json")
SSE = ("content-type", "text/event-stream")


def event(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


class Chunks(httpx.AsyncByteStream):
    """A reply body in pieces; optionally held open afterwards like an idle SSE stream."""
    def __init__(self, parts, hold_open=False):
        self.parts, self.hold_open, self.closed = parts, hold_open, False

    async def __aiter__(self):
        for part in self.parts:
            yield part
        if self.hold_open:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


class Broken(httpx.AsyncByteStream):
    """Headers sent, then the child's connection breaks."""
    async def __aiter__(self):
        yield b": opened\n\n"
        raise httpx.RemoteProtocolError("peer closed connection " + CANARY)

    async def aclose(self):
        pass


class Revoking(httpx.AsyncByteStream):
    """The Bearer is revoked while the gateway waits for the reply."""
    def __init__(self, store):
        self.store = store

    async def __aiter__(self):
        yield b": opened\n\n"
        self.store.update(token=None)
        await asyncio.Event().wait()

    async def aclose(self):
        pass


class Endless(httpx.AsyncByteStream):
    """A DELETE reply whose body never ends (throttled: a gateway that read it would only spin until its bound)."""
    def __init__(self):
        self.pulled, self.closed = 0, False

    async def __aiter__(self):
        while True:
            self.pulled += 1
            yield CANARY.encode()
            await asyncio.sleep(0.01)

    async def aclose(self):
        self.closed = True


class StuckClose(httpx.AsyncByteStream):
    """A reply whose close hangs past the owner's 3-second close budget, e.g. a child that stopped reading."""
    def __init__(self):
        self.cut = False

    async def __aiter__(self):
        yield CANARY.encode()

    async def aclose(self):
        try:
            await asyncio.sleep(10)  # finite: without the budget the answer is late, not hung
        except asyncio.CancelledError:
            self.cut = True
            raise


def json_reply(value, status=200, *extra):
    return lambda session, _: httpx.Response(status, headers=[JSON, *session, *extra], content=json.dumps(value).encode())


def raw(status, *headers, content=b""):
    return lambda session, _: httpx.Response(status, headers=[*session, *headers], content=content)


def sse_reply(*parts, hold_open=False):
    return lambda session, _: httpx.Response(200, headers=[SSE, *session], stream=Chunks(list(parts), hold_open))


def sse_stream(make):
    return lambda session, child: httpx.Response(200, headers=[SSE, *session], stream=make(child))


def revoked_first(session, child):
    child.store.update(token=None)
    return json_reply(REPLY)(session, child)


def state_broken_first(session, child):
    child.store.path.write_text("broken")
    return json_reply(REPLY)(session, child)


def failing_filter(*_):
    raise ConfigError("state unavailable")


def failing_answer(*_):
    raise RuntimeError(CANARY)


# Every way an initialize is refused after the child answered: (child reply, client status, gateway patches).
REFUSALS = {
    "Bearer revoked before the status check": (revoked_first, 401, {}),
    "state unreadable before the status check": (state_broken_first, 401, {}),
    "child 101": (raw(101), 502, {}),
    "child 307": (raw(307, ("location", CHILD_URL + "/moved")), 502, {}),
    "child 401": (raw(401, ("www-authenticate", "Bearer"), content=CANARY.encode()), 502, {}),
    "child 403": (raw(403, content=CANARY.encode()), 502, {}),
    "child 404": (raw(404, content=CANARY.encode()), 404, {}),
    "child 429": (raw(429, ("retry-after", "5"), content=CANARY.encode()), 429, {}),
    "child 500": (raw(500, content=CANARY.encode()), 500, {}),
    "202 with a body": (json_reply(REPLY, 202), 502, {}),
    "202 declared empty": (raw(202, ("content-length", "0")), 503, {}),
    "200 untyped and declared empty": (raw(200, ("content-length", "0")), 503, {}),
    "200 text/plain": (raw(200, ("content-type", "text/plain"), content=CANARY.encode()), 502, {}),
    "JSON without a body": (raw(200, JSON), 503, {}),
    "JSON reply to another id": (json_reply({"jsonrpc": "2.0", "id": 8, "result": {}}), 503, {}),
    "SSE ended without the reply": (sse_reply(b": heartbeat\n\n", event({"jsonrpc": "2.0", "method": "notifications/message"})),
                                    503, {}),
    "SSE broken after the headers": (sse_stream(lambda _: Broken()), 503, {}),
    "Bearer revoked while reading": (sse_stream(lambda child: Revoking(child.store)), 401, {}),
    "malformed JSON": (raw(200, JSON, content=b"{not json " + CANARY.encode()), 502, {}),
    "malformed SSE event": (sse_reply(b"data: {not json}\n\n"), 502, {}),
    "SSE event with a lone CR": (sse_reply(b'data: {"jsonrpc":"2.0","id":7,"result":{}}\rdata: x\n\n'), 502, {}),
    "both result and error": (json_reply({**REPLY, "error": {"code": 1, "message": CANARY}}), 502, {}),
    "a batch": (json_reply([REPLY]), 502, {}),
    "oversize reply": (json_reply({**REPLY, "result": {**RESULT, "instructions": "y" * 8000}}), 502,
                       {"MAX_RESPONSE": 4096}),
    "protocolVersion not a date (JSON)": (json_reply(BAD_VERSION), 502, {}),
    "protocolVersion not a date (SSE held open)": (sse_reply(event(BAD_VERSION), hold_open=True), 502, {}),
    "result not an object": (json_reply({"jsonrpc": "2.0", "id": 7, "result": "2025-03-26"}), 502, {}),
    "state error while filtering": (json_reply(REPLY), 503, {"filter_list": failing_filter}),
    "answer could not be built": (json_reply(REPLY), 500, {"json_reply": failing_answer}),
}
# The answers that hand the session id to the client.
ACCEPTED = {
    "JSON result": json_reply(REPLY),
    "SSE result, stream held open": sse_reply(b"id: e-1\nevent: message\n" + event(REPLY), hold_open=True),
    "JSON-RPC error (JSON)": json_reply(ERROR),
    "JSON-RPC error (SSE)": sse_reply(event(ERROR)),
}
# Session ids the gateway would never forward: never reused, not even by the DELETE.
UNUSABLE = {
    "non-ASCII": [(b"mcp-session-id", "中".encode())],
    "257 characters": [("mcp-session-id", "x" * 257)],
    "a space": [("mcp-session-id", "a b")],
    "a DEL character": [("mcp-session-id", "a\x7f")],
    "empty": [("mcp-session-id", "")],
    "two headers": [("mcp-session-id", "a"), ("mcp-session-id", "b")],
}


class Child:
    """A mock child: the initialize POST gets the scenario's reply, a DELETE the given behaviour."""
    def __init__(self, store, scenario, session, delete):
        self.store, self.scenario, self.delete = store, scenario, delete
        self.session = ([] if session is None else [("mcp-session-id", session)] if isinstance(session, str)
                        else session)
        self.requests = []
        self.delete_cancelled = False
        self.delete_reply = None

    async def __call__(self, request):
        self.requests.append(request)
        if request.method != "DELETE":
            return self.scenario(self.session, self)
        if self.delete == "slow":
            try:
                await asyncio.sleep(5)  # finite: without the bound the answer is late, not hung
            except asyncio.CancelledError:
                self.delete_cancelled = True
                raise
        if self.delete == "raise":
            raise RuntimeError(CANARY)
        if self.delete == "connect":
            raise httpx.ConnectError(CANARY, request=request)
        if self.delete == "error":
            return httpx.Response(500, headers={"mcp-session-id": "delete-reply-session", "x-child": CANARY},
                                  json={"error": CANARY})
        if self.delete == "redirect":
            return httpx.Response(307, headers={"location": CHILD_URL + "/moved"})
        if self.delete == "endless":
            self.delete_reply = Endless()
            return httpx.Response(200, headers=[SSE, ("mcp-session-id", "delete-reply-session")], stream=self.delete_reply)
        return httpx.Response(204)


class Spy(httpx.AsyncClient):
    """The gateway's child client, recording every request it starts to build (also one httpx then refuses, e.g. a
    header value that is None or not ASCII), besides those that reach the child."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = []

    def build_request(self, method, url, **kwargs):
        self.attempts.append(method)
        return super().build_request(method, url, **kwargs)


class Outcome:
    def __init__(self, response, child, attempts, elapsed, client_token, child_token):
        self.response, self.child, self.attempts, self.elapsed = response, child, attempts, elapsed
        self.client_token, self.child_token = client_token, child_token

    @property
    def methods(self):
        return [request.method for request in self.child.requests]

    @property
    def answer(self):
        return self.response.status_code, self.response.headers.multi_items(), self.response.content


async def run(tmp_path, scenario, session=SESSION, delete="ok", message=INITIALIZE, client_headers=None, follow=False):
    store = Store(tmp_path / secrets.token_hex(8))
    try:
        state = store.load()
        child = Child(store, scenario, session, delete)
        async with Spy(transport=httpx.MockTransport(child), follow_redirects=follow) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                         base_url="http://mcp") as client:
                headers = {"Authorization": "Bearer " + state.token, **(client_headers or {})}
                started = time.monotonic()
                response = await asyncio.wait_for(client.post("/mcp", headers=headers, json=message), 10)
                elapsed = time.monotonic() - started
        return Outcome(response, child, to_child.attempts, elapsed, state.token, state.child_token)
    finally:
        store.close()


def assert_requests(outcome, *methods):
    """What the gateway started and what reached the child."""
    assert outcome.attempts == list(methods) and outcome.methods == list(methods)


def assert_ended(outcome, session=SESSION):
    """Exactly one DELETE for that session, with the gateway's own headers and none of the client's."""
    assert_requests(outcome, "POST", "DELETE")
    delete = outcome.child.requests[1]
    assert delete.url == CHILD_URL and delete.content == b""
    assert delete.headers.get_list("mcp-session-id") == [session]
    assert delete.headers.get_list("authorization") == ["Bearer " + outcome.child_token]
    assert delete.headers["accept"] == "application/json, text/event-stream"
    assert delete.headers["accept-encoding"] == "identity"
    for name in ("mcp-protocol-version", "last-event-id", "content-type"):
        assert name not in delete.headers
    assert outcome.client_token not in str(delete.headers.raw)


def assert_withheld(outcome, *texts):
    """Neither the session id nor child text reaches the client."""
    shown = str(outcome.response.headers.raw) + outcome.response.text
    for text in (SESSION, CANARY, *texts):
        assert text not in shown


def patch(monkeypatch, patches):
    for name, value in patches.items():
        monkeypatch.setattr(gateway, name, value)


CLIENT_HEADERS = {"mcp-protocol-version": "2025-03-26", "last-event-id": "e-1"}


@pytest.mark.parametrize("name", REFUSALS)
async def test_every_refusal_ends_the_new_session_and_keeps_the_answer(tmp_path, monkeypatch, name):
    scenario, status, patches = REFUSALS[name]
    patch(monkeypatch, patches)
    baseline = await run(tmp_path, scenario, session=None, client_headers=CLIENT_HEADERS)
    assert baseline.response.status_code == status
    assert_requests(baseline, "POST")
    outcome = await run(tmp_path, scenario, client_headers=CLIENT_HEADERS)
    assert outcome.answer == baseline.answer
    assert_withheld(outcome)
    assert_ended(outcome)


@pytest.mark.parametrize("mode", ["raise", "connect", "error", "redirect", "slow", "endless"])
@pytest.mark.parametrize("name", REFUSALS)
async def test_a_failing_or_slow_delete_never_changes_the_answer(tmp_path, monkeypatch, name, mode):
    scenario, _, patches = REFUSALS[name]
    patch(monkeypatch, {**patches, "SESSION_END_SECONDS": 0.2})
    baseline = await run(tmp_path, scenario, session=None)
    # A child client that would follow redirects: the gateway's DELETE still never does.
    outcome = await run(tmp_path, scenario, delete=mode, follow=mode == "redirect")
    assert outcome.answer == baseline.answer
    assert_withheld(outcome, "delete-reply-session")
    assert_requests(outcome, "POST", "DELETE")  # one attempt: no retry, no redirect followed
    if mode == "slow":
        assert outcome.child.delete_cancelled  # cut at the bound, not awaited
        assert outcome.elapsed < baseline.elapsed + 0.2 + 1.5
    if mode == "endless":
        # The reply is never read (a child's body may be large or never end: reading it costs memory and holds the
        # answer until the bound) and always closed (a reply left open keeps its pooled connection: with the real
        # pool, 40 such refusals would take every connection and every later request would fail).
        assert outcome.child.delete_reply.pulled == 0 and outcome.child.delete_reply.closed


def test_the_documented_bound():
    assert gateway.SESSION_END_SECONDS == 2


@pytest.mark.parametrize("name", ACCEPTED)
async def test_a_session_handed_to_the_client_is_never_ended(tmp_path, name):
    outcome = await run(tmp_path, ACCEPTED[name])
    assert outcome.response.status_code == 200 and outcome.response.headers["mcp-session-id"] == SESSION
    assert_requests(outcome, "POST")


@pytest.mark.parametrize("name", ["child 500", "SSE ended without the reply", "protocolVersion not a date (JSON)",
                                  "Bearer revoked before the status check"])
@pytest.mark.parametrize("client", [None, {"mcp-session-id": "client-session"}])
async def test_no_delete_without_a_session_id(tmp_path, name, client):
    outcome = await run(tmp_path, REFUSALS[name][0], session=None, client_headers=client)
    assert outcome.response.status_code == REFUSALS[name][1]
    assert_requests(outcome, "POST")


@pytest.mark.parametrize("session", UNUSABLE)
@pytest.mark.parametrize("name,status", [("child 500", 500), ("SSE ended without the reply", 503),
                                         ("protocolVersion not a date (JSON)", 502),
                                         ("Bearer revoked before the status check", 401), ("accepted", 502)])
async def test_no_delete_for_an_unusable_session_id(tmp_path, name, status, session):
    scenario = json_reply(REPLY) if name == "accepted" else REFUSALS[name][0]
    outcome = await run(tmp_path, scenario, session=UNUSABLE[session])
    assert outcome.response.status_code == status and "mcp-session-id" not in outcome.response.headers
    assert_requests(outcome, "POST")


@pytest.mark.parametrize("session", ["!", "~", "x" * 256, "".join(map(chr, range(0x21, 0x7f)))])
async def test_boundary_session_ids_are_ended_verbatim(tmp_path, session):
    outcome = await run(tmp_path, REFUSALS["protocolVersion not a date (JSON)"][0], session=session)
    assert outcome.response.status_code == 502
    assert_ended(outcome, session)


async def test_a_session_id_the_client_sent_is_never_ended(tmp_path):
    # A child may echo it (a Python SDK child re-initializes the client's live session; n8n-mcp reuses the id): the
    # session is the client's, which may still use it.
    client = {"mcp-session-id": "client-session"}
    for name in ("child 500", "protocolVersion not a date (JSON)", "Bearer revoked before the status check"):
        outcome = await run(tmp_path, REFUSALS[name][0], session="client-session", client_headers=client)
        assert outcome.response.status_code == REFUSALS[name][1]
        assert_requests(outcome, "POST")
    # A new id from the child is still the gateway's to end, and only that one.
    scenario = REFUSALS["protocolVersion not a date (JSON)"][0]
    outcome = await run(tmp_path, scenario, session=SESSION, client_headers=client)
    assert outcome.response.status_code == 502
    assert_ended(outcome)
    assert outcome.child.requests[0].headers["mcp-session-id"] == "client-session"


@pytest.mark.parametrize("method", ["ping", "tools/list"])
@pytest.mark.parametrize("client", [None, {"mcp-session-id": "client-session"}])
async def test_other_requests_never_end_a_session(tmp_path, method, client):
    message = {"jsonrpc": "2.0", "id": 7, "method": method, "params": {}}
    for scenario, status in ((raw(200, JSON, content=b"{not json"), 502), (raw(500), 500), (raw(307), 502),
                             (json_reply({"jsonrpc": "2.0", "id": 7, "result": {}}), 200)):
        outcome = await run(tmp_path, scenario, session=SESSION, message=message, client_headers=client)
        if client is None:  # 0.1.8 (GATEWAY-2): without a session id the gateway answers 400 itself
            assert outcome.response.status_code == 400 and "mcp-session-id" not in outcome.response.headers
            assert_requests(outcome)
            continue
        assert outcome.response.status_code == status
        assert_requests(outcome, "POST")


@pytest.mark.parametrize("verb", ["GET", "DELETE"])
async def test_get_and_client_delete_reach_the_child_once(tmp_path, verb):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(500, headers={"mcp-session-id": SESSION}, content=b"x")
    store = Store(tmp_path / "state")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                response = await client.request(verb, "/mcp", headers={"Authorization": "Bearer " + store.load().token,
                                                                       "mcp-session-id": "client-session"})
    finally:
        store.close()
    assert response.status_code == 500 and [r.method for r in seen] == [verb]
    assert seen[0].headers["mcp-session-id"] == "client-session"


async def test_no_delete_when_the_child_never_answered(tmp_path):
    def unreachable(_, __):
        raise httpx.ConnectError("refused")
    outcome = await run(tmp_path, unreachable)
    assert outcome.response.status_code == 502
    assert_requests(outcome, "POST")


async def test_the_reply_is_closed_before_the_session_ends(tmp_path):
    stream = Chunks([event(BAD_VERSION)], hold_open=True)
    closed_at_delete = []

    class Recording(Child):
        async def __call__(self, request):
            if request.method == "DELETE":
                closed_at_delete.append(stream.closed)
            return await super().__call__(request)
    store = Store(tmp_path / "state")
    try:
        child = Recording(store, sse_stream(lambda _: stream), SESSION, "ok")
        async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                headers = {"Authorization": "Bearer " + store.load().token}
                response = await asyncio.wait_for(client.post("/mcp", headers=headers, json=INITIALIZE), 10)
    finally:
        store.close()
    assert response.status_code == 502 and closed_at_delete == [True]


async def test_the_session_ends_even_when_closing_the_reply_runs_out_of_its_budget(tmp_path):
    # The DELETE follows the owner's 3-second close budget instead of sharing it: a reply whose close hangs still has
    # its session ended, once the budget cut the close (this test takes about 3 seconds).
    stream = StuckClose()
    outcome = await run(tmp_path, lambda session, _: httpx.Response(500, headers=session, stream=stream))
    assert outcome.response.status_code == 500
    assert stream.cut  # the close ran out of its budget
    assert_withheld(outcome)
    assert_ended(outcome)
    assert outcome.elapsed < 3 + 1.5


async def test_the_delete_runs_inside_the_requests_slot(tmp_path, monkeypatch):
    # With all 32 slots held by refused initializes whose DELETE is pending, a 33rd request waits for a slot (503);
    # the DELETEs therefore never outnumber the slots.
    monkeypatch.setattr(gateway, "SESSION_END_SECONDS", 30)  # released by the test, never by the bound
    entered, release = asyncio.Event(), asyncio.Event()
    opened, ended = [], []

    async def handler(request):
        if request.method == "DELETE":
            ended.append(request.headers["mcp-session-id"])
            if len(ended) == 32:
                entered.set()
            await release.wait()
            return httpx.Response(204)
        if json.loads(request.content)["method"] == "ping":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {}})
        opened.append("session-%d" % len(opened))
        return httpx.Response(500, headers={"mcp-session-id": opened[-1]}, content=b"x")
    store = Store(tmp_path / "state")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                headers = {"Authorization": "Bearer " + store.load().token}
                ping = {"jsonrpc": "2.0", "id": 9, "method": "ping"}
                session = {**headers, "Mcp-Session-Id": "client-session"}  # 0.1.8: only initialize comes without one
                pending = [asyncio.create_task(client.post("/mcp", headers=headers, json=INITIALIZE)) for _ in range(32)]
                await asyncio.wait_for(entered.wait(), 10)
                assert (await client.post("/mcp", headers=session, json=ping)).status_code == 503
                assert not any(task.done() for task in pending)  # each answer waits for its own DELETE (bounded)
                release.set()
                answers = await asyncio.wait_for(asyncio.gather(*pending), 10)
                assert (await client.post("/mcp", headers=session, json=ping)).status_code == 200
    finally:
        store.close()
    assert [answer.status_code for answer in answers] == [500] * 32
    assert sorted(ended) == sorted(opened) and len(set(ended)) == 32


async def test_the_slot_is_released_whatever_ends_the_delete(tmp_path):
    # end_session swallows every Exception and runs shielded, so only a BaseException could leave it (httpx never
    # raises CancelledError by itself; it stands for one here). The slot is still released: one more such initialize
    # than there are slots, then a ping still gets a slot.
    def handler(request):
        if request.method == "DELETE":
            raise asyncio.CancelledError()
        if json.loads(request.content)["method"] == "ping":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {}})
        return httpx.Response(500, headers={"mcp-session-id": SESSION}, content=b"x")
    store = Store(tmp_path / "state")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                headers = {"Authorization": "Bearer " + store.load().token}
                for _ in range(33):
                    request = asyncio.create_task(client.post("/mcp", headers=headers, json=INITIALIZE))
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(request, 5)
                ping = await client.post("/mcp", headers={**headers, "Mcp-Session-Id": "client-session"},
                                         json={"jsonrpc": "2.0", "id": 9, "method": "ping"})
    finally:
        store.close()
    assert ping.status_code == 200


async def test_a_cancelled_request_still_ends_the_session(tmp_path, monkeypatch):
    # The DELETE is part of the owner's shielded, joined cleanup: cancelling the request neither skips nor detaches it.
    monkeypatch.setattr(gateway, "SESSION_END_SECONDS", 30)
    entered, release = asyncio.Event(), asyncio.Event()
    ended = []

    async def handler(request):
        if request.method == "DELETE":
            entered.set()
            await release.wait()
            ended.append(request.headers["mcp-session-id"])
            return httpx.Response(204)
        return httpx.Response(500, headers={"mcp-session-id": SESSION}, content=b"x")
    store = Store(tmp_path / "state")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as to_child:
            _, app = make_apps(store, TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                task = asyncio.create_task(client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                                       json=INITIALIZE))
                await asyncio.wait_for(entered.wait(), 5)
                task.cancel()
                await asyncio.sleep(0.05)
                assert not task.done()
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
    finally:
        store.close()
    assert ended == [SESSION]


async def test_the_session_id_and_child_text_are_never_logged(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    for mode in ("ok", "error", "raise", "connect"):
        outcome = await run(tmp_path, REFUSALS["protocolVersion not a date (JSON)"][0], delete=mode)
        assert_requests(outcome, "POST", "DELETE")
    captured = capsys.readouterr()
    for text in (caplog.text, captured.out, captured.err):
        assert SESSION not in text and CANARY not in text
