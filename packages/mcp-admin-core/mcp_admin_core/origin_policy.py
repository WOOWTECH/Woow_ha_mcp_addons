"""The secret path's Origin allowlist of a switched-on add-on: one for every profile, report-only by default
(multi-profile plan 8.7, 12.3 HM-27; DQ-11 (a), the user's decision of 2026-11-14; contract 2.6, 3.1, 3.5, 4.1 and
section 9; FM-73, FM-74, FM-123; acceptance T-24).

PaaS (woow-mcp-server 69ac425, mcp_admin_core/origin_security.py and docs/security/mcp-origin-policy.md; R01 D-01, R04
S-09, S-10, R07 X-17) checks every /private_* request against the deployment's list (MCP_ADMIN_ALLOWED_ORIGINS) in a
mode (MCP_ADMIN_ORIGIN_MODE): report-only, the default, writes one decision=would_deny line and lets the request
through; enforce answers 403. HA, once a product is switched on (features.enabled; run_product's ProfileManager):

- One policy for the add-on, every profile's secret path (FM-73: service level, no per-profile rules), kept in
  /data/mcp/origin-policy.json (POLICY_NAME; never in the default profile's state): its mode, report-only or enforce,
  and the origins it allows. Without the file (nothing saved yet): report-only and https://claude.ai (the PaaS chart's
  defaults). Nothing is written until the panel saves it (profile_admin: GET and PUT {base}/api/origin-policy through
  the shared management pipeline, If-Match, Idempotency-Key, the receipts beside it in .origin-policy.json.operations.
  json).
- Checked on the secret path once its token is (gateway.make_apps origin_policy: after the method rule, where Headscale's
  rule sits; a wrong token never learns it and a client without one cannot write a line, unlike PaaS where the check
  comes first, K-09): a request without an Origin passes, as one with exactly one the list holds (normalized as PaaS
  does: the scheme and the host in lowercase, the default port left out, ASCII only). Any other, not listed, malformed,
  null or more than one: in report-only it is answered as without the check, byte for byte, and writes one
  decision=would_deny line; in enforce it is 403 {"error":"request denied"} (the gateway's fixed answer, the Bearer
  path's and Headscale's; PaaS answers {"detail":"ORIGIN_DENIED"}) and writes one decision=deny line.
- No CORS (FM-74): no Access-Control-* or Vary header, in either mode. PaaS report-only answers what its pre-#136 CORS
  answered, reflecting any origin with credentials; HA never had CORS and adding it would widen access. A preflight
  stays today's 405 after the token check.
- Not here: the Bearer path, where any Origin is 403 as before (gateway.serve; DQ-11's second question waits for the
  S14 measurement), and Headscale, which keeps its own rule (run_product's secret_path_allowed_origins: only
  https://claude.ai, enforced, no line; the user's HA Headscale decision, R01 H-08): its manager makes no policy, the
  file is never read and the route is an unknown operation.
- A file the add-on cannot use (not a single-link 0600 regular file of this uid within MAX_POLICY_BYTES, a link, or not
  this module's exact JSON in its normal form): every secret-path request whose token is checked is 503 {"error":"state
  unavailable"}, with or without an Origin (PaaS answers a bad value at runtime with 503 on the MCP path, with or without
  an Origin, and refuses to start on one at startup: on HA that would leave no way to repair it). One WARNING when it is
  found so (once per state of the file, never its content). The panel shows it and saves a new one over it (its If-Match
  is the unusable file's own ETag). The file is looked at (one lstat) at every such request and read again whenever it
  changed: a valid replacement applies at once, as every state of HA (plan 8.8 #46).
- The lines (PaaS log_denial, on HA's line): the decision, the mode, the reason (not_allowed, malformed, duplicate,
  null) and the origin as PaaS renders it (normalized scheme://host[:port]; of a malformed one only its
  scheme://host[:port] and which parts it had, or a summary without its text), with the profile (its id's first 8
  characters, profiles.log_id): never the path, the token, the query, another header or the body. One line per profile
  and (decision, reason, origin) a LOG_INTERVAL_SECONDS, at most LOG_MAX_PER_WINDOW lines a LOG_WINDOW_SECONDS per
  profile (PaaS: per origin a minute, 20 a minute for the whole service, which one flood fills for every profile); the
  lines held back are counted and written as one line before the profile's next line, or by a timer when its window
  ends. A line that cannot be written never changes the answer.

Switched off (or Headscale) none of this exists: make_apps gets no origin_policy, the file is never read or written,
{base}/api/origin-policy is an unknown operation (contract 1.2).
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import astuple, dataclass
from functools import partial
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import time

from . import profiles
from .admin_auth import BadRequest
from .config import ConfigError, strict_json
from .operations import OperationJournal

logger = logging.getLogger(__name__)

POLICY_NAME = 'origin-policy.json'  # in the default profile's store directory (/data/mcp), beside profiles.json
POLICY_VERSION = 1
MAX_POLICY_BYTES = 16384
MODE_REPORT_ONLY, MODE_ENFORCE = 'report-only', 'enforce'
MODES = (MODE_REPORT_ONLY, MODE_ENFORCE)  # exactly these, in lowercase (the PaaS chart's check)
DEFAULT_ALLOWED = ('https://claude.ai',)  # the PaaS chart 0.1.10 default
MAX_ORIGINS = 16  # HA's bound (PaaS has none: an environment variable); a request over it is 422
STATE_DEFAULT, STATE_SAVED, STATE_UNUSABLE = 'default', 'saved', 'unusable'  # origin_policy_state
ETAG = re.compile(r'"o1-[0-9a-f]{64}"')
KIND = 'origin.policy'  # the receipt's kind (operations.OperationJournal results)
RESULTS = {KIND: {'status': 'ok', 'origin_policy_state': STATE_SAVED}}
INVALID = 'origin_policy_invalid'  # 422, shape A: the request's mode or origins break the rules (no value echoed)
UNUSABLE_WARNING = ("multi-profile: the secret path's Origin policy (origin-policy.json) cannot be used; MCP requests "
                    "on secret paths are refused (503) until it is saved again in the panel")

DECISION_WOULD_DENY, DECISION_DENY = 'would_deny', 'deny'
REASON_NOT_ALLOWED, REASON_MALFORMED, REASON_DUPLICATE, REASON_NULL = 'not_allowed', 'malformed', 'duplicate', 'null'
LOG_INTERVAL_SECONDS = 60.0  # one line per profile and (decision, reason, origin) this often (PaaS: per origin)
LOG_WINDOW_SECONDS = 60.0
LOG_MAX_PER_WINDOW = 20  # lines per profile and window (PaaS: for the whole service)
LOG_MAX_KEYS = 256  # (decision, reason, origin) remembered per profile (bounded by the window's lines anyway)
LOG_MAX_PROFILES = 32  # profiles whose window is remembered (6 at most at once; ids of deleted ones go first)
MAX_RENDERED_ORIGIN = 120

# ---- the origin rule (PaaS origin_security.normalize_origin; Headscale's legacy trailing dot is not HA's) ----

# re.ASCII: without it re.I folds Unicode case (the Kelvin sign U+212A matches k, U+017F s), so a non-ASCII host would
# be normalized into an ASCII one of the list. An Origin header is ASCII only.
_ORIGIN = re.compile(r'(https?)://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::([0-9]+))?', re.I | re.ASCII)
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.I | re.ASCII)


def normalize_origin(value: str) -> tuple[str, str, int]:
    """(scheme, host, port) of an exact http(s) origin; ValueError for anything else (a path, a trailing slash or dot,
    userinfo, a query, *, null, a port outside 1-65535, a non-ASCII character)."""
    match = _ORIGIN.fullmatch(value)
    if match is None:
        raise ValueError('not an origin')
    scheme, host, port = match.groups()
    scheme, host = scheme.lower(), host.lower()
    if host.startswith('['):
        host = str(ipaddress.IPv6Address(host[1:-1]))
    elif len(host) > 253 or any(not _LABEL.fullmatch(label) for label in host.split('.')):
        raise ValueError('not an origin host')
    number = int(port) if port else (443 if scheme == 'https' else 80)
    if not 1 <= number <= 65535:
        raise ValueError('not an origin port')
    return scheme, host, number


def format_origin(scheme: str, host: str, port: int) -> str:
    shown = f'[{host}]' if ':' in host else host
    default = 443 if scheme == 'https' else 80
    return f'{scheme}://{shown}' if port == default else f'{scheme}://{shown}:{port}'


def canonical(value: str) -> str:
    """The normal form of an origin (scheme://host[:port], lowercase, the default port left out); ValueError."""
    return format_origin(*normalize_origin(value))


# ---- how a line shows the Origin it was sent (PaaS origin_security, rendering only, unchanged) ----

_URL_SHAPE = re.compile(r'https?://[!-~]+', re.I | re.ASCII)
_KNOWN_SCHEMES = frozenset({'http', 'https', 'ftp', 'ws', 'wss', 'file', 'data', 'javascript', 'blob', 'about',
                            'chrome-extension', 'moz-extension', 'capacitor', 'ionic', 'app'})
_SCHEME_PREFIX = re.compile(r'([a-z][a-z0-9+.-]{0,20}):', re.I | re.ASCII)


def _escape_char(char: str) -> str:
    code = ord(char)
    if code < 0x100:
        return f'\\x{code:02x}'
    if code < 0x10000:
        return f'\\u{code:04x}'
    return f'\\U{code:08x}'


def sanitize_origin_text(value: str, limit: int = MAX_RENDERED_ORIGIN) -> str:
    """Any header value as printable ASCII for one log line: '!' to '~' kept but '"' and '\\', everything else
    escaped (\\xHH, \\uHHHH); over limit characters it is cut and ends with '...' (never inside an escape). Only the
    characters needed are looked at."""
    pieces: list[str] = []
    size = 0
    for char in value:
        piece = char if ('!' <= char <= '~' and char not in '"\\') else _escape_char(char)
        pieces.append(piece)
        size += len(piece)
        if size > limit:
            break
    if size <= limit:
        return ''.join(pieces)
    kept: list[str] = []
    size = 0
    for piece in pieces:
        if size + len(piece) > limit - 3:
            break
        kept.append(piece)
        size += len(piece)
    return ''.join(kept) + '...'


def _summarize_malformed(value: str) -> str:
    """A malformed value that is not URL-shaped: its length, its classes of characters and a scheme prefix of a fixed
    list; none of its text (a bare private_<token> or Bearer <token> shows nothing of the token)."""
    classes = []
    for name, test in (('alpha', lambda c: c.isascii() and c.isalpha()), ('digit', lambda c: c.isascii() and c.isdigit()),
                       ('space', lambda c: c in ' \t'), ('control', lambda c: c < ' ' or c == '\x7f'),
                       ('non-ascii', lambda c: not c.isascii())):
        if any(test(c) for c in value[:4096]):
            classes.append(name)
    if any('!' <= c <= '~' and not c.isalnum() for c in value[:4096]):
        classes.append('punct')
    summary = f"non-url(len={len(value)},classes={'+'.join(classes) or 'none'}"
    prefix = _SCHEME_PREFIX.match(value)
    if prefix and prefix.group(1).lower() in _KNOWN_SCHEMES:
        summary += f',scheme={prefix.group(1).lower()}'
    return summary + ')'


def _summarize_url_shaped(value: str) -> str | None:
    """A URL-shaped malformed value: its scheme://host[:port] and which parts it had (has=userinfo+path+query+
    fragment), never their content; None when no valid host can be read (then the summary)."""
    scheme, _, rest = value.partition('://')  # a backslash ends the authority, as a browser reads it
    end = next((i for i, char in enumerate(rest) if char in '/?#\\'), len(rest))
    authority, tail = rest[:end], rest[end:]
    userinfo = '@' in authority
    try:
        shown = canonical(f"{scheme}://{authority.rsplit('@', 1)[-1]}")
    except ValueError:
        return None
    before_fragment = tail.partition('#')[0]
    flags = [name for name, present in (
        ('userinfo', userinfo), ('path', before_fragment[:1] in ('/', '\\')),
        ('query', '?' in before_fragment), ('fragment', '#' in tail)) if present]
    return f"{shown}(has={'+'.join(flags)})" if flags else shown


def _redact_malformed(value: str) -> str:
    if _URL_SHAPE.fullmatch(value):
        shown = _summarize_url_shaped(value)
        if shown is not None:
            return shown
    return _summarize_malformed(value)


def _render(value: str) -> str:
    try:
        return canonical(value)
    except ValueError:
        return _redact_malformed(value)


def classify_denial(origins: list[str]) -> tuple[str, str]:
    """The Origin header values a request was refused or would be refused for -> (reason, the origin as shown): the
    shown value is printable ASCII without quotes or whitespace, at most MAX_RENDERED_ORIGIN characters."""
    if len(origins) > 1:
        shown = ','.join(_render(value) for value in origins[:4])
        return REASON_DUPLICATE, sanitize_origin_text(shown + (',...' if len(origins) > 4 else ''))
    value = origins[0] if origins else ''
    if value == 'null':
        return REASON_NULL, 'null'
    try:
        normalized = canonical(value)
    except ValueError:
        return REASON_MALFORMED, sanitize_origin_text(_redact_malformed(value))
    return REASON_NOT_ALLOWED, sanitize_origin_text(normalized)


# ---- the lines and their rate, per profile ----

class _Window:
    """One profile's lines (PaaS DenialLogLimiter, for one profile): the window's start and count, the lines held back,
    the (decision, reason, origin) written lately and whether a timer will write the count of the held ones."""

    def __init__(self):
        self.start = None
        self.count = self.suppressed = 0
        self.recent = {}
        self.timer = False

    def roll(self, now, interval, window):
        """A new window: the count of the lines the last one held back (0 while still in it), the old keys forgotten."""
        if self.start is not None and now - self.start < window:
            return 0
        held, self.suppressed = self.suppressed, 0
        self.start, self.count = now, 0
        self.prune(now, interval)
        return held

    def prune(self, now, interval):
        for key in [key for key, at in self.recent.items() if now - at >= interval]:
            del self.recent[key]
        while len(self.recent) >= LOG_MAX_KEYS:
            del self.recent[next(iter(self.recent))]  # the oldest first

    def admit(self, key, now, interval, per_window):
        last = self.recent.get(key)
        if (last is not None and now - last < interval) or self.count >= per_window:
            self.suppressed += 1
            return False
        if len(self.recent) >= LOG_MAX_KEYS:
            self.prune(now, interval)
        self.recent.pop(key, None)
        self.recent[key] = now
        self.count += 1
        return True


class Denials:
    """The add-on's decision lines (see the module docstring), one window per profile: a flood of one profile never
    holds back another's. record() never raises."""

    def __init__(self, *, clock=time.monotonic, interval=LOG_INTERVAL_SECONDS, window=LOG_WINDOW_SECONDS,
                 per_window=LOG_MAX_PER_WINDOW):
        self.clock, self.interval, self.window, self.per_window = clock, interval, window, per_window
        self.windows = OrderedDict()  # profile id -> _Window, the most recent last

    def record(self, profile_id, mode, origins):
        """One request's Origin the policy does not allow, for profile_id in mode: its line, unless held back. Only the
        Origin values and the profile reach the line; a failure writes nothing and never reaches the request."""
        try:
            reason, shown = classify_denial(origins)
            self._write(profile_id, mode, reason, shown)
        except Exception:  # a line never changes an answer (nor shows what failed: it may hold a header value)
            pass

    def _window(self, profile_id):
        window = self.windows.pop(profile_id, None) or _Window()
        self.windows[profile_id] = window
        while len(self.windows) > LOG_MAX_PROFILES:
            self.windows.popitem(last=False)
        return window

    def _write(self, profile_id, mode, reason, shown):
        name = profiles.log_id(profile_id)
        window = self._window(profile_id)
        now = self.clock()
        held = window.roll(now, self.interval, self.window)
        if held:
            self._held(name, held)
        decision = DECISION_WOULD_DENY if mode == MODE_REPORT_ONLY else DECISION_DENY
        if window.admit((decision, reason, shown), now, self.interval, self.per_window):
            effect = 'report-only: served as usual' if decision == DECISION_WOULD_DENY else 'enforce: refused, 403'
            logger.warning('MCP gateway [profile=%s]: an Origin the secret path does not allow (%s) decision=%s mode=%s '
                           'reason=%s origin="%s"', name, effect, decision, mode, reason, shown)
        else:
            self._schedule(name, window)

    def _held(self, name, count):
        logger.warning('MCP gateway [profile=%s]: Origin lines held back suppressed=%d (one line per origin every %g s, '
                       'at most %d lines every %g s per profile)', name, count, self.interval, self.per_window,
                       self.window)

    def _schedule(self, name, window):
        """At most one timer a window: the count of the lines held back once the window ends, unless the profile's
        next line writes it first. None without a running loop (the next line writes it)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if not window.suppressed or window.timer or window.start is None:
            return
        window.timer = True
        delay = max(0.0, self.window - (self.clock() - window.start)) + 0.01
        loop.call_later(delay, self._flush, name, window)

    def _flush(self, name, window):
        try:
            window.timer = False
            now = self.clock()
            if window.suppressed and window.start is not None and now - window.start >= self.window:
                held = window.roll(now, self.interval, self.window)
                if held:
                    self._held(name, held)
        except Exception:
            pass

    def size(self, profile_id):
        """The keys remembered for profile_id (tests: bounded)."""
        window = self.windows.get(profile_id)
        return 0 if window is None else len(window.recent)

    def profiles_held(self):
        return len(self.windows)


# ---- the policy and its file ----

@dataclass(frozen=True)
class Policy:
    """A mode and the origins it allows (each in its normal form, distinct, at most MAX_ORIGINS)."""
    mode: str
    allowed: tuple[str, ...]

    def permits(self, origins) -> bool:
        """Exactly one Origin, one the list holds once normalized."""
        if len(origins) != 1:
            return False
        try:
            return canonical(origins[0]) in self.allowed
        except ValueError:
            return False

    def document(self) -> bytes:
        return json.dumps({'version': POLICY_VERSION, 'mode': self.mode, 'allowed_origins': list(self.allowed)},
                          separators=(',', ':'), ensure_ascii=True).encode()

    def view(self, state):
        return {'mode': self.mode, 'allowed_origins': list(self.allowed), 'origin_policy_state': state}


DEFAULT_POLICY = Policy(MODE_REPORT_ONLY, DEFAULT_ALLOWED)


def request_shape(value) -> bool:
    """Step 5 of the shared pipeline (contract 3.2: no state read; a fixed 400 otherwise): exactly
    {"mode": <string>, "allowed_origins": [<string>, ...]}."""
    return (isinstance(value, dict) and set(value) == {'mode', 'allowed_origins'} and isinstance(value['mode'], str)
            and isinstance(value['allowed_origins'], list)
            and all(isinstance(item, str) for item in value['allowed_origins']))


def requested(value) -> Policy:
    """The policy a well-shaped request asks for (request_shape), or 422 origin_policy_invalid: a mode other than
    exactly report-only or enforce, more than MAX_ORIGINS origins, one that is not an exact http(s) origin (no *, null,
    path, trailing slash or dot, userinfo, query or whitespace; PaaS's rule), or two that are the same once
    normalized. Each is kept in its normal form, in the order given."""
    if value['mode'] not in MODES or len(value['allowed_origins']) > MAX_ORIGINS:
        raise BadRequest(422, {'code': INVALID})
    allowed = []
    for item in value['allowed_origins']:
        try:
            origin = canonical(item)
        except ValueError:
            raise BadRequest(422, {'code': INVALID}) from None
        if origin in allowed:
            raise BadRequest(422, {'code': INVALID})
        allowed.append(origin)
    return Policy(value['mode'], tuple(allowed))


def _parse(raw: bytes) -> Policy:
    """The file's policy: exactly {"version": 1, "mode": ..., "allowed_origins": [...]}, every origin in its normal form
    and distinct; ValueError for anything else."""
    value = strict_json(raw)
    if (not isinstance(value, dict) or set(value) != {'version', 'mode', 'allowed_origins'}
            or type(value['version']) is not int or value['version'] != POLICY_VERSION
            or value['mode'] not in MODES or not isinstance(value['allowed_origins'], list)
            or len(value['allowed_origins']) > MAX_ORIGINS
            or len(set(value['allowed_origins'])) != len(value['allowed_origins'])):
        raise ValueError('not an origin policy')
    for item in value['allowed_origins']:
        if not isinstance(item, str) or canonical(item) != item:
            raise ValueError('not an origin policy')
    return Policy(value['mode'], tuple(value['allowed_origins']))


@dataclass(frozen=True)
class Signature:
    """What the add-on remembers of the file it read or wrote last (as profiles.IndexSignature, with the mode)."""
    st_dev: int
    st_ino: int
    st_mode: int
    st_nlink: int
    st_size: int
    st_mtime_ns: int
    st_ctime_ns: int

    @classmethod
    def of(cls, info):
        return cls(info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns,
                   info.st_ctime_ns)


@dataclass(frozen=True)
class Found:
    """The file as read: its state (default: no file; saved; unusable), its policy (None when unusable), its raw bytes
    (at most MAX_POLICY_BYTES + 1; the unusable file's ETag) and its signature (None: no file)."""
    state: str
    policy: Policy | None
    raw: bytes
    signature: Signature | None


def _lstat_signature(path):
    """The entry's signature (not following a link); None when there is none."""
    try:
        return Signature.of(os.lstat(path))
    except FileNotFoundError:
        return None


class PolicyFile:
    """/data/mcp/origin-policy.json: read when asked, again only when it is not the one read last (one lstat); written
    whole (a new 0600 file, fsync, rename, fsync of the directory). Reading never creates, writes or chmods anything."""

    def __init__(self, path):
        self.path = Path(path)
        self.found = None

    def read(self) -> Found:
        try:
            signature = _lstat_signature(self.path)
        except OSError:
            signature = False  # cannot be looked at: read again, which finds it unusable
        if self.found is not None and signature is not False and signature == self.found.signature:
            return self.found
        found = self._load()
        if found.state == STATE_UNUSABLE and not (self.found is not None and self.found.state == STATE_UNUSABLE
                                                  and self.found.signature == found.signature):
            logger.warning(UNUSABLE_WARNING)
        self.found = found
        return found

    def _load(self) -> Found:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except (FileNotFoundError, NotADirectoryError):
            return Found(STATE_DEFAULT, DEFAULT_POLICY, b'', None)
        except OSError:
            try:
                return Found(STATE_UNUSABLE, None, b'', _lstat_signature(self.path))
            except OSError:
                return Found(STATE_UNUSABLE, None, b'', None)
        try:
            info = os.fstat(fd)
            signature = Signature.of(info)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_POLICY_BYTES):
                return Found(STATE_UNUSABLE, None, b'', signature)
            chunks, size = [], 0
            while chunk := os.read(fd, MAX_POLICY_BYTES + 1 - size):
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_POLICY_BYTES:
                    break
            raw = b''.join(chunks)
            if size > MAX_POLICY_BYTES:
                return Found(STATE_UNUSABLE, None, raw, signature)
            try:
                return Found(STATE_SAVED, _parse(raw), raw, signature)
            except (ValueError, RecursionError):
                return Found(STATE_UNUSABLE, None, raw, signature)
        except OSError:
            return Found(STATE_UNUSABLE, None, b'', None)
        finally:
            os.close(fd)

    def write(self, policy: Policy, *, expected: Signature | None) -> Found:
        """Replace the file with policy while it is still the one read (expected: its signature). OSError when it is not,
        or when it cannot be written; the file in force is then what is on disk (read() reads it again)."""
        if _lstat_signature(self.path) != expected:
            raise OSError('origin policy changed')
        raw = policy.document()
        temporary = self.path.with_name('.' + self.path.name + '-' + secrets.token_hex(8))
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            os.fchmod(fd, 0o600)  # exactly 0600 whatever the umask: read() refuses any other mode
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            signature = Signature.of(os.fstat(fd))  # after the rename (it changes the ctime)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary)  # gone after the rename; left only by a failure
            except OSError:
                pass
        self.found = Found(STATE_SAVED, policy, raw, signature)
        return self.found


class OriginPolicy:
    """The add-on's one policy (see the module docstring): its file, its receipts, its lock, its lines and the key of
    its ETags. directory: the default profile's store directory (/data/mcp). Made by a switched-on product's
    ProfileManager only (never for Headscale); nothing is read before it is asked."""

    def __init__(self, directory):
        self.file = PolicyFile(Path(directory) / POLICY_NAME)
        self.journal = OperationJournal(self.file.path, results=RESULTS)
        self.lock = asyncio.Lock()  # every save, one at a time
        self.denials = Denials()
        self._key = secrets.token_bytes(32)

    def guard(self, profile_id):
        """profile_id's check (gateway.make_apps origin_policy): called with the request's Origin values once its token
        is checked."""
        return partial(self.check, profile_id)

    def check(self, profile_id, origins):
        """None: the request goes on. Unusable file: ConfigError (503 state unavailable). Not permitted: report-only
        writes a would_deny line and lets it go on; enforce writes a deny line and refuses it (403)."""
        found = self.file.read()
        if found.policy is None:
            raise ConfigError('origin policy unavailable')
        if not origins or found.policy.permits(origins):
            return
        self.denials.record(profile_id, found.policy.mode, origins)
        if found.policy.mode == MODE_ENFORCE:
            raise BadRequest(403)

    def etag(self, found: Found) -> str:
        """'"o1-<64 hex>"': an HMAC with this process's key of the policy (the same policy, saved or the default, the
        same ETag), or of an unusable file's signature and raw bytes (only a save over it takes that one)."""
        if found.policy is None:
            described = json.dumps(None if found.signature is None else astuple(found.signature)).encode()
            material = b'raw\0' + described + b'\0' + found.raw
        else:
            material = b'policy\0' + json.dumps([found.policy.mode, list(found.policy.allowed)],
                                                separators=(',', ':'), ensure_ascii=True).encode()
        return '"o1-' + hmac.new(self._key, material, hashlib.sha256).hexdigest() + '"'

    @staticmethod
    def view(found: Found):
        """What the panel is shown: the mode, the origins and the state; an unusable file has neither."""
        if found.policy is None:
            return {'mode': None, 'allowed_origins': None, 'origin_policy_state': STATE_UNUSABLE}
        return found.policy.view(found.state)


def applies(app_options) -> bool:
    """Whether a switched-on product's secret path takes the add-on's policy: every product but one with its own fixed
    rule (Headscale: run_product's secret_path_allowed_origins)."""
    return app_options.get('secret_path_allowed_origins') is None
