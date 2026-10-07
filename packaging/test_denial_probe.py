"""Dispatch-only mutation; real schemas/list filter, owned in-process HTTP fake."""
import asyncio
import copy
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
import httpx
from mcp_admin_core import policy
from mcp_admin_core.products import TOOLS, ProductState
from n8n_adapter import TOOLS as N8N
from denial_probe import assert_denials, WRITE_CASES


class DenialTests(unittest.TestCase):
    def exercise(self, product, authorize):
        tools = N8N if product == 'n8n' else TOOLS[product]
        state = ProductState(product=product, token='a' * 43, child_token='b' * 43)
        calls = []
        async def fake(request):
            import json
            try:
                authorize(json.loads(request.content), tools, state)
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
            self.assertEqual(listed['result']['tools'], [] if tools[name].write else [{'name':name, 'inputSchema':policy.declared_schema(tools[name].arguments)}])
            for args, disabled in (({'unreviewed': True}, []), (arguments, [name])):
                with self.assertRaises(policy.Denied):
                    ns['authorize']({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': copy.deepcopy(args)}},
                        tools, state.model_copy(update={'disabled': disabled}))
            with self.subTest(product=product), self.assertRaisesRegex(AssertionError, 'schema-valid supported write: HTTP denial missing'):
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
