# Changelog

## 0.4.3 — release candidate (2026-10-28)

Applies to the six Store-enabled add-ons and the OpenDesign source. The six 0.4.3 images require
fresh exact-image acceptance before release; OpenDesign stays disabled in the Store.

### Legacy installations: one-time all-on at the first start (aligned with the PaaS; owner decision 2026-10-27)

- A legacy state (schema 1/2/3, written by 0.1.x or the 2026-10-03 prototypes) is migrated before ProductStore or any
  child starts (`mcp_admin_core/owner_defaults.py`, called by `run_product.py` and `apps/n8n/run.py`) to exactly the
  all_on plan the 0.3.0–0.4.1 review page applied: schema 4, writes on, every write grant, nothing disabled, no
  operation deny; token, child token, endpoint and backend kept. The same atomic state write adds the marker
  `owner_defaults_20261025` (`applied`, `at`, `from_schema`, later `restored_at` / `acknowledged_at`), the PaaS
  marker's name. Before it, the legacy policy is saved once as the format 2 record
  `/data/mcp/owner-defaults-20261025-recovery.json` (0600, exclusive, policy and digests only), published complete or
  not at all (temporary file, fsync, link), so a failed or interrupted write never leaves a partial record that would
  stop every later start; an identical record from an interrupted attempt is reused, any other refused. MCP then
  serves at once: no 503 `upgrade_review_required`, no review listener; one fixed line in the add-on log.
- Schema 4 is never touched (new installations, 0.2.0+, states the review page migrated, ws97's writes-off Hermes).
  The marker is omitted while absent, so such states keep exactly the 0.4.1 keys.
- Unreadable, invalid, linked or busy state, a record that cannot be saved, or an existing record that is not this
  state's: nothing is migrated or rewritten (bytes, mode, mtime); the add-on logs which of these (fixed text naming
  the file) and stops with `runtime unavailable; local recovery required`. After a disk-full failure a restart with
  free space completes the migration.

### The review page becomes a notice with an optional, faithful restore

- The pre-start review listeners, `upgrade.py` and the `upgrade.js` page are removed. The normal panel shows, on
  every page until the administrator acts, when (UTC) the defaults were applied, from which schema and the
  differences (`bootstrap.owner_defaults`).
- "還原升級前的限制" (`POST /api/owner-defaults/restore`, CSRF and `If-Match` required, 428 without it):
  `migration.plan_owner_restore` reads each legacy list the way 0.1.x enforced it. Tools are a deny list: the tools
  the legacy state disabled are disabled again and a tool added since 0.1.x stays enabled, so never "everything
  disabled" as with `preserve`. Writes are an allow list: only the grants the legacy state held stay (exact grants;
  the legacy switch for n8n `n8n_delete_workflow` and OpenDesign `delete_project`) and every other write is revoked,
  one added since 0.1.x included, as 0.1.x refused it; its legacy switch and operation denies come back. The restored
  policy permits exactly the writes the legacy runtime permitted (ws97 Hermes 0.1.14 sample: no write, 9 of 11 tools
  listed, `preserve` gave 0; a 0.1.14 n8n default: no write, 18 of 28 tools). Restrictive merge: later
  administrator limits stay; nothing is enabled. EMQX, LiteLLM and Nextcloud restart their child, as for a saved
  policy.
- "保持全開，不再提示" (`POST /api/owner-defaults/dismiss`) records `acknowledged_at`; the restore stays on the
  diagnostics page. The offline CLI `--restore-policy` accepts the format 2 record too.
