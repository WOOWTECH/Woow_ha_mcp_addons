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
- 2026-11-15 rebase 兩次：先到 `e5fa5c7`（#89～#93：HM-00、HM-01、HM-04、HM-17、HM-07），沒有衝突；HM-06（#94）與 HM-05（#95）合併後
  再到 `8e02ac1`，只有 `packaging/test_container_probe.py` 文字衝突（兩邊都加測試，兩邊都留）。帳本兩次都以 `claude-delivery` 的為底、
  加回本片條目，每個 commit 都用當下的實際內容核對摘要（第 2.1 節）。
- 檔名只有一個來源（審查 SF-1）：HM-07 的 `profiles.py` 用模組常數定義，`Layout` 用它們組路徑；`restore_detect.py` 與容器探針
  import 它們。`packaging/entrypoint.py` 只能用標準函式庫，留一份副本，由測試鎖住；它仍然不 import 任何核心模組（第 3.6 節）。
- 零改寫測試：屬於本片的部分已做：8 個產品的 `bb48449` 樣本，開關關時還原檢查什麼都不改；開關開的第一次只多 sentinel 兩檔。
  正式 runtime 開機時「開通後只多 sentinel 兩檔」要等 HM-13b 接線，寫進交接（第 3.7、11 節）。
- 容器驗收：`packaging/container_probe.py` 多一段「Supervisor 式還原後的啟動」（審查 MF-1，主對話 2026-11-15 定案照選項 (a)）。
  每個產品下一次發版的 builder 容器驗收都會跑；真容器第一次跑是 HM-19a 前的 builder 乾跑，不是本片的合併關卡（第 3.5、11 節）。
- HM-03a 的實機探針（UC-08、sentinel 的 ctime 穩定性）還沒做。本片照設計實作；實機結果在 HM-13b 合併前寫回（第 11 節）。
- 獨立安全審查判「修正後通過」（必修 1、建議 10）。必修與建議的處理見第 12 節。
- 本機檢查（第二次 rebase 後，第 5 節）：`tests/test_restore_detection.py` 139 案：134 通過；5 案 `test_root_*` 只在 CI（root）驗，
  本機執行會在第一行失敗，不會 skip。HM-07 的帳號資料層與零改寫測試、HM-05 的 `test_profile_runtime.py`、HM-06 的
  `test_child_bearer.py`、HM-01 守門全部通過（另 1 個 HM-07 既有、要 root 的案例只在 CI 驗）；packaging unittest `Ran 201`、
  `OK (skipped=5)`；`packaging/validate.py` PASS。全套 pytest 沒跑（主對話說不用跑），以 CI 為準。
- 守門有效：先紅後綠有紀錄；本片的突變共 46 個（作者 26、審查後補 20）全部被擋；收斂與零改寫測試另做 12 個，也全部被擋（第 4.4 節）。
- 帳本：`docs/provenance/runtime-patches.json` 列管 `packaging/entrypoint.py`（第一次列管）與 `restore_detect.py`；收斂改到 HM-07 的
  `profiles.py`，三個摘要照合併後的內容重算。每個 commit 都同步。沒動 `apps/`，tool-surface 不用重產。
