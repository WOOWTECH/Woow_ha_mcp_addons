"""8081 of a switched-on product: which profile an MCP request belongs to, and every profile's own admission, byte
budget and stream cap (multi-profile plan 5.1, 5.2; contract 2.2, 2.3, 2.4, 2.7, 5; HM-08).

A product is switched on by features.enabled() only (the repository switches none on); a switched-off product never
loads a dispatcher, its 8081 is the default profile's own app as before (run_product). Once on, run_product serves
McpDispatcher on 8081, built by profile_runtime.ProfileManager, which knows the profiles.

Which profile (plan 5.1; I1, I2; DQ-01 (a), DQ-09, DQ-12):

- Only the path and the Authorization header are read. /private_<secret>/mcp is matched with Starlette's own Route on
  the gateway's own template (gateway.SECRET_ROUTE), so the dispatcher and the profile's app always agree which segment
  is the token, and the request's Authorization header is never read there; /mcp needs exactly one Authorization
  header, literally "Bearer <token>" (gateway.token_valid's rule). Anything else (no candidate) goes to the default
  profile's app untouched: its answer is today's, byte for byte (a wrong token there is its own 401 or 404). 8081 never
  reads X-MCP-Profile, a cookie or the query to choose (FM-29).
- The candidate is hashed once (sha256) and compared with every routable profile's token digest
  (hmac.compare_digest): the default profile and every indexed profile the manager could open, all of them, with no
  early exit; a revoked token has no digest. A profile's digest is kept with its state file's signature (st_dev,
  st_ino, st_mtime_ns, st_size, st_nlink, st_mode; with st_ctime_ns for an additional profile, whose reads never
  chmod) and read again only when that changes (FM-14); an additional profile whose directory is no longer the one
  opened (another inode at its name; HM-07 review S-08) or whose state cannot be read is not routed (FM-05: its token
  is then an unknown token, never served by another profile).
- Exactly one match: that profile's gate, then its own app, which checks the token again with its own store (a stale
  digest can only be refused, never served by the wrong profile). No match: the default profile's app. Two or more
  (a copied directory, a hand edit; HA has no token-setting API): 503 {"error":"state unavailable"}, no profile served,
  one WARNING a minute per group of profiles (their ids' first 8 characters, never the token; DQ-09).
- Unusable: the index is corrupt or changed behind the add-on's back (profiles.recheck_index: sticky until a restart;
  DQ-12), the profile data could not be listed at startup, or the default profile's state cannot be read (a duplicate
  of its token cannot be ruled out): 503 {"error":"state unavailable"} for every token, the default profile's included.
- HM-13c (plan 8.4 全部撤銷; contract 4.2): a token a "revoke all" could not revoke (its profile failed; the manager's
  revoke_fence holds its digest) gets 503 {"error":"state unavailable"} too, whatever its state says now, until a
  "revoke all" finishes (the next start finishes the unfinished one before anything is served).
  /health/ready (which speaks for the default profile, DQ-19) then answers not ready, as the default app does when its
  state cannot be read; any other path keeps the default app's answer.

Every profile's own limits (ProfileGate; plan 5.2; contract 5; I8; DQ-07 (a)): before a request's body is read, its
profile's admission (64 for the default profile, 32 for an additional one; a request with no candidate or no match
takes none). A GET (an event stream) takes one of the profile's stream places (24, 8; 0.5.1: no reply ticket, only a small byte bound of its own).
A GET past the stream cap: 429 +
-32003 id null + Retry-After 30, at once. The profile's app answers a forwarding slot that stays busy for a second with
the PaaS busy shapes (ProfileGate.slot_busy, make_apps slot_busy). Each limit writes one WARNING per profile and
situation a minute (Reports: id's first 8 characters, suppressed=N), never a token, URL, label or request content.

HM-31 (plan 12.3 HM-31; contract 2.4, 5; the PaaS #155 gateway, woow-mcp-server d7f5849): the byte budget is no longer
the gate's own. HM-08's per-profile budget (64 MiB, charged from admission) and the PaaS request body budget are one:
request_budget.RequestBudget, one for the add-on (the manager's), each profile's share (ProfileGate.budget_share:
min(its quota's 64 MiB, half the add-on's budget, at least 16 MiB)) charged by the profile's app (gateway.make_apps
body_budget) once the token is checked: what was read and what is forwarded, until the request ends; a declared
length that does not fit is refused before a byte is read (drained, its id from its head and tail: 200 + -32003, else
503); small requests (64 KiB at most) are never charged nor refused. The add-on's refusal allowance (8 at once, 512 KiB)
is gone with it.

Admission full (HM-14 review MF-2 (b), settled 2026-11-16 by the main session as the PaaS semantics; DQ-07's numbers
unchanged): a POST of at most 64 KiB (REFUSAL_BODY_LIMIT; declared, or without a length and ending within it: the
gateway's request_budget.declared_length, so a Content-Length beside a Transfer-Encoding declares nothing) is still
read, within REFUSAL_READ_SECONDS and with no bound on how many are read at once (PaaS: small requests are not charged
and their reads not counted; the 8081 listener's bound holds them). One that carries no request (gateway.
carries_no_request: a notification or a response) goes on to the profile's app beyond its admission, so the reserve
still carries notifications/initialized when the ordinary slots and their queue are full; any other is answered busy
with its id (200 + -32003; 503 without one). A larger POST, a GET or a DELETE: 503 + -32003 id null at once, unread
(plan 8.8 #16: PaaS reads every body first).

HM-14 (contract 2.4, 2.5; the PaaS #148 gateway, woow-mcp-server 69ac425): ProfileGate.slot_busy (gateway.SlotBusy) also
gives the profile's app its lanes' queue cap (32, 16 requests waiting in each lane on its own) and its reserve (4 slots
kept for a POST that carries no request), and the answers and WARNINGs that name the profile: a lane's queue full
(refused at once), a client gone while its request waited (never sent; a WARNING only), the child's connection broken
mid-request (-32004; a WARNING with the HTTP method and the error's class). The -32003 texts are settled (HM-14): the four
HM-08 wrote, as they were (HM-31: the byte budget's is the PaaS one, request_budget.budget_text), and the reserved
slots' and the queue's (forward_text, queue_text).

What the budget bounds is the bytes of a profile's requests, not every byte they cost: parsing a body costs more than
its size (HM-31's structure guard keeps a request's structure within 200,000 elements and 64 levels, contract 5), and
the 8081 listener's connections are one bound of the whole add-on (uvicorn's limit_concurrency counts idle keep-alive
connections and those of clients without a token too: when it is full, a new connection gets uvicorn's plain-text 503
whatever its profile; HM-08 review S-5, known since G2 S7). The isolation of one profile from another holds per request.

Every profile's answers not received yet (HM-30; plan 5.2, 5.5; contract 2.4, 5, 6; C2-MF-4, C1-M5): the bytes of
every answer its app hands to the server are charged to the profile's pending-reply budget (32 MiB each, the default
profile's included) until the server took them. h11 (uvicorn) takes a message only once what it held before was
written out (flow control: it waits for its buffer to drain first), so a message stays charged until the request's
next message was taken or the request ends. An answer that declares its length (a JSON answer: Content-Length) is
handed over in pieces of REPLY_PIECE, then an empty last message: the bytes on the wire are the same, the server never
holds more than its own buffer (64 KiB) and one piece of it, and the request ends only once the server took it all. An
event stream (chunked) is handed over as its app yields it (its framing unchanged); its end waits until the server took
it. While the profile's charge is at or over its budget, its next tools/call is answered 200 + -32003 under its id
before it is forwarded (gateway.PENDING_REPLIES; pending_text), one WARNING a minute. The answers already forwarded are
always processed and handed over (a client that reads its answers in order must never wait for an answer held back),
so a profile can hold up to its budget plus the answers in flight when it was reached: at most its forwarding slots of
replies of up to gateway.MAX_RESPONSE as read, charged as the gateway serializes them (ASCII escapes: up to about
three times as many bytes; contract 5, 6). HM-30 review 2 MF-2: that bound holds because a tools/call is checked
again once it took its slot (it may have waited in HM-14's queue after the first check), and a relayed JSON reply is
charged (gateway.PENDING_CHARGE) before it releases its slot, not only once its app hands it over: a call that waited
for that slot sees it charged. An event stream holds its slot until it ends, so its reply is charged while it does.

The reply mask (plan 5.1 point 8, DQ-40 (a) ⑧): the manager's reply_secrets() gives every profile's app every token
and child token the add-on holds (make_apps reply_secrets). Not here: the lanes, the -32004/-32005 endings and the
initialize generation fence themselves (gateway.make_apps, given slot_busy; HM-14), the reply worker (HM-30:
reply_worker.py), the Origin policy of the secret path (HM-27: origin_policy.py, checked by each profile's app once its
token is; the dispatcher never reads an Origin).

8099 of a switched-on product (AdminDispatcher, HM-10; plan 5.3; contract 3.1-3.3, 3.7; DQ-17, UC-10): the shared
management pipeline for every path, then the profile. See AdminDispatcher. HM-27: {base}/api/origin-policy is one more
global path (the add-on's Origin policy; contract 3.1, 3.5).
"""
from __future__ import annotations

