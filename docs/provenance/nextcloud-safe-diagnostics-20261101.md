# Nextcloud fixed diagnostics source update (0.4.10 candidate)

This source-only change vendors `WOOWTECH/Woow_nextcloud_mcp_server@28767c4fa15acd4981586ed04906c48523f6bf26`, the merged upstream revision containing the safe quota diagnostic and the additional home-folder wording. The `0.4.8–0.4.9` add-on source used v0.1.6 `8aa6be3d034509e43b4501c1d3da1523f6a299e5`. The historical provenance and the 2026-10-15 raw-backend-text decision remain in [nextcloud-mcp-0.1.6-20261030.md](nextcloud-mcp-0.1.6-20261030.md); this change intentionally supersedes that behavior for the next release.

Recognized WebDAV Sabre XML, OCS JSON and plain-text quota failures now expose only the fixed category `storage quota exhausted` with the public `BACKEND_HTTP_ERROR` status code. An unrecognized failure retains its generic status text; redirect responses no longer print the backend-supplied `Location`. Backend bodies, arbitrary tokens, internal hosts and configured credentials do not appear in the tool response. The 401/429 latch is set before reading the error body, as before. Tool names, input schemas, output schemas and successful responses are unchanged.

`client.py` retains the HA-only fail-closed requirement for `backend_policy`, and `server.py` retains the private `woow_backend_probe`. All other vendored Nextcloud Python files, including `errors.py` and `webdav.py`, are byte-identical to the recorded upstream revision. Per-file upstream and local hashes are in `runtime-sources.json`; `scripts/vendor_runtimes.py` pins the same source revision.

The change is source-level only. Passing tests and packaging validation do not imply a published `0.4.10` image or a ws97 HAOS acceptance. Image publication requires the separate exact-head private-builder and release checks.
