from contextlib import closing
import json

import httpx
import pytest

from mcp_admin_core.config import ConfigError
from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.migration import plan_migration
from mcp_admin_core.products import ProductStore, N8nSession
from n8n_adapter import TOOLS, child_spec


def test_old_state_is_not_rewritten_and_new_settings_survive_reopen(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        before = store.path.read_bytes()
        assert 'n8n_session' not in json.loads(before)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.path.read_bytes() == before
        assert store.load().effective_n8n_session.model_dump() == {'timeout_seconds': 600, 'max_sessions': 20}
        settings = {'timeout_seconds': 61, 'max_sessions': 3}
        state = store.update(n8n_session=settings)
        assert state.effective_n8n_session.timeout_minutes == 2
        assert plan_migration(state.model_dump(), 'n8n', policy='all_on').state.n8n_session.model_dump() == settings
        with pytest.raises(Exception):
            plan_migration({**state.model_dump(), 'n8n_session': None}, 'n8n', policy='all_on')
        with pytest.raises(ConfigError): store.update(n8n_session=None)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.load().n8n_session.model_dump() == settings
    with closing(ProductStore(tmp_path / 'wrong', 'odoo')) as store:
        with pytest.raises(ConfigError): store.update(n8n_session=settings)


@pytest.mark.parametrize('seconds,minutes', [(60, 1), (61, 2), (600, 10), (86400, 1440)])
def test_native_environment_rounds_up_like_paas(tmp_path, monkeypatch, seconds, minutes):
    from pathlib import Path
    monkeypatch.setattr(Path, 'is_file', lambda _: True)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        state = store.update(n8n_session={'timeout_seconds': seconds, 'max_sessions': 100})
        env = child_spec(state, tmp_path).env
        assert env['SESSION_TIMEOUT_MINUTES'] == str(minutes)
        assert env['N8N_MCP_MAX_SESSIONS'] == '100'


@pytest.mark.parametrize('value', [dict(timeout_seconds=True, max_sessions=20), dict(timeout_seconds=59, max_sessions=20),
    dict(timeout_seconds=86401, max_sessions=20), dict(timeout_seconds=60, max_sessions=0),
    dict(timeout_seconds=60, max_sessions=101), dict(timeout_seconds='60', max_sessions=20),
    dict(timeout_seconds=60, max_sessions=20, extra=1), dict(timeout_seconds=60)])
def test_invalid_limits_refused(value):
    with pytest.raises(ValueError): N8nSession.model_validate(value)


async def test_session_api_requires_revision_and_reports_saved_values(tmp_path):
    restarts = []
    async def verify(_): return True
    async def restart(state): restarts.append(state.effective_n8n_session)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS, child, verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                assert boot.json()['n8n_session_source'] == 'legacy_default'
                headers = {**identity, 'x-csrf-token': boot.json()['csrf']}
                payload = {'n8n_session': {'timeout_seconds': 901, 'max_sessions': 30}}
                assert (await client.put('/api/n8n/session', headers=headers, json=payload)).status_code == 428
                headers['if-match'] = boot.headers['etag']
                assert (await client.put('/api/n8n/session', headers=headers, json=payload)).status_code == 200
                assert len(restarts) == 1
                assert (await client.put('/api/n8n/session', headers=headers, json=payload)).status_code == 409
                fresh = (await client.get('/api/bootstrap', headers=identity)).json()
                assert fresh['n8n_session'] == payload['n8n_session']
                assert fresh['n8n_session_effective_minutes'] == 16
                assert fresh['n8n_session_source'] == 'saved'


def test_launch_revision_tracks_effective_native_settings(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        tracker = ConfigurationState(store)
        default = tracker.launch_revision(store.load())
        state = store.update(n8n_session={'timeout_seconds': 600, 'max_sessions': 20})
        assert tracker.launch_revision(state) == default
        state = store.update(n8n_session={'timeout_seconds': 601, 'max_sessions': 20})
        assert tracker.launch_revision(state) != default
