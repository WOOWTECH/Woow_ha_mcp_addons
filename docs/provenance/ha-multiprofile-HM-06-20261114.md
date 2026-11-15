# HA 多帳號 HM-06 provenance：子程式 bearer（一律生效）（2026-11-14；2026-11-15 審查後、rebase 後更新）

## 結論

- 7 支 Python 子程式（Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud、Headscale）只服務自己的 child bearer：
  剛好一個 `Authorization: Bearer <child token>`（`hmac.compare_digest`）才交給 MCP SDK，其他一律 401、沒有本文、不寫細節。
- `WOOW_MCP_CHILD_TOKEN` 缺、空、不是 child_token 的格式（`[A-Za-z0-9_-]{43}`）時，子程式在 patch 任何東西之前就拒絕啟動；
  錯誤訊息是固定字串，不含值。
- 不受開關管：任何產品下一次發版都會帶出去（HM-00 契約第 1.2 節、第 7 節、第 9 節 #37）。
- 單帳號經閘道的行為不變：閘道、健康監看、能力探測本來就帶這個 bearer，`gateway.py`、`health.py`、`capabilities.py` 沒改。
  HM-01 的黃金回歸與兩個契約凍結照過，期望值一個都沒改。
- n8n 不變（本來就驗 `AUTH_TOKEN`，同一個 child_token）；已下架的 Odoo Manage 不變（不跑 session_idle、不拿 bearer），
  寫進 `docs/operations/guide.md`。
- 新測試 `tests/test_child_bearer.py` 28 案，先紅後綠（第 4 節）；12 個臨時突變都被擋下。受影響的既有測試 5 檔 33 案逐案處理，帳本測試由帳本更新處理（第 5 節）。
- 獨立安全審查（repo 外 `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-06.md`）：**修正後通過**，程式沒有安全缺陷。
  必修 3 項都不是程式缺陷，都處理了；建議 7 項都採用。處理見第 13 節：
  - 審查後補的：真子程式測試多驗「其他路徑不驗就不服務」與「拒絕不等 body」；`send()` 不再讀 GET 的 200 串流（回歸時不會卡死）；
    容器探針直連 3000 驗 child bearer（每個產品發版的容器驗收都會跑）；SDK 升版重審清單。
  - **MF-1、MF-2 由主對話定案**（2026-11-15 08:0x，第 12.1 節）。MF-1 選 (a)：n8n 維持現狀，HM-00 的 T-23、I4、契約第 9 節 #37
    照 n8n-mcp 的實際行為改寫（另外收下的三種寫法都要先有自己的 child token，沒有越權）。MF-2：DQ-08 的 HM-06 部分照計畫 §8.3
    （DQ-40 (a) 的細節），寫進 `decisions.md`；listener 檢查仍待定，屬 HM-15。
  - **MF-3 在 rebase 時做了**（第 12.2 節）：HM-04 快照的 12 個 Python 案例加 `WOOW_MCP_CHILD_TOKEN={child_token}`、`changes` 加一筆 HM-06。
- rebase：從 HM-01 的 `32ecac8` 移到 `claude-delivery` `e5fa5c7`（含 HM-00、HM-01、HM-04、HM-17、HM-07）。只有帳本有文字衝突；
  `products.py` 自動合併（HM-04 的 port 參數、HM-07 的 `profile_initial_state` 都在，本片的 env 不變）。帳本以 `claude-delivery`
  為底逐筆合併，兩個列管檔的 SHA-256 用合併後的內容重算；本片在每個檔的增刪行和審查時逐行相同（第 12.2 節）。
- 本機檢查（rebase 後，第 6.3 節）：目標 22 檔 1089 案、0 skip：1088 通過，1 個失敗是 HM-07 已知要 root 的案例（只在 CI 驗）。其中本片 28 案、
  本片的 14 個目標檔 301 案、HM-01 守門 97 案、HM-04 的 `test_child_port_param.py` 233 案（快照同步後）全過。
  packaging unittest `Ran 194`、`OK (skipped=5)`；`validate.py` PASS；`tool_inventory.py --write` 0 差異。全套 pytest 以 CI 為準。
- 兩個預檢（rebase 後的最終 HEAD，含本筆記這一版）：秘密預檢 0 命中（本片 9 個 commit，含本筆記；`--full` 的 HEAD 全檔與全歷史也 0）；
  帳本預檢 OK（167／70／159 個摘要 0 漂移、0 缺檔；改 19 個檔，列管檔 2 個與兩本帳本同步；沒有新增而沒列管的執行期檔）（第 9 節）。