import asyncio
import hashlib
from hmac import compare_digest
import json
import logging
import os

from dataclasses import dataclass

from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, Response
from starlette.routing import Match, Route

from . import gateway, origin_policy, profiles, reply_memory, request_budget
from .admin_auth import BadRequest
from .config import ConfigError, strict_json
from .profile_admin import Call
from .request_limits import not_utf8

logger = logging.getLogger(__name__)

# HM-31 (MF-2 (b)): what the gate reads of a POST beyond its profile's admission (a small request: request_budget's
# SMALL_REQUEST_BYTES) and for how long, to see whether it carries no request (then served) or to find its JSON-RPC id.
REFUSAL_BODY_LIMIT = request_budget.SMALL_REQUEST_BYTES
REFUSAL_READ_SECONDS = 2
# One WARNING per profile and situation this often (the PaaS gateway_pool.REPORT_INTERVAL_SECONDS), remembering at most
# this many situations (request_budget.Reports). HM-14 review S-4: every situation of every profile an add-on can have
# must fit, or the oldest is forgotten before it comes round again and every line is written: a profile has 11 since
# HM-14 and 16 since HM-31 (the budget, the idle body and four kinds of refused body), Odoo's 6 profiles 96, and the
# shared-token groups count too (at most 57 for 6 profiles); 256 holds them.
REPORT_SECONDS = request_budget.REPORT_SECONDS
MAX_REPORT_KEYS = request_budget.MAX_REPORT_KEYS
MiB = 1024 * 1024
# HM-30: how much of an answer that declares its length the gate hands the server at once (see the module docstring).
REPLY_PIECE = 64 * 1024


