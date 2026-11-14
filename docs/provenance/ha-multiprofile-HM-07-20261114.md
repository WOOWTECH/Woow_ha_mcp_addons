# HA 多帳號 HM-07 provenance：帳號資料層、開關常數、身分欄位分類（未接線）（2026-11-14）

## 結論

- 範圍：新模組 `features.py`、`profiles.py`、`identity_fields.py`（在 `packages/mcp-admin-core/mcp_admin_core/`），改 `config.py`
  （`existing_only`、建立路徑、擁有者檢查）與 `products.py`（`profile_initial_state`），加測試、uid 10001 探針、8 份升級樣本與帳本。
- **未接線**：沒有任何入口 import 這三個新模組（測試鎖住）；預設帳號的 `Store` 行為不變；8081、8099 的回應不變
  （HM-01 的黃金回歸與兩個契約凍結照過）。
- **獨立安全審查（2026-11-15）判定「修正後通過」**，程式沒有找到安全缺陷。審查意見逐條處理，見第 13 節：
  - 必修 MF-1（索引 port 3000／8081／8099）：改成和 PaaS 一致，三個 port 都不算結構錯，只停相關帳號。依據是契約開頭
    「沒列的就要相同」、FM-40、設計稿 A-port，不新增差異。**要主對話確認**：要改回「8081／8099 整份壞」，就 revert 第 13 節的 C3，
    並在契約第 9 節補一列。
  - 必修 MF-2（PaaS 變動清單）：這一波不連遠端，沒跑。開 PR 前由主對話在連得到 Gitea 的地方補（第 9 節）。
  - 建議 16 項：採用 13 項（S-01～S-07、S-09～S-13、S-16）；3 項留給接線的片（S-08、S-14、S-15），理由見第 13 節。
- 新測試 5 檔 250 案（審查前 226 案）：本機 249 通過；1 案要 root（uid 10001 的 mode／owner 證明），本機照預期失敗，只在 CI 驗（第 6 節）。
- 先寫測試：審查前三輪、審查修正一輪，先紅後綠都有紀錄（第 4.1 節）。突變：審查前 61 個擋到 59 個（2 個等價）；審查的 59 個裡沒擋到的
  9 個，現在都擋到；修正本身另做 14 個，全部擋到（第 4.3 節）。
- 兩個預檢：秘密預檢對本分支 17 個 commit（HM-01 的 9 個＋本片 8 個）0 命中，建置機同款的 HEAD 與全歷史掃描也 0 命中；
  帳本預檢 OK（列管 5 檔，`config.py` 從本片起列管，第 8 節）。
