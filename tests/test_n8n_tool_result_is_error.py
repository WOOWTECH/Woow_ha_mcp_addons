"""Offline regression: the actual tools/call callback, with fake handler results.

This is not a live n8n or full MCP transport test. The Node VM has no network or
module loader; validation sanitation is an identity fake for these plain values.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'apps/n8n/patches/fix_tool_result_is_error.py'
spec = importlib.util.spec_from_file_location('n8n_result_patch', SCRIPT)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


@pytest.mark.parametrize('name,result,is_error', [
    ('n8n_delete_workflow', {'success': True, 'data': {'id': 'fake'}}, False),
    ('n8n_delete_workflow', {'success': False, 'error': 'FAKE_BACKEND_REFUSED', 'code': 'API_ERROR'}, True),
    ('validate_workflow', {'valid': False, 'errors': [{'message': 'fake invalid workflow'}]}, False),
], ids=['success', 'success-false', 'valid-false'])
def test_tool_response_flag_preserves_result(name, result, is_error):
    completed = subprocess.run(
        ['node', str(ROOT / 'tests/n8n_tool_result_probe.cjs'), str(patch.TARGET),
         json.dumps({'name': name, 'result': result})],
        env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=10, check=True,
    )
    reply = json.loads(completed.stdout)
    assert reply.get('isError', False) is is_error
    assert len(reply['content']) == 1 and reply['content'][0]['type'] == 'text'
    assert reply['content'][0]['text'] == json.dumps(result, indent=2)
    assert json.loads(reply['content'][0]['text']) == result
    if name.startswith('validate_'):
        assert reply['structuredContent'] == result
    else:
        assert 'structuredContent' not in reply


def test_patch_digest_idempotence_drift_and_build_wiring(tmp_path):
    current = patch.TARGET.read_bytes()
    assert patch.digest(current) == patch.PATCHED
    pinned = current.decode().replace(patch.NEW, patch.OLD).encode()
    assert patch.digest(pinned) == patch.PINNED
    target = tmp_path / 'server.js'
    target.write_bytes(pinned)

    def run():
        return subprocess.run([sys.executable, '-B', str(SCRIPT), str(target)],
                              capture_output=True, text=True, timeout=10)

    first = run()
    assert first.returncode == 0 and patch.digest(target.read_bytes()) == patch.PATCHED
    second = run()
    assert second.returncode == 0 and 'already patched' in second.stdout
    assert target.read_bytes() == current
    altered = pinned + b'\n// unreviewed drift\n'
    target.write_bytes(altered)
    drift = run()
    assert drift.returncode != 0 and 'review required' in drift.stderr
    assert target.read_bytes() == altered
    guard = (ROOT / 'apps/n8n/backend_policy.cjs').read_text()
    assert f'["mcp/server.js", "{patch.PATCHED}"]' in guard
    for name in ('apps/n8n/Dockerfile', 'packaging/unit.sh'):
        source = (ROOT / name).read_text()
        assert 'apps/n8n/patches/fix_tool_result_is_error.py' in source
        assert 'apps/n8n/patches/fix_test_run_error_messages.py' in source
