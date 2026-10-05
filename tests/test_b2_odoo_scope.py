"""Facade/source contract probes in the exact pinned Odoo interpreter."""
import json
from pathlib import Path
import subprocess
import pytest
from mcp_admin_core.products import TOOLS
from test_b2_odoo_policy import CASES, BAD

ROOT = Path(__file__).resolve().parents[1]


def probe(code, data=None):
    result = subprocess.run([str(ROOT/'apps/odoo/.venv/bin/python'), '-c', code],
        input=json.dumps(data), text=True, capture_output=True, timeout=20,
        env={'PATH':'/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1',
             'PYTHONPATH':str(ROOT/'apps/runtime')})
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize('name,args', CASES)
def test_b2_private_validator_parity(name, args):
    model = TOOLS['odoo'][name].arguments
    valid = [model.model_validate(args).model_dump(), model.model_validate({**args,'instance':'default'}).model_dump()]
    invalid = [{**valid[0],**change} for change in BAD[name]]
    invalid += [{**valid[0],key:value} for key,value in [('context',{}),('instance','other'),('ctx',{})]]
    probe('''
import json,sys
from odoo_b2_scope import arguments
name,valid,invalid=json.load(sys.stdin)
for values in valid: arguments(name,values)
for values in invalid:
    try: arguments(name,values)
    except ValueError: pass
    else: raise AssertionError(values)
''', [name,valid,invalid])


def test_b2_genuine_sources_cache_generation_failures_and_facade():
    probe('''
from types import SimpleNamespace as NS
import asyncio
from odoo_mcp import server, tools_read, tools_diagnostics, tools_data_quality
import odoo_b2_scope as b
b.guard_sources()
class Client:
    def __init__(self): self.calls=[]; self.required=True; self.bad=False; self.no_fields=False
    def execute_method(self,model,method,*args,**kwargs):
        self.calls.append((model,method,args,kwargs))
        if method=='search_read': return [{'model':'res.partner','name':'PRIVATE'}]
        if method=='fields_get':
            if self.no_fields: return {}
            return {name:{'type':b.FIELD_TYPES[name], 'required': self.required and name=='name',
                'relation':'res.partner', 'compute':'PRIVATE', 'help':'PRIVATE', 'default':'PRIVATE'} for name in args[0]}
        if method=='search_count': return True if self.bad else 4
        raise AssertionError('arbitrary operation')
a=Client(); app=NS(odoo=a,_default_instance_name='default')
ctx=NS(request_context=NS(lifespan_context=app))
originals={'schema_catalog':tools_read.schema_catalog,'inspect_model_relationships':tools_diagnostics.inspect_model_relationships,
           'data_quality_report':tools_data_quality.data_quality_report}
seen=[]
def spy(name):
    def invoke(**kw):
        seen.append(name)
        return originals[name](**kw)
    return invoke
wrapped={name:b.wrap(name,spy(name)) for name in originals}
for name in originals:
    args={} if name=='schema_catalog' else {'model':'res.partner'}
    assert wrapped[name](ctx=ctx,**args)['success']
assert seen==list(originals), seen
catalog=wrapped['schema_catalog']
assert catalog(ctx=ctx)['metadata_used']['cache_hit']
for fields in (False,True):
    for refresh in (False,True):
        for instance in (None,'default'):
            assert catalog(ctx=ctx,include_fields=fields,refresh=refresh,instance=instance)['success']
assert len(app._b2_catalog[1])==2
assert 'PRIVATE' not in repr(app._b2_catalog[1])
before=len(a.calls)
assert catalog(ctx=ctx,query='other')['success'] is False
assert len(a.calls)==before
# Identity/generation change invalidates both keys, before returning a cache hit.
z=Client(); z.required=False; app.odoo=z
result=catalog(ctx=ctx,include_fields=True)
assert result['metadata_used']['cache_hit'] is False and z.calls
assert result['result'][0]['fields']['name']['required'] is False
quality=wrapped['data_quality_report']
result=quality(ctx=ctx,model='res.partner')
assert result['results'][0]['fields_checked']==[] and result['summary']['clean'] is True
z.required=True; z.bad=True
assert quality(ctx=ctx,model='res.partner')=={'success':False,'tool':'data_quality_report','error':'BACKEND_RESPONSE_INVALID'}
z.no_fields=True
assert catalog(ctx=ctx,include_fields=True,refresh=True)['success'] is False
assert app._b2_catalog[1]=={}
# Source drift is checked even on cache hits and raises no raw diagnostic.
z.no_fields=False; z.bad=False
assert catalog(ctx=ctx)['success']
before=len(z.calls); b.SOURCES['tools_read']='0'*64
assert catalog(ctx=ctx)['success'] is False
assert len(z.calls)==before
# The facade itself denies arbitrary execution/read/group/related model paths.
f=b.ScopedClient(z,True)
for model,method,args in [('res.users','search_count',[[['name','=',False]]]),
                         ('res.partner','read_group',[]),('res.partner','search_read',[])]:
    try: f.execute_method(model,method,*args)
    except ValueError: pass
    else: raise AssertionError('unsafe facade call')
assert not hasattr(f,'search_read') and not hasattr(f,'get_user_context')
''')


