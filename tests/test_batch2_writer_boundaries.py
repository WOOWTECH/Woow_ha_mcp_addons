"""Isolated adapter contracts; complements (does not replace) owned real-runtime tests."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANAGE_PYTHON = ROOT / 'apps/odoo-manage/.venv/bin/python'
ENV = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'),
       'PYTHONDONTWRITEBYTECODE': '1', 'N8N_MCP_TELEMETRY_DISABLED': 'true'}


@pytest.mark.parametrize('source', ['services/n8n-api-client.js', 'utils/n8n-errors.js',
                                    'mcp/handlers-n8n-manager.js'])
def test_n8n_writer_guard_rejects_source_drift(source):
    code = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const read = fs.readFileSync;
fs.readFileSync = function(file, ...args) {
    if (String(file).endsWith(process.argv[1])) return Buffer.from('drift');
    return read.call(this, file, ...args);
};
assert.throws(() => require('./apps/n8n/backend_policy.cjs'), /requires source review/);
'''
    result = subprocess.run(['node', '-e', code, source], cwd=ROOT, env=ENV,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('source', ['tools.py', 'odoo_connection.py'])
def test_manage_writer_guard_rejects_source_drift(source):
    code = '''
from pathlib import Path
import runpy, sys
# Import normally first; mutate only the digest read, never the installed file.
import mcp_server_odoo.tools, mcp_server_odoo.odoo_connection
read = Path.read_bytes
def drift(self):
    if self.name == sys.argv[2]: return b'drift'
    return read(self)
Path.read_bytes = drift
try:
    runpy.run_path(sys.argv[1], run_name='boundary_test')
except RuntimeError as exc:
    assert str(exc) in ('Manage B1 handlers require source review',
                        'Manage authentication transport requires source review')
else:
    raise AssertionError('drift accepted')
'''
    result = subprocess.run([str(MANAGE_PYTHON), '-c', code, str(ROOT / 'apps/odoo-manage/launch.py'), source],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_manage_boundary_preserves_cancellation_and_never_stringifies_errors():
    code = '''
import asyncio, runpy, sys
module = runpy.run_path(sys.argv[1], run_name='boundary_test')
boundary = module['bounded_post_message']
access = module['access']
tools = module['tools']
class PrivateError(Exception):
    def __str__(self): raise AssertionError('must not stringify')
    def __repr__(self): raise AssertionError('must not repr')
async def exercise():
    for error, expected in [(PrivateError(), 'BACKEND_UNAVAILABLE'),
            (access.AccessControlError('PRIVATE'), 'BACKEND_ACCESS_DENIED'),
            (access.AccessControlUnavailableError('PRIVATE'), 'BACKEND_UNAVAILABLE'),
            (module['MessageResponseError']('PRIVATE'), 'BACKEND_INVALID_RESPONSE')]:
        async def original(*args, **kwargs):
            raise tools.ValidationError('PRIVATE') from error
        boundary.__globals__['post_message'] = original
        try: await boundary(None)
        except tools.ValidationError as exc:
            assert str(exc) == expected
            assert exc.__cause__ is None and exc.__suppress_context__
        else: raise AssertionError('invented success')
    for signal in [asyncio.CancelledError(), GeneratorExit(), KeyboardInterrupt()]:
        async def original(*args, **kwargs): raise signal
        boundary.__globals__['post_message'] = original
        try: await boundary(None)
        except BaseException as exc: assert exc is signal
        else: raise AssertionError('cancellation swallowed')
asyncio.run(exercise())
'''
    result = subprocess.run([str(MANAGE_PYTHON), '-c', code, str(ROOT / 'apps/odoo-manage/launch.py')],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_n8n_error_boundary_uses_only_typed_status_and_code():
    code = r'''
const assert = require('node:assert/strict');
const root = './apps/n8n/node_modules/n8n-mcp/dist/';
const {N8nApiClient} = require(root + 'services/n8n-api-client.js');
const {N8nApiError} = require(root + 'utils/n8n-errors.js');
let failure;
N8nApiClient.prototype.createWorkflow = async () => { throw failure; };
require('./apps/n8n/backend_policy.cjs');
(async () => {
    for (const [status, code, expected] of [
        [400, 'VALIDATION_ERROR', 'VALIDATION_ERROR'], [401, 'AUTHENTICATION_ERROR', 'AUTHENTICATION_ERROR'],
        [403, 'PUBLISH_FORBIDDEN', 'FORBIDDEN'], [404, 'NOT_FOUND', 'NOT_FOUND'],
        [429, 'RATE_LIMIT_ERROR', 'RATE_LIMIT_ERROR'], [599, 'SERVER_ERROR', 'SERVER_ERROR'],
        [undefined, 'NO_RESPONSE', 'NO_RESPONSE'], [undefined, 'REQUEST_ERROR', 'BACKEND_UNAVAILABLE'],
        [418, 'PRIVATE', 'BACKEND_UNAVAILABLE']]) {
        failure = new N8nApiError('PRIVATE', status, code, {secret: 'PRIVATE'});
        for (const key of ['message', 'details', 'toString', 'stack']) {
            Object.defineProperty(failure, key, {get() { throw Error('must not inspect private text'); }});
        }
        await assert.rejects(N8nApiClient.prototype.createWorkflow(), error => {
            assert.equal(error.code, expected);
            assert.equal(error.details, undefined);
            assert(!error.message.includes('PRIVATE'));
            return true;
        });
    }
    // A backend-shaped plain object cannot supply classification authority.
    failure = {statusCode: 400, code: 'VALIDATION_ERROR', toString() { throw Error('no stringify'); }};
    await assert.rejects(N8nApiClient.prototype.createWorkflow(), {code: 'BACKEND_UNAVAILABLE'});
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', code], cwd=ROOT, env=ENV,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
