"""Bounded offline selector audit: pinned native guards + real HA ASGI/policy/UI contracts."""
from contextlib import closing
from admin_write_headers import reviewed_headers
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.capabilities import tool_catalog
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import ToolCallRefused, authorize
from mcp_admin_core.products import ProductStore, fresh_write_grants
from mcp_admin_core.surface import full_tools

ROOT = Path(__file__).resolve().parents[1]
TOOLS = full_tools('n8n')
NAMES = ('n8n_manage_agents', 'n8n_test_workflow', 'n8n_list_catalog')


def call(name, args):
    return {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}


def node(script, *args):
    return subprocess.run(['node', *script, *args], env={'PATH':'/usr/bin:/bin','LOG_LEVEL':'error'},
                          text=True, capture_output=True, check=True, timeout=20).stdout


def test_pinned_native_callback_schema_effects_and_auto_trigger_guard():
    data = json.loads(node([str(ROOT/'tests/n8n_selector_probe.cjs')],
                          str(ROOT/'apps/n8n/node_modules/n8n-mcp/dist/mcp')))
    for name in NAMES:
        tool = TOOLS[name]
        assert data[name]['selector'] == tool.selector
        assert set(data[name]['values']) == set(tool.operations)
        assert data[name]['default'] == tool.default_operation
        assert data[name]['dispatches'] == len(tool.operations)
    assert {op: op in TOOLS[NAMES[0]].write_operations for op in TOOLS[NAMES[0]].operations} == data['agentWrites']


@pytest.mark.parametrize('name', NAMES)
async def test_denies_unknowns_wrappers_and_grants_before_child(tmp_path, name):
    tool = TOOLS[name]
    seen = []
    def answer(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'jsonrpc':'2.0','id':1,'result':{'content':[]}})
    with closing(ProductStore(tmp_path,'n8n')) as store:
        initial = store.load()
        # Whole-tool grants unchanged; selectors create no additional write grants.
        assert len(fresh_write_grants('n8n')) == 33
        assert tool.grants(name) == ([name] if tool.write else [])
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as child:
            _, public = make_apps(store, TOOLS, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(public),base_url='http://owned') as client:
                headers={'Authorization':'Bearer '+initial.token,'Mcp-Session-Id':'owned',
                         'Accept':'application/json, text/event-stream'}
                async def send(args, denied=False):
                    before=len(seen)
                    reply=await client.post('/mcp',headers=headers,json=call(name,args))
                    assert reply.status_code == 200
                    assert ('error' in reply.json()) is denied, reply.text
                    assert len(seen) == before+(not denied)
                for op in tool.operations:
                    args={tool.selector:op,'workflowId':'fake'}
                    store.update(denied_operations={})
                    await send(args)
                    store.update(denied_operations={name:[op]})
                    await send(args,True)
                    await send({'output':json.dumps(args)},True)
                    other=next(x for x in tool.operations if x!=op and not (op=='trigger' and x=='auto'))
                    await send({tool.selector:other,'workflowId':'fake'})
                for denied in ({},{name:[tool.operations[0]]}):
                    store.update(denied_operations=denied)
                    for op in (None,1,True,[],{},'UNKNOWN','expose'):
                        await send({tool.selector:op,'workflowId':'fake'},True)
                store.update(denied_operations={})
                await send({'workflowId':'fake'},tool.default_operation is None)
                if name=='n8n_test_workflow':
                    await send({'workflowId':'fake','method':' \t\ufeff'})
                    store.update(denied_operations={name:['trigger']})
                    for args in ({'workflowId':'fake'},{'workflowId':'fake','method':'auto'},
                                 {'workflowId':'fake','method':' \t\ufeff'}):
                        await send(args,True)
                    await send({'workflowId':'fake','method':'prepare'})
                    items=tool_catalog({name:tool},None,None,store.load())['items'][0]['operations']
                    assert not next(x for x in items if x['name']=='auto')['policy_enabled']
                store.update(denied_operations={},enabled_write_tools=[])
                await send({tool.selector:tool.read_operations[0]},tool.write)
                store.update(enabled_write_tools=initial.enabled_write_tools,disabled=[name])
                await send({tool.selector:tool.read_operations[0]},True)


async def test_real_bootstrap_ui_serializer_and_policy_api(tmp_path):
    async def role(_): return True
    def forbidden(_): raise AssertionError('admin must not reach backend')
    with closing(ProductStore(tmp_path,'n8n')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as child:
            admin,_=make_apps(store,TOOLS,child,verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=('172.30.32.2',1)),base_url='http://owned') as client:
                identity={'x-remote-user-id':'selector-review'}
                bootstrap=(await client.get('/api/bootstrap',headers=identity)).json()
                for name in NAMES:
                    entry=bootstrap['tools'][name]
                    assert entry['operation_parameter']==TOOLS[name].selector
                    assert {x['name']:x['write'] for x in entry['operations']} == {
                        op:op in TOOLS[name].write_operations for op in TOOLS[name].operations}
                code='''import {operationPolicy,toolRows,policyPayload} from './packages/mcp-admin-ui/src/contracts.js';
import assert from 'node:assert/strict';
const b=JSON.parse(process.argv[1]); assert(operationPolicy(b));
const names=JSON.parse(process.argv[2]);
for(const n of names) assert(toolRows(b).find(r=>r.name===n).auditedOperations.length>0);
const grants=toolRows(b).flatMap(r=>r.operations.length?r.operations.map(operation=>({tool:r.name,operation})):(r.write?[{tool:r.name,operation:null}]:[]));
const denies=names.map(tool=>({tool,operation:b.tools[tool].operations[0].name}));
process.stdout.write(JSON.stringify(policyPayload(b,[],grants,denies)));'''
                result=subprocess.run(['node','--input-type=module','-e',code,json.dumps(bootstrap),json.dumps(NAMES)],
                    cwd=ROOT,env={'PATH':'/usr/bin:/bin'},text=True,capture_output=True,timeout=10)
                assert result.returncode == 0, result.stderr
                payload=json.loads(result.stdout)
                assert set(payload['enabled_write_tools']) == set(store.load().enabled_write_tools)
                headers=reviewed_headers(bootstrap, identity)
                response=await client.put('/api/policy',headers=headers,json=payload)
                assert response.status_code==200,response.text
                assert store.load().denied_operations==payload['denied_operations']
                payload['denied_operations']['n8n_test_workflow']=['expose']
                assert (await client.put('/api/policy',headers=headers,json=payload)).status_code==400
