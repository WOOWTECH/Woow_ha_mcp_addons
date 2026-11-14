# HA 多帳號 HM-13a provenance：還原偵測（entrypoint 標記、sentinel；不受開關管）（2026-11-14～15）

## 結論

- 範圍：還原偵測的兩個訊號，都不受產品開關管。
  - 訊號 1：`packaging/entrypoint.py` 發現 `/data/mcp` 屬 root（HA 還原）時，在修復的 pass 1 之前建 `.restore-detected` 並 fsync。
  - 訊號 2：新模組 `packages/mcp-admin-core/mcp_admin_core/restore_detect.py`：sentinel 與 record 的建立、比對、重建，只在產品開通或
    磁碟上有帳號資料時動作。
- 新模組還沒接進開機流程。依偵測結果撤銷、重建 sentinel、刪標記是 HM-13b。
- 今天沒有產品開通、也沒有帳號資料。執行期看得到的變化只有一項：還原後 `/data/mcp` 多一個空的 `.restore-detected`
  （0600、10001），`re-owned` 的數字多 1。沒有還原的開機零變化。
- 建不出標記：磁碟上有帳號資料就拒絕啟動（下次開機重試）；沒有就印一行 WARNING、繼續修復。兩行訊息都在括號裡寫原因
  （errno 名稱或 `name in use`）。
- 容器驗收：`packaging/container_probe.py` 多一段「Supervisor 式還原後的啟動」，每個產品下一次發版的 builder 驗收都會跑
  （審查必修 MF-1，採選項 (a)；**開 PR 前要負責人確認**，第 12 節）。
- 獨立安全審查判「修正後通過」（必修 1、建議 10）。必修與建議的處理見第 12 節。
- 新測試 `tests/test_restore_detection.py` 139 案：134 案本機（一般使用者）通過；5 案 `test_root_*` 只在 CI（root）驗，本機執行
  會在第一行失敗，不會 skip。packaging unittest 191 案 OK（skipped=5，同基準）。
- 守門有效：先紅後綠有紀錄；本片的突變共 46 個（作者 26、審查後補 20）全部被擋（第 4 節）。
- 全套 pytest：審查修正前在 `4aae8ea` 跑過（3858 案：3853 通過、5 個要 root 的失敗、0 skip）。修正後沒有重跑全套（第 5.1 節），
  全套收集 3871 案。以 CI 為準。
- 帳本：`docs/provenance/runtime-patches.json` 列管 `packaging/entrypoint.py`（第一次列管）與 `restore_detect.py`，每個 commit 都同步
  更新摘要。沒動 `apps/`，tool-surface 不用重產。
- 兩個預檢：秘密預檢 0 命中；帳本預檢 0 漂移、沒有未列管的新執行期檔（第 8 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-13a（計畫 §8.4「偵測」「標記」、§12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm13a-20261114` |
| HA 基準 | `32ecac8`（`claude-delivery` @ `bb48449`＋HM-01，PR #90） |
| 依據 | 計畫 §3.3、§4.1、§7.1、§8.4、§10.1、§10.3、§11.5、§12.3、§14 #18；HM-00（PR #89）的 `docs/multi-profile/contract.md` §1.2、`threat-model.md` I9、`decisions.md` |
| 決策 | DQ-03 採 (b)：沒有帳號資料的還原不撤銷任何 token，所以建不出標記時可以照常啟動。DQ-39 採 (a)：交 HM-03a 實機驗證。沒有用到待定題。MF-1 的選項不是 DQ 題，但要負責人確認（第 12 節） |
| 對齊的 PaaS | 沒有搬程式或測試。PaaS 由還原工具（k8s Job）寫標記，HA 由 entrypoint 與開機守門處理（計畫 §8.8 #20，部署差異）。照用 PaaS `restore_marker.restore_in_progress` 的判斷：任何種類的項目都算存在，查不到答案也算 |
| FM | FM-79、FM-117、FM-126（偵測的部分；撤銷與核對是 HM-13b、HM-13c） |
| 安全審查 | `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-13a.md`（repo 外；2026-11-15，審 `b206440`） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/entrypoint.py` | `_mark_restored`：`/data/mcp` 屬 root 時、pass 1 之前，用 `/data/mcp` 的目錄 fd 以 `O_CREAT\|O_EXCL\|O_NOFOLLOW`、0600 建 `.restore-detected`，fsync 檔案與目錄；已存在、而且是單一連結的一般檔就保留。`_has_profile_data`：`profiles.json`、`profiles` 只用 lstat 查存在（任何種類都算，查不到答案也算）。建不出標記時依它決定拒絕或 WARNING；`_marker_failure` 給訊息的原因碼（審查 SF-4） |
| `packages/mcp-admin-core/mcp_admin_core/restore_detect.py`（新） | `detect(directory, enabled=...)`、`rebuild(directory, enabled=...)`、`Detection`、判定常數（第 3.2、3.3 節）。只用標準函式庫與 `config.ConfigError`、`config.strict_json` |
| `tests/test_restore_detection.py`（新） | 第 4、5、6 節 |
| `packaging/test_entrypoint.py` | 只改一個既有 root 案例的期望值：`re-owned 4` → `5`（多一個標記），並確認標記存在。本片的測試不放這裡（這一步在 CI 不是 root、允許 skip） |
| `packaging/container_probe.py` | 容器驗收的還原階段：`restore_as_supervisor`、`check_restored_start`、`restored_start`，`run()` 在第一次停機後呼叫（第 3.5 節；審查 MF-1 (a)） |
| `packaging/test_container_probe.py` | 還原階段的 mock 測試（不需 root） |
| `docs/operations/update-backup-rollback.md` | 還原修復表補「還原標記」「建不出標記」兩列，「上限」「成功」兩列註明含標記（審查 SF-3） |
| `docs/operations/acceptance.md` | 容器驗收的說明補一句還原階段 |
| `docs/provenance/runtime-patches.json` | `packaging/entrypoint.py`、`restore_detect.py` 兩筆（摘要與說明） |
| 本筆記 | — |

