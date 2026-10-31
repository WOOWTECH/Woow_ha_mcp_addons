"""Pinned child processes + real gateway + real SDK clients; fake backends only."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess

import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from mcp_admin_core.surface import listing
from n8n_adapter import TOOLS as N8N_TOOLS, child_spec as n8n_spec
from owned_runtime import Endpoint
from test_active_token_leases import listen
from test_expansion_runtime import fake_api, READS, WRITES
from test_real_products import connection
from test_tool_snapshot import child_listing, own_listing
from test_batch2_policy import GRAPH

ROOT = Path(__file__).resolve().parents[1]
PINNED = json.loads((ROOT/'packages/mcp-admin-core/mcp_admin_core/output_schemas.json').read_text())


@pytest.mark.parametrize('product', ['litellm','nextcloud','odoo','n8n'])
async def test_real_child_live_and_fallback_contracts_match(tmp_path,product):
    with fake_api() as (url,events,mutations,failures), closing(ProductStore(tmp_path/'state',product)) as store:
        if product == 'n8n':store.update(backend_url=url,backend_key='DUMMY')
        else:store.update(connection=connection(product,url))
        raw,live=await child_listing(store,product)
        pinned={e['tool']:e['schema'] for e in PINNED['entries'] if e['product']==product}
        assert {t['name']:t['outputSchema'] for t in raw['tools'] if t['name'] in pinned}==pinned
        assert {t['name']:t['outputSchema'] for t in live['tools'] if 'outputSchema' in t}==pinned
        fallback=await own_listing(store,product,{'child':'backoff','ready':False,'backend':'unknown','reason':None})
        assert fallback==live
        assert not mutations and not failures


@pytest.mark.parametrize('sdk',['python2','typescript'])
@pytest.mark.parametrize('product',['litellm','nextcloud','odoo','n8n'])
async def test_sdk_clients_validate_actual_structured_results(tmp_path,product,sdk):
    # CI already installs the repository's pinned n8n SDK. Local isolated installs
    # may point only at a separately owned copy of that same exact SDK version.
    sdk_path=Path(os.environ.get('WOOW_OUTPUT_SCHEMA_SDK',ROOT/'apps/n8n/node_modules/@modelcontextprotocol/sdk'))
    if sdk=='typescript':assert json.loads((sdk_path/'package.json').read_text())['version']=='1.32.2'
    cases = ([('validate_node', {'nodeType':'nodes-base.noOp','config':{}}),
              ('validate_workflow', {'workflow':GRAPH})] if product == 'n8n'
             else READS[product] if product == 'odoo' else READS[product] + WRITES[product])
    calls=[(name,args,False) for name,args in cases if name!='get_file_content']
    if product=='nextcloud':calls.append(('read_text_file',{'path':'missing.txt'},True))
    elif product=='litellm':calls.append(('litellm_model_info',{},True))  # fake backend 404 -> tool error, no schema failure
    with fake_api() as (url,events,mutations,failures), closing(ProductStore(tmp_path/'state',product)) as store:
        if product == 'n8n':store.update(backend_url=url,backend_key='DUMMY')
        else:store.update(connection=connection(product,url))
        endpoint=Endpoint(product);manager=endpoint.supervisor((n8n_spec if product=='n8n' else child_spec)(store.load(),store.directory))
        try:
            await manager.start()
            async with endpoint.client(timeout=20) as child:
                tools=N8N_TOOLS if product=='n8n' else TOOLS[product]
                _,app=make_apps(store,tools,child,child_url=endpoint.url,listing=listing(product))
                async with listen(app) as base:
                    env={'PATH':os.environ['PATH'],'HOME':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1',
                        'WOOW_URL':base+'/mcp','WOOW_TOKEN':store.load().token,'WOOW_CALLS':json.dumps(calls),'WOOW_SDK':str(sdk_path)}
                    argv=([str(ROOT/'apps/litellm/.venv/bin/python'),str(ROOT/'tests/output_schema_sdk_client.py')]
                          if sdk=='python2' else ['node',str(ROOT/'tests/output_schema_sdk_client.cjs')])
                    done=await asyncio.to_thread(subprocess.run,argv,env=env,cwd=tmp_path,capture_output=True,text=True,timeout=60)
                    assert done.returncode==0,done.stderr[-5000:]
                    result=json.loads(done.stdout.splitlines()[-1])
                    assert result['schemas']=={e['tool']:e['schema'] for e in PINNED['entries'] if e['product']==product}
                    assert [r['error'] for r in result['results']]==[c[2] for c in calls]
                    assert result['protocol']==('2025-03-26' if product=='n8n' else '2025-11-25')
        finally:
            await manager.stop();endpoint.close()
