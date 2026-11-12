# 0.1.14 候選發佈紀錄

狀態：**已發佈**：2026-10-14 上架商店，六支（OpenDesign 0.1.12 起沒有映像，商店停在 0.1.11）（GitHub tag／release `v0.1.14`，以映像建置 commit `ed3122b` 為準）。以下為發佈前的候選紀錄，內文的「準備中」「待驗收」等字樣是當時的狀態。

0.1.12、0.1.13 映像已推上 GHCR，但從未發佈到 Store；GHCR 標籤不可覆寫，因此 0.1.12、0.1.13 不再使用，下列五項（前三項原為 0.1.12、第四項原為 0.1.13 準備內容）一併以 0.1.14 發佈。

一、把七支 manifest 的開機預設由 `boot: manual` 改為 `boot: auto`。起因：PaaS 正式測試 HAOS VM 重開機後，`boot: manual` 的 MCP 與後端 add-on 都沒有自動回來（Supervisor 只自動啟動 `boot: auto`）；使用者 2026-10-14 決定「要自動」。`packaging/validate.py` 的 manifest 精確規則同步改為 `boot='auto'`，`packaging/test_validate.py` 的反向 mutation 改為 `boot: manual` 必須被拒。其他權限、`startup: application`、protection mode、auto-update 與工具面皆不變。

二、共用 gateway 新增 Claude.ai 網頁版自訂連接器用的密鑰網址 `/private_<token>/mcp`（Claude.ai 自訂連接器無法帶 Authorization header）：用同一把 Add-on 權杖（rotate／revoke 同時生效），以 sha256 摘要經 `hmac.compare_digest` 比對；權杖錯誤、空白、未設定或已撤銷（含請求途中的重驗）一律回與不存在路徑相同的 Starlette 404；忽略請求自帶的 Authorization；允許 Origin 且不轉給子程序；`/mcp` 的 Bearer 行為不變（含 Origin 403）。新增 `mcp_admin_core/redact.py`，在 LogRecord factory 與 uvicorn handlers 兩層把 `/private_…/` 遮成 `/private_[REDACTED]/`（`access_log` 仍關閉）。管理面板新增「顯示 Claude.ai 連線網址」（沿用 token reveal 的 CSRF 流程，需先設定對外端點）。說明見 [client 設定](clients.md)；測試見 `tests/test_secret_path.py` 與 UI 測試。

三、manifest 移除 `ingress_entry: /`（2026-10-14 實機發現）：Supervisor 2026.09（`supervisor/apps/app.py` 的 `ingress_url`）回傳 `f"/api/hassio_ingress/{token}/{ingress_entry}"`，舊值使 HA 側邊欄開啟 `…/<token>//`，管理面板回 404（0.1.11 實例同樣受影響）。不設此鍵時入口為 `…/<token>/`。PaaS 測試 VM 以本機 add-on 實測：移除並 rebuild 後 ingress_url 結尾單一 `/`、GET 200。`packaging/validate.py` 不再接受此鍵（`exact()` 拒絕），`test_validate` 加入反向案例。

四、JSON-RPC 白名單修正，讓真實 Claude.ai 自訂連接器能連上（2026-10-14 實機發現）。經 Cloudflare 到測試 VM 的記錄代理（只記 key 名）看到 Claude.ai 先送 `server/discover`（header `MCP-Protocol-Version: 2026-07-28`，params 只有 `_meta`：clientCapabilities、clientInfo、protocolVersion、traceparent），再退回 `initialize`（protocolVersion 2025-11-25，clientInfo `Anthropic/ClaudeAI` 或 `Anthropic/Toolbox`，params 為 `_meta`（traceparent）、`capabilities`（extensions）、`clientInfo`、`protocolVersion`）；gateway 兩者都回 HTTP 403。原因：`policy.authorize()` 要求 initialize params 恰好三個 key、其他方法也不允許 `_meta`，不認識的方法一律 Denied，`gateway.serve()` 再把 Denied 全轉成 403。同一網址用不帶 `_meta` 的 python-httpx 與 MCP Python SDK 則正常。

修正（`packages/mcp-admin-core/mcp_admin_core/policy.py`、`gateway.py`）：