# ---- the -32003 texts (HM-14 settles them: HM-08's four as they were, and the reserved slots' and the queue's): which
# limit, and "retry shortly"; English, then Traditional Chinese, as the PaaS gateway writes them (69ac425 proxy.py
# _busy_message, _stream_limit_message; its 子行程 is HA's 子程式). Never a token, a URL, a label or request content. ----

def admission_text(limit: int) -> str:
    return (f"This MCP URL already has {limit} requests in progress, the limit of its profile, so this request was not "
            "read or sent. Retry shortly. "
            f"(這個 MCP 網址同時進行中的請求已達這個帳號的上限 {limit} 個，這個請求沒有讀取也沒有送出，請稍後再試。)")


def forward_text(slots: int, wait: float, reserved: bool = False) -> str:
    """A request that waited for one of its lane's slots in vain (reserved: the slots kept for notifications; each lane
    names its own number of slots, PaaS review N8)."""
    english, chinese = ('connections reserved for notifications', '保留給通知、') if reserved else ('connections', '')
    return (f"All {slots} {english} of this MCP URL to its MCP server are in use; waited {wait:g} s without a free "
            "one, so this request was not sent. Retry shortly. "
            f"(這個 MCP 網址{chinese}送往 MCP 子程式的 {slots} 條連線都在使用中，等了 {wait:g} 秒仍沒有空出來，這個請求沒有送出，"
            "請稍後再試。)")


def queue_text(queue: int, slots: int, reserved: bool = False) -> str:
    """A request refused at once because its lane's queue was full (reserved: as forward_text)."""
    english, chinese = ('connections reserved for notifications', '保留給通知、') if reserved else ('connections', '')
    return (f"{queue} requests of this MCP URL are already waiting for one of its {slots} {english} to its MCP server, "
            "so this request was not queued or sent. Retry shortly. "
            f"(這個 MCP 網址已經有 {queue} 個請求在排隊等 {slots} 條{chinese}送往 MCP 子程式的連線，這個請求沒有排隊也沒有送出，"
            "請稍後再試。)")


def pending_text(limit: int) -> str:
    """HM-30 (contract 2.4): a tools/call refused because the profile's answers not received yet hold its pending-reply
    budget; written as HM-14 settled the others (English, then Traditional Chinese; the limit, never a token, a URL, a
    label or content)."""
    size = f'{limit / MiB:g} MiB'
    return (f"The answers of this MCP URL that its clients have not received yet already hold {size}, the limit of its "
            "profile, so this request was not sent. Retry shortly. "
            f"(這個 MCP 網址還沒被用戶端收完的回覆已達這個帳號的上限 {size}，這個請求沒有送出，請稍後再試。)")


def global_reply_text() -> str:
    return ("The add-on's reply memory reservation is full, so this request was not sent. Retry shortly. "
            "(外掛的回覆記憶體額度已滿，這個請求沒有送出，請稍後再試。)")


def streams_text(streams: int) -> str:
    return (f"This MCP URL already has {streams} open event streams (GET), the limit of its profile. Close MCP clients "
            "that are no longer used, or retry later; requests (POST) still work. "
            f"(這個 MCP 網址已經開著 {streams} 條事件串流（GET），是這個帳號的上限；請關閉不再使用的 MCP 用戶端或稍後再試，"
            "一般請求（POST）不受影響。)")


class Unavailable(Exception):
    """Which profile holds a token cannot be told now (contract 2.3): every token gets 503."""


class Reports(request_budget.Reports):
    """One WARNING per (profile, situation) a REPORT_SECONDS window (the PaaS gateway_pool report; HM-31 moved it to
    request_budget.Reports, which a switched-off add-on's budget uses too): the first one written, the others counted,
    and the next line written ends with suppressed=N, on this module's logger. text is complete fixed text (the profile
    by profiles.log_id, a limit): never a token, a URL, a label or request content."""

    def __init__(self):
        super().__init__(logger)


def _header(scope, name):
    return [value for key, value in scope['headers'] if key == name]


def json_content(scope) -> bool:
    """gateway.json_body's rule: the first Content-Type names application/json (parameters aside)."""
    values = _header(scope, b'content-type')
    return bool(values) and values[0].decode('latin-1').split(';')[0] == 'application/json'


