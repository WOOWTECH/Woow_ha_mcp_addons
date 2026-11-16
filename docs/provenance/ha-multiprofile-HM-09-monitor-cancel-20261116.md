# HA 多帳號 HM-09 追補 provenance：健康監看一定照停止要求停下（所有產品；2026-11-16）

## 結論

- **現象**：PR #103（HM-14，head `8ff259b`）的 `checks` 只有一案失敗：HM-20 的
  `tests/test_backend_loopback.py::test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end[False]`。
  測試本體結束、rig 取消 `run_product.run` 之後，`tests/multi_profile_runtime.py` 的 `asyncio.timeout(CLOSE_SECONDS)`（30 秒）逾時。
  這時 `run_product.run` 停在 `await asyncio.gather(monitor, stopping, ...)`：額外帳號 B 的監看在 rig 取消後照常每秒查 2 次、查滿 30 秒，
  第二次取消才停；預設帳號的監看在第一次取消就停了。
- **根因**（第 2 節）：監看 task 收到的取消被 HTTP 堆疊吃掉了，不是我們的程式吃的。httpx 每開一條新連線都經過 `anyio.connect_tcp`，
  它的 task group 在連上時取消自己的 cancel scope（anyio 4.15.1 `anyio/_core/_sockets.py:206`），這個取消立刻送到正在連線的 task。
  停止要求（`_stop_monitors`、`remove()`、run_product 收到 SIGTERM 時的 `monitor.cancel()`）如果剛好在那之後、task 再跑之前到，
  CPython 3.13 只把 task 標成要取消，task 拿到的還是 anyio 那一個 `CancelledError`；scope 結束時看訊息認得是自己的，就吞掉
  （`anyio/_backends/_asyncio.py:453-549`，判斷在 530-534 行，不看 `Task.cancelling()`）。連線照常完成、這次檢查做完、監看的迴圈繼續，
  等它的關閉就一直等。CI 上每個健康檢查的請求都新開一條連線（第 3.1 節），一次檢查有 5 個這樣的時間點。httpcore 的讀取期限
  （`anyio.fail_after`）也是同一種。
- **四個候選逐一驗證**（第 3.3 節）：只有 anyio 的兩處會吃掉取消（連線的 task group、讀取期限）。`_pause` 的 `wait_for`、`_check` 的
  `asyncio.timeout(8)`／`(5)`、finally 裡的 DELETE 都不會；B 只有一個監看 task；預設帳號和 B 的監看參數只差起點，兩種都會吃掉。
- **和 HM-14 無關**（第 3.4 節）：精準重現在不含 HM-14 的 `269f5a5` 上就紅；HM-14 只改閘道三個檔，監看的路徑一行都沒碰。
- **本機重現**：真的 HM-20 測試在 `269f5a5` 上連跑 30 次全過（時間點太窄，打不到）；改用精準重現：在 anyio 的連線上掛鉤子，把取消放在那一步
  之後、task 再跑之前（CI 的時機，變成必然）。
- **決策**（第 4 節）：同樣的競態在沒開通的單帳號監看也有（每 15 秒一次檢查，機率低很多，但已發行的每個產品都有）。使用者 2026-11-16 13:4x
  定「全部產品都修」：所有監看都套用，屬不受開關管的變更（契約第 1.2 節），只改關閉，8081、8099 的回應逐位元不變。
- **修法**（第 4 節，只改 `health.py`）：`HealthMonitor.check()` 記下檢查前 task 的 `cancelling()`，檢查做完時比檢查前多，就自己
  `raise asyncio.CancelledError`。`asyncio.timeout` 和 anyio 都會撤回自己發的取消，多出來的只會是外面要它停、卻沒以例外送到的那一次。
- **測試**（第 5、6 節）：新 `tests/test_monitor_cancel.py` 13 案（開通：一次檢查的 5 條連線、預設帳號的起點、讀取期限、`settle()`、rig 的
  取消、SIGTERM ×2；沒開通：ProfileRuntime 的監看、SIGTERM）。只有測試、在 `d00a338` 上：13 案全紅；只修開通的版本：沒開通的 2 案紅、
  其他 11 案綠；所有產品都修：連跑 5 遍 65 案全過，每案 0.23 秒以內。
