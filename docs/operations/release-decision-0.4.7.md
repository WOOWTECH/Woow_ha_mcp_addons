# 0.4.7 release decision — 2026-10-30

Status: **source candidate; image publication pending**. The 0.4.6 images and receipts do not cover this candidate.

## Contents and compatibility

All persisted administration changes require the exact strong If-Match revision reviewed by the caller. Missing revisions return428; stale or malformed revisions return409 before a new effect. Token rotation/revocation and child restart additionally require one Idempotency-Key. The bundled UI uses the server clock plus a cryptographic random suffix, retains only the operation identity/revision in sessionStorage, and offers explicit query or same-ID resend after an uncertain response.

A private bounded journal persists an intent before the effect and a completion afterward. Completed replay returns fixed non-secret outcome labels without repeating the effect. A crash can leave an unknown outcome; unknown intents never automatically execute again. Fresh HA administrator authority is checked under the mutation lock before disclosure or replay, and receipts are bound to the original user. Revoke now returns200 JSON instead of204; custom API clients must adopt the headers and response contract. MCP tool calls and provider/backend permission boundaries are unchanged.

This is not an exactly-once transaction with the child process. Backups must retain the full data directory including the hidden journal. Restore/downgrade requires compatible data/binary and independent review of current tokens, child state and outstanding client intentions. Older backups cannot retain receipts created afterward. See [API contract](../admin-write-contracts.md) and the root upgrade notes.

## Evidence and release gates

The integrated source includes HA implementation9af732a and real-backend harnessd71d352. Focused implementation checks and an independent journal review passed; full exact-source CI and browser results remain to be attached. The backend harness contains actual Odoo18, Nextcloud35.0.2 and EMQX5.8.9 acceptance, but its completed runs exercised the recorded0.4.6/PaaS sources, not this candidate. Tests of older images do not establish0.4.7 runtime acceptance.

Required before distribution:

1. Exact committed source checks, Release train, upgrade comparison and independent integration review.
2. Six linux/amd64 images through the existing private builder: P1–P5, current/full-history/layer secret scans, SBOM/CVE/license policy, final package checks, packaged runtime, exact UI and UID boundaries. Existing precise secret-triage exceptions retain their explicit security-review scope. Passing policy does not mean zero vulnerabilities.
3. Publish only accepted immutable IDs and independently verify anonymous manifests, source/config/ordered layers and fresh remote blob bytes. Preserve failures and previous0.4.6 identities. The Docker daemon is shared and provenance unsigned; no host-isolation or SLSA claim.
4. Commit actual publication records, pass final readiness and required checks, then merge normally.
5. Verify six stable releases, Store and Local Download. Exact0.4.7 HAOS upgrade, real Ingress roles, operation recovery and backup/restore acceptance must be recorded separately.

Seven source version bindings advance; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud publish. OpenDesign stays disabled and Odoo Manage archived. No production HAOS rollout, off-cluster backup or full restore completion is implied by this candidate.
