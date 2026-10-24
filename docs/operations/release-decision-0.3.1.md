# 0.3.1 release preparation — 2026-10-24

Status: candidate metadata, documentation and a bounded UI rendering fix. No 0.3.1 image build,
container/supply-chain acceptance, registry publication or stable Release is
claimed. All six exact-image gates and publication receipts remain pending.
The presence of this document is not evidence that those gates passed.

## Source, ownership and scope

The user has authorized the remaining functionality and subsequent merge/release.
Root coordinates release actions. This preparation worktree owns metadata,
documentation and the explicitly delegated UI fix/tests/asset build; it does not
commit, push, build product images, publish or modify HAOS.
That delegation boundary is not a request for renewed user authorization.

Fresh verified `claude-delivery` base:
`290f8c19e0de064de48619425c222adbf1675f79`, the normal PR15 merge of tested source
`e94c5fa79d42ab37dcb065cdf843e000e13fb432`. Latest stable is 0.3.0, with six
per-addon Releases published on 2026-10-24. This patch promotes the merged
runtime-parity corrections to version 0.3.1. The release-preparation delta changes
version metadata/documentation and fixes literal `null` rendering in the
configuration card, with a browser regression and rebuilt UI assets. Python
runtime behavior and all dependency/child pins remain unchanged from the merge.
The future image-source commit must be frozen and recorded before any build.

Enabled products are Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud. All six need
new canonical linux/amd64 images because they share the changed core/UI.
OpenDesign remains Store-disabled: its source metadata follows the common version
contract, but no image or stable Release is requested. Archived Odoo Manage is
unchanged. No immutable existing tag may be overwritten.

## Behavior and upgrade notes

Configuration status distinguishes a durable save from successful application by
the current child generation. Backend health stays separate. Optional exact
`If-Match` checks reject stale saves with HTTP 409 before mutation; the new UI
retains drafts until explicit reload. Clients omitting the header remain
compatible without conflict protection. Revisions are process-local, so a
management restart requires old editors to reload. A save that commits before
child replacement fails returns HTTP 503 with `saved:true` and safe failure
metadata; the UI reports saved but not applied and does not retry automatically.

Persisted token revoke/rotate cancels active request I/O and actual ASGI sends,
including blocked sends and open GET/POST streams. Both Bearer and secret-path
routes are covered. No child restart is introduced; bytes already delivered and
backend effects already dispatched cannot be rolled back. HA does not expose
legacy `/sse` or `/messages` endpoints. See [the API and lifecycle contract](../runtime-configuration.md).

Maximum functionality remains the fresh-install default. Existing schema 4 keeps
its saved policy. Schema 1/2/3 retains 0.3.0's authenticated HA Ingress prestart
review before ProductStore or the MCP child starts: `all_on` is preselected, but
an administrator must confirm it or explicitly choose `preserve`. Refresh does
not migrate. Until confirmation, MCP/readiness returns 503. Back up first and
open the panel after upgrading legacy data. Tokens, including revoked state, are
preserved. [Migration](legacy-migration.md) and [backup/rollback](update-backup-rollback.md)
constraints still apply. There is no new schema migration, dependency/child pin,
option, port, architecture, image name or privilege change in 0.3.1.

## Existing evidence and its limits

PR15's normal exact-head [CI run 40069357356](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/40069357356)
passed on `e94c5fa`: 2456 core tests, zero skips, including the unchanged UID0 and
paused-iterator cleanup tests; UI unit 26, browser 39 and upgrade-browser 10 passed.
Packaging ran 157 cases with five existing skips. Readiness and release-train
checks passed. These results precede this version/UI preparation and do not
replace its new required CI or image gates.

