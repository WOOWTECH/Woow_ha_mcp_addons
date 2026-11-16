# HA 多帳號 HM-31 provenance：對齊 PaaS #155，閘道請求內容位元組預算與 JSON 結構守門（所有產品生效）（2026-11-16）

## 結論

- **對齊 PaaS #155（woow-mcp-server `d7f5849`），所有產品都生效（不受開關管）**：使用者 2026-11-16 07:1x 決定。開關關時，只有超過上限的
  請求回應改變（第 8 節逐項）；上限內的請求逐位元照舊，HM-01 的黃金回歸與兩個契約凍結斷言一個字都沒改（第 7 節逐組核對）。
  repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **HM-08 的每帳號位元組額度併成一套**：新模組 `request_budget.py`，全 add-on 一份預算、每帳號一個份額，兩層都放得下才放行（PaaS）。
  HM-08 和 PaaS 不同的地方逐項取 PaaS 的做法；HA 較嚴而保留的寫進契約第 9 節（加嚴 #98 份額上限 64 MiB、#99 轉送的大小也扣），
  平台差異寫成部署或既有（#100～#104）。HM-08 的拒絕小額度（同時 8 個、合計 512 KiB）拿掉。
- **常數的推導**：PaaS 公式 (上限−76−帳號數×子程式 MiB−150)÷20（16 MiB～16 GiB）。上限取 cgroup 記憶體上限；HA 的 add-on 通常沒有，
  改取 MemAvailable 減 256 MiB（計畫 §5.2 的「MemAvailable－保留量」）；都讀不到固定 32 MiB。每帳號份額＝min(64 MiB, max(16 MiB, 全 add-on÷2))。
  啟動時讀一次。全部暫定，待 HM-19c 量測（第 11 節）。
- **HM-14 審查 MF-2 (b)**（2026-11-16 07:5x 主對話定案，DQ-07 的數值不改）：准入滿時仍讀 ≤64 KiB 的 POST（2 秒內，同時讀幾個不設上限），
  只有通知或回應的照常交帳號 app，`notifications/initialized` 經保留名額送到子程式。補了「佇列與准入都滿時，剛連上用戶端的
  `notifications/initialized` 仍送到子程式」的測試。
- **測試**：新 3 檔 149 案（預算單元 42、結構守門 82、端到端 25：開關關 14＋8 個產品的正式 runtime、開關開 3）＋改既有 5 檔。
  **先寫測試**：在 `351666f` 的程式上新與改過的測試先紅：新 3 檔當時的 141 案有 138 案失敗、之後加的 8 個產品案 8 案全失敗，改過的 5 檔 20 案失敗（第 6.1 節）。臨時突變 20 個全部擋下（第 6.2 節）。
  PaaS 5 個測試檔 84 個案例逐案對照（第 5 節：78 案有對應，6 案不適用並寫理由）。
- **兩個預檢**：秘密預檢 0 命中、帳本預檢 OK（第 13 節）。本機全套 pytest：**沒跑**（共用 pytest 鎖前面排了另外兩條線，這個階段結束前沒輪到）。
  新與改過的測試用迷你執行器全綠，3 檔正式 pytest 131 案全過，validate 與 tool_inventory 過（第 9 節）。以 CI 為準。
- **還沒做**：獨立安全審查（驗收條件之一，交主對話安排）；rebase 到 `claude-delivery`（HM-14 合併後，第 15 節列出預期的衝突）；
  本機全套 pytest 與 packaging unittest（第 9 節）；開 PR 後補 `checks` 秒數。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-31（計畫 §12.3，2026-11-16 新增；風險高、工作量 M；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm31-20261116`（一般 clone，不是 worktree） |
| 基準 | `351666f`（HM-14 的修正 head：`claude-delivery` 的 HM-08 合併點 `b5d10c5`＋HM-14 的 10 個 commit）。`claude-delivery` 之後的 #100、HM-09（#101）、HM-20、HM-14 本身都不在本分支；主對話在 HM-14 合併後 rebase（gateway.py 的順序 HM-14 → HM-31；和 HM-30 誰後合誰 rebase） |
| 依據 | 計畫 §12.3 HM-31、§5.1、§5.2；契約第 1.2、2、4.2、5、9 節；威脅模型 I8；HM-08、HM-14 的 provenance 筆記與審查報告（`artifacts/…/wave3/review-HM-08.md`、`wave4/review-HM-14.md`）；決策見第 12 節 |
| 對齊的 PaaS | `woow-mcp-server` main `d7f5849`（#155：`7ba572d`、`3b135ca`、`e6971c0`、`1637a0f`、`a2f8905`）：`request_budget.py`、`request_limits.py`、`request_body.py`、`proxy.py`、`app.py`、`gateway_pool.py`、`profiles.py`、`docs/mcp-gateway-limits.md` 與 5 個測試檔、9 個產品的 `test_request_structure_guard.py`。本機唯讀 PaaS repo（沒 fetch、沒 checkout；`origin/main`＝`d7f5849`） |
| 移植的 PaaS 程式 | `request_limits.py` 的 `structure_violation`、`not_utf8`、`NOT_UTF8_REASON`、`DEFAULT_MAX_TOTAL_ELEMENTS`、`DEFAULT_MAX_DEPTH`、`_RUN_THEN_STRUCTURE`，`request_body.py` 的 `_request_id` 與四個正規表示式（HA：`head_tail_id`）、`too_complex` 的訊息：照搬，正規表示式逐位元相同（本機用 PaaS 原始碼 `exec` 比對過）。`request_budget.py` 的公式、常數與訊息照 PaaS；類別與 ASGI 接線是 HA 自己寫的（HA 的閘道不是 FastAPI proxy） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/request_budget.py`（新） | `RequestBudget`（全 add-on＋每帳號）、`Share`（份額＝min(cap, per_profile)）、`Reservation`（收到與轉送兩者較大的，超過 64 KiB 才扣；超過單筆上限不扣；`close` 歸還）、`BudgetLimits.derive`（cgroup → MemAvailable−256 → 32 MiB；帳號數依開關）、`memory_limit_mib`、`available_memory_mib`、`memory_ceiling`、`watch`（宣告長度先扣、沒帶的邊讀邊扣、閒置 30 秒）、`drain`（讀完丟掉、只留頭尾）、`budget_text`、`idle_text`、`budget_note`、`Reports`（從 `profile_router.py` 移來，logger 可指定）、`own_share`（沒開通的 add-on 自己的預算） |
| `Hc/request_limits.py` | 照搬 PaaS 的結構守門與 UTF-8 檢查、`head_tail_id`、`too_complex`；`RequestLimitError` 加 `kind`、`log_reason`；`McpRequestLimits` 加 `max_total_elements`、`structure_reason`、`check_structure`；`parse_and_check` 先跑 `check_structure`（n8n） |
| `Hc/gateway.py` | `STRUCTURE_LIMITS`；`BODY_RESERVATION`（取代 HM-08 的 `FORWARDED_BODY`）；`AnyMethod(handler, budget)` 開關每個請求的預約；`json_body(request, guard)`；`idle_reply`；`make_apps(body_budget=…)`（沒給就 `own_share`）；`serve()`：token、方法、Origin、query 檢查之後才裝 `watch`，讀 body 的整段包住 `BudgetExceeded`（`over_budget`：宣告的讀完丟掉、從頭尾找 id）與 `BodyIdleTimeout`（408），結構守門與 n8n 的拒收經 `refused_body` 記 WARNING，標準路徑的 413 也記；轉送前 `reservation.forward(len(content))`；`authorize` 移到讀 body 的 try 外面（順序不變） |
| `Hc/profile_router.py` | `ProfileGate(profile_id, quota, budget, reports)`：不再自己算位元組（拿掉 counted_receive、cut、forwarding、busy_instead）、`budget_share`；准入滿時 `beyond_admission`（`read_small`、`small_message`、`replayed`；`beyond` 計數）；拿掉 `RefusalAllowance`、`REFUSAL_SLOTS`、`REFUSAL_BYTES`、`bytes_text`；`Reports` 改成 `request_budget.Reports` 的子類別（logger 仍是本模組的）；模組說明 |
| `Hc/profile_runtime.py` | `ProfileManager.budget`（啟動時 `derive(product, switched_on=True)`）取代 `allowance`；`ProfileGate` 拿預算；`ProfileRuntime(body_budget=…)` 只在給了時傳給 `make_apps`；`RUNTIME_OPTIONS` 加 `body_budget` |
| `Hc/profiles.py` | 只改 `ProfileQuota` 的說明與 `body_bytes` 的註解（現在是份額的上限）；數值不變 |
| `tests/test_request_budget.py`（新） | 42 案：推導、兩層、份額上限、小請求、單筆上限、歸還、1000 個混合、轉送大小、astral、頭尾 id、文字、WARNING 節流、沒開通的預算 |
| `tests/test_request_structure.py`（新） | 82 案：結構守門的單元（PaaS 的 pathological、邊界、閉括號、UTF-16／32、BOM、合法 UTF-8）、放大語料的解析成本、HTTP 拒收形狀、n8n |
| `tests/test_request_budget_gateway.py`（新） | 25 案：開關關的端到端（預算拒絕、格式、chunked、13.3 MiB、灌爆、歸還、轉送大小、閒置 408、慢但穩定、小請求、涓流、丟的時候用戶端離開、建在 make_apps）、8 個產品的正式 runtime、開關開（份額不跨帳號、全 add-on 共用、份額來源） |
| `tests/test_carries_no_request.py` | HM-14 釘住的現況（准入滿時通知 503）改成 MF-2 (b) 的定案（兩種排隊數都 202），加剛連上用戶端的一案 |
| `tests/test_profile_quotas.py` | HM-08 的位元組額度測試改成一套預算的份額：PaaS 表、准入滿的小請求、攻擊方（12 條 16 MiB，4 條扣、8 條讀完丟掉回 503）、SSE 期間的持有量（被拒的改成 200＋id）、歸還；拒絕小額度的測試換成 `beyond_admission` 的讀取工具 |
| `tests/test_gateway_busy_shapes.py`、`tests/test_profile_routing.py` | `ProfileGate` 的第三個參數、歸還的檢查改看 `manager.budget` |
| `tests/test_n8n_request_bounds.py` | 深度超過 64 一案改成結構守門的回應（200＋id 7） |
| `docs/multi-profile/contract.md` | 第 0、1.2、2.2、2.4、4.2、5、9、10 節（第 3 節表） |
| `docs/multi-profile/threat-model.md` | I8 的做法與測試欄；第 3 節改兩條、加四條 |
| `docs/multi-profile/decisions.md` | 第 1.1 節（兩項計畫外的決定）、變更紀錄一列 |
| `docs/multi-profile/acceptance-matrix.md` | T-19；測試檔登記表加三個新檔 |
| `docs/multi-profile/ledger-tracking.md` | 新模組表加 `request_budget.py`；三個既有列補 HM-31 |
| `docs/provenance/runtime-patches.json` | 新增 `request_budget.py`；更新 `gateway.py`、`profile_router.py`、`profile_runtime.py`、`request_limits.py`、`profiles.py` |
| 本筆記 | — |

