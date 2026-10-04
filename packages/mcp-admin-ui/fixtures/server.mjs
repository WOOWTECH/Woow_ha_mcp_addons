// LOCAL MOCK ONLY. Not imported by src or build; never ship this as an HA verifier.
import http from 'node:http';
import '../../../tests/owned_network.cjs';
if (process.env.UI_PORT !== undefined) throw Error('invalid private UI_PORT: owned ephemeral fixture required');
const generation = process.env.OWNED_UI_FIXTURE;
if (!process.send || !/^[a-f0-9]{64}$/.test(generation ?? '')) throw Error('owned fixture lifecycle required');
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { extname, resolve, sep } from 'node:path';
import { mountPath, products, backendPayload } from '../src/contracts.js';
const dist = process.env.OWNED_UI_ASSET_ROOT ?? fileURLToPath(new URL('../dist/', import.meta.url));
const prefix = '/api/hassio_ingress/DUMMY';
const mounts = [prefix, ''];
let config, state, calls, nonce;
function reset(next = {}) {
  config = next;
  calls = [];
  nonce = 0;
  state = {
    product: next.product ?? 'n8n', endpoint: next.endpoint ?? null,
    backend_url: null, backend_key_set: false, connection_configured: next.configured ?? false,
    token_active: true, writes_enabled: next.legacyWrites ?? false, disabled: [],
    ...(next.granular !== false ? { policy_contract: 'woow-v3-exact-grants' } : {}), enabled_write_tools: [],
    tools: {
      read_example: { write: false, legacy_write:false, write_grants:[], operation_parameter:null, inputSchema:{} },
      write_example: { write: true, legacy_write:true, write_grants:['write_example'], operation_parameter:null, inputSchema:{} },
      mixed_example: { write: false, legacy_write:false, write_grants:['mixed_example:create','mixed_example:delete'], operation_parameter:'action', inputSchema:{} },
    },
    health: { management: 'alive', child: { state: 'not_started', transport_ready: false }, backend: next.offline ? 'unreachable' : 'unconfigured' },
  };
}
reset();
const json = (response, status, value) => { response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); response.end(JSON.stringify(value)); };
async function body(request) {
  let raw = '';
  for await (const chunk of request) { raw += chunk; if (raw.length > 262144) throw Error('MOCK oversized body'); }
  return raw ? JSON.parse(raw) : null;
}
const server = http.createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://127.0.0.1').pathname;
    if (path === '/__fixture/ready') return json(response, 200, { fixture: 'LOCAL MOCK — not HA security' });
    if (path === '/__fixture/reset' && request.method === 'POST') { reset(await body(request) ?? {}); return json(response, 200, { reset: true }); }
    if (path === '/__fixture/calls') return json(response, 200, calls);
    const mount = mounts.find(candidate => candidate === '' || path.startsWith(`${candidate}/`));
    const local = path.slice(mount.length);
    if (local === '/api/bootstrap') {
      if (config.deniedBootstrap) return json(response, 403, { error: 'MOCK denied' });
      nonce++;
      return json(response, 200, { ...state, base_path: mount, api_base: `${mount}/api`, csrf: config.missingCsrf ? null : `mock_fresh_csrf_value_${nonce}` });
    }
    if (local.startsWith('/api/')) {
      const operation = local.slice(5);
      const payload = await body(request);
      const validCsrf = request.headers['x-csrf-token'] === `mock_fresh_csrf_value_${nonce}`;
      calls.push({ operation, method: request.method, validCsrf, fields: Object.keys(payload ?? {}), ...(operation === 'policy' ? { policy: payload } : {}) });
      if (!validCsrf || config.deniedSave) return json(response, 403, { error: 'MOCK DENIED PRIVATE_CANARY_MUST_NOT_RENDER' });
      if (config.saveStatus) return json(response, config.saveStatus, { error: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER' });
      if (operation.startsWith('token/')) {
        if (request.method !== 'POST' || payload !== null) return json(response, 400, { error: 'MOCK token contract' });
        if (operation === 'token/revoke') { state.token_active = false; response.writeHead(204); return response.end(); }
        if (operation === 'token/rotate') state.token_active = true;
        return json(response, 200, { token: state.token_active ? 'M'.repeat(43) : null });
      }
      if (request.method !== 'PUT') return json(response, 405, {});
      if (operation === 'backend') {
        const connection = state.product === 'n8n' ? payload : payload.connection;
        const clear = state.product === 'n8n' ? connection?.url === null && connection?.key === null : connection === null;
        if (!clear) backendPayload(state.product, 'replace', connection);
        if (JSON.stringify(payload) !== JSON.stringify(clear ? backendPayload(state.product, 'clear') : backendPayload(state.product, 'replace', connection))) return json(response, 400, {});
        state.connection_configured = !clear;
      } else if (operation === 'endpoint') state.endpoint = payload.endpoint;
      else if (operation === 'policy') {
        if (Object.keys(payload).sort().join() !== 'disabled,enabled_write_tools,writes_enabled') return json(response, 400, {});
        Object.assign(state, payload);
      } else return json(response, 404, {});
      return json(response, 200, { saved: true });
    }
    if (local.startsWith('/assets/')) {
      const filename = resolve(dist, `.${local}`);
      if (!filename.startsWith(`${resolve(dist)}${sep}`)) return json(response, 404, {});
      const types = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.eot': 'application/vnd.ms-fontobject' };
      response.writeHead(200, { 'Content-Type': types[extname(filename)] ?? 'application/octet-stream' });
      return response.end(await readFile(filename));
    }
    if (!['/', '/overview', '/backend', '/tools', '/access'].includes(local)) return json(response, 404, {});
    // Same validation required in production AFTER trusted HA role/prefix resolution.
    const html = (await readFile(`${dist}/index.html`, 'utf8')).replaceAll('__MCP_UI_BASE__', mountPath(mount));
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'", 'X-Content-Type-Options': 'nosniff' });
    response.end(html.replace('<body>', '<body><div role="note" class="notice">LOCAL MOCK · 瀏覽器測試資料，非 HA 授權或後端實測</div>'));
  } catch { if (!response.headersSent) json(response, 400, { error: 'MOCK invalid request' }); else response.end(); }
});
server.once('error', () => process.exit(1));
server.listen(0, '127.0.0.1', () => {
  const port = server.address().port;
  if (port === 3000) return server.close(() => process.exit(1));
  process.send({ generation, port }); // candidate only; parent proves live PID/fd/inode
});
const stop = () => { server.close(() => process.exit(0)); server.closeAllConnections(); };
for (const signal of ['SIGINT', 'SIGTERM', 'disconnect']) process.on(signal, stop);
