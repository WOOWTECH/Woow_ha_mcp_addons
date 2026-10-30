"""Write CAS, durable receipts and crash uncertainty at the real admin boundary."""
import asyncio
from contextlib import asynccontextmanager, closing
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

import httpx
import pytest

from mcp_admin_core.admin_auth import BadRequest
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.operations import OperationJournal, TTL_MS, MAX_RECEIPTS
from mcp_admin_core.products import ProductStore
from n8n_adapter import TOOLS

IDENTITY = {'x-remote-user-id': 'admin-contract-review'}


def operation_id():
    return f'{int(time.time() * 1000)}.{secrets.token_urlsafe(16)}'


@asynccontextmanager
async def client_for(store, *, restart=None, role=None):
    async def allowed(_): return True
    async with httpx.AsyncClient(trust_env=False) as child:
        admin, _ = make_apps(store, TOOLS, child, verify_admin=role or allowed, restart_child=restart)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                     base_url='http://local', headers=IDENTITY) as client:
            yield client


async def write_headers(client, *, key=None):
    boot = await client.get('/api/bootstrap')
    return {'x-csrf-token': boot.json()['csrf'], 'If-Match': boot.headers['etag'],
            'Idempotency-Key': key or operation_id()}


def code(response, status, value):
    assert response.status_code == status, response.text
    assert response.json()['detail']['code'] == value


@pytest.mark.parametrize('route,payload', [
    ('backend', {'url': None, 'key': None}), ('endpoint', {'endpoint': None}),
    ('policy', {'writes_enabled': False, 'disabled': []}),
    ('backend/patch', {'values': {}, 'clear_secrets': []}),
    ('n8n/session', {'n8n_session': {'timeout_seconds': 600, 'max_sessions': 20}}),
])
async def test_every_valid_persisted_put_requires_reviewed_revision(tmp_path, route, payload):
    # Use canonical patch shape for this product from its published contract.
    if route == 'backend/patch': payload = {'changes': {'mcp_access_token': None}}
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        if route == 'backend/patch': store.update(backend_url='https://backend.invalid', backend_key='SYNTHETIC')
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            headers.pop('If-Match')
            response = await client.put('/api/' + route, json=payload, headers=headers)
            code(response, 428, 'config_revision_required')
            assert store.path.read_bytes() == before


@pytest.mark.parametrize('route', ['token/rotate', 'token/revoke', 'child/restart', 'owner-defaults/restore', 'owner-defaults/dismiss'])
async def test_persisted_posts_require_revision_before_effect(tmp_path, route):
    effects = []
    async def restart(_): effects.append('restart')
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, restart=restart) as client:
            headers = await write_headers(client)
            headers.pop('If-Match')
            before = store.path.read_bytes()
            code(await client.post('/api/' + route, headers=headers), 428, 'config_revision_required')
            assert store.path.read_bytes() == before and not effects
            assert not OperationJournal(store.path).path.exists()


async def test_exact_single_etag_and_concurrent_writers(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            for invalid in ['*', 'W/' + headers['If-Match'], headers['If-Match'] + ', ' + headers['If-Match']]:
                code(await client.put('/api/endpoint', json={'endpoint': None}, headers={**headers, 'If-Match': invalid}), 409, 'config_conflict')
            duplicated = list(headers.items()) + [('If-Match', headers['If-Match'])]
            code(await client.put('/api/endpoint', json={'endpoint': None}, headers=duplicated), 409, 'config_conflict')
            results = await asyncio.gather(*[
                client.put('/api/endpoint', json={'endpoint': f'https://site{n}.invalid/mcp'}, headers=headers)
                for n in (1, 2)])
            assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.parametrize('route', ['token/rotate', 'token/revoke', 'child/restart'])
async def test_id_required_and_malformed_refused_without_effect(tmp_path, route):
    effects = []
    async def restart(_): effects.append(1)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, restart=restart) as client:
            headers = await write_headers(client)
            headers.pop('Idempotency-Key')
            before = store.path.read_bytes()
            code(await client.post('/api/' + route, headers=headers), 428, 'operation_id_required')
            code(await client.post('/api/' + route, headers={**headers, 'Idempotency-Key': 'bad'}), 400, 'operation_id_invalid')
            duplicates = list(headers.items()) + [('Idempotency-Key', operation_id()), ('Idempotency-Key', operation_id())]
            code(await client.post('/api/' + route, headers=duplicates), 400, 'operation_id_invalid')
            assert not effects and store.path.read_bytes() == before


