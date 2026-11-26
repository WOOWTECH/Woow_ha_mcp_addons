# 同一個 session 內進行中的重複 JSON-RPC id（PaaS #161 的移植，2026-11-25）

分支 `feat/duplicate-jsonrpc-id-20261125`，基準 `claude-delivery` `092b1b5`。不受開關管（所有產品、開通與否都生效），隨火車 B 發佈；
版號、`features.MULTI_PROFILE_PRODUCTS`、`addons/` 都沒動。規則見 `docs/multi-profile/contract.md` 第 2.8 節（第 1.2 節記回應的改變，第 4.2 節是錯誤代碼，
第 9 節 #145（原稿 #134，火車 B 升版時依「後合併的重編」改號）是和 PaaS 的差異；列號暫定）。

## 1. 來源與為什麼

PaaS `WOOWTECH/woow-mcp-server` #161 的三個 commit（2026-11-23；本機副本在 repo 外的 `notes/paas/`）：`81fd50a`（主修：登記表、轉送前登記、結束時放、
重複回 400／`-32600`／`id: null`）、`ad03275`（審查後：每帳號上限、單一 POST 的 id 數門檻、補測試）、`39891b6`（拒絕的 log 改走閘道的節流）。
程式照 HA 的閘道自己寫，沒有複製 PaaS 的程式；拒絕訊息的文字照 PaaS 原文（id 的顯示不同，第 3 節）。

MCP Python SDK 2.3.0（七個 Python 產品的子程式都釘這一版）的 Streamable HTTP 以 `str(message.id)` 當回應串流的鍵（`server/streamable_http.py`：
`request_id = str(message.id)`、`self._request_streams[request_id]`，SSE 與 JSON 模式都是）：同一個 `Mcp-Session-Id` 內兩個進行中的請求用同一個 id，
後一個蓋掉前一個的串流。本機實測（一次性腳本，不在 repo）：HA 的真閘道（開關關）接真的 SDK 2.3.0 子程式與一個睡 2 秒的唯讀工具，同一個 session 同時
8 個 id=7 的請求——沒有登記表：1 個有回答、7 個卡住（用戶端 15 秒放棄；閘道自己的期限是 330 秒）；有登記表：1 個有回答（2.05 秒）、7 個在約 0.05 秒內被拒
（400／`-32600`），之後同一個 id 可以再用。和 PaaS 2026-11-17 的實測相同。n8n 的子程式是 Node（n8n-mcp、TypeScript SDK），它對重複 id 怎麼回**沒實測**；
閘道的檢查和子程式無關，照樣生效。

## 2. 掛在哪裡

- **`gateway.serve`，拿到轉送名額、政策與待送回覆額度的重驗都過了之後、轉送之前**：只管「閘道已經決定轉送給子程式」的請求；閘道自己回答的（initialize 的自答、
  tools/list 自答、被政策拒絕的 tools/call、未知方法、子程式沒起來時的 session、轉送名額的忙碌回答）在它前面就回了，不登記也不檢查；通知、GET、DELETE 沒有 id 或不是
  請求，也不登記。登記在 `reserve_reply`（開通 Odoo 的回覆票券）與位元組預算的轉送扣款**之前**：重複的 id 先拿到 400，不佔票券、不做 `json.dumps`。
- **釋放掛在 `UpstreamOwner.close`，和轉送名額同一處放**：回應送完、用戶端斷線、`LeasedResponse` 的 token 換掉（`-32005`；沒開通是 `ClientDisconnect`）、子程式斷線
  （`-32004`）、閘道逾時、`serve` 的 `finally` 接住的所有例外與取消（`close` 的清理在 `anyio.CancelScope(shield=True)` 裡），所有結束都經過同一處，釋放可重複呼叫、只放一次。
  **另外**，SSE 串流的最後一個事件到手時就先放（`stream()`）：拿到回覆就用同一個 id 再送的用戶端，遇到的是已經放掉的 id，不會被自己上一個請求的收尾擋到（PaaS 沒有這一步）。
