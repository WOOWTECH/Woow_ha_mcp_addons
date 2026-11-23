"""HM-19c request guard: what a large request may cost before it is parsed (contract 2.4, 5, 6; decisions.md HM-30 Q4).

Why. A body's byte count says little about what ``json.loads`` makes of it: 800 KB of ``{"a":1}`` (99,990 objects) is an
18 MiB object graph (22.9 times), the gateway builds it, keeps it until the request ends and forwards it, and the child
builds another. HM-19c (J6412, 64 concurrent) measured a 314 ms longest event-loop stop (limit 50 ms), 42.3 times
amplification (limit 20) and 1.62 s more p99 for another profile (limit 2d + 0.2 s). The structure guard (depth 64,
200,000 elements) and the byte budget count other things, so none of them stopped it, and the parse itself (a C call
that holds the GIL, on a thread as on the loop) cannot be cut into pieces.

What. For a switched-on product (the add-on's profiles share one process), for a POST body above LARGE_REQUEST_BYTES,
before ``json.loads``:

1. ``classify``: a body whose cheap upper bound (C ``bytes.count`` of commas and container openers, strings included) is
   large is "heavy"; one long string (a file, base64, text) is not and is parsed as before, without a place or an estimate.
   A heavy body takes the add-on's ONE large-parse place (``ParsePlace``); it never waits: another heavy parse in
   process means the caller answers the contract's busy shape at once (POST: 200, -32003 under its own id,
   Retry-After 5, Cache-Control no-store; 503 when no id can be read).
2. ``scan`` reads the body ONCE in SCAN_CHUNK pieces (a C call each, a breath between them: the loop is never behind
   one C call longer than a piece) and keeps only counts and the structural bytes; nothing is built.
3. ``too_costly`` turns the counts into the parsed memory (the whole pipeline: the gateway's graph, the child's, the byte
   copies) and the longest stretch the parser runs without calling back into Python, with coefficients measured on this
   code (see the constants). Above MAX_AMPLIFICATION times the body (the 20x of contract 5), or a stretch above
   MAX_STALL_REFERENCE_SECONDS (50 ms on the J6412 divided by J6412_FACTOR and SAFETY), the request is refused
   (200 + -32602 under its id, else 413: the structure guard's shape) and never parsed.
4. ``parse_large`` runs the guard, the estimate and ``strict_json`` on a worker thread that breathes like the reply
   worker (reply_worker.breathe); ``encode_forward`` writes the forwarded bytes the same way.

Nothing here reads a switch: ``gateway.json_body`` calls it only with the profile's parse slot (switched on), so a
switched-off product's requests are parsed exactly as before. Nothing of a body is ever put in a message or a log.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import gc
import re
import threading
import time

from . import reply_worker, request_budget
from .config import strict_json
from .request_limits import (DEFAULT_MAX_DEPTH, DEFAULT_MAX_TOTAL_ELEMENTS, NOT_UTF8_REASON, RequestLimitError,
                             _STRUCTURE_BYTES, _walk_structure, head_tail_id, ID_WINDOW, not_utf8, too_complex)

#: A request this large (bytes) is estimated and takes the add-on's one large-parse place (contract 2.4: the byte
#: budget's own small request is also 64 KiB). Below it nothing changes.
LARGE_REQUEST_BYTES = request_budget.SMALL_REQUEST_BYTES
#: request.state attribute json_body sets for a body above LARGE_REQUEST_BYTES (a switched-on product's): the gateway writes
#: the bytes it forwards for it in pieces on a thread (encode_forward).
LARGE_BODY = "request_guard_large_body"
#: One scan piece (a C call of ~1.3 ms for the densest body on an EPYC 7713, ~10 ms on a J6412 at J6412_FACTOR).
SCAN_CHUNK = 32 * 1024
#: A large body whose commas plus container openers, counted over its raw bytes (strings included: an upper bound of what
#: the scan would count), are at most this many is not "heavy" (see ``light``): it takes no place and is not scanned for cost.
LIGHT_ELEMENTS = 1_500

#: The contract's amplification gate (5, HM-19c): the whole pipeline's memory over the body's bytes.
MAX_AMPLIFICATION = 20.0

# --- measured coefficients (CPython 3.13.15, EPYC 7713 one core; tests/test_request_guard.py::test_model_bounds_the_measured_
# shapes re-measures them on every run and fails when any shape's memory is above the model; the report has the table) ---
#: Bytes of the parsed graph per feature: an upper envelope of tracemalloc of ``strict_json`` over 59 measured shapes
#: (empty and tiny objects, arrays of every scalar, wide and nested dicts, Odoo batches, random mixes, every alphabet).
BYTES_PER_OBJECT = 190        # a dict: ``{"a":1}`` is 184 bytes with its one entry (192 with its list slot); empty 64. Above the
                              # measured 136 on purpose: the HM-19c objects shape sits on this limit, and the first local run
                              # at the limit peaked at 20.0 times (best 13.6)
BYTES_PER_MEMBER = 60         # one "key": value entry (hash entry and index, with the table's growth slack); keys repeat
                              # and the decoder shares them: a key costs its entry and its bytes, not a str object
BYTES_PER_ARRAY = 80          # a list object; its slots are BYTES_PER_ITEM
BYTES_PER_ITEM = 12           # one array slot (8) with the list's over-allocation
BYTES_PER_STRING = 72         # the str object of a string VALUE (compact ASCII 41 bytes before its text, others more)
BYTES_PER_NUMBER = 36         # an int or float that is not one of the interpreter's cached ints
#: The child parses the forwarded bytes into a graph of its own (HM-19c: 42.3 total against the gateway's 22.9 by
#: tracemalloc; the SDK's pydantic validation builds about as much), as a fraction of the gateway's.
CHILD_GRAPH_FACTOR = 0.9
#: Byte copies of the body alive at once (read, joined, forwarded, the child's receive buffer).
BODY_COPIES = 3.0

# --- the time model. Seconds on the measuring machine (one core). The gate is the longest stretch the parser runs
# without calling back into Python: strict_json's checkpoint is called once per object and once per 1,024 numbers
# (config.strict_json), so a stretch is the strings, empty arrays and literals between two objects. One long string is
# one C call at memcpy speed (1.3 to 2.7 ns a byte) whatever the model says; it is not part of the gate (see the report).
SECONDS_PER_STRING = 75e-9       # a string in an array (short_strs: 69 ns); each is a str object and a slot
SECONDS_PER_ARRAY = 75e-9        # an empty array in an array (empty_arrs: 68 ns)
SECONDS_PER_LITERAL = 20e-9      # true, false, null (bools: 14 ns)
#: The whole parse, for the report and the CPU assertions (fit over the same shapes, then raised until none is under).
SECONDS_PER_OBJECT = 160e-9
SECONDS_PER_MEMBER = 300e-9
SECONDS_PER_ITEM = 60e-9
SECONDS_PER_NUMBER = 280e-9
SECONDS_PER_BYTE = 2.6e-9
#: What the J6412 costs against the measuring machine (one core): 丁's calibration (core-fix/calibration) gives the
#: number; the report says which. SAFETY covers what the model cannot see.
J6412_FACTOR = 8.0
SAFETY = 1.5
#: The loop's longest stop (contract 6) and what is left of it for a stretch on the measuring machine.
LOOP_LIMIT_SECONDS = 0.050
MAX_STALL_REFERENCE_SECONDS = LOOP_LIMIT_SECONDS / (J6412_FACTOR * SAFETY)

TOO_MUCH_MEMORY = "the parsed request would need more than 20 times its size in memory"
TOO_SLOW = "the request would take too long to parse"


# The same strings as request_limits._COMPLETE_STRING (a complete JSON string, the possessive repeat keeps an
# unterminated one from backtracking), written with character-class repeats: four times faster on long strings.
_STRING = re.compile(rb'"[^"\\]*+(?:\\.[^"\\]*+)*+"', re.DOTALL)
_LONE_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89a-fA-F]")
_ASTRAL = re.compile(rb"[\xf0-\xf4]|\\u[dD][89abAB]")      # a character outside the BMP: its string is 4 bytes a character
_ESCAPE_U = re.compile(rb"\\u")                        # an escape that may make a string 2 bytes a character
# a number that is not one of the interpreter's cached ints (-5..256): three digits, a sign before a digit, a fraction or
# an exponent (a number with more than one match counts more than once: a bound)
_UNCACHED_NUMBER = re.compile(rb"[0-9]{3,}|-[0-9]|[0-9][.eE]")


@dataclass(frozen=True)
class Scan:
    """What one pass over a body counted: all outside strings except ``strings`` and ``string_bytes``."""
    size: int
    objects: int
    arrays: int
    commas: int
    members: int       # colons: object entries (each has a key string)
    strings: int       # complete strings (keys and values)
    string_bytes: int  # bytes between their quotes, as sent
    literals: int      # true, false, null
    uncached_numbers: int  # numbers outside strings that are not cached small ints (a bound)
    structural: bytes  # [ ] { } , outside strings, in order (what the depth and element guard walks)
    width: int = 1     # bytes a character of any string may take in memory: 1 ASCII, 2 BMP, 4 a character outside the BMP
    stall: float = 0.0  # longest stretch the parser runs without a callback, seconds on the measuring machine (model)

    @property
    def elements(self) -> int:
        """Elements as the structure guard counts them (commas and container openers outside strings)."""
        return self.commas + self.objects + self.arrays

    @property
    def items(self) -> int:
        """Array slots (a bound: commas that do not separate object members, plus one per container)."""
        return max(0, self.commas - self.members + self.objects + self.arrays)

    @property
    def value_strings(self) -> int:
        return max(0, self.strings - self.members)

    @property
    def numbers(self) -> int:
        """Numbers (a bound): values that are not containers, string values or literals; an int under 257 or a float
        needs memory only when it is not one of the interpreter's cached ints: a token of fewer than 2 bytes never is
        one that is not cached, so the bound is by what the scan counted."""
        values = self.members + self.items
        bound = max(0, values - self.objects - self.arrays - self.value_strings - self.literals)
        return min(bound, self.uncached_numbers)


def cheap_counts(raw: bytes):
    """C-speed upper bounds (strings included): (openers, commas). Used for the light test only."""
    return raw.count(b"{") + raw.count(b"["), raw.count(b",")


def light(raw: bytes) -> bool:
    """A large body that cannot be heavy to parse: its commas and container openers over the raw bytes (the most the
    scan could count) are few. One long string (a file, base64, text of any alphabet), a few records: yes; the near-limit
    ``[{"a":1}, ...]`` and ``[[],[]...]``: no."""
    openers, commas = cheap_counts(raw)
    return openers + commas <= LIGHT_ELEMENTS


def scan(raw: bytes, checkpoint=None) -> Scan:
    """One linear pass in SCAN_CHUNK pieces, ``checkpoint`` (a breath) called between them. State carried across a piece
    boundary: inside a string, and after a backslash. A piece that starts inside a string gets the quote (and the
    backslash) that open it put in front, so the same regex reads it. The structural bytes equal the one-call scan of
    request_limits._scan_structure for every input (tests/test_request_guard.py compares them on random bodies)."""
    in_string = escaped = False
    parts: list[bytes] = []
    outside = strings = colons = objects = arrays = commas = literals = uncached = 0
    run = longest = 0.0
    width = 1
    for start in range(0, len(raw), SCAN_CHUNK):
        piece = raw[start:start + SCAN_CHUNK]
        if in_string:
            piece = (b'"\\' if escaped else b'"') + piece
        stripped, complete = _STRING.subn(b"", piece)
        strings += complete
        before, quote, after = stripped.partition(b'"')
        if quote:
            in_string = True
            escaped = (len(after) - len(after.rstrip(b"\\"))) % 2 == 1
        else:
            in_string = escaped = False
        outside += len(before)
        if width < 4:  # one such character makes its whole string that wide
            if _ASTRAL.search(piece):
                width = 4
            elif width < 2 and (not piece.isascii() or _ESCAPE_U.search(piece)):
                width = 2
        colons += before.count(b":")
        structural = before.translate(_STRUCTURE_BYTES).replace(b"\x00", b"")
        opened_objects = structural.count(b"{")
        opened_arrays = structural.count(b"[")
        objects += opened_objects
        arrays += opened_arrays
        commas += structural.count(b",")
        parts.append(structural)
        true, false, null = before.count(b"true"), before.count(b"false"), before.count(b"null")
        literals += true + false + null
        uncached += _UNCACHED_NUMBER.subn(b"", before)[1]
        # A stretch without a callback (SECONDS_PER_STRING...): pieces without an object opener run together; the piece
        # that has one ends the stretch, and its own work counts at both ends (where in it the opener is, is not known).
        here = complete * SECONDS_PER_STRING + opened_arrays * SECONDS_PER_ARRAY + (true + false + null) * SECONDS_PER_LITERAL
        run += here
        longest = max(longest, run)
        run = here if opened_objects else run
        if checkpoint is not None:
            checkpoint()
    # bytes of strings = the body less what is outside them and their quotes (an unterminated last string counts as 0)
    string_bytes = max(0, len(raw) - outside - 2 * strings)
    return Scan(len(raw), objects, arrays, commas, colons, strings, string_bytes, literals, uncached, b"".join(parts), width, longest)


def graph_bytes(found: Scan) -> float:
    """The parsed graph in the gateway, bytes (non-ASCII text is narrower in memory than on the wire: counted as sent)."""
    return (found.objects * BYTES_PER_OBJECT + found.members * BYTES_PER_MEMBER + found.arrays * BYTES_PER_ARRAY
            + found.items * BYTES_PER_ITEM + found.value_strings * BYTES_PER_STRING
            + found.numbers * BYTES_PER_NUMBER + found.string_bytes * found.width)


def pipeline_bytes(found: Scan) -> float:
    """The whole request's memory: the gateway's graph, the child's, and the copies of the body."""
    return graph_bytes(found) * (1.0 + CHILD_GRAPH_FACTOR) + found.size * BODY_COPIES


