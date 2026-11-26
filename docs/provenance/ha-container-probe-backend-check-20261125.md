# 容器探針的拒絕案例與閘道自己的健康檢查撞期（Headscale 0.5.0 候選建置，2026-11-25）

分支 `fix/probe-health-tick-20261125`，基準是火車 B 的發版分支 `20292de`。只動 `packaging/`（探針與它的測試）：映像裡的程式、版號、
`features.MULTI_PROFILE_PRODUCTS`、`addons/` 都沒動。這份是 `packaging/test_container_probe.py` 的 `ADDED_BEYOND_BASE` 要求的說明：新增的那一個
「開通產品專屬」分支是什麼、為什麼加。

## 1. 發生什麼

2026-11-25 18:31 起，火車 B 三個產品用同一個 head（`20292de2b385`）觸發 `release.yaml`。Hermes（run 45595820241）與 n8n（run 45595834338）的候選建置通過；
Headscale 在候選建置的容器探針（`Test and scan this candidate exactly once; fail closed`）失敗，同一個斷言、兩次、兩個不同的案例：

| run | 失敗的案例 | 訊息（`packaging/denial_probe.py:37`） | 距步驟開始 |
|---|---|---|---|
| 45595847885 | 第 1 個：`unknown tool` | `AssertionError: unknown tool: backend contacted` | 18.45 秒 |
| 45602933766（同一個 head 重跑） | 第 2 個：`schema-valid supported write` | `AssertionError: schema-valid supported write: backend contacted` | 18.57 秒 |

每個案例的第一個斷言（閘道自己的 JSON-RPC 拒絕）都過了；失敗的是第二個：被拒絕的呼叫前後，假後端看到的請求數多了。兩次的時間點幾乎相同。

## 2. 成因

- **被拒絕的呼叫沒有被轉送。** 未知工具與沒有授權的寫入由閘道的 `policy.authorize`（`packages/mcp-admin-core/mcp_admin_core/policy.py`，`ToolCallRefused`、
  `Unknown tool`）在轉送之前就回答了；Headscale 的子程式沒有自己的背景請求（`apps/headscale/` 沒有計時器或背景任務；`SavedPolicy` 只讀本機的
  `state.json`），也沒有 HTTP 重試（`http_policy.py` 的 `retries=0`）。就算閘道誤轉送，真的 Headscale 子程式也不會碰後端（它回 `Unknown tool`／
  `HEADSCALE_POLICY_DENIED`）。
- **多出來的請求是閘道自己的健康檢查。** 探針用 `CALLS`（假後端收到的每一個請求）當後端計數，沒有分辨誰送的。開通多帳號的產品，
  `ProfileManager._monitor` 一面跑 `start_all`（預設帳號的子程式在聽 port 之後，`_started` 每 0.5 秒輪詢一次，用 `HealthMonitor.settle()` 做第一次檢查），
  一面讓預設帳號的監看 `run()` 之後每 15 秒檢查；一次檢查經子程式對後端送一個請求（Headscale：`GET /api/v1/health`）。
- **這是啟動相位，不是每 15 秒才撞一次的偶發。** 獨立審查者用真的閘道、真的 Headscale 子程式與探針自己的假後端，重播探針從最後一次啟動到拒絕案例的流程（本機，
  不是 CI），自程序啟動起算：8081 起 1.45 秒、子程式聽 port 6.9 秒、探針的 `initialize` 成功 7.1 秒、第一次檢查的後端請求 8.19 秒、探針自己的 `tools/call`
  8.27 秒、拒絕案例開始 8.3 秒；之後的檢查在 16.5 秒與 31.6 秒。不加等待重播 14 次，第一次檢查每次都落在拒絕案例窗開始前 20～45 毫秒（一次 116 毫秒）；三個案例的
  窗合計約 22～35 毫秒。本機沒撞上，只差十幾毫秒，CI 位移一點就會撞上第 1 或第 2 個案例：吻合「兩次不同案例、時間幾乎相同」。CI 的 18.45／18.57 秒約是最後一次啟動後
  4～7 秒，不是 16 秒的週期檢查（這是推論，沒有 CI 的時間線可核對）。