- 全套 pytest（審查修正後，正式 conftest）：3982 案、0 skip、28 分 24 秒：3980 通過、2 失敗，都是已知要 root 的（基準的 `test_uid10001_nondumpable_self_and_own_child_proof`＋本片的 `test_mode_and_owner_as_the_add_on_user`）。22 個瀏覽器測試這次都過（這個 clone 已補裝 Chromium）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-07（計畫 §12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm07-20261114` |
| 基準 | HM-01 分支 head `32ecac8`（＝`claude-delivery` `bb48449`＋HM-01；PR #90 待合併） |
| 依據 | 計畫 §3.3、§4.1～§4.4、§5.2、§5.4、§7.1、§7.3、§8.2（I2、I5、I6、I7）、§10.1、§10.3；HM-00 契約（PR #89）§1.2、§2.3、§3.6、§5、§7、§8、§9；`threat-model.md`；獨立安全審查報告 `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-07.md`（repo 外） |
| FM | FM-01、03、04、05、09、10、13、16、19、20、21、23、30、40、80、83、97、106 |
| 對齊的 PaaS | 沒有移植 PaaS 程式。索引規則（含 MF-1 之後的 port 規則：PaaS `_index_entries` 收 1024～65535、`_port_collisions` 只停相關帳號）、容量公式、新帳號初值照 PaaS `woow-mcp-server` `packages/mcp-admin-core/mcp_admin_core/profiles.py` @`69ac425`（經研究報告 R03 §4、G1 與契約）；身分欄位照 PaaS #147 還原手冊的 `IDENTITY` 清單（R12、G5）。測試裡的 PaaS 欄只是對照，本 repo 不跑 PaaS 程式 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/features.py`（新） | `MULTI_PROFILE_PRODUCTS: frozenset[str] = frozenset()`（全部關）；`enabled(product)` 每次呼叫才讀集合，未知產品丟 `ValueError`（不默默當成關） |
| `Hc/profiles.py`（新） | 帳號索引 `profiles.json`（`{"version":1,"profile_index":{id:{label,port}}}`）的解析與編碼、讀（不 chmod）與原子寫（暫存檔＋fsync＋replace＋目錄 fsync，0600；**寫入先比對**：只蓋掉本程序最後讀到或寫入、狀態 absent／ok、而且沒被外改的索引）、簽章（`st_dev`、`st_ino`、`st_mtime_ns`、`st_ctime_ns`、`st_size`、`st_nlink`）、DQ-12 判定（`IndexView.serves_mcp`、`offers_quarantine`）；索引 port 1024～65535（同 PaaS；重複、3000、8081、8099 都只停相關帳號）；布局 `Layout`（索引、收據、`profiles/`、帳號目錄與 `child/`、還原用的 5 個檔名）、隔離目錄與索引隔離的命名、`has_profile_data`；`profiles/` 的建立（建好後 fsync `/data/mcp`）與掃描（不跟隨連結）；一致性報告；容量常數與 PaaS 公式、停用原因順序、每帳號名額、8081 外框；名稱規則；id 與 port 配發 |
| `Hc/identity_fields.py`（新） | 九個產品每個存檔後端欄位的類別（`identity`／`secret`／`option`）；改了要換 token 的身分欄位；`ProductState` 每個欄位的類別（`credential`、`backend`、`policy`、`session`、`endpoint`、`record`） |
| `Hc/config.py` | `Store(directory, existing_only=True)`：不建目錄、lock 不帶 `O_CREAT`、缺 state 就 `ConfigError`；`Store(directory, create=<state>)`：目錄必須原本不存在（連懸空連結也不行）、建好先 fsync 上一層、lock 用 `O_EXCL`、一次寫入最終初值、失敗只清掉自己建的兩個檔與目錄。兩種模式都在任何 chmod 之前檢查目錄、lock、state 的擁有者是本 uid，並把放寬的權限收回 0700／0600；額外帳號讀 0600 的 state 不 fchmod（ctime 不變）。預設帳號（不帶參數）的建構路徑和原本相同（只多一層縮排），`load()` 照樣每次 fchmod |
| `Hc/products.py` | `ProductStore(..., existing_only=, create=)` 傳給 `Store`，這兩種模式不遷移（舊 schema 原樣拒絕、不改寫）；`create=` 遇到 OpenDesign、Odoo Manage 先丟 `ValueError`、什麼都不建（`existing_only` 照常能開）；`profile_initial_state(default, taken=())`；`NO_PROFILE_PRODUCTS`（DQ-28） |
| `tests/test_profile_index.py` | 索引規則 53 案（每案有 PaaS 對照欄：13 案 HA 比 PaaS 嚴、各寫明依據；9 案是 HA 自己檔案格式的規則。MF-1 讓兩個 listener port 案例和 PaaS 相同，S-12 多兩個外圍空白案例）、順序、編碼、port 衝突（含 listener port 只停那個帳號）、停用原因順序、id、名稱（含非 ASCII 外圍空白）、port 配發、容量常數與公式、讀寫（含寫入先比對、每條路徑都關 fd）、簽章、複查出錯判 modified、DQ-12 判定 |
| `tests/test_profile_store.py` | 新帳號初值（DQ-02，7 個可開的產品；不帶 owner-defaults 標記）、Store 層拒絕不開放的產品、只開既有、建立的每一步故障注入（11 步，含 fsync 上一層）、建立與 `profiles/` 的 fsync、讀 state 不改 ctime、擁有者與權限（目錄、lock、state 三者都先放寬再驗順序）、不遷移、`profiles/` 目錄、整棵樹在 entrypoint 還原修復的上限內、uid 10001 證明（root） |
| `tests/profile_owner_probe.py` | 上一列 uid 10001 證明的探針：降權前 import 好所有模組，降權後只回報 JSON（不含 token）；記下每一次對別的 uid 擁有的項目做的 chmod |
| `tests/test_profile_consistency.py` | 布局、隔離命名、掃描（每條路徑都關 fd）、缺目錄或讀不到的帳號（掃描沒找到的就算給了 credentials 也是 unavailable）、孤兒、撞號（含 token 與 child token 交叉）、`has_profile_data` |
| `tests/test_identity_fields.py` | 每個欄位都有類別（新欄位沒分類就失敗）、和模型的 `repr=False`、`backend_edit.FIELDS`、面板 `contracts.js` 對得上、FM-80 的表、換 token 的欄位 |
| `tests/test_upgrade_zero_rewrite.py` | 入口沒有 import 新模組（靜態掃描＋實際載入 4 個入口）；開關全部關、呼叫時才讀、子程序前置碼能打開；`bb48449` 寫出的 state 啟動正式 runtime 後一個位元組都沒變；單帳號安裝讀資料層什麼都不改；建帳號不寫預設 `state.json` |
| `tests/fixtures/upgrade_zero_rewrite/`（8 份＋README） | `bb48449` 的程式為已設定的 add-on 寫出的 `state.json`（照 owner_defaults README 正規化；做法見該 README） |
| `docs/provenance/runtime-patches.json` | 新增 `features.py`、`profiles.py`、`identity_fields.py`、`config.py` 四筆（`config.py` 是審查 S-10 後才列）；`products.py` 更新摘要並補 HM-07 說明 |
| 本筆記 | — |

沒改：入口（`run_product.py`、`apps/n8n/run.py`、`packaging/management_launcher.py`、`packaging/entrypoint.py`）、`gateway.py`、
`lifecycle.py`、`health.py`、`apps/`、`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`
（沒動 `apps/runtime/*.py` 與 `apps/*/launch.py`，不用重產）、`docs/provenance/runtime-sources.json`（沒有 vendored 檔）、workflow、
既有測試與替身。本分支沒有 `docs/multi-profile/`，也沒加。

## 3. 設計重點與解讀

- **索引的 port 規則（審查 MF-1 後）**：port 只要是 int、不是 bool、1024～65535，就不算結構錯（同 PaaS `_index_entries`）。
  port 重複、3000（預設子程式）、8081、8099（add-on 自己的 listener）都只停持有它的帳號：`port_conflicts` 列出這些帳號，
  `disabled_reason=port_conflict`；索引照常可用，8081 照常服務預設帳號和其他帳號。
  - 依據：契約開頭「沒列的就要相同」（契約第 9 節沒有這一列）；FM-40 的 HA 差異欄是「—」；設計稿 A-port 把 3000、8081、8099 都列成
    不算結構錯。
  - 計畫 §4.2 與契約第 8 節同時寫了「不是 3000／8081／8099 → 整份壞」和「撞預設 port 不算結構錯」，兩句矛盾。審查前本片讓 8081／8099
    整份壞，比 PaaS 嚴，契約第 9 節卻沒有這一列（審查 MF-1）。現在照後一句和 PaaS；前一句的文字由主對話改（第 12 節待辦 1）。
  - 和 PaaS 的細微差別：PaaS 的 `_port_collisions` 只列重複和預設帳號的 port；listener port 是 spawn 時才由 `_port_refusal`
    拒絕（`child_port_conflict`）。本片照審查 MF-1 的修法 (b) 與設計稿 A-port，listener port 也列進 `port_conflicts`。兩邊都只停那個帳號、
    都不起它的子程式。要逐字照 PaaS，就把 `port_conflicts` 裡的 listener port 拿掉、交給 HM-09 的 spawn 檢查；主對話確認 MF-1 時一起定。
