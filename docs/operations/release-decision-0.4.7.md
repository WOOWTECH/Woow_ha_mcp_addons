# 0.4.7 release decision — 2026-10-30

Status: **six exact-source images published and independently verified**. Final publication-record checks, normal merge and distribution remain separate gates in [PR #40](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/40).

## Contents and compatibility

All persisted administration changes require the exact strong If-Match revision reviewed by the caller. Missing revisions return428; stale or malformed revisions return409 before a new effect. Token rotation/revocation and child restart additionally require one Idempotency-Key. The bundled UI uses the server clock plus a cryptographic random suffix, retains only the operation identity/revision in sessionStorage, and offers explicit query or same-ID resend after an uncertain response.

A private bounded journal persists an intent before the effect and a completion afterward. Completed replay returns fixed non-secret outcome labels without repeating the effect. A crash can leave an unknown outcome; unknown intents never automatically execute again. Fresh HA administrator authority is checked under the mutation lock before disclosure or replay, and receipts are bound to the original user. Revoke now returns200 JSON instead of204; custom API clients must adopt the headers and response contract. MCP tool calls and provider/backend permission boundaries are unchanged.

This is not an exactly-once transaction with the child process. Backups must retain the full data directory including the hidden journal. Restore/downgrade requires compatible data/binary and independent review of current tokens, child state and outstanding client intentions. Older backups cannot retain receipts created afterward. See [API contract](../admin-write-contracts.md) and the root upgrade notes.

EMQX retained-message failures now propagate instead of being converted into empty lookups or a second publish. The source tests reproduce the failures before the fix and verify one dispatch, explicit404 lookup compatibility and valid204/202 results afterward. Tool names, input schemas and grant defaults are unchanged. The P9 operator kit also uses the shared management client, validates receipts and stops after ambiguous responses without retrying.

## Evidence and release gates

The integrated source includes HA implementation9af732a and real-backend harnessd71d352. Focused implementation checks, an independent journal review, exact-source CI and fresh browser results passed; publication evidence follows below. The backend harness contains actual Odoo18, Nextcloud35.0.2 and EMQX5.8.9 acceptance, but its completed runs exercised the recorded0.4.6/PaaS sources, not this candidate. Tests of older images do not establish0.4.7 runtime acceptance.

Required before distribution:

1. Exact committed source checks, Release train, upgrade comparison and independent integration review.
2. Six linux/amd64 images through the existing private builder: P1–P5, current/full-history/layer secret scans, SBOM/CVE/license policy, final package checks, packaged runtime, exact UI and UID boundaries. Existing precise secret-triage exceptions retain their explicit security-review scope. Passing policy does not mean zero vulnerabilities.
3. Publish only accepted immutable IDs and independently verify anonymous manifests, source/config/ordered layers and fresh remote blob bytes. Preserve failures and previous0.4.6 identities. The Docker daemon is shared and provenance unsigned; no host-isolation or SLSA claim.
4. Commit actual publication records, pass final readiness and required checks, then merge normally.
5. Verify six stable releases, Store and Local Download. Exact0.4.7 HAOS upgrade, real Ingress roles, operation recovery and backup/restore acceptance must be recorded separately.

Seven source version bindings advance; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud publish. OpenDesign stays disabled and Odoo Manage archived. No production HAOS rollout, off-cluster backup or full restore completion is implied by this candidate.


## Exact-image publication

Image source: `f464c5a0c87f2873f8e7efcfb0537ed0cf82ce5b`; tree `f68ddd4dc19f8942ea43286a7da0462b42cbb726`. The later documentation commit is not the image source.
Fresh hosted source checks passed 3,139 Python tests and 71 browser cases; WVT and Upgrade comparison passed.
The fresh UI build also passed 54 unit tests and 71 browser cases; 68 private-helper guards passed.

All six linux/amd64 images passed P1–P5, packaged runtime with owned mocks, current/full-history/layer secret
scans, SBOM/CVE/license policy, final installed package checks, exact UI bytes and UID10001 DAC. Prior 0.4.6
image IDs were preserved. Scanner and precise secret-triage policy bytes are unchanged; their security review
scope and exact exceptions remain explicit. Passing policy does not mean zero vulnerabilities.

Only accepted immutable IDs were published. Anonymous manifest/config/source/platform/ordered-layer metadata
checks passed. A separate fresh download verified 83 unique remote layer blobs
covering 103 ordered image-layer positions and
344,170,287 compressed bytes; every compressed digest/size and uncompressed
diffID matched. This verification used neither Docker nor a local layer cache; CDN cache state is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned. Accepted local images remain.
See [image provenance](../provenance/release-0.4.7-images.json) and
[remote-layer evidence](../provenance/release-0.4.7-remote-layers.json).

Provenance is unsigned and the Docker daemon is shared. No SLSA, host-isolation or hosted BLD2 admission is claimed.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:5cbf15ce90c74609b7c215a81be1764431e6d2405705101747544180e18f4b89` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:181b2116e1e52509d9610519c4e195356541e6ef42976b0d39f41828aba3b62b` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:ffc637bf17184a516f5a3969f17e70d54f5263e87f63241349bd07c9661ed063` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:03bf217db61c5bf9ddacc4207ca7bb0e95301943034953c9a0a4a2e4ad2a58ba` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:16439f35d3ca41cfeb768d4f9554bc7d0db42dae68ed0da0d721998deb3e21cd` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:eae49ad5004d6c91647591babd4be770ee185ab1d16336d9fced0440cc5b32c9` |

HAOS upgrade/settings/partial restore and real-backend acceptance are separate evidence. These image gates do not establish a ws97 reinstall, off-cluster backup or full production restore.
