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
- 新測試 2 檔 37 案（`tests/test_profile_admin_api.py` 32 案、`tests/test_admin_pipeline_matrix.py` 5 案；審查修正前是 35 案：30＋5）；
  改 2 個測試工具／既有測試檔。先寫測試：實作前（`24d72cc` 的核心程式）新 2 檔 35 案 32 失敗（通過的 3 案鎖的是沒開通與 HM-01 交下、
  本來就不該變的位元組），實作後全過；第三個工作階段補的 3 案對前一版（`537f5bc`）全紅、改完全過（第 4.1 節）。作者的臨時突變 30 個
  全部被抓到（第 4.2 節）。
- **獨立安全審查（2026-11-16）判定「修正後通過」**：程式沒有安全問題，但有 5 處契約條文沒有測試守住（必修 MF-1）；另有建議 6 項。
  第四個工作階段全部處理（第 14 節）：補 5 處測試（突變 R03、R04、R05、R13、R17、R18、R21 都改成被抓到）；索引隔離改成拿每個已登錄
  額外帳號自己的鎖（S-1，先寫的測試在 `c094e63` 紅、改完綠）；契約第 9 節補 PaaS 差異（S-2）；筆記數字更正（S-3）；Ingress 轉不轉
  `ETag` 回應標頭列進第 11 節（S-4）；S-5、S-6 交 HM-18，寫進 PR 描述。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest（HEAD `bc37ac7`）：5,411 案、5,404 過、7 失敗（都是本機一定失敗的
  root 案例）、0 skip，1,841.6 秒；之後只多一個測試案例（`47d03dd`），本片＋相關 9 檔 228 案重跑全過（第 5 節）。
- 契約第 3、4.1、5、7 節標「暫定／待定」而本片定下的細節都已同步，變更紀錄一列（第 3.9 節）；驗收矩陣 T-12 補上本片的刪除測試。`decisions.md` 沒改：DQ-13、DQ-14 已由 #100
  記進 `claude-delivery`，本分支沒有它，rebase 時會一起進來。
- 這條線只 commit，不 push、不開 PR（計畫 §12.1：HM-10 是「審查」片，獨立安全審查已做，第 14 節）。2026-11-16 rebase 到 HM-14 之後才 push、
  開 PR（第 15 節）。
- 工作分四個工作階段：第一個寫測試與實作（2026-11-15 21:29 撞到用量上限）；第二個補鎖與刪目錄的斷言、修全套抓到的退步、commit 4 個
  （2026-11-16 00:41 主程序結束中斷，紅的那一段跑到一半）；第三個（06:3x 起）重跑全部檢查、補 3 個缺口（開機與重評起子程式的鎖、FD 預算、
  沒有索引檔的隔離）與筆記；第四個（09:4x 起）處理獨立安全審查的意見（第 14 節）。第 1～13 節的數字是第三個工作階段驗證的，
  審查修正改到的地方另外標明；審查修正的數字在第 4.3、5、7、14 節。
- **2026-11-16 rebase 到 HM-14（PR #103）之後**（第 15 節）：16 個 commit 用 `git rebase --onto 8ff259b 24d72cc` 重放，HM-14 合併後再
  rebase 到 `claude-delivery` `7c6f80c`（樹和 `8ff259b` 相同、沒有衝突）。衝突 5 個 commit，都是說明文字、契約與帳本；程式的改動 git 自動合併、
  逐行等於原本。兩邊的行為都留：HM-08 審查修正、HM-09 最終版、HM-20、HM-14 的程式一行沒被本片蓋掉。本片在契約第 9 節沒有自己的列
  （差異併在 #19、#27、#34、#51），列號不用改；#19、第 3.3 節補指到 HM-08 審查的 #87、#88，#75 改成上限 60 分鐘。帳本 7 列照實際內容
  重算。rebase 後本機：本片 3 檔 86 案、HM-01 45 案、HM-14 143 案、HM-20 243 案、HM-09 119 案、相關其他 24 檔 1,027 案全過；全套
  5,780 案只有 7 個要 root 的失敗、0 skip；突變 6 個全部抓到；兩個預檢 OK。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-10（計畫 §12.3；風險高、工作量 L；「審查」片） |
| 分支 | `feat/ha-multiprofile-hm10-20261115`（一般 clone），疊在 HM-09 的實作 head `24d72cc` 上；2026-11-16 rebase 到 `claude-delivery` `7c6f80c`（HM-14 PR #103 合併後；第 15 節） |
| 基準 | `claude-delivery` 的 HM-00～HM-08（HM-08 是審查前的 `cfdc487`）、HM-13a、HM-17、HM-02，加上 HM-09 的 5 個 commit（HM-09 在別的工作線審查與修正中）。`claude-delivery` 之後又合了 #99（HM-08 審查修正：`gateway.py`、`profile_router.py`、契約）與 #100（`checks` 上限 60 分鐘、`decisions.md` 記 DQ-13／14／30／31／43），本分支都沒有，rebase 時處理（第 13.3 節） |
| 依據 | 計畫 §4.3、§4.4、§5.3（全部）、§7.2 第 1、2 點、§8.5、§8.8、§10.3 的 HM-10 列、§12.0、§12.3 HM-10；契約 §1、§3、§4.1、§9；`threat-model.md`（I3、I5、I6、I10、I12）；FM-01、05、06、07、08、12、18、19、21、22、23、24、25、26、33、47、53、54、93、131、139、148；驗收矩陣 T-02、T-06、T-07、T-09、T-12；HM-00～HM-09 的 provenance 筆記交給 HM-10 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425`：`profiles.py`（`ProfileRegistry.create`／`rename`／`delete`／`list`、`ProfileCapacity`、`ProfileContextMiddleware`）、`routers/profiles.py`、`routers/tokens.py`（`set_token` 撞號，HA 沒有這個 API：§8.8 #80）、`tests/test_profiles.py`；HA 加嚴的地方都在契約第 9 節（#31～#35、#83） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/gateway.py` | 共用管線抽成模組層函式：`management_operation`（頁面檢查）、`management_value`（③）、`management_exchange`（①～④）、`management_app`、`method_not_allowed`；`JSON_OPERATIONS`、`PROFILE_OPERATIONS`（帳號範圍的路由表）。`make_apps` 的 `admin_page`、`admin_api` 改呼叫它們（行為不變）；多兩個 keyword-only 選項 `default_endpoint`（額外帳號）、`bootstrap_fields`；回聲保留動作設定的每個標頭（HM-05 審查的提醒）；`admin.state.profile_action` 給分派器 |
| `Hc/profile_router.py` | `AdminDispatcher`（開通後的 8099）、`GLOBAL_ROUTES`（全域路由表）、`global_route`、`is_global`；模組說明 |
| `Hc/profile_admin.py`（新） | `ProfileAdmin`：清單、建立、改名、刪除、索引隔離（⑧～⑪）、索引 ETag 與壞索引 ETag、容量判斷（FD 預算不夠時 `limit` 0）、bootstrap 欄位、⑦ 的額外帳號解析；沒有索引檔時不隔離；`Registry`：本模組用到的 `ProfileManager` 介面全部集中在這裡（建立後在新帳號自己的 `mutation_lock` 裡起子程式）。審查修正（S-1）：索引隔離另拿每個已登錄額外帳號自己的鎖（`_registered_profiles_locked`），第二輪撤銷拿掉 |
| `Hc/profile_runtime.py` | `ProfileManager`：建 `ProfileAdmin` 與 `AdminDispatcher`（`admin_app` 改成分派器）、每帳號的回聲（`echo`、`relabel`）、bootstrap 欄位、額外帳號的 `default_endpoint`、`files_for_extras`（開啟時 FD 上限夠不夠額外帳號用）；`ProfileRuntime`：`ConfigurationState` 帶帳號 id、收 `default_endpoint`／`bootstrap_fields`、`admin_action`（`make_apps` 放在 admin app 的 `state`；測試替身的 admin app 沒有時是 `None`，只有開通的分派器會呼叫它）、`launch()` 拿該帳號的 `mutation_lock`（HM-09 審查 S-12 第 2 點） |
| `Hc/configuration.py` | `ConfigurationState(profile_id=…)`：revision 的 HMAC domain 帶帳號 id（`edit:<id>`、`launch:<id>`） |
| `Hc/operations.py` | `OperationJournal(results=, subjects=)`；`PROFILE_RESULTS`（`profile.create`、`profile.delete`、`profile.index_quarantine`）、`SUBJECT`。帳號自己的收據檔格式不變 |
| `Hc/profiles.py` | `free_index_quarantine_name`（同一秒加 `-2`…）、`move_index_aside`、`index_bytes`、`remove_profile_directory`（從 `O_NOFOLLOW` 開、驗過擁有者的 `profiles/` 目錄 fd 往下刪） |
| `tests/test_profile_admin_api.py`（新，30 個測試函式、32 案；審查修正前 28 個函式、30 案） | 契約第 3 節的情況（第 6 節對照表）。審查修正：新函式 2 個（刪除途中索引被外改、索引隔離拿帳號的鎖），延伸 3 個（第二次角色檢查、owner-defaults、`X-MCP-Profile`），工具函式 `replace_index` |
| `tests/test_admin_pipeline_matrix.py`（新，4 個測試函式、5 案） | 路由表與 `admin_action` 的對照；否定矩陣；分派器路由每條路由；HM-01 交下的固定回應（開與關） |
| `tests/multi_profile_runtime.py` | HM-08 的測試工具：`Runtime.admin(profile_id)` 改成面板的客戶端（開通時經 8099 分派器、每個請求帶 `X-MCP-Profile`；沒開通照舊）；可指定 `verifier` |
| `tests/test_router_passthrough.py` | HM-08 的開通後重跑 HM-01 三組測試：管理客戶端帶 `X-MCP-Profile: default`、把回聲拿掉再比位元組（`Unechoed`；PATCH／DELETE 補 CSRF，因為開通後方法表在 identity 之後）；8099 是分派器的斷言 |
| `docs/multi-profile/contract.md` | 第 3.1～3.7、4.1、5、7 節、第 9 節 #27、第 10 節一列（第 3.9 節）。審查修正：第 3.1、3.2、3.6 節，第 9 節 #19、#34、#51，第 10 節再一列 |
| `docs/multi-profile/acceptance-matrix.md` | T-12 的測試欄補 `tests/test_profile_admin_api.py`（刪除那一半） |
| `docs/provenance/runtime-patches.json` | 6 個列管檔重算摘要並補說明；新列 `profile_admin.py`；第三個工作階段改了 `profile_runtime.py`、`profile_admin.py`，照實際內容再算一次；審查修正改了 `profile_admin.py`，摘要照實際內容再算、說明補 S-1 一句 |
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
- 做法（審查修正後）：拿全 add-on 的帳號鎖 → 依 id 順序拿每個已登錄額外帳號自己的 `mutation_lock`（各最多 2 秒，逾時 503、已拿到的放掉；
  審查 S-1）→ ⑩ → If-Match、Idempotency-Key 等檢查 → 選一個沒人用的隔離名 → 列出 `profiles/` 底下的帳號目錄（列不出來就 503，不留收據）
  → 收據 begin → 撤銷這些帳號目錄與每個已登錄額外帳號的 token → 提交 → `profiles.json` 改名成
  `profiles.json.quarantine-<UTC>`（同一秒有了就加 `-2`、`-3`…，不覆蓋：HM-07 審查 S-15；在帳號鎖裡選名稱）→ 重新讀索引（absent）→
  adopt：8081 立刻恢復服務預設帳號，不用重啟 → 已登錄的額外帳號停掉、不再路由 → 放開各帳號的鎖 → 孤兒遮罩值、reevaluate → 收據 complete
  → 200 `{"quarantined":"<檔名>","operation"}`。帳號目錄都變孤兒，可以逐一刪。