- **各產品下一版 CHANGELOG 的句子**（本 PR 不改 CHANGELOG，交發版片）：
  "Fixed: stopping the add-on could wait for Home Assistant's 30 s stop timeout in rare cases."
- **檢查**（第 7 節）：全套 pytest 5793 案：5786 過、7 個失敗都是要 root 的既有案例、0 skip（head `5ac68d5`，之後只加本筆記）；其中新檔 13、HM-01 守門 45、health 三檔 62、lifecycle 28、runtime 三檔 106、HM-20 的 loopback 153、HM-10 三檔 86、HM-14 五檔 135 案全過。兩個預檢 OK（gitleaks 0 findings；帳本 0 漂移，`health.py` 照預期列成「沒列管、要人看」）、`validate.py` PASS、`tool_inventory.py` 0 漂移、packaging unittest 203 案（5 個要 root 的 skip）。
- **沒處理的**（第 10 節）：上游 anyio 沒回報（不准連外）；`test_saved` 不在保護內（無害）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 性質 | HM-09 的追補（不是新切片）；不受開關管（契約第 1.2 節），`MULTI_PROFILE_PRODUCTS` 維持空的，測試用 monkeypatch |
| 分支 | `fix/ha-multiprofile-hm09-monitor-cancel-20261116`。commit：`4aab30b` 測試（先紅）、`4f67f27` 修正、`5ac68d5` 契約與驗收表、本筆記 |
| HA 基準 | `claude-delivery` `d00a338`（#104 HM-10 的合併；含 #103 HM-14、#102 HM-20、#101 HM-09） |
| 觸發 | PR #103 的 `checks`（head `8ff259b`；CI：root、Python 3.13.16）；job log 的 traceback 約第 1529～1830 行、captured log 第 1823～6040 行 |
| 決策 | 2026-11-16 13:4x 使用者定「全部產品都修」（主對話轉達）；之前照指示只修開通的產品 |
| 套件（都沒動，`uv.lock` 未改） | CPython 3.13.15（本機）／3.13.16（CI）、anyio 4.15.1、httpx 0.28.1、httpcore 1.0.9 |
| 證據目錄（repo 外） | `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-09-monitor-cancel/`（第二輪在 `v2/` 與檔名帶 `red1`、`red2`、`green-all-products` 的檔） |

## 2. 根因

一步一步（行號是本機 venv 裡的檔案）：

1. 健康檢查的每個請求走 `self.client.stream(...)`：httpx → httpcore `AsyncConnectionPool` → `httpcore/_backends/anyio.py`
   `connect_tcp`（`anyio.fail_after(3)` 包著）→ `anyio.connect_tcp`。
2. `anyio.connect_tcp`（`anyio/_core/_sockets.py:145-267`）開一個 task group，子 task `try_connect` 連上後
   `connected_stream = stream; tg.cancel_scope.cancel()`（第 206 行）。`CancelScope.cancel()` → `_deliver_cancellation()`
   立刻對宿主 task（就是監看的 task，正在 `move_on_after` 裡等 `event.wait()`）呼叫
   `task.cancel("Cancelled via cancel scope …")`：task 等的那個 future 帶著 anyio 的訊息被取消，task 排進下一輪。
3. 這時如果有人對同一個 task 呼叫 `task.cancel()`（`_stop_monitors`；或 run_product 對 monitor task），
   CPython 3.13 的 `Task.cancel()` 發現 `_fut_waiter.cancel()` 回 False（已經取消了），只設 `_must_cancel`；
   task 下一步拿到的還是那個帶 anyio 訊息的 `CancelledError`，`_must_cancel` 被清掉（`asyncio/tasks.py:198-238`、`__step` 281-289；
   C 版 `_asyncio` 的做法相同）。兩個要求、一個例外；`cancelling()` 是 2。
4. task group 結束時，scope 的 `__exit__`（`anyio/_backends/_asyncio.py:453-549`）撤回自己的要求（`uncancel()`，`cancelling()` 回到 1），
   看到例外是 anyio 自己的（`is_anyio_cancellation` 只看訊息）就回 True：吞掉。`connect_tcp` 正常回傳連線。
