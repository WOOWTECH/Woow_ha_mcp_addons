# HA 多帳號 HM-05 provenance：每帳號執行套件（行為不變）（2026-11-15；審查後、rebase 後更新）

## 結論

- 新增 `Hc/profile_runtime.py`：`ProfileRuntime` 是一個帳號的執行套件（`make_apps` 的兩個 app、這個帳號的子程式與
  lifecycle 參數、port、子程式的 httpx client、`HealthMonitor`、`ConfigurationState`、`TokenAccess`、mutation lock）；
  `SharedAdmin` 裝全 add-on 共用的管理物件（一份 `AdminAuthority`、16 個管理名額、共用管線）。
- `Hc/run_product.py` 改用 `ProfileRuntime` 建預設帳號。這一片只有預設帳號用它，而且不給共用管理物件、不給帳號回聲；
  `apps/n8n/run.py` 不動（計畫 §12.2 衝突表：HM-25）。
- `gateway.make_apps` 只加 6 個 keyword-only 參數：`authority`、`admin_slots`、`admin_pipeline`、`token_access`、
  `mutation_lock`、`profile_view`。給了才驗證（不合法就 `ValueError`）；不給時照舊在函式裡建立，行為逐位元相同。
- 預設帳號的行為逐位元不變：HM-01 的黃金回歸與兩個契約凍結全過，斷言一個字都沒改；只把 `production_runtime` 的兩行
  patch 改到 `profile_runtime`（多一個 `profile` 變數與一個 import），檔頭說明這兩個注入點的文字跟著改。
- 既有測試只改替身的注入點：5 個檔的 `Supervisor`、`HealthMonitor`、`make_apps`、子程式 client 從 `run_product` 改到
  `profile_runtime`，替身本身與斷言沒改。
- 啟動預設帳號前後 `/data/mcp` 不新增任何檔：寫了測試鎖住（八個產品×新裝與已設定，16 案；改之前就成立，改完照過）。
- 新測試 `tests/test_profile_runtime.py` 65 案（審查前 63 案、審查後補 2 案）。先紅後綠（審查前的 63 案）：改程式前 20 通過
  （兩個「今天就成立」的鎖）、43 失敗；改完 63 全過、0 skip。31 個臨時突變：先寫的測試擋下 29 個；沒擋下的 2 個（P14、R2）
  補測試後都擋下（第 4.3 節）。審查的 15 個突變有 5 個沒被擋：補的 2 案擋下其中 3 個（ME2、ME3、ME7）；另 2 個（ME6、MD2）
  照審查建議交給 HM-08、HM-10（第 4.4 節）。
- 獨立審查判定通過：必修 0 項；建議 5 項都處理了（第 13 節）。S-1、S-2(a) 補測試；S-2(b)、S-3、S-5 改說明，交給 HM-08、
  HM-10、HM-25；S-4 補上計畫 §11.5 的發版規定。
- **合併後的發版（計畫 §11.5）**：本片合併後，任何產品的發版都要走完整既有流程，不能只看單帳號黃金回歸（第 11 節）。
- rebase（2026-11-15，第 14 節）：從舊 HM-04 分支 head `9f1e35e` 移到 `claude-delivery` `9c5dd88`（含 HM-00 #89、HM-01 #90、
  HM-04 #91、HM-17 #92、HM-07 #93、HM-06 #94）。本片 5 個 commit 重放，**沒有衝突**：`claude-delivery` 在 `9f1e35e` 之後沒有動
  `gateway.py`、`run_product.py` 與本片改的 5 個既有測試檔，本片的檔 rebase 前後內容逐位元相同。帳本沒有只信自動合併：以
  `claude-delivery` 的帳本為底，加回本片 3 筆（`gateway.py`、`run_product.py` 的說明，新的 `profile_runtime.py`），55 個列管檔的
  SHA-256 全部用合併後的實際內容重算，結果和自動合併的帳本逐筆相同。tool-surface 重產 0 差異。`test_upgrade_zero_rewrite.py`
  的 `UNWIRED` 清單不用改（`profile_runtime.py` 沒有 import `profiles`、`features`、`identity_fields`）。
- 本機檢查（rebase 後，第 5.3 節）：目標 35 檔 1720 案、0 skip：1718 通過，2 個失敗都是已知要 root 的案例（HM-01 前就有的 1 個、
  HM-07 的 1 個；只在 CI 驗）。其中本片 65 案、HM-01 守門 97 案、本片改過注入點的 4 檔、HM-04 的 `test_child_port_param.py` 233 案、
  HM-06 的 `test_child_bearer.py` 28 案、HM-07 的 250 案（要 root 的 1 案除外）都過；起真子程式的 `test_role_lifecycle.py`、
  `test_real_products.py`、`test_unconfigured_connect.py`、`test_runtime_failure.py`、`test_real_n8n.py` 也都過。packaging unittest
  `Ran 194`、`OK (skipped=5)`；`validate.py` PASS。全套 pytest 以 CI 為準。
- 兩個預檢（rebase 後的最終 HEAD，含本筆記這一版）：秘密預檢 0 命中（本片 6 個 commit；`--full` 的 HEAD 全檔與全歷史也 0）；
  帳本預檢 OK（168／70／159 個摘要 0 漂移、0 缺檔；改 11 個檔，列管檔 3 個與帳本同步；沒有新增而沒列管的執行期檔）（第 8 節）。
- rebase 前（開發與審查時）的本機全套 pytest：4057 案：4034 通過、23 失敗、0 skip，28 分 19 秒（`e089210`）。22 個失敗是這個 clone 沒有 Playwright 的 Chromium
  （`browserType.launch` 找不到執行檔；HM-04 同一批）：把本機既有、同版（Playwright 1.61.1、chromium-headless-shell 1228）的
  瀏覽器複製進 clone 的 `node_modules`（git 忽略；沒有下載）後，這 3 個檔重跑 52 案全過、`check_results.py` PASS；
  剩下 1 個是已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`。審查員在 `161cb04` 重跑全套：4057 案，
  4056 通過、只剩同一個要 root 的案例、0 skip。審查後只改 `tests/test_profile_runtime.py` 與本筆記，重跑受影響的檢查
  （第 5.1 節），全套沒有重跑。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-05（計畫 §3.2、§5.3、§12.3；風險高、工作量 M）。不受開關管（契約 §1.2；計畫 §3.3 的保證方式是「HM-01 逐位元」） |
| 分支 | `feat/ha-multiprofile-hm05-20261114`（rebase 後 push、開 PR；本片不合併） |
| 基準 | `claude-delivery` `9c5dd88`（#94 HM-06 的合併；含 #89 HM-00、#90 HM-01、#91 HM-04、#92 HM-17、#93 HM-07）。開發與審查時的基準是舊 HM-04 分支 head `9f1e35e`（`bb48449`＋HM-01＋HM-04，當時都還沒合併）；2026-11-15 rebase（第 14 節）。rebase 後本分支也含 #90 合併前補的 `ledger_precheck.py` 修正 `1281abe` |
| 依據 | 計畫 §3.2、§5.3、§12.0、§12.2 衝突表、§12.3 HM-05；HM-00 契約 §1.2、§3.2、§3.4、§3.5；`ledger-tracking.md`；`acceptance-matrix.md`（`tests/test_profile_runtime.py` 一列）；`paas-test-mapping.md` 指給本片的 7 案；`deviation-trace.md` 的 FM-06、FM-37、FM-54、T-16、T-18 |
| 對齊的 PaaS | pin `69ac425`。本片沒有移植 PaaS 程式或測試；對應的是 PaaS 的每帳號 `McpProcessManager` 與 `ProfileRegistry`（`Pc/profiles.py`、`Pc/process.py`），HA 用自己的 `make_apps`、`Supervisor`、`HealthMonitor`。到 main `cf3d0d5` 的變動見第 9 節（本片相關的 PaaS 檔沒有改動） |
| FM | FM-06、32、33、37、47、54、65、76 |
| 決策 | 第 12 節 |
| 審查 | 獨立審查 2026-11-15（審 `161cb04`，rebase 後是 `49705fd`）：判定通過；必修 0、建議 5（S-1～S-5），處理見第 13 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/profile_runtime.py`（新） | `ProfileRuntime(store, tools, child_spec, *, port, profile_id, lifecycle, shared, profile_view, app_options)`：`open()`／`aclose()`（或 `async with`）建與收：`Supervisor(None, **lifecycle)`、子程式 httpx client（`CHILD_CONNECTIONS`＝40）、`HealthMonitor`（`child_url` 由 port 組出）、`ConfigurationState`、`TokenAccess`、`asyncio.Lock`、`make_apps` 的兩個 app；`backend_changed(state)`（先停舊子程式、再用新 state 組 spec、再起）；`launch()`（起始的 `backend_changed`，失敗不往外丟）；`monitor()`（健康監看迴圈）。`profile_id` 只收 `default` 或 24 位小寫 hex，port 用 `lifecycle.child_url()` 驗；`app_options` 不能出現執行套件自己給的參數。`SharedAdmin(authority, slots, pipeline)`。借用 store，不寫任何自己的檔 |
| `Hc/gateway.py` | `make_apps` 加 6 個 keyword-only 參數（第 3.3 節）；`ADMIN_SLOTS = 16`（取代原本的字面值 16）；`PROFILE_ID`；型別別名 `AdminPipeline`；`profile_echo(view)`（驗證帳號回聲的形狀）；`admin_page` 尾端：沒有 `admin_pipeline` 時照舊呼叫 `admin_api`，有就交給管線；`profile_action`、`echoed()` 只在給了 `profile_view` 時加回聲 |
| `Hc/run_product.py` | `run()` 用 `ProfileRuntime` 建預設帳號：先驗子程式 port（和改之前一樣在 legacy 遷移之前），遷移、開 store、裝 signal handler，`async with ProfileRuntime(...)` 裡建 listener、裝紀錄遮罩、`launch()`、跑 listener 與監看；收尾 client 先關、再停子程式、最後關 store、拆 signal handler。產品專屬的 `make_apps` 參數（`verify_admin=make_ha_admin_verifier()`、`management`、`server_name`、`instructions`、`listing`、`secret_path_allowed_origins`）原樣留在這裡 |
| `tests/test_profile_runtime.py`（新） | 第 4 節 |
| `tests/test_single_profile_golden.py` | 只改 `production_runtime` 的注入點：`Supervisor` 與 `httpx.AsyncClient` 改 patch 在 `profile_runtime`（n8n 照舊在 `apps/n8n/run.py`）；檔頭說明這兩個注入點的文字跟著改（HM-01 的檔頭本來就寫「HM-05 may move these lines when the names they patch move」）。斷言、常數、摘要一個字都沒改 |
| `tests/test_product_ha_role.py`、`tests/test_product_runtime_failure.py`、`tests/test_role_lifecycle.py`、`tests/owned_executable.py` | 只改替身的注入點：`Supervisor`、`HealthMonitor`、`make_apps`、`httpx.AsyncClient` 改 patch 在 `profile_runtime`；`child_spec`、`Listener`、`ProductStore`、`make_ha_admin_verifier` 仍在 `run_product`。`owned_executable.install_runner` 對 `run_product` 改 patch `profile_runtime`，對 n8n 與 `SimpleNamespace` 照舊 |
| `docs/provenance/runtime-patches.json` | 新增 `profile_runtime.py`（照 `ledger-tracking.md` 由建立它的片列管，放在 `run_product.py` 後面）；`gateway.py`、`run_product.py` 更新 `sha256` 並在 `change` 補 HM-05 的說明。rebase 後以 `claude-delivery` 的帳本為底，只加回這 3 筆，摘要全部用合併後的內容重算（第 14 節） |
| `docs/provenance/ha-multiprofile-HM-05-20261114.md` | 本筆記 |

