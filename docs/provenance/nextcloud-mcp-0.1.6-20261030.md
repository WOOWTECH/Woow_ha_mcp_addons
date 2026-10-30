# Nextcloud child: vendored upstream v0.1.6 (HA 0.4.7)

Source change only. The version bump, image build, publication and Store release are recorded separately in
[release-decision-0.4.7.md](../operations/release-decision-0.4.7.md).

## Sources

- HA base: `e5c13f41` (`claude-delivery`, merged #39, 0.4.6).
- Upstream: `WOOWTECH/Woow_nextcloud_mcp_server@8aa6be3d034509e43b4501c1d3da1523f6a299e5` (v0.1.6, branch
  `release/v0.1.6-credential-masking`, PR #2). It contains `159410ac` (main `ce59615`), the masking the PaaS
  `woow-mcp-server` already vendors, plus three further commits. The previous vendored source was tag v0.1.5
  `4e09c86f8ee66f147a2d227e7ed1eb9d989394a6`. If the upstream merge or tag ends on a different commit, only the
  commit strings in `runtime-sources.json`, `scripts/vendor_runtimes.py` and the notices change; the file bytes
  below must be the same.
- Acquisition: `python scripts/vendor_runtimes.py --stage nextcloud <empty dir>` against raw.githubusercontent.com
  at `8aa6be3`. The staged files are byte-identical to the git objects of that commit. LICENSE (MIT, 2026 WOOWTECH)
  did not change.

| File | Upstream SHA-256 (v0.1.6) | Shipped SHA-256 |
| --- | --- | --- |
| `nextcloud_mcp_server/__init__.py` | `ca4f898ad6970c83…` | upstream bytes |
| `nextcloud_mcp_server/server.py` | `fa2f912301bd0d3e…` | `eb25088dc4d2158f…` (unchanged local file) |
| `nextcloud_mcp_server/settings.py` | `d8283658375f65ec…` | upstream bytes |
| `nextcloud_mcp_server/client.py` | `ebc19b1faf64c7b9…` | `d68fded078c54a4e…` |
| `nextcloud_mcp_server/errors.py` | `add1c055407964f3…` | `fcb45f44cac902a4…` |
| `nextcloud_mcp_server/paths.py` | `806f187a9ad668c8…` | upstream bytes |
| `nextcloud_mcp_server/webdav.py` | `9ad656234100ea2a…` | `5a0ee7e6c896579f…` |
| `nextcloud_mcp_server/caldav.py` | `a6643700ae4f2b9c…` | upstream bytes |
| `nextcloud_mcp_server/ical.py` | `531ca3c58684ea1c…` | upstream bytes |
| `nextcloud_mcp_server/tools.py` | `9b22f15816e56e68…` | upstream bytes |
| `LICENSE` | `1b05bfafc14067be…` | upstream bytes |

Full hashes and the reason for every local change are in `runtime-sources.json`.

## What upstream changed between v0.1.5 and v0.1.6

- `errors.py` adds `REDACTED`, `credential_forms()` and `mask_credentials()`. The forms of each credential are
  the literal value; URL-quoted (`quote(safe="")`); JSON-escaped with ASCII-only and with UTF-8 output; standard
  and URL-safe base64 with and without padding; and each of these with `/` written as `\/`. Matching runs once on
  the original text, longest form first; overlapping occurrences merge into one `[REDACTED]`, adjacent separate
  occurrences keep one marker each, and the marker itself is never matched again.
- `webdav.py` `server_message(body, *, credentials=())` masks before folding whitespace and before the length
  bound.
- `client.py` passes the configured app password and `username:password` for statuses below 500.
- `__init__.py` is 0.1.6. `server.py`, `settings.py`, `paths.py`, `caldav.py`, `ical.py` and `tools.py` are
  unchanged, so tool names, schemas, annotations and registration are unchanged.

## Local changes carried over (HA wrapper)

| File | Local change | Reason |
| --- | --- | --- |
| `client.py` | `load_backend_policy()` refuses to start without `backend_policy` | Never an unrestricted client behind the gateway |
| `client.py` | The masked `server_message` call also runs for 5xx | Owner decision 2026-10-15: Nextcloud's own text is relayed for every non-2xx status; upstream reads it below 500 only |
| `errors.py` | `status_message` appends ` Nextcloud: <detail>` | Same owner decision; the masking helpers in this file are unmodified upstream code |
| `webdav.py` | OCS `meta/message` (XML/JSON), JSON `message`/`error` and plain-text extraction; `SERVER_MESSAGE_LIMIT = 1000` (upstream 200) | Same owner decision |
| `server.py` | Private `woow_backend_probe` | Gateway health probe; byte-identical to 0.4.6 |

The 0.2.1 hunks of `errors.py` and the extraction code of `webdav.py` are identical to 0.4.6. The `client.py`
5xx change is the same behavior on top of the new upstream call.

## The HA masking routine is removed

0.4.4 added a small routine to `webdav.server_message`
([nextcloud-error-secrets-20261029.md](nextcloud-error-secrets-20261029.md)). Upstream v0.1.6 covers each of its
forms at the same position, so the routine is removed and every extraction path calls `errors.mask_credentials`.

| Form | HA 0.4.4 routine | Upstream v0.1.6 |
| --- | --- | --- |
| Literal password and `username:password` | masked | masked |
| URL-quoted (`safe=""`) | masked | masked |
| JSON-escaped (ASCII output) | masked | masked |
| JSON-escaped (UTF-8 output) | not masked | masked. HA credentials are printable ASCII (`products.credential`), so this form equals the ASCII one here |
| Standard and URL-safe base64, with and without padding | masked | masked |
| Any of the above with `/` written as `\/` (PHP `json_encode` default) | not masked | masked |
| Overlapping occurrences (periodic password, base64 padding followed by a password starting with `=`) | fragment left | one marker |
| Position | after extraction, before folding and truncation | same |

Upstream does not mask 5xx detail, because it does not read it, and it extracts only Sabre messages. Those two
paths are HA wrapper behavior, listed above. Both now go through the upstream function; no part of the old
routine remains.

User-visible effect: Nextcloud error text that echoes a configured credential in one of the new forms now shows
`[REDACTED]` where 0.4.6 showed it, and overlapping occurrences show one marker where 0.4.6 left a fragment. Public
error codes, `isError`, the 401/429 latches (set before the body is read), the fixed 401/429 texts, the 1000-character
limit, successful replies, tool schemas and permissions are unchanged. No option, state or schema change.

## Verification

- `tests/test_nextcloud_error_secrets.py` (genuine child behind the genuine gateway, owned fake backend, fake
  credentials) keeps its 14 cases (7 forms × SSE/JSON) and adds 6: `json-slash`, `basic-slash`, `overlap` × SSE/JSON.
  Each case checks 403/422 JSON and 500 JSON/Sabre/OCS/plain-text replies, plus caplog, captured output and retained
  child logs. With the 0.4.6 vendor (`e5c13f4`) and the new test file: **14 passed, 6 failed**; every failure is a
  credential form in the tool response for all six status/format combinations. With this source: **20 passed**.
- `test_nextcloud_child.py`, `test_child_diagnostics.py` and the Nextcloud parts of `test_raw_backend_errors.py`
  pass unchanged, including the relayed own-message cases for Sabre, OCS and plain text at 403/422/500/503.
- Differential check of `webdav.server_message`, 0.4.6 vendor against this source, 20,000 random printable-ASCII
  credentials, five body formats: with messages built from the forms of the 0.4.4 routine, 99,995 outputs are
  identical. With forms only upstream adds, the new output never contains a known form; the 0.4.6 output still
  contained one in 22,900 of 99,995 cases. Periodic credentials leave no fragment.
- The full repository checks for the release are in the release decision.

## Limits

Masking covers the two credentials this client holds and the forms above. Arbitrary backend secrets, other
encodings, and a backend that returns only part of a credential are not recognized. Ordinary diagnostic text stays
visible under the owner policy. The gateway still redacts its own tokens and the connection credentials from every
reply. This record is a source review; image, HAOS and production acceptance are separate.
