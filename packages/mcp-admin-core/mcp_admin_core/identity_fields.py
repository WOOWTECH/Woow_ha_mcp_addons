"""Which stored fields name a backend account, which are secrets, and what each state field is (HM-07; HM-12 wires it).

Multi-profile plan §4.4 ("身分欄位分類"), §8.8 #40, #41; FEATURE-MATRIX FM-80, FM-152; DQ-02 (a) and DQ-40 ⑨, ⑩ (a)
(2026-11-14). Users: HM-12 (products.identity_rebound: a changed identity rotates the MCP token in the same write, I11;
backend_edit.new_origin_refused: a URL moved to another origin needs its secrets again, URL_SECRETS), HM-13b and HM-13c
(restore records and review cards show identity and policy, never a secret). Data only: what reads it decides when it
applies (a switched-on product only, for both of HM-12's rules). tests/test_identity_fields.py fails for a connection or
state field without a class.

Backend fields carry the stored names: a typed connection's field names, and n8n's top-level backend_url,
backend_key and mcp_access_token (its admin API calls them url, key and mcp_access_token: backend_edit.FIELDS).
"""
from __future__ import annotations

IDENTITY = 'identity'  # which backend, or which account on it, the add-on acts as
SECRET = 'secret'      # a credential: never recorded, never shown, never logged
OPTION = 'option'      # a connection setting that is neither (Odoo Manage's access mode)
KINDS = (IDENTITY, SECRET, OPTION)

BACKEND_FIELDS = {
    'odoo': {'url': IDENTITY, 'database': IDENTITY, 'username': IDENTITY, 'password': SECRET},
    'odoo-manage': {'url': IDENTITY, 'database': IDENTITY, 'username': IDENTITY, 'api_key': SECRET, 'mode': OPTION},
    'n8n': {'backend_url': IDENTITY, 'backend_key': SECRET, 'mcp_access_token': SECRET},
    'hermes': {'gateway_url': IDENTITY, 'gateway_api_key': SECRET, 'dashboard_url': IDENTITY,
               'dashboard_username': IDENTITY, 'dashboard_password': SECRET},
    'opendesign': {'url': IDENTITY},
    'emqx': {'url': IDENTITY, 'api_key': SECRET, 'api_secret': SECRET},
    'litellm': {'url': IDENTITY, 'master_key': SECRET},
    'nextcloud': {'url': IDENTITY, 'username': IDENTITY, 'app_password': SECRET},
    'headscale': {'url': IDENTITY, 'api_key': SECRET},
}

# Identity fields whose change rotates the MCP token (I11): Odoo as PaaS #131 (plan §9), Nextcloud and Hermes by
# DQ-40 ⑩ (a). Changing only a password or key, or the first setup, never rotates. The other products' account is
# decided by their secret (an API key), so they have none. What acts on them is products.IDENTITY_BOUND: Odoo's since
# HM-12; Hermes is intentionally not bound to these fields, matching PaaS.
TOKEN_ROTATING = {
    'odoo': ('url', 'database', 'username'),
    'nextcloud': ('url', 'username'),
    'hermes': ('gateway_url', 'dashboard_url', 'dashboard_username'),
}

# HM-12 (DQ-40 ⑨ (a); plan §8.8 #41): the secrets each backend URL takes to its server, in the stored names. A URL moved
# to another origin (scheme, host or port) brings these again, once its product is switched on
# (backend_edit.new_origin_refused); every URL of every product is named, and every secret of a product exactly once
# (tests/test_new_origin_secret.py). Hermes' gateway and dashboard are two servers with a secret each; n8n's API key
# and its instance-level MCP access token both go to the one n8n; OpenDesign sends no credential.
URL_SECRETS = {
    'odoo': {'url': ('password',)},
    'odoo-manage': {'url': ('api_key',)},
    'n8n': {'backend_url': ('backend_key', 'mcp_access_token')},
    'hermes': {'gateway_url': ('gateway_api_key',), 'dashboard_url': ('dashboard_password',)},
    'opendesign': {'url': ()},
    'emqx': {'url': ('api_key', 'api_secret')},
    'litellm': {'url': ('master_key',)},
    'nextcloud': {'url': ('app_password',)},
    'headscale': {'url': ('api_key',)},
}

# Every ProductState field (products.ProductState).
CREDENTIAL = 'credential'  # the MCP token and the child token: new for each profile, never copied or recorded
BACKEND = 'backend'        # the stored backend fields above: empty in a new profile
POLICY = 'policy'          # what the tools may do: a new profile copies the default profile's current value (DQ-02)
SESSION = 'session'        # n8n's native session settings: never copied (DQ-02), so a new profile has the defaults
ENDPOINT = 'endpoint'      # the public MCP endpoint the panel shows: a new profile does not store one
RECORD = 'record'          # bookkeeping: schema, product, token history, the owner-defaults migration marker
STATE_FIELDS = {
    'schema_version': RECORD, 'product': RECORD, 'token_history': RECORD, 'owner_defaults_20261025': RECORD,
    'token': CREDENTIAL, 'child_token': CREDENTIAL,
    'connection': BACKEND, 'backend_url': BACKEND, 'backend_key': BACKEND, 'mcp_access_token': BACKEND,
    'writes_enabled': POLICY, 'disabled': POLICY, 'enabled_write_tools': POLICY, 'denied_operations': POLICY,
    'odoo_write_switches': POLICY, 'odoo_allowed_methods': POLICY,
    'n8n_session': SESSION,
    'endpoint': ENDPOINT,
}


def fields(product: str, kind: str) -> tuple[str, ...]:
    """The product's stored backend fields of *kind*, in the connection model's order."""
    if product not in BACKEND_FIELDS or kind not in KINDS:
        raise ValueError('unknown product or field kind')
    return tuple(name for name, value in BACKEND_FIELDS[product].items() if value == kind)


def rotating_fields(product: str) -> tuple[str, ...]:
    if product not in BACKEND_FIELDS:
        raise ValueError('unknown product')
    return TOKEN_ROTATING.get(product, ())
