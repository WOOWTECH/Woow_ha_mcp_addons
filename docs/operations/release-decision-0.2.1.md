# 0.2.1 候選發佈紀錄（完整版修正）

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

## 背景

0.2.0（[紀錄](release-decision-0.2.0.md)）映像已推上 GHCR（標籤不可覆寫），並在 PaaS 測試 VM 完整實測：168 項中 157 PASS。
使用者 2026-10-15 決定：修完以 0.2.1 上架，**0.2.0 不上商店**；Store 由 0.1.14 直接升 0.2.1。0.2.0 的全部內容（完整版、
寫入與工具預設全開、Odoo 任意方法與 chatter 直發、原始錯誤訊息）一併隨 0.2.1 發佈。升級遷移與 0.2.0 相同：state schema 3→4
只遷移一次，寫入授權全開、0.1.x 停用清單清空，token、連線、對外端點保留；0.2.0 寫入的 schema 4 state 照樣載入，只補一個空的
n8n MCP access token 欄位。七支共用版本規則一致升 0.2.1。

## 修正（對應實測 B1–B5）

一、B1 n8n MCP access token：0.2.0 只給子程序 `N8N_API_URL`／`N8N_API_KEY`，n8n-mcp 需要 `N8N_MCP_ACCESS_TOKEN`（n8n 設定 →
Instance-level MCP，與 API 金鑰不同）才能用原生版本歷史、資料表欄位操作、`n8n_test_workflow` prepare／pinned／direct、
`n8n_explore_node_resources`、`n8n_manage_agents`，實測全回 NOT_CONFIGURED。新增選填欄位：`ProductState.mcp_access_token`
（只限 n8n、可列印 ASCII 1–8192、不進 repr），管理 API `PUT /api/backend` 接受 `{url, key[, mcp_access_token]}`（整組取代，
不帶或清除即移除），bootstrap 只回 `mcp_access_token_set`，面板「後端連線設定」新增選填欄位；`n8n_adapter.child_spec` 有設定時
傳入；`redact.secret_values` 納入（回覆中換成 `[REDACTED]`）。

二、B2 n8n webhook／URL SSRF 防護完全關閉（使用者決定）：子程序設 `WEBHOOK_SECURITY_MODE=permissive`。依據 pinned n8n-mcp 2.91.0
`dist/utils/ssrf-protection.js`：模式由此環境變數讀取（預設 `strict`），`validateWebhookUrl` 與 `validateUrlSync` 在 permissive 下對
任何解析位址（私網、ULA、loopback）回 valid，只有讀模式前就擋的雲端 metadata 主機名仍拒絕；`moderate` 只多放行 localhost。
`n8n_test_workflow` 因此能連到 HA 內網的 n8n（實測 172.30.33.10、fd0c:ac1e:2100::11 原回「SSRF protection: IPv6 private address not
allowed」）。**風險：MCP 可經 n8n-mcp 連到 add-on 能到的任何內網位址。** n8n API 後端的 DNS 固定 agents（`backend_policy.cjs`）與
其他產品的出站防護不變。

三、B3 HTTP 狀態錯誤：`backend_policy.error_code` 未處理 `httpx.HTTPStatusError`（子程序 `raise_for_status()`），Hermes 的 422 被標成
`BACKEND_UNAVAILABLE` 且只有 httpx 文字。現在依狀態分類為 `BACKEND_HTTP_ERROR status=<碼>`，`backend_error_text` 附上
「狀態、方法與路徑：後端回應內容」（最多 4096 字、不含查詢字串、未讀取的 body 省略），仍經 gateway 憑證遮罩。

四、B4 Odoo 競態：非同步任務被取消後仍執行時，前景 `execute_method` create 與 `chatter_post` 各回一次 `BACKEND_UNAVAILABLE: Idle`。
根因：odoo-mcp `submit_async_task` 以 session 的 OdooClient（`app_context.odoo`）在 task_queue 自己的執行緒跑（不經 launch.py 的
BoundedTools 單一工作者；取消只標記，執行中的工作會跑完），與前景共用同一個 xmlrpc transport；它快取一條 http.client 連線並在每次
請求後關閉（`XMLTransport.request` 的 finally），交錯使用時 http.client 回 `Idle`（ResponseNotReady／CannotSendRequest）。修正：
`XMLTransport` 以每個 transport 一把鎖序列化交換（每個 RPC 之間仍可交錯）。重現測試在修正前得到完全相同的
`ValueError: BACKEND_UNAVAILABLE: Idle`。

五、B5 Nextcloud 原始錯誤：上游對 403 與 5xx 只回固定對照文字。`webdav.server_message` 另讀 OCS `meta/message`（XML／JSON）、JSON
`message`／`error` 與純文字（最多 1000 字，原 200 字、只認 Sabre），`client` 對每個非 2xx（含 5xx）都讀，`status_message` 在對照文字後
加「Nextcloud: <訊息>」；401、429 仍固定並暫停連線。更正 0.2.0 CHANGELOG 中「非 2xx 附上 Nextcloud 自己的錯誤訊息」的不準確描述
（寫在 0.2.1 段落）。

## 測試

`tests/test_n8n_mcp_access_token.py`、`tests/test_n8n_permissive_webhooks.py`（pinned 驗證器 strict 拒、permissive 收私網與 ULA、
metadata 仍拒）、`tests/test_raw_backend_errors.py`（HTTPStatusError 分類與 body、真實 Hermes 子程序 422）、
`tests/test_odoo_shared_transport.py`（B4 重現）、`tests/test_nextcloud_child.py::test_nextcloud_own_error_message_is_relayed`、
UI contract 測試（n8n token）。

## 後續

主控核對 CI、builder admission 與候選 receipts，再於 PaaS HAOS VM 驗收：0.1.14 → 0.2.1 升級遷移、B1（設定 token 後五類功能）、
B2（HA 內網 n8n 的 test_workflow）、B3（Hermes 422 原文）、B4（取消中的非同步任務與前景寫入並行）、B5（Nextcloud 403／5xx 原文）、
真實 Claude.ai 連線。本紀錄不宣告商用 PASS。