- **登記表**：`ProfileManager` 建一份（各帳號共用，鍵 `(帳號 id, Mcp-Session-Id, str(id))`）；沒開通時 `make_apps` 自己建一份。`make_apps(inflight=…)`、
  `ProfileRuntime(inflight=…)`；`mcp_app.state.inflight` 給測試與診斷。
- **O(1)**：只用已解析的訊息裡的 id，不再讀 body；登記、檢查、釋放是幾次集合與計數的操作；id 先比長度才雜湊（超過 256 字、或整數超過 1,024 位元的不登記，也不轉成字串）。
  本機 `timeit`：登記加釋放約 2 µs、重複的檢查約 1 µs、16 MB 的 id（不登記）約 0.6 µs，不隨 body 大小變。

## 3. 和 PaaS 不同的地方（取捨）

| 項目 | PaaS #161 | HA | 理由 |
|---|---|---|---|
| 登記的時機 | 轉送之前（等名額的請求也登記） | 拿到轉送名額之後 | 一個帳號登記的 id 不會比它的轉送名額多，上限自然有界；代價：重複的請求要先拿到名額（最多等 1 秒，或排隊已滿的 `-32003`）才被拒 |
| batch | 整包登記或整包拒絕；單一 POST 超過 256 個 id 不登記 | 不適用 | `policy.authorize` 本來就只收單一訊息（batch、對伺服器請求的回應、沒有 id 的工具呼叫都在名額之前 403） |
| 全表上限 | 20000，環境變數 `MCP_GATEWAY_MAX_INFLIGHT_IDS` | 512，程式常數，不讀環境變數 | HA 的限制都是程式常數（契約 #45）；512 大於全 add-on 最多同時持有的量（Odoo：32＋5×16＝112），`tests/test_inflight_ids.py` 在名額改了的時候擋住 |
| 每帳號上限 | 全表的 1/4 | 該帳號的轉送名額（預設帳號 32、額外帳號 16） | HA 的額度結構：真正轉送給子程式的是轉送名額；一個請求一個 id、持有一個名額到結束 |
| id 的長度 | 不限；訊息用 `repr` 寫整個 id | 超過 256 字不登記（放行，記一行 WARNING）；訊息最多顯示 64 字、`ascii()` 跳脫、超過寫總長度 | 用戶端可以塞 16 MiB 的 id：不能讓它進回應或 log，也不能讓事件迴圈雜湊它；256 字是 `request_limits.head_tail_id` 讀 id 的上限 |
| 釋放 | 回應送完 | 子程式回答完（SSE 最後事件到手）或最晚和轉送名額一起 | 見第 2 節 |
| 拒絕的 log | 節流（每帳號 60 秒一行） | `budget_share.warn`，同一套，帶帳號 id 前 8 碼；放不下三種各一種情況 | HA 的慣例；文字固定，沒有 id、session id、token。每帳號的節流情況多 4 種（約 23 種，Odoo 六帳號加共用 token 的組別約 195，小於 `MAX_REPORT_KEYS` 256） |

## 4. 驗證（本機，2026-11-25）

全部在本機（2026-11-25）、一次只跑一個 pytest 程序；沒有 HAOS 實機，沒有 Cloudflare 那一段。本機環境照 `packaging/unit.sh`：各產品的 `uv sync`（含 odoo-manage）、
n8n 的 `npm ci` 加 `apps/n8n/patches/*.py` 與 better-sqlite3 預建檔、面板的 `npm ci` 加 `npm run build`；另有只在本機用的小外掛（這台找不到 `node`、主機名解析成
127.0.1.1），不在 repo 裡。

