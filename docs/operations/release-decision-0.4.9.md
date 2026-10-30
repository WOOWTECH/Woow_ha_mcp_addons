# 0.4.9 image publication

Status: **six exact-source images published and independently verified**. Final docs CI/readiness, normal PR44 merge and distribution remain separate gates.

PR #43 normally merged as `118d7429fb46b47a5b35f5dab82318968b6fdb5f`. PR #44 image source is `2a485662ecfa8b2452d5e02d83ca39cebf5d3bb0`, tree `8a1cee636d94c71e359556a66649c3a24686524d`. The later publication-doc commit is not the image source.

Hermes ports the two reviewed functions and unchanged session-mutation helper from PaaS
`052887fa68d5e67b86c622ef92f46dd7f75a08ca`. DELETE reads fresh Agent fences, sends one request,
verifies absence and permits only explicit replay of the unchanged three-field identity.
It does not resend DELETE after401 or an uncertain response. The Agent mutation-snapshot/receipt
contract is required; no unfenced fallback is added. See [the exact contract](../../apps/hermes/docs/session-delete-contract.md).
The session description and optional arguments change; the 11 tool names, grants, destination policy,
redaction, shared state format and other products' behavior retain the reviewed source contracts.

Seven add-on manifests and seven Dockerfile defaults advance together. Only Odoo, n8n, Hermes,
EMQX, LiteLLM and Nextcloud are enabled for publication; OpenDesign remains disabled and Odoo Manage
remains archived. Python 3.13.18, Node/uv pins, dependency locks, scanner policy and precise triage stay pinned.

Use the existing 0.4.8 private flow with new exact-source bindings: source CI, six immutable image builds,
P1–P5 and exact UI/runtime checks, immediate successful-gate private cleanup, accepted-ID publication,
anonymous manifest/config/ordered-layer verification and fresh remote full-blob/diffID verification.
Preserve the accepted 0.4.8 image IDs and all historical receipts. Generate 0.4.9 provenance only from
actual new receipts. A later docs commit must pass normal required checks and readiness before Main
merges the version PR; the normal merge pipeline then emits six Stable Releases and syncs Store/Local Download.

Shared-daemon and unsigned-provenance limits remain. Source/image gates do not claim actual HAOS,
customer backend, backup or restore acceptance. The completed image publication is recorded below; it does not grant admission to any HAOS or customer workload.


## Exact-image publication

Approved plan SHA-256: `c11318b3c855d2ae484ca675a7e185a6286d869a7f92453c8c162d7d18531b8c`. Source freeze: `5463c9f48e95ff8db11410b02b5afca57f8f6215d1c024ca263189585ea13201`.
Builder helper freeze (`ADAPTER-FREEZE.json`): `6e8748b1dece6a37eea372412b4b6cc12b1a4f92f25b4407806a35a51974aa1a`.
Exact-source checks, WVT and Upgrade comparison passed in the hash-bound source-CI input.
Actual exact-source UI receipts report 54 unit tests and 71 browser cases, with zero failures.
All six linux/amd64 images passed P1–P5, current/full-history/image-layer secret scans, SBOM/CVE/license policy,
packaged-runtime checks with owned mocks, installed-package checks, exact UI bytes and UID10001 DAC.
Nextcloud retains output-schema `ha_commit` `03833340f11f78200062a731662e35d05dd9ec83`. Accepted 0.4.8 IDs and historical failed 048 R2 image
`sha256:033424ac1ff06eb6b433b70f291585329d965d3bff56699923678a897dde90d9` remain preserved; the failed image is not reused or reclassified.

Each successful canonical gate has its own cleanup receipt confirming private files absent and journals preserved.
Recorded `deadline_elapsed` values remain truthful; no cleanup timeliness claim is inferred from success.
Scanner/precise triage policy and historical independent-security-review limits remain unchanged.
Policy pass does not mean zero vulnerabilities.

Anonymous immutable manifest/config/source/platform/ordered-layer verification passed. Fresh remote downloads verified
83 unique blobs, 103 ordered layer positions and
324,082,591 compressed bytes, including compressed digest/size and uncompressed diffID.
No Docker daemon or local layer cache was used for that fresh verification; CDN cache bypass is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned; accepted local images remain.
See [actual image provenance](../provenance/release-0.4.9-images.json) and
[remote layer proof](../provenance/release-0.4.9-remote-layers.json), copied byte-for-byte from completed receipts.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:712797b4d9c26dd537116d7604ee09baa4d552c1d44e3aa2e38cf7ea8d947fdf` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:672dc849b14943f47c467199d145f1567a012369ee01e387efec7bb46ff76ee9` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:365a053f8070a9581583a4e5e6ff61544f14ba5e8e41b154b090e0ce0d59ddb3` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:4aae905d1cb4f685bbb236269779e1906438914c626b6ebaadd41a88dc4a187b` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:24e618ed8ebb6bfef4ac67d54458b04942d3c23e4975fe3f3267f012a07c6d27` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:ac31985a39f34a2bc7653566d389fde92ce54c86a926f88d3c672578dd262404` |

OpenDesign is disabled and source-version-only: no OpenDesign image, image gates or publication. Provenance is unsigned; the daemon is shared. No SLSA, host isolation or hosted BLD2 admission is claimed. Stable Releases, Store/Local Download and actual HAOS/backend/restore acceptance require their own evidence.

### HA Hermes Agent compatibility

The independent published-artifact review establishes HA Agent **0.1.10** as the minimum proven compatible release: HA source `d74dad5356bdc6d6d1fc903d30219bc8fa9b9a47`, registry index `sha256:06011c55856a661c460870e69537667f58e5cacf5a942725c903fa2d5e9f725c`. The adjacent **0.1.9** artifact lacks mutation snapshots and revision/generation fences.

The reviewed **0.1.14** artifact contains authenticated snapshots, revision/generation CAS and durable principal-bound exact-replay receipts. Its chain is HA source `61ddab31dd18d2f197f0448e9db0f6525ffdd8bb` → index `sha256:e5090b50df397accab6487991fadb8fe0e57c1fea35cf1996197f295aaf5275d` → amd64 manifest `sha256:7c75cc12dbbb341371f6e3a0dc26a09351623d0b5dcbf8ee019e8f55945b664f` → config `sha256:c5331f58c6f4e825166af7a39a48e2573777198173173d230c40a71812d58da1`. These distinct digest types must not be conflated. This matches Carver's recorded ws97 inventory at 2026-10-30T14:24:36Z; no Agent upgrade or backend source fix is required for that recorded 0.1.14 installation.

This proves published artifact/source compatibility, **not live HA049 acceptance**. PaaS Agent `20261025.0421` / `39718…` is port provenance only, not the HA Agent identity. Missing contracts continue to fail closed without unfenced DELETE. Fixed public sources: [HA 0.1.10 Dockerfile](https://github.com/WOOWTECH/Woow_ha_hermes_add_on/blob/d74dad5356bdc6d6d1fc903d30219bc8fa9b9a47/hermes/Dockerfile), [HA 0.1.14 Dockerfile](https://github.com/WOOWTECH/Woow_ha_hermes_add_on/blob/61ddab31dd18d2f197f0448e9db0f6525ffdd8bb/hermes/Dockerfile). Operator-retained independent report SHA-256: `10d3700b782e1bb6147ba4ae461444cb9c4ad80880a37f39339726a95ffce3de`; artifact manifest SHA-256: `9eae463f71ee0eee298958732566159e33416ce4316859d1d8365f1911bf0836`.
