"""Offline tests for the P9 plan generator."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import p9_plan as p

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py'
SURFACE = {'products': {'demo': {'tools': [
    {'name': 'health', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {'properties': {}}},
    {'name': 'list', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {
        'properties': {'limit': {'type': 'integer', 'minimum': 1, 'default': 10},
                       'kind': {'enum': ['tags', 'projects']}}, 'required': ['kind']}},
    {'name': 'fields', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {
        'properties': {'model': {'const': 'res.partner'},
                       'fields': {'type': 'array', 'minItems': 1, 'items': {'enum': ['id', 'name']}},
                       'tags': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}}},
        'required': ['model', 'fields']}},
    {'name': 'get', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {
        'properties': {'id': {'type': 'string', 'pattern': '^[A-Za-z0-9]+$'}}, 'required': ['id']}},
    {'name': 'create', 'status': 'supported-bounded', 'effect': 'write', 'accepted_schema': {
        'properties': {'name': {'type': 'string'}, 'nodes': {'type': 'array', 'minItems': 2}}, 'required': ['name', 'nodes']}},
    {'name': 'executions', 'status': 'supported-bounded', 'effect': 'mixed', 'operation_parameter': 'action',
     'operation_effects': {'action': {'list': 'read', 'delete': 'write'}},
     'accepted_schema': {'properties': {'action': {'type': 'string'}, 'id': {'type': 'string'}}, 'required': ['action']}},
    {'name': 'withheld_write', 'status': 'temporarily-unsupported', 'effect': 'write', 'accepted_schema': {}},
    {'name': 'update', 'status': 'supported-bounded', 'effect': 'write', 'accepted_schema': {
        '$defs': {'Values': {'properties': {'name': {'type': 'string'}}, 'required': ['name']}},
        'properties': {'model': {'const': 'res.partner'}, 'values': {'$ref': '#/$defs/Values'}}, 'required': ['model', 'values']}},
    {'name': 'odd_write', 'status': 'supported-bounded', 'effect': 'write', 'accepted_schema': {
        'properties': {'blob': {'type': 'null'}}, 'required': ['blob']}},
    {'name': 'delete', 'status': 'supported-bounded', 'effect': 'write', 'accepted_schema': {
        'properties': {'record_id': {'type': 'integer', 'minimum': 1, 'maximum': 2147483647}}, 'required': ['record_id']}},
]}}}

# 0.2.0 on: the surface of the full products. accepted_schema is null (the gateway forwards the arguments and the child
# validates its own inputSchema); the inputSchema is the one the packaged tools/list snapshot holds.
FULL = {'products': {'demo': {'tools': [
    {'name': name, 'status': 'supported-full', 'effect': effect, 'accepted_schema': None,
     'operation_parameter': selector, 'operation_effects': {selector: operations} if selector else {}}
    for name, effect, selector, operations in [
        ('health', 'read', None, None),
        ('read_record', 'read', None, None),
        ('list_kind', 'read', None, None),
        ('read_page', 'read', None, None),
        ('read_attachment', 'read', None, None),
        ('read_optional', 'read', None, None),
        ('unlisted', 'read', None, None),
        ('delete_record', 'write', None, None),
        ('nodes', 'mixed', 'operation', {'list': 'read', 'get': 'read', 'delete': 'write'}),
        ('agents', 'write', 'action', {'get': 'read', 'create': 'write'}),
        ('runner', 'unverified-side-effects', 'action', {'status': 'read', 'run': 'write'}),
    ]] + [{'name': 'withheld', 'status': 'temporarily-unsupported', 'effect': 'read', 'accepted_schema': None}]}}}
SCHEMAS = {
    'health': {'type': 'object', 'properties': {}},
    'read_record': {'type': 'object', 'properties': {'model': {'type': 'string'}, 'record_id': {'type': 'integer'}},
                    'required': ['model', 'record_id']},
    'list_kind': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['tags', 'projects']}},
                  'required': ['kind']},
    'read_page': {'type': 'object', 'properties': {'page': {'type': 'integer', 'default': 1}}, 'required': ['page']},
    'read_attachment': {'type': 'object', 'properties': {'attachment_id': {'type': 'integer', 'minimum': 1}},
                        'required': ['attachment_id']},
    # a required argument its schema bounds only by anyOf (an integer or null) declares no value either
    'read_optional': {'type': 'object', 'properties': {'record_id': {'anyOf': [{'type': 'integer'}, {'type': 'null'}]}},
                      'required': ['record_id']},
    'delete_record': {'type': 'object', 'properties': {'record_id': {'type': 'integer'}}, 'required': ['record_id']},
    'nodes': {'type': 'object', 'oneOf': [
        {'properties': {'operation': {'const': 'list'}}, 'required': ['operation']},
        {'properties': {'operation': {'const': 'get'}, 'node_id': {'type': 'string'}}, 'required': ['operation', 'node_id']},
        {'properties': {'operation': {'const': 'delete'}, 'node_id': {'type': 'string'}},
         'required': ['operation', 'node_id']}]},
    'agents': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['get', 'create']}},
               'required': ['action']},
    'runner': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['status', 'run']}},
               'required': ['action']},
}
# HAOS 2026-11-18: n8n reads the child refused with only their operation, for an argument that only its description
# requires (missing workflowId, versionId or query, or Invalid input).
HAOS_DESCRIBED_ONLY = ['n8n_manage_credentials:get', 'n8n_manage_credentials:getSchema',
                       'n8n_manage_datatable:getTable', 'n8n_manage_datatable:getRows', 'n8n_manage_folders:get',
                       'n8n_workflow_versions:list', 'n8n_workflow_versions:get', 'n8n_workflow_versions:diff',
                       'search_templates']
# p9_plan.DESCRIBED_REQUIRED was reviewed against these tools' inputSchemas in the snapshot (n8n-mcp 2.96.2): the
# sha256 of their JSON (sorted keys) in the order of their names. A new n8n-mcp version that changes one of them fails
# here: read their property descriptions again, update DESCRIBED_REQUIRED, then this digest.
REVIEWED_N8N_SCHEMAS = '5bc571f3470777f132e636767ae33a13fd73f3ad6661b5aec520e246f46f239a'


def snapshot_schemas(product):
    return p.snapshot_schemas(SNAPSHOT.read_bytes(), product)


def required_for(schema, arguments):
    """The names a child's inputSchema requires for these arguments: its own, and those of the oneOf/anyOf branch whose
    const values the arguments carry (Headscale's operations)."""
    names = set(schema.get('required', []))
    for branch in schema.get('oneOf') or schema.get('anyOf') or []:
        consts = {key: value['const'] for key, value in (branch.get('properties') or {}).items() if 'const' in value}
        if consts and all(arguments.get(key) == value for key, value in consts.items()):
            names |= set(branch.get('required', []))
    return names


class PlanTests(unittest.TestCase):
    def test_reads_denials_and_needs_args(self):
        result = p.plan('demo', SURFACE)
        self.assertEqual(result['reads'], [['health', {}], ['list', {'kind': 'tags'}],
                                           ['fields', {'model': 'res.partner', 'fields': ['id']}], ['executions', {'action': 'list'}]])
        self.assertEqual(result['needs_args'], ['get'])
        self.assertEqual(result['denials'], [
            ['create', {'name': 'p9-denied', 'nodes': []}], ['executions', {'action': 'delete'}],
            ['withheld_write', {}], ['update', {'model': 'res.partner', 'values': {'name': 'p9-denied'}}],
            ['odd_write', {}], ['delete', {'record_id': 2147483647}], ['definitely_not_a_tool', {}]])

    def test_overrides_fill_reads_and_denials(self):
        result = p.plan('demo', SURFACE, {'get': {'id': 'abc123'}, 'executions:delete': {'action': 'delete', 'id': 'none'}})
        self.assertIn(['get', {'id': 'abc123'}], result['reads'])
        self.assertEqual(result['needs_args'], [])
        self.assertIn(['executions', {'action': 'delete', 'id': 'none'}], result['denials'])

    def test_operations_follow_the_schema_branch_that_admits_them(self):
        surface = {'products': {'demo': {'tools': [
            {'name': 'runs', 'status': 'supported-bounded', 'effect': 'mixed', 'operation_parameter': 'action',
             'operation_effects': {'action': {'get': 'read', 'list': 'read', 'delete': 'write'}},
             'accepted_schema': {'properties': {'action': {'const': 'list'}, 'limit': {'type': 'integer', 'default': 20}},
                                 'required': ['action']}},
            {'name': 'folders', 'status': 'supported-bounded', 'effect': 'mixed', 'operation_parameter': 'action',
             'operation_effects': {'action': {'list': 'read', 'get': 'read', 'create': 'write', 'move': 'write'}},
             'accepted_schema': {
                 'properties': {'action': {'enum': ['list', 'get', 'create']}, 'projectId': {'type': 'string', 'default': 'personal'}},
                 'required': ['action'],
                 'oneOf': [
                     {'properties': {'action': {'const': 'list'}, 'folderId': {'type': 'null'}}, 'required': ['action']},
                     {'properties': {'action': {'const': 'get'}, 'folderId': {'type': 'string', 'pattern': '^[a-z]+$'},
                                     'projectId': {'not': {'const': 'personal'}}}, 'required': ['action', 'folderId', 'projectId']},
                     {'properties': {'action': {'const': 'create'}, 'name': {'type': 'string'}}, 'required': ['action', 'name']}]}},
        ]}}}
        result = p.plan('demo', surface)
        self.assertEqual(result['reads'], [['runs', {'action': 'list'}], ['folders', {'action': 'list'}]])
        self.assertEqual(result['needs_args'], ['folders:get'])
        self.assertEqual(result['denials'], [
            ['runs', {'action': 'get'}], ['runs', {'action': 'delete'}],
            ['folders', {'action': 'create', 'name': 'p9-denied'}], ['folders', {'action': 'move'}],
            ['definitely_not_a_tool', {}]])
        surface['products']['demo']['tools'].append(
            {'name': 'model', 'status': 'supported-bounded', 'effect': 'mixed', 'operation_parameter': None,
             'operation_effects': {'action': {'info': 'read', 'list_providers': 'read', 'set': 'write'}},
             'accepted_schema': {'properties': {'action': {'default': 'info', 'enum': ['info', 'list_providers']},
                                                'model': {'type': 'null', 'default': None}}}})
        result = p.plan('demo', surface)
        self.assertEqual(result['reads'][-2:], [['model', {'action': 'info'}], ['model', {'action': 'list_providers'}]])
        self.assertEqual(result['denials'][-2:], [['model', {'action': 'set'}], ['definitely_not_a_tool', {}]])
        filled = p.plan('demo', surface, {'folders:get': {'action': 'get', 'folderId': 'abc', 'projectId': 'p1'}})
        self.assertIn(['folders', {'action': 'get', 'folderId': 'abc', 'projectId': 'p1'}], filled['reads'])

    def test_a_full_surface_tool_reads_with_the_values_its_child_schema_declares(self):
        """supported-full (0.2.0 on) is supported as supported-bounded is. A full tool has no accepted_schema: its
        required arguments come from the child's inputSchema, and only a value that schema declares (default, an enum's
        first value, const) fills one. Any other required argument (an id, a name, a number) or no inputSchema at all
        puts the read under needs_args instead of sending it with {} (HAOS 2026-11-18: those reads failed)."""
        result = p.plan('demo', FULL, input_schemas=SCHEMAS)
        self.assertEqual(result['reads'], [['health', {}], ['list_kind', {'kind': 'tags'}], ['read_page', {'page': 1}],
                                           ['nodes', {'operation': 'list'}]])
        self.assertEqual(result['needs_args'],
                         ['read_record', 'read_attachment', 'read_optional', 'unlisted', 'nodes:get'])
        # A full tool's denial carries only its operation: the gateway refuses it by its write grant before the child
        # sees any argument (policy.authorize), as on HAOS 2026-11-18. An unverified-side-effects tool's grant is the
        # whole tool, as a write's is: its read operation is refused too.
        self.assertEqual(result['denials'], [
            ['delete_record', {}], ['nodes', {'operation': 'delete'}], ['agents', {'action': 'get'}],
            ['agents', {'action': 'create'}], ['runner', {'action': 'status'}], ['runner', {'action': 'run'}],
            ['withheld', {}], ['definitely_not_a_tool', {}]])
        filled = p.plan('demo', FULL, {'read_record': {'model': 'res.partner', 'record_id': 7},
                                       'nodes:get': {'operation': 'get', 'node_id': '1'}}, SCHEMAS)
        self.assertIn(['read_record', {'model': 'res.partner', 'record_id': 7}], filled['reads'])
        self.assertIn(['nodes', {'operation': 'get', 'node_id': '1'}], filled['reads'])
        self.assertEqual(filled['needs_args'], ['read_attachment', 'read_optional', 'unlisted'])
        # Without the snapshot nothing is known about a full tool's arguments: no read is guessed.
        bare = p.plan('demo', FULL)
        self.assertEqual(bare['reads'], [])
        self.assertEqual(bare['needs_args'], ['health', 'read_record', 'list_kind', 'read_page', 'read_attachment',
                                              'read_optional', 'unlisted', 'nodes:list', 'nodes:get'])

    def test_every_call_of_a_whole_tool_write_is_a_denial(self):
        """A write tool's grant is the whole tool (policy.Tool.grants), so with every write off the gateway refuses each
        of its calls, its read operations too: on HAOS 2026-11-18 n8n_manage_agents and n8n_test_workflow's read
        operations, planned as reads, were refused as an unknown tool. Bounded or full alike, and an unverified tool's
        grant is the whole tool as well."""
        for status, schema in [('supported-bounded', {'properties': {'action': {'enum': ['get', 'create']}},
                                                      'required': ['action']}), ('supported-full', None)]:
            for effect in ('write', 'unverified-side-effects'):
                with self.subTest(status=status, effect=effect):
                    surface = {'products': {'demo': {'tools': [
                        {'name': 'agents', 'status': status, 'effect': effect, 'operation_parameter': 'action',
                         'operation_effects': {'action': {'get': 'read', 'create': 'write'}},
                         'accepted_schema': schema}]}}}
                    result = p.plan('demo', surface, input_schemas={'agents': SCHEMAS['agents']})
                    self.assertEqual((result['reads'], result['needs_args']), ([], []))
                    self.assertEqual(result['denials'][:2],
                                     [['agents', {'action': 'get'}], ['agents', {'action': 'create'}]])

    def test_a_read_whose_child_requires_an_argument_only_its_description_states_needs_args(self):
        """n8n-mcp states some requirements only in property descriptions (no if/then or dependentRequired in an
        inputSchema), so no schema rule sees them: sent with the operation alone, those reads were refused on HAOS
        2026-11-18. The reviewed table p9_plan.DESCRIBED_REQUIRED lists them under needs_args; overrides fill them as
        they fill any other."""
        with mock.patch.dict(p.DESCRIBED_REQUIRED, {'demo': {'health': ('scope',), 'nodes:list': ('owner',)}}):
            result = p.plan('demo', FULL, input_schemas=SCHEMAS)
            self.assertEqual(result['reads'], [['list_kind', {'kind': 'tags'}], ['read_page', {'page': 1}]])
            self.assertEqual(result['needs_args'], ['health', 'read_record', 'read_attachment', 'read_optional',
                                                    'unlisted', 'nodes:list', 'nodes:get'])
            filled = p.plan('demo', FULL, {'health': {'scope': 'all'},
                                           'nodes:list': {'operation': 'list', 'owner': 'me'}}, SCHEMAS)
            self.assertEqual(filled['reads'][:1], [['health', {'scope': 'all'}]])
            self.assertIn(['nodes', {'operation': 'list', 'owner': 'me'}], filled['reads'])
            self.assertEqual(filled['needs_args'], ['read_record', 'read_attachment', 'read_optional', 'unlisted',
                                                    'nodes:get'])
            other = p.plan('other', {'products': {'other': FULL['products']['demo']}}, input_schemas=SCHEMAS)
            self.assertIn(['health', {}], other['reads'])  # each product has its own table
        surface = json.loads((ROOT / 'docs/tool-surface.json').read_text())
        schemas = snapshot_schemas('n8n')
        result = p.plan('n8n', surface, input_schemas=schemas)
        reviewed = p.DESCRIBED_REQUIRED['n8n']
        self.assertTrue(set(HAOS_DESCRIBED_ONLY) <= set(reviewed) <= set(result['needs_args']))
        tools = {tool['name']: tool for tool in surface['products']['n8n']['tools']}
        planned = {name for name, _ in result['reads']}
        for key, names in reviewed.items():
            with self.subTest(key=key):
                name, _, operation = key.partition(':')
                tool = tools[name]
                self.assertEqual(tool['status'], 'supported-full')
                if operation:
                    selector = tool['operation_parameter']
                    self.assertEqual(tool['operation_effects'][selector][operation], 'read')
                    self.assertNotIn(operation, [arguments.get(selector) for read, arguments in result['reads']
                                                 if read == name])
                else:
                    self.assertEqual(tool['effect'], 'read')
                    self.assertNotIn(name, planned)
                # Each named argument is in the child's inputSchema but not in its required list: only its description
                # requires it, and nothing in the schema states a condition.
                schema = schemas[name]
                self.assertTrue(set(names) <= set(schema['properties']))
                self.assertFalse(set(names) & set(schema.get('required', [])))
                self.assertFalse({'if', 'then', 'oneOf', 'anyOf', 'allOf', 'dependentRequired'} & set(schema))
        pinned = sorted({key.partition(':')[0] for key in reviewed})
        digest = hashlib.sha256(json.dumps([schemas[name] for name in pinned], sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, REVIEWED_N8N_SCHEMAS,
                         'n8n-mcp changed a tool of p9_plan.DESCRIBED_REQUIRED: review the table against its property '
                         'descriptions, then pin the new digest')

    def test_every_product_in_the_repository_surface_produces_a_plan(self):
        surface = json.loads((ROOT / 'docs/tool-surface.json').read_text())
        for product, value in surface['products'].items():
            with self.subTest(product=product):
                schemas = snapshot_schemas(product)
                result = p.plan(product, surface, input_schemas=schemas)
                listed = len(result['reads']) + len(result['needs_args']) + len(result['denials'])
                self.assertGreaterEqual(listed, len(value['tools']) + 1)
                self.assertEqual(result['denials'][-1], ['definitely_not_a_tool', {}])
                tools = {t['name']: t for t in value['tools']}
                self.assertTrue({r[0] for r in result['reads']} <= set(tools))
                self.assertTrue(result['reads'], 'a product with read tools gets reads (0.2.0 on: supported-full)')
                for tool in tools.values():
                    if tool['status'] == 'supported-full':
                        self.assertIn(tool['name'], schemas, 'every full tool has its inputSchema in the snapshot')
                    if tool['status'] != 'temporarily-unsupported':
                        # the generator's rule (an effect that is neither read nor mixed is a whole-tool write) is the
                        # gateway's: such a tool's grant is its own name
                        self.assertEqual(tool['effect'] not in ('read', 'mixed'), tool['name'] in tool['write_grants'])
                for name, arguments in result['reads']:
                    self.assertIn(tools[name]['effect'], ('read', 'mixed'))
                    if tools[name]['status'] == 'supported-full':
                        missing = required_for(schemas[name], arguments) - set(arguments)
                        self.assertFalse(missing, '%s is read without its required %s' % (name, sorted(missing)))
        odoo = p.plan('odoo', surface, input_schemas=snapshot_schemas('odoo'))
        self.assertIn(['health_check', {}], odoo['reads'])
        self.assertTrue({'read_record', 'search_records', 'get_model_fields'} <= set(odoo['needs_args']))

    def test_cli_records_the_surface_digest(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = p.main(['n8n'])
        self.assertEqual(len(result['tool_surface_sha256']), 64)
        self.assertEqual(result['tool_snapshot_sha256'], hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest())
        self.assertEqual(json.loads(out.getvalue())['product'], 'n8n')
        self.assertIn(['tools_documentation', {}], result['reads'])

    def test_cli_reads_the_full_tools_schemas_from_the_snapshot_file(self):
        """--surface and --snapshot name the two inputs; the snapshot's LISTED is parsed, never imported."""
        with tempfile.TemporaryDirectory() as directory:
            surface, snapshot = Path(directory) / 'surface.json', Path(directory) / 'snapshot.py'
            surface.write_text(json.dumps(FULL))
            listed = {'demo': [{'name': name, 'inputSchema': schema} for name, schema in SCHEMAS.items()]}
            snapshot.write_text('"""A snapshot."""\nraise SystemExit("imported")\nLISTED = %r\n' % listed)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = p.main(['demo', '--surface', str(surface), '--snapshot', str(snapshot)])
            self.assertEqual(json.loads(out.getvalue()), result)
            self.assertEqual(result['reads'], p.plan('demo', FULL, input_schemas=SCHEMAS)['reads'])
            self.assertEqual(result['tool_snapshot_sha256'], hashlib.sha256(snapshot.read_bytes()).hexdigest())
            self.assertEqual(result['tool_surface_sha256'], hashlib.sha256(surface.read_bytes()).hexdigest())
            self.assertEqual(sorted(result), ['denials', 'needs_args', 'product', 'reads', 'tool_snapshot_sha256',
                                              'tool_surface_sha256'])


if __name__ == '__main__':
    unittest.main()
