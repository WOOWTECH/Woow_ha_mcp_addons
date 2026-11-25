## 2026-11-25 maintenance release — Odoo 0.5.2, EMQX, LiteLLM and Nextcloud 0.5.1, n8n and Hermes 0.4.15, Headscale 0.4.20

- Main reason: the admin panel of every store product accepts Home Assistant Core 2026.11.3 (its 25 Core contract and adjacent files are byte-identical to 2026.11.2, and Supervisor 2026.11.0 ships the reviewed WebSocket proxy unchanged) and, from now on, any later patch release of a Core month a release has reviewed (2026.7 to 2026.11; owner decision 2026-11-25). The previous releases (Odoo 0.5.1, EMQX, LiteLLM and Nextcloud 0.5.0, n8n and Hermes 0.4.14, Headscale 0.4.19) accept Core only up to 2026.11.2 and refuse every admin panel request on Core 2026.11.3, the version Home Assistant's stable channel offered on 2026-11-25; MCP endpoints do not use this check. The rule: the Core version must be exactly `year.month.patch` in ASCII digits without zero padding, its year and month must already have a reviewed release, and its patch must be higher than every reviewed patch of that month (2026.11.4 and later; not 2026.7.0 or 2026.7.1). A new month (2026.12.0), pre-releases and any other form of the string stay refused until a release reviews them; the machine token is still sent only after the version check and the user's role is still read afresh on every request. A version accepted without a review of its own gets one add-on log line. What it would cost if the rule were wrong, how it would show and how to undo it: `docs/ha-role-core-contract.md`.
- Includes the merged changes that reach these images (listed in `docs/multi-profile/unreleased-changes.md` until this release):
  - Odoo, EMQX, LiteLLM and Nextcloud (multiple profiles on): the panel reads a weak ETag, which is what a compressing proxy such as Cloudflare makes of the add-on's strong ETag, as the same revision; behind Cloudflare the "browser origin check" card could not be saved before. The profile list is read the same way and was fixed with it; measured behind Cloudflare it was not affected (Home Assistant compresses that answer with gzip first and its ETag stays strong).
  - EMQX: the `emqx_list_topics` description no longer says that a topic missing from the list has no subscriber (PaaS #160), and the documentation says that an EMQX broker before 5.9 (open source edition) does not enforce the `viewer` role of an API key.
  - n8n, Hermes and Headscale, and OpenDesign's source: the boot-time restore guard (#108) and the panel's restore notice (#112) after a backup restore; the other multiple-profile groundwork these images carry (#116, and the work of Odoo, EMQX, LiteLLM and Nextcloud merged in #136 and #137) stays switched off.
  - Nextcloud: the documentation states the confirmed brute-force behavior (UC-12).
- Node.js base image 26.12.1 → 26.13.1 in every image build and in CI (`node:26.13.1-bookworm-slim`, multi-arch index digest; same Node ABI 147, so the pinned better-sqlite3 prebuilt file is unchanged). The Node 26.12.1 binary of the 0.4.14 n8n image matched seven High vulnerabilities that 26.13.1 fixes (CVE-2026-123863, CVE-2026-123864, CVE-2026-123865, CVE-2026-123866, CVE-2026-123872, CVE-2026-123874 and CVE-2026-126051), and the release's supply-chain scan blocks an image that still has them. n8n is the only product that puts the Node binary into its final image; for Odoo, EMQX, LiteLLM, Nextcloud, Hermes and Headscale the Node image only builds the admin panel (the built panel files are byte for byte the same as a build with 26.12.1, checked locally), and OpenDesign's source carries the same pin.
- Corrections to the entries below, which still said "release candidate, images pending": the Odoo 0.5.1 and the LiteLLM, Nextcloud and EMQX 0.5.0 images are published and verified; and the Nextcloud brute-force protection, presumed in 0.5.0 to count per source address, is confirmed to (a wrong password on one profile slows down the new logins of the other profiles; logged-in connections are not affected).
- Version lines: n8n and Hermes advance to 0.4.15 with the shared default version (so does OpenDesign's source version; it stays disabled in the Store); Odoo advances to 0.5.2, EMQX, LiteLLM and Nextcloud to 0.5.1 and Headscale to 0.4.20, each on its own line. The workflows carry the six-way version expression `validate.py` generates.
- The images are built and accepted by the GitHub-hosted release route (PR #121); the published digests and the HAOS acceptance results are in the release records `docs/operations/release-decision-{odoo-0.5.2,emqx-0.5.1,litellm-0.5.1,nextcloud-0.5.1,n8n-0.4.15,hermes-0.4.15,headscale-0.4.20}.md`.

## LiteLLM, Nextcloud and EMQX 0.5.0 — multiple profiles (train A; images published and verified)

- Main reason: multiple profiles are switched on for LiteLLM, Nextcloud and EMQX (`MULTI_PROFILE_PRODUCTS` is `{'odoo', 'emqx', 'litellm', 'nextcloud'}`; Odoo went first with its own 0.5.1). Beside the default profile, an administrator can add up to three profiles in the admin panel, each with its own backend connection, MCP token and both of its URLs, tool policy and MCP child; only the token decides the profile. An installation that never adds a profile keeps its token, both URLs, `state.json` byte for byte, its policy and its child; what it still sees change is listed in each add-on's `CHANGELOG.md`, in `upgrade-notes.yaml` and in contract section 1.4 (`docs/multi-profile/contract.md`).
- Per product: LiteLLM keeps its MCP token when the key or URL changes, allows 50 backend connections per child with a health check of its own, normalizes an origin-root `/v1` URL suffix and now asks the `create` permission for three active tools (read-only mode exposes 15 instead of 18 tools). Nextcloud binds the MCP token to the account (a new URL or username issues a new token), normalizes pasted page URLs and credentials, and no longer restarts the child when a policy save only tightens or changes nothing. EMQX adds a per-profile child policy check (a third layer behind the gateway and the child's environment gate) and the three PaaS #153 fixes (`match_topic` text, Prometheus text, a fixed error code for identifiers a URL cannot carry).
- Includes the merged post-0.4.14 changes that reach these images (listed in `docs/multi-profile/unreleased-changes.md` until this release): the boot-time restore guard (#108), the panel's restore notice and review (#112) and the secret URL's Origin policy (#116), written as part of the 0.5.0 list of each add-on.
- Hermes, Headscale and n8n keep their switches off and their versions (0.4.14, 0.4.19 and 0.4.14); OpenDesign and Odoo Manage are never switched on. The workflows carry the six-way version expression `validate.py` generates (`odoo`, `emqx`, `litellm`, `nextcloud` at 0.5.0, `headscale` at 0.4.19, the rest 0.4.14); the shared default version stays 0.4.14.
- The images are published and verified: built, accepted and pushed to GHCR on 2026-11-24 by the GitHub-hosted release route (PR #121), then accepted on the HAOS showroom device against real backends on 2026-11-24; the manifests, image IDs and results are in the release records `docs/operations/release-decision-{litellm,nextcloud,emqx}-0.5.0.md`.

## Odoo 0.5.1 — multiple profiles (image published and verified)

- Release history: 0.5.0 was built and pushed to GHCR but never listed in the Store (the Store had 0.4.14), so 0.5.1 is the first listed multi-profile version and updates directly from 0.4.14. It fixes F1 found in the 0.5.0 acceptance: an event stream (GET) no longer holds a 64 MiB reply reservation, so a client with its own resident stream can still call tools; the stream limit is the ordinary 24 for the default profile and 8 per additional profile again, and each stream's memory is bounded on its own (1 MiB unread, 128 KiB per child event), counted in the memory plan (64 MiB). Details in `addons/odoo/CHANGELOG.md` and contract sections 2.4 and 5.
- Main reason: multiple profiles are switched on for Odoo, the first product (multi-profile plan R1; `MULTI_PROFILE_PRODUCTS` is `{'odoo'}`). Beside the default profile, an administrator can add up to five profiles in the admin panel, each with its own Odoo connection, MCP token and both of its URLs, tool policy and MCP child; only the token decides the profile. An installation that never adds a profile keeps its token, both URLs, `state.json` byte for byte, its policy and its child; what it still sees change (the admin API's `X-MCP-Profile` header, two byte-level changes on port 8099, JSON-RPC busy answers on port 8081, the PaaS watchdog and health tolerance, token rotation when the Odoo URL, database or username changes, loopback backend URLs refused, the secret URL's report-only Origin list, two new files and the restore review) is listed in `addons/odoo/CHANGELOG.md`, `upgrade-notes.yaml` and contract section 1.4 (`docs/multi-profile/contract.md`).
- Includes the merged post-0.4.14 changes that reach the Odoo image (listed in `docs/multi-profile/unreleased-changes.md` until this release): the boot-time restore guard (#108; it reads and removes the restore marker 0.4.14 leaves), the panel's restore notice and review (#112) and the secret URL's Origin policy (#116). The other products carry them from their next release: the restore guard's warning and the panel's restore notice visibly (A8, A9 in that list), the rest switched off.
- The Store upgrade comparison hooks that HM-16 drafted in `packaging/hooks/` move to `addons/odoo/upgrade-check/` (`seed`, `verify`; read-only and the same for every version).
- Advance only Odoo's own version line, from 0.4.14 to 0.5.1 (DQ-32; 0.5.0 was never listed): `VERSION_OVERRIDES` and `PRODUCT_VERSIONS` add Odoo beside Headscale 0.4.19, and the workflows carry the three-way version expression `validate.py` generates; the shared default version stays 0.4.14.
- The image is published and verified: built, accepted and pushed to GHCR on 2026-11-23 (UTC) by the GitHub-hosted release route (PR #121), then accepted on the HAOS showroom device on 2026-11-24 and listed in the Store with PR #137; the manifest, image ID and result are in the release record `docs/operations/release-decision-odoo-0.5.1.md`.

## Headscale 0.4.19 — maintenance release (image published and verified)

- Main reason: Headscale's admin panel accepts Home Assistant Core 2026.11.2 (PR #120: its 25 Core contract and adjacent files are byte-identical to 2026.11.1, and Supervisor 2026.11.0 ships the reviewed WebSocket proxy unchanged). The 0.4.18 image accepts Core only up to 2026.11.1 and refuses every admin panel request on Core 2026.11.2; MCP endpoints do not use this check. Later patches (such as 2026.11.3) and pre-releases stay refused until reviewed.
- Includes the merged post-0.4.18 shared changes that reach the Headscale image (listed in `docs/multi-profile/unreleased-changes.md` until this release): log redaction applies the PaaS server's rules first (#98); the child on port 3000 serves only the gateway's child bearer (#94); restore detection leaves an owner-only `.restore-detected` marker after a restore (#97); credentials in a child's `initialize` error are redacted (#103); gateway request limits aligned with the PaaS server (#105); a rare 30 s wait when stopping is fixed (#106); and the switched-off groundwork for multiple profiles (#91, #93, #95, #99, #101–#104, #107, #110, #111, #114), with no visible change while the product switch is off.
- Security update: dnspython 2.9.0 to 2.9.2 in the Headscale child environment (GHSA-vvf4-9x63-8xvv, High; the release scanner blocked it on 2026-11-18). No other dependency changes.
- Advance only Headscale's own version line, from 0.4.18 to 0.4.19; the shared default version stays 0.4.14.
- Image published and verified on 2026-11-18 (manifest `sha256:a05e1a35fe3a048590b34fb542a38bd9a2fa2883d5151bd5732903d7c44baed9`): built, accepted (container checks, supply-chain gate and J1900) and pushed by the GitHub-hosted release route (PR #121), then every layer fetched back anonymously. Readiness, the Upgrade comparison, HAOS acceptance and Store distribution remain separate gates.

## 0.4.14 — maintenance release for six products (images published and verified)

- Main reason: the admin panels of Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud accept Home Assistant Core 2026.11.0, 2026.11.1 and 2026.11.2 (PR #81, the review made for Headscale 0.4.14; PR #120: in 2026.11.2 the 25 Core contract and adjacent files are byte-identical to 2026.11.1, and Supervisor 2026.11.0 ships the reviewed WebSocket proxy unchanged). Their 0.4.13 images accept Core only up to 2026.10.4 and refuse every admin panel request on Core 2026.11.x; MCP endpoints do not use this check. Later patches (such as 2026.11.3) and pre-releases stay refused until reviewed.
- Includes the merged post-0.4.13 changes that reach these images (listed in `docs/multi-profile/unreleased-changes.md` until this release):
  - Every product, OpenDesign's source included: log redaction applies the PaaS server's rules first (#98); the child on port 3000 serves only the gateway's child bearer (#94; n8n's child already did); restore detection leaves an owner-only `.restore-detected` marker after a restore (#97); credentials in a child's `initialize` error are redacted (#103); gateway request limits aligned with the PaaS server (#105); a rare 30 s wait when stopping is fixed (#106).
  - Hermes: `hermes_cron` `create` with `enabled=false` now creates the job paused (#85), and the tool description says what `enabled=false` and `trigger` do (#115).
  - EMQX: `emqx_test_rule_sql` is labeled as needing write permission (#87). EMQX and LiteLLM: the connection pools ask for no idle connections, with no behavior change (#113). EMQX, LiteLLM and Nextcloud: a shorter policy-restart notice in the admin panel (#77).
  - OpenDesign (source only): `read_file` lists its reviewed output schema (#86).
  - The switched-off groundwork for multiple profiles (#91, #93, #95, #99, #101–#104, #107, #110, #111, #114): no visible change while the product switch is off.
- Security update: dnspython 2.9.0 to 2.9.2 in the EMQX, LiteLLM and Nextcloud child environments (GHSA-vvf4-9x63-8xvv, High; the release scanner blocked the first 0.4.14 candidates of these three on 2026-11-18). No other dependency changes.
- Advance the shared default version to 0.4.14: Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud, and OpenDesign's source version (it stays disabled in the Store). Headscale stays on its own version line and carries the shared changes from its 0.4.19 release (above).
- Images published and verified on 2026-11-18: built, accepted (container checks, supply-chain gate and J1900) and pushed by the GitHub-hosted release route (PR #121), then every layer fetched back anonymously. Readiness, the Upgrade comparison, the HAOS regression (on Core 2026.7.2, by the owner's decision) and Store distribution remain separate gates; see the [release record](docs/operations/release-decision-0.4.14.md).

## Headscale 0.4.18 — reviewed output schemas

- Publish the reviewed output-schema metadata from PR #86 for all 11 Headscale tools. Public `tools/list` now carries each child-declared object schema and continues to omit a schema if its reviewed binding drifts.
- Keep the 29 native operations, tool inputs, authorization policy, backend handlers, Origin policy and DNS fallback unchanged from 0.4.17.
- Other products keep their published versions. GHCR publication, Stable Release, Store sync and two-host HAOS acceptance remain separate gates.

## Headscale 0.4.17 — DNS address fallback release candidate

- Include merged PR #83: after validating every resolved Headscale address, try each numeric address within the existing connection deadline. A failed first address no longer masks a reachable later address; destination validation and redirect denial remain in force.
- Include the Headscale secret URL Origin policy from PR #82. Version 0.4.16 is already a Stable Release and in the Store; its immutable image predates the DNS fix. Version 0.4.17 must be built and accepted from the merged source before this fix can enter the Store.
- Other products keep their published 0.4.13 versions. GHCR publication, Stable Release, Store sync and QA Supervisor upgrade remain separate gates.

## Headscale 0.4.14 — HA Core 2026.11 compatibility candidate

- Source-reviewed Core 2026.11.0 and 2026.11.1 across 25 role-contract/adjacent files and Supervisor 2026.10.5 proxy. The HA admin verifier adds only these exact releases; later patches and prereleases remain denied.
- Headscale gains an independently pinned 0.4.14 manifest, build, MCP version and registry tag. The seven other add-ons retain their published 0.4.13 images and compatibility until separately rebuilt.
- Candidate image, public registry and Store-installed HAOS 2026.11.1 acceptance remain separate release gates.

## 0.4.13 — images published and verified (2026-11-08)

- Includes the merged post-0.4.12 source changes in PRs #73–#75. URL path arguments are encoded as one segment before HTTP normalization; the gateway also refuses dot-segment paths and rejects newly saved backend URLs that the runtime would refuse.
- Nextcloud read ETags omit compression suffixes so conditional update and delete can use them; the upstream and PaaS source fixes have already merged.
- The admin panel explains child restarts on policy saves, accepts an EMQX base URL ending in `/api/v5` by normalizing it, and improves Odoo, LiteLLM and Nextcloud credential guidance.
- Advance all seven source versions together. OpenDesign stays disabled in the Store; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud are enabled image products.
- Six images from source `4966f40f` passed P1–P5, anonymous readback and fresh remote layer verification. See [release decision](docs/operations/release-decision-0.4.13.md) and [provenance](docs/provenance/release-0.4.13-images.json). Stable distribution and HAOS acceptance are separate.

## 0.4.12 — images published and verified (2026-11-07)

- Include merged PRs #65–#70 (#67–#70 reached `claude-delivery` through #71: they had been merged into their stacked base branches):
  - Odoo (#65, #66): the readiness probe tells a login Odoo refused (`BACKEND_AUTH_REJECTED`, fixed text) from a server that cannot be reached; tool calls wait up to 30 s for Odoo, as the PaaS server does (the probe keeps 5 s); with "Allow Unreviewed Methods" off `execute_method` runs every method of the reviewed read list; `health_check` reports 41 tools; the admin API answers 400 instead of 503 to a `null` body on `PUT api/odoo/write-switches`.
  - n8n (#67, #69): `n8n-mcp` runs on the pinned native better-sqlite3 12.11.1, the PaaS image's engine, instead of the sql.js fallback: `search_nodes` ranks and filters (`source: "core"`) like the PaaS server, replies no longer carry `mode`, and the `n8n_workflow_versions` counters are real values; the workflow version history lives in a private copy inside the container and starts empty after the add-on is recreated or updated; `n8n_delete_workflow` says how to delete a published workflow, as on PaaS.
  - Hermes (#68): `hermes_mcp add` refuses a cloud-metadata URL with the PaaS sentence (`INVALID_INPUT: url blocked by SSRF protection: Cloud metadata endpoint blocked`); the unique-local metadata addresses `fd20:ce::254` and `fd00:a9fe:a9fe::1`, which 0.4.11 registered, are refused now.
  - Every Python child (#70): a request path may carry a literal `%` (a Nextcloud file, folder or calendar name, an EMQX client id…) as long as no decoder can read more into it than the first decode gave; httpcore's `target` request extension is refused.
- Documentation: every add-on's DOCS states that it publishes tools only (no prompts or resources; only Nextcloud sends server instructions, the same text as the PaaS server) and what the PaaS server publishes besides; the owner decided on 2026-11-07 to keep it so.
- Build note: the n8n image build downloads one pinned file from github.com (the better-sqlite3 prebuilt for Node 26; URL, size and sha256 in `packaging/inputs.json`, checked by `packaging/native_addon.mjs`; no upstream signature exists). The builder needs egress to github.com and its redirect host.
- Advance seven source versions together; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud are enabled image products. OpenDesign stays disabled and Odoo Manage remains archived.
- Six exact-source images (source `359963f4`) passed P1–P5 and were published; anonymous readback and fresh remote layer/diffID checks passed. Stable Releases/Store and actual HAOS/backend acceptance remain separate evidence. See [0.4.12 release decision](docs/operations/release-decision-0.4.12.md) and [image provenance](docs/provenance/release-0.4.12-images.json).

## 0.4.11 — images published and verified (2026-11-05)

- Include merged PR #58: every MCP-visible Hermes error reads `CODE: text` (same table as the PaaS woow-mcp-server); Dashboard and Gateway transport failures use fixed public wording that never repeats the configured URL, upstream body, redirect Location or transport text; wrong reply shapes are rejected; a turn the Gateway itself reports as failed returns `CHAT_TURN_FAILED` with the Gateway's own message. Hermes tool names, inputs, settings and grants do not change. The output-schema registry keeps its 136 reviewed entries; its n8n and Hermes source pins move to the commits that carry these sources.
- Include merged PR #59: the seven MCP add-ons declare `stage: stable` and drop the "Experimental;" prefix from their store description (the image `io.hass.description` label follows), so the Home Assistant store stops showing the experimental badge once a Stable Release carries this version. The retired Odoo Manage image label is unchanged.
- Advance seven source versions together; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud are enabled image products. OpenDesign stays disabled and Odoo Manage remains archived.
- Security: the OS-package step of every image Dockerfile (generated from `packaging/inputs.json` `os_security_upgrades`) also upgrades `apt` and `libapt-pkg6.0` from 2.6.1 to 2.6.2, taken from the signature-checked Debian security snapshot `20261104T124343Z`, because the pinned Python base still carries the vulnerable 2.6.1 (CVE-2026-109518, High, fix available). The supply-chain policy, scanners and pins are unchanged; no policy exception is added. The n8n output-schema source pin is rebound again to the commit that carries the changed Dockerfile.
- Six exact-source images (source `2ad4521c`) passed P1–P5 and were published; anonymous readback and fresh remote layer/diffID checks passed. Two earlier attempts closed fail-closed with nothing published. Stable Releases/Store and actual HAOS/backend acceptance remain separate evidence. See [0.4.11 release decision](docs/operations/release-decision-0.4.11.md) and [image provenance](docs/provenance/release-0.4.11-images.json).

## 0.4.10 — images published and verified (2026-11-04)

- Based on the protected PR #46 merge `fc5c7cf4`: Odoo failed generic reads now return errors instead of successful empty results; successful generic record reads above the default 2 MiB limit return `success:false`/MCP `isError:true` with field-size guidance.
- Include merged PR #48: the Odoo gateway now advertises all 41 upstream output schemas. Include merged PR #49: n8n-mcp 2.96.2 now declares object-valued workflow warning/error details correctly, and the HA gateway advertises the corrected validator schemas. Tool names, input schemas and grants do not change.
- Include merged PR #50: the HA Hermes gateway and fallback now advertise 11 reviewed output schemas matching the pinned child and PaaS runtime; Hermes tool names, inputs, settings and grants do not change.
- Include merged PR #54 (source PRs #51–#53): EMQX errors are bounded and redirects rejected; its gateway/fallback advertise 39 reviewed output schemas. Hermes dashboard connection and missing-configuration failures provide bounded user guidance. The merged registry has 136 exact output-schema pins; tool names, inputs and grants remain unchanged.
- Include merged PR #55: Nextcloud now reports only a fixed quota category for recognized backend errors and omits redirect Location; arbitrary backend diagnostics stay private. Its source provenance is rebound to `3abcf334` without changing the eight reviewed output schemas, tool names, inputs or grants.
- Include merged PR #56: recoverable Odoo XML-RPC connection drops and timeouts retain `BACKEND_UNAVAILABLE`/`BACKEND_TIMEOUT` categories so pinned `odoo-mcp==1.3.0` can perform its bounded read-only retry; writes remain one attempt, with pinned destination, redirect denial and grants unchanged.
- Include source PR #57 (merged into the release branch as `5420b95f`): Hermes Dashboard failures use fixed public categories, malformed/deep/non-object replies are rejected, and an ambiguous cron creation sends exactly one POST and reports an unknown outcome. Tool names, inputs and grants do not change.
- n8n lockfile: `follow-redirects` 1.16.1 → 1.16.2 (GHSA-mrwp-f3q8-3g9p, `7cac1668`). The n8n output-schema source pin is rebound to that commit; the 136 schema entries, tool names, inputs and grants are unchanged.
- Advance seven source versions together; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud are enabled image products. OpenDesign stays disabled and Odoo Manage remains archived.
- Six exact-source images (source `78a4e69c`) passed P1–P5 and were published; anonymous readback and fresh remote layer/diffID checks passed. Stable Releases/Store and actual HAOS/backend acceptance remain separate evidence. See [0.4.10 release decision](docs/operations/release-decision-0.4.10.md) and [image provenance](docs/provenance/release-0.4.10-images.json).

## 0.4.8 — release candidate (2026-10-30; images pending)

- Vendor Nextcloud MCP v0.1.6 (`8aa6be3`) from merged PR #41; sanitize credentials through the upstream error-handling implementation.
- Retain the reviewed Nextcloud output-schema adaptation (`0383334`) and inherited 0.4.7 management contracts. No new tool/schema/configuration breaking change.
- Publish six products through the existing private exact-image P1–P5 pipeline after source checks. OpenDesign remains disabled. Publication, distribution and real HAOS acceptance are separate recorded outcomes.

## 0.4.7 — release candidate (2026-10-30; images pending)

- Require the exact reviewed configuration revision for every persisted admin mutation.
- EMQX retained reads report non-404 failures; failed retained deletes never dispatch a fallback publish. Invalid/empty JSON success bodies are refused except explicit204.
- The P9 operator driver uses the shared reviewed-revision and operation-receipt client, stops on unconfirmed results and does not resend automatically.
- Token rotation, revocation and child restart use durable operation IDs; query or explicitly resend the same ID after a lost response without repeating a completed effect.
- Recheck current administrator authority before receipt disclosure/replay; HA receipts belong to the original user. Replays never return historical tokens.
- Admin API clients must send If-Match and, for token/restart actions, Idempotency-Key. Token revoke now returns200 JSON instead of204. Include the hidden operation journal in data backups; unknown outcomes require state review, not blind retries.
- Six enabled images require fresh exact-image P1–P5, anonymous verification and provenance before release. OpenDesign remains disabled. See docs/operations/release-decision-0.4.7.md and upgrade-notes.yaml.

## 0.4.5

- Integrates PR35 and PR36 on the protected 0.4.4 merge.
- n8n native success:false results carry isError:true; content and structuredContent are preserved.
- Expose 22 audited n8n operation limits without changing the existing 33 write grants. Unknown selectors cannot dispatch; denying trigger also blocks auto/default.
- Correct LiteLLM update-model registry to PATCH /model/{model_id}/update.
- Keep the legacy migration catalog independent of current selector additions and verify only reviewed operation effect differences.
- Six enabled images require fresh P1–P5, anonymous verification and provenance before merge; OpenDesign remains disabled.

# Changelog

## 0.4.4 — release candidate (2026-10-29; images pending)

Combines PR30 Odoo error results, PR31 child write switches, PR32 token history and PR33 Nextcloud secret
redaction on the PR29 0.4.3 base.
Seven source manifests and version bindings are 0.4.4; only six Store-enabled products will publish.
This candidate has no built or published images; the existing 0.4.3
image receipt applies only to its recorded source, never to these changes.

- Odoo tool results with `success: false` now carry MCP `isError: true`; text JSON and outputSchema-compatible
  `structuredContent` are retained, including the SDK result envelope. Tracebacks are reduced to the final exception
  line. The conversion also covers refusals from the four-switch overlay, before the existing worker/error wrappers.
- Odoo exposes `enable_writes`, `allow_direct_writes`, `allow_unknown_methods` and `chatter_direct` in the admin panel.
  A protected, revision-checked save persists all four booleans atomically and restarts the child. Missing state keeps
  the prior all-on defaults. The source-guarded PaaS decision module controls actual child execution and descriptions;
  outer tool grants and operation denies still apply. Exact `model.method` allowlist editing remains a parity gap.
- The panel shows the current token's mask and at most five rotate/revoke events with UTC times and previous-token
  masks. Each token transition and event share one durable write; repeated revoke adds no event. No old token is
  retained in history, and active leases are invalidated only after commit.
- Nextcloud masks its configured password and Basic-auth credential forms in decoded backend error detail before
  whitespace folding or truncation. Literal, URL-quoted, JSON-escaped and standard/URL-safe base64 forms are covered;
  detailed diagnostics, public error codes, isError, auth latches and successful replies are retained. Real child and
  gateway tests use fake credentials; unknown secrets or arbitrary encodings are outside this bounded contract.
- Schema 4 is unchanged in number and existing files are not rewritten at startup. Saving Odoo switches persists
  `odoo_write_switches`; rotating/revoking a token persists `token_history`. The 0.4.3 decoder rejects either new key.
  Back up before upgrading; downgrade after either action requires restoring that pre-upgrade add-on backup and
  reviewing restored grants/tokens. Do not silently strip keys or manually edit state. See `upgrade-notes.yaml`.

## 0.4.3 — release candidate (2026-10-28)

Applies to the six Store-enabled add-ons and the OpenDesign source. The six 0.4.3 images require
fresh exact-image acceptance before release; OpenDesign stays disabled in the Store.

### Legacy installations: one-time all-on at the first start (aligned with the PaaS; owner decision 2026-10-27)

- A legacy state (schema 1/2/3, written by 0.1.x or the 2026-10-03 prototypes) is migrated before ProductStore or any
  child starts (`mcp_admin_core/owner_defaults.py`, called by `run_product.py` and `apps/n8n/run.py`) to exactly the
  all_on plan the 0.3.0–0.4.1 review page applied: schema 4, writes on, every write grant, nothing disabled, no
  operation deny; token, child token, endpoint and backend kept. The same atomic state write adds the marker
  `owner_defaults_20261025` (`applied`, `at`, `from_schema`, later `restored_at` / `acknowledged_at`), the PaaS
  marker's name. Before it, the legacy policy is saved once as the format 2 record
  `/data/mcp/owner-defaults-20261025-recovery.json` (0600, exclusive, policy and digests only), published complete or
  not at all (temporary file, fsync, link), so a failed or interrupted write never leaves a partial record that would
  stop every later start; an identical record from an interrupted attempt is reused, any other refused. MCP then
  serves at once: no 503 `upgrade_review_required`, no review listener; one fixed line in the add-on log.
- Schema 4 is never touched (new installations, 0.2.0+, states the review page migrated, ws97's writes-off Hermes).
  The marker is omitted while absent, so such states keep exactly the 0.4.1 keys.
- Unreadable, invalid, linked or busy state, a record that cannot be saved, or an existing record that is not this
  state's: nothing is migrated or rewritten (bytes, mode, mtime); the add-on logs which of these (fixed text naming
  the file) and stops with `runtime unavailable; local recovery required`. After a disk-full failure a restart with
  free space completes the migration.

### The review page becomes a notice with an optional, faithful restore

- The pre-start review listeners, `upgrade.py` and the `upgrade.js` page are removed. The normal panel shows, on
  every page until the administrator acts, when (UTC) the defaults were applied, from which schema and the
  differences (`bootstrap.owner_defaults`).
- "還原升級前的限制" (`POST /api/owner-defaults/restore`, CSRF and `If-Match` required, 428 without it):
  `migration.plan_owner_restore` reads each legacy list the way 0.1.x enforced it. Tools are a deny list: the tools
  the legacy state disabled are disabled again and a tool added since 0.1.x stays enabled, so never "everything
  disabled" as with `preserve`. Writes are an allow list: only the grants the legacy state held stay (exact grants;
  the legacy switch for n8n `n8n_delete_workflow` and OpenDesign `delete_project`) and every other write is revoked,
  one added since 0.1.x included, as 0.1.x refused it; its legacy switch and operation denies come back. The restored
  policy permits exactly the writes the legacy runtime permitted (ws97 Hermes 0.1.14 sample: no write, 9 of 11 tools
  listed, `preserve` gave 0; a 0.1.14 n8n default: no write, 18 of 28 tools). Restrictive merge: later
  administrator limits stay; nothing is enabled. EMQX, LiteLLM and Nextcloud restart their child, as for a saved
  policy.
- "保持全開，不再提示" (`POST /api/owner-defaults/dismiss`) records `acknowledged_at`; the restore stays on the
  diagnostics page. The offline CLI `--restore-policy` accepts the format 2 record too.
- The notice is only in the add-on panel and one add-on log line (no sidebar entry by default, no HA notification),
  so the README, every DOCS and every add-on CHANGELOG (the Store's update notes) say to open the panel after the
  upgrade. A notice the panel cannot read is not hidden: a fixed card 「升級通知無法顯示」 asks to reload or update
  the add-on (no server value, no action).

### Tests and docs

- `tests/test_owner_defaults.py` with real legacy samples (`tests/fixtures/owner_defaults`: schema 1/2 written by
  313ab01, schema 3/4 by v0.1.14/v0.2.2 and by the real ws97 Hermes add-on; fake tokens only); browser and
  unit tests for the notice. README, DOCS, guide, legacy migration,
  update/rollback and `upgrade-notes.yaml` describe the new behavior. Rolling back a migrated installation to 0.4.1
  needs the pre-update backup (0.4.1 refuses the marker key).

## 0.4.2 — release candidate (2026-10-27)

The management panel's HA role check (shared by the seven add-ons) accepts three more Home Assistant Core releases
and says why when it refuses an unreviewed one. This patch release builds new images for the six Store-enabled add-ons. It changes no option, port, tool,
grant or state schema.

- Core 2026.10.2, 2026.10.3 and 2026.10.4 are added to `ha_role._HA_VERSIONS` after the contract review recorded in
  [ha-role-core-contract.md](docs/ha-role-core-contract.md): 20 of the 21 consumed Core files and the 4 adjacent ones
  are byte-identical to 2026.10.1; `auth/__init__.py` only changes `AuthManager.async_remove_user` (it now revokes a
  removed user's refresh tokens), outside `config/auth/list`. Supervisor 2026.10.2–2026.10.4 (`api/proxy.py`
  `cab849dc`) only start the two proxy loops as background tasks; the auth frames are unchanged.
- Any other Core version, pre-releases included, is still refused, now with the reason: the panel's pages show
  「這個 HA Core 版本尚未審核：<version>」 as static text, its API answers 403
  `{"error": "request denied", "detail": {"code": "core_version_unreviewed", "ha_version": ...}}`, and the add-on log
  gets one line per version (no frame, token or user). The machine token is still never sent to such a version, and
  every other refusal keeps the fixed `{"error": "request denied"}`. MCP endpoints do not use this check.
  `tests/test_ha_role.py`, `packages/mcp-admin-ui/tests/core-version.test.mjs`.

## 0.4.1 — release candidate (2026-10-25)

The six Store-enabled add-ons carry the reviewed HA management UI update from PR #20 on the merged 0.4.0 base. For n8n, the Tools page shows that `exposeToMcp: true` can write even when the selected operation reads, names the existing `n8n_update_partial_workflow` dependency and distinguishes saved policy from a draft or unknown child state. No grant, default, gateway enforcement, dependency, option, port, image name or state-schema change is intended; OpenDesign remains disabled. 0.4.0 images do not contain this UI change. See [0.4.1 release decision](docs/operations/release-decision-0.4.1.md); image publication and ws97 upgrade remain pending.

## 0.4.0 — release candidate (2026-10-25)

The six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) move to 0.4.0,
after 0.3.4: phase 2 of the MCP SDK 2 migration (issue #21; the WOOW PaaS twin
woow-mcp-server did phase 1 in #81 and #82). OpenDesign stays disabled (metadata
version only, no image). No option, port, architecture, image name, tool name or
state schema changes; schema stays 4 and the full-functionality defaults are
unchanged. One declared breaking change: 13 Odoo tools return their structured
result unwrapped (`upgrade-notes.yaml`). See the
[0.4.0 release decision](docs/operations/release-decision-0.4.0.md).

### Dependencies

- Python MCP SDK `mcp` 1.30.0 -> 2.3.0 (plus `mcp-types` 2.3.0) in the six Store
  children; FastMCP 3.4.11 -> 4.1.3 (EMQX, LiteLLM, Nextcloud); `odoo-mcp` 1.1.0 ->
  1.3.0 (Odoo; both build patches apply unchanged). The SDK brings httpx2/httpcore2
  2.16.0, truststore 0.10.5 and opentelemetry-api 1.45.1 and drops httpx-sse; the
  children's backend clients stay on HTTPX 0.28.1. The archived Odoo Manage keeps its
  own mcp 1.30.0 / mcp-server-odoo 0.7.1 lock.
- Node 22.23.4 -> 26.12.1 (Active LTS from 2026-10-28) in every image and in CI
  (`node:26.12.1-bookworm-slim`, multi-arch index digest). Node 26's official binary
  links libatomic.so.1: the n8n image copies the node stage's Debian libatomic1 library
  next to libstdc++/libgcc_s and checks `node --version` right after. n8n-mcp 2.96.2
  and the 28 n8n tools are unchanged; the n8n child keeps its sql.js fallback
  (`npm ci --ignore-scripts`, no native better-sqlite3).

### MCP SDK 1 -> 2 behaviour, kept as it was

- Tool error text: SDK 2 shows only `Error executing tool <name>` for any exception but
  `ToolError`. `apps/runtime/tool_error_text.py` (port of the PaaS `keep_error_text`)
  restores the 1.x text in Odoo, Hermes and OpenDesign; the real children answer the
  same texts as 0.3.4.
- Odoo concurrency: SDK 2 runs sync tools on parallel worker threads; `BoundedTools`
  still serializes every Odoo tool (writes included) on its one owned worker.
- Request body 16 MiB and the 30-minute session idle limit still take effect
  (`apps/runtime/session_idle.py`, verified with SDK 2 and six real children).
- FastMCP 4 cancels a running async tool when its session is deleted: the Nextcloud
  readiness probe is shielded, so a slow 401 still latches (at most two failed logins).
- Protocol: clients stay on the 2025 handshake era. The gateway still answers
  `server/discover` itself (-32601) and no longer forwards a client's
  `MCP-Protocol-Version` header with an initialize (SDK 2 children refuse such an
  initialize). Raw JSON-RPC, the Python SDK 1.30 and 2.3 clients and the TypeScript SDK
  1.32 client connect, list and call through the gateway (`tests/test_protocol_clients.py`).

### Odoo tool texts match the add-on's gating

- odoo-mcp 1.3.0 tells the model that `execute_method` blocks direct create/write/unlink and
  that `chatter_post` needs a preview approval token; this add-on runs both directly
  (`ODOO_MCP_ALLOW_DIRECT_WRITES=1`, `MCP_CHATTER_DIRECT=1`). The HA copy of the
  direct-writes build patch makes both texts follow those switches (and now accepts only
  the published 1.3.0 file and writes one pinned digest); the behaviour is unchanged.
  `tests/test_odoo_write_descriptions.py`.

### Hermes

- The vendored Hermes files are re-snapshotted from woow-mcp-server main (server.py
  as of 471efdf: SDK 2 `MCPServer`, 1.x error text), keeping the HA changes, including
  the 0.3.4 loopback refusal (AI-HMCP-002-2) and the LAN allowance.

## 0.3.4 — stable Release (2026-10-24)

The same six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) move to
0.3.4, after 0.3.3; 0.3.2 is not used (it had been reserved for this release).
OpenDesign stays disabled (metadata version only, no image). 0.3.4 is a dependency
and Hermes security release on top of 0.3.3: no option, port, architecture, image
name, tool name or state schema changes; schema stays 4 and the full-functionality
defaults are unchanged. See the
[0.3.4 release decision](docs/operations/release-decision-0.3.4.md).

### Dependencies (aligned with the WOOW PaaS twin)

- Python MCP SDK `mcp` 1.28.1 -> 1.30.0 in every Python child (GHSA-84m7-p3x7-pcfv:
  Streamable HTTP sessions were never reclaimed). The add-on keeps its 30-minute
  session idle limit and raises the SDK's new 4 MiB request-body default to the
  gateway's 16 MiB (`apps/runtime/session_idle.py`).
- FastMCP 3.4.5 -> 3.4.11 (EMQX, LiteLLM, Nextcloud; includes the GHSA-7xgj-8392-5q4r fix);
  `certifi` 2026.10.19 -> 2026.10.23;
  the other locked Python packages move to their newest release in the same major
  (pydantic 2.14.1, pydantic-settings 2.16.1, starlette 1.9.0, websockets 17.3, ...).
  `odoo-mcp` 1.1.0 and `mcp-server-odoo` 0.7.1 stay (the same as the PaaS; Odoo's
  build patches match their source text).
- n8n: `n8n-mcp` 2.91.0 -> 2.96.2, MCP TypeScript SDK override 1.32.0 -> 1.32.2, and
  the newest npm versions inside the existing ranges (`npm audit`: 0 findings; fixes
  body-parser GHSA-27r3-jxmh-p828, undici GHSA-4qv8-2p9j-2685 and GHSA-xjj6-f33q-929c,
  zod GHSA-mrhx-c7xc-m3w5 and moderate fast-uri/ip-address advisories). The 28 tool
  definitions are byte-identical to 2.91.0's; the test-run error build patch is
  re-pinned to the 2.96.2 file. `n8n_health_check` no longer queries the npm
  registry: the child runs with `N8N_MCP_VERSION_CHECK_DISABLED=true`, as the PaaS
  (`checkStatus: "disabled"`).
  The 0.3.3 effective-argument authorization (`output` extraction, conditional
  `exposeToMcp` writes) is re-reviewed against 2.96.2: `validateExtractedArgs`, the
  extraction and `coerceStringifiedJsonParams` are byte-identical and its tests pass
  against the 2.96.2 child.
- Node 22.23.2 -> 22.23.4 for every image (n8n-mcp 2.96.2 requires `^22.23.4`).
- MCP SDK 2.x, FastMCP 4 and Node 24 are a separate migration.

### Hermes

- `hermes_mcp` action=add refuses loopback MCP server URLs again (localhost,
  *.localhost, localhost.localdomain, 127.0.0.0/8, ::1, IPv4-mapped loopback):
  the loopback part of AI-HMCP-002-2 that the LAN-friendly guard of 0.3.0-0.3.3
  dropped. LAN addresses stay allowed; metadata, link-local and 0.0.0.0 stay refused.
  A refused URL sends no dashboard API request. Servers registered earlier are not
  removed.
- The vendored Hermes MCP files are recorded against woow-mcp-server main `a5db051`;
  0.3.0-0.3.3 already contain the same code.

## 0.3.3 — stable Release (2026-10-24)

This candidate integrates a bounded n8n authorization correction in the shared
runtime. Exact-source freeze/CI remain pending, followed by fresh six-image
container/supply-chain gates and publication. See the
[0.3.3 release decision](docs/operations/release-decision-0.3.3.md).
Published 0.3.1 images and their evidence remain unchanged.

Version 0.3.2 is reserved by the separate dependency-update PR17. This bounded
authorization release uses 0.3.3 to avoid assigning the same image tags to
different sources. Our unpublished 0.3.2 candidate is superseded; no PR17
dependency changes are merged into this release.

- All 28 n8n tools normalize the pinned child's one-level eligible `output` JSON
  wrapper before checking operation denies/grants and forwarding the same
  effective arguments. This closes outer-read/inner-write overrides for all six
  mixed selectors. A second eligible wrapper is refused as ambiguous; repeated
  authorization is idempotent, with existing input budgets applied first.
- A workflow-history read with effective `exposeToMcp=true` can also change the
  workflow's MCP exposure setting. The correction requires the existing
  `n8n_update_partial_workflow` tool to be enabled with its effective write grant,
  in addition to the invoking tool/mode's own permission, before child dispatch.
  The same dependency applies to `n8n_test_workflow` exposure requests.
- Revoking or disabling the updater must prevent this indirect write, including
  the pinned child's accepted boolean and output-wrapper representations.
  Requests without exposure retain their existing read behavior; full-policy
  users retain exposure functionality. No new write grant is introduced.
- Additive `conditional_writes` capability metadata names the exposure parameter,
  existing updater dependency and its effective policy state. Existing UI grant
  controls remain sufficient; no UI source or new persisted permission is added.
- The n8n contract remains 28 tools and 33 write grants. Schema 4, saved tokens,
  dependencies, child versions and UI source are unchanged by this correction.
  Fresh installs retain maximum functionality. Existing schema 1/2/3 upgrades
  retain authenticated prestart review with `all_on` preselected and explicit
  administrator confirmation; current-schema startup remains unchanged.

All six enabled products advance together under the shared-core version
contract. OpenDesign receives source metadata only and remains unpublished.
No option, port, architecture, image name or privilege change is planned.
Existing state needs no migration, but downgrading the binary restores the
conditional-write defect. Preserve a backup and current token/policy state.
The planned official Hermes test upgrades 0.3.0 directly to 0.3.3 with a fresh
backup; no official 0.3.1 HAOS upgrade is claimed.

## 0.3.1 — stable Release (2026-10-24)

Six enabled add-ons share the runtime and UI fixes below. OpenDesign remains
disabled: metadata only, no image or stable Release. Exact 0.3.1 image acceptance,
supply-chain scans and publication are pending; source/candidate results do not
replace those gates. See the [release decision](docs/operations/release-decision-0.3.1.md).

- Management bootstrap, saves and restart responses add configuration revisions
  and pending/applied/failed/unconfigured/unknown status. Applied means the current
  child generation completed its protocol probe; backend health remains separate.
  Token and endpoint changes do not imply a child restart.
- Fix a literal `null` appended to the configuration status card when no stale
  revision warning is needed. Initial applied display and status/page refreshes
  now render only DOM rows; older bootstraps without configuration omit the card.
- Optional `If-Match` rejects stale settings with HTTP 409 before any durable
  write or child replacement. Existing clients without the header remain
  compatible. The UI retains a conflicting draft until explicit reload, which
  clears the draft; it never silently advances an open form's revision. Revisions
  are process-local, so forms opened before a management restart must reload.
- A committed save followed by failed child replacement reports HTTP 503,
  `saved:true`, a fixed safe error code and failed apply status. Management remains
  available after launch failure. The UI distinguishes saved from applied and
  does not retry the mutation automatically.
- Persisted shared-token revoke/rotate now cancels already-open GET/POST streams,
  pending child I/O and blocked response sends on both public MCP routes, without
  restarting the child. Cleanup closes paused upstream iterators and joins owned
  readers/slots. A response that has started closes instead of changing its HTTP
  status. Already delivered bytes and dispatched backend work cannot be recalled.

No state-schema, dependency-pin, child-runtime, manifest option, port, architecture
or privilege change. Maximum functionality remains the default for new installs;
existing schema 4 keeps its saved policy. Upgrades from schema 1/2/3 retain the
0.3.0 authenticated prestart review: `all_on` is preselected but an administrator
must confirm, or explicitly choose `preserve`. Back up before upgrading, then open
the panel if legacy review is pending. Current credentials and revoked state are
preserved; this patch does not automatically re-enable tokens or restricted tools.

## 0.3.0 — stable Release (2026-10-24)

Six enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) share this
release. OpenDesign stays disabled: metadata version only, no image publication.
The default remains maximum functionality: all tools and writes enabled on new
installations, with `all_on` selected by default in legacy upgrade review.

### Upgrade behavior change

Legacy schema 1/2/3 waits in an HA-admin-authenticated Ingress review before any
ProductStore migration or MCP child starts. An administrator must confirm
`all_on` or explicitly choose `preserve`. Unattended legacy upgrades therefore
remain in review until confirmation; MCP and readiness return 503. Fresh
installations and existing schema 4 retain normal startup. Existing tokens,
including revoked ones, are preserved.

Back up before upgrading. Open the add-on panel, compare both previews, and
confirm. After durable migration, review listeners stop and the normal runtime
starts on the same ports. `preserve` disables new tools and tools whose expanded
arguments need review; it cannot recreate old binary argument restrictions.

### Security dependencies

- Pin certifi 2026.10.19 in the six published products to address
  GHSA-6q48-6c7w-9gw2; rebuild the vendored Python environments.
- Pin n8n MCP SDK 1.32.0 for GHSA-22jm-h49p-29qw and
  GHSA-46jr-4wx8-v453, with a product-specific input-budget mitigation.
  After authentication, n8n requests are limited to 4 MiB, 10,000 recursive
  argument members/elements and depth 64. JSON-looking encoded argument
  structures share the element budget and a cumulative 4 MiB decoding budget;
  compressed requests are rejected. Oversized workflows must be split or
  reduced. Other products retain their existing request limits.
  Release scans retain the original policy and severity threshold.

### Policy and token management

- Per-operation denies and exact write grants distinguish saved from effective
  access. Disabled operations remain denied even with a saved write grant.
- Token rotate/revoke persists the shared-token change before invalidating old
  access, without restarting the child; already dispatched backend work cannot
  be rolled back. Revoked state survives reload/restart and stale generic saves.
- The offline CLI previews/applies legacy migration and restrictive policy
  recovery. Recovery retains current credentials, unions denies and intersects
  grants; it never restores an old token or enables a later-disabled global write.
- EMQX/LiteLLM/Nextcloud policy updates retain their existing child restart
  behavior; affected clients reinitialize after an old-session 404. Token-only
  changes do not restart the child.

Schema remains 4, but an older binary cannot enforce the new operation denies.
A downgrade is not equivalent to restrictive policy recovery. Stop the runtime
and review a compatible full backup plus current token revocations separately.
See [migration](docs/operations/legacy-migration.md),
[backup and rollback](docs/operations/update-backup-rollback.md), and the
[release decision and acceptance boundaries](docs/operations/release-decision-0.3.0.md).

The six exact-image supply-chain and anonymous registry gates completed, followed
by six per-addon stable Releases on 2026-10-24 through the existing Store workflow.
The linked 0.3.0 decision retains the exact image identities and acceptance limits.
