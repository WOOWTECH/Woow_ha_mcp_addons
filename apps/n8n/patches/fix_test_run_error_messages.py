"""Build-time patch of the pinned n8n-mcp 2.92.1: test-run errors keep n8n's own message.

0.2.3: n8n-mcp 2.91.0 -> 2.92.1. ``dist/mcp/handlers-n8n-manager.js`` of the published 2.92.1 tarball is byte-identical
to 2.91.0's (sha256 PINNED below, recomputed from n8n-mcp-2.92.1.tgz), so ``handleTestRunError`` still drops n8n's own
message and this patch, its reviewed block and both digests are unchanged.

Problem (test VM 2026-10-16)
----------------------------
``handleTestRunError`` in ``dist/mcp/handlers-n8n-manager.js`` (every ``n8n_evaluations`` action) answers a 403 with a
fixed "the API key lacks testRun scopes" hint and drops n8n's own reason, e.g. "Evaluations are not available on your
plan"; the 402, 409 and 404 hints drop it the same way. The owner decided on 2026-10-15 that backend errors reach the
client with the backend's own text.

Fix
---
Each fixed hint of ``handleTestRunError`` is followed by `` n8n: <n8n's message>`` (the N8nApiError message: n8n's JSON
``message``, else axios' text) when there is one and the hint does not already contain it. Nothing else changes.

Applied by apps/n8n/Dockerfile after ``npm ci`` and by packaging/unit.sh; apps/n8n/backend_policy.cjs refuses to start the
child unless the file has the PATCHED digest below, so an unpatched or altered package fails closed. Idempotent: an
already patched file is left as it is; any other content is refused.

    python3 apps/n8n/patches/fix_test_run_error_messages.py [path/to/handlers-n8n-manager.js]
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

TARGET = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp/dist/mcp/handlers-n8n-manager.js'
PINNED = '0d99e10ec1eb9a6e4d78726636aa79f52eb4f3862be506785b794f1aeb9608cc'  # n8n-mcp 2.92.1 (and 2.91.0) as published
PATCHED = '5b8205754d24e8c6b2d001d4b04e6c0e408d5037215668a75049ce932d6d985d'  # the digest backend_policy.cjs checks

OLD = '''    if (error instanceof n8n_errors_1.N8nApiError) {
        if (error.statusCode === 402) {
            return { success: false, error: TEST_RUN_QUOTA_HINT, code: error.code };
        }
        if (error.statusCode === 403) {
            return { success: false, error: options.scopeHint, code: error.code };
        }
        if (error.statusCode === 409 && options.conflictHint) {
            return { success: false, error: options.conflictHint, code: error.code };
        }
        if (error.statusCode === 404 || error.statusCode === 405) {
            const gate = await testRunRouteGate(error.statusCode, context, options);
            if (gate) {
                return { success: false, error: gate, code: error.code };
            }
        }
        if (error.statusCode === 404) {
            return { success: false, error: options.notFoundHint, code: error.code };
        }
'''
NEW = '''    if (error instanceof n8n_errors_1.N8nApiError) {
        // PATCH(woowtech 0.2.2): every fixed hint also carries n8n's own message (owner decision 2026-10-15: backend
        // errors reach the client with the backend's text), e.g. "Evaluations are not available on your plan".
        const own = typeof error.message === 'string' ? error.message.trim() : '';
        const withN8n = (hint) => own && !String(hint).includes(own) ? `${hint} n8n: ${own}` : hint;
        if (error.statusCode === 402) {
            return { success: false, error: withN8n(TEST_RUN_QUOTA_HINT), code: error.code };
        }
        if (error.statusCode === 403) {
            return { success: false, error: withN8n(options.scopeHint), code: error.code };
        }
        if (error.statusCode === 409 && options.conflictHint) {
            return { success: false, error: withN8n(options.conflictHint), code: error.code };
        }
        if (error.statusCode === 404 || error.statusCode === 405) {
            const gate = await testRunRouteGate(error.statusCode, context, options);
            if (gate) {
                return { success: false, error: withN8n(gate), code: error.code };
            }
        }
        if (error.statusCode === 404) {
            return { success: false, error: withN8n(options.notFoundHint), code: error.code };
        }
'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    text = source.decode()
    if text.count(OLD) != 1:
        raise SystemExit('handlers-n8n-manager.js: the reviewed handleTestRunError block was not found exactly once')
    return text.replace(OLD, NEW).encode()


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else TARGET
    source = target.read_bytes()
    if digest(source) == PATCHED:
        print(f'{target}: already patched')
        return 0
    if digest(source) != PINNED:
        raise SystemExit(f'{target}: not the pinned n8n-mcp 2.92.1 file (sha256 {digest(source)}); review required')
    result = patched(source)
    if digest(result) != PATCHED:
        raise SystemExit(f'{target}: patch result {digest(result)} is not the reviewed digest')
    target.write_bytes(result)
    print(f'{target}: patched')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
