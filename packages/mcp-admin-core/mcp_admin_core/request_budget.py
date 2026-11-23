"""The gateway's request body byte budget (multi-profile plan 12.3 HM-31; contract 2.4, 5; the PaaS gateway of #155,
woow-mcp-server d7f5849: request_budget.py, proxy.py, docs/mcp-gateway-limits.md). Not gated: every product, switched on
or off (the user's decision of 2026-11-16, contract 1.2).

Why: a count of requests says nothing of their memory. Before it, a switched-off add-on read up to 64 requests of 16 MiB
at once (8081's limit_concurrency) and parsing one costs many times its size (PaaS sandbox: 1 GiB pods OOM-killed by
32 requests of 4 MiB; HM-08: many small objects 24 times). HM-08's per-profile byte budget (64 MiB, switched-on
products only) is merged into this one budget, with the PaaS rules: not two budgets on top of each other.

One budget of the add-on (RequestBudget), two layers, both must hold (PaaS):

- the whole add-on (BudgetLimits.total): every profile's request bodies together;
- each profile's share (Share.limit): min(the profile's quota, profiles.ProfileQuota.body_bytes = 64 MiB: DQ-07's value
  kept as the share's ceiling, HA stricter than PaaS), max(16 MiB, total / 2)). One profile filling its share leaves the
  others theirs; every profile can always hold one request of the single-request ceiling (16 MiB) unless the others
  hold the whole budget.

What is charged (Reservation): a request's body bytes, from the moment its body is read (a declared Content-Length
before a byte is read: refused then, nothing read into memory; and every byte as it arrives, whatever was declared: a
Content-Length beside a Transfer-Encoding declares nothing, HM-31 review MF-1) until the request ends (its
answer sent in full, an event stream's last byte included, or its client gone: the gateway's forwarded copy of the body
stays referenced until then, HM-08 review MF-1). HA re-serializes a body before forwarding it (ASCII escapes: a CJK
character 6 bytes, an emoji 12; a number in Python's own form), so the larger of what was read and what is forwarded is
charged (HM-08 review S-1; PaaS forwards the bytes it read). Not charged, never refused (PaaS): a small request (at most
SMALL_REQUEST_BYTES both read and forwarded: notifications, the usual tool calls, initialize, GET, DELETE), so the
notification reserve keeps its purpose; a body over the single-request ceiling (16 MiB, n8n 4 MiB), which is refused as
too large anyway. Switched-on Odoo is stricter: every POST reserves at least 64 KiB before its first body read and
keeps that charge until the response ends, so parsed small bodies are covered by the shared admission factor.

The defaults (BudgetLimits.derive; constants provisional until HM-19c measures the target hardware, contract 5):

    total = (ceiling - GATEWAY_BASELINE_MIB - accounts x child MiB - SAFETY_MARGIN_MIB) / AMPLIFICATION,
            within MIN_BUDGET_BYTES (16 MiB) and MAX_BUDGET_BYTES (16 GiB);
            FALLBACK_TOTAL_BYTES (32 MiB) with no ceiling

- ceiling: the container's cgroup memory limit when it has one (PaaS); an HA add-on has none (Supervisor sets no memory
  limit; HM-03a confirms on HAOS), so MemAvailable of /proc/meminfo less HOST_RESERVE_MIB (256 MiB, the plan's
  "MemAvailable - 保留量", plan 5.2) when the budget is made (at startup); neither readable: the fixed fallback. Both
  are read with HM-09's readers, the ones the profile capacity and the memory check use (profiles.memory_limit_mib,
  available_memory_mib; HM-31 review S-6: no copy of them here);
- accounts: 1 switched off (the default profile alone), 1 + the product's additional-profile capacity switched on (PaaS:
  1 + current_profile_capacity().limit); child MiB: profiles.CHILD_MEMORY_MIB (160 when the product names none).

Single-threaded (the event loop): no lock, no await, every count update is atomic. No environment variable is read:
HA's limits are program constants (contract 9, #45); the PaaS variables MCP_GATEWAY_MAX_BUFFERED_BYTES and the others
change nothing here.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import logging
import time
from typing import Callable

from starlette.requests import ClientDisconnect

from . import profiles, reply_memory
from .capacity_metrics import active_metrics
from .request_limits import ID_WINDOW, head_tail_id  # noqa: F401  (head_tail_id: the gateway's)

logger = logging.getLogger(__name__)
MiB = 1024 * 1024

#: The single-request ceiling (gateway.MAX_REQUEST): every share can hold one of these, so both layers' floor.
MIN_BUDGET_BYTES = 16 * MiB
MAX_BUDGET_BYTES = 16 * 1024 * MiB
#: A request of at most this many bytes (read and forwarded) is never charged nor refused by the budget (PaaS).
SMALL_REQUEST_BYTES = 64 * 1024
#: The memory a request body's byte costs in the gateway and its child together, under the structure guard, for valid
#: UTF-8 (PaaS d7f5849, measured with a real uvicorn gateway and MCP SDK child: one ASCII string 5.5, the guard's worst
#: structure 8.0, one non-BMP character in a large string 15.2, both together 17.8; HM-19c measures HA's own).
AMPLIFICATION = 20.0
# HM-19c: Odoo's release gate remains 20x. The larger number here is a
# conservative *admission* factor while the near-200k-element shape's measured
# gateway-plus-child peak is unresolved. It must never be reported as a pass.
ODOO_ADMISSION_AMPLIFICATION = 64.0
ODOO_REPLY_RESERVE_MIB = 512
ODOO_REPLY_WORK_MIB = 221       # ceil(8 MiB * 27.6)
# 0.5.1 (F1): event streams (GET) take no reply ticket; each is bounded by reply_memory.STREAM_BYTES instead. The most
# that can be open at once: the default profile's 24 plus every additional profile's 8 (profiles.*_PROFILE_QUOTA).
ODOO_MAX_STREAMS = (profiles.DEFAULT_PROFILE_QUOTA.get_streams
                    + profiles.EXTRA_PROFILE_LIMITS['odoo'] * profiles.EXTRA_PROFILE_QUOTA.get_streams)
ODOO_STREAM_RESERVE_MIB = -(-ODOO_MAX_STREAMS * reply_memory.STREAM_BYTES // MiB)   # 64 streams x 1 MiB = 64
# Every Odoo POST holds at least this much of the shared body budget before parsing.
# The 64x admission factor reserves 4 MiB for a <=64 KiB parsed body.
ODOO_SMALL_MINIMUM_BYTES = SMALL_REQUEST_BYTES
GATEWAY_BASELINE_MIB = 76      # the gateway's own baseline (PaaS sandbox 71-76 MiB)
SAFETY_MARGIN_MIB = 150        # what is left for peaks (GC, a child growing, logs) with every budget full
FALLBACK_TOTAL_BYTES = 32 * MiB
PER_PROFILE_FRACTION = 0.5
DEFAULT_CHILD_MEMORY_MIB = 160
#: Kept for the host when MemAvailable is the ceiling: an add-on shares the machine with HA Core and every other add-on
#: (the plan's reserve, profiles.PROFILE_MEMORY_RESERVE_MIB).
HOST_RESERVE_MIB = profiles.PROFILE_MEMORY_RESERVE_MIB
#: A large request (declared over SMALL_REQUEST_BYTES, or no Content-Length) that sends nothing for this long is
#: dropped: 408 and its bytes given back (PaaS MCP_GATEWAY_BODY_IDLE_SECONDS default). The whole read stays bounded by
#: the gateway's own BODY_SECONDS (60 s, every request; PaaS 300 s for large ones only).
BODY_IDLE_SECONDS = 30.0

REPORT_SECONDS = 60
MAX_REPORT_KEYS = 256


# ---- the memory the defaults are derived from: HM-09's readers (profiles.memory_limit_mib, available_memory_mib) ----

def memory_ceiling() -> tuple[int | None, str]:
    """(the memory the budget is derived from, in MiB, or None; where it came from): 'cgroup' (the container's limit,
    profiles.memory_limit_mib), 'meminfo' (MemAvailable less HOST_RESERVE_MIB, never below 0; profiles.
    available_memory_mib, not read when there is a limit) or 'none'. Read when called (HM-31 review S-6: the readers the
    profile capacity and the memory check use, not a copy of them)."""
    limit = profiles.memory_limit_mib()
    if limit is not None:
        return limit, 'cgroup'
    available = profiles.available_memory_mib()
    if available is not None:
        return max(0, available - HOST_RESERVE_MIB), 'meminfo'
    return None, 'none'


def default_total_bytes(ceiling_mib: int | None, *, accounts: int = 1,
                        child_memory_mib: int = DEFAULT_CHILD_MEMORY_MIB) -> int:
    """The add-on's budget (request body bytes) for a ceiling (PaaS default_total_bytes): every account's child and the
    gateway's baseline taken off, the safety margin kept, divided by AMPLIFICATION; within the floor and the ceiling of
    a budget; FALLBACK_TOTAL_BYTES without a ceiling."""
    if ceiling_mib is None:
        return FALLBACK_TOTAL_BYTES
    available = ceiling_mib - GATEWAY_BASELINE_MIB - accounts * child_memory_mib - SAFETY_MARGIN_MIB
    derived = int(max(0, available) * MiB / AMPLIFICATION)
    return min(MAX_BUDGET_BYTES, max(MIN_BUDGET_BYTES, derived))


def odoo_switched_total_bytes(ceiling_mib: int | None, accounts: int, source: str) -> int:
    """Joint body/reply planning cap; cgroup also keeps the 256 MiB host reserve.

    The caller checks odoo_switched_memory_fits before enabling multi-profile
    admission: the 16 MiB floor alone cannot make a low ceiling safe.
    """
    if ceiling_mib is None:
        return MIN_BUDGET_BYTES
    available = (ceiling_mib - (HOST_RESERVE_MIB if source == 'cgroup' else 0)
                 - GATEWAY_BASELINE_MIB - accounts * 100 - SAFETY_MARGIN_MIB
                 - ODOO_REPLY_RESERVE_MIB - ODOO_REPLY_WORK_MIB - ODOO_STREAM_RESERVE_MIB)
    derived = int(max(0, available) * MiB / ODOO_ADMISSION_AMPLIFICATION)
    return min(MAX_BUDGET_BYTES, max(MIN_BUDGET_BYTES, derived))


def odoo_switched_memory_fits(ceiling_mib: int | None, accounts: int, source: str) -> bool:
    """The whole switched-on Odoo plan must fit before its 16 MiB body floor applies."""
    if ceiling_mib is None or source not in ('cgroup', 'meminfo'):
        return False
    required = (HOST_RESERVE_MIB if source == 'cgroup' else 0) + GATEWAY_BASELINE_MIB + accounts * 100 + \
        SAFETY_MARGIN_MIB + ODOO_REPLY_RESERVE_MIB + ODOO_REPLY_WORK_MIB + ODOO_STREAM_RESERVE_MIB + \
        ODOO_ADMISSION_AMPLIFICATION * MIN_BUDGET_BYTES / MiB
    return ceiling_mib >= required


def default_per_profile_bytes(total: int) -> int:
    """A profile's share before its quota caps it (PaaS): half the budget, at least the single-request ceiling."""
    return max(MIN_BUDGET_BYTES, int(total * PER_PROFILE_FRACTION))


