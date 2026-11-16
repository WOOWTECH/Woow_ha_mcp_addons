import test from 'node:test';
import assert from 'node:assert/strict';
import { childPortOf, createP9AdminClient, crossLine, crossLines, logId, revealToken, temporaryLabel, withTemporaryProfile } from '../../../packaging/ha_p9_admin.mjs';

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

// ---- HM-16 (FM-107; plan 12.3 HM-16): the kit's profile flows against a switched-on add-on ----

const extra = 'b'.repeat(24), temporary = 'c'.repeat(24);
const indexRevision = 'p1-' + '1'.repeat(64);
// A switched-on add-on: the profile routes (list with its ETag, create, delete) and each profile's bootstrap, token and
// backend, every answer echoing the profile its request named. lose: the response of 'create' or 'delete' is lost.
function switchedServer({ lose = null, revoked = [], etag = true } = {}) {
  const calls = [];
  const ports = new Map([['default', 3000], [extra, 18000]]);
  const tokens = new Map([['default', 'T'.repeat(43)], [extra, 'C'.repeat(43)]]);
  const row = id => ({ id, label: id === 'default' ? 'Default' : 'Probe', port: ports.get(id), is_default: id === 'default',
    disabled_reason: null, status: 'running', blocked_reason: null });
  const fetcher = async (url, options = {}) => {
    const path = url.pathname.slice(mount.length), method = options.method ?? 'GET';
    const profile = options.headers?.['X-MCP-Profile'];
    calls.push({ path, method, profile, ifMatch: options.headers?.['If-Match'], key: options.headers?.['Idempotency-Key'] });
    if (path === '/api/profiles' && method === 'GET') {
      return Response.json({ profiles: [...ports.keys()].map(row) }, { headers: etag ? { ETag: `"${indexRevision}"` } : {} });
    }
    if (path === '/api/profiles' && method === 'POST') {
      if (lose === 'create') throw new Error('synthetic lost response');
      ports.set(temporary, 18001);
      tokens.set(temporary, 'S'.repeat(43));
      return Response.json({ ...row(temporary), operation: { id: options.headers['Idempotency-Key'], kind: 'profile.create',
        state: 'completed', replayed: false } }, { status: 201 });
    }
    if (path.startsWith('/api/profiles/') && method === 'DELETE') {
      if (lose === 'delete') throw new Error('synthetic lost response');
      const id = path.slice('/api/profiles/'.length);
      ports.delete(id);
      tokens.delete(id);
      return Response.json({ deleted: id, operation: { id: options.headers['Idempotency-Key'], kind: 'profile.delete',
        state: 'completed', replayed: false } });
    }
    if (profile === undefined) return json({ detail: { code: 'profile_id_required' } }, 400);
    if (!ports.has(profile)) return json({ detail: { code: 'profile_not_found' } }, 404);
    if (path === '/api/bootstrap') {
      return json({ ...bootstrap, profile: { id: profile, label: profile === 'default' ? 'Default' : 'Probe',
        is_default: profile === 'default' }, profiles_supported: true });
    }
    if (path === '/api/token/reveal') return json({ token: revoked.includes(profile) ? null : tokens.get(profile), profile: { id: profile } });
    if (path === '/api/backend') return json({ saved: true, profile: { id: profile } });
    throw new Error(`unexpected ${method} ${path}`);
  };
  return { fetcher, calls, ports };
}
function kit(server) {
  const clientFor = profile => createP9AdminClient('https://ha.example' + mount + '/', { Cookie: 'ingress_session=fixture' },
    async (url, options) => server.fetcher(url, options), { profile });
  return { clientFor, admin: clientFor('default') };
}

test('P9 names a profile by its log id and reveals each profile\'s token under that profile only', async () => {
  assert.equal(logId('default'), 'default');
  assert.equal(logId(extra), 'bbbbbbbb');
  assert.equal(crossLine(extra, 'gone', 'C'.repeat(43)), `bbbbbbbb\tgone\t${'C'.repeat(43)}\n`);
  assert.match(temporaryLabel(), /^p9-temp-[0-9a-f]{8}$/);
  const server = switchedServer({ revoked: [] });
  const { clientFor } = kit(server);
  assert.equal(await revealToken(clientFor(extra)), 'C'.repeat(43));
  assert.ok(server.calls.filter(call => call.path !== '/api/bootstrap' || call.profile !== undefined)
    .every(call => call.profile === extra));
  const reports = [];
  const lines = await crossLines(clientFor, ['default', extra], line => reports.push(line));
  assert.equal(lines, `default\tlive\t${'T'.repeat(43)}\nbbbbbbbb\tlive\t${'C'.repeat(43)}\n`);
  assert.deepEqual(reports, []);
});

