"""HM-01: every log record a test dispatches, scanned for synthetic secrets and account names (0 hits to pass).

Every new test uses it (multi-profile plan, rule 3 of the slice rules; invariant I7: no record shows a token, an
account name or a secret path):

    from log_scan import log_scan  # noqa: F401  (the fixture)

    async def test_something(log_scan, tmp_path):
        ...
        log_scan.watch_state(store.load())              # the token, the child token, every credential of a state
        log_scan.watch('Alpha Prod', kind='name')         # an account (profile) name

At teardown the fixture fails the test when any record showed a watched value. The report names the kind, the
logger, the level and the source line, never the value or the message.

What is seen: every LogRecord any logger dispatches while the test runs (Logger.handle is wrapped), whichever logger
filter, handler, handler filter, level or propagation setting applies after that; meanwhile the root logger is lowered
to DEBUG so that loggers without their own level create their records too. Each record is rendered at that moment:
message, arguments, exception text, stack and extra attributes. That is after the record factory ran
(mcp_admin_core.redact's first layer scrubs every record there) and before any handler filter could (its second
layer): every handler, logging.lastResort included, gets the record as it is then, so a value that only a later
handler filter would hide still counts. A token also counts when any TOKEN_WINDOW-character piece of it shows (a
truncated or partly redacted token is still a leak); names also count in any letter case.

Not an output scan: print() and child process output are not log records.
"""
from __future__ import annotations

import logging
import threading

import pytest

TOKEN_WINDOW = 16
MIN_SECRET = 8   # watch_state() skips shorter credentials; too common in ordinary text to scan
MIN_NAME = 4
KINDS = ('token', 'secret', 'name')
_STANDARD = frozenset(vars(logging.LogRecord('', logging.INFO, '', 0, '', (), None))) | {'message', 'asctime'}


def render(record: logging.LogRecord) -> str:
    """The text a handler could write for this record, plus any extra attribute."""
    parts = [record.name]
    try:
        parts.append(record.getMessage())
    except Exception:
        parts += [repr(record.msg), repr(record.args)]
    if record.exc_info and not record.exc_text:
        try:
            parts.append(logging.Formatter().formatException(record.exc_info))
        except Exception:
            parts.append(repr(record.exc_info[1]))
    if record.exc_text:
        parts.append(record.exc_text)
    if record.stack_info:
        parts.append(record.stack_info)
    for key, value in vars(record).items():
        if key not in _STANDARD:
            try:
                parts.append(f'{key}={value!r}')
            except Exception:
                parts.append(key + '=<unrepresentable>')
    return '\n'.join(str(part) for part in parts)


class LogScan:
    def __init__(self):
        self.records: list[logging.LogRecord] = []
        self.seen: list[tuple[str, str, str, str]] = []  # (logger, level, source, text) of each record as dispatched
        self._needles: list[tuple[str, str]] = []
        self._handle = None
        self._previous_handle = None
        self._previous_level = None
        self._active = False
        self._rendering = threading.local()

    # ---- what to look for ----

    def watch(self, *values, kind='token'):
        if kind not in KINDS:
            raise ValueError('unknown kind')
        for value in values:
            minimum = {'token': TOKEN_WINDOW, 'secret': 1, 'name': MIN_NAME}[kind]
            if not isinstance(value, str) or len(value) < minimum:
                raise ValueError(f'a watched {kind} must be a string of at least {minimum} characters')
            if (kind, value) not in self._needles:
                self._needles.append((kind, value))
        return self

    def watch_state(self, state):
        """The add-on token and child token, and every credential the state holds (redact.secret_values: backend keys,
        connection secrets and their Basic Authorization forms) of at least MIN_SECRET characters."""
        from mcp_admin_core import redact
        tokens = [value for value in (getattr(state, 'token', None), getattr(state, 'child_token', None)) if value]
        self.watch(*tokens, kind='token')
        self.watch(*(value for value in redact.secret_values(state)
                     if value not in tokens and len(value) >= MIN_SECRET), kind='secret')
        return self

    @property
    def watched(self):
        return tuple(self._needles)

    # ---- collection ----

    def take(self, record):
        """Keep the record and its text as dispatched now (Logger.handle calls this before anything else)."""
        if getattr(self._rendering, 'active', False):
            return  # a record logged while rendering one (a __repr__ that logs) is not scanned twice
        self._rendering.active = True
        try:
            self.records.append(record)
            self.seen.append((record.name, record.levelname, f'{record.pathname}:{record.lineno}', render(record)))
        finally:
            self._rendering.active = False

    def start(self):
        if self._active:
            raise RuntimeError('log scan already started')
        previous = self._previous_handle = logging.Logger.handle
        scan = self

        def handle(logger, record):
            if scan._active:
                scan.take(record)
            return previous(logger, record)

        self._handle = handle
        logging.Logger.handle = handle
        root = logging.getLogger()
        self._previous_level = root.level
        root.setLevel(logging.DEBUG)
        self._active = True
        return self

    def stop(self):
        if not self._active:
            return
        self._active = False
        logging.getLogger().setLevel(self._previous_level)
        if logging.Logger.handle is self._handle:
            logging.Logger.handle = self._previous_handle
        # Otherwise another scan started meanwhile wraps this one: keep the chain intact, this layer now only passes
        # records through.

    # ---- verdict ----

    def _matches(self, text):
        folded = text.casefold()
        for kind, value in self._needles:
            if kind == 'name':
                found = value in text or value.casefold() in folded
            elif kind == 'token':
                found = any(value[i:i + TOKEN_WINDOW] in text for i in range(len(value) - TOKEN_WINDOW + 1))
            else:
                found = value in text
            if found:
                yield kind

    def hits(self):
        """(kind, logger, level, source) of every record that showed a watched value; never the value or message."""
        return [(kind, name, level, source) for name, level, source, text in list(self.seen)
                for kind in self._matches(text)]

    def assert_clean(self):
        hits = self.hits()
        if hits:
            pytest.fail(f'log scan: {len(hits)} watched value(s) in log records ({len(self.seen)} scanned): '
                        + '; '.join(f'{kind} in logger {name!r} {level} at {source}'
                                    for kind, name, level, source in hits), pytrace=False)


@pytest.fixture
def log_scan():
    scan = LogScan().start()
    try:
        yield scan
    finally:
        scan.stop()
    scan.assert_clean()
