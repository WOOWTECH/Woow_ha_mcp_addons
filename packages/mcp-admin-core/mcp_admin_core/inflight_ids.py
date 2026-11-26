"""The JSON-RPC request ids in flight in one MCP session (the PaaS #161 gateway, woow-mcp-server 81fd50a, ad03275, 39891b6:
inflight_ids.py, proxy.py; contract 1.2, 2.8; not gated: every product, switched on or off).

Why: the MCP Python SDK's Streamable HTTP transport keys the stream of a request's answer by str(message.id) (mcp 2.3.0,
server/streamable_http.py: request_id = str(message.id), self._request_streams[request_id], in SSE and in JSON mode), so
two requests of one session that are in flight together with the same id overwrite each other's stream. PaaS measured 8
requests with id 7: none got its own answer, one got another's, seven hung until the gateway's own limit. A client may
not do that (MCP: an id must not be reused within a session), but a client that does made its requests hang. The gateway
registers (profile, Mcp-Session-Id, str(id)) when a request is about to be forwarded to the child and gives it back when
the request ends; a request whose key is registered is refused at once (gateway.duplicate_id_reply) and never sent.

- The key is str(id), as the SDK's: 7 and "7" are one id. Only what is in flight counts: once the child has answered, or
  the request ended otherwise (its client gone, an upstream error, a timeout, a changed token) the id can be used again.
- A request is registered after the gateway has decided to forward it (never an initialize, a notification, a GET, a
  DELETE, nor anything the gateway answers itself: a refused call, an unknown method, a session of its own), holding its
  forwarding slot, and given back with that slot (gateway.UpstreamOwner.close): every way a request can end goes through
  there, so it cannot be missed. An event stream gives it back earlier, as soon as the child's reply is in hand.
- The table is bounded and fails open: a request that does not fit is not registered and not refused (it is forwarded as
  before, without the check) and the gateway writes one throttled WARNING. A profile registers at most one id per
  forwarding slot it holds, so it can never hold more than its slots (32 for the default profile, 16 for an additional
  one), and the whole table is larger than what every profile of the add-on could hold at once (MAX_ENTRIES). Neither
  bound is reached unless a release is missed; if one ever is, they keep one profile from filling the table for the
  others and keep its memory bounded.
- Everything here is O(1) on the event loop and reads nothing but the request's id: the key is hashed and compared, so an
  id longer than MAX_ID_LENGTH (the 256 characters request_limits.head_tail_id reads) is not registered at all, and what
  a refusal shows of an id is cut and escaped (shown_id).

Single-threaded (the event loop): no lock and no await, so every call is atomic, as request_budget's counts.
"""
from __future__ import annotations

from typing import Callable

# begin()'s outcomes: registered, or why not (a duplicate is refused, the others are forwarded unchecked)
REGISTERED = 'registered'
DUPLICATE = 'duplicate'
TABLE_FULL = 'table-full'
PROFILE_FULL = 'profile-full'
ID_TOO_LONG = 'id-too-long'

# The most ids the table holds, for every profile together: more than the add-on's profiles can hold at once, one id per
# forwarding slot (32 + 5 x 16 = 112 for Odoo, the most; tests/test_inflight_ids.py keeps it so when a quota changes).
MAX_ENTRIES = 512
# The longest id (as str(id)) that is registered, as many characters as request_limits.head_tail_id reads of an id: an
# integer is converted only below INT_BITS (a bigger one is longer than that anyway).
MAX_ID_LENGTH = 256
INT_BITS = 1024
# How much of an id a refusal shows (then its length), before it is escaped.
SHOWN_ID_LENGTH = 64
# JSON-RPC's "Invalid Request" (the PaaS refusal's code).
DUPLICATE_ERROR_CODE = -32600


class InflightIds:
    """The table (see the module docstring): one for the add-on's profiles together (profile_runtime.ProfileManager), or
    a switched-off add-on's own (gateway.make_apps)."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError('invalid in-flight id table')
        self.max_entries = max_entries
        self._entries: set[tuple[str, str, str]] = set()
        self._held: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def count(self, profile_id: str) -> int:
        """How many ids the profile holds now."""
        return self._held.get(profile_id, 0)

    def held(self) -> dict[str, int]:
        """What every profile holds now ({} when the table is empty)."""
        return dict(self._held)

    def begin(self, profile_id: str, session_id: str, rpc_id, limit: int) -> tuple[Callable[[], None] | None, str]:
        """Register rpc_id of a request of profile_id in session_id, the profile holding at most limit ids (its
        forwarding slots). (release, outcome): outcome REGISTERED and release() to call when the request ends (as often as
        asked: it gives back once); DUPLICATE: the key is registered, nothing was changed (refuse the request); TABLE_FULL,
        PROFILE_FULL, ID_TOO_LONG: not registered, nothing was changed (forward the request without the check)."""
        if type(rpc_id) is int and rpc_id.bit_length() > INT_BITS:
            return None, ID_TOO_LONG
        key = str(rpc_id)
        if len(key) > MAX_ID_LENGTH:
            return None, ID_TOO_LONG
        entry = (profile_id, session_id, key)
        if entry in self._entries:
            return None, DUPLICATE
        held = self._held.get(profile_id, 0)
        if len(self._entries) >= self.max_entries:
            return None, TABLE_FULL
        if held >= limit:
            return None, PROFILE_FULL
        self._entries.add(entry)
        self._held[profile_id] = held + 1
        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            self._entries.discard(entry)
            left = self._held.get(profile_id, 0) - 1
            if left > 0:
                self._held[profile_id] = left
            else:
                self._held.pop(profile_id, None)

        return release, REGISTERED


def shown_id(key: str) -> str:
    """How a refusal names an id: at most SHOWN_ID_LENGTH characters of it, escaped (ascii(): quotes, backslashes,
    control characters, bidirectional controls and everything beyond ASCII), then its length when it was cut. Whatever
    the client sent, this is short and cannot change how the text reads."""
    shown = ascii(key[:SHOWN_ID_LENGTH])
    return shown if len(key) <= SHOWN_ID_LENGTH else f'{shown}... ({len(key)} characters)'


def duplicate_text(rpc_id) -> str:
    """The refusal's message: the PaaS text (inflight_ids.duplicate_message), with the id shown by shown_id (PaaS shows
    it with repr, of any length). English, then Traditional Chinese; never a token, a session or a profile."""
    key = rpc_id if type(rpc_id) is str else str(rpc_id)
    shown = shown_id(key)
    return (f"Duplicate in-flight JSON-RPC request id {shown} in this MCP session: a request with the same id is "
            "still being processed, so this request was not sent. Use a unique id per request (ids must not be "
            f"reused within a session while in flight). (同一個 MCP session 內已有進行中的請求使用相同的 id {shown}，"
            "這個請求沒有送出；請求 id 在同一個 session 內不得重複使用。)")


def skipped_text(outcome: str, max_entries: int, limit: int) -> str:
    """The WARNING of a request that was not registered (TABLE_FULL, PROFILE_FULL, ID_TOO_LONG): which bound, never the
    id, the session or a token."""
    if outcome == TABLE_FULL:
        return (f'the table of in-flight JSON-RPC ids is full ({max_entries} entries); this request was forwarded without '
                'the duplicate-id check')
    if outcome == PROFILE_FULL:
        return (f'this profile already holds {limit} in-flight JSON-RPC ids, one for each of its forwarding slots; this '
                'request was forwarded without the duplicate-id check')
    return (f'a JSON-RPC request id is longer than {MAX_ID_LENGTH} characters; this request was forwarded without the '
            'duplicate-id check')
