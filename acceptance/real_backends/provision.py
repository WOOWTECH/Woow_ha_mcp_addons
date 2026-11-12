"""Prepare exact-image, same-pod loopback fixtures; no production endpoints."""
from common import *
import secrets
import time

def create_namespace():
    # Main's concrete resource lease is a technical coordination prerequisite.
    lease = json.loads((LANE/'MAIN-RESOURCE-LEASE.json').read_text())
    assert lease.get('execute_isolated_fixture') is True and lease['namespace'] == NS and lease['node'] == NODE
    assert dt.datetime.fromisoformat(lease['launch_before_UTC']) > dt.datetime.now(dt.timezone.utc)
    expiry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=lease['hard_stop_seconds_from_first_create'])).isoformat()
    assert not get('namespace', NS) and not (LANE/'run.json').exists()
    n = get('node', NODE); conditions = {x['type']:x['status'] for x in n['status']['conditions']}
    assert n['metadata']['uid']==lease['node_uid']
    assert conditions['Ready']=='True' and all(conditions[x]=='False' for x in ['MemoryPressure','DiskPressure','PIDPressure'])
    stats = json.loads(command(K+['get','--raw',f'/api/v1/nodes/{NODE}/proxy/stats/summary']))['node']
    assert stats['fs']['availableBytes'] > 15*1024**3 and stats['memory']['availableBytes'] > 8*1024**3
    rid = secrets.token_hex(4)
    command(K+['create','-f','-'],json.dumps({'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':{'acceptance.woowtech.io/run':rid,'acceptance.woowtech.io/data':'synthetic-only','pod-security.kubernetes.io/enforce':'baseline'},'annotations':{'cleanup-at':expiry}}}).encode())
    c={'run':rid,'namespace':NS,'namespace_uid':get('namespace',NS)['metadata']['uid'],'node':NODE,'node_uid':lease['node_uid'],'expiry':expiry,'created_at':now()}
    (LANE/'run.json').write_text(json.dumps(c,indent=2)+'\n')
    with (LANE/'watchdog-private.log').open('xb') as log:
        p=subprocess.Popen(['python3',str(ROOT/'cleanup.py'),'watchdog'],stdout=log,stderr=log,start_new_session=True)
    save('watchdog-start.json',{'pid':p.pid,'expiry':expiry})
    apply([item('NetworkPolicy','deny-all',{'podSelector':{},'policyTypes':['Ingress','Egress']}),item('ResourceQuota','budget',{'hard':{'pods':'1','requests.cpu':'1500m','limits.cpu':'5','requests.memory':'3Gi','limits.memory':'6Gi','persistentvolumeclaims':'0','requests.ephemeral-storage':'1Gi','limits.ephemeral-storage':'5Gi'}})])
    save('namespace-created.json',{'passed':True,**c,'capacity':{'memory':stats['memory']['availableBytes'],'disk':stats['fs']['availableBytes']}})

def item(kind,name,spec=None,**kwargs):
    x={'apiVersion':'networking.k8s.io/v1' if kind=='NetworkPolicy' else 'v1','kind':kind,'metadata':{'name':name,'namespace':NS,'labels':{'acceptance.woowtech.io/run':config()['run']}}}
    if spec is not None:x['spec']=spec
    x.update(kwargs);return x

