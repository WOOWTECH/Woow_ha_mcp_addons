# n8n validator output-schema parity

Source change for the next HA MCP release. No version, OCI image, HAOS add-on,
PaaS tenant, or n8n workflow is changed by this commit.

## Measured boundary

Two existing PaaS accea n8n services (144 and 145) and an isolated exact HA
0.4.9 n8n OCI image expose the same 28 tool names and 28 input schemas when
the PaaS backend is configured. The PaaS services advertise output schemas for
`validate_node` and `validate_workflow`; the released HA gateway advertises
neither. The pinned HA n8n child itself advertises exactly those two schemas.
Both canonical hashes match the two PaaS services and the PaaS c195 exact
image's no-backend documentation mode.

The exact-image no-backend pair also measured an expected availability
difference: PaaS c195 exposes seven documentation tools, while HA 0.4.9
exposes its 28-tool fallback. The seven shared input schemas differ in this
mode. This source change does not pretend to make the no-backend catalogs
identical; it restores only two proven output contracts. Both isolated
namespaces were removed after the pair. The HA image ran outside HAOS
Supervisor, so no HA administrator-role acceptance is claimed.

Local evidence is in `PAAS-N8N-EXISTING-SCHEMAS-20261031.json`,
`HA-N8N-CHILD-OUTPUT-SCHEMAS-20261031.json`, and
`n8n-exact-image-pair-prep-20261031/runs/776060dafda4-PAIR.json` in the
parity work area. The existing-service probe made only authenticated
`tools/list` requests and verified Pod UID/image ID, deleted sessions and
unchanged configuration. The exact-image pair used a synthetic setup, deny-all
network policy, no PVC and no business backend calls.

## Controlled publication and verification

The existing exact product/tool/schema registry now contains two n8n pins
bound to `n8n-mcp==2.96.2`, TypeScript MCP SDK 1.32.2 and the reviewed HA
source files at `2a485662`. The generated fallback snapshot adds only those
two `outputSchema` values; other n8n metadata and every other product entry
are unchanged. The exact-match validator still omits any changed or
unreviewed child schema.

CI compares the real pinned n8n child, live gateway and fallback against both
pins. Python MCP 2 and TypeScript SDK 1.32.2 call both validator tools through
the gateway against a fake n8n API and validate their structured results.
The next release still requires new exact-image P1–P5 gates, publication,
anonymous readback and HAOS Supervisor acceptance. The 0.4.9 images retain
the observed omission.
