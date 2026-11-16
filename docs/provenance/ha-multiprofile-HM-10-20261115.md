# HA 多帳號 HM-10 provenance：管理 API（共用管線、帳號增刪改查、選帳號、索引隔離、狀態欄位）（2026-11-15）

## 結論

- **產品沒開通時，管理 API 一個位元組都不變**：8099 仍是預設帳號自己的 app，`/api/profiles*` 是未知操作（角色檢查之後空本體 404），
  PATCH、DELETE 照舊是 Starlette 的 405，帳號範圍路徑不要求、也不看 `X-MCP-Profile`。從 `admin_page`、`admin_api` 抽出的共用管線
  （`gateway.management_operation`、`management_value`、`management_exchange`）是同一段程式，HM-01 的黃金回歸與兩個契約凍結一字未改照過。
  repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開），8099 是新的管理分派器（`profile_router.AdminDispatcher`）：
  - **一條共用管線走所有路徑**（契約 §3.2）：頁面檢查 → ① identity → ② 管理名額 16 → ③ 有界讀 body → ④ 斷線監看 → ⑤ 方法表與不讀 state 的格式
    → ⑥ **第一次角色檢查** → 全域路徑交 `profile_admin.ProfileAdmin`（⑧～⑪，含**第二次角色檢查**），帳號範圍路徑先 ⑦ 選帳號、再交該帳號
    自己的動作（今天的 `admin_action`）。非管理員最遠到 ⑥：路由表自動產生的否定矩陣裡，9 種不是管理員的呼叫方 × 每條路由都是 403，
    兩輪不同的帳號狀態下位元組逐一相同，而且什麼都沒變。
  - **選帳號只看 `X-MCP-Profile`**（DQ-17；UC-10 照使用者 2026-11-15 15:3x 的決定，不做網址路徑備案）：沒帶 400 `profile_id_required`、
    兩個以上或格式錯 400 `profile_id_invalid`、索引沒有 404 `profile_not_found`、讀不到 503，絕不退回預設帳號。
  - **帳號增刪改查**：清單（每列 `status`、`blocked_reason`；另列孤兒）、建立（一次寫入最終初值，回應與重送都不含 token）、改名、刪除
    （DQ-14 的順序：撤銷並結束請求 → 抹憑證 → 停 → 移出索引 → 刪目錄 → 重評被擋的帳號）、隔離不能用的索引（DQ-12）。寫索引一律帶
    `expected=`；增刪改與隔離都要 If-Match（索引 ETag `"p1-…"`），建立、刪除、隔離另要 Idempotency-Key，收據放索引旁。
  - **容量**：第 6 個額外帳號 409 `profile_limit_reached`＋`limit`（FD 預算不夠、只服務預設帳號時 `limit` 0）；記憶體不夠 409
    `profile_memory_insufficient`＋`limit`、`required_memory_mib`、`available_memory_mib`（有 cgroup 時另帶 `memory_limit_mib`）；沒有 port 409
    `profile_port_unavailable`。
  - **子程式的鎖**：建立後在新帳號自己的 `mutation_lock` 裡起子程式；開機與索引變更後重評起子程式（`ProfileRuntime.launch()`）也拿該帳號的
    鎖（HM-09 審查 S-12 第 2 點，HM-09 的 PR 交給本片），和存檔、面板重啟不會交錯。
  - **回聲與全域設定**：每個帳號範圍的 JSON 回應帶 `profile`（bootstrap 帶整個回聲與 `profiles_supported`，預設帳號另帶
    `profile_index_state`）；endpoint 全域一個（DQ-13：額外帳號顯示預設帳號的、`PUT endpoint` 409 `endpoint_global`）；owner-defaults
    只在預設帳號（額外帳號 409 形狀 C）。
  - **帳號 ETag 綁帳號 id**（DQ-15）：HMAC domain 是 `edit:<id>`；兩個帳號的 state 逐位元相同、金鑰也相同，拿 A 的 ETag 寫 B 仍是 409。
- 新測試 2 檔 35 案（`tests/test_profile_admin_api.py` 30 案、`tests/test_admin_pipeline_matrix.py` 5 案）；改 2 個測試工具／既有測試檔。
  先寫測試：實作前（`24d72cc` 的核心程式）新 2 檔 35 案 32 失敗（通過的 3 案鎖的是沒開通與 HM-01 交下、本來就不該變的位元組），實作後全過；
  第三個工作階段補的 3 案對前一版（`537f5bc`）全紅、改完全過（第 4.1 節）。臨時突變 30 個（含第三個工作階段補的 3 個），全部被抓到（第 4.2 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest（HEAD `bc37ac7`）：5,411 案、5,404 過、7 失敗（都是本機一定失敗的
  root 案例）、0 skip，1,841.6 秒；之後只多一個測試案例（`47d03dd`），本片＋相關 9 檔 228 案重跑全過（第 5 節）。
- 契約第 3、4.1、5、7 節標「暫定／待定」而本片定下的細節都已同步，變更紀錄一列（第 3.9 節）；驗收矩陣 T-12 補上本片的刪除測試。`decisions.md` 沒改：DQ-13、DQ-14 已由 #100
  記進 `claude-delivery`，本分支沒有它，rebase 時會一起進來。
- 這個階段只 commit，不 push、不開 PR；合併前要做獨立安全審查（計畫 §12.1：HM-10 是「審查」片）。
- 工作分三個工作階段：第一個寫測試與實作（2026-11-15 21:29 撞到用量上限）；第二個補鎖與刪目錄的斷言、修全套抓到的退步、commit 4 個
  （2026-11-16 00:41 主程序結束中斷，紅的那一段跑到一半）；第三個（06:3x 起）重跑全部檢查、補 3 個缺口（開機與重評起子程式的鎖、FD 預算、
  沒有索引檔的隔離）與筆記。本筆記的數字都是第三個工作階段重新驗證的。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-10（計畫 §12.3；風險高、工作量 L；「審查」片） |
| 分支 | `feat/ha-multiprofile-hm10-20261115`（一般 clone），疊在 HM-09 的實作 head `24d72cc` 上 |
| 基準 | `claude-delivery` 的 HM-00～HM-08（HM-08 是審查前的 `cfdc487`）、HM-13a、HM-17、HM-02，加上 HM-09 的 5 個 commit（HM-09 在別的工作線審查與修正中）。`claude-delivery` 之後又合了 #99（HM-08 審查修正：`gateway.py`、`profile_router.py`、契約）與 #100（`checks` 上限 60 分鐘、`decisions.md` 記 DQ-13／14／30／31／43），本分支都沒有，rebase 時處理（第 13.3 節） |
| 依據 | 計畫 §4.3、§4.4、§5.3（全部）、§7.2 第 1、2 點、§8.5、§8.8、§10.3 的 HM-10 列、§12.0、§12.3 HM-10；契約 §1、§3、§4.1、§9；`threat-model.md`（I3、I5、I6、I10、I12）；FM-01、05、06、07、08、12、18、19、21、22、23、24、25、26、33、47、53、54、93、131、139、148；驗收矩陣 T-02、T-06、T-07、T-09、T-12；HM-00～HM-09 的 provenance 筆記交給 HM-10 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425`：`profiles.py`（`ProfileRegistry.create`／`rename`／`delete`／`list`、`ProfileCapacity`、`ProfileContextMiddleware`）、`routers/profiles.py`、`routers/tokens.py`（`set_token` 撞號，HA 沒有這個 API：§8.8 #80）、`tests/test_profiles.py`；HA 加嚴的地方都在契約第 9 節（#31～#35、#83） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/gateway.py` | 共用管線抽成模組層函式：`management_operation`（頁面檢查）、`management_value`（③）、`management_exchange`（①～④）、`management_app`、`method_not_allowed`；`JSON_OPERATIONS`、`PROFILE_OPERATIONS`（帳號範圍的路由表）。`make_apps` 的 `admin_page`、`admin_api` 改呼叫它們（行為不變）；多兩個 keyword-only 選項 `default_endpoint`（額外帳號）、`bootstrap_fields`；回聲保留動作設定的每個標頭（HM-05 審查的提醒）；`admin.state.profile_action` 給分派器 |
| `Hc/profile_router.py` | `AdminDispatcher`（開通後的 8099）、`GLOBAL_ROUTES`（全域路由表）、`global_route`、`is_global`；模組說明 |
| `Hc/profile_admin.py`（新） | `ProfileAdmin`：清單、建立、改名、刪除、索引隔離（⑧～⑪）、索引 ETag 與壞索引 ETag、容量判斷（FD 預算不夠時 `limit` 0）、bootstrap 欄位、⑦ 的額外帳號解析；沒有索引檔時不隔離；`Registry`：本模組用到的 `ProfileManager` 介面全部集中在這裡（建立後在新帳號自己的 `mutation_lock` 裡起子程式） |
| `Hc/profile_runtime.py` | `ProfileManager`：建 `ProfileAdmin` 與 `AdminDispatcher`（`admin_app` 改成分派器）、每帳號的回聲（`echo`、`relabel`）、bootstrap 欄位、額外帳號的 `default_endpoint`、`files_for_extras`（開啟時 FD 上限夠不夠額外帳號用）；`ProfileRuntime`：`ConfigurationState` 帶帳號 id、收 `default_endpoint`／`bootstrap_fields`、`admin_action`（`make_apps` 放在 admin app 的 `state`；測試替身的 admin app 沒有時是 `None`，只有開通的分派器會呼叫它）、`launch()` 拿該帳號的 `mutation_lock`（HM-09 審查 S-12 第 2 點） |
| `Hc/configuration.py` | `ConfigurationState(profile_id=…)`：revision 的 HMAC domain 帶帳號 id（`edit:<id>`、`launch:<id>`） |
| `Hc/operations.py` | `OperationJournal(results=, subjects=)`；`PROFILE_RESULTS`（`profile.create`、`profile.delete`、`profile.index_quarantine`）、`SUBJECT`。帳號自己的收據檔格式不變 |
| `Hc/profiles.py` | `free_index_quarantine_name`（同一秒加 `-2`…）、`move_index_aside`、`index_bytes`、`remove_profile_directory`（從 `O_NOFOLLOW` 開、驗過擁有者的 `profiles/` 目錄 fd 往下刪） |
| `tests/test_profile_admin_api.py`（新，28 個測試函式、30 案） | 契約第 3 節的情況（第 6 節對照表） |
| `tests/test_admin_pipeline_matrix.py`（新，4 個測試函式、5 案） | 路由表與 `admin_action` 的對照；否定矩陣；分派器路由每條路由；HM-01 交下的固定回應（開與關） |
| `tests/multi_profile_runtime.py` | HM-08 的測試工具：`Runtime.admin(profile_id)` 改成面板的客戶端（開通時經 8099 分派器、每個請求帶 `X-MCP-Profile`；沒開通照舊）；可指定 `verifier` |
| `tests/test_router_passthrough.py` | HM-08 的開通後重跑 HM-01 三組測試：管理客戶端帶 `X-MCP-Profile: default`、把回聲拿掉再比位元組（`Unechoed`；PATCH／DELETE 補 CSRF，因為開通後方法表在 identity 之後）；8099 是分派器的斷言 |
| `docs/multi-profile/contract.md` | 第 3.1～3.7、4.1、5、7 節、第 9 節 #27、第 10 節一列（第 3.9 節） |
| `docs/multi-profile/acceptance-matrix.md` | T-12 的測試欄補 `tests/test_profile_admin_api.py`（刪除那一半） |
| `docs/provenance/runtime-patches.json` | 6 個列管檔重算摘要並補說明；新列 `profile_admin.py`；第三個工作階段改了 `profile_runtime.py`、`profile_admin.py`，照實際內容再算一次 |
| 本筆記 | — |

