# nextcloud 0.1.7 (not yet released) — bundled Python packages from the lock

**Not an image SBOM.** No Nextcloud image exists yet. This list is the installed closure of `apps/nextcloud/uv.lock`
(the reviewed EMQX lock plus `defusedxml` 0.7.1 and `tzdata` 2026.5), read from each package's installed metadata;
the supply-chain gate's syft SBOM of the first built image replaces it (`nextcloud-0.1.7.md`), together with the
Debian packages and binaries of the pinned base image, which are the same as for the other products.

`defusedxml` 0.7.1 records `PSFL` (not an SPDX id); its shipped LICENSE is the Python Software Foundation License 2.
If syft reports `PSFL`, the license gate needs an owner-approved, version-pinned `known_package_licenses` entry
(`python:defusedxml:0.7.1` = `PSF-2.0`); it has **not** been added.

| package | version | license expression / metadata | classifiers | license files in dist-info |
|---|---|---|---|---|
| aiofile | 3.12.3 | Apache-2.0 | Apache Software License | LICENCE, LICENCE.md |
| annotated-types | 0.8.0 | MIT | MIT License | LICENSE |
| anyio | 4.15.1 | MIT | — | LICENSE |
| attrs | 26.1.0 | MIT | — | LICENSE |
| Authlib | 1.8.0 | BSD-3-Clause | BSD License | LICENSE |
| beartype | 0.22.9 | (none) | MIT License | LICENSE |
| cachetools | 7.2.0 | MIT | — | LICENSE |
| caio | 0.12.9 | Apache-2.0 | — | COPYING |
| certifi | 2026.7.22 | MPL-2.0 | Mozilla Public License 2.0 (MPL 2.0) | LICENSE |
| cffi | 2.1.1 | MIT-0 | — | LICENSE |
| click | 8.5.0 | BSD-3-Clause | — | LICENSE.txt |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | — | LICENSE, LICENSE.APACHE, LICENSE.BSD |
| cyclopts | 5.1.1 | Apache-2.0 | Apache Software License | LICENSE |
| defusedxml | 0.7.1 | PSFL | Python Software Foundation License | LICENSE |
| dnspython | 2.8.0 | ISC | ISC License (ISCL) | LICENSE |
| docstring_parser | 0.18.0 | MIT | MIT License | LICENSE.md |
| email-validator | 2.3.0 | Unlicense | The Unlicense (Unlicense) | LICENSE |
| exceptiongroup | 1.3.1 | (none) | MIT License | LICENSE |
| fastmcp | 3.4.5 | Apache-2.0 | Apache Software License | LICENSE |
| fastmcp-slim | 3.4.5 | Apache-2.0 | Apache Software License | — |
| griffelib | 2.3.0 | ISC | — | LICENSE |
| h11 | 0.16.0 | MIT | MIT License | LICENSE.txt |
| httpcore | 1.0.9 | BSD-3-Clause | BSD License | LICENSE.md |
| httpx | 0.28.1 | BSD-3-Clause | BSD License | LICENSE.md |
| httpx-sse | 0.4.3 | MIT | — | LICENSE |
| idna | 3.20 | BSD-3-Clause | — | LICENSE.md |
| jaraco.classes | 3.4.0 | (none) | MIT License | LICENSE |
| jaraco.context | 6.1.2 | MIT | — | LICENSE |
| jaraco.functools | 4.6.0 | MIT | — | LICENSE |
| jeepney | 0.9.0 | MIT | — | LICENSE |
| joserfc | 1.7.5 | BSD-3-Clause | BSD License | LICENSE |
| jsonref | 1.1.0 | MIT | — | LICENSE |
| jsonschema | 4.26.0 | MIT | — | COPYING |
| jsonschema-path | 0.5.0 | Apache-2.0 | Apache Software License | LICENSE |
| jsonschema-specifications | 2025.9.1 | MIT | — | COPYING |
| keyring | 25.7.0 | MIT | — | LICENSE |
| markdown-it-py | 4.2.0 | (none) | MIT License | LICENSE, LICENSE.markdown-it |
| mcp | 1.28.1 | MIT | MIT License | LICENSE |
| mdurl | 0.1.2 | (none) | MIT License | LICENSE |
| more-itertools | 11.1.0 | MIT | — | LICENSE |
| openapi-pydantic | 0.6.0 | MIT | MIT License | LICENSE, license.py |
| opentelemetry-api | 1.45.0 | Apache-2.0 | — | LICENSE |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | — | LICENSE, LICENSE.APACHE, LICENSE.BSD, __init__.py, _spdx.py |
| pathable | 0.6.0 | Apache-2.0 | Apache Software License | LICENSE |
| platformdirs | 4.12.2 | MIT | MIT License | LICENSE |
| py-key-value-aio | 0.4.6 | Apache-2.0 | — | LICENSE |
| pycparser | 3.0 | BSD-3-Clause | — | LICENSE |
| pydantic | 2.13.5 | MIT | — | LICENSE |
| pydantic-settings | 2.15.0 | MIT | MIT License | LICENSE |
| pydantic_core | 2.46.5 | MIT | — | LICENSE |
| Pygments | 2.21.0 | BSD-2-Clause | — | AUTHORS, LICENSE |
| PyJWT | 2.15.1 | MIT | — | AUTHORS.rst, LICENSE |
| pyperclip | 1.11.0 | BSD | BSD License | AUTHORS.txt, LICENSE.txt |
| python-dotenv | 1.2.4 | BSD-3-Clause | — | LICENSE |
| python-multipart | 0.0.32 | Apache-2.0 | Apache Software License | LICENSE.txt |
| PyYAML | 6.0.3 | MIT | MIT License | LICENSE |
| referencing | 0.37.0 | MIT | — | COPYING |
| rich | 15.0.0 | MIT | MIT License | LICENSE |
| rich-rst | 2.2.0 | MIT | — | LICENSE, LICENSES.txt |
| rpds-py | 2026.6.3 | MIT | — | LICENSE |
| SecretStorage | 3.5.0 | BSD-3-Clause | — | LICENSE |
| sse-starlette | 3.5.0 | BSD-3-Clause | — | AUTHORS, LICENSE |
| starlette | 1.7.0 | BSD-3-Clause | — | LICENSE.md |
| typing-inspection | 0.4.4 | MIT | — | LICENSE |
| typing_extensions | 4.16.0 | PSF-2.0 | — | LICENSE |
| tzdata | 2026.5 | Apache-2.0 | — | LICENSE, LICENSE_APACHE |
| uncalled-for | 0.4.0 | (none) | MIT License | LICENSE |
| uvicorn | 0.54.0 | BSD-3-Clause | — | LICENSE.md |
| watchfiles | 1.3.0 | MIT | MIT License | LICENSE |
| websockets | 17.1 | BSD-3-Clause | — | LICENSE |
