# HA 多帳號 HM-13b provenance：開機守門（撤銷、隔離、獨立驗證、休眠處理、全部撤銷標記；不受開關管）（2026-11-16）

## 結論

- **新模組 `restore_lock.py`：開機守門。** `run_product` 與 `apps/n8n/run.py` 每次開機在 legacy 遷移與預設帳號的 store 之後、任何子程式與
  listener 之前跑 `restore_lock.guard`。沒做完一律 `ConfigError`：什麼都不服務（`runtime unavailable`）、標記都保留，下次開機重跑。
  不受產品開關管：任何產品下一次發版都會帶出去。
- **今天的安裝（沒開通、沒有帳號資料）逐位元不變。** 沒有還原時只多查四個名稱，什麼都不寫、不記 log（連 ctime 都不變，8 個產品各一案）。
  有還原時（DQ-03 (b)）：記一行 WARNING「權杖已回到備份當時的值」、刪掉 entrypoint 的標記，state、收據與其他每一項都照還原的原樣。
  標記刪不掉也照常啟動（沒有帳號資料，沒有東西要撤銷），多記一行、下次再試。
- **有帳號資料或已開通時，還原照計畫 §8.4 A～F。** 快照 → 預設帳號（DQ-03 (b)：有帳號資料才撤銷並重產 child token）→ `profiles/` 底下
  每個 24 hex 目錄（不看索引）撤銷、重產、封存收據，開不了的改名隔離 → 索引旁的收據封存 → `restore-record.json`（不含任何 token 或
  憑證）→ 從磁碟重讀的獨立驗證 → 重建 sentinel → 刪 `.revoke-all-pending`、最後刪還原標記。
- **舊收據 410 `operation_restored`。** 還原帶回的收據檔改名成 `.restored`（每個收據檔只留 1 份），換上新檔，多一個
  `restored_before_ms`；比它早的操作 id（含備份後才做、隨還原消失的）一律 410。只有守門寫的收據檔有這個鍵，其他逐位元照舊。
- **休眠帳號**（沒開通、有帳號資料）：每次開機撤銷還沒撤銷的額外帳號與孤兒，已撤銷的不寫任何東西；預設帳號不動；
  bootstrap 只多 `dormant_profiles`。
- **全部撤銷**：`revoke_all()` 先寫 `.revoke-all-pending`，全部成功而且驗證通過才刪；第 k 個失敗時回逐帳號結果、標記留著，
  下次開機在 listener 前補完（不看開關）。HM-13c 的路由用它。
- **每一步都能中途斷電後重做。** 測試在 64 個改磁碟的呼叫之前與之後各停一次（128 次），下次開機都做完；磁碟滿時停下、不丟任何東西。
- **sentinel 不被任何 chmod／chown 碰到**：映像裡所有 chmod／chown／utime 呼叫點列成清單（17 處，逐一寫明目標），新增呼叫點就失敗；
  另外在執行時記錄每一次呼叫的 inode，跑過開通的 runtime、帳號增刪、全部撤銷、還原與守門、休眠開機。
- **HM-10 交來的四件都做了**：`dormant_profiles`、索引旁收據封存與 410、帳號目錄隔離名不覆蓋（同一秒加 `-2`）、守門遇到刪除或索引隔離
  做到一半的殘留（第 12 節）。
- **接續（15:2x 起，上一段在 14:3x 因額度中斷）**：草稿裡的數字全部重跑或重建核對過（第 16 節）。另外找到並修了三個缺陷：
  - `cc5adb0`（先紅後綠）：收據檔「停在兩次改名之間」那條補新檔的路，沒有套用 `c5999ed` 的時鐘下限（時鐘慢時備份裡的 id 之後會被當成新操作）。
  - `9c29b4f`（先紅後綠）：還原紀錄上限 256 KiB 放不下「8 個帳號的政策都用到 state 上限」的紀錄，守門會每次開機都停在寫紀錄、add-on
    再也起不來。改成 1 MiB。
  - `96c4d3b`（全套 pytest 抓到）：`e91fc6f` 改了 `apps/n8n/run.py` 卻沒更新 `tests/test_output_schemas.py` 對它的位元組釘選（CI 會紅）；
    換成現在的摘要。
  - 另補兩個記錄行為的測試：沒有額外帳號的產品（OpenDesign、Odoo Manage）磁碟上的帳號目錄照樣被撤銷（HM-07 審查 S-06 交下的）；
    全部撤銷時 store 回報失敗、磁碟卻已撤銷，標記照樣留著。契約第 7 節的 log 清單補漏掉的一行（`7d237f6`）。
- 先寫測試：新 3 檔在實作前收集就失敗；實作後、測試替身還沒跟上時 128 案失敗（重建核對，第 4.1 節）。臨時突變在最終程式上 32 個，
  31 個被抓到，1 個等價（第 4.2 節）。
- 本機：新 3 檔 81 案全過（約 8 秒）；全套 pytest（`1f8c29f`）5869 案、0 skip、32 分 23 秒：5861 過，失敗的 8 案＝7 個要 root 的既有案例
  ＋上面那筆釘選（`96c4d3b` 修好，該檔 189 案全過）；packaging unittest `Ran 204`、`OK (skipped=5)`；`validate.py` PASS；
  `scripts/tool_inventory.py` 通過。已知會偶發逾時的 `test_backend_loopback` 那案這次沒出現（0／1 次）。
