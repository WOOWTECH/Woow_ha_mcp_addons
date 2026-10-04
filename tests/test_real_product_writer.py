"""Actual OpenDesign handler write only against a disposable loopback backend."""
import asyncio
import socket

import httpx

from mcp_admin_core.gateway import make_apps
from owned_runtime import Endpoint
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from test_real_products import backend, connection, rpc


async def test_real_delete_requires_enable_and_disabled_direct_call_still_denied(tmp_path):
    with backend('opendesign') as (url, calls, _):
        store = ProductStore(tmp_path / 'state', 'opendesign')
        store.update(connection=connection('opendesign', url))
        endpoint = Endpoint('opendesign')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _, app = make_apps(store, TOOLS['opendesign'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '0'}}}
                    async with asyncio.timeout(10):
                        while True:
                            try:
                                result = await rpc(client, '/mcp', headers, init)
                                break
                            except ValueError:
                                await asyncio.sleep(.1)
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    message = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                        'name': 'delete_project', 'arguments': {'project_id': '12345678-1234-1234-1234-123456789abc'}}}
                    assert (await client.post('/mcp', headers=headers, json=message)).status_code == 403
                    assert calls == []
                    store.update(writes_enabled=True)
                    reply = await rpc(client, '/mcp', headers, message)
                    assert not reply.get('isError')
                    assert calls == [('DELETE', '/api/projects/12345678-1234-1234-1234-123456789abc')]
                    store.update(disabled=['delete_project'])
                    assert (await client.post('/mcp', headers=headers, json=message)).status_code == 403
                    assert len(calls) == 1
                    await client.delete('/mcp', headers=headers)
        finally:
            await process.stop(); endpoint.close(); store.close()
