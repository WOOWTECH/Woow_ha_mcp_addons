"""Commercial acceptance AI-HER-PERF-1 (PaaS Hermes MCP 249 -> Hermes 247, Hermes 0.21.6): the Hermes dashboard allows 10
POST /auth/password-login per client IP per 60 s (successful logins count too) and its 429 carries no Retry-After. The
child's cookie cache is shared by every MCP session, but when 10+ concurrent calls start cold they all see an empty cache
and each logs in, so the 11th gets 429, which the vendored server raised as is. Now concurrent logins for one
dashboard_url are coalesced into one (single-flight) and a 429 login is retried up to twice after Retry-After (capped at
10 s) or 1 s / 2 s. The real Hermes child against a LOCAL fake dashboard that throttles like Hermes 0.21.6.
"""
import asyncio
import json
import threading
import time

from test_six_hardening import Quiet, call, runtime, serve

STATUS = {'version': '0.21.6', 'gateway_running': True, 'gateway_state': 'running', 'active_sessions': 1}


def dashboard(state, *, limit=10, delay=.3, script=()):
    """A Hermes 0.21.6-like dashboard: at most `limit` logins (successful ones count), then 429 without Retry-After.
    `script` lists (status, headers) replies for the first logins."""
    lock = threading.Lock()
    script = list(script)
    state.update(logins=0, accepted=0, at=[])

    class Dashboard(Quiet):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            assert self.path == '/auth/password-login', self.path
            with lock:
                state['logins'] += 1
                state['at'].append(time.monotonic())
                scripted = script.pop(0) if script else None
            time.sleep(delay)  # concurrent logins overlap
            if scripted is None:
                with lock:
                    allowed = state['accepted'] < limit
                    state['accepted'] += allowed
                scripted = (200, {}) if allowed else (429, {})
            status, headers = scripted
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            if status == 200:
                self.send_header('Set-Cookie', 'hermes_session_at=session-cookie-0815')
            body = json.dumps({'ok': True} if status == 200 else {'detail': 'Too many login attempts. Try again shortly.'})
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            assert self.path == '/api/status', self.path
            assert 'session-cookie-0815' in self.headers.get('Cookie', ''), 'tool request without the login cookie'
            self.reply(STATUS)
    return Dashboard


def text_of(response):
    body = response.text
    data = next((line[5:].strip() for line in body.splitlines() if line.startswith('data:')), body)
    return json.loads(data)['result']


async def gateway_status(client, headers, id=2):
    response = await client.post('/mcp', headers=headers, json=call('hermes_gateway', {'action': 'status'}, id=id))
    assert response.status_code == 200, response.text
    return text_of(response)


async def test_concurrent_cold_calls_share_one_login(tmp_path):
    state = {}
    with serve(dashboard(state)) as url:
        async with runtime(tmp_path, 'hermes', url) as (client, headers, *_):
            results = await asyncio.gather(*(gateway_status(client, headers, id=10 + i) for i in range(12)))
            failed = [r for r in results if r.get('isError')]
            assert not failed, f'{len(failed)} of 12 calls failed: {failed[0]}'
            for result in results:
                assert json.loads(result['content'][0]['text'])['running'] is True
            assert state['logins'] == 1, f"12 concurrent cold calls logged in {state['logins']} times"
            await gateway_status(client, headers, id=99)  # cached cookie: no new login
            assert state['logins'] == 1


async def test_429_login_is_retried_after_retry_after(tmp_path):
    state = {}
    with serve(dashboard(state, delay=0, script=[(429, {'Retry-After': '1'})])) as url:
        async with runtime(tmp_path, 'hermes', url) as (client, headers, *_):
            result = await gateway_status(client, headers)
            assert not result.get('isError'), result
            assert state['logins'] == 2
            assert state['at'][1] - state['at'][0] >= .9


async def test_persistent_429_gives_up_after_two_backoff_retries(tmp_path):
    state = {}
    with serve(dashboard(state, limit=0, delay=0)) as url:
        async with runtime(tmp_path, 'hermes', url) as (client, headers, *_):
            result = await gateway_status(client, headers)
            assert result.get('isError') is True, result
            assert '429' in result['content'][0]['text']
            assert state['logins'] == 3  # one attempt + two retries
            gaps = [b - a for a, b in zip(state['at'], state['at'][1:])]
            assert gaps[0] >= .9 and gaps[1] >= 1.9, gaps  # exponential backoff 1 s, 2 s
