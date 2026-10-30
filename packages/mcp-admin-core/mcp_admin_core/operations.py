"""Bounded private receipts, owned by Store's writer lock and the admin lock.

Persist intent before the effect. A crash leaves an unknown outcome, never an
instruction to repeat. No token, user id, backend value or raw error is stored.
The journal must travel with the data directory in backups; restoring older data
cannot preserve receipts for operations performed after that backup.
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


def fail(status, code):
    raise BadRequest(status, {'code': code})


class OperationJournal:
    def __init__(self, config_path: Path):
        self.path = config_path.with_name('.' + config_path.name + '.operations.json')
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
            if (not isinstance(data, dict) or set(data) != {'version', 'key', 'expired_before_ms', 'receipts'}
                    or type(data['version']) is not int or data['version'] != 1
                    or not isinstance(data['key'], str) or not re.fullmatch(r'[0-9a-f]{64}', data['key'])
                    or type(data['expired_before_ms']) is not int or data['expired_before_ms'] < 0
                    or not isinstance(data['receipts'], dict) or len(data['receipts']) > MAX_RECEIPTS):
                raise ValueError('Invalid operation journal')
            for key, item in data['receipts'].items():
                if (not ID_PATTERN.fullmatch(key) or not isinstance(item, dict)
                        or set(item) != {'kind', 'state', 'fingerprint', 'actor'}
                        or item['kind'] not in RESULTS or item['state'] not in {'pending', 'completed'}
                        or any(not isinstance(item[field], str) or not re.fullmatch(r'[0-9a-f]{64}', item[field])
                               for field in ('fingerprint', 'actor'))):
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

    def begin(self, operation_id, data, kind, actor, fingerprint):
        if kind not in RESULTS:
            raise ValueError('Unsupported operation')
        if len(data['receipts']) >= MAX_RECEIPTS:
            fail(503, 'operation_journal_full')
        data['receipts'][operation_id] = {'kind': kind, 'state': 'pending', 'fingerprint': fingerprint,
                                        'actor': self._digest(data, ['actor', actor])}
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
                'result': dict(RESULTS[item['kind']]) if item['state'] == 'completed' else {}}
