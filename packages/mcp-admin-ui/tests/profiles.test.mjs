// HM-11 (plan 6, 10.3): the panel's profile rules without a browser. A small double of the management API as
// contract.md section 3 describes it; LOCAL MOCK only.
import test from 'node:test';
import assert from 'node:assert/strict';
import { AdminApi, ApiError, ProfileEchoError, StaleProfileError } from '../src/api.js';
import { OperationIdentity, PROFILES_SCOPE } from '../src/operation-identity.js';
import { DEFAULT_PROFILE, blockedNotice, clientName, disabledNotice, echoMatches, indexState, labelProblem, optionLabel, orphanIds, profileName, profileRows, shortId } from '../src/profiles.js';
import { readFileSync } from 'node:fs';
import { clientExample, policyFingerprint, policyRestartNotice, UiError } from '../src/contracts.js';
import { createP9AdminClient } from '../../../packaging/ha_p9_admin.mjs';
// HM-12: read through the modules, so a name a module does not have fails only the cases that use it.
import * as panelApi from '../src/api.js';
import * as panelContracts from '../src/contracts.js';

const mount = '/api/hassio_ingress/DUMMY';
const B = '0123456789abcdef01234567', C = 'fedcba9876543210fedcba98';
const indexRevision = 'p1-' + '1'.repeat(64);
const revisionOf = id => id === DEFAULT_PROFILE ? 'c1-' + 'a'.repeat(64) : 'c1-' + 'b'.repeat(64);
const HEADER = 'X-MCP-Profile';
export function memoryStorage() {
  const data = new Map();
  return {getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key), data};
}
const row = (id, label, extra = {}) => ({id, label, port: id === DEFAULT_PROFILE ? 3000 : 18000, is_default: id === DEFAULT_PROFILE,
  disabled_reason: null, status: 'running', blocked_reason: null, ...extra});

// The double. switched: profiles on; echo(operation, id) may lie about the profile; every request is recorded.
function server({ switched = true, labels = { [B]: '會計' }, echo = (_operation, id) => id, dropHeader = false, answer = {} } = {}) {
  const calls = [];
  const known = new Set([DEFAULT_PROFILE, ...Object.keys(labels)]);
  const fetcher = async (path, options = {}) => {
    const headers = options.headers ?? {};
    const profile = dropHeader ? undefined : headers[HEADER];
    calls.push({path, method: options.method ?? 'GET', headers, options, body: options.body});
    const local = path.slice(mount.length);
    if (local === '/api/profiles' || local.startsWith('/api/profiles/')) {
      if (!switched) return new Response(null, {status: 404});
      if ((options.method ?? 'GET') === 'GET') return Response.json({profiles: [...known].map(id => row(id, labels[id] ?? 'Default'))}, {headers: {ETag: `"${indexRevision}"`}});
      if (answer[local]) return answer[local](options);
      const key = headers['Idempotency-Key'];
      if (options.method === 'POST') return Response.json({...row(C, JSON.parse(options.body).label), operation: {id: key, kind: 'profile.create', state: 'completed', replayed: false}, token: 'S'.repeat(43)}, {status: 201});
      if (options.method === 'PATCH') return Response.json(row(local.slice(14), JSON.parse(options.body).label));
      if (options.method === 'DELETE') return Response.json({deleted: local.slice(14), operation: {id: key, kind: 'profile.delete', state: 'completed', replayed: false}});
    }
    if (switched) {
      if (profile === undefined) return Response.json({error: 'request denied', detail: {code: 'profile_id_required'}}, {status: 400});
      if (!known.has(profile)) return Response.json({error: 'request denied', detail: {code: 'profile_not_found'}}, {status: 404});
    }
    const id = switched ? profile : null;
    const operation = local.slice('/api/'.length);
    const named = id === null ? {} : operation === 'bootstrap'
      ? {profile: {id: echo(operation, id), label: labels[echo(operation, id)] ?? 'Default', is_default: echo(operation, id) === DEFAULT_PROFILE}, profiles_supported: true}
      : {profile: {id: echo(operation, id)}};
    if (answer[local]) return answer[local](options, named);
    if (operation === 'bootstrap') return Response.json({product: 'n8n', base_path: mount, api_base: `${mount}/api`, csrf: 'synthetic_csrf_value',
      configuration: {revision: revisionOf(id ?? DEFAULT_PROFILE)}, operation_contract: {version: 1, server_time_ms: 1793318400000}, ...named});
    if (operation.startsWith('operations/')) return Response.json({operation: {id: operation.slice(11), kind: 'token.rotate', state: 'completed', replayed: true}, ...named});
    if (operation === 'token/reveal') return Response.json({token: (id === B ? 'T' : 'M').repeat(43), ...named});
    if (operation === 'token/rotate') return Response.json({status: 'ok', token: 'M'.repeat(43), operation: {id: headers['Idempotency-Key'], kind: 'token.rotate', state: 'completed', replayed: false}, ...named});
    if (['configuration', 'capabilities', 'diagnostics'].includes(operation)) return Response.json({configuration: {}, ...named});
    return Response.json({saved: true, ...named});
  };
  return {fetcher, calls};
}
const header = call => call.headers?.[HEADER];
const fresh = (product = 'n8n') => ({product, operation_contract: {version: 1, server_time_ms: 1793318400000}});

test('switched off: no request names a profile and every request is exactly as before', async () => {
  const {fetcher, calls} = server({switched: false});
  const api = new AdminApi(mount, fetcher, memoryStorage());
  const boot = await api.bootstrap();
  assert.equal(api.profile, null);
  assert.equal(boot.profile, undefined);
  await api.configuration(); await api.capabilities(); await api.diagnostics();
  await api.mutate('endpoint', {endpoint: null}, revisionOf(DEFAULT_PROFILE));
  await api.mutate('token/rotate', undefined, revisionOf(DEFAULT_PROFILE));
  assert.equal(calls.length, 8);
  assert.ok(calls.every(call => header(call) === undefined));
  // A read is sent with exactly the options it had before profiles existed (no headers object at all).
  for (const call of calls.filter(item => item.method === 'GET')) assert.deepEqual(Object.keys(call.options).sort(), ['cache', 'credentials', 'redirect', 'signal']);
  assert.equal(api.pendingProfileOperation(), null);
  await assert.rejects(() => api.profileList(), error => error instanceof ApiError && error.status === 404);
  assert.throws(() => api.select(B), UiError);
});

test('switched on: the first bootstrap finds out; every profile-scoped request names its profile, the default too; profile routes never do', async () => {
  const {fetcher, calls} = server();
  const api = new AdminApi(mount, fetcher, memoryStorage());
  const boot = await api.bootstrap();
  assert.deepEqual(calls.map(header), [undefined, DEFAULT_PROFILE]);   // the probe without, then explicitly the default profile
  assert.deepEqual(boot.profile, {id: DEFAULT_PROFILE, label: 'Default', is_default: true});
  await api.configuration(); await api.capabilities(); await api.diagnostics();
  await api.mutate('endpoint', {endpoint: null}, revisionOf(DEFAULT_PROFILE));
  const list = await api.profileList();
  assert.deepEqual(list.rows.map(item => item.id), [DEFAULT_PROFILE, B]);
  assert.equal(list.revision, indexRevision);
  api.select(B);
  assert.equal((await api.mutate('token/reveal', undefined, undefined, B)).token, 'T'.repeat(43));
  await api.createProfile('  出納  ', list.revision);
  await api.renameProfile(B, '會計二', list.revision);
  await api.deleteProfile(B, list.revision);
  const scoped = calls.filter(call => !call.path.includes('/api/profiles'));
  const global = calls.filter(call => call.path.includes('/api/profiles'));
  // ... the reveal's bootstrap and the reveal on B; the fresh bootstraps of create, rename and delete are the default
  // profile's (the CSRF value is shared, and a profile that cannot be read must stay deletable).
  assert.deepEqual(scoped.slice(1).map(header), [DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE,
    B, B, DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE]);
  assert.equal(global.length, 4);
  assert.ok(global.every(call => header(call) === undefined && !Object.keys(call.headers).some(name => name.toLowerCase() === 'x-mcp-profile')));
});

test('a server that keeps refusing the header is not asked forever', async () => {
  const {fetcher, calls} = server({dropHeader: true});
  const api = new AdminApi(mount, fetcher, memoryStorage());
  await assert.rejects(() => api.bootstrap(), error => error instanceof ApiError && error.code === 'profile_id_required' && /轉送帳號標頭/.test(error.message));
  assert.equal(calls.length, 2);
});