def runtime_inputs(product, *, switched_on: bool, memory_limit: int | None = None) -> tuple[int, int]:
    """(accounts, child MiB) for product: one account switched off; switched on, the default profile and the product's
    additional-profile capacity (profiles.capacity under the cgroup limit, as the profile capacity uses it)."""
    child = profiles.CHILD_MEMORY_MIB.get(product) or DEFAULT_CHILD_MEMORY_MIB
    if not switched_on or product not in profiles.EXTRA_PROFILE_LIMITS:
        return 1, child
    return 1 + profiles.capacity(product, memory_limit).limit, child


@dataclass(frozen=True)
class BudgetLimits:
    """total: the add-on's budget; per_profile: a profile's share before its quota caps it; idle_seconds: how long a
    large request may send nothing; source: where total came from ('cgroup', 'meminfo', 'none' or 'given')."""
    total: int
    per_profile: int
    idle_seconds: float = BODY_IDLE_SECONDS
    source: str = 'given'
    small_minimum: int = 0

    def __post_init__(self):
        if (type(self.total) is not int or type(self.per_profile) is not int or self.total < 1 or self.per_profile < 1
                or isinstance(self.idle_seconds, bool) or not isinstance(self.idle_seconds, (int, float))
                or not self.idle_seconds > 0 or type(self.small_minimum) is not int or self.small_minimum < 0):
            raise ValueError('invalid request budget')

    @classmethod
    def derive(cls, product=None, *, switched_on: bool = False) -> 'BudgetLimits':
        """The defaults (see the module docstring), read now: when the gateway is made, at startup."""
        ceiling, source = memory_ceiling()
        accounts, child = runtime_inputs(product, switched_on=switched_on,
                                         memory_limit=ceiling if source == 'cgroup' else None)
        total = (odoo_switched_total_bytes(ceiling, accounts, source) if switched_on and product == 'odoo'
                 else default_total_bytes(ceiling, accounts=accounts, child_memory_mib=child))
        return cls(total=total, per_profile=default_per_profile_bytes(total), source=source,
                   small_minimum=ODOO_SMALL_MINIMUM_BYTES if switched_on and product == 'odoo' else 0)


