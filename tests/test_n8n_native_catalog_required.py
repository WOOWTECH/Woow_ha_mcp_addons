"""n8n persistent catalogs must never fall back to sql.js."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/n8n'
PACKAGE = APP / 'node_modules/n8n-mcp'
ADAPTER = PACKAGE / 'dist/database/database-adapter.js'
POLICY = APP / 'backend_policy.cjs'
ENTRY = PACKAGE / 'dist/mcp/index.js'
SEED = PACKAGE / 'data/nodes.db'
TOKEN = 'C' * 43

INJECTOR = r'''
const Module = require('node:module');
const fs = require('node:fs');
const load = Module._load;
let opens = 0;
Module._load = function(name, parent, isMain) {
  if (name === 'sql.js') fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'sqljs\n');
  if (name === 'better-sqlite3') {
    fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'native-require\n');
    if (process.env.TEST_NATIVE_MODE === 'missing') {
      const e = new Error('synthetic missing native module'); e.code = 'MODULE_NOT_FOUND'; throw e;
    }
    if (process.env.TEST_NATIVE_MODE === 'broken') return function() { throw new Error('synthetic binding failure'); };
    const Native = load.apply(this, arguments);
    return new Proxy(Native, {construct(target, args) {
      fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'native-open\n');
      if (++opens > 1 && process.env.TEST_NATIVE_MODE === 'unstable') throw new Error('synthetic later failure');
      return Reflect.construct(target, args);
    }});
  }
  return load.apply(this, arguments);
};
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_for(path, trace, mode, port):
    return {**os.environ, 'NODE_DB_PATH': str(path), 'MCP_MODE': 'http', 'HOST': '127.0.0.1',
            'PORT': str(port), 'AUTH_TOKEN': TOKEN, 'LOG_LEVEL': 'error', 'DISABLE_CONSOLE_OUTPUT': 'true',
            'N8N_MCP_VERSION_CHECK_DISABLED': 'true', 'N8N_MCP_TELEMETRY_DISABLED': 'true',
            'TEST_NATIVE_TRACE': str(trace), 'TEST_NATIVE_MODE': mode}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def catalog(path):
    shutil.copyfile(SEED, path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO workflow_versions(instance_id,workflow_id,version_number,workflow_name,workflow_snapshot,trigger) "
                   "VALUES('i','owned',1,'owned','{\"marker\":true}','partial_update')")


@pytest.mark.parametrize('mode', ['missing', 'broken'])
def test_persistent_adapter_refuses_fallback_without_changing_catalog(tmp_path, mode):
    path, trace, inject = tmp_path/'nodes.db', tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    before = digest(path)
    inject.write_text(INJECTOR)
    script = '''
const {createDatabaseAdapter} = require(process.argv[1]);
(async () => { const db = await createDatabaseAdapter(process.env.NODE_DB_PATH);
  console.log('unexpected adapter:', db.constructor.name); db.close();
})().catch(e => { console.error(e.message); process.exitCode = 23; });
'''
    result = subprocess.run(['node', '--require', str(inject), '-e', script, str(ADAPTER)],
                            env=env_for(path, trace, mode, 0), capture_output=True, text=True, timeout=25)
    assert result.returncode == 23 and 'native' in result.stderr.lower(), (result.returncode, result.stdout, result.stderr)
    assert 'sqljs' not in trace.read_text()
    assert digest(path) == before


@pytest.mark.parametrize('mode', ['missing', 'broken'])
def test_real_child_refuses_to_listen_and_preserves_catalog(tmp_path, mode):
    path, trace, inject = tmp_path/'nodes.db', tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    before = digest(path)
    inject.write_text(INJECTOR)
    port = free_port()
    proc = subprocess.Popen(['node', '--require', str(inject), '--require', str(POLICY), str(ENTRY)],
                            env=env_for(path, trace, mode, port), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        try:
            out, err = proc.communicate(timeout=6)
        except subprocess.TimeoutExpired:
            pytest.fail('child kept running without native SQLite')
        assert proc.returncode != 0 and 'native' in err.lower(), (proc.returncode, out, err)
        assert 'sqljs' not in trace.read_text()
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', port)) != 0
        assert digest(path) == before
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=5)


def test_real_native_child_initializes_its_persistent_catalog(tmp_path):
    path, trace, inject = tmp_path/'nodes.db', tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    inject.write_text(INJECTOR)
    port = free_port()
    proc = subprocess.Popen(['node', '--require', str(inject), '--require', str(POLICY), str(ENTRY)],
                            env=env_for(path, trace, 'native', port), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        url = f'http://127.0.0.1:{port}/mcp'
        with httpx.Client(trust_env=False, timeout=3) as client:
            deadline = time.monotonic() + 20
            while True:
                if proc.poll() is not None:
                    pytest.fail(f'child exited: {proc.stderr.read()}')
                try:
                    response = client.post(url, headers={'Authorization': f'Bearer {TOKEN}',
                        'Accept': 'application/json, text/event-stream'}, json={'jsonrpc':'2.0', 'id':1,
                        'method':'initialize', 'params':{'protocolVersion':'2025-03-26', 'capabilities':{},
                        'clientInfo':{'name':'native-catalog-test', 'version':'1'}}})
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline: raise
                    time.sleep(.05)
            assert response.status_code == 200, response.text
            assert '"serverInfo"' in response.text, response.text
        events = trace.read_text()
        assert events.count('native-open') >= 2 and 'sqljs' not in events, events
        with sqlite3.connect(path) as db:
            assert json.loads(db.execute("SELECT workflow_snapshot FROM workflow_versions WHERE workflow_id='owned'").fetchone()[0]) == {'marker': True}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.communicate(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.communicate(timeout=5)


def test_native_failure_after_preflight_never_falls_back(tmp_path):
    path, trace, inject = tmp_path/'nodes.db', tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    before = digest(path)
    inject.write_text(INJECTOR)
    script = """const {createDatabaseAdapter} = require(process.argv[1]);