test('an answer for a profile nobody asked for is never used (contract 3.4, I12)', async () => {
  // A probe answered with a profile echo: asked again, explicitly for the default profile.
  {
    let probes = 0;
    const base = server();
    const api = new AdminApi(mount, async (path, options = {}) => {
      if (path.endsWith('/bootstrap') && !options.headers?.[HEADER]) { probes++; return Response.json({product: 'n8n', base_path: mount, api_base: `${mount}/api`, profile: {id: B, label: '會計', is_default: false}, profiles_supported: true}); }
      return base.fetcher(path, options);
    }, memoryStorage());
    assert.equal((await api.bootstrap()).profile.id, DEFAULT_PROFILE);
    assert.equal(probes, 1);
  }
  for (const [lie, operation] of [[() => B, 'bootstrap'], [() => DEFAULT_PROFILE, 'token/reveal'], [() => B, 'configuration']]) {
    const echo = (name, id) => name === operation && id === C ? lie() : id;
    const {fetcher, calls} = server({labels: {[B]: '會計', [C]: '出納'}, echo});
    const api = new AdminApi(mount, fetcher, memoryStorage());
    await api.bootstrap();
    api.select(C);
    const before = calls.length;
    const attempt = operation === 'configuration' ? api.configuration() : api.mutate('token/reveal', undefined, undefined, C);
    await assert.rejects(() => attempt, ProfileEchoError);
    // A bootstrap that names another profile stops the change before it is sent.
    if (operation === 'bootstrap') assert.equal(calls.length - before, 1);
  }
  // Missing pieces of the bootstrap echo, and an echo where a single-profile server has none.
  assert.equal(echoMatches({profile: {id: DEFAULT_PROFILE, label: 'Default', is_default: true}}, DEFAULT_PROFILE, true), false);
  assert.equal(echoMatches({profile: {id: B, label: '會計', is_default: true}, profiles_supported: true}, B, true), false);
  assert.equal(echoMatches({profile: {id: B, label: 'a\u202eb', is_default: false}, profiles_supported: true}, B, true), true);   // never shown (review S-2)
  assert.equal(echoMatches({profile: {id: B, label: '', is_default: false}, profiles_supported: true}, B, true), false);
  assert.equal(echoMatches({profile: {id: B, label: 'x'.repeat(81), is_default: false}, profiles_supported: true}, B, true), false);
  assert.equal(echoMatches({profile: {id: DEFAULT_PROFILE, label: 'Default', is_default: true}, profiles_supported: false}, DEFAULT_PROFILE, true), true);   // DQ-28
  assert.equal(echoMatches({profile: {id: DEFAULT_PROFILE, label: 'Default', is_default: true}, profiles_supported: 'yes'}, DEFAULT_PROFILE, true), false);
  assert.equal(echoMatches({profile: {id: B, label: '會計'}}, B), false);
  assert.equal(echoMatches({saved: true}, B), false);
  assert.equal(echoMatches({saved: true, profile: {id: DEFAULT_PROFILE}}, null), false);
  assert.equal(echoMatches({saved: true}, null), true);
  const single = new AdminApi(mount, async path => Response.json(path.endsWith('/bootstrap')
    ? {product: 'n8n', base_path: mount, api_base: `${mount}/api`} : {configuration: {}, profile: {id: DEFAULT_PROFILE}}), memoryStorage());
  await single.bootstrap();
  await assert.rejects(() => single.configuration(), ProfileEchoError);
});

// HM-11 review S-4: an answer without a body cannot name its profile, so with profiles a profile-scoped 204 is refused
// like any other answer without the echo; switched off a 204 is read as before (no value).
test('with profiles a profile-scoped answer without a body (204) is not used; switched off it is as before', async () => {
  const empty = () => new Response(null, {status: 204});
  const on = server({answer: {'/api/configuration': empty, '/api/token/reveal': empty}});
  const api = new AdminApi(mount, on.fetcher, memoryStorage());
  await api.bootstrap();
  await assert.rejects(() => api.configuration(), ProfileEchoError);
  api.select(B);
  await assert.rejects(() => api.configuration(), ProfileEchoError);
  await assert.rejects(() => api.mutate('token/reveal', undefined, undefined, B), ProfileEchoError);
  const off = server({switched: false, answer: {'/api/configuration': empty}});
  const single = new AdminApi(mount, off.fetcher, memoryStorage());
  await single.bootstrap();
  assert.equal(await single.configuration(), null);
});

test('mutate(profile) fixes the profile: both requests carry it; a caller whose profile is no longer selected sends nothing', async () => {
  const {fetcher, calls} = server();
  const api = new AdminApi(mount, fetcher, memoryStorage());
  await api.bootstrap();
  api.select(B);
  const before = calls.length;
  await api.mutate('policy', {writes_enabled: false, disabled: []}, revisionOf(B), B);
  assert.deepEqual(calls.slice(before).map(header), [B, B]);
  assert.equal(calls.at(-1).headers['If-Match'], `"${revisionOf(B)}"`);
  await assert.rejects(() => api.mutate('policy', {writes_enabled: false, disabled: []}, revisionOf(DEFAULT_PROFILE), DEFAULT_PROFILE), StaleProfileError);
  assert.equal(calls.length, before + 2);
  await assert.rejects(() => api.mutate('policy', {}, revisionOf(B), 'not-a-profile'), StaleProfileError);
  assert.equal(calls.length, before + 2);
});

test('an answer that arrives after the profile changed is dropped, its receipt kept for its own profile', async () => {
  const base = server();
  let release;
  const held = new Promise(resolve => { release = resolve; });
  const api = new AdminApi(mount, async (path, options) => {
    if (path.endsWith('/token/rotate') || path.endsWith('/configuration')) { await held; }
    return base.fetcher(path, options);
  }, memoryStorage());
  await api.bootstrap();
  api.select(B);
  const reading = api.configuration();
  const rotating = (async () => { await reading.catch(() => {}); return api.mutate('token/rotate', undefined, revisionOf(B), B); })();
  await new Promise(resolve => setImmediate(resolve));
  api.select(DEFAULT_PROFILE);
  release();
  await assert.rejects(() => reading, StaleProfileError);
  await assert.rejects(() => rotating, StaleProfileError);   // started under the old epoch: nothing sent
  assert.equal(base.calls.filter(call => call.path.endsWith('/token/rotate')).length, 0);
  // A change whose answer comes late keeps its identity for its profile; the default profile has none.
  let late;
  const slow = new Promise(resolve => { late = resolve; });
  const second = new AdminApi(mount, async (path, options) => {
    if (path.endsWith('/token/rotate')) await slow;
    return base.fetcher(path, options);
  }, memoryStorage());
  await second.bootstrap();
  second.select(B);
  const change = second.mutate('token/rotate', undefined, revisionOf(B), B);
  await new Promise(resolve => setTimeout(resolve, 5));
  second.select(DEFAULT_PROFILE);
  late();
  await assert.rejects(() => change, StaleProfileError);
  assert.equal(second.pendingOperation(B).profile, B);
  assert.equal(second.pendingOperation(), null);
});