def amplification(found: Scan) -> float:
    return pipeline_bytes(found) / max(1, found.size)


def stall_seconds(found: Scan) -> float:
    """The longest stretch the parse runs without a callback (seconds on the measuring machine): measured per piece
    during the scan (Scan.stall). The J6412's is this times J6412_FACTOR."""
    return found.stall


def parse_seconds(found: Scan) -> float:
    """The whole parse by strict_json (seconds on the measuring machine), for the report and the CPU assertions."""
    return (found.objects * SECONDS_PER_OBJECT + found.arrays * SECONDS_PER_ARRAY + found.members * SECONDS_PER_MEMBER
            + found.items * SECONDS_PER_ITEM + found.value_strings * SECONDS_PER_STRING
            + found.literals * SECONDS_PER_LITERAL + found.numbers * SECONDS_PER_NUMBER
            + found.size * SECONDS_PER_BYTE)


def too_costly(found: Scan):
    """The refusal reason (English short phrase, no content) or None."""
    if amplification(found) > MAX_AMPLIFICATION:
        return TOO_MUCH_MEMORY
    if stall_seconds(found) > MAX_STALL_REFERENCE_SECONDS:
        return TOO_SLOW
    return None


# --- the add-on's one large-parse place -------------------------------------------------------------------------

class ParsePlace:
    """One place for the whole process (the profiles of an add-on share it): take() never waits."""

    def __init__(self, places: int = 1):
        self._lock = threading.Lock()
        self._free = places
        self._places = places

    def take(self) -> bool:
        with self._lock:
            if self._free <= 0:
                return False
            self._free -= 1
            return True

    def give(self) -> None:
        with self._lock:
            self._free = min(self._places, self._free + 1)

    @property
    def free(self) -> int:
        with self._lock:
            return self._free


