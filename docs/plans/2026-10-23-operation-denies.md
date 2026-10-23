# HA operation restrictions

Goal: persist per-tool operation denies without resetting schema-4 policy or identity.

Architecture: `ProductState.denied_operations` maps tool names to denied operation
names. The audited `Tool` selector/read/write/default metadata is the only operation
catalog. Gateway authorization checks denies before child dispatch. The existing
policy route accepts optional denies, preserving them for old clients. The UI edits
denies separately from write grants and preserves stale restrictions.

1. Add strict bounded storage shape and startup-only additive migration in products.py.
2. Add operation authorization/catalog helpers in policy.py; reuse audited surface.py metadata.
3. Extend gateway policy validation/bootstrap and capabilities counts/states.
4. Extend UI contracts and controls; retain saved restrictions and independent grants.
5. Add focused persistence, API, authorization, JSON/SSE, and browser regressions.
6. Run bounded tests using the main venv with this worktree's PYTHONPATH; save evidence.
7. Review the final diff against requirements, verify, and commit on the owned branch.

Root owns migration.py compatibility, run_product.py, apps/n8n/run.py, upgrade
modules/entrypoints, and build.mjs. No live/CI/push/subagents or full suite here.
