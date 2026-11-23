"""HM-19c: the request envelope of a large MCP request, read without parsing its body.

The gateway used to parse every request body into Python objects (strict_json), check it, and serialize it again before
it handed it to the child. For a body made of many tiny containers (800 KB, 100,000 ``{"a":1}``) that costs one long GIL
hold per C call (the structure scan's re.sub, the final json.dumps), a 25-fold object graph in the gateway and the same
graph again in the child. The gateway never looks at the contents of ``params.arguments`` of a full-surface tool: it needs
``jsonrpc``, ``id``, ``method``, ``params.name``, the key set of ``params``, the type of ``arguments`` and (for the few tools
with an operation selector) the selector's value. This module reads exactly that, in bounded steps, and leaves the bytes to
be forwarded as they came (minus an ``params._meta`` entry, spliced out of the bytes).

Every step is bounded: one C call looks at most :data:`CHUNK` bytes (about half a millisecond), the scan is a generator the
caller drives (``run``: the event loop gets control between steps), and nothing builds an object per JSON element.

What is still checked, and how it differs from ``strict_json`` + ``structure_violation`` (the parse every body of at most
``ENVELOPE_BYTES`` still gets, unchanged):

* UTF-8 (``not_utf8``'s rule), element count and nesting depth of the WHOLE body (``structure_violation``'s definitions:
  elements are commas plus containers outside strings), optional container density: same refusals, same texts;
* a lone surrogate written as a ``\\uXXXX`` escape, anywhere in the body (``json.dumps(..., ensure_ascii=False)`` used to
  refuse it): refused with 400, as before;
* duplicate keys, ``NaN``/``Infinity`` and numbers beyond a float: checked only on the envelope's own keys (the top level,
  ``params``, and the selector level of ``arguments``). Nested content is the child's to read; the child is another process
  and does its own strict parse. This is the one deliberate change (see the design note).

Not valid JSON in the parts the scan reads is a 400 as before; invalid JSON inside a skipped value is judged by the child.
"""
from __future__ import annotations

import codecs
import json
import re
import time
from dataclasses import dataclass

from .config import strict_json
from .request_limits import NOT_UTF8_REASON

#: One C call looks at most this many bytes. Dense JSON (``{"a":1},`` repeated) costs about 36 ms per MiB here, so a chunk
#: is about 0.5 ms on a fast machine and about 3 ms on a J6412; the caller gives the loop control between chunks.
CHUNK = 16 * 1024
#: A skipped container starts with a small step and doubles it, so a small container never pays for a whole chunk.
FIRST_STEP = 256
#: The ordered (token by token) walk of the chunk where a container ends, or whose depth the fast path cannot bound.
EXACT_SLICE = 2 * 1024
#: Largest token (key, id, method, name, selector value) read into an object; the longest the envelope may carry.
MAX_TOKEN = 4096
#: Most keys of an object the scan walks (top level, params, selector level of arguments).
MAX_ENTRIES = 4096
#: Longest run of whitespace between two tokens. Everything else is skipped inside values by C calls of CHUNK bytes.
MAX_WS = 4096
#: params._meta is accepted up to this many bytes of compact JSON (policy.META_LIMIT); a raw span above SPAN_MAX is refused
#: without a parse (compact JSON is never longer than its raw text, so only whitespace padding could make that wrong).
META_LIMIT = 8192
META_SPAN_MAX = 65536
#: A slice of work between two returns of control to the event loop (``run``).
SLICE_SECONDS = 0.0005
UTF8_STEP = 32 * 1024

_WS = re.compile(rb'[ \t\n\r]{0,%d}' % (MAX_WS + 1))
# The body of a JSON string up to (not including) its closing quote: no control characters, every backslash followed by
# one more non-control byte. Possessive: linear, never backtracks.
_STR_REST = re.compile(rb'[^"\\\x00-\x1f]*+(?:\\[^\x00-\x1f][^"\\\x00-\x1f]*+)*+')
_COMPLETE_STRING = re.compile(rb'"[^"\\\x00-\x1f]*+(?:\\[^\x00-\x1f][^"\\\x00-\x1f]*+)*+"')
_STRING_TOKEN = _COMPLETE_STRING
_LITERAL = re.compile(rb'true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')
_STRUCTURE_BYTES = bytes.maketrans(bytes(range(256)), bytes(char if char in b'[]{},' else 0 for char in range(256)))
_RESIDUAL = re.compile(rb'[\]}]*[\[{]*\Z')
_TOKEN = re.compile(rb'["\[\]{},]')
# A string's escapes that keep surrogates paired: text, an escape that is a valid surrogate pair, a non-surrogate \u, or
# any other escape. It stops at the first lone surrogate escape (or at the end of its window).
_ESCAPES_OK = re.compile(rb'(?:[^\\]++|\\(?:u[dD][89abAB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}|u(?:[^dD]|[dD][0-7])|[^u]))*+')
_PAIR = re.compile(rb'\\u[dD][89abAB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}')
_LONE = re.compile(rb'\\u[dD][89a-fA-F][0-9a-fA-F]{2}')

