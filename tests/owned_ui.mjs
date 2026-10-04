// Private Linux/IPv4 standalone UI harness. Never imported by production.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { readFileSync, readdirSync, readlinkSync } from 'node:fs';
import { cp, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import './owned_network.cjs';
import { origin, routeForwarder } from './owned_browser.mjs';

export function rejectPortOverride() {
  // Overrides are not an ownership contract, even when syntactically valid.
  if (process.env.UI_PORT !== undefined) throw Error('invalid private UI_PORT: owned ephemeral fixture required');
}

function kernelProof(child, port) {
  assert(Number.isInteger(child.pid) && child.pid > 0 && child.exitCode === null && child.signalCode === null, 'fixture exited');
  assert(Number.isInteger(port) && port > 0 && port <= 65535 && port !== 3000, 'invalid private UI_PORT');
  const stat = () => {
    const fields = readFileSync(`/proc/${child.pid}/stat`, 'utf8').split(') ')[1].split(' ');
    assert(!['Z', 'X'].includes(fields[0]), 'fixture exited');
    return fields[19]; // starttime (field 22), not comm or a PID scan
  };
  const start = stat();
  const sockets = new Set(readdirSync(`/proc/${child.pid}/fd`).flatMap(fd => {
    try { return [readlinkSync(`/proc/${child.pid}/fd/${fd}`)]; } catch { return []; }
  }));
  const address = `0100007F:${port.toString(16).toUpperCase().padStart(4, '0')}`;
  const rows = readFileSync(`/proc/${child.pid}/net/tcp`, 'utf8').split('\n').map(line => line.trim().split(/\s+/))
    .filter(cols => cols[1] === address && cols[3] === '0A' && /^[1-9][0-9]*$/.test(cols[9]) && sockets.has(`socket:[${cols[9]}]`));
  assert.equal(rows.length, 1, 'missing own live listener proof');
  assert.equal(stat(), start, 'fixture PID generation changed');
  assert(child.exitCode === null && child.signalCode === null, 'fixture exited');
  return `${child.pid}:${start}:${rows[0][9]}`;
}

export function retainUIListener(child, port, generation) {
  assert(/^[a-f0-9]{64}$/.test(generation), 'invalid fixture generation');
  const baseURL = origin(`http://127.0.0.1:${port}`);
  const retained = kernelProof(child, port);
  let terminal = false;
  const invalidate = () => { terminal = true; };
  child.once('exit', invalidate);
  child.once('error', invalidate);
  function resolveURL(value) {
    assert(typeof value === 'string' || value instanceof URL, 'opaque request denied');
    const url = new URL(value, baseURL);
    assert(url.origin === baseURL && !url.username && !url.password && !url.hash && url.port !== '3000', 'unexpected UI destination');
    return url.href;
  }
  async function guard(value, expectedGeneration = generation) {
    resolveURL(value);
    assert(!terminal && expectedGeneration === generation, 'terminal or stale fixture generation');
    assert.equal(kernelProof(child, port), retained, 'fixture listener changed');
    assert(!terminal, 'terminal fixture');
  }
  return Object.freeze({ baseURL, generation, resolveURL, guard, invalidate });
}

export function guardedUIRequest(raw, proof) {
  assert(proof && typeof proof.guard === 'function' && typeof proof.resolveURL === 'function', 'missing UI ownership guard');
  const guarded = {};
  for (const method of ['fetch', 'get', 'post', 'put', 'patch', 'delete', 'head']) {
    guarded[method] = async (value, options = {}) => {
      const url = proof.resolveURL(value);
      await proof.guard(url);
      const response = await raw[method](url, { ...options, url, maxRedirects: 0, maxRetries: 0 });
      if (response.status() >= 300 && response.status() < 400) {
        await response.dispose();
        throw Error('redirect response denied');
      }
      return response;
    };
  }
  // No raw request/context escape hatch. Only non-network operations exposed.
  guarded.dispose = (...args) => raw.dispose(...args);
  guarded.storageState = (...args) => raw.storageState(...args);
  return Object.freeze(guarded);
}

export async function installUIContextGuard(context, proof) {
  assert(proof && typeof proof.guard === 'function', 'missing UI ownership guard');
  assert.equal(context.pages().length, 0, 'UI guard must precede pages');
  const forward = routeForwarder(proof);
  const active = new Set();
  async function handle(route) {
    try {
      await forward({ request: () => route.request(), fetch: options => route.fetch({ ...options, maxRetries: 0 }) },
        response => route.fulfill({ response }));
    } catch {
      // Navigation cancellation may already have settled a fulfill. Never
      // continue/retry; only tolerate an already-settled/closed abort target.
      try { await route.abort('blockedbyclient'); }
      catch (error) { if (!/Route is already handled|Target .*closed/.test(error.message)) throw error; }
    }
  }
  await context.route('**/*', route => {
    const operation = handle(route);
    active.add(operation);
    return operation.finally(() => active.delete(operation));
  });
  await context.routeWebSocket('**/*', socket => socket.close());
  // Installed Playwright route.fetch itself calls context.request._innerFetch.
  // Guard that send boundary in place; replacing context.request would break
  // Playwright internals. This also guards ordinary page/context.request calls.
  const send = context.request._innerFetch.bind(context.request);
  context.request._innerFetch = async (options = {}) => {
    const url = proof.resolveURL(options.url ?? options.request?.url());
    await proof.guard(url);
    const response = await send({ ...options, url, maxRedirects: 0, maxRetries: 0 });
    if (response.status() >= 300 && response.status() < 400) {
      await response.dispose();
      throw Error('redirect response denied');
    }
    return response;
  };
  return async () => {
    // Close before draining: keep guards installed while cancelling pending
    // navigations/fetches, and do not call Playwright APIs on a closed context.
    await context.close();
    const settled = await Promise.allSettled([...active]);
    const failed = settled.find(result => result.status === 'rejected');
    if (failed) throw failed.reason;
  };
}

export async function startOwnedUI({ request,
  assetRoot = process.env.OWNED_UI_DIST ?? new URL('../packages/mcp-admin-ui/dist/', import.meta.url).pathname,
  fixturePath = new URL('../packages/mcp-admin-ui/fixtures/server.mjs', import.meta.url).pathname,
} = {}) {
  rejectPortOverride();
  assert(request && typeof request.newContext === 'function', 'missing readiness request factory');
  const directory = await mkdtemp(join(tmpdir(), 'owned-ui-'));
  let child, proof, api, timer, closed;
  const generation = randomBytes(32).toString('hex');
  async function stop() {
    proof?.invalidate(); // revoke before waiting or signalling
    try { await api?.dispose(); }
    finally {
      if (child && child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM');
        const kill = setTimeout(() => child.kill('SIGKILL'), 3000);
        try { await closed; } finally { clearTimeout(kill); }
      } else if (closed) await closed;
      await rm(directory, { recursive: true, force: true });
      if (child) console.log(JSON.stringify({ ownedUI: 'closed', pid: child.pid, code: child.exitCode, signal: child.signalCode, reaped: true }));
    }
  }
  try {
    await cp(assetRoot, join(directory, 'dist'), { recursive: true, dereference: true });
    child = spawn(process.execPath, [fixturePath], {
      env: { PATH: '/usr/bin:/bin', HOME: directory, OWNED_UI_FIXTURE: generation, OWNED_UI_ASSET_ROOT: join(directory, 'dist') },
      stdio: ['ignore', 'ignore', 'ignore', 'ipc'],
    });
    closed = new Promise(resolve => child.once('close', resolve));
    const address = await new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(Error('owned fixture startup deadline')), 10000);
      child.once('error', reject);
      child.once('exit', () => reject(Error('owned fixture exited before ready')));
      child.once('message', message => {
        if (message?.generation !== generation || !Number.isInteger(message.port) || message.port < 1 || message.port > 65535 || message.port === 3000) reject(Error('invalid fixture generation/address'));
        else resolve(message.port);
      });
    });
    clearTimeout(timer);
    // IPC is only a candidate address. It never authorizes HTTP by itself.
    proof = retainUIListener(child, address, generation);
    api = await request.newContext({ baseURL: proof.baseURL });
    const ready = await guardedUIRequest(api, proof).get('/__fixture/ready', { timeout: 3000 });
    try { assert.equal(ready.status(), 200, 'owned fixture not ready'); } finally { await ready.dispose(); }
    console.log(JSON.stringify({ ownedUI: 'started', pid: child.pid, generation, port: address }));
    return Object.freeze({ ...proof, stop });
  } catch (error) { await stop(); throw error; }
  finally { clearTimeout(timer); }
}
