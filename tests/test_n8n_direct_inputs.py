"""Run the published compiled handler, not a reimplementation of its direct branch."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/n8n-native'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'apps/n8n/patches/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


message = load('fix_test_run_error_messages')
direct = load('fix_direct_inputs')


def test_native_dispatcher_is_the_reviewed_pinned_dependency():
    package = ROOT / 'apps/n8n/node_modules/n8n-mcp'
    assert json.loads((package / 'package.json').read_text())['version'] == '2.96.2'
    assert hashlib.sha256((package / 'dist/mcp/handlers-official-tools.js').read_bytes()).hexdigest() == \
        'e85937c58d5a8426d54b1b69598adc83a14648402fc58a8714ef5db8132977cd'


@pytest.fixture
def compiled(tmp_path):
    manifest = json.loads((FIXTURES / 'manifest.json').read_text())
    original = gzip.decompress((FIXTURES / 'n8n-mcp-2.96.2-handler.js.gz').read_bytes())
    assert hashlib.sha256(original).hexdigest() == manifest['handler_sha256'] == message.PINNED
    target = tmp_path / 'handler.js'
    target.write_bytes(direct.patched(message.patched(original)))
    return target


@pytest.mark.parametrize('scenario', [
    'formats', 'formats-zod3', 'client-isolation', 'no-inputs', 'failed-retry', 'retry-timeout',
    'failed-retry-not-cached', 'changed-client-in-flight', 'cached-error-no-retry',
    'exposure-denied', 'other-methods', 'wrong-path', 'wrong-code', 'wrong-options',
    'wrong-discriminator', 'wrong-note', 'nested-union-errors',
    'multiple-issues', 'business-error', 'plain-phrase', 'wrong-tool', 'malformed-json',
    'truncated-json', 'authorization', 'execution-error', 'timeout',
])
def test_actual_native_handler(compiled, scenario):
    run = subprocess.run(['node', str(ROOT / 'tests/n8n_direct_inputs_probe.cjs'), str(compiled), scenario],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout.splitlines()[-1])['passed'] is True


def test_combined_bytes_and_existing_build_entrypoint(compiled):
    result = compiled.read_bytes()
    assert direct.digest(result) == message.COMBINED == direct.PATCHED
    original = result.decode()
    for before, after in reversed(direct.REPLACEMENTS):
        assert original.count(after) == 1
        original = original.replace(after, before, 1)
    assert message.digest(original.encode()) == message.PATCHED
    assert message.digest(original.replace(message.NEW, message.OLD).encode()) == message.PINNED
    compiled.write_bytes(original.replace(message.NEW, message.OLD).encode())
    command = [sys.executable, str(ROOT / 'apps/n8n/patches/fix_test_run_error_messages.py'), str(compiled)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    assert compiled.read_bytes() == result
    before = compiled.stat()
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    assert (compiled.stat().st_ino, compiled.stat().st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    guard = (ROOT / 'apps/n8n/backend_policy.cjs').read_text()
    assert f'["mcp/handlers-n8n-manager.js", "{direct.PATCHED}"]' in guard
    assert '638b148f91c18d484b8bcede838be1032f82ddd1b3aa53b24cf005325ae3d9f7' in guard
    subprocess.run(['node', '--check', str(compiled)], check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('kind', ['pristine', 'drift', 'symlink'])
def test_direct_patch_refuses_unreviewed_or_wrong_stage(compiled, kind):
    if kind == 'pristine':
        compiled.write_bytes(gzip.decompress((FIXTURES / 'n8n-mcp-2.96.2-handler.js.gz').read_bytes()))
    elif kind == 'drift':
        compiled.write_bytes(compiled.read_bytes() + b'\n// drift')
    else:
        regular = compiled.with_suffix('.regular.js')
        compiled.rename(regular)
        compiled.symlink_to(regular)
    before = compiled.read_bytes()
    run = subprocess.run([sys.executable, str(ROOT / 'apps/n8n/patches/fix_direct_inputs.py'), str(compiled)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    assert compiled.read_bytes() == before
