# Changelog

## 0.3.4 — release candidate (2026-10-24)

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
