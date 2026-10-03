# 七類完整 upstream 工具對照（W2a）

由 `scripts/tool_inventory.py` 產生；Python 是 decorator AST（含條件註冊），n8n 是 pinned runtime 定義 export，不冒充全部都曾由 MCP tools/list 觀察。
每個工具的精確參數／default／允許 operation 見 `tool-surface.json` 的 accepted_schema。混合工具僅 schema 中列出的 read action 可用；寫入總開關不擴大 schema。
read 表示 wrapper 沒有刻意業務寫入，不保證無敏感資料、cache/log/auth 活動；未驗證副作用明列，不按 GET/annotation 猜安全。
管理需 HA 可信 admin role；目前 executable fail closed，沒有繞過旗標。GUI/W3 尚未交付。所有 writers 預設關閉；未支援工具即使 writes_enabled=true 仍拒絕。
來源版本／修改／授權見 `provenance/six-runtimes.md`。每次升版須 drift test 及重新審查，不可自動允許新工具。

## odoo：上游 41／本地 bounded 2

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `accounting_health_across_instances` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `accounting_health_summary` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `aggregate_across_instances` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `aggregate_records` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `analyze_upgrade_log` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `build_domain` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `business_pack_report` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `cancel_async_task` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `chatter_post` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `data_quality_report` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `diagnose_access` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `diagnose_odoo_call` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `execute_approved_write` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `execute_method` | mixed | temporarily-unsupported / off | {"arbitrary-method": {"*": "unverified-side-effects"}} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `fit_gap_report` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `generate_json2_payload` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `get_async_task` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `get_model_fields` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `get_odoo_profile` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `health_check` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `index_knowledge` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `inspect_model_relationships` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `knowledge_stats` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_async_tasks` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_instances` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_models` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `lookup_model_history` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `preview_write` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `read_attachment` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `read_record` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `receivable_payable_aging` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `scan_addons_source` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `schema_catalog` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_across_instances` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_employee` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_holidays` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_knowledge` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_records` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `submit_async_task` | write | temporarily-unsupported / off | {"operation": {"data_quality_report": "write", "index_knowledge": "write", "receivable_payable_aging": "write", "scan_addons_source": "write"}} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `upgrade_risk_report` | read | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `validate_write` | write | temporarily-unsupported / off | {} | W2b：需逐 handler／模型／欄位輸出審查、參數界限及假 XML-RPC 正反測試；禁止任意方法、跨 instance 與本機檔案讀取。 不可由 GUI 啟用；需 W2b source/policy/test review |