#: The process's place (tests replace it with their own through ``gateway.json_body(place=...)``).
PLACE = ParsePlace(1)


class ParseBusy(Exception):
    """Another large parse is in process: the caller answers the contract's busy shape (never a queue). ``ident`` is the
    request's id from its head and tail (request_limits.head_tail_id), or None."""

    def __init__(self, ident=None):
        super().__init__("another large request is being parsed")
        self.ident = ident


def busy_text() -> str:
    return ("this MCP server is already parsing another large request, so this one was not processed. Retry shortly, or "
            "send smaller requests. (這台 MCP 伺服器正在處理另一個大型請求，這個請求沒有處理，請稍後再試，或改送較小的請求。)")


def too_costly_error(raw: bytes, reason: str) -> RequestLimitError:
    """A refusal in the structure guard's shape (request_limits.too_complex): 200 + -32602 under the request's id
    (head and tail), else 413; the message names the limit and what to do, never the content."""
    message = (f"MCP request body was refused because parsing it would cost too much ({reason}) and it was not "
               "processed. Send fewer or flatter items per call: split the work into several calls, and send file "
               "contents as one string. (MCP 請求內容解析後會佔用過多記憶體或時間，未處理；請減少每次呼叫的項目數或巢狀層數，"
               "拆成多次呼叫，檔案內容請以單一字串傳送。)")
    ident = head_tail_id(raw[:ID_WINDOW], raw[-ID_WINDOW:])
    return RequestLimitError(message, status=413 if ident is None else 200, code=-32602, rpc_id=ident,
                             kind="cost", log_reason=reason)