(async () => { await createDatabaseAdapter(process.env.NODE_DB_PATH); process.exitCode = 99; })()
.catch(e => { console.error(e.message); process.exitCode = 23; });"""
    result = subprocess.run(['node', '--require', str(inject), '--require', str(POLICY), '-e', script, str(ADAPTER)],
                            env=env_for(path, trace, 'unstable', 0), capture_output=True, text=True, timeout=20)
    assert result.returncode == 23 and 'native' in result.stderr.lower(), result.stderr
    events = trace.read_text()
    assert events.count('native-open') == 2 and 'sqljs' not in events, events
    assert digest(path) == before


@pytest.mark.parametrize('mode', ['missing', 'broken'])
def test_nonpersistent_memory_keeps_upstream_sqljs_fallback(tmp_path, mode):
    trace, inject = tmp_path/'trace', tmp_path/'inject.cjs'
    inject.write_text(INJECTOR)
    script = """const {createDatabaseAdapter} = require(process.argv[1]);
(async () => { const db = await createDatabaseAdapter(':memory:');
console.log(db.constructor.name); db.close(); })().catch(e => { console.error(e); process.exitCode=1; });"""
    result = subprocess.run(['node', '--require', str(inject), '--require', str(POLICY), '-e', script, str(ADAPTER)],
                            cwd=tmp_path, env=env_for(':memory:', trace, mode, 0), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and result.stdout.strip() == 'SQLJSAdapter', (result.stdout, result.stderr)
    assert 'sqljs' in trace.read_text()


@pytest.fixture
def preflight_case_dir(tmp_path, request):
    if request.node.callspec.params['kind'] != 'readonly' or os.geteuid() != 0:
        yield tmp_path
        return
    # The unprivileged child must traverse the directory even when pytest's
    # root-owned tmp_path ancestors are private.
    with tempfile.TemporaryDirectory(prefix='n8n-readonly-', dir='/tmp') as directory:
        path = Path(directory)
        path.chmod(0o755)
        yield path


@pytest.mark.parametrize('kind', ['missing', 'empty', 'corrupt', 'readonly'])
def test_preflight_refuses_invalid_persistent_path_without_creating_or_replacing_it(preflight_case_dir, kind):
    path, trace, inject = preflight_case_dir/'nodes.db', preflight_case_dir/'trace', preflight_case_dir/'inject.cjs'
    inject.write_text(INJECTOR)
    if kind == 'corrupt': path.write_bytes(b'synthetic corrupt catalog')
    child_identity = {}
    policy = POLICY
    if kind == 'readonly':
        catalog(path)
        path.chmod(0o444)
        if os.geteuid() == 0:
            nobody = pwd.getpwnam('nobody')
            child_identity = {'user': nobody.pw_uid, 'group': nobody.pw_gid, 'extra_groups': ()}
            inject.chmod(0o644)
            trace.touch(mode=0o666)
            trace.chmod(0o666)
            # The checkout (including its ancestors) may be inaccessible to nobody.
            # Give the child its own readable copy of the real policy and dependencies.
            app = preflight_case_dir/'app'
            app.mkdir()
            policy = app/'backend_policy.cjs'
            shutil.copyfile(POLICY, policy)
            shutil.copytree(APP/'node_modules', app/'node_modules')
            for directory, dirs, files in os.walk(app):
                Path(directory).chmod(0o755)
                for name in files:
                    file = Path(directory)/name
                    file.chmod(file.stat().st_mode | 0o444)
        # Verify the same identity can load native SQLite and read, but not write, the catalog.
        probe = subprocess.run(['node', '-e', "const fs=require('node:fs'); const D=require('node:module').createRequire(process.argv[2])('better-sqlite3'); new D(':memory:').close(); fs.accessSync(process.argv[1], fs.constants.R_OK); try { fs.accessSync(process.argv[1], fs.constants.W_OK); process.exit(1); } catch {}", str(path), str(policy)],
                               cwd=preflight_case_dir, capture_output=True, text=True, timeout=10, **child_identity)
        assert probe.returncode == 0, (probe.stdout, probe.stderr)
    original = path.read_bytes() if path.exists() else None
    env = env_for('' if kind == 'empty' else path, trace, 'native', 0)
    result = subprocess.run(['node', '--require', str(inject), '--require', str(policy), '-e', "console.log('started')"],
                            cwd=preflight_case_dir, env=env, capture_output=True, text=True, timeout=10, **child_identity)
    assert result.returncode != 0 and 'persistent catalog requires native SQLite' in result.stderr, (result.stdout, result.stderr)
    assert str(path) not in result.stderr
    assert (path.read_bytes() if path.exists() else None) == original
    assert not trace.exists() or 'sqljs' not in trace.read_text()


def test_successful_native_preflight_keeps_catalog_bytes_and_schema_unchanged(tmp_path):
    path, trace, inject = tmp_path/'nodes.db', tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    before = digest(path)
    inject.write_text(INJECTOR)
    result = subprocess.run(['node', '--require', str(inject), '--require', str(POLICY), '-e', "console.log('ready')"],
                            env=env_for(path, trace, 'native', 0), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stdout.strip() == 'ready', result.stderr
    assert digest(path) == before and 'sqljs' not in trace.read_text()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workflow_versions WHERE workflow_id='owned'").fetchone() == (1,)
