"""LOCAL/MOCK: n8n_delete_workflow's description names the way out of n8n's refusal of a published workflow (unreleased,
0.4.12 line).

n8n refuses to delete a published (active) workflow. The pinned upstream describes the tool only as "Permanently delete a
workflow. This action cannot be undone.", so a model that follows the description meets the refusal and has to guess. The
PaaS woow-mcp-server adds one sentence (apps/n8n/n8n_mcp_admin/upstream_result_patch.py); HA 0.4.11 and before did not, so
the two servers described the same tool differently (found by the 2026-11-05 real-backend comparison). The build patch
fix_delete_workflow_description.py makes the same edit to the same file with the same digests. Offline: the installed
n8n-mcp tree, the patch script on copies of the file, the build wiring and the gateway's packaged tools/list snapshot.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from mcp_admin_core.tool_snapshot import LISTED

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'apps/n8n/patches/fix_delete_workflow_description.py'
spec = importlib.util.spec_from_file_location('n8n_delete_description_patch', SCRIPT)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

UPSTREAM = 'Permanently delete a workflow. This action cannot be undone.'
# The PaaS text, character for character (woow-mcp-server 21ec3be8, upstream_result_patch.py _DELETE_DESCRIPTION_PATCHED).
PAAS = (UPSTREAM + ' A published (active) workflow cannot be deleted: deactivate it first with n8n_update_partial_workflow '
        '(operations: [{type: "deactivateWorkflow"}]), then delete it.')

LOAD = r'''
const fs = require('fs'), path = require('path'), Module = require('module');
const [file, before, after] = process.argv.slice(1);
// Compile the file's text (optionally with the patch undone) at its real path, so its relative require still resolves.
const text = fs.readFileSync(file, 'utf8').replace(before, () => after);
const mod = new Module(file, null);
mod.filename = file;
mod.paths = Module._nodeModulePaths(path.dirname(file));
mod._compile(text, file);
console.log(JSON.stringify(mod.exports.n8nManagementTools));
'''


def management_tools(before='', after=''):
    out = subprocess.run(['node', '-e', LOAD, str(patch.TARGET), before, after], env={'PATH': '/usr/bin:/bin'},
                         capture_output=True, text=True, timeout=30, check=True).stdout
    return {tool['name']: tool for tool in json.loads(out)}


def test_the_installed_tool_says_what_the_paas_tool_says_and_nothing_else_changed():
    installed = management_tools()
    pinned = management_tools(patch.NEW, patch.OLD)  # the same file with the build patch undone
    assert installed['n8n_delete_workflow']['description'] == PAAS
    assert pinned['n8n_delete_workflow']['description'] == UPSTREAM
    assert installed.keys() == pinned.keys() and len(installed) == 21
    changed = [name for name in installed if installed[name] != pinned[name]]
    assert changed == ['n8n_delete_workflow']
    assert {**installed['n8n_delete_workflow'], 'description': UPSTREAM} == pinned['n8n_delete_workflow']  # schema, annotations


def test_the_gateways_packaged_listing_carries_the_same_description():
    [listed] = [tool for tool in LISTED['n8n'] if tool['name'] == 'n8n_delete_workflow']
    assert listed['description'] == PAAS


def test_patch_digest_idempotence_drift_and_build_wiring(tmp_path):
    current = patch.TARGET.read_bytes()
    assert patch.digest(current) == patch.PATCHED
    pinned = current.decode().replace(patch.NEW, patch.OLD).encode()
    assert patch.digest(pinned) == patch.PINNED
    target = tmp_path / 'tools-n8n-manager.js'
    target.write_bytes(pinned)

    def run():
        return subprocess.run([sys.executable, '-B', str(SCRIPT), str(target)], capture_output=True, text=True, timeout=10)

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
    missing = tmp_path / 'other.js'
    missing.write_bytes(b'')
    assert subprocess.run([sys.executable, '-B', str(SCRIPT), str(missing)], capture_output=True, text=True,
                          timeout=10).returncode != 0
    guard = (ROOT / 'apps/n8n/backend_policy.cjs').read_text()
    assert f'["mcp/tools-n8n-manager.js", "{patch.PATCHED}"]' in guard  # an unpatched package fails closed
    for name in ('apps/n8n/Dockerfile', 'packaging/unit.sh'):
        assert 'apps/n8n/patches/fix_delete_workflow_description.py' in (ROOT / name).read_text(), name


def test_the_patch_text_is_the_paas_text():
    assert patch.NEW == f'description: `{PAAS}`,' and patch.OLD == f'description: `{UPSTREAM}`,'
    assert (patch.PINNED, patch.PATCHED) == ('28d54ea6a3001678fd510542c82c04c26b2ff3b55b7db63b630800e82e02191f',
                                              'e31acfb4d4344704786d4a69fc4a2a0a6b784a265df3474073dd5bc5951efac7')  # the PaaS digests
