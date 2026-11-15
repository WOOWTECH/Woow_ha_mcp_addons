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
