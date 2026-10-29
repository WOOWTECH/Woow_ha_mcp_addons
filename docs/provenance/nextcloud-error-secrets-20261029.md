# Nextcloud error detail: configured credential masking

## Sources and existing owner contract

- HA baseline: `f71fb756baf5ca3458b32c5c20635e0689c13118` (`claude-delivery`, merged #26).
- PaaS #89 comparison: `38a9041fb44de6d8848166473facd2f443e04710`. PaaS behavior below comes from the prior pinned-source comparison, not a new production request.
- Upstream vendored Nextcloud: `WOOWTECH/Woow_nextcloud_mcp_server@4e09c86f8ee66f147a2d227e7ed1eb9d989394a6`.
- The owner's 2026-10-15 decision, recorded in `runtime-sources.json` and `tests/test_nextcloud_child.py::test_nextcloud_own_error_message_is_relayed`, preserves Nextcloud's own diagnostic detail. This change preserves that decision.
- The earlier `nextcloud-error-parity-2026-10-29.md` audit and separate helper-only commit `21cd30336d87461655ca16be37b3999d6c5804ca` already resolved the distinction between the pure 401/429 formatter and actual requests. The real client latches 401/429 before reading the response body. This change does not include that helper patch.

## Demonstrated leak and smallest repair

`tests/test_nextcloud_error_secrets.py` runs the genuine pinned Nextcloud child through the genuine HA gateway, with a saved fake app password and an owned loopback Nextcloud server. The backend accepts the configured credentials for the account lookup and echoes them in a failing WebDAV request. Both JSON and SSE MCP responses are inspected after decoding, including `isError` and the public status code. No production backend, credential or image is used.

Before the change, the gateway's `redact.secret_values` / `redact.redact_secrets` removed literal passwords and Basic-auth values, but not URL-quoted passwords, JSON-escaped passwords embedded in a message, or base64 of the password alone. All three reversible representations escaped in actual 403/422/500 tool responses. There were six failing cases and four passing controls (two MCP transports).

Two additional transformations also defeated the gateway: Nextcloud folds repeated whitespace in a detail, and truncates it to 1000 characters. A configured password containing two spaces leaked after folding; a password starting at offset 984 leaked its first 16 characters after truncation. These four additional real-child cases failed before the repair.

The repair supplies the configured password and `username:password` to `server_message`, which replaces exact known credential forms **after parsing XML/JSON and before whitespace folding or truncation**. Its variants follow the existing `diagnostics.scrub_line` approach (literal, URL-quoted, JSON-escaped and base64), with the gateway's URL-safe/unpadded Basic forms. A single substitution pass prevents a short credential from corrupting previously emitted `[REDACTED]` masks. The child cannot import the admin core with its existing isolated `PYTHONPATH`, so this small vendored routine uses only the standard library and does not widen that path or change dependencies.

Only error detail is processed here. Ordinary diagnostics, the 1000-character limit, error codes, `isError`, tool schemas, permissions, authentication latches and successful file contents keep their existing contracts. The gateway remains responsible for its own tokens.

## Evidence matrix

| Contract | PaaS pinned-source evidence | HA baseline | HA repaired source |
| --- | --- | --- | --- |
| Actual 401/429 | Fixed text; auth latch before body read | Same, irrespective of pure helper behavior | Existing latch retained |
| 403/500 ordinary detail | 403 fixed text; 500 detail suppressed | Detail retained by owner decision | Detail retained |
| 422 ordinary detail | Sabre detail in generic error text | More detail formats; different punctuation | Existing HA wording retained |
| Configured literal password / Basic auth in 403/422/500 | Not re-tested in this work | Gateway masks them | Still masked |
| URL / JSON-escaped / password-only base64 in 403/422/500 | Not re-tested in this work | Reversible credential escapes in JSON and SSE | Masked before formatting |
| Password containing repeated spaces | Not re-tested in this work | Whitespace-folded password escapes | Masked before whitespace folding |
| Password crossing the 1000-character limit | Not re-tested in this work | First 16 password characters escape | Masked before truncation |
| Child diagnostics and gateway/captured logs | Not re-tested in this work | No tested credential forms found | No tested credential forms found |

The log check reads actual `Supervisor.logs` after the child stops and output readers join; entries must be nonempty. The current implementation retains bounded, scrubbed child output in memory. Older comments claiming all child output is discarded are stale.

## Verification and limits

The initial 14 real-child regression cases changed from 10 failing / 4 passing to **14 passing**. The final regression also exercises JSON, Sabre XML, OCS JSON and plain-text detail while preserving a nonsensitive diagnostic marker: 84 error calls across 14 child lifetimes. The focused run of `test_nextcloud_error_secrets.py`, `test_nextcloud_child.py`, `test_child_diagnostics.py` and `test_raw_backend_errors.py` passed **70 tests**. `test_tool_inventory.py` passed **6 tests**; `scripts/tool_inventory.py --check`, `packaging/validate.py` and `git diff --check` also passed. Full commands and raw outputs are recorded in the local audit report and evidence matrix.

The original PR33 at `d81bc7c578746b0a94ea762e103db81b7d101f30` was a source-only repair with no version change or publication. The unified 0.4.4 draft now includes that exact client/webdav code alongside PR30/31/32; its release decision and integration record own the version/gate status. The original PRs remain unchanged. Reconcile the two Nextcloud hash entries if the separate helper commit is later integrated; retain each change's independent evidence.

Masking covers credentials known to this Nextcloud client and the explicit representations above. Arbitrary backend secrets, unknown encodings, and a backend that supplies only a partial credential cannot be recognized generally. Ordinary internal diagnostic text remains visible under the existing owner policy; this evidence does not establish that every backend message is free of sensitive information. Live PaaS/HA acceptance and released-image verification are outside this source audit.