- **DQ-12 的判定**：`read_index` 回 `absent`／`ok`／`corrupt`；`recheck_index` 每個請求一次 lstat，簽章不符就 `modified`，lstat 出錯（不是
  ENOENT）也是 `modified`；`modified` 一直維持到重啟重讀（呼叫端保留回傳的 view）。`corrupt` 與 `modified` 都是 `serves_mcp=False`
  （8081 全部 503，含預設帳號）、`offers_quarantine=True`（面板照開、提供「隔離帳號索引」）。本片只做判定，HM-08、HM-10 接線。
- **寫入先比對（審查 S-07）**：`write_index(path, entries, *, expected)` 只在三件事都成立時才寫：`expected` 是本程序最後一次讀到或寫入的
  view；它的狀態是 `absent` 或 `ok`；複查仍然回傳它本身。`corrupt`、`modified`、比較舊的基準、外部改過或憑空出現的檔，都丟
  `ProfileDataError`，原檔一個位元組都不動。所以寫入洗不掉「503 到重啟」；只有「隔離帳號索引」（HM-10）能結束它。
- **讀索引不 chmod**：預設帳號的 `load()` 每次讀都 `fchmod 0600`；索引如果也這樣做，會改到簽章比對的 ctime。所以權限不是 0600 就判壞，
  不自動收緊。entrypoint 的還原修復會把檔案設回 0600（`packaging/entrypoint.py` 的 `_reown_restored`）。
- **簽章**：同 uid 改得回位元組、大小、mtime（`os.utime`），改不回 ctime；硬連結會改 nlink。同 uid 下不是安全邊界（DQ-37），只防誤改。
  Linux 的 ctime 是粗時鐘（數 ms）：同一個 tick 內改了又改回原位元組，簽章可能分不出來；同 uid 本來就不是邊界，只記錄（審查報告 §6.3）。
- **名稱規則**：去頭尾空白（Python `str.strip()`，含全形空白、NBSP 等非 ASCII 空白）後 1～80 個 code point；拒絕 Cc、Cf（含 bidi、零寬）、
  Zl、Zp、Cs、Co、Cn；判重用 NFKC→casefold→NFKC；保留 `default` 與「預設帳號」。存在索引裡的名稱必須已經是正規化後的樣子
  （頭尾有空白就判壞）。名稱不進目錄名與 log（`log_id` 只給 id 前 8 碼）。Cn 用執行中 Python 的 Unicode 資料庫判斷，讀檔也擋
  （審查 S-14，交 DQ-16 定案，第 12 節）。
- **新帳號初值**（DQ-02 (a)）：新 token、新 child token（43 字元，不和預設帳號與 `taken` 裡的值重複；I2）；連線、憑證、endpoint 都空（I5）；
  政策照預設帳號當下的值，Odoo 四個子程式開關寫成「已儲存」、方法清單沒存過就維持沒存；不帶 `n8n_session`、owner-defaults 標記、
  token 歷史（預設帳號帶著 owner-defaults 標記時也一樣）。OpenDesign、Odoo Manage：`profile_initial_state` 與 `ProductStore(create=…)`
  都拒絕（DQ-28；HM-10 會先回 409）；`existing_only` 照常能開，留給 HM-13b 撤銷還原留下的殘留。
- **只開既有與建立**：額外帳號的 store 不會走「第一次開機補建全開 state」的路（FM-04 的 probe-ha #1）；建立失敗只清掉自己建的，
  目錄裡若多了別的東西就留下，變成孤兒（一致性報告列出，不開、不路由）。
  - 落盤順序（審查 S-13）：建立時 mkdir 之後先 fsync 上一層（`profiles/`），再建 lock 與 state；`ensure_profiles_directory` 之後 fsync
    `/data/mcp`。斷電後，已落盤的索引不會列著一個目錄項目沒落盤的帳號。fsync 失敗就是錯誤（建立會清掉自己建的東西）。
  - 讀 state 不改 ctime（審查 S-09）：額外帳號的 `load()` 只在 state 不是 0600 時才 fchmod，所以 HM-08 的 state 簽章可以含 ctime；
    權限被放寬時照樣收緊。預設帳號每次讀都 fchmod，不變（HM-01 凍結）。
  - 已開的 store 之後的讀寫走路徑，沒有釘住建構時驗過的目錄（審查 S-08；要同 uid 才做得到，DQ-37）。留給 HM-08，第 12 節。
- **一致性報告**只回報事實：`unavailable`（索引有、但掃描沒找到目錄，或 state 讀不到）、孤兒、隔離目錄、其他項目數、port 衝突、撞號群組
  （token 與 child token 任兩個值相同就連成一組，預設帳號排第一）。記 log、503、拒絕啟動、刪除都是後面的片；本片什麼都不刪
  （刪除細節是 DQ-14，還沒問）。
- **容量**：契約第 5 節的暫定值（Odoo 5、n8n 2、其他 3、OpenDesign／Odoo Manage 0；每子程式 MiB；保留 256 MiB）、PaaS 公式
  `min(上限, max(1, ⌊(memory.max−256)÷每子程式 MiB⌋)−1)`、`required_memory_mib`、停用順序（產品上限→記憶體→port；同一個帳號有幾種原因時
  取第一個）、每帳號名額（預設 64／64 MiB／32／24…，額外 32／64 MiB／16／8…）與 8081 外框 64＋32×上限。HM-19c 量測後定案。
- **隔離目錄名** `.quarantine-<id>-<YYYYMMDDTHHMMSSZ>`、索引隔離 `profiles.json.quarantine-<同格式>`：計畫只寫「<UTC>」，格式是本片暫定。
  只到秒，同一秒做兩次會撞名（審查 S-15）；HM-10、HM-13b 改名時用不覆蓋的寫法或加序號，用到時可改格式。
