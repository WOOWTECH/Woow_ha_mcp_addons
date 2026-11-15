"""0.1.12: the secret-path credential (/private_<token>/mcp) never reaches a log line.

Claude.ai custom connectors cannot send an Authorization header, so the gateway also accepts the add-on token as a
path segment. A request path is then a secret. Uvicorn runs with access_log=False and Starlette's handlers never echo
a path, but any record that might (an access log someone turns on, an exception message, a warning from a library)
is scrubbed when it is created: install() wraps the process-wide LogRecord factory, so every logger and every handler
(including logging.lastResort) only ever sees /private_[REDACTED]/. RedactSecretPaths is the same scrub as a Filter,
for handlers that build records some other way (logging.makeLogRecord).

HM-02 (multi-profile plan section 8.6; the PaaS twin is woow-mcp-server #149): the PaaS log redaction runs first, the
HA rule after it. log_redaction.py is woow-mcp-server 7d111b1's module, vendored byte for byte and never edited here
(a later PaaS change comes in as a whole-file sync; docs/provenance/runtime-patches.json). It masks /private_<token>
in any spelling (percent escapes in any number of layers, separators pasted before, inside or after the token, a
backslash or U+FFFD inside the marker) and the value of every credential query parameter
(log_redaction.CREDENTIAL_PARAM_NAMES: token, access_token, api_key, key, secret, password, sig and the others) as
***, and puts "[redacted: ambiguous URL encoding]" (log_redaction.AMBIGUOUS) in place of text whose URL encoding it
cannot judge. The HA rule then turns /private_*** into /private_[REDACTED], so a secret path reads as before.
scrub() (the record factory and RedactSecretPaths) and scrub_text() (child output, diagnostics.scrub_line) apply both;
redact() and leaks() stay the HA rule alone.

The composition never shows more than the PaaS module alone (the HA rule only replaces text). It could show what the
HA rule alone hides: the PaaS module answers with the decoded text once a decoded-text rule masked something, and
the HA rule then stops at a space or quote that the text spelled as an escape; its query value can also end at a # or
& inside what the HA rule takes as one secret path. shows_hidden() checks every result against the HA rule alone on
the same text, and such a result becomes log_redaction.AMBIGUOUS (fail closed) instead. It compares runs of letters
and digits and, since the HM-02 review, windows of 2 or 3 characters of any kind, which a short value between
symbols needs (a password, user:pw).
"""
from __future__ import annotations

import logging
import re

from . import log_redaction

PRIVATE_SEGMENT = re.compile(r"/private_[^/\s\"'<>\\]*")
REDACTED = "/private_[REDACTED]"
PATH_RULES = ((PRIVATE_SEGMENT, REDACTED),)  # HM-02: the HA rule as (pattern, replacement) pairs, for shows_hidden()
_installed = False


def redact(text: str) -> str:
    """The HA rule alone: every /private_ segment, as far as a slash, space, quote, angle bracket or backslash."""
    return PRIVATE_SEGMENT.sub(REDACTED, text)


def leaks(text: str) -> bool:
    """True when text has a /private_ segment other than the redacted form."""
    return redact(text) != text


# ---- HM-02: the PaaS rules first, then the HA rules ----

# Characters in a row (letters, digits, _ or -) that count as a shown piece of a hidden value: as short as a credential
# that redact_secrets() still replaces (MIN_SECRET below).
PIECE = 4
_RUN = re.compile(r"[A-Za-z0-9_-]{%d,}" % PIECE)
# HM-02 review (MF-1): a value of short runs between symbols (x7!Kq!9z, u:p q r) has no run of PIECE characters. The
# finer pieces are windows of any characters, 2 or 3 in a row, all but one of them letters or digits.
WINDOWS = (2, 3)
_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_SCAN_BUDGET = 1 << 22  # characters of substring search; above it, the set of every piece instead
# the PaaS module's own words, not shown pieces of anything
_PLACEHOLDERS = re.compile(re.escape(log_redaction.AMBIGUOUS) + r"| \u2026\[truncated \d+ chars\]")
# what a mask puts in place of a value (the HA rules' [REDACTED], the PaaS module's *** and its own words): the text
# between two masks is what a result shows
_MASKS = re.compile(r"\[REDACTED\]|\*\*\*|" + _PLACEHOLDERS.pattern)
_VALUE_CHAR = re.compile(r"[^\W_]")  # a letter or a digit
LINE_WITHHELD = "line withheld (redaction failed)"  # scrub_text() when it fails (scrub() withholds a record)


def apply_rules(text: str, rules=PATH_RULES):
    """text with each (pattern, replacement) rule applied in turn, and every match a rule replaced."""
    replaced = []
    for pattern, replacement in rules:
        replaced += [match.group(0) for match in pattern.finditer(text)]
        text = pattern.sub(replacement, text)
    return text, replaced


