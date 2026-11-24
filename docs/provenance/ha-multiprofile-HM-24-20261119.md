# HA 多帳號 HM-24 provenance：Hermes 開通的功能 PR（2026-11-19）

## 結論

- **做了什麼**：Hermes 開通要的產品專屬程式、測試與文件都備好；之後 Hermes 的升版 PR 只要把 `hermes` 加進
  `features.MULTI_PROFILE_PRODUCTS`、改 `addons/hermes/` 的版號與文件。本片沒改 `MULTI_PROFILE_PRODUCTS`、沒碰 `addons/`、不改版號。
- **產品專屬程式只有一項：Hermes 的 token 綁後端身分**（DQ-40 ⑩ (a)；計畫 §9 Hermes 列）。`products.IDENTITY_BOUND` 加 `hermes`，
  面板 `contracts.js` 的 `identityBound` 同步。開通後換 `gateway_url`、`dashboard_url`、`dashboard_username` 就走 HM-12 的換身分換 token
  （先停舊子程式 → 一次寫入連線＋新 token＋rotate 歷史 → 發布 → 起新子程式）。Dashboard 三欄一起清空也算換身分（照 HM-12 的 Odoo
  規則）；一起補上也算是本片的做法，**待使用者確認**（第 4.1、12 節）；只換 `gateway_api_key`、`dashboard_password`、初次設定、token
  已撤銷不換。沒開通時什麼都不變。
- **面板修一個會出錯的文字**：等核對時被擋的後端存檔，原本固定說「Odoo 的網址、資料庫或使用者」。Hermes 加進 `identityBound` 後會讓
  Hermes 的使用者看到 Odoo 的字，所以改成照存檔的產品說（`contracts.js` 新增 `identityChange`）。Odoo 的文字逐字不變。
- **計畫 §9 Hermes 列的其他項目都已經成立，本片用測試釘住、寫進文件**（第 3 節）：launcher `--port`（HM-04）、cookie 快取每個子程式一份
  （每帳號一個子程式，快取在子程式的記憶體）、`hermes_chat` 最長 330 秒佔自己帳號的轉送名額（HM-08、HM-14）、Dashboard 登入限流共用
  （寫進契約 #135 與威脅模型）、長 chat 不卡別帳號（真子程式測試）。
- **測試**：新 `tests/test_hermes_multi_profile.py` 23 案（兩種開關、含真 Hermes 子程式一案；審查後加還原核對關卡 2 案）；改 `tests/test_odoo_identity_rotation.py`
  （開通後不換 token 的產品拿掉 Hermes）與 `packages/mcp-admin-ui/tests/profiles.test.mjs`（3 處）。先紅後綠記在第 6 節，第 7 節的突變（程式 5 個、
  替身 1 個、面板 1 個）都會讓新測試紅。HM-01 黃金回歸與兩個契約凍結逐位元照過（開關關）。
- **獨立審查（2026-11-19）**：修正後通過，必修 2、建議 8，全部採用（第 14 節）。DQ-05 標出「補上 Dashboard 也換」還沒經使用者確認，
  **確認前不合併**；還原與回退文件四處補 Hermes；T-12 的測試照真的順序（先停子程式：進行中的 chat 收到 `-32004`，不是 401）；
  Hermes 的還原核對關卡有了伺服器端測試；vendored `guards.py` 的 loopback 註解改成開通後也成立（帳本與 tool-surface 各一個摘要）；
  驗收手冊補 T-02；Hermes 開通版的 CHANGELOG 句子只留在本筆記；本筆記補 PaaS 變動清單（第 5.1 節）與 HM-18 的衝突（第 11 節）。
- **文件**：契約第 3.1、5 節與第 9 節 #134～#136（**列號暫定**：其他產品的開通片同時在做，後合併的一方接在當時最後一列之後重編，
  同 HM-27）；驗收矩陣、`docs/operations/acceptance.md` 的 Hermes 一節（HAOS 驗收要另外做的與 60 分鐘負載量測）、威脅模型、決策紀錄、
  還原與回退手冊（審查後）、發版交接清單（第 4.2 節一列；Hermes 開通那一版的 CHANGELOG 句子在本筆記第 9 節，清單第 3.3 節指過來）。
- **預檢**：秘密預檢 0 命中、帳本預檢 OK、`validate.py` PASS、packaging unittest OK、node 119 案全過、相關 pytest 全過（第 8 節）。
- **要使用者決定的**（第 12 節）：「補上 Dashboard 也換 token」要不要照這樣（清空也換照 HM-12 的規則；**確認前不合併**）；之後 HAOS
  實測要用的後端身分與 60 分鐘負載量測。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 基準 | `claude-delivery` `c90b214`（PR #109 HM-16 合併；契約第 9 節最後是 #128） |
| 分支 | `feat/ha-multiprofile-hm24-hermes-20261119`（clone `ha-mp-hm24-20261119`；審查處理完由收尾步驟 push，第 14 節） |
| 依據 | 計畫 §9 Hermes 列、§12.3「HM-21～HM-26｜各產品開通」（含 2026-11-17 加的 HM-12 面板交辦）、§8.8 #40、#63；契約第 9 節；`docs/operations/acceptance.md` T-01～T-29；HM-12 筆記第 15 節、HM-12 面板筆記第 13 節的交辦 |
| 參考做法 | Odoo（HM-12）：`products.IDENTITY_BOUND` 與 `identity_fields.py`、`profile_runtime` 每帳號子程式、`run_product`、面板 `identityBound`、`tests/test_upgrade_zero_rewrite.py` 的開關做法、`packaging/container_profiles.py` |
| PaaS（唯讀） | 本機研究 worktree `paas-mp-research-20261114`（`443e95a`）：`apps/hermes/hermes_mcp_admin/main.py`（每帳號子程式、`--port {port}`、管理端 Dashboard 代理）、`apps/hermes/hermes_mcp_server/server.py`（chat 預設 90 秒、cookie 快取模組全域）、`apps/hermes/tests/test_dashboard_profile_cache.py`、`packages/mcp-admin-core/mcp_admin_core/routers/tools.py`（政策由代理執行、只有 n8n 重啟子程式）。PaaS 變動清單見第 5.1 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hc/products.py`（列管） | `IDENTITY_BOUND` 加 `hermes`；註解與 `identity_rebound` 的說明寫 Hermes 的欄位。判斷邏輯沒改（HM-12 的通用寫法本來就涵蓋 Hermes） |
| `Hc/identity_fields.py`（列管） | 只改 `TOKEN_ROTATING` 的註解（誰在用它）；分類資料不變 |
| `Hui/contracts.js`（列管） | `identityBound` 加 `hermes`；新增 `identityChange`（每個綁身分的產品的身分欄位說法；Odoo 的字照 HM-13c） |
| `Hui/api.js`（列管） | 等核對時被擋的後端存檔說明改用 `identityChange[產品]`；Odoo 的文字逐字不變 |
| `docs/provenance/runtime-patches.json` | 上面四個檔重算 SHA-256，`change` 各補一句（照 JSON 結構改，沒用 `--write`） |
| `apps/hermes/vendor/hermes_mcp_server/guards.py`（vendored，列管在 `runtime-sources.json`） | 審查後（S-1，HM-20 交辦）：只改 loopback 那段註解，寫明 `backend_policy` 只在 Hermes 沒開通時對設定的後端放行 loopback；開通後管理程序起子程式時打開 `backend_policy` 的 loopback 拒絕（`WOOW_MCP_DENY_LOOPBACK=1`；註解不點名這個變數，`tests/test_backend_loopback.py` 只准兩個政策檔與 n8n spec 點名），也拒。程式不變 |
| `docs/provenance/runtime-sources.json`、`docs/tool-surface.json` | 審查後：`guards.py` 的 `local_sha256` 重算、`modification` 補一句（照 JSON 結構改）；tool-surface 用 `scripts/tool_inventory.py --write` 重產，只有 `guards.py` 的摘要變（`tool-surface.md` 不變） |
| `tests/test_hermes_multi_profile.py` | 新增 23 案（第 6 節；審查後改 T-12 一案、加還原核對關卡 2 案） |
| `tests/test_odoo_identity_rotation.py` | `OTHERS` 拿掉 Hermes（開通後 Hermes 會換 token），說明跟著改 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs` | `identityBound` 的期望值；HM-12 S-7 提示加 Hermes 四案；新增 HM-24 一案（等核對的說明寫自己產品的欄位、每個綁身分的產品都有說法） |
| 文件 | 契約、驗收矩陣、驗收手冊、威脅模型、決策紀錄、發版交接清單（第 10、11 節）；審查後加還原與回退手冊 `docs/operations/update-backup-rollback.md`（MF-2） |

