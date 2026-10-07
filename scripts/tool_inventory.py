"""Source inventory, not a permissive tool registry. Run --write after review only.

Python decorators are parsed, not imported. n8n's two installed export arrays are
loaded in a clean Node process (source-defined runtime inventory, no MCP/backend).
Every name must have an explicit effect classification; additions fail closed.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
from mcp_admin_core.products import TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS

POLICIES = {**TOOLS, 'n8n': N8N_TOOLS}

READ = {
 'odoo': 'accounting_health_across_instances accounting_health_summary aggregate_across_instances aggregate_records analyze_upgrade_log build_domain business_pack_report data_quality_report diagnose_access diagnose_odoo_call fit_gap_report generate_json2_payload get_async_task get_model_fields get_odoo_profile health_check inspect_model_relationships knowledge_stats list_async_tasks list_instances list_models lookup_model_history read_attachment read_record receivable_payable_aging scan_addons_source schema_catalog search_across_instances search_employee search_holidays search_knowledge search_records upgrade_risk_report',
 'odoo-manage': 'aggregate_records get_record list_models list_resource_templates search_records',
 'hermes': 'hermes_inspect',
 'opendesign': 'get_file_info get_project health list_agents list_connectors list_plugins list_project_files list_projects list_runs list_skills read_file version',
 'emqx': 'emqx_authz_settings emqx_broker_stats emqx_client_subscriptions emqx_cluster_status emqx_get_client emqx_get_retained emqx_get_rule_metrics emqx_get_trace_log emqx_list_actions emqx_list_alarms emqx_list_authn emqx_list_authz_sources emqx_list_banned emqx_list_clients emqx_list_connectors emqx_list_listeners emqx_list_retained emqx_list_rules emqx_list_subscriptions emqx_list_topics emqx_list_traces emqx_metrics_current emqx_metrics_history emqx_node_detail emqx_prometheus_stats',
 'litellm': 'litellm_global_spend_report litellm_health_readiness litellm_key_info litellm_list_keys litellm_list_models litellm_list_plugins litellm_list_teams litellm_list_users litellm_model_group_info litellm_model_info litellm_plugin_info litellm_skill_hub litellm_spend_logs litellm_team_info litellm_user_info',
 'nextcloud': 'get_file_content get_file_tree list_calendars list_tasks read_text_file',
 'n8n': 'tools_documentation search_nodes get_node validate_node get_template search_templates validate_workflow n8n_get_workflow n8n_list_workflows n8n_validate_workflow n8n_health_check n8n_list_catalog',
}
WRITE = {
 'odoo': 'cancel_async_task chatter_post execute_approved_write index_knowledge submit_async_task validate_write preview_write execute_method',
 'odoo-manage': 'create_record delete_record post_message update_record call_model_method',
 'hermes': 'hermes_chat',
 'opendesign': 'create_project delete_project send_message',
 'emqx': 'emqx_ban emqx_client_subscribe emqx_client_unsubscribe emqx_create_trace emqx_delete_retained emqx_delete_trace emqx_kick_client emqx_publish emqx_publish_bulk emqx_toggle_rule emqx_unban',
 'nextcloud': 'create_text_file delete_file_checked update_text_file upload_file',
 'litellm': 'litellm_health litellm_token_counter litellm_spend_calculate litellm_add_model litellm_block_key litellm_chat_completion litellm_create_team litellm_create_user litellm_delete_key litellm_delete_model litellm_delete_plugin litellm_delete_team litellm_delete_user litellm_disable_plugin litellm_enable_plugin litellm_generate_key litellm_regenerate_key litellm_register_plugin litellm_team_member_add litellm_team_member_delete litellm_unblock_key litellm_update_key litellm_update_model litellm_update_team litellm_update_user',
 'n8n': 'n8n_manage_agents n8n_explore_node_resources n8n_create_workflow n8n_update_full_workflow n8n_update_partial_workflow n8n_delete_workflow n8n_autofix_workflow n8n_test_workflow n8n_deploy_template',
}
MIXED = {
 'odoo': '', 'odoo-manage': '',
 'hermes': 'hermes_config hermes_cron hermes_gateway hermes_mcp hermes_model hermes_session hermes_skill hermes_tools hermes_webhook',
 'opendesign': '', 'emqx': 'emqx_manage_authn_users emqx_manage_authz_rules', 'litellm': '',
 'n8n': 'n8n_executions n8n_evaluations n8n_workflow_versions n8n_manage_datatable n8n_manage_folders n8n_manage_credentials',
}
# These handlers are not proven non-mutating by the wrapper. Explicitly NOT read.
UNCERTAIN = {'emqx': 'emqx_test_rule_sql', 'litellm': '',
             'n8n': 'n8n_audit_instance'}

# Exact source operation splits, only used for inventory (never authorization).
OPERATION_READS = {
 'hermes_config': ['get'], 'hermes_cron': ['list'], 'hermes_gateway': ['status'],
 'hermes_mcp': ['list'], 'hermes_model': ['info', 'list_providers'],
 'hermes_session': ['list', 'get'], 'hermes_skill': ['list'], 'hermes_tools': ['list'],
 'hermes_webhook': ['list'], 'emqx_manage_authn_users': ['read'], 'emqx_manage_authz_rules': ['read'],
 'n8n_executions': ['get', 'list'], 'n8n_evaluations': ['list_runs', 'get_run', 'list_cases'],
 'n8n_workflow_versions': ['list', 'get', 'diff'],
 'n8n_manage_datatable': ['listTables', 'getTable', 'getRows'],
 'n8n_manage_folders': ['list', 'get'], 'n8n_manage_credentials': ['list', 'get', 'getSchema'],
 'n8n_manage_agents': ['reference', 'search', 'get', 'validate', 'versions', 'discover_assets'],
}

def source_inventory():
    inventory = {}
    digests = {}
    for product in TOOLS:
        app = ROOT / 'apps' / product
        if product in ('odoo', 'odoo-manage'):
            package = 'odoo_mcp' if product == 'odoo' else 'mcp_server_odoo'
            files = sorted((app / '.venv/lib/python3.13/site-packages' / package).glob('*.py'))
        else:
            files = sorted((app / 'vendor').rglob('*.py'))
        rows = {}
        for file in files:
            relative = str(file.relative_to(ROOT))
            data = file.read_bytes()
            digests[relative] = hashlib.sha256(data).hexdigest()
            tree = ast.parse(data)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in node.decorator_list:
                    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == 'tool'):
                        continue
                    name = next((k.value.value for k in dec.keywords if k.arg == 'name' and isinstance(k.value, ast.Constant)), node.name)
                    assert name not in rows
                    operations = {}
                    for compare in ast.walk(node):
                        if not isinstance(compare, ast.Compare) or not isinstance(compare.left, ast.Name) or compare.left.id not in ('action', 'operation', 'target'):
                            continue
                        vals = []
                        for comp in compare.comparators:
                            if isinstance(comp, ast.Constant) and isinstance(comp.value, str): vals.append(comp.value)
                            elif isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                                vals.extend(v.value for v in comp.elts if isinstance(v, ast.Constant) and isinstance(v.value, str))
                        operations.setdefault(compare.left.id, set()).update(vals)
                    rows[name] = {'source': relative, 'line': node.lineno, 'evidence': 'python-decorator-AST',
                                  'operations': {k: sorted(v) for k, v in operations.items()},
                                  'source_signature': ast.unparse(node.args)}
            if product == 'nextcloud' and file.name == 'tools.py':
                # No decorators: register_tools() adds Tool.from_function for the nested handlers that _functions()
                # returns by name (READONLY/ALLOW_DELETE/DISABLED_TOOLS only remove some). The add-on's private
                # woow_backend_probe is added in server.py, not here, and is never inventoried as an upstream tool.
                [functions] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_functions']
                handlers = {n.name: n for n in functions.body if isinstance(n, ast.AsyncFunctionDef)}
                [returned] = [n.value for n in functions.body if isinstance(n, ast.Return)]
                assert isinstance(returned, ast.Dict) and [k.value for k in returned.keys] == [v.id for v in returned.values]
                for key in returned.keys:
                    node = handlers[key.value]
                    assert key.value not in rows
                    rows[key.value] = {'source': relative, 'line': node.lineno, 'evidence': 'python-registration-AST',
                                       'operations': {}, 'source_signature': ast.unparse(node.args)}
        inventory[product] = rows
    base = ROOT / 'apps/n8n/node_modules/n8n-mcp/dist/mcp'
    code = "const p=process.argv[1]; const a=require(p+'/tools.js').n8nDocumentationToolsFinal; const b=require(p+'/tools-n8n-manager.js').n8nManagementTools; console.log(JSON.stringify([a,b]));"
    arrays = json.loads(subprocess.check_output(['node', '-e', code, str(base)], env={'PATH': '/usr/bin:/bin'}, cwd=ROOT))
    rows = {}
    for tools, filename in zip(arrays, ('tools.js', 'tools-n8n-manager.js')):
        file = base / filename
        relative = str(file.relative_to(ROOT))
        digests[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
        for tool in tools:
            rows[tool['name']] = {'source': relative, 'evidence': 'installed-runtime-definition-export',
                'source_schema': tool['inputSchema'],
                'operations': {k: v['enum'] for k, v in tool['inputSchema'].get('properties', {}).items()
                               if k in ('action', 'mode', 'method', 'kind', 'searchMode', 'methodType') and 'enum' in v}}
    inventory['n8n'] = rows
    # Handler changes also require re-review, not only renamed advertisements.
    for file in sorted(base.glob('*.js')) + [base.parent / 'services/n8n-api-client.js']:
        digests[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    # B1 local validators and workflow creation depend on these pinned helpers.
    for file in sorted((base.parent / 'services').glob('*valid*.js')):
        digests[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    for relative in ('apps/n8n/backend_policy.cjs', 'apps/n8n/metadata_reads.cjs',
                     'apps/n8n/node_modules/n8n-mcp/dist/utils/npm-version-checker.js'):
        file = ROOT / relative
        digests[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
    # New local transport/dispatch adapters are part of the reviewed runtime too.
    for file in sorted((ROOT / 'apps/runtime').glob('*.py')) + sorted((ROOT / 'apps').glob('*/launch.py')):
        digests[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    return inventory, digests


# Remaining branches of supported mixed tools are explicitly not granted.
DEFERRED_BRANCHES = {
    'hermes_inspect': 'config/model/all 尚含未受限設定或模型資料；需逐 target 正向投影。',
    'hermes_model': 'set 會更改模型/provider 且回原始資料；需 provider 路由 schema、輸出與 fake mutation 測試。',
    'hermes_session': 'get 回私人 session/messages；需獨立內容權限，不使用 metadata list grant。',
    'hermes_cron': 'create/update/resume/trigger 可配置或啟動 agent prompt；需獨立 agent execution 與 schedule/schema/費用範圍。',
    'n8n_get_workflow': 'minimal 以外可能回 node parameters/credentials/execution 或完整 graph；需內容投影。',
    'n8n_manage_folders': 'move/delete 有 reparent/搬移/封存 workflows 的副作用，仍拒絕；get 僅有界 metadata、明確 project/folder IDs。',
    'n8n_executions': 'get 含私人 payload；delete/run/retry 未授權；僅 list includeData=false 有界 metadata。',
    'n8n_health_check': 'diagnostic 含設定、URL、env、metrics；只開 status，無 npm/official-MCP/version 查詢。',
    'n8n_list_catalog': 'projects/personal/official-MCP fallback 仍拒絕；只開 public API tags 第一頁最多250。',
    'get_node': '其他 mode 尚無 bounded schema 與 sourcehandler 正反測試；本批只測 local info minimal/standard。',
    'search_nodes': '舊 bounded schema 未開放顯式 mode；保留 pinned handler 的省略預設，不推測其他查詢模式。',
}


def build():
    inventory, digests = source_inventory()
    products = {}
    review = json.loads((ROOT / 'docs/tool-review.json').read_text())
    for product, rows in inventory.items():
        assert set(rows) == set(review[product]), 'every source tool needs an individual review row'
        categories = {}
        for effect, mapping in [('read', READ), ('write', WRITE), ('mixed', MIXED), ('unverified-side-effects', UNCERTAIN)]:
            for name in mapping.get(product, '').split():
                assert name not in categories
                categories[name] = effect
        assert set(rows) == set(categories), (product, set(rows) ^ set(categories))
        entries = []
        for name, evidence in sorted(rows.items()):
            tool = POLICIES[product].get(name)
            supported = tool is not None
            operation_effects = {}
            selector = next((k for k in ('action', 'operation', 'mode') if k in evidence['operations']), None)
            for parameter, values in evidence['operations'].items():
                if categories[name] == 'mixed' and name in OPERATION_READS and parameter == selector:
                    operation_effects[parameter] = {v: ('read' if v in OPERATION_READS[name] else 'write') for v in values}
                else:
                    operation_effects[parameter] = {v: categories[name] for v in values}
            if name in ('execute_method', 'call_model_method', 'n8n_explore_node_resources'):
                operation_effects['arbitrary-method'] = {'*': 'write'}
            dispatch = {}
            properties = tool.arguments.model_json_schema().get('properties', {}) if tool else {}
            for parameter, values in evidence['operations'].items():
                accepted = properties.get(parameter, {})
                choices = accepted.get('enum', [accepted['const']] if 'const' in accepted else [])
                dispatch[parameter] = {}
                for operation in values:
                    allowed = supported and operation in choices
                    writer = allowed and (tool.write or parameter == tool.selector and operation in tool.write_operations)
                    dispatch[parameter][operation] = {
                        'supported_explicit': allowed,
                        'default_readonly': allowed and not writer,
                        'write_grant': (name if tool.write else f'{name}:{operation}') if writer else None,
                        'deferred_reason': None if allowed else DEFERRED_BRANCHES.get(name, review[product][name]),
                    }
            entries.append({'name': name, **evidence, 'effect': categories[name], 'operation_effects': operation_effects,
                'dispatch_operations': dispatch,
                'status': 'supported-bounded' if supported else 'temporarily-unsupported',
                'default_enabled': supported and not tool.write,
                'write_grants': tool.grants(name) if supported else [],
                'operation_parameter': tool.selector if supported else None,
                'enable': ('PUT /api/policy (HA admin+CSRF): enabled_write_tools 選取精確 grant；disabled 優先；舊全域開關僅保留兩個既有 writer' if tool.grants(name) else 'authorized-admin-policy: remove from disabled') if supported else '不可由 GUI 啟用；需 source/policy/test review',
                'reason': review[product][name],
                'accepted_schema': tool.arguments.model_json_schema() if supported else None,
                'tests': ['tests/test_tool_inventory.py'] + (['tests/test_b3_n8n_policy.py', 'tests/test_b3_n8n_runtime.py', 'tests/test_b3_n8n_boundaries.py'] if supported and product == 'n8n' and name in ('n8n_list_catalog', 'n8n_executions', 'n8n_health_check', 'n8n_manage_folders') else []) + (['tests/test_b2_odoo_policy.py', 'tests/test_b2_odoo_runtime.py', 'tests/test_b2_odoo_scope.py'] if supported and product == 'odoo' and name in ('schema_catalog', 'inspect_model_relationships', 'data_quality_report') else []) + (['tests/test_batch2_policy.py', 'tests/test_batch2_bounds.py', 'tests/test_batch2_runtime.py'] if supported and product in ('odoo', 'odoo-manage', 'n8n') and name in ('build_domain', 'generate_json2_payload', 'diagnose_odoo_call', 'aggregate_records', 'list_resource_templates', 'post_message', 'validate_node', 'validate_workflow', 'n8n_create_workflow') else []) + ((['tests/test_expansion_security.py', 'tests/test_expansion_runtime.py', 'tests/test_stream_error_redaction.py'] if product != 'n8n' else ['tests/test_expansion_runtime.py', 'tests/test_schema_defaults.py', 'tests/test_real_n8n.py']) if supported else []) + (['tests/test_nextcloud_child.py'] if supported and product == 'nextcloud' else [])})
        products[product] = {'upstream_count': len(entries), 'supported_count': len(POLICIES[product]), 'tools': entries}
    return {'format': 2, 'scope': 'W2b plus BATCH2 B1/B2/B3 bounded expansion; B3 pending SPEC then NEW SECURITY; not complete product/HA/release acceptance',
            'source_digests': digests, 'products': products}


def markdown(data):
    lines = ['# 八類完整 upstream 工具對照（W2b bounded）', '',
             '由 `scripts/tool_inventory.py` 產生；Python 是 decorator AST（含條件註冊；Nextcloud 是 `_functions()` 註冊表 AST），n8n 是 pinned runtime 定義 export，不冒充全部都曾由 MCP tools/list 觀察。',
             '每個工具的精確參數／default／允許 operation 見 `tool-surface.json` 的 accepted_schema。混合工具逐 operation 授權；enabled_write_tools 使用 exact tool 或 tool:operation；舊 writes_enabled 不授權新增 writer。來源 signature/schema 與本地 accepted_schema 分列。',
             'read 表示 wrapper 沒有刻意業務寫入，不保證無敏感資料、cache/log/auth 活動；未驗證副作用明列，不按 GET/annotation 猜安全。',
             '管理需 HA 可信 admin role；只有 n8n 接正式 provider，其餘七類維持 fail closed；不新增 UI。所有新增 writers 預設關閉；未支援工具即使 writes_enabled=true 仍拒絕。',
             '來源版本／修改／授權見 `provenance/six-runtimes.md`。每次升版須 drift test 及重新審查，不可自動允許新工具。', '']
    for product, group in data['products'].items():
        lines += [f"## {product}：上游 {group['upstream_count']}／本地 bounded {group['supported_count']}", '',
                  '| exact tool | 來源副作用 | 支援／預設唯讀 | operations（來源） | 寫入 grants | 理由／剩餘工作 | 測試 |', '|---|---|---|---|---|---|---|']
        for tool in group['tools']:
            operations = json.dumps(tool['operation_effects'], ensure_ascii=False)
            if tool['dispatch_operations']:
                operations += '<br>本地：' + json.dumps(tool['dispatch_operations'], ensure_ascii=False)
            lines.append(f"| `{tool['name']}` | {tool['effect']} | {tool['status']} / {'on' if tool['default_enabled'] else 'off'} | {operations} | {', '.join(tool['write_grants']) or '—'} | {tool['reason']} {tool['enable']} | {', '.join(tool['tests'])} |")
        lines.append('')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    data = build()
    if sys.argv[1:] == ['--write']:
        (ROOT / 'docs/tool-surface.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
        (ROOT / 'docs/tool-surface.md').write_text(markdown(data))
    else:
        expected = json.loads((ROOT / 'docs/tool-surface.json').read_text())
        assert data == expected, 'inventory/source/policy drift: review before regenerating'
        assert markdown(data) == (ROOT / 'docs/tool-surface.md').read_text()
        print({k: (v['upstream_count'], v['supported_count']) for k, v in data['products'].items()})