沒改：`apps/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、tool-surface、workflow、`run_product.py`、`apps/n8n/run.py`
（沒接線）、`packaging/container_acceptance.py`、HM-01 的守門測試與預檢工具、HM-00 的文件（在 #89）。

帳本說明：HM-00（#89）的 `docs/multi-profile/ledger-tracking.md` 第 3 節寫 `packaging/entrypoint.py`「維持現狀不列管；該片審查要求
列管時才加，決定寫進該片的 provenance 筆記」。本片在第一次改它時列管：它是每個 Dockerfile 都複製、以 root 執行的開機程式，HM-01
的帳本預檢也把它算執行期檔。安全審查同意列管（SF-5）。`ledger-tracking.md` 要把它移到「已列管」那一節（第 11 節）。

## 3. 行為

### 3.1 訊號 1：entrypoint 的標記（所有產品）

| `/data/mcp` 的情況 | 結果 |
|---|---|
| 不存在（新安裝） | 同今天：建立、交給 10001；不建標記 |
| 屬 10001（一般開機） | 同今天：不碰任何一項 |
| 屬 root（還原） | pass 1 前建標記，fsync 標記與 `/data/mcp`；接著照舊修復；`re-owned N`（N 含標記） |
| 屬 root，標記已存在（單一連結的一般檔） | 保留：同一個 inode、內容不動；仍 fsync `/data/mcp` |
| 屬 root，建不出標記，有帳號資料 | 印一行、拒絕啟動（`bootstrap unavailable`），什麼都沒改；下次開機重試 |
| 屬 root，建不出標記，沒有帳號資料 | 印一行 WARNING，繼續修復。名稱被目錄占用：修復照常完成、啟動。名稱被連結或有第二個連結的檔占用：pass 1 照既有規則拒絕（`unsupported restored entry`），不啟動 |
| 外來擁有者，或 entrypoint 不是 root | 同今天拒絕；不建標記 |

「建不出標記」包括：建檔失敗（例如沒有空間、唯讀）、fsync 失敗、名稱被目錄、連結或有第二個連結的檔占用。

兩行新訊息（stderr，原文；`<原因>` 是 errno 名稱，例如 `ENOSPC`、`EROFS`、`EIO`，或 `name in use`；不印路徑或任何值）：

```text
bootstrap: WARNING: /data/mcp was restored but its restore marker (.restore-detected) could not be saved (<原因>); starting (no profile data)
bootstrap: /data/mcp was restored with profile data but its restore marker (.restore-detected) could not be saved (<原因>); not starting (retried at the next start)
```

為什麼在 pass 1 之前（計畫 §8.4）：修復最後才改 `/data/mcp` 的擁有者。標記在那之前落盤，任何一步中斷，下次開機目錄仍屬 root，會再標記
（或找到標記）並重做修復。在 pass 1 之後、pass 2 之前建，pass 2 會因為多一個名稱拒絕開機。pass 1／pass 2 把標記當一般檔核准、改成 10001。

修復上限 512 項現在包含標記：新建標記時，還原樹本身最多 511 項（審查實驗 X1：剛好 512 項的還原樹，`32ecac8` 修得好，本片拒絕）。
實際 `/data/mcp` 只有幾項到幾十項（契約估 5 個帳號約 50 項），可以接受，已寫進 `update-backup-rollback.md`。

### 3.2 訊號 2：`restore_detect.detect(directory, enabled=開關)`

- 回傳 `Detection(marker, active, sentinel)`；`restored` ＝ 標記存在，或 `sentinel` 是還原判定。`enabled` 由呼叫端在呼叫時讀
  （HM-07 的 `features.enabled`）。
- 標記（訊號 1）一律回報，不看開關。任何種類的項目都算存在；查不到答案（不是「不存在」的錯誤）也算。
- 開關關、也沒有帳號資料（`profiles.json` 或 `profiles`，判斷同上）：`sentinel='inactive'`。只查三個名稱，不開目錄裡任何檔、
  不寫任何東西。
- 其他情況比對 `.instance-sentinel`（空檔）的 `(st_ino, st_ctime_ns)` 和 `.instance-record`。兩個數字有一個不同就是別的檔。不比 `st_dev`。

由上往下，第一個符合的列：

| sentinel | record | 帳號資料 | 判定 | 寫入 |
|---|---|---|---|---|
| 不是一般檔，或查不到答案 | 任何 | 任何 | `sentinel_invalid`：還原（中斷的建立不會留下這種東西） | 不寫 |
| 沒有 | 沒有 | 沒有 | `established`（開通後第一次啟動） | 建兩檔 |
| 一般檔 | 沒有 | 沒有 | `rebuilt`（第一次啟動在兩檔之間中斷） | 重建兩檔（新 inode） |
| 沒有或一般檔 | 沒有 | 有 | `record_missing`：還原 | 不寫 |
| 沒有或一般檔 | 讀不到、不安全或格式錯 | 任何 | `record_invalid`：還原 | 不寫 |
| 沒有 | 格式正確 | 任何 | `sentinel_missing`：還原 | 不寫 |
| 一般檔 | 格式正確，名字是別的檔 | 任何 | `mismatch`：還原 | 不寫 |
| 一般檔 | 格式正確，相符 | 任何 | `consistent` | 不寫 |

- record：嚴格 JSON（重複鍵、NaN 都拒絕），鍵剛好 `version`（1）、`st_ino`、`st_ctime_ns`（非負整數，三個都不收 bool）。檔案要是
  單一連結的一般檔、擁有者是自己、最多 4 KiB（fstat 的大小與實際讀到的都要在內），以 `O_NOFOLLOW|O_NONBLOCK` 開。兩個檔都不含秘密。
- sentinel 判還原時什麼都不寫；標記留到開機守門（HM-13b）最後才刪。所以守門中途停掉，下次開機仍偵測得到。
- 例外：還原了開通前的備份（沒有 sentinel、沒有 record、沒有帳號資料）到開關開的版本時，第一次啟動照常建兩檔
  （`established`）；這次還原靠標記偵測到（`test_a_first_start_that_finds_the_marker_still_reads_as_a_restore`）。
- 目錄打不開、或建不出 sentinel：`ConfigError`。

### 3.3 `restore_detect.rebuild(directory, enabled=開關)`（HM-13b 的最後一步用）

0. 開關關、磁碟上也沒有帳號資料：只查 `profiles.json`、`profiles` 兩個名稱就回 `ConfigError`，什麼都不寫（審查 SF-10；未開通的產品
   不會因為誤呼叫多出兩個檔）。有帳號資料（休眠）時照常重建。
1. 刪舊 sentinel。
2. 以 `O_CREAT|O_EXCL|O_NOFOLLOW`、0600 建新的，fsync 檔案，再 fsync 目錄（新 sentinel 先落盤，record 才指向它）。
3. 新 record 寫到固定暫存檔 `.instance-record.tmp`（先刪遺留的），fsync，`replace` 成 `.instance-record`，fsync 目錄。
4. 重新比對；不是 `consistent` 就 `ConfigError`。

新 record 就位之前的任何中斷，下次都判還原（`mismatch` 或 `sentinel_missing`），開機守門會重做。失敗回 `ConfigError`，並清掉暫存檔。
sentinel 或暫存檔的名稱被目錄占用時刪不掉，之後每次 `rebuild()` 都回 `ConfigError`（不會自動刪目錄；只有偽造的備份或同 uid 被攻破
會這樣；審查實驗 X9）。依計畫 §8.4，HM-13b 的開機守門這時會保留標記並停下，add-on 就起不來；HM-13b 要決定怎麼脫困（審查 SF-7：
改名隔離後重建，或寫明脫困方法）。

### 3.4 本片合併後、HM-13b 合併前（過渡期）

- 還沒有程式讀或刪標記。還原後 `.restore-detected` 會留在 `/data/mcp`：空檔、0600、10001。
- 之後的備份會帶著它；再還原時「已存在就保留」。修復時多算一項（上限見第 3.1 節）。
- 沒有 WARNING：只有建不出標記時才印第 3.1 節的兩行。計畫 §3.3、§7.1 與契約 §1.2 寫的「開機時刪掉並記一行 WARNING」是 HM-13b 的事，
  發版時 CHANGELOG 不要照抄（審查 SF-2）。
- HM-13b 第一次開機照計畫 §8.4 處理：沒開通、沒有帳號資料時，記一行 WARNING 後刪除，不改任何 state。
- `detect()`、`rebuild()` 沒人呼叫，不會建 sentinel 或 record。

可以直接貼進「HM-13b 合併前發版」的產品 CHANGELOG（審查 SF-2；英文是各產品 CHANGELOG 的語言）：

```text
- Restore detection (groundwork for multiple profiles): after Home Assistant restores this add-on's backup, the first
  start leaves an empty, owner-only marker file `.restore-detected` in `/data/mcp`, and the restore repair log line
  counts it (`re-owned N restored entries`). A later version reads and removes it; until then it stays, also in later
  backups. If the marker cannot be saved, that start logs one line with the reason (an errno name such as `ENOSPC`, or
  `name in use`); with multi-profile data on disk (none today) the start is refused and retried at the next start.
  Starts without a restore are unchanged.
