"""Bounded acceptance phases. Failed attempts remain; mutation phases never auto-retry."""
from common import *
import sys
import time

def launch(family,mode):
    if mode=='ha':
        runtime=(ROOT/'ha_runtime.py').read_text()
        code='import json,subprocess\nfrom pathlib import Path\np=Path("/tmp/ha_runtime.py");p.write_text('+repr(runtime)+')\nf=open("/tmp/ha-private.log","wb")\nc=subprocess.Popen(["'+PY+'",str(p)],stdout=f,stderr=f,start_new_session=True)\nPath("/data/runtime.pid").write_text(str(c.pid))\nprint(json.dumps({"pid":c.pid}))'
    else:
        code='''import json,subprocess,os
from pathlib import Path
from mcp_admin_core.config.store import fresh_config
f=json.loads(Path('/run/scratch/fixture.json').read_text())
p=Path('/data/config.json')
if not p.exists():
 c=fresh_config();c['admin_password']=f['admin_password'];c['proxy']['timeout']=60
 p.write_text(json.dumps(c));p.chmod(0o600)
log=open('/tmp/paas-private.log','wb')
c=subprocess.Popen(['uvicorn',f['family']+'_mcp_admin.main:app','--host','127.0.0.1','--port','8080','--no-access-log'],stdout=log,stderr=log,start_new_session=True)
Path('/data/runtime.pid').write_text(str(c.pid))
print(json.dumps({'pid':c.pid}))
'''
    answer=json.loads(exec_code(family,mode,code));save(family+'-'+mode+'-launch-'+str(time.time_ns())+'.json',answer)
    code='''import httpx,time,json
for _ in range(80):
 try:
  r=httpx.get(URL,headers=HEADERS,timeout=2,trust_env=False)
  if r.status_code==200:break
 except Exception:pass
 time.sleep(.5)
else:raise RuntimeError('admin_unavailable')
print(json.dumps({'http_status':r.status_code}))
'''
    url='http://127.0.0.1:8099/api/bootstrap' if mode=='ha' else 'http://127.0.0.1:8080/healthz'
    headers={'X-Remote-User-Id':'04404404404404404404404404404404'} if mode=='ha' else {}
    return json.loads(exec_code(family,mode,'URL='+repr(url)+'\nHEADERS='+repr(headers)+'\n'+code))

def backend_ready(family):
    code='''import httpx,time,json
from pathlib import Path
f=json.loads(Path('/run/scratch/fixture.json').read_text());c=f['connection']
path={'odoo':'/web/login','nextcloud':'/status.php','emqx':'/api/v5/status'}[f['family']]
for _ in range(180):
 try:
  r=httpx.get(c['url']+path,timeout=3,trust_env=False)
  if r.status_code==200:break
 except Exception:pass
 time.sleep(1)
else:raise RuntimeError('backend_unavailable')
print(json.dumps({'backend_ready':True,'http_status':r.status_code}))
'''
    return json.loads(exec_code(family,'ha',code,timeout=210))

def setup_odoo():
    code='''import json
from pathlib import Path
assert env.cr.dbname=='parityscratch'
assert not env['ir.module.module'].search_count([('name','in',['mail','account','payment']),('state','=','installed')])
assert not env['res.users'].sudo().search_count([('login','=','parity_contact')])
admin=env.ref('base.user_admin');admin.sudo().write({'password':Path('/run/scratch/admin-password').read_text().strip()})
user=env['res.users'].with_context(no_reset_password=True,tracking_disable=True).sudo().create({'name':'Parity synthetic tester','login':'parity_contact','password':Path('/run/scratch/password').read_text().strip(),'groups_id':[(6,0,[env.ref('base.group_user').id,env.ref('base.group_partner_manager').id])]})
assert not user.has_group('base.group_system') and not user.has_group('base.group_erp_manager')
for mode in ['read','create','write','unlink']:env['res.partner'].with_user(user).check_access_rights(mode)
env.cr.commit()
print('SAFE:'+json.dumps({'uid':user.id,'non_admin':True,'partner_crud_acl':True,'mail_account_payment_absent':True}))
'''
    guard();raw=command(K+['-n',NS,'exec','-i','odoo','-c','backend','--','odoo','shell','-c','/run/scratch/odoo.conf','-d','parityscratch'],code.encode(),180)
    rows=[json.loads(x[5:]) for x in raw.decode().splitlines() if x.startswith('SAFE:')];assert len(rows)==1
    save('odoo-account.json',rows[0])