- 兩個預檢（最終 HEAD、基準 `684a2dd`）：秘密預檢 0 命中；帳本預檢 OK（第 8 節）。
- 這條線只 commit，不 push、不開 PR。計畫 §12.1 標 HM-13b 是「審查」片：合併前要獨立安全審查（還沒做），也要 HM-03a 的結果。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-13b（計畫 §8.4「開機守門」、休眠處理、全部撤銷；§10.3；§12.3；風險高、工作量 L） |
| 分支 | `feat/ha-multiprofile-hm13b-20261116`（一般 clone，不是 worktree） |
| HA 基準 | `684a2dd`：HM-10 的 PR #104 head（`claude-delivery` `7c6f80c` 加 HM-10 的 18 個 commit）。HM-10 先合併；之後由主對話 rebase 到 `claude-delivery` |
| 本片 commit | 15 個：接續前 7 個（`3c90b6c`～`0028169`）；接續後 8 個（`cc5adb0`、`9c29b4f`、`360836e`、`5b596cd`、`7d237f6`、本筆記 `1f8c29f`、`96c4d3b`，以及補全套與預檢結果的最後一個筆記 commit；第 16 節） |
| 依據 | 計畫 §3.3、§4.1、§8.4、§8.8、§8.10、§10.3、§12.3 HM-13a／b／c；契約 §1.2、§3.5、§3.6、§4.1、§7、§8、§9；`threat-model.md`；HM-13a 的筆記與審查（`wave1/review-HM-13a.md`）；FM-04、07、13、16、78、79、80、118、119、120 |
| PaaS | 沒有搬程式。對照 `Pc/restore_guard.py`（`prepare`、`_write_config`、`_write_journal`、`_archive_journal`、`_read_journal_floor`）、`Pc/restore_inplace.py`（`_verify`）、`Pc/restore_marker.py`（任何項目都算存在）；pin `69ac425`，到 `d7f5849` 這幾檔沒變（第 9 節） |
| 決策 | DQ-03 (b)、DQ-39 (a)、DQ-13、DQ-14、DQ-21、DQ-40 (a)（第 10 節）；沒有碰到待定題 |
| 安全審查 | 還沒做（計畫 §12.1：本片要審查） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/restore_lock.py`（新） | `guard()`、`revoke_all()`、`mark_revoke_all()`、`revoke_all_pending()`、`read_record()`、`read_tokens()`、`facts()`；log 文字常數；`DEFAULT_REVOKED_WHEN_SWITCHED_ON`（DQ-03 的 (a)／(b)，現在 `False`＝(b)）；`RECORD_LIMIT` 1 MiB |
| `operations.py` | 收據檔可多 `restored_before_ms`（其他值讓收據檔 503）；`_load` 在 24 小時保留期之前先判 410 `operation_restored`；`archive_for_restore()`、`journal_path()` |
| `profiles.py` | `free_quarantine_name()`、`free_aside_name()`（不覆蓋、同一秒加 `-2`…）；隔離名的正規式收 `-n` |
| `run_product.py` | 開關每次開機只讀一次；守門在 `ProfileManager`／單帳號 runtime 之前；休眠數給 bootstrap |
| `apps/n8n/run.py` | 同上（n8n 到 HM-25 才有帳號；守門只會刪還原標記或補完全部撤銷） |
| `gateway.py` | `make_apps(dormant_profiles=n)`：bootstrap 多 `dormant_profiles`；沒給時逐位元同今天；和 `profile_view` 不能同時給 |
| `profile_runtime.py` | `ProfileRuntime(dormant_profiles=…)` 轉給 `make_apps`；模組說明 |
| `packaging/container_probe.py` | 容器驗收還原階段的檢查：標記已被守門刪掉、沒開通的產品沒有 sentinel／record／還原紀錄、還原項目都修好、state 位元不變 |
| `docs/provenance/runtime-patches.json` | 新增 `restore_lock.py`；6 個改到的列管檔重算摘要並補說明；`restore_detect.py`、`identity_fields.py` 只補「已接線」的說明 |
| 測試（新） | `tests/restore_guard_disk.py`、`tests/test_restore_lock.py`（59 案）、`tests/test_dormant_profiles.py`（7）、`tests/test_revoke_all.py`（15） |
| 測試（改） | 見第 3.10 節（含 `tests/test_output_schemas.py` 的一筆釘選） |
| 文件 | 契約（第 1.1、1.2、1.3（新）、3.5、3.6、7、8、9、10 節）、`threat-model.md`（I9、I13、第 3 節兩條）、`acceptance-matrix.md`（T-21）、`ledger-tracking.md`（`profiles.py` 那列）、`docs/operations/update-backup-rollback.md`（還原標記那列）、`docs/operations/acceptance.md`（容器驗收還原階段） |

沒改：`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`MULTI_PROFILE_PRODUCTS`（仍是空集合）、`packaging/entrypoint.py`、
`restore_detect.py`、`identity_fields.py`、`apps/runtime/*.py`、`apps/*/launch.py`（tool-surface 不用重產；`scripts/tool_inventory.py` 檢查通過）、
`tests/conftest.py`、`decisions.md`（沒有新決策）、面板（HM-11、HM-13c）。

## 3. 行為

### 3.1 觸發與今天的安裝

`guard(store, product, enabled=)` 先跑 HM-13a 的 `detect()`（開通後第一次開機在這裡建 sentinel 兩檔），再查 `.revoke-all-pending`。

| 情況 | 結果 |
|---|---|
| 沒開通、沒有帳號資料、沒有還原、沒有全部撤銷標記 | 什麼都不做（只查四個名稱：標記、`profiles.json`、`profiles`、`.revoke-all-pending`） |
| 同上，但有還原（標記） | `KEPT_NOTICE` 一行；刪標記、fsync 目錄；其他不動。刪不掉：`MARKER_LEFT` 一行，照常啟動 |
| 開通或有帳號資料，沒有還原、沒有標記、不是休眠 | 什麼都不做（開通後第一次開機只多 sentinel 兩檔） |
| 有還原、全部撤銷標記或休眠 | 第 3.2～3.5 節 |

### 3.2 還原：A～F

範圍 S：預設帳號、`profiles/` 底下每個 24 hex 目錄（索引內、孤兒、索引壞都算）、既有的隔離目錄（只讀 token 放進快照，從不當帳號開）。

| 步 | 做法 | 失敗時 |
|---|---|---|
| A 快照 | 預設帳號從 store 讀；每個目錄的 `state.json` 用 `read_tokens` 原始讀（不拿鎖、不 chmod），讀得到的 token 與 child token 放進記憶體 | 預設帳號讀不到：`ConfigError` |
| B 預設帳號 | 有帳號資料（或有全部撤銷標記）時：`change_token(None,'revoke')`、新的 child token（不和快照裡任何值相同）、封存收據。沒有帳號資料：原樣不動 | 記一行、繼續撤銷其他帳號，最後停 |
| C 帳號目錄 | `existing_only` 開得了：撤銷、新的 child token、封存收據。開不了（任何原因）：改名 `profiles/.quarantine-<id>-<UTC>[-n]`、fsync `profiles/`；writer lock 被別人拿著的只算失敗、不搬。最後封存索引旁的收據 | 同上 |
| D 紀錄 | `restore-record.json`（第 3.6 節） | 停 |
| E 獨立驗證 | 從磁碟重讀每個目錄（不經寫入的 store）：被撤銷的 token 是 None；新的 child token 和快照不同、也不在快照裡；現在的任何 token、child token 都不在快照裡（預設帳號沒被撤銷時排除它自己的兩個值，而且它要和快照一模一樣）；帳號目錄＝快照的減掉隔離的；每個隔離目錄都還是隔離目錄 | 停（不開 listener） |
| F 收尾 | 守門自己的名稱若被目錄占用先移開；`restore_detect.rebuild()`；刪 `.revoke-all-pending`；最後刪還原標記；fsync 目錄 | 停 |

