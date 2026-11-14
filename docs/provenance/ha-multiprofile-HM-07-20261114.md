# HA 多帳號 HM-07 provenance：帳號資料層、開關常數、身分欄位分類（未接線）（2026-11-14）

## 結論

- 範圍：新模組 `features.py`、`profiles.py`、`identity_fields.py`（在 `packages/mcp-admin-core/mcp_admin_core/`），改 `config.py`
  （`existing_only`、建立路徑、擁有者檢查）與 `products.py`（`profile_initial_state`），加測試、uid 10001 探針、8 份升級樣本與帳本。
- **未接線**：沒有任何入口 import 這三個新模組（測試鎖住）；預設帳號的 `Store` 路徑一行沒改；8081、8099 的回應不變
  （HM-01 的黃金回歸與兩個契約凍結照過）。
- 新測試 5 檔 226 案：本機 225 通過；1 案要 root（uid 10001 的 mode／owner 證明），本機照預期失敗，只在 CI 驗（第 6 節）。
- 先寫測試：三輪先紅後綠都有紀錄（第 4.1 節）。臨時突變 61 個，59 個讓新測試失敗；沒擋到的 2 個是等價突變（第 4.2 節）。
- 兩個預檢：秘密預檢對本分支 11 個 commit（HM-01 的 9 個＋本片 2 個）0 命中，建置機同款的 HEAD 與全歷史掃描也 0 命中
  （第一次掃到 1 個誤判，改寫法後重掃，第 8 節）；帳本預檢 OK（`config.py` 照 HM-00 `ledger-tracking.md` 第 3 節不列管，列為「待人看」）。
