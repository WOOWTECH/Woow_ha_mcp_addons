"""HM-01: scripts/secret_precheck.py with a stand-in gitleaks (the pinned binary is not on the CI runner).

The stand-in records each invocation with the configuration it was given and answers with the report the test chose.
Checked: the scanner comes only from the pinned archive and runs only after its digest and version check; the
allowlist is exactly packaging/supply_chain.py gitleaks_config(); the flags are the builder gate's history scan except
--exit-code 0 and the commit range; the range is the branch's own commits; a finding is shown without its value; any
other failure closes (exit 2) without echoing scanner output.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('secret_precheck', ROOT / 'scripts/secret_precheck.py')
precheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(precheck)

COPIED = ('packaging/supply_chain.py', 'packaging/inputs.json', 'packaging/scanner-pins.json',
          'packaging/secret-triage.json', 'packaging/supply-chain-policy.json',
          'tests/fixtures/owner_defaults/schema1-n8n-313ab01.json',
          'tests/fixtures/owner_defaults/schema3-n8n-v0.1.14-max.json',
          'tests/fixtures/owner_defaults/schema4-n8n-v0.2.2-max.json')
PINNED = json.loads((ROOT / 'packaging/scanner-pins.json').read_text())['gitleaks']['version']  # 8.28.0 at bb48449
STAND_IN = r'''#!{python}
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
args = sys.argv[1:]
if args == ['version']:
    print((here / 'version').read_text() if (here / 'version').exists() else '{version}')
    sys.exit(0)
with open(here / 'calls.jsonl', 'a') as log:
    log.write(json.dumps({'argv': args, 'config': Path(args[args.index('--config') + 1]).read_text()}) + '\n')
Path(args[args.index('--report-path') + 1]).write_text((here / 'findings.json').read_text())
sys.stderr.write((here / 'stderr').read_text())
sys.exit(int((here / 'status').read_text()))
'''


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    for name, value in (('GIT_CONFIG_GLOBAL', os.devnull), ('GIT_CONFIG_NOSYSTEM', '1'),
                        ('GIT_AUTHOR_NAME', 'HM01 Test'), ('GIT_AUTHOR_EMAIL', 'hm01@example.invalid'),
                        ('GIT_COMMITTER_NAME', 'HM01 Test'), ('GIT_COMMITTER_EMAIL', 'hm01@example.invalid')):
        monkeypatch.setenv(name, value)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, path, text, message):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    """A small repository with the builder's allowlist inputs; main, then a feature branch with two commits."""
    path = tmp_path / 'repo'
    for name in COPIED:
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path / name)
    git(path, 'init', '-q', '-b', 'main')
    git(path, 'add', '-A')
    git(path, 'commit', '-q', '-m', 'base')
    git(path, 'switch', '-q', '-c', 'feature')
    commit(path, 'notes/one.txt', 'one\n', 'one')
    commit(path, 'notes/two.txt', 'two\n', 'two')
    return path


def stand_in_text():
    return STAND_IN.replace('{python}', sys.executable).replace('{version}', PINNED)


def stand_in(directory, *, findings=(), stderr='', status=0, version=PINNED, digest=True):
    directory.mkdir(parents=True, exist_ok=True)
    tool = directory / 'gitleaks'
    tool.write_text(stand_in_text())
    tool.chmod(0o700)
    (directory / 'findings.json').write_text(json.dumps(list(findings)))
    (directory / 'stderr').write_text(stderr)
    (directory / 'status').write_text(str(status))
    (directory / 'version').write_text(version)
    if digest:
        (directory / 'gitleaks.sha256').write_text(hashlib.sha256(tool.read_bytes()).hexdigest())
    return directory


def calls(directory):
    path = directory / 'calls.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def normalized(argv):
    """Paths in an invocation replaced by their role, so the builder's and the precheck's can be compared."""
    result, index = [], 0
    while index < len(argv):
        item = argv[index]
        if item in ('--config', '--gitleaks-ignore-path', '--report-path'):
            result += [item, '<' + item.strip('-') + '>']
            index += 2
            continue
        result.append(item)
        index += 1
    result[1] = '<target>'
    return result