沒改：`run_product.py`、`apps/`（含 `apps/n8n/run.py`：n8n 經 `make_apps` 自動拿到預算與守門）、`lifecycle.py`、`health.py`、`config.py`、
`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、
`tests/conftest.py`、`tests/contract/profiles_v1_cases.json`（第 7 節）、`paas-test-mapping.md`、`deviation-trace.md`（兩份由 repo 外的產生器重產，
不手改；本片的對照在第 5 節、差異在契約第 9 節 #98～#104）。

## 3. 設計重點

### 3.1 HM-08 與 PaaS #155 逐項比較（取 PaaS；HA 較嚴而保留的寫進契約第 9 節）

| 項目 | HM-08（`351666f`） | PaaS #155（`d7f5849`） | HM-31 |
|---|---|---|---|
| 預算的層 | 每帳號 64 MiB，沒有全 add-on 的池 | 全域＋每帳號份額，兩層都過才放行 | **照 PaaS**（共用的只有全 add-on 預算與 8081 外框；契約第 5 節、§9 #15） |
| 每帳號份額 | 64 MiB | 全域÷2，至少 16 MiB，沒有上限 | min(64 MiB, max(16 MiB, 全域÷2))：**加嚴**（§9 #98，DQ-07 的 64 MiB 保留成上限、沒改數值） |
| 預設值 | 固定 64 MiB | 依容器記憶體上限推導（公式、放大 20） | 照 PaaS 公式；HA 沒有 Pod 上限，上限改取 MemAvailable−256 MiB（**部署**，§9 #100） |
| 誰生效 | 只有開通的產品 | 全部（PaaS 沒有開關） | **全部，不受開關管**（使用者決定；契約第 1.2 節） |
| 什麼時候開始扣 | 准入時（讀 body 前、token 只比過摘要） | proxy 驗過 token 之後、讀 body 之前 | **照 PaaS**：帳號 app 驗過 token（與方法、Origin、query）之後；沒驗過 token 的請求一個位元組都不扣（防沒有 token 的人佔滿預算） |
| 扣到什麼時候 | 請求結束（MF-1） | 送往子行程的回應結束（transport detach） | 請求結束（`AnyMethod` 的 finally；SSE 串流結束才還）：兩者等價 |
| 小請求 | 每個請求都扣 | ≤64 KiB 不扣、不拒 | **照 PaaS**（收到與轉送都 ≤64 KiB 才算小） |
| 扣的大小 | max(宣告, 已讀, 轉送) | 宣告或已讀（原樣轉送） | 收到的與轉送的兩者較大的：**加嚴**（§9 #99；HA 重新序列化，HM-08 審查 S-1） |
| 超過單筆上限 | 宣告的扣到 16 MiB 為止 | 不扣（之後回 413） | 照 PaaS；HA 的標準路徑會讀到 16 MiB 才 413，所以沒宣告長度或宣告超過上限的仍邊讀邊扣，超過上限那一刻全部還回去 |
| 宣告長度放不下 | 讀之前拒絕；≤64 KiB 用拒絕小額度讀出 id，更大的 503 不讀 | 讀之前拒絕，內容讀完丟掉，只留頭尾找 id（200 或 503） | **照 PaaS**（丟的時候閒置 30 秒、整體 60 秒就不再等；用戶端離開回 499） |
| 讀到一半放不下 | 停讀，app 看到斷線，換成 503 id null | 停讀，id 從已讀的開頭找（200 或 503） | **照 PaaS** |
| 轉送的大小放不下 | 200＋id（不送） | （沒有） | 保留（#99 的一部分） |
| 讀取閒置 | 沒有 | 已登記的大請求 30 秒，408＋`-32003`＋`Connection: close` | **照 PaaS** |
| 整體讀取期限 | 60 秒（`BODY_SECONDS`，每個請求），408 `{"error":"request denied"}` | 已登記的大請求 300 秒，408＋`-32003` | 保留 HA 的 60 秒與今天的回應形狀（**既有**，§9 #102：比 PaaS 嚴，而且不改單帳號既有的 408） |
| 拒絕小額度 | 全 add-on 共用：同時 8 個、合計 512 KiB | （沒有） | **拿掉**：准入滿時的讀取照 MF-2 (b) 不限數量；預算拒絕改成讀完丟掉，不需要額度 |
| 准入滿時的小請求 | 用拒絕小額度讀出 id；通知 503 | （沒有准入） | MF-2 (b)：讀進來，通知或回應照常處理，其他回忙碌（§9 #94 改成部署） |
| 結構守門 | 只有 n8n（深度 64、工具參數 10,000） | 每個產品：深度 64、整個請求 20 萬個元素、只收 UTF-8 | **照 PaaS**（Headscale 照 HA 的預設，§9 #103；不是 JSON 照今天 400，§9 #104） |
| 設定入口 | 程式常數 | 4 個環境變數 | 程式常數（**部署**，§9 #101、#45） |
| WARNING | 每帳號每情況 60 秒一行 | 每帳號每情況 60 秒一行（P2-D：預算、閒置、結構、編碼、超過單筆上限） | 照 PaaS；沒開通的產品寫 `profile=default` |
| `-32003` 文字 | 「這個 MCP 網址進行中的請求內容已達這個帳號的上限」 | 分「這個 MCP 網址」與「這台 MCP 伺服器（所有網址合計）」 | **照 PaaS 原文**（`budget_text`） |

### 3.2 為什麼預算放在帳號 app 裡（不放在分派器）

- 要所有產品都生效，沒開通的產品（8081 直接是預設帳號的 app，沒有分派器）也要有；n8n 自己的 `apps/n8n/run.py` 直接呼叫 `make_apps`。
  放在 `make_apps` 裡，兩種模式、九個產品都走同一段程式，`apps/n8n/run.py` 與 `run_product.py` 都不用改。
- 扣在 token 驗過之後：沒有 token 的請求（錯 token 404／401）一個位元組都不扣，沒有 token 的人佔不滿預算（PaaS 也是驗過 token 才登記）。
- 預約在 `AnyMethod`（每個 MCP 路徑的 ASGI 端點）開、在它的 finally 關：回應整個送完（SSE 串流的最後一個位元組）、用戶端離開、例外、取消，
  一定歸還（`test_the_budget_is_given_back_however_a_request_ends`、突變 B04）。

### 3.3 MF-2 (b) 的做法（`ProfileGate.beyond_admission`）

- 准入滿時：POST、`application/json`、宣告 ≤64 KiB（或沒帶但 64 KiB 內結束）→ 2 秒內讀完（`read_small`，不經任何共用額度）→
  `small_message`（UTF-8、strict JSON、沒有單獨代理字元）→ `carries_no_request` 成立就把讀到的 body 重播給帳號 app（`replayed`），不佔准入
  （`beyond` 計數）；保留名額有自己的 4 條與佇列，再滿就回保留名額自己的忙碌回應。其他小請求回准入的忙碌回應（有 id 200）。
- 讀的數量不設上限（PaaS 的語意），由 8081 外框（Odoo 開通時 224 條）限住：最壞約 224×64 KiB＝14 MiB。2 秒的讀取時限是 HA 加的
  （PaaS 小請求沒有時限），只在准入滿時。
- 剛連上的用戶端：initialize 是帶 id 的請求，准入滿時拿 200＋`-32003`；准入有空位時連上的，之後的 `notifications/initialized` 一定送到。

### 3.4 單帳號的路徑（開關關）

token 檢查 → 租約 → 方法 405 → Origin 403 → query 400 →（HM-31）裝 `watch` → 讀 body（`Content-Type` 415、n8n 的壓縮 415／宣告超過 4 MiB 413
都在讀第一個位元組之前，不扣）→ 結構守門 → strict JSON → `authorize` → 名額 → 轉送前扣轉送的大小 → 轉送。上限內的請求，每一步的回應都和今天
逐位元相同；`authorize` 只是移到讀 body 的 try 外面，順序沒變。

## 4. PaaS 變動清單（`git log --oneline cf3d0d5..d7f5849`，本機唯讀 PaaS repo）

| commit | 內容 | 對本片 |
|---|---|---|
| `7ba572d` | 閘道請求內容位元組預算（全域＋每帳號，proxy 在讀內容前登記、transport detach 時歸還） | 本片第 3.1 節 |
| `3b135ca` | 所有產品的 JSON 結構守門（深度、元素個數）；9 個產品的 `test_request_structure_guard.py` | 本片；各產品的測試對到 `test_every_products_runtime_reads_under_the_budget_and_the_guard` |
| `e6971c0` | 預設值扣掉子行程記憶體、啟動時建立、卡住的上傳逾時（閒置 30 秒） | 本片（HA 不讀環境變數） |
| `1637a0f` | 第三輪：UTF-16／32 繞過、閉括號掃描 DoS、放大倍數低估、涓流整體期限、n8n／Headscale 拒收格式一致 | 本片（整體期限用 HA 既有的 60 秒） |
| `a2f8905` | 放大倍數 20、編碼拒收訊息更正、文件據實 | 本片 |
| `d7f5849` | #155 合併 | — |
| `671d2e7`（#152）、`0f43fd3`、`4f1a77f` | Nextcloud base_url 存檔過 SSRF、日誌遮罩保留 args 形狀 | 不在本片：HM-22（使用者 2026-11-16 定） |
| `a175150`（#154）、`0f94aa4` | Nextcloud 換使用者或網址撤銷舊 MCP 網址 | 不在本片：HM-22 |
| `5b84b5d`（#153）、`cd1ed89`、`4b4fd16`、`574c805`、`e59c9b2`、`fabb192` | EMQX 實測小修 | 不在本片：HM-23 |

`git log cf3d0d5..d7f5849 -- packages/mcp-admin-core/mcp_admin_core/ docs/mcp-gateway-limits.md` 只有 #155 的五個 commit。HM-14 筆記第 10 節已確認
#155 不改 HM-14 對齊的符號。

## 5. PaaS 5 個測試檔逐案對照（`d7f5849`；HA 檔名縮寫：RB＝`tests/test_request_budget.py`、RS＝`tests/test_request_structure.py`、RG＝`tests/test_request_budget_gateway.py`、PQ＝`tests/test_profile_quotas.py`）

### 5.1 `test_gateway_request_budget.py`（20 案）

| # | PaaS | HA |
|---|---|---|
| 1 | `test_defaults_derive_from_the_cgroup_memory_limit` | RB `test_defaults_follow_the_paas_formula_on_a_cgroup_limit` |
| 2 | `test_defaults_without_a_cgroup_limit_and_clamps` | RB `test_without_any_memory_reading_the_budget_is_fixed_and_small_ceilings_are_clamped`；HA 另加 `test_without_a_cgroup_limit_memavailable_less_the_reserve_is_the_ceiling`（沒有 cgroup 上限時用 MemAvailable−256） |
| 3 | `test_environment_overrides_and_invalid_values_warn` | **不適用**：HA 不讀環境變數（契約 §9 #101、#45）；RB `test_the_add_on_reads_no_environment_variable` 釘住設了也不生效 |
| 4 | `test_small_requests_are_never_charged_or_refused` | RB 同名（另含轉送 ≤64 KiB） |
| 5 | `test_profile_and_global_limits_are_independent` | RB 同名 |
| 6 | `test_every_profile_can_always_send_one_maximum_size_request` | RB 同名 |
| 7 | `test_requests_over_the_single_request_cap_are_not_held` | RB 同名 |
| 8 | `test_reservation_is_held_until_proxy_finished_and_every_upstream_closed` | RB `test_a_reservation_is_held_until_its_request_ends`（HA 沒有 transport 的 attach／detach：請求結束時關一次）；SSE 串流期間仍扣著：RG `test_the_budget_is_given_back_however_a_request_ends`、PQ `test_an_event_stream_keeps_its_bytes_charged_until_it_ends` |
| 9 | `test_a_refused_grow_does_not_leak_and_finish_refunds` | RB `test_a_refused_grow_does_not_leak_and_close_gives_back` |
| 10 | `test_thousand_mixed_requests_return_the_budget_to_zero` | RB `test_a_thousand_mixed_requests_give_the_budget_back_to_zero`（加轉送） |
| 11 | `test_transport_returns_the_budget_on_stream_close_error_and_queue_full` | RG `test_the_budget_is_given_back_however_a_request_ends`（串流結束、子程式斷線 502、例外）；開通的排隊與取消：PQ `test_admission_bytes_and_streams_are_given_back_however_a_request_ends` |
| 12 | `test_over_budget_request_is_refused_immediately_with_the_queue_full_style_reply` | RG `test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded`；開通：PQ `test_the_byte_budget_answers_as_the_paas_table` |
| 13 | `test_refusal_formats_for_get_batch_and_chunked` | RG `test_the_refusal_formats_for_a_get_a_batch_and_a_chunked_body` |
| 14 | `test_chunked_request_within_budget_is_forwarded_and_budget_returns` | RG `test_a_chunked_request_within_the_budget_is_forwarded_and_given_back` |
| 15 | `test_one_profile_filling_its_share_does_not_affect_another` | RG 同名（開通） |
| 16 | `test_global_budget_is_shared_by_all_profiles` | RG `test_the_add_ons_budget_is_shared_by_every_profile`（開通） |
| 17 | `test_legitimate_13_mib_upload_passes_with_default_budget` | RG `test_a_legitimate_13_mib_upload_passes_with_the_default_budget`（cgroup 與 MemAvailable 兩種來源） |
| 18 | `test_flood_of_large_requests_never_holds_more_than_the_budget` | RG `test_a_flood_of_large_requests_never_holds_more_than_the_budget`（20 個 4 MiB，共用一個 body：CI 時間） |
| 19 | `test_budget_returns_after_abandoned_queue_client_disconnect_and_refusals` | RG `test_the_budget_is_given_back_however_a_request_ends`（讀到一半取消、等子程式時取消）；排隊中放棄：開通才有排隊，HM-14 的 `test_gateway_queue_ha.py` 與 PQ 已釘住，歸還由 RG 的 AnyMethod 案例涵蓋 |
| 20 | `test_proxy_wrapper_returns_the_budget_when_the_request_raises` | RG `test_the_budget_is_given_back_however_a_request_ends`（`authorize` 丟例外的一段） |

### 5.2 `test_gateway_request_structure.py`（17 個函式）

| # | PaaS | HA |
|---|---|---|
| 1 | `test_pathological_16_mib_bodies_are_refused`［lists、dicts、kv、floats、strings］ | RS 同名（另加 small-ints） |
| 2 | `test_one_big_string_has_no_structure_to_refuse` | RS 同名 |
| 3 | `test_legitimate_nextcloud_upload_of_13_3_mib_passes` | RS `test_a_legitimate_nextcloud_upload_of_13_3_mib_passes` |
| 4 | `test_legitimate_odoo_batch_create_of_thousands_of_records_passes` | RS `test_a_legitimate_odoo_batch_create_of_thousands_of_records_passes` |
| 5 | `test_legitimate_large_n8n_workflow_passes` | RS `test_a_legitimate_large_n8n_workflow_passes` |
| 6 | `test_batch_of_thousands_of_small_requests_passes` | RS `test_a_batch_of_thousands_of_small_requests_passes_the_scan`（守門放行；HA 的政策另外拒絕 batch，403，與守門無關） |
| 7 | `test_brackets_and_commas_inside_strings_do_not_count` | RS 同名 |
| 8 | `test_depth_boundary` | RS `test_the_depth_boundary` |
| 9 | `test_element_boundary_counts_commas_and_containers` | RS `test_the_element_boundary_counts_commas_and_containers` |
| 10 | `test_scanning_cost_is_bounded_by_the_limit_not_the_body_size` | RS `test_the_scan_costs_what_the_limit_allows_not_what_the_body_holds` |
| 11 | `test_mcp_request_limits_check_structure_error_has_no_content` | RS `test_an_n8n_limits_refusal_carries_no_content` |
| 12 | `test_default_structure_limits_are_installed_by_create_app` | RS `test_every_product_but_n8n_gets_the_default_structure_limits`、`test_the_default_limits_are_the_paas_ones`；RG `test_every_products_runtime_reads_under_the_budget_and_the_guard`［8 個產品］ |
| 13 | `test_pathological_body_is_refused_before_any_forward`［mcp、messages/ × lists、kv］ | RS `test_a_pathological_body_is_refused_before_anything_is_forwarded`［lists、kv］；`messages/` **不適用**：HA 沒有 legacy SSE（契約 §9 #6） |
| 14 | `test_too_deep_body_is_refused_and_the_message_has_no_content` | RS `test_a_too_deep_body_is_refused_and_the_message_has_no_content` |
| 15 | `test_batch_without_a_recoverable_id_is_refused_with_413` | RS `test_a_body_without_a_recoverable_id_is_refused_with_413` |
| 16 | `test_legitimate_large_calls_still_forward` | RS `test_legitimate_large_calls_still_forward`（另加中文與 emoji 原樣轉送） |
| 17 | `test_non_json_and_non_post_behave_as_before` | RS `test_not_json_and_bodiless_requests_answer_as_before`（HA 不是 JSON 照今天 400；PaaS 轉送：§9 #104） |

### 5.3 `test_gateway_budget_defaults.py`（7 個函式）

| # | PaaS | HA |
|---|---|---|
| 1 | `test_one_gib_pod_keeps_at_least_200_mib_of_headroom_in_the_sandbox_worst_cases`［3］ | RB `test_a_one_gib_ceiling_keeps_the_sandbox_headroom`［3］（同一組沙盒數字；HA 的 1 GiB 指 cgroup 或 MemAvailable−256） |
| 2 | `test_old_defaults_would_have_failed_the_sandbox_scenarios` | RB `test_the_old_paas_defaults_would_have_failed_the_sandbox_scenarios` |
| 3 | `test_more_accounts_or_heavier_children_shrink_the_budget` | RB 同名；帳號數依開關：`test_switched_off_counts_one_account_and_switched_on_the_products_capacity` |
| 4 | `test_formula_matches_the_documented_arithmetic` | RB 同名 |
| 5 | `test_small_pod_is_clamped_to_the_single_request_ceiling` | RB `test_a_small_ceiling_is_clamped_to_the_single_request_ceiling` |
| 6 | `test_environment_variables_still_win` | **不適用**：HA 不讀環境變數（§9 #101）；RB `test_the_add_on_reads_no_environment_variable` |
| 7 | `test_amplification_covers_the_measured_worst_case_under_the_structure_guard` | RB `test_the_amplification_covers_the_measured_worst_cases` |

### 5.4 `test_gateway_budget_round2.py`（10 個函式）

| # | PaaS | HA |
|---|---|---|
| 1 | `test_budget_is_built_at_app_creation_and_invalid_env_warns_on_stdout_and_logs_page` | RG `test_the_budget_is_made_with_the_apps`（建在 `make_apps`／`ProfileManager`，啟動時）；環境變數的 WARNING **不適用**（不讀環境變數） |
| 2 | `test_request_budget_logger_has_a_stdout_handler` | **不適用**：HA 沒有 Logs 頁，WARNING 經 Python 的 lastResort 進 add-on log（HM-08 以來的 `profile_router` 相同）；logger 名稱由 RB `test_refusal_reports_are_throttled_per_profile_with_a_suppressed_count` 釘住 |
| 3 | `test_invalid_idle_env_warns_without_echoing_the_value` | **不適用**（不讀環境變數） |
| 4 | `test_idle_registered_connection_is_dropped_and_returns_the_budget` | RG `test_an_idle_upload_is_dropped_with_408_and_its_bytes_given_back` |
| 5 | `test_slow_but_steady_upload_is_not_cut_off` | RG `test_a_slow_but_steady_upload_is_not_cut_off` |
| 6 | `test_small_requests_are_not_subject_to_the_idle_timeout_and_budget` | RG `test_small_requests_are_neither_charged_nor_cut_off_when_idle` |
| 7 | `test_legacy_sse_messages_refusal_is_503_not_200` | **不適用**：HA 沒有 legacy SSE（§9 #6） |
| 8 | `test_client_disconnect_while_draining_a_refused_request_is_not_an_error` | RG `test_a_client_leaving_while_its_refused_body_is_drained_is_no_error` |
| 9 | `test_refusal_report_is_throttled_per_profile_with_a_suppressed_count` | RB `test_refusal_reports_are_throttled_per_profile_with_a_suppressed_count`；PQ `test_busy_warnings_are_one_line_per_profile_and_situation_a_minute` |
| 10 | `test_chunked_request_refused_mid_stream_still_gets_its_id_back` | RG 同名 |

### 5.5 `test_gateway_budget_round3.py`（30 個函式）

| # | PaaS | HA |
|---|---|---|
| 1 | `test_utf16_and_utf32_bodies_are_refused`［6×3］ | RS 同名［6×3］ |
| 2 | `test_bom_prefixed_bodies_are_refused`［4］ | RS 同名［4］ |
| 3 | `test_nul_in_the_first_four_bytes_is_refused_like_json_detect_encoding` | RS `test_a_nul_in_the_first_four_bytes_is_refused_as_json_detect_encoding_reads_it` |
| 4 | `test_bytes_that_are_not_valid_utf8_are_refused` | RS 同名 |
| 5 | `test_valid_utf8_with_cjk_and_emoji_passes`［6］ | RS `test_valid_utf8_with_chinese_and_emoji_passes`［6］ |
| 6 | `test_empty_and_plain_ascii_bodies_are_unchanged` | RS 同名 |
| 7 | `test_large_valid_utf8_bodies_pass_quickly_and_without_copying_the_whole_body` | RS `test_large_strings_of_chinese_and_emoji_pass_quickly`［3］ |
| 8 | `test_a_multibyte_character_split_by_the_chunk_boundary_is_not_misjudged` | RS `test_a_multibyte_character_split_by_a_check_block_is_not_misjudged` |
| 9 | `test_mcp_request_limits_refusal_for_utf16_has_no_content_and_the_usual_format` | RS `test_an_encoding_refusal_says_so_and_a_structure_refusal_says_that`（前半） |
| 10 | `test_utf16_refusal_message_is_about_encoding_not_structure` | 同上（後半；另驗結構拒收認得出 id 就 200） |
| 11 | `test_closing_bracket_flood_does_not_stall_the_scan`［4］ | RS `test_a_closing_bracket_flood_does_not_stall_the_scan`［4］ |
| 12 | `test_scan_time_does_not_grow_with_body_size` | RS `test_the_scan_time_does_not_grow_with_the_body` |
| 13 | `test_closers_hidden_after_balanced_structure_are_bounded_too` | RS `test_closers_after_balanced_structure_are_bounded_too` |
| 14 | `test_closers_never_exceed_the_work_bound_for_valid_nesting` | RS `test_valid_nesting_never_passes_the_work_bound` |
| 15 | `test_amplification_covers_the_measured_astral_worst_case` | RB `test_the_amplification_covers_the_measured_worst_cases` |
| 16 | `test_python_str_really_is_four_bytes_per_character_with_one_astral_character` | RB 同名 |
| 17 | `test_two_gib_pod_cannot_be_oom_killed_by_astral_requests_that_fit_the_budget` | RB `test_a_two_gib_ceiling_cannot_be_oom_killed_by_astral_requests_that_fit` |
| 18 | `test_one_gib_production_default_is_unchanged_at_the_single_request_floor` | RB `test_a_one_gib_ceiling_is_at_the_single_request_floor_for_every_switched_on_product` |
| 19 | `test_astral_request_is_charged_and_refused_under_a_small_budget` | RB `test_an_astral_request_is_charged_and_refused_under_a_small_budget` |
| 20 | `test_plain_ascii_big_string_is_still_accepted_by_the_structure_guard` | RS `test_a_plain_ascii_big_string_is_still_accepted` |
| 21 | `test_escaped_quote_does_not_end_the_string` | RS `test_an_escaped_quote_does_not_end_the_string` |
| 22 | `test_escaped_backslash_before_a_quote_does_end_the_string` | RS `test_an_escaped_backslash_before_a_quote_does_end_the_string` |
| 23 | `test_string_ending_with_backslash_pairs_and_quotes_in_the_slow_path` | RS `test_backslash_pairs_and_quotes_in_the_slow_path` |
| 24 | `test_element_boundary_is_exactly_the_limit_on_the_fast_path` | RS `test_the_element_boundary_is_exactly_the_limit_on_the_fast_path` |
| 25 | `test_element_boundary_is_exactly_the_limit_on_the_slow_path` | RS `test_the_element_boundary_is_exactly_the_limit_on_the_slow_path` |
| 26 | `test_utf16_pathological_body_is_refused_and_json_loads_is_never_called` | RS `test_utf16_bodies_are_refused_and_never_parsed`（把閘道的 `strict_json` 換成一呼叫就失敗的替身） |
| 27 | `test_valid_utf8_cjk_and_emoji_is_forwarded_and_parsed` | RS `test_legitimate_large_calls_still_forward`（第三個 body，子程式收到的參數逐字相同） |
| 28 | `test_structure_refusals_log_one_throttled_warning_per_profile` | RS `test_structure_refusals_log_one_throttled_warning_per_profile_and_kind` |
| 29 | `test_total_upload_deadline_env_is_validated` | **不適用**：不讀環境變數；整體期限是 HA 既有的 `BODY_SECONDS` 60 秒（§9 #102） |
| 30 | `test_a_trickling_upload_is_dropped_at_the_total_deadline_even_if_it_never_goes_idle` | RG `test_a_trickling_upload_ends_at_the_whole_read_limit_as_before`（HA：60 秒、今天的 408 形狀） |

合計 84 個函式（參數化的算一案）：78 個有 HA 對應（其中 5.2 #13 的 `messages/` 與 5.4 #1 的環境變數 WARNING 兩部分不適用），6 個整案不適用
（環境變數 4：5.1 #3、5.3 #6、5.4 #3、5.5 #29；stdout handler 1：5.4 #2；legacy SSE 1：5.4 #7）。PaaS 9 個產品的 `test_request_structure_guard.py` 對到 RG
`test_every_products_runtime_reads_under_the_budget_and_the_guard`［8 個上架產品］與 RS `test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`；
k8s 不適用（HA 沒有這個產品）。

### 5.6 HA 自己的測試（PaaS 沒有對應）

轉送的大小也扣（RB `test_the_forwarded_size_is_charged_when_it_is_larger`、RG `test_the_forwarded_size_is_charged_and_a_body_that_does_not_fit_as_forwarded_is_not_sent`、
PQ 的 SSE 三案）；份額上限 64 MiB（RB `test_each_profiles_share_is_capped_at_its_quota`）；MemAvailable 來源（RB）；開關與帳號數（RB）；頭尾找 id（RB 11 案）；
文字（RB）；不合理的限制（RB）；放大語料的解析成本（RS 5 案）；MF-2 (b)（`test_carries_no_request.py` 3 案、PQ 2 案）；n8n 先跑守門（RS 2 案）；
開關關時 add-on 自己的預算（RB、RG）；8 個產品的正式 runtime（RG 8 案）。

## 6. 守門有效的證據

### 6.1 先紅後綠

測試先寫（`a6c8e80`，實作在 `e3694cc`）。新模組在測試執行時才 import，所以每案各自失敗。先紅用 repo 外的迷你執行器
（`SP:hm31/dev/minirun.py`：逐案呼叫、提供 tmp_path／monkeypatch／log_scan 與模組裡的 fixture；不是 pytest，因為共用 pytest 鎖排了 1 小時以上）
在 `351666f` 的程式（`git stash` 只暫存 `packages/`）上跑；之後的綠用正式 pytest（第 9 節）。

| 檔 | 先紅（`351666f` 的程式） | 紅的原因 |
|---|---|---|
| RB | 42 案：41 失敗、1 通過 | 沒有 `request_budget` 模組；通過的是 PEP 393 的事實案（`test_python_str_really_is_four_bytes_per_character_with_one_astral_character`） |
| RS | 82 案：80 失敗、2 通過 | 沒有結構守門；通過的兩案釘的是今天就成立、本片要保留的行為（合法大呼叫照常轉送、不是 JSON 照今天 400） |
| RG | 17 案全失敗。之後加的 8 個產品案（`8c99fc1`）另在 repo 外的暫存樹跑（HEAD 的測試＋`351666f` 的 `packages/`）：8 案全失敗 | 沒有 `request_budget` 模組。8 個產品的行為另用同一組請求的探針看（探針不 commit）：在 `351666f` 上，7 個產品把 70 層深與 UTF-16 的 body 整個解析完，再由政策回 403；n8n 回自己的 413（id null）與 400 `-32700`。現在都在解析前拒絕（200＋`-32602` id 7；413）。「子程式沒收到」在 `351666f` 上也成立（政策擋下），所以紅的依據是回應，不是子程式 |
| PQ | 16 案：10 失敗、6 通過 | `ProfileGate` 沒有 `budget_share`、`ProfileManager` 沒有 `budget`、准入滿時通知 503；通過的是轉送名額、串流上限、client、WARNING 節流、開關關 |
| `test_carries_no_request.py` | 62 案：3 失敗 | 准入滿時通知 503（HM-14 現況）、沒有 `beyond` |
| `test_gateway_busy_shapes.py` | 7 案：3 失敗 | `ProfileGate` 的第三個參數要預算（沒有 `request_budget`） |
| `test_n8n_request_bounds.py` | 62 案：2 失敗 | 沒有 `too_complex`（深度一案的新期望值） |
| `test_profile_routing.py` | 23 案：2 失敗 | `ProfileManager` 沒有 `budget` |

綠：迷你執行器在實作後同樣這些檔全過（RB 42、RS 82、RG 25、PQ 16、62、7、62、22＋1 個迷你執行器不支援 `capsys` 的案），正式 pytest 見第 9 節。

### 6.2 臨時突變

每個突變只改正式程式的一處，用迷你執行器跑指定的測試檔，記第一個失敗的測試；跑完用 `git checkout` 還原並以 SHA-256 核對（`SP:hm31/mutate/mutate.py`），
最後 `git status` 乾淨。20 個全部擋下：

| # | 突變 | 擋下的第一個測試 |
|---|---|---|
| B01 | 宣告的長度讀之前不扣 | RG `test_the_refusal_formats_for_a_get_a_batch_and_a_chunked_body` |
| B02 | 小請求也扣（`SMALL_REQUEST_BYTES` 0） | RB `test_small_requests_are_never_charged_or_refused` |
| B03 | 轉送的大小不扣 | RG `test_the_forwarded_size_is_charged_and_a_body_that_does_not_fit_as_forwarded_is_not_sent` |
| B04 | 請求結束不歸還（`AnyMethod` 的 finally 拿掉） | RG `test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded` |
| B05 | 大請求不登記（不看閒置、不邊讀邊扣） | RG `test_the_refusal_formats_for_a_get_a_batch_and_a_chunked_body` |
| B06 | MCP 路徑不跑結構守門 | RS `test_a_pathological_body_is_refused_before_anything_is_forwarded` |
| B07 | 接受 UTF-16／32 | RS `test_utf16_and_utf32_bodies_are_refused` |
| B08 | 閉括號灌水不停 | RS `test_a_closing_bracket_flood_does_not_stall_the_scan` |
| B09 | 份額不受帳號的位元組額度限制 | RB `test_each_profiles_share_is_capped_at_its_quota` |
| B10 | 放不下的宣告 body 不讀完就回答 | RG `test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded` |
| B11 | 准入滿時通知照樣拒絕 | `test_the_reserve_is_reached_even_once_the_profiles_admission_is_full` |
| B12 | 不看全 add-on 的預算 | RG `test_the_add_ons_budget_is_shared_by_every_profile` |
| B13 | MemAvailable 不減保留量 | RB `test_without_a_cgroup_limit_memavailable_less_the_reserve_is_the_ceiling` |
| B14 | 頭尾找不到 id | RG `test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded` |
| B15 | 閒置時安靜結束（不回 408） | RG `test_an_idle_upload_is_dropped_with_408_and_its_bytes_given_back` |
| B16 | n8n 不跑結構守門 | RS `test_an_encoding_refusal_says_so_and_a_structure_refusal_says_that` |
| B17 | 准入滿時什麼都不讀（HM-14 的現況） | `test_the_reserve_is_reached_even_once_the_profiles_admission_is_full` |
| B18 | 超過單筆上限仍扣著 | RB `test_requests_over_the_single_request_cap_are_not_held` |
| B19 | 開通時只算一個帳號 | RB `test_switched_off_counts_one_account_and_switched_on_the_products_capacity` |
| B20 | 元素上限差一（慢路徑 `>=`） | RS `test_the_element_boundary_is_exactly_the_limit_on_the_slow_path` |

## 7. HM-01 契約凍結與黃金回歸逐案核對（契約第 1.2 節）

結論：**沒有一案的回應改變，凍結檔與黃金回歸的斷言都沒改**。理由：每一案的 body 都 ≤64 KiB（initialize、tools/list、通知、server/discover、
`{`、空、未知通知、被拒的 tools/call），不登記預算、不受閒置逾時，結構與編碼都在上限內。

| 組（`tests/contract/profiles_v1_cases.json`） | 案數 | 核對 |
|---|---|---|
| connect | 2 | initialize（約 150 位元組）：不扣、守門放行，子程式收到的與今天逐位元相同 |
| error（含 order-） | 46 | 錯 token、方法、Origin、query 都在裝 `watch` 之前回答；`malformed`（`{`）守門不判違規（快速路徑），照今天 strict JSON 400；`text/plain` 照今天 415（讀之前） |
| unknown_token | 8 | 零命中：預設 app 的 404／401，在 token 檢查就回答，不碰預算 |
| header_switch | 7 | initialize：同 connect |
| cross_profile | 1 | 同 unknown_token（HM-01 時 B 不存在） |
| url_variant | 31 | 路徑比對或 token 檢查就回答；命中的同 connect |
| token_change | 4 | 輪替、撤銷後的舊 token：token 檢查回答 |

黃金回歸（`tests/test_single_profile_golden.py`，8 產品×2 狀態）與管理契約凍結：本機全過（第 9 節）。新的單帳號回應（第 8 節）由 RB、RS、RG 釘住，
沒有加進凍結檔：凍結檔是 HM-01 的守門檔（HM-08 也沒改），新回應各自有逐位元的斷言。

## 8. 單帳號行為改變（開關關，逐項；給 PR 與各產品下一版 CHANGELOG）

| # | 情況 | 以前 | 現在 | 測試 |
|---|---|---|---|---|
| 1 | 宣告的 `Content-Length` 超過 64 KiB、放不進預算 | 照常處理 | 讀完丟掉，200＋`-32003`＋`Retry-After: 5`（頭尾認得出 id）或 503 | RG `test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded` 等 |
| 2 | 沒帶 `Content-Length`，讀到一半放不進預算 | 照常處理 | 停讀，200＋`-32003`（開頭認得出 id）或 503 | RG `test_a_chunked_request_refused_mid_stream_still_gets_its_id_back` |
| 3 | 轉送的大小放不進預算（非 ASCII 內容） | 照常轉送 | 200＋`-32003`，子程式收不到 | RG `test_the_forwarded_size_is_charged_and_a_body_that_does_not_fit_as_forwarded_is_not_sent` |
| 4 | 已登記的大請求 30 秒沒有新位元組 | 等到 60 秒回 408 `{"error":"request denied"}` | 30 秒回 408＋`-32003`＋`id: null`＋`Retry-After: 5`＋`Connection: close`（整體 60 秒的回應照舊） | RG `test_an_idle_upload_is_dropped_with_408_and_its_bytes_given_back` |
| 5 | JSON 巢狀超過 64 層、元素超過 20 萬 | 照常解析（太深的 strict JSON 遞迴錯 400） | 200＋`-32602`（認得出 id）或 413 | RS、RG 8 個產品 |
| 6 | 不是 UTF-8（UTF-16／32、BOM、不合法 UTF-8） | UTF-16／32 照常解析；n8n 400＋`-32700` | 413（或 200）＋`-32602`、編碼的訊息 | RS |
| 7 | n8n 巢狀超過 64 層 | 413、`id: null`、「MCP JSON exceeds 64 levels of nesting」 | 200＋`-32602`（認得出 id）、結構的訊息 | `test_n8n_request_bounds.py`、RS |
| 8 | 上面每一種拒收與超過 16 MiB 的 413 | 沒有 log | 每情況 60 秒一行 WARNING（`MCP gateway [profile=default]: …`，不含內容或 token） | RS、RB |

上限內的請求、錯 token、其他既有回應：逐位元照舊（第 7 節）。

**各產品下一版 CHANGELOG 的句子**（英文，照各產品 CHANGELOG 的語言；`#NNN` 換成本片的 PR 號；交發版片）：

- 8 個產品共用（Odoo、n8n、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud、Headscale；Odoo Manage 已下架，有發版時同樣適用）：
  > Gateway request limits aligned with the PaaS server (PR #NNN): a request body over 64 KiB is read under a byte budget derived at startup from the container's memory limit, or from MemAvailable less 256 MiB when there is none (at least 16 MiB, at most 64 MiB for the add-on's profile). A large body the budget cannot hold is answered with JSON-RPC error -32003 and `Retry-After: 5` (HTTP 200 under its id when its head or tail shows it, else 503) instead of being processed, and one that sends nothing for 30 seconds is dropped with HTTP 408 (`-32003`, `Connection: close`); the 60-second whole-read limit and its 408 are unchanged. A JSON body nested deeper than 64 levels, with more than 200,000 elements, or not UTF-8 (UTF-16 and UTF-32 are refused) is refused before it is parsed: HTTP 200 with `-32602` under its id when its head or tail shows it, else 413. Requests within these limits are answered exactly as before; each kind of refusal writes one warning a minute.
- n8n 另加一句：
  > n8n: a body nested deeper than 64 levels now gets HTTP 200 with `-32602` under its id (it was 413 with a null id), and a body that is not UTF-8 gets the encoding refusal (it was 400 with `-32700`).

各產品的預算預設值不同（子程式估計：Odoo 100、n8n 300、其他 160 MiB）：MemAvailable 2 GiB 時全 add-on 約 Odoo 73、n8n 63、其他 70 MiB，份額約一半。

## 9. 本機檢查（2026-11-16，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排隊在共用鎖）

| 檢查 | 怎麼跑 | 結果 |
|---|---|---|
| 新與改過的測試：先紅 | 迷你執行器（`SP:hm31/dev/minirun.py`），`351666f` 的 `packages/` | 第 6.1 節：新 3 檔當時 141 案有 138 案失敗、之後的 8 個產品案 8 案失敗；改過的 5 檔 20 案失敗 |
| 新 3 檔：綠 | 迷你執行器，`bf2365f` | RB 42、RS 82、RG 25 全過（逐檔牆鐘 1、7、8 秒） |
| 改過的 5 檔：綠 | 迷你執行器，實作之後 | PQ 16、`test_carries_no_request.py` 62、`test_gateway_busy_shapes.py` 7、`test_n8n_request_bounds.py` 62 全過；`test_profile_routing.py` 22 過，另 1 案迷你執行器不支援 `capsys`（不算失敗） |
| 正式 pytest（3 檔） | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_n8n_request_bounds.py tests/test_carries_no_request.py tests/test_gateway_busy_shapes.py`（排共用鎖） | 開發期間（實作已在）131 案全過；這 3 檔與 `packages/` 之後沒再改 |
| 正式 pytest：新與改過的測試、HM-01 守門檔、全套 | `SP:hm31/bin/verify.sh`（排共用鎖） | **沒跑**：前面排了另外兩條線，這個階段結束前沒輪到，排隊的執行已停止 |
| 臨時突變 | `SP:hm31/mutate/mutate.py` | 20 個全部擋下（第 6.2 節）；還原後用 SHA-256 核對，`git status` 乾淨 |
| 迷你執行器掃全部測試檔（開發用） | `SP:hm31/bin/sweep.sh` | 掃了約 60／108 檔後停止；失敗全是迷你執行器不支援的東西（`capsys`、`caplog`、async generator fixture、參數展開），不是測試失敗 |
| `packaging/validate.py` | ci-venv 的 python | exit 0（`PASS: 8 strict Supervisor-subset manifests, …`） |
| `scripts/tool_inventory.py` | `.venv/bin/python` | exit 0，沒有漂移 |
| packaging unittest（離線暫存 venv） | — | **沒跑**（排在全套之後；本片沒動 `packaging/`） |
| 秘密預檢、帳本預檢 | 第 13 節 | 第 13 節 |

### 9.1 只在 CI 跑的測試

本片新增與改過的測試都在本機跑過（迷你執行器；正式 pytest 只跑了其中 3 檔）。全套 pytest 與 packaging unittest 這次本機沒跑，
CI 是第一次完整執行。CI（root、0 skip）才是準：

- 已知要 root、本機一定失敗的既有案例（不是本片造成；這次本機沒跑全套，名單是前幾片本機跑全套時的 7 案）：
  `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、
  `test_restore_detection.py` 的 5 個 `test_root_*`。CI 用 root 跑。
- 本片的測試在 root 下：沒有依賴 uid 或檔案權限；記憶體讀取都換成測試自己的檔或函式（不讀機器的 cgroup／MemAvailable）；開關關的
  `make_apps` 預設預算會讀 CI 機器的記憶體，但每個斷言預算的測試都把推導換掉或固定上限。
- Python：CI 3.13.16、本機 3.13.15。

### 9.2 `checks` 秒數與新測試的時間

- `checks`：開 PR 後補（前：`claude-delivery` 最近一次 PR run；後：本片 PR）。
- 新測試的本機秒數：正式 pytest 沒量到。迷你執行器逐檔的牆鐘：RB 1、RS 7、RG 8 秒，合計約 16 秒（逐案呼叫，不含 pytest 的收集與
  fixture）。CI 推估：GitHub runner 約是本機的 1.5～2 倍，新 3 檔約 25～35 秒；加上改過的 5 檔的增量，估計整片在 1.5 分鐘內
  （計畫 §10.1：每片增量 ≤1.5 分鐘）。開 PR 後用 CI 的 `--durations` 核對。
  大請求的測試用串流產生或共用一個 body，最多同時持有幾個 16 MiB 的物件；16 MiB 的結構語料一次只建一個。

## 10. 量測（本機 AMD EPYC 7713、Python 3.13.15；HM-19c 在目標硬體重量）

### 10.1 結構守門之下，閘道自己的解析成本（`strict_json`，`tracemalloc` 的高峰；守門上限內最多的元素）

| body | `{},` 10 萬個 | `[],` 10 萬個 | `{"a":1},` 10 萬個 | `1.5,` 20 萬個 | `1,` 20 萬個 |
|---|---|---|---|---|---|
| 1 MiB | 8.6 MiB（8.6 倍） | 7.8 MiB | **19.5 MiB（19.5 倍）** | 7.4 MiB | 3.2 MiB |
| 4 MiB | 14.6 MiB（3.6 倍） | 13.8 MiB | 25.5 MiB（6.4 倍） | 13.4 MiB | 9.2 MiB |
| 16 MiB | 38.6 MiB（2.4 倍） | 37.8 MiB | 49.5 MiB（3.1 倍） | 37.4 MiB | 33.2 MiB |

- 元素上限讓結構的成本有絕對上界（每個請求約 20～50 MiB），不再隨 body 變大（HM-08 量的 16 MiB `{}` 是 24 倍、約 390 MiB）。
- 但 1 MiB 左右、元素接近上限的請求，閘道一側就約 20 倍，加上子程式的解析會超過放大倍數 20 的假設；同時大量這種請求的總量由准入（開通）或
  8081 外框 64（沒開通）限住。PaaS 一樣（它只量了 16 MiB）。列為 HM-19c 要量的項目（第 11 節）。

### 10.2 掃描時間（最壞，三次取最快）

| body | 時間 |
|---|---|
| 16 MiB 閉括號灌水（`"`＋30 萬逗號＋`]`） | 34 ms |
| 16 MiB 字串相鄰（`"a""a"…`） | 31 ms |
| 20 萬元素、慢路徑 | 107 ms |
| 16 MiB `[[],[],…]`（掃到超過上限就停、拒收） | 182 ms |
| 16 MiB 單一 ASCII／中文／emoji 字串 | 17／44／45 ms |

都在事件迴圈裡同步跑（PaaS 同）；最壞約 0.2 秒。

### 10.3 預算的推導（`BudgetLimits.derive`，例子）

| MemAvailable | 沒開通的 Odoo：全 add-on／份額 | 開通的 Odoo（6 帳號） |
|---|---|---|
| 1 GiB | 22.1 MiB／16 MiB（下限） | 16 MiB（下限）／16 MiB |
| 2 GiB | 73.3 MiB／36.6 MiB | 48.3 MiB／24.1 MiB |
| 8 GiB 機器、MemAvailable 5 GiB | 226.9 MiB／64 MiB（上限） | 201.9 MiB／64 MiB（上限） |

## 11. 待 HM-19c 量測的常數（全部暫定；量測後要改就回功能 PR）

| 常數 | 值 | 來源 | HM-19c 要量 |
|---|---|---|---|
| `AMPLIFICATION` | 20 | PaaS 沙盒（閘道＋子程式最壞 17.8 倍） | HA 閘道（會重新序列化）＋各產品子程式在 J6412（可以的話 J1900）的倍數：ASCII、中文、emoji、守門上限內最壞的結構，特別是 1 MiB 左右的結構（第 10.1 節） |
| `GATEWAY_BASELINE_MIB` | 76 | PaaS 沙盒 | HA 管理程序的基線 RSS |
| `SAFETY_MARGIN_MIB` | 150 | PaaS | 尖峰餘裕 |
| `HOST_RESERVE_MIB` | 256 | 計畫 §5.2 的保留量（`PROFILE_MEMORY_RESERVE_MIB`） | 要不要改成只取 MemAvailable 的一部分（add-on 和 HA Core、其他 add-on 共用整台機器；開機那一刻的 MemAvailable 之後會變小） |
| `FALLBACK_TOTAL_BYTES` | 32 MiB | PaaS | 讀不到記憶體時的值 |
| `PER_PROFILE_FRACTION`／份額上限 | 0.5／64 MiB（DQ-07） | PaaS／DQ-07 | 6 個帳號時的份額 |
| `MIN_BUDGET_BYTES` | 16 MiB | 單筆上限（`MAX_REQUEST`） | — |
| `SMALL_REQUEST_BYTES` | 64 KiB | PaaS | — |
| `BODY_IDLE_SECONDS` | 30 秒 | PaaS | Cloudflare Tunnel 後面的上傳 |
| `DEFAULT_MAX_TOTAL_ELEMENTS`／`DEFAULT_MAX_DEPTH` | 20 萬／64 | PaaS | — |
| `profiles.CHILD_MEMORY_MIB` | Odoo 100、n8n 300、其他 160 | HM-07（PaaS） | 各產品子程式的實際 RSS |
| `REFUSAL_READ_SECONDS` | 2 秒 | HM-08（准入滿時的讀取） | — |

## 12. 本片用到的決策

| 決策 | 結論 | 本片怎麼用 |
|---|---|---|
| 2026-11-16 07:1x 使用者 | 對齊 PaaS #155、所有產品都生效（不受開關管） | 全片；`decisions.md` 第 1.1 節記下 |
| 2026-11-16 07:5x 主對話（HM-14 審查 MF-2 (b)） | 不改 DQ-07 的數值；准入滿時仍讀 ≤64 KiB 的小請求，是通知或回應就走保留名額 | 第 3.3 節；`decisions.md` 第 1.1 節記下 |
| DQ-07 (a)＋DQ-29 | 名額與記憶體規則；數值暫定、HM-19c 定案 | 數值都沒改；64 MiB 當份額的上限（§9 #98） |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 9 節；commit |
| §8.8 #45（契約第 9 節） | 程式常數、不讀部署層設定 | 不讀 PaaS 的環境變數（§9 #101） |

沒有碰到別的待定題。下面兩點是本片的判斷，請主對話確認（不是使用者定過的數值，也不是 DQ）：(1) 每帳號份額保留 DQ-07 的 64 MiB 當上限
（不改數值，只限制 PaaS 的「全域÷2」不超過它）；(2) 整體讀取上限保留 HA 既有的 60 秒與今天的 408 形狀（PaaS 300 秒、-32003），只加 PaaS 的
閒置 30 秒。要改成完全照 PaaS，兩處都是小改。

## 13. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 351666f --head HEAD --full` | `bf2365f`（本筆記之前的 6 個 commit）：`result: OK, 0 findings`。加上本筆記的 commit 後重跑的結果寫在交回主對話的回報（筆記記不到自己那個 commit） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 351666f` | `result: OK`（`runtime-patches.json` 有改；沒有未列管的新 runtime 檔） |

測試資料：沒有 commit 任何隨機 token。token 都在測試執行時產生（`configure`、`create_profile`、`ProductStore`），網址 `.invalid`；
本筆記不含 token、密碼或像金鑰的字串（帳本摘要只寫前 12 碼）。

## 14. 驗收條件（計畫 §12.3 HM-31）

| 條件 | 狀態 |
|---|---|
| 全綠 | **本機只完成一部分**：新與改過的測試全綠（迷你執行器），3 檔正式 pytest 131 案全過，20 個突變全擋，validate 與 tool_inventory 過；全套 pytest 與 packaging unittest 本機沒跑，等 CI（root、0 skip） |
| PaaS 測試逐案對照 | 通過：第 5 節（84 案：78 有對應、6 不適用並寫理由；另 9 個產品的測試對到 8 個上架產品） |
| 單帳號行為改變逐項列出（PR 與各產品下一版 CHANGELOG 句子） | 通過：第 8 節（8 項；英文句子兩段，給發版片） |
| 獨立安全審查 | **還沒做**：交主對話安排（HM-08、HM-14 都是另一個代理審，報告放 `artifacts/…/wave*/`） |
| 和 HM-08 的位元組額度整合成一套 | 通過：第 3.1 節；HM-08 的計數與拒絕小額度都拿掉 |
| 所有產品都生效、契約 §1.2 寫明例外與理由、HM-01 凍結逐案核對 | 通過：契約第 1.2 節、本筆記第 7 節 |
| 常數依記憶體推導、寫清楚來源與下限 | 通過：契約第 5 節、本筆記第 10.3、11 節 |
| MF-2 (b) 與測試 | 通過：第 3.3 節；`test_a_newly_connected_clients_initialized_reaches_the_child_with_the_queue_and_admission_full` |
| 放大倍數語料 | 通過：RS（{}、[]、浮點、小整數、短字串、中文、emoji、kv）與第 10.1 節的量測 |
| 單帳號與開通兩種模式 | 通過：RG（開關關 14＋8 產品、開關開 3）、PQ、`test_carries_no_request.py` |
| 同 PR 更新帳本、新模組列管 | 通過：第 13 節 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：第 13 節 |

## 15. 還沒解決、交給後面的片

- **獨立安全審查**（驗收條件）：建議看 (1) 扣在 token 驗過之後、`AnyMethod` 一定歸還；(2) 讀完丟掉的拒絕佔連線（開通時也佔准入）；
  (3) 准入滿時不設上限的小請求讀取；(4) MemAvailable 推導在共用機器上的上界；(5) 結構守門的掃描時間；(6) 第 12 節最後的兩個判斷。
- **rebase 到 `claude-delivery`**（HM-14 合併後；主對話做）。預期的衝突：
  - `gateway.py`：HM-09 在 `make_apps` 簽章加了 `child_blocked`，本片加 `body_budget`（同一行附近）；HM-14 本身會先合。
  - `profile_runtime.py`：HM-09 改很多；本片只改 import、`RUNTIME_OPTIONS`、`ProfileRuntime` 的參數與 `gateway_options`、`ProfileManager.__init__`
    的 `allowance`→`budget`、`add()` 兩行。
  - `profiles.py`：HM-09 加了 `memory_limit_mib`、`available_memory_mib`；本片在 `request_budget.py` 有同樣的兩個讀取函式（為了不和 HM-09 衝突）。
    rebase 後建議改用 `profiles` 的那兩個、拿掉 `request_budget` 的重複（行為相同；測試換的是 `request_budget.CGROUP_MEMORY_LIMITS`、`MEMINFO`、
    `memory_ceiling`，改用 `profiles` 時跟著改）。
  - `decisions.md`、`contract.md`、`acceptance-matrix.md`、`threat-model.md`：HM-09、HM-14 也改；本片的段落都是新增或整段改寫，照段落合併。
  - 契約第 9 節的編號：`claude-delivery` 到 #89，HM-14 加 #90～#97，本片接著加 #98～#104。HM-10、HM-20、HM-30 若也新增列，後合的要重編號；
    引用這些編號的只有文件（契約、`acceptance-matrix.md`、`decisions.md`、本筆記），測試沒有。
  - 帳本：rebase 後重產摘要、重跑兩個預檢與 CI（摘要要重算）。
  - HM-30（回覆工作執行緒）也改 `gateway.py`：誰後合誰 rebase。
- **HM-19c**：第 11 節的常數；MemAvailable 推導要不要只取一部分；1 MiB 左右最多元素的請求（閘道＋子程式）倍數。
- **HM-18**：把契約第 1.2、2.4、5 節本片的文字與威脅模型第 3 節本片加的五條寫進產品 DOCS。
- **發版片**：第 8 節的 CHANGELOG 句子。
- **repo 外**：FEATURE-MATRIX 補 FM-154；計畫 §5.2 的表格（位元組額度那一列）與 §12.3 HM-31 的「做法」可補一句「准入滿時讀小請求」；
  `paas-test-mapping.md`、`deviation-trace.md` 由產生器重產（#98～#104）。
