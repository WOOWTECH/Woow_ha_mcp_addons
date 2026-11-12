"""LOCAL/MOCK: an Odoo tool call waits up to 30 s for Odoo, as the PaaS server does (unreleased, 0.4.12 line).

Up to 0.4.11 every XML-RPC exchange with Odoo was cut at 5 s (ODOO_TIMEOUT=5 in the child's environment and a 5 s clamp in
apps/odoo/launch.py), so a read Odoo finishes in 6-30 s (a report, a search_read on a big table) came back BACKEND_TIMEOUT
here and succeeded on the PaaS server, which keeps odoo-mcp's own 30 s. The tools now get 30 s. The add-on has ONE Odoo tool
worker (BoundedTools, capacity 1; a second call gets BACKEND_BUSY at once), so the longer wait is only acceptable if it is
bounded: a call that Odoo never answers must end with BACKEND_TIMEOUT after the limit (times the odoo-mcp retries of a
read) and give the worker back. The private readiness probe keeps its 5 s: HealthMonitor waits 5 s for it and probes every
15 s, and the probe's own thread is free again only when its call returns.

Genuine pinned Odoo child (the real odoo-mcp 1.3.0 OdooClient and the add-on's XML-RPC transport) and the real gateway,
against an owned stdlib XML-RPC peer that holds its answers for as long as a test says.
"""
import asyncio
import json
import subprocess
import threading
import time
import xmlrpc.client
from pathlib import Path

import pytest

import test_six_hardening as hardening
from mcp_admin_core.products import PROBES, ProductStore, child_spec
from test_odoo_probe_auth_rejected import UNAVAILABLE, failed, probe, running_child
from test_real_products import connection, rpc
from test_six_hardening import Quiet, call, runtime, serve

ROOT = Path(__file__).resolve().parents[1]


def slow_odoo(state):
    """Answers authenticate and execute_kw as Odoo does, after holding each call for as long as `state` says: the next
    value of state['hold'][kind] (kind: 'authenticate' or 'rpc'), or state['hang'] (rpc only) until the test is over."""
    class Handler(Quiet):
        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            kind = 'authenticate' if method == 'authenticate' else 'rpc'
            with state['lock']:
                state['seen'].append(kind)
                queue = state['hold'][kind]
                seconds = 30 if kind == 'rpc' and state['hang'] else queue.pop(0) if queue else 0
            state['release'].wait(seconds)  # a held call ends early when the test is over
            if method == 'authenticate':
                value = 7
            else:
                value = [1] if params[4] == 'search' else [{'model': 'res.partner', 'name': 'Contact'}]
            self.reply(xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode())
    return Handler


def new_state():
    return {'lock': threading.Lock(), 'seen': [], 'release': threading.Event(), 'hang': False,
            'hold': {'authenticate': [], 'rpc': []}}


def text_of(reply):
    return reply['content'][0]['text']


def test_the_transport_waits_up_to_the_tool_limit_and_no_longer():
    """The cap, in the Odoo child's own interpreter: what odoo-mcp asks for is honoured up to 30 s and cut there."""
    script = r'''
import json, os
os.environ['ODOO_URL'] = 'http://127.0.0.1:1'
import launch

def waits(*args, **kwargs):
    return launch.BackendTransport(*args, **kwargs).timeout

print(json.dumps({'tool': launch.TOOL_TIMEOUT, 'probe': launch.PROBE_TIMEOUT, 'default': waits(),
                  'asked': {str(n): waits(timeout=n) for n in (2, 5, 10, 30, 31, 300)}}))
'''
    finished = subprocess.run(
        [str(ROOT / 'apps/odoo/.venv/bin/python'), '-B', '-c', script], cwd=ROOT / 'apps/odoo', capture_output=True, text=True,
        env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': f'{ROOT / "apps/runtime"}:{ROOT / "apps/odoo"}', 'PYTHONDONTWRITEBYTECODE': '1'},
        timeout=30, check=False)
    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == {
        'tool': 30, 'probe': 5, 'default': 30, 'asked': {'2': 2, '5': 5, '10': 10, '30': 30, '31': 30, '300': 30}}