沒改：`run_product.py`（8099 照舊掛 `profile.admin_app`，開通時那就是分派器）、`admin_auth.py`、`products.py`、`config.py`、`lifecycle.py`、
`health.py`、`apps/`、`packaging/`、`packages/mcp-admin-ui/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`
（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、workflow、`tests/conftest.py`、HM-01 的守門測試檔、`decisions.md`、`tests/contract/profiles_v1_cases.json`。

## 3. 設計重點

### 3.1 分派器（計畫 §5.3；契約 §3.1、§3.2）

- 帳號是在第一次角色檢查（⑥）之後才選的，所以入口不能是任何一個帳號的 app。分派器自己跑共用管線，⑦ 選好帳號後直接呼叫該帳號的動作
  （`ProfileRuntime.admin_action`＝`make_apps` 的 `profile_action`：`admin_action`＋回聲）。HM-05 開的 `admin_pipeline` 注入點沒有用到
  （它在某個帳號的 app 裡才被呼叫，那時帳號已經選了）；保留給「一個帳號的 app 帶自己的管線」的用法，HM-05 的測試照舊。
- 頁面與靜態檔交預設帳號的動作（照今天：拿鎖、角色檢查、回檔案），開通後多一次角色檢查（計畫 §7.2 第 2 點）。
- 路由表：`gateway.PROFILE_OPERATIONS`（帳號範圍）＋`profile_router.GLOBAL_ROUTES`（全域）。全域路徑是 `profiles` 與 `profiles/` 底下：
  `profiles`（GET 清單、POST 建立）、`profiles/index/quarantine`（POST）、`profiles/{id}`（PATCH 改名、DELETE 刪除），其他 `profiles/…`
  是未知操作（⑥ 之後空本體 404，不看標頭）。HM-13c 的全部撤銷、還原紀錄、核對、刪隔離目錄之後加進 `GLOBAL_ROUTES`，矩陣自動涵蓋。
- 方法表（⑤）：PATCH、DELETE 只在 `profiles/{id}`；其他路徑回 405，位元組同今天 Starlette 的（純文字、`Allow` 列該路徑的方法）。
  全域路徑表外的方法也 405。頁面的 PUT、POST 照今天 404，PATCH、DELETE 照今天 405，都在頁面檢查（identity 之後）就回。
  差別只有順序：沒開通時 405 在 identity 之前（路由層），開通後在 identity 之後（契約 §3.1 寫好的）。所以 HM-01 管理契約凍結的 405 案例
  （沒帶 CSRF 的 DELETE）開通重跑時，測試客戶端要補 CSRF（`Unechoed`）。
- ⑤ 的格式檢查：全域路徑的本體剛好 `{"label": <字串>}`、路徑的 `<id>` 是 `default` 或 24 位小寫 hex，錯了固定 400。帳號範圍路徑的本體
  驗證照今天在該帳號的動作裡（⑨），非管理員在 ⑥ 就 403，連格式錯都看不到。

### 3.2 選帳號（契約 §3.3；DQ-17；DQ-40 (a) ①；§8.8 #31、#32、#83；I12）

- `request.headers.getlist('x-mcp-profile')`：0 個 400 `profile_id_required`；多於 1 個或不符 `default|[0-9a-f]{24}` 400
  `profile_id_invalid`（大寫 hex、`Default`、逗號串起來的兩個值、隔離目錄名都算）；`default` 就是預設帳號。
- 額外帳號：索引不能用 503 `profile_index_corrupt`；索引沒有（孤兒、已刪除、隔離目錄的 id、任何其他）404 `profile_not_found`；索引有但
  沒有登錄（讀不到）503 `{"error":"state unavailable"}`；目錄已不是開啟時那一個（HM-07 審查 S-08 的管理面：每次比一次目錄的
  `(st_dev, st_ino)`，`Credentials.refresh`）也 503。這些都在 ⑥ 之後。
- UC-10：照使用者 2026-11-15 15:3x 的決定用標頭，不做 `{base}/api/p/<id>/…` 備案；`/api/p/<id>/bootstrap` 只是未知的帳號範圍操作
  （要標頭、⑥ 之後 404，有測試）。Ingress 會不會原樣轉這個標頭與 PATCH／DELETE 待 HM-03a 實測（第 11 節）。

### 3.3 清單與狀態欄位（契約 §3.6；FM-18、FM-26、FM-139；DQ-19）

- 預設帳號第一列（`label` `Default`、`port` 是預設子程式的 port），之後照索引順序；每列鍵的順序照 PaaS 再加 `status`、`blocked_reason`。
- `disabled_reason` 用 `ProfileManager` 手上的（HM-09 依 PaaS 順序算的：產品上限 → 記憶體 → port）；索引有、沒登錄的帳號是 HA 的
  `profile_unavailable`（狀態 `failed`）。
- `status` 從 `Supervisor.status` 對應：`stopped`（還沒輪到起，或重起的中間）算 `starting`，其他同名；`blocked_reason` 只在 `blocked` 時有值
  （`profile_limit` 被擋時是 `null`，HM-09 的定案照用）。`/health/ready` 不變（DQ-19）。
- 另列 `orphans`：`profiles/` 底下有、索引沒有的帳號目錄（DQ-14：不自動刪、列出可刪）。
- 清單是讀取，不拿鎖；⑥、⑩ 兩次角色檢查之後同步組好回答。

### 3.4 建立（計畫 §4.3；DQ-02、DQ-16、DQ-28；FM-19、20、21、25）

- ⑪ 的順序：If-Match（缺 428、多個或格式錯 409）→ Idempotency-Key（缺 428、多個 400；已完成就照收據重送，回目前那一列，帳號已刪就只回 id；
  沒完成 409 `operation_outcome_unknown`）→ ETag 不符 409 → 名稱規則 422 → 產品不開放 409 → 上限 409 → 記憶體 409 → 名稱衝突 409 → 沒有 port 409。
  容量與衝突的先後照 PaaS `ProfileRegistry.create`。
- 記憶體：有 cgroup 上限時照 PaaS 公式；沒有時看 MemAvailable 夠不夠再起一個子程式（每子程式 MiB＋256，同 HM-09 起子程式的規則），
  讀不到就照建立並記一行 WARNING（不假設夠）。
- port：`ProfileManager.free_port()`（18000～18099，避開 3000、8081、8099、索引與執行中子程式的 port、試綁失敗的）。
- 寫入：新 id（避開索引、目錄、隔離目錄的 id）→ `profile_initial_state(預設帳號當下的 state, taken=所有 token 與 child token)` → 收據 begin →
  `ensure_profiles_directory` → `ProductStore(create=…)`（目錄原本不存在、lock `O_EXCL`、一次寫入）→ `write_index(expected=手上的索引)`
  ＝提交（`committed`）→ adopt → `ProfileManager.add` → `reevaluate` → 在新帳號自己的 `mutation_lock` 裡 `start_profile`（記憶體檢查照 HM-09）
  → 收據 complete → 201。⑩ 之後到提交之間不 await，斷線取消不到中間；提交後的步驟不被取消。
- 為什麼在新帳號的鎖裡起（HM-09 審查 S-12 第 2 點；HM-09 的 PR 把它交給 HM-10 接線時做）：寫完索引，清單就看得到新 id；這時面板若
  馬上對新帳號送 `child/restart` 或存後端，`admin_action` 會在這把鎖裡重起子程式。建立這邊不拿鎖的話，兩邊的 `stop`／`start` 可能交錯，
  最後跑的是舊 state 的子程式。現在兩邊互相等。
- 開機的錯開啟動（`start_all`）與索引變更後的重評（`reevaluate()`）起子程式走 `ProfileRuntime.launch()`：本片讓它也拿該帳號的
  `mutation_lock`（第三個工作階段補的；HM-09 審查 S-12 第 2 點的另一半，原本寫成交還 HM-09，但 HM-09 的 PR 已寫明交給 HM-10）。存檔或面板
  重啟正在重起那個帳號時，`launch()` 等它做完；刪除與建立之後的 `reevaluate()` 因此可能多等一下（已提交，照樣做完）。不會互鎖：`launch()`
  只在沒拿任何帳號鎖的地方被呼叫（開機、建立時拿新帳號的鎖之前、刪除放開目標帳號的鎖之後、隔離），`admin_action` 拿著鎖時也不會等
  `ProfileAdmin` 的鎖。沒開通的產品在 listener 起來之前呼叫，沒有人搶這把鎖，行為不變。A
  `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`（突變 M28）。
- FD 預算（HM-08）：開啟時 FD 上限提不到額外帳號要的量，add-on 只服務預設帳號（索引裡的帳號列成 `profile_unavailable`）。這時建立回
  409 `profile_limit_reached`、`limit` 0，什麼都不寫：不然新帳號會被登錄、繞過 FD 預算，重啟後卻又不服務。代碼用既有的上限代碼（`limit`
  是「現在能服務幾個額外帳號」），沒有新增代碼。A `test_no_profile_is_created_while_only_the_default_profile_is_served`（突變 M29）。
- 寫索引失敗：關 store、刪剛建的目錄（它從沒被路由過、token 沒給過任何人），用手上的索引複查（被外改就維持 503，DQ-12），409
  `operation_outcome_unknown`。登錄失敗（runtime 開不起來）：帳號留在索引、列成 `profile_unavailable`，可以刪。