- The notice is only in the add-on panel and one add-on log line (no sidebar entry by default, no HA notification),
  so the README, every DOCS and every add-on CHANGELOG (the Store's update notes) say to open the panel after the
  upgrade. A notice the panel cannot read is not hidden: a fixed card 「升級通知無法顯示」 asks to reload or update
  the add-on (no server value, no action).

### Tests and docs

- `tests/test_owner_defaults.py` with real legacy samples (`tests/fixtures/owner_defaults`: schema 1/2 written by
  313ab01, schema 3/4 by v0.1.14/v0.2.2 and by the real ws97 Hermes add-on; fake tokens only); browser and
  unit tests for the notice. README, DOCS, guide, legacy migration,
  update/rollback and `upgrade-notes.yaml` describe the new behavior. Rolling back a migrated installation to 0.4.1
  needs the pre-update backup (0.4.1 refuses the marker key).

## 0.4.2 — release candidate (2026-10-27)

The management panel's HA role check (shared by the seven add-ons) accepts three more Home Assistant Core releases
and says why when it refuses an unreviewed one. This patch release builds new images for the six Store-enabled add-ons. It changes no option, port, tool,
grant or state schema.

- Core 2026.10.2, 2026.10.3 and 2026.10.4 are added to `ha_role._HA_VERSIONS` after the contract review recorded in
  [ha-role-core-contract.md](docs/ha-role-core-contract.md): 20 of the 21 consumed Core files and the 4 adjacent ones
  are byte-identical to 2026.10.1; `auth/__init__.py` only changes `AuthManager.async_remove_user` (it now revokes a
  removed user's refresh tokens), outside `config/auth/list`. Supervisor 2026.10.2–2026.10.4 (`api/proxy.py`
  `cab849dc`) only start the two proxy loops as background tasks; the auth frames are unchanged.
- Any other Core version, pre-releases included, is still refused, now with the reason: the panel's pages show
  「這個 HA Core 版本尚未審核：<version>」 as static text, its API answers 403
  `{"error": "request denied", "detail": {"code": "core_version_unreviewed", "ha_version": ...}}`, and the add-on log
  gets one line per version (no frame, token or user). The machine token is still never sent to such a version, and
  every other refusal keeps the fixed `{"error": "request denied"}`. MCP endpoints do not use this check.
  `tests/test_ha_role.py`, `packages/mcp-admin-ui/tests/core-version.test.mjs`.

## 0.4.1 — release candidate (2026-10-25)

The six Store-enabled add-ons carry the reviewed HA management UI update from PR #20 on the merged 0.4.0 base. For n8n, the Tools page shows that `exposeToMcp: true` can write even when the selected operation reads, names the existing `n8n_update_partial_workflow` dependency and distinguishes saved policy from a draft or unknown child state. No grant, default, gateway enforcement, dependency, option, port, image name or state-schema change is intended; OpenDesign remains disabled. 0.4.0 images do not contain this UI change. See [0.4.1 release decision](docs/operations/release-decision-0.4.1.md); image publication and ws97 upgrade remain pending.

## 0.4.0 — release candidate (2026-10-25)

The six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) move to 0.4.0,
after 0.3.4: phase 2 of the MCP SDK 2 migration (issue #21; the WOOW PaaS twin
woow-mcp-server did phase 1 in #81 and #82). OpenDesign stays disabled (metadata
version only, no image). No option, port, architecture, image name, tool name or
state schema changes; schema stays 4 and the full-functionality defaults are
unchanged. One declared breaking change: 13 Odoo tools return their structured
result unwrapped (`upgrade-notes.yaml`). See the
[0.4.0 release decision](docs/operations/release-decision-0.4.0.md).

### Dependencies

- Python MCP SDK `mcp` 1.30.0 -> 2.3.0 (plus `mcp-types` 2.3.0) in the six Store
  children; FastMCP 3.4.11 -> 4.1.3 (EMQX, LiteLLM, Nextcloud); `odoo-mcp` 1.1.0 ->
  1.3.0 (Odoo; both build patches apply unchanged). The SDK brings httpx2/httpcore2
  2.16.0, truststore 0.10.5 and opentelemetry-api 1.45.1 and drops httpx-sse; the
  children's backend clients stay on HTTPX 0.28.1. The archived Odoo Manage keeps its
  own mcp 1.30.0 / mcp-server-odoo 0.7.1 lock.
- Node 22.23.4 -> 26.12.1 (Active LTS from 2026-10-28) in every image and in CI
  (`node:26.12.1-bookworm-slim`, multi-arch index digest). Node 26's official binary
  links libatomic.so.1: the n8n image copies the node stage's Debian libatomic1 library
  next to libstdc++/libgcc_s and checks `node --version` right after. n8n-mcp 2.96.2
  and the 28 n8n tools are unchanged; the n8n child keeps its sql.js fallback
  (`npm ci --ignore-scripts`, no native better-sqlite3).

### MCP SDK 1 -> 2 behaviour, kept as it was

- Tool error text: SDK 2 shows only `Error executing tool <name>` for any exception but
  `ToolError`. `apps/runtime/tool_error_text.py` (port of the PaaS `keep_error_text`)
  restores the 1.x text in Odoo, Hermes and OpenDesign; the real children answer the
  same texts as 0.3.4.
