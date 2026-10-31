"""Reviewed public output contracts, never a general child-schema relay.

Only exact (product, tool, schema) pins are exposed. The finite JSON Schema
vocabulary below needs no resolver, regex compiler or format plug-in. The
reviewed Odoo contracts use four references to definitions in the same schema;
external, missing and recursive references remain unsupported. Neither schema
absence nor a mismatch is repaired using another tool's pin.
"""
import copy
import functools
import hashlib
import json
from pathlib import Path

_DATA = Path(__file__).with_name('output_schemas.json')
_TYPES = frozenset({'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'})
_KEYWORDS = frozenset({'type', 'properties', 'required', 'items', 'additionalProperties',
                       'anyOf', 'enum', 'const', 'title', 'description', 'default', '$defs', '$ref'})
_MAX_BYTES = 32768


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _safe_schema(schema):
    """Finite reviewed vocabulary, including Odoo's bounded local definitions.

    No network refs, regexes, formats, arbitrary annotations or recursion.
    This check applies to both packaged pins and child candidates; exact pin
    equality remains mandatory before a public schema is returned.
    """
    if type(schema) is not dict or schema.get('type') != 'object':
        return False
    definitions = schema.get('$defs', {})
    if type(definitions) is not dict or len(definitions) > 32:
        return False
    if any(type(name) is not str or not name or len(name) > 64
           or not name.replace('_', '').isalnum() or not name[0].isalpha()
           for name in definitions):
        return False
    # Definitions may not reference one another. All four reviewed Odoo refs
    # point from a property to a root-level definition, so this is sufficient
    # to prohibit cycles without invoking a resolver.
    todo = [(schema, 0, False)]
    count = 0
    while todo:
        node, depth, inside_definition = todo.pop()
        count += 1
        if count > 1024 or depth > 16 or type(node) is not dict or set(node) - _KEYWORDS:
            return False
        if not node:
            # The reviewed Odoo domain and index responses contain a few
            # unconstrained nested JSON values. The root is still an object.
            continue
        if '$ref' in node:
            ref = node['$ref']
            return_ref = (set(node) == {'$ref'} and not inside_definition
                          and type(ref) is str and ref.startswith('#/$defs/')
                          and ref.removeprefix('#/$defs/') in definitions)
            if not return_ref:
                return False
            continue
        if '$defs' in node:
            if node is not schema:
                return False
            todo.extend((value, depth + 1, True) for value in definitions.values())
        kind = node.get('type')
        if kind is not None and (type(kind) is not str or kind not in _TYPES):
            return False
        if kind is None and 'anyOf' not in node:
            return False
        for key in ('title', 'description'):
            value = node.get(key)
            if key in node and (type(value) is not str or len(value) > 512
                                or any(ord(char) < 32 for char in value)):
                return False
        if 'default' in node:
            value = node['default']
            if value is not None and (type(value) is not str or len(value) > 256):
                return False
        if 'properties' in node:
            props = node['properties']
            if kind != 'object' or type(props) is not dict or len(props) > 128:
                return False
            if any(type(k) is not str or not k or len(k) > 128 for k in props):
                return False
            todo.extend((v, depth + 1, inside_definition) for v in props.values())
        if 'required' in node:
            required = node['required']
            if (kind != 'object' or type(required) is not list
                    or any(type(k) is not str for k in required)
                    or len(required) != len(set(required))
                    or not set(required) <= set(node.get('properties', {}))):
                return False
        if 'additionalProperties' in node:
            value = node['additionalProperties']
            if kind != 'object' or type(value) not in (bool, dict):
                return False
            if type(value) is dict:
                todo.append((value, depth + 1, inside_definition))
        if 'items' in node:
            if kind != 'array':
                return False
            todo.append((node['items'], depth + 1, inside_definition))
        if kind == 'array' and 'items' not in node:
            return False
        if 'anyOf' in node:
            branches = node['anyOf']
            if type(branches) is not list or not 1 < len(branches) <= 8:
                return False
            todo.extend((v, depth + 1, inside_definition) for v in branches)
        for key in ('enum', 'const'):
            if key in node:
                values = node[key] if key == 'enum' else [node[key]]
                if (kind != 'string' or type(values) is not list or not 0 < len(values) <= 128
                        or any(type(v) is not str or len(v) > 256 for v in values)):
                    return False
    return True


def _digest(product, name, schema):
    return hashlib.sha256(_encoded({'product': product, 'tool': name, 'schema': schema})).hexdigest()


@functools.lru_cache(maxsize=1)
def _reviewed():
    """Load packaged pins once; a damaged registry exposes no output contracts."""
    try:
        data = json.loads(_DATA.read_text())
        if type(data['format']) is not int or data['format'] != 1 or type(data['entries']) is not list:
            return {}
        pins = {}
        for entry in data['entries']:
            product, name, schema = entry['product'], entry['tool'], entry['schema']
            if (type(product) is not str or type(name) is not str or (product, name) in pins
                    or not _safe_schema(schema) or len(_encoded(schema)) > _MAX_BYTES
                    or _digest(product, name, schema) != entry['binding_sha256']
                    or hashlib.sha256(_encoded(schema)).hexdigest() != entry['schema_sha256']):
                return {}
            pins[product, name] = schema
        return pins
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        return {}


def reviewed_output_schema(product, name, candidate):
    """Return a fresh audited schema only when the advertised contract matches.

    Product comes from local state, not child metadata. Returning the pinned
    copy also prevents a caller from mutating the packaged fallback contract.
    """
    if type(product) is not str or type(name) is not str or type(candidate) is not dict:
        return None
    pinned = _reviewed().get((product, name))
    if pinned is None:
        return None
    try:
        if not _safe_schema(candidate):
            return None
        encoded = _encoded(candidate)
        if len(encoded) <= _MAX_BYTES and encoded == _encoded(pinned):
            return copy.deepcopy(pinned)
    except (TypeError, ValueError, RecursionError, UnicodeError):
        pass
    return None
