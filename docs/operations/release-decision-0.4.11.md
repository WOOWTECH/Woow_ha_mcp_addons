# 0.4.11 image publication

Status: **six exact-source images published and independently verified** (2026-11-05 UTC). Final docs CI/readiness, the normal PR #60 merge and distribution remain separate gates.

PR #60 image source is `2ad4521c5b61ea144dfa1ffbc658ee16a67591a5`, tree `ff301dadcde57fb882e1fb36eeba8aba6004eb70` (399 full-history commits; canonical archive SHA-256 `bbb059200dfc584181a128fe13fdadfa68ff69e2e0351dd3905006a3815ff407`). The later publication-doc commit is not the image source.

## Exact source and scope

The release branch is based on the protected `claude-delivery` merge `024862cdc8431b97fb990e8cee0daff9a52d6833` (PR #59), whose parents are the PR #58 merge `d319945c456bc5cd7169c40d776f6180c1fdec73` and the PR #59 head `5e61e21f8194e07c633a77168cca95392e80516c`. After the source checks of `2ad4521` ran, `claude-delivery` advanced to `6a0e7b1ed757418a534bb7b126702f79db0c7b46` (PR #61, release gating #148): it changes only `.github/workflows/woow-addon-release.yml` (the upgrade comparison now scans published images) and `AGENTS.md`, none of the 31 files this release changes. PR #60 and its source checks therefore record base `024862c`, while the release required `6a0e7b1` as the live `claude-delivery` tip before every stage.

- **Hermes (PR #58).** Every MCP-visible Hermes error reads `CODE: text`, with the same code table as the PaaS woow-mcp-server. Dashboard and Gateway transport failures use fixed public wording that never repeats the configured URL, the upstream body, a redirect Location or transport text, and wrong reply shapes are rejected with fixed wording. A chat turn that the Gateway itself reports as failed, incomplete or cancelled returns `CHAT_TURN_FAILED` with the Gateway's own error message or reason; the add-on's own Gateway transport verdicts keep `BACKEND_BUSY` and `BACKEND_STREAM_ERROR`. Loopback and non-HTTP MCP server URLs are refused as `INVALID_INPUT`. Tool names, inputs, settings, grants and the 11 reviewed output schemas do not change.
- **Store label (PR #59).** The seven add-on manifests declare `stage: stable` and their store descriptions no longer start with "Experimental;"; the image `io.hass.description` label follows (verified on the published images). The retired Odoo Manage image label is unchanged.
- **Security.** The generated OS-package step of every image Dockerfile also upgrades `apt` and `libapt-pkg6.0` from 2.6.1 to 2.6.2 (CVE-2026-109518, High, fixed in 2.6.2), taken from the signature-checked Debian security snapshot `20261104T124343Z`; `libssl3`/`openssl` stay at `3.0.22-1~deb12u2`. Each gate read the final installed versions from the accepted image ID with `dpkg-query` (network none, read-only, UID 10001). The all-layers SBOM still lists the base layer's superseded `apt`/`libapt-pkg6.0` 2.6.1 records because that layer is unchanged; the vulnerability policy passed without any exception. The n8n output-schema source pin is rebound to `ab2997665f1a1f1eaf343aa10094aa25f632c7ca`, the commit that carries the changed n8n Dockerfile.

The registry keeps its **136** reviewed output-schema entries (Odoo 41, n8n 2, Hermes 11, EMQX 39, LiteLLM 35, Nextcloud 8); registry guard `e8b0a9c6201479c18078f6c3ff9669135d850866ec07e2b8356d853b9531f28c`. Seven add-on manifests, seven Dockerfile build-version defaults and the core `serverInfo` version advance to 0.4.11. Only **Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud** are Store-enabled image products; OpenDesign is source-version-only and remains disabled; Odoo Manage remains archived. No dependency lock, base digest, permission, setting schema, tool name/input/grant, scanner policy or precise secret-triage allowance changed.

## Exact-image publication

Approved plan SHA-256: `0da46808f2cf2358f98ab1cc5fd7da9b9c4dab3d8cceb88bc8e78fd743ed29bc`. Source freeze: `156e3dff76912622901bf29da2878884fdd50f8d133a6b362bbc7e1f3c8439d6`. Builder helper freeze (`ADAPTER-FREEZE.json`): `236ac2a43ed03ddd28cc2424c391bdd7ab4edae6e40d920499b22f54564fe786`.
Exact-source checks, WVT and Upgrade comparison passed in the hash-bound source-CI input (3376 Python tests, 71 browser cases, 160 packaging tests).
Actual exact-source UI receipts report 54 unit tests and 71 browser cases, with zero failures.
All six linux/amd64 images passed P1–P5, current/full-history/image-layer secret scans, SBOM/CVE/license policy, packaged-runtime checks with owned mocks, installed-package checks, exact UI bytes and UID10001 DAC.
The Hermes and n8n security runtime probes ran on the accepted image IDs; the Hermes probe expects the exact 0.4.11 behavior for 18 refused MCP URLs (11 loopback and 3 non-HTTP targets `INVALID_INPUT`, 4 shared-policy `BACKEND_DESTINATION_DENIED`) and exactly one dashboard write for each LAN/ULA target.
The 0.4.11 P4 supplement ran on the same accepted image IDs with owned loopback fakes and no HAOS or real backend: gateway output-schema counts against registry `e8b0a9c6…`, representative result/error cases for every product, 18 Hermes error/guidance cases (including the PR #58 `CODE:`-prefixed Dashboard and Gateway cases) and 19 Nextcloud safe-diagnostics cases.
Accepted 0.4.10 image IDs were verified read-only and not retagged, deleted or adopted.

Each successful canonical gate has its own cleanup receipt confirming private files absent and journals preserved; all six record `deadline_elapsed: false`.
Scanner/precise triage policy and historical independent-security-review limits remain unchanged.
Policy pass does not mean zero vulnerabilities.

Anonymous immutable manifest/config/source/platform/ordered-layer verification passed. Fresh remote downloads verified
84 unique blobs, 104 ordered layer positions and
336,482,290 compressed bytes, including compressed digest/size and uncompressed diffID.
No Docker daemon or local layer cache was used for that fresh verification; CDN cache bypass is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned; accepted local images remain.
See [actual image provenance](../provenance/release-0.4.11-images.json) and
[remote layer proof](../provenance/release-0.4.11-remote-layers.json), copied byte-for-byte from completed receipts.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:f198a3c9c99618b18e85a22fae7920bbbccca90f76c6f181da64baa744a95b77` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:62c977789688a6b5992a94801bd6a92f480d3eeff25ece77f75c49bcca73c6de` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:a49a4fa8429e78ab062ac34422f41bfe585ce8077815e4d23674e2e0811a8fd8` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:36fef7c4735d0b97cc50511ab08ebfae3703ded740e19e104412ad8940e1cd02` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:3dd40c92b72a47ef2d1354b542d8bc452185835aa37929fb8a9fc2d4e8ec791a` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:5b557049b783ab1a544f4dd78aeed5f139d7f2fe8eb92cd4de2b4069d9d2adcf` |

### Earlier attempts

Two earlier 0.4.11 attempts closed fail-closed and published nothing (all six 0.4.11 tags were anonymously absent afterwards).
The first used candidate `f7d8ebae39ca8270ebe5f8762b825290311061ee` and closed at the odoo supply-chain gate, whose policy rejected `apt`/`libapt-pkg6.0` 2.6.1 (CVE-2026-109518); the source fix is commit `ab29976`.
The second used `2ad4521` (approved plan `3189630e…`), passed the odoo and n8n gates and closed at the hermes gate: the release helper's Hermes security runtime probe, inherited from 0.4.10, caught only the old backend-failure type, while PR #58 refuses loopback and non-HTTP MCP URLs as `INVALID_INPUT` input errors. The product behavior was correct; the probe was corrected to expect the exact 0.4.11 behavior per case and now also runs offline on the exact source.
The local candidate images of both attempts were removed by exact ID and none is reused; the second attempt's builder run root (same source, same name) was renamed and kept as evidence.
The successful attempt pinned the 0.4.10 baselines with stopped containers during the run (removed afterwards), retried only idempotent reads, and ran while the Gitea runner that shares the builder daemon was disabled (it was re-enabled afterwards).
The 0.4.10 provenance key-order defect is fixed in the 0.4.11 helpers: this provenance needed no post-release adapter.

OpenDesign is disabled and source-version-only: no OpenDesign image, image gates or publication. Provenance is unsigned; the daemon is shared. No SLSA, host isolation or hosted BLD2 admission is claimed. Stable Releases, Store/Local Download and actual HAOS/backend/restore acceptance require their own evidence.

## Remaining gates

1. **Docs head checks and protected distribution.** This publication-doc commit must pass the required checks: readiness (six 0.4.11 images anonymously pullable and this decision) and the Upgrade comparison, which since release gating #148 pulls the published 0.4.10 and 0.4.11 amd64 images and scans both with the Store's Syft and Grype database (category 4 blocks only new fixable Critical/High findings). Merging the version PR publishes to the WOOW App Store (`AGENTS.md`; a merge commit, so the n8n output-schema source pin stays an ancestor); afterwards read back all six Stable Releases and the Store/Local Download source/config/image references, and confirm the experimental badge is gone.
2. **Post-release HAOS acceptance.** In a separately reviewed, capacity-reserved HAOS fixture, install the six actual immutable 0.4.11 images and verify Supervisor/ingress/admin and non-admin roles, tool catalogs and schemas, the Hermes `CODE: text` errors and URL refusals, fixed public errors, auth/token/policy lifecycle, and backup/rollback/cleanup. Production tenant upgrade and full off-cluster restore need their own authorization and evidence.
