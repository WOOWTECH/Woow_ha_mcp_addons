"""Local hardening: bounded public errors, never raw upstream diagnostics.

Upstream MIT notice retained in vendor/LICENSE. Error bodies may echo master
keys or provider credentials. FastMCP ToolError is public even when masked.
"""
from __future__ import annotations

from typing import Any
import httpx
from fastmcp.exceptions import ToolError
from backend_policy import public_backend_error


class LiteLLMApiError(ToolError):
    """Stable public backend failure."""


def json_body(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except Exception:
        raise LiteLLMApiError('BACKEND_INVALID_RESPONSE') from None


async def litellm_request(client, method: str, path: str, *,
                          params: dict[str, Any] | None = None,
                          json_data: Any | None = None, **kwargs) -> httpx.Response:
    if params:
        params = {key: value for key, value in params.items() if value is not None}
    try:
        response = await client.request(method.upper(), path, params=params, json=json_data, **kwargs)
    except Exception as exc:
        raise LiteLLMApiError(public_backend_error(exc)) from None
    if not response.is_success:
        raise LiteLLMApiError(f'BACKEND_HTTP_ERROR status={response.status_code}')
    return response
