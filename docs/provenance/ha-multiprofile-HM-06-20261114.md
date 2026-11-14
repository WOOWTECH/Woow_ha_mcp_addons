# HA 多帳號 HM-06 provenance：子程式 bearer（一律生效）（2026-11-14）

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
- 全套 pytest（本機、一般使用者）：3760 案、0 skip；3737 通過，23 失敗：1 個是已知要 root 的測試，22 個是瀏覽器測試（本 clone 的
  `node_modules` 沒有 Playwright 的 Chromium；補上後這 3 檔重跑 52 案全過）。本片的 28 案與受影響的既有測試全過。
- 兩個預檢：秘密預檢 0 命中（本分支 12 個 commit，含本筆記；`--full` 的 HEAD 與全歷史也 0）；帳本預檢 OK（0 漂移、0 缺檔、沒有新增而沒列管的執行期檔）。
- 要回報、不是本片自己定的事：HM-00 驗收矩陣 T-23 寫「7 支 Python 子程式＋n8n：兩個標頭都 401」，但照計畫 §8.3 沒改的 n8n
  會收下「第一個是自己 token」的兩個標頭與「兩個空白」的寫法（都要先有正確的 token；錯的、別帳號的、沒有的都 401）。
  測試照實釘住，交主對話決定（第 12 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-06（計畫 §8.3、§12.3；風險高、工作量 L；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm06-20261114`（只 commit，沒有 push、沒有 PR） |
| HA 基準 | HM-01 的分支 head `32ecac8`（＝`bb48449`＋HM-01；PR #90 CI 全綠、等合併） |
| 依據 | 計畫 §8.3、§12.0、§12.3 HM-06；HM-00 契約（PR #89）第 1.2 節、第 7 節「子程式 bearer」列、第 9 節 #37；`threat-model.md` I4 與同 uid 信任邊界；`acceptance-matrix.md` T-23；FM-42、FM-92 |
| 決策 | DQ-40 ⑥（7 支 Python 子程式也驗 bearer、驗格式；2026-11-14 使用者採用）。DQ-08 的細節照計畫 §8.3 原文實作，沒有另定；它待定的部分（listener 檢查）屬 HM-15，本片沒碰。DQ-27（EMQX 子程式端政策）也沒碰 |
| 對齊的 PaaS | 加嚴，不是移植：PaaS 只有 n8n 驗 bearer（`Pc/profiles.py:387-393`；§8.8 #37）。本片沒有移植 PaaS 程式或測試 |
| FM | FM-42（子程式 bearer）、FM-92（EMQX：只有「子程式驗入站身分」這一段） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `apps/runtime/session_idle.py` | 新增 `bearer()`：讀 `WOOW_MCP_CHILD_TOKEN`，缺、空、格式不符就 `RuntimeError(REFUSED)`（固定訊息）。新增 ASGI 閘門 `ChildBearer`：剛好一個 `Authorization` 而且值等於 `Bearer <token>`（`hmac.compare_digest`）才交給內層 app；其他 HTTP 請求回 401（`WWW-Authenticate: Bearer`、`Content-Length: 0`、沒有本文）；不是 HTTP 的 scope 不交下去、也不回；`__slots__`、固定的 `repr`。`install()` 在 patch 之前呼叫 `bearer()`；既有的 `__init__` 包裝在 `original(...)` 之後把 `self.asgi_app` 換成 `ChildBearer`。idle 上限、body 上限、冪等標記都不變。沒有另開 `child_auth.py`（計畫允許兩種；掛點就在這支，帳本已列管） |
| `packages/mcp-admin-core/mcp_admin_core/products.py` | `child_spec`：Odoo Manage 以外的 7 支 Python 子程式加 `WOOW_MCP_CHILD_TOKEN`＝state 的 `child_token`。其他變數、argv、工具、授權、state 都不變 |
| `tests/test_child_bearer.py`（新） | 第 4 節 |
| `tests/test_session_idle.py` | 單元測試的子程序環境帶 `C`×43 的 child token（`install()` 沒有它就拒絕啟動） |
| `tests/test_nextcloud_child.py` | env 快照（`spec.env == {...}`）加 `WOOW_MCP_CHILD_TOKEN`；兩處直連子程式的呼叫改帶 child bearer |
| `tests/test_native_probe_separation.py`、`tests/test_real_products.py` | 直連子程式的呼叫改帶 child bearer |
| `tests/test_owned_ports_bearer.py`（HM-01） | 「替身自己產生的 bearer」改用沒有 bearer 的 Odoo Manage spec；真子程式一律驗「不帶 bearer 回 401」（原本只有 n8n）；兩段 docstring 改成現況 |
| `docs/provenance/runtime-patches.json` | `session_idle.py`、`products.py` 重新釘選並加 HM-06 說明；`session_idle.py` 的 guarded sources 由 6 個加到 17 個（第 3.1 節）；`scope` 加一句 |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只換 `apps/runtime/session_idle.py` 的摘要；工具清單不變，`docs/tool-surface.md` 重產後沒有差異 |
| `docs/operations/guide.md` | 安裝檢查表第 6 點加一段（未發版）：3000 上的 Python 子程序只接受 gateway 自己的 child bearer，直連不帶、帶錯或多帶一律 401，沒有有效的 child token 就不啟動；n8n 的子程序本來就只認同一個 child token；Odoo Manage 維持原狀 |
| `docs/provenance/ha-multiprofile-HM-06-20261114.md` | 本筆記 |

沒改：`gateway.py`、`health.py`、`capabilities.py`（本來就帶 child bearer）、`config.py`、`lifecycle.py`、`apps/n8n/`、
`apps/odoo-manage/`、各產品的 launcher、`run_child.py`、測試替身（`tests/owned_*`、`tests/log_scan.py`）、HM-01 的黃金回歸與
契約凍結、版號、`addons/<x>/`、CHANGELOG、`upgrade-notes.yaml`、workflow、`packaging/`。

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
- 每個 manager 都包，含 stateless（idle 上限只給 stateful，bearer 不分）。閘門在 SDK 的 body 上限外面：沒帶對 bearer 的請求，
  SDK 一個位元組都不讀。
- 帳本的 guarded sources（17 個）：7 個 venv 的 `mcp/server/streamable_http_manager.py`（原本 6 個，補上 Headscale）；Odoo、Hermes、
  OpenDesign 的 `mcp/server/mcpserver/server.py` 與 `mcp/server/lowlevel/server.py`（MCPServer 建路由）；EMQX、LiteLLM、Nextcloud、
  Headscale 的 `fastmcp/server/http.py`（FastMCP 建路由）。SDK 升版時 `tests/test_tool_inventory.py` 會擋，要重新審查掛點。
  和其他 guarded sources 一樣只在測試時比對，執行期不比摘要。

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
  別帳號的、沒有的都 401。測試照實釘住（`N8N_ALSO_ACCEPTS`）。閘道從不送兩個標頭。
- Odoo Manage：已下架（0.1.5 起沒有映像）；launcher 不呼叫 `session_idle`（mcp 1.30.0），`child_spec` 不給這個變數，
  維持現狀（計畫 §8.3），寫進 `docs/operations/guide.md`。

## 4. 新測試、先紅後綠與臨時突變

### 4.1 新測試

`tests/test_child_bearer.py`（28 案，全部用 HM-01 的 `log_scan`；token 都在執行時產生，憑證 `DUMMY-…`、網址 `.invalid`）：

| 測試 | 驗什麼 |
|---|---|
| `test_child_spec_gives_the_seven_python_children_their_child_token`（9 個產品） | 每支子程式拿到的環境變數集合＝`bb48449` 的集合，7 支 Python 子程式多 `WOOW_MCP_CHILD_TOKEN`（值＝state 的 child_token），n8n、Odoo Manage 不變；add-on token 不進子程式；兩個 token 都不在 argv（env 快照，C4-SF-4） |
| `test_the_token_is_read_from_the_environment_or_the_child_refuses` | 缺、空與 11 種格式錯（短、長、結尾換行、結尾空白、開頭空白、`.`、`=`、`+`、`/`、非 ASCII、帶 `Bearer `）都是固定訊息的 `RuntimeError`，沒有串接例外 |
| `test_the_gate_lets_only_the_child_bearer_through` | 程序內驅動 `ChildBearer`：14 種拒絕都回同一個 401、內層 0 次；只有一個值時才 `compare_digest`；名稱只差大小寫的兩個標頭算兩個；websocket、lifespan 不交下去；`repr` 沒有 token |
| `test_install_gates_every_manager_or_refuses_before_patching`（兩種 SDK） | hermes（MCPServer）、emqx（FastMCP）的 venv：stateful、stateless、位置參數、明確參數、SDK 自己的 server 與 FastMCP 子類別，5 個 manager 的 `asgi_app` 都是 `ChildBearer`、裡面是 SDK 的 `RequestBodyLimitMiddleware`；缺、空、格式錯時 `install()` 拒絕而且 `__init__` 沒被換掉 |
| `test_real_child_serves_only_its_own_child_bearer`（7 支） | 真子程式：直連 14 種拒絕都 401（沒有本文、沒有 session）；2 MiB body 也立刻 401、下一個請求照常；session 內不帶、別帳號、兩個標頭的 POST、GET、DELETE 都 401，session 還在；自己的 bearer 200。閘道 A 正常（tools/call 打到後端）；閘道 B（別帳號的 child token）initialize 與帶 A 的真 session 的 tools/call 都 502、後端 0 次；B 的健康監看 not ready、A 的 reachable。原始輸出沒有 4 個 token 的任何 16 字元片段；子程式只起一次 |
| `test_real_n8n_child_serves_only_its_own_auth_token` | 真 n8n 子程式：14 種裡 11 種 401，3 種（第 3.7 節）收下；原始輸出沒有 token |
| `test_a_child_without_a_valid_child_token_refuses_to_start`（7 支） | 照 add-on 的方式起真子程式（私有 port），缺、空、格式錯三種：結束碼非 0、stderr 有固定訊息、沒有 `Uvicorn running`、輸出沒有 token |

### 4.2 先紅後綠

先寫測試，再拿 `32ecac8` 的 `session_idle.py`、`products.py` 跑同一個測試檔（跑完換回本片的檔、核對摘要）：

| 階段 | 結果 |
|---|---|
| 第一次：測試檔的前一版＋`32ecac8` 的兩個執行期檔 | 25 失敗、3 通過（24 秒）。拒絕啟動的 7 案在讀 `session_idle.REFUSED` 時就失敗，沒有測到行為。所以把固定訊息改放在測試檔裡（另驗模組的常數相同）、子程式起來了就明確失敗，再跑一次 |
| 第二次：最終的測試檔＋`32ecac8` 的兩個執行期檔 | 25 失敗、3 通過（443 秒）。通過的 3 案本來就該不變：n8n 與 Odoo Manage 的環境變數集合、真 n8n 子程式。失敗的原因：7 支子程式的環境沒有這個變數；`bearer()`、`ChildBearer` 還不存在；兩種 SDK 的 manager 沒被包、缺 token 也照常 patch；7 支真子程式不帶 bearer 也回 200；7 支子程式缺、空、格式錯時照樣起來（stderr 有 `Started server process` 或 `Starting MCP server`；同時起的三個程序有兩個撞同一個私有 port 結束） |
| 最終的測試檔＋本片的實作 | 28 案全過（35 秒；另在全套 pytest 裡也全過） |

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
另外重跑一次（上表是重跑的結果）。

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

## 6. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

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
| `scripts/ledger_precheck.py` | OK（第 9 節） |
| UI `npm test`、Playwright `test:browser`、`build-closure.mjs` | 沒跑：本片沒動 `packages/mcp-admin-ui/` 與 `tests/owned_network.cjs`；CI 會跑 |
| `git status` | 乾淨（commit 之後） |

## 7. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。新測試不靠執行身分或權限下判斷；CI 以 root 跑子程式，
  bearer 的判斷和 uid 無關，預期結果相同。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root）。它的
  子程式是一支假 listener（`tests/owned_uid_probe.py`），不是 MCP 子程式，本片不影響它。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。
- 容器驗收（`packaging/container_acceptance.py`、`container_probe.py` 在映像裡跑）：要 docker 與建好的映像，本機與 PR 的 CI 都不跑，
  留給 HM-19a 前的 builder 乾跑。探針只經 8081，不直連子程式。

## 8. `checks` 秒數

- 前：HM-01 的 PR #90（head `32ecac8`）`checks` 1434 秒（run 43587407864）。
- 後：開 PR 後補。
- 推估：新測試本機約 35 秒（7 支真子程式各約 1.5～3 秒、真 n8n 1 秒、拒絕啟動 7 支各約 1 秒）；改過的既有測試只多 7 個直連請求。
  推估 CI 多 40～70 秒，在每片 1.5 分鐘的預算內。

## 9. 預檢結果

- **秘密預檢**（`scripts/secret_precheck.py`）：gitleaks 8.28.0（釘選、執行檔摘要相符）；設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本分支的 commit（`bb48449..HEAD`，git 模式；HM-01 的 9 個＋本片 3 個，含本筆記） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史（建置機同款） | 0 |

- **帳本預檢**（`scripts/ledger_precheck.py`）：`runtime-patches.json` 163 個路徑（`session_idle.py` 的 guarded sources 多 11 個）、
  `runtime-sources.json` 70 個 vendored 檔、`tool-surface.json` 159 個摘要，都 0 漂移、0 缺檔；對 `origin/claude-delivery` 改了
  28 個檔（含 HM-01 的檔），列管檔 2 個（`session_idle.py`、`products.py`），帳本同時改了（`runtime-patches.json`、
  `tool-surface.json`），新增或改到而沒列管的執行期檔 0 個。結果 OK。

## 10. PaaS 變動

- 沒有連 Gitea（這一波不連遠端）。用本機 PaaS 研究 clone 已經 fetch 的 `origin/main`（`cf3d0d5`，2026-11-14 22:30 台北）跑
  `git log 69ac425..origin/main -- packages/mcp-admin-core/mcp_admin_core/{profiles,process,proxy,child_identity,launch_policy}.py docs/security/mcp-child-identity.md apps/n8n`：
  兩個 commit，都只改文字：`19f36e2`（#148 之後的文件更正：`proxy.py` 只改註解）、`8bfb12e`（`apps/n8n/Dockerfile` 一行註解拿掉
  已移除的 vk）。沒有可執行的改動和子程式 bearer 有關。
- 主對話開 PR 前，在連得到 Gitea 的地方用最新的 `origin/main` 再跑一次。

## 11. 驗收條件（計畫 §12.3 HM-06）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR（這一波不 push；主對話等 #90 合併、依帳本順序 rebase 後開 PR）。本機見第 6 節 |
| 單帳號經閘道的行為不變（HM-01 黃金回歸與契約凍結逐位元照過） | 通過（本機）：`test_single_profile_golden.py` 17 案、`test_mcp_contract_freeze.py` 9 案（99 個契約案例）、`test_admin_contract_freeze.py` 19 案全過，期望值與案例檔沒改；`gateway.py`、`health.py`、`capabilities.py` 沒改 |
| 容器探針的單帳號路徑照過 | 本機能跑的部分通過：`packaging/validate.py` PASS、packaging unittest `Ran 184`、`OK (skipped=5)`。探針只經 8081，不直連子程式；閘道本來就帶 child bearer。實際容器留給 HM-19a 前的 builder 乾跑（本片沒跑） |
| 下一階段的獨立安全審查 | 待做（下一階段） |
| 7 支 Python 子程式一律要求 child bearer；只接受正確的 `Authorization: Bearer <child token>`，其他 401 | 通過（第 4 節；真子程式 14 種拒絕＋session 內＋2 MiB body） |
| env 缺、空、格式錯時拒絕啟動 | 通過（程序內 13 種、兩種 SDK 各 3 種、7 支真子程式各 3 種） |
| token 不出現在 stderr、log、錯誤訊息 | 通過：子程式原始輸出、`log_scan`、拒絕訊息、argv 都 0 命中；臨時突變 M9 證明這個檢查有效 |
| `child_spec` 只給 7 支 Python 子程式；n8n 的 Node 子程式照計畫 §8.3 | 通過：n8n 不變（本來就驗同一個 child_token）；Odoo Manage 不變 |
| 受影響的既有測試更新、env 快照重定（C4-SF-4） | 通過（第 5 節；環境變數集合快照在新測試，`test_nextcloud_child.py` 的完整快照已更新）。HM-04 若有自己的快照，rebase 時加這個變數（第 12 節） |
| 同 PR 更新帳本、重產 tool-surface | 通過：帳本預檢 OK、`scripts/tool_inventory.py` 檢查通過、`tests/test_tool_inventory.py` 全過 |
| 先寫測試、記下先紅後綠 | 通過（第 4.2 節） |
| 新測試用 HM-01 的 log 掃描、沒有條件式 skip | 通過：`pytestmark` 用 `log_scan`；沒有 `skip`／`skipif`／`xfail` |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 在執行時產生或用 `C`×43；憑證 `DUMMY-…`、網址 `.invalid`；沒有 commit 隨機 token；秘密預檢 0 命中 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG | 通過 |

## 12. 還沒解決、交給後面的片

- **要主對話決定（回報，不是本片自己定）**：HM-00 `acceptance-matrix.md` T-23 寫「7 支 Python 子程式＋n8n：不帶、帶錯、帶別帳號、
  兩個標頭、空字串都 401」。實測沒改的 n8n：不帶、帶錯、帶別帳號、空字串都 401，但「兩個標頭而第一個是自己的 token」與
  「兩個空白」會收下（第 3.7 節）。沒有錯的或別帳號的 bearer 能通過，閘道也從不送兩個標頭。可選：(a) 改 T-23 的寫法（n8n
  不保證「剛好一個標頭」，記成刻意差異）；(b) 另開一片在 n8n 的 `backend_policy.cjs` 前置擋重複標頭（要改 n8n，計畫 §8.3 目前寫維持現狀）。
- 合併順序 HM-04 → HM-06（計畫 §12.2）：rebase 到 HM-04 之後一律重產帳本（`products.py`、`session_idle.py` 的摘要）與
  tool-surface、重跑 CI。HM-04 若加了 argv／env 快照（它的驗收寫「與 `bb48449` 位元相同」），7 支 Python 子程式的快照要加
  `WOOW_MCP_CHILD_TOKEN`（C4-SF-4）。本片 `ENV_KEYS` 是 `bb48449` 的集合；HM-04 照計畫不改預設帳號的環境變數，不用動。
- HM-00（#89）合併後：`decisions.md` 的 DQ-08 可記「細節照計畫 §8.3 實作（HM-06）」；要不要記、怎麼記由主對話決定。
- HM-09：額外帳號的子程式拿自己 state 的 child_token（每帳號不同）；直連矩陣可以重用本檔的 `refusals()`。
- HM-13b：重產 child_token 之後要重啟子程式（子程式只在啟動時讀一次）。
- HM-15（條件式）：「別的程序先綁住 port」不在本片範圍。
- HM-09／HM-30 的 log 事件：子程式回 401 時，健康監看只看得到 readiness false（`MCP_SERVER_NOT_READY`），沒有專屬原因碼；
  要不要加，由那兩片決定。
- HM-18：把 `docs/operations/guide.md` 這段帶進各產品 DOCS。
- `checks` 的「後」秒數：PR 的 CI 跑完後補。
