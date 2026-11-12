# Legacy migration preview and recovery implementation plan

**Goal:** Make legacy permission changes reviewable without changing startup migration while its policy decision is pending.

**Architecture:** An offline, pure planner validates schemas 1–4 before computing either explicit policy choice. A secret-free policy recovery record can restrict a current schema 4 state while retaining its current tokens, endpoint and backend. The confirmed delivery scope retains the existing ProductStore all-on migration and exposes both choices through an explicit offline CLI. No commit before parent freeze.

**Tech Stack:** Python 3.13, existing Pydantic models and policy catalogs, pytest, standard-library filesystem operations.

1. Inspect retained bounded tool models and pre-schema-4 source. Record exact global-switch semantics, grants and additions for all eight products, including n8n.
2. Add `mcp_admin_core/migration.py` with strict legacy validation and pure explicit-choice preview, including disabled differences, effective write differences, new tools/operations and unclassified entries. Keep existing schema 4 state intact.
3. Add an offline helper under `scripts/` that reads without opening ProductStore, prints only policy data, and optionally persists an exclusive 0600 secret-free recovery record in a protected directory. Recovery plans must merge current identity/backend data and retain later revocations.
4. Add literal schema 1/2/3 fixtures and tests covering both choices, every product, malformed inputs, schema 4, idempotence, reload, secure records, and revoked/rotated token recovery. Run the focused suite plus existing migration/storage tests.
5. Document source limitations, commands, test evidence and integration seams in `evidence/batch2/migration-handoff.md` and an operator guide. Keep startup wiring unchanged; leave final provenance hashes, commit and live candidate to the parent after its freeze.