- 全套 pytest（正式 conftest）：3958 案、0 skip、28 分 26 秒，3934 通過、24 失敗。失敗的是 2 個已知要 root 的（基準 1 個＋本片 1 個，
  第 6 節）和 22 個瀏覽器測試：這個 clone 的環境腳本沒裝 Playwright 的 Chromium（CI 的 `packaging/unit.sh` 會跑 `browser:install`）；
  裝好後單獨重跑那 3 檔，52 案全過。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-07（計畫 §12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm07-20261114` |
| 基準 | HM-01 分支 head `32ecac8`（＝`claude-delivery` `bb48449`＋HM-01；PR #90 待合併） |
| 依據 | 計畫 §3.3、§4.1～§4.4、§5.2、§5.4、§7.1、§7.3、§8.2（I2、I5、I6、I7）、§10.1、§10.3；HM-00 契約（PR #89）§1.2、§2.3、§3.6、§5、§7、§8、§9；`threat-model.md` |
| FM | FM-01、03、04、05、09、10、13、16、19、20、21、23、30、40、80、83、97、106 |
| 對齊的 PaaS | 沒有移植 PaaS 程式。索引規則、容量公式、`port` 衝突只停相關帳號、新帳號初值照 PaaS `woow-mcp-server` `packages/mcp-admin-core/mcp_admin_core/profiles.py` @`69ac425`（經研究報告 R03 §4、G1 與契約）；身分欄位照 PaaS #147 還原手冊的 `IDENTITY` 清單（R12、G5）。測試裡的 PaaS 欄只是對照，本 repo 不跑 PaaS 程式 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/features.py`（新） | `MULTI_PROFILE_PRODUCTS: frozenset[str] = frozenset()`（全部關）；`enabled(product)` 每次呼叫才讀集合，未知產品丟 `ValueError`（不默默當成關） |
| `Hc/profiles.py`（新） | 帳號索引 `profiles.json`（`{"version":1,"profile_index":{id:{label,port}}}`）的解析與編碼、讀（不 chmod）與原子寫（暫存檔＋fsync＋replace＋目錄 fsync，0600）、簽章（`st_dev`、`st_ino`、`st_mtime_ns`、`st_ctime_ns`、`st_size`、`st_nlink`）、DQ-12 判定（`IndexView.serves_mcp`、`offers_quarantine`）；布局 `Layout`（索引、收據、`profiles/`、帳號目錄與 `child/`、還原用的 5 個檔名）、隔離目錄與索引隔離的命名、`has_profile_data`；`profiles/` 的建立與掃描（不跟隨連結）；一致性報告；容量常數與 PaaS 公式、每帳號名額、8081 外框；名稱規則；id 與 port 配發 |
| `Hc/identity_fields.py`（新） | 九個產品每個存檔後端欄位的類別（`identity`／`secret`／`option`）；改了要換 token 的身分欄位；`ProductState` 每個欄位的類別（`credential`、`backend`、`policy`、`session`、`endpoint`、`record`） |
| `Hc/config.py` | `Store(directory, existing_only=True)`：不建目錄、lock 不帶 `O_CREAT`、缺 state 就 `ConfigError`；`Store(directory, create=<state>)`：目錄必須原本不存在（連懸空連結也不行）、lock 用 `O_EXCL`、一次寫入最終初值、失敗只清掉自己建的兩個檔與目錄。兩種模式都在任何 chmod 之前檢查目錄、lock、state 的擁有者是本 uid，並把放寬的權限收回 0700／0600。預設帳號的路徑（不帶參數）原樣保留 |
| `Hc/products.py` | `ProductStore(..., existing_only=, create=)` 傳給 `Store`，這兩種模式不遷移（舊 schema 原樣拒絕、不改寫）；`profile_initial_state(default, taken=())`；`NO_PROFILE_PRODUCTS`（DQ-28） |
| `tests/test_profile_index.py` | 索引規則 51 案（每案有 PaaS 對照欄：13 案 HA 比 PaaS 嚴、各寫明依據；9 案是 HA 自己檔案格式的規則）、順序、編碼、port 衝突、id、名稱、port 配發、容量常數與公式、讀寫、簽章、DQ-12 判定 |
| `tests/test_profile_store.py` | 新帳號初值（DQ-02，7 個可開的產品）、只開既有、建立的每一步故障注入（10 步）、擁有者與權限、不遷移、`profiles/` 目錄、整棵樹在 entrypoint 還原修復的上限內、uid 10001 證明（root） |
| `tests/profile_owner_probe.py` | 上一列 uid 10001 證明的探針：降權前 import 好所有模組，降權後只回報 JSON（不含 token） |
| `tests/test_profile_consistency.py` | 布局、隔離命名、掃描、缺目錄或讀不到的帳號、孤兒、撞號（含 token 與 child token 交叉）、`has_profile_data` |
| `tests/test_identity_fields.py` | 每個欄位都有類別（新欄位沒分類就失敗）、和模型的 `repr=False`、`backend_edit.FIELDS`、面板 `contracts.js` 對得上、FM-80 的表、換 token 的欄位 |
| `tests/test_upgrade_zero_rewrite.py` | 入口沒有 import 新模組（靜態掃描＋實際載入 4 個入口）；開關全部關、呼叫時才讀、子程序前置碼能打開；`bb48449` 寫出的 state 啟動正式 runtime 後一個位元組都沒變；單帳號安裝讀資料層什麼都不改；建帳號不寫預設 `state.json` |
| `tests/fixtures/upgrade_zero_rewrite/`（8 份＋README） | `bb48449` 的程式為已設定的 add-on 寫出的 `state.json`（照 owner_defaults README 正規化；做法見該 README） |
| `docs/provenance/runtime-patches.json` | 新增 `features.py`、`profiles.py`、`identity_fields.py` 三筆；`products.py` 更新摘要並補 HM-07 說明 |
| 本筆記 | — |

沒改：入口（`run_product.py`、`apps/n8n/run.py`、`packaging/management_launcher.py`、`packaging/entrypoint.py`）、`gateway.py`、
`lifecycle.py`、`health.py`、`apps/`、`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`
（沒動 `apps/runtime/*.py` 與 `apps/*/launch.py`，不用重產）、workflow、既有測試與替身。本分支沒有 `docs/multi-profile/`，也沒加。

