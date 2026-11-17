# HA 多帳號 HM-13b provenance：開機守門（撤銷、隔離、獨立驗證、休眠處理、全部撤銷標記；不受開關管）（2026-11-16）

## 結論

- **和 `claude-delivery` `165dbaf` 合併（2026-11-17 07:5x；第 19 節）。** HM-12 後端（PR #110）、HM-30（#111）、HM-32（#113）、HM-12 面板（#114）先合併，本 PR 和主線有衝突、GitHub 不替它跑 CI。照 PR #106 的前例用 merge commit 合進來（`6bb7fcd`），不 rebase、不 force push。
  衝突在 8 個檔：程式、測試與文件 7 個檔 19 塊，帳本 4 塊另照 JSON 重組。程式都是「同一個地方各加一個選項」，HM-12 的 `stop_child`、HM-30 的 `reply_worker` 和本片的
  `dormant_profiles` 並存，`run_product` 留 HM-30 的 `worker = None`、判斷用本片這次開機讀到的 `enabled`。契約第 9 節本片的列改成 #118～#121
  （`0ea1c37`）。本機：pytest 子集 39 檔 1,848 案只有 5 個要 root 的失敗；node、build closure、packaging、`validate.py`、`tool_inventory.py`、
  兩個預檢都過，雙向控制字元 0 個。
- **rebase 到 `claude-delivery` `f4c7718`（2026-11-16 21:4x；第 18 節）。** 22 個 commit 照原順序重放；衝突在 5 個 commit、6 個檔，兩邊的行為都留
  （HM-31 的 `body_budget` 和本片的 `dormant_profiles` 在 `make_apps`、`ProfileRuntime` 並存）。契約第 9 節本片的列改成 #113～#116，引用一起改。
  帳本照 rebase 後的實際內容重算，每個重放的 commit 都 0 漂移。本機子集另外抓到 HM-31 一案釘住 `make_apps` 的參數順序，改測試（`ebcb771`）。
  rebase 後本機：pytest 子集 900 案 895 過（5 個要 root 的失敗）、全套 6,090 案 6,083 過（7 個要 root 的既有案例失敗，0 skip）；
  packaging `Ran 205`、`validate.py` PASS、`tool_inventory.py` exit 0。兩個預檢 OK、雙向控制字元 0 個。
