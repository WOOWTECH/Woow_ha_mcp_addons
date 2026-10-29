"""Real pinned child + gateway, using only the owned in-memory XML-RPC backend."""
import asyncio
from contextlib import closing

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from owned_runtime import Endpoint
from test_expansion_policy import call as request_call
from test_expansion_runtime import fake_api
from test_odoo_child_switch_runtime import ALL_ON, INIT, call
from test_real_products import connection, rpc
from tool_refusal import refused


ALLOWLIST = ['res.partner.action_confirm', 'res.partner.message_post', 'res.partner.create',
             'res.partner.write', 'res.partner.unlink']


@pytest.mark.parametrize('changes', [
    {'allow_unknown_methods': False},
    {'allow_unknown_methods': False, 'enable_writes': False},
    {'allow_unknown_methods': False, 'allow_direct_writes': False},
    {'allow_unknown_methods': False, 'chatter_direct': False},
    {},  # broad unknown mode must remain broad, even with a nonempty allowlist
])
async def test_exact_list_and_all_existing_gates_in_actual_child(tmp_path, changes):
    switches = {**ALL_ON, **changes}
    with fake_api() as (backend, events, mutations, failures), closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection=connection('odoo', backend), odoo_write_switches=switches,
                     odoo_allowed_methods=ALLOWLIST)
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _, app = make_apps(store, TOOLS['odoo'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    async with asyncio.timeout(25):
                        while True:
                            try:
                                init = await rpc(client, '/mcp', headers, INIT)
                                break
                            except (ValueError, httpx.HTTPError):
                                await asyncio.sleep(.1)
                    headers['MCP-Protocol-Version'] = init['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    health = await call(client, '/mcp', headers, 2, 'health_check', {})
                    assert health['runtime']['allowed_side_effect_methods'] == ALLOWLIST

                    async def execute(ident, model, method, args, expected, mutates=True):
                        before = len(events), len(mutations)
                        result = await call(client, '/mcp', headers, ident, 'execute_method',
                                            {'model': model, 'method': method, 'args': args})
                        assert result['success'] is expected, result
                        assert len(mutations) == before[1] + int(expected and mutates)
                        if not expected:
                            assert len(events) == before[0], 'refused call reached the backend'

                    await execute(3, 'res.partner', 'action_confirm', [[1]], switches['enable_writes'])
                    await execute(4, 'res.partner', 'message_post', [[1]], switches['enable_writes'] and switches['chatter_direct'])
                    for ident, method, args in ((5, 'create', [{'name': 'FAKE'}]),
                                                (6, 'write', [[1], {'name': 'FAKE'}]), (7, 'unlink', [[1]])):
                        await execute(ident, 'res.partner', method, args,
                                      switches['enable_writes'] and switches['allow_direct_writes'])
                    await execute(8, 'res.partner', 'search_count', [[]], True, mutates=False)
                    if changes:
                        for ident, model, method in ((9, 'res.partner2', 'action_confirm'),
                                                     (10, 'res.partner', 'action_confirm_extra'),
                                                     (11, 'res.partner', 'Action_confirm'),
                                                     (12, 'res.partner', 'get_portal_url')):
                            await execute(ident, model, method, [[1]], False)
                    else:
                        # This model.method is not allowlisted; it still runs in broad mode.
                        await execute(13, 'ir.model', 'action_confirm', [[1]], True)

                    # Revoke the outer grant/disable the tool without restarting the child.
                    for policy in ({'enabled_write_tools': []},
                                   {'enabled_write_tools': ['execute_method'], 'disabled': ['execute_method']}):
                        store.update(**policy)
                        before = len(events), len(mutations), endpoint.dispatches
                        response = await client.post('/mcp', headers=headers, json=request_call('execute_method',
                            {'model': 'res.partner', 'method': 'action_confirm', 'args': [[1]]}))
                        assert refused(response)
                        assert (len(events), len(mutations), endpoint.dispatches) == before
                    await client.delete('/mcp', headers=headers)
        finally:
            await process.stop()
            endpoint.close()
    assert not failures
