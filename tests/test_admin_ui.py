"""Real gateway HTML/static security; owned build miniature, never shipped fixture."""
import asyncio
import httpx
import pytest
from mcp_admin_core import ui
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore
from n8n_adapter import TOOLS

IDENTITY = {'x-remote-user-id': 'a' * 32}

@pytest.fixture
def build(tmp_path, monkeypatch):
    root = tmp_path / 'dist'
    (root / 'assets').mkdir(parents=True)
    (root / 'licenses').mkdir()
    (root / 'index.html').write_text('<html>__MCP_UI_BASE__ __MCP_UI_BASE__</html>')
    (root / 'assets/app.js').write_text('/* self hosted */')
    (root / 'licenses/NOTICE.txt').write_text('license')
    (tmp_path / 'private').write_text('DO_NOT_READ')
    (root / 'assets/link.js').symlink_to(tmp_path / 'private')
    (root / 'assets/dir').symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(ui, 'UI_ROOT', root)
    return root

@pytest.mark.parametrize('base', ['', '/api/hassio_ingress/DUMMY'])
async def test_real_admin_pages_assets_and_security(tmp_path, build, base):
    allowed, queries = True, []
    async def role(user):
        queries.append(user)
        return allowed
    store = ProductStore(tmp_path / 'state', 'n8n')
    async with httpx.AsyncClient() as child:
        admin, public = make_apps(store, TOOLS, child, verify_admin=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://untrusted-host') as c:
            headers = {**IDENTITY, 'x-ingress-path':base}
            for path in ('/', '/overview', '/backend', '/tools', '/access', '/assets/app.js', '/licenses/NOTICE.txt'):
                for route in set((path, base + path)):
                    before = len(queries)
                    r = await c.get(route, headers=headers)
                    assert r.status_code == 200
                    assert len(queries) == before + 1
                    assert r.headers['cache-control'] == 'no-store'
                    assert r.headers['x-content-type-options'] == 'nosniff'
                    assert r.headers['referrer-policy'] == 'no-referrer'
                    assert "frame-ancestors 'self'" in r.headers['content-security-policy']
                    assert '__MCP_UI_BASE__' not in r.text
                    if path in ui.PAGES: assert r.text == f'<html>{base} {base}</html>'
            bootstrap = (await c.get(base+'/api/bootstrap', headers=headers)).json()
            assert bootstrap['policy_contract'] == 'woow-v3-exact-grants'
            assert bootstrap['endpoint'] is None
            for bad in ('/unknown', '/api/unknown', '/api/__ui__', '/assets/no.js', '/assets/link.js', '/assets/dir/private.js', '/assets/%2e%2e/private', '/assets/x%2fy.js', '/overview?x=1'):
                r = await c.get(base+bad, headers=headers)
                assert r.status_code in (400,404)
                assert 'DO_NOT_READ' not in r.text and '<html>' not in r.text
            allowed = False
            for path in ('/', '/assets/app.js', '/api/bootstrap'):
                assert (await c.get(base+path, headers=headers)).status_code == 403
            allowed = True
            for extra in ([('x-remote-user-id','a'*32)], [('x-ingress-path',base)]):
                assert (await c.get('/', headers=[*headers.items(), *extra])).status_code in (400,403)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin), base_url='http://local') as c:
            assert (await c.get('/',headers=IDENTITY)).status_code == 403
        async with httpx.AsyncClient(transport=httpx.ASGITransport(public), base_url='http://local') as c:
            for path in ('/', '/assets/app.js','/api/bootstrap'):
                assert (await c.get(path,headers=IDENTITY)).status_code == 404
    store.close()

async def test_missing_build_and_unapproved_provider(tmp_path, build):
    store = ProductStore(tmp_path/'state', 'n8n')
    async def role(_): return True
    async with httpx.AsyncClient() as child:
        for verifier, expected in ((None,403),(role,503)):
            admin, _ = make_apps(store,TOOLS,child,verify_admin=verifier)
            (build/'index.html').unlink(missing_ok=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=('172.30.32.2',1)),base_url='http://test') as c:
                r=await c.get('/',headers=IDENTITY)
                assert r.status_code==expected and '<html>' not in r.text
    store.close()

async def test_asset_fanout_is_bounded_and_cancelled(tmp_path, build):
    entered = asyncio.Event()
    active = 0
    async def role(_):
        nonlocal active
        active += 1
        entered.set()
        try: await asyncio.Event().wait()
        finally: active -= 1
    store=ProductStore(tmp_path/'state','n8n')
    async with httpx.AsyncClient() as child:
        admin,_=make_apps(store,TOOLS,child,verify_admin=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=('172.30.32.2',1)),base_url='http://test') as c:
            tasks=[asyncio.create_task(c.get('/assets/app.js',headers=IDENTITY)) for _ in range(16)]
            await entered.wait()
            await asyncio.sleep(.05)
            assert (await c.get('/assets/app.js',headers=IDENTITY)).status_code==503
            assert active==1  # same bounded management lock, no WS fan-out
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            assert active==0
    store.close()