- **獨立安全審查（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13b.md`）：修正後通過；本輪處理完（第 17 節）。**
  - MF-1：新測試的固定時鐘寫死 2026-11-16T09:30:15Z，今天 09:30Z 以後 CI 一定紅。改成每案取「現在的下一個整秒」（`aa8ef57`，只改測試）。
  - MF-2：`profiles/` 一時列不出來（EMFILE、EIO、ENOMEM、權限）時，守門與全部撤銷都當成「沒有額外帳號」（fail open）。改成停下：
    標記留著、什麼都不服務、下次開機重做；全部撤銷照樣撤銷呼叫端拿著的 store、`finished=false`（`f3b8fa1`）。只有 `profiles` 確定不是
    目錄才照 #119 照常啟動。
  - 建議 8 項：S-1、S-2、S-5、S-6、S-7、S-8 採用；S-3 部分採用（開通的候選映像要有還原檔；stderr 兩行交 HM-16）；S-4 寫進文件、
    分辨暫時性錯誤交 HM-18／HM-13c。Q-1（沒開通的產品只有 log 提示）：使用者 2026-11-16 定案照 DQ-03 (b) 原文，
    單帳號還原後也要有面板提示，交 HM-13c 做，本片不改（第 18.12 節）。
  - 這一輪在 19:4x 也因額度中斷過一次（修正的 5 個 commit 已在，全套跑到約 80% 就斷）。20:3x 接續：核對 commit 與草稿、刪掉留下的
    `/tmp/ha-mp-*`、全套重跑、威脅模型 I9／I13 的測試欄補上審查的新案（`27eeb16`）、預檢重跑（第 17 節）。
- **新模組 `restore_lock.py`：開機守門。** `run_product` 與 `apps/n8n/run.py` 每次開機在 legacy 遷移與預設帳號的 store 之後、任何子程式與
  listener 之前跑 `restore_lock.guard`。沒做完一律 `ConfigError`：什麼都不服務（`runtime unavailable`）、標記都保留，下次開機重跑。
  不受產品開關管：任何產品下一次發版都會帶出去。
- **今天的安裝（沒開通、沒有帳號資料）逐位元不變。** 沒有還原時只多查四個名稱，什麼都不寫、不記 log（連 ctime 都不變，9 個產品各一案：審查 S-8 加了 Odoo Manage）。
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
  31 個被抓到，1 個等價（第 4.2 節）。審查後的修正也先紅後綠：新案在 `551d210` 的程式上 11 案紅、修好後全綠；13 個突變全部被擋
  （第 4.1、4.2 節）。
- 本機（審查修正後，第 5 節）：新 3 檔 97 案全過（約 9 秒）；全套 pytest（`89a7e02`，之後只改文件）5,885 案、0 skip、32 分 32 秒：
  只有 7 個要 root 的既有案例失敗；packaging unittest `Ran 205`、`OK (skipped=5)`；`validate.py` PASS；`scripts/tool_inventory.py` 通過。
  已知會偶發逾時的 `test_backend_loopback` 那案：0 次（這次全套 4.5 秒通過）。
- 兩個預檢（最終 HEAD、基準 `684a2dd`）：秘密預檢 0 命中；帳本預檢 OK（第 8 節）。
- rebase 後由這條線 push、開 PR，不合併。獨立安全審查做過了（第 17 節）；合併前還要 HM-03a 的結果（第 11 節，DQ-39 (a)），
  HM-03a 也要量守門沒做完時 Supervisor 會不會用 Watchdog 自動再起。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-13b（計畫 §8.4「開機守門」、休眠處理、全部撤銷；§10.3；§12.3；風險高、工作量 L） |
| 分支 | `feat/ha-multiprofile-hm13b-20261116`（一般 clone，不是 worktree） |
| HA 基準 | **2026-11-17 起：合併 `claude-delivery` `165dbaf`**（merge commit `6bb7fcd`，第一個 parent 是本片 `ebab019`、第二個是 `165dbaf`；第 19 節）。合併前：**rebase 後：`claude-delivery` `f4c7718`**（2026-11-16 21:4x；第 18 節）。rebase 前：`684a2dd`：HM-10 的 PR #104 head（`claude-delivery` `7c6f80c` 加 HM-10 的 18 個 commit）。HM-10 先合併；之後由主對話 rebase 到 `claude-delivery`。2026-11-16 19:0x 查（只 fetch `claude-delivery`）：已是 `df686dd`（合了 #104 HM-10、#105 HM-31、#106 HM-09 監看 cancel 修正）；`git merge-tree` 預估 rebase 時要解 6 個檔：`contract.md`、`ledger-tracking.md`、`threat-model.md`、`runtime-patches.json`、`gateway.py`、`profile_runtime.py`。20:4x 再查：已是 `f4c7718`（再合了 #107 HM-11），要解的仍是這 6 個檔 |
| 本片 commit | 22 個：接續前 7 個（`3c90b6c`～`0028169`）；接續後 8 個（`cc5adb0`、`9c29b4f`、`360836e`、`5b596cd`、`7d237f6`、本筆記 `1f8c29f`、`96c4d3b`、`551d210`；第 16 節）；審查修正 7 個（`aa8ef57`、`77394fc`、`f3b8fa1`、`895119b`、`89a7e02`、`27eeb16`，以及記錄審查處理的這個筆記 commit；第 17 節）。rebase 後：這 22 個重放（新的 commit 編號見第 18.11 節），再加 4 個（`7a85928` 改列號、`ebcb771` HM-31 測試的參數順序、`df63d79` 筆記改列號、本筆記第 18 節），共 26 個。2026-11-17 合併 `claude-delivery` 後再加 3 個（merge commit `6bb7fcd`、`0ea1c37` 改列號、本筆記的現行列號與第 19 節），共 29 個（含 1 個 merge commit；第 19.11 節） |
| 依據 | 計畫 §3.3、§4.1、§8.4、§8.8、§8.10、§10.3、§12.3 HM-13a／b／c；契約 §1.2、§3.5、§3.6、§4.1、§7、§8、§9；`threat-model.md`；HM-13a 的筆記與審查（`wave1/review-HM-13a.md`）；FM-04、07、13、16、78、79、80、118、119、120 |
| PaaS | 沒有搬程式。對照 `Pc/restore_guard.py`（`prepare`、`_write_config`、`_write_journal`、`_archive_journal`、`_read_journal_floor`）、`Pc/restore_inplace.py`（`_verify`）、`Pc/restore_marker.py`（任何項目都算存在）；pin `69ac425`，到 `d7f5849` 這幾檔沒變（第 9 節） |
| 決策 | DQ-03 (b)、DQ-39 (a)、DQ-13、DQ-14、DQ-21、DQ-40 (a)（第 10 節）；沒有碰到待定題 |
| 安全審查 | 做了：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13b.md`（判定「修正後通過」；證據 `wave4/evidence-review-HM-13b/`）；處理見第 17 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/restore_lock.py`（新） | `guard()`、`revoke_all()`、`mark_revoke_all()`、`revoke_all_pending()`、`read_record()`、`read_tokens()`、`facts()`；log 文字常數；`DEFAULT_REVOKED_WHEN_SWITCHED_ON`（DQ-03 的 (a)／(b)，現在 `False`＝(b)）；`RECORD_LIMIT` 1 MiB。審查後：`profiles/` 列不出來時停（MF-2）；`revoke_all()` 撤銷呼叫端的每個 store、E 一定跑、`stores` 只收額外帳號；還原紀錄與收據封存的名稱上的目錄移開（S-1）；log 多 `SET_ASIDE_IN_PROFILE` 一行 |
| `operations.py` | 收據檔可多 `restored_before_ms`（其他值讓收據檔 503）；`_load` 在 24 小時保留期之前先判 410 `operation_restored`；`archive_for_restore()`、`journal_path()` |
| `profiles.py` | `free_quarantine_name()`、`free_aside_name()`（不覆蓋、同一秒加 `-2`…）；隔離名的正規式收 `-n`。審查後：`RECEIPT_ARCHIVE_NAMES`、`ASIDE_NAMES`（`free_aside_name` 多收還原紀錄與兩種收據封存的名稱，S-1） |
| `run_product.py` | 開關每次開機只讀一次；守門在 `ProfileManager`／單帳號 runtime 之前；休眠數給 bootstrap |
| `apps/n8n/run.py` | 同上（n8n 到 HM-25 才有帳號；守門只會刪還原標記或補完全部撤銷） |
| `gateway.py` | `make_apps(dormant_profiles=n)`：bootstrap 多 `dormant_profiles`；沒給時逐位元同今天；和 `profile_view` 不能同時給 |
| `profile_runtime.py` | `ProfileRuntime(dormant_profiles=…)` 轉給 `make_apps`；模組說明 |
| `packaging/container_probe.py` | 容器驗收還原階段的檢查：標記已被守門刪掉、沒開通的產品沒有 sentinel／record／還原紀錄、還原項目都修好、state 位元不變。審查後：開通的候選映像三個還原檔都要在（10001 的單一連結一般檔、0600；S-3） |
| `docs/provenance/runtime-patches.json` | 新增 `restore_lock.py`；6 個改到的列管檔重算摘要並補說明；`restore_detect.py`、`identity_fields.py` 只補「已接線」的說明 |
| 測試（新） | `tests/restore_guard_disk.py`、`tests/test_restore_lock.py`（71 案）、`tests/test_dormant_profiles.py`（8）、`tests/test_revoke_all.py`（18）；審查前是 59、7、15 |
| 測試（改） | 見第 3.10 節（含 `tests/test_output_schemas.py` 的一筆釘選） |
| 文件 | 契約（第 1.1、1.2、1.3（新）、3.5、3.6、7、8、9、10 節）、`threat-model.md`（I9、I13、第 3 節；審查後的改動見第 17 節）、`acceptance-matrix.md`（T-21）、`ledger-tracking.md`（`profiles.py` 那列）、`docs/operations/update-backup-rollback.md`（還原標記那列）、`docs/operations/acceptance.md`（容器驗收還原階段） |

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
| A 快照 | 預設帳號從 store 讀；每個目錄的 `state.json` 用 `read_tokens` 原始讀（不拿鎖、不 chmod），讀得到的 token 與 child token 放進記憶體 | 預設帳號讀不到：`ConfigError`。`profiles` 是目錄（或查不出是什麼）卻列不出來：記成失敗，B 照做後停（審查 MF-2）；`profiles` 確定不是目錄：記一行、繼續（#119） |
| B 預設帳號 | 有帳號資料（或有全部撤銷標記）時：`change_token(None,'revoke')`、新的 child token（不和快照裡任何值相同）、封存收據。沒有帳號資料：原樣不動 | 記一行、繼續撤銷其他帳號，最後停 |
| C 帳號目錄 | `existing_only` 開得了：撤銷、新的 child token、封存收據。開不了（任何原因）：改名 `profiles/.quarantine-<id>-<UTC>[-n]`、fsync `profiles/`；writer lock 被別人拿著的只算失敗、不搬。最後封存索引旁的收據 | 同上 |
| D 紀錄 | `restore-record.json`（第 3.6 節） | 停 |
| E 獨立驗證 | 從磁碟重讀每個目錄（不經寫入的 store）：被撤銷的 token 是 None；新的 child token 和快照不同、也不在快照裡；現在的任何 token、child token 都不在快照裡（預設帳號沒被撤銷時排除它自己的兩個值，而且它要和快照一模一樣）；帳號目錄＝快照的減掉隔離的；每個隔離目錄都還是隔離目錄 | 停（不開 listener） |
| F 收尾 | 守門自己的名稱若被目錄占用先移開；`restore_detect.rebuild()`；刪 `.revoke-all-pending`；最後刪還原標記；fsync 目錄 | 停 |

「停」＝ log `UNFINISHED`（括號裡是固定的原因）、`ConfigError`、標記都保留。每一步都冪等：token 已是 None 時不再多一筆歷史；child token 每次重做都
再換；沒有收據的收據檔不再封存；紀錄重寫。所以停在任何地方，下次開機都看得到還原（標記還在，或 sentinel 還沒重建），再做一次就好
（第 4.2 節、`test_a_start_stopped_anywhere_is_finished_by_the_next`）。

為什麼 E 比對的是這次的快照、不是備份本身（契約 #118）：Supervisor 還原不留備份副本。中途斷電後重做時，上一次已換掉的值已不在磁碟上；
備份裡還留在磁碟上的值一定在這次的快照裡，所以「現在任何值都不在快照裡」仍然證明備份裡能認證的東西現在都不能認證。

### 3.3 收據（FM-07；契約 §3.5、#67、#121）

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
- `profiles/` 列不出來時（審查 MF-2）：照樣撤銷預設帳號與 `stores` 裡的每個帳號（results 逐一列出），但 `finished=False`、標記留著，
  下次開機補完（列不到的目錄裡可能有還有效的 token，例如孤兒）。E 不管前面有沒有失敗都跑：store 說撤銷了、磁碟沒變的也算 `failed`
  （HM-13c 據此在 8081 回 503）。`stores` 只收額外帳號的 id，其他 `ValueError`、什麼都不做。
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

### 3.7 守門自己的名稱（HM-13a 審查 SF-7；契約 #120）

sentinel、record、record 暫存檔、還原標記、全部撤銷標記的名稱若是目錄（偽造的備份；修復接受目錄），改名放到 `<名稱>.quarantine-<UTC>[-n]`，
從不刪。不處理的話 `rebuild()` 每次失敗、add-on 再也起不來。審查 S-1 後，`restore-record.json` 與收據封存（`.state.json.operations.json.restored`、
`.profiles.json.operations.json.restored`）的名稱也一樣（`profiles.ASIDE_NAMES`；帳號目錄裡的那一行帶 `[profile=<id 前 8 碼>]`）。

`profiles` 確定不是目錄（一般檔、連結）時記一行、照撤銷預設帳號後啟動（契約 #119；裡面什麼都不會被開或路由，開通後 HM-08 對每個 token
回 503）。`profiles` 是目錄、或查不出是什麼，卻一時列不出來時，守門停下（審查 MF-2；同 PaaS）。

仍會讓守門每次開機都停下的偽造備份（`threat-model.md` 第 3 節）：還原紀錄超過 1 MiB；收據檔本身是目錄、旁邊已有封存檔（目錄改不了名
到檔案上）。後者審查沒提，本輪用實驗確認後寫進文件、不另外處理（要 HA 管理員上傳偽造備份；脫困是還原別份備份）。

### 3.8 開機順序與 fail closed

- `run_product.run`：legacy 遷移 → 預設帳號的 store → **守門** → `ProfileManager`（開通）或單帳號 `ProfileRuntime` → listener → 子程式。
  測試記錄事件順序：守門結束前沒有任何 Supervisor、子程式或 listener（開關開與關、n8n 各一次）。
- 守門沒做完：`run()` 丟 `ConfigError`，`main()` 印 `runtime unavailable; local recovery required`；沒有任何 listener 或 Supervisor 被建立
  （`test_a_guard_that_does_not_finish_serves_nothing`）。下次啟動時守門重跑：使用者重新啟動、主機重開，或 HA 介面的 Watchdog 開著時
  Supervisor 自動再起。`addons/*/config.yaml` 沒有 `watchdog` 鍵，會不會自動再起沒確認（`research/R08-ha-arch.md:122`；第 11 節；審查 S-6）。

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
| 審查 MF-1（`aa8ef57`） | 舊測試檔在 `551d210` 的程式上 10:45Z 跑：`test_a_restore_with_profile_data_revokes_every_profile` 兩案紅（`assert 'new' == (410, 'operation_restored')`）；只換時鐘後 81 案全過 |
| 審查的新案（`77394fc`，程式仍是 `551d210`） | 11 案紅：MF-2 守門 3 案 `DID NOT RAISE ConfigError`（守門照樣做完）、全部撤銷 1 案 `finished=True`、E 一定跑 1 案（說謊的撤銷算 `revoked`）、`stores` 驗證 1 案；S-1 4 案 `ConfigError: restore guard unfinished`（每次開機都停）；名稱常數 1 案 `AttributeError` |
| 審查修正（`f3b8fa1`） | 新 3 檔 97 案全過 |

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

審查後（`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-13b/scripts/mutate.py`：`551d210` 匯出加上修正後的檔，一次改一處，只跑新 3 檔、不拿鎖；基準 N00 0 個失敗；結果在同目錄 `mutations/mutations.json`）：

| 突變 | 結果 |
|---|---|
| N01 E 拿掉「每個帳號目錄、每個撤銷的 token 是 None」（審查 R21） | 被擋（休眠時說謊的撤銷那案） |
| N02 E 不比保留的預設帳號（R22） | 被擋（檢查前被改的預設帳號那案） |
| N03 E 不要求隔離目錄還是隔離目錄（R23） | 被擋（檢查前不見的隔離目錄那案） |
| N04 列不出來的 `profiles` 目錄不算失敗（審查前的程式） | 被擋（3 案） |
| N05 查不出 `profiles` 是什麼時當成「不是目錄」 | 被擋 |
| N06 `revoke_all` 不看原因就算做完 | 被擋 |
| N07 `revoke_all` 只撤銷掃到的、不撤銷給的 store | 被擋 |
| N08 `revoke_all` 只在沒有失敗時跑 E | 被擋 |
| N09 E 不讀沒列到的 store | 被擋 |
| N10 不清還原紀錄的名稱 | 被擋 |
| N11 不清收據封存的名稱 | 被擋（2 案） |
| N12 清名稱時直接刪掉 | 被擋（2 案） |
| N13 `stores` 收任何 id | 被擋 |

## 5. 本機檢查（2026-11-16，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

本節是 rebase 前的結果；rebase 到 `claude-delivery` `f4c7718` 之後重跑的在第 18.7 節。

開發中的反覆執行用 `--noconftest` 加一個裝同樣網路與子程序守門、只是不拿全機測試鎖的外掛（同 HM-13a 的做法；只跑不開固定 port、不起真子程式
的檔）。全套用正式的 `tests/conftest.py`，排在 wave1 鎖後面。

| 檢查 | 結果 |
|---|---|
| **審查修正後**：新 3 檔（`test_restore_lock.py` 71、`test_dormant_profiles.py` 8、`test_revoke_all.py` 18；`f3b8fa1`） | 97 案全過，9.0 秒（最慢的是中途停下那案 4.4 秒） |
| **審查修正後**：影響到的 18 檔（不拿鎖；新 3 檔、`test_restore_detection`、`test_upgrade_zero_rewrite`、`test_router_passthrough`、黃金回歸、`test_profile_admin_api`、`test_tool_inventory`、`test_ledger_precheck`、`test_output_schemas`、`test_profile_routing`、`test_profile_store`、`test_log_scan`、兩個契約凍結、`test_admin_pipeline_matrix`、`test_profile_index`） | 845 案：839 過；6 個失敗都是要 root 的（`test_restore_detection.py` 的 5 案 `test_root_*`、`test_profile_store.py` 的 1 案），46.9 秒 |
| **審查修正後**：新 3 檔（正式 conftest、第二次接續時；`89a7e02`） | 97 案全過，9.0 秒 |
| **審查修正後**：全套 pytest（正式 conftest、wave1 鎖；`89a7e02`，之後只改文件；Chromium 用 clone 裡已裝的） | 5,885 案（審查前 5,869 加新的 16 案）、0 skip、1,952.1 秒（32 分 32 秒）：5,878 過；7 個失敗都是要 root 的既有案例（第 6 節），沒有別的失敗。新 3 檔 97 案（junit 7.6 秒）、`test_restore_detection` 139、`test_upgrade_zero_rewrite` 45、黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19、`test_router_passthrough` 49、`test_output_schemas` 189 案都過 |
| **審查修正後**：packaging unittest（同 CI 的離線暫存 venv）、`validate.py`、`scripts/tool_inventory.py`（`27eeb16`；程式同 `89a7e02`） | `Ran 205`、`OK (skipped=5)`（多的 1 案是 S-3）；PASS；通過（tool-surface 不用重產） |
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
- 審查修正後（全套的 junit，`89a7e02`）：新 3 檔 7.6 秒（`test_restore_lock` 71 案 6.6 秒、`test_dormant_profiles` 8 案 0.5 秒、
  `test_revoke_all` 18 案 0.5 秒；多 16 案，都在程序內、不起真子程式）；CI 推估本片合計多 20～30 秒。

## 7. `checks` 秒數

開 PR 後補（前、後兩個 run 的 `checks` 秒數）。

## 8. 預檢結果

本節是 rebase 前的結果；rebase 後（base `origin/claude-delivery`）的在第 18.8 節。

在本筆記的 commit 之後、以最終的 HEAD 跑（基準 `684a2dd`）：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <scratchpad>/hm01/gitleaks-tools --repo . --base 684a2dd --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 684a2dd
```

- 秘密預檢：gitleaks 8.28.0（釘選、已核對）；本片 22 個 commit（`684a2dd..HEAD`，審查修正後）、`--full` 的 HEAD 全部檔與全歷史：0 命中
  （本筆記 commit 前在 `27eeb16` 先跑一次：21 個 commit、0 命中）。
  測試的 token 都在執行時產生；憑證用 `DUMMY-…`、網址 `.invalid`（照 `tests/fixtures/owner_defaults/README.md`）。
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
- 審查後補查：本機 PaaS 的 `origin/main` 已被別的工作 fetch 到 `7087280`（本線沒有 fetch）。`d7f5849..7087280` 是 Hermes cron、LiteLLM 與 EMQX
  不保留閒置連線三個修正，還原相關檔 0 變動，上面的結論不變。PaaS 收據下限 `max(cutoff_ms, journal_floors[...])` 沒有上限
  （`Pc/restore_guard.py:513-516`，pin `69ac425`）；HA 的 24 小時上限記在契約 #67（審查 S-6）。

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
| HAOS 開機時主機時鐘不會比備份裡的收據慢超過 24 小時（審查 S-6） | 是（有 NTP） | 備份裡較新的操作 id 在時鐘校正後可能被當成新操作（`threat-model.md` 第 3 節） |
| add-on 以非零結束（守門沒做完）後，Supervisor 會不會自動再起：Watchdog 開關與它的預設值（審查 S-6、7.8） | 不假設 | 不會自動再起時，要使用者重新啟動或主機重開才會重做守門；HM-18 的 DOCS 要寫 |

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
| HM-13a 審查 SF-7 | sentinel 或 `.instance-record.tmp` 被目錄占用時 `rebuild()` 一直失敗 | 做了：移開到 `<名稱>.quarantine-<UTC>[-n]`，兩個標記也一樣（第 3.7 節）；審查 S-1 後還原紀錄與收據封存的名稱也一樣；契約布局補 `.instance-record.tmp`（原本交 HM-18，本片動到第 8 節就一起補） |
| HM-13a 審查 SF-10 | 沒開通、沒有帳號資料時不能呼叫 `rebuild()`（會多兩個檔） | 守門只在 `detection.active` 時重建；單帳號還原的 9 案（審查前 8 案）確認不多 sentinel、record 或還原紀錄 |
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
  - 審查 Q-1 的使用者定案（2026-11-16）：照 DQ-03 (b) 原文，沒開通的單帳號安裝還原後也要有面板提示，由 HM-13c 做（第 18.12 節；
    計畫 §12.3 HM-13c 已加註）。本片的守門在這種情況只記一行 WARNING、刪標記、不寫紀錄；HM-13c 要接在守門上另留一筆提示紀錄。
  - 本輪看到、審查沒提（沒改，請 HM-13c 定）：備份時某個帳號還沒有自己的收據檔（從沒輪替、撤銷或重啟過），備份後才做的操作 id 隨還原消失，
    守門照契約 §3.5「兩個都沒有就不寫」不寫新收據檔，之後重送那個 id 會被當成新操作、不是 410。核對關卡（`restore_review_required`）在核對前
    擋住重發；要不要對範圍 S 的每個帳號都寫新收據檔（同 PaaS「每份設定都換新收據檔」），和核對流程一起定。
  - 審查 S-5：`revoke_all()` 要在 `ProfileAdmin.lock`（建立、刪除、索引隔離都拿的 add-on 帳號鎖）裡呼叫，不只拿各已登錄帳號的鎖；建立做到
    一半（只有目錄）時呼叫，那個目錄會被當成讀不到而隔離（審查 X11）。它是同步的、每帳號兩次 state 寫入加 fsync，要用 `asyncio.to_thread`
    之類在執行緒裡跑，不卡 8081、8099 與健康檢查（HM-30 的公平排程）。results 已列出 `stores` 的每個帳號；`finished=False` 的回應與
    8081 的 503 名單照 results。
  - `POST profiles/revoke-all`：照索引隔離的寫法先依 id 順序拿每個已登錄帳號的鎖，呼叫 `restore_lock.revoke_all(store, product, stores=<已登錄的>)`；
    每個撤銷的帳號 `TokenAccess.committed()`、重起子程式（新 child token）；`finished=False` 時回 409 `operation_outcome_unknown`＋逐帳號
    `results`，失敗的帳號在 8081 回 503 直到重試成功（可用 `revoke_all_pending()` 加失敗名單）；收據「結果未知」。寫入失敗的 store 會中毒
    （`Store._write` 既有的規則：之後每次 `load()` 都 `ConfigError`），要重啟才恢復，重啟時守門會補完。
  - `restore-record` 讀 `restore_lock.read_record()`（上限 1 MiB）；核對卡、`reviewed_at` 的寫入、`token/rotate` 的 409 `restore_review_required`；
    bootstrap 的還原與休眠通知欄位名（含 HM-13a 過渡期留下的舊標記：開通後第一次開機也會有一筆沒有帳號資料的還原紀錄）。
  - 刪除隔離目錄的路由：名稱格式現在是 `<id>-<UTC>[-n]`（`parse_quarantine_name` 的第二組）。
  - `docs/operations/update-backup-rollback.md`：開通後的還原行為、涵蓋範圍、回退後按全部撤銷（本片只改了還原標記那一列）。
- **HM-16**：容器探針的多帳號階段：開通的候選映像還原後要看到還原紀錄、sentinel 重建、每個帳號都撤銷；`docker run` 180 秒上限。
  審查 S-3 交下（要在 HM-19a 前的 builder 乾跑之前做好）：還原階段的 `start()` 把 stdout、stderr 丟到 DEVNULL，分不出「守門刪了標記」與
  「entrypoint 根本沒建標記」。要把還原階段的 stderr 收下來，斷言 entrypoint 的 `bootstrap: re-owned N restored entries in /data/mcp`
  （N＝還原項目＋標記）與守門的 `KEPT_NOTICE`（沒開通）或 `REVOKED_NOTICE`（有帳號資料）各一行。本片只補了開通時三個還原檔的檢查。
- **HM-18**（審查 S-4、S-6 交下）：還原時開帳號目錄遇到暫時性錯誤（EMFILE、EIO…）也會把好的帳號改名隔離、之後只能刪；DOCS 寫「同一份備份再還原
  一次就會重做」。要不要讓 `Store` 帶出原因、暫時性錯誤改成「這次開機停下、下次重做」，和 HM-13c 一起定（動到 `config.py`）。
  DOCS 也寫：守門沒做完時 add-on 會不會自己再起看 Watchdog 開關；`profiles` 列不出來時（`not finished (the profiles directory cannot be
  listed)`）要修好磁碟或權限再重啟。
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
| §10.3 的守門測試全綠 | 合併 `claude-delivery` `165dbaf` 後（第 19.7 節）：子集 39 檔 1,848 案、0 skip，只剩 5 個要 root 的 `test_root_*`（新 3 檔 97 案全過）。本機（rebase 後，第 18.7 節）：新 3 檔 97 案全過；子集 900 案只剩 5 個要 root 的 `test_root_*`；全套 6,090 案、0 skip，只剩 7 個要 root 的既有案例（rebase 前：新 3 檔 97 案全過；全套 5,885 案只剩 7 個要 root 的既有案例，第 5 節）；CI（root、0 skip）待 PR。§10.3 的每一項都有測試：全部撤銷、child token 重產、舊收據 410、孤兒撤銷、讀不到的 state 改名隔離且之後任何開機都不被路由、改名失敗保留標記、獨立驗證不過保留標記且不開 listener、DQ-03 兩種模式、開關關＋帳號資料＋標記全撤銷才刪標記、C1-M1 攻擊序、UC-24 三情境、全部撤銷第 k 個失敗、sentinel 不被任何 chmod／chown 碰到；另有每一步中途中斷、標記寫一半、磁碟滿 |
| sentinel 不被任何 chmod／chown 碰到 | 通過（第 3.9 節） |
| HM-03a 的 UC-08 與 sentinel 結果寫進 provenance | **待 HM-03a**（第 11 節）；合併前要補，不可靠就照 DQ-39 (a) |
| 獨立安全審查 | 做了：判定「修正後通過」；2 必修修好、建議逐項處理（第 17 節）；Q-1 使用者已定案，交 HM-13c（第 18.12 節） |
| 單帳號（開關關、沒有帳號資料）逐位元不變 | 通過：沒有還原時連 ctime 都不變（9 個產品，審查 S-8 加了 Odoo Manage）；有還原時只刪標記、一行 log；HM-01 黃金回歸與兩個契約凍結照過 |
| 同 PR 更新帳本；契約「待定」同步；第 9 節與變更紀錄 | 通過（第 2 節；契約 #118～#121 接在 #117 後面（第一次 rebase 前是 #101～#104、接在 #100 後面；合併 `claude-delivery` `165dbaf` 前是 #113～#116、接在 #112 後面），第 10 節四列） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在執行時產生；憑證 `DUMMY-…`、網址 `.invalid`；秘密預檢 0 命中 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |

## 15. 已知 bug 的出現次數

`tests/test_backend_loopback.py::test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end[False]` 關閉時逾時
（HM-09 額外帳號監看沒照 cancel 停，另一條線在修）：0 次。全套跑了 1 次（`1f8c29f`），`[False]` 4.5 秒、`[True]` 2.3 秒都過；不拿鎖的反覆執行沒有跑這個檔（它起真子程式）。
審查修正後的全套（`89a7e02`）：`[False]` 4.5 秒、`[True]` 2.3 秒都過，逾時 0 次。本片的全套共跑 2 次（`1f8c29f`、`89a7e02`），審查另跑 2 次，
都沒有逾時。

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

## 17. 獨立安全審查的處理（2026-11-16 18:3x 起）

審查報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13b.md`（審查對象 `551d210`；證據 `wave4/evidence-review-HM-13b/`）。
本輪的腳本與 log（先紅後綠、突變、影響到的檔、packaging、全套）：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-13b/`
（log 先遮掉像 token 的字串，掃描 0 命中）。
判定「修正後通過」：必修 2 項、建議 8 項、請主對話確認 1 題。先核對每一項（審查實驗的情境在本線重寫成測試或實驗重現），再改。

| # | 意見（摘要） | 處理 | commit | 測試／證據 |
|---|---|---|---|---|
| MF-1 | 新測試的固定時鐘寫死 09:30:15Z，CI 一定紅 | 修：`guard_clock()` 每案取「現在的下一個整秒」，紀錄的 `at`、隔離名稱、時間戳由它推；既有隔離目錄名用固定的過去日期（只是名稱） | `aa8ef57` | `551d210` 上 10:45Z 跑 2 紅 → 81 綠（第 4.1 節） |
| MF-2 | `profiles/` 一時列不出來時 fail open（全部撤銷回成功、還原讓舊 token 復活） | 修：照審查的草稿判斷「是目錄或查不出」，再多做三件：給的 `stores` 都撤銷並列進 results（不只算失敗）、E 不管前面有沒有失敗都跑、E 直接讀沒列到的 store；`stores` 只收額外帳號 | `77394fc`（測試）、`f3b8fa1`、`27eeb16` | 守門 3 案（還原、休眠、查不出是什麼）、全部撤銷 3 案；突變 N04～N09、N13 都被擋；契約 #119、第 1.3 節、`threat-model.md` 第 3 節與 I9、I13 的測試欄 |
| S-1 | 偽造備份的 `restore-record.json`、收據封存是目錄時每次開機都停 | 採用：寫紀錄、封存前把目錄移開到 `<名稱>.quarantine-<UTC>[-n]`（`profiles.ASIDE_NAMES`） | `77394fc`、`f3b8fa1` | 4 個名稱各一案＋名稱常數一案；N10～N12。實驗另確認「收據檔本身是目錄、旁邊已有封存檔」仍會停：寫進 `threat-model.md` 第 3 節，不另外處理 |
| S-2 | 第 E 步三個防禦檢查沒有測試（R21～R23 存活） | 採用：休眠時說謊的撤銷、檢查前被改的保留預設帳號、檢查前不見的隔離目錄各一案 | `77394fc`、`27eeb16`（威脅模型 I13 的測試欄） | N01～N03 都被擋 |
| S-3 | 容器探針還原階段證據變弱 | 部分採用：開通的候選映像三個還原檔都要在、10001、0600（docstring 說了卻沒檢查）。stderr 兩行要改 `start()` 的輸出處理、只能在真映像上驗：交 HM-16（第 13 節），HM-19a 前的 builder 乾跑之前做好 | `895119b` | packaging unittest `Ran 205`、`OK (skipped=5)` |
| S-4 | 暫時性錯誤讓好的帳號被永久隔離 | 不改程式：計畫 §8.4 C 寫「任何原因」；分辨原因要讓 `Store` 帶出例外原因（`config.py`，所有產品共用）；結果是安全方向（隔離的永遠不服務），同一份備份再還原一次就會重做。寫進 `threat-model.md` 第 3 節，交 HM-18／HM-13c | `89a7e02` | — |
| S-5 | 交 HM-13c 要補拿 `ProfileAdmin.lock`、在執行緒裡跑、results 列出每個 store | 採用：`revoke_all()` 的 docstring、契約第 1.3 節、本筆記第 13 節 | `f3b8fa1`、`89a7e02`、本 commit | results 列出 store：MF-2 的全部撤銷那案 |
| S-6 | 契約、威脅模型與筆記的小落差 | 採用：#67 補 24 小時上限（PaaS 沒有上限）；第 3.5 節「時鐘慢」限 24 小時；`threat-model.md` 補「慢超過 24 小時」；第 3.8 節改成「下次啟動（使用者、主機重開或 Watchdog）」並加進第 11 節；`update-backup-rollback.md` 那列改字；第 9 節補 `7087280` | `89a7e02`、本 commit | PaaS 唯讀查：`git -C <paas> show 69ac425:…/restore_guard.py`、`log d7f5849..origin/main` |
| S-7 | `96c4d3b` 之後沒重跑全套 | 採用：修正後重跑全套（第 5 節） | — | `89a7e02`：5,885 案、0 skip，只有 7 個要 root 的既有案例失敗 |
| S-8 | 單帳號「什麼都不變」的測試沒涵蓋 Odoo Manage | 採用：兩案參數改成 9 個產品（`EVERY_PRODUCT`） | `77394fc` | 多 2 案 |
| Q-1 | DQ-03 (b) 的「面板提示」對沒開通的單帳號安裝 | 不是本片能定：照計畫 §3.3、§8.4 沒開通又沒有帳號資料時只 log 一行、刪標記、不寫紀錄，所以今天的安裝還原後只有 log。要面板也提示，得留一個不含秘密的通知來源（會動到「逐位元不變」的範圍）。請主對話確認「沒開通的產品只有 log」可以接受，或在 HM-13c 前另定。建議：沒開通只有 log（今天的面板逐位元不變）；開通的產品由 HM-13c 依還原紀錄（預設帳號那列 `token: kept`）在面板提示。**2026-11-16 使用者定案**：照 DQ-03 (b) 原文，單帳號還原後也要有面板提示，交 HM-13c 做，本片不改（第 18.12 節） | — | — |

本輪沒有新決策，也沒有碰到待定題。

`evidence-fix-HM-13b/logs/red-367edde.txt` 是 `77394fc` 改 commit 訊息之前的同一棵樹（`367edde`，tree 相同）跑的。

第二次接續（2026-11-16 20:3x 起）：這一輪在 19:4x 因額度中斷。當時 5 個修正 commit（`aa8ef57`～`89a7e02`）已在，本筆記是沒 commit 的草稿
（數字留空），全套 pytest（`895119b`）跑到約 80% 就斷，留下一個 `/tmp/ha-mp-*`。接續時：

- 讀過每個 commit 的 diff、草稿、證據 log（先紅後綠、突變 N00～N13、影響到的 18 檔），和審查報告逐條對照，沒有發現要改的程式；
  先刪掉上一段留下的 `/tmp/ha-mp-*`（用完整路徑）。
- 正式 conftest 重跑新 3 檔：97 案全過，9.0 秒（`89a7e02`）。
- 全套 pytest 重跑（`89a7e02`；之後只改文件），結果見第 5 節。
- 威脅模型 I9、I13 的測試欄補上審查的新案，開頭的狀態照實寫第 3 節改了哪些（`27eeb16`）。
- `tool_inventory.py`、packaging、兩個預檢在新的 HEAD 重跑（第 5、8 節）。
- 再 fetch 一次 `claude-delivery`（只動 `origin/claude-delivery`）：`f4c7718`，多合了 #107 HM-11，它用掉契約第 9 節 #109～#112。

rebase 到 `claude-delivery` 時的提醒（寫在 rebase 之前；已照做，見第 18 節）：

- HM-31（#105）用掉契約第 9 節 #101～#108，HM-11（#107）用掉 #109～#112（20:4x 查）。本片的 #101～#104 要接在當時最後一列後面
  （照 20:4x 是 #113～#116），引用一起改：契約（第 1.3、3.5、3.6、9、10 節）、`acceptance-matrix.md` T-21、`threat-model.md` 第 3 節、
  本筆記、`runtime-patches.json` 的 `restore_lock.py` 說明、`restore_lock.py` 的 docstring（2 處 #102）、`tests/test_restore_lock.py`
  （4 處）、`tests/test_revoke_all.py`（1 處 #103）。本片加的每一處都在 `git diff 684a2dd..HEAD` 的新增行裡（`grep '#10[1-4]'`）；
  `claude-delivery` 本來就有的 #101～#104 是 HM-31 的，不要改。改了 `restore_lock.py` 就要重算它的 SHA-256。
- `git merge-tree` 預估要解的 6 個檔見第 1 節；HM-09 監看 cancel 的修正（#106）合進去之後，已知的 `test_backend_loopback` 逾時應該不再出現。

## 18. rebase 到 claude-delivery（2026-11-16）

第 1～17 節照 rebase 前寫，裡面的 commit 編號是 rebase 前的（對照在第 18.11 節）；契約列號已照 rebase 後的改（第 18.4 節）。
證據在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-rebase-HM-13b/`（`tools/` 是用到的腳本，副檔名多加 `.txt`；`logs/` 是 log；
`conflicts/` 是 5 個衝突 commit 解衝突前的檔，含衝突標記）。

### 18.0 結論

- 基準換成 `claude-delivery` `f4c7718`（HM-10 的 PR #104、HM-31 的 PR #105、HM-09 追補的 PR #106、HM-11 的 PR #107 合併後）。
  22 個 commit 照原順序重放。衝突在 5 個 commit、6 個檔（契約、`ledger-tracking.md`、`threat-model.md`、帳本、`gateway.py`、
  `profile_runtime.py`），兩邊的行為都留。
- 程式的衝突只有一種：HM-31 加 `body_budget` 的地方，就是本片加 `dormant_profiles` 的地方（`make_apps` 與 `ProfileRuntime`）。
  兩個參數都留，各自的檢查與說明都在。其他 17 個 commit 的 patch 和 rebase 前逐行相同。
- 本機子集另外抓到一個語意衝突（不是文字衝突）：HM-31 的測試釘住 `make_apps` 參數的最後四個，本片的 `dormant_profiles` 接在後面就不對了。
  改成釘住最後五個、並確認 `dormant_profiles` 也是 keyword-only、預設 None（`ebcb771`，只改測試；第 18.2 節）。
- 契約第 9 節本片的四列從 #101～#104 改成 #113～#116（HM-31 用掉 #101～#108、HM-11 用掉 #109～#112）。所有引用一起改，
  第 10 節加一列（`7a85928`）。本筆記的引用另一個 commit 改（`df63d79`）。
- 帳本 64 列：55 列和新基準逐欄相同；本片碰過的 9 列，說明是新基準的文字接本片的、SHA-256 照 rebase 後的檔重算。
  重放的 22 個 commit 每個都 0 漂移。
- 本機：pytest 子集（任務列的各檔與 HM-01 守門，共 22 檔）900 案 895 過，只有 5 個要 root 的 `test_root_*` 失敗；
  全套 6,090 案、0 skip，6,083 過，只有 7 個要 root 的既有案例失敗（33 分 38 秒）。子集第一次另外抓到 HM-31 一案的參數順序
  斷言（語意衝突），改測試後重跑（`ebcb771`，第 18.2 節）。packaging unittest `Ran 205`、`OK (skipped=5)`；`validate.py` PASS；
  `tool_inventory.py` exit 0。
- 兩個預檢 OK（base 是 `origin/claude-delivery`）；`origin/claude-delivery..HEAD` 每個 commit 都沒有原始雙向控制字元。
- 使用者 2026-11-16 對審查 Q-1 的定案寫進第 18.12 節：照 DQ-03 (b) 原文，單帳號還原後也要有面板提示，交 HM-13c 做，本片不改。

### 18.1 範圍

- `git fetch origin`（21:4x）：`origin/claude-delivery`＝`f4c7718`。先開本機備份分支 `backup/hm13b-before-rebase-20261116`（指向 `37cb6f4`，不 push）。
- `git log --oneline 684a2dd..37cb6f4` 是 22 個。#104 用 merge commit 合併（`d00a338`，第二個 parent 是 `684a2dd`，兩者的樹相同），
  所以直接 `git rebase origin/claude-delivery`，只重放這 22 個。
- 新基準帶進來的（`684a2dd..f4c7718`，69 個 commit，含 5 個合併 commit）：HM-10 的合併 `d00a338`、HM-31（PR #105）、
  HM-09 監看修正（PR #106）、HM-11（PR #107），共改 43 個檔。
- 和本片重疊的 8 個檔：契約、`acceptance-matrix.md`、`ledger-tracking.md`、`threat-model.md`、帳本、`gateway.py`、`profile_runtime.py`、
  `profiles.py`。`acceptance-matrix.md` 與 `profiles.py`（HM-31 只改註解）git 自動合併，其餘 6 個有衝突。
- 依賴：`684a2dd..f4c7718` 沒有動 `uv.lock`、`package-lock.json`、`package.json`、`pyproject.toml`、`requirements*`、`packaging/inputs.json`、
  patch 檔與 Dockerfile，沒有重跑 `setup_repo_env.sh`。面板原始碼有變（HM-11），照 CI 先 `npm run build` 再 `node tests/build-closure.mjs`
  （PASS；`dist/` 是忽略的檔，`git status` 仍乾淨）。

### 18.2 衝突與處理

解衝突用 repo 外的腳本：`blocks.py`（逐塊先斷言兩邊的內容，再組合）、`resolve_e91fc6f.py`、`resolve_6d30ef1.py`、`resolve_threat_header.py`
（各 commit 的規則）、`merge_ledger.py`（帳本不解文字，照 JSON 重組）。原則：新基準那一側照原文、放在前面；本片的行接在後面、照原文
（列號在 rebase 之後一起改，第 18.4 節）。兩邊改同一列時，各留自己改的部分，先確認另一邊那一列還是原 parent 的樣子。

| rebase 後（原本） | 衝突 | 處理 |
|---|---|---|
| `9c92cbd`（`e91fc6f`） | `gateway.py` 3 塊、`profile_runtime.py` 4 塊、帳本 3 列 | `make_apps` 的參數：`body_budget`（HM-31）在前、`dormant_profiles` 在後。docstring：HM-31 那段在前，空一行接本片那段（三引號移到本片那段結尾）。參數檢查：HM-31 的 `invalid request budget` 在前、本片的 `invalid dormant profiles` 在後。bootstrap 多 `dormant_profiles` 那行由 git 自動合併。`profile_runtime.py`：模組說明 HM-31 段在前、空一行接本片段；`RUNTIME_OPTIONS` 兩個名稱都加；`__init__` 兩個關鍵字都收（超過一行就換行）；`gateway_options` 兩個都轉給 `make_apps`。帳本：`merge_ledger.py` 重組（第 18.5 節） |
| `3106367`（`6d30ef1`） | 契約 6 塊、`ledger-tracking.md` 1 塊、`threat-model.md` 2 塊 | 契約：第 1.2 節尾 HM-31 與 HM-09 追補的兩段在前，空一行接本片的第 1.3 節；第 7 節「啟動順序」列用本片的、「關閉」列用 HM-09 追補的；第 9 節說明段 HM-31、HM-11 兩行在前、本片一行在後；#81 用 HM-31 審查改的、#82 用本片加附註的；表尾 #101～#112 在前、本片四列在後；第 10 節新基準七列在前、本片一列在後。`ledger-tracking.md` 的 `profiles.py` 列：負責片寫成 `HM-10 → HM-31（只改註解）→ HM-13b（隔離名稱不覆蓋、守門的移開名稱）→ HM-25`。`threat-model.md`：開頭狀態的本片那句原本接在 HM-09 那行尾；新基準在那行後面多了 HM-31 三行，所以本片那句改成放在最後、自成一行（字不變）；I8 用 HM-31 的、I9 用本片的 |
| `86bff5a`（`f3b8fa1`） | 帳本 1 列（`profiles.py`） | `merge_ledger.py` 重組 |
| `0346543`（`89a7e02`） | `threat-model.md` 1 塊（開頭狀態） | 新基準四行照原文；本片那句換成這個 commit 的寫法（補「依獨立審查改寫這兩條（MF-2、S-1、S-6；同日）」） |
| `509542b`（`27eeb16`） | `threat-model.md` 2 塊（開頭狀態、I8／I9） | 開頭狀態同上（這個 commit 的寫法）；I8 用 HM-31 的、I9 用這個 commit 的 |
| `ebcb771`（rebase 後新加） | 沒有文字衝突；本機子集抓到的語意衝突 | HM-31 的 `test_make_apps_takes_only_a_share_of_a_budget_beside_hm09s_and_hm10s_options` 釘住 `make_apps` 參數的最後四個是 `child_blocked`、`default_endpoint`、`bootstrap_fields`、`body_budget`（合併順序的檢查）。本片的 `dormant_profiles` 照合併順序接在 `body_budget` 後面，最後一個就變了。改成釘最後五個，並照 `body_budget` 的寫法確認 `dormant_profiles` 是 keyword-only、預設 None；`body_budget` 原有的檢查一個字沒改。程式沒改 |
| 其他 17 個 | 沒有 | 照原樣重放。帳本 4 個 commit（`dac66f2`、`6ebfbf0`、`7fe4417`、`23f138e`）自動合併：改的是 `operations.py`、`restore_lock.py` 兩列，新基準沒動 |

合計 5 個 commit：文件與程式 19 塊，帳本 4 塊（`9c92cbd` 3 塊、`86bff5a` 1 塊；帳本不解文字，整份重組）。

### 18.3 核對

- `git range-diff 684a2dd..37cb6f4 origin/claude-delivery..ed76963`：17 個「=」（patch 相同），5 個「!」就是上表的衝突 commit。
- 逐 commit（`same_change.py`：每個檔增刪的行當成多重集合比）：17 個逐行相同；5 個衝突 commit 只差在解衝突合起來的那幾行
  （帳本的 SHA-256 與說明、上表的程式行、`ledger-tracking.md` 一列、`threat-model.md` 開頭狀態）。
- 整段（`blob_compare.py`、`whole_change.py`，在 `ed76963`）：本片改、新基準沒改的 20 個檔和 `37cb6f4` 逐位元相同；其他檔（913 個）和 `f4c7718`
  逐位元相同；兩邊都改的 8 個檔裡，契約、`acceptance-matrix.md`、`profiles.py` 的增刪行和 rebase 前相同，其餘 5 個只差在解衝突的行。
- 每個重放的 commit，帳本的每一列都和那個 commit 的檔相符（`ledger_drift_per_commit.py`：22 個 commit 都 0 漂移、0 缺檔）。

### 18.4 列號對照（契約第 9 節；新基準最後是第 112 列）

| rebase 前（`684a2dd` 基準） | rebase 後（`f4c7718` 基準） | 項目 |
|---|---|---|
| #101 | #113 | 還原後獨立驗證比對的基準 |
| #102 | #114 | 還原樹裡 `profiles` 不是目錄 |
| #103 | #115 | 守門自己的名稱被目錄占用（列裡的「同 #102」→「同 #114」） |
| #104 | #116 | 沒有帳號資料時預設帳號的收據 |

- 新基準的 #101～#108 是 HM-31 的列、#109～#112 是 HM-11 的列，本片沒有引用。#1～#100 沒有移動，本片引用的 #20～#24、#67、#69、#82 不變。
- 解衝突時不改號（本片的行照原文重放）。改號在 rebase 後的一個 commit（`7a85928`，`renumber.py`）：每處是精確字串、次數固定，而且一定在本片
  自己加的行上，所以 HM-31、HM-11 的 #101～#112 與 PR 編號（#104～#107）改不到；改完再確認本片加的行沒有舊號。
- `7a85928` 改的：契約 13 處（開頭的狀態、第 1.3 節兩處、第 3.5、3.6 節、第 9 節說明段、四列的列號、#115 裡的「同 #114」、第 10 節本片的兩列），
  第 10 節加一列、開頭的狀態加一句；`threat-model.md` 第 3 節 1 處；`acceptance-matrix.md` T-21 1 處；`restore_lock.py` docstring 2 處；
  `tests/test_restore_lock.py` 4 處；`tests/test_revoke_all.py` 1 處（都只是說明文字）；帳本 `restore_lock.py` 那列的說明 2 處，SHA-256 重算。
- 本筆記 8 處另一個 commit（`df63d79`：結論、第 3.2、3.3、3.7 節、第 14、17 節）。第 1 節的 PR 編號（#104～#107）、第 5 節的「101.8 秒」、
  第 17 節最後 rebase 前寫的提醒照原文。PR 說明（repo 外的草稿）也改了。
- 不用改的地方：本片加的行只有上面 8 個檔寫了這幾個列號（掃 `git diff origin/claude-delivery HEAD` 的新增行）；`decisions.md`、
  `docs/operations/*.md`、面板與其他測試都沒有。
- commit 訊息照寫的當時，不改寫：`3106367`（原 `6d30ef1`）寫「接在 #100 後面補 #101～#104」與 T-21 的 #101～#104，`86bff5a`（原 `f3b8fa1`）寫
  「契約 #102」，`0346543`（原 `89a7e02`）寫「#102 分成…」「#103 補兩種名稱」，就是上表左欄。審查報告（`wave4/review-HM-13b.md`）與之前的
  證據目錄也是舊列號、舊 commit 編號。

### 18.5 帳本（`docs/provenance/runtime-patches.json`）

不只看文字合併：衝突的 commit 用 `merge_ledger.py` 照 JSON 重組（新基準的每一列照原文、原順序；本片碰過的列：說明是新基準的文字接本片在
列尾加的那段，先確認兩邊都只在列尾追加；新列照本片放在 `restore_detect.py` 後面；SHA-256 一律照工作樹的檔重算），再全列核對漂移。

- 新基準 63 列，rebase 前 62 列，現在 64 列（多了本片的 `restore_lock.py`）。
- 55 列和新基準逐欄相同（含 HM-31、HM-11 改的那些列）。
- 本片碰過的 9 列（`ledger_final.py` 在最後的 HEAD 核對）：

| 列管檔 | 新基準 | rebase 前（`37cb6f4`） | rebase 後 |
|---|---|---|---|
| `gateway.py` | `1f954cf11cde` | `24c1feb6a28b` | `fd31659f2e86` |
| `profile_runtime.py` | `048e73896820` | `43fb41e975ed` | `39b23230a042` |
| `profiles.py` | `cd74d45a0abe` | `15cbcab36617` | `1b6ebb49d005` |
| `restore_lock.py`（新列） | — | `807a6a54755d` | `182282ed7ac9`（重放後是 `807a6a54755d`；`7a85928` 改了 docstring 兩處） |
| `run_product.py` | `59d281b17549` | `7d9c3dc8e237` | `7d9c3dc8e237` |
| `operations.py` | `85456d10615f` | `f26275cbe5be` | `f26275cbe5be` |
| `apps/n8n/run.py` | `96861eee084f` | `6b92b9c7c2a6` | `6b92b9c7c2a6` |
| `restore_detect.py`（只補說明） | `4dc72563dc2b` | `4dc72563dc2b` | `4dc72563dc2b` |
| `identity_fields.py`（只補說明） | `af6e130ceb36` | `af6e130ceb36` | `af6e130ceb36` |

- 兩邊都改的 3 個檔，值是新的：檔的內容本來就是兩邊合起來的。只有本片改的 3 個檔（`run_product.py`、`operations.py`、`apps/n8n/run.py`）
  和 rebase 前相同（檔逐位元相同）；`restore_detect.py`、`identity_fields.py` 本片只補說明，檔沒變。
- 說明文字：只有 `restore_lock.py` 那列和 rebase 前不同（列號兩處）；其他 8 列都是新基準的文字接本片原本加的那段。
- JSON 照 repo 的寫法（`indent=2`、`ensure_ascii=False`、結尾換行），每個 commit 重新序列化都逐位元相同。
- 沒動 `apps/runtime/*.py`、`apps/*/launch.py`：tool-surface 不用重產，`scripts/tool_inventory.py` exit 0（第 18.7 節）。

### 18.6 和新基準的互動

- HM-31（請求內容位元組預算、結構守門）：守門在 `ProfileManager`（開通時在建構時推導全 add-on 的預算）與單帳號 runtime（`make_apps`
  自己建份額）之前跑；守門不讀 body、不開 listener，不扣預算，也碰不到結構守門。`make_apps` 同時收 `body_budget` 與 `dormant_profiles`；
  休眠時 `run_product` 只給 `dormant_profiles`，份額照 HM-31 由 `make_apps` 自己建。HM-31 的 3 檔 181 案（`test_request_budget` 61、
  `test_request_structure` 83、`test_request_budget_gateway` 37）在 `ebcb771` 全過；`test_every_products_runtime_reads_under_the_budget_and_the_guard`
  跑每個產品的正式 runtime，也經過守門。唯一的語意衝突是參數順序那案（第 18.2 節）。
- HM-09 追補（監看一定照停止要求停下）：`test_monitor_cancel.py` 13 案全過。它直接跑 `run_product.run`（開通與沒開通兩種），帳號由
  `multi_profile_runtime.create_profile` 建（本片讓它先建 sentinel），所以開通時守門看不到還原；沒開通的那案磁碟上有帳號資料，依程式
  B 會先被守門當成休眠帳號撤銷。這幾案只量關閉的時間，都在 HA 的 30 秒內停下。
- HM-11（面板）：本片沒動面板。真後端形狀比對 `tests/test_panel_profile_api_shapes.py` 10 案全過，`expect` 不用重錄：開通的 bootstrap
  不會有 `dormant_profiles`（`make_apps` 拒絕和 `profile_view` 一起給），沒開通又沒有帳號資料時逐位元同今天。面板原始碼有變，照 CI 重建了 `dist/`。
- HM-10：`test_profile_admin_api` 32、`test_admin_pipeline_matrix` 5、`test_router_passthrough` 49 案全過。
- `tests/test_output_schemas.py` 對 `apps/n8n/run.py` 的位元組釘選（原 `96c4d3b`，現 `0ac439f`）仍對：新基準沒動這個檔，189 案全過。
- HM-01 守門 7 檔（log 掃描、owned ports bearer、黃金回歸、兩個契約凍結、兩個預檢工具）132 案全過：開關關的回應逐位元不變。

### 18.7 本機檢查（一般使用者；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 都排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `npm run build`＋`node packages/mcp-admin-ui/tests/build-closure.mjs`（面板原始碼有變，照 CI 先建；`7a85928` 之前、21:52） | PASS（`dist/` 是忽略的檔，`git status` 乾淨） |
| pytest 子集第 1 次（`7a85928`；22:33 取得鎖，正式 conftest） | 900 案：894 過、6 失敗＝5 個要 root 的 `test_root_*`＋HM-31 的 `test_make_apps_takes_only_a_share_of_a_budget_beside_hm09s_and_hm10s_options`（參數順序，語意衝突；`ebcb771` 修，第 18.2 節）。全套因此沒跑 |
| pytest 子集第 2 次（`ebcb771`；22:36 取得鎖） | 900 案、0 skip：895 過，5 個失敗都是要 root 的 `test_root_*`，82.1 秒 |
| 子集的各檔（第 2 次） | 新 3 檔：`test_restore_lock` 71、`test_dormant_profiles` 8、`test_revoke_all` 18 全過；HM-13a `test_restore_detection` 139（134 過，5 個 root）；HM-10 3 檔 86；HM-31 3 檔 181；`test_monitor_cancel` 13；`test_panel_profile_api_shapes` 10；`test_output_schemas` 189；HM-01 守門 7 檔 132；`test_upgrade_zero_rewrite` 45；`test_tool_inventory` 8（`logs/subset-2-by-file.txt`） |
| pytest 全套（`tests`，CI 的指令加 `-rfEs --durations=30`，正式 conftest；`ebcb771`） | 6,090 案、0 skip，6,083 過、7 個失敗，2,018.4 秒（33 分 38 秒；22:38 開始、23:11 跑完，開始與結束時工作樹都乾淨、HEAD 都是 `ebcb771`）。失敗的 7 案就是要 root 的既有案例（`test_restore_detection` 5、`test_profile_store` 1、`test_owned_executable` 1，都停在要求 root 的那一行斷言：`os.geteuid() == 0`，`test_owned_executable` 是 `os.getuid() == 0`）。新 3 檔 97 案（junit 8.0 秒）。子集的 22 檔在全套裡也全過（root 的除外） |
| packaging unittest（照 CI 的離線暫存 venv：`uv sync --frozen --no-dev --offline`＋`requirements-ci`，不用 PYTHONPATH） | `Ran 205`、`OK (skipped=5)`（5 個 `skipUnless(root)` 同基準；`7a85928`，之後沒改 `packaging/`） |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15） | PASS（`7a85928`） |
| `scripts/tool_inventory.py` | exit 0（`7a85928`；沒動 tool-surface 的來源） |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`features.py` 對新基準 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |
| 已知的 HM-09 關閉逾時（`test_backend_loopback.py::…end_to_end[False]`） | 0 次（#106 已在新基準裡） |

### 18.8 預檢（base 都是 `origin/claude-delivery`）

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | OK，0 命中（gitleaks 8.28.0；`f4c7718..ebcb771` 24 個 commit，另掃 HEAD 的樹與整段歷史；`7a85928` 上也跑過一次：23 個 commit、0 命中） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | OK：`runtime-patches.json` 177 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的 29 個檔裡 7 個列管檔由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔（`ebcb771`） |

本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 18.9 雙向控制字元

`bidi_scan.py`（HM-11 的同一支）逐 commit 查 `origin/claude-delivery..HEAD`：那個 commit 的樹裡、這段範圍碰過的每個文字檔的全文；那個 commit
自己新增的行；commit 訊息（標題與內文）。`ebcb771`（本筆記之前的 24 個 commit）上：U+202A～202E、U+2066～2069 合計 0 個；U+200E、U+200F、U+061C 也是 0 個。
這段範圍碰過的 29 個檔都是文字檔，沒有跳過的檔。本筆記的兩個 commit 之後再跑一次，結果記在 PR 說明。

### 18.10 只在 CI 跑的測試、CI 時間

- rebase 只改了一個測試的斷言：HM-31 的 `make_apps` 參數順序那案多釘一個參數（`ebcb771`，第 18.2 節）；`7a85928` 只改兩個測試檔的說明文字。
  沒有只在 CI 跑的新測試；要 root 的 7 個既有案例本機一定失敗（第 6 節）。
- `checks` 推估照第 6 節（本片多約 20～30 秒）。實際秒數 CI 跑完再補。

### 18.11 commit 對照

「相同」＝`git range-diff` 的「=」（patch 相同）。

| # | rebase 前 | rebase 後 | 說明 |
|---|---|---|---|
| 1 | `3c90b6c` | `42b558c` | 相同 |
| 2 | `e91fc6f` | `9c92cbd` | 衝突（`gateway.py`、`profile_runtime.py`、帳本） |
| 3 | `6d30ef1` | `3106367` | 衝突（契約、`ledger-tracking.md`、`threat-model.md`） |
| 4 | `c5999ed` | `dac66f2` | 相同（帳本，自動合併） |
| 5 | `2c4de0f` | `2b324e8` | 相同 |
| 6 | `338a8bf` | `bc28a55` | 相同 |
| 7 | `0028169` | `6ebfbf0` | 相同（帳本，自動合併） |
| 8 | `cc5adb0` | `7fe4417` | 相同（帳本，自動合併） |
| 9 | `9c29b4f` | `23f138e` | 相同（帳本，自動合併） |
| 10 | `360836e` | `7fe239d` | 相同 |
| 11 | `5b596cd` | `320a3d4` | 相同 |
| 12 | `7d237f6` | `127f630` | 相同 |
| 13 | `1f8c29f` | `e0dd3d5` | 相同 |
| 14 | `96c4d3b` | `0ac439f` | 相同 |
| 15 | `551d210` | `85b571b` | 相同 |
| 16 | `aa8ef57` | `e25cd2e` | 相同 |
| 17 | `77394fc` | `5036dab` | 相同 |
| 18 | `f3b8fa1` | `86bff5a` | 衝突（帳本） |
| 19 | `895119b` | `aeb44bb` | 相同 |
| 20 | `89a7e02` | `0346543` | 衝突（`threat-model.md`） |
| 21 | `27eeb16` | `509542b` | 衝突（`threat-model.md`） |
| 22 | `37cb6f4` | `ed76963` | 相同 |

rebase 之後新加的 commit：

| commit | 內容 |
|---|---|
| `7a85928` | 契約第 9 節本片的列改成 #113～#116，所有引用一起改；第 10 節加一列；帳本 `restore_lock.py` 那列重算 |
| `ebcb771` | HM-31 的 `make_apps` 參數順序測試多釘 `dormant_profiles`（本機子集抓到的語意衝突） |
| `df63d79` | 本筆記改列號（8 處；第 18.4 節） |
| 本筆記 | 第 18 節；結論、第 1 節的基準與 commit、第 5、8、13、14、17 節的狀態 |

### 18.12 使用者定案與交接

- **審查 Q-1，使用者 2026-11-16 21:xx 定案**：照 DQ-03 (b) 原文，沒開通的單帳號安裝還原後也要有面板提示「權杖已回到備份當時的值」，
  不只 log。由 HM-13c 做（計畫 §12.3 HM-13c 已加註）：開機守門偵測到還原時留一筆提示紀錄、接在本片的守門上；bootstrap 多一個欄位、
  面板顯示、管理員可以關掉；這是不受開關管的改變（契約 §1.2 記例外、HM-01 管理契約凍結逐案改並寫理由、各產品 CHANGELOG 記一行，交發版片）；
  還原時權杖的行為仍和今天一樣，不撤銷。**本片不改**：沒開通又沒有帳號資料時仍只記一行 WARNING、刪標記，什麼都不寫（第 3.1 節）。
- HM-03a 的探針多一項（README 的交接已加）：守門沒做完時，Supervisor 會不會用 Watchdog 自動再起（第 11 節最後一列）。
- push：先查遠端沒有這個分支，再 `git push -u origin feat/ha-multiprofile-hm13b-20261116`（分支原本沒有上游）。備份分支只在本機。
- 合併條件不變：HM-03a 的 UC-08 與 sentinel 實機結果寫進第 11 節（不可靠就照 DQ-39 (a)）；CI 全綠。
- 列號：之後還有片在契約第 9 節 #116 後面加列時，後合併的接在當時最後一列後面重排。

## 19. 和 claude-delivery 合併（2026-11-17）

第 1～18 節照合併前寫；契約列號的現行指標已改成合併後的（第 19.4 節），第 18 節是第一次 rebase 的紀錄，照原文。
證據在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-merge-HM-13b/`（`tools/`：用到的腳本，副檔名多加 `.txt`；`logs/`：log；
`conflicts/`、`conflicts-diff3/`：解衝突前的 8 個檔，含衝突標記，後者是 diff3 格式）。

