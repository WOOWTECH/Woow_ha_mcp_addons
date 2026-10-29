"""Build-time patch for pinned n8n-mcp 2.96.2: handler failures set MCP isError.

Only an object with success === false sets the flag. Validation valid:false is
still a normal answer; text and structuredContent retain their existing form.
The separate test-run error-message patch remains unchanged. Dockerfile and
packaging/unit.sh apply both patches; backend_policy.cjs requires both digests.

    python3 apps/n8n/patches/fix_tool_result_is_error.py [path/to/server.js]
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

TARGET = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp/dist/mcp/server.js'
PINNED = 'a1237f5cafe34cddcecb85c48bc467c38a443be487a34b0f24c5cbbb343b30e9'
PATCHED = '638b148f91c18d484b8bcede838be1032f82ddd1b3aa53b24cf005325ae3d9f7'

OLD = '''                if (name.startsWith('validate_') && structuredContent !== null) {
                    mcpResponse.structuredContent = structuredContent;
                }
                return mcpResponse;'''
NEW = '''                if (name.startsWith('validate_') && structuredContent !== null) {
                    mcpResponse.structuredContent = structuredContent;
                }
                if (result !== null && typeof result === 'object' && result.success === false) {
                    mcpResponse.isError = true;
                }
                return mcpResponse;'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    text = source.decode()
    if text.count(OLD) != 1:
        raise SystemExit('server.js: the reviewed tool-result block was not found exactly once')
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