- 容器探針在實際容器裡跑一次，交給 HM-19a 前的 builder 乾跑；不是本片的合併關卡（功能 PR 不改版號、不出貨）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-06（計畫 §8.3、§12.3；風險高、工作量 L；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm06-20261114`（rebase 後 push、開 PR；本片不合併） |
| HA 基準 | `claude-delivery` `e5fa5c7`（#93 HM-07 的合併；含 #89 HM-00、#90 HM-01、#91 HM-04、#92 HM-17）。開發與審查時的基準是 HM-01 的分支 head `32ecac8`；2026-11-15 rebase（第 12.2 節） |
| 依據 | 計畫 §3.3、§8.3、§11.5、§12.0、§12.3 HM-06；HM-00 契約（PR #89）第 1.2 節、第 7 節「子程式 bearer」列、第 9 節 #37；`threat-model.md` I4 與同 uid 信任邊界；`acceptance-matrix.md` T-23；FM-42、FM-92 |
| 決策 | DQ-40 ⑥（7 支 Python 子程式也驗 bearer、驗格式；2026-11-14 使用者採用）。**DQ-08 的 HM-06 部分照計畫 §8.3**：計畫 §13.2 把 DQ-08 列為 DQ-40 的細節（「DQ-40 一次確認後照做」），DQ-40 (a) 是使用者 2026-11-14 13:4x 採用的建議；主對話 2026-11-15 08:0x 確認照做、沒有另問使用者，寫進 `decisions.md` 第 1 節（審查 MF-2，第 12.1 節）。本片的規則就是 §8.3 原文，沒有另定。DQ-08 的另一部分（listener 檢查）仍待定，屬 HM-15（DQ-37、UC-04），本片沒碰。DQ-27（EMQX 子程式端政策）也沒碰 |
| 對齊的 PaaS | 加嚴，不是移植：PaaS 只有 n8n 驗 bearer（`Pc/profiles.py:387-393`；§8.8 #37）。本片沒有移植 PaaS 程式或測試。對齊基準 pin：PaaS main `69ac425`（DQ-06）；到 main `cf3d0d5` 的變動見第 10 節（子程式 bearer 相關的 PaaS 檔沒有可執行的改動） |
| FM | FM-42（子程式 bearer）、FM-92（EMQX：只有「子程式驗入站身分」這一段） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `apps/runtime/session_idle.py` | 新增 `bearer()`：讀 `WOOW_MCP_CHILD_TOKEN`，缺、空、格式不符就 `RuntimeError(REFUSED)`（固定訊息）。新增 ASGI 閘門 `ChildBearer`：剛好一個 `Authorization` 而且值等於 `Bearer <token>`（`hmac.compare_digest`）才交給內層 app；其他 HTTP 請求回 401（`WWW-Authenticate: Bearer`、`Content-Length: 0`、沒有本文）；不是 HTTP 的 scope 不交下去、也不回；`__slots__`、固定的 `repr`。`install()` 在 patch 之前呼叫 `bearer()`；既有的 `__init__` 包裝在 `original(...)` 之後把 `self.asgi_app` 換成 `ChildBearer`。idle 上限、body 上限、冪等標記都不變。沒有另開 `child_auth.py`（計畫允許兩種；掛點就在這支，帳本已列管） |
| `packages/mcp-admin-core/mcp_admin_core/products.py` | `child_spec`：Odoo Manage 以外的 7 支 Python 子程式加 `WOOW_MCP_CHILD_TOKEN`＝state 的 `child_token`。其他變數、argv、工具、授權、state 都不變 |
| `tests/test_child_bearer.py`（新） | 第 4 節。審查後：真子程式測試多驗其他路徑與不送的 body（S-04）；`send()` 遇到 GET 的 200 不讀本文、每個直連請求最多 30 秒（S-05）。rebase 後：n8n 那段註解（`N8N_ALSO_ACCEPTS` 上面）改成引用 MF-1 的定案，測試本身不變 |
| `tests/contract/child_spec_default.json`（HM-04 的快照；rebase 後，審查 MF-3） | 7 支 Python 子程式的 12 個案例，env 在 `PYTHONPATH=…` 後面加 `WOOW_MCP_CHILD_TOKEN={child_token}`（和 `child_spec` 的順序相同）；n8n、odoo-manage 的 4 個案例不動；`changes` 加一筆 HM-06（`slice`、`change`，照檔案既有的英文）。`baseline` 仍是 `bb48449`，`tests/test_child_port_param.py` 不用改 |
| `docs/multi-profile/decisions.md`（HM-00 的檔；rebase 後，審查 MF-2） | DQ-08 的 HM-06 部分從第 2 節（待定）移到第 1 節（已定，照計畫 §8.3；listener 檢查待定、負責片 HM-15）；結論的題數（21 題已定、25 題待定）、第 1 節標題、狀態行、變更紀錄一列 |
| `docs/multi-profile/contract.md`、`acceptance-matrix.md`、`threat-model.md`（HM-00 的檔；rebase 後，審查 MF-1） | 照 n8n-mcp 的實際行為改寫：契約第 9 節 #37 加註（n8n 另外收下的三種寫法都要先有自己的 child token、沒有越權，以及不另外擋的理由）與第 10 節變更紀錄一列；T-23 的 n8n 期望值；I4 的測試欄；後兩份的狀態行。第 7 節「子程式 bearer」列不變 |
| `tests/test_session_idle.py` | 單元測試的子程序環境帶 `C`×43 的 child token（`install()` 沒有它就拒絕啟動） |
| `tests/test_nextcloud_child.py` | env 快照（`spec.env == {...}`）加 `WOOW_MCP_CHILD_TOKEN`；兩處直連子程式的呼叫改帶 child bearer |
| `tests/test_native_probe_separation.py`、`tests/test_real_products.py` | 直連子程式的呼叫改帶 child bearer |
| `tests/test_owned_ports_bearer.py`（HM-01） | 「替身自己產生的 bearer」改用沒有 bearer 的 Odoo Manage spec；真子程式一律驗「不帶 bearer 回 401」（原本只有 n8n）；兩段 docstring 改成現況 |
| `packaging/container_probe.py`（審查後，S-01） | 單帳號階段、確認 3000 只綁 IPv4 loopback 之後，新函式 `assert_child_bearer` 直連 `http://127.0.0.1:3000/mcp`：不帶 bearer、帶另一個 43 字元的值都要 401、沒有 session；帶 state 的 child_token 要 200，開的 session 馬上 DELETE。8 個上架產品（含 n8n）都跑；失敗訊息固定、不含 token。這支檔在容器驗收時以唯讀方式掛進映像，不在映像裡、不在帳本 |
| `packaging/test_container_probe.py`（審查後，S-01） | 2 案，用私有 port 上的假子程式（不碰 3000）：只認自己 bearer 的子程式通過，而且請求依序是「不帶、別的值、自己的、DELETE 那個 session」；不驗、任何 43 字元都收、拒絕自己的、DELETE 不掉，4 種都失敗，訊息固定 |
| `docs/provenance/runtime-patches.json` | `session_idle.py`、`products.py` 重新釘選並加 HM-06 說明；`session_idle.py` 的 guarded sources 由 6 個加到 17 個（第 3.1 節）；`scope` 加一句。審查後：`session_idle.py` 的說明加審查補的測試與 SDK 升版重審清單（S-03；只改文字，摘要不變）。rebase 後：以 `claude-delivery` 的帳本為底逐筆合併（第 12.2 節）；`products.py` 的說明依序是 HM-04、HM-07、HM-06，摘要用合併後的內容重算 |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只換 `apps/runtime/session_idle.py` 的摘要；工具清單不變，`docs/tool-surface.md` 重產後沒有差異 |
| `docs/operations/guide.md` | 安裝檢查表第 6 點加一段（未發版）：3000 上的 Python 子程序只接受 gateway 自己的 child bearer，直連不帶、帶錯或多帶一律 401，沒有有效的 child token 就不啟動；n8n 的子程序本來就只認同一個 child token；Odoo Manage 維持原狀 |
| `docs/provenance/ha-multiprofile-HM-06-20261114.md` | 本筆記 |

沒改：`gateway.py`、`health.py`、`capabilities.py`（本來就帶 child bearer）、`config.py`、`lifecycle.py`、`apps/n8n/`、
`apps/odoo-manage/`、各產品的 launcher、`run_child.py`、測試替身（`tests/owned_*`、`tests/log_scan.py`）、HM-01 的黃金回歸與
契約凍結、`tests/test_child_port_param.py`（HM-04）、HM-07 的測試、版號、`addons/<x>/`、CHANGELOG、`upgrade-notes.yaml`、workflow。
`packaging/` 只改容器探針與它的單元測試（審查 S-01）。HM-00 的文件只改上表的四份（審查 MF-1、MF-2）。
審查後沒有改任何執行期檔：本片對 `session_idle.py`、`products.py` 的改動和審查時逐字相同。`session_idle.py` 的摘要仍是 `207dd2e6…`；
`products.py` 的摘要在 rebase 後換成合併後內容的 `c83a59d0…`（HM-04 的 port 參數、HM-07 的 `profile_initial_state` 加上本片的 env）。

## 3. 設計

### 3.1 掛點

- 7 支 Python 子程式都在 server 建 session manager 之前呼叫 `session_idle.install()`：Odoo（`start_switches.py`；`launch.py`
  再呼叫一次、冪等）、Hermes、OpenDesign、Headscale（各自的 `launch.py`）、EMQX、LiteLLM、Nextcloud（`run_child.py`）。
- `install()` 本來就包住 `StreamableHTTPSessionManager.__init__`。同一個包裝裡，`original(...)` 之後把 `self.asgi_app` 換成
  `ChildBearer(self.asgi_app, expected)`。
- 為什麼包 `asgi_app`：mcp 2.3.0 在 `__init__` 設它（`streamable_http_manager.py:114`）。MCPServer（Odoo、Hermes、OpenDesign）的
  路由是 SDK 的 `StreamableHTTPASGIApp`，直接呼叫 `session_manager.asgi_app`（`:426-427`）；FastMCP 4.1.3（EMQX、LiteLLM、
  Nextcloud、Headscale）的路由呼叫 `handle_request`，它再呼叫 `asgi_app`（`:181`）。只包 `handle_request` 擋不到 MCPServer 那條路。
  這兩個 SDK 裡沒有別的地方讀 `asgi_app`（grep）；子程式也沒有註冊別的 HTTP 路由（沒有 `custom_route`、沒設 auth）。
- 每個 manager 都包，含 stateless（idle 上限只給 stateful，bearer 不分）。閘門在 SDK 的 body 上限外面。SDK 的
  `RequestBodyLimitMiddleware`（`mcp/server/transport_security.py:126-168`）先看 `Content-Length`，再把整個 body（最多 16 MiB）
  讀進記憶體才交給 SDK；閘門在它外面，沒帶對 bearer 的請求一個位元組都不讀，也不能讓子程式先緩衝 16 MiB（審查後的測試驗，第 4.1 節）。
- 帳本的 guarded sources（17 個）：7 個 venv 的 `mcp/server/streamable_http_manager.py`（原本 6 個，補上 Headscale）；Odoo、Hermes、
  OpenDesign 的 `mcp/server/mcpserver/server.py` 與 `mcp/server/lowlevel/server.py`（MCPServer 建路由）；EMQX、LiteLLM、Nextcloud、
  Headscale 的 `fastmcp/server/http.py`（FastMCP 建路由）。SDK 升版時 `tests/test_tool_inventory.py` 會擋，要重新審查掛點。
  和其他 guarded sources 一樣只在測試時比對，執行期不比摘要。審查判斷值得保留（SDK 漂移實驗 S01、S02：路由改成繞過
  `asgi_app` 時，真子程式矩陣與帳本摘要兩層都紅）。