「停」＝ log `UNFINISHED`（括號裡是固定的原因）、`ConfigError`、標記都保留。每一步都冪等：token 已是 None 時不再多一筆歷史；child token 每次重做都
再換；沒有收據的收據檔不再封存；紀錄重寫。所以停在任何地方，下次開機都看得到還原（標記還在，或 sentinel 還沒重建），再做一次就好
（第 4.2 節、`test_a_start_stopped_anywhere_is_finished_by_the_next`）。

為什麼 E 比對的是這次的快照、不是備份本身（契約 #101）：Supervisor 還原不留備份副本。中途斷電後重做時，上一次已換掉的值已不在磁碟上；
備份裡還留在磁碟上的值一定在這次的快照裡，所以「現在任何值都不在快照裡」仍然證明備份裡能認證的東西現在都不能認證。

### 3.3 收據（FM-07；契約 §3.5、#67、#104）

- `archive_for_restore(state.json 或索引的路徑, 還原當下的毫秒)`：先寫新收據檔的暫存檔並 fsync，再把舊檔改名 `.restored`（蓋掉更舊的那份）、
  換上新檔、fsync 目錄。磁碟滿時連暫存檔都建不出來，舊檔原樣。
- 新檔：`{"version":1,"key":<新的>,"expired_before_ms":0,"receipts":{},"restored_before_ms":<還原當下>}`。
  `restored_before_ms` 不會早於被封存的收據檔裡最新的 id、`expired_before_ms` 或 `restored_before_ms`（同 PaaS `_read_journal_floor`）：
  主機時鐘比備份慢時，備份裡的 id 也一律 410（`test_a_slow_clock_never_lets_a_restored_id_through`，`c5999ed`）。這個下限最多比還原當下
  晚 24 小時（`TTL_MS`）：偽造備份裡遠在未來的 id 不會讓之後好幾年的新操作都 410（`test_a_far_future_id_in_a_restored_journal_moves_the_cutoff_one_retention_period_at_most`，`0028169`）。
- 重做時：沒有收據的收據檔（上一次寫的）不再封存，只把 `restored_before_ms` 往後推；收據檔不見但旁邊有 `.restored`（停在兩次改名之間）就補新檔，
  時間同樣不早於封存裡最新的 id（`test_an_archive_left_without_its_new_journal_keeps_the_floor_of_a_slow_clock`，`cc5adb0`）；兩個都沒有
  （從沒有過操作）就什麼都不寫。
- 預設帳號沒被撤銷時（DQ-03 (b)，沒有帳號資料）它的收據不動：24 小時內重送備份前的 id 照今天回 completed（不回 token）。
- 全部撤銷、休眠撤銷都不封存（不是還原）。

### 3.4 休眠（I13；契約 §1.2、#24）

- 沒開通、有帳號資料：每次開機對每個帳號目錄：token 還不是 None 的撤銷並換 child token；已是 None 的什麼都不寫；開不了的隔離。預設帳號不動
  （同時偵測到還原時照第 3.2 節，有帳號資料就撤銷預設帳號）。
- 有撤銷或隔離時寫 `restore-record.json`（`dormant` 段落）並記 `DORMANT_NOTICE` 一行；之後的開機不寫、不記。
- `Outcome.dormant`＝剩下的帳號目錄數，給 bootstrap 的 `dormant_profiles`。開關關時沒有任何管理路由（計畫 §3.3）。
- 沒有額外帳號的產品（OpenDesign、Odoo Manage）也一樣：磁碟上有帳號目錄（只會是手工拼的備份）就撤銷，並撤銷預設帳號
  （`test_a_profile_directory_of_a_product_without_profiles_is_revoked`）。

### 3.5 全部撤銷（契約 §1.3、#82）

- `mark_revoke_all()`：`O_CREAT|O_EXCL|O_NOFOLLOW` 建 `.revoke-all-pending`、fsync 檔與目錄（已存在就保留）。這是第一個改磁碟的動作。
- `revoke_all(store, product, stores=)`：預設帳號 → 帳號目錄依 id，各自撤銷並換 child token；開不了的隔離；跑 E；全部成功才刪標記。
  回傳 `RevokeAll(results, finished)`，results 是 `revoked`／`failed`／`quarantined`。store 回報寫入失敗時，就算磁碟上已撤銷，那個帳號也是
  `failed`、標記留著（`test_a_failure_the_store_reports_keeps_the_marker_even_when_the_disk_shows_it_done`）。
- 執行中的管理器拿著已登錄帳號的 store（writer lock）：HM-13c 要把它們放進 `stores`。沒放的話那個目錄開不了，但守門看得出 lock 被別人拿著，
  只算失敗、不會把它搬去隔離（`test_revoke_all_uses_the_stores_its_caller_holds`）。
- 開機看到標記（任何種類的項目，內容不看）：不看開關都補完，包括沒開通、沒有帳號資料的預設帳號（管理員要求過）。
- 8081 上失敗帳號回 503、`TokenAccess.committed()`、重起子程式（新的 child token 要重起才生效，HM-06 審查 S-07）是 HM-13c 的路由要做的；
  開機補完時子程式還沒起，不用重起。

### 3.6 還原紀錄（契約 §3.6）

格式見契約 §3.6。重點：每列 `id`、`label`（索引裡的名稱；孤兒或索引讀不到是 `null`）、`is_default`、`token`（`revoked`／`kept`／
`already_revoked`）、`identity`（`identity_fields` 的身分欄位）、`policy`（政策與 n8n session 欄位）、`reviewed_at: null`；另有 `restore`
（時間、兩個訊號）、`dormant`、`index`、`quarantined`、`profiles_directory`、`other_entries`。HA 存的網址本來就不能帶帳密、query、fragment
（`config.http_url`），所以不必像 PaaS 的 `url()` 再遮；測試確認紀錄裡沒有任何 token、child token 或密碼。

上限 1 MiB（`RECORD_LIMIT`，寫入與 `read_record` 共用；`9c29b4f`）：每列是 state 的一部分，store 收的 state 最多 64 KiB，政策欄位各自的
上限（停用工具 256 個、禁止的操作 16 KiB、Odoo 方法清單 16 KiB）加起來就接近 64 KiB。預設帳號、索引裡 5 個與 10 個孤兒都到上限也放得下；
更多只會是手工拼的備份，這時守門停下（fail closed，`threat-model.md` 第 3 節）。

### 3.7 守門自己的名稱（HM-13a 審查 SF-7；契約 #103）

