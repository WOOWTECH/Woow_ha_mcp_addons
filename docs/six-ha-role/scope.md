# Six-product HA role enablement — approved minimum slice

- Worktree: `/data/pi-agent/home/work/Woow_ha_mcp_addons-six-ha-role`
- Branch: `feat/six-ha-role-20261005`
- Exact base: `4300ae07c42c0d16b0cf6a37b98b0af2c791b8ca`
- Approval: runtime `claude-delivery/USER-DECISIONS-20261005T0820Z.md`, decision 2; the broad HA Core administrator capability and whole-HA exposure were disclosed. This is wiring reuse, not a new authorization design.
- User assigns Pi core only and Claude manifest/version/packaging sole ownership. Referenced `c509e86f` is not an object in this local repository; no fetch or alternate-context lookup was attempted. Current explicit instructions and the approval document define this slice. Parent-reported delivery `8588b97` file equivalence was not independently rechecked.

## Changes

`run_product.run()` now supplies the existing `make_ha_admin_verifier()` to `make_apps()` for odoo, odoo-manage, hermes, opendesign, emqx and litellm. The ha_role module docstring acknowledges this approved scope. No protocol, role decision, gateway, product child construction, lifecycle, dependency, or entrypoint restoration logic changes.

The verifier still uses only `ws://supervisor/core/websocket`, its own `SUPERVISOR_TOKEN`, and `config/auth/list`; no configurable URL or new authority source. Non-admin, unknown and inactive subjects are denied. Missing token and unavailable WS fail closed. Broad machine authority is not delegated to MCP clients or children.

## Approved test seams and evidence

- Execute real `run_product.run()` for all six products; real factory/verifier/gateway/store and actual unconfigured child_spec. Substitute listener, supervisor and health scheduling so no server/child is started. HTTP is MockTransport/ASGITransport; only the WS connector is replaced for role verification.
- Positive bootstrap requires actual production wiring (RED: six 403 responses before wiring; GREEN after wiring), exact auth/query frames, fixed URI, connection closure, and no HA token in response/store/log/stdout/stderr.
- All six products: fresh denial of bootstrap, reveal/rotate/revoke, backend, policy and endpoint actions after non-admin/unknown/inactive status, missing machine token, or WS outage; no state mutation/disclosure.
- Forged Ingress headers on MCP cannot authenticate; HA token is not the MCP bearer. Genuine MCP bearer dispatches unchanged using the separate child token. Direct admin peer spoofing is denied.
- Configured `products.child_spec()` runs for all six, constructing actual argv/env without inheriting `SUPERVISOR_TOKEN`. Only ROOT points to a temporary tree containing an empty Python-presence placeholder; nothing executes or installs there. Existing connection fixtures are reused.
- Existing test_ha_role protocol/schema/role/freshness/Ingress/mutation/queue assertions and parametrization are imported into the focused module with owned_provider replaced by fake WS. Original loopback/executable tests are NOT run. The obsolete “other six unchanged” assertion is updated to shared factory wiring.
- Focused module blocks socket connect/connect_ex/bind and subprocess launches as a safety net. No live HA, network listener, MCP server, VM, registry, account or reset operations.

## Reproduction

Every shell command was bounded by tool timeout; test/dependency commands also use `timeout`.

```sh
uv sync --frozen --offline --python /data/pi-agent/home/work/Woow_ha_mcp_addons-claude-delivery/.venv/bin/python --no-python-downloads
timeout 60s .venv/bin/python -m pytest -q tests/test_product_ha_role.py tests/test_ha_role.py::test_n8n_and_six_products_share_factory tests/test_product_runtime_failure.py
```

Existing CPython 3.13.2 and offline cache only; no lockfile/version changes. `logs/red.log` / `red.exit`: 6 failed / 1. `logs/green-checkpoint.log` / corresponding exit: 7 passed / 0 at 2026-10-05T09:20:53Z (first repository inspection at 09:17Z). `logs/green-focused.log`: 109 passed / 0 before the final stdout/stderr assertion addition. `logs/green-final.log` and exit file are the final full focused evidence. `source-hashes.json` records exact base/current SHA-256 and a reproducible source/test patch SHA-256. `logs/verification.log` records base/branch/index/allowlist/protected-file/diff checks.

## Out of scope / handoff gates

No addon/config.yaml, version, CHANGELOG, packaging, validate.py, dependency pins, MAIN/B4 or unrelated LiteLLM changes. No staging, commit, push, merge or subagents. The only external report is runtime `reports/worker-six-ha-role-enablement.md`.

Claude must independently change the six addon manifests to `homeassistant_api: true` and apply agreed `0.1.1` manifest/version/packaging expectations, without overwriting 0.1.0. None of those edits are made here. No real HA or child runtime, full original loopback suite, six-product dependency installs, product image builds or images have been validated in this slice. Independent SPEC and security/quality review, followed by packaging and appropriate live/image acceptance, remain required; this is not a publication/release-complete claim.
