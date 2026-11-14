"""HM-01: scripts/ledger_precheck.py finds digest drift in the three ledgers, names the ledger-pinned files a branch
changes and fails on a new runtime file no ledger lists; it reads only (not even the git index). The checkout itself has
no drift (tests/test_tool_inventory.py remains the gate)."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ledger_precheck', ROOT / 'scripts/ledger_precheck.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)

GUARDED = 'packages/mcp-admin-core/mcp_admin_core/guarded.py'
WHEEL = 'apps/odoo/.venv/lib/python3.13/site-packages/pinned.py'
VENDORED = 'apps/emqx/vendor/emqx_mcp_server/server.py'
SURFACE = 'apps/runtime/tool.py'
EXISTING = 'apps/runtime/existing.py'  # a runtime file no ledger lists, already on the base branch


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    for name, value in (('GIT_CONFIG_GLOBAL', os.devnull), ('GIT_CONFIG_NOSYSTEM', '1'),
                        ('GIT_AUTHOR_NAME', 'HM01 Test'), ('GIT_AUTHOR_EMAIL', 'hm01@example.invalid'),
                        ('GIT_COMMITTER_NAME', 'HM01 Test'), ('GIT_COMMITTER_EMAIL', 'hm01@example.invalid')):
        monkeypatch.setenv(name, value)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write(repo, path, text):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)


def ledgers(repo, guarded):
    write(repo, 'docs/provenance/runtime-patches.json', json.dumps({'scope': 'test', 'patches': [
        {'path': GUARDED, 'sha256': guarded, 'change': 'test', 'guarded_sources': {WHEEL: '0' * 64}}]}))
    write(repo, 'docs/provenance/runtime-sources.json', json.dumps([
        {'product': 'emqx', 'path': 'emqx_mcp_server/server.py', 'source': 'test',
         'upstream_sha256': digest('server\n')}]))
    write(repo, 'docs/tool-surface.json', json.dumps({'format': 1, 'source_digests': {SURFACE: digest('tool\n')}}))


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / 'repo'
    for name, text in ((GUARDED, 'guarded\n'), (VENDORED, 'server\n'), (SURFACE, 'tool\n'), ('README.md', 'x\n'),
                       (EXISTING, 'existing\n'), ('packaging/entrypoint.py', 'entry\n')):
        write(path, name, text)
    ledgers(path, digest('guarded\n'))
    git(path, 'init', '-q', '-b', 'main')
    git(path, 'add', '-A')
    git(path, 'commit', '-q', '-m', 'base')
    git(path, 'switch', '-q', '-c', 'feature')
    return path


def test_this_checkout_has_no_ledger_drift(log_scan):
    report = ledger.precheck(ROOT, None)
    assert report['ok'], ledger.text(report)
    pinned = ledger.pins(ROOT)
    for name, item in report['drift'].items():
        assert item['drift'] == [] and item['missing'] == []
        assert item['checked'] + item['needs_install'] == len(pinned[name]) > 0


def test_drift_and_pinned_changes(repo, capsys):
    write(repo, GUARDED, 'guarded, edited without its ledger\n')
    git(repo, 'commit', '-q', '-am', 'edit')
    report = ledger.precheck(repo, 'main')
    patches = report['drift']['docs/provenance/runtime-patches.json']
    assert patches['drift'] == [GUARDED] and patches['needs_install'] == 1 and patches['missing'] == []
    assert report['drift']['docs/provenance/runtime-sources.json']['checked'] == 1
    assert report['drift']['docs/tool-surface.json']['checked'] == 1
    changes = report['changes']
    assert changes['merge_base'] == git(repo, 'rev-parse', 'main')
    assert changes['pinned_changed'] == [GUARDED] and changes['ledgers_changed'] == []
    assert changes['unlisted_runtime_added'] == changes['unlisted_runtime_changed'] == []
    assert ledger.main(['--repo', str(repo), '--base', 'main']) == 1
    out = capsys.readouterr().out
    assert f'drift: {GUARDED}' in out and 'result: DRIFT' in out and 'edited without' not in out
    # Updated in the same branch: no drift, and the ledger shows as changed.
    ledgers(repo, digest('guarded, edited without its ledger\n'))
    assert ledger.main(['--repo', str(repo), '--base', 'main']) == 0
    report = ledger.precheck(repo, 'main')
    assert report['changes']['ledgers_changed'] == ['docs/provenance/runtime-patches.json']


def test_a_new_runtime_file_no_ledger_lists_fails_and_a_changed_one_is_named(repo, capsys):
    """HM-00 ledger-tracking.md rule 1: the PR that creates a runtime module lists it in runtime-patches.json."""
    write(repo, 'apps/runtime/new.py', 'new\n')                    # committed on the branch
    write(repo, EXISTING, 'existing, edited\n')                     # on the base, no ledger lists it
    write(repo, 'packaging/entrypoint.py', 'entry, edited\n')      # copied into every image
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'edit')
    write(repo, 'apps/runtime/untracked.py', 'untracked\n')        # not even staged
    write(repo, 'apps/runtime/tests/test_x.py', 'test\n')          # tests are not runtime files
    write(repo, 'packaging/other.py', 'build tool\n')              # nor other packaging files
    changes = ledger.precheck(repo, 'main')['changes']
    assert changes['unlisted_runtime_added'] == ['apps/runtime/new.py', 'apps/runtime/untracked.py']
    assert changes['unlisted_runtime_changed'] == [EXISTING, 'packaging/entrypoint.py']
    assert ledger.main(['--repo', str(repo), '--base', 'main']) == 1
    out = capsys.readouterr().out
    assert 'new runtime file no ledger lists (fails' in out and 'result: UNLISTED' in out and 'DRIFT' not in out
    assert f'runtime file no ledger lists (review): {EXISTING}' in out
    # Listed in this branch's ledger (and the untracked one dropped): only the review list stays.
    document = json.loads((repo / 'docs/provenance/runtime-patches.json').read_text())
    document['patches'].append({'path': 'apps/runtime/new.py', 'sha256': digest('new\n'), 'change': 'test',
                                'guarded_sources': {}})
    write(repo, 'docs/provenance/runtime-patches.json', json.dumps(document))
    (repo / 'apps/runtime/untracked.py').unlink()
    report = ledger.precheck(repo, 'main')
    assert report['ok'] and report['changes']['unlisted_runtime_added'] == []
    assert report['changes']['pinned_changed'] == ['apps/runtime/new.py']
    assert ledger.main(['--repo', str(repo), '--base', 'main']) == 0


def test_a_missing_pinned_file_fails(repo, capsys):
    (repo / VENDORED).unlink()
    assert ledger.main(['--repo', str(repo), '--base', '']) == 1
    assert f'missing: {VENDORED}' in capsys.readouterr().out


def test_an_unreadable_ledger_or_base_closes(repo, capsys):
    assert ledger.main(['--repo', str(repo), '--base', 'no-such-branch']) == 2
    write(repo, 'docs/tool-surface.json', '{')
    assert ledger.main(['--repo', str(repo), '--base', '']) == 2
    assert 'unavailable' in capsys.readouterr().err


def test_it_only_reads(repo):
    before = git(repo, 'status', '--porcelain', '--untracked-files=all', '--ignored')
    # A tracked file whose stat no longer matches the index: git diff and git status would refresh (rewrite) the
    # index unless optional locks are off.
    os.utime(repo / 'README.md', ns=(1_000_000_000, 1_000_000_000))
    index = (repo / '.git/index').read_bytes()
    ledger.precheck(repo, 'main')
    assert (repo / '.git/index').read_bytes() == index
    assert git(repo, 'status', '--porcelain', '--untracked-files=all', '--ignored') == before


def test_runs_as_a_script(repo):
    result = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/ledger_precheck.py'), '--repo', str(repo),
                             '--base', 'main', '--json'], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['ok'] is True
