// LOCAL MOCK ONLY. Not imported by src or build; never ship this as an HA verifier.
import http from 'node:http';
import '../../../tests/owned_network.cjs';
if (process.env.UI_PORT !== undefined) throw Error('invalid private UI_PORT: owned ephemeral fixture required');
const generation = process.env.OWNED_UI_FIXTURE;
if (!process.send || !/^[a-f0-9]{64}$/.test(generation ?? '')) throw Error('owned fixture lifecycle required');
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { extname, resolve, sep } from 'node:path';
import { mountPath, products, backendPayload, odooSwitchPayload, n8nSessionPayload, odooMethodsPayload } from '../src/contracts.js';
const dist = process.env.OWNED_UI_ASSET_ROOT ?? fileURLToPath(new URL('../dist/', import.meta.url));
const prefix = '/api/hassio_ingress/DUMMY';
const mounts = [prefix, ''];
// HM-11: the multi-profile management API as contract.md section 3 describes it (HM-10 is the real one). Switched off
// (the default: config.profiles unset) every answer is the single-profile one, as before, and X-MCP-Profile is ignored.
// Switched on (config.profiles: true or {extra: [...], limit, indexCorrupt, ...}) every profile-scoped request needs
// exactly one X-MCP-Profile, answers echo it, and /api/profiles lists, creates, renames and deletes profiles.
const DEFAULT = 'default';
const PROFILE = /^(?:default|[0-9a-f]{24})$/;
const OPERATION = /^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/;
// Synthetic low-entropy tokens, one letter per profile (test data rule, plan 12.0 item 4).
const TOKEN_LETTERS = ['T', 'U', 'V', 'W', 'X', 'Y'];
let config, calls, reads, nonce, profiles, index, defaults = {};
function profileState(next) {
  const state = {
    product: next.product ?? 'n8n', endpoint: next.endpoint ?? null,
    backend_url: null, backend_key_set: false, connection_configured: next.configured ?? false,
    token_active: true, writes_enabled: next.legacyWrites ?? false, disabled: [],
    ...(Object.hasOwn(next, 'tokenMask') ? {token_masked: next.tokenMask} : {}),
    ...(Object.hasOwn(next, 'tokenHistory') ? {token_history: structuredClone(next.tokenHistory)} : {}),
    ...(next.granular !== false ? { policy_contract: 'woow-v3-exact-grants' } : {}), enabled_write_tools: next.grants ?? [],
    tools: {
      read_example: { write: false, legacy_write:false, write_grants:[], operation_parameter:null, inputSchema:{} },
      write_example: { write: true, legacy_write:true, write_grants:['write_example'], operation_parameter:null, inputSchema:{} },
      mixed_example: { write: false, legacy_write:false, write_grants:['mixed_example:create','mixed_example:delete'], operation_parameter:'action', inputSchema:{} },
    },
    health: { management: 'alive', child: { state: 'not_started', transport_ready: false }, backend: next.offline ? 'unreachable' : 'unconfigured' },
    // 2026-10-27 one-time all-on notice (shape of owner_defaults.view); omitted unless a test supplies it.
    ...(next.ownerDefaults ? { owner_defaults: structuredClone(next.ownerDefaults) } : {}),
  };
  if (state.product === 'odoo' && next.odooApi !== false) {
    state.odoo_write_switches = next.odooSwitches ?? {enable_writes:true, allow_direct_writes:true,
      allow_unknown_methods:true, chatter_direct:true};
    state.odoo_write_switches_source = next.odooSource ?? 'legacy_all_on';
  }
  if (next.parity046) {
    state.backend_edit = {contract:'woow-connection-patch-v1',
      values:Object.fromEntries(products[state.product].fields.filter(([, , type]) => !type.includes('secret')).map(([key]) => [key, next.connection?.[key] ?? null])),
      secret_set:Object.fromEntries(products[state.product].fields.filter(([, , type]) => type.includes('secret')).map(([key]) => [key, true]))};
    if (state.product === 'odoo') {state.odoo_allowed_methods = []; state.odoo_allowed_methods_source = 'legacy_empty';}
    if (state.product === 'n8n') {
      state.n8n_session = {timeout_seconds:600, max_sessions:20};
      state.n8n_session_source = 'legacy_default';
    }
  }
  if (next.operations) {
    state.denied_operations = next.denied_operations ?? {};
    for (const tool of Object.values(state.tools)) Object.assign(tool, {operations: [], default_operation: null});
    Object.assign(state.tools.mixed_example, {default_operation: 'list', operations: [
      {name:'list', write:false}, {name:'get', write:false}, {name:'create', write:true}, {name:'delete', write:true},
    ]});
  }
  if (next.n8nExposure) {
    // 僅供介面測試；與正式 n8n 三個工具的既有授權形狀相同。
    state.tools = {
      n8n_workflow_versions: {write:false, legacy_write:false, operation_parameter:'mode', default_operation:'list',
        write_grants:['rollback','delete','prune'].map(op => `n8n_workflow_versions:${op}`),
        operations:['list','get','diff','rollback','delete','prune'].map(name => ({name,write:['rollback','delete','prune'].includes(name)})), inputSchema:{}},
      n8n_test_workflow: {write:true, legacy_write:false, write_grants:['n8n_test_workflow'], operation_parameter:null, default_operation:null, operations:[], inputSchema:{}},
      n8n_update_partial_workflow: {write:true, legacy_write:false, write_grants:['n8n_update_partial_workflow'], operation_parameter:null, default_operation:null, operations:[], inputSchema:{}},
    };
  }
  return state;
}
const switchedOn = () => Boolean(config.profiles);
const profileConfig = () => typeof config.profiles === 'object' && config.profiles !== null ? config.profiles : {};
function reset(next = {}) {
  config = {...defaults, ...next};
  calls = [];
  reads = [];
  nonce = 0;
  profiles = new Map([[DEFAULT, {id: DEFAULT, label: 'Default', port: 3000, token: 'M', state: profileState(config),
    revision: 1, receipts: new Map(), status: 'running', disabled_reason: null, blocked_reason: null}]]);
  index = {revision: 1, receipts: new Map(), created: 0};
  for (const spec of profileConfig().extra ?? []) addProfile(spec);
}
// DQ-02: a new profile copies the default profile's policy as it is now; its connection is empty and its token new.
function addProfile(spec = {}) {
  const base = profiles.get(DEFAULT).state;
  const id = spec.id ?? `e${(++index.created).toString(16).padStart(7, '0')}${'f'.repeat(16)}`;
  const next = {...config, ownerDefaults: undefined, endpoint: null, connection: undefined, configured: spec.configured ?? false};
  delete next.tokenMask;
  delete next.tokenHistory;
  for (const field of ['tokenMask', 'tokenHistory']) if (Object.hasOwn(spec, field)) next[field] = spec[field];
  const state = profileState(next);
  if (state.backend_edit && !state.connection_configured) for (const field of Object.keys(state.backend_edit.secret_set)) state.backend_edit.secret_set[field] = false;
  for (const key of ['disabled', 'enabled_write_tools', 'writes_enabled', 'denied_operations', 'odoo_allowed_methods']) {
    if (Object.hasOwn(base, key)) state[key] = structuredClone(base[key]);
  }
  if (base.odoo_write_switches) { state.odoo_write_switches = structuredClone(base.odoo_write_switches); state.odoo_write_switches_source = 'saved'; }
  if (spec.policy) Object.assign(state, structuredClone(spec.policy));
  const taken = new Set([...profiles.values()].map(profile => profile.port));
  let port = 18000;
  while (taken.has(port)) port++;
  const profile = {id, label: spec.label ?? `帳號 ${profiles.size}`, port: spec.port ?? port, token: spec.token ?? TOKEN_LETTERS[(profiles.size - 1) % TOKEN_LETTERS.length],
    state, revision: 1, receipts: new Map(), status: spec.status ?? 'unconfigured', disabled_reason: spec.disabled_reason ?? null,
    blocked_reason: spec.blocked_reason ?? null, unavailable: spec.unavailable === true,
    ...(Object.hasOwn(spec, 'required_memory_mib') ? {required_memory_mib: spec.required_memory_mib} : {})};
  profiles.set(id, profile);
  return profile;
}
function capabilities(profile) {
  const state = profile.state;
  const result = {schema_version:1, deployment:{kind:config.fixed ? 'builtin' : 'ha-addon'}, product:{id:state.product,version:'test'},
    admin:{authority:config.fixed ? 'paas-password' : 'ha-admin'}, backend:{mode:config.fixed?'fixed':'manual',can_edit:!config.fixed,can_test:true},
    capabilities:{tool_schema:true,effective_tools:true,operation_policy:true,logs:true,restart_child:true,revoke_token:true},
    tools:{catalog_count:3,policy_enabled_count:3,effective_count:config.offline?null:3,status:config.offline?'unknown':'observed',
      items:Object.keys(state.tools).map(name=>({name,description:`Description for ${name}`,inputSchema:{type:'object',properties:{value:{type:'string'}}},schema_source:'child',policy_enabled:true,effective:config.offline?null:true}))}};
  if (config.operations) {
    result.capabilities.operation_denies = true;
    for (const item of result.tools.items) {
      const tool = state.tools[item.name];
      const whole = !state.disabled.includes(item.name) && (!tool.write || state.enabled_write_tools.includes(item.name) || tool.legacy_write && state.writes_enabled);
      item.operations = tool.operations.map(op => ({...op, denied: state.denied_operations[item.name]?.includes(op.name) ?? false,
        policy_enabled: whole && !state.denied_operations[item.name]?.includes(op.name) && (!op.write || state.enabled_write_tools.includes(`${item.name}:${op.name}`))}));
      for (const operation of item.operations) operation.effective = operation.policy_enabled ? config.offline ? null : true : false;
      item.policy_enabled = whole && (item.operations.length ? item.operations.some(op => op.policy_enabled) : !state.denied_operations[item.name]?.length);
      item.effective = item.policy_enabled ? config.offline ? null : true : false;
      if (!item.policy_enabled) item.reason = 'operations_not_permitted';
    }
    result.tools.policy_enabled_count = result.tools.items.filter(item => item.policy_enabled).length;
    result.tools.effective_count = config.offline ? null : result.tools.policy_enabled_count;
    const operations = result.tools.items.flatMap(item => item.operations);
    result.tools.operation_count = operations.length;
    result.tools.policy_enabled_operation_count = operations.filter(operation => operation.policy_enabled).length;
    result.tools.effective_operation_count = config.offline ? null : operations.filter(operation => operation.effective === true).length;
  }
  if (config.n8nExposure) {
    const updater = result.tools.items.find(item => item.name === 'n8n_update_partial_workflow');
    for (const item of result.tools.items.filter(item => item.name !== updater.name)) {
      item.conditional_writes = [{parameter:'exposeToMcp', requires_tool:updater.name,
        policy_enabled:config.unknownExposure ? null : updater.policy_enabled}];
    }
  }
  return result;
}
reset();
// The default profile's revision is the single-profile one; an additional profile's differs (its HMAC domain).
const etag = profile => profile.id === DEFAULT ? `"c1-${profile.revision.toString(16).padStart(64, '0')}"`
  : `"c1-${profile.id}${profile.revision.toString(16).padStart(40, '0')}"`;
