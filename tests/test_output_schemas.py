"""Only reviewed schema pins can change public metadata; no resolver or network."""
import copy
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from mcp_admin_core import output_schemas as contracts
from mcp_admin_core.policy import filter_list, listed_tool
from mcp_admin_core.products import ProductStore, TOOLS
from mcp_admin_core.surface import listing
from mcp_admin_core.tool_snapshot import LISTED
from test_tool_snapshot import own_listing

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'packages/mcp-admin-core/mcp_admin_core/output_schemas.json').read_text())
ENTRIES = DATA['entries']


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['product'] + '/' + e['tool'])
def test_audited_schema_is_exact_and_isolated(entry):
    product, name, schema = entry['product'], entry['tool'], entry['schema']
    returned = contracts.reviewed_output_schema(product, name, copy.deepcopy(schema))
    assert returned == schema and returned is not schema
    returned.clear()
    assert contracts.reviewed_output_schema(product, name, schema) == schema
    assert contracts._digest(product, name, schema) == entry['binding_sha256']
    snapshot = next(t for t in LISTED[product] if t['name'] == name)
    assert snapshot['outputSchema'] == schema
    # Child-controlled product/title cannot select a pin for another product.
    assert contracts.reviewed_output_schema('wrong-product', name, schema) is None
    assert contracts.reviewed_output_schema(product, 'unreviewed-tool', schema) is None


def test_exact_source_bytes_are_reviewed_not_guessed_from_type_hints():
    assert {p: sum(e['product'] == p for e in ENTRIES) for p in DATA['sources']} == {'litellm': 35, 'nextcloud': 8}
    for source in DATA['sources'].values():
        assert source['ha_commit'] == '235338cc7d1a02d17fbb93b631e37c77a20c7889'
        for name, expected in source['files'].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert 'woow_backend_probe' not in {e['tool'] for e in ENTRIES}
    assert 'get_file_content' not in {e['tool'] for e in ENTRIES}  # resource/content result, no output schema
    assert 'litellm_spend_logs' not in {e['tool'] for e in ENTRIES}  # no declared structured contract


@pytest.mark.parametrize('candidate', [None, True, [], 'object', {}, {'type': 'array'},
    {'type': 'object'}, {'type': 'object', 'additionalProperties': False},
    {'type': 'object', '$ref': 'https://schema.invalid/private'},
    {'type': 'object', '$ref': '#/$defs/Local', '$defs': {'Local': {'type': 'object'}}},
    {'type': 'object', '$id': 'https://schema.invalid/'},
    {'type': 'object', 'properties': {'x': {'type': 'string', 'pattern': '(a+)+$'}}},
    {'type': 'object', 'properties': {'x': {'type': 'string', 'format': 'uri'}}},
    {'type': 'object', 'properties': {'x': {'$dynamicRef': 'https://schema.invalid/'}}},
    {'type': 'object', 'x-unknown': True},
    {'type': 'object', 'additionalProperties': True, 'description': 'child supplied text'},
    {'type': 'object', 'additionalProperties': 1},
    {'type': 'object', 'properties': [], 'required': ['x']},
])
def test_changed_unknown_external_and_unsupported_schema_is_omitted(candidate):
    assert contracts.reviewed_output_schema('litellm', 'litellm_list_models', candidate) is None


def test_cycles_and_deep_or_oversize_schema_fail_closed():
    cycle = {'type': 'object'}; cycle['properties'] = {'loop': cycle}
    assert contracts.reviewed_output_schema('litellm', 'litellm_list_models', cycle) is None
    assert contracts.reviewed_output_schema('litellm', 'litellm_list_models',
        {'type': 'object', 'properties': {'x' * 50000: {'type': 'string'}}}) is None