```

### 3.5 容器驗收的還原階段（審查 MF-1，選項 (a)）

- 位置：`container_probe.run()` 第一次（未設定）啟動、停機之後，設定 fixture 之前。fixture 只在停機時改（探針既有規則）。
- `restore_as_supervisor()`：先確認每一項都是一般目錄或單一連結的一般檔、還沒有標記（不合就什麼都不改、直接失敗）；再把
  `/data/mcp` 整棵 `chown 0:0`、檔案 0644、底下的目錄 0755（2026-10-05 HA 實測看到的樣子）。回傳還原項目的名稱與 `state.json` 的位元。
- `restored_start()`：用真映像啟動（entrypoint 以 root 執行 → 修復 → 降權 → exec 管理程序）；`ready_listener` 照舊驗 uid／gid 10001、
  NoNewPrivs、CapEff 0、`/data/mcp` 10001／0700、`state.json` 10001／0600；`check_restored_start()` 另驗標記存在（空檔、單一連結、
  10001、0600）、每個還原項目改回 10001（目錄 0700、檔案 0600）、`state.json` 位元不變；最後停機（檢查失敗也停）。
- 之後的流程不變：標記留在 `/data/mcp`，`fixture_snapshot()` 照收（一般檔、最多 16 項）。
- 誰跑：每個產品下一次發版時，builder 的 `supply_chain.py candidate` → `container_acceptance.py` 都會跑。本波不跑 builder，真容器沒有驗過；
  多一次未設定的啟動與停機，`docker run` 上限 180 秒內（推估多幾秒）。
- 本機的保證：`packaging/test_container_probe.py`（mock）與 `tests/test_restore_detection.py` 的兩案（同一段還原與檢查夾著真的
  entrypoint：一般使用者用 VirtualRoot，CI 以 root 用真的擁有者）。
- HM-13b 合併後，守門會在這次啟動就刪掉標記：HM-13b 要同時把探針的標記斷言改成它的新行為（第 11 節）。

## 4. 守門有效的證據

### 4.1 先紅後綠

先寫測試，再分兩步實作：

| 階段 | 結果 |
|---|---|
| 只有新測試（沒有 `restore_detect.py`、entrypoint 未改） | 收集失敗：`ImportError: cannot import name 'restore_detect'` |
| 有 `restore_detect.py`，entrypoint 未改 | 37 失敗、84 通過。失敗的是 33 個標記案例與 4 個 root 案例；通過的是全部 sentinel 案例，與今天就該成立的零變化案例 |
| entrypoint 改完 | 117 通過；只剩 4 個 root 案例（本機故意失敗） |
| 補 `st_dev` 案例後 | 118 通過、4 個 root 案例 |
| 補「sentinel 不是一般檔、record 也不在」3 案 | 原本先看 record 的順序有 2 案失敗：名稱是目錄時被當成「建立中斷」去重建、刪不掉而 `ConfigError`；是連結時被重建。改成先判 sentinel 的型別後 121 通過、4 個 root 案例 |
| 第 4 個 commit：補「開通前的備份還原到開關開的版本」1 案（2026-11-15） | 特性測試，鎖住現有行為，直接通過（122 通過、4 個 root 案例）；程式只改模組說明 |
| 2026-11-15 用最終的測試檔重做一次（暫存區複本，`--noconftest`） | 沒有 `restore_detect.py`：收集失敗；有它、entrypoint 用 `32ecac8` 的版本：38 失敗、88 通過；entrypoint 用本分支的版本：122 通過、4 個 root 案例 |
| 審查修正後（2026-11-15，暫存區複本，最終測試檔） | entrypoint 換回 `b206440`（訊息沒有原因）：24 個非 root 案例失敗；`restore_detect.py` 換回 `b206440`（`rebuild()` 沒有 `enabled`）：23 個失敗；entrypoint 換回 `32ecac8`（沒有標記）：39 個失敗，含容器還原階段那案。本分支：134 通過、5 個 root 案例 |

### 4.2 臨時突變

都在暫存區的複本一次改一處、跑相關測試，跑完用 git 還原並比對摘要；沒有 commit。「被擋」＝至少一個非 root 案例失敗（容器探針的突變
另跑 `packaging/test_container_probe.py`）。

作者的 26 個（2026-11-15 在第 4 個 commit 上重跑全部）：

| 突變 | 新增失敗 |
|---|---|
| E1 標記改在修復之後才建 | 33 |
| E2 不 fsync 標記 | 5 |
| E3 不 fsync `/data/mcp` | 6 |
| E4 拿掉 `O_EXCL` | 1 |
| E5 標記用 0644 建 | 1 |
| E6 名稱被任何東西占用都當成標記 | 6 |
| E7 建不出標記一律拒絕 | 6 |
| E8 建不出標記一律照常啟動 | 14 |
| E9 查不到答案當成沒有帳號資料 | 2 |
| E10 一般開機也建標記 | 29 |
| R1 只比 inode | 25 |
| R2 也比 `st_dev` | 1 |
| R3 不符時也重建 | 27 |
| R4 沒開通時也讀 record | 4 |
| R5 忽略帳號資料 | 11 |
| R6 有帳號資料時仍重建「只有 sentinel」 | 1 |
| R7 不查 record 的擁有者 | 1 |
| R8 不查 record 的連結數 | 1 |
| R9 跟隨連結讀 record | 1 |
| R10 寫 record 前不 fsync 目錄 | 4 |
| R11 忽略標記 | 9 |
| R12 查不到答案當成不存在 | 3 |
| R13 版本收 bool | 1 |
| R14 重建後不再比對 | 1 |
| R15 sentinel 的型別改回在 record 之後才判 | 2 |
| R16 有標記時第一次啟動不建兩檔 | 1 |

安全審查另做 55 個（審查報告第 6 節）：50 個被擋，5 個沒被擋（R03、R14 等價；R16、E19、E20 結果仍安全），R13 以卡住 120 秒才算被擋。
審查後補測試，在最終的程式上重跑那 6 個，並對修正本身另做 14 個（2026-11-15，編號沿用審查報告；未修改的複本先跑一次，全過）：

| 突變 | 結果 |
|---|---|
| E19 查帳號資料時跟隨連結（懸空的 `profiles` 連結算沒有） | 被擋，1 案 |
| E20 有兩個連結的舊標記也照收 | 被擋，3 案 |
| E21 訊息不帶原因 | 被擋，24 案 |
| E22 原因印錯誤本身的文字（含檔名） | 被擋，15 案（注入的錯誤帶檔名） |
| E23 每種失敗都說 `name in use` | 被擋，15 案 |
| R03 只比 ctime | 被擋，1 案（ctime 相同、inode 不同） |
| R13 讀 record 不帶 `O_NONBLOCK` | 被擋，1 案；5 秒期限到就失敗，整個檔 6.4 秒跑完，不再卡住 |
| R14 拿掉 `st_size` 檢查 | 被擋，1 案（fstat 報的大小超過上限） |
| R16 `st_ino`、`st_ctime_ns` 收 bool | 被擋，2 案 |
| R36 `rebuild()` 不查是否 active | 被擋，1 案 |
| R37 `rebuild()` 只看開關（休眠帳號被拒） | 被擋，2 案 |
| P1 `run()` 不跑還原階段 | 被擋（packaging：原始碼位置的那案） |
| P2 還原時不改成 root | 被擋（packaging 1 案；tests 1 案：entrypoint 不修復，數字不符） |
| P3 檢查不看標記 | 被擋（packaging 5 案） |
| P4 檢查不看還原項目 | 被擋（packaging 2 案） |
| P5 檢查失敗時不停機 | 被擋（packaging 1 案） |
| P6 還沒檢查完就開始改擁有者 | 被擋（packaging 2 失敗、1 錯誤） |
| P7 還原時不改模式 | 被擋（packaging 1 案） |
| P8 標記不是 10001／0600 也接受 | 被擋（packaging 2 案） |
| P9 不比 `state.json` 的位元 | 被擋（packaging 1 案） |

### 4.3 root 案例的邏輯（本機）

原本 4 個 `test_root_*` 在本機另跑過一次：拿掉 `require_root()`，真的 chown 與 fork 成 uid 10001 換成虛擬擁有者表（同第 5 節的
VirtualRoot），其他照原樣。4 案通過（2026-11-15 在第 4 個 commit 上重跑，仍 4 案通過）。新的 root 案例
`test_root_the_container_probes_restore_stage_meets_the_entrypoint` 的邏輯和它的一般使用者版本
`test_the_container_probes_restore_stage_meets_the_entrypoint` 相同（同一段還原、真的 entrypoint、同一個檢查），只把虛擬擁有者換成
真的 chown。這只驗測試本身的邏輯；真的擁有者與 uid 10001 的存取只有 CI 驗得到（第 6 節）。本機也沒辦法用 user namespace 模擬 root
（這台機器的 AppArmor 擋掉非特權 user namespace）。

## 5. 本機檢查（2026-11-15，最終 HEAD；一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

| 檢查 | 結果 |
|---|---|
| `tests/test_restore_detection.py`（139 案） | 134 通過、5 失敗（`test_root_*`，都停在 `require_root()`）；0 skip；約 1.3 秒 |
| HM-01 守門（`test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`、`test_tool_inventory`、`test_ledger_precheck`、`test_secret_precheck`） | 74 通過 |
| `tests/test_migration_preview.py`（複製整個核心套件、跑遷移模組的那一案也在裡面） | 226 通過 |
| 全套收集（`--collect-only tests`） | 3871 案（本檔 139 案） |
| 全套 pytest（`tests/`） | 見第 5.1 節 |
| `packaging/validate.py`（CI 的 PyYAML） | PASS |
| packaging unittest（`discover -s packaging`；PyYAML 照 CI 另外提供，放在 `PYTHONPATH`，沒動 `.venv`） | `Ran 191`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `packaging/test_container_probe.py` 換成有 setgid 的 TMPDIR 再跑 | 10 案 OK（fixture 自己清掉 setgid 位元） |
| `scripts/tool_inventory.py`（漂移檢查） | 通過 |
| 先紅後綠、臨時突變、root 案例的邏輯 | 第 4 節 |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨 |

`tests/conftest.py` 的本機測試鎖這段期間一直被別的代理的全套 pytest 占著，所以上面的 pytest 都用 `--noconftest`，另外載一個和
conftest 一樣裝網路與子程序守門（`owned_network.install()`、`install_subprocess_guard()`）、只是不拿鎖的外掛；只跑不綁固定 port 的檔。

訊號 1 的案例用 VirtualRoot 以一般使用者執行：它是 entrypoint 自己的 `os` 模組，`geteuid()` 回 0，擁有者記在每個 inode 上
（本使用者擁有、又沒 chown 過的 inode 當成 root 的）；chown 只改這張表。mode、名稱、內容、fsync 與呼叫順序都是真的。CI 以 root
跑同一批案例，結果相同（擁有者一樣只記在表上）。

### 5.1 全套 pytest

結論：審查修正前，3858 案在第 4 個 commit（`4aae8ea`）上都跑過：3853 通過、5 失敗、0 skip。5 個失敗都要 root：本片 4 個 `test_root_*`
與既有的 `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（同基準）。

