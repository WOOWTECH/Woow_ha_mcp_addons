"""Standalone UI ownership regressions; no foreign listener or port3000 I/O."""
import json
import os
from pathlib import Path
import signal
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_node(args, tmp_path, *, extra_env=None, deadline=50):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'PLAYWRIGHT_BROWSERS_PATH': '0',
           'UI_EVIDENCE_DIR': str(tmp_path), **(extra_env or {})}
    with (tmp_path/'node.log').open('w+') as log:
        process = subprocess.Popen(['node', *args], cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        log.seek(0)
        output = log.read()
    print(output)
    print(json.dumps({'owned_node': process.pid, 'pgid': process.pid,
                      'exit': process.returncode, 'reaped': True, 'deadline': deadline,
                      'timed_out': timed_out}))
    assert not timed_out
    assert process.returncode == 0, output
    return output


def test_installed_standalone_startup_refuses_owned_decoy_without_http(tmp_path):
    output = run_node(['tests/owned_ui_preflight.mjs'], tmp_path, deadline=25)
    record = json.loads(output.splitlines()[0])
    assert record['proofBeforeStartup'] and record['closed'] and record['reaped']
    assert record['hits'] == 0 and record['code'] == 1


@pytest.mark.parametrize('mode', ['unit', 'lifecycle', 'browser'])
def test_standalone_ownership_boundaries(tmp_path, mode):
    output = run_node(['tests/owned_ui_regressions.mjs', mode], tmp_path)
    assert f'"mode":"{mode}"' in output


@pytest.mark.parametrize('relative', ['playwright.config.mjs', 'fixtures/server.mjs'])
@pytest.mark.parametrize('port', ['3000', '43210', '0', '-1', '65536', 'invalid', ''])
def test_ui_overrides_refused_before_listen_or_connect(tmp_path, relative, port):
    target = (ROOT/'packages/mcp-admin-ui'/relative).as_uri()
    code = f'''
import assert from 'node:assert/strict';
import net from 'node:net';
let calls=0;
net.Server.prototype.listen=function(){{calls++; throw Error('downstream listen');}};
net.Socket.prototype.connect=function(){{calls++; throw Error('downstream connect');}};
await assert.rejects(import({json.dumps(target)}), /invalid private UI_PORT/);
assert.equal(calls,0);
'''
    run_node(['--input-type=module', '-e', code], tmp_path,
             extra_env={'UI_PORT': port}, deadline=5)
