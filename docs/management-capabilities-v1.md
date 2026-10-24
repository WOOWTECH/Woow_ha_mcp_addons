# Management capabilities v1

The authenticated `GET /api/capabilities` is additive. Existing bootstrap, backend,
policy, endpoint, token, ingress role checks and MCP transports remain available.
No state schema or default grants change in this work.

## Upgrade boundary

The existing standalone `ProductStore` migration is unchanged: schema 1/2 states
pass through earlier migrations, and schema 3→4 clears disabled tools and enables
all write grants once (except the retired Odoo Manage product). This was the prior
0.2.0 owner decision. A 0.1.14 installation can therefore change policy when first
opened by this candidate, even though the new management routes do not edit policy.
Do not describe that upgrade as preserving all prior restrictions.

Preservation tests for these additions cover **schema 4**: an already-migrated
state with revoked token, disabled tool, empty write grants, saved endpoint and
backend survives backend checks, child restart and reopening byte-for-byte.
Existing-addon upgrades from older schemas are deferred to root's explicit policy
and rollback plan. Local tests use disposable state. The builtin compatibility
backport separately retains its schema-3 store and bounded 15-tool policy; it must
not import the standalone full-surface migration.

The snapshot follows the parent parity contract (`schema_version: 1`): deployment,
product/version, admin authority, backend features, management features, layered
health, and tool catalog. Public endpoint health stays `unverified`: saving an
endpoint or successfully listing tools does not verify an external connection.

Tool catalog is the union of the policy registry, pinned catalog and the child's
observed `tools/list`. Unknown runtime tools remain visible but policy-disabled;
observation never grants new tools. Catalog count, policy-enabled count and effective
count have separate meanings. Effective means both registered by the observed child
and allowed by current gateway policy. It does not prove a backend call will work.
When observation fails, effective count is null and permitted tools have null
`effective`; denied tools remain false. Status is `observed` or `unknown`.

Full-surface tools use observed child input schemas, falling back to the pinned
snapshot with explicit `schema_source`. Bounded adapters use their registry model
because that is what their gateway accepts. Operation entries describe the existing
read/write classifications and exact grants, without replacing the policy contract.
Bootstrap retains its original fields and includes an unobserved capability snapshot;
the new UI explicitly reads the observed snapshot. Probe sessions paginate with
bounded time, pages, bytes and tool count, and close even on cancellation.

| Route | Meaning |
| --- | --- |
| `GET /api/capabilities` | Bounded child initialize/list observation and effective policy snapshot |
| `POST /api/backend/test` | Read-only probe using saved configuration, no request body |
| `POST /api/child/restart` | Restart using saved configuration, no request body; HTTP 202 with `accepted: true`, `apply_state: pending` |
| `GET /api/diagnostics` | Child health plus bounded, redacted stdout/stderr entries |

Every route uses the same trusted ingress peer, identity and fresh role checks as
the existing API. POST additionally requires the bootstrap's CSRF token. Body-bearing
check/restart requests are rejected, so drafts cannot silently become test settings.
A successful backend-check HTTP response means the check completed; its `backend`
field separately reports reachability. Restart acceptance does not mean ready.
The restart keeps the mutation lock and joins process-group cleanup after caller
cancellation or disconnect. It does not rotate the token or save configuration.

Diagnostics retain at most 200 entries and 128 KiB in memory. Lines over 8192 bytes
are dropped whole, including lines split across reads. Known environment credentials,
encoded variants, Authorization values, secret assignments, URL userinfo and private
MCP token paths are scrubbed before retention. Reader tasks drain both pipes during
cleanup and are joined before replacement. This is child output, not backend logs,
and retention resets with the management process. No raw environment or argv is exposed.

## Builtin adapter hook

```python
from mcp_admin_core.capabilities import ManagementOptions

admin, mcp = make_apps(
    store, tools, child,
    # Keep the deployment's existing identity/role adapter.
    verify_admin=verify_admin,
    health=health.snapshot,
    management=ManagementOptions(
        kind="builtin",                 # ha-addon | paas | builtin
        authority="ha-ingress",         # ha-admin | ha-ingress | paas-password
        backend_mode="fixed",           # manual | fixed
        backend_can_edit=False,
        product_version="0.2.2",        # optional; defaults to core VERSION
    ),
    backend_check=health.test_saved,     # optional async(state) -> check result
    restart_child=backend_changed,      # optional async(state) -> None
    diagnostics=manager.diagnostics,    # optional () -> {child, logs}
)
```

Omitted callbacks advertise unavailable features and their routes return structured
409 `unsupported`. A fixed backend must have `backend_can_edit=False`; valid backend
replacement/clear requests then return 409 `backend_fixed` without saving or restarting.
The UI hides that form and uses deployment/authority labels rather than assuming HA.
These options are metadata and action restrictions, never authentication overrides.
A builtin can retain its bounded Tool models, existing store and migrations; no
full-surface migration is required. Older Tool classes can omit `child_schema` and
`read_operations`.

The optional callback contracts are trusted runtime hooks, never HTTP-supplied commands.
`backend_check` returns `tested_configuration: "saved"`, `checked_at`, `health`,
`backend`, and optional `reason`; `HealthMonitor.test_saved` supplies this shape.
`restart_child` must preserve the runtime's owned stop/reap/start behavior.
`diagnostics` returns `Supervisor.diagnostics()`'s shape; logs include `entries`
(`at`, `stream`, `generation`, `text`), `dropped`, byte/count bounds, and `redacted`.

## Local verification scope

Regression coverage lives in `tests/test_management_capabilities.py`,
`tests/test_child_diagnostics.py`, the existing lifecycle/role suite, and
`packages/mcp-admin-ui/tests/{capabilities.test.mjs,browser/capabilities.spec.mjs}`.
Owned fake child/backend tests do not establish HAOS ingress or live backend acceptance.
Root owns deployment, live verification and version changes.
