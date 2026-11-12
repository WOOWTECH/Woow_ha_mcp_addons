# 0.4.12 image publication

Status: **six exact-source images published and independently verified** (2026-11-07 UTC). Final docs CI/readiness, the normal PR #72 merge and distribution remain separate gates.

PR #72 image source is `359963f44a55639345dae9a4846454c20230ac8e`, tree `9baa532ad02e9af60b7e3920cdc606779aac245f` (432 full-history commits; canonical archive SHA-256 `dc16bc331b979ab9ccc2023cfeb8b0ece32592a6b8f6bf278af2fb385d91e4df`). The later publication-doc commit is not the image source.

## Exact source and scope

The release branch is based on the protected `claude-delivery` merge `6834b16c271caf015c090291718320f4bfb966b5` (PR #71), whose parents are `585365f7926aee1263b1f4fb1e2feb0e2cfba499` (the PR #66 merge) and `c0fb5de98cafb483fdadbc3d36de3f479d313e4d` (the PR #70 head); #71 brought PRs #67–#70, which had been merged into their stacked base branches, into `claude-delivery`. `claude-delivery` stayed at `6834b16` for the whole release (the helpers re-checked it at every phase).

- **Odoo (PR #65, #66).** The readiness probe tells a login Odoo refused (`BACKEND_AUTH_REJECTED`, fixed text) from a server that cannot be reached; tool calls wait up to 30 s for Odoo, as the PaaS server does (the probe keeps 5 s); with "Allow Unreviewed Methods" off `execute_method` runs every method of the reviewed read list; `health_check` reports 41 tools; the admin API answers 400 instead of 503 to a `null` body on `PUT api/odoo/write-switches`.
- **n8n (PR #67, #69).** `n8n-mcp` runs on the pinned native better-sqlite3 12.11.1 (the PaaS image's engine) instead of the sql.js fallback; the build downloads one pinned prebuilt from github.com (URL, size and sha256 in `packaging/inputs.json`); `n8n_delete_workflow` says how to delete a published workflow, as on PaaS.
- **Hermes (PR #68).** A cloud-metadata MCP URL is refused with the PaaS sentence (`INVALID_INPUT: url blocked by SSRF protection: Cloud metadata endpoint blocked`); the unique-local metadata addresses `fd20:ce::254` and `fd00:a9fe:a9fe::1` are refused.
- **Every Python child (PR #70).** A request path may carry a literal `%` as long as no decoder can read more into it than the first decode gave; httpcore's `target` request extension is refused.
- **Documentation.** Every add-on's DOCS states that it publishes tools only (no prompts or resources; only Nextcloud sends server instructions, the same text as the PaaS server).

The registry keeps its **136** reviewed output-schema entries; registry guard `214b09f9c60db0dfc3244eb786f7b6774d22d8020c5d79aefa7fdffc02d0144d`. Seven add-on manifests, seven Dockerfile build-version defaults and the core `serverInfo` version advance to 0.4.12. Only **Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud** are Store-enabled image products; OpenDesign stays disabled and Odoo Manage remains archived.

Before the release, the candidate source tree ran against real backends next to the PaaS woow-mcp-server (Odoo and n8n: 499 paired steps; Hermes and Nextcloud: 584 paired steps): no candidate defect. One pre-existing defect ships unchanged on both sides: a Nextcloud `read_text_file` ETag can carry Apache's `-gzip` suffix, so an update or delete with it fails `ETAG_MISMATCH`; the fix is planned after 0.4.12 for HA and PaaS.

## Exact-image publication

Approved plan SHA-256: `3402de043cae4d6d24b54d93ce79a2cc805e488478b04ba9d4a89acdf56dd2a2`. Source freeze: `73b9fa3a2212e240cd7f8657efb41e7dd98a887830c7a6b918c972a28e71ebfe`. Builder helper freeze (`ADAPTER-FREEZE.json`): `fd647703c3fca9abf2563338c062ba39ad01ac1542c4c5c91ab2e7c058db730f` (preparation freeze `cca52be6814d5fa5a73fc10d7b6324258645e552657496a4b5bac8e5d734e6ef`).
Exact-source checks and WVT passed in the hash-bound source-CI input (3482 Python tests, 71 browser cases, 174 packaging tests with 5 skipped). Under release gating #148 the two Upgrade comparison jobs of the version-changing head can only fail before the images exist; the helpers accepted exactly that failure (GHCR answered `not found` for the six 0.4.12 tags and nothing else failed). The Store's category 1/4 comparison and its upgrade test run first on this publication-doc head, and the `claude-delivery` ruleset requires them green before the merge.
Actual exact-source UI receipts report 54 unit tests and 71 browser cases, with zero failures.
All six linux/amd64 images passed P1–P5, current/full-history/image-layer secret scans, SBOM/CVE/license policy, packaged-runtime checks with owned mocks, installed-package checks, exact UI bytes and UID10001 DAC.
The Hermes and n8n security runtime probes ran on the accepted image IDs (Hermes: the PR #68 metadata refusals; n8n: the native addon's member bytes, version, an in-memory database with FTS5 and SQLite 3.53.2). The 0.4.12 P4 supplement ran on the same accepted image IDs with owned loopback fakes and no HAOS or real backend, including the new Odoo error cases and the Nextcloud literal-`%` cases.
Accepted 0.4.11 image IDs were verified read-only and not retagged, deleted or adopted.

Each successful canonical gate has its own cleanup receipt confirming private files absent and journals preserved.
Scanner/precise triage policy and historical independent-security-review limits remain unchanged.
Policy pass does not mean zero vulnerabilities.

Anonymous immutable manifest/config/source/platform/ordered-layer verification passed. Fresh remote downloads verified
86 unique blobs, 106 ordered layer positions and
337,959,326 compressed bytes, including compressed digest/size and uncompressed diffID.
No Docker daemon or local layer cache was used for that fresh verification; CDN cache bypass is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned; accepted local images remain.
See [actual image provenance](../provenance/release-0.4.12-images.json) and
[remote layer proof](../provenance/release-0.4.12-remote-layers.json), copied byte-for-byte from completed receipts.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:0c196747e6addadbbd1d2b802673d964a673dbfa3efdfbe48e0e6fec1da82121` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:a25bbfb488a475eaa7dfc83b06fbd5f2bc1b8d78b25c682018548ac92c8987d2` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:93a962efed8e9fc8d1c5944b374cae314475eba8e850ddc43a676a077bf1bb73` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:08b29d1545e0bf982fcfeed91f809e25b78df6b1997ba6f98d5bcb11b5e01b81` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:59f01c9112151df4bfbf7d266cd77204ac668716b8f5486bd8f50f0689b2f6d0` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:5551395ddd2637e63776eb2fe30d8e239e9f1d06b7261b40146b8581dbcc08ef` |

The release was a single first attempt. It pinned the 0.4.11 baselines with stopped containers during the run (removed afterwards), retried only idempotent reads, and ran while the Gitea runner that shares the builder daemon was disabled (it was re-enabled afterwards).

OpenDesign is disabled and source-version-only: no OpenDesign image, image gates or publication. Provenance is unsigned; the daemon is shared. No SLSA, host isolation or hosted BLD2 admission is claimed. Stable Releases, Store/Local Download and actual HAOS/backend/restore acceptance require their own evidence.

## Remaining gates

1. **Docs head checks and protected distribution.** This publication-doc commit must pass the required checks: readiness (six 0.4.12 images anonymously pullable and this decision) and the Upgrade comparison, which pulls the published 0.4.11 and 0.4.12 amd64 images, compares configuration and upgrade notes (category 1), scans both with the Store's Syft and Grype database (category 4) and runs the upgrade test for the first time on these images. Then the normal PR #72 merge (merge commit) and the Store sync publish the Stable Releases and Local Download.
2. **Post-release HAOS acceptance.** On the dedicated HAOS test host, upgrade to the six actual immutable 0.4.12 images and verify Supervisor/ingress/admin and non-admin roles, tool catalogs and schemas, the admin API's 400 for a `null` write-switch body, AppArmor/uid/image identity, token/policy lifecycle and backup/rollback. Production tenant upgrades follow separately.