sentinel、record、record 暫存檔、還原標記、全部撤銷標記的名稱若是目錄（偽造的備份；修復接受目錄），改名放到 `<名稱>.quarantine-<UTC>[-n]`，
從不刪。不處理的話 `rebuild()` 每次失敗、add-on 再也起不來。`profiles` 不是目錄時記一行、照撤銷預設帳號後啟動（契約 #102；裡面什麼都不會被
開或路由，開通後 HM-08 對每個 token 回 503）。

### 3.8 開機順序與 fail closed

- `run_product.run`：legacy 遷移 → 預設帳號的 store → **守門** → `ProfileManager`（開通）或單帳號 `ProfileRuntime` → listener → 子程式。
  測試記錄事件順序：守門結束前沒有任何 Supervisor、子程式或 listener（開關開與關、n8n 各一次）。
- 守門沒做完：`run()` 丟 `ConfigError`，`main()` 印 `runtime unavailable; local recovery required`；沒有任何 listener 或 Supervisor 被建立
  （`test_a_guard_that_does_not_finish_serves_nothing`）。Supervisor 會再起 add-on，下次開機守門重跑。

### 3.9 sentinel 不變式

- 靜態：`test_every_mode_and_owner_call_site_is_reviewed` 用 AST 掃映像裡所有 Python（核心套件、`apps/`、`packaging/entrypoint.py`、
  `packaging/management_launcher.py`），列出每個 chmod、fchmod、lchmod、chown、fchown、lchown、utime、copymode、copystat、chflags 呼叫點
  （17 處：`config.py` 4、`operations.py` 1、`profiles.py` 2、`packaging/entrypoint.py` 7、Headscale 子程式的測試碼 3）和它的目標；
  `restore_lock.py`、`restore_detect.py` 沒有。新呼叫點要先審過、加進清單。
- 執行時：`test_nothing_chmods_or_chowns_the_sentinel` 包住 os 的這些函式，記錄每次呼叫的 inode；跑開通的 runtime（開機、預設帳號與 A 輪替
  token、經 8099 建立與刪除帳號）、全部撤銷、還原與守門、休眠開機。每一段 sentinel 的 inode 都不是目標，而且 restore detection 都判
  `consistent`（inode 與 ctime 都沒變；還原那段 sentinel 本來就換新，只看重建後是否一致）。每段只比該段的紀錄：刪掉的檔的 inode 號會被重用。
- 本片新增的寫入路徑（`_new_journal`、`_write_record`、`mark_revoke_all`、隔離與移開的 rename）都是 `os.open(…, 0o600)` 或 rename，沒有任何
  chmod／chown。

### 3.10 為了守門改的既有測試