每次都用 wave1 鎖包住。因為和其他代理同時在跑，分成幾段才跑完：

| 次 | 時間（11-15） | 結果 |
|---|---|---|
| 1 | 00:52 | 3858 案全部 error：其他代理的測試占著 `tests/conftest.py` 的本機測試鎖超過 120 秒（`LOCAL TEST lock busy`），一案都沒跑到 |
| 2 | 00:58～01:14 | 照收集順序跑到第 2343 案（前 98 個檔，59%），全部通過；第 2344 案（`test_output_schema_runtime.py` 第一案）跑到一半時，pytest 被外部送來的 SIGTERM 終止（exit 143；不是測試失敗，來源查不到） |
| 3 | 02:28～02:41 | 補跑剩下的 46 個檔（1515 案）：1488 通過、27 失敗。其中 22 個是 `test_owned_browser_ipc.py`、`test_owned_browser_redirect.py`、`test_owned_ui.py[browser]`：這個 clone 還沒裝 Playwright 的 Chromium（CI 的 `packaging/unit.sh` 在 pytest 前會跑 `npm run browser:install`），不是程式問題；另 5 個是上面說的 root 案例 |
| 4 | 02:43～02:44 | 照 CI 跑 `npm run browser:install --prefix packages/mcp-admin-ui` 後，重跑那 3 個檔：52 案全部通過 |

