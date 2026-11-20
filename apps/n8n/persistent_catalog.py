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
import re
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


# Only the reviewed upstream 2.96.2 history schema is supported. Unknown
# versions must be reviewed, not handed to upstream's destructive migration.
HISTORY_COLUMNS = (
    ('id', 'INTEGER', 0, None, 1), ('instance_id', 'TEXT', 1, "''", 0),
    ('workflow_id', 'TEXT', 1, None, 0), ('version_number', 'INTEGER', 1, None, 0),
    ('workflow_name', 'TEXT', 1, None, 0), ('workflow_snapshot', 'TEXT', 1, None, 0),
    ('trigger', 'TEXT', 1, None, 0), ('operations', 'TEXT', 0, None, 0),
    ('fix_types', 'TEXT', 0, None, 0), ('metadata', 'TEXT', 0, None, 0),
    ('created_at', 'DATETIME', 0, 'CURRENT_TIMESTAMP', 0),
)
HISTORY_NAMES = tuple(row[0] for row in HISTORY_COLUMNS)
HISTORY_SQL_SHA256 = 'd6a76b2986971ea52c0ea80844b909ba21683385942a1db223912ff64e7fefda'
CATALOG_TABLES = ('nodes', 'node_versions', 'templates', 'template_node_configs', 'nodes_fts', 'templates_fts')


def _validate(path, *, writable=True, reference=None):
    uri = Path(path).as_uri() + ('?mode=rw' if writable else '?mode=ro')
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('catalog integrity check failed')
        if not db.execute('SELECT 1 FROM nodes LIMIT 1').fetchone():
            raise ValueError('catalog is empty')
        if tuple(tuple(row[1:]) for row in db.execute('PRAGMA table_info(workflow_versions)')) != HISTORY_COLUMNS:
            raise ValueError('unsupported workflow history schema')
        history_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workflow_versions'").fetchone()
        if not history_sql or hashlib.sha256(' '.join(history_sql[0].split()).encode()).hexdigest() != HISTORY_SQL_SHA256:
            raise ValueError('unsupported workflow history constraints')
        for table in CATALOG_TABLES:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                raise ValueError('catalog schema incomplete')
        if reference is not None:
            with closing(sqlite3.connect(Path(reference).as_uri() + '?mode=ro', uri=True)) as seed:
                def objects(connection):
                    return {(kind, name, table, ' '.join(sql.split()) if sql is not None else None)
                            for kind, name, table, sql in connection.execute(
                                'SELECT type,name,tbl_name,sql FROM sqlite_master')}
                expected_objects = objects(seed)
                actual_objects = objects(db)
                marker = ('table', '__woow_catalog_seed', '__woow_catalog_seed',
                          'CREATE TABLE __woow_catalog_seed(digest TEXT NOT NULL)')
                if actual_objects != expected_objects and actual_objects != expected_objects | {marker}:
                    raise ValueError('unsupported catalog schema')
                for table in CATALOG_TABLES:
                    expected = tuple(tuple(row[1:]) for row in seed.execute(f'PRAGMA table_info("{table}")'))
                    actual = tuple(tuple(row[1:]) for row in db.execute(f'PRAGMA table_info("{table}")'))
                    if not expected or expected != actual:
                        raise ValueError('unsupported catalog schema')
        if writable:
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE __woow_write_probe(value INTEGER)')
                db.execute('INSERT INTO __woow_write_probe VALUES(1)')
            finally:
                db.rollback()


def _seed_digest(source):
    with source.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _stored_digest(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        found = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='__woow_catalog_seed'").fetchone()
        if not found:
            return None
        rows = db.execute('SELECT digest FROM __woow_catalog_seed LIMIT 2').fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str):
            raise ValueError('invalid catalog seed marker')
        return rows[0][0]


