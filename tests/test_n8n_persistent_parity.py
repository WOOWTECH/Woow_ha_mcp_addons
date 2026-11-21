"""Persistent history stays with its profile and backend, including cold restores."""
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from persistent_catalog import prepare


@pytest.fixture
def setup_catalog(tmp_path):
    root = tmp_path / 'data'
    root.mkdir(mode=0o700)
    extra = root / 'profiles' / ('a' * 24)
    extra.mkdir(mode=0o700, parents=True)
    (root / 'profiles').chmod(0o700)
    seed = tmp_path / 'seed.db'
    import n8n_adapter
    shutil.copyfile(n8n_adapter.PACKAGED_CATALOG, seed)
    return root, seed


def state(url='https://one.example', key='first'):
    return SimpleNamespace(backend_url=url, backend_key=key)


def test_history_survives_restart_restore_and_isolated_backend(setup_catalog, tmp_path):
    root, seed = setup_catalog
    first = prepare(root, 'default', state(), seed)
    with sqlite3.connect(first) as db:
        db.execute("INSERT INTO workflow_versions(id,workflow_id,version_number,workflow_name,workflow_snapshot,trigger) VALUES(1,'w',1,'n',?,'full_update')", ('snapshot',))
    assert prepare(root, 'default', state(), seed) == first
    other_profile = prepare(root, 'a' * 24, state(), seed)
    other_backend = prepare(root, 'default', state(key='second'), seed)
    for path in (other_profile, other_backend):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM workflow_versions').fetchone() == (0,)
    restored = tmp_path / 'restored'
    shutil.copytree(root, restored)
    with sqlite3.connect(prepare(restored, 'default', state(), seed)) as db:
        assert db.execute('SELECT workflow_snapshot FROM workflow_versions').fetchone() == ('snapshot',)


def test_corrupt_existing_history_is_not_overwritten(setup_catalog):
    root, seed = setup_catalog
    target = prepare(root, 'default', state(), seed)
    target.write_bytes(b'corrupt evidence')
    with pytest.raises(sqlite3.DatabaseError):
        prepare(root, 'default', state(), seed)
    assert target.read_bytes() == b'corrupt evidence'


def test_catalog_directory_symlink_is_refused(setup_catalog, tmp_path):
    root, seed = setup_catalog
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (root / 'n8n-mcp').symlink_to(elsewhere)
    with pytest.raises(OSError):
        prepare(root, 'default', state(), seed)
    assert not list(elsewhere.iterdir())


def test_strict_policy_with_pinned_n8n_runtime(tmp_path):
    import json
    import os
    import subprocess
    import n8n_adapter
    from mcp_admin_core.config import Store

    store = Store(tmp_path / 'state')
    try:
        spec = n8n_adapter.child_spec(store.load(), store.path.parent)
        assert spec.env['WEBHOOK_SECURITY_MODE'] == 'strict'
        script = r'''
const {SSRFProtection: s} = require(process.argv[1]);
(async () => {
  const ips = ['127.0.0.1', '10.0.0.1', '192.168.1.2', 'fc00::1', '169.254.169.254', '8.8.8.8'];
  const checks = ips.map(ip => s.validateResolvedAddress('example.invalid', ip, 'strict').valid);
  const webhook = await s.validateWebhookUrl('http://127.0.0.1:5678/webhook/test');
  process.stdout.write(JSON.stringify({checks, webhook: webhook.valid}));
})();
'''
        dist = Path(n8n_adapter.__file__).parent / 'node_modules/n8n-mcp/dist/utils/ssrf-protection.js'
        result = subprocess.run([spec.argv[0], '-e', script, str(dist)], env=spec.env,
                                capture_output=True, text=True, timeout=15, check=True)
        assert json.loads(result.stdout) == {'checks': [False, False, False, False, False, True], 'webhook': False}
    finally:
        store.close()


