# 0.4.10 image publication

Status: **six exact-source images published and independently verified** (2026-11-04). Final docs CI/readiness, the normal PR #47 merge and distribution remain separate gates.

PR #47 image source is `78a4e69cde0e4a36f8287b90b88bd658fab2bac6`, tree `65ee0f412cc525bf63c5b18810055bba255a574a` (384 full-history commits; canonical archive SHA-256 `c9f3aa55a0731c7b61c9fb62b71a3582c8c6b1babdb43a640934877ecaf20e05`). The later publication-doc commit is not the image source.

## Exact source and scope

The release branch is based on the protected `claude-delivery` merge `fb3f94cdf7a74c8d937a912e8e5063d375072978` (PR #56), whose parents are the PR #55 merge `4f034246e2ef7a0abfbf6a7533c95a4e145c5eca` and the reviewed PR #56 head `b02e1787a42c077f200e34b556dc19727bb09967`. The base also includes the PR #54 merge `274f226edc1e4616a63835247b37ef8de6d6d25f`, the earlier `cc784478` merge (PRs #46, #48, #49 and #50), and source PRs #51, #52 and #53.

- **Odoo.** PR #46 propagates `search_read`/`read_records` failures and bounds successful generic `search_records`/`read_record` results at 2 MiB by default. PR #48 adds 41 output schemas. PR #56 restores bounded upstream read-only retry after XML-RPC connection drops/timeouts while preserving `BACKEND_UNAVAILABLE`/`BACKEND_TIMEOUT`; writes remain one attempt, and the pinned destination, redirect denial and grants are unchanged.
- **n8n.** PR #49 corrects the exact n8n-mcp 2.96.2 workflow validator schema for object-valued warning/error details and advertises both validator schemas. `7cac166822c60c891c821135cf4c78ae3a0bff4b` updates `apps/n8n/package-lock.json` from `follow-redirects` 1.16.1 to 1.16.2 (GHSA-mrwp-f3q8-3g9p) after an earlier 0.4.10 attempt's n8n gate rejected 1.16.1. `78a4e69` rebinds the n8n output-schema source pin to `7cac166` and the lockfile hash to `1d128f699b0a9d4bf1018e5208f01e371469a4e639ebd0c9d4ef452fb367d6fa`.
- **Hermes.** PR #50 adds 11 output schemas and PR #53 improves dashboard connection and missing-configuration guidance. Source-only PR #57 was merged into this release branch as `5420b95f00fe6121ada9cceee6de677140f2c905` (tree `3b55ba58de04114d10e794b7899aba1c2de0d65c`) from its checked head `ca75199a897f13bcd938756f91c29da1cddf7f89`. It aligns fixed public Dashboard error categories, rejects malformed/deep/non-object response shapes and keeps an ambiguous cron creation to one POST with an outcome-unknown result. PR #57 changed no add-on version, manifest, Dockerfile, tool name, input or grant.
- **EMQX.** PR #51 bounds public errors, rejects redirects and avoids returning raw broker responses or request paths; PR #52 adds 39 exact output schemas to the gateway and fallback.
- **Nextcloud.** PR #55 vendors safe diagnostics: only a fixed quota category may appear in recognized failures, while arbitrary backend text and redirect `Location` are withheld. Its five-file output-schema provenance is bound to source commit `3abcf334e108118771e94a48ed20684d361085e9`; the eight schema entries, tool names, inputs and grants are unchanged.
- **LiteLLM.** Version synchronization only.

The registry has **136** reviewed output-schema entries (Odoo 41, n8n 2, Hermes 11, EMQX 39, LiteLLM 35, Nextcloud 8); `7cac166`/`78a4e69` changed none of them. Source pins: Odoo, EMQX, LiteLLM and Nextcloud `d6403f263f5246288864c15381c2d1bddbb9179c`; n8n `7cac166822c60c891c821135cf4c78ae3a0bff4b`; Hermes `607d6a5c886113be6e9bc83f1418c6a64e895974`. The registry guard is `8699eec8191476301aded4f9b5ab371bb543b0b9b8f6a7c7635ff691136750c1`; `e4dee324984842714e2957196b1a240a9fad2b95723caae897db4042f277ac44` (post-#57) and `db853c40b3eba47739bca9a325e329ec9723a44b836ed41685f7dbf77d41d8f1` (pre-#57) are historical.

Seven add-on manifests, seven Dockerfile build-version defaults, the core `serverInfo` version and the CI/manual-release bindings advance to 0.4.10. Only **Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud** are Store-enabled image products. OpenDesign is source-version-only and remains disabled; Odoo Manage remains archived. Apart from the n8n `follow-redirects` lock update, no dependency lock, base digest, permission, setting schema, tool name/input/grant, scanner policy or precise secret-triage allowance changed.

Odoo metadata boundary: the independent PaaS 169f comparison found 40/41 input schemas equal when importing the *unmodified installed HA wheel directly*. That import bypasses the shipped `start_switches.py` entrypoint, whose source-guarded overlay replaces `execute_method.method.description` before MCP listing. The HA decision/text module and PaaS 169f module have the same SHA-256 (`b4852fb0ebd78b6d10c4a3fcd401d0d16eeb21a129ea3b2ece3b19e30c4a4b8d`); the served all-on child listing, gateway fallback and management catalog use the PaaS wording that warns about unreviewed side-effect methods, and a focused test pins that exact wording. The raw-wheel 40/41 result remains accurate for that bypass path. The exact Odoo image passed the 41-output-schema gateway check below; image-level input-schema parity with PaaS belongs to the post-release HAOS acceptance.

## Exact-image publication

Approved plan SHA-256: `65dfea74bc391816ae404c46a92070a4cba4d2d55a2d4b11418518ee79ca638b`. Source freeze: `c4a14b4518632d9cb4b5d0ffc81c95d4010be3429dc4b6c680a1b2b13a40b321`. Builder helper freeze (`ADAPTER-FREEZE.json`): `c0ff6d56800215a604cdab0c0682c8c1f04e6fe0e0cb369a253bfb4f55377210`.
Exact-source checks, WVT and Upgrade comparison passed in the hash-bound source-CI input.
Actual exact-source UI receipts report 54 unit tests and 71 browser cases, with zero failures.
All six linux/amd64 images passed P1–P5, current/full-history/image-layer secret scans, SBOM/CVE/license policy, packaged-runtime checks with owned mocks, installed-package checks, exact UI bytes and UID10001 DAC.
The 0.4.10 P4 supplement ran on the same accepted image IDs with owned loopback fakes and no HAOS or real backend: gateway output-schema counts against registry `8699eec8…` (Odoo 41, n8n 2, Hermes 11, EMQX 39, LiteLLM 35, Nextcloud 8), representative result/error cases for every product, 11 Hermes error/guidance cases and 19 Nextcloud safe-diagnostics cases.
Accepted 0.4.9 image IDs remain preserved.

Each successful canonical gate has its own cleanup receipt confirming private files absent and journals preserved; all six record `deadline_elapsed: false`.
Scanner/precise triage policy and historical independent-security-review limits remain unchanged.
Policy pass does not mean zero vulnerabilities.

Anonymous immutable manifest/config/source/platform/ordered-layer verification passed. Fresh remote downloads verified
84 unique blobs, 104 ordered layer positions and
324,502,879 compressed bytes, including compressed digest/size and uncompressed diffID.
No Docker daemon or local layer cache was used for that fresh verification; CDN cache bypass is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned; accepted local images remain.
See [actual image provenance](../provenance/release-0.4.10-images.json) and
[remote layer proof](../provenance/release-0.4.10-remote-layers.json), copied byte-for-byte from completed receipts.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:7e683111b3a06976fa5ad8a43fe877267de2aadeb4fbad2b0f8e5995c22c5b25` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:990e12c44250d841b6121425fb93487092b4ae4bfcc1c7166111a07f30078ad3` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:7c2e7f9dd5c1bb54d597247098731ebe90743c2752d7e2f49478e9bc869a46a5` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:26202df1d2ebfef7ddc30759ccf97f50f160da597d8242f547ea134ff869ede5` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:6fb54c713f3c676fecfd2ac711001fd42f2f50f4edfc97c4d6d8dcde726ca0af` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:7f9d3883bf69ec3d8676a7d72242b8aba96c0a3c1382cbbd9a89f18be65c7f84` |

### Earlier attempts and the provenance adapter

Three earlier 0.4.10 attempts closed fail-closed and published nothing. r3 and r4 used source `eeeedcae30968bc176a398b2d71438b9f1d337e4`: r3 closed at preserve because the preserved 0.4.9 baselines were missing (operator diagnosis: the builder daemon's nightly image prune had removed them; they were restored from GHCR by exact ID), and r4 closed at the n8n gate, whose supply-chain policy rejected `follow-redirects` 1.16.1 (see the `7cac166` commit message). r5 used `78a4e69` and closed at the n8n cleanup on an uncertain disk sample (`sample_uncertain` in its disk-budget journal). Their local candidate images were removed by exact ID and none is reused. The successful attempt pinned the 0.4.9 baselines with stopped containers during the run, retried only idempotent reads, and ran while the Gitea runner that shares the builder daemon was disabled (it was re-enabled afterwards).

The provenance helper re-validates each gate's P4 supplement by comparing dictionary key order with fixed tuples, but gate receipts are stored with sorted keys, so it rejected all six although key sets, values and counts matched. The provenance was therefore produced through a disclosed post-release adapter: in memory only, it re-ordered `p4_supplement.probes` and the Hermes/Nextcloud error-case maps to the expected order when their key sets were exactly the expected sets, then ran the unchanged validation, including every per-probe check against the gate image ID. The adapter (SHA-256 `bd0c6737a9da014ca1ebe0b3e8081380e26adb1fd08f053b513717301db94ac1`) records itself in the provenance field `post_release_adapter`; no helper byte changed.

OpenDesign is disabled and source-version-only: no OpenDesign image, image gates or publication. Provenance is unsigned; the daemon is shared. No SLSA, host isolation or hosted BLD2 admission is claimed. Stable Releases, Store/Local Download and actual HAOS/backend/restore acceptance require their own evidence.

## Remaining gates

1. **Docs head checks and protected distribution.** This publication-doc commit must pass the required checks, including readiness (six 0.4.10 images anonymously pullable and this decision). Merging the version PR publishes to the WOOW App Store (`AGENTS.md`); afterwards read back all six Stable Releases and the Store/Local Download source/config/image references.
2. **Post-release HAOS acceptance.** In a separately reviewed, capacity-reserved and isolated HAOS fixture, install the six actual immutable 0.4.10 images. Verify Supervisor/ingress/admin and non-admin roles, tool catalogs/input/output schemas/effective grants, same-product/same-synthetic-backend Odoo success/error/oversize, n8n object-warning/error, EMQX errors/output contracts, Hermes output contracts/dashboard guidance, fixed public errors, malformed/deep/non-object replies, bounded nested projection and ambiguous cron-create outcome after exactly one POST, Nextcloud safe diagnostics, auth/token/policy lifecycle, and backup/rollback/cleanup. Odoo's read-error/result-limit change needs the same synthetic Odoo 18 backend on both PaaS and HAOS for a parity conclusion. OCI-Pod observations outside Supervisor do not close this gate. Production tenant upgrade and full off-cluster restore need their own authorization and evidence.
