# 0.3.4 release decision — 2026-10-24

Status: pending image publication. Candidate dependency/Hermes changes and release
metadata only: no 0.3.4 image build, container/supply-chain acceptance, registry
publication or stable Release is claimed. All six exact-image gates and publication
receipts remain pending. The presence of this document is not evidence that those
gates passed.

## Scope

Six Store-enabled products move to 0.3.4: Odoo, n8n, Hermes, EMQX, LiteLLM and
Nextcloud. 0.3.4 follows 0.3.3 (PR #19: n8n effective-argument authorization and
conditional exposure writes), which followed 0.3.1 (PR #16: configuration application
status and active token revocation); both keep the 0.3.0 dependency pins. 0.3.2 is
not used: it had been reserved for this release. The latest stable release is 0.3.3
(six stable Releases published 2026-10-24 11:22 UTC); this branch is based on
`2343850`.
OpenDesign remains disabled in the Store registry; its source manifest shares the
version but no OpenDesign image or stable Release is requested. Existing immutable
tags must never be replaced. `RELEASE-GATES.json` stays closed.

0.3.4 contains:

1. the dependency alignment with the WOOW PaaS twin (woow-mcp-server) below,
   including `N8N_MCP_VERSION_CHECK_DISABLED=true` in the n8n child environment;
2. the Hermes loopback refusal of AI-HMCP-002-2 (below).

Ports, architectures, image names, manifest options, privileges, tool names and the
state schema (4) are unchanged; full-functionality defaults are unchanged. 0.3.0-0.3.3
installations upgrade without the legacy review page (that is only for schema 1/2/3).

## Versions

| Component | 0.3.0-0.3.3 | 0.3.4 |
|---|---|---|
| Python MCP SDK `mcp` (all Python children) | 1.28.1 | 1.30.0 |
| FastMCP / fastmcp-slim (EMQX, LiteLLM, Nextcloud) | 3.4.5 | 3.4.11 |
| `certifi` (children and core) | 2026.10.19 (OpenDesign/Odoo Manage source: 2026.7.22) | 2026.10.23 |
| pydantic / pydantic-core (children) | 2.13.5 / 2.46.5 | 2.14.1 / 2.50.1 |
| pydantic-settings (children; Nextcloud direct pin) | 2.15.0 | 2.16.1 |
| starlette (children) | 1.7.0 | 1.9.0 |
| other locked packages: pycparser 3.12 and rpds-py 2026.9.1 (all children); authlib 1.9.1, beartype 0.23.1, cachetools 7.2.4, caio 0.12.10, cyclopts 5.3.0, dnspython 2.9.0, griffelib 2.4.1, joserfc 1.7.7, more-itertools 11.2.1, opentelemetry-api 1.45.1, platformdirs 4.13.5, uncalled-for 0.4.1, websockets 17.3 (FastMCP children) | locked | newest in the same major (`uv lock --upgrade`) |
| `odoo-mcp` / `mcp-server-odoo` | 1.1.0 / 0.7.1 | unchanged |
| `n8n-mcp` | 2.91.0 | 2.96.2 |
| MCP TypeScript SDK (npm override) | 1.32.0 | 1.32.2 |
| other npm packages | locked | newest inside the existing ranges (`npm audit`: 0) |
| Node base image | `node:22.23.2-bookworm-slim` (linux/amd64 child digest) | `node:22.23.4-bookworm-slim@sha256:de170b39…` (multi-arch index digest) |
| CI Node (`setup-node`) | 22.23.2 | 22.23.4 |
| Core gateway pins (anyio, httpx, pydantic 2.12.5, starlette 1.3.1, uvicorn 0.38.0, websockets 15.0.1) | — | unchanged; only `certifi` moves in `uv.lock` |

`odoo-mcp` 1.2.0–1.2.3 and `mcp-server-odoo` 0.8.0 still declare `mcp<2`, but the
PaaS twin pins 1.1.0 / 0.7.1 and Odoo's two build patches match `odoo_mcp` source
text, so they stay; their latest releases (1.3.0, 0.9.0) require MCP SDK 2.x. MCP
SDK 2.x, FastMCP 4.x and Node 24 are a separate migration, as are the core
gateway's own pins.

## Dependency review