- **新測試** `tests/test_inflight_ids.py`：81 個（開關關與開兩種模式；真的閘道、模擬的子程式；PaaS `test_proxy_inflight_ids.py` 的 19 個測試函式〔20 案〕逐案的對照在檔頭）。
  先紅後綠：對 `092b1b5` 的程式（`gateway.py`、`profile_runtime.py` 還原、沒有 `inflight_ids.py`）81 個全部各自失敗（不是收集錯誤）；最後的程式 81 個全過。
- **突變** 19 個，每個只改程式一處，改完一律還原並核對 sha256，每個都被新測試抓到（先跑一次沒突變的對照：81 個全過）：
  放掉 id 的路徑——完全不放、`close` 不放、SSE 最後事件不提早放；鍵——少帳號、少 session、用原始 id 不用 `str(id)`、每個帳號各一份登記表；登記的範圍——`initialize` 也登記、
  閘道自己回答的也登記；上限——沒有全表上限、沒有每帳號上限、上限判斷排在重複判斷前面、沒有 id 長度上限、每帳號的計數沒有還；回應與 log——拒絕回在請求的 id 底下、
  每次拒絕記一行、顯示整個 id、log 帶 id、log 帶 session id。
- **HM-01 黃金回歸與兩個契約凍結沒動**：`tests/test_single_profile_golden.py`、`tests/test_mcp_contract_freeze.py`、`tests/test_admin_contract_freeze.py` 與 `tests/contract/`
  相對 `092b1b5` 沒有任何差異；17＋9＋19 個全過，開通後同一組黃金回歸的 `tests/test_router_passthrough.py` 49 個也全過。
- **既有測試**：改了三個檔（commit `62feb12`，理由寫在 commit 內文）：三個用一模一樣的請求佔滿名額或預算的測試（兩個各 32 個 ping、一個 20 個同一份 body）改成各自的 id 或 session（它們檢查的東西不變），`make_apps` 的選項清單多一個
  `inflight`。這四個測試對 `092b1b5` 的程式：選項清單紅，其他三個過。
- **沒有任何既有測試撞到新規則**：本機外掛記下每一次沒登記成功的呼叫（重複、表滿、帳號滿、id 太長）與當時的測試名稱；下面每一輪裡，新測試檔以外一次都沒有。
- **最後的程式上跑過的既有測試**：(a) 新測試、黃金回歸、兩個契約凍結、開通後的黃金回歸、三個改過的既有測試檔，共 343 個：342 個過，1 個是本機外掛自己的錯（把 `2**100000`
  轉成字串記 log）；外掛修好後單獨重跑那一個，過。(b) 閘道、名額與佇列、結尾、預算、session、initialize、串流、回覆處理、帳號執行套件與路由、Origin 政策等
  27 個檔，共 1,393 個：1,387 個過。(c) 帳號管理 API、EMQX 與 LiteLLM 的真子程式多帳號測試、Nextcloud 子程式、Odoo 換身分、`test_tool_inventory.py`
  （含 `runtime-patches.json` 逐檔核對）等，共 183 個：174 個過。失敗的都在下一點。
- **失敗的既有測試都不是這次造成的**：下面這些在基準 `092b1b5` 的程式上**同樣失敗**（基準用 `git archive` 展開在 repo 外，同一台機器、同一組相依、同一輪重跑；Supervisor 的三個另外用規則給的指令、不帶任何外掛兩邊各跑過一次，也一樣失敗）：
  `test_review_regressions.py::test_stop_during_natural_exit_cleanup_reaps_group[False／True]` 與 `test_profile_lifecycle.py::test_stop_all_stops_every_child_at_once_within_haos_30_seconds`
  （用真的子行程測 Supervisor 的收尾與停止時間，這台的行為和測試預期的不同；和閘道無關，原因沒查）；`test_boundary.py::test_the_n8n_child_loads_the_one_pinned_native_addon_and_n8n_mcp_uses_it`
  （預建的 better-sqlite3 是 Node 26 的，這台的 node 是 22，載入失敗、退回 sql.js）；`test_profile_quotas.py::test_the_default_profiles_token_holder_cannot_exhaust_memory`
  （請求預算依啟動時的 MemAvailable 推導，這台的份額只有 16 MiB，測試要 64 MiB）；`test_reply_worker.py` 迴圈延遲的測試（門檻 50 ms，有負載時超過；基準上失敗得更多）。
  面板沒建置時另有四個測試回 503（`test_profile_runtime.py` 兩個、`test_profile_admin_api.py` 兩個），`npm run build` 之後全過。
