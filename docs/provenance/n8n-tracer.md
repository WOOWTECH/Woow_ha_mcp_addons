# n8n tracer source and publication boundary

**Local adaptation only; NOT publication clearance, HA acceptance, or an image build.**
No blanket MIT license is asserted for this repository. The shared boundary is new
code, not an import of legacy shared core/UI; unused legacy licensing questions
are **not** a permanent blocker for that new code. Public source/image clearance
still requires app/dependency notices, SBOM, vulnerability review, approved
sensitive-data scans and publisher authorization. Any later copied legacy fragment
needs its own scoped provenance/license review.

## New boundary code

`packages/mcp-admin-core/mcp_admin_core/` is a compact new Python implementation.
The legacy source was inspected read-only at
`614ae663fadd91c76972f60017a76d2627bea87e`, specifically:

- `packages/mcp-admin-core/mcp_admin_core/config/store.py`: same-directory exclusive
  0600 temporary file and atomic replacement primitive. The adaptation adds schema
  validation, a lifetime writer lock, 0700 directory, fsync(file/directory), no-follow
  reads, no silent recovery/default merge, and fresh snapshots instead of a mutable
  cached dictionary.
- `apps/n8n/n8n_mcp_admin/launcher.py`: loopback HTTP child concept and separate
  `AUTH_TOKEN`. The new launcher uses a local locked package and a minimal environment,
  not global npm discovery or inherited environment.

No old auth/proxy/process/UI implementation, saved configuration, Git history,
private inventory or deployment manifests were copied. These are conceptual references reported by W1, not claims that old files or
fragments were copied. This repair pass did not access the original repository and
does not claim an independent line-by-line comparison with it. The UI has not been
ported or modified.

### File-level authorship boundary

| Files | Origin / copied material |
|---|---|
| Shared `__init__.py`, `config.py`, `policy.py`, `gateway.py`, `lifecycle.py`, `health.py` | Newly authored Python boundary; `config.py` uses the conceptual atomic-write pattern noted above, not an imported legacy file. Review repairs are newly written here |
| `apps/n8n/n8n_adapter.py`, `run.py` | New launcher/policy/runtime; conceptual launcher reference above |
| `apps/n8n/backend_policy.cjs` | New scoped preload adapter written in the repair pass; calls installed upstream `N8nApiClient` / `SSRFProtection.createPinnedAgents`, does not copy their implementation or edit node_modules |
| `apps/n8n/metadata_reads.cjs`, core `n8n_b3.py` | New B3 narrow adapters/schemas around genuine pinned handlers/client methods; no dependency source copied or modified. Default-off shared Tool backend preconditions are the explicit policy scope exception; no lifecycle/state migration |
| `tests/*.py` | New disposable local regression harnesses; no legacy test/config data imported |
| `licenses/n8n-mcp-MIT.txt` | Actual copied upstream notice; retain attribution, not an umbrella license |
| npm/Python lockfiles | Generated dependency metadata; actual npm application/third-party source is installed via locks, not authored here or copied from the old repo |

This table records authorship evidence, not copyright counsel's clearance. App,
bundled-data, transitive dependency and any future copied-source obligations remain.

## Actual npm artifact inspected

- Package: **n8n-mcp 2.91.0**, registry `https://registry.npmjs.org`.
- Tarball: `https://registry.npmjs.org/n8n-mcp/-/n8n-mcp-2.91.0.tgz`.
- npm integrity: `sha512-0dQtYV6+pcYUvgmZflwa84cxZLs2h/stby7gzlv3//6EiYIZyp6NZyuIAVUIudktahpHZtt0epd9TyTPWxd50A==`.
- npm shasum: `2c999da6fbe2594a093b5920e93dcd816577df17`.
- Registry-reported gitHead: `3a2ec761e006089638d281a27d15ba030ec3ec88`.
- Source: `https://github.com/czlonkowski/n8n-mcp`.
- Artifact license: MIT, copyright 2024 Romuald Czlonkowski; retained at
  `licenses/n8n-mcp-MIT.txt`. This is NOT a transitive/bundled-data license clearance.