class ProfileGate:
    """One profile's admission, stream cap and pending-reply budget on 8081 (see the module docstring); quota is its
    profiles.ProfileQuota, budget the add-on's request_budget.RequestBudget (budget_share: this profile's share, which
    its app charges). active and streams are what its requests hold now, reply_bytes its answers handed to the server
    and not taken by it yet (HM-30); beyond, the POSTs it serves beyond its admission (they carry no request: HM-31,
    MF-2 (b))."""

    def __init__(self, profile_id, quota, budget, reports, reply_memory=None):
        self.profile_id, self.quota, self.reports = profile_id, quota, reports
        self.reply_memory = reply_memory
        self.name = profiles.log_id(profile_id)
        self.active = self.streams = self.beyond = 0
        self.reply_bytes = 0  # HM-30: its answers handed to the server and not taken by it yet
        # make_apps slot_busy (HM-08: the busy answer; HM-14: the lanes' queue cap and reserve, and the answers and
        # WARNINGs that name this profile): the profile's app forwards with it.
        self.slot_busy = gateway.SlotBusy(queue=quota.queue, reserve=quota.reserved_notifications,
                                          wait=quota.forward_wait_seconds, answer=self.forward_busy,
                                          abandoned=self.forward_abandoned, interrupted=self.child_interrupted)
        # make_apps body_budget (HM-31): this profile's share of the add-on's request body budget
        self.budget_share = budget.share(profile_id, cap=quota.body_bytes, warn=self.warn)

    def warn(self, situation, text):
        self.reports.warn(self.profile_id, situation, f'MCP gateway [profile={self.name}]: {text}')

    def forward_busy(self, message, situation, lane):
        """gateway.SlotBusy.answer: a request of this profile found its lane's slots busy: it waited in vain (situation
        "wait") or the lane's queue was full ("queue"). Each lane names its own number of slots."""
        quota = self.quota
        reserved = lane == gateway.RESERVED_LANE
        slots = quota.reserved_notifications if reserved else quota.forward_slots
        kind = 'forwarding slots reserved for notifications' if reserved else 'forwarding slots'
        if situation == 'queue':
            self.warn(('queue', lane), f'{quota.queue} requests were waiting for one of its {slots} {kind}, its limit; '
                                       'new ones were answered busy (-32003) without waiting')
            return gateway.busy_reply(message, queue_text(quota.queue, slots, reserved))
        wait = quota.forward_wait_seconds
        if reserved:
            self.warn(('forward', lane), f'all {slots} {kind} stayed in use for {wait:g} s; notifications were answered '
                                         'busy (-32003) and not sent (its MCP server may be stuck)')
        else:
            self.warn('forward', f'all {slots} forwarding slots stayed in use for {wait:g} s; requests were answered '
                                 'busy (-32003) and not sent')
        return gateway.busy_reply(message, forward_text(slots, wait, reserved))

    def forward_abandoned(self, lane):
        """gateway.SlotBusy.abandoned: a client closed its connection while its request waited for a slot."""
        self.warn(('abandoned', lane), 'a client closed its connection while its request waited for a forwarding '
                                       'slot; the request was not sent')

    def child_interrupted(self, method, error, stopped):
        """gateway.SlotBusy.interrupted: the connection to this profile's child broke while it handled a request (the
        HTTP method and the httpx error's class name: no path, token or content)."""
        cause = 'the MCP server stopped' if stopped else 'the MCP server is still running'
        self.warn(('interrupted', stopped), f'the connection to its MCP server broke while it handled a {method} '
                                            f'request ({error}); {cause}; answered -32004')

    def pending_reply(self, message):
        """gateway.PENDING_REPLIES (HM-30): a tools/call about to be forwarded while this profile's answers not received
        yet hold its pending-reply budget or more: the busy answer, 200 + -32003 under its id; None: forward it."""
        limit = self.quota.pending_reply_bytes
        if self.reply_bytes < limit:
            return None
        self.warn('replies', f'its answers not received yet held {limit / MiB:g} MiB, its limit; new tools/call '
                             'requests were answered busy (-32003) and not sent')
        return gateway.busy_reply(message, pending_text(limit))

    async def serve(self, app, scope, receive, send):
        quota = self.quota
        stream = scope['method'] == 'GET'
        # 0.5.1 (F1): a GET stream takes no reply ticket (the ticket bounds only a POST that may carry a large reply), so
        # its limit is the profile's ordinary one (quota.get_streams: 24 default, 8 additional) and a POST still gets
        # its ticket and its forwarding slot while every stream is open. What a stream holds is bounded by its own
        # small numbers instead (reply_memory.STREAM_BYTES, STREAM_EVENT_BYTES).
        stream_cap = quota.get_streams
        if stream and self.streams >= stream_cap:
            self.warn('streams', f'{stream_cap} event streams (GET) were open, its limit; new ones were '
                                 'answered 429')
            return await gateway.stream_busy_reply(streams_text(stream_cap))(scope, receive, send)
        if self.active >= quota.admission:
            return await self.beyond_admission(app, scope, receive, send)
        self.active += 1
        self.streams += stream
        # HM-30: whether the answer declares its length (pieces then change no byte on the wire), and its bytes handed to
        # the server and not known to be taken by it yet (charged to reply_bytes). HM-30 review 2 MF-2: early, the bytes
        # the app charged before it handed them over (gateway.PENDING_CHARGE: charged to reply_bytes too, until they
        # are handed over or the request ends).
        started = framed = ticket = False
        held = early = 0
        # 0.5.1 (F1): a switched-on Odoo's GET stream (no ticket) is bounded by its own bytes.
        bounded = stream and self.reply_memory is not None

        def reserve_reply(message):
            nonlocal ticket
            if ticket:
                return None
            if self.reply_memory.take(self.profile_id):
                ticket = True
                return None
            self.warn('reply_memory', 'the add-on reply memory reservation was full; request answered busy (-32003) '
                                        'before forwarding')
            return gateway.busy_reply(message, global_reply_text())

        def charge(size):
            """gateway.PENDING_CHARGE (HM-30 review 2 MF-2): an answer of size bytes the app is about to hand over,
            charged from now on (before the request's forwarding slot is released)."""
            nonlocal early
            if ticket and held + early + size > self.reply_memory.TICKET_BYTES:
                raise BadRequest(502)
            early += size
            self.reply_bytes += size

        async def counted_send(message):
            nonlocal started, framed
            if message['type'] == 'http.response.start':
                started = True
                framed = any(name.lower() == b'content-length' for name, _ in message.get('headers', ()))
            elif message['type'] == 'http.response.body' and started:
                return await hand_over(message)
            await send(message)

        def stream_over(what):
            self.warn('stream_bytes', f'an event stream (GET) held more than {what} and was ended; its client '
                                      'reconnects')

        async def cut_stream():
            """0.5.1 (F1): end this GET stream cleanly (its client reconnects): one last empty body so the response is
            complete, within gateway.ENDING_SECONDS for a client that reads nothing, then StreamLimit stops the app's
            relay (serve() catches it). The log line names the cause, never a token or content."""
            stream_over(f'{reply_memory.STREAM_BYTES // 1024} KiB of replies the server had not taken')
            try:
                async with asyncio.timeout(gateway.ENDING_SECONDS):
                    await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
            except (TimeoutError, OSError, ClientDisconnect):
                pass
            raise gateway.StreamLimit

        async def hand_over(message):
            """HM-30: an answer's body, charged to the profile's answers not received yet until the server took it (the
            module docstring): what was handed over before it is taken once the server took this message. What the app
            charged early (charge) covers it as far as it goes."""
            nonlocal held, early
            body = message.get('body', b'')
            earlier = held
            covered = min(early, len(body))
            if ticket and held + len(body) + early - covered > self.reply_memory.TICKET_BYTES:
                raise BadRequest(502)
            if bounded and held + len(body) + early - covered > reply_memory.STREAM_BYTES:
                await cut_stream()
            held += len(body)
            early -= covered
            self.reply_bytes += len(body) - covered
            if framed and len(body) > REPLY_PIECE:
                for start in range(0, len(body), REPLY_PIECE):
                    await send({'type': 'http.response.body', 'body': body[start:start + REPLY_PIECE],
                                'more_body': True})
                if not message.get('more_body', False):
                    await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
            else:
                await send(message)
            held -= earlier
            self.reply_bytes -= earlier

        # The app reaches pending_reply and charge through its request's state (Starlette's request.state is
        # scope['state']); a copy, so nothing is written into the server's own dict.
        state = {**scope.get('state', {}), gateway.PENDING_REPLIES: self.pending_reply,
                 gateway.PENDING_CHARGE: charge}
        if self.reply_memory is not None:
            state[gateway.REPLY_RESERVE] = reserve_reply
            if bounded:
                event_limit = reply_memory.STREAM_EVENT_BYTES
                state[gateway.STREAM_GUARD] = (
                    event_limit, lambda what: stream_over(f'{event_limit // 1024} KiB in {what}'))
        scope = {**scope, 'state': state}
        try:
            try:
                await app(scope, receive, counted_send)
            except* gateway.StreamLimit:
                pass  # cut_stream ended the response; nothing for the server to see
        finally:
            self.active -= 1
            self.streams -= stream
            self.reply_bytes -= held + early
            if ticket:
                self.reply_memory.give(self.profile_id)

    async def beyond_admission(self, app, scope, receive, send):
        """The profile's admission is full (HM-31: HM-14 review MF-2 (b), the PaaS semantics; see the module docstring).
        A small POST is read: one carrying no request is served beyond the admission (the reserve's purpose: a
        notification can use the reserved lane when the body budget allows); any other is answered busy with its id.
        Anything else: busy, unread."""
        # Odoo's minimum charge must also cover the small POSTs inspected beyond
        # admission. Keep it until the response send completes, including a
        # notification handed to the app. Switched-off and other products have
        # no minimum and retain their existing path.
        reservation = None
        if scope['method'] == 'POST' and json_content(scope) and self.budget_share.budget.limits.small_minimum:
            reservation = self.budget_share.open()
            try:
                reservation.reserve_small()
            except request_budget.BudgetExceeded as exceeded:
                reservation.close()
                self.budget_share.warn('bytes', request_budget.budget_note(exceeded))
                return await gateway.busy_reply(None, request_budget.budget_text(exceeded))(scope, receive, send)
        try:
            return await self._beyond_admission_reserved(app, scope, receive, send, reservation)
        finally:
            if reservation is not None:
                reservation.close()

    async def _beyond_admission_reserved(self, app, scope, receive, send, reservation):
        quota = self.quota
        text = admission_text(quota.admission)
        message = None
        if scope['method'] == 'POST' and json_content(scope):
            # the gateway's one rule (HM-31 review S-6): none beside a Transfer-Encoding; read_small counts what arrives
            length = request_budget.declared_length(scope['headers'])
            body = None if length is not None and length > REFUSAL_BODY_LIMIT else await read_small(receive)
            if body is not None:
                message = small_message(body)
                if gateway.carries_no_request('POST', message):
                    self.beyond += 1
                    try:
                        # AnyMethod reuses this exact reservation while its
                        # body watcher parses/forwards the replayed bytes.
                        app_scope = ({**scope, 'state': {**scope.get('state', {}),
                                                      gateway.BODY_RESERVATION: reservation}}
                                     if reservation is not None else scope)
                        return await app(app_scope, replayed(body, receive), send)
                    finally:
                        self.beyond -= 1
        self.warn('admission', f'{quota.admission} requests were in progress, its limit; requests were answered busy '
                               '(-32003)')
        await gateway.busy_reply(message, text)(scope, receive, send)


