"""Nextcloud HTTP client: one ``httpx.AsyncClient`` per server lifetime, lazily created."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from fastmcp.exceptions import ToolError

from . import __version__
from .errors import (
    AUTH_MESSAGE,
    NextcloudHTTPError,
    Operation,
    backend_error,
    status_message,
)
from .paths import encode_path
from .settings import Settings

logger = logging.getLogger("nextcloud_mcp_server")

USER_AGENT = f"woow-nextcloud-mcp-server/{__version__}"
CONNECT_TIMEOUT = 10.0
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_ERROR_BODY = 64 * 1024

PolicyFactory = Callable[..., Any]
# Everything httpx raises for a failed exchange (StreamError and InvalidURL are not
# HTTPError subclasses).
_HTTPX_ERRORS = (httpx.HTTPError, httpx.StreamError, httpx.InvalidURL)


class BodyTooLarge(ToolError):
    """The response body exceeded the cap given to :meth:`NextcloudClient.send`.

    It is a :class:`ToolError`, so a caller that does not handle it still produces a
    clean tool error; tools that want a more specific message catch it.
    """

    def __init__(self, limit: int, label: str | None = None) -> None:
        target = f' for "{label}"' if label else ""
        super().__init__(
            f"Nextcloud's answer{target} is larger than {limit} bytes and was not processed."
        )
        self.limit = limit


class BackendPolicyError(Exception):
    """The gateway's ``backend_policy`` module exists but cannot be used."""


@dataclass
class Reply:
    """A fully read (and size-capped) backend response."""

    status: int
    headers: httpx.Headers
    body: bytes


def _redirect_target(request_url: str, location: str | None) -> str:
    if not location:
        return "an unknown address"
    try:
        target = urlsplit(urljoin(request_url, location))
        host = target.hostname or ""
        port = f":{target.port}" if target.port else ""
    except ValueError:
        return "an unknown address"
    return f"{target.scheme}://{host}{port}{target.path}"


def load_backend_policy() -> PolicyFactory | None:
    """Return ``backend_policy.async_client`` when a gateway ships that module.

    ``None`` when no module named ``backend_policy`` exists. A module that exists but
    fails to import, or has no callable ``async_client``, raises
    :class:`BackendPolicyError`: a gateway that ships a policy must never silently get
    an unrestricted client instead.
    """
    try:
        module = importlib.import_module("backend_policy")
    except ModuleNotFoundError as exc:
        if exc.name == "backend_policy":
            return None
        raise BackendPolicyError(
            f"backend_policy could not be imported ({type(exc).__name__}: missing module "
            f"{exc.name!r})"
        ) from None
    except Exception as exc:
        raise BackendPolicyError(
            f"backend_policy could not be imported ({type(exc).__name__})"
        ) from None
    factory = getattr(module, "async_client", None)
    if not callable(factory):
        raise BackendPolicyError("backend_policy has no callable async_client(*, base_url, ...)")
    return factory


_UNSET: Any = object()