沒改：`features.MULTI_PROFILE_PRODUCTS`（仍是空集合）、`addons/`、`apps/` 的程式（Hermes 子程式、launcher；vendored `guards.py` 只改註解）、
`gateway.py`、`profile_runtime.py`、`profiles.py`（`EXTRA_PROFILE_LIMITS['hermes']`＝3、`CHILD_MEMORY_MIB['hermes']`＝160 照舊）、`packaging/`、
`tests/conftest.py`。沒動 `apps/runtime/*.py` 與 `apps/*/launch.py`；tool-surface 只因 `guards.py` 的註解重產一個摘要（審查 S-1，
`scripts/tool_inventory.py` 不帶參數檢查沒有漂移，exit 0）。
計畫 §12.2 的衝突表把 `tests/owned_child.py`、`tests/owned_runtime.py` 列給 HM-24（HM-01 → HM-24）：不用改。HM-01 已經把子程式的
production port 參數化（額外帳號的 `--port` 也走 `owned_child.py`），本片的真子程式案用 `tests/multi_profile_runtime.py` 的
`real_children`（每個子程式一個 ephemeral port，同 HM-12 的 Odoo 真子程式案）。

## 3. 計畫 §9 Hermes 列逐項

| 項目 | 現況 | 本片 | 測試 |
|---|---|---|---|
| launcher `--port` | HM-04 已做：預設帳號的子程式照舊（沒有 `--port`，3000），額外帳號帶 `--port <索引 port>` | 開通時每個帳號的 argv、環境、目錄逐欄釘住；沒開通時預設帳號的 spec 和今天只差 HM-20 的 loopback 變數 | `test_every_profiles_child_has_its_own_port_environment_and_directory`；真子程式一案（兩個子程式各自的 ephemeral port） |
| cookie 快取每子程式隔離 | 每帳號一個子程式；快取是子程式的模組全域（`_cookie_cache`、`_login_locks`），只在記憶體 | 不用改程式。真子程式測試：同一個 Dashboard、兩個帳號各自登入一次，每個 Dashboard 請求帶的是自己那次登入的 cookie，子程式目錄沒有寫任何檔 | `test_real_children_keep_their_dashboard_cookies_and_long_chats_apart`（對照 PaaS `test_dashboard_health_cookie_follows_profile`） |
| `hermes_chat` 最長 330 秒算進每帳號名額 | 閘道 tools/call 用 `CALL_SECONDS`（330 秒）轉送，整段佔自己帳號的轉送名額（HM-08、HM-14） | 釘住：轉送的讀寫逾時是 330 秒；額外帳號 16 個名額都被 chat 佔住時，下一個請求等 1 秒後 200＋`-32003`、不到子程式；別的帳號的 chat 立刻回答。開關關照今天（32 個名額、503） | `test_long_chats_hold_their_own_profiles_slots_and_no_other_profiles`、`test_switched_off_long_chats_hold_todays_32_slots` |
| Dashboard 登入限流共用 | 每個子程式各自登入；同一個 add-on 的子程式從同一個來源位址連線 | 寫進契約 #135、威脅模型第 3 節、驗收手冊（記下有沒有 429） | 真子程式一案：兩個帳號對同一個 Dashboard 就是兩次登入 |
| DQ-40 (a)：換 gateway_url、dashboard_url、dashboard_username 換 token | HM-12 的通用程式只對 `IDENTITY_BOUND` 生效 | `IDENTITY_BOUND`＋面板 `identityBound` 加 Hermes（第 4.1 節） | 換身分 7 案、補上與清空、只換秘密、預設帳號、沒開通、長 chat 進行中換身分、真子程式換 Dashboard 使用者 |
| 長 chat 不卡別帳號 | 名額每帳號一份；子程式各自 | 真子程式：B 的長 chat 掛在 Gateway 時，預設帳號的 chat 與 B 自己的 status 都照常回答；B 換身分時只有 B 的 chat 結束（先停子程式：`-32004`，審查 S-2） | 真子程式一案；`test_an_identity_change_ends_its_own_profiles_long_chat_only`（T-12） |
| HAOS 至少 60 分鐘負載量測定每子程式 MiB | `CHILD_MEMORY_MIB['hermes']`＝160（暫定，照 PaaS） | 量法寫進 `docs/operations/acceptance.md`「Hermes 開通（HM-24）」第 7 點（審查前是第 6 點）；契約第 5 節 Hermes 列指過去。常數本片不改 | —（HAOS） |
| 子程式環境各自（§12.3） | 每帳號自己的 state 與目錄（HM-05） | 每個環境只有自己的值，別帳號的任何值（token、child token、連線、目錄）都不在裡面 | 同第一列 |
| 存政策只重啟該帳號（任務要求的隔離） | Hermes 的子程式啟動時不帶政策，閘道每個請求照帳號的 state 執行（PaaS 同：代理執行，只有 n8n 重啟） | 釘住：存 B 的政策只改 B 的工具清單與呼叫，**沒有任何子程式重啟**（任務寫的「只重啟該帳號的子程式」對 Hermes 是零個）；兩種開關都測 | `test_saving_one_profiles_policy_changes_only_its_tools_and_restarts_no_child`、`test_switched_off_a_policy_save_restarts_no_hermes_child` |

## 4. 設計重點

### 4.1 Hermes 的換身分範圍（契約 #134）

- 身分欄位照 HM-07 的 `identity_fields.TOKEN_ROTATING['hermes']`：`gateway_url`、`dashboard_url`、`dashboard_username`。`products.identity_rebound`
  沒改：已存的連線完整、token 有效、任一身分欄位和新值不同就換。
- HM-12 筆記第 15 節交辦「Hermes 的 dashboard 可以整組清空，清空算不算換身分照 Odoo 的規則再確認一次」。照通用程式與 Odoo 的規則：
  - **清空 Dashboard 也換**：同 Odoo 清空連線也換。不換的話，先清空、再補上另一個 Dashboard 帳號就成了「初次設定」，舊 token 會留下來。
  - **補上 Dashboard（原本只有 Gateway）也換**：token 原本只代表 Gateway 上的身分，補上之後多了一個 Dashboard 身分。照「每條網址永久綁
    一個後端身分」，身分組合變了就換。代價：管理員事後才補 Dashboard 時，用戶端要換新網址。這點列為要使用者確認（第 12 節）：
    DQ-40 ⑩ 推不出來、PaaS 的通用判斷也不會換，是本片自己的選擇，**確認前不合併**（審查 MF-1；`decisions.md` DQ-05 的狀態欄與第 4 節）。
  - **三欄只給一部分**：`HermesConnection` 本來就要三欄一起（`dashboard_complete`），存檔照今天 400 `{"error":"request denied"}`，
    舊子程式不停、什麼都不寫（測試釘住）。
  - **初次設定**（沒有任何連線）、**只換 `gateway_api_key` 或 `dashboard_password`**、**token 已撤銷**：照今天，不換。
- 和 PaaS 通用判斷的差別（PaaS 不綁 Hermes，這是照搬時才會有的差別）：PaaS `patch_connection_bound`（`packages/mcp-admin-core/
  mcp_admin_core/config/store.py`，`origin/main` `5ef1046` 唯讀核對）要舊連線的**每個**身分欄位都是非空字串才換（「初次設定沒有完整的
  舊身分」）。Odoo、Nextcloud 的身分欄位都必填，所以兩邊一樣；Hermes 的 Dashboard 選填，照搬的話只有 Gateway 的帳號連換 Gateway 網址
  都不會換。HA 用 HM-12 的 `identity_rebound`：存了連線（Gateway 必填）就算有身分，任一身分欄位改變（含補上、清空 Dashboard）就換。
  所以只有 Gateway 的帳號也綁得住；代價是上一點的「補上也換」。
- 新來源要重填秘密（DQ-40 ⑨，HM-12 已涵蓋全部產品）：`gateway_url` 換來源要帶 `gateway_api_key`，`dashboard_url` 換來源要帶
  `dashboard_password`；本片的換身分測試照這個規則帶（同來源只換路徑的一案不帶）。
- 換身分的順序、回應（`token_rotated: true`、新 state 的 `ETag`）、五種失敗與 WARNING、還原核對關卡（HM-13c S-3）都是 HM-12 的通用程式，
  本片沒改。失敗的故障注入 HM-12 已對 Odoo 做過；Hermes 走同一條路，本片只測成功、補上、清空、不換與長 chat。還原核對關卡審查後加了
  Hermes 的伺服器端測試（S-6）：核對前改 `dashboard_username` 回 409、什麼都不做，只換 `gateway_api_key` 照常存。

