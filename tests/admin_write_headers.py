"""Explicit reviewed headers for positive admin-write scenarios, never auto-injected."""
import secrets
import time


def reviewed_headers(bootstrap, headers=None):
    return {**(headers or {}), 'x-csrf-token': bootstrap['csrf'],
            'if-match': '"' + bootstrap['configuration']['revision'] + '"',
            'idempotency-key': f'{int(time.time() * 1000)}.{secrets.token_urlsafe(16)}'}


async def current_headers(client, headers):
    """Explicitly review current state before an independent positive mutation."""
    boot = (await client.get('/api/bootstrap', headers=headers)).json()
    return reviewed_headers(boot, headers)