5. 請求照常送出，檢查做完，`HealthMonitor.run()` 進 `_pause` 再查下一次；`_watched` 永遠看不到 `CancelledError`，也就沒有
   'monitor stopped'。`_stop_monitors` 的 `gather` 一直等，`_monitor` 的 finally 不會結束，run_product 第 97 行一直等，
   rig 的 30 秒到了才第二次取消，這次落在 `_pause` 裡，B 才停。
6. httpcore 的讀取（`anyio.fail_after(10)`）是第二個地方：期限到時 anyio 同樣先取消 task，外面的取消跟在後面到就一樣被吞，
   `fail_after` 再把它變成 `TimeoutError` → `httpx.ReadTimeout` → `_check` 的 `except Exception`，迴圈繼續。要子程式剛好卡住，比較少見。
7. 為什麼是 B 不是預設帳號：兩個都是開通後的監看，參數只差起點（`first_check_after`），程式路徑相同。CI 那次預設帳號的最後一次檢查
   在 02:52:24 做完、取消落在 `_pause`；B 的取消落在某條連線的那一步之後。第 3.3 節的精準重現裡，預設帳號那種監看一樣會吃掉。

## 3. 證據

### 3.1 CI log（`ci-8ff259b-captured-log.txt`、`ci-log-analysis.txt`）

- 子程式 port：預設帳號 48995、B 49941。每個請求都新開一條連線：48995 有 31 次 `connect_tcp.started`（2 次在子程式聽 port 前失敗）
  對 29 個請求，49941 有 316 次對 314 個請求。每次健康檢查 5 個請求（initialize、initialized、ping、tools/call、DELETE），
  也就是 5 條新連線。
- 照 `notifications/initialized` 的 202 回應的 `date` 標頭算：預設帳號最後一次檢查在 02:52:24；B 從 02:52:24 到 02:52:54 每秒 2 次
  （02:52:25 與 02:52:45 各 1 次，02:52:38 沒有），和取消前一樣的頻率：只有一個 B 的監看 task 在跑，不是兩個。
- 整段 captured log 沒有任何 `CancelledError`：httpcore 的 trace（`httpcore/_trace.py:95-107`）在請求途中收到取消會記
  `….failed exception=CancelledError(...)`；被 anyio 吞掉的取消不會留下任何紀錄，連線照樣 `connect_tcp.complete`。

### 3.2 本機重現：真的 HM-20 測試 30 次（`repro-claude-delivery-269f5a5/`）

- `269f5a5` 上連跑 `[False]` 30 次：30 過、0 失敗（`summary.txt`；幾次 12～27 秒是在等共用測試鎖）。
- 診斷外掛（`tools/hm09_cancel_diag.py`，只觀察：anyio 吞掉取消時 task 還有沒處理的取消就記一筆；`_stop_monitors` 取消前一刻
  每個監看 task 的 await 鏈；3 秒還沒停就再記一次）：60 次 `_stop_monitors`（每次測試 2 次，第二次沒有 task），30 次 B 都在
  `health.py:348 run → 260 _pause → wait_for → Event.wait`（`269f5a5` 的行號），1 ms 內停；沒有一次 anyio 吞掉取消。本機的時間點太窄，靠運氣打不到。

### 3.3 逐一打候選點（`tools/repro_candidates.py`、`repro-candidates-before-fix.txt`／`.json`）

不起真子程式：本機 asyncio HTTP 伺服器，每個回應都 `connection: close`（每個請求新開連線，同 CI），真的 httpx、httpcore、anyio。
每個候選都在確定的時間點送外部取消，看 task 1 秒內停了沒有（`269f5a5`）：

