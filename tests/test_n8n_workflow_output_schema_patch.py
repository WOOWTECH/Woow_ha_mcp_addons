"""Exact npm 2.96.2 artifact correction, before public schema publication."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'apps/n8n/patches/fix_workflow_output_schema.py'
FIXTURE = ROOT / 'tests/fixtures/n8n-native/n8n-mcp-2.96.2-tools.js.gz'
spec = importlib.util.spec_from_file_location('n8n_workflow_output_patch', SCRIPT)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


@pytest.fixture
def package(tmp_path):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == 'f1f99d4d1f8b9416e8036695047271eeffd08669ded30fbe349fb3feeda86a03'
    original = gzip.decompress(FIXTURE.read_bytes())
    assert patch.digest(original) == patch.ORIGINAL
    target = tmp_path / 'dist/mcp/tools.js'
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    (tmp_path / 'package.json').write_text(json.dumps({'version': patch.VERSION}))
    return tmp_path


def test_exact_schema_only_and_idempotence(package):
    target = package / 'dist/mcp/tools.js'
    original = target.read_bytes()
    assert patch.patch(package) is True
    fixed = target.read_bytes()
    assert patch.digest(fixed) == patch.PATCHED
    assert fixed.replace(patch.AFTER, patch.BEFORE) == original
    assert patch.patch(package) is False


def test_node_exports_corrected_warning_and_error_schema(package):
    assert patch.patch(package) is True
    script = """
const tools=require(process.argv[1]).n8nDocumentationToolsFinal;
const output=tools.find(x=>x.name==='validate_workflow').outputSchema;
console.log(JSON.stringify({names:tools.map(x=>x.name),
  error:output.properties.errors.items.properties.details,
  warning:output.properties.warnings.items.properties.details}));
"""
    done = subprocess.run(['node', '-e', script, str(package / 'dist/mcp/tools.js')],
                          capture_output=True, text=True, check=True, timeout=15)
    observed = json.loads(done.stdout)
    assert observed['error'] == observed['warning'] == {'type': 'object'}
    assert len(observed['names']) == 7


def test_unknown_version_or_source_rejected(package):
    target = package / 'dist/mcp/tools.js'
    original = target.read_bytes()
    (package / 'package.json').write_text('{"version":"2.96.3"}')
    with pytest.raises(ValueError, match='version'):
        patch.patch(package)
    assert target.read_bytes() == original
    (package / 'package.json').write_text(json.dumps({'version': patch.VERSION}))
    target.write_bytes(original + b'\n// drift\n')
    drift = target.read_bytes()
    with pytest.raises(ValueError, match='bytes'):
        patch.patch(package)
    assert target.read_bytes() == drift


def test_build_and_unit_wiring():
    for name in ('apps/n8n/Dockerfile', 'packaging/unit.sh'):
        assert 'apps/n8n/patches/fix_workflow_output_schema.py' in (ROOT / name).read_text()
