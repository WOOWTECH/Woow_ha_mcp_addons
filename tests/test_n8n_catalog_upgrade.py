"""Real pinned n8n catalog: refresh, strict history schema, and atomic migration."""
import shutil
import sqlite3
from types import SimpleNamespace

import pytest
import n8n_adapter
import persistent_catalog

STATE = SimpleNamespace(backend_url='https://example.invalid', backend_key='SYNTHETIC')


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / 'data'
    root.mkdir(mode=0o700)
    seed = tmp_path / 'seed.db'
    shutil.copyfile(n8n_adapter.PACKAGED_CATALOG, seed)
    path = persistent_catalog.prepare(root, 'default', STATE, seed)
    return root, seed, path


def add_history(db):
    for scope in ('', 'instance-X'):
        db.execute('INSERT INTO workflow_versions(instance_id,workflow_id,version_number,workflow_name,workflow_snapshot,trigger) VALUES(?,?,?,?,?,?)',
                   (scope, 'workflow', 1, 'name', '{"safe":true}', 'full_update'))
    db.execute("UPDATE sqlite_sequence SET seq=900 WHERE name='workflow_versions'")


def test_seed_upgrade_preserves_every_history_field_scope_and_sequence(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        add_history(db)
        rows = db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall()
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    result = persistent_catalog.prepare(root, 'default', STATE, seed)
    with sqlite3.connect(result) as db:
        assert db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall() == rows
        assert db.execute("SELECT seq FROM sqlite_sequence WHERE name='workflow_versions'").fetchone() == (900,)
        assert db.execute("SELECT count(*) FROM nodes WHERE description='UPDATED-TEST-SEED'").fetchone() == (1,)


def test_missing_history_column_is_refused_without_overwriting(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE workflow_versions')
        db.execute('CREATE TABLE workflow_versions(id INTEGER, instance_id TEXT)')
    before = path.read_bytes()
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before


def test_refresh_failure_preserves_original(catalog, monkeypatch):
    root, seed, path = catalog
    with sqlite3.connect(path) as db: add_history(db)
    with sqlite3.connect(seed) as db: db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    before = path.read_bytes()
    def fail(*args): raise OSError('synthetic failure')
    monkeypatch.setattr(persistent_catalog.os, 'replace', fail)
    with pytest.raises(OSError): persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before


def test_empty_seed_sequence_is_preserved(catalog):
    _, _, path = catalog
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM workflow_versions').fetchone() == (0,)
        assert db.execute("SELECT seq FROM sqlite_sequence WHERE name='workflow_versions'").fetchone() == (487,)


def test_missing_catalog_column_is_refused(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE nodes DROP COLUMN npm_readme')
    before = path.read_bytes()
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before


def test_sqlite_sidecar_is_not_discarded(catalog):
    root, seed, path = catalog
    sidecar = path.with_name(path.name + '-wal')
    sidecar.write_bytes(b'preserve this sidecar')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='sidecar'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before
    assert sidecar.read_bytes() == b'preserve this sidecar'


def test_unchanged_seed_keeps_the_existing_database(catalog):
    root, seed, path = catalog
    inode = path.stat().st_ino
    with sqlite3.connect(path) as db:
        add_history(db)
    assert persistent_catalog.prepare(root, 'default', STATE, seed).stat().st_ino == inode
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT instance_id FROM workflow_versions ORDER BY id').fetchall() == [('',), ('instance-X',)]


def test_failed_fsync_preserves_original(catalog, monkeypatch):
    root, seed, path = catalog
    with sqlite3.connect(path) as db: add_history(db)
    with sqlite3.connect(seed) as db: db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    before = path.read_bytes()
    def fail(*args): raise OSError('synthetic fsync failure')
    monkeypatch.setattr(persistent_catalog.os, 'fsync', fail)
    with pytest.raises(OSError): persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before


def test_existing_unmarked_reviewed_database_migrates_without_losing_history(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        add_history(db)
        expected = db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall()
        db.execute('DROP TABLE __woow_catalog_seed')
    persistent_catalog.prepare(root, 'default', STATE, seed)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall() == expected
        assert db.execute("SELECT seq FROM sqlite_sequence WHERE name='workflow_versions'").fetchone() == (900,)


def test_unknown_legacy_history_without_instance_id_is_left_intact(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE workflow_versions')
        db.execute('CREATE TABLE workflow_versions(id INTEGER PRIMARY KEY, workflow_snapshot TEXT)')
        db.execute("INSERT INTO workflow_versions VALUES(1, 'legacy evidence')")
    before = path.read_bytes()
    with pytest.raises(ValueError, match='schema'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before
