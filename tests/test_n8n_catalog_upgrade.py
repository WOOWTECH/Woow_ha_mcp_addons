"""Real pinned n8n catalog: refresh, strict history schema, and atomic migration."""
import shutil
import sqlite3
from types import SimpleNamespace
from pathlib import Path

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


def test_unknown_populated_table_is_refused_without_loss(catalog):
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE user_extra (important TEXT)')
        db.execute("INSERT INTO user_extra VALUES('preserve me')")
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    before = path.read_bytes()
    with pytest.raises(ValueError, match='schema'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT important FROM user_extra').fetchone() == ('preserve me',)


def test_killed_process_leaves_temporary_then_restart_recovers(catalog, tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time
    root, seed, path = catalog
    with sqlite3.connect(path) as db: add_history(db)
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    marker = tmp_path / 'ready'
    code = '''
import os, sys, time
from pathlib import Path
from types import SimpleNamespace
import persistent_catalog as p
original = p._refresh
def pause(*args):
    original(*args)
    Path(sys.argv[3]).write_text('ready')
    while True: time.sleep(1)
p._refresh = pause
p.prepare(Path(sys.argv[1]), 'default', SimpleNamespace(backend_url='https://example.invalid', backend_key='SYNTHETIC'), Path(sys.argv[2]))
'''
    env = os.environ.copy()
    repo = Path(n8n_adapter.__file__).resolve().parents[1]
    env['PYTHONPATH'] = os.pathsep.join([str(repo / 'n8n'), str(repo.parent / 'packages/mcp-admin-core'), env.get('PYTHONPATH', '')])
    process = subprocess.Popen([sys.executable, '-c', code, str(root), str(seed), str(marker)], env=env)
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert marker.exists()
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
        leftovers = list(path.parent.glob('.seed-*.tmp'))
        assert len(leftovers) == 1
        with pytest.raises(ValueError, match='recovery required'):
            persistent_catalog.prepare(root, 'default', STATE, seed)
        assert leftovers[0].exists()
        # Test-only operator decision after inspecting the stopped process's temporary.
        leftovers[0].unlink()
        persistent_catalog.prepare(root, 'default', STATE, seed)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT instance_id FROM workflow_versions ORDER BY id').fetchall() == [('',), ('instance-X',)]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_directory_fsync_failure_after_replace_retains_snapshot_and_recovers(catalog, monkeypatch):
    import os
    import stat
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        add_history(db)
        history = db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall()
        old_node = db.execute('SELECT description FROM nodes ORDER BY node_type LIMIT 1').fetchone()
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes ORDER BY node_type LIMIT 1)")
    real_replace, real_fsync = os.replace, os.fsync
    replaced = False
    def replace(src, dst, *args, **kwargs):
        nonlocal replaced
        result = real_replace(src, dst, *args, **kwargs)
        if Path(dst).name == path.name: replaced = True
        return result
    def fsync(fd):
        if replaced and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('synthetic directory fsync failure')
        return real_fsync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(persistent_catalog.os, 'replace', replace)
        patch.setattr(persistent_catalog.os, 'fsync', fsync)
        with pytest.raises(OSError, match='directory fsync'):
            persistent_catalog.prepare(root, 'default', STATE, seed)
    backups = list(path.parent.glob('.previous-*.db'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall() == history
        assert db.execute('SELECT description FROM nodes ORDER BY node_type LIMIT 1').fetchone() == old_node
    target_before, backup_before = path.read_bytes(), backups[0].read_bytes()
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == target_before and backups[0].read_bytes() == backup_before
    # Test-only operator selection: restore the examined snapshot, then retry.
    os.replace(backups[0], path)
    persistent_catalog.prepare(root, 'default', STATE, seed)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall() == history


@pytest.mark.parametrize('stage', ['snapshot', 'replacement'])
def test_kill_after_snapshot_or_replacement_recovers(catalog, tmp_path, stage):
    import os
    import signal
    import subprocess
    import sys
    import time
    root, seed, path = catalog
    with sqlite3.connect(path) as db:
        add_history(db)
        rows = db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall()
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    ready = tmp_path / 'publication-ready'
    script = '''
import os, sys, time
from pathlib import Path
from types import SimpleNamespace
import persistent_catalog as p
real = os.replace
def pause(src, dst, *args, **kwargs):
    result = real(src, dst, *args, **kwargs)
    name = Path(dst).name
    if (sys.argv[4] == 'snapshot' and name.startswith('.previous-')) or (sys.argv[4] == 'replacement' and name == sys.argv[5]):
        Path(sys.argv[3]).write_text('ready')
        while True: time.sleep(1)
    return result
p.os.replace = pause
p.prepare(Path(sys.argv[1]), 'default', SimpleNamespace(backend_url='https://example.invalid', backend_key='SYNTHETIC'), Path(sys.argv[2]))
'''
    repo = Path(n8n_adapter.__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(repo / 'n8n'), str(repo.parent / 'packages/mcp-admin-core')])}
    process = subprocess.Popen([sys.executable, '-c', script, str(root), str(seed), str(ready), stage, path.name], env=env)
    try:
        deadline = time.monotonic() + 40
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists()
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
        assert len(list(path.parent.glob('.previous-*.db'))) == 1
        backups = list(path.parent.glob('.previous-*.db'))
        leftovers = list(path.parent.glob('.seed-*.tmp'))
        with pytest.raises(ValueError, match='recovery required'):
            persistent_catalog.prepare(root, 'default', STATE, seed)
        assert backups[0].exists() and all(item.exists() for item in leftovers)
        # Test-only manual choice after inspecting both catalog generations.
        os.replace(backups[0], path)
        for item in leftovers: item.unlink()
        persistent_catalog.prepare(root, 'default', STATE, seed)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT * FROM workflow_versions ORDER BY id').fetchall() == rows
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_untrusted_temporary_symlink_is_never_followed_or_removed(catalog, tmp_path):
    root, seed, path = catalog
    other = tmp_path / 'important'
    other.write_text('preserve')
    link = path.parent / '.seed-abcdefgh.tmp'
    link.symlink_to(other)
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert link.is_symlink() and other.read_text() == 'preserve'


def test_different_history_in_recovery_is_not_overwritten(catalog, monkeypatch):
    root, seed, path = catalog
    with sqlite3.connect(path) as db: add_history(db)
    with sqlite3.connect(seed) as db:
        db.execute("UPDATE nodes SET description='UPDATED-TEST-SEED' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    original_replace = persistent_catalog.os.replace
    def stop(src, dst, *args, **kwargs):
        if Path(dst).name == path.name:
            raise OSError('stop before replacement')
        return original_replace(src, dst, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(persistent_catalog.os, 'replace', stop)
        with pytest.raises(OSError, match='stop before replacement'):
            persistent_catalog.prepare(root, 'default', STATE, seed)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO workflow_versions(instance_id,workflow_id,version_number,workflow_name,workflow_snapshot,trigger) VALUES('', 'newer', 1, 'name', '{}', 'full_update')")
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert list(path.parent.glob('.previous-*.db'))
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workflow_versions WHERE workflow_id='newer'").fetchone() == (1,)


@pytest.mark.parametrize('name', ['.seed-abcdefgh.tmp', '.undo-abcdefgh.tmp', '.seed-abcdefgh.tmp-journal'])
def test_unknown_regular_temporary_is_preserved(catalog, name):
    root, seed, path = catalog
    unknown = path.parent / name
    unknown.write_bytes(b'unrelated important data')
    unknown.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert unknown.read_bytes() == b'unrelated important data'
    assert path.read_bytes() == before


def test_recovery_preserves_target_and_previous_with_different_catalog_data(catalog):
    root, seed, path = catalog
    previous = path.parent / ('.previous-' + path.name)
    shutil.copyfile(path, previous)
    previous.chmod(0o600)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE nodes SET description='NEWER-USER-DATA' WHERE node_type=(SELECT node_type FROM nodes LIMIT 1)")
    before, backup = path.read_bytes(), previous.read_bytes()
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert path.read_bytes() == before and previous.read_bytes() == backup
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM nodes WHERE description='NEWER-USER-DATA'").fetchone() == (1,)


def test_previous_with_missing_target_is_preserved_for_manual_review(catalog):
    root, seed, path = catalog
    previous = path.parent / ('.previous-' + path.name)
    path.rename(previous)
    before = previous.read_bytes()
    with pytest.raises(ValueError, match='recovery required'):
        persistent_catalog.prepare(root, 'default', STATE, seed)
    assert not path.exists() and previous.read_bytes() == before
