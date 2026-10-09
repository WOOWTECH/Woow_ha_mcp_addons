# 0.1.8 發佈紀錄（草稿，開發中）

> 本機分支 `local/claude-0.1.8`，尚未建置、審查或發佈。下列每一項都改到 gateway 或子程序的行為，留給 0.1.8 RC 審查。
> 版號（config.yaml、`packaging/validate.py` 的 VERSION、Dockerfile 的 BUILD_VERSION）在發版準備時才改成 0.1.8。

## 內容

### 映像標籤（61c72da）

七支 Dockerfile 的 `io.hass.name`／`io.hass.description` 改成和 config.yaml 相同（「Woow ○○ MCP Server」與現行說明）；
`packaging/validate.py` 會擋不一致。

### GATEWAY-2：沒有 session 的請求由 gateway 回 400（0.1.6 RC GATEWAY-2）

- 行為：除了 initialize，沒帶 `Mcp-Session-Id` 的 POST（請求或通知）、GET、DELETE 由 gateway 直接回 400，不轉給子程序。
  Bearer（401）、方法（405）、Origin（403）、query（400）、body（415／413／400）與 policy（403）的檢查都在它前面，順序不變。
- 回覆：有 id 的請求與 GET 是 `child_status_reply` 的形狀（`{"jsonrpc":"2.0","id":<id 或 null>,"error":{"code":-32000,"message":"Bad Request"}}`），
  通知與 DELETE 是沒有內容的 400，和以前 gateway 轉出子程序拒絕時的形狀相同，只是不帶子程序新開的 session id；都帶 `Cache-Control: no-store`。
  n8n 例外（審查 F-3 更正）：n8n-mcp 2.91.0 對沒有 session 的請求、GET、DELETE 本來就回 400、不開 session，但對沒有 session 的通知回 202
  （`dist/http-server-single-session.js:590–597`），現在這種通知改由 gateway 回 400。994c49c 的 commit 說明與 0.1.8 CHANGELOG 初稿寫成
  「n8n 本來就回 400」，以本段為準。
- 原因：六個子程序都是有狀態的。mcp 1.28.1（FastMCP 3.4.5 沿用）的 session manager 對沒有 session 的非 initialize 請求，
  會先建 transport、啟動 server task，再回 400 並帶上新 id；這些 session 沒有閒置回收（見 GATEWAY-3），會留到子程序重啟。
  MCP Streamable HTTP 規範：要求 session 的 server 對沒帶 session id 的非 initialize 請求 SHOULD 回 400。
- 測試：`tests/test_session_required.py`（15 項；撤回修正後 7 項失敗：ping／tools/list／tools/call／通知／DELETE／GET 與 50 次 ping
  都會轉給子程序）。既有 10 個測試檔的請求原本沒帶 session id，補上 `Mcp-Session-Id`（行為不變）；
  `test_initialize_cleanup.py::test_other_requests_never_end_a_session` 的「client 沒帶 session」分支改為預期 400 且子程序收不到請求。
- 對 e2e 的影響（只記錄，e2e 分支未改）：e2e 案例檔中 LiteLLM 的 `LL-HR-07`、`LL-NL-LM`、`LL-NL-LT`、`LL-NL-LIST`、`LL-FIN-NL-LM`
  在沒有 session 時送 tools/list 或放行的 tools/call，預期「轉送後因沒有子程序回 502、body `{"error":"request denied"}`」；
  綁 0.1.8 時要改成 400、body 為上面的 JSON-RPC 錯誤（outcome 改判 rejected）。其他沒有 session 的案例（PROTO-04／05 的格式錯誤、
  401、403、405、413、415）在這個檢查之前就被擋，不受影響；PROTO-06（帶了不存在的 session id）照舊轉給子程序。

### F6：initialize 的回覆由 gateway 組成（0.1.6 R1 F6）

- 行為：initialize 成功時，result 只有 `protocolVersion`（子程序的值，必須是審查過的 MCP 版本，見下一節）、`capabilities: {"tools": {}}`、
  `serverInfo: {"name": "woow-mcp-<產品>", "version": <add-on 版號>}`，以及（只有 Nextcloud）gateway 自己的 `instructions`。
  子程序的 serverInfo（含 title、icons、websiteUrl）、instructions、`_meta` 與其他欄位都不再轉送。JSON-RPC 錯誤回覆照舊。