- **SDK 升版重審清單**（審查 S-03；也寫進 `runtime-patches.json` 的 `session_idle.py` 說明）。mcp 或 fastmcp 升版、guarded source
  的摘要變了，重新釘選之前：
  1. `tests/test_child_bearer.py` 全過，包括真子程式矩陣、其他路徑、不送的 body。
  2. MCPServer 的路由（mcp 的 `StreamableHTTPASGIApp`）與 FastMCP 的路由（它自己的 `StreamableHTTPASGIApp`，經 `handle_request`）
     仍然只經 `asgi_app` 進 manager。
  3. 沒有新的預設 HTTP 路由在閘門旁邊服務（MCPServer 的 `_custom_starlette_routes`、FastMCP 的 `_get_additional_http_routes`）。
  FastMCP 的 `server/mixins/transport.py`（`custom_route` 在這裡）沒有列進 guarded sources：其他路徑的行為測試會直接擋
  （突變 ROUTE，第 4.4 節）。

### 3.2 規則

- 剛好一個 `authorization` 標頭（名稱不分大小寫）；它的值和 `b'Bearer ' + token` 用 `hmac.compare_digest` 比。零個或兩個以上
  不比，直接 401。名稱只差大小寫的兩個標頭也算兩個。
- 只認閘道送的逐字形式。`bearer`（小寫）、兩個空白、只有 token、`Basic`、多一個或少一個字元、`Bearer a, Bearer b`（一個標頭
  兩個值）都 401。RFC 7235 允許 scheme 不分大小寫，這裡刻意不收：閘道、健康監看、能力探測都送 `Bearer `。
- 401 的回應：`WWW-Authenticate: Bearer`、`Content-Length: 0`、沒有本文、沒有 session；uvicorn 自己的 `date`、`server` 照舊。
  閘道本來就把子程式的 401 轉成自己的 502（`gateway.py` 既有的 `if upstream.status_code in (401, 403)`）。
- 不是 HTTP 的 scope（websocket、lifespan）不交給 SDK，也不回任何東西（Starlette 的 `Route` 本來就只收 HTTP）。
- 不讀 body 就回 401：uvicorn（7 個 venv 都是 uvicorn 0.54.0＋h11 0.16.0）在回應完成後丟掉剩下的 body，子程式照常服務下一個
  請求（測試送 2 MiB 的 body 再送正常請求）。
- FastMCP 的 Host／Origin 檢查（`HostOriginGuardMiddleware`）在閘門外面，照舊先擋；MCPServer 的 DNS rebinding 檢查在 SDK 裡、
  閘門後面。兩種順序都只會是拒絕。

### 3.3 啟動拒絕

- `install()` 在 patch 之前讀一次環境變數（已經裝過就照舊直接回傳）。缺、空、格式不符就 `RuntimeError(REFUSED)`；
  這時 `__init__` 還沒被換掉（測試驗）。
- 訊息固定：`child bearer: WOOW_MCP_CHILD_TOKEN is missing or not a child token`。不含值，也沒有串接的例外（先比格式、後編碼）。
- 正式環境不會遇到：`ProductState` 的 `child_token` 本來就驗同一個格式（`config.py:62-68`），`child_spec` 一律帶它。
  拒絕啟動的子程式結束碼非 0、stderr 有那一行；Supervisor 照既有規則退避重試，閘道走既有的「子程式未就緒」路徑。

### 3.4 不從環境變數拿掉

- 計畫 §8.3、DQ-37：同 uid 讀得到 `/proc/<pid>/environ` 和每個帳號的 `state.json`，藏環境變數沒有實益。
- 新的 child token 要等子程式重啟（新程序）才生效：子程式只在啟動時讀一次。

### 3.5 變數名稱與子程式輸出

- Odoo 子程式啟動時把 `ODOO_*`、`MCP_*` 環境變數逐一印到 stderr（`odoo_mcp/__main__.py:337-343`；名稱像秘密的才遮）。
  `WOOW_MCP_CHILD_TOKEN` 兩個前綴都不是，不會被印。
- Supervisor 的子程式輸出緩衝本來就依鍵名（含 `TOKEN`）遮掉 spec 的秘密（`lifecycle.py:114-115`）。測試另外讀遮罩前的原始輸出
  （含 uvicorn 的 `401 Unauthorized` 存取紀錄），7 支都沒有任何 token 的 16 字元片段。
- 兩個 token 都不在 argv（每個本機使用者都讀得到 `/proc/<pid>/cmdline`；測試驗 9 個產品）。

### 3.6 port 錯置

- 閘道 B 打到 A 的子程式：子程式回 401，閘道 B 回 502 `{"error":"request denied"}`，後端 0 次呼叫；就算帶的是 A 的子程式
  真的開過的 session id 也一樣（測試）。
- 健康監看 B 拿到 401：readiness 是 false、`backend` 是 `unreachable`，後端 0 次呼叫；A 自己的健康監看照常 reachable（測試）。
- 不擋「別的程序先綁住那個 port」：那是 HM-15（條件式）。同 uid 的程序讀得到 token（threat-model 第 1 節）。

### 3.7 n8n 與 Odoo Manage

- n8n：n8n-mcp 2.96.2 本來就驗 `AUTH_TOKEN`（`apps/n8n/n8n_adapter.py:129`，同一個 child_token），本片不改。它只看 `Bearer ` 開頭、
  比對前 trim（`http-server-single-session.js:260-292`），Node 的 http 對重複的 `Authorization` 只留第一個。所以真 n8n 子程式在
  14 種拒絕裡擋 11 種：兩個空白、兩個都是自己的 token、第一個是自己的 token 這 3 種會收下。3 種都要先有自己正確的 token；錯的、
  別帳號的、沒有的都 401。測試照實釘住（`N8N_ALSO_ACCEPTS`）。閘道從不送兩個標頭。HM-00 的 T-23、I4 與契約第 9 節 #37 已照這個行為
  改寫（MF-1 選 (a)，第 12.1 節）；`apps/n8n/` 不改。
- n8n-mcp 另有兩個本來就不驗的資訊頁（`GET /`、`GET /health`：名稱、版本、uptime；不開 session、不打後端），本片不改，也不在
  「其他路徑」測試裡（那個測試只跑 7 支 Python 子程式）。
- Odoo Manage：已下架（0.1.5 起沒有映像）；launcher 不呼叫 `session_idle`（mcp 1.30.0），`child_spec` 不給這個變數，
  維持現狀（計畫 §8.3），寫進 `docs/operations/guide.md`。容器驗收本來就不收它（`container_acceptance.py` 只收上架產品）。

## 4. 新測試、先紅後綠與臨時突變

### 4.1 新測試

`tests/test_child_bearer.py`（28 案，全部用 HM-01 的 `log_scan`；token 都在執行時產生，憑證 `DUMMY-…`、網址 `.invalid`）：

| 測試 | 驗什麼 |
|---|---|
| `test_child_spec_gives_the_seven_python_children_their_child_token`（9 個產品） | 每支子程式拿到的環境變數集合＝`bb48449` 的集合，7 支 Python 子程式多 `WOOW_MCP_CHILD_TOKEN`（值＝state 的 child_token），n8n、Odoo Manage 不變；add-on token 不進子程式；兩個 token 都不在 argv（env 快照，C4-SF-4） |
| `test_the_token_is_read_from_the_environment_or_the_child_refuses` | 缺、空與 11 種格式錯（短、長、結尾換行、結尾空白、開頭空白、`.`、`=`、`+`、`/`、非 ASCII、帶 `Bearer `）都是固定訊息的 `RuntimeError`，沒有串接例外 |
| `test_the_gate_lets_only_the_child_bearer_through` | 程序內驅動 `ChildBearer`：14 種拒絕都回同一個 401、內層 0 次；只有一個值時才 `compare_digest`；名稱只差大小寫的兩個標頭算兩個；websocket、lifespan 不交下去；`repr` 沒有 token |
| `test_install_gates_every_manager_or_refuses_before_patching`（兩種 SDK） | hermes（MCPServer）、emqx（FastMCP）的 venv：stateful、stateless、位置參數、明確參數、SDK 自己的 server 與 FastMCP 子類別，5 個 manager 的 `asgi_app` 都是 `ChildBearer`、裡面是 SDK 的 `RequestBodyLimitMiddleware`；缺、空、格式錯時 `install()` 拒絕而且 `__init__` 沒被換掉 |
| `test_real_child_serves_only_its_own_child_bearer`（7 支） | 真子程式：直連 14 種拒絕都 401（沒有本文、沒有 session）；2 MiB body 也立刻 401、下一個請求照常。**審查後補**：29 種其他路徑、方法、斜線、大小寫與編碼，不帶 bearer 都不是 2xx、沒有 session（不讀本文）；宣告 body 但一個位元組都不送：不帶 bearer（8 MiB 與超過 16 MiB）、帶別帳號的 bearer（超過 16 MiB）都立刻 401，自己的 bearer 是 SDK 的 413；這段後端 0 次。session 內不帶、別帳號、兩個標頭的 POST、GET、DELETE 都 401，session 還在；自己的 bearer 200。閘道 A 正常（tools/call 打到後端）；閘道 B（別帳號的 child token）initialize 與帶 A 的真 session 的 tools/call 都 502、後端 0 次；B 的健康監看 not ready、A 的 reachable。原始輸出沒有 4 個 token 的任何 16 字元片段；子程式只起一次 |
| `test_real_n8n_child_serves_only_its_own_auth_token` | 真 n8n 子程式：14 種裡 11 種 401，3 種（第 3.7 節）收下；原始輸出沒有 token |
| `test_a_child_without_a_valid_child_token_refuses_to_start`（7 支） | 照 add-on 的方式起真子程式（私有 port），缺、空、格式錯三種：結束碼非 0、stderr 有固定訊息、沒有 `Uvicorn running`、輸出沒有 token |