def _forms(text: str) -> list:
    """text as written and, if it has a percent escape, decoded as many rounds as the PaaS module decodes, with its
    own decoder: log_redaction._unquote gives the text urllib.parse.unquote(errors="replace") gives, in C (the stdlib
    one made the guard 4 to 6.5 times slower than the PaaS module on a line of deep escapes and many lone %)."""
    decoded = text
    for _ in range(log_redaction.MAX_DECODE_ROUNDS):
        if _ESCAPE.search(decoded) is None:
            break
        decoded = log_redaction._unquote(decoded)
    return [text] if decoded == text else [text, decoded]


def _pieces(texts):
    for text in texts:
        for run in _RUN.findall(text):
            for start in range(len(run) - PIECE + 1):
                yield run[start:start + PIECE]


def _windows(texts, size: int) -> set:
    """Every ``size`` characters in a row of texts."""
    found = set()
    for text in texts:
        found.update([text[start:start + size] for start in range(len(text) - size + 1)])
    return found


def _parts(texts) -> set:
    """The parts of texts between their masks: what they show."""
    return {part for text in texts for part in _MASKS.split(text) if part}


def _not_shown(found: set, parts: set, joined: str, every) -> set:
    """found without what parts (joined: the parts with a line break between them) show: a substring search for each
    within _SCAN_BUDGET, else taking away every(parts)."""
    if len(found) * len(joined) > _SCAN_BUDGET:
        return found - set(every(parts))
    return {item for item in found
            if ((not any(item in part for part in parts)) if "\n" in item else (item not in joined))}


def shows_hidden(original: str, shown: str, rules=PATH_RULES) -> bool:
    """True when shown (as written or decoded) has a piece of a value that ``rules`` alone, applied to original,
    replace and do not show anywhere else (as written or decoded): PIECE letters, digits, _ or - in a row, or (HM-02
    review MF-1) a window of WINDOWS characters of any kind, all but one of them letters or digits, which a value of
    short runs between symbols needs (x7!Kq!9z next to ?token=%2Fv, which the PaaS module answers decoded, shows Kq!9z
    once the password rule stops at the decoded space; in &key=cookie: H;L the PaaS module masks key=cookie:, and the
    assignment rule no longer sees cookie:). The composition only takes text away (masks) or decodes it, so such a
    piece is text the rules alone hide; only the parts of shown (between its masks) that the rules alone do not show
    as they are have pieces to check. Linear in the length of the texts: original counts up to the PaaS module's own
    limit (log_redaction.MAX_REDACT_CHARS), which also bounds what the PaaS module shows of it."""
    alone, replaced = apply_rules(original[:log_redaction.MAX_REDACT_CHARS], rules)
    if shown == alone or not replaced:
        return False
    alone_parts = _parts(_forms(alone))
    new = _parts(_forms(shown)) - alone_parts  # a part the rules alone show as it is shows nothing they hide
    if not new:
        return False
    joined, hidden = "\n".join(alone_parts), None
    kinds = [(_pieces, 0)] + [(lambda texts, size=size: _windows(texts, size), size - 1) for size in WINDOWS]
    for every, letters in kinds:
        found = _not_shown(set(every(new)), alone_parts, joined, every)
        found = {item for item in found if len(_VALUE_CHAR.findall(item)) >= letters}
        if not found:
            continue
        if hidden is None:  # a line break ends every run
            hidden = "\n".join(_parts(form for value in replaced for form in _forms(value)))
        if len(found) * len(hidden) <= _SCAN_BUDGET:
            if any(item in hidden for item in found):
                return True
        elif not found.isdisjoint(every((hidden,))):
            return True
    return False


def scrub_text(text: str, rules=PATH_RULES) -> str:
    """HM-02: text as a log may show it: the PaaS rules first, then ``rules`` (the HA rule, or a caller's rules that
    include it); the PaaS placeholder instead when that would show what ``rules`` alone hide. It never raises: child
    output is scrubbed on the supervisor's event loop (diagnostics.ChildLogs.collect, one task per pipe), and an
    exception there would stop reading that pipe; a failure gives LINE_WITHHELD instead."""
    try:
        shown, _ = apply_rules(log_redaction.redact(text), rules)
        return log_redaction.AMBIGUOUS if shows_hidden(text, shown, rules) else shown
    except Exception:
        return LINE_WITHHELD


def _scrub_value(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, (bytes, bytearray)):
        text = bytes(value).decode("latin-1")
        return redact(text).encode("latin-1") if leaks(text) else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        text = str(value)
    except Exception:
        return value
    return redact(text) if leaks(text) else value


def _message(record):
    try:
        return record.getMessage()
    except Exception:
        return None


_ACCESS_ARGS = 5  # uvicorn's AccessFormatter unpacks client, method, path, HTTP version and status