| 候選 | 怎麼打 | 結果 |
|---|---|---|
| 2c anyio 連線的 task group（B 那種監看，一次檢查的第 1～5 條連線） | 連上後在下一步取消（anyio 的取消已經先到：`waiter.cancelled()` 為真） | 5 案都**沒停**：那次檢查剩下的請求照送（5、4、3、2、1 個），`cancelling()` 還是 1 |
| 2c 同上，預設帳號那種監看（起點 0） | 同上，第 1 條連線 | **沒停** |
| 2c 同上，沒開通的監看（沒有參數） | 同上 | **沒停**（同樣的競態；使用者因此定全部產品都修，第 4 節） |
| 1 `_pause` 的 `wait_for` 逾時同一刻 | 在 `Timeout._on_timeout` 之前、之後各取消一次 | 兩種順序都停（`asyncio.timeout` 用 `cancelling()` 計數，不會把外部取消當成逾時） |
| 2a `_check` 的 `asyncio.timeout` 到期同一刻（子程式不回） | 同上 | 兩種順序都停 |
| 2b finally 裡的 DELETE 正在等回應時取消 | 伺服器收到 DELETE 時取消 | 停（`except Exception` 不接 `CancelledError`） |
| 2d httpcore 讀取的 `fail_after` 期限同一刻（子程式不回） | 期限前、後各取消一次 | 取消在前：停；**期限在前：沒停** |

候選 3（`_watched`、`_stop_monitors`、`_watch` 有第二個 B 的 task 或 task 被換掉）：`_watch` 只在沒有 task 或 task 已結束時才建新的；
`_monitor` 的 finally 先把 `_serving` 設成 False，再取消並等 `starting`，之後才 `_stop_monitors`，所以 start_all 不會再 `_watch`；
CI log 裡 B 的頻率在取消後沒變（第 3.1 節）。排除。候選 4（預設帳號與 B 的參數差異）：只有起點不同，上表兩種都會吃掉。排除。

### 3.4 和 HM-14 無關

- 第 3.3 節的重現與第一輪紅燈（第 5.1 節）都在 `269f5a5` 上：它不含 HM-14（HM-14 分支的 merge base 就是 `269f5a5`，那時它的 commit 都不在 `claude-delivery`）。
- HM-14 改的執行期檔只有 `gateway.py`、`access.py`、`profile_router.py`（`git diff --stat 269f5a5 origin/feat/ha-multiprofile-hm14-20261115`）。
  監看的路徑（`health.py`；`profile_runtime.py` 的 `_monitor`、`_watched`、`_stop_monitors`；`run_product.py`）和它 import 的模組都沒動；
  吃掉取消的是 anyio 的連線，每次健康檢查都會經過，和閘道無關。
- HM-14 最多改變事件迴圈的忙碌程度，也就是打到時間點的機率；#102 的 CI 綠、#103 的 CI 紅各只有一次，看不出機率差異。

## 4. 決策與修法

**決策**：第一輪（`269f5a5` 上）照當時的指示「開關關的單一帳號路徑行為不變」，只修開通的產品（`HealthMonitor.paced`：有 HM-09 監看參數的
監看），把沒開通的同一個競態列為待決。2026-11-16 13:4x 使用者定「全部產品都修」：拿掉 `paced` 條件，所有監看都套用。這是不受開關管的變更
（契約第 1.2 節），任何產品下一次發版都會帶出去；只改關閉。

`packages/mcp-admin-core/mcp_admin_core/health.py`：

- `HealthMonitor.check()`：檢查前記下 `asyncio.current_task().cancelling()`，檢查做完時如果比檢查前多，就 `raise asyncio.CancelledError`。
- 模組 docstring 加一段，說明 anyio 的行為與版本、所有產品都套用。

為什麼這樣改：

- `check()` 是監看迴圈（開通的 `run()`、沒開通的「一次檢查、睡 15 秒」）和錯開啟動的就緒等待（`settle()` → `ProfileManager._started`）
  共同的入口，anyio 只在這裡面跑；`_pause` 與 `asyncio.sleep` 純 asyncio，不會吃掉取消（第 3.3 節候選 1）。一個地方擋住所有路，
  `profile_runtime.py`、`run_product.py` 都不用改。
- 比的是「檢查前後」：`asyncio.timeout` 與 anyio 都會撤回自己的取消，多出來的只會是外面要求停止、卻沒以例外送到的那一次。檢查裡面的
  `asyncio.timeout`（8、5、3 秒）自己的取消被吞掉時，離開那個區塊時會自己撤回（`uncancel()`），計數回到原來的值，不會誤停。