_OPEN = (ord('['), ord('{'))
_QUOTE, _BACKSLASH, _COMMA, _COLON, _LBRACE, _RBRACE = 34, 92, 44, 58, 123, 125


class EnvelopeInvalid(ValueError):
    """The part of the body the gateway reads is not valid JSON (a 400, as ``strict_json`` failing was)."""


class EnvelopeRefused(Exception):
    """A limit the structure guard owns: ``reason`` is the text ``request_limits.too_complex`` puts in its answer."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EnvelopeDenied(Exception):
    """The policy's own refusal of the envelope (an invalid ``params._meta``): a 403, as ``strip_meta`` raising Denied was."""


class NeedsFullParse(Exception):
    """The tool the call names reads its arguments (or is not a full-surface tool): the old full parse takes this one."""


@dataclass(frozen=True)
class EnvelopeLimits:
    max_depth: int = 64
    max_elements: int = 200_000
    #: Most containers (``[`` and ``{``) per KiB of body; None: not limited. A parsed container costs 56 to 260 bytes in the
    #: child's process (measured: ``{"a":1}`` 184 bytes in CPython, 258 with jiter), the density bounds the child's memory.
    max_containers_per_kib: int | None = None


@dataclass
class Envelope:
    #: What ``policy.authorize`` and the gateway read: the body's own top-level keys, ``params`` with ``name``, a stand-in
    #: for ``arguments`` (only the selector keys of the tool) and no ``_meta``.
    message: dict
    #: The bytes for the child: the body as it came, without ``params._meta`` when it had one.
    forward: bytes
    elements: int
    containers: int
    meta_removed: bool = False


# --------------------------------------------------------------------------------------------------------------------
# bounded checks of the whole body

def utf8_steps(raw: bytes):
    """``request_limits.not_utf8`` in steps (a generator): raises EnvelopeRefused for UTF-16/32 and invalid UTF-8."""
    if b"\x00" in raw[:4]:
        raise EnvelopeRefused(NOT_UTF8_REASON)
    decoder = codecs.getincrementaldecoder("utf-8")()
    view = memoryview(raw)
    try:
        for start in range(0, len(raw), UTF8_STEP):
            part = view[start:start + UTF8_STEP]
            if not part.tobytes().isascii():
                decoder.decode(part)
            elif decoder.getstate()[0]:
                decoder.decode(part)  # an ASCII byte inside a multi-byte sequence: the decoder rejects it
            yield
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        raise EnvelopeRefused(NOT_UTF8_REASON) from None


def lone_surrogate_steps(raw: bytes):
    """Whether the body has a ``\\uD800``-``\\uDFFF`` escape that is not half of a valid pair (a generator returning bool).

    ``json.loads`` joins a high and a low escape that follow each other into one character and keeps any other as a lone
    surrogate, which ``json.dumps(..., ensure_ascii=False).encode()`` then refused. Windows end at a complete token: the
    pattern cannot cross the window's end, so a pair cut in two is retried from its first half."""
    size = len(raw)
    pos = 0
    while pos < size:
        stop = min(pos + CHUNK, size)
        end = _ESCAPES_OK.match(raw, pos, stop).end()
        if end >= stop:
            pos = stop
        elif raw.startswith(b"\\u", end):
            if _PAIR.match(raw, end):
                pos = end  # a pair cut by the window's end: its first half starts the next window
            elif _LONE.match(raw, end):
                return True
            else:
                pos = end + 2  # \\u not followed by four hex digits: not a surrogate escape (the child refuses it)
        elif raw[end] == _BACKSLASH and end == stop - 1:
            pos = end
        else:
            pos = end + 1
        yield
    return False


