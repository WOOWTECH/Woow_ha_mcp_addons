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
// HM-11: the multi-profile management API as HM-10 serves it (contract.md section 3; the real one is profile_router and
// profile_admin). Switched off (the default: config.profiles unset) every answer is the single-profile one, as before,
// X-MCP-Profile is ignored and /api/profiles... is an unknown operation (404, no body). Switched on (config.profiles:
// true or {extra: [...], orphans, limit, memory, noPort, indexCorrupt, noIndexFile, listStatus, noEtag}) every profile-scoped
// request needs exactly one X-MCP-Profile and every answer of a profile's action echoes it (the ETag of its revision
// too); /api/profiles lists (with the orphans), creates, renames and deletes profiles and quarantines an unusable index,
// with the add-on's order of checks. tests/profile-api-cases.json holds what the add-on answers (checked against the
// real app by tests/test_panel_profile_api_shapes.py) and tests/browser/profile-api-parity.spec.mjs checks this mock
// against the same cases.
// HM-13c (contract 3.1, 3.6, 4.1): config.restoreNotice ({at}: the default bootstrap's restore_notice until the default
// profile's token changes, switched on or off; HM-12's identity change that rotates it too), config.dormantProfiles (a switched-off bootstrap's dormant_profiles) and,
// switched on, config.profiles.restore ({at, dormantAt, rows: [{id, label, token, identity, policy, reviewed_at}],
// broken}: the guard's record, GET profiles/restore-record, POST profiles/<id>/restore-review, the bootstrap's
// restore_review and restore_review_required, the token/rotate gate), config.profiles.quarantined (names: the list's
// "quarantined", POST profiles/quarantine/<name>/delete) and POST profiles/revoke-all (config.profiles.revokeFail: ids
// whose revocation fails once: 409 operation_outcome_unknown with the results; config.profiles.revokeOutcome, once:
// 'unstarted' (its marker could not be saved: nothing revoked, no result) or 'unfinished' (every profile revoked, its
// end not done), both 409 operation_outcome_unknown, as tests/test_restore_review.py has the add-on answer them).
const DEFAULT = 'default';
const PROFILE = /^(?:default|[0-9a-f]{24})$/;
const OPERATION = /^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/;
// Synthetic low-entropy tokens, one letter per profile (test data rule, plan 12.0 item 4).
const TOKEN_LETTERS = ['T', 'U', 'V', 'W', 'X', 'Y'];
// HM-12 (DQ-05, DQ-40 ⑨ (a); contract 3.1, 4.1), switched on only: a backend save as the add-on answers it.
// - backend/patch moving a URL to another origin (scheme, host, effective port) without the stored secrets that URL takes
//   there: 422 CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN after If-Match, nothing saved (every product; the table and
//   the origin are written here independently of the panel's urlSecrets and urlOrigin).
// - Odoo, the product whose token is bound to its backend identity: a save that changes url, database or username of a
//   complete saved connection (a cleared one too) while the token is active rotates the token in the same save (the
//   next letter of ROTATION_LETTERS; its mask and a rotate entry in the history where the state has them) and answers
//   {saved, token_rotated: true, configuration} with the echo and the new ETag. config.profiles.rebindFault ('stop',
//   'write' or 'start'; for the next such save only) answers as the add-on's failed identity change: 503 {"error":
//   "request denied"} or {"error":"state unavailable"} with nothing saved, or shape D with token_rotated (saved, the new
//   child not started: apply_state failed).
// - config.saveCode with config.saveStatus: the refusal says that code (the add-on's refusals carry no echo).
const URL_SECRETS = {odoo: {url: ['password']}, 'odoo-manage': {url: ['api_key']}, n8n: {url: ['key', 'mcp_access_token']},
  hermes: {gateway_url: ['gateway_api_key'], dashboard_url: ['dashboard_password']}, opendesign: {url: []},
  emqx: {url: ['api_key', 'api_secret']}, litellm: {url: ['master_key']}, nextcloud: {url: ['app_password']}, headscale: {url: ['api_key']}};
