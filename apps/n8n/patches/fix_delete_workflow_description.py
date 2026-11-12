"""Build-time patch for pinned n8n-mcp 2.96.2: n8n_delete_workflow's description names the way out of a refusal.

n8n refuses to delete a published (active) workflow, but the pinned upstream describes the tool only as "Permanently
delete a workflow. This action cannot be undone.", so a model that follows the description meets the refusal and has to
guess. The PaaS woow-mcp-server (apps/n8n/n8n_mcp_admin/upstream_result_patch.py) adds one sentence; this is the same
edit to the same file with the same digests. Only the description text of `dist/mcp/tools-n8n-manager.js` changes: the
input schema, the annotations, the write gating and every other tool are untouched. Unreleased (0.4.12 line).

    python3 apps/n8n/patches/fix_delete_workflow_description.py [path/to/tools-n8n-manager.js]
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

TARGET = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp/dist/mcp/tools-n8n-manager.js'
PINNED = '28d54ea6a3001678fd510542c82c04c26b2ff3b55b7db63b630800e82e02191f'
PATCHED = 'e31acfb4d4344704786d4a69fc4a2a0a6b784a265df3474073dd5bc5951efac7'

OLD = 'description: `Permanently delete a workflow. This action cannot be undone.`,'
NEW = ('description: `Permanently delete a workflow. This action cannot be undone. '
       'A published (active) workflow cannot be deleted: deactivate it first with n8n_update_partial_workflow '
       '(operations: [{type: "deactivateWorkflow"}]), then delete it.`,')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    text = source.decode()
    if text.count(OLD) != 1:
        raise SystemExit('tools-n8n-manager.js: the reviewed n8n_delete_workflow description was not found exactly once')
    return text.replace(OLD, NEW).encode()


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else TARGET
    source = target.read_bytes()
    if digest(source) == PATCHED:
        print(f'{target}: already patched')
        return 0
    if digest(source) != PINNED:
        raise SystemExit(f'{target}: not the pinned n8n-mcp 2.96.2 file (sha256 {digest(source)}); review required')
    result = patched(source)
    if digest(result) != PATCHED:
        raise SystemExit(f'{target}: patch result {digest(result)} is not the reviewed digest')
    target.write_bytes(result)
    print(f'{target}: patched')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
