# 0.4.13 image publication

Status: **six exact-source images published and independently verified**. Final PR checks, merge and Store distribution are separate gates.

PR #76 image source: `4966f40f53d176b285d18bb8948b8a52679ae95b`; tree `8ced51f7575de7a53f66701ff777cee9784d6ffd`. Approved plan SHA-256: `d39e7fc3779a8b4ed3d57f6bec49208a95874f4c16e551a76c86067f96ec4fda`. The later documentation commit is not the image source.

The source CI passed 3534 Python tests, 71 browser tests and 174 packaging tests. The independent exact-source UI receipt passed 57 unit tests and 71 browser tests.

All six enabled linux/amd64 images passed P1–P5 and packaged-runtime probes using owned mocks. The accepted 0.4.12 image IDs were verified read-only. Each new image was anonymously verified by immutable digest; the remote-layer proof checked compressed digests, sizes and uncompressed diffIDs without a Docker layer cache. OpenDesign remains disabled.

Before publication, readiness failed only for six missing images and six absent decision-record checks; both Upgrade comparison jobs failed only for unpublished images. The post-publication PR head must pass **all required checks**, including the first real Upgrade comparison and runtime upgrade test, before merge. LiteLLM Enterprise-only key rotation is excluded from the agreed live-test scope.

See [image provenance](../provenance/release-0.4.13-images.json) and [remote layer proof](../provenance/release-0.4.13-remote-layers.json).

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:7ca917f3d034344357ee7b38360aa457dee5f68e20aa2da95d1a04ced1903786` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:846d02c97dd64a14c0ac1d976c8d5bacece8267e104a306a7121e430a358928c` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:6a10ffe19dcf7b4a61e3be0fb22d9b39ab65f4a00c14a69cd200f4f6bc130eea` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:e6b1cce3b9aa17f3bc96811e3e6f3ba8b7c1262e8bf164c7111ba48bf5619a5e` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:628e4f32d199639bd5b7dbff3579c3424804ce852fb5c54a4eaff313af7192ca` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:4c24074798f09ac2bf60a424e6bb5a53daac24251615c77dde30c65d40d93e90` |

This publication does not claim HAOS, production backend, or Store acceptance. Those require separate evidence after the normal protected-branch merge.
