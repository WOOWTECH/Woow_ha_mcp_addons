"""Independent fixed effect/name baselines: --write alone cannot approve drift."""
import hashlib
import json
from pathlib import Path

from mcp_admin_core.native_inventory import NAMES
from mcp_admin_core.products import TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_runtime import READS, WRITES
from test_batch2_policy import CASES as B1_CASES

ROOT = Path(__file__).resolve().parents[1]


def test_effect_classification_review_baseline():
    data = json.loads((ROOT/'docs/tool-surface.json').read_text())
    effects = {p: {t['name']: t['effect'] for t in g['tools']} for p,g in data['products'].items()}
    assert hashlib.sha256(json.dumps(effects, sort_keys=True).encode()).hexdigest() == '71e02d8dceff5091e5c486702d4de2e407b2887d76aff03013ed1c2e21a3426d'
    operations = {p: {t['name']: t['operation_effects'] for t in g['tools']} for p,g in data['products'].items()}
    assert hashlib.sha256(json.dumps(operations, sort_keys=True).encode()).hexdigest() == '1cf8a2c9d12f58d046d0cc7d540059ddbc559cfda72fd3ef866d447d23a502fc'
    for p, name in [('odoo', 'execute_method'), ('odoo-manage', 'call_model_method'),
                    ('hermes', 'hermes_chat'), ('opendesign', 'send_message'),
                    ('litellm', 'litellm_chat_completion'), ('litellm', 'litellm_health'),
                    ('litellm', 'litellm_spend_calculate'), ('n8n', 'n8n_manage_agents'),
                    ('n8n', 'n8n_explore_node_resources')]:
        assert effects[p][name] == 'write'
    for product, names in NAMES.items():
        assert set(names) == set(effects[product])


def test_native_update_checker_source_and_no_network_no_cache(tmp_path):
    import subprocess
    for product in ('emqx', 'litellm'):
        base = ROOT/'apps'/product/'.venv/lib/python3.13/site-packages/fastmcp'
        assert hashlib.sha256((base/'settings.py').read_bytes()).hexdigest() == 'f96cd4e29b0d56e1f24c522ea977170f1b6efbdb88dc59023b1e9fa9afe3397c'
        assert hashlib.sha256((base/'utilities/version_check.py').read_bytes()).hexdigest() == 'ce36361da496e1fd3d1a3ba7dd5e932f269e242fd93cf7f5e95bd001d0e280ef'
        result = subprocess.run([str(ROOT/'apps'/product/'.venv/bin/python'), '-c', '''
import fastmcp.utilities.version_check as check
import httpx
from pathlib import Path
import os

def forbidden(*args, **kwargs):
    raise AssertionError('update check must never access HTTP/cache')
httpx.get = forbidden
check._read_cache = forbidden
check._write_cache = forbidden
assert check.check_for_newer_version() is None
assert not list(Path(os.environ['HOME']).iterdir())
'''], env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path),
           'PYTHONDONTWRITEBYTECODE': '1', 'FASTMCP_CHECK_FOR_UPDATES': 'off'},
           capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr


def test_legacy_writer_documentation_matches_authorization():
    ledger = json.loads((ROOT/'docs/tool-review.json').read_text())
    inventory = json.loads((ROOT/'docs/tool-surface.json').read_text())
    for product, name in [('n8n', 'n8n_delete_workflow'), ('opendesign', 'delete_project')]:
        reason = ledger[product][name]
        assert 'writes_enabled=true 或 exact grant' in reason
        assert 'disabled 永遠優先' in reason
        assert '一般開關不授權' not in reason
        row = next(t for t in inventory['products'][product]['tools'] if t['name'] == name)
        assert reason in json.dumps(row, ensure_ascii=False)


def test_every_added_tool_has_real_handler_positive_case():
    policies = {**TOOLS, 'n8n': N8N_TOOLS}
    assert {(p,n) for p,tools in policies.items() for n,t in tools.items() if t.legacy_write} == {
        ('n8n', 'n8n_delete_workflow'), ('opendesign', 'delete_project')}
    old = {
        'odoo': {'health_check', 'list_models'}, 'odoo-manage': {'list_models'},
        'hermes': {'hermes_inspect', 'hermes_skill', 'hermes_tools', 'hermes_gateway', 'hermes_model'},
        'opendesign': {'health','version','list_agents','list_projects','list_plugins','list_skills','get_project','list_project_files','get_file_info','delete_project'},
        'emqx': {'emqx_cluster_status','emqx_broker_stats','emqx_metrics_current'},
        'litellm': {'litellm_list_models','litellm_health_readiness'},
        'n8n': {'tools_documentation','search_nodes','n8n_list_workflows','n8n_delete_workflow'},
    }
    for product, tools in {**TOOLS, 'n8n': N8N_TOOLS}.items():
        b1_cases = [(name, args) for p, name, args in B1_CASES if p == product]
        actual_cases = {name for name, _ in READS[product]+WRITES[product]+b1_cases}
        assert set(tools)-old[product] <= actual_cases
        # Every new operation grant has a real writer case, not just tools/list.
        covered = {name if tools[name].write else f'{name}:{args[tools[name].selector]}'
                   for name,args in WRITES[product]+[(n,a) for n,a in b1_cases if tools[n].write]}
        for name,tool in tools.items():
            if not tool.legacy_write:
                assert set(tool.grants(name)) <= covered