- 為什麼要拿各帳號的鎖（審查 S-1，實驗 E1）：原本只拿全 add-on 的鎖。C 正在輪替 token（已拿 C 的鎖、已讀 state、停在最後一次角色檢查）時，
  隔離撤銷了 C；輪替放行後用隔離前讀到的 state 比 If-Match，照樣寫進新 token，8081 在 C 被移除登錄之前用新 token 回 200（原本靠
  「移除後再撤銷一次」收尾）。現在隔離等 C 的鎖：輪替先做完，再被唯一一次撤銷收掉；隔離途中才來的請求拿到鎖時 C 的 store 已關（503）。
  所以「再撤銷一次」拿掉了。存檔或面板重啟也被同一把鎖排開，不會和移除登錄交錯（審查推論、沒實測的「`aclose()` 之後才 `start()`、
  留下沒人管的子程式」那種空檔）；這一種沒有另寫隔離的測試，做法和刪除相同，刪除那邊由 A `test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing`
  守住。只有管理員自己的並行操作會撞到這個空檔，原本也不算越權。
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
14. 審查修正（S-1）：索引隔離依 id 順序拿每個已登錄額外帳號的鎖，⑩ 在拿完之後，拿到移除登錄為止；撤銷只做一次（第 3.6 節；契約
    §3.2、§3.6）。
15. 審查修正（S-2、S-6）：契約第 9 節 #19、#34、#51 補上和 PaaS 的差異；第 3.1 節寫明開通後預設帳號看得到的兩個 405／403 位元組變化。

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
| M04 | `profile_admin.py` | 全域路徑的第二次角色檢查（⑩）一次全部拿掉（`_final` 不問角色）。審查更正（S-3）：只靠建立、改名、刪除（等全域鎖）那幾輪抓到；單獨拿掉清單、索引隔離或「刪除等完目標帳號的鎖」的 ⑩，審查前的測試都抓不到（審查突變 R04、R03、R05），第 4.3 節補上 | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change` |
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

### 4.3 審查修正的先紅後綠與突變（第四個工作階段，2026-11-16）

- 做法：先寫測試（第 14 節），再改程式。紅的那一半照第 4.1 節的做法：工作樹的 `tests/test_profile_admin_api.py` 對審查對象 `c094e63` 的核心跑
  （`SP:hm10-fix/base`：`git archive c094e63 packages/mcp-admin-core`、建好的 UI 一份、`apps` 連回 clone，因為 `products.ROOT` 是
  `parents[3]`；`pytest -o "pythonpath=<base> apps/n8n"`）。突變用 `SP:hm10-fix/mutate.py`：每個突變是工作樹核心的一份拷貝（同樣帶 UI 與
  `apps` 連結）改一處（原字串剛好出現一次、改完可編譯），用真的 pytest 跑本片 3 檔（A＋M＋P，86 案），跑完刪掉拷貝；工作樹不動
  （每輪前後 `git status` 都只有本片還沒 commit 的 5 個檔）。
- 第一輪（10:13～10:38）有兩個自己的錯，重跑過：(1) base 少了 `apps` 連結，紅的那一半每個起 runtime 的測試都卡在 `settle()` 逾時，結果作廢；
  (2) 突變 S1a（隔離不拿帳號的鎖）下，`test_the_index_quarantine_holds_every_profiles_own_lock` 自己卡住（攔 `manager.remove` 的鉤子在第一段就裝了，
  隔離走到移除 B 就停著等測試放行），跑到 900 秒上限。測試改成鉤子到第二段才裝、每個等待都有上限，退步時會失敗、不會卡住；突變工具也改成
  逾時記 TIMEOUT、不中斷。第一輪其他結果（綠、HM-01、相關 29 檔、packaging）程式相同，照用（第 5 節）。
- 紅（第二輪，`c094e63` 的核心）：A 32 案 **2 失敗**、30 通過，4.5 秒。失敗的正是 S-1 的兩處：`test_the_index_quarantine_holds_every_profiles_own_lock`
  （C 的鎖被拿著，隔離沒等它，回 200 而不是 503）與 `test_the_second_role_check_comes_after_every_wait_and_before_any_change`（拿著 B 的鎖送隔離，
  隔離沒等它，回 200 而不是 403）。MF-1 補的其他測試在 `c094e63` 都通過：那些條文的程式本來就對，測試要守的是之後的退步（下表）。
- 綠（第二輪，修正後）：A＋M＋P 86 案全過，16.2 秒。
- 突變（第二輪，修正後的程式與測試，206 秒）：

| id | 改了什麼 | 結果 | 抓到它的測試 |
|---|---|---|---|
| M00 | 沒改（拷貝本身） | 86 案全過 | — |
| R03 | 索引隔離拿掉 ⑩（審查 R03） | 抓到（審查前存活） | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change` |
| R03b | 索引隔離的 ⑩ 移到拿帳號的鎖之前（S-1 的順序） | 抓到 | 同上 |
| R04 | 清單拿掉 ⑩（審查 R04） | 抓到（審查前存活） | 同上（清單一次請求問兩次角色） |
| R05 | 刪除的 ⑩ 移到等目標帳號的鎖之前（審查 R05） | 抓到（審查前存活） | 同上 |
| R13 | 刪除寫索引改用重讀的 view（審查 R13） | 抓到（審查前存活） | A `test_a_deletion_never_writes_over_an_index_changed_meanwhile` |
| R17 | 額外帳號的 owner-defaults 動作不拒絕（審查 R17） | 抓到（審查前存活） | A `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles` |
| R18 | 額外帳號的 bootstrap 給 owner-defaults 通知（審查 R18） | 抓到（審查前存活） | 同上 |
| R21 | ⑦ 不比對目錄是不是開啟時那一個（審查 R21） | 抓到（審查前存活） | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| R24 | 隔離不撤銷已登錄帳號的 token（審查 R24） | 抓到（審查前存活） | A `test_quarantining_…[replaced]`、`test_the_index_quarantine_holds_every_profiles_own_lock` |
| S1a | 隔離不拿已登錄帳號的鎖（`c094e63` 的做法） | 抓到 | A `test_the_index_quarantine_holds_every_profiles_own_lock`、`test_the_second_role_check_…` |
| S1b | 隔離在移除登錄之前就放開帳號的鎖 | 第二輪存活；第三輪抓到（見下） | A `test_the_index_quarantine_holds_every_profiles_own_lock` |

- S1b 第二輪存活的原因：放開得早，等在鎖上的請求讀到的是撤銷後的 state，它手上的 If-Match 一定過期（409），所以這組測試看不出差別；
  但 C 原本就沒有 token 時撤銷不改 state，一個隔離前排隊的輪替就可能在移除登錄前寫進新 token。契約寫的是「拿到移除登錄為止」，
  所以補一個直接的斷言：攔 `manager.remove` 的鉤子記下每個帳號被移除登錄時它自己的鎖還在不在隔離手上（B、C 都要是）。
- 第三輪（11:18～11:20，只重跑碰到這個測試的部分）：紅，`c094e63` 的核心 32 案同樣只有 S-1 的 2 案失敗（4.4 秒）；綠，86 案全過（16.8 秒）；
  突變 M00 全過，R24、S1a、S1b 都被抓到（S1b 由 `test_the_index_quarantine_holds_every_profiles_own_lock` 的新斷言抓到）。
  所以修正後的程式與測試下，12 個突變全部被抓到。
- 審查原本存活的 10 個（R03、R04、R05、R13、R14、R17、R18、R17R18、R21、R24）：R14 是等價突變不補（第 14 節）；R17R18 是 R17＋R18 合併，
  兩個各自被抓到就一定被抓到；其他 8 個上表都抓到。