- Odoo concurrency: SDK 2 runs sync tools on parallel worker threads; `BoundedTools`
  still serializes every Odoo tool (writes included) on its one owned worker.
- Request body 16 MiB and the 30-minute session idle limit still take effect
  (`apps/runtime/session_idle.py`, verified with SDK 2 and six real children).
- FastMCP 4 cancels a running async tool when its session is deleted: the Nextcloud
  readiness probe is shielded, so a slow 401 still latches (at most two failed logins).
- Protocol: clients stay on the 2025 handshake era. The gateway still answers
  `server/discover` itself (-32601) and no longer forwards a client's
  `MCP-Protocol-Version` header with an initialize (SDK 2 children refuse such an
  initialize). Raw JSON-RPC, the Python SDK 1.30 and 2.3 clients and the TypeScript SDK
  1.32 client connect, list and call through the gateway (`tests/test_protocol_clients.py`).

### Odoo tool texts match the add-on's gating

- odoo-mcp 1.3.0 tells the model that `execute_method` blocks direct create/write/unlink and
  that `chatter_post` needs a preview approval token; this add-on runs both directly
  (`ODOO_MCP_ALLOW_DIRECT_WRITES=1`, `MCP_CHATTER_DIRECT=1`). The HA copy of the
  direct-writes build patch makes both texts follow those switches (and now accepts only
  the published 1.3.0 file and writes one pinned digest); the behaviour is unchanged.
  `tests/test_odoo_write_descriptions.py`.

### Hermes

- The vendored Hermes files are re-snapshotted from woow-mcp-server main (server.py
  as of 471efdf: SDK 2 `MCPServer`, 1.x error text), keeping the HA changes, including
  the 0.3.4 loopback refusal (AI-HMCP-002-2) and the LAN allowance.

## 0.3.4 — stable Release (2026-10-24)

The same six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) move to
0.3.4, after 0.3.3; 0.3.2 is not used (it had been reserved for this release).
OpenDesign stays disabled (metadata version only, no image). 0.3.4 is a dependency
and Hermes security release on top of 0.3.3: no option, port, architecture, image
name, tool name or state schema changes; schema stays 4 and the full-functionality
defaults are unchanged. See the
[0.3.4 release decision](docs/operations/release-decision-0.3.4.md).

### Dependencies (aligned with the WOOW PaaS twin)

- Python MCP SDK `mcp` 1.28.1 -> 1.30.0 in every Python child (GHSA-84m7-p3x7-pcfv:
  Streamable HTTP sessions were never reclaimed). The add-on keeps its 30-minute
  session idle limit and raises the SDK's new 4 MiB request-body default to the
  gateway's 16 MiB (`apps/runtime/session_idle.py`).
- FastMCP 3.4.5 -> 3.4.11 (EMQX, LiteLLM, Nextcloud; includes the GHSA-7xgj-8392-5q4r fix);
  `certifi` 2026.10.19 -> 2026.10.23;
  the other locked Python packages move to their newest release in the same major
  (pydantic 2.14.1, pydantic-settings 2.16.1, starlette 1.9.0, websockets 17.3, ...).
  `odoo-mcp` 1.1.0 and `mcp-server-odoo` 0.7.1 stay (the same as the PaaS; Odoo's
  build patches match their source text).
- n8n: `n8n-mcp` 2.91.0 -> 2.96.2, MCP TypeScript SDK override 1.32.0 -> 1.32.2, and
  the newest npm versions inside the existing ranges (`npm audit`: 0 findings; fixes
  body-parser GHSA-27r3-jxmh-p828, undici GHSA-4qv8-2p9j-2685 and GHSA-xjj6-f33q-929c,
  zod GHSA-mrhx-c7xc-m3w5 and moderate fast-uri/ip-address advisories). The 28 tool
  definitions are byte-identical to 2.91.0's; the test-run error build patch is
  re-pinned to the 2.96.2 file. `n8n_health_check` no longer queries the npm
  registry: the child runs with `N8N_MCP_VERSION_CHECK_DISABLED=true`, as the PaaS
  (`checkStatus: "disabled"`).
  The 0.3.3 effective-argument authorization (`output` extraction, conditional
  `exposeToMcp` writes) is re-reviewed against 2.96.2: `validateExtractedArgs`, the
  extraction and `coerceStringifiedJsonParams` are byte-identical and its tests pass
  against the 2.96.2 child.