- 兩個預檢（對 `origin/claude-delivery` @ `8e02ac1`）：秘密預檢 0 命中；帳本預檢 OK（第 8 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-13a（計畫 §8.4「偵測」「標記」、§12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm13a-20261114` |
| HA 基準 | `8e02ac1`（`claude-delivery`，已含 #89 HM-00、#90 HM-01、#91 HM-04、#92 HM-17、#93 HM-07、#94 HM-06、#95 HM-05）。原本從 `32ecac8`（HM-01 的舊 head）開分支，2026-11-15 先 rebase 到 `e5fa5c7`、再 rebase 到 `8e02ac1`（第 2.1 節） |
| 依據 | 計畫 §3.3、§4.1、§7.1、§8.4、§10.1、§10.3、§11.5、§12.3、§14 #18；HM-00（#89）的 `docs/multi-profile/contract.md` §1.2、`threat-model.md` I9、`decisions.md`；HM-07（#93）的 `profiles.Layout` 與 `tests/test_upgrade_zero_rewrite.py` |
| 決策 | DQ-03 採 (b)：沒有帳號資料的還原不撤銷任何 token，所以建不出標記時可以照常啟動。DQ-39 採 (a)：交 HM-03a 實機驗證。沒有用到待定題。MF-1 的選項不是 DQ 題，主對話 2026-11-15 定案照 (a)（第 12 節） |
| 對齊的 PaaS | 沒有搬程式或測試。PaaS 由還原工具（k8s Job）寫標記，HA 由 entrypoint 與開機守門處理（計畫 §8.8 #20，部署差異）。照用 PaaS `restore_marker.restore_in_progress` 的判斷：任何種類的項目都算存在，查不到答案也算 |
| FM | FM-79、FM-117、FM-126（偵測的部分；撤銷與核對是 HM-13b、HM-13c） |
| 安全審查 | `artifacts/ha-multiprofile-parity-20261114/wave1/review-HM-13a.md`（repo 外；2026-11-15，審 `b206440`） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/entrypoint.py` | `_mark_restored`：`/data/mcp` 屬 root 時、pass 1 之前，用 `/data/mcp` 的目錄 fd 以 `O_CREAT\|O_EXCL\|O_NOFOLLOW`、0600 建 `.restore-detected`，fsync 檔案與目錄；已存在、而且是單一連結的一般檔就保留。`_has_profile_data`：`profiles.json`、`profiles` 只用 lstat 查存在（任何種類都算，查不到答案也算）。建不出標記時依它決定拒絕或 WARNING；`_marker_failure` 給訊息的原因碼（審查 SF-4）。2026-11-15 只改說明與註解：`MARKER`、`PROFILE_DATA` 是 `profiles` 檔名常數的副本（第 3.6 節） |
| `packages/mcp-admin-core/mcp_admin_core/restore_detect.py`（新） | `detect(directory, enabled=...)`、`rebuild(directory, enabled=...)`、`Detection`、判定常數（第 3.2、3.3 節）。只用標準函式庫、`config.ConfigError`、`config.strict_json` 與 `profiles` 的檔名常數（2026-11-15 起；第 3.6 節） |
| `packages/mcp-admin-core/mcp_admin_core/profiles.py`（HM-07） | 布局的檔名改成模組常數，只寫在這裡（`INDEX_NAME`、`INDEX_OPERATIONS_NAME`、`PROFILES_NAME`、`PROFILE_DATA_NAMES`、`SENTINEL_NAME`、`INSTANCE_RECORD_NAME`、`INSTANCE_RECORD_TEMPORARY_NAME`、`RESTORE_MARKER_NAME`、`REVOKE_ALL_MARKER_NAME`、`RESTORE_RECORD_NAME`）；`Layout`、`has_profile_data`、`index_quarantine_name` 改用它們。值與行為不變（第 3.6 節） |
| `tests/test_restore_detection.py`（新） | 第 4、5、6 節；名稱測試 2026-11-15 擴充（第 3.6 節） |
| `tests/test_upgrade_zero_rewrite.py`（HM-07） | `UNWIRED` 加 `restore_detect`（它 import `profiles`，自己也還沒接線）；新測試：8 個產品的 `bb48449` 樣本上跑還原檢查（第 3.7 節）；建 `/data/mcp` 的幾行抽成 `installed()`，兩個測試共用 |
| `packaging/test_entrypoint.py` | 只改一個既有 root 案例的期望值：`re-owned 4` → `5`（多一個標記），並確認標記存在。本片的測試不放這裡（這一步在 CI 不是 root、允許 skip） |
| `packaging/container_probe.py` | 容器驗收的還原階段：`restore_as_supervisor`、`check_restored_start`、`restored_start`，`run()` 在第一次停機後呼叫（第 3.5 節；審查 MF-1 (a)）。標記名稱 2026-11-15 起 import 自 `profiles` |
| `packaging/test_container_probe.py` | 還原階段的 mock 測試（不需 root） |
| `docs/operations/update-backup-rollback.md` | 還原修復表補「還原標記」「建不出標記」兩列，「上限」「成功」兩列註明含標記（審查 SF-3） |
| `docs/operations/acceptance.md` | 容器驗收的說明補一句還原階段 |
| `docs/provenance/runtime-patches.json` | `packaging/entrypoint.py`、`restore_detect.py` 兩筆（摘要與說明）；`profiles.py` 那筆（HM-07）重算摘要、補說明 |
| 本筆記 | — |

