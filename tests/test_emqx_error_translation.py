"""Check the EMQX child using its own pinned environment, as CI does."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "apps" / "emqx" / ".venv" / "bin" / "python"
VENDOR = ROOT / "apps" / "emqx" / "vendor"
SCRIPT = r'''
import asyncio
import json
import httpx
from emqx_mcp_server.errors import emqx_request

CANARY = 'FAKE backend-private diagnostic'
class FakeClient:
    def __init__(self, status=None, error=None):
        self.status, self.error = status, error
    async def request(self, method, path, **kwargs):
        if self.error is not None:
            raise self.error('FAKE transport detail')
        return httpx.Response(self.status, text=CANARY,
                              request=httpx.Request(method, 'http://example.invalid' + path))

async def main():
    cases = {
        '302': (FakeClient(status=302), 'GET', '/api/v5/status'),
        '500': (FakeClient(status=500), 'GET', '/api/v5/status'),
        '503': (FakeClient(status=503), 'GET', '/api/v5/status'),
        'read_error': (FakeClient(error=httpx.ReadError), 'GET', '/api/v5/status'),
        'timeout': (FakeClient(error=httpx.ReadTimeout), 'DELETE', '/api/v5/resource'),
        '404': (FakeClient(status=404), 'GET', '/api/v5/private-topic'),
    }
    out = {}
    for name, (client, method, path) in cases.items():
        try:
            response = await emqx_request(client, method, path)
            out[name] = {'kind': 'response', 'status': response.status_code}
        except Exception as exc:
            out[name] = {'kind': type(exc).__name__, 'message': str(exc),
                         'status_code': getattr(exc, 'status_code', None)}
    print(json.dumps(out, sort_keys=True))
asyncio.run(main())
'''


@pytest.fixture(scope="module")
def cases():
    assert CHILD.is_file(), "CI must install the pinned apps/emqx environment first"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(VENDOR)
    result = subprocess.run([str(CHILD), "-c", SCRIPT], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


@pytest.mark.parametrize("status", [302, 500, 503])
def test_redirect_and_backend_errors_are_bounded(cases, status):
    observed = cases[str(status)]
    assert observed["kind"] == "EmqxApiError"
    assert observed["message"] == (
        "EMQX_REDIRECT_DENIED: configure the final broker URL"
        if status == 302 else f"EMQX_API_ERROR status={status}"
    )
    assert "FAKE backend-private diagnostic" not in observed["message"]


def test_read_error_is_translated_without_transport_detail(cases):
    observed = cases["read_error"]
    assert observed["kind"] == "EmqxApiError"
    assert observed["message"].startswith("EMQX_UNAVAILABLE:")
    assert "FAKE transport detail" not in observed["message"]


def test_timeout_warns_about_uncertain_write(cases):
    observed = cases["timeout"]
    assert observed["kind"] == "EmqxApiError"
    assert observed["message"].startswith("EMQX_TIMEOUT:")
    assert "Check state before repeating a write" in observed["message"]


def test_404_preserves_status_without_echoing_path(cases):
    observed = cases["404"]
    assert observed["kind"] == "EmqxApiError"
    assert observed["status_code"] == 404
    assert "/api/v5/private-topic" not in observed["message"]
