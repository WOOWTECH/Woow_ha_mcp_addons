"""Node fetch and browser-origin guards without invoking the final joined run."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import socket

import pytest

from owned_browser import browser_proofs


async def test_node_origins_and_fresh_inherited_channel():
    calls = []
    async def serve(reader, writer):
        calls.append(await reader.readuntil(b'\r\n\r\n'))
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    module = Path(__file__).with_name('owned_browser.mjs').as_uri()
    program = f'''
import assert from 'node:assert/strict';
import {{origin, proofGuard}} from {json.dumps(module)};
for (const value of ['http://127.0.0.1:3000','http://[::1]:3000','http://localhost:43210',
                     'https://127.0.0.1:43210','http://user@127.0.0.1:43210']) {{
  let downstream=0;
  assert.throws(()=>{{ origin(value); downstream++; }});
  assert.equal(downstream,0);
}}
const proof=proofGuard([{json.dumps(origin)}]);
try {{
  for(let i=0;i<5;i++) await proof.guard({json.dumps(origin)}+'/owned');
  let downstream=0;
  await assert.rejects(async()=>{{await proof.guard('http://127.0.0.1:3000/mcp'); downstream++;}});
  assert.equal(downstream,0);
  await proof.guard({json.dumps(origin)}+'/owned');
  assert.equal(await (await fetch({json.dumps(origin)}+'/owned',{{redirect:'error'}})).text(),'ok');
}} finally {{proof.close();}}
'''
    try:
        async with browser_proofs(SimpleNamespace(config={'public_ports': []}), port) as (fd, instance, handle):
            process = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e', program,
                pass_fds=(fd,), env={'PATH':'/usr/bin:/bin','OWNED_PROOF_FD':str(fd), 'OWNED_PROOF_INSTANCE':instance},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            handle['process'] = process
            try:
                out, err = await asyncio.wait_for(process.communicate(), 10)
                assert process.returncode == 0, err.decode()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
        assert len(calls) == 1 and calls[0].startswith(b'GET /owned HTTP/1.1')
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize('fault', ['nonce', 'instance', 'generation', 'pid', 'inode'])
async def test_node_malformed_proof_denies_before_dispatch(fault):
    module = Path(__file__).with_name('owned_browser.mjs').as_uri()
    parent, child = socket.socketpair()
    parent.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=parent)
    instance = 'a' * 64
    program = f'''
import assert from 'node:assert/strict';
import {{proofGuard}} from {json.dumps(module)};
const proof=proofGuard(['http://127.0.0.1:43210']);
let downstream=0;
try {{
  await assert.rejects(async()=>{{await proof.guard('http://127.0.0.1:43210/api/bootstrap'); downstream++;}});
  assert.equal(downstream,0);
}} finally {{proof.close();}}
'''
    process = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e', program,
        pass_fds=(child.fileno(),), env={'PATH':'/usr/bin:/bin', 'OWNED_PROOF_FD':str(child.fileno()),
            'OWNED_PROOF_INSTANCE':instance}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    child.close()
    try:
        request = json.loads(await asyncio.wait_for(reader.readline(), 3))
        response = {'nonce':request['nonce'], 'instance':instance, 'generation':1, 'proof':[process.pid,'12345']}
        if fault in ('nonce', 'instance'): response[fault] = 'b'*64
        elif fault == 'generation': response[fault] = True
        elif fault == 'pid': response['proof'][0] = 'not-a-pid'
        elif fault == 'inode': response['proof'][1] = ''
        writer.write(json.dumps(response).encode()+b'\n')
        await asyncio.wait_for(writer.drain(), 3)
        out, err = await asyncio.wait_for(process.communicate(), 5)
        assert process.returncode == 0, err.decode()
    finally:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 3)
        if process.returncode is None:
            process.kill()
            await asyncio.wait_for(process.wait(), 3)


def test_forwarded_routes_retain_browser_per_origin_concurrency():
    module = Path(__file__).with_name('owned_browser.mjs').as_uri()
    code = f'''
import assert from 'node:assert/strict';
import {{routeForwarder}} from {json.dumps(module)};
let active=0, peak=0, checks=0, disposed=0, release;
const gate=new Promise(resolve=>release=resolve);
const forward=routeForwarder({{guard:async()=>{{checks++;}}}});
const jobs=Array.from({{length:24}},()=>forward({{
  request:()=>({{url:()=> 'http://127.0.0.1:43210/asset'}}),
  fetch:async options=>{{
    assert.equal(options.maxRedirects,0);
    active++; peak=Math.max(peak,active);
    await gate;
    active--;
    return {{status:()=>200, dispose:async()=>{{disposed++;}}}};
  }},
}}, async()=>{{}}));
await new Promise(resolve=>setImmediate(resolve));
try {{
  assert.equal(active,6, 'Node route.fetch must not bypass the browser six-connection budget');
  assert.equal(checks,6, 'queued routes must obtain proof at dispatch, not before waiting');
}} finally {{release(); await Promise.all(jobs);}}
assert.equal(peak,6);
assert.equal(checks,24);
assert.equal(disposed,24);
let downstream=0;
const denied=routeForwarder({{guard:async()=>{{throw Error('denied');}}}});
await assert.rejects(denied({{
  request:()=>({{url:()=> 'http://127.0.0.1:43210/asset'}}),
  fetch:async()=>{{downstream++;}},
}}, async()=>{{}}), /denied/);
assert.equal(downstream,0);
'''
    result = subprocess.run(['node', '--input-type=module', '-e', code],
        capture_output=True, text=True, timeout=5, env={'PATH':'/usr/bin:/bin'})
    assert result.returncode == 0, result.stderr


def test_redirect_denial_disposes_and_recovers_all_forwarding_slots():
    module = Path(__file__).with_name('owned_browser.mjs').as_uri()
    code = f'''
import assert from 'node:assert/strict';
import {{routeForwarder}} from {json.dumps(module)};
let disposed=0, consumed=0, checks=0;
const forward=routeForwarder({{guard:async()=>{{checks++;}}}});
const route=(status, gate=Promise.resolve())=>({{
  request:()=>({{url:()=> 'http://127.0.0.1:43210/owned'}}),
  fetch:async options=>{{
    assert.equal(options.maxRedirects,0);
    await gate;
    return {{status:()=>status, dispose:async()=>{{disposed++;}}}};
  }},
}});
for (const status of [300,301,302,303,304,307,308,399]) {{
  await Promise.all(Array.from({{length:6}},()=>assert.rejects(
    forward(route(status), async()=>{{consumed++;}}), /redirect response denied/)));
}}
assert.equal(consumed,0);
assert.equal(disposed,48);
let release;
const gate=new Promise(resolve=>release=resolve);
const jobs=Array.from({{length:7}},()=>forward(route(200,gate), async()=>{{consumed++;}}));
await new Promise(resolve=>setImmediate(resolve));
try {{assert.equal(checks,54, 'all six slots must recover after redirect denial');}}
finally {{release(); await Promise.all(jobs);}}
assert.equal(disposed,55);
assert.equal(consumed,7);
for (const status of [201,204,299,400]) {{
  await forward(route(status), async response=>{{assert.equal(response.status(),status); consumed++;}});
}}
assert.equal(disposed,59);
assert.equal(consumed,11);
'''
    result = subprocess.run(['node', '--input-type=module', '-e', code],
        capture_output=True, text=True, timeout=5, env={'PATH':'/usr/bin:/bin'})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('relative', ['playwright.config.mjs', 'fixtures/server.mjs'])
def test_ui_port_override_rejected_before_any_listen_spy(relative):
    root = Path(__file__).resolve().parents[1]
    target = (root/'packages/mcp-admin-ui'/relative).as_uri()
    code = f'''
import net from 'node:net';
import assert from 'node:assert/strict';
let calls=0;
net.Server.prototype.listen=function(){{calls++; throw Error('downstream spy');}};
await assert.rejects(import({json.dumps(target)}), /invalid private UI_PORT/);
assert.equal(calls,0);
'''
    result = subprocess.run(['node','--input-type=module','-e',code], capture_output=True, text=True,
                            timeout=5, env={'PATH':'/usr/bin:/bin','UI_PORT':'3000'})
    assert result.returncode == 0, result.stderr