async def read_small(receive):
    """A request's body when it ends within REFUSAL_BODY_LIMIT bytes and REFUSAL_READ_SECONDS, else None (larger, too
    slow, or its client left)."""
    body = bytearray()
    try:
        async with asyncio.timeout(REFUSAL_READ_SECONDS):
            while True:
                message = await receive()
                if message['type'] != 'http.request':
                    return None  # the client left
                body += message.get('body', b'')
                if len(body) > REFUSAL_BODY_LIMIT:
                    return None
                if not message.get('more_body', False):
                    return bytes(body)
    except TimeoutError:
        return None


def small_message(body):
    """body's JSON value as the gateway would read it (UTF-8, strict JSON, no lone surrogate), else None."""
    if not_utf8(body):
        return None
    try:
        value = strict_json(body)
        json.dumps(value, ensure_ascii=False).encode('utf-8')  # a lone surrogate: the gateway's 400
    except (ValueError, RecursionError):
        return None
    return value


def replayed(body, receive):
    """The receive of a request whose body was read already: that body once, then the server's own (the client
    leaving)."""
    pending = [{'type': 'http.request', 'body': body, 'more_body': False}]

    async def replay():
        if pending:
            return pending.pop()
        return await receive()
    return replay


class Credentials:
    """One profile's token as the dispatcher compares it, and its token and child token for the reply mask (plan 5.1
    point 4): the token's sha256 digest kept with the state file's signature, read again only when the signature
    changes (with st_ctime_ns for an additional profile: its reads never chmod, HM-07 review S-09; the default
    profile's store fchmods its state at every read). An additional profile's directory must stay the one opened
    (st_dev, st_ino; HM-07 review S-08). Same uid is no security boundary (DQ-37): this catches stray copies, not an
    attacker; the profile's app checks the token again with its store anyway."""

    def __init__(self, store, *, owned):
        self.store, self.owned = store, owned
        self.signature = self.digest = None
        self.values = ()  # the token and child token last read (a revoked token left out)
        self.directory = self._identity(store.directory) if owned else None

    @staticmethod
    def _identity(path):
        info = os.lstat(path)
        return info.st_dev, info.st_ino

    def refresh(self):
        """The digest of the profile's token now (None: revoked). ConfigError when it cannot be read or its directory
        is not the one opened; values then keep what was read last (the reply mask masks more, never less)."""
        try:
            if self.directory is not None and self._identity(self.store.directory) != self.directory:
                raise ConfigError('profile directory replaced')
            info = os.lstat(self.store.path)
        except OSError:
            raise ConfigError('profile state unavailable') from None
        signature = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size, info.st_nlink, info.st_mode,
                     info.st_ctime_ns if self.owned else None)
        if signature != self.signature:
            state = self.store.load()
            self.values = tuple(value for value in (state.token, state.child_token) if value)
            self.digest = None if state.token is None else hashlib.sha256(state.token.encode()).digest()
            self.signature = signature
        return self.digest