test('receipts: the default profile keeps its key and 4-key record; an additional profile its own key and 5 keys; get() takes each format only under its key', async () => {
  const storage = memoryStorage();
  const identity = new OperationIdentity(mount, storage);
  const legacy = `woow-admin-operation-v1:${mount}`;
  const first = identity.start('token/rotate', revisionOf(DEFAULT_PROFILE), fresh(), DEFAULT_PROFILE);
  assert.deepEqual(Object.keys(first).sort(), ['id', 'product', 'revision', 'route']);
  assert.deepEqual([...storage.data.keys()], [legacy]);
  assert.deepEqual(identity.get(null), first);   // a server without profiles reads the same record
  const extra = identity.start('token/revoke', revisionOf(B), fresh(), B);
  assert.deepEqual(Object.keys(extra).sort(), ['id', 'product', 'profile', 'revision', 'route']);
  assert.equal(extra.profile, B);
  assert.deepEqual([...storage.data.keys()], [legacy, `${legacy}:${B}`]);
  assert.equal(identity.get(C), null);
  assert.throws(() => identity.start('token/rotate', revisionOf(B), fresh(), B), /另一筆操作/);
  // Each key holds only its own format.
  storage.setItem(`${legacy}:${C}`, JSON.stringify(first));
  assert.throws(() => identity.get(C), /不相容/);
  storage.setItem(`${legacy}:${C}`, JSON.stringify({...extra, profile: B}));
  assert.throws(() => identity.get(C), /不相容/);
  storage.setItem(legacy, JSON.stringify(extra));
  assert.throws(() => identity.get(DEFAULT_PROFILE), /不相容/);
  assert.throws(() => identity.keyFor('../x'), UiError);
  // Profile create and delete: their own key; a resend is the same record, another label is refused.
  const create = identity.start('profiles/create', indexRevision, fresh(), PROFILES_SCOPE, {label: '出納'});
  assert.deepEqual(Object.keys(create).sort(), ['id', 'label', 'product', 'revision', 'route']);
  assert.ok(storage.data.has(`${legacy}:profiles`));
  assert.deepEqual(identity.start('profiles/create', indexRevision, fresh(), PROFILES_SCOPE), create);
  assert.throws(() => identity.start('profiles/create', indexRevision, fresh(), PROFILES_SCOPE, {label: '別的'}), /另一筆帳號操作/);
  identity.clear(PROFILES_SCOPE);
  const remove = identity.start('profiles/delete', indexRevision, fresh(), PROFILES_SCOPE, {profile: B});
  assert.deepEqual(Object.keys(remove).sort(), ['id', 'product', 'profile', 'revision', 'route']);
  assert.throws(() => identity.start('profiles/delete', revisionOf(B), fresh(), C, {}), UiError);
  identity.clear(PROFILES_SCOPE);
  assert.throws(() => identity.start('profiles/delete', indexRevision, fresh(), PROFILES_SCOPE, {profile: DEFAULT_PROFILE}), /內容不符/);
  assert.throws(() => identity.start('profiles/create', indexRevision, fresh(), PROFILES_SCOPE, {label: 'a\u200bb'}), /內容不符/);
});

test('a record the previous panel left (4 keys) is queried after the upgrade, now naming the default profile', async () => {
  const storage = memoryStorage();
  const id = '1793318400000.' + 'ab'.repeat(16);
  storage.setItem(`woow-admin-operation-v1:${mount}`, JSON.stringify({id, route: 'token/rotate', revision: revisionOf(DEFAULT_PROFILE), product: 'n8n'}));
  const {fetcher, calls} = server();
  const api = new AdminApi(mount, fetcher, storage);
  await api.bootstrap();
  assert.equal(api.pendingOperation().id, id);
  assert.equal((await api.queryOperation()).state, 'completed');
  assert.equal(header(calls.at(-1)), DEFAULT_PROFILE);
  assert.equal(calls.at(-1).path, `${mount}/api/operations/${id}`);
  assert.equal(api.pendingOperation(), null);
  // The same record is not shown for an additional profile.
  storage.setItem(`woow-admin-operation-v1:${mount}`, JSON.stringify({id, route: 'token/rotate', revision: revisionOf(DEFAULT_PROFILE), product: 'n8n'}));
  api.select(B);
  assert.equal(api.pendingOperation(), null);
});

test('profile create, rename and delete: routes, bodies, If-Match of the index, an identity, no X-MCP-Profile, never a token', async () => {
  const {fetcher, calls} = server();
  const storage = memoryStorage();
  const api = new AdminApi(mount, fetcher, storage);
  await api.bootstrap();
  const created = await api.createProfile('  出納 ', indexRevision);
  assert.deepEqual(created, {id: C, label: '出納', replayed: false});   // the token the double sent is not passed on
  const post = calls.find(call => call.method === 'POST');
  assert.equal(post.path, `${mount}/api/profiles`);
  assert.deepEqual(JSON.parse(post.body), {label: '出納'});
  assert.equal(post.headers['If-Match'], `"${indexRevision}"`);
  assert.match(post.headers['Idempotency-Key'], /^1793318400000\.[0-9a-f]{32}$/);
  assert.equal(post.headers['X-CSRF-Token'], 'synthetic_csrf_value');
  assert.equal(api.pendingProfileOperation(), null);
  await api.renameProfile(B, '會計二', indexRevision);
  const patch = calls.find(call => call.method === 'PATCH');
  assert.deepEqual([patch.path, JSON.parse(patch.body), patch.headers['If-Match'], patch.headers['Idempotency-Key']],
    [`${mount}/api/profiles/${B}`, {label: '會計二'}, `"${indexRevision}"`, undefined]);
  assert.deepEqual(await api.deleteProfile(B, indexRevision), {deleted: B, replayed: false});
  const remove = calls.find(call => call.method === 'DELETE');
  assert.deepEqual([remove.path, remove.body, remove.headers['If-Match']], [`${mount}/api/profiles/${B}`, undefined, `"${indexRevision}"`]);
  assert.match(remove.headers['Idempotency-Key'], /^1793318400000\./);
  assert.ok(calls.every(call => !call.path.includes('/api/profiles') || header(call) === undefined));
  const sent = calls.length;
  await assert.rejects(() => api.deleteProfile(DEFAULT_PROFILE, indexRevision), /預設帳號/);
  await assert.rejects(() => api.renameProfile(DEFAULT_PROFILE, 'x', indexRevision), /預設帳號/);
  await assert.rejects(() => api.createProfile('default', indexRevision), /保留名稱/);
  await assert.rejects(() => api.createProfile('出納', 'c1-' + 'a'.repeat(64)), /版本格式/);
  assert.equal(calls.length, sent);
});

test('a lost create answer keeps its identity; the resend is the same request; a refusal before the intent releases it', async () => {
  let lost = true, conflict = false;
  const sent = [];
  const base = server({answer: {'/api/profiles': options => {
    sent.push({key: options.headers['Idempotency-Key'], body: options.body});
    if (lost) { lost = false; throw Error('synthetic lost answer'); }
    if (conflict) return Response.json({error: 'request denied', detail: {code: 'profile_label_conflict'}}, {status: 409});
    return Response.json({...row(C, '出納'), operation: {id: options.headers['Idempotency-Key'], kind: 'profile.create', state: 'completed', replayed: true}});
  }}});
  const storage = memoryStorage();
  const api = new AdminApi(mount, base.fetcher, storage);
  await api.bootstrap();
  await assert.rejects(() => api.createProfile('出納', indexRevision), /連線中斷/);
  const pending = api.pendingProfileOperation();
  assert.deepEqual([pending.route, pending.label, pending.revision], ['profiles/create', '出納', indexRevision]);
  const reopened = new AdminApi(mount, base.fetcher, storage);   // a reload of the page
  await reopened.bootstrap();
  assert.deepEqual(await reopened.retryProfileOperation(), {id: C, label: '出納', replayed: true});
  assert.equal(sent[0].key, sent[1].key);
  assert.equal(sent[0].body, sent[1].body);
  assert.equal(reopened.pendingProfileOperation(), null);
  conflict = true;
  await assert.rejects(() => reopened.createProfile('出納', indexRevision), error => error.code === 'profile_label_conflict' && /同名/.test(error.message));
  assert.equal(reopened.pendingProfileOperation(), null);
});

// Align review S-2: HM-10 answers a failure after the commit (a directory not made, the index or the receipt not
// written) with 409 operation_outcome_unknown, and the same key keeps getting it. That is no refusal before the
// intent: the identity is kept, so a resend stays the same request and never a second creation or deletion.
test('an unknown outcome of a profile create or delete (409 operation_outcome_unknown) keeps its identity', async () => {
  const unknown = () => Response.json({error: 'request denied', detail: {code: 'operation_outcome_unknown'}}, {status: 409});
  for (const [route, attempt] of [['profiles/create', api => api.createProfile('出納', indexRevision)], ['profiles/delete', api => api.deleteProfile(B, indexRevision)]]) {
    const base = server({answer: {'/api/profiles': unknown, [`/api/profiles/${B}`]: unknown}});
    const api = new AdminApi(mount, base.fetcher, memoryStorage());
    await api.bootstrap();
    await assert.rejects(() => attempt(api), error => error instanceof ApiError && error.code === 'operation_outcome_unknown', route);
    const pending = api.pendingProfileOperation();
    assert.equal(pending?.route, route);
    const sent = base.calls.filter(call => call.method !== 'GET' && call.path.includes('/api/profiles'));
    assert.equal(sent.length, 1, route);
    assert.equal(sent[0].headers['Idempotency-Key'], pending.id, route);
  }
});

