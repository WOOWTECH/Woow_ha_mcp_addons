"""Actual Core bootstrap/policy and unmodified production UI v3 serializers."""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import httpx
import pytest
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_real_products import connection

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('product,grant', [('n8n', 'n8n_create_workflow'), ('odoo-manage', 'post_message')])
async def test_b1_real_admin_ui_grants_roundtrip(tmp_path, product, grant):
    # Explicit local role injection, not a six-product production HA provider.
    async def role(_): return True
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'odoo-manage': store.update(connection={**connection(product, 'http://127.0.0.1:12345'), 'mode': 'module'})
        store.update(writes_enabled=True)
        tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, tools, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://local') as client:
                identity = {'x-remote-user-id': 'a'*32}
                bootstrap = (await client.get('/api/bootstrap', headers=identity)).json()
                probe = subprocess.run(['node', '--input-type=module', '-e', '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {granularPolicy, toolRows, effectiveGrant, policyPayload} from './packages/mcp-admin-ui/src/contracts.js';
const [b, grant] = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.equal(granularPolicy(b), true);
const row = toolRows(b).find(r => r.name === grant);
assert.equal(row.legacy, false);
assert.equal(effectiveGrant(b, row, null), false); // old global=true never inherits
const payload = policyPayload(b, [], [{tool:grant, operation:null}]);
assert.deepEqual(payload.enabled_write_tools, [grant]);
assert.equal(payload.writes_enabled, false);
console.log(JSON.stringify(payload));
'''], cwd=ROOT, input=json.dumps([bootstrap, grant]), text=True, capture_output=True, timeout=10,
                    env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
                assert probe.returncode == 0, probe.stderr
                response = await client.put('/api/policy', headers={**identity, 'x-csrf-token': bootstrap['csrf']}, json=json.loads(probe.stdout))
                assert response.status_code == 200, response.text
                assert store.load().enabled_write_tools == [grant] and store.load().writes_enabled is False
                fresh = (await client.get('/api/bootstrap', headers=identity)).json()
                assert fresh['enabled_write_tools'] == [grant]
                response = await client.put('/api/policy', headers={**identity, 'x-csrf-token': fresh['csrf']}, json={'writes_enabled': False, 'disabled': [], 'enabled_write_tools': []})
                assert response.status_code == 200 and store.load().enabled_write_tools == []
