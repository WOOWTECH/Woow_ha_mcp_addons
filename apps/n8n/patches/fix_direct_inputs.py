"""Guarded native execute_workflow compatibility, after the backend-message patch.

Start with upstream's untagged inputs. Retry once only for the native SDK's exact
pre-dispatch inputs.type discriminator validation rejection. Never retry transport,
authorization or execution failures. Remember successful formats by official client
identity (including its credential/instance lifetime), not by process or public API
client. Unknown validation formats fail unchanged, without speculative dispatch.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

PINNED = '6cd673423e829902f3e56de66afe90f7e2196d7ef76cca02551a20eee03ae2eb'
PATCHED = '491d6dd15f39941bcda742c7da03cd6b7e4ffc3ca630a88eb88a9f6d215d246a'
TARGET = Path(__file__).resolve().parents[1] / 'node_modules/n8n-mcp/dist/mcp/handlers-n8n-manager.js'
REPLACEMENTS = (
    ("const OFFICIAL_TEST_ACTION = 'test_workflow';",
     """// PATCH(woowtech): native input formats belong to an official client, never a tenant-global flag.
const woowDirectInputFormats = new WeakMap();
const OFFICIAL_TEST_ACTION = 'test_workflow';"""),
    ("""            const response = await routeOfficial(['execute_workflow'], {
                workflowId: input.workflowId,
                executionMode: input.executionMode ?? 'manual',
                ...(directTriggerNode ? { triggerNodeName: directTriggerNode } : {}),
                ...(inputs ? { inputs } : {}),
            }, false, 'direct');""",
     """            const nativeClient = (0, official_mcp_access_1.getOfficialMcpClient)(context);
            const knownFormat = nativeClient ? woowDirectInputFormats.get(nativeClient) : undefined;
            const sameClient = () => nativeClient && nativeClient === (0, official_mcp_access_1.getOfficialMcpClient)(context);
            const execute = (tagged) => routeOfficial(['execute_workflow'], {
                workflowId: input.workflowId,
                executionMode: input.executionMode ?? 'manual',
                ...(directTriggerNode ? { triggerNodeName: directTriggerNode } : {}),
                ...(inputs ? { inputs: tagged ? {
                    type: 'chatInput' in inputs ? 'chat' : 'formData' in inputs ? 'form' : 'webhook',
                    ...inputs,
                } : inputs } : {}),
            }, false, 'direct');
            const missingInputTag = (result) => {
                const prefix = 'Input validation error: Invalid arguments for tool execute_workflow: ';
                if (result.success !== false || result.code !== 'INVALID_ARGS' ||
                    typeof result.error !== 'string' || !result.error.startsWith(prefix)) return false;
                try {
                    const issues = JSON.parse(result.error.slice(prefix.length));
                    if (!Array.isArray(issues) || issues.length !== 1) return false;
                    const issue = issues[0];
                    const discriminatorIssue = issue?.code === 'invalid_union_discriminator' ||
                        (issue?.code === 'invalid_union' && issue.discriminator === 'type' &&
                         issue.note === 'No matching discriminator' &&
                         Array.isArray(issue.errors) && issue.errors.length === 0);
                    return discriminatorIssue &&
                        JSON.stringify(issue.path) === '["inputs","type"]' &&
                        Array.isArray(issue.options) &&
                        JSON.stringify([...issue.options].sort()) === '["chat","form","webhook"]';
                } catch { return false; }
            };
            let response = await execute(knownFormat === true);
            if (inputs && knownFormat === undefined && sameClient()) {
                if (response.success === true) {
                    woowDirectInputFormats.set(nativeClient, false);
                } else if (missingInputTag(response)) {
                    // Validation rejected the first call before execution; no generic write retry.
                    const retry = await execute(true);
                    if (retry.success === true) {
                        if (sameClient()) woowDirectInputFormats.set(nativeClient, true);
                        response = retry;
                    }
                    // Keep the original rejection, including its code/text, if negotiation fails.
                }
            }"""),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched(source: bytes) -> bytes:
    if digest(source) != PINNED:
        raise SystemExit('direct inputs require the reviewed message-patched handler; review required')
    text = source.decode()
    for before, after in REPLACEMENTS:
        if text.count(before) != 1:
            raise SystemExit('direct inputs: reviewed call site not found exactly once')
        text = text.replace(before, after, 1)
    result = text.encode()
    if digest(result) != PATCHED:
        raise SystemExit('direct inputs: patch result is not the reviewed digest')
    return result


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else TARGET
    if target.is_symlink():
        raise SystemExit('direct inputs: expected a regular handler')
    source = target.read_bytes()
    if digest(source) == PATCHED:
        print(f'{target}: already patched')
        return 0
    target.write_bytes(patched(source))
    print(f'{target}: patched')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
