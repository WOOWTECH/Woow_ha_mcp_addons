// P9 kit, operator side (Node >= 22): real HA admin login -> Ingress session -> the app's admin API (token
// reveal/rotate/revoke), then packaging/ha_p9_probe.py on the HA host over SSH with the MCP token on stdin.
// HA credentials come from the environment only; no token, password or cookie is printed or written.
// The HA refresh token issued for this run is revoked at the end. See docs/operations/ha-p9-kit.md.
//
//   HA_URL=https://ha.example HA_USER=... HA_PASS=... APP_SLUG=<repo>_woow_mcp_<product> \
//   SSH_TARGET=<ssh host> PROBE_PORT=18081 [PROBE_TOOL=name PROBE_TOOL_ARGS='{"k":"v"}'] [SSH_CONFIG=path] \
//   node packaging/ha_p9_driver.mjs [--backend-file F] [--tokens] [--plan P [--outage-url U]] [--modes restart,childkill,bench,cycle]
// --backend-file: 0600 JSON with the exact admin API body (n8n {"url","key"}; others {"connection":{...}}); never printed.
// --plan: JSON {"reads": [[tool, args], ...], "denials": [[tool, args], ...]} run by the probe's plan mode.
// --outage-url: with --backend-file and --plan, swap the backend URL for an unreachable one, require structured
//   read failures, then restore the original backend and require the plan to pass again.
import { spawnSync } from 'node:child_process';
import { readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const env = (name, fallback) => {
  const value = process.env[name] ?? fallback;
  if (value === undefined) throw new Error(`missing ${name}`);
  return value;
};
const H = env('HA_URL').replace(/\/$/, ''), CID = H + '/', SLUG = env('APP_SLUG'), TARGET = env('SSH_TARGET');
const PORT = env('PROBE_PORT'), REMOTE = env('PROBE_REMOTE', '/tmp/ha_p9_probe.py');
const SSH = [...(process.env.SSH_CONFIG ? ['-F', process.env.SSH_CONFIG] : []), TARGET];
if (!/^[A-Za-z0-9_.-]+$/.test(SLUG) || !/^\d+$/.test(PORT) || !/^[A-Za-z0-9_./-]+$/.test(REMOTE)) throw new Error('bad slug/port/path');
const quote = (s) => `'${String(s).replaceAll("'", `'\\''`)}'`;
const args = ['--port', PORT, '--slug', SLUG];
if (process.env.PROBE_TOOL) args.push('--tool', process.env.PROBE_TOOL, '--args', env('PROBE_TOOL_ARGS', '{}'));
const argv = process.argv.slice(2);
const opt = (name) => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : undefined);
const secretJson = (path) => {
  if ((statSync(path).mode & 0o077) !== 0) throw new Error(`${path} must not be readable by group/others (chmod 600)`);
  return JSON.parse(readFileSync(path, 'utf8'));
};
const BACKEND = opt('--backend-file') ? secretJson(opt('--backend-file')) : undefined;
const PLAN = opt('--plan') ? JSON.parse(readFileSync(opt('--plan'), 'utf8')) : undefined;
const OUTAGE = opt('--outage-url');
if (OUTAGE && !(BACKEND && PLAN)) throw new Error('--outage-url needs --backend-file and --plan');
const withUrl = (body, url) => {
  const copy = structuredClone(body);
  if (copy.connection) { for (const key of Object.keys(copy.connection)) if (/(^|_)url$/.test(key)) copy.connection[key] = url; }
  else copy.url = url;
  return copy;
};
const modes = argv.includes('--modes') ? argv[argv.indexOf('--modes') + 1].split(',') : [];
for (const mode of modes) if (!['restart', 'childkill', 'bench', 'cycle'].includes(mode)) throw new Error('bad mode ' + mode);

const ssh = (command, input) => spawnSync('ssh', [...SSH, command], { input, encoding: 'utf8', timeout: 900000 });
const remote = (mode, input, extra = []) => {
  const r = ssh(`python3 ${REMOTE} ${mode} ${[...args, ...extra].map(quote).join(' ')}`, input);
  process.stdout.write(r.stdout || '');
  if (r.status !== 0) console.log(`probe ${mode} exit ${r.status}: ${(r.stderr || '').slice(-400)}`);
};
const upload = ssh(`cat > ${REMOTE}`, readFileSync(fileURLToPath(new URL('./ha_p9_probe.py', import.meta.url))));
if (upload.status !== 0) throw new Error('probe upload failed');

const UA = 'Mozilla/5.0 (X11; Linux x86_64) woow-p9-driver';
const json = async (r) => { const t = await r.text(); try { return JSON.parse(t); } catch { throw new Error(`${r.status} ${t.slice(0, 120)}`); } };
const post = (u, body, type = 'application/json') => fetch(H + u, { method: 'POST', headers: { 'Content-Type': type, 'User-Agent': UA }, body });
const flow = await json(await post('/auth/login_flow', JSON.stringify({ client_id: CID, handler: ['homeassistant', null], redirect_uri: H + '/?auth_callback=1' })));
const step = await json(await post('/auth/login_flow/' + flow.flow_id, JSON.stringify({ client_id: CID, username: env('HA_USER'), password: env('HA_PASS') })));
if (step.type !== 'create_entry') throw new Error('HA login failed: ' + step.type);
const tok = await json(await post('/auth/token', new URLSearchParams({ grant_type: 'authorization_code', code: step.result, client_id: CID }), 'application/x-www-form-urlencoded'));
let ws;
try {
  ws = new WebSocket(H.replace(/^http/, 'ws') + '/api/websocket', { headers: { 'User-Agent': UA } });
  let nextId = 1; const pending = new Map();
  const call = (endpoint, method) => new Promise((resolve, reject) => {
    const id = nextId++; pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, type: 'supervisor/api', endpoint, method }));
  });
  await new Promise((resolve, reject) => {
    ws.onmessage = (e) => { const m = JSON.parse(e.data);
      if (m.type === 'auth_required') ws.send(JSON.stringify({ type: 'auth', access_token: tok.access_token }));
      else if (m.type === 'auth_ok') resolve();
      else if (m.type === 'auth_invalid') reject(new Error('ws auth invalid'));
      else if (pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.success ? p.resolve(m.result) : p.reject(new Error(JSON.stringify(m.error))); } };
    ws.onerror = () => reject(new Error('ws error')); setTimeout(() => reject(new Error('ws timeout')), 20000); });
  const info = await call(`/addons/${SLUG}/info`, 'get');
  const session = (await call('/ingress/session', 'post')).session;
  console.log(`HA admin login ok; app ${SLUG} ${info.version} state=${info.state}`);
  const ING = H + info.ingress_url.replace(/\/*$/, '/'), hdr = { Cookie: 'ingress_session=' + session, 'User-Agent': UA };
  const boot = async () => { const r = await fetch(ING + 'api/bootstrap', { headers: hdr }); return { status: r.status, ...(await r.json()) }; };
  let b = await boot();
  console.log('bootstrap', b.status, JSON.stringify({ product: b.product, backend_url_set: Boolean(b.backend_url), backend_key_set: b.backend_key_set, connection_configured: b.connection_configured, token_active: b.token_active, writes_enabled: b.writes_enabled, tools: Object.keys(b.tools || {}).length }));
  const act = async (name) => { const r = await fetch(ING + 'api/token/' + name, { method: 'POST', headers: { ...hdr, 'x-csrf-token': b.csrf } });
    console.log(`token/${name}:`, r.status); return r.status === 200 ? (await r.json()).token : undefined; };
  const check = (rows) => remote('check', rows.map(([label, token]) => `${label}\t${token}\n`).join(''));
  const putBackend = async (body, label) => {
    const r = await fetch(ING + 'api/backend', { method: 'PUT', headers: { ...hdr, 'x-csrf-token': b.csrf, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    console.log(`PUT api/backend (${label}):`, r.status);
    if (r.status !== 200) throw new Error('backend update refused');
    await new Promise((resolve) => setTimeout(resolve, 5000));  // the app restarts its MCP child
    b = await boot();
    console.log('bootstrap', JSON.stringify({ connection_configured: b.connection_configured, health: b.health }));
  };
  const plan = async (extra = []) => remote('plan', (await act('reveal')) + '\n' + JSON.stringify(PLAN), extra);

  if (BACKEND) await putBackend(BACKEND, 'from file');

  if (argv.includes('--tokens')) {
    const noCsrf = await fetch(ING + 'api/token/rotate', { method: 'POST', headers: hdr });
    console.log('token/rotate without csrf:', noCsrf.status, '(expect 403)');
    const t1 = await act('reveal');
    check([['T1 current', t1]]);
    const t2 = await act('rotate');
    console.log('rotate returned a different token:', Boolean(t2) && t2 !== t1);
    check([['T1 after rotate', t1], ['T2 rotated', t2]]);
    await act('revoke');
    b = await boot(); console.log('after revoke token_active:', b.token_active);
    check([['T2 after revoke', t2]]);
    const t3 = await act('rotate');
    check([['T2 after re-issue', t2], ['T3 re-issued', t3]]);
  }
  if (PLAN) {
    console.log('--- plan');
    await plan();
    if (OUTAGE) {
      console.log('--- outage');
      await putBackend(withUrl(BACKEND, OUTAGE), 'unreachable URL');
      await plan(['--expect-backend-down']);
      await putBackend(BACKEND, 'restored');
      await plan();
    }
  }
  for (const mode of modes) {
    console.log('---', mode);
    const current = await act('reveal');
    remote(mode, current + '\n');
    if (mode === 'restart') {
      b = await boot();  // the app restarted: fresh CSRF
      console.log('token unchanged across restart:', (await act('reveal')) === current);
    }
  }
} finally {
  ws?.close();
  const r = await post('/auth/token', new URLSearchParams({ action: 'revoke', token: tok.refresh_token }), 'application/x-www-form-urlencoded');
  console.log('revoke HA refresh token:', r.status);
}