- 結果檔：`SP:hm10-fix/logs/mutations-run2.json`、`mutations-run3.json`（第三輪）、每個突變的 `mut-<id>.log`／`.xml`；紅綠的 junit 在
  `SP:hm10-fix/logs/fix2-red.xml`、`fix2-hm10.xml`、`fix3-*.xml`。

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
| **審查修正（第四個工作階段，2026-11-16）**：環境 | clone 的依賴、patch 與 UI 已由前面的工作階段照 `setup_repo_env.sh` 裝好（11 個 venv／`node_modules` 都在），這次沒有重跑（重跑會連 npm registry）；每輪 `. bin/ha_env.sh`、排在 `SP:wave1-pytest.lock` 後面，一輪只拿一次鎖 | — |
| 審查修正：本片 3 檔 | `SP:hm10-fix/batch.sh`、`batch2.sh`、`batch3.sh` 的綠段：`pytest tests/test_profile_admin_api.py tests/test_admin_pipeline_matrix.py tests/test_router_passthrough.py` | 第一輪 86 案全過、0 skip，16.7 秒（A 32 案 4.0 秒、M 5 案 6.6 秒、P 49 案 5.4 秒）；第二輪 86 案全過，16.2 秒；第三輪 86 案全過，16.8 秒（A 32 案 4.0 秒、M 5 案 6.5 秒、P 49 案 5.6 秒） |
| 審查修正：HM-01 黃金回歸＋兩個契約凍結（開關關） | `batch.sh` 第三段 | 45 案全過、0 skip，6.7 秒；三檔與 `tests/contract/` 對 `24d72cc` 一字未改 |
| 審查修正：相關 29 檔 | `batch.sh` 第四段（審查報告用的同一份清單：HM-05／07／08／09 的測試與既有管理面測試，含讀帳本的 `test_tool_inventory.py`、`test_ledger_precheck.py`） | 1,127 案全過、0 skip，104.2 秒 |
| 審查修正：先紅後綠、突變 | 第 4.3 節 | 紅：`c094e63` 的核心 32 案只有 S-1 的 2 案失敗；綠：全過；突變 12 個（第三輪補 S1b 的斷言後）全部被抓到 |
| 審查修正：packaging | `batch.sh` 第六段（同上面兩列的做法） | `validate.py` PASS；unittest `Ran 201`、`OK (skipped=5)`；`tool_inventory.py` exit 0 |
| 審查修正：全套 pytest | 沒有重跑 | 程式只改 `profile_admin.py` 的 `quarantine()`；碰到 `ProfileAdmin` 與索引隔離的測試只有本片 3 檔（`grep` 過），上面都跑了；相關 29 檔也過。全套以 CI 為準（最後一次本機全套是 `bc37ac7`） |
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
| §3.1 `endpoint`、`owner-defaults/*` | 額外帳號 409；owner-defaults「不管目錄裡有什麼」 | A `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles`（審查修正 MF-1 (3)：B 的目錄放了一次性遷移的標記與復原紀錄，對照組證明它的 state 本來會顯示通知、可以還原；審查前 B 沒有標記，沒標記本來就 409，突變 R17、R18 存活） |
| §3.1 `token/reveal`、`token/revoke`、`token/rotate` | 只動選定帳號；`restore_review_required` | A `test_every_answer_of_a_profile_names_it`（reveal）；HM-08 `tests/test_profile_routing.py`（經分派器輪替、撤銷）；`restore_review_required` 是 HM-13c |
| §3.1 方法 | PATCH、DELETE 只在 `profiles/<id>`；405 位元組 | M `test_the_dispatcher_routes_every_route_of_its_table`；P `test_switched_on_the_management_contract_freeze_holds`；沒開通：A `test_switched_off_the_profile_paths_are_unknown_and_no_header_is_needed` |
| §3.1 query、`%`、`\\` | 400 | P（HM-01 管理契約凍結開通重跑） |
| §3.2 ①～⑥ | 每條路由 × 9 種非管理員 → 403、沒有任何變化 | M `test_every_route_refuses_every_caller_who_is_not_an_administrator` |
| §3.2 ②③④ 的固定回應 | 503（名額、鎖、state）、408、413、斷線 403，開與關同位元組 | M `test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte`（兩種） |
| §3.2 ⑤ | 全域路徑的本體與 id 固定 400 | A `test_a_rename_changes_only_the_label` |
| §3.2 ⑦ | 見 §3.3 | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| §3.2 ⑧ | 帳號鎖、目標帳號的鎖各 2 秒 503；建立後在新帳號的鎖裡起；開機與重評起子程式也拿帳號的鎖；索引隔離拿每個已登錄帳號的鎖（審查 S-1） | A `test_a_deletion_waits_for_the_profiles_lock_and_the_add_ons`、`test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token`、`test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`、`test_the_index_quarantine_holds_every_profiles_own_lock`；M 固定回應（帳號鎖 503） |
| §3.2 ⑨ | 依 state 驗證照今天 | P（「400 a value that does not validate」） |
| §3.2 ⑩ | 第二次角色檢查在每個等待之後、提交之前 | A `test_the_second_role_check_comes_after_every_wait_and_before_any_change`（審查修正 MF-1 (1)(2)：每一種等待各一輪：全域鎖下的建立、改名、刪除、索引隔離；目標帳號的鎖下的刪除；索引隔離拿的 B、C 的鎖；清單一次請求問兩次角色。審查前只有全域鎖下的建立、改名、刪除，突變 R03、R04、R05 存活） |
| §3.2 ⑪ | 寫入保護與狀態相依判斷（含 FD 預算不夠時的上限 `limit` 0、沒有索引檔的隔離） | A `test_every_profile_write_needs_the_index_etag_and_its_operation_id`、建立／改名／刪除各案、`test_no_profile_is_created_while_only_the_default_profile_is_served`、`test_there_is_nothing_to_quarantine_without_an_index_file` |
| §3.2 非管理員逐位元相同 | 標籤有沒有、上限到沒、帳號有沒有、標頭有沒有 | M `test_every_route_refuses_every_caller_who_is_not_an_administrator`（兩輪 × 5 種變化） |
| §3.2 沒開通順序同今天；開通後只多一次角色查詢 | — | HM-01 三組（沒開通，一字未改）；P（開通重跑） |
| §3.2 新路由沒進矩陣就失敗 | — | M `test_the_route_table_has_every_operation_a_profile_answers` |
| §3.3 每一列 | 沒帶、兩個、格式錯、不存在、讀不到、目錄已不是開啟時那一個、索引壞、全域路徑、沒開通、8081 | A `test_a_profile_scoped_request_names_exactly_one_known_profile`（審查修正 MF-1 (4)：執行中把 B 的目錄換成複本，bootstrap 與 `token/reveal` 都 503；審查前沒有這一列的測試，突變 R21 存活）、`test_quarantining_…`（索引壞 503）、`test_switched_off_…`；8081：HM-08 `tests/test_profile_routing.py`（契約案例的 `X-MCP-Profile` 不理） |
| §3.4 | bootstrap 整個回聲與 `profiles_supported`；其他 `profile:{id}`；拒絕不帶；改名立刻換；標頭保留 | A `test_every_answer_of_a_profile_names_it`、`test_a_product_without_profiles_refuses_to_create_one`（`false`）；P（形狀 B 的 ETag 標頭） |
| §3.5 帳號設定 | domain 帶 id、逐位元相同的對照 | A `test_another_profiles_etag_is_a_conflict_even_for_the_same_state` |
| §3.5 增刪改、隔離 | If-Match、Idempotency-Key、各錯誤代碼、重送、提交後失敗 | A `test_every_profile_write_needs_the_index_etag_and_its_operation_id`、`test_an_operation_whose_outcome_is_unknown_is_never_repeated`、`test_the_index_etag_is_bound_to_the_entries_and_this_process` |
| §3.5 建立與重送不回 token | — | A `test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token` |
| §3.6 清單列、`orphans` | — | A `test_the_list_…`、`test_a_profile_over_the_memory_limit_…`、`test_an_orphan_and_an_unavailable_profile_can_be_deleted` |
| §3.6 bootstrap 欄位 | `profile_index_state`、`profile_index_etag` | A `test_every_answer_…`、`test_quarantining_…` |
| §3.6 請求本體與名稱規則 | 剛好 `{"label"}`；DQ-16 | A `test_a_creation_is_refused_…`、`test_a_rename_changes_only_the_label` |
| §3.6 還原紀錄 | HM-13b／c | — |
| §3.6 索引隔離、刪除的步驟 | 含：監看停了、預設 state 沒被寫、刪目錄不跟隨連結、刪除途中在等鎖的請求什麼都不做、刪不乾淨時一行 WARNING（只有 id 前 8 碼）且剩下的是孤兒、`profiles/` 列不出來又沒有索引檔時不隔離；寫索引一律傳手上的 view（刪除途中索引被外改：409、不覆寫、8081 503 到重啟）；索引隔離拿各帳號的鎖、撤銷之後沒有 token 被路由 | A `test_quarantining_…`、`test_a_deletion_revokes_…`、`test_deleting_a_profile_under_load_…`、`test_a_profile_directory_is_removed_without_following_a_link`、`test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing`（`removed`、`left as an orphan`）、`test_there_is_nothing_to_quarantine_without_an_index_file`、`test_a_deletion_never_writes_over_an_index_changed_meanwhile`（審查修正 MF-1 (5)；審查前突變 R13 存活）、`test_the_index_quarantine_holds_every_profiles_own_lock`（審查 S-1；審查前突變 R24 存活） |
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
要不要在 HM-18 定稿時把管理面案例也寫成資料檔，交 HM-18 決定。審查 S-5：這是偏離計畫 §10.3 的決定，PR 描述明列「沒做、理由、交 HM-18
決定」，請主對話確認。

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
- 新測試的時間（審查更正 S-3：原本寫的「34 案、29 案」不對，審查修正前實際是 35 案：A 30、M 5）：審查修正後新 2 檔 37 案本機 10.5 秒
  （`test_profile_admin_api.py` 32 案 4.0 秒、`test_admin_pipeline_matrix.py` 5 案 6.6 秒，最慢的是固定回應兩案各約 2.4 秒與否定矩陣約 1.7 秒）；
  改過的 `test_router_passthrough.py` 49 案 5.4 秒（HM-08 的檔，開通重跑多了帶標頭、拿掉回聲）。審查修正補的 2 個新函式與延伸的 3 個，
  本機每案 0.08～0.26 秒，合計約 0.6 秒。CI 推估新 2 檔 11～16 秒（runner 比本機慢、而且會跳）；全套本機 1,841.6 秒（`bc37ac7`）。全部在程序內
  （ASGI、`NoProcessSupervisor`、MockTransport），不起真子程式。等待都用事件或 `asyncio.timeout`／`wait_for` 上限；只有兩處是
  「等 0.2～0.3 秒、確認某件事沒發生」（刪除途中只斷 B 的呼叫、開機與重評起子程式要等帳號的鎖）：runner 慢只會讓它們少抓到錯，不會讓對的程式
  失敗。審查修正的 `test_the_index_quarantine_holds_every_profiles_own_lock` 讓 C 的輪替停在最後一次角色檢查（`AdminAuthority.verify` 自己的
  3 秒上限內），中間只做幾個程序內請求與一次 0.1 秒的拿鎖逾時，本機不到 0.3 秒；退步時每個等待都有上限，測試失敗、不會卡住。
