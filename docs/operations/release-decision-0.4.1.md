# 0.4.1 release decision — 2026-10-25

Status: **candidate, images pending**. This branch follows merged UI PR #20
(`e095b00928e2248f16aef9a5827aeff0dee2a6a0`) on `claude-delivery`.
Do not publish from a moving parent.
The six `0.4.1` tags must be absent before the private builder starts. No
publication, stable Release, Store sync or ws97 upgrade is claimed here.

## Scope and compatibility

The six Store-enabled products (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud)
carry one shared HA management UI. The new n8n Tools view displays existing
`conditional_writes` capability metadata for `n8n_workflow_versions` and
`n8n_test_workflow`: `exposeToMcp: true` can write even if a selected operation
reads, and HA requires the already existing `n8n_update_partial_workflow`
permission. It labels **saved** dependency policy as allowed, denied or unknown;
unsaved draft choices and child availability do not impersonate saved policy.
No grant is added or automatically enabled.

The WOOW PaaS implementation represents this consent as a separate `expose`
operation (`exposeToMcp` flag); HA's SDK child calls the updater tool. The two
interfaces should describe their actual enforcement, with the same user-visible
warning and completion criteria. The HA 0.4.0 backend already returns both
conditional rules (28 tools observed in ws97), but its 0.4.0 UI does not render
them; this release adds the presentation.

There is no intended change to tool names, gateway authorization, full-function
defaults, schema 4 state, options, ports, architecture, image names, dependency
locks or child runtime. OpenDesign stays disabled in the Store and gets only
matching source manifest metadata. The 0.4.0 Odoo structured result migration
remains in effect; 0.4.1 adds no breaking data change, so no new entry in
`upgrade-notes.yaml` is needed. Rollback to 0.4.0 requires no state conversion,
but the conditional-write explanation disappears from the older UI.

## Evidence and release gates

1. PR #20 at final head `50464028c717d45eca15ef092292ca04f8e72921`
   passed local UI build, 27 JavaScript unit tests, 49 Playwright browser tests
   (including eight conditional-write cases at 320/360/1440 px), 144 n8n
   authorization tests and `packaging/validate.py`. Its required CI then passed
   2,646 unit/integration cases, 49 browser cases, readiness and Release train;
   the merge commit is `e095b00928e2248f16aef9a5827aeff0dee2a6a0`.
   The live ws97 0.4.0 n8n
   management API returned exactly two `exposeToMcp` conditional rules, each
   naming the updater. These are source/UI and metadata checks, not a 0.4.1
   image or live UI acceptance.
2. Freeze this rebased branch's exact source SHA and rerun the release candidate
   checks. Six enabled manifests, the
   runtime VERSION, Docker build arguments, CI tags and `packaging/inputs.json`
   must all say `0.4.1`; keep the retired Odoo Manage version untouched.
3. On the same private builder flow used for 0.3.1/0.3.3/0.3.4/0.4.0, build
   six `linux/amd64` images from the frozen source. Run exact-image P1–P5,
   source/history/all-layer secret scans, SBOM, current vulnerability and
   license policy, and the source/UI asset digest checks. Do not reuse or
   retag 0.4.0 images as 0.4.1.
4. Publish each accepted image ID only after its `0.4.1` tag absence and
   complete gate evidence are confirmed. Anonymously pull by immutable digest
   and compare manifest, config, layers and source label. Commit the six-image
   provenance receipt to this PR branch. `readiness` must become green before
   the protected merge; stable Releases and Store sync are separate checks.
5. On ws97, take a scoped current backup and upgrade the test n8n add-on from
   0.4.0 to 0.4.1. Confirm the published image digest, existing state/token/
   policy retention, both conditional messages in the real Ingress UI, saved
   grant versus draft behavior and 320/360/1440 px. Confirm the other five MCP
   add-ons and unrelated add-ons did not change. The configured Hermes and
   LiteLLM add-ons require their own client-safe upgrade window; a source-only
   check does not count as their live UI acceptance.

Failure at any gate leaves the release pending. Keep the prior immutable
0.4.0 images and published receipts intact; do not merge or update ws97 from
an unaccepted image.
