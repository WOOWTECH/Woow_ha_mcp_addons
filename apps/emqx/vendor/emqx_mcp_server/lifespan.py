"""One pooled httpx client for the whole server lifetime."""

from __future__ import annotations

import httpx
from backend_policy import async_client
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from .settings import settings


def make_client() -> httpx.AsyncClient:
    return async_client(
        base_url=f"{settings.base_url.rstrip('/')}/api/v5",
        auth=(settings.api_key, settings.api_secret),
        timeout=httpx.Timeout(
            connect=5.0, read=settings.request_timeout, write=10.0, pool=5.0
        ),
        # HM-32 (PaaS #135): keep no idle connection. After a brief outage an
        # old pooled socket can look alive while the broker no longer answers
        # on it, and reusing it makes the first request after the recovery
        # wait for the read timeout. Each request opens a fresh connection
        # instead (backend_policy resolves and checks the address again).
        # Nothing is retried, so an ambiguous write is never sent twice.
        # backend_policy's transport builds its own pool with the same rule.
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=0),
        headers={"Accept": "application/json"},
    )


@lifespan
async def emqx_lifespan(server: FastMCP):
    client = make_client()
    try:
        yield {"emqx": client}
    finally:
        await client.aclose()