def snapshot(label):
    guard()
    sql="SELECT COALESCE(jsonb_agg(to_jsonb(p) ORDER BY id),'[]'::jsonb) FROM res_partner p"
    raw=command(K+['-n',NS,'exec','odoo','-c','pg','--','psql','-U','odoo','-d','parityscratch','-At','-v','ON_ERROR_STOP=1','-c',sql])
    rows=json.loads(raw);value={'row_count':len(rows),'all_partner_rows_sha256':digest(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()),'marker_count':sum(r.get('name','').startswith('parity-'+config()['run']) for r in rows)}
    save('odoo-native-'+label+'-'+str(time.time_ns())+'.json',value);return value

def source_proof(family,mode):
    source='28b8317ec12c47c81c946fe9aaec18dd1d5ad852' if mode=='ha' else 'f748090eb782bc103edcd99ac9aa821f77294fb0'
    repo=ROOT.parents[1] if mode=='ha' else Path('/data/pi-agent/home/work/paas-parity-integration-20261029')
    paths=['packages/mcp-admin-core/mcp_admin_core/'+n for n in (['gateway.py','products.py','surface.py','policy.py','lifecycle.py','health.py','run_product.py'] if mode=='ha' else ['app.py','proxy.py','process.py','launch_policy.py','tool_filter.py','config/store.py'])]
    if mode=='ha' and family in ('nextcloud','emqx'):
        paths += [str(p.relative_to(repo)) for p in (repo/'apps'/family/'vendor').rglob('*.py')]
    if mode=='paas':paths += ['apps/'+family+'/'+family+'_mcp_admin/'+p for p in ['main.py','tool_registry.py','routers/config.py']]
    if mode=='paas' and family=='nextcloud':
        paths += [str(p.relative_to(repo)) for p in (repo/'apps/nextcloud/nextcloud_mcp_server').glob('*.py')]
    expected={p:digest(command(['git','-C',str(repo),'show',source+':'+p])) for p in paths}
    code='import json,hashlib\nfrom pathlib import Path\nexpected='+repr(expected)+'\nroot=Path('+repr('/opt/woow' if mode=='ha' else '/app')+')\nactual={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in expected}\nprint(json.dumps({"actual":actual,"matches":actual==expected}))'
    result=json.loads(exec_code(family,mode,code));save(family+'-'+mode+'-source-proof.json',{'source':source,'expected':expected,**result});assert result['matches']

def phase(family,mode,name):
    code='MODE='+repr(mode)+'\nPHASE='+repr(name)+'\n'+(ROOT/'probe.py').read_text()
    guard();p=subprocess.run(K+['-n',NS,'exec','-i',family,'-c',mode,'--',PY if mode=='ha' else 'python3','-'],input=code.encode(),capture_output=True,timeout=240)
    rows=[json.loads(l[5:]) for l in p.stdout.decode().splitlines() if l.startswith('SAFE:')]
    result=rows[0] if len(rows)==1 else {'passed':False,'phase':name,'mode':mode,'family':family,'exit_code':p.returncode,'safe_receipt_missing':True,'stderr_sha256':digest(p.stderr)}
    save(family+'-'+mode+'-'+name+'-'+str(time.time_ns())+'.json',result)
    print(json.dumps(result),flush=True)
    assert p.returncode==0 and result['passed'], 'phase_failed'
    return result

def restart_backend(family, receipt_name=None):
    p=get('pod',family,NS);uid=p['metadata']['uid'];old=next(x for x in p['status']['containerStatuses'] if x['name']=='backend')['restartCount']
    guard()
    cmd=['python3','-c','import os,signal;os.kill(1,signal.SIGTERM)'] if family=='odoo' else ['php','-r','posix_kill(1,2);'] if family=='nextcloud' else ['/opt/emqx/bin/emqx','stop']
    # Stopping PID 1 may terminate the exec stream even after a clean shutdown.
    # Never retry the stop: Kubernetes restartCount and backend readiness decide.
    stop=subprocess.run(K+['-n',NS,'exec',family,'-c','backend','--']+cmd,capture_output=True,timeout=45)
    for _ in range(90):
        p=get('pod',family,NS);assert p['metadata']['uid']==uid
        s=next(x for x in p['status']['containerStatuses'] if x['name']=='backend')
        if s['restartCount']>old and s['ready']:break
        time.sleep(1)
    else:raise RuntimeError('backend_restart_unobserved')
    backend_ready(family)
    save(receipt_name or family+'-restart.json',{'passed':True,'pod_uid':uid,'before':old,'after':s['restartCount'],'stop_exec_returncode':stop.returncode,'stop_stderr_sha256':digest(stop.stderr),'same_emptydir_data':True,'scope':'container restart only; no PVC/pod-reschedule persistence claim'})

