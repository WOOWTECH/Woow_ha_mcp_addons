"""HA product state only: token transitions stay durable, bounded and masked."""
from contextlib import closing
import json
import os

import httpx
import pytest

from mcp_admin_core.config import ConfigError
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.migration import plan_migration
from mcp_admin_core.products import ProductStore
from n8n_adapter import TOOLS


IDENTITY = {'x-remote-user-id': 'token-history-review'}


def test_existing_state_is_not_rewritten_until_a_token_transition(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        before = store.path.read_bytes()
        assert 'token_history' not in json.loads(before)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.path.read_bytes() == before
        assert store.load().token_history is None
        old = store.load().token
        new = 'N' * 43
        updated, changed = store.change_token(new, action='rotate')
        assert changed and updated.token == new
        assert updated.token_history[0].previous_token_masked == old[:4] + '*' * 20 + old[-4:]
        assert old not in store.path.read_text()
        for index in range(5):
            store.change_token(chr(65 + index) * 43, action='rotate')
        latest = store.load()
        assert len(latest.token_history) == 5
        assert all(item.action == 'rotate' for item in latest.token_history)
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.load() == latest


def test_revoke_is_idempotent_without_a_false_second_event(tmp_path):
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        old = store.load().token
        updated, changed = store.change_token(None, action='revoke')
        assert changed and updated.token is None
        assert updated.token_history[0].previous_token_masked == old[:4] + '*' * 20 + old[-4:]
        before = store.path.read_bytes()
        assert store.change_token(None, action='revoke') == (updated, False)
        assert store.path.read_bytes() == before
        updated, changed = store.change_token('X' * 43, action='rotate')
        assert changed and updated.token_history[0].previous_token_masked == ''
        assert [item.action for item in updated.token_history] == ['rotate', 'revoke']


def test_schema_four_migration_preview_preserves_recorded_history(tmp_path):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        updated, _ = store.change_token('M' * 43, action='rotate')
        raw = store.path.read_bytes()
        preview = plan_migration(json.loads(raw), 'n8n', policy='all_on')
        assert preview.state.token_history == updated.token_history
        assert store.path.read_bytes() == raw


@pytest.mark.parametrize('history', [
    None,
    [{'action': 'rotate', 'rotated_at': '2026-10-29T00:00:00+00:00', 'previous_token_masked': 'A' * 43}],
    [{'action': 'revoke', 'rotated_at': '2026-10-29T00:00:00+00:00', 'previous_token_masked': '', 'token': 'X' * 43}],
    [{'action': 'set', 'rotated_at': '2026-10-29T00:00:00+00:00', 'previous_token_masked': ''}],
    [{'action': 'rotate', 'rotated_at': '2026-02-30T00:00:00+00:00', 'previous_token_masked': ''}],
    [{'action': 'rotate', 'rotated_at': '2026-10-29T00:00:00+08:00', 'previous_token_masked': ''}],
    [{'action': 'rotate', 'rotated_at': '2026-10-29T00:00:00+00:00', 'previous_token_masked': ''}] * 6,
])
def test_corrupt_history_is_not_repaired_or_rewritten(tmp_path, history):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        raw = json.loads(store.path.read_text())
    raw['token_history'] = history
    before = json.dumps(raw).encode()
    (tmp_path / 'state.json').write_bytes(before)
    with pytest.raises(ConfigError):
        ProductStore(tmp_path, 'n8n')
    assert (tmp_path / 'state.json').read_bytes() == before


def test_failed_durable_write_keeps_old_token_and_history(tmp_path, monkeypatch):
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        before = store.path.read_bytes()
        def fail(*_):
            raise OSError('injected local disk failure')
        monkeypatch.setattr(os, 'replace', fail)
        with pytest.raises(ConfigError):
            store.change_token('X' * 43, action='rotate')
        assert store.path.read_bytes() == before
        monkeypatch.undo()
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.path.read_bytes() == before


async def test_admin_bootstrap_only_exposes_masked_history(tmp_path):
    async def role(_): return True
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        original = store.load().token
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, TOOLS, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://local') as client:
                boot = (await client.get('/api/bootstrap', headers=IDENTITY)).json()
                assert boot['token_history'] == []
                assert boot['token_masked'] == original[:4] + '*' * 20 + original[-4:]
                headers = {**IDENTITY, 'x-csrf-token': boot['csrf']}
                rotated = await client.post('/api/token/rotate', headers=headers)
                assert rotated.status_code == 200
                new = rotated.json()['token']
                boot = (await client.get('/api/bootstrap', headers=IDENTITY)).json()
                assert original not in json.dumps(boot) and new not in json.dumps(boot)
                assert boot['token_masked'] == new[:4] + '*' * 20 + new[-4:]
                assert boot['token_history'] == [{'action': 'rotate', 'rotated_at': boot['token_history'][0]['rotated_at'],
                    'previous_token_masked': original[:4] + '*' * 20 + original[-4:]}]
                revoked = await client.post('/api/token/revoke', headers=headers)
                assert revoked.status_code == 204
                before = store.path.read_bytes()
                assert (await client.post('/api/token/revoke', headers=headers)).status_code == 204
                assert store.path.read_bytes() == before
                boot = (await client.get('/api/bootstrap', headers=IDENTITY)).json()
                assert [entry['action'] for entry in boot['token_history']] == ['revoke', 'rotate']
                assert new not in json.dumps(boot)
