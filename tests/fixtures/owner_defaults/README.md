# Legacy state samples for the one-time all-on migration (2026-10-27)

Real formats, fake values. Each file is a `state.json` as the named code wrote it; then every token / child token was
replaced by a fixed low-entropy fake of the same format (`T`×43, `C`×43), every credential by a `DUMMY-…` string and
every URL by a `.invalid` host (a one-off normalization script, not part of this repository). Keys, policy fields and
schema are as written. No sample holds a real secret.

| Files | Written by |
|---|---|
| `schema1-n8n-313ab01.json` | commit 313ab01 (2026-10-03), the n8n tracer's `config.Store` (schema 1): backend set, `n8n_list_workflows` disabled, legacy write switch on |
| `schema2-<product>-313ab01.json` | commit 313ab01, `products.ProductStore` (schema 2, the only code that wrote it): connection set, first tool disabled, writes off |
| `schema3-<product>-v0.1.14-{fresh,max}.json` | tag v0.1.14 (`ProductStore`): a new state (writes off, no grant), and an administrator's maximum (writes on, every 0.1.x grant, first tool disabled; n8n none) |
| `schema3-hermes-ws97-0.1.14.json` | the real Hermes MCP add-on 0.1.14 on the test HAOS ws97 (2026-10-26, round 2 evidence 1-A-03): `hermes_skill` disabled, no write granted |
| `schema4-<product>-v0.2.2-max.json` | tag v0.2.2: a schema 4 state without `denied_operations` (added in 0.3.0) |
| `schema4-hermes-ws97-0.4.1-writes-off.json` | the real Hermes MCP add-on 0.4.1 on ws97 (round 2 evidence 1-B-07): schema 4, writes off |

The v0.1.14 and v0.2.2 files were generated offline with each tag's own code (their keys are sorted, as that generator
stored them); the ws97 files were rebuilt from masked dumps of the real add-on state (every key and policy value kept). Used by `tests/test_owner_defaults.py`.