直連請求的共用函式 `send()`（審查 S-05）：GET 拿到 200 時不讀本文直接回傳（那是開著的 SSE 串流）；每個請求最多 30 秒
（`READ_SECONDS`）。正常情況 GET 一律 401，不影響判斷；回歸時測試直接失敗，不會卡到 CI 的 40 分鐘上限。
其他路徑與不送 body 的請求不經共用客戶端（它的守門只送 `/mcp`），改在每個請求前用同一個 owned-listener 證明確認 port 上
還是這支子程式（`owned()`）。

### 4.2 先紅後綠

先寫測試，再拿 `32ecac8` 的 `session_idle.py`、`products.py` 跑同一個測試檔（跑完換回本片的檔、核對摘要）：

| 階段 | 結果 |
|---|---|
| 第一次：測試檔的前一版＋`32ecac8` 的兩個執行期檔 | 25 失敗、3 通過（24 秒）。拒絕啟動的 7 案在讀 `session_idle.REFUSED` 時就失敗，沒有測到行為。所以把固定訊息改放在測試檔裡（另驗模組的常數相同）、子程式起來了就明確失敗，再跑一次 |
| 第二次：最終的測試檔＋`32ecac8` 的兩個執行期檔 | 25 失敗、3 通過（443 秒）。通過的 3 案本來就該不變：n8n 與 Odoo Manage 的環境變數集合、真 n8n 子程式。失敗的原因：7 支子程式的環境沒有這個變數；`bearer()`、`ChildBearer` 還不存在；兩種 SDK 的 manager 沒被包、缺 token 也照常 patch；7 支真子程式不帶 bearer 也回 200；7 支子程式缺、空、格式錯時照樣起來（stderr 有 `Started server process` 或 `Starting MCP server`；同時起的三個程序有兩個撞同一個私有 port 結束） |
| 最終的測試檔＋本片的實作 | 28 案全過（35 秒；另在全套 pytest 裡也全過） |

審查員另外重播一次先紅：25 失敗、3 通過（442.7 秒），和上表相同。審查後補的檢查放在既有的真子程式測試裡，那 7 案在先紅時
本來就失敗（不帶 bearer 回 200），所以沒有重跑先紅；新檢查有效的證據是第 4.4 節的突變。

### 4.3 臨時突變（守門有效）

每次只改實作的一處、跑新測試的程序內部分（`test_the_token`、`test_the_gate`、`test_install`、`test_child_spec`），跑完換回原檔、
核對摘要；沒有 commit。

| 突變 | 擋下它的測試 |
|---|---|
| M1 兩個 `Authorization` 時只看第一個 | `test_the_gate`（`twice`） |
| M2 用 `==` 取代 `hmac.compare_digest` | `test_the_gate`（`compare_digest` 沒被呼叫） |
| M3 環境變數只看有沒有、不驗格式 | `test_the_token`（沒有丟錯）、`test_install`×2 |
| M4 只包 stateful 的 manager | `test_install`×2 |
| M5 拒絕回 403 | `test_the_gate` |
| M6 標頭名稱分大小寫比 | `test_the_gate`（名稱只差大小寫的兩個標頭） |
| M7 patch 之後才讀 token | `test_install`×2（`__init__` 已被換掉） |
| M8 不是 HTTP 的 scope 交下去 | `test_the_gate` |
| M9 拒絕訊息帶值 | `test_the_token`、`test_install`×2（輸出出現 token 片段） |
| M10 一支子程式（Headscale）沒有這個變數 | `test_child_spec[headscale]` |
| M11 給 add-on token、不給 child token | `test_child_spec`×7 |
| M12 child token 當成 Odoo 的參數 | `test_child_spec[odoo]`（argv 有 token） |

12 個都被擋下。M2 第一次跑時碰到 repo 自己的測試鎖（`tests/conftest.py` 等 120 秒放棄，13 案都是 setup error、沒有真的跑），
另外重跑一次（上表是重跑的結果）。審查員另做 29 個程式突變與 2 個 SDK 漂移，31 個全部擋下（審查報告第 5 節）。

### 4.4 審查後補的檢查：突變與真子程式（2026-11-15）

同樣一次只套一個、跑完換回並核對 SHA-256（`apps/runtime/session_idle.py` 是帳本釘的 `207dd2e6…`；EMQX venv 的
`fastmcp/server/mixins/transport.py` 不在 git 裡，也核對前後摘要）；`git status` 前後相同；沒有 commit。只跑
`test_real_child_serves_only_its_own_child_bearer` 的 `[odoo]`（MCPServer）與 `[emqx]`（FastMCP）。

| 突變 | 結果 |
|---|---|
| V12（審查的編號）只擋 POST，其他方法不驗 | 擋下（2 案，共 5.4 秒）：其他路徑的檢查裡，不帶 bearer 的 `OPTIONS /mcp` 進了 SDK，回應帶著 `mcp-session-id`（SDK 替一個沒驗身分的請求開了 session）。審查時這個突變卡在 session 內的 GET，12 分鐘以上沒結束 |
| GET 只有「帶 session id 的 GET」不驗（只走 S-05 那條路：session 內開著的 SSE 串流） | 擋下（2 案，共 5.9 秒）：session 內不帶 bearer 的 GET 拿到 200，`send()` 不讀串流，測試以 `('none', 200)` 失敗，不再卡死 |
| V22 閘門放進 SDK 的 body 上限裡面 | 擋下（2 案）：不帶 bearer、宣告 8 MiB 不送，5 秒內沒有回應（SDK 的上限在等 body）；超過 16 MiB 的，不帶與別帳號的 bearer 都拿到 413，不是 401 |
| READ 閘門先把整個 body 讀完再判斷 | 擋下（2 案）：4 種不送 body 的請求都沒有回應（各 5 秒逾時） |
| ROUTE EMQX 的 FastMCP 多一條不驗的預設路由 `GET /health`（模擬 SDK 升版；只跑 `[emqx]`） | 擋下：其他路徑的檢查，`GET /health` 不帶 bearer 拿到 200。這支檔不在 guarded sources，只有這個行為測試擋得到 |

容器探針的新函式（S-01）另用一個臨時測試（只在跑的時候放進 `tests/`，沒有 commit）對真子程式跑：7 支 Python 子程式與
真 n8n 子程式，各自照 `child_spec` 起在私有 port，`assert_child_bearer` 用 `url=` 指到那個 port。8 案全過（17 秒）：
8 支都是不帶與別的值 401、自己的 200、session 刪得掉；用別帳號的 child token 當成「自己的」時，函式以固定訊息
`child refused its own bearer` 失敗；子程式原始輸出沒有 token。

## 5. 受影響的既有測試

HM-01 筆記建議 HM-06 開工時先用臨時突變找出直連測試。本片直接用實作找（要求正確的 child bearer，比「要求有 `Authorization`」
更嚴）：把改過的 5 個既有測試檔換回 `32ecac8` 版（實作、帳本、新測試不動）跑一次，144 案裡 33 失敗、111 通過，逐案處理如下。

