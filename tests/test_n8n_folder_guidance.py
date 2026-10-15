"""Genuine public gateway/child; synthetic HTTP failures, never a licensed backend."""
import asyncio
import json
import pytest
import test_batch2_n8n_public_errors as owned
from test_expansion_policy import call
from test_real_products import rpc

FOLDER_MESSAGES = {
    'FORBIDDEN': 'Folder access denied. Verify folder entitlement (Registered Community or eligible plan), API key folder scopes, and project access.',
    'NOT_FOUND': 'Folder API route or resource not found. Verify backend folder API support and explicit project/folder IDs.',
}

# 0.2.0: folder get is the pinned handler as published (no B3 metadata_reads boundary): its failures get the generic
# public message, like every other unwrapped handler.
@pytest.mark.parametrize('action', ['list', 'create', 'rename'])
async def test_folder_guidance_is_fixed_and_does_not_infer_cause(tmp_path, monkeypatch, action):
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (store, state, client, headers, wire, dispatches):
        args = {'action':action, 'projectId':'project1'}
        write = action in ('create', 'rename')
        if write:
            args['name'] = 'Owned'
            store.update(enabled_write_tools=['n8n_manage_folders:'+action])
        if action in ('get', 'rename'):
            args['folderId'] = 'folder1'
        for status, code in [(403, 'FORBIDDEN'), (404, 'NOT_FOUND')]:
            state['case'] = status
            before = len(state['calls'])
            reply = await rpc(client, '/mcp', headers, call('n8n_manage_folders', args))
            value = json.loads(reply['content'][0]['text'])
            assert value == {'success':False,'code':code,'error':FOLDER_MESSAGES[code] + (
                ' Write outcome may be unknown; verify before retrying.' if write else '')}
            assert len(state['calls']) == before + 1  # no entitlement lookup, retry or REST fallback
            assert owned.KEY not in json.dumps(reply) and owned.PRIVATE not in json.dumps(reply)
            assert 'license_required' not in json.dumps(reply)

async def test_workflow_forbidden_keeps_generic_contract(tmp_path):
    async with asyncio.timeout(50), owned.runtime(tmp_path) as (_, state, client, headers, wire, _):
        state['case'] = 403
        reply = await rpc(client, '/mcp', headers, call('n8n_list_workflows', {'limit':1}))
        owned.error_result(reply, wire, 'FORBIDDEN')
