"""Single-writer, GUI-owned state. No deployment options or executable settings.

New implementation informed by the legacy same-directory atomic replace primitive;
see docs/provenance/n8n-tracer.md. No permissive recovery from missing/corrupt state.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigError(RuntimeError):
    pass


# Owner decision 2026-10-15: a new installation (products.ProductStore) starts with every reviewed write enabled (the
# legacy global switch and every exact write grant). The administrator can still turn each one off in the panel; that
# saved choice is kept across restarts and upgrades because an existing state is never re-seeded.
FRESH_WRITES_ENABLED = True


def http_url(value: str) -> str:
    if len(value) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise ValueError("invalid URL")
    parts = urlsplit(value)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or any(c.isspace() for c in value)
            or "\\" in value):
        raise ValueError("expected explicit HTTP URL without credentials/query/fragment")
    _ = parts.port
    return value.rstrip("/")


class State(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: int = 1
    token: str | None = Field(repr=False)
    child_token: str = Field(repr=False)
    backend_url: str | None = None
    backend_key: str | None = Field(default=None, repr=False)
    endpoint: str | None = None
    # The model default is not the fresh-install default: a stored state must carry every key (Store._decode), and a
    # new product state gets ProductStore._initial_state, which turns writes on (owner decision 2026-10-15).
    writes_enabled: bool = False
    disabled: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def version(cls, value):
        if value != 1:
            raise ValueError("unsupported schema; restore compatible backup, do not downgrade state")
        return value

    @field_validator("token", "child_token")
    @classmethod
    def tokens(cls, value, info):
        if value is None and info.field_name == "token":
            return value
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise ValueError("invalid token")
        return value

    @field_validator("backend_url", "endpoint")
    @classmethod
    def urls(cls, value, info):
        if value is None:
            return value
        value = http_url(value)
        if info.field_name == "endpoint" and not value.endswith("/mcp"):
            raise ValueError("endpoint must end in /mcp")
        return value

    @field_validator("backend_key")
    @classmethod
    def key(cls, value):
        if value is not None and (not value or len(value) > 8192 or any(not 32 <= ord(c) <= 126 for c in value)):
            raise ValueError("invalid credential")
        return value

    @field_validator("disabled")
    @classmethod
    def names(cls, value):
        if len(value) > 256 or len(set(value)) != len(value) or any(not re.fullmatch(r"[a-zA-Z0-9_]{1,128}", v) for v in value):
            raise ValueError("invalid disabled tools")
        return value


# HM-30 review 2 MF-1: with a checkpoint, strict_json also calls it once every NUMBERS_A_CHECKPOINT numbers it parses.
NUMBERS_A_CHECKPOINT = 1024


def strict_json(raw: bytes, *, checkpoint=None):
    """HM-30: checkpoint, when given, is called once for every JSON object the parser builds, before it builds it
    (reply_worker.breathe: the reply worker lets the event loop have the GIL there); the value and every error stay the
    same. Left out, as before.

    HM-30 review 2 MF-1: with a checkpoint, it is also called once every NUMBERS_A_CHECKPOINT numbers: json's C scanner
    builds a flat array of numbers (record ids, a time series) in one call otherwise, with no object to stop at, and it
    calls parse_int and parse_float for each number (int itself gives the same value and raises the same ValueError past
    the digits limit). A flat array of strings, true, false, null or empty arrays has no such hook: still one call."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def checked(items):
        checkpoint()
        return pairs(items)

    def constant(_):
        raise ValueError("nonfinite number")

    def number(text):
        value = float(text)
        if value in (float("inf"), float("-inf")):
            raise ValueError("nonfinite number")  # e.g. 1e400 would re-serialize as Infinity
        return value

    if checkpoint is None:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    count = 0

    def counted_float(text):
        nonlocal count
        count += 1
        if count >= NUMBERS_A_CHECKPOINT:
            count = 0
            checkpoint()
        return number(text)

    def counted_int(text):
        nonlocal count
        count += 1
        if count >= NUMBERS_A_CHECKPOINT:
            count = 0
            checkpoint()
        return int(text)

    return json.loads(raw, object_pairs_hook=checked, parse_constant=constant, parse_float=counted_float,
                      parse_int=counted_int)


