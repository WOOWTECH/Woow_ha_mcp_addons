"""B3 accepted schemas must equal runtime authorization; no new grants."""
from contextlib import closing
from copy import deepcopy
from mcp_admin_core.config import State
from mcp_admin_core.products import ProductState
from mcp_admin_core.policy import Tool
import pytest
from pydantic import ValidationError
from mcp_admin_core.products import ProductStore
from mcp_admin_core.policy import authorize, Denied
from n8n_adapter import TOOLS
from test_batch2_bounds import schema_results
from test_expansion_policy import call

CASES = [('n8n_list_catalog', {'kind': 'tags'}),
         ('n8n_executions', {'action': 'list'}),
         ('n8n_health_check', {}),
         ('n8n_manage_folders', {'action': 'get', 'projectId': 'project1', 'folderId': 'folder1'})]
BAD = {
    'n8n_list_catalog': [{'kind':'projects'}, {'kind':None}, {'query':None}, {'query':'x'*257}, {'limit':251}, {'limit':None}, {'limit':True}, {'cursor':'abc'}],
    'n8n_executions': [{'action':'get'}, {'action':'delete'}, {'includeData':True}, {'includeData':0}, {'limit':101}, {'limit':True}, {'cursor':None}, {'cursor':'x'*513}, {'cursor':'../../'}, {'cursor':'abc\n'}, {'cursor':''}, {'includeData':None}, {'limit':None}, {'workflowId':'abc\n'}, {'workflowId':None}, {'workflowId':'../x'}, {'projectId':'personal'}, {'status':'private'}, {'status':None}],
    'n8n_health_check': [{'mode':'diagnostic'}, {'mode':None}, {'verbose':True}],
    'n8n_manage_folders': [{'projectId':'personal'}, {'projectId':None}, {'folderId':None}, {'folderId':'../x'}, {'folderId':'abc\n'}, {'projectId':'abc\n'}, {'name':'x'}, {'action':'move'}, {'action':'delete'}],
}

@pytest.mark.parametrize('name,args', CASES)
def test_b3_schema_parity(tmp_path, name, args):
    assert name in TOOLS
    tool = TOOLS[name]
    candidates = [(args, True)] + [({**args, **change}, False) for change in BAD[name]]
    candidates += [({**args, key:value}, False) for key,value in [('url','http://other.invalid'),('unknown',True),('credentials',{})]]
    if name == 'n8n_manage_folders':
        candidates.append(({'action':'get','folderId':'folder1'},False))
    with closing(ProductStore(tmp_path,'n8n')) as store:
        store.update(backend_url='http://backend.invalid', backend_key='DUMMY_B3_KEY')
        schema = tool.arguments.model_json_schema()
        for (value, valid), matched in zip(candidates, schema_results(schema,[v for v,_ in candidates]), strict=True):
            assert matched == valid, value
            if valid:
                parsed = tool.arguments.model_validate(value).model_dump()
                authorize(call(name,parsed),TOOLS,store.load())
            else:
                with pytest.raises(ValidationError): tool.arguments.model_validate(value)
                message = call(name,deepcopy(value))
                before = deepcopy(message)
                with pytest.raises(Denied): authorize(message,TOOLS,store.load())
                assert message == before
        store.update(disabled=[name],writes_enabled=True)
        with pytest.raises(Denied): authorize(call(name,args),TOOLS,store.load())
        assert tool.grants(name) == (['n8n_manage_folders:create','n8n_manage_folders:rename'] if name == 'n8n_manage_folders' else [])


@pytest.mark.parametrize('state_type', [State, ProductState])
@pytest.mark.parametrize('url,key', [(None,None), ('http://backend.invalid',None), (None,'DUMMY_B3_KEY'), ('http://backend.invalid','DUMMY_B3_KEY')])
@pytest.mark.parametrize('name,args', CASES)
def test_b3_backend_precondition(state_type, url, key, name, args):
    state = state_type(token='a'*43, child_token='b'*43, backend_url=url, backend_key=key,
                       **({'product':'n8n'} if state_type is ProductState else {}))
    message = call(name,deepcopy(args))
    before = deepcopy(message)
    if url and key:
        authorize(message,TOOLS,state)
        normalized = deepcopy(message)
        authorize(message,TOOLS,state)
        assert message == normalized
    else:
        with pytest.raises(Denied, match='backend'):
            authorize(message,TOOLS,state)
        assert message == before
    # Default-OFF: older APIs and genuine local tools keep their old policy.
    for old_name, old_args in [('tools_documentation',{}), ('search_nodes',{'query':'webhook'}),
                               ('n8n_list_workflows',{}), ('n8n_manage_folders',{'action':'list'})]:
        authorize(call(old_name,old_args),TOOLS,state)


def test_b3_inconsistent_backend_metadata_rejected():
    with pytest.raises(ValueError):
        Tool(TOOLS['n8n_executions'].arguments, backend_required_operations=('list',))
    with pytest.raises(ValueError):
        Tool(TOOLS['n8n_executions'].arguments, selector='missing', backend_required_operations=('list',))
    with pytest.raises(ValueError):
        Tool(TOOLS['n8n_executions'].arguments, selector='action', backend_required_operations=('typo',))


def test_b3_defaults_and_folder_existing_contract():
    assert TOOLS['n8n_executions'].arguments.model_validate({'action':'list'}).model_dump() == {'action':'list','limit':20,'includeData':False}
    assert TOOLS['n8n_health_check'].arguments.model_validate({}).model_dump() == {'mode':'status'}
    for args in [{'action':'list'}, {'action':'create','name':'Owned'}, {'action':'rename','folderId':'folder1','name':'Owned'}]:
        assert TOOLS['n8n_manage_folders'].arguments.model_validate(args).model_dump()['projectId'] == 'personal'