| 檔 | 改了什麼、為什麼 |
|---|---|
| `tests/multi_profile_runtime.py`（HM-08） | `create_profile` 在第一個帳號之前先建 sentinel。正式環境只有開通過的 add-on 才會建帳號，而它第一次開機就建了 sentinel；不建的話「有帳號資料卻沒有 record」會被當成還原（HM-13a 的規則），守門撤銷所有 token（第 4.1 節：128 案失敗） |
| `tests/test_single_profile_golden.py`（HM-01） | `expected_entries` 在產品開通時多 sentinel 兩檔（`test_router_passthrough` 開著開關重跑黃金回歸）。沒開通時一字不變 |
| `tests/test_router_passthrough.py`（HM-08） | `test_switched_off_profile_data_on_disk_changes_nothing` 改名 `…_is_revoked_and_nothing_else_changes`：原文就寫「休眠撤銷是 HM-13b 的」；現在斷言 B 已撤銷、多一個還原紀錄、其他每一項不變 |
| `tests/test_profile_admin_api.py`（HM-10） | `test_there_is_nothing_to_quarantine_without_an_index_file` 先建 sentinel（同上） |
| `tests/test_upgrade_zero_rewrite.py`（HM-07） | `UNWIRED` 清空（HM-13b 接上 `restore_detect` 與 `identity_fields`）；入口實際載入 `restore_lock`；`bb48449` 樣本開通後正式開機只多 child 與 sentinel 兩檔（HM-13a 交下的另一半） |
| `tests/test_restore_detection.py`（HM-13a） | 容器探針還原階段的兩案（一般使用者與 root）在 entrypoint 之後跑管理程序的守門，再做探針的檢查 |
| `packaging/test_container_probe.py`（HM-13a） | 探針檢查的新期望（標記已刪、沒開通沒有還原檔）與開通候選映像那一案 |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES` 裡 `apps/n8n/run.py` 的 SHA-256 換成現在的（開機守門與 `dormant_profiles`，沒有工具、schema 或 handler 的變動；`96c4d3b`，同 HM-04、HM-20 的做法） |

## 4. 守門有效的證據

### 4.1 先紅後綠

接續時（15:2x 之後）每一列都重新核對，不靠上一段的 log：用 `git archive` 把當時的樹匯出到 repo 外，需要時把個別檔換回前一版再跑
（venv 與 `node_modules` 用符號連結指回 clone，UI 的 `dist` 複製一份：`ui.py` 用 `O_NOFOLLOW` 開它，連結會被拒）。

| 階段 | 結果 |
|---|---|
| 只有新測試（`3c90b6c` 的樹，核心程式是基準的） | 新 3 檔與改過的 `test_restore_detection.py`、`test_upgrade_zero_rewrite.py`、`test_router_passthrough.py` 共 6 檔收集就失敗（`ImportError: cannot import name 'restore_lock'`） |
| 實作完成、既有的測試替身還沒跟上（重建：`e91fc6f` 的樹，只把 `multi_profile_runtime.py`、`test_single_profile_golden.py`、`test_router_passthrough.py`、`test_profile_admin_api.py` 換回 `684a2dd` 版） | 用替身的 18 檔（新 3 檔＋HM-08～HM-14 的 15 檔；要真子程式的 `test_backend_loopback.py` 不跑）420 案：新 3 檔 74 案全過；128 案失敗，分在 12 檔（`test_gateway_stream_endings` 31、`test_profile_routing` 22、`test_router_passthrough` 22、`test_profile_quotas` 12、`test_profile_admin_api` 11、`test_reply_mask_union` 8、`test_gateway_queue_ha` 6、`test_initialize_generation` 6、`test_carries_no_request` 4、`test_gateway_busy_shapes` 3、`test_admin_pipeline_matrix` 2、`test_staggered_start` 1）。原因都是替身直接在磁碟上建帳號、從沒建 sentinel：守門判還原、撤銷全部 token（log 有 `REVOKED_NOTICE`） |
| 同上，但 `multi_profile_runtime.py` 用 `e91fc6f` 版（替身先建 sentinel） | `test_router_passthrough`、`test_profile_admin_api`、`test_single_profile_golden` 98 案：19 案失敗＝開著開關重跑的黃金回歸 12（多了 sentinel 兩檔）、休眠的既有測試 6（開關關＋帳號資料不再「什麼都不變」）、沒有索引檔的隔離 1；三檔跟上後通過 |
| 全部改完（`e91fc6f`） | 新 3 檔 74 案全過 |
| 收據下限（`c5999ed`） | `test_a_slow_clock_never_lets_a_restored_id_through` 在 `e91fc6f` 的 `operations.py` 上紅（`restored_before_ms` 是慢一小時的時鐘），改完綠；新 3 檔 75 案 |
| 下限的上限（`0028169`） | `test_a_far_future_id_in_a_restored_journal_moves_the_cutoff_one_retention_period_at_most` 在 `c5999ed` 的 `operations.py` 上紅（`restored_before_ms` 是 `9999999999999`），改完綠；新 3 檔 76 案 |
| 補新檔也守下限（`cc5adb0`，接續後） | `test_an_archive_left_without_its_new_journal_keeps_the_floor_of_a_slow_clock` 在 `0028169` 的程式上紅（`restored_before_ms` 是慢一小時的時鐘），改完綠 |
| 還原紀錄上限（`9c29b4f`，接續後） | `test_a_restore_of_states_as_large_as_the_store_takes_still_finishes` 在 256 KiB 上限紅（`not finished (the restore record could not be saved)`），1 MiB 綠（紀錄 > 256 KiB） |
| 記錄行為的兩案（`360836e`、`5b596cd`，接續後） | 沒有額外帳號的產品 2 案、store 回報失敗 1 案：程式本來就這樣，寫上就過（不是先紅後綠）。新 3 檔 81 案 |

### 4.2 臨時突變（`SP:hm13b/mutate2.py`：在 repo 外的匯出樹一次改一處，跑相關測試，跑完還原；`-k "not test_root_"`）

在 `360836e` 的程式上重跑（上一段在 `e91fc6f` 上跑過 M01～M28，結果相同；接續時 M20 照改過的 `operations.py` 換寫法，並加 M29～M32）。
未修改的匯出樹 259 案全過、5 案 deselected。

| 突變 | 結果 |
|---|---|
| M01 有帳號資料時不撤銷預設帳號 | 被擋 |
| M02 生產值改成 DQ-03 (a) | 被擋 |
| M03 不換 child token | 被擋 |
| M04 不撤銷 token（只換 child token） | 被擋 |
| M05 隔離名不避開已有的名稱 | 被擋 |
| M06 不封存收據 | 被擋 |
| M07 沒有收據的收據檔也再封存一次 | 被擋 |
| M08 先改名舊收據、才寫新檔 | 被擋（磁碟滿那案） |
| M09 先刪標記、才重建 sentinel | 被擋（中途停下那案） |
| M10 休眠時已撤銷的也再換 child token | 被擋 |
| M11 守門放在開關後面 | 被擋 |
| M12 `run_product` 不跑守門 | 被擋 |
| M13 n8n 不跑守門 | 被擋 |
| M14 bootstrap 沒有 `dormant_profiles` | 被擋 |
| M15 看不出 writer lock 被別人拿著 | 被擋 |
| M16 守門名稱上的目錄直接刪掉 | 被擋 |
| M17 紀錄帶 token | 被擋 |
| M18 `revoke_all` 有失敗也當作做完 | **沒被擋（等價）**：`check()` 的結果一定含之前記下的失敗（`failed` 一路累積），`not sweep.failed` 只是提早一步。`5b596cd` 加的那案證明 store 回報失敗、磁碟已撤銷時標記也留著（這個突變下也留著，所以擋不到） |
| M19 `revoke_all` 先撤銷才寫標記 | 被擋 |
| M20 空收據檔的時間不往後推 | 被擋 |
| M21 範圍只看索引 | 被擋（孤兒沒撤銷） |
| M22 舊操作 id 不回 410 | 被擋 |
| M23 不跑獨立驗證 | 被擋 |
| M24 容器探針仍要標記在 | 被擋 |
| M25 單帳號還原不刪標記 | 被擋 |
| M26 隔離名的 `-n` 不認 | 被擋 |
| M27 DQ-03 (b) 保留的預設帳號被改寫 | 被擋 |
| M28 不重建 sentinel | 被擋 |
| M29 收據檔不見時不看封存的下限 | 被擋 |
| M30 還原紀錄上限改回 256 KiB | 被擋 |
| M31 遠未來的 id 不設上限 | 被擋 |
| M32 新收據檔的時間低於被封存的最新 id | 被擋 |

## 5. 本機檢查（2026-11-16，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

開發中的反覆執行用 `--noconftest` 加一個裝同樣網路與子程序守門、只是不拿全機測試鎖的外掛（同 HM-13a 的做法；只跑不開固定 port、不起真子程式
的檔）。全套用正式的 `tests/conftest.py`，排在 wave1 鎖後面。

| 檢查 | 結果 |
|---|---|
| 新 3 檔（`test_restore_lock.py` 59、`test_dormant_profiles.py` 7、`test_revoke_all.py` 15；`5b596cd`） | 81 案全過，8.1 秒（最慢的是中途停下那案 3.9 秒：128 次停下） |
| 影響到的 32 檔（不拿鎖、`1f8c29f`；HM-01 黃金回歸與兩個契約凍結、HM-07～HM-10、HM-13a、HM-14 的檔、新 3 檔、`test_tool_inventory`、`test_ledger_precheck`、`test_log_scan`） | 1,012 案：1,006 過；6 個失敗都是要 root 的（`test_restore_detection.py` 的 5 案 `test_root_*`、HM-07 的 1 案），101.8 秒 |
| 全套 pytest（正式 conftest、wave1 鎖；`1f8c29f`；Chromium 照 CI 的 `npm run browser:install` 裝在 `node_modules`） | 5869 案、0 skip、1,943.5 秒（32 分 23 秒）：5861 過；8 個失敗＝7 個要 root 的既有案例（第 6 節）＋`test_output_schemas.py::test_exact_source_bytes_are_reviewed_not_guessed_from_type_hints`（`apps/n8n/run.py` 的位元組釘選沒跟上）。新 3 檔 81、`test_restore_detection` 139、`test_upgrade_zero_rewrite` 45、黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19、`test_router_passthrough` 49 案都在裡面 |
| 修好釘選之後（`96c4d3b`）：`tests/test_output_schemas.py` | 189 案全過。全套沒有重跑：只改這個檔的一筆 SHA-256，沒有別的測試 import 它；共用鎖當時還排著 3 個（約要等 1～2 小時）。全套以 CI 為準 |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`，不用 PYTHONPATH） | `Ran 204`、`OK (skipped=5)`（5 個 `skipUnless(root)` 同基準） |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| `scripts/tool_inventory.py` | 通過（沒動 tool-surface 的來源） |
| 臨時突變 | 第 4.2 節 |
| `git status` | 乾淨 |