const indexEtag = () => `"p1-${index.revision.toString(16).padStart(64, '0')}"`;
const configuration = profile => ({revision: etag(profile).slice(1, -1), saved_revision: 'launch-fixture',
  applied_revision: config.applyState === 'pending' || config.applyState === 'failed' ? null : 'launch-fixture',
  apply_state: config.applyState ?? 'applied', last_error_code: config.applyState === 'failed' ? 'child_start_failed' : null});
const json = (response, status, value, headers = {}) => { response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers }); response.end(JSON.stringify(value)); };
const refuse = (response, status, code, extra = {}) => json(response, status, {error: 'request denied', detail: {code, ...extra}});
// The echo (contract 3.4): a profile-scoped success answer names the profile; config.wrongEcho = {operation, id} makes
// one operation name another profile, to test that the panel shows nothing of such an answer.
function reply(response, status, value, profile, operation) {
  if (!switchedOn() || status >= 300) return json(response, status, value);
  const id = config.wrongEcho?.operation === operation ? config.wrongEcho.id : profile.id;
  const echo = operation === 'bootstrap' ? {profile: {id, label: profiles.get(id)?.label ?? profile.label, is_default: id === DEFAULT}, profiles_supported: true}
    : {profile: {id}};
  return json(response, status, {...value, ...echo});
}
// contract 3.3: exactly one X-MCP-Profile, default or 24 lowercase hex, an existing profile; never a fallback.
function scoped(request, response) {
  if (!switchedOn()) return profiles.get(DEFAULT);
  const value = request.headers['x-mcp-profile'];
  if (value === undefined) { refuse(response, 400, 'profile_id_required'); return null; }
  if (value.includes(',') || !PROFILE.test(value)) { refuse(response, 400, 'profile_id_invalid'); return null; }
  const profile = profiles.get(value);
  if (!profile) { refuse(response, 404, 'profile_not_found'); return null; }
  if (profileConfig().indexCorrupt && profile.id !== DEFAULT) { refuse(response, 503, 'profile_index_corrupt'); return null; }
  // A profile whose state cannot be read (contract 3.3): 503 state unavailable; it can still be deleted.
  if (profile.unavailable) { json(response, 503, {error: 'state unavailable'}); return null; }
  return profile;
}
const header = request => request.headers['x-mcp-profile'] === undefined ? {} : {profileHeader: request.headers['x-mcp-profile']};
const row = profile => ({id: profile.id, label: profile.label, port: profile.port, is_default: profile.id === DEFAULT,
  disabled_reason: profile.disabled_reason, ...(profile.disabled_reason === 'memory_capacity' ? {required_memory_mib: profile.required_memory_mib ?? 1156} : {}),
  status: profile.status, blocked_reason: profile.blocked_reason});