const IDENTITY = ['url', 'database', 'username'];
const ROTATION_LETTERS = ['N', 'P', 'Q', 'R'];
let config, calls, reads, nonce, profiles, index, orphans, rotations, defaults = {};
let restoreRows, quarantined, revokeFail, revokeOutcome;
const QUARANTINE = /^([0-9a-f]{24})-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?$/;
const REVIEWED_AT = '2026-11-16T10:00:00+00:00';
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
// HM-12: where a URL's requests go (scheme, host, effective port), as urlsplit reads the URL; another spelling of a host
// is another origin.
function originOf(url) {
  const found = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)/.exec(url);
  if (!found) return null;
  const scheme = found[1].toLowerCase(), hostinfo = found[2].split('@').at(-1);
  const bracketed = /^\[([^\]]*)\](?::(.*))?$/.exec(hostinfo);
  const [host, port] = bracketed ? [bracketed[1], bracketed[2] ?? ''] : [hostinfo.split(':')[0], hostinfo.split(':').slice(1).join(':')];
  return `${scheme} ${host.toLowerCase()} ${port === '' ? {http: 80, https: 443}[scheme] : Number(port)}`;
}
// Whether a backend/patch moves a stored URL to another origin without a stored secret that URL takes there.
function newOriginRefused(state, changes) {
  for (const [url, secrets] of Object.entries(URL_SECRETS[state.product] ?? {})) {
    const before = state.backend_edit.values[url];
    if (typeof before !== 'string' || typeof changes[url] !== 'string' || originOf(before) === originOf(changes[url])) continue;
    if (secrets.some(secret => state.backend_edit.secret_set[secret] && !Object.hasOwn(changes, secret))) return true;
  }
  return false;
}
// A saved Odoo identity (url, database, username), or null when the saved connection is not complete.
const identityOf = (configured, connection) => configured && IDENTITY.every(key => typeof connection?.[key] === 'string')
  ? Object.fromEntries(IDENTITY.map(key => [key, connection[key]])) : null;
