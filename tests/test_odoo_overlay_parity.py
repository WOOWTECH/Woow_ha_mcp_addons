"""LOCAL/MOCK: two parity fixes of the Odoo write-switch overlay (unreleased, 0.4.12 line), found on 2026-11-06 by running the four
switches in five combinations against the same real Odoo on HA 0.4.10 and on PaaS 21ec3be8 (stage C).

C1. With "Allow Unreviewed Methods" off, HA refused nine of the eighteen methods of the reviewed read list that PaaS runs
    (search_fetch, read_group, web_read, web_search_read, web_read_group, web_name_search, read_progress_bar,
    formatted_read_group, formatted_read_grouping_sets) with the wheel's own text "Unreviewed side-effect methods are blocked by
    default". The overlay's gate let them through, but the wheel's execute_method guard then classified them by name; PaaS replaces
    that guard. The overlay now corrects the classification execute_method consults, for the reviewed list only.
C2. health_check.server.tool_count was 42 on HA and 41 on PaaS: the launcher's private readiness probe (woow_backend_probe) was counted.

Genuine pinned Odoo child (the real odoo-mcp 1.3.0 client, the add-on's XML-RPC transport and the overlay) against an owned stdlib
XML-RPC peer that answers every execute_kw with True and records what reached it.
"""
import asyncio
from contextlib import closing
import json
import threading
import xmlrpc.client

import httpx
import pytest

from mcp_admin_core.products import ProductStore, child_spec
from mcp_admin_core import odoo_write_gates as gates
from owned_runtime import Endpoint
from test_odoo_child_switch_runtime import ALL_ON, INIT, call
from test_real_products import connection, rpc
from test_six_hardening import Quiet, serve

BLOCKED = 'Unreviewed side-effect methods are blocked by default'
# The eighteen methods of the reviewed read list (PaaS write_gates.REVIEWED_READ_METHODS), on the model each is called on.
REVIEWED = sorted(gates.REVIEWED_READ_METHODS)
NINE = ['formatted_read_group', 'formatted_read_grouping_sets', 'read_group', 'read_progress_bar', 'search_fetch', 'web_name_search',
        'web_read', 'web_read_group', 'web_search_read']
# Not on the list: refused whenever Allow Unreviewed Methods or Allow Direct Writes or the master gate is off, as before.
NOT_REVIEWED = ['action_confirm', 'copy', 'toggle_active', 'get_portal_url', 'default_get']


def odoo_peer(seen):
    class Handler(Quiet):
        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            value = 7 if method == 'authenticate' else True
            if method == 'execute_kw':
                seen.append((params[3], params[4]))
            self.reply(xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode())
    return Handler


class Child:
    """One Odoo child with the given switches; `call(tool, arguments)` goes straight to it."""

    def __init__(self, child, url, headers):
        self.child, self.url, self.headers, self.ident = child, url, headers, 100

    async def call(self, name, arguments):
        self.ident += 1
        return await call(self.child, self.url, self.headers, self.ident, name, arguments)

    async def listing(self):
        self.ident += 1
        result = await rpc(self.child, self.url, self.headers, {'jsonrpc': '2.0', 'id': self.ident, 'method': 'tools/list'})
        return [tool['name'] for tool in result['tools']]


async def started(store, endpoint, child):
    headers = {'Authorization': 'Bearer ' + store.load().child_token, 'Accept': 'application/json, text/event-stream'}
    async with asyncio.timeout(25):
        while True:
            try:
                init = await rpc(child, endpoint.url, headers, INIT)
                break
            except (ValueError, httpx.HTTPError):
                await asyncio.sleep(.1)
    headers['MCP-Protocol-Version'] = init['protocolVersion']
    await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return Child(child, endpoint.url, headers)


def method_call(method):
    model = 'res.users' if method == 'context_get' else 'res.partner'
    return {'model': model, 'method': method, 'args': [[1]] if method not in ('search', 'search_count', 'search_read') else [[]]}


@pytest.mark.parametrize('off', [None, 'enable_writes', 'allow_direct_writes', 'allow_unknown_methods', 'chatter_direct'])
async def test_every_method_of_the_reviewed_read_list_reaches_odoo_under_every_switch_combination(tmp_path, off):
    """PaaS (apps/odoo/docs/write-switches.md): the reviewed reads run in every combination, whatever the other switches say."""
    seen = []
    values = {**ALL_ON, **({off: False} if off else {})}
    with serve(odoo_peer(seen)) as url, closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', url), odoo_write_switches=values)
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as raw:
                child = await started(store, endpoint, raw)
                for method in REVIEWED:
                    before = len(seen)
                    answer = await child.call('execute_method', method_call(method))
                    assert answer.get('success') is True and BLOCKED not in json.dumps(answer), (off, method, answer)
                    assert len(seen) == before + 1 and seen[-1][1] == method, (off, method, seen[before:])
                # What is not on the list keeps its rule: refused (and never sent to Odoo) unless every switch lets any method run.
                every_method_runs = off is None or off == 'chatter_direct'
                for method in NOT_REVIEWED:
                    before = len(seen)
                    answer = await child.call('execute_method', method_call(method))
                    assert (answer.get('success') is True) is every_method_runs, (off, method, answer)
                    assert len(seen) == before + int(every_method_runs), (off, method)
                await raw.delete(endpoint.url, headers=child.headers)
        finally:
            await process.stop()
            endpoint.close()


async def test_nine_methods_were_refused_by_the_wheel_guard_before_the_fix_and_the_diagnostics_keep_upstream_classification(tmp_path):
    """The exact configuration of the stage-C finding (Allow Unreviewed Methods off, the rest on). The nine are the ones upstream's
    READ_ONLY_METHODS lacks; diagnose_odoo_call still reports upstream's classification for them (as PaaS does): the fix is
    limited to what execute_method consults."""
    assert sorted(set(REVIEWED) & set(NINE)) == NINE and len(REVIEWED) == 18
    seen = []
    values = {**ALL_ON, 'allow_unknown_methods': False}
    with serve(odoo_peer(seen)) as url, closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', url), odoo_write_switches=values)
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as raw:
                child = await started(store, endpoint, raw)
                for method in NINE:
                    answer = await child.call('execute_method', method_call(method))
                    assert answer['success'] is True, (method, answer)
                refused = await child.call('execute_method', method_call('action_confirm'))
                assert refused['success'] is False and BLOCKED in refused['error'], refused  # still the wheel's own refusal for what is not on the list
                for method in ('read_group', 'web_search_read'):
                    report = await child.call('diagnose_odoo_call', {'model': 'res.partner', 'method': method})
                    assert report['success'] is True and report['classification']['safety'] == 'unknown', report
                await raw.delete(endpoint.url, headers=child.headers)
        finally:
            await process.stop()
            endpoint.close()


async def test_health_check_counts_the_published_tools_only(tmp_path):
    seen = []
    with serve(odoo_peer(seen)) as url, closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', url), odoo_write_switches=ALL_ON)
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as raw:
                child = await started(store, endpoint, raw)
                listed = await child.listing()
                assert listed.count('woow_backend_probe') == 1  # the child registers it; the gateway never lists it
                health = await child.call('health_check', {})
                assert health['server']['tool_count'] == len(listed) - 1 == 41, (health['server'], len(listed))
                await raw.delete(endpoint.url, headers=child.headers)
        finally:
            await process.stop()
            endpoint.close()
