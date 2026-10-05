# Licenses and notices for the published 0.1.0 images

Applies to the seven images `ghcr.io/woowtech/amd64-mcp-<product>:0.1.0` built from source
`f75fe32b2f79b4cf9f99563667439a94db8b1d82`. The project's own code is Apache-2.0 (see `LICENSE`).

## Bundled third-party packages

Each image bundles third-party packages that keep their own licenses. Per-image inventories, generated
from the supply-chain gate's SBOM of the exact published image:

| Product | Inventory |
|---|---|
| n8n | [n8n-0.1.0.md](n8n-0.1.0.md) |
| Odoo | [odoo-0.1.0.md](odoo-0.1.0.md) |
| Odoo Manage | [odoo-manage-0.1.0.md](odoo-manage-0.1.0.md) |
| Hermes | [hermes-0.1.0.md](hermes-0.1.0.md) |
| OpenDesign | [opendesign-0.1.0.md](opendesign-0.1.0.md) |
| EMQX | [emqx-0.1.0.md](emqx-0.1.0.md) |
| LiteLLM | [litellm-0.1.0.md](litellm-0.1.0.md) |

License texts ship inside every image: Python `*.dist-info/licenses/`, Node `node_modules/*/LICENSE*`,
Debian `/usr/share/doc/*/copyright`, and the repository files `THIRD_PARTY_NOTICES.md` and
`docs/provenance/` copied to `/opt/woow/`.

The supply-chain license policy (`packaging/supply-chain-policy.json`) records the project owner's
decisions of 2026-10-05: Debian main package licenses accepted, pure OR expressions with an allowed option
accepted, MIT-0 and BlueOak-1.0.0 allowed, and version-pinned licenses for three packages whose metadata
is missing or non-SPDX but whose shipped license text was checked (exceptiongroup 1.3.1 MIT,
markdown-it-py 4.2.0 MIT, pyperclip 1.11.0 BSD-3-Clause).

## MPL-2.0 source (Odoo Manage)

The Odoo Manage image bundles `mcp-server-odoo` 0.7.1 (MPL-2.0). Its exact Source Code Form is attached
to the GitHub release `v0.1.0` of this repository as `mcp_server_odoo-0.7.1.tar.gz`
(SHA256 `4d3c2a71db22adb9c7e59fe5696600c4c42e0a3414880c5d00ec345c4963c67b`, identical to the PyPI sdist).
The upstream files are not edited; this project's launcher and helpers that change its runtime behaviour are
in this repository under Apache-2.0 and are described in `THIRD_PARTY_NOTICES.md`.

## Known open item

OpenDesign: the original upstream rights holder is not yet confirmed (see
`docs/provenance/opendesign-upstream-chain.md`). The project owner accepted publishing 0.1.0 with this item
open on 2026-10-05. Report rights questions through the repository issues.