- MCP 規格把 `_meta` 保留給所有 request／notification 的 params。每個允許的方法（initialize、ping、tools/list、tools/call、notifications/initialized）都接受選填 `params._meta`：必須是物件，序列化（compact JSON、UTF-8）後至多 8 KiB，否則仍 Denied（403）；通過後在轉給子程序前移除，params 只剩空物件時整個 params 一併移除。子程序收到的內容與不帶 `_meta` 的 client 相同，因此 `progressToken` 等也不會到子程序。其他欄位檢查（initialize 三個 key、tools/call 的參數模型、寫入閘、backend 需求、ping／initialized 不得有其他 params）嚴格度不變。
- 不認識的 request（有字串或整數 id，例如 `server/discover`、`resources/list`、`prompts/list`）不再 403：gateway 自己回 HTTP 200、`Content-Type: application/json` 的 `{"jsonrpc":"2.0","id":<同 id>,"error":{"code":-32601,"message":"Method not found"}}`；不認識的 notification（無 id，例如 `notifications/cancelled`）回 202。兩者都在 session 檢查前回覆，不轉給子程序、不建 session、不佔 32 個連線名額。權杖檢查仍在最前面：錯誤權杖仍是 `/mcp` 401、密鑰路徑與不存在路徑相同的 404。格式錯誤（id 為 null／布林／小數、params 非物件、多餘頂層 key、帶 id 的 initialized、無 id 的已知 request）維持 403。
- 只接受 `application/json`（Accept 不含 `text/event-stream` 與 `*/*`）的 client，initialize 的回覆改用 JSON（子程序以 SSE 回時也是）。其他回覆的 SSE 轉 JSON 未做：MCP 規定 client 必須同時接受兩者，改動 streaming 路徑風險較大。

測試：`tests/test_claude_ai_connector.py`（Claude.ai 形狀的 initialize 在兩條路徑成功且子程序收到的 params 不含 `_meta`；tools/list、tools/call、ping、notifications/initialized 帶 `_meta` 轉送時已剝除；`_meta` 非物件或過大被拒；`server/discover` 等回 200 + -32601 且未轉送；不認識的 notification 回 202 未轉送；錯誤權杖對 `server/discover` 仍 401／404；名額全滿時 `server/discover` 仍回答；工具權限不退化）。`tests/test_boundary.py`、`tests/test_real_products.py`、`tests/test_batch2_runtime.py` 與 `packaging/container_probe.py` 中「不認識方法回 403」的斷言改為 200 + -32601（仍斷言未轉送）。修正後尚未以真實 Claude.ai 重測。

五、工具呼叫被拒時改為正常回話說明原因（2026-10-14 實機發現）。經 Claude.ai 形狀的請求，Odoo `aggregate_records` 的 group_by 不是 `'active'`、`schema_catalog` 的 limit 大於 1、`get_model_fields` 的欄位不在白名單、LiteLLM `litellm_model_info` 的 id 含 `/`、n8n `validate_workflow` 少節點，都得到 HTTP 403 `{"error":"request denied"}`；Claude.ai 只看到傳輸錯誤，看不到原因，無法自行修正重試。原因：`gateway.serve()` 把 `policy.authorize()` 的每個 Denied 一律轉成 403。

修正（`packages/mcp-admin-core/mcp_admin_core/policy.py`、`gateway.py`）：

- `policy.ToolCallRefused`（Denied 子類別，`str()` 仍是原本的拒絕文字）：格式正確的 tools/call（字串或整數 id、params 是物件且只有 `name`（字串）與 `arguments`）遇到四種拒絕時拋出，`error()` 產生 JSON-RPC 錯誤物件：
  - 工具不存在、被停用或寫入工具未授權：`-32602`「Unknown tool」，`data: {"tool": <名稱，截到 128 字>}`；不區分是哪一種。
  - 參數驗證失敗：`-32602`「Invalid params」，`data: {"tool", "errors": [{"field", "message", "type"}]}`，最多 20 筆、每筆 message 截到 300 字。不讀 pydantic 的 `input`／`ctx`；`field` 只保留整數索引與該參數模型 JSON schema 內出現的名稱（屬性名、`$defs` 名、title、字串 const／enum 值），其他（多餘鍵、dict 的鍵）顯示為 `*`；`message` 只對訊息模板僅含固定文字或 schema 限制的類型（`missing`、`extra_forbidden`、`literal_error`、`string_pattern_mismatch`、`too_long` 等，見 `PLAIN_ERROR_TYPES`）沿用 pydantic 說明；`value_error`／`assertion_error` 只在自訂訊息是純文字（無引號、冒號）時沿用（Python 內建 ValueError 會用引號帶出原值）；其他類型（`union_tag_invalid` 會帶出輸入的 tag、各種 `*_parsing`／`url_*`／`json_invalid` 會帶出解析器訊息、自訂類型）改用固定說明。最後若說明含有呼叫者參數中任何長度 ≥3 的字串（鍵或值，不分大小寫；本身就是 schema 名稱或允許值者除外），也改用固定說明。
  - 寫入操作未開放：`-32602`「Operation not permitted」，`data.reason` 為固定文字「write operation disabled by the add-on policy; an administrator can enable it in the add-on panel」。
  - 後端未設定：`-32603`「Backend not configured」，`data: {"tool"}`。選 -32603 而非 -32602：參數本身有效，換參數也不會成功，是 add-on 端的設定狀態；-32602 會讓模型以為改參數就能過。