### 19.0 結論

- `claude-delivery` 在 `f4c7718` 之後合了 HM-12 後端（PR #110）、HM-30（PR #111）、HM-32（PR #113）、HM-12 面板（PR #114），head 是 `165dbaf`。
  本 PR（#108）和它有衝突，GitHub 不替有衝突的 PR 跑 CI，疊在上面的 #112 也一樣。照 PR #106 的前例（`6231b0f`），用 merge commit 把
  `origin/claude-delivery` 合進本片（`6bb7fcd`：第一個 parent 是本片 `ebab019`、第二個是 `165dbaf`），不 rebase、不 force push；之後一般的
  fast-forward push。
- 衝突在 8 個檔：程式、測試與文件 7 個檔 19 塊，帳本 4 塊另照 JSON 重組（不解文字）。程式的衝突都是「兩邊在同一個地方各加一個選項」：HM-12 的 `stop_child`、HM-30 的
  `reply_worker` 和本片的 `dormant_profiles` 在 `make_apps`、`ProfileRuntime` 並存；`run_product` 留 HM-30 的 `worker = None`，判斷照本片用這次
  開機讀到的 `enabled`（守門和 runtime 看到同一個答案）。兩個測試檔的說明與一個參數順序斷言照語意合（第 19.2 節）。文件的表格與清單：新基準的
  行在前、本片在後，逐字保留。