沒改：`apps/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、tool-surface、workflow、`run_product.py`、`apps/n8n/run.py`
（沒接線）、`packaging/container_acceptance.py`、HM-01 的守門測試與預檢工具、`docs/multi-profile/*`（HM-00 的文件）。

帳本說明：HM-00（#89，已合併）的 `docs/multi-profile/ledger-tracking.md` 第 3 節寫 `packaging/entrypoint.py`「維持現狀不列管；該片審查
要求列管時才加，決定寫進該片的 provenance 筆記」。本片在第一次改它時列管：它是每個 Dockerfile 都複製、以 root 執行的開機程式，HM-01
的帳本預檢也把它算執行期檔。安全審查同意列管（SF-5）。`ledger-tracking.md` 由主對話的同步 PR #96（只改 `docs/multi-profile/`）
改成「`packaging/entrypoint.py`：HM-13a 起列管」；本片不改那份文件（第 11 節）。

### 2.1 rebase 與帳本（2026-11-15）

第一次（到 `e5fa5c7`）：

- `git fetch origin claude-delivery`：`bb48449..e5fa5c7`。`git rebase --onto origin/claude-delivery 32ecac8`：本片 10 個 commit 都套上，
  沒有衝突（`claude-delivery` 這段沒有動到本片改的任何一個程式或測試；兩邊都改的只有 `runtime-patches.json`，改在不同位置）。
  rebase 前的 head 是 `37f2a31`。
- 帳本不是只看文字合併：以 `claude-delivery` 的 54 筆為底（HM-07 新增 `features.py`、`profiles.py`、`identity_fields.py`、`config.py`；
  HM-04、HM-07 改了 7 筆），加回本片的 2 筆（位置不變）；rebase 後 `scope` 與那 54 筆和 `claude-delivery` 逐字相同（收斂的 commit
  才改 `profiles.py` 那筆）。逐 commit 核對：每個 commit 上，帳本列的每個檔（有進 git 的）都等於該 commit 裡檔案的 SHA-256；本片全部
  commit 0 漂移。
- 收斂的 commit 改了 `profiles.py`、`restore_detect.py`、`packaging/entrypoint.py`，三個摘要照改後的內容重算，說明各補一句。
- tool-surface：本片沒動 `apps/runtime/*.py`、`apps/*/launch.py`；rebase 帶進來的 HM-04 改動（hermes、opendesign 的 `launch.py`）
  在 `claude-delivery` 已經重產過。`scripts/tool_inventory.py`（檢查模式）通過，不用重產。
第二次（HM-06、HM-05 合併後，到 `8e02ac1`）：

- `git fetch origin claude-delivery`：`e5fa5c7..8e02ac1`（#94 HM-06、#95 HM-05，17 個 commit）。
  `git rebase --onto origin/claude-delivery e5fa5c7`：只重放本片的 13 個 commit。第一次 rebase 後的 head 是 `c328974`。
- 兩邊都改的檔：`runtime-patches.json`、`packaging/container_probe.py`、`packaging/test_container_probe.py`。
  - `container_probe.py` 自動合併：HM-06 加了 `CHILD` 與 `assert_child_bearer`（設定後的啟動直接打 3000 驗子程式 bearer），本片加了
    `MARKER`、還原階段的三個函式與 `run()` 裡的一行，位置不重疊。還原階段跑在未設定的第一次啟動之後，不會啟動子程式，和 HM-06 的
    檢查（設定後才跑）互不影響。
  - `test_container_probe.py` 文字衝突（`1295191` 那個 commit）：兩邊都改了開頭的說明與 import，也都在 `HeadscaleBackendTests` 後面加了
    測試類別。照兩邊的意圖合併：說明合成一句；import 取聯集（`ast`、`json`、`os`、`stat`）；HM-06 的 `FakeChild`、
    `ChildBearerCheckTests` 與本片的 `Seen`、`Owners`、`RestoreStageTests` 都留，兩段的內容和各自原本的版本逐字相同。
- 帳本：`claude-delivery` 的 55 筆為底（HM-05 新增 `profile_runtime.py`；HM-05、HM-06 改了 `products.py`、`session_idle.py`、
  `gateway.py`、`run_product.py`），加回本片的 2 筆，`profiles.py` 那筆用本片收斂後的內容（HM-05、HM-06 沒改 `profiles.py`）；
  `scope` 與其他 55 筆和 `claude-delivery` 逐字相同，JSON 格式照舊。逐 commit 核對：13 個 commit 都 0 漂移。
- tool-surface：HM-06 改 `session_idle.py` 時已在 `claude-delivery` 重產；本片沒動 `apps/`，`scripts/tool_inventory.py` 通過，不用重產。
- `git log origin/claude-delivery..HEAD` 只有本片的 13 個 commit，加上本筆記這次的更新（第 5 節列出）。

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

### 3.5 容器驗收的還原階段（審查 MF-1，選項 (a)；主對話 2026-11-15 定案）

- 位置：`container_probe.run()` 第一次（未設定）啟動、停機之後，設定 fixture 之前。fixture 只在停機時改（探針既有規則）。
- `restore_as_supervisor()`：先確認每一項都是一般目錄或單一連結的一般檔、還沒有標記（不合就什麼都不改、直接失敗）；再把
  `/data/mcp` 整棵 `chown 0:0`、檔案 0644、底下的目錄 0755（2026-10-05 HA 實測看到的樣子）。回傳還原項目的名稱與 `state.json` 的位元。
- `restored_start()`：用真映像啟動（entrypoint 以 root 執行 → 修復 → 降權 → exec 管理程序）；`ready_listener` 照舊驗 uid／gid 10001、
  NoNewPrivs、CapEff 0、`/data/mcp` 10001／0700、`state.json` 10001／0600；`check_restored_start()` 另驗標記存在（空檔、單一連結、
  10001、0600）、每個還原項目改回 10001（目錄 0700、檔案 0600）、`state.json` 位元不變；最後停機（檢查失敗也停）。
- 之後的流程不變：標記留在 `/data/mcp`，`fixture_snapshot()` 照收（一般檔、最多 16 項）。
- 誰跑：每個產品下一次發版時，builder 的 `supply_chain.py candidate` → `container_acceptance.py` 都會跑。本波不跑 builder，真容器沒有驗過；
  多一次未設定的啟動與停機，`docker run` 上限 180 秒內（推估多幾秒）。
- 真容器第一次跑：HM-19a 前的 builder 乾跑（主對話 2026-11-15 定案，同 HM-06 的作法）。功能 PR 不改版號、不出貨，所以這**不是**本片的
  合併關卡；之後的接手是 HM-16（驗收工具的多帳號階段）與各產品的發版片（第 11 節）。
- 本機的保證：`packaging/test_container_probe.py`（mock）與 `tests/test_restore_detection.py` 的兩案（同一段還原與檢查夾著真的
  entrypoint：一般使用者用 VirtualRoot，CI 以 root 用真的擁有者）。
- HM-13b 合併後，守門會在這次啟動就刪掉標記：HM-13b 要同時把探針的標記斷言改成它的新行為（第 11 節）。

### 3.6 檔名只有一個來源（審查 SF-1；2026-11-15，rebase 到 HM-07 之後）

| 角色 | 檔 | 做法 |
|---|---|---|
| 定義 | `profiles.py`（HM-07 的布局，計畫 §4.1） | 模組常數 `INDEX_NAME`、`INDEX_OPERATIONS_NAME`、`PROFILES_NAME`、`PROFILE_DATA_NAMES`、`SENTINEL_NAME`、`INSTANCE_RECORD_NAME`、`INSTANCE_RECORD_TEMPORARY_NAME`、`RESTORE_MARKER_NAME`、`REVOKE_ALL_MARKER_NAME`、`RESTORE_RECORD_NAME`。整個核心套件只有這裡寫這些字串；`Layout` 的屬性、`has_profile_data`、`index_quarantine_name` 都改用它們 |
| 引用 | `restore_detect.py` | `from .profiles import ... as MARKER, SENTINEL, RECORD, TEMPORARY, PROFILE_DATA`：名稱沿用，其他程式與測試不用改 |
| 引用 | `packaging/container_probe.py` | `MARKER` 改成 import `profiles.RESTORE_MARKER_NAME`。探針在映像的 venv 裡跑，本來就 import `mcp_admin_core.health`、`products` |
| 副本 | `packaging/entrypoint.py` | 保留 `MARKER`、`PROFILE_DATA` 兩份副本，註解寫明來源。它在降權前以 root、用 `/usr/local/bin/python` 執行，只用標準函式庫；核心套件要 venv（`config.py` import pydantic），不能也不該在這時載入 |

- 為什麼由 `profiles.py` 定義：布局是 HM-07 的（計畫 §4.1），`profiles.json`、`profiles` 本來就是索引自己的名稱。反過來由
  `restore_detect.py` 定義，索引檔名就會寫在還原偵測模組裡；兩邊各定義一部分，又會互相 import（循環）。
- import 關係：`restore_detect` → `profiles` → `config`（原本是 `restore_detect` → `config`；`profiles` 也只 import 標準函式庫與
  `config`）。entrypoint 仍然不 import 任何核心模組。四個入口（`run_product`、`apps/n8n/run.py`、`management_launcher`、entrypoint）
  實際載入時都沒有 `profiles`、`features`、`identity_fields`、`restore_detect`（HM-07 的 `test_no_entry_point_imports_the_unwired_modules`）。
- HM-07 的測試要跟著改一處：`tests/test_upgrade_zero_rewrite.py` 的靜態掃描會檢查每個核心檔，`restore_detect.py` import `profiles` 會被
  當成「有執行期檔 import 未接線模組」。`restore_detect` 自己也還沒接線，所以把它加進 `UNWIRED`：HM-07 的規則（入口不 import
  `profiles.py`）不變，另外多鎖住「入口不載入 `restore_detect`」（之前沒有測試鎖這件事）。HM-13b 接線時把 `profiles`、`restore_detect`
  一起移出清單。沒有和 HM-07 的測試或本片的設計衝突。
- 測試：`test_the_entrypoint_and_the_detection_use_the_same_names` 擴充成：`Layout` 的路徑等於 `restore_detect` 的名稱；`TEMPORARY`；
  探針的 `MARKER`；`restore_detect.py` 與 `container_probe.py` 的原始碼裡沒有任何一個名稱的字串常數（AST 掃描）；entrypoint 的副本等於
  固定值。HM-07 的 `test_layout_paths`、`test_quarantine_names`、`test_profile_data_presence` 本來就鎖固定值，照過。
- 值與行為都沒變；突變見第 4.4 節。

### 3.7 零改寫測試（HM-07 的交接）

- HM-07 交接：「`tests/test_upgrade_zero_rewrite.py` 的零改寫測試在 HM-13a／b 要加『開通後只多 sentinel 兩檔』」。
- 本片的程式還沒接線：正式 runtime 開機（`test_a_state_bb48449_wrote_starts_without_any_rewrite`）不論開關，都不會呼叫 `detect()`、不會
  建 sentinel。所以「正式開機、開通後只多兩檔」是 HM-13b 接線後的行為，交給 HM-13b（第 11 節）。
- 屬於本片的部分：`detect()` 本身在同一批樣本上的行為。新測試 `test_the_restore_check_on_a_state_bb48449_wrote_adds_only_the_sentinel`
  （8 個產品各一案）：
  - 開關關，連續兩次：`inactive`，整個目錄的種類、mode、inode、連結數、大小、mtime、ctime、內容都不變。
  - 開關開的第一次：`established`、不算還原；新增的項目剛好是 `.instance-sentinel` 與 `.instance-record`；其他項目（含 `state.json`、
    `.writer.lock` 的 ctime）都不變，只有目錄本身因為多兩項而改。
  - 之後開、關、開各一次：`consistent`、`inactive`、`consistent`，什麼都不變；`state.json` 位元相同；沒有帳號資料。
  - 每次看之前，先等檔案時鐘走過 `/data/mcp` 裡最新的 ctime（`test_restore_detection.after_tick`，探測檔建在 `/data/mcp` 外面）：
    檔案時間的 tick 很粗，同一個 tick 內的 chmod 不會改 ctime，沒等就看不出來（第 4.4 節 Z3）。

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

### 4.4 rebase 後的收斂與零改寫測試（2026-11-15）

先紅後綠：

- 名稱測試先擴充，在收斂前的 `restore_detect.py`（自己寫字串常數）上 AST 檢查失敗（同下表 N1）；改成 import 後通過。
- `UNWIRED`：`restore_detect` 改 import `profiles` 之後，HM-07 原本的清單讓靜態掃描失敗（N8）；把 `restore_detect` 加進清單後通過。
  這也證明 HM-07 的守門看得到這個新的 import。
- 零改寫的新測試是特性測試：鎖住現有行為，寫好就通過；它擋得住的改壞見下表 Z1～Z5。

臨時突變：在暫存區的複本（不含 `.git` 與 venv）一次改一處，跑名稱測試、`UNWIRED` 兩個測試、零改寫新測試、HM-07 的
`test_layout_paths`、`test_quarantine_names`、`test_profile_data_presence`（共 17 案；正式 conftest、wave1 鎖下）；每個跑完還原並比對
摘要，前後各跑一次未修改的複本（17 案全過）。「被擋」＝至少一案失敗。

| 突變 | 結果 |
|---|---|
| N1 `restore_detect.py` 自己再寫一份 `MARKER` 字串 | 被擋：名稱測試（AST） |
| N2 容器探針自己再寫一份 `MARKER` 字串 | 被擋：名稱測試（AST） |
| N3 entrypoint 的副本只列 `profiles.json` | 被擋：名稱測試 |
| N4 entrypoint 的副本改成別的標記名 | 被擋：名稱測試 |
| N5 布局改了標記名，entrypoint 的副本沒跟著改 | 被擋：名稱測試、`test_layout_paths` |
| N6 布局把 `profiles` 改名 | 被擋：名稱測試、`test_layout_paths`、`test_profile_data_presence` |
| N7 `run_product.py` 提早 import `restore_detect` | 被擋：靜態掃描、`run_product` 的實際載入 |
| N8 `UNWIRED` 照 HM-07 原本的清單（沒有 `restore_detect`） | 被擋：靜態掃描 |
| Z1 開關關也去看 sentinel（拿掉 `inactive` 的提早回傳） | 被擋：8 案 |
| Z2 重建後留下暫存檔 | 被擋：8 案 |
| Z3 開關開的第一次 chmod `state.json` | 被擋：8 案。第一輪只擋到 2 案：剛建好的檔在同一個時鐘 tick 內 chmod，ctime 不變。測試改成每次看之前先等檔案時鐘走過 `/data/mcp` 裡最新的 ctime（`after_tick`，探測檔建在 `/data/mcp` 外面），重跑 8 案都擋到 |
| Z5 開關關時 chmod `state.json` | 被擋：8 案（加了 `after_tick` 之後才做） |

## 5. 本機檢查（2026-11-15，第二次 rebase 後的最終程式；一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

本片的 commit（`git log origin/claude-delivery..HEAD`，舊到新）：`30ea3a7`、`aa44ce7`、`97713b1`、`7575217`、`feb8610`、`d7f8e95`、
`dcf4616`、`ebaed27`、`aa4a696`、`69c9150`（以上 10 個是最早的 `59a0e61`～`37f2a31`）、`687746a`（檔名收斂）、`2d68b4c`（零改寫測試）、
`6a8098f`（第一次 rebase 後的筆記），加上本筆記第二次 rebase 的更新。

pytest 用正式的 `tests/conftest.py`（拿全機共用的測試鎖），外面再包 wave1 鎖排隊；跑法同 CI（`-q -p no:cacheprovider`、
`PYTHONDONTWRITEBYTECODE=1`）。

- 第一次 rebase 後（`e5fa5c7` 上）：同一組目標測試（不含下表 HM-05、HM-06 兩列）698 案：692 通過、6 個要 root 的失敗、0 skip，
  在 `6fa9b93` 與 `bd782d0`（零改寫測試加了 `after_tick`，第 4.4 節 Z3）各跑一次，結果相同；那時等別的代理的全套跑完，等了 495 秒。
- 第二次 rebase 後（`8e02ac1` 上，`6a8098f`），加跑 HM-05 的 `tests/test_profile_runtime.py` 與 HM-06 的 `tests/test_child_bearer.py`：

| 檢查 | 結果 |
|---|---|
| `tests/test_restore_detection.py`（139 案） | 134 通過；5 失敗都是 `test_root_*`，停在 `require_root()`（`assert 1000 == 0`）；0 skip |
| HM-07：`test_profile_consistency`、`test_profile_index`、`test_profile_store`、`test_identity_fields`（221 案） | 220 通過；1 失敗是 HM-07 既有、要 root 的 `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（同 HM-07 provenance 第 6 節，只在 CI 驗） |
| HM-07：`tests/test_upgrade_zero_rewrite.py`（37 案，含本片新增 8 案） | 37 通過（`UNWIRED` 靜態掃描、4 個入口實際載入、`bb48449` 樣本正式開機零改寫、本片的還原檢查 8 案共約 0.05 秒） |
| HM-05：`tests/test_profile_runtime.py`（65 案） | 65 通過 |
| HM-06：`tests/test_child_bearer.py`（28 案） | 28 通過 |
| HM-01 守門（`test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`、`test_tool_inventory`、`test_ledger_precheck`、`test_secret_precheck`） | 75 通過 |
| `tests/test_migration_preview.py`（複製整個核心套件、跑遷移模組的那一案也在裡面） | 226 通過 |
| 合計 | 791 案：785 通過、6 個要 root 的失敗、0 skip；78 秒 |
| 全套收集（`--collect-only tests`，不拿測試鎖） | 4500 案（本片 `test_restore_detection.py` 139 案、`test_upgrade_zero_rewrite.py` 37 案），沒有重複收集 |
| `packaging/validate.py`（ci-venv 的 Python，PyYAML 6.0.3） | PASS |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`，`--offline` 只用快取；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同），23 秒；含 `test_entrypoint.py`、`test_container_probe.py`（HM-06 的 `ChildBearerCheckTests` 與本片的 `RestoreStageTests` 都在）。第一次 rebase 後是 `Ran 199` |
| `scripts/tool_inventory.py`（漂移檢查） | 通過 |
| 先紅後綠、臨時突變、root 案例的邏輯 | 第 4 節 |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨 |

packaging unittest 第一次用 `.venv` 加 `PYTHONPATH` 提供 PyYAML 跑，HM-17 的
`test_release_data_no_expression_can_carry_stops_every_tool_in_one_line` 有 4 個 subTest 失敗：它在子程序裡拿掉 `PYTHONPATH` 再跑
`validate.py`，找不到 `yaml`。這是本機環境問題（CI 把 PyYAML 裝進 `.venv`），所以改成上表照 CI 的暫存 venv，全部通過。

審查修正前（2026-11-15 早上）本機測試鎖一直被別的代理占著，當時的 pytest 用 `--noconftest` 加一個裝同樣網路與子程序守門、只是
不拿鎖的外掛；rebase 後這次都用正式 conftest。

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
也正常。rebase 與收斂後也沒跑全套（主對話說不用跑）：收斂只換了檔名的出處（值不變），改到的檔由第 5 節的目標測試全部跑到。
全套以 CI（root、0 skip）為準。

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
  `container_acceptance` 跑第 3.5 節的還原階段；本波不跑 builder，所以還沒有真容器的結果。第一次是 HM-19a 前的 builder 乾跑，不是本片的
  合併關卡。

## 7. `checks` 秒數

- 前、後：CI 跑完再補（寫進 PR 說明）。
- 推估：新測試本機約 1.3 秒，零改寫的新測試 8 案不到 1 秒，packaging 測試多約 1.5 秒；CI 增加約 3～5 秒，在每片 1.5 分鐘的預算內。
  最近幾片的 `checks` 在 1880～1944 秒（runner 變慢，主對話 11-15 07:5x 的分析），上限 40 分鐘。

## 8. 預檢結果

2026-11-15 第二次 rebase 後，在本筆記 commit 之後、以最終的 HEAD 跑（指令照 HM-01 筆記第 8 節，基準是 `origin/claude-delivery`
@ `8e02ac1`）：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <釘選的 gitleaks> --repo . --base origin/claude-delivery --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery
```

