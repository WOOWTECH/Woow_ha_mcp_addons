"""Institutional registry pull identity; no customer/backend credentials."""
import base64
import urllib.request
from common import *

REGISTRY='jcr-prod.woowtech.io'
def registry_auth():
    source_namespace=os.environ.get('REGISTRY_SOURCE_NAMESPACE','paas-ws-b83741fc')
    source_name=os.environ.get('REGISTRY_SOURCE_SECRET','paas-registry')
    secret=json.loads(command(K+['-n',source_namespace,'get','secret',source_name,'-o','json']))
    assert secret['type']=='kubernetes.io/dockerconfigjson'
    auths=json.loads(base64.b64decode(secret['data']['.dockerconfigjson']))['auths']
    values=[v for k,v in auths.items() if k.removeprefix('https://').rstrip('/')==REGISTRY]
    assert len(values)==1
    value=values[0]
    return value.get('auth') or base64.b64encode((value['username']+':'+value['password']).encode()).decode()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('registry_redirect_refused')

def verify(product):
    reference=IMAGES['paas_'+product];repository=reference.split('/',1)[1].split('@')[0].split(':')[0]
    wanted=reference.split('@')[1];auth=registry_auth();opener=urllib.request.build_opener(NoRedirect())
    def fetch(path):
        request=urllib.request.Request('https://'+REGISTRY+'/v2/'+repository+path,headers={'Authorization':'Basic '+auth,'Accept':'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json','User-Agent':'curl/8.7.1'})
        with opener.open(request,timeout=30) as r:
            data=r.read(4*1024*1024+1);assert len(data)<=4*1024*1024;return data
    manifest=fetch('/manifests/'+wanted);assert 'sha256:'+digest(manifest)==wanted
    cfgdigest=json.loads(manifest)['config']['digest'];config_bytes=fetch('/blobs/'+cfgdigest);assert 'sha256:'+digest(config_bytes)==cfgdigest
    image=json.loads(config_bytes);assert image['architecture']=='amd64'
    save(product+'-registry-verification.json',{'passed':True,'at':now(),'image':reference,'manifest_digest':wanted,'config_digest':cfgdigest,'os':image['os'],'architecture':image['architecture'],'user':image['config'].get('User'),'authenticated_manifest_and_config_bytes_hashed':True,'credentials_logged':False})

def ensure_pull_secret():
    from provision import item
    guard()
    if get('secret','owned-registry-pull',NS):return
    docker={'auths':{REGISTRY:{'auth':registry_auth()}}}
    apply([item('Secret','owned-registry-pull',type='kubernetes.io/dockerconfigjson',data={'.dockerconfigjson':base64.b64encode(json.dumps(docker).encode()).decode()})])

if __name__=='__main__':
    import sys
    ensure_pull_secret() if sys.argv[1]=='prepare' else verify(sys.argv[1])
