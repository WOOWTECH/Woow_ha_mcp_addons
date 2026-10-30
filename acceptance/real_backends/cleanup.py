from common import *
import sys
import time

def cleanup():
    c=config()
    if get('namespace',NS):
        guard();command(K+['delete','namespace',NS,'--wait=false'])
    for _ in range(120):
        if get('namespace',NS) is None:break
        time.sleep(2)
    else:raise RuntimeError('namespace_cleanup_pending')
    pvs=json.loads(command(K+['get','pv','-o','json']))['items']
    assert not any(p['spec'].get('claimRef',{}).get('namespace')==NS for p in pvs)
    n=get('node',NODE);assert n['metadata']['uid']==c['node_uid']
    assert next(x['status'] for x in n['status']['conditions'] if x['type']=='Ready')=='True'
    save('cleanup-'+str(time.time_ns())+'.json',{'at':now(),'passed':True,'namespace':NS,'namespace_uid':c['namespace_uid'],'namespace_absent':True,'pv_claims_absent':True,'no_pvc_used':True,'owned_secrets_removed':True,'node_ready':True})
    print(json.dumps({'cleanup_passed':True}))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='watchdog':
        while dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(config()['expiry']):
            if get('namespace',NS) is None:
                save('watchdog-exit.json',{'namespace_absent':True,'at':now()});sys.exit(0)
            time.sleep(10)
    cleanup()
