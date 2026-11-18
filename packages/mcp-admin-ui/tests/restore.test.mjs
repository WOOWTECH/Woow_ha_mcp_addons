// HM-13c (plan 6 還原與休眠核對卡; contract 3.1, 3.6, 4.1): what the panel reads about a restore, checked without a
// browser: the bootstrap's notices, the guard's record, the quarantine directories, "revoke all"'s results, the
// identities of the new profile operations and the export (never a token or a credential).
import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/api.js';
import { OperationIdentity, PROFILES_SCOPE } from '../src/operation-identity.js';
import { QUARANTINE_SHOWN, RecordError, dormantProfiles, exportDocument, exportEntry, policyLine, quarantineTime,
  quarantinedEntries, recordView, restoreNotice, restoreReview, revocationResults, tokenText, waitsForReview } from '../src/restore.js';

function memoryStorage() {
  const data = new Map();
  return {getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key)};
}

const B = '0123456789abcdef01234567';
const AT = '2026-11-16T09:30:15+00:00';
const fresh = {product: 'odoo', operation_contract: {version: 1, server_time_ms: 1_763_284_215_000}};
const indexRevision = 'p1-' + '1'.repeat(64);
const policy = {writes_enabled: true, disabled: ['a', 'b'], enabled_write_tools: ['w'], denied_operations: {t: ['x', 'y']},
  odoo_write_switches: {enable_writes: true, allow_direct_writes: false}, odoo_allowed_methods: null, n8n_session: null};
const record = (rows, extra = {}) => ({record: {version: 1, restore: {at: AT, marker: true, sentinel: 'mismatch'}, dormant: null,
  index: 'ok', profiles: rows, quarantined: [], profiles_directory: 'present', other_entries: 0, ...extra}});
const row = (id, extra = {}) => ({id, label: id === 'default' ? 'Default' : '會計', is_default: id === 'default', token: 'revoked',
  identity: {url: 'https://a.invalid', database: 'DUMMY-db', username: null}, policy, reviewed_at: null, ...extra});

test('the notices: a restore that kept the token, the profiles waiting for a review, the dormant ones', () => {
  assert.equal(restoreNotice({}), null);
  assert.deepEqual(restoreNotice({restore_notice: {at: AT}}), {at: AT});
  assert.deepEqual(restoreNotice({restore_notice: {at: '<script>'}}), {at: null});  // still shown, without a time
  assert.deepEqual(restoreNotice({restore_notice: 'yes'}), {at: null});
  assert.equal(restoreReview({}), null);
  assert.deepEqual(restoreReview({restore_review: {pending: 2, restore_at: AT, dormant_at: null}}), {pending: 2, restoreAt: AT, dormantAt: null});
  assert.deepEqual(restoreReview({restore_review: {pending: null, restore_at: null, dormant_at: null}}), {pending: null, restoreAt: null, dormantAt: null});
  assert.deepEqual(restoreReview({restore_review: {pending: -1, restore_at: 'x', dormant_at: AT}}), {pending: null, restoreAt: null, dormantAt: AT});
  assert.equal(dormantProfiles({dormant_profiles: 3}), 3);
  for (const value of [undefined, -1, 1.5, '3', null]) assert.equal(dormantProfiles({dormant_profiles: value}), null);
});

test('the record: rows as the guard writes them, a policy summary of whole numbers, anything else refused', () => {
  const view = recordView(record([row('default'), row(B, {reviewed_at: AT, token: 'already_revoked'})]));
  assert.equal(view.restoreAt, AT);
  assert.deepEqual(view.rows.map(item => [item.id, item.token, item.reviewedAt]), [['default', 'revoked', null], [B, 'already_revoked', AT]]);
  assert.deepEqual(view.rows[0].identity, [['url', 'https://a.invalid'], ['database', 'DUMMY-db'], ['username', null]]);
  assert.equal(policyLine(view.rows[0].policy), '舊版全域寫入：開、停用工具 2 個、逐項寫入授權 1 項、禁止的操作 2 項、Odoo 子操作開關開啟 1 項、Odoo 方法清單：沒有存過');
  assert.equal(waitsForReview(view.rows[0]), true);
  assert.equal(waitsForReview(view.rows[1]), false);
  assert.equal(waitsForReview({token: 'kept', reviewedAt: null}), false);
  assert.equal(tokenText('kept'), '權杖沒有撤銷（回到備份當時的值）');
  assert.equal(tokenText('<b>'), '權杖狀態不明');
  assert.equal(recordView({record: null}), null);
  const broken = [
    {}, {record: {version: 2}}, {record: null, extra: 1},
    record([row('default'), row('default')]), record([row('DEFAULT')]), record([row(B, {is_default: true})]),
    record([row(B, {token: 'active'})]), record([row(B, {reviewed_at: 'today'})]), record([row(B, {identity: {URL: 'x'}})]),
    record([row(B, {identity: {url: 5}})]), record([row(B, {policy: {disabled: 'all'}})]),
    record([row(B, {policy: {odoo_write_switches: {enable_writes: 'yes'}}})]), record([row(B)], {restore: {at: 'now'}}),
  ];
  for (const value of broken) assert.throws(() => recordView(value), RecordError, JSON.stringify(value).slice(0, 80));
});

