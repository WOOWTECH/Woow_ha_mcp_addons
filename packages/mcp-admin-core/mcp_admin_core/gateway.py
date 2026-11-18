"""Independent Ingress-only admin and token-authenticated Streamable HTTP applications.

Management fails closed without an explicit role provider (installed only by n8n).
No legacy SSE /sse or /messages endpoints are exposed. The MCP endpoint is /mcp with a Bearer header and, from 0.1.12,
/private_<token>/mcp with the same token in the path (Claude.ai custom connectors cannot send headers).
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import copy
from dataclasses import dataclass
import functools
import hashlib
import hmac
from http import HTTPStatus
import json
import logging
import re
import secrets
import time
from typing import Awaitable, Callable, Iterable

import anyio
import httpx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route, request_response
from starlette.middleware import Middleware

from . import odoo_methods, owner_defaults, redact, request_budget, ui
from .access import AccessChanged, LeasedResponse, TokenAccess, masked_token

from . import VERSION
from .config import ConfigError, State, Store, strict_json
from .configuration import ConfigurationState
from .lifecycle import CHILD_URL
from .policy import Denied, ToolCallRefused, UnknownMethod, authorize, filter_list, validate_operation_denies
from .admin_auth import AdminAuthority, BadRequest, prefix
from .capabilities import ManagementOptions, capability_snapshot, observe_tools, tool_catalog
from .request_limits import DEFAULT_MAX_TOTAL_ELEMENTS, McpRequestLimits, RequestLimitError
from .operations import OperationJournal, KINDS as OPERATION_KINDS, RESULTS as OPERATION_RESULTS, TTL_MS
from .reply_worker import WorkerStopped, breathe, encoded
# HM-05 (contract 1.1): a profile's id, the default profile's or 24 lowercase hexadecimal characters; HM-08: the one
# grammar, profiles.PROFILE_ID.
from .profiles import PROFILE_ID, log_id

logger = logging.getLogger(__name__)
# HM-12 (DQ-40 ⑨; contract 4.1): a switched-on product's backend/patch that moves a URL to another origin without the
# secrets it takes there (backend_edit.new_origin_refused). The PaaS Headscale code, in HA's shape for a new code.
NEW_ORIGIN_SECRET = "CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"
# HM-12: what the add-on log says when a switched-on backend identity change fails (one line per failure; the profile
# by profiles.log_id, never a token, URL, label or credential).
REBIND_WARNING = "multi-profile: the backend identity change of profile "

# 0.2.0: 16 MiB (was 256 KiB). The full Nextcloud surface uploads up to 10 MiB as base64 (about 13.4 MiB of JSON) and
# writes text files up to 1 MiB; a body is read only after the token check. BODY_SECONDS bounds the read.
MAX_REQUEST = 16 * 1024 * 1024
# n8n-mcp uses the SDK's low-level Server, so the SDK 1.32.0 McpServer input-element option does not protect it.
# Bound only authenticated n8n ingress here; other products retain MAX_REQUEST for large inputs such as Nextcloud.
N8N_MAX_REQUEST = 4 * 1024 * 1024
N8N_MAX_ARGUMENT_ELEMENTS = 10_000
N8N_MAX_ARGUMENT_DEPTH = 64
N8N_REQUEST_LIMITS = McpRequestLimits(N8N_MAX_REQUEST, N8N_MAX_ARGUMENT_ELEMENTS, N8N_MAX_ARGUMENT_DEPTH)
# HM-31 (contract 1.2, 2.4; PaaS #155 create_app's mcp_structure_limits, woow-mcp-server d7f5849), not gated: every other
# product's JSON structure guard (depth 64, 200,000 elements in the whole request) before the body is parsed; n8n's own
# limits run the same guard first (McpRequestLimits.parse_and_check). Only check_structure is used of it: the body's
# bytes stay bounded by MAX_REQUEST in body().
STRUCTURE_LIMITS = McpRequestLimits(MAX_REQUEST, DEFAULT_MAX_TOTAL_ELEMENTS)
BODY_SECONDS = 60
MAX_RESPONSE = 8 * 1024 * 1024
STREAM_SECONDS = 120
# 0.2.2 (test VM 2026-10-16, G2): a tools/call reply may take as long as its child allows. Each child bounds its own
# backend calls; the longest is a Hermes chat turn (hermes_chat, 300 s: free models took 28-30 s, past the former 30 s).
# A tools/call reply may be idle (between bytes) and take in total up to CALL_SECONDS; every other request keeps the 30 s
# idle and STREAM_SECONDS total limits. The call holds one of the 32 slots meanwhile.
CALL_SECONDS = 330
EVENT_BOUNDARY = re.compile(rb"\r?\n\r?\n")
FORWARDED_HEADERS = {"mcp-session-id": re.compile(r"[\x21-\x7e]{1,256}"),
                     "mcp-protocol-version": re.compile(r"[\x21-\x7e]{1,256}"),
                     "retry-after": re.compile(r"[0-9]{1,10}"),
                     "content-type": re.compile(r"[\x20-\x7e]{1,256}")}
LONE_CR = re.compile(rb"\r(?!\n)")
SSE_FIELD = re.compile(rb"(?:id|event):[ ]?[\x21-\x7e]{0,256}|retry:[ ]?[0-9]{1,10}")  # id as Last-Event-ID allows
SSE_COMMENT = re.compile(rb":[\x20-\x7e]{0,1024}")
# 0.1.4: the only child notification a client gets, and only as these fixed bytes (no child params). Progress is
# never relayed: authorize removes params._meta before dispatch (0.1.13; refused it before), so no client can ask for
# it and any progress event is unsolicited child text (the pinned TS client puts unknown-token progress into an error
# message); log messages and resource updates carry child text or name surfaces the gateway never exposes.
LIST_CHANGED = b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}'
# HM-30: what make_apps' relayed_event makes of an event besides a line to relay: not relayed, or the stream ends.
SKIP_EVENT, END_STREAM = "skip", "end"
# HM-30 D1: an event whose frame is larger than this is framed (sse_frame, sse_data), processed and built into the
# bytes it is relayed as on the reply worker, not on the loop (each of those steps copies or scans the whole frame:
# 35 to 50 ms for an 8 MiB event on the EPYC 7713); a smaller one is framed on the loop, as before.
WORKER_FRAME_BYTES = 64 * 1024
# 0.1.5 (R1 #6): the pinned TS client puts an unsupported protocolVersion into an error, so no child text may pass.
# 0.1.8 (review 6b): only the reviewed MCP revisions, not any date. The pinned children negotiate within this set,
# except n8n-mcp, which echoes "2024-06-25" to a client that asks for it: that initialize is now refused (502).
PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"})
# 0.1.6 (R2): the bound of the gateway's own DELETE that ends an initialize session no client received.
SESSION_END_SECONDS = 2
# 0.1.8 (0.1.6 R1 F6): the name the initialize answer gives when the caller names no product.
SERVER_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
# 0.2.2: sessions the gateway opens itself when no child can answer (make_apps listing=). Idle ones end after 30 minutes,
# as the children's (GATEWAY-3); at most LOCAL_SESSION_LIMIT, the least recently used ending first.
LOCAL_SESSION_SECONDS = 30 * 60
LOCAL_SESSION_LIMIT = 256
# 0.2.2: how long an initialize waits for a child that is starting (connection refused) before the gateway answers it.
CHILD_WAIT_SECONDS = 10
CHILD_RETRY_SECONDS = .25
CHILD_UP = ("running", "starting")
# HM-05 (multi-profile plan 3.2): the management requests one add-on serves at a time (make_apps admin_slots). The
# profiles of an add-on share one set (profile_runtime.SharedAdmin); a make_apps without it has its own, as before.
ADMIN_SLOTS = 16
# HM-08: the requests one profile forwards to its child at once, and how long a request waits for one (make_apps
# forward_slots; plan 5.2: 32 for the default profile, 16 for an additional one; 1 s each, as before).
FORWARD_SLOTS = 32
FORWARD_WAIT_SECONDS = 1
# HM-08 (plan 5.1 point 1): the MCP listener's routes. profile_router's dispatcher matches a request against these same
# templates with Starlette's own Route, so both always agree which path segment is the token.
MCP_ROUTE = "/mcp"
SECRET_ROUTE = "/private_{secret}/mcp"
READY_ROUTE = "/health/ready"
# HM-08 (contract 2.4; the PaaS gateway's GATEWAY_BUSY_ERROR_CODE and Retry-After values, woow-mcp-server 69ac425
# proxy.py): a profile's limit refused the request before its child got it.
GATEWAY_BUSY = -32003
BUSY_RETRY_AFTER = 5
STREAM_RETRY_AFTER = 30
# HM-31 (contract 2.2 point 4, 2.4, 5; PaaS #155): the request state's name for the request's request_budget.Reservation
# (AnyMethod opens one for every MCP request of make_apps' body_budget and closes it when the request ends: its answer
# sent in full, an event stream's last byte included, or its client gone). serve() charges it once the token is checked:
# the body as read (a declared Content-Length before a byte is read) and as forwarded to the child (HM-08 review MF-1,
# S-1). It replaces HM-08's FORWARDED_BODY: one budget, switched on or off.
BODY_RESERVATION = "body_reservation"
# HM-30 (contract 2.4, 6): the request state's name for a switched-on product's check of the profile's answers not
# received yet (profile_router.ProfileGate puts it there). Before a tools/call is forwarded (before it takes or waits
# for a forwarding slot), serve() calls it with the message: None forwards it, anything else is the answer instead
# (the profile's pending-reply budget is used up: 200 + -32003 under its id). HM-30 review 2 MF-2: called again once the
# tools/call took its slot (it may have waited in HM-14's queue meanwhile), right before it is forwarded.
PENDING_REPLIES = "pending_replies"
# HM-30 review 2 MF-2 (contract 2.4, 5): the request state's name for a switched-on product's early charge of a relayed
# JSON reply (profile_router.ProfileGate puts it there): serve() calls it with the bytes of the answer the reply worker
# made, before the request's forwarding slot is released (the slot goes as the reply is handed back, before the
# server took a byte of it); the profile's gate counts them as its answers not received yet from then on, and against
# what its app hands the server later. A tools/call that waited for that slot is then refused by the check above.
PENDING_CHARGE = "pending_charge"
# HM-14 (contract 2.4, 2.5; the PaaS gateway's codes, texts and timings, woow-mcp-server 69ac425 proxy.py, mcp_access.py,
# gateway_pool.py), for a switched-on product only (make_apps slot_busy given): a child whose connection broke while it
# handled a request (-32004) and a token rotated or revoked after an answer began to go out (-32005).
CHILD_INTERRUPTED = -32004
ACCESS_CHANGED = -32005
# How long the gateway keeps looking for the child's exit once its connection broke: the broken connection and the
# Supervisor seeing the exit come within milliseconds of each other, in either order (PaaS CHILD_EXIT_GRACE_SECONDS).
CHILD_EXIT_GRACE_SECONDS = .25
# How long the gateway tries to hand its own ending (a refusal, or the -32005 event and the end of the stream) to a
# client that does not read (PaaS mcp_access.INTERRUPTED_FINISH_TIMEOUT); then it gives up, raising nothing.
ENDING_SECONDS = 2
# The answer of a request whose client closed its connection while it waited for a forwarding slot: nobody receives it
# (the server sends nothing once its client left); 499, nginx's Client Closed Request, as the PaaS gateway answers.
CLIENT_CLOSED = 499
# A switched-on profile's two groups of forwarding slots (Lane): the ordinary one (forward_slots) and the one kept for a
# POST that carries no request (SlotBusy.reserve; carries_no_request).
ORDINARY_LANE, RESERVED_LANE = "ordinary", "reserved"
CHILD_STOPPED_TEXT = (
    "The MCP server process stopped while handling this request (it restarts automatically). The operation may or may "
    "not have completed; check before retrying. (MCP 子程式在處理這個請求時停止了（會自動重新啟動），這個操作可能已完成"
    "也可能沒有，請先確認再重試。)")
CHILD_CONNECTION_TEXT = (
    "The connection to the MCP server was interrupted while handling this request, but the MCP server process is still "
    "running. The operation may or may not have completed; check before retrying. (閘道與 MCP 子程式之間的連線在處理這個"
    "請求時中斷，但子程式仍在執行；這個操作可能已完成也可能沒有，請先確認再重試。)")
# HM-14 after HM-09 (contract 2.5, 7): CHILD_STOPPED_TEXT, the PaaS text, says the child restarts automatically. It does
# only in these Supervisor states (lifecycle.Supervisor.status) once the generation a request went to stopped: the
# watchdog waits out its backoff, a start is under way, a new generation runs. In any other nothing restarts it now
# (blocked: a disabled profile, too little memory, a refused start; failed: its monitor stopped, DQ-21; stopped: the
# profile deleted or the add-on stopping; unconfigured: no connection saved), and the text says so instead.
CHILD_RESTARTING_STATES = frozenset({"backoff", "starting", "running"})
CHILD_HALTED_TEXT = (
    "The MCP server process stopped while handling this request and is not restarting now (blocked, failed, stopped or "
    "not configured; the add-on log says why). The operation may or may not have completed; check before retrying. "
    "(MCP 子程式在處理這個請求時停止了，目前沒有在重新啟動（被擋下、失敗、已停止或沒有設定，原因見 add-on 的 log），"
    "這個操作可能已完成也可能沒有，請先確認再重試。)")
ACCESS_CHANGED_TEXT = (
    "The MCP token was rotated or revoked while this request was running, so the gateway stopped the response. "
    "Reconnect with the current MCP URL or token. (處理這個請求時 MCP 權杖已被輪替或撤銷，閘道已停止這個回應；請用目前的 "
    "MCP 網址或權杖重新連線。)")


@dataclass(frozen=True)
class SlotBusy:
    """HM-14 (contract 2.4, 2.5, 5; plan 12.3 HM-14): make_apps slot_busy, what a switched-on profile's gateway does
    when its forwarding slots are busy and the answers that name the profile (profile_router.ProfileGate builds it from
    the profile's quota and Reports; HM-08 passed only the busy answer):

    - queue: how many requests may wait for a slot at once, in each lane on its own (32 for the default profile, 16 for
      an additional one; 0: none waits);
    - reserve: the slots kept for a POST that carries no request (carries_no_request: notifications/initialized is the
      only one this gateway forwards), 4; 0: such a POST takes an ordinary slot;
    - wait: how long a request waits for a slot (1 s);
    - answer(message, situation, lane): the busy answer, with the profile's WARNING: situation "wait" (it waited in
      vain) or "queue" (its lane's queue was full: refused at once); lane ORDINARY_LANE or RESERVED_LANE; message the
      JSON-RPC message of a POST, else None (busy_reply's shapes);
    - abandoned(lane): its client closed its connection while it waited (a WARNING; the request is never sent);
    - interrupted(http_method, error_name, stopped): the connection to the child broke while it handled a request (a
      WARNING; stopped: the child generation it went to has stopped)."""
    queue: int
    reserve: int
    wait: float
    answer: Callable[[object, str, str], Response]
    abandoned: Callable[[str], None]
    interrupted: Callable[[str, str, bool], None]

    def __post_init__(self):
        if (type(self.queue) is not int or type(self.reserve) is not int or self.queue < 0 or self.reserve < 0
                or isinstance(self.wait, bool) or not isinstance(self.wait, (int, float)) or not self.wait > 0
                or not all(callable(value) for value in (self.answer, self.abandoned, self.interrupted))):
            raise ValueError("invalid busy answer")


def carries_no_request(method, message):
    """HM-14 (contract 2.4; the PaaS rule, proxy._carries_no_request, woow-mcp-server 69ac425 proxy.py:336): whether a
    request may use its profile's reserved slots: a POST whose JSON value carries no JSON-RPC request, an object or a
    non-empty array of objects, none of them a request (a string method with an id other than null) and each a
    notification (a string method) or a response to the server (an id and a result or an error, no method). Anything
    else is False and takes an ordinary slot: another HTTP method (a GET is a stream, a DELETE ends a session), nothing
    parsed (None), an empty array, a value that is not an object, a member that is neither. HA's policy lets only single
    messages through (authorize: a batch, a response and an id-less call are refused before any slot), so the one POST
    that reaches the reserve here is notifications/initialized; the rule is the PaaS one, unchanged."""
    if method != "POST" or message is None:
        return False
    items = message if isinstance(message, list) else [message]
    if not items or any(isinstance(item, dict) and isinstance(item.get("method"), str) and item.get("id") is not None
                        for item in items):
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if "method" in item:
            if not isinstance(item["method"], str):
                return False
        elif "id" not in item or not ("result" in item or "error" in item):
            return False
    return True


class Lane:
    """HM-14: one group of a switched-on profile's forwarding slots and the requests waiting for them (take_slot)."""
    __slots__ = ("name", "limit", "semaphore", "waiting")

    def __init__(self, name, limit):
        self.name, self.limit = name, limit
        self.semaphore = asyncio.Semaphore(limit)
        self.waiting = 0


def _hand_back(semaphore):
    """When a slot's acquire ends after its waiter gave up (timed out, its client left, it was cancelled): a slot the
    acquire took is released at once (PaaS gateway_pool._hand_back)."""
    def done(task):
        if not task.cancelled() and task.exception() is None:
            semaphore.release()
    return done


def _consume(task):
    if not task.cancelled():
        task.exception()  # retrieved: no "Task exception was never retrieved"


async def _watch_client(gone):
    """Until the client is gone. A watcher that fails (its receive raised) is no disconnect and never ends the wait
    early: it then waits for nothing, the slot and the deadline decide (PaaS gateway_pool._watch_client)."""
    try:
        await gone()
    except asyncio.CancelledError:
        raise
    except Exception:
        await asyncio.Event().wait()


async def take_slot(lane, queue, wait, gone):
    """HM-14 (contract 2.4; PaaS gateway_pool.ProfileLimitedTransport._acquire and _wait_for_slot, 69ac425): one of
    lane's slots for a request whose body is read. A free slot is taken at once, without yielding. Otherwise the request
    waits, unless queue requests already wait in this lane ("queue": refused at once, it does not wait), for at most wait
    seconds ("wait": none came free) while gone() watches its client: a client that closed its connection is never
    forwarded ("abandoned"), even when a slot came free in the same instant (that slot is given back). "taken": the
    caller holds one of lane.semaphore's slots (UpstreamOwner releases it). Between a slot taken and the return there is
    no await and the clean-up is synchronous, so a cancellation anywhere leaks no slot and leaves no waiter behind."""
    if not lane.semaphore.locked():
        await lane.semaphore.acquire()  # a free slot: no wait, no yield
        return "taken"
    if lane.waiting >= queue:
        return "queue"
    lane.waiting += 1
    loop = asyncio.get_running_loop()
    acquire = loop.create_task(lane.semaphore.acquire())
    watch = loop.create_task(_watch_client(gone))
    keep = False
    try:
        done, _ = await asyncio.wait({acquire, watch}, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
        got = acquire in done and not acquire.cancelled() and acquire.exception() is None
        left = watch in done
        if got and not left:
            keep = True
            return "taken"
        return "abandoned" if left else "wait"  # a client gone in the same instant: the slot goes back, nothing is sent
    finally:
        lane.waiting -= 1
        if not keep:
            if not acquire.done():
                acquire.cancel()
            acquire.add_done_callback(_hand_back(lane.semaphore))
        if not watch.done():
            watch.cancel()
        watch.add_done_callback(_consume)


async def client_gone(request):
    """Returns when the client closed its connection (http.disconnect). Called only once the body is read in full and
    before the answer starts, so nothing else reads the request then."""
    while (await request.receive())["type"] != "http.disconnect":
        pass


def interrupted(error):
    """HM-14: whether an httpx error means the child's connection broke while it handled the request (a read, write or
    protocol error once it was reached), not that it could not be reached (ConnectError) or answered too slowly."""
    return (isinstance(error, httpx.TransportError)
            and not isinstance(error, (httpx.TimeoutException, httpx.ConnectError)))


def gateway_event(ident, code, text):
    """One SSE event with the gateway's own JSON-RPC error under ident (contract 2.5: -32004, -32005)."""
    value = {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": text}}
    return b"event: message\ndata: " + json.dumps(value, separators=(",", ":")).encode() + b"\n\n"


def request_id(message):
    """HM-08: the id of message when it is a JSON-RPC request this gateway would answer under that id (an object of
    jsonrpc 2.0 with a string method and a string or integer id: authorize's rule), else None. A batch, a notification,
    a response, a boolean or other id are None: this gateway never answers a batch or another id type."""
    if (isinstance(message, dict) and message.get("jsonrpc") == "2.0" and isinstance(message.get("method"), str)
            and type(message.get("id")) in (str, int)):
        return message["id"]
    return None


def busy_reply(message, text):
    """HM-08 (contract 2.4, the PaaS table): a request a profile's limit refused before its child got it. A request
    with an id: HTTP 200 with a -32003 error under that id (MCP Python SDK 1.x ends the whole session on any other
    status); anything else (no id, a GET, a DELETE, a body that was not read): 503 with the error under id null. Both
    with Retry-After 5 and Cache-Control no-store. text is fixed text: never a token, a URL or a label."""
    ident = request_id(message)
    return json_reply({"jsonrpc": "2.0", "id": ident, "error": {"code": GATEWAY_BUSY, "message": text}},
                      503 if ident is None else 200,
                      {"Retry-After": str(BUSY_RETRY_AFTER), "Cache-Control": "no-store"})


def stream_busy_reply(text):
    """HM-08 (contract 2.4): a GET while the profile's event streams are at their cap: 429, Retry-After 30, a -32003
    error under id null, at once (a stream is never queued)."""
    return json_reply({"jsonrpc": "2.0", "id": None, "error": {"code": GATEWAY_BUSY, "message": text}}, 429,
                      {"Retry-After": str(STREAM_RETRY_AFTER), "Cache-Control": "no-store"})


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


def same_id(value, ident):
    """JSON-RPC ids match only with the same JSON type: true is not 1."""
    return type(value) is type(ident) and value == ident


def backend_unavailable(ident):
    """initialize without a reply from the child: no dead session id; clients may retry later."""
    return json_reply({"jsonrpc": "2.0", "id": ident, "error": {"code": -32000, "message": "BACKEND_UNAVAILABLE"}},
                      503, {"Retry-After": "5", "Cache-Control": "no-store"})


def one_reply(value):
    """A JSON-RPC response object: exactly one of result and error (a client may parse both as an error)."""
    return isinstance(value, dict) and "method" not in value and (("result" in value) != ("error" in value))


def gateway_reply(value, method=None):
    """The reply a client gets is the gateway's own object (0.1.5): jsonrpc, id and exactly one of result or error,
    no other top-level member, and an error with only code (an integer), message and data: the pinned TS client's
    strict schemas put an unknown key's name (child text) into an error. The same holds for ping's empty result
    (R1 #3), so a successful ping is always {}; other results are relayed (tools/capabilities filtered by the caller).
    An error the gateway cannot vouch for becomes its own (0.1.4): a URL elicitation error (-32042) asks the user to
    open a child-chosen URL (the gateway declares no elicitation capability); a code that is not a 32-bit JSON integer
    (e.g. "-32042", which a Python client coerces; integral floats count, as for clients) or a message that is not a
    string is malformed."""
    if "result" in value:
        return {"jsonrpc": "2.0", "id": value.get("id"), "result": {} if method == "ping" else value["result"]}
    error = value["error"]
    code = error.get("code") if isinstance(error, dict) else None
    if (not (type(code) is int or type(code) is float and code.is_integer()) or not -2 ** 31 <= code < 2 ** 31
            or not isinstance(error.get("message"), str)):
        error = {"code": -32000, "message": "Invalid error from the MCP server"}
    elif code == -32042:
        error = {"code": -32000, "message": "URL elicitation is not supported"}
    else:
        error = {"code": int(code), "message": error["message"], **({"data": error["data"]} if "data" in error else {})}
    return {"jsonrpc": "2.0", "id": value.get("id"), "error": error}


def child_status_reply(ident, status, headers):
    """0.1.4: a non-2xx child reply keeps its status (404 ends a session, Retry-After still applies) but never the
    child's bytes; MCP clients put error bodies into user-visible messages (0.1.2 review note)."""
    try:
        text = HTTPStatus(status).phrase
    except ValueError:
        text = "HTTP %d" % status
    return json_reply({"jsonrpc": "2.0", "id": ident, "error": {"code": -32000, "message": text}}, status, headers)


def json_reply(value, status, headers):
    """Re-serialized JSON with ASCII escapes, so a lone surrogate from a child cannot make the reply unencodable."""
    return encoded_reply(json.dumps(value, separators=(",", ":")).encode(), status, headers)


def encoded_reply(body, status, headers):
    """HM-30: json_reply's answer for a body already serialized as json_reply serializes it (the reply worker's)."""
    headers = {k: v for k, v in headers.items() if k != "content-type"}
    return Response(body, status_code=status, media_type="application/json", headers=headers)
RoleVerifier = Callable[[str], Awaitable[bool]]
# HM-05 (multi-profile plan 5.3): the shared management pipeline make_apps can be given (admin_pipeline): it takes one
# management request with the profile's action and answers it.
AdminPipeline = Callable[[Request, Callable[..., Awaitable[Response]]], Awaitable[Response]]


def profile_echo(view):
    """HM-05: a profile's echo as make_apps' profile_view gives it (plan 5.3 item 5, contract 3.4): exactly its id,
    its label (a non-empty string) and is_default (true for the default profile only). Anything else: ValueError."""
    if (not isinstance(view, dict) or set(view) != {"id", "label", "is_default"}
            or not isinstance(view["id"], str) or not PROFILE_ID.fullmatch(view["id"])
            or not isinstance(view["label"], str) or not view["label"]
            or view["is_default"] is not (view["id"] == "default")):
        raise ValueError("invalid profile echo")
    return {"id": view["id"], "label": view["label"], "is_default": view["is_default"]}


class UpstreamOwner:
    """Own the reader, response and slot across ASGI cancellation and handoff (0.1.6: and the end of an initialize
    session that no client received)."""
    def __init__(self, slots):
        self.slots = slots
        self.response = None
        self.reader = None
        self.iterator = None
        self.closed = False
        self.overflowed = False  # chunks() stopped at MAX_RESPONSE, not at the end of the reply
        self.end_session = None  # 0.1.6 (R2): set while the child's new session id is withheld from the client
        # HM-14 (switched on; contract 2.5): the error that broke the child's connection while chunks() read its reply
        # (interrupted), the child generation the request went to (its Supervisor's start count, when there is a health
        # monitor), the POST's id an event stream answers ((id,), None for a GET) and whether its answer was delivered:
        # the child's reply or, once the child's connection broke, the gateway's own -32004 event (review S-1).
        self.interrupted = None
        self.generation = None
        self.reply = None
        self.answered = False
        self.reply_event = None  # the answer's event as the stream yields it (an Ending compares what the server took)

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
                    if self.iterator is not None:
                        # A send can be cancelled while iteration is paused at a
                        # yield, with no pending anext task left to cancel.
                        await self.iterator.aclose()
                    if self.response is not None:
                        await self.response.aclose()
            except (TimeoutError, httpx.HTTPError):
                pass
            finally:
                try:
                    if self.end_session is not None:
                        # After the reply is closed (its connection is free) or the budget above cut that close, and
                        # inside this request's slot, so these DELETEs never outnumber the slots. Bounded; no Exception
                        # leaves it (a BaseException such as a cancellation can, and the slot is still released).
                        await self.end_session()
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


class OwnedInitializeResponse:
    """Retain the new-session cleanup obligation until its complete answer is sent.

    HM-14 (switched on; FM-43, contract 2.5): fence() is asked right before the answer's headers go out, when the session
    id would reach the client. While the child generation the initialize went to is no longer the one running (it
    exited, was stopped or replaced), the client gets fenced instead (backend_unavailable: 503, Retry-After 5, no session
    id) and the dead session gets no DELETE (it ended with its child; the DELETE would reach the next generation)."""
    def __init__(self, response, owner, fence=None, fenced=None):
        self.response, self.owner, self.fence, self.fenced = response, owner, fence, fenced
        self.status_code = response.status_code

    async def __call__(self, scope, receive, send):
        try:
            if self.fence is not None and not self.fence():
                self.owner.end_session = None
                await self.fenced(scope, receive, send)
                return
            await self.response(scope, receive, send)
            self.owner.end_session = None
        finally:
            await self.owner.close()


class Ending:
    """HM-14 (switched on; contract 2.5; PaaS mcp_access._finish_interrupted and initialize_fence, woow-mcp-server
    69ac425): how the gateway ends an answer whose token was rotated or revoked (a deleted profile's token is revoked
    first) after the answer began to go out (access.LeasedResponse ending), instead of raising ClientDisconnect to the
    server (which logged it with a traceback, and answered 500 when no header had gone out):

    - its headers were not taken by the server (the client was not reading: backpressure): refusal, the bytes a changed
      token gets before an answer starts (Bearer 401 {"error":"request denied"}, secret path 404 Not Found);
    - its headers went out on an event stream: one -32005 event under the POST's id when its answer was not delivered
      (its answer: the child's reply, or the gateway's own -32004 event once the child's connection broke; a GET stream
      gets none), then the end of the stream; never another byte of the child's;
    - its headers went out on a buffered answer: its Content-Length is fixed (HM-01's golden bytes), so nothing more can
      be sent; the gateway returns and the server closes the connection (uvicorn logs one line without a traceback,
      "ASGI callable returned without completing response.");
    - the answer was complete: nothing.
    Each within ENDING_SECONDS; for a client that reads nothing the gateway gives up quietly."""

    def __init__(self, refusal, response):
        self.refusal, self.response = refusal, response

    async def __call__(self, scope, receive, send, delivery):
        if delivery.completed:
            return
        try:
            async with asyncio.timeout(ENDING_SECONDS):
                if not delivery.accepted:
                    await self.refusal(scope, receive, send)
                    return
                if not isinstance(self.response, OwnedStreamingResponse):
                    return
                owner = self.response.owner
                # the answer is delivered once the server took its event (the child's reply or the gateway's -32004):
                # the generator resumed after it (answered), or the token changed as the server took it (the last body
                # the server took is that event)
                answered = owner.answered or (owner.reply_event is not None and delivery.last_body is owner.reply_event)
                if owner.reply is not None and not answered:
                    await send({"type": "http.response.body", "more_body": True,
                                "body": gateway_event(owner.reply[0], ACCESS_CHANGED, ACCESS_CHANGED_TEXT)})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        except (TimeoutError, OSError, ClientDisconnect):
            pass


class AnyMethod:
    """An ASGI endpoint, so Starlette hands every method to the handler: the Bearer check comes first, then 405.

    HM-31: budget (a request_budget.Share), when given, opens the request's reservation (the request's state,
    BODY_RESERVATION) and closes it when the request ends, however it ends: nothing it held stays charged."""
    def __init__(self, handler, budget=None):
        self.app = request_response(handler)
        self.budget = budget

    async def __call__(self, scope, receive, send):
        if self.budget is None:
            return await self.app(scope, receive, send)
        reservation = self.budget.open()
        # A copy of the request's state, so nothing is written into the server's own dict.
        scope = {**scope, "state": {**scope.get("state", {}), BODY_RESERVATION: reservation}}
        try:
            await self.app(scope, receive, send)
        finally:
            reservation.close()


async def body(request: Request):
    # HM-31 review MF-3: a body that declares more than MAX_REQUEST (request_budget.declared_length: one Content-Length
    # and no Transfer-Encoding) can never be served: today's 413 before a byte of it is read, never charged to the
    # request body budget nor answered with its retryable -32003 (PaaS: not charged, 413; n8n's read_body does the same).
    # The response is the one a body read past MAX_REQUEST gets; 8099's management API reads through here too.
    declared = request_budget.declared_length(request.headers.raw)
    if declared is not None and declared > MAX_REQUEST:
        raise BadRequest(413)
    content = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                content.extend(chunk)
                if len(content) > MAX_REQUEST:
                    raise BadRequest(413)
    except ClientDisconnect:
        raise BadRequest(403) from None
    except TimeoutError:
        raise BadRequest(408) from None
    return bytes(content)


async def json_body(request, guard=None):
    """HM-31: guard (an McpRequestLimits; the MCP path gives STRUCTURE_LIMITS) checks the body's structure and encoding
    before it is parsed: request_limits.too_complex (a RequestLimitError) when it is too deep, has too many elements or
    is not UTF-8. The management API gives none."""
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise BadRequest(415)
    try:
        raw = await body(request)
        if guard is not None:
            guard.check_structure(raw)
        value = strict_json(raw)
        # A lone surrogate (e.g. an id "\ud800") parses but cannot be encoded back into a reply.
        json.dumps(value, ensure_ascii=False).encode("utf-8")
        return value
    except (ValueError, RecursionError):  # UnicodeEncodeError is a ValueError
        raise BadRequest() from None


def request_limit_reply(error):
    return json_reply(error.payload, error.status, {"Cache-Control": "no-store"})


def idle_reply(seconds):
    """HM-31 (contract 2.4; PaaS proxy._idle_timeout_response, d7f5849): a large request whose body sent nothing for
    seconds: 408, -32003 under id null, Retry-After 5, Connection: close (the body was not read to its end); its bytes
    were given back."""
    return json_reply({"jsonrpc": "2.0", "id": None,
                       "error": {"code": GATEWAY_BUSY, "message": request_budget.idle_text(seconds)}}, 408,
                      {"Retry-After": str(BUSY_RETRY_AFTER), "Cache-Control": "no-store", "Connection": "close"})


def token_valid(request, state):
    values = request.headers.getlist("authorization")
    return (state.token is not None and len(values) == 1
            and hmac.compare_digest(values[0].encode(), ("Bearer " + state.token).encode()))


def secret_valid(secret, state):
    """0.1.12: the /private_<secret>/mcp credential is the add-on token itself (rotate and revoke apply at once).

    Both sides are hashed to fixed-length digests before hmac.compare_digest, so neither the token's length nor how
    much of a guess matches shows in the timing; there is no separate length or charset check to leak through. A
    revoked token (None) matches nothing."""
    if state.token is None:
        return False
    supplied = hashlib.sha256(secret.encode("utf-8", "replace")).digest()
    return hmac.compare_digest(supplied, hashlib.sha256(state.token.encode()).digest())


def json_only(request):
    """0.1.13: the client's Accept names application/json and neither text/event-stream nor */*."""
    accept = ",".join(request.headers.getlist("accept")).lower()
    return "application/json" in accept and "text/event-stream" not in accept and "*/*" not in accept


async def error_handler(request, exc):
    if isinstance(exc, ConfigError):
        return JSONResponse({"error": "state unavailable"}, status_code=503)
    detail = getattr(exc, "detail", None)
    if detail is not None:
        # An HA Core version this release has not reviewed (admin_auth.denial_detail). The role check guards every
        # panel asset too, so a page request gets the reason as static HTML; API callers get the fixed code.
        if getattr(request.state, "ui_path", None) in ui.PAGES:
            return ui.unreviewed_core_page(detail["ha_version"])
        return JSONResponse({"error": "request denied", "detail": detail}, status_code=exc.status)
    return JSONResponse({"error": "request denied"}, status_code=exc.status)


# ---- HM-10 (multi-profile plan 5.3; contract 3.1, 3.2): the shared management pipeline ----
# Extracted from make_apps' admin_page and admin_api, so that a switched-on product's 8099 dispatcher
# (profile_router.AdminDispatcher) runs exactly the steps make_apps runs before it chooses a profile. make_apps serves a
# switched-off product with them as before, byte for byte (HM-01's management contract freeze).

# The profile-scoped operations that take a JSON body, every one a PUT (step 3); any other management request has none.
JSON_OPERATIONS = frozenset({"backend", "backend/patch", "policy", "endpoint", "odoo/write-switches", "n8n/session",
                             odoo_methods.ROUTE})
# Every profile-scoped operation a profile's action answers, with its method (contract 3.1). The refusal matrix
# (tests/test_admin_pipeline_matrix.py) is generated from this table and fails when admin_action answers an operation
# that is not in it.
PROFILE_OPERATIONS = (
    ("bootstrap", "GET"), ("configuration", "GET"), ("capabilities", "GET"), ("diagnostics", "GET"),
    ("operations/{id}", "GET"), ("backend", "PUT"), ("backend/patch", "PUT"), ("policy", "PUT"), ("endpoint", "PUT"),
    ("odoo/write-switches", "PUT"), ("n8n/session", "PUT"), (odoo_methods.ROUTE, "PUT"), ("backend/test", "POST"),
    ("child/restart", "POST"), ("token/reveal", "POST"), ("token/rotate", "POST"), ("token/revoke", "POST"),
    ("owner-defaults/restore", "POST"), ("owner-defaults/dismiss", "POST"))
# The methods 8099 routes (Starlette answers any other with its 405 before the identity check); a switched-on product's
# dispatcher routes PATCH and DELETE too and keeps that 405 for every path but its own (contract 3.1).
MANAGEMENT_METHODS = ("GET", "HEAD", "POST", "PUT")


def management_app(endpoint, methods=MANAGEMENT_METHODS):
    """The management listener's application: every path to endpoint, ui.SecurityHeaders on every answer, BadRequest and
    ConfigError answered by error_handler, no slash redirect."""
    app = Starlette(routes=[Route("/{path:path}", endpoint, methods=list(methods))],
                    middleware=[Middleware(ui.SecurityHeaders)],
                    exception_handlers={BadRequest: error_handler, ConfigError: error_handler})
    app.router.redirect_slashes = False
    return app


def method_not_allowed(methods):
    """The bytes Starlette's routing answers a method it does not route with (405, text/plain, Allow), for the
    dispatcher's method table (contract 3.1: fixed, no detail); Allow in this fixed order."""
    return Response("Method Not Allowed", status_code=405, media_type="text/plain",
                    headers={"Allow": ", ".join(methods)})


def management_operation(request, identity):
    """The page checks every management request passes first (admin_page's, unchanged): the caller's identity (here only
    for its mount base; 403 or 400), no '%' and no backslash pair in the raw path and no query (400), and the operation:
    the path after {base}/api/, or "__ui__" for any other path (a page or an asset, request.state.ui_path). The caller
    refuses a page written to (404)."""
    _, base, _ = identity(request)
    raw = request.scope.get("raw_path", b"")
    if b"%" in raw or b"\\\\" in raw or request.url.query:
        raise BadRequest()
    path = request.url.path
    if base and (path == base or path.startswith(base + "/")):
        path = path[len(base):] or "/"
    if path.startswith("/api/"):
        request.path_params["operation"] = path[5:]
    else:
        request.path_params["operation"] = "__ui__"
        request.state.ui_path = path
    return base, request.path_params["operation"]


async def management_value(request, takes_json):
    """Step 3, the bounded body read: the JSON value of an operation that takes one (415, 400, 403, 408, 413), else no
    body at all (400)."""
    if takes_json:
        return await json_body(request)
    if await body(request):
        raise BadRequest()
    return None


async def management_exchange(request, identity, slots, read, step):
    """Steps 1 to 4 of every management request (admin_api's, extracted by HM-10): identity(request) gives (user, base,
    csrf) or refuses (403; 400 for X-Ingress-Path); one of slots (the add-on's management slots: 503 at once when all
    are taken); await read(request), the request's value (step 3); then step(request, user, base, csrf, value,
    peer_disconnected, committed) runs while a watcher waits for the client to leave (step 4: a client gone first is
    403 and the step is cancelled with zero effects; once the step set committed it runs to its end, never cancelled,
    and keeps whatever lock it holds until then). Its answer is the step's."""
    user, base, csrf = identity(request)
    # Reject saturation rather than accumulating unbounded body/lock waiters.
    if slots.locked():
        raise BadRequest(503)
    await slots.acquire()
    tasks = []
    action = None
    committed = asyncio.Event()
    try:
        value = await read(request)
        peer_disconnected = asyncio.Event()

        async def disconnected():
            # Body is fully consumed: this task exclusively owns receive now.
            while (await request.receive())["type"] != "http.disconnect":
                pass
            # Deny even when role completion and disconnect wake together,
            # before the outer waiter has had a chance to cancel the action.
            peer_disconnected.set()

        watcher = asyncio.create_task(disconnected())
        action = asyncio.create_task(step(request, user, base, csrf, value, peer_disconnected, committed))
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
        slots.release()
        if cancelled:
            raise asyncio.CancelledError


def make_apps(store: Store, tools, child: httpx.AsyncClient, *,
              verify_admin: RoleVerifier | None = None,
              child_url=CHILD_URL, health=None, backend_changed=None,
              server_name="woow-mcp", instructions: str | None = None,
              listing=None, availability=None, management: ManagementOptions | None = None,
              backend_check=None, restart_child=None, diagnostics=None, configuration=None,
              secret_path_allowed_origins: frozenset[str] | None = None,
              authority: AdminAuthority | None = None, admin_slots: asyncio.Semaphore | None = None,
              admin_pipeline: AdminPipeline | None = None, token_access: TokenAccess | None = None,
              mutation_lock: asyncio.Lock | None = None, profile_view: Callable[[], dict] | None = None,
              forward_slots: int | None = None, slot_busy: SlotBusy | None = None,
              reply_secrets: Callable[[], Iterable[str]] | None = None,
              child_blocked: Callable[[], str | None] | None = None,
              default_endpoint: Callable[[], str | None] | None = None,
              bootstrap_fields: Callable[[], dict] | None = None,
              body_budget: request_budget.Share | None = None,
              stop_child: Callable[[], Awaitable] | None = None,
              reply_worker=None,
              dormant_profiles: int | None = None):
    """listing (0.2.2): the product's tools/list tools as its child lists them (surface.listing). With it, a client
    connects whatever the backend's state: when no child can answer (no backend configured, so no child; a child that is
    not up) the gateway answers initialize, notifications/initialized, ping and tools/list itself, from listing through
    the same filter_list, in a session of its own, and refuses tools/call with a JSON-RPC error; a tool that
    requires_backend is refused without a configured backend (-32603 Backend not configured; n8n's child, which runs
    without one, still answers its documentation tools) and while the last health check finds the backend unreachable
    (-32603 Backend unreachable, with the check's reason). availability() is HealthMonitor.availability. Without listing
    (Odoo Manage, older tests) nothing changes.

    HM-05 (multi-profile plan 3.2, 5.3): the apps of one profile (store). Each of these is created here when left out,
    exactly as before; profile_runtime.ProfileRuntime passes them:
    - authority: the add-on's AdminAuthority, shared by every profile (one CSRF key; one HA role verifier, so one
      bound on its concurrent queries). verify_admin, when also given, must be its verifier.
    - admin_slots: the add-on's management slots (ADMIN_SLOTS), shared by every profile.
    - admin_pipeline: the shared management pipeline (HM-10). Every management request that passed the page checks
      goes to admin_pipeline(request, action) instead of admin_api (identity, the slots, the bounded body read, the
      disconnect watch, all of which it then owns); it lets this profile act by awaiting action(request, user, base,
      csrf, value, peer_disconnected, committed): this profile's lock, validation on its state, the final role check,
      If-Match, receipts and commit, unchanged (with the profile echo on its answer, none on the pipeline's own).
    - token_access: this store's TokenAccess, created by the profile's runtime, which reaches it (a token change of
      one profile ends only that profile's leases).
    - mutation_lock: this profile's lock, created by its runtime; every management change of the profile holds it.
    - profile_view: the profile's echo (DQ-40 point 2), a callable read for every answer: {"id", "label",
      "is_default"} (profile_echo). The bootstrap then carries it as "profile" with "profiles_supported": true, and
      every other JSON answer of this profile's action its id ("profile": {"id"}); see echoed() in admin_page.

    HM-08 (multi-profile plan 5.1, 5.2; contract 2.4, 2.7), given only for a switched-on product (profile_runtime's
    ProfileManager); left out, everything stays as before:
    - forward_slots: this profile's forwarding slots (FORWARD_SLOTS when left out; an additional profile has 16).
    - slot_busy: a SlotBusy (profile_router.ProfileGate.slot_busy; HM-14): what a request gets when the profile's
      forwarding slots are busy and the answers that name the profile (see below). Left out: a request waits
      FORWARD_WAIT_SECONDS for one of the slots, then gets 503 {"error":"request denied"}, as before.
    - reply_secrets: every token and child token the add-on holds (every profile's, every orphan's; a callable read
      for every reply). Every answer that carries a child's or a backend's text (a relayed reply, an SSE event, the
      gateway's own tools/list, a refused tools/call's health reason, a child's initialize error, backend/test,
      diagnostics) is masked with this profile's own secrets (redact.secret_values, as before) and these (DQ-40 (a) ⑧).
    The byte budget HM-08 charged in the dispatcher (FORWARDED_BODY) is HM-31's body_budget now, switched on or off.

    HM-09 (multi-profile plan 5.4; contract 3.1, 3.6), likewise only for a switched-on product:
    - child_blocked: why the profile's child is not started now (lifecycle.Supervisor.blocked_reason: None,
      child_port_conflict, child_port_in_use, memory_capacity), read after a child/restart; its 202 answer then
      carries it as "blocked_reason" (PaaS B-22: a refused restart looked like a success). Left out: as before.

    HM-14 (plan 12.3 HM-14; contract 2.4, 2.5; the PaaS #148 gateway, woow-mcp-server 69ac425), given slot_busy (a
    switched-on product); left out, every answer below stays as before:
    - two lanes of forwarding slots: a POST that carries no request (carries_no_request) takes one of the slot_busy.reserve
      slots kept for it, anything else an ordinary one (forward_slots). In each lane at most slot_busy.queue requests wait
      at once; one more is refused at once, one that waited slot_busy.wait seconds in vain is refused (both:
      slot_busy.answer, busy_reply's shapes: an id 200 + -32003, none 503; Retry-After 5). A request whose client closes
      its connection while it waits is dropped and never forwarded (take_slot; slot_busy.abandoned).
    - the child's connection breaks while it handles a request (interrupted): before the answer's headers, 502 with the
      gateway's own -32004 error (under the request's id when it has one); on an event stream, one -32004 event under the
      POST's id, then the end. Its text says whether the child generation the request went to has stopped (looked at for
      up to CHILD_EXIT_GRACE_SECONDS) or still runs, and of a stopped one whether it comes back by itself
      (interruption_text: HM-09's Supervisor states); slot_busy.interrupted writes the profile's WARNING.
    - the token changes after the answer began to go out: the gateway's own ending (Ending), no exception for the server.
    - an initialize answer is handed to the client only while the child generation it went to still runs
      (OwnedInitializeResponse fence); otherwise backend_unavailable, no session.

    HM-14 (contract 1.2, not gated): a child's initialize error (its message and data are the child's text) is masked as
    every other relayed text, whether or not the product is switched on (HM-08 review S-4 (a): it was relayed unmasked,
    with not even this profile's own credentials masked).

    HM-10 (multi-profile plan 5.3; contract 3.1, 3.4), only for a switched-on product, as HM-08's and HM-09's:
    - default_endpoint: given for an additional profile only: the add-on's one endpoint (DQ-13: stored in the default
      profile's state), read for its bootstrap; its PUT endpoint answers 409 endpoint_global (shape A) and its
      owner-defaults actions 409 owner_defaults_unavailable (shape C): only the default profile has the one-time
      migration's notice (FM-08), whatever its directory holds.
    - bootstrap_fields: what the bootstrap carries after the echo (profiles_supported; the default profile's
      profile_index_state): a callable read for every bootstrap, only with profile_view.
    The admin app's state.profile_action is this profile's action (admin_action and its echo), for the dispatcher:
    profile_router.AdminDispatcher runs the shared pipeline itself and calls it once it has chosen this profile.

    HM-31 (plan 12.3 HM-31; contract 1.2, 2.4, 5; the PaaS #155 gateway, woow-mcp-server d7f5849), not gated: every MCP
    request is read under the add-on's request body budget, and every POST body passes the JSON structure guard.
    - body_budget: this profile's request_budget.Share of the add-on's budget (profile_runtime.ProfileManager gives
      every profile of a switched-on add-on its share of one budget). Left out: a budget of this add-on's own, made now
      (request_budget.own_share: derived from the memory at startup, the default profile's share).
    - once the token is checked, a large body (declared over 64 KiB, or without Content-Length; a Content-Length
      beside a Transfer-Encoding declares nothing, review MF-1) is charged: a declared length that does not fit is
      refused before a byte is read, its body drained (only its head and tail kept, to find its id: 200 + -32003
      under it, else 503; Retry-After 5); the bytes that arrive are charged too, whatever was declared, and a body is
      cut off once they do not fit (its id from its head); one that sends nothing for
      request_budget.BODY_IDLE_SECONDS gets 408 (idle_reply). A body that declares more than MAX_REQUEST gets today's
      413 before a byte is read (body(); review MF-3).
      The body as forwarded to the child is charged too (re-serialized: up to 3 times as large); one that does not fit
      then is not sent (200 + -32003 under its id). Small requests (64 KiB at most, read and forwarded) are never
      charged nor refused. What a request holds goes back when it ends (AnyMethod).
    - a POST body too deep (over 64 levels), with too many elements (over 200,000) or not UTF-8 is refused before it
      is parsed (request_limits.too_complex: 200 + -32602 under its id when its head or tail shows it, else 413).
    - each refusal writes one WARNING per profile and situation a minute (body_budget's warn), never content or a
      token.

    HM-12 (multi-profile plan 9 Odoo row, 12.3 HM-12; DQ-05, DQ-40 ⑨ (a); contract 3.1, 4.1, section 9 #40, #41 and
    HM-12's rows; I11), only once the product is switched on; switched off, every answer stays as before:
    - stop_child: stops this profile's child, from then on until backend_changed relaunches it
      (ProfileRuntime.stop_child); a failure raises. Left out (no child of its own), nothing is stopped.
    - backend, backend/patch of an identity-bound product (products.identity_rebound: Odoo's url, database or username
      changed, a cleared connection included, while the token is active and a complete connection is saved) are done
      in this order: the old child is stopped (stop_child), one durable write holds the new connection, a new token
      and its history entry (ProductStore.rebind), the token change is published (token_access.committed(): every
      request of the old token ends, on both paths), then the child is started on what was written (backend_changed).
      200 {"saved": true, "token_rotated": true, "configuration": ...} with the new state's ETag, never the token. A
      stop that fails writes nothing (503 request denied). A write that fails, whatever it raises, answers today's 503
      state unavailable, and what is on disk decides the rest: the old token still there (the store refused the write,
      or it failed before the state file was replaced), nothing was written, the child is relaunched on the saved
      state and the old token is still served; else (the store poisoned once the state file was being replaced: 503
      until the add-on restarts; or a new token on disk) nothing is relaunched, since a new token may be on disk. A new
      child that does not start: shape D with "token_rotated": true. Each failure writes one WARNING (REBIND_WARNING).
      A first setup, a password change alone or a revoked token: as before (no token_rotated).
    - backend/patch that moves a stored URL to another origin without bringing the secrets that URL takes there (every
      product; backend_edit.new_origin_refused): 422 {"error":"request denied","detail":{"code":
      "CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}, after If-Match and backend_fixed, nothing written.

    HM-30 (multi-profile plan 5.5; contract 6; §8.8 #17), likewise only for a switched-on product:
    - reply_worker: this profile's turn on the add-on's reply worker (reply_worker.Lane). Every relayed JSON reply and
      every event with data of a relayed event stream is then processed there, not on the event loop: what it needs
      of the store (the state, the masks) is read on the loop when it is handed over, the worker runs only the pure
      steps (strict_json, the reply checks, redact_secrets, filter_list, json.dumps: relayed_reply and relayed_event,
      the very functions the loop runs when it is left out, with the worker's checkpoints, reply_worker.breathe, in the
      parser and between the steps; D1: json.dumps in pieces, reply_worker.encoded, the values let go of in pieces,
      redact_secrets breathing too; an event larger than WORKER_FRAME_BYTES is framed there as well, relayed_frame),
      and the answer is byte for byte the same. D3: each piece of the child's reply is read with one state read
      (chunks, TokenLease.run checked). A job the worker can no longer take
      (WorkerStopped) is answered as a reply the gateway cannot process (502; an event stream ends). Left out: every
      reply is processed on the loop, as before (no checkpoint).
    A switched-on product's dispatcher also gives a tools/call the check of the profile's answers not received yet,
    through the request's state (PENDING_REPLIES; profile_router.ProfileGate): no make_apps option. HM-30 review 2
    MF-2: the check runs before the slot and again once the call holds it, and a relayed JSON reply is charged
    (PENDING_CHARGE) before its slot is released.

    HM-13b (multi-profile plan 3.3; contract 1.2, 3.6; not gated): dormant_profiles, given only for a product that is
    not switched on but has profile data on disk: how many profile directories its boot guard left revoked
    (restore_lock.Outcome.dormant); the bootstrap carries it as "dormant_profiles" (the panel's "休眠帳號 N 個，權杖已撤銷",
    HM-13c). Left out (every installation without profile data): the bootstrap is as before, byte for byte."""
    if not SERVER_NAME.fullmatch(server_name) or instructions is not None and not (
            isinstance(instructions, str) and 0 < len(instructions) <= 4096):
        raise ValueError("invalid server identity")
    if authority is not None and (not isinstance(authority, AdminAuthority)
                                  or verify_admin is not None and verify_admin is not authority.verifier):
        raise ValueError("one administrator authority")
    if admin_slots is not None and not isinstance(admin_slots, asyncio.Semaphore):
        raise ValueError("invalid management slots")
    if admin_pipeline is not None and not callable(admin_pipeline):
        raise ValueError("invalid management pipeline")
    if token_access is not None and not isinstance(token_access, TokenAccess):
        raise ValueError("invalid token access")
    if token_access is not None and token_access.store is not store:
        raise ValueError("token access of another store")
    if mutation_lock is not None and not isinstance(mutation_lock, asyncio.Lock):
        raise ValueError("invalid mutation lock")
    if profile_view is not None:
        if not callable(profile_view):
            raise ValueError("invalid profile echo")
        profile_echo(profile_view())
    if forward_slots is not None and (type(forward_slots) is not int or forward_slots < 1):
        raise ValueError("invalid forwarding slots")
    if slot_busy is not None and not isinstance(slot_busy, SlotBusy):
        raise ValueError("invalid busy answer")
    if reply_secrets is not None and not callable(reply_secrets):
        raise ValueError("invalid reply secrets")
    if child_blocked is not None and not callable(child_blocked):
        raise ValueError("invalid blocked reason")
    if default_endpoint is not None and not callable(default_endpoint):
        raise ValueError("invalid default endpoint")
    if bootstrap_fields is not None and (not callable(bootstrap_fields) or profile_view is None):
        raise ValueError("invalid bootstrap fields")
    if body_budget is not None and not isinstance(body_budget, request_budget.Share):
        raise ValueError("invalid request budget")
    if stop_child is not None and not callable(stop_child):
        raise ValueError("invalid child stop")
    if reply_worker is not None and not callable(getattr(reply_worker, "run", None)):
        raise ValueError("invalid reply worker")
    if dormant_profiles is not None and (type(dormant_profiles) is not int or dormant_profiles < 0
                                         or profile_view is not None):
        raise ValueError("invalid dormant profiles")
    n8n_request_bounds = getattr(store, "product", None) == "n8n"
    # HM-31: the add-on's request body budget (this profile's share) and the single-request ceiling it is charged up to
    budget_share = request_budget.own_share(getattr(store, "product", None)) if body_budget is None else body_budget
    body_cap = N8N_MAX_REQUEST if n8n_request_bounds else MAX_REQUEST
    idle_seconds = budget_share.budget.limits.idle_seconds
    management = management or ManagementOptions()
    if listing is not None:
        listing = copy.deepcopy(list(listing))
        if not all(isinstance(tool, dict) and isinstance(tool.get("name"), str) for tool in listing):
            raise ValueError("invalid tool listing")
    if availability is None:
        def availability():
            return {"child": "running", "ready": True, "backend": "unknown", "reason": None}
    local_sessions = OrderedDict()  # 0.2.2: session id -> last use (time.monotonic())
    redact.install()  # 0.1.12: a request path may now carry the token; no log record may show it
    mutation_lock = asyncio.Lock() if mutation_lock is None else mutation_lock
    token_access = TokenAccess(store) if token_access is None else token_access
    configuration = configuration or ConfigurationState(store)
    operations = OperationJournal(store.path)
    slots = asyncio.Semaphore(FORWARD_SLOTS if forward_slots is None else forward_slots)
    # HM-14: a switched-on profile's two lanes (the ordinary slots and the reserved ones); switched off: slots, as before
    lanes = None if slot_busy is None else {
        ORDINARY_LANE: Lane(ORDINARY_LANE, FORWARD_SLOTS if forward_slots is None else forward_slots),
        RESERVED_LANE: Lane(RESERVED_LANE, slot_busy.reserve)}
    admin_slots = asyncio.Semaphore(ADMIN_SLOTS) if admin_slots is None else admin_slots

    def masks(state):
        """The credentials no answer of this profile may carry: its own (redact.secret_values) and, once a product is
        switched on, every token and child token the add-on holds (reply_secrets; HM-08). Longest first."""
        own = redact.secret_values(state)
        if reply_secrets is None:
            return own
        return tuple(sorted(set(own) | others(), key=len, reverse=True))

    def others():
        return {value for value in reply_secrets() if isinstance(value, str) and len(value) >= redact.MIN_SECRET}

    def relayed_reply(raw, ident, method, state_of, masks_of, checkpoint=None, parsed=None):
        """A relayed JSON reply (HM-30: the same steps on the loop and on the reply worker): raw parsed (strict JSON),
        the reply to this request (exactly one of result and error, under the request's id: else ValueError), masked
        with masks_of(state) and filtered on state, state_of()'s answer (read after the parse, as before). checkpoint
        (the reply worker's breathe) is called in the parser and between the steps; on the loop there is none. parsed
        (D1, the worker's): a list the parsed value is put in, for the worker to let go of it in pieces (released)."""
        # D1: the worker parses the bytes it was handed as they are (json.loads takes a bytearray as it takes bytes): no
        # copy of an 8 MiB reply in one call first
        value = strict_json(bytes(raw)) if checkpoint is None else strict_json(raw, checkpoint=checkpoint)
        if parsed is not None:
            parsed.append(value)
        if not (one_reply(value) and same_id(value.get("id"), ident)):
            raise ValueError("not this request's reply")
        current = state_of()
        if checkpoint is not None:
            checkpoint()
        # 0.2.0: backend errors carry their own text; no credential the add-on holds leaves
        if checkpoint is None:
            return filter_list(redact.redact_secrets(gateway_reply(value, method), masks_of(current)), tools, current)
        return filter_list(redact.redact_secrets(gateway_reply(value, method), masks_of(current), checkpoint), tools,
                           current)  # D1: the worker breathes while it masks

    def relayed_event(payload, request, state_of, masks_of, checkpoint=None, head=None):
        """One SSE event's data as a stream relays it (HM-30: the same steps on the loop and on the reply worker).
        request is the (id, method) of the POST the stream answers, None for a GET stream. SKIP_EVENT: not relayed;
        END_STREAM: the stream ends there; else (the data line, whether it is the reply, which ends the stream).
        ValueError, ConfigError (state_of), RecursionError: the stream ends there too. checkpoint: as relayed_reply.
        head (D1, the worker's for a large event, relayed_frame): the event's lines before its data line; the reply's
        line is then the whole event (head, the data line, its end), made in one copy."""
        value = strict_json(payload) if checkpoint is None else strict_json(payload, checkpoint=checkpoint)
        if not isinstance(value, dict):
            return END_STREAM  # a batch: never sent by the gateway, never filtered element by element
        if "method" in value:
            if "id" in value or value["method"] != "notifications/tools/list_changed":
                return SKIP_EVENT  # a server-to-client request (elicitation, sampling, roots: the client could not
                # answer it through the gateway) or a notification other than 0.1.4's one
            return LIST_CHANGED, False
        if "result" not in value and "error" not in value:
            return SKIP_EVENT  # not a reply: never relayed as one
        if not one_reply(value):
            return END_STREAM  # both result and error: malformed, never relayed, never guessed
        if request is None or not same_id(value.get("id"), request[0]):
            # 0.1.5: a reply to another request (the TS client reports it with its text). A GET stream carries no
            # reply at all (R1 #2): MCP allows one only when resuming a stream, and no pinned child keeps an event store.
            return SKIP_EVENT
        if checkpoint is not None:
            checkpoint()
        # 0.2.0: backend errors carry their own text; no credential the add-on holds leaves
        if checkpoint is None:
            checked = redact.redact_secrets(gateway_reply(value, request[1]), masks_of(state_of()))
        else:
            checked = redact.redact_secrets(gateway_reply(value, request[1]), masks_of(state_of()), checkpoint)
        if isinstance(checked.get("result"), dict) and {"tools", "capabilities"} & checked["result"].keys():
            checked = filter_list(checked, tools, state_of())
        if checkpoint is None:
            return b"data: " + json.dumps(checked, separators=(",", ":")).encode(), True
        checkpoint()
        # D1: the same bytes, in pieces; the parsed and the masked value let go of in pieces once encoded
        return encoded(checked, checkpoint, prefix=(head or b"") + b"data: ",
                       suffix=b"\n\n" if head is not None else b"", release=releasable(checked), twin=value), True

    def prepared():
        """HM-30: what a job of the reply worker needs of the store, read on the loop when the job is handed over (the
        worker never reads it): the state and its masks, or the ConfigError the job raises where the loop's own read
        of the state would have raised it (after the reply's checks)."""
        try:
            current = store.load()
        except ConfigError as error:
            return error
        return current, masks(current)

    def prepared_reads(found):
        """state_of and masks_of for what prepared() found."""
        def state_of():
            if isinstance(found, ConfigError):
                raise found
            return found[0]

        def masks_of(_):
            return found[1]
        return state_of, masks_of

    def releasable(value):
        """D1: whether the worker may let go of a reply's value in pieces: everything in it is the gateway's own copy
        (strict_json's and redact_secrets' objects), unless filter_list rebuilt a tool list in it (its tools hold the
        policy's own schemas)."""
        result = value.get("result")
        return not (isinstance(result, dict) and "tools" in result)

    def worker_reply(raw, ident, method, found):
        """HM-30, on the reply worker: relayed_reply (with the worker's checkpoints), then json_reply's serialization
        (D1: reply_worker.encoded, the same bytes in pieces; the parsed and the masked value let go of in pieces)."""
        parsed = []
        value = relayed_reply(raw, ident, method, *prepared_reads(found), checkpoint=breathe, parsed=parsed)
        breathe()
        return encoded(value, breathe, release=releasable(value), twin=parsed[0])

    def worker_event(payload, request, found):
        """HM-30, on the reply worker: relayed_event (with the worker's checkpoints)."""
        return relayed_event(payload, request, *prepared_reads(found), checkpoint=breathe)

    def relayed_frame(frame, request, state_of, masks_of, checkpoint=None):
        """HM-30 D1, on the reply worker: one SSE event from its frame (the boundary removed) to the bytes it is relayed
        as, the steps stream() takes on the loop, in their order (sse_frame, sse_data, an empty event kept empty,
        relayed_event, the kept lines and the data line joined): END_STREAM, SKIP_EVENT, or (the event, None when it
        has no line; whether it is the reply). ValueError, ConfigError, RecursionError: as relayed_event's."""
        parsed = sse_frame(frame)
        if parsed is None:
            return END_STREAM
        kept, data_lines = parsed
        payload = sse_data(data_lines)
        final = False
        if data_lines and not payload.strip():
            data_lines = [b"data:"]  # an empty (priming) event stays empty
        elif data_lines:
            head = b"\n".join(kept) + b"\n" if kept else b""
            outcome = relayed_event(payload, request, state_of, masks_of, checkpoint, head=head)
            if outcome == END_STREAM or outcome == SKIP_EVENT:
                return outcome
            line, final = outcome
            if final:
                return line, final  # the whole event already (relayed_event head): the same bytes, one copy
            data_lines = [line]
        lines = kept + data_lines
        return (b"\n".join(lines) + b"\n\n" if lines else None), final

    def worker_frame(pending, end, request, found):
        """HM-30 D1, on the reply worker: a large event, its frame pending's first `end` bytes (the loop leaves pending
        alone until the job ended), copied out and relayed here (relayed_frame, with the worker's checkpoints)."""
        frame = bytes(memoryview(pending)[:end])
        breathe()
        return relayed_frame(frame, request, *prepared_reads(found), checkpoint=breathe)

    def snapshot():
        return health() if health else {"management": "alive", "child": {"state": "not_started", "transport_ready": False}, "backend": "unconfigured"}

    def child_generation():
        """HM-14: the child generation a request goes to now, its Supervisor's start count (the health monitor's child
        view: every spawn counts one); None without a health monitor (nothing to compare)."""
        if health is None:
            return None
        starts = (snapshot().get("child") or {}).get("starts")
        return starts if type(starts) is int else None

    def child_runs(generation):
        """HM-14: whether that generation is still the one running (not exited, stopped or replaced)."""
        current = snapshot().get("child") or {}
        return current.get("starts") == generation and current.get("state") == "running"

    async def child_stopped(generation):
        """HM-14 (contract 2.5; PaaS proxy._child_stopped): whether the child generation a request went to has stopped,
        once its connection broke: at once when it has, else after CHILD_EXIT_GRACE_SECONDS of looking (the broken
        connection may come a moment before the Supervisor sees the exit). No generation to compare: stopped (the
        established wording)."""
        if generation is None:
            return True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CHILD_EXIT_GRACE_SECONDS
        while child_runs(generation):
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(.02)
        return True

    def interruption_text(stopped, generation):
        """HM-14 (contract 2.5), read right after child_stopped, with no await between (the state the stop left): the
        -32004 text. The child still runs: CHILD_CONNECTION_TEXT. It stopped: CHILD_STOPPED_TEXT ("it restarts
        automatically", PaaS's) only while it comes back by itself (CHILD_RESTARTING_STATES, HM-09's watchdog), else
        CHILD_HALTED_TEXT (blocked, failed, stopped or not configured: nothing restarts it now). No generation to
        compare: the established wording."""
        if not stopped:
            return CHILD_CONNECTION_TEXT
        if generation is None:
            return CHILD_STOPPED_TEXT
        state = (snapshot().get("child") or {}).get("state")
        return CHILD_STOPPED_TEXT if state in CHILD_RESTARTING_STATES else CHILD_HALTED_TEXT

    async def interrupted_answer(owner, request, message, error):
        """HM-14 (switched on; contract 2.5): the child's connection broke before the answer's headers: 502 with the
        gateway's own -32004 error, under the request's id when it has one (null for a notification, a GET, a DELETE),
        its text by the cause, and the profile's WARNING (the HTTP method and the error's class, never a path, token or
        body). A session the child opened for an initialize is ended only while the child still runs."""
        stopped = await child_stopped(owner.generation)
        text = interruption_text(stopped, owner.generation)
        if stopped:
            owner.end_session = None  # the session ended with its child
        await owner.close()
        slot_busy.interrupted(request.method, type(error).__name__, stopped)
        ident = request_id(message) if request.method == "POST" else None
        return json_reply({"jsonrpc": "2.0", "id": ident, "error": {"code": CHILD_INTERRUPTED, "message": text}},
                          502, {"Cache-Control": "no-store"})

    def capabilities(state, catalog):
        return capability_snapshot(management, state, snapshot(), catalog, can_test=backend_check is not None,
                                   can_restart=restart_child is not None, logs=diagnostics is not None)

    def profile_name():
        """How this profile's log lines name it (profiles.log_id): the echo's id, 'default' without an echo."""
        return log_id(profile_echo(profile_view())["id"] if profile_view is not None else "default")

    async def relaunch_saved(state):
        """HM-12: the child relaunched on the saved state after a failed identity change: the outcome's words."""
        if backend_changed is None:
            return "it has no child to relaunch"
        try:
            await backend_changed(state)
        except Exception:
            return "its child could not be relaunched"
        return "its child was relaunched on the saved connection"

    async def rebind_identity(state, changes, headers, committed):
        """HM-12 (see make_apps): a switched-on profile's backend saved under another identity: stop, one write,
        publish, start. Called after every check of step 11 and holding the profile's mutation_lock throughout."""
        committed.set()  # the transition is owned from here: a client gone cancels none of its steps
        try:
            if stop_child is not None:
                await stop_child()
        except Exception:
            outcome = await relaunch_saved(state)
            logger.warning("%s%s was not saved: its child could not be stopped; %s", REBIND_WARNING, profile_name(),
                           outcome)
            raise BadRequest(503) from None
        try:
            updated = store.rebind(changes, secrets.token_urlsafe(32))
        except Exception:
            # Whatever was raised, what is on disk decides (HM-12 review S-5). The old token still on disk: nothing was
            # written (the store refused it, the new file could not be made, or it raised before writing), so the old
            # child is relaunched on the saved state and the old token is still served. A store poisoned once the state
            # file was being replaced, or a new token on disk although the write raised (a failure after the rename
            # that left the store usable): a new token may be on disk, so no child runs on the old credentials (UC-21);
            # the store stays as it is (a poisoned one fails closed) and the add-on's restart reads what is on disk.
            try:
                kept = store.load().token == state.token
            except ConfigError:
                kept = False
            if kept:
                outcome = await relaunch_saved(state)
                logger.warning("%s%s was not saved: the new state could not be written; %s", REBIND_WARNING,
                               profile_name(), outcome)
            else:
                logger.warning("%s%s failed while its state file was being replaced: whether it was saved is unknown, "
                               "so its child stays stopped until the add-on restarts and reads the state on disk",
                               REBIND_WARNING, profile_name())
            raise ConfigError("state unavailable") from None  # today's fixed 503, whatever was raised
        token_access.committed()
        headers['ETag'] = configuration.etag(updated)
        body = {"saved": True, "token_rotated": True}
        if backend_changed:
            try:
                await backend_changed(updated)
            except Exception:
                # Saved: the new token is the profile's; the old child (old credentials) is never started again.
                return JSONResponse({**body, 'detail': {'code': 'config_apply_failed'},
                                     'configuration': configuration.snapshot(updated)}, status_code=503,
                                    headers=headers)
        return JSONResponse({**body, 'configuration': configuration.snapshot(updated)}, headers=headers)

    authority = AdminAuthority(verify_admin) if authority is None else authority
    admin_identity = authority.identity
    final_role = authority.verify

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
            if name in ("backend", "backend/patch", "policy", "endpoint", "odoo/write-switches", "n8n/session", odoo_methods.ROUTE) and request.method == "PUT":
                try:
                    if not isinstance(value, dict):
                        raise ValueError()
                    if name == "backend":
                        if getattr(state, 'product', 'n8n') == 'n8n':
                            # 0.2.1: optional mcp_access_token (n8n's instance-level MCP key); the whole set is
                            # replaced, so leaving it out (or clearing) removes a stored token.
                            if set(value) not in ({"url", "key"}, {"url", "key", "mcp_access_token"}):
                                raise ValueError()
                            changes = dict(backend_url=value["url"], backend_key=value["key"])
                            if hasattr(state, "mcp_access_token"):
                                token = value.get("mcp_access_token")
                                changes["mcp_access_token"] = None if value["url"] is None else token
                            elif value.get("mcp_access_token") is not None:
                                raise ValueError()
                        else:
                            if set(value) != {"connection"}:
                                raise ValueError()
                            changes = value
                    elif name == "backend/patch":
                        from .backend_edit import changes as connection_changes
                        if not hasattr(state, 'product'):
                            raise ValueError()
                        changes = connection_changes(state, value)
                    elif name == 'n8n/session':
                        if getattr(state, 'product', None) != 'n8n' or set(value) != {'n8n_session'} or value['n8n_session'] is None:
                            raise ValueError()
                        changes = value
                    elif name == "endpoint":
                        if set(value) != {"endpoint"}:
                            raise ValueError()
                        changes = value
                    elif name == odoo_methods.ROUTE:
                        changes = odoo_methods.changes(state, value)
                    elif name == 'odoo/write-switches':
                        # Unreleased (0.4.12 line): null is a field the model accepts ("not saved") but this route cannot express; it
                        # reached the commit and answered 503 "state unavailable" instead of 400 (stage-C finding C3), as n8n/session
                        # above has always refused it.
                        if (getattr(state, 'product', None) != 'odoo' or set(value) != {'odoo_write_switches'}
                                or value['odoo_write_switches'] is None):
                            raise ValueError()
                        changes = value
                    else:
                        if (not {"writes_enabled", "disabled"} <= set(value)
                                or set(value) - {"writes_enabled", "disabled", "enabled_write_tools", "denied_operations"}
                                or not isinstance(value["disabled"], list)
                                or any(not isinstance(t, str) or t not in tools for t in value["disabled"])):
                            raise ValueError()
                        changes = value
                    # Validate without writing. Store.update revalidates on commit.
                    candidate = type(state).model_validate({**state.model_dump(), **changes})
                    if name in ("backend", "backend/patch"):
                        from .products import check_saved_destinations
                        check_saved_destinations(candidate, state)
                    if name == 'policy' and 'denied_operations' in changes:
                        validate_operation_denies(candidate.denied_operations, tools, state)
                except ValueError:
                    raise BadRequest() from None
            if peer_disconnected.is_set():
                raise BadRequest(403)
            await final_role(user)
            if peer_disconnected.is_set():
                raise BadRequest(403)
            # No awaited work between this final decision and disclosure/commit.
            headers['ETag'] = configuration.etag(state)
            notice_action = name in ('owner-defaults/restore', 'owner-defaults/dismiss') and request.method == 'POST'
            operation_kind = OPERATION_KINDS.get(name) if request.method == 'POST' else None
            operation_id = None
            operation_data = None
            if changes is not None or notice_action or operation_kind:
                matches = request.headers.getlist('if-match')
                if not matches:
                    raise BadRequest(428, {'code': 'config_revision_required'})
                if len(matches) != 1 or not re.fullmatch(r'"c1-[0-9a-f]{64}"', matches[0]):
                    return JSONResponse({'detail': {'code': 'config_conflict'}}, status_code=409, headers=headers)
                if operation_kind:
                    ids = request.headers.getlist('idempotency-key')
                    if not ids:
                        raise BadRequest(428, {'code': 'operation_id_required'})
                    if len(ids) != 1:
                        raise BadRequest(400, {'code': 'operation_id_invalid'})
                    operation_id = ids[0]
                    operation_data, prior, fingerprint = operations.inspect(operation_id, operation_kind, user)
                    if prior:
                        public = operations.public(operation_id, prior, replayed=True)
                        if prior['state'] != 'completed':
                            raise BadRequest(409, {'code': 'operation_outcome_unknown', 'operation': public})
                        # Receipt replay is an authenticated observation, not a new
                        # write against an obsolete form or a rotated token.
                        return JSONResponse({**OPERATION_RESULTS[operation_kind], 'operation': public,
                                             'configuration': configuration.snapshot(state)}, headers=headers)
                if matches[0] != headers['ETag']:
                    return JSONResponse({'detail': {'code': 'config_conflict'}}, status_code=409, headers=headers)

            def begin_operation():
                operations.begin(operation_id, operation_data, operation_kind, user, fingerprint)
                # Intent is now durable; own the effect through disconnect, as
                # with an already persisted configuration mutation.
                committed.set()

            def finish_operation(updated):
                try:
                    public = operations.complete(operation_id, operation_data)
                except (OSError, ValueError):
                    raise BadRequest(409, {'code': 'operation_outcome_unknown'}) from None
                headers['ETag'] = configuration.etag(updated)
                return {**OPERATION_RESULTS[operation_kind], 'operation': public,
                        'configuration': configuration.snapshot(updated)}

            if name.startswith('operations/') and request.method == 'GET':
                return JSONResponse(operations.query(name[len('operations/'):], user), headers=headers)
            if name == "__ui__" and hasattr(request.state, "ui_path") and request.method in ("GET", "HEAD"):
                return ui.response(request.state.ui_path, base)
            if name == "bootstrap" and request.method == "GET":
                from .odoo_switch_listing import for_state as listing_for_state
                catalog = tool_catalog(tools, listing_for_state(listing, state), None, state)
                schemas = {item["name"]: item.get("inputSchema") for item in catalog["items"]}
                # Owner decision 2026-10-27: the one-time all-on migration's notice (only on a state it wrote). HM-10
                # (FM-08): never an additional profile's, whatever its directory holds.
                notice = owner_defaults.view(state, store.directory) if default_endpoint is None else None
                from .backend_edit import view as connection_view
                edit_view = connection_view(state) if hasattr(state, 'product') else None
                return JSONResponse({"base_path": base, "api_base": base + "/api", "csrf": csrf,
                    "operation_contract": {"version": 1, "server_time_ms": int(time.time() * 1000),
                                           "retention_ms": TTL_MS},
                    **({"owner_defaults": notice} if notice is not None else {}),
                    **odoo_methods.bootstrap(state),
                    "configuration": configuration.snapshot(state),
                    # HM-10 (DQ-13): an additional profile shows the add-on's one endpoint, the default profile's.
                    "endpoint": state.endpoint if default_endpoint is None else default_endpoint(),
                    "backend_url": edit_view['values']['url']
                    if edit_view and getattr(state, 'product', None) == 'n8n' else state.backend_url,
                    "backend_key_set": state.backend_key is not None, "token_active": state.token is not None,
                    "token_masked": masked_token(state.token),
                    "token_history": [entry.model_dump() for entry in (getattr(state, 'token_history', None) or [])],
                    "mcp_access_token_set": getattr(state, "mcp_access_token", None) is not None,
                    "product": getattr(state, 'product', 'n8n'),
                    **({'odoo_write_switches': state.effective_odoo_write_switches.model_dump(),
                        'odoo_write_switches_source': 'saved' if state.odoo_write_switches is not None else 'legacy_all_on'}
                       if getattr(state, 'product', None) == 'odoo' else {}),
                    **({'backend_edit': edit_view} if edit_view is not None else {}),
                    **({'n8n_session': state.effective_n8n_session.model_dump(),
                        'n8n_session_source': 'saved' if state.n8n_session is not None else 'legacy_default',
                        'n8n_session_effective_minutes': state.effective_n8n_session.timeout_minutes}
                       if getattr(state, 'product', None) == 'n8n' else {}),
                    "connection_configured": getattr(state, 'configured', bool(state.backend_url and state.backend_key)),
                    "writes_enabled": state.writes_enabled, "disabled": state.disabled,
                    "policy_contract": "woow-v3-exact-grants",
                    "enabled_write_tools": getattr(state, 'enabled_write_tools', []),
                    **({"denied_operations": state.denied_operations} if hasattr(state, 'denied_operations') else {}),
                    "capabilities": capabilities(state, catalog),
                    "tools": {k: {"write": v.write, "write_grants": v.grants(k),
                                  "operation_parameter": v.selector, "legacy_write": v.legacy_write,
                                  "default_operation": v.default_operation,
                                  "operations": [{"name": op, "write": op in v.write_operations} for op in v.operations],
                                  "inputSchema": schemas.get(k) or v.arguments.model_json_schema()} for k, v in tools.items()}, "health": snapshot(),
                    **({"dormant_profiles": dormant_profiles} if dormant_profiles is not None else {})}, headers=headers)
            if name == "configuration" and request.method == "GET":
                return JSONResponse({'configuration': configuration.snapshot(state)}, headers=headers)
            if name == "capabilities" and request.method == "GET":
                before = snapshot().get("child")
                observed = await observe_tools(child, child_url, state)
                await final_role(user)  # the probe awaited work; recheck before disclosure
                # Include exits/replacements during the final awaited role lookup.
                if before != snapshot().get("child"):
                    observed = None
                from .odoo_switch_listing import for_state as listing_for_state
                return JSONResponse(capabilities(state, tool_catalog(tools, listing_for_state(listing, state), observed, state)), headers=headers)
            if name == "backend/test" and request.method == "POST":
                if backend_check is None:
                    return JSONResponse({"error": "unsupported"}, status_code=409, headers=headers)
                try:
                    async with asyncio.timeout(20):
                        result = await backend_check(state)
                except Exception:
                    return JSONResponse({"error": "backend_check_failed"}, status_code=503, headers=headers)
                await final_role(user)
                return JSONResponse(redact.redact_secrets(result, masks(state)), headers=headers)
            if name == "child/restart" and request.method == "POST":
                if restart_child is None:
                    return JSONResponse({"error": "unsupported"}, status_code=409, headers=headers)
                # Same ownership transfer as a committed backend update. Disconnect
                # cannot abandon stop/reap/restart or release the mutation lock early.
                begin_operation()
                try:
                    await restart_child(state)
                except Exception:
                    raise BadRequest(409, {'code': 'operation_outcome_unknown'}) from None
                answer = {**finish_operation(state), "accepted": True, "health": snapshot()}
                if child_blocked is not None:
                    answer["blocked_reason"] = child_blocked()  # HM-09
                return JSONResponse(answer, status_code=202, headers=headers)
            if name == "diagnostics" and request.method == "GET":
                if diagnostics is None:
                    return JSONResponse({"error": "unsupported"}, status_code=409, headers=headers)
                return JSONResponse(redact.redact_secrets(diagnostics(), masks(state)), headers=headers)
            if name == "token/reveal" and request.method == "POST":
                return JSONResponse({"token": store.load().token}, headers=headers)
            if name == "token/rotate" and request.method == "POST":
                begin_operation()
                new_token = secrets.token_urlsafe(32)
                try:
                    updated = (store.change_token(new_token, action='rotate')[0] if hasattr(store, 'change_token')
                               else store.update(token=new_token))
                except (OSError, ConfigError):
                    raise BadRequest(409, {'code': 'operation_outcome_unknown'}) from None
                token_access.committed()
                return JSONResponse({**finish_operation(updated), "token": updated.token}, headers=headers)
            if name == "token/revoke" and request.method == "POST":
                begin_operation()
                try:
                    if hasattr(store, 'change_token'):
                        updated, changed = store.change_token(None, action='revoke')
                    else:
                        changed = state.token is not None
                        updated = store.update(token=None) if changed else state
                except (OSError, ConfigError):
                    raise BadRequest(409, {'code': 'operation_outcome_unknown'}) from None
                if changed:
                    token_access.committed()
                return JSONResponse(finish_operation(updated), headers=headers)
            if notice_action:
                # Owner decision 2026-10-27: restore the faithful pre-upgrade limits, or keep the defaults (dismiss).
                restoring = name == 'owner-defaults/restore'
                try:
                    if default_endpoint is not None:
                        raise owner_defaults.Unavailable()  # HM-10 (FM-08): an additional profile has no notice
                    updated = (owner_defaults.restore if restoring else owner_defaults.dismiss)(store)
                except owner_defaults.Unavailable:
                    return JSONResponse({'error': 'owner_defaults_unavailable',
                                         'detail': {'code': 'owner_defaults_unavailable'}}, status_code=409, headers=headers)
                committed.set()
                headers['ETag'] = configuration.etag(updated)
                body = {'saved': True, 'configuration': configuration.snapshot(updated),
                        'owner_defaults': owner_defaults.view(updated, store.directory)}
                if restoring and getattr(state, 'product', 'n8n') in ('emqx', 'litellm', 'nextcloud', 'headscale') and backend_changed:
                    # As a saved policy: these children are launched with the policy (READONLY, DISABLED_TOOLS).
                    try:
                        await backend_changed(updated)
                    except Exception:
                        return JSONResponse({**body, 'detail': {'code': 'config_apply_failed'}}, status_code=503,
                                            headers=headers)
                return JSONResponse(body, headers=headers)
            if changes is not None:
                if name in ("backend", "backend/patch") and not management.backend_can_edit:
                    return JSONResponse({"error": "backend_fixed"}, status_code=409, headers=headers)
                if name == "endpoint" and default_endpoint is not None:
                    # HM-10 (DQ-13): the add-on has one endpoint, stored in the default profile's state.
                    raise BadRequest(409, {"code": "endpoint_global"})
                if name in ("backend", "backend/patch"):
                    from .backend_edit import new_origin_refused
                    from .products import identity_rebound
                    if name == "backend/patch" and new_origin_refused(state, candidate, value):
                        # HM-12 (DQ-40 ⑨): a stored credential never follows a URL to another server unasked
                        raise BadRequest(422, {"code": NEW_ORIGIN_SECRET})
                    if identity_rebound(state, candidate):
                        return await rebind_identity(state, changes, headers, committed)
                updated = store.update(**changes)
                # No yield between durable commit and lifecycle ownership transfer.
                # An authorized mutation is not undone by losing its HTTP caller.
                committed.set()
                headers['ETag'] = configuration.etag(updated)
                if (name in ('backend', 'backend/patch', 'odoo/write-switches', 'n8n/session', odoo_methods.ROUTE) or (name == "policy" and getattr(state, 'product', 'n8n') in ('emqx', 'litellm', 'nextcloud', 'headscale'))) and backend_changed:
                    try:
                        await backend_changed(updated)
                    except Exception:
                        return JSONResponse({'saved': True, 'detail': {'code': 'config_apply_failed'},
                                             'configuration': configuration.snapshot(updated)}, status_code=503, headers=headers)
                return JSONResponse({"saved": True, 'configuration': configuration.snapshot(updated)}, headers=headers)
            return Response(status_code=404)
        finally:
            mutation_lock.release()

    async def admin_api(request):
        # HM-10: steps 1 to 4 are management_exchange (extracted from here, unchanged); its step: this profile's action.
        name = request.path_params["operation"]
        return await management_exchange(
            request, admin_identity, admin_slots,
            lambda request: management_value(request, name in JSON_OPERATIONS and request.method == "PUT"),
            admin_action)

    async def admin_page(request):
        # The same admission, bounded body, lock, fresh role and disconnect
        # ownership as the API apply to every asset; no unbounded WS fan-out.
        _, operation = management_operation(request, admin_identity)  # HM-10: extracted, unchanged
        if operation == "__ui__" and request.method not in ("GET", "HEAD"):
            raise BadRequest(404)
        if admin_pipeline is None:
            response = await admin_api(request)  # its only answer is the action's (action.result())
            return response if profile_view is None else echoed(response, operation)
        return await admin_pipeline(request, profile_action)  # HM-05: the shared pipeline (see make_apps)

    async def profile_action(request, user, base, csrf, value, peer_disconnected, committed):
        """HM-05: this profile's action as the shared pipeline gets it: admin_action, its answer with the echo (an answer
        the pipeline gives itself never carries this profile's echo). HM-10: the switched-on dispatcher calls it
        (admin.state.profile_action) once it has chosen this profile."""
        response = await admin_action(request, user, base, csrf, value, peer_disconnected, committed)
        return response if profile_view is None else echoed(response, request.path_params["operation"])

    def echoed(response, name):
        """HM-05: this profile's echo (profile_view) in a JSON object its action answered: the bootstrap gets "profile"
        (id, label, is_default) and "profiles_supported": true (HM-10: then bootstrap_fields()), any other answer
        "profile": {"id"}. The action answers only after its final role check; a refusal (an exception: 403, 428 ...)
        gets no echo from error_handler, so a caller who is not an administrator learns nothing about the profile
        (invariant I10). Status and headers stay: HM-10 (HM-05 review) keeps every header the action set, in its order
        and with a repeated name repeated (a dict merged them), then the new body's length and type."""
        if not isinstance(response, JSONResponse):
            return response
        content = json.loads(response.body)
        if not isinstance(content, dict):
            return response
        view = profile_echo(profile_view())
        if name == "bootstrap":
            content.update(profile=view, profiles_supported=True)
            if bootstrap_fields is not None:
                content.update(bootstrap_fields())
        else:
            content["profile"] = {"id": view["id"]}
        result = JSONResponse(content, status_code=response.status_code)
        result.raw_headers = [pair for pair in response.raw_headers
                              if pair[0] not in (b"content-length", b"content-type")] + result.raw_headers
        return result

    def still_authorized(token):
        try:
            current = store.load().token
            return current is not None and hmac.compare_digest(current, token)
        except ConfigError:
            return False

    async def chunks(owner, lease, seconds=None):
        """Bound total bytes/time (seconds, default STREAM_SECONDS); poll revocation even while upstream is idle.

        HM-30 D3 (contract 6), only for a switched-on product (reply_worker given): each piece is read under the lease
        without checking it again first (TokenLease.run checked): the check that ended the lease's previous operation
        (the child's headers, then each piece) is the one before the next piece, and whatever changed since stops the
        piece before it is used (one state read a piece, not three). Left out, as before."""
        iterator = owner.iterator = owner.response.aiter_bytes()
        total = 0
        try:
            async with asyncio.timeout(seconds or STREAM_SECONDS):
                while True:
                    async def read_one():
                        owner.reader = asyncio.create_task(anext(iterator))
                        return await owner.reader
                    try:
                        chunk = await (lease.run(read_one) if reply_worker is None else
                                       lease.run(read_one, checked=True))
                    except StopAsyncIteration:
                        return
                    total += len(chunk)
                    if total > MAX_RESPONSE:
                        owner.overflowed = True
                        return
                    yield chunk
        except (httpx.HTTPError, TimeoutError) as error:
            if interrupted(error):
                owner.interrupted = error  # HM-14: read by a switched-on profile only (contract 2.5)
            return

    async def end_session(child_token, session):
        """0.1.6 (R2 review): end a session the child opened for an initialize whose answer withholds its id (401,
        502, 503, a refused child status, a state error); otherwise it stays open until the child's idle reaping (n8n:
        10 minutes, with 20 sessions shared by all clients; the pinned Python SDK children kept it until they restarted
        until 0.1.7, and from 0.1.8 end it after 30 idle minutes, apps/runtime/session_idle.py). One DELETE with the
        gateway's own headers and none of the client's; best effort and bounded: nothing of the child's reply is read or
        relayed (it is streamed and closed unread: a body may be large or never end, and a reply left open would keep its
        pooled connection) and no Exception escapes, since the client's answer is already decided and must not change."""
        try:
            async with asyncio.timeout(SESSION_END_SECONDS):
                async with child.stream("DELETE", child_url, follow_redirects=False, headers={
                        "Authorization": "Bearer " + child_token, "Accept": "application/json, text/event-stream",
                        "Accept-Encoding": "identity", "mcp-session-id": session}):
                    pass  # the child's status, headers and body are never read
        except Exception:
            pass

    async def initialize_reply(owner, lease, is_sse, ident):
        """Read the child's reply to initialize: (outcome, message, SSE frame lines other than data).

        outcome is "ok", "missing" or "invalid". Stops at the JSON-RPC response with the request's id
        (an SSE stream may stay open after it). "missing": the child answered 200 and ended without a
        reply, e.g. its per-session lifespan could not reach the backend (Odoo Manage, 0.1.1 HA test),
        so the session id it sent is dead.
        """
        def reply(value):
            """"ok" for this request's reply, "invalid" when it has both result and error (0.1.4), None for another
            message (a request, a notification, another id, or neither result nor error: skipped as in 0.1.2)."""
            if "method" in value or not same_id(value.get("id"), ident) or not ("result" in value or "error" in value):
                return None
            return "ok" if one_reply(value) else "invalid"

        pending = bytearray()
        reader = chunks(owner, lease)
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
                    payload = sse_data(data_lines)
                    if not payload.strip():
                        continue  # no data, or an empty priming event (MCP 2025-11-25 resumability)
                    try:
                        value = strict_json(payload)
                    except (ValueError, RecursionError):
                        return "invalid", None, None
                    if not isinstance(value, dict):
                        return "invalid", None, None  # a batch: the gateway never sends one
                    outcome = reply(value)
                    if outcome == "ok":
                        return "ok", value, [line for line in kept if not line.startswith(b":")]
                    if outcome == "invalid":
                        return "invalid", None, None
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
        outcome = reply(value)
        return ("ok", value, None) if outcome == "ok" else ("invalid" if outcome else "missing", None, None)

    async def stream(owner, lease, request=None, seconds=None):
        """Relay a child's SSE 200 (the only stream the caller hands over). request is the (id, method) of the POST
        this stream answers, None for a GET stream; seconds bounds it (chunks)."""
        # Every event is rebuilt from the lines the gateway understood (sse_frame), so nothing it did not filter
        # can reach a client as data.
        pending = bytearray()
        async for chunk in chunks(owner, lease, seconds):
            start = max(0, len(pending) - 3)  # only new bytes, plus a boundary split across chunks
            pending.extend(chunk)
            while match := EVENT_BOUNDARY.search(pending, start):
                if reply_worker is not None and match.start() > WORKER_FRAME_BYTES:
                    # HM-30 D1: a large event is framed, processed and built on the reply worker, in this profile's
                    # turn (relayed_frame: the steps below, the same bytes); the state for a POST stream's reply is read
                    # here, on the loop. pending stays as it is until the job ended.
                    end = match.start()
                    found = None if request is None else prepared()
                    try:
                        outcome = await lease.run(lambda: reply_worker.run(worker_frame, pending, end, request, found))
                    except (ValueError, ConfigError, RecursionError, WorkerStopped):
                        return
                    del pending[:match.end()]
                    start = 0
                    if outcome == END_STREAM:
                        return
                    if outcome == SKIP_EVENT:
                        continue
                    event, final = outcome
                else:
                    parsed = sse_frame(bytes(pending[:match.start()]))
                    del pending[:match.end()]
                    start = 0
                    if parsed is None:
                        return
                    kept, data_lines = parsed
                    payload = sse_data(data_lines)
                    final = False
                    if data_lines and not payload.strip():
                        data_lines = [b"data:"]  # an empty (priming) event stays empty
                    elif data_lines:
                        try:
                            if reply_worker is None:
                                outcome = relayed_event(payload, request, store.load, masks)
                            else:
                                # HM-30: processed on the add-on's reply worker, in this profile's turn; the state for
                                # a POST stream's reply is read here, on the loop (a GET stream relays no reply).
                                found = None if request is None else prepared()
                                outcome = await lease.run(lambda: reply_worker.run(worker_event, payload, request,
                                                                                   found))
                        except (ValueError, ConfigError, RecursionError, WorkerStopped):
                            return
                        if outcome == END_STREAM:
                            return
                        if outcome == SKIP_EVENT:
                            continue
                        # final, R1 #1: the reply ends the stream (MCP: the server SHOULD close it)
                        line, final = outcome
                        data_lines = [line]
                    lines = kept + data_lines
                    event = b"\n".join(lines) + b"\n\n" if lines else None
                if event is not None:
                    if final:
                        owner.reply_event = event  # HM-14: an Ending knows the reply by it (delivered or not)
                    yield event
                if final:
                    # HM-14: the generator resumes only once the server took the reply: it was delivered (an Ending
                    # after it adds no -32005; when the token changed as the server took it, Ending sees the event)
                    owner.answered = True
                    return  # a duplicate reply or anything after it is never relayed
        # A truncated SSE event is intentionally not dispatched.
        if slot_busy is not None and owner.interrupted is not None:
            # HM-14 (contract 2.5): the child's connection broke after the stream started. A POST's reply that did not
            # come gets the gateway's own -32004 event under its id (a GET stream answers no request: it just ends);
            # the stream then ends normally, no exception for the server.
            stopped = await child_stopped(owner.generation)
            text = interruption_text(stopped, owner.generation)
            slot_busy.interrupted("POST" if request is not None else "GET", type(owner.interrupted).__name__, stopped)
            if request is not None:
                event = gateway_event(request[0], CHILD_INTERRUPTED, text)
                owner.reply_event = event  # HM-14 review S-1: this event answers the POST, as a reply does
                yield event
                owner.answered = True  # the server took it: an Ending adds no -32005 under the same id

    def local_session(session):
        """0.2.2: whether session is a live session the gateway opened itself (its last use is renewed)."""
        now = time.monotonic()
        while local_sessions and now - next(iter(local_sessions.values())) >= LOCAL_SESSION_SECONDS:
            local_sessions.popitem(last=False)
        if session not in local_sessions:
            return False
        local_sessions[session] = now
        local_sessions.move_to_end(session)
        return True

    def local_initialize(message):
        """0.2.2: the initialize answer the gateway gives itself: the same result a child's answer is rebuilt into, the
        client's protocolVersion when it is a reviewed one (else the newest reviewed one), and a new session of its own."""
        local_session(None)  # ends idle sessions first
        session = "woow-local-" + secrets.token_hex(16)
        local_sessions[session] = time.monotonic()
        while len(local_sessions) > LOCAL_SESSION_LIMIT:
            local_sessions.popitem(last=False)
        requested = message["params"]["protocolVersion"]
        result = {"protocolVersion": requested if requested in PROTOCOL_VERSIONS else max(PROTOCOL_VERSIONS),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": server_name, "version": management.product_version or VERSION},
                  **({"instructions": instructions} if instructions else {})}
        return json_reply({"jsonrpc": "2.0", "id": message["id"], "result": result}, 200,
                          {"Cache-Control": "no-store", "mcp-session-id": session})

    def listed_reply(ident, state):
        """0.2.2: tools/list answered from listing, filtered exactly as a child's answer (redact, then filter_list)."""
        from .odoo_switch_listing import for_state as listing_for_state
        value = {"jsonrpc": "2.0", "id": ident, "result": {"tools": listing_for_state(listing, state)}}
        value = filter_list(redact.redact_secrets(value, masks(state)), tools, state)
        return json_reply(value, 200, {"Cache-Control": "no-store"})

    async def mcp(request):
        return await leased_serve(request, None)

    async def private_mcp(request):
        return await leased_serve(request, request.path_params["secret"])

    async def leased_serve(request, secret):
        def refused():
            return BadRequest(401) if secret is None else HTTPException(404)
        try:
            response = await serve(request, secret)
        except AccessChanged:
            raise refused() from None
        lease = getattr(request.state, "token_lease", None)
        if lease is None or response.status_code in (401, 404):
            return response
        ending = None
        if slot_busy is not None:
            # HM-14 (switched on; contract 2.5): a token that changes once the answer began to go out gets the gateway's
            # own ending. refusal: the bytes refused() gets from error_handler (Bearer) or Starlette's 404 (secret path).
            refusal = (JSONResponse({"error": "request denied"}, status_code=401) if secret is None
                       else PlainTextResponse("Not Found", status_code=404))
            ending = Ending(refusal, response)
        return LeasedResponse(response, lease, refused, ending)

    async def serve(request, secret):
        """secret is None on /mcp (Bearer header) and the path segment on /private_<secret>/mcp.

        On the secret path a wrong, revoked or unset token is the same 404 as any unknown path (Starlette's own
        HTTPException(404): same status, body and headers, no WWW-Authenticate), so the reply never says whether
        the path exists, the token was revoked or the guess was close. The request's own Authorization header is
        never read there. A product may restrict the secret path to exact browser Origins; no Origin remains valid
        for non-browser clients. /mcp is unchanged: 401 with WWW-Authenticate, Origin 403.

        0.1.14: on both paths, a well-formed tools/call the policy refuses (policy.ToolCallRefused) is answered HTTP 200
        with a JSON-RPC error giving the reason, when it carries a session id; without one it stays 403 as before."""
        def authorized(state):
            return token_valid(request, state) if secret is None else secret_valid(secret, state)

        def refused():
            return BadRequest(401) if secret is None else HTTPException(404)

        def unauthorized():
            if secret is not None:
                raise refused()
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})

        def tool_refusal(ident, refusal):
            """0.1.14: a refused well-formed tools/call is answered as JSON-RPC (ToolCallRefused.error()), not 403. HM-08:
            switched on, a health check's reason in it is masked with every token the add-on holds as well (the health
            monitor masks it with this profile's own credentials)."""
            error = refusal.error()
            if reply_secrets is not None:
                error = redact.redact_secrets(error, tuple(sorted(others(), key=len, reverse=True)))
            return json_reply({"jsonrpc": "2.0", "id": ident, "error": error}, 200, {"Cache-Control": "no-store"})

        def session_gone():
            """0.2.2: the session is no longer served (its child stopped, or the gateway's own session ends because the
            child is up): 404, as a child answers for a session it does not know; MCP clients then initialize again."""
            if request.method == "POST" and isinstance(message, dict) and "id" in message:
                return child_status_reply(message["id"], 404, {"Cache-Control": "no-store"})
            return Response(status_code=404, headers={"Cache-Control": "no-store"})

        def backend_refusal(available, configured):
            """0.2.2: a tools/call no child is asked: None when it may be forwarded."""
            name = message["params"]["name"]
            tool = tools[name]
            if not tool.requires_backend:
                return None
            if not configured:
                return tool_refusal(message["id"], ToolCallRefused("backend_not_configured", name))
            if available["ready"] and available["backend"] == "unreachable":
                return tool_refusal(message["id"], ToolCallRefused("backend_unreachable", name, reason=available["reason"]))
            return None

        def refused_body(error):
            """A body the request limits refused (n8n's McpRequestLimits; HM-31: the structure guard): its answer as
            before, and the profile's WARNING (HM-31, PaaS P2-D: the kind, the HTTP status and a short reason)."""
            budget_share.warn("body-" + error.kind, f"refused a request body ({error.kind}, HTTP {error.status}): "
                                                    f"{error.log_reason}")
            return request_limit_reply(error)

        async def over_budget(exceeded, unwatched):
            """HM-31 (contract 2.4; PaaS proxy._refuse_over_budget, d7f5849): the body does not fit the budget. A
            declared one (nothing read) is drained first, only its head and tail kept (a client that sends its whole
            body before it reads gets this answer, not a reset); one without a length was cut off as it arrived. Its id
            from its head (and tail): 200 + -32003 under it, else 503; Retry-After 5. Nothing reaches the child."""
            budget_share.warn("bytes", request_budget.budget_note(exceeded))
            head, tail = exceeded.head, b""
            if not exceeded.read:
                head, tail, left = await request_budget.drain(unwatched, idle_seconds=idle_seconds,
                                                              total_seconds=BODY_SECONDS)
                if left:
                    return Response(status_code=CLIENT_CLOSED, headers={"Cache-Control": "no-store"})
            ident = request_budget.head_tail_id(head, tail) if request.method == "POST" else None
            return busy_reply(request_budget.unread_message(ident), request_budget.budget_text(exceeded))

        def without_child():
            """0.2.2 (listing only): the answers the gateway gives itself, before a slot or the child; None forwards."""
            state = store.load()  # reading the body yielded: a revoked token is refused as on any other path
            if not authorized(state):
                return unauthorized()
            available = availability()
            configured = getattr(state, "configured", bool(state.backend_url and state.backend_key))
            child_up = available["child"] in CHILD_UP
            if method == "initialize":
                return None if child_up else local_initialize(message)
            session = headers["mcp-session-id"]
            if local_session(session):
                if available["ready"]:
                    local_sessions.pop(session, None)  # the child answers now: the client opens a session with it
                    return session_gone()
                if request.method == "DELETE":
                    local_sessions.pop(session, None)
                    return Response(status_code=200, headers={"Cache-Control": "no-store"})
                if request.method == "GET":  # no server-to-client stream (MCP: 405 when a server offers none)
                    return Response(status_code=405, headers={"Allow": "POST, DELETE", "Cache-Control": "no-store"})
                if method == "notifications/initialized":
                    return Response(status_code=202, headers={"Cache-Control": "no-store"})
                if method == "ping":
                    return json_reply({"jsonrpc": "2.0", "id": message["id"], "result": {}}, 200, {"Cache-Control": "no-store"})
                if method == "tools/list":
                    return listed_reply(message["id"], state)
                name = message["params"]["name"]  # tools/call: authorize allows nothing else here
                if not configured and tools[name].requires_backend:
                    return tool_refusal(message["id"], ToolCallRefused("backend_not_configured", name))
                reason = (available["reason"] if available["backend"] == "unreachable" and available["reason"] else
                          "MCP_SERVER_NOT_READY: the add-on's MCP server is " + available["child"] + "; try again shortly")
                return tool_refusal(message["id"], ToolCallRefused("backend_unreachable", name, reason=reason))
            if not child_up:
                return session_gone()  # a child session: it ended with the child
            if request.method == "POST" and method == "tools/list" and not configured:
                return listed_reply(message["id"], state)  # n8n: its unconfigured child lists only documentation tools
            if request.method == "POST" and method == "tools/call":
                return backend_refusal(available, configured)
            return None

        state = store.load()
        if not authorized(state):
            return unauthorized()
        lease = request.state.token_lease = token_access.lease(state.token)
        if request.method not in ("GET", "POST", "DELETE"):  # any other method, only after the token check
            return Response(status_code=405, headers={"Allow": "GET, POST, DELETE"})
        origins = request.headers.getlist("origin")
        if secret is None and origins:
            raise BadRequest(403)  # Browser clients not in the Bearer contract; the secret path is for Claude.ai.
        if secret is not None and secret_path_allowed_origins is not None and origins and (
                len(origins) != 1 or origins[0] not in secret_path_allowed_origins):
            raise BadRequest(403)
        if request.url.query:
            raise BadRequest()
        method = message = refusal = None
        content = b""
        # HM-31 (contract 2.4): the token is checked; a large body is read under the request body budget from here on
        reservation = getattr(request.state, BODY_RESERVATION)
        unwatched = request_budget.watch(request, reservation, cap=body_cap, idle_seconds=idle_seconds)
        try:
            if request.method == "POST":
                if n8n_request_bounds:
                    if request.headers.get("content-type", "").split(";")[0] != "application/json":
                        raise BadRequest(415)
                    try:
                        async with asyncio.timeout(BODY_SECONDS):
                            limited_body = await lease.run(lambda: N8N_REQUEST_LIMITS.read_body(request))
                        N8N_REQUEST_LIMITS.parse_and_check(limited_body)
                        try:
                            message = strict_json(limited_body)
                            # Preserve HA's duplicate/nonfinite checks and reject lone surrogates before any dispatch.
                            json.dumps(message, ensure_ascii=False).encode("utf-8")
                        except (ValueError, RecursionError):  # UnicodeEncodeError is a ValueError
                            raise RequestLimitError(
                                "Invalid or excessively nested JSON", status=400, code=-32700) from None
                    except RequestLimitError as error:
                        return refused_body(error)
                    except ClientDisconnect:
                        raise BadRequest(403) from None
                    except TimeoutError:
                        raise BadRequest(408) from None
                else:
                    try:
                        message = await lease.run(lambda: json_body(request, STRUCTURE_LIMITS))
                    except RequestLimitError as error:
                        return refused_body(error)  # HM-31: the structure guard (too deep, too many elements, not UTF-8)
                    except BadRequest as error:
                        if error.status == 413:
                            budget_share.warn("body-too-large", "refused a request body (too-large, HTTP 413): body "
                                                                f"exceeds {MAX_REQUEST} bytes")
                        raise
            elif n8n_request_bounds:
                try:
                    async with asyncio.timeout(BODY_SECONDS):
                        nonempty = await lease.run(lambda: N8N_REQUEST_LIMITS.read_body(request))
                except RequestLimitError as error:
                    return refused_body(error)
                except ClientDisconnect:
                    raise BadRequest(403) from None
                except TimeoutError:
                    raise BadRequest(408) from None
            else:
                nonempty = await lease.run(lambda: body(request))
        except request_budget.BudgetExceeded as exceeded:
            return await over_budget(exceeded, unwatched)
        except request_budget.BodyIdleTimeout as idle:
            budget_share.warn("body-idle", f"a request body sent nothing for {idle.seconds:g} s; the request was "
                                           "dropped (408) and its bytes given back")
            return idle_reply(idle.seconds)
        if request.method == "POST":
            try:
                method = authorize(message, tools, state)
            except ToolCallRefused as refused_call:
                # 0.1.14: answered below with its reason when the request also carries usable session headers (as any
                # tools/call needs), never with a slot or the child; otherwise still 403, as in 0.1.13.
                method, refusal = "tools/call", refused_call
            except UnknownMethod as unknown:
                # 0.1.13: answered here, before the session check, a slot or the child (Claude.ai sends server/discover
                # first and needs a JSON-RPC answer to fall back to initialize). Only after the token check above.
                if not unknown.request:
                    return Response(status_code=202, headers={"Cache-Control": "no-store"})
                return json_reply({"jsonrpc": "2.0", "id": message["id"],
                                   "error": {"code": -32601, "message": "Method not found"}},
                                  200, {"Cache-Control": "no-store"})
            except Denied:
                raise BadRequest(403) from None
        elif nonempty:
            raise BadRequest()
        headers = {"Authorization": "Bearer " + state.child_token, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",  # fixed: the gateway reads both itself
                   "Accept-Encoding": "identity"}
        for name in ("mcp-session-id", "mcp-protocol-version", "last-event-id"):
            values = request.headers.getlist(name)
            if len(values) > 1 or (values and (len(values[0]) > 256 or not re.fullmatch(r"[\x21-\x7e]+", values[0]))):
                raise BadRequest(403 if refusal is not None else 400)
            # 0.4.0: never on an initialize. The body's protocolVersion negotiates; mcp 1.x children ignored the header
            # there, but MCP SDK 2 (2.3.0) routes any request whose header is not an initialize-handshake revision
            # (2026-07-28, a typo) to its 2026-07-28 handling, which refuses an initialize (HTTP 400), so a client that
            # still sends its server/discover header could no longer connect.
            if values and not (name == "mcp-protocol-version" and method == "initialize"):
                headers[name] = values[0]
        if refusal is not None and "mcp-session-id" not in headers:
            raise BadRequest(403)  # a refused call without a session: unchanged from 0.1.13
        if method != "initialize" and "mcp-session-id" not in headers:
            # 0.1.8 (0.1.6 RC GATEWAY-2): every child is stateful, so anything but initialize needs the session it
            # opened (MCP: such a server SHOULD answer 400). Forwarded, the pinned Python SDK children opened a new
            # session for it before refusing it, and kept it until they restarted (until 0.1.7; from 0.1.8 idle sessions
            # end after 30 minutes, GATEWAY-3).
            # The answer has the shape a refusing child's answer was relayed in (child_status_reply; a bare 400 for a
            # notification or DELETE), minus the child's new session id. n8n-mcp, which opens no session for these,
            # accepted a notification without one (202); it now gets 400 like every other request.
            if request.method == "DELETE" or request.method == "POST" and not (isinstance(message, dict)
                                                                                and "id" in message):
                return Response(status_code=400, headers={"Cache-Control": "no-store"})
            return child_status_reply(message.get("id") if request.method == "POST" else None, 400,
                                      {"Cache-Control": "no-store"})
        if refusal is not None:
            # Decided again on fresh state (reading the body yielded): a revoked token is still refused as above, and a
            # call the policy now allows takes the normal path below.
            state = store.load()
            if not authorized(state):
                return unauthorized()
            try:
                authorize(message, tools, state)
            except ToolCallRefused as refused_call:
                return tool_refusal(message["id"], refused_call)
            except Denied:
                raise BadRequest(403) from None
        if listing is not None:
            answer = without_child()
            if answer is not None:
                return answer
        pending = None
        if request.method == "POST" and method == "tools/call":
            pending = getattr(request.state, PENDING_REPLIES, None)
            if pending is not None:
                # HM-30 (contract 2.4, 6): switched on, a profile whose answers not received yet hold its pending-reply
                # budget gets its next tools/call answered busy by its gate, before a slot or the child (before HM-14's
                # lanes too: a tools/call refused for its pending replies never queues for a slot first).
                answer = pending(message)
                if answer is not None:
                    return answer
        if lanes is None:
            try:
                async with asyncio.timeout(FORWARD_WAIT_SECONDS):
                    await slots.acquire()
            except TimeoutError:
                raise BadRequest(503) from None
            taken = slots
        else:
            # HM-08, HM-14 (switched on; contract 2.4): the PaaS lanes, queue cap, disconnect watch and busy shapes
            reserved = lanes[RESERVED_LANE]
            lane = (reserved if reserved.limit and carries_no_request(request.method, message)
                    else lanes[ORDINARY_LANE])
            outcome = await take_slot(lane, slot_busy.queue, slot_busy.wait, lambda: client_gone(request))
            if outcome == "abandoned":
                slot_busy.abandoned(lane.name)
                return Response(status_code=CLIENT_CLOSED, headers={"Cache-Control": "no-store"})
            if outcome != "taken":
                return slot_busy.answer(message if request.method == "POST" else None, outcome, lane.name)
            taken = lane.semaphore
        upstream = None
        owner = UpstreamOwner(taken)
        handed_off = False
        try:
            # Revalidate after yielding for body/concurrency; sessions do not cache policy.
            state = store.load()
            if not authorized(state):
                raise refused()
            if request.method == "POST":
                try:
                    authorize(message, tools, state)
                except ToolCallRefused as refused_call:
                    # The policy changed while this call waited for a slot: the same answer as above (the slot is
                    # released by the finally below; the child is never reached).
                    return tool_refusal(message["id"], refused_call)
                except Denied:
                    raise BadRequest(403) from None
                if pending is not None:
                    # HM-30 review 2 MF-2 (contract 2.4, 5): checked again now that the call holds its slot. It passed
                    # the check above before it waited for the slot; meanwhile the replies of the calls that held the
                    # slots were charged (PENDING_CHARGE) as they released them. Refused here, it is never forwarded
                    # (the slot is released by the finally below).
                    answer = pending(message)
                    if answer is not None:
                        return answer
                forwarded = message
                if method == "initialize" and isinstance(message.get("params"), dict):
                    # The gateway answers no server-to-client requests (sampling, elicitation, roots): the
                    # child must not expect any, whatever the real client declared.
                    forwarded = {**message, "params": {**message["params"], "capabilities": {}}}
                content = json.dumps(forwarded, separators=(",", ":")).encode()
                try:
                    # HM-08 review MF-1, S-1; HM-31: what the child is sent stays charged until the request ends (this
                    # serialization can be larger than what was read: ASCII escapes make a CJK character 6 bytes and an
                    # emoji 12, and a number is written in Python's own form).
                    reservation.forward(len(content))
                except request_budget.BudgetExceeded as exceeded:
                    budget_share.warn("bytes", request_budget.budget_note(exceeded))
                    # the slot is released below; the child never gets the request
                    return busy_reply(message, request_budget.budget_text(exceeded))
            waited = time.monotonic() + CHILD_WAIT_SECONDS
            call_seconds = CALL_SECONDS if method == "tools/call" else None  # 0.2.2: see CALL_SECONDS
            async with asyncio.timeout(call_seconds + 5 if call_seconds else 35):
                while True:
                    lease.check()
                    outgoing = child.build_request(request.method, child_url, headers=headers, content=content,
                                                   timeout=httpx.Timeout(call_seconds or 30, connect=3, pool=3))
                    if lanes is not None:
                        owner.generation = child_generation()  # HM-14: the generation this attempt goes to
                    try:
                        async def send_owned():
                            owner.response = await child.send(outgoing, stream=True, follow_redirects=False)
                            # Adopt a newly opened session before the lease's post-I/O check:
                            # revocation may race the arrival of initialize headers.
                            session = owner.response.headers.get("mcp-session-id")
                            if (method == "initialize" and session is not None
                                    and FORWARDED_HEADERS["mcp-session-id"].fullmatch(session)
                                    and session != headers.get("mcp-session-id")):
                                owner.end_session = functools.partial(end_session, state.child_token, session)
                            return owner.response
                        upstream = await lease.run(send_owned)
                        break
                    except httpx.ConnectError:
                        # 0.2.2 (listing only): nothing listens on the child's port. Its sessions ended with it; an
                        # initialize waits for a child that is starting, then the gateway answers it itself.
                        if listing is None:
                            raise
                        if method != "initialize":
                            return session_gone()
                        if time.monotonic() >= waited or availability()["child"] not in CHILD_UP:
                            return local_initialize(message)
                        await lease.run(lambda: asyncio.sleep(CHILD_RETRY_SECONDS))
            # Only well-formed values of four headers are forwarded (a non-Latin-1 value from a child could
            # not be encoded into the reply); session/protocol values follow the same rule as request headers.
            response_headers = {k: v for k, v in upstream.headers.items()
                                if k in FORWARDED_HEADERS and FORWARDED_HEADERS[k].fullmatch(v)}
            response_headers["Cache-Control"] = "no-store"
            session = response_headers.get("mcp-session-id")
            if method == "initialize" and session not in (None, headers.get("mcp-session-id")):
                # 0.1.6 (R2): the child opened this session for this initialize. Until an answer hands its id to the
                # client the gateway owns it, and every other way out ends it (UpstreamOwner.close). Only a usable
                # id (one the gateway would forward), and never one the client sent itself: that session is the
                # client's (a child may echo it).
                owner.end_session = functools.partial(end_session, state.child_token, session)
            if not still_authorized(state.token):
                raise refused()
            if not 200 <= upstream.status_code <= 599 or 300 <= upstream.status_code < 400:
                raise BadRequest(502)  # no interim reply (an ASGI server cannot send it), no child redirect
            if upstream.status_code in (401, 403):
                raise BadRequest(502)  # the child refused the gateway's own token or Host: not a client credential issue
            media = upstream.headers.get("content-type", "").split(";")[0].strip().lower()
            is_sse = media == "text/event-stream"
            if is_sse:  # the gateway re-frames events itself: never forward the child's parameters (charset)
                response_headers["content-type"] = "text/event-stream"
            request_id = request.method == "POST" and isinstance(message, dict) and "id" in message
            if request.method == "DELETE" or request.method == "POST" and not request_id:
                # Replies to a notification or a session DELETE carry nothing a client needs: status and the
                # forwarded headers only, never the child's bytes.
                return Response(status_code=upstream.status_code,
                                headers={k: v for k, v in response_headers.items() if k != "content-type"})
            if upstream.status_code >= 400:
                if method == "initialize":
                    response_headers.pop("mcp-session-id", None)  # no session for a failed initialize
                return child_status_reply(message.get("id") if request_id else None, upstream.status_code,
                                          response_headers)
            if 200 <= upstream.status_code < 300 and (request.method == "GET" or request_id):
                # A success body must be one the gateway parses and filters itself: an SSE stream, or (for a
                # request) a plain 200 JSON reply. Nothing else is relayed, not even a body declared empty:
                # framing headers can lie (Content-Length: 0 with chunked encoding still carries a body).
                if not (is_sse and upstream.status_code == 200 or
                        request_id and media == "application/json" and upstream.status_code == 200):
                    if method == "initialize" and upstream.headers.get("content-length") == "0":
                        return backend_unavailable(message.get("id"))  # the child sent no reply
                    raise BadRequest(502)
            if method == "initialize" and upstream.status_code == 200:
                outcome, value, frame = await initialize_reply(owner, lease, is_sse, message.get("id"))
                if not still_authorized(state.token):
                    raise refused()
                if lanes is not None and owner.interrupted is not None:
                    return await interrupted_answer(owner, request, message, owner.interrupted)  # HM-14
                if outcome == "missing":
                    return backend_unavailable(message.get("id"))
                try:
                    if outcome != "ok":
                        raise ValueError("invalid initialize response")
                    if "mcp-session-id" in upstream.headers and "mcp-session-id" not in response_headers:
                        raise ValueError("unusable session id")  # a client could not continue the session
                    value = gateway_reply(value)
                    if "result" in value:
                        version = value["result"].get("protocolVersion") if isinstance(value["result"], dict) else None
                        if not (isinstance(version, str) and version in PROTOCOL_VERSIONS):
                            raise ValueError("unusable protocol version")
                        # 0.1.8 (0.1.6 R1 F6): the result is the gateway's own; only the child's protocolVersion (one of
                        # the reviewed revisions) remains. serverInfo names this add-on, not the child (n8n-mcp calls itself
                        # "n8n-documentation-mcp"), and the child's instructions are never relayed: Claude Code puts
                        # instructions into the model's system prompt, and EMQX's and LiteLLM's describe their whole
                        # upstream tool set, including tools this gateway hides or refuses (Odoo's is a generic line).
                        # The caller may pass reviewed fixed text.
                        value["result"] = {"protocolVersion": version,
                                           "capabilities": {"tools": {}},
                                           "serverInfo": {"name": server_name, "version": management.product_version or VERSION},
                                           **({"instructions": instructions} if instructions else {})}
                except ValueError:
                    raise BadRequest(502) from None
                if "error" in value:
                    # A child's initialize error (its message and data are the child's text) is masked as every other
                    # relayed text: this profile's credentials and, switched on, every token the add-on holds (masks).
                    # HM-14 (contract 1.2, not gated): masked whether or not the product is switched on; before it, a
                    # switched-off product relayed it unmasked (HM-08 review S-4 (a)).
                    value = redact.redact_secrets(value, masks(store.load()))
                if frame is None or json_only(request):
                    # 0.1.13: a client that accepts only application/json gets the initialize answer as JSON even when
                    # the child framed it as an SSE event (the gateway holds the parsed reply either way).
                    answer = json_reply(value, 200, response_headers)
                else:
                    # The child's event framing (id/event/retry lines) with the filtered data.
                    frame.append(b"data: " + json.dumps(value, separators=(",", ":")).encode())
                    answer = Response(b"\n".join(frame) + b"\n\n", status_code=200, headers=response_headers)
                fence = fenced = None
                if lanes is not None and owner.generation is not None:
                    # HM-14 (FM-43): the session goes out only while the generation this initialize went to still runs
                    generation = owner.generation
                    fence = functools.partial(child_runs, generation)
                    fenced = backend_unavailable(message.get("id"))
                handed_off = True
                return OwnedInitializeResponse(answer, owner, fence, fenced)
            if request_id and not is_sse and upstream.status_code == 200:
                # Every JSON reply is parsed, must answer this request, is filtered and re-serialized: a child
                # cannot hand a client an unfiltered list under another request's id or in a batch.
                result = bytearray()
                async for chunk in chunks(owner, lease, call_seconds):
                    result.extend(chunk)
                if not still_authorized(state.token):
                    raise refused()
                if lanes is not None and owner.interrupted is not None:
                    return await interrupted_answer(owner, request, message, owner.interrupted)  # HM-14
                if reply_worker is None:
                    try:
                        if owner.overflowed:
                            raise ValueError("oversize reply")
                        value = relayed_reply(result, message.get("id"), method, store.load, masks)
                    except (ValueError, RecursionError):
                        raise BadRequest(502) from None
                    return json_reply(value, 200, response_headers)
                # HM-30: processed on the add-on's reply worker, in this profile's turn (the state and masks read here,
                # on the loop); the same steps, so the same bytes. A job it can no longer take is a 502 as well.
                try:
                    if owner.overflowed:
                        raise ValueError("oversize reply")
                    found = prepared()
                    # HM-30 review 2 S-6: not named encoded (the module's function) nor body (make_apps' reader of
                    # the request body, which a lambda above reads from this scope)
                    serialized = await lease.run(lambda: reply_worker.run(worker_reply, result, message.get("id"),
                                                                          method, found))
                except (ValueError, RecursionError, WorkerStopped):
                    raise BadRequest(502) from None
                charge = getattr(request.state, PENDING_CHARGE, None)
                if charge is not None:
                    charge(len(serialized))  # HM-30 review 2 MF-2: before the finally below releases the slot
                return encoded_reply(serialized, 200, response_headers)
            if not (is_sse and upstream.status_code == 200):
                raise BadRequest(502)  # unreachable (R1 #8): every other success body was answered or refused above
            if request_id:
                owner.reply = (message.get("id"),)  # HM-14: the id an Ending's -32005 event answers
            response = OwnedStreamingResponse(stream(owner, lease, (message.get("id"), method) if request_id else None,
                                                     call_seconds),
                                              owner=owner, status_code=200, headers=response_headers)
            # This answer hands any session id it carries over to the client, so the end of its stream must never
            # DELETE that session (an initialize never streams today: it is answered or refused above).
            owner.end_session = None
            handed_off = True  # only once the response owns the slot: a failed constructor must release it
            return response
        except (httpx.HTTPError, TimeoutError) as error:
            if lanes is not None and interrupted(error):
                return await interrupted_answer(owner, request, message, error)  # HM-14 (contract 2.5)
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
    admin = management_app(admin_page)  # HM-10: the same application as before, built by the shared helper
    admin.state.profile_action = profile_action  # HM-10: for the switched-on dispatcher (see the docstring)
    mcp_app = Starlette(routes=[Route(MCP_ROUTE, AnyMethod(mcp, budget_share)),
                                Route(SECRET_ROUTE, AnyMethod(private_mcp, budget_share)), Route(READY_ROUTE, readiness)],
                        exception_handlers=exceptions)
    mcp_app.router.redirect_slashes = False
    mcp_app.state.lanes = lanes  # HM-14: a switched-on profile's lanes (slots, waiting), for diagnostics and tests
    mcp_app.state.body_budget = budget_share  # HM-31: this profile's share of the request body budget (tests)
    return admin, mcp_app
