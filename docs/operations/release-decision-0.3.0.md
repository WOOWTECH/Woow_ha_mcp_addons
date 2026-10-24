# 0.3.0 release decision — 2026-10-24

Status: image publication complete. All six exact-image P1–P5 gates and anonymous
immutable manifest/config/layer verification passed on 2026-10-24. Root retains
PR12 merge and designated HAOS upgrade ownership; required PR checks still gate merge.

## Authorization and publication route

The user explicitly authorized merge/release on 2026-10-24 and authorized the
complete private-builder acceptance, supply-chain and publication path. The
existing [private release decision](release-decision-2026-10-05.md) remains the
route: build from a committed source, accept and scan exact image IDs, publish
those same IDs without rebuilding, then anonymously verify immutable manifest,
config and layer identity. Keep raw scanner output private and retain sanitized
receipts. This is unsigned evidence, not a SLSA claim.

The historical private builder VM is no longer present. For this release, root
explicitly directed the existing Batch 3 operator-controlled DinD builder, with
a dedicated release controller and task-owned source/evidence directories. The
source-bundle, context-closure, exact-image container/supply-chain and anonymous
registry-verification gates run there unchanged. This preserves their executable
checks; it does not claim exclusive host isolation, the deleted VM's identity,
hosted BLD2 admission or protected GitHub workflow approval. Only this release
operator owns the six destination references during publication. No manual
workflow admission flag or scanner policy is relaxed.

Six Store-enabled products receive 0.3.0: Odoo, n8n, Hermes, EMQX, LiteLLM and
Nextcloud. OpenDesign remains disabled in the Store registry; its source manifest
shares the version but no OpenDesign image or stable Release is requested.
Existing immutable tags must never be replaced. `RELEASE-GATES.json` stays closed;
this does not enable or bypass the separate manual public-release workflow.

Latest stable baseline: six per-addon 0.2.2 Releases published 2026-10-21.
Runtime acceptance baseline: `3573535a118b5dca629c9192acb6a02b68634cce`.
Release metadata advances the minor version because it adds permission controls
and changes unattended legacy boot timing. The accepted runtime/UI baseline is
retained with the release version updated, apart from the n8n input-budget fix
below. Fresh supply-chain scans required the narrowly scoped dependency and
input-budget fixes; those changes require fresh exact-image and corresponding
functional acceptance. The container gate fixture now asserts pending legacy
review and an explicit stopped-runtime CLI migration instead of expecting the
old automatic boot migration; it does not bypass HA authentication.

## Security dependency delta

