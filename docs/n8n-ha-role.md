# n8n HA administrator-role gate

## Status and authority

**Current state (0.1.6).** The broad Core-administrator capability exception was first approved for the n8n pilot only (2026-10-03 upstream decision; n8n ships it since 0.1.0); since 2026-10-05 the owner has approved it for all six store products (odoo, hermes, opendesign, emqx and litellm from 0.1.1). All six use the same verifier, `make_ha_admin_verifier()` in `ha_role.py`: n8n wires it in `apps/n8n/run.py`, the other five in `mcp_admin_core/run_product.py` (`tests/test_ha_role.py` asserts the shared factory). The reviewed Core list `_HA_VERSIONS` below therefore applies to all six management panels. The local integration (n8n only at the time) passed a bounded specification/security review on 2026-10-03; in 0.1.1 the provider wiring and the token hand-off passed an independent specification and security review that did not cover images, HA or publication. Every release 0.1.1–0.1.5 was regressed on the test HA (Core 2026.7.2): owner allowed, non-administrator 403. Post-login demotion and the browser UI were verified only locally; local protocol/executable tests are not HA acceptance.

All six manifests enable the approved `homeassistant_api: true`; no sibling permission was added. Keep `hassio_api: false`, `auth_api: false`, default Supervisor role and protection mode, with no new host mounts/capabilities. The archived Odoo Manage (last release 0.1.4) used the same verifier; it is no longer built or published.

**The token is not read-only.** The Supervisor Core proxy authenticates as a privileged Core system user. A stolen machine token can exercise broad Core administrator APIs, including potential indirect Supervisor/host service effects. Restricting this implementation to a single query does not reduce that credential's underlying authority.

## Implemented protocol

`packages/mcp-admin-core/mcp_admin_core/ha_role.py` uses the maintained `websockets` asyncio client, pinned to `15.0.1` in the root project and hashed `uv.lock` (Python 3.13).

Every final decision creates a new connection to exactly:

```text
ws://supervisor/core/websocket
S: {"type":"auth_required","ha_version":"2026.7.2"}
C: {"type":"auth","access_token":"<own runtime SUPERVISOR_TOKEN>"}
S: {"type":"auth_ok","ha_version":"2026.7.2"}
C: {"id":1,"type":"config/auth/list"}
S: {"id":1,"type":"result","success":true,"result":[<current users>]}
```

The socket is then terminated and joined; it is never pooled or reused. This is **not** a generic WS proxy, `auth/current_user`, HTTP role lookup or a browser-token flow. There is no production URL, command, machine-token or transport override in CLI/GUI. The private Python connector seam is used only by owned-loopback tests; those tests preserve/assert the fixed URI, path and Host while replacing the network transport.

Compatibility is deliberately restricted to source-reviewed Core releases: `2026.7.2` until 0.1.5, and from 0.1.6 the list `2026.7.2`–`2026.9.4` plus `2026.10.0` in `ha_role._HA_VERSIONS`. The auth frames come from Supervisor's WebSocket proxy, which advertises the Core version it has recorded; the consumed Core contract (`config/auth/list` behind `require_admin`, its user fields, the result envelope and the `system-admin` group) is unchanged across the list (review and procedure: [ha-role-core-contract.md](ha-role-core-contract.md)). `auth_required` and `auth_ok` must advertise the same listed version; any other version denies until reviewed. Source research also targets Supervisor `2026.09.3`. There is no separate online Supervisor-version discovery request. Source bases:

- Core `f9122fb28dd30d3833b3b313924befbc82157f97`, `homeassistant/components/config/auth.py` (`config/auth/list`, role fields), `homeassistant/auth/models.py`, `homeassistant/auth/const.py`.
- Supervisor `64ea3be4322537fd5dcfbf620c4dc25490c1f56d`, `supervisor/api/proxy.py` (machine-token/HA-API-flag authentication), `supervisor/api/ingress.py` (forwarded identity).

## Decision and action timing