### 4.2 Dashboard 登入限流（契約 #135）

- Hermes Agent 的 `/auth/password-login` 每個來源位址每 60 秒只放 10 次（成功也算），429 不帶 Retry-After（vendored `server.py` 的說明）。
- 子程式的做法（vendored，沒改）：cookie 快取 10 分鐘、鍵含 URL 與帳密指紋；同一個子程式同時的登入合成一次；401 時重登一次；
  429 時退避 1、2 秒重試兩次，仍 429 的那次工具呼叫回 `BACKEND_HTTP_ERROR status=429`。
- 每帳號一個子程式，所以 N 個帳號接同一個 Dashboard 就是 N 次登入（真子程式測試看得到：兩個帳號、兩次登入）；它們都從 add-on 的
  同一個位址連線，共用那 10 次。Hermes 最多 4 個子程式，平常碰不到；子程式反覆重啟或同一位址還有別的程式在登入時才會碰到。
- PaaS 同一個 Pod 的子程式與管理端 Dashboard 代理也共用 Pod 的位址；HA 沒有管理端代理（#63），登入只來自子程式。不做跨子程式的
  登入協調（子程式之間不共用狀態）。

### 4.3 長 chat 佔名額（契約 #136）

- `hermes_chat` 在子程式裡最長 300 秒（vendored 預設，沒有帳號設 `HERMES_MCP_CHAT_TIMEOUT`，測試釘住），閘道 tools/call 最長 330 秒
  （`gateway.CALL_SECONDS`，#5）。整段佔自己帳號的一個轉送名額：預設帳號 32、額外帳號 16，等 1 秒，排隊 32／16（契約第 5 節）。
- 一個帳號的名額都被長 chat 佔住時，只有它自己的請求排隊或被拒；別的帳號照常。換身分、輪替、撤銷、刪除只結束該帳號進行中的 chat
  （舊 token 的請求，HM-08、HM-12）。
- 換身分時怎麼結束（審查 S-2）：HM-12 先停舊子程式、再寫入、再發布。已經送到子程式的 chat 在停子程式時就結束：子程式的連線中斷，
  閘道回自己的 `-32004`（Hermes 的 chat 是 SSE：HTTP 200 加一則事件），不是 401。審查用真 Supervisor、真子程式與本機假 Hermes 量到
  的就是這樣（文字是 `CHILD_CONNECTION_TEXT`，見第 12 節）。子程式結束得比閘道判斷快時（閘道看子程式有沒有停最多 0.25 秒），新 token
  先發布，chat 收到的是 `-32005`（權杖已換）：本片用替身做過 3 次都是這樣，但這要看排程先後，沒有寫成測試。還在排隊、沒送到子程式的
  請求在發布時結束（Bearer 401、密鑰網址 404）。
- PaaS：chat 預設 90 秒、閘道 110 秒回 `-32001`；每帳號 64 條連線、等 10 秒。

### 4.4 開關關

- `identity_rebound` 每次呼叫時讀 `features.enabled`，Hermes 沒開通就回 False：存檔照今天（先寫入再重起、不換 token、回應沒有新欄位）。
  `test_switched_off_a_hermes_identity_change_keeps_todays_answer_order_and_token` 在 Hermes 已在 `IDENTITY_BOUND` 的情況下驗這點。
- 面板：`identityBound` 只在開通時用（`profile !== null`）；沒開通時面板與請求逐位元照今天。
- HM-01 黃金回歸（8 個產品、fresh 與 configured）、MCP 與管理契約凍結、`tests/test_upgrade_zero_rewrite.py` 都照過（第 8 節）。

## 5. PaaS 對照

| PaaS | HA | 歸屬 |
|---|---|---|
| Hermes 不綁身分（只有 Odoo #131、Nextcloud #154；`origin/main` 另有 K8s #157，HA 沒有這個產品）；通用判斷要舊連線每個身分欄位都有值 | 開通後綁 `gateway_url`、`dashboard_url`、`dashboard_username`；存了連線就算有身分（第 4.1 節） | 加嚴，#134（DQ-40 ⑩） |
| 管理端 Dashboard 代理，cookie 快取鍵帶帳號，刪帳號清除（`test_dashboard_proxy_cookie_follows_profile_and_credential_changes`） | 沒有管理端代理 | 既有，#63 |
| 健康檢查的 Dashboard cookie 跟著帳號（`test_dashboard_health_cookie_follows_profile`） | 每帳號一個子程式，cookie 跟著子程式；Hermes 的健康檢查只打 Gateway | `tests/test_hermes_multi_profile.py` 真子程式一案（`paas-test-mapping.md` 第 2 案指到的暫定名，就是這個檔） |
| 子程式 `--port {port}` | launcher `--port`（HM-04；預設帳號不帶） | 部署，FM-38 |
| chat 90 秒、閘道 110 秒、連線池 64／等 10 秒 | chat 300 秒、閘道 330 秒、轉送 32／16 等 1 秒 | #5、#15、#136 |
| 政策由代理執行，Hermes 存政策不重啟（只有 n8n 重啟） | 同（閘道執行，不重啟） | 不是差異；驗收矩陣 T-07 寫明 |

### 5.1 PaaS 變動清單（審查 S-4 補；計畫 §11.1、§12.0 第 2 點）

本機唯讀 PaaS repo（`paas-mp-research-20261114`；`git log --oneline 69ac425..origin/main -- <相關檔>`，`origin/main`＝`5ef1046`，
2026-11-18 03:00 UTC 的 #159 合併）。沒有 fetch（那個 clone 的 remote 是正式 Gitea）；GitHub 鏡像唯讀查過，2026-11-19 的 `main` 也是
`5ef1046`，之後沒有新 commit。`69ac425..5ef1046` 共 51 個 commit。

查的路徑：`apps/hermes/`、`Pc/config/`（`patch_connection_bound`）、`Pc/connection_apply.py`、`Pc/proxy.py`、`Pc/gateway_pool.py`、
`Pc/mcp_access.py`、`Pc/launch_policy.py`、`Pc/profiles.py`、`Pc/routers/`、`apps/nextcloud/nextcloud_mcp_admin/`、
`apps/odoo/odoo_mcp_admin/routers/config.py`，以及另外兩個產品的身分綁定（Nextcloud #154、K8s #157）。

| commit | 內容 | 對本片 |
|---|---|---|
| `34769c2`（#156） | `hermes_cron` 說明補 `enabled=false` 與 trigger 的實際行為（`apps/hermes/hermes_mcp_server/server.py`、README、CHANGELOG） | HM-33 已對齊（vendored `server.py`），和本片無關 |
| `6748353`（#138） | Hermes cron 停用建立的契約（create 同時送 `paused`） | HA 的 #85（`b50f1c7`）已做，和本片無關 |
| `3b135ca`、`1637a0f`（#155） | 只動 `apps/hermes/tests/test_request_structure_guard.py`（JSON 結構守門、位元組預算第三輪） | HM-31 已對齊，和本片無關 |
| `7ba572d`、`e6971c0`（#155） | `Pc/proxy.py`、`gateway_pool.py`、`profiles.py`：請求內容位元組預算 | HM-31 已對齊；名額與轉送逾時（#136 的 PaaS 欄）沒變 |
| `19f36e2`（#148 的文件更正） | `Pc/proxy.py`、`gateway_pool.py` 的說明（斷線保護範圍、排隊請求的記憶體估算） | 只改文字；HM-14 對照的 `-32004` 規則不變 |
| `0f94aa4`、`0f43fd3`、`4f1a77f`（#154、#152） | Nextcloud 換使用者或網址撤銷舊網址（走核心 `save_bound_connection`）、`base_url` 過 SSRF、遮罩 | HM-22 的事；核心判斷沒改 |
| `7cbf9a3`（#157）、`4b133c5`（#158）、`5ef1046`（#159） | K8s：kubeconfig 檢查、SSRF、換身分換網址（`identity_connection_keys` 經 `save_bound_connection`）、上游升版、刪帳號清 `/tmp` | HA 沒有 K8s；同樣走核心的判斷 |

`Pc/config/store.py` 的 `patch_connection_bound` 在 `69ac425..5ef1046` 沒有改（`git log` 該目錄是空的）；第 4.1 節對照的「舊連線每個
身分欄位都有值才換」照舊。PaaS 這段期間 Hermes 仍不綁身分，#134～#136 的 PaaS 欄不用改。

## 6. 測試（先紅後綠）