def _refresh(source, old, temporary, digest):
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as seed:
        with closing(sqlite3.connect(temporary)) as copy:
            seed.backup(copy)
    _validate(temporary, reference=source)
    with closing(sqlite3.connect(temporary.as_uri() + '?mode=rw', uri=True)) as db:
        if db.execute('SELECT 1 FROM workflow_versions LIMIT 1').fetchone():
            raise ValueError('seed contains workflow history')
        if old is not None:
            db.execute('ATTACH DATABASE ? AS prior', (old.as_uri() + '?mode=ro',))
            columns = ','.join('"' + name + '"' for name in HISTORY_NAMES)
            oldseq = db.execute("SELECT seq FROM prior.sqlite_sequence WHERE name='workflow_versions' LIMIT 2").fetchall()
            if len(oldseq) > 1:
                raise ValueError('invalid history sequence')
            db.execute(f'INSERT INTO main.workflow_versions ({columns}) SELECT {columns} FROM prior.workflow_versions')
            for left, right in (('main', 'prior'), ('prior', 'main')):
                if db.execute(f'SELECT {columns} FROM {left}.workflow_versions EXCEPT SELECT {columns} FROM {right}.workflow_versions LIMIT 1').fetchone():
                    raise ValueError('history migration mismatch')
            db.execute("DELETE FROM sqlite_sequence WHERE name='workflow_versions'")
            if oldseq:
                db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('workflow_versions',?)", oldseq[0])
            if db.execute("SELECT seq FROM sqlite_sequence WHERE name='workflow_versions'").fetchall() != oldseq:
                raise ValueError('history sequence mismatch')
        db.execute('CREATE TABLE __woow_catalog_seed(digest TEXT NOT NULL)')
        db.execute('INSERT INTO __woow_catalog_seed VALUES(?)', (digest,))
        db.commit()
    _validate(temporary, reference=source)


# These names are reserved for files created under the catalog lock. Never
# follow links or remove unrecognised files when recovering an interrupted run.
_TEMPORARY = re.compile(r'\.(?:seed|undo)-[a-z0-9_]{8}\.tmp(?:-journal)?')
_PREVIOUS = re.compile(r'\.previous-([0-9a-f]{64})\.db')


def _no_sidecars(directory, name):
    for suffix in ('-wal', '-shm', '-journal'):
        try:
            os.stat(name + suffix, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise ValueError('catalog has SQLite sidecar')


def _recover(directory):
    """Preserve ambiguous files; names alone cannot prove ownership or publication state."""
    if any(_PREVIOUS.fullmatch(name) or _TEMPORARY.fullmatch(name) for name in os.listdir(directory)):
        raise ValueError('catalog recovery required; preserve files for manual review')


def _save_previous(directory, proc_dir, name, source):
    """Durably save a separate single-link SQLite snapshot before replacement."""
    previous = '.previous-' + name
    try:
        os.stat(previous, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise ValueError('catalog recovery required')
    fd, temporary = tempfile.mkstemp(prefix='.undo-', suffix='.tmp', dir=proc_dir)
    os.close(fd)
    try:
        with closing(sqlite3.connect((proc_dir / name).as_uri() + '?mode=ro', uri=True)) as old:
            with closing(sqlite3.connect(temporary)) as backup:
                old.backup(backup)
        _validate(Path(temporary), writable=False, reference=source)
        with open(temporary, 'rb') as backup:
            os.fsync(backup.fileno())
        os.replace(temporary, proc_dir / previous)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return previous


def _same_history(first, second):
    """Do not publish a migration if history changed while its snapshot was made."""
    with closing(sqlite3.connect(first.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('ATTACH DATABASE ? AS saved', (second.as_uri() + '?mode=ro',))
        columns = ','.join('"' + name + '"' for name in HISTORY_NAMES)
        for left, right in (('main', 'saved'), ('saved', 'main')):
            if db.execute(f'SELECT {columns} FROM {left}.workflow_versions EXCEPT SELECT {columns} FROM {right}.workflow_versions LIMIT 1').fetchone():
                raise ValueError('history changed during catalog refresh')
        for schema in ('main', 'saved'):
            sequence = db.execute(f"SELECT seq FROM {schema}.sqlite_sequence WHERE name='workflow_versions' LIMIT 2").fetchall()
            if schema == 'main':
                expected = sequence
            elif sequence != expected:
                raise ValueError('history sequence changed during catalog refresh')


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
            _validate(source, writable=False)
            digest = _seed_digest(source)
            _recover(directory)
            try:
                _check_file(directory, name)
                exists = True
            except FileNotFoundError:
                exists = False
            if exists:
                # Sidecars can hold committed data not present in the main file.
                _no_sidecars(directory, name)
                _validate(path, reference=source)
            if not exists or _stored_digest(path) != digest:
                fd, temporary = tempfile.mkstemp(prefix='.seed-', suffix='.tmp', dir=proc_dir)
                os.close(fd)
                try:
                    _refresh(source, path if exists else None, Path(temporary), digest)
                    with open(temporary, 'rb') as copy:
                        os.fsync(copy.fileno())
                    previous = _save_previous(directory, proc_dir, name, source) if exists else None
                    if previous is not None:
                        _same_history(Path(temporary), proc_dir / previous)
                    os.replace(temporary, path)
                    os.fsync(directory)
                    if previous is not None:
                        os.unlink(previous, dir_fd=directory)
                        os.fsync(directory)
                finally:
                    try:
                        os.unlink(temporary)
                    except FileNotFoundError:
                        pass
            _check_file(directory, name)
            _validate(path, reference=source)

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
