# MCP client 連線（真實 client 待驗收）

**七支 0.1.7 映像已發佈；管理面板與 provider 已在測試 HA 實測到 0.1.6（owner 可用、一般使用者 403），0.1.7 的測試 HA 回歸待負責人核准窗口
（Nextcloud 還沒在 HA 上實測）；真實 MCP client 尚未驗收（見文末）。
以下是配置形狀，不是可用憑證或繞過授權操作。** 支援的本地契約是
Streamable HTTP `/mcp`（回應可含 SSE），不是 legacy `/sse` 或 token path。

## Endpoint 與網路

- 同 HA bridge：`http://<實際安裝後顯示的完整-addon-DNS>:8081/mcp`。
  實際 hostname 與 repository 身分／slug 有關，必須從這次安裝查證，不猜
  固定 repository hash，也不重用舊商店 DNS。
- LAN：`http://<HA-LAN-IP>:<本產品明確配置的host-port>/mcp`。預設 `8081/tcp: null`
  不做 LAN host mapping；跨不可信網路必須另行核准 TLS／路由，沒有預設公網。
- Pi／Omnigent／Hermes 的實際安裝可能 host-network 或不同隔離網路；bridge DNS
  不一定可達。逐 client／版本／transport 驗證，必要時才配置唯一 LAN port。
- Ingress iframe 的 origin、`/api/hassio_ingress/...`、8099 都**不是** MCP URL。
  不從 browser `window.location.origin` 推導。管理 UI 與 MCP token 完全分離。

## Client 設定形狀（無真實 token）

各 client key 名稱要以其已安裝版本文件為準，不承諾下列通用 JSON 可直接匯入：

```json
{
  "transport": "streamable-http",
  "url": "http://<verified-addon-dns>:8081/mcp",
  "headers": {"Authorization": "Bearer <從批准管理流程安全取得的獨立token>"}
}
```

不要把 token 放在 URL path/query、同步設定庫、命令列參數、screenshot 或 log。
使用 client 的秘密儲存；每 Add-on 一把 token，不承諾 per-client token/OAuth。
不要拿 HA Cookie、Ingress header、backend key 或 session ID 取代 Bearer。

Wire 範例（只列 placeholder；不要將 token 填進可公開的範例檔）：

```http
POST /mcp HTTP/1.1
Host: <verified-addon-dns>:8081
Authorization: Bearer <redacted>
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"approved-client-test","version":"<actual>"}}}
```

依 initialize 回傳協議／session headers，送 `notifications/initialized`，再
`tools/list`，最後該產品已審的無副作用 `tools/call`。成功 list 不等於成功 backend
read。Bearer 要送在每個 POST/GET/DELETE、stream reconnect/session request；
transport session ID 不是額外認證。瀏覽器 Origin 在現有 tracer 拒絕；不承諾
browser SDK 或 SaaS OAuth client 相容。

工具預設唯讀，有些已支援 schema 比上游更窄；七支合計上游 183 個工具中支援 76 個，未支援的 107 個一律 deny。
寫入需有效 HA 管理員 UI 的逐工具／operation exact grant，且符合參數與 disabled gate；
v3 保存取代全部 `enabled_write_tools` 並關閉 legacy global，不能僅用 global false 當撤銷；
直接偽造 `tools/call` 不能繞過。[工具表](../tool-surface.md) 是唯一支援對照。

## Token 事件與故障

- 缺失／錯誤／撤銷 Bearer：401。不要透過換 URL path、HA headers 或 cookie 規避。
- 工具不支援／停用／write 未開：403；不應因此開全權限後端帳號。403 的 body 只有 `{"error":"request denied"}`，
  不說是哪個工具或參數被擋。已知 client 差異（0.1.5 審查 RC F7；0.1.6、0.1.7 都未改，延到 0.1.8，修法待負責人決定）：Python MCP SDK
  1.x client 遇到這個 403 會讓整個 session 斷線（要重新連線）；TypeScript SDK 只有那一次呼叫失敗。斷線時 Python client 不送
  DELETE，子程序的 session 會留下來：n8n 所有 client 共用 20 個 session，10 分鐘內約 20 次這種拒絕就會用完，之後所有 client 的
  initialize 都回 429（JSON-RPC 錯誤 -32000「Too Many Requests」），要等閒置 10 分鐘的 session 被回收；其他五支的子程序沒有
  閒置回收，留下的 session 會累積到子程序重啟（含 Add-on 重啟）。
