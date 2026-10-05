# MCP client 連線（待真實 client／HA 驗收）

**n8n 管理 UI/provider 已本地串接，但映像與 HA 尚未驗收；其他六類正式管理仍 fail closed。
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

工具預設唯讀，有些已支援 schema 比上游更窄，未支援 119 tools 一律 deny。
寫入需有效 HA 管理員 UI 的逐工具／operation exact grant，且符合參數與 disabled gate；
v3 保存取代全部 `enabled_write_tools` 並關閉 legacy global，不能僅用 global false 當撤銷；
直接偽造 `tools/call` 不能繞過。[工具表](../tool-surface.md) 是唯一支援對照。

## Token 事件與故障

- 缺失／錯誤／撤銷 Bearer：401。不要透過換 URL path、HA headers 或 cookie 規避。
- 工具不支援／停用／write 未開：403；不應因此開全權限後端帳號。
- 輪替後所有 client 更新秘密；舊 token 的新請求與 stream 後續轉送被拒。
  已送到 backend 的工作不會交易式回滾；輪替不等於取消後端工作。
- 備份還原會復活備份中的 token／policy，需核對舊 token 暴露風險，再經批准流程輪替。
- 503 readiness 可能只是未設定／backend 離線；不要自動重啟 HA 或既有服務。
- initialize 回 HTTP 503＋JSON-RPC 錯誤 `BACKEND_UNAVAILABLE`（Retry-After 5，0.1.2 起）：child 沒有回覆這次初始化，
  通常是後端連不上（例如 Odoo Manage 每個連線階段都要先連 Odoo），但也可能是 child 本身異常；沒有 session id，
  稍後重新 initialize 即可。502 是 child 回了格式錯誤或過大的回覆。

記錄每個真實 client 版本、network mode、正確 DNS/port（公開證據需匿名化）、
初始化/list/read/stream/reconnect／缺錯撤 token 結果；不保存秘密或 raw payload。
目前同 HA Pi／Omnigent／Hermes、LAN client 以及 HA E2E 全部待驗收。
