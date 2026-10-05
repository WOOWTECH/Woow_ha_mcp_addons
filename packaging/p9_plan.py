"""P9 plan generator: reads and denials for one product, derived from docs/tool-surface.json.

    python packaging/p9_plan.py <product> [--overrides args.json] > plan.json

reads   supported-bounded tools (or operations) whose effect is read, with minimal arguments built from
        the accepted schema (for an operation: the oneOf/anyOf branch that admits it); a read whose required
        arguments cannot be built safely (free-form or patterned strings) is listed under needs_args unless
        --overrides supplies its arguments
denials supported write tools/operations (writes are off by default), read operations the accepted schema
        does not admit, withheld tools and one unknown tool; the gateway must refuse each with HTTP 403.
        Their arguments are schema-valid where possible but aim at records that cannot exist (largest
        allowed integer ids, placeholder names) so a broken guard harms nothing

Overrides map a tool name (or 'tool:operation') to an arguments object. The plan records the sha256 of
the tool-surface file it came from. Output is consumed by ha_p9_probe.py plan mode (ha_p9_driver.mjs --plan).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UNKNOWN_TOOL = 'definitely_not_a_tool'
PLACEHOLDER = 'p9-denied'


class NeedsArgs(Exception):
    pass


def value_for(schema, strict, root):
    """A minimal valid value for one property; strict=True refuses guesses that could be wrong."""
    ref = schema.get('$ref', '')
    if ref.startswith('#/$defs/'):
        schema = (root.get('$defs') or {}).get(ref[len('#/$defs/'):], {})
    if 'default' in schema:
        return schema['default']
    if schema.get('enum'):
        return schema['enum'][0]
    if 'const' in schema:
        return schema['const']
    options = schema.get('anyOf') or schema.get('oneOf')
    if options:
        return value_for(next((o for o in options if o.get('type') != 'null'), options[0]), strict, root)
    kind = schema.get('type')
    if kind == 'boolean':
        return False
    if kind in ('integer', 'number'):
        # Reads use the smallest valid value; denials aim at a record that cannot exist, so a broken
        # write guard still cannot touch real data.
        return max(1, schema.get('minimum', 1)) if strict else schema.get('maximum', 2147483647)
    if kind == 'array':
        count = schema.get('minItems', 0)
        if not count:
            return []
        items = schema.get('items') or {}
        if strict and not any(k in items for k in ('const', 'enum', 'default')):
            raise NeedsArgs()  # only fixed item values are safe guesses for a read
        try:
            options = items.get('enum') or [value_for(items, strict, root)]
        except NeedsArgs:
            return []  # denials only: refused regardless of item values
        return [options[i % len(options)] for i in range(count)]
    if kind == 'object' or (kind is None and 'properties' in schema):
        return arguments(schema, strict, root=root)
    if kind == 'string' and not strict:
        return PLACEHOLDER
    raise NeedsArgs()


def arguments(schema, strict, fixed=None, root=None):
    root = schema if root is None else root
    props = schema.get('properties') or {}
    result = dict(fixed or {})
    for name in schema.get('required', []):
        if name not in result:
            result[name] = value_for(props.get(name, {}), strict, root)
    return result


def admitted(values, operation):
    """None when the property schema says nothing about the operation, else whether it admits it."""
    if 'const' in values:
        return values['const'] == operation
    if values.get('enum'):
        return operation in values['enum']
    return None


def operation_schema(schema, selector, operation):
    """The accepted schema as it applies to one operation, or None if it does not admit the operation.

    A oneOf/anyOf branch that names the operation replaces the shared property schemas it redefines (a
    branch may forbid a shared default) and adds its required names.
    """
    shared = schema.get('properties') or {}
    if admitted(shared.get(selector, {}), operation) is False:
        return None
    options = schema.get('oneOf') or schema.get('anyOf')
    if not options:
        return schema
    for option in options:
        if admitted((option.get('properties') or {}).get(selector, {}), operation):
            merged = {k: v for k, v in schema.items() if k not in ('oneOf', 'anyOf')}
            merged['properties'] = {**shared, **(option.get('properties') or {})}
            required = list(schema.get('required', []))
            merged['required'] = required + [n for n in option.get('required', []) if n not in required]
            return merged
    return None


def denial_arguments(schema, fixed=None):
    """Writes must be refused whatever the arguments; fall back to the bare operation if none can be built."""
    try:
        return arguments(schema, False, fixed)
    except NeedsArgs:
        return dict(fixed or {})


def plan(product, surface, overrides=None):
    overrides = overrides or {}
    tools = surface['products'][product]['tools']
    reads, denials, needs = [], [], []

    def read(key, name, schema, fixed=None):
        if key in overrides:
            reads.append([name, overrides[key]])
            return
        try:
            reads.append([name, arguments(schema, True, fixed)])
        except NeedsArgs:
            needs.append(key)

    for tool in tools:
        name, schema = tool['name'], tool.get('accepted_schema') or {}
        if tool['status'] != 'supported-bounded':
            denials.append([name, {}])  # withheld: refused whatever the arguments
            continue
        selector = tool.get('operation_parameter')
        if not selector and tool['effect'] == 'mixed' and len(tool.get('operation_effects') or {}) == 1:
            selector = next(iter(tool['operation_effects']))  # mixed tool whose selector is not declared
        effects = (tool.get('operation_effects') or {}).get(selector) if selector else None
        if effects:
            for operation, effect in effects.items():
                key = '%s:%s' % (name, operation)
                scoped = operation_schema(schema, selector, operation)
                if scoped is None:  # outside the accepted surface: refused whatever its effect
                    denials.append([name, overrides.get(key, {selector: operation})])
                elif effect == 'read':
                    read(key, name, scoped, {selector: operation})
                else:
                    denials.append([name, overrides.get(key, denial_arguments(scoped, {selector: operation}))])
        elif tool['effect'] == 'read':
            read(name, name, schema)
        else:
            denials.append([name, overrides.get(name, denial_arguments(schema))])
    denials.append([UNKNOWN_TOOL, {}])
    return {'product': product, 'reads': reads, 'denials': denials, 'needs_args': needs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('product')
    parser.add_argument('--surface', type=Path, default=ROOT / 'docs/tool-surface.json')
    parser.add_argument('--overrides', type=Path)
    opts = parser.parse_args(argv)
    raw = opts.surface.read_bytes()
    surface = json.loads(raw)
    if opts.product not in surface['products']:
        parser.error('unknown product %s' % opts.product)
    overrides = json.loads(opts.overrides.read_text()) if opts.overrides else {}
    result = plan(opts.product, surface, overrides)
    result['tool_surface_sha256'] = hashlib.sha256(raw).hexdigest()
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write('\n')
    return result


if __name__ == '__main__':
    main()
