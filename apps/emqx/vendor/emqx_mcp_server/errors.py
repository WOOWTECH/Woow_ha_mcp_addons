"""EMQX API failures, translated into messages an LLM can act on."""

from __future__ import annotations

import httpx
from fastmcp.exceptions import ToolError


class EmqxApiError(ToolError):
    """Raised for any EMQX REST API failure.

    ToolError messages are always forwarded verbatim to the model, so they
    are written as instructions rather than stack traces.
    """


async def emqx_request(
    client, method: str, path: str, **kwargs
) -> httpx.Response:
    """Call the EMQX REST API, converting failures into actionable errors."""
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as exc:
        raise EmqxApiError(
            f"EMQX timed out on {method} {path}. The broker may be busy — "
            "retry with a smaller `limit`."
        ) from exc
    except httpx.ConnectError as exc:
        raise EmqxApiError(
            "Cannot reach the EMQX broker. Check that the dashboard API "
            "(default port 18083) is running and reachable."
        ) from exc

    if response.status_code == 401:
        raise EmqxApiError(
            "EMQX rejected the API credentials (401). The configured API key "
            "or secret is wrong, expired, or disabled."
        )
    if response.status_code == 404:
        raise EmqxApiError(
            f"EMQX has no such resource: {method} {path}. "
            "Double-check the identifier — list the collection first."
        )
    if response.status_code >= 400:
        raise EmqxApiError(
            f"EMQX API error {response.status_code} on {method} {path}: "
            f"{response.text[:300]}"
        )
    return response


def json_body(response: httpx.Response) -> dict | list:
    """Parse a response body, tolerating EMQX's empty 204s."""
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}
