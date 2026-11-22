"""Server lifespan: owns the pooled httpx client to the LiteLLM gateway.

A single ``httpx.AsyncClient`` is created for the whole server process, with a
tuned connection pool and timeouts, and torn down on shutdown. Tools borrow a
non-closeable handle to it via :mod:`woow_litellm_mcp_server.deps`.

Important gotchas preserved from the reference architecture:
  * NO ``/api/v5`` suffix on the base URL (that is an EMQX-ism).
  * Bearer auth with the master key, NOT HTTP Basic auth.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
from backend_policy import async_client

from .settings import get_settings

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Key under which the pooled client lives in the lifespan context dict.
LITELLM_CLIENT_KEY = "litellm"


def build_client() -> httpx.AsyncClient:
    """Construct the pooled async client for the LiteLLM gateway."""
    cfg = get_settings()
    headers = {
        "Accept": "application/json",
        "User-Agent": "woow-litellm-mcp-server",
    }
    if cfg.master_key:
        headers["Authorization"] = f"Bearer {cfg.master_key}"

    timeout = httpx.Timeout(
        cfg.request_timeout,
        connect=min(10.0, cfg.request_timeout),
    )
    limits = httpx.Limits(
        max_connections=50,
        # HM-32 (PaaS #139): keep no idle connection. After a brief outage an
        # old pooled socket can look alive while the gateway no longer answers
        # on it, and reusing it makes the first tool call after the recovery
        # wait for the read timeout. Each request opens a fresh connection
        # instead (backend_policy resolves and checks the address again).
        # Nothing is retried, so an ambiguous write is never sent twice.
        # The pinned transport also keeps no idle connections.
        max_keepalive_connections=0,
    )
    return async_client(
        base_url=cfg.base_url,
        headers=headers,
        timeout=timeout,
        limits=limits,
        max_backend_connections=50,
        wait_for_resolver=True,
    )


@asynccontextmanager
async def lifespan(_server: "FastMCP") -> AsyncIterator[dict[str, Any]]:
    """FastMCP lifespan: yield a context dict holding the pooled client."""
    client = build_client()
    cfg = get_settings()
    logger.info("LiteLLM MCP server starting; upstream=%s", cfg.base_url)
    try:
        yield {LITELLM_CLIENT_KEY: client}
    finally:
        logger.info("LiteLLM MCP server shutting down; closing client")
        await client.aclose()
