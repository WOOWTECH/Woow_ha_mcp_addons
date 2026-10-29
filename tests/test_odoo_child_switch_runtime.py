"""Actual isolated Odoo child against an in-memory fake XML-RPC backend; no tenant or real HA calls."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.products import ProductStore, child_spec
from owned_runtime import Endpoint
from test_expansion_runtime import fake_api
from test_real_products import connection, rpc

ALL_ON = dict(enable_writes=True, allow_direct_writes=True, allow_unknown_methods=True, chatter_direct=True)
INIT = {'jsonrpc':'2.0', 'id':1, 'method':'initialize', 'params':{
    'protocolVersion':'2025-11-25', 'capabilities':{}, 'clientInfo':{'name':'switch-test', 'version':'0'}}}


async def call(child, url, headers, ident, name, arguments):
    result = await rpc(child, url, headers, {'jsonrpc':'2.0', 'id':ident, 'method':'tools/call',
                                            'params':{'name':name, 'arguments':arguments}})
    value = result.get('structuredContent') or result
    value = value['result'] if isinstance(value, dict) and set(value) == {'result'} and isinstance(value['result'], dict) else value
    if isinstance(value, dict) and isinstance(value.get('success'), bool):
        # PR30 must wrap PR31's refusal as well as the original wheel's result.
        assert result.get('isError', False) is (value['success'] is False), result
        if value['success'] is False:
            assert json.loads(result['content'][0]['text']) == value
    return value


@pytest.mark.parametrize('off', [None, 'enable_writes', 'allow_direct_writes',
                                 'allow_unknown_methods', 'chatter_direct'])
async def test_each_switch_changes_real_child_behavior_without_unexpected_writes(tmp_path, off):
    values = {**ALL_ON, **({off:False} if off else {})}
    with fake_api() as (backend, _events, mutations, failures), closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', backend), odoo_write_switches=values)
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                headers = {'Authorization':'Bearer ' + store.load().child_token,
                           'Accept':'application/json, text/event-stream'}
                async with asyncio.timeout(25):
                    while True:
                        try:
                            init = await rpc(child, endpoint.url, headers, INIT)
                            break
                        except (ValueError, httpx.HTTPError):
                            await asyncio.sleep(.1)
                headers['MCP-Protocol-Version'] = init['protocolVersion']
                await rpc(child, endpoint.url, headers, {'jsonrpc':'2.0', 'method':'notifications/initialized'})
                health = await call(child, endpoint.url, headers, 2, 'health_check', {})
                runtime = health['runtime']
                assert runtime['write_execution_enabled'] is values['enable_writes']
                assert runtime['direct_writes_enabled'] is values['allow_direct_writes']
                assert runtime['unknown_execute_method_enabled'] is values['allow_unknown_methods']
                assert runtime['chatter_direct_enabled'] is values['chatter_direct']
                assert runtime['broad_unknown_method_mode']['enabled'] is (
                    values['enable_writes'] and values['allow_direct_writes'] and values['allow_unknown_methods'])

                read = await call(child, endpoint.url, headers, 3, 'execute_method',
                                  {'model':'res.partner', 'method':'search_count', 'args':[[]]})
                assert read.get('success') is True, read
                assert not mutations
                create = await call(child, endpoint.url, headers, 4, 'execute_method',
                                    {'model':'res.partner', 'method':'create', 'args':[{'name':'FAKE'}]})
                should_create = values['enable_writes'] and values['allow_direct_writes']
                assert create['success'] is should_create
                assert len(mutations) == int(should_create)

                if off in ('enable_writes', 'allow_direct_writes'):
                    write = {'model':'res.partner', 'operation':'create', 'values':{'name':'FAKE APPROVED'}}
                    preview = await call(child, endpoint.url, headers, 8, 'preview_write', write)
                    validated = await call(child, endpoint.url, headers, 9, 'validate_write', write)
                    assert preview['success'] is True and validated['success'] is True
                    assert validated['valid'] is True and not mutations
                    approved = await call(child, endpoint.url, headers, 10, 'execute_approved_write',
                                          {'approval':validated['approval'], 'confirm':True})
                    assert approved['success'] is (off == 'allow_direct_writes'), approved
                    assert len(mutations) == int(off == 'allow_direct_writes')

                before = len(mutations)
                unknown = await call(child, endpoint.url, headers, 5, 'execute_method',
                                     {'model':'res.partner', 'method':'action_confirm', 'args':[[1]]})
                should_unknown = values['enable_writes'] and values['allow_direct_writes'] and values['allow_unknown_methods']
                assert unknown['success'] is should_unknown
                assert len(mutations) == before + int(should_unknown)
                if off in ('enable_writes', 'allow_direct_writes', 'allow_unknown_methods'):
                    # Upstream classifies get_* by name as read-only; the PaaS #89 reviewed-read rule must win.
                    before = len(mutations)
                    guessed_read = await call(child, endpoint.url, headers, 11, 'execute_method',
                                              {'model':'res.partner', 'method':'get_portal_url', 'args':[[1]]})
                    assert guessed_read['success'] is False
                    assert len(mutations) == before
                if off == 'chatter_direct':
                    before = len(mutations)
                    bypass = await call(child, endpoint.url, headers, 12, 'execute_method',
                                        {'model':'res.partner', 'method':'message_post', 'args':[[1]],
                                         'kwargs':{'body':'Synthetic bypass attempt'}})
                    assert bypass['success'] is False
                    assert len(mutations) == before

                before = len(mutations)
                chatter = await call(child, endpoint.url, headers, 6, 'chatter_post',
                                     {'model':'res.partner', 'record_id':1, 'body':'Synthetic comment'})
                if not values['enable_writes']:
                    assert chatter['success'] is False and len(mutations) == before
                elif not values['chatter_direct']:
                    assert chatter['mode'] == 'preview' and len(mutations) == before
                    posted = await call(child, endpoint.url, headers, 7, 'chatter_post',
                                        {'model':'res.partner', 'record_id':1, 'body':'Synthetic comment',
                                         'approval':chatter['approval'], 'confirm':True})
                    assert posted['success'] is True and len(mutations) == before + 1
                else:
                    assert chatter['mode'] == 'direct' and len(mutations) == before + 1
                await child.delete(endpoint.url, headers=headers)
        finally:
            await process.stop()
            endpoint.close()
    assert not failures


def test_overlay_fails_closed_before_touching_tool_when_pinned_wheel_drifts():
    root = Path(__file__).resolve().parents[1]
    code = ("from odoo_mcp.server import mcp\n"
            "import odoo_switch_overlay as overlay\n"
            "tool = mcp._tool_manager.get_tool('execute_method')\n"
            "original = tool.fn\n"
            "overlay.SOURCES['tools_write'] = '0' * 64\n"
            "try: overlay.install(mcp)\n"
            "except RuntimeError: pass\n"
            "else: raise AssertionError('drift accepted')\n"
            "assert tool.fn is original\n")
    env = {'PATH':'/usr/bin:/bin', 'PYTHONPATH':':'.join((str(root / 'packages/mcp-admin-core'),
                                                     str(root / 'apps/odoo'), str(root / 'apps/runtime'))),
           'PYTHONDONTWRITEBYTECODE':'1'}
    completed = subprocess.run([str(root / 'apps/odoo/.venv/bin/python'), '-c', code], cwd=root, env=env,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr[-1500:]
