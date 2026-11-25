# HA role check: reviewed Core releases

`packages/mcp-admin-core/mcp_admin_core/ha_role.py` decides whether the user behind an admin request is an HA owner or
administrator. This page records why it accepts the Core releases listed in `_HA_VERSIONS`, which later patch releases of those months it
accepts without a review of their own (since 2026-11-25, see "Later patch releases of a reviewed month") and how a release is
added.

## Who produces what

- **Auth frames.** The add-on connects to `ws://supervisor/core/websocket`. Supervisor's WebSocket proxy
  (`supervisor/api/proxy.py`, reviewed at Supervisor 2026.09.3, git blob `fc11251d`; Supervisor 2026.10.0 ships the same
  blob; Supervisor 2026.10.1 ships blob `002174e5`, reviewed 2026-10-08: the `auth_required`/`auth_ok` frames are unchanged and
  its new message filtering does not touch the add-on's `config/auth/list` request; Supervisor 2026.10.2, 2026.10.3 and
  2026.10.4 ship blob `cab849dc`, reviewed 2026-10-27: its only hunk starts the two proxy loops with
  `sys_create_background_task` instead of `sys_create_task`, the frames and the filter are unchanged) terminates the add-on handshake:
  it sends `{"type": "auth_required", "ha_version": <version>}` and `{"type": "auth_ok", "ha_version": <version>}`,
  where the version is the Core version Supervisor has recorded (`sys_homeassistant.version`), and checks the add-on's
  `SUPERVISOR_TOKEN` itself. The verifier requires exactly these keys, a listed version (or a later patch release of a
  listed month, see below), and the same version in both frames (the agreement only fails during an update race). Supervisor updates are frozen during tests and pinned for
  the build (Supervisor 2026.09.3); a different frame shape fails closed.
- **The consumed Core contract** (Supervisor-to-Core leg): `config/auth/list` behind `require_admin`, its per-user fields
  `id`, `is_owner`, `is_active`, `system_generated`, `group_ids`, `local_only`, the result envelope
  `{id, type: "result", success, result}`, and the admin group id `system-admin`. The verifier allows only an active,
  non-system user who is the owner or in `system-admin`.

## Review of 2026.7.2–2026.9.4, 2026.10.0 (0.1.6), 2026.10.1 (0.1.9), 2026.10.2–2026.10.4 (0.4.2), 2026.11.0–2026.11.1 (Headscale 0.4.14), 2026.11.2 (Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud 0.4.14; Headscale 0.4.19), and 2026.11.3 (maintenance release of 2026-11-25: Odoo 0.5.2, EMQX, LiteLLM and Nextcloud 0.5.1, n8n and Hermes 0.4.15, Headscale 0.4.20)

Git blob SHAs (first 8 characters) of the Core files that produce or can change that contract, from the GitHub tree of
each tag; `=` means unchanged from the previous tag. The `10.1` column is the 2026.10.1 tag (commit `abe1fdd7`). The `10.0` column is the 2026.10.0 tag (commit `6a811d33`), whose files
are byte-identical to 2026.10.0b4, where the line-by-line review was done. The `10.2`, `10.3` and `10.4` columns are the
2026.10.2 (commit `8d7fd8b6`), 2026.10.3 (commit `1f214b84`) and 2026.10.4 (commit `357cae5c`) tags. The `11.2` column is
the 2026.11.2 tag (commit `ff5d56b8`). The `11.3` column is the 2026.11.3 tag (commit `92da9f15`).

