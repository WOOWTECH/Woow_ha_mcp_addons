"""The HA EMQX child must not expose backend bodies or accept redirects as success."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "emqx" / "vendor"))
from emqx_mcp_server.errors import EmqxApiError, emqx_request  # noqa: E402


class FakeClient:
    def __init__(self, *, status: int | None = None, error: type[Exception] | None = None):
        self.status = status
        self.error = error

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self.error is not None:
            raise self.error("FAKE transport detail")
        return httpx.Response(
            self.status,
            text="FAKE backend-private diagnostic",
            request=httpx.Request(method, "http://example.invalid" + path),
        )


@pytest.mark.parametrize("status", [302, 500, 503])
async def test_redirect_and_backend_errors_are_bounded(status):
    with pytest.raises(EmqxApiError) as caught:
        await emqx_request(FakeClient(status=status), "GET", "/api/v5/status")
    message = str(caught.value)
    assert message == (
        "EMQX_REDIRECT_DENIED: configure the final broker URL"
        if status == 302 else f"EMQX_API_ERROR status={status}"
    )
    assert "FAKE backend-private diagnostic" not in message


async def test_read_error_is_translated_without_transport_detail():
    with pytest.raises(EmqxApiError, match="EMQX_UNAVAILABLE") as caught:
        await emqx_request(FakeClient(error=httpx.ReadError), "GET", "/api/v5/status")
    assert "FAKE transport detail" not in str(caught.value)


async def test_timeout_warns_about_uncertain_write():
    with pytest.raises(EmqxApiError, match="EMQX_TIMEOUT") as caught:
        await emqx_request(FakeClient(error=httpx.ReadTimeout), "DELETE", "/api/v5/resource")
    assert "Check state before repeating a write" in str(caught.value)


async def test_404_preserves_status_without_echoing_path():
    with pytest.raises(EmqxApiError) as caught:
        await emqx_request(FakeClient(status=404), "GET", "/api/v5/private-topic")
    assert caught.value.status_code == 404
    assert "/api/v5/private-topic" not in str(caught.value)