test('list rows and what the menu says about them (PaaS profileStatus.test; §8.8 #51)', () => {
  assert.equal(optionLabel(row(DEFAULT_PROFILE, 'Default')), '預設帳號（default） · 執行中');
  assert.equal(optionLabel(row(B, '會計')), '會計（01234567） · 執行中');
  for (const [reason, text] of [['memory_capacity', '記憶體不足，已停用'], ['profile_limit', '超過帳號上限，已停用'], ['port_conflict', 'port 衝突，已停用'],
    ['profile_unavailable', '設定讀不到，已停用'], ['quarantined', '已隔離，已停用'], ['dormant', '休眠，已停用'], ['future_reason', '已停用']]) {
    assert.equal(optionLabel(row(B, '會計', {disabled_reason: reason})), `會計（01234567） · 執行中 · ${text}`);
  }
  assert.equal(optionLabel(row(B, '會計', {status: 'surprise'})), '會計（01234567） · 未知狀態');
  assert.match(disabledNotice(row(B, '會計', {disabled_reason: 'memory_capacity', required_memory_mib: 1156})), /記憶體不足.*1156 MiB/);
  assert.doesNotMatch(disabledNotice(row(B, '會計', {disabled_reason: 'memory_capacity'})), /MiB/);
  assert.match(disabledNotice(row(B, '會計', {disabled_reason: 'port_conflict'})), /port/);
  assert.match(disabledNotice(row(B, '會計', {disabled_reason: 'profile_limit'})), /帳號上限/);
  assert.match(disabledNotice(row(B, '會計', {disabled_reason: 'future_reason'})), /停用/);
  assert.equal(disabledNotice(row(B, '會計')), '');
  assert.match(blockedNotice(row(B, '會計', {status: 'blocked', blocked_reason: 'child_port_in_use'})), /已被其他程式占用/);
  assert.match(blockedNotice(row(B, '會計', {status: 'blocked', blocked_reason: 'something_else'})), /原因未知/);
  assert.equal(blockedNotice(row(B, '會計')), '');
  const rows = [row(DEFAULT_PROFILE, 'Default'), row(B, '會計')];
  assert.deepEqual(profileRows({profiles: rows}), rows);
  for (const broken of [[row(B, '會計')], [...rows, row(B, '重複')], [row(DEFAULT_PROFILE, 'Default'), row('ABC', 'x')],
    [row(DEFAULT_PROFILE, 'Default'), row(B, '')], [row(DEFAULT_PROFILE, 'Default'), row(B, 'x'.repeat(81))], [row(DEFAULT_PROFILE, 'Default'), row(B, 42)],
    [row(DEFAULT_PROFILE, 'Default'), {...row(B, '會計'), is_default: true}], [row(DEFAULT_PROFILE, 'Default'), row(B, '會計', {port: 80})],
    [row(DEFAULT_PROFILE, 'Default'), row(B, '會計', {disabled_reason: '<b>x</b>'})], Array(7).fill(0).map((_, n) => row(n ? n.toString(16).padStart(24, '0') : DEFAULT_PROFILE, `p${n}`))]) {
    assert.throws(() => profileRows({profiles: broken}), /帳號清單格式不符/);
  }
  assert.equal(shortId(DEFAULT_PROFILE), DEFAULT_PROFILE);
  assert.equal(shortId(B), '01234567');
});

test('labels count code points; control, format and reserved names are refused before any request (DQ-16)', () => {
  assert.equal(labelProblem('會計'), null);
  assert.equal(labelProblem('😀'.repeat(80)), null);   // 80 code points, 160 UTF-16 units
  assert.match(labelProblem('😀'.repeat(81)), /最多 80 個字（目前 81 個）/);
  assert.equal(labelProblem('<img src=x onerror=alert(1)>'), null);   // allowed; always shown as text
  for (const bad of ['', '   ', 'a\u200bb', 'a\u202eb', 'a\u0007b', 'a\u2028b', 'a\u2029b', 'a\ue000b', 'a\ufeffb', 'a\u{e0001}b', 'a\ud800b', 'Default', ' DEFAULT ', 'ｄｅｆａｕｌｔ', '預設帳號', 42, null]) {
    assert.notEqual(labelProblem(bad), null, String(bad));
  }
});

test('the policy fingerprint names the profile; the example names an additional profile; a restart notice says only this profile', () => {
  const policy = {product: 'odoo', policy_contract: 'woow-v3-exact-grants', tools: {}, disabled: [], writes_enabled: false, enabled_write_tools: []};
  assert.notEqual(policyFingerprint({...policy, profile: {id: DEFAULT_PROFILE}}), policyFingerprint({...policy, profile: {id: B}}));
  assert.equal(clientName('odoo', null), 'woow');
  assert.equal(clientName('odoo', DEFAULT_PROFILE), 'woow');
  assert.equal(clientName('odoo', B), 'woow-odoo-01234567');
  assert.deepEqual(Object.keys(JSON.parse(clientExample(null, null, clientName('odoo', B))).mcpServers), ['woow-odoo-01234567']);
  assert.equal(clientExample(null), clientExample(null, null, 'woow'));
  assert.throws(() => clientExample(null, null, 'woow"}'), UiError);
  assert.match(policyRestartNotice('emqx', true), /只會重新啟動這個帳號/);
  assert.equal(policyRestartNotice('emqx'), policyRestartNotice('emqx', false));
  assert.equal(policyRestartNotice('odoo', true), '');
});

test('profile codes get fixed copy only with their documented status; numbers are the only values taken', async () => {
  const answer = (status, detail) => async path => path.endsWith('/bootstrap') ? Response.json({error: 'request denied', detail}, {status}) : null;
  for (const [status, detail, code, copy] of [
    [409, {code: 'profile_limit_reached', limit: 5, message: 'PRIVATE_CANARY'}, 'profile_limit_reached', /最多 5 個額外帳號/],
    [409, {code: 'profile_memory_insufficient', required_memory_mib: 1156, available_memory_mib: '<b>'}, 'profile_memory_insufficient', /1156 MiB）/],
    [404, {code: 'profile_not_found'}, 'profile_not_found', /已不存在/],
    [503, {code: 'profile_index_corrupt'}, 'profile_index_corrupt', /帳號索引損壞/],
    [409, {code: 'endpoint_global'}, 'endpoint_global', /只能在預設帳號修改/],
    [409, {code: 'profile_not_found'}, null, /設定已變更/],
    [422, {code: 'profile_id_required'}, null, /欄位驗證未通過/],
  ]) {
    const api = new AdminApi(mount, answer(status, detail), memoryStorage());
    await assert.rejects(() => api.open(), error => error instanceof ApiError && error.code === code && copy.test(error.message)
      && !error.message.includes('PRIVATE_CANARY') && !error.message.includes('<b>'));
  }
});

test('the P9 kit names the profile by itself and a caller header cannot override it', async () => {
  const {fetcher, calls} = server();
  const p9 = createP9AdminClient(`https://ha.example${mount}/`, {Cookie: 'ingress_session=fixture'}, async (url, options) => fetcher(url.pathname, options));
  const boot = await p9.bootstrap();
  assert.equal(boot.profile.id, DEFAULT_PROFILE);
  await p9.mutate('endpoint', {endpoint: null}, revisionOf(DEFAULT_PROFILE));
  assert.deepEqual(calls.map(header), [undefined, DEFAULT_PROFILE, DEFAULT_PROFILE, DEFAULT_PROFILE]);
  assert.equal(calls.at(-1).headers.Cookie, 'ingress_session=fixture');
  const other = server();
  const forB = createP9AdminClient(`https://ha.example${mount}/`, {}, async (url, options) => other.fetcher(url.pathname, options), {profile: B});
  assert.equal((await forB.bootstrap()).profile.id, B);
  assert.equal((await forB.mutate('token/reveal')).token, 'T'.repeat(43));
  assert.ok(other.calls.slice(1).every(call => header(call) === B));
  assert.throws(() => createP9AdminClient(`https://ha.example${mount}/`, {'x-mcp-profile': B}), /X-MCP-Profile/);
  const single = server({switched: false});
  const p9Single = createP9AdminClient(`https://ha.example${mount}/`, {}, async (url, options) => single.fetcher(url.pathname, options), {profile: B});
  await assert.rejects(() => p9Single.bootstrap(), /沒有開通多帳號/);
});