- Session 結束：client 用完要送 `DELETE /mcp`（帶 `Mcp-Session-Id`）。n8n 的 session 閒置 10 分鐘回收；其他五支的子程序沒有
  閒置回收，沒送 DELETE 的 session 會留到子程序重啟，例如 client 當掉、斷線，或 TypeScript SDK 只呼叫 `close()`（1.30.0 的
  `close()` 不送 DELETE，要先呼叫 transport 的 `terminateSession()`）。這五支收到沒帶 `Mcp-Session-Id` 的 initialize 以外請求
  （ping、tools/list、GET、DELETE 等）也會開一個新 session 並留下來，所以要先 initialize，之後每個請求都帶 `Mcp-Session-Id`。
  0.1.6、0.1.7 仍是如此，延到 0.1.8。0.1.7 新增的 Nextcloud 子程序和 EMQX 一樣是 FastMCP 3.4.5、啟動時沒有設定閒置回收，
  預期和這五支相同（未另外實測）。
- 輪替後所有 client 更新秘密；舊 token 的新請求與 stream 後續轉送被拒。
  已送到 backend 的工作不會交易式回滾；輪替不等於取消後端工作。
- 備份還原會復活備份中的 token／policy，需核對舊 token 暴露風險，再經批准流程輪替。
- 503 readiness 可能只是未設定／backend 離線；不要自動重啟 HA 或既有服務。
- initialize 回 HTTP 503＋JSON-RPC 錯誤 `BACKEND_UNAVAILABLE`（Retry-After 5，0.1.2 起）：child 沒有回覆這次初始化，
  通常是後端連不上（例如已下架的 Odoo Manage 每個連線階段都要先連 Odoo），但也可能是 child 本身異常；沒有 session id，
  稍後重新 initialize 即可。502 是 child 回了格式錯誤或過大的回覆，或根本沒有 child 可轉送。
- n8n 以外各支未設定後端時沒有 child（設定後端後才有；n8n 沒有後端也會啟動內建文件 runtime）。
  2026-10-07 對測試 HA 上未設定後端的 LiteLLM 逐一打 45 個案例，支援的讀取分兩種：標記為需要後端的
  （例如 `litellm_model_info`、`litellm_team_info`、`litellm_list_users`）由 gateway 直接回 403；不需檢查後端就轉送的
  （例如 `litellm_list_models`、`litellm_health_readiness`）和 initialize、tools/list 一樣回 502。
  寫入、暫不支援與不存在的工具照常 403，readiness 503。這些 403 與 502 的 body 都只有 `{"error":"request denied"}`。

記錄每個真實 client 版本、network mode、正確 DNS/port（公開證據需匿名化）、
初始化/list/read/stream/reconnect／缺錯撤 token 結果；不保存秘密或 raw payload。
目前完成的只有 HA 主機上的腳本 probe（[P9 工具](ha-p9-kit.md)，標準庫 HTTP，不是 MCP SDK client）：0.1.1–0.1.6 每版的
initialize／tools/list／讀取／拒絕／缺錯撤 token／後端斷線回歸（[0.1.6 紀錄](ha-test-0.1.6.md)；0.1.7 的測試 HA 回歸待負責人核准窗口，
Nextcloud 還沒在 HA 上實測）。同 HA Pi／Omnigent／Hermes、
LAN client、HA Assist、n8n AI Agent 等真實 client 仍待驗收。

**AI client 相容性（0.1.6 已修正）：** 0.1.6 把下面 7 個工具宣告的 `inputSchema` 頂層改成單純的 `type: object`（拿掉 `oneOf`／`allOf`，
分支規則寫進 description；gateway 驗證不變）。2026-10-07 以同樣五個模型經 OpenRouter 複驗，六支全部接受（30/30）；0.1.7 新增的 Nextcloud 沒有做這項測試；直連
Anthropic／OpenAI API 與實際 client 仍未測。以下是 0.1.5 的紀錄。

**0.1.5 的已知相容性問題（0.1.6 已修正）：** 2026-10-07 不經 HA 的模型供應商測試（只送 0.1.5 的工具 schema，只走 OpenRouter）：Claude Sonnet 4.5、
GPT-4o-mini 拒收 n8n、Odoo、Hermes 的完整工具清單（HTTP 400；7 個工具的 `inputSchema` 頂層有 `oneOf`／`allOf`），
OpenDesign、EMQX、LiteLLM 兩家都接受；另外三個模型（GLM-4.6、MiniMax-M2、Llama-3.3-70B）六支都接受。
供應商拒絕的是整個請求，不只那幾個工具。直連 Anthropic／OpenAI API 與實際 client（Claude Code、HA 對話代理、n8n AI Agent 等）
都沒測，不知道它們會不會先改寫 schema；原樣轉送的話，預期這兩家模型在這三支一個工具都叫不到。client 若把多個 MCP server
的工具併成一個請求送給這兩家模型，只要含這三支的工具，整個請求都會 400，連其他 server 的工具也不能用（依同一個錯誤推論，未實測）。
原始紀錄在 Claude 交付線 `e2e/B0-provider-smoke-20261007T0941Z/`（不在 repo）。
