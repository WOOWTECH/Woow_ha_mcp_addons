"""No sockets/child services: preflight the actual cross-cutting read fixtures.

This tests the real gateway authorization/dispatch seam, NOT backend redaction;
the original two real-child tests remain mandatory after an owned runtime slot.
"""
import json

import httpx
import pytest
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from test_stream_error_redaction import http_read_arguments
from test_six_hardening import call


@pytest.mark.parametrize('json_response', [False, True])
async def test_cross_cutting_litellm_read_arguments_reach_dispatch(tmp_path, json_response):
    calls = []
    def dispatch(request):
        message = json.loads(request.content)
        calls.append(message)
        reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': []}}
        if json_response:
            return httpx.Response(200, json=reply)
        return httpx.Response(200, text='event: message\ndata: '+json.dumps(reply)+'\n\n',
                              headers={'Content-Type': 'text/event-stream'})

    store = ProductStore(tmp_path, 'litellm')
    try:
        store.update(connection={'url': 'http://unused.invalid', 'master_key': 'DUMMY'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as child:
            _, app = make_apps(store, TOOLS['litellm'], child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                headers = {'Authorization': 'Bearer '+store.load().token,
                           'Accept': 'application/json, text/event-stream',
                           'Mcp-Session-Id': 'test-session'}  # 0.1.8: only initialize comes without one
                for name, tool in TOOLS['litellm'].items():
                    if tool.write:
                        continue
                    args = http_read_arguments('litellm', name)
                    before = len(calls)
                    response = await client.post('/mcp', headers=headers, json=call(name, args))
                    assert len(calls) == before + 1, (name, args, response.text)
                    assert response.status_code == 200
                    assert calls[-1]['params']['arguments'] == tool.arguments.model_validate(args).model_dump(mode='json')
    finally:
        store.close()