- **秘密預檢**：gitleaks 8.28.0（釘選、壓縮檔與執行檔摘要都核對過）；設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`8e02ac1..HEAD`，14 個，含本筆記兩次更新） | 0 |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史（建置機同款） | 0 |

- **帳本預檢**（`scripts/ledger_precheck.py`）：`runtime-patches.json` 170 個路徑、`runtime-sources.json` 70 個、`tool-surface.json`
  159 個，都 0 漂移、0 缺檔、0 個要 CI 安裝才有的檔。對 `origin/claude-delivery`（merge base `8e02ac1`）改了 12 個檔：列管檔 3 個
  （`profiles.py`、`restore_detect.py`、`packaging/entrypoint.py`）、帳本 1 個（`runtime-patches.json`）；新增而沒列管的執行期檔 0 個、
  改到而沒列管的執行期檔 0 個。結果 OK。
- 每個 commit 的帳本摘要都等於該 commit 裡檔案的 SHA-256（逐 commit 核對過，第 2.1 節）。
- 第一次 rebase 後（`c328974`，基準 `e5fa5c7`）：秘密預檢 13 個 commit 0 命中；帳本預檢 OK（158、70、159 個路徑，12 個檔，列管檔 3 個）。
- 最早（`37f2a31`，基準 `bb48449`）：秘密預檢 0 命中；帳本預檢 OK（154、70、159 個路徑，27 個檔，列管檔 2 個）。