- 原因：Claude Code 會把 instructions 放進模型的 system prompt。目前會送 instructions 的子程序有 Odoo、EMQX、LiteLLM 與 Nextcloud：
  EMQX 與 LiteLLM 的文字描述的是上游的全部工具（斷線、刪憑證、對話補全、發金鑰等），本 add-on 都隱藏或拒絕；
  Nextcloud 是 WOOWTECH 自己的 server，說明有用（先讀再寫、etag），所以改由 gateway 送一份審查過的副本
  （`products.INSTRUCTIONS`；`tests/test_initialize_identity.py` 會比對 vendored 原文，re-vendor 改了說明就失敗，要先審再改副本）。
  Odoo（審查 F-2 更正）送的是 odoo-mcp 1.1.0 通用的一句「MCP Server for interacting with Odoo ERP systems」（`server_core.py:100、130–135`），
  不再轉送；啟用中的 `health_check` 工具結果仍帶 `server.instructions`（`tools_read.py:216`），是工具輸出、內容無害，維持不變。
  n8n、Hermes、OpenDesign 的子程序沒有送 instructions，只有 serverInfo 改變。
- 版號：新增 `mcp_admin_core.VERSION`（目前 0.1.7），`packaging/validate.py` 要求它等於發版的 VERSION，發版準備時一起改成 0.1.8。
- 刻意不做：serverInfo 不加 title（只放規範必填的 name、version，避免任何 client 的嚴格 schema 出問題）。
- 測試：`tests/test_initialize_identity.py`（新）；`test_initialize_reply.py`、`test_sse_sanitize.py`（BOM 測試改用 protocolVersion 區分；
  lone surrogate 測試改用錯誤訊息，因為 initialize 的 result 已沒有子程序文字）、`test_initialize_cleanup.py`（拿掉「filtering 時狀態錯誤」
  這個已不存在的拒絕路徑：initialize 的回覆不再讀取狀態）。真實子程序測試：`test_real_products.py`（六支經 run_product 的 serverInfo
  與 instructions）、`test_real_n8n.py`、`test_nextcloud_child.py`、`integration_local_runtime.py`（root 才跑）改為新的名稱。
  撤回 gateway 修正後 6 項失敗。
- 對 e2e 的影響（只記錄）：e2e 案例對 initialize 只斷言 `result.capabilities` 與 `result.protocolVersion`，不受影響；
  `ha_p9_probe.py` 報告的 `serverInfo=` 會從 `n8n-documentation-mcp` 等變成 `woow-mcp-<產品>`（只是報告文字）；
  AI 測試 harness（`e2e/ai/mcp_client.py`）只記錄 serverInfo。AI 實測若比較「有無 instructions」，Nextcloud 以外的產品已沒有 instructions。

### initialize 的 protocolVersion 只接受審查過的版本（0.1.8 審查建議 6b）

- 行為：initialize 回覆的 `protocolVersion` 必須是 2024-11-05、2025-03-26、2025-06-18、2025-11-25 之一（0.1.5 起原本是任何日期格式）；
  其他值 gateway 回 502，並照 0.1.6 的 R2 收尾結束子程序剛開的 session。
- 影響：Python 子程序（mcp 1.28.1）只會回這四個之一（client 要求別的版本時回 2025-11-25）。n8n-mcp 2.91.0 自己協商：n8n／langchain
  client 一律 2024-11-05，client 要求 2025-03-26、2024-11-05、2024-06-25 時照回，其他回 2025-03-26；所以只有要求 2024-06-25 的 client
  會從「照轉」變成 502（MCP 沒有這個正式版本，實務上應該沒有 client 這樣要求）。
- 測試：`tests/test_initialize_identity.py`（四個版本通過；2024-06-25、2024-10-07、2025-03-27、前後空白、非字串等 11 種回 502）、
  `tests/test_initialize_cleanup.py` 新增「protocolVersion not reviewed」拒絕情境（子程序的 session 被結束、id 與子程序文字不外流）。

### GATEWAY-3：Python 子程序結束閒置的 session（0.1.6 RC GATEWAY-3）

- 量測（Claude 交付線 `reviews-018/idle-session-measure.md`，本機、假後端）：每個閒置 session 佔 Odoo 約 350 KiB、Hermes 約 100、
  OpenDesign 約 50–70、EMQX 約 100、LiteLLM 約 80–90、Nextcloud 約 90–100 KiB；每分鐘留一個，Odoo 一天約 480 MiB、其他 70–140 MiB。
