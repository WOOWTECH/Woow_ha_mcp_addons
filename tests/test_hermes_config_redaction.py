"""0.2.2 (test VM 2026-10-16, G1): hermes_config get returned Hermes' GET /api/config verbatim, so a custom provider's
custom_providers[].api_key (set through the Hermes dashboard) reached the MCP client in plain text. A config read now keeps
every field name and whether a secret is set, never its value; writes are unchanged. The real Hermes child against a
LOCAL fake dashboard. Not the "backend errors carry their own text" decision: these are credentials the backend holds.
"""
import json

from test_six_hardening import Quiet, call, runtime, serve

PROVIDER_KEY = 'held-provider-key'
WEBHOOK_SECRET = 'held-sign-key'
CONFIG = {
    'model': {'default': 'woow-free', 'provider': 'custom', 'base_url': 'https://proxy.test/v1'},
    'max_tokens': 4096, 'auth_mode': 'basic', 'toolsets': ['web'], 'max_live_sessions': 4,
    'custom_providers': [{'name': 'litellm', 'base_url': 'https://user:held-url-pass@proxy.test/v1', 'api_key': PROVIDER_KEY,
                          'models': ['woow-free']},
                         {'name': 'unset', 'api_key': '', 'token': None}],
    'mcp_servers': {'github': {'url': 'https://mcp.test', 'env': {'GITHUB_TOKEN': 'held-gh-token', 'LOG_LEVEL': 'info'}}},
    'secrets': {'OPENROUTER_API_KEY': 'held-or-key'},
    'webhooks': {'signing': {'secret': WEBHOOK_SECRET, 'enabled': True}},
}
HELD = (PROVIDER_KEY, WEBHOOK_SECRET, 'held-url-pass', 'held-gh-token', 'held-or-key')


def dashboard(writes):
    class Dashboard(Quiet):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Set-Cookie', 'hermes_session_at=session-cookie-0815')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def do_GET(self):
            assert self.path == '/api/config', self.path
            self.reply(CONFIG)

        def do_PUT(self):
            writes.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.reply({'ok': True})
    return Dashboard


def text_of(response):
    body = response.text
    data = next((line[5:].strip() for line in body.splitlines() if line.startswith("data:")), body)
    return json.loads(json.loads(data)['result']['content'][0]['text'])


async def test_config_reads_never_return_backend_held_credentials(tmp_path):
    writes = []
    with serve(dashboard(writes)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_config:set']) as (client, headers, *_):
            async def get(arguments):
                response = await client.post('/mcp', headers=headers, json=call('hermes_config', arguments))
                assert response.status_code == 200, response.text
                assert not any(secret in response.text for secret in HELD), response.text
                return text_of(response)

            everything = await get({'action': 'get'})
            assert everything['custom_providers'][0] == {'name': 'litellm', 'base_url': 'https://user:[REDACTED]@proxy.test/v1',
                                                         'api_key': '[REDACTED]', 'models': ['woow-free']}
            assert everything['custom_providers'][1] == {'name': 'unset', 'api_key': '', 'token': None}  # "not set" stays visible
            assert everything['mcp_servers']['github']['env'] == {'GITHUB_TOKEN': '[REDACTED]', 'LOG_LEVEL': 'info'}
            assert everything['secrets'] == {'OPENROUTER_API_KEY': '[REDACTED]'}
            assert everything['webhooks']['signing'] == {'secret': '[REDACTED]', 'enabled': True}
            assert everything['max_tokens'] == 4096 and everything['auth_mode'] == 'basic'  # not secrets
            assert everything['model'] == CONFIG['model']
            providers = await get({'action': 'get', 'key': 'custom_providers'})
            assert providers['value'][0]['api_key'] == '[REDACTED]' and providers['value'][0]['name'] == 'litellm'
            assert (await get({'action': 'get', 'key': 'secrets.OPENROUTER_API_KEY'}))['value'] == '[REDACTED]'
            assert (await get({'action': 'get', 'key': 'webhooks.signing'}))['value'] == {'secret': '[REDACTED]', 'enabled': True}
            assert (await get({'action': 'get', 'key': 'max_tokens'}))['value'] == 4096
            summary = await client.post('/mcp', headers=headers, json=call('hermes_inspect', {'target': 'config'}))
            assert text_of(summary)['config_summary'] == {'model': CONFIG['model'], 'toolsets': ['web'], 'max_live_sessions': 4}
            # Credential writes use the service settings, matching the PaaS guard; no credential echoes.
            written = await client.post('/mcp', headers=headers, json=call('hermes_config', {
                'action': 'set', 'key': 'model.api_key', 'value': 'new-held-key'}))
            assert written.status_code == 200, written.text
            assert 'cannot be changed through MCP' in written.text
            assert 'new-held-key' not in written.text
            assert writes == []