## 6. 只在 CI 跑的測試與時間

- 要 root 的（本機一般使用者執行會在第一行失敗，不會 skip）：`test_restore_detection.py` 的 5 案 `test_root_*`，其中
  `test_root_the_container_probes_restore_stage_meets_the_entrypoint` 是本片改的（entrypoint 之後以 uid 10001 跑守門）；HM-07 的
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`；`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`。
- 本片新測試都在 in-process 或暫存目錄跑：不起真子程式、不開固定 port（開通的 runtime 用 `NoProcessSupervisor` 與 MockTransport）。
- 時間（全套的 junit，`1f8c29f`）：新 3 檔 7.8 秒（中途停下那案 3.9 秒最久）；新增或改過的既有案例（零改寫開通 8 案、休眠 6 案、探針 1 案）
  合計 0.5 秒。CI（root、runner 較慢）推估多 15～25 秒，在每片 1.5 分鐘內。

## 7. `checks` 秒數

開 PR 後補（前、後兩個 run 的 `checks` 秒數）。

## 8. 預檢結果

在本筆記的 commit 之後、以最終的 HEAD 跑（基準 `684a2dd`）：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <scratchpad>/hm01/gitleaks-tools --repo . --base 684a2dd --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 684a2dd
```

- 秘密預檢：gitleaks 8.28.0（釘選、已核對）；本片 15 個 commit（`684a2dd..HEAD`）、`--full` 的 HEAD 全部檔與全歷史：0 命中。測試的 token 都在
  執行時產生；憑證用 `DUMMY-…`、網址 `.invalid`（照 `tests/fixtures/owner_defaults/README.md`）。
- 帳本預檢：`runtime-patches.json` 175 個路徑、`runtime-sources.json` 70、`tool-surface.json` 159，都 0 漂移、0 缺檔；對 `684a2dd` 改了
  28 個檔，列管檔 7 個（`apps/n8n/run.py`、`gateway.py`、`operations.py`、`profile_runtime.py`、`profiles.py`、`restore_lock.py`、`run_product.py`），
  帳本 1 個；新增或改到而沒列管的執行期檔 0 個。結果 OK。

## 9. PaaS 變動（本機唯讀 PaaS repo，`git log/diff 69ac425..d7f5849`；沒有 fetch、沒有 checkout）

- `restore_guard.py`、`restore_inplace.py`、`restore_marker.py`、`operations.py`（含 `routers/operations.py`）：`69ac425..d7f5849` 沒有變動。
- `profiles.py`：只有 `e6971c0`（#155 的閘道預算：預算預設值扣掉子行程記憶體），和還原無關（HM-31 的範圍）。
- 測試：`test_restore_marker.py`（`f5223be`）、`test_restore_runbook.py`（`36bde7b`）只因移除 VK 拿掉參數或表格列。
- `docs/paas-config-restore-runbook.md`：移除 VK（`36bde7b`）；Nextcloud 換使用者或網址時撤銷舊網址（`0f94aa4`，HM-22 的範圍）。記錄網址前遮帳密的
  `url()` 沒變；HA 存的網址本來就不能帶帳密（第 3.6 節）。
- 結論：本片照用的 PaaS 規則（任何項目都算標記存在、獨立驗證「備份裡能認證的東西現在都不能認證」、新收據檔讓舊 id 410、新收據檔的時間不早於
  舊收據檔最新的 id）沒有變。

## 10. 本片用到的決策

| DQ | 怎麼用 |
|---|---|
| DQ-03 (b) A2 | 只有磁碟上有帳號資料的還原才撤銷預設帳號；沒有帳號資料時預設帳號的 state 與收據都照還原的原樣，log 提示權杖已回到備份當時的值；開通的產品另寫還原紀錄給面板（HM-13c 顯示）。(a) 寫成常數 `DEFAULT_REVOKED_WHEN_SWITCHED_ON`，兩種模式都有測試 |
| DQ-39 (a) | HM-03a 若證實某種還原偵測不到，首發不出貨、先修偵測（第 11 節） |
| DQ-13 | 守門不碰 endpoint（只存在預設帳號）；還原紀錄不記 endpoint |
| DQ-14 | 守門從不刪帳號目錄、孤兒或隔離目錄（只撤銷、改名）；刪除與憑證抹除只在面板刪除時做 |
| DQ-21 | 守門沒做完時整個 add-on 不啟動（開機時的停止，不是監看結束）；啟動之後的監看規則不變 |
| DQ-40 (a) | 撤銷後的 child token 不和任何帳號的舊值或新值相同（⑥⑧）；全部撤銷的 If-Match／Idempotency-Key 在 HM-13c 的路由（③） |

沒有碰到待定題（DQ-04、22～24、26、27、35、41、42、44～46 都沒用到）。還原紀錄上限 1 MiB 是本片的實作細節，不是決策題。

## 11. 待 HM-03a 確認（合併前要有結果；不可靠就照 DQ-39 (a)）

| 項目 | 本片的假設 | 不成立時 |
|---|---|---|
| UC-08：full、partial、加密備份各還原一次，`/data/mcp` 屬 root、`re-owned N` 那一行、`.restore-detected` 建立 | 訊號 1 觸發（HM-13a 讀 Supervisor 原始碼推得） | 只靠訊號 2；兩個都不觸發就照 DQ-39 (a) 不出貨，改用 `backup_exclude` 備案 |
| sentinel 的 `st_ino`、`st_ctime_ns` 在 add-on 重啟、主機重開、add-on 更新、Supervisor 更新後不變（UC-25；記下資料分割的檔案系統與 inode 大小） | 不變（一般程式改不了 ctime） | 每次開機都被當成還原：有帳號資料時每次開機都撤銷全部 token。要評估只比到秒、或改用 `backup_exclude` |
| 還原後 sentinel 一定是新檔（ctime＝還原當下） | 是（檔案層級還原） | 區塊層級的回滾看不到（HM-13a 已列已知限制，HM-18 寫進文件） |
| 還原樹裡不會有硬連結（`copytree` 一個一個複製） | 是 | 第二個連結的 state 會讓那個帳號被隔離（方向安全） |
| UC-24 (ii)：拉不到舊映像時 Supervisor 沿用目前映像 | 是（`suppress(DockerError)`） | 新映像＋舊資料仍有訊號 1，守門照跑；不影響本片 |
| HAOS 開機時主機時鐘不會遠快於實際時間 | 是 | 收據的還原時間點可能偏後（`threat-model.md` 第 3 節） |

