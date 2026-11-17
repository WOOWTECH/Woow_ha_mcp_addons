// HM-27 (DQ-11 (a); contract 2.6, 3.1, 3.5, 4.1): the panel's calls for the add-on's one Origin policy of the secret
// path, without a browser. A small double of the management API as the contract describes it; LOCAL MOCK only.
// The panel reads and saves the policy only once the server serves profiles; it is a global path (no X-MCP-Profile, no
// echo); a save carries the CSRF value of a fresh default bootstrap, If-Match of the policy read, an Idempotency-Key kept
// for this tab under its own scope with the request itself, so a resend is the same request.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as panelApi from '../src/api.js';
import * as identity from '../src/operation-identity.js';
import { UiError } from '../src/contracts.js';

const { AdminApi, ApiError } = panelApi;
const mount = '/api/hassio_ingress/DUMMY';
const HEADER = 'X-MCP-Profile';
const etagOf = n => `"o1-${n.toString(16).padStart(64, '0')}"`;
const scopeKey = `woow-admin-operation-v1:${mount}:origin-policy`;
function memoryStorage() {
  const data = new Map();
  return { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key), data };
}

// The double: profiles on unless switched is false; the policy as the add-on keeps it; answer may replace the PUT's.
function server({ switched = true, answer = null } = {}) {
  const calls = [];
  const policy = { revision: 1, state: 'default', mode: 'report-only', allowed: ['https://claude.ai'] };
  const receipts = new Map();
  const view = () => ({ mode: policy.mode, allowed_origins: [...policy.allowed], origin_policy_state: policy.state });
  const fetcher = async (path, options = {}) => {
    const headers = options.headers ?? {};
    calls.push({ path, method: options.method ?? 'GET', headers, body: options.body });
    const local = path.slice(mount.length);
    if (local === '/api/origin-policy') {
      if (!switched) return new Response(null, { status: 404 });
      if ((options.method ?? 'GET') === 'GET') return Response.json(view(), { headers: { ETag: etagOf(policy.revision) } });
      if (answer) return answer(options, policy);
      const key = headers['Idempotency-Key'], sent = JSON.parse(options.body);
      if (receipts.has(key)) return Response.json({ ...view(), operation: { ...receipts.get(key), replayed: true } }, { headers: { ETag: etagOf(policy.revision) } });
      if (headers['If-Match'] !== etagOf(policy.revision)) return Response.json({ detail: { code: 'config_conflict' } }, { status: 409, headers: { ETag: etagOf(policy.revision) } });
      Object.assign(policy, { revision: policy.revision + 1, state: 'saved', mode: sent.mode, allowed: sent.allowed_origins.map(item => item.toLowerCase()) });
      receipts.set(key, { id: key, kind: 'origin.policy', state: 'completed', replayed: false });
      return Response.json({ ...view(), operation: receipts.get(key) }, { headers: { ETag: etagOf(policy.revision) } });
    }
    const profile = headers[HEADER];
    if (switched && profile === undefined) return Response.json({ error: 'request denied', detail: { code: 'profile_id_required' } }, { status: 400 });
    const named = switched ? { profile: { id: profile, label: 'Default', is_default: true }, profiles_supported: true } : {};
    if (local === '/api/bootstrap') return Response.json({ product: 'odoo', base_path: mount, api_base: `${mount}/api`, csrf: 'synthetic_csrf_value',
      configuration: { revision: 'c1-' + 'a'.repeat(64) }, operation_contract: { version: 1, server_time_ms: 1793318400000 }, ...named });
    return Response.json({ saved: true, ...(switched ? { profile: { id: profile } } : {}) });
  };
  return { fetcher, calls, policy };
}
async function opened(options) {
  const double = server(options);
  const storage = memoryStorage();
  const api = new AdminApi(mount, double.fetcher, storage);
  await api.open();
  return { ...double, api, storage };
}
const origin = call => call.path.endsWith('/api/origin-policy');

test('switched off: the panel never reads or saves the Origin policy (no such API there)', async () => {
  const { api, calls } = await opened({ switched: false });
  assert.equal(api.profile, null);
  await assert.rejects(() => api.originPolicy(), error => error instanceof UiError && !(error instanceof ApiError));
  await assert.rejects(() => api.saveOriginPolicy('enforce', [], 'o1-' + '1'.padStart(64, '0')), UiError);
  assert.equal(api.pendingOriginOperation(), null);
  assert.equal(calls.filter(origin).length, 0);
});

