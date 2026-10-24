# 0.3.2 release preparation — 2026-10-24

## Status and source boundary

**Pending: exact-source freeze/CI, six-image
P1–P5 gates, publication and independent anonymous verification.** This document
is a candidate record, not completed builder acceptance or permission to skip a
release gate. No 0.3.2 image digest or successful publication is recorded yet.

Preparation starts from merged PR16,
`da6edd7fcfae83360931eb4dab1848eaaf9a4645`. The reviewed guard is integrated with
the release metadata; the exact 0.3.2 image-source commit will be frozen after
the integrated checks and root review.
The final publication record must distinguish that source from the later
documentation head and protected merge. Historical [0.3.1 image evidence](../provenance/release-0.3.1-images.json)
and its [publication decision](release-decision-0.3.1.md) remain unchanged; they
cannot satisfy new 0.3.2 gates. No 0.3.1 tag or image is overwritten.

## Bounded correction and compatibility

The pinned n8n child can change a workflow's MCP exposure setting when a history
read requests effective `exposeToMcp=true`. An offline reproduction against the
0.3.1 image source recorded three failing safety regressions with seven passing
controls: native-history `list`, `get` and `diff` reached a mocked workflow update
despite zero write grants. It exercised real pinned handler and policy code with
synthetic state and denied network access; it was not a live backend exploit or
an authorized business write. The private regression receipts remain preserved.

All 28 n8n tools now normalize the pinned child's one-level eligible `output`
JSON object before operation denies/grants and forwarding. This also closes
outer-read/inner-write selector overrides for the six mixed tools: workflow
versions, executions, evaluations, credentials, folders and datatables. A second
eligible wrapper is refused as ambiguous. Repeated authorization sees the same
canonical arguments, and existing encoded byte/element/depth budgets run first.

The candidate correction requires the existing `n8n_update_partial_workflow`
tool to be enabled with its effective write permission before exposure can be
forwarded, in addition to the invoking tool/mode's own authorization. The same
dependency applies to `n8n_test_workflow` exposure. Effective boolean and
output-wrapper representations accepted by the child must receive the same
decision; denied requests must not reach the child. Read requests with exposure
omitted/false remain available, and full-policy users retain exposure behavior.

Additive `conditional_writes` capability metadata names `exposeToMcp`, the
existing updater dependency and its effective policy state on versions/test.
The existing UI grant controls remain sufficient; no new UI control or persisted
permission is introduced.

There is no new grant: n8n remains 28 tools and 33 explicit write grants. The
release keeps schema 4, current tokens, saved restrictions, dependency and child
pins, UI source, request limits, ports, image names and privileges. Fresh installs
retain maximum functionality. Legacy schema 1/2/3 still waits for an authenticated
HA administrator to confirm preselected `all_on` or explicitly choose `preserve`
before migration/runtime startup. Current-schema startup is unchanged.

Existing state needs no migration for this correction, but a binary downgrade
restores the conditional-write defect. State compatibility does not establish
equivalent security behavior. Preserve a backup and review current token and
policy state before any separately coordinated recovery.

## Products and unchanged release gates

Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud advance together under the shared
core contract. Their intended immutable version tags are
`ghcr.io/woowtech/amd64-mcp-<product>:0.3.2` (`linux/amd64`). OpenDesign's retained
source metadata advances for packaging consistency, but Store remains disabled;
it has no 0.3.2 image build, stable Release or acceptance claim.

The existing operator-local builder/publisher route may be reused only with
fresh exact source/tree/full-history/context/helper bindings and current builder
identity. Canonical Dockerfiles and dependency/UI caches may be reused; context
permissions and the bounded runtime-stage cache correction remain enforced.
Every published image must receive fresh P1–P5 acceptance, pinned-tool secret,
SBOM/license/vulnerability checks under the existing policy, actual UI-byte proof
and anonymous immutable-manifest/config/rootfs verification. A version-string
readiness check alone does not establish completed acceptance.

Only the tested image IDs may be pushed, after exact-tag absence checks. Complete
phase journals, owned-reference cleanup, credential cleanup and independent
anonymous verification are required before publication PASS. An uncertain phase
requires diagnosis and a separately bound continuation; no blind retry, overwrite
or invented recovery receipt. The existing route is cooperative on a shared
daemon, not host isolation, hosted BLD2 admission, signed provenance or SLSA.
Closed hosted-builder/manual-release gates and scan thresholds stay unchanged.

After actual six-image completion, the release owner records the immutable
identities and evidence hashes in a new `release-0.3.2-images.json`, closes this
pending decision and verifies documentation/runtime closure. Required exact-head
checks then permit the normal protected PR merge. The ordinary push workflow
creates six `woow_mcp_<product>-v0.3.2` stable Releases; notification and Store
catalog verification must bind actual run heads, resolved tags, merge and image
source. Optional Local Download evidence remains a separate proof.

## Acceptance still required

Integrated local verification passed 339 policy, request-bound, filtered
full-surface, operation-deny, capability, full-default and provenance checks
(eight external-inventory/real-child cases deliberately excluded). Packaging
validation and 28 focused version/release-contract tests also passed. Dependency
source hashes were checked through temporary links to existing environments;
no dependency installation or change was made. Mocked registry responses in
packaging tests are fixtures, not publication proof. These scoped results do not
replace final exact-head CI, canonical-image or live acceptance.

| Gate | Current state |
|---|---|
| Guard integration/review and scoped integrated regressions | PASS within the local scope above |
| Exact integrated source freeze and CI | Pending |
| Local version/packaging checks | PASS; normal exact-head CI remains pending |
| Six canonical image P1–P5 gates and tested UI bytes | Pending |
| Publication, anonymous immutable verification and cleanup | Pending |
| Completed image record, normal merge/stable Releases/Store catalog | Pending |
| Official Hermes 0.3.0 → 0.3.2 upgrade | Pending separate root-owned execution |

The designated official Hermes may remain on 0.3.0 while normal 0.3.1
Release/Store delivery completes. After 0.3.2 publication/catalog proof, the
authorized plan is one direct 0.3.0 → 0.3.2 upgrade with fresh VM/addon/route
identity, protected inventory, exact old/new image proof, private cold state
archive and verified Supervisor partial backup. Keep the Supervisor disk guard.
Verify preserved configuration/token/policy, runtime/read-only MCP and masked
desktop/mobile UI evidence afterward. Existing authorization covers this work;
root owns its execution, and this metadata step performs no VM action.

No official 0.3.1 HAOS upgrade is claimed. A future successful Hermes upgrade
would validate its shared-runtime upgrade, not a real-backend n8n exposure write.
The n8n correction's evidence remains scoped to its actual regressions and image
acceptance unless a separate bounded n8n candidate proof is recorded. No business
write, billable inference, complete every-product backend acceptance or successful
rollback is inferred from this release preparation.