## 3. 設計重點與解讀

- **索引的 port 規則（計畫內部不一致，本片的解讀）**：計畫 §4.2「每筆」列寫 port「不是 3000／8081／8099」＝整份壞，下一列又寫
  「撞預設 port 不算結構錯，只停相關額外帳號」（契約第 8 節同樣兩句）。本片：8081、8099（add-on 自己的 listener）＝整份壞；
  3000（預設子程式的 port）和 port 重複一樣只停相關帳號（`port_conflicts`，`disabled_reason=port_conflict`）。理由：PaaS
  `_port_collisions` 對撞預設帳號 port 就是這樣（R03 §4.9），設計稿 A-port 也把 3000 放在「不算結構錯」。8081／8099 整份壞比 PaaS 嚴，
  契約第 9 節還沒有這一列（第 12 節待辦 1）。
- **DQ-12 的判定**：`read_index` 回 `absent`／`ok`／`corrupt`；`recheck_index` 每個請求一次 lstat，簽章不符就 `modified`，而且
  `modified` 一直維持到重啟重讀（呼叫端保留回傳的 view）。`corrupt` 與 `modified` 都是 `serves_mcp=False`（8081 全部 503，含預設帳號）、
  `offers_quarantine=True`（面板照開、提供「隔離帳號索引」）。本片只做判定，HM-08、HM-10 接線。
- **讀索引不 chmod**：預設帳號的 `load()` 每次讀都 `fchmod 0600`；索引如果也這樣做，會改到簽章比對的 ctime。所以權限不是 0600 就判壞，
  不自動收緊。entrypoint 的還原修復會把檔案設回 0600（`packaging/entrypoint.py` 的 `_reown_restored`）。
- **簽章**：同 uid 改得回位元組、大小、mtime（`os.utime`），改不回 ctime；硬連結會改 nlink。同 uid 下不是安全邊界（DQ-37），只防誤改。
- **名稱規則**：去頭尾空白後 1～80 個 code point；拒絕 Cc、Cf（含 bidi、零寬）、Zl、Zp、Cs、Co、Cn；判重用 NFKC→casefold→NFKC；
  保留 `default` 與「預設帳號」。存在索引裡的名稱必須已經是正規化後的樣子（頭尾有空白就判壞）。名稱不進目錄名與 log（`log_id` 只給 id 前 8 碼）。
- **新帳號初值**（DQ-02 (a)）：新 token、新 child token（43 字元，不和預設帳號與 `taken` 裡的值重複；I2）；連線、憑證、endpoint 都空（I5）；
  政策照預設帳號當下的值，Odoo 四個子程式開關寫成「已儲存」、方法清單沒存過就維持沒存；不帶 `n8n_session`、owner-defaults 標記、
  token 歷史。OpenDesign、Odoo Manage 直接拒絕（DQ-28；HM-10 會先回 409）。
- **只開既有與建立**：額外帳號的 store 不會走「第一次開機補建全開 state」的路（FM-04 的 probe-ha #1）；建立失敗只清掉自己建的，
  目錄裡若多了別的東西就留下，變成孤兒（一致性報告列出，不開、不路由）。
- **一致性報告**只回報事實：`unavailable`（索引有、目錄或 state 讀不到）、孤兒、隔離目錄、其他項目數、port 衝突、撞號群組（token 與
  child token 任兩個值相同就連成一組，預設帳號排第一）。記 log、503、拒絕啟動、刪除都是後面的片；本片什麼都不刪（刪除細節是 DQ-14，還沒問）。
