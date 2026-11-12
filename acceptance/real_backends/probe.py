"""Executed in an exact gateway image. Only sanitized evidence leaves the pod.

MODE/PHASE are prepended by the controller. No automatic retries of mutations.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
import httpx

F=json.loads(Path('/run/scratch/fixture.json').read_text())
PRODUCT=F['family']; MARK=F['marker']+'-'+MODE
USER='04404404404404404404404404404404'
STAGE='start'
SELECTED={'odoo':['execute_method','search_records','read_record','health_check'],
          'nextcloud':['create_text_file','read_text_file','update_text_file','delete_file_checked','get_file_tree'],
          'emqx':['emqx_publish','emqx_get_retained','emqx_delete_retained','emqx_broker_stats']}
WRITES={'odoo':['execute_method'],'nextcloud':['create_text_file','update_text_file','delete_file_checked'],'emqx':['emqx_publish','emqx_delete_retained']}
OFF={'enable_writes':False,'allow_direct_writes':True,'allow_unknown_methods':False,'chatter_direct':False}
A=httpx.Client(base_url='http://127.0.0.1:'+('8099' if MODE=='ha' else '8080'),trust_env=False,timeout=75)
if MODE=='ha': A.headers['X-Remote-User-Id']=USER
else:
    r=A.post('/api/auth/login',json={'password':F['admin_password']});assert r.status_code==200
    A.headers['Authorization']='Bearer '+r.json()['token']

def admin(path,data=None,method='PUT'):
    if MODE=='ha':
        b=A.get('/api/bootstrap');assert b.status_code==200
        headers={'If-Match':b.headers['etag'],'X-CSRF-Token':b.json()['csrf']}
    else:
        b=A.get('/api/settings');assert b.status_code==200
        headers={'If-Match':b.headers['etag']}
    r=A.request(method,'/api/'+path,headers=headers,**({'json':data} if data is not None else {}))
    assert r.status_code==200, 'admin_status_'+str(r.status_code)+'_'+path
    return r.json()

def ready():
    for _ in range(90):
        if MODE=='ha':
            r=A.get('/api/bootstrap')
            if (r.status_code==200
                    and r.json().get('configuration',{}).get('apply_state')=='applied'
                    and r.json().get('health',{}).get('backend')=='reachable'):return
        else:
            r=A.get('/api/settings/mcp/status')
            if r.status_code==200 and r.json().get('running') and r.json().get('configuration',{}).get('apply_state')=='applied':
                try:
                    transport=httpx.options('http://127.0.0.1:8000/mcp',timeout=2,trust_env=False)
                    if transport.status_code in (200,204,400,404,405,406):return
                except httpx.TransportError:pass
        time.sleep(1)
    raise RuntimeError('child_not_ready')

def policy(allow):
    if MODE=='ha':
        from mcp_admin_core.products import TOOLS
        return admin('policy',{'writes_enabled':False,'disabled':sorted(set(TOOLS[PRODUCT])-set(SELECTED[PRODUCT])), 'enabled_write_tools':WRITES[PRODUCT] if allow else [],'denied_operations':{}})
    rows=A.get('/api/tools');assert rows.status_code==200
    all_names={x['name'] for x in rows.json()['tools']}
    allowed=set(SELECTED[PRODUCT])-(set() if allow else set(WRITES[PRODUCT]))
    widened=bool(set(rows.json()['disabled_tools']) & allowed)
    old_pid=A.get('/api/settings/mcp/status').json().get('pid')
    result=admin('tools',{'disabled_tools':sorted(all_names-allowed)})
    if PRODUCT=='nextcloud' and widened and old_pid:
        # This shipped middleware restarts AFTER sending the policy response.
        # Wait for its replacement PID, then the app's own applied revision.
        for _ in range(90):
            s=A.get('/api/settings/mcp/status').json()
            if s.get('pid') and s['pid']!=old_pid:
                ready();break
            time.sleep(1)
        else:raise RuntimeError('policy_child_restart_not_observed')
    return result

def switches(on):
    if MODE=='ha':admin('odoo/write-switches',{'odoo_write_switches':{**OFF,'enable_writes':on}})
    else:admin('settings/mcp_server',{'env':{'ODOO_MCP_ENABLE_WRITES':'1' if on else '0','ODOO_MCP_ALLOW_DIRECT_WRITES':'1','ODOO_MCP_ALLOW_UNKNOWN_METHODS':'0','MCP_CHATTER_DIRECT':'0'}})
    ready()

class MCP:
    def __init__(self):
        if MODE=='ha':
            token=admin('token/reveal',None,'POST')['token'];self.url='http://127.0.0.1:8081/mcp'
            headers={'Authorization':'Bearer '+token}
        else:
            token=admin('settings/mcp_auth_token/reveal',None,'POST')['value'];self.url='http://127.0.0.1:8080/private_'+token+'/mcp';headers={}
        self.client=httpx.Client(trust_env=False,timeout=75,headers={**headers,'Accept':'application/json, text/event-stream'});self.i=0
        z=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'owned-real-backends','version':'1'}})
        assert 'result' in z
        self.client.headers['MCP-Protocol-Version']=z['result']['protocolVersion']
        r=self.client.post(self.url,json={'jsonrpc':'2.0','method':'notifications/initialized'});assert r.status_code in (200,202,204)
    def rpc(self,method,params):
        self.i+=1;r=self.client.post(self.url,json={'jsonrpc':'2.0','id':self.i,'method':method,'params':params});assert r.status_code==200
        if 'mcp-session-id' in r.headers:self.client.headers['Mcp-Session-Id']=r.headers['mcp-session-id']
        if 'text/event-stream' in r.headers.get('content-type',''):
            return next(x for x in [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith('data:')] if x.get('id')==self.i)
        return r.json()
    def call(self,name,args):return self.rpc('tools/call',{'name':name,'arguments':args})
    def close(self):
        try:self.client.delete(self.url)
        finally:self.client.close()

def payload(r):
    assert 'result' in r
    v=r['result'];p=v.get('structuredContent')
    if p is None:
        try:p=json.loads(v['content'][0]['text'])
        except (ValueError,KeyError):p=v['content'][0]['text']
    if PRODUCT=='odoo':
        for _ in range(3):
            if isinstance(p,dict) and isinstance(p.get('success'),bool):break
            p=p.get('result') if isinstance(p,dict) else json.loads(p)
    return p
def good(r):
    assert 'result' in r and not r['result'].get('isError'), 'expected_success'
    p=payload(r)
    if PRODUCT=='odoo':assert p['success'] is True;return p['result']
    return p
def denied(r):
    if 'error' in r:
        assert r['error']['code'] == -32602
        return {'rpc_error':r['error']['code']}
    assert r['result'].get('isError') is True
    return {'isError':True}
def execute(m,method,args,kwargs=None,model='res.partner'):
    return m.call('execute_method',{'model':model,'method':method,'args':args,'kwargs':kwargs or {}})
def own():return json.loads(Path('/data/owned.json').read_text())
def snapshot_native():
    c=F['connection']
    if PRODUCT=='nextcloud':
        r=httpx.get(c['url']+'/remote.php/dav/files/'+c['username']+'/'+MARK+'.txt',auth=(c['username'],c['app_password']),timeout=20,trust_env=False)
        assert r.status_code in (200,404)
        return {'status':r.status_code,'body_sha256':hashlib.sha256(r.content).hexdigest() if r.status_code==200 else None}
    if PRODUCT=='emqx':
        r=httpx.get(c['url']+'/api/v5/mqtt/retainer/message/'+urllib.parse.quote(MARK+'/retained',safe=''),auth=(c['api_key'],c['api_secret']),timeout=20,trust_env=False)
        assert r.status_code in (200,404)
        p=r.json().get('payload') if r.status_code==200 else None
        return {'status':r.status_code,'payload_sha256':hashlib.sha256(base64.b64decode(p)).hexdigest() if p else None}
    import xmlrpc.client
    common=xmlrpc.client.ServerProxy(c['url']+'/xmlrpc/2/common',allow_none=True)
    uid=common.authenticate(c['database'],c['username'],c['password'],{});assert isinstance(uid,int) and uid>0
    obj=xmlrpc.client.ServerProxy(c['url']+'/xmlrpc/2/object',allow_none=True)
    rows=obj.execute_kw(c['database'],uid,c['password'],'res.partner','search_read',[[['name','=',MARK]]],{'fields':['id','name','email']})
    return {'rows':rows}

def main():
    global STAGE
    if PHASE=='configure':
        STAGE='restrict_policy';policy(False)
        if MODE=='ha':admin('backend',{'connection':F['connection']})
        else:admin('settings/connection',F['paas_connection'])
        ready()
        if PRODUCT=='odoo':switches(False)
        return {'management_api_configured':True,'initial_write_grants':False,'synthetic_ha_identity':MODE=='ha','haos':False}
    if PHASE=='enable':
        policy(True)
        if PRODUCT=='odoo':switches(True)
        ready();return {'permitted_tools':SELECTED[PRODUCT]}
    if PHASE=='revoke':policy(False);return {'write_grants_revoked':True}
    if PHASE=='child-denied':
        assert PRODUCT=='odoo';policy(True);switches(False)
    # Backend HTTP readiness precedes the gateway's periodic health observation.
    # Wait on management state, never retry a business tools/call.
    if PHASE in ('verify','cleanup'):ready()
    before=snapshot_native();m=MCP()
    try:
        if PHASE in ('denied','child-denied','final-denied'):
            STAGE='denied_write'
            if PRODUCT=='odoo':r=execute(m,'create',[{'name':MARK}])
            elif PRODUCT=='nextcloud':r=m.call('create_text_file',{'path':MARK+'.txt','content':'must-not-exist'})
            else:r=m.call('emqx_publish',{'topic':MARK+'/retained','payload':'must-not-exist','retain':True})
            error=denied(r)
            text=json.dumps(r).lower()
            if PHASE=='child-denied':assert 'writes' in text and ('disabled' in text or 'off' in text)
            elif MODE=='ha':assert 'unknown tool' in text
            else:assert 'disabled' in text
            after=snapshot_native();assert before==after
            error['expected_denial_reason']=True
            return {**error,'native_state_unchanged':True,'native_before':before,'native_after':after}
        if PHASE=='create':
            STAGE='create'
            if PRODUCT=='odoo':
                assert before['rows']==[];rid=good(execute(m,'create',[{'name':MARK,'email':'created@example.invalid'}]));assert isinstance(rid,int)
                owned={'id':rid,'marker':MARK};Path('/data/owned.json').write_text(json.dumps(owned))
                got=good(m.call('search_records',{'model':'res.partner','domain':[['name','=',MARK]],'fields':['id','name','email'],'limit':3}));assert got==[{'id':rid,'name':MARK,'email':'created@example.invalid'}]
            elif PRODUCT=='nextcloud':
                assert before['status']==404;good(m.call('create_text_file',{'path':MARK+'.txt','content':'created-'+MARK}));p=good(m.call('read_text_file',{'path':MARK+'.txt'}));assert p['content']=='created-'+MARK
                Path('/data/owned.json').write_text(json.dumps({'marker':MARK,'etag':p['etag']}))
            else:
                assert before['status']==404;good(m.call('emqx_publish',{'topic':MARK+'/retained','payload':'created-'+MARK,'retain':True}));p=good(m.call('emqx_get_retained',{'topic':MARK+'/retained'}));assert p['found'] and p['payload']=='created-'+MARK
                Path('/data/owned.json').write_text(json.dumps({'marker':MARK}))
            return {'write_read_passed':True,'native_after':snapshot_native()}
        owned=own();assert owned['marker']==MARK
        if PHASE=='update':
            STAGE='update'
            if PRODUCT=='odoo':assert good(execute(m,'write',[[owned['id']],{'email':'updated@example.invalid'}])) is True
            elif PRODUCT=='nextcloud':good(m.call('update_text_file',{'path':MARK+'.txt','content':'updated-'+MARK,'expected_etag':owned['etag']}))
            else:good(m.call('emqx_publish',{'topic':MARK+'/retained','payload':'updated-'+MARK,'retain':True}))
            return {'updated':True,'native_after':snapshot_native()}
        if PHASE=='error':
            STAGE='expected_error'
            if PRODUCT=='odoo':r=execute(m,'write',[[owned['id']],{'parity_nonexistent_field':MARK}])
            elif PRODUCT=='nextcloud':r=m.call('update_text_file',{'path':MARK+'.txt','content':'must-not-replace','expected_etag':'"parity-stale-etag"'})
            else:r=m.call('emqx_publish',{'topic':MARK+'/#','payload':'must-not-publish','retain':True})
            error=denied(r);text=json.dumps(r).lower()
            if PRODUCT=='odoo':assert 'parity_nonexistent_field' in text and 'invalid' in text
            elif PRODUCT=='nextcloud':assert any(x in text for x in ['etag_mismatch','etag','file changed'])
            else:assert 'wildcard' in text
            error['expected_error_reason']=True
            assert before==snapshot_native()
            return {**error,'native_state_unchanged':True,'error_case':{'odoo':'invalid_field_write','nextcloud':'stale_etag','emqx':'wildcard_topic'}[PRODUCT]}
        if PHASE=='verify':
            STAGE='verify_persisted'
            if PRODUCT=='odoo':
                rows=good(execute(m,'read',[[owned['id']]],{'fields':['id','name','email']}));assert rows==[{'id':owned['id'],'name':MARK,'email':'updated@example.invalid'}]
                assert snapshot_native()['rows']==rows
            elif PRODUCT=='nextcloud':
                p=good(m.call('read_text_file',{'path':MARK+'.txt'}));assert p['content']=='updated-'+MARK
                assert before['body_sha256']==hashlib.sha256(('updated-'+MARK).encode()).hexdigest()
            else:
                p=good(m.call('emqx_get_retained',{'topic':MARK+'/retained'}));assert p['found'] and p['payload']=='updated-'+MARK
                assert before['payload_sha256']==hashlib.sha256(('updated-'+MARK).encode()).hexdigest()
            return {'updated_value_read':True,'native_observation':before}
        if PHASE=='cleanup':
            STAGE='owned_cleanup'
            if PRODUCT=='odoo':
                assert before['rows'] and before['rows'][0]['id']==owned['id'];assert good(execute(m,'unlink',[[owned['id']]])) is True
                assert snapshot_native()['rows']==[]
            elif PRODUCT=='nextcloud':
                p=good(m.call('read_text_file',{'path':MARK+'.txt'}));good(m.call('delete_file_checked',{'path':MARK+'.txt','expected_etag':p['etag']}));assert snapshot_native()['status']==404
            else:good(m.call('emqx_delete_retained',{'topic':MARK+'/retained'}));assert snapshot_native()['status']==404
            return {'owned_record_removed':True,'native_after':snapshot_native()}
        raise AssertionError('unknown_phase')
    finally:m.close()

try:
    result=main();print('SAFE:'+json.dumps({'passed':True,'family':PRODUCT,'mode':MODE,'phase':PHASE,**result}))
except BaseException as e:
    frames=[];tb=e.__traceback__
    while tb:frames.append({'function':tb.tb_frame.f_code.co_name,'line':tb.tb_lineno});tb=tb.tb_next
    print('SAFE:'+json.dumps({'passed':False,'family':PRODUCT,'mode':MODE,'phase':PHASE,'stage':STAGE,'error_type':type(e).__name__,'frames':frames,'bodies_withheld':True}));sys.exit(1)
finally:A.close()