- **身分欄位**：照 FM-80 的表；換 token 的欄位是 Odoo `url`／`database`／`username`（PaaS #131）加 DQ-40 ⑩ 的 Nextcloud `url`／`username`、
  Hermes `gateway_url`／`dashboard_url`／`dashboard_username`。n8n 存在頂層的 `backend_url`、`backend_key`、`mcp_access_token` 用存檔名。
- **升級零改寫**（計畫 §7.3）：8 份樣本是用 `git archive bb48449` 取出的程式產生的位元組（本分支的程式產生的完全相同），測試在上面跑
  HM-01 的 `production_runtime`（正式 runtime，只換掉外部），比對 `state.json` 的位元組、inode、連結數、大小、mode、mtime 與目錄項目
  （不比 ctime：預設帳號的 `load()` 每次讀都 fchmod）。另一個測試確認樣本就是 `Store._write` 對該 state 寫出的位元組，沒有人手改過。
- **uid 10001 證明**：root 讀寫任何檔都過得了權限檢查，所以 0700／0600、擁有者 10001、收緊放寬的權限、拒絕別的 uid 擁有的項目，
  在真正降權的子程序裡驗（計畫 §10.1，C4-SF-6；FM-97）。探針在降權前 import 好所有模組：CI runner 的家目錄不一定開放給別的使用者讀，
  降權後可能讀不到 checkout（另有一個不用 root 的測試鎖住這點）。
  - 只看「被拒」證明不了「先查擁有者」（審查 S-03）：uid 10001 對別人的檔 chmod，核心本來就回 EPERM，有沒有擁有者檢查都會被拒。
    所以探針另外記下每一次對別的 uid 擁有的項目做的 chmod，測試要求這份清單是空的。
  - 本機模擬（不降權；假報這些項目是 root 擁有，對它們 chmod 回 EPERM）：正式程式的清單是空的；拿掉三個擁有者檢查（審查的
    R31＋R32＋R33）之後清單有 3 筆，被拒的結果完全相同。所以這份清單分得出擁有者檢查，只看「被拒」分不出。

## 4. 守門有效的證據

### 4.1 先紅後綠

| 輪 | 做法 | 結果 |
|---|---|---|
| 1 | 先寫 5 個測試檔，還沒有新模組 | 5 檔收集時 `ImportError`（`profiles`、`features` 不存在） |
| 2 | 加了三個新模組與 `profile_initial_state`，`config.py`／`ProductStore` 還沒改 | 60 失敗、154 通過。絕大多數是 `existing_only`／`create` 參數還不存在；另外 3 個：要 root 的證明（本機照預期）、撞號群組重疊（(A,B)＋(A,B,C)）→ 實作改成把相連的群組合併、測試自己的錯（umask 設在建立測試目錄之前）→ 修測試 |
| 3 | 審查前自查時再加 4 個測試，改程式前先跑 | 4 個失敗：`modified` 沒有維持（回了新的 view）、OpenDesign／Odoo Manage 拿得到初值、探針在降權後才 import、入口掃描漏掉 `import_module(".profiles", "mcp_admin_core")` 又把單純的字串 `"profiles"`／`"features"` 當成 import → 改完全過 |
| 4 | 獨立審查後（2026-11-15），每項先改測試、跑一次，再改程式 | MF-1：4 個失敗（兩個 listener port 的 PARITY 案例、`test_a_listener_port_stops_only_the_profile_holding_it`、一致性報告的 port 衝突）；S-06：1 個；S-07：1 個；S-13＋S-09：4 個（另 1 個是要 root 的）→ 改完全過。S-01～S-05、S-11、S-12 補的是缺口測試：程式本來就對，寫好就過；有效與否由第 4.3 節的突變證明 |

第 4 輪的紅綠在 clone 裡跑，用 conftest 的網路與子程序守門、不拿使用者鎖（當時別的代理的全套佔著鎖；這 5 檔不綁固定 port）。
修正後的正式結果見第 5 節（正式 conftest）。

### 4.2 臨時突變（審查前）

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
| M25 索引接受 8081／8099 | 4 個失敗（審查前的規則；見表後說明） |
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

M25 改的「索引接受 8081／8099」是審查前的規則被改壞。MF-1 之後這就是正確行為，反方向（listener port 讓整份壞、listener port 不算
衝突）由第 4.3 節的 N01、N02 守門。

同一份清單的 M01～M45 在審查前跑過一次（當時 M43 的比對字串寫錯沒套用，改正後重跑擋到）；上表是審查前本片最後的程式。

### 4.3 臨時突變（審查修正後）

做法同 4.2：暫存區的複本（每個 `git ls-files` 檔的摘要都和 clone 的 HEAD 相同，跑完再比一次，已還原），一次只改一處、跑 HM-07 的
5 個測試檔、改回。基準：249 通過、1 失敗（要 root 的那一個）。和 4.1 第 4 輪一樣用 conftest 的網路與子程序守門、不拿使用者鎖。

R 開頭是審查報告裡沒擋到的 9 個（同樣的改法）；N 開頭是針對這次修正新做的。