def _fail_closed(record, message, exc_text, stack_info):
    """HM-02: a message, exception text or stack that now shows what the HA rule alone hides in it as it was created
    becomes the PaaS placeholder. uvicorn's access record keeps its five arguments: the path goes first, then every
    other string argument (as log_redaction does for that record)."""
    if message is not None and shows_hidden(message, record.getMessage()):
        args = record.args
        if record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) == _ACCESS_ARGS:
            record.args = (args[0], args[1], log_redaction.AMBIGUOUS, args[3], args[4])
            if shows_hidden(message, record.getMessage()):
                record.args = tuple(log_redaction.AMBIGUOUS if isinstance(a, str) else a for a in record.args)
        else:
            record.msg, record.args = log_redaction.AMBIGUOUS, ()
    if exc_text and record.exc_text and shows_hidden(exc_text, record.exc_text):
        record.exc_text = log_redaction.AMBIGUOUS
    if stack_info and record.stack_info and shows_hidden(stack_info, record.stack_info):
        record.stack_info = log_redaction.AMBIGUOUS


def scrub(record: logging.LogRecord) -> logging.LogRecord:
    """Redact the message template, its arguments, the formatted exception and the stack in place.

    HM-02: the PaaS rules first, log_redaction.scrub_record (it also renders the message, for a secret split across
    arguments, keeps uvicorn's access record at its five arguments and never raises), then the HA rule as before; a
    part that then shows what the HA rule alone hides in it as created becomes the PaaS placeholder (_fail_closed).
    Arguments are redacted one by one (not merged into the message) so formatters that read record.args, such as
    uvicorn's access formatter, keep working. If the final message still matches (msg was an object), the record
    carries the redacted text instead.
    """
    try:
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        created = (_message(record), record.exc_text, record.stack_info)
        log_redaction.scrub_record(record)
        record.msg = _scrub_value(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub_value(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _scrub_value(v) for k, v in record.args.items()}
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        message = record.getMessage()
        if leaks(message):
            record.msg, record.args = redact(message), ()
        _fail_closed(record, *created)
    except Exception:
        # Never let logging fail open with the raw text: drop the content instead.
        record.msg, record.args, record.exc_info, record.exc_text = "log record withheld (redaction failed)", (), None, None
    return record


class RedactSecretPaths(logging.Filter):
    def filter(self, record):
        scrub(record)
        return True


def guard_handlers(*names):
    """Also filter the handlers uvicorn.Config just configured (second layer; the record factory is the first)."""
    for name in ("", *names):
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, RedactSecretPaths) for f in handler.filters):
                handler.addFilter(RedactSecretPaths())


UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


def install():
    """Idempotent. Call before any listener starts (make_apps and both launchers do).

    HM-02: the factory runs scrub(): the PaaS rules, then the HA rule. The PaaS module's own install() is not used: its
    logger filters (uvicorn.access, uvicorn.error, httpx) would mask again after the HA rule, and a handler without
    RedactSecretPaths (logging.lastResort) would then show /private_***; guard_handlers() stays the second layer. Its
    lazily compiled patterns are compiled here, as its install() does, so that no request pays for that.
    """
    global _installed
    if _installed:
        return
    log_redaction._warm_patterns()
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        return scrub(previous(*args, **kwargs))

    logging.setLogRecordFactory(factory)
    _installed = True


# 0.2.0 (owner decision 2026-10-15): backend errors are relayed with their own text, as the PaaS servers do. Every
# credential this add-on holds is replaced in every reply the gateway relays, wherever a backend or child echoes it.
SECRET_MASK = "[REDACTED]"
SECRET_FIELDS = ("password", "api_key", "api_secret", "master_key", "app_password", "gateway_api_key",
                 "dashboard_password")
BASIC_PAIRS = (("username", "password"), ("api_key", "api_secret"), ("username", "app_password"),
               ("dashboard_username", "dashboard_password"))
MIN_SECRET = 4  # shorter values are too common in ordinary text to replace


def secret_values(state):
    """The credentials of a state: the add-on and child tokens, n8n's backend key and MCP access token, every secret connection field, and
    the Basic Authorization forms (base64 of user:secret, also URL-safe and unpadded) built from them. Longest first."""
    import base64
    found = {getattr(state, "token", None), getattr(state, "child_token", None), getattr(state, "backend_key", None),
             getattr(state, "mcp_access_token", None)}  # 0.2.1: n8n's MCP access token
    connection = getattr(state, "connection", None)
    fields = connection.model_dump() if connection is not None else {}
    found.update(fields.get(name) for name in SECRET_FIELDS)
    for user, secret in BASIC_PAIRS:
        if isinstance(fields.get(user), str) and isinstance(fields.get(secret), str):
            raw = f"{fields[user]}:{fields[secret]}".encode()
            for encode in (base64.b64encode, base64.urlsafe_b64encode):
                text = encode(raw).decode()
                found.update((text, text.rstrip("=")))
    return tuple(sorted((v for v in found if isinstance(v, str) and len(v) >= MIN_SECRET), key=len, reverse=True))


def redact_secrets(value, secrets):
    """value with every occurrence of each secret replaced by [REDACTED], in every string (keys too) of a JSON value."""
    if not secrets:
        return value
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, SECRET_MASK)
        return value
    if isinstance(value, list):
        return [redact_secrets(item, secrets) for item in value]
    if isinstance(value, dict):
        return {redact_secrets(key, secrets): redact_secrets(item, secrets) for key, item in value.items()}
    return value
