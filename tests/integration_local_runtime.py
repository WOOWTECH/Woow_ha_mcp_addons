"""LOCAL MOCK, not HA: real bootstrap/guard/n8n/provider/core/browser integration.

Only owned loopback WS/backend; injected roles for the six unapproved products
exist in this test process alone. Browser install is explicit, not auto-download.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sys
import tempfile

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from websockets.asyncio.server import serve

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from test_real_n8n import fake_backend
from test_real_products import rpc
from batch2_owned_port import reserve_port
from owned_executable import Executable
from owned_runtime import forbidden_transport
from owned_browser import browser_proofs

ROOT = Path(__file__).resolve().parents[1]
MACHINE = 'INVENTED-LOCAL-MACHINE-ONLY'


def free_port():
    with reserve_port() as s:
        return s.getsockname()[1]


async def test_real_packaging_guard_provider_and_chromium(fake_backend, monkeypatch):
    backend, events = fake_backend
    assert os.getuid() == 0, 'actual bootstrap uid10001 integration requires local root'
    # Existing prebuilt assets only; never build/install or mutate MAIN's assets.
    ui_dist = Path(os.environ.get('OWNED_UI_DIST', str(ROOT/'packages/mcp-admin-ui/dist'))).resolve()
    assert (ui_dist/'index.html').is_file(), 'provide existing OWNED_UI_DIST assets'
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}
    role = {'mode':'owner', 'queries':0}
    ws_errors = []
    async def websocket(ws):
        try:
            assert ws.request.path == '/core/websocket'
            assert ws.request.headers['Host'] == 'supervisor'
            await ws.send(json.dumps({'type':'auth_required','ha_version':'2026.7.2'}))
            assert json.loads(await ws.recv()) == {'type':'auth','access_token':MACHINE}
            await ws.send(json.dumps({'type':'auth_ok','ha_version':'2026.7.2'}))
            assert json.loads(await ws.recv()) == {'id':1,'type':'config/auth/list'}
            role['queries'] += 1
            if role['mode'] == 'error':
                await ws.send('{malformed'); return
            await ws.send(json.dumps({'id':1,'type':'result','success':True,'result':[
                {'id':'owner','is_active':True,'is_owner':role['mode']=='owner','system_generated':False,'group_ids':['system-admin'] if role['mode']=='admin' else []},
                {'id':'nonadmin','is_active':True,'is_owner':False,'system_generated':False,'group_ids':[]},
            ]}))
            await ws.wait_closed()
        except Exception:
            # Transport abort after decision is expected; assertion failures aren't.
            import traceback
            if sys.exc_info()[0] is AssertionError: ws_errors.append(traceback.format_exc())

    processes, stores = [], []
    control_server = None
    control_task = None
    with tempfile.TemporaryDirectory(prefix='woow-integrated-') as directory:
        temp = Path(directory)
        temp.chmod(0o755)
        # Readable owned interpreter/venv; do not chmod any existing private home.
        interpreter = Path(sys.executable).resolve().parents[1]
        shutil.copytree(interpreter, temp/'python', symlinks=True)
        shutil.copytree(ROOT/'.venv', temp/'.venv', symlinks=True)
        for p in (temp/'.venv/bin').glob('python*'): p.unlink()
        (temp/'.venv/bin/python').symlink_to(temp/'python/bin/python3.13')
        (temp/'.venv/pyvenv.cfg').write_text(f'home = {temp}/python/bin\ninclude-system-site-packages = false\nversion = 3.13.2\n')
        (temp/'packages').symlink_to(ROOT/'packages', target_is_directory=True)
        (temp/'apps').symlink_to(ROOT/'apps', target_is_directory=True)
        (temp/'packaging').mkdir()
        (temp/'data').mkdir()
        shutil.copytree(ui_dist, temp/'ui-dist')
        from mcp_admin_core import ui
        monkeypatch.setattr(ui, 'UI_ROOT', temp/'ui-dist')
        shutil.copyfile(ROOT/'tests/integration_runtime_wrapper.py', temp/'packaging/management_launcher.py')
        data = temp/'data/mcp'
        (temp/'child-check.cjs').write_text("""
