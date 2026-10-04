// Test-only origin validation and bounded fresh challenges over an inherited FD.
import assert from 'node:assert/strict';
import net from 'node:net';
import { randomBytes } from 'node:crypto';
import './owned_network.cjs';

export function origin(value) {
  const url = new URL(value);
  assert.equal(url.protocol, 'http:');
  assert.equal(url.hostname, '127.0.0.1');
  assert(!url.username && !url.password && !url.search && !url.hash);
  assert(url.port && url.port !== '3000' && url.pathname === '/');
  return url.origin;
}

// route.fetch uses Node's pool, not Chromium's six HTTP/1 connections per
// origin. Keep that browser budget so font bursts cannot manufacture a Core
// admission-limit failure. No retry/delay and no proof held across queue waits.
export function routeForwarder(proof) {
  const origins = new Map();
  return async (route, consume) => {
    const key = origin(new URL(route.request().url()).origin);
    if (!origins.has(key)) origins.set(key, {active:0, waiters:[]});
    const slots = origins.get(key);
    if (slots.active === 6) {
      assert(slots.waiters.length < 256, 'route queue bound');
      await new Promise((resolve, reject) => {
        const ready = () => { clearTimeout(timer); resolve(); };
        const timer = setTimeout(() => {
          slots.waiters.splice(slots.waiters.indexOf(ready), 1);
          reject(Error('route queue deadline'));
        }, 30000);
        slots.waiters.push(ready);
      });
    } else slots.active++;
    try {
      await proof.guard(route.request().url());
      const response = await route.fetch({maxRedirects:0});
      try {
        // Node's maxRedirects does not constrain Chromium after fulfill().
        // Fail closed for ALL 3xx, even same-origin or missing Location, before
        // the consumer can expose a redirect response to the browser.
        const status = response.status();
        if (status >= 300 && status < 400) throw Error('redirect response denied');
        await consume(response);
      } finally { await response.dispose(); }
    } finally {
      const next = slots.waiters.shift();
      if (next) next();
      else slots.active--;
    }
  };
}

export function proofGuard(origins) {
  const allowed = new Set(origins.map(origin));
  const fd = Number(process.env.OWNED_PROOF_FD);
  const instance = process.env.OWNED_PROOF_INSTANCE;
  assert(Number.isInteger(fd) && fd >= 3 && /^[a-f0-9]{64}$/.test(instance));
  const socket = new net.Socket({fd, readable:true, writable:true});
  const pending = new Map();
  let buffered = '', terminal = null;
  function fail(error) {
    if (terminal) return;
    // Synchronous and permanent: destroy's error/close events arrive too late
    // to invalidate promises resolved by other frames in this same callback.
    terminal = error;
    buffered = '';
    for (const value of pending.values()) { clearTimeout(value.timer); value.reject(error); }
    pending.clear();
    socket.destroy(error);
  }
  function checkOpen() {
    if (terminal) throw terminal;
    assert(!socket.destroyed, 'proof channel closed');
  }
  socket.on('error', fail);
  socket.on('close', () => fail(Error('owned proof channel closed')));
  socket.on('data', bytes => {
    if (terminal) return;
    buffered += bytes.toString();
    if (buffered.length > 65536) { fail(Error('oversize proof')); return; }
    while (buffered.includes('\n')) {
      const index = buffered.indexOf('\n');
      const line = buffered.slice(0,index); buffered = buffered.slice(index+1);
      try {
        const response = JSON.parse(line), value = pending.get(response.nonce);
        assert(value && response.instance === instance);
        assert(Number.isSafeInteger(response.generation) && response.generation > 0);
        assert(Array.isArray(response.proof) && response.proof.length === 2);
        assert(Number.isSafeInteger(response.proof[0]) && response.proof[0] > 0);
        assert(typeof response.proof[1] === 'string' && /^[1-9][0-9]*$/.test(response.proof[1]));
        clearTimeout(value.timer); pending.delete(response.nonce); value.resolve();
      } catch (error) { fail(error); return; }
    }
  });
  async function guard(value) {
    const url = new URL(value);
    assert(allowed.has(url.origin) && url.port !== '3000' && !url.username && !url.password,
           'unexpected browser/fetch destination');
    checkOpen();
    assert(pending.size < 64 && String(url).length <= 2048, 'proof queue/request bound');
    const nonce = randomBytes(32).toString('hex');
    await new Promise((resolve,reject) => {
      const timer = setTimeout(() => { pending.delete(nonce); reject(Error('proof timeout')); }, 3000);
      pending.set(nonce,{resolve,reject,timer});
      try { socket.write(JSON.stringify({nonce, instance, url:String(url)})+'\n'); }
      catch (error) { fail(error); }
    });
    // A valid frame can precede a bad frame in the same data callback. Promise
    // resolution alone must not let that guard escape a now-poisoned channel.
    checkOpen();
  }
  return {guard, close:() => fail(Error('owned proof channel closed'))};
}
