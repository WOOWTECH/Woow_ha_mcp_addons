# HA role check: reviewed Core releases

`packages/mcp-admin-core/mcp_admin_core/ha_role.py` decides whether the user behind an admin request is an HA owner or
administrator. This page records why it accepts the Core releases listed in `_HA_VERSIONS` and how a release is added.

## Who produces what

- **Auth frames.** The add-on connects to `ws://supervisor/core/websocket`. Supervisor's WebSocket proxy
  (`supervisor/api/proxy.py`, reviewed at Supervisor 2026.09.3, git blob `fc11251d`) terminates the add-on handshake:
  it sends `{"type": "auth_required", "ha_version": <version>}` and `{"type": "auth_ok", "ha_version": <version>}`,
  where the version is the Core version Supervisor has recorded (`sys_homeassistant.version`), and checks the add-on's
  `SUPERVISOR_TOKEN` itself. The verifier requires exactly these keys, a listed version, and the same version in both
  frames (the agreement only fails during an update race). Supervisor updates are frozen during tests and pinned for
  the build (Supervisor 2026.09.3); a different frame shape fails closed.
- **The consumed Core contract** (Supervisor-to-Core leg): `config/auth/list` behind `require_admin`, its per-user fields
  `id`, `is_owner`, `is_active`, `system_generated`, `group_ids`, `local_only`, the result envelope
  `{id, type: "result", success, result}`, and the admin group id `system-admin`. The verifier allows only an active,
  non-system user who is the owner or in `system-admin`.

## Review of 2026.7.2–2026.9.4 (0.1.6)

Git blob SHAs (first 8 characters) of the Core files that produce or can change that contract, from the GitHub tree of
each tag; `=` means unchanged from the previous tag. `10.0b2` is shown for information only and is not accepted.

| file (`homeassistant/`) | 7.2 | 7.3 | 7.4 | 8.0 | 8.1 | 8.2 | 8.3 | 9.0 | 9.1 | 9.2 | 9.3 | 9.4 | 10.0b2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `components/websocket_api/auth.py` | f4660664 | = | = | = | = | = | = | = | = | = | = | = | a4b73688 |
| `components/websocket_api/messages.py` | 13f856e6 | = | = | a6d3b54f | = | = | = | = | = | = | = | = | f1f543e2 |
| `components/websocket_api/decorators.py` | 37ac60ba | = | = | = | = | = | = | = | = | = | = | = | d5df7f88 |
| `components/websocket_api/connection.py` | 19d4782a | = | = | = | = | = | = | d4f824d2 | = | = | = | = | cd6e0426 |
| `components/websocket_api/http.py` | 9cfca068 | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/websocket_api/commands.py` | 5bc65849 | = | = | fe87a4e9 | = | = | = | = | = | = | = | = | 3f2b8103 |
| `components/websocket_api/__init__.py` | 3a526e32 | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/websocket_api/const.py` | f1eb480d | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/config/auth.py` | 2479fe65 | = | = | = | = | = | = | = | = | = | = | = | 75b0c88b |
| `components/config/__init__.py` | ef7a1147 | = | = | = | = | = | = | = | = | = | = | = | = |
| `auth/__init__.py` | 34a8bffa | = | = | 88a8b1d5 | = | = | = | = | = | = | = | = | a5850978 |
| `auth/auth_store.py` | 13ecdfc6 | = | = | = | = | = | = | = | = | = | = | = | = |
| `auth/const.py` | 05b9e6d7 | = | = | = | = | = | = | = | = | = | = | = | = |
| `auth/models.py` | 5646d23d | = | = | a41b03d1 | = | = | = | = | = | = | = | = | 7342e9d4 |
| `auth/permissions/__init__.py` | b5254236 | = | = | = | = | = | = | = | = | = | = | = | aeab7ff8 |
| `components/hassio/__init__.py` | b38caf53 | = | = | 3a3cd368 | = | 373c0b0c | = | 59c14de4 | = | = | = | = | 67abae35 |
| `components/http/auth.py` | e2c68719 | = | = | = | = | = | = | = | = | = | = | = | 702eb7c8 |
| `components/http/auth_util.py` | 4eed1443 | = | = | = | = | = | = | = | = | = | = | = | = |
| `helpers/json.py` | 1789bda1 | = | = | = | = | = | = | 3ea52348 | = | = | = | = | f6a778dd |
| `util/json.py` | 1f8e6a0e | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/onboarding/views.py` | a4cd0198 | = | = | = | = | = | = | 2801f426 | = | = | d3144de5 | = | 2835631c |

Changes inside 2026.7.2–2026.9.4 and why they do not touch the consumed contract (source diffs reviewed):
- `websocket_api/messages.py` @8.0: event and state-diff message caching only; the result message is unchanged.
- `websocket_api/commands.py` @8.0: a new `slugify` command.
- `auth/__init__.py` @8.0: login-flow `credential_only` removed; an invalid JWT key now returns None.
- `auth/models.py` @8.0: `credential_only` removed from the auth-flow context; the `User` model is unchanged.
- `websocket_api/connection.py` @9.0: an import change.
- `helpers/json.py` @9.0: date and time serialization.
- `hassio/__init__.py` @8.0, @8.2, @9.0: the Supervisor user id moves into the config entry; the user is still created by
  `async_create_system_user` (system-generated, `system-admin`); from 9.0 Core removes that user's refresh tokens and
  Supervisor reaches Core over its Unix socket, authenticated as the same system user by `http/auth.py` (unchanged).
- `onboarding/views.py` @9.0, @9.3: the owner is still created in `system-admin`.

## Adding a release

1. Fetch the GitHub tree of the new tag and compare the blob SHAs of the files above with the last reviewed tag.
2. For every changed file, review the diff line by line for the consumed contract (a hash comparison alone is not
   enough: 2026.10.0 moves Core's schemas from voluptuous to probatio, which changes most of these files).
3. Add the version to `_HA_VERSIONS`, to `test_the_reviewed_versions_are_exactly_these`, and a row to this table.
Any version not listed, including pre-releases, later patch releases and differently formatted strings, is refused.
