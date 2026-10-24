# Changelog

## 0.3.1 — release candidate (2026-10-24)

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