def restart_gateway(family,mode):
    path='/data/mcp/state.json' if mode=='ha' else '/data/config.json'
    code='import hashlib,json\nfrom pathlib import Path\nprint(json.dumps({"sha256":hashlib.sha256(Path('+repr(path)+').read_bytes()).hexdigest()}))'
    before=json.loads(exec_code(family,mode,code))
    p=get('pod',family,NS);uid=p['metadata']['uid'];old=next(x['restartCount'] for x in p['status']['containerStatuses'] if x['name']==mode)
    exec_code(family,mode,'import os,signal;os.kill(1,signal.SIGINT)')
    for _ in range(90):
        p=get('pod',family,NS);assert p['metadata']['uid']==uid
        s=next(x for x in p['status']['containerStatuses'] if x['name']==mode)
        if s['restartCount']>old and s['ready']:break
        time.sleep(1)
    else:raise RuntimeError('gateway_restart_unobserved')
    launch(family,mode)
    after=json.loads(exec_code(family,mode,code));assert before==after
    save(family+'-'+mode+'-gateway-restart.json',{'passed':True,'pod_uid':uid,'restart_before':old,'restart_after':s['restartCount'],'state_bytes_equal':True,'state_sha256':after['sha256'],'scope':'container restart and shipped runtime startup; emptyDir data retained'})

def run_family(family):
    guard();backend_ready(family)
    if family=='odoo':setup_odoo()
    modes=['ha','paas'] if 'paas_'+family in IMAGES else ['ha']
    baseline=snapshot('baseline') if family=='odoo' else None
    for mode in modes:
        denial_baseline=snapshot(mode+'-before-denial') if family=='odoo' else None
        source_proof(family,mode);launch(family,mode)
        phase(family,mode,'configure');phase(family,mode,'denied')
        if family=='odoo':
            phase(family,mode,'child-denied');assert snapshot(mode+'-denied')==denial_baseline
        phase(family,mode,'enable');phase(family,mode,'create');phase(family,mode,'update');phase(family,mode,'error');phase(family,mode,'verify')
    restart_backend(family)
    for mode in modes:
        phase(family,mode,'verify');phase(family,mode,'cleanup');phase(family,mode,'revoke');phase(family,mode,'final-denied')
        restart_gateway(family,mode);phase(family,mode,'final-denied')
    if family=='odoo':assert snapshot('restored')==baseline
    save(family+'-acceptance.json',{'passed':True,'modes':modes,'real_backend':True,'backend_restart_persistence':True,'native_effect_oracle':True,'owned_records_cleaned':True,'ha_identity_synthetic':True,'haos':False,'full_partner_rows_restored':family=='odoo'})

def remove_family(family):
    guard();accepted=json.loads((E/(family+'-acceptance.json')).read_text());assert accepted['passed'] and accepted['owned_records_cleaned']
    pod=get('pod',family,NS);proof=json.loads((E/(family+'-runtime-images.json')).read_text())
    assert pod and pod['metadata']['uid']==proof['pod_uid'] and pod['metadata']['labels']['acceptance.woowtech.io/run']==config()['run']
    command(K+['-n',NS,'delete','pod',family,'--wait=true','--timeout=90s'],timeout=100)
    secret=get('secret',family+'-fixture',NS);assert secret['metadata']['labels']['acceptance.woowtech.io/run']==config()['run']
    command(K+['-n',NS,'delete','secret',family+'-fixture'])
    assert get('pod',family,NS) is None and get('secret',family+'-fixture',NS) is None
    save(family+'-family-cleanup.json',{'passed':True,'at':now(),'pod_uid':proof['pod_uid'],'pod_absent':True,'owned_secret_absent':True,'emptydirs_deleted':True})

if __name__=='__main__':
    try:
        action=sys.argv[1];family=sys.argv[2]
        if action=='run':run_family(family)
        elif action=='launch':launch(family,sys.argv[3])
        elif action=='phase':phase(family,sys.argv[3],sys.argv[4])
        elif action=='source':source_proof(family,sys.argv[3])
        elif action=='restart':restart_backend(family)
        elif action=='restart-gateway':restart_gateway(family,sys.argv[3])
        elif action=='ready':print(backend_ready(family))
        elif action=='setup':setup_odoo()
        elif action=='snapshot':print(snapshot(sys.argv[3]))
        elif action=='remove':remove_family(family)
    except BaseException as e:
        frames=[];tb=e.__traceback__
        while tb:frames.append({'function':tb.tb_frame.f_code.co_name,'line':tb.tb_lineno});tb=tb.tb_next
        result={'passed':False,'at':now(),'action':sys.argv[1:],'error_type':type(e).__name__,'frames':frames}
        save('failure-'+str(time.time_ns())+'.json',result);print(json.dumps(result));sys.exit(1)