- `checks` 秒數：前＝#100 合併時 1,899 秒（31 分 39 秒；上限已是 60 分鐘；README 進度紀錄）；本片：開 PR 後補。rebase 後的「前」：
  PR #103（HM-14）合併時 1,650 秒（27 分 30 秒；第一次跑因 HM-09 監看的關閉逾時失敗、重跑全綠，README 進度紀錄）。

## 8. 預檢結果

rebase 到 HM-14 之後的兩個預檢在第 15.8 節（以 `claude-delivery` 為基準）；本節是 rebase 前的紀錄。

審查修正後（第四個工作階段，2026-11-16 11:2x）：兩個都在 commit 本筆記之前、對 HEAD `bbb24bc`（審查修正的 4 個 commit 之後）跑：

| 預檢 | 結果 |
|---|---|
| 秘密預檢（指令同下表） | gitleaks 8.28.0（釘版、已驗）；`24d72cc..bbb24bc` 15 個 commit，另掃 HEAD 樹與全部歷史：**0 命中**（`result: OK, 0 findings`） |
| 帳本預檢（指令同下表） | 173／70／159 筆，0 漂移、0 缺；7 個列管檔都在帳本，沒有沒列管的新執行檔：**OK**。另用 sha256 逐一核對 7 個列管檔的實際內容，和帳本一致 |

commit 本筆記之後，對最終 HEAD 再跑一次兩個預檢；結果寫在 PR 描述（`artifacts/ha-multiprofile-parity-20261114/wave4/pr-HM-10.md`）。

審查前（第三個工作階段）：兩個都在 commit 本筆記之後、對 HEAD 跑（2026-11-16）：

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
| DQ-01 (a) | Bearer 也依 token 選帳號 | 本片不改 8081；刪除與索引隔離之後，舊 token 在 Bearer 與密鑰網址兩條路都立即失效（A 的刪除案例；審查修正的隔離案例另驗 Bearer） |
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
| Ingress 會不會原樣轉送 `ETag` **回應**標頭（審查 S-4；HM-11 審查 S-2 第 3 點）。清單的索引 ETag 只放在回應標頭，建立、改名、刪除、隔離的 If-Match 都從它來；今天的面板寫入版本都從 bootstrap 本體拿，這是第一個靠 Ingress 轉送回應 `ETag` 的流程 | 照 UC-10 同樣的原則（標頭先、實測不通才補）：先不在清單本體多帶版本，不另開和 PaaS 不同的欄位。拿不到時面板怎麼顯示是 HM-11 的事（HM-11 審查 S-2 建議：只剩預設帳號、增刪改停用） | 同上：echo add-on 回一個帶 `ETag` 的回應，看瀏覽器拿不拿得到。拿不到就在清單本體多帶同值的 `index_etag`（面板優先讀本體），HM-10 補或 HM-11 收尾時一起做 |
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
| 契約第 3 節每一條都指到一個測試 | 審查前**不成立**：審查找出 5 條有程式、沒有測試守住（MF-1：索引隔離的 ⑩、刪除等完目標帳號的鎖才做 ⑩、額外帳號 owner-defaults「不管目錄裡有什麼」、目錄換掉回 503、刪除寫索引傳手上的 view）。審查修正後通過：5 條都補了測試，對應的審查突變都被抓到（第 4.3、6、14 節） |
| UC-10 依使用者決定用標頭（實機結果待 HM-03a） | 照做；實機待 HM-03a（第 11 節） |
| 同 PR 更新帳本；契約「待定」同步並加變更紀錄 | 通過（第 2、8 節；契約第 10 節一列；帳本預檢 OK） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空集合；commit 沒有 AI 署名 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在測試執行時產生（`create_profile`、建立 API）；憑證 `DUMMY-…`、網址 `.invalid`；Idempotency-Key 在執行時產生；沒有 commit 任何像金鑰的字串 |
| 獨立安全審查 | 做了（2026-11-16，報告 `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-10.md`，在 repo 外）：修正後通過。必修 MF-1、建議 S-1～S-6 的處理見第 14 節 |

## 13. 還沒解決、交給後面的片

### 13.1 前面的片交給 HM-10 的事項

| 來源 | 事項 | 處理 |
|---|---|---|
| HM-00 第 10 節 | 契約「暫定」：刪除、索引隔離的路徑與回應本體；額外帳號的 owner-defaults 代碼；索引壞時可用的路由 | 做了（契約 §3.1、§3.5、§3.6、§4.1）。刪隔離目錄的路由、全部撤銷失敗的狀態碼、還原紀錄欄位、索引壞時全部撤銷與還原紀錄能不能用：HM-13b／c（契約仍標暫定）。owner-defaults「不管目錄裡有什麼」原本沒有測試，審查修正補上（MF-1 (3)） |
| HM-00 第 12 節、HM-01 第 4.1 節 | 8099 的 503（名額滿、拿鎖逾時、state 讀不到）、408、413、斷線 403 沒有逐位元案例 | 做了：M `test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte`，沒開通與開通各一次、位元組相同 |
| HM-01 第 11 節 | 改到那條路徑的片補未開通時的逐位元案例 | 管理面（§4.1）做了；MCP 面（§4.2）是 HM-08、HM-14 |
| HM-05 第 11 節 (1) | 從 `admin_api`／`admin_action` 抽出共用管線 | 做了（第 3.1 節）；沒有經 `admin_pipeline` 注入點，理由見第 3.1 節 |
| HM-05 第 11 節 (2) | 帳號回聲的範圍定案、逐條測試 | 做了（契約 §3.4；A `test_every_answer_of_a_profile_names_it`） |
| HM-05 第 11 節 (3)、(5)；審查 S-3 | HMAC domain 加帳號 id；兩個帳號 state 完全相同的對照案例 | 做了（第 3.7 節；突變 M05 被抓到） |
| HM-05 第 11 節 (4) | 刪帳號用執行套件的 `token_access.committed()` 與 `mutation_lock` | 做了（第 3.5 節） |
| HM-05 第 11 節 (6) | `echoed()` 只處理 `JSONResponse`；同名多值標頭被合併；`profile_view()` 丟例外變 500 | 第一點照舊（刻意）；第二點改了；第三點：`ProfileManager.echo` 不丟例外（第 3.8 節） |
| HM-07 第 12 節第 6 點（S-08） | 管理面、收據、owner-defaults、`child_spec` 走路徑 | ⑦ 每次比一次額外帳號目錄的 `(st_dev, st_ino)`，換掉就 503；額外帳號的 owner-defaults 一律拒絕；收據與 `child_spec` 仍走路徑（同 uid 才做得到，DQ-37；比對與使用之間仍有時間差，不是安全邊界）。審查修正（MF-1 (3)(4)）：前兩點原本沒有測試，現在 A `test_a_profile_scoped_request_names_exactly_one_known_profile`（執行中換成複本：503）與 `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles`（目錄裡有遷移標記也 409）守住 |
| HM-07 第 12 節第 7 點（S-14） | 讀檔也擋 Cn 綁住目前 Python 的 Unicode 資料庫 | 維持讀檔也擋（DQ-16 照計畫「拒絕未指派」）。理由：Unicode 指派過的字不會再變未指派，換新版 Python 只會多認字；要讀到「新 Python 寫的名稱」的舊 Python，只會發生在還原較舊的備份時，而還原帶回的是備份當時的索引（那時的名稱是那時的 Python 驗過的）；Store 也不收降版。寫進本筆記，HM-18 決定要不要寫進 DOCS |
| HM-07 第 12 節第 8 點（S-15） | 同一秒的隔離名撞名 | 索引隔離：在帳號鎖裡選一個沒人用的名稱，必要時加 `-2`…（A `test_a_second_quarantine_in_the_same_second_gets_its_own_name`）；帳號目錄的隔離名是 HM-13b |
| HM-07 第 12 節第 9 點 | 寫索引一律傳 `expected=`；`ProfileDataError` 之後用手上的 view 複查 | 做了：建立、改名、刪除都傳 `manager.index`；失敗後 `serves_mcp()` 複查（MODIFIED 維持到重啟）。只有索引隔離之後重新 `read_index`（隔離本來就是要換基準）。審查修正（MF-1 (5)）：刪除在拿到 view 和寫索引之間會 await（停子程式），是唯一有外改空檔的路，原本沒有測試；現在 A `test_a_deletion_never_writes_over_an_index_changed_meanwhile` 守住。建立與改名在檢查和寫入之間沒有 await（審查突變 R14 存活但等價），不另補 |
| HM-08 第 3.5、14.2 節 | `add`／`remove`／`adopt_index`；`shared.pipeline`；每帳號的管理 app；S-08 的管理面；契約 §3 | 做了；`shared.pipeline` 不用（第 3.1 節）；分派器呼叫 `admin_action`，不經各帳號的 app |
| HM-09 第 13.2 節 | 清單的 `status`（`stopped` 要對應）、`blocked_reason`、`disabled_reason`；409 記憶體與 port；寫索引後 `adopt_index`＋`reevaluate()`；建立後 `start_profile`；刪除用 `remove`；8099 把 `child/restart` 等路由到額外帳號 | 做了（第 3.3～3.5 節）；`profile_limit` 的 `blocked_reason` 維持 `null` |
| HM-09 第 13.2 節（HM-10／HM-11） | 看門狗一直重試時 `apply_state` 是 `pending`，清單用 `status=backoff` | 清單照 `Supervisor.status` 給 `backoff`；面板要不要另外提示是 HM-11 |
| HM-08 審查第 15.3 節（`claude-delivery` 版筆記） | FD 預算照產品上限算；索引被手改成超過上限時多開的 client 會超出估計：「交 HM-10（建立帳號時本來就擋上限）」 | 建立擋上限（409 `profile_limit_reached`，A `test_a_creation_is_refused_…`）；FD 上限提不到預算、只服務預設帳號時建立也擋（`limit` 0，A `test_no_profile_is_created_while_only_the_default_profile_is_served`，第三個工作階段補的）；手改索引是同 uid（DQ-37），量實際 FD 是 HM-19c |
| HM-09 審查 S-4（R16、R17） | `reevaluate()` 新變 disabled 的帳號要停（R16）、`remove()` 要停該帳號的監看（R17）沒有測試；「或在 HM-10 交接寫成必測」 | HM-09 的 PR（`wave3/pr-HM-09.md`）寫明它的修正線已補這兩個測試，並寫「HM-10 接線後經 API 再測」。R17 經 API 測了：刪除的案例斷言被刪帳號的監看工作已取消、不在管理器的監看表裡（突變 M25 被抓到）。R16 經 API 測不到：HM-10 的 API 沒有一條路會讓帳號「新變 disabled」（建立先擋上限、記憶體與 port，新帳號排在索引最後、不會擠掉前面的；改名不改 disabled；索引隔離是整個停掉） |
| HM-09 審查 S-12 第 2 點 | `start_all`、`reevaluate` 的 `launch()` 不拿 `mutation_lock`，和面板存檔交錯；「HM-10 接線時一起處理」（HM-09 的 PR 也寫「(2) `_relaunch` 拿 `mutation_lock` 交 HM-10」） | 做了：建立後在新帳號自己的鎖裡 `start_profile`（A 的建立案例、突變 M24）；`ProfileRuntime.launch()`（開機與重評）也拿該帳號的鎖（A `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock`、突變 M28）。沒有改 `_relaunch`：存檔與面板重啟是拿著鎖呼叫它的，在它裡面拿會自己鎖死（第 3.4 節） |

