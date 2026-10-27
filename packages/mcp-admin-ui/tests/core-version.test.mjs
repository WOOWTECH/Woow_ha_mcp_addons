import test from 'node:test';
import assert from 'node:assert/strict';
import {AdminApi, ApiError} from '../src/api.js';

// The management server answers 403 {detail: {code: 'core_version_unreviewed', ha_version}} when HA Core advertises a
// version this add-on release has not reviewed (mcp_admin_core.admin_auth.denial_detail).
const denied = (status, detail) => async () => Response.json({error: 'request denied', detail, untrusted: 'PRIVATE_CANARY'}, {status});

test('an unreviewed HA Core version is named in the denial; nothing else from the body is shown', async () => {
  for (const version of ['2026.11.0', '2026.10.5', '2026.11.0b1', '2026.11.0.dev20261027']) {
    const api = new AdminApi('', denied(403, {code: 'core_version_unreviewed', ha_version: version}));
    await assert.rejects(() => api.bootstrap(), error => error instanceof ApiError && error.status === 403
      && error.code === 'core_version_unreviewed' && error.haVersion === version
      && error.message.startsWith(`這個 HA Core 版本尚未審核：${version}。`) && error.message.includes('MCP 端點')
      && !error.message.includes('PRIVATE_CANARY'));
  }
});

test('a version outside the Core release form is never echoed', async () => {
  for (const version of ['<img src=x onerror=1>', '2026.11', ' 2026.11.0', 'x'.repeat(300), 2026, null]) {
    const api = new AdminApi('', denied(403, {code: 'core_version_unreviewed', ha_version: version}));
    await assert.rejects(() => api.bootstrap(), error => error instanceof ApiError && error.code === 'core_version_unreviewed'
      && error.haVersion === null && error.message.includes('版本字串無法辨識')
      && (typeof version !== 'string' || !error.message.includes(version.trim())));
  }
});

test('the reason counts only on a 403; other statuses keep their fixed copy', async () => {
  for (const status of [400, 409, 503]) {
    const api = new AdminApi('', denied(status, {code: 'core_version_unreviewed', ha_version: '2026.11.0'}));
    await assert.rejects(() => api.bootstrap(), error => error instanceof ApiError && error.status === status
      && error.code === null && !error.message.includes('2026.11.0'));
  }
  const plain = new AdminApi('', async () => Response.json({error: 'request denied'}, {status: 403}));
  await assert.rejects(() => plain.bootstrap(), error => error instanceof ApiError && error.code === null
    && error.message.includes('你沒有管理權限'));
});
