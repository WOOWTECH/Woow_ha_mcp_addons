#!/usr/bin/env python3
"""Read-only precheck of the source digest ledgers, run before every push (multi-profile plan, rule 6 of the slices).

    python3 scripts/ledger_precheck.py [--repo DIR] [--base REF] [--json]

1. Drift: the SHA-256 of every file a ledger pins that this checkout has, compared with the ledger:
   docs/provenance/runtime-patches.json (each patched file and its guarded wheel sources), docs/provenance/
   runtime-sources.json (each vendored file: apps/<product>/vendor/<path>, local_sha256 or upstream_sha256) and
   docs/tool-surface.json (source_digests). A pinned file that only the CI installs provide (apps/*/.venv,
   node_modules) and that is not installed here is counted, not checked.
2. Changes: the files this branch changes against the merge base with --base (default origin/claude-delivery:
   commits, staged, unstaged and untracked files), the ones a ledger pins, and whether a ledger changes too. A pinned
   file changed in a PR has its ledger entry updated in the same PR (docs/tool-surface.json: scripts/tool_inventory.py).
   Runtime files are the image's own code: packages/mcp-admin-core/, packages/mcp-admin-ui/src/ and apps/ (.py, .js,
   .cjs, .mjs; not tests, not installs) and the two packaging files every Dockerfile copies (entrypoint.py,
   management_launcher.py). A changed runtime file no ledger lists is named for review, without failing; a new one
   (added on this branch) fails: the PR that creates a module lists it in runtime-patches.json
   (docs/multi-profile/ledger-tracking.md, rule 1).

Exit 0: no drift and no new unlisted runtime file; 1: drift, a missing pinned file or a new unlisted runtime file (paths
listed); 2: the precheck could not run. It writes nothing in the checkout, not even the git index (git diff refreshes
the index it reads, so it reads a private copy; git runs with --no-optional-locks) and prints paths and counts only.
A fast local precheck; tests/test_tool_inventory.py stays the gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

DEFAULT_REPO = Path(__file__).resolve().parents[1]
PATCHES = 'docs/provenance/runtime-patches.json'
SOURCES = 'docs/provenance/runtime-sources.json'
SURFACE = 'docs/tool-surface.json'
LEDGERS = (PATCHES, SOURCES, SURFACE, 'docs/tool-surface.md')
RUNTIME_PREFIXES = ('packages/mcp-admin-core/', 'packages/mcp-admin-ui/src/', 'apps/')
RUNTIME_SUFFIXES = ('.py', '.js', '.cjs', '.mjs')
RUNTIME_FILES = ('packaging/entrypoint.py', 'packaging/management_launcher.py')  # COPY'd by every apps/*/Dockerfile


class Unavailable(RuntimeError):
    pass


def installed_only(path):
    return '/.venv/' in path or '/node_modules/' in path


def runtime_file(path):
    return path in RUNTIME_FILES or (path.startswith(RUNTIME_PREFIXES) and path.endswith(RUNTIME_SUFFIXES)
                                     and not installed_only(path) and '/tests/' not in path)


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(root, name):
    try:
        return json.loads((root / name).read_text())
    except (OSError, ValueError) as error:
        raise Unavailable(f'{name}: unreadable ({type(error).__name__})') from None


def pins(root):
    """{ledger name: {repository path: expected sha256}}."""
    found = {PATCHES: {}, SOURCES: {}, SURFACE: {}}
    for entry in read_json(root, PATCHES)['patches']:
        found[PATCHES][entry['path']] = entry['sha256']
        found[PATCHES].update(entry.get('guarded_sources') or {})
    for record in read_json(root, SOURCES):
        path = f"apps/{record['product']}/vendor/{record['path']}"
        found[SOURCES][path] = record.get('local_sha256', record['upstream_sha256'])
    found[SURFACE].update(read_json(root, SURFACE)['source_digests'])
    return found


def drift(root, pinned):
    report = {}
    for ledger, paths in pinned.items():
        checked, differing, needs_install, missing = 0, [], 0, []
        for path, digest in sorted(paths.items()):
            target = root / path
            if not target.is_file():
                if installed_only(path):
                    needs_install += 1
                else:
                    missing.append(path)
                continue
            checked += 1
            if sha256(target) != digest:
                differing.append(path)
        report[ledger] = {'checked': checked, 'drift': differing, 'missing': missing, 'needs_install': needs_install}
    return report


def git(root, *args, index=None):
    """git in root; index: a private index file to read (and refresh) instead of the checkout's own."""
    env = None if index is None else {**os.environ, 'GIT_INDEX_FILE': str(index)}
    try:
        result = subprocess.run(['git', '--no-optional-locks', '-c', f'safe.directory={root}', '-C', str(root),
                                 *args], capture_output=True, text=True, timeout=60, check=True, env=env)
    except (OSError, subprocess.SubprocessError):
        raise Unavailable('git ' + ' '.join(args[:2]) + ' failed') from None
    return result.stdout


