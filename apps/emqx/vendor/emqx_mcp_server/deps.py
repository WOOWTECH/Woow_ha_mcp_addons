"""Dependency-injection helpers.

Parameters resolved through `Depends` are stripped from the JSON Schema, so
the model never sees (or can override) the HTTP client.

Why the handle exists: FastMCP's DI enters and exits anything the provider
returns that looks like an async context manager. Returning the pooled
`httpx.AsyncClient` therefore closed it as soon as the first tool finished,
and the second tool in the same session died with "Cannot reopen a client
instance, once it has been closed". An async generator does not help either —
this FastMCP passes the generator object straight through. So the provider
hands back a plain object that owns nothing and is not a context manager.
`tests/test_client_lifetime.py` pins the behaviour.

HA multi-profile HM-23 (PaaS #153, woow-mcp-server 4b4fd16 and 574c805; there in BrokerClient.request): every tool's
request goes through EmqxHttp.request, so this is where a request is refused before any I/O when it asks for another
Accept value than the two a tool uses, passes any other request option, or carries a URL httpx would not build.
"""

from __future__ import annotations

from typing import Any

import httpx
from backend_policy import BackendDenied
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context

# The only Accept values a request may carry: JSON for every tool, plain text for emqx_prometheus_stats (EMQX answers
# GET /prometheus/stats with the Prometheus exposition text only to 'text/plain', with JSON statistics otherwise).
ACCEPT_JSON = "application/json"
ACCEPT_TEXT = "text/plain"
# The request options a tool passes (every other one, headers included, is refused before any I/O).
REQUEST_OPTIONS = frozenset({"params", "json", "content", "data"})
# httpx refuses any URL or URL component longer than this (httpx._urlparse.MAX_URL_LENGTH, pinned with httpx 0.28.1).
MAX_URL_CHARS = 65536


class EmqxHttp:
    """A borrowed reference to the pooled client. Deliberately not closeable."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(self, method: str, url: str, *, accept: str = ACCEPT_JSON, **kwargs: Any) -> httpx.Response:
        """One request to the broker. Refused before any I/O with backend_policy.BackendDenied, which emqx_request
        answers with the fixed EMQX_DESTINATION_DENIED: another Accept value or request option; a URL longer than
        httpx builds (before anything looks at it); a request httpx cannot build, because a URL part is too long once
        encoded or a value cannot be encoded (a lone surrogate in a path, query or JSON value). Those two are not
        httpx.HTTPError: they used to escape as a traceback and FastMCP's masked "Error calling tool" (PaaS #153)."""
        if accept not in (ACCEPT_JSON, ACCEPT_TEXT) or set(kwargs) - REQUEST_OPTIONS:
            raise BackendDenied()
        if len(str(url)) > MAX_URL_CHARS:
            raise BackendDenied()
        try:
            request = self._client.build_request(method, url, headers={"Accept": accept}, **kwargs)
        except (httpx.InvalidURL, UnicodeError):
            raise BackendDenied() from None
        return await self._client.send(request)

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    @property
    def timeout(self) -> httpx.Timeout:
        return self._client.timeout


def emqx_client() -> EmqxHttp:
    """The pooled EMQX client for the current request."""
    try:
        client = get_context().lifespan_context["emqx"]
    except (RuntimeError, KeyError, TypeError) as exc:
        raise ToolError(
            "The EMQX connection is not initialised. Restart the MCP server "
            "from the Admin console and try again."
        ) from exc

    if client.is_closed:
        raise ToolError(
            "The EMQX connection was closed unexpectedly. Restart the MCP "
            "server from the Admin console and try again."
        )
    return EmqxHttp(client)
