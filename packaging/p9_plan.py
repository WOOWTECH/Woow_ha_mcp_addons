"""P9 plan generator: reads and denials for one product, derived from docs/tool-surface.json.

    python packaging/p9_plan.py <product> [--overrides args.json] > plan.json

A supported tool is supported-bounded (Odoo Manage: the gateway validates its accepted_schema) or supported-full (0.2.0
on: accepted_schema is null, the gateway forwards the arguments and the child validates its own inputSchema, which is
read from the packaged tools/list snapshot, mcp_admin_core/tool_snapshot.py, parsed, not imported).

reads   supported tools (or operations) whose effect is read, with minimal arguments: for a bounded tool built from the
        accepted schema (for an operation: the oneOf/anyOf branch that admits it); for a full tool only a value its
        inputSchema declares (default, an enum's first value, const) fills a required argument. A read whose required
        arguments cannot be built safely (free-form or patterned strings; for a full tool any value its schema does not
        declare, or no inputSchema in the snapshot), or whose child requires an argument only its description states
        (DESCRIBED_REQUIRED), is listed under needs_args unless --overrides supplies its arguments
denials supported write tools/operations (the add-on under test must have every write turned off in its panel: a
        NEW state has them all on since 2026-10-15), every operation of a tool whose write grant is the whole tool (an
        effect other than read or mixed: the gateway refuses the tool, its read operations too), read operations the
        accepted schema does not admit, withheld tools and one unknown tool; the gateway must refuse each (HTTP 403, or
        from 0.1.14 inside a session HTTP 200 with its own JSON-RPC -32602/-32603 error; ha_p9_probe.gateway_refused).
        A bounded tool's arguments are schema-valid where possible but aim at records that cannot exist (largest allowed
        integer ids, placeholder names) so a broken guard harms nothing; a full tool's denial carries only its operation:
        the gateway checks the write grant before the child sees any argument (mcp_admin_core.policy.authorize). A
        broken guard then reaches a child that refuses a call missing its required arguments, but a call whose schema
        requires nothing more (hermes_gateway restart, n8n_audit_instance, litellm_health) runs as sent: compare the
        backend before and after either way

Overrides map a tool name (or 'tool:operation') to an arguments object. The plan records the sha256 of the tool-surface
file and of the snapshot it came from; generate it at the commit of the add-on version under test (both follow the
version). Output is consumed by ha_p9_probe.py plan mode (ha_p9_driver.mjs --plan).
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py'
UNKNOWN_TOOL = 'definitely_not_a_tool'
PLACEHOLDER = 'p9-denied'
SUPPORTED = ('supported-bounded', 'supported-full')
# Reads whose child requires an argument that only its description states: n8n-mcp writes no if/then or
# dependentRequired into an inputSchema, so no schema rule here sees these. Sent with the operation alone, each was
# refused on HAOS 2026-11-18 (docs/provenance/ha-multiprofile-HM-16-p9plan-20261119.md). Reviewed against the property
# descriptions in the packaged snapshot; packaging/test_p9_plan.py pins those inputSchemas, so a new n8n-mcp version is
# reviewed here again. Each names the arguments its description requires.
DESCRIBED_REQUIRED = {'n8n': {
    'n8n_manage_credentials:get': ('id',),
    'n8n_manage_credentials:getSchema': ('type',),
    'n8n_manage_datatable:getTable': ('tableId',),
    'n8n_manage_datatable:getRows': ('tableId',),
    'n8n_manage_folders:get': ('folderId',),
    'n8n_workflow_versions:list': ('workflowId',),
    'n8n_workflow_versions:get': ('versionId',),
    'n8n_workflow_versions:diff': ('workflowId', 'versionId'),
    'search_templates': ('query',),  # its default searchMode, keyword
}}


class NeedsArgs(Exception):
    pass


def value_for(schema, strict, root, declared=False):
    """A minimal valid value for one property; strict=True refuses guesses that could be wrong; declared=True (a full
    tool's read) takes only a value the schema itself declares."""
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
        return value_for(next((o for o in options if o.get('type') != 'null'), options[0]), strict, root, declared)
    if declared:
        raise NeedsArgs()  # the child's schema bounds nothing else: no id, name, number or list is a safe guess
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


def arguments(schema, strict, fixed=None, root=None, declared=False):
    root = schema if root is None else root
    props = schema.get('properties') or {}
    result = dict(fixed or {})
    for name in schema.get('required', []):
        if name not in result:
            result[name] = value_for(props.get(name, {}), strict, root, declared)
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


def snapshot_schemas(raw, product):
    """{tool name: inputSchema} of the product in the packaged tools/list snapshot (its LISTED), parsed, not imported."""
    found = [node.value for node in ast.parse(raw).body if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'LISTED']
    if len(found) != 1:
        raise SystemExit('the snapshot has no single LISTED assignment')
    return {tool['name']: tool['inputSchema'] for tool in ast.literal_eval(found[0]).get(product, [])}


def plan(product, surface, overrides=None, input_schemas=None):
    """input_schemas: {tool name: inputSchema} of the product's full tools (snapshot_schemas); a full tool without one
    gets no guessed read."""
    overrides = overrides or {}
    input_schemas = input_schemas or {}
    described = DESCRIBED_REQUIRED.get(product, {})
    tools = surface['products'][product]['tools']
    reads, denials, needs = [], [], []

    def read(key, name, schema, fixed=None, declared=False):
        if key in overrides:
            reads.append([name, overrides[key]])
            return
        try:
            if schema is None or key in described:
                raise NeedsArgs()  # a full tool's inputSchema (or operation branch) is not known; DESCRIBED_REQUIRED
            reads.append([name, arguments(schema, True, fixed, declared=declared)])
        except NeedsArgs:
            needs.append(key)

    for tool in tools:
        name = tool['name']
        if tool['status'] not in SUPPORTED:
            denials.append([name, {}])  # withheld: refused whatever the arguments
            continue
        full = tool['status'] == 'supported-full'
        # A full tool's arguments are not checked before its grant: nothing is outside an accepted schema.
        schema = {} if full else tool.get('accepted_schema') or {}
        child = input_schemas.get(name) if full else None
        # The grant of a write (or unverified) tool is the tool itself (policy.Tool.grants): with every write off the
        # gateway refuses each of its calls, read operations included.
        whole_write = tool['effect'] not in ('read', 'mixed')
        selector = tool.get('operation_parameter')
        if not selector and tool['effect'] == 'mixed' and len(tool.get('operation_effects') or {}) == 1:
            selector = next(iter(tool['operation_effects']))  # mixed tool whose selector is not declared
        effects = (tool.get('operation_effects') or {}).get(selector) if selector else None
        if effects:
            for operation, effect in effects.items():
                key = '%s:%s' % (name, operation)
                fixed = {selector: operation}
                scoped = operation_schema(schema, selector, operation)
                if scoped is None:  # outside the accepted surface: refused whatever its effect
                    denials.append([name, overrides.get(key, fixed)])
                elif effect == 'read' and not whole_write:
                    if full:
                        branch = None if child is None else operation_schema(child, selector, operation)
                        read(key, name, branch, fixed, declared=True)
                    else:
                        read(key, name, scoped, fixed)
                else:
                    denials.append([name, overrides.get(key, denial_arguments(scoped, fixed))])
        elif tool['effect'] == 'read':
            read(name, name, child if full else schema, declared=full)
        else:
            denials.append([name, overrides.get(name, denial_arguments(schema))])
    denials.append([UNKNOWN_TOOL, {}])
    return {'product': product, 'reads': reads, 'denials': denials, 'needs_args': needs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('product')
    parser.add_argument('--surface', type=Path, default=ROOT / 'docs/tool-surface.json')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT, help='the tools/list snapshot (full tools inputSchema)')
    parser.add_argument('--overrides', type=Path)
    opts = parser.parse_args(argv)
    raw = opts.surface.read_bytes()
    surface = json.loads(raw)
    if opts.product not in surface['products']:
        parser.error('unknown product %s' % opts.product)
    overrides = json.loads(opts.overrides.read_text()) if opts.overrides else {}
    snapshot = opts.snapshot.read_bytes()
    result = plan(opts.product, surface, overrides, snapshot_schemas(snapshot, opts.product))
    result['tool_surface_sha256'] = hashlib.sha256(raw).hexdigest()
    result['tool_snapshot_sha256'] = hashlib.sha256(snapshot).hexdigest()
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write('\n')
    return result


if __name__ == '__main__':
    main()
