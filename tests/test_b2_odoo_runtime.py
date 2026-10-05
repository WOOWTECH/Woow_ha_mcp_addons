"""Genuine pinned Odoo child -> owned XMLRPC, with exact outbound RPC evidence."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import xmlrpc.client
import httpx
import pytest
from owned_runtime import Endpoint
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from test_real_products import connection, rpc
from test_expansion_policy import call
from test_expansion_runtime import payload
from test_b2_odoo_policy import CASES, BAD

FIELDS = {'id':'integer', 'name':'char', 'display_name':'char', 'active':'boolean',
          'parent_id':'many2one', 'child_ids':'one2many'}
ATTRS = ['type', 'required', 'readonly', 'store', 'relation']
CANARY = 'B2_PRIVATE_DUMMY_CREDENTIAL'

@contextmanager
def fake_odoo():
    events, failures = [], []
    state = {'mode': 'ok', 'started': threading.Event(), 'release': threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            try:
                params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
                events.append((method, params[3:] if method == 'execute_kw' else ()))
                if method == 'authenticate':
                    assert params[2] == CANARY
                    value = 7
                else:
                    assert method == 'execute_kw'
                    assert params[2] == CANARY
                    model, op, args, kw = params[3:]
                    assert model in ('ir.model', 'res.partner')
                    if state['mode'] == 'fault':
                        raise xmlrpc.client.Fault(1, CANARY+' backend raw context')
                    if state['mode'] == 'blocked':
                        state['started'].set()
                        assert state['release'].wait(8)
                    if model == 'ir.model':
                        assert op == 'search_read' and args == [[['model','=','res.partner']]]
                        assert kw == {'fields':['model'], 'limit':1}
                        value = [{'model':'res.partner','name': CANARY, 'private':CANARY}]
                    elif op == 'fields_get':
                        assert args in ([list(FIELDS)], [['name','active']])
                        assert kw == {'attributes': ['type','required','store'] if args == [['name','active']] else ATTRS}
                        value = {n: {'type': FIELDS[n], 'required': n == 'name', 'readonly': n == 'display_name',
                                     'store': True, 'relation': 'res.partner' if n in ('parent_id','child_ids') else False,
                                     'help':CANARY, 'string':CANARY, 'context':{'key':CANARY}, 'compute':CANARY}
                                 for n in args[0]}
                        value['email'] = {'type':'char', 'default':CANARY}
                        if state['mode'] == 'malformed': value['name']['required'] = CANARY
                        if state['mode'] == 'relation': value['parent_id']['relation'] = CANARY
                    else:
                        assert op == 'search_count' and args == [[['name','=',False]]] and kw == {}
                        value = 3 if state['mode'] != 'bad_count' else CANARY
                data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
            except xmlrpc.client.Fault as exc:
                data = xmlrpc.client.dumps(exc).encode()
            except Exception as exc:
                failures.append(repr(exc))
                data = xmlrpc.client.dumps(xmlrpc.client.Fault(1,'fake assertion')).encode()
            self.send_response(200); self.send_header('Content-Type','text/xml')
            self.send_header('Content-Length',str(len(data))); self.end_headers()
            try: self.wfile.write(data)
            except BrokenPipeError: pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}', events, failures, state
    finally:
        state['release'].set(); server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()


async def initialize(client, headers):
    init = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26',
            'capabilities':{},'clientInfo':{'name':'b2-owned','version':'0'}}}
    async with asyncio.timeout(25):
        while True:
            try: result = await rpc(client,'/mcp',headers,init); break
            except ValueError: await asyncio.sleep(.1)
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client,'/mcp',headers,{'jsonrpc':'2.0','method':'notifications/initialized'})


async def test_b2_genuine_handlers_rpc_cache_errors_and_denials(tmp_path):
    with fake_odoo() as (url,events,failures,state):
        store = ProductStore(tmp_path/'state','odoo')
        store.update(connection={**connection('odoo',url),'password':CANARY})
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(),store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _,app = make_apps(store,TOOLS['odoo'],child,child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://boundary') as client:
                    headers={'Authorization':'Bearer '+store.load().token,'Accept':'application/json, text/event-stream'}
                    await initialize(client,headers)
                    listed=await rpc(client,'/mcp',headers,{'jsonrpc':'2.0','id':2,'method':'tools/list'})
                    assert {n for n,_ in CASES} <= {t['name'] for t in listed['tools']}
                    for name,args in CASES:
                        tool=next(t for t in listed['tools'] if t['name']==name)
                        assert tool['inputSchema']==TOOLS['odoo'][name].arguments.model_json_schema()
                        assert 'res.partner' in tool['description']
                        before=len(events)
                        value=payload(await rpc(client,'/mcp',headers,call(name,args)))
                        assert len(events)>before
                        assert CANARY not in json.dumps(value)
                        if name=='schema_catalog':
                            assert value['result']==[{'model':'res.partner','name':''}]  # SDK response-model default, never backend label
                            assert value['metadata_used']['cache_hit'] is False
                            before=len(events)
                            hit=payload(await rpc(client,'/mcp',headers,call(name,args)))
                            assert hit['metadata_used']['cache_hit'] is True and len(events)==before
                            value=payload(await rpc(client,'/mcp',headers,call(name,{'include_fields':True})))
                            assert set(value['result'][0]['fields'])==set(FIELDS)
                            assert value['result'][0]['fields']['parent_id']['relation']=='res.partner'
                            before=len(events)
                            await rpc(client,'/mcp',headers,call(name,{'include_fields':True,'refresh':True}))
                            assert len(events)==before+2
                        elif name=='inspect_model_relationships':
                            assert value['summary']=={'field_count':6,'relationship_count':2,'required_count':1}
                            assert value['relationships']['many2one']==[{'name':'parent_id','relation':'res.partner','required':False,'readonly':False}]
                            assert 'write_hints' not in value and 'create_hints' not in value
                            assert value['metadata_used']=={'fields_get':True,'source':'server'}
                        else:
                            assert value['summary']['total_issues']==3 and value['summary']['clean'] is False
                            assert value['results']==[{'check':'missing_required','ok':False,'issue_count':3,
                                'fields_checked':['name'],'evidence':[{'field':'name','records_missing_value':3}]}]
                            assert value.get('instance') is None
                        before=len(events)
                        for change in BAD[name]+[{'context':{}},{'instance':'other'}]:
                            assert (await client.post('/mcp',headers=headers,json=call(name,{**args,**change}))).status_code==403
                        store.update(disabled=[name],writes_enabled=True)
                        assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code==403
                        assert len(events)==before
                        store.update(disabled=[])
                    for mode in ('fault','malformed','bad_count','relation'):
                        state['mode']=mode
                        for name,args in CASES:
                            if mode=='bad_count' and name!='data_quality_report': continue
                            if mode=='relation' and name=='data_quality_report': continue
                            if name=='schema_catalog': args={**args,'include_fields':True,'refresh':True}
                            reply=await rpc(client,'/mcp',headers,call(name,args))
                            text=json.dumps(reply)
                            assert CANARY not in text and 'backend raw context' not in text
                            if mode=='fault':
                                # 0.1.2: the fixed transport code is reported (0.1.1 HA: an account without ir.model
                                # access read as BACKEND_RESPONSE_INVALID); the raw fault text still never leaves.
                                assert json.loads(reply['content'][0]['text'])['error']=='BACKEND_RPC_FAULT', reply
                                assert 'BACKEND_RESPONSE_INVALID' not in text, reply
                            else:
                                assert 'BACKEND_RESPONSE_INVALID' in text or reply.get('isError') is True, reply
                    state['mode']='ok'
                    # Cancel each genuine sync handler while its own RPC is held.
                    # Capacity belongs to execution, not the disconnected caller.
                    for name,args in CASES:
                        state['mode']='blocked'; state['started'].clear(); state['release'].clear()
                        if name=='schema_catalog': args={**args,'refresh':True}
                        pending=asyncio.create_task(rpc(client,'/mcp',headers,call(name,args)))
                        try:
                            async with asyncio.timeout(5):
                                while not state['started'].is_set(): await asyncio.sleep(.02)
                            pending.cancel()
                            try: await pending
                            except asyncio.CancelledError: pass
                            busy=await rpc(client,'/mcp',headers,call('inspect_model_relationships',{'model':'res.partner'}))
                            assert busy.get('isError') is True and 'BACKEND_BUSY' in json.dumps(busy), busy
                        finally:
                            state['mode']='ok'; state['release'].set()
                            if not pending.done():
                                pending.cancel()
                                try: await pending
                                except asyncio.CancelledError: pass
                        async with asyncio.timeout(5):
                            while True:
                                recovered=await rpc(client,'/mcp',headers,call('data_quality_report',{'model':'res.partner'}))
                                if not recovered.get('isError'): break
                                await asyncio.sleep(.02)
                        assert payload(recovered)['summary']['total_issues']==3
                    assert not failures, failures
                    print('B2_RPC_EVIDENCE', json.dumps(events))
                    await client.delete('/mcp',headers=headers)
        finally:
            await process.stop(); store.close()