def _outside(chunk: bytes, in_string: bool, escaped: bool):
    """The bytes of ``chunk`` that are outside JSON strings, and the string state at its end (in a string, a backslash
    pending). Never builds more than ``len(chunk)``. Raises EnvelopeInvalid for a control character inside a string."""
    start = 0
    if in_string:
        if escaped:
            if chunk[0] < 0x20:
                raise EnvelopeInvalid("control character in a string")
            start = 1
        end = _STR_REST.match(chunk, start).end()
        if end == len(chunk):
            return b"", True, False
        if chunk[end] == _QUOTE:
            start = end + 1
        elif chunk[end] == _BACKSLASH and end == len(chunk) - 1:
            return b"", True, True
        else:
            raise EnvelopeInvalid("control character in a string")
    rest = chunk[start:] if start else chunk
    outside = _COMPLETE_STRING.sub(b"", rest)
    quote = outside.find(b'"')
    if quote < 0:
        return outside, False, False
    # An unterminated string starts here (no match can begin inside it: every quote in it is escaped).
    tail = outside[quote + 1:]
    end = _STR_REST.match(tail).end()
    if end == len(tail):
        return outside[:quote], True, False
    if tail[end] == _BACKSLASH and end == len(tail) - 1:
        return outside[:quote], True, True
    raise EnvelopeInvalid("control character in a string")