def odoo_switched_limits(ceiling_mib: int, accounts: int, source: str) -> BudgetLimits:
    """Build an activated Odoo budget from the same reading used to check its floor and capacity."""
    if not odoo_switched_memory_fits(ceiling_mib, accounts, source):
        raise ValueError('Odoo multi-profile memory plan does not fit')
    total = odoo_switched_total_bytes(ceiling_mib, accounts, source)
    return BudgetLimits(total=total, per_profile=default_per_profile_bytes(total), source=source,
                        small_minimum=ODOO_SMALL_MINIMUM_BYTES)


class BudgetExceeded(Exception):
    """A request's body does not fit the budget. scope: 'profile' (its share) or 'global' (the add-on's); limit: that
    layer's bytes; read: whether any of the body was read (False: refused on its declared length, nothing read);
    head: the first ID_WINDOW bytes read (to find its id)."""

    def __init__(self, scope: str, limit: int, *, head: bytes = b'', read: bool = False):
        super().__init__(f'request body budget exceeded ({scope}, limit {limit} bytes)')
        self.scope, self.limit, self.head, self.read = scope, limit, head, read


class BodyIdleTimeout(Exception):
    """A large request sent nothing for seconds while its body was read."""

    def __init__(self, seconds: float):
        super().__init__(f'request body idle for {seconds:g} seconds')
        self.seconds = seconds