@pytest.mark.parametrize('route', ['token/rotate', 'token/revoke', 'child/restart'])
async def test_concurrent_replay_survives_new_app_without_old_secret(tmp_path, route):
    effects = []
    async def restart(_): effects.append(1)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        original = store.load().token
        async with client_for(store, restart=restart) as client:
            headers = await write_headers(client)
            results = await asyncio.gather(*[client.post('/api/' + route, headers=headers) for _ in range(2)])
            assert all(r.status_code in (200, 202) for r in results), [r.text for r in results]
            bodies = [r.json() for r in results]
            assert sorted(b['operation']['replayed'] for b in bodies) == [False, True]
            before = store.path.read_bytes()
        # New authority CSRF/revision, same private on-disk receipt.
        async with client_for(store, restart=restart) as client:
            fresh = await write_headers(client)
            headers['x-csrf-token'] = fresh['x-csrf-token']
            result = await client.post('/api/' + route, headers=headers)
            assert result.status_code == 200 and result.json()['operation']['replayed']
            assert 'token' not in result.json()
            assert store.path.read_bytes() == before
            queried = await client.get('/api/operations/' + headers['Idempotency-Key'])
            assert queried.status_code == 200 and queried.json()['operation']['state'] == 'completed'
            assert original not in queried.text and original not in OperationJournal(store.path).path.read_text()
            if store.load().token:
                assert store.load().token not in queried.text
            assert len(effects) == (1 if route == 'child/restart' else 0)
            if route != 'child/restart': assert len(store.load().token_history) == 1
            other = 'token/revoke' if route == 'token/rotate' else 'token/rotate'
            code(await client.post('/api/' + other, headers=headers), 409, 'operation_id_conflict')


async def test_replay_and_query_reauthorize_and_bind_actor(tmp_path):
    authorized = True
    async def role(_): return authorized
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, role=role) as client:
            headers = await write_headers(client)
            assert (await client.post('/api/token/rotate', headers=headers)).status_code == 200
            before = store.path.read_bytes()
            query = '/api/operations/' + headers['Idempotency-Key']
            code(await client.get(query, headers={'x-remote-user-id': 'another-admin'}), 404, 'operation_not_found')
            boot = (await client.get('/api/bootstrap', headers={'x-remote-user-id': 'another-admin'})).json()
            code(await client.post('/api/token/rotate', headers={**headers, 'x-remote-user-id': 'another-admin', 'x-csrf-token': boot['csrf']}), 404, 'operation_not_found')
            authorized = False
            assert (await client.get(query)).status_code == 403
            assert (await client.post('/api/token/rotate', headers=headers)).status_code == 403
            assert store.path.read_bytes() == before


async def test_callback_failure_is_unknown_and_never_retried(tmp_path):
    effects = []
    async def restart(_):
        effects.append(1)
        raise RuntimeError('PRIVATE_INTERNAL_FAILURE')
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, restart=restart) as client:
            headers = await write_headers(client)
            for _ in range(2):
                response = await client.post('/api/child/restart', headers=headers)
                code(response, 409, 'operation_outcome_unknown')
                assert 'PRIVATE_INTERNAL_FAILURE' not in response.text
            assert effects == [1]
            result = (await client.get('/api/operations/' + headers['Idempotency-Key'])).json()
            assert result['operation']['state'] == 'unknown' and result['result'] == {}


async def test_journal_write_failure_prevents_effect(tmp_path, monkeypatch):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            def fail(*_): raise OSError('PRIVATE_DISK_ERROR')
            monkeypatch.setattr(OperationJournal, '_write', fail)
            response = await client.post('/api/token/rotate', headers=headers)
            code(response, 503, 'operation_journal_unavailable')
            assert 'PRIVATE_DISK_ERROR' not in response.text and store.path.read_bytes() == before