- 契約第 9 節本片的四列從 #113～#116 改成 #118～#121（HM-12 用掉 #113～#115、HM-12 面板用掉 #116、#117），引用一起改（`0ea1c37`）；本筆記的
  現行指標在本筆記的 commit 改（第 19.4 節）。
- 帳本 65 列：新基準 64 列照原順序，本片的 `restore_lock.py` 接在 `restore_detect.py` 後面；兩邊都改的 4 列，說明是新基準的文字接本片的；
  SHA-256 照合併後的檔重算（第 19.5 節）。
- 本機：pytest 子集 39 檔 1,848 案、0 skip，1,843 過，只有 5 個要 root 的 `test_root_*` 失敗；面板 node 88 案、build、build closure PASS；packaging
  unittest `Ran 205`、`OK (skipped=5)`；`validate.py` PASS；`tool_inventory.py` exit 0。兩個預檢 OK、雙向控制字元 0 個（第 19.7～19.9 節）。
- 和 `claude-delivery` 相比，本 PR 的改動仍是原本的 29 個檔；26 個檔的增刪行數和合併前（對 `f4c7718`）相同，差在契約（第 10 節多一列）與兩個
  測試檔（第 19.2 節）。

### 19.1 範圍

- `git fetch origin`（2026-11-17 07:5x）：`origin/claude-delivery`＝`165dbaf`；本片的遠端分支與本機 head 都是 `ebab019`、工作樹乾淨。先開本機
  備份分支 `backup/hm13b-before-merge-20261117`（指向 `ebab019`，不 push）。
