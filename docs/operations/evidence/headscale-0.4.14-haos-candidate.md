# Headscale 0.4.14 isolated HAOS candidate acceptance

- Date: 2026-11-11 UTC.
- Namespace: `hsstore-acceptance-20261111-a46c42`; namespace UID `e9564eb7-b3aa-44b8-85b9-f9f4975e3357`.
- VM: `hsstore-acceptance`; VM UID `91b8653e-de2e-47d0-a6e3-3cbf9b9a7cb9`.
- HAOS 18.3; Core 2026.11.1; Supervisor 2026.10.5.
- Public candidate: `ghcr.io/woowtech/amd64-mcp-headscale:0.4.14`; manifest digest `sha256:c3099fc3398ffa8c5491edb8d728978f1f87f5a7592cd032eacddb8c8086ac92`.
- Local add-on slug: `local_woow_mcp_headscale`; Supervisor version 0.4.14; state `started`.
- Owner ingress: management HTML 200, JavaScript asset 200, `/api/bootstrap` 200; bootstrap `capabilities.product.version` = 0.4.14.
- Anonymous `/api/bootstrap`: 401.
- Ordinary user: Core account creation and password login passed; no admin group; Supervisor issued an ingress session; `/api/bootstrap` returned 403.
- Isolation: fresh VM and synthetic owner; no production Headscale backend token or target. Local candidate and Store 0.4.13 remain separate slugs.

The private HA auth material was held outside the repository and will be destroyed with the test VM. The Store-installed upgrade from 0.4.13 to 0.4.14 is pending stable source release and Store sync.
