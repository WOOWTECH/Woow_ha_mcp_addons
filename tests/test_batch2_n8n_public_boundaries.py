"""Supplementary isolated fault injection; actual runtime coverage is separate."""
from pathlib import Path
import json
import subprocess

import pytest

from test_batch2_policy import GRAPH

ROOT = Path(__file__).resolve().parents[1]
ENV = {'PATH': '/usr/bin:/bin', 'N8N_MCP_TELEMETRY_DISABLED': 'true',
       'DISABLE_CONSOLE_OUTPUT': 'true', 'LOG_LEVEL': 'error'}


def node(code, *args):
    result = subprocess.run(['node', '-e', code, *args], cwd=ROOT, env=ENV,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('source', ['services/n8n-api-client.js', 'utils/n8n-errors.js',
                                    'mcp/handlers-n8n-manager.js', 'mcp/server.js'])
def test_public_error_guard_precedes_loading(source):
    node(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const read = fs.readFileSync;
const load = Module._load;
let guardedLoads = 0;
Module._load = function(name, ...args) {
    if (/n8n-mcp\/dist\//.test(String(name))) guardedLoads++;
    return load.call(this, name, ...args);
};
fs.readFileSync = function(file, ...args) {
    if (String(file).endsWith(process.argv[1])) return Buffer.from('drift');
    return read.call(this, file, ...args);
};
assert.throws(() => require('./apps/n8n/backend_policy.cjs'), /requires source review/);
assert.equal(guardedLoads, 0, 'guard must precede runtime loading');
''', source)


def test_public_formatter_is_type_only_and_does_not_mutate_raw_errors():
    node(r'''
const assert = require('node:assert/strict');
require('./apps/n8n/backend_policy.cjs');
const errors = require('./apps/n8n/node_modules/n8n-mcp/dist/utils/n8n-errors.js');
for (const [status, code, expected] of [
    [400, 'VALIDATION_ERROR', 'rejected'], [401, 'AUTHENTICATION_ERROR', 'Authentication'],
    [403, 'PUBLISH_FORBIDDEN', 'denied access'], [404, 'NOT_FOUND', 'not found'],
    [429, 'RATE_LIMIT_ERROR', 'rate limit'], [500, 'SERVER_ERROR', 'server error'],
    [599, 'SERVER_ERROR', 'server error'], [undefined, 'NO_RESPONSE', 'No response'],
    [undefined, 'BACKEND_INVALID_RESPONSE', 'invalid response'],
    [418, 'API_ERROR', 'could not be completed'], ['400', 'PRIVATE', 'could not be completed'],
    [true, 'PRIVATE', 'could not be completed'], [NaN, 'PRIVATE', 'could not be completed']]) {
    const error = new errors.N8nApiError('PRIVATE', status, code, {private: 'PRIVATE'});
    for (const key of ['message', 'details', 'stack', 'toString']) {
        Object.defineProperty(error, key, {get() { throw Error('private field read'); }});
    }
    const before = Object.getOwnPropertyDescriptors(error);
    assert(errors.getUserFriendlyErrorMessage(error).includes(expected));
    assert.deepEqual(Object.getOwnPropertyDescriptors(error), before);
}
for (const error of [null, undefined, 'PRIVATE', 42, Symbol('PRIVATE'),
    {statusCode: 404, code: 'NOT_FOUND', toString() { throw Error('stringified'); }}]) {
    assert.equal(errors.getUserFriendlyErrorMessage(error), 'The n8n operation could not be completed.');
}
// The raw mapper/settings parser still sees exact diagnostics internally.
const raw = new errors.N8nValidationError("body/settings Unrecognized key(s) in object: 'saveExecutionProgress' PRIVATE", {private: 'PRIVATE'});
assert.equal(errors.handleN8nApiError(raw), raw);
assert.deepEqual(errors.unknownSettingsKeysNamedBy(raw), ['saveExecutionProgress']);
assert(raw.message.includes('PRIVATE') && raw.details.private === 'PRIVATE');
''')


# Genuine source handlers, injected API failure only; NOT a replacement formatter.
@pytest.mark.parametrize('handler,method,args', [
    ('handleListWorkflows', 'listWorkflows', {'limit': 1}),
    ('handleGetWorkflowMinimal', 'getWorkflow', {'id': 'owned1'}),
    ('handleDeleteWorkflow', 'deleteWorkflow', {'id': 'owned1'}),
    ('handleListFolders', 'listFolders', {'projectId': 'project1'}),
    ('handleCreateFolder', 'createFolder', {'projectId': 'project1', 'name': 'Owned'}),
    ('handleRenameFolder', 'updateFolder', {'projectId': 'project1', 'folderId': 'folder1', 'name': 'Owned'}),
    ('handleCreateWorkflow', 'createWorkflow', GRAPH),
])
def test_genuine_handler_unknown_exceptions_fail_closed(handler, method, args):
    node(r'''
const assert = require('node:assert/strict');
process.env.N8N_API_URL = 'https://owned.invalid';
process.env.N8N_API_KEY = 'INVENTED_KEY';
require('./apps/n8n/backend_policy.cjs');
const root = './apps/n8n/node_modules/n8n-mcp/dist/';
const handlers = require(root + 'mcp/handlers-n8n-manager.js');
const {N8nApiClient} = require(root + 'services/n8n-api-client.js');
const {N8nApiError} = require(root + 'utils/n8n-errors.js');
const [handler, method, argumentSource] = process.argv.slice(1);
const args = JSON.parse(argumentSource);
let calls = 0;
(async () => {
    const poison = new Error('PRIVATE');
    for (const key of ['message', 'details', 'stack', 'toString']) {
        Object.defineProperty(poison, key, {get() { throw Error('PRIVATE getter'); }});
    }
    const aborted = new DOMException('PRIVATE', 'AbortError');
    for (const failure of [new Error('PRIVATE'), poison, 'PRIVATE', null, undefined,
            {message:'PRIVATE', code:'NOT_FOUND'}, aborted]) {
        N8nApiClient.prototype[method] = async () => { calls++; throw failure; };
        const result = await handlers[handler](args);
        assert.deepEqual(Object.keys(result).sort(), ['code','error','success']);
        assert.equal(result.success, false);
        assert.equal(result.code, 'BACKEND_UNAVAILABLE');
        assert(!JSON.stringify(result).includes('PRIVATE'));
    }
    assert.equal(calls, 7, 'must call the actual handler API branch');
    // Overlapping handler invocations cannot steal typed status from one another.
    // AsyncLocalStorage retains only fixed public classification, never diagnostics.
    let turn = 0;
    N8nApiClient.prototype[method] = async () => {
        const index = turn++;
        await new Promise(resolve => setTimeout(resolve, index % 2 ? 1 : 15));
        throw new N8nApiError('PRIVATE', index % 2 ? 429 : 404, 'PRIVATE', {secret:'PRIVATE'});
    };
    const results = await Promise.all(Array.from({length:8}, () => handlers[handler](args)));
    results.forEach((result, i) => {
        assert.equal(result.code, i % 2 ? 'RATE_LIMIT_ERROR' : 'NOT_FOUND');
        assert(!JSON.stringify(result).includes('PRIVATE'));
    });
})().catch(error => { console.error(error); process.exitCode = 1; });
''', handler, method, json.dumps(args))