class NextcloudClient:
    """Thin async wrapper around the Nextcloud WebDAV/CalDAV/OCS endpoints of one account."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        policy: PolicyFactory | None = _UNSET,
    ) -> None:
        """``policy`` defaults to :func:`load_backend_policy`, resolved here (at start-up)."""
        self.settings = settings
        self._transport = transport
        self.policy: PolicyFactory | None = load_backend_policy() if policy is _UNSET else policy
        self._verify = settings.tls_verify()
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._user_id: str | None = None
        self._user_lock = asyncio.Lock()

    # -- lifecycle -----------------------------------------------------------------

    def client_kwargs(self) -> dict[str, Any]:
        """Keyword arguments used to build the HTTP client (plain or via ``backend_policy``)."""
        settings = self.settings
        kwargs: dict[str, Any] = {
            "auth": httpx.BasicAuth(settings.username, settings.app_password.get_secret_value()),
            "follow_redirects": False,
            "trust_env": False,
            "verify": self._verify,
            "timeout": httpx.Timeout(
                settings.request_timeout,
                connect=CONNECT_TIMEOUT,
            ),
            "headers": {"User-Agent": USER_AGENT},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return kwargs

    async def http(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it on first use (no request is made)."""
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                kwargs = self.client_kwargs()
                if self.policy is not None:
                    # WOOW HA add-on: the gateway's backend_policy.async_client sets follow_redirects and
                    # trust_env itself (passing them again is a TypeError) and owns the transport, whose TLS
                    # verification is always on: verify and a custom transport are not handed to it.
                    for key in ("follow_redirects", "trust_env", "transport", "verify"):
                        kwargs.pop(key, None)
                    client = self.policy(base_url=self.settings.base_url, **kwargs)
                    if inspect.isawaitable(client):
                        client = await client
                else:
                    client = httpx.AsyncClient(base_url=self.settings.base_url, **kwargs)
                self._client = client
        return self._client

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    # -- requests ------------------------------------------------------------------

    async def send(
        self,
        method: str,
        url: str,
        *,
        label: str,
        op: Operation,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        max_body: int | None = None,
        ok: tuple[int, ...] = (200, 201, 204, 207),
    ) -> Reply:
        """Send one request and return the size-capped body.

        Raises :class:`ToolError` for transport/protocol failures and redirects,
        :class:`NextcloudHTTPError` for statuses outside ``ok`` and :class:`BodyTooLarge`
        (also a ToolError) when the body exceeds ``max_body`` bytes (default
        :data:`MAX_XML_BYTES`).
        """
        client = await self.http()
        # WOOW HA add-on: any failure (not only httpx's) is reported by backend_error(), i.e. as a
        # backend_policy public code; redirects and unexpected statuses use fixed texts and the error body is
        # never read, so no backend text (Location, Sabre message) reaches a tool error.
        try:
            request = client.build_request(method, url, headers=headers, content=content)
            response = await client.send(request, stream=True)
        except Exception as exc:
            logger.warning("%s request failed: %s", method, type(exc).__name__)
            raise backend_error(exc, label, op) from None
        try:
            logger.debug("%s -> %s", method, response.status_code)
            if 300 <= response.status_code < 400:
                raise ToolError(
                    f"BACKEND_HTTP_ERROR status={response.status_code}: Nextcloud answered with a "
                    "redirect; set NEXTCLOUD_MCP_BASE_URL to the final address."
                )
            if response.status_code not in ok:
                if response.status_code == 401:
                    raise NextcloudHTTPError(AUTH_MESSAGE, 401)
                raise NextcloudHTTPError(
                    f"BACKEND_HTTP_ERROR status={response.status_code}: "
                    + status_message(response.status_code, label, op),
                    response.status_code,
                )
            limit = MAX_XML_BYTES if max_body is None else max_body
            try:
                body = await self._read_capped(response, limit)
            except BodyTooLarge:
                raise BodyTooLarge(limit, label) from None
            return Reply(status=response.status_code, headers=response.headers, body=body)
        except ToolError:
            raise
        except Exception as exc:
            logger.warning("%s response failed: %s", method, type(exc).__name__)
            raise backend_error(exc, label, op) from None
        finally:
            try:
                await response.aclose()
            except Exception as exc:  # the answer was already read or has already failed
                logger.warning("%s response close failed: %s", method, type(exc).__name__)

    @staticmethod
    async def _read_capped(
        response: httpx.Response, limit: int, *, tolerate: bool = False
    ) -> bytes:
        length = response.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > limit and not tolerate:
            raise BodyTooLarge(limit)
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                if tolerate:
                    break
                raise BodyTooLarge(limit)
            chunks.append(chunk)
        return b"".join(chunks)

    # -- account -------------------------------------------------------------------

    async def user_id(self) -> str:
        """The Nextcloud user id (may differ from the login name), resolved once."""
        if self._user_id is not None:
            return self._user_id
        async with self._user_lock:
            if self._user_id is None:
                self._user_id = await self._fetch_user_id()
        return self._user_id

    async def _fetch_user_id(self) -> str:
        url = f"{self.settings.base_url}/ocs/v2.php/cloud/user?format=json"
        try:
            reply = await self.send(
                "GET",
                url,
                label="account",
                op="read",
                headers={"OCS-APIRequest": "true", "Accept": "application/json"},
                max_body=1024 * 1024,
                ok=(200,),
            )
        except NextcloudHTTPError as exc:
            if exc.status == 401:
                raise
            raise ToolError(
                f"BACKEND_HTTP_ERROR status={exc.status}: Could not read the Nextcloud account; check "
                "NEXTCLOUD_MCP_BASE_URL points at the Nextcloud root."
            ) from None
        except BodyTooLarge:
            raise ToolError(
                "BACKEND_INVALID_RESPONSE: Nextcloud sent an unexpectedly large account answer."
            ) from None
        try:
            data = json.loads(reply.body)
            user_id = data["ocs"]["data"]["id"]
        except (ValueError, KeyError, TypeError):
            user_id = None
        if not isinstance(user_id, str) or not user_id:
            raise ToolError(
                "BACKEND_INVALID_RESPONSE: The address in NEXTCLOUD_MCP_BASE_URL did not answer like a "
                "Nextcloud server; check that it is the Nextcloud root URL."
            )
        return user_id

    async def probe(self) -> dict[str, Any]:
        """WOOW HA add-on: the gateway HealthMonitor's private readiness probe (woow_backend_probe).

        One fixed OCS GET (cloud/user) on a FRESH client built the same way as the tools' one (through
        backend_policy), closed afterwards: it never waits for or holds the tools' connections and never uses the
        cached user id. Answers only ok and the account's user id; failures are the tools' public errors.
        """
        fresh = NextcloudClient(self.settings, transport=self._transport, policy=self.policy)
        try:
            return {"ok": True, "user_id": await fresh._fetch_user_id()}
        finally:
            await fresh.aclose()

    # -- URLs ----------------------------------------------------------------------

    async def files_home(self) -> str:
        user = quote(await self.user_id(), safe="")
        return f"{self.settings.base_url}/remote.php/dav/files/{user}/"

    async def calendars_home(self) -> str:
        user = quote(await self.user_id(), safe="")
        return f"{self.settings.base_url}/remote.php/dav/calendars/{user}/"

    async def file_url(self, normalized: str) -> str:
        return await self.files_home() + encode_path(normalized)