`tests/test_hermes_multi_profile.py` 的 23 案（都跑在 HM-01 的 log 掃描下，token、child token、Gateway key、Dashboard 密碼、帳號名稱都在
掃描清單；審查後改 T-12 一案、加還原核對關卡 2 案）：

| 案 | 開關 | 驗什麼 |
|---|---|---|
| `test_hermes_is_bound_to_its_gateway_and_dashboard_identity` | — | `hermes` 在 `IDENTITY_BOUND`、旋轉欄位不含秘密、repo 沒開通 Hermes |
| `test_a_changed_hermes_identity_stops_the_old_child_then_rotates_the_token_in_one_write`（7 案） | 開 | `gateway_url`（兩種路由；換來源帶 key）、同來源換路徑、`dashboard_url`（兩種路由；換來源帶密碼）、`dashboard_username`（兩種路由）：停 → 一次寫入 → 發布 → 新子程式帶新連線；回應、`ETag`、歷史、分派器路由、兩條入口的舊 token、預設帳號不動 |
| `test_adding_or_clearing_the_dashboard_rotates_the_token` | 開 | 補上換、只清一部分 400 不動、清空換、清連線換且不起子程式；三筆 rotate 歷史 |
| `test_a_secret_change_or_the_first_setup_keeps_the_hermes_token` | 開 | 初次設定、只換 key、只換密碼、整份同身分、尾斜線：都不換、順序照今天；撤銷後換身分不發新 token |
| `test_the_default_hermes_profile_is_bound_to_its_identity_too` | 開 | 預設帳號也綁；額外帳號不動 |
| `test_switched_off_a_hermes_identity_change_keeps_todays_answer_order_and_token` | 關 | 四種存檔（含換來源沒帶密碼、清空 Dashboard）都照今天 |
| `test_a_hermes_identity_change_waits_for_the_profiles_restore_review`（2 案：兩種路由） | 開 | 審查 S-6 加。還原時開關關、之後重發了預設帳號的權杖，開通後還沒核對：改 `dashboard_username` 回 409 `restore_review_required`，子程式不停、目錄樹不變、權杖照舊可用、沒有換身分的 WARNING；只換 `gateway_api_key` 照常存（今天的順序）、核對照樣在等（同 `tests/test_restore_review.py` 的 Odoo 案） |
| `test_every_profiles_child_has_its_own_port_environment_and_directory` | 開（＋關的對照） | argv、環境逐欄、目錄、沒有 chat 逾時變數、沒有別帳號的值 |
| `test_each_profiles_token_reaches_only_its_own_child_and_every_other_token_is_refused` | 開 | 三個帳號各到自己的子程式；換身分換掉的、撤銷的、未知的（T×43）、child token、C×43 兩條入口都被拒且不到子程式；密鑰網址不看 `Authorization`、Bearer 不看 `X-MCP-Profile` |
| `test_switched_off_only_the_default_profiles_token_is_served` | 關 | 休眠帳號的 token 在開機時已撤銷、被拒；只有預設帳號的 token 可用 |
| `test_long_chats_hold_their_own_profiles_slots_and_no_other_profiles` | 開 | 330 秒的轉送逾時；B 的 16 個名額被 chat 佔住時下一個 `-32003`；預設帳號與 C 的 chat 立刻回答 |
| `test_switched_off_long_chats_hold_todays_32_slots` | 關 | 照今天：同樣 330 秒轉送、32 個名額都被 chat 佔住時下一個等 1 秒回 503 `{"error":"request denied"}`、不到子程式 |
| `test_an_identity_change_ends_its_own_profiles_long_chat_only` | 開 | 審查 S-2 改。B 的 chat 照 Hermes 子程式的回法（SSE），B 換身分時子程式先停：替身照真的 Supervisor，連線先斷、閘道回答之後才算停。B 的 chat 在存檔回答之前就結束：HTTP 200、一則 `-32004`（`CHILD_CONNECTION_TEXT`）；預設帳號的長 chat 照常完成；舊 token 兩條入口都拒、新 token 到新子程式。原本斷言的 401 只有停不下 MockTransport 子程式的替身才會出現 |
| `test_saving_one_profiles_policy_changes_only_its_tools_and_restarts_no_child` | 開 | 停用與再啟用 `hermes_chat`：只改 B；沒有子程式重啟；別帳號的 state 不動 |
| `test_switched_off_a_policy_save_restarts_no_hermes_child` | 關 | 同上，單帳號 |
| `test_real_children_keep_their_dashboard_cookies_and_long_chats_apart` | 開 | 真 Supervisor、`apps/hermes/launch.py` 的真子程式兩個、一個本機假 Hermes（第 3 節） |

先紅後綠（本機，一般使用者 uid 1000；AMD EPYC 7713；CPython 3.13.15；node 22.23.3；TMPDIR 用 `/tmp/ha-mp-*` 短路徑，跑完刪掉）：

1. 基準程式＋新測試檔（還沒 commit）：**15 紅、5 綠**（97 秒）。
   - 紅在預期的地方：綁定一案、換身分 7 案、補上與清空、預設帳號、開關關一案（它斷言 `hermes` 在 `IDENTITY_BOUND`）、矩陣一案與長 chat
     換身分一案（都要先換身分）、真子程式一案（cookie、長 chat、child bearer 都過，紅在最後換 Dashboard 使用者那段）。
   - 另 1 紅是測試自己的期望寫錯：政策一案以為被拒的回答沒有 `data`，實際是 `{"tool":"hermes_chat"}`。改測試後這案在基準上就綠
     （政策行為本來就成立，本片只釘住），commit 前修好。
   - 5 綠是本來就成立的結構：只換秘密不換、環境各自、開關關的矩陣、長 chat 佔名額、開關關的政策。
2. 改 Odoo 的測試與面板測試（`2010f06`，測試 commit）：`profiles.test.mjs` 2 紅（`identityBound` 的期望值、S-7 提示的 Hermes 案）。
3. `products.IDENTITY_BOUND` 加 `hermes`：`tests/test_identity_fields.py` 的面板同步一案紅（伺服器有 Hermes、面板沒有）。
4. `contracts.js` 加 `hermes`：node 30／30、Python 同步綠；`tests/test_hermes_multi_profile.py` 20／20 綠（7.2 秒；真子程式一案 3.8 秒）。
5. 等核對說明（面板）：先寫 HM-24 一案（紅：Hermes 拿到 Odoo 的字），改 `api.js`＋`identityChange` 後綠；node 全部 119 案綠。
6. 審自己的測試時補開關關的長 chat 一案（`test_switched_off_long_chats_hold_todays_32_slots`）：釘住今天的行為，和本片的程式改動無關
   （和第 1 步的 5 綠一樣是既有的結構；沒有在基準上單獨跑過）。
7. 審查後（2026-11-19，第 14 節）：
   - S-2：改寫 T-12 一案（Hermes 回法的 SSE 替身 `Severed`、停子程式時先斷線的 `StoppingSupervisor`）。最後的程式上綠（0.4 秒）；
     替身不斷線（＝原本的替身，M8）就紅：存檔回答時 B 的 chat 還沒結束；換身分改成先寫入、發布再停子程式（M9）也紅：B 的 chat 收到
     `-32005`。
   - S-6：新的還原核對關卡 2 案在最後的程式上就綠（關卡是 HM-13c 的通用程式，本片只釘住它對 Hermes 也成立）；`IDENTITY_BOUND` 拿掉
     `hermes`（M10，＝基準）2 案都紅：存檔回 200、沒有被關卡擋。
   - 整檔 23 案 9 秒（真子程式一案 3.7 秒）。

## 7. 突變（一次改一處、跑相關測試、`git checkout` 還原；都在 commit 之後做，還原後 `git status` 沒有程式改動）

| 突變 | 結果 |
|---|---|
| M0 `IDENTITY_BOUND` 沒有 `hermes`（＝基準） | 第 6 節第 1 步的 15 紅 |
| M1 補上或清空的欄位不算改變（兩邊都有值才比） | `test_adding_or_clearing_the_dashboard_rotates_the_token` 紅 |
| M2 Hermes 不帶 `--port` | `test_every_profiles_child_has_its_own_port_environment_and_directory` 紅 |
| M5 Hermes 存政策也重啟子程式 | 兩個政策案都紅 |
| M6 換身分不看開關 | `test_switched_off_a_hermes_identity_change_keeps_todays_answer_order_and_token` 紅 |
| 面板：等核對說明固定 Odoo 的字 | node HM-24 一案紅（第 6 節第 5 步） |
| M8（審查後；替身）停子程式時不斷線 | `test_an_identity_change_ends_its_own_profiles_long_chat_only` 紅（存檔回答時 B 的 chat 還沒結束） |
| M9（審查後）`gateway.rebind_identity` 先寫入、發布再停子程式 | 同一案紅（B 的 chat 收到 `-32005`）；順序本來也由換身分 7 案的事件順序擋 |
| M10（審查後）`IDENTITY_BOUND` 沒有 `hermes` | `test_a_hermes_identity_change_waits_for_the_profiles_restore_review` 2 案紅（200，沒被關卡擋） |

