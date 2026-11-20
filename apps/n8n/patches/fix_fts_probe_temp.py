"""Harden n8n-mcp 2.96.2 FTS probes and persistent catalog adapter selection.

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
PREVIOUS = 'b0bfa44960b9109b383b2c467ed9f1155f38d972a2c5ef7b403ce0caeb9e060c'
PATCHED = '2219a87a9f34dfceba0d6008e7218bc11a1a1ed4351f487c470c4e50fe528505'
OLD = '''            this.exec("CREATE VIRTUAL TABLE IF NOT EXISTS test_fts5 USING fts5(content);");
            this.exec("DROP TABLE IF EXISTS test_fts5;");'''
NEW = '''            this.exec("CREATE VIRTUAL TABLE IF NOT EXISTS temp.test_fts5 USING fts5(content);");
            this.exec("DROP TABLE IF EXISTS temp.test_fts5;");'''

FALLBACK_OLD = """    catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);"""
FALLBACK_NEW = """    catch (error) {
        if (process.env.NODE_DB_PATH !== undefined && process.env.NODE_DB_PATH !== ':memory:') {
            throw new Error('persistent catalog requires native SQLite');
        }
        const errorMessage = error instanceof Error ? error.message : String(error);"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    text = source.decode('utf-8')
    if digest(source) == PINNED:
        if text.count(OLD) != 2:
            raise SystemExit('database-adapter.js: expected exactly two reviewed FTS probe blocks')
        text = text.replace(OLD, NEW)
    elif digest(source) != PREVIOUS:
        raise SystemExit('database-adapter.js: source is not reviewed')
    if text.count(FALLBACK_OLD) != 1:
        raise SystemExit('database-adapter.js: expected exactly one reviewed fallback block')
    return text.replace(FALLBACK_OLD, FALLBACK_NEW).encode('utf-8')


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else TARGET
    source = target.read_bytes()
    if digest(source) == PATCHED:
        print(f'{target}: already patched')
        return 0
    if digest(source) not in (PINNED, PREVIOUS):
        raise SystemExit(f'{target}: not pinned n8n-mcp 2.96.2 (sha256 {digest(source)}); review required')
    result = patched(source)
    if digest(result) != PATCHED:
        raise SystemExit(f'{target}: patch result {digest(result)} is not the reviewed digest')
    target.write_bytes(result)
    print(f'{target}: patched')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
