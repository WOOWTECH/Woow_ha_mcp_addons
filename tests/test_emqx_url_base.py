"""EMQX connection URL: a pasted ".../api/v5" root is saved without it, because the child appends /api/v5 itself.

The PaaS server accepts both spellings too (apps/emqx/emqx_mcp_server/http_policy.py normalize_base_url). Anything else in the path that
contains /api/v5 is refused. Fake data only."""
import pytest
from pydantic import ValidationError
from mcp_admin_core.products import EmqxConnection, ProductStore


@pytest.mark.parametrize('raw,saved', [
    ('https://broker.test', 'https://broker.test'),
    ('https://broker.test/', 'https://broker.test'),
    ('https://broker.test/api/v5', 'https://broker.test'),
    ('https://broker.test/api/v5/', 'https://broker.test'),
    ('https://broker.test:8443/emqx/api/v5', 'https://broker.test:8443/emqx'),
    ('http://192.0.2.7:18083/api/v5', 'http://192.0.2.7:18083'),
    ('https://api/v5', 'https://api/v5'),  # a host called "api" with the path /v5 is not the suffix
])
def test_pasted_api_root_is_saved_without_the_suffix(raw, saved):
    assert EmqxConnection(url=raw, api_key='fake-key', api_secret='fake-secret').url == saved


@pytest.mark.parametrize('bad', ['https://broker.test/api/v5/api/v5', 'https://broker.test/api/v5/status', 'https://broker.test/x/api/v5/y',
                                 'https://user:pass@broker.test/api/v5', 'https://broker.test/api/v5?x=1', 'ftp://broker.test/api/v5'])
def test_other_api_paths_and_the_old_url_restrictions_stay_refused(bad):
    with pytest.raises(ValidationError):
        EmqxConnection(url=bad, api_key='fake-key', api_secret='fake-secret')


def test_saved_connection_has_the_base_only(tmp_path):
    store = ProductStore(tmp_path, 'emqx')
    try:
        store.update(connection={'url': 'https://broker.test/api/v5/', 'api_key': 'fake-key', 'api_secret': 'fake-secret'})
        assert store.load().connection.url == 'https://broker.test'
    finally:
        store.close()