## odoo-manage：上游 10／本地 bounded 1

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `aggregate_records` | read | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `call_model_method` | mixed | temporarily-unsupported / off | {"arbitrary-method": {"*": "unverified-side-effects"}} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `create_record` | write | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `delete_record` | write | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `get_record` | read | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_models` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_resource_templates` | read | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `post_message` | write | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_records` | read | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `update_record` | write | temporarily-unsupported / off | {} | W2b：需模型／欄位白名單及假後端測試；寫入需另外批准 backend mode，禁止 arbitrary call_model_method；resources 不開放。 不可由 GUI 啟用；需 W2b source/policy/test review |

## hermes：上游 11／本地 bounded 5

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `hermes_chat` | write | temporarily-unsupported / off | {} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `hermes_config` | mixed | temporarily-unsupported / off | {"action": {"get": "read", "set": "write"}} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `hermes_cron` | mixed | temporarily-unsupported / off | {"action": {"create": "write", "delete": "write", "list": "read", "pause": "write", "resume": "write", "trigger": "write", "update": "write"}} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `hermes_gateway` | mixed | supported-bounded / on | {"action": {"restart": "write", "status": "read"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `hermes_inspect` | read | supported-bounded / on | {"target": {"all": "read", "capabilities": "read", "config": "read", "model": "read", "status": "read"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `hermes_mcp` | mixed | temporarily-unsupported / off | {"action": {"add": "write", "list": "read", "remove": "write"}} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `hermes_model` | mixed | supported-bounded / on | {"action": {"info": "read", "list_providers": "read", "set": "write"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `hermes_session` | mixed | temporarily-unsupported / off | {"action": {"delete": "write", "get": "read", "list": "read"}} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `hermes_skill` | mixed | supported-bounded / on | {"action": {"disable": "write", "enable": "write", "list": "read"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `hermes_tools` | mixed | supported-bounded / on | {"action": {"disable": "write", "enable": "write", "list": "read"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `hermes_webhook` | mixed | temporarily-unsupported / off | {"action": {"create": "write", "delete": "write", "enable_platform": "write", "list": "read", "toggle": "write"}} | W2b：需逐 action、路徑及內容遮罩審查；session/config/prompt/MCP URL 可能洩密，agent/chat/cron 有寫入或費用。 不可由 GUI 啟用；需 W2b source/policy/test review |

## opendesign：上游 15／本地 bounded 10

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `create_project` | write | temporarily-unsupported / off | {} | W2b：檔案讀取需非秘密路徑及回應上限；廣泛結果需內容審查；AI 生成需費用／副作用測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `delete_project` | write | supported-bounded / off | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 PUT /api/policy (HA admin+CSRF): writes_enabled=true; remove from disabled |
| `get_file_info` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `get_project` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `health` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_agents` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_connectors` | read | temporarily-unsupported / off | {} | W2b：檔案讀取需非秘密路徑及回應上限；廣泛結果需內容審查；AI 生成需費用／副作用測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_plugins` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_project_files` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_projects` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `list_runs` | read | temporarily-unsupported / off | {} | W2b：檔案讀取需非秘密路徑及回應上限；廣泛結果需內容審查；AI 生成需費用／副作用測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `list_skills` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `read_file` | read | temporarily-unsupported / off | {} | W2b：檔案讀取需非秘密路徑及回應上限；廣泛結果需內容審查；AI 生成需費用／副作用測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `send_message` | write | temporarily-unsupported / off | {} | W2b：檔案讀取需非秘密路徑及回應上限；廣泛結果需內容審查；AI 生成需費用／副作用測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `version` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |

## emqx：上游 39／本地 bounded 3

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `emqx_authz_settings` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_ban` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_broker_stats` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `emqx_client_subscribe` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_client_subscriptions` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_client_unsubscribe` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_cluster_status` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `emqx_create_trace` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_delete_retained` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_delete_trace` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_get_client` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_get_retained` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_get_rule_metrics` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_get_trace_log` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_kick_client` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_actions` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_alarms` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_authn` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_authz_sources` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_banned` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_clients` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_connectors` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_listeners` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_retained` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_rules` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_subscriptions` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_topics` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_list_traces` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_manage_authn_users` | mixed | temporarily-unsupported / off | {"operation": {"create": "write", "delete": "write", "read": "read"}} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_manage_authz_rules` | mixed | temporarily-unsupported / off | {"operation": {"create": "write", "delete": "write", "read": "read"}} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_metrics_current` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `emqx_metrics_history` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_node_detail` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_prometheus_stats` | read | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_publish` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_publish_bulk` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_test_rule_sql` | unverified-side-effects | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_toggle_rule` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `emqx_unban` | write | temporarily-unsupported / off | {} | W2b：需逐工具參數及輸出審查／假 broker 測試；payload、認證、trace、integration 可能敏感；混合工具用 operation，不是 action。 不可由 GUI 啟用；需 W2b source/policy/test review |

## litellm：上游 40／本地 bounded 2

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `litellm_add_model` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_block_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_chat_completion` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_create_team` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_create_user` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_delete_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_delete_model` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_delete_plugin` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_delete_team` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_delete_user` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_disable_plugin` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_enable_plugin` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_generate_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_global_spend_report` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_health` | unverified-side-effects | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_health_readiness` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `litellm_key_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_list_keys` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_list_models` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `litellm_list_plugins` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_list_teams` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_list_users` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_model_group_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_model_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_plugin_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_regenerate_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_register_plugin` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_skill_hub` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_spend_calculate` | unverified-side-effects | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_spend_logs` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_team_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_team_member_add` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_team_member_delete` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_token_counter` | unverified-side-effects | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_unblock_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_update_key` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_update_model` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_update_team` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_update_user` | write | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `litellm_user_info` | read | temporarily-unsupported / off | {} | W2b：需參數／pagination／輸出遮罩及版本相容測試；key/model/spend 可能敏感；推論及 health provider probe 可能產生費用。 不可由 GUI 啟用；需 W2b source/policy/test review |

