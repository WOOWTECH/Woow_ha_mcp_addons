// HM-11 (plan 6, 12.3 HM-11; contract 3, 4.1): the LOCAL MOCK (fixtures/server.mjs) answers every management call the
// panel makes with profiles, and every refusal it handles, as the add-on does. tests/profile-api-cases.json holds the
// cases with the shape the real 8099 app gives (tests/test_panel_profile_api_shapes.py checks the add-on against it);
// this spec checks the mock against the same file. No browser page: requests only (the same rules as the Python test).
import { readFileSync } from 'node:fs';
import { test, expect } from '../owned-fixture.mjs';

const CASES = JSON.parse(readFileSync(new URL('../profile-api-cases.json', import.meta.url), 'utf8'));
const RULES = CASES.rules;
const HEX24 = /^[0-9a-f]{24}$/;
const QUARANTINED = /^profiles\.json\.quarantine-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?$/;
const CLASSES = [[/^"p1-[0-9a-f]{64}"$/, '<etag:p1>'], [/^"c1-[0-9a-f]{64}"$/, '<etag:c1>'],
  [/^p1-[0-9a-f]{64}$/, '<revision:p1>'], [/^c1-[0-9a-f]{64}$/, '<revision:c1>']];

function etagClass(value) {
  if (value === undefined || value === null) return null;
  const found = CLASSES.slice(0, 2).find(([pattern]) => pattern.test(value));
  return found ? found[1].slice('<etag:'.length, -1) : 'other';
}
function shape(value, context, key = null) {
  if (Array.isArray(value)) return value.map(item => shape(item, context, key));
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, shape(item, context, name)]));
  if (typeof value === 'boolean' || value === null) return value;
  if (typeof value === 'number') return Number.isInteger(value) ? '<int>' : '<number>';
  if (value === 'default') return value;
  if (HEX24.test(value)) return `<${context.roles[value] ?? 'hex24'}>`;
  if (Object.hasOwn(context.keys, value)) return `<key:${context.keys[value]}>`;
  const found = CLASSES.find(([pattern]) => pattern.test(value));
  if (found) return found[1];
  if (QUARANTINED.test(value)) return '<quarantine-name>';
  return RULES.literal.includes(key) ? value : '<str>';
}
function projected(item, body) {
  if (item.keys === '*' || body === null || typeof body !== 'object' || Array.isArray(body)) return body;
  const names = {bootstrap: RULES.bootstrap_keys, 'bootstrap-profile': RULES.bootstrap_profile_keys}[item.keys] ?? item.keys;
  return Object.fromEntries(names.filter(name => Object.hasOwn(body, name)).map(name => [name, body[name]]));
}
async function observed(item, response, context) {
  const seen = {status: response.status(), etag: etagClass(response.headers().etag)};
  const text = await response.text();
  seen.body = (response.headers()['content-type'] ?? '').startsWith('application/json') ? shape(projected(item, JSON.parse(text)), context)
    : text === '' ? '<empty>' : '<text>';
  return seen;
}

// The fixture's state for a scenario (the cases file's setup). HM-12: backend_edit (parity046), an extra's saved
// connection and the identity change's failure (rebindFault).
// HM-13c: a restore (the guard's record of every profile, revoked; the quarantine directories it made; the notice of a
// kept token when there is no profile data), with the policy every profile copies from the default one.
const RESTORED_AT = '2026-11-16T09:30:15+00:00';
const restoredPolicy = policy => ({writes_enabled: true, disabled: [], enabled_write_tools: [], denied_operations: {},
  odoo_write_switches: null, odoo_allowed_methods: null, n8n_session: null, ...policy});