審查修正後沒有重跑全套：11-15 04:00 wave1 鎖前面還有 4 個代理在排（每個約 30～40 分鐘）。修正只動到：entrypoint 還原分支的兩行訊息、
`restore_detect.rebuild()`（執行期沒有呼叫者）、只在 builder 跑的容器探針、測試與文件；改到的路徑都由第 5 節的測試直接跑到，全套收集
也正常。全套以 CI（root、0 skip）為準。

HM-01 的黃金回歸與契約凍結（`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`）在兩次
都通過。

## 6. 只在 CI 跑的測試

- 新測試（5 案）：`test_root_backup_restore_and_repair`、`test_root_start_without_a_restore_changes_nothing`、
  `test_root_marker_name_taken_by_a_directory[None]`、`[index]`、`test_root_the_container_probes_restore_stage_meets_the_entrypoint`。
  用真的擁有者跑：root 擁有的還原樹、真的 chown 成 10001、名稱被目錄占用、容器探針的還原階段夾著真的 entrypoint；前兩案再在 fork 出來
  的 uid 10001 子程序（同管理程序的身分）確認：看得到標記、讀得到 record、判得出 `mismatch`、重建得了 sentinel、載得入預設 state。
  本機一般使用者執行會在 `require_root()` 失敗，不會 skip。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root，和基準相同）。
