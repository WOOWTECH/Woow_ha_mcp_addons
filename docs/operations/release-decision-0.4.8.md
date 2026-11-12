# 0.4.8 release decision — 2026-10-30

Status: **six exact-source images published and independently verified**. Final publication-record checks, normal merge and distribution remain separate gates in [PR #42](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/42). Source base is merged PR #41 at `4d81dcc408c9b8cc2bdcd1af2dffcfb74d2a962a`, following the published 0.4.7 release.

## Contents

Nextcloud vendors upstream v0.1.6 (`8aa6be3`) and its credential masking in error messages. The reviewed output-schema adaptation remains pinned to `0383334`; tool names, input/output contracts and saved connection settings are preserved. See [source comparison](../provenance/nextcloud-mcp-0.1.6-20261030.md).

Other enabled products retain the 0.4.7 runtime and management contracts. Seven source version bindings advance to0.4.8; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud publish. OpenDesign remains disabled and Odoo Manage remains archived. No dependency, scanner-policy or precise secret-triage exception is added by this release integration.

## Required publication gates

1. Exact committed-source checks, WVT release train and upgrade comparison.
2. Six fresh linux/amd64 private-builder images: P1–P5, current/full-history/layer secret scanning, SBOM/CVE/license policy, final installed package checks, packaged runtime, exact UI bytes and UID10001 boundaries. Existing precise triage entries retain their explicit security-review scope.
3. Publish only accepted immutable image IDs, independently verify anonymous manifests/config/source/platform and every ordered layer, and verify fresh remote compressed blobs and uncompressed diffIDs. Preserve prior0.4.7 image IDs.
4. Commit actual publication records, pass final readiness and required checks, then normal merge.
5. Read back six Stable Releases, Store and Local Download source/config/image digests. Record real HAOS and backend acceptance separately.

The Docker daemon is shared; provenance remains unsigned. No host-isolation, SLSA, hosted BLD2 admission, zero-vulnerability, ws97 rollout, off-cluster backup or full restore completion is claimed by source or image gates. Existing 0.4.7 HAOS acceptance remains a separate evidence lane.


## Exact-image publication

Image source: `fd7de71c18da5873d103b5ecb070405cf40b5970`; tree `238000ab284d1f62f834bceaaed551cc8a37f7d7`. The later documentation commit is not the image source.
Actual R3 plan SHA-256: `ae022b9fa3111451d8245cbeb8972e6457bd3981ab2141b32fbd4042f21ed515`. Source freeze: `6fbc10799574adb88f276ee91927bc8d5af59a429ef8ec2e51f84652cd2b8552`.
Release helper freeze (`R3-HELPER-FREEZE.json`): `2b0748c285e036140d826dd782f6c7c9f4c4259c3a8b8427927611d84662f976`.
Exact-source checks, WVT and Upgrade comparison passed, as recorded in the hash-bound R3 source-CI input.
The fresh exact-source UI receipts report 54 unit tests and 71 browser cases,
with zero failures. Test counts are taken from these actual receipts.

Nextcloud remains upstream v0.1.6 with output-schema `ha_commit` `03833340f11f78200062a731662e35d05dd9ec83`.
Python runtime source is the pinned 3.13.18 security correction in this source, documented in
[Python base security](../provenance/python-base-security-20261030.md).

### Failed R2 history retained

The earlier source `8d34507c87d6169874c66142aca5982a2cdd1114` produced Odoo image `sha256:033424ac1ff06eb6b433b70f291585329d965d3bff56699923678a897dde90d9`.
Its original gate stopped without success; a later unchanged-policy diagnostic gate failed on fixed
Critical `CVE-2026-115557` in Python 3.13.16. That image and its failed receipts remain historical failures.
The R3 ownership evidence retains that exact failed image under quarantine; this publication does not
reclassify or reuse it as an accepted image. All six accepted images belong to the fresh R3 source above.

All six linux/amd64 images passed P1–P5, current/full-history/layer secret scans, SBOM/CVE/license policy,
packaged runtime with owned mocks, installed-package checks, exact UI bytes and UID10001 DAC.
Prior 0.4.7 image IDs were preserved. Scanner and precise secret-triage policy bytes are unchanged;
their independent security-review scope and exact exceptions remain explicit. Policy pass does not mean zero vulnerabilities.

Only accepted immutable IDs were published. Anonymous manifest/config/source/platform/ordered-layer checks passed.
A separate fresh download verified 83 unique remote layer blobs covering
103 ordered image-layer positions and
323,868,365 compressed bytes; compressed digest/size and uncompressed diffID matched.
This verification used neither Docker nor a local layer cache; CDN cache state is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned. Accepted local images remain.
See [image provenance](../provenance/release-0.4.8-images.json) and
[remote-layer evidence](../provenance/release-0.4.8-remote-layers.json), copied byte-for-byte from actual R3 receipts.

Provenance is unsigned and the Docker daemon is shared. No SLSA, host-isolation or hosted BLD2 admission is claimed.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:62b7cb373d468609bc86fb0578765c7fe73787b460c6594c9e2214cc426d42cd` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:888b20e879718e80d6b32ee72a910f6d80f59e88871f726b8e3d78de8594bd36` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:3fb9457c8c82e52d996eb27c46518b30d23c6cd8596bd656440651329ad5d9a1` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:99c847b82c12fd4f3c76898bf2fa8ba0874dc93cb48a8467b5329146d11360a4` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:e2f4ecac3cb73abca13d659d6677593eb91ebb4a95a16d06264d79c836f2c031` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:6049035263b8cb730445f14d673fc544d952dda054ec3dd427caeaae82c75a04` |

Stable Releases, Store/Local Download, HAOS upgrade/settings/partial restore and real-backend acceptance remain separate evidence. These image gates do not establish a ws97 reinstall, off-cluster backup or full production restore.