- **MCP SDK 1.30.0** (GHSA-84m7-p3x7-pcfv): the SDK now ends idle sessions itself
  (1800 s default), forgets a session at DELETE or when its opening request fails,
  caps sessions at 10 000 and request bodies at 4 MiB. The SDK's own FastMCP passes
  the idle default explicitly, so `apps/runtime/session_idle.py` also replaces a value
  equal to the parameter's default and sets the body limit to the gateway's 16 MiB
  `MAX_REQUEST` (Nextcloud uploads); the production idle limit stays 30 minutes.
  `func_metadata.py` only adds root-`$ref` inlining for structured output, so the
  `BoundedTools` guard digest moves; `tools/base.py` and `mcp/shared/version.py`
  (the gateway's `PROTOCOL_VERSIONS`) are byte-identical. Ported from the unmerged
  0.2.3 draft (PR #14), which this release supersedes.
- **FastMCP 3.4.11** (3.4.10 fixed GHSA-7xgj-8392-5q4r, post-transform component
  authorization skipped on direct calls): `settings.py` only adds `ssrf_trust_proxy` (auth metadata and
  JWKS fetches, off by default; no child configures auth). The banner/update-check
  settings and `utilities/version_check.py` are unchanged; the session manager still
  passes no body size.
- **n8n-mcp 2.96.2** (cumulative 2.91.0 → 2.96.2 tarball diff): `tools.js` and
  `tools-n8n-manager.js` are byte-identical (no tool added, removed or renamed).
  Reviewed changes and the new guard digests are in
  [n8n-tracer provenance](../provenance/n8n-tracer.md) and `apps/n8n/backend_policy.cjs`:
  request-scoped instance context (single-tenant here), UI-app metadata unless
  `N8N_MCP_DISABLE_UI_APPS=true` (not set), an `instance` argument only for a
  multi-instance context (never here), node deprecation details, validation codes,
  more blocked cloud-metadata IPv6 addresses, and a version-check status field.
  The 0.3.3 effective-argument boundary (`packages/mcp-admin-core/mcp_admin_core/n8n_arguments.py`)
  mirrors `validateExtractedArgs`, the `output` extraction and the `exposeToMcp`
  coercion of the pinned child: in 2.96.2 these are byte-identical; the only new step
  on that path drops a top-level `instance` key from built-in tool arguments after
  extraction, which no authorization decision reads. Only its ledger guard digest for
  `server.js` moves; `tests/test_n8n_exposure_policy.py` and
  `tests/test_n8n_request_bounds.py` pass against the 2.96.2 child.
  As in the PaaS, the fixed child environment now sets
  `N8N_MCP_VERSION_CHECK_DISABLED=true`, so `n8n_health_check` reports
  `checkStatus: "disabled"` and never queries the npm registry (0.3.0-0.3.3 did);
  `tests/test_boundary.py` runs the pinned checker in the child environment with a
  failing `fetch` stub and checks that an inherited `false` cannot re-enable it.
  `handleTestRunError` is unchanged, so the build patch keeps its replacement and is
  re-pinned (published `6860193f…`, patched `6cd67342…`). SDK 1.32.1/1.32.2 change only
  `McpServer`; this child uses the low-level `Server`, so the 0.3.0 n8n input budget is
  still the protection for GHSA-46jr-4wx8-v453. The 0.3.0-0.3.3 npm lock had advisories
  published after its scan (body-parser GHSA-27r3-jxmh-p828, undici GHSA-4qv8-2p9j-2685
  and GHSA-xjj6-f33q-929c, zod GHSA-mrhx-c7xc-m3w5, fast-uri, ip-address); the 0.3.4 lock
  has none (`npm audit --omit=dev`).
- **Licenses**: every changed Python and npm package declares MIT, BSD-3-Clause,
  Apache-2.0, ISC or MPL-2.0 (the policy's allowed list); no version-pinned
  `known_package_licenses` entry is affected.

## Hermes (AI-HMCP-002-2)

`hermes_mcp` action=add stores a URL that Hermes itself connects to later. The guard
of 0.3.0-0.3.3 reused `apps/runtime/backend_policy.py`, which permits loopback for
the add-on's own backends, so `http://127.0.0.1:8000/mcp`, `http://[::1]:8000/mcp` and
`http://localhost:8000/mcp` were registered (reproduced with 0.3.0's guard). The
Hermes guard now refuses localhost names (localhost, *.localhost,
localhost.localdomain) and every loopback answer (127.0.0.0/8, ::1, IPv4-mapped
loopback); `backend_policy`'s general rule is unchanged, LAN/ULA destinations stay
allowed and metadata, link-local and 0.0.0.0 stay refused. A refusal sends no
dashboard API request; servers registered earlier are not removed.
`tests/test_hermes_mcp_url_guard.py` runs the old BLOCKED_MCP_URLS list plus other
loopback spellings against the real child. The error keeps 0.3.0's stable text
(`BACKEND_INVALID_RESPONSE: loopback MCP servers (localhost, 127.0.0.0/8, ::1) cannot
be added`). The vendored Hermes files are recorded against woow-mcp-server main
`a5db051`; re-snapshotting them with the HA modifications reproduces the 0.3.0-0.3.3
files byte for byte, so only `guards.py` changes ([runtime sources](../provenance/runtime-sources.json)).

## Breaking changes

None under AGENTS.md rule 3: no option is removed or retyped, no port, architecture
or image name changes and no state needs conversion, so no `upgrade-notes.yaml`
entry is needed. Behavior changes are listed in the CHANGELOGs: Hermes refuses
loopback MCP server URLs (servers registered earlier are not removed), and
`n8n_health_check` reports the version check as `disabled` instead of querying the
npm registry.

## Local evidence (this pod; not image or HA acceptance)

Merged onto `2343850` (0.3.3) in the pi-agent pod: Node 22.23.4, CPython 3.13.15,
uv 0.12.10, no root and no container runtime.

- `packaging/validate.py` passes at 0.3.4. On the merged dependency state, 337
  targeted tests pass: the 0.3.3 n8n authorization tests
  (`tests/test_n8n_exposure_policy.py`, `tests/test_n8n_request_bounds.py`) against
  the 2.96.2 child, the real n8n child, the tool snapshot (real children list exactly
  the committed snapshot), `tests/test_hermes_mcp_url_guard.py` (fails on the earlier
  guard: `http://127.0.0.1:8000/mcp` is registered), `tests/test_session_idle.py`
  (real children accept a body just under 16 MiB), `tests/test_boundary.py` (version
  check disabled, an inherited `false` ignored), initialize identity, drift and the
  inventory/ledger tests.
- The same dependency changes on the previous base (`290f8c1`): the full local suite
  gave 2458 passed with one failure that needs root
  (`test_uid10001_nondumpable_self_and_own_child_proof`; CI runs pytest with `sudo`;
  the 0.3.0 baseline fails it the same way here), and the hosted `checks` job passed
  with 2459 executed cases and no skips on two heads. Packaging unittests show the
  same 2 errors and 5 skips as the 0.3.0 baseline in this pod (root or ordinary data
  ownership needed).
- `npm audit --omit=dev` for n8n and `npm audit` for the admin UI: 0. An OSV query of
  every locked Python and npm package finds only pytest 8.4.2 (dev group, not in any
  image).
- Release train (`wvt check`, manifest `b26e667`): passes with no warnings (the
  0.3.0 baseline had 13, including mcp 1.28.1 below the 1.30.0 security floor).
- `packaging/release_gate.py all` finds this record for all six products and fails
  only on the images (HTTP 404) until 0.3.4 is published.

## Release gates

1. Clean exact committed source and canonical Dockerfiles for linux/amd64; labels
   identify source revision and 0.3.4. Product dependency closure stays pinned.
2. Container acceptance of each exact image ID, followed by pinned Gitleaks
   source/full-history/all-layer/config/evidence scans, Syft SBOM/SPDX, current
   Grype database and unchanged CVE/license policy. No new blanket exceptions.
3. Registry preflight proves the 0.3.4 tag absent. Publish the accepted ID, then
   anonymous immutable pull verifies manifest/config/diffIDs and digest receipts.
4. Required PR checks (`checks`, `readiness`, Release train) pass. Readiness must see
   all six public 0.3.4 images and this decision; it fails until the images exist.
5. Merge through the protected `claude-delivery` PR flow; its push workflow creates
   six `<slug>-v0.3.4` stable Releases and Store sync follows. Do not create tags or
   releases manually or enable OpenDesign.

No image has been built for 0.3.4: this pod has no container runtime, and PR checks
do not build images (builder admission denies PR image execution by design).
