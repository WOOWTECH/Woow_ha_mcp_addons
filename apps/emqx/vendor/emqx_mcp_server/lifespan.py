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
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        headers={"Accept": "application/json"},
    )


@lifespan
async def emqx_lifespan(server: FastMCP):
    client = make_client()
    try:
        yield {"emqx": client}
    finally:
        await client.aclose()