| 突變 | 改壞的行為 | 新測試的結果 |
|---|---|---|
| R10 | port 衝突蓋掉產品上限、記憶體的停用原因 | 1 個失敗 |
| R19 | 複查時 lstat 出錯就回傳原 view（fail open） | 1 個失敗 |
| R26 | `unavailable` 不看掃描結果 | 1 個失敗 |
| R34 | 目錄先 chmod 再查擁有者 | 1 個失敗 |
| R46 | 新帳號帶 owner-defaults 標記 | 7 個失敗 |
| R57 | 名稱只去 ASCII 空白 | 5 個失敗 |
| R58 | `scan_profiles` 不關 fd | 1 個失敗 |
| R60 | lock 先 chmod 再查擁有者 | 1 個失敗 |
| R61 | `read_index` 不關 fd | 1 個失敗 |
| N01 | MF-1 改回去：listener port 讓整份壞 | 4 個失敗 |
| N02 | listener port 不算 port 衝突 | 3 個失敗 |
| N03 | S-06 拿掉：`ProductStore(create=…)` 建得出 OpenDesign／Odoo Manage | 1 個失敗 |
| N04 | S-06 過頭：這兩個產品既有的也開不了 | 9 個失敗 |
| N05 | S-07 拿掉：`write_index` 不管索引狀態都寫 | 1 個失敗 |
| N06 | `write_index` 只比檔案、不看狀態（corrupt／modified 也照寫） | 1 個失敗 |
| N07 | `write_index` 只看狀態、不比檔案 | 1 個失敗 |
| N08 | S-13：建立時不 fsync 上一層 | 2 個失敗 |
| N09 | S-13：建好 `profiles/` 不 fsync `/data/mcp` | 1 個失敗 |
| N10 | S-13：fsync `/data/mcp` 失敗被吞掉 | 1 個失敗 |
| N11 | S-09 拿掉：額外帳號每次讀都 fchmod | 1 個失敗 |
| N12 | S-09 過頭：預設帳號也不 fchmod（動到凍結的行為） | 1 個失敗 |
| N13 | S-09 過頭：額外帳號放寬的權限不收緊 | 3 個失敗 |
| N14 | state 先 chmod 再查擁有者 | 2 個失敗 |

23 個全部擋到。S-03 的探針改動只在 root 下跑，改用第 3 節的本機模擬證明（拿掉擁有者檢查後清單有 3 筆）。

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

審查修正後（rebase 前的 HEAD `28c3fd9`＝第 13 節的 C7；之後的 C8 只改本筆記）：

| 檢查 | 結果 |
|---|---|
| HM-07 新測試 5 檔（正式 conftest） | 250 案：249 通過、1 失敗（要 root，第 6 節）、0 skip；約 5 秒 |
| HM-01 守門（黃金回歸、MCP 與管理 API 契約凍結、log 掃描、兩個預檢工具的測試；正式 conftest） | 79 通過 |
| `Store`／`ProductStore` 相關既有測試 16 檔（`test_streaming_and_storage`、`test_owner_defaults`、`test_token_history`、`test_writes_default_on`、`test_boundary`、`test_schema_defaults`、`test_migration_preview`、`test_tool_inventory`、`test_admin_operations`、`test_management_capabilities`、`test_configuration_status`、`test_odoo_child_switches`、`test_odoo_allowed_methods`、`test_saved_destinations`、`test_connection_patch`、`test_n8n_session_settings`；正式 conftest） | 684 通過 |
| 全套 pytest（`tests/`，正式 conftest，在 wave1 鎖下跑） | 3982 案、0 skip，28 分 24 秒：3980 通過、2 失敗，都是已知要 root 的（基準 1 個＋本片 1 個，第 6 節）。22 個瀏覽器測試這次都過（這個 clone 已補裝 Chromium）。本片的 250 案都在裡面 |
| `packaging/validate.py` | PASS |
| packaging unittest（同 CI：`.venv` 的 Python 加 `requirements-ci` 的 PyYAML 6.0.3） | `Ran 184`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `scripts/tool_inventory.py`（不帶參數，CI 同款） | 通過；工具面沒變 |
| 兩個預檢 | 第 8 節 |

審查前（`a278f83`，作者自己跑）：

| 檢查 | 結果 |
|---|---|
| HM-07 新測試 5 檔 | 226 案：225 通過、1 失敗（要 root）、0 skip |
| HM-01 守門＋`Store`／`ProductStore` 相關既有測試 8 檔 | 全過（帳本重產之後） |
| 其他會建 store 或讀 state 的既有測試 24 檔 | 516 通過 |
| 全套 pytest（正式 conftest） | 3958 案、0 skip，28 分 26 秒：3934 通過、24 失敗。失敗的是 2 個已知要 root 的（基準 1 個＋本片 1 個）和 22 個瀏覽器測試（這個 clone 當時沒裝 Playwright 的 Chromium；裝好後單獨重跑那 3 檔 52 案全過） |

## 6. 只在 CI 跑的測試

- 新測試：`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`。要 root 才能切到 uid 10001（CI 的 pytest 以 root 跑），本機一般使用者
  照預期在第一行的 `assert os.geteuid() == 0` 失敗（不是 skip）。它驗 0700／0600、擁有者 10001、收緊放寬的權限、拒絕別的 uid 擁有的項目，
  以及（審查 S-03 之後）「對別的 uid 擁有的項目一次 chmod 都沒做」。本機用「不降權、把指定 inode 的 stat 改報成 root 擁有、對它們 chmod
  回 EPERM」的模擬跑過同一個探針，回報和測試的期望相同（uid／gid 換成本機使用者；模擬腳本在暫存區，不進 repo）。本機沒有 newuidmap，
  也不能用 user namespace 真的切到 uid 10001。另有不用 root 的 `test_the_probe_loads_everything_before_it_drops_privileges` 鎖住「降權前 import 好」。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root；本片沒改它用到的東西）。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip。
- 本機全套 pytest 因此有 2 個已知失敗（基準的 1 個＋上面這個）。

## 7. `checks` 秒數

開 PR 後補（前：HM-01 PR 的 `checks`；後：本片 PR 的 `checks`）。推估：新測試本機約 5 秒，CI 增加不到 1 分鐘。

## 8. 預檢結果

指令同 HM-01 筆記第 8 節。數字是審查修正後、含本筆記的 commit。