class _Scan:
    """One scan of one body. Every method that does C work over more than a few hundred bytes is a generator."""

    def __init__(self, raw: bytes, limits: EnvelopeLimits, keys_for):
        self.raw = raw
        self.size = len(raw)
        self.limits = limits
        self.keys_for = keys_for
        self.elements = 0
        self.containers = 0
        self.counting = True

    # ---- small helpers -------------------------------------------------------------------------------------------
    def peek(self, pos: int) -> int:
        return self.raw[pos] if pos < self.size else -1

    def ws(self, pos: int) -> int:
        end = _WS.match(self.raw, pos).end()
        if end - pos > MAX_WS:
            raise EnvelopeInvalid("too much whitespace")
        return end

    def count(self, containers: int, commas: int):
        if not self.counting:
            return
        self.containers += containers
        self.elements += containers + commas
        if self.elements > self.limits.max_elements:
            raise EnvelopeRefused(f"more than {self.limits.max_elements} JSON elements")

    def depth_check(self, depth: int):
        if depth > self.limits.max_depth:
            raise EnvelopeRefused(f"more than {self.limits.max_depth} levels of nesting")

    def key(self, pos: int):
        """Read an object key (a string of at most MAX_TOKEN bytes): (str, end)."""
        if self.peek(pos) != _QUOTE:
            raise EnvelopeInvalid("object key expected")
        match = _STRING_TOKEN.match(self.raw, pos, min(self.size, pos + MAX_TOKEN))
        if match is None:
            raise EnvelopeInvalid("object key too long or not a string")
        return strict_json(match.group()), match.end()

    def expect_colon(self, pos: int) -> int:
        pos = self.ws(pos)
        if self.peek(pos) != _COLON:
            raise EnvelopeInvalid("colon expected")
        return self.ws(pos + 1)

    # ---- skipping values -----------------------------------------------------------------------------------------
    def skip_string(self, pos: int):
        """End (exclusive) of the string that opens at ``pos``. A generator."""
        raw, size = self.raw, self.size
        cursor = pos + 1
        while True:
            stop = min(cursor + CHUNK, size)
            end = _STR_REST.match(raw, cursor, stop).end()
            if end < stop:
                char = raw[end]
                if char == _QUOTE:
                    return end + 1
                if char == _BACKSLASH and end == stop - 1 and stop < size:
                    cursor = end  # the pair is cut by the window's end: retry from the backslash
                    yield
                    continue
                raise EnvelopeInvalid("bad character in a string")
            if stop >= size:
                raise EnvelopeInvalid("unterminated string")
            cursor = stop
            yield

    def skip_container(self, pos: int, depth: int):
        """End (exclusive) of the container that opens at ``pos``, counting its elements and checking its depth; ``depth``
        is the nesting level the opener sits in (1 for a value of the top-level object). A generator.

        Per chunk, in C: remove the strings (carrying their state across chunks), keep only ``[]{},``, count, collapse
        balanced pairs. If what is left is closers then openers, the chunk cannot end the container unless the closers
        reach its level, and its deepest point is bounded by the passes the collapse took; then the chunk is accounted for
        from counts alone. Otherwise (the container ends in this chunk, the bound is not good enough, the brackets do not
        pair) the chunk is walked token by token, EXACT_SLICE bytes at a time."""
        raw, size = self.raw, self.size
        base = depth
        level = depth  # nesting level after the brackets seen so far
        in_string = escaped = False
        cursor = pos
        step = FIRST_STEP
        while cursor < size:
            stop = min(cursor + step, size)
            chunk = raw[cursor:stop]
            outside, now_in, now_escaped = _outside(chunk, in_string, escaped)
            structure = outside.translate(_STRUCTURE_BYTES).replace(b"\x00", b"")
            openers = structure.count(b"[") + structure.count(b"{")
            closers = structure.count(b"]") + structure.count(b"}")
            commas = structure.count(b",")
            brackets = structure.replace(b",", b"")
            passes = 0
            while brackets and passes <= 40:
                shorter = brackets.replace(b"[]", b"").replace(b"{}", b"")
                if len(shorter) == len(brackets):
                    break
                brackets = shorter
                passes += 1
            clean = passes <= 40 and _RESIDUAL.match(brackets) is not None
            if clean:
                left_closers = brackets.count(b"]") + brackets.count(b"}")
                left_openers = len(brackets) - left_closers
                peak = max(level, level - left_closers + left_openers) + 2 * passes
                clean = level - left_closers > base and peak <= self.limits.max_depth
            if clean:
                self.count(openers, commas)
                level += openers - closers
                in_string, escaped = now_in, now_escaped
                cursor = stop
                step = min(step * 2, CHUNK)
                yield
                continue
            end = yield from self.walk(cursor, stop, base, level, in_string, escaped)
            if isinstance(end, int):
                return end
            level, in_string, escaped = end  # the walk's state at the chunk's end
            cursor = stop
            step = min(step * 2, CHUNK)
        raise EnvelopeInvalid("unterminated container")

    def walk(self, start: int, stop: int, base: int, level: int, in_string: bool, escaped: bool):
        """Walk raw[start:stop] token by token. Returns the end offset (int) when the depth falls back to ``base`` (the
        container's closer), else the tuple (level, in_string, escaped) at ``stop``. Counts elements as it goes."""
        raw = self.raw
        pos = start
        mark = pos
        while pos < stop:
            if pos - mark >= EXACT_SLICE:
                mark = pos
                yield
            if in_string:
                if escaped:
                    escaped = False
                    pos += 1
                    continue
                end = _STR_REST.match(raw, pos, stop).end()
                if end >= stop:
                    pos = stop
                    continue
                char = raw[end]
                if char == _QUOTE:
                    in_string = False
                    pos = end + 1
                elif char == _BACKSLASH and end == stop - 1:
                    escaped = True
                    pos = stop
                else:
                    raise EnvelopeInvalid("control character in a string")
                continue
            found = _TOKEN.search(raw, pos, stop)
            if found is None:
                pos = stop
                continue
            at = found.start()
            char = raw[at]
            pos = at + 1
            if char == _QUOTE:
                in_string = True
            elif char == _COMMA:
                self.count(0, 1)
            elif char in _OPEN:
                level += 1
                self.depth_check(level)
                self.count(1, 0)
            else:
                level -= 1
                if level <= base:
                    return pos
        return level, in_string, escaped

    def skip_value(self, pos: int, depth: int):
        """End of the value at ``pos`` and a stand-in for it. A generator returning (stand_in, end)."""
        char = self.peek(pos)
        if char == _QUOTE:
            end = yield from self.skip_string(pos)
            return None, end
        if char in (91, 123):
            self.depth_check(depth + 1)
            end = yield from self.skip_container(pos, depth)
            return ([] if char == 91 else {}), end
        match = _LITERAL.match(self.raw, pos, min(self.size, pos + MAX_TOKEN))
        if match is None:
            raise EnvelopeInvalid("value expected")
        return None, match.end()

    def small_value(self, pos: int, depth: int, *, required: bool):
        """A value of the envelope read into an object when it is a scalar of at most MAX_TOKEN bytes. ``required``: a
        longer string is invalid (an id, method or name); else it is stood in for by an object() that is no str.
        A generator returning (value, end)."""
        char = self.peek(pos)
        if char == _QUOTE:
            match = _STRING_TOKEN.match(self.raw, pos, min(self.size, pos + MAX_TOKEN))
            if match is not None:
                return strict_json(match.group()), match.end()
            if required:
                raise EnvelopeInvalid("string too long or malformed")
            _, end = yield from self.skip_value(pos, depth)
            return _OVERSIZE, end
        if char in (91, 123):
            value, end = yield from self.skip_value(pos, depth)
            return value, end
        match = _LITERAL.match(self.raw, pos, min(self.size, pos + MAX_TOKEN))
        if match is None:
            raise EnvelopeInvalid("value expected")
        return strict_json(match.group()), match.end()

    # ---- the envelope ---------------------------------------------------------------------------------------------
    def entries(self, pos: int, depth: int, handle):
        """Walk the entries of the object that opens at ``pos`` (depth: its level, 1 for the body). ``handle(key, start)``
        is a generator returning (stand_in, end) for the value at ``start``. Rejects duplicate keys. Returns
        (dict of stand-ins, end)."""
        self.count(1, 0)
        self.depth_check(depth)
        found = {}
        pos = self.ws(pos + 1)
        if self.peek(pos) == _RBRACE:
            return found, pos + 1
        while True:
            key, pos = self.key(pos)
            if key in found:
                raise EnvelopeInvalid("duplicate key")
            if len(found) >= MAX_ENTRIES:
                raise EnvelopeRefused(f"more than {MAX_ENTRIES} keys in one object")
            pos = self.expect_colon(pos)
            value, pos = yield from handle(key, pos)
            found[key] = value
            pos = self.ws(pos)
            char = self.peek(pos)
            if char == _COMMA:
                self.count(0, 1)
                pos = self.ws(pos + 1)
                continue
            if char == _RBRACE:
                return found, pos + 1
            raise EnvelopeInvalid("comma or end of object expected")

    def top(self):
        raw = self.raw
        pos = self.ws(0)
        if self.peek(pos) != _LBRACE:
            raise EnvelopeInvalid("JSON object expected")
        self.meta = None

        def handle_top(key, start):
            if key == "params" and self.peek(start) == _LBRACE:
                return (yield from self.params(start))
            return (yield from self.small_value(start, 1, required=key in ("jsonrpc", "id", "method")))

        message, end = yield from self.entries(pos, 1, handle_top)
        if self.ws(end) != self.size:
            raise EnvelopeInvalid("data after the JSON value")
        return message

    def params(self, pos: int):
        """The ``params`` object (level 2). Returns (stand-in dict, end)."""
        state = {"name": _MISSING, "arguments": None, "previous": None}

        def handle_params(key, start):
            if key == "name":
                value, end = yield from self.small_value(start, 2, required=True)
                state["name"] = value
                return value, end
            if key == "arguments":
                return (yield from self.arguments(start, state))
            if key == "_meta":
                value, end = yield from self.skip_value(start, 2)
                self.meta = {"value_start": start, "value_end": end, "object": self.peek(start) == _LBRACE}
                return value if value is not None else {}, end
            value, end = yield from self.skip_value(start, 2)
            return value, end

        # the entry positions of _meta, for the splice (key start, previous value end, next key start)
        params, end = yield from self.entries_with_spans(pos, handle_params)
        name = state["name"]
        if name is not _MISSING and isinstance(name, str) and state.get("span") is not None:
            wanted = self.keys_for(name)
            if wanted is None:
                raise NeedsFullParse
            if wanted:
                start, stop = state["span"]
                self.counting = False
                try:
                    values, _ = yield from self.selector_entries(start, wanted)
                finally:
                    self.counting = True
                params["arguments"] = values
        return params, end

    def entries_with_spans(self, pos: int, handle):
        """Like ``entries`` for ``params``, and records where ``_meta`` sits so it can be cut out of the bytes."""
        self.count(1, 0)
        self.depth_check(2)
        found = {}
        previous_end = None
        pos = self.ws(pos + 1)
        if self.peek(pos) == _RBRACE:
            return found, pos + 1
        while True:
            key_start = pos
            key, pos = self.key(pos)
            if key in found:
                raise EnvelopeInvalid("duplicate key")
            if len(found) >= MAX_ENTRIES:
                raise EnvelopeRefused(f"more than {MAX_ENTRIES} keys in one object")
            pos = self.expect_colon(pos)
            value, pos = yield from handle(key, pos)
            found[key] = value
            value_end = pos
            pos = self.ws(pos)
            char = self.peek(pos)
            if char == _COMMA:
                self.count(0, 1)
                pos = self.ws(pos + 1)
                if key == "_meta":
                    self.meta["cut"] = (key_start, pos)  # key through the comma and the whitespace after it
                previous_end = value_end
                continue
            if char == _RBRACE:
                if key == "_meta":
                    # the last entry: cut from the end of the entry before it (its comma goes with it)
                    self.meta["cut"] = (key_start, value_end) if previous_end is None else (previous_end, value_end)
                return found, pos + 1
            raise EnvelopeInvalid("comma or end of object expected")

    def arguments(self, pos: int, state: dict):
        """``params.arguments`` (level 3). Descends into it only for a tool whose selector the gateway reads and which is
        already named; otherwise skips it and remembers where it was. Returns (stand-in, end)."""
        char = self.peek(pos)
        name = state["name"]
        if char == _LBRACE and name is not _MISSING and isinstance(name, str):
            wanted = self.keys_for(name)
            if wanted is None:
                raise NeedsFullParse
            if wanted:
                return (yield from self.selector_entries(pos, wanted))
        value, end = yield from self.skip_value(pos, 2)
        if char == _LBRACE:
            state["span"] = (pos, end)
        return value, end

    def selector_entries(self, pos: int, wanted):
        """The top-level keys of an arguments object: the values of ``wanted`` keys that are small scalars, nothing else.
        Duplicate keys refused (the child would read the last, the gateway the first). Returns (dict, end)."""
        found = {}

        def handle(key, start):
            if key in wanted:
                return (yield from self.small_value(start, 3, required=False))
            value, end = yield from self.skip_value(start, 3)
            return value, end

        every, end = yield from self.entries(pos, 3, handle)
        for key in wanted:
            if key in every:
                found[key] = every[key]
        return found, end