| HM-11 審查 S-5（HM-10 開工後才出；審查修正時補列） | (1) 帳號增刪的重送先回收據、再比 If-Match；(2) 探測的 400 `profile_id_required` 不寫 WARNING 以上的 log；(3) 清單列數上限 6、id 不重複 | 三點都已符合（HM-10 審查核對過）：建立、刪除、隔離是「If-Match 格式 → Idempotency-Key 重送 → 才比 ETag」；⑦ 的 400 不寫 log；孤兒放在另一個鍵 `orphans`，不進清單列。DOCS 寫明探測 400 是預期行為：HM-18 |
| HM-11 審查 S-2 第 3 點（審查修正時補列） | Ingress 若拿掉 `ETag`，清單本體另帶版本 | 列進第 11 節待 HM-03a（審查 S-4）；實測不通才在清單本體多帶 `index_etag` |

### 13.2 交給後面的片

- **HM-11（面板）**：開通後每個帳號範圍請求都帶 `X-MCP-Profile`（含 `default`）；比對 bootstrap 與變更兩個回應的回聲；清單的 `orphans`
  （列出可刪）；`profile_index_state:"corrupt"` 時顯示「隔離帳號索引」並送 `profile_index_etag`；刪除與隔離的兩段確認（DQ-14）；
  `profiles_supported:false` 不顯示新增；PATCH、DELETE 一定帶 CSRF（開通後方法表在 identity 之後）；建立的回應沒有 token，要另外 reveal；
  建立重送回目前那一列、帳號已刪時只有 id；`status`、`blocked_reason`、`disabled_reason` 的文字；fixture server 照本片的回應形狀；
  `profile_limit_reached` 的 `limit` 可能是 0（FD 預算不夠、只服務預設帳號）；`corrupt` 時隔離回 409 `config_conflict` 而索引仍是
  `corrupt`，表示沒有索引檔可隔離（`profiles/` 開機時列不出來），提示「修好後重啟 add-on」。審查修正後：隔離可能因為某個帳號的變更
  還拿著鎖而 503（逾時，什麼都沒做），面板照 503 的通用文字提示再試一次即可。清單的索引 ETag 只在回應標頭：Ingress 轉不轉待 HM-03a
  （第 11 節，審查 S-4）；拿不到時怎麼顯示照 HM-11 審查 S-2 的建議。
- **HM-12**：Odoo 換身分換 token（`backend`、`backend/patch` 經分派器，`admin_action` 不變）；A 的審批 token 在 B 被拒。
- **HM-13b**：休眠帳號（沒開通但有資料）的 bootstrap `dormant_profiles`；索引旁收據在還原時的封存（`.profiles.json.operations.json.restored`）
  與 410 `operation_restored`；帳號目錄的隔離名（S-15）；開機守門與本片刪除、隔離的互動（`.revoke-all-pending`）。
- **HM-13c**：全部撤銷、還原紀錄、核對、刪隔離目錄四條全域路由加進 `GLOBAL_ROUTES`（`ProfileAdmin` 加 handler，矩陣自動涵蓋）；
  `token/rotate` 的 409 `restore_review_required`；索引壞時這幾條能不能用（契約暫定：照常可用）。審查修正後要照著做（審查 S-1、MF-1）：
  「全部撤銷」照索引隔離的寫法，先依 id 順序拿每個已登錄額外帳號的鎖（`ProfileAdmin._registered_profiles_locked`），拿完才做 ⑩，撤銷在
  鎖裡；每條新路由的 ⑩ 都要在 `test_the_second_role_check_comes_after_every_wait_and_before_any_change` 多一輪（每一種等待各一輪），
  否定矩陣只守 ⑥。
- **HM-16**：P9 kit 與容器探針的管理請求帶 `X-MCP-Profile`；多帳號的增刪改查與隔離在容器裡跑一次。
- **HM-18**：DOCS 寫刪除與隔離的步驟、S-14 的說明、Ingress 備援沒做的理由；「`profiles/` 開機時列不出來：修好後重啟 add-on（隔離索引
  解決不了）」；FD 預算不夠時不能新增帳號；`tests/contract/profiles_v1_cases.json` 要不要加管理面的資料案例（第 6 節；審查 S-5，
  請主對話確認這個偏離計畫 §10.3 的決定）；計畫 §7.2 的「預設帳號會變的事」清單、各產品 CHANGELOG 與 `upgrade-notes.yaml` 補兩個
  位元組變化：PATCH、DELETE 沒帶 CSRF 從 405 變 403，表外方法（OPTIONS 等）的 `Allow` 從 4 個方法變 6 個（審查 S-6；契約 §3.1 已寫）；
  DOCS 的疑難排解寫明「開面板時瀏覽器 console 有一筆 400 是預期行為」（HM-11 審查 S-5 第 2 點）。契約第 9 節原本沒有 FD 預算這一列：
  審查修正（S-2）已併進 #19，不必再補。
- **HM-25**：n8n 上 `ProfileManager` 時，刪除要清它的 `/tmp/woow-n8n-mcp/profiles/<id>/`（PaaS `profile_deleted` 回呼的 HA 版）；n8n 的
  `ConfigurationState` 也帶帳號 id。
- **獨立安全審查**：做了（第 14 節）。

### 13.3 rebase 時要注意

2026-11-16 已照下面各點 rebase（結果在第 15 節）。

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
- 帳本：rebase 後重算 6 個列管檔與 `profile_admin.py` 的摘要（`SP:hm10/ledger_update.py`、`ledger_update3.py`、審查修正的
  `SP:hm10-fix/ledger_update.py` 的做法：說明不動、摘要照實際內容算），重跑兩個預檢與 CI。
- 審查修正後 A 碰到 HM-09 內部的地方：`monkeypatch.setattr(manager, 'remove', …)` 3 處（原本 `test_a_save_waiting_…` 1 處，審查修正的
  `test_a_deletion_never_writes_over_…`、`test_the_index_quarantine_holds_…` 各 1 處）、`asyncio.Lock._waiters` 2 處（原本 1 處、
  `test_the_index_quarantine_holds_…` 1 處）、`monitor_of()` 1 處。HM-09 修正若改了 `remove()` 的名稱或簽名，改這幾處即可。
- `checks` 秒數：開 PR 後補（第 7 節）。

