"""All seven source inventories must stay synchronized; unknown remains denied."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from mcp_admin_core.config import State
from mcp_admin_core.policy import Denied, authorize

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'scripts/tool_inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def test_inventory_names_hashes_schema_and_documentation_do_not_drift():
    actual = inventory.build()
    expected = json.loads((ROOT / 'docs/tool-surface.json').read_text())
    assert actual == expected
    assert inventory.markdown(actual) == (ROOT / 'docs/tool-surface.md').read_text()
    assert {p: d['upstream_count'] for p, d in actual['products'].items()} == {
        'n8n': 28, 'odoo': 41, 'odoo-manage': 10, 'hermes': 11, 'opendesign': 15, 'emqx': 39, 'litellm': 40}


def test_all_withheld_tools_deny_even_when_writes_enabled():
    data = json.loads((ROOT / 'docs/tool-surface.json').read_text())
    state = State(token='a' * 43, child_token='b' * 43, writes_enabled=True)
    count = 0
    for product, group in data['products'].items():
        for tool in group['tools']:
            if tool['status'] == 'temporarily-unsupported':
                with pytest.raises(Denied):
                    authorize({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                               'params': {'name': tool['name'], 'arguments': {}}}, inventory.POLICIES[product], state)
                assert tool['reason'] and tool['enable'] and tool['source']
                count += 1
    assert count == 108  # 184 exact pinned tools, 76 bounded supported (+5 LiteLLM metadata reads).


def test_vendored_content_hashes_and_license_notices():
    import hashlib
    records = json.loads((ROOT / 'docs/provenance/runtime-sources.json').read_text())
    for record in records:
        path = ROOT / 'apps' / record['product'] / 'vendor' / record['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record.get('local_sha256', record['upstream_sha256'])
        if record.get('local_sha256'):
            assert record.get('modification')
    for product in ('hermes', 'opendesign', 'emqx', 'litellm'):
        assert 'MIT License' in (ROOT / 'apps' / product / 'vendor/LICENSE').read_text()


DIGEST = re.compile(r"""['"]([0-9a-f]{64})['"]""")


def guard_apps(patch):
    """Apps whose own code runs a patch's source guard: shared runtime modules by import, BoundedTools by use."""
    if not patch.startswith('apps/runtime/'):
        return {patch.split('/')[1]}
    name = Path(patch).stem
    used = re.compile(r'\bBoundedTools\b' if name == 'bounded_tools' else rf'^\s*(?:from|import) {name}\b', re.M)
    return {app.name for app in (ROOT / 'apps').iterdir() if app.name != 'runtime'
            and any(used.search(f.read_text()) for f in [*app.glob('*.py'), *app.glob('vendor/**/*.py')])}


def test_runtime_patch_ledger_and_guarded_wheel_sources():
    import hashlib
    ledger = json.loads((ROOT / 'docs/provenance/runtime-patches.json').read_text())
    for patch in ledger['patches']:
        assert hashlib.sha256((ROOT / patch['path']).read_bytes()).hexdigest() == patch['sha256']
        assert patch['change']
        for path, expected in patch['guarded_sources'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
        # 0.1.5 (0.1.4 re-review #5): every source-guard digest written in a patched file is listed for review,
        # in every app where that guard runs (the same file has the same digest in each venv).
        written = set(DIGEST.findall((ROOT / patch['path']).read_text()))
        if written:
            apps = guard_apps(patch['path'])
            assert {path.split('/')[1] for path in patch['guarded_sources']} == apps, patch['path']
            for app in apps:
                listed = {digest for path, digest in patch['guarded_sources'].items() if path.startswith(f'apps/{app}/')}
                assert written <= listed, (patch['path'], app, sorted(written - listed))