- 新基準帶進來的（`f4c7718..165dbaf`）：84 個 commit（含 4 個合併 commit：#110 `7646f0f`、#111 `ebefebe`、#113 `a709b97`、#114 `165dbaf`），共改 51 個檔。
- 兩邊都改的 12 個檔：契約、`acceptance-matrix.md`、`ledger-tracking.md`、`threat-model.md`、帳本、`gateway.py`、`profile_runtime.py`、`run_product.py`、
  `tests/multi_profile_runtime.py`、`tests/test_output_schemas.py`、`tests/test_request_budget_gateway.py`、`tests/test_upgrade_zero_rewrite.py`。
  `acceptance-matrix.md`、`ledger-tracking.md`、`multi_profile_runtime.py`、`test_output_schemas.py` 兩邊改的是不同行，git 自動合併；其餘 8 個有衝突。
- 依賴：`f4c7718..165dbaf` 沒有動 `uv.lock`、`package-lock.json`、`package.json`、`pyproject.toml`、`requirements*`、`packaging/inputs.json`、patch 檔與
  Dockerfile，沒有重跑 `setup_repo_env.sh`。面板原始碼有變（HM-12 面板），照 CI 先 `npm run build` 再 `node tests/build-closure.mjs`。
- PaaS：本機唯讀 PaaS repo 的 `origin/main` 是 `48f394d`（沒有 fetch），`7087280` 之後只多 #156（Hermes 排程工具說明，HM-33 在補），和本片無關。

