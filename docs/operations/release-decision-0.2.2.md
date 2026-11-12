# 0.2.2 候選發佈紀錄（未設定／連不上也能連線；Hermes 與 n8n 實測修正）

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

## 背景

0.1.14 起 Claude.ai 可用密鑰網址連線，但 n8n 以外的六支在後端未設定時沒有子程序（`products.child_spec` 回 None），gateway
沒有東西可轉送，initialize 在對外網址回 HTTP 502（2026-10-14 實測 EMQX、Nextcloud），連接器根本加不上去；n8n 沒有後端時子程序
照常啟動，但 tools/list 只有 7 個文件工具。0.2.x 的 tools/list 用子程序自己的 inputSchema，沒有子程序時需要另一個來源。
使用者 2026-10-16 核准以 0.2.2 修正：initialize、`notifications/initialized`、tools/list 一律成功（完整清單與 schema），
tools/call 回 JSON-RPC 錯誤（未設定 `-32603 Backend not configured`；連不上帶原因），不轉給子程序；readiness 與管理面板不變。

## 設計選擇：建置時的工具清單快照

評估過兩種來源：

| | 以空／假連線啟動子程序只為列工具 | 建置時快照（採用） |
|---|---|---|
| 與子程序一致 | 天然一致 | 由測試保證：快照＝真實子程序 tools/list，不一致即失敗 |
| 執行期成本 | 未設定時也多一個常駐程序（記憶體、啟動時間），要監看、重啟、清 session | 一個 Python 資料模組（約 320 KB 原始碼） |
| 安全 | 用假憑證／假網址啟動子程序，違反 0.1.x「未設定不 spawn、不造假憑證、不探測外部」的界線；子程序可能嘗試連線 | 沒有程序、沒有出站 |
| 子程序沒在跑（當掉、退避、啟動中） | 仍然沒有答案 | 照樣能回答 |
| 維護 | 不需重產 | 子程序升級時要重產並審查（測試會提醒） |

快照是 `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py`（`.dockerignore` 只放行 `*.py`，所以是 Python 資料模組，不是 JSON），
由 `tests/test_tool_snapshot.py` 以 `WOOW_WRITE_TOOL_SNAPSHOT=1` 從真實子程序產生：每支在假後端、所有工具與寫入都開啟的狀態下列出
的 tools/list，只留 gateway 會轉送的欄位（name、title、description、inputSchema、annotations），依子程序原順序，不含私有健康探測工具。
測試檢查：（一）快照名稱＝`surface.py` 的分類＝各產品的 Tool 名單；（二）每支真實子程序目前的 tools/list 縮減後與快照逐字相同；
（三）同一個 state 下，gateway 自己用快照回的 tools/list 與它轉送真實子程序的 tools/list 完全相同；（四）未設定的 n8n 子程序列出的
正好是 `surface.BACKEND_FREE['n8n']` 的 7 個文件工具。2026-10-16 另行實測：七支子程序在後端位址不通時都照常回 initialize 與完整 tools/list，
兩個不同後端位址列出的內容相同（快照不含連線資訊）。

## 行為

`gateway.make_apps(listing=..., availability=...)`；`run_product`（六支）與 `apps/n8n/run.py` 都傳入 `surface.listing(product)` 與
`HealthMonitor.availability`。不傳 listing（已下架的 Odoo Manage、舊測試）行為不變。

- 權杖檢查、方法、Origin、body、policy（Unknown tool／Invalid params／Operation not permitted）、沒帶 session 的 400 都照舊先處理。
- 子程序不在跑（`Supervisor.status` 不是 running／starting；未設定時是 unconfigured）：gateway 自己回 initialize（與子程序回覆
  改寫後相同的 result：client 的 protocolVersion 若在審查過的四版內則照回，否則回最新的；serverInfo 為本 add-on；新的
  `woow-local-<32 hex>` session）、`notifications/initialized`（202）、ping（`{}`）、tools/list（快照經 `redact_secrets`＋`filter_list`，
  與子程序回覆同一路徑）；GET 405、DELETE 200。tools/call：需要後端的工具在未設定時 `-32603 Backend not configured`，其餘
  `-32603 Backend unreachable`，`data.reason` 為 `MCP_SERVER_NOT_READY: the add-on's MCP server is <狀態>; try again shortly`
  或最近一次檢查的後端原因。
