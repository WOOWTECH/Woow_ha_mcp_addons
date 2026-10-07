"""0.1.6 (AI Stage 0, owner decision D21): the inputSchema a tools/list declares is provider-safe.

Claude and GPT refused a WHOLE request (HTTP 400) when any tool's input schema had oneOf/anyOf/allOf (GPT also enum,
const, not) at its top level, so a client that forwards the gateway's list unchanged could not use n8n, Odoo or Hermes.
The declared form is a superset of what the pinned model accepts (its branch rules move into the description); the
gateway still validates every call with the original strict model.
"""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import subprocess
from typing import Annotated, Literal

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mcp_admin_core.expansion import N8N_GRANTS
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import RULES_PREFIX, Denied, authorize, declared_schema, enabled, filter_list, flat_schema
from mcp_admin_core.products import ProductState, ProductStore, TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_batch2_bounds import BAD as NESTED_BYPASSES
from test_expansion_policy import call
from test_expansion_runtime import READS, WRITES
from test_real_products import connection

ROOT = Path(__file__).resolve().parents[1]
# The provider refusals, written out here rather than imported: a keyword dropped from the gateway's list must fail.
REFUSED = {'oneOf', 'anyOf', 'allOf', 'enum', 'const', 'not', 'if', 'then', 'else'}
# Written out as well (review F2): the CHANGELOGs and docs/n8n-tracer-contract.md quote this text.
PREFIX = 'Argument rules (checked by the server): '
PRODUCTS = ('n8n', *TOOLS)
SEVEN = {'n8n_manage_folders': 'n8n', 'diagnose_odoo_call': 'odoo', 'generate_json2_payload': 'odoo',
         'hermes_skill': 'hermes', 'hermes_tools': 'hermes', 'hermes_session': 'hermes', 'hermes_cron': 'hermes'}
PREVIEW_RULE = 'if method="search_count": omit kwargs.fields, kwargs.limit and kwargs.offset'
RULES = {
    'n8n_manage_folders': 'action="list": omit folderId and name; action="create": requires name, omit folderId; '
                          'action="rename": requires folderId and name; action="get": requires projectId and folderId, '
                          'omit name, projectId must not be "personal"',
    'diagnose_odoo_call': PREVIEW_RULE, 'generate_json2_payload': PREVIEW_RULE,
    'hermes_skill': 'action="list": omit name; action="enable": requires name; action="disable": requires name',
    'hermes_tools': 'action="list" (or omitted): omit toolset; action="enable": requires toolset; '
                    'action="disable": requires toolset',
    'hermes_session': 'action="list" (or omitted): omit session_id; action="delete": requires session_id',
    'hermes_cron': 'action="list" (or omitted): omit job_id; action="delete": requires job_id; '
                   'action="pause": requires job_id',
}
# Each branch the original schema distinguished: (member, value when omitted, values). Every one must be exercised.
BRANCHES = {'n8n_manage_folders': ('action', None, {'list', 'create', 'rename', 'get'}),
            'diagnose_odoo_call': ('method', None, {'search_read', 'search_count'}),
            'generate_json2_payload': ('method', None, {'search_read', 'search_count'}),
            'hermes_skill': ('action', None, {'list', 'enable', 'disable'}),
            'hermes_tools': ('action', 'list', {'list', 'enable', 'disable'}),
            'hermes_session': ('action', 'list', {'list', 'delete'}),
            'hermes_cron': ('action', 'list', {'list', 'delete', 'pause'})}