## 14. 獨立安全審查的意見與處理（第四個工作階段，2026-11-16）

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-10.md`（repo 外；證據在同層 `evidence-review-HM-10/`）。審查對象
  `c094e63`，判定**修正後通過**：必修 1 項（MF-1）、建議 6 項（S-1～S-6）。審查沒有找到非管理員越權、帳號互看 token、秘密進 log 或回應的問題。
- 每一點都先核對過審查的說法：審查的突變（`mutations.py`）照目前的程式改寫後重做；實驗 E1～E4 改寫成本片的測試，在 `c094e63` 與修正後
  各跑一次（第 4.3 節；審查的實驗檔本身沒有放進 repo）。
  審查說的都成立，沒有要反駁的：5 處條文在 `c094e63` 的程式都對、測試都守不住；S-1 的空檔在 `c094e63` 重現得出來（新測試紅）。

| 意見 | 內容（摘要） | 處理 | 證據 |
|---|---|---|---|
| MF-1 (1) | 索引隔離的 ⑩ 沒有測試守住（突變 R03 存活） | 採用。`test_the_second_role_check_comes_after_every_wait_and_before_any_change` 多一輪：壞索引（`replace_index`）＋拿著全 add-on 的帳號鎖送隔離，第一次角色檢查答完後撤銷角色再放鎖 → 403、`tree_of` 不變（索引檔、每個 token、沒有收據）、B 與 C 仍登錄 | R03 改成被抓到（第 4.3 節） |
| MF-1 (2) | 刪除要等完目標帳號的鎖才做 ⑩（R05 存活） | 採用。同一個測試再一輪：拿著 B 的 `mutation_lock` 送刪除 → 403、什麼都沒變 | R05 改成被抓到 |
| MF-1 (3) | 額外帳號 owner-defaults「不管目錄裡有什麼」都 409（R17、R18、R17R18 存活） | 採用（照實驗 E2）。`test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles` 的 B 目錄放 schema 3 fixture、跑 `owner_defaults.apply_legacy_upgrade` 造出標記與復原紀錄；對照組斷言 B 的 state 本來會顯示通知、可以還原；斷言 B 的 bootstrap 沒有 `owner_defaults`、restore 與 dismiss 409 形狀 C、`state.json` 與復原紀錄位元組不變 | R17、R18 改成被抓到 |
| MF-1 (4) | ⑦ 遇到「目錄已不是開啟時那一個」要 503（R21 存活） | 採用（照實驗 E3）。`test_a_profile_scoped_request_names_exactly_one_known_profile` 最後：先確認 B 的 bootstrap 200，再把 B 的目錄搬走、`copytree` 回原名 → bootstrap 與 `token/reveal` 都 503 `{"error":"state unavailable"}`（複本裡的 token 不會被回出去） | R21 改成被抓到 |
| MF-1 (5) | 刪除寫索引一律傳手上的 view（R13 存活） | 採用（照實驗 E4）。新測試 `test_a_deletion_never_writes_over_an_index_changed_meanwhile`：在 `manager.remove` 裡把索引換成同內容的新檔 → 刪除 409 `operation_outcome_unknown`、索引檔的位元組與 inode 都是外改後那一份（沒被覆寫）、B 已撤銷已抹除、不再登錄、目錄還在、預設帳號與 C 的 token 在 8081 都 503、清單 503 `profile_index_corrupt` | R13 改成被抓到 |
| MF-1 筆記 | §6 三列、§13.1 兩列、§4.2 M04 要改 | 採用：§6 的 `owner-defaults`、⑩、§3.3、⑧、§3.6 五列；§13.1 的 HM-00、HM-07 #6、#9 三列；§4.2 M04；§12「契約每一條都指到測試」改寫成審查前不成立、修正後成立 | — |
| MF-1 順手 | 清單的 ⑩（R04 存活）可斷言「一次請求問兩次角色」 | 採用：同一個測試開頭斷言清單一次請求問兩次角色（⑥、⑩） | R04 改成被抓到 |
| MF-1 順手 | R14（建立寫索引改重讀）存活但等價 | 不補：建立在 ⑩ 之後到寫索引之間沒有 await，重讀與手上的 view 一定相同（審查也說不必補） | — |
| S-1 | 索引隔離不拿各額外帳號的 `mutation_lock`：進行中的輪替在隔離撤銷之後寫進新 token，8081 在移除登錄前照樣路由（E1 實證）；If-Match 被繞過；推論：存後端的重起可能在 `aclose()` 之後才 `start()` | 採用。`quarantine()` 在全 add-on 的鎖之後，依 id 順序拿每個已登錄額外帳號的鎖（`_registered_profiles_locked`，每把 2 秒，逾時 503、已拿的放掉），拿完才做 ⑩，撤銷、改名、移除登錄都在鎖裡，放鎖後才 `reevaluate()`。第二輪撤銷因此拿掉（理由見第 3.6 節）。新測試 `test_the_index_quarantine_holds_every_profiles_own_lock`（E1 改寫成斷言安全的行為）：C 的輪替停在最後一次角色檢查時，隔離 0.1 秒拿不到 C 的鎖 → 503、什麼都沒變；再送一次隔離 → 等 C 的鎖（B 的鎖已拿著、什麼都還沒做）→ 輪替放行、200、拿到新 token → 隔離改名索引、在移除 B 的途中：預設帳號 200，B、C 的舊 token 與 C 的新 token 都 401 → 隔離 200，B、C 都撤銷、移除登錄、列成孤兒。⑩ 在拿完各帳號的鎖之後，也在第二次角色檢查的測試多兩輪（拿著 B、C 的鎖送隔離） | `c094e63` 紅、修正後綠（第 4.3 節）；突變 S1a（不拿帳號的鎖）、R24（不撤銷已登錄帳號）、R03b（⑩ 移到帳號的鎖之前）、S1b（移除登錄前就放鎖；第三輪補「移除登錄時鎖還在隔離手上」的斷言後）都被抓到 |
| S-2 | 契約第 9 節少列 4 項和 PaaS 的差異 | 採用，併進既有列（不加新列號，避免和其他片撞號）：(a) `orphans` 鍵 → #51；刪除也收孤兒與讀不到的帳號 → #34；(b) FD 預算 → #19（作者原本要交 HM-18，順手做掉）；(c) 刪目錄前先抹後端欄位 → #34；(d) 本體格式錯固定 400（PaaS pydantic 422）→ #34。PaaS 的說法用 `git -C <paas> show 69ac425:…` 核對過（`routers/profiles.py` 的 `ProfileInput` 與 `list_profiles`、`profiles.py` 的 `delete()`） | 契約 §9、§10 |
| S-3 | §7 的「34 案、29 案」不準；M04 說明不清楚 | 採用：§7 改成實測數字；§4.2 M04 寫清楚是一次拿掉全部 ⑩、單獨拿掉某一條原本抓不到 | — |
| S-4 | 清單的索引 ETag 只在回應標頭；HM-03a 要加量 | 採用前半：第 11 節加「Ingress 轉不轉 `ETag` 回應標頭」。後半（清單本體另帶 `index_etag`）先不做：照 UC-10 同一個原則（標頭先、實測不通才補），不先開一個和 PaaS 不同的欄位，也不讓 HM-11 正在對的回應形狀變動；實測拿不到就補（HM-10 或 HM-11 收尾） | 第 11、13.2 節 |
| S-5 | `tests/contract/profiles_v1_cases.json` 沒擴充，是偏離計畫 §10.3 的決定 | 本片不改：理由同第 6 節（那是 HM-01 只描述 8081 的守門檔；管理面用路由表自動產生的矩陣，多守「新路由沒進表就失敗」）。PR 描述明列「沒做、理由、交 HM-18 決定」，請主對話確認 | 第 6、13.2 節 |
| S-6 | 開通後預設帳號兩個位元組變化沒寫進計畫 §7.2 | 契約 §3.1 寫明兩點（405→403；表外方法的 `Allow` 4→6 個方法）。計畫 §7.2、CHANGELOG、`upgrade-notes.yaml` 本片不改（功能 PR 不寫 CHANGELOG；計畫由主對話維護）：交 HM-18 或升版片，寫進 PR 描述 | 契約 §3.1；第 13.2 節 |

- 給主對話的交接（審查第 8 節）也照做了：rebase（第 13.3 節，多記審查修正碰到 HM-09 內部的地方）、HM-11（第 13.2 節）、HM-13c（全部撤銷
  照隔離拿鎖、每條新路由的 ⑩ 各一輪降權測試）、HM-18（S-5、S-6、DOCS）、HM-03a（第 11 節）。

## 15. rebase 到 HM-14（2026-11-16）

第 1～14 節照 rebase 前寫，裡面的 commit 編號是 rebase 前的（對照見第 15.9 節）；列號沒有變（第 15.3 節）。

### 15.1 範圍

- 第一段：`git fetch origin`（`origin/feat/ha-multiprofile-hm14-20261115`＝`8ff259b`，HM-14 的 PR #103），先開備份分支
  `backup/hm10-before-rebase-20261116`（`c2d22e9`，不 push），`git log --oneline 24d72cc..c2d22e9` 是 16 個，再
  `git rebase --onto 8ff259b 24d72cc feat/ha-multiprofile-hm10-20261115`：只重放本片的 16 個 commit。`24d72cc` 是 HM-09 rebase 之前的實作
  head，不是 `claude-delivery` 的祖先（HM-09 合併前 rebase 過），所以用 `--onto`。
- 新基準帶進來的（`24d72cc..8ff259b`）：HM-08 審查修正（PR #99）、PR #100（`checks` 上限 60 分鐘、`decisions.md` 記 DQ-13／14／30／31／43）、
  HM-09 的最終版（PR #101，含審查修正）、HM-20（PR #102）、HM-14（PR #103，疊在 `269f5a5` 上）。和本片重疊的檔：`Hc/gateway.py`、
  `Hc/profile_router.py`、`Hc/profile_runtime.py`、`Hc/profiles.py`、`tests/multi_profile_runtime.py`、`tests/test_router_passthrough.py`、
  契約、驗收矩陣、帳本。`decisions.md`、`threat-model.md` 本片沒改，就是基準的版本（`decisions.md` 與 `claude-delivery` 逐位元相同）。
- 第二段：主對話 2026-11-16 11:5x 通知 HM-14 已以 PR #103 合併（`claude-delivery`＝`7c6f80c`，merge commit，第二個 parent 是 `8ff259b`）。
  `git diff 8ff259b origin/claude-delivery` 是空的（兩邊的樹都是 `a6f19cf`），`git rebase origin/claude-delivery` 沒有衝突，前後的樹相同
  （`6b3d8a2`）。所以第 15.6～15.8 節的檢查（在第二段之後跑）就是對要 push 的樹跑的。
- `git log origin/claude-delivery..HEAD`：本片 16 個＋rebase 後加的 2 個（契約、本筆記）。

### 15.2 衝突與處理

| rebase 後的 commit（原本） | 衝突 | 處理 |
|---|---|---|
| `7632eaf`（`ad60cd7`） | `gateway.py` 的 `make_apps` 說明尾段：HM-14 加的兩段（閘道收尾；不受開關管的 initialize 錯誤遮罩）與本片加的 HM-10 段 | 兩邊都留，照合併順序 HM-08 → HM-09 → HM-14 → HM-10（說明的結尾 `"""` 移到本片那段之後）。本片那段開頭的「likewise only for a switched-on product」改成「only for a switched-on product, as HM-08's and HM-09's」：前一段現在是 HM-14「not gated」的那段，照原文讀會變成「同樣不受開關管」。簽名 git 自動合併（`slot_busy: SlotBusy \| None`、`child_blocked`、`default_endpoint`、`bootstrap_fields` 都在） |
| 同上 | `profile_router.py` 模組說明「Not here」那句：HM-14 改寫成「the lanes, the -32004/-32005 endings and the initialize generation fence themselves (…; HM-14)」；本片拿掉「the management dispatcher (HM-10)」、加 8099 一段 | 用 HM-14 的句子，拿掉「the management dispatcher (HM-10)」（現在就是本片做的），8099 那段照本片 |
| `53e58a4`（`a18bc73`）、`13bc8a6`（`e707837`） | 帳本 `gateway.py`、`profile_router.py`、`profile_runtime.py`、`profiles.py` 的 `change` 與 `sha256` | 不只解文字：以 HEAD（新基準）的帳本為底，本片每個改到的列，`change` 是新基準的文字接本片原本加的那段（本片只在列尾追加，原文的前段改了也不影響；HM-08 審查、HM-09、HM-14 的說明在前，本片的在後），新列 `profile_admin.py` 照原 commit 放在 HM-09 的 `lifecycle.py` 之後；每個改到的列 `sha256` 照當下的檔案重算（腳本 `SP:hm10-rebase-20261116/bin/merge_ledger.py`；第 15.5 節） |
| `b6542e6`（`537f5bc`） | 契約第 10 節變更紀錄 | 基準的 6 列（HM-09 審查、HM-20、HM-14 四列）在前，本片的列在後 |
| `1906f4a`（`14a08b0`） | 契約三處：第 5 節 FD 一點（HM-08 審查改了下一點）、第 7 節錯開啟動列（HM-09 審查 S-12 在列尾加了一句）、第 10 節本片那列 | FD：本片的句尾（「HM-10：這時建立帳號回 409 `profile_limit_reached`（`limit` 0），什麼都不寫」）接 HM-08 審查改寫的兩點；錯開啟動：HM-09 審查那句在前、本片「每個帳號起子程式時拿它自己的 `mutation_lock`」在後；第 10 節：基準的列不動、本片那列換成新版 |
| 其他 11 個 | 沒有衝突 | 測試 4 個（`a721623`、`fee3ca7`、`7b3c544`、`280803c`）、程式 2 個（`d74b774`、`a673365`）、帳本 1 個（`3b91fdc`：只動 `profile_admin.py` 那列；`profile_admin.py` 只有本片改，摘要和原本相同，照實際內容核對過）、契約與驗收矩陣 2 個（`824e560`、`1517ed5`）、筆記 2 個（`fbb58b0`、`16526b2`） |

核對（`SP:hm10-rebase-20261116/logs/`；第 15.4 節的契約 commit 之前）：15 個檔逐一比「本片的改動」（`git diff 24d72cc c2d22e9` 對 `git diff 8ff259b HEAD` 的增刪行）：11 個逐行相同；
`gateway.py` 只差說明結尾那兩行（`"""` 的位置、likewise）、`profile_router.py` 只差「Not here」那句、契約只差錯開啟動那一列（多了 HM-09 審查那句）、
帳本只差上面說的文字與摘要。程式的改動（含 `launch()` 拿鎖、`open()` 的 `files_for_extras`）全部是 git 自動合併、逐行等於原本；
`profile_admin.Registry` 用到的 `ProfileManager` 介面在 HM-09 最終版都還在、簽名沒變，不用改。

### 15.3 列號

- **本片在契約第 9 節沒有新列**：審查 S-2 時刻意把 PaaS 差異併進既有的 #19、#34、#51（#27 是 DQ-13 定案的更新），不另開列號（第 14 節）。
  rebase 前是 86 列（本片沒加），rebase 後是 100 列：第 87～88 列（HM-08 審查）、第 89 列（HM-09 審查）、第 90 列（HM-20）、第 91～100 列
  （HM-14）都接在 HM-00 的 86 列之後，本片引用的列沒有移動，所以列號與引用都不用改，commit 訊息裡的列號也都還對。
- 新舊對照（本片改到或引用的第 9 節列）：

| 列 | rebase 前 | rebase 後 | 內容 | 本片怎麼用 |
|---|---|---|---|---|
| #19 | #19 | #19 | 容量檢查 | 改：FD 預算、`available_memory_mib`（rebase 後補「（#87）」，見第 15.4 節） |
| #27 | #27 | #27 | endpoint | 改：DQ-13 已定、額外帳號 409 `endpoint_global` |
| #34 | #34 | #34 | 帳號 CRUD 寫入保護 | 改：刪除範圍、先抹後端欄位、格式錯 400 |
| #51 | #51 | #51 | 帳號清單欄位 | 改：`orphans` |
| #11、#12、#25、#29、#31、#32、#35、#80、#83 | 同 | 同 | 管理身分、管理管線、索引壞、日誌、沒帶帳號、格式錯、名稱、`set_token`、兩個標頭 | 只引用 |
| #75 | #75 | #75 | CI | rebase 後順手改：上限 60 分鐘（第 15.4 節） |

- 「#99」「#100」在本筆記第 1～14 節是 PR 編號（HM-08 審查修正、`checks` 上限）；rebase 後契約第 9 節也有第 99、100 列（HM-14），
  所以本節與契約新寫的地方都寫成「PR #99」「PR #100」。

### 15.4 rebase 後補的修正（`b51cf8c`，只改契約）

- 第 10 節加一列（rebase 到 HM-14 之後）。
- #19：FD 預算指到 #87（HM-08 審查補的「FD 上限不夠」列；本片寫 #19 時基準還沒有這一列，兩列說的是同一條降級，本片那句只多「建立回 409、`limit` 0」）。
- 第 3.3 節：「目錄已不是開啟時那一個」指到 #88（同一個 HM-08 審查補的 8081 那一側）。
- #75：「上限 40 分鐘」「DQ-43 待定」改成「上限 60 分鐘（DQ-43，2026-11-15 定案，PR #100）」與「DQ-43：先調上限，拆 job 等真的太慢再議」
  （`decisions.md` 的 DQ-43；`.github/workflows/woow-addon-release.yml` 的 `checks` 是 `timeout-minutes: 60`）。
- 第 10 節 HM-10 列的「`decisions.md` 由 #100 記」寫明是 PR #100。

### 15.5 帳本（`docs/provenance/runtime-patches.json`）

以新基準的帳本為底（60 列）加回本片：61 列。每列的 `sha256` 照 rebase 後的實際內容重算；`change` 是新基準的文字接本片的那段；JSON 照 repo
的寫法（`indent=2`、`ensure_ascii=False`）逐位元可重現；其他 54 列和新基準逐位元相同（`SP:hm10-rebase-20261116/logs/ledger-verify.log`）。

| 列管檔 | 本片 rebase 前（`c2d22e9`） | 新基準（`8ff259b`） | rebase 後 | 說明 |
|---|---|---|---|---|
| `gateway.py` | `103957dc3a6c` | `9111302d86f2` | `f6cf0fda2611` | 新的值（兩邊都改了）；`change` 19,154＋970 字 |
| `profile_router.py` | `1f5b1656f8f2` | `6eaa597f53d3` | `97ec58644e93` | 新的值；4,371＋662 字 |
| `profile_runtime.py` | `06fab115f81a` | `b8ebbad0e2cb` | `c449a991c1d7` | 新的值；4,877＋720 字 |
| `profiles.py` | `39a44531ca5a` | `d17bfc3fa32f` | `55dcc665fa28` | 新的值；3,947＋391 字 |
| `configuration.py` | `678fbc3dff18` | `5e1ee5bde771` | `678fbc3dff18` | 只有本片改，和 rebase 前相同；677＋309 字 |
| `operations.py` | `85456d10615f` | `7bc5c0c6cc4c` | `85456d10615f` | 只有本片改，和 rebase 前相同；448＋348 字 |
| `profile_admin.py`（新列） | `f3ef30819da3` | — | `f3ef30819da3` | 只有本片改；原 commit 的列，放在 `lifecycle.py` 之後 |

本片沒動 `apps/runtime/*.py`、`apps/*/launch.py`，tool-surface 不用重產（`scripts/tool_inventory.py` exit 0，第 15.6 節）。

### 15.6 本機檢查（2026-11-16，一般使用者 uid 1000；TMPDIR 用 ha_env.sh 給的 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪除；pytest 都排在共用鎖後面）

證據在 repo 外：`SP:hm10-rebase-20261116/`（`bin/` 腳本、`logs/` 的 pytest log 與 junit、突變結果、SHA-256 核對），副本（遮掉測試時產生的
token）在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-rebase-HM-10/`。全部在一次共用鎖裡跑（`bin/batch1.sh`，12:17～12:57），
head 是第二段之後的 `b51cf8c`（樹和第一段的 `5999d24` 相同）。

