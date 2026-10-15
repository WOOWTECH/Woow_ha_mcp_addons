# 工具範圍：0.2.0 完整版

**2026-10-15 負責人決定：HA add-on 做「完整版」，與原始 MCP server（GitHub／Gitea）及 PaaS woow-mcp-server 功能對齊，
所有工具（含高風險）全部開放、全部預設開啟，管理介面可逐一關閉。** 0.1.x 的有界子集（W2b、BATCH2 B1／B2／B3：本地
pydantic 模型、res.partner 限定、輸出投影）自 0.2.0 起不再用於任何出貨產品；其原始內容見 git 歷史（0.1.14 為止的本檔）。
已下架、不出貨的 Odoo Manage 仍保留 0.1.x 有界版。

## 每支開放的工具

| 產品 | 子程序工具數 | 開放 | 說明 |
|---|---:|---:|---|
| Odoo | 41 | 41 | odoo-mcp 1.1.0 全部工具，套上 PaaS 的兩個 build patch（跨 session approval token、直接寫入開關）；`ODOO_MCP_ENABLE_WRITES=1`、`ODOO_MCP_ALLOW_DIRECT_WRITES=1`（`execute_method` 可直接 create／write／unlink，三步驟 preview／validate／execute_approved_write 仍列出可用） |
| n8n | 28 | 28 | n8n-mcp 2.91.0 全部工具（credentials、test_workflow、datatable、versions、agents 等） |
| Hermes | 11 | 11 | 與 PaaS 版 hermes_mcp_server 相同（chat、config set、mcp add、webhook、cron create 等）；保留 server 本身的 stdio／command 拒絕與 config 拒絕清單 |
| OpenDesign | 15 | 15 | 全部工具（create_project、send_message 等） |
| EMQX | 39 | 39 | `EMQX_MCP_READONLY=false`（publish、ban、retained、trace、authn／authz 管理等） |
| LiteLLM | 40 | 40 | `LITELLM_MCP_READONLY=false`（key 產生／更新、chat completion、user／team／model／plugin 管理、spend 報表等） |
| Nextcloud | 9 | 9 | `NEXTCLOUD_MCP_READONLY=false`、`NEXTCLOUD_MCP_ALLOW_DELETE=true` |

逐名清單與分類（read／write／mixed／unverified-side-effects）見 [tool-surface.md](tool-surface.md)，由
`scripts/tool_inventory.py` 依 pinned 原始碼產生；分類本身在 `packages/mcp-admin-core/mcp_admin_core/surface.py`。

## Gateway 怎麼轉送

- **tools/list**：子程序回報的每個工具，只要名字在本產品的分類名單內就列出；`inputSchema` 是子程序自己的 schema，經 0.1.6
  的 provider-safe 正規化（`policy.flat_schema`：頂層一定是 object，去掉 Claude／GPT 會整批拒絕的 oneOf／anyOf／allOf／enum／
  const／not／$ref），讀不懂的 schema 列為 `{"type":"object"}`；`outputSchema`、`icons`、`_meta` 等仍移除；寫入工具不轉
  readOnlyHint 等放寬提示。上游升級後新增、尚未分類的工具不列出、呼叫一律拒絕。
- **tools/call**：參數必須是 JSON 物件，**原樣轉給子程序**，由子程序驗證並回自己的錯誤（gateway 不再用本地模型改寫或補預設值）。
  gateway 仍檢查：工具名在名單內、沒有被停用（disabled）、寫入工具有自己的 grant、混合工具的寫入 operation 有 `tool:operation`
  grant（省略 operation 時用原始碼預設值，皆為讀取；未分類的值視為可能是新寫入，需要該工具全部寫入 grant）。被拒時沿用 0.1.14 的
  JSON-RPC 錯誤（`-32602 Unknown tool`／`Invalid params`／`Operation not permitted`）。
- **輸出**：子程序原樣輸出（0.1.x 的 100 筆／256 字截斷與白名單欄位投影都已移除：Hermes session／cron 列表、OpenDesign
  run 列表、LiteLLM team／user／model metadata、n8n 建立 workflow／tags／executions／folder／health、Odoo B1／B2 統計）。
- **請求大小**：16 MiB（原 256 KiB），配合 Nextcloud 上傳 10 MiB（base64 約 13.4 MiB）與 1 MiB 文字檔。

## 預設與狀態遷移

- state schema 4：新安裝，以及從 0.1.x（schema 3，或更舊的 1／2 經 3）升級時**一次**遷移成：每個寫入 grant 全開、
  `writes_enabled=true`；token、連線、對外端點與停用清單（disabled）保留。之後管理員在「工具與寫入授權」取消的寫入或停用的工具，
  重啟與後續升級都維持。
- 回退：0.1.x 不接受 schema 4（state 會被拒絕並要求人工回復），回退請還原升級前的備份。

## 刻意保留的安全層

- 權杖：`/mcp` 的 Bearer 與 `/private_<token>/mcp` 密鑰網址（錯誤、空白、已撤銷一律 404）；log 把 `/private_…/` 遮成
  `/private_[REDACTED]/`。
- session 規則、32 個併發 slot、請求大小上限、回應 8 MiB 上限、SSE 重組與 JSON-RPC 回覆整形。
- 子程序出站：DNS pin、只連設定的後端、拒絕 redirect／proxy、TLS 驗證、metadata 位址拒絕（Python `apps/runtime/backend_policy.py`、
  n8n `apps/n8n/backend_policy.cjs`）；後端錯誤只回固定代碼／訊息，不回原始錯誤文字（各 vendor 的 error boundary 保留並補到
  Hermes／OpenDesign 原本沒有的 handler）。
- 原始碼守門：Odoo（含 patch 後的 tools_write／server_core）、n8n 與 vendored 檔案 digest 不符即拒絕啟動。
- 子程序環境不繼承父程序秘密；child token、乾淨工作目錄、私有 readiness probe 不列出也不能呼叫。
- 管理面板：只有 HA owner／系統管理員可進入，CSRF、確認對話框；設定只存在 add-on state。

## 風險

網址（或權杖）等同後端帳號的完整權限：AI client 可以刪改 Odoo 任意紀錄（`execute_method`）、建立或刪除 n8n credentials 與
workflow、產生 LiteLLM key、改 Hermes 設定或加 MCP server、發佈 MQTT 訊息或封鎖 client、刪除 Nextcloud 檔案。請把後端帳號
權限設對（最小權限），只保留需要的工具與寫入，網址外洩時立刻在管理面板重新產生權杖。
