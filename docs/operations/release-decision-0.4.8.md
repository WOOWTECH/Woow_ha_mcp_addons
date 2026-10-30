# 0.4.8 release decision — 2026-10-30

Status: **pending image publication**. Source base is merged PR #41 at `4d81dcc408c9b8cc2bdcd1af2dffcfb74d2a962a`, following the published 0.4.7 release.

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
