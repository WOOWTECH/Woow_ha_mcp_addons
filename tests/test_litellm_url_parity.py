"""HA model and actual client joins; fake HTTP only, no live LiteLLM."""
import importlib.util
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from mcp_admin_core.products import LiteLLMConnection, NextcloudConnection, ProductStore

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reviewed_litellm_urls', ROOT / 'apps/litellm/vendor/woow_litellm_mcp_server/urls.py')
urls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(urls)


@pytest.mark.parametrize('raw,base,path', [
    ('http://lite.test/', 'http://lite.test', '/v1/models'),
    ('http://lite.test/v1', 'http://lite.test', '/v1/models'),
    ('http://lite.test/v1///', 'http://lite.test', '/v1/models'),
    ('http://lite.test/proxy/v1/', 'http://lite.test/proxy/v1', '/proxy/v1/v1/models'),
    ('http://lite.test/proxy/', 'http://lite.test/proxy', '/proxy/v1/models'),
    ('http://lite.test/V1/', 'http://lite.test/V1', '/V1/v1/models'),
    ('http://lite.test/%76%31/', 'http://lite.test/%76%31', '/%76%31/v1/models'),
])
async def test_model_child_root_and_route_agree(raw, base, path):
    conn = LiteLLMConnection(url=raw, master_key='fake-key')
    assert conn.url == urls.normalize_base_url(raw) == base
    seen = []
    def backend(request):
        seen.append(request.url.raw_path.decode())
        return httpx.Response(200, json={'data': []})
    async with httpx.AsyncClient(base_url=conn.url, transport=httpx.MockTransport(backend)) as client:
        await client.get('/v1/models')
        await client.get('/health/readiness')
    assert seen == [path, path.removesuffix('/v1/models') + '/health/readiness']


@pytest.mark.parametrize('bad', ['http://user:pass@lite.test/v1', 'http://lite.test/v1?x=1',
                               'http://lite.test/v1#frag', 'http://lite.test:bad/v1',
                               'http://lite.test/a\\v1', 'ftp://lite.test/v1'])
def test_model_preserves_existing_url_restrictions(bad):
    with pytest.raises(ValidationError):
        LiteLLMConnection(url=bad, master_key='fake-key')


def test_saved_connection_normalizes_only_litellm(tmp_path):
    store = ProductStore(tmp_path, 'litellm')
    try:
        store.update(connection={'url': 'http://lite.test/v1/', 'master_key': 'fake-key'})
        assert store.load().connection.url == 'http://lite.test'
        store.update(connection={'url': 'http://lite.test/proxy/v1/', 'master_key': 'fake-key'})
        assert store.load().connection.url == 'http://lite.test/proxy/v1'
    finally:
        store.close()
    other = NextcloudConnection(url='http://cloud.test/v1/', username='fake', app_password='fake-key')
    assert other.url == 'http://cloud.test/v1'