M8～M10 在審查後、測試 commit（`3828fcb`）之前做：程式檔用 `git checkout` 還原，測試檔用改之前的備份還原（`cmp` 相同），每次都看過
`git status` 只剩本輪要改的檔。另外做了一個不是突變的實驗：替身讓子程式立刻結束（不等閘道回答），3 次 B 的 chat 都收到 `-32005`
（第 4.3 節）；實驗的改動同樣從備份還原。

## 8. 本機檢查

| 檢查 | 結果 |
|---|---|
| `python3 scripts/secret_precheck.py --tools …/scan0414/tools` | gitleaks 8.28.0（釘版、驗過）；`c90b214..HEAD` 的全部 commit（第 13 節）：**OK，0 命中**（每加一個 commit 重跑） |
| `python3 scripts/ledger_precheck.py` | runtime-patches 180、runtime-sources 70、tool-surface 159 檢查，0 漂移；改到的四個列管檔帳本同 PR 更新；**result: OK** |
| `packaging/validate.py`（`ha-gh-release-20261117` 的 venv） | **PASS**：8 strict Supervisor-subset manifests… |
| `python -m unittest discover -s packaging -p 'test_*.py'`（短 TMPDIR） | 366 案 **OK**（skipped 5：非 root 允許的 skip），27～28 秒（改程式後與最後各跑一次） |
| `node --test packages/mcp-admin-ui/tests/*.test.mjs` | **119／119** |
| `scripts/tool_inventory.py`（不帶參數） | exit 0，沒有漂移（沒動 `apps/runtime`、`apps/*/launch.py`，不用重產） |
| pytest：新測試＋身分相關（`test_hermes_multi_profile`、`test_identity_fields`、`test_odoo_identity_rotation`） | 69 綠 |
| pytest：HM-01 黃金回歸、兩個契約凍結、`test_upgrade_zero_rewrite`、`test_odoo_multi_profile`、`test_new_origin_secret`、`test_saved_destinations`、`test_restore_review`、`test_panel_profile_api_shapes`、`test_connection_patch`、`test_configuration_status`、`test_health_backoff`、`test_unconfigured_connect` | 445 綠（142 秒） |
| pytest：較廣的一批（第 8.1 節；最後的程式與測試） | 1,583 案：**1,578 過**，5 紅都是要 root 的 `test_root_*`（454 秒） |
| HM-00 對照腳本 `check_hm00.py`（repo 外，唯讀） | C2（131 列、欄位與類型都對、PaaS 欄和 HA 欄都不同）、C3、C4、C5（登記 71 個測試檔）、C7、C8、C9 **PASS**。C1 不過是預期的（本片不是只改 `docs/`）。C6 不過和本片無關：本機 PaaS 研究 worktree 的 `origin/main` 已到 `5ef1046`（多了 K8s 的測試檔），`paas-test-mapping.md` 本片沒動 |

### 8.1 較廣的一批與只在 CI 跑的測試

- 較廣的一批（commit 前的最後一版，含開關關的長 chat 一案）：`tests/test_hermes_*.py`（15 檔）、`test_identity_fields`、`test_odoo_identity_rotation`、`test_odoo_multi_profile`、`test_new_origin_secret`、`test_saved_destinations`、`test_restore_review`、`test_panel_profile_api_shapes`、`test_profile_admin_api`、`test_profile_routing`、`test_profile_runtime`、`test_profile_quotas`、`test_router_passthrough`、`test_upgrade_zero_rewrite`、`test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`、`test_connection_patch`、`test_backend_loopback`、`test_origin_policy`、`test_dormant_profiles`、`test_restore_lock`、`test_tool_inventory`、`test_ledger_precheck`、`test_secret_precheck`、`test_child_bearer`、`test_child_port_param`、`test_admin_ui`、`test_profile_lifecycle`、`test_staggered_start`、`test_active_token_leases`、`test_restore_detection`：1,583 案，1,578 過，454 秒。
- 本機紅的 5 案都是 `tests/test_restore_detection.py` 要 root 的 `test_root_*`（`test_root_backup_restore_and_repair`、`test_root_start_without_a_restore_changes_nothing`、`test_root_marker_name_taken_by_a_directory[None]`、`[index]`、`test_root_the_container_probes_restore_stage_meets_the_entrypoint`）：一般使用者跑不了，和本片無關，只在 CI（root、0 skip）跑。
- 本機的測試鎖（`tests/conftest.py`，同一個使用者共用）同時被其他工作線的測試佔用，跑之前排隊等過幾次；沒有跳過任何測試。
- Playwright：本機這個 clone 沒裝 chromium，瀏覽器 spec 只在 CI 跑。本片沒加新的 spec；`restore-review.spec.mjs` 斷言的 Odoo 等核對說明
  逐字沒變。
- 真 Hermes 子程式一案在 CI 也跑（同 `tests/test_hermes_chat_timeout.py`、`tests/test_odoo_multi_profile.py` 的真子程式案）。本機 3.8 秒，
  `checks` 的時間影響很小；CI 秒數開 PR 後才知道。

### 8.2 審查後重跑（2026-11-19；最後的程式與測試，`e08bc52` 之上加本筆記）

| 檢查 | 結果 |
|---|---|
| `python3 scripts/secret_precheck.py --tools …/scan0414/tools` | gitleaks 8.28.0（釘版、驗過）；`c90b214..HEAD` 的 12 個 commit：**OK，0 命中**（加審查的 3 個 commit 後先跑一次 10 個；commit 本筆記後再跑一次 12 個） |
| `python3 scripts/ledger_precheck.py` | runtime-patches 180、runtime-sources 70、tool-surface 159 檢查，0 漂移；列管的檔多了 vendored `guards.py`（`runtime-sources.json` 與 tool-surface 同 PR 更新）；**result: OK** |
| `packaging/validate.py`（`ha-gh-release-20261117` 的 venv） | **PASS**（`d1fef47` 與 `e08bc52` 各跑一次） |
| `python -m unittest discover -s packaging -p 'test_*.py'`（短 TMPDIR） | 366 案 **OK**（skipped 5），27～28 秒（`d1fef47` 與 `e08bc52` 各跑一次） |
| `node --test packages/mcp-admin-ui/tests/*.test.mjs` | **119／119**（這一輪沒改面板；兩次） |
| `scripts/tool_inventory.py` | `--write` 重產後，diff 只有 `guards.py` 的摘要（`tool-surface.md` 不變）；不帶參數檢查 exit 0 |
| pytest：`tests/test_hermes_multi_profile.py` | 23 過（8.7 秒；真子程式一案 3.7 秒） |
| pytest：較廣的一批（第 8.1 節那 46 檔＋`tests/test_gateway_stream_endings.py`；`d1fef47` 的程式與測試） | 1,620 案：1,614 過、6 紅（480 秒）。5 紅是要 root 的 `test_root_*`（同第 8.1 節）。另 1 紅是本輪自己造成的：`tests/test_backend_loopback.py::test_no_child_code_names_or_removes_the_variable`（HM-20 審查 S-3 的守門：`apps/` 底下只有兩個政策檔與 n8n spec 可以點名 loopback 的環境變數），`cd284ff` 的 `guards.py` 註解點名了它。`e08bc52` 改寫成不點名、重算兩本帳本的摘要 |
| pytest：改寫註解後重跑受影響的檔（`tests/test_backend_loopback.py`、`test_tool_inventory.py`、`test_ledger_precheck.py`、`tests/test_hermes_*.py` 15 檔；`e08bc52`） | **294 過**、0 紅（`test_no_child_code_names_or_removes_the_variable` 綠；pytest 報 1,262 秒，大部分是收集之後在共用鎖上排隊） |
| HM-00 對照腳本 `check_hm00.py`（repo 外，唯讀；`d1fef47`，之後只改了 `guards.py` 的註解與兩本帳本的摘要） | C2（131 列）、C3、C4、C5（71 個測試檔）、C7、C8（DQ-05 改寫後照過）、C9 **PASS**；C1、C6 不過的原因同第 8 節（不是只改 `docs/`；PaaS `5ef1046` 多了 K8s 的測試檔） |
| Playwright | 本機沒有 chromium，只在 CI 跑；這一輪沒改面板 |
| `git diff --check`、雙向控制字元 | 沒有 |