_MISSING = object()
_OVERSIZE = object()  # a value too long to read: no str, no number; policy refuses it as it would any wrong type


def _splice(raw: bytes, meta: dict) -> bytes:
    start, stop = meta["cut"]
    return raw[:start] + raw[stop:]


def _check_meta(raw: bytes, meta: dict):
    """policy.strip_meta's checks on a ``_meta`` entry that was skipped: an object, of at most META_LIMIT bytes."""
    if not meta["object"]:
        raise EnvelopeDenied("invalid _meta")
    span = raw[meta["value_start"]:meta["value_end"]]
    if len(span) > META_SPAN_MAX:
        raise EnvelopeDenied("_meta too large")
    try:
        value = strict_json(span)
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (ValueError, RecursionError):
        raise EnvelopeDenied("invalid _meta") from None
    if size > META_LIMIT:
        raise EnvelopeDenied("_meta too large")


def scan_steps(raw: bytes, limits: EnvelopeLimits, keys_for):
    """The whole check and scan of one body, as a generator returning an Envelope.

    ``keys_for(name)`` says what the gateway reads of ``params.arguments`` for the tool ``name``: a tuple of top-level
    keys (empty: nothing), or None when the tool needs the whole arguments (NeedsFullParse is raised)."""
    yield from utf8_steps(raw)
    scan = _Scan(raw, limits, keys_for)
    message = yield from scan.top()
    if scan.counting and limits.max_containers_per_kib is not None:
        allowed = max(1, limits.max_containers_per_kib * len(raw) // 1024)
        if scan.containers > allowed:
            raise EnvelopeRefused(f"more than {limits.max_containers_per_kib} JSON containers per KiB")
    lone = yield from lone_surrogate_steps(raw)
    if lone:
        raise EnvelopeInvalid("lone surrogate")
    forward = raw
    removed = False
    meta = getattr(scan, "meta", None)
    if meta is not None:
        _check_meta(raw, meta)
        forward = _splice(raw, meta)
        removed = True
    return Envelope(message, forward, scan.elements, scan.containers, removed)


def scan_sync(raw: bytes, limits: EnvelopeLimits | None = None, keys_for=lambda name: ()):
    """Drive ``scan_steps`` to its end without yielding to anything (tests, tools)."""
    steps = scan_steps(raw, limits or EnvelopeLimits(), keys_for)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


async def scan(raw: bytes, limits: EnvelopeLimits, keys_for, sleep):
    """Drive ``scan_steps`` on the event loop: after every SLICE_SECONDS of work, ``await sleep()`` (``asyncio.sleep(0)``),
    so no other task waits longer than a slice plus one step for the loop."""
    steps = scan_steps(raw, limits, keys_for)
    mark = time.perf_counter()
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value
        if time.perf_counter() - mark >= SLICE_SECONDS:
            await sleep(0)
            mark = time.perf_counter()
