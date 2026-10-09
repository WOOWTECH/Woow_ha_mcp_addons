# Build from repository ROOT: docker build -f apps/emqx/Dockerfile .
FROM node:22.23.2-bookworm-slim@sha256:43aeff40f4afc22e83f7589a2f37e111cff5ca84529571f1c8415bcc5fcc21b2 AS ui
WORKDIR /ui
COPY packages/mcp-admin-ui/package.json packages/mcp-admin-ui/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY packages/mcp-admin-ui/src ./src
COPY packages/mcp-admin-ui/scripts/build.mjs ./scripts/build.mjs
COPY packages/mcp-admin-ui/NOTICE.txt ./NOTICE.txt
RUN npm run build
FROM astral/uv:0.12.10@sha256:34c0f9a55abeb840c34391bb7b63a1a06f8cb9281e028f27757a01a1a8a2d461 AS uv
FROM python:3.13.16-slim-bookworm@sha256:f040863673aea2570c3ff6a5c3fb4c673a016cbc5375005ad145915922b6b78a AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /opt/woow
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --python /usr/local/bin/python
COPY apps/emqx/pyproject.toml apps/emqx/uv.lock ./apps/emqx/
RUN uv sync --project apps/emqx --frozen --no-dev --python /usr/local/bin/python
FROM python:3.13.16-slim-bookworm@sha256:f040863673aea2570c3ff6a5c3fb4c673a016cbc5375005ad145915922b6b78a AS runtime
ARG BUILD_VERSION=0.1.7
LABEL io.hass.type="app" io.hass.arch="amd64" io.hass.version="${BUILD_VERSION}" \
      io.hass.name="Woow EMQX MCP Server" io.hass.description="Experimental; HA admin-role management; partial tools, read-only by default." \
      io.hass.url="https://github.com/WOOWTECH/Woow_ha_mcp_addons" \
      org.opencontainers.image.source="https://github.com/WOOWTECH/Woow_ha_mcp_addons" \
      org.opencontainers.image.version="${BUILD_VERSION}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/woow/packages/mcp-admin-core:/opt/woow/apps/n8n \
    PATH=/usr/local/bin:/usr/bin:/bin
WORKDIR /opt/woow
COPY --from=dependencies /opt/woow/.venv ./.venv
COPY packages/mcp-admin-core ./packages/mcp-admin-core
COPY --from=ui /ui/dist ./packages/mcp-admin-ui/dist
COPY apps/runtime ./apps/runtime
COPY apps/emqx ./apps/emqx
COPY --from=dependencies /opt/woow/apps/emqx/.venv ./apps/emqx/.venv
COPY packaging/entrypoint.py packaging/management_launcher.py ./packaging/
COPY THIRD_PARTY_NOTICES.md ./THIRD_PARTY_NOTICES.md
COPY docs/provenance ./docs/provenance
RUN /usr/sbin/groupadd --gid 10001 mcp && /usr/sbin/useradd --uid 10001 --gid 10001 --no-create-home --home-dir /data/mcp --shell /usr/sbin/nologin mcp
# Root ONLY for no-follow creation/ownership of a NEW /data/mcp, then irreversible uid/gid drop.
# Supervisor-owned options are never chowned; an existing tree only in the verified HA-restore
# repair (packaging/entrypoint.py). No backend-dependent watchdog.
EXPOSE 8081
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/python", "/opt/woow/packaging/entrypoint.py", "emqx"]