def _unrouted(*_):  # the endpoint of the dispatcher's matching routes: matched against, never called
    raise AssertionError('not an endpoint')


class McpDispatcher:
    """The 8081 application of a switched-on product (see the module docstring). manager is its
    profile_runtime.ProfileManager: profiles() (the default profile first, then index order), get(profile_id) and
    check() (Unavailable while the index or the profile data cannot be trusted)."""

    def __init__(self, manager, reports):
        self.manager, self.reports = manager, reports
        # The gateway's own templates; AnyMethod as the default app has it, so every method matches the path.
        self.secret_route = Route(gateway.SECRET_ROUTE, gateway.AnyMethod(_unrouted))
        self.mcp_route = Route(gateway.MCP_ROUTE, gateway.AnyMethod(_unrouted))
        self.ready_route = Route(gateway.READY_ROUTE, _unrouted)  # GET and HEAD, as the default app's readiness

    @property
    def default_app(self):
        return self.manager.get(profiles.DEFAULT_PROFILE).runtime.mcp_app

    @property
    def routes(self):
        """The routes it serves: the default profile's app's (every profile's app has the same three)."""
        return self.default_app.routes

    def candidate(self, scope) -> bytes | None:
        """The token a request names where the gateway reads one, as bytes: the secret path's segment (UTF-8, as
        gateway.secret_valid hashes it), or exactly one literal "Bearer <token>" on /mcp; else None."""
        match, child = self.secret_route.matches(scope)
        if match is Match.FULL:
            return child['path_params']['secret'].encode('utf-8', 'replace')
        if self.mcp_route.matches(scope)[0] is Match.FULL:
            values = _header(scope, b'authorization')
            if len(values) == 1 and values[0].startswith(b'Bearer '):
                return values[0][len(b'Bearer '):]
        return None

    def resolve(self, candidate: bytes):
        """The registered profiles whose token is candidate: every routable profile compared once, whatever matched
        before (plan 5.1 point 2). Unavailable when the index or the default profile's state cannot be trusted."""
        self.manager.check()
        supplied = hashlib.sha256(candidate).digest()
        if supplied in self.manager.revoke_fence:
            raise Unavailable()  # HM-13c: a "revoke all" could not revoke it
        found = []
        for entry in self.manager.profiles():
            try:
                digest = entry.credentials.refresh()
            except ConfigError:
                if entry.profile_id == profiles.DEFAULT_PROFILE:
                    raise Unavailable() from None
                continue  # not routed (FM-05)
            if digest is not None and compare_digest(supplied, digest):
                found.append(entry)
        return found

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.default_app(scope, receive, send)
        candidate = self.candidate(scope)
        if candidate is None:
            if self.ready_route.matches(scope)[0] is Match.FULL and not self.manager.serves_mcp():
                return await JSONResponse({'ready': False}, status_code=503)(scope, receive, send)
            return await self.default_app(scope, receive, send)
        try:
            found = self.resolve(candidate)
        except Unavailable:
            return await JSONResponse({'error': 'state unavailable'}, status_code=503)(scope, receive, send)
        if not found:
            return await self.default_app(scope, receive, send)
        if len(found) > 1:
            group = tuple(entry.profile_id for entry in found)
            names = ', '.join('profile=' + profiles.log_id(profile_id) for profile_id in group)
            self.reports.warn(group, 'shared token',
                              f'MCP gateway: a token is held by more than one profile ({names}); its requests are '
                              'refused (503) and no profile serves them')
            return await JSONResponse({'error': 'state unavailable'}, status_code=503)(scope, receive, send)
        entry, = found
        await entry.gate.serve(entry.runtime.mcp_app, scope, receive, send)


