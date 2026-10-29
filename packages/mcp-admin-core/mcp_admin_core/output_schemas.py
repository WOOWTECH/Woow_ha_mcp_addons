"""Reviewed public output contracts, never a general child-schema relay.

Only exact (product, tool, schema) pins are exposed. The small JSON Schema
vocabulary below needs no resolver, regex compiler or format plug-in. In
particular *all* refs (even local ones) remain unsupported until reviewed.
Neither schema absence nor a mismatch is repaired using another tool's pin.
"""
import copy
import functools
import hashlib
import json
from pathlib import Path

_DATA = Path(__file__).with_name('output_schemas.json')
_TYPES = frozenset({'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'})
_KEYWORDS = frozenset({'type', 'properties', 'required', 'items', 'additionalProperties', 'anyOf', 'enum', 'const'})
_MAX_BYTES = 32768


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _safe_schema(schema):
    """The exact finite vocabulary used by the audited object/TypedDict outputs.

    No refs, regexes, arbitrary annotations, extension keywords or recursive
    schemas. Bounds also keep malformed in-process metadata from breaking list.
    """
    if type(schema) is not dict or schema.get('type') != 'object':
        return False
    todo = [(schema, 0)]
    count = 0
    while todo:
        node, depth = todo.pop()
        count += 1
        if count > 1024 or depth > 16 or type(node) is not dict or set(node) - _KEYWORDS:
            return False
        kind = node.get('type')
        if kind is not None and (type(kind) is not str or kind not in _TYPES):
            return False
        if not node or kind is None and set(node) != {'anyOf'}:
            return False
        if 'properties' in node:
            props = node['properties']
            if kind != 'object' or type(props) is not dict or len(props) > 128:
                return False
            if any(type(k) is not str or not k or len(k) > 128 for k in props):
                return False
            todo.extend((v, depth + 1) for v in props.values())
        if 'required' in node:
            required = node['required']
            if (kind != 'object' or type(required) is not list
                    or any(type(k) is not str for k in required)
                    or len(required) != len(set(required))
                    or not set(required) <= set(node.get('properties', {}))):
                return False
        if 'additionalProperties' in node and (kind != 'object' or type(node['additionalProperties']) is not bool):
            return False
        if 'items' in node:
            if kind != 'array':
                return False
            todo.append((node['items'], depth + 1))
        if kind == 'array' and 'items' not in node:
            return False
        if 'anyOf' in node:
            branches = node['anyOf']
            if type(branches) is not list or not 1 < len(branches) <= 8:
                return False
            todo.extend((v, depth + 1) for v in branches)
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
        if data['format'] != 1 or type(data['entries']) is not list:
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