| 檔 | 失敗 | 原因 | 處理 |
|---|---|---|---|
| `tests/test_session_idle.py` | 7／24（兩種 SDK 的單元測試 2、無效上限 5） | 單元測試的子程序環境沒有 child token，`install()` 拒絕啟動 | 環境帶 `C`×43 |
| `tests/test_nextcloud_child.py` | 6／47（env 快照 1、帳號查詢 body 壞 4、格式錯回答 1） | 快照少新變數；直連子程式時沿用閘道的 headers（add-on token） | 快照加這個變數（＝state 的 `'b'*43`）；直連改帶 child bearer |
| `tests/test_native_probe_separation.py` | 12／12（EMQX、LiteLLM 8；Nextcloud 4） | 直連子程式時沿用閘道的 headers | 直連改帶 child bearer（兩個函式各 2 處） |
| `tests/test_real_products.py` | 7／9（7 支 Python 子程式；Odoo Manage 照過） | 同上（`runner.child_url`） | 同上 |
| `tests/test_owned_ports_bearer.py`（HM-01） | 1／52 | 兩個 endpoint 共用 Odoo 的 spec，現在拿到同一個真 child token，「每個 endpoint 自己產生的值不同」不成立 | 改用沒有 bearer 的 Odoo Manage spec 測替身自己產生的值；另驗 Odoo 的 spec 帶真 child token |

另外，帳本與 tool-surface 沒更新時，`tests/test_tool_inventory.py` 的兩個摘要檢查會失敗；本片同一個 commit 更新帳本、重產
tool-surface，這個測試沒改。

計畫列的 `tests/test_session_idle.py:177-189`、`tests/test_nextcloud_child.py:164-177`、`tests/test_hermes_safe_public_errors.py:56-57`：
這三處走 HM-01 的共用客戶端（`Endpoint.client()` 自動帶 spec 的 bearer），不用改。`test_session_idle.py` 與
`test_nextcloud_child.py` 要改的是上表別的地方。

## 6. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

### 6.1 審查前（2026-11-15）

| 檢查 | 結果 |
|---|---|
| 新測試 `tests/test_child_bearer.py` | 28 案全過、0 skip（35 秒） |
| 目標測試 14 檔（新測試、HM-01 的黃金回歸與兩個契約凍結、改過的 5 檔、`test_hermes_safe_public_errors.py`、`test_tool_inventory.py`、`test_owned_runtime.py`、`test_headscale_product.py`、`test_product_boundary.py`） | 301 案全過、0 skip（590 秒） |
| 全套 pytest（`tests/`） | 3760 案、0 skip；3737 通過、23 失敗；28 分 29 秒。1 個是已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`。22 個是 `test_owned_browser_ipc.py`、`test_owned_browser_redirect.py`、`test_owned_ui.py`：本 clone 的 `packages/mcp-admin-ui/node_modules` 沒有 Playwright 的 Chromium（`setup_repo_env.sh` 的 `npm ci` 會清掉；CI 由 `unit.sh` 的 `npm run browser:install` 裝）。從本機基準 clone 複製同一版（playwright-core 1.61.1、chromium 1228）後，這 3 檔重跑 52 案全過 |
| 受影響的既有測試（第 5 節） | 5 檔換回 `32ecac8` 版：144 案，33 失敗、111 通過 |
| 先紅後綠、12 個臨時突變 | 第 4.2、4.3 節 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest（暫存 venv：`uv sync --frozen --no-dev`＋`requirements-ci.txt`，同 CI 的步驟；沒動 clone 的 `.venv`） | `Ran 184`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py`（檢查模式，同 `unit.sh`） | 通過 |
| `scripts/ledger_precheck.py` | OK |
| UI `npm test`、Playwright `test:browser`、`build-closure.mjs` | 沒跑：本片沒動 `packages/mcp-admin-ui/` 與 `tests/owned_network.cjs`；CI 會跑 |

審查員重跑全套（跳過 3 個瀏覽器檔）：3708 案、0 skip，3706 過；2 個失敗是要 root 的那 1 案，和 port 被同時跑的測試搶走的 1 案
（`test_output_schema_runtime.py[odoo]`，單獨重跑 31 案全過）。

### 6.2 審查後（2026-11-15）

| 檢查 | 結果 |
|---|---|
| `tests/test_child_bearer.py` | 28 案全過、0 skip（41.8 秒；審查前 35 秒） |
| HM-01 守門與帳本：`test_tool_inventory.py`、`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、`test_owned_ports_bearer.py` | 105 案全過、0 skip（31 秒）：`test_tool_inventory.py` 8、黃金回歸 17、MCP 契約凍結 9（99 個契約案例）、管理契約凍結 19、`test_owned_ports_bearer.py` 52 |
| 審查後的突變與容器探針函式對真子程式 | 第 4.4 節 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest（暫存 venv，步驟同 CI、離線） | `Ran 186`、`OK (skipped=5)`（多的 2 案是 `ChildBearerCheckTests`） |
| `scripts/tool_inventory.py`（檢查模式） | 通過 |
| `scripts/ledger_precheck.py`、`scripts/secret_precheck.py --full` | 第 9 節 |
| 全套 pytest | 沒有重跑：這一輪只改測試、容器探針、文件與帳本說明文字，執行期檔一個位元組都沒改；全套的結果見第 6.1 節。CI 會跑全套 |
| `git status` | 乾淨（commit 之後）；用過的 TMPDIR 都已刪除 |

### 6.3 rebase 後（2026-11-15，HEAD `13c0708` 的程式；之後只加本筆記）

| 檢查 | 結果 |
|---|---|
| 目標 22 檔，一次 pytest（同 CI 的 `-q -p no:cacheprovider`；正式 conftest，排到共用測試鎖後才跑） | 1089 案、0 skip、617 秒：1088 通過、1 失敗＝HM-07 已知要 root 的 `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（`assert os.geteuid() == 0`，只在 CI 驗） |
| 其中本片：`tests/test_child_bearer.py` | 28 案全過（37.9 秒） |
| 其中本片的 14 個目標檔（第 6.1 節那組：新測試、HM-01 的黃金回歸與兩個契約凍結、改過的 5 檔、`test_hermes_safe_public_errors.py`、`test_tool_inventory.py`、`test_owned_runtime.py`、`test_headscale_product.py`、`test_product_boundary.py`） | 301 案全過，和 rebase 前相同 |
| 其中 HM-01 守門：`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、`test_owned_ports_bearer.py` | 17＋9＋19＋52＝97 案全過，期望值與案例檔沒改 |
| 其中 HM-04：`test_child_port_param.py`（快照同步後）、`test_initialize_cleanup.py` | 233＋293 案全過 |
| 其中 HM-07：`test_profile_consistency.py`、`test_profile_index.py`、`test_profile_store.py`、`test_identity_fields.py`、`test_upgrade_zero_rewrite.py` | 250 案：249 通過、1 失敗（上面那個要 root 的） |
| 其中 `test_management_capabilities.py`（能力探測帶 child bearer，審查突變 C01） | 12 案全過 |
| MF-3 先紅：`tests/test_child_port_param.py` 配 `claude-delivery` 的快照（跑完換回、核對摘要） | 233 案：正好 12 案失敗（7 支 Python 子程式的 12 個案例）、221 案通過（10.6 秒）；更新後 233 案全過 |
| `scripts/tool_inventory.py --write`／檢查模式 | 重產 0 差異；檢查通過 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest（暫存 venv：`uv sync --frozen --no-dev`＋`requirements-ci.txt`，同 CI 的步驟、離線；不動 clone 的 `.venv`） | `Ran 194`、`OK (skipped=5)`（5 個 `skipUnless(root)`；比 rebase 前多 8 案，是 HM-17 加的；`ChildBearerCheckTests` 2 案通過） |
| `scripts/ledger_precheck.py`、`scripts/secret_precheck.py --full` | 第 9 節 |
| 全套 pytest | 沒有跑（以 CI 為準）。rebase 只改了快照、文件與測試註解；執行期的改動和審查時逐行相同（第 12.2 節） |
| `git status` | 乾淨（commit 之後）；用過的 TMPDIR 都已刪除 |

## 7. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。新測試不靠執行身分或權限下判斷；CI 以 root 跑子程式，
  bearer 的判斷和 uid 無關，預期結果相同。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root）。它的
  子程式是一支假 listener（`tests/owned_uid_probe.py`），不是 MCP 子程式，本片不影響它。rebase 後多一個 HM-07 的同類案例：
  `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（uid 10001 的 mode／owner 證明，本機 `geteuid() != 0` 照預期失敗），
  本片也不影響它。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。
