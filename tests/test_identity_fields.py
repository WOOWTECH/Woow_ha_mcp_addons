"""HM-07: every stored backend field and every state field is classified (identity_fields; not wired yet).

Multi-profile plan §4.4 ("身分欄位分類"), §8.8 #40; FEATURE-MATRIX FM-80; DQ-40 ⑩ (2026-11-14). HM-12 (a changed
identity rotates the token), HM-13b (restore records: identity and policy, never secrets) and DQ-40 ⑨ (a new
origin needs its secret again) use these tables. A field added to a connection model or to ProductState without a
class fails here (PaaS tests/test_restore_runbook.py:1210-1456 and tests/test_launch_policy.py:92-379 do the same for
the PaaS inventory and launch policies).
"""
import json
import subprocess
import typing
from pathlib import Path

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import backend_edit, features, identity_fields, profiles
from mcp_admin_core.config import State
from mcp_admin_core.identity_fields import IDENTITY, OPTION, SECRET
from mcp_admin_core.products import (
    CONNECTIONS, OWNER_DEFAULTS, TOKEN_HISTORY, URL_FIELDS, Product, ProductState, profile_initial_state,
)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

ROOT = Path(__file__).resolve().parents[1]
N8N_STATE_FIELDS = ('backend_url', 'backend_key', 'mcp_access_token')
N8N_API_NAMES = {'url': 'backend_url', 'key': 'backend_key', 'mcp_access_token': 'mcp_access_token'}


def model_fields(product):
    if product == 'n8n':
        return {name: ProductState.model_fields[name] for name in N8N_STATE_FIELDS}
    return dict(CONNECTIONS[product].model_fields)


def test_every_product_and_every_backend_field_is_classified():
    assert set(identity_fields.BACKEND_FIELDS) == set(typing.get_args(Product)) == features.KNOWN_PRODUCTS
    for product, fields in identity_fields.BACKEND_FIELDS.items():
        assert list(fields) == list(model_fields(product)), product  # same names, the models' order
        assert set(fields.values()) <= {IDENTITY, SECRET, OPTION}, product


def test_secret_fields_are_exactly_the_credentials_the_models_hide():
    # A credential is declared repr=False in its model (it never shows in a repr or a traceback); every such field,
    # and only those, is SECRET.
    for product in identity_fields.BACKEND_FIELDS:
        hidden = {name for name, field in model_fields(product).items() if field.repr is False}
        assert set(identity_fields.fields(product, SECRET)) == hidden, product
    assert {name for name, field in ProductState.model_fields.items() if field.repr is False} == {
        'token', 'child_token', 'connection', *[n for n in N8N_STATE_FIELDS if n != 'backend_url']}


def test_the_fm80_table():
    identity = {product: identity_fields.fields(product, IDENTITY) for product in identity_fields.BACKEND_FIELDS}
    assert identity == {
        'odoo': ('url', 'database', 'username'), 'odoo-manage': ('url', 'database', 'username'),
        'n8n': ('backend_url',), 'hermes': ('gateway_url', 'dashboard_url', 'dashboard_username'),
        'opendesign': ('url',), 'emqx': ('url',), 'litellm': ('url',), 'nextcloud': ('url', 'username'),
        'headscale': ('url',)}
    secrets = {name for product in identity_fields.BACKEND_FIELDS for name in identity_fields.fields(product, SECRET)}
    assert secrets == {'password', 'backend_key', 'mcp_access_token', 'gateway_api_key', 'dashboard_password',
                       'master_key', 'app_password', 'api_key', 'api_secret'}
    assert {product: identity_fields.fields(product, OPTION) for product in identity_fields.BACKEND_FIELDS
            if identity_fields.fields(product, OPTION)} == {'odoo-manage': ('mode',)}


def test_every_backend_url_is_an_identity_field():
    for product, names in URL_FIELDS.items():
        assert set(names) <= set(identity_fields.fields(product, IDENTITY)), product
    assert identity_fields.BACKEND_FIELDS['n8n']['backend_url'] == IDENTITY


def test_the_token_rotating_fields():
    # I11: an Odoo token stays bound to one backend identity (PaaS #131: url, database, username); DQ-40 ⑩ (a) adds
    # Nextcloud url/username and Hermes gateway_url/dashboard_url/dashboard_username. A password or key change, or
    # the first setup, never rotates (plan §9). The other products' account is decided by their secret.
    assert {product: identity_fields.rotating_fields(product) for product in identity_fields.BACKEND_FIELDS} == {
        'odoo': ('url', 'database', 'username'), 'nextcloud': ('url', 'username'),
        'hermes': ('gateway_url', 'dashboard_url', 'dashboard_username'),
        'odoo-manage': (), 'n8n': (), 'opendesign': (), 'emqx': (), 'litellm': (), 'headscale': ()}
    for product in identity_fields.BACKEND_FIELDS:
        assert set(identity_fields.rotating_fields(product)) <= set(identity_fields.fields(product, IDENTITY))
    with pytest.raises(ValueError):
        identity_fields.rotating_fields('bogus')
    with pytest.raises(ValueError):
        identity_fields.fields('odoo', 'bogus')


