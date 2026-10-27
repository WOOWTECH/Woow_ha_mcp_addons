# 0.4.2 release decision — 2026-10-27

Status: **six exact-source images published and independently verified; readiness, protected merge, Store sync and ws97 acceptance pending**.
Source branch: `release/ha-core-allowlist-0.4.2`, based on merged PR #24 at
`72c30fe2b59f6120f886b3d4a7af8383fc2aab13`.
The exact image source is `1f1924f15fe85c34bc3b22c8003d2328dc99e220`.
The later documentation commit is not an image source. The six immutable
digests and verification results are in the
[publication receipt](../provenance/release-0.4.2-images.json).

## Scope

The shared HA management panel accepts Core 2026.10.2, 2026.10.3 and 2026.10.4,
following the reviewed file-by-file contract in `docs/ha-role-core-contract.md`.
For an unreviewed Core version, the panel gives `core_version_unreviewed` with
that version; the machine token remains withheld. Other denials keep their
fixed response. The MCP endpoint does not use this management check.

Six Store-enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) receive
new versioned amd64 images. OpenDesign remains disabled and gets matching
manifest metadata only. No tool, grant, state schema, option, port, dependency
or gateway behavior changes. Existing schema 4 data needs no migration.

## Release and deployment gates

1. Validate all version bindings, Core role tests, UI build and browser tests,
   and the complete required CI at the frozen source commit.
2. Build six new images from that commit on the private builder. Run exact-image
   P1–P5, source/history/layer secret checks, SBOM, vulnerability and license
   policies, and confirm final UI asset and UID 10001. Preserve 0.4.1 images.
3. Publish only accepted image IDs to six absent 0.4.2 tags. Independently pull
   anonymous immutable digests and compare manifest, config, ordered layers,
   platform and source label. Commit the provenance receipt to the PR.
4. Require green readiness and Release train checks before protected merge.
   Verify six stable Releases and WOOW HA App Store synchronization afterwards.
5. On ws97, retain a scoped backup for each of the six add-ons, upgrade one at
   a time, and verify the running digest, settings and state hashes, MCP reads,
   management panel behavior and unrelated add-ons. The separate PVC expansion
   and off-cluster backup issues remain tracked independently.

## Exact-image publication — 2026-10-27

The six `0.4.2` tags were absent before publication. The private builder
accepted six fresh `linux/amd64` images from the frozen source. Each passed
exact-image P1–P5, source/history/all-layer secret scans, SBOM, vulnerability
and license policy, final UI asset and UID 10001 checks. The six prior `0.4.1`
image IDs were preserved. Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud were
pushed from their accepted IDs and anonymously pulled by immutable digest.
An independent verifier compared each manifest, config, ordered layers,
platform and source label with the publication receipt. The unchanged,
exact-file Odoo secret triage review is carried forward. The receipt is
unsigned provenance and does not claim builder host isolation or SLSA.

This PR still requires green readiness and a protected merge. Stable Releases,
Store synchronization and the six-product ws97 acceptance must be checked
against the merged version. Keep the prior immutable `0.4.1` images and
publication receipts intact.