- 容器驗收（`packaging/container_acceptance.py`、`container_probe.py` 在映像裡跑）：要 docker 與建好的映像，本機與 PR 的 CI 都不跑。
  審查後探針多了直連 3000 的 child bearer 檢查（S-01）：函式本身有 packaging 單元測試，也對 8 支真子程式跑過（第 4.4 節），
  但在真的容器裡還沒跑過。實際容器跑一次，交給 HM-19a 前的 builder 乾跑（計畫 §12.3 HM-19a；要使用者授權）。這**不是本片的
  合併關卡**：功能 PR 不改版號、不出貨（主對話 2026-11-15 08:0x 定案）。見第 11、12.3 節。

## 8. `checks` 秒數

- 前：本片 rebase 後的基準是 #93（HM-07）：合併前最後一次 `checks`（head `cdcb2f7`，run 43654510484）1881 秒。開發時的基準
  HM-01 的 PR #90（head `32ecac8`，run 43587407864）1434 秒。
- 後：CI 跑完再補。
- 推估：新測試本機約 42 秒（審查前 35 秒；7 支真子程式各 2.7～4.1 秒、真 n8n 0.9 秒、拒絕啟動 7 支各 1～2 秒）；
  改過的既有測試只多 7 個直連請求；packaging unittest 多 2 案（約 1 秒）。推估 CI 多 50～80 秒，在每片 1.5 分鐘的預算內。

## 9. 預檢結果

