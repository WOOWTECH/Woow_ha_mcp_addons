"""Independent Ingress-only admin and Bearer-only Streamable HTTP applications.

Management fails closed without an explicit role provider (installed only by n8n).
No legacy SSE /sse or /messages endpoints are exposed.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
from typing import Awaitable, Callable

import anyio
import httpx
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.middleware import Middleware

from . import ui

from .config import ConfigError, State, Store, strict_json
from .policy import Denied, authorize, filter_list
from .ha_role import valid_user_id

MAX_REQUEST = 262144
MAX_RESPONSE = 8 * 1024 * 1024
STREAM_SECONDS = 120
EVENT_BOUNDARY = re.compile(rb"\r?\n\r?\n")
LONE_CR = re.compile(rb"\r(?!\n)")
SSE_FIELD = re.compile(rb"(?:id|event|retry):[ ]?[\x20-\x7e]{0,256}")
SSE_COMMENT = re.compile(rb":[\x20-\x7e]{0,1024}")


def sse_frame(frame: bytes):
    """Split one SSE event (boundary removed) into (kept field lines, data lines), or None if unsafe.

    Only printable-ASCII id/event/retry fields and comments are kept besides data lines; anything else
    (a BOM, unknown fields, blank lines, non-ASCII) is dropped, so no client can read it as data that the
    gateway did not see. A lone CR ends a line for some SSE parsers but not for this scan: refused.
    """
    if LONE_CR.search(frame):
        return None
    kept, data = [], []
    for line in frame.split(b"\n"):
        line = line[:-1] if line.endswith(b"\r") else line
        if line.startswith(b"data:"):
            data.append(line)
        elif SSE_FIELD.fullmatch(line) or SSE_COMMENT.fullmatch(line):
            kept.append(line)
    return kept, data


def sse_data(data_lines):
    return b"\n".join(line[5:].lstrip(b" ") for line in data_lines)
RoleVerifier = Callable[[str], Awaitable[bool]]


class UpstreamOwner:
    """Own the reader, response and slot across ASGI cancellation and handoff."""
    def __init__(self, slots):
        self.slots = slots
        self.response = None
        self.reader = None
        self.closed = False
        self.overflowed = False  # chunks() stopped at MAX_RESPONSE, not at the end of the reply

    async def close(self):
        if self.closed:
            return
        self.closed = True

        async def cleanup():
            try:
                async with asyncio.timeout(3):
                    if self.reader is not None:
                        if not self.reader.done():
                            self.reader.cancel()
                        await asyncio.gather(self.reader, return_exceptions=True)
                    if self.response is not None:
                        await self.response.aclose()
            except (TimeoutError, httpx.HTTPError):
                pass
            finally:
                self.slots.release()

        # ASGI 2.3 level cancellation and direct asyncio cancellation both must
        # join this bounded cleanup. No reader/cleanup task is detached.
        with anyio.CancelScope(shield=True):
            task = asyncio.create_task(cleanup())
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
            task.result()
            if cancelled:
                raise asyncio.CancelledError


class OwnedStreamingResponse(StreamingResponse):
    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Includes headers/send failures where a generator may never start.
            await self.owner.close()


class BadRequest(Exception):
    def __init__(self, status=400):
        self.status = status


async def body(request: Request):
    content = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                content.extend(chunk)
                if len(content) > MAX_REQUEST:
                    raise BadRequest(413)
    except ClientDisconnect:
        raise BadRequest(403) from None
    except TimeoutError:
        raise BadRequest(408) from None
    return bytes(content)


async def json_body(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise BadRequest(415)
    try:
        value = strict_json(await body(request))
        # A lone surrogate (e.g. an id "\ud800") parses but cannot be encoded back into a reply.
        json.dumps(value, ensure_ascii=False).encode("utf-8")
        return value
    except (ValueError, RecursionError):  # UnicodeEncodeError is a ValueError
        raise BadRequest() from None


def prefix(request):
    values = request.headers.getlist("x-ingress-path")
    if len(values) > 1:
        raise BadRequest()
    value = values[0] if values else ""
    if value and (not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", value) or len(value) > 512):
        raise BadRequest()
    return value


def token_valid(request, state):
    values = request.headers.getlist("authorization")
    return (state.token is not None and len(values) == 1
            and hmac.compare_digest(values[0].encode(), ("Bearer " + state.token).encode()))


async def error_handler(_, exc):
    if isinstance(exc, ConfigError):
        return JSONResponse({"error": "state unavailable"}, status_code=503)
    return JSONResponse({"error": "request denied"}, status_code=exc.status)


def make_apps(store: Store, tools, child: httpx.AsyncClient, *,
              verify_admin: RoleVerifier | None = None,
              child_url="http://127.0.0.1:3000/mcp", health=None, backend_changed=None):
    csrf_key = secrets.token_bytes(32)
    mutation_lock = asyncio.Lock()
    slots = asyncio.Semaphore(32)
    admin_slots = asyncio.Semaphore(16)

    def snapshot():
        return health() if health else {"management": "alive", "child": {"state": "not_started", "transport_ready": False}, "backend": "unconfigured"}

    def admin_identity(request):
        # Uvicorn MUST have proxy_headers=False; request.client is the socket peer.
        if not request.client or request.client.host != "172.30.32.2" or verify_admin is None:
            raise BadRequest(403)
        identities = request.headers.getlist("x-remote-user-id")
        if len(identities) != 1 or not valid_user_id(identities[0]):
            raise BadRequest(403)
        user = identities[0]
        base = prefix(request)
        csrf = hmac.new(csrf_key, (user + "\0" + base).encode(), hashlib.sha256).hexdigest()
        if request.method not in ("GET", "HEAD"):
            values = request.headers.getlist("x-csrf-token")
            if len(values) != 1 or not hmac.compare_digest(values[0].encode(), csrf.encode()):
                raise BadRequest(403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                raise BadRequest(403)
        return user, base, csrf

    async def final_role(user):
        try:
            async with asyncio.timeout(3):
                allowed = await verify_admin(user)
        except Exception:
            allowed = False
        if allowed is not True:
            raise BadRequest(403)

    async def admin_action(request, user, base, csrf, value, peer_disconnected, committed):
        name = request.path_params["operation"]
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        # Bounded lock wait; the role check occurs AFTER waiting and validating.
        try:
            async with asyncio.timeout(2):
                await mutation_lock.acquire()
        except TimeoutError:
            raise BadRequest(503) from None
        try:
            state = store.load()
            changes = None
            if name in ("backend", "policy", "endpoint") and request.method == "PUT":
                try:
                    if not isinstance(value, dict):
                        raise ValueError()
                    if name == "backend":
                        if getattr(state, 'product', 'n8n') == 'n8n':
                            if set(value) != {"url", "key"}:
                                raise ValueError()
                            changes = dict(backend_url=value["url"], backend_key=value["key"])
                        else:
                            if set(value) != {"connection"}:
                                raise ValueError()
                            changes = value
                    elif name == "endpoint":
                        if set(value) != {"endpoint"}:
                            raise ValueError()
                        changes = value
                    else:
                        if (set(value) not in ({"writes_enabled", "disabled"}, {"writes_enabled", "disabled", "enabled_write_tools"}) or not isinstance(value["disabled"], list)
                                or any(not isinstance(t, str) or t not in tools for t in value["disabled"])):
                            raise ValueError()
                        changes = value
                    # Validate without writing. Store.update revalidates on commit.
                    type(state).model_validate({**state.model_dump(), **changes})
                except ValueError:
                    raise BadRequest() from None
            if peer_disconnected.is_set():
                raise BadRequest(403)
            await final_role(user)
            if peer_disconnected.is_set():
                raise BadRequest(403)
            # No awaited work between this final decision and disclosure/commit.
            if name == "__ui__" and hasattr(request.state, "ui_path") and request.method in ("GET", "HEAD"):
                return ui.response(request.state.ui_path, base)
            if name == "bootstrap" and request.method == "GET":
                return JSONResponse({"base_path": base, "api_base": base + "/api", "csrf": csrf,
                    "endpoint": state.endpoint, "backend_url": state.backend_url,
                    "backend_key_set": state.backend_key is not None, "token_active": state.token is not None,
                    "product": getattr(state, 'product', 'n8n'),
                    "connection_configured": getattr(state, 'configured', bool(state.backend_url and state.backend_key)),
                    "writes_enabled": state.writes_enabled, "disabled": state.disabled,
                    "policy_contract": "woow-v3-exact-grants",
                    "enabled_write_tools": getattr(state, 'enabled_write_tools', []),
                    "tools": {k: {"write": v.write, "write_grants": v.grants(k),
                                  "operation_parameter": v.selector, "legacy_write": v.legacy_write,
                                  "inputSchema": v.arguments.model_json_schema()} for k, v in tools.items()}, "health": snapshot()}, headers=headers)
            if name == "token/reveal" and request.method == "POST":
                return JSONResponse({"token": store.load().token}, headers=headers)
            if name == "token/rotate" and request.method == "POST":
                updated = store.update(token=secrets.token_urlsafe(32))
                return JSONResponse({"token": updated.token}, headers=headers)
            if name == "token/revoke" and request.method == "POST":
                store.update(token=None)
                return Response(status_code=204, headers=headers)
            if changes is not None:
                updated = store.update(**changes)
                # No yield between durable commit and lifecycle ownership transfer.
                # An authorized mutation is not undone by losing its HTTP caller.
                committed.set()
                if (name == "backend" or (name == "policy" and getattr(state, 'product', 'n8n') in ('emqx', 'litellm'))) and backend_changed:
                    await backend_changed(updated)
                return JSONResponse({"saved": True}, headers=headers)
            return Response(status_code=404)
        finally:
            mutation_lock.release()

    async def admin_api(request):
        user, base, csrf = admin_identity(request)
        # Reject saturation rather than accumulating unbounded body/lock waiters.
        if admin_slots.locked():
            raise BadRequest(503)
        await admin_slots.acquire()
        tasks = []
        action = None
        committed = asyncio.Event()
        try:
            name = request.path_params["operation"]
            if name in ("backend", "policy", "endpoint") and request.method == "PUT":
                value = await json_body(request)
            else:
                if await body(request):
                    raise BadRequest()
                value = None

            peer_disconnected = asyncio.Event()

            async def disconnected():
                # Body is fully consumed: this task exclusively owns receive now.
                while (await request.receive())["type"] != "http.disconnect":
                    pass
                # Deny even when role completion and disconnect wake together,
                # before the outer waiter has had a chance to cancel the action.
                peer_disconnected.set()

            watcher = asyncio.create_task(disconnected())
            action = asyncio.create_task(admin_action(request, user, base, csrf, value, peer_disconnected, committed))
            tasks = [watcher, action]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                raise BadRequest(403)
            return action.result()
        finally:
            for task in tasks:
                if task is not action or not committed.is_set():
                    task.cancel()
            # Before commit: cancel/join role cleanup with zero effects. After
            # commit: join the lifecycle callback without cancelling it; action
            # retains mutation_lock until stop/reap/restart finishes. Neither
            # ASGI nor repeated direct cancellation may detach that ownership.
            cancelled = False
            with anyio.CancelScope(shield=True):
                if tasks:
                    joined = asyncio.gather(*tasks, return_exceptions=True)
                    while not joined.done():
                        try:
                            await asyncio.shield(joined)
                        except asyncio.CancelledError:
                            cancelled = True
            admin_slots.release()
            if cancelled:
                raise asyncio.CancelledError

    async def admin_page(request):
        # The same admission, bounded body, lock, fresh role and disconnect
        # ownership as the API apply to every asset; no unbounded WS fan-out.
        _, base, _ = admin_identity(request)
        raw = request.scope.get("raw_path", b"")
        if b"%" in raw or b"\\\\" in raw or request.url.query:
            raise BadRequest()
        path = request.url.path
        if base and (path == base or path.startswith(base + "/")):
            path = path[len(base):] or "/"
        if path.startswith("/api/"):
            request.path_params["operation"] = path[5:]
        else:
            if request.method not in ("GET", "HEAD"):
                raise BadRequest(404)
            request.path_params["operation"] = "__ui__"
            request.state.ui_path = path
        return await admin_api(request)

    def still_authorized(token):
        try:
            current = store.load().token
            return current is not None and hmac.compare_digest(current, token)
        except ConfigError:
            return False

    async def chunks(owner, token):
        """Bound total bytes/time; poll revocation even while upstream is idle."""
        iterator = owner.response.aiter_bytes()
        total = 0
        try:
            async with asyncio.timeout(STREAM_SECONDS):
                while True:
                    pending = owner.reader = asyncio.create_task(anext(iterator))
                    while not pending.done():
                        await asyncio.wait({pending}, timeout=0.2)
                        if not still_authorized(token):
                            return
                    try:
                        chunk = pending.result()
                    except StopAsyncIteration:
                        return
                    if not still_authorized(token):
                        return
                    total += len(chunk)
                    if total > MAX_RESPONSE:
                        owner.overflowed = True
                        return
                    yield chunk
        except (httpx.HTTPError, TimeoutError):
            return

    async def initialize_reply(owner, token, is_sse, ident):
        """Read the child's reply to initialize: (outcome, message, SSE frame lines other than data).

        outcome is "ok", "missing" or "invalid". Stops at the JSON-RPC response with the request's id
        (an SSE stream may stay open after it). "missing": the child answered 200 and ended without a
        reply, e.g. its per-session lifespan could not reach the backend (Odoo Manage, 0.1.1 HA test),
        so the session id it sent is dead.
        """
        def reply(value):
            return (isinstance(value, dict) and value.get("id") == ident and "method" not in value
                    and ("result" in value or "error" in value))

        pending = bytearray()
        reader = chunks(owner, token)
        try:
            async for chunk in reader:
                start = max(0, len(pending) - 3)  # only new bytes, plus a boundary split across chunks
                pending.extend(chunk)
                while is_sse and (match := EVENT_BOUNDARY.search(pending, start)):
                    parsed = sse_frame(bytes(pending[:match.start()]))
                    del pending[:match.end()]
                    start = 0
                    if parsed is None:
                        return "invalid", None, None
                    kept, data_lines = parsed
                    if not data_lines:
                        continue
                    try:
                        value = strict_json(sse_data(data_lines))
                    except (ValueError, RecursionError):
                        return "invalid", None, None
                    if reply(value):
                        return "ok", value, [line for line in kept if not line.startswith(b":")]
        finally:
            await reader.aclose()
        if owner.overflowed:
            return "invalid", None, None
        if is_sse or not pending.strip():
            return "missing", None, None  # a truncated SSE event is not dispatched
        try:
            value = strict_json(bytes(pending))
        except (ValueError, RecursionError):
            return "invalid", None, None
        if not isinstance(value, dict):
            return "invalid", None, None
        return ("ok", value, None) if reply(value) else ("missing", None, None)

    async def stream(owner, token, is_sse):
        if not is_sse:
            async for chunk in chunks(owner, token):
                yield chunk
            return
        # Restrict advertisements also on resumed GET streams. Every event is rebuilt from the lines the
        # gateway understood (sse_frame), so nothing it did not filter can reach a client as data.
        pending = bytearray()
        async for chunk in chunks(owner, token):
            start = max(0, len(pending) - 3)  # only new bytes, plus a boundary split across chunks
            pending.extend(chunk)
            while match := EVENT_BOUNDARY.search(pending, start):
                parsed = sse_frame(bytes(pending[:match.start()]))
                del pending[:match.end()]
                start = 0
                if parsed is None:
                    return
                kept, data_lines = parsed
                if data_lines:
                    try:
                        value = strict_json(sse_data(data_lines))
                        if (isinstance(value, dict) and isinstance(value.get("result"), dict)
                                and {"tools", "capabilities"} & value["result"].keys()):
                            value = filter_list(value, tools, store.load())
                            data_lines = [b"data: " + json.dumps(value, separators=(",", ":")).encode()]
                    except (ValueError, ConfigError, RecursionError):
                        return
                lines = kept + data_lines
                if lines:
                    yield b"\n".join(lines) + b"\n\n"
        # A truncated SSE event is intentionally not dispatched.

    async def mcp(request):
        state = store.load()
        if not token_valid(request, state):
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        if request.headers.get("origin") is not None:
            raise BadRequest(403)  # Browser clients not in this tracer contract.
        if request.url.query:
            raise BadRequest()
        method = None
        content = b""
        if request.method == "POST":
            message = await json_body(request)
            try:
                method = authorize(message, tools, state)
            except Denied:
                raise BadRequest(403) from None
        elif await body(request):
            raise BadRequest()
        headers = {"Authorization": "Bearer " + state.child_token, "Content-Type": "application/json",
                   "Accept": request.headers.get("accept", "application/json, text/event-stream"),
                   "Accept-Encoding": "identity"}
        for name in ("mcp-session-id", "mcp-protocol-version", "last-event-id"):
            values = request.headers.getlist(name)
            if len(values) > 1 or (values and (len(values[0]) > 256 or not re.fullmatch(r"[\x21-\x7e]+", values[0]))):
                raise BadRequest()
            if values:
                headers[name] = values[0]
        try:
            async with asyncio.timeout(1):
                await slots.acquire()
        except TimeoutError:
            raise BadRequest(503) from None
        upstream = None
        owner = UpstreamOwner(slots)
        handed_off = False
        try:
            # Revalidate after yielding for body/concurrency; sessions do not cache policy.
            state = store.load()
            if not token_valid(request, state):
                raise BadRequest(401)
            if request.method == "POST":
                try:
                    authorize(message, tools, state)
                except Denied:
                    raise BadRequest(403) from None
                content = json.dumps(message, separators=(",", ":")).encode()
            outgoing = child.build_request(request.method, child_url, headers=headers, content=content,
                                           timeout=httpx.Timeout(30, connect=3, pool=3))
            async with asyncio.timeout(35):
                upstream = owner.response = await child.send(outgoing, stream=True, follow_redirects=False)
            response_headers = {k: v for k, v in upstream.headers.items() if k in
                                ("content-type", "mcp-session-id", "mcp-protocol-version", "retry-after")}
            response_headers["Cache-Control"] = "no-store"
            if not still_authorized(state.token):
                raise BadRequest(401)
            is_sse = upstream.headers.get("content-type", "").split(";")[0] == "text/event-stream"
            if is_sse:  # the gateway re-frames events itself: never forward the child's parameters (charset)
                response_headers["content-type"] = "text/event-stream"
            if method in ("initialize", "tools/list") and 200 < upstream.status_code < 300:
                raise BadRequest(502)  # these replies are filtered: only a plain 200 may carry them
            if method == "initialize" and upstream.status_code == 200:
                outcome, value, frame = await initialize_reply(owner, state.token, is_sse, message.get("id"))
                if not still_authorized(state.token):
                    raise BadRequest(401)
                if outcome == "missing":
                    # No dead session id; clients may retry once the backend answers again.
                    return JSONResponse({"jsonrpc": "2.0", "id": message.get("id"),
                                         "error": {"code": -32000, "message": "BACKEND_UNAVAILABLE"}},
                                        status_code=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})
                try:
                    if outcome != "ok":
                        raise ValueError("invalid initialize response")
                    value = filter_list(value, tools, store.load())
                except ValueError:
                    raise BadRequest(502) from None
                if frame is None:
                    response_headers.pop("content-type", None)  # re-serialized: application/json
                    return JSONResponse(value, status_code=200, headers=response_headers)
                # The child's event framing (id/event/retry lines) with the filtered data.
                frame.append(b"data: " + json.dumps(value, separators=(",", ":")).encode())
                return Response(b"\n".join(frame) + b"\n\n", status_code=200, headers=response_headers)
            if method == "tools/list" and not is_sse and upstream.status_code == 200:
                result = bytearray()
                async for chunk in chunks(owner, state.token):
                    result.extend(chunk)
                try:
                    value = filter_list(strict_json(result), tools, store.load())
                except (ValueError, RecursionError):
                    raise BadRequest(502) from None
                if not still_authorized(state.token):
                    raise BadRequest(401)
                response_headers.pop("content-type", None)  # re-serialized: application/json
                return JSONResponse(value, status_code=upstream.status_code, headers=response_headers)
            handed_off = True
            return OwnedStreamingResponse(stream(owner, state.token, is_sse), owner=owner,
                                          status_code=upstream.status_code, headers=response_headers)
        except (httpx.HTTPError, TimeoutError):
            raise BadRequest(502) from None
        finally:
            if not handed_off:
                await owner.close()

    async def readiness(_):
        value = snapshot()
        try:
            state = store.load()
            ready = bool(value["child"]["transport_ready"]
                         and getattr(state, 'configured', bool(state.backend_url and state.backend_key))
                         and value["backend"] == "reachable")
        except ConfigError:
            ready = False
        # Minimal public status exception, never an unconditional watchdog success.
        return JSONResponse({"ready": ready}, status_code=200 if ready else 503)

    exceptions = {BadRequest: error_handler, ConfigError: error_handler}
    admin = Starlette(routes=[Route("/{path:path}", admin_page, methods=["GET", "HEAD", "PUT", "POST"])],
                      middleware=[Middleware(ui.SecurityHeaders)], exception_handlers=exceptions)
    mcp_app = Starlette(routes=[Route("/mcp", mcp, methods=["GET", "POST", "DELETE"]), Route("/health/ready", readiness)], exception_handlers=exceptions)
    admin.router.redirect_slashes = False
    mcp_app.router.redirect_slashes = False
    return admin, mcp_app
