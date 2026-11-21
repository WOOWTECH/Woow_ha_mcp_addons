"""DNS admission at the real admin boundary must preserve role and CAS checks."""
import asyncio
from contextlib import closing

import pytest
from mcp_admin_core import n8n_ssrf
from mcp_admin_core.products import ProductStore
from test_admin_operations import client_for, write_headers

BODY = {'url': 'https://new.example.invalid', 'key': 'SYNTHETIC'}


async def test_stale_etag_does_not_resolve_dns(tmp_path, monkeypatch):
    calls = []
    async def resolve(*args):
        calls.append(args)
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            store.update(endpoint='https://changed.example.invalid/mcp')
            response = await client.put('/api/backend', json=BODY, headers=headers)
            assert response.status_code == 409
            assert not calls


@pytest.mark.parametrize('revision,expected', [(None, 428), ('*', 409)])
async def test_missing_or_malformed_etag_does_not_resolve_dns(tmp_path, monkeypatch, revision, expected):
    calls = []
    async def resolve(*args):
        calls.append(args)
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            if revision is None:
                headers.pop('If-Match')
            else:
                headers['If-Match'] = revision
            before = store.path.read_bytes()
            response = await client.put('/api/backend', json=BODY, headers=headers)
            assert response.status_code == expected and not calls
            assert store.path.read_bytes() == before


async def test_demotion_during_dns_refuses_save(tmp_path, monkeypatch):
    entered, proceed = asyncio.Event(), asyncio.Event()
    allowed = True
    async def role(_): return allowed
    async def resolve(*args):
        entered.set()
        await proceed.wait()
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, role=role) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            task = asyncio.create_task(client.put('/api/backend', json=BODY, headers=headers))
            await asyncio.wait_for(entered.wait(), 2)
            allowed = False
            proceed.set()
            response = await task
            assert response.status_code == 403
            assert store.path.read_bytes() == before


async def test_state_changed_during_dns_refuses_save(tmp_path, monkeypatch):
    entered, proceed = asyncio.Event(), asyncio.Event()
    async def resolve(*args):
        entered.set()
        await proceed.wait()
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            task = asyncio.create_task(client.put('/api/backend', json=BODY, headers=headers))
            await asyncio.wait_for(entered.wait(), 2)
            store.update(endpoint='https://changed.example.invalid/mcp')
            proceed.set()
            response = await task
            assert response.status_code == 409
            assert store.load().backend_url is None


async def test_dns_timeout_refuses_without_writing(tmp_path, monkeypatch):
    async def resolve(*args): raise TimeoutError()
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            response = await client.put('/api/backend', json=BODY, headers=headers)
            assert response.status_code == 400
            assert store.path.read_bytes() == before


async def test_two_concurrent_dns_writers_resolve_only_the_winner(tmp_path, monkeypatch):
    entered, proceed = asyncio.Event(), asyncio.Event()
    calls = []
    async def resolve(url, mode):
        calls.append((url, mode))
        entered.set()
        await proceed.wait()
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            first = asyncio.create_task(client.put('/api/backend', json=BODY, headers=headers))
            await asyncio.wait_for(entered.wait(), 2)
            second = asyncio.create_task(client.put('/api/backend', json={**BODY, 'url': 'https://other.example.invalid'}, headers=headers))
            await asyncio.sleep(0)
            proceed.set()
            responses = await asyncio.gather(first, second)
            assert [r.status_code for r in responses] == [200, 409]
            assert calls == [(BODY['url'], 'strict')]


async def test_demotion_before_dns_does_not_resolve(tmp_path, monkeypatch):
    calls = []
    role_calls = 0
    demote = False
    async def role(_):
        nonlocal role_calls
        if not demote:
            return True
        role_calls += 1
        return False  # demoted before the locked role check
    async def resolve(*args):
        calls.append(args)
        return n8n_ssrf.SsrfCheck(True)
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store, role=role) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            demote = True
            response = await client.put('/api/backend', json=BODY, headers=headers)
            assert response.status_code == 403
            assert role_calls >= 1 and not calls
            assert store.path.read_bytes() == before


async def test_blocked_dns_does_not_save(tmp_path, monkeypatch):
    async def resolve(url, mode):
        assert mode == 'strict'
        return n8n_ssrf.SsrfCheck(False, addresses=['10.0.0.1'])
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            response = await client.put('/api/backend', json=BODY, headers=headers)
            assert response.status_code == 400
            assert store.path.read_bytes() == before


async def test_dns_deadline_cancels_slow_resolution(tmp_path, monkeypatch):
    cancelled = asyncio.Event()
    async def resolve(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            response = await asyncio.wait_for(client.put('/api/backend', json=BODY, headers=headers), 5)
            assert response.status_code == 400 and cancelled.is_set()
            assert store.path.read_bytes() == before


async def test_patch_checks_strict_dns_after_revision(tmp_path, monkeypatch):
    calls = []
    async def resolve(url, mode):
        calls.append((url, mode))
        return n8n_ssrf.SsrfCheck(False, addresses=['127.0.0.1'])
    monkeypatch.setattr(n8n_ssrf, 'check_url', resolve)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(backend_url='https://old.example.invalid', backend_key='SYNTHETIC')
        async with client_for(store) as client:
            headers = await write_headers(client)
            before = store.path.read_bytes()
            response = await client.put('/api/backend/patch',
                                        json={'changes': {'url': BODY['url'], 'key': BODY['key']}},
                                        headers=headers)
            assert response.status_code == 400
            assert calls == [(BODY['url'], 'strict')]
            assert store.path.read_bytes() == before
