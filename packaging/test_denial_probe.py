"""Dispatch-only mutation; real schemas/list filter, owned in-process HTTP fake."""
import asyncio
import copy
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
import httpx
from mcp_admin_core import policy
from mcp_admin_core.products import TOOLS, ProductState
from n8n_adapter import TOOLS as N8N
import denial_probe
from denial_probe import assert_denials, WRITE_CASES


class DenialTests(unittest.TestCase):
    def exercise(self, product, authorize):
        tools = N8N if product == 'n8n' else TOOLS[product]
        state = ProductState(product=product, token='a' * 43, child_token='b' * 43)
        calls = []
        async def fake(request):
            import json
            message = json.loads(request.content)
            try:
                authorize(message, tools, state)
            except policy.ToolCallRefused as refused:  # the gateway's 0.1.14 answer
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'error': refused.error()})
            except policy.Denied:
                return httpx.Response(403)
            calls.append('OWNED fake backend only')
            return httpx.Response(200, json={})
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
                await assert_denials(client, 'http://owned.invalid/mcp', {}, product, lambda: len(calls))
        asyncio.run(run())

    def test_production_dispatch_denies_valid_writes(self):
        for product in ('n8n', *TOOLS):
            with self.subTest(product=product):
                self.exercise(product, policy.authorize)

    def test_only_dispatch_write_gate_removed_probe_fails(self):
        ns = dict(vars(policy))
        ns['dispatch_enabled'] = lambda name, tools, state: name in tools and name not in state.disabled
        source = inspect.getsource(policy.authorize)
        mutated = source.replace('not enabled(name, tools, state)', 'not dispatch_enabled(name, tools, state)')
        mutated = mutated.replace("if f'{name}:{normalized[tool.selector]}' not in getattr(state, 'enabled_write_tools', ()):", "if False:  # only dispatch operation grant removed")
        self.assertNotEqual(source, mutated)
        exec(compile(mutated, '<dispatch-only-mutation>', 'exec'), ns)
        for product, (name, arguments) in WRITE_CASES.items():
            tools = N8N if product == 'n8n' else TOOLS[product]
            tools[name].arguments.model_validate(arguments)  # schema-valid, not a malformed false pass
            state = ProductState(product=product, token='a' * 43, child_token='b' * 43)
            listed = policy.filter_list({'result': {'tools': [{'name': name}]}}, tools, state)
            # 0.1.6 (AI Stage 0): the declared form of the local model (hermes_skill loses its top-level oneOf).
            self.assertEqual(listed['result']['tools'], [] if tools[name].write else [{'name':name, 'inputSchema':
                policy.child_input_schema(None) if tools[name].child_schema else policy.declared_schema(tools[name].arguments)}])
            # 0.2.0: a full-surface tool forwards any object to the child, so only a bounded model refuses extra keys.
            cases = ((arguments, [name]),) if tools[name].child_schema else (({'unreviewed': True}, []), (arguments, [name]))
            for args, disabled in cases:
                with self.assertRaises(policy.Denied):
                    ns['authorize']({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': copy.deepcopy(args)}},
                        tools, state.model_copy(update={'disabled': disabled}))
            with self.subTest(product=product), self.assertRaisesRegex(AssertionError, 'schema-valid supported write: refusal missing'):
                self.exercise(product, ns['authorize'])

    def test_denial_status_without_zero_backend_delta_fails(self):
        async def run():
            calls = []
            async def false_denial(request):
                calls.append(1)
                return httpx.Response(403)
            async with httpx.AsyncClient(transport=httpx.MockTransport(false_denial)) as client:
                with self.assertRaises(AssertionError):
                    await assert_denials(client, 'http://owned.invalid/mcp', {}, 'n8n', lambda: len(calls))
        asyncio.run(run())

    def test_a_failure_names_the_requests_that_reached_the_backend(self):
        """A probe run that can list the mock's requests (REACHED) says which ones: method and path, never the query."""
        async def run():
            calls = []
            async def refused_but_contacted(request):
                calls.append(('GET', '/api/v1/health?token=never-shown'))
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 5, 'error': {
                    'code': -32602, 'message': 'Unknown tool', 'data': {'tool': 'unknown'}}})
            async def failure(**patched):
                calls.clear()
                with patch.multiple(denial_probe, **patched):
                    with self.assertRaises(AssertionError) as raised:
                        await assert_denials(client, 'http://owned.invalid/mcp', {}, 'n8n', lambda: len(calls))
                return str(raised.exception)
            async with httpx.AsyncClient(transport=httpx.MockTransport(refused_but_contacted)) as client:
                self.assertEqual(await failure(REACHED=None, SYNCED=None), 'unknown tool: backend contacted')  # as before
                self.assertEqual(await failure(REACHED=lambda: list(calls), SYNCED=None),
                                 'unknown tool: backend contacted (GET /api/v1/health)')
                self.assertEqual(await failure(REACHED=lambda: list(calls), SYNCED=True),
                                 'unknown tool: backend contacted (GET /api/v1/health)')
                self.assertEqual(await failure(REACHED=lambda: list(calls), SYNCED=False),
                                 'unknown tool: backend contacted (GET /api/v1/health); '
                                 'no backend check of the gateway was seen before the denial checks')
        asyncio.run(run())

    def test_the_text_lists_at_most_six_requests(self):
        calls = [('GET', f'/p{number}') for number in range(10)]
        with patch.multiple(denial_probe, REACHED=lambda: calls, SYNCED=None):
            self.assertEqual(denial_probe.reached(2), ' (GET /p2, GET /p3, GET /p4, GET /p5, GET /p6, GET /p7)')
        with patch.multiple(denial_probe, REACHED=None, SYNCED=None):
            self.assertEqual(denial_probe.reached(2), '')