def test_branch_commits_with_the_builders_allowlist_and_flags(repo, tmp_path, capsys, log_scan):
    tools = stand_in(tmp_path / 'tools')
    assert precheck.main(['--tools', str(tools), '--repo', str(repo), '--base', 'main', '--head', 'feature']) == 0
    out = capsys.readouterr().out
    assert 'commits' in out and ': 2' in out and 'result: OK, 0 findings' in out
    merge_base, head = git(repo, 'merge-base', 'main', 'feature'), git(repo, 'rev-parse', 'feature')
    (call,) = calls(tools)
    argv = call['argv']
    assert argv[:2] == ['git', str(repo)] and argv[-1] == f'--log-opts=--full-history -m {merge_base}..{head}'
    builder = precheck.load_supply_chain(ROOT)
    assert call['config'] == builder.gitleaks_config() == precheck.load_supply_chain(repo).gitleaks_config()
    # The builder's own history invocation, recorded by the same stand-in.
    private = tmp_path / 'builder'
    private.mkdir()
    builder.secret_scan(tools / 'gitleaks', 'git', repo, private, 'history', {'PATH': '/usr/bin:/bin'})
    gate = calls(tools)[1]['argv']
    assert gate[-1] == '--log-opts=--all --full-history -m'
    assert normalized(argv)[:-1] == normalized(gate)[:-1] + ['--exit-code', '0']


def test_the_scan_leaves_the_git_index_alone(repo, tmp_path):
    """Its git status runs without optional locks: a stat-dirty checkout does not get its index refreshed."""
    os.utime(repo / 'notes/one.txt', ns=(1_000_000_000, 1_000_000_000))
    index = (repo / '.git/index').read_bytes()
    assert precheck.main(['--tools', str(stand_in(tmp_path / 'tools')), '--repo', str(repo), '--base', 'main',
                          '--head', 'feature']) == 0
    assert (repo / '.git/index').read_bytes() == index


def test_no_new_commit_scans_nothing(repo, tmp_path, capsys):
    tools = stand_in(tmp_path / 'tools')
    assert precheck.main(['--tools', str(tools), '--repo', str(repo), '--base', 'feature', '--head', 'feature']) == 0
    assert calls(tools) == [] and 'result: OK, 0 findings' in capsys.readouterr().out


def test_findings_are_listed_without_values(repo, tmp_path, capsys):
    head = git(repo, 'rev-parse', 'feature')
    finding = {'RuleID': 'generic-api-key', 'File': 'notes/two.txt', 'StartLine': 1, 'Commit': head,
               'Secret': 'REDACTED', 'Match': 'key = REDACTED', 'Author': 'HM01 Test', 'Email': 'hm01@example.invalid',
               'Message': 'commit message canary', 'Fingerprint': head + ':notes/two.txt:generic-api-key:1'}
    tools = stand_in(tmp_path / 'tools', findings=[finding], stderr='WRN leaks found: 1\n')
    assert precheck.main(['--tools', str(tools), '--repo', str(repo), '--base', 'main', '--head', 'feature']) == 1
    out = capsys.readouterr().out
    assert f'commits: generic-api-key notes/two.txt:1 commit {head[:12]}' in out and '1 finding(s)' in out
    for hidden in ('REDACTED', 'HM01 Test', 'example.invalid', 'canary', 'leaks found'):
        assert hidden not in out


@pytest.mark.parametrize('broken', ['no digest', 'other digest', 'other version', 'status', 'stderr', 'report'])
def test_an_unverifiable_scan_closes(repo, tmp_path, capsys, broken):
    tools = stand_in(tmp_path / 'tools', digest=broken != 'no digest',
                     version=PINNED + '-other' if broken == 'other version' else PINNED,
                     status=1 if broken == 'status' else 0,
                     stderr='stderr-canary REDACTED\n' if broken == 'stderr' else '')
    if broken == 'other digest':
        (tools / 'gitleaks.sha256').write_text('0' * 64)
    if broken == 'report':
        (tools / 'findings.json').write_text('{"not": "a list"}')
    assert precheck.main(['--tools', str(tools), '--repo', str(repo), '--base', 'main', '--head', 'feature']) == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'secret precheck unavailable' in captured.err and 'canary' not in captured.err
    if broken in ('no digest', 'other digest', 'other version'):
        assert calls(tools) == []  # never run before its check


