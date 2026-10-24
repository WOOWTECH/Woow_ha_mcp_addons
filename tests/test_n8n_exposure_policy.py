"""The exposure flag is an indirect workflow update, including child coercions."""
import copy
import json

import pytest

from mcp_admin_core.capabilities import tool_catalog
from mcp_admin_core.policy import ToolCallRefused, authorize
from mcp_admin_core.products import ProductState, fresh_write_grants
from mcp_admin_core.surface import listing
from n8n_adapter import TOOLS

UPDATER = 'n8n_update_partial_workflow'
VERSIONS = 'n8n_workflow_versions'
TEST = 'n8n_test_workflow'
MIXED = [
    (VERSIONS,'mode','list','rollback'),
    ('n8n_executions','action','list','delete'),
    ('n8n_evaluations','action','list_runs','run'),
    ('n8n_manage_credentials','action','list','delete'),
    ('n8n_manage_folders','action','list','delete'),
    ('n8n_manage_datatable','action','listTables','deleteTable'),
]


def state(name=VERSIONS, *, updater=False, disabled=(), denies=None, global_write=False):
    return ProductState(product='n8n', token='s'*43, child_token='c'*43,
        backend_url='https://offline.invalid', backend_key='synthetic',
        enabled_write_tools=([TEST] if name == TEST else []) + ([UPDATER] if updater else []),
        writes_enabled=global_write, disabled=list(disabled), denied_operations=denies or {})


def call(name, arguments):
    return {'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':name,'arguments':arguments}}


def arguments(flag=True):
    return {'mode':'list','source':'native','workflowId':'synthetic', 'exposeToMcp':flag}


EXPOSURES = [arguments(), arguments('true'), arguments(' \ttrue\r\n'),
             arguments('\ufefftrue\u2029'), {'output':json.dumps(arguments())},
             {**arguments(False), 'output':json.dumps(arguments())},
             {'output':json.dumps({**arguments(), 'limit':'0x10'})}]


@pytest.mark.parametrize('name', [VERSIONS, TEST])
@pytest.mark.parametrize('args', EXPOSURES)
@pytest.mark.parametrize('restriction', ['ungranted','disabled','denied','global_only'])
def test_exposure_is_denied_before_child(name, args, restriction):
    current = state(name, updater=restriction in ('disabled','denied'),
                    disabled=[UPDATER] if restriction == 'disabled' else [],
                    denies={UPDATER:['retained_unknown_operation']} if restriction == 'denied' else {},
                    global_write=restriction == 'global_only')
    child_calls = []
    with pytest.raises(ToolCallRefused) as failure:
        authorize(call(name, copy.deepcopy(args)), TOOLS, current)
        child_calls.append('would dispatch')
    assert failure.value.kind == 'operation_not_permitted'
    assert failure.value.error()['code'] == -32602
    assert child_calls == []


@pytest.mark.parametrize('name', [VERSIONS, TEST])
@pytest.mark.parametrize('args', EXPOSURES)
def test_explicit_updater_grant_forwards_canonical_arguments_idempotently(name, args):
    message = call(name, copy.deepcopy(args))
    assert authorize(message, TOOLS, state(name, updater=True)) == 'tools/call'
    canonical = copy.deepcopy(message)
    assert authorize(message, TOOLS, state(name, updater=True)) == 'tools/call'
    assert message == canonical  # no double unwrap when gateway rechecks after yielding
    expected = json.loads(args['output']) if 'output' in args else copy.deepcopy(args)
    expected['exposeToMcp'] = True
    assert message['params']['arguments'] == expected