### 19.2 衝突與處理

解衝突用 repo 外的腳本：`blocks3.py`（diff3 格式，逐塊先斷言三邊的內容再組合）、`resolve_hm13b_merge.py`（每塊的規則）、`merge_ledger3.py`
（帳本三方照 JSON 重組）。原則：新基準那一側照原文、放在前面；本片的行接在後面、照原文（列號在合併之後一起改，第 19.4 節）；程式照語意合。

| 檔 | 衝突 | 處理 |
|---|---|---|
| `gateway.py` | 3 塊 | `make_apps` 的參數照合併順序：`stop_child`、`reply_worker`（HM-12、HM-30）在前，`dormant_profiles` 在後。docstring：HM-12、HM-30 兩段在前，空一行接本片那段（三引號移到本片那段結尾）。參數檢查：`invalid child stop`、`invalid reply worker` 在前，本片的 `invalid dormant profiles` 在後。bootstrap 多 `dormant_profiles` 那行 git 自動合併 |
| `profile_runtime.py` | 5 塊 | 模組說明：HM-12、HM-30 兩段在前，空一行接本片那段；`RUNTIME_OPTIONS` 三個名稱都收（`'stop_child', 'reply_worker', 'dormant_profiles'`）；類別說明 HM-30 段在前、本片段在後；`__init__` 收 `reply_worker=None, dormant_profiles=None`；`gateway_options` 兩個都轉給 `make_apps`（超過一行就換行）。HM-30 的 `self.reply_worker = reply_worker` 自動合併 |
| `run_product.py` | 1 塊 | HM-30 在判斷前加 `worker = None`，本片把判斷改成這次開機讀到的 `enabled`：兩行都留（`worker = None`、`if enabled:`）。開通時 `ProfileManager(..., reply_worker=worker)`（HM-30），沒開通時 `ProfileRuntime(..., dormant_profiles=guarded.dormant)`（本片），都自動合併 |
| `tests/test_request_budget_gateway.py` | 2 塊 | HM-31 那案釘住 `make_apps` 參數的最後幾個（合併順序的檢查）：HM-30 改成釘最後六個（`stop_child`、`reply_worker`），本片原本釘最後五個（`dormant_profiles`）。改成釘最後七個：`..., 'body_budget', 'stop_child', 'reply_worker', 'dormant_profiles'`；本片原有的「`dormant_profiles` 也是 keyword-only、預設 None」照留。說明用 HM-30 的文字，本片那句改成「merged after HM-31, HM-12 and HM-30, follows reply_worker」。程式沒改 |
| `tests/test_upgrade_zero_rewrite.py` | 2 塊 | 兩邊都改了模組說明與 `UNWIRED`：HM-12 接上 `identity_fields.py`（`UNWIRED = ('restore_detect',)`），本片接上 `restore_detect.py` 而且守門也讀 `identity_fields.py`（`UNWIRED = ()`）。說明用本片的「Wired since」，接一句 HM-12 接上 `identity_fields.py` 的原文；本片那句改成「HM-13b wired HM-13a's restore_detect.py and reads HM-07's identity_fields.py too」。`UNWIRED = ()`，註解寫三片各接了什麼 |
| 契約 | 4 塊 | 第 1.2 節尾 HM-32 那段在前，接本片的第 1.3 節；第 9 節說明段 HM-12、HM-30、HM-12 面板三行在前、本片一行在後；第 9 節表尾 HM-12 的 #113～#117 在前、本片四列在後；第 10 節新基準的列在前、本片三列在後 |
| `threat-model.md` | 2 塊 | 開頭狀態：HM-12、HM-30 的行在前、本片的兩行在後；I8 用 HM-30 改的那列（本片沒改 I8，先斷言本片這邊的 I8 和基準相同）、I9 用本片改的那列（新基準沒改 I9，同樣先斷言） |
| 帳本 | 4 塊 | 不解文字，`merge_ledger3.py` 照 JSON 重組（第 19.5 節） |

