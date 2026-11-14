"""Restore detection (multi-profile HM-13a): the entrypoint's restore marker and the instance sentinel.

Supervisor restores an app by deleting its data and copying the backup's copy back (copytree, links kept, no chown,
no hook) and starts the app again when it ran at backup time. Either signal means /data/mcp came back from a backup:

1. MARKER: packaging/entrypoint.py found /data/mcp root-owned (the restore owner) and saved this marker before it
   repaired the ownership. Every product's entrypoint does, whatever the product's multi-profile switch.
2. SENTINEL: an empty file, created once, whose (st_ino, st_ctime_ns) RECORD keeps. A file-level restore always makes
   a new file and its ctime is the time of the restore; no ordinary call sets a ctime back, and the inode number alone
   is not enough (ext4 hands a freed number out again at once). st_dev is not compared: a host that numbers its disks
   differently (one more USB disk at boot) must not read as restored.

The sentinel and its record are looked at, created or replaced only while the product's switch is on or profile data
(PROFILE_DATA) is on disk. Otherwise detect() looks up three names in the directory (MARKER, PROFILE_DATA), opens no
file in it and writes nothing: a product that is not enabled gets no new file. Neither file holds a secret.

This module only detects. The boot gate (HM-13b) acts on a restore, then calls rebuild() and removes the marker last;
detect() writes nothing while a restore is detected, so a gate stopped half way is detected again at the next start.
Once created, nothing but the entrypoint's restore repair may chmod, chown, write, link or rename the sentinel: each
changes its ctime (a rename does on ext4) and reads as a restore. One caller at a time: the management process, as it
starts.
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .config import ConfigError, strict_json

MARKER = '.restore-detected'  # written by packaging/entrypoint.py, which keeps the same name
SENTINEL = '.instance-sentinel'
RECORD = '.instance-record'
TEMPORARY = '.instance-record.tmp'  # the next record before it replaces RECORD; a leftover is removed first
PROFILE_DATA = ('profiles.json', 'profiles')  # the profile index and the extra profiles' directory (entrypoint too)
RECORD_LIMIT = 4096
RECORD_KEYS = frozenset({'version', 'st_ino', 'st_ctime_ns'})

# Detection.sentinel when no restore is seen
INACTIVE = 'inactive'        # switch off and no profile data: neither file looked at
ESTABLISHED = 'established'  # neither file and no profile data (the first start with the switch on): both made
REBUILT = 'rebuilt'          # a sentinel without its record and no profile data (that first start stopped): both made
CONSISTENT = 'consistent'    # the sentinel is the file the record names
# ... and when it sees a restore
MISMATCH = 'mismatch'                  # another file than the recorded one
SENTINEL_MISSING = 'sentinel_missing'  # a record without its sentinel
SENTINEL_INVALID = 'sentinel_invalid'  # not a regular file, or no answer about it
RECORD_MISSING = 'record_missing'      # profile data without a record
RECORD_INVALID = 'record_invalid'      # an unreadable, unsafe or malformed record
RESTORED = frozenset({MISMATCH, SENTINEL_MISSING, SENTINEL_INVALID, RECORD_MISSING, RECORD_INVALID})
_NEW, _UNRECORDED = 'new', 'unrecorded'  # internal: created by detect() as ESTABLISHED and REBUILT


@dataclass(frozen=True)
class Detection:
    marker: bool   # signal 1, whatever the switch
    active: bool   # the switch is on or profile data is on disk: the sentinel was looked at
    sentinel: str  # signal 2: one of the verdicts above

    @property
    def restored(self) -> bool:
        return self.marker or self.sentinel in RESTORED


def detect(directory: Path, *, enabled: bool) -> Detection:
    """Both signals for the data directory (normally /data/mcp). enabled: the product's multi-profile switch as the
    caller reads it at this call (HM-07 features.enabled).

    The first start with the switch on (and the one after it, when that stopped between the two files) makes the
    sentinel and its record; nothing else is written. ConfigError: the directory cannot be opened, or a sentinel
    cannot be made.
    """
    fd = _open_directory(directory)
    try:
        marker = _present(fd, MARKER)
        profile_data = any(_present(fd, name) for name in PROFILE_DATA)
        if not (enabled or profile_data):
            return Detection(marker, False, INACTIVE)
        verdict = _inspect(fd, profile_data)
        if verdict in (_NEW, _UNRECORDED):
            _rebuild(fd)
            verdict = ESTABLISHED if verdict == _NEW else REBUILT
        return Detection(marker, True, verdict)
    finally:
        os.close(fd)


def rebuild(directory: Path) -> None:
    """A new sentinel and its record, for an active product (the boot gate's last step before the marker goes).

    The old sentinel goes first, the new record last, each step durable: a stop before the new record is in place
    reads as a restore (a record naming another file, or no sentinel). ConfigError when it could not be done.
    """
    fd = _open_directory(directory)
    try:
        _rebuild(fd)
    finally:
        os.close(fd)


def _open_directory(directory):
    try:
        return os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise ConfigError('state directory unavailable') from None


def _present(fd, name):
    """Any kind of entry counts, and so does one a lookup cannot rule out (fails closed, as PaaS restore_marker)."""
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _inspect(fd, profile_data):
    try:
        sentinel = os.stat(SENTINEL, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        sentinel = None
    except OSError:
        return SENTINEL_INVALID
    if sentinel is not None and not stat.S_ISREG(sentinel.st_mode):
        return SENTINEL_INVALID  # never something an interrupted creation leaves
    record = _read_record(fd)
    if record is None:
        if profile_data:
            return RECORD_MISSING
        return _NEW if sentinel is None else _UNRECORDED
    if record == RECORD_INVALID:
        return RECORD_INVALID
    if sentinel is None:
        return SENTINEL_MISSING
    return CONSISTENT if (sentinel.st_ino, sentinel.st_ctime_ns) == record else MISMATCH


def _read_record(fd):
    """(st_ino, st_ctime_ns), None when there is no record, or RECORD_INVALID."""
    try:
        record = os.open(RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    except OSError:
        return RECORD_INVALID
    try:
        info = os.fstat(record)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_size > RECORD_LIMIT):
            return RECORD_INVALID
        with os.fdopen(record, 'rb', closefd=False) as stream:
            raw = stream.read(RECORD_LIMIT + 1)
        if len(raw) > RECORD_LIMIT:
            return RECORD_INVALID
        value = strict_json(raw)
    except (OSError, ValueError, RecursionError):
        return RECORD_INVALID
    finally:
        os.close(record)
    if (not isinstance(value, dict) or set(value) != RECORD_KEYS or type(value['version']) is not int
            or value['version'] != 1
            or any(type(value[key]) is not int or value[key] < 0 for key in ('st_ino', 'st_ctime_ns'))):
        return RECORD_INVALID
    return value['st_ino'], value['st_ctime_ns']


def _rebuild(fd):
    try:
        with suppress(FileNotFoundError):
            os.unlink(SENTINEL, dir_fd=fd)
        sentinel = os.open(SENTINEL, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            os.fsync(sentinel)
            info = os.fstat(sentinel)
        finally:
            os.close(sentinel)
        os.fsync(fd)  # the new sentinel is on disk before a record names it
        _write_record(fd, info.st_ino, info.st_ctime_ns)
    except OSError:
        raise ConfigError('restore sentinel not durably saved') from None
    if _inspect(fd, True) != CONSISTENT:
        raise ConfigError('restore sentinel not durably saved')


def _write_record(fd, ino, ctime_ns):
    raw = json.dumps({'version': 1, 'st_ino': ino, 'st_ctime_ns': ctime_ns}, sort_keys=True,
                     separators=(',', ':')).encode()
    with suppress(FileNotFoundError):
        os.unlink(TEMPORARY, dir_fd=fd)
    temporary = os.open(TEMPORARY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(temporary, view):]
            os.fsync(temporary)
        finally:
            os.close(temporary)
        os.replace(TEMPORARY, RECORD, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    except OSError:
        with suppress(OSError):
            os.unlink(TEMPORARY, dir_fd=fd)
        raise
