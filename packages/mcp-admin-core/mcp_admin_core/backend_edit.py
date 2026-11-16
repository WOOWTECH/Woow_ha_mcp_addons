"""Explicit partial connection edits. Original PUT backend remains whole replacement.

Only administrators see nonsecret fields and presence flags. Omission keeps bytes;
null clears only nullable fields. Existing credentials may be reused at a deliberately
changed destination, so clients must present that choice and bind the saved revision.

HM-12 (DQ-40 ⑨ (a), 2026-11-14; multi-profile plan 8.8 #41; contract 3.1, 4.1, section 9 #41 and HM-12's row on the
new-origin rule; unreleased): once the product is switched on (features.enabled), a stored credential no longer follows
a URL to another origin (scheme, host or port): new_origin_refused, which gateway.admin_action answers with 422
CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN (the PaaS Headscale code). Switched off, the reuse above is unchanged.
The same origin under another path is not a new origin (DQ-40 ⑨'s scope; a known limit, threat model section 3).
"""
from urllib.parse import unquote, urlsplit

from . import features, identity_fields
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
    'headscale': ('url', 'api_key'),
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


# The admin API names of n8n's stored fields (FIELDS above; identity_fields keeps the stored names).
_N8N_NAMES = {'backend_url': 'url', 'backend_key': 'key', 'mcp_access_token': 'mcp_access_token'}


def url_secrets(product):
    """identity_fields.URL_SECRETS in the admin API's names: {URL field: the secret fields that URL takes to its
    server}."""
    names = _N8N_NAMES if product == 'n8n' else {}
    return {names.get(url, url): tuple(names.get(secret, secret) for secret in carried)
            for url, carried in identity_fields.URL_SECRETS[product].items()}


def origin(url):
    """Where a URL's requests go (RFC 6454 section 4): its scheme, its host (lower case; an IPv6 literal without
    brackets) and its port, the scheme's own (80, 443) when none is written. Different spellings of one host (a
    trailing dot, an IPv4 address in another notation) are different origins here: the safe direction."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port
    if port is None:
        port = {'http': 80, 'https': 443}.get(scheme)
    return scheme, parts.hostname or '', port


def new_origin_refused(state, candidate, value):
    """Whether a backend/patch edit (value: its validated {"changes": ...}, candidate: the state it validates to) of a
    switched-on product moves one of the stored URLs to another origin without bringing every secret that URL takes
    there and holds now (DQ-40 ⑨). A secret brought counts whatever its value, null included where a field may be
    cleared (it is cleared then, not carried); a secret not stored (null) is not carried either; a URL cleared or set
    for the first time carries nothing. The same origin (another path, the host in capitals, the default port written
    out) needs nothing. PaaS (woow-mcp-server 69ac425 apps/headscale/headscale_mcp_admin/connection.py:104-109, the only
    product with the rule there) compares the whole URL; HA its origin, the scope DQ-40 ⑨ names."""
    product = state.product
    if not features.enabled(product):
        return False
    before, after, brought = _values(state), _values(candidate), set(value['changes'])
    for url, carried in url_secrets(product).items():
        old, new = before.get(url), after.get(url)
        if old is None or new is None or origin(old) == origin(new):
            continue
        if any(before.get(secret) is not None and secret not in brought for secret in carried):
            return True
    return False