def provision(family):
    c=guard();assert family in ('odoo','nextcloud','emqx')
    assert dt.datetime.now(dt.timezone.utc) < dt.datetime.fromisoformat(c['expiry'])
    assert get('node',NODE)['metadata']['uid']==c['node_uid']
    assert not json.loads(command(K+['-n',NS,'get','pods','-o','json']))['items']
    pw=secrets.token_urlsafe(30); admin=secrets.token_urlsafe(30); pg=secrets.token_urlsafe(30)
    conn={'odoo':{'url':'http://127.0.0.1:8069','database':'parityscratch','username':'parity_contact','password':pw},'nextcloud':{'url':'http://127.0.0.1:8082','username':'parity','app_password':pw},'emqx':{'url':'http://127.0.0.1:18083','api_key':'parity_'+c['run'],'api_secret':pw}}[family]
    fixture={'family':family,'connection':conn,'marker':'parity-'+c['run'],'admin_password':admin,'paas_connection':({'odoo_url':conn['url'],'odoo_db':conn['database'],'odoo_username':conn['username'],'odoo_password':pw} if family=='odoo' else {'base_url':conn['url'],'username':'parity','app_password':pw} if family=='nextcloud' else {})}
    conf='[options]\ndb_host = 127.0.0.1\ndb_port = 5432\ndb_user = odoo\ndb_password = '+pg+'\ndb_name = parityscratch\ndbfilter = ^parityscratch$\nlist_db = False\nadmin_passwd = '+admin+'\ndata_dir = /var/lib/odoo\nworkers = 0\nmax_cron_threads = 0\nhttp_interface = 0.0.0.0\nhttp_port = 8069\nlog_level = warn\n'
    secret={'fixture.json':json.dumps(fixture),'password':pw,'admin-password':admin,'pg-password':pg,'odoo.conf':conf,'emqx-api-keys':conn.get('api_key','unused')+':'+pw+':administrator\n','emqx-cookie':secrets.token_urlsafe(24)}
    apply([item('Secret',family+'-fixture',type='Opaque',stringData=secret)])
    volumes=[{'name':'fixture','secret':{'secretName':family+'-fixture','defaultMode':0o444}}]
    containers=[]
    def container(name,img,uid,cmd,paths,mem='768Mi',cpu='1'):
        mounts=[{'name':'fixture','mountPath':'/run/scratch','readOnly':True}]
        for index,path in enumerate(paths):
            vn=name+'-'+str(index)
            size='64Mi' if path=='/tmp' else '16Mi' if path=='/var/run/postgresql' else '1536Mi' if path=='/var/www/html' else '128Mi' if path=='/opt/emqx/log' else '1Gi' if name=='pg' else '512Mi'
            volumes.append({'name':vn,'emptyDir':{'sizeLimit':size}});mounts.append({'name':vn,'mountPath':path})
        z={'name':name,'image':img,'imagePullPolicy':'IfNotPresent','command':cmd,'securityContext':{'runAsUser':uid,'runAsGroup':uid,'runAsNonRoot':uid!=0,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'resources':{'requests':{'cpu':'100m','memory':'256Mi','ephemeral-storage':'128Mi'},'limits':{'cpu':cpu,'memory':mem,'ephemeral-storage':'1Gi'}},'volumeMounts':mounts}
        containers.append(z);return z
    if family=='odoo':
        z=container('pg',IMAGES['postgres'],999,['docker-entrypoint.sh','postgres'],['/var/lib/postgresql/data','/var/run/postgresql','/tmp'],'768Mi')
        z['env']=[{'name':'POSTGRES_USER','value':'odoo'},{'name':'POSTGRES_DB','value':'postgres'},{'name':'PGDATA','value':'/var/lib/postgresql/data/pgdata'},{'name':'POSTGRES_PASSWORD_FILE','value':'/run/scratch/pg-password'}]
        start="import socket,time,subprocess,os\nfor _ in range(90):\n try:\n  s=socket.create_connection(('127.0.0.1',5432),2);s.close();break\n except OSError:time.sleep(1)\nelse:raise SystemExit(2)\nargs=['odoo','-c','/run/scratch/odoo.conf','-d','parityscratch']\nif not os.path.exists('/var/lib/odoo/initialized'):\n subprocess.run(args+['-i','base','--without-demo=all','--stop-after-init'],check=True);open('/var/lib/odoo/initialized','w').close()\nos.execvp('odoo',args)"
        container('backend',IMAGES['odoo'],100,['python3','-u','-c',start],['/var/lib/odoo','/tmp'],'2Gi','2')
    elif family=='nextcloud':
        start='set -eu\nif [ ! -e /var/www/html/occ ]; then cp -R --no-preserve=all /usr/src/nextcloud/. /var/www/html/; fi\ncd /var/www/html\nif [ ! -e config/installed-by-parity ]; then php occ maintenance:install --database sqlite --admin-user parity --admin-pass "$(cat /run/scratch/password)" --data-dir /var/www/html/data; php occ config:system:set trusted_domains 1 --value 127.0.0.1; touch config/installed-by-parity; fi\nexec php -S 0.0.0.0:8082 -t /var/www/html'
        container('backend',IMAGES['nextcloud'],33,['sh','-c',start],['/var/www/html','/tmp'],'2Gi','2')
    else:
        z=container('backend',IMAGES['emqx'],1000,['/usr/bin/docker-entrypoint.sh','/opt/emqx/bin/emqx','foreground'],['/opt/emqx/data','/opt/emqx/log','/tmp'],'2Gi','2')
        z['env']=[{'name':'EMQX_NODE__NAME','value':'emqx@127.0.0.1'},{'name':'EMQX_NODE__COOKIE','valueFrom':{'secretKeyRef':{'name':family+'-fixture','key':'emqx-cookie'}}},{'name':'EMQX_API_KEY__BOOTSTRAP_FILE','value':'/run/scratch/emqx-api-keys'},{'name':'EMQX_DASHBOARD__DEFAULT_PASSWORD','valueFrom':{'secretKeyRef':{'name':family+'-fixture','key':'admin-password'}}},{'name':'EMQX_RETAINER__BACKEND__STORAGE_TYPE','value':'disc'}]
    holder='import time;time.sleep(10800)'
    container('ha',IMAGES['ha_'+family],10001,[PY,'-c',holder],['/data','/tmp'])
    if 'paas_'+family in IMAGES:
        z=container('paas',IMAGES['paas_'+family],1000,['python3','-c',holder],['/data','/tmp'])
        z['env']=[{'name':'WEBHOOK_SECURITY_MODE','value':'moderate'}]
    pod=item('Pod',family,{'nodeSelector':{'kubernetes.io/hostname':NODE},'restartPolicy':'Always','activeDeadlineSeconds':10800,'terminationGracePeriodSeconds':15,'automountServiceAccountToken':False,'securityContext':{'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},'containers':containers,'volumes':volumes})
    pod['spec']['activeDeadlineSeconds']=max(1,int((dt.datetime.fromisoformat(c['expiry'])-dt.datetime.now(dt.timezone.utc)).total_seconds()))
    if get('secret','owned-registry-pull',NS):pod['spec']['imagePullSecrets']=[{'name':'owned-registry-pull'}]
    # fsGroup grants all non-root users write access to their own separate volumes.
    apply([pod]);save(family+'-pod-spec.json',pod)
    command(K+['-n',NS,'wait','pod/'+family,'--for=condition=Ready','--timeout=240s'],timeout=250)
    actual=get('pod',family,NS)
    proof=[]
    for s in actual['status']['containerStatuses']:
        wanted=next(x['image'] for x in containers if x['name']==s['name'])
        assert s['imageID'].endswith(wanted.split('@')[1])
        proof.append({'container':s['name'],'image':wanted,'image_id':s['imageID'],'restart_count':s['restartCount']})
    save(family+'-runtime-images.json',{'at':now(),'pod_uid':actual['metadata']['uid'],'images':proof,'no_service_no_ingress_no_network_egress':True})

if __name__=='__main__':
    import sys
    create_namespace() if sys.argv[1]=='namespace' else provision(sys.argv[1])