- `packaging/test_entrypoint.py::RestoredStateTests::test_root_owned_restore_is_reowned_once`：本片改了期望值，但它在 CI 的
  packaging 步驟也 skip（那一步不是 root），所以哪裡都不會跑。同樣的情境由上面的 root 案例在 CI 驗。
- 容器驗收（真的映像、真的 `/data` 掛載、真的 entrypoint → 降權 → 管理程序）：不在 GitHub CI。每個產品下一次發版時由 builder 的
  `container_acceptance` 跑第 3.5 節的還原階段；本波不跑 builder，所以還沒有真容器的結果。

## 7. `checks` 秒數

- 前、後：開 PR 後補（PR 的 CI 跑完後寫進 PR 說明）。
- 推估：新測試本機約 1.3 秒，packaging 測試多約 1.5 秒；CI 增加約 3～5 秒，在每片 1.5 分鐘的預算內。

## 8. 預檢結果

指令照 HM-01 筆記第 8 節。2026-11-15 在本筆記 commit 之後、以最終的 HEAD 跑。

- **秘密預檢**：gitleaks 8.28.0（壓縮檔 SHA-256 與 `packaging/scanner-pins.json` 的 `a65b5253…40eb` 相符，執行檔摘要相符）；設定是本
  repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本分支的 commit（`bb48449..HEAD`，git 模式；HM-01 的 9 個＋本片 10 個，含本筆記） | 0 |
  | 本片的 commit（`32ecac8..HEAD`，10 個） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

- **帳本預檢**（`scripts/ledger_precheck.py`）：`runtime-patches.json` 154 個路徑、`runtime-sources.json` 70 個、`tool-surface.json`
  159 個，都 0 漂移、0 缺檔、0 個要 CI 安裝才有的檔。對 `origin/claude-delivery`（`bb48449`）改了 27 個檔（HM-01 的 17 個＋本片 10 個）：
  列管檔 2 個（`packaging/entrypoint.py`、`restore_detect.py`）、帳本 1 個（`runtime-patches.json`）；新增而沒列管的執行期檔 0 個、
  改到而沒列管的執行期檔 0 個。結果 OK。對 `32ecac8` 是 10 個檔，結果相同。
- 每個 commit 的帳本摘要都等於當下兩個檔的 SHA-256（逐 commit 核對過）。

## 9. PaaS 變動

- 本片沒有搬 PaaS 程式或測試。HM-00（#89）的對照表把 PaaS `restore_marker.py` 對到本片（#89 的
  `docs/provenance/multi-profile-parity-baseline.md` 第 2 節；這個檔與 `docs/multi-profile/*` 在 #89，本分支還沒有）；它在 pin `69ac425`
  與 `7d111b1` 之間沒有變動（同文件第 3 節，2026-11-14 16:07 的檢查）。
