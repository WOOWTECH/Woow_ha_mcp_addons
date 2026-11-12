"""Partial edits exercise actual management auth/state/lifecycle, using synthetic credentials."""
from contextlib import closing

import httpx
import pytest

from mcp_admin_core.backend_edit import view, changes
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS

IDENTITY = {'x-remote-user-id': 'fake-admin'}
CONNECTIONS = {
    'odoo': dict(url='http://old.test', database='fake', username='fake', password='secret-odoo'),
    'hermes': dict(gateway_url='http://old.test', gateway_api_key='secret-hermes',
                   dashboard_url='http://dash.test', dashboard_username='fake', dashboard_password='secret-dashboard'),
    'emqx': dict(url='http://old.test', api_key='secret-emqx-key', api_secret='secret-emqx'),
    'litellm': dict(url='http://old.test', master_key='secret-litellm'),
    'nextcloud': dict(url='http://old.test', username='fake', app_password='secret-nextcloud'),
}


@pytest.mark.parametrize('product', ['n8n', *CONNECTIONS])
async def test_partial_url_update_preserves_secrets_and_requires_revision(tmp_path, product):
    restarts = []
    role = {'allowed': True}
    async def verify(_): return role['allowed']
    async def restart(state): restarts.append(state)
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'n8n':
            store.update(backend_url='http://old.test', backend_key='secret-n8n', mcp_access_token='secret-native')
        else:
            store.update(connection=CONNECTIONS[product])
        before = store.load()
        before_bytes = store.path.read_bytes()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child,
                                 verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                boot = await client.get('/api/bootstrap', headers=IDENTITY)
                assert 'secret-' not in boot.text
                edit = boot.json()['backend_edit']
                assert edit['contract'] == 'woow-connection-patch-v1'
                assert all(edit['secret_set'].values())
                headers = {**IDENTITY, 'x-csrf-token': boot.json()['csrf']}
                key = 'gateway_url' if product == 'hermes' else 'url'
                payload = {'changes': {key: 'http://new.test'}}
                assert (await client.put('/api/backend/patch', headers=headers, json=payload)).status_code == 428
                headers['if-match'] = boot.headers['etag']
                role['allowed'] = False
                assert (await client.put('/api/backend/patch', headers=headers, json=payload)).status_code == 403
                role['allowed'] = True
                for invalid in ({'changes': {}}, {'changes': {'token': 'x'}}, {'changes': {key: None}}):
                    assert (await client.put('/api/backend/patch', headers=headers, json=invalid)).status_code == 400
                assert store.path.read_bytes() == before_bytes and not restarts
                response = await client.put('/api/backend/patch', headers=headers, json=payload)
                assert response.status_code == 200 and response.json()['saved'] is True
                assert len(restarts) == 1
                after = store.load()
                if product == 'n8n':
                    assert after.backend_url == 'http://new.test'
                    assert (after.backend_key, after.mcp_access_token) == (before.backend_key, before.mcp_access_token)
                else:
                    assert after.connection.model_dump() == {**before.connection.model_dump(), key: 'http://new.test'}
                assert (await client.put('/api/backend/patch', headers=headers, json=payload)).status_code == 409
                assert len(restarts) == 1


def test_explicit_clear_and_required_credential_refusal(tmp_path):
    with closing(ProductStore(tmp_path / 'n8n', 'n8n')) as store:
        with pytest.raises(ValueError): changes(store.load(), {'changes': {'url': 'http://new.test'}})
        store.update(backend_url='http://old.test', backend_key=' exact bytes ', mcp_access_token='native-secret')
        updated = store.update(**changes(store.load(), {'changes': {'mcp_access_token': None}}))
        assert updated.backend_key == ' exact bytes ' and updated.mcp_access_token is None
        assert view(updated)['secret_set'] == {'key': True, 'mcp_access_token': False}
        with pytest.raises(ValueError): changes(updated, {'changes': {'key': None}})
    with closing(ProductStore(tmp_path / 'hermes', 'hermes')) as store:
        store.update(connection=CONNECTIONS['hermes'])
        patch = {'changes': dict.fromkeys(('dashboard_url', 'dashboard_username', 'dashboard_password'))}
        updated = store.update(**changes(store.load(), patch))
        assert updated.connection.dashboard_password is None and updated.connection.gateway_api_key == 'secret-hermes'


async def test_partial_edit_respects_fixed_backend(tmp_path):
    async def verify(_): return True
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection=CONNECTIONS['odoo'])
        before = store.path.read_bytes()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=verify,
                                 management=ManagementOptions(backend_can_edit=False))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                boot = await client.get('/api/bootstrap', headers=IDENTITY)
                response = await client.put('/api/backend/patch', json={'changes': {'url': 'http://new.test'}},
                    headers={**IDENTITY, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']})
                assert response.status_code == 409 and store.path.read_bytes() == before


@pytest.mark.parametrize('product', ['odoo', 'litellm', 'nextcloud', 'n8n'])
@pytest.mark.parametrize('encoded', [False, True])
async def test_known_credentials_in_public_fields_are_withheld_without_rewriting(tmp_path, product, encoded):
    secret = 'SYNTHETIC-CREDENTIAL-046'
    fragment = ''.join(f'%{ord(c):02x}' for c in secret) if encoded else secret
    url = 'https://backend.test/private_' + fragment + '/service'
    async def verify(_): return True
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'n8n':
            store.update(backend_url=url, backend_key=secret)
        else:
            key = {'odoo':'password','litellm':'master_key','nextcloud':'app_password'}[product]
            store.update(connection={**CONNECTIONS[product], 'url':url, key:secret})
        before = store.path.read_bytes()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(500))) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child, verify_admin=verify)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=('172.30.32.2',1)),base_url='http://admin') as client:
                boot = await client.get('/api/bootstrap',headers=IDENTITY)
                assert boot.status_code == 200
                assert secret not in boot.text and fragment not in boot.text
                assert boot.json()['backend_edit']['values']['url'] is None
                assert boot.json()['backend_edit']['withheld_fields'] == ['url']
                assert store.path.read_bytes() == before
                # A deliberate fresh replacement works; hidden display values
                # were never sent back as null/masks to erase the original.
                payload = changes(store.load(), {'changes':{'url':'https://clean.test'}})
                updated = store.update(**payload)
                assert view(updated)['values']['url'] == 'https://clean.test'
