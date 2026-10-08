import test from 'node:test';
import assert from 'node:assert/strict';
import { products, mountPath, explicitUrl, backendPayload, policyPayload, toolRows, clientExample } from '../src/contracts.js';
import { AdminApi, ApiError } from '../src/api.js';
const base = '/api/hassio_ingress/DUMMY';
const bootstrap = () => ({ base_path: base, api_base: `${base}/api`, product: 'n8n', csrf: 'fresh_csrf_for_mock_only', tools: {} });
const response = value => new Response(JSON.stringify(value), { status: 200 });

test('MOCK mount path fails closed, including protocol-relative and template values', () => {
  for (const bad of ['//evil.test', '/ok/../bad', '/foo%2fbar', '/foo?token=x', '__MCP_UI_BASE__', null, '/trailing/']) assert.throws(() => mountPath(bad));
  assert.equal(mountPath(base), base);
  assert.equal(mountPath(''), '');
});
test('URLs reject credentials/query/fragment, preserve explicit client endpoint', () => {
  for (const bad of ['https://u:p@example.test/mcp', 'https://example.test/mcp?token=x', 'https://example.test/mcp#x', 'javascript:alert(1)', 'https://example.test/mcp?', ' https://example.test/mcp']) assert.throws(() => explicitUrl(bad, true));
  assert.equal(explicitUrl('http://192.0.2.4:8081/mcp/', true), 'http://192.0.2.4:8081/mcp');
  assert.throws(() => explicitUrl('https://example.test/api', true));
});
test('eight typed product payloads; no invented OpenDesign token, preserve means no request', () => {
  assert.equal(Object.keys(products).length, 8);
  for (const [product, spec] of Object.entries(products)) {
    const filler = product === 'nextcloud' ? 'fixture value' : ' fixture value ';  // Nextcloud refuses padded values
    const values = Object.fromEntries(spec.fields.map(([key, , type]) => [key, type.startsWith('optional') ? '' : type === 'mode' ? 'read' : type === 'url' ? 'https://backend.example.test' : filler]));
    const payload = backendPayload(product, 'replace', values);
    const connection = product === 'n8n' ? payload : payload.connection;
    assert.deepEqual(Object.keys(connection), spec.fields.map(([key]) => key));
    for (const [key, , type] of spec.fields) if (type === 'secret') assert.equal(connection[key], filler);
    assert.equal(backendPayload(product, 'preserve', {}), null);
    assert.deepEqual(backendPayload(product, 'clear', {}), product === 'n8n' ? { url: null, key: null } : { connection: null });
  }
  assert.deepEqual(backendPayload('opendesign', 'replace', { url: 'https://design.example.test' }), { connection: { url: 'https://design.example.test' } });
});
test('typed replacement refuses blank secrets, partial dashboard, malformed credentials and API suffix', () => {
  assert.throws(() => backendPayload('n8n', 'replace', { url: 'https://n8n.example.test', key: '' }));
  assert.throws(() => backendPayload('n8n', 'replace', { url: 'https://n8n.example.test', key: 'bad\nkey' }));
  assert.throws(() => backendPayload('hermes', 'replace', { gateway_url: 'https://hermes.example.test', gateway_api_key: 'fixture', dashboard_url: 'https://dashboard.example.test' }));
  assert.throws(() => backendPayload('emqx', 'replace', { url: 'https://broker.example.test/api/v5', api_key: 'fixture', api_secret: 'fixture' }));
  for (const [username, app_password] of [['   ', 'fixture'], [' tester', 'fixture'], ['tester ', 'fixture'], ['tester', '   '], ['tester', ' fixture'], ['tester', 'fixture ']]) {
    assert.throws(() => backendPayload('nextcloud', 'replace', { url: 'https://cloud.example.test', username, app_password }), /不可空白/);
  }
  assert.throws(() => backendPayload('nextcloud', 'replace', { url: 'https://雲端.example.tw', username: 'tester', app_password: 'fixture' }),
    /xn-- 形式：https:\/\/xn--suzq78c\.example\.tw$/);
  assert.throws(() => backendPayload('nextcloud', 'replace', { url: 'https://cloud.台灣:8443/nc', username: 'tester', app_password: 'fixture' }),
    /xn--.*:8443\/nc$/);
  for (const url of ['https://xn--suzq78c.example.tw', 'https://Cloud.Example.test:8443/nc', 'http://192.0.2.4/nc', 'https://[2001:DB8:0::1]:8443'])
    assert.equal(backendPayload('nextcloud', 'replace', { url, username: 'tester', app_password: 'fixture' }).connection.url, url);
  assert.deepEqual(backendPayload('nextcloud', 'replace', { url: 'https://cloud.example.test/', username: 'tester', app_password: 'fix ture' }),
    { connection: { url: 'https://cloud.example.test', username: 'tester', app_password: 'fix ture' } });
});
test('unknown policy contract cannot save hidden grants; v3 is explicit/data driven', () => {
  const old = { tools: { read_one: { write: false }, write_one: { write: true }, mixed: { write: false, write_operations: ['create', 'delete'] }, unknown: {} } };
  assert.equal(toolRows(old).length, 4);
  assert.throws(() => policyPayload(old, [], []));
  assert.throws(() => policyPayload(old, [], [{ tool: 'write_one', operation: null }]));
  const next = { policy_contract: 'woow-v3-exact-grants', disabled: [], writes_enabled: false, enabled_write_tools: [], tools: Object.fromEntries(Object.entries(old.tools).filter(([n]) => n !== 'unknown').map(([n,t]) => [n,{write:t.write,legacy_write:false,operation_parameter:t.write_operations?'action':null,write_grants:t.write?[n]:(t.write_operations??[]).map(o=>`${n}:${o}`),inputSchema:{}}])) };
  assert.deepEqual(policyPayload(next, ['read_one'], [{ tool: 'write_one', operation: null }, { tool: 'mixed', operation: 'create' }]), { writes_enabled:false, disabled: ['read_one'], enabled_write_tools:['write_one','mixed:create'] });
  for (const grant of [{ tool: 'unknown', operation: null }, { tool: 'mixed', operation: 'shell' }, { tool: 'read_one', operation: null }]) assert.throws(() => policyPayload(next, [], [grant]));
  assert.throws(() => policyPayload(next, ['write_one'], [{ tool: 'write_one', operation: null }]));
});
test('data-driven grant names never mutate JavaScript object prototypes', () => {
  const next = { policy_contract: 'woow-v3-exact-grants', disabled:[], writes_enabled:false, enabled_write_tools:[], tools: JSON.parse('{"__proto__":{"write":false,"legacy_write":false,"operation_parameter":"action","inputSchema":{},"write_grants":["__proto__:create"]}}') };
  const payload = policyPayload(next, [], [{ tool: '__proto__', operation: 'create' }]);
  assert.equal(Object.getPrototypeOf(payload), Object.prototype);
  assert.deepEqual(payload.enabled_write_tools, ['__proto__:create']);
});
test('client example uses placeholders, not browser origin or default credentials', () => {
  assert.match(clientExample(null), /YOUR-MCP-HOST/);
  assert.match(clientExample('https://client.example.test/mcp'), /YOUR_ADDON_TOKEN/);
  assert.match(clientExample(null, 'explicit-fixture-token'), /explicit-fixture-token/);
});
test('MOCK mutation refreshes CSRF; same-origin, no-store, empty POST token body', async () => {
  const calls = [];
  const api = new AdminApi(base, async (path, options) => { calls.push({ path, ...options }); return response(path.endsWith('bootstrap') ? bootstrap() : { token: null }); });
  await api.mutate('token/reveal');
  assert.equal(calls.length, 2);
  assert.equal(calls[0].path, `${base}/api/bootstrap`);
  assert.equal(calls[1].path, `${base}/api/token/reveal`);
  assert.equal(calls[1].method, 'POST');
  assert.equal(calls[1].body, undefined);
  assert.equal(calls[1].headers['X-CSRF-Token'], bootstrap().csrf);
  for (const call of calls) { assert.equal(call.credentials, 'same-origin'); assert.equal(call.cache, 'no-store'); assert.equal(call.redirect, 'error'); }
});
test('MOCK missing CSRF and mismatched API base stop mutation before dispatch', async () => {
  for (const patch of [{ csrf: '' }, { api_base: 'https://evil.example.test/api' }, { base_path: '/wrong' }]) {
    let count = 0;
    const api = new AdminApi(base, async () => { count++; return response({ ...bootstrap(), ...patch }); });
    await assert.rejects(() => api.mutate('endpoint', { endpoint: null }));
    assert.equal(count, 1);
  }
});
test('MOCK HTTP 200 without typed saved acknowledgement is not success', async () => {
  const api = new AdminApi(base, async path => response(path.endsWith('bootstrap') ? bootstrap() : {}));
  await assert.rejects(() => api.mutate('endpoint', { endpoint: null }), /無法確認/);
});
test('MOCK denied save never reports success or reflects server/body credentials', async () => {
  const api = new AdminApi(base, async path => path.endsWith('bootstrap') ? response(bootstrap()) : new Response('PRIVATE_CANARY', { status: 403 }));
  await assert.rejects(() => api.mutate('backend', { url: null, key: null }), error => error instanceof ApiError && error.status === 403 && !error.message.includes('PRIVATE_CANARY'));
});