def structure_reason(found: Scan, *, max_depth: int = DEFAULT_MAX_DEPTH,
                     max_elements: int = DEFAULT_MAX_TOTAL_ELEMENTS):
    """request_limits.structure_violation's answer for the body that was scanned, without scanning it again."""
    return _walk_structure(found.structural, max_depth, max_elements)


# --- the thread's side -------------------------------------------------------------------------------------------

class Breath:
    """Lets the thread that runs a request's parse breathe like the reply worker (reply_worker.breathe: after
    SLICE_SECONDS of work it sleeps, and goes on while the loop is busy): set on the thread that calls ``bind`` and
    undone by ``release``. The GIL convoy of HM-30 (the loop waits for a thread that never gives it up) is the same."""

    def __init__(self, loop: asyncio.AbstractEventLoop, loop_thread: int):
        self.loop = loop
        self.loop_thread = loop_thread

    def bind(self):
        breath = reply_worker._breath
        breath.since = time.perf_counter()
        breath.loop_thread = self.loop_thread
        breath.ready = getattr(self.loop, "_ready", None)

    @staticmethod
    def release():
        reply_worker._breath.since = None

    @staticmethod
    def checkpoint():
        reply_worker.breathe()


def check_lone_surrogates(value, checkpoint=None) -> None:
    """The ``json.dumps(value, ensure_ascii=False).encode()`` check of gateway._parse_json_body (a lone surrogate, which
    only a ``\\u`` escape can make, is a ValueError), as a walk with breaths instead of one C call over the whole value."""
    stack = [value]
    steps = 0
    while stack:
        item = stack.pop()
        if type(item) is str:
            item.encode("utf-8")
        elif type(item) is dict:
            for key, member in item.items():
                key.encode("utf-8")
                if type(member) in (str, dict, list):
                    stack.append(member)
        elif type(item) is list:
            for member in item:
                if type(member) in (str, dict, list):
                    stack.append(member)
        steps += 1
        if checkpoint is not None and steps % 512 == 0:
            checkpoint()