## n8n：上游 28／本地 bounded 4

| exact tool | 來源副作用 | 支援／預設 | operations（來源） | 理由／啟用 |
|---|---|---|---|---|
| `get_node` | read | temporarily-unsupported / off | {"mode": {"info": "read", "docs": "read", "search_properties": "read", "versions": "read", "compare": "read", "breaking": "read", "migrations": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `get_template` | read | temporarily-unsupported / off | {"mode": {"nodes_only": "read", "structure": "read", "full": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_audit_instance` | unverified-side-effects | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_autofix_workflow` | write | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_create_workflow` | write | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_delete_workflow` | write | supported-bounded / off | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 PUT /api/policy (HA admin+CSRF): writes_enabled=true; remove from disabled |
| `n8n_deploy_template` | write | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_evaluations` | mixed | temporarily-unsupported / off | {"action": {"list_runs": "read", "get_run": "read", "list_cases": "read", "run": "write", "cancel": "write"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_executions` | mixed | temporarily-unsupported / off | {"action": {"get": "read", "list": "read", "delete": "write"}, "mode": {"preview": "mixed", "summary": "mixed", "filtered": "mixed", "full": "mixed", "error": "mixed"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_explore_node_resources` | mixed | temporarily-unsupported / off | {"methodType": {"listSearch": "mixed", "loadOptions": "mixed"}, "arbitrary-method": {"*": "unverified-side-effects"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_get_workflow` | read | temporarily-unsupported / off | {"mode": {"full": "read", "details": "read", "structure": "read", "minimal": "read", "active": "read", "filtered": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_health_check` | read | temporarily-unsupported / off | {"mode": {"status": "read", "diagnostic": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_list_catalog` | read | temporarily-unsupported / off | {"kind": {"projects": "read", "tags": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_list_workflows` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `n8n_manage_agents` | mixed | temporarily-unsupported / off | {"action": {"reference": "read", "search": "read", "get": "read", "create": "write", "mutate": "write", "validate": "read", "call": "write", "publish": "write", "unpublish": "write", "revert": "write", "versions": "read", "delete": "write", "discover_assets": "read", "verify_mcp_server": "unverified-side-effects", "update_integration": "write"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_manage_credentials` | mixed | temporarily-unsupported / off | {"action": {"list": "read", "get": "read", "create": "write", "update": "write", "delete": "write", "getSchema": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_manage_datatable` | mixed | temporarily-unsupported / off | {"action": {"createTable": "write", "listTables": "read", "getTable": "read", "updateTable": "write", "deleteTable": "write", "getRows": "read", "insertRows": "write", "updateRows": "write", "upsertRows": "write", "deleteRows": "write", "addColumn": "write", "deleteColumn": "write", "renameColumn": "write"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_manage_folders` | mixed | temporarily-unsupported / off | {"action": {"create": "write", "list": "read", "get": "read", "rename": "write", "move": "write", "delete": "write"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_test_workflow` | write | temporarily-unsupported / off | {"method": {"auto": "write", "trigger": "write", "prepare": "write", "pinned": "write", "direct": "write"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_update_full_workflow` | write | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_update_partial_workflow` | write | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_validate_workflow` | read | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `n8n_workflow_versions` | mixed | temporarily-unsupported / off | {"mode": {"list": "read", "get": "read", "rollback": "write", "delete": "write", "prune": "write", "diff": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `search_nodes` | read | supported-bounded / on | {"mode": {"OR": "read", "AND": "read", "FUZZY": "read"}} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `search_templates` | read | temporarily-unsupported / off | {"searchMode": {"keyword": "read", "by_nodes": "read", "by_task": "read", "by_metadata": "read", "patterns": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `tools_documentation` | read | supported-bounded / on | {} | 僅接受 adapter inputSchema；server-side unknown/disabled/write gate。 authorized-admin-policy: remove from disabled |
| `validate_node` | read | temporarily-unsupported / off | {"mode": {"full": "read", "minimal": "read"}} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |
| `validate_workflow` | read | temporarily-unsupported / off | {} | W2b：tracer 以外工具需逐 handler/action、輸出秘密與間接執行審查，並有 disposable fake backend 正反測試。 不可由 GUI 啟用；需 W2b source/policy/test review |

