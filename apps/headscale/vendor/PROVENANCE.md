# Headscale vendored child provenance

The native client, schemas, 29-operation registry, dispatcher and error model
were imported from `WOOWTECH/woow-mcp-server`,
`apps/headscale/headscale_mcp_server/`, at commit
`d7c78aaeff001f5fcf87f69ecd3db290396a5906` (the native contract files
were last changed in `690ed6a537968e2f107ff7c18f110bdf8cf6a6e8`).
`log_redaction.py` came from that commit's
`apps/headscale/headscale_mcp_admin/log_redaction.py`.

The source pins Headscale v0.29.4 at
`juanfont/headscale@8106636c7f8d0cf8c9d4fb0beae94415069b768b`.
The HA adaptation replaces the other repository's saved-policy reader with
per-call HA `ProductState` checks, uses HA `backend_policy.allowed_address`
at the pinned HTTPX/httpcore TCP seam, and launches on loopback via
`apps/headscale/launch.py`. `operation_policy.py` is the local subset needed
by the reviewed Headscale registry. No PaaS platform extension is included.

The source app's `pyproject.toml` declares MIT. `LICENSE` is the WOOWTECH MIT
text already shipped in that same repository's `apps/emqx/LICENSE`.