- Only actual socket peer `172.30.32.2` can select management identity; Uvicorn keeps `proxy_headers=False`. Exactly one 1–256-character nonempty printable-ASCII `X-Remote-User-Id` is required. Commas, whitespace, controls, duplicate and combined values deny. Forwarding, role/name headers, JSON and query parameters cannot select another subject.
- Existing Ingress path/CSRF protections remain. The gateway completes bounded body parsing, acquires a bounded mutation lock and validates the complete proposed state **before** the final role query. There is no early positive role grant to reuse after a slow body or queue wait.
- Every HTML page, static asset/license, bootstrap read, token reveal/rotate/revoke, backend credential update, policy update and endpoint update requires a fresh final decision. After that decision there is no awaited work before disclosure/state commit. Queued requests cannot inherit a predecessor's decision.
- Response JSON rejects duplicate keys, nonfinite constants, nonobjects, binary frames, wrong sequencing/type/ID, nonboolean success and malformed result lists. The result envelope has an exact key set; command ID must be integer `1`, never boolean.
- Every user's consumed role fields have strict types. All IDs must be valid and unique across the directory, including unrelated users. Exactly one record must match the trusted subject. Unused Core personal/credential-provider metadata is not interpreted or exposed; `local_only`, when present, must be boolean.
- Allow only `is_active is True AND system_generated is False AND (is_owner is True OR "system-admin" in group_ids)`. Missing/deleted, inactive owner/admin, system user and nonadministrator deny.
- Machine-token absence/revocation, disabled capability flag, protocol incompatibility, outages and exceptions deny. Fresh handshakes recheck machine capability rather than retaining an already authorized socket. No positive or stale-if-error role cache exists.

## Resource and confidentiality limits

The provider permits eight simultaneous queries with immediate saturation denial and **no waiting queue**. Connect/auth/query budget is 2.25 seconds; transport-abort/join cleanup has a 0.2-second budget, below the gateway's 3-second guard. WS message size is at most 1 MiB and receive high-water queue is one frame. Compression is disabled rather than accepting decompression expansion; unsolicited extensions fail negotiation. Redirects and environment proxies are disabled. Large directories intentionally fail closed.

The gateway admits at most sixteen management requests (including body readers and lock waiters), then denies saturation. Bodies have the existing 256 KiB/10-second bound; lock acquisition is bounded at two seconds. The disconnect watcher owns receive only after body consumption, marks observed disconnects before commit and cancels/joins pending role work. Direct task cancellation also joins cleanup; no verifier reader/cleanup task is detached.

The machine token is read only from the management process's own runtime environment at each query. It is never stored in GUI state, sent to the browser/client/backend, copied into subprocess argv/environment or logged. Existing n8n child launch uses an explicit environment allowlist excluding `SUPERVISOR_TOKEN`; tests assert this. Client and child Bearer tokens and backend API keys remain separate. The WS client receives a private disabled logger because library debug logs otherwise expose frames. Exceptions are reduced to boolean denial/generic gateway errors; raw exceptions and user directories are not logged or returned.

The packaged final exec enters `management_launcher.py` before app/core imports. It verifies
no_new_privs, dumpable=0 and zero core limits, then uses runpy (no second exec).
`tests/integration_local_runtime.py` runs real bootstrap→guard→n8n→this factory/protocol with
an owned fake WS transport and test-only Ingress peer simulation. The real Node child checks
parent environ/mem denial; browser wire/state/argv/log/child isolation is checked with a dummy
machine token. This is local Linux evidence, not image, HA AppArmor or production acceptance.
The explicit root-only integration test is outside default collection; instructions are in the UI README.

## Limits that this does not solve

A role lookup and an Add-on commit are not a distributed transaction. Demotion concurrent with an already authorized in-flight operation can race; already committed backend changes may continue their child restart. There is no promise of atomic, zero-time revocation across HA and the Add-on.

**HA logout is not identical to role revocation.** Ingress forwards a user ID, not the browser's originating refresh-token/session ID. An independently valid Ingress cookie may outlive revocation/logout of one browser token while the user remains active/admin. This verifier cannot detect that event and does not claim immediate browser-session logout invalidation. Session-bound enforcement would require separately approved architecture.

Plain internal WS, the Supervisor/Ingress trust boundary, upstream HA logging and same-security-domain process compromise remain deployment risks. Suppressing this client's logs is not a claim about all HA logs. Live administrator/nonadministrator Ingress has been tested on the test HA (0.1.1–0.1.5, Core 2026.7.2 only); live demotion/disable/deletion, machine-capability revocation and client acceptance still require an explicitly approved disposable HA pilot.

## Local verification

`tests/test_ha_role.py` exercises actual WebSocket framing against an owned loopback server with dummy credentials, not a successful boolean callback standing in for the provider. It includes a real `run.main()` subprocess/TCP listener/real n8n child test, with test-only simulated ingress peer and WS network transport. Other cases cover schema/identity failures, fresh connections, body/queue demotion, all sensitive operations denied without state change or secret disclosure, timeout/concurrency/cancellation/disconnect cleanup, no credential crossover and the six-executable boundary.

Run with the machine token removed from the test environment:

```sh
env -u SUPERVISOR_TOKEN uv sync --frozen
env -u SUPERVISOR_TOKEN .venv/bin/python -m pytest -q
```