const fs=require('node:fs');
if ('SUPERVISOR_TOKEN' in process.env || fs.readFileSync('/proc/self/environ').includes('SUPERVISOR_TOKEN')) throw Error('machine inherited');
for (const file of ['environ','mem']) {
  try { const fd=fs.openSync(`/proc/${process.ppid}/${file}`,'r'); fs.closeSync(fd); throw Error('parent readable'); }
  catch(e) { if (!['EACCES','EPERM'].includes(e.code)) throw e; }
}
if (fs.readFileSync(`/proc/${process.ppid}/cmdline`).includes('INVENTED-LOCAL-MACHINE-ONLY')) throw Error('machine argv');
fs.writeFileSync(process.env.HOME+'/real-child-guard',String(process.pid));
""")
        async with (serve(websocket, '127.0.0.1', 0) as ws,
                    httpx.AsyncClient(trust_env=False) as client,
                    httpx.AsyncClient(transport=forbidden_transport()) as forms_child):
            admin_port, mcp_port, control_port = free_port(), free_port(), free_port()
            runner = Executable(data, 'n8n', [admin_port, mcp_port])
            runner.config['trace'] = str(data/'owned-lifecycle.jsonl')
            client.event_hooks['request'].append(runner.guard)
            config={'source':str(ROOT),'data':str(data),'admin_port':admin_port,'mcp_port':mcp_port,
                    'ws_port':ws.sockets[0].getsockname()[1], 'owned_runtime':runner.config,
                    'ui_dist':str(temp/'ui-dist')}
            (temp/'local-test.json').write_text(json.dumps(config))
            # The real entrypoint (not a copied approximation) owns prepare/drop/
            # exec; only fixed filesystem root/data are relocated in this test.
            launch = (
                'import importlib.util,pathlib,sys; '
                f's=importlib.util.spec_from_file_location("entry",{str(ROOT/"packaging/entrypoint.py")!r}); '
                'e=importlib.util.module_from_spec(s); s.loader.exec_module(e); '
                f'e.ROOT=pathlib.Path({str(temp)!r}); '
                'prepare=e.prepare_data; e.prepare_data=lambda:prepare(e.ROOT/"data"); '
                'sys.argv=["entrypoint.py","n8n"]; e.main()')
            runner.release()
            process = await asyncio.create_subprocess_exec(sys.executable,'-c',launch,env={**env,'SUPERVISOR_TOKEN':MACHINE},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            processes.append(process)
            try:
                await runner.ready(process, timeout=35)
                initial_public = await runner.guard_url(f'http://127.0.0.1:{admin_port}/api/bootstrap')
                initial_child = await runner.guard_url(runner.child_url)
                async with asyncio.timeout(35):
                    while True:
                        assert process.returncode is None, 'bootstrap/runtime exited'
                        try:
                            r=await client.get(f'http://127.0.0.1:{admin_port}/api/bootstrap')
                            if r.status_code==200: break
                        except httpx.HTTPError: pass
                        await asyncio.sleep(.1)
                assert (data/'factory-called').read_text()=='real factory'
                async with asyncio.timeout(30):
                    while not (data/'real-child-guard').exists(): await asyncio.sleep(.1)
                child_pid=int((data/'real-child-guard').read_text())
                assert Path(f'/proc/{child_pid}').exists()
                assert MACHINE.encode() not in Path(f'/proc/{process.pid}/cmdline').read_bytes()
                assert MACHINE not in (data/'state.json').read_text()
                assert MACHINE not in r.text
                assert r.json()['policy_contract']=='woow-v3-exact-grants'
                state = json.loads((data/'state.json').read_text())
                endpoint = f'http://127.0.0.1:{mcp_port}/mcp'
                headers = {'Authorization':'Bearer '+state['token'], 'Accept':'application/json, text/event-stream'}
                init = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                    'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'local-integrated','version':'1'}}}
                async with asyncio.timeout(30):
                    while True:
                        try:
                            initialized = await rpc(client,endpoint,headers,init)
                            break
                        except ValueError: await asyncio.sleep(.1)
                assert initialized['serverInfo']['name']=='n8n-documentation-mcp'
                assert initialized['serverInfo']['version']=='2.91.0'
                headers['MCP-Protocol-Version']=initialized['protocolVersion']
                await rpc(client,endpoint,headers,{'jsonrpc':'2.0','method':'notifications/initialized'})
                documentation=await rpc(client,endpoint,headers,{'jsonrpc':'2.0','id':2,'method':'tools/call',
                    'params':{'name':'tools_documentation','arguments':{'topic':'overview'}}})
                assert not documentation.get('isError') and documentation['content']
                assert MACHINE not in json.dumps(documentation)
                assert (await client.get(f'http://127.0.0.1:{admin_port}/api/bootstrap',headers={'x-remote-user-id':'nonadmin'})).status_code==403
                role['mode']='admin'
                assert (await client.get(f'http://127.0.0.1:{admin_port}/')).status_code==200
                role['mode']='owner'
                for path in ('/','/assets/app.js','/api/bootstrap'):
                    assert (await client.get(f'http://127.0.0.1:{mcp_port}'+path)).status_code==404

                # Six products exercise their real typed Core API, not production
                # role approval or native runtime. No backend callback/network.
                apps={}
                for product in TOOLS:
                    store=ProductStore(temp/('form-'+product),product); stores.append(store)
                    async def local_role(_): return True
                    apps[product],_=make_apps(store,TOOLS[product],forms_child,verify_admin=local_role)
                async def control(request):
                    value=await request.json()
                    assert value['mode'] in ('owner','admin','demoted','error')
                    role['mode']=value['mode']
                    return JSONResponse({'ok':True,'queries':role['queries']})
                controls=Starlette(routes=[Route('/__local/role',control,methods=['POST'])])
                active_forms = {}
                peak_forms = {}
                async def local_app(scope,receive,send):
                    path=scope['path']
                    if path.startswith('/local-product/'):
                        product=path.split('/')[2]
                        base='/local-product/'+product
                        scope={**scope,'client':('172.30.32.2',1),'headers':[*scope['headers'],(b'x-remote-user-id',b'owner'),(b'x-ingress-path',base.encode())]}
                        active_forms[product] = active_forms.get(product, 0) + 1
                        peak_forms[product] = max(peak_forms.get(product, 0), active_forms[product])
                        async def observed_send(message):
                            if message['type'] == 'http.response.start' and message['status'] >= 400:
                                print('BT1_FORM_RESPONSE', json.dumps({'product': product,
                                    'operation': 'bootstrap' if path.endswith('/api/bootstrap') else 'asset',
                                    'status': message['status'], 'active': active_forms[product]}))
                            await send(message)
                        try:
                            return await apps[product](scope,receive,observed_send)
                        finally:
                            active_forms[product] -= 1
                    await controls(scope,receive,send)
                control_server=uvicorn.Server(uvicorn.Config(local_app,host='127.0.0.1',port=control_port,log_level='error',access_log=False,lifespan='off'))
                control_task=asyncio.create_task(control_server.serve())
                async with asyncio.timeout(5):
                    while not control_server.started: await asyncio.sleep(.01)
                async with browser_proofs(runner, control_port) as (proof_fd, instance, browser_handle):
                    browser=await asyncio.create_subprocess_exec('node',str(ROOT/'packages/mcp-admin-ui/tests/integrated-browser.mjs'),
                        env={**env,'PLAYWRIGHT_BROWSERS_PATH':'0','LOCAL_ADMIN':f'http://127.0.0.1:{admin_port}',
                             'LOCAL_CONTROL':f'http://127.0.0.1:{control_port}','LOCAL_BACKEND':backend,
                             'OWNED_PROOF_FD':str(proof_fd),'OWNED_PROOF_INSTANCE':instance},
                        pass_fds=(proof_fd,), stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    browser_handle['process'] = browser
                    processes.append(browser)
                    out,err=await asyncio.wait_for(browser.communicate(),120)
                assert MACHINE.encode() not in out+err
                assert browser.returncode==0, (out+err).decode()
                print(out.decode().strip())
                final_public = await runner.guard_url(f'http://127.0.0.1:{admin_port}/api/bootstrap')
                final_child = await runner.guard_url(runner.child_url)
                assert final_public['proof'] == initial_public['proof']
                assert final_public['generation'] == initial_public['generation'] == 1
                assert final_child['generation'] == initial_child['generation'] + 2
                assert final_child['proof'] != initial_child['proof']
                assert not Path(f'/proc/{initial_child["proof"][0]}').exists()
                print('BT1_IPC', json.dumps({'public_stable': True,
                    'initial_child': initial_child['proof'], 'final_child': final_child['proof'],
                    'generation': final_child['generation']}))
                assert role['queries']>30 and not ws_errors
                assert MACHINE not in (data/'state.json').read_text()
                state=json.loads((data/'state.json').read_text())
                assert state['schema_version']==3 and state['enabled_write_tools']==[] and not state['writes_enabled']
                assert state['endpoint']=='https://client.example.test:8081/mcp'
                assert state['token'] is None
                assert (await client.post(endpoint,headers=headers,json=init)).status_code==401
                assert all(request.startswith(b'GET /api/v1/workflows') for request in events)  # only owned health reads
                child_pid=int((data/'real-child-guard').read_text())
                process.send_signal(signal.SIGTERM)
                out,err=await asyncio.wait_for(process.communicate(),15)
                assert process.returncode==0 and MACHINE.encode() not in out+err
                assert not Path(f'/proc/{child_pid}').exists(), 'orphan real child'
            finally:
                if control_server: control_server.should_exit=True
                if control_task: await asyncio.wait_for(control_task,5)
                for p in processes:
                    if p.returncode is None:
                        p.terminate()
                        try: await asyncio.wait_for(p.communicate(),15)
                        except TimeoutError:
                            p.kill(); await asyncio.wait_for(p.communicate(),5)
                            pytest.fail('owned integration subprocess did not stop')
                if 'peak_forms' in locals():
                    print('BT1_FORM_PEAK', json.dumps(peak_forms))
                for store in stores:
                    try:
                        store.load()
                        print('BT1_STORE', store.product, 'valid')
                    except Exception as error:
                        print('BT1_STORE', store.product, type(error).__name__)
                    store.close()
                trace = data/'owned-lifecycle.jsonl'
                if trace.exists():
                    metadata = trace.read_text()
                    print('BT1_LIFECYCLE ' + metadata)
                    child_pids = {item['child_pid'] for line in metadata.splitlines()
                                  if (item := json.loads(line))['child_pid'] is not None}
                    assert all(not Path(f'/proc/{pid}').exists() for pid in child_pids), 'owned child not reaped'
                    print('BT1_CLEANUP', json.dumps({'child_pids': sorted(child_pids),
                        'children_reaped': True, 'processes': [
                            {'pid': p.pid, 'exit': p.returncode} for p in processes]}))
