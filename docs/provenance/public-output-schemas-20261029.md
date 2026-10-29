# Controlled public output schemas

Source feature only; no version change, image build, publication or deployment.
Base: `235338cc7d1a02d17fbb93b631e37c77a20c7889` (protected PR37 merge).

## Source and contract review

`packages/mcp-admin-core/mcp_admin_core/output_schemas.json` records 43 exact
schemas, their canonical SHA-256, and a second digest of
`{product, tool, schema}`. Each entry identifies its actual handler source;
`sources` pins the reviewed HA commit, handler/server/guard bytes and child
`pyproject.toml`/`uv.lock`. These are review pins, not signatures or claims that
an arbitrary child is trusted.

The schemas were extracted from the actual pinned children, using FastMCP
4.1.3 / MCP 2.3.0 / mcp-types 2.3.0, then independently compared with raw
HTTP `tools/list` from the real child processes behind the gateway. No schema
was inferred from an example response or invented to fill a parity gap.

| Product | Public contracts | Audited meaning |
| --- | ---: | --- |
| LiteLLM | 35 of 40 tools | Actual `dict` return contract: `type: object, additionalProperties: true`. This deliberately promises no unreviewed backend-specific fields. Includes model, key, team, user, health and selected plugin operations. |
| Nextcloud | 8 of 9 tools | Exact TypedDict fields for file tree/text, calendars/tasks, create/update/upload/delete results, including nullable fields, optional notes and fixed status values. |

The five LiteLLM tools without an output declaration (`litellm_spend_logs`,
`litellm_list_plugins`, `litellm_plugin_info`, `litellm_delete_plugin`,
`litellm_skill_hub`) remain without one. Nextcloud `get_file_content` returns
content/resources without such a declaration and remains unchanged. The private
`woow_backend_probe` is never made public. Other products remain uncurated;
this does not claim complete cross-product output-schema parity.

Current PaaS comparison uses clean tracked source
`b3201ba657c07ed01e7e8ba8b233044f900fcf37` in woow-mcp-server. All LiteLLM
handler module bytes match HA; Nextcloud `tools.py` matches too. With the same
pinned SDK, both actual PaaS server factories produce the same 40/9 public
schema declarations (35/8 non-null) as HA. PaaS `tool_filter.py` remains
byte-identical to the prior reviewed `38a9041` version (SHA-256
`f2d5434af412549211ff2d67053996858ac9f74b3ece448623cf8da6af19d1e8`): it removes
disabled names and otherwise retains child metadata.

No PaaS handler change is necessary for these 43 schemas to match. Applying the
same *controlled-publication policy* to PaaS would require a separate proxy
filter/fallback review: its present relay does not enforce this allowlist. This
HA change does not claim to harden that PaaS path.

## Runtime boundary

- Product identity comes from local product state; child-provided product fields
  cannot select a pin. Only full-child tools are eligible; bounded local tools
  keep their existing contract.
- A supplied schema must match the entire canonical pinned value. Unknown
  product/tool, absence, a changed field or an unreviewed extension omits only
  `outputSchema`; the tool remains callable under its original policy.
- A finite, bounded vocabulary permits the object/array/scalar fields and
  nullable unions actually used by these contracts. All references (including
  local refs), regex patterns, format hooks, custom keywords and arbitrary
  annotations remain unsupported. There is no resolver or regex compilation.
- A damaged registry fails closed. Returned data is a fresh copy of the reviewed
  value, not a child-owned object.
- `execution`, icons, `_meta`, unknown fields, cautious annotation rules,
  duplicate-name handling, pagination, input schemas and authorization retain
  their prior filters. Tool call output is not rewritten or projected.
- The existing generated fallback snapshot now includes precisely these 43
  schemas. It uses the same listing filter as live responses. It keeps the
  audited contract when no child is available; a live child with changed or
  missing schema is not silently assigned the fallback schema.

## Verification

Focused command (repository's normal installed n8n SDK is the CI default;
local execution used a separately owned SDK 1.32.2 installation):

```sh
WOOW_OUTPUT_SCHEMA_SDK=/path/to/owned/node_modules/@modelcontextprotocol/sdk \
.venv/bin/python -m pytest -q \
  tests/test_output_schemas.py tests/test_output_schema_runtime.py \
  tests/test_tool_metadata.py tests/test_full_surface.py tests/test_tool_snapshot.py \
  -k '(not every_child_tool_is_served and not real_child_lists_its_complete_surface and not snapshot_equals_the_real_child and not unconfigured_n8n) or litellm or nextcloud'
```

Result: **120 passed, 12 deselected**, two existing websockets deprecation
warnings. Tests include all 43 pins, exact source hashes, changed/unknown/
external/ref/pattern rejection, corrupted registry, product binding, metadata
and grant filtering, repeated fallback, and real LiteLLM/Nextcloud child lists.
Python MCP 2.3.0 and TypeScript SDK 1.32.2 connect/list/call through the real
gateway, validate structured results and accept tool errors. They exercise all
eight Nextcloud contracts and five representative LiteLLM tools against owned
fake HTTP/WebDAV/CalDAV backends. Python additionally proves missing structured
content is rejected by its actual SDK validator. These tests do not claim live
customer/backend or HAOS acceptance.

An initial broader selection produced 120 passes plus six environment failures:
it also selected inventory/other-product real-child tests whose pinned child
environments were intentionally not installed in this new worktree. The final
selection retains the affected two products and existing metadata tests; those
six failures are not presented as passing tests. No full CI was run.

## Integration ownership

Main owns the final runtime ledger and release integration. Before its full CI,
main must update `docs/provenance/runtime-patches.json` for `policy.py` and
`tool_snapshot.py`, add a new `output_schemas.py` runtime entry with `output_schemas.json` in its
`guarded_sources` map, and describe the exact 43-contract exception to the historical
all-output-schema-drop policy. No upstream/vendor/lockfile bytes changed, so
`runtime-sources.json` upstream hashes need no re-pin for this feature. Include
this document in the release/tool-surface explanation without claiming broader
coverage. The separate handoff receipt records exact old/new SHA-256 values. Keep the JSON
as a guarded data source of the module, not a standalone executable patch: the
existing ledger test interprets bare 64-hex strings inside non-Python patches as
child-wheel source guards; this JSON instead contains product/tool/schema review
pins. The ordinary guarded-source file-hash assertion covers the entire JSON,
and the focused tests check every binding and handler source hash.

For a future schema/source change, inspect actual pinned child output and its
structured-result behavior, review the complete schema and source hashes,
update the registry, regenerate the affected fallback from the real child, and
rerun the focused tests. Do not auto-approve arbitrary metadata or simply update
a digest to make a mismatch disappear.