test('read: a global path (no X-MCP-Profile, no echo), its revision from the ETag', async () => {
  const { api, calls } = await opened();
  const policy = await api.originPolicy();
  assert.deepEqual(policy, { state: 'default', mode: 'report-only', origins: ['https://claude.ai'], revision: 'o1-' + '1'.padStart(64, '0') });
  const [read] = calls.filter(origin);
  assert.equal(read.method, 'GET');
  assert.equal(read.headers?.[HEADER], undefined);
});

test('read: an unusable file is shown as such; an answer of any other shape is not shown', async () => {
  for (const [body, expected] of [
    [{ mode: null, allowed_origins: null, origin_policy_state: 'unusable' }, { state: 'unusable', mode: null, origins: null }],
    [{ mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved' }, { state: 'saved', mode: 'enforce', origins: [] }],
  ]) {
    const api = new AdminApi(mount, async () => Response.json(body, { headers: { ETag: etagOf(7) } }), memoryStorage());
    api.profile = 'default'; api.connected = true;
    assert.deepEqual(await api.originPolicy(), { ...expected, revision: 'o1-' + '7'.padStart(64, '0') });
  }
  for (const body of [{ mode: 'Enforce', allowed_origins: [], origin_policy_state: 'saved' },
    { mode: 'enforce', allowed_origins: ['javascript:alert(1)'], origin_policy_state: 'saved' },
    { mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved', profile: { id: 'default' } },
    { mode: 'enforce', allowed_origins: null, origin_policy_state: 'saved' },
    { mode: null, allowed_origins: null, origin_policy_state: 'default' },
    { mode: 'report-only', allowed_origins: Array(17).fill('https://a.example'), origin_policy_state: 'saved' }]) {
    const api = new AdminApi(mount, async () => Response.json(body, { headers: { ETag: etagOf(7) } }), memoryStorage());
    api.profile = 'default'; api.connected = true;
    await assert.rejects(() => api.originPolicy(), UiError, JSON.stringify(body));
  }
  // A missing or malformed ETag: shown, but no revision to save with.
  const api = new AdminApi(mount, async () => Response.json({ mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved' }, { headers: { ETag: '"p1-' + '0'.repeat(64) + '"' } }), memoryStorage());
  api.profile = 'default'; api.connected = true;
  assert.equal((await api.originPolicy()).revision, null);
});

test('save: PUT with a fresh CSRF value, If-Match, an Idempotency-Key and the request; no profile header; receipt checked', async () => {
  const { api, calls, storage } = await opened();
  const { revision } = await api.originPolicy();
  const saved = await api.saveOriginPolicy('enforce', ['https://claude.ai', 'https://app.example'], revision);
  assert.deepEqual(saved, { state: 'saved', mode: 'enforce', origins: ['https://claude.ai', 'https://app.example'],
    revision: 'o1-' + '2'.padStart(64, '0'), replayed: false });
  const put = calls.filter(origin).find(call => call.method === 'PUT');
  assert.equal(put.headers[HEADER], undefined);
  assert.equal(put.headers['X-CSRF-Token'], 'synthetic_csrf_value');
  assert.equal(put.headers['If-Match'], etagOf(1));
  assert.match(put.headers['Idempotency-Key'], /^1793318400000\.[0-9a-f]{32}$/);
  assert.equal(put.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(put.body), { mode: 'enforce', allowed_origins: ['https://claude.ai', 'https://app.example'] });
  // The CSRF value came from the default profile's fresh bootstrap.
  const bootstrap = calls[calls.indexOf(put) - 1];
  assert.ok(bootstrap.path.endsWith('/api/bootstrap') && bootstrap.headers[HEADER] === 'default');
  assert.equal(storage.data.size, 0);  // completed: the identity is cleared
  assert.equal(api.pendingOriginOperation(), null);
});

test('save: what the panel can tell is wrong is never sent', async () => {
  const { api, calls } = await opened();
  const { revision } = await api.originPolicy();
  const before = calls.length;
  for (const [mode, origins] of [['Enforce', []], ['enforce', ['https://claude.ai/']], ['enforce', ['claude.ai']],
    ['enforce', ['https://claude.ai', 'HTTPS://CLAUDE.AI:443']], ['enforce', Array.from({ length: 17 }, (_, i) => `https://o${i}.example`)],
    ['enforce', ['https://a.example\nhttps://b.example']], ['enforce', ['https://user@a.example']], ['enforce', 'https://a.example']]) {
    await assert.rejects(() => api.saveOriginPolicy(mode, origins, revision), UiError);
  }
  await assert.rejects(() => api.saveOriginPolicy('enforce', [], 'p1-' + '0'.repeat(64)), UiError);
  assert.equal(calls.length, before);
});

test('originList: one per line, trimmed, blank lines dropped; a repeated or malformed origin refused without echoing it', () => {
  assert.deepEqual(panelApi.originList(' https://claude.ai \n\n http://localhost:6274\n'), ['https://claude.ai', 'http://localhost:6274']);
  assert.deepEqual(panelApi.originList(''), []);
  assert.deepEqual(panelApi.originList('https://[::1]:8443'), ['https://[::1]:8443']);
  for (const text of ['https://a.example\nHTTPS://A.EXAMPLE', 'https://a.example\nhttps://a.example:443', 'http://a.example\nhttp://A.example:80',
    '*', 'null', 'https://a.example/', 'https://a.example?x', 'https://a.example#x', 'https://u@a.example', 'ftp://a.example',
    'https://a b.example', Array.from({ length: 17 }, (_, i) => `https://o${i}.example`).join('\n')]) {
    assert.throws(() => panelApi.originList(text), error => error instanceof UiError && !error.message.includes('a.example'), text);
  }
  assert.equal(panelApi.MAX_ORIGINS, 16);
  assert.deepEqual([...panelApi.ORIGIN_MODES], ['report-only', 'enforce']);
  assert.deepEqual([...panelApi.DEFAULT_ORIGINS], ['https://claude.ai']);
});

test('a lost answer keeps the identity with the request; a resend is the same request; the receipt completes it', async () => {
  const double = server();
  let lose = true;
  const fetcher = async (path, options) => {
    const answer = await double.fetcher(path, options);
    if (lose && path.endsWith('/api/origin-policy') && options.method === 'PUT') { lose = false; throw new TypeError('synthetic: connection lost'); }
    return answer;
  };
  const storage = memoryStorage();
  const api = new AdminApi(mount, fetcher, storage);
  await api.open();
  const { revision } = await api.originPolicy();
  await assert.rejects(() => api.saveOriginPolicy('enforce', ['https://claude.ai'], revision), UiError);
  const pending = api.pendingOriginOperation();
  assert.deepEqual(Object.keys(pending).sort(), ['allowed_origins', 'id', 'mode', 'product', 'revision', 'route']);
  assert.deepEqual([pending.route, pending.mode, pending.allowed_origins, pending.revision, pending.product],
    ['origin-policy', 'enforce', ['https://claude.ai'], revision, 'odoo']);
  assert.ok(storage.data.has(scopeKey));
  // Another save while one is unconfirmed: refused, nothing sent.
  const before = double.calls.length;
  await assert.rejects(() => api.saveOriginPolicy('report-only', [], revision), /尚未確認結果/);
  assert.equal(double.calls.filter(origin).length, double.calls.slice(0, before).filter(origin).length);
  const resent = await api.retryOriginOperation();
  assert.equal(resent.replayed, true);
  const puts = double.calls.filter(call => origin(call) && call.method === 'PUT');
  assert.equal(puts.length, 2);
  assert.equal(puts[1].headers['Idempotency-Key'], puts[0].headers['Idempotency-Key']);
  assert.equal(puts[1].headers['If-Match'], puts[0].headers['If-Match']);
  assert.equal(puts[1].body, puts[0].body);
  assert.equal(api.pendingOriginOperation(), null);
});

test('a refusal before the intent releases the identity; one after it keeps it', async () => {
  for (const [status, code, kept] of [[409, 'config_conflict', false], [428, 'config_revision_required', false],
    [428, 'operation_id_required', false], [400, 'operation_id_invalid', false], [422, 'origin_policy_invalid', false],
    [409, 'operation_outcome_unknown', true], [503, 'operation_journal_unavailable', true]]) {
    const { api } = await opened({ answer: () => Response.json({ error: 'request denied', detail: { code } }, { status }) });
    const { revision } = await api.originPolicy();
    await assert.rejects(() => api.saveOriginPolicy('enforce', ['https://claude.ai'], revision),
      error => error instanceof ApiError && error.code === code);
    assert.equal(api.pendingOriginOperation() !== null, kept, code);
  }
});

test('origin_policy_invalid has fixed copy and only with 422; nothing of the answer is shown', async () => {
  const { api } = await opened({ answer: () => Response.json({ error: 'request denied', detail: { code: 'origin_policy_invalid' }, untrusted: 'PRIVATE_CANARY' }, { status: 422 }) });
  const { revision } = await api.originPolicy();
  await assert.rejects(() => api.saveOriginPolicy('enforce', ['https://claude.ai'], revision), error =>
    error.code === 'origin_policy_invalid' && error.message.includes('來源檢查設定不符合規則') && !error.message.includes('PRIVATE_CANARY'));
  const other = await opened({ answer: () => Response.json({ error: 'request denied', detail: { code: 'origin_policy_invalid' } }, { status: 409 }) });
  const otherRevision = (await other.api.originPolicy()).revision;
  await assert.rejects(() => other.api.saveOriginPolicy('enforce', [], otherRevision), error => error.code === null);
});

test('a save answer that is not a completed receipt of this request, or not a saved policy, is not confirmed', async () => {
  for (const answer of [
    (options) => Response.json({ mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved', operation: { id: options.headers['Idempotency-Key'], kind: 'origin.policy', state: 'unknown', replayed: false } }),
    (options) => Response.json({ mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved', operation: { id: options.headers['Idempotency-Key'], kind: 'profile.create', state: 'completed', replayed: false } }),
    (options) => Response.json({ mode: 'enforce', allowed_origins: [], origin_policy_state: 'default', operation: { id: options.headers['Idempotency-Key'], kind: 'origin.policy', state: 'completed', replayed: false } }),
    () => Response.json({ mode: 'enforce', allowed_origins: [], origin_policy_state: 'saved' }),
  ]) {
    const { api } = await opened({ answer });
    const { revision } = await api.originPolicy();
    await assert.rejects(() => api.saveOriginPolicy('enforce', [], revision), UiError);
    assert.notEqual(api.pendingOriginOperation(), null);  // kept: the outcome is not confirmed
  }
});

test('the identity record: its own key and exactly the request; another scope never reads it', () => {
  const storage = memoryStorage();
  const ids = new identity.OperationIdentity(mount, storage);
  const fresh = { product: 'odoo', operation_contract: { version: 1, server_time_ms: 1793318400000 } };
  const record = ids.start('origin-policy', 'o1-' + '1'.padStart(64, '0'), fresh, identity.ORIGIN_SCOPE, { mode: 'enforce', allowed_origins: ['https://claude.ai'] });
  assert.deepEqual(Object.keys(record).sort(), ['allowed_origins', 'id', 'mode', 'product', 'revision', 'route']);
  assert.deepEqual([...storage.data.keys()], [scopeKey]);
  assert.deepEqual(ids.get(identity.ORIGIN_SCOPE), record);
  assert.equal(ids.get(), null);
  assert.equal(ids.get(identity.PROFILES_SCOPE), null);
  for (const wrong of [{ ...record, mode: 'Enforce' }, { ...record, revision: 'p1-' + '1'.repeat(64) }, { ...record, extra: 1 },
    { ...record, route: 'profiles/create' }, { ...record, allowed_origins: 'https://claude.ai' }]) {
    storage.setItem(scopeKey, JSON.stringify(wrong));
    assert.throws(() => ids.get(identity.ORIGIN_SCOPE), UiError);
  }
  storage.removeItem(scopeKey);
  assert.throws(() => ids.start('origin-policy', 'c1-' + 'a'.repeat(64), fresh, identity.ORIGIN_SCOPE, { mode: 'enforce', allowed_origins: [] }), UiError);
  assert.throws(() => ids.start('token/rotate', 'o1-' + '1'.padStart(64, '0'), fresh, identity.ORIGIN_SCOPE, { mode: 'enforce', allowed_origins: [] }), UiError);
  assert.deepEqual(identity.operationReceipt({ id: record.id, kind: 'origin.policy', state: 'completed', replayed: false }, record).kind, 'origin.policy');
});