- 直接 `raise` 而不是再 `task.cancel()` 一次：計數維持「真正的要求數」，外層的 `asyncio.timeout`（`_started` 的就緒等待）照樣能分辨：
  被吞的是它自己的逾時就轉成 `TimeoutError`，是外面的取消就往外傳。
- 被吞掉之後，這次檢查剩下的請求會做完才停：子程式正常時是幾毫秒；最壞（剛好又卡住）是檢查自己的上限 8＋5＋3 秒。不修的話是永遠不停。

沒開通的單帳號只改關閉：

- 沒有停止要求時，`check()` 做的事和之前一樣（多讀兩次 `cancelling()`），8081、8099 的回應、狀態碼、標頭、健康狀態與 log 都逐位元不變：
  HM-01 的黃金回歸與兩個契約凍結照過（第 7 節）。
- 收到 SIGTERM 時，run_product 的 `monitor.cancel()` 被吞的那種罕見情況，以前會卡到 HA 的停止上限強制結束（子程式沒照順序停），
  現在那次檢查做完就停、照順序關完。
- 各產品下一版 CHANGELOG 的句子（發版片寫；本 PR 不改 CHANGELOG、不改版號）：
  "Fixed: stopping the add-on could wait for Home Assistant's 30 s stop timeout in rare cases."

沒改的：`test_saved`（面板的後端測試，跑在請求的 task 裡；取消被吞只是那次測試做完才回）、`profile_runtime.py`、`run_product.py`、
`uv.lock`、套件版本、版號、`addons/`、CHANGELOG。`health.py` 不列管（`docs/multi-profile/ledger-tracking.md` 第 3 節），帳本不用動；
`ledger_precheck.py` 會把它列成「沒列管、要人看」但不算失敗。

契約：第 1.2 節「不受開關管」多一項（附缺口、理由、改了什麼、HM-01 凍結不用改、測試），第 7 節「關閉」列補一句、第 10 節加一列。第 9 節
（和 PaaS 的刻意差異）不加列：PaaS（`d7f5849`）沒有常駐的 httpx 健康監看迴圈（`process.py` 不用 httpx，健康探測是各產品的
`health_probes.py`），這不是刻意差異，所以沒有列號要重編。驗收表的測試檔登記表加 `tests/test_monitor_cancel.py`。

## 5. 測試（先紅後綠）

`tests/test_monitor_cancel.py`（新檔，13 案；一律在 HM-01 的 log scan 下跑）：

| 測試 | 做什麼 |
|---|---|
| `test_a_stop_anyio_s_connect_swallowed_still_ends_the_monitor[additional-1..5]` | 開通、額外帳號的起點，在第一次檢查的第 n 條連線（initialize、initialized、ping、探測、DELETE）被取消：先驗 anyio 的取消先到（`waiter.cancelled()`）、那次檢查剩下的請求照送（確實被吞），再要求監看以取消結束 |
| `…[default-1]` | 同上，預設帳號的起點（馬上查） |
| `test_a_stop_after_anyio_s_read_deadline_still_ends_the_monitor` | 子程式不回、讀取期限縮成 0.2 秒，期限一到就取消（anyio 先） |
| `test_start_all_s_readiness_wait_ends_when_anyio_swallowed_its_stop` | `settle()`（`ProfileManager._started` 用的就緒等待）在第一條連線被取消 |
| `test_a_switched_off_profile_s_monitor_ends_when_anyio_swallowed_its_stop` | 沒開通：照 run_product 建的 `ProfileRuntime`（沒有監看參數：馬上查，之後每 15 秒），它的監看在第一條連線被取消：那次檢查照做完（被吞），之後要停 |
| `test_the_rig_s_close_is_not_held_by_a_monitor_whose_stop_anyio_swallowed` | PR #103 的路徑：`multi_profile_runtime`（開通、真的子程式客戶端）被 rig 取消，`_stop_monitors` 給 B 的取消壓到 B 的下一條連線、在 anyio 的那一步之後送到（`held_stop`） |
| `test_sigterm_stops_a_switched_on_…[additional]`、`[default]` | 第 6 節 |
| `test_sigterm_stops_a_switched_off_…` | 第 6 節 |

