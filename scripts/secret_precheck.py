#!/usr/bin/env python3
"""Secret precheck of a branch's new commits with the builder's own scanner and allowlist (multi-profile plan, rule 4).

    python3 scripts/secret_precheck.py install DIR [--tarball FILE]
    python3 scripts/secret_precheck.py [--tools DIR] [--repo DIR] [--base REF] [--head REF] [--full]

install: the gitleaks pinned in packaging/scanner-pins.json (version, archive URL and archive SHA-256), downloaded or
taken from --tarball, verified against the pin, unpacked to DIR/gitleaks with its own digest in DIR/gitleaks.sha256
(as packaging/install_scanners.py does on the builder).

scan (default): checks DIR/gitleaks against DIR/gitleaks.sha256 and its version against the pin, then scans every
commit in merge-base(--base, --head)..--head (default origin/claude-delivery..HEAD) with gitleaks git and the same
configuration as the builder's supply-chain gate: packaging/supply_chain.py gitleaks_config() (default rules plus only
the reviewed exact values of packaging/secret-triage.json) and its source/history flags (redacted, zero tolerance).
--full also runs the builder's two scans themselves: the HEAD tree and the whole history.

A finding is printed as rule, file, line and commit only; the report (redacted by gitleaks) stays in a private
temporary directory. Exit 0: no finding; 1: findings; 2: the precheck could not run (no verified scanner, git or
scanner failure, scanner output on stderr, which the builder gate also refuses). Uncommitted changes are not scanned:
commit first. A finding is fixed by changing the data (tests/fixtures/owner_defaults/README.md); only a new ledger
digest goes through packaging/secret-triage.json with an independent review and the owner's approval.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import urllib.request

DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_TOOLS = Path(os.environ.get('WOOW_SECRET_PRECHECK_TOOLS') or Path.home() / '.cache/woow-secret-precheck')
MAX_ARCHIVE = 200 * 1024 * 1024


class Closed(RuntimeError):
    """The precheck cannot vouch for a result; never shows scanner output."""


def load_supply_chain(root):
    """packaging/supply_chain.py of this checkout under a private name. Its version_for import (packaging/validate.py,
    which needs PyYAML) is a stand-in that refuses to run: the precheck uses only pins(), gitleaks_config(),
    scanner_env() and regular_files(). sys.modules is left as it was, and no bytecode is written into the checkout."""
    stand_in = types.ModuleType('validate')

    def version_for(product):
        raise Closed('version_for is not part of the secret precheck')

    stand_in.version_for = version_for
    previous = sys.modules.get('validate')
    sys.modules['validate'] = stand_in
    bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location('woow_secret_precheck_supply_chain',
                                                      Path(root) / 'packaging/supply_chain.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ValueError, KeyError) as error:
        raise Closed(f'packaging/supply_chain.py unavailable ({type(error).__name__})') from None
    finally:
        sys.dont_write_bytecode = bytecode
        if previous is None:
            sys.modules.pop('validate', None)
        else:
            sys.modules['validate'] = previous
    return module


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(command, *, cwd=None, env=None, timeout=900):
    try:
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Closed(f'{Path(str(command[0])).name} could not run') from None


def git(root, *args):
    result = run(['git', '-c', f'safe.directory={root}', '-C', str(root), *args], timeout=120)
    if result.returncode != 0:
        raise Closed('git ' + ' '.join(args[:2]) + ' failed')
    return result.stdout.decode().strip()


# ---- install ----

def download(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read(MAX_ARCHIVE + 1)
    except OSError:
        raise Closed('download failed') from None
    if len(data) > MAX_ARCHIVE:
        raise Closed('archive too large')
    return data


def install(root, destination, tarball=None):
    pin = load_supply_chain(root).pins()['gitleaks']
    data = Path(tarball).read_bytes() if tarball else download(pin['url'])
    if sha256(data) != pin['sha256']:
        raise Closed('archive SHA-256 differs from packaging/scanner-pins.json')
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            member = archive.getmember('gitleaks')
            if not member.isfile():
                raise Closed('gitleaks is not a regular file in the archive')
            payload = archive.extractfile(member).read()
    except (tarfile.TarError, KeyError, OSError):
        raise Closed('unreadable scanner archive') from None
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination / '.gitleaks.partial'
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)
    os.replace(temporary, destination / 'gitleaks')
    (destination / 'gitleaks.sha256').write_text(sha256(payload))
    verified(destination, pin)
    return destination / 'gitleaks'


def verified(directory, pin):
    """The installed gitleaks after checking its recorded digest and its version against the pin."""
    tool, digest = Path(directory) / 'gitleaks', Path(directory) / 'gitleaks.sha256'
    if not tool.is_file() or not digest.is_file():
        raise Closed(f'no installed gitleaks in {directory}; run: secret_precheck.py install {directory}')
    if sha256(tool.read_bytes()) != digest.read_text().strip():
        raise Closed('gitleaks differs from its recorded digest; reinstall it')
    result = run([str(tool), 'version'], timeout=60)
    if result.returncode != 0 or result.stdout.decode().strip() != pin['version']:
        raise Closed(f"gitleaks is not the pinned version {pin['version']}")
    return tool


# ---- scan ----

def command(tool, mode, target, private, label, log_opts=None):
    """The builder's source/history invocation (supply_chain.secret_scan), with --exit-code 0 so that only the report
    decides (a non-zero status is then always a scanner failure) and, for git, the commits to scan."""
    report = private / (label + '.json')
    argv = [str(tool), mode, str(target), '--config', str(private / 'gitleaks.toml'),
            '--gitleaks-ignore-path', str(private / 'empty-ignore'), '--ignore-gitleaks-allow',
            '--max-decode-depth', '5', '--max-archive-depth', '5', '--max-target-megabytes', '0',
            '--log-level', 'warn', '--redact=100', '--no-banner', '--report-format', 'json',
            '--report-path', str(report),
            '--exit-code', '0']
    if log_opts is not None:
        argv.append('--log-opts=' + log_opts)
    return argv, report


def scan(tool, mode, target, private, label, env, log_opts=None):
    argv, report = command(tool, mode, target, private, label, log_opts)
    result = run(argv, cwd=private, env=env)
    if result.returncode != 0:
        raise Closed(f'gitleaks failed on the {label} scan (status {result.returncode})')
    try:
        findings = json.loads(report.read_text())
    except (OSError, ValueError):
        raise Closed(f'no {label} report') from None
    if not isinstance(findings, list):
        raise Closed(f'invalid {label} report')
    if result.stderr and not findings:
        # With findings gitleaks warns "leaks found" there; without, any warning also fails the builder gate.
        raise Closed(f'gitleaks wrote {len(result.stderr)} bytes to stderr on a clean {label} scan; the builder '
                     'gate refuses that too')
    return [{'scan': label, 'rule': str(item.get('RuleID')), 'file': str(item.get('File')),
             'line': item.get('StartLine'), 'commit': str(item.get('Commit') or '')[:12]} for item in findings]


def precheck(root, tools, base, head, full=False):
    root = Path(root).resolve()
    supply_chain = load_supply_chain(root)
    pin = supply_chain.pins()['gitleaks']
    tool = verified(tools, pin)
    head_commit = git(root, 'rev-parse', '--verify', head + '^{commit}')
    merge_base = git(root, 'merge-base', base, head_commit)
    commits = int(git(root, 'rev-list', '--count', f'{merge_base}..{head_commit}'))
    dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=all'))
    findings = []
    with tempfile.TemporaryDirectory(prefix='woow-secret-precheck-') as temporary:
        private = Path(temporary)
        os.chmod(private, 0o700)
        (private / 'gitleaks.toml').write_text(supply_chain.gitleaks_config())
        (private / 'empty-ignore').write_text('')
        env = {**supply_chain.scanner_env(private), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'safe.directory', 'GIT_CONFIG_VALUE_0': str(root)}
        if commits:
            findings += scan(tool, 'git', root, private, 'commits', env,
                             f'--full-history -m {merge_base}..{head_commit}')
        if full:
            exported = private / 'source.tar'
            git(root, 'archive', '--format=tar', '--output=' + str(exported), head_commit)
            with tarfile.open(exported) as archive:
                supply_chain.regular_files(archive, private / 'source-files')
            findings += scan(tool, 'dir', private / 'source-files', private, 'source', env)
            findings += scan(tool, 'git', root, private, 'history', env, '--all --full-history -m')
    return {'repo': str(root), 'gitleaks': pin['version'], 'base': base, 'head': head_commit, 'merge_base': merge_base,
            'commits': commits, 'full': full, 'uncommitted_changes': dirty, 'findings': findings}


def text(report):
    lines = [f"secret precheck: {report['repo']}",
             f"  gitleaks {report['gitleaks']} (pinned, verified); "
             'allowlist: packaging/supply_chain.py gitleaks_config()',
             f"  commits {report['merge_base'][:12]}..{report['head'][:12]} ({report['base']}): {report['commits']}"]
    if report['full']:
        lines.append('  also the builder scans: HEAD tree and whole history')
    if report['uncommitted_changes']:
        lines.append('  note: uncommitted changes are not scanned; commit them and run again')
    lines += [f"  {item['scan']}: {item['rule']} {item['file']}:{item['line']}"
              + (f" commit {item['commit']}" if item['commit'] else '') for item in report['findings']]
    count = len(report['findings'])
    lines.append('  result: ' + ('OK, 0 findings' if not count else f'{count} finding(s)'))
    return '\n'.join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['install']:
        parser = argparse.ArgumentParser(prog='secret_precheck.py install')
        parser.add_argument('directory', type=Path)
        parser.add_argument('--tarball', type=Path)
        parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
        args = parser.parse_args(argv[1:])
        try:
            tool = install(args.repo, args.directory, args.tarball)
        except (Closed, ValueError) as error:  # ValueError: supply_chain.Closed (pins or allowlist refused)
            print(f'secret precheck install failed: {error}', file=sys.stderr)
            return 2
        print(f'installed the pinned gitleaks: {tool}')
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--tools', type=Path, default=DEFAULT_TOOLS)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--base', default='origin/claude-delivery')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--full', action='store_true', help="also the builder's HEAD tree and whole-history scans")
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = precheck(args.repo, args.tools, args.base, args.head, args.full)
    except (Closed, ValueError) as error:  # ValueError: supply_chain.Closed (pins or allowlist refused)
        print(f'secret precheck unavailable: {error}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=1) if args.json else text(report))
    return 1 if report['findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
