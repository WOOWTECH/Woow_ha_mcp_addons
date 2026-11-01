"""Hermes Dashboard failures: actionable text without backend URL or credentials."""
from contextlib import closing
import socket

from mcp_admin_core.products import ProductStore, child_spec
from owned_runtime import Endpoint
from test_real_products import rpc
from test_six_hardening import call, runtime


INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {},
    'clientInfo': {'name': 'dashboard-guidance-test', 'version': '0'}}}
ACCEPT = {'Accept': 'application/json, text/event-stream'}


async def direct_status(child, endpoint):
    headers = ACCEPT.copy()
    await rpc(child, endpoint.url, headers, INIT)
    await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return await rpc(child, endpoint.url, headers, call('hermes_gateway', {'action': 'status'}))


def error_text(reply):
    assert reply['isError'] is True, reply
    return reply['content'][0]['text']


async def test_refused_dashboard_connection_has_safe_guidance_at_child_and_gateway(tmp_path):
    # Bound but not listening: an owned loopback port that refuses TCP connects.
    with closing(socket.socket()) as refused:
        refused.bind(('127.0.0.1', 0))
        port = refused.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        secret = 'CANARY-hermes-dashboard-password-9917'
        async with runtime(tmp_path, 'hermes', url, canary=secret) as (client, headers, _store, manager, child):
            direct = error_text(await direct_status(child, manager.endpoint))
            public = error_text(await rpc(client, '/mcp', headers, call('hermes_gateway', {'action': 'status'})))

    for text in (direct, public):
        assert 'BACKEND_UNAVAILABLE: Hermes Dashboard 不可達 (unreachable)' in text
        assert 'Check that the Hermes service is running' in text
        assert 'Connection > Dashboard REST API in the MCP admin page has the right address' in text
        assert url not in text and str(port) not in text and secret not in text
        assert 'All connection attempts failed' not in text


async def test_missing_dashboard_connection_keeps_code_and_existing_admin_hint(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'hermes')) as store:
        store.update(connection={'gateway_url': 'http://127.0.0.1:9', 'gateway_api_key': 'DUMMY'})
        endpoint = Endpoint('hermes')
        manager = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await manager.start()
            async with endpoint.client(timeout=15) as child:
                text = error_text(await direct_status(child, endpoint))
        finally:
            await manager.stop()
            endpoint.close()

    assert 'BACKEND_UNAVAILABLE: dashboard_url is not configured' in text
    assert 'set it in the admin GUI under Connection > Dashboard REST API' in text