| file (`homeassistant/`) | 7.2 | 7.3 | 7.4 | 8.0 | 8.1 | 8.2 | 8.3 | 9.0 | 9.1 | 9.2 | 9.3 | 9.4 | 10.0 | 10.1 | 10.2 | 10.3 | 10.4 | 11.0 | 11.1 | 11.2 | 11.3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `components/websocket_api/auth.py` | f4660664 | = | = | = | = | = | = | = | = | = | = | = | a4b73688 | = | = | = | = | 244484bf | = | = | = |
| `components/websocket_api/messages.py` | 13f856e6 | = | = | a6d3b54f | = | = | = | = | = | = | = | = | f1f543e2 | = | = | = | = | = | = | = | = |
| `components/websocket_api/decorators.py` | 37ac60ba | = | = | = | = | = | = | = | = | = | = | = | d5df7f88 | = | = | = | = | = | = | = | = |
| `components/websocket_api/connection.py` | 19d4782a | = | = | = | = | = | = | d4f824d2 | = | = | = | = | cd6e0426 | = | = | = | = | e031b7c4 | = | = | = |
| `components/websocket_api/http.py` | 9cfca068 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | da44d879 | = | = | = |
| `components/websocket_api/commands.py` | 5bc65849 | = | = | fe87a4e9 | = | = | = | = | = | = | = | = | d769c753 | = | = | = | = | 03297e08 | = | = | = |
| `components/websocket_api/__init__.py` | 3a526e32 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | a00ab2af | = | = | = |
| `components/websocket_api/const.py` | f1eb480d | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/config/auth.py` | 2479fe65 | = | = | = | = | = | = | = | = | = | = | = | 75b0c88b | = | = | = | = | = | = | = | = |
| `components/config/__init__.py` | ef7a1147 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | 784ba83b | = | = | = |
| `auth/__init__.py` | 34a8bffa | = | = | 88a8b1d5 | = | = | = | = | = | = | = | = | a5850978 | = | 0314c4b7 | = | = | 851a64b7 | = | = | = |
| `auth/auth_store.py` | 13ecdfc6 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = |
| `auth/const.py` | 05b9e6d7 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = |
| `auth/models.py` | 5646d23d | = | = | a41b03d1 | = | = | = | = | = | = | = | = | 7342e9d4 | = | = | = | = | = | = | = | = |
| `auth/permissions/__init__.py` | b5254236 | = | = | = | = | = | = | = | = | = | = | = | aeab7ff8 | = | = | = | = | = | = | = | = |
| `components/hassio/__init__.py` | b38caf53 | = | = | 3a3cd368 | = | 373c0b0c | = | 59c14de4 | = | = | = | = | 67abae35 | = | = | = | = | a35b70ef | = | = | = |
| `components/http/auth.py` | e2c68719 | = | = | = | = | = | = | = | = | = | = | = | 702eb7c8 | = | = | = | = | 6188a2be | = | = | = |
| `components/http/auth_util.py` | 4eed1443 | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = |
| `helpers/json.py` | 1789bda1 | = | = | = | = | = | = | 3ea52348 | = | = | = | = | f6a778dd | = | = | = | = | c0b24680 | = | = | = |
| `util/json.py` | 1f8e6a0e | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = | = |
| `components/onboarding/views.py` | a4cd0198 | = | = | = | = | = | = | 2801f426 | = | = | d3144de5 | = | 2835631c | = | = | = | = | 21eb4a5f | = | = | = |

2026.11 review (2026-11-11): the exact GitHub tag commits are Core `74cf5a49c63ed8d4d87717844bf14f79c28c9cea` (11.0) and `d8a0dc698c8946b44e455d904000db563cfbf1ba` (11.1), compared to reviewed 10.4 `357cae5c598dfcd7a0ea7dc5b1facccd4ec6037b`. Every one of the 25 consumed and adjacent files is byte-identical between 11.0 and 11.1. Fourteen changed between 10.4 and 11.0; all their hunks were read. Full blob SHAs and tag commits are in [the comparison record](provenance/headscale-ha-core-2026-11-blobs.json).

- `config/auth.py`, `websocket_api/decorators.py` and `messages.py`, `auth/models.py`, `auth/permissions/__init__.py`, and `auth/auth_store.py` did not change. Thus `config/auth/list`, its `require_admin` decorator, `_user_info` fields, `User.is_admin`, `system-admin`, and the `{id,type,success,result}` envelope are unchanged.
- `websocket_api/auth.py` and `connection.py` changed token-revocation handling: a revoked connection now stops processing/sending, except for a short deferred reply by the revoking command. The verifier opens a fresh query-only connection, checks the same reply envelope, and denies on any unsuccessful or missing response. `http.py` added an unauthenticated message-size cap and debug-log redaction. `commands.py` added unrelated system-state and target commands. `websocket_api/__init__.py` and `config/__init__.py` only changed exports.
- `auth/__init__.py` now initializes providers together, serializes new-user creation, and revokes sessions when credentials are removed; `async_get_users` and the role fields remain unchanged. `hassio/__init__.py` added log reader, auto-update, network event handling and unload cleanup, but kept the Supervisor system-user creation and its admin group. `hassio/const.py` added constants. `http/auth.py` moved a key import, `http/__init__.py` added an SSL-profile repair, `http/const.py` added SSL and request-size constants, and `helpers/json.py` only renamed its datetime import. `onboarding/views.py` tightened unauthenticated request size and redirect validation; owner group creation is unchanged.
- Supervisor 2026.10.5 (tag `fdba115f215c61f7a02c7c0567263785cfcf0034`) has the same `supervisor/api/proxy.py` blob `cab849dc` as reviewed 2026.10.4 (tag `d92eb0e373a304c1e6a66dcef66585854a2002d1`). The `auth_required`/`auth_ok` frames and proxy filter therefore retain the reviewed shape. The isolated HAOS test reports Supervisor 2026.10.5 and Core 2026.11.1; role and Ingress acceptance is required before publishing the updated image.

2026.11.2 review (2026-11-17): the exact GitHub tag commit is Core `ff5d56b825a0fb66b03d01bc297d49e206cdaba3` (11.2, released 2026-11-16), compared to reviewed 11.1 `d8a0dc698c8946b44e455d904000db563cfbf1ba`. Every one of the 25 consumed and adjacent files is byte-identical between 11.1 and 11.2: each file was downloaded at both tags and its git blob recomputed, and the blobs equal the GitHub contents API listings of both tags and, for 11.1, [the 2026.11 record](provenance/headscale-ha-core-2026-11-blobs.json). No hunk to read; the consumed contract is unchanged. Full blob SHAs, tag commits and the tag comparison are in [the 2026.11.2 record](provenance/ha-core-2026-11-2-blobs.json).

- Outside the 25 files: the tag comparison (52 commits, 95 files) changes no file under `auth/`, `components/auth/`, `components/websocket_api/`, `components/http/`, `components/hassio/`, `components/config/`, `components/onboarding/` or `components/person/`. Besides integrations and tests it changes the version constants (`const.py`, `pyproject.toml`), the frontend pin (20261028.5 to 20261028.6), integration requirements, `input_text/entity.py` and `helpers/config_validation.py` (a configuration error names a section's keys instead of printing its values); none of them is on the `config/auth/list` path or in the Supervisor handshake.
- Supervisor 2026.11.0 (tag `c1c6f0a754c0656eb1af189f11009f1cfc4b3e28`, released 2026-11-06) ships `supervisor/api/proxy.py` blob `cab849dc`, byte-identical to 2026.10.5 (downloaded at both tags), so the `auth_required`/`auth_ok` frames and the proxy filter keep the reviewed shape.
- Images that accept 2026.11.2: Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud from 0.4.14, Headscale from 0.4.19. Headscale 0.4.18 and the other products' 0.4.13 images deny it.

2026.11.3 review (2026-11-25): the exact GitHub tag commit is Core `92da9f154079459b9e547126f9bd9fce726de16a` (11.3; Core's stable channel offers it as the default on 2026-11-25), compared to reviewed 11.2 `ff5d56b825a0fb66b03d01bc297d49e206cdaba3`; 11.3 is 43 commits ahead of 11.2 and none behind. Every one of the 25 consumed and adjacent files is byte-identical between 11.2 and 11.3: each file was downloaded at both tags and its git blob recomputed, and the blobs equal the GitHub git tree listings of both tags and, for 11.2, [the 2026.11.2 record](provenance/ha-core-2026-11-2-blobs.json). No hunk to read in those files; the consumed contract is unchanged. Full blob SHAs, tag commits and the tag comparison are in [the 2026.11.3 record](provenance/ha-core-2026-11-3-blobs.json).

- Outside the 25 files: the tag comparison (43 commits, 76 files) changes one file under a contract path, `components/auth/indieauth.py`, and none under `auth/`, `components/websocket_api/`, `components/http/`, `components/hassio/`, `components/config/`, `components/onboarding/` or `components/person/`. The rest is 28 other integrations (mostly device and service integrations) and their tests, the frontend pin (20261028.6 to 20261028.8, in `components/frontend/manifest.json`, `package_constraints.txt` and the pylint plugin's `FRONTEND_VERSION`), the version constants (`const.py`, `pyproject.toml`), integration requirements (`requirements_all.txt`) and `core_config.py`; none of them is on the `config/auth/list` path or in the Supervisor handshake.
- `components/auth/indieauth.py` (+5 −1, read in full): `fetch_redirect_uris`, which fetches a login client's `client_id` page to read its `redirect_uri` links, now opens its own `aiohttp` session with `max_line_size` and `max_field_size` set to `MAXIMUM_HEADER_SIZE` (65536; that constant is in `helpers/aiohttp_client.py`, unchanged between the tags). It is called by `verify_redirect_uri`, which the HTTP login flow (`components/auth/login_flow.py`) uses to validate an OAuth/IndieAuth client. That is not the `config/auth/list` path (a WebSocket command of `components/config/auth.py`, unchanged) and not the Supervisor handshake, and the hunk does not touch `User`, groups, `require_admin` or the result envelope.
- `core_config.py` (+3 −2, read in full): `Config._async_update` now sets the time zone first, so an invalid one raises before any other field changes. The auth provider and multi-factor configuration of the same file (`auth_manager_from_config`) lies outside the hunks. `const.py` only changes `PATCH_VERSION` from 2 to 3.
- Supervisor: the stable channel (`version.home-assistant.io/stable.json`, 2026-11-25) is still Supervisor 2026.11.0. Its `supervisor/api/proxy.py` was downloaded again at the 2026.11.0 and 2026.10.5 tags and has blob `cab849dc` at both, so the `auth_required`/`auth_ok` frames and the proxy filter keep the reviewed shape.
- Images that accept 2026.11.3, together with the later-patch rule below: the maintenance release of 2026-11-25, that is Odoo 0.5.2, EMQX, LiteLLM and Nextcloud 0.5.1, n8n and Hermes 0.4.15, Headscale 0.4.20 (and OpenDesign's source 0.4.15). Every earlier image (Odoo 0.5.1 and before, EMQX, LiteLLM and Nextcloud 0.5.0 and before, n8n and Hermes 0.4.14 and before, Headscale 0.4.19 and before) denies 2026.11.3.

The 0.4.13 images continue to deny these Core versions. Only an image rebuilt and accepted for a new product release includes this reviewed allowlist. Headscale 0.4.14 was the first such release; Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud carry the allowlist from their 0.4.14 release.

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

Changes in 2026.10.1 (0.1.9): none. All 21 files have the same git blob as in 2026.10.0 (compared on the GitHub trees of
both tags on 2026-10-11), and so do the adjacent `http/const.py`, `http/__init__.py`, `hassio/const.py` and `hassio/auth.py`;
the consumed contract is unchanged and there is no hunk to read. The only auth-related change between the tags is in
`components/auth/indieauth.py` and `login_flow.py` (an OAuth loopback redirect may change port when PKCE is used), which is
not on the `config/auth/list` path the add-on uses.

Changes in 2026.10.2, 2026.10.3 and 2026.10.4 (next release; blobs read from the GitHub contents API of each tag on
2026-10-27 and recomputed as git blobs from all 25 downloaded files of every tag, 0 mismatches): 20 of the 21 files and the adjacent
`http/const.py`, `http/__init__.py`, `hassio/const.py` and `hassio/auth.py` have the same blob as in 2026.10.1. Only
`auth/__init__.py` changed (`a5850978` → `0314c4b7`, the same blob in all three tags, so 2026.10.3 and 2026.10.4 change
nothing more). Its one hunk (four lines, read in full) is in `AuthManager.async_remove_user`: before the user is deleted
from the store, each of the user's refresh tokens is now removed with `async_remove_refresh_token`, whose revoke
callbacks close the connections that use them. `async_get_users` (what `config/auth/list` returns), `User.is_admin`,
`require_admin`, `_user_info` and the result envelope are untouched, so the consumed contract is unchanged; the add-on
never removes users, and a removed user was already absent from the list the verifier reads per request. Supervisor
2026.10.2–2026.10.4 (`api/proxy.py` blob `cab849dc`) are reviewed above. Raw evidence (blob listings, both versions of
the file, the diffs) is kept outside the repository with the 2026-10-27 review.

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
   - `tests/test_ha_role.py`: add the version to `test_the_reviewed_versions_are_exactly_these`, to the per-release list of
     `test_core_2026_11_releases_keep_fresh_admin_check` (or its successor for a new month), and to the two tables of
     the rule's tests (the newest reviewed patch of each month in
     `test_exactly_the_reviewed_versions_and_the_later_patches_of_reviewed_months_are_accepted` and `_REVIEWED_MONTHS` in
     `test_the_rule_table_is_computed_from_the_reviewed_list_and_cannot_be_changed_at_run_time`); the range
     `(reviewed: …)` in `test_an_unreviewed_core_version_denies_with_its_reason_and_one_log_line` names the newest
     listed version. Then move every example that stood for the version: once it is listed it is neither a later patch
     (`LATER_PATCHES` and the log tests: use the next patch number) nor unreviewed (`NEAR_MISSES`, `UNREVIEWED`; the
     near-miss tests fail until it is removed). For the first release of a new month the unreviewed examples move to the
     month after it (`2026.12.0` today, in `test_wrong_sequence_and_revoked_machine_capability` and the gateway tests);
   - the version-list sentence in [n8n-ha-role.md](n8n-ha-role.md) ("Compatibility is deliberately restricted to …");
   - the new release's `addons/<product>/CHANGELOG.md`, naming the added versions;
   - the supported-version note in that product's `DOCS.md`, `README.md`, the repository `README.md`, and
     `docs/operations/guide.md`. Other products' published images keep their earlier allowlist until separately built.
5. Ship it in a new add-on release: an installed add-on accepts only the versions listed in its own image and the later
   patch releases of those months (next section). The first release of a new month always needs steps 1 to 4 and a new
   add-on release before any installed add-on accepts it.
6. A later patch release that the rule has been accepting is reviewed the same way at the next add-on release: once it is
   listed it has a column and its log line stops.

## Later patch releases of a reviewed month

Owner decision 2026-11-25 (DQ-35, [decisions](multi-profile/decisions.md)): a release that is later than every reviewed
release of a month already in `_HA_VERSIONS` is accepted without waiting for an add-on release; a new month is still
reviewed first ("reviewed 2026.11 means 2026.11.x is accepted"). Before, every Core update, a patch release included,
locked the management panel (403) of every installed add-on until an add-on release listed it. This is a change to a
permission check, so it needs a separate review before it enters a release: it first enters the maintenance release of 2026-11-25 (Odoo 0.5.2, EMQX, LiteLLM and Nextcloud 0.5.1, n8n and Hermes 0.4.15, Headscale 0.4.20); the status of that review is in the decision log (DQ-35).

**The rule** (`ha_role._later_patch`; its table `_REVIEWED_MONTHS` is computed from `_HA_VERSIONS` when the module loads,
not per request, and cannot be changed at run time):

- The advertised string is exactly `year.month.patch`: four ASCII digits, a month from 1 to 12 and a patch of one to
  three ASCII digits, neither padded with zeros (`0` alone is fine). Padding (`2026.09.4`, `2026.10.01`), spaces or a
  newline around it, a `v` prefix, a pre-release (`b`, `rc`, `.dev`), a fourth number and any non-ASCII digit are
  refused, and so is a value that is not a string.
- The year and month already have a release in `_HA_VERSIONS`, and the patch is greater than the newest reviewed patch of
  that month. With 2026.11.3 reviewed, 2026.11.4 and every later patch of 2026.11 are accepted (2026.11.0 to 2026.11.3 are
  listed); 2026.7.0 and 2026.7.1 (before the first reviewed release of July, 2026.7.2) are not, and neither are
  2026.12.0, 2026.6.9 or any other month that is not listed.
- Nothing else changes. `auth_required` and `auth_ok` must carry the same version; a version that is not accepted is
  refused before the machine token is sent; every decision is a fresh connection with a fresh `config/auth/list` and no
  cache; the answer is parsed as strictly as before (a changed shape denies); only an active, non-system user who is the
  owner or in `system-admin` passes.
- One add-on log line per version and process, at most 32 (the refusal's own limit, counted apart):
  `management: Home Assistant Core <version> is accepted as a later patch release of <year>.<month>, which this add-on
  release reviewed (<first> to <last>); the version itself was not reviewed. The management panel checks the administrator
  role as for a reviewed release.` No frame, token or user is logged, and a listed version logs nothing.

**Why this is acceptable.** The version string is Supervisor's record of the installed Core, not something a client
sends; it only says which Core code answers `config/auth/list`. A patch release is a bug-fix release of the code of its
month, so the contract read for that month is expected to stand. Of the 16 patch releases reviewed so far after a reviewed
release of the same month (2026.7.3–7.4, 8.1–8.3, 9.1–9.4, 10.1–10.4, 11.1–11.3), 13 changed none of the 21 files of
the table and 3 changed one each (2026.8.2 `hassio/__init__.py`, 2026.9.3 `onboarding/views.py`, 2026.10.2
`auth/__init__.py`); in all three the hunks were outside the consumed contract (notes above).

**The risk accepted.** A later patch release could change the contract this verifier consumes (the fields of
`config/auth/list`, the meaning of `is_owner`, `is_active`, `system_generated` or the `system-admin` group, or who
`require_admin` lets through) before an add-on release has read it. The strict parsing denies a changed shape, not a
changed meaning that keeps the shape. The window lasts until the next add-on release reviews that patch release; the
owner accepted it so that a Core patch update does not lock the panel. The first release of a new month, and its
pre-releases, are not covered: they need the full review above before any add-on accepts them.

**What it would cost, how it would show, how to undo it.**

- Worst case. A user who is not an administrator but is reported as one gets the panel's full administration of that
  add-on: `token/reveal` shows the MCP token, `token/rotate` replaces it, and the backend connection with its credentials
  and the tool policy can be changed. That is the add-on's reach into its backend (Odoo, LiteLLM, Nextcloud, EMQX, n8n,
  Hermes or Headscale), for the length of the window.
- Detection. One add-on log line per version and process (`accepted as a later patch release`, above). The panel shows
  nothing.
- Recovery. The rule has no run-time switch. Refusing a Core version again takes a new add-on release (an estimated
  working day or more, [threat model](multi-profile/threat-model.md)), or stopping the add-on.

**Where the exposure is today.** Home Assistant no longer ships patch releases of the older months (the last ones are
2026.7.4, 2026.8.3, 2026.9.4 and 2026.10.4), so in practice the rule newly accepts 2026.11.4 and later, nothing before it.

**What stands behind the rule, and what does not.** (1) Core's Ingress check is not an independent gate. From Core
2026.11.0 the dedicated commands `hassio/ingress/info` and `hassio/ingress/session` call `_async_check_ingress_access`
(`components/hassio/websocket_api.py`, lines 175-183, called at lines 199 and 231 in 2026.11.3), which refuses a user who
is not an administrator for an add-on whose panel is admin-only (`panel_admin: true`, set by all eight add-ons here).
2026.7.2, 2026.9.4, 2026.10.0 and 2026.10.4 do not have it. It can also be walked around: `WS_NO_ADMIN_ENDPOINTS` (lines
60-65) lets a non-administrator call `/ingress/session` through the generic `supervisor/api` command (lines 135-138), and
Supervisor's `create_session` (`supervisor/api/ingress.py`, 2026.11.0, lines 145-162) checks that the user exists and is
active, not that the user is an administrator. (2) What stops a non-administrator is Supervisor's check on every Ingress
request: `handler` in `supervisor/api/ingress.py` refuses the request when the add-on's `panel_admin` is set and the user
is not an administrator (line 191 in 2026.11.0). It exists from Supervisor 2026.10.2 (not in 2026.9.3, 2026.10.0 or
2026.10.1), so on Core 2026.11.x with the current stable Supervisor (2026.11.0) it is there. It is not independent of
this verifier: Supervisor gets its users by sending `config/auth/list` (`supervisor/homeassistant/module.py`,
`list_users`) and its `HomeAssistantUser.is_admin` mirrors Core's `User.is_admin` (`supervisor/const.py`), so a Core patch
release that changed what `config/auth/list` reports would mislead both. It does catch an implementation error on either
side. The add-on does not rely on it either way (the README: `panel_admin` is not an authorization). (3) Every request to
the panel is checked against the live role on a fresh connection, so a demotion applies to the next request. (4) A string
that is not exactly `year.month.patch` of a reviewed month is refused before the token is sent. (5) MCP endpoints never
used this check and are not affected either way.

## A version that is not accepted

Any other version, including a new month, a patch release before the first reviewed one of its month, pre-releases and
differently formatted strings, is refused. The refusal says why. The verifier stops before it sends the machine token
(as before) and returns a denial that carries the advertised version when it has the form of a Core release or
pre-release (`shown_version`; any other string is reported as unrecognized and never echoed). The panel then answers its
pages with a static page "這個 HA Core 版本尚未審核：<version>" and its API with HTTP 403
`{"error": "request denied", "detail": {"code": "core_version_unreviewed", "ha_version": <version or null>}}`; every
other refusal keeps the fixed `{"error": "request denied"}`. The page and the panel's message say that a later patch
release of a reviewed month is accepted without a review, so a refused version is a new month, an earlier patch, a
pre-release or an unrecognized string. The add-on log gets one line per version and process
(`management: Home Assistant Core <version> has not been reviewed for this add-on release (reviewed: <first> to <last>);
only a later patch release of a reviewed month is accepted without a review, so the management panel refuses every request
until an add-on release reviews it. MCP endpoints do not use this check.`), without any frame, token or user. MCP endpoints
authenticate with the add-on token only and never use this check, so they keep serving.