- 回應與重送都不含 token；新帳號的 token 只能經 `token/reveal`＋`X-MCP-Profile: <新 id>` 拿（計畫 §4.3）。

### 3.5 改名與刪除（契約 §3.1、§3.6；DQ-14；FM-22、FM-23、FM-33；T-09、T-12）

- 改名：If-Match → 預設帳號 422 → 不存在 404 → 名稱規則 422 → 名稱衝突（不算自己）409 → 寫索引 → adopt → 回聲的名稱立刻換（`relabel`）。
  token、port、目錄都不變。不要 Idempotency-Key。
- 刪除：先拿全 add-on 的帳號鎖，再拿目標帳號的 `mutation_lock`（各最多 2 秒），⑩ → If-Match → Idempotency-Key → 預設帳號 422 →
  不在索引也不是孤兒 404 → 收據 begin →
  1. 撤銷 token（`change_token(None, 'revoke')`）＋`TokenAccess.committed()`：帶著它的請求立刻結束（有測試：B 的呼叫 401，預設帳號同時在跑的
     呼叫照常拿到結果）；
  2. 抹掉後端欄位（`connection`、`backend_url`、`backend_key`、`mcp_access_token`）；
  3. `ProfileManager.remove`：不再路由、停監看與子程式、關 client 與 store；
  4. 從索引移除（`write_index(expected=…)`），這時 port 才空出來；
  5. 刪目錄：先用 `O_NOFOLLOW` 開 `profiles/`、確認是本 uid 的目錄（和 `scan_profiles` 同一條規則），再從這個目錄 fd 往下用 `shutil.rmtree`
     的 descriptor 走法（`dir_fd=`），不跟隨任何連結；帳號自己的名稱是連結、或 `profiles/` 被換成連結都不刪（HM-07 審查 S-08 的管理面：
     不從路徑走）。刪不乾淨記一行 WARNING（id 前 8 碼），剩下的是孤兒；
  6. 重算孤兒的遮罩值、`reevaluate()`：被這個 port 或上限擋住的帳號立刻起（修 PaaS B-17）；
  7. 收據 complete → 200 `{"deleted","operation"}`。
  計畫 §4.4 把「關 store 與 client」排在移出索引之後；`ProfileManager.remove()` 一次做完 3，所以 HA 放在 4 之前。寫索引若失敗，那個帳號
  留在索引裡、已撤銷已抹除、不再服務，再刪一次即可（契約 §3.6 寫明）。
- 刪除途中才進來、在等 B 的鎖的請求（例如存 B 的設定）：刪除放開 B 的鎖時 B 的 store 已關（`Store.load()` 在關掉之後一律
  `ConfigError`），所以那個請求拿到鎖就 503 `{"error":"state unavailable"}`，什麼都不寫、不會替已刪的帳號再起子程式；它帶的 If-Match
  也是抹除之前算的，本來就會 409。A `test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing` 有兩種：目錄刪掉了（`removed`），
  與刪不乾淨、留下孤兒（`left as an orphan`：一行 WARNING 只有 id 前 8 碼、清單列成孤兒、state 停在撤銷並抹除後的位元組）。第三個工作階段
  重跑突變才發現：目錄刪掉時，在等的請求要等刪除做完才輪到，那時 `state.json` 已經不在，不管 store 關了沒都是 503，所以突變 M27
  （`remove()` 不關 store）在 `removed` 那種抓不到（第二個工作階段的筆記寫成這個測試抓得到，這次重跑不成立）；`left as an orphan` 那種
  目錄還在，store 沒關就會讀到抹除後的 state、回 409，所以補了這一種（`47d03dd`，突變 M27 被它抓到）。
- 孤兒與讀不到的帳號：沒有登錄，用 `existing_only` 開它的 store 撤銷、抹除（開不了就略過：讀不到的 state 本來就不會被路由），讀不到的帳號
  另從索引移除，再刪目錄。
- 「產品清理」（PaaS 的 `profile_deleted` 回呼）：目前沒有要做的（n8n 在 HM-25 才上 `ProfileManager`；它的 `/tmp` nodes.db 到時加）。

### 3.6 索引隔離（DQ-12；FM-131；契約 §3.6）

- 索引不能用（壞掉或被外改）時，預設帳號的 bootstrap 帶 `profile_index_state:"corrupt"` 與 `profile_index_etag`（這個程序的金鑰對索引檔的
  lstat 簽章與原始位元組算的 HMAC）。`POST profiles/index/quarantine` 要這個 ETag 與 Idempotency-Key；索引能用時一律 409 `config_conflict`。
- 做法：選一個沒人用的隔離名 → 列出 `profiles/` 底下的帳號目錄（列不出來就 503，不留收據）→ 收據 begin → 撤銷這些帳號目錄與每個
  已登錄額外帳號的 token → 提交 → `profiles.json` 改名成
  `profiles.json.quarantine-<UTC>`（同一秒有了就加 `-2`、`-3`…，不覆蓋：HM-07 審查 S-15；在帳號鎖裡選名稱）→ 重新讀索引（absent）→
  adopt：8081 立刻恢復服務預設帳號，不用重啟 → 已登錄的額外帳號停掉、不再路由 → 再撤銷一次（萬一有已經在等鎖的 token 變更寫了新 token）
  → 孤兒遮罩值、reevaluate → 收據 complete → 200 `{"quarantined":"<檔名>","operation"}`。帳號目錄都變孤兒，可以逐一刪。
- 沒有索引檔可隔離（第三個工作階段補的）：開機時 `profiles/` 列不出來（不是目錄、是連結或別的 uid 的）也算索引不能用（HM-08 的
  `unusable`，到重啟為止）。這時索引檔可能根本不存在；原本會先撤銷、寫收據，改名時才失敗（409 `operation_outcome_unknown`、收據停在未完成）。
  現在 ETag 對了之後先看索引檔在不在，不在就 409 `config_conflict`，什麼都不撤銷、不留收據；修好 `profiles/` 之後要重啟 add-on（隔離解決
  不了，契約 §3.6 寫明）。A `test_there_is_nothing_to_quarantine_without_an_index_file`（突變 M30）。

### 3.7 寫入保護（契約 §3.5；DQ-15；§8.8 #34；FM-06、07、24）

- 帳號 ETag：`ConfigurationState(profile_id=…)` 的 domain `edit:<id>`、`launch:<id>`。`ProfileRuntime` 建的每個帳號都帶，沒開通時的預設帳號
  也是：ETag 是這個程序的隨機金鑰算的，本來就不跨程序、不能預測，用戶端看到的沒有差別（HM-01 的測試都在同一個程序裡比）。
  n8n（`apps/n8n/run.py`）到 HM-25 前不帶。HM-05 審查 S-3 的對照案例：兩個帳號 state 逐位元相同、金鑰也強制相同，ETag 仍不同、拿 B 的
  ETag 寫 C 是 409；不帶 id 時同一把金鑰同一份 state 是同一個 ETag（證明測試分得出來）。
- 索引 ETag：這個程序的隨機金鑰對「每一筆（id、名稱、port）照順序」算的 HMAC。
- 索引旁的收據：格式同帳號自己的收據，另多 `subject`（帳號 id 或改名後的檔名；都不是秘密），重送才回得出做了什麼。帳號自己的收據檔
  （`results=RESULTS`、沒有 `subject`）位元組不變。

### 3.8 回聲與全域設定（契約 §3.4；DQ-13；DQ-40 (a) ②；FM-08、FM-12）

- 回聲（HM-05 的暫定照用、本片定案）：只加在帳號動作自己回的 JSON 物件，都在它最後一次角色檢查之後；以例外拒絕的回應與分派器自己的
  回應不帶。HM-05 審查的三個提醒：`echoed()` 只處理 `JSONResponse`（照舊：頁面、空本體不加）；同名多值標頭被 dict 合併（改成保留原始
  標頭順序與重複）；`profile_view()` 丟例外會 500（`ProfileManager.echo` 讀自己的名稱表，帳號刪掉後也留著，不會丟例外）。
- bootstrap：`profiles_supported` 是產品有沒有額外帳號（OpenDesign、Odoo Manage 是 `false`，DQ-28）；預設帳號另帶 `profile_index_state`。
- endpoint（DQ-13）：只存在預設 state；額外帳號的 bootstrap 顯示預設帳號的，`PUT endpoint` 在 If-Match 之後 409 `endpoint_global`、什麼都不寫。
- owner-defaults（FM-08）：額外帳號的 restore／dismiss 在 If-Match 之後 409 形狀 C，不管目錄裡有什麼；bootstrap 也不給它通知。

### 3.9 計畫沒寫死、本片定的做法（契約已同步，第 10 節一列）

1. 分派器的結構與共用管線的抽法（第 3.1 節）；HM-05 的注入點不用。
2. 405 的位元組與位置、`profiles/` 底下未知路徑、頁面的 PATCH／DELETE（第 3.1 節）。
3. ⑤ 只檢查全域路徑的本體與 id；帳號範圍的格式驗證照今天在 ⑨（第 3.1 節）。
4. ⑪ 的順序（第 3.4、3.5 節）；鎖的範圍與「清單不拿鎖」。
5. 清單的 `orphans`、`status` 的對應、`profile_unavailable`（第 3.3 節）。
6. 建立重送的回應、刪除與隔離的回應本體、壞索引的 ETag 與 `profile_index_etag`、索引 ETag 的算法、收據的 `subject`、提交後失敗的處理。
7. 記憶體不足的兩種算法與欄位（第 3.4 節）；`profile_port_unavailable` 的範圍是 18000～18099。
8. 帳號 ETag 的 domain 在每個 `ProfileRuntime` 都帶（第 3.7 節）。
9. 回聲的範圍與標頭、`profiles_supported`、額外帳號的 endpoint 與 owner-defaults（第 3.8 節）。
10. 建立後在新帳號自己的鎖裡起子程式（第 3.4 節）；刪目錄從驗過的 `profiles/` 目錄 fd 往下走（第 3.5 節）。
11. 開機與重評起子程式（`launch()`）也拿該帳號的鎖（第 3.4 節；契約 §3.2、§7）。
12. FD 預算不夠時建立回 409 `profile_limit_reached`、`limit` 0（第 3.4 節；契約 §3.2、§4.1、§5）。
13. 沒有索引檔可隔離時 409 `config_conflict`（第 3.6 節；契約 §3.2、§3.6、§4.1）。

## 4. 守門有效的證據

### 4.1 先紅後綠