const masked = letter => `${letter.repeat(4)}${'*'.repeat(20)}${letter.repeat(4)}`;
function rotate(profile) {
  const state = profile.state, previous = profile.token;
  profile.token = ROTATION_LETTERS[rotations++ % ROTATION_LETTERS.length];
  if (Object.hasOwn(state, 'token_masked')) state.token_masked = masked(profile.token);
  if (Object.hasOwn(state, 'token_history')) {
    state.token_history = [{action: 'rotate', rotated_at: '2026-11-17T00:00:00+00:00', previous_token_masked: masked(previous)}, ...state.token_history].slice(0, 5);
  }
}
const switchedOn = () => Boolean(config.profiles);
const profileConfig = () => typeof config.profiles === 'object' && config.profiles !== null ? config.profiles : {};
function reset(next = {}) {
  config = {...defaults, ...next};
  calls = [];
  reads = [];
  nonce = 0;
  rotations = 0;
  profiles = new Map([[DEFAULT, {id: DEFAULT, label: 'Default', port: 3000, token: 'M', state: profileState(config),
    revision: 1, receipts: new Map(), status: 'running', disabled_reason: null, blocked_reason: null,
    identity: identityOf(config.configured, config.connection)}]]);
  index = {revision: 1, receipts: new Map(), created: 0, quarantined: 0};
  orphans = new Set(profileConfig().orphans ?? []);  // profile directories the index does not list (DQ-14)
  for (const spec of profileConfig().extra ?? []) addProfile(spec);
  // HM-13c: the guard's record rows (their reviews change), the quarantine directories, the failures of "revoke all".
  restoreRows = structuredClone(profileConfig().restore?.rows ?? []);
  quarantined = new Set(profileConfig().quarantined ?? []);
  revokeFail = new Set(profileConfig().revokeFail ?? []);
  revokeOutcome = profileConfig().revokeOutcome ?? null;
  for (const row of restoreRows) { const profile = profiles.get(row.id); if (profile && ['revoked', 'already_revoked'].includes(row.token)) profile.state.token_active = false; }
}
// The guard's record (contract 3.6), as the add-on reads it back.
function mockRecord() {
  const spec = profileConfig().restore;
  if (!spec) return null;
  return {version: 1, restore: spec.at ? {at: spec.at, marker: true, sentinel: 'consistent'} : null,
    dormant: spec.dormantAt ? {at: spec.dormantAt} : null, index: 'ok',
    profiles: restoreRows.map(row => ({id: row.id, label: row.label ?? null, is_default: row.id === DEFAULT, token: row.token,
      identity: structuredClone(row.identity ?? {}), policy: structuredClone(row.policy ?? {}), reviewed_at: row.reviewed_at ?? null})),
    quarantined: [...quarantined].sort().map(name => ({name: `.quarantine-${name}`, id: name.slice(0, 24), new: true})),
    profiles_directory: 'present', other_entries: 0};
}
const gated = profile => restoreRows.some(row => row.id === profile.id && ['revoked', 'already_revoked'].includes(row.token) && !row.reviewed_at);
function reviewSummary() {
  const spec = profileConfig().restore;
  if (!spec) return null;
  if (spec.broken) return {pending: null, restore_at: null, dormant_at: null};
  // The profiles that still exist: an index the add-on cannot use lists none (only the default profile counts then).
  const pending = restoreRows.filter(row => ['revoked', 'already_revoked'].includes(row.token) && !row.reviewed_at
    && (row.id === DEFAULT || !indexCorrupt() && profiles.has(row.id))).length;
  return pending ? {pending, restore_at: spec.at ?? null, dormant_at: spec.dormantAt ?? null} : null;
}
// DQ-12: an index the add-on cannot use (corrupt, or replaced behind its back) until it is quarantined.
const indexCorrupt = () => Boolean(profileConfig().indexCorrupt) && index.quarantined === 0;
// DQ-28: OpenDesign and Odoo Manage never have additional profiles (the bootstrap's profiles_supported).
const supportsProfiles = () => !['opendesign', 'odoo-manage'].includes(profiles.get(DEFAULT).state.product);
// DQ-02: a new profile copies the default profile's policy as it is now; its connection is empty and its token new.
function addProfile(spec = {}) {
  const base = profiles.get(DEFAULT).state;
  const id = spec.id ?? `e${(++index.created).toString(16).padStart(7, '0')}${'f'.repeat(16)}`;
  const next = {...config, ownerDefaults: undefined, endpoint: null, connection: spec.connection, configured: spec.configured ?? false};
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
    blocked_reason: spec.blocked_reason ?? null, unavailable: spec.unavailable === true, identity: identityOf(spec.configured, spec.connection),
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
// The unusable index file's own ETag (the default bootstrap's profile_index_etag): only the quarantine takes it.
const rawEtag = () => `"p1-f${index.revision.toString(16).padStart(63, '0')}"`;
const configuration = profile => ({revision: etag(profile).slice(1, -1), saved_revision: 'launch-fixture',
  applied_revision: config.applyState === 'pending' || config.applyState === 'failed' ? null : 'launch-fixture',
  apply_state: config.applyState ?? 'applied', last_error_code: config.applyState === 'failed' ? 'child_start_failed' : null});
const json = (response, status, value, headers = {}) => { response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers }); response.end(JSON.stringify(value)); };
const refuse = (response, status, code, extra = {}) => json(response, status, {error: 'request denied', detail: {code, ...extra}});
// The echo (contract 3.4): every JSON answer of a profile's action names the profile (an answer it refuses with, as
// the add-on raises them, does not: refuse); the bootstrap the whole echo,
// profiles_supported and, for the default profile, the index's state. config.wrongEcho = {operation, id} makes one
// operation name another profile, to test that the panel shows nothing of such an answer. Every such answer carries the
// ETag of the profile's revision, as the add-on's action sets it (switched off too: only that header is new there).
function reply(response, status, value, profile, operation) {
  if (!switchedOn()) return json(response, status, value, {ETag: etag(profile)});
  const id = config.wrongEcho?.operation === operation ? config.wrongEcho.id : profile.id;
  const review = profile.id === DEFAULT ? reviewSummary() : null;
  const echo = operation === 'bootstrap' ? {profile: {id, label: profiles.get(id)?.label ?? profile.label, is_default: id === DEFAULT},
    profiles_supported: supportsProfiles(), ...(profile.id === DEFAULT ? {profile_index_state: indexCorrupt() ? 'corrupt' : 'ok',
      ...(indexCorrupt() ? {profile_index_etag: rawEtag()} : {})} : {}),
    ...(review ? {restore_review: review} : {}), ...(gated(profile) ? {restore_review_required: true} : {})}
    : {profile: {id}};
  return json(response, status, {...value, ...echo}, {ETag: etag(profile)});
}
// contract 3.3: exactly one X-MCP-Profile, default or 24 lowercase hex, an existing profile; never a fallback.
function scoped(request, response) {
  if (!switchedOn()) return profiles.get(DEFAULT);
  const value = request.headers['x-mcp-profile'];
  if (value === undefined) { refuse(response, 400, 'profile_id_required'); return null; }
  if (value.includes(',') || !PROFILE.test(value)) { refuse(response, 400, 'profile_id_invalid'); return null; }
  if (value === DEFAULT) return profiles.get(DEFAULT);
  // HM-10's order: an unusable index first (whatever the id), then the index, then the profile's state.
  if (indexCorrupt()) { refuse(response, 503, 'profile_index_corrupt'); return null; }
  const profile = profiles.get(value);
  if (!profile) { refuse(response, 404, 'profile_not_found'); return null; }
  // A profile whose state cannot be read (contract 3.3): 503 state unavailable; it can still be deleted.
  if (profile.unavailable) { json(response, 503, {error: 'state unavailable'}); return null; }
  return profile;
}
const header = request => request.headers['x-mcp-profile'] === undefined ? {} : {profileHeader: request.headers['x-mcp-profile']};
const row = profile => ({id: profile.id, label: profile.label, port: profile.port, is_default: profile.id === DEFAULT,
  disabled_reason: profile.disabled_reason, ...(profile.disabled_reason === 'memory_capacity' ? {required_memory_mib: profile.required_memory_mib ?? 1156} : {}),
  status: profile.status, blocked_reason: profile.blocked_reason});
