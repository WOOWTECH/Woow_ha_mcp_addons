"""W2b grants must not inherit the legacy blanket writer switch."""
import pytest
from mcp_admin_core.products import ProductState, ProductStore, TOOLS
from mcp_admin_core.policy import authorize, Denied


def call(name, arguments):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}


def test_new_mixed_writer_requires_exact_operation_grant():
    state = ProductState(product='hermes', token='a'*43, child_token='b'*43, writes_enabled=True)
    message = call('hermes_skill', {'action': 'disable', 'name': 'example'})
    with pytest.raises(Denied):
        authorize(message, TOOLS['hermes'], state)
    state = ProductState(**{**state.model_dump(), 'enabled_write_tools': ['hermes_skill:disable']})
    authorize(message, TOOLS['hermes'], state)
    for args in ({'action': 'enable', 'name': 'example'}, {'action': 'unknown'}, {'action': 'list', 'name': 'example'}):
        with pytest.raises(Denied):
            authorize(call('hermes_skill', args), TOOLS['hermes'], state)
    authorize(call('hermes_skill', {'action': 'list'}), TOOLS['hermes'], state)


def test_grants_validate_product_and_preserve_legacy_state(tmp_path):
    store = ProductStore(tmp_path, 'hermes')
    original = store.path.read_bytes()
    for grant in ('n8n_delete_workflow', 'hermes_skill:unknown', 'hermes_inspect', '*'):
        with pytest.raises(Exception):
            store.update(enabled_write_tools=[grant])
        assert store.path.read_bytes() == original
    store.update(enabled_write_tools=['hermes_skill:disable'])
    assert store.load().enabled_write_tools == ['hermes_skill:disable']
    store.close()


def test_old_v2_switch_never_grants_new_writers(tmp_path):
    import json
    store = ProductStore(tmp_path, 'hermes')
    old = store.load().model_dump()
    old.pop('enabled_write_tools', None)
    old['schema_version'] = 2
    old['writes_enabled'] = True
    store.path.write_text(json.dumps(old))
    store.close()
    store = ProductStore(tmp_path, 'hermes')
    assert store.load().schema_version == 3
    assert store.load().enabled_write_tools == []
    with pytest.raises(Denied):
        authorize(call('hermes_skill', {'action': 'disable', 'name': 'example'}), TOOLS['hermes'], store.load())
    store.close()