- 做法：本片的測試（新 2 檔與改過的 `tests/multi_profile_runtime.py`、`tests/test_router_passthrough.py`，都是 HEAD 的版本）對 `24d72cc`
  的核心程式跑：`git archive 24d72cc packages/mcp-admin-core` 解到暫存區（另放一份建好的 UI，`ui.UI_ROOT` 才找得到；`apps` 指回 clone），
  用 `pytest -o "pythonpath=<那份核心> apps/n8n"` 換掉 `pyproject.toml` 的路徑；失敗的 traceback 都指向暫存區那份核心，證明換到了
  （`SP:hm10/batch3.sh` 第二段）。
- 紅（`24d72cc` 的核心，2026-11-16 08:37 最後一次重跑，測試是 `47d03dd` 的）：3 檔 84 案，**57 失敗**、27 通過。新 2 檔 35 案 32 失敗
  （`profile_admin` 不存在、分派器不存在、8099 還是預設帳號的 app）；通過的 3 案是 A 的「沒開通時照舊」與 M 的「固定回應開與關逐位元相同」
  兩案（後兩案鎖的是 HM-01 交下、本來就該不變的位元組，實作前後都要過）。`test_router_passthrough.py` 49 案 25 失敗（開通後經分派器重跑
  HM-01 三組）、24 通過（沒開通的案例與 HM-08 的 8081 案例，本片沒改它們的期望值）。07:03 在 `bc37ac7` 的測試上跑的那次是 83 案 56 失敗，
  差的一案就是 `47d03dd` 補的 `left as an orphan`。
- 綠（`47d03dd`）：同樣 3 檔 84 案全過；連同改到的測試工具會用到的 6 檔（`test_role_lifecycle.py`、`test_product_runtime_failure.py`、
  `test_profile_runtime.py`、`test_profile_routing.py`、`test_reply_mask_union.py`、`test_profile_quotas.py`）共 228 案全過，62.9 秒
  （`bc37ac7` 時 227 案，62.4 秒）。
- 第三個工作階段補的 3 案（`eec12f7`）也是先寫測試：對前一版的核心（`537f5bc`）3 案全紅，原因各是「C 在存檔還拿著鎖時就起了」
  （`running`，不是 `blocked`）、「FD 不夠也建立成功」（201）、「沒有索引檔也去隔離」（409 `operation_outcome_unknown`、留下未完成的收據）；
  改完（`ae590e8`）3 案全過（`SP:hm10/logs/s3-new-red.log`、`s3-new-green.log`）。
- 第二個工作階段補的斷言（建立在新帳號自己的鎖裡起子程式、刪目錄不跟隨連結）也是先寫測試：對還沒改的程式（就是突變 M24、M26 還原的
  那兩段）跑會紅，見第 4.2 節。
- 前一個工作階段的全套 pytest 在 `profile_runtime.ProfileRuntime.open()` 用 `self.admin_app.state.profile_action` 時抓到 26 個既有案例變紅
  （`tests/test_role_lifecycle.py` 24 案、`tests/test_product_runtime_failure.py` 2 案：它們把 `make_apps` 換成回傳純 ASGI 函式的替身）。
  改成讀不到就是 `None`（只有開通的分派器會呼叫它），兩檔全過（上面的綠）。這是全套 pytest 才抓得到的退步，第 5 節的全套已含。

### 4.2 臨時突變

`SP:hm10/mutate.py`：每個突變是核心套件的一份拷貝（在暫存區，工作樹不動）改一處，用 `SP:hm10/minirun.py`（在同一個程序裡直接呼叫測試函式；
沒有 conftest 的網路守門，只拿來量測試抓不抓得到）跑本片 2 檔＋`test_router_passthrough.py`。整批在共用測試鎖（`wave1-pytest.lock`）裡跑，
和別的工作線的 pytest 不重疊。M00 是沒改的拷貝（全過）。

2026-11-16 07:34～07:43 在 HEAD `bc37ac7` 的核心上重跑全部 30 個（第一、二個工作階段的 M01～M27，加第三個工作階段的 M28～M30）：
**30 個全部被抓到**（每個都至少一案失敗），M00 全過，574 秒。M27 在這一輪只被 A `test_another_profiles_etag_…` 抓到（store 沒關、鎖檔不放，關掉 runtime 之後再開那個帳號的 store 就失敗），原本寫的 `test_a_save_waiting_…` 抓不到（第 3.5 節）；補了 `left as an orphan` 那種（`47d03dd`）之後 08:37 重跑 M00 與 M27：M00 全過，M27 兩個測試都抓到（minirun 單看：`removed` 過、`left as an orphan` 失敗；`SP:hm10/logs/mutations-session3-m27.json`）。下表 M27 那列是重跑後的。

| id | 檔 | 突變 | 抓到它的測試 |
|---|---|---|---|
| M01 | `profile_router.py` | 拿掉第一次角色檢查（⑥） | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change`、M `test_every_route_refuses_every_caller_who_is_not_an_administrator` |
| M02 | `profile_router.py` | 沒帶 `X-MCP-Profile` 退回預設帳號 | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| M03 | `profile_router.py` | PaaS 的做法：兩個標頭取第一個、格式錯回 404 | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| M04 | `profile_admin.py` | 全域路徑拿掉第二次角色檢查（⑩） | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change` |
| M05 | `configuration.py` | ETag 的 domain 不帶帳號 id | A `test_another_profiles_etag_is_a_conflict_even_for_the_same_state` |
| M06 | `profile_admin.py` | 建立的回應帶 token | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token` |
| M07 | `profile_admin.py` | 刪除不先撤銷 token | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile` |
| M08 | `profile_admin.py` | 刪除後不重評被擋的帳號 | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile`、A `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock` |
| M09 | `profile_admin.py` | 刪除不抹憑證 | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile` |
| M10 | `profile_admin.py` | 什麼都不撤銷（刪除、隔離） | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile`、A `test_quarantining_an_unusable_index_serves_the_default_profile_again` |
| M11 | `profile_admin.py` | 建立不看 MemAvailable | A `test_a_creation_is_refused_for_its_label_its_capacity_and_its_port` |
| M12 | `profile_admin.py` | 建立不擋名稱衝突 | A `test_a_creation_is_refused_for_its_label_its_capacity_and_its_port` |
| M13 | `gateway.py` | bootstrap 不帶 `bootstrap_fields` | A `test_a_product_without_profiles_refuses_to_create_one`、A `test_every_answer_of_a_profile_names_it`、A `test_quarantining_an_unusable_index_serves_the_default_profile_again`、A `test_there_is_nothing_to_quarantine_without_an_index_file` |
| M14 | `gateway.py` | 額外帳號可以存 endpoint | A `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles` |
| M15 | `profile_admin.py` | 同一個 key 重送又建一個 | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token` |
| M16 | `profile_router.py` | `profiles/` 底下未知路徑交給帳號 | M `test_the_dispatcher_routes_every_route_of_its_table` |
| M17 | `gateway.py` | 管理名額滿了改成等待 | M `test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte` |
| M18 | `profile_admin.py` | 改名不要 If-Match | A `test_every_profile_write_needs_the_index_etag_and_its_operation_id` |
| M19 | `profile_router.py` | PATCH、DELETE 進到帳號的動作（沒有 405） | M `test_the_dispatcher_routes_every_route_of_its_table`、P `test_switched_on_the_management_contract_freeze_holds` |
| M20 | `profile_admin.py` | 索引不能用時額外帳號照常服務 | A `test_quarantining_an_unusable_index_serves_the_default_profile_again` |
| M21 | `gateway.py` | 回聲丟掉動作的標頭（ETag、Cache-Control） | P `test_switched_on_the_management_contract_freeze_holds` |
| M22 | `profile_admin.py` | 索引隔離不撤銷也不停任何帳號 | A `test_quarantining_an_unusable_index_serves_the_default_profile_again` |
| M23 | `profile_router.py` | 未知的帳號 id 退回預設帳號 | A `test_a_profile_scoped_request_names_exactly_one_known_profile`、A `test_a_profiles_actions_restart_and_show_only_its_own_child`、A `test_quarantining_an_unusable_index_serves_the_default_profile_again` |
| M24 | `profile_admin.py` | 建立後不在新帳號自己的鎖裡起子程式 | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token` |
| M25 | `profile_runtime.py` | `remove()` 不停被刪帳號的監看（HM-09 審查 R17） | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile` |
| M26 | `profiles.py` | 刪目錄改回從帳號路徑走（第一版）：`profiles/` 是連結時會跟過去 | A `test_a_profile_directory_is_removed_without_following_a_link` |
| M27 | `profile_runtime.py` | `remove()` 不關被刪帳號的 store（在等鎖的請求會讀到它） | A `test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing`（`left as an orphan`）、A `test_another_profiles_etag_is_a_conflict_even_for_the_same_state` |
| M28 | `profile_runtime.py` | `launch()`（開機與重評起子程式）不拿帳號的鎖 | A `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock` |
| M29 | `profile_admin.py` | FD 上限不夠額外帳號也照建立 | A `test_no_profile_is_created_while_only_the_default_profile_is_served` |
| M30 | `profile_admin.py` | 沒有索引檔也去隔離（撤銷、寫收據之後才失敗） | A `test_there_is_nothing_to_quarantine_without_an_index_file` |

結果檔：`SP:hm10/logs/mutations-session3.json`（`SP:` ＝ 這條工作線的暫存區 `scratchpad/`；第一個工作階段的 23 個另存
`mutations-session1.json`，結果相同）。

## 5. 本機檢查（2026-11-15～16，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

環境：clone 先跑 `setup_repo_env.sh`（`npm ci` 會清掉 Playwright 的瀏覽器，所以另照 CI 跑 `npm run browser:install --prefix packages/mcp-admin-ui`）；
每次測試前 `. bin/ha_env.sh`；pytest 一律排在 `SP:wave1-pytest.lock` 後面（`flock`）。2026-11-16 00:41 那次因主程序結束中斷（紅的那一段跑到
一半、exit 137），這裡的結果都是 2026-11-16 06:3x 之後重跑的。