HM-03a 的結果出來後，寫回本筆記這一節（或 HM-13a 的筆記第 11 節），並在 PR 說明列出。

## 12. 前面各片交給 HM-13b 的待辦

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-13a 第 11 節 | `detect()` 接進開機順序（legacy 遷移之後、任何 listener 與子程式之前），`enabled` 呼叫時讀 | 做了：`run_product`、`apps/n8n/run.py`；開關每次開機讀一次，守門與 runtime 共用（第 3.8 節） |
| 同上 | 還原時跑守門，最後 `rebuild()` 再刪標記；沒開通、沒有帳號資料時記一行 WARNING 後刪標記 | 做了（第 3.1、3.2 節） |
| 同上 | 測試掃描所有 chmod／chown 呼叫點，確認碰不到 sentinel | 做了：靜態清單＋執行時記錄（第 3.9 節） |
| 同上（HM-07 交接另一半） | 零改寫：開通時正式開機只多 child 與 sentinel 兩檔；沒開通不多任何檔 | 做了（`test_a_state_bb48449_wrote_starts_without_any_rewrite` 開關兩種，8 個產品） |
| 同上 | 把 `profiles`、`restore_detect` 移出 `UNWIRED` | 做了；`identity_fields` 也移出（還原紀錄用它）；`UNWIRED` 現在是空的 |
| 同上 | 守門的檔名一律取 `profiles.py` 的常數，不另寫字串 | 做了（`restore_lock.py` 只用 `profiles` 的常數；`state.json`、`.writer.lock` 是 store 自己的名稱） |
| 同上 | `container_probe.check_restored_start()` 改成新行為 | 做了（第 2 節；探針的 mock 測試與 `tests/` 的兩案跟著改） |
| HM-13a 審查 SF-7 | sentinel 或 `.instance-record.tmp` 被目錄占用時 `rebuild()` 一直失敗 | 做了：移開到 `<名稱>.quarantine-<UTC>[-n]`，兩個標記也一樣（第 3.7 節）；契約布局補 `.instance-record.tmp`（原本交 HM-18，本片動到第 8 節就一起補） |
| HM-13a 審查 SF-10 | 沒開通、沒有帳號資料時不能呼叫 `rebuild()`（會多兩個檔） | 守門只在 `detection.active` 時重建；單帳號還原的 8 案確認不多 sentinel、record 或還原紀錄 |
| HM-13a 第 11 節 | HM-13a 先發、HM-13b 還沒發的期間留下的舊標記；HM-13b、HM-13c 的通知要涵蓋 | 沒開通：照單帳號還原處理（一行、刪標記）；開通後第一次開機：當成還原、沒有帳號資料不撤銷、寫還原紀錄。通知文字「資料是從備份還原的」對舊標記也成立。面板的文字交 HM-13c |
| HM-07 第 12 節第 3 點 | `UNWIRED` | 同上 |
| HM-07 第 12 節第 8 點（S-15） | 隔離目錄名同一秒撞名 | 做了：`free_quarantine_name` 檢查後再改名、需要時加 `-2`…；`parse_quarantine_name` 認得 `-n`（守門開機時單一程序；同 uid 不是邊界，DQ-37） |
| HM-07 第 3 節（審查 S-06） | OpenDesign、Odoo Manage 的 `existing_only` 留給 HM-13b 撤銷還原留下的殘留 | 做了：守門對任何產品都用 `existing_only` 開帳號目錄；`test_a_profile_directory_of_a_product_without_profiles_is_revoked`（兩個產品各一案，`360836e`） |
| HM-06 第 12.3 節（審查 S-07） | 重產 child token 之後要重啟子程式 | 開機時子程式還沒起，起的時候就讀新的；執行中的全部撤銷要重起：交 HM-13c |
| HM-08 第 3.4 節 | 開關關時磁碟上的休眠帳號 token 不遮，HM-13b 開機時撤銷 | 做了（休眠處理） |
| HM-09 第 13.2 節 | 開機順序；隔離、還原守門逐帳號動作、休眠撤銷的 log 事件 | 做了（契約第 7 節 log 列） |
| HM-10 第 13.2 節 | 休眠帳號的 bootstrap `dormant_profiles` | 做了（`make_apps(dormant_profiles=)`；`test_the_bootstrap_of_a_dormant_add_on_only_adds_dormant_profiles`） |
| 同上 | 索引旁收據在還原時封存（`.profiles.json.operations.json.restored`）與 410 `operation_restored` | 做了（第 3.3 節） |
| 同上 | 帳號目錄的隔離名（S-15） | 做了 |
| 同上 | 開機守門與刪除、索引隔離的互動（`.revoke-all-pending`） | 做了：刪到一半的目錄（沒有 state）被隔離；刪除的待完成收據重送回 410；已被改名的索引檔（`profiles.json.quarantine-…`）不碰；全部撤銷標記補完並刪掉（`test_the_guard_meets_an_interrupted_deletion_and_index_quarantine`）。守門只在開機跑，不會和執行中的刪除或隔離同時發生 |
| HM-10 第 13.1 節（HM-00 第 10 節） | 還原紀錄欄位、全部撤銷失敗的狀態碼、索引壞時全部撤銷與還原紀錄能不能用 | 還原紀錄欄位定了（契約 §3.6）；守門不看索引決定範圍，索引壞時照常撤銷並在紀錄寫 `index: corrupt`。路由的狀態碼與索引壞時的路由：HM-13c |
| HM-05 第 3 節 | 全部撤銷用執行套件的 `TokenAccess` 與 `mutation_lock` | 本片給 `revoke_all(stores=)`；拿鎖、`committed()`、重起子程式是 HM-13c 的路由 |

## 13. 交給後面的片

