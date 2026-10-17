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