class RequestBudget:
    """The add-on's request body budget: one for a switched-off add-on's only profile (gateway.make_apps), one shared by
    every profile of a switched-on add-on (profile_runtime.ProfileManager)."""

    def __init__(self, limits: BudgetLimits):
        if not isinstance(limits, BudgetLimits):
            raise ValueError('invalid request budget')
        self.limits = limits
        self._total = 0
        self._profiles: dict[str, int] = {}
        self.peak = 0  # the most the add-on ever held (tests, diagnostics)
        self._capacity_metrics = active_metrics()
        if self._capacity_metrics is not None:
            self._capacity_metrics.on_charge_change(0)

    def used(self, profile_id: str | None = None) -> int:
        """What is charged now: the add-on's, or one profile's."""
        return self._total if profile_id is None else self._profiles.get(profile_id, 0)

    def share(self, profile_id: str, *, cap: int, warn: Callable[[object, str], None] | None = None) -> 'Share':
        """profile_id's share: at most cap (its quota's body_bytes) and the budget's per_profile."""
        return Share(self, profile_id, min(cap, self.limits.per_profile), warn)

    def _charge(self, profile_id: str, amount: int, limit: int) -> None:
        """Charge amount, or raise BudgetExceeded and change nothing."""
        used = self._profiles.get(profile_id, 0)
        if used + amount > limit:
            raise BudgetExceeded('profile', limit)
        if self._total + amount > self.limits.total:
            raise BudgetExceeded('global', self.limits.total)
        self._total += amount
        self.peak = max(self.peak, self._total)
        self._profiles[profile_id] = used + amount
        if self._capacity_metrics is not None:
            self._capacity_metrics.on_charge_change(self._total)

    def _refund(self, profile_id: str, amount: int) -> None:
        self._total -= amount
        left = self._profiles.get(profile_id, 0) - amount
        if left > 0:
            self._profiles[profile_id] = left
        else:
            self._profiles.pop(profile_id, None)
        if self._capacity_metrics is not None:
            self._capacity_metrics.on_charge_change(self._total)