test('P9 leaves a profile without an active token out of the cross matrix and says so by its log id', async () => {
  const server = switchedServer({ revoked: [extra] });
  const reports = [];
  const lines = await crossLines(kit(server).clientFor, ['default', extra], line => reports.push(line));
  assert.equal(lines, `default\tlive\t${'T'.repeat(43)}\n`);
  assert.deepEqual(reports, ['profile bbbbbbbb: no active token; left out of the cross matrix']);
});

test('P9 temporary profile: created with the list\'s revision, used under its own id, then deleted with a fresh revision', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  const seen = [];
  const result = await withTemporaryProfile(admin, clientFor, async (id, client) => {
    seen.push(id, await revealToken(client));
    return 'used';
  }, { label: 'p9-temp-01234567' });
  assert.deepEqual(seen, [temporary, 'S'.repeat(43)]);
  assert.deepEqual(result, { id: temporary, outcome: 'used' });
  assert.equal(server.ports.has(temporary), false);
  const writes = server.calls.filter(call => call.method === 'POST' && call.path === '/api/profiles' || call.method === 'DELETE');
  assert.deepEqual(writes.map(call => [call.method, call.path, call.ifMatch, call.profile]), [
    ['POST', '/api/profiles', `"${indexRevision}"`, undefined],
    ['DELETE', `/api/profiles/${temporary}`, `"${indexRevision}"`, undefined]]);
  assert.match(writes[0].key, /^1793334000000\.[0-9a-f]{32}$/);
  assert.notEqual(writes[0].key, writes[1].key);
  assert.equal(admin.pendingProfileOperation(), null);
});

test('P9 temporary profile is deleted when what used it failed', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  await assert.rejects(withTemporaryProfile(admin, clientFor, async () => { throw new Error('probe failed'); }), /probe failed/);
  assert.equal(server.ports.has(temporary), false);
  assert.equal(server.calls.filter(call => call.method === 'DELETE').length, 1);
});

test('P9 temporary profile: a lost create or delete answer stops at once, keeps its identity, is never sent again', async () => {
  for (const lose of ['create', 'delete']) {
    const server = switchedServer({ lose });
    const { admin, clientFor } = kit(server);
    const reports = [];
    let used = 0;
    await assert.rejects(withTemporaryProfile(admin, clientFor, async () => { used++; }, { report: line => reports.push(line) }));
    const method = lose === 'create' ? 'POST' : 'DELETE';
    assert.equal(server.calls.filter(call => call.method === method).length, 1, lose);
    assert.equal(used, lose === 'create' ? 0 : 1, lose);
    const pending = admin.pendingProfileOperation();
    assert.equal(pending.route, 'profiles/' + lose);
    assert.deepEqual(reports, [`unconfirmed profile operation; check the profile list and its receipt before another run: ${pending.id} profiles/${lose}`,
      ...(lose === 'delete' ? ['temporary profile cccccccc may still exist; delete it in the panel before another run'] : [])]);
    if (lose === 'create') assert.equal(server.calls.some(call => call.method === 'DELETE'), false);
  }
});

test('P9 temporary profile is never created from a list without its index revision', async () => {
  const server = switchedServer({ etag: false });
  const { admin, clientFor } = kit(server);
  await assert.rejects(withTemporaryProfile(admin, clientFor, async () => {}), /index revision/);
  assert.equal(server.calls.some(call => call.method === 'POST'), false);
});

test('P9 childkill takes the named profile\'s child port from the profile list', async () => {
  const server = switchedServer();
  const { admin } = kit(server);
  await admin.bootstrap();
  assert.equal(await childPortOf(admin, 'default'), 3000);
  assert.equal(await childPortOf(admin, extra), 18000);
  await assert.rejects(childPortOf(admin, temporary), /cccccccc is not in the profile list/);
});
