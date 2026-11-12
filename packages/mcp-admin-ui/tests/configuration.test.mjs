import test from 'node:test';
import assert from 'node:assert/strict';
import {AdminApi, ApiError} from '../src/api.js';

const revision = 'c1-' + 'a'.repeat(64);
const fresh = 'c1-' + 'b'.repeat(64);
const bootstrap = {product: 'n8n', base_path: '', api_base: '/api', csrf: 'synthetic_csrf_value', configuration: {revision: fresh}};

test('fresh CSRF cannot silently advance an open form revision', async () => {
  const calls = [];
  const api = new AdminApi('', async (path, options) => {
    calls.push({path, options});
    return Response.json(path.endsWith('bootstrap') ? bootstrap : {saved: true});
  });
  await api.mutate('endpoint', {endpoint: null}, revision);
  assert.equal(calls[1].options.headers['If-Match'], `"${revision}"`);
  assert.equal(calls[1].options.headers['X-CSRF-Token'], bootstrap.csrf);
});

test('conflict and partial application errors use only fixed safe codes; never replay', async () => {
  for (const [status, code, copy] of [[409, 'config_conflict', /草稿已保留/], [503, 'config_apply_failed', /設定已儲存/]]) {
    let mutations = 0;
    const api = new AdminApi('', async path => {
      if (path.endsWith('bootstrap')) return Response.json(bootstrap);
      mutations++;
      return Response.json({saved: true, detail: {code}, error: 'PRIVATE_CANARY'}, {status});
    });
    await assert.rejects(() => api.mutate('backend', {url: null, key: null}, revision), error =>
      error instanceof ApiError && error.code === code && copy.test(error.message) && !error.message.includes('PRIVATE_CANARY'));
    assert.equal(mutations, 1);
  }
});
