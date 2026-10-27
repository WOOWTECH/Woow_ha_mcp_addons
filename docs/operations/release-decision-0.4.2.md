# 0.4.2 release decision — 2026-10-27

Status: **pending exact-source six-image publication, readiness, protected merge, Store sync and ws97 acceptance**.
Source branch: `release/ha-core-allowlist-0.4.2`, based on merged PR #24 at
`72c30fe2b59f6120f886b3d4a7af8383fc2aab13`.
The exact source commit and immutable image digests must be recorded in
`docs/provenance/release-0.4.2-images.json` before merge.

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
