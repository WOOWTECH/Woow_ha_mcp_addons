// HM-11 (plan 6, 10.3): the panel's profile rules without a browser. A small double of the management API as
// contract.md section 3 describes it; LOCAL MOCK only.
import test from 'node:test';
import assert from 'node:assert/strict';
import { AdminApi, ApiError, ProfileEchoError, StaleProfileError } from '../src/api.js';
import { OperationIdentity, PROFILES_SCOPE } from '../src/operation-identity.js';
import { DEFAULT_PROFILE, blockedNotice, clientName, disabledNotice, echoMatches, labelProblem, optionLabel, profileRows, shortId } from '../src/profiles.js';
import { clientExample, policyFingerprint, policyRestartNotice, UiError } from '../src/contracts.js';
import { createP9AdminClient } from '../../../packaging/ha_p9_admin.mjs';

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
  assert.equal(echoMatches({profile: {id: B, label: 'a\u202eb', is_default: false}, profiles_supported: true}, B, true), false);
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
    [row(DEFAULT_PROFILE, 'Default'), row(B, 'a\u202eb')], [row(DEFAULT_PROFILE, 'Default'), row(B, ' 前後 ')],
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