- **HM-13c**：
  - `POST profiles/revoke-all`：照索引隔離的寫法先依 id 順序拿每個已登錄帳號的鎖，呼叫 `restore_lock.revoke_all(store, product, stores=<已登錄的>)`；
    每個撤銷的帳號 `TokenAccess.committed()`、重起子程式（新 child token）；`finished=False` 時回 409 `operation_outcome_unknown`＋逐帳號
    `results`，失敗的帳號在 8081 回 503 直到重試成功（可用 `revoke_all_pending()` 加失敗名單）；收據「結果未知」。寫入失敗的 store 會中毒
    （`Store._write` 既有的規則：之後每次 `load()` 都 `ConfigError`），要重啟才恢復，重啟時守門會補完。
  - `restore-record` 讀 `restore_lock.read_record()`（上限 1 MiB）；核對卡、`reviewed_at` 的寫入、`token/rotate` 的 409 `restore_review_required`；
    bootstrap 的還原與休眠通知欄位名（含 HM-13a 過渡期留下的舊標記：開通後第一次開機也會有一筆沒有帳號資料的還原紀錄）。
  - 刪除隔離目錄的路由：名稱格式現在是 `<id>-<UTC>[-n]`（`parse_quarantine_name` 的第二組）。
  - `docs/operations/update-backup-rollback.md`：開通後的還原行為、涵蓋範圍、回退後按全部撤銷（本片只改了還原標記那一列）。
- **HM-16**：容器探針的多帳號階段：開通的候選映像還原後要看到還原紀錄、sentinel 重建、每個帳號都撤銷；`docker run` 180 秒上限。
- **HM-18**：DOCS 寫守門每一行 log 的意思與怎麼處理（`not finished (…)`：磁碟滿就清空間、其他原因還原別份備份）；偽造備份的項目被移開
  （`<名稱>.quarantine-<UTC>`）可以刪；`profiles` 不是目錄時要修好再重啟；還原紀錄超過 1 MiB（只有手工拼的備份）時守門停下；時鐘依賴；
  計畫 §7.2「預設帳號會變的事」補：開通的產品第一次開機多 sentinel 兩檔、還原後多 `restore-record.json`、有帳號資料時還原會撤銷預設帳號；
  各產品 CHANGELOG 的「還原標記」段落改成新行為（HM-13a 第 3.4 節的段落只適用 HM-13b 之前的版本）。
- **HM-19a**：首發前 HM-03a 的結果（第 11 節）是合併條件；builder 乾跑時容器探針的還原階段第一次真的跑（本片改了它的檢查）。
- **HM-25**：n8n 接 `ProfileManager` 時，守門已經在 `apps/n8n/run.py` 裡；帳號目錄裡的 n8n 檔案（`nodes.db` 在 `/tmp`，DQ-04）不在範圍。
- **HM-03a**：第 11 節的探針。

## 14. 驗收條件（計畫 §12.3 HM-13b）

| 條件 | 狀態 |
|---|---|
| §10.3 的守門測試全綠 | 本機：新 3 檔 81 案全過；全套只剩 7 個要 root 的既有案例（另一案是位元組釘選，`96c4d3b` 已修；第 5 節）；CI（root、0 skip）待 PR。§10.3 的每一項都有測試：全部撤銷、child token 重產、舊收據 410、孤兒撤銷、讀不到的 state 改名隔離且之後任何開機都不被路由、改名失敗保留標記、獨立驗證不過保留標記且不開 listener、DQ-03 兩種模式、開關關＋帳號資料＋標記全撤銷才刪標記、C1-M1 攻擊序、UC-24 三情境、全部撤銷第 k 個失敗、sentinel 不被任何 chmod／chown 碰到；另有每一步中途中斷、標記寫一半、磁碟滿 |
| sentinel 不被任何 chmod／chown 碰到 | 通過（第 3.9 節） |
| HM-03a 的 UC-08 與 sentinel 結果寫進 provenance | **待 HM-03a**（第 11 節）；合併前要補，不可靠就照 DQ-39 (a) |
| 獨立安全審查 | 還沒做 |
| 單帳號（開關關、沒有帳號資料）逐位元不變 | 通過：沒有還原時連 ctime 都不變（8 個產品）；有還原時只刪標記、一行 log；HM-01 黃金回歸與兩個契約凍結照過 |
| 同 PR 更新帳本；契約「待定」同步；第 9 節與變更紀錄 | 通過（第 2 節；契約 #101～#104 接在 #100 後面，第 10 節一列） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在執行時產生；憑證 `DUMMY-…`、網址 `.invalid`；秘密預檢 0 命中 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |

## 15. 已知 bug 的出現次數

`tests/test_backend_loopback.py::test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end[False]` 關閉時逾時
（HM-09 額外帳號監看沒照 cancel 停，另一條線在修）：0 次。全套跑了 1 次（`1f8c29f`），`[False]` 4.5 秒、`[True]` 2.3 秒都過；不拿鎖的反覆執行沒有跑這個檔（它起真子程式）。

## 16. 接續紀錄（2026-11-16 15:2x 之後）

上一段在 14:3x 因帳號的每週額度用完中斷：7 個 commit（`3c90b6c`～`0028169`）已在，本筆記是沒 commit 的草稿；全套 pytest 排隊後在 15:10
開跑、跑到約 18% 就斷了（它的 `/tmp/ha-mp-*` 已被主對話刪掉）。接續時：

- 讀懂已做的部分（commit、diff、草稿），先重跑新 3 檔（76 案全過），再對程式逐段審一次。
- 找到兩個缺陷，先寫測試看到紅、再修（第 4.1 節）：`cc5adb0`（補新檔那條路沒守時鐘下限）、`9c29b4f`（還原紀錄上限太小，會讓還原後永遠起不來）。
  帳本照實際內容重算、契約第 3.5、3.6 節與 `threat-model.md` 第 3 節跟著改。
- 補兩個記錄行為的測試：`360836e`（沒有額外帳號的產品，HM-07 審查 S-06）、`5b596cd`（store 回報失敗時標記留著）。
- 草稿的數字逐一核對：64 個改磁碟的呼叫（重算）、17 個呼叫點（測試的清單）、新 3 檔各階段的案數（每個 commit 匯出後收集：74、75、76、81）、
  先紅後綠的四列（重建）、突變（在最終程式上重跑）、PaaS 變動（重查）、packaging unittest、`validate.py`、`tool_inventory.py`、兩個預檢、全套。
  上一段草稿裡「替身沒跟上時 58 案失敗」對不上重建的結果（用替身的 18 檔裡 128 案），改成重建的數字；其他照實寫。
- 全套 pytest（`1f8c29f`，正式 conftest、排在 wave1 鎖後面）抓到 `tests/test_output_schemas.py` 對 `apps/n8n/run.py` 的位元組釘選沒跟上
  `e91fc6f`（CI 一定紅）：`96c4d3b` 修好。契約第 7 節 log 清單漏的 `INDEX_NOT_ARCHIVED` 那一行在 `7d237f6` 補上。
- Chromium 照 CI 的 `npm run browser:install` 裝進 clone 的 `node_modules`（只動被忽略的檔），全套的瀏覽器案例才跑得起來。
