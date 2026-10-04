"""Pinned child positive calls and zero-dispatch negatives; owned fake only."""
import asyncio
import copy
import json
import httpx
import pytest
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from n8n_adapter import TOOLS as N8N_TOOLS, child_spec as n8n_spec
from batch2_owned_port import private_spec, reserve_port, request_guard, wait_owned_listener
from test_batch2_policy import BAD_CONNECTION_KEYS, CASES, GRAPH, GRAPH_NAME_CASES, graph_with_name
from test_expansion_policy import call
from test_expansion_runtime import fake_api, payload
from test_real_products import connection, rpc

PURE = {'build_domain', 'generate_json2_payload', 'diagnose_odoo_call', 'validate_node', 'validate_workflow'}

@pytest.mark.parametrize('product,major,allow_write', [('odoo', 18, True), ('odoo', 19, True), ('odoo-manage', 18, True), ('odoo-manage', 19, True), ('odoo-manage', 19, False), ('n8n', 18, True)])
async def test_batch2_real_handlers(tmp_path, product, major, allow_write):
    with fake_api(major=major, allow_write=allow_write) as (url, events, mutations, failures):
        store = ProductStore(tmp_path / 'state', product)
        tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
        if product == 'n8n': store.update(backend_url=url, backend_key='DUMMY')
        else:
            conn = connection(product, url)
            if product == 'odoo-manage': conn['mode'] = 'module'
            store.update(connection=conn)
        production_spec = (n8n_spec if product == 'n8n' else child_spec)(store.load(), store.directory)
        process = Supervisor(production_spec, retries=0)
        reservation = reserve_port()
        port = reservation.getsockname()[1]
        try:
            process.spec = private_spec(production_spec, product, port)
            reservation.close()  # stock CLI cannot inherit; ownership check closes the bind race
            await process.start()
            proof = await wait_owned_listener(process, port)
            print(f'B1_OWNED_LISTENER product={product} major={major} allow_write={allow_write} '
                  f'port={port} pid={proof[0]} inode={proof[1]}')
            dispatches = []
            async def dispatched(request): dispatches.append(request.method)
            async with httpx.AsyncClient(trust_env=False, event_hooks={
                    'request': [request_guard(process, port, proof), dispatched]}) as child:
                _, app = make_apps(store, tools, child, child_url=f'http://127.0.0.1:{port}/mcp')
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer '+store.load().token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'owned-b1', 'version': '0'}}}
                    async with asyncio.timeout(25):
                        while True:
                            try: result = await rpc(client, '/mcp', headers, init); break
                            except ValueError: await asyncio.sleep(.1)
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    store.update(writes_enabled=True)
                    for p, name, args in CASES:
                        if p != product: continue
                        before, count, dispatched_before = len(events), len(mutations), len(dispatches)
                        if tools[name].write:
                            assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                            assert len(events) == before and len(mutations) == count and len(dispatches) == dispatched_before
                            store.update(enabled_write_tools=[name])
                        reply = await rpc(client, '/mcp', headers, call(name, args))
                        if name == 'post_message' and not allow_write:
                            assert reply.get('isError') is True
                            assert len(mutations) == count
                            store.update(enabled_write_tools=[])
                            continue
                        value = payload(reply)
                        assert 'MUST_NOT_ESCAPE' not in json.dumps(reply)
                        if name in PURE:
                            assert len(events) == before and len(mutations) == count
                        elif tools[name].write:
                            assert len(mutations) == count + 1
                        else: assert len(mutations) == count
                        if name == 'build_domain': assert value['domain'] == [['active', '=', True]]
                        if name == 'generate_json2_payload':
                            assert value['endpoint'] == {'path': '/json/2/res.partner/search_read', 'url': None}
                            assert value['body']['fields'] == ['id', 'name']
                            assert value['metadata_used']['client_instantiated'] is False
                        if name == 'diagnose_odoo_call': assert value['method'] == 'search_count'
                        if name == 'validate_node':
                            assert value['valid'] is True
                            for mode in ('full', 'minimal'):
                                for profile in ('strict', 'runtime', 'ai-friendly', 'minimal'):
                                    checked = payload(await rpc(client, '/mcp', headers, call(name, {**args, 'mode': mode, 'profile': profile})))
                                    assert checked['valid'] is True
                            assert len(events) == before and len(mutations) == count
                        if name == 'validate_workflow':
                            assert value['valid'] is True
                            invalid = copy.deepcopy(GRAPH)
                            # Referencing self is bounded data, not execution. The
                            # real validator must identify this invalid graph.
                            invalid['connections']['Start']['main'][0][0]['node'] = 'Start'
                            checked = payload(await rpc(client, '/mcp', headers, call(name, {'workflow': invalid})))
                            assert checked['valid'] is False
                            assert len(events) == before and len(mutations) == count
                        if name == 'aggregate_records':
                            rows = value['rows' if product == 'odoo' else 'groups']
                            assert rows == [{'active': True, 'id:count': 2, '__count': 2}]
                        if name == 'list_resource_templates':
                            assert value['enabled_models'] == ['res.partner']
                            assert 'denied' in value['note']
                            before_resource = len(events)
                            response = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'resources/read', 'params': {'uri': 'odoo://res.partner/record/1'}})
                            assert response.status_code == 403 and len(events) == before_resource
                        if name == 'post_message':
                            assert value['message_id'] == 2
                            assert mutations[-1][3] == {'body': args['body'], 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_note'}
                        if name == 'n8n_create_workflow':
                            assert mutations[-1][:2] == ('POST', '/api/v1/workflows')
                            body = mutations[-1][2]
                            assert 'active' not in body and 'credentials' not in json.dumps(body)
                            assert body['connections'] == GRAPH['connections']
                            assert value['data']['active'] is False
                        before, count, dispatched_before = len(events), len(mutations), len(dispatches)
                        if name in ('n8n_create_workflow', 'validate_workflow'):
                            for key in BAD_CONNECTION_KEYS:
                                graph = {**GRAPH, 'connections': {key: {'unexpected': 'not a typed edge'}}}
                                invalid_args = {'workflow': graph} if name == 'validate_workflow' else graph
                                response = await client.post('/mcp', headers=headers, json=call(name, invalid_args))
                                assert response.status_code == 403
                                assert len(events) == before and len(mutations) == count
                                assert len(dispatches) == dispatched_before
                            for boundary in ('id', 'name', 'connection-key', 'edge-target'):
                                for value, valid in GRAPH_NAME_CASES:
                                    if valid: continue
                                    graph = graph_with_name(value, boundary)
                                    invalid_args = {'workflow': graph} if name == 'validate_workflow' else graph
                                    response = await client.post('/mcp', headers=headers, json=call(name, invalid_args))
                                    assert response.status_code == 403, (boundary, repr(value))
                                    assert len(events) == before and len(mutations) == count
                                    assert len(dispatches) == dispatched_before
                        for extra in ('ctx', 'session', '__proto__', 'action'):
                            assert (await client.post('/mcp', headers=headers, json=call(name, {**args, extra: {}}))).status_code == 403
                        store.update(disabled=[name])
                        assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                        assert len(events) == before and len(mutations) == count and len(dispatches) == dispatched_before
                        store.update(disabled=[], enabled_write_tools=[])
                        if tools[name].write:
                            assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                            assert len(events) == before and len(dispatches) == dispatched_before
                    assert not failures, failures
                    await client.delete('/mcp', headers=headers)
        finally:
            reservation.close()
            await process.stop(); store.close()