class Share:
    """One profile's share of the budget; warn(situation, text) writes the profile's WARNING (one a minute); reports:
    the Reports own_share made for it (None for a switched-on profile's: its gate's)."""
    __slots__ = ('budget', 'profile_id', 'limit', '_warn', 'reports')

    def __init__(self, budget, profile_id, limit, warn):
        if type(limit) is not int or limit < 1 or warn is not None and not callable(warn):
            raise ValueError('invalid budget share')
        self.budget, self.profile_id, self.limit, self._warn = budget, profile_id, limit, warn
        self.reports = None

    def open(self) -> 'Reservation':
        return Reservation(self)

    def warn(self, situation, text):
        if self._warn is not None:
            self._warn(situation, text)


class Reservation:
    """What one request holds of the budget: the larger of its body as read (size; nothing once over the single-request
    ceiling) and as forwarded (forwarded), once that is over SMALL_REQUEST_BYTES; Odoo may also hold a minimum before
    parsing. charged is what is held now."""
    __slots__ = ('share', 'size', 'forwarded', 'charged', 'over_cap', 'closed', 'small_reserved')

    def __init__(self, share: Share):
        self.share = share
        self.size = self.forwarded = self.charged = 0
        self.over_cap = self.closed = False
        self.small_reserved = False

    def _settle(self):
        held = max(0 if self.over_cap else self.size, self.forwarded)
        minimum = self.share.budget.limits.small_minimum if self.small_reserved else 0
        target = max(held, minimum) if held > SMALL_REQUEST_BYTES or minimum else 0
        share = self.share
        if target > self.charged:
            share.budget._charge(share.profile_id, target - self.charged, share.limit)
        elif target < self.charged:
            share.budget._refund(share.profile_id, self.charged - target)
        self.charged = target

    def reserve_small(self) -> None:
        """Reserve an Odoo POST's minimum before any body bytes are parsed."""
        if not self.closed and not self.small_reserved:
            self.small_reserved = True
            self._settle()

    def grow(self, size: int, *, cap: int) -> None:
        """The body as read (or declared) is size bytes now (it only grows). Over cap it is not charged (refused as too
        large; what was charged goes back). BudgetExceeded when it does not fit (what was charged stays, until
        close)."""
        if self.closed or size <= self.size:
            return
        self.size = size
        if size > cap:
            self.over_cap = True
        self._settle()

    def forward(self, size: int) -> None:
        """The body re-serialized for the child is size bytes (HA's own rule; no ceiling: it is the copy the gateway
        holds). BudgetExceeded when it does not fit."""
        if self.closed or size <= self.forwarded:
            return
        self.forwarded = size
        self._settle()

    def close(self) -> None:
        """The request ended: whatever it held goes back. Idempotent."""
        if not self.closed:
            self.closed = True
            if self.charged:
                self.share.budget._refund(self.share.profile_id, self.charged)
                self.charged = 0


# ---- reading a body under the budget ----

