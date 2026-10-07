# HA role check: reviewed Core releases

`packages/mcp-admin-core/mcp_admin_core/ha_role.py` decides whether the user behind an admin request is an HA owner or
administrator. This page records why it accepts the Core releases listed in `_HA_VERSIONS` and how a release is added.

## Who produces what

- **Auth frames.** The add-on connects to `ws://supervisor/core/websocket`. Supervisor's WebSocket proxy
  (`supervisor/api/proxy.py`, reviewed at Supervisor 2026.09.3, git blob `fc11251d`; Supervisor 2026.10.0 ships the same
  blob) terminates the add-on handshake:
  it sends `{"type": "auth_required", "ha_version": <version>}` and `{"type": "auth_ok", "ha_version": <version>}`,
  where the version is the Core version Supervisor has recorded (`sys_homeassistant.version`), and checks the add-on's
  `SUPERVISOR_TOKEN` itself. The verifier requires exactly these keys, a listed version, and the same version in both
  frames (the agreement only fails during an update race). Supervisor updates are frozen during tests and pinned for
  the build (Supervisor 2026.09.3); a different frame shape fails closed.
- **The consumed Core contract** (Supervisor-to-Core leg): `config/auth/list` behind `require_admin`, its per-user fields
  `id`, `is_owner`, `is_active`, `system_generated`, `group_ids`, `local_only`, the result envelope
  `{id, type: "result", success, result}`, and the admin group id `system-admin`. The verifier allows only an active,
  non-system user who is the owner or in `system-admin`.

## Review of 2026.7.2–2026.9.4 and 2026.10.0 (0.1.6)

Git blob SHAs (first 8 characters) of the Core files that produce or can change that contract, from the GitHub tree of
each tag; `=` means unchanged from the previous tag. The `10.0` column is the 2026.10.0 tag (commit `6a811d33`), whose files
are byte-identical to 2026.10.0b4, where the line-by-line review was done.

| file (`homeassistant/`) | 7.2 | 7.3 | 7.4 | 8.0 | 8.1 | 8.2 | 8.3 | 9.0 | 9.1 | 9.2 | 9.3 | 9.4 | 10.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `components/websocket_api/auth.py` | f4660664 | = | = | = | = | = | = | = | = | = | = | = | a4b73688 |
| `components/websocket_api/messages.py` | 13f856e6 | = | = | a6d3b54f | = | = | = | = | = | = | = | = | f1f543e2 |
| `components/websocket_api/decorators.py` | 37ac60ba | = | = | = | = | = | = | = | = | = | = | = | d5df7f88 |
| `components/websocket_api/connection.py` | 19d4782a | = | = | = | = | = | = | d4f824d2 | = | = | = | = | cd6e0426 |
| `components/websocket_api/http.py` | 9cfca068 | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/websocket_api/commands.py` | 5bc65849 | = | = | fe87a4e9 | = | = | = | = | = | = | = | = | d769c753 |
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

Changes in 2026.10.0 (13 files, every hunk read at 2026.10.0b4; the 2026.10.0 tag is identical to b4 for these 21 files
and for the adjacent `http/const.py`, `http/__init__.py`, `hassio/const.py` and `hassio/auth.py`):
- Most hunks move schemas from voluptuous to probatio (`config/auth.py`, `websocket_api/{decorators,messages,connection,
  auth,commands}.py`, `auth/permissions/__init__.py`, `onboarding/views.py`). `config/auth/list` has a one-key schema,
  so it still dispatches through `connection.async_handle`'s hand-written checks with `_ws_schema = False`; neither the
  request nor the response passes through probatio. A probatio difference could only produce an error envelope, which the
  verifier denies (`success is not True`).
- `config/auth.py`: `websocket_list` (`@require_admin`, `async_get_users`, `result_message`) and `_user_info` (`id`,
  `is_owner`, `is_active`, `local_only`, `system_generated`, `group_ids`, …) are unchanged; `config/auth/delete` now
  refuses system-generated users and the owner.
- `websocket_api/decorators.py`: `require_admin` is unchanged; `ws_require_user(only_supervisor=True)` now compares the
  Supervisor user's id instead of its name.
- `websocket_api/messages.py`, `helpers/json.py`: `result_message` and `json_bytes` are unchanged (new cached helpers only).
- `auth/__init__.py`, `auth/models.py`: the owner cannot be removed; login-flow PKCE fields. `User.is_admin` (owner, or
  active and in `system-admin`) and `async_create_system_user` are unchanged.
- `hassio/__init__.py`, `http/auth.py`, `http/const.py`, `http/__init__.py`, `hassio/const.py`, `hassio/auth.py`: the
  Supervisor user is kept under `DATA_SUPERVISOR_USER` (same `"hassio_supervisor_user"` key string) and looked up by id
  on every Unix-socket request; it is still a system-generated, active `system-admin` user, so `require_admin` passes.
- `onboarding/views.py`: the owner is still created in `system-admin`.
- Unrelated to the contract but new in 2026.10: `subscribe_condition` no longer requires admin, and users may rename
  themselves (`person/update_own_profile`); the verifier reads ids and roles, never names.

## Adding a release

1. Fetch the GitHub tree of the new tag and compare the blob SHAs of the files above with the last reviewed tag.
2. For every changed file, review the diff line by line for the consumed contract (a hash comparison alone is not
   enough: 2026.10.0 moves Core's schemas from voluptuous to probatio, which changes most of these files).
3. Add the version to `_HA_VERSIONS` and add a column for it to the table above (files are rows, versions are columns);
   note under the table what changed, and update the heading of that review section.
4. In the same change, update every other place that spells out the reviewed versions:
   - the comment above `_HA_VERSIONS` in `ha_role.py`;
   - `tests/test_ha_role.py`: add the version to `test_the_reviewed_versions_are_exactly_these` and remove it from
     `NEAR_MISSES` (the list holds, for example, `2026.10.1`; the near-miss tests fail until it is removed);
   - the version-list sentence in [n8n-ha-role.md](n8n-ha-role.md) ("Compatibility is deliberately restricted to …");
   - the new release's section of all six `addons/*/CHANGELOG.md`, naming the added version;
   - the supported-version note in the six `addons/*/DOCS.md`, `README.md` and `docs/operations/guide.md`.
5. Ship it in a new add-on release: an installed add-on accepts only the versions listed in its own image.

Any version not listed, including pre-releases, later patch releases and differently formatted strings, is refused.