def test_the_child_asks_odoo_mcp_for_the_tool_limit(tmp_path):
    store = ProductStore(tmp_path / 'state', 'odoo')
    store.update(connection=connection('odoo', 'http://127.0.0.1:9'))
    try:
        assert child_spec(store.load(), store.directory).env['ODOO_TIMEOUT'] == '30'
    finally:
        store.close()


async def test_a_read_odoo_answers_after_the_old_5_second_limit_succeeds(tmp_path):
    state = new_state()
    state['hold']['rpc'] = [6.5]  # the first exchange of the read: longer than 5 s, far inside 30 s
    with serve(slow_odoo(state)) as url:
        try:
            async with runtime(tmp_path, 'odoo', url) as (client, headers, *_):
                started = time.monotonic()
                reply = await rpc(client, '/mcp', headers, call(*PROBES['odoo']))
                elapsed = time.monotonic() - started
        finally:
            state['release'].set()
    assert not reply.get('isError'), reply
    assert json.loads(text_of(reply))['success'] is True
    assert 6 < elapsed < 20, elapsed  # it waited for Odoo; it was not cut at 5 s and retried
    assert state['seen'].count('rpc') == 2  # ir.model search + read: one attempt each, no retry


async def test_a_hung_odoo_ends_with_backend_timeout_and_frees_the_single_worker(tmp_path, monkeypatch):
    """The wait is bounded: the same child with ODOO_TIMEOUT=2 (one retry of a read, no back-off) stands in for 30 s. A
    call Odoo never answers holds the one worker for the limit times its attempts, a second call is refused at once, and
    when the limit has passed the worker takes the next call."""
    def short(state, directory):
        spec = child_spec(state, directory)
        spec.env.update(ODOO_TIMEOUT='2', ODOO_MCP_RETRY_ATTEMPTS='1', ODOO_MCP_RETRY_BACKOFF='0')
        return spec

    monkeypatch.setattr(hardening, 'child_spec', short)
    state = new_state()
    state['hang'] = True
    with serve(slow_odoo(state)) as url:
        try:
            async with runtime(tmp_path, 'odoo', url) as (client, headers, *_):
                started = time.monotonic()
                held = asyncio.create_task(rpc(client, '/mcp', headers, call(*PROBES['odoo'], id=10)))
                await asyncio.sleep(.7)  # the first call is inside its first, hung exchange
                refused = await rpc(client, '/mcp', headers, call(*PROBES['odoo'], id=11))
                assert 'BACKEND_BUSY' in json.dumps(refused) and time.monotonic() - started < 1.5, refused
                timed_out = await held
                elapsed = time.monotonic() - started
                assert timed_out.get('isError') and 'BACKEND_TIMEOUT' in text_of(timed_out), timed_out
                assert 3.5 < elapsed < 9, elapsed  # 2 s limit x (1 attempt + 1 retry): bounded, not forever
                assert state['seen'].count('rpc') == 2
                state['hang'] = False  # Odoo is back
                recovered = await rpc(client, '/mcp', headers, call(*PROBES['odoo'], id=12))
                assert not recovered.get('isError') and json.loads(text_of(recovered))['success'] is True, recovered
        finally:
            state['release'].set()


async def test_the_readiness_probe_keeps_its_5_second_limit_while_tools_wait_longer(tmp_path):
    """Odoo answers authenticate after 8 s: the tool path (30 s) would wait for it, the probe gives up at 5 s and reads
    BACKEND_UNAVAILABLE, so the health check is not held up by an Odoo that answers late (or never)."""
    state = new_state()
    state['hold']['authenticate'] = [8]
    with serve(slow_odoo(state)) as url:
        try:
            async with running_child(tmp_path, url) as (store, endpoint, _):
                started = time.monotonic()
                assert await probe(store, endpoint) == failed(UNAVAILABLE)
                elapsed = time.monotonic() - started
        finally:
            state['release'].set()
    assert 4.5 < elapsed < 7.5, elapsed
    assert state['seen'] == ['authenticate']