| 檢查 | 指令（摘要） | 結果 |
|---|---|---|
| 環境 | clone 的依賴、patch、UI 已由前面的工作階段照 `setup_repo_env.sh` 裝好；`24d72cc..7c6f80c` 沒有動任何 `uv.lock`、`package-lock.json`、`pyproject.toml`、`packaging/inputs.json`、`packages/mcp-admin-ui/`，所以沒有重跑（不連 npm）；Playwright 的 Chromium（`chromium-1228`）在 clone 裡，瀏覽器測試照跑 | — |
| 本片 3 檔 | `pytest tests/test_profile_admin_api.py tests/test_admin_pipeline_matrix.py tests/test_router_passthrough.py` | **86 案全過**、0 skip，17.4 秒（A 32、M 5、P 49） |
| HM-01 黃金回歸＋兩個契約凍結（開關關） | `test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py` | **45 案全過**（17＋9＋19），6.9 秒；三檔與 `tests/contract/` 本片沒動 |
| HM-14 新 5 檔＋`test_reply_mask_union.py` | `test_carries_no_request.py`、`test_gateway_busy_shapes.py`、`test_gateway_queue_ha.py`、`test_gateway_stream_endings.py`、`test_initialize_generation.py` | **143 案全過**（61＋7＋23＋35＋9＋8），18.8 秒 |
| HM-20 兩檔 | `test_backend_loopback.py`、`test_saved_destinations.py` | **243 案全過**（153＋90），65.6 秒 |
| HM-09 五檔 | `test_profile_lifecycle.py`、`test_staggered_start.py`、`test_profile_ports.py`、`test_health_backoff.py`、`test_extra_child_resources.py` | **119 案全過**（28＋9＋29＋41＋12），27.3 秒 |
| 審查用的相關 29 檔裡其他 24 檔 | `evidence-review-HM-10/scripts/batch_a.sh` A3 的清單去掉上一列的 5 檔（含讀帳本的 `test_tool_inventory.py`、`test_ledger_precheck.py`） | **1,027 案全過**，86.0 秒（29 檔合計 1,146 案；審查時在舊基準上是 1,127 案） |
| `packaging/validate.py` | `SP:ha-baseline/ci-venv/bin/python packaging/validate.py` | PASS |
| packaging unittest | 照 CI：離線暫存 venv（`uv sync --frozen --no-dev --offline`＋`requirements-ci`）→ `unittest discover -s packaging` | `Ran 203`、`OK (skipped=5)`（5 個 `skipUnless(root)`；HM-20 多 2 案） |
| tool-surface 漂移 | `.venv/bin/python scripts/tool_inventory.py` | exit 0 |
| 全套 pytest | `.venv/bin/python -m pytest -q -p no:cacheprovider tests`（同 `packaging/unit.sh`，只是不用 root） | **5,780 案：5,773 過、7 失敗、0 skip**，1,937.8 秒（32 分 17 秒）。7 個失敗正是第 7 節那 7 個要 root 的；HM-14 筆記寫的 22 個瀏覽器測試（`test_owned_browser_redirect.py` 16、`test_owned_browser_ipc.py` 的 browser=True 5、`test_owned_ui.py` 1）都過；2 個 warning 是既有的 `websockets` 棄用提示 |
| 已知的 HM-09 關閉逾時 | `test_backend_loopback.py::test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end[False]` | 本機跑 2 次（HM-20 兩檔一次、全套一次），**2 次都過**（約 4.5 秒），沒有碰到 CLOSE_SECONDS 逾時。本片不修（另一條工作線在修） |
| 實驗（不 commit） | `SP:hm10-rebase-20261116/bin/test_zz_hm10_rebase_experiment.py`：經 `POST /api/profiles` 建的帳號，它的 `SlotBusy`（佇列上限 16、保留 4、等 1 秒）、兩條 lane（16＋4，不是預設帳號或 B 的）、佇列滿的回答（200＋`-32003`＋自己的文字）與 WARNING 都是它自己的 | 第一次跑（B0）失敗，是實驗自己的錯：斷言「只有一行 WARNING」太嚴，同一個帳號另有 HM-09 生命週期的「not started: no connection is saved yet」那一行。改成只數閘道的 WARNING 後，在乾淨的樹上通過（突變 X0），X3 下失敗。只為了突變 X3 跑，跑完就從 `tests/` 刪掉 |
| 正式程式的 SHA-256 | `sha256sum packages/mcp-admin-core/mcp_admin_core/*.py`：跑前、全套後、突變後 | 三次相同（`logs/core-sha256-*.txt`） |
| 暫存目錄 | ha_env.sh 給的 `/tmp/ha-mp-MrWgMu` | 跑完用完整路徑刪除（`logs/tmpdirs.txt`）；`git status` 只有還沒 commit 的本筆記 |