@pytest.mark.parametrize('mode', ['list','get','diff'])
@pytest.mark.parametrize('flag', [False, 'false', ' \tfalse\n', 'omitted'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_normal_reads_keep_zero_grants(mode, flag, wrapped):
    args = {**arguments(flag), 'mode':mode, 'versionId':'a','toVersionId':'b'}
    if flag == 'omitted':
        args.pop('exposeToMcp')
    if wrapped:
        args = {'output':json.dumps(args)}
    assert authorize(call(VERSIONS,args),TOOLS,state()) == 'tools/call'


@pytest.mark.parametrize('nested', [
    {**arguments(), 'exposeToMcp':'true'},  # child rejects extracted boolean type, uses outer args
    {**arguments(), 'limit':'not-a-number'},
    {**arguments(), 'workflowId':17},
])
def test_invalid_nested_candidate_uses_outer_read(nested):
    outer = {**arguments(False), 'output':json.dumps(nested)}
    assert authorize(call(VERSIONS,outer),TOOLS,state()) == 'tools/call'


@pytest.mark.parametrize('mode', ['list','rollback'])
@pytest.mark.parametrize('granted', [False,True])
def test_second_eligible_unwrap_is_rejected_even_with_full_grants(mode, granted):
    inner = {**arguments(False), 'mode':mode}
    twice = {'output':json.dumps({**arguments(False), 'output':json.dumps(inner)})}
    current = state().model_copy(update={'enabled_write_tools':fresh_write_grants('n8n')}) if granted else state()
    with pytest.raises(ToolCallRefused) as failure:
        authorize(call(VERSIONS,twice),TOOLS,current)
    assert failure.value.kind == 'invalid_params'


@pytest.mark.parametrize('restriction', ['ungranted','denied'])
def test_effective_mode_cannot_hide_rollback(restriction):
    hidden = {**arguments(False),'output':json.dumps({**arguments(False),'mode':'rollback'})}
    current = state(denies={VERSIONS:['rollback']} if restriction == 'denied' else {})
    if restriction == 'denied':
        current = current.model_copy(update={'enabled_write_tools':[VERSIONS+':rollback']})
    with pytest.raises(ToolCallRefused):
        authorize(call(VERSIONS,hidden),TOOLS,current)


def test_unparseable_integer_cannot_hide_child_exposure():
    nested = '{"mode":"list","exposeToMcp":true,"unknown":' + '9'*5000 + '}'
    with pytest.raises(ToolCallRefused) as failure:
        authorize(call(VERSIONS,{**arguments(False),'output':nested}),TOOLS,state())
    assert failure.value.kind == 'invalid_params'


def test_test_workflow_still_requires_its_own_grant():
    with pytest.raises(ToolCallRefused) as failure:
        authorize(call(TEST,arguments()),TOOLS,state(updater=True))
    assert failure.value.kind == 'unknown_tool'


def test_existing_grants_schema_and_full_defaults_unchanged():
    grants = fresh_write_grants('n8n')
    assert len(TOOLS) == 28 and len(grants) == 33
    current = state().model_copy(update={'enabled_write_tools':grants, 'writes_enabled':True})
    before = current.model_dump()
    for name in (VERSIONS,TEST):
        assert authorize(call(name,arguments()),TOOLS,current) == 'tools/call'
    assert current.schema_version == 4 and current.model_dump() == before
    assert authorize(call('n8n_list_workflows',{'exposeToMcp':True}),TOOLS,state()) == 'tools/call'


def test_capabilities_describe_conditional_dependency_without_hiding_reads():
    for granted in (False,True):
        rows = tool_catalog(TOOLS,listing('n8n'),None,state(updater=granted))['items']
        version = next(row for row in rows if row['name'] == VERSIONS)
        assert version['policy_enabled'] is True
        assert version['conditional_writes'] == [{'parameter':'exposeToMcp',
            'requires_tool':UPDATER,'policy_enabled':granted}]
        assert version['write_grants'] == [VERSIONS+':'+value for value in ('rollback','delete','prune')]


@pytest.mark.parametrize('name,selector,read,write', MIXED)
@pytest.mark.parametrize('restriction', ['no_grant','write_denied','read_denied','ambiguous'])
def test_every_mixed_tool_checks_effective_selector_before_dispatch(name,selector,read,write,restriction):
    current = state()
    operation = read if restriction == 'read_denied' else write
    inner = {selector:operation,'workflowId':'synthetic','id':'synthetic'}
    outer = {selector:read,'output':json.dumps(inner)}
    if restriction in ('write_denied','read_denied'):
        current = current.model_copy(update={'enabled_write_tools':fresh_write_grants('n8n'),
                                            'denied_operations':{name:[operation]}})
    if restriction == 'ambiguous':
        # The intermediate object must itself satisfy the child's required keys.
        intermediate = {selector:read,'workflowId':'synthetic','output':json.dumps(inner)}
        outer = {'output':json.dumps(intermediate)}
        current = current.model_copy(update={'enabled_write_tools':fresh_write_grants('n8n')})
    dispatched = []
    with pytest.raises(ToolCallRefused) as failure:
        authorize(call(name,outer),TOOLS,current)
        dispatched.append(outer)
    assert failure.value.kind == ('invalid_params' if restriction == 'ambiguous' else 'operation_not_permitted')
    assert dispatched == []


@pytest.mark.parametrize('name,selector,read,write', MIXED)
@pytest.mark.parametrize('write_granted', [False,True])
def test_every_mixed_tool_retains_normal_reads_and_explicit_writes(name,selector,read,write,write_granted):
    inner = {selector:write if write_granted else read,'workflowId':'synthetic','id':'synthetic'}
    message = call(name,{'output':json.dumps(inner)})
    current = state().model_copy(update={'enabled_write_tools':[name+':'+write] if write_granted else []})
    authorize(message,TOOLS,current)
    assert message['params']['arguments'] == inner
    authorize(message,TOOLS,current)
    assert message['params']['arguments'] == inner


def test_all_28_use_pinned_schema_normalization_and_only_two_require_updater():
    from mcp_admin_core.n8n_arguments import SCHEMAS
    assert len(SCHEMAS) == 28 and set(SCHEMAS) == set(TOOLS)
    assert all(tool.n8n_arguments for tool in TOOLS.values())
    assert {name for name,tool in TOOLS.items() if tool.exposure_write_tool} == {VERSIONS,TEST}