- 子程序在跑：initialize 照常轉送；連線被拒（子程序啟動中、尚未 listen）時最多等 10 秒（每 0.25 秒重試），之後由 gateway 自己回答。
  其他請求連線被拒時回 404（子程序的 session 已隨它結束）。
- 未設定但子程序在跑（只有 n8n）：tools/list 由 gateway 用快照回答（完整 28 個），`surface.BACKEND_FREE` 的 7 個文件工具照常轉送，
  其他工具 `-32603 Backend not configured`。
- 已設定、最近一次**完成**的健康檢查（同一次子程序啟動、initialize 與 ping 都有回）判定後端連不上：需要後端的工具
  `-32603 Backend unreachable`，`data.reason` 是那次檢查的探測工具回覆（後端自己的錯誤文字，或 JSON 的 error／message；去掉
  SDK 的「Error executing tool <名稱>:」前綴、合併空白、最多 1000 字、憑證換成 `[REDACTED]`）；逾時為
  `BACKEND_TIMEOUT: the health check got no answer within 5 s`。沒有完成的檢查（例如剛重啟）時一律轉送，不以猜測拒絕；檢查進行中
  也不影響（`snapshot()` 給 readiness／面板的值照舊，`availability()` 只看完成的檢查）。
- gateway 自己的 session 閒置 30 分鐘結束、最多 256 個（最久沒用的先結束）。子程序起來並通過一次健康檢查後，用這種 session 的下一個
  請求回 404，client 依 MCP 規範重新 initialize 即改連子程序；反過來子程序停掉後，它的 session 也回 404。
- `ToolCallRefused` 新增 `backend_unreachable`（只由 gateway 使用）；`surface.full_tools` 為每個工具標 `requires_backend`
  （n8n 的 7 個文件工具除外）。`HealthMonitor` 新增 `settled`／`availability()`，`snapshot()` 與 readiness 不變。

取捨與限制：後端短暫失敗時，最多到下一次完成的檢查（約 15 秒）內需要後端的工具會被拒；Odoo 少數不連後端的本地工具（例如
`build_domain`）在後端連不上時也被拒（保守起見，所有非 n8n 文件工具都視為需要後端）。Odoo 的健康探測只回代碼（例如
`BACKEND_UNAVAILABLE`），不像 EMQX／n8n 帶原文。Claude.ai 收到 404 是否自動重新 initialize 尚未實測。

## 同版另修三項（測試 VM 2026-10-16 實測）

一、G1 Hermes `hermes_config get` 明文吐出後端憑證：在 Hermes dashboard 設定自訂 OpenAI 相容端點後，`hermes_config
{action:"get"}`（或 `key:"custom_providers"`）回覆含 `custom_providers[].api_key`。原因：vendored `hermes_mcp_server/server.py` 原樣
回傳 `GET /api/config`，`DENIED_CONFIG_KEYS` 只擋 set。修正：`redact_config` 把 secret 類欄位（任一字為 password、secret(s)、
authorization、credential(s)、apikey、cookie 等，或最後一字為 key、token、auth、pat、bearer；以非英數字與 camelCase 分字，所以
`max_tokens`、`auth_mode` 不算）的非空值換成 `[REDACTED]`（含巢狀物件與 list），保留欄位名、空字串、null 與布林（看得出是否已設定），
並遮蔽網址 userinfo 的密碼；get（整份或 key 路徑；路徑任一段是 secret 時整個值遮蔽）與 `hermes_inspect` 的 config 摘要都套用。set
不變。這是後端持有的憑證，不屬於 0.2.0「後端錯誤回原文」的決定。**PaaS 的 hermes_mcp_server 是同一份程式碼，有相同問題。**