def declared_length(headers) -> int | None:
    """The body length a request declares, from its ASGI scope's headers ((name, value) bytes pairs): its one
    Content-Length, a plain number; None (its body is then counted as it arrives) when it states none, more than one, a
    malformed one, or has a Transfer-Encoding. RFC 9112 6.3: the Transfer-Encoding frames the body and the
    Content-Length is ignored. h11 0.16.0, the add-on's parser (no httptools in its environment), reads a request with
    both as chunked and hands content-length on as sent (HM-31 review MF-1). The one rule of the gateway's watch and
    body and of the dispatcher's admission-full read (review S-6)."""
    lengths = []
    for name, value in headers:
        name = name.lower()
        if name == b'transfer-encoding':
            return None
        if name == b'content-length':
            lengths.append(value)
    if len(lengths) != 1:
        return None
    value = lengths[0].decode('latin-1').strip()
    if not value.isascii() or not value.isdigit() or len(value) > 19:
        return None
    return int(value)


def registered(declared: int | None) -> bool:
    """A large request (PaaS): declared over SMALL_REQUEST_BYTES, or no Content-Length. Only its body is watched for
    idleness and charged."""
    return declared is None or declared > SMALL_REQUEST_BYTES


def watch(request, reservation: Reservation, *, cap: int, idle_seconds: float = BODY_IDLE_SECONDS):
    """Make request.stream charge reservation and watch for idleness (PaaS proxy._count_stream and _watch_idle), and
    return the stream it replaced (a refused body is drained with it). Normally nothing changes for a small request: one that
    declares at most SMALL_REQUEST_BYTES (declared_length: a Content-Length beside a Transfer-Encoding declares
    nothing, so a body framed chunked is a large request whatever its Content-Length says; HM-31 review MF-1).
    Switched-on Odoo also wraps small POSTs to reserve their minimum before the parser sees a byte.

    - a declared Content-Length over SMALL_REQUEST_BYTES and at most cap is charged when the body's read begins, before
      a byte is read: BudgetExceeded (read False) if it does not fit;
    - the bytes that arrive are charged as they arrive, whatever was declared (review MF-1: the declared length is no
      bound on them; a Reservation only grows, so a body framed by its length adds nothing): BudgetExceeded (read True,
      the head kept) once they do not fit; over cap they are no longer charged (the reader refuses the body as too
      large; gateway.body refuses a declared one over its ceiling before a byte is read, review MF-3);
    - BodyIdleTimeout when no new byte came for idle_seconds (between two chunks, or before the first)."""
    original = request.stream
    declared = declared_length(request.headers.raw)
    reserve_small = getattr(request, 'method', None) == 'POST' and reservation.share.budget.limits.small_minimum > 0
    if not registered(declared) and not reserve_small:
        return original
    precharged = declared is not None and declared <= cap

    async def stream():
        if reserve_small:
            reservation.reserve_small()
        if precharged:
            reservation.grow(declared, cap=cap)
        chunks = original().__aiter__()
        total, head = 0, b''
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(chunks.__anext__(), idle_seconds)
                except StopAsyncIteration:
                    return
                except TimeoutError:
                    raise BodyIdleTimeout(idle_seconds) from None
                if chunk:
                    total += len(chunk)
                    if len(head) < ID_WINDOW:
                        head += chunk[:ID_WINDOW - len(head)]
                    try:
                        reservation.grow(total, cap=cap)
                    except BudgetExceeded as exc:
                        exc.head, exc.read = head, True
                        raise
                yield chunk
        finally:
            aclose = getattr(chunks, 'aclose', None)
            if aclose is not None:
                await aclose()

    request.stream = stream
    return original