- **容量**：契約第 5 節的暫定值（Odoo 5、n8n 2、其他 3、OpenDesign／Odoo Manage 0；每子程式 MiB；保留 256 MiB）、PaaS 公式
  `min(上限, max(1, ⌊(memory.max−256)÷每子程式 MiB⌋)−1)`、`required_memory_mib`、停用順序（產品上限→記憶體→port）、每帳號名額
  （預設 64／64 MiB／32／24…，額外 32／64 MiB／16／8…）與 8081 外框 64＋32×上限。HM-19c 量測後定案。
- **隔離目錄名** `.quarantine-<id>-<YYYYMMDDTHHMMSSZ>`、索引隔離 `profiles.json.quarantine-<同格式>`：計畫只寫「<UTC>」，格式是本片暫定，
  HM-13b、HM-10 用到時可改。
- **身分欄位**：照 FM-80 的表；換 token 的欄位是 Odoo `url`／`database`／`username`（PaaS #131）加 DQ-40 ⑩ 的 Nextcloud `url`／`username`、
  Hermes `gateway_url`／`dashboard_url`／`dashboard_username`。n8n 存在頂層的 `backend_url`、`backend_key`、`mcp_access_token` 用存檔名。
- **升級零改寫**（計畫 §7.3）：8 份樣本是用 `git archive bb48449` 取出的程式產生的位元組（本分支的程式產生的完全相同），測試在上面跑
  HM-01 的 `production_runtime`（正式 runtime，只換掉外部），比對 `state.json` 的位元組、inode、連結數、大小、mode、mtime 與目錄項目
  （不比 ctime：`load()` 每次讀都 fchmod）。另一個測試確認樣本就是 `Store._write` 對該 state 寫出的位元組，沒有人手改過。
- **uid 10001 證明**：root 讀寫任何檔都過得了權限檢查，所以 0700／0600、擁有者 10001、收緊放寬的權限、拒絕別的 uid 擁有的項目，
  在真正降權的子程序裡驗（計畫 §10.1，C4-SF-6；FM-97）。探針在降權前 import 好所有模組：CI runner 的家目錄不一定開放給別的使用者讀，
  降權後可能讀不到 checkout（另有一個不用 root 的測試鎖住這點）。

## 4. 守門有效的證據

### 4.1 先紅後綠

| 輪 | 做法 | 結果 |
|---|---|---|
| 1 | 先寫 5 個測試檔，還沒有新模組 | 5 檔收集時 `ImportError`（`profiles`、`features` 不存在） |
| 2 | 加了三個新模組與 `profile_initial_state`，`config.py`／`ProductStore` 還沒改 | 60 失敗、154 通過。絕大多數是 `existing_only`／`create` 參數還不存在；另外 3 個：要 root 的證明（本機照預期）、撞號群組重疊（(A,B)＋(A,B,C)）→ 實作改成把相連的群組合併、測試自己的錯（umask 設在建立測試目錄之前）→ 修測試 |
| 3 | 審查時再加 4 個測試，改程式前先跑 | 4 個失敗：`modified` 沒有維持（回了新的 view）、OpenDesign／Odoo Manage 拿得到初值、探針在降權後才 import、入口掃描漏掉 `import_module(".profiles", "mcp_admin_core")` 又把單純的字串 `"profiles"`／`"features"` 當成 import → 改完全過 |

### 4.2 臨時突變

在暫存區的複本（不是 clone）每次只改一處、跑 HM-07 的 5 個測試檔、改回。基準：225 通過、1 失敗（要 root 的那一個）。

