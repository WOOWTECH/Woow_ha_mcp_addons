# 0.3.1 image publication decision — 2026-10-24

Status: all six canonical images passed fresh P1–P5 gates, were published without rebuilding, and were anonymously verified by immutable manifest/config/rootfs identity. This records completed image publication. Normal exact-head PR checks, protected merge, per-addon stable Releases and Store synchronization remain root-owned subsequent stages; they are not inferred from image publication.

## Exact source and documentation boundary

Every accepted image was built from `93dfa3dcbef3902b400707e054f0be6c4065621b` (tree `d95ad6213607aa1aa3afcaf7941ce1b21eb92152`). The user authorized merge/release. This record binds the successful **C2** operator-local continuation and its fresh completed receipts. Earlier failed packaging attempts remain separate; a failed image is not an accepted subject. The continuation retains the same frozen source and canonical Dockerfiles, validates canonical context bytes/modes, and re-runs the full gates. No failed attempt's image or receipt is relabeled as accepted.

The later commit containing this decision, README update and [image receipt](../provenance/release-0.3.1-images.json) is a **documentation head**, not the image-source commit. Root verifies the exact documentation head and final merge with the read-only closure helper: runtime, dependencies, child pins, Dockerfiles, entrypoint and tested UI remain identical to the image source. README is excluded from the Docker context. The decision document is included by the parent docs allowlist but is not copied by the canonical Dockerfiles. The new image receipt is under `docs/provenance`, which all six Dockerfiles copy; it was absent from the already published images. A future rebuild would include that new receipt, so full shipped provenance/tree byte equality is explicitly not claimed. No rebuild is needed merely to insert a post-publication receipt into its own image.

## Completed image gates and publication

P1/P2 bound the clean committed source, full reachable history, canonical archive and extracted context. P3 built each canonical linux/amd64 image. P4 ran exact packaged-runtime acceptance with owned mocks. P5 retained source/history/all-layer/config/evidence secret scanning, SBOM/SPDX, the fresh vulnerability database, and the original vulnerability/license policy. Passing policy does not mean zero detected vulnerabilities. Scanner pins/policy and exception thresholds were not relaxed. The accepted image IDs, diff IDs, database, counts and sanitized evidence hashes are in the image receipt.

The publisher checked unused destination refs, pushed the accepted IDs without rebuilding, performed anonymous immutable pulls, and removed its private auth config and owned temporary aliases. The independent verifier checked tag/immutable manifest bytes, config digests and rootfs diff IDs against those gates. Exact image UI bytes match the browser-tested `dist/assets/app.js` SHA256 `f20cdd713606aeaf05ff3a4183ad5c5603e089680665d7514ab025d6c7520871`, closing the literal-null fix's packaged-byte requirement.

| Product | Immutable published image |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:6f184215439c905e385be1302379373b0c90ac0e3539b79219e4587b1967e296` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:971263ced50afec6dc2e4ce2f98337e97ee84bce7a0899276802a48d65e99681` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:ba5f89bcb61523edfaf3cd48dcea60bc0bdd4575bcbce7a9a9e89e31cd1a4728` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:9d7dc5b940b181a3283cbbcc5362b123006ec641f8de71ba34d2fb9e7e4c92f8` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:b229421781c9d6565898590c23d347e9af675c24fe890bdb2f589022cf18ccaa` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:cee4f430ab6c22e38f2a33aae595e536a0d3b70a3e5e63b91254a5f8a6096d2c` |

OpenDesign remains Store-disabled and is not published. Odoo Manage remains archived. The route is explicitly operator-local on a shared daemon, with unsigned receipts. It is not host isolation, hosted BLD2 admission, signed provenance or SLSA certification. The sole-publisher declaration covers cooperative ownership of these six refs, not global daemon idleness or registry compare-and-swap. BLD2 admission remains blocked; `RELEASE-GATES.json` and the closed manual release workflow are not bypassed.

## Behavior and upgrade notes