### 15.7 突變（rebase 後）

腳本 `SP:hm10-rebase-20261116/bin/mutate.py`：每個只改正式程式一處（原字串剛好出現一次、改完可編譯），在工作樹原地改，跑指定的測試檔
（`--maxfail=25`），跑完從先存的位元組還原；還原後的 SHA-256 要同時等於改之前與 HEAD 的 blob，不等就停。挑的是 rebase 時手動合或緊鄰手動合
的地方。**6 個全部抓到**，還原全部 OK。

| id | 位置 | 突變 | 結果 | 抓到它的測試 |
|---|---|---|---|---|
| X0 | — | 沒改（實驗在乾淨的樹上） | 通過（對照） | — |
| X1 | `profile_runtime.py` `ProfileRuntime.launch()`：本片的帳號鎖，緊鄰 HM-09 最終版 `start_all` 的 S-12 修正 | 開機與重評起子程式不拿帳號的 `mutation_lock` | 抓到 | A `test_a_start_after_an_index_change_waits_for_the_profiles_own_lock` |
| X2 | `profile_router.py` `AdminDispatcher.profile`：8099 的必帶標頭（這個檔的模組說明在 rebase 時手動合） | 沒帶 `X-MCP-Profile` 退回預設帳號 | 抓到 | A `test_a_profile_scoped_request_names_exactly_one_known_profile` |
| X3 | `profile_runtime.py` `ProfileManager.add`：本片的回聲、bootstrap 欄位、`default_endpoint` 與 HM-14 的 `slot_busy=gate.slot_busy` 在同一個呼叫；開機登錄與經 profiles 路由建的帳號都走它 | 額外帳號不給 `SlotBusy`（沒有 HM-14 的 lane 與佇列） | 抓到（10 案） | 實驗；`test_gateway_queue_ha.py` 6 案（例如 `test_the_queue_is_capped_per_profile_and_the_overflow_gets_a_clean_busy_answer`、`test_one_profiles_full_queue_never_refuses_another_profiles_waiting_request` 兩種）；`test_gateway_busy_shapes.py` 3 案。本片的 A 32 案都過：本片沒有「經 API 建帳號後測佇列」的測試，這一點靠 HM-14 的測試守（同一個 `add()`），實驗補的是經 API 建的帳號那一側 |
| X4 | `profile_runtime.py` `start_all` 的 `one()`：HM-09 最終版審查 S-12（它呼叫的 `launch()` 本片加了鎖） | 拿掉每個帳號各自攔例外（起不來的帳號不記一行、監看不起） | 抓到 | `test_staggered_start.py::test_a_start_that_fails_is_named_and_never_stops_the_others` |
| X5 | `profiles.py` `port_occupied`：HM-09 最終版審查 S-6（兩邊都改了這個檔，git 自動合併） | IPv6 試綁被平台擋（EACCES、EPERM）又算 port 被佔（PaaS 的做法） | 抓到 | `test_profile_ports.py::test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning`［EACCES］［EPERM］ |
| X6 | `gateway.py` `make_apps` 的 `endpoint_global`：本片（`make_apps` 的說明在 rebase 時手動合；參數和 HM-09 的 `child_blocked`、HM-14 的 `slot_busy` 一起） | 額外帳號的 `PUT endpoint` 照存 | 抓到 | A `test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles` |

還原後的 SHA-256（= HEAD 的 blob = 帳本第 15.5 節）：

- `profile_runtime.py`（X0、X1、X3、X4）：`c449a991c1d725f41435a5d14f68f1568a2888edd9c3671f36601549c543e0f5`
- `profile_router.py`（X2）：`97ec58644e938ea2b0536969d424940968f512dc8c09efe2511a4edecc9c6be1`
- `profiles.py`（X5）：`55dcc665fa28c3b7591c848a7de334a89af0983ced95e6d4742d068bb784e797`
- `gateway.py`（X6）：`f6cf0fda2611977f937756a339ca47cbf5c13fbdf9380996c49574cad76d2831`

結果檔：`SP:hm10-rebase-20261116/logs/mutations.json`、每個突變的 `mut-<id>.log`／`.xml`。

### 15.8 預檢

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢（第一段） | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 8ff259b --head 5999d24 --full` | gitleaks 8.28.0（釘版、已驗）；`8ff259b..5999d24` 17 個 commit，另掃 HEAD 樹與全部歷史：**0 命中** |
| 帳本預檢（第一段） | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 8ff259b` | `runtime-patches.json` 174、`runtime-sources.json` 70、`tool-surface.json` 159 筆：0 漂移、0 缺；改到的 7 個列管檔都在帳本；沒有沒列管的新執行檔：**OK** |
| 秘密預檢（第二段，commit 本筆記之前） | 同上，`--base origin/claude-delivery --head HEAD`（`b51cf8c`） | `7c6f80c..b51cf8c` 17 個 commit＋HEAD 樹＋全部歷史：**0 命中** |
| 帳本預檢（第二段，commit 本筆記之前） | 同上，`--base origin/claude-delivery` | 同第一段：**OK** |

另用 sha256 逐一核對帳本 61 列的實際內容（`logs/ledger-verify.log`）：全部一致。commit 本筆記之後，對最終 head 再跑一次兩個預檢；結果寫在 PR 描述
（`artifacts/ha-multiprofile-parity-20261114/wave4/pr-HM-10.md`）。

### 15.9 commit 對照

| 原本 | 第一段（基準 `8ff259b`） | 第二段（基準 `7c6f80c`） | 內容 |
|---|---|---|---|
| `c265941` | `fec73ed` | `a721623` | 測試（新 2 檔、測試工具） |
| `ad60cd7` | `013a7f7` | `7632eaf` | 程式 |
| `a18bc73` | `4da1562` | `53e58a4` | 帳本 |
| `537f5bc` | `eba9710` | `b6542e6` | 契約 |
| `eec12f7` | `6415a6f` | `fee3ca7` | 測試（帳號鎖、FD 預算、沒有索引檔） |
| `ae590e8` | `f1621ed` | `d74b774` | 程式（同上） |
| `e707837` | `12434c7` | `13bc8a6` | 帳本 |
| `14a08b0` | `7f57dfb` | `1906f4a` | 契約 |
| `bc37ac7` | `b7b3fcf` | `824e560` | 驗收矩陣 T-12 |
| `47d03dd` | `b33db1a` | `7b3c544` | 測試（刪不乾淨的孤兒） |
| `c094e63` | `c9b0ccb` | `fbb58b0` | 本筆記（審查對象） |
| `c26e9dd` | `0ee5514` | `280803c` | 審查修正的測試 |
| `56dd5fc` | `f0205a9` | `a673365` | 審查修正的程式（S-1） |
| `30473de` | `6cc7995` | `3b91fdc` | 審查修正的帳本 |
| `bbb24bc` | `5d764b3` | `1517ed5` | 審查修正的契約 |
| `c2d22e9` | `a810ec7` | `16526b2` | 本筆記（審查修正） |
| — | `5999d24` | `b51cf8c` | rebase 後：契約（第 15.4 節） |
| — | — | 本筆記的 commit | 第 15 節；結論、第 1 節、第 7、8、13.3 節的指引 |

備份分支 `backup/hm10-before-rebase-20261116` 留在本機（`c2d22e9`），沒有 push。