// ---- HM-11 aligned with HM-10's real management API (2026-11-16) ----

// Review S-2: one label this browser cannot show hides only that label (its row stays, by its id); a list without its
// ETag is shown but read-only; the orphans (DQ-14) are read beside the rows.
test('a row whose label this browser cannot show stays, by its id; orphans are read; a list without its ETag is read-only', async () => {
  const rows = [row(DEFAULT_PROFILE, 'Default'), row(B, 'a\u202eb'), row(C, ' 前後 ')];
  const shown = profileRows({profiles: rows});
  assert.deepEqual(shown.map(item => [item.id, item.label, item.hidden ?? false]), [[DEFAULT_PROFILE, 'Default', false], [B, null, true], [C, null, true]]);
  assert.equal(profileName(shown[1]), '名稱無法顯示的帳號');
  assert.equal(optionLabel(shown[1]), '名稱無法顯示的帳號（01234567） · 執行中');
  const E = 'e'.repeat(24), F = 'f'.repeat(24);
  assert.deepEqual(orphanIds({orphans: [{id: E}, {id: F}]}, shown), [E, F]);
  assert.deepEqual(orphanIds({}, shown), []);
  for (const broken of [[{id: E}, {id: E}], [{id: B}], [{id: DEFAULT_PROFILE}], [{id: E, label: 'x'}], 'x', [E]]) {
    assert.throws(() => orphanIds({orphans: broken}, shown), /帳號清單格式不符/);
  }
  for (const etag of [null, `W/"${indexRevision}"`, indexRevision, '"p1-short"']) {
    const api = new AdminApi(mount, async (path, options = {}) => {
      if (path.endsWith('/api/profiles')) return Response.json({profiles: [row(DEFAULT_PROFILE, 'Default'), row(B, '會計')], orphans: [{id: E}]}, {headers: etag === null ? {} : {ETag: etag}});
      return server().fetcher(path, options);
    }, memoryStorage());
    await api.bootstrap();
    const list = await api.profileList();
    assert.deepEqual([list.rows.length, list.orphans, list.revision], [2, [E], null], String(etag));
  }
  assert.deepEqual(indexState({profile_index_state: 'corrupt', profile_index_etag: `"${indexRevision}"`}), {corrupt: true, etag: `"${indexRevision}"`});
  assert.deepEqual(indexState({profile_index_state: 'corrupt', profile_index_etag: indexRevision}), {corrupt: true, etag: null});
  assert.deepEqual(indexState({profile_index_state: 'ok'}), {corrupt: false, etag: null});
});

test('the bootstrap of a product without additional profiles (profiles_supported false, DQ-28) is used as the default profile', async () => {
  const base = server();
  const api = new AdminApi(mount, async (path, options = {}) => {
    const answer = await base.fetcher(path, options);
    if (!path.endsWith('/bootstrap') || answer.status !== 200) return answer;
    return Response.json({...await answer.json(), product: 'opendesign', profiles_supported: false});
  }, memoryStorage());
  const boot = await api.bootstrap();
  assert.deepEqual([api.profile, boot.profiles_supported, boot.profile.id], [DEFAULT_PROFILE, false, DEFAULT_PROFILE]);
});

test('a created profile deleted since is replayed as its id alone: confirmed, gone, its identity released', async () => {
  const storage = memoryStorage();
  let lose = true;
  const base = server({answer: {'/api/profiles': options => {
    if (lose) { lose = false; throw Error('synthetic lost answer'); }
    return Response.json({id: C, operation: {id: options.headers['Idempotency-Key'], kind: 'profile.create', state: 'completed', replayed: true}});
  }}});
  const api = new AdminApi(mount, base.fetcher, storage);
  await api.bootstrap();
  await assert.rejects(() => api.createProfile('出納', indexRevision), /連線中斷/);
  assert.deepEqual(await api.retryProfileOperation(), {id: C, label: null, replayed: true, gone: true});
  assert.equal(api.pendingProfileOperation(), null);
  // An answer of another shape is no confirmation: the identity is kept.
  const odd = server({answer: {'/api/profiles': options => Response.json({id: C, deleted: C, operation: {id: options.headers['Idempotency-Key'], kind: 'profile.create', state: 'completed', replayed: true}})}});
  const other = new AdminApi(mount, odd.fetcher, memoryStorage());
  await other.bootstrap();
  await assert.rejects(() => other.createProfile('出納', indexRevision), /帳號清單格式不符|預期的帳號確認/);
  assert.notEqual(other.pendingProfileOperation(), null);
  // A created row whose label this browser cannot show is confirmed, but its label is not passed on (review S-2).
  const hidden = server({answer: {'/api/profiles': options => Response.json({...row(C, 'a\u202eb'), operation: {id: options.headers['Idempotency-Key'], kind: 'profile.create', state: 'completed', replayed: false}}, {status: 201})}});
  const third = new AdminApi(mount, hidden.fetcher, memoryStorage());
  await third.bootstrap();
  assert.deepEqual(await third.createProfile('出納', indexRevision), {id: C, label: null, replayed: false});
});

test('the index quarantine: a POST without a body, the unusable index\'s ETag as given, an identity, CSRF, no X-MCP-Profile', async () => {
  const etag = `"p1-${'f'.repeat(64)}"`, name = 'profiles.json.quarantine-20261116T000000Z';
  let status = 'lost';
  const sent = [];
  const base = server({answer: {'/api/profiles/index/quarantine': options => {
    sent.push(options);
    if (status === 'lost') { status = 'ok'; throw Error('synthetic lost answer'); }
    if (status === 'busy') return Response.json({error: 'request denied'}, {status: 503});
    if (status === 'conflict') return Response.json({detail: {code: 'config_conflict'}}, {status: 409, headers: {ETag: etag}});
    return Response.json({quarantined: name, operation: {id: options.headers['Idempotency-Key'], kind: 'profile.index_quarantine', state: 'completed', replayed: sent.length > 1}});
  }}});
  const storage = memoryStorage();
  const api = new AdminApi(mount, base.fetcher, storage);
  await api.bootstrap();
  await assert.rejects(() => api.quarantineIndex(etag), /連線中斷/);
  const pending = api.pendingProfileOperation();
  assert.deepEqual(Object.keys(pending).sort(), ['id', 'product', 'revision', 'route']);
  assert.deepEqual([pending.route, pending.revision], ['profiles/quarantine', etag.slice(1, -1)]);
  const reopened = new AdminApi(mount, base.fetcher, storage);   // a reload of the page
  await reopened.bootstrap();
  assert.deepEqual(await reopened.retryProfileOperation(), {quarantined: name, replayed: true});
  const [first, second] = sent;
  for (const options of [first, second]) {
    assert.equal(options.method, 'POST');
    assert.equal(options.body, undefined);
    assert.deepEqual(Object.keys(options.headers).sort(), ['Idempotency-Key', 'If-Match', 'X-CSRF-Token']);
    assert.equal(options.headers['If-Match'], etag);
  }
  assert.equal(first.headers['Idempotency-Key'], second.headers['Idempotency-Key']);
  assert.equal(api.pendingProfileOperation(), null);
  // Refused before the intent (409 config_conflict): released; a bare 503 (another profile's change holds its lock): kept.
  status = 'conflict';
  await assert.rejects(() => api.quarantineIndex(etag), error => error instanceof ApiError && error.code === 'config_conflict');
  assert.equal(api.pendingProfileOperation(), null);
  status = 'busy';
  await assert.rejects(() => api.quarantineIndex(etag), error => error instanceof ApiError && error.status === 503 && error.code === null);
  assert.equal(api.pendingProfileOperation().route, 'profiles/quarantine');
  assert.throws(() => api.quarantineIndex(etag.slice(1, -1)), /版本格式不符/);
});

test('limit 0 (the open file limit holds no additional profile) says the add-on serves the default profile only', async () => {
  const api = new AdminApi(mount, async () => Response.json({error: 'request denied', detail: {code: 'profile_limit_reached', limit: 0}}, {status: 409}), memoryStorage());
  await assert.rejects(() => api.open(), error => error.code === 'profile_limit_reached' && /只能服務預設帳號/.test(error.message) && !/最多 0/.test(error.message));
});

