"""Correct two pinned n8n-mcp 2.96.2 workflow issue output-schema types.

The child emits object-valued ``details`` for warnings/errors, but its
published tools.js calls both fields strings. Exact full-file hashes prevent
silently patching an unreviewed npm package or source change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp'
VERSION = '2.96.2'
ORIGINAL = 'acb4d2a3ec74b5f2b41d327a93340a0f9a799e99947656afd010a76390fb10cb'
PATCHED = 'e30bddb3967661d36ae5dd8c6b5eb8b7e1b56f6053b2bb972543d7bbc4d57803'
BEFORE = b"details: { type: 'string' }"
AFTER = b"details: { type: 'object' }"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch(package: Path = PACKAGE) -> bool:
    if json.loads((package / 'package.json').read_text())['version'] != VERSION:
        raise ValueError('Unreviewed n8n-mcp version')
    target = package / 'dist/mcp/tools.js'
    if target.is_symlink() or not target.is_file():
        raise ValueError('Expected regular upstream tools.js')
    original = target.read_bytes()
    current = digest(original)
    if current == PATCHED:
        return False
    if current != ORIGINAL or original.count(BEFORE) != 2:
        raise ValueError('Unreviewed n8n-mcp tools.js bytes')
    changed = original.replace(BEFORE, AFTER)
    if digest(changed) != PATCHED:
        raise ValueError('Patched tools.js digest mismatch')
    target.write_bytes(changed)
    return True


def main(argv: list[str]) -> int:
    package = Path(argv[1]) if len(argv) > 1 else PACKAGE
    print('n8n workflow output schema:', 'patched' if patch(package) else 'verified')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
