"""Actual Chromium redirect denial: retained OWN listeners, never port3000."""
import asyncio
import json
import os
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest

from owned_browser import browser_proofs
from owned_executable import self_listener


CASES = ([(status, target) for target in ('cross', 'same')
          for status in (301, 302, 303, 307, 308)]
         + [(300, 'cross'), (399, 'cross'), (302, 'missing'), (304, 'missing'),
            (200, 'cross'), (299, 'missing')])


@pytest.mark.parametrize('status,target', CASES)
async def test_chromium_redirect_denied_before_fulfill(status, target):
    root = Path(__file__).resolve().parents[1]
    received = {'source': [], 'decoy': []}
    handlers, errors = set(), []
    ports = {}

    async def serve(kind, reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            async with asyncio.timeout(5):
                request = await reader.readuntil(b'\r\n\r\n')
                path = request.split(b' ', 2)[1].decode('ascii')
                received[kind].append(path)
                code, location = 200, ''
                if kind == 'source' and path == '/case':
                    code = status
                    if target != 'missing':
                        port = ports['decoy' if target == 'cross' else 'source']
                        location = f'Location: http://127.0.0.1:{port}/landing\r\n'
                body = b'' if code == 304 else b'ok'
                writer.write((f'HTTP/1.1 {code} Test\r\n{location}'
                              f'Content-Length: {len(body)}\r\nContent-Type: text/plain\r\n'
                              'Connection: close\r\n\r\n').encode() + body)
                await writer.drain()
        except Exception as error:
            errors.append(type(error).__name__)
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 3)
            finally:
                handlers.discard(task)

    servers = []
    process = None
    try:
        for kind in ('decoy', 'source'):
            async def accept(reader, writer, kind=kind):
                await serve(kind, reader, writer)
            server = await asyncio.start_server(accept, '127.0.0.1', 0)
            servers.append(server)
            ports[kind] = server.sockets[0].getsockname()[1]
        proofs = {kind: self_listener(port) for kind, port in ports.items()}
        assert all(proof is not None and proof[0] == os.getpid() for proof in proofs.values())
        source = f'http://127.0.0.1:{ports["source"]}'
        program = f'''
import assert from 'node:assert/strict';
import {{chromium}} from {json.dumps((root/'packages/mcp-admin-ui/node_modules/@playwright/test/index.mjs').as_uri())};
import {{routeForwarder, proofGuard}} from {json.dumps((root/'tests/owned_browser.mjs').as_uri())};
const origin={json.dumps(source)};
const proof=proofGuard([origin]);
const checks=[], consumed=[], denied=[], disposed=[], options=[];
const forward=routeForwarder({{guard:async url=>{{checks.push(new URL(url).pathname); await proof.guard(url);}}}});
const browser=await chromium.launch({{headless:true}});
let failed=false, firstStatus=null, recovered=false;
try {{
  const context=await browser.newContext({{serviceWorkers:'block'}});
  await context.route('**/*', async route=>{{
    const path=new URL(route.request().url()).pathname;
    // Observe, but delegate to the real Playwright fetch/response/fulfill.
    const observed={{request:()=>route.request(), fetch:async settings=>{{
      options.push(settings.maxRedirects);
      const response=await route.fetch(settings);
      const dispose=response.dispose.bind(response);
      response.dispose=async()=>{{await dispose(); disposed.push(path);}};
      return response;
    }}}};
    try {{await forward(observed, async response=>{{
      consumed.push({{path,status:response.status()}});
      await route.fulfill({{response}});
    }});}} catch {{denied.push(path); await route.abort();}}
  }});
  await context.routeWebSocket('**/*', socket=>socket.close());
  const page=await context.newPage();
  try {{firstStatus=(await page.goto(origin+'/case',{{timeout:5000}})).status();}}
  catch {{failed=true;}}
  // Aborted navigation may still commit Chromium's internal error page. Use
  // another page in the SAME context/forwarder to test recovered capacity,
  // rather than racing that internal navigation or sleeping/retrying.
  await page.close();
  const recovery=await context.newPage();
  recovered=(await recovery.goto(origin+'/ok',{{timeout:5000}})).status()===200;
  await context.close();
}} finally {{await browser.close(); proof.close();}}
console.log(JSON.stringify({{checks, consumed, denied, disposed, options, failed,
  firstStatus, recovered, browserClosed:!browser.isConnected()}}));
'''
        # The broker performs fresh own PID/fd checks for every allowed source
        # request. The independently proved decoy is deliberately NOT allowed.
        async with browser_proofs(SimpleNamespace(config={'public_ports': []}), ports['source']) as (fd, instance, handle):
            assert {kind: self_listener(port) for kind, port in ports.items()} == proofs
            process = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e', program,
                pass_fds=(fd,), start_new_session=True,
                env={'PATH':'/usr/bin:/bin', 'HOME':'/tmp', 'PLAYWRIGHT_BROWSERS_PATH':'0',
                     'OWNED_PROOF_FD':str(fd), 'OWNED_PROOF_INSTANCE':instance},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            handle['process'] = process
            print('BT1_REDIRECT_START', json.dumps({'pid':process.pid, 'pgid':process.pid,
                  'status':status, 'target':target, 'ports':ports, 'proofs':proofs, 'deadline':20}))
            try:
                out, err = await asyncio.wait_for(process.communicate(), 20)
            finally:
                if process.returncode is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    await asyncio.wait_for(process.wait(), 5)
            assert process.returncode == 0, err.decode()
            result = json.loads(out)
            print('BT1_REDIRECT_RESULT', json.dumps({'exit':process.returncode, 'reaped':True,
                  'received':received, **result}))
        assert received['decoy'] == [], 'Chromium reached forbidden OWN decoy without a guard'
        assert '/landing' not in received['source'], 'same-origin redirect must also be denied'
        assert result['options'] == [0, 0]
        assert result['checks'] == ['/case', '/ok']
        assert result['disposed'] == ['/case', '/ok']
        assert result['recovered'] and result['browserClosed'] and not errors
        if 300 <= status < 400:
            assert result['failed'] and result['firstStatus'] is None
            assert result['denied'] == ['/case']
            assert result['consumed'] == [{'path':'/ok', 'status':200}]
        else:
            assert not result['failed'] and not result['denied']
            assert result['firstStatus'] == status
            assert result['consumed'] == [{'path':'/case', 'status':status}, {'path':'/ok', 'status':200}]
    finally:
        for server in servers:
            server.close()
        async with asyncio.timeout(6):
            for server in servers:
                await server.wait_closed()
            if handlers:
                await asyncio.gather(*list(handlers))
        assert not handlers
        print('BT1_REDIRECT_CLEANUP', json.dumps({'listeners_closed':True, 'handlers_joined':True,
              'pid':process.pid if process else None, 'exit':process.returncode if process else None}))
