// Executed by test_owned_ui.py; actual listeners are only retained own children.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium, request } from '../packages/mcp-admin-ui/node_modules/playwright/index.mjs';
import { retainUIListener, guardedUIRequest, installUIContextGuard, startOwnedUI } from './owned_ui.mjs';

const generation = 'a'.repeat(64);
const response = status => ({ status: () => status, dispose: async () => {} });
let sequence = 0;
async function exchange(child, action) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { child.off('message', receive); reject(Error('own IPC deadline')); }, 2000);
    function receive(message) { if (message.id === id) { clearTimeout(timer); child.off('message', receive); resolve(message); } }
    child.on('message', receive); child.send({ id, action });
  });
}
async function listener(destination = '') {
  const code = `
    const http=require('node:http');
    let hits=[], server;
    function make(port) {
      server=http.createServer((req,res)=>{
        const path=new URL(req.url,'http://127.0.0.1').pathname; hits.push(path);
        if (path.startsWith('/redirect/')) {
          res.writeHead(Number(path.split('/')[2]), {Location:process.env.DESTINATION+'/landing'}); res.end();
        } else {res.setHeader('Content-Type','text/html'); res.end('<title>owned</title><h1>owned</h1>');}
      });
      server.on('upgrade',(req,socket)=>{hits.push('/upgrade');socket.destroy();});
      server.once('error',()=>process.exit(1));
      server.listen(port,'127.0.0.1',()=>process.send({kind:'ready',port:server.address().port}));
    }
    process.on('message',m=>{
      if(m.action==='stats')process.send({id:m.id,hits});
      if(m.action==='replace') {const port=server.address().port;server.closeAllConnections();server.close(()=>{make(port);process.send({id:m.id});});}
    });
    function stop(){server.closeAllConnections();server.close(()=>process.exit(0));}
    process.on('SIGTERM',stop); process.on('disconnect',stop); make(0);
  `;
  const child = spawn(process.execPath, ['--require', new URL('./owned_network.cjs', import.meta.url).pathname, '-e', code], {
    env: { PATH: '/usr/bin:/bin', HOME: '/tmp', DESTINATION: destination }, stdio: ['ignore', 'ignore', 'ignore', 'ipc'],
  });
  const closed = once(child, 'close');
  const timer = setTimeout(() => child.kill('SIGKILL'), 45000);
  const [ready] = await once(child, 'message');
  assert.equal(ready.kind, 'ready');
  const proof = retainUIListener(child, ready.port, generation);
  console.log(JSON.stringify({ ownListener: child.pid, port: ready.port, proved: true }));
  let stopped = false;
  async function stop() {
    if (stopped) return;
    stopped = true; proof.invalidate();
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
    const kill = setTimeout(() => child.kill('SIGKILL'), 2000);
    try { await closed; } finally { clearTimeout(kill); clearTimeout(timer); }
    console.log(JSON.stringify({ ownListener: child.pid, reaped: true, code: child.exitCode, signal: child.signalCode }));
  }
  return { child, proof, port: ready.port, stop, stats: () => exchange(child, 'stats') };
}

async function unit() {
  let sends = 0, proofs = 0, dead = false, disposed = 0;
  const proof = { resolveURL: value => value, guard: async () => { proofs++; assert(!dead, 'stale'); } };
  const raw = {};
  for (const method of ['fetch', 'get', 'post', 'put', 'patch', 'delete', 'head']) raw[method] = async (url, options) => {
    sends++; assert.equal(options.maxRedirects, 0); assert.equal(options.maxRetries, 0);
    assert.equal(options.url, url, 'options must not override the authorized URL');
    return { status: () => Number(url), dispose: async () => { disposed++; } };
  };
  assert.throws(() => guardedUIRequest(raw), /missing UI ownership guard/);
  await assert.rejects(installUIContextGuard({ pages: () => { throw Error('downstream'); } }), /missing UI ownership guard/);
  const api = guardedUIRequest(raw, proof);
  for (const method of Object.keys(raw)) {
    await api[method]('200', { url: 'opaque:must-not-send', maxRedirects: 20, maxRetries: 20 });
    dead = true; await assert.rejects(api[method]('200'), /stale/); dead = false;
  }
  for (let status = 300; status < 400; status++) await assert.rejects(api.get(String(status)), /redirect response denied/);
  assert.equal(sends, 107); assert.equal(proofs, 114); assert.equal(disposed, 100);
  console.log(JSON.stringify({ mode: 'unit', sends, proofs, disposed, deniedStale: 7, deniedRedirectStatuses: 100 }));
}