| 突變 | 新測試的結果 |
|---|---|
| M01 只開既有時 lock 帶 `O_CREAT` | 1 個失敗 |
| M02 只開既有時補建缺的 state | 1 個失敗 |
| M03 不檢查 state 的擁有者 | 1 個失敗 |
| M04 先 chmod 再檢查擁有者 | 1 個失敗 |
| M05 不檢查目錄的擁有者 | 1 個失敗 |
| M06 放寬的目錄權限不收緊 | 2 個失敗 |
| M07 不檢查 lock 的擁有者與連結數 | 2 個失敗 |
| M08 建立時沿用已存在的目錄 | 1 個失敗 |
| M09 建立失敗留下自己建的檔 | 11 個失敗 |
| M10 建立時先寫一份全開 state 再寫最終值 | 1 個失敗 |
| M11 額外帳號的 store 照樣遷移舊 schema | 28 個失敗 |
| M12 新帳號複製 `n8n_session` | 1 個失敗 |
| M13 新帳號複製 endpoint | 14 個失敗 |
| M14 Odoo 開關留成 legacy（不存） | 2 個失敗 |
| M15 新 token 可以和已用的值重複 | 1 個失敗 |
| M16 新帳號不複製政策（照新安裝全開） | 14 個失敗 |
| M17 開關在 import 時綁定 | 3 個失敗 |
| M18 未知產品當成「關」 | 1 個失敗 |
| M19 `run_product` import `profiles` | 2 個失敗 |
| M20 `products.py` 在函式裡 import `profiles` | 1 個失敗 |
| M21 簽章不含 ctime | 1 個失敗 |
| M22 簽章不含連結數 | 1 個失敗 |
| M23 讀索引時收緊權限 | 2 個失敗 |
| M24 讀索引不看擁有者 | 1 個失敗 |
| M25 索引接受 8081／8099 | 4 個失敗 |
| M26 port 接受 bool（`isinstance`） | 0 個（等價突變，見下） |
| M27 port 重複當成整份壞 | 3 個失敗 |
| M28 名稱只用 casefold 判重（PaaS） | 3 個失敗 |
| M29 名稱接受 Cf（bidi、零寬） | 9 個失敗 |
| M30 拿掉保留字「預設帳號」 | 2 個失敗 |
| M31 索引接受 6 筆 | 3 個失敗 |
| M32 寫索引不 fsync 目錄 | 1 個失敗 |
| M33 寫索引沿用 umask 的權限 | 1 個失敗 |
| M34 複查永遠說沒變 | 3 個失敗 |
| M35 索引壞仍服務 MCP | 2 個失敗 |
| M36 掃描跟隨連結 | 1 個失敗 |
| M37 不回報孤兒 | 1 個失敗 |
| M38 撞號只比 MCP token、不比 child token | 1 個失敗 |
| M39 配 port 不避開保留 port | 0 個（等價突變，見下） |
| M40 n8n 上限改成 5 | 3 個失敗 |
| M41 OpenDesign 開放 3 個 | 4 個失敗 |
| M42 `has_profile_data` 判斷不了時說沒有 | 1 個失敗 |
| M43 Nextcloud `username` 改了不換 token | 1 個失敗 |
| M44 Hermes `dashboard_password` 當成身分欄位 | 4 個失敗 |
| M45 有一個 state 欄位沒分類 | 1 個失敗 |
| M46 `modified` 不維持（每次重新判定） | 1 個失敗 |
| M47 OpenDesign／Odoo Manage 拿得到初值 | 1 個失敗 |
| M48 探針在降權後才 import | 1 個失敗 |
| M49 `run_product` 啟動時重寫 `state.json`（同位元組） | 7 個失敗 |
| M50 `apps/n8n/run.py` 啟動時重寫 `state.json`（同位元組） | 1 個失敗 |
| M51 `run_product` 啟動時建 `profiles/` | 7 個失敗 |
| M52 新帳號帶著預設帳號的 token 歷史 | 7 個失敗 |
| M53 `Layout.profile` 接受任何名字 | 1 個失敗 |
| M54 名稱不去頭尾空白 | 6 個失敗 |
| M55 寫索引不 fsync 檔案 | 1 個失敗 |
| M56 `has_profile_data` 跟隨連結 | 1 個失敗 |
| M57 讀不到 state 的帳號算可用 | 1 個失敗 |
| M58 讀索引跟隨連結 | 1 個失敗 |
| M59 索引寫成 `\u` 跳脫 | 1 個失敗 |
| M60 只開既有時不檢查 lock | 3 個失敗 |
| M61 升級樣本被手改（多一個空白） | 1 個失敗 |