數字是 rebase 後的最終 HEAD（含本筆記這一版的 commit；本筆記 commit 之後重掃，結果相同）。指令：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <暫存區的 gitleaks-tools> --repo . --base origin/claude-delivery --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery
```

- **秘密預檢**（`scripts/secret_precheck.py`）：gitleaks 8.28.0（釘選、執行檔摘要相符；用暫存區既有的執行檔，沒有下載）；
  設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`e5fa5c7..HEAD`，git 模式；rebase 後的 6 個＋新的 3 個，含本筆記） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史（建置機同款） | 0 |

  rebase 前（`131edd4`：本片 6 個、本分支 15 個 commit）、審查前（`5e6f1c3`）與審查員的掃描也都是 0。

- **帳本預檢**（`scripts/ledger_precheck.py`）：`runtime-patches.json` 167 個路徑（rebase 前 163；多的 4 個是 HM-07 新列管的
  `config.py`、`features.py`、`identity_fields.py`、`profiles.py`）、`runtime-sources.json` 70 個 vendored 檔、`tool-surface.json`
  159 個摘要，都 0 漂移、0 缺檔、0 個要 CI 安裝才有的檔。對 `origin/claude-delivery`（merge base `e5fa5c7`）改 19 個檔；列管檔 2 個
  （`session_idle.py`、`products.py`），兩本帳本（`runtime-patches.json`、`tool-surface.json`）同時改了；新增而沒列管的執行期檔 0 個、
  改到而沒列管的執行期檔 0 個（`packaging/container_probe.py` 不是執行期檔：容器驗收時才唯讀掛進去，不在映像裡）。結果 OK。

## 10. PaaS 變動

- 作者沒有連 Gitea（本片不連遠端）。用本機 PaaS 研究 clone 已經 fetch 的 `origin/main`（`cf3d0d5`，2026-11-14 22:30 台北；
  本機各個 PaaS clone 裡最新的）跑
  `git log 69ac425..origin/main -- packages/mcp-admin-core/mcp_admin_core/{profiles,process,proxy,child_identity,launch_policy}.py docs/security/mcp-child-identity.md apps/n8n`：
  兩個 commit，都只改文字：`19f36e2`（#148 之後的文件更正：`proxy.py` 只改註解）、`8bfb12e`（`apps/n8n/Dockerfile` 一行註解拿掉
  已移除的 vk）。沒有可執行的改動和子程式 bearer 有關。
- 審查員（2026-11-15 06:16）與審查後（2026-11-15 07:07，唯讀、沒有 fetch）各重跑一次，結果相同。
- **主對話代查（審查 S-02；本片不連 Gitea）**：主對話 2026-11-15 06:2x 在本機 PaaS git fetch 後查，PaaS main 是 `cf3d0d5`。
  `69ac425..cf3d0d5` 動到核心模組（`packages/mcp-admin-core/mcp_admin_core/`）的只有：
  - `log_redaction.py`（#149，交給 HM-02）。
  - `gateway_pool.py` 與 `proxy.py`（#148 合併後的註解與文件更正 `19f36e2`，交給 HM-14）。
  - `setup_status.py`（移除 VK 的說明文字 `8bfb12e`）。
- 子程式 bearer 相關的 PaaS 檔沒有改動。和上面本機唯讀查的結果一致：那份清單只碰到 `19f36e2`（`proxy.py` 只改註解）與
  `8bfb12e`（`apps/n8n/Dockerfile` 一行註解），都不是可執行的改動。本片不用回頭對齊。

| 查詢時間 | `origin/main` | 結果 |
|---|---|---|
| 作者開發時（本機唯讀；那份 `origin/main` 是 2026-11-14 22:30 fetch 的） | `cf3d0d5` | 上面的清單：`19f36e2`、`8bfb12e` 兩個純文字 commit |
| 2026-11-15 06:16（審查員，本機唯讀） | `cf3d0d5` | 同上 |
| 2026-11-15 07:07（作者，審查後，本機唯讀） | `cf3d0d5` | 同上 |
| 2026-11-15 06:2x（主對話，本機 PaaS git fetch 後） | `cf3d0d5` | 核心模組只動 `log_redaction.py`、`gateway_pool.py`、`proxy.py`、`setup_status.py`；子程式 bearer 相關的檔沒有改動 |

## 11. 驗收條件（計畫 §12.3 HM-06）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR 的 CI（rebase 到 `e5fa5c7` 後開 PR；本片不合併，CI 全綠後由主對話合併）。本機見第 6.3 節 |
| 單帳號經閘道的行為不變（HM-01 黃金回歸與契約凍結逐位元照過） | 通過（本機）：`test_single_profile_golden.py` 17 案、`test_mcp_contract_freeze.py` 9 案（99 個契約案例）、`test_admin_contract_freeze.py` 19 案全過，期望值與案例檔沒改；rebase 後重跑同樣全過（第 6.3 節）；`gateway.py`、`health.py`、`capabilities.py` 沒改 |
| 容器探針的單帳號路徑照過 | 實際容器還沒跑：交給 HM-19a 前的 builder 乾跑（要使用者授權）。主對話定案：**不是本片的合併關卡**（功能 PR 不改版號、不出貨）。本機能跑的部分通過：`packaging/validate.py` PASS、packaging unittest `Ran 194`、`OK (skipped=5)`。探針審查後多了直連 3000 的 child bearer 檢查（審查 S-01），函式對 8 支真子程式跑過 |
| 獨立安全審查 | 完成：修正後通過（repo 外 `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-06.md`）；處理見第 13 節 |
| 7 支 Python 子程式一律要求 child bearer；只接受正確的 `Authorization: Bearer <child token>`，其他 401 | 通過（第 4 節；真子程式 14 種拒絕＋session 內＋2 MiB body＋其他路徑＋不送的 body） |
| env 缺、空、格式錯時拒絕啟動 | 通過（程序內 13 種、兩種 SDK 各 3 種、7 支真子程式各 3 種） |
| token 不出現在 stderr、log、錯誤訊息 | 通過：子程式原始輸出、`log_scan`、拒絕訊息、argv 都 0 命中；臨時突變 M9 證明這個檢查有效；容器探針的失敗訊息固定 |
| `child_spec` 只給 7 支 Python 子程式；n8n 的 Node 子程式照計畫 §8.3 | 通過：n8n 不變（本來就驗同一個 child_token）；Odoo Manage 不變 |
| T-23（改寫後：7 支 Python 子程式兩個標頭也 401；n8n 照 n8n-mcp 現況） | 通過：7 支 Python 子程式 14 種拒絕都 401；真 n8n 子程式 11 種 401、另外 3 種收下，和改寫後的 T-23 相同（MF-1 選 (a)，第 12.1 節） |
| 受影響的既有測試更新、env 快照重定（C4-SF-4） | 通過：對 `32ecac8`（第 5 節；環境變數集合快照在新測試，`test_nextcloud_child.py` 的完整快照已更新）與 rebase 後（第 6.3 節）都過。HM-04 的快照已同步（MF-3：先紅正好 12 案，更新後 233 案全過；第 12.2 節） |
| 同 PR 更新帳本、重產 tool-surface | 通過：rebase 後帳本逐筆合併、摘要重算；帳本預檢 OK；`scripts/tool_inventory.py --write` 0 差異、檢查通過；`tests/test_tool_inventory.py` 8 案全過 |
| 先寫測試、記下先紅後綠 | 通過（第 4.2 節） |
| 新測試用 HM-01 的 log 掃描、沒有條件式 skip | 通過：`pytestmark` 用 `log_scan`；沒有 `skip`／`skipif`／`xfail` |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 在執行時產生或用 `C`×43；憑證 `DUMMY-…`、網址 `.invalid`；沒有 commit 隨機 token；秘密預檢 0 命中 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG | 通過 |

## 12. 定案、rebase 與交給後面的片

### 12.1 主對話的定案（2026-11-15 08:0x；審查 MF-1、MF-2）

- **MF-1　n8n 的重複標頭：選 (a)。** 程式、測試與 `apps/n8n/` 都不改；HM-00 的文件照 n8n 的實際行為寫：沒改的 n8n-mcp 會收下
  審查列的三種寫法（`Bearer` 後兩個空白、兩個標頭都是自己的、第一個是自己的＋第二個是別帳號的；第 3.7 節），但都要先有自己的
  child token，沒有越權。
  - 理由：閘道只轉送自己的 child bearer、只送一個標頭（HM-01 的黃金回歸鎖住：子程式收到的 `Authorization` 一律剛好是
    `Bearer <child token>` 一個，用戶端塞不進第二個）；能直連子程式 port 的只有 add-on 容器內同 uid 的程序（`host_network: false`，
    loopback 在容器自己的網路裡），在 DQ-37 接受的信任邊界內。
  - 改了：`contract.md` 第 9 節 #37 的註與第 10 節變更紀錄一列、`acceptance-matrix.md` T-23 的 n8n 期望值、`threat-model.md` I4 的
    測試欄（後兩份另加狀態行）；`tests/test_child_bearer.py` 的 `N8N_ALSO_ACCEPTS` 註解改成引用這個決定（`13c0708`）。
  - 改之前先讀過 n8n-mcp 2.96.2 的 `dist/http-server-single-session.js:260-293`（`authenticateRequest`：`startsWith('Bearer ')`、
    `slice(7).trim()`、`timingSafeCompare`），和審查報告指的行為相同。
  - 沒改 `docs/operations/guide.md`：它寫的「n8n 的子程序本來就只認同一個 child token」仍然正確；「不擋重複標頭」由 HM-18 寫進 DOCS。
- **MF-2　DQ-08：已有答案，沒有另問使用者。** 計畫 §13.2 把 DQ-08 列為 DQ-40 的細節（「DQ-40 一次確認後照做」），DQ-40 (a) 是
  使用者 2026-11-14 13:4x 採用的 §13.1 建議；子程式身分的做法寫在計畫 §8.3。所以 HM-06 照 §8.3：剛好一個 `Authorization`、
  `hmac.compare_digest` 比對 `Bearer <WOOW_MCP_CHILD_TOKEN>`、缺或格式錯就拒絕啟動，就是本片的規則。listener 檢查仍待定，
  留給 HM-15（DQ-37、UC-04）。
  - 改了：`decisions.md` 的 DQ-08 移到第 1 節並記日期、結論的題數、變更紀錄一列；本筆記第 1 節的決策列改成引用這個決定（`13c0708`）。
  - 附帶一提：計畫 §13.2 那一列寫「照 §5.3、§6、§8.5、§8.7、§9」，沒有列 §8.3（DQ-08 的做法所在）；本片照主對話的定案記成「照 §8.3」。
- **容器探針在實際容器跑一次**：照計畫放在 HM-19a 前的 builder 乾跑，不是本片的合併關卡（功能 PR 不改版號、不出貨；第 7、11 節）。

### 12.2 rebase（2026-11-15；審查 MF-3）

1. `git fetch origin claude-delivery`（`e5fa5c7`），`git rebase --onto origin/claude-delivery 32ecac8`：6 個 commit 依序重放，
   只有第一個（`67852e9` → `242640d`）衝突，而且只在 `docs/provenance/runtime-patches.json`。
   - `products.py`、`tests/test_real_products.py`、`docs/tool-surface.json` 自動合併。`child_spec` 保留 HM-04 的 `port` 參數，
     檔裡也保留 HM-07 的 `profile_initial_state`；本片的 env 接在建 `env` 之後（`PYTHONPATH` 後面），和審查時相同。
     `test_real_products.py` 保留 HM-17 的 `release_version()`；`tool-surface.json` 是 HM-04 的兩個 launcher 摘要＋本片的 `session_idle.py`。
   - 最後一個 commit（`131edd4` → `ae29300`，`session_idle.py` 說明補的那句）自動套上。
2. 帳本不是只解文字。以 `claude-delivery` 的帳本為底，逐筆三方合併（暫存區的一次性腳本，不進 repo）：
   - `scope`：`claude-delivery` 沒改，用本片的（多 HM-06 一句）。
   - `session_idle.py`：`claude-delivery` 沒改，用本片的說明與 17 個 guarded sources（本片多的 11 個）。
   - `products.py`：說明是 `claude-delivery` 的（原文＋HM-04＋HM-07）再接本片的 HM-06 那段。
   - 其他 52 筆（含 HM-07 新增的 `config.py`、`features.py`、`identity_fields.py`、`profiles.py`）照 `claude-delivery`，順序也照它。
   - 每一筆列管檔的 SHA-256 都用工作目錄裡合併後的檔重算，只有兩筆變：`products.py` `ecffa712…` → `c83a59d0…`、
     `session_idle.py` `79ecbaff…` → `207dd2e6…`；guarded sources 逐一和實際檔案核對，0 漂移。
   - JSON 格式照原檔（`indent=2`、`ensure_ascii=False`、結尾換行）。
   - 核對：本片在每個檔的增刪行和審查時逐行相同（`git diff -U0` 的增刪行，`32ecac8..131edd4` 對 `e5fa5c7..HEAD`）：
     `session_idle.py`、`products.py`、5 個既有測試、容器探針與它的測試、`guide.md` 共 10 個檔相同；`tests/test_child_bearer.py`
     只多 MF-1 的註解（3 行換 5 行）。
3. `tests/contract/child_spec_default.json`（`0dec7c8`）：12 個 Python 案例在 `PYTHONPATH=…` 後加 `WOOW_MCP_CHILD_TOKEN={child_token}`
   （`odoo/plain`、`odoo/switches`、`hermes/gateway`、`hermes/dashboard`、`opendesign/plain`、`emqx/plain`、`emqx/restricted`、
   `litellm/plain`、`litellm/restricted`、`nextcloud/plain`、`nextcloud/restricted`、`headscale/plain`）；n8n、odoo-manage 的 4 個不動；
   `changes` 加一筆 HM-06（英文，同檔案既有的語言）。
   - 先紅：工作目錄換回 `claude-delivery` 的快照跑 `tests/test_child_port_param.py`，正好這 12 案失敗、221 案通過（10.6 秒；
     失敗訊息印的是正規化過的 spec，token 是 `{child_token}` 佔位字）；跑完換回、核對摘要。
   - 更新後 233 案全過。
4. `scripts/tool_inventory.py --write`：0 差異（自動合併的 `tool-surface.json` 已經正確）；檢查模式通過。
5. `git log origin/claude-delivery..HEAD` 只剩本片的 9 個 commit：

   | rebase 後 | 原本 | 標題 |
   |---|---|---|
   | `242640d` | `67852e9` | feat(runtime): require the child bearer in the seven Python children (HM-06) |
   | `f7989a9` | `8146b33` | docs(operations): note the child bearer and the unchanged Odoo Manage (HM-06) |
   | `a37f5a8` | `5e6f1c3` | docs(provenance): add HM-06 multi-profile provenance note |
   | `58b7690` | `488b386` | test(multi-profile): fail fast on an open stream, cover other routes and unsent bodies (HM-06) |
   | `a96eeba` | `4d121a7` | test(packaging): check the child bearer straight on 3000 in the container probe (HM-06) |
   | `ae29300` | `131edd4` | docs(provenance): record the HM-06 review fixes and rechecks |
   | `0dec7c8` | （新） | test(multi-profile): add the child token to the HM-04 child spec snapshot (HM-06) |
   | `13c0708` | （新） | docs(multi-profile): record DQ-08 and what the n8n child takes (HM-06) |
   | 本筆記這一版 | （新） | docs(provenance): record the HM-06 rebase, the MF-1 and MF-2 decisions and the PaaS change list |

### 12.3 交給後面的片

- HM-19a 與每個產品的升版（審查 S-07；計畫 §3.3、§11.5）：HM-06 合併後，任何產品的 CHANGELOG 都要寫明「容器內直連子程式要帶
  child bearer」；容器驗收的直連 401 檢查已經在探針裡（第 2 節），每次發版的 builder 乾跑都會跑到。探針在實際容器裡的第一次，
  就是 HM-19a 前的 builder 乾跑（主對話定案：不是本片的合併關卡）；建議至少 Odoo（MCPServer）、一個 FastMCP 產品（例如 EMQX）
  與 n8n 各跑一次。
- HM-09：額外帳號的子程式拿自己 state 的 child_token（每帳號不同）；直連矩陣可以重用本檔的 `refusals()`。
- HM-13b（審查 S-07）：重產 child_token 之後要重啟子程式（子程式只在啟動時讀一次）。`configuration.py:33-36` 的 `launch_revision`
  已含 `child_token`，設定流程會重啟；HM-13b 走同一條路徑。
- HM-15（條件式）：「別的程序先綁住 port」不在本片範圍。
- HM-09／HM-30 的 log 事件（審查 S-07）：子程式回 401 時，健康監看只看得到 readiness false（`MCP_SERVER_NOT_READY`）、
  `backend` 是 `unreachable`，沒有專屬原因碼，容易誤判成後端壞；要不要加，由那兩片決定。
- HM-16：探針的多帳號階段沿用 `assert_child_bearer`（每個帳號的子程式 port 與 child_token）。
- HM-18（審查 S-07）：把 `docs/operations/guide.md` 這段帶進各產品 DOCS；註明 Odoo Manage 是唯一沒有 bearer 的子程式
  （已下架、DQ-28 不開放）。MF-1 已選 (a)：一併寫 n8n 不擋重複標頭（另外收下的三種寫法都要先有自己的 child token）。
- 決策同步的尾巴（給主對話；本片不改 repo 外的東西）：
  - HM-00 的對照腳本 `check_hm00.py`（repo 外）的 C8 若仍只認「§13.1 已採用、其他待定」，重跑會把 DQ-08 也報成問題（HM-07 筆記
    第 12 節第 5 點已記同一件事：DQ-09、DQ-12、DQ-19、DQ-38）。
  - 計畫 §13.2 那一列的另外 6 題（DQ-05、10、15、16、17、18）也是「DQ-40 一次確認後照做」；本片只記 DQ-08，其他題等負責片開工時由
    主對話決定要不要同樣記成已定。
- `checks` 的「後」秒數：PR 的 CI 跑完後補。

## 13. 審查意見處理（2026-11-15；rebase 後更新）

審查報告：repo 外 `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-06.md`（審 `5e6f1c3`，rebase 後是 `a37f5a8`；判定：
修正後通過；必修 3、建議 7）。先核對過審查的證據：n8n-mcp 的認證程式（`http-server-single-session.js:260-293`）、`decisions.md`
的 DQ-08、`container_probe.py` 的檢查、兩個 SDK 的路由與 body 上限（自己讀程式）；HM-04 的快照在 rebase 後直接讀
`claude-delivery` 的檔（不碰 HM-04 的 clone）。沒有發現審查有誤。commit 欄是 rebase 後的 SHA（第 12.2 節的對照表）。

| 項目 | 審查意見 | 處理 | commit | 理由 |
|---|---|---|---|---|
| MF-1 | T-23／I4 寫 n8n「兩個標頭也 401」，實際的 n8n 會收下（要先有自己的 token） | 主對話 2026-11-15 08:0x 選 (a)：程式、測試、`apps/n8n/` 不改；HM-00 的 T-23、I4、契約第 9 節 #37 照 n8n 的實際行為改寫；`N8N_ALSO_ACCEPTS` 註解改成引用定案（第 12.1 節） | `13c0708` | 沒有越權：三種都要先有自己的 child token；閘道只送自己的一個 bearer（HM-01 黃金回歸鎖住）；能直連的只有容器內同 uid 程序（DQ-37） |
| MF-2 | DQ-08 還是「待定（細節）」，最晚「HM-06 開工前」 | 主對話確認已有答案、不另問使用者：DQ-08 是 DQ-40 的細節，DQ-40 (a) 已採用，HM-06 照計畫 §8.3。`decisions.md` 的 DQ-08 移到第 1 節、記日期；第 1 節決策列改成引用；listener 檢查仍待定（HM-15） | `13c0708`、本筆記 | 計畫 §13.2「DQ-40 一次確認後照做」 |
| MF-3 | rebase 到 HM-04 後，HM-04 的 child spec 快照 12 案一定紅、`runtime-patches.json` 衝突 | rebase 到 `e5fa5c7` 時做了：帳本以 `claude-delivery` 為底逐筆合併、兩個列管檔的摘要用合併後的內容重算；快照 12 個 Python 案例加 `WOOW_MCP_CHILD_TOKEN={child_token}`、`changes` 加一筆 HM-06；`tool_inventory.py --write` 0 差異（第 12.2 節） | `242640d`（帳本）、`0dec7c8`（快照） | 審查的 rebase 模擬與本次 rebase 後的先紅都證實 12 案 |
| S-01 | 容器探針沒有直連 3000 的 401 檢查；這條驗收本機驗不了 | 採用：`container_probe.py` 加 `assert_child_bearer`（不帶、別的 43 字元值 401、沒有 session；自己的 200、session 馬上 DELETE；n8n 也跑）；`packaging/test_container_probe.py` 加 2 案；另對 8 支真子程式跑過（第 4.4 節）。實際容器跑一次交給 HM-19a 前的 builder 乾跑，**不是本片的合併關卡**（主對話定案） | `a96eeba` | 計畫 §3.3 的保證方式有容器探針；§11.5 每次發版要做直連 401 檢查，放進探針就每次自動做；功能 PR 不改版號、不出貨 |
| S-02 | PaaS 變動清單要在連得到 Gitea 的地方重跑；第 1 節補 pin | 採用：第 1 節補 pin `69ac425`（DQ-06）；主對話 2026-11-15 06:2x 在本機 PaaS git fetch 後代查 `cf3d0d5`（第 10 節） | 本筆記 | 本片不連 Gitea |
| S-03 | guarded sources 6 → 17 保留；缺 SDK 升版重審清單 | 採用：清單寫進第 3.1 節與 `runtime-patches.json` 的 `session_idle.py` 說明。不再加 guarded sources（`fastmcp/server/mixins/transport.py` 由其他路徑的行為測試擋，突變 ROUTE） | `ae29300` | 審查的 SDK 漂移實驗 S01、S02 |
| S-04 | 「其他路徑沒有後門」「閘門在 body 上限外、不讀 body」沒有行為測試 | 採用，做法微調：放進既有的真子程式測試（子程式不多起一次）。E1：29 種路徑／方法（同審查），不讀本文。E3：宣告 body 但**一個位元組都不送**（審查是送 64 KiB）：不帶 bearer（8 MiB、超過 16 MiB）與別帳號的 bearer（超過 16 MiB）立刻 401，自己的 bearer 413。沒收審查的 E2（原始 socket 標頭寫法）：它驗的是 h11 的正規化，不是閘門的規則，審查也沒要求 | `58b7690` | 不送 body 時，伺服器關連線時沒有沒讀的資料，不會有 RST 的時序問題；「閘門不等 body」照樣驗得到（等了就逾時）。突變 V22、READ、ROUTE 都被擋（第 4.4 節） |
| S-05 | `send()` 讀 GET 200 的 SSE 串流會卡死（突變 V12 卡 12 分鐘以上） | 採用：GET 拿到 200 不讀本文直接回傳；每個直連請求另有 30 秒上限 | `58b7690` | 突變 V12 現在被其他路徑的檢查在幾秒內擋下；只放行 session 內 GET 的突變（GET）在 6 秒內以 `('none', 200)` 失敗（第 4.4 節） |
| S-06 | provenance 幾處要更新 | 採用：第 1 節（PaaS pin、DQ-08）、第 7、11 節（容器探針列）、第 12 節（MF-1～MF-3），並加本節 | `ae29300`、本筆記 | — |
| S-07 | 交給後面的片的事項 | 採用：寫進第 12.3 節（HM-19a 與各產品升版、HM-13b、HM-09／HM-30、HM-18） | `ae29300`、本筆記 | 不擋本片 |