- **真的 SDK 子程式**（一次性腳本，不在 repo）：HA 的正式 runtime（開關關）接 `apps/odoo/.venv` 的 mcp 2.3.0 與一個睡 2 秒的唯讀工具，同一個 session 同時 8 個 id=7：沒有登記表 1 個有回答、7 個卡住（用戶端 15 秒放棄）；
  有登記表 1 個有回答（2.06 秒）、7 個在約 0.05 秒內被拒（400／`-32600`），只記了一行 WARNING，之後同一個 id 可再用。
- **事件迴圈上的成本**（`timeit`）：登記加釋放約 2 µs、重複的檢查約 1 µs、16 MB 的 id（不登記）約 0.6 µs，不隨 body 大小變。
- **`packaging/validate.py`** PASS；**`scripts/ledger_precheck.py`**：0 漂移（`runtime-patches.json` 186 個、`runtime-sources.json` 70 個、`tool-surface.json` 160 個列管檔都在，
  各產品相依都裝了），沒有未列管的新檔；**`scripts/secret_precheck.py`**（gitleaks 8.28.0，釘版）：四個 commit 0 個發現。

## 5. 限制與沒驗證的事

- id 在**閘道**認為請求結束時釋放（回應送完、用戶端斷線…），不是子程式把工具跑完的時候：用戶端斷線後，子程式可能還在跑那個工具；之後同一個 id 再用（規格本來就禁止重用 id），
  在 SDK 裡仍可能撞到舊請求的回覆。這和 PaaS 一樣，閘道看不到子程式內部。
- SDK 在子程式那一側清掉串流表是非同步的：用戶端拿到回覆立刻重用同一個 id 時，理論上有一個極短的窗口（比兩段 HTTP 往返短得多）。沒量到、PaaS 一樣。
- n8n 的子程式（Node）對重複 id 的行為沒實測；沒在 HAOS 實機與 Cloudflare 隧道後面驗；沒用 Claude、ChatGPT 等真用戶端驗（它們都不重複使用 id）。
- 登記在拿到轉送名額之後：名額全滿、排隊也滿時，重複的請求先拿到 `-32003`（在它的 id 底下），不是 400。要在名額之前就擋，得在 `take_slot` 前另加一次不登記的檢查；這次沒做。
- 回 HTTP 400：MCP Python SDK 1.x 的用戶端遇到非 2xx 會結束 session（`busy_reply` 的註解）。這是 PaaS 的選擇（違規的用戶端），HA 照做。
- 列號 #145 暫定（原稿 #134）。`deviation-trace.md`、`acceptance-matrix.md`、`paas-test-mapping.md` 是 repo 外的產生器重產的，這次沒改；重產後 #145 與新測試的對照才會進去。（火車 B 升版併入時，`deviation-trace.md` 與 `acceptance-matrix.md` 已手改：差異表加第 145 列、只寫出處，計數改成 145 列、對到 133 列、其餘 12 列，測試登記表加 `tests/test_inflight_ids.py`；`paas-test-mapping.md` 仍沒重產，下次重產要加 #145 的對照。）
- 產品 DOCS、`docs/operations/*` 與各產品 CHANGELOG 沒寫（交升版片；句子在 `unreleased-changes.md` 的 A12，原稿叫 A10）。（火車 B 升版時已寫進 Hermes、n8n、Headscale 的 0.5.0 CHANGELOG；其餘產品與 OpenDesign 的來源下一次發版寫，見 `unreleased-changes.md` 第 1 節 A12。）