// Labels (contract 3.6): the server's rule, written here independently of the panel's.
const key = label => label.normalize('NFKC').toLowerCase().normalize('NFKC');
function labelRefusal(value, except = null) {
  if (typeof value !== 'string') return [400, null];
  const label = value.trim();
  if ([...label].length < 1 || [...label].length > 80 || /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}\p{Co}\p{Cn}]/u.test(label)) return [422, 'profile_label_invalid'];
  const taken = [...profiles.values()].filter(profile => profile.id !== except && profile.id !== DEFAULT).map(profile => key(profile.label));
  if (['default', '預設帳號'].includes(key(label)) || taken.includes(key(label))) return [409, 'profile_label_conflict'];
  return null;
}
async function profileRoutes(request, response, local) {
  const id = local === '/api/profiles' ? null : local.slice('/api/profiles/'.length);
  const payload = await body(request);
  if (request.method === 'GET' && id === null) {
    if (profileConfig().indexCorrupt) return refuse(response, 503, 'profile_index_corrupt');
    if (profileConfig().listStatus) return json(response, profileConfig().listStatus, {error: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER'});
    reads.push({operation: 'profiles', ...header(request)});  // reads are not calls: specs count calls
    return json(response, 200, {profiles: [...profiles.values()].map(row)}, {ETag: indexEtag()});
  }
  const validCsrf = request.headers['x-csrf-token'] === `mock_fresh_csrf_value_${nonce}`;
  const operationId = request.headers['idempotency-key'];
  const ifMatch = request.headers['if-match'];
  calls.push({operation: id === null ? 'profiles' : `profiles/${id}`, method: request.method, validCsrf, ifMatch,
    ...(operationId ? {operationId} : {}), fields: Object.keys(payload ?? {}), ...(payload?.label !== undefined ? {label: payload.label} : {}), ...header(request)});
  if (!validCsrf || config.deniedSave) return json(response, 403, { error: 'MOCK DENIED PRIVATE_CANARY_MUST_NOT_RENDER' });
  if (id !== null && !PROFILE.test(id)) return json(response, 400, {error: 'request denied'});
  if (id === null && request.method === 'POST') {
    if (!payload || typeof payload !== 'object' || Object.keys(payload).join() !== 'label') return json(response, 400, {error: 'request denied'});
    const prior = operationId && index.receipts.get(operationId);
    if (prior) {  // replay before If-Match, as every receipt (0.4.7)
      if (prior.kind !== 'profile.create' || prior.label !== payload.label.trim()) return refuse(response, 409, 'operation_id_conflict');
      return json(response, 200, {...row(profiles.get(prior.target)), operation: {...prior.operation, replayed: true}});
    }
    if (!ifMatch) return refuse(response, 428, 'config_revision_required');
    if (!operationId) return refuse(response, 428, 'operation_id_required');
    if (!OPERATION.test(operationId)) return refuse(response, 400, 'operation_id_invalid');
    if (ifMatch !== indexEtag()) return json(response, 409, {detail: {code: 'config_conflict'}});
    const refusal = labelRefusal(payload.label);
    if (refusal) return refusal[1] ? refuse(response, ...refusal) : json(response, refusal[0], {error: 'request denied'});
    const limit = profileConfig().limit ?? 5;
    if (profiles.size - 1 >= limit) return refuse(response, 409, 'profile_limit_reached', {limit});
    if (profileConfig().memory) return refuse(response, 409, 'profile_memory_insufficient', {limit, required_memory_mib: 1156, available_memory_mib: 900});
    const created = addProfile({label: payload.label.trim()});
    index.revision++;
    const operation = {id: operationId, kind: 'profile.create', state: 'completed', replayed: false};
    index.receipts.set(operationId, {kind: 'profile.create', label: created.label, target: created.id, operation});
    if (config.createToken) return json(response, 201, {...row(created), operation, token: `${created.token}`.repeat(43)});
    return json(response, 201, {...row(created), operation});
  }
  if (id !== null && request.method === 'PATCH') {
    if (!payload || typeof payload !== 'object' || Object.keys(payload).join() !== 'label') return json(response, 400, {error: 'request denied'});
    if (!ifMatch) return refuse(response, 428, 'config_revision_required');
    if (id === DEFAULT) return refuse(response, 422, 'profile_default_immutable');
    if (!profiles.has(id)) return refuse(response, 404, 'profile_not_found');
    if (ifMatch !== indexEtag()) return json(response, 409, {detail: {code: 'config_conflict'}});
    const refusal = labelRefusal(payload.label, id);
    if (refusal) return refusal[1] ? refuse(response, ...refusal) : json(response, refusal[0], {error: 'request denied'});
    profiles.get(id).label = payload.label.trim();
    index.revision++;
    return json(response, 200, row(profiles.get(id)));
  }
  if (id !== null && request.method === 'DELETE') {
    if (payload !== null) return json(response, 400, {error: 'request denied'});
    const prior = operationId && index.receipts.get(operationId);
    if (prior) {
      if (prior.kind !== 'profile.delete' || prior.target !== id) return refuse(response, 409, 'operation_id_conflict');
      return json(response, 200, {deleted: id, operation: {...prior.operation, replayed: true}});
    }
    if (!ifMatch) return refuse(response, 428, 'config_revision_required');
    if (!operationId) return refuse(response, 428, 'operation_id_required');
    if (!OPERATION.test(operationId)) return refuse(response, 400, 'operation_id_invalid');
    if (id === DEFAULT) return refuse(response, 422, 'profile_default_immutable');
    if (!profiles.has(id)) return refuse(response, 404, 'profile_not_found');
    if (ifMatch !== indexEtag()) return json(response, 409, {detail: {code: 'config_conflict'}});
    // DQ-14: the token is revoked and the credentials wiped first (a mock: the profile is simply gone).
    profiles.delete(id);
    index.revision++;
    const operation = {id: operationId, kind: 'profile.delete', state: 'completed', replayed: false};
    index.receipts.set(operationId, {kind: 'profile.delete', target: id, operation});
    return json(response, 200, {deleted: id, operation});
  }
  return json(response, 405, {});
}
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
    // HM-11: what every reset of this worker starts from (the profiles-on Playwright project switches profiles on).
    if (path === '/__fixture/defaults' && request.method === 'POST') { defaults = await body(request) ?? {}; reset(); return json(response, 200, { defaults: true }); }
    if (path === '/__fixture/calls') return json(response, 200, calls);
    if (path === '/__fixture/reads') return json(response, 200, reads);
    if (path === '/__fixture/configuration' && request.method === 'POST') {
      const value = await body(request);
      if (value.changed) profiles.get(value.profile ?? DEFAULT).revision++;
      config.applyState = value.applyState;
      return json(response, 200, {});
    }
    // HM-11: another administrator (or tab) changes the profiles; the state each profile holds, for assertions.
    if (path === '/__fixture/profile' && request.method === 'POST') {
      const value = await body(request);
      if (value.action === 'delete') profiles.delete(value.id);
      else if (value.action === 'rename') profiles.get(value.id).label = value.label;
      else if (value.action === 'add') addProfile(value.spec ?? {});
      else if (value.action === 'switch') config = {...config, profiles: value.profiles};  // an upgrade: state and receipts kept
      else return json(response, 400, {});
      if (value.action !== 'switch') index.revision++;
      return json(response, 200, {});
    }
    if (path === '/__fixture/profiles') return json(response, 200, {index: indexEtag(), profiles: Object.fromEntries([...profiles.values()].map(profile => [profile.id,
      {label: profile.label, token_active: profile.state.token_active, revision: profile.revision, connection_configured: profile.state.connection_configured,
        endpoint: profile.state.endpoint, disabled: profile.state.disabled, enabled_write_tools: profile.state.enabled_write_tools, receipts: profile.receipts.size}]))});
    const mount = mounts.find(candidate => candidate === '' || path.startsWith(`${candidate}/`));
    const local = path.slice(mount.length);
    if (switchedOn() && (local === '/api/profiles' || local.startsWith('/api/profiles/'))) return await profileRoutes(request, response, local);
    if (local === '/api/capabilities') { const profile = scoped(request, response); return profile && reply(response, 200, capabilities(profile), profile, 'capabilities'); }
    if (local === '/api/diagnostics') {
      const profile = scoped(request, response);
      return profile && reply(response, 200, {logs:{entries:[{at:'2026-10-23',stream:'stderr',generation:1,text:switchedOn() ? `token=[REDACTED] profile=${profile.id.slice(0, 8)}` : 'token=[REDACTED]'}],redacted:true,bytes:100,dropped:2}}, profile, 'diagnostics');
    }
    if (local === '/api/configuration') { const profile = scoped(request, response); return profile && reply(response, 200, {configuration: configuration(profile)}, profile, 'configuration'); }
    if (local === '/api/bootstrap') {
      if (config.deniedBootstrap) return json(response, 403, { error: 'MOCK denied' });
      // The management server's answer while HA Core advertises a version the add-on has not reviewed.
      if (config.unreviewedCore) return json(response, 403, { error: 'request denied', detail: { code: 'core_version_unreviewed', ha_version: config.unreviewedCore }, untrusted: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER' });
      const profile = scoped(request, response);
      if (!profile) return;
      nonce++;
      const state = profile.state;
      return reply(response, 200, { ...state, ...(config.parity === false ? {} : {configuration: configuration(profile)}), operation_contract:{version:1,server_time_ms:Date.now(),retention_ms:86400000}, capabilities:capabilities(profile), base_path: mount, api_base: `${mount}/api`, csrf: config.missingCsrf ? null : `mock_fresh_csrf_value_${nonce}`,
        // With profiles the endpoint is the add-on's (the default profile's, DQ-13); the default profile also reports the index state.
        ...(switchedOn() ? {endpoint: profiles.get(DEFAULT).state.endpoint, ...(profile.id === DEFAULT ? {profile_index_state: profileConfig().indexCorrupt ? 'corrupt' : 'ok'} : {})} : {}) }, profile, 'bootstrap');
    }
    if (local.startsWith('/api/operations/')) {
      if (config.deniedSave) return json(response, 403, {});
      const profile = scoped(request, response);
      if (!profile) return;
      const saved=profile.receipts.get(local.slice('/api/operations/'.length));
      return saved ? reply(response,200,{operation:saved.operation,result:{status:'ok'}},profile,'operations') : json(response,404,{detail:{code:'operation_not_found'}});
    }
    if (local.startsWith('/api/')) {
      const operation = local.slice(5);
      const payload = await body(request);
      const validCsrf = request.headers['x-csrf-token'] === `mock_fresh_csrf_value_${nonce}`;
      calls.push({ operation, method: request.method, validCsrf, ifMatch: request.headers['if-match'], ...(request.headers['idempotency-key'] ? {operationId:request.headers['idempotency-key']} : {}), fields: Object.keys(payload ?? {}), ...(operation === 'policy' ? { policy: payload } : {}), ...(operation === 'odoo/write-switches' ? {switches:payload} : {}), ...(['backend/patch','n8n/session','odoo/allowed-methods'].includes(operation) ? {changedKeys:Object.keys(payload?.changes ?? {}), session:payload?.n8n_session, methods:payload?.odoo_allowed_methods} : {}), ...header(request) });
      if (!validCsrf || config.deniedSave) return json(response, 403, { error: 'MOCK DENIED PRIVATE_CANARY_MUST_NOT_RENDER' });
      const profile = scoped(request, response);
      if (!profile) return;
      const state = profile.state, receipts = profile.receipts;
      if (config.saveStatus) return json(response, config.saveStatus, { error: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER' });
      const kind={'token/rotate':'token.rotate','token/revoke':'token.revoke','child/restart':'mcp.restart'}[operation];
      const operationId=request.headers['idempotency-key'];
      if (kind && receipts.has(operationId)) {
        const prior=receipts.get(operationId);
        if(prior.operation.kind!==kind)return json(response,409,{detail:{code:'operation_id_conflict'}});
        return reply(response,200,{status:'ok',operation:{...prior.operation,replayed:true}},profile,operation);
      }
      if (!['token/reveal','backend/test'].includes(operation) && !request.headers['if-match']) return json(response,428,{detail:{code:'config_revision_required'}});
      if (request.headers['if-match'] && request.headers['if-match'] !== etag(profile)) return json(response, 409, {detail: {code: 'config_conflict'}, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER'});
      if (operation === 'backend/test') return reply(response,200,{tested_configuration:'saved',backend:'reachable',health:state.health},profile,operation);
      if (operation === 'owner-defaults/restore' || operation === 'owner-defaults/dismiss') {
        // MOCK of the server rules: POST, no body, If-Match of the reviewed revision, a pending marker.
        if (request.method !== 'POST' || payload !== null) return json(response, 400, { error: 'MOCK notice contract' });
        if (!request.headers['if-match']) return json(response, 428, { detail: { code: 'precondition_required' } });
        if (request.headers['if-match'] !== etag(profile)) return json(response, 409, { detail: { code: 'config_conflict' }, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER' });
        const view = state.owner_defaults;
        const restoring = operation.endsWith('/restore');
        if (!view || view.restored_at || (restoring ? !view.restore?.available : view.acknowledged_at)) {
          return json(response, 409, { error: 'owner_defaults_unavailable', detail: { code: 'owner_defaults_unavailable' }, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER' });
        }
        const at = '2026-10-27T09:30:00+00:00';
        if (restoring) {
          state.disabled = [...new Set([...state.disabled, ...view.restore.disabled_added])];
          state.enabled_write_tools = state.enabled_write_tools.filter(grant => !view.restore.write_grants_removed.includes(grant));
          Object.assign(view, { restored_at: at, notice: false });
          view.restore.available = false;
        } else Object.assign(view, { acknowledged_at: at, notice: false });
        profile.revision++;
        return reply(response, 200, { saved: true, configuration: configuration(profile), owner_defaults: view }, profile, operation);
      }
      let receipt;
      if(kind){
        if(!/^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/.test(operationId??''))return json(response,428,{detail:{code:'operation_id_required'}});
        receipt={id:operationId,kind,state:'completed',replayed:false};
        receipts.set(operationId,{operation:receipt});
      }
      if (operation === 'child/restart') return reply(response,202,{status:'ok',operation:receipt,accepted:true,apply_state:'pending'},profile,operation);
      if (operation.startsWith('token/')) {
        if (request.method !== 'POST' || payload !== null) return json(response, 400, { error: 'MOCK token contract' });
        if (operation === 'token/revoke') { state.token_active = false; profile.revision++; return reply(response,200,{status:'ok',operation:receipt},profile,operation); }
        if (operation === 'token/rotate') {state.token_active = true; profile.revision++;}
        return reply(response, 200, { ...(receipt ? {status:'ok',operation:receipt} : {}), token: state.token_active ? profile.token.repeat(43) : null }, profile, operation);
      }
      if (request.method !== 'PUT') return json(response, 405, {});
      if (operation === 'backend') {
        const connection = state.product === 'n8n' ? payload : payload.connection;
        const clear = state.product === 'n8n' ? connection?.url === null && connection?.key === null : connection === null;
        if (!clear) backendPayload(state.product, 'replace', connection);
        if (JSON.stringify(payload) !== JSON.stringify(clear ? backendPayload(state.product, 'clear') : backendPayload(state.product, 'replace', connection))) return json(response, 400, {});
        state.connection_configured = !clear;
      } else if (operation === 'backend/patch') {
        if (!config.parity046 || !state.connection_configured || !request.headers['if-match']) return json(response,400,{});
        for (const [key, value] of Object.entries(payload.changes)) {
          if (Object.hasOwn(state.backend_edit.secret_set, key)) state.backend_edit.secret_set[key] = value !== null;
          else state.backend_edit.values[key] = value;
        }
      } else if (operation === 'n8n/session') {
        n8nSessionPayload(state, Object.fromEntries(Object.entries(payload.n8n_session).map(([k,v]) => [k,String(v)])));
        state.n8n_session = payload.n8n_session;
        state.n8n_session_source = 'saved';
      } else if (operation === 'endpoint') {
        // DQ-13: the endpoint is the add-on's, kept by the default profile only.
        if (profile.id !== DEFAULT) return refuse(response, 409, 'endpoint_global');
        state.endpoint = payload.endpoint;
      }
      else if (operation === 'odoo/write-switches') {
        if (state.product !== 'odoo' || !state.odoo_write_switches ||
            JSON.stringify(odooSwitchPayload(state, payload.odoo_write_switches)) !== JSON.stringify(payload)) return json(response, 400, {});
        state.odoo_write_switches = structuredClone(payload.odoo_write_switches);
        state.odoo_write_switches_source = 'saved';
      }
      else if (operation === 'odoo/allowed-methods') {
        odooMethodsPayload(state,payload.odoo_allowed_methods.join('\n'));
        state.odoo_allowed_methods = structuredClone(payload.odoo_allowed_methods);
        state.odoo_allowed_methods_source = 'saved';
      }
      else if (operation === 'policy') {
        if (Object.keys(payload).sort().join() !== (config.operations ? 'denied_operations,disabled,enabled_write_tools,writes_enabled' : 'disabled,enabled_write_tools,writes_enabled')) return json(response, 400, {});
        Object.assign(state, payload);
      } else return json(response, 404, {});
      profile.revision++;
      return reply(response, 200, { saved: true }, profile, operation);
    }
    if (local.startsWith('/assets/')) {
      const filename = resolve(dist, `.${local}`);
      if (!filename.startsWith(`${resolve(dist)}${sep}`)) return json(response, 404, {});
      const types = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.eot': 'application/vnd.ms-fontobject' };
      response.writeHead(200, { 'Content-Type': types[extname(filename)] ?? 'application/octet-stream' });
      return response.end(await readFile(filename));
    }
    if (!['/', '/overview', '/backend', '/tools', '/access', '/diagnostics'].includes(local)) return json(response, 404, {});
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
