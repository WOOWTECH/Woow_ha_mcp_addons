"""Move both n8n-mcp 2.96.2 FTS probes to connection-local temp schema.

The main catalog is never changed by the probe, including if the process dies
between CREATE and DROP. Explicit temp qualification also prevents the DROP
from touching an existing main.test_fts5. Refuse all unreviewed source bytes.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

TARGET = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp/dist/database/database-adapter.js'
PINNED = 'ce43947010501c11eb4fd9fede6ed20e2202233dc1954c8de1345f20df936388'
PATCHED = 'b0bfa44960b9109b383b2c467ed9f1155f38d972a2c5ef7b403ce0caeb9e060c'
OLD = '''            this.exec("CREATE VIRTUAL TABLE IF NOT EXISTS test_fts5 USING fts5(content);");
            this.exec("DROP TABLE IF EXISTS test_fts5;");'''
NEW = '''            this.exec("CREATE VIRTUAL TABLE IF NOT EXISTS temp.test_fts5 USING fts5(content);");
            this.exec("DROP TABLE IF EXISTS temp.test_fts5;");'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    text = source.decode('utf-8')
    if text.count(OLD) != 2:
        raise SystemExit('database-adapter.js: expected exactly two reviewed FTS probe blocks')
    return text.replace(OLD, NEW).encode('utf-8')


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else TARGET
    source = target.read_bytes()
    if digest(source) == PATCHED:
        print(f'{target}: already patched')
        return 0
    if digest(source) != PINNED:
        raise SystemExit(f'{target}: not pinned n8n-mcp 2.96.2 (sha256 {digest(source)}); review required')
    result = patched(source)
    if digest(result) != PATCHED:
        raise SystemExit(f'{target}: patch result {digest(result)} is not the reviewed digest')
    target.write_bytes(result)
    print(f'{target}: patched')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