- 本機的測試鎖這一輪也被其他工作線佔用（HM-25 的整套 pytest、HM-26 與 HM-23 的批次），排隊等過；沒有跳過任何測試。改寫註解後的重跑
  用只在本機的 pytest plugin 在核心的鎖佇列裡等（`scratchpad/HM-24/plugins/hm24_lockwait.py`，不在 repo、跑完刪掉；拿到鎖立刻放掉，
  讓 `tests/conftest.py` 的 fixture 接手，互斥不變；HM-23、HM-26 用同樣的做法）。

## 9. Hermes 開通那一版的 CHANGELOG 句子（交給 Hermes 的升版 PR）

句子只放在這裡（審查 S-7：受開關管的片照 `unreleased-changes.md` 檔頭第 2 點不寫 CHANGELOG 句子；那份清單的第 3.3 節只留一行指過來，
第 4.2 節照舊一列）。共通的開通項目（帳號選單、`X-MCP-Profile`、名額、看門狗、回覆工作執行緒、還原等）照計畫 §7.2 由升版 PR 另寫。
句子最後的字由發版片定；第 2 句的「補上 Dashboard 也換」要等使用者確認（第 12 節），選 (b) 就改那半句：

```text
- Multiple profiles for Hermes (HM-24): besides the default profile, up to 3 more profiles, each with its own MCP URL and token, its own Hermes Gateway and Dashboard connection, its own tool policy and its own Hermes MCP child (its own port, environment and working directory).
- The MCP token of a profile is bound to its Hermes identity: saving another Gateway URL, Dashboard URL or Dashboard user rotates that profile's token, adding the Dashboard to a Gateway-only connection or clearing it included; both old URLs stop working at once and the panel says where to copy the new token. Changing only the Gateway API key or the Dashboard password, and the first setup, keep the token.
- Each profile's child logs in to the Hermes Dashboard with its own account and keeps its own session cookie (in memory, 10 minutes). Hermes limits Dashboard logins per source address (10 a minute, successful ones included), and every profile of this add-on connects from the same address: profiles pointed at one Dashboard share that limit.
- A `hermes_chat` turn (up to 300 s; the gateway waits up to 330 s for a tool call) holds one of its own profile's forwarding slots while it runs: 32 for the default profile, 16 for each additional one. When all of a profile's slots are busy, its next request waits 1 s and then gets JSON-RPC error -32003 with `Retry-After: 5`; other profiles are not affected. Saving another identity, rotating, revoking or deleting a profile ends that profile's chats in progress only.
```

Hermes 的下一版若還沒開通：本片沒有可見變化，不寫 CHANGELOG（發版交接清單第 4.2 節加了 HM-24 一列）。第 4 句審查後補「Saving another
identity」（換身分也只結束自己帳號的 chat）；chat 收到的錯誤碼（`-32004` 或 `-32005`）不寫進 CHANGELOG，寫在驗收手冊與契約 #136。

## 10. 之後 HAOS 實測要的（Hermes 的升版 PR；`docs/operations/acceptance.md`「Hermes 開通（HM-24）」）

- **要使用者批准的後端身分**：一台測試用 Hermes Agent（Gateway 與 Dashboard；PaaS 正式站用 v0.22.5）；每個帳號一組自己的 Gateway API key
  與 Dashboard 帳號：預設帳號＋至少 2 個額外帳號（T-04 的 N×N 最多預設＋3），另一組換身分用的 Dashboard 帳號（T-03）。一台 Hermes 若只能有
  一組 Gateway key 或一個 Dashboard 使用者，就要多台測試用 Hermes（還沒確認，第 12 節）。只用合成名稱；建立與刪除每一組都要批准，驗完刪、
  留清理證明（T-29）。並行長 chat 會花模型費用：用免費模型或測試 Gateway，先問使用者。
- **T 列**：照 `acceptance.md` 的表（Odoo 首發標「是」的那些；T-10 是 Odoo 的審批、T-22 是 n8n，不適用 Hermes），另外加：
  - T-02：Hermes 的上限 3（第 4 個額外帳號 409 `profile_limit_reached`；審查 S-5 後寫進 `acceptance.md` Hermes 一節第 2 點）。
  - T-03：三個身分欄位各換一次、補上與清空 Dashboard 各一次：兩條舊網址都失效；只換 key 或密碼不換（#134）。
  - T-04：每個帳號用自己的 Hermes 身分留標記，只看得到自己的。
  - T-07：存一個帳號的政策只改它的工具清單，每個子程式 PID 不變。
  - T-12、T-19：長 chat 進行中換身分或撤銷只結束該帳號的；名額滿時 `-32003`、別帳號照常（#136）。換身分時那個 chat 收到 `-32004`
    （子程式先停；新 token 先發布時是 `-32005`），不是 401，照實記下收到的是哪一個與它的文字（審查 S-2）。
  - T-13、T-14、T-23：childkill、冷啟動、child bearer（容器階段 `packaging/container_profiles.py` 對 Hermes 一樣適用：預設子程式沒寫
    `--port` 就當 3000）。
  - Dashboard 登入：兩個以上帳號接同一個 Dashboard 時各自只登入一次；記下有沒有 429（#135）。
  - T-17：**至少 60 分鐘負載量測**定每子程式 MiB（計畫 §9、C3-SF-12；PaaS 量到 RSS 90 → 160～168 MiB、負載停了不回落，R02 C-04）。
    量法在 `acceptance.md` Hermes 一節第 7 點（審查後加了 T-02 一點，原第 6 點往後移）：目標硬體、預設＋3 個額外帳號、混合呼叫、
    每 30 秒記 RSS／PSS 與 MemAvailable、停止後再記 10 分鐘。
    結果要改 `profiles.CHILD_MEMORY_MIB['hermes']`（暫定 160）時另開功能 PR（HM-31 的位元組預算會跟著重算），升版 PR 不改常數。

## 11. 契約第 9 節列號（暫定）與會衝突的地方

- 本片用 #134～#136（基準最後是 #128）。HM-21、HM-22、HM-23、HM-25、HM-26 同時在準備，也可能加列：**後合併的一方接在當時最後一列之後
  重編**（同 HM-27 的做法），並一起改引用這幾個列號的地方：契約開頭的狀態、第 3.1 節 `backend` 列（#134；審查後 ③ 也指 #136）、
  第 9 節說明段本片那行、第 10 節本片兩列；`acceptance-matrix.md` T-03（#134）、T-12、T-19（#136）；`threat-model.md` 第 3 節（#135）；
  `decisions.md` DQ-05（#134）；`docs/operations/acceptance.md` Hermes 一節（#134～#136）；`docs/operations/update-backup-rollback.md`
  「細節」那行（#134，審查後）；本筆記；程式與帳本：`products.py` 註解（#134）、`contracts.js` 註解（#134）、
  `tests/test_hermes_multi_profile.py` 的說明（#134～#136）、帳本 `products.py` 那筆的 `change`（#134）。
- 和 HM-22（Nextcloud 開通）一定會衝突：`products.IDENTITY_BOUND`、`contracts.js` 的 `identityBound` 與 `identityChange`（Nextcloud 要補
  它的說法，`profiles.test.mjs` 的新案會擋）、`profiles.test.mjs` 的 `deepEqual`、`tests/test_odoo_identity_rotation.py` 的 `OTHERS`、
  契約第 3.1 節 `backend` 列、`identity_fields.py` 的註解。後合併的一方兩邊都留。
- 和 HM-18（文件定稿，PR 未合併；計畫裡 R1 前合併，本片屬 R3，幾乎一定較晚合併）會衝突，審查 S-3 補：
  - 同時改的檔：`contract.md`、`decisions.md`、`acceptance-matrix.md`、`threat-model.md`、`unreleased-changes.md`、
    `docs/operations/acceptance.md`、`docs/operations/update-backup-rollback.md`（HM-18 在本片改的四處旁邊加了好幾段）。後合併的一方兩邊都留。
  - HM-18 分支上有三處只寫 Odoo，本片合併時要把 Hermes 補進去：契約第 1.4 節第 16 點（開通後預設帳號會變的事：加一句 Hermes 換
    `gateway_url`、`dashboard_url`、`dashboard_username`，補上或清空 Dashboard 也算，只換金鑰或密碼不換）；`docs/operations/guide.md`
    「換後端身分會換權杖（Odoo）」整節（標題與內文加 Hermes）；`update-backup-rollback.md` 的還原核對（本片已改的四處，HM-18 的版本照舊只寫 Odoo）。
  - repo 外：請主對話在計畫 §7.2 第 7 點補 Hermes 一句（本片不能改計畫）。