合計：程式 9 塊、測試 4 塊、文件 6 塊、帳本 4 塊（另算）。

### 19.3 核對

- 每個兩邊都改的檔（`both_sides_kept.py`，在合併的工作樹）：每一邊對基準加的行都在合併後的檔裡，除了上表解衝突時合起來的那幾行。
  契約、`acceptance-matrix.md`、`ledger-tracking.md`、`threat-model.md`、`run_product.py`、`multi_profile_runtime.py`、`test_output_schemas.py`
  兩邊加的行全在、沒有新寫的行；`gateway.py` 只差參數的 `reply_worker=None):`→`reply_worker=None,` 與 HM-30 docstring 最後一行的三引號；
  `profile_runtime.py` 只差上表三處合起來的行；兩個測試檔只差上表的說明與斷言；帳本只差 4 列的 SHA-256 與說明（第 19.5 節）。
- 合併後和 `claude-delivery` 相比改了 29 個檔，就是本片原本的 29 個（對 `f4c7718`）；26 個檔的增刪行數和合併前相同，契約多 1 行（第 10 節的新列）、
  `test_request_budget_gateway.py`、`test_upgrade_zero_rewrite.py` 照上表。
- 第 9 節的列號在 `0ea1c37` 之後是 1～121 連號、沒有重複。

### 19.4 列號對照（契約第 9 節；新基準最後是第 117 列）

