# 0.1.13 候選發佈紀錄

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

0.1.12 映像已推上 GHCR，但從未發佈到 Store；GHCR 標籤不可覆寫，因此 0.1.12 不再使用，下列四項（前三項原為 0.1.12 準備內容）一併以 0.1.13 發佈。

一、把七支 manifest 的開機預設由 `boot: manual` 改為 `boot: auto`。起因：PaaS 正式測試 HAOS VM 重開機後，`boot: manual` 的 MCP 與後端 add-on 都沒有自動回來（Supervisor 只自動啟動 `boot: auto`）；使用者 2026-10-14 決定「要自動」。`packaging/validate.py` 的 manifest 精確規則同步改為 `boot='auto'`，`packaging/test_validate.py` 的反向 mutation 改為 `boot: manual` 必須被拒。其他權限、`startup: application`、protection mode、auto-update 與工具面皆不變。

二、共用 gateway 新增 Claude.ai 網頁版自訂連接器用的密鑰網址 `/private_<token>/mcp`（Claude.ai 自訂連接器無法帶 Authorization header）：用同一把 Add-on 權杖（rotate／revoke 同時生效），以 sha256 摘要經 `hmac.compare_digest` 比對；權杖錯誤、空白、未設定或已撤銷（含請求途中的重驗）一律回與不存在路徑相同的 Starlette 404；忽略請求自帶的 Authorization；允許 Origin 且不轉給子程序；`/mcp` 的 Bearer 行為不變（含 Origin 403）。新增 `mcp_admin_core/redact.py`，在 LogRecord factory 與 uvicorn handlers 兩層把 `/private_…/` 遮成 `/private_[REDACTED]/`（`access_log` 仍關閉）。管理面板新增「顯示 Claude.ai 連線網址」（沿用 token reveal 的 CSRF 流程，需先設定對外端點）。說明見 [client 設定](clients.md)；測試見 `tests/test_secret_path.py` 與 UI 測試。

三、manifest 移除 `ingress_entry: /`（2026-10-14 實機發現）：Supervisor 2026.09（`supervisor/apps/app.py` 的 `ingress_url`）回傳 `f"/api/hassio_ingress/{token}/{ingress_entry}"`，舊值使 HA 側邊欄開啟 `…/<token>//`，管理面板回 404（0.1.11 實例同樣受影響）。不設此鍵時入口為 `…/<token>/`。PaaS 測試 VM 以本機 add-on 實測：移除並 rebuild 後 ingress_url 結尾單一 `/`、GET 200。`packaging/validate.py` 不再接受此鍵（`exact()` 拒絕），`test_validate` 加入反向案例。

四、JSON-RPC 白名單修正，讓真實 Claude.ai 自訂連接器能連上（2026-10-14 實機發現）。經 Cloudflare 到測試 VM 的記錄代理（只記 key 名）看到 Claude.ai 先送 `server/discover`（header `MCP-Protocol-Version: 2026-07-28`，params 只有 `_meta`：clientCapabilities、clientInfo、protocolVersion、traceparent），再退回 `initialize`（protocolVersion 2025-11-25，clientInfo `Anthropic/ClaudeAI` 或 `Anthropic/Toolbox`，params 為 `_meta`（traceparent）、`capabilities`（extensions）、`clientInfo`、`protocolVersion`）；gateway 兩者都回 HTTP 403。原因：`policy.authorize()` 要求 initialize params 恰好三個 key、其他方法也不允許 `_meta`，不認識的方法一律 Denied，`gateway.serve()` 再把 Denied 全轉成 403。同一網址用不帶 `_meta` 的 python-httpx 與 MCP Python SDK 則正常。

修正（`packages/mcp-admin-core/mcp_admin_core/policy.py`、`gateway.py`）：

- MCP 規格把 `_meta` 保留給所有 request／notification 的 params。每個允許的方法（initialize、ping、tools/list、tools/call、notifications/initialized）都接受選填 `params._meta`：必須是物件，序列化（compact JSON、UTF-8）後至多 8 KiB，否則仍 Denied（403）；通過後在轉給子程序前移除，params 只剩空物件時整個 params 一併移除。子程序收到的內容與不帶 `_meta` 的 client 相同，因此 `progressToken` 等也不會到子程序。其他欄位檢查（initialize 三個 key、tools/call 的參數模型、寫入閘、backend 需求、ping／initialized 不得有其他 params）嚴格度不變。
- 不認識的 request（有字串或整數 id，例如 `server/discover`、`resources/list`、`prompts/list`）不再 403：gateway 自己回 HTTP 200、`Content-Type: application/json` 的 `{"jsonrpc":"2.0","id":<同 id>,"error":{"code":-32601,"message":"Method not found"}}`；不認識的 notification（無 id，例如 `notifications/cancelled`）回 202。兩者都在 session 檢查前回覆，不轉給子程序、不建 session、不佔 32 個連線名額。權杖檢查仍在最前面：錯誤權杖仍是 `/mcp` 401、密鑰路徑與不存在路徑相同的 404。格式錯誤（id 為 null／布林／小數、params 非物件、多餘頂層 key、帶 id 的 initialized、無 id 的已知 request）維持 403。
- 只接受 `application/json`（Accept 不含 `text/event-stream` 與 `*/*`）的 client，initialize 的回覆改用 JSON（子程序以 SSE 回時也是）。其他回覆的 SSE 轉 JSON 未做：MCP 規定 client 必須同時接受兩者，改動 streaming 路徑風險較大。

測試：`tests/test_claude_ai_connector.py`（Claude.ai 形狀的 initialize 在兩條路徑成功且子程序收到的 params 不含 `_meta`；tools/list、tools/call、ping、notifications/initialized 帶 `_meta` 轉送時已剝除；`_meta` 非物件或過大被拒；`server/discover` 等回 200 + -32601 且未轉送；不認識的 notification 回 202 未轉送；錯誤權杖對 `server/discover` 仍 401／404；名額全滿時 `server/discover` 仍回答；工具權限不退化）。`tests/test_boundary.py`、`tests/test_real_products.py`、`tests/test_batch2_runtime.py` 與 `packaging/container_probe.py` 中「不認識方法回 403」的斷言改為 200 + -32601（仍斷言未轉送）。修正後尚未以真實 Claude.ai 重測。

此 repo 七個產品共用 VERSION、initialize 身分、manifest、Dockerfile 與 CI/release 版本，因此一致準備 0.1.13；不新增版號分流機制。新版本改變 core VERSION、image labels 及 source revision，必須產生新 image ID，不能 retag 或繼承 0.1.11／0.1.12 映像驗收。

後續由主控核對 hosted CI、builder admission 與候選 image/test/scan receipts，再在 PaaS 已建立的 HAOS VM 完成實機驗收（含重開機後七支自動啟動、真實 Claude.ai 自訂連接器連線）。已安裝且使用者曾手動切換「開機時啟動」的實例，可能保留其個別設定，升版後需在 HA 上逐支確認。主控統一 release/merge/部署；本紀錄不宣告商用 PASS。