- **秘密預檢**：gitleaks 8.28.0（`packaging/scanner-pins.json` 釘選；本機已有的壓縮檔 SHA-256 相符才裝，執行檔摘要相符）；設定是本 repo 的
  `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本分支的 commit（`bb48449..HEAD`，git 模式；HM-01 的 9 個＋本片 8 個，含本筆記） | 0（17 個 commit） |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

  審查前第一次掃本片的 commit 時有 1 個 `generic-api-key`：`tests/test_identity_fields.py` 的一個集合字面值裡，token 歷史的欄位名後面
  緊接著 owner-defaults 標記的欄位名（都不是秘密；規則把 token 字樣後面接逗號與一長串字當成金鑰）。改用 `products` 的兩個欄位名常數，
  改在同一個還沒 push 的 commit 裡，歷史裡沒有留下；重掃 0 命中。本筆記第一版照抄了那組字面值，又被掃到一次，改成上面的寫法。
- **帳本預檢**：`runtime-patches.json` 156 個路徑（54 個補丁檔＋guarded sources；本片多 4 個：三個新模組與 `config.py`）、`runtime-sources.json` 70 個、`tool-surface.json` 159 個摘要，都 0 漂移、0 缺檔；對 `origin/claude-delivery` 改了 39 個檔（含 HM-01 的 17 個），列管檔 5 個（`config.py`、`features.py`、`identity_fields.py`、`products.py`、`profiles.py`）、帳本 1 個（`runtime-patches.json`），新增而沒列管的執行期檔 0 個，沒列管、要人看的 0 個（審查前「待人看」的 `config.py` 已列管）。結果 OK。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

**還沒跑（審查必修 MF-2）。** 這一波不連任何遠端（Gitea 也不連），也不碰其他 clone；沒有 fetch 過的 `origin/main` 也不能當結果。
開 PR 前由主對話在連得到 Gitea 的地方跑：

```sh
git fetch origin
git log --format='%h %ad %s' --date=iso 69ac425..origin/main -- \
  packages/mcp-admin-core/mcp_admin_core/profiles.py \
  packages/mcp-admin-core/mcp_admin_core/launch_policy.py \
  packages/mcp-admin-core/tests/test_profiles.py \
  packages/mcp-admin-core/tests/test_profile_robustness.py
```

- 要看的規則：索引規則（`_index_entries`）、`_port_collisions`、容量公式（`ProfileCapacity`、`_memory_limit_mib`）、每產品上限與每子程式 MiB、
  新帳號初值（`create`）；本片照抄的就是這些。
- 結果寫在這裡：查詢時間、`origin/main` 的 SHA、有沒有變動。沒有變動也要寫「無變動」。
- 規則有變，就回本片對齊並補測試，重跑兩個預檢。

| 查詢時間 | `origin/main` | 結果 |
|---|---|---|
| （待主對話補） | — | — |

## 10. 本片用到的決策（主對話之後同步到 `docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片哪裡用到 |
|---|---|---|
| DQ-02 (a)（2026-11-14 採用） | 新帳號複製預設帳號當下的政策；`n8n_session` 不複製；建立不記 history | `profile_initial_state` |
| DQ-07＋DQ-29 (a)（同上） | 每帳號名額與位元組額度（含預設帳號）；暫定值，HM-19c 量測後定案 | `profiles.py` 的 `ProfileQuota`、容量常數 |
| DQ-12（2026-11-14 21:5x，照建議） | 索引壞或被外部改動時 8081 全部 503；面板照開、顯示「隔離帳號索引」；HA 上不提供手動修復 | `IndexView` 的判定（`serves_mcp`、`offers_quarantine`），外改後維持到重啟；寫入先比對，不蓋掉 corrupt／modified 的索引 |
| DQ-09（同上，照建議） | 撞號 503 `{"error":"state unavailable"}` | 本片只偵測（`Consistency.shared_secrets`），HM-08 回 503 |
| DQ-28（2026-11-14 採用） | OpenDesign、Odoo Manage 不開放 | 容量 0、`supports_profiles`、`NO_PROFILE_PRODUCTS`；`profile_initial_state` 與 `ProductStore(create=…)` 都拒絕 |
| DQ-32 (a)（同上） | 逐產品開關，開關＝發版 | `features.py` |
| DQ-37 (a)（同上） | 同 uid 是同一個信任邊界 | 簽章只防誤改，寫明不是安全邊界；S-08（已開的 store 沒釘住目錄）留給 HM-08 |
| DQ-40 (a)（同上）④、⑩ | 名稱擋控制與零寬字元、NFKC 判重；換使用者欄位換 token 擴到 Nextcloud、Hermes | 名稱規則；`identity_fields.TOKEN_ROTATING` |
| DQ-16（§13.2，DQ-40 一次確認後照計畫做） | 名稱規則的細節 | 照契約 §3.6 的暫定值；HM-10、HM-11 定案時若改，改 `profiles.py` 的常數與測試。讀檔時要不要也擋 Cn（S-14）一起定 |
| DQ-33 (a)、DQ-36（同上） | 本機用短 TMPDIR；commit 不加 AI 署名 | 本機檢查；本片 commit |
| DQ-14（§13.2，還沒問） | 刪除細節 | 沒用到：本片什麼都不刪，只回報孤兒 |

另外兩條是既有的規則，不是新決策：

| 規則 | 內容 | 本片哪裡用到 |
|---|---|---|
| 契約開頭（HM-00，PR #89） | HA 和 PaaS 不同的地方都列在第 9 節，沒列的就要相同 | MF-1：索引 port 規則改成和 PaaS 一致（待主對話確認，第 12 節待辦 1） |
| `ledger-tracking.md` 第 3 節（HM-00） | 新檔以外的執行期檔要不要列管，由審查決定 | S-10：審查建議列管，`config.py` 從本片起列進 `runtime-patches.json`（`guarded_sources` 是 `{}`） |

## 11. 驗收條件（計畫 §12.3 HM-07）