## 9. PaaS 變動

- 本片沒有搬 PaaS 程式或測試。HM-00（#89）的對照表把 PaaS `restore_marker.py` 對到本片
  （`docs/provenance/multi-profile-parity-baseline.md` 第 2 節）；它在 pin `69ac425` 與 `7d111b1` 之間沒有變動（同文件第 3 節，
  2026-11-14 16:07 的檢查）。
- 變動清單（2026-11-15，主對話代查；本片代理沒有連 Gitea）：PaaS `main` ＝ `cf3d0d5`（06:2x fetch）。`69ac425..cf3d0d5` 動到核心模組
  （`packages/mcp-admin-core/mcp_admin_core/`）的只有：
  - `log_redaction.py`（#149）；
  - `gateway_pool.py`、`proxy.py`（#148 合併後的註解與文件更正，`19f36e2`）；
  - `setup_status.py`（移除 VK 的說明文字，`8bfb12e`）。
  - 還原標記相關的 PaaS 測試 `test_restore_marker.py` 只因移除 VK 改了參數列；`restore_marker.py` 沒變。
  - 結論：沒有一項和還原偵測的規則有關，本片照用的判斷（任何種類的項目都算存在、查不到答案也算）不變，不用改程式或測試。
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
| 全綠 | 本機：一般使用者能跑的全部通過（第 5 節；全套在審查修正前跑過，第 5.1 節）。CI（root、0 skip）待 PR |
| 未開通、沒有帳號資料的產品在沒有還原時零變化 | 通過：entrypoint 的一般開機不碰任何一項（`test_a_start_without_a_restore_changes_nothing`；root 版 `test_root_start_without_a_restore_changes_nothing` 在 CI）；`detect()` 只查三個名稱、不開檔不寫檔（`test_a_product_that_is_not_enabled_and_has_no_profile_data_is_left_alone`，與 8 個產品的 `bb48449` 樣本，第 3.7 節）；`rebuild()` 在這種情況拒絕、不寫（`test_a_rebuild_is_only_for_an_active_product`）；沒有接進執行期（`UNWIRED` 靜態掃描與 4 個入口的實際載入）。HM-01 黃金回歸（8 個產品的資料目錄不變）與 HM-07 的零改寫測試通過 |
| 每個產品下一次發版的容器驗收跑 root 還原樹 | 本片補上容器探針的還原階段（第 3.5 節；審查 MF-1 選項 (a)，主對話 2026-11-15 定案），之後每個產品發版的 builder 容器驗收都會跑。真容器第一次跑在 HM-19a 前的 builder 乾跑，交 HM-16 與發版片，不是本片的合併關卡 |
| 獨立安全審查 | 完成：「修正後通過」（必修 1、建議 10），處理見第 12 節 |
| 測試放 `tests/`、CI 以 root 跑、0 skip，不放 `packaging/test_entrypoint.py` | 通過：新測試沒有 `skip`／`skipif`／`xfail`；root 案例用斷言要求 root。`packaging/test_container_probe.py` 只放 mock（計畫 §10.1） |
| 同 PR 更新帳本 | 通過（第 2、8 節；每個 commit 都同步） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 一律執行時產生；state 用 `{"restored": true}`、`{"fixture": true}` 這類不含秘密的位元；record 只有整數；秘密預檢見第 8 節 |