沒改：版號、`addons/<x>/`、CHANGELOG、`upgrade-notes.yaml`、`packaging/`、workflow、UI、`apps/`（含 `apps/n8n/run.py`）、
`tests/conftest.py`、`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`apps/*/launch.py`，`scripts/tool_inventory.py` 漂移檢查照過）、
`docs/multi-profile/`（開發時本分支沒有；rebase 後有 HM-00 起的這些文件，本片沒改）。HM-01 的守門檔除了 `test_single_profile_golden.py` 的注入點以外都沒動
（`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、`tests/contract/*.json`、`log_scan.py`、`owned_runtime.py`、
`owned_child.py`、`owned_network.py`、兩個預檢腳本與它們的測試：rebase 前 `git diff 9f1e35e HEAD`、rebase 後
`git diff origin/claude-delivery HEAD` 對這些檔都是空的；`tests/test_owned_ports_bearer.py`、`tests/conftest.py` 也是）。
`acceptance/real_backends/ha_runtime.py` 也 patch `run_product.make_apps`，但它跑的是釘在 `28b8317`（0.4.6）的已發佈映像
（README：source proof 對的是凍結的 commit），本片不影響也不改它。

## 3. 設計理由

### 3.1 執行套件放什麼

- 照計畫 §3.2「每帳號一份」：ProductStore（借用）、Supervisor 與子程式輸出緩衝、HealthMonitor 與自己的 httpx client、
  ConfigurationState（ETag 金鑰與套用狀態）、TokenAccess、mutation lock、自答 session、轉送名額、收據（後三者仍在
  `make_apps` 裡，每份一套；收據每帳號一份有測試，轉送名額每帳號一份還沒有，交 HM-08，第 11 節）。「全 add-on 共用」的
  AdminAuthority、CSRF 金鑰、角色查詢器、管理名額、共用管線從外面給（`SharedAdmin`）。
- **TokenAccess 與 mutation lock 由執行套件建、傳給 `make_apps`**（計畫寫「外部建立」）：之後的片要拿得到它們
  （HM-10 刪帳號先撤銷再 `committed()`、拿目標帳號的鎖；HM-13b 全部撤銷），不必再改 `make_apps`。預設帳號也照這樣傳，
  兩個物件的行為和 `make_apps` 自己建的一樣。
- **借用 store**：預設帳號的 store 要在 legacy 遷移之後才開（計畫 §5.4 啟動順序），額外帳號的 store 在 HM-07 是「只開既有」；
  誰開誰關最單純。執行套件不關 store，`run()` 照舊在最後關。
- **lifecycle**：`Supervisor` 的 keyword 參數原樣傳過去；預設帳號不給，所以仍是 `Supervisor(None)`（`owned_executable` 的替身
  也照舊斷言沒有 keyword）。HM-09 的看門狗參數從這裡進來。
- **child spec 由產品給**（`products.child_spec` 或 `n8n_adapter.child_spec`）：測試用八個產品的 `child_spec(state, directory, port)`
  各建兩套（計畫風險 19：介面一開始就用八個產品驗）。

### 3.2 預設帳號為什麼不給共用物件、不給回聲

驗收要「不給這些參數時，行為和今天逐位元相同」，而且這一片只有預設帳號。只有一個帳號時，共用與不共用的結果一樣，
但 `make_apps` 收到的參數越接近原本，逐位元的理由越直接：預設帳號只多傳 `token_access` 與 `mutation_lock`
（`test_run_product_serves_the_default_profiles_runtime` 鎖住：沒有 `authority`、`admin_slots`、`admin_pipeline`、`profile_view`）。
共用物件由 HM-08／HM-10 接線。

### 3.3 `make_apps` 的 6 個參數

| 參數 | 給了的意思 | 驗證 |
|---|---|---|
| `authority` | 全 add-on 一份 `AdminAuthority`：一把 CSRF 金鑰、一個角色驗證器（所以一個並行上限）。identity、兩次角色檢查都用它 | 不是 `AdminAuthority` 或 `verify_admin` 同時給了卻不是它的 verifier → `ValueError` |
| `admin_slots` | 全 add-on 一份管理名額（`ADMIN_SLOTS`＝16） | 不是 `asyncio.Semaphore` → `ValueError` |
| `admin_pipeline` | 共用管線的注入點：通過頁面檢查的每個管理請求改交 `admin_pipeline(request, action)`，由它負責 identity、名額、讀 body、斷線監看；要讓這個帳號動作時呼叫 `action(request, user, base, csrf, value, peer_disconnected, committed)`：`profile_action`，也就是原本的 `admin_action`（鎖、依 state 驗證、最後一次角色檢查、If-Match、收據、提交），給了 `profile_view` 時再加上回聲 | 不可呼叫 → `ValueError` |
| `token_access` | 這個 store 的 `TokenAccess`（執行套件建的） | 不是 `TokenAccess` 或屬於別的 store → `ValueError` |
| `mutation_lock` | 這個帳號的鎖 | 不是 `asyncio.Lock` → `ValueError` |
| `profile_view` | 帳號回聲（DQ-40 ②）：每次回答時呼叫，回 `{"id","label","is_default"}` | 不可呼叫，或形狀不對（鍵集合、id 格式、label 空、`is_default` 和 id 不一致）→ `ValueError`；建構時先呼叫一次驗 |

- **角色驗證器**：計畫列的「共用的角色驗證器」沿用既有的 `verify_admin` 參數；共用時由 `authority` 帶著（它的 verifier）。
  同時給兩個不同的 verifier 會變成兩個並行上限，所以拒絕。
- **共用管線只開注入點**：計畫把「從 `admin_api`／`admin_action` 抽出共用管線（兩次角色檢查）」排在 HM-10。本片不搬
  `admin_api`，只讓 `make_apps` 收一個管線；沒給時 `admin_api` 一行都沒改。
- **帳號回聲的範圍（暫定，HM-10 依契約 §3.4 定案）**：bootstrap 加 `profile`（id、label、is_default）與
  `profiles_supported: true`；帳號動作的其他 JSON 回答加 `profile: {"id"}`（含帳號動作自己回的 409 `config_conflict`
  這類 JSON 回答）。不加的有兩種：(1) 以例外拒絕的回答（403、428、400 等，由 `error_handler` 回），(2) 共用管線自己給的回答。
  理由：帳號動作的回答全都在最後一次角色檢查之後（`admin_action` 先 `final_role` 才回任何 JSON），所以非管理員拿不到
  帳號 id（I10）；管線的回答可能在角色檢查之前，所以一律不加（`profile_action` 只包帳號動作）。
- **HMAC domain 加帳號 id 不在本片**：契約 §3.5 寫「HMAC domain 加帳號 id」，屬 DQ-15 的細節（待定，負責片 HM-10）；計畫 HM-10
  的「做法」也列了 `Hc/configuration.py`。本片沒有改 `configuration.py`。跨帳號 ETag 409 目前由兩邊 state 內容不同保證：
  兩個帳號的 token、child_token 各自隨機，所以 revision 不同。每帳號自己的 `ConfigurationState` 各有一把隨機金鑰，是第二層，
  測試沒有單獨證明（審查 S-3：突變 MD2 把金鑰改成全程序一把，測試照過）。HM-10 補「兩個帳號 state 內容完全相同」的
  對照案例（第 11 節）。

### 3.4 `run()` 的順序與失敗語意

- 和改之前相同的部分：子程式 port 先驗（`child_port_text`；原本是 `child_url()` 第一行就驗）→ legacy 遷移 → 開 store →
  建 Supervisor、client、監看、設定狀態、app → listener → 紀錄遮罩 → 起始 `backend_changed`（失敗不往外丟）→ 跑 →
  收尾 client 先關、再停子程式、最後關 store。入口失敗訊息（`runtime unavailable; local recovery required`）與 CLI 不變。
- 有差的兩處，都不會出現在回應裡：(1) signal handler 改在建 Supervisor 之前裝（原本在之後；兩者都只是本機呼叫，
  Supervisor 建不起來時一樣在 finally 拆掉）；(2) 停子程式失敗時，原本會跳過 `store.close()`，現在 store 照樣關
  （程序本來就要結束）。`make_ha_admin_verifier()` 等產品參數改在建 Supervisor 之前算，都沒有 I/O。
- `backend_changed` 從閉包變成執行套件的方法；`child_spec` 在建執行套件時傳入（原本每次呼叫時查 `run_product.child_spec`）。
  只有在執行中替換 `run_product.child_spec` 才看得出差別；正式程式不會，既有替身都在啟動前替換。

### 3.5 其他

- `PROFILE_ID` 放在 `gateway.py`（`profile_echo` 要用，`profile_runtime` 匯入它；放 `profile_runtime` 會循環匯入）。
  HM-07 的 `profiles.py` 也會定帳號 id 格式；兩邊合併後可改成同一個來源（第 11 節）。
- `CHILD_CONNECTIONS`＝40 是預設帳號原本的值（計畫 §5.2：預設帳號 40、額外帳號 24 由 HM-08／HM-09 設）。子程式 client 的
  四個選項（含它）由 `test_each_runtime_makes_its_child_client_as_run_product_did` 鎖住（審查 S-1）。
- 測試在執行時才匯入 `mcp_admin_core.profile_runtime`：改程式前每案各自失敗（先紅後綠表才有逐案數字），而不是整個檔收集失敗。

## 4. 新測試、先紅後綠、突變

### 4.1 新測試（`tests/test_profile_runtime.py`，65 案，其中 2 案審查後補；全部在 HM-01 的 `log_scan` 下，另有 autouse 檢查 `owned_network` 的拒絕計數不能增加）

子程式都是 MockTransport（照 port 分給各帳號的假子程式，不開 socket），Supervisor 是真的但不起程序（`NoProcessSupervisor`）。

| 測試 | 案數 | 內容 | 對照 |
|---|---|---|---|
| `test_make_apps_takes_the_shared_and_external_objects_as_keyword_only_options` | 1 | 6 個新參數都是 keyword-only、預設 `None`；`ProfileRuntime` 前三個是位置參數，其他 keyword-only | — |
| `test_a_runtime_carries_its_profile_id_port_and_store` | 1 | 預設帳號 `default`／3000、額外帳號 24 hex／18000；各自的 store、`TokenAccess`、鎖、Supervisor、client、監看、設定狀態、兩個 app 都不是同一個物件 | PaaS `test_default_manager_and_registry_managers_carry_their_profile_id` |
| `test_a_runtime_refuses_what_is_not_its_own` | 1 | 不合法的 id（大小寫、空白、換行、長度、非 hex、非字串）、port、`app_options` 用了執行套件自己的參數、`shared` 型別、不可呼叫的 `profile_view` → `ValueError` | — |
| `test_lifecycle_options_reach_the_profiles_supervisor` | 1 | `lifecycle` 原樣到 Supervisor | — |
| `test_two_runtimes_keep_their_tokens_and_children_apart` | 8 | 八個產品各兩套：自己的 token 兩條入口都通（session 由自己的子程式開、tools/list 和黃金回歸同一份摘要）；拿去別帳號拿到的位元組和錯 token 相同、沒有任何子程式被問；各自的 client 只打自己的 `child_url`。n8n 的 nodes.db 副本（`prepare_catalog`）是行程全域，這裡沒做（說明已寫明；DQ-04、HM-25；審查 S-5） | FM-37；計畫風險 19 |
| `test_each_child_is_started_on_its_own_state_directory_and_port` | 8 | 每個 Supervisor 拿到的 spec＝用自己的 state、目錄、port 組出的 spec；cwd 在自己的目錄；env 只有自己的憑證與網址 | PaaS `test_registry_reloads_saved_profiles_and_child_env_uses_their_files` |
| `test_child_sessions_stay_with_their_profile` | 1 | A 的子程式 session＋B 的 token：B 的子程式回 404、刪不掉；A 的子程式沒被問；A 的 session 之後照用 | FM-32 |
| `test_the_gateways_own_sessions_stay_with_their_profile` | 1 | 沒有後端時閘道自答的 `woow-local-*` session 只屬於那個帳號（別帳號 404、刪不掉） | FM-32 |
| `test_a_token_change_ends_only_its_own_profiles_requests` | 1 | A 有呼叫在等子程式時輪替 B：A 的呼叫不斷、照常回 200；撤銷 A：A 的呼叫立刻 401，B 的呼叫不斷 | FM-33、I3 |
| `test_a_save_restarts_only_its_own_child` | 1 | A 存後端只重啟 A 的子程式（新密碼）；B 的子程式沒停、套用狀態仍是 applied、state.json 沒動 | FM-47、T-16 |
| `test_each_profile_keeps_its_own_child_output` | 1 | 6 個帳號：塞爆 5 個的子程式輸出，安靜帳號的診斷頁不變；每個保留自己最新的行、各自不超過 200 筆／128 KiB，合計不超過 6 份 | FM-65、T-18；PaaS logs 緩衝 4 案 |
| `test_each_profile_redacts_its_replies_with_its_own_secrets` | 1 | 每個帳號用自己 state 的憑證遮罩子程式回覆 | FM-76 |
| `test_each_runtime_makes_its_child_client_as_run_product_did`（審查後補，S-1） | 1 | 兩套執行套件的子程式 client 都用 `run_product` 原本的四個選項：`trust_env=False`（子程式 bearer 不經環境變數的 proxy 或 `.netrc`）、`follow_redirects=False`、`Timeout(10, connect=3)`、`Limits(max_connections=40)`；比對建 client 時收到的全部 keyword 參數 | 計畫 §3.2、§5.2 |
| `test_each_profile_keeps_its_own_receipts`（審查後補，S-2(a)） | 1 | 兩個帳號輪流輪替 token（額外帳號、預設帳號各一次）：收據只寫在自己目錄的 `.state.json.operations.json`；另一個帳號的目錄樹不變，查這個 operation id 回 404 `operation_not_found` | 計畫 §3.2；契約 §3.5 |
| `test_one_shared_authority_one_csrf_and_another_profiles_etag_is_a_conflict` | 1 | 共用 `SharedAdmin`：兩個帳號 CSRF 相同、互通；拿 A 的 ETag 寫 B → 409 `{"detail":{"code":"config_conflict"}}`、兩邊 state.json 都沒動；拿 B 的 ETag → 200；一個角色驗證器服務兩個帳號。不共用時 CSRF 不同、A 的 CSRF 在 B 403。409 由兩邊 state 內容不同保證；金鑰共不共用這裡分不出來（第 3.3 節） | FM-54、FM-06；PaaS `test_admin_logout_uses_global_store_across_profiles`；A-port P2 |
| `test_shared_management_slots_are_one_budget_for_every_profile` | 1 | 共用名額：兩個帳號各 8 個請求卡在讀 body，第 17 個不論哪個帳號都 503；不共用時第 17 個照常 200 | FM-54 |
| `test_a_shared_authority_is_the_one_role_verifier` | 1 | `verify_admin` 和 `authority` 的 verifier 不同、或 `authority` 型別錯 → `ValueError` | — |
| `test_external_objects_must_be_this_profiles` | 1 | 別的 store 的 `TokenAccess`、錯型別的 5 個參數、8 種形狀錯的回聲 → `ValueError` | — |
| `test_the_apps_use_the_token_access_and_lock_they_are_given` | 1 | 外面握著鎖時寫入會等；輪替 token 時呼叫的是外面給的 `TokenAccess.committed()` | — |
| `test_the_profile_echo_marks_this_profiles_answers` | 1 | bootstrap 帶 `profile` 與 `profiles_supported`；configuration、409、200 存檔帶 `profile.id`，ETag 標頭不變；非管理員 403、缺 If-Match 428、頁面和沒有回聲的 app 逐位元相同、不含 id 與名稱；改名立刻反映 | DQ-40 ②；I10 |
| `test_an_injected_pipeline_takes_every_management_request` | 1 | 管線收到每個管理請求（API、頁面）與該帳號自己的動作；動作的回答有回聲；管線自己拒絕（例外或 JSON 回答）時動作沒跑、沒有回聲 | 計畫 §5.3 |
| `test_run_product_serves_the_default_profiles_runtime` | 7 | `run_product` 的七個產品：只建一套執行套件，`default`／3000／資料目錄的 store、沒有共用物件、沒有 lifecycle、沒有回聲；兩個 listener 服務它的兩個 app；`make_apps` 拿到它的 `TokenAccess` 與鎖，沒有 `authority` 等 4 個參數 | — |
| `test_an_invalid_child_port_is_refused_before_anything_starts` | 4 | 不合法的子程式 port 在 legacy 遷移與開 store 之前就拒絕，什麼都不寫（改之前就成立的鎖） | — |
| `test_starting_the_default_profile_adds_no_file` | 16 | 驗收鎖：八個產品×新裝與已設定，第一次啟動後的項目＝`bb48449` 的（`.writer.lock`、`state.json`，有後端的產品加空的 `child/`），沒有多帳號之後才有的檔；服務中、第二次啟動（讀 bootstrap、configuration、capabilities、diagnostics、MCP initialize）前後每個項目的路徑、型別、權限不變，state.json 連改寫都沒有（改之前就成立的鎖） | 驗收；I6 |
| `test_closing_a_runtime_stops_only_its_child_and_lets_the_store_close` | 1 | 關一套：client 先關、再停子程式（同 `run()` 原本的順序）；另一套照常服務；store 關掉後 writer lock 可以再拿；額外帳號不寫預設帳號的目錄 | — |
| `test_a_runtime_that_cannot_open_leaves_nothing_running` | 2 | `open()` 失敗（伺服器名稱不合法、回聲指到別的帳號）時 Supervisor 停掉、client 關掉、沒有殘留 task；store 仍開著（借用） | — |

本機一般使用者：63 案 5.2 秒（`test_two_runtimes_keep_their_tokens_and_children_apart` 0.9 秒、token 變動 1.1 秒、不新增檔 1.1 秒最多）；
審查後 65 案 5.8 秒。

### 4.2 先紅後綠

在 `e94ae87`（只加測試；`git diff 9f1e35e e94ae87 -- packages apps` 是空的）與改完的 `e089210` 各跑一次
`tests/test_profile_runtime.py`（`e94ae87` 用 detached checkout，跑完切回分支）：

| 測試 | `e94ae87`（改程式前） | `e089210`（改完） |
|---|---|---|
| `test_starting_the_default_profile_adds_no_file`（16 案） | 16 通過（今天就成立的鎖） | 16 通過 |
| `test_an_invalid_child_port_is_refused_before_anything_starts`（4 案） | 4 通過（今天就成立的鎖） | 4 通過 |
| 用到 `ProfileRuntime` 的 15 個測試（36 案） | 36 失敗：`ModuleNotFoundError: mcp_admin_core.profile_runtime` | 36 通過 |
| `make_apps` 新參數的 5 個測試（5 案） | 5 失敗：`make_apps() got an unexpected keyword argument`（`authority`、`token_access`） | 5 通過 |
| 參數簽名（1 案） | 失敗：`KeyError: 'authority'` | 通過 |
| 共用名額（1 案） | 失敗：沒有 `gateway.ADMIN_SLOTS` | 通過 |
| 合計 | 20 通過、43 失敗 | 63 通過、0 skip |

審查後補的 2 案沒有對應的程式改動，改用突變證明（第 4.4 節）。

### 4.3 突變（暫時改一處、跑測試、`git checkout` 還原；每次還原後 `git status` 乾淨，沒有 commit）

突變腳本放暫存區。第一輪 31 個突變在補測試前的 `2588749` 跑（執行期檔和 `e089210` 相同，只差測試檔）：29 個被擋、
P14 與 R2 沒被擋。把 `test_a_runtime_that_cannot_open_leaves_nothing_running` 的回聲案例與
`test_an_invalid_child_port_is_refused_before_anything_starts` 補進先寫測試的 commit（改寫還沒 push 的本機 commit，
`e94ae87`），在和 `e089210` 同一棵樹的 `1913fed`（只差 commit 訊息）重跑這兩個，都被擋。
多數只跑新測試檔（58 或 63 案）；P8、P9、P10、R3 另跑黃金回歸、`test_product_runtime_failure.py`、`test_child_port_param.py`（311 案）。

| 突變 | 擋下它的測試（失敗案數） |
|---|---|
| G1 `make_apps` 不理共用的 `authority` | 共用 CSRF、共用名額、回聲、管線（4） |
| G2 不理共用的 `admin_slots` | 共用名額（1） |
| G3 不理外面給的 `token_access` | 外部物件（1） |
| G4 不理外面給的 `mutation_lock` | 外部物件（1） |
| G5 不理 `admin_pipeline` | 管線（1） |
| G6 bootstrap 回聲少 `profiles_supported` | 回聲（1） |
| G7 管線自己的回答也加回聲（本片審查自己的設計時抓到的洞） | 管線（1） |
| G8 接受和 `authority` 不同的 `verify_admin` | 角色驗證器（1） |
| G9 接受別的 store 的 `TokenAccess` | 外部物件（1） |
| G10 `is_default` 可以和 id 不一致 | 外部物件（1） |
| G11 管理名額改 17 | 共用名額（1） |
| G12 回聲只加在 2xx | 回聲（1） |
| G13 bootstrap 回聲只有 id | 回聲、管線（2） |
| P1 監看用預設網址 | 兩套 token 與子程式（8）、存檔（1） |
| P2 spec 用預設 port | 子程式 spec（8） |
| P3 不傳 lifecycle | lifecycle（1） |
| P4 共用時不傳 `admin_slots` | 共用名額（1） |
| P5 共用時不傳 `authority`（改傳它的 verifier） | 共用 CSRF（1） |
| P6 所有帳號共用一個 `TokenAccess` | 15 個測試（48） |
| P7 先停子程式、再關 client | 關閉（1） |
| P8 `launch()` 失敗往外丟 | `test_initial_launch_failure_keeps_management_alive_and_retry_observable`（1，既有） |
| P9 換 spec 前不先停舊子程式 | 關閉（1）、`test_invalid_replacement_spec_stops_previous_child_first`（1，既有） |
| P10 執行套件在資料目錄寫一個自己的檔 | 黃金回歸（14）、不新增檔（14）；n8n 不經執行套件，它的 2＋2 案照過 |
| P11 不驗帳號 id | 拒收（1） |
| P12 `app_options` 可以用執行套件自己的參數 | 拒收（1） |
| P13 `open()` 失敗不收拾 | 開不起來（1） |
| P14 回聲指到別的帳號也接受 | 第一輪沒擋；補測試後：開不起來（1） |
| R1 `run_product` 給預設帳號共用物件（同一個 verifier） | `run_product` 執行套件（7） |
| R2 子程式 port 改在遷移與開 store 之後才驗 | 第一輪沒擋；補測試後：不合法 port（4） |
| R3 `run_product` 不傳 `child_port` | `test_one_port_reaches_every_child_request`（7，HM-04） |

### 4.4 審查後補的測試：用突變證明（2026-11-15）

審查後補的是測試與測試說明，程式沒改，所以先紅後綠改用突變證明：在 `a58555e`（審查後的測試 commit）上，每個突變單獨
套上，跑 `tests/test_profile_runtime.py`（65 案），再 `git checkout` 還原；每次還原後 `git status` 乾淨，沒有 commit。
突變照審查報告的定義；審查員的紀錄是這 5 個在審查前的測試下都存活（ME2、ME3 跑 1258 案、ME7 與 MD2 跑 155 案、ME6 跑 108 案，
全過）。突變腳本放暫存區。

| 突變 | 結果 | 擋下它的測試 |
|---|---|---|
| ME2 子程式 client：`trust_env=True`、`follow_redirects=True`、`Timeout(30, connect=10)`、`CHILD_CONNECTIONS`＝24 | 65 案 1 失敗 | `test_each_runtime_makes_its_child_client_as_run_product_did` |
| ME3 只改 `trust_env=True` | 65 案 1 失敗 | 同上 |
| ME7 收據改成同產品共用第一個帳號的 `OperationJournal`（同一個事件迴圈） | 65 案 1 失敗 | `test_each_profile_keeps_its_own_receipts` |
| ME6 轉送名額（32）改成所有帳號共用一份 | 65 案全過（照審查建議交 HM-08，第 11 節） | — |
| MD2 `ConfigurationState` 的 HMAC 金鑰改成全程序一把 | 65 案全過（照審查建議交 HM-10，第 11 節） | — |

收據測試兩個方向都測（額外帳號、預設帳號各輪替一次），比審查建議的單向多一個方向：預設帳號的收據也只在預設帳號的目錄。

## 5. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

### 5.1 審查後（2026-11-15，rebase 前的 HEAD `975528c`）

審查後只改了 `tests/test_profile_runtime.py`（補 2 案、改 2 段說明）與本筆記，沒有改執行期檔、帳本、`apps/`、`packaging/`。
重跑受影響的檢查。pytest 在 `a58555e`（或 commit 前內容相同的工作樹）上跑；本筆記的 commit 只改本筆記。全部排在全套測試鎖裡，
每次用新的 `/tmp/ha-mp-*`，跑完刪除：

| 檢查 | 結果 |
|---|---|
| 新測試檔（commit 前的工作樹；junit 經 `packaging/check_results.py` PASS：65 executed, no skips） | 65 通過、0 skip，5.8 秒；下一列的目標批次（`a58555e`）裡再跑一次，65 全過 |
| 目標批次（和審查員同一組 23 個檔：新測試檔、HM-01 守門、改到替身的檔、設定狀態、租約、收據、角色查詢、兩個預檢工具的測試等） | 1317 案：1316 通過、1 失敗（已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`）、0 skip，85 秒。其中黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19、`test_owned_ports_bearer` 52、`test_log_scan` 13、兩個預檢工具的測試 14＋7 全過 |
| 5 個突變 | 第 4.4 節 |
| `packaging/validate.py`（PyYAML 的 Python） | PASS |
| packaging unittest（`.venv`，PyYAML 由 `PYTHONPATH` 加進來，不改 `.venv`） | `Ran 184`、`OK (skipped=5)`（同基準） |
| `scripts/tool_inventory.py`（漂移檢查，CI 同款） | 通過（exit 0） |
| 兩個預檢 | 第 8 節 |
| 全套 pytest、起真子程式的 5 個檔 | 沒重跑：審查後只改這一個測試檔，沒有別的測試 import 或讀它（`test_tool_inventory` 只掃 `apps/`）。審查員在 `161cb04` 跑過全套（4057 案，4056 通過、只剩同一個要 root 的案例、0 skip，瀏覽器測試也過）與起真子程式的 5 個檔（97 全過）。以 PR 的 CI 為準 |
| `git status` | 乾淨；`git diff 161cb04 975528c` 只有 `tests/test_profile_runtime.py` 與本筆記 |

### 5.2 審查前（2026-11-15，`e089210`）

環境：`setup_repo_env.sh` 照 `packaging/unit.sh` 第 5～25 行裝好（uv sync 根目錄與 8 個子程式、Odoo／n8n patch、n8n 與 UI 的 `npm ci`、
UI build）。全套 pytest 在多個 clone 共用的全套測試鎖（`wave1-pytest.lock`）裡跑；小範圍的 pytest 在 `tests/conftest.py` 的本機測試鎖空著時跑。

| 檢查 | 結果 |
|---|---|
| 新測試（`e089210`） | 63 通過、0 skip，5.2 秒 |
| HM-01 守門＋改到替身的檔＋原始碼字串測試（`e089210`；`test_profile_runtime`、黃金回歸、兩個契約凍結、`test_owned_ports_bearer`、`test_log_scan`、兩個預檢工具的測試、`test_child_port_param`、`test_initialize_cleanup`、`test_product_ha_role`、`test_product_runtime_failure`、`test_owner_defaults`、`test_ha_role`、`test_initialize_identity`、`test_secret_path`、`test_owned_executable`、`test_tool_inventory`） | 1250 案：1249 通過、1 失敗（已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`），78 秒 |
| 起真子程式的整合測試（`test_role_lifecycle`、`test_real_products`、`test_unconfigured_connect`、`test_runtime_failure`、`test_real_n8n`；在 commit 前的工作樹跑，內容就是 `2588749`，執行期檔和 `e089210` 相同） | 97 通過，219 秒 |
| 全套 pytest（`tests/`） | 4057 案（HM-04 審查後的 3994＋本片 63）：4034 通過、23 失敗、0 skip，1701 秒（28 分 19 秒）。失敗：(1) 22 個瀏覽器測試（`test_owned_browser_ipc.py` 5、`test_owned_browser_redirect.py` 16、`test_owned_ui.py` 1），都在 `browserType.launch` 找不到 Chromium：本機沒跑 CI `unit.sh` 的 `npm run browser:install`。把本機既有、同版的 chromium-headless-shell 1228（另一個舊整合線 clone 用 Playwright 安裝程式裝的，有 `INSTALLATION_COMPLETE`）複製進本 clone 的 `packages/mcp-admin-ui/node_modules/playwright-core/.local-browsers/`（git 忽略，沒有下載）後這 3 個檔重跑：52 通過、0 skip、`check_results.py` PASS。這 3 個檔只用 `owned_executable.self_listener`，不經本片改的 `install_runner`。(2) 已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof` |
| 31 個臨時突變 | 第 4.3 節 |
| `packaging/validate.py`（PyYAML 的 Python） | PASS |
| packaging unittest（`.venv`，PyYAML 由 `PYTHONPATH` 加進來，不改 `.venv`） | `Ran 184`、`OK (skipped=5)`（同基準） |
| `scripts/tool_inventory.py`（漂移檢查，CI 同款） | 通過（exit 0） |
| UI `npm test`、Playwright（`npm run test:browser`） | 沒跑：本片沒改 UI；全套 pytest 裡的 3 個瀏覽器測試檔補上瀏覽器後重跑全過（上一列） |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨；`git diff 9f1e35e e089210 -- addons packaging .github apps CHANGELOG.md upgrade-notes.yaml` 空白 |

### 5.3 rebase 後（2026-11-15；`claude-delivery` `9c5dd88` 之上）

pytest 在 rebase 後的 `58d2aa4` 跑（工作樹乾淨），之後只加本筆記這一版。全部排在共用測試鎖後才跑，用正式的 `tests/conftest.py`；
每次用新的 `/tmp/ha-mp-*`，跑完刪除。

| 檢查 | 結果 |
|---|---|
| 目標 35 檔，一次 pytest（同 CI 的 `-q -p no:cacheprovider`） | 1720 案、0 skip、347 秒：1718 通過、2 失敗＝兩個已知要 root 的案例：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof` 與 HM-07 的 `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（`assert os.geteuid() == 0`；只在 CI 驗，第 6 節） |
| 其中本片：`tests/test_profile_runtime.py` | 65 案全過（5.6 秒），和 rebase 前相同 |
| 其中 HM-01 守門：黃金回歸、MCP 契約凍結、管理契約凍結、`test_owned_ports_bearer.py` | 17＋9＋19＋52＝97 案全過，期望值與案例檔沒改 |
| 其中本片改過替身注入點的既有測試：`test_product_ha_role.py`、`test_product_runtime_failure.py`、`test_role_lifecycle.py`（黃金回歸在上一列） | 122＋3＋36 案全過（`test_role_lifecycle.py` 起真子程式） |
| 其中用到 `tests/owned_executable.py`（本片改了 `install_runner`）的檔：`test_owned_executable.py`、`test_real_products.py`、`test_unconfigured_connect.py`、`test_runtime_failure.py`、`test_real_n8n.py`、`test_ha_role.py` | 3＋9＋61＋3＋3＋197 案：只有上面那個要 root 的 1 案失敗。`test_real_products.py`、`test_unconfigured_connect.py` 是 HM-06 改過的檔：真子程式要 child bearer，經本片改的注入點跑，全過 |
| 其中 HM-04：`test_child_port_param.py`（HM-06 同步過的快照）、`test_initialize_cleanup.py` | 233＋293 案全過 |
| 其中 HM-06：`test_child_bearer.py` | 28 案全過（38.4 秒） |
| 其中 HM-07：`test_profile_consistency.py`、`test_profile_index.py`、`test_profile_store.py`、`test_identity_fields.py`、`test_upgrade_zero_rewrite.py` | 14＋111＋81＋15＋29＝250 案：249 通過、1 失敗（上面那個要 root 的）。`test_upgrade_zero_rewrite.py` 用的是本片改過注入點的 `production_runtime`，29 案全過；`UNWIRED` 清單不用改（第 14 節） |
| 其中其他 13 檔（原始碼字串、預檢工具、設定狀態、租約、收據、角色查詢、能力探測）：`test_initialize_identity.py`、`test_secret_path.py`、`test_owner_defaults.py`、`test_log_scan.py`、`test_secret_precheck.py`、`test_ledger_precheck.py`、`test_tool_inventory.py`、`test_review_regressions.py`、`test_configuration_status.py`、`test_active_token_leases.py`、`test_admin_operations.py`、`test_admin_ui.py`、`test_management_capabilities.py` | 317 案全過 |
| `scripts/tool_inventory.py --write`／檢查模式 | 重產 0 差異；檢查通過 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest | 照 CI 的步驟用暫存 venv：`UV_PROJECT_ENVIRONMENT=<暫存區> uv sync --frozen --no-dev --offline`＋`uv pip install --offline --require-hashes --only-binary=:all: -r packaging/requirements-ci.txt`（離線、沒有下載；不動 clone 的 `.venv`），再 `-m unittest discover -s packaging -p 'test_*.py' -v`：`Ran 194`、`OK (skipped=5)`（5 個 `skipUnless(root)`；比 rebase 前的 184 多 10 案：HM-17 的 8 案、HM-06 的 2 案）。第一次照 rebase 前的做法用 `PYTHONPATH` 加 PyYAML：HM-17 的 `test_release_data_no_expression_can_carry_stops_every_tool_in_one_line` 在子程序裡拿掉 `PYTHONPATH`，4 個子案例 `No module named 'yaml'`。這是本機環境的做法不同，不是程式問題；改用同 CI 的暫存 venv 後全過 |
| 兩個預檢 | 第 8 節 |
| 全套 pytest | 沒有跑（以 CI 為準）。本片的檔 rebase 前後內容逐位元相同（帳本除外，第 14 節） |
| `git status` | 乾淨（commit 之後）；用過的 TMPDIR 都已刪除 |

## 6. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。CI 以 root 跑 pytest；新測試不看執行身分（資料目錄、
  store、假子程式都由同一個身分建立，`tree()` 只比對前後是否相同，不寫死擁有者），預期 root 下結果相同。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root 切到 uid 10001）。
  它經 `tests/owned_uid_probe.py` 用 `Endpoint(port=...)`，不經本片改的 `install_runner`；`install_runner` 對 `run_product` 的新路徑在本機
  由 `test_real_products.py`、`test_unconfigured_connect.py` 跑過，n8n 與 `SimpleNamespace` 的舊路徑由 `test_real_n8n.py`、
  `test_runtime_failure.py`、`test_ha_role.py`、`test_callback_is_not_serialized_behind_health` 跑過。
- rebase 後多一個 HM-07 的同類案例：`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（uid 10001 的 mode／owner 證明，
  本機 `geteuid() != 0` 照預期失敗）。它經 `tests/profile_owner_probe.py` 只用 `profiles`、`config`，不經本片改的檔，本片不影響它。
- `tests/integration_runtime_wrapper.py`：只給本機 root 明確執行的 `tests/integration_local_runtime.py` 用，而且只跑 n8n 的 `apps/n8n/run.py`
  （本片沒動）；它呼叫的 `install_runner(app, ...)` 對 n8n 模組照舊 patch 模組本身。本片沒跑（要 root）。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。
- 審查後補的 2 案也沒有只能在 CI 跑的：子程式是 MockTransport、Supervisor 不起程序，只比對 client 的參數、收據檔的位置與
  目錄樹前後是否相同，不看執行身分。

## 7. `checks` 秒數

- 前：rebase 後的基準是 #94（HM-06）：合併前最後一次 `checks`（head `dc0dcbb`，run 43661578061）1634 秒。開發時的參考：
  `bb48449` 的 push run 43222889894 `checks` 1380 秒、同一個 commit 的 pull_request run 43222899526 1834 秒（HM-01 筆記第 7 節）；
  HM-01 的 PR #90（run 43587407864）1434 秒。
- 後：CI 跑完再補。
- 推估：新測試本機約 6 秒（65 案；審查前 63 案 5.2 秒），推估 CI 增加不到 30 秒；改到替身的既有測試只換 patch 的位置，耗時不變。

## 8. 預檢結果

### 8.1 rebase 後（2026-11-15）

數字是 rebase 後的最終 HEAD（含本筆記這一版的 commit；本筆記 commit 之後重掃，結果相同）。指令：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <暫存區的 gitleaks-tools> --repo . --base origin/claude-delivery --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery
```

- **秘密預檢**：gitleaks 8.28.0（釘選、執行檔摘要相符；用暫存區既有的執行檔，沒有下載）；設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`9c5dd88..HEAD`，git 模式；rebase 後的 5 個＋本筆記這一版，共 6 個） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史（建置機同款） | 0 |

  本筆記這一版 commit 之前，rebase 後的 5 個 commit（`9c5dd88..58d2aa4`）與 `--full` 也先掃過，都 0 命中。

- **帳本預檢**：`runtime-patches.json` 168 個路徑（rebase 前 153；多的 15 個是 HM-07 新列管的 `config.py`、`features.py`、
  `identity_fields.py`、`profiles.py` 4 個，加 HM-06 在 `session_idle.py` 多列的 11 個 guarded sources）、`runtime-sources.json` 70 個、
  `tool-surface.json` 159 個，都 0 漂移、0 缺檔、0 個要 CI 安裝才有的檔。對 `origin/claude-delivery`（merge base `9c5dd88`）改 11 個檔：
  列管檔 3 個（`gateway.py`、`run_product.py`、新的 `profile_runtime.py`）與帳本 `runtime-patches.json` 一起改；新增而沒列管的執行期檔
  0 個、改到而沒列管的執行期檔 0 個。結果 OK。

### 8.2 rebase 前（`9f1e35e` 之上；下面的 HEAD 是當時的 `975528c`）

gitleaks 由 `secret_precheck.py install --tarball` 從暫存區既有的釘選壓縮檔安裝到本片自己的工具目錄（沒有下載；壓縮檔
SHA-256 `a65b5253…40eb` 和 `packaging/scanner-pins.json` 相符；每次掃描前核對執行檔摘要與版本，輸出 `gitleaks 8.28.0 (pinned, verified)`）。

- **秘密預檢**（設定是本 repo 的 `gitleaks_config()`）：

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`9f1e35e..975528c`，git 模式） | 0（5 個 commit：審查前 3 個，加審查後的測試與本筆記各 1 個） |
  | 當時本分支的 commit（`bb48449..975528c`，含 HM-01 的 9 個、HM-04 的 5 個） | 0（19 個 commit） |
  | `--full`：`git archive HEAD` 的全部檔與全歷史 `--all --full-history -m`（建置機同款） | 0 |

  審查後的測試 commit `a58555e` 上也先掃過一次：本片 4 個 commit、全分支 18 個 commit，都 0 命中。

- **帳本預檢**（`scripts/ledger_precheck.py --base 9f1e35e`）：`runtime-patches.json` 153 個路徑（多了 `profile_runtime.py`）、
  `runtime-sources.json` 70 個、`tool-surface.json` 159 個，都 0 漂移、0 缺檔。對 `9f1e35e` 改了 11 個檔：列管檔 3 個（`gateway.py`、
  `run_product.py`、新的 `profile_runtime.py`）與帳本 `runtime-patches.json` 一起改；新增而沒列管的執行期檔 0 個；改到而沒列管的
  執行期檔 0 個。結果 OK。對 `origin/claude-delivery`（`bb48449`）也 OK（HM-04 的 `health.py`、`lifecycle.py` 照舊列為要人看）。
  審查後重跑，兩個都 OK、數字相同（審查後改的測試檔與本筆記都不在帳本裡）。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

- 作者開發時：這一波規定不連遠端，沒有重新 fetch。用本機 PaaS clone 既有的 `origin/main`（`cf3d0d5`，2026-11-14 14:30 UTC 的 ref）查：
  `git log 69ac425..origin/main -- packages/mcp-admin-core/mcp_admin_core/{profiles.py,process.py,app.py,auth/}` 是 0 個 commit
  （對應本片的每帳號 registry、process manager 與共用管理身分）。這段期間 `mcp_admin_core` 只動了紀錄遮罩（#149，HM-02）
  與一個只改註解的 commit（`8bfb12e`，移除 VK 的說明文字）。
- **主對話代查（本片不連 Gitea）**：主對話 2026-11-15 06:2x 在本機 PaaS git fetch 後查，PaaS main 是 `cf3d0d5`。
  `69ac425..cf3d0d5` 動到核心模組（`packages/mcp-admin-core/mcp_admin_core/`）的只有：
  - `log_redaction.py`（#149，交給 HM-02）。
  - `gateway_pool.py` 與 `proxy.py`（#148 合併後的註解與文件更正 `19f36e2`，交給 HM-14）。
  - `setup_status.py`（移除 VK 的說明文字 `8bfb12e`）。
- 本片相關的 PaaS 檔（`profiles`、`process`、`app`、`auth`）沒有改動，和作者開發時查的結果一致。本片不用回頭對齊。

| 查詢時間 | `origin/main` | 結果 |
|---|---|---|
| 作者開發時（本機唯讀；那份 `origin/main` 是 2026-11-14 14:30 UTC fetch 的） | `cf3d0d5` | `profiles.py`、`process.py`、`app.py`、`auth/` 0 個 commit |
| 2026-11-15 06:2x（主對話，本機 PaaS git fetch 後） | `cf3d0d5` | 核心模組只動 `log_redaction.py`、`gateway_pool.py`、`proxy.py`、`setup_status.py`；本片相關的檔沒有改動 |

## 10. 驗收條件（計畫 §12.3 HM-05）

| 條件 | 狀態 |
|---|---|
| 既有測試全綠 | 本機 rebase 前：全套 4057 案只剩已知要 root 的 1 個失敗（22 個瀏覽器測試補上瀏覽器後重跑全過）；審查員在 `161cb04` 跑全套也一樣。rebase 後：目標 35 檔 1720 案只剩 2 個已知要 root 的案例失敗、0 skip（第 5.3 節）。以 PR 的 CI（root、0 skip）為準 |
| 既有測試只改替身注入點 | 通過：5 個檔只換 patch 的位置（`run_product` → `profile_runtime`），黃金回歸的檔頭只改說明這兩個注入點的文字；斷言、替身、常數沒改（第 2 節） |
| HM-01 逐位元 | 通過：黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19 全過，期望值一個字都沒改（第 5 節） |
| `/data/mcp` 不新增任何檔 | 通過：`test_starting_the_default_profile_adds_no_file` 16 案（改之前就成立、改完照過）；突變 P10（執行套件寫一個檔）被它與黃金回歸擋下 |
| `make_apps` 只加 keyword-only 參數，不給時逐位元相同 | 通過：簽名測試；預設路徑由 HM-01 守門與全部既有測試驗；`admin_api` 一行未改 |
| `run_product.py` 改用 `profile_runtime` 建預設帳號 | 通過：`test_run_product_serves_the_default_profiles_runtime` 7 案 |
| 同一個程序兩套 runtime 互不相通（token、session、子程式網址） | 通過：第 4.1 節的 10 個測試（24 案：token 與子程式、spec、兩種 session、token 變動、存檔、子程式 client 的選項、收據、輸出緩衝、回覆遮罩）。轉送名額交 HM-08、n8n 的 nodes.db 副本交 HM-25（第 11 節） |
| 共用 AdminAuthority 時 CSRF 共用、跨帳號 ETag 409 | 通過：`test_one_shared_authority_one_csrf_and_another_profiles_etag_is_a_conflict`（409 的成因見第 3.3 節） |
| 先寫測試、先紅後綠 | 通過（第 4.2 節）；突變第 4.3 節；審查後補的 2 案用突變證明（第 4.4 節） |
| 新測試沒有條件式 skip、用 log 掃描 | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail`；`pytestmark` 用 `log_scan`，並監看每個帳號的 token、憑證與帳號名稱 |
| 同 PR 更新帳本（新模組列管） | 通過：`profile_runtime.py` 新增；`gateway.py`、`run_product.py` 更新；rebase 後以 `claude-delivery` 的帳本為底、摘要全部重算（第 14 節）；沒動 `apps/`，tool-surface 重產 0 差異 |
| `ledger_precheck` OK、`secret_precheck` 0 命中 | 通過（第 8 節） |
| 不改版號、不碰 `addons/<x>/`、CHANGELOG | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：憑證 `DUMMY-<帳號>-…`、網址 `.invalid`、token 執行時產生；沒有新增 64 hex（除了帳本摘要）；秘密預檢 0 命中 |

## 11. 還沒解決、交給後面的片

- **開 PR 前（已做，2026-11-15）**：rebase 到 `claude-delivery` `9c5dd88`；帳本以 `claude-delivery` 為底加回本片 3 筆、摘要全部重算；
  `scripts/tool_inventory.py --write` 0 差異、檢查模式通過；本機檢查（第 5.3 節）；兩個預檢（第 8 節）；PaaS 變動由主對話代查（第 9 節）。
  做法見第 14 節。
- `checks` 的「後」秒數：PR 的 CI 跑完後補。
- **合併後的發版（計畫 §11.5；審查 S-4）**：本片合併後，任何產品（含 Headscale）的發版都走完整既有流程，不能只看單帳號
  黃金回歸：該產品 HAOS P9 回歸、子程式 bearer 的直連 401 檢查、HM-13a 合併後加容器驗收的 root 還原樹；CHANGELOG 寫明帶出去的
  不受開關管變更（計畫 §3.3 表的 HM-05 列：對未開通產品可見的變化「無」）。理由：每個產品映像整包複製 `packages/mcp-admin-core`，
  新的 `profile_runtime.py` 與改過的 `gateway.py`、`run_product.py` 會隨下一個發版的任何產品出去。
- **合併順序**（計畫 §12.2）：`gateway.py`、`run_product.py` 照 HM-04 → HM-05 → HM-08；`profile_runtime.py` 照 HM-05 → HM-08 → HM-09 → HM-13b → HM-30 → HM-25；
  `runtime-patches.json` 一次送審一片，後合的 rebase 後重產摘要、重跑 CI。本片已 rebase 到 `claude-delivery` `9c5dd88`（HM-04 #91 與
  HM-06 #94 之後；`gateway.py`、`run_product.py` 照 HM-04 → HM-05 的順序）。
- **HM-08**：建 ProfileManager 時用 `ProfileRuntime` 建額外帳號（store 用 HM-07 的「只開既有」）、用一份 `SharedAdmin` 給所有帳號；
  額外帳號的子程式 client 上限 24（計畫 §5.2，本片只有 `CHILD_CONNECTIONS`＝40）。`PROFILE_ID` 和 HM-07 `profiles.py` 的帳號 id 格式統一成一個來源。
  上限改 24 時，`test_each_runtime_makes_its_child_client_as_run_product_did` 改成依帳號斷言（預設 40、額外 24），其他三個選項不變
  （審查 S-1）。轉送名額（`make_apps` 的 32）每帳號一份目前沒有測試（審查 S-2(b)：突變 ME6 讓所有帳號共用一份，測試照過）：
  `test_profile_quotas.py` 的「轉送名額逾時」（計畫 §10.3）要補跨帳號案例：一個帳號的轉送名額滿時，別的帳號照常轉送。
- **HM-09**：看門狗參數經 `lifecycle` 傳給 Supervisor；`start_all`、`stop_all`、錯開啟動在 `profile_runtime.py`。
- **HM-10**：(1) 從 `admin_api`／`admin_action` 抽出共用管線，經 `admin_pipeline` 給每個帳號（本片只開注入點）；(2) 帳號回聲的範圍定案
  （本片暫定：帳號動作的 JSON 回答都帶，例外拒絕與管線自己的回答不帶；契約 §3.4 的逐條測試）；(3) `ConfigurationState` 的 HMAC domain 加帳號 id
  （契約 §3.5，DQ-15 細節待定）；(4) 刪帳號用執行套件的 `token_access.committed()` 與 `mutation_lock`；(5) 做 (3) 時補「兩個帳號
  state 內容完全相同」的對照案例：拿 A 的 ETag 寫 B 仍要 409（審查 S-3：今天的測試分不出金鑰共不共用，突變 MD2 照過）；
  (6) 審查提醒（本片正式程式沒有傳回聲）：`echoed()` 只處理 `JSONResponse`；它用 dict 重組標頭，同名多值標頭（例如多個
  Set-Cookie）會合併；`profile_view()` 丟例外會變 500。
- **HM-16**：`acceptance/real_backends/ha_runtime.py` 仍 patch `run_product.make_apps`。它跑釘在 0.4.6 的已發佈映像，今天不受影響；
  拿含本片的映像重跑時會在 import 時 `AttributeError`（明顯失敗，不會默默失效）。改驗收工具時要跟著改注入點（審查的其他觀察）。
- **HM-25**：`apps/n8n/run.py` 改用 `ProfileRuntime`（本片測試已用 n8n 的 `child_spec` 建過兩套，介面可用）；FM-37「兩個入口合成一個」在那時完成。
  `n8n_adapter._catalog`（`prepare_catalog` 做的 nodes.db 副本，子程式的 `NODE_DB_PATH`）是行程全域：兩個 n8n 帳號的子程式會拿到
  同一份可寫 nodes.db（審查 S-5）。額外帳號的副本放哪裡等 DQ-04（計畫 §13.3，還沒問），HM-25 開工前問使用者。本片沒改 n8n，
  正式程式不受影響。
- **HM-01（O-1）**：`ledger_precheck.py` 改用 `shutil.copy2` 的修正（`1281abe`）在 #90 合併前補進。開發時本分支沒有它；rebase 後有了，
  第 8 節 rebase 後的帳本預檢用的就是它。rebase 前的帳本預檢都在工作樹乾淨時跑，不受影響。

## 12. 本片用到的決策

- **DQ-33（已定，§13.1）**：本機測試用短的 `/tmp/ha-mp-<隨機>` 當 TMPDIR，跑完刪；以 GitHub CI 為準。
- **DQ-36（已定，§13.1；2026-11-15 06:1x 補合併授權）**：commit 與 PR 說明不加 AI 署名；標題加「⛔ 勿代 merge｜待覆核 — HM-05 …」。
  不改版號的多帳號功能 PR 由使用者授權本工作的主對話在 CI 全綠後依序合併，其他人或代理不合併（`docs/multi-profile/decisions.md`
  的 DQ-36）；本片不改版號、不碰 `addons/`。本片作者不合併。
- **DQ-40 ②（已定，§13.1）**：管理回應帶帳號回聲。本片只開 `profile_view` 參數（正式程式沒有傳），回聲的範圍是暫定，由 HM-10 定案。
- **DQ-19（2026-11-14 21:5x 照建議）**：`/health/ready` 只代表預設帳號。本片沒改它：`run_product` 的 MCP listener 掛的仍是預設帳號的 app，
  每套執行套件的 `/health/ready` 只看自己的帳號。
- 沒有用到、也沒有自己定任何 §13.2、§13.3 的待定題：DQ-15（HMAC domain 加帳號 id）、DQ-17（`X-MCP-Profile`）都留給 HM-10；DQ-09、DQ-12、DQ-38 本片沒用到。
- 審查後的處理也沒有用到或自己定待定題：S-3 的對照案例留給 HM-10（DQ-15），S-5 的 nodes.db 位置留給 HM-25（DQ-04，§13.3）。

## 13. 審查意見處理（獨立審查 2026-11-15，審 `161cb04`：判定通過；必修 0、建議 5）

審查報告在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave2/review-HM-05.md`。rebase 後的 commit：審查的 `161cb04` 是
`49705fd`；S-1、S-2(a) 補的測試與 S-3、S-5 在測試說明裡的文字（`a58555e`）是 `a5ef01a`；本筆記的處理（`975528c`）是 `58d2aa4`
（第 14 節）。

| id | 審查意見 | 處理 |
|---|---|---|
| 必修 | 無 | — |
| S-1 | 子程式 client 的四個選項（`trust_env=False`、`follow_redirects=False`、`Timeout(10, connect=3)`、`max_connections=40`）搬進 `profile_runtime.py` 後沒有測試。`trust_env=False` 是安全性質：子程式 bearer 每個請求都帶，改成 `True` 會照環境變數的 proxy 與 `.netrc` 走。突變 ME2、ME3 下相關的 1258 案全過 | 採用。新增 `test_each_runtime_makes_its_child_client_as_run_product_did`：攔下 `profile_runtime.httpx.AsyncClient` 收到的全部 keyword 參數，兩套都必須剛好是這四個。ME2、ME3 下這個測試紅（第 4.4 節）。HM-08 給額外帳號 24 連線時改成依帳號斷言（第 11 節） |
| S-2 | 計畫 §3.2 每帳號一份的收據與轉送名額沒有測試；突變 ME7（收據併到第一個帳號的檔）、ME6（轉送名額共用）照過 | (a) 收據：採用，範圍比建議大一點。新增 `test_each_profile_keeps_its_own_receipts`，兩個方向都測（額外帳號、預設帳號各輪替一次）：收據只在自己目錄的 `.state.json.operations.json`，另一個帳號的目錄樹不變，查這個 operation id 回 404 `operation_not_found`。ME7 下這個測試紅。(b) 轉送名額：照建議留給 HM-08。理由：HM-08 會把額外帳號的轉送名額改成 16（計畫 §5.2），計畫 §10.3 已把「轉送名額逾時」排進它的 `test_profile_quotas.py`；現在寫的數字會在 HM-08 改掉。第 11 節的 HM-08 項寫明要補跨帳號案例；ME6 仍存活（第 4.4 節） |
| S-3 | 筆記第 3.3 節說「跨帳號 409 來自每帳號自己的金鑰」，比測試證明的多；突變 MD2（全程序一把金鑰）照過 | 採用（只改說明）。第 3.3 節改成：409 目前由兩邊 state 內容不同保證，每帳號金鑰是第二層，測試沒有單獨證明；測試檔頭的同一句也改了。第 11 節的 HM-10 項加：做 ETag 綁帳號時補「兩個帳號 state 內容完全相同」的對照案例。沒有在本片補這個案例：它驗的是 ETag 綁帳號的那一層，契約 §3.5 把這一層的做法列為 DQ-15 細節（待定、負責片 HM-10），照審查建議跟 HM-10 一起補；今天每個 `ConfigurationState` 各有隨機金鑰，實際沒有風險 |
| S-4 | 筆記與 PR 描述沒寫計畫 §11.5：本片合併後，任何產品的發版都要走完整既有流程 | 採用（只改文件）。第 11 節加一條，結論也提一句；PR 說明也寫了 |
| S-5 | n8n 的 nodes.db 副本（`n8n_adapter._catalog`）是行程全域，兩個 n8n 帳號的子程式會拿到同一份可寫 nodes.db；`test_two_runtimes_keep_their_tokens_and_children_apart` 說「每個產品的 child_spec 都適用」，但沒跑 `prepare_catalog`，看不到這一點 | 採用（只改說明，不決定）。第 11 節的 HM-25 項記下；放哪裡等 DQ-04（計畫 §13.3，還沒問），HM-25 開工前問使用者。測試說明與檔頭也寫明這裡沒做 nodes.db 副本。本片沒改 n8n |
| 其他觀察 | (1) golden 檔頭換行後留了一行很短的字（純排版，可不改）；(2) `acceptance/real_backends/ha_runtime.py` 仍 patch `run_product.make_apps`；(3) 給 HM-10 的三個提醒（`echoed()` 只處理 `JSONResponse`、同名多值標頭會合併、`profile_view()` 丟例外變 500）；(4) `PROFILE_ID` 要和 HM-07 統一 | (1) 不改：HM-01 的守門檔只動注入點，不為排版再改一次。(2) 第 11 節加 HM-16 項。(3) 第 11 節的 HM-10 項記下。(4) 原本就記在第 11 節的 HM-08 項 |

## 14. rebase（2026-11-15）

1. `git fetch origin claude-delivery`（`9c5dd88`），`git rebase --onto origin/claude-delivery 9f1e35e`：本片 5 個 commit 依序重放，
   **沒有衝突**。
   - `claude-delivery` 在 `9f1e35e` 之後（HM-00、HM-01 的合併，與 rebase 過的 HM-04、HM-17、HM-07、HM-06）沒有動 `gateway.py`、
     `run_product.py`、`tests/test_single_profile_golden.py`、`tests/test_product_ha_role.py`、`tests/test_product_runtime_failure.py`、
     `tests/test_role_lifecycle.py`、`tests/owned_executable.py`（`git diff 9f1e35e origin/claude-delivery` 對這 7 個檔是空的）。
     HM-04 的 `child_port` 原樣在，本片的 `profile_runtime` 疊在它上面；HM-06、HM-07 沒改這兩個執行期檔，沒有要合併的改動。
   - HM-06、HM-07 和本片相關的地方逐一看過：
     - HM-06 讓 `products.child_spec` 給 7 支 Python 子程式 `WOOW_MCP_CHILD_TOKEN`：執行套件照舊用產品給的
       `child_spec(state, directory, port=...)`，不看 env 的內容。`test_two_runtimes_keep_their_tokens_and_children_apart`、
       `test_each_child_is_started_on_its_own_state_directory_and_port`（各 8 案）用的就是新的 spec，全過。
     - HM-06 改過的 `tests/test_real_products.py`、`tests/test_unconfigured_connect.py` 經 `owned_executable.install_runner` 起真子程式；
       本片改的是 `install_runner` 對 `run_product` 的注入點（改 patch `profile_runtime`）。兩邊的改動不重疊、都保留，rebase 後全過。
     - HM-06、HM-07 新增或改的測試，沒有一個 patch 本片從 `run_product` 搬走的名字（`Supervisor`、`HealthMonitor`、`make_apps`、
       `httpx`）。rebase 後 `git grep` `tests/`、`packaging/`、`acceptance/`、`apps/`、`scripts/`：只剩
       `acceptance/real_backends/ha_runtime.py` patch `run_product.make_apps`（釘在已發佈映像，第 11 節的 HM-16 項）。
     - HM-07 的 `tests/test_upgrade_zero_rewrite.py` 用黃金回歸的 `production_runtime`（本片改過它的兩個注入點），29 案全過。
       它的 `UNWIRED = ('profiles', 'features', 'identity_fields')` 不用改：`profile_runtime.py` 只 import `access`、`admin_auth`、
       `configuration`、`gateway`、`health`、`lifecycle`，`gateway.py`、`run_product.py` 也沒有 import 這三個模組；
       `test_no_runtime_file_imports_the_unwired_modules` 與 `test_no_entry_point_imports_the_unwired_modules`（4 個入口）照過。
     - HM-07 的 `profiles.py` 也定了帳號 id 格式；本片的 `PROFILE_ID` 照計畫暫放 `gateway.py`，由 HM-08 統一成一個來源（第 11 節）。
   - 核對：本片 11 個檔的增刪行（`git diff -U0`，`9f1e35e..975528c` 對 `9c5dd88..58d2aa4`）逐行相同；帳本以外的 10 個檔，
     內容（blob）也和 rebase 前相同。
2. 帳本（`docs/provenance/runtime-patches.json`）沒有只看文字合併。git 自動合併沒有衝突：`claude-delivery` 改的是 `scope`、
   `products.py`、`session_idle.py` 三筆與檔尾新增的 4 筆，本片改的是 `gateway.py`、`run_product.py` 兩筆與插在 `run_product.py`
   後面的 1 筆。另外用暫存區的一次性腳本（不進 repo）照規則重建一份來比：
   - 以 `claude-delivery` 的帳本（54 筆）為底；`scope` 照 `claude-delivery`（本片沒改）。
   - 加回本片的 3 筆：`gateway.py`、`run_product.py` 的 `change` 換成本片的（原文＋本片的 HM-05 那段；`claude-delivery` 在 `9f1e35e`
     之後沒改這兩筆）；`profile_runtime.py` 插在 `run_product.py` 後面。其他 52 筆（含 HM-07 新增的 `config.py`、`features.py`、
     `identity_fields.py`、`profiles.py`，與 HM-06 改的 `products.py`、`session_idle.py`）照 `claude-delivery`，順序也照它。
   - 55 筆列管檔的 SHA-256 全部用工作目錄裡合併後的檔重算，有安裝的 guarded sources 也重算。和 `claude-delivery` 比，只有本片的
     兩筆變：`gateway.py` `a07fb0e9…` → `1c489f0d…`、`run_product.py` `6bd89482…` → `f6540f3d…`；新的 `profile_runtime.py` 是
     `a92cbfa1…`。三個都和 rebase 前相同。
   - 重建的帳本和自動合併的結果逐筆相同（JSON 內容相同；格式照原檔：`indent=2`、`ensure_ascii=False`、結尾換行），所以帳本不用再改。
   - `scripts/ledger_precheck.py`：0 漂移、0 缺檔（第 8.1 節）。
3. `scripts/tool_inventory.py --write`：0 差異；檢查模式通過。本片沒動 `apps/runtime/*.py`、`apps/*/launch.py`。
4. `git log origin/claude-delivery..HEAD` 只剩本片的 6 個 commit：

   | rebase 後 | 原本 | 標題 |
   |---|---|---|
   | `c35448d` | `e94ae87` | test(multi-profile): pin the per-profile runtime and the default profile built with it (HM-05) |
   | `dbe9c44` | `e089210` | feat(runtime): build one profile's runtime in profile_runtime, the default profile first (HM-05) |
   | `49705fd` | `161cb04` | docs(provenance): add HM-05 multi-profile provenance note |
   | `a5ef01a` | `a58555e` | test(multi-profile): pin the child client options and per-profile receipts (HM-05) |
   | `58d2aa4` | `975528c` | docs(provenance): record the HM-05 review fixes and rechecks |
   | 本筆記這一版 | （新） | docs(provenance): record the HM-05 rebase onto claude-delivery and the PaaS change list |

5. 本機檢查見第 5.3 節，兩個預檢見第 8.1 節，PaaS 變動見第 9 節。
