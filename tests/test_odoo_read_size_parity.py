"""The pinned Odoo 1.3.0 child must not disguise read failures or emit huge reads.

Runs the actual wheel in its lockfile venv, with a fake in-process Odoo client.
No network or real customer data is used.
"""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'apps/odoo/.venv/bin/python'


def probe(code):
    result = subprocess.run([str(PYTHON), '-B', '-c', code], cwd=ROOT,
                            capture_output=True, text=True, timeout=35,
                            env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp',
                                 'PYTHONDONTWRITEBYTECODE': '1',
                                 'PYTHONPATH': str(ROOT / 'apps/runtime')})
    assert result.returncode == 0, result.stderr[-1600:]
    return json.loads(result.stdout.splitlines()[-1])


def test_real_handler_reports_synthetic_read_fault_instead_of_zero_records():
    value = probe(r'''
import json
from types import SimpleNamespace as NS
from odoo_mcp.odoo_client import OdooClient
from odoo_mcp import tools_read
import odoo_read_errors

class Fake:
    search_read = OdooClient.search_read
    read_records = OdooClient.read_records
    def _execute(self, *args, **kwargs):
        raise ValueError('SYNTHETIC_ACCESS_DENIED')

fake = Fake()
app = NS(odoo=fake, _default_instance_name='default', schema_cache={})
ctx = NS(request_context=NS(lifespan_context=app))
before_search = tools_read.search_records(ctx=ctx, model='res.partner', fields=['id'])
before_read = tools_read.read_record(ctx=ctx, model='res.partner', record_id=5, fields=['id','name'])
odoo_read_errors.propagate_read_errors(Fake)
after_search = tools_read.search_records(ctx=ctx, model='res.partner', fields=['id'])
after_read = tools_read.read_record(ctx=ctx, model='res.partner', record_id=5, fields=['id','name'])
print(json.dumps({'before_search':before_search,'before_read':before_read,
                  'after_search':after_search,'after_read':after_read}))
''')
    assert value['before_search']['success'] is True
    assert value['before_search']['count'] == 0
    assert value['before_read'] == {'success': False, 'error': 'Record not found: res.partner ID 5'}
    assert value['after_search'] == {'success': False, 'error': 'SYNTHETIC_ACCESS_DENIED'}
    assert value['after_read'] == {'success': False, 'error': 'SYNTHETIC_ACCESS_DENIED'}


def test_oversized_read_becomes_mcp_error_with_bounded_diagnostic():
    value = probe(r'''
import asyncio,json
from odoo_mcp.server import mcp
import odoo_result_limits,odoo_tool_errors

tool=mcp._tool_manager.get_tool('search_records')
tool.fn=lambda **kw:{'success':True,'count':1,'result':[{'id':1,'datas':'x'*(2*1024*1024+100)}]}
installed=odoo_result_limits.install(mcp)
again=odoo_result_limits.install(mcp)
odoo_tool_errors.install(mcp)
async def call():
 return await tool.run({'model':'res.partner'},None,convert_result=True)
result=asyncio.run(call())
text=json.loads(result.content[0].text)
small={'success':True,'count':1,'result':[{'id':1,'name':'Synthetic'}]}
small_unchanged=odoo_result_limits.check_result_size(small) is small
print(json.dumps({'installed':installed,'again':again,'is_error':result.is_error,
 'text':{'success':text.get('success'),'result_bytes':text.get('result_bytes'),
         'max_result_bytes':text.get('max_result_bytes'),'largest_fields':text.get('largest_fields')},
 'small_unchanged':small_unchanged}))
''')
    assert value['installed'] == ['read_record', 'search_records']
    assert value['again'] == []
    assert value['is_error'] is True
    assert value['text']['success'] is False
    assert value['text']['result_bytes'] > 2 * 1024 * 1024
    assert value['text']['max_result_bytes'] == 2 * 1024 * 1024
    assert value['text']['largest_fields'][0] == 'datas'
    assert value['small_unchanged'] is True