## 11. 交接與還沒解決的事

- **開 PR（2026-11-15）**：HM-06（#94）、HM-05（#95）合併後已再 rebase 到 `8e02ac1`、照資料重算帳本、重跑受影響的測試與兩個預檢
  （第 2.1、5、8 節），再 push、開 PR。`checks` 秒數等 CI 跑完補（第 7 節）。
- **MF-1（主對話 2026-11-15 定案照 (a)）**：容器探針的還原階段留在本片。真容器第一次跑在 HM-19a 前的 builder 乾跑，交 HM-16 與發版片，
  不是本片的合併關卡。計畫 §10.1 寫「多帳號與 root 還原樹階段只在開通的候選映像跑」，和 §3.3、§11.5、§12.3、§14 #18 不一致；照 (a)
  可以讀成「多帳號（含 sentinel）的 root 還原樹是 HM-16、只在開通的候選映像跑；單帳號的 root 還原樹（本片）每個映像都跑」，計畫文字
  請主對話改（計畫在 repo 外）。
- **HM-13b**：把 `detect()` 接進開機順序（legacy 遷移之後、任何 listener 與子程式之前），`enabled` 用 `features.enabled(product)`
  在呼叫時讀；`restored` 時跑守門，最後 `rebuild(directory, enabled=...)`、再刪標記；沒開通、沒有帳號資料時記一行 WARNING 後刪標記。
  另加測試掃描所有 chmod／chown 呼叫點，確認碰不到 sentinel。
  - 零改寫（HM-07 交接的另一半，第 3.7 節）：擴充 `test_a_state_bb48449_wrote_starts_without_any_rewrite`：產品開通時，正式 runtime
    開機後新增的項目只有原本的 `child`（n8n 沒有）加上 `.instance-sentinel`、`.instance-record`，其他項目一個位元組都不變；沒開通時
    和今天一樣不多任何檔。
  - 接線時把 `profiles`、`restore_detect` 移出 `tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED`（`features` 是 HM-08）。
  - 守門要用的檔名一律取 `profiles.py` 的常數或 `Layout`（`REVOKE_ALL_MARKER_NAME`、`RESTORE_RECORD_NAME`、隔離名稱），不要另寫字串；
    entrypoint 的副本只有 `MARKER`、`PROFILE_DATA` 兩個。
  - 守門刪標記之後，`container_probe.check_restored_start()` 的「標記還在」要改成新行為（例如標記已刪、state 不變）。
  - sentinel 或 `.instance-record.tmp` 的名稱被目錄占用時，`rebuild()` 每次都失敗、add-on 起不來（審查 SF-7、X9）：改名隔離後重建，
    或寫明脫困方法。
  - 本片先發、HM-13b 還沒發的期間，還原留下的標記會一直在；開通的產品第一次開機遇到這種舊標記也會跑一次守門（沒有帳號資料時依
    DQ-03 (b) 不撤銷、只發通知），HM-13b、HM-13c 的通知文字要涵蓋這種情況。
