# n8n result flag and LiteLLM registry correction — next release after 0.4.4

Source-only follow-up, 2026-10-29. This work is for a release **strictly newer
than 0.4.4**. It is not part of the frozen 0.4.4 candidate and does not change
versions, dependencies, image tags, release receipts or deployment state.

## Base and scope

- Frozen PR34 integration source: `a373bc266e1287a29b8f57581c9f88d5a00983bc`.
- Integration branch: `integration/ha-mcp-parity-0.4.4-20261029`.
- Its parent: `f378a7752538d0cdbf2a23db4af3dfb7ceee0e39`.
- Separate worktree/branch: `fix/n8n-error-contract-next-20261029`.
- Before starting, the frozen tree and all 618 tracked file digests were checked
  against the local release team's source freeze. The main coordinator then explicitly
  confirmed that complete SHA.

The preceding PaaS/HA audit found all 68 public n8n/LiteLLM tools and input
schemas aligned at maximum access. These two corrections address a response
flag defect and a registry description defect. Fine operation denies, direct
inputs compatibility, session settings, `/v1` URL normalization and outputSchema
policy are separate follow-ups; none are changed here.

## n8n

`apps/n8n/patches/fix_tool_result_is_error.py` changes only the result tail in
pinned n8n-mcp 2.96.2 `dist/mcp/server.js`:

| File state | SHA-256 |
| --- | --- |
| Published server.js | `a1237f5cafe34cddcecb85c48bc467c38a443be487a34b0f24c5cbbb343b30e9` |
| Patched server.js | `638b148f91c18d484b8bcede838be1032f82ddd1b3aa53b24cf005325ae3d9f7` |
| Existing patched handlers-n8n-manager.js, unchanged | `6cd673423e829902f3e56de66afe90f7e2196d7ef76cca02551a20eee03ae2eb` |

An object with `success === false` adds `isError: true`. A `valid:false`
validation answer alone remains normal. Existing response text and validation
structuredContent are preserved. The result-tail replacement and its resulting
digest match the reviewed PaaS #89 `38a9041` result patch; its separate workflow
delete description change is not included.

The Dockerfile and unit setup apply this patch after the existing test-run
error-message patch. `backend_policy.cjs` accepts only the new server digest.
Unreviewed bytes fail before writing; a second application is a no-op. The
runtime patch ledger updates the backend guard and the two existing source
references for request limits and argument normalization. Those two modules'
code and the old handler patch are unchanged.

## LiteLLM

Only `litellm_update_model` in the vendored registry changes from
`POST /model/update` to `PATCH /model/{model_id}/update`, matching the existing
handler. The handler still percent-encodes the model ID and retains its body,
operation grant, effect, input/output schemas and backend behavior.

The upstream registry digest stays in runtime-sources.json; a local digest and
modification record are added. The generated inventory changes only three
digests: this registry, n8n server.js and n8n backend_policy.cjs. All inventory
tool entries and generated Markdown remain identical to the frozen base.

## Focused verification

Existing installed environments were reused. n8n node_modules was copied into
the separate worktree before patching; the integration copy was not changed.
No dependency installation, service startup, image build or live backend call
was used.

```sh
# After restoring the already-pinned dependencies, use the normal build patches:
python3 apps/n8n/patches/fix_test_run_error_messages.py
python3 apps/n8n/patches/fix_tool_result_is_error.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/tool_inventory.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_n8n_tool_result_is_error.py \
  tests/test_litellm_registry_contract.py \
  tests/test_tool_inventory.py \
  tests/test_n8n_test_run_errors.py::test_the_patch_turns_the_pinned_file_into_the_guarded_one
node --check apps/n8n/backend_policy.cjs
node --check tests/n8n_tool_result_probe.cjs
sh -n packaging/unit.sh
git diff --check
```

Focused pytest result: **12 passed**. Before applying the result patch, the
three response cases produced **one expected failure, two passes**: only
`success:false` lacked the required flag.

| Synthetic handler result | Expected MCP result |
| --- | --- |
| `success:true` | No error flag; original text |
| `success:false` with fake API error | `isError:true`; original text |
| `valid:false` from validate_workflow | No error flag; original text and structuredContent |

The response probe executes the entire tools/call callback extracted from the
pinned installed server in a Node VM. Handler, policy, logging, telemetry and
validation sanitizer collaborators are fakes; the VM has no require/network
facility. This verifies callback behavior, not a real n8n service or complete
MCP transport. The LiteLLM test compares registry metadata against the actual
handler AST. The remaining checks cover patch drift/idempotence/wiring,
inventory/provenance and preservation of the old handler patch.

The release team's 64 browser, 39 UI and 30 builder guard results belong to the
frozen 0.4.4 candidate; they were not rerun or claimed as acceptance of this
follow-up. Full hosted CI and any future release/image acceptance remain
separate.

## Integration relationship

This branch descends directly from the frozen candidate and changes none of
its integrated handlers. Four file paths also changed during 0.4.4 integration:
`apps/n8n/Dockerfile`, `docs/provenance/runtime-patches.json`,
`docs/provenance/runtime-sources.json` and `docs/tool-surface.json`. This work
preserves those integrated changes and adds only the corrections above.

There is no divergent merge against the frozen ancestor. Future release receipt
or provenance edits may still require reconciliation; no blanket claim of
conflict-free integration with later heads is made. Keep the PR draft and out
of 0.4.4. Rebase/retarget after PR34 lands, and ship only with a later release.