def parse_large(raw: bytes, guard, breath: Breath, heavy: bool):
    """The parse of a body larger than LARGE_REQUEST_BYTES, on a worker thread (gateway.json_body): the structure
    guard, for a heavy body (``classify``: it holds the add-on's one place) the estimate, and strict_json in pieces with
    breaths. Returns the parsed value. Raises RequestLimitError (the guard's or the estimate's)."""
    breath.bind()
    held = gc.isenabled()
    if held:
        gc.disable()  # a full collection walks every object of the add-on in one C call (as the reply worker holds it off)
    try:
        if guard is not None and not_utf8(raw):
            raise too_complex(raw, NOT_UTF8_REASON)
        if guard is not None:
            openers, commas = cheap_counts(raw)
            if heavy or openers > guard.max_depth or openers + commas > guard.max_total_elements:
                found = scan(raw, breath.checkpoint)
                reason = structure_reason(found, max_depth=guard.max_depth, max_elements=guard.max_total_elements)
                if reason is not None:
                    raise too_complex(raw, reason)
                if heavy:
                    reason = too_costly(found)
                    if reason is not None:
                        raise too_costly_error(raw, reason)
        value = strict_json(raw, checkpoint=breath.checkpoint)
        if _LONE_SURROGATE_ESCAPE.search(raw):
            check_lone_surrogates(value, breath.checkpoint)
        return value
    finally:
        breath.release()
        if held:
            gc.enable()


def classify(raw: bytes) -> bool:
    """True when a body of at least LARGE_REQUEST_BYTES is heavy: it takes the place and is estimated."""
    return len(raw) > LARGE_REQUEST_BYTES and not light(raw)


def encode_forward(value, breath: Breath) -> bytes:
    """``json.dumps(value, separators=(",", ":")).encode()`` byte for byte (the bytes the gateway forwards), written in
    pieces with breaths on a worker thread: reply_worker.encoded (D1) never makes one C call of more than about
    PIECE_BYTES. For a large request only; a small one is serialized on the loop as before."""
    breath.bind()
    try:
        return reply_worker.encoded(value, breath.checkpoint)
    finally:
        breath.release()