async function lifecycle() {
  const source = await listener(), decoy = await listener();
  const directory = await mkdtemp(join(tmpdir(), 'owned-ui-regression-'));
  const raw = await request.newContext();
  let dispatches = 0;
  const api = guardedUIRequest({ get: async (...args) => { dispatches++; return raw.get(...args); } }, source.proof);
  try {
    await (await api.get('/positive')).dispose();
    assert.equal(dispatches, 1);
    for (const value of ['http://127.0.0.1:3000/no-io', 'data:text/plain,no', `http://dummy@127.0.0.1:${source.port}/`, decoy.proof.baseURL, { url: () => source.proof.baseURL }]) await assert.rejects(api.get(value));
    await assert.rejects(source.proof.guard('/stale', 'b'.repeat(64)), /stale fixture generation/);
    assert.equal(dispatches, 1);
    assert.throws(() => retainUIListener(source.child, decoy.port, generation), /missing own live listener proof/);
    await writeFile(join(directory, 'index.html'), '<h1>owned miniature</h1>');
    let readinessContexts = 0;
    const noReadiness = { newContext: async () => { readinessContexts++; throw Error('unguarded readiness'); } };
    const sentinel = new URL('./owned_network.cjs', import.meta.url).pathname;
    for (const [name, script, expected] of [
      ['wrong-owner', `process.send({port:${decoy.port},generation:process.env.OWNED_UI_FIXTURE});setInterval(()=>{},1000);`, /missing own live listener proof/],
      ['wrong-generation', `process.send({port:${decoy.port},generation:'b'.repeat(64)});setInterval(()=>{},1000);`, /invalid fixture generation/],
      ['bind-error', `require(${JSON.stringify(sentinel)});const s=require('node:net').createServer();s.on('error',()=>process.exit(1));s.listen(${decoy.port},'127.0.0.1');`, /exited before ready/],
      ['exit', 'process.exit(1);', /exited before ready/],
    ]) {
      const fixturePath = join(directory, name + '.cjs'); await writeFile(fixturePath, script);
      await assert.rejects(startOwnedUI({ request: noReadiness, assetRoot: directory, fixturePath }), expected);
    }
    assert.equal(readinessContexts, 0);
    const fixture = await startOwnedUI({ request, assetRoot: directory });
    const fixtureAPI = guardedUIRequest(raw, fixture);
    await (await fixtureAPI.get('/__fixture/ready')).dispose();
    await fixture.stop();
    await assert.rejects(fixtureAPI.get('/__fixture/ready'), /terminal|exited/);
    const rebound = new Promise(resolve => {
      function ready(message) { if (message.kind === 'ready') { source.child.off('message', ready); resolve(); } }
      source.child.on('message', ready);
    });
    await exchange(source.child, 'replace'); await rebound;
    // Same PID and port, but a newly bound inode must not refresh old authority.
    await assert.rejects(api.get('/replaced'), /fixture listener changed/);
    assert.equal(dispatches, 1);
    assert.deepEqual((await decoy.stats()).hits, []);
    await source.stop();
    await assert.rejects(api.get('/exited'), /terminal|exited/);
    assert.equal(dispatches, 1);
    console.log(JSON.stringify({ mode: 'lifecycle', dispatches, readinessContexts, decoyHTTP: 0, refusedStartupCases: 4 }));
  } finally { await raw.dispose(); await source.stop(); await decoy.stop(); await rm(directory, { recursive: true, force: true }); }
}

