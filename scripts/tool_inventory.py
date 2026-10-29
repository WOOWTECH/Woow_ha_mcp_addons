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
from mcp_admin_core.products import TOOLS, fresh_write_grants
from n8n_adapter import TOOLS as N8N_TOOLS

POLICIES = {**TOOLS, 'n8n': N8N_TOOLS}

# The reviewed classification lives in the runtime now (0.2.0: it decides the write grants of the full surface).
from mcp_admin_core.surface import MIXED, OPERATION_READS, READ, UNCERTAIN, WRITE  # noqa: E402

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
    for relative in ('apps/n8n/backend_policy.cjs',
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
            selector = tool.selector if tool else None
            for parameter, values in evidence['operations'].items():
                if name in OPERATION_READS and parameter == selector:
                    operation_effects[parameter] = {v: ('read' if v in OPERATION_READS[name] else 'write') for v in values}
                else:
                    operation_effects[parameter] = {v: categories[name] for v in values}
            if name in ('execute_method', 'call_model_method', 'n8n_explore_node_resources'):
                operation_effects['arbitrary-method'] = {'*': 'write'}
            dispatch = {}
            full = supported and tool.child_schema
            properties = tool.arguments.model_json_schema().get('properties', {}) if supported and not full else {}
            for parameter, values in evidence['operations'].items():
                accepted = properties.get(parameter, {})
                choices = accepted.get('enum', [accepted['const']] if 'const' in accepted else [])
                dispatch[parameter] = {}
                for operation in values:
                    # 0.2.0: a full-surface tool forwards every value to the child, which validates it.
                    allowed = supported and (full or operation in choices)
                    writer = allowed and (tool.write or parameter == tool.selector and operation in tool.write_operations)
                    dispatch[parameter][operation] = {
                        'supported_explicit': allowed,
                        'default_readonly': allowed and not writer,
                        'write_grant': (name if tool.write else f'{name}:{operation}') if writer else None,
                        'deferred_reason': None if allowed else DEFERRED_BRANCHES.get(name, review[product][name]),
                    }
            status = ('supported-full' if full else 'supported-bounded') if supported else 'temporarily-unsupported'
            if full:
                enable = '預設開啟（新安裝與從 0.1.x 升級）；管理面板可逐一停用工具或撤銷寫入 grant；disabled 優先'
            elif supported:
                enable = ('PUT /api/policy (HA admin+CSRF): enabled_write_tools 選取精確 grant；disabled 優先；舊全域開關僅保留兩個既有 writer'
                          if tool.grants(name) else 'authorized-admin-policy: remove from disabled')
            else:
                enable = '不可由 GUI 啟用；需 source/policy/test review'
            entries.append({'name': name, **evidence, 'effect': categories[name], 'operation_effects': operation_effects,
                'dispatch_operations': dispatch,
                'status': status,
                # On a new state and on every state migrated to schema 4 (0.2.0): every write grant on (Odoo Manage none).
                'default_enabled': supported and set(tool.grants(name)) <= set(fresh_write_grants(product)),
                'write_grants': tool.grants(name) if supported else [],
                'operation_parameter': tool.selector if supported else None,
                'enable': enable,
                'reason': '子程序完整工具（0.2.0）：參數由子程序驗證，輸入原樣轉送，輸出不再投影。' if full else review[product][name],
                # A full-surface tool has no local argument model: tools/list carries the child's own inputSchema.
                'accepted_schema': None if full or not supported else tool.arguments.model_json_schema(),
                'tests': ['tests/test_tool_inventory.py'] + (['tests/test_full_surface.py', 'tests/test_real_products.py']
                                                             if full else [])})
        products[product] = {'upstream_count': len(entries), 'supported_count': len(POLICIES[product]), 'tools': entries}
    return {'format': 3, 'scope': '0.2.0 full child surface (owner decision 2026-10-15); Odoo Manage (retired) keeps the 0.1.x bounded surface; not HA/release acceptance',
            'source_digests': digests, 'products': products}


def markdown(data):
    lines = ['# 八類完整 upstream 工具對照（0.2.0 完整版）', '',
             '由 `scripts/tool_inventory.py` 產生；Python 是 decorator AST（含條件註冊；Nextcloud 是 `_functions()` 註冊表 AST），n8n 是 pinned runtime 定義 export，不冒充全部都曾由 MCP tools/list 觀察。',
             '0.2.0（負責人 2026-10-15 決定）：七支（Odoo、n8n、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud）開放子程序的全部工具（supported-full），tools/list 用子程序自己的 inputSchema（經 provider-safe 正規化），tools/call 參數原樣轉送、由子程序驗證；已下架的 Odoo Manage 維持 0.1.x 有界版（supported-bounded）。',
             '寫入 grants：寫入工具是工具名，混合工具是 tool:operation；新安裝與從 0.1.x 升級（state schema 4 遷移一次）時全部開啟，管理員可在面板逐一撤銷或停用工具（disabled 優先）。read 表示 wrapper 沒有刻意業務寫入，不保證無敏感資料、cache/log/auth 活動；未驗證副作用（unverified-side-effects）以寫入 grant 管理。',
             '管理需 HA 可信 admin role。子程序名單之外的工具（升級後上游新增者）在此重新分類前一律拒絕。',
             '來源版本／修改／授權見 `provenance/six-runtimes.md`。每次升版須 drift test 及重新審查，不可自動允許新工具。', '']
    for product, group in data['products'].items():
        lines += [f"## {product}：上游 {group['upstream_count']}／開放 {group['supported_count']}", '',
                  '| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 寫入 grants | 理由／剩餘工作 | 測試 |', '|---|---|---|---|---|---|---|']
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
