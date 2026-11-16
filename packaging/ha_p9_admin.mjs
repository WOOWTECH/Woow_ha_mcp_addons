// The P9 operator kit uses the same strict write contract as the management UI.
// Only operation identity is retained in memory. Tokens never enter this store.
// HM-11 (plan 6, 12.3): the panel's AdminApi finds out whether the app serves profiles and then names the profile in
// X-MCP-Profile on every profile-scoped request (the default profile explicitly; a run against one additional profile
// passes {profile}). The caller's headers can never carry X-MCP-Profile: only AdminApi decides which profile is asked.
import { AdminApi } from '../packages/mcp-admin-ui/src/api.js';

export function createP9AdminClient(ingress, headers, fetcher = globalThis.fetch.bind(globalThis), { profile } = {}) {
  if (Object.keys(headers ?? {}).some(name => name.toLowerCase() === 'x-mcp-profile')) {
    throw new Error('X-MCP-Profile is chosen by the admin client (pass {profile}), never by the caller headers');
  }
  const base = new URL(ingress);
  const records = new Map();
  const storage = {
    getItem: key => records.get(key) ?? null,
    setItem: (key, value) => records.set(key, value),
    removeItem: key => records.delete(key),
  };
  const transport = (path, options) => fetcher(new URL(path, base), {
    ...options, headers: { ...headers, ...options.headers },
  });
  return new AdminApi(base.pathname.replace(/\/$/, ''), transport, storage, profile === undefined ? {} : { profile });
}

// HM-16 (FM-107; plan 12.3 HM-16): the kit's profile flows. Every line the kit prints names a profile by its log id
// (default, or the first 8 characters of its id), never by its name, and never shows a token.
export const logId = profile => (profile === 'default' ? 'default' : String(profile).slice(0, 8));

// The profile's MCP token (token/reveal under its own X-MCP-Profile), or null when it has none (revoked).
export async function revealToken(client) {
  const fresh = await client.bootstrap();
  const result = await client.mutate('token/reveal', undefined, fresh.configuration?.revision);
  return typeof result?.token === 'string' && result.token ? result.token : null;
}

// One line of ha_p9_probe.py's cross mode: the profile's log id, live or gone, its token.
export const crossLine = (profile, kind, token) => `${logId(profile)}\t${kind}\t${token}\n`;

// The cross mode's input for these profiles: each one's token, revealed under its own profile; a profile without an
// active token is left out, and reported by its log id.
export async function crossLines(clientFor, profiles, report = () => {}) {
  let lines = '';
  for (const profile of profiles) {
    const token = await revealToken(clientFor(profile));
    if (token === null) {
      report(`profile ${logId(profile)}: no active token; left out of the cross matrix`);
      continue;
    }
    lines += crossLine(profile, 'live', token);
  }
  return lines;
}

export function temporaryLabel() {
  return 'p9-temp-' + Array.from(globalThis.crypto.getRandomValues(new Uint8Array(4)), byte => byte.toString(16).padStart(2, '0')).join('');
}

// An unconfirmed profile operation stops the run: its public identity is reported, it is never sent again here.
function stopUnconfirmed(admin, report) {
  const pending = admin.pendingProfileOperation();
  if (pending) report(`unconfirmed profile operation; check the profile list and its receipt before another run: ${pending.id} ${pending.route}`);
}

