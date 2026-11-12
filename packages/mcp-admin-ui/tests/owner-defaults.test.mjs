import test from 'node:test';
import assert from 'node:assert/strict';
import {AdminApi, ApiError} from '../src/api.js';
import {UiError, noticeTime, ownerDefaultsView} from '../src/contracts.js';

// The shape mcp_admin_core.owner_defaults.view returns (2026-10-27 one-time all-on migration).
const valid = () => ({
  decision: '2026-10-25', applied: 'migrated', at: '2026-10-27T03:04:05+00:00', from_schema: 3,
  restored_at: null, acknowledged_at: null, notice: true, recovery: 'available',
  upgrade: {enabled_tools: ['hermes_skill'], granted_writes: ['hermes_cron:pause'], cleared_operation_denies: [],
    new_tools: ['hermes_chat'], new_write_operations: ['hermes_chat'], writes_enabled: [false, true], changed: true},
  restore: {disabled_added: ['hermes_skill'], write_grants_removed: ['hermes_chat', 'hermes_cron:pause'],
    operation_denies_added: [], writes_enabled: [true, false], kept_new_tools: ['hermes_config'],
    policy_changed: true, available: true},
});

test('a server without the notice and a valid notice are accepted as they are', () => {
  assert.equal(ownerDefaultsView(undefined), null);
  assert.equal(ownerDefaultsView(null), null);
  assert.deepEqual(ownerDefaultsView(valid()), valid());
  assert.deepEqual(ownerDefaultsView({...valid(), recovery: 'missing', upgrade: null, restore: null}).recovery, 'missing');
});

test('malformed notices are refused, never half shown', () => {
  const broken = [
    {...valid(), applied: 'fresh_install'}, {...valid(), at: '2026-10-27 03:04:05'}, {...valid(), at: null},
    {...valid(), from_schema: 4}, {...valid(), from_schema: true}, {...valid(), restored_at: 'now'},
    {...valid(), notice: 'yes'}, {...valid(), recovery: 'unknown'}, {...valid(), upgrade: null},
    {...valid(), upgrade: {...valid().upgrade, new_tools: [1]}}, {...valid(), upgrade: {...valid().upgrade, writes_enabled: [true]}},
    {...valid(), restore: {...valid().restore, available: 'true'}}, {...valid(), restore: {...valid().restore, kept_new_tools: ''}},
    {...valid(), restore: {...valid().restore, write_grants_removed: undefined}},
    {...valid(), upgrade: {...valid().upgrade, enabled_tools: ['x'.repeat(301)]}}, [valid()], 'migrated',
  ];
  for (const value of broken) assert.throws(() => ownerDefaultsView(value), UiError);
});

test('times are shown as the server wrote them (UTC), independent of the browser time zone', () => {
  assert.equal(noticeTime('2026-10-27T03:04:05+00:00'), '2026-10-27 03:04（UTC）');
  assert.equal(noticeTime('2026-10-27T03:04:05+08:00'), '時間不明');
  assert.equal(noticeTime(null), '時間不明');
});

test('notice actions are body-less POSTs with CSRF and the reviewed If-Match; a missing revision sends nothing', async () => {
  const revision = 'c1-' + 'a'.repeat(64);
  const bootstrap = {product: 'hermes', base_path: '', api_base: '/api', csrf: 'synthetic_csrf_value'};
  const calls = [];
  const api = new AdminApi('', async (path, options) => {
    calls.push({path, options});
    return Response.json(path.endsWith('bootstrap') ? bootstrap : {saved: true, owner_defaults: valid()});
  });
  for (const action of ['restore', 'dismiss']) {
    await api.mutate(`owner-defaults/${action}`, undefined, revision);
    const sent = calls.at(-1);
    assert.equal(sent.path, `/api/owner-defaults/${action}`);
    assert.equal(sent.options.method, 'POST');
    assert.equal(sent.options.body, undefined);
    assert.equal(sent.options.headers['If-Match'], `"${revision}"`);
    assert.equal(sent.options.headers['X-CSRF-Token'], bootstrap.csrf);
  }
  const before = calls.length;
  await assert.rejects(() => api.mutate('owner-defaults/restore'), UiError);
  assert.equal(calls.filter(call => !call.path.endsWith('bootstrap')).length, before / 2);
});

test('an unconfirmed or refused notice action reports only fixed text', async () => {
  const revision = 'c1-' + 'a'.repeat(64);
  const bootstrap = {product: 'hermes', base_path: '', api_base: '/api', csrf: 'synthetic_csrf_value'};
  const unconfirmed = new AdminApi('', async path => Response.json(path.endsWith('bootstrap') ? bootstrap : {done: true}));
  await assert.rejects(() => unconfirmed.mutate('owner-defaults/dismiss', undefined, revision), UiError);
  const refused = new AdminApi('', async path => path.endsWith('bootstrap') ? Response.json(bootstrap)
    : Response.json({detail: {code: 'owner_defaults_unavailable'}, error: 'PRIVATE_CANARY'}, {status: 409}));
  await assert.rejects(() => refused.mutate('owner-defaults/restore', undefined, revision), error =>
    error instanceof ApiError && error.code === 'owner_defaults_unavailable' && /升級通知已處理過/.test(error.message)
    && !error.message.includes('PRIVATE_CANARY'));
});