### 5.1 結果

| 輪 | 程式 | 結果 | 證據 |
|---|---|---|---|
| 第一輪紅（開通的 11 案，`269f5a5`） | 沒有修正 | 連跑 3 遍：33 案全紅 | `red-before-fix.txt` |
| 第一輪綠（開通的 11 案） | 只修開通的版本 | 連跑 5 遍：55 案全過 | `green-after-fix.txt` |
| 紅 1（13 案，`d00a338`，只有測試＝本分支第一個 commit） | 沒有修正 | 13 failed（29.8 秒；關閉上限縮成 5 秒） | `red1-base-d00a338.txt` |
| 紅 2（13 案） | 只修開通的版本（`paced` 條件還在） | 11 passed、2 failed：沒開通的 2 案（「the switched-off profile's monitor went on after its stop」、「run_product.run did not stop within 5 s of SIGTERM」） | `red2-paced-only-fix.txt` |
| 綠（13 案×5 遍＋HM-01 守門） | 所有產品都修（本分支） | 110 passed：本檔 65 案，每案 ≤ 0.23 秒；HM-01 守門 45 案（第一案的 86 秒是在等共用測試鎖） | `green-all-products.txt` |

每案都紅在預期的那一句：取消後監看還在跑、就緒等待照常回傳、rig 的關閉逾時（`TimeoutError`，同 CI）、SIGTERM 後沒關完。

怎麼讓競態必然發生：

- `ClosingChild`：本機 asyncio 伺服器，回 initialize、initialized、ping、產品的就緒探測與 DELETE，每個回應都 `connection: close`，
  所以每個請求都新開連線（同 CI log）。
- `cancel_in_anyio_s_window`：monkeypatch `anyio._backends._asyncio.AsyncIOBackend.connect_tcp`（`anyio.connect_tcp` 的 `try_connect`
  用它連線），真的連上後用 `call_soon` 在下一步取消目標 task。這時 `try_connect` 已經取消它的 task group（anyio 的取消先到），
  目標 task 還沒再跑：就是 CI 那次的時機。
- `held_stop`（整個 add-on）：用 loop 的 task factory 讓目標 task 是 `asyncio.Task` 的子類別，正式程式碼裡負責停它的那個函式
  （`_stop_monitors` 或 `run_product.run`）第一次對它 `cancel()` 時先壓著不送，等它下一條連線再照上面的時機送到。
- 沒開通的監看每次檢查之間睡 15 秒：SIGTERM 那案把 `health.py` 裡的這一次等待縮成 0.05 秒（只換 `health` 模組的 `asyncio` 名稱，
  `shorter_switched_off_interval`）。
- 紅燈那幾輪的關閉上限：整個 add-on 的測試卡住時要等 30 秒（HA 的上限），證據用的外掛 `tools/short_close.py` 把它縮成 5 秒，
  讓一次 session 很短、不擋別人排隊的全套。提交的測試照用 30 秒。

測試檔用到的私有介面（版本都釘在 `uv.lock`）：`AsyncIOBackend.connect_tcp`、`CancelScope.cancel` 與 `_host_task`、`Task._fut_waiter`。
anyio 改了這些，測試會在前提的斷言（`anyio_first`）或設定時失敗，不會假裝通過。

## 6. 正式的關閉路徑（SIGTERM）

HA 停 add-on 時送 SIGTERM，最多等 30 秒（契約第 7 節）。

- 開通的產品：(1) `run_product.run` 的 SIGTERM 處理器設 `stop`，finally 裡 `monitor.cancel()`（預設帳號的監看，跑在
  `ProfileManager._monitor` 的 task 裡）並等它；(2) `_monitor` 的 finally 取消並等 `start_all`，再 `_stop_monitors()` 取消並等每個額外帳號的
  監看；(3) 等 listener 停（最多 5 秒），離開 `async with profile`：`stop_all()` 並行停所有子程式。
- 沒開通：(1) 同上，`monitor.cancel()` 停的是 `ProfileRuntime.monitor()`（`HealthMonitor.run()`：一次檢查、睡 15 秒）；(3) 關 runtime（子程式）。

