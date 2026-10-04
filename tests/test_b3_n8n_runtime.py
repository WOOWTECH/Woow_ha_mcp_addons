"""Real ChildSpec/dispatcher/handlers against retained owned ephemeral HTTP only."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit, parse_qs
import pytest
import test_batch2_n8n_public_errors as owned
from test_b3_n8n_policy import CASES, BAD
from test_expansion_policy import call
from test_real_products import rpc

KEY = owned.KEY
PRIVATE = owned.PRIVATE

@contextmanager
def backend():
    state = {'calls': [], 'keys': [], 'failures': [], 'case':'success'}
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)
        def log_message(self,*args): pass
        def do_GET(self):
            path = urlsplit(self.path)
            key = self.headers.get('X-N8N-API-KEY')
            state['keys'].append(key)
            state['calls'].append((self.command,path.path,parse_qs(path.query)))
            secret = PRIVATE + ':' + (key or KEY)
            case = state['case']
            value = {'status':'ok','private':secret}
            if path.path.endswith('/tags'):
                value = {'data':[{'id':'tag1','name':'Useful tag','private':secret}], 'nextCursor':'NEXT=='}
            elif path.path.endswith('/executions'):
                value = {'data':[{'id':'exec1','workflowId':'workflow1','status':'success', 'startedAt':'2026-10-01T12:00:00.000Z','stoppedAt':None,'data':{'inputs':secret},'stack':secret}], 'nextCursor':'NEXT=='}
            elif '/folders/' in path.path:
                value = {'id':'folder1','name':'Useful folder','parentFolderId':None,'createdAt':'2026-10-01T12:00:00.000Z','workflows':[{'credentials':secret}]}
            elif path.path.endswith('/workflows'):
                value = {'data': []}
            status = 200
            if case == 'health-fallback' and path.path == '/healthz':
                status, value = 404, {'message':secret}
            if type(case) is int:
                status, value = case, {'message':secret,'details':{'secret':secret},'stack':secret}
            elif case == 'null': value = None
            elif case == 'nonprimitive': value = {'data':[{'id':{'secret':secret},'name':secret}], 'id':{'private':secret}, 'status':{'private':secret}}
            elif case == 'overbudget': value = {'data':[{'id':'a','name':'a'}]*251}
            elif case == 'key-name': value = {'data':[{'id':'tag1','name':secret}], 'id':'folder1','name':secret}
            elif case == 'key-id':
                value = {'id':secret,'name':'Useful','data':[{'id':secret,'name':'Useful','workflowId':'workflow1','status':'success'}]}
            elif case == 'key-cursor':
                value = {'data':[{'id':'safe1','name':'Useful','workflowId':'workflow1','status':'success'}], 'nextCursor':secret}
            elif case == 'key-status':
                value = {'data':[{'id':'exec1','workflowId':'workflow1','status':secret}]}
            elif case == 'huge': value = {'data':secret*10000}
            if 'response' in state:
                value = state['response']  # B3 Unicode regressions supply exact metadata bodies.
            raw = secret.encode() if case == 'text' else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            if status == 302: self.send_header('Location','/never-follow')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads = True
    assert server.server_port != 3000
    server.timeout = .05
    stop = threading.Event()
    def serve():
        while not stop.is_set(): server.handle_request()
    thread = threading.Thread(target=serve,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}',state
    finally:
        stop.set(); thread.join(2); server.server_close()
        assert not thread.is_alive()

@pytest.mark.parametrize('name,args',CASES)
async def test_b3_real_success_and_predispatch_denials(tmp_path,monkeypatch,name,args):
    monkeypatch.setattr(owned,'backend',backend)
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (store,state,client,headers,wire,dispatches):
        reply = await rpc(client,'/mcp',headers,call(name,args))
        value = json.loads(reply['content'][0]['text'])
        assert value['success'] is True, value
        data = value['data']
        if name == 'n8n_list_catalog':
            assert data == {'items':[{'id':'tag1','name':'Useful tag'}], 'scanLimit':250,'hasMore':True,'scope':'first-page'}
            expected = ('GET','/api/v1/tags',{'limit':['250']})
        elif name == 'n8n_executions':
            assert data == {'executions':[{'id':'exec1','workflowId':'workflow1','status':'success','startedAt':'2026-10-01T12:00:00.000Z','stoppedAt':None}], 'returned':1,'nextCursor':'NEXT==','hasMore':True}
            expected = ('GET','/api/v1/executions',{'limit':['20'],'includeData':['false']})
        elif name == 'n8n_health_check':
            assert data == {'status':'ok','scope':'service-availability','authentication':'not-verified'}
            expected = ('GET','/healthz',{})
        else:
            assert data == {'id':'folder1','name':'Useful folder','parentFolderId':None,'createdAt':'2026-10-01T12:00:00.000Z','projectId':'project1'}
            expected = ('GET','/api/v1/projects/project1/folders/folder1',{})
        assert state['calls'] == [expected]
        assert state['keys'] == ([None] if name == 'n8n_health_check' else [KEY])
        assert KEY not in json.dumps(reply) and PRIVATE not in json.dumps(reply)
        for change in BAD[name]:
            before = len(dispatches)
            assert (await client.post('/mcp',headers=headers,json=call(name,{**args,**change}))).status_code == 403
            assert len(dispatches) == before and state['calls'] == [expected]
        before = len(dispatches)
        assert (await client.post('/mcp',headers=headers,json=call('unknown_b3',{}))).status_code == 403
        assert len(dispatches) == before
        for update in [{'disabled':[name]}, {'disabled':[],'backend_key':None},
                       {'backend_url':None,'backend_key':KEY}, {'backend_key':None}]:
            store.update(**update)
            before = len(dispatches)
            assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code in (403,503)
            assert len(dispatches) == before

@pytest.mark.parametrize('name,args',CASES)
async def test_b3_fresh_presend_authorization(tmp_path,monkeypatch,name,args):
    import mcp_admin_core.gateway as gateway
    monkeypatch.setattr(owned,'backend',backend)
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (store,state,client,headers,wire,dispatches):
        original = gateway.authorize
        checked = []
        def clear_after_first(message, tools, config):
            result = original(message,tools,config)
            if message.get('params',{}).get('name') == name:
                checked.append(result)
                store.update(backend_key=None)
            return result
        monkeypatch.setattr(gateway,'authorize',clear_after_first)
        before = len(dispatches)
        assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code == 403
        assert checked == ['tools/call']
        assert len(dispatches) == before and not state['calls']


async def test_b3_filters_cursor_and_health_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(owned,'backend',backend)
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (store,state,client,headers,wire,dispatches):
        for query, expected in [('USEFUL',1),('not present',0)]:
            reply = await rpc(client,'/mcp',headers,call('n8n_list_catalog',{'kind':'tags','query':query,'limit':1}))
            value = json.loads(reply['content'][0]['text'])
            assert len(value['data']['items']) == expected
            assert value['data']['hasMore'] is True
        assert state['calls'] == [('GET','/api/v1/tags',{'limit':['250']})]*2
        state['calls'].clear()
        reply = await rpc(client,'/mcp',headers,call('n8n_executions',{'action':'list','limit':100,'cursor':'NEXT==','workflowId':'workflow1','projectId':'project1','status':'success'}))
        assert json.loads(reply['content'][0]['text'])['success'] is True
        assert state['calls'] == [('GET','/api/v1/executions',{'limit':['100'],'includeData':['false'],'cursor':['NEXT=='],'workflowId':['workflow1'],'projectId':['project1'],'status':['success']})]
        state['calls'].clear(); state['case']='health-fallback'
        reply = await rpc(client,'/mcp',headers,call('n8n_health_check',{}))
        assert json.loads(reply['content'][0]['text']) == {'success':True,'data':{'status':'ok','scope':'service-availability','authentication':'not-verified'}}
        assert state['calls'] == [('GET','/healthz',{}),('GET','/api/v1/workflows',{'limit':['1']})]
        assert KEY not in json.dumps(reply) and PRIVATE not in json.dumps(reply)


async def test_b3_genuine_unconfigured_local_startup(tmp_path,monkeypatch):
    from n8n_adapter import child_spec
    monkeypatch.setattr(owned,'backend',backend)
    monkeypatch.setattr(owned,'child_spec',lambda state,directory: child_spec(
        state.model_copy(update={'backend_url':None,'backend_key':None}),directory))
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (store,state,client,headers,wire,dispatches):
        store.update(backend_url=None,backend_key=None)
        reply = await rpc(client,'/mcp',headers,call('tools_documentation',{}))
        assert reply['content'] and not reply.get('isError')
        assert reply['content'][0]['text'].startswith('# n8n MCP Tools Reference')
        for name,args in CASES:
            before = len(dispatches)
            assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code == 403
            assert len(dispatches) == before
        assert not state['calls']


@pytest.mark.parametrize('name,args',CASES)
async def test_b3_error_corpus(tmp_path,monkeypatch,name,args):
    monkeypatch.setattr(owned,'backend',backend)
    async with asyncio.timeout(100), owned.runtime(tmp_path) as (store,state,client,headers,wire,dispatches):
        for case in [400,401,403,404,429,500,599,418,302,'null','nonprimitive','huge','text','overbudget','key-name','key-id','key-cursor','key-status']:
            # healthz native checks status only and may fall back to authenticated workflows;
            # unrelated payload fields are discarded, not a metadata validity claim.
            if name == 'n8n_health_check' and not isinstance(case,int): continue
            if case == 'key-cursor' and name == 'n8n_manage_folders': continue
            if case == 'key-status' and name != 'n8n_executions': continue
            state['case']=case; state['calls'].clear(); wire.clear()
            reply=await rpc(client,'/mcp',headers,call(name,args))
            value=json.loads(reply['content'][0]['text'])
            assert value['success'] is False, (case,value)
            assert set(value) == {'success','error','code'}
            if type(case) is int and case in (400,401,403,404,429,500,599):
                expected = {400:'VALIDATION_ERROR',401:'AUTHENTICATION_ERROR',403:'FORBIDDEN',404:'NOT_FOUND',429:'RATE_LIMIT_ERROR',500:'SERVER_ERROR',599:'SERVER_ERROR'}
                assert value['code'] == expected[case]
            assert KEY not in json.dumps(reply) and PRIVATE not in json.dumps(reply)
            assert KEY not in b''.join(wire).decode() and PRIVATE not in b''.join(wire).decode()
            assert len(json.dumps(reply)) < 2048
            assert len(state['calls']) == (2 if name == 'n8n_health_check' else 1)
            assert all(c[1] != '/never-follow' for c in state['calls'])
