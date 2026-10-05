"""Six-product production wiring; in-process ASGI and fake WS, no listeners/children."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import socket
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core import ha_role, products, run_product
import test_ha_role as original_role_tests
from test_ha_role import (
    DUMMY, IDENTITY, result, user,
    test_actual_protocol_and_current_subject,
    test_failclosed_result_schema,
    test_wrong_sequence_and_revoked_machine_capability,
    test_fresh_connection_no_positive_cache_token_reloaded,
    test_identity_ambiguity_never_queries,
    test_denied_fresh_action_no_mutation_or_disclosure,
    test_body_and_validation_precede_fresh_query,
    test_queued_demotion_checks_after_lock,
)
from test_real_products import connection

SIX = ('odoo', 'odoo-manage', 'hermes', 'opendesign', 'emqx', 'litellm')


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('focused HA-role tests forbid network/listener/subprocess I/O')
    for name in ('connect', 'connect_ex', 'bind'):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_shell', forbidden)


class FakeSocket:
    def __init__(self, record):
        self.record = record
        self.transport = self
        self.closed = False
        self.messages = iter([
            record.get('first') or {'type': 'auth_required', 'ha_version': '2026.7.2'},
            record.get('auth') or {'type': 'auth_ok', 'ha_version': '2026.7.2'},
            record['response'],
        ])

    async def recv(self):
        payload = next(self.messages)
        return payload if isinstance(payload, (str, bytes)) else json.dumps(payload)

    async def send(self, message):
        self.record['frames'].append(json.loads(message))

    def abort(self):
        self.closed = True

    async def wait_closed(self):
        assert self.closed
        self.record['closed'] += 1


@pytest.fixture(autouse=True)
def reuse_existing_role_tests_without_sockets(monkeypatch):
    @asynccontextmanager
    async def fake_provider(monkeypatch, *, response=None, first=None, auth=None):
        monkeypatch.setenv('SUPERVISOR_TOKEN', DUMMY)
        record = {'response': result() if response is None else response,
                  'first': first, 'auth': auth, 'frames': [], 'connections': 0, 'closed': 0}
        async def connect(uri, **options):
            assert uri == 'ws://supervisor/core/websocket'
            assert options['proxy'] is None and options['logger'].disabled
            record['connections'] += 1
            return FakeSocket(record)
        verify = ha_role._Verifier(connect)
        yield verify, record, asyncio.Event()
        assert verify._active == 0
        assert record['closed'] == record['connections']
    # Reuse original assertions and parametrization; replace only the WS boundary.
    monkeypatch.setattr(original_role_tests, 'owned_provider', fake_provider)


@pytest.fixture
def fake_ws(monkeypatch):
    monkeypatch.setenv('SUPERVISOR_TOKEN', DUMMY)
    record = {'response': result(), 'frames': [], 'connections': 0, 'closed': 0,
              'unavailable': False}

    async def connect(uri, **options):
        assert uri == 'ws://supervisor/core/websocket'
        assert options['proxy'] is None and options['compression'] is None
        assert options['logger'].disabled
        assert options['max_size'] == 1024 * 1024 and options['max_queue'] == 1
        record['connections'] += 1
        if record['unavailable']:
            raise OSError(DUMMY + '-private-directory')
        return FakeSocket(record)

    # Keep the real factory, verifier, protocol, gateway and runtime run() path.
    monkeypatch.setattr(ha_role, '_NoRedirectConnect', connect)
    return record


@asynccontextmanager
async def runtime_apps(tmp_path, monkeypatch, product):
    captured = {}
    ready, finish = asyncio.Event(), asyncio.Event()
    real_apps = run_product.make_apps

    def apps(store, tools, child, **kwargs):
        captured.update(store=store, verifier=kwargs.get('verify_admin'))
        return real_apps(store, tools, child, **kwargs)

    class Manager:
        def __init__(self, spec):
            assert spec is None  # Real unconfigured child_spec; no child install.
        async def start(self): pass
        async def stop(self): pass

    class Monitor:
        def __init__(self, *args): pass
        def snapshot(self): return {}
        async def run(self): await asyncio.Event().wait()

    class Listener:
        def __init__(self, config):
            captured[config.port] = config.app
            self.should_exit = False
        async def serve(self):
            ready.set()
            await finish.wait()

    requests = []
    def dispatch(request):
        requests.append(request)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {}})

    real_client = httpx.AsyncClient
    def client(**kwargs):
        kwargs.setdefault('transport', httpx.MockTransport(dispatch))
        return real_client(**kwargs)

    monkeypatch.setattr(run_product.httpx, 'AsyncClient', client)
    monkeypatch.setattr(run_product, 'make_apps', apps)
    monkeypatch.setattr(run_product, 'Supervisor', Manager)
    monkeypatch.setattr(run_product, 'HealthMonitor', Monitor)
    monkeypatch.setattr(run_product, 'Listener', Listener)
    args = SimpleNamespace(data=tmp_path / product, product=product, host='127.0.0.1',
                           admin_port=8099, mcp_port=8081)
    task = asyncio.create_task(run_product.run(args))
    try:
        await asyncio.wait_for(ready.wait(), 2)
        async with real_client(transport=httpx.ASGITransport(app=captured[8099],
                client=('172.30.32.2', 1)), base_url='http://admin') as admin:
            async with real_client(transport=httpx.ASGITransport(app=captured[8081]),
                    base_url='http://mcp') as mcp:
                yield admin, mcp, captured, requests
    finally:
        finish.set()
        with pytest.raises(RuntimeError, match='runtime component stopped'):
            await asyncio.wait_for(task, 2)


@pytest.mark.parametrize('product', SIX)
async def test_runtime_uses_shared_admin_verifier(tmp_path, monkeypatch, fake_ws, product, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        async with runtime_apps(tmp_path, monkeypatch, product) as (admin, _, captured, __):
            response = await admin.get('/api/bootstrap', headers=IDENTITY)
            assert response.status_code == 200
            assert isinstance(captured['verifier'], ha_role._Verifier)
            assert run_product.make_ha_admin_verifier is ha_role.make_ha_admin_verifier
            assert fake_ws['frames'] == [
                {'type': 'auth', 'access_token': DUMMY},
                {'id': 1, 'type': 'config/auth/list'},
            ]
            assert fake_ws['closed'] == fake_ws['connections'] == 1
            assert DUMMY not in response.text
            assert DUMMY not in captured['store'].path.read_text()
    output = capsys.readouterr()
    assert DUMMY not in caplog.text + output.out + output.err


@pytest.mark.parametrize('product', SIX)
@pytest.mark.parametrize('denial', ['non-admin', 'unknown', 'inactive', 'missing-token', 'ws-unavailable'])
async def test_runtime_denies_fresh_actions(tmp_path, monkeypatch, fake_ws, product, denial, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        async with runtime_apps(tmp_path, monkeypatch, product) as (admin, _, captured, __):
            bootstrap = await admin.get('/api/bootstrap', headers=IDENTITY)
            assert bootstrap.status_code == 200
            headers = {**IDENTITY, 'X-CSRF-Token': bootstrap.json()['csrf']}
            before = captured['store'].path.read_bytes()
            if denial == 'missing-token':
                monkeypatch.delenv('SUPERVISOR_TOKEN')
            elif denial == 'ws-unavailable':
                fake_ws['unavailable'] = True
            else:
                denied_user = {'non-admin': user(group_ids=[]), 'unknown': user(id='other'),
                               'inactive': user(is_active=False)}[denial]
                fake_ws['response'] = result([denied_user])
            for method, path, payload in [
                ('GET', 'bootstrap', None), ('POST', 'token/reveal', None),
                ('POST', 'token/rotate', None), ('POST', 'token/revoke', None),
                ('PUT', 'backend', {'connection': None}),
                ('PUT', 'policy', {'writes_enabled': True, 'disabled': []}),
                ('PUT', 'endpoint', {'endpoint': 'http://example.test/mcp'}),
            ]:
                response = await admin.request(method, '/api/' + path, headers=headers, json=payload)
                assert response.status_code == 403
                assert response.json() == {'error': 'request denied'}
                assert DUMMY not in response.text
                assert captured['store'].load().token not in response.text
                assert captured['store'].path.read_bytes() == before
            assert fake_ws['connections'] == (1 if denial == 'missing-token' else 8)
    output = capsys.readouterr()
    assert DUMMY not in caplog.text + output.out + output.err


@pytest.mark.parametrize('product', SIX)
async def test_runtime_mcp_bearer_and_ingress_separation(tmp_path, monkeypatch, fake_ws, product):
    async with runtime_apps(tmp_path, monkeypatch, product) as (admin, mcp, captured, requests):
        state = captured['store'].load()
        spoof = {**IDENTITY, 'X-Forwarded-For': '172.30.32.2',
                 'X-Remote-User-Is-Admin': 'true', 'X-Ingress-Path': '/fake'}
        for extra in ({}, {'Authorization': 'Bearer wrong'}, {'Authorization': 'Bearer ' + DUMMY}):
            denied = await mcp.get('/mcp', headers={**spoof, **extra})
            assert denied.status_code == 401
            assert denied.headers['www-authenticate'] == 'Bearer'
        assert (await mcp.get('/api/bootstrap', headers=spoof)).status_code == 404
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=captured[8099],
                client=('127.0.0.1', 1)), base_url='http://direct') as direct:
            assert (await direct.get('/api/bootstrap', headers=spoof)).status_code == 403
        assert (await admin.get('/api/bootstrap', headers={
            'Authorization': 'Bearer ' + state.token})).status_code == 403
        assert fake_ws['connections'] == 0 and requests == []
        accepted = await mcp.post('/mcp', headers={**spoof, 'Authorization': 'Bearer ' + state.token},
                                  json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        assert accepted.status_code == 200
        assert len(requests) == 1
        assert requests[0].headers['authorization'] == 'Bearer ' + state.child_token
        assert 'x-remote-user-id' not in requests[0].headers
        assert DUMMY not in str(requests[0].headers) + accepted.text
        assert fake_ws['connections'] == 0


@pytest.mark.parametrize('product', SIX)
def test_real_child_spec_env_excludes_supervisor_token(tmp_path, monkeypatch, product):
    monkeypatch.setenv('SUPERVISOR_TOKEN', DUMMY)
    # A file-presence fixture only: no child dependency install or executable launch.
    root = tmp_path / 'source'
    python = root / 'apps' / product / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(products, 'ROOT', root)
    store = products.ProductStore(tmp_path / 'state', product)
    try:
        store.update(connection=connection(product, 'http://example.test'))
        spec = products.child_spec(store.load(), store.directory)
        assert spec is not None
        assert 'SUPERVISOR_TOKEN' not in spec.env
        assert DUMMY not in repr(spec.env) + repr(spec.argv)
        assert spec.env['HOME'] == str(spec.cwd)
        assert spec.argv[0] == str(python)
    finally:
        store.close()