# Argument objects of the e2e plans for these tools (Woow_ha_mcp_addons-e2e packaging/e2e/plans/{n8n,odoo,hermes}.json,
# 2026-10-07), deduplicated, accepted and refused alike: {"$var": NAME} became WOOW-MCP-TEST-name and ${RUN_PREFIX}
# WOOW-MCP-TEST-B0-, as a run substitutes them. The pinned model decides which are valid.
PLAN_ARGUMENTS = {
    'n8n_manage_folders': [
        {'action': 'list'}, {'action': 'create', 'name': 'WOOW-MCP-TEST-p9-denied'},
        {'action': 'rename', 'folderId': 'WOOW-MCP-TEST-p9-denied', 'name': 'WOOW-MCP-TEST-p9-denied'},
        {'action': 'move'}, {'action': 'delete'}, {'action': 'list', 'projectId': 'a' * 128},
        {'action': 'list', 'projectId': 'a' * 129}, {'action': 'list', 'projectId': ''},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-owner-project-id', 'folderId': 'WOOW-MCP-TEST-folder-nx'},
        {'action': 'list', 'projectId': 'WOOW-MCP-TEST-owner-project-id'},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-owner-project-id',
         'folderId': 'WOOW-MCP-TEST-folder-nx' + 'a' * 105},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-owner-project-id',
         'folderId': 'WOOW-MCP-TEST-folder-nx' + 'a' * 106},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-owner-project-id', 'folderId': ''},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-proj-nx', 'folderId': 'WOOW-MCP-TEST-folder-nx'},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-folder-01'},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-folder-' + 'x' * 211}, {'action': 'create', 'name': ''},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-folder-rv'},
        {'action': 'rename', 'folderId': 'WOOW-MCP-TEST-folder-nx', 'name': 'WOOW-MCP-TEST-B0-folder-r'},
        {'action': 'rename', 'folderId': 'WOOW-MCP-TEST-folder-nx', 'name': 'WOOW-MCP-TEST-B0-folder-rv'},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-folder-' + 'x' * 212},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-folder-dp'},
        {'action': 'rename', 'folderId': 'WOOW-MCP-TEST-folder-nx', 'name': 'WOOW-MCP-TEST-B0-folder-dp'},
        {'action': 'get', 'projectId': 'WOOW-MCP-TEST-b19-project-id', 'folderId': 'WOOW-MCP-TEST-folder-seed-id'},
    ],
    'diagnose_odoo_call': [
        {'model': 'res.partner', 'method': 'search_read'}, {'model': 'res.partner', 'method': 'search_count'},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'auto'},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'xmlrpc'},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'jsonrpc'},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'json2'},
        {'model': 'res.partner', 'method': 'search_read', 'target_version': '18'},
        {'model': 'res.partner', 'method': 'search_read', 'target_version': '19'},
        {'model': 'res.partner', 'method': 'search_read', 'target_version': '20'},
        {'model': 'res.partner', 'method': 'search_read', 'include_debug': False},
        {'model': 'res.partner', 'method': 'search_read', 'use_live_metadata': False},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'xmlrpc', 'target_version': '19',
         'kwargs': {'domain': [['active', '=', True]], 'fields': ['id', 'name'], 'limit': 10}},
        {'model': 'res.partner', 'method': 'search_read',
         'kwargs': {'domain': [['active', '=', True]], 'fields': ['id', 'name'], 'limit': 10}},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'json2',
         'kwargs': {'domain': [['active', '=', True]], 'fields': ['id', 'name'], 'limit': 10}},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'xmlrpc', 'target_version': '18',
         'kwargs': {'domain': [['active', '=', True]], 'fields': ['id', 'name'], 'limit': 10}},
        {'model': 'res.partner', 'method': 'search_read', 'transport': 'xmlrpc', 'target_version': '20',
         'kwargs': {'domain': [['active', '=', True]], 'fields': ['id', 'name'], 'limit': 10}},
        {'model': 'res.partner', 'method': 'search_count',
         'kwargs': {'domain': [['name', 'ilike', 'WOOW-MCP-TEST-B0-']]}},
    ],
    'generate_json2_payload': [
        {'model': 'res.partner', 'method': 'search_read'}, {'model': 'res.partner', 'method': 'search_count'},
        {'model': 'res.partner', 'method': 'search_read',
         'kwargs': {'domain': [['name', 'ilike', 'WOOW-MCP-TEST-B0-']], 'fields': ['id', 'name'], 'limit': 5}},
        {'model': 'res.partner', 'method': 'search_count',
         'kwargs': {'domain': [['name', 'ilike', 'WOOW-MCP-TEST-B0-']]}},
        {'model': 'res.partner', 'method': 'search_read', 'include_database_header': False,
         'kwargs': {'domain': [['name', 'ilike', 'WOOW-MCP-TEST-B0-']], 'fields': ['id', 'name'], 'limit': 5}},
    ],
    'hermes_skill': [
        {'action': 'list'}, {'action': 'disable', 'name': 'WOOW-MCP-TEST-p9-denied'},
        {'action': 'enable', 'name': 'WOOW-MCP-TEST-p9-denied'}, {'action': 'disable', 'name': 'a' * 129},
        {'action': 'enable', 'name': ''}, {'action': 'disable', 'name': 'WOOW-MCP-TEST-skill-name'},
        {'action': 'enable', 'name': 'WOOW-MCP-TEST-skill-name'},
        {'action': 'disable', 'name': 'WOOW-MCP-TEST-sch' + 'a' * 112}, {'action': 'disable', 'name': ''},
        {'action': 'disable', 'name': 'WOOW-MCP-TEST-missing'},
        {'action': 'enable', 'name': 'WOOW-MCP-TEST-' + 'a' * 114},
        {'action': 'enable', 'name': 'WOOW-MCP-TEST-missing'},
    ],
    'hermes_tools': [
        {'action': 'list'}, {'action': 'disable', 'toolset': 'WOOW-MCP-TEST-p9-denied'},
        {'action': 'enable', 'toolset': 'WOOW-MCP-TEST-p9-denied'}, {'action': 'disable', 'toolset': 'a' * 129},
        {'action': 'enable', 'toolset': ''}, {'action': 'enable', 'toolset': 'WOOW-MCP-TEST-toolset'},
        {'action': 'disable', 'toolset': 'WOOW-MCP-TEST-toolset-t'},
        {'action': 'disable', 'toolset': 'WOOW-MCP-TEST-toolset'},
        {'action': 'enable', 'toolset': 'WOOW-MCP-TEST-toolset-t'},
        {'action': 'disable', 'toolset': 'WOOW-MCP-TEST-' + 'a' * 114},
        {'action': 'disable', 'toolset': 'WOOW-MCP-TEST-toolset' + 'a' * 108}, {'action': 'disable', 'toolset': ''},
    ],
    'hermes_session': [
        {'action': 'list'}, {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-p9-denied'}, {'action': 'get'},
        {'action': 'delete', 'session_id': 'a' * 129}, {'action': 'delete', 'session_id': ''},
        {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-missing'},
        {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-session-seed-id'},
        {'action': 'get', 'session_id': 'WOOW-MCP-TEST-missing'},
        {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-B0-nx-session'},
        {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-' + 'a' * 114},
        {'action': 'delete', 'session_id': 'WOOW-MCP-TEST-missing' + 'a' * 108},
    ],
    'hermes_cron': [
        {'action': 'list'}, {'action': 'create'}, {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-p9-denied'},
        {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-p9-denied'}, {'action': 'resume'}, {'action': 'trigger'},
        {'action': 'update'}, {'action': 'list', 'enabled': True},
        {'action': 'create', 'name': 'WOOW-MCP-TEST-B0-x', 'schedule': '0 0 1 1 *', 'prompt': 'x'},
        {'action': 'update', 'job_id': 'WOOW-MCP-TEST-cron-denied-id', 'name': 'y'},
        {'action': 'resume', 'job_id': 'WOOW-MCP-TEST-cron-denied-id'},
        {'action': 'trigger', 'job_id': 'WOOW-MCP-TEST-cron-denied-id'}, {'action': 'pause', 'job_id': 'a' * 129},
        {'action': 'delete', 'job_id': ''}, {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-cron-denied-id'},
        {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-cron-denied-id'},
        {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-cron-verify-id'},
        {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-cron-pause-id'},
        {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-cron-pause-id'},
        {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-sch' + 'a' * 112}, {'action': 'pause', 'job_id': ''},
        {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-cron-delete-id'},
        {'action': 'pause', 'job_id': 'WOOW-MCP-TEST-missing'},
        {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-missing'},
        {'action': 'delete', 'job_id': 'WOOW-MCP-TEST-' + 'a' * 114},
    ],
}

# Generated per branch: every combination of these member values (ABSENT leaves the member out). The pinned model
# decides which are valid; together they cover each branch, explicit nulls, defaults and every cross-branch mix.
ABSENT = object()
KWARGS = [ABSENT, {}, {'domain': []}, {'domain': [['name', 'ilike', 'x']]}, {'fields': ['id']}, {'limit': 5},
          {'offset': 0}, {'fields': None}, {'limit': None}, {'offset': None},
          {'domain': [['id', '=', 1]], 'fields': ['id', 'name'], 'limit': 10, 'offset': 1}]
PREVIEW = {'model': [ABSENT, 'res.partner'], 'method': [ABSENT, 'search_read', 'search_count'], 'kwargs': KWARGS}
POOLS = {
    'n8n_manage_folders': {'action': [ABSENT, 'list', 'create', 'rename', 'get', 'move'],
                           'projectId': [ABSENT, 'personal', 'proj-1', None], 'folderId': [ABSENT, None, 'folder-1'],
                           'name': [ABSENT, None, 'Folder 1']},
    'diagnose_odoo_call': {**PREVIEW, 'transport': [ABSENT, 'json2'], 'target_version': [ABSENT, '19', None]},
    'generate_json2_payload': {**PREVIEW, 'include_database_header': [ABSENT, False], 'base_url': [ABSENT, None]},
    'hermes_skill': {'action': [ABSENT, 'list', 'enable', 'disable', 'create'], 'name': [ABSENT, None, 'skill-1']},
    'hermes_tools': {'action': [ABSENT, 'list', 'enable', 'disable'], 'toolset': [ABSENT, None, 'toolset-1']},
    'hermes_session': {'action': [ABSENT, 'list', 'delete', 'get'], 'session_id': [ABSENT, None, 'session-1']},
    'hermes_cron': {'action': [ABSENT, 'list', 'delete', 'pause'], 'job_id': [ABSENT, None, 'job-1'],
                    'enabled': [ABSENT, True, False], 'name': [ABSENT, None]},
}


def tools_of(product):
    return N8N_TOOLS if product == 'n8n' else TOOLS[product]


def model(name):
    return tools_of(SEVEN[name])[name].arguments


def accepted(name, args):
    try:
        model(name).model_validate(deepcopy(args))
    except ValidationError:
        return False
    return True


def unique(values):
    return list({json.dumps(value, sort_keys=True): value for value in values}.values())


def pool(name):
    members = POOLS[name]
    for values in itertools.product(*members.values()):
        yield {member: value for member, value in zip(members, values) if value is not ABSENT}


def provider_safe(schema):
    return (isinstance(schema, dict) and schema.get('type') == 'object' and isinstance(schema.get('properties'), dict)
            and not REFUSED & schema.keys() and '$ref' not in schema)


def validate(groups):
    """[(schema, [instance, ...]), ...] -> [[valid, ...], ...] with the pinned child's jsonschema (Draft 2020-12), in
    one process; every schema must itself be a valid Draft 2020-12 schema."""
    probe = subprocess.run([str(ROOT / 'apps/odoo/.venv/bin/python'), '-c', '''
import json, sys
from jsonschema import Draft202012Validator
out = []
for schema, instances in json.load(sys.stdin):
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    out.append([validator.is_valid(instance) for instance in instances])
print(json.dumps(out))
'''], input=json.dumps(groups), text=True, capture_output=True, timeout=60,
        env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert probe.returncode == 0, probe.stderr
    return json.loads(probe.stdout)


def full_state(product, **changes):
    """Every write grant of the product and a configured backend: a refusal is then the arguments', not the policy's."""
    tools = tools_of(product)
    grants = N8N_GRANTS if product == 'n8n' else {g for name, tool in tools.items() for g in tool.grants(name)}
    if product == 'n8n':
        extra = {'backend_url': 'http://backend.invalid', 'backend_key': 'DUMMY_DECLARED_KEY'}
    else:
        extra = {'connection': {**connection(product, 'http://127.0.0.1:9'),
                                **({'mode': 'module'} if product == 'odoo-manage' else {})}}
    return ProductState(product=product, token='a' * 43, child_token='b' * 43, writes_enabled=True,
                        enabled_write_tools=sorted(grants), **extra, **changes)


def full_store(directory, product):
    """A product store holding full_state(product)."""
    store, state = ProductStore(directory, product), full_state(product)
    store.update(backend_url=state.backend_url, backend_key=state.backend_key, writes_enabled=True,
                 enabled_write_tools=state.enabled_write_tools,
                 connection=state.connection.model_dump() if state.connection else None)
    return store


def default_state(product):
    return ProductState(product=product, token='a' * 43, child_token='b' * 43)


@pytest.mark.parametrize('product', PRODUCTS)
@pytest.mark.parametrize('writes', [False, True], ids=['default', 'all-writes'])
def test_every_listed_schema_is_provider_safe(product, writes):
    # (a) Through the publication path, from a child whose own schemas are the refused shape.
    tools = tools_of(product)
    state = full_state(product) if writes else default_state(product)
    child = [{'name': name, 'inputSchema': {'type': 'object', 'oneOf': [{'required': ['x']}]}} for name in tools]
    listed = filter_list({'result': {'tools': child}}, tools, state)['result']['tools']
    assert [tool['name'] for tool in listed] == [name for name in tools if enabled(name, tools, state)]
    if writes:
        assert len(listed) == len(tools)  # every tool of every product is checked
    for tool in listed:
        schema = tool['inputSchema']
        assert provider_safe(schema), (product, tool['name'], sorted(schema))
        assert schema == declared_schema(tools[tool['name']].arguments)
        original = tools[tool['name']].arguments.model_json_schema()
        if tool['name'] in SEVEN:
            assert schema != original and not provider_safe(original)
        else:
            assert schema == original  # unchanged where the top level was already safe


@pytest.mark.parametrize('name', SEVEN)
def test_declared_form_of_the_seven_tools(name):
    # Only the top-level combinator goes; title, properties, defaults, required, additionalProperties and $defs stay,
    # and the branch rules become plain clauses in the description.
    assert RULES_PREFIX == PREFIX
    original = model(name).model_json_schema()
    assert REFUSED & original.keys()
    expected = {key: value for key, value in original.items() if key not in REFUSED}
    assert declared_schema(model(name)) == {**expected, 'description': PREFIX + RULES[name] + '.'}
    assert declared_schema(model(name))['additionalProperties'] is False
    assert model(name).model_json_schema() == original  # the model's own schema (the validated contract) is untouched


def reordered(schema):
    """The schema as another process may build it: in its top-level combinators, every object's members and every
    required list in reverse order (n8n_b3.folder_schema builds each branch's members from a set, whose order changes
    per process). The branches keep their order: the declared form follows the generator's branch order (review F5)."""
    def reverse(value):
        if isinstance(value, list):
            return [reverse(item) for item in value]
        if not isinstance(value, dict):
            return value
        return dict(reversed([(key, item[::-1] if key == 'required' and isinstance(item, list) else reverse(item))
                              for key, item in value.items()]))
    return {key: reverse(value) if key in REFUSED else value for key, value in schema.items()}


@pytest.mark.parametrize('name', SEVEN)
def test_declared_form_does_not_follow_member_order_in_branches(name):
    original = model(name).model_json_schema()
    other = reordered(original)
    assert json.dumps(other) != json.dumps(original)  # the same schema in another member order
    assert json.dumps(flat_schema(other)) == json.dumps(flat_schema(original))  # byte for byte, description included


@pytest.fixture(scope='module')
def verdicts():
    """For each of the seven tools: the valid (raw and normalized) and refused examples, and how the declared and the
    original schema judge them, from one jsonschema process."""
    extra = {name: [args for product in READS for tool, args in READS[product] + WRITES[product] if tool == name]
             for name in SEVEN}
    rows, groups = {}, []
    for name in SEVEN:
        examples = unique(PLAN_ARGUMENTS[name] + extra[name] + list(pool(name)))
        valid = [args for args in examples if accepted(name, args)]
        refused = [args for args in examples if not accepted(name, args)]
        normalized = unique(model(name).model_validate(deepcopy(args)).model_dump(mode='json') for args in valid)
        rows[name] = {'valid': valid + normalized, 'refused': refused, 'plan_valid': [
            args for args in PLAN_ARGUMENTS[name] if accepted(name, args)]}
        groups += [(declared_schema(model(name)), rows[name]['valid'] + refused),
                   (model(name).model_json_schema(), rows[name]['valid'] + refused)]
    results = iter(validate(groups))
    for name, row in rows.items():
        declared, original = next(results), next(results)
        count = len(row['valid'])
        row.update(declared_valid=declared[:count], declared_refused=declared[count:],
                   original_valid=original[:count], original_refused=original[count:])
    return rows


@pytest.mark.parametrize('name', SEVEN)
def test_declared_schema_accepts_everything_the_model_accepts(name, verdicts):
    # (b) SUPERSET over plan cases, the reviewed examples, every generated combination and their normalized forms.
    row = verdicts[name]
    assert row['plan_valid'] and len(row['valid']) >= 10
    member, omitted, values = BRANCHES[name]
    assert {args.get(member, omitted) for args in row['valid']} == values  # every branch is exercised
    missed = [args for args, ok in zip(row['valid'], row['declared_valid']) if not ok]
    assert missed == []
    # The original schema agrees with the model on all of them (it described the branches exactly).
    assert all(row['original_valid'])


@pytest.mark.parametrize('name', SEVEN)
def test_gateway_still_refuses_what_only_the_branch_rules_forbid(name, verdicts):
    # (c) The declared schema accepts these, the original schema and the model do not, and authorize() denies them
    # without touching the request, even with every grant and a configured backend.
    row = verdicts[name]
    loose = [args for args, ok in zip(row['refused'], row['declared_refused']) if ok]
    assert loose, name  # the declared form really is looser: these exist and must be caught
    assert not any(ok for args, ok in zip(row['refused'], row['original_refused']) if args in loose)
    state = full_state(SEVEN[name])
    for args in loose:
        message = call(name, deepcopy(args))
        before = deepcopy(message)
        with pytest.raises(Denied, match='invalid tool arguments'):
            authorize(message, tools_of(SEVEN[name]), state)
        assert message == before, args
    # Every schema-level refusal (bounds, enums, unknown members) is still declared: only branch rules were moved.
    tight = [args for args, ok in zip(row['refused'], row['declared_refused']) if not ok]
    assert tight


# Branch-only refusals named one by one, through the gateway: 403 and the child is never called.
BRANCH_INVALID = [
    ('n8n_manage_folders', {'action': 'list', 'name': 'x'}), ('n8n_manage_folders', {'action': 'create'}),
    ('n8n_manage_folders', {'action': 'rename', 'name': 'x'}),
    ('n8n_manage_folders', {'action': 'get', 'folderId': 'f'}),
    ('n8n_manage_folders', {'action': 'get', 'folderId': 'f', 'projectId': 'personal'}),
    ('n8n_manage_folders', {'action': 'create', 'name': 'x', 'folderId': 'f'}),
    ('generate_json2_payload', {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'limit': 10}}),
    ('generate_json2_payload', {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'fields': None}}),
    ('diagnose_odoo_call', {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'offset': 0}}),
    ('diagnose_odoo_call', {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'fields': ['id']}}),
    ('hermes_skill', {'action': 'list', 'name': 'x'}), ('hermes_skill', {'action': 'enable'}),
    ('hermes_tools', {'action': 'disable'}), ('hermes_tools', {'toolset': 'x'}),
    ('hermes_session', {'action': 'delete'}), ('hermes_session', {'session_id': 'x'}),
    ('hermes_cron', {'action': 'pause'}), ('hermes_cron', {'job_id': 'x'}),
]
BRANCH_VALID = {'n8n': ('n8n_manage_folders', {'action': 'list'}),
                'odoo': ('generate_json2_payload', {'model': 'res.partner', 'method': 'search_count'}),
                'hermes': ('hermes_cron', {})}


async def test_branch_invalid_calls_never_reach_the_child(tmp_path):
    results = validate([(declared_schema(model(name)), [args]) for name, args in BRANCH_INVALID]
                       + [(model(name).model_json_schema(), [args]) for name, args in BRANCH_INVALID])
    assert results[:len(BRANCH_INVALID)] == [[True]] * len(BRANCH_INVALID)  # the declared form lets them through
    assert results[len(BRANCH_INVALID):] == [[False]] * len(BRANCH_INVALID)  # the original schema did not
    for product in ('n8n', 'odoo', 'hermes'):
        (tmp_path / product).mkdir()
        store = full_store(tmp_path / product, product)
        try:
            calls = []

            def upstream(request):
                calls.append(request)
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {}})
            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
                _, app = make_apps(store, tools_of(product), child)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, 'Mcp-Session-Id': 'existing'}
                    for name, args in BRANCH_INVALID:
                        if SEVEN[name] == product:
                            response = await client.post('/mcp', headers=headers, json=call(name, args))
                            assert response.status_code == 403 and response.json() == {'error': 'request denied'}, args
                    # A branch-valid call still goes through: the refusals above are the arguments', not the policy's.
                    name, args = BRANCH_VALID[product]
                    assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 200
            assert len(calls) == 1
        finally:
            store.close()


@pytest.mark.parametrize('product', ['n8n', 'odoo', 'hermes'])
@pytest.mark.parametrize('sse', [False, True], ids=['json', 'sse'])
async def test_tools_list_through_the_gateway_declares_the_flat_schemas(tmp_path, product, sse):
    # (d) The JSON and the SSE reply of a real make_apps gateway carry the declared form, never the child's schema.
    tools = tools_of(product)
    store = full_store(tmp_path, product)
    try:
        child_schema = {'type': 'object', 'anyOf': [{'required': ['CHILD']}], 'x': 'CHILD-SCHEMA'}
        body = json.dumps({'jsonrpc': '2.0', 'id': 9, 'result': {'tools': [
            {'name': name, 'description': 'child text', 'inputSchema': child_schema} for name in tools]}}).encode()

        def upstream(_):
            if sse:
                return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                      content=b'data: ' + body + b'\n\n')
            return httpx.Response(200, headers={'content-type': 'application/json'}, content=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
            _, app = make_apps(store, tools, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://mcp') as client:
                response = await client.post('/mcp', headers={'Authorization': 'Bearer ' + store.load().token,
                                                              'Mcp-Session-Id': 's'},
                                             json={'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list', 'params': {}})
    finally:
        store.close()
    assert response.status_code == 200 and 'CHILD-SCHEMA' not in response.text
    raw = next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')) if sse else response.text
    listed = {tool['name']: tool['inputSchema'] for tool in json.loads(raw)['result']['tools']}
    assert set(listed) == set(tools)
    for name, schema in listed.items():
        assert provider_safe(schema), name
        assert schema == declared_schema(tools[name].arguments)
    seven = [name for name in SEVEN if SEVEN[name] == product]
    assert seven and all(listed[name]['description'] == PREFIX + RULES[name] + '.' for name in seven)


def test_nested_bypasses_are_still_refused_by_the_declared_schema():
    # Flattening only touches the top level: every nested bypass test_batch2_bounds refuses stays refused, except the
    # one search_count rule that was a top-level if/then (now a description clause, still refused by authorize).
    results = validate([(declared_schema(tools_of(product)[name].arguments), [args])
                        for product, name, args in NESTED_BYPASSES])
    moved = [(name, args) for (_, name, args), [ok] in zip(NESTED_BYPASSES, results) if ok]
    assert moved == [('generate_json2_payload',
                      {'model': 'res.partner', 'method': 'search_count', 'kwargs': {'limit': 10}})]


# The transformation itself, on shapes a future generator could produce (none of the pinned models does today).
class Deep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    y: str


class Nested(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: int
    deep: Deep | None = None


class Alpha(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['a']
    shared: str
    size: int = 1
    only_a: Nested


class Beta(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['b']
    shared: str
    size: str = 'x'


UNION = TypeAdapter(Annotated[Alpha | Beta, Field(discriminator='kind')]).json_schema()


def test_a_top_level_union_merges_its_branches():
    assert set(UNION) == {'$defs', 'discriminator', 'oneOf'}  # pydantic's shape for a discriminated union
    flat = flat_schema(UNION)
    alpha, beta = UNION['$defs']['Alpha']['properties'], UNION['$defs']['Beta']['properties']
    assert flat == {
        'type': 'object',
        'properties': {
            'kind': {'type': 'string', 'enum': ['a', 'b']},  # string consts merged into one enum
            'shared': alpha['shared'],  # identical in both: kept once
            'size': {'anyOf': [alpha['size'], beta['size']]},  # different: a nested anyOf of the distinct schemas
            'only_a': alpha['only_a'],  # Beta forbids it (additionalProperties false): Alpha's schema
        },
        'required': ['kind', 'shared'],  # what every branch requires, not the union
        'additionalProperties': False,  # every branch has it
        'description': RULES_PREFIX + 'kind="a": requires only_a and shared; kind="b": requires shared, omit only_a.',
        # Still referenced, directly or through Nested; Alpha and Beta are not.
        '$defs': {'Deep': UNION['$defs']['Deep'], 'Nested': UNION['$defs']['Nested']},
    }
    good = [{'kind': 'a', 'shared': 's', 'only_a': {'x': 1}}, {'kind': 'b', 'shared': 's', 'size': 'big'},
            {'kind': 'a', 'shared': 's', 'size': 3, 'only_a': {'x': 2, 'deep': {'y': 'z'}}},
            {'kind': 'b', 'shared': ''}]
    bad = [{'kind': 'c', 'shared': 's'}, {'kind': 'a'}, {'shared': 's'}, {'kind': 'b', 'shared': 's', 'extra': 1},
           {'kind': 'a', 'shared': 's', 'only_a': {'x': 'no'}}, {'kind': 'b', 'shared': 's', 'size': True},
           {'kind': 'a', 'shared': 's', 'only_a': {'x': 1, 'deep': {'y': 1}}}]
    loose = [{'kind': 'b', 'shared': 's', 'only_a': {'x': 1}}, {'kind': 'a', 'shared': 's', 'size': 'big'}]
    adapter = TypeAdapter(Annotated[Alpha | Beta, Field(discriminator='kind')])
    for args in good:
        adapter.validate_python(args)
    for args in bad + loose:
        with pytest.raises(ValidationError):
            adapter.validate_python(args)
    [declared, original] = validate([(flat, good + bad + loose), (UNION, good + bad + loose)])
    assert declared == [True] * len(good) + [False] * len(bad) + [True] * len(loose)
    assert original == [True] * len(good) + [False] * (len(bad) + len(loose))


def test_merge_rules_on_partial_branches():
    # A member a branch does not mention is free in that branch, unless the branch is closed: `tag` is declared nowhere
    # (the open first branch takes anything), `limit` is (the others refuse it). The schema's own members always win.
    schema = {'type': 'object', 'title': 'T', 'description': 'Own text.',
              'properties': {'mode': {'enum': ['x', 'y', 'z']}},
              'oneOf': [{'properties': {'mode': {'const': 'x'}, 'limit': {'maximum': 5}},
                         'required': ['mode', 'limit']},
                        {'properties': {'mode': {'const': 'y'}, 'tag': {'type': 'string'}}, 'required': ['mode'],
                         'additionalProperties': False},
                        {'properties': {'mode': {'const': 'z'}, 'tag': {'type': 'integer'}}, 'required': ['mode'],
                         'additionalProperties': False}]}
    flat = flat_schema(schema)
    assert flat == {'type': 'object', 'title': 'T',
                    'properties': {'mode': {'enum': ['x', 'y', 'z']}, 'limit': {'maximum': 5}},
                    'required': ['mode'],
                    'description': 'Own text. ' + RULES_PREFIX + 'mode="x": requires limit; mode="y": omit limit; '
                                   'mode="z": omit limit.'}
    good = [{'mode': 'x', 'limit': 3}, {'mode': 'y', 'tag': 'a'}, {'mode': 'z', 'tag': 1}, {'mode': 'y'},
            {'mode': 'x', 'limit': 5, 'tag': {}}]
    loose = [{'mode': 'y', 'tag': 5}, {'mode': 'x'}, {'mode': 'z', 'tag': 'a'}, {'mode': 'y', 'limit': 3}]
    [declared, original] = validate([(flat, good + loose + [{'mode': 'w'}, {}, {'mode': 'x', 'limit': 6}]),
                                     (schema, good + loose)])
    assert declared == [True] * (len(good) + len(loose)) + [False] * 3
    assert original == [True] * len(good) + [False] * len(loose)


def test_conjunctions_conditionals_and_value_rules():
    member = {'type': 'object', 'properties': {'n': {'type': 'integer'}}, 'additionalProperties': False}
    schema = {'type': 'object', 'properties': {'t': {'enum': ['p', 'q']}, 'p': {'type': 'string'}},
              'allOf': [{'required': ['t']}, {'properties': {'q': {'type': 'string'}, 'p': {'const': 'P'}}}],
              'if': {'properties': {'t': {'const': 'p'}}}, 'then': {'required': ['p']},
              'else': {'required': ['p', 'q'], 'properties': {'q': {'not': {'enum': ['none', 'null']}}}},
              'not': {'required': ['n']}, '$defs': {'Unused': member}}
    flat = flat_schema(schema)
    assert flat == {
        'type': 'object',
        'properties': {'t': {'enum': ['p', 'q']}, 'p': {'type': 'string'}, 'q': {'type': 'string'}},
        'required': ['t', 'p'],  # allOf adds t; one of then/else holds and both require p
        'description': RULES_PREFIX + 'requires t; p must be "P"; if t="p": requires p; otherwise: requires p and q, '
                                      'q must not be "none" or "null"; '
                                      'the arguments must not match {"required":["n"]}.',
    }
    good = [{'t': 'p', 'p': 'P'}, {'t': 'q', 'p': 'P', 'q': 'x'}]
    loose = [{'t': 'p', 'p': 'other'}, {'t': 'q', 'p': 'P'}, {'t': 'q', 'p': 'P', 'q': 'none'},
             {'t': 'p', 'p': 'P', 'n': 1}]
    [declared, original] = validate([(flat, good + loose + [{'p': 'P'}, {'t': 'p'}]), (schema, good + loose)])
    assert declared == [True] * (len(good) + len(loose)) + [False, False]
    assert original == [True] * len(good) + [False] * len(loose)
    # A top-level $ref, const or enum is replaced too; the referenced definition's members are declared.
    ref = {'$ref': '#/$defs/Model', '$defs': {'Model': {**member, 'required': ['n']}}, 'enum': [{'n': 1}, {'n': 2}]}
    assert flat_schema(ref) == {'type': 'object', 'properties': {'n': {'type': 'integer'}}, 'required': ['n'],
                                'additionalProperties': False,
                                'description': RULES_PREFIX + 'the arguments must be one of [{"n":1},{"n":2}].'}
    assert flat_schema({'type': 'object', 'properties': {}, 'const': {}}) == {
        'type': 'object', 'properties': {}, 'description': RULES_PREFIX + 'the arguments must equal {}.'}
    # unevaluatedProperties counted what the branches evaluated: without them it would refuse valid arguments.
    uneval = {'type': 'object', 'properties': {'a': {'type': 'string'}}, 'unevaluatedProperties': False,
              'oneOf': [{'properties': {'b': {'type': 'string'}}, 'required': ['b']},
                        {'properties': {'c': {'type': 'integer'}}, 'required': ['c']}]}
    assert flat_schema(uneval) == {'type': 'object', 'properties': {'a': {'type': 'string'}},
                                   'description': RULES_PREFIX + 'the arguments must match one of: (1) requires b; '
                                                  '(2) requires c.'}
    valid = [{'a': 'x', 'b': 'y'}, {'c': 1}]
    assert validate([(uneval, valid), (flat_schema(uneval), valid)]) == [[True, True], [True, True]]
    # An already safe schema is returned as is.
    safe = {'type': 'object', 'properties': {'a': {'anyOf': [{'type': 'string'}, {'type': 'null'}]}}}
    assert flat_schema(safe) is safe


def test_false_members_several_values_and_own_keywords():
    # A false member schema only forbids the member (the other branch's schema is declared as is); a discriminator
    # may carry several values; members only an open branch mentions stay free.
    schema = {'type': 'object', 'oneOf': [
        {'properties': {'k': {'enum': ['a', 'c']}, 'p': False, 'q': {'type': 'null'}}, 'required': ['k', 'q']},
        {'properties': {'k': {'const': 'b'}, 'p': {'type': 'string'}, 'mode': {'enum': ['fast', 'slow']}},
         'required': ['k', 'p']}]}
    flat = flat_schema(schema)
    assert flat == {'type': 'object', 'properties': {'k': {'type': 'string', 'enum': ['a', 'c', 'b']},
                                                     'p': {'type': 'string'}},
                    'required': ['k'],
                    'description': RULES_PREFIX + 'k one of ["a","c"]: omit p, q must be null; k="b": requires p, '
                                   'mode must be one of "fast", "slow".'}
    good = [{'k': 'a', 'q': None}, {'k': 'c', 'q': None}, {'k': 'b', 'p': 'x', 'mode': 'fast'}, {'k': 'b', 'p': ''}]
    loose = [{'k': 'a', 'q': None, 'p': 'x'}, {'k': 'b'}, {'k': 'b', 'p': 'x', 'mode': 'other'}, {'k': 'a'}]
    # Literals that are not strings are never merged into a string enum: they stay distinct anyOf members.
    numbers = {'type': 'object', 'oneOf': [{'properties': {'v': {'const': 1}}, 'required': ['v']},
                                           {'properties': {'v': {'const': 2}}, 'required': ['v']}]}
    assert flat_schema(numbers) == {'type': 'object', 'properties': {'v': {'anyOf': [{'const': 1}, {'const': 2}]}},
                                    'required': ['v'],
                                    'description': RULES_PREFIX + 'the arguments must match one of: (1) requires v, '
                                                   'v must be 1; (2) requires v, v must be 2.'}
    [declared, original, counted] = validate([(flat, good + loose + [{'k': 'd'}, {'k': 'b', 'p': 1}, {}]),
                                              (schema, good + loose),
                                              (flat_schema(numbers), [{'v': 1}, {'v': 2}, {'v': 3}])])
    assert declared == [True] * (len(good) + len(loose)) + [False] * 3
    assert original == [True] * len(good) + [False] * len(loose)
    assert counted == [True, True, False]
    # The schema's own keywords stay, a typed additionalProperties included; without a discriminator the branches
    # are numbered.
    own = {'type': 'object', 'properties': {'a': {'type': 'string'}}, 'additionalProperties': {'type': 'integer'},
           'anyOf': [{'required': ['a']}, {'required': ['b']}]}
    assert flat_schema(own) == {'type': 'object', 'properties': {'a': {'type': 'string'}},
                                'additionalProperties': {'type': 'integer'},
                                'description': RULES_PREFIX + 'the arguments must match one of: (1) requires a; '
                                               '(2) requires b.'}
    # A false branch accepts nothing and adds nothing; a member one branch leaves unconstrained is unconstrained.
    single = {'type': 'object', 'oneOf': [False, {'properties': {'a': {'const': 'x'}}, 'required': ['a']}]}
    assert flat_schema(single) == {'type': 'object', 'properties': {'a': {'const': 'x'}}, 'required': ['a'],
                                   'description': RULES_PREFIX + 'the arguments must match one of: (1) requires a, '
                                                  'a must be "x".'}
    free = {'type': 'object', 'oneOf': [
        {'properties': {'k': {'const': 'x'}, 'r': {}}, 'additionalProperties': False},
        {'properties': {'k': {'const': 'y'}, 'r': {'type': 'string'}}, 'additionalProperties': False}]}
    assert flat_schema(free) == {'type': 'object', 'properties': {'k': {'type': 'string', 'enum': ['x', 'y']}, 'r': {}},
                                 'additionalProperties': False,
                                 'description': RULES_PREFIX + 'k="x" (or omitted): no further rules; '
                                                'k="y" (or omitted): no further rules.'}


def test_conditionals_pattern_members_mixed_values_and_true_branches_stay_supersets():
    # (review F1) Instances each original schema accepts, which its declared form must accept too: with if/then/else
    # either then or else holds (neither's required is required of all); a branch whose patternProperties admit
    # members it does not list is not closed; an enum mixing a string and a number is never merged into a string
    # enum; a true branch accepts every object, so it is never closed.
    conditional = {'type': 'object', 'if': {'properties': {'t': {'const': 'a'}}, 'required': ['t']},
                   'then': {'required': ['x']}, 'else': {'required': ['y']}}
    pattern = {'type': 'object', 'oneOf': [
        {'properties': {'a': {'type': 'string'}}, 'patternProperties': {'^x-': {}}, 'additionalProperties': False,
         'required': ['a']},
        {'properties': {'b': {'type': 'string'}}, 'additionalProperties': False, 'required': ['b']}]}
    mixed = {'type': 'object', 'oneOf': [{'properties': {'k': {'enum': ['a', 1]}}, 'required': ['k']},
                                         {'properties': {'k': {'const': 'b'}}, 'required': ['k']}]}
    true = {'type': 'object', 'oneOf': [True, {'properties': {'a': {'type': 'string'}}, 'additionalProperties': False}]}
    cases = [(conditional, [{'t': 'a', 'x': 1}, {'t': 'b', 'y': 1}]), (pattern, [{'a': 's', 'x-1': 1}, {'b': 's'}]),
             (mixed, [{'k': 1}, {'k': 'a'}, {'k': 'b'}]), (true, [{'a': 1}, {'z': 1}])]
    assert all(provider_safe(flat_schema(schema)) for schema, _ in cases)
    results = validate(cases + [(flat_schema(schema), instances) for schema, instances in cases])
    assert results == [[True] * len(instances) for _, instances in cases] * 2  # the originals, then the declared forms
