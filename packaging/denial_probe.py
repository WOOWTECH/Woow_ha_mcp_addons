"""Shared image assertion. No real writes: probe runs only against owned fakes."""
WRITE_CASES = {
    'n8n': ('n8n_delete_workflow', {'id': 'fixture'}),
    'opendesign': ('delete_project', {'project_id': '00000000-0000-0000-0000-000000000001'}),
    'odoo': ('chatter_post', {'model':'res.partner', 'record_id':1, 'body':'Owned test comment'}),
    'odoo-manage': ('create_record', {'model':'res.partner', 'values':{'name':'Owned'}}),
    'hermes': ('hermes_skill', {'action':'disable', 'name':'example'}),
    'emqx': ('emqx_kick_client', {'clientid':'device'}),
    'litellm': ('litellm_create_team', {'team_alias':'Owned'}),
    'nextcloud': ('create_text_file', {'path':'Owned/denied.md', 'content':'Owned'}),
}


REFUSALS = ('Unknown tool', 'Operation not permitted', 'Invalid params')


async def assert_denials(client, endpoint, headers, product, backend_count):
    cases = [('unknown tool', 'unknown', {})]
    name, arguments = WRITE_CASES[product]
    cases += [('schema-valid supported write', name, arguments),
              ('malformed supported write', name, {'unreviewed': True})]
    for label, name, arguments in cases:
        before = backend_count()
        response = await client.post(endpoint, headers=headers, json={
            'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}})
        # 0.1.14: inside a session a refused well-formed call is the gateway's own JSON-RPC error (HTTP 200), not 403:
        # "Unknown tool" for a missing tool or a write tool without its grant (whatever its arguments), "Operation not
        # permitted" for a write operation of a read tool, "Invalid params" for its malformed arguments. Never a result.
        reply = response.json() if response.status_code == 200 else None
        error = reply.get('error') if isinstance(reply, dict) and 'result' not in reply else None
        assert (isinstance(error, dict) and error.get('code') == -32602 and error.get('message') in REFUSALS
                and error.get('data', {}).get('tool') == name), label + ': refusal missing'
        assert backend_count() == before, label + ': backend contacted'
