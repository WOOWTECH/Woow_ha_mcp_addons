# MCP client 連線（真實 client 待驗收）

**七支 0.1.7 映像已發佈；管理面板與 provider 已在測試 HA 實測（0.1.7，七支：owner 可用、一般使用者 403）；真實 MCP client 尚未驗收（見文末）。
以下是配置形狀，不是可用憑證或繞過授權操作。** 支援的本地契約是 Streamable HTTP（回應可含 SSE），不是 legacy `/sse`。
0.1.14 起有兩種接法，用的是**同一把** Add-on 權杖（管理面板「連線與權杖」頁；重新產生／撤銷對兩種接法同時生效）：

| 接法 | 網址 | 權杖放哪裡 | 適用 |
|---|---|---|---|
| 一、Bearer header | `<端點>/mcp` | `Authorization: Bearer <token>` header | 能自訂 header 的 client（例如 Claude Code、腳本；其他 client 依其文件確認） |
| 二、密鑰網址 | `<端點去掉結尾 /mcp>/private_<token>/mcp` | 網址路徑裡 | 不能帶自訂 header 的 client：**Claude.ai 網頁版自訂連接器** |

能帶 header 的 client 一律用接法一；接法二只給做不到的 client。

## Endpoint 與網路

- 同 HA bridge：`http://<實際安裝後顯示的完整-addon-DNS>:8081/mcp`。
  實際 hostname 與 repository 身分／slug 有關，必須從這次安裝查證，不猜
  固定 repository hash，也不重用舊商店 DNS。
- LAN：`http://<HA-LAN-IP>:<本產品明確配置的host-port>/mcp`。預設 `8081/tcp: null`
  不做 LAN host mapping；跨不可信網路必須另行核准 TLS／路由，沒有預設公網。
- Claude.ai（接法二）從 Anthropic 的雲端連線，不是從你的瀏覽器：端點必須是網際網路連得到的 **HTTPS** 網址
  （例如經 Cloudflare Tunnel／反向代理轉到 Add-on 的 8081）。Add-on 本身不提供 TLS、公網或 tunnel；這些由你另行設定與核准。
  反向代理要把 `/private_<token>/mcp` 原樣轉給 Add-on（不改寫路徑、不加查詢參數），並且**不要記錄這段路徑**（見下方「接法二」）。
- Pi／Omnigent／Hermes 的實際安裝可能 host-network 或不同隔離網路；bridge DNS
  不一定可達。逐 client／版本／transport 驗證，必要時才配置唯一 LAN port。
- Ingress iframe 的 origin、`/api/hassio_ingress/...`、8099 都**不是** MCP URL。
  不從 browser `window.location.origin` 推導。管理 UI 與 MCP token 完全分離。
- 管理面板「MCP 用戶端端點」存的是**不含權杖**的 `/mcp` 網址（`PUT /api/endpoint {"endpoint": "https://…/mcp"}`；必須以 `/mcp` 結尾，
  不可含帳密、查詢參數或片段，可清除為 `null`）。它只用來產生連線範例與接法二的網址，不影響 Add-on 實際監聽的位址。

## 接法一：Bearer header

各 client key 名稱要以其已安裝版本文件為準，不承諾下列通用 JSON 可直接匯入：

```json
{
  "transport": "streamable-http",
  "url": "http://<verified-addon-dns>:8081/mcp",
  "headers": {"Authorization": "Bearer <從批准管理流程安全取得的獨立token>"}
}
```

這個接法下不要把 token 放在 URL path/query、同步設定庫、命令列參數、screenshot 或 log。
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
transport session ID 不是額外認證。`/mcp` 帶瀏覽器 `Origin` header 一律 403（不變）；不承諾
browser SDK 或 SaaS OAuth client 相容。錯誤、缺少或已撤銷的 Bearer 回 401（帶 `WWW-Authenticate: Bearer`）。

## 接法二：Claude.ai 自訂連接器（密鑰網址，0.1.14 起）

Claude.ai 網頁版的自訂連接器（custom connector）只能填網址與選填的 OAuth 設定，無法帶自訂 `Authorization` header。
這時把權杖放進路徑：

```text
https://<你的對外網址>/private_<token>/mcp
```

