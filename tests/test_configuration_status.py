"""Saved state, actual child generation, and conditional admin edits (owned mocks)."""
from admin_write_headers import reviewed_headers
import asyncio
from types import SimpleNamespace
from contextlib import closing

import httpx
import pytest

from mcp_admin_core.config import ConfigError
from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_real_products import connection
from test_management_capabilities import setup


async def test_bootstrap_revision_is_the_form_snapshot_and_stale_save_is_inert(tmp_path):
    async with setup(tmp_path) as (store, record, client, headers, admin, boot):
        first = await client.get('/api/bootstrap', headers=headers)
        revision = first.json()['configuration']['revision']
        assert first.headers['etag'] == '"' + revision + '"'
        conditional = {**headers, 'if-match': first.headers['etag']}
        assert (await client.put('/api/endpoint', headers=conditional,
                                 json={'endpoint': 'https://one.example/mcp'})).status_code == 200
        saved = store.path.read_bytes()
        denied = await client.put('/api/backend', headers=conditional, json={'url': None, 'key': None})
        assert denied.status_code == 409
        assert denied.json()['detail']['code'] == 'config_conflict'
        assert store.path.read_bytes() == saved and record['restart'] == 0
        # A legacy request without the reviewed revision is now explicitly refused.
        legacy = {k:v for k,v in headers.items() if k.lower() != 'if-match'}
        assert (await client.put('/api/endpoint', headers=legacy, json={'endpoint': None})).status_code == 428


async def test_save_acknowledgement_does_not_claim_child_readiness(tmp_path):
    async with setup(tmp_path) as (_, _, client, headers, _, _):
        result = await client.put('/api/backend', headers=headers,
                                  json={'url': 'https://n8n.example', 'key': 'synthetic-only'})
        assert result.status_code == 200 and result.json()['saved'] is True
        assert result.json()['configuration']['apply_state'] == 'unknown'
        assert result.json()['configuration']['applied_revision'] is None


@pytest.mark.parametrize('product', ['n8n', 'hermes', 'odoo', 'odoo-manage', 'opendesign', 'emqx', 'litellm', 'nextcloud'])
async def test_every_product_connection_route_rejects_second_editor_before_replacement(tmp_path, product):
    async def verify(_): return True
    replaced = []
    async def replace(state): replaced.append(state)
    with closing(ProductStore(tmp_path, product)) as store:
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child,
                                 verify_admin=verify, backend_changed=replace)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'owned-editor'}
                boot = await client.get('/api/bootstrap', headers=identity)
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                payload = {'url': 'https://first.example', 'key': 'SYNTHETIC'} if product == 'n8n' else {
                    'connection': connection(product, 'https://first.example')}
                saved = await client.put('/api/backend', headers=headers, json=payload)
                assert saved.status_code == 200 and len(replaced) == 1
                first_bytes = store.path.read_bytes()
                rejected = await client.put('/api/backend', headers=headers, json=payload)
                assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'config_conflict'
                assert store.path.read_bytes() == first_bytes and len(replaced) == 1
                fresh = await client.get('/api/configuration', headers=identity)
                assert fresh.headers['etag'] == saved.headers['etag']
                assert fresh.json()['configuration'] == saved.json()['configuration']


async def test_two_simultaneous_editors_have_exactly_one_commit(tmp_path):
    async with setup(tmp_path) as (store, _, client, headers, _, boot):
        conditional = {**headers, 'if-match': '"' + boot['configuration']['revision'] + '"'}
        results = await asyncio.gather(*(client.put('/api/endpoint', headers=conditional,
            json={'endpoint': 'https://' + name + '.example/mcp'}) for name in ('first', 'second')))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(i for i, result in enumerate(results) if result.status_code == 200)
        assert store.load().endpoint == 'https://' + ('first', 'second')[winner] + '.example/mcp'


async def test_commit_failure_preserves_revision_and_never_restarts(tmp_path, monkeypatch):
    async with setup(tmp_path) as (store, record, client, headers, _, boot):
        def failed(**changes): raise ConfigError('synthetic commit error')
        original = store.path.read_bytes()
        monkeypatch.setattr(store, 'update', failed)
        response = await client.put('/api/backend', headers=headers, json={'url': None, 'key': None})
        assert response.status_code == 503
        assert store.path.read_bytes() == original and record['restart'] == 0
        after = await client.get('/api/bootstrap', headers=headers)
        assert after.json()['configuration'] == boot['configuration']


async def test_saved_but_failed_application_is_explicit_and_secret_free(tmp_path):
    async with setup(tmp_path) as (store, _, _, _, _, _):
        process = SimpleNamespace(starts=1, status='running')
        health = SimpleNamespace(settled=(1, True, 'reachable', None))
        tracker = ConfigurationState(store, process, health)
        async def replace(state):
            tracker.begin(state)
            process.status = 'failed'
            tracker.failed('child_start_failed')
            raise RuntimeError('PRIVATE_CREDENTIAL_CANARY')
        async def verify(_): return True
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, N8N_TOOLS, child, configuration=tracker,
                                 verify_admin=verify, backend_changed=replace)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'owned-editor'}
                boot = (await client.get('/api/bootstrap', headers=identity)).json()
                response = await client.put('/api/backend', headers=reviewed_headers(boot, identity),
                                            json={'url': 'https://saved.example', 'key': 'SYNTHETIC'})
                assert response.status_code == 503
                assert response.json()['saved'] is True
                assert response.json()['detail']['code'] == 'config_apply_failed'
                assert response.json()['configuration']['apply_state'] == 'failed'
                assert 'PRIVATE_CREDENTIAL_CANARY' not in response.text
                fresh = await client.get('/api/bootstrap', headers=identity)
                assert fresh.json()['backend_url'] == 'https://saved.example'
                assert fresh.json()['configuration']['apply_state'] == 'failed'