// The requests the panel sends are the ones tests/profile-api-cases.json checked against the add-on
// (tests/test_panel_profile_api_shapes.py): method, path, which of X-MCP-Profile, X-CSRF-Token, If-Match,
// Idempotency-Key and a JSON body, and the body's keys.
test('every management request the panel sends with profiles is the case the add-on answered as recorded', async () => {
  const cases = JSON.parse(readFileSync(new URL('./profile-api-cases.json', import.meta.url), 'utf8'));
  const named = Object.fromEntries(cases.scenarios.flatMap(scenario => scenario.cases.map(item => [`${scenario.name}/${item.name}`, item.request])));
  const N = C, quarantineEtag = `"p1-${'f'.repeat(64)}"`;
  const ids = {...cases.rules.ids, B, N};
  const base = server({labels: {[B]: 'Beta Ops'}, answer: {
    '/api/profiles/index/quarantine': options => Response.json({quarantined: 'profiles.json.quarantine-20261116T000000Z', operation: {id: options.headers['Idempotency-Key'], kind: 'profile.index_quarantine', state: 'completed', replayed: false}}),
  }});
  const api = new AdminApi(mount, base.fetcher, memoryStorage());
  await api.bootstrap();
  const calls = [];
  const last = async (action, scope = () => true) => { const before = base.calls.length; await action(); calls.push(base.calls.slice(before).filter(scope).at(-1)); };
  const profileRoute = call => call.path.includes('/api/profiles');
  const scopedRoute = call => !profileRoute(call) && !call.path.endsWith('/bootstrap');
  const checks = [
    ['main/list', () => api.profileList()],
    ['main/create', () => api.createProfile('Kappa Desk', indexRevision), profileRoute],
    ['main/rename', () => api.renameProfile(N, 'Kappa Desk Two', indexRevision), profileRoute],
    ['main/delete', () => api.deleteProfile(N, indexRevision), profileRoute],
    ['corrupt/quarantine', () => api.quarantineIndex(quarantineEtag), profileRoute],
    ['main/endpoint-default', () => api.mutate('endpoint', {endpoint: cases.rules.endpoint}, revisionOf(DEFAULT_PROFILE)), scopedRoute],
    ['main/bootstrap-B', async () => { api.select(B); await api.bootstrap(); }],
    ['main/configuration-B', () => api.configuration()],
    ['main/capabilities-B', () => api.capabilities()],
    ['main/diagnostics-B', () => api.diagnostics()],
    ['main/reveal-B', () => api.mutate('token/reveal', undefined, undefined, B), scopedRoute],
    ['main/rotate-B', () => api.mutate('token/rotate', undefined, revisionOf(B), B), scopedRoute],
    ['main/policy-B', () => api.mutate('policy', {writes_enabled: false, disabled: [], enabled_write_tools: []}, revisionOf(B), B), scopedRoute],
    ['main/notice-dismiss-B', () => api.mutate('owner-defaults/dismiss', undefined, revisionOf(B), B), scopedRoute],
    // HM-12: the backend saves (the partial edit and the whole connection) of profile B.
    ['identity/patch-username', () => api.mutate('backend/patch', {changes: {username: 'DUMMY-user-two'}}, revisionOf(B), B), scopedRoute],
    ['identity/replace-database', () => api.mutate('backend', {connection: {url: 'https://pbbbb.odoo.invalid/odoo', database: 'DUMMY-db-two',
      username: 'DUMMY-user-two', password: 'DUMMY-pbbbb-odoo-password-three'}}, revisionOf(B), B), scopedRoute],
  ];
  for (const [, action, scope] of checks) await last(action, scope);
  checks.forEach(([name], index) => {
    const spec = named[name], call = calls[index];
    const headers = Object.fromEntries(Object.entries(call.headers ?? {}).map(([key, value]) => [key.toLowerCase(), value]));
    const path = spec.path.replace(/\{([A-Z])\}/g, (_, role) => ids[role]);
    assert.deepEqual({method: call.method, path: call.path.slice(mount.length), profile: 'x-mcp-profile' in headers, csrf: 'x-csrf-token' in headers,
      ifMatch: 'if-match' in headers, key: 'idempotency-key' in headers, json: headers['content-type'] === 'application/json',
      body: call.body === undefined ? null : Object.keys(JSON.parse(call.body)).sort()},
    {method: spec.method, path, profile: spec.profile !== undefined, csrf: spec.csrf === true, ifMatch: spec.if_match !== undefined, key: spec.key !== undefined,
      json: spec.body !== undefined, body: spec.body === undefined ? null : Object.keys(spec.body).sort()}, name);
    if (spec.profile !== undefined && !spec.profile.includes(',')) assert.equal(headers['x-mcp-profile'], ids[spec.profile] ?? spec.profile, name);
  });
});

// ---- HM-12 (DQ-05, DQ-40 ⑨ (a); contract 3.1, 4.1, section 9 #113-#115 and HM-12's panel rows): a backend save once the
// product is switched on.
// The copy is the panel's own (the server sends codes and flags only, #113); these are the texts the panel shows.
const ROTATED = '後端身分已變更，這個帳號的 MCP 權杖已換新：舊權杖與含舊權杖的連線網址已撤銷。請到「連線與權杖」顯示並複製新的權杖（或 Claude.ai 連線網址），更新所有用戶端。';
const APPLY_FAILED = '設定已儲存，但子行程尚未套用成功。請重新整理套用狀態，檢查後再重試啟動。';
const UNAVAILABLE = '管理狀態暫時無法使用。請檢查服務與受保護的設定儲存。';
const OUTCOME = '存檔結果不明時請重新啟動 add-on，之後到「連線與權杖」確認 MCP 網址：若這次換了後端身分，權杖可能已換新，舊網址會失效。';
const NEW_ORIGIN = '網址改到另一台伺服器（scheme、主機或 port 不同）時，不會沿用已儲存的密碼或金鑰：請在同一次儲存中為新網址重新輸入（選填的可以明確清除）。這次未儲存任何變更。';
const ODOO_EDIT = {contract: 'woow-connection-patch-v1', values: {url: 'https://odoo.invalid', database: 'DUMMY-db', username: 'DUMMY-user'},
  withheld_fields: [], secret_set: {password: true}};
// The double with a product's bootstrap and one answer for its saves (backend, backend/patch, policy).
function saving(product, save, options = {}) {
  return server({...options, answer: {
    '/api/bootstrap': (_options, named) => Response.json({product, base_path: mount, api_base: `${mount}/api`, csrf: 'synthetic_csrf_value',
      configuration: {revision: revisionOf(named.profile?.id ?? DEFAULT_PROFILE)}, operation_contract: {version: 1, server_time_ms: 1793318400000}, ...named}),
    '/api/backend/patch': save, '/api/backend': save, '/api/policy': save}});
}
const usernameChange = {changes: {username: 'DUMMY-user-two'}};
// HM-12 review S-5: server text an answer may carry; the panel never shows it.
const CANARY = 'PRIVATE_CANARY_MUST_NOT_RENDER';

test('HM-12: a save that rotated the token says token_rotated (200): passed on with its echo checked, never a token', async () => {
  const etag = `"c1-${'c'.repeat(64)}"`;
  const rotated = (_options, named) => Response.json({saved: true, token_rotated: true, configuration: {revision: etag.slice(1, -1)}, ...named}, {headers: {ETag: etag}});
  const {fetcher, calls} = saving('odoo', rotated);
  const api = new AdminApi(mount, fetcher, memoryStorage());
  await api.bootstrap();
  api.select(B);
  const result = await api.mutate('backend/patch', usernameChange, revisionOf(B), B);
  assert.deepEqual([result.saved, result.token_rotated, result.token], [true, true, undefined]);
  assert.equal(header(calls.at(-1)), B);
  assert.equal(panelApi.TOKEN_ROTATED, ROTATED);
  // The flag never stands for the echo (I12): an answer for another profile is not used.
  const other = new AdminApi(mount, saving('odoo', rotated, {echo: (operation, id) => operation === 'backend/patch' ? DEFAULT_PROFILE : id}).fetcher, memoryStorage());
  await other.bootstrap();
  other.select(B);
  await assert.rejects(() => other.mutate('backend/patch', usernameChange, revisionOf(B), B), ProfileEchoError);
});