沒擋到的 2 個都是等價突變（行為沒有不同，測不出來）：

- M26：bool 只有 0 和 1，本來就在 1024～65535 之外，範圍檢查一樣拒絕。
- M39：18000～18099 裡沒有保留 port（`test_port_allocation_is_the_first_free_port_of_18000_to_18099` 釘住常數），拿掉排除也配不到保留 port。

同一份清單的 M01～M45 在審查前跑過一次（當時 M43 的比對字串寫錯沒套用，改正後重跑擋到）；上表是本片最後的程式。

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

| 檢查 | 結果 |
|---|---|
| HM-07 新測試 5 檔 | 226 案：225 通過、1 失敗（要 root，第 6 節）、0 skip；約 5 秒 |
| HM-01 守門（黃金回歸、兩個契約凍結、log 掃描、兩個預檢工具的測試）＋ `Store`／`ProductStore` 相關既有測試（`test_streaming_and_storage`、`test_owner_defaults`、`test_token_history`、`test_writes_default_on`、`test_boundary`、`test_schema_defaults`、`test_migration_preview`、`test_tool_inventory`） | 全過（帳本重產之後） |
| 其他會建 store 或讀 state 的既有測試 24 檔（`test_admin_operations`、`test_management_capabilities`、`test_configuration_status`、`test_odoo_child_switches`、`test_odoo_allowed_methods`、`test_saved_destinations`、`test_connection_patch`、`test_full_surface`、`test_active_token_leases`、`test_n8n_session_settings` 等） | 516 通過 |
| 全套 pytest（`tests/`，正式 conftest） | 3958 案、0 skip，28 分 26 秒：3934 通過、24 失敗。失敗的是 2 個已知要 root 的（基準 1 個＋本片 1 個，第 6 節）和 22 個瀏覽器測試（`test_owned_browser_ipc` 5、`test_owned_browser_redirect` 16、`test_owned_ui[browser]` 1）：這個 clone 的環境腳本沒裝 Playwright 的 Chromium（`npm ci` 之後要另跑 `npm run browser:install`，CI 的 `packaging/unit.sh` 有跑），裝好後用正式 conftest 單獨重跑這 3 檔：52 案全過。本片的 226 案在全套裡 4.3 秒 |
| `packaging/validate.py` | PASS |
| packaging unittest | `Ran 184`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `scripts/tool_inventory.py`（不帶參數，CI 同款） | 通過；工具面沒變 |
| 兩個預檢 | 第 8 節 |

## 6. 只在 CI 跑的測試

- 新測試：`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`。要 root 才能切到 uid 10001（CI 的 pytest 以 root 跑），本機一般使用者
  照預期在第一行的 `assert os.geteuid() == 0` 失敗（不是 skip）。本機用「不降權、把指定 inode 的 stat 改報成 root 擁有」的模擬跑過同一個探針，
  回報和測試的期望相同（uid／gid 換成本機使用者；模擬腳本在暫存區，不進 repo）。本機沒有 newuidmap，也不能用 user namespace 真的切到
  uid 10001。另有不用 root 的 `test_the_probe_loads_everything_before_it_drops_privileges` 鎖住「降權前 import 好」。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root；本片沒改它用到的東西）。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip。
- 本機全套 pytest 因此有 2 個已知失敗（基準的 1 個＋上面這個）。

## 7. `checks` 秒數

開 PR 後補（前：HM-01 PR 的 `checks`；後：本片 PR 的 `checks`）。推估：新測試本機約 5 秒，CI 增加不到 1 分鐘。

## 8. 預檢結果

指令同 HM-01 筆記第 8 節。

