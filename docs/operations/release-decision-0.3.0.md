# 0.3.0 release decision — 2026-10-24

Status: release preparation. Image publication and Store merge remain gated by
fresh exact-image receipts; this document is not evidence that those gates passed.

## Authorization and publication route

The user explicitly authorized merge/release on 2026-10-24 and authorized the
complete private-builder acceptance, supply-chain and publication path. The
existing [private release decision](release-decision-2026-10-05.md) remains the
route: build from a committed source, accept and scan exact image IDs, publish
those same IDs without rebuilding, then anonymously verify immutable manifest,
config and layer identity. Keep raw scanner output private and retain sanitized
receipts. This is unsigned evidence, not a SLSA claim.

Six Store-enabled products receive 0.3.0: Odoo, n8n, Hermes, EMQX, LiteLLM and
Nextcloud. OpenDesign remains disabled in the Store registry; its source manifest
shares the version but no OpenDesign image or stable Release is requested.
Existing immutable tags must never be replaced. `RELEASE-GATES.json` stays closed;
this does not enable or bypass the separate manual public-release workflow.

Latest stable baseline: six per-addon 0.2.2 Releases published 2026-10-21.
Runtime acceptance baseline: `3573535a118b5dca629c9192acb6a02b68634cce`.
Release metadata advances the minor version because it adds permission controls
and changes unattended legacy boot timing. Dependencies and runtime/UI logic
remain those of the accepted baseline; only version/provenance/docs change for
release preparation.

## Defaults, upgrade and recovery

Maximum functionality remains the default. Fresh installs enable all tools and
writes. Existing schema 4 loads its saved policy normally. Schema 1/2/3 now waits
before ProductStore/child startup in an HA-admin-authenticated Ingress review:
`all_on` is selected by default, but an administrator must confirm it or choose
`preserve`. Refreshing does not migrate. During review MCP/readiness returns 503;
a durable confirmed migration starts the normal runtime on the same ports.
Unattended legacy upgrades stay in review until an administrator opens the panel.

`preserve` retains restrictive policy and disables newly introduced and
argument-review tools; it does not recreate old argument validation. Existing
credentials and revoked token state survive migration. Offline restrictive
recovery unions tool/operation denies, intersects grants, preserves a later
false global-write flag and current token state. Full-state backup restore is a
separate operation and can bring back an old token. Stop the runtime before CLI
apply/recovery. See [migration](legacy-migration.md) and
[backup/rollback](update-backup-rollback.md).

Schema remains 4 but older binaries do not enforce the new operation denies;
0.2.2 is not an equivalent policy rollback. Ports, architectures, image names,
manifest options and privileges are unchanged. At preparation time AGENTS.md's
pipeline #89 upgrade-notes schema is not defined in the discovered Store release
contract; migration changes are declared here, in CHANGELOG and the version PR
as required by its interim rule.

## Functional evidence and limits

The runtime baseline passed independent SPEC/quality review, full Python/UI CI
and scoped HAOS candidate acceptance. Authenticated real Ingress review covered
n8n schema 1 with preserve (19 gate checks), LiteLLM schema 2 with default all_on
(18), and Hermes schema 3 with default all_on (18). Refresh without migration,
rejected confirmation, schema 4 restart bypass, actual backend reads, operation
denials and two-client token lifecycle were exercised without backend writes or
billable inference. Runtime receipts: n8n 38, LiteLLM 39, Hermes 48 checks. Offline
synthetic CLI fixtures checked restrictive recovery and token preservation (231
fixture assertions plus two wrapper checks).

LiteLLM's receipt combines an initial full 40-tool baseline with resumed
39-tool restrictive acceptance; policy save restarts this product's child, so an
old session returned 404 and was reinitialized. The final full count was read
again. EMQX/Nextcloud share the existing policy-restart mechanism. Token mutations
do not restart the child. n8n/LiteLLM final all_on restoration was issued but its
PUT result and full saved policy were not asserted before their removal; their
final backend reads passed. Retained Hermes full saved/effective policy was
separately verified (five checks, 11 effective tools / 21 write grants).

Receipt filenames, SHA-256 hashes and bounded check counts are retained in
[the sanitized runtime summary](../provenance/release-0.3.0-runtime.json); raw
private receipts remain with the release operator. These are candidate-runtime proofs, not a claim that official 0.3.0 images have
already passed image or Store-upgrade acceptance. No formal Store add-on was
modified. HA active-stream cancellation was not independently live-proven;
existing-client subsequent requests were rejected after revocation. Backend reads
proved non-error MCP results and backend GET paths, not complete cross-product
response semantics. The original n8n MCP response shape was not retained; its
supplemental direct GET is not additional MCP acceptance. LiteLLM retained only
result shapes/counts. In-flight
backend effects cannot be rolled back. No full Store upgrade/downgrade, every-
product full backup recovery, power-loss recovery, or nondefault mount setup is
claimed. HAOS disk remains below its 2 GiB installation guard at the prior final
check; no VM upgrade is authorized by this release-preparation step.

## Required fresh release gates

1. Clean exact committed source and canonical Dockerfiles for linux/amd64; labels
   identify source revision and 0.3.0. Product dependency closure stays pinned.
2. Container acceptance of each exact image ID, followed by pinned Gitleaks
   source/full-history/all-layer/config/evidence scans, Syft SBOM/SPDX, current
   Grype database and unchanged CVE/license policy. No new blanket exceptions.
3. Registry preflight proves the 0.3.0 tag absent. Publish the accepted ID, then
   anonymous immutable pull verifies manifest/config/diffIDs and digest receipts.
4. Focused local release validation and required PR checks (`checks`, `readiness`,
   Release train) pass. Readiness must see all six public images and this decision.
5. Root merges PR12 through the protected `claude-delivery` PR flow. Its existing
   push workflow creates six `<slug>-v0.3.0` stable Releases and Store sync follows.
   Do not manually create tags/releases or enable OpenDesign.

The current automated decision-file check only matches the version string; it
does not validate this document's status or receipt digests. Root must keep PR12
unmerged until the completed six-image receipt is incorporated and independently
checked, even if readiness becomes green as images appear. No gate code is
weakened in this release.

Fresh build, scan, publish and anonymous-pull receipts will identify the exact
source commit and six immutable digests. Until recorded as passing, publication
and merge are not ready. Root retains merge ownership; VM changes require a
separate handoff.