| 檢查 | 指令（摘要） | 結果 |
|---|---|---|
| 全套 pytest（第一次，第二個工作階段，還沒 commit 的工作樹） | `SP:hm10/run_pytest.sh full-2 tests -q -rfE --junitxml=…` | 5,406 案：5,373 過、33 失敗、0 skip，1,921 秒。33 個裡 7 個是本機一定失敗的 root 案例（第 7 節），26 個是本片的退步（`ProfileRuntime.open()`，第 4.1 節），已修 |
| 全套 pytest（最後，HEAD `bc37ac7`） | `SP:hm10/batch3.sh` 第三段：`.venv/bin/python -m pytest -q -p no:cacheprovider -rfE tests --junitxml=…` | **5,411 案：5,404 過、7 失敗、0 skip**，1,841.6 秒（30 分 41 秒）。7 個失敗正是第 7 節那 7 個本機一定失敗的 root 案例；2 個 warning 是既有的 `websockets` 棄用提示 |
| 本片＋相關 9 檔 | `SP:hm10/batch3.sh` 第一段；補 `left as an orphan` 之後 `SP:hm10/quick2.sh` 再跑一次 | `bc37ac7`：227 案全過，62.4 秒；`47d03dd`：228 案全過，62.9 秒 |
| 本片＋HM-01、HM-08、HM-09 相關 19 檔 | `SP:hm10/run_pytest.sh s3-related …`（改完 `launch()` 之後、commit 之前） | 396 案全過，90.1 秒（含 HM-09 的 `test_profile_lifecycle.py`、`test_staggered_start.py`、`test_profile_ports.py`、`test_health_backoff.py`、`test_extra_child_resources.py`，與 HM-01 的黃金回歸、兩個契約凍結） |
| 先紅後綠 | `SP:hm10/batch3.sh`、`quick2.sh` 第二段（第 4.1 節） | 紅：`24d72cc` 的核心 84 案 57 失敗、27 通過；綠：全過 |
| 臨時突變 | `SP:hm10/batch3.sh` 第四段、`quick2.sh` 第三段（第 4.2 節） | 30 個全部被抓到、M00 全過（574 秒）；M27 補測試後重跑也被抓到 |
| `packaging/validate.py` | `SP:ha-baseline/ci-venv/bin/python packaging/validate.py` | PASS（exit 0） |
| packaging unittest | 照 CI：暫存 venv（`UV_PROJECT_ENVIRONMENT=$TMPDIR/pkg-venv uv sync --frozen --no-dev --offline`＋`uv pip install --offline --require-hashes -r packaging/requirements-ci.txt`）→ `python -m unittest discover -s packaging -p 'test_*.py'` | `Ran 201`、`OK (skipped=5)`（同 HM-09；GHCR 那幾行是測試替身印的，沒有連網） |
| tool-surface 漂移 | `.venv/bin/python scripts/tool_inventory.py` | exit 0（本片沒動 `apps/runtime/*.py`、`apps/*/launch.py`） |
| 跑完後的工作樹 | `git status --short` | 只有還沒 commit 的本筆記（測試沒有留下任何檔） |

## 6. 契約第 3 節逐條對到的測試

`A` ＝ `tests/test_profile_admin_api.py`，`M` ＝ `tests/test_admin_pipeline_matrix.py`，`P` ＝ `tests/test_router_passthrough.py`（HM-08 的開通重跑
HM-01 三組）。

