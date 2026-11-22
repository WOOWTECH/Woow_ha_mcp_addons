# Nextcloud PaaS comparison (2026-11-20)

Compared HA HM-22 `b0b9c4f` with PaaS `origin/main` `5ef1046`, especially `apps/nextcloud/nextcloud_mcp_admin/routers/config.py`, `tool_policy.py`, and their identity and policy tests.

HA now normalizes submitted Nextcloud root URLs on both backend save routes: scheme and host case, default port and trailing slash, and browser page suffixes (`index.php`, `remote.php`, `ocs`, `apps`, `login`, `settings`). Identity comparison uses the same normalization, including legacy stored URLs. The complete submitted URL is checked by HA's destination rules before suffix removal; HA retains its stricter URL and credential validation and its origin-change credential requirement. Existing state is not rewritten merely by loading it. An equivalent legacy spelling is retained on save, as in PaaS; this can preserve a legacy page suffix in the stored child root, so correcting such a legacy value may require clearing and reconfiguring the connection, which rotates an active token.

Both platforms rotate an active token when a previously configured URL or username changes, not for an app-password-only change or first configuration. HA stops the child before its atomic identity/token update and preserves restore-review and per-profile isolation rules.

Policy saves now match PaaS for Nextcloud: tightening and unchanged saves do not restart, while widening restarts the selected child only if it is running or starting. A stopped, blocked, failed or backing-off child is not started by a policy save; its next launch uses the updated policy. The gateway immediately enforces restrictions on existing sessions. The same rule applies to restoring a prior policy. Other products retain their existing lifecycle behavior. Configuration status follows the gateway-enforced policy without claiming a new child generation.

HA retains bounded credentials and connection replacement semantics: it requires a complete connection rather than accepting PaaS's partial empty connection fields; patching a URL to a new origin requires resubmitting its stored secret. HA also retains stricter destination checks. These are distinct security and API contracts.
