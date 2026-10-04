"""B2 public schema/authorization parity, not upstream unrestricted defaults."""
from contextlib import closing
import json
import subprocess
from pathlib import Path
import httpx
from test_batch2_bounds import schema_results
import pytest
from pydantic import ValidationError
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from mcp_admin_core.policy import authorize, Denied
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.health import HealthMonitor
from test_expansion_policy import call

CASES = [('schema_catalog', {}), ('inspect_model_relationships', {'model': 'res.partner'}),
         ('data_quality_report', {'model': 'res.partner'})]
BAD = {
    'schema_catalog': [{'models': None}, {'models': []}, {'models': ['res.users']}, {'models': ['res.partner']*2},
                       {'query': 'partner'}, {'limit': 2}, {'limit': True}, {'include_fields': None}, {'refresh': None}],
    'inspect_model_relationships': [{'model': 'res.users'}, {'fields_metadata': {}}, {'use_live_metadata': False},
                                    {'include_computed': False}, {'include_readonly': None}],
    'data_quality_report': [{'model': 'hr.employee'}, {'checks': None}, {'checks': []}, {'checks': ['duplicates']},
                            {'checks': ['missing_required']*2}, {'key_fields': ['email']}, {'key_fields': None},
                            {'sample_limit': 0}, {'sample_limit': 101}, {'sample_limit': True}],
}

@pytest.mark.parametrize('name,args', CASES)
def test_b2_schema_parity_and_policy(tmp_path, name, args):
    assert name in TOOLS['odoo']
    tool = TOOLS['odoo'][name]
    assert not tool.write and not tool.grants(name)
    schema = tool.arguments.model_json_schema()
    candidates = [(args, True), ({**args, 'instance': None}, True), ({**args, 'instance': 'default'}, True)]
    candidates += [({**args, **change}, False) for change in BAD[name]]
    candidates += [({**args, k: v}, False) for k, v in [('context', {}), ('ctx', {}), ('instance', 'other'),
                    ('metadata_error', 'private'), ('url', 'http://example.invalid'), ('domain', []), ('depth', 2)]]
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        accepted = schema_results(schema, [values for values, _ in candidates])
        for (values, valid), result in zip(candidates, accepted, strict=True):
            assert result is valid, values
            if valid:
                parsed = tool.arguments.model_validate(values).model_dump()
                authorize(call(name, parsed), TOOLS['odoo'], store.load())
            else:
                with pytest.raises(ValidationError): tool.arguments.model_validate(values)
                with pytest.raises(Denied): authorize(call(name, values), TOOLS['odoo'], store.load())
        store.update(disabled=[name], writes_enabled=True)
        with pytest.raises(Denied): authorize(call(name, args), TOOLS['odoo'], store.load())
        with pytest.raises(Denied): authorize(call('execute_method', {'model':'res.partner'}), TOOLS['odoo'], store.load())

async def test_b2_unconfigured_zero_dispatch_and_dynamic_ui(tmp_path):
    async def role(_): return True
    dispatched = []
    async def backend(request):
        dispatched.append(request)
        raise AssertionError('unconfigured must not dispatch')
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        assert child_spec(store.load(), store.directory) is None
        async with httpx.AsyncClient(transport=httpx.MockTransport(backend)) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=role)
            process = Supervisor(child_spec(store.load(), store.directory))
            try:
                await process.start()
                monitor = HealthMonitor(store, process, child)
                await monitor.check()
                assert process.starts == 0 and monitor.backend == 'unconfigured'
            finally:
                await process.stop()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2',1)), base_url='http://local') as client:
                bootstrap = (await client.get('/api/bootstrap', headers={'x-remote-user-id':'a'*32})).json()
                probe = subprocess.run(['node','--input-type=module','-e', '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {toolRows} from './packages/mcp-admin-ui/src/contracts.js';
const [b,names] = JSON.parse(fs.readFileSync(0,'utf8'));
const rows = toolRows(b);
for (const name of names) assert.ok(rows.some(r => r.name === name));
'''], input=json.dumps([bootstrap,[n for n,_ in CASES]]), text=True, capture_output=True,
                    cwd=Path(__file__).resolve().parents[1], timeout=10, env={'PATH':'/usr/bin:/bin'})
                assert probe.returncode == 0, probe.stderr
        assert not dispatched
