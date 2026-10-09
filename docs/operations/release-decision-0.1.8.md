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
  通知與 DELETE 是沒有內容的 400，和以前子程序拒絕時 gateway 轉出的形狀相同，只是不帶子程序新開的 session id；都帶 `Cache-Control: no-store`。
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

## 待辦（0.1.8 範圍內，進行中）

- F6（0.1.6 R1 F6）：initialize 回覆的 serverInfo、instructions 不再是子程序內容。
- GATEWAY-3：五支 Python 子程序（加上 Nextcloud）的 session 閒置回收；先量測單一閒置 session 的記憶體。
- F7 不在本版自行決定：負責人在 AI 實測 Stage 0 之後決定（f7-design.md）。
