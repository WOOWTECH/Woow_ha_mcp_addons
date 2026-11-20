import test from 'node:test';
import assert from 'node:assert/strict';
import { childkillArguments, childPortOf, createP9AdminClient, crossLine, crossLines, logId, revealToken, runCross,
  runTemporaryProfile, temporaryLabel, withTemporaryProfile } from '../../../packaging/ha_p9_admin.mjs';

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
const revisionOf = n => 'p1-' + String(n).repeat(64);  // the index's ETag after n - 1 changes
const indexRevision = revisionOf(1);
// A switched-on add-on: the profile routes (list with its ETag, create, delete) and each profile's bootstrap, token and
// backend, every answer echoing the profile its request named. Each create or delete changes the index's ETag, and a
// write with another If-Match than the current one is refused (409 config_conflict, contract 3): a deletion must read
// the list again (review SF-3). lose: the response of 'create' or 'delete' is lost.
function switchedServer({ lose = null, revoked = [], etag = true } = {}) {
  const calls = [];
  const ports = new Map([['default', 3000], [extra, 18000]]);
  const tokens = new Map([['default', 'T'.repeat(43)], [extra, 'C'.repeat(43)]]);
  let changes = 1;
  const row = id => ({ id, label: id === 'default' ? 'Default' : 'Probe', port: ports.get(id), is_default: id === 'default',
    disabled_reason: null, status: 'running', blocked_reason: null });
  const stale = options => options.headers?.['If-Match'] !== `"${revisionOf(changes)}"`;
  const fetcher = async (url, options = {}) => {
    const path = url.pathname.slice(mount.length), method = options.method ?? 'GET';
    const profile = options.headers?.['X-MCP-Profile'];
    calls.push({ path, method, profile, ifMatch: options.headers?.['If-Match'], key: options.headers?.['Idempotency-Key'],
      body: options.body });
    if (path === '/api/profiles' && method === 'GET') {
      return Response.json({ profiles: [...ports.keys()].map(row) }, { headers: etag ? { ETag: `"${revisionOf(changes)}"` } : {} });
    }
    if (path === '/api/profiles' && method === 'POST') {
      if (lose === 'create') throw new Error('synthetic lost response');
      if (stale(options)) return json({ detail: { code: 'config_conflict' } }, 409);
      ports.set(temporary, 18001);
      tokens.set(temporary, 'S'.repeat(43));
      changes++;
      return Response.json({ ...row(temporary), operation: { id: options.headers['Idempotency-Key'], kind: 'profile.create',
        state: 'completed', replayed: false } }, { status: 201 });
    }
    if (path.startsWith('/api/profiles/') && method === 'DELETE') {
      if (lose === 'delete') throw new Error('synthetic lost response');
      if (stale(options)) return json({ detail: { code: 'config_conflict' } }, 409);
      const id = path.slice('/api/profiles/'.length);
      ports.delete(id);
      tokens.delete(id);
      changes++;
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
    ['DELETE', `/api/profiles/${temporary}`, `"${revisionOf(2)}"`, undefined]]);  // the list read again after the create
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

// ---- HM-16 review SF-3: what the driver runs, with the probe recorded instead of run over SSH ----

function probeRecorder() {
  const runs = [];
  return { runs, remote: (mode, input, extra = []) => { runs.push([mode, input, extra]); } };
}

test('P9 childkill of a switched-on app names its profile\'s child port; an app not switched on is killed as before', async () => {
  const server = switchedServer();
  const { admin } = kit(server);
  await admin.bootstrap();
  assert.deepEqual(await childkillArguments(admin, true, extra), ['--child-port', '18000']);
  assert.deepEqual(await childkillArguments(admin, true, 'default'), ['--child-port', '3000']);
  const listed = server.calls.filter(call => call.path === '/api/profiles').length;
  assert.deepEqual(await childkillArguments(admin, false, 'default'), []);
  assert.equal(server.calls.filter(call => call.path === '/api/profiles').length, listed);  // no list read for it
});

test('P9 --cross sends every listed profile\'s own token to the probe\'s cross mode', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  const { runs, remote } = probeRecorder();
  await admin.bootstrap();
  await runCross(admin, clientFor, remote);
  assert.deepEqual(runs, [['cross', `default\tlive\t${'T'.repeat(43)}\nbbbbbbbb\tlive\t${'C'.repeat(43)}\n`, []]]);
});

test('P9 --temp-profile: its backend, then the cross with the default profile and the plan on its token, deleted, then its token gone', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  const { runs, remote } = probeRecorder();
  const reports = [];
  let settled = 0;
  const plan = { reads: [['search_nodes', { query: 'x' }]] };
  const id = await runTemporaryProfile(admin, clientFor, remote, { backend: { url: 'https://backend.invalid' }, plan,
    report: line => reports.push(line), label: 'p9-temp-01234567', settle: async () => { settled++; } });
  assert.equal(id, temporary);
  const own = 'T'.repeat(43), its = 'S'.repeat(43);
  assert.deepEqual(runs, [
    ['cross', `default\tlive\t${own}\ncccccccc\tlive\t${its}\n`, []],
    ['plan', its + '\n' + JSON.stringify(plan), []],
    ['cross', `default\tlive\t${own}\ncccccccc\tgone\t${its}\n`, []]]);  // after the deletion: its token refused
  const saved = server.calls.filter(call => call.path === '/api/backend' && call.method === 'PUT');
  assert.deepEqual(saved.map(call => [call.profile, JSON.parse(call.body)]), [[temporary, { url: 'https://backend.invalid' }]]);
  assert.equal(settled, 1);
  assert.equal(server.ports.has(temporary), false);
  assert.deepEqual(reports, ['temporary profile created: cccccccc', 'PUT api/backend (temporary profile): confirmed',
    'temporary profile deleted: cccccccc']);
});

test('P9 --temp-profile without a backend of its own: its PROBE_TOOL call must be refused, never answered', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  const { runs, remote } = probeRecorder();
  await runTemporaryProfile(admin, clientFor, remote, { probeTool: 'search_nodes', probeToolArgs: '{"query":"x"}',
    settle: async () => { throw new Error('no backend: nothing to wait for'); } });
  assert.deepEqual(runs.map(([mode]) => mode), ['cross', 'plan', 'cross']);
  assert.equal(runs[1][1], 'S'.repeat(43) + '\n' + JSON.stringify({ denials: [['search_nodes', { query: 'x' }]] }));
  assert.equal(server.calls.some(call => call.path === '/api/backend'), false);
});

test('P9 --temp-profile: when its use fails it is deleted all the same, and its token is not reported gone', async () => {
  const server = switchedServer();
  const { admin, clientFor } = kit(server);
  const runs = [];
  const remote = (mode, input) => {
    runs.push(mode);
    if (mode === 'cross') throw new Error('probe failed');
  };
  await assert.rejects(runTemporaryProfile(admin, clientFor, remote, {}), /probe failed/);
  assert.equal(server.ports.has(temporary), false);
  assert.deepEqual(runs, ['cross']);
});

test('P9 fails closed when a Headscale version refuses token reveal', async () => {
  const calls = [];
  const client = {bootstrap: async () => ({product: 'headscale'}), mutate: async operation => {
    calls.push(operation); throw Object.assign(new Error('not found'), {status: 404});
  }};
  await assert.rejects(revealToken(client), /token reveal is unavailable/);
  assert.deepEqual(calls, ['token/reveal']);
  assert.equal(await revealToken({bootstrap: async () => ({product: 'headscale'}), mutate: async () => ({token: 'older-version'})}), 'older-version');
});
