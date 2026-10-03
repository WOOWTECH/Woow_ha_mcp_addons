"""Public JSON schemas and normalized dispatch agree on reviewed examples."""
import json
from pathlib import Path
import subprocess

from mcp_admin_core.products import TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_security import CASES

ROOT = Path(__file__).resolve().parents[1]


def test_actual_public_schemas_match_conditional_dispatch_and_defaults():
    cases = []
    for product, name, args in CASES:
        tool = (N8N_TOOLS if product == 'n8n' else TOOLS[product])[name]
        normalized = tool.arguments.model_validate(args).model_dump(mode='json')
        assert normalized == tool.arguments.model_validate(normalized).model_dump(mode='json')
        schema = tool.arguments.model_json_schema()
        assert schema['additionalProperties'] is False
        cases.extend([(schema, args, True), (schema, normalized, True), (schema, {**args, 'unreviewed': 'x'}, False)])
    for name,args in [('hermes_skill', {'action': 'list', 'name': 'ignored'}),
                      ('hermes_tools', {'action': 'enable'}),
                      ('hermes_session', {'action': 'list', 'session_id': 'ignored'}),
                      ('hermes_cron', {'action': 'pause'}),
                      ('hermes_cron', {'enabled': False})]:
        cases.append((TOOLS['hermes'][name].arguments.model_json_schema(), args, False))
    cases.append((N8N_TOOLS['n8n_manage_folders'].arguments.model_json_schema(), {'action': 'list', 'name': 'ignored'}, False))
    for clause in [['password', '=', 'x'], ['id', '=', True], ['active', 'ilike', 'x']]:
        cases.append((TOOLS['odoo']['search_records'].arguments.model_json_schema(),
                      {'model': 'res.partner', 'fields': ['name'], 'domain': [clause]}, False))
    # Use already locked child dependency, no root dependency addition/install.
    probe = subprocess.run([str(ROOT/'apps/odoo/.venv/bin/python'), '-c', '''
import json, sys
from jsonschema import Draft202012Validator
for schema, args, expected in json.load(sys.stdin):
    Draft202012Validator.check_schema(schema)
    actual = Draft202012Validator(schema).is_valid(args)
    assert actual == expected, (schema['title'], args, actual, expected)
print('SCHEMA_CASES_PASS')
'''], input=json.dumps(cases), text=True, capture_output=True, timeout=10,
        env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert probe.returncode == 0, probe.stderr
    assert 'SCHEMA_CASES_PASS' in probe.stdout
