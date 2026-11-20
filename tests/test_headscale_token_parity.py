"""Headscale uses PaaS's rotate-to-disclose contract; other products retain reveal."""
import httpx
import pytest

from admin_write_headers import reviewed_headers
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS


@pytest.mark.parametrize('product', ['headscale', 'hermes'])
async def test_reveal_and_rotate_are_scoped_to_product(tmp_path, product):
    store = ProductStore(tmp_path / product, product)
    old = store.load().token
    async def admin_role(user):
        return user == 'admin'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as child:
        app, mcp = make_apps(store, TOOLS[product], child, verify_admin=admin_role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('172.30.32.2', 1)), base_url='http://admin') as client:
            identity = {'X-Remote-User-Id': 'admin'}
            boot = (await client.get('/api/bootstrap', headers=identity)).json()
            headers = reviewed_headers(boot, identity)
            denied = await client.post('/api/token/reveal', headers={**headers, 'X-Remote-User-Id': 'not-admin'})
            assert denied.status_code == 403 and old not in denied.text
            reveal = await client.post('/api/token/reveal', headers=headers)
            if product == 'headscale':
                assert reveal.status_code == 404
                assert old not in reveal.text
                assert store.load().token == old
            else:
                assert reveal.status_code == 200 and reveal.json()['token'] == old
            rotated = await client.post('/api/token/rotate', headers=headers)
            assert rotated.status_code == 200
            assert rotated.json()['token'] == store.load().token != old
            replay = await client.post('/api/token/rotate', headers=headers)
            assert replay.status_code == 200 and replay.json()['operation']['replayed'] is True
            assert 'token' not in replay.json()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp), base_url='http://mcp') as client:
            refused = await client.get('/mcp', headers={'Authorization': 'Bearer ' + old})
            assert refused.status_code == 401
    store.close()


async def test_headscale_profile_reveal_and_rotation_are_isolated(tmp_path):
    from multi_profile_runtime import create_profile, multi_profile_runtime
    from test_single_profile_golden import ADMIN

    data = tmp_path / 'data'
    ProductStore(data, 'headscale').close()
    profile = 'a' * 24
    create_profile(data, 'headscale', profile, label='Extra', port=18000, configured=False)
    async with multi_profile_runtime('headscale', data) as runtime:
        original = {name: runtime.token(name) for name in ('default', profile)}
        for name in original:
            async with runtime.admin(name) as client:
                boot = (await client.get('/api/bootstrap', headers=ADMIN)).json()
                headers = reviewed_headers(boot, ADMIN)
                response = await client.post('/api/token/reveal', headers=headers)
                assert response.status_code == 404
                assert original[name] not in response.text
        async with runtime.admin(profile) as client:
            boot = (await client.get('/api/bootstrap', headers=ADMIN)).json()
            response = await client.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))
            assert response.status_code == 200
            assert response.json()['token'] == runtime.token(profile) != original[profile]
            assert runtime.token('default') == original['default']