第 (1)、(2) 步的取消都可能被吞，修正前會卡在那一步，永遠走不到 (3)（HA 30 秒後強制結束，子程式沒照順序停）。修正後監看都在那次檢查做完時停。

`test_sigterm_stops_a_switched_on_…`、`test_sigterm_stops_a_switched_off_…`：`run_product.run`（Odoo；listener 不開 socket、子程式用
`NoProcessSupervisor`、子程式客戶端是真的，打到 `ClosingChild`）服務後，對本程序送真的 SIGTERM（只在 run_product 的處理器已裝上時送；
預設動作會結束整個測試）。開通的兩案讓 `_stop_monitors` 給 B 的取消（`[additional]`）或 `run_product.run` 給預設帳號監看的取消
（`[default]`）落在 anyio 的那一步之後；沒開通那案讓 `run_product.run` 給唯一監看的取消落在那裡。三案都要求 `run_product.run` 在 30 秒內
正常回傳（不是被取消）、監看以取消結束：修正後都在 0.23 秒內收完；修正前都沒回傳。

## 7. 跑過的檢查

第二輪（所有產品，`d00a338` 上；`v2/` 與檔名帶 `red1`、`red2`、`green-all-products` 的檔）：

| 檢查 | 結果 | 證據 |
|---|---|---|
| 新測試：紅 1、紅 2、綠 | 見第 5.1 節 | `red1-base-d00a338.txt`、`red2-paced-only-fix.txt`、`green-all-products.txt` |
| 全套 pytest（排在 `wave1-pytest.lock` 後面，head `5ac68d5`） | 5793 案：5786 過、7 失敗（都是下面要 root 的既有案例）、0 skip、0 error，1931 秒 | `v2/full-suite.txt`、`v2/full-suite-junit.xml` |
| 全套裡的相關檔 | 新檔 13、HM-01 守門（黃金回歸＋兩個契約凍結）45、`test_health_backoff`＋`test_staggered_start`＋`test_health` 62、`test_profile_lifecycle` 28、`test_profile_runtime`＋`test_extra_child_resources`＋`test_profile_ports` 106、`test_backend_loopback` 153、HM-10 三檔（`test_profile_admin_api`、`test_admin_pipeline_matrix`、`test_router_passthrough`）86、HM-14 五檔（`test_carries_no_request`、`test_gateway_busy_shapes`、`test_gateway_queue_ha`、`test_gateway_stream_endings`、`test_initialize_generation`）135：全過 | `v2/full-suite-groups.txt` |
| HM-01 守門（綠那輪另外一起跑） | 45 passed | `green-all-products.txt` |
| `secret_precheck.py --full`（gitleaks 8.28.0，base `origin/claude-delivery`） | OK，0 findings（本分支 4 個 commit、HEAD tree、整個歷史） | `v2/secret-precheck.txt` |
| `ledger_precheck.py --base origin/claude-delivery` | OK：三本帳 0 漂移；改到的檔沒有列管的；`health.py` 列成「沒列管、要人看」 | `v2/ledger-precheck.txt` |
| `packaging/validate.py`（ci-venv 的 Python） | PASS | `v2/packaging-validate.txt` |
| `scripts/tool_inventory.py` | 0 漂移（exit 0） | `v2/tool-inventory.txt` |
| packaging unittest（`discover -s packaging -p 'test_*.py'`，同 CI） | ci-venv：182 過、5 skip（要 root），沒有 httpx 載不進來的 2 個模組用 repo 的 `.venv` 跑 13＋3 案 OK，合計 203 案 | `v2/packaging-unittest-full.txt`、`v2/packaging-unittest.txt` |

第一輪（只修開通的產品，`269f5a5` 上；留作根因與重現的證據）：