async function browser() {
  const decoy = await listener();
  const source = await listener(decoy.proof.baseURL);
  const browser = await chromium.launch({ headless: true });
  const contexts = [], closeContexts = [];
  const raw = await request.newContext();
  let denied = 0;
  async function pageFor(proof) {
    const context = await browser.newContext({ baseURL: source.proof.baseURL, viewport: { width: 333, height: 777 }, serviceWorkers: 'block' });
    contexts.push(context);
    closeContexts.push(await installUIContextGuard(context, proof));
    const page = await context.newPage();
    assert.deepEqual(page.viewportSize(), { width: 333, height: 777 });
    return page;
  }
  async function deniedGoto(context, url) {
    const page = await context.newPage();
    try { await assert.rejects(page.goto(url, { timeout: 3000 }), /ERR_BLOCKED_BY_CLIENT/); }
    finally { await page.close(); } // join Chrome's error-page navigation
  }
  try {
    const page = await pageFor(source.proof);
    assert.equal((await page.goto('/positive')).status(), 200);
    assert.equal((await page.request.get('/page-request')).status(), 200);
    assert.equal((await page.context().request.get('/context-request')).status(), 200);
    const api = guardedUIRequest(raw, source.proof);
    for (const status of [300, 301, 302, 303, 304, 307, 308, 399]) {
      await assert.rejects(api.get(`/redirect/${status}`, { maxRedirects: 10, maxRetries: 10 }), /redirect response denied/);
      await deniedGoto(page.context(), `/redirect/${status}`);
      denied += 2;
    }
    assert.equal((await page.goto('/recovered')).status(), 200);
    // Exact blur-before-response composition used by ui.spec; proof fails only
    // after the page hook executes, proving fallback cannot bypass the guard.
    let blurred = false;
    await page.route('**/token', async route => {
      await page.evaluate(() => window.dispatchEvent(new Event('blur')));
      blurred = true; source.proof.invalidate(); await route.fallback();
    });
    assert.equal(await page.evaluate(() => fetch('/token').then(() => false, () => true)), true);
    await page.unrouteAll({ behavior: 'wait' });
    assert(blurred);
    const before = (await source.stats()).hits.length;
    await assert.rejects(api.get('/stale-api'), /terminal/);
    await assert.rejects(page.request.get('/stale-page-api'), /terminal/);
    await deniedGoto(page.context(), '/stale-browser');
    // An actual browser negative only targets the independently proved decoy.
    await deniedGoto(page.context(), decoy.proof.baseURL);
    assert.equal((await source.stats()).hits.length, before);
    assert(!(await source.stats()).hits.includes('/token'));
    assert.deepEqual((await decoy.stats()).hits, []);
    // Fresh positive context tests WS denial, before any handshake to decoy.
    const fresh = retainUIListener(source.child, source.port, 'c'.repeat(64));
    const wsPage = await pageFor(fresh); await wsPage.goto('/websocket-page');
    await wsPage.evaluate(url => new Promise(resolve => { const ws = new WebSocket(url); ws.onclose = () => resolve(); ws.onerror = () => resolve(); }), decoy.proof.baseURL.replace('http:', 'ws:'));
    assert.deepEqual((await decoy.stats()).hits, []);
    await source.stop();
    await assert.rejects(wsPage.request.get('/exited-api'), /terminal|exited|ENOENT/);
    await deniedGoto(wsPage.context(), '/exited-browser');
    console.log(JSON.stringify({ mode: 'browser', redirectsDenied: denied, decoyHTTP: 0, tokenHookHTTP: 0, staleHTTP: 0, websocketHTTP: 0, exitDenied: true }));
  } finally {
    for (const close of closeContexts) await close();
    await raw.dispose(); await browser.close(); await source.stop(); await decoy.stop();
    console.log(JSON.stringify({ mode: 'browser', browserClosed: true, contextsClosed: contexts.length }));
  }
}

const modes = { unit, lifecycle, browser };
assert(Object.hasOwn(modes, process.argv[2]), 'unknown regression mode');
await modes[process.argv[2]]();