- `gateway.serve()`（`/mcp` 與 `/private_<token>/mcp` 同一段程式）：第一次 authorize 遇到 ToolCallRefused 時先記下，照原順序做 header 檢查與 session 檢查；請求帶格式正確的 `Mcp-Session-Id` 時，以重新讀取的狀態再驗一次權杖與 policy（讀 body 期間可能已撤銷權杖或改了 policy），仍被拒就回 HTTP 200、`Content-Type: application/json`、`Cache-Control: no-store` 的 `{"jsonrpc":"2.0","id":<同 id>,"error":...}`，不取 slot、不轉給子程序、不建 session；若此時 policy 已允許，就走原本的轉送路徑。取得 slot 後的重驗（等待期間 policy 改變）若遇到 ToolCallRefused，也回同樣的 JSON-RPC（slot 由 finally 釋放，子程序不會收到），不再是 403。
- 沒帶 `Mcp-Session-Id`（或 session 相關 header 格式錯誤）的被拒呼叫維持 0.1.13 的 403：理由只在已初始化的 session 內回覆，與一般 tools/call 需要 session 一致，也不改變 session 檢查的位置。權杖檢查仍最先（錯誤權杖 401／404）。其他 Denied（JSON-RPC 格式錯、id 型別錯、`_meta` 不合法、tools/call 多餘的 params 鍵或 name 非字串、initialize 參數錯、帶 id 的 initialized 等）維持 403。
- 權限沒有放寬：工具白名單、參數模型、寫入閘與後端需求的判斷與順序完全不變，只改回應形式；錯誤內容不含權杖、後端網址、憑證或參數值。

連帶更新：`packaging/denial_probe.py`（容器驗收的拒絕斷言：帶 session 的拒絕必須是 -32602 且 `data.tool` 相符、沒有 result，後端呼叫數不變）、`packaging/test_denial_probe.py`；`packaging/ha_p9_probe.py` 的 plan 模式（denials 接受 403 或 gateway 的 -32602／-32603 JSON-RPC 錯誤；reads 必須有 result，避免把 200 的拒絕誤判成讀取成功）與 `packaging/test_ha_p9_probe.py`、`p9_plan.py` 說明、`docs/operations/ha-p9-kit.md`。`packaging/container_probe.py` 重啟後的拒絕檢查不帶 session，仍是 403，未改。

測試：新增 `tests/test_tool_call_refusals.py`（四種拒絕在兩條路徑回 200 + 正確 code／message／data；以含標記字串的錯誤參數與鍵驗證回應不含輸入值；子程序未收到請求；名額全滿時仍回答；slot 後 policy 改變回同樣 JSON-RPC；第一次被拒但新狀態允許時照常轉送；沒 session 或 session header 錯誤仍 403；其他格式錯誤仍 403；2026-10-14 實測的五種參數錯誤各自的說明；`argument_errors` 對 dict 鍵、Python ValueError、含輸入字串的說明、筆數與長度上限）。既有 22 個測試檔中「帶 session 的 tools/call 被拒回 403」的斷言改用新 helper `tests/tool_refusal.py`（必須是 HTTP 200、`application/json`、`no-store`、只有 jsonrpc／id／error 且 code／message 為四種之一），各處原本「子程序／後端未被呼叫」的斷言保留不變；`test_claude_ai_connector.py` 的工具 policy 案例分成 JSON-RPC 拒絕與仍為 403 的格式錯誤兩類。修正後尚未以真實 Claude.ai 重測。

此 repo 七個產品共用 VERSION、initialize 身分、manifest、Dockerfile 與 CI/release 版本，因此一致準備 0.1.14；不新增版號分流機制。新版本改變 core VERSION、image labels 及 source revision，必須產生新 image ID，不能 retag 或繼承 0.1.11／0.1.12／0.1.13 映像驗收。

後續由主控核對 hosted CI、builder admission 與候選 image/test/scan receipts，再在 PaaS 已建立的 HAOS VM 完成實機驗收（含重開機後七支自動啟動、真實 Claude.ai 自訂連接器連線與工具被拒時看得到原因）。已安裝且使用者曾手動切換「開機時啟動」的實例，可能保留其個別設定，升版後需在 HA 上逐支確認。主控統一 release/merge/部署；本紀錄不宣告商用 PASS。