# ---- 8099 of a switched-on product: the management dispatcher (HM-10) ----

PROFILE_HEADER = 'x-mcp-profile'
ALL_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE')
GLOBAL_PREFIX = 'profiles'
ORIGIN_POLICY = 'origin-policy'  # HM-27: the add-on's Origin policy of the secret path (a global path of its own)


def label_shape(value):
    """Step 5 of a profile creation or rename: exactly {"label": <string>}."""
    return isinstance(value, dict) and set(value) == {'label'} and isinstance(value['label'], str)


@dataclass(frozen=True)
class GlobalRoute:
    """One global management path (contract 3.1: X-MCP-Profile is never read there): each method's ProfileAdmin
    handler and whether it takes a JSON body, of the shape step 5 checks without reading any state (label_shape:
    exactly {"label": <string>}; HM-27's Origin policy: origin_policy.request_shape; a fixed 400 otherwise); "{id}" is
    one path segment, a profile id (the default profile's or 24 lowercase hexadecimal characters), "{name}" one, a
    quarantine directory's name as the API shows it (HM-13c: <id>-<UTC>[-n], profiles.quarantine_directory_name):
    anything else is a fixed 400 at step 5. The handler gets the segments in their order."""
    template: str
    methods: dict
    shape: object = label_shape

    def allows(self):
        return tuple(method for method in ALL_METHODS if method in self.methods)


# The global paths (contract 3.1), matched in this order (an exact path before "profiles/{id}"); every other path under
# profiles/ is an unknown operation (404 after the role check, as today). tests/test_admin_pipeline_matrix.py generates
# its refusal matrix from this table and gateway.PROFILE_OPERATIONS. HM-13c: "revoke all", the restore record, a
# restore review and a quarantine directory's deletion. HM-27: the Origin policy (its handlers answer an unknown
# operation's 404 for a product with its own rule, Headscale).
GLOBAL_ROUTES = (
    GlobalRoute('profiles', {'GET': ('list', False), 'POST': ('create', True)}),
    GlobalRoute('profiles/index/quarantine', {'POST': ('quarantine', False)}),
    GlobalRoute('profiles/revoke-all', {'POST': ('revoke_all', False)}),
    GlobalRoute('profiles/restore-record', {'GET': ('restore_record', False)}),
    GlobalRoute('profiles/quarantine/{name}/delete', {'POST': ('delete_quarantined', False)}),
    GlobalRoute('profiles/{id}/restore-review', {'POST': ('restore_review', False)}),
    GlobalRoute('profiles/{id}', {'PATCH': ('rename', True), 'DELETE': ('delete', False)}),
    GlobalRoute(ORIGIN_POLICY, {'GET': ('origin_policy', False), 'PUT': ('save_origin_policy', True)},
                origin_policy.request_shape),
)
PLACEHOLDERS = ('{id}', '{name}')


def global_route(operation):
    """(route, {placeholder: segment}) of a global operation, in the template's order; (None, {}) for an unknown one
    under profiles/. A placeholder is one non-empty segment."""
    wanted = operation.split('/')
    for route in GLOBAL_ROUTES:
        parts = route.template.split('/')
        if len(parts) != len(wanted):
            continue
        found = {}
        for part, segment in zip(parts, wanted):
            if part in PLACEHOLDERS:
                if not segment:
                    break
                found[part] = segment
            elif part != segment:
                break
        else:
            return route, found
    return None, {}


def valid_segments(found):
    """Step 5's check of a global path's segments (no state read): a profile id, a quarantine directory's name."""
    return (('{id}' not in found or profiles.PROFILE_ID.fullmatch(found['{id}']) is not None)
            and ('{name}' not in found or profiles.quarantine_directory_name(found['{name}']) is not None))


def is_global(operation):
    return operation in (GLOBAL_PREFIX, ORIGIN_POLICY) or operation.startswith(GLOBAL_PREFIX + '/')