| 契約 | 內容 | 測試 |
|---|---|---|
| §3.1 全域 `GET profiles` | 清單、列的欄位、孤兒、ETag、不看標頭 | A `test_the_list_names_every_profile_with_its_state_and_no_secret`、`test_a_profile_over_the_memory_limit_is_listed_with_what_it_needs` |
| §3.1 `POST profiles` | 201 該列、不含 token、重送 200 同列、收據放索引旁 | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token`；拒絕：`test_a_creation_is_refused_for_its_label_its_capacity_and_its_port`、`test_a_product_without_profiles_refuses_to_create_one` |
| §3.1 `PATCH profiles/<id>` | 改名 200 該列；422／404／409；400 格式；GET 405 | A `test_a_rename_changes_only_the_label` |
| §3.1 `DELETE profiles/<id>` | 刪除（含孤兒、讀不到的）、200＋收據、重送同 | A `test_a_deletion_revokes_stops_unindexes_and_removes_the_profile`、`test_an_orphan_and_an_unavailable_profile_can_be_deleted`、`test_deleting_a_profile_under_load_ends_only_its_own_requests` |
| §3.1 `POST profiles/index/quarantine` | 壞索引的 ETag、隔離、索引能用 409、重送 | A `test_quarantining_an_unusable_index_serves_the_default_profile_again`（corrupt、replaced）、`test_a_second_quarantine_in_the_same_second_gets_its_own_name` |
| §3.1 全部撤銷、還原紀錄、核對、刪隔離目錄 | HM-13c 的路由 | 還沒有路由；加進 `GLOBAL_ROUTES` 時 M 的矩陣自動涵蓋 |
| §3.1 頁面與靜態檔 | 照今天；PATCH／DELETE 405 | M `test_the_dispatcher_routes_every_route_of_its_table`；A `test_a_profile_scoped_request_names_exactly_one_known_profile`（頁面不看標頭） |
| §3.1 帳號範圍 `bootstrap`、`configuration`、`capabilities` | 回聲 | A `test_every_answer_of_a_profile_names_it`；M `test_the_dispatcher_routes_every_route_of_its_table` |
| §3.1 `diagnostics` | 只回選定帳號的 | A `test_a_profiles_actions_restart_and_show_only_its_own_child` |
| §3.1 `operations/<id>` | 收據依帳號 | A `test_a_profiles_actions_restart_and_show_only_its_own_child`（B 的收據在 B 的目錄）；HM-05 `tests/test_profile_runtime.py::test_each_profile_keeps_its_own_receipts` |
| §3.1 `backend`、`backend/patch` | Odoo 換身分換 token | HM-12（還沒做） |
| §3.1 `backend/test` | 測選定帳號 | HM-08 `tests/test_reply_mask_union.py::test_the_management_answers_carry_no_token_either`（經分派器） |
| §3.1 `policy` 等、`child/restart` | 只重啟選定帳號；`blocked_reason` | A `test_a_profiles_actions_restart_and_show_only_its_own_child`（經分派器：B 的 `child/restart` 與存寫入開關各重起 B 一次、預設帳號不動、過期 If-Match 與未知帳號什麼都不重起）；HM-05 `test_a_save_restarts_only_its_own_child`；HM-09 `tests/test_profile_ports.py` |
| §3.1 `endpoint`、`owner-defaults/*` | 額外帳號 409 | A `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles` |
| §3.1 `token/reveal`、`token/revoke`、`token/rotate` | 只動選定帳號；`restore_review_required` | A `test_every_answer_of_a_profile_names_it`（reveal）；HM-08 `tests/test_profile_routing.py`（經分派器輪替、撤銷）；`restore_review_required` 是 HM-13c |
| §3.1 方法 | PATCH、DELETE 只在 `profiles/<id>`；405 位元組 | M `test_the_dispatcher_routes_every_route_of_its_table`；P `test_switched_on_the_management_contract_freeze_holds`；沒開通：A `test_switched_off_the_profile_paths_are_unknown_and_no_header_is_needed` |
| §3.1 query、`%`、`\\` | 400 | P（HM-01 管理契約凍結開通重跑） |
| §3.2 ①～⑥ | 每條路由 × 9 種非管理員 → 403、沒有任何變化 | M `test_every_route_refuses_every_caller_who_is_not_an_administrator` |
| §3.2 ②③④ 的固定回應 | 503（名額、鎖、state）、408、413、斷線 403，開與關同位元組 | M `test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte`（兩種） |
| §3.2 ⑤ | 全域路徑的本體與 id 固定 400 | A `test_a_rename_changes_only_the_label` |
| §3.2 ⑦ | 見 §3.3 | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| §3.2 ⑧ | 帳號鎖、目標帳號的鎖各 2 秒 503；建立後在新帳號的鎖裡起；開機與重評起子程式也拿帳號的鎖 | A `test_a_deletion_waits_for_the_profiles_lock_and_the_add_ons`、`test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token`、`test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`；M 固定回應（帳號鎖 503） |
| §3.2 ⑨ | 依 state 驗證照今天 | P（「400 a value that does not validate」） |
| §3.2 ⑩ | 第二次角色檢查在每個等待之後、提交之前 | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change` |
| §3.2 ⑪ | 寫入保護與狀態相依判斷（含 FD 預算不夠時的上限 `limit` 0、沒有索引檔的隔離） | A `test_every_profile_write_needs_the_index_etag_and_its_operation_id`、建立／改名／刪除各案、`test_no_profile_is_created_while_only_the_default_profile_is_served`、`test_there_is_nothing_to_quarantine_without_an_index_file` |
| §3.2 非管理員逐位元相同 | 標籤有沒有、上限到沒、帳號有沒有、標頭有沒有 | M `test_every_route_refuses_every_caller_who_is_not_an_administrator`（兩輪 × 5 種變化） |
| §3.2 沒開通順序同今天；開通後只多一次角色查詢 | — | HM-01 三組（沒開通，一字未改）；P（開通重跑） |
| §3.2 新路由沒進矩陣就失敗 | — | M `test_the_route_table_has_every_operation_a_profile_answers` |
| §3.3 每一列 | 沒帶、兩個、格式錯、不存在、讀不到、索引壞、全域路徑、沒開通、8081 | A `test_a_profile_scoped_request_names_exactly_one_known_profile`、`test_quarantining_…`（索引壞 503）、`test_switched_off_…`；8081：HM-08 `tests/test_profile_routing.py`（契約案例的 `X-MCP-Profile` 不理） |
| §3.4 | bootstrap 整個回聲與 `profiles_supported`；其他 `profile:{id}`；拒絕不帶；改名立刻換；標頭保留 | A `test_every_answer_of_a_profile_names_it`、`test_a_product_without_profiles_refuses_to_create_one`（`false`）；P（形狀 B 的 ETag 標頭） |
| §3.5 帳號設定 | domain 帶 id、逐位元相同的對照 | A `test_another_profiles_etag_is_a_conflict_even_for_the_same_state` |
| §3.5 增刪改、隔離 | If-Match、Idempotency-Key、各錯誤代碼、重送、提交後失敗 | A `test_every_profile_write_needs_the_index_etag_and_its_operation_id`、`test_an_operation_whose_outcome_is_unknown_is_never_repeated`、`test_the_index_etag_is_bound_to_the_entries_and_this_process` |
| §3.5 建立與重送不回 token | — | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token` |
| §3.6 清單列、`orphans` | — | A `test_the_list_…`、`test_a_profile_over_the_memory_limit_…`、`test_an_orphan_and_an_unavailable_profile_can_be_deleted` |
| §3.6 bootstrap 欄位 | `profile_index_state`、`profile_index_etag` | A `test_every_answer_…`、`test_quarantining_…` |
| §3.6 請求本體與名稱規則 | 剛好 `{"label"}`；DQ-16 | A `test_a_creation_is_refused_…`、`test_a_rename_changes_only_the_label` |
| §3.6 還原紀錄 | HM-13b／c | — |
| §3.6 索引隔離、刪除的步驟 | 含：監看停了、預設 state 沒被寫、刪目錄不跟隨連結、刪除途中在等鎖的請求什麼都不做、刪不乾淨時一行 WARNING（只有 id 前 8 碼）且剩下的是孤兒、`profiles/` 列不出來又沒有索引檔時不隔離 | A `test_quarantining_…`、`test_a_deletion_revokes_…`、`test_deleting_a_profile_under_load_…`、`test_a_profile_directory_is_removed_without_following_a_link`、`test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing`（`removed`、`left as an orphan`）、`test_there_is_nothing_to_quarantine_without_an_index_file` |
| §3.7 | 不做路徑備案（UC-10） | A `test_a_profile_scoped_request_names_exactly_one_known_profile`（`/api/p/<id>/bootstrap` 404） |
| §1.2 沒開通 | `/api/profiles*` 404、不要求標頭 | A `test_switched_off_the_profile_paths_are_unknown_and_no_header_is_needed` |

第 4.1 節本片負責的代碼：`profile_id_required`、`profile_id_invalid`、`profile_not_found`、`profile_label_invalid`、`profile_default_immutable`、
`profile_label_conflict`、`profile_limit_reached`、`profile_memory_insufficient`、`profile_port_unavailable`、`profile_product_unsupported`、
`endpoint_global`、`profile_index_corrupt`、`config_conflict`、`config_revision_required`、`operation_id_required`、`operation_id_invalid`、
`operation_id_expired`、`operation_id_conflict`、`operation_not_found`、`operation_outcome_unknown`、`owner_defaults_unavailable` 都在 A 的案例裡
各有斷言；`operation_journal_full`、`operation_journal_unavailable` 是今天的收據程式（沒改它的上限與讀寫），沒有另寫案例。

計畫 §10.3 的 HM-10 列還寫了「`tests/contract/profiles_v1_cases.json`（擴充）」：沒有擴充。那個檔是 HM-01 的守門檔，格式只描述 8081
（原始 HTTP 請求打真 listener）；管理面的案例由路由表自動產生（M），比靜態檔多涵蓋「新路由沒進表就失敗」；和 PaaS 不同的地方
（§8.8 #31、#32、#34、#35、#83）各有斷言（A），PaaS 行為當突變跑過（M03、M18）。HM-08 也沒有改它（見 HM-08 筆記第 14.1 節）。
要不要在 HM-18 定稿時把管理面案例也寫成資料檔，交 HM-18 決定。

### 6.1 PaaS 對照案例（`paas-test-mapping.md` 指給 HM-10 的 13 列）

| PaaS 測試（@69ac425） | HA 測試 | HA 的期望值 |
|---|---|---|
| `apps/nextcloud/tests/test_main.py::test_unauthenticated_put_does_not_restart` | M `test_every_route_refuses_every_caller_who_is_not_an_administrator` | 非管理員 403；子程式（狀態、啟動次數）、索引、目錄、收據都沒變 |
| `apps/nextcloud/tests/test_main.py::test_stale_policy_update_does_not_restart` | A `test_a_profiles_actions_restart_and_show_only_its_own_child` | 過期 If-Match 409 `config_conflict`、子程式不重起（Odoo 存檔會重起的是寫入開關，所以用它） |
| `apps/nextcloud/tests/test_main.py::test_unknown_profile_does_not_restart` | 同上；A `test_a_profile_scoped_request_names_exactly_one_known_profile` | 未知帳號 404 `profile_not_found`、絕不退回預設帳號、什麼都不重起 |
| `packages/mcp-admin-core/tests/test_auth.py::test_protected_api_requires_token`、`test_bearer_token_grants_access`、`test_invalid_token_rejected` | M 否定矩陣 | HA 沒有管理 token：不是 Ingress 來源、沒有或兩個 `X-Remote-User-Id`、不是管理員一律 403（§8.8 #11） |
| `test_auth.py::test_mcp_token_rotation_keeps_current_admin_session_and_revoked_session_denied` | M 否定矩陣（「an MCP token instead」） | MCP token 不能當管理憑證 |
| `test_logs_profile_buffers.py::test_stream_endpoint_serves_only_the_selected_profile`、`test_logs_router.py::test_search_and_sse_keep_profile_logs_separate` | A `test_a_profiles_actions_restart_and_show_only_its_own_child` | 診斷只回選定帳號的子程式輸出（§8.8 #29） |
| `test_origin_root_path.py::test_root_path_never_bypasses_admin_authentication` | M 否定矩陣（頁面 `/`、`/overview`） | 頁面也先驗管理員；Core 未審時是 403 的 HTML 頁 |
| `test_profile_robustness.py::test_create_refused_for_memory_says_so_and_how_much_is_needed` | A `test_a_creation_is_refused_for_its_label_its_capacity_and_its_port` | 409 `profile_memory_insufficient`＋`limit`、`required_memory_mib`（有 cgroup 時照 PaaS 公式）；HA 另帶 `available_memory_mib`（§8.8 #19），不帶 `message` |
| `test_profile_robustness.py::test_memory_disabled_profile_is_listed_with_its_reason_and_logged_when_not_started` | A `test_a_profile_over_the_memory_limit_is_listed_with_what_it_needs` | 清單 `disabled_reason:"memory_capacity"`＋`required_memory_mib`；HA 另帶 `status:"blocked"`、`blocked_reason:"memory_capacity"` |
| `test_initialize_stop_recovery.py::test_profile_b_restart_completes_while_profile_a_drains` | A `test_a_profiles_actions_restart_and_show_only_its_own_child` | 預設帳號的呼叫還在等子程式時，B 的重啟與存檔就完成；之後預設帳號的呼叫照常拿到結果 |

## 7. 只在 CI 跑的測試與 `checks` 秒數

- 本片新增與改過的案例沒有一個要 root、也沒有條件式 skip，本機全部跑過；CI（root、0 skip）跑同樣的案例。
- 本機一定失敗、只在 CI（root）才會過的既有案例有 7 個，都和本片無關（HM-09 審查報告也列了其中 6 個）：
  `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（HM-07：uid 10001 的 mode／owner 證明，非 root 時刻意失敗）、
  `tests/test_restore_detection.py` 的 5 個 `test_root_*`（HM-13a）。
- 新測試的時間：新 2 檔 34 案本機 9.9 秒（`test_profile_admin_api.py` 29 案 3.3 秒、`test_admin_pipeline_matrix.py` 5 案 6.6 秒，最慢的是固定回應兩案各 2.4 秒與否定矩陣 1.7 秒）；改過的 `test_router_passthrough.py` 49 案 5.4 秒（HM-08 的檔，開通重跑多了帶標頭、拿掉回聲）。CI 推估新 2 檔 10～15 秒（runner 比本機慢、而且會跳）；全套本機 1,841.6 秒。全部在程序內（ASGI、`NoProcessSupervisor`、MockTransport），不起真子程式。等待都用事件或 `asyncio.timeout` 上限；只有兩處是
  「等 0.2～0.3 秒、確認某件事沒發生」（刪除途中只斷 B 的呼叫、開機與重評起子程式要等帳號的鎖）：runner 慢只會讓它們少抓到錯，不會讓對的程式
  失敗。
- `checks` 秒數：前＝#100 合併時 1,899 秒（31 分 39 秒；上限已是 60 分鐘；README 進度紀錄）；本片：開 PR 後補。

## 8. 預檢結果

兩個都在 commit 本筆記之後、對 HEAD 跑（2026-11-16）：

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 24d72cc --head HEAD --full` | gitleaks 8.28.0（釘版、已驗）；`24d72cc..HEAD` 11 個 commit，另掃 HEAD 樹與全部歷史：**0 命中**（`result: OK, 0 findings`） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 24d72cc` | `runtime-patches.json` 173 筆、`runtime-sources.json` 70 筆、`tool-surface.json` 159 筆，0 漂移、0 缺；改到的 7 個列管檔都在帳本（含新的 `profile_admin.py`）；沒有沒列管的新執行檔：**OK** |

## 9. PaaS 變動（`git log 69ac425..cf3d0d5 -- <相關檔>`，本機唯讀 PaaS repo）

| 範圍 | 結果 | 對本片 |
|---|---|---|
| `profiles.py`、`routers/profiles.py`、`routers/tokens.py`、`routers/settings.py`、`operations.py`、`app.py`、`config/store.py`（`69ac425..cf3d0d5`） | 0 個 commit（`git diff --stat 69ac425 cf3d0d5` 對這些檔也是空的） | 期望值不變 |
| 核心模組（`git diff --stat 69ac425 cf3d0d5 -- packages/mcp-admin-core/mcp_admin_core/`） | 只動 `log_redaction.py`（#149，HM-02 已收）、`gateway_pool.py`／`proxy.py` 的註解（#150）、`setup_status.py` 的說明文字（VK 移除 `8bfb12e`） | 沒影響 |
| 本機 PaaS repo 的 `origin/main` 已被別的工作線更新（2026-11-16 再看是 `d7f5849`；本片沒有 fetch、沒有 checkout） | `cf3d0d5..5b84b5d`（#152～#154）核心模組 0 變動；只動 `apps/nextcloud`（`0f43fd3` 存檔過 SSRF 檢查、`0f94aa4` 換使用者或網址撤銷 token、`4f1a77f` 遮罩保留 args）、`apps/emqx`（#153 實測小修）與 `docs/paas-config-restore-runbook.md` 一行 | 沒影響（Nextcloud 是 HM-20、HM-22 的事；EMQX 是 HM-23） |
| `5b84b5d..d7f5849`（#155 閘道請求內容位元組預算） | 核心動了 `profiles.py`（只把 `ProfileRegistry.capacity()` 的算法抽成 `current_profile_capacity()`，行為不變）、`app.py`（啟動時建預算、結構守門）、`proxy.py`、`request_budget.py`（新）、`request_limits.py`、`request_body.py`、`gateway_pool.py`：都是 8081 的請求位元組預算與 JSON 結構守門 | 帳號管理的期望值不變。8081 的預算是 HM-08／HM-14 那一側的事（HA 已有 HM-08 的每帳號位元組額度）：要不要對照 #155 交主對話判斷 |
| 本片引用的 PaaS 測試名稱 | `git grep "def <名稱>" 69ac425` 逐一核對過都存在（第 6.1 節那 13 個；2026-11-16 重查一次） | — |

## 10. 本片用到的決策

| 題 | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-02 (a) | 新帳號複製預設帳號當下的政策；`n8n_session` 不複製；建立不記 history | 建立用 `profile_initial_state`（第 3.4 節） |
| DQ-12 | 索引壞與被外改：8081 503；面板照開、提供「隔離帳號索引」 | 第 3.6 節 |
| DQ-13 | 2026-11-15 17:4x 使用者採用建議：endpoint 全域一個、只存在預設帳號 | 第 3.8 節（`decisions.md` 由 #100 記） |
| DQ-14 | 2026-11-15 17:4x 使用者採用建議：刪除先撤銷 token 並抹掉後端憑證再刪、孤兒不自動刪、面板列出可刪、不做軟刪除、兩段確認 | 第 3.5 節；API 端要 If-Match＋Idempotency-Key，兩段確認的 UI 在 HM-11 |
| DQ-15～DQ-18（依 DQ-40 (a)） | 寫入保護、名稱規則、`X-MCP-Profile`、帳號選擇只放記憶體 | 第 3.2、3.4、3.7 節；DQ-18 是 HM-11 |
| DQ-19 | `/health/ready` 只代表預設帳號 | 不變 |
| DQ-28 | OpenDesign、Odoo Manage 不開放 | 建立 409 `profile_product_unsupported`、`profiles_supported:false` |
| DQ-36 | commit 不加 AI 署名 | commit |
| DQ-40 (a) ①～④ | 必帶帳號、回聲、CRUD If-Match 與 Idempotency-Key、名稱加嚴 | 第 3.2、3.4、3.7、3.8 節 |
| UC-10（2026-11-15 15:3x） | 照 PaaS 用 `X-MCP-Profile` 標頭，不做網址路徑備案；探針實測不通才補 | 第 3.2 節；契約 §3.7 |
| DQ-33 | 本機短 TMPDIR、以 CI 為準 | 第 5 節 |
| DQ-37 (a) | 同 uid 不是安全邊界（一個子程式被攻破＝整個 add-on） | 隔離名在帳號鎖裡選、目錄比對與「不跟隨連結」是防誤改與誤拷，不是安全邊界（第 3.2、3.5 節） |

沒有碰到其他待定題。HM-07 審查 S-14（讀檔也用執行中 Python 的 Unicode 資料庫擋 Cn，DQ-16 的細節）：維持讀檔也擋，理由見第 13.1 節。

## 11. 待 HM-03a 確認

| 項目 | 本片怎麼處理 | 要 HM-03a 量什麼 |
|---|---|---|
| Ingress 會不會原樣轉 `X-MCP-Profile`（UC-10） | 只認這個標頭（使用者決定）；不轉的話開通後所有帳號範圍請求都 400 `profile_id_required`，面板用不了（不會落到別的帳號）。研究時讀過原始碼：Core 端會轉（`INIT_HEADERS_FILTER` 只濾 8 個標頭；計畫 §5.3 第 11 點、C2 第 4 節），Supervisor 端還沒實測 | 拋棄式 echo add-on：自訂標頭、重複兩個時的樣子 |
| Ingress 會不會轉 PATCH、DELETE 與它們的本體、`Content-Type`（改名的 JSON 本體） | 照 PaaS 的方法；不轉就要回到契約 §3.7 的備案（使用者 15:3x：探針實測不通才補）。Core 端讀原始碼會轉，Supervisor 端待實測 | 同上 |
| Ingress 會不會動 `If-Match`、`Idempotency-Key`、`X-CSRF-Token`（今天的面板已在用，預期會轉） | 照舊 | 同上，順便記 |
| 容器裡 `/proc/meminfo` 的 MemAvailable 是主機的值、cgroup `memory.max` 看不看得到（HM-09 的項目） | 建立時照第 3.4 節；讀不到就照建立、一行 WARNING | 同 HM-09 筆記第 11 節 |
| `os.rename` 改名索引、`shutil.rmtree` 在 HAOS 的資料磁碟（ext4／overlay）上的行為 | 照 POSIX；刪不乾淨只記 WARNING | 刪除與隔離各做一次，看目錄與項目數 |
| add-on 容器的 `RLIMIT_NOFILE`（HM-08 的項目） | 提不到 FD 預算時只服務預設帳號，建立回 409 `profile_limit_reached`、`limit` 0（第 3.4 節） | 同 HM-08 筆記：soft／hard 的值；Odoo 要 544（＋25% 是 680） |

## 12. 驗收條件（計畫 §12.3 HM-10）

| 條件 | 結果 |
|---|---|
| 全綠 | 本機：全套（`bc37ac7`）5,411 案，5,404 過，7 個失敗都是本機一定失敗的 root 案例（第 7 節），0 skip；之後只多一個測試案例（`47d03dd`），相關 9 檔 228 案重跑全過；packaging 檢查都過（第 5 節）。CI（root、0 skip）開 PR 後才知道 |
| 共用管線從 `admin_api`／`admin_action` 抽出、兩次角色檢查 | 通過：`management_operation`／`management_value`／`management_exchange`（第 3.1 節）；⑥ 在分派器、⑩ 在 `ProfileAdmin._final` 與各帳號的 `admin_action`；突變 M01、M04 被抓到 |
| 新 `profile_admin.py`：增刪改查、索引隔離、容量判斷（409＋`limit`、`required_memory_mib`、`available_memory_mib`）；錯誤欄位照 PaaS；DQ-14 的刪除順序；寫索引一律傳 `expected=` | 通過（第 3.3～3.6 節；A 的建立、刪除、隔離各案；突變 M07～M12、M15、M18、M22、M29、M30） |
| `profile_router.py` 的 8099 分派：方法表、開通後帳號範圍路徑剛好一個 `X-MCP-Profile`；不做網址路徑備案（UC-10） | 通過（第 3.1、3.2 節；突變 M02、M03、M16、M19、M23） |
| `gateway.py`：profiles 路由、bootstrap 回聲與 `profiles_supported`、帳號範圍回應帶回聲、endpoint 全域、owner-defaults 只在預設帳號 | 通過（第 3.8 節；突變 M13、M14、M21） |
| `configuration.py`：HMAC domain 帶帳號 id；`operations.py`：索引旁收據；清單帶 `status`、`blocked_reason` | 通過（第 3.3、3.7 節；突變 M05） |
| 建立後子程式要起；刪除後舊 token 立即失效、子程式停、port 釋放、目錄刪除、blocked 帳號立刻重評（T-09） | 通過（A `test_a_new_profile_…`（在新帳號自己的鎖裡起，突變 M24）、`test_a_deletion_revokes_…`（監看也停，M25）、`test_deleting_a_profile_under_load_…`、`test_a_save_waiting_for_a_deleted_profiles_lock_…`（含刪不乾淨的孤兒，M27）、`test_a_profile_directory_is_removed_without_following_a_link`（M26）、`test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`（重評起子程式拿鎖，M28）） |
| 路由表自動產生的否定矩陣；非管理員逐位元相同；建立與重送不回 token；開關關時 `/api/profiles` 404 且不要求標頭 | 通過（M 三案；A `test_a_new_profile_…`、`test_switched_off_…`） |
| 跨帳號 ETag 409（含兩帳號 state 完全相同的對照） | 通過（A `test_another_profiles_etag_is_a_conflict_even_for_the_same_state`；突變 M05） |
| HM-01 黃金回歸與契約凍結在開關關時逐位元 | 通過（三組測試一字未改、全套裡全過；開通重跑也過，第 5 節） |
| 契約第 3 節每一條都指到一個測試 | 通過（第 6 節對照表） |
| UC-10 依使用者決定用標頭（實機結果待 HM-03a） | 照做；實機待 HM-03a（第 11 節） |
| 同 PR 更新帳本；契約「待定」同步並加變更紀錄 | 通過（第 2、8 節；契約第 10 節一列；帳本預檢 OK） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空集合；commit 沒有 AI 署名 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在測試執行時產生（`create_profile`、建立 API）；憑證 `DUMMY-…`、網址 `.invalid`；Idempotency-Key 在執行時產生；沒有 commit 任何像金鑰的字串 |
| 獨立安全審查 | **還沒做**：這個階段只 commit；合併前要做（計畫 §12.1） |

## 13. 還沒解決、交給後面的片

### 13.1 前面的片交給 HM-10 的事項

| 來源 | 事項 | 處理 |
|---|---|---|
| HM-00 第 10 節 | 契約「暫定」：刪除、索引隔離的路徑與回應本體；額外帳號的 owner-defaults 代碼；索引壞時可用的路由 | 做了（契約 §3.1、§3.5、§3.6、§4.1）。刪隔離目錄的路由、全部撤銷失敗的狀態碼、還原紀錄欄位、索引壞時全部撤銷與還原紀錄能不能用：HM-13b／c（契約仍標暫定） |
| HM-00 第 12 節、HM-01 第 4.1 節 | 8099 的 503（名額滿、拿鎖逾時、state 讀不到）、408、413、斷線 403 沒有逐位元案例 | 做了：M `test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte`，沒開通與開通各一次、位元組相同 |
| HM-01 第 11 節 | 改到那條路徑的片補未開通時的逐位元案例 | 管理面（§4.1）做了；MCP 面（§4.2）是 HM-08、HM-14 |
| HM-05 第 11 節 (1) | 從 `admin_api`／`admin_action` 抽出共用管線 | 做了（第 3.1 節）；沒有經 `admin_pipeline` 注入點，理由見第 3.1 節 |
| HM-05 第 11 節 (2) | 帳號回聲的範圍定案、逐條測試 | 做了（契約 §3.4；A `test_every_answer_of_a_profile_names_it`） |
| HM-05 第 11 節 (3)、(5)；審查 S-3 | HMAC domain 加帳號 id；兩個帳號 state 完全相同的對照案例 | 做了（第 3.7 節；突變 M05 被抓到） |
| HM-05 第 11 節 (4) | 刪帳號用執行套件的 `token_access.committed()` 與 `mutation_lock` | 做了（第 3.5 節） |
| HM-05 第 11 節 (6) | `echoed()` 只處理 `JSONResponse`；同名多值標頭被合併；`profile_view()` 丟例外變 500 | 第一點照舊（刻意）；第二點改了；第三點：`ProfileManager.echo` 不丟例外（第 3.8 節） |
| HM-07 第 12 節第 6 點（S-08） | 管理面、收據、owner-defaults、`child_spec` 走路徑 | ⑦ 每次比一次額外帳號目錄的 `(st_dev, st_ino)`，換掉就 503；額外帳號的 owner-defaults 一律拒絕；收據與 `child_spec` 仍走路徑（同 uid 才做得到，DQ-37；比對與使用之間仍有時間差，不是安全邊界） |
| HM-07 第 12 節第 7 點（S-14） | 讀檔也擋 Cn 綁住目前 Python 的 Unicode 資料庫 | 維持讀檔也擋（DQ-16 照計畫「拒絕未指派」）。理由：Unicode 指派過的字不會再變未指派，換新版 Python 只會多認字；要讀到「新 Python 寫的名稱」的舊 Python，只會發生在還原較舊的備份時，而還原帶回的是備份當時的索引（那時的名稱是那時的 Python 驗過的）；Store 也不收降版。寫進本筆記，HM-18 決定要不要寫進 DOCS |
| HM-07 第 12 節第 8 點（S-15） | 同一秒的隔離名撞名 | 索引隔離：在帳號鎖裡選一個沒人用的名稱，必要時加 `-2`…（A `test_a_second_quarantine_in_the_same_second_gets_its_own_name`）；帳號目錄的隔離名是 HM-13b |
| HM-07 第 12 節第 9 點 | 寫索引一律傳 `expected=`；`ProfileDataError` 之後用手上的 view 複查 | 做了：建立、改名、刪除都傳 `manager.index`；失敗後 `serves_mcp()` 複查（MODIFIED 維持到重啟）。只有索引隔離之後重新 `read_index`（隔離本來就是要換基準） |
| HM-08 第 3.5、14.2 節 | `add`／`remove`／`adopt_index`；`shared.pipeline`；每帳號的管理 app；S-08 的管理面；契約 §3 | 做了；`shared.pipeline` 不用（第 3.1 節）；分派器呼叫 `admin_action`，不經各帳號的 app |
| HM-09 第 13.2 節 | 清單的 `status`（`stopped` 要對應）、`blocked_reason`、`disabled_reason`；409 記憶體與 port；寫索引後 `adopt_index`＋`reevaluate()`；建立後 `start_profile`；刪除用 `remove`；8099 把 `child/restart` 等路由到額外帳號 | 做了（第 3.3～3.5 節）；`profile_limit` 的 `blocked_reason` 維持 `null` |
| HM-09 第 13.2 節（HM-10／HM-11） | 看門狗一直重試時 `apply_state` 是 `pending`，清單用 `status=backoff` | 清單照 `Supervisor.status` 給 `backoff`；面板要不要另外提示是 HM-11 |
| HM-08 審查第 15.3 節（`claude-delivery` 版筆記） | FD 預算照產品上限算；索引被手改成超過上限時多開的 client 會超出估計：「交 HM-10（建立帳號時本來就擋上限）」 | 建立擋上限（409 `profile_limit_reached`，A `test_a_creation_is_refused_…`）；FD 上限提不到預算、只服務預設帳號時建立也擋（`limit` 0，A `test_no_profile_is_created_while_only_the_default_profile_is_served`，第三個工作階段補的）；手改索引是同 uid（DQ-37），量實際 FD 是 HM-19c |
| HM-09 審查 S-4（R16、R17） | `reevaluate()` 新變 disabled 的帳號要停（R16）、`remove()` 要停該帳號的監看（R17）沒有測試；「或在 HM-10 交接寫成必測」 | HM-09 的 PR（`wave3/pr-HM-09.md`）寫明它的修正線已補這兩個測試，並寫「HM-10 接線後經 API 再測」。R17 經 API 測了：刪除的案例斷言被刪帳號的監看工作已取消、不在管理器的監看表裡（突變 M25 被抓到）。R16 經 API 測不到：HM-10 的 API 沒有一條路會讓帳號「新變 disabled」（建立先擋上限、記憶體與 port，新帳號排在索引最後、不會擠掉前面的；改名不改 disabled；索引隔離是整個停掉） |
| HM-09 審查 S-12 第 2 點 | `start_all`、`reevaluate` 的 `launch()` 不拿 `mutation_lock`，和面板存檔交錯；「HM-10 接線時一起處理」（HM-09 的 PR 也寫「(2) `_relaunch` 拿 `mutation_lock` 交 HM-10」） | 做了：建立後在新帳號自己的鎖裡 `start_profile`（A 的建立案例、突變 M24）；`ProfileRuntime.launch()`（開機與重評）也拿該帳號的鎖（A `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`、突變 M28）。沒有改 `_relaunch`：存檔與面板重啟是拿著鎖呼叫它的，在它裡面拿會自己鎖死（第 3.4 節） |

### 13.2 交給後面的片

- **HM-11（面板）**：開通後每個帳號範圍請求都帶 `X-MCP-Profile`（含 `default`）；比對 bootstrap 與變更兩個回應的回聲；清單的 `orphans`
  （列出可刪）；`profile_index_state:"corrupt"` 時顯示「隔離帳號索引」並送 `profile_index_etag`；刪除與隔離的兩段確認（DQ-14）；
  `profiles_supported:false` 不顯示新增；PATCH、DELETE 一定帶 CSRF（開通後方法表在 identity 之後）；建立的回應沒有 token，要另外 reveal；
  建立重送回目前那一列、帳號已刪時只有 id；`status`、`blocked_reason`、`disabled_reason` 的文字；fixture server 照本片的回應形狀；
  `profile_limit_reached` 的 `limit` 可能是 0（FD 預算不夠、只服務預設帳號）；`corrupt` 時隔離回 409 `config_conflict` 而索引仍是
  `corrupt`，表示沒有索引檔可隔離（`profiles/` 開機時列不出來），提示「修好後重啟 add-on」。
- **HM-12**：Odoo 換身分換 token（`backend`、`backend/patch` 經分派器，`admin_action` 不變）；A 的審批 token 在 B 被拒。
- **HM-13b**：休眠帳號（沒開通但有資料）的 bootstrap `dormant_profiles`；索引旁收據在還原時的封存（`.profiles.json.operations.json.restored`）
  與 410 `operation_restored`；帳號目錄的隔離名（S-15）；開機守門與本片刪除、隔離的互動（`.revoke-all-pending`）。
- **HM-13c**：全部撤銷、還原紀錄、核對、刪隔離目錄四條全域路由加進 `GLOBAL_ROUTES`（`ProfileAdmin` 加 handler，矩陣自動涵蓋）；
  `token/rotate` 的 409 `restore_review_required`；索引壞時這幾條能不能用（契約暫定：照常可用）。
- **HM-16**：P9 kit 與容器探針的管理請求帶 `X-MCP-Profile`；多帳號的增刪改查與隔離在容器裡跑一次。
- **HM-18**：DOCS 寫刪除與隔離的步驟、S-14 的說明、Ingress 備援沒做的理由；「`profiles/` 開機時列不出來：修好後重啟 add-on（隔離索引
  解決不了）」；FD 預算不夠時不能新增帳號；`tests/contract/profiles_v1_cases.json` 要不要加管理面的資料案例（第 6 節）；契約第 9 節的
  刻意差異表沒有 FD 預算這一列（HM-08 起就沒有；PaaS 沒有 FD 預算），「FD 不夠只服務預設帳號、建立回 `limit` 0」要不要補一列。
- **HM-25**：n8n 上 `ProfileManager` 時，刪除要清它的 `/tmp/woow-n8n-mcp/profiles/<id>/`（PaaS `profile_deleted` 回呼的 HA 版）；n8n 的
  `ConfigurationState` 也帶帳號 id。
- **獨立安全審查**：合併前要做（計畫 §12.1）。

### 13.3 rebase 時要注意

- `claude-delivery` 的 #99（HM-08 審查修正）改了 `gateway.py` 的 `make_apps` 說明與轉送一段、`profile_router.py` 的模組說明與
  `ProfileGate`、契約第 2、5 節；本片改的是管理那一段與檔尾，預期能自動合；`make_apps` 說明文字的尾段（HM-08、HM-09、HM-10 三段相鄰）要手動看。
- HM-09 的修正若改了 `ProfileManager` 的 `add`／`remove`／`reevaluate`／`start_profile`／`free_port`／`relabel` 用到的欄位，只要改
  `profile_admin.Registry` 一處；測試裡碰到 HM-09 內部的只有 `tests/test_profile_admin_api.py` 的 `monitor_of()`（讀 `_monitors`）一處。
  HM-09 修正線的 clone 沒有讀也沒有改；它改了什麼只從 repo 外的 `wave3/pr-HM-09.md` 得知（例如 rebase 到 HM-08 最終 head `adfc4bf`、
  `start_all` 每個帳號各自攔例外、IPv6 試綁、`lifecycle.py` 列管）。
- 本片直接改到 HM-09 程式的地方只有 `profile_runtime.py` 的三處：`ProfileRuntime.launch()` 拿鎖（4 行，含 `nullcontext` 的 import）、
  `ProfileManager.__init__` 的 `files_for_extras`、`open()` 記下 `raise_open_file_limit` 的結果。HM-09 的修正若也改了 `launch()` 或
  `open()` 的那一行，手動合：保留兩邊（`launch()` 的鎖包住 `_relaunch`；`served = self.files_for_extras = …`）；`start_all` 的
  `one()` 改成各自攔例外不影響本片（它呼叫的還是 `launch()`）。合完照實際內容重算 `profile_runtime.py` 的摘要。
- #99 的 `tests/test_reply_mask_union.py` 新案例（`test_diagnostics_carry_no_token_either`）用 `runtime.admin(B)`：本片把這個測試工具改成經
  8099 分派器、帶 `X-MCP-Profile`，rebase 後照樣可用；#99 對 `tests/test_router_passthrough.py` 的改動（`Forbidden.__getattr__`）和本片改的段落不重疊。
- #100 的 `decisions.md`（DQ-13、DQ-14 已定）本片沒有重複改；契約第 9 節 #75 仍寫「上限 40 分鐘、DQ-43 待定」，不是本片的範圍，HM-18 或下一個
  動契約的片順手改。
- 帳本：rebase 後重算 6 個列管檔與 `profile_admin.py` 的摘要（`SP:hm10/ledger_update.py`、`ledger_update3.py` 的做法：說明不動、
  摘要照實際內容算），重跑兩個預檢與 CI。
- `checks` 秒數：開 PR 後補（第 7 節）。
