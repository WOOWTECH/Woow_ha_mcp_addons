"""Offline tests for the P9 plan generator."""
import contextlib
import io
import json
from pathlib import Path
import unittest

import p9_plan as p

ROOT = Path(__file__).resolve().parents[1]
SURFACE = {'products': {'demo': {'tools': [
    {'name': 'health', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {'properties': {}}},
    {'name': 'list', 'status': 'supported-bounded', 'effect': 'read', 'accepted_schema': {
        'properties': {'limit': {'type': 'integer', 'minimum': 1, 'default': 10},
                       'kind': {'enum': ['tags', 'projects']}}, 'required': ['kind']}},
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


class PlanTests(unittest.TestCase):
    def test_reads_denials_and_needs_args(self):
        result = p.plan('demo', SURFACE)
        self.assertEqual(result['reads'], [['health', {}], ['list', {'kind': 'tags'}], ['executions', {'action': 'list'}]])
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

    def test_every_product_in_the_repository_surface_produces_a_plan(self):
        surface = json.loads((ROOT / 'docs/tool-surface.json').read_text())
        for product, value in surface['products'].items():
            with self.subTest(product=product):
                result = p.plan(product, surface)
                listed = len(result['reads']) + len(result['needs_args']) + len(result['denials'])
                self.assertGreaterEqual(listed, len(value['tools']) + 1)
                self.assertEqual(result['denials'][-1], ['definitely_not_a_tool', {}])
                names = {t['name'] for t in value['tools']}
                self.assertTrue({r[0] for r in result['reads']} <= names)

    def test_cli_records_the_surface_digest(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = p.main(['n8n'])
        self.assertEqual(len(result['tool_surface_sha256']), 64)
        self.assertEqual(json.loads(out.getvalue())['product'], 'n8n')


if __name__ == '__main__':
    unittest.main()