class AdminDispatcher:
    """The 8099 application of a switched-on product (multi-profile plan 5.3; contract 3.1-3.3; FM-53, FM-54, FM-148;
    invariants I10, I12), built by profile_runtime.ProfileManager: one shared management pipeline for every path,
    global or profile-scoped, a page or an asset, with the add-on's one AdminAuthority and 16 management slots:

    - the page checks (gateway.management_operation, as a switched-off product runs them): identity, no '%', backslash
      pair or query; a page written to: PUT, POST 404 and PATCH, DELETE Starlette's 405 (as before, after the identity
      check now);
    - steps 1 to 4 (gateway.management_exchange, as admin_api runs them): identity, a management slot, the bounded body
      read (a JSON body only for an operation that takes one), the disconnect watch;
    - step 5: the method table (PATCH and DELETE only on profiles/{id}: anywhere else Starlette's 405 with the path's
      methods; a global path's other methods the same) and the request's shape where no state is read (a global
      path's {"label": <string>}, HM-27's {"mode": <string>, "allowed_origins": [<string>...]}, and its profile id:
      a fixed 400);
    - step 6: the first role check (AdminAuthority.verify: 403, core_version_unreviewed for an unreviewed Core). A
      caller who is not an administrator gets no further: every answer that depends on any profile's state comes
      after it, so every such caller gets the same bytes whatever exists (I10);
    - then a global path: ProfileAdmin (steps 8 to 11, its own second role check; never X-MCP-Profile); a page or an
      asset: the default profile's action (its lock, its final role check, the asset, as before);
    - a profile-scoped path (every other {base}/api/ path): step 7, exactly one X-MCP-Profile, "default" or 24
      lowercase hexadecimal characters (missing: 400 profile_id_required; two or more, or another value: 400
      profile_id_invalid; an id the index does not list: 404 profile_not_found, never the default profile instead;
      an unusable index: 503 profile_index_corrupt), then that profile's own action (steps 8 to 11: its lock, the
      validation on its state, its final role check, If-Match, receipts, the commit) with its echo (I12).

    The profile is chosen after the first role check, so no profile's app can be the entry: each one's action is
    called directly (ProfileRuntime.admin_action). There is no path fallback (contract 3.7): the user kept the header
    (UC-10, 2026-11-15 15:3x) until HM-03a proves the Ingress drops it; {base}/api/p/<id>/... is an unknown operation."""

    def __init__(self, manager, admin):
        self.manager, self.admin = manager, admin  # profile_runtime.ProfileManager, profile_admin.ProfileAdmin
        self.app = gateway.management_app(self.serve, ALL_METHODS)

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)

    @property
    def routes(self):
        """Its application's one route (every path), as an admin app's, for whoever looks (the MCP dispatcher too)."""
        return self.app.routes

    async def serve(self, request):
        authority, slots = self.manager.shared.authority, self.manager.shared.slots
        _, operation = gateway.management_operation(request, authority.identity)
        method = request.method
        route, segments = None, {}
        if operation == '__ui__':
            if method in ('PATCH', 'DELETE'):
                return gateway.method_not_allowed(gateway.MANAGEMENT_METHODS)
            if method not in ('GET', 'HEAD'):
                raise BadRequest(404)
            takes_json = False
        elif is_global(operation):
            route, segments = global_route(operation)
            takes_json = route is not None and route.methods.get(method, (None, False))[1]
        else:
            takes_json = operation in gateway.JSON_OPERATIONS and method == 'PUT'

        async def step(request, user, base, csrf, value, peer_disconnected, committed):
            # Step 5: the method table and the request's shape; no state is read.
            if is_global(operation) and route is not None:
                if method not in route.methods:
                    return gateway.method_not_allowed(route.allows())
                if takes_json and not route.shape(value):
                    raise BadRequest()
                if not valid_segments(segments):
                    raise BadRequest()
            elif operation != '__ui__' and not is_global(operation) and method in ('PATCH', 'DELETE'):
                return gateway.method_not_allowed(gateway.MANAGEMENT_METHODS)
            # Step 6: the first role check.
            await authority.verify(user)
            if peer_disconnected.is_set():
                raise BadRequest(403)
            if is_global(operation):
                if route is None:
                    return Response(status_code=404)  # an unknown operation, as a profile's action answers it
                handler = getattr(self.admin, route.methods[method][0])
                call = Call(request, user, value, peer_disconnected, committed)
                return await handler(call, *segments.values())
            entry = (self.manager.get(profiles.DEFAULT_PROFILE) if operation == '__ui__'
                     else self.profile(request))  # step 7
            return await entry.runtime.admin_action(request, user, base, csrf, value, peer_disconnected, committed)

        return await gateway.management_exchange(request, authority.identity, slots,
                                                 lambda request: gateway.management_value(request, takes_json), step)

    def profile(self, request):
        """Step 7: the profile a profile-scoped request names (see the class docstring)."""
        values = request.headers.getlist(PROFILE_HEADER)
        if not values:
            raise BadRequest(400, {'code': 'profile_id_required'})
        if len(values) != 1 or not profiles.PROFILE_ID.fullmatch(values[0]):
            raise BadRequest(400, {'code': 'profile_id_invalid'})
        if values[0] == profiles.DEFAULT_PROFILE:
            return self.manager.get(profiles.DEFAULT_PROFILE)
        return self.admin.profile_entry(values[0])
