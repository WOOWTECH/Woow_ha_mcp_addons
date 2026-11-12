# EMQX retained-operation correctness port

This HA source change starts from PR40 candidate
`2a62c186ddfd1d2169bc105698f9c4e77ecf9dd6`. The vendored upstream remains
`WOOWTECH/Woow_emqx_mcp_server@1be17bad5aef6c7b7519686ccbfe1d80762bc10e`.
The retained-operation correction follows the independently developed PaaS
EMQX app checkpoint `caad3965646f9dac3f4f57f3677aff92196745a2`
(`apps/emqx/emqx_mcp_server/errors.py` and `tools/messaging.py`). It is a
bounded behavior port, not a replacement of HA's destination/transport policy.

## Changed behavior

- `errors.py` preserves the HTTP status as typed exception metadata. A timeout explicitly leaves the write result
  uncertain. Empty, malformed, or scalar JSON is an error where a JSON body is
  expected; explicit HTTP204 retains its no-content behavior.
- `tools/messaging.py` handles a retained GET404 through the existing listing
  compatibility path. Authorization, rate-limit, server, transport, and JSON
  failures propagate instead of masquerading as an absent retained message.
- Retained DELETE sends one DELETE. No failure, including404, triggers a
  second empty retained publish: that publish is visible to subscribers and
  could follow an already-applied deletion. A caller must inspect broker state
  before deciding whether to make a separate write after an uncertain result.

Valid direct reads, topic percent encoding, listing fallback results, and
successful DELETE204 remain supported. Tool names, arguments, schema outputs,
default grants, selectors, shared UI, and backend destination checks are unchanged.
The response parser now rejects invalid JSON for other tools using the same helper,
including publish; it does not claim to validate every endpoint's response schema.

## Provenance and verification

`runtime-sources.json` retains both original upstream SHA256 values and adds
the adapted local SHA256 and explanation. `runtime-patches.json` covers the two
modified files. `tool-surface.json` changes only their hashes and five shifted
declaration line numbers; no tool surface or grant changes.

`tests/test_emqx_retained_errors.py` invokes the pinned EMQX child through the
HA gateway against owned HTTP fixtures. It checks non404 errors, failed writes
that already applied at the backend, request/effect counts, invalid JSON,
404 listing compatibility, successful direct reads, DELETE204, and publish202.
These are local protocol regressions, not acceptance against a published image
or a real EMQX backend. Original failing and corrected run receipts remain in
the implementing lane's external evidence directory.

No version bump, image build/publication, registry change, or production action
is performed by this port. Main owns final release integration and acceptance.

## 2026-10-31 bounded-error follow-up

The later source-only EMQX parity change keeps the typed `status_code` and the
single-request retained DELETE behavior above. It rejects redirects, stops
returning raw broker response bodies and request paths in tool errors, and
maps additional `httpx` transport failures to bounded public codes. This
matches the seven reviewed synthetic PaaS 29fa source cases. It requires a
future HA image and real-broker replay; this document is not publication proof.
