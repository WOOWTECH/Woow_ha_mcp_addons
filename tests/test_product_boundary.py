"""Positive/negative product boundary tests; all transports are MOCK here."""
import json

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import (PRODUCTS, PROBES, ProductStore, TOOLS, child_spec, health_probe_success,
                                    probe_success)
from test_real_products import connection


@pytest.mark.parametrize('product', PRODUCTS)
async def test_config_api_typed_secret_safe_and_restart_on_rotation(tmp_path, product):
    store = ProductStore(tmp_path / product, product)
    changed = []
    async def verify(_): return True  # test-only; executable has no verifier
    async def on_change(state): changed.append(state)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS[product], child, verify_admin=verify, backend_changed=on_change)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=('172.30.32.2', 123)), base_url='http://admin') as client:
                headers = {'x-remote-user-id': 'test-admin'}
                bootstrap = (await client.get('/api/bootstrap', headers=headers)).json()
                headers['x-csrf-token'] = bootstrap['csrf']
                configured = connection(product, 'http://127.0.0.1:9999')
                assert (await client.put('/api/backend', headers=headers, json={'connection': configured})).status_code == 200
                assert len(changed) == 1
                response = await client.get('/api/bootstrap', headers=headers)
                assert 'DUMMY' not in response.text
                assert response.json()['connection_configured']
                original = store.path.read_bytes()
                for bad in ({'connection': {**configured, 'command': 'sh'}}, {'url': 'http://x.test', 'key': 'DUMMY'},
                            {'connection': {**configured, 'env': {'SUPERVISOR_TOKEN': 'DUMMY'}}}):
                    assert (await client.put('/api/backend', headers=headers, json=bad)).status_code == 400
                    assert store.path.read_bytes() == original
                assert (await client.put('/api/backend', headers=headers, json={'connection': None})).status_code == 200
                assert not store.load().configured and len(changed) == 2
    finally: store.close()


@pytest.mark.parametrize('product', PRODUCTS)
async def test_unconfigured_does_not_spawn_or_probe(tmp_path, product):
    store = ProductStore(tmp_path / product, product)
    process = Supervisor(child_spec(store.load(), store.directory))
    contacted = []

    async def forbidden(request):
        contacted.append(request)  # recorded: the monitor contains exceptions raised here (0.1.2)
        raise AssertionError('unconfigured must not contact child/backend')
    try:
        await process.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
            monitor = HealthMonitor(store, process, client)
            await monitor.check()
            assert contacted == [], 'unconfigured must not contact child/backend'
            assert monitor.backend == 'unconfigured'
            assert process.status == 'unconfigured' and process.starts == 0
    finally:
        await process.stop(); store.close()


@pytest.mark.parametrize('product', PRODUCTS)
def test_fixed_child_ignores_parent_secrets_and_gui_commands(tmp_path, product, monkeypatch):
    monkeypatch.setenv('SUPERVISOR_TOKEN', 'NEVER-IN-CHILD')
    monkeypatch.setenv('HTTP_PROXY', 'http://NEVER-IN-CHILD')
    monkeypatch.setenv('PYTHONPATH', '/tmp/NEVER-IN-CHILD')
    monkeypatch.setenv('ODOO_MCP_PLUGINS', 'NEVER-IN-CHILD')
    store = ProductStore(tmp_path / product, product)
    try:
        store.update(connection=connection(product, 'http://127.0.0.1:9999'))
        spec = child_spec(store.load(), store.directory)
        assert not any('NEVER-IN-CHILD' in v for v in spec.env.values())
        assert 'DUMMY' not in ' '.join(spec.argv)
        assert '127.0.0.1' in spec.argv or product in ('hermes', 'opendesign')
        assert spec.env['HOME'] == str(spec.cwd)
        (spec.cwd / '.env').write_text('DUMMY=do-not-read')
        with pytest.raises(RuntimeError): child_spec(store.load(), store.directory)
    finally: store.close()


async def test_writer_is_denied_before_dispatch_then_explicitly_enabled(tmp_path):
    store = ProductStore(tmp_path / 'state', 'opendesign')
    requests = []
    async def dispatch(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {'content': []}})
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
        'name': 'delete_project', 'arguments': {'project_id': '12345678-1234-1234-1234-123456789abc'}}}
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as child:
            _, app = make_apps(store, TOOLS['opendesign'], child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
                headers = {'Authorization': 'Bearer ' + store.load().token}
                assert (await client.post('/mcp', headers=headers, json=message)).status_code == 403
                assert requests == []
                store.update(writes_enabled=True)
                assert (await client.post('/mcp', headers=headers, json=message)).status_code == 200
                assert requests == [message]
                store.update(disabled=['delete_project'])
                assert (await client.post('/mcp', headers=headers, json=message)).status_code == 403
                assert len(requests) == 1
    finally: store.close()


@pytest.mark.parametrize('product', PRODUCTS)
def test_health_rejects_generic_success_and_error_payloads(product):
    for payload in ({'success': True}, {}, {'error': 'DUMMY'}, [], None):
        assert not probe_success(product, payload)
        assert not health_probe_success(product, payload)
    if product == 'odoo':
        # Only Odoo's authenticate answer, exactly: a positive int user id (False for rejected credentials).
        assert health_probe_success(product, {'uid': 7})
        for payload in ({'uid': False}, {'uid': 0}, {'uid': -1}, {'uid': True}, {'uid': '7'}, {'uid': 7.0},
                        {'uid': 7, 'error': None}, {'uid': 7, 'success': True}):
            assert not health_probe_success(product, payload)