def test_full_also_runs_the_builders_tree_and_history_scans(repo, tmp_path, capsys):
    tools = stand_in(tmp_path / 'tools')
    assert precheck.main(['--tools', str(tools), '--repo', str(repo), '--base', 'main', '--head', 'feature',
                          '--full']) == 0
    commits, source, history = (call['argv'] for call in calls(tools))
    assert commits[0] == 'git' and source[0] == 'dir' and Path(source[1]).name == 'source-files'
    assert history[:2] == ['git', str(repo)] and history[-1] == '--log-opts=--all --full-history -m'
    assert 'also the builder scans' in capsys.readouterr().out


def archive(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                info.type, info.linkname = tarfile.SYMTYPE, '/bin/sh'
                tar.addfile(info)
    return buffer.getvalue()


def pin_archive(repo, data):
    path = repo / 'packaging/scanner-pins.json'
    pins = json.loads(path.read_text())
    pins['gitleaks']['sha256'] = hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(pins))


def test_install_takes_only_the_pinned_archive(repo, tmp_path, capsys):
    tool = stand_in_text().encode()
    good = archive([('LICENSE', b'MIT\n', 'file'), ('gitleaks', tool, 'file')])
    tarball = tmp_path / 'gitleaks.tar.gz'
    tarball.write_bytes(good)
    # The real pin names the real archive: a different archive is refused and nothing is installed.
    assert precheck.main(['install', str(tmp_path / 'refused'), '--tarball', str(tarball), '--repo', str(repo)]) == 2
    assert not (tmp_path / 'refused' / 'gitleaks').exists()
    pin_archive(repo, good)
    assert precheck.main(['install', str(tmp_path / 'tools'), '--tarball', str(tarball), '--repo', str(repo)]) == 0
    installed = tmp_path / 'tools' / 'gitleaks'
    assert installed.read_bytes() == tool and installed.stat().st_mode & 0o777 == 0o700
    assert (tmp_path / 'tools' / 'gitleaks.sha256').read_text() == hashlib.sha256(tool).hexdigest()
    for members in ([('gitleaks', b'', 'link')], [('other', tool, 'file')]):
        data = archive(members)
        tarball.write_bytes(data)
        pin_archive(repo, data)
        assert precheck.main(['install', str(tmp_path / 'bad'), '--tarball', str(tarball), '--repo', str(repo)]) == 2
    assert 'install failed' in capsys.readouterr().err


def test_loading_the_builder_gate_leaves_modules_and_the_checkout_as_they_were(repo, monkeypatch):
    before = sys.modules.get('validate')
    module = precheck.load_supply_chain(ROOT)
    assert sys.modules.get('validate') is before
    assert module.ROOT == ROOT and module.pins()['gitleaks']['version'] == PINNED
    with pytest.raises(precheck.Closed):
        module.version_for('odoo')  # the stand-in for packaging/validate.py refuses
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)  # as a plain `python3 scripts/secret_precheck.py` run
    assert precheck.load_supply_chain(repo).ROOT == repo.resolve() and sys.dont_write_bytecode is False
    assert not (repo / 'packaging/__pycache__').exists()  # no bytecode written into the scanned checkout


def test_runs_as_a_script(repo, tmp_path):
    tools = stand_in(tmp_path / 'tools')
    result = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/secret_precheck.py'), '--tools', str(tools),
                             '--repo', str(repo), '--base', 'main', '--head', 'feature', '--json'],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['commits'] == 2 and report['findings'] == [] and report['gitleaks'] == PINNED
