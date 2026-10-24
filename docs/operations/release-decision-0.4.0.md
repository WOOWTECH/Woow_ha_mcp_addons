# 0.4.0 release decision — 2026-10-25

Status: pending image publication. Candidate MCP SDK 2 migration and release metadata
only: no 0.4.0 image build, container/supply-chain acceptance, registry publication or
stable Release is claimed. All six exact-image gates and publication receipts remain
pending. The presence of this document is not evidence that those gates passed.

## Scope

Six Store-enabled products move to 0.4.0: Odoo, n8n, Hermes, EMQX, LiteLLM and
Nextcloud. 0.4.0 is phase 2 of the MCP SDK 2 migration (issue #21; owner decision
2026-10-24: the PaaS first, then HA). The PaaS twin did phase 1 in woow-mcp-server
#81 (Node 26.12.1) and #82 (MCP SDK 2.3.0, FastMCP 4.1.3, odoo-mcp 1.3.0). The latest
stable release is 0.3.4 (six stable Releases published 2026-10-24 18:08 UTC); this
branch is based on `40dd0a4`. OpenDesign remains disabled in the Store registry; its
source manifest shares the version but no OpenDesign image or stable Release is
requested. Existing immutable tags must never be replaced. `RELEASE-GATES.json` stays
closed.

0.4.0 contains:

1. the dependency migration below (Python children, odoo-mcp, Node 26);
2. the handling of every SDK 1 -> 2 behaviour change that would otherwise reach users
   (below), with regression tests;
3. the Hermes re-snapshot of woow-mcp-server main (server.py as of `471efdf`).

Ports, architectures, image names, manifest options, privileges, tool names and the
state schema (4) are unchanged; full-functionality defaults are unchanged. 0.3.x
installations upgrade without the legacy review page (that is only for schema
1/2/3). One breaking change is declared in [`upgrade-notes.yaml`](../../upgrade-notes.yaml)
(AGENTS.md rule 3): 13 Odoo tools return their structured result unwrapped.

## Versions

| Component | 0.3.4 | 0.4.0 |
|---|---|---|
| Python MCP SDK `mcp` (Odoo, Hermes, OpenDesign, EMQX, LiteLLM, Nextcloud) | 1.30.0 | 2.3.0, plus `mcp-types` 2.3.0 |
| FastMCP / fastmcp-slim (EMQX, LiteLLM, Nextcloud) | 3.4.11 | 4.1.3 |
| `odoo-mcp` (Odoo) | 1.1.0 | 1.3.0 (PyPI sdist sha256 `5c1fb57c…`, the release-train target) |
| SDK 2 closure (the six children) | httpx-sse 0.4.3 | httpx2 / httpcore2 2.16.0, truststore 0.10.5 (httpx2-jsfetch 1.0 is locked for emscripten only, never installed); opentelemetry-api 1.45.1 now also in Odoo, Hermes, OpenDesign; pydantic-settings and python-dotenv leave those three locks |
| Backend HTTP clients of the children | HTTPX 0.28.1 / httpcore 1.0.9 | unchanged (the backend policy guards stay valid) |
| Odoo Manage (archived, not built) | mcp 1.30.0 / mcp-server-odoo 0.7.1 | unchanged, own lock |
| `n8n-mcp` / MCP TypeScript SDK override | 2.96.2 / 1.32.2 | unchanged (28 tools, guards and build patch unchanged) |
| Node base image | `node:22.23.4-bookworm-slim@sha256:de170b39…` | `node:26.12.1-bookworm-slim@sha256:28147155…` (multi-arch index; linux/amd64 child `1884ec27…`) |
| CI Node (`setup-node`) | 22.23.4 | 26.12.1 |
| Core gateway pins | — | unchanged (`uv.lock` untouched) |