- 行為：`apps/runtime/session_idle.py` 的 `install()` 讓這個程序建的每個有狀態 `StreamableHTTPSessionManager` 帶
  `session_idle_timeout=1800`（30 分鐘；stateless 與已指定的不動）。Odoo、Hermes、OpenDesign 的 `launch.py` 在建 server 前呼叫；
  EMQX、LiteLLM、Nextcloud 改由 `apps/runtime/run_child.py` 啟動（`python -m run_child <module> …`，`products.child_spec` 的 argv 跟著改）。
  上限時間內沒有任何請求的 session 被 SDK 取消並移除，下一個請求收到 404；有請求就順延。`WOOW_MCP_SESSION_IDLE_SECONDS` 只給測試覆寫
  （1–86400 秒，無效值子程序不啟動）。n8n 不變（n8n-mcp 自己 10 分鐘回收）。
- 測試：`tests/test_session_idle.py`：兩種 SDK（mcp 1.28.1 FastMCP、FastMCP 3.4.5）各自的 venv 裡，預設、指定、stateless、
  位置參數、FastMCP 建的 manager 都拿到正確上限；無效上限拒絕啟動；六個真實子程序（照 add-on 的啟動方式、私有埠、假後端，
  上限縮成 2 秒）閒置的 session 回 404、使用中的回 200。`test_nextcloud_child.py` 的 argv 期待值改為 `-m run_child`。
- 待 RC 審查或負責人決定：30 分鐘是否合適（client 閒置後第一個請求收到 404，Claude Code、n8n、HA 等 client 是否都自動重新
  initialize 沒有實測，要在 e2e／AI 實測補）；`install()` 改的是 SDK 類別的建構子，依賴釘選版本（SDK 改版時找不到參數就拒絕啟動）。
- 對 e2e 的影響（只記錄）：e2e 窗口內同一個 session 最長閒置不會到 30 分鐘；若有案例刻意長時間保留 session，要留意 404。
- 文件（審查 F-1）：Odoo、Hermes、OpenDesign、EMQX、LiteLLM 的 DOCS.md 與 `docs/operations/clients.md` 改寫，Nextcloud 的 DOCS.md 新增 Session 一點：閒置 30 分鐘的 session 由子程序結束，之後用它的請求回 404，client 要重新 initialize；initialize 以外沒帶 `Mcp-Session-Id` 的請求一律回 400、不開 session。n8n 的 session 行為不變（共用 20 個、閒置 10 分鐘回收），DOCS 只補上 400（沒有 session 的通知以前回 202）。
- `docs/tool-surface.json` 重新產生：只多了 `apps/runtime/session_idle.py`、`run_child.py` 兩個檔與三個 `launch.py` 的雜湊，工具本身沒有變。sha256 從 0.1.7 的 `fa924793…` 變成 `75db0eca…`；e2e 案例檔與 scenarios 的 `tool_surface_sha256`（R11）綁 0.1.8 時要改成發版當時的值。

## 本機測試（2026-10-09，Claude 交付線 tests-018/）

- 基準（d01c530）：pytest 1754 passed、1 failed；packaging unittest 147 OK（5 skipped）；validate PASS。
- 三項修正後（77d594d）：pytest 1790 passed、1 failed；packaging unittest 147 OK（5 skipped）；validate PASS。
- 兩次唯一的失敗都是 `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`：它要求以 root 執行，
  這個容器現在是 uid 1000（0.1.7 的 run2 是 root，1755 全過）。與本版修改無關。
- 注意：F6 那個 commit（e792d5a）單獨看會讓 `test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources` 失敗
  （改了 products.py 卻沒更新 `docs/provenance/runtime-patches.json`），在 GATEWAY-3 的 commit（77d594d）一併修正。

## 待辦（0.1.8 範圍內）

- F7 不在本版自行決定：負責人在 AI 實測 Stage 0 之後決定（f7-design.md）。
- GATEWAY-3 改變了 F7 的影響（審查建議）：Python SDK 1.x client 被 policy 的 403 斷線、不送 DELETE 而留下的 session，在 Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud 六支 Python 子程序裡 30 分鐘內就會被回收，不再累積到子程序重啟；n8n 共用 20 個 session、閒置 10 分鐘回收的限制不變，10 分鐘內約 20 次這種拒絕仍會讓所有 client 的 initialize 回 429。F7 本身（403 讓 Python client 整段斷線）沒有改變。f7-design.md 已加註。