def test_native_n8n_history_survives_a_cold_copy(tmp_path):
    import json
    import os
    import shutil
    import subprocess
    import n8n_adapter

    node = shutil.which('node')
    assert node
    root = tmp_path / 'data'
    root.mkdir(mode=0o700)
    target = prepare(root, 'default', state(), n8n_adapter.PACKAGED_CATALOG)
    package = Path(n8n_adapter.__file__).parent / 'node_modules/n8n-mcp'
    js = r'''
const path = require('path');
const pkg = process.argv[1], dbPath = process.argv[2], mode = process.argv[3];
const {createDatabaseAdapter} = require(path.join(pkg, 'dist/database/database-adapter.js'));
const {NodeRepository} = require(path.join(pkg, 'dist/database/node-repository.js'));
(async () => {
 const db = await createDatabaseAdapter(dbPath);
 if (db.constructor.name !== 'BetterSQLiteAdapter') throw Error('native adapter required');
 const repo = new NodeRepository(db);
 if (mode === 'write') {
   const id = repo.createWorkflowVersion({instanceId: 'i', workflowId: 'w', versionNumber: 1,
     workflowName: 'test', workflowSnapshot: {marker: 'survives'}, trigger: 'partial_update'});
   if (!(Number(id) > 0)) throw Error('version not written');
 }
 db.close();
 process.stdout.write('native-ok');
})();
'''
    subprocess.run([node, '-e', js, str(package), str(target), 'write'], check=True, capture_output=True, timeout=30)
    backup = tmp_path / 'backup'
    shutil.copytree(root, backup)
    restored = prepare(backup, 'default', state(), n8n_adapter.PACKAGED_CATALOG)
    subprocess.run([node, '-e', js, str(package), str(restored), 'read'], check=True, capture_output=True, timeout=30)
    with sqlite3.connect(restored) as db:
        snapshot = db.execute('SELECT workflow_snapshot FROM workflow_versions WHERE workflow_id=?', ('w',)).fetchone()
    assert json.loads(snapshot[0])['marker'] == 'survives'


@pytest.mark.asyncio
async def test_save_check_rejects_mixed_dns_answers(monkeypatch):
    import asyncio
    import socket
    from mcp_admin_core.n8n_ssrf import check_url

    async def resolve(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', port))]
    monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', resolve)
    result = await check_url('https://n8n.example.invalid', 'strict')
    assert not result.ok


def test_supervisor_restore_bootstrap_and_guard_preserve_history(tmp_path):
    """Cold restore passes the actual bootstrap repair and guard before reopening history."""
    import n8n_adapter
    from contextlib import closing
    from mcp_admin_core import restore_lock
    from mcp_admin_core.products import ProductStore
    from test_restore_detection import VirtualRoot, boot

    parent = tmp_path / 'supervisor'
    parent.mkdir()
    data = parent / 'mcp'
    with closing(ProductStore(data, 'n8n')) as store:
        current = store.load()
        path = prepare(data, 'default', current, n8n_adapter.PACKAGED_CATALOG)
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO workflow_versions(instance_id,workflow_id,version_number,workflow_name,"
                       "workflow_snapshot,trigger) VALUES(?,?,?,?,?,?)",
                       ('restore-test', 'restore-test', 1, 'restore-test', '{\"marker\":true}', 'partial_update'))
    backup = tmp_path / 'cold-backup'
    shutil.copytree(data, backup)
    shutil.rmtree(data)
    shutil.copytree(backup, data)
    assert 're-owned' in boot(parent, VirtualRoot())
    with closing(ProductStore(data, 'n8n')) as store:
        outcome = restore_lock.guard(store, 'n8n', enabled=False)
        assert outcome.restored
        restored = prepare(data, 'default', store.load(), n8n_adapter.PACKAGED_CATALOG)
        with sqlite3.connect(restored) as db:
            row = db.execute('SELECT workflow_snapshot FROM workflow_versions WHERE workflow_id=?',
                             ('restore-test',)).fetchone()
        assert row == ('{\"marker\":true}',)