| 條件 | 狀態 |
|---|---|
| 全綠 | 本機：新測試 249／250（1 個要 root）；全套 3982 案 3980 通過，2 個失敗都是要 root 的。CI 待 PR |
| 入口沒有 import `profiles.py` | 通過：`test_no_runtime_file_imports_the_unwired_modules`（靜態）、`test_no_entry_point_imports_the_unwired_modules`（實際載入 `run_product`、`apps/n8n/run.py`、`management_launcher.py`、`entrypoint.py`）；`features.py`、`identity_fields.py` 也一樣 |
| HTTP 面沒有變化 | 通過（本機）：HM-01 的黃金回歸、MCP 與管理 API 契約凍結照過；預設帳號 `Store` 行為不變；`bb48449` 樣本啟動後零改寫 |
| mode／owner 在 uid 10001 子程序驗 | 只在 CI：`test_mode_and_owner_as_the_add_on_user`（第 6 節），含「沒有對外來項目 chmod」；本機用模擬跑過探針 |
| 新測試沒有條件式 skip | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail` |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 用 `T`×43、`C`×43 或執行時產生（`test_new_tokens_avoid_the_taken_values` 另用 `X`／`Y`／`Z`×43 的低熵假值），憑證 `DUMMY-…`，網址 `.invalid`；秘密預檢見第 8 節 |
| 同 PR 更新帳本 | 通過：4 個新列管檔（3 個新模組＋`config.py`）、`products.py` 摘要更新；帳本預檢 OK |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG | 通過 |

## 12. 還沒解決、交給後面的片

1. **MF-1 待主對話確認**：本片照契約開頭規則改成和 PaaS 一致（第 3 節）。
   - 確認後：計畫 §4.2「每筆」列與契約第 8 節要拿掉「不是 3000／8081／8099」半句（只剩「1024～65535」）。
   - listener port 的 `disabled_reason` 和 PaaS 有細微差別（第 3 節），一起定。
   - 要改回「8081／8099 整份壞」：revert 第 13 節的 C3，在契約第 9 節補一列（PaaS：spawn 時才拒；HA：整份壞；附理由），decisions 與本筆記各記一行。
2. **和同一波其他片的 rebase**：HM-04、HM-06 也改 `products.py`（帳本的 `products.py` 摘要要在 rebase 後重產）；HM-13a 可能在 entrypoint 或
   `restore_detect.py` 自己定義 `.restore-detected`、`.instance-sentinel` 等檔名，和本片 `Layout` 的同名常數要收斂成一個來源。
3. **HM-08 起接線時要改的測試**：`tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED`（HM-08 接 `features.py`、`profiles.py`，HM-13b 讓入口 import
   `profiles.py` 做存在檢查）；同檔的零改寫測試在 HM-13a／b 要加「開通後只多 sentinel 兩檔」。
4. **PaaS 變動清單**（MF-2，第 9 節）：開 PR 前在連得到 Gitea 的地方補跑。
5. **決策同步**：第 10 節的決策由主對話寫進 `docs/multi-profile/decisions.md`；DQ-16 的細節目前照契約暫定值。
6. **S-08（HM-08、HM-10）**：已開的額外帳號 store 之後的讀寫走路徑，沒有釘住建構時驗過的目錄。收據（`operations.py` 的
   `OperationJournal(store.path)`）、owner-defaults、`child_spec` 也都走路徑，只改 `Store` 的讀寫補不齊。HM-08 做每帳號執行套件與 state
   簽章快取時，一起改成留住驗過的目錄 fd（`dir_fd=`）或每次比對目錄的 `(st_dev, st_ino)`。同 uid 才做得到（DQ-37）。
7. **S-14（DQ-16，HM-10 開工前定）**：讀檔也用執行中 Python 的 Unicode 資料庫擋 Cn。之後換新的 Python、名稱用了新字元，再回到舊映像時，
   整份索引會被判壞、8081 全部 503。建議 Cn 只在建立與改名時擋、讀檔不擋，或寫進文件。現在沒有程式會寫名稱，沒有相容問題。
8. **S-15（HM-10、HM-13b）**：隔離目錄名與索引隔離名只到秒，同一秒做兩次會撞名，`rename` 會蓋掉空目錄或檔案。改名時用不覆蓋的寫法
   （檢查後在全域 CRUD 鎖內改名，或 `renameat2(RENAME_NOREPLACE)`），需要時加序號，`parse_quarantine_name` 跟著改。
9. **HM-10 檢查清單**：寫索引一律傳 `expected=`：啟動時（或「隔離帳號索引」之後）讀到的 view，或上一次寫入回傳的 view。不能為了寫而重新
   `read_index` 拿新的基準：那等於替外改過的檔背書，會洗掉 DQ-12 的「503 到重啟」。`ProfileDataError` 之後用手上的 view 複查，照結果維持
   503 與隔離。
10. `checks` 秒數開 PR 後補。
11. 本機曾有一次組合執行時 `tests/test_ledger_precheck.py::test_drift_and_pinned_changes` 失敗（HM-01 的既有測試，用自己的臨時 repo）；單獨重跑 8 次、
    組合重跑 2 次、全套 1 次都通過，原因沒找到，請在 CI 留意。
12. 本機環境：`setup_repo_env.sh` 的 UI `npm ci` 之後沒有 `npm run browser:install`，全套 pytest 會多 22 個瀏覽器測試失敗（找不到 Chromium）；
    本片的 clone 已補裝（不進 git）。其他片的 clone 若看到同樣的 22 個，是環境不是退步。
13. uid 10001 證明的探針改成降權前 import，是因為 CI runner 的家目錄可能不開放給別的使用者；這點只有 CI 跑過才知道（第 6 節）。

## 13. 審查意見處理表

審查報告：`artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-07.md`（repo 外，2026-11-15；判定「修正後通過」）。

本片的 commit（rebase 後 SHA 會變，照標題對；括號是 rebase 前的短 SHA）：

| 代號 | commit 標題 |
|---|---|
| C1 | `feat(multi-profile): add the profile data layer, the product switch and identity field classes, not wired (HM-07)`（`a278f83`） |
| C2 | `docs(provenance): add HM-07 multi-profile provenance note`（`6b39558`） |
| C3 | `fix(multi-profile): let an index port on the add-on's own listeners stop only its profile, as PaaS does (HM-07)`（`40f9899`） |
| C4 | `fix(multi-profile): refuse to create a profile of OpenDesign or Odoo Manage in ProductStore (HM-07)`（`d66e278`） |
| C5 | `fix(multi-profile): write the profile index only over the view this process vouches for (HM-07)`（`b1ce38d`） |
| C6 | `fix(multi-profile): fsync the parent of a new profile directory and keep a profile state's ctime on reads (HM-07)`（`73d6cdb`） |
| C7 | `test(multi-profile): close the HM-07 review's test gaps`（`28c3fd9`） |
| C8 | `docs(provenance): record the HM-07 review fixes and rechecks`（本筆記這一版） |