@pytest.mark.parametrize('tamper', ['digest', 'product', 'duplicate', 'external_ref', 'pattern', 'missing_file'])
def test_packaged_registry_corruption_does_not_open_a_general_relay(tmp_path, monkeypatch, tamper):
    data = copy.deepcopy(DATA); entry = data['entries'][0]
    if tamper == 'digest': entry['binding_sha256'] = '0' * 64
    if tamper == 'product': entry['product'] = 'another-product'
    if tamper == 'duplicate': data['entries'].append(entry)
    if tamper in ('external_ref', 'pattern'):
        entry['schema'] = {'type': 'object', 'properties': {'x': (
            {'$ref': 'https://schema.invalid/'} if tamper == 'external_ref' else {'type': 'string', 'pattern': '(a+)+$'})}}
        # Even a recomputed digest cannot bless a new schema vocabulary.
        entry['binding_sha256'] = contracts._digest(entry['product'], entry['tool'], entry['schema'])
        entry['schema_sha256'] = hashlib.sha256(contracts._encoded(entry['schema'])).hexdigest()
    path = tmp_path / 'pins.json'
    if tamper != 'missing_file': path.write_text(json.dumps(data))
    monkeypatch.setattr(contracts, '_DATA', path); contracts._reviewed.cache_clear()
    try:
        assert contracts.reviewed_output_schema('litellm', 'litellm_list_models', ENTRIES[0]['schema']) is None
    finally:
        contracts._reviewed.cache_clear()


def test_only_output_schema_is_added_existing_metadata_rules_remain():
    name = 'litellm_update_model'; local = TOOLS['litellm'][name]
    tool = {'name': name, 'product': 'litellm', 'inputSchema': {'type': 'object'},
            'outputSchema': {'type': 'object', 'additionalProperties': True},
            'description': 'D', 'title': 'T', 'icons': [{'src': 'https://x.invalid'}],
            '_meta': {'secret': 'x'}, 'execution': {'taskSupport': 'required'},
            'annotations': {'readOnlyHint': True, 'idempotentHint': True, 'destructiveHint': False,
                            'openWorldHint': False, 'title': 'A', 'extra': True}}
    before = listed_tool(tool, local)
    after = listed_tool(tool, local, product='litellm')
    assert after.pop('outputSchema') == tool['outputSchema']
    assert before == after and before['annotations'] == {'title': 'A'}
    assert set(before) == {'name', 'inputSchema', 'description', 'title', 'annotations'}
    assert 'outputSchema' not in listed_tool(tool, replace(local, child_schema=False), product='litellm')
    assert 'outputSchema' not in listed_tool({k:v for k,v in tool.items() if k != 'outputSchema'}, local, product='litellm')


@pytest.mark.parametrize('product', ['litellm', 'nextcloud'])
async def test_fallback_output_schema_stable_and_policy_still_filters(tmp_path, product):
    available = {'child': 'backoff', 'ready': False, 'backend': 'unknown', 'reason': None}
    with closing(ProductStore(tmp_path / product, product)) as store:
        first = await own_listing(store, product, available)
        second = await own_listing(store, product, available)
        assert first == second
        assert sum('outputSchema' in t for t in first['tools']) == (35 if product == 'litellm' else 8)
        name = 'litellm_update_model' if product == 'litellm' else 'delete_file_checked'
        store.update(disabled=[name])
        disabled = await own_listing(store, product, available)
        assert name not in {t['name'] for t in disabled['tools']}
        assert next(t for t in listing(product) if t['name'] == name)['outputSchema']
        store.update(disabled=[], enabled_write_tools=[])
        no_grant = await own_listing(store, product, available)
        assert name not in {t['name'] for t in no_grant['tools']}


def test_first_entry_and_cursor_rules_still_apply(tmp_path):
    with closing(ProductStore(tmp_path, 'litellm')) as store:
        name='litellm_list_models'; tools=[{'name':name,'outputSchema':{'type':'object'}},
            {'name':name,'outputSchema':ENTRIES[0]['schema']}, {'name':'unknown','outputSchema':ENTRIES[0]['schema']}]
        result=filter_list({'result':{'tools':tools,'nextCursor':'next','_meta':{'x':1}}},TOOLS['litellm'],store.load())['result']
        assert list(result)==['tools','nextCursor'] and len(result['tools'])==1
        assert 'outputSchema' not in result['tools'][0]  # duplicate cannot supply a later accepted schema
