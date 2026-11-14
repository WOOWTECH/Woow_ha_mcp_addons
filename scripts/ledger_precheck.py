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
   Changed runtime files (packages/, apps/) that no ledger lists are named for review, without failing.

Exit 0: no drift; 1: drift (paths listed); 2: the precheck could not run. It writes nothing and prints paths and counts
only. A fast local precheck; tests/test_tool_inventory.py stays the gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

DEFAULT_REPO = Path(__file__).resolve().parents[1]
PATCHES = 'docs/provenance/runtime-patches.json'
SOURCES = 'docs/provenance/runtime-sources.json'
SURFACE = 'docs/tool-surface.json'
LEDGERS = (PATCHES, SOURCES, SURFACE, 'docs/tool-surface.md')
RUNTIME_PREFIXES = ('packages/mcp-admin-core/', 'packages/mcp-admin-ui/src/', 'apps/')
RUNTIME_SUFFIXES = ('.py', '.js', '.cjs', '.mjs')


class Unavailable(RuntimeError):
    pass


def installed_only(path):
    return '/.venv/' in path or '/node_modules/' in path


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


def git(root, *args):
    try:
        result = subprocess.run(['git', '-c', f'safe.directory={root}', '-C', str(root), *args],
                                capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        raise Unavailable('git ' + ' '.join(args[:2]) + ' failed') from None
    return result.stdout


def changed(root, base):
    merge_base = git(root, 'merge-base', base, 'HEAD').strip()
    paths = set(git(root, 'diff', '--name-only', '--no-renames', merge_base).split('\n'))
    paths |= set(git(root, 'ls-files', '--others', '--exclude-standard').split('\n'))
    return merge_base, sorted(path for path in paths if path)


def precheck(root, base):
    root = Path(root).resolve()
    pinned = pins(root)
    report = {'repo': str(root), 'drift': drift(root, pinned)}
    if base is not None:
        merge_base, paths = changed(root, base)
        listed = {path for paths_of in pinned.values() for path in paths_of}
        report['changes'] = {
            'base': base, 'merge_base': merge_base, 'changed_files': len(paths),
            'pinned_changed': sorted(path for path in paths if path in listed),
            'ledgers_changed': sorted(path for path in paths if path in LEDGERS),
            'unlisted_runtime_changed': sorted(
                path for path in paths if path not in listed and path.startswith(RUNTIME_PREFIXES)
                and path.endswith(RUNTIME_SUFFIXES) and not installed_only(path) and '/tests/' not in path),
        }
    report['ok'] = not any(item['drift'] or item['missing'] for item in report['drift'].values())
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
                           ('unlisted_runtime_changed', 'runtime file no ledger lists (review)')):
            lines += [f'    {label}: {path}' for path in changes[key]] or [f'    {label}: none']
    lines.append('  result: ' + ('OK' if report['ok'] else 'DRIFT'))
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