- Source/artifact equivalence and registry provenance signatures are not independently
  verified; npm integrity and distributed JavaScript inspection are the evidence here.

`apps/n8n/package-lock.json` pins the complete npm resolution with registry URLs and
integrities. Use `npm ci --prefix apps/n8n --ignore-scripts --no-audit --no-fund`.
No global npm installs or native build/install scripts are required for this tracer.
The tested fallback is **sql.js 1.14.2**; optional better-sqlite3 11.10.0 is installed
as package contents but its native addon is not built. MCP JS SDK is **1.30.0**.

### Important launcher correction

The old `dist/http-server.js` exists but is deprecated and does **not** implement
modern streaming. Do not use it for this tracer. The npm `n8n-mcp` bin points to
`dist/mcp/stdio-wrapper.js`, which is not the HTTP entrypoint.

The immutable adapter runs `node --require <adapter>/backend_policy.cjs <local-package>/dist/mcp/index.js` with
`MCP_MODE=http`, `HOST=127.0.0.1`, `PORT=3000`. Index lines 78–130 select
`SingleSessionHTTPServer` from `dist/http-server-single-session.js` unless
`USE_FIXED_HTTP=true` (never set here). That implementation provides session-based
POST/GET/DELETE `/mcp`. Its legacy `/sse` and `/messages` are intentionally NOT
exposed by the outer gateway. Only Streamable HTTP, including its SSE responses,
is claimed locally.

The child receives an independent 256-bit `AUTH_TOKEN`, optional GUI-owned
`N8N_API_URL` and `N8N_API_KEY`, production/log settings, and bounded session options
`N8N_MCP_MAX_SESSIONS=20`, `SESSION_TIMEOUT_MINUTES=10`. Telemetry is explicitly
disabled with `N8N_MCP_TELEMETRY_DISABLED=true`. There are no inherited backend,
Supervisor, proxy or Node injection variables. Child output is discarded, not
forwarded into potentially credential-bearing logs. Its working directory is the
new restricted state directory; no old `.env` is used.

The preload's network adaptation overrides the backend API client's agent factory, scoped to the
one configured origin/base path. Global webhook SSRF stays strict. It checks every
DNS answer and pins connections, admits reviewed LAN/ULA/loopback backends, rejects
metadata/reserved/transition destinations and retains redirects-disabled behavior.
The exact API-client SHA-256 below is enforced before loading this adapter. Health
monitor uses an internal bounded workflow-list call through this same network policy; B3 public status is distinct and does not establish credential permissions.
See `../n8n-tracer-contract.md` for the complete policy and local-only evidence.

The upstream accepts `x-n8n-*` request headers as instance overrides even outside
explicit multi-tenant mode. The gateway forwards ONLY MCP session/protocol/event
headers and Accept; it never forwards instance-override headers, client auth,
Ingress identity, cookies, forwarded headers, Origin, arbitrary paths or query strings.

### SHA-256 of distributed files inspected

| File below npm package | SHA-256 |
|---|---|
| `dist/mcp/index.js` | `4476ee45971533c0b7e97cfec4f53466e88100af616fa3fd0a7df49e90128e15` |
| `dist/http-server-single-session.js` | `da499542df98783e93961cf7a5c410d38fc1d45876828172a7119b0f7c0db74b` |
| `dist/http-server.js` (NOT launched) | `8eb7359605a29b25c5083e2bdbc8ac703e59e4a98d55c0bbe8107ed21a98ffe3` |
| `dist/mcp/server.js` | `a4dfc41f48282423a610ee9ac45c0374357b7409cdaa4858e11ba58a32b2128c` |
| `dist/mcp/handlers-n8n-manager.js` | `0d99e10ec1eb9a6e4d78726636aa79f52eb4f3862be506785b794f1aeb9608cc` |
| `dist/services/n8n-api-client.js` | `e64be8d3def0623b6710c6e98f7a08ed14a49a1764a5f789def58ea1e900947c` |
| `LICENSE` | `8292ff05257b8f1ceae44382f0585abb0df9dc007d2ee2254c5a835c01920b35` |

