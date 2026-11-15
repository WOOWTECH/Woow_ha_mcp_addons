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
  /health/ready (which speaks for the default profile, DQ-19) then answers not ready, as the default app does when its
  state cannot be read; any other path keeps the default app's answer.

Every profile's own limits (ProfileGate; plan 5.2; contract 5; I8; DQ-07 (a)): before a request's body is read, its
profile's admission (64 for the default profile, 32 for an additional one; a request with no candidate or no match
takes none); while it is read and until it ends, the profile's byte budget (64 MiB each, the default profile's
included: C1-M5). A request is charged max(the declared Content-Length up to gateway.MAX_REQUEST, the bytes read so far,
the size of the body its app forwards to the child) from admission until it ends (its answer sent or its client gone),
not only until its answer starts (HM-08 review MF-1): a child answers a request with an event stream whose headers come
before its tool runs (mcp 2.3.0 and FastMCP 4.1.3 do by default), and the gateway's forwarded copy of the body stays
referenced by the child's response (httpx keeps the request on it) until that stream ends. The forwarded size is the
gateway's own re-serialization (ASCII escapes: a 4-byte UTF-8 character is forwarded as 12 bytes, a CJK one as 6;
review S-1): the app reports it before sending (gateway.FORWARDED_BODY in the request's state), and a body the budget
cannot hold then is not sent: 200 + -32003 under its id (503, id null, without one). A GET (an event stream) takes one
of the profile's stream places (24, 8). No pool is shared. A request refused before its body is read (admission full,
or a declared length over what is left of the budget) is read with the add-on's refusal allowance (RefusalAllowance: 8
at once, 512 KiB in all, at most 64 KiB and 2 s each; the add-on's one shared pool) only to find its JSON-RPC id: with
one, 200 and a -32003 error under it; otherwise 503, id null; both Retry-After 5 (gateway.busy_reply; the PaaS table,
with HA's one deviation: a body over 64 KiB, or one the allowance has no room for, gets 503, plan 8.8 #16). A body that
grows past the budget while it is read is cut off at once: the profile's app sees the client leave, its answer is
replaced by 503 + -32003 id null, nothing of it reaches the child and its bytes are given back. A GET past the stream
cap: 429 + -32003 id null + Retry-After 30, at once. The profile's app answers a forwarding slot that stays busy for a
second the same way (ProfileGate.slot_busy, make_apps slot_busy). Each limit writes one WARNING per profile and
situation a minute (Reports: id's first 8 characters, suppressed=N), never a token, URL, label or request content. The
-32003 texts are fixed and provisional (HM-14 settles them).

What the budget bounds is the bytes of a profile's requests, not every byte they cost: parsing a body costs more than
its size (many small objects or arrays: about 24 times, contract 5), and the 8081 listener's connections are one bound
of the whole add-on (uvicorn's limit_concurrency counts idle keep-alive connections and those of clients without a
token too: when it is full, a new connection gets uvicorn's plain-text 503 whatever its profile; HM-08 review S-5,
known since G2 S7). The isolation of one profile from another holds per request.

The reply mask (plan 5.1 point 8, DQ-40 (a) ⑧): the manager's reply_secrets() gives every profile's app every token
and child token the add-on holds (make_apps reply_secrets). Not here: queue limits, the notification reserve and the
-32004/-32005 endings (HM-14), the pending-reply budget and the reply worker (HM-30), the management dispatcher
(HM-10), Origin reporting (HM-27).
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
from hmac import compare_digest
import json
import logging
import os
import time

from starlette.responses import JSONResponse
from starlette.routing import Match, Route

from . import gateway, profiles
from .config import ConfigError, strict_json

logger = logging.getLogger(__name__)

# The refusal allowance (contract 2.4): what the add-on reads of refused requests to find their JSON-RPC ids.
REFUSAL_BODY_LIMIT = 64 * 1024
REFUSAL_READ_SECONDS = 2
REFUSAL_SLOTS = 8
REFUSAL_BYTES = 512 * 1024
# One WARNING per profile and situation this often (the PaaS gateway_pool.REPORT_INTERVAL_SECONDS), remembering at most
# this many situations.
REPORT_SECONDS = 60
MAX_REPORT_KEYS = 64
MiB = 1024 * 1024


# ---- the -32003 texts (provisional; HM-14 settles them): which limit, and "retry shortly" ----

def admission_text(limit: int) -> str:
    return (f"This MCP URL already has {limit} requests in progress, the limit of its profile, so this request was not "
            "read or sent. Retry shortly. "
            f"(這個 MCP 網址同時進行中的請求已達這個帳號的上限 {limit} 個，這個請求沒有讀取也沒有送出，請稍後再試。)")


def bytes_text(limit: int) -> str:
    size = f'{limit / MiB:g} MiB'
    return (f"The requests of this MCP URL in progress already hold {size}, the limit of its profile, so this request "
            "was not sent. Retry shortly. "
            f"(這個 MCP 網址進行中的請求內容已達這個帳號的上限 {size}，這個請求沒有送出，請稍後再試。)")


def forward_text(slots: int, wait: float) -> str:
    return (f"All {slots} connections of this MCP URL to its MCP server are in use; waited {wait:g} s without a free "
            "one, so this request was not sent. Retry shortly. "
            f"(這個 MCP 網址送往 MCP 子程式的 {slots} 條連線都在使用中，等了 {wait:g} 秒仍沒有空出來，這個請求沒有送出，"
            "請稍後再試。)")


def streams_text(streams: int) -> str:
    return (f"This MCP URL already has {streams} open event streams (GET), the limit of its profile. Close MCP clients "
            "that are no longer used, or retry later; requests (POST) still work. "
            f"(這個 MCP 網址已經開著 {streams} 條事件串流（GET），是這個帳號的上限；請關閉不再使用的 MCP 用戶端或稍後再試，"
            "一般請求（POST）不受影響。)")


class Unavailable(Exception):
    """Which profile holds a token cannot be told now (contract 2.3): every token gets 503."""


class Reports:
    """One WARNING per (profile, situation) a REPORT_SECONDS window (the PaaS gateway_pool report): the first one
    written, the others counted, and the next line written ends with suppressed=N. text is complete fixed text (the
    profile by profiles.log_id, a limit): never a token, a URL, a label or request content. At most MAX_REPORT_KEYS
    situations are remembered (expired ones go first, then the oldest)."""

    def __init__(self):
        self.clock = time.monotonic
        self.state = OrderedDict()  # (profile, situation) -> [when the next line may be written, suppressed]

    def warn(self, profile, situation, text):
        now = self.clock()
        key = (profile, situation)
        entry = self.state.get(key)
        if entry is not None and now < entry[0]:
            entry[1] += 1
            return
        suppressed = entry[1] if entry is not None else 0
        self.state.pop(key, None)
        if len(self.state) >= MAX_REPORT_KEYS:
            for stale in [name for name, value in self.state.items() if value[0] <= now]:
                del self.state[stale]
            while len(self.state) >= MAX_REPORT_KEYS:
                self.state.popitem(last=False)
        self.state[key] = [now + REPORT_SECONDS, 0]
        logger.warning(text + (f' suppressed={suppressed}' if suppressed else ''))


def _header(scope, name):
    return [value for key, value in scope['headers'] if key == name]


def declared_length(scope) -> int | None:
    """The request's Content-Length when it states exactly one (h11 refuses a malformed one), else None."""
    values = _header(scope, b'content-length')
    if len(values) != 1 or not values[0].isdigit() or len(values[0]) > 19:
        return None
    return int(values[0])


def json_content(scope) -> bool:
    """gateway.json_body's rule: the first Content-Type names application/json (parameters aside)."""
    values = _header(scope, b'content-type')
    return bool(values) and values[0].decode('latin-1').split(';')[0] == 'application/json'


class RefusalAllowance:
    """The add-on's allowance for reading the body of a refused request to find its JSON-RPC id (contract 2.4), shared
    by every profile: at most `slots` read at once and `budget` bytes reserved in all (a request without a declared
    length reserves REFUSAL_BODY_LIMIT), each at most REFUSAL_BODY_LIMIT bytes and REFUSAL_READ_SECONDS."""

    def __init__(self, slots=REFUSAL_SLOTS, budget=REFUSAL_BYTES):
        self.slots, self.budget = slots, budget
        self.active = self.reserved = 0

    async def read_message(self, scope, receive, length):
        """The JSON value of the request's body when it can be read within the allowance and is a body the gateway
        would parse (application/json, strict JSON, no lone surrogate), else None. Nothing is read when the declared
        length is over REFUSAL_BODY_LIMIT, the body is not application/json, or the allowance is in use."""
        if length is not None and length > REFUSAL_BODY_LIMIT or not json_content(scope):
            return None
        reserve = REFUSAL_BODY_LIMIT if length is None else length
        if self.active >= self.slots or self.reserved + reserve > self.budget:
            return None
        self.active += 1
        self.reserved += reserve
        body = bytearray()
        try:
            async with asyncio.timeout(REFUSAL_READ_SECONDS):
                while True:
                    message = await receive()
                    if message['type'] != 'http.request':
                        return None  # the client left
                    body += message.get('body', b'')
                    if len(body) > reserve:
                        return None
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            return None
        finally:
            self.active -= 1
            self.reserved -= reserve
        try:
            value = strict_json(bytes(body))
            json.dumps(value, ensure_ascii=False).encode('utf-8')  # a lone surrogate: the gateway's 400, no id here
        except (ValueError, RecursionError):
            return None
        return value


class ProfileGate:
    """One profile's admission, byte budget and stream cap on 8081 (see the module docstring); quota is its
    profiles.ProfileQuota. active, body_bytes and streams are what its requests hold now."""

    def __init__(self, profile_id, quota, allowance, reports):
        self.profile_id, self.quota, self.allowance, self.reports = profile_id, quota, allowance, reports
        self.name = profiles.log_id(profile_id)
        self.active = self.body_bytes = self.streams = 0

    def warn(self, situation, text):
        self.reports.warn(self.profile_id, situation, f'MCP gateway [profile={self.name}]: {text}')

    def slot_busy(self, message):
        """make_apps slot_busy: a request of this profile waited for one of its forwarding slots in vain."""
        slots, wait = self.quota.forward_slots, self.quota.forward_wait_seconds
        self.warn('forward', f'all {slots} forwarding slots stayed in use for {wait:g} s; requests were answered busy '
                             '(-32003) and not sent')
        return gateway.busy_reply(message, forward_text(slots, wait))

    async def refuse(self, situation, text, note, scope, receive, send, length):
        """A request refused before its body is read: its id looked for (a POST only) with the refusal allowance."""
        self.warn(situation, note)
        message = await self.allowance.read_message(scope, receive, length) if scope['method'] == 'POST' else None
        await gateway.busy_reply(message, text)(scope, receive, send)

    async def serve(self, app, scope, receive, send):
        quota = self.quota
        stream = scope['method'] == 'GET'
        if stream and self.streams >= quota.get_streams:
            self.warn('streams', f'{quota.get_streams} event streams (GET) were open, its limit; new ones were '
                                 'answered 429')
            return await gateway.stream_busy_reply(streams_text(quota.get_streams))(scope, receive, send)
        length = declared_length(scope)
        reserved = 0 if length is None else min(length, gateway.MAX_REQUEST)
        if self.active >= quota.admission:
            return await self.refuse('admission', admission_text(quota.admission),
                                     f'{quota.admission} requests were in progress, its limit; requests were answered '
                                     'busy (-32003) without being read', scope, receive, send, length)
        if self.body_bytes + reserved > quota.body_bytes:
            return await self.refuse('bytes', bytes_text(quota.body_bytes), self.bytes_note(), scope, receive, send,
                                     length)
        self.active += 1
        self.streams += stream
        self.body_bytes += reserved
        # What this request holds of the budget (max of the three below, from admission until it ends), what was read
        # of its body, and the size its app forwards to the child (0 until it reports it).
        charged, read, forwarded = reserved, 0, 0
        cut = started = replaced = False

        def give_back():
            nonlocal charged
            self.body_bytes -= charged
            charged = 0

        async def counted_receive():
            nonlocal charged, read, cut
            if cut:
                return {'type': 'http.disconnect'}
            message = await receive()
            size = len(message.get('body', b'')) if message['type'] == 'http.request' and not started else 0
            if size:
                needed = max(reserved, read + size, forwarded)
                if self.body_bytes + needed - charged > quota.body_bytes:
                    cut = True  # this chunk is not handed on; the app sees the client leave
                    give_back()
                    self.warn('bytes', self.bytes_note())
                    return {'type': 'http.disconnect'}
                read += size
                self.body_bytes += needed - charged
                charged = needed
            return message

        def forwarding(message, size):
            """gateway.FORWARDED_BODY: the app re-serialized the request's body for its child as size bytes. Charged
            when it is more than this request holds; None to send it, or the busy answer when the budget cannot hold it
            (200 + -32003 under its id; the child never gets it)."""
            nonlocal charged, forwarded
            needed = max(charged, size)
            if self.body_bytes + needed - charged > quota.body_bytes:
                self.warn('bytes', self.bytes_note())
                return gateway.busy_reply(message, bytes_text(quota.body_bytes))
            forwarded = size
            self.body_bytes += needed - charged
            charged = needed
            return None

        async def busy_instead():
            nonlocal replaced
            replaced = True
            await gateway.busy_reply(None, bytes_text(quota.body_bytes))(scope, receive, send)

        async def counted_send(message):
            nonlocal started
            if cut and not started:
                if not replaced:  # the app's answer to the cut read (its 403 for a client that left)
                    await busy_instead()
                return
            if message['type'] == 'http.response.start':
                # The bytes stay charged until the request ends (the finally below): an event stream's headers come
                # before its tool runs, and the forwarded body stays referenced until the stream ends (review MF-1).
                started = True
            await send(message)

        # The app reaches forwarding through its request's state (Starlette's request.state is scope['state']); a copy,
        # so nothing is written into the server's own dict.
        scope = {**scope, 'state': {**scope.get('state', {}), gateway.FORWARDED_BODY: forwarding}}
        try:
            await app(scope, counted_receive, counted_send)
            if cut and not started and not replaced:
                await busy_instead()
        finally:
            self.active -= 1
            self.streams -= stream
            give_back()

    def bytes_note(self):
        return (f'its requests in progress held {self.quota.body_bytes / MiB:g} MiB, its limit; requests were answered '
                'busy (-32003)')


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