| 檢查 | 結果 | 證據 |
|---|---|---|
| 真的 HM-20 `[False]`，修正前 30 次 | 30 過（本機打不到時間點，第 3.2 節） | `repro-claude-delivery-269f5a5/` |
| 真的 HM-20 `[False]`，修正後 10 次（同一個診斷外掛） | 10 過；10 次取消時 B 都在 `_pause`，`_stop_monitors` 都在 0.5 秒內回來 | `after-fix-hm20-false-81cc766/` |
| 逐一打候選點 | 見第 3.3 節 | `repro-candidates-before-fix.txt`／`.json` |
| 全套 pytest（`81cc766`） | 5619 案：5612 過、7 失敗（都是要 root 的既有案例）、0 skip | `full-suite.txt`、`full-suite-junit.xml` |
| 相關檔（HM-01 守門、health 三檔、lifecycle、loopback、runtime 三檔） | 45、62、28、153、106 passed | `related/`、`related-health-files.txt` |
| packaging unittest（`discover -s packaging`，同 CI） | ci-venv 182 過、5 skip（要 root），沒有 httpx 載不進來的 2 個模組用 repo 的 `.venv` 跑 13＋3 案 OK，合計 203 案 | `packaging-unittest-full.txt`、`packaging-unittest-two-with-repo-venv.txt` |

本機一定失敗的既有案例（要 root）：`test_owned_executable` 的 uid10001、`test_profile_store::test_mode_and_owner_as_the_add_on_user`、
`test_restore_detection` 的 `test_root_*` ×5。暫存目錄（`/tmp/ha-mp-*`）每次用完都刪了，清單在證據目錄的 `tmpdirs.txt`。

## 8. rebase 與 commit

- 第一輪的 5 個 commit 先 rebase 到 `d00a338`（`git fetch origin` 後 `git rebase origin/claude-delivery`）：只有契約第 10 節衝突
  （HM-14、HM-10 在表尾加的列），兩邊都留、本片的列接在最後；驗收表自動合併。
- 使用者改成全部產品都修之後，還沒 push，所以把整片重排成 4 個 commit：測試（只有它時 13 案全紅）、修正、契約與驗收表、本筆記。
  第一輪「只修開通」的中間狀態不留在歷史裡，過程寫在本筆記（第 4、5 節）。
- 帳本：本分支沒動列管的檔；`ledger_precheck` 照算（第 7 節）。

## 9. 和 HM-30、HM-31 的衝突評估

唯讀看了兩個 clone（沒改、沒 fetch）：

- **HM-30**（`ha-mp-hm30-20261116`，`5b6d4a5`）：`health.py` 沒改，`profile_runtime.py` 只加回覆工作執行緒的參數，沒碰 `_monitor`、
  `_watched`、`_stop_monitors`；本修正只改 `health.py`，沒有文字衝突。「time the health checks from when they were due」（`33798ad`）
  只改測試與驗收表。HM-30 不會讓 bug 消失或變嚴重：吃掉取消的是 anyio 的連線，它沒動健康檢查的請求；回覆移到工作執行緒後事件迴圈比較閒，
  打中的機率最多小一點。HM-30 的 `run_product.run` 仍在 `run()` 裡 `monitor.cancel()`，本檔的 SIGTERM 測試照樣適用；它給
  `multi_profile_runtime` 加的 `may_stop`、`Runtime.task` 是選用參數，不衝突。文件只有契約第 10 節、驗收表各加一列，接起來即可。
- **HM-31**（`ha-mp-hm31-20261116`，`a0ed01a`）：`health.py` 沒改；`profile_runtime.py` 只加請求內容預算的參數。契約第 1.2 節兩邊都會加
  「不受開關管」的項目（同一句清單），rebase 時兩邊都留；第 10 節同樣只是表尾加列。

## 10. 沒處理的

- **上游**：anyio 4.15.1 的 `CancelScope.__exit__` 只看訊息決定吞不吞，沒有看宿主 task 還有沒有別人的取消要求；CPython 3.13 把同一步裡的
  多個取消併成一個例外。這裡沒有回報上游（不准連外），也沒升級套件、沒動 `uv.lock`。升級 anyio 時要重看 `test_monitor_cancel.py`
  的前提斷言，必要時改測試的掛鉤點。
- 面板的後端測試（`test_saved`）跑在請求的 task 裡，沒加這個判斷：它的取消被吞只會讓那次測試做完才回，不拖住關閉。
- 各產品下一版的 CHANGELOG 由發版片寫（第 4 節的句子）。
- PaaS（`d7f5849`）沒有常駐的 httpx 健康監看迴圈，沒有要回補的對應項目。
