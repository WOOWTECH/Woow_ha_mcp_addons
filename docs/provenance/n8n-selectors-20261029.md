# n8n operation selectors — next release after 0.4.4

## Scope and source

Main coordinator supplied PR35 `d730837a41c988398032677bb5adfff58d3e13ee` as the exact base. This independent source branch stacks on `fix/n8n-error-contract-next-20261029`; it must not merge into the 0.4.4 release. No version, integration branch, native handler, image, registry or production change.

The omission was confirmed in HA `surface.py`: these tools existed but lacked selector metadata, so `/api/policy` could not accept their known operation denies and the dynamic UI could not offer them. No new native operations are introduced.

| Tool | Selector | Known operations | Existing grant |
| --- | --- | --- | --- |
| n8n_manage_agents | action | reference, search, get, create, mutate, validate, call, publish, unpublish, revert, versions, delete, discover_assets, verify_mcp_server, update_integration | whole tool |
| n8n_test_workflow | method | auto, trigger, prepare, pinned, direct | whole tool |
| n8n_list_catalog | kind | projects, tags | none |

All products retain the exact PR35 grant sets (n8n: 33); whole-tool disable and the existing updater grant for `exposeToMcp` still take precedence. Operation effects are separate from grants: agents' read labels follow the pinned action map, including verify_mcp_server; test prepare reads unless exposure is requested. Read labels do not promise absence of remote probes/cache/auth activity.

Missing test method and ECMAScript whitespace-only strings preserve the native `auto` default. Native public inputSchema omits a default, but TOOL_OPERATION_DEFAULT and the actual handler both implement auto. Null, wrong types, unknown values and missing required action/kind fail closed before child dispatch, even without an active deny. Output wrapper normalization runs first. Denying trigger also blocks auto/default, matching the pinned handler guard. `expose` is not a method enum and cannot be added through the API; its existing updater dependency remains intact.

Bootstrap and capabilities publish these selectors/effects/defaults through the existing dynamic UI contracts. No UI production code change is needed. The catalog reports auto policy-disabled when trigger is denied.

## Bounded verification

- Focused pytest: selector tests plus existing operation denies, exposure, full surface, PR35 result contract and inventory/provenance tests; 249 passed in 27.04 seconds.
- Existing UI operation contract tests: 4 passed.
- New native probe executes the entire pinned tools/call callback for all 22 known values, each denied (zero fake dispatches) and allowed (one fake dispatch). It executes the whole native test handler with real Zod and native policy, reaching its trigger deny guard for auto, trigger, omitted and whitespace method. No n8n server/database initialization; execution collaborators are fake and network calls are forbidden.
- Real HA ASGI gateway + MockTransport: every known value, denied output wrappers, invalid selectors with and without restrictions, required/default selectors, grant revocation and tool disable; denied calls leave mock-child count unchanged.
- Actual bootstrap -> production JS toolRows/operationPolicy/policyPayload -> real policy API round trip; unknown virtual method refused.
- Generated inventory matches source; all product grant sets and all pinned native source digests equal PR35. Existing result/error and test-run handler patches are preserved.

Re-run from repository root with existing dependencies (no install/build):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/mcp-admin-core:apps/n8n .venv/bin/python -B -m pytest -q tests/test_n8n_selectors.py tests/test_operation_denies.py tests/test_n8n_exposure_policy.py tests/test_full_surface.py tests/test_n8n_tool_result_is_error.py tests/test_tool_inventory.py
node --test packages/mcp-admin-ui/tests/operations.test.mjs
git diff --check
```

These are source/offline tests with fake backend collaborators, not live n8n or customer acceptance. No new full browser or image tests. CI is not yet verified. Workflow inspection: PR checks/readiness/WVT do not build images; image jobs run only main/dispatch and publishing is gated separately. No skip directive is required for this source PR. Local Node is v22.23.3, not the CI-pinned v26.12.1.

## Pinned source SHA-256

- `apps/n8n/node_modules/n8n-mcp/dist/mcp/server.js`: `638b148f91c18d484b8bcede838be1032f82ddd1b3aa53b24cf005325ae3d9f7`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/tools-n8n-manager.js`: `28d54ea6a3001678fd510542c82c04c26b2ff3b55b7db63b630800e82e02191f`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/agents-action-map.js`: `9282db04957b8a7931cd99ceddcbfd943419732930325256b03ecc443075c8e8`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/handlers-agents.js`: `80e65ea7c8db18638b9c831c2f5d74012412d57839a92ab18d7a9c735062f4ac`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/handlers-official-tools.js`: `e85937c58d5a8426d54b1b69598adc83a14648402fc58a8714ef5db8132977cd`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/handlers-n8n-manager.js`: `6cd673423e829902f3e56de66afe90f7e2196d7ef76cca02551a20eee03ae2eb`
- `apps/n8n/node_modules/n8n-mcp/dist/mcp/tool-policy.js`: `e3ec9753d7b64320d83829015905c32a1b03620a4b82f0e39d5fcbb142a75ec5`