- 和 HM-23（EMQX 開通）的帳本衝突：HM-23 也改 `docs/tool-surface.json` 與 `docs/provenance/runtime-sources.json`（EMQX 的 vendored 檔），
  本片審查後也改這兩本（`guards.py` 的摘要，S-1）。照帳本規則，後合併的一方 merge 之後重產 tool-surface、重算摘要、重跑 CI。
  `runtime-patches.json` 本來就和 HM-22、HM-23、HM-25、HM-26 都會衝突，做法相同。
- `deviation-trace.md`、`paas-test-mapping.md` 是 repo 外的產生器寫的（檔頭寫明不要手改）：本片沒動。下次文件同步重產時：FM-86 加
  #134～#136、FM-153 加 #134 與 `tests/test_hermes_multi_profile.py`；`paas-test-mapping.md` 第 2 案的「暫定名」拿掉（改產生器規格）。

## 12. 還沒解決、需要使用者決定的

- **要使用者確認，確認前不合併**（審查 MF-1；`decisions.md` DQ-05 的狀態欄與第 4 節）：補上 Dashboard（原本只有 Gateway）也換 token
  （第 4.1 節）。照「每條網址永久綁一個後端身分」這樣做；DQ-40 ⑩ 推不出來、PaaS 的通用判斷也不會換，是本片自己的選擇；代價是事後才補
  Dashboard 時用戶端要換網址。清空也換照 HM-12 的 Odoo 規則，不用另問。其他做法：
  - (b)「初次補上 Dashboard 不換」，清空仍要換（不然可以繞過）。要改的地方（審查 S-8 補全）：程式 `products.identity_rebound` 的判斷
    與它的說明、`products.py` 的 `IDENTITY_BOUND` 註解；面板 `contracts.js` `identityChange.hermes` 的「補上或清空 Dashboard 也算」與
    `profiles.test.mjs` 的期望文字；測試 `test_adding_or_clearing_the_dashboard_rotates_the_token`（與測試檔開頭的說明）；契約第 3.1 節
    `backend` 列與 #134；`decisions.md` DQ-05（結論、狀態欄、第 4 節那列）；`acceptance-matrix.md` T-03 與測試登記表那列；
    `docs/operations/acceptance.md` Hermes 一節第 3 點（T-03）；`docs/operations/update-backup-rollback.md` 四處的「補上或清空 Dashboard
    也算」；`threat-model.md` I11；本筆記第 4.1 節與第 9 節第 2 句（CHANGELOG）；帳本裡改到的檔的摘要。
  - (c) 照搬 PaaS 的通用判斷（舊連線每個身分欄位都有值才換）：只有 Gateway 的帳號連換 Gateway 網址都不換，不建議。
  - 使用者定了：DQ-05 的狀態欄改成「使用者 2026-11-xx 確認」，第 4 節那列刪掉；契約 #134 的「待使用者確認」拿掉；選 (b) 照上面的清單改。
- **記給 HM-29／HM-14 追補（審查 S-2，不在本片改）**：換身分時主動停子程式，進行中的請求收到的 `-32004` 文字是 `CHILD_CONNECTION_TEXT`
  （「子程式仍在執行、請確認後重試」），但 token 其實已經換了，用舊網址重試只會拿到 401／404。這是 HM-14 `interruption_text` 的問題：
  閘道只看子程式在 0.25 秒內有沒有停，主動停下而且 token 要換的情況沒有自己的說法（`CHILD_STOPPED_TEXT` 說會自動重啟、
  `CHILD_HALTED_TEXT` 說目前沒在重啟，也都不對）。
- **要使用者批准**：之後 HAOS 實測的後端身分（第 10 節）、目標硬體上至少 60 分鐘的負載量測、並行長 chat 的模型費用。
- **還沒確認**：一台 Hermes Agent 能不能有多組 Gateway key 與多個 Dashboard 使用者（決定 T-04 要幾台測試用 Hermes）。
- Dashboard 登入限流共用只寫進文件，不做跨子程式的登入協調（計畫 §9 寫「共用」）；HAOS 實測若看到 429 再提。
- Playwright：沒加 Hermes 的瀏覽器 spec（面板的 Hermes 行為由 node 測試涵蓋；換 token 的提示本來就不分產品）。

## 13. commit

| commit | 內容 |
|---|---|
| `2010f06` | test(hermes)：新測試檔、Odoo 測試拿掉 Hermes、面板測試（這個 commit 上是紅的） |
| `c6947be` | feat(core)：`IDENTITY_BOUND` 加 Hermes、面板 `identityBound`／`identityChange`、`api.js` 的等核對說明、帳本 |
| `0a6257f` | docs(multi-profile)：契約、驗收矩陣、驗收手冊、威脅模型、決策紀錄、發版交接清單 |
| `52fa261` | test(hermes)：開關關的長 chat 一案（自己審測試時補） |
| `35bf640` | docs(multi-profile)：#134 的理由補 PaaS 通用判斷的差別、測試登記表補開關關的長 chat |
| `092fe49` | docs(provenance)：本筆記 |
| `b742ef7` | docs(provenance)：這張表與第 8 節的最後檢查 |
| `3828fcb` | 審查後：test(hermes)：T-12 照真的順序（`-32004`）、Hermes 的還原核對關卡 2 案（S-2、S-6） |
| `cd284ff` | 審查後：docs(hermes)：vendored `guards.py` 的 loopback 註解、`runtime-sources.json` 與 tool-surface 的摘要（S-1） |
| `d1fef47` | 審查後：docs(multi-profile)：DQ-05 待確認、還原手冊補 Hermes、`-32004`、T-02、CHANGELOG 句子移回本筆記（MF-1、MF-2、S-2、S-5～S-7） |
| `e08bc52` | 審查後：docs(hermes)：`guards.py` 的註解改寫成不點名 loopback 的環境變數（較廣的一批抓到 `test_no_child_code_names_or_removes_the_variable` 紅），兩本帳本的摘要重算 |
| 本筆記的下一個 commit | 審查後：docs(provenance)：第 5.1、14 節與跟著改的各節、第 8 節重跑的檢查 |

commit 照 DQ-36 不加署名行；用 clone 設定的身分 commit。審查前沒有 push；審查處理完由收尾步驟 push（第 14 節）。

## 14. 審查與處理（2026-11-19）

- 獨立審查（2026-11-19，結果由收尾步驟轉交）判定**修正後通過**：必修 2 項（MF-1、MF-2）、建議 8 項（S-1～S-8），全部採用，沒有不處理的。
- 先核對再改：S-2 用替身照真的順序重做（審查用真 Supervisor、真子程式量到的 `-32004`，替身也得到同一個回答）；另外做了「子程式立刻結束」
  的替身實驗 3 次，都是 `-32005`（新 token 先發布），照實寫進契約 #136 與驗收手冊，但沒寫成測試（要看排程先後）。S-4 在本機唯讀 PaaS
  repo 重跑，GitHub 鏡像唯讀確認 `main` 沒有更新的 commit。S-3 讀了 HM-18 分支（`d123173`）上那三處的原文。
- 處理的 commit：`3828fcb`（測試）、`cd284ff`（vendored 註解與帳本）、`d1fef47`（文件）、`e08bc52`（註解改寫：不點名 loopback 的
  環境變數）、本筆記的這個 commit。