The fresh 2026-10-23 Grype database blocked the initial unpublished images. No
exception or severity threshold was changed. The shared Python lock and enabled
Python product locks pin certifi 2026.10.19 instead of 2026.7.22 for
[GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)
(Critical). n8n's existing npm override moves MCP SDK 1.31.0 to 1.32.0 for
[GHSA-22jm-h49p-29qw](https://github.com/advisories/GHSA-22jm-h49p-29qw) and
[GHSA-46jr-4wx8-v453](https://github.com/advisories/GHSA-46jr-4wx8-v453)
(High). A version bump alone does not enable the latter advisory's optional
input-validation limit. This n8n child uses the low-level SDK `Server` over HTTP,
with no experimental `taskStore`; its 10 MB Express parser has no element budget.
The gateway therefore applies a n8n-only pre-dispatch budget after authentication:
4 MiB of actual request bytes, 10,000 recursive object members/array elements in
tool arguments (the root itself is not counted), and a nesting limit of 64.
JSON-looking structured argument strings are inspected under the same element
budget and a cumulative 4 MiB decoding budget, covering the child's nested-output
and stringified-parameter coercion without changing forwarded values. Nonidentity
Content-Encoding is refused (415 / JSON-RPC -32602). Excess budgets return
413 / -32602; malformed JSON returns 400 / -32700. HA still rejects an entire
unsupported batch before dispatch. Other products retain their existing 16 MiB
request limit. Large n8n workflows that exceed these limits must be split or
reduced; the fixture measurements are not a claim about every customer workflow.

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
private receipts remain with the release operator. These are candidate-runtime proofs. The new official images separately passed
the exact-image gates recorded below; an official Store-upgrade acceptance is
not claimed here. This release sidecar did not modify a formal Store add-on. HA active-stream cancellation was not independently live-proven;
existing-client subsequent requests were rejected after revocation. Backend reads
proved non-error MCP results and backend GET paths, not complete cross-product
response semantics. The original n8n MCP response shape was not retained; its
supplemental direct GET is not additional MCP acceptance. LiteLLM retained only
result shapes/counts. In-flight
backend effects cannot be rolled back. No full Store upgrade/downgrade, every-
product full backup recovery, power-loss recovery, or nondefault mount setup is
claimed. The user has authorized the designated HAOS official-channel upgrade
test, which root coordinates. The release sidecar has not received root's VM
handoff and must not mutate the VM; this is a delegation boundary, not a request
for renewed user permission. Root reported 2.380 GiB free on HAOS at 03:03 UTC after an external baseline
change. The canonical Hermes image is 183,775,072 bytes uncompressed (175.26 MiB);
backup, extraction and filesystem overhead are additional. Root must recheck the
Supervisor 2 GiB installation guard and actual free space immediately before the
scoped upgrade; no guard was disabled.

## Release gates

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
does not validate this document's status or receipt digests. The completed six-image receipt is incorporated below and root has independently
verified its published manifest/config identities. Required PR checks still gate
merge. No gate code is weakened in this release.

## Completed image publication

Exact image-source commit: `769ee23ebc52d016587f2e1dad0d65b098ab9a40`.
All six canonical linux/amd64 images were built from its Git archive, with the
full 223-commit source bundle and tracked Docker COPY closure verified first.
Each exact image ID passed packaged-runtime/owned-mock acceptance and the
unchanged P5 policy: source/history/all-layer/config/evidence Gitleaks, Syft
SBOM/SPDX, fresh Grype database and license validation. Scanner pins remain
Gitleaks 8.28.0, Syft 1.54.0 and Grype 0.120.0. Database build time was
2026-10-23T06:30:15Z. No scanner pin, severity threshold or exception was relaxed.
All six SBOMs identify certifi 2026.10.19; n8n identifies SDK 1.32.0. The original
policy still reports lower-severity and explicitly not-fixed/wont-fix matches;
passing does not mean zero vulnerabilities.

At 03:20:34 UTC, all six `ghcr.io/woowtech/amd64-mcp-<product>:0.3.0` tags had
been published from those accepted local image IDs without rebuilding and
verified through anonymous immutable pulls. The [public image receipt](../provenance/release-0.3.0-images.json)
records each manifest digest, config/image ID, layer diffIDs, uncompressed size,
source/bundle identity, scan counts/database and evidence hashes. OpenDesign was
not published. Root independently fetched all six tag/immutable manifests and
config blobs anonymously, checked their hashes and rootfs diffIDs against the
accepted image IDs, and bound the full-pull worker receipts without another
Docker pull. Its receipt hash is included in the public image summary.
Detailed retained SBOM/provenance evidence remains private with the release
operator; raw transient scanner findings are not published.

The original publisher review's four conditions are closed:

1. Before importing project helpers, the pinned driver required exact clean
   source (including untracked files), nonshallow history and both helper hashes.
   Fresh postchecks again found the same clean 223-commit source.
2. Python optimization was disabled and nonempty `PYTHONOPTIMIZE` was refused;
   critical checks use explicit exceptions rather than removable assertions.
3. Both build queues ended before publication. The delegated operator owned the
   six destination refs, acquired an exclusive owned lock and persisted the
   declaration. All-six and immediate per-product unused-tag checks passed.
   This remains cooperative shared-daemon admission, not host exclusivity or an
   atomic registry compare-and-swap claim.
4. The durable exact-ref journal records all six anonymous verifications,
   removal of 12 owned tag/digest refs, preservation of accepted local images,
   deletion of ephemeral credential configuration and release of the lock.
   The final private receipt hashes and declaration/journal hashes are retained
   in the public image summary; no credential is retained there.

The exact image-source commit's complete `checks` CI passed at 03:18:58 UTC
([run](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/40056742468));
focused n8n/mock-surface/provenance tests passed 62 with eight real-child/inventory
tests excluded from that bounded controller run and covered by full CI instead.
The release train check also passed. The initial readiness check preceded image
publication; the final receipt commit triggers required checks again, and root
must verify them before merge.

The final follow-up commit changes only this excluded operations document and
adds the post-publication image receipt. The receipt is intentionally absent
from the already accepted images; it would be included by a rebuild because the
Dockerfiles copy `docs/provenance`. Images continue to claim the exact source
commit above, never the later receipt/merge commit. The closure check proves
runtime, dependencies, Docker policy, entrypoint, UI, notices and pre-existing
provenance unchanged. This avoids an endless receipt/rebuild cycle without
claiming complete final-tree/image equality.

Root retains merge and VM-operation ownership. This completed publication
record does not merge PR12, create a stable GitHub Release or upgrade the VM;
those coordinated steps remain within the user's existing authorization.