1. 在管理面板「連線與權杖」頁，先把「MCP 用戶端端點」設成 Claude.ai 連得到的 `https://…/mcp` 並儲存。
2. 按「顯示 Claude.ai 連線網址」，確認後網址只顯示 60 秒（與「顯示權杖」同一個 CSRF 保護的 reveal 流程；離開頁面、切換視窗即隱藏），
   按「複製 Claude.ai 連線網址」。沒設定端點時按鈕停用並顯示說明，不會產生猜測的網址。
3. 在 Claude.ai 新增自訂連接器，把網址貼進伺服器網址欄位；OAuth 進階設定留空。

**這個網址等同密碼。** 拿到網址的人不需要其他東西就能以本 Add-on 目前的工具權限呼叫工具。只貼進 Claude.ai 的連接器設定；
不要分享、截圖、貼到聊天、Git、工單或文件。網址可能外洩（被分享、出現在代理或 CDN 的 log、瀏覽器紀錄）時，立刻在管理面板按
「重新產生」：舊網址（和舊 Bearer）立即失效，再把新網址貼回 Claude.ai。不再使用時按「撤銷權杖」。

Gateway 在這條路徑上的行為：

- 路徑裡的權杖與 Bearer 用同一把，以固定長度摘要做常數時間比對。權杖錯誤、空白、已撤銷或已輪替掉時，回應與「不存在的路徑」
  完全相同（404、同樣的 body 與 headers，沒有 `WWW-Authenticate`），不透露是哪一種原因；405（方法）等其他檢查都排在這之後。
  請求處理途中權杖被撤銷或輪替，同樣回 404（Bearer 路徑是 401）。
- 請求自帶的 `Authorization` header 一律忽略：不能用它開啟錯誤的密鑰路徑，錯誤的值也不影響正確的密鑰路徑。
- 允許帶 `Origin` header（Bearer 的 `/mcp` 仍然 403），但 `Origin` 不會轉給子程序。
- 其他規則與 `/mcp` 相同：查詢參數 400、方法 405、initialize 以外沒帶 `Mcp-Session-Id` 回 400、工具 policy 拒絕（見下）、
  共用的同時連線上限與 session 規則；session 結束用 `DELETE /private_<token>/mcp`。
- 兩條路徑相同（0.1.14 起）：params 的 MCP 保留欄位 `_meta`（例如 Claude.ai 帶的 traceparent）接受為至多 8 KiB 的物件，
  轉給子程序前移除；gateway 不提供的 JSON-RPC 方法（例如 Claude.ai 先送的 `server/discover`、`resources/list`）由 gateway
  自己回 HTTP 200 的 `-32601 Method not found`，不認識的 notification 回 202，都不需 session、不轉給子程序。
- 工具呼叫被拒（兩條路徑相同，0.1.14 起）：見下方「Token 事件與故障」；帶 session 的拒絕回 JSON-RPC 錯誤說明原因，
  Claude.ai 會把它當成工具錯誤顯示給模型，模型可據此修正參數重試。
- Add-on 自己的 log 不記錄存取紀錄（uvicorn `access_log` 關閉），而且任何 log 行裡的 `/private_<…>/` 都會被遮成
  `/private_[REDACTED]/`（含錯誤 traceback）。Add-on 前面的反向代理、tunnel 或 CDN 的 log 不在這個保護範圍內，請自行關閉或遮罩。

2026-10-14 首次以真實 Claude.ai 連 PaaS 測試 VM：Claude.ai 送的 `server/discover` 與帶 `_meta` 的 `initialize` 都被 0.1.12 候選回 403，0.1.13 候選已修正；同日經 Claude.ai 呼叫工具時，參數不符（例如 Odoo `aggregate_records` 的 group_by 不是 `active`、`schema_catalog` 的 limit 大於 1、LiteLLM `litellm_model_info` 的 id 含 `/`、n8n `validate_workflow` 少 nodes）也都只得到 HTTP 403，Claude.ai 只看到傳輸錯誤，0.1.14 改為回 JSON-RPC 錯誤說明原因。兩項都隨 0.2.0 發佈（0.1.14 未發佈；見 [0.1.14 紀錄](release-decision-0.1.14.md) 與 [0.2.0 紀錄](release-decision-0.2.0.md)）；修正後尚未以真實 Claude.ai 重測（目前只有本機 mock 與單元／整合測試）。

