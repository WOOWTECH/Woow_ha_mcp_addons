"""Odoo child failures must be MCP failures, including SDK 2 output-schema wrapping.

The child venv and patched wheel are installed by packaging/unit.sh. No Odoo backend is contacted.
"""

from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_success_false_is_error_for_named_and_wrapped_odoo_tools():
    script = r'''
import asyncio
import json
import jsonschema
from odoo_mcp.server import mcp
from odoo_tool_errors import as_error_result, install, scrub_error_text
from bounded_tools import BoundedTools
from tool_error_text import keep_error_text

cases = {'search_records': {'model': 'res.partner'},
         'execute_method': {'model': 'res.partner', 'method': 'write'}}
for name in cases:
    tool = mcp._tool_manager.get_tool(name)
    def fake_failure(**_kwargs):
        return {'success': False, 'error': 'FAKE_BACKEND_REFUSED'}
    tool.fn = fake_failure

installed = install(mcp)
again = install(mcp)
workers = BoundedTools(mcp, capacity=1)
keep_error_text(mcp)

async def verify():
    out = {}
    for name, arguments in cases.items():
        tool = mcp._tool_manager.get_tool(name)
        result = await tool.run(arguments, None, convert_result=True)
        jsonschema.validate(result.structured_content, tool.output_schema)
        out[name] = {'is_error': result.is_error,
                     'structured': result.structured_content,
                     'text': json.loads(result.content[0].text)}
    return out

try:
    actual = asyncio.run(verify())
    failure = {'success': False, 'tool': 'fake', 'error': 'FAKE_BACKEND_REFUSED'}
    schemas = all(jsonschema.Draft202012Validator(tool.output_schema).is_valid(
        as_error_result(failure, wrap=bool(tool.fn_metadata.wrap_output)).structured_content)
        for tool in mcp._tool_manager.list_tools() if tool.name != 'woow_backend_probe')
    ok = {'success': True, 'count': 0}
    print(json.dumps({'actual': actual, 'all_41_schemas_valid': schemas,
        'tool_count': len(mcp._tool_manager.list_tools()), 'installed_count': len(installed),
        'again': again, 'success_unchanged': as_error_result(ok) is ok,
        'traceback': scrub_error_text("Traceback (most recent call last):\\n  File 'x', line 1\\nValueError: fake") }))
finally:
    workers.close()
'''
    completed = subprocess.run(
        [str(ROOT / "apps/odoo/.venv/bin/python"), "-c", script],
        cwd=ROOT, text=True, capture_output=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONPATH": str(ROOT / "apps/runtime")},
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["tool_count"] == 41
    assert result["installed_count"] == 41 and result["again"] == []
    assert result["all_41_schemas_valid"] and result["success_unchanged"]
    assert result["traceback"] == "Odoo server error: ValueError: fake"
    for name in ("search_records", "execute_method"):
        reply = result["actual"][name]
        assert reply["is_error"] is True
        assert reply["text"] == {"success": False, "error": "FAKE_BACKEND_REFUSED"}
        expected = {"result": reply["text"]} if name == "execute_method" else reply["text"]
        assert reply["structured"] == expected
    assert "odoo_tool_errors.install(mcp)" in (ROOT / "apps/odoo/launch.py").read_text()