// Labels (contract 3.6; DQ-16): the server's rule, written here independently of the panel's: 1-80 code points once
// trimmed, no control, format, separator, surrogate, private-use or unassigned character (422); NFKC + casefold for
// duplicates, default and 預設帳號 reserved (409).
const key = label => label.normalize('NFKC').toLowerCase().normalize('NFKC');
const labelInvalid = label => [...label].length < 1 || [...label].length > 80 || /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}\p{Co}\p{Cn}]/u.test(label);
const labelTaken = (label, except = null) => ['default', '預設帳號'].includes(key(label))
  || [...profiles.values()].some(profile => profile.id !== except && profile.id !== DEFAULT && key(profile.label) === key(label));
// The global paths (contract 3.1; HM-10's ProfileAdmin), in the add-on's order of checks: the identity (CSRF on a
// write; 403), the method table (405) and the request's shape ({"label": <string>}, the path's id: a fixed 400), then
// an unusable index (503 profile_index_corrupt; the quarantine aside), If-Match (428; a malformed or stale one 409
// config_conflict with the current ETag), Idempotency-Key (428; malformed 400; a replay answers what was done, before
// the ETag is compared; another request under the same key 409 operation_id_conflict), and each route's own checks.
const ROUTES = {'': ['GET', 'POST'], 'index/quarantine': ['POST'], 'revoke-all': ['POST'], 'restore-record': ['GET']};
const conflict = (response, current) => json(response, 409, {detail: {code: 'config_conflict'}}, {ETag: current});
const answer = (response, status, value) => json(response, status, value, {ETag: indexEtag()});
const receiptOf = (operationId, kind) => ({id: operationId, kind, state: 'completed', replayed: false});
async function profileRoutes(request, response, local) {
  const rest = local === '/api/profiles' ? '' : local.slice('/api/profiles/'.length);
  // HM-13c: profiles/<id>/restore-review and profiles/quarantine/<name>/delete (POST only).
  const review = /^([^/]+)\/restore-review$/.exec(rest), sweep = /^quarantine\/([^/]+)\/delete$/.exec(rest);
  const id = Object.hasOwn(ROUTES, rest) || sweep ? null : review ? review[1] : rest;
  const allowed = Object.hasOwn(ROUTES, rest) ? ROUTES[rest] : review || sweep ? ['POST'] : ['PATCH', 'DELETE'];
  const payload = await body(request);
  const write = request.method !== 'GET';
  const validCsrf = request.headers['x-csrf-token'] === `mock_fresh_csrf_value_${nonce}`;
  const operationId = request.headers['idempotency-key'];
  const ifMatch = request.headers['if-match'];
  if (write) calls.push({operation: rest === '' ? 'profiles' : `profiles/${rest}`, method: request.method, validCsrf, ifMatch,
    ...(operationId ? {operationId} : {}), fields: Object.keys(payload ?? {}), ...(payload?.label !== undefined ? {label: payload.label} : {}), ...header(request)});
  if (write && (!validCsrf || config.deniedSave)) return json(response, 403, {error: 'request denied'});
  if (id !== null && id.includes('/')) return answer404(response);  // an unknown operation under profiles/
  if (!allowed.includes(request.method)) { response.writeHead(405, {'Content-Type': 'text/plain; charset=utf-8', Allow: allowed.join(', ')}); return response.end('Method Not Allowed'); }
  const labelled = request.method === 'PATCH' || request.method === 'POST' && rest === '';
  if (labelled ? !payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).join() !== 'label' || typeof payload.label !== 'string'
      : payload !== null) return json(response, 400, {error: 'request denied'});
  if (id !== null && !PROFILE.test(id)) return json(response, 400, {error: 'request denied'});
  if (sweep && !QUARANTINE.test(sweep[1])) return json(response, 400, {error: 'request denied'});
  if (request.method === 'GET' && rest === 'restore-record') {
    if (profileConfig().restore?.broken) return json(response, 503, {error: 'state unavailable'});
    return json(response, 200, {record: mockRecord()}, {ETag: indexCorrupt() ? rawEtag() : indexEtag()});
  }
  if (request.method === 'GET') {
    if (indexCorrupt()) return refuse(response, 503, 'profile_index_corrupt');
    if (profileConfig().listStatus) return json(response, profileConfig().listStatus, {error: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER'});
    reads.push({operation: 'profiles', ...header(request)});  // reads are not calls: specs count calls
    // noEtag: the header lost on the way (HM-03a measures whether the Ingress keeps it).
    const list = {profiles: [...profiles.values()].map(row), orphans: [...orphans].sort().map(item => ({id: item}))};
    if (quarantined.size) list.quarantined = [...quarantined].sort().map(name => ({name, id: name.slice(0, 24)}));
    return json(response, 200, list, profileConfig().noEtag ? {} : {ETag: indexEtag()});
  }
  const quarantine = rest === 'index/quarantine', revokeAll = rest === 'revoke-all';
  if (indexCorrupt() && !quarantine && !revokeAll) return refuse(response, 503, 'profile_index_corrupt');
  const current = (quarantine || revokeAll) && indexCorrupt() ? rawEtag() : indexEtag();
  if (!ifMatch) return refuse(response, 428, 'config_revision_required');
  if (!/^"p1-[0-9a-f]{64}"$/.test(ifMatch)) return conflict(response, current);
  const kind = quarantine ? 'profile.index_quarantine' : revokeAll ? 'profile.revoke_all' : review ? 'profile.restore_review'
    : sweep ? 'profile.quarantine_delete' : request.method === 'POST' ? 'profile.create' : request.method === 'DELETE' ? 'profile.delete' : null;
  if (kind) {
    if (!operationId) return refuse(response, 428, 'operation_id_required');
    if (!OPERATION.test(operationId) || Number(operationId.split('.')[0]) > Date.now()) return refuse(response, 400, 'operation_id_invalid');
    const prior = index.receipts.get(operationId);
    if (prior) {
      const subject = kind === 'profile.create' ? payload.label : ['profile.delete', 'profile.restore_review'].includes(kind) ? id
        : kind === 'profile.quarantine_delete' ? sweep[1] : null;
      if (prior.kind !== kind || prior.request !== subject) return refuse(response, 409, 'operation_id_conflict');
      const replayed = {...prior.operation, replayed: true};
      if (prior.operation.state !== 'completed') return refuse(response, 409, 'operation_outcome_unknown', {operation: replayed});
      if (kind === 'profile.create') return answer(response, 200, {...(profiles.has(prior.target) ? row(profiles.get(prior.target)) : {id: prior.target}), operation: replayed});
      if (kind === 'profile.delete') return answer(response, 200, {deleted: prior.target, operation: replayed});
      if (kind === 'profile.revoke_all') return json(response, 200, {revoked: 'all', operation: replayed}, {ETag: current});
      if (kind === 'profile.restore_review') return answer(response, 200, {reviewed: prior.target, reviewed_at: restoreRows.find(item => item.id === prior.target)?.reviewed_at ?? null, operation: replayed});
      if (kind === 'profile.quarantine_delete') return answer(response, 200, {deleted: prior.target, operation: replayed});
      return answer(response, 200, {quarantined: prior.target, operation: replayed});
    }
  }
  if (ifMatch !== current) return conflict(response, current);
  if (revokeAll) {
    // Every profile (the default one first, then the profile directories by id): failed ones once (revokeFail), the
    // others revoked; the default profile's restore notice goes with its token.
    const ids = [DEFAULT, ...[...[...profiles.keys()].filter(item => item !== DEFAULT), ...orphans].sort()];
    const results = revokeOutcome === 'unstarted' ? []
      : ids.map(item => ({id: item, result: revokeFail.has(item) ? 'failed' : 'revoked'}));
    for (const item of results) if (item.result === 'revoked' && profiles.has(item.id)) { profiles.get(item.id).state.token_active = false; profiles.get(item.id).revision++; }
    if (results[0]?.result === 'revoked') config.restoreNotice = undefined;
    const failed = revokeFail.size > 0 || revokeOutcome !== null;
    revokeFail = new Set();
    revokeOutcome = null;
    const operation = {...receiptOf(operationId, kind), ...(failed ? {state: 'unknown'} : {})};
    index.receipts.set(operationId, {kind, request: null, target: 'all', operation});
    if (failed) return refuse(response, 409, 'operation_outcome_unknown', {operation, results});
    return json(response, 200, {revoked: 'all', results, operation}, {ETag: current});
  }
  if (review) {
    const found = restoreRows.find(item => item.id === id);
    if (!found || (id !== DEFAULT && !profiles.has(id))) return refuse(response, 404, 'profile_not_found');
    found.reviewed_at ??= REVIEWED_AT;
    const operation = receiptOf(operationId, kind);
    index.receipts.set(operationId, {kind, request: id, target: id, operation});
    return answer(response, 200, {reviewed: id, reviewed_at: found.reviewed_at, operation});
  }
  if (sweep) {
    if (!quarantined.delete(sweep[1])) return refuse(response, 404, 'profile_not_found');
    const operation = receiptOf(operationId, kind);
    index.receipts.set(operationId, {kind, request: sweep[1], target: sweep[1], operation});
    return answer(response, 200, {deleted: sweep[1], operation});
  }
  if (quarantine) {
    // Only an unusable index with its file is moved aside: every profile directory's token revoked, each one an orphan.
    if (!indexCorrupt() || profileConfig().noIndexFile) return conflict(response, current);
    for (const profile of [...profiles.values()].filter(item => item.id !== DEFAULT)) { profiles.delete(profile.id); orphans.add(profile.id); }
    index.quarantined++;
    index.revision++;
    const name = `profiles.json.quarantine-20261116T000000Z${index.quarantined > 1 ? `-${index.quarantined}` : ''}`;
    const operation = receiptOf(operationId, kind);
    index.receipts.set(operationId, {kind, request: null, target: name, operation});
    return answer(response, 200, {quarantined: name, operation});
  }
  if (request.method === 'POST') {
    const label = payload.label.trim();
    if (labelInvalid(label)) return refuse(response, 422, 'profile_label_invalid');
    if (!supportsProfiles()) return refuse(response, 409, 'profile_product_unsupported');
    const limit = profileConfig().limit ?? 5;
    if (profiles.size - 1 >= limit) return refuse(response, 409, 'profile_limit_reached', {limit});
    const memory = profileConfig().memory;
    if (memory) return refuse(response, 409, 'profile_memory_insufficient', {limit: profiles.size - 1, required_memory_mib: 356, available_memory_mib: memory.available_memory_mib ?? 300});
    if (labelTaken(label)) return refuse(response, 409, 'profile_label_conflict');
    if (profileConfig().noPort) return refuse(response, 409, 'profile_port_unavailable');
    const created = addProfile({label});
    index.revision++;
    const operation = receiptOf(operationId, kind);
    index.receipts.set(operationId, {kind, request: payload.label, target: created.id, operation});
    if (config.createToken) return answer(response, 201, {...row(created), operation, token: `${created.token}`.repeat(43)});
    return answer(response, 201, {...row(created), operation});
  }
  if (id === DEFAULT) return refuse(response, 422, 'profile_default_immutable');
  if (request.method === 'PATCH') {
    if (!profiles.has(id)) return refuse(response, 404, 'profile_not_found');
    const label = payload.label.trim();
    if (labelInvalid(label)) return refuse(response, 422, 'profile_label_invalid');
    if (labelTaken(label, id)) return refuse(response, 409, 'profile_label_conflict');
    profiles.get(id).label = label;
    index.revision++;
    return answer(response, 200, row(profiles.get(id)));
  }
  // DELETE (DQ-14: the token is revoked and the credentials wiped first; a mock: the profile is simply gone). An orphan
  // or a profile whose state cannot be read is deleted the same way.
  if (!profiles.has(id) && !orphans.has(id)) return refuse(response, 404, 'profile_not_found');
  if (profiles.delete(id)) index.revision++;
  orphans.delete(id);
  const operation = receiptOf(operationId, kind);
  index.receipts.set(operationId, {kind, request: id, target: id, operation});
  return answer(response, 200, {deleted: id, operation});
}
const answer404 = response => { response.writeHead(404); response.end(); };
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
    // Switched off the profile routes do not exist (contract 1.2: an unknown operation, 404 without a body).
    if (local === '/api/profiles' || local.startsWith('/api/profiles/')) return switchedOn() ? await profileRoutes(request, response, local) : answer404(response);
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
        // With profiles the endpoint is the add-on's (the default profile's, DQ-13); the echo adds the index state.
        ...(switchedOn() ? {endpoint: profiles.get(DEFAULT).state.endpoint} : {}),
        // HM-13b, HM-13c: dormant profiles of a switched-off add-on; a restore that kept the default profile's token.
        ...(!switchedOn() && config.dormantProfiles !== undefined ? {dormant_profiles: config.dormantProfiles} : {}),
        ...(profile.id === DEFAULT && config.restoreNotice ? {restore_notice: structuredClone(config.restoreNotice)} : {}) }, profile, 'bootstrap');
    }
    if (local.startsWith('/api/operations/')) {
      if (config.deniedSave) return json(response, 403, {});
      const profile = scoped(request, response);
      if (!profile) return;
      const saved=profile.receipts.get(local.slice('/api/operations/'.length));
      if (saved) return reply(response,200,{operation:saved.operation,result:{status:'ok'}},profile,'operations');
      return switchedOn() ? refuse(response, 404, 'operation_not_found') : json(response,404,{detail:{code:'operation_not_found'}});
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
      if (config.saveStatus) return json(response, config.saveStatus, switchedOn() && config.saveCode
        ? {error: 'request denied', detail: {code: config.saveCode}, untrusted: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER'} : { error: 'MOCK PRIVATE_CANARY_MUST_NOT_RENDER' });
      const kind={'token/rotate':'token.rotate','token/revoke':'token.revoke','child/restart':'mcp.restart'}[operation];
      const operationId=request.headers['idempotency-key'];
      if (kind && receipts.has(operationId)) {
        const prior=receipts.get(operationId);
        if(prior.operation.kind!==kind)return json(response,409,{detail:{code:'operation_id_conflict'}});
        return reply(response,200,{status:'ok',operation:{...prior.operation,replayed:true}},profile,operation);
      }
      if (!['token/reveal','backend/test'].includes(operation) && !request.headers['if-match']) return switchedOn() ? refuse(response, 428, 'config_revision_required') : json(response,428,{detail:{code:'config_revision_required'}});
      if (request.headers['if-match'] && request.headers['if-match'] !== etag(profile)) return reply(response, 409, {detail: {code: 'config_conflict'}, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER'}, profile, operation);
      if (operation === 'backend/test') return reply(response,200,{tested_configuration:'saved',backend:'reachable',health:state.health},profile,operation);
      if (operation === 'owner-defaults/restore' || operation === 'owner-defaults/dismiss') {
        // MOCK of the server rules: POST, no body, If-Match of the reviewed revision, a pending marker.
        if (request.method !== 'POST' || payload !== null) return json(response, 400, { error: 'MOCK notice contract' });
        if (!request.headers['if-match']) return switchedOn() ? refuse(response, 428, 'config_revision_required') : json(response, 428, { detail: { code: 'precondition_required' } });
        if (request.headers['if-match'] !== etag(profile)) return reply(response, 409, { detail: { code: 'config_conflict' }, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER' }, profile, operation);
        const view = state.owner_defaults;
        const restoring = operation.endsWith('/restore');
        if (!view || view.restored_at || (restoring ? !view.restore?.available : view.acknowledged_at)) {
          // An additional profile never has the notice (FM-08): the same refusal, its echo with it (the add-on's action returns it).
          return reply(response, 409, { error: 'owner_defaults_unavailable', detail: { code: 'owner_defaults_unavailable' }, untrusted: 'PRIVATE_CANARY_MUST_NOT_RENDER' }, profile, operation);
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
      // HM-13c (contract 4.1): a profile whose token the restore guard revoked gets a new one once it was reviewed.
      if (operation === 'token/rotate' && switchedOn() && gated(profile)) return refuse(response, 409, 'restore_review_required');
      let receipt;
      if(kind){
        if(!/^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/.test(operationId??''))return json(response,428,{detail:{code:'operation_id_required'}});
        receipt={id:operationId,kind,state:'completed',replayed:false};
        receipts.set(operationId,{operation:receipt});
      }
      // HM-09: with profiles the restart answer says why the child is not started now (null: it is).
      if (operation === 'child/restart') return reply(response,202,{status:'ok',operation:receipt,accepted:true,apply_state:'pending',...(switchedOn() ? {blocked_reason: profile.blocked_reason ?? null} : {})},profile,operation);
      if (operation.startsWith('token/')) {
        if (request.method !== 'POST' || payload !== null) return json(response, 400, { error: 'MOCK token contract' });
        // HM-13c: the default profile's token changing ends the restore notice (a revoke only when it revoked one).
        if (profile.id === DEFAULT && (operation === 'token/rotate' || operation === 'token/revoke' && state.token_active)) config.restoreNotice = undefined;
        if (operation === 'token/revoke') { state.token_active = false; profile.revision++; return reply(response,200,{status:'ok',operation:receipt},profile,operation); }
        if (operation === 'token/rotate') {state.token_active = true; profile.revision++;}
        return reply(response, 200, { ...(receipt ? {status:'ok',operation:receipt} : {}), token: state.token_active ? profile.token.repeat(43) : null }, profile, operation);
      }
      if (request.method !== 'PUT') return json(response, 405, {});
      // HM-12: the identity a backend save leaves (null: cleared), when it moves a switched-on Odoo token, and the
      // failure armed for it.
      let rebound = false, fault;
      const rebinds = next => {
        rebound = switchedOn() && state.product === 'odoo' && state.token_active && profile.identity !== null
          && (next === null || IDENTITY.some(key => next[key] !== profile.identity[key]));
        fault = rebound ? profileConfig().rebindFault : undefined;
        if (fault) delete config.profiles.rebindFault;
        return fault === 'stop' ? {error: 'request denied'} : fault === 'write' ? {error: 'state unavailable'} : null;
      };
      if (operation === 'backend') {
        const connection = state.product === 'n8n' ? payload : payload.connection;
        const clear = state.product === 'n8n' ? connection?.url === null && connection?.key === null : connection === null;
        if (!clear) backendPayload(state.product, 'replace', connection);
        if (JSON.stringify(payload) !== JSON.stringify(clear ? backendPayload(state.product, 'clear') : backendPayload(state.product, 'replace', connection))) return json(response, 400, {});
        if (switchedOn()) {
          const next = clear ? null : identityOf(true, connection), failed = rebinds(next);
          if (failed) return json(response, 503, failed);
          profile.identity = next;
        }
        state.connection_configured = !clear;
      } else if (operation === 'backend/patch') {
        if (!config.parity046 || !state.connection_configured || !request.headers['if-match']) return json(response,400,{});
        if (switchedOn()) {
          if (newOriginRefused(state, payload.changes)) return refuse(response, 422, 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN');
          const next = profile.identity && {...profile.identity, ...Object.fromEntries(IDENTITY.filter(key => Object.hasOwn(payload.changes, key)).map(key => [key, payload.changes[key]]))};
          const failed = next ? rebinds(next) : null;
          if (failed) return json(response, 503, failed);
          if (next) profile.identity = next;
        }
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
      if (rebound) {
        rotate(profile);
        // HM-13c with HM-12: the default profile's kept token is the backup's no more, so its restore notice ends.
        if (profile.id === DEFAULT) config.restoreNotice = undefined;
        if (fault === 'start') {
          config.applyState = 'failed';
          return reply(response, 503, {saved: true, token_rotated: true, detail: {code: 'config_apply_failed'}, configuration: configuration(profile)}, profile, operation);
        }
        return reply(response, 200, {saved: true, token_rotated: true, configuration: configuration(profile)}, profile, operation);
      }
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
