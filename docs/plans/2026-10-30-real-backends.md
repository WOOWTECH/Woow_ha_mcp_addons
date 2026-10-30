# Real backend acceptance implementation plan

**Goal:** Exercise released MCP gateways against owned real Odoo, Nextcloud and EMQX servers.

**Architecture:** A UID-guarded namespace hosts one backend family at a time. Exact digest gateway images retain their installed source; HA uses a declared synthetic loopback identity. Native backend observations establish side effects, denials, restart persistence and cleanup.

**Tech Stack:** Python, Kubernetes, Odoo18/PostgreSQL, Nextcloud/SQLite, EMQX, HTTP MCP.

1. Reuse the proven Odoo18 account/CRUD/state-hash cases from `work/ha044-real-odoo18-20261029`, retaining historical evidence. Inventory current published digests. Never reuse historical credentials.
2. Implement `acceptance/real_backends/controller.py` for resource lease checking, namespace ownership, generation, image readback, bounded exec, restart, cleanup and evidence hashing. Implement `ha_runtime.py` as the minimal identity-only adapter around shipped apps.
3. Implement `probe.py` with real management configuration and MCP sessions. Odoo: grant and child-switch denial, CRUD with a non-admin account, invalid-field backend error, persistence. Nextcloud: create/read/update, stale-etag conflict, deny no-effect, persistence, owned deletion. EMQX: publish/retained read, disabled publish no-effect, invalid topic error, persistence, owned retained deletion.
4. Run `python3 -m py_compile acceptance/real_backends/*.py` and focused safety checks before live creation. Require the main resource lease and current Ready/no-pressure capacity. Do not create resources while waiting for the lease.
5. Run each family sequentially; retain every failing attempt, diagnose exact failures and fix only the owned worktree. Capture exact running image digests and source hashes before acceptance. Verify backend state after each denied/error operation and after owned cleanup.
6. Delete only the UID/label-matched namespace; verify namespace absence and no PV claims. Produce honest matrix, source commit, hashes and handoff. PaaS EMQX is not in the eight-app release and must be separately resolved or explicitly unavailable.