// The temporary profile mode (PaaS public_probe --temp-profile): create a profile with the index revision of the list
// just read, run(id, its client), then delete it with a fresh revision, also when run failed. A create or delete
// whose outcome is unknown stops at once with its identity reported; nothing is retried.
export async function withTemporaryProfile(admin, clientFor, run, { label = temporaryLabel(), report = () => {} } = {}) {
  await admin.bootstrap();
  const list = await admin.profileList();
  if (list.revision === null) throw new Error('the profile list carries no index revision; no temporary profile is created');
  let created;
  try {
    created = await admin.createProfile(label, list.revision);
  } catch (error) {
    stopUnconfirmed(admin, report);
    throw error;
  }
  let outcome;
  try {
    outcome = await run(created.id, clientFor(created.id));
  } finally {
    try {
      const again = await admin.profileList();
      if (again.revision === null) throw new Error('the profile list carries no index revision; the temporary profile is not deleted');
      await admin.deleteProfile(created.id, again.revision);
    } catch (error) {
      stopUnconfirmed(admin, report);
      report(`temporary profile ${logId(created.id)} may still exist; delete it in the panel before another run`);
      throw error;
    }
  }
  return { id: created.id, outcome };
}

// The child port of a profile of a switched-on app (childkill --child-port), from the profile list.
export async function childPortOf(admin, profile) {
  const { rows } = await admin.profileList();
  const row = rows.find(item => item.id === profile);
  if (!row) throw new Error(`profile ${logId(profile)} is not in the profile list`);
  return row.port;
}

// HM-16 review SF-3: what the driver runs for childkill, --cross and --temp-profile, with the probe passed in as
// remote(mode, input, extra) (the driver's: ha_p9_probe.py on the HA host over SSH), so that their order and arguments
// are tested; the driver itself logs in to HA first and has no test of its own.

// childkill's extra probe arguments: on a switched-on app (profiles) only that profile's child, by its port; on one that
// is not switched on none (the probe then kills the launcher's children, as before profiles).
export async function childkillArguments(admin, profiles, profile) {
  return profiles ? ['--child-port', String(await childPortOf(admin, profile))] : [];
}

// --cross: every listed profile's token, each revealed under its own profile, into the probe's cross mode.
export async function runCross(admin, clientFor, remote, report = () => {}) {
  const { rows } = await admin.profileList();
  remote('cross', await crossLines(clientFor, rows.map(row => row.id), report));
}

// --temp-profile (PaaS public_probe.py --temp-profile): the default profile's token (it must have one); a temporary
// profile (withTemporaryProfile) given the backend (then settle: the app starts its child) and its own token; that
// token cross-checked with the default profile's, then the plan run with it, or without a backend of its own a call of
// probeTool that must be refused (never answered with the default profile's backend); once it is deleted, its token
// must be refused (the cross mode's "gone"). Returns the temporary profile's id.
export async function runTemporaryProfile(admin, clientFor, remote, { backend, plan, probeTool, probeToolArgs = '{}',
  report = () => {}, label, settle = () => new Promise(resolve => setTimeout(resolve, 5000)) } = {}) {
  const own = await revealToken(clientFor('default'));
  if (own === null) throw new Error('the default profile has no active token');
  let gone;
  const { id } = await withTemporaryProfile(admin, clientFor, async (created, temporary) => {
    report(`temporary profile created: ${logId(created)}`);
    if (backend) {
      const fresh = await temporary.bootstrap();
      try { await temporary.mutate('backend', backend, fresh.configuration?.revision); }
      catch (error) {
        const pending = temporary.pendingOperation();
        if (pending) report(`unconfirmed operation; inspect receipt before another run: ${pending.id} ${pending.route}`);
        throw error;
      }
      report('PUT api/backend (temporary profile): confirmed');
      await settle();
    }
    const token = await revealToken(temporary);
    if (token === null) throw new Error('the temporary profile has no active token');
    gone = token;
    remote('cross', crossLine('default', 'live', own) + crossLine(created, 'live', token));
    if (plan) remote('plan', token + '\n' + JSON.stringify(plan));
    else if (!backend && probeTool) remote('plan', token + '\n' + JSON.stringify({ denials: [[probeTool, JSON.parse(probeToolArgs)]] }));
    return created;
  }, { report, label });
  report(`temporary profile deleted: ${logId(id)}`);
  remote('cross', crossLine('default', 'live', own) + crossLine(id, 'gone', gone));
  return id;
}