def test_the_admin_api_fields_and_secrets_agree():
    for product, names in backend_edit.FIELDS.items():
        stored = tuple(N8N_API_NAMES[name] if product == 'n8n' else name for name in names)
        assert stored == tuple(identity_fields.BACKEND_FIELDS[product]), product
        api_secrets = {N8N_API_NAMES[n] if product == 'n8n' else n for n in names if n in backend_edit.SECRETS}
        assert api_secrets == set(identity_fields.fields(product, SECRET)), product


def test_the_connection_page_fields_and_kinds_agree():
    # PaaS tests/test_launch_policy.py:372 (the backend connection labels are the connection page's): here the
    # panel's own field list (packages/mcp-admin-ui/src/contracts.js) names the same fields, its secret kinds the
    # same secrets.
    probe = subprocess.run(['node', '--input-type=module', '-e', '''
import {products} from './packages/mcp-admin-ui/src/contracts.js';
console.log(JSON.stringify(Object.fromEntries(Object.entries(products).map(([k, v]) => [k, v.fields.map(f => [f[0], f[2]])]))));
'''], capture_output=True, text=True, cwd=ROOT, timeout=20, env={'PATH': '/usr/bin:/bin'})
    assert probe.returncode == 0, probe.stderr
    panel = json.loads(probe.stdout)
    assert set(panel) == set(identity_fields.BACKEND_FIELDS)
    for product, rows in panel.items():
        names = tuple(N8N_API_NAMES[name] if product == 'n8n' else name for name, _ in rows)
        assert names == tuple(identity_fields.BACKEND_FIELDS[product]), product
        secret = {N8N_API_NAMES.get(name, name) if product == 'n8n' else name for name, kind in rows
                  if kind in ('secret', 'optional-secret')}
        assert secret == set(identity_fields.fields(product, SECRET)), product


def test_every_state_field_has_a_class():
    assert set(identity_fields.STATE_FIELDS) == set(ProductState.model_fields)
    assert set(State.model_fields) <= set(identity_fields.STATE_FIELDS)
    by_class = {}
    for name, kind in identity_fields.STATE_FIELDS.items():
        by_class.setdefault(kind, set()).add(name)
    assert by_class == {
        identity_fields.CREDENTIAL: {'token', 'child_token'},
        identity_fields.BACKEND: {'connection', 'backend_url', 'backend_key', 'mcp_access_token'},
        identity_fields.POLICY: {'writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations',
                                 'odoo_write_switches', 'odoo_allowed_methods'},
        identity_fields.SESSION: {'n8n_session'},
        identity_fields.ENDPOINT: {'endpoint'},
        identity_fields.RECORD: {OWNER_DEFAULTS, TOKEN_HISTORY, 'schema_version', 'product'},
    }
    # The stored backend fields of n8n are its BACKEND state fields; every other product keeps them in `connection`.
    assert {n for n in N8N_STATE_FIELDS} | {'connection'} == by_class[identity_fields.BACKEND]


@pytest.mark.parametrize('product', [p for p in sorted(identity_fields.BACKEND_FIELDS) if profiles.supports_profiles(p)])
def test_a_new_profile_follows_the_classes(product, log_scan):
    # DQ-02 (a), read through the classes, so a new state field gets a rule here as soon as it gets a class.
    default = ProductState(product=product, token='T' * 43, child_token='C' * 43, writes_enabled=False,
                           disabled=['x_tool'], endpoint='https://ha.invalid/mcp')
    new = profile_initial_state(default)
    log_scan.watch_state(new)
    for name, kind in identity_fields.STATE_FIELDS.items():
        value = getattr(new, name)
        if kind == identity_fields.CREDENTIAL:
            assert value not in (None, getattr(default, name)) and len(value) == 43, name
        elif kind in (identity_fields.BACKEND, identity_fields.SESSION, identity_fields.ENDPOINT):
            assert value is None, name
        elif kind == identity_fields.POLICY:
            expected = (default.effective_odoo_write_switches if name == 'odoo_write_switches' and product == 'odoo'
                        else getattr(default, name))
            assert value == expected, name
        else:
            assert value == {'schema_version': 4, 'product': product}.get(name), name
