"""W2a LOCAL tests. Invented credentials, never a live backend."""
import json
import os

import pytest
from pydantic import ValidationError

from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.products import ProductStore, PRODUCTS, TOOLS, child_spec
from mcp_admin_core.policy import Denied, authorize


def call(name, arguments):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}


@pytest.mark.parametrize('product', PRODUCTS)
def test_product_bootstrap_is_unconfigured_and_cannot_launch(tmp_path, product):
    store = ProductStore(tmp_path / product, product)
    try:
        assert store.load().product == product
        assert not store.load().configured
        assert child_spec(store.load(), store.directory) is None
        with pytest.raises(ConfigError):
            store.update(connection={'command': 'sh', 'env': {}})
        other = next(p for p in PRODUCTS if p != product)
        with pytest.raises(ConfigError):
            store.update(product=other)
    finally:
        store.close()


def test_v1_migration_preserves_every_gui_field_and_rollback_fails_closed(tmp_path):
    old = Store(tmp_path / 'state')
    old.update(backend_url='http://127.0.0.1:9999', backend_key='DUMMY', writes_enabled=True,
               disabled=['search_nodes'], endpoint='http://mcp.test/mcp')
    original = old.load().model_dump()
    old.close()
    migrated = ProductStore(tmp_path / 'state', 'n8n')
    for key, value in original.items():
        if key != 'schema_version':
            assert getattr(migrated.load(), key) == value
    raw = migrated.path.read_bytes()
    migrated.close()
    with pytest.raises(ConfigError):
        Store(tmp_path / 'state')
    assert (tmp_path / 'state/state.json').read_bytes() == raw
    reopened = ProductStore(tmp_path / 'state', 'n8n')
    assert reopened.path.read_bytes() == raw
    reopened.close()


@pytest.mark.parametrize('bad', ['wrong_product', 'future', 'corrupt', 'incomplete'])
def test_invalid_migration_is_not_rewritten(tmp_path, bad):
    old = Store(tmp_path / 'state')
    raw = old.load().model_dump()
    old.close()
    product = 'emqx' if bad == 'wrong_product' else 'n8n'
    if bad == 'future': raw['schema_version'] = 999
    if bad == 'incomplete': raw.pop('disabled')
    data = b'{' if bad == 'corrupt' else json.dumps(raw).encode()
    path = tmp_path / 'state/state.json'
    path.write_bytes(data)
    with pytest.raises(ConfigError): ProductStore(tmp_path / 'state', product)
    assert path.read_bytes() == data


@pytest.mark.parametrize(('product', 'name', 'good', 'bad'), [
    ('odoo', 'list_models', {'limit': 5}, {'instance': 'other'}),
    ('odoo-manage', 'list_models', {}, {'ctx': {}}),
    ('hermes', 'hermes_inspect', {'target': 'capabilities'}, {}),
    ('hermes', 'hermes_model', {}, {'action': 'list'}),
    ('hermes', 'hermes_gateway', {}, {'action': 'restart'}),
    ('hermes', 'hermes_skill', {'action': 'list'}, {'action': 'enable', 'name': 'x'}),
    ('opendesign', 'get_project', {'project_id': '12345678-1234-1234-1234-123456789abc'}, {'project_id': '../secrets'}),
    ('emqx', 'emqx_cluster_status', {}, {'emqx': {}}),
    ('litellm', 'litellm_list_models', {}, {'ctx': {}}),
    ('nextcloud', 'get_file_tree', {'path': 'Documents', 'depth': 3}, {'path': 'Documents', 'depth': 4}),
    ('nextcloud', 'read_text_file', {'path': 'Documents/notes.md'}, {'path': '../other-user/notes.md'}),
    ('nextcloud', 'list_tasks', {'calendar': 'personal', 'limit': 500}, {'limit': 501}),
])
def test_exact_source_arguments_and_unknown_deny(tmp_path, product, name, good, bad):
    store = ProductStore(tmp_path / product, product)
    try:
        authorize(call(name, good), TOOLS[product], store.load())
        with pytest.raises(Denied): authorize(call(name, bad), TOOLS[product], store.load())
        with pytest.raises(Denied): authorize(call('unknown', {}), TOOLS[product], store.load())
        store.update(disabled=[name])
        with pytest.raises(Denied): authorize(call(name, good), TOOLS[product], store.load())
    finally: store.close()


def test_writer_enable_and_path_policy(tmp_path):
    store = ProductStore(tmp_path / 'state', 'opendesign')
    args = {'project_id': '12345678-1234-1234-1234-123456789abc'}
    try:
        with pytest.raises(Denied): authorize(call('delete_project', args), TOOLS['opendesign'], store.load())
        store.update(writes_enabled=True)
        authorize(call('delete_project', args), TOOLS['opendesign'], store.load())
        for value in ('../a', '/etc/passwd', 'x%2fy', 'x?secret', 'x\\y', './x'):
            with pytest.raises(Denied):
                authorize(call('get_file_info', {**args, 'file_path': value}), TOOLS['opendesign'], store.load())
    finally: store.close()
