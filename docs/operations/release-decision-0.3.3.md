# 0.3.3 image publication decision — 2026-10-24

Status: six canonical images completed fresh P1–P5 gates, publication without rebuilding, and anonymous immutable manifest/config/rootfs verification. This records completed image publication. Exact-head CI, normal protected merge, stable Releases, Store synchronization and the official HAOS upgrade are separate root-owned stages; publication does not imply their completion.

## Exact source and documentation boundary

Image source is `26888f9a45fef8f35185b358b66ef568e487d87d`, tree `00cca708474cff9b18f69a6ba2c5903a837b077e`. Root freeze receipt SHA256 is `443840f618f4bce1774b63b6066508bcacfc444e5ae50e29e9dd086ec9f78ffc`. This is a new normal 0.3.3 publication, not a 0.3.1 recovery or image overwrite. The plan SHA256 is `4a675f7be17d31b65d6ffadb7abb4a44ff3da9764a369e29fb9996baac34840a`; full-history, archive, context, helper, gate and journal bindings are recorded in the [image receipt](../provenance/release-0.3.3-images.json).

The later documentation head and protected merge are not the image source. The read-only closure verifier checks that their only delta is README, this decision and the image receipt, with unchanged runtime, dependencies, child pins, Dockerfiles, entrypoint and UI. README is excluded by Docker context policy; the operations decision is not a Docker COPY input. The new receipt is under `docs/provenance`, which all six Dockerfiles copy, and was absent from the already published images. A future rebuild would include that receipt, so full shipped provenance/tree equality is not claimed. The post-publication receipt does not require rebuilding its own image.

## Separate version reservation

The independent dependency-update [PR17](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/17)
already reserves 0.3.2 for different source and dependency changes. This bounded
authorization correction therefore uses 0.3.3. Our unpublished 0.3.2 candidate
source `c1ec45d81424459e5e045101ee40e8aeb89d61f2` is retained as historical
preparation evidence, not a release or publication proof. Do not publish its
0.3.2 refs or reuse its local image gates as 0.3.3 acceptance. No PR17 dependency
changes are merged. The new source/version requires its own exact-image gates,
publication, normal PR checks and Store evidence. Published 0.3.1 history remains
unchanged.

## Completed image gates and route limits

P1/P2 bound the clean frozen commit, full reachable history, canonical archive and context bytes/modes. P3 built canonical linux/amd64 images. P4 exercised exact packaged runtimes with owned mocks. P5 retained source/history/all-layer/config/evidence secret scans, SBOM/SPDX, the vulnerability database and the existing vulnerability/license policy. Passing policy is not a zero-vulnerability claim. Scanner pins, policy thresholds and exception rules were unchanged.

Each of the six accepted image IDs was pushed only after exact-tag absence checks, without a rebuild. The completed normal publisher journal binds push intent/completion, anonymous immutable pull, private credential removal, owned tag/digest alias cleanup and lock release. Independent anonymous verification binds tags/manifests/configs/rootfs to those accepted subjects. Image UI bytes match the tested `dist/assets/app.js` SHA256 `f20cdd713606aeaf05ff3a4183ad5c5603e089680665d7514ab025d6c7520871` with fresh 0.3.3 effective-layer and runtime UID 10001 readability proof. The build/browser tests are reused from source `c1ec45d81424459e5e045101ee40e8aeb89d61f2` because the complete UI source manifest is byte-identical; no new 0.3.3 browser or build-test run is claimed. Original build receipt SHA256 `04578ab41f74d7f3c26f08d45d36d504d6044638ddeffb9ebc34844b197bcd50` and browser receipt SHA256 `cf4971d31cf242fabd779761126082c92ea137603038f82f8957fc584a8e64d7` remain unchanged and are included with the new GO-bound reuse attestation in the image record. These reused UI tests do not substitute for any of the six fresh 0.3.3 image gates.

| Product | Immutable published image |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:2aa3c6be06fabe2b9cdb75e054f93a8fba17f06e7ca8308789d01a8ec93db169` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:4e51a90b50f7b97ff7f0ef2935b9dbec5c11bae82814335e41e81fb1ea0c7f64` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:2fbf3ab3c9cba860223bbd10c64d441c12fa23703642908073c625cebc64d10c` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:d64d8502659fb4cc65382abb95d06bb15edbbfd2d5ffb512ec7a99e0a7ae4a6e` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:9883e77a11fe12434d4ac01db2735e0547d6bab9367a8eb9b963e5746da635b1` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:faeb787605f80516cc265e36310b4014805bba0b436743a613c5ee9a0c24c39b` |

Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud advance together. OpenDesign remains Store-disabled and has no published 0.3.3 image or stable Release. The operator-local shared-daemon route is unsigned, not host isolation, hosted BLD2 admission or SLSA. Sole publisher means cooperative ownership of six refs, not an idle daemon or registry compare-and-swap. BLD2 remains blocked; closed hosted/manual workflows and release gates are not bypassed.

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

The correction requires the existing `n8n_update_partial_workflow`
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

## Functional evidence and limits

Integrated local verification passed 339 policy, bounds, filtered full-surface, operation-deny, capability, full-default and provenance checks, with eight external-inventory/real-child cases deliberately excluded. Packaging validation and 28 focused version/release-contract tests passed. These prior source results used existing dependency environments and mocked registry responses; they are not publication receipts. Fresh image acceptance above provides separate canonical packaged-runtime evidence.

Historical 0.3.0 and 0.3.1 decisions/receipts remain unchanged. No official 0.3.1 HAOS upgrade is claimed. The authorized designated Hermes plan is one direct 0.3.0 → 0.3.3 upgrade after normal release/catalog proof, with fresh VM/route/addon identity, protected inventory, the Supervisor free-space guard, exact old/new image identity, complete private cold state archive and verified Supervisor partial backup. Root owns execution. Configuration, active token and restrictive policy must remain byte-identical; final proof covers actual read-only MCP and masked desktop/mobile UI. Backup creation is not a restore rehearsal, and an uncertain phase cannot be replayed automatically.

A successful Hermes upgrade proves its own shared-runtime path, not a real-backend n8n exposure write. The n8n correction's proof remains bounded to the recorded regressions and canonical-image tests unless a separate candidate receipt is produced. No business write, billable inference, every-product backend acceptance, or successful rollback is inferred.

## Remaining normal release stages

Root verifies documentation/runtime closure, obtains required exact-head checks and normally merges the release PR into protected `claude-delivery`. Existing push workflows create six `woow_mcp_<product>-v0.3.3` stable Releases; notification and Store verification must bind actual run heads, resolved tags, merge and image source. Optional Local Download catalog/downloader proof is separate and does not claim installation. This docs update performs no VM action.
