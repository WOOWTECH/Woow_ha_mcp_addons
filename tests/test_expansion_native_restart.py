"""Grant through the actual API -> owned native restart -> real fake write."""
import asyncio
from pathlib import Path

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from owned_runtime import Endpoint
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from test_expansion_policy import call
from test_expansion_runtime import WRITES, fake_api, payload
from test_real_products import connection, rpc


@pytest.mark.parametrize('product', ['emqx', 'litellm'])
async def test_api_enabling_writer_rebuilds_actual_native_gate(tmp_path, product):
    with fake_api() as (url, events, mutations, failures):
        store = ProductStore(tmp_path, product)
        store.update(connection=connection(product, url))
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(child_spec(store.load(), store.directory))
        async def restart(state):
            await manager.stop()
            manager.spec = endpoint.prepare(child_spec(state, store.directory))
            await manager.start()
        async def role(_): return True
        try:
            await manager.start()
            async with endpoint.client() as child:
                admin, app = make_apps(store, TOOLS[product], child, verify_admin=role, backend_changed=restart, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    async def initialize():
                        headers = {'Authorization': 'Bearer '+store.load().token, 'Accept': 'application/json, text/event-stream'}
                        init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'native-grant-test', 'version': '0'}}}
                        async with asyncio.timeout(20):
                            while True:
                                try:
                                    await rpc(client, '/mcp', headers, init); break
                                except ValueError: await asyncio.sleep(.1)
                        await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                        return headers
                    headers = await initialize()
                    name,args = WRITES[product][0]
                    before = len(events)
                    assert (await client.post('/mcp', headers=headers, json=call(name,args))).status_code == 403
                    assert len(events) == before and not mutations
                    old_pid = manager.process.pid
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2',1)), base_url='http://admin') as a:
                        identity = {'x-remote-user-id': 'a'*32}
                        bootstrap = (await a.get('/api/bootstrap', headers=identity)).json()
                        identity['x-csrf-token'] = bootstrap['csrf']
                        response = await a.put('/api/policy', headers=identity, json={
                            'writes_enabled': False, 'disabled': [], 'enabled_write_tools': [name]})
                        assert response.status_code == 200
                        assert manager.process.pid != old_pid and not Path(f'/proc/{old_pid}').exists()
                        headers = await initialize()
                        reply = await rpc(client, '/mcp', headers, call(name,args))
                        payload(reply)
                        assert len(mutations) == 1
                        response = await a.put('/api/policy', headers=identity, json={
                            'writes_enabled': False, 'disabled': [name], 'enabled_write_tools': []})
                        assert response.status_code == 200
                        before = len(events)
                        # The old session must never bypass the new parent gate.
                        assert (await client.post('/mcp', headers=headers, json=call(name,args))).status_code == 403
                        assert len(events) == before and len(mutations) == 1
                    assert not failures
        finally:
            await manager.stop(); endpoint.close(); store.close()
