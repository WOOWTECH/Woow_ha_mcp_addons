"""Fault injection at n8n persistent catalog handoff and native open."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

import httpx
import pytest

import n8n_adapter
from mcp_admin_core.config import Store
from test_n8n_native_catalog_required import (ENTRY, POLICY, SEED, TOKEN, catalog, env_for, free_port)

INJECT = r'''
const Module = require('node:module');
const fs = require('node:fs');
const real = Module._load;
let opens = 0;
Module._load = function(name, parent, isMain) {
  if (name === 'sql.js') fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'sqljs\n');
  const v = real.apply(this, arguments);
  if (name !== 'better-sqlite3') return v;
  return new Proxy(v, {construct(target, args) {
    const n = ++opens;
    if (n === 2 && process.env.TEST_RACE === 'before-open') {
      fs.renameSync(process.env.NODE_DB_PATH, process.env.TEST_SAVED);
      fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'removed-before-open\n');
    }
    const db = Reflect.construct(target, args);
    if (n === 1 && process.env.TEST_RACE === 'after-preflight') {
      const close = db.close.bind(db);
      db.close = () => {
        close();
        fs.renameSync(process.env.NODE_DB_PATH, process.env.TEST_SAVED);
        fs.appendFileSync(process.env.TEST_NATIVE_TRACE, 'removed-after-preflight\n');
      };
    }
    return db;
  }});
};
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prepared_default_catalog_disappears_before_child_spec(tmp_path, monkeypatch):
    path = tmp_path / 'nodes.db'
    path.write_bytes(b'owned')
    store = Store(tmp_path / 'state')
    try:
        monkeypatch.setattr(n8n_adapter, '_catalog', path)
        path.unlink()
        with pytest.raises(RuntimeError, match='catalog'):
            n8n_adapter.child_spec(store.load(), store.path.parent)
        assert not path.exists()
    finally:
        store.close()


@pytest.mark.parametrize('race', ['after-preflight', 'before-open'])
def test_real_child_rejects_catalog_loss(tmp_path, race):
    path, saved, replacement = tmp_path/'nodes.db', tmp_path/'saved.db', tmp_path/'replacement.db'
    trace, inject = tmp_path/'trace', tmp_path/'inject.cjs'
    catalog(path)
    original = sha(path)
    catalog(replacement)
    with sqlite3.connect(replacement) as db:
        db.execute("UPDATE workflow_versions SET workflow_name='replacement' WHERE workflow_id='owned'")
    replacement_hash = sha(replacement)
    fallback = tmp_path/'data/nodes.db'
    fallback.parent.mkdir()
    shutil.copyfile(SEED, fallback)
    fallback_hash = sha(fallback)
    inject.write_text(INJECT)
    port = free_port()
    env = {**env_for(path, trace, 'native', port), 'TEST_RACE': race, 'TEST_SAVED': str(saved),
           }
    proc = subprocess.Popen(['node', '--require', str(inject), '--require', str(POLICY), str(ENTRY)],
                            cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        url = f'http://127.0.0.1:{port}/mcp'
        with httpx.Client(trust_env=False, timeout=5) as client:
            deadline = time.monotonic()+20
            while True:
                if proc.poll() is not None:
                    break  # failure before listener is acceptable
                try:
                    response = client.post(url, headers={'Authorization':f'Bearer {TOKEN}',
                        'Accept':'application/json, text/event-stream'}, json={'jsonrpc':'2.0','id':1,
                        'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},
                        'clientInfo':{'name':'race-test','version':'1'}}})
                    assert response.status_code != 200 or '"serverInfo"' not in response.text, response.text
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline: raise
                    time.sleep(.05)
                except httpx.ReadTimeout:
                    break
        assert trace.exists() and {'after-preflight':'removed-after-preflight',
             'before-open':'removed-before-open'}[race] in trace.read_text()
        assert saved.exists() and sha(saved) == original
        assert sha(fallback) == fallback_hash
        assert not path.exists()
        assert sha(replacement) == replacement_hash
        for base in (path, saved, replacement, fallback):
            for suffix in ('-journal','-wal','-shm'):
                assert not Path(str(base)+suffix).exists()
        assert 'sqljs' not in trace.read_text()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.communicate(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.communicate(timeout=5)
