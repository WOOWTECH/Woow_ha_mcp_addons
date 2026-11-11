"""Source inventory, not a permissive tool registry. Run --write after review only.

Python decorators and Headscale's programmatic registry are parsed, not imported.
n8n's two installed export arrays are loaded in a clean Node process
(source-defined runtime inventory, no MCP/backend). Every name must have an
explicit effect classification; additions fail closed.
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
from mcp_admin_core.surface import MIXED, OPERATION_READS, READ, SELECTORS, UNCERTAIN, WRITE  # noqa: E402


HEADSCALE_VENDOR = 'apps/headscale/vendor/headscale_mcp_server'


def _assignment(tree, name):
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == name]
    assert len(assignments) == 1, (name, 'expected one literal assignment')
    assert sum(isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store)
               for node in ast.walk(tree)) == 1, (name, 'reassigned')
    return assignments[0].value


def _string(node):
    assert isinstance(node, ast.Constant) and type(node.value) is str, 'expected a literal string'
    return node.value


def _literal_dict(node):
    assert isinstance(node, ast.Dict), 'expected a literal dictionary'
    keys = [_string(key) for key in node.keys]
    assert len(keys) == len(set(keys)), ('duplicate keys', keys)
    return dict(zip(keys, node.values))


def _headscale_registration(registry, server):
    # Require the source registry to derive exactly from the two literal maps.
    for name in ('_GROUPS', '_FIXED'):
        for node in ast.walk(registry):
            if isinstance(node, (ast.Subscript, ast.Attribute)) and isinstance(node.value, ast.Name) and node.value.id == name:
                assert isinstance(node, ast.Attribute) and node.attr == 'items', (name, 'dynamic registry access')
    loops = {}
    for node in ast.walk(registry):
        if (isinstance(node, ast.For) and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Attribute) and node.iter.func.attr == 'items'
                and isinstance(node.iter.func.value, ast.Name) and node.iter.func.value.id in ('_GROUPS', '_FIXED')):
            loops.setdefault(node.iter.func.value.id, []).append(node)
    assert {name: len(found) for name, found in loops.items()} == {'_GROUPS': 1, '_FIXED': 1}
    appends = [node for node in ast.walk(registry) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == '_registry' and node.func.attr == 'append']
    assert len(appends) == 2
    for found in loops.values():
        calls = [node for node in ast.walk(found[0]) if node in appends]
        assert len(calls) == 1 and len(calls[0].args) == 1
        assert isinstance(calls[0].args[0], ast.Call) and isinstance(calls[0].args[0].func, ast.Name)
        assert calls[0].args[0].func.id == 'ToolSpec'
    registry_value = _assignment(registry, 'TOOL_REGISTRY')
    assert (isinstance(registry_value, ast.Call) and isinstance(registry_value.func, ast.Name)
            and registry_value.func.id == 'tuple' and len(registry_value.args) == 1
            and isinstance(registry_value.args[0], ast.Name) and registry_value.args[0].id == '_registry')

    # The child exposes only this loop's ToolSpec names; a second add_tool path
    # must be reviewed before the source inventory can be regenerated.
    additions = [node for node in ast.walk(server) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_tool']
    loops = [node for node in ast.walk(server) if isinstance(node, ast.For)
             and isinstance(node.target, ast.Name) and node.target.id == 'spec'
             and isinstance(node.iter, ast.Name) and node.iter.id == 'TOOL_REGISTRY']
    assert len(additions) == len(loops) == 1 and additions[0] in ast.walk(loops[0])
    [tool] = additions[0].args
    assert isinstance(tool, ast.Call) and isinstance(tool.func, ast.Name) and tool.func.id == 'NativeTool'
    name = next((keyword.value for keyword in tool.keywords if keyword.arg == 'name'), None)
    assert isinstance(name, ast.Attribute) and isinstance(name.value, ast.Name)
    assert name.value.id == 'spec' and name.attr == 'name'


def headscale_inventory(registry_source=None, native_source=None, server_source=None):
    """Read the 11 registered tools and 29 native routes from AST, never importing child code."""
    base = ROOT / HEADSCALE_VENDOR
    registry = ast.parse(registry_source if registry_source is not None else (base / 'registry.py').read_bytes())
    native = ast.parse(native_source if native_source is not None else (base / 'native.py').read_bytes())
    server = ast.parse(server_source if server_source is not None else (base / 'server.py').read_bytes())
    _headscale_registration(registry, server)

    builders = [node for node in native.body if isinstance(node, ast.FunctionDef) and node.name == '_op']
    assert len(builders) == 1
    returns = [node for node in ast.walk(builders[0]) if isinstance(node, ast.Return)]
    assert len(returns) == 1 and isinstance(returns[0].value, ast.Call)
    constructed = returns[0].value
    assert isinstance(constructed.func, ast.Name) and constructed.func.id == 'NativeOperation'
    route = constructed.args[1]
    assert (isinstance(route, ast.BinOp) and isinstance(route.op, ast.Add)
            and isinstance(route.left, ast.Constant) and route.left.value == '/api/v1'
            and isinstance(route.right, ast.Name) and route.right.id == 'path')

    native_value = _assignment(native, 'NATIVE_OPERATIONS')
    assert (isinstance(native_value, ast.Call) and isinstance(native_value.func, ast.Name)
            and native_value.func.id == 'MappingProxyType' and len(native_value.args) == 1
            and not native_value.keywords)
    native_rows = {}
    for operation_id, call in _literal_dict(native_value.args[0]).items():
        assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == '_op'
        assert 3 <= len(call.args) <= 4 and _string(call.args[0]) == operation_id
        method, path = _string(call.args[1]), _string(call.args[2])
        assert method in ('GET', 'POST', 'PUT', 'DELETE') and path.startswith('/')
        if len(call.args) == 4:
            _literal_dict(call.args[3])
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert None not in keywords and len(keywords) == len(call.keywords)
        assert set(keywords) <= {'path_fields', 'query', 'response', 'read'}
        read = keywords.pop('read', ast.Constant(value=False))
        assert isinstance(read, ast.Constant) and type(read.value) is bool
        for field in ('path_fields', 'query'):
            if field in keywords:
                value = keywords[field]
                assert isinstance(value, (ast.Tuple, ast.List))
                [_string(item) for item in value.elts]
        if 'response' in keywords:
            _string(keywords['response'])
        native_rows[operation_id] = {'operation_id': operation_id, 'method': method,
            'path': '/api/v1' + path, 'read_only': read.value,
            'source': f'{HEADSCALE_VENDOR}/native.py', 'line': call.lineno}

    rows, bindings = {}, {}
    for name, value in _literal_dict(_assignment(registry, '_GROUPS')).items():
        assert isinstance(value, ast.Tuple) and len(value.elts) == 3
        assert (isinstance(value.elts[0], ast.Attribute) and isinstance(value.elts[0].value, ast.Name)
                and value.elts[0].value.id == 'ToolCategory')
        _string(value.elts[1])
        operations = _literal_dict(value.elts[2])
        assert operations
        natives = {}
        for operation, item in operations.items():
            assert isinstance(item, ast.Tuple) and len(item.elts) == 2
            native_id = item.elts[0]
            assert isinstance(native_id, ast.Constant) and (native_id.value is None or type(native_id.value) is str)
            _literal_dict(item.elts[1])
            natives[operation] = native_id.value
            if native_id.value is not None:
                assert native_id.value not in bindings, ('duplicate native binding', native_id.value)
                bindings[native_id.value] = (name, operation)
        rows[name] = {'source': f'{HEADSCALE_VENDOR}/registry.py', 'line': value.lineno,
                      'evidence': 'python-group-registration-AST', 'operations': {'operation': sorted(operations)},
                      'native_bindings': natives, 'source_signature': ast.unparse(value.elts[2])}
    for name, value in _literal_dict(_assignment(registry, '_FIXED')).items():
        assert name not in rows and isinstance(value, ast.Tuple) and len(value.elts) == 5
        assert (isinstance(value.elts[0], ast.Attribute) and isinstance(value.elts[0].value, ast.Name)
                and value.elts[0].value.id == 'ToolCategory')
        _string(value.elts[1])
        operation, native_id = _string(value.elts[2]), _string(value.elts[3])
        _literal_dict(value.elts[4])
        assert native_id not in bindings, ('duplicate native binding', native_id)
        bindings[native_id] = (name, operation)
        rows[name] = {'source': f'{HEADSCALE_VENDOR}/registry.py', 'line': value.lineno,
                      'evidence': 'python-fixed-registration-AST', 'operations': {},
                      'native_bindings': {operation: native_id}, 'source_signature': ast.unparse(value.elts[4])}
    assert len(rows) == 11 and len(native_rows) == 29 and set(bindings) == set(native_rows), 'Headscale coverage drift'
    for operation_id, (name, operation) in bindings.items():
        native_rows[operation_id].update(tool=name, operation=operation)
    return rows, native_rows

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
        if product == 'headscale':
            rows, _ = headscale_inventory()
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
    _, headscale_native = headscale_inventory()
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
            if product == 'headscale' and evidence['operations']:
                assert name in SELECTORS and SELECTORS[name][0] == 'operation'
                assert set(evidence['operations']['operation']) == set(SELECTORS[name][1].split()), name
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
            if full and product == 'headscale':
                enable = '新安裝預設開啟；管理面板可逐一停用工具或撤銷寫入 grant；disabled 優先；沒有 0.1.x 舊狀態升級路徑'
            elif full:
                enable = '預設開啟（新安裝與從 0.1.x 升級）；管理面板可逐一停用工具或撤銷寫入 grant；disabled 優先'
            elif supported:
                enable = ('PUT /api/policy (HA admin+CSRF): enabled_write_tools 選取精確 grant；disabled 優先；舊全域開關僅保留兩個既有 writer'
                          if tool.grants(name) else 'authorized-admin-policy: remove from disabled')
            else:
                enable = '不可由 GUI 啟用；需 source/policy/test review'
            if product == 'headscale':
                for operation, native_id in evidence['native_bindings'].items():
                    if native_id is not None:
                        effect = operation_effects.get('operation', {}).get(operation, categories[name])
                        assert (effect == 'read') == headscale_native[native_id]['read_only'], (name, operation, native_id)
            entries.append({'name': name, **evidence, 'effect': categories[name], 'operation_effects': operation_effects,
                'dispatch_operations': dispatch,
                'status': status,
                # New states enable reviewed grants; migration only applies to the original products (Odoo Manage none).
                'default_enabled': supported and set(tool.grants(name)) <= set(fresh_write_grants(product)),
                'write_grants': tool.grants(name) if supported else [],
                'operation_parameter': tool.selector if supported else None,
                'enable': enable,
                'reason': ('Headscale 已審查工具：參數由子程序驗證，輸入原樣轉送。' if product == 'headscale' else
                           '子程序完整工具（0.2.0）：參數由子程序驗證，輸入原樣轉送，輸出不再投影。') if full else review[product][name],
                **({'review_reason': review[product][name]} if product == 'headscale' else {}),
                # A full-surface tool has no local argument model: tools/list carries the child's own inputSchema.
                'accepted_schema': None if full or not supported else tool.arguments.model_json_schema(),
                'tests': ['tests/test_tool_inventory.py'] + (['tests/test_full_surface.py', 'tests/test_real_products.py']
                                                             if full else [])})
        products[product] = {'upstream_count': len(entries), 'supported_count': len(POLICIES[product]), 'tools': entries}
        if product == 'headscale':
            products[product]['native_operations'] = [headscale_native[name] for name in sorted(headscale_native)]
    return {'format': 3, 'scope': '0.2.0 full child surface for the original seven products (owner decision 2026-10-15); Odoo Manage (retired) keeps the 0.1.x bounded surface; Headscale targets v0.29.4 native API (11 tools, 29 operations) on new installs; not HA/release acceptance',
            'source_digests': digests, 'products': products}


def markdown(data):
    lines = ['# 九類完整 upstream 工具對照（含 Headscale v0.29.4）', '',
             '由 `scripts/tool_inventory.py` 產生；一般 Python 是 decorator AST（含條件註冊；Nextcloud 是 `_functions()` 註冊表 AST）；Headscale 是 `_GROUPS`／`_FIXED`、`NATIVE_OPERATIONS` 與 `add_tool` 註冊路徑 AST；n8n 是 pinned runtime 定義 export。不冒充全部都曾由 MCP tools/list 觀察。',
             '0.2.0（負責人 2026-10-15 決定）：原有七支（Odoo、n8n、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud）開放子程序的全部工具（supported-full）；已下架的 Odoo Manage 維持 0.1.x 有界版（supported-bounded）。新加入的 Headscale 同樣開放其 11 支已審查工具，覆蓋 Headscale v0.29.4 的 29 個 native operations，`diff` 是本地衍生操作。完整工具的 tools/list 用子程序自己的 inputSchema（經 provider-safe 正規化），tools/call 參數原樣轉送、由子程序驗證。',
             '寫入 grants：寫入工具是工具名，混合工具是 tool:operation；原有產品新安裝與從 0.1.x 升級（state schema 4 遷移一次）時全部開啟，Headscale 只適用新安裝並拒絕舊狀態。管理員可在面板逐一撤銷或停用工具（disabled 優先）。read 表示 wrapper 沒有刻意業務寫入，不保證無敏感資料、cache/log/auth 活動；未驗證副作用（unverified-side-effects）以寫入 grant 管理。',
             '管理需 HA 可信 admin role。子程序名單之外的工具（升級後上游新增者）在此重新分類前一律拒絕。',
             '來源版本／修改／授權見 `provenance/six-runtimes.md`；Headscale 詳見 `provenance/headscale-source.md`。每次升版須 drift test 及重新審查，不可自動允許新工具。', '']
    for product, group in data['products'].items():
        lines += [f"## {product}：上游 {group['upstream_count']}／開放 {group['supported_count']}", '',
                  '| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 寫入 grants | 理由／剩餘工作 | 測試 |', '|---|---|---|---|---|---|---|']
        for tool in group['tools']:
            operations = json.dumps(tool['operation_effects'], ensure_ascii=False)
            if tool['dispatch_operations']:
                operations += '<br>本地：' + json.dumps(tool['dispatch_operations'], ensure_ascii=False)
            reason = tool['reason'] + (' ' + tool['review_reason'] if 'review_reason' in tool else '')
            lines.append(f"| `{tool['name']}` | {tool['effect']} | {tool['status']} / {'on' if tool['default_enabled'] else 'off'} | {operations} | {', '.join(tool['write_grants']) or '—'} | {reason} {tool['enable']} | {', '.join(tool['tests'])} |")
        lines.append('')
        if product == 'headscale':
            lines += ['### Headscale v0.29.4 native operations（29）', '',
                      '| native operation | HTTP | API path | tool / task operation | read only | source |',
                      '|---|---|---|---|---|---|']
            for operation in group['native_operations']:
                lines.append(f"| `{operation['operation_id']}` | {operation['method']} | `{operation['path']}` | "
                             f"`{operation['tool']}` / `{operation['operation']}` | "
                             f"{'yes' if operation['read_only'] else 'no'} | "
                             f"`{operation['source']}:{operation['line']}` |")
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