test('HM-12: shape D with token_rotated (saved, the new child not started) is config_apply_failed that also says the token changed; only that shape', async () => {
  const shapeD = (_options, named) => Response.json({saved: true, token_rotated: true, message: CANARY, detail: {code: 'config_apply_failed', message: CANARY},
    configuration: {}, ...named}, {status: 503});
  const api = new AdminApi(mount, saving('odoo', shapeD).fetcher, memoryStorage());
  await api.bootstrap();
  await assert.rejects(() => api.mutate('backend/patch', usernameChange, revisionOf(DEFAULT_PROFILE)), error => error instanceof ApiError
    && error.status === 503 && error.code === 'config_apply_failed' && error.tokenRotated === true && error.message === `${APPLY_FAILED} ${ROTATED}`
    && !error.message.includes(CANARY));
  // Said of another profile than the one asked (I12): nothing of it is taken, today's copy (an error's echo decides
  // nothing else; this one would say whose token changed).
  const elsewhere = new AdminApi(mount, saving('odoo', shapeD, {echo: (operation, id) => operation === 'backend/patch' ? DEFAULT_PROFILE : id}).fetcher, memoryStorage());
  await elsewhere.bootstrap();
  elsewhere.select(B);
  await assert.rejects(() => elsewhere.mutate('backend/patch', usernameChange, revisionOf(B), B),
    error => error instanceof ApiError && error.code === 'config_apply_failed' && error.tokenRotated !== true && error.message === APPLY_FAILED);
  // Anything else is today's answer: no flag, today's copy.
  for (const [status, body] of [[503, {saved: true, detail: {code: 'config_apply_failed'}}], [503, {saved: true, token_rotated: 'true', detail: {code: 'config_apply_failed'}}],
    [503, {token_rotated: true, detail: {code: 'config_apply_failed'}}], [409, {saved: true, token_rotated: true, detail: {code: 'config_conflict'}}],
    [500, {saved: true, token_rotated: true, detail: {code: 'config_apply_failed'}}]]) {
    const other = new AdminApi(mount, saving('odoo', (_options, named) => Response.json({...body, ...named}, {status})).fetcher, memoryStorage());
    await other.bootstrap();
    await assert.rejects(() => other.mutate('backend/patch', usernameChange, revisionOf(DEFAULT_PROFILE)),
      error => error instanceof ApiError && error.status === status && error.tokenRotated !== true && !error.message.includes('權杖已換新'), JSON.stringify(body));
  }
});