class Store:
    """One process owns the lock until close. State is reread/validated per request.

    Dedicated 0700 subdirectory (normally /data/mcp) is owned by the runtime user.
    No migration exists before v1; missing keys are rejected, not silently seeded.

    An additional profile's store (multi-profile plan §4.3; HM-07, nothing opens one yet) never takes the first-boot
    path that seeds a fresh state. existing_only=True opens an existing directory only: no directory is made, the lock
    is opened without O_CREAT, a missing state is an error. create=<state> makes a new one: the directory must not
    exist yet (not even as a dangling link), the lock is created with O_EXCL, *state* is written once as the final
    first value, and a failure removes what this creation made. Both refuse a directory, lock or state file another
    uid owns, checked before any chmod, and tighten a widened mode to 0700 / 0600. A creation fsyncs the parent
    directory, so the new directory's name is on disk before an index can list it. Reading an additional profile's
    0600 state changes nothing (no fchmod, its ctime stays; only a widened mode is tightened). The default profile's
    store keeps its behavior.
    """
    _owned = False  # True for an additional profile's store

    def __init__(self, directory: Path, *, existing_only: bool = False, create: State | None = None):
        if existing_only and create is not None:
            raise ValueError("existing_only and create exclude each other")
        self._lock_fd = None
        self._poisoned = False
        self._owned = existing_only or create is not None
        self.directory = Path(os.path.abspath(directory))
        self.path = self.directory / "state.json"
        made = None  # creation only: False once the directory exists, then its (st_dev, st_ino)
        try:
            for parent in [*reversed(self.directory.parents), self.directory]:
                if parent.is_symlink():
                    raise ConfigError("symlink state directory refused")
            if create is not None:
                os.mkdir(self.directory, 0o700)  # FileExistsError for any existing name
                made = False
                made = self._owned_directory()
                self._sync_parent()
                self._lock_fd = os.open(self.directory / ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                self._owned_lock()
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._write(self._decode(strict_json(create.model_dump_json())))
            elif existing_only:
                self._owned_directory()
                self._lock_fd = os.open(self.directory / ".writer.lock", os.O_RDWR | os.O_NOFOLLOW)
                self._owned_lock()
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(self.directory, 0o700)
                try:
                    self._lock_fd = os.open(self.directory / ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    first_boot = True
                except FileExistsError:
                    self._lock_fd = os.open(self.directory / ".writer.lock", os.O_RDWR | os.O_NOFOLLOW)
                    first_boot = False
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if first_boot and not self.path.exists() and not self.path.is_symlink():
                    self._write(self._initial_state())
            self.load()
        except Exception:
            self.close()
            if made is not None:
                self._discard_created(made)
            raise ConfigError("state unavailable or incompatible; manual recovery required") from None

    def _owned_directory(self):
        """An additional profile's directory: a real directory (not a link) of this uid; a widened mode becomes 0700.
        Returns its (st_dev, st_ino)."""
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            current = os.lstat(self.directory)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
                raise ConfigError("state directory refused")
            if stat.S_IMODE(info.st_mode) != 0o700:
                os.fchmod(fd, 0o700)
            return info.st_dev, info.st_ino
        finally:
            os.close(fd)

    def _sync_parent(self):
        """Make a new directory's name durable in its parent (profiles/), before anything can list the profile."""
        fd = os.open(self.directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _owned_lock(self):
        """An additional profile's writer lock: a single-link regular file of this uid; a widened mode becomes 0600."""
        info = os.fstat(self._lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise ConfigError("writer lock refused")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.fchmod(self._lock_fd, 0o600)

    def _discard_created(self, made):
        """Undo a failed creation: the two files it makes, through the descriptor of the directory it made (never
        through a name swapped in since), then the directory. Anything else in it stays, and with it the directory:
        profile data the index does not list is an orphan, never opened or routed. *made*: False when the directory's
        identity was not established yet (nothing was created in it)."""
        if made:
            try:
                fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except OSError:
                return
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != made:
                    return
                for name in ("state.json", ".writer.lock"):
                    try:
                        os.unlink(name, dir_fd=fd)
                    except OSError:
                        pass
            finally:
                os.close(fd)
        try:
            os.rmdir(self.directory)
        except OSError:
            pass

    def close(self):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def load(self) -> State:
        if self._lock_fd is None or self._poisoned:
            raise ConfigError("state unavailable")
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536
                        or (self._owned and info.st_uid != os.geteuid())):
                    raise ValueError("invalid state file")
                if not self._owned or stat.S_IMODE(info.st_mode) != 0o600:
                    os.fchmod(stream.fileno(), 0o600)
                value = strict_json(stream.read(65537))
            return self._decode(value)
        except (OSError, ValueError, RecursionError):
            raise ConfigError("state unavailable or incompatible; manual recovery required") from None

    def _initial_state(self):
        # The v1 (pre-product) state: production always runs ProductStore, whose _initial_state applies
        # FRESH_WRITES_ENABLED; a plain v1 Store is only a migration source and test fixture, so it keeps writes off.
        return State(token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))

    def _decode(self, value):
        if not isinstance(value, dict) or set(value) != set(State.model_fields):
            raise ValueError("incomplete schema")
        return State.model_validate(value)

    def update(self, **changes) -> State:
        try:
            updated = self._decode({**self.load().model_dump(), **changes})
        except ValueError:
            raise ConfigError("invalid state update") from None
        self._write(updated)
        return updated

    def _write(self, value: State, *, poison_before_replace: bool = True):
        """Replace the state file with value durably: a new file written and synced, renamed over it, the directory
        synced. A failure poisons the store (no read or write until a restart: its outcome is unknown) and raises.

        poison_before_replace=False (HM-12: ProductStore.rebind, a switched-on backend identity change): a failure
        before the rename (the new file could not be made, written or synced) leaves the store usable, since the state
        file is then certainly the one before; from the rename on, every failure still poisons it."""
        temporary = self.directory / (".state-" + secrets.token_hex(16))
        replacing = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(value.model_dump_json())
                stream.flush()
                os.fsync(stream.fileno())
            replacing = True
            os.replace(temporary, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            if replacing or poison_before_replace:
                self._poisoned = True
            raise ConfigError("durable state write failed; manual recovery required") from None
        finally:
            temporary.unlink(missing_ok=True)