- **HM-16**：容器探針的多帳號階段（含 sentinel 的 root 還原樹）接在本片的還原階段之後；`docker run` 180 秒上限要跟著看。
- **各產品的發版**：HM-13a 合併後第一個發版的產品，builder 容器驗收第一次真的跑第 3.5 節（最早是 HM-19a 前的 builder 乾跑）；失敗時先查
  探針與 entrypoint，不要放寬檢查。CHANGELOG 用第 3.4 節的段落，不要照抄計畫 §3.3 的表（那是 HM-13b 之後的行為）。
- **HM-03a**（實機，還沒做；本片照設計實作）：在 QA HAOS 做 full、partial、加密備份各一次還原，確認 `/data/mcp` 屬 root、標記建立、
  sentinel 判 `mismatch`；sentinel 的 ctime 在 add-on 重啟、**主機重開**、add-on 更新、Supervisor 更新後不變（UC-08、UC-25）。本片所有
  測試都在同一次開機內，sentinel 的 inode 沒有離開過快取（審查 SF-9）：UC-25 一定要包含主機重開，記下資料分割的檔案系統與 inode 大小，
  重開前後比對 record 與 `lstat`；奈秒不穩時再評估只比到秒的備案。**實機結果在 HM-13b 合併前寫回**（本筆記或 HM-13b 的 provenance）。
  若某種還原兩個訊號都不觸發，照 DQ-39 (a) 不出貨、先修偵測。