Root's retained `evidence/batch4/ha-candidate-acceptance.json` binds that exact
source and reports 26/26 live checks. SHA-256:
`984168693ec33827ef01ba315b5916262bd26b4b4c21068279595a115fc066b8`.
It used an isolated local Supervisor Hermes candidate layering frozen runtime/UI
onto a published dependency image, not a new canonical published 0.3.1 image.
Authenticated owner Ingress, saved/applied generation status, stale-editor
rejection without durable/process change, a real Hermes status read, local write
denial, closure of an actual idle stream alive at the revoke barrier, old-token
rejection, reissue/read and no token-induced child restart passed. Final policy
was explicitly read-only. No business write or billable inference was performed.

Root subsequently found literal `null` in the merged candidate status-card
screenshot. The 26 live checks and earlier browser suite did not assert that
visual defect; their original evidence is preserved. This release candidate fixes
only the optional-row DOM construction and adds initial/refresh/mobile and
missing-configuration browser assertions. Final image UI acceptance must verify
that `#configuration-state` contains no literal `null`; old candidate screenshots
are not proof of the corrected UI.

Local preparation checks passed: strict packaging validation; 157 packaging
tests with five existing skips (registry lines were mocks; external network was
blocked); 26 UI unit tests; 41 browser tests; and the final five configuration
browser tests after strengthening the refresh-completion assertion. The original
bundle reproduced two literal-null failures before the fix. Build closure verified
434 unchanged fonts, 870 local references and six notices/licenses; among 445
built UI files, only `assets/app.js` changed. Pure file checks verified the 19
version-contract edits, 29 provenance source hashes and 94 guarded dependency
hashes. Two core ledger/inventory pytest cases could not start because the shared
local test lock remained busy for 120 seconds; no lock was bypassed and no test
success is claimed for that attempt. Normal candidate CI remains required.

The live stream proof is bounded to that Hermes idle-stream scenario; the broader
two-client GET/POST, blocked-header/send and coalesced-frame matrix is local socket
regression coverage. This is not every-product live acceptance, complete backend
response-semantic coverage, a canonical image proof, an official Store upgrade,
or full backup/rollback acceptance for 0.3.1. Earlier 0.3.0 release evidence remains
historical and is not relabeled as 0.3.1 acceptance.

## Required gates before version PR merge

1. Freeze a clean committed source and full history. Confirm canonical Docker
   context/dependency closure, exact source identity and an available supported
   private builder/publisher route. The existing operator-local controller route
   has been rediscovered with matching daemon/controller/tool identities; its
   new per-source binding and image gates remain pending. The separate BLD2
   workflow admission remains blocked. No daemon is admitted by this document. Preserve the executable P1–P5 checks and original
   scanner pins, CVE/license policy and secret-handling rules.
2. Build and accept each of the six exact image IDs. Run container/owned-mock
   acceptance, source/full-history/all-layer/config/evidence secret scans,
   SBOM/SPDX, a fresh vulnerability database and license validation. Source tests
   and derivative HA candidates cannot substitute for these image gates.
3. Prove each destination version tag unused, publish the accepted ID without
   rebuilding, and independently verify anonymous immutable manifest, config and
   rootfs diffIDs. Retain sanitized digest-linked receipts only after real success;
   then replace this pending status with factual completed evidence. Do not create
   placeholder image receipts or claim zero vulnerabilities from a passing policy.
4. Run the release metadata validations and all normal required PR checks. The
   current readiness decision-file check only recognizes the version string;
   root must inspect completed six-image evidence before merging, even if that
   automated check is green.
5. Root merges the ready version PR through protected `claude-delivery`. The
   existing push workflow creates six `<slug>-v0.3.1` stable Releases and Store
   sync follows. No manual tag/release or gate bypass is part of this preparation.

The historical [private publication route](release-decision-2026-10-05.md) and
[release rules](release.md) remain authoritative. `RELEASE-GATES.json` stays
closed; the separate manual workflow is not enabled. Root owns any later VM
handoff and must freshly verify identity, backup and the Supervisor disk guard.
This source preparation performs no VM cleanup or upgrade.
