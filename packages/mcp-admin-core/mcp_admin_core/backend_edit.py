"""Explicit partial connection edits. Original PUT backend remains whole replacement.

Only administrators see nonsecret fields and presence flags. Omission keeps bytes;
null clears only nullable fields. Existing credentials may be reused at a deliberately
changed destination, so clients must present that choice and bind the saved revision.
"""
from urllib.parse import unquote

from .redact import secret_values

FIELDS = {
    'n8n': ('url', 'key', 'mcp_access_token'),
    'odoo': ('url', 'database', 'username', 'password'),
    'odoo-manage': ('url', 'database', 'username', 'api_key', 'mode'),
    'hermes': ('gateway_url', 'gateway_api_key', 'dashboard_url', 'dashboard_username', 'dashboard_password'),
    'opendesign': ('url',),
    'emqx': ('url', 'api_key', 'api_secret'),
    'litellm': ('url', 'master_key'),
    'nextcloud': ('url', 'username', 'app_password'),
}
SECRETS = frozenset(('key', 'mcp_access_token', 'password', 'api_key', 'api_secret',
                     'gateway_api_key', 'dashboard_password', 'master_key', 'app_password'))
NULLABLE = frozenset(('mcp_access_token', 'dashboard_url', 'dashboard_username', 'dashboard_password'))


def _values(state):
    if state.product == 'n8n':
        return {'url': state.backend_url, 'key': state.backend_key, 'mcp_access_token': state.mcp_access_token}
    return state.connection.model_dump() if state.connection is not None else {}


def view(state):
    values = _values(state)
    fields = FIELDS[state.product]
    # Public field names do not guarantee public contents: credentials can be
    # embedded in URL paths (including reversible percent encodings). Withhold
    # the whole display value, never a mask that could be accidentally saved.
    secrets = set(secret_values(state)) | {value for name, value in values.items()
                                         if name in SECRETS and isinstance(value, str) and value}
    public, withheld = {}, []
    for name in fields:
        if name in SECRETS:
            continue
        value = values.get(name)
        decoded = value
        while isinstance(decoded, str):
            if any(secret in decoded for secret in secrets):
                withheld.append(name)
                value = None
                break
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        public[name] = value
    return {'contract': 'woow-connection-patch-v1',
            'values': public, 'withheld_fields': withheld,
            'secret_set': {name: values.get(name) is not None for name in fields if name in SECRETS}}


def changes(state, value):
    if (not state.configured or not isinstance(value, dict) or set(value) != {'changes'}
            or not isinstance(value['changes'], dict) or not value['changes']
            or set(value['changes']) - set(FIELDS[state.product])):
        raise ValueError('invalid partial connection edit')
    patch = value['changes']
    if any(item is None and name not in NULLABLE for name, item in patch.items()):
        raise ValueError('required field cannot be cleared')
    merged = {**_values(state), **patch}
    if state.product == 'n8n':
        return {'backend_url': merged['url'], 'backend_key': merged['key'],
                'mcp_access_token': merged['mcp_access_token']}
    return {'connection': merged}