- **HM-07（已處理，2026-11-15）**：rebase 後檔名收斂成 `profiles.py` 一個來源（第 3.6 節，審查 SF-1）；零改寫測試屬於本片的部分已做
  （第 3.7 節），正式開機的部分見上面 HM-13b。
- **HM-00 `ledger-tracking.md`**（#89 已合併，本片沒改這份文件；交 HM-18 或下一個動到 `docs/multi-profile/` 的片）：第 3 節要把
  `packaging/entrypoint.py` 移到「已列管」（審查 SF-5）。同一節的 `config.py` 也已在 HM-07（#93）列管；第 1 節 `profiles.py` 那列
  「之後會改的片」要加 HM-13a。
- **HM-18**：DOCS 寫兩行訊息每種原因怎麼處理（`ENOSPC`：清出空間；`EROFS`、`EIO`：查儲存；`name in use`：還原別份備份）；契約布局
  補 `.instance-record.tmp`（SF-7）；已知限制寫進文件：區塊層級的回滾（例如虛擬機快照還原）帶回同一個 inode 與 ctime、擁有者也不變，
  兩個訊號都看不到，本片只涵蓋 Supervisor 的檔案層級還原（計畫 §8.9 的延伸）。

## 12. 審查意見處理（`wave1/review-HM-13a.md`，判定「修正後通過」）

| id | 處理 | 在哪裡 |
|---|---|---|
| MF-1 容器驗收的 root 還原樹沒有落地方法 | 處理：選項 (a)（主對話 2026-11-15 定案），本片補容器探針的還原階段與 mock 測試，另在 `tests/` 夾著真的 entrypoint 跑（含 CI 的 root 版）。真容器在 HM-19a 前的 builder 乾跑，交 HM-16 與發版片，不是本片的合併關卡。計畫 §10.1 的文字請主對話改 | `packaging/container_probe.py`、`packaging/test_container_probe.py`、`tests/test_restore_detection.py`、`docs/operations/acceptance.md`；第 3.5、11 節 |
| SF-1 rebase 時鎖住帳號資料的名稱 | 處理（2026-11-15，rebase 後）：檔名只在 HM-07 的 `profiles.py` 定義，`restore_detect` 與容器探針 import；entrypoint 的副本由測試鎖住 | `profiles.py`、`restore_detect.py`、`packaging/container_probe.py`、`tests/test_restore_detection.py`、`tests/test_upgrade_zero_rewrite.py`；第 3.6 節 |
| SF-2 過渡期行為與計畫不同，CHANGELOG 不能照抄 | 處理：可直接貼的 CHANGELOG 段落 | 第 3.4 節；PR 說明 |
| SF-3 操作文件的還原修復表沒跟上 | 處理：加「還原標記」「建不出標記」兩列，「上限」「成功」註明含標記 | `docs/operations/update-backup-rollback.md` |
| SF-4 建不出標記的訊息不說原因 | 處理：同一行加原因碼（errno 名稱或 `name in use`），不含路徑或值；各原因的處理方式交 HM-18 | `packaging/entrypoint.py`；第 3.1 節 |
| SF-5 HM-00 `ledger-tracking.md` 要改 | 主對話的同步 PR #96（只改 `docs/multi-profile/`）處理，寫成「`packaging/entrypoint.py`：HM-13a 起列管」；本片不改 HM-00 的文件 | 第 11 節 |
| SF-6 provenance 第 3.1 節、entrypoint 註解、引用 #89 的文件 | 處理：第 3.1 節分開寫「名稱被目錄占用」與「被連結或多重連結占用」；註解改成 sentinel 只看得到「開通後做的備份」；那些文件在 #89，rebase 後本分支已有 | 第 3.1、9 節；`packaging/entrypoint.py`；帳本 |
| SF-7 名稱被目錄占用時 `rebuild()` 一直失敗 | 留給 HM-13b（守門怎麼脫困）與 HM-18（契約布局補 `.instance-record.tmp`）；本片 `rebuild()` 沒有呼叫者 | 第 3.3、11 節 |
| SF-8 測試缺口（R16、E19、E20、R03、R14、R13 卡住） | 處理：補 bool inode／ctime、懸空 `profiles` 連結、有兩個連結的標記、inode／ctime 各自不同、fstat 大小超過上限；FIFO 案例加 5 秒期限。6 個都改成被擋 | `tests/test_restore_detection.py`；第 4.2 節 |
| SF-9 重開機後 ctime 是否穩定 | 交 HM-03a：UC-25 一定包含主機重開，記錄檔案系統與 inode 大小、重開前後比對 | 第 11 節（HM-03a） |
| SF-10 `rebuild()` 沒擋未開通、沒有帳號資料的呼叫 | 處理：`rebuild(directory, enabled=...)` 不是 active 就 `ConfigError`、不寫 | `restore_detect.py`；第 3.3 節 |