| # | 意見 | 決定 | 怎麼處理 | 證據 |
|---|---|---|---|---|
| MF-1 | DQ-05 把「補上 Dashboard 也換」寫成已定（PaaS 的通用判斷不會換，DQ-40 ⑩ 推不出來） | 採用 | `decisions.md` DQ-05：結論分開寫「清空也換」（HM-12 的規則）與「補上也換」（本片的做法），狀態欄寫明**待使用者確認、確認前不合併 HM-24**；第 4 節加一列（選項指第 12 節；使用者定了要改的地方）；變更紀錄那列補記。契約 #134 標出待確認。確認要由主對話問使用者（本片不能代答） | `d1fef47` |
| MF-2 | 還原與回退手冊的核對關卡四處只寫 Odoo | 採用 | 四處改成「改後端身分的存檔（Odoo：網址、資料庫或使用者；Hermes：Gateway 網址、Dashboard 網址或使用者，補上或清空 Dashboard 也算）」，只改密碼補「Hermes：Gateway 金鑰、Dashboard 密碼」，「細節」加 #134。另外查到契約第 4.1 節 `restore_review_required` 列也只寫 Odoo，一起補 | `d1fef47` |
| S-1 | HM-20 交辦的 `guards.py` loopback 註解沒做也沒記 | 採用（第一個做法） | 改註解（開通後管理程序起子程式時打開 `backend_policy` 的 loopback 拒絕，對設定的後端也拒）；`runtime-sources.json` 重算 `local_sha256`、`modification` 補一句；tool-surface 重產，只有這個摘要變。第一次寫的註解點名了 `WOOW_MCP_DENY_LOOPBACK`，較廣的一批裡 `test_no_child_code_names_or_removes_the_variable` 紅（HM-20 審查 S-3 的守門），改寫成不點名、摘要再算一次。HM-23 也改這兩本，第 11 節寫明後合併的一方重產 | `cd284ff`、`e08bc52`；帳本預檢 OK、`tool_inventory.py` exit 0 |
| S-2 | T-12 斷言的 401 只有替身會出現；契約 ③ 對已送到子程式的請求不準 | 採用（兩點都做） | 測試照真的順序：SSE 替身 `Severed`、停子程式時先斷線的 `StoppingSupervisor`，斷言 B 的 chat 在存檔回答前收到 `-32004`（`CHILD_CONNECTION_TEXT`）。契約 #136、第 3.1 節 `backend` 列 ③、`acceptance.md` Hermes 一節第 6 點、驗收矩陣 T-12 與登記表寫明 `-32004`、不是 401（新 token 先發布時 `-32005`）。文字說子程式仍在執行的問題記給 HM-29／HM-14（第 12 節） | `3828fcb`、`d1fef47`；M8、M9 擋下 |
| S-3 | 第 11 節的衝突清單漏 HM-18 | 採用 | 第 11 節加 HM-18：同改的 7 個檔、HM-18 上三處只寫 Odoo（契約第 1.4 節第 16 點、`guide.md`「換後端身分會換權杖（Odoo）」、還原手冊）合併時要補 Hermes；計畫 §7.2 第 7 點請主對話補 | 本筆記 |
| S-4 | 少 PaaS 變動清單 | 採用 | 第 5.1 節：`69ac425..5ef1046`（51 個 commit）逐路徑列出；`patch_connection_bound` 沒改；#134～#136 的 PaaS 欄不用改 | 本筆記 |
| S-5 | Hermes 一節沒有 T-02 的數字 | 採用 | `acceptance.md` Hermes 一節加第 2 點：上限 3、第 4 個額外帳號 409 `profile_limit_reached`；T-13、T-14、T-23 容器階段的預設 port 3000。之後各點往後移一號（本筆記第 10 節跟著改） | `d1fef47` |
| S-6 | 伺服器端缺 Hermes 的還原核對關卡測試 | 採用 | 新案 `test_a_hermes_identity_change_waits_for_the_profiles_restore_review`（兩種路由）：核對前改 `dashboard_username` 409、什麼都不做，只換 `gateway_api_key` 照常存；驗收矩陣 T-21 與登記表 | `3828fcb`；M10 擋下 |
| S-7 | 開通版的 CHANGELOG 句子和發版交接清單規則 2 衝突 | 採用（第一個做法） | 句子只留在本筆記第 9 節（第 4 句補「Saving another identity」）；`unreleased-changes.md` 第 3.3 節改成一行指過來，寫明還沒開通的版本不寫、不刪；第 4.2 節照舊 | `d1fef47` |
| S-8 | 第 12 節選項 (b) 少算改動 | 採用 | 第 12 節列全（程式、面板與它的測試、測試、契約、決策、驗收矩陣、驗收手冊、還原手冊、威脅模型、本筆記、帳本） | 本筆記 |

- 審查意見裡的事實照寫進來：換身分時已經送到子程式的請求在 ① 停子程式時結束（第 4.3 節）；`-32004` 的文字問題不在本片改（第 12 節）。
- 這一輪的本機檢查見第 8.2 節。push：收尾步驟照任務的指令 push 到 `feat/ha-multiprofile-hm24-hermes-20261119`（遠端還沒有
  這個分支，是新分支；不 force、不 rebase），push 後的 head 見收尾回報。

## 15. 合併 `claude-delivery` `95b7e9d`（2026-11-19）

- 2026-11-19：用 merge commit 合入 `claude-delivery` `95b7e9d`（#122 HM-18 定稿、#123 P9 計畫產生器、#124 測試的 port 撞號；不 rebase、不 force push），PR #128 的 CI 才能再跑。衝突只在 `docs/multi-profile/` 五檔，都以 HM-18 的定稿為底、本片的增補接在後面：契約的標題與狀態、第 9 節說明段（本片第 129～131 列接在第 128 列後，列號照舊暫定）、第 10 節（HM-18 三列在前、本片兩列在後，另加一列合併列）；驗收矩陣與威脅模型的狀態、威脅模型第 3 節（本片那條接在 HM-18 改過的 Bearer 那條後）；`decisions.md` 照 HM-18 的已定 41 題、待定 5 題，本片 DQ-05 的細分與第 4 節那列自動合併照留（「補上 Dashboard 也換」仍待使用者確認），變更紀錄 HM-18 兩列在前；`unreleased-changes.md` 第 4.2 節 HM-18 補的兩列在前。照第 11 節的交辦補 Hermes：契約第 1.4 節第 16 點、`docs/operations/guide.md`「換後端身分會換權杖（Odoo、Hermes）」；HM-18 新寫的 `docs/runtime-configuration.md` 也只寫 Odoo，加一點 Hermes（還原手冊的四處自動合併照留）。第 12 節選 (b) 時這三處的「補上或清空也算」一起改，DQ-05 定案時第 1.4 節第 16 點的「待使用者確認」一起拿掉。`deviation-trace.md`：repo 外裝好的 `gen_trace.py`（`8f7abd977804fcdb…`）讀主線的契約逐位元重產主線的檔，讀合併後的契約停在「缺 [129, 130, 131]」；照 HM-18 的做法用暫存複本改三處重產（FM-86 加 #134～#136、FM-153 加 #134 與 `tests/test_hermes_multi_profile.py`、檔頭一句；產生器 `89e6095807822049…`、輸出 `faafb7de2a5c1dd0…`），和主線的檔只差檔頭、結論的列數、FM-86 與 FM-153 兩列、反查表的 #134～#136；這三處交主對話裝進產生器、更新 `SHA256SUMS`，本片的列重編時跟著改再重產（第 11 節最後一點的「本片沒動」不再成立；`paas-test-mapping.md` 照舊）。#123、#124 和本片的測試沒有交集：真子程式案用 `multi_profile_runtime.free_port()`（#124 照舊沒改它），沒有 import #124 拿掉的那幾份 `free_port()`；P9 計畫只讀 tool-surface 的工具，本片只改 `guards.py` 的摘要。合併後的檢查：帳本預檢 OK；`validate.py` PASS；packaging unittest 370 案 OK（skipped 5）；node 119／119（node 22、26）；`tool_inventory.py` 沒有漂移；pytest PYTEST_RESULT；HM-00 對照 C2（131 列）、C3、C4、C5、C7、C8（41／5）、C9 PASS，C1 不過是預期的（本片不是只改 `docs/`），C6 照舊（PaaS 鏡像前進到 `5ef1046`）；秘密預檢在 commit 之後跑，結果寫在收尾回報。

## 火車 B 整合時的列號重編（2026-11-25）

契約第 9 節的列號本片原用 #129～#131。整合分支（`integ/train-b-20261125`，基準主線 `092b1b5`，第 9 節最後一列是 #133）先收本片，三列依「後合併的重編」慣例改為 #134～#136；本筆記內與 `contract.md`、`acceptance-matrix.md`、`deviation-trace.md`、`decisions.md`、`threat-model.md`、`docs/operations/acceptance.md`、`docs/operations/update-backup-rollback.md`、帳本 `change` 的相關引用同步改號。內文「Odoo #131」指 PaaS 的議題，沒有改。

整合時另外照 2026-11-20 的定案（Hermes 換後端身分保留 MCP token，與 PaaS 一致）處理：`products.IDENTITY_BOUND` 維持 `{odoo, nextcloud}`、面板 `identityBound` 同，沒有 Hermes；HM-22 加進去的 Nextcloud 說明與本片的 Hermes 定案兩邊都留。上面第 4.1、12 節與審查處理的「Hermes 也綁身分、補上 Dashboard 也換」是 2026-11-19 的歷史描述，已被定案取代（契約開頭、`decisions.md` 開頭的定案）。
