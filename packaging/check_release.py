"""Manual publication gate: no tokens, HTTP or arbitrary source checkout.

approved_commit is reviewed main content. Only RELEASE-GATES.json may differ
between that commit and the workflow's main SHA, avoiding a self-referential hash.
Protection/required reviewers/namespace ownership remain external admin controls.
"""
import os
from pathlib import Path
import subprocess
import sys

from validate import ROOT, PRODUCTS, VERSION, Invalid, clearance_shape, load, require


def check(product):
    require(product in PRODUCTS, 'product not allowed')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual event required')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'release must run from main')
    gates = load(ROOT / 'RELEASE-GATES.json')
    clearance_shape(gates)
    require(gates['approved_commit'] is not None, 'no approved source commit')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(head == os.environ.get('GITHUB_SHA'), 'checkout differs from dispatched main SHA')
    approved = gates['approved_commit']
    require(subprocess.run(['git', 'merge-base', '--is-ancestor', approved, head], check=False).returncode == 0, 'approved source is not main ancestor')
    changed = subprocess.check_output(['git', 'diff', '--name-only', approved, head], text=True).splitlines()
    require(set(changed) <= {'RELEASE-GATES.json'}, 'unreviewed source since approval')
    required = [gates[k] for k in ('source', 'license', 'secret', 'publisher')]
    required += [gates['products'][product][k] for k in ('image', 'ha')]
    for gate in required:
        require(gate['cleared'] is True, 'publication clearance is CLOSED')
        evidence = ROOT / gate['evidence']
        require(evidence.is_file() and not evidence.is_symlink() and evidence.stat().st_size > 100, 'missing reviewed evidence')
        require(subprocess.run(['git', 'ls-files', '--error-unmatch', gate['evidence']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0, 'evidence must be tracked')
    print(f'PASS: approved main source and source/license/secret/publisher/image/HA gates for {product} {VERSION}')


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'product required')
        check(sys.argv[1])
    except Invalid as exc:
        raise SystemExit(str(exc)) from None
