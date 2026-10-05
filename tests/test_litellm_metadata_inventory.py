"""Scoped drift check: current LiteLLM source, policy and rendered metadata.

Other products' pinned source evidence is carried forward, NOT re-observed.
This avoids installing six unrelated apps just to regenerate this batch.
The original complete inventory test remains the full-environment gate.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scoped_inventory(document):
    spec = importlib.util.spec_from_file_location('litellm_inventory_generator', ROOT/'scripts/tool_inventory.py')
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    evidence_keys = ('source', 'line', 'evidence', 'operations', 'source_signature', 'source_schema')
    source = {product: {t['name']: {k:t[k] for k in evidence_keys if k in t} for t in group['tools']}
              for product,group in document['products'].items()}
    rows, digests = {}, dict(document['source_digests'])
    prefix = 'apps/litellm/vendor/'
    paths = sorted((ROOT/prefix).rglob('*.py'))
    current = {str(path.relative_to(ROOT)) for path in paths}
    digests = {k:v for k,v in digests.items() if not k.startswith(prefix) or k in current}
    for path in paths:
        relative = str(path.relative_to(ROOT))
        digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for node in ast.walk(ast.parse(path.read_bytes())):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            for dec in node.decorator_list:
                if not (isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr=='tool'): continue
                name = next((k.value.value for k in dec.keywords if k.arg=='name' and isinstance(k.value,ast.Constant)),node.name)
                assert name not in rows
                # These five tools have no operation selector. Fail if that drifts.
                for compare in ast.walk(node):
                    assert not (isinstance(compare,ast.Compare) and isinstance(compare.left,ast.Name)
                                and compare.left.id in ('action','operation','target'))
                rows[name] = {'source':relative,'line':node.lineno,'evidence':'python-decorator-AST',
                              'operations':{},'source_signature':ast.unparse(node.args)}
    source['litellm'] = rows
    inventory.source_inventory = lambda: (source,digests)
    return inventory.build(), inventory.markdown


def test_scoped_source_schema_hashes_and_rendered_docs():
    document = json.loads((ROOT/'docs/tool-surface.json').read_text())
    actual, markdown = scoped_inventory(document)
    assert actual == document
    assert markdown(actual) == (ROOT/'docs/tool-surface.md').read_text()
    assert actual['products']['litellm']['supported_count'] == 12
    assert actual['products']['litellm']['upstream_count'] == 40


def test_metadata_patch_hashes():
    ledger = json.loads((ROOT/'docs/provenance/runtime-patches.json').read_text())
    paths = {'apps/litellm/vendor/woow_litellm_mcp_server/metadata.py',
             'packages/mcp-admin-core/mcp_admin_core/expansion.py'}
    rows = [row for row in ledger['patches'] if row['path'] in paths]
    assert len(rows) == len(paths)
    for row in rows:
        assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest() == row['sha256']
        assert row['change']
