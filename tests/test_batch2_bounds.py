"""Nested accepted schema, projection limits and source effect regressions."""
from contextlib import closing
import json
import subprocess
import importlib.util
from pathlib import Path
import pytest
from pydantic import ValidationError
from mcp_admin_core.products import ProductStore, TOOLS
from mcp_admin_core.policy import authorize, Denied, filter_list
from n8n_adapter import TOOLS as N8N_TOOLS
from test_batch2_policy import BAD_CONNECTION_KEYS, CASES, GRAPH, GRAPH_NAME_CASES, graph_with_name
from test_expansion_policy import call
from test_real_products import connection

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('b1_output', ROOT / 'apps/runtime/batch2_outputs.py')
output = importlib.util.module_from_spec(spec); spec.loader.exec_module(output)

def schema_results(schema, args_list):
    # Reuse the pinned child validator, as test_expansion_schemas does.
    probe = subprocess.run([str(ROOT / 'apps/odoo/.venv/bin/python'), '-c', '''
import json, sys
from jsonschema import Draft202012Validator
schema, args_list = json.load(sys.stdin)
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
print(json.dumps([validator.is_valid(args) for args in args_list]))
'''], input=json.dumps([schema, args_list]), text=True, capture_output=True, timeout=10,
        env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert probe.returncode == 0, probe.stderr
    return json.loads(probe.stdout)


def schema_valid(schema, args):
    return schema_results(schema, [args])[0]


@pytest.mark.parametrize('product,name,args', CASES)
def test_advertised_b1_schema_and_normalized_wire(product, name, args):
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    model = tools[name].arguments
    assert schema_valid(model.model_json_schema(), args)
    normalized = model.model_validate(args).model_dump(mode='json')
    assert schema_valid(model.model_json_schema(), normalized)
    assert normalized == model.model_validate(normalized).model_dump(mode='json')

@pytest.mark.parametrize('name', ['n8n_create_workflow', 'validate_workflow'])
@pytest.mark.parametrize('key', BAD_CONNECTION_KEYS, ids=[
    'slash', 'leading-digit', 'leading-hyphen', 'newline', 'nul', 'tab',
    'non-ascii', 'proto', 'prototype', 'constructor',
])
def test_connection_keys_rejected_by_public_schema_and_authorize(tmp_path, name, key):
    graph = {**GRAPH, 'connections': {key: {'unexpected': 'not a typed edge'}}}
    args = {'workflow': graph} if name == 'validate_workflow' else graph
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(enabled_write_tools=['n8n_create_workflow'])
        state = store.load()
        # Exercise the tools/list publication path, not a hand-written schema.
        published = filter_list({'result': {'tools': [{'name': name}]}}, N8N_TOOLS, state)
        schema = published['result']['tools'][0]['inputSchema']
        with pytest.raises(Denied, match='invalid tool arguments'):
            authorize(call(name, args), N8N_TOOLS, state)
        assert not schema_valid(schema, args)


@pytest.mark.parametrize('name', ['n8n_create_workflow', 'validate_workflow'])
@pytest.mark.parametrize('boundary', ['id', 'name', 'connection-key', 'edge-target'])
def test_graph_name_portable_boundaries(tmp_path, name, boundary):
    model = N8N_TOOLS[name].arguments
    graphs = [graph_with_name(value, boundary) for value, _ in GRAPH_NAME_CASES]
    args_list = [{'workflow': graph} if name == 'validate_workflow' else graph for graph in graphs]
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(enabled_write_tools=['n8n_create_workflow'])
        state = store.load()
        published = filter_list({'result': {'tools': [{'name': name}]}}, N8N_TOOLS, state)
        schema = published['result']['tools'][0]['inputSchema']
        results = schema_results(schema, args_list)
        for (value, expected), args, accepted in zip(GRAPH_NAME_CASES, args_list, results, strict=True):
            if expected:
                normalized = model.model_validate(args).model_dump(mode='json')
                assert model.model_validate(normalized).model_dump(mode='json') == normalized
                authorize(call(name, args), N8N_TOOLS, state)
            else:
                with pytest.raises(ValidationError) as error:
                    model.model_validate(args)
                # Not merely unknown cross-references: a structural name check failed.
                assert any(e['type'] in ('string_pattern_mismatch', 'string_too_short',
                    'string_too_long', 'value_error') and 'unknown connection' not in e['msg']
                    for e in error.value.errors()), repr(value)
                with pytest.raises(Denied, match='invalid tool arguments'):
                    authorize(call(name, args), N8N_TOOLS, state)
            assert accepted is expected, (boundary, repr(value), accepted, expected)
        valid_normalized = [model.model_validate(args).model_dump(mode='json')
            for args, (_, expected) in zip(args_list, GRAPH_NAME_CASES, strict=True) if expected]
        assert all(schema_results(schema, valid_normalized))


@pytest.mark.parametrize('name', ['n8n_create_workflow', 'validate_workflow'])
def test_correct_connection_key_still_requires_typed_outputs(name):
    graph = {**GRAPH, 'connections': {'Start': {'unexpected': 'not a typed edge'}}}
    args = {'workflow': graph} if name == 'validate_workflow' else graph
    model = N8N_TOOLS[name].arguments
    assert not schema_valid(model.model_json_schema(), args)
    with pytest.raises(ValidationError):
        model.model_validate(args)


def test_graph_name_schema_fragments_in_python_and_ecmascript():
    schema = N8N_TOOLS['n8n_create_workflow'].arguments.model_json_schema()
    # Check every GraphName use independently, including propertyNames where
    # Pydantic moves the positive pattern into patternProperties.
    connections = schema['properties']['connections']
    fragments = [schema['$defs']['SafeNode']['properties'][field] for field in ('id', 'name')]
    fragments += [schema['$defs']['Edge']['properties']['node'], connections['propertyNames']]
    key_pattern, = connections['patternProperties']
    fragments[-1] = {**fragments[-1], 'pattern': key_pattern}
    values = [value for value, _ in GRAPH_NAME_CASES]
    expected = [valid for _, valid in GRAPH_NAME_CASES]
    # Isolate real connection keys with VALID Outputs, independent of node names.
    assert schema_results({'$defs': schema['$defs'], **connections},
        [{value: GRAPH['connections']['Start']} for value in values]) == expected
    for fragment in fragments:
        assert schema_results(fragment, values) == expected
    # Small regex/schema-keyword probe, not a replacement JSON-schema validator.
    probe = subprocess.run(['node', '-e', '''
const [fragments, values] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
function valid(s, v) {
  return (!s.pattern || new RegExp(s.pattern).test(v)) &&
    (s.minLength === undefined || v.length >= s.minLength) &&
    (s.maxLength === undefined || v.length <= s.maxLength) &&
    (!s.enum || s.enum.includes(v)) && (!s.not || !valid(s.not, v)) &&
    (!s.allOf || s.allOf.every(x => valid(x, v)));
}
console.log(JSON.stringify(fragments.map(s => values.map(v => valid(s, v)))));
'''], input=json.dumps([fragments, values]), text=True, capture_output=True,
        timeout=10, env={'PATH': '/usr/bin:/bin'})
    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == [expected] * len(fragments)


BAD = [
    ('odoo', 'build_domain', {'conditions': [{'field': 'password', 'operator': '=', 'value': 'x'}]}),
    ('odoo', 'build_domain', {'conditions': [{'field': 'id', 'operator': '=', 'value': True}]}),
    ('odoo', 'build_domain', {'conditions': [{'field': 'name', 'operator': '=', 'value': {'__proto__': {}}}]}),
    ('odoo', 'build_domain', {'conditions': [], 'fields_metadata': {'name': {}}}),
    ('odoo', 'generate_json2_payload', {'model': 'res.partner', 'method': 'unlink'}),
    ('odoo', 'generate_json2_payload', {'model': 'res.partner', 'method': 'search_read', 'base_url': 'http://127.0.0.1'}),
    ('odoo', 'generate_json2_payload', {'model': 'res.partner', 'method': 'search_read', 'kwargs': {'context': {'sudo': True}}}),
    ('odoo', 'generate_json2_payload', {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'limit': 10}}),
    ('odoo', 'diagnose_odoo_call', {'model': 'res.partner', 'method': 'search_read', 'use_live_metadata': True}),
    ('odoo', 'diagnose_odoo_call', {'model': 'res.partner', 'method': 'search_read', 'observed_error': {'key': 'x'}}),
    ('odoo', 'aggregate_records', {'model': 'res.partner', 'group_by': ['active'], 'measures': ['id:array_agg']}),
    ('odoo', 'aggregate_records', {'model': 'res.partner', 'group_by': ['active'], 'limit': 101}),
    ('odoo-manage', 'aggregate_records', {'model': 'res.partner', 'groupby': ['password']}),
    ('odoo-manage', 'aggregate_records', {'model': 'res.partner', 'groupby': ['active'], 'domain': [['id', 'child_of', 1]]}),
    ('odoo-manage', 'post_message', {'model': 'res.partner', 'record_id': 1, 'body': 'x', 'subtype': 'comment'}),
    ('odoo-manage', 'post_message', {'model': 'res.partner', 'record_id': 1, 'body': 'x', 'partner_ids': [1]}),
    ('odoo-manage', 'post_message', {'model': 'res.partner', 'record_id': 1, 'body': 'x', 'attachment_ids': [1]}),
    ('odoo-manage', 'post_message', {'model': 'res.partner', 'record_id': 1, 'body': 'x', 'body_is_html': True}),
    ('n8n', 'validate_node', {'nodeType': 'nodes-base.noOp', 'config': {'__proto__': {}}}),
    ('n8n', 'validate_node', {'nodeType': 'nodes-base.noOp', 'config': {}, 'mode': 'execute'}),
    ('n8n', 'n8n_create_workflow', {**GRAPH, 'active': True}),
    ('n8n', 'n8n_create_workflow', {**GRAPH, 'settings': {'errorWorkflow': 'one'}}),
    ('n8n', 'n8n_create_workflow', {**GRAPH, 'projectId': 'elsewhere'}),
    ('n8n', 'n8n_create_workflow', {**GRAPH, 'nodes': GRAPH['nodes'] * 11}),
    ('n8n', 'n8n_create_workflow', {**GRAPH, 'connections': {'constructor': {'main': [[]]}}}),
]