test('HM-12 (DQ-40 ⑨): the new-origin 422 has fixed copy and shows nothing of the request or the answer; the answer has no echo', async () => {
  const typed = 'https://elsewhere.odoo.invalid';
  const refusal = status => () => Response.json({error: 'request denied', detail: {code: 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN'},
    untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER', url: typed}, {status});
  for (const switched of [true, false]) {
    const api = new AdminApi(mount, saving('odoo', refusal(422), {switched}).fetcher, memoryStorage());
    await api.bootstrap();
    await assert.rejects(() => api.mutate('backend/patch', {changes: {url: typed}}, revisionOf(DEFAULT_PROFILE)), error => error instanceof ApiError
      && !(error instanceof ProfileEchoError) && error.status === 422 && error.code === 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN'
      && error.message === NEW_ORIGIN && !error.message.includes('elsewhere') && !error.message.includes('CANARY'));
  }
  // The code only with its documented status (contract 4.1): another status keeps that status' text.
  const other = new AdminApi(mount, saving('odoo', refusal(400)).fetcher, memoryStorage());
  await other.bootstrap();
  await assert.rejects(() => other.mutate('backend/patch', {changes: {url: typed}}, revisionOf(DEFAULT_PROFILE)),
    error => error.status === 400 && error.code === null && error.message === '設定格式不符。伺服器未確認儲存，請檢查欄位。');
});

test('HM-12 review S-7: a backend save of a switched-on Odoo answered 503 state unavailable adds the restart hint; request denied and everything else keep today\'s text', async () => {
  const run = async (body, {switched = true, operation = 'backend/patch', product = 'odoo'} = {}) => {
    const api = new AdminApi(mount, saving(product, () => Response.json(body, {status: 503}), {switched}).fetcher, memoryStorage());
    await api.bootstrap();
    const payload = operation === 'policy' ? {writes_enabled: false, disabled: [], enabled_write_tools: []} : operation === 'backend' ? {connection: null} : usernameChange;
    let caught = null;
    try { await api.mutate(operation, payload, revisionOf(DEFAULT_PROFILE)); } catch (error) { caught = error; }
    assert.ok(caught instanceof ApiError && caught.status === 503 && caught.code === null && caught.tokenRotated !== true);
    return caught.message;
  };
  const denied = {error: 'request denied'}, unavailable = {error: 'state unavailable'};
  assert.equal(await run(denied), UNAVAILABLE);                      // the old child did not stop: nothing was saved
  assert.equal(await run(unavailable), `${UNAVAILABLE} ${OUTCOME}`);  // nothing saved, or saved: unknown
  assert.equal(await run(unavailable, {operation: 'backend'}), `${UNAVAILABLE} ${OUTCOME}`);
  // Switched off (bit for bit), another operation, a product whose token is not bound to its backend: today's text.
  assert.equal(await run(unavailable, {switched: false}), UNAVAILABLE);
  assert.equal(await run(unavailable, {operation: 'policy'}), UNAVAILABLE);
  assert.equal(await run(unavailable, {product: 'emqx'}), UNAVAILABLE);
  // HM-22: Nextcloud's token is bound to its url and username too: the same hint, its switched-off save today's text.
  assert.equal(await run(unavailable, {product: 'nextcloud'}), `${UNAVAILABLE} ${OUTCOME}`);
  assert.equal(await run(unavailable, {product: 'nextcloud', switched: false}), UNAVAILABLE);
  assert.equal(await run(denied, {switched: false}), UNAVAILABLE);
});

// HM-22 review MF-1: a backend save of a profile whose restore review waits, refused because it would rotate the token
// (HM-13c review S-3), names the identity fields of the save's own product: Odoo's copy as HM-13c wrote it, a
// switched-on Nextcloud's url and username; every product of identityBound has its words (contracts.js identityChange).
test('HM-22 review MF-1: the review-wait copy of a backend save names the identity fields of the save\'s own product', async () => {
  const {identityBound, identityChange} = panelContracts;
  assert.deepEqual(Object.keys(identityChange ?? {}).sort(), [...identityBound].sort());
  const WAITS = '這個帳號是從備份還原（或休眠）回來的，還沒有核對：請先到預設帳號頁的核對卡確認它的設定，按「已核對」後才能重新產生權杖。';
  const saveWaits = names => `改後端身分（${names}）會換新這個帳號的 MCP 權杖，所以也要先核對才能儲存；這次未儲存任何變更。`;
  const held = () => Response.json({error: 'request denied', detail: {code: 'restore_review_required'}}, {status: 409});
  const run = async (product, {switched = true, operation = 'backend/patch'} = {}) => {
    const api = new AdminApi(mount, saving(product, held, {switched}).fetcher, memoryStorage());
    await api.bootstrap();
    const payload = operation === 'policy' ? {writes_enabled: false, disabled: [], enabled_write_tools: []}
      : operation === 'backend' ? {connection: null} : usernameChange;
    let caught = null;
    try { await api.mutate(operation, payload, revisionOf(DEFAULT_PROFILE)); } catch (error) { caught = error; }
    assert.ok(caught instanceof ApiError && caught.status === 409 && caught.code === 'restore_review_required');
    return caught.message;
  };
  assert.equal(await run('odoo'), `${WAITS} ${saveWaits('Odoo 的網址、資料庫或使用者')}`);  // HM-13c's words, unchanged
  assert.equal(await run('nextcloud'), `${WAITS} ${saveWaits('Nextcloud 的網址或使用者')}`);
  assert.equal(await run('nextcloud', {operation: 'backend'}), `${WAITS} ${saveWaits('Nextcloud 的網址或使用者')}`);
  // Another operation, a Nextcloud not switched on (no profile: today's panel), a product whose token is not bound to
  // its backend: the review copy alone.
  assert.equal(await run('nextcloud', {operation: 'policy'}), WAITS);
  assert.equal(await run('nextcloud', {switched: false}), WAITS);
  assert.equal(await run('emqx'), WAITS);
});

test('HM-12 (DQ-40 ⑨): every backend URL names the secrets it takes to its server, every secret of a product exactly once', () => {
  const {urlSecrets, identityBound, products} = panelContracts;
  assert.deepEqual(Object.keys(urlSecrets ?? {}).sort(), Object.keys(products).sort());
  for (const [product, table] of Object.entries(urlSecrets)) {
    const fields = products[product].fields;
    assert.deepEqual(Object.keys(table), fields.filter(([, , type]) => type.includes('url')).map(([key]) => key), product);
    const carried = Object.values(table).flat();
    assert.equal(new Set(carried).size, carried.length, product);
    assert.deepEqual([...carried].sort(), fields.filter(([, , type]) => type.includes('secret')).map(([key]) => key).sort(), product);
  }
  assert.deepEqual(urlSecrets.hermes, {gateway_url: ['gateway_api_key'], dashboard_url: ['dashboard_password']});
  assert.deepEqual(urlSecrets.n8n, {url: ['key', 'mcp_access_token']});
  assert.deepEqual(urlSecrets.opendesign, {url: []});
  assert.deepEqual(identityBound, ['odoo', 'nextcloud']);  // HM-22: Nextcloud's url and username
});

test('HM-12: a URL\'s origin is the server\'s (backend_edit.origin): scheme and host in lower case, the effective port, nothing else normalized', () => {
  const origin = panelContracts.urlOrigin;
  assert.equal(typeof origin, 'function');
  assert.deepEqual(origin('https://odoo.invalid'), ['https', 'odoo.invalid', 443]);
  assert.deepEqual(origin('HTTP://Odoo.Invalid:80/x/y'), ['http', 'odoo.invalid', 80]);
  assert.deepEqual(origin('http://odoo.invalid:0443'), ['http', 'odoo.invalid', 443]);
  assert.deepEqual(origin('http://odoo.invalid:'), ['http', 'odoo.invalid', 80]);
  assert.deepEqual(origin('http://[2001:DB8::1]:8080/p'), ['http', '2001:db8::1', 8080]);
  assert.deepEqual(origin('https://odoo.invalid.'), ['https', 'odoo.invalid.', 443]);   // the trailing dot stays: the safe direction
  assert.deepEqual(origin('http://0x7f.1'), ['http', '0x7f.1', 80]);                     // so does another IPv4 notation
  for (const value of ['http://odoo.invalid:x', 'http://odoo.invalid:99999', 'http://', 'odoo.invalid', null]) assert.equal(origin(value), null, String(value));
});

test('HM-12 (DQ-40 ⑨): switched on, a URL moved to another origin needs its stored secrets again before anything is sent; switched off as before', () => {
  const {backendPatchPayload, newOriginSecrets} = panelContracts;
  assert.equal(typeof newOriginSecrets, 'function');
  const odoo = {product: 'odoo', connection_configured: true, backend_edit: ODOO_EDIT};
  const keep = {url: 'keep', database: 'keep', username: 'keep', password: 'keep'};
  const moved = {...keep, url: 'set'}, elsewhere = {url: 'https://elsewhere.invalid'};
  // Switched off: today's partial edit (the stored password goes to the new place, by the administrator's choice).
  assert.deepEqual(backendPatchPayload(odoo, moved, elsewhere), {changes: elsewhere});
  assert.deepEqual(backendPatchPayload(odoo, moved, elsewhere, false), {changes: elsewhere});
  // Switched on: refused here until the password is typed again; the message names the field, never the typed URL.
  assert.deepEqual(newOriginSecrets(odoo, moved, elsewhere), ['password']);
  assert.throws(() => backendPatchPayload(odoo, moved, elsewhere, true), error => error instanceof UiError
    && error.message === '網址改到另一台伺服器時不會沿用已儲存的憑證：請重新輸入密碼或 API Key。');
  assert.deepEqual(backendPatchPayload(odoo, {...moved, password: 'set'}, {...elsewhere, password: 'DUMMY-new'}, true), {changes: {...elsewhere, password: 'DUMMY-new'}});
  // Another scheme, port or spelling of the host is another origin; another path, case or the default port written out is not.
  for (const url of ['http://odoo.invalid', 'https://odoo.invalid:8443', 'https://odoo.invalid.']) assert.deepEqual(newOriginSecrets(odoo, moved, {url}), ['password'], url);
  for (const url of ['https://odoo.invalid/odoo', 'HTTPS://ODOO.INVALID', 'https://odoo.invalid:443/']) {
    assert.deepEqual(newOriginSecrets(odoo, moved, {url}), [], url);
    assert.deepEqual(backendPatchPayload(odoo, moved, {url}, true), {changes: {url: url.replace(/\/+$/, '')}}, url);
  }
  // Nothing to bring: the URL kept, not a URL yet, or the secret never stored.
  assert.deepEqual(newOriginSecrets(odoo, keep, elsewhere), []);
  assert.deepEqual(newOriginSecrets(odoo, moved, {url: 'not a url'}), []);
  assert.deepEqual(newOriginSecrets({...odoo, backend_edit: {...ODOO_EDIT, secret_set: {password: false}}}, moved, elsewhere), []);
  // A URL the server withholds (its stored value unknown here) counts as moved: the safe direction.
  const withheld = {...odoo, backend_edit: {...ODOO_EDIT, values: {...ODOO_EDIT.values, url: null}, withheld_fields: ['url']}};
  assert.deepEqual(newOriginSecrets(withheld, moved, {url: 'https://odoo.invalid/odoo'}), ['password']);
  // n8n: its API key and MCP access token both go to its one server; one never stored is not asked for, a cleared one is brought.
  const n8n = {product: 'n8n', connection_configured: true, backend_edit: {contract: 'woow-connection-patch-v1', values: {url: 'http://old.n8n.invalid'}, secret_set: {key: true, mcp_access_token: true}}};
  const n8nMoved = {url: 'set', key: 'keep', mcp_access_token: 'keep'}, n8nElsewhere = {url: 'http://new.n8n.invalid'};
  assert.deepEqual(newOriginSecrets(n8n, n8nMoved, n8nElsewhere), ['key', 'mcp_access_token']);
  assert.deepEqual(backendPatchPayload(n8n, {...n8nMoved, key: 'set', mcp_access_token: 'clear'}, {...n8nElsewhere, key: 'DUMMY-new-key'}, true),
    {changes: {url: 'http://new.n8n.invalid', key: 'DUMMY-new-key', mcp_access_token: null}});
  assert.throws(() => backendPatchPayload(n8n, {...n8nMoved, key: 'set'}, {...n8nElsewhere, key: 'DUMMY-new-key'}, true), /MCP Access Token.*或明確清除。$/);
  assert.deepEqual(newOriginSecrets({...n8n, backend_edit: {...n8n.backend_edit, secret_set: {key: true, mcp_access_token: false}}}, n8nMoved, n8nElsewhere), ['key']);
  // Hermes: each URL its own server's secret; a dashboard set for the first time brings nothing; OpenDesign sends none.
  const hermes = {product: 'hermes', connection_configured: true, backend_edit: {contract: 'woow-connection-patch-v1',
    values: {gateway_url: 'https://gw.invalid', dashboard_url: 'https://dash.invalid', dashboard_username: 'DUMMY-user'}, secret_set: {gateway_api_key: true, dashboard_password: true}}};
  const hermesKeep = {gateway_url: 'keep', gateway_api_key: 'keep', dashboard_url: 'keep', dashboard_username: 'keep', dashboard_password: 'keep'};
  assert.deepEqual(newOriginSecrets(hermes, {...hermesKeep, dashboard_url: 'set'}, {dashboard_url: 'https://other.invalid'}), ['dashboard_password']);
  assert.deepEqual(newOriginSecrets(hermes, {...hermesKeep, gateway_url: 'set'}, {gateway_url: 'https://other.invalid'}), ['gateway_api_key']);
  const firstDashboard = {...hermes, backend_edit: {...hermes.backend_edit, values: {...hermes.backend_edit.values, dashboard_url: null, dashboard_username: null},
    secret_set: {gateway_api_key: true, dashboard_password: false}}};
  assert.deepEqual(newOriginSecrets(firstDashboard, {...hermesKeep, dashboard_url: 'set'}, {dashboard_url: 'https://other.invalid'}), []);
  assert.deepEqual(newOriginSecrets({product: 'opendesign', connection_configured: true, backend_edit: {contract: 'woow-connection-patch-v1', values: {url: 'https://od.invalid'}, secret_set: {}}},
    {url: 'set'}, {url: 'https://other.invalid'}), []);
});