- **秘密預檢**：gitleaks 8.28.0（`packaging/scanner-pins.json` 釘選；壓縮檔 SHA-256 相符才裝，執行檔摘要相符）；設定是本 repo 的
  `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本分支的 commit（`bb48449..HEAD`，git 模式；HM-01 的 9 個＋本片 2 個，含本筆記） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

  第一次掃本片的 commit 時有 1 個 `generic-api-key`：`tests/test_identity_fields.py` 的一個集合字面值裡，token 歷史的欄位名後面
  緊接著 owner-defaults 標記的欄位名（都不是秘密；規則把 token 字樣後面接逗號與一長串字當成金鑰）。改用 `products` 的兩個欄位名常數，
  改在同一個還沒 push 的 commit 裡，歷史裡沒有留下；重掃 0 命中。本筆記第一版照抄了那組字面值，又被掃到一次，改成上面的寫法。
- **帳本預檢**：`runtime-patches.json` 155 個路徑（53 個補丁檔＋guarded sources；本片多 3 個）、`runtime-sources.json` 70 個、
  `tool-surface.json` 159 個摘要，都 0 漂移、0 缺檔；對 `origin/claude-delivery` 改了 39 個檔（含 HM-01 的 17 個），列管檔 4 個
  （`features.py`、`identity_fields.py`、`products.py`、`profiles.py`）、帳本 1 個（`runtime-patches.json`），新增而沒列管的執行期檔 0 個，
  沒列管、要人看的 1 個（`config.py`，第 12 節待辦 6）。結果 OK。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

沒跑：這一波不連任何遠端（Gitea 也不連）。本片沒有移植 PaaS 程式，只照規則；要在連得到 Gitea 的地方跑
`git log 69ac425..origin/main -- packages/mcp-admin-core/mcp_admin_core/profiles.py packages/mcp-admin-core/mcp_admin_core/launch_policy.py`
（交主對話，第 12 節待辦 4）。

## 10. 本片用到的決策（主對話之後同步到 `docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片哪裡用到 |
|---|---|---|
| DQ-02 (a)（2026-11-14 採用） | 新帳號複製預設帳號當下的政策；`n8n_session` 不複製；建立不記 history | `profile_initial_state` |
| DQ-07＋DQ-29 (a)（同上） | 每帳號名額與位元組額度（含預設帳號）；暫定值，HM-19c 量測後定案 | `profiles.py` 的 `ProfileQuota`、容量常數 |
| DQ-12（2026-11-14 21:5x，照建議） | 索引壞或被外部改動時 8081 全部 503；面板照開、顯示「隔離帳號索引」；HA 上不提供手動修復 | `IndexView` 的判定（`serves_mcp`、`offers_quarantine`），外改後維持到重啟 |
| DQ-09（同上，照建議） | 撞號 503 `{"error":"state unavailable"}` | 本片只偵測（`Consistency.shared_secrets`），HM-08 回 503 |
| DQ-28（2026-11-14 採用） | OpenDesign、Odoo Manage 不開放 | 容量 0、`supports_profiles`、`NO_PROFILE_PRODUCTS` |
| DQ-32 (a)（同上） | 逐產品開關，開關＝發版 | `features.py` |
| DQ-37 (a)（同上） | 同 uid 是同一個信任邊界 | 簽章只防誤改，寫明不是安全邊界 |
| DQ-40 (a)（同上）④、⑩ | 名稱擋控制與零寬字元、NFKC 判重；換使用者欄位換 token 擴到 Nextcloud、Hermes | 名稱規則；`identity_fields.TOKEN_ROTATING` |
| DQ-16（§13.2，DQ-40 一次確認後照計畫做） | 名稱規則的細節 | 照契約 §3.6 的暫定值；HM-10、HM-11 定案時若改，改 `profiles.py` 的常數與測試 |
| DQ-33 (a)、DQ-36（同上） | 本機用短 TMPDIR；commit 不加 AI 署名 | 本機檢查；本片 commit |
| DQ-14（§13.2，還沒問） | 刪除細節 | 沒用到：本片什麼都不刪，只回報孤兒 |

