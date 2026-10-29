"""0.2.2 (test VM 2026-10-16): n8n-mcp 2.91.0 answered every 403 of an n8n_evaluations action with a fixed "the API key
lacks testRun scopes" hint and dropped n8n's own reason ("Evaluations are not available on your plan"); the 402, 409 and
404 hints did the same. The build patch apps/n8n/patches/fix_test_run_error_messages.py appends " n8n: <n8n's message>"
(owner decision 2026-10-15: backend errors carry the backend's text); backend_policy.cjs only starts the patched file.
0.3.4: n8n-mcp 2.96.2 keeps the same handleTestRunError block; the patch's pinned and patched digests are recomputed.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from test_batch2_n8n_public_errors import KEY, PRIVATE, runtime
from test_expansion_policy import call
from test_real_products import rpc

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('n8n_patch', ROOT / 'apps/n8n/patches/fix_test_run_error_messages.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
direct_spec = importlib.util.spec_from_file_location('n8n_direct_patch', ROOT / 'apps/n8n/patches/fix_direct_inputs.py')
direct = importlib.util.module_from_spec(direct_spec)
direct_spec.loader.exec_module(direct)


def test_the_patch_turns_the_pinned_file_into_the_guarded_one(tmp_path):
    current = patch.TARGET.read_bytes()
    assert patch.digest(current) == patch.COMBINED  # this checkout: packaging/unit.sh (or the image build) applied it
    message_only = current.decode()
    for before, after in reversed(direct.REPLACEMENTS):
        assert message_only.count(after) == 1
        message_only = message_only.replace(after, before, 1)
    assert patch.digest(message_only.encode()) == patch.PATCHED
    pinned = message_only.replace(patch.NEW, patch.OLD).encode()
    assert patch.digest(pinned) == patch.PINNED
    assert patch.digest(patch.patched(pinned)) == patch.PATCHED
    guard = (ROOT / 'apps/n8n/backend_policy.cjs').read_text()
    assert f'["mcp/handlers-n8n-manager.js", "{patch.COMBINED}"]' in guard
    target = tmp_path / 'handlers-n8n-manager.js'
    target.write_bytes(pinned)
    run = lambda: subprocess.run(['python3', str(ROOT / 'apps/n8n/patches/fix_test_run_error_messages.py'), str(target)],
                                 capture_output=True, text=True, timeout=30)
    assert 'patched' in run().stdout and patch.digest(target.read_bytes()) == patch.COMBINED
    assert 'already patched' in run().stdout and patch.digest(target.read_bytes()) == patch.COMBINED  # idempotent
    target.write_bytes(pinned + b'\n// drift\n')
    drift = run()
    assert drift.returncode != 0 and 'review required' in drift.stderr
    for name in ('Dockerfile',):
        assert 'apps/n8n/patches/fix_test_run_error_messages.py' in (ROOT / 'apps/n8n' / name).read_text()
    assert 'apps/n8n/patches/fix_test_run_error_messages.py' in (ROOT / 'packaging/unit.sh').read_text()


@pytest.mark.parametrize('status,hint', [
    (403, "n8n rejected the request (403). The API key lacks testRun scopes"),
    (402, "n8n rejected the request (402): the plan's evaluation quota is used up."),
])
async def test_a_test_run_error_keeps_n8ns_own_message(tmp_path, status, hint):
    async with asyncio.timeout(50), runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        state['case'] = status
        reply = await rpc(client, '/mcp', headers, call('n8n_evaluations', {'action': 'list_runs', 'workflowId': 'owned1'}))
        value = json.loads(next(c['text'] for c in reply['content'] if c['type'] == 'text'))
        assert value['success'] is False and value['error'].startswith(hint), value
        # n8n's own message (the fake echoes the received key, which the gateway replaces with [REDACTED]).
        assert value['error'].endswith(f' n8n: {PRIVATE}:[REDACTED]'), value
        assert KEY not in json.dumps(reply)
        assert any(path.endswith('/test-runs') for _, path, _ in state['calls']), state['calls']
