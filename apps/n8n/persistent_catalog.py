"""Persistent, profile- and backend-scoped n8n catalog and workflow history.

The catalog and workflow_versions share one SQLite database.  Keep it below the
profile's data directory so Supervisor's cold backup includes it.  A backend
change selects a different file; old histories are never exposed to a new
backend and are retained in the backup until the profile is deleted.
"""
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile


def _private_dir(name, parent=None):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError('catalog directory is not private')
    return fd


def _check_file(directory, name):
    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or not info.st_mode & 0o200):
        raise ValueError('catalog is not a private writable file')
    return info


def _validate(path):
    with closing(sqlite3.connect(path, timeout=10)) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('catalog integrity check failed')
        if not db.execute('SELECT 1 FROM nodes LIMIT 1').fetchone():
            raise ValueError('catalog is empty')
        db.execute('SELECT 1 FROM workflow_versions LIMIT 1').fetchone()
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE __woow_write_probe(value INTEGER)')
            db.execute('INSERT INTO __woow_write_probe VALUES(1)')
        finally:
            db.rollback()


def prepare(root, profile_id, state, source):
    """Open/seed a catalog for one saved identity, or raise without replacing existing data."""
    from mcp_admin_core import profiles
    if profile_id != profiles.DEFAULT_PROFILE and not profiles.is_profile_id(profile_id):
        raise ValueError('invalid profile')
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('catalog seed unavailable')
    root = Path(root)
    fds = []
    try:
        directory = _private_dir(root)
        fds.append(directory)
        if profile_id != profiles.DEFAULT_PROFILE:
            for component in ('profiles', profile_id):
                directory = _private_dir(component, directory)
                fds.append(directory)
        try:
            os.mkdir('n8n-mcp', 0o700, dir_fd=directory)
        except FileExistsError:
            pass
        directory = _private_dir('n8n-mcp', directory)
        fds.append(directory)
        # A filename is derived from both URL and key, never from either as text.
        digest = hashlib.sha256(json.dumps([state.backend_url, state.backend_key]).encode()).hexdigest()
        name = f'{digest}.db'
        lock_fd = os.open('.seed.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                          dir_fd=directory)
        with os.fdopen(lock_fd, 'r+b') as lock:
            info = os.fstat(lock.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                raise ValueError('catalog lock is not private')
            fcntl.flock(lock, fcntl.LOCK_EX)
            proc_dir = Path(f'/proc/self/fd/{directory}')
            path = proc_dir / name
            try:
                _check_file(directory, name)
            except FileNotFoundError:
                fd, temporary = tempfile.mkstemp(prefix='.seed-', suffix='.tmp', dir=proc_dir)
                os.close(fd)
                try:
                    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as seed:
                        with closing(sqlite3.connect(temporary)) as copy:
                            seed.backup(copy)
                    _validate(temporary)
                    with open(temporary, 'rb') as copy:
                        os.fsync(copy.fileno())
                    os.replace(temporary, path)
                    os.fsync(directory)
                finally:
                    try:
                        os.unlink(temporary)
                    except FileNotFoundError:
                        pass
            _check_file(directory, name)
            _validate(path)
        base = root if profile_id == profiles.DEFAULT_PROFILE else root / 'profiles' / profile_id
        result = base / 'n8n-mcp' / name
        held = os.stat(name, dir_fd=directory, follow_symlinks=False)
        visible = os.stat(result, follow_symlinks=False)
        if (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino):
            raise ValueError('catalog path changed')
        return result
    finally:
        for fd in reversed(fds):
            os.close(fd)