## Audited narrow tool policy

This is intentionally NOT the entire upstream registry. All unlisted tools and
unlisted arguments are denied, including mixed-action/generic execution tools.
Upstream annotations, names and list visibility are not authorization inputs.

| Tool | Classification and source evidence in distributed JS | Accepted arguments |
|---|---|---|
| `tools_documentation` | Read: `mcp/server.js:1152–1153,3114–3121`, returns local documentation | topic (identifier), depth (`essentials`/`full`) |
| `search_nodes` | Read: `mcp/server.js:1154–1163,1555+`, local database SELECT search | query, bounded limit |
| `n8n_list_workflows` | Read: `handlers-n8n-manager.js:962+` → `services/n8n-api-client.js:607–616`, GET `/workflows`, returns reduced metadata | bounded limit, active |
| `n8n_delete_workflow` | **Write**: `handlers-n8n-manager.js:926–961` → `services/n8n-api-client.js:535–543`, DELETE encoded workflow path | identifier-only id |

Write authorization is off on bootstrap and requires a verified administrator's
CSRF-protected policy update. No real workflow deletion is used in tests. Enabling
writes does not enable unreviewed tools. Every direct `tools/call` is checked before
forwarding, even in an existing session; list filtering is secondary.

## B3 narrow metadata reads (pending independent SPEC then NEW SECURITY)

The installed 2.91.0 dispatch calls genuine `handleListCatalog` → `listTags`
(single `/tags?limit=250`, then original filter/slice); `handleListExecutions` →
`listExecutions` (single `/executions`, includeData=false); `handleGetFolder` →
`getFolder` (explicit non-personal project/folder, no discovery); and
`handleHealthCheck` → `healthCheck` (derived `/healthz`, then at most one
`/workflows?limit=1` fallback). New successful projections contain bounded
metadata only. No get-execution payload, run/retry/delete, project catalog,
folder move/delete or new grants. Full schema/effect/budget contracts are in
`../tool-expansion.md` and `../tool-surface.json`.

Health's genuine handler also normally invokes `checkNpmVersion` (global fetch
to npm registry), `buildOfficialMcpHealth(context,false)` (configuration/possible
client construction), and client `getVersion` (`/settings`). B3 invocation-local
auxiliary denial prevents those calls before DNS/connect; only an actual backend
health/fallback success can become public status=ok. Output explicitly says
service-availability and authentication=not-verified. The older credential
monitor, API successes, retry/settings fallback, local unconfigured startup,
DNS pinning and Webhook SSRF policy are unchanged.

Before requiring runtime/helper code, the preload additionally guards:

| Distributed file | SHA-256 |
|---|---|
| `dist/mcp/handlers-official-tools.js` | `e85937c58d5a8426d54b1b69598adc83a14648402fc58a8714ef5db8132977cd` |
| `dist/mcp/official-mcp-access.js` | `113d3556e4b93a870b36986a0fce8de45391ce64d7ab4c9f50fd6715eee3c733` |
| `dist/utils/npm-version-checker.js` | `35eb4789eef7766e4516f78caf125542778cf7de33e1fff4bc670c1f1029057a` |

## Python and local runtime

`pyproject.toml` pins direct Python dependencies; `uv.lock` pins transitives with
hashes. `uv sync --frozen --python python3.13` creates an isolated `.venv`.
The repair promotes already-locked **AnyIO 4.15.1** (cancellation scopes) and
**ipaddr.js 1.9.1** (address classification) to explicit direct dependencies; no
version upgrade or new registry download was used. The latter predates RFC8215
classification, so the adapter also restricts public IPv6 to 2000::/3 and tests
translation-prefix rejection explicitly. Their license/security obligations remain.
Local verification used CPython **3.13.2**, Node **22.23.2**, npm **10.9.8**, uv
**0.12.10**, Linux x86_64. OS/Node/Python container base digests are a packaging gate,
not resolved by these application locks. No container tooling was installed.
