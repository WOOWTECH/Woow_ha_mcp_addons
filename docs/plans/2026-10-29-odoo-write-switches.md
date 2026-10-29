# Odoo child write switches implementation plan

**Goal:** Give HA Odoo administrators PaaS #89's four child write switches without changing outer tool grants or silently increasing existing tenants' access.

**Source:** PaaS `38a9041fb44de6d8848166473facd2f443e04710`; HA base `f71fb756baf5ca3458b32c5c20635e0689c13118`. Keep PR #30's `apps/odoo/launch.py`, `apps/runtime/odoo_tool_errors.py`, `docs/tool-surface.json`, and error tests untouched.

**Architecture:** Persist an optional, strictly typed Odoo-only switch object in schema 4. Absent means four enabled because that is the effective child configuration in 0.4.2/0.4.3; no outer policy is modified. Add a separate management PUT with the existing admin/CSRF/ETag/commit/restart path. A new Odoo entrypoint installs source-guarded callbacks on the registered child tools before the existing launcher runs; the pure decision functions are copied byte for byte from PaaS #89 into the shared core package, and all changed text and health metadata derive from the same four values. No Odoo backend access is needed to test refusal.

**Verification:** Fake Odoo backend and browser fixture only; 16 switch combinations, direct/approved/chatter/unknown methods, legacy state, concurrent ETag, restart failure and UI save/error flow. Run focused Python and Node tests, inventory/provenance gate and full CI. Open independent PR, leave it open until #29 merges and release coordination confirms rebase/version.

## Steps

1. Add tests for PaaS refusal precedence and legacy state; see failure on HA base.
2. Add optional `odoo_write_switches` model/state/child env and migration validation; run focused tests.
3. Add source-guarded Odoo entrypoint and tool wrappers using PaaS `write_gates`; test all 16 combinations and fake backend call counts. Keep existing launcher file untouched.
4. Add management API route with explicit Odoo-only validation, revision guard and child restart; test errors and rollback semantics.
5. Add UI contract, switch card, and fixture/browser tests for save, status, stale version, non-Odoo absence and narrow screens.
6. Update provenance and operator notes in disjoint files where possible; run fresh focused and full verification; commit, push and open PR without merge.