- 開 PR 前在連得到 Gitea 的 PaaS clone 重跑同文件第 4 節的指令，結果補進 PR 說明（開 PR 後補）。
- HM-00 `paas-test-mapping.md` 歸給本片的 PaaS 案例與本片對應：

  | PaaS 案例 | 本片 |
  |---|---|
  | `test_restore_inplace.py::test_volume_root_owner_rule` | `test_only_data_that_comes_back_root_owned_is_marked` |
  | `test_restore_inplace.py::test_overlapping_run_is_refused_while_another_holds_the_marker` | `test_a_marker_already_there_is_kept_as_it_is` |
  | `test_restore_marker.py::test_marker_detection_fails_closed` | `test_with_profile_data_a_restore_without_its_marker_does_not_start`、`test_a_profile_data_check_that_cannot_rule_it_out_counts_as_profile_data`、`test_any_entry_under_those_names_counts` |
  | `test_restore_marker.py` 的「標記讓啟動失敗」5 案（`test_marker_refuses_startup_before_migration_token_and_children` 等） | 本片：標記在管理程序啟動前就在（`test_a_restore_saves_the_marker_durably_before_pass_1`、`test_a_backup_restored_by_supervisor_shows_both_signals`、`test_root_backup_restore_and_repair`）。listener 之前的守門是 HM-13b |
  | `test_restore_guard.py::test_n8n_incomplete_or_unsafe_backup_never_starts` | 計畫 §8.8 #20：不安全的還原樹由既有修復拒絕；本片補「拒絕時標記仍在」（`test_a_refused_restore_keeps_its_marker`）與「名稱被連結或有第二個連結的檔占用就不啟動」（`test_a_link_in_the_markers_name_never_starts`） |

## 10. 驗收條件（計畫 §12.3 HM-13a）

| 條件 | 狀態 |
|---|---|
| 全綠 | 本機：一般使用者能跑的全部通過（第 5 節；全套在修正前跑過，第 5.1 節）。CI（root、0 skip）待 PR |
| 未開通、沒有帳號資料的產品在沒有還原時零變化 | 通過：entrypoint 的一般開機不碰任何一項（`test_a_start_without_a_restore_changes_nothing`；root 版 `test_root_start_without_a_restore_changes_nothing` 在 CI）；`detect()` 只查三個名稱、不開檔不寫檔（`test_a_product_that_is_not_enabled_and_has_no_profile_data_is_left_alone`）；`rebuild()` 在這種情況拒絕、不寫（`test_a_rebuild_is_only_for_an_active_product`）；沒有接進執行期。HM-01 黃金回歸（8 個產品的資料目錄不變）通過 |
| 每個產品下一次發版的容器驗收跑 root 還原樹 | 本片補上容器探針的還原階段（第 3.5 節；審查 MF-1 選項 (a)，**開 PR 前要負責人確認**）。真容器在下一次發版的 builder 驗收才跑 |
| 獨立安全審查 | 完成：「修正後通過」（必修 1、建議 10），處理見第 12 節 |
| 測試放 `tests/`、CI 以 root 跑、0 skip，不放 `packaging/test_entrypoint.py` | 通過：新測試沒有 `skip`／`skipif`／`xfail`；root 案例用斷言要求 root。`packaging/test_container_probe.py` 只放 mock（計畫 §10.1） |
| 同 PR 更新帳本 | 通過（第 2、8 節；每個 commit 都同步） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 一律執行時產生；state 用 `{"restored": true}`、`{"fixture": true}` 這類不含秘密的位元；record 只有整數；秘密預檢見第 8 節 |

## 11. 交接與還沒解決的事

- **開 PR 前（主對話）**：MF-1 的選項請負責人確認（第 12 節）。選 (b) 或 (c) 時，整個拿掉 `test(packaging): restore /data/mcp as
  Supervisor does in the container probe (HM-13a)` 這個 commit，改寫本筆記第 3.5、6、10、11、12 節與 PR 說明。另外，計畫 §10.1 寫
  「多帳號與 root 還原樹階段只在開通的候選映像跑」，和 §3.3、§11.5、§12.3、§14 #18 不一致；照 (a) 可以讀成「多帳號（含 sentinel）
  的 root 還原樹是 HM-16、只在開通的候選映像跑；單帳號的 root 還原樹（本片）每個映像都跑」，請一併改計畫文字。
- **HM-13b**：把 `detect()` 接進開機順序（legacy 遷移之後、任何 listener 與子程式之前），`enabled` 用 `features.enabled(product)`
  在呼叫時讀；`restored` 時跑守門，最後 `rebuild(directory, enabled=...)`、再刪標記；沒開通、沒有帳號資料時記一行 WARNING 後刪標記。
  另加測試掃描所有 chmod／chown 呼叫點，確認碰不到 sentinel。
  - 守門刪標記之後，`container_probe.check_restored_start()` 的「標記還在」要改成新行為（例如標記已刪、state 不變）。
  - sentinel 或 `.instance-record.tmp` 的名稱被目錄占用時，`rebuild()` 每次都失敗、add-on 起不來（審查 SF-7、X9）：改名隔離後重建，
    或寫明脫困方法。
  - 本片先發、HM-13b 還沒發的期間，還原留下的標記會一直在；開通的產品第一次開機遇到這種舊標記也會跑一次守門（沒有帳號資料時依
    DQ-03 (b) 不撤銷、只發通知），HM-13b、HM-13c 的通知文字要涵蓋這種情況。
- **HM-16**：容器探針的多帳號階段（含 sentinel 的 root 還原樹）接在本片的還原階段之後；`docker run` 180 秒上限要跟著看。
- **各產品的發版**：HM-13a 合併後第一個發版的產品，builder 容器驗收第一次真的跑第 3.5 節；失敗時先查探針與 entrypoint，不要放寬檢查。
  CHANGELOG 用第 3.4 節的段落，不要照抄計畫 §3.3 的表（那是 HM-13b 之後的行為）。
