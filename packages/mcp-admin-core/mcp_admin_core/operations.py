"""Bounded private receipts, owned by Store's writer lock and the admin lock.

Persist intent before the effect. A crash leaves an unknown outcome, never an
instruction to repeat. No token, user id, backend value or raw error is stored.
The journal must travel with the data directory in backups; restoring older data
cannot preserve receipts for operations performed after that backup.

HM-13b (multi-profile plan 4.1, 8.4 C; contract 3.5, 4.1, 9 #67; FM-07): the boot
guard archives a restored journal (archive_for_restore): it becomes
<journal>.restored (one archive kept) and a new journal refuses every operation id
from before the restore with 410 operation_restored (restored_before_ms), the ids
of operations made after that backup and lost with it included.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

from .admin_auth import BadRequest
from .config import strict_json

TTL_MS = 24 * 60 * 60 * 1000
MAX_RECEIPTS = 128
MAX_BYTES = 262144
ID_PATTERN = re.compile(r"[0-9]{13}\.[A-Za-z0-9_-]{16,64}\Z")
KINDS = {'token/rotate': 'token.rotate', 'token/revoke': 'token.revoke', 'child/restart': 'mcp.restart'}
RESULTS = {
    'token.rotate': {'status': 'ok', 'token_state': 'active'},
    'token.revoke': {'status': 'ok', 'token_state': 'revoked'},
    'mcp.restart': {'status': 'ok', 'child_state': 'accepted', 'apply_state': 'pending'},
}
# HM-10 (multi-profile plan 4.1, 5.3 point 7; contract 3.5): the receipts of creating and deleting a profile and of the
# profile index quarantine, kept beside the index (/data/mcp/.profiles.json.operations.json: OperationJournal(index
# path, results=PROFILE_RESULTS, subjects=True); profile_admin). Each carries its subject: the profile's id, or the
# name the quarantined index was given; neither is a secret. A profile's own journal (RESULTS, no subject) is as before.
PROFILE_RESULTS = {
    'profile.create': {'status': 'ok', 'profile_state': 'created'},
    'profile.delete': {'status': 'ok', 'profile_state': 'deleted'},
    'profile.index_quarantine': {'status': 'ok', 'profile_index_state': 'quarantined'},
}
SUBJECT = re.compile(r'[0-9a-f]{24}|profiles\.json\.quarantine-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?')
# HM-13b: a journal the boot guard wrote after a restore has one more key: every operation id at or before it (ms) was
# made before the restore and answers 410 operation_restored. Only journals the guard writes carry it (an image before
# HM-13b never reads one: a restore brings back its own image with the backup's data).
KEYS = frozenset({'version', 'key', 'expired_before_ms', 'receipts'})
RESTORED_KEY = 'restored_before_ms'
RESTORED_SUFFIX = '.restored'  # the archived journal of a restore (<journal>.restored; one kept per journal)


def fail(status, code):
    raise BadRequest(status, {'code': code})


class OperationJournal:
    def __init__(self, config_path: Path, *, results=RESULTS, subjects=False):
        self.path = config_path.with_name('.' + config_path.name + '.operations.json')
        self.results = results  # the kinds this journal keeps (HM-10: PROFILE_RESULTS beside the index)
        self.subjects = subjects  # HM-10: every receipt names its subject (SUBJECT)
        self._fields = {'kind', 'state', 'fingerprint', 'actor', *(('subject',) if subjects else ())}
        self._seen = self.path.exists()
        self._poisoned = False

    def _read(self):
        if self._poisoned:
            raise ValueError('Operation journal requires recovery')
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if self._seen:
                raise ValueError('Operation journal disappeared') from None
            return {'version': 1, 'key': secrets.token_hex(32), 'expired_before_ms': 0, 'receipts': {}}
        self._seen = True
        try:
            info = os.fstat(fd)
            visible = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                    or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)
                    or info.st_size > MAX_BYTES):
                raise ValueError('Unsafe operation journal')
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = strict_json(stream.read(MAX_BYTES + 1))
            if (not isinstance(data, dict) or set(data) not in (KEYS, KEYS | {RESTORED_KEY})
                    or RESTORED_KEY in data and (type(data[RESTORED_KEY]) is not int or data[RESTORED_KEY] < 0)
                    or type(data['version']) is not int or data['version'] != 1
                    or not isinstance(data['key'], str) or not re.fullmatch(r'[0-9a-f]{64}', data['key'])
                    or type(data['expired_before_ms']) is not int or data['expired_before_ms'] < 0
                    or not isinstance(data['receipts'], dict) or len(data['receipts']) > MAX_RECEIPTS):
                raise ValueError('Invalid operation journal')
            for key, item in data['receipts'].items():
                if (not ID_PATTERN.fullmatch(key) or not isinstance(item, dict)
                        or set(item) != self._fields
                        or item['kind'] not in self.results or item['state'] not in {'pending', 'completed'}
                        or any(not isinstance(item[field], str) or not re.fullmatch(r'[0-9a-f]{64}', item[field])
                               for field in ('fingerprint', 'actor'))
                        or self.subjects and (not isinstance(item['subject'], str)
                                              or not SUBJECT.fullmatch(item['subject']))):
                    raise ValueError('Invalid operation receipt')
            return data
        finally:
            os.close(fd)

    def _write(self, data):
        raw = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError('Operation journal capacity exceeded')
        tmp = self.path.with_name(self.path.name + '.tmp.' + secrets.token_hex(8))
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
            self._seen = True
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, ValueError):
            # Even failure after rename/fsync is ambiguous. This process must not
            # accept another effect until reopened and durable bytes re-read.
            self._poisoned = True
            raise
        finally:
            tmp.unlink(missing_ok=True)

    def _load(self, operation_id):
        now = int(time.time() * 1000)
        if not isinstance(operation_id, str) or not ID_PATTERN.fullmatch(operation_id):
            fail(400, 'operation_id_invalid')
        timestamp = int(operation_id.split('.', 1)[0])
        if timestamp > now:
            fail(400, 'operation_id_invalid')
        try:
            data = self._read()
        except (OSError, ValueError, KeyError, TypeError):
            fail(503, 'operation_journal_unavailable')
        if RESTORED_KEY in data and timestamp <= data[RESTORED_KEY]:
            fail(410, 'operation_restored')  # HM-13b: made before a restore (its receipt is in the archive, or lost)
        floor = max(data['expired_before_ms'], now - TTL_MS)
        if timestamp <= floor:
            fail(410, 'operation_id_expired')
        data['expired_before_ms'] = floor
        data['receipts'] = {key: item for key, item in data['receipts'].items() if int(key.split('.', 1)[0]) > floor}
        return data

    @staticmethod
    def _digest(data, value):
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
        return hmac.new(bytes.fromhex(data['key']), raw, hashlib.sha256).hexdigest()

    @staticmethod
    def public(operation_id, item, *, replayed=False):
        return {'id': operation_id, 'kind': item['kind'],
                'state': 'completed' if item['state'] == 'completed' else 'unknown', 'replayed': replayed}

    def _owned(self, data, operation_id, actor):
        item = data['receipts'].get(operation_id)
        if item and not hmac.compare_digest(item['actor'], self._digest(data, ['actor', actor])):
            fail(404, 'operation_not_found')
        return item

    def inspect(self, operation_id, kind, actor, payload=None):
        data = self._load(operation_id)
        item = self._owned(data, operation_id, actor)
        fingerprint = self._digest(data, ['request', kind, payload])
        if item and not hmac.compare_digest(item['fingerprint'], fingerprint):
            fail(409, 'operation_id_conflict')
        return data, item, fingerprint

    def begin(self, operation_id, data, kind, actor, fingerprint, subject=None):
        if kind not in self.results or (subject is not None) != self.subjects or (
                subject is not None and not SUBJECT.fullmatch(subject)):
            raise ValueError('Unsupported operation')
        if len(data['receipts']) >= MAX_RECEIPTS:
            fail(503, 'operation_journal_full')
        data['receipts'][operation_id] = {'kind': kind, 'state': 'pending', 'fingerprint': fingerprint,
                                        'actor': self._digest(data, ['actor', actor]),
                                        **({'subject': subject} if self.subjects else {})}
        try:
            self._write(data)
        except (OSError, ValueError):
            fail(503, 'operation_journal_unavailable')

    def complete(self, operation_id, data):
        item = data['receipts'][operation_id]
        item['state'] = 'completed'
        self._write(data)
        return self.public(operation_id, item)

    def query(self, operation_id, actor):
        data = self._load(operation_id)
        item = self._owned(data, operation_id, actor)
        if not item:
            fail(404, 'operation_not_found')
        return {'operation': self.public(operation_id, item),
                'result': dict(self.results[item['kind']]) if item['state'] == 'completed' else {}}


def journal_path(config_path: Path) -> Path:
    """The journal of a state file (or of the index): .<name>.operations.json beside it."""
    config_path = Path(config_path)
    return config_path.with_name('.' + config_path.name + '.operations.json')


def archive_for_restore(config_path: Path, cutoff_ms: int) -> str:
    """HM-13b: the receipts of a restored profile (config_path: its state.json; or the index, for the receipts beside
    it). The journal the restore brought back becomes <journal>.restored (the one archive kept: it replaces an older
    one) and a new, empty journal refuses every operation id at or before cutoff_ms (the restore's time) with 410
    operation_restored. The new journal is written first (a temporary, fsynced), then the old one moved, then the new one
    put in place and the directory fsynced: a full disk leaves the journal as it was. The cutoff is never below the
    restored journal's newest operation id or floor (a host clock behind the backup's), but at most TTL_MS ahead of
    cutoff_ms (a forged far-future id). Idempotent, for a guard stopped
    half way and run again: a journal without receipts (the one this wrote, or one emptied) is not archived again, so
    the archive keeps the receipts it holds; only its cutoff moves forward. A missing journal next to an archive
    (stopped between the two moves) gets its new one, its cutoff not below the archive's newest id either; with
    neither, nothing is written (no operation was ever made). A journal that cannot be read is archived as it is.
    Returns 'archived', 'renewed' or 'none'; OSError when it was not done (the next start does it again)."""
    if type(cutoff_ms) is not int or cutoff_ms < 0:
        raise ValueError('invalid cutoff')
    path = journal_path(config_path)
    archive = path.with_name(path.name + RESTORED_SUFFIX)
    found = _receipts(path)
    if found is None:
        if not os.path.lexists(archive):
            return 'none'
        # Stopped between the two moves: the archive holds the restored receipts, so its floor counts as theirs did.
        found = 0, (_receipts(archive) or (0, None))[1]
    count, floor = found
    # As PaaS restore_guard (_read_journal_floor): never below the journal's own newest id or floor, whatever the clock;
    # but at most a retention period ahead of it, so that a forged far-future id cannot refuse every new id for years.
    cutoff_ms = max(cutoff_ms, min(floor or 0, cutoff_ms + TTL_MS))
    if count == 0:
        _new_journal(path, cutoff_ms, archive=None)
        return 'renewed'
    _new_journal(path, cutoff_ms, archive=archive)
    return 'archived'


def _receipts(path):
    """(receipt count, floor) of the journal at path, the floor being the newest of its expired_before_ms,
    restored_before_ms and receipt id times (None when there is none); (-1, None) for one that cannot be read as a
    journal (any kind of entry, unsafe or malformed); None when there is none."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        return -1, None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_size > MAX_BYTES):
            return -1, None
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = strict_json(stream.read(MAX_BYTES + 1))
    except (OSError, ValueError, RecursionError):
        return -1, None
    finally:
        os.close(fd)
    if not isinstance(data, dict) or not isinstance(data.get('receipts'), dict):
        return -1, None
    times = [value for value in (data.get('expired_before_ms'), data.get(RESTORED_KEY))
             if type(value) is int and value >= 0]
    times += [int(key.split('.', 1)[0]) for key in data['receipts'] if isinstance(key, str) and ID_PATTERN.fullmatch(key)]
    return len(data['receipts']), max(times) if times else None


def _new_journal(path, cutoff_ms, *, archive):
    data = {'version': 1, 'key': secrets.token_hex(32), 'expired_before_ms': 0, 'receipts': {},
            RESTORED_KEY: cutoff_ms}
    raw = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
    temporary = path.with_name(path.name + '.tmp.' + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        if archive is not None:
            os.replace(path, archive)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)  # gone after the move; left only by a failure
        except OSError:
            pass