@pytest.mark.parametrize('product,name,args', BAD)
def test_nested_bypasses_denied_in_schema_and_dispatch(tmp_path, product, name, args):
    tools = N8N_TOOLS if product == 'n8n' else TOOLS[product]
    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'odoo-manage': store.update(connection={**connection(product, 'http://127.0.0.1:12345'), 'mode': 'module'})
        if tools[name].write: store.update(enabled_write_tools=[name])
        assert not schema_valid(tools[name].arguments.model_json_schema(), args)
        with pytest.raises(Denied): authorize(call(name, args), tools, store.load())

@pytest.mark.parametrize('rows', [None, {}, [{'active': True, 'id': True}], [{'active': 'secret', 'id': 1}],
    [{'active': True, 'id': -1}], [{'active': True, 'id': 2**32}], [{'active': True, 'id': 1}] * 101])
def test_count_output_malformed_or_unbounded_fails_closed(rows):
    with pytest.raises(ValueError, match='BACKEND_RESPONSE_INVALID'): output.count_rows(rows)


def test_count_output_never_includes_drilldown_or_arbitrary_values():
    assert output.count_rows([{'active': False, 'id': 2, '__domain': ['SECRET'], 'password': 'SECRET'}]) == [
        {'active': False, 'id:count': 2, '__count': 2}]
    assert output.odoo_counts({'success': False, 'error': 'SECRET'}) == {'success': False, 'error': 'BACKEND_REQUEST_FAILED'}