## 11. 驗收條件（計畫 §12.3 HM-07）

| 條件 | 狀態 |
|---|---|
| 全綠 | 本機：新測試 225／226（1 個要 root）；全套 3958 案 3934 通過；24 失敗＝2 個要 root＋22 個瀏覽器測試（本機沒裝 Chromium；裝好後重跑 52 案全過）。CI 待 PR |
| 入口沒有 import `profiles.py` | 通過：`test_no_runtime_file_imports_the_unwired_modules`（靜態）、`test_no_entry_point_imports_the_unwired_modules`（實際載入 `run_product`、`apps/n8n/run.py`、`management_launcher.py`、`entrypoint.py`）；`features.py`、`identity_fields.py` 也一樣 |
| HTTP 面沒有變化 | 通過（本機）：HM-01 的黃金回歸、MCP 與管理 API 契約凍結照過；預設帳號 `Store` 路徑沒改；`bb48449` 樣本啟動後零改寫 |
| mode／owner 在 uid 10001 子程序驗 | 只在 CI：`test_mode_and_owner_as_the_add_on_user`（第 6 節）；本機用模擬跑過探針 |
| 新測試沒有條件式 skip | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail` |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 用 `T`×43、`C`×43 或執行時產生（`test_new_tokens_avoid_the_taken_values` 另用 `X`／`Y`／`Z`×43 的低熵假值），憑證 `DUMMY-…`，網址 `.invalid`；秘密預檢見第 8 節 |
| 同 PR 更新帳本 | 通過：3 個新模組列管、`products.py` 摘要更新；帳本預檢 OK |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG | 通過 |

## 12. 還沒解決、交給後面的片

1. **契約第 9 節缺一列**：索引 port 是 8081／8099 時整份壞，比 PaaS 嚴（PaaS 只在 spawn 時拒絕）。計畫 §4.2 與契約第 8 節對 3000 的兩句互相矛盾，
   本片的解讀見第 3 節。主對話定案後補進契約（HM-00／HM-18）。
2. **和同一波其他片的 rebase**：HM-04、HM-06 也改 `products.py`（帳本的 `products.py` 摘要要在 rebase 後重產）；HM-13a 可能在 entrypoint 或
   `restore_detect.py` 自己定義 `.restore-detected`、`.instance-sentinel` 等檔名，和本片 `Layout` 的同名常數要收斂成一個來源。
3. **HM-08 起接線時要改的測試**：`tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED`（HM-08 接 `features.py`、`profiles.py`，HM-13b 讓入口 import
   `profiles.py` 做存在檢查）；同檔的零改寫測試在 HM-13a／b 要加「開通後只多 sentinel 兩檔」。
4. **PaaS 變動清單**（第 9 節）在連得到 Gitea 的地方補跑。
5. **決策同步**：第 10 節的決策由主對話寫進 `docs/multi-profile/decisions.md`；DQ-16 的細節目前照契約暫定值。
6. `config.py` 照 `ledger-tracking.md` 第 3 節不列管；審查要求列管時再加。
7. `checks` 秒數開 PR 後補。
8. 本機曾有一次組合執行時 `tests/test_ledger_precheck.py::test_drift_and_pinned_changes` 失敗（HM-01 的既有測試，用自己的臨時 repo）；單獨重跑 8 次、
   組合重跑 2 次、全套 1 次都通過，原因沒找到，請在 CI 留意。
9. 本機環境：`setup_repo_env.sh` 的 UI `npm ci` 之後沒有 `npm run browser:install`，全套 pytest 會多 22 個瀏覽器測試失敗（找不到 Chromium）；
   本片的 clone 已補裝（`packages/mcp-admin-ui/node_modules`，不進 git）。其他片的 clone 若看到同樣的 22 個，是環境不是退步。
10. uid 10001 證明的探針改成降權前 import，是因為 CI runner 的家目錄可能不開放給別的使用者；這點只有 CI 跑過才知道（第 6 節）。