async def test_complete_failure_keeps_effect_but_unknown_receipt(tmp_path, monkeypatch):
    original = OperationJournal._write
    calls = 0
    def fail_second(self, data):
        nonlocal calls
        calls += 1
        if calls == 2: raise OSError('completion interrupted')
        original(self, data)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            monkeypatch.setattr(OperationJournal, '_write', fail_second)
            code(await client.post('/api/token/rotate', headers=headers), 409, 'operation_outcome_unknown')
            before = store.path.read_bytes()
            code(await client.post('/api/token/rotate', headers=headers), 409, 'operation_outcome_unknown')
            assert before == store.path.read_bytes() and len(store.load().token_history) == 1


@pytest.mark.parametrize('finish', [False, True])
async def test_actual_process_exit_after_token_effect(tmp_path, finish):
    key = operation_id()
    script = '''
import os,sys
from pathlib import Path
from mcp_admin_core.products import ProductStore
from mcp_admin_core.operations import OperationJournal
store=ProductStore(Path(sys.argv[1]),'n8n')
j=OperationJournal(store.path)
data,prior,fp=j.inspect(sys.argv[2],'token.rotate','admin-contract-review')
j.begin(sys.argv[2],data,'token.rotate','admin-contract-review',fp)
store.change_token('X'*43,action='rotate')
if sys.argv[3]=='True': j.complete(sys.argv[2],data)
os._exit(23)
'''
    completed = subprocess.run([sys.executable, '-c', script, str(tmp_path), key, str(finish)], capture_output=True, text=True,
                               env={**os.environ, 'PYTHONPATH': os.pathsep.join(sys.path)})
    assert completed.returncode == 23, completed.stderr
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        before = store.path.read_bytes()
        async with client_for(store) as client:
            headers = await write_headers(client, key=key)
            result = await client.post('/api/token/rotate', headers=headers)
            if finish:
                assert result.status_code == 200 and result.json()['operation']['replayed']
                assert 'token' not in result.json()
            else: code(result, 409, 'operation_outcome_unknown')
            assert store.path.read_bytes() == before and store.load().token == 'X' * 43


def test_expiry_capacity_private_bytes_and_corrupt_fail_closed(tmp_path, monkeypatch):
    journal = OperationJournal(tmp_path / 'state.json')
    now = int(time.time() * 1000)
    monkeypatch.setattr('mcp_admin_core.operations.time.time', lambda: now / 1000)
    for n in range(MAX_RECEIPTS):
        key = f'{now}.{n:016d}'
        data, _, fp = journal.inspect(key, 'token.rotate', 'private-admin')
        journal.begin(key, data, 'token.rotate', 'private-admin', fp)
    assert journal.path.stat().st_mode & 0o777 == 0o600
    assert 'private-admin' not in journal.path.read_text()
    key = f'{now}.extra_receipt_000'
    data, _, fp = journal.inspect(key, 'token.rotate', 'private-admin')
    with pytest.raises(BadRequest) as error: journal.begin(key, data, 'token.rotate', 'private-admin', fp)
    assert error.value.detail['code'] == 'operation_journal_full'
    monkeypatch.setattr('mcp_admin_core.operations.time.time', lambda: (now + TTL_MS + 1) / 1000)
    with pytest.raises(BadRequest) as error: journal.query(f'{now}.{0:016d}', 'private-admin')
    assert error.value.status == 410
    new = f'{now + TTL_MS + 1}.new_receipt_0000'
    data, _, fp = journal.inspect(new, 'token.rotate', 'private-admin')
    journal.begin(new, data, 'token.rotate', 'private-admin', fp)
    assert len(data['receipts']) == 1
    journal.path.write_text('{"version":1,"version":1}')
    with pytest.raises(BadRequest) as error: journal.query(new, 'private-admin')
    assert error.value.status == 503
    assert journal.path.read_text() == '{"version":1,"version":1}'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo'])
def test_unsafe_receipt_file_refused(tmp_path, kind):
    journal = OperationJournal(tmp_path / 'state.json')
    target = tmp_path / 'target'
    target.write_text('unchanged')
    if kind == 'symlink': journal.path.symlink_to(target)
    elif kind == 'hardlink': os.link(target, journal.path)
    else: os.mkfifo(journal.path)
    with pytest.raises(BadRequest) as error: journal.query(operation_id(), 'admin')
    assert error.value.status == 503 and target.read_text() == 'unchanged'