def changed(root, base):
    """(merge base, every changed path, the paths added on this branch): commits, staged, unstaged and untracked."""
    merge_base = git(root, 'merge-base', base, 'HEAD').strip()
    index = Path(git(root, 'rev-parse', '--git-path', 'index').strip())
    with tempfile.TemporaryDirectory(prefix='ledger-precheck-') as private:
        copy = Path(private) / 'index'
        try:
            shutil.copyfile(index if index.is_absolute() else root / index, copy)
        except OSError:
            raise Unavailable('git index unreadable') from None
        paths = set(git(root, 'diff', '--name-only', '--no-renames', merge_base, index=copy).split('\n'))
        added = set(git(root, 'diff', '--name-only', '--no-renames', '--diff-filter=A', merge_base,
                        index=copy).split('\n'))
    untracked = set(git(root, 'ls-files', '--others', '--exclude-standard').split('\n'))
    return (merge_base, sorted(path for path in paths | untracked if path),
            sorted(path for path in added | untracked if path))


def precheck(root, base):
    root = Path(root).resolve()
    pinned = pins(root)
    report = {'repo': str(root), 'drift': drift(root, pinned)}
    if base is not None:
        merge_base, paths, added = changed(root, base)
        listed = {path for paths_of in pinned.values() for path in paths_of}
        unlisted = [path for path in paths if path not in listed and runtime_file(path)]
        report['changes'] = {
            'base': base, 'merge_base': merge_base, 'changed_files': len(paths),
            'pinned_changed': sorted(path for path in paths if path in listed),
            'ledgers_changed': sorted(path for path in paths if path in LEDGERS),
            'unlisted_runtime_added': sorted(path for path in unlisted if path in added),
            'unlisted_runtime_changed': sorted(path for path in unlisted if path not in added),
        }
    report['drift_ok'] = not any(item['drift'] or item['missing'] for item in report['drift'].values())
    report['ok'] = report['drift_ok'] and not report.get('changes', {}).get('unlisted_runtime_added')
    return report


def text(report):
    lines = [f"ledger precheck: {report['repo']}"]
    for ledger, item in report['drift'].items():
        lines.append(f"  {ledger}: {item['checked']} checked, {len(item['drift'])} drift, "
                     f"{len(item['missing'])} missing, {item['needs_install']} need the CI installs")
        lines += [f'    drift: {path}' for path in item['drift']] + [f'    missing: {path}' for path in item['missing']]
    if 'changes' in report:
        changes = report['changes']
        lines.append(f"  changes against {changes['base']} (merge base {changes['merge_base'][:12]}): "
                     f"{changes['changed_files']} file(s)")
        for key, label in (('pinned_changed', 'pinned by a ledger'), ('ledgers_changed', 'ledger changed'),
                           ('unlisted_runtime_added', 'new runtime file no ledger lists (fails: list it in '
                                                      'runtime-patches.json in this branch)'),
                           ('unlisted_runtime_changed', 'runtime file no ledger lists (review)')):
            lines += [f'    {label}: {path}' for path in changes[key]] or [f'    {label}: none']
    problems = [name for name, bad in (('DRIFT', not report['drift_ok']),
                                       ('UNLISTED', bool(report.get('changes', {}).get('unlisted_runtime_added'))))
                if bad]
    lines.append('  result: ' + (', '.join(problems) or 'OK'))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--base', default='origin/claude-delivery', help="'' for the drift check only")
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = precheck(args.repo, args.base or None)
    except (Unavailable, KeyError, TypeError) as error:
        print(f'ledger precheck unavailable: {error}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=1) if args.json else text(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
