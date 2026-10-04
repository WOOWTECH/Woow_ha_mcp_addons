"""Coalesced IPC failures are terminal before any forwarded browser I/O.

All live HTTP listeners belong to this test. Fault injection is confined to its
inherited socketpair; persistent tests have no dependency on reviewer reports.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import time

import pytest

from owned_executable import self_listener


PROGRAM = r'''
import net from 'node:net';
const {proofGuard, routeForwarder} = await import(config.helper);
const timers = new Set(), chunks = [];
const set = globalThis.setTimeout, clear = globalThis.clearTimeout;
globalThis.setTimeout = (callback, delay, ...args) => {
  if (delay !== 3000) return set(callback, delay, ...args);
  const handle = set(() => {timers.delete(handle); callback(...args);}, delay);
  timers.add(handle);
  return handle;
};
globalThis.clearTimeout = handle => {timers.delete(handle); return clear(handle);};
// Observe the real data callback, without altering framing, delivery or timers.
const on = net.Socket.prototype.on;
let channel;
net.Socket.prototype.on = function(event, listener) {
  if (this._handle?.fd === Number(process.env.OWNED_PROOF_FD) && event === 'data') {
    channel = this;
    return on.call(this, event, bytes => {
      chunks.push([...bytes].filter(value => value === 10).length);
      return listener(bytes);
    });
  }
  return on.call(this, event, listener);
};
const proof = proofGuard([config.source]);
net.Socket.prototype.on = on;
const forward = routeForwarder(proof);
let fetched=0, consumed=0, disposed=0, aborted=0, laterDenied=false, expiredMs=null, laterMs=0, recoveryMs=0;
let browser;
try {
  if (config.fault.includes('replay')) await proof.guard(config.source+'/prime');
  if (config.fault.includes('expired')) {
    const start=performance.now();
    try {await proof.guard(config.source+'/prime'); throw Error('expected timeout');}
    catch (error) {if (error.message !== 'proof timeout') throw error;}
    expiredMs=performance.now()-start;
  }
  let outcomes;
  if (config.browser) {
    const {chromium} = await import(config.playwright);
    browser=await chromium.launch({headless:true});
    const context=await browser.newContext({serviceWorkers:'block'});
    await context.route('**/*', async route => {
      const wrapped={request:()=>route.request(), fetch:async options=>{
        if (options.maxRedirects !== 0) throw Error('redirect option changed');
        fetched++;
        const response=await route.fetch(options);
        const dispose=response.dispose.bind(response);
        response.dispose=async()=>{await dispose(); disposed++;};
        return response;
      }};
      try {await forward(wrapped, async response=>{consumed++; await route.fulfill({response});});}
      catch {aborted++; await route.abort();}
    });
    await context.routeWebSocket('**/*', ws=>ws.close());
    const pages=await Promise.all(Array.from({length:2},()=>context.newPage()));
    outcomes=await Promise.all(pages.map(async(page,index)=>{
      try {return (await page.goto(config.source+'/owned/'+index,{timeout:5000})).status()===200;}
      catch {return false;}
    }));
    await context.close();
  } else {
    const jobs=Array.from({length:8},()=>forward({
      request:()=>({url:()=>config.source+'/owned'}),
      fetch:async options=>{
        if (options.maxRedirects !== 0) throw Error('redirect option changed');
        fetched++;
        return {status:()=>200, dispose:async()=>{disposed++;}};
      },
    }, async()=>{consumed++;}));
    if (config.fault === 'explicit-close') proof.close();
    if (config.fault === 'channel-error') channel.emit('error', Error('owned injected channel error'));
    outcomes=(await Promise.allSettled(jobs)).map(result=>result.status==='fulfilled');
  }
  // Inspect cleanup BEFORE explicit close can hide lingering pending timers.
  const pendingTimers=timers.size;
  if (config.fault !== 'valid') {
    const laterStart=performance.now();
    try {await proof.guard(config.source+'/later');} catch {laterDenied=true;}
    laterMs=performance.now()-laterStart;
    const recoveryStart=performance.now();
    // The same forwarder must reject all slots/queued requests after poison.
    await Promise.all(Array.from({length:8},async()=>{
      try {await forward({request:()=>({url:()=>config.source+'/later'}),
        fetch:async()=>{fetched++; throw Error('terminal dispatch');}},async()=>{});}
      catch {}
    }));
    recoveryMs=performance.now()-recoveryStart;
  }
  if (browser) await browser.close();
  console.log(JSON.stringify({fetched,consumed,disposed,aborted,laterDenied,expiredMs,
    pendingTimers,finalTimers:timers.size,outcomes,chunks,laterMs,recoveryMs,browserClosed:!browser?.isConnected()}));
} finally {
  if (browser?.isConnected()) await browser.close();
  proof.close();
  globalThis.setTimeout=set; globalThis.clearTimeout=clear;
}
'''


CASES = [(fault, False) for fault in (
    'malformed-first', 'wrongnonce-first', 'replay-first', 'expired-first',
    'valid-first-malformed', 'valid-one-malformed', 'valid-first-replay',
    'valid-first-expired', 'closed', 'oversized', 'explicit-close', 'channel-error', 'valid')]
CASES += [(fault, True) for fault in (
    'malformed-first', 'replay-first', 'expired-first', 'valid-first-malformed', 'valid')]


@pytest.mark.parametrize('fault,browser', CASES)
async def test_terminal_coalesced_proof(fault, browser):
    root = Path(__file__).resolve().parents[1]
    http_requests, handler_errors, handlers = [], [], set()
    async def serve(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            async with asyncio.timeout(5):
                data = await reader.readuntil(b'\r\n\r\n')
                http_requests.append(data.split(b'\r\n')[0].decode('ascii'))
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nok')
                await writer.drain()
        except Exception as error:
            handler_errors.append(type(error).__name__)
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 3)
            finally:
                handlers.discard(task)
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    owned = self_listener(port)
    assert owned and owned[0] == os.getpid()
    parent, child = socket.socketpair()
    parent.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=parent)
    instance = 'a' * 64
    source = f'http://127.0.0.1:{port}'
    config = {'source':source, 'fault':fault, 'browser':browser,
              'helper':(root/'tests/owned_browser.mjs').as_uri(),
              'playwright':(root/'packages/mcp-admin-ui/node_modules/@playwright/test/index.mjs').as_uri()}
    process = None
    challenges = 0
    async def reply():
        nonlocal challenges
        request = json.loads(await asyncio.wait_for(reader.readline(), 7))
        challenges += 1
        assert request['instance'] == instance and request['url'].startswith(source+'/')
        assert self_listener(port) == owned
        return json.dumps({'nonce':request['nonce'], 'instance':instance,
                           'generation':1, 'proof':owned}).encode()+b'\n'
    async def send(payload):
        assert self_listener(port) == owned  # just before every proof write
        writer.write(payload)  # one coalesced write, not separate test frames
        await asyncio.wait_for(writer.drain(), 3)
    try:
        assert self_listener(port) == owned
        process = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e',
            'const config='+json.dumps(config)+';\n'+PROGRAM,
            pass_fds=(child.fileno(),), start_new_session=True,
            env={'PATH':'/usr/bin:/bin', 'HOME':'/tmp', 'PLAYWRIGHT_BROWSERS_PATH':'0',
                 'OWNED_PROOF_FD':str(child.fileno()), 'OWNED_PROOF_INSTANCE':instance},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        child.close()
        print('BT1_TERMINAL_START', json.dumps({'fault':fault, 'browser':browser,
            'pid':process.pid, 'pgid':process.pid, 'port':port, 'proof':owned, 'deadline':20}))
        previous, prime_time = None, None
        if 'replay' in fault or 'expired' in fault:
            previous = await reply()
            prime_time = time.monotonic()
            if 'replay' in fault:
                await send(previous)
        count = 2 if browser else 6
        if fault not in ('explicit-close', 'channel-error'):
            valid = [await reply() for _ in range(count)]
            if 'expired' in fault:
                assert time.monotonic()-prime_time >= 2.9  # real unmodified 3s timeout
            poison = b'{invalid json}\n'
            if 'replay' in fault or 'expired' in fault:
                poison = previous
            elif fault == 'wrongnonce-first':
                value = json.loads(valid[0])
                poison = json.dumps({**value, 'nonce':'b'*64}).encode()+b'\n'
            if fault == 'closed':
                writer.close()
            elif fault == 'oversized':
                await send(b'x'*66000+b''.join(valid))
            elif fault == 'valid':
                await send(b''.join(valid))
                if not browser:
                    await send(b''.join([await reply() for _ in range(2)]))
            elif fault.startswith('valid-first'):
                await send(b''.join(valid)+poison)
            elif fault == 'valid-one-malformed':
                await send(valid[0]+poison+b''.join(valid[1:]))
            else:
                await send(poison+b''.join(valid))
        out, err = await asyncio.wait_for(process.communicate(), 20)
        assert process.returncode == 0, err.decode()
        result = json.loads(out)
        print('BT1_TERMINAL_RESULT', json.dumps({'fault':fault, 'browser':browser,
            'pid':process.pid, 'exit':process.returncode, 'reaped':True,
            'http_requests':http_requests, 'challenges':challenges, **result}))
        assert result['pendingTimers'] == result['finalTimers'] == 0
        assert result['browserClosed'] and not handler_errors
        total = 2 if browser else 8
        if fault == 'valid':
            assert result['outcomes'] == [True]*total
            assert result['fetched'] == result['consumed'] == result['disposed'] == total
            assert len(http_requests) == (2 if browser else 0)
            assert max(result['chunks']) >= count, 'positive replies must actually coalesce'
        else:
            assert not http_requests, 'poisoned proof permitted actual Chromium HTTP'
            assert result['fetched'] == result['consumed'] == result['disposed'] == 0
            assert result['outcomes'] == [False]*total and result['laterDenied']
            assert result['laterMs'] < 1000 and result['recoveryMs'] < 1000, 'terminal rejection must not wait for proof/queue deadlines'
            if browser:
                assert result['aborted'] == 2
            if fault not in ('closed', 'oversized', 'explicit-close', 'channel-error'):
                assert max(result['chunks']) >= count+1, 'poison and matching frames must share a data callback'
            if 'expired' in fault:
                assert result['expiredMs'] >= 2900
    finally:
        if process and process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await asyncio.wait_for(process.wait(), 5)
        child.close()
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 3)
        except (ConnectionResetError, BrokenPipeError):
            pass  # explicit-close/error controls intentionally close unread IPC
        server.close()
        async with asyncio.timeout(6):
            await server.wait_closed()
            if handlers:
                await asyncio.gather(*list(handlers))
        assert not handlers
        print('BT1_TERMINAL_CLEANUP', json.dumps({'pid':process.pid if process else None,
            'exit':process.returncode if process else None, 'listener_closed':True, 'handlers_joined':True}))