- **HM-03a**（實機，還沒做）：在 QA HAOS 做 full、partial、加密備份各一次還原，確認 `/data/mcp` 屬 root、標記建立、sentinel 判
  `mismatch`；sentinel 的 ctime 在 add-on 重啟、**主機重開**、add-on 更新、Supervisor 更新後不變（UC-08、UC-25）。本片所有測試都在
  同一次開機內，sentinel 的 inode 沒有離開過快取（審查 SF-9）：UC-25 一定要包含主機重開，記下資料分割的檔案系統與 inode 大小，
  重開前後比對 record 與 `lstat`；奈秒不穩時再評估只比到秒的備案。結果在 HM-13b 合併前寫回。若某種還原兩個訊號都不觸發，照
  DQ-39 (a) 不出貨、先修偵測。
- **HM-07**：`profiles.json`、`profiles/` 的名稱要和 HM-07 的布局常數一致。HM-07 依波 1 順序先合（HM-04 → HM-06 → HM-07 → HM-13a），
  本 PR rebase 時就在 `test_the_entrypoint_and_the_detection_use_the_same_names` 加斷言，或讓 `restore_detect` 直接引用 HM-07 的常數
  （entrypoint 只能用標準函式庫，保留自己那份，由測試比對；審查 SF-1）。
- **HM-00 `ledger-tracking.md`**：第 3 節要把 `packaging/entrypoint.py` 移到「已列管」（#89 合併前或 HM-18；審查 SF-5）。
- **HM-18**：DOCS 寫兩行訊息每種原因怎麼處理（`ENOSPC`：清出空間；`EROFS`、`EIO`：查儲存；`name in use`：還原別份備份）；契約布局
  補 `.instance-record.tmp`（SF-7）；已知限制寫進文件：區塊層級的回滾（例如虛擬機快照還原）帶回同一個 inode 與 ctime、擁有者也不變，
  兩個訊號都看不到，本片只涵蓋 Supervisor 的檔案層級還原（計畫 §8.9 的延伸）。

## 12. 審查意見處理（`wave1/review-HM-13a.md`，判定「修正後通過」）

| id | 處理 | 在哪裡 |
|---|---|---|
| MF-1 容器驗收的 root 還原樹沒有落地方法 | 處理：採選項 (a)，本片補容器探針的還原階段與 mock 測試，另在 `tests/` 夾著真的 entrypoint 跑（含 CI 的 root 版）。審查要求由負責人選 (a)／(b)／(c)：**開 PR 前請確認**；選 (b)、(c) 時拿掉該 commit（第 11 節）。計畫 §10.1 的文字請主對話一併改 | `packaging/container_probe.py`、`packaging/test_container_probe.py`、`tests/test_restore_detection.py`、`docs/operations/acceptance.md`；第 3.5 節 |
| SF-1 rebase 時鎖住帳號資料的名稱 | 留到 rebase：HM-07 還沒合併，現在沒有它的常數可以比 | 第 11 節（HM-07） |
| SF-2 過渡期行為與計畫不同，CHANGELOG 不能照抄 | 處理：可直接貼的 CHANGELOG 段落 | 第 3.4 節；PR 說明 |
| SF-3 操作文件的還原修復表沒跟上 | 處理：加「還原標記」「建不出標記」兩列，「上限」「成功」註明含標記 | `docs/operations/update-backup-rollback.md` |
| SF-4 建不出標記的訊息不說原因 | 處理：同一行加原因碼（errno 名稱或 `name in use`），不含路徑或值；各原因的處理方式交 HM-18 | `packaging/entrypoint.py`；第 3.1 節 |
| SF-5 HM-00 `ledger-tracking.md` 要改 | 不在本分支（#89）；交主對話（#89 合併前）或 HM-18 | 第 11 節 |
| SF-6 provenance 第 3.1 節、entrypoint 註解、引用 #89 的文件 | 處理：第 3.1 節分開寫「名稱被目錄占用」與「被連結或多重連結占用」；註解改成 sentinel 只看得到「開通後做的備份」；本筆記與帳本說明註明那些文件在 #89 | 第 3.1、9 節；`packaging/entrypoint.py`；帳本 |
| SF-7 名稱被目錄占用時 `rebuild()` 一直失敗 | 留給 HM-13b（守門怎麼脫困）與 HM-18（契約布局補 `.instance-record.tmp`）；本片 `rebuild()` 沒有呼叫者 | 第 3.3、11 節 |
| SF-8 測試缺口（R16、E19、E20、R03、R14、R13 卡住） | 處理：補 bool inode／ctime、懸空 `profiles` 連結、有兩個連結的標記、inode／ctime 各自不同、fstat 大小超過上限；FIFO 案例加 5 秒期限。6 個都改成被擋 | `tests/test_restore_detection.py`；第 4.2 節 |
| SF-9 重開機後 ctime 是否穩定 | 交 HM-03a：UC-25 一定包含主機重開，記錄檔案系統與 inode 大小、重開前後比對 | 第 11 節（HM-03a） |
| SF-10 `rebuild()` 沒擋未開通、沒有帳號資料的呼叫 | 處理：`rebuild(directory, enabled=...)` 不是 active 就 `ConfigError`、不寫 | `restore_detect.py`；第 3.3 節 |