- Node 22.23.2 -> 22.23.4 for every image (n8n-mcp 2.96.2 requires `^22.23.4`).
- MCP SDK 2.x, FastMCP 4 and Node 24 are a separate migration.

### Hermes

- `hermes_mcp` action=add refuses loopback MCP server URLs again (localhost,
  *.localhost, localhost.localdomain, 127.0.0.0/8, ::1, IPv4-mapped loopback):
  the loopback part of AI-HMCP-002-2 that the LAN-friendly guard of 0.3.0-0.3.3
  dropped. LAN addresses stay allowed; metadata, link-local and 0.0.0.0 stay refused.
  A refused URL sends no dashboard API request. Servers registered earlier are not
  removed.
- The vendored Hermes MCP files are recorded against woow-mcp-server main `a5db051`;
  0.3.0-0.3.3 already contain the same code.

## 0.3.3 — stable Release (2026-10-24)

This candidate integrates a bounded n8n authorization correction in the shared
runtime. Exact-source freeze/CI remain pending, followed by fresh six-image
container/supply-chain gates and publication. See the
[0.3.3 release decision](docs/operations/release-decision-0.3.3.md).
Published 0.3.1 images and their evidence remain unchanged.

Version 0.3.2 is reserved by the separate dependency-update PR17. This bounded
authorization release uses 0.3.3 to avoid assigning the same image tags to
different sources. Our unpublished 0.3.2 candidate is superseded; no PR17
dependency changes are merged into this release.

- All 28 n8n tools normalize the pinned child's one-level eligible `output` JSON
  wrapper before checking operation denies/grants and forwarding the same
  effective arguments. This closes outer-read/inner-write overrides for all six
  mixed selectors. A second eligible wrapper is refused as ambiguous; repeated
  authorization is idempotent, with existing input budgets applied first.
- A workflow-history read with effective `exposeToMcp=true` can also change the
  workflow's MCP exposure setting. The correction requires the existing
  `n8n_update_partial_workflow` tool to be enabled with its effective write grant,
  in addition to the invoking tool/mode's own permission, before child dispatch.
  The same dependency applies to `n8n_test_workflow` exposure requests.
- Revoking or disabling the updater must prevent this indirect write, including
  the pinned child's accepted boolean and output-wrapper representations.
  Requests without exposure retain their existing read behavior; full-policy
  users retain exposure functionality. No new write grant is introduced.
- Additive `conditional_writes` capability metadata names the exposure parameter,
  existing updater dependency and its effective policy state. Existing UI grant
  controls remain sufficient; no UI source or new persisted permission is added.
- The n8n contract remains 28 tools and 33 write grants. Schema 4, saved tokens,
  dependencies, child versions and UI source are unchanged by this correction.
  Fresh installs retain maximum functionality. Existing schema 1/2/3 upgrades
  retain authenticated prestart review with `all_on` preselected and explicit
  administrator confirmation; current-schema startup remains unchanged.

All six enabled products advance together under the shared-core version
contract. OpenDesign receives source metadata only and remains unpublished.
No option, port, architecture, image name or privilege change is planned.
Existing state needs no migration, but downgrading the binary restores the
conditional-write defect. Preserve a backup and current token/policy state.
The planned official Hermes test upgrades 0.3.0 directly to 0.3.3 with a fresh
backup; no official 0.3.1 HAOS upgrade is claimed.

## 0.3.1 — stable Release (2026-10-24)

Six enabled add-ons share the runtime and UI fixes below. OpenDesign remains
disabled: metadata only, no image or stable Release. Exact 0.3.1 image acceptance,
supply-chain scans and publication are pending; source/candidate results do not
replace those gates. See the [release decision](docs/operations/release-decision-0.3.1.md).

- Management bootstrap, saves and restart responses add configuration revisions
  and pending/applied/failed/unconfigured/unknown status. Applied means the current
  child generation completed its protocol probe; backend health remains separate.
  Token and endpoint changes do not imply a child restart.
- Fix a literal `null` appended to the configuration status card when no stale
  revision warning is needed. Initial applied display and status/page refreshes
  now render only DOM rows; older bootstraps without configuration omit the card.