0.2.0 起是完整版（2026-10-15 使用者決定）：七支開放子程序的全部工具（合計 183 個），全部工具與寫入預設開啟（新安裝與從 0.1.x 升級時），管理員可在管理面板逐一停用或取消寫入，風險見 [寫入預設開啟](guide.md#寫入預設開啟)。tools/list 的 inputSchema 是子程序自己的（經 provider-safe 正規化），tools/call 參數原樣轉給子程序，參數錯誤由子程序回覆；gateway 只檢查工具名在名單內、未停用、寫入工具或寫入 operation 有 grant，不符時回 0.1.14 起的 JSON-RPC 錯誤（見下）。直接偽造 `tools/call` 不能繞過這些檢查。[工具表](../tool-surface.md) 是唯一支援對照。請求上限 16 MiB。

## Token 事件與故障

- 缺失／錯誤／撤銷 Bearer：401。密鑰網址的權杖錯誤／撤銷：404。不要用 HA headers 或 cookie 規避。
- 工具呼叫被拒（0.1.14 起）：帶 `Mcp-Session-Id`、格式正確（字串或整數 id、params 只有 `name`（字串）與 `arguments`）的
  tools/call，被 policy 拒絕時由 gateway 回 HTTP 200、`application/json`、`Cache-Control: no-store` 的 JSON-RPC 錯誤，
  不轉給子程序、不開 session、不佔同時連線名額（權限本身不變，同樣的呼叫照樣被拒）：
  - 工具不存在、被停用或寫入工具未授權：`-32602`「Unknown tool」，`data` 只有 `tool`（截到 128 字）；不區分是哪一種。
  - 參數驗證失敗：`-32602`「Invalid params」，`data.errors` 每筆有 `field`（例如 `group_by.0`）、`message`（pydantic 說明，
    例如 `Input should be 'active'`，至多 300 字）、`type`（例如 `literal_error`），最多 20 筆。**不回顯任何參數值**：
    schema 沒有的鍵名（多餘欄位、dict 的鍵）顯示為 `*`；說明可能夾帶輸入值的錯誤類型（解析錯誤、tag 不符、Python 自己的
    ValueError 等）改用固定說明，說明中出現呼叫者送的字串（schema 自己的名稱與允許值除外）時也改用固定說明。
  - 寫入操作未開放（例如 n8n 資料夾 create／rename）：`-32602`「Operation not permitted」，`data.reason` 說明管理員可在面板開啟。
  - 後端未設定：`-32603`「Backend not configured」（參數本身沒錯，換參數也不會成功，要管理員先設定 add-on）。
  例：`{"jsonrpc":"2.0","id":7,"error":{"code":-32602,"message":"Invalid params","data":{"tool":"schema_catalog",
  "errors":[{"field":"limit","message":"Input should be less than or equal to 1","type":"less_than_equal"}]}}}`。
  沒帶 `Mcp-Session-Id`（或 session header 格式錯誤）的這類呼叫，以及格式錯誤的請求（id 為 null／布林／小數、params 非物件、
  多餘的 params 鍵、`_meta` 不合法、initialize 參數錯、帶 id 的 initialized 等）仍回 403，body 只有 `{"error":"request denied"}`。
  不應因被拒而開全權限後端帳號。已知 client 差異（0.1.5 審查 RC F7）：Python MCP SDK 1.x client 遇到 403 會讓整個 session
  斷線（要重新連線）；TypeScript SDK 只有那一次呼叫失敗。斷線時 Python client 不送 DELETE，子程序的 session 會留下來：n8n 所有
  client 共用 20 個 session，10 分鐘內約 20 次這種拒絕就會用完，之後所有 client 的 initialize 都回 429（JSON-RPC 錯誤 -32000
  「Too Many Requests」），要等閒置 10 分鐘的 session 被回收；其他六支（Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud）
  留下的 session 0.1.8 起閒置 30 分鐘就結束（0.1.7 以前會累積到子程序重啟）。0.1.14 起帶 session 的工具拒絕不再是 403，
  Python client 對 JSON-RPC 錯誤的行為尚未在本 repo 重測。
- Session：先 initialize，之後每個請求都帶 `Mcp-Session-Id`。0.1.8 起 initialize 以外沒帶 `Mcp-Session-Id` 的請求（ping、
  tools/list、tools/call、通知、GET、DELETE）一律由 gateway 回 400，不轉給子程序、不會開 session（有 id 的請求與 GET 是 JSON-RPC
  錯誤 -32000「Bad Request」，通知與 DELETE 沒有內容）。這個檢查排在 Bearer（401）、方法（405）、Origin（403）與 policy（403）
  之後：缺 Bearer 仍是 401，被拒的工具仍是 403。0.1.7 以前，Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud 的子程序
  會為這種請求開一個新 session 並留到子程序重啟；n8n 對這種請求回 400，但沒有 session 的通知回 202。
- Session 結束：client 用完要送 `DELETE /mcp`（帶 `Mcp-Session-Id`）。沒送 DELETE 的 session（例如 client 當掉、斷線，或 TypeScript
  SDK 只呼叫 `close()`：1.30.0 的 `close()` 不送 DELETE，要先呼叫 transport 的 `terminateSession()`）：
  - n8n：不變，所有 client 共用 20 個 session，閒置 10 分鐘回收。
  - Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud：0.1.8 起閒置 30 分鐘由子程序結束（0.1.7 以前留到子程序重啟）。
  被結束的 session，之後用它的請求：
  - Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud：回 404，有 id 的請求與 GET 是 JSON-RPC 錯誤 -32000「Not Found」
    （GET 的 id 是 null），通知與 DELETE 是沒有內容的 404。
  - n8n：有 id 的請求與 DELETE 回 404；GET 回 400（JSON-RPC 錯誤 -32000「Bad Request」，id 是 null）；通知回 202、沒有內容。
  client 要重新 initialize。
  MCP 規範要求 client 收到 404 時重新 initialize；各 client 是否自動這樣做，0.1.8 尚未實測。子程序重啟（含 Add-on 重啟）後
  舊 session 也會失效。
- 輪替後所有 client 更新秘密（Bearer client 換 header，Claude.ai 換成新的密鑰網址）；舊 token 的新請求與 stream 後續轉送被拒。
  已送到 backend 的工作不會交易式回滾；輪替不等於取消後端工作。
- 備份還原會復活備份中的 token／policy，需核對舊 token 暴露風險，再經批准流程輪替。
- 503 readiness 可能只是未設定／backend 離線；不要自動重啟 HA 或既有服務。
- initialize 回 HTTP 503＋JSON-RPC 錯誤 `BACKEND_UNAVAILABLE`（Retry-After 5，0.1.2 起）：child 沒有回覆這次初始化，
  通常是後端連不上（例如已下架的 Odoo Manage 每個連線階段都要先連 Odoo），但也可能是 child 本身異常；沒有 session id，
  稍後重新 initialize 即可。502 是 child 回了格式錯誤或過大的回覆、initialize 協商出的 protocolVersion 不在審查過的四個版本
  （2024-11-05、2025-03-26、2025-06-18、2025-11-25）之內（0.1.8 起；目前只有 n8n 對要求 2024-06-25 的 client 會這樣），
  或根本沒有 child 可轉送。
- n8n 以外各支未設定後端時沒有 child（設定後端後才有；n8n 沒有後端也會啟動內建文件 runtime）。
  2026-10-07 對測試 HA 上未設定後端的 LiteLLM 逐一打 45 個案例，支援的讀取分兩種：標記為需要後端的
  （例如 `litellm_model_info`、`litellm_team_info`、`litellm_list_users`）由 gateway 直接回 403；不需檢查後端就轉送的
  （例如 `litellm_list_models`、`litellm_health_readiness`）和 initialize、tools/list 一樣回 502。
  寫入、暫不支援與不存在的工具照常 403，readiness 503。這些 403 與 502 的 body 都只有 `{"error":"request denied"}`。

記錄每個真實 client 版本、network mode、正確 DNS/port（公開證據需匿名化）、
初始化/list/read/stream/reconnect／缺錯撤 token 結果；不保存秘密或 raw payload。
目前完成的只有 HA 主機上的腳本 probe（[P9 工具](ha-p9-kit.md)，標準庫 HTTP，不是 MCP SDK client）：0.1.1–0.1.6 每版的
initialize／tools/list／讀取／拒絕／缺錯撤 token／後端斷線回歸（[0.1.7 紀錄](ha-test-0.1.7.md)，含 Nextcloud）。同 HA Pi／Omnigent／Hermes、
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