| 合併前（`f4c7718` 基準） | 合併後（`165dbaf` 基準） | 項目 | 原稿（`684a2dd` 基準） |
|---|---|---|---|
| #113 | #118 | 還原後獨立驗證比對的基準 | #101 |
| #114 | #119 | 還原樹裡 `profiles` 不是目錄 | #102 |
| #115 | #120 | 守門自己的名稱被目錄占用（列裡的「同 #114」→「同 #119」） | #103 |
| #116 | #121 | 沒有帳號資料時預設帳號的收據 | #104 |

- 新基準的 #113～#115 是 HM-12 的列、#116、#117 是 HM-12 面板的列，本片沒有引用。#1～#112 沒有移動，本片引用的 #20～#24、#67、#69、#82 不變。
- 解衝突時不改號（本片的行照原文）。改號在合併後的一個 commit（`0ea1c37`，`renumber_hm13b.py`）：每處是精確字串、次數固定，而且一定在本片自己加的行上
  （新基準的檔沒有那一行），所以 HM-12 的 #113～#117 改不到；改完再確認本片加的行沒有舊號（第一次 rebase 的紀錄除外）。
- `0ea1c37` 改的：契約 14 處（開頭的狀態兩處：審查改的 #119、#120，另加「合併 `claude-delivery` `165dbaf` 之後改成 #118～#121（2026-11-17）」；
  第 1.3 節兩處；第 3.5、3.6 節；第 9 節說明段；四列的列號；#120 裡的「同 #119」；第 10 節本片的第一、二列），第 10 節加一列；`threat-model.md`
  第 3 節 1 處；`acceptance-matrix.md` T-21 1 處；`restore_lock.py` docstring 2 處；`tests/test_restore_lock.py` 4 處；`tests/test_revoke_all.py` 1 處
  （都只是說明文字）；帳本 `restore_lock.py` 那列的說明 2 處，SHA-256 重算。
- 照原文的歷史紀錄：契約第 10 節第一次 rebase 那一列（「原稿 #101～#104 成為第 113～116 列」「#115 裡指到的 #114」）與開頭狀態裡講它的那句
  （「rebase 到 `claude-delivery` 之後本片的列改成 #113～#116（同日）」）；本筆記的結論第二點、第 17 節最後的 rebase 前提醒、第 18 節整節。
- 本筆記改的現行指標 8 處（本筆記的 commit；`renumber_hm13b_notes.py`）：結論 MF-2 那點、第 3.2 節表格與說明、第 3.3、3.7 節標題、第 3.8 節、
  第 14 節「第 9 節與變更紀錄」那列（改寫成兩次改號都寫）、第 17 節 MF-2 那列。PR 說明（repo 外的草稿）也改了。
- 不用改的地方：本片加的行只有上面這些檔寫了這幾個列號（掃 `git diff origin/claude-delivery HEAD` 的新增行）；`decisions.md`、`docs/operations/*.md`、
  面板與其他測試都沒有。FM-118～FM-120 是功能對照表的編號，不是列號。
- commit 訊息照寫的當時，不改寫（第 18.4 節列的那幾個，與 `7a85928`、`ebab019` 的訊息）。

### 19.5 帳本（`docs/provenance/runtime-patches.json`）

`merge_ledger3.py`：以新基準（`165dbaf`）的帳本為底、照原順序；本片沒碰的列照新基準；只有本片碰的列用本片的；兩邊都碰的列，說明是新基準的文字接
本片在列尾加的那段（先確認兩邊都只在列尾追加，其他欄位三邊相同）；本片新加的列放在本片帳本裡它前一列的後面；SHA-256 一律照合併後的工作樹重算，
最後全列核對 0 漂移。JSON 照 repo 的寫法（`indent=2`、`ensure_ascii=False`、結尾換行）。

| 列管檔 | 基準 `f4c7718` | 本片 `ebab019` | 新基準 `165dbaf` | 合併後（`6bb7fcd`） | `0ea1c37` 之後 |
|---|---|---|---|---|---|
| `gateway.py`（兩邊） | `1f954cf11cde` | `fd31659f2e86` | `92cb8313a108` | `d7b7e6bf6f73` | 同左 |
| `run_product.py`（兩邊） | `59d281b17549` | `7d9c3dc8e237` | `78d511c9b82e` | `a31ea8d9238a` | 同左 |
| `profile_runtime.py`（兩邊） | `048e73896820` | `39b23230a042` | `012bc7ba24d7` | `dc5464cb2804` | 同左 |
| `identity_fields.py`（兩邊；本片只補說明） | `af6e130ceb36` | `af6e130ceb36` | `2dbd605c1834` | `2dbd605c1834`（檔是新基準的） | 同左 |
| `restore_lock.py`（本片新列） | — | `182282ed7ac9` | — | `182282ed7ac9` | `5441cf09c8d8`（docstring 兩處改號） |
| `apps/n8n/run.py`、`operations.py`、`profiles.py`、`restore_detect.py`（只有本片） | — | — | — | 和本片相同（`6b92b9c7c2a6`、`f26275cbe5be`、`1b6ebb49d005`、`4dc72563dc2b`） | 同左 |

- 新基準 64 列、本片 64 列，合併後 65 列（多本片的 `restore_lock.py`）；本片沒碰的 56 列和新基準逐欄相同（含 HM-12、HM-30 加的 `reply_worker.py` 等列）。
- 兩邊都改的 4 列，說明 = 新基準的文字（27,880／3,887／6,920／926 字）接本片加的那段（444／421／308／169 字）。

### 19.6 和新基準的互動

- HM-12（Odoo 換身分換 token、新來源重填秘密）：守門在開機時、任何子程式與 listener 之前跑；換身分在執行中的 8099 存檔時跑。兩者不共用狀態：
  `make_apps` 同時收 `stop_child` 與 `dormant_profiles`（後者只給沒開通、有帳號資料的產品，那時沒有換身分）。HM-12 的 4 個測試檔 94 案全過
  （`test_odoo_identity_rotation` 33、`test_new_origin_secret` 41、`test_odoo_multi_profile` 3、`test_identity_fields` 17；另 `test_saved_destinations` 90）。
  HM-12 把 `identity_fields.py` 接進 `products.py`、`backend_edit.py`，本片的守門本來就讀它：`test_upgrade_zero_rewrite` 45 案全過。
- HM-30（回覆工作執行緒）：`run_product` 開通時建 `ReplyWorker` 給 `ProfileManager`，沒開通時 `worker` 是 None（今天的單帳號）；守門在兩者之前跑，
  不讀回覆、不碰工作執行緒。`test_reply_worker` 147、`test_health_tolerance` 2、`test_profile_runtime` 65 案全過（量停頓的測試也綠）。
- HM-32（LiteLLM、EMQX 的連線池）：和本片沒有交集；`test_fresh_backend_connections` 20 案全過。
- HM-12 面板：本片沒動面板。重建 `dist/` 後 `test_panel_profile_api_shapes` 14 案全過（`expect` 不用重錄：沒開通又沒有帳號資料時 bootstrap 逐位元同今天）。
- HM-09 追補、HM-31、HM-10、HM-11：`test_monitor_cancel` 13、HM-31 三檔 181、`test_profile_admin_api` 32、`test_admin_pipeline_matrix` 5、
  `test_router_passthrough` 49 案全過。
- HM-01 守門 7 檔（log 掃描、owned ports bearer、黃金回歸、兩個契約凍結、兩個預檢工具）132 案全過；`test_tool_inventory` 8 案全過。

### 19.7 本機檢查（一般使用者 uid 1000；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `npm test`、`npm run build`、`node tests/build-closure.mjs`（`0ea1c37`，08:03） | node 88 案全過；build、build closure PASS（`dist/` 是忽略的檔，`git status` 乾淨） |
| pytest 子集（`0ea1c37`；08:03 取得鎖，正式 conftest；`tools/pytest-subset.txt` 的 39 檔：本片 4 檔、本片改過的既有測試、HM-12、HM-30、HM-31、HM-32、HM-09、HM-10／HM-11 與起 runtime 的測試、HM-01 守門與預檢） | 1,848 案、0 skip：1,843 過，5 個失敗都是要 root 的 `test_root_*`（`test_restore_detection`），321.4 秒（`logs/pytest-subset-by-file.txt`） |
| packaging unittest（照 CI 的離線暫存 venv） | `Ran 205`、`OK (skipped=5)`（5 個 `skipUnless(root)` 同基準） |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15，不加 `-I`） | PASS |
| `scripts/tool_inventory.py` | exit 0（沒動 tool-surface 的來源） |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`features.py` 對新基準 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |

全套 pytest 這次沒在本機跑（CI 會跑）；HM-13c 合併本片之後，在 HM-13c 的 head 上跑。

### 19.8 預檢（base 都是 `origin/claude-delivery`）

| 預檢 | 結果 |
|---|---|
| 秘密 `secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | OK，0 命中（gitleaks 8.28.0；`165dbaf..0ea1c37` 28 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 `ledger_precheck.py --repo . --base origin/claude-delivery` | OK：0 漂移、0 缺；改過的列管檔都由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔（`0ea1c37`） |

本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 19.9 雙向控制字元

`bidi_scan.py`（HM-11 的同一支）逐 commit 查 `origin/claude-delivery..HEAD`，另用 `bidi_merge_check.py` 查合併 commit：和兩個 parent 各比一次的新增行、
訊息，以及和 `claude-delivery` 不同的 29 個檔在 HEAD 的全文。`0ea1c37` 上：U+202A～202E、U+2066～2069 合計 0 個；U+200E、U+200F、U+061C 也是 0 個。
本筆記的 commit 之後再跑一次，結果記在 PR 說明。

### 19.10 只在 CI 跑的測試、CI 時間

- 合併只改了測試的說明與 HM-31 一案的參數順序斷言（第 19.2 節），沒有只在 CI 跑的新測試；要 root 的 7 個既有案例本機一定失敗（第 6 節）。
- `checks` 推估：新基準的全套比 `f4c7718` 多 HM-12、HM-30、HM-32 的測試（#114 的 CI 2,322 秒）；本片自己的增量照第 6 節（多約 20～30 秒）。實際秒數
  CI 跑完再補。

### 19.11 commit 與 push

| commit | 內容 |
|---|---|
| `6bb7fcd` | merge commit：把 `claude-delivery` `165dbaf` 合進本片（第 19.2 節的解法；訊息寫了每個檔怎麼解） |
| `0ea1c37` | 契約第 9 節本片的列改成 #118～#121，所有引用一起改；第 10 節加一列；帳本 `restore_lock.py` 那列重算 |
| 本筆記 | 現行列號 8 處、結論、第 1、14 節的狀態、第 19 節 |

- push：一般的 `git push origin feat/ha-multiprofile-hm13b-20261116`（從 `ebab019` 往前 fast-forward，不 force）。備份分支只在本機。
- 合併條件不變：HM-03a 的 UC-08、sentinel 與 Watchdog 結果寫進第 11 節（不可靠就照 DQ-39 (a)）；CI 全綠。
- 列號：之後還有片在契約第 9 節 #121 後面加列時（HM-13c 的 #117、#118 會變成 #122、#123），後合併的接在當時最後一列後面重排。
