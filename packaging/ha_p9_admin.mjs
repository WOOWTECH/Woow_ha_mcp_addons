// The P9 operator kit uses the same strict write contract as the management UI.
// Only operation identity is retained in memory. Tokens never enter this store.
import { AdminApi } from '../packages/mcp-admin-ui/src/api.js';

export function createP9AdminClient(ingress, headers, fetcher = globalThis.fetch.bind(globalThis)) {
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
  return new AdminApi(base.pathname.replace(/\/$/, ''), transport, storage);
}