二、G2 `hermes_chat` 逾時：原本與其他 Gateway 呼叫共用固定 30 秒，一輪對話（約 1.45 萬 prompt tokens、免費模型）常要 28–30 秒，
3 次有 2 次 `BACKEND_TIMEOUT`（Hermes 端其實完成）。修正：對話一輪最多 300 秒（`HERMES_MCP_CHAT_TIMEOUT`，1–3600 秒；連線 30 秒），
其他呼叫維持 30 秒。gateway 端：tools/call 的回覆最多可閒置、總共 330 秒（`gateway.CALL_SECONDS`；等子程序回 header 335 秒），其他
請求維持閒置 30 秒、header 35 秒、總共 120 秒。Python SDK 子程序每 15 秒送 SSE 註解，所以原本實際會切斷的是 120 秒總時限（本機測試：33 秒的
對話在舊 gateway 也能過，舊 vendor 則逾時）。長呼叫期間佔 32 個同時連線名額之一。Claude.ai 與中間代理（例如 Cloudflare tunnel）自己的
時限未實測。

三、n8n 評估錯誤原文：n8n-mcp 2.91.0 `dist/mcp/handlers-n8n-manager.js` 的 `handleTestRunError`（所有 `n8n_evaluations` 動作）把 403
一律換成固定的 testRun scope 提示，n8n 的原因（例如「Evaluations are not available on your plan」）被吃掉；402、409、404 的固定提示
也一樣。修正：固定提示後加「 n8n: <n8n 原文>」（N8nApiError 的 message）。以 build-time patch
`apps/n8n/patches/fix_test_run_error_messages.py` 套用（比照 Odoo patches）：只接受 pinned 原檔（sha256 `0d99e10e…`），結果固定為
`5b820575…`、可重複執行；`apps/n8n/Dockerfile` 在 `npm ci` 後、`packaging/unit.sh` 在其 `npm ci` 後執行；`backend_policy.cjs` 的
source guard 改為 patched digest，未套用或被改動即拒絕啟動子程序。node_modules 不進 git。

## 測試

`tests/test_unconfigured_connect.py`（七支 × Bearer／密鑰網址的未設定連線序列、policy 與 session 規則、錯誤權杖、後端連不上、
子程序不在跑與恢復、initialize 等待啟動中的子程序、session 上限與閒置、`probe_reason`、`HealthMonitor.availability`，以及真實
可執行檔：七支未設定、EMQX／Odoo／n8n 後端位址不通）、`tests/test_tool_snapshot.py`（快照與分類、真實子程序、gateway 兩條路徑一致、
n8n 文件工具）、`tests/test_hermes_config_redaction.py`（真實 Hermes 子程序：整份／key 路徑／inspect 摘要不含任何後端憑證、欄位名與空值保留、set 不變；舊程式碼下失敗）、`tests/test_hermes_chat_timeout.py`（33 秒的對話經 gateway 成功，舊 vendor 逾時；環境變數生效且不影響管理呼叫；只有 tools/call 可超過 STREAM_SECONDS）、`tests/test_n8n_test_run_errors.py`（patch digest、冪等、拒絕 drift、Dockerfile／unit.sh 掛點；真實 n8n 子程序 403／402 錯誤帶 n8n 原文且憑證遮蔽）。

## 後續

主控核對 CI、builder admission 與候選 receipts，再於 PaaS HAOS VM 驗收：未設定後端時以真實 Claude.ai 新增連接器並列出工具、
呼叫工具得到 Backend not configured；設定後端後重新連線改連子程序；後端離線時的 Backend unreachable 原因文字；子程序重啟期間的行為；
readiness 與面板不變；Hermes 自訂端點設定後 `hermes_config get` 不含 api_key、一輪 30 秒以上的 `hermes_chat` 成功（含經 Claude.ai／tunnel 時的時限）；n8n 未授權評估功能時的錯誤帶 n8n 原文。本紀錄不宣告商用 PASS。
