"""B1 exact source names, bounded schemas, no implicit writer authority."""
import copy
from contextlib import closing
import pytest
from mcp_admin_core.products import ProductStore, TOOLS
from mcp_admin_core.policy import authorize, Denied
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_policy import call
from test_real_products import connection

GRAPH = {'name': 'Owned draft', 'nodes': [
    {'id': 'start', 'name': 'Start', 'type': 'n8n-nodes-base.manualTrigger', 'typeVersion': 1, 'position': [0, 0], 'parameters': {}},
    {'id': 'end', 'name': 'End', 'type': 'n8n-nodes-base.noOp', 'typeVersion': 1, 'position': [200, 0], 'parameters': {}},
], 'connections': {'Start': {'main': [[{'node': 'End', 'type': 'main', 'index': 0}]]}}}
BAD_CONNECTION_KEYS = (
    'invalid/source', '1Start', '-Start', 'Start\nEnd', 'Start\x00End',
    'Start\tEnd', 'Stárt', '__proto__', 'prototype', 'constructor',
)

# Include terminal separators with otherwise well-typed edges: malformed Outputs
# can hide a key-pattern end-anchor mismatch in the advertised schema.
GRAPH_NAME_CASES = [(value, False) for value in (
    'Start\n', '', '1Start', '-Start', '_Start', 'invalid/source', 'Stárt', 'A' * 65,
    '__proto__', 'prototype', 'constructor', '__proto__\n',
    'prototype\n', 'constructor\n', 'Start\r\n', 'Start\u0085',
    'Start\u2028', 'Start\u2029', 'Start\ufeff', 'Start\u200b',
    *('Start' + chr(code) for code in (*range(32), 127) if code != 10),
    'Start\nEnd', 'Start\rEnd', 'Start\u2028End', 'Start\u2029End',
)] + [(value, True) for value in (
    'A', 'Z', 'a', 'z', 'A' * 64, 'Start', 'Start 09_-', 'Start ',
    'Constructor', 'Prototype', 'constructorX', 'prototype_', 'A__proto__',
)]


def graph_with_name(value, boundary):
    graph = copy.deepcopy(GRAPH)
    if boundary == 'id':
        graph['nodes'][0]['id'] = value
    elif boundary in ('name', 'connection-key'):
        graph['nodes'][0]['name'] = value
        graph['connections'][value] = graph['connections'].pop('Start')
    elif boundary == 'edge-target':
        # Keep the legitimate value 'Start' distinct from the source node.
        graph['nodes'][0]['name'] = 'Source'
        graph['connections']['Source'] = graph['connections'].pop('Start')
        graph['nodes'][1]['name'] = value
        graph['connections']['Source']['main'][0][0]['node'] = value
    else:
        raise AssertionError(boundary)
    return graph


CASES = [
    ('odoo', 'build_domain', {'conditions': [{'field': 'active', 'operator': '=', 'value': True}]}),
    ('odoo', 'generate_json2_payload', {'model': 'res.partner', 'method': 'search_read', 'kwargs': {'fields': ['id', 'name'], 'limit': 10}}),
    ('odoo', 'diagnose_odoo_call', {'model': 'res.partner', 'method': 'search_count'}),
    ('odoo', 'aggregate_records', {'model': 'res.partner', 'group_by': ['active'], 'measures': ['id:count'], 'limit': 10}),
    ('odoo-manage', 'aggregate_records', {'model': 'res.partner', 'groupby': ['active'], 'aggregates': ['id:count'], 'limit': 10}),
    ('odoo-manage', 'list_resource_templates', {}),
    ('odoo-manage', 'post_message', {'model': 'res.partner', 'record_id': 1, 'body': 'Owned internal note'}),
    ('n8n', 'validate_node', {'nodeType': 'nodes-base.noOp', 'config': {}}),
    ('n8n', 'validate_workflow', {'workflow': GRAPH}),
    ('n8n', 'n8n_create_workflow', GRAPH),
]

@pytest.mark.parametrize('product,name,args', CASES)
def test_b1_surface_exact_grants_and_unknown_fields(tmp_path, product, name, args):
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    assert name in tools
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'odoo-manage':
            store.update(connection={**connection(product, 'http://127.0.0.1:12345'), 'mode': 'module'})
        store.update(writes_enabled=True)
        tool = tools[name]
        if tool.write:
            with pytest.raises(Denied): authorize(call(name, args), tools, store.load())
            store.update(enabled_write_tools=[name])
        authorize(call(name, args), tools, store.load())
        for field in ('ctx', 'session', 'action', '__proto__', 'instance_override'):
            with pytest.raises(Denied): authorize(call(name, {**args, field: {}}), tools, store.load())
        store.update(disabled=[name])
        with pytest.raises(Denied): authorize(call(name, args), tools, store.load())

@pytest.mark.parametrize('change', [
    {'credentials': {'x': {'id': '1'}}}, {'parameters': {'jsCode': 'return []'}},
    {'type': 'n8n-nodes-base.httpRequest'}, {'parameters': {'url': 'https://example.invalid'}},
    {'name': '__proto__'}, {'name': 'constructor'}, {'typeVersion': True},
])
def test_b1_graph_unsafe_nodes_denied(tmp_path, change):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(enabled_write_tools=['n8n_create_workflow'])
        graph = copy.deepcopy(GRAPH); graph['nodes'][0].update(change)
        for name, args in [('validate_workflow', {'workflow': graph}), ('n8n_create_workflow', graph)]:
            with pytest.raises(Denied): authorize(call(name, args), N8N_TOOLS, store.load())