@pytest.mark.parametrize('include_fields', [False, True])
def test_b2_source_drift_erases_both_catalog_variants(include_fields):
    print(probe('''
import json, sys
from types import SimpleNamespace as NS
from odoo_mcp import server, server_core, tools_read
import odoo_b2_scope as b
include_fields = json.load(sys.stdin)
class Client:
    def __init__(self): self.calls=[]
    def execute_method(self, model, method, *args, **kwargs):
        self.calls.append((model, method, args, kwargs))
        if method == 'search_read':
            assert model == 'ir.model' and args == ([['model', '=', 'res.partner']],)
            assert kwargs == {'fields': ['model'], 'limit': 1}
            return [{'model': 'res.partner'}]
        assert model == 'res.partner' and method == 'fields_get'
        assert args == (list(b.FIELD_TYPES),) and kwargs == {'attributes': b.ATTRIBUTES}
        return {name: {'type': kind, 'relation': 'res.partner'} for name, kind in b.FIELD_TYPES.items()}
client = Client()
app = NS(odoo=client, _default_instance_name='default')
ctx = NS(request_context=NS(lifespan_context=app))
catalog = b.wrap('schema_catalog', tools_read.schema_catalog)
def populate():
    for fields in (False, True):
        before = len(client.calls)
        result = catalog(ctx=ctx, include_fields=fields)
        assert result['success'] and result['metadata_used']['cache_hit'] is False
        assert len(client.calls) - before == 1 + int(fields)
    assert len(app._b2_catalog[1]) == 2
populate()
cache = app._b2_catalog[1]
# Observe genuine functions without replacing the handler, resolver or guard.
watched = {tools_read.schema_catalog.__code__, server_core._resolve_odoo.__code__, Client.__init__.__code__}
executed = []
def trace(frame, event, arg):
    if event == 'call' and frame.f_code in watched: executed.append(frame.f_code.co_name)
before = len(client.calls)
old = b.SOURCES['tools_read']
b.SOURCES['tools_read'] = '0' * 64  # only fault injection; never edit installed sources
try:
    sys.setprofile(trace)
    failed = catalog(ctx=ctx, include_fields=include_fields)
finally:
    sys.setprofile(None)
    b.SOURCES['tools_read'] = old
assert failed == {'success': False, 'tool': 'schema_catalog', 'error': 'BACKEND_RESPONSE_INVALID'}
assert len(client.calls) == before and executed == [], executed
assert cache == {}, 'source drift retained %d catalog variants' % len(cache)
assert app._b2_catalog == (client, cache)
populate()  # each first recovered variant must perform fresh bounded RPCs
before = len(client.calls)
for fields in (False, True):
    assert catalog(ctx=ctx, include_fields=fields)['metadata_used']['cache_hit'] is True
assert len(client.calls) == before and len(cache) == 2
print('B2_DRIFT_CACHE_OK variants=2 drift_rpc=0 resolver=0 handler=0 constructor=0 recovery_rpc=3 hit_rpc=0')
''', include_fields))


def test_b2_baseexception_cancellation_not_swallowed():
    probe('''
import asyncio
from types import SimpleNamespace as NS
import odoo_b2_scope as b
class Client: pass
ctx=NS(request_context=NS(lifespan_context=NS(odoo=Client(),_default_instance_name='default')))
def cancelled(**kw): raise asyncio.CancelledError()
for name in b.DEFAULTS:
    args={} if name=='schema_catalog' else {'model':'res.partner'}
    try: b.wrap(name,cancelled)(ctx=ctx,**args)
    except asyncio.CancelledError: pass
    else: raise AssertionError(name)
''')


def test_b2_fixed_transport_failures_pass_through_and_other_text_stays_hidden():
    # 0.1.1 HA: an account without ir.model read access made schema_catalog say BACKEND_RESPONSE_INVALID.
    print(probe('''
from types import SimpleNamespace as NS
from odoo_mcp import tools_read, tools_diagnostics, tools_data_quality
import odoo_b2_scope as b
b.guard_sources()
class Client:
    def __init__(self, error): self.error = error
    def execute_method(self, model, method, *args, **kwargs):
        if self.error is None:
            if method == 'search_read': return [{'model': 'res.partner'}]
            return {name: {'type': kind, 'relation': 'res.partner'} for name, kind in b.FIELD_TYPES.items()}
        raise ValueError(self.error)
cases = [('BACKEND_RPC_FAULT', 'BACKEND_RPC_FAULT'), ('BACKEND_TIMEOUT', 'BACKEND_TIMEOUT'),
         ('BACKEND_UNAVAILABLE', 'BACKEND_UNAVAILABLE'), ('BACKEND_HTTP_ERROR status=403', 'BACKEND_HTTP_ERROR status=403'),
         ('PRIVATE partner Alice', 'BACKEND_RESPONSE_INVALID'), ('BACKEND_RPC_FAULT PRIVATE', 'BACKEND_RESPONSE_INVALID'),
         ('BACKEND_HTTP_ERROR status=4031', 'BACKEND_RESPONSE_INVALID')]
for error, expected in cases:
    client = Client(None)
    app = NS(odoo=client, _default_instance_name='default')
    ctx = NS(request_context=NS(lifespan_context=app))
    catalog = b.wrap('schema_catalog', tools_read.schema_catalog)
    assert catalog(ctx=ctx)['success'] is True and len(app._b2_catalog[1]) == 1
    client.error = error
    result = catalog(ctx=ctx, refresh=True)
    assert result == {'success': False, 'tool': 'schema_catalog', 'error': expected}, (error, result)
    assert app._b2_catalog[1] == {}, 'a failure must not keep catalog variants'
    for name, handler in (('inspect_model_relationships', tools_diagnostics.inspect_model_relationships),
                          ('data_quality_report', tools_data_quality.data_quality_report)):
        result = b.wrap(name, handler)(ctx=ctx, model='res.partner')
        assert result['success'] is False and result['tool'] == name, result
        assert result['error'] in (expected, 'BACKEND_RESPONSE_INVALID'), (name, error, result)
        assert 'PRIVATE' not in repr(result)
print('B2_PUBLIC_FAILURES_OK cases=%d' % len(cases))
'''))