| 編號 | 意見（摘要） | 處理 | commit | 證據 |
|---|---|---|---|---|
| MF-1 | 索引 port 3000／8081／8099 的規則，計畫與契約自相矛盾；8081／8099 整份壞比 PaaS 嚴，契約第 9 節沒有這一列 | 採 (b)：照 PaaS 與設計稿 A-port，三個都不算結構錯，只停相關帳號。**待主對話確認**（第 12 節待辦 1） | C3 | 兩個 PARITY 案例改成 ok／ok；`test_a_listener_port_stops_only_the_profile_holding_it`；N01、N02 |
| MF-2 | PaaS 變動清單沒跑 | 沒跑：這一波不連遠端。第 9 節寫好指令與要看的規則，開 PR 前由主對話補 | — | 第 9 節 |
| S-01 | 「新帳號不帶 owner-defaults 標記」沒有測試 | 採用 | C7 | `test_new_profile_never_carries_the_owner_defaults_marker`（7 個產品）；R46 |
| S-02 | 「先查擁有者再 chmod」只測了 state | 採用：目錄、lock、state 三者都先放寬；外來的那一項被拒且權限沒變 | C7 | `test_existing_only_refuses_an_entry_another_uid_owns_before_touching_it`；R34、R60、N14 |
| S-03 | uid 10001 證明分不出擁有者檢查與核心的 EPERM | 採用修法 1：探針記下對外來項目的 chmod，測試要求清單是空的；註解改準 | C7 | 第 3 節本機模擬：正式程式 0 筆，拿掉擁有者檢查 3 筆 |
| S-04 | 停用原因的優先順序沒有測試 | 採用 | C7 | `test_a_profile_keeps_its_first_disabled_reason`（產品上限、記憶體各一）；R10 |
| S-05 | 複查 lstat 出錯判 modified 沒有測試 | 採用 | C7 | `test_a_recheck_that_cannot_stat_the_index_fails_closed`；R19 |
| S-06 | `ProductStore(create=…)` 仍收 OpenDesign、Odoo Manage | 採用：`create=` 先丟 `ValueError`、什麼都不建；`existing_only` 照常能開 | C4 | `test_the_store_creates_no_profile_of_a_product_without_profiles`；N03、N04 |
| S-07 | `write_index` 不先比對就寫 | 採用：`write_index(path, entries, *, expected)` | C5 | `test_a_write_replaces_only_the_index_this_process_vouches_for`；N05～N07 |
| S-08 | 已開的額外帳號 store 沒有釘住驗過的目錄 | 留給 HM-08：收據、owner-defaults、`child_spec` 也走路徑，只改 `Store` 補不齊；同 uid 才做得到（DQ-37）；審查也把它列在接線片 | — | 第 12 節待辦 6 |
| S-09 | 額外帳號的 `load()` 每次 fchmod，ctime 一直變 | 採用：只在不是 0600 時 fchmod；預設帳號不變 | C6 | `test_reading_a_profile_state_changes_nothing`；N11～N13 |
| S-10 | 建議 `config.py` 列進帳本 | 採用：`runtime-patches.json` 加一筆，`guarded_sources` 是 `{}` | C6 | 帳本預檢列管 5 檔（第 8 節） |
| S-11 | `unavailable` 的「索引有、掃描沒有」沒測 | 採用 | C7 | `test_an_indexed_profile_the_scan_did_not_find_is_unavailable_whatever_the_credentials`；R26 |
| S-12 | 非 ASCII 外圍空白、fd 洩漏沒測 | 採用：U+3000、U+00A0、U+2003；`read_index`、`scan_profiles` 每條路徑都關 fd | C7 | PARITY 兩案＋名稱三案；`test_read_closes_its_descriptor_whatever_the_file`、`test_scan_closes_its_descriptor`；R57、R58、R61 |
| S-13 | 建目錄後沒有 fsync 上一層 | 採用：建立時 fsync `profiles/`；`ensure_profiles_directory` 之後 fsync `/data/mcp`；失敗就是錯誤 | C6 | `test_create_makes_the_new_directory_name_durable`、`test_the_profiles_directory_name_is_durable`、故障注入多一步 `fsync-parent`；N08～N10 |
| S-14 | 讀檔的 Cn 檢查綁住目前 Python 的 Unicode 資料庫 | 留給 DQ-16（HM-10 開工前定）：讀檔要不要擋 Cn 是名稱規則的細節，不由本片定；現在沒有程式會寫名稱 | — | 第 12 節待辦 7 |
| S-15 | 隔離名只到秒，同一秒會撞名 | 留給 HM-10、HM-13b：改名是那兩片做；格式是本片暫定，用到時可改 | — | 第 12 節待辦 8 |
| S-16 | 測試註解寫「section 5」 | 採用：改成 section 3（本筆記第 3 節的編號維持不變） | C3 | `tests/test_profile_index.py` 的 listener port 案例註解 |

審查報告第 8 節列的作者待辦（rebase 後重產 `products.py` 摘要、`Layout` 檔名收斂、`UNWIRED` 清單、決策同步、DQ-16、`checks` 秒數、
`test_ledger_precheck` 偶發失敗、環境沒裝 Chromium）都還在第 12 節。
