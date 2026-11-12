# Python base security update for HA MCP 0.4.8

## Finding and fixed base

The 2026-10-30 11:01 UTC full gate of the existing 0.4.8 Odoo candidate
(`8d34507c87d6169874c66142aca5982a2cdd1114`, image
`sha256:033424ac1ff06eb6b433b70f291585329d965d3bff56699923678a897dde90d9`)
rejected **binary Python 3.13.16**, matched to **CVE-2026-115557**, Critical,
with an available fix. The vulnerability database was within the unchanged
120-hour limit. This is the newly observed gate failure; the original 09:03
failure has insufficient retained evidence to assign the same cause.

The [PSF CVE record](https://github.com/CVEProject/cvelistV5/blob/main/cves/2026/115xxx/CVE-2026-115557.json)
identifies affected Python 3.13 versions before **3.13.18**. The
[PSF advisory](https://mail.python.org/archives/list/security-announce@python.org/message/FNAJMZV6XQYLVPABNINDMF3VF66AYLW4/)
describes rejection of known compromised certificates by the `ssl` module.

All eight source Dockerfiles use the same immutable Python base in their
dependency and runtime stages. This includes retained OpenDesign and retired
Odoo Manage source to satisfy the existing packaging contract. It does not
add either product to this release's six-image publication scope.

## Official registry metadata verified 2026-10-30 11:04 UTC

Anonymous Docker Hub GETs verified the response bytes against the index digest,
the index's linux/amd64 child digest and size, and the child config digest and
size. No authenticated customer credentials were used or saved.

| Object | Exact value |
| --- | --- |
| Official tag | `docker.io/library/python:3.13.18-slim-bookworm` |
| Index | `sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f` |
| Pinned linux/amd64 manifest | `sha256:70bda1e795ded2a684ef9815955e05829b14ee5bb5c3eb2a940648e88f10fce9` |
| Config | `sha256:b7ddb46f14cdb6312b0ac3816e0513fe55904bd66e4525b8845058d3c1aa0f79` |
| Config Python version | `3.13.18` |
| Config creation time | `2026-10-28T02:04:38.23058335Z` |
| Compressed layer sizes, total | `44197665` bytes |

The index annotation points to official docker-library/python source commit
[`152874b138f0b1c4699fbdcb52b174608cfbfff5`, `3.13/slim-bookworm`](https://github.com/docker-library/python/tree/152874b138f0b1c4699fbdcb52b174608cfbfff5/3.13/slim-bookworm).
This is a metadata verification, not a layer download, signature verification,
runtime acceptance, or vulnerability clearance.

## Scope and required release evidence

The update changes the shared Python base and matching Dockerfile references.
It preserves version 0.4.8, Nextcloud 0.1.6 dependencies, its `0383334` schema
provenance, application/UI source, existing OS security upgrades, and all
scanner, CVE, license and secret policies. No finding is exempted.

Regression tests reject a Python base below 3.13.18, require dependency/runtime
base consistency, and retain rejection of this fixed Critical vulnerability.
The old base fails the new minimum-version test.

The changed source must pass normal required CI and be frozen into new builder
inputs. All six images then require fresh build, full original gates, exact UI
and runtime checks, publication, anonymous verification and fresh remote layer
hash verification. Earlier source/image success receipts do not clear these
new artifacts. The old source, failed attempts and original images are retained.
