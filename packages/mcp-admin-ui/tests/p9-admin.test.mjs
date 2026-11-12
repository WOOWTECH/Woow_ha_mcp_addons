import test from 'node:test';
import assert from 'node:assert/strict';
import { createP9AdminClient } from '../../../packaging/ha_p9_admin.mjs';

const mount = '/api/hassio_ingress/p9-fixture';
const revision = 'c1-' + 'a'.repeat(64);
const bootstrap = { base_path: mount, api_base: mount + '/api', product: 'n8n',
  csrf: 'csrf-fixture-0123456789', configuration: { revision },
  operation_contract: { version: 1, server_time_ms: 1793334000000 } };
const json = (value, status = 200) => new Response(JSON.stringify(value), { status });
function fixture(effect) {
  const calls = [];
  const client = createP9AdminClient('https://ha.example' + mount + '/',
    { Cookie: 'ingress_session=fixture', 'User-Agent': 'fixture' }, async (url, options) => {
      calls.push({ url: String(url), ...options });
      if (url.pathname.endsWith('/bootstrap')) return json(bootstrap);
      return effect(url, options);
    });
  return { client, calls };
}

test('P9 backend save sends reviewed revision, fresh CSRF and real ingress cookie together', async () => {
  const { client, calls } = fixture((_url, request) => {
    assert.equal(request.method, 'PUT');
    assert.equal(request.headers['If-Match'], '"' + revision + '"');
    assert.equal(request.headers['X-CSRF-Token'], bootstrap.csrf);
    assert.equal(request.headers.Cookie, 'ingress_session=fixture');
    assert.equal(request.headers['Idempotency-Key'], undefined);
    assert.deepEqual(JSON.parse(request.body), { url: 'https://backend.example' });
    assert.equal(request.redirect, 'error');
    return json({ saved: true });
  });
  await client.mutate('backend', { url: 'https://backend.example' }, revision);
  assert.equal(calls.length, 2);
});

test('P9 rotate validates metadata receipt and retains no returned secret in operation storage', async () => {
  let effects = 0;
  const { client } = fixture((_url, request) => {
    effects++;
    const id = request.headers['Idempotency-Key'];
    assert.match(id, /^1793334000000\.[0-9a-f]{32}$/);
    assert.equal(request.headers['If-Match'], '"' + revision + '"');
    return json({ status: 'ok', token: 'synthetic-return-only-secret',
      operation: { id, kind: 'token.rotate', state: 'completed', replayed: false } });
  });
  assert.equal((await client.mutate('token/rotate', undefined, revision)).token, 'synthetic-return-only-secret');
  assert.equal(client.pendingOperation(), null);
  assert.equal(effects, 1);
});

test('P9 lost rotate response stops after one dispatch and retains original public receipt identity', async () => {
  let effects = 0;
  const { client, calls } = fixture(() => { effects++; throw new Error('synthetic lost response'); });
  await assert.rejects(client.mutate('token/rotate', undefined, revision));
  const pending = client.pendingOperation();
  assert.equal(pending.route, 'token/rotate');
  assert.equal(pending.revision, revision);
  assert.deepEqual(Object.keys(pending).sort(), ['id', 'product', 'revision', 'route']);
  assert.equal(effects, 1);
  assert.equal(calls.length, 2);
});

test('P9 stale backend save and mismatched token receipt cannot be reported as success', async () => {
  const stale = fixture(() => json({ detail: { code: 'config_conflict' } }, 409));
  await assert.rejects(stale.client.mutate('backend', {}, revision), error => error.status === 409);
  assert.equal(stale.calls.length, 2);
  const mismatch = fixture((_url, request) => json({ status: 'ok', token: 'do-not-accept',
    operation: { id: request.headers['Idempotency-Key'], kind: 'token.revoke', state: 'completed', replayed: false } }));
  await assert.rejects(mismatch.client.mutate('token/rotate', undefined, revision));
  assert.ok(mismatch.client.pendingOperation());
  assert.equal(mismatch.calls.length, 2);
});