async def drain(stream, *, idle_seconds: float, total_seconds: float) -> tuple[bytes, bytes, bool]:
    """Read a refused body to its end and keep only its first and last ID_WINDOW bytes (PaaS _refuse_over_budget: the
    client that sends its whole body before reading the answer gets the answer, not a reset; nothing held but the two
    windows). Stops early, answering anyway, after idle_seconds without a byte or total_seconds in all.
    (head, tail, left): left when the client left (ClientDisconnect)."""
    head = tail = b''
    chunks = stream().__aiter__()
    try:
        async with asyncio.timeout(total_seconds):
            while True:
                try:
                    chunk = await asyncio.wait_for(chunks.__anext__(), idle_seconds)
                except StopAsyncIteration:
                    break
                if len(head) < ID_WINDOW:
                    head += chunk[:ID_WINDOW - len(head)]
                tail = (tail + chunk[-ID_WINDOW:])[-ID_WINDOW:]
    except ClientDisconnect:
        return head, tail, True
    except TimeoutError:
        pass
    finally:
        aclose = getattr(chunks, 'aclose', None)
        if aclose is not None:
            await aclose()
    return head, tail, False


# ---- the JSON-RPC id of a body that is not parsed: request_limits.head_tail_id (PaaS request_body._request_id) ----

def unread_message(ident):
    """A stand-in message for the gateway's busy answer of a body that was not parsed: its id, or None."""
    return None if ident is None else {'jsonrpc': '2.0', 'id': ident, 'method': 'unread'}


# ---- the fixed texts (PaaS proxy._budget_message, _idle_timeout_response, d7f5849): no token, URL or content ----

def budget_text(exc: BudgetExceeded) -> str:
    size = f'{exc.limit / MiB:g}'
    if exc.scope == 'profile':
        english, chinese = 'this MCP URL', '這個 MCP 網址'
    else:
        english, chinese = 'this MCP server (all of its URLs together)', '這台 MCP 伺服器（所有網址合計）'
    return (f'{english} is already holding {size} MiB of request bodies, the limit, so this request was not read or '
            f'sent. Retry shortly, or send smaller requests. ({chinese}目前處理中的請求內容已達上限 {size} MiB，'
            '這個請求沒有讀取也沒有送出，請稍後再試，或改送較小的請求。)')


def idle_text(seconds: float) -> str:
    return (f'No request body data arrived for {seconds:g} seconds, so this request was dropped and its share of the '
            'request body budget was released. Retry. '
            f'(請求內容連續 {seconds:g} 秒沒有收到任何資料，這個請求已放棄，佔用的請求內容預算已歸還，請重試。)')


def budget_note(exc: BudgetExceeded) -> str:
    """The WARNING of a refusal: which layer and its limit."""
    size = f'{exc.limit / MiB:g}'
    if exc.scope == 'profile':
        return (f'its requests in progress held {size} MiB of request bodies, its share of the byte budget; new large '
                'requests were answered busy (-32003) and not sent')
    return (f"every profile's requests in progress held {size} MiB of request bodies, the add-on's byte budget; new "
            "large requests were answered busy (-32003) and not sent")


# ---- one WARNING per profile and situation a minute (PaaS gateway_pool._report; HM-08's profile_router.Reports) ----

class Reports:
    """One WARNING per (profile, situation) a REPORT_SECONDS window: the first one written, the others counted, and the
    next line written ends with suppressed=N. text is complete fixed text: never a token, a URL, a label or request
    content. At most MAX_REPORT_KEYS situations are remembered (expired ones go first, then the oldest). log: the
    logger the lines go to (profile_router's for a switched-on add-on)."""

    def __init__(self, log=None):
        self.log = log or logger
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
        self.log.warning(text + (f' suppressed={suppressed}' if suppressed else ''))


def own_share(product=None) -> Share:
    """A switched-off add-on's budget and its only share (the default profile's): gateway.make_apps makes it when none
    is given. Its WARNINGs: one a minute per situation, 'MCP gateway [profile=default]: ...'."""
    reports = Reports()
    budget = RequestBudget(BudgetLimits.derive(product, switched_on=False))

    def warn(situation, text):
        reports.warn(profiles.DEFAULT_PROFILE, situation, 'MCP gateway [profile=default]: ' + text)
    share = budget.share(profiles.DEFAULT_PROFILE, cap=profiles.DEFAULT_PROFILE_QUOTA.body_bytes, warn=warn)
    share.reports = reports
    return share
