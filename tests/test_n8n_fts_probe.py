"""A killed FTS5 capability probe must not modify the persistent main schema."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'apps/n8n/node_modules/n8n-mcp/dist/database/database-adapter.js'

SCRIPT = r'''
const fs = require('node:fs');
const [file, kind, mode] = process.argv.slice(1);
const {createDatabaseAdapter, createSQLJSAdapter} = require(process.env.ADAPTER_PATH);
(async () => {
  const adapter = await (kind === 'native' ? createDatabaseAdapter(file) : createSQLJSAdapter(file));
  if (kind === 'native' && adapter.constructor.name !== 'BetterSQLiteAdapter') throw Error('native adapter missing');
  // sql.js's bundled SQLite lacks FTS5. For its crash path only, emulate the
  // CREATE operation using an ordinary table in the namespace named by the
  // real statement, then force an export as if its asynchronous save fired.
  if (kind === 'sqljs' && mode === 'crash') {
    const exec = adapter.db.exec.bind(adapter.db);
    adapter.db.exec = sql => exec(sql.replace('CREATE VIRTUAL TABLE', 'CREATE TABLE')
      .replace(' USING fts5(content)', ' (content)'));
  }
  const exec = adapter.exec.bind(adapter);
  adapter.exec = sql => {
    const result = exec(sql);
    if (mode === 'crash' && sql.startsWith('CREATE VIRTUAL TABLE')) {
      if (kind === 'sqljs') fs.writeFileSync(file, Buffer.from(adapter.db.export()));
      fs.writeSync(1, 'created\n');
      process.kill(process.pid, 'SIGKILL');
      throw Error('kill did not arrive');
    }
    return result;
  };
  const supported = adapter.checkFTS5Support();
  const temp = adapter.prepare("SELECT name FROM sqlite_temp_master WHERE name LIKE 'test_fts5%' ORDER BY name").all();
  adapter.close();
  console.log(JSON.stringify({node:process.version, adapter:adapter.constructor.name, supported, temp}));
})().catch(e => { console.error(e); process.exitCode=1; });
'''


def main_schema(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name").fetchall()


def run_node(path, kind, mode):
    env = {**os.environ, 'ADAPTER_PATH': str(ADAPTER), 'MCP_MODE': 'stdio'}
    return subprocess.run(['node', '-e', SCRIPT, str(path), kind, mode], env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize('kind', ['native', 'sqljs'])
def test_probe_killed_immediately_after_create_leaves_main_schema_unchanged(tmp_path, kind):
    path = tmp_path / 'catalog.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE existing (v TEXT)')
    before = main_schema(path)
    run = run_node(path, kind, 'crash')
    assert run.returncode == -9 and run.stdout == 'created\n', (run.returncode, run.stdout, run.stderr)
    assert main_schema(path) == before


@pytest.mark.parametrize('kind,supported', [('native', True), ('sqljs', False)])
def test_normal_probe_keeps_main_table_named_test_fts5(tmp_path, kind, supported):
    path = tmp_path / 'catalog.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE test_fts5 (v TEXT)')
        db.execute("INSERT INTO test_fts5 VALUES ('preserve')")
    before = main_schema(path)
    run = run_node(path, kind, 'normal')
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result == {'node': 'v26.12.1', 'adapter': 'BetterSQLiteAdapter' if kind == 'native' else 'SQLJSAdapter',
                      'supported': supported, 'temp': []}
    assert main_schema(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT v FROM test_fts5').fetchall() == [('preserve',)]


def test_patch_is_exact_idempotent_wired_and_runtime_guarded(tmp_path):
    import importlib.util

    path = ROOT / 'apps/n8n/patches/fix_fts_probe_temp.py'
    spec = importlib.util.spec_from_file_location('fts_patch', path)
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    current = ADAPTER.read_bytes()
    assert patch.digest(current) == patch.PATCHED
    assert current.count(patch.NEW.encode()) == 2
    original = current.replace(patch.NEW.encode(), patch.OLD.encode())
    assert patch.digest(original) == patch.PINNED
    assert original == (ROOT / 'apps/n8n/patches/tests/database-adapter-2.96.2.js').read_bytes()
    assert patch.patched(original) == current
    target = tmp_path / 'adapter.js'
    target.write_bytes(original)
    def apply():
        return subprocess.run(['python3', str(path), str(target)], capture_output=True, text=True, timeout=10)
    assert apply().returncode == 0 and target.read_bytes() == current
    assert 'already patched' in apply().stdout
    target.write_bytes(original + b'\n// unexpected\n')
    result = apply()
    assert result.returncode != 0 and 'review required' in result.stderr
    assert target.read_bytes() == original + b'\n// unexpected\n'
    for name in ('apps/n8n/Dockerfile', 'packaging/unit.sh'):
        assert 'apps/n8n/patches/fix_fts_probe_temp.py' in (ROOT / name).read_text()
    assert f'["database/database-adapter.js", "{patch.PATCHED}"]' in (ROOT / 'apps/n8n/backend_policy.cjs').read_text()


def test_child_guard_refuses_unpatched_adapter_before_loading_it(tmp_path):
    import importlib.util
    import shutil

    patch_path = ROOT / 'apps/n8n/patches/fix_fts_probe_temp.py'
    spec = importlib.util.spec_from_file_location('fts_patch_guard_test', patch_path)
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    app = tmp_path / 'n8n'
    modules = app / 'node_modules'
    runtime = modules / 'n8n-mcp/dist'
    (runtime / 'services').mkdir(parents=True)
    (runtime / 'database').mkdir()
    (modules / 'ipaddr.js').symlink_to(ROOT / 'apps/n8n/node_modules/ipaddr.js', target_is_directory=True)
    shutil.copyfile(ROOT / 'apps/n8n/backend_policy.cjs', app / 'backend_policy.cjs')
    shutil.copyfile(ROOT / 'apps/n8n/node_modules/n8n-mcp/dist/services/n8n-api-client.js',
                    runtime / 'services/n8n-api-client.js')
    current = ADAPTER.read_bytes()
    original = current.replace(patch.NEW.encode(), patch.OLD.encode())
    assert patch.digest(original) == patch.PINNED
    (runtime / 'database/database-adapter.js').write_bytes(original)
    result = subprocess.run(['node', '-e', f'require({json.dumps(str(app / "backend_policy.cjs"))})'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'requires source review' in result.stderr