Each child lock was regenerated with `uv lock` (uv 0.12.10) inside the new pins only:
no other package moved. Every changed Python package declares MIT, BSD-3-Clause or
Apache-2.0 (the policy's allowed list). An OSV query of all 93 locked Python packages
finds only pytest 8.4.2 (dev group, not in any image); `npm audit` is 0 for the n8n
child and the admin UI.

## SDK 1 -> 2 behaviour changes and their handling

| Change (assessment `mcp-v2-assessment-20261024`) | Handling in 0.4.0 | Evidence |
|---|---|---|
| `FastMCP` is `MCPServer`; transport settings move from `mcp.settings` to `run()`; `_mcp_server` is `_lowlevel_server` | Hermes/OpenDesign launchers pass host, port and path to `run()`; vendored OpenDesign imports `MCPServer`; Hermes re-snapshot; `BoundedTools` imports `mcp.server.mcpserver` lazily (Odoo Manage stays on 1.x) | every real-child test |
| A tool's exception text is hidden unless it is a `ToolError` (`Error executing tool <name>` only) | `apps/runtime/tool_error_text.keep_error_text` (port of the PaaS function) wraps every tool of Odoo, Hermes and OpenDesign, after `BoundedTools` | `tests/test_tool_error_text.py`: unit premise + real children answer exactly the 0.3.4 texts (measured with the 0.3.4 tree); `test_raw_backend_errors.py`, `test_six_hardening.py` (`BACKEND_BUSY`) |
| Sync tools run on parallel anyio worker threads | Odoo: `BoundedTools(capacity=1)` keeps every tool, writes included, on one owned worker. HA has no `ODOO_MCP_READ_THREADS` and no code reads `ToolAnnotations` attributes (the gateway reads the wire JSON, whose camelCase hints are unchanged) | `test_six_hardening.py::test_odoo_writes_stay_serialized_under_mcp_sdk2` (fails without `BoundedTools`: 8 concurrent writes reach Odoo together) |
| Request body limit 4 MiB; idle sessions end after the SDK's explicit 1800 s | `apps/runtime/session_idle.py` (0.3.4) still replaces both explicit defaults (`MCPServer` passes them; FastMCP 4 passes neither); reviewed against 2.3.0 | `test_session_idle.py`: both flavours, invalid values, six real children end idle sessions and accept a body just under 16 MiB |
| FastMCP 4 cancels a running async tool when its session is deleted | The Nextcloud readiness probe runs under `anyio.CancelScope(shield=True)` | `test_nextcloud_child.py::test_slow_401_still_latches_after_health_check_timeouts`: 5 failed logins without the shield, at most 2 with it |
| A request whose `MCP-Protocol-Version` header is not a handshake revision goes to the 2026-07-28 handling, which refuses an initialize (HTTP 400; mcp 1.x ignored the header there) | The gateway no longer forwards that header with an initialize. It still answers `server/discover` itself (-32601, 0.1.13) and strips `params._meta`, so no 2026-07-28 request succeeds through it | `tests/test_protocol_clients.py` (fails without the gateway change) |
| `mcp.shared.version` removed | Gateway guard follows `mcp_types/version.py`: `HANDSHAKE_PROTOCOL_VERSIONS` = `PROTOCOL_VERSIONS`, `LATEST_HANDSHAKE_VERSION` 2025-11-25 is the answer to other revisions | `test_initialize_identity.py` |
| FastMCP 4 update check uses httpx2 | `FASTMCP_CHECK_FOR_UPDATES=off` unchanged; the drift test now also forbids `httpx2.get` | `test_expansion_drift.py` |
| `initialize`: `serverInfo.version` empty for `MCPServer`, `capabilities.experimental` and the UI extension gone | none needed: the gateway answers initialize with its own result | surface probe below |
| OpenTelemetry API is a required dependency | API only, no SDK or exporter: no spans or network | review |

Client compatibility through the real gateway (`tests/test_protocol_clients.py`, Odoo and
EMQX children): raw JSON-RPC at 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 (each
echoed); the Python MCP SDK 1.30.0 client; the TypeScript SDK 1.32.2 client (n8n-mcp's
pinned copy); the Python MCP SDK 2.3.0 client in its default `auto` mode, which falls
back from `server/discover` to initialize. All land on 2025-11-25 and list and call.

## Odoo (odoo-mcp 1.1.0 -> 1.3.0)

Both PaaS build patches apply to 1.3.0 at their anchors (patched `tools_write.py`
`50ac5cfa…`, `server_core.py` `4866870f…`); the cross-session token store is redundant
under SDK 2 (one lifespan per process) and harmless. Reviewed 1.1.0 -> 1.3.0 diffs of the
seven guarded files (`docs/provenance/runtime-patches.json`, `apps/odoo/launch.py` and
`odoo_read_exists.py` entries): the XML-RPC transport replacement, `read_record`'s
contract and `_resolve_odoo` are unchanged; `execute_approved_write` confirms through
`Resolve(...)` and still approves without asking unless `ODOO_MCP_ELICIT_WRITES` is
set; `<field>_from_path` uploads read a local file only from
`ODOO_MCP_ATTACHMENT_UPLOAD_ROOTS`; OAuth starts only with `ODOO_MCP_AUTH_*`. The child
environment sets none of these (`tests/test_product_boundary.py::test_odoo_mcp_1_3_opt_ins_stay_off`).
Only `execute_approved_write` is async, as in 1.1.0.

Tool-surface diff (real children, raw `tools/list`, 0.3.4 vs 0.4.0): no tool added,
removed or renamed in any product; annotations and descriptions unchanged; Odoo: 57
parameters of 10 tools gain a description (types and required fields unchanged), and 13
tools declare typed `outputSchema`s instead of `{"result": …}`, so their
`structuredContent` is the result object itself (the text content is the same JSON;
`upgrade-notes.yaml`). The gateway never lists `outputSchema`. Nextcloud's private probe
gains a derived title (never listed). `docs/tool-surface.json` changes only source
digests, line numbers and 11 Odoo source signatures; effects and statuses are unchanged
(the drift baselines hold); `tool_snapshot.py` changes only those 10 Odoo tools.

## Source guard re-review

`docs/provenance/runtime-patches.json` lists 30 guarded sources that the new files
invalidate, each re-reviewed against the new file (not re-pinned mechanically): 4 SDK
tool-dispatch files of `BoundedTools` (moved to `mcp/server/mcpserver`), 6
`streamable_http_manager.py` of `session_idle`, 2 Odoo sources of `odoo_read_exists`, 6
odoo-mcp files of the Odoo launcher (`diagnostics.py` unchanged), 6 FastMCP
`settings.py`/`utilities/version_check.py` of `products.py` and 6 `mcp_types/version.py`
of the gateway (moved from `mcp/shared/version.py`); the new `tool_error_text.py` guards
`tools/base.py` in its three venvs. The 49 HTTPX/httpcore guards of `backend_policy`, the
n8n guards and Odoo Manage's 5 guards are unchanged. The re-review notes name what was
read; `tests/test_tool_inventory.py` checks every digest.

## Hermes

The vendored files are re-snapshotted from woow-mcp-server main `83d6de5` (server.py and
guards.py last changed upstream in `471efdf`; server.py upstream sha256 `6b8abf82…`, the
release-train target): `MCPServer`, `_lowlevel_server` and `keep_error_text`, imported
from `apps/runtime/tool_error_text.py` because the child cannot import `mcp_admin_core`.
The HA changes listed in `docs/provenance/runtime-sources.json` are kept, including the
0.3.4 loopback refusal (AI-HMCP-002-2) and the LAN allowance.

## Node 26

`node:26.12.1-bookworm-slim` (anonymous Docker Hub GET of the multi-arch index): its
`/usr/local/bin/node` is byte-identical to the official v26.12.1 tarball, and it installs
Debian bookworm libatomic1 12.2.0-14+deb12u1 (source gcc-12, the version of the Python
base's libgcc-s1 and libstdc++6), which Node 26's official binary links. Only the n8n image
copies node into the Python base: it copies `libatomic.so.1` next to libstdc++/libgcc_s
(no package installation in images, `packaging/test_supply_chain.py`) and checks
`node --version` = v26.12.1 right after. The UI stages run in the node image. The n8n
child keeps the sql.js fallback (`npm ci --ignore-scripts`: no native better-sqlite3,
`tests/test_boundary.py`, which also asserts that the child runs Node 26.12.1); the PaaS better-sqlite3 override
does not apply. CI: pytest runs under `sudo`, whose secure PATH found the hosted runner's own `/usr/local/bin/node`
before the pinned `/usr/bin/node`, so the n8n child in CI could run on the runner's own Node (22.23.3 in the first
0.4.0 run, caught by that assertion); the workflows now pin `/usr/local/bin/node` to the setup-node binary as well
and check `sudo -n -- node --version`.

## Local evidence (this pod; not image or HA acceptance)

CPython 3.13.15, uv 0.12.10, Node 26.12.1 (official tarball; this pod lacks libatomic1,
so the local copy loads the node image's `libatomic.so.1`), no root and no container
runtime. Results are in the PR description.

## Release gates

1. Clean exact committed source and canonical Dockerfiles for linux/amd64; labels
   identify source revision and 0.4.0. Product dependency closure stays pinned.
2. Container acceptance of each exact image ID, followed by pinned Gitleaks
   source/full-history/all-layer/config/evidence scans, Syft SBOM/SPDX, current
   Grype database and unchanged CVE/license policy. No new blanket exceptions.
3. Registry preflight proves the 0.4.0 tag absent. Publish the accepted ID, then
   anonymous immutable pull verifies manifest/config/diffIDs and digest receipts.
4. Required PR checks (`checks`, `readiness`, Release train) pass. Readiness must see
   all six public 0.4.0 images and this decision; it fails until the images exist.
5. Merge through the protected `claude-delivery` PR flow; its push workflow creates
   six `<slug>-v0.4.0` stable Releases and Store sync follows. Do not create tags or
   releases manually or enable OpenDesign.
6. Real HAOS acceptance on the dedicated test HAOS (ws97), coordinated separately: install
   and upgrade from 0.3.4, MCP clients, Odoo writes, Nextcloud upload and backup/restore.

No image has been built for 0.4.0: this pod has no container runtime, and PR checks
do not build images (builder admission denies PR image execution by design).