Configuration status distinguishes a durable save from successful application by
the current child generation. Backend health stays separate. Optional exact
`If-Match` checks reject stale saves with HTTP 409 before mutation; the new UI
retains drafts until explicit reload. Clients omitting the header remain
compatible without conflict protection. Revisions are process-local, so a
management restart requires old editors to reload. A save that commits before
child replacement fails returns HTTP 503 with `saved:true` and safe failure
metadata; the UI reports saved but not applied and does not retry automatically.

Persisted token revoke/rotate cancels active request I/O and actual ASGI sends,
including blocked sends and open GET/POST streams. Both Bearer and secret-path
routes are covered. No child restart is introduced; bytes already delivered and
backend effects already dispatched cannot be rolled back. HA does not expose
legacy `/sse` or `/messages` endpoints. See [the API and lifecycle contract](../runtime-configuration.md).

Maximum functionality remains the fresh-install default. Existing schema 4 keeps
its saved policy. Schema 1/2/3 retains 0.3.0's authenticated HA Ingress prestart
review before ProductStore or the MCP child starts: `all_on` is preselected, but
an administrator must confirm it or explicitly choose `preserve`. Refresh does
not migrate. Until confirmation, MCP/readiness returns 503. Back up first and
open the panel after upgrading legacy data. Tokens, including revoked state, are
preserved. [Migration](legacy-migration.md) and [backup/rollback](update-backup-rollback.md)
constraints still apply. There is no new schema migration, dependency/child pin,
option, port, architecture, image name or privilege change in 0.3.1.

## Functional evidence and limits

The original isolated Hermes candidate on `e94c5fa79d42ab37dcb065cdf843e000e13fb432` passed 26/26 recorded live checks: owner Ingress, saved/applied status, stale-save rejection, real status read, local write denial, an idle stream alive at the revoke barrier closing after revoke, old-token rejection, reissue/read and no token-triggered child restart. Its receipt SHA256 is `984168693ec33827ef01ba315b5916262bd26b4b4c21068279595a115fc066b8`. It is a derivative candidate, not these canonical published images. Its screenshot subsequently exposed the literal-null UI bug; that old evidence remains unchanged. Source93 includes the bounded UI fix and browser assertions; fresh image-byte proof binds that tested fix to these images.

Broader two-client GET/POST, blocked-header/send and coalesced-frame behavior has local socket regression coverage. These facts are not every-product real-backend acceptance, complete backend response semantics, an official 0.3.1 Store upgrade, or a backup/rollback rehearsal. No business write or billable inference is inferred or required. Earlier 0.3.0 receipts remain historical. The official Hermes upgrade is a separately reviewed root-owned phase with fresh VM/add-on identity, complete private backup, protected inventory, exact published image proof and the Supervisor disk guard.

## Remaining normal release stages

Root reviews this completed publication record and runs the required validations/normal checks on the documentation head before merging PR16 through protected `claude-delivery`. The existing push workflow then creates the six `<slug>-v0.3.1` stable Releases and synchronizes Store. Exact documentation-head and final-merge closure receipts distinguish those Git commits from the immutable image source. A green version-string readiness check alone is insufficient; the actual six-image evidence is required and is now recorded above. No manual tag overwrite, gated-workflow bypass or VM upgrade is performed by this documentation update.

## Publication recovery record

The first C2 publication pushed Odoo successfully, then stopped before its anonymous-pull intent. The original failure records remain byte-for-byte prefixes of the completed host and remote journals. The exact failing precondition was not retained; automatic Docker digest aliases and a transient anonymous read remain hypotheses. Root amendment `393a410bcd47217d4d1500d03694c296da287ef1dddd840c51ef86e74be7df54` authorized verification-only of the already published Odoo manifest `sha256:6f184215439c905e385be1302379373b0c90ac0e3539b79219e4587b1967e296`, followed by new pushes of n8n, Hermes, EMQX, LiteLLM and Nextcloud. Odoo was not repushed; no image was rebuilt and no published tag was overwritten. The continuation reused the same six accepted C2 gates and packaged-UI proof, repeated anonymous immutable pulls, and completed owned-alias, credential and lock cleanup. The amendment/helper hashes and preserved failure hashes are included in the image receipt. This publication continuation is distinct from the earlier C2 build-context continuation.