test('the quarantine directories: a name and its id, the time from the name; anything else refuses the list', () => {
  const name = `${B}-20261116T093015Z`;
  assert.deepEqual(quarantinedEntries({}), []);
  assert.deepEqual(quarantinedEntries({quarantined: [{name, id: B}, {name: `${name}-2`, id: B}]}), [{name, id: B}, {name: `${name}-2`, id: B}]);
  assert.equal(quarantineTime(name), '2026-11-16 09:30（UTC）');
  assert.equal(quarantineTime('x'), '時間不明');
  for (const entries of [[{name, id: 'f'.repeat(24)}], [{name: `.quarantine-${name}`, id: B}], [{name, id: B, extra: 1}], [{name}],
    [{name, id: B}, {name, id: B}], 'all', [{name: `${B}-2026`, id: B}]]) {
    assert.throws(() => quarantinedEntries({quarantined: entries}), /帳號清單格式不符/, JSON.stringify(entries));
  }
  // HM-13c review S-5: never refused for their number (the panel shows QUARANTINE_SHOWN and says how many more).
  const many = Array.from({length: QUARANTINE_SHOWN + 6}, (_, n) => ({name: `${name}-${n + 2}`, id: B}));
  assert.deepEqual(quarantinedEntries({quarantined: many}), many);
  assert.equal(QUARANTINE_SHOWN, 64);
});

test('"revoke all" results: only the contract\'s ids and results; an unknown outcome keeps them in its error', () => {
  const results = [{id: 'default', result: 'revoked'}, {id: B, result: 'failed'}];
  assert.deepEqual(revocationResults(results), results);
  for (const value of [null, 'x', [{id: 'x', result: 'revoked'}], [{id: B, result: 'maybe'}], [{id: B, result: 'failed', why: 'x'}]]) {
    assert.equal(revocationResults(value), null);
  }
  const error = new ApiError(409, 'operation_outcome_unknown', null, {code: 'operation_outcome_unknown', results});
  assert.deepEqual(error.results, results);
  assert.equal(new ApiError(409, 'operation_outcome_unknown', null, {code: 'operation_outcome_unknown'}).results, null);
  assert.match(new ApiError(409, 'restore_review_required', null, {code: 'restore_review_required'}).message, /按「已核對」後才能重新產生權杖/);
  assert.match(new ApiError(410, 'operation_restored', null, {code: 'operation_restored'}).message, /備份還原之前送出的/);
});

test('the new profile operations keep an identity of their own shape, and a different one waits for it', () => {
  const identity = new OperationIdentity('/api/hassio_ingress/DUMMY', memoryStorage());
  const name = `${B}-20261116T093015Z`;
  for (const [route, detail, keys] of [['profiles/revoke-all', {}, 'id,product,revision,route'],
    ['profiles/restore-review', {profile: 'default'}, 'id,product,profile,revision,route'],
    ['profiles/restore-review', {profile: B}, 'id,product,profile,revision,route'],
    ['profiles/quarantine-delete', {name}, 'id,name,product,revision,route']]) {
    const started = identity.start(route, indexRevision, fresh, PROFILES_SCOPE, detail);
    assert.equal(Object.keys(started).sort().join(), keys);
    assert.deepEqual(identity.get(PROFILES_SCOPE), started);
    assert.deepEqual(identity.start(route, indexRevision, fresh, PROFILES_SCOPE, detail), started);  // the same request: kept
    assert.throws(() => identity.start('profiles/create', indexRevision, fresh, PROFILES_SCOPE, {label: '出納'}), /另一筆帳號操作尚未核對/);
    identity.clear(PROFILES_SCOPE);
  }
  for (const [route, detail] of [['profiles/restore-review', {profile: 'Default'}], ['profiles/quarantine-delete', {name: B}],
    ['profiles/quarantine-delete', {name: `.quarantine-${name}`}]]) {
    assert.throws(() => identity.start(route, indexRevision, fresh, PROFILES_SCOPE, detail), /帳號操作內容不符/);
  }
});

test('the export holds the list, the non-secret backend fields and the policy, never a token or a credential', () => {
  const bootstrap = {product: 'odoo', csrf: 'C'.repeat(64), token_masked: 'TTTT' + '*'.repeat(20) + 'TTTT', token_active: true,
    token_history: [{previous_token_masked: 'UUUU' + '*'.repeat(20) + 'UUUU'}], backend_key_set: true, connection_configured: true,
    backend_edit: {values: {url: 'https://a.invalid', database: 'DUMMY-db', username: 'DUMMY-user'}, secret_set: {password: true},
      withheld_fields: []}, ...policy, configuration: {revision: 'c1-' + 'a'.repeat(64)}, endpoint: 'https://mcp.invalid/mcp'};
  const entry = exportEntry({id: B, label: '會計', port: 18000}, bootstrap);
  assert.deepEqual(Object.keys(entry).sort(), ['connection', 'connection_configured', 'id', 'is_default', 'label', 'policy', 'port']);
  assert.deepEqual(entry.connection, {url: 'https://a.invalid', database: 'DUMMY-db', username: 'DUMMY-user'});
  assert.deepEqual(entry.policy, policy);
  const text = exportDocument('odoo', [entry], new Date('2026-11-16T09:30:15.123Z'));
  assert.equal(JSON.parse(text).exported_at, AT);
  for (const secret of ['CCCC', 'TTTT', 'UUUU', 'c1-', 'csrf', 'secret_set', 'password', 'endpoint']) assert.ok(!text.includes(secret), secret);
  assert.equal(exportEntry({id: B, label: null, hidden: true, port: 18000}, {}).label, null);
  const n8n = exportEntry({id: 'default', label: 'Default', port: 3000}, {product: 'n8n', backend_url: 'https://n8n.invalid', mcp_access_token_set: true});
  assert.deepEqual(n8n.connection, {backend_url: 'https://n8n.invalid'});
});
