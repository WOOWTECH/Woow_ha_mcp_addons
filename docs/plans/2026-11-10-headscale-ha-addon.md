# Headscale HA Add-on Implementation Plan

**Goal:** Ship a Headscale MCP Home Assistant Add-on with the existing HA admin, gateway, release, and 29-operation native API contract.

**Architecture:** Vendor the reviewed native Headscale child and adapt only its deployment and policy seams to the HA state. Add `headscale` to the shared product registry, tool classifications, static catalog, typed connection form, and image/add-on allowlists. Preserve separate Ingress administration on 8099, bearer MCP on 8081, and child on loopback 3000.

**Tech Stack:** Python 3.13, FastMCP 4.1.3, MCP SDK 2.3.0, Pydantic 2, Home Assistant Supervisor add-on manifest, GitHub Actions, GHCR.

---

### Task 1: Pin the child and HA-specific launch boundary

**Files:** `apps/headscale/vendor/headscale_mcp_server/*.py`, `apps/headscale/launch.py`, `apps/runtime/run_child.py`, `apps/headscale/tests/*.py`.

1. Copy only the 29-operation native adapter from the reviewed Gitea source and record its commit and license.
2. Adapt its saved policy and destination guard to HA state and the HA child process. Reject unknown tools, revoked writes, and denied operations on every call; keep the parent gateway as another authorization boundary.
3. Start FastMCP on 127.0.0.1:3000/mcp with no public child port and no inherited Supervisor token.
4. Run focused tests for the native catalog, SSRF, one-time secret handling, route replacement, policy update, and denied operations.

### Task 2: Register Headscale in shared HA management

**Files:** `packages/mcp-admin-core/mcp_admin_core/{products,surface,native_inventory,tool_snapshot,configuration,gateway}.py`, `packages/mcp-admin-ui/src/contracts.js`, matching tests.

1. Add a typed `url` and `api_key` connection and destination validation, retaining existing product schemas.
2. Classify every Headscale tool and operation, with exactly 29 native operations covered by the child; add a source-backed authenticated health probe.
3. Add the child spec, GUI form, complete tool listing, and restart behavior on connection or policy changes.
4. Test fresh state grants, revocation, tool listing while backend is absent, and child environment isolation.

### Task 3: Add HA packaging and release matrix

**Files:** `addons/headscale/**`, `apps/headscale/{Dockerfile,pyproject.toml,uv.lock}`, `packaging/{validate,inputs,entrypoint,management_launcher}.py`, `.github/workflows/*`.

1. Add an amd64 Add-on with Ingress 8099 and optional LAN MCP 8081 following the existing manifest.
2. Include Headscale in strict packaging, image build, and release allowlists without implicitly releasing existing products.
3. Run offline manifest validator, image build, cold-start/upgrade, security and source/license gates as the repository requires.

### Task 4: Publish and verify

**Files:** `addons/headscale/{README,DOCS,CHANGELOG}.md`, `docs/operations/**` as required by release gates.

1. Build and push the fixed-version GHCR image through the dedicated builder; verify image digest and labels.
2. Open a PR to `claude-delivery`, wait for required checks including upgrade comparison, then merge through the protected branch.
3. Verify WOOW HA App Store synchronization and install on test HA; exercise administrator/nonadministrator, Ingress, MCP, backup/restore and a real Headscale backend.

Do not claim release or HA acceptance until the corresponding image, PR, Store, and HA receipts exist. Podman is out of scope for this plan.