const restoredIdentity = {url: 'https://backend.example.invalid', database: 'DUMMY-db', username: 'DUMMY-user'};
function fixtureSetup(setup) {
  const ids = RULES.ids;
  if (setup.switched_off) return {product: setup.product, ...(setup.restore ? {restoreNotice: {at: RESTORED_AT}} : {})};
  const extra = spec => ({id: ids[spec.role], label: spec.label, configured: true, status: spec.status ?? 'unconfigured',
    ...(spec.disabled_reason ? {disabled_reason: spec.disabled_reason} : {}), ...(spec.blocked_reason ? {blocked_reason: spec.blocked_reason} : {}),
    ...(spec.required_memory_mib ? {required_memory_mib: spec.required_memory_mib} : {}), ...(spec.unavailable ? {unavailable: true} : {}),
    ...(spec.connection ? {connection: spec.connection} : {})});
  return {product: setup.product, ...(setup.backend_edit ? {parity046: true} : {}), profiles: {
    extra: [...setup.extras.map(extra), ...(setup.unavailable ?? []).map(spec => ({...extra(spec), disabled_reason: 'profile_unavailable', status: 'failed', unavailable: true}))],
    orphans: (setup.orphans ?? []).map(role => ids[role]),
    ...(setup.limit !== undefined ? {limit: setup.limit} : {}), ...(setup.file_budget === 'short' ? {limit: 0} : {}),
    ...(setup.available_memory_mib !== undefined ? {memory: {available_memory_mib: setup.available_memory_mib}} : {}),
    ...(setup.no_port ? {noPort: true} : {}), ...(setup.corrupt ? {indexCorrupt: true} : {}),
    ...(setup.no_index_file ? {indexCorrupt: true, noIndexFile: true} : {}),
    ...(setup.fault ? {rebindFault: setup.fault} : {}),
    ...(setup.restore ? {restore: {at: RESTORED_AT, rows: [{id: 'default', label: 'Default', token: 'revoked', identity: restoredIdentity,
      policy: restoredPolicy(setup.policy)}, ...setup.extras.map(spec => ({id: ids[spec.role], label: spec.label, token: 'revoked',
        identity: restoredIdentity, policy: restoredPolicy(setup.policy)}))]}} : {}),
    ...(setup.quarantine ? {quarantined: setup.quarantine.map(role => `${ids[role]}-20261116T093015Z`)} : {}),
  }};
}
const operationKey = () => `${Date.now() - 1000}.${Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('')}`;
function resolved(text, context) {
  let value = text;
  for (const [role, id] of Object.entries(context.ids)) value = value.replaceAll(`{${role}}`, id);
  for (const [key, name] of Object.entries(context.keys)) value = value.replaceAll(`{key:${name}}`, key);
  return value.replaceAll('{endpoint}', RULES.endpoint);
}
const profileValue = (spec, context) => Object.hasOwn(context.ids, spec) ? context.ids[spec] : resolved(spec, context);

class Rig {
  constructor(request, switchedOn) { this.request = request; this.switchedOn = switchedOn; }
  async bootstrap(profile = 'default') {
    const response = await this.request.get('/api/bootstrap', {headers: this.switchedOn ? {'X-MCP-Profile': profile} : {}});
    expect(response.status()).toBe(200);
    return response.json();
  }
  async indexEtag() {
    const response = await this.request.get('/api/profiles');
    expect(response.status()).toBe(200);
    return response.headers().etag;
  }
  async send(item, context) {
    const spec = item.request, headers = {};
    if (spec.profile !== undefined) headers['X-MCP-Profile'] = profileValue(spec.profile, context);
    const match = spec.if_match;
    if (match === 'index') headers['If-Match'] = await this.indexEtag();
    else if (match === 'raw') headers['If-Match'] = (await this.bootstrap()).profile_index_etag;
    else if (match?.startsWith('config:')) {
      const role = match.slice('config:'.length);
      headers['If-Match'] = `"${(await this.bootstrap(context.ids[role] ?? role)).configuration.revision}"`;
    } else if (match !== undefined) headers['If-Match'] = RULES[match.replace('-', '_')];
    // The CSRF value of the newest bootstrap (the mock takes only that one; the add-on takes any fresh one).
    if (spec.csrf) headers['X-CSRF-Token'] = (await this.bootstrap()).csrf;
    if (spec.key === 'new') { headers['Idempotency-Key'] = operationKey(); context.keys[headers['Idempotency-Key']] = item.name; }
    else if (spec.key !== undefined) headers['Idempotency-Key'] = Object.entries(context.keys).find(([, name]) => name === spec.key.slice('same:'.length))[0];
    const body = spec.body === undefined ? undefined : JSON.parse(resolved(JSON.stringify(spec.body), context));
    return this.request.fetch(resolved(spec.path, context), {method: spec.method, headers, ...(body === undefined ? {} : {data: body})});
  }
}

for (const scenario of CASES.scenarios) {
  test(`the mock answers the panel's cases as the add-on does: ${scenario.name}`, async ({request}) => {
    await (await request.post('/__fixture/reset', {data: fixtureSetup(scenario.setup)})).dispose();
    const ids = RULES.ids;
    const context = {ids: {...ids}, roles: Object.fromEntries(Object.entries(ids).map(([role, id]) => [id, role])), keys: {}};
    const rig = new Rig(request, !scenario.setup.switched_off);
    const seen = {}, expected = {};
    for (const item of scenario.cases) {
      const response = await rig.send(item, context);
      if (item.learn && [200, 201].includes(response.status())) {
        const learnt = (await response.json()).id;
        context.ids[item.learn] = learnt; context.roles[learnt] = item.learn;
      }
      // HM-13c: a quarantine directory's name, for a later path.
      if (item.learn_quarantine && response.status() === 200) context.ids[item.learn_quarantine] = (await response.json()).quarantined[0].name;
      seen[item.name] = await observed(item, response, context);
      expected[item.name] = item.expect;
      await response.dispose();
    }
    expect(seen).toEqual(expected);
  });
}