- Optional `If-Match` rejects stale settings with HTTP 409 before any durable
  write or child replacement. Existing clients without the header remain
  compatible. The UI retains a conflicting draft until explicit reload, which
  clears the draft; it never silently advances an open form's revision. Revisions
  are process-local, so forms opened before a management restart must reload.
- A committed save followed by failed child replacement reports HTTP 503,
  `saved:true`, a fixed safe error code and failed apply status. Management remains
  available after launch failure. The UI distinguishes saved from applied and
  does not retry the mutation automatically.
- Persisted shared-token revoke/rotate now cancels already-open GET/POST streams,
  pending child I/O and blocked response sends on both public MCP routes, without
  restarting the child. Cleanup closes paused upstream iterators and joins owned
  readers/slots. A response that has started closes instead of changing its HTTP
  status. Already delivered bytes and dispatched backend work cannot be recalled.

No state-schema, dependency-pin, child-runtime, manifest option, port, architecture
or privilege change. Maximum functionality remains the default for new installs;
existing schema 4 keeps its saved policy. Upgrades from schema 1/2/3 retain the
0.3.0 authenticated prestart review: `all_on` is preselected but an administrator
must confirm, or explicitly choose `preserve`. Back up before upgrading, then open
the panel if legacy review is pending. Current credentials and revoked state are
preserved; this patch does not automatically re-enable tokens or restricted tools.

## 0.3.0 — stable Release (2026-10-24)

Six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) share this
release. OpenDesign stays disabled: metadata version only, no image publication.
The default remains maximum functionality: all tools and writes enabled on new
installations, with `all_on` selected by default in legacy upgrade review.

### Upgrade behavior change

Legacy schema 1/2/3 waits in an HA-admin-authenticated Ingress review before any
ProductStore migration or MCP child starts. An administrator must confirm
`all_on` or explicitly choose `preserve`. Unattended legacy upgrades therefore
remain in review until confirmation; MCP and readiness return 503. Fresh
installations and existing schema 4 retain normal startup. Existing tokens,
including revoked ones, are preserved.

Back up before upgrading. Open the add-on panel, compare both previews, and
confirm. After durable migration, review listeners stop and the normal runtime
starts on the same ports. `preserve` disables new tools and tools whose expanded
arguments need review; it cannot recreate old binary argument restrictions.

### Security dependencies

- Pin certifi 2026.10.19 in the six published products to address
  GHSA-6q48-6c7w-9gw2; rebuild the vendored Python environments.
- Pin n8n MCP SDK 1.32.0 for GHSA-22jm-h49p-29qw and
  GHSA-46jr-4wx8-v453, with a product-specific input-budget mitigation.
  After authentication, n8n requests are limited to 4 MiB, 10,000 recursive
  argument members/elements and depth 64. JSON-looking encoded argument
  structures share the element budget and a cumulative 4 MiB decoding budget;
  compressed requests are rejected. Oversized workflows must be split or
  reduced. Other products retain their existing request limits.
  Release scans retain the original policy and severity threshold.

### Policy and token management

- Per-operation denies and exact write grants distinguish saved from effective
  access. Disabled operations remain denied even with a saved write grant.
- Token rotate/revoke persists the shared-token change before invalidating old
  access, without restarting the child; already dispatched backend work cannot
  be rolled back. Revoked state survives reload/restart and stale generic saves.
- The offline CLI previews/applies legacy migration and restrictive policy
  recovery. Recovery retains current credentials, unions denies and intersects
  grants; it never restores an old token or enables a later-disabled global write.
- EMQX/LiteLLM/Nextcloud policy updates retain their existing child restart
  behavior; affected clients reinitialize after an old-session 404. Token-only
  changes do not restart the child.

Schema remains 4, but an older binary cannot enforce the new operation denies.
A downgrade is not equivalent to restrictive policy recovery. Stop the runtime
and review a compatible full backup plus current token revocations separately.
See [migration](docs/operations/legacy-migration.md),
[backup and rollback](docs/operations/update-backup-rollback.md), and the
[release decision and acceptance boundaries](docs/operations/release-decision-0.3.0.md).

The six exact-image supply-chain and anonymous registry gates completed, followed
by six per-addon stable Releases on 2026-10-24 through the existing Store workflow.
The linked 0.3.0 decision retains the exact image identities and acceptance limits.