- **每個開通的產品都貼近，不只 Headscale。** 同樣的重播：LiteLLM 的第一次檢查在窗前 12 毫秒、Odoo 10 毫秒、Nextcloud 74 毫秒；Hermes 在窗後 240 毫秒；EMQX 在探針
  自己的呼叫之前。Headscale 先撞上是相位，不是它慢；火車 A 的產品與這次的 Hermes、n8n 通過，是運氣，不是設計。
- 未開通的產品沒有這個重疊：它的監看在 T0（子程式還沒聽）與 T0+15 秒才檢查，離拒絕案例都遠。

這是探針的設計問題，不是產品的問題：被拒絕的呼叫是否碰到後端，要在「沒有別的請求」的時間窗裡判斷。

## 3. 補強（不是放寬）

- `container_profiles.after_backend_check(probe)`：只對開通多帳號的產品（探針的 `if features.enabled(APP):` 分支，單一帳號路徑一句都沒改，
  `packaging/test_container_probe.py` 的 AST 比對會把關，另有一案釘住這個分支就在拒絕案例之前、只做這件事），在拒絕案例之前等「假後端的請求數成長
  （看到一次檢查）、之後安靜 0.5 秒」。看到的若是第一次檢查，下一次是約 10 秒後的週期檢查；看到的若是週期檢查，下一次在 15 秒後：兩種都離拒絕案例（約 0.1 秒）很遠。
  兩段等待各有 `HEALTH_INTERVAL + 3` 秒的上限（最壞約 37 秒，審查者實測等待 0.7～13.1 秒）；逾時就照舊往下走（best effort），不會卡住。
- **什麼都沒有被過濾或略過**：拒絕案例的斷言（回應與「後端請求數不變」）一個字沒動，`backend_count` 仍是 `lambda: len(CALLS)`；等待只改變「什麼時候量」，不改變「量什麼」。
  審查者另做了反向驗證：讓「未知工具」與「有效寫入」真的被轉送並多打一個請求，補強後的探針仍然失敗，並說出請求。
- 失敗訊息現在會說多出來的是哪些請求（`denial_probe.REACHED`，只在開通的探針設定）：方法與路徑，最多六個，不含 query、標頭與內容；若沒有看到檢查（`SYNCED` 為
  False）也會說。如果成因判斷錯了，下一次失敗會直接說出是什麼，不必再猜。
- 已知的剩餘風險：子程式要約 14 秒以上才聽 port 時，第一次與第二次檢查才會相鄰（安靜只有 0.5 秒）；本機量到 3.7～6.9 秒，CI 的整段探針約 18 秒。

## 4. 測試

`packaging/test_container_profiles.py::AfterBackendCheckTests`（看到檢查並等它結束、沒有檢查時逾時離開、探針自己先前的請求不算檢查、請求不停時有界、預設值涵蓋監看的
間隔）；`packaging/test_denial_probe.py`（訊息有／沒有 `REACHED`、有／沒有 `SYNCED`、至多六個、不含 query）；`packaging/test_container_probe.py`（`ADDED_BEYOND_BASE`
與分支數各加一，另釘分支的位置與內容）。容器內的真實驗證只有候選建置本身（本機沒有 Docker）。

## 5. 獨立審查

2026-11-25，獨立審查者（與寫補強的人不同）：結論「可以推」。沒有削弱把關（只讀 `len(CALLS)`、不過濾、不寫）；有界；對所有開通產品都適用（量了 Hermes、EMQX、LiteLLM、
Nextcloud、Odoo、Headscale，每個的檢查都讓 `CALLS` 成長，沒有白等的產品；n8n 以讀程式推論）；17 個突變殺掉 12 個，存活的 5 個（預設常數、分支位置與內容、安靜段、
`REACHED` 的全域狀態、檔案排版）已全部補測試或修正。審查者也更正了本筆記的兩處措辭（「Headscale 啟動最慢所以先撞上」缺證據；「下一次檢查在 15 秒外」只在看到週期檢查時成立）。
沒驗證的：真容器（entrypoint 降權、`--read-only`、docker bridge）的實際時間與整體探針秒數（候選建置本身會驗）。
