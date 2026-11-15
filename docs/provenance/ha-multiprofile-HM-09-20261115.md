# HA 多帳號 HM-09 provenance：子程式生命週期（port、看門狗、錯開啟動、停機）（2026-11-15）

## 結論

- **獨立審查判定「修正後通過」（必修 2 項、建議 12 項），都處理了**（處理表在第 15 節；沒有碰到待定題）：
  - MF-1 基準過時：本片先 rebase 到 HM-08 的最終 head `adfc4bf`（HM-08 已在 18:05 以 #99 合併，`claude-delivery` `b5d10c5` 的 tree 和它
    相同），只重放本片的 5 個 commit；3 處衝突照審查的三點解（第 14.1 節），帳本照實際內容重算。`claude-delivery` 之後又合併 #100
    （`51bc4b7`，19:10），開 PR 前再 rebase 到 `51bc4b7`（第 14.2 節）：只有 `decisions.md` 衝突，以 `claude-delivery` 的版本為底改成
    34 題已定、12 題待定。第一次 rebase 後重跑全套 pytest、兩個預檢、`validate.py`、packaging unittest、突變 M34；第二次只帶進 #100 的
    workflow 與 `decisions.md`（`tests/` 裡沒有測試讀這兩個檔），之後照實際內容核對帳本，重跑兩個預檢、`validate.py`、packaging unittest
    與 tool-surface，全套以 CI 為準。
  - MF-2 三個執行面沒有測試擋得住：收進審查的 E8、E9、E10（E9 另加面板的 `child/restart`），DQ-21 測試改成比對新的子程式世代；
    `acceptance-matrix.md` 的 HM-09 列照實際涵蓋範圍改寫。突變 R40、R19、R41 現在都擋下。
  - 建議：S-1～S-7、S-10、S-12 的 (1)(3)(4) 改了程式或測試；S-8、S-11、S-12 (2) 寫進第 13.2 節的交接；S-9 的五個解讀與 S-1、S-6 的兩個
    PaaS 差異在 PR 說明逐條點名，請使用者看過。
- **產品沒開通時，行為一行都不變**：Supervisor 照舊「同一次啟動最多 4 次（約 1、2、4 秒間隔）、跑多久都不歸零、之後 failed」，不寫 log、
  不做 spawn 前檢查、不經包裝器；健康監看照舊每 15 秒一次、一次失敗就判 unreachable、不退避、子程式什麼狀態都照探；`child/restart` 的回應
  照舊。HM-01 的黃金回歸、兩個契約凍結照過（開關關與開兩種都跑），斷言一個字都沒改。repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開），每個帳號（含預設帳號）：
  - **看門狗照 PaaS**（DQ-20 (b)）：異常結束、spawn 失敗、spawn 前檢查拒絕，都照 2、5、15、30、60、120、300 秒退避，之後一直 300 秒、
    不限次數；連續跑 120 秒（含）以上歸零。spawn 失敗也重試是本片和 PaaS 的差異（契約 §9 #14；審查 S-1 要使用者看過）。
  - **spawn 前檢查**：port 是 add-on 自己的 listener（8081、8099）或別的帳號執行中的子程式在用 → `blocked`＋`child_port_conflict`；
    試綁 127.0.0.1、0.0.0.0、::1、::（照 PaaS `port_occupied`）失敗 → `blocked`＋`child_port_in_use`；這兩種照看門狗退避重試，
    port 放開就自動恢復（T-15）。檢查本身出錯也當拒絕（fail closed）。IPv6 試綁被平台擋（EACCES、EPERM）時跳過那個位址並記一行
    WARNING（審查 S-6；PaaS 當成被佔；契約 §9 #89）。索引內重複或等於 3000 的帳號（HM-07 `port_conflicts`）開啟時就 `disabled`，
    起子程式時 `blocked`＋`child_port_conflict`、不試綁、不重試，索引變了（`reevaluate()`）才重評（修 PaaS B-17）。被擋的子程式不 spawn，
    健康監看也不送任何東西到那個 port（搶 port 的程式收到 0 筆）。
  - **錯開啟動**：預設帳號照今天在 listener 之前起；額外帳號等預設帳號第一次健康檢查通過或 30 秒後，依索引順序、同時最多 2 個在起，
    名額在「子程式回了健康檢查」「不在起了（被擋、沒設定、spec 失敗、子程式結束）」或 30 秒時讓出，壞的標記、不擋其他（某個帳號的啟動
    或等待丟例外時記一行、其他照起：審查 S-12）。
  - **並行停**：關閉時所有子程式同時停（6 個都要 SIGKILL 的子程式約 3 秒收完，HA 上限 30 秒）。
  - **健康監看**（DQ-25，2026-11-15 11:2x 使用者採用建議）：每帳號自己的 client、起點錯開（預設帳號開機就查；第 k 個額外帳號在自己的
    子程式起好後 15×(1＋k÷(產品上限＋1)) 秒）、間隔不變 15 秒；後端認證被拒時 15→30→60→120→300 秒退避，存檔與面板重啟歸零；開通後
    連兩次失敗才判 unreachable。
  - **監看失敗**（DQ-21，同時採用建議）：額外帳號的監看停止只標記該帳號 `failed`（停它的子程式），其他帳號與 add-on 照常，存檔或
    `child/restart` 後子程式與監看一起恢復；預設帳號維持今天：監看停止就讓 add-on 結束，由 Supervisor 重啟。
  - **額外帳號子程式**：`oom_score_adj` 500、`nice` +5，由子程式在 exec 前自己寫（`python -I -S -c` 的包裝器，不用 `preexec_fn`）；
    寫不進去、或沒有直譯器可跑包裝器，就照起、記一行 WARNING，不假設。存檔與面板重啟時讀 MemAvailable，不夠就存檔、不起
    （`blocked`＋`memory_capacity`）；開機與看門狗不查；讀得到 cgroup `memory.max` 時改用 PaaS 公式。
  - **log 事件**（契約第 7 節）：`MCP child [profile=<id 前 8 碼> port=<p> pid=<n>]: …`，每帳號每情況 60 秒一行（`suppressed=N`）。
  - `child/restart` 的 202 回應多 `blocked_reason`（修 PaaS B-22）。
- 新測試 5 檔 119 案（實作時 107 案，審查後加 11 案、改 6 案，複查時再加 1 案）＋測試工具 2 檔；改 3 個既有測試檔。**先寫測試**：實作前新 5 檔 103 案裡
  100 失敗、3 通過；審查後的測試先 commit（`1f4193a`），在修正前的程式上 118 案 4 失敗、114 通過（失敗的正是程式修正要擋的 4 案）（第 4.3 節）。臨時突變：實作時 46 個全部擋下
  （第 4.2 節）；審查後 18 個，17 個擋下；R03b 第一次卡住（第 10 案，不是停機測試），在兩個測試工具的關閉加上 30 秒上限後重跑擋下（32.8 秒；改跑 HM-08 的 `test_profile_routing.py` 也擋下，32.3 秒）（第 4.4 節）。
- **複查時找到並修好測試工具的一個偶發失敗**（第 4.5 節）：`free_port()` 連續兩次可能拿到同一個 port（本機 2 萬次「連抽三個」有 5 次重複），
  同一個 rig 的兩個帳號就同 port：預設帳號的就緒檢查打到 B 的替身子程式（401），`start_all` 等滿 30 秒，
  `test_removing_a_profile_stops_its_monitor_and_its_child` 在 10 秒逾時。強制同 port 重現後，`free_port()` 改成不再發最近發過的 port，
  補 `test_a_rig_never_gives_two_profiles_one_port`（舊寫法紅、新寫法綠）。只改 `tests/`，沒動正式程式。
- 兩個預檢（base `origin/claude-delivery`＝`51bc4b7`）：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest（rebase 前的 `62b5186`，程式與帳本和最後的 head 相同）：5395 案、0 skip、31 分 08 秒（1,869 秒）：5388 通過，7 個失敗都是已知要 root 的既有案例；之後只改兩個測試工具（用到它們的 9 個檔連跑兩次全過）與文件（第 5、6 節）。
- `decisions.md` 記 DQ-21、DQ-25（rebase 到 `claude-delivery` 後是 34 題已定、12 題待定）；契約第 7 節的「待定」改成已定並寫明本片的做法（第 3.10 節）。
- 平台事實都在執行時讀，做不到就降級並記一行 WARNING；HM-03a 要確認的項目在第 11 節（審查後補了試綁的 errno 與 `oom_score_adj` 基準）。
  rebase 到 `claude-delivery` 之後 push 並開 PR（不合併；主對話在 CI 全綠後合併）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-09（計畫 §12.3；風險中、工作量 L；不是「審查」片） |
| 分支 | `feat/ha-multiprofile-hm09-20261115`（一般 clone）。修正階段先 rebase 到 HM-08 的最終 head `adfc4bf`（只重放本片的 5 個 commit），加審查修正與複查的 7 個 commit（第 15.2 節），開 PR 前再 rebase 到 `claude-delivery` `51bc4b7`（第 14.2 節）；加上本筆記最後一個 commit 共 13 個 |
| 基準 | `claude-delivery` `51bc4b7`：#100 在 2026-11-15 19:10 合併（`checks` 上限 40→60 分鐘、`decisions.md` 記 DQ-13／14／30／31／43）；它的前一個是 #99 在 18:05 把 HM-08 的最終 head `adfc4bf` 合併成的 `b5d10c5`（兩者 tree 都是 `f9f4e6e`）：HM-00、01、02、04、05、06、07、08、13a、17 都已合併。2026-11-16 開 PR 前 `git fetch` 時 `claude-delivery` 仍是 `51bc4b7` |
| 依據 | 計畫 §5.4、§3.3、§7.1、§7.2 第 5 點、§10.1、§10.3 的 HM-09 列、§12.0、§12.3 HM-09；契約 §1.2、§3.1、§3.6、§5、§7、§9 #14、#18、#19、#29、#53；驗收矩陣 T-13、T-14、T-15、T-17、T-18；FM-13、25、37、38、39、40、45、46、68、69、133、134、137、138；C2-SF-3、SF-4、SF-5、SF-10、C2-MF-4 第 3 點、C3-MF-1、C3-SF-3、C4-SF-6；HM-04～HM-08 的 provenance 筆記交給 HM-09 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425`：`process.py`（`AUTO_RESTART_DELAYS`、`STABLE_SECONDS`、`_schedule_auto_restart`、`_port_refusal`、`CHILD_PORT_CONFLICT`、`CHILD_PORT_IN_USE`、`_tag`）、`child_identity.py`（`port_occupied`、exec 包裝器的寫法）、`profiles.py`（`port_conflict`、`start_all`、`_memory_limit_mib`、容量公式）。到 `cf3d0d5` 這幾個檔都沒變（第 9 節） |
| 獨立審查 | `artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-09.md`（repo 外；證據在同層的 `evidence-review-HM-09/`）：修正後通過，必修 2、建議 12（第 15 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/lifecycle.py`（HM-09 起列管：審查 S-10） | `Supervisor` 多 keyword-only 的 `delays`、`max_attempts`、`stable_seconds`（看門狗；`WATCHDOG`＝PaaS 的值）、`preflight`（spawn 前檢查）、`log`（`ChildLog`）、`resources`（`ChildResources`）；新屬性 `blocked_reason`、`failures`、`retry_in`、`resource_state`、`clock`；新方法 `block()`、`retry_now()`、`give_up()`；一次 spawn 抽成 `_attempt()`，舊的有界迴圈照舊（`_run`），看門狗另走 `_watch()`；`EXEC_WRAPPER`（exec 前寫 `oom_score_adj` 與 `nice`）；`LifecycleLog`、`ChildLog`（每帳號每情況 60 秒一行）；原因碼常數 `CHILD_PORT_CONFLICT`、`CHILD_PORT_IN_USE`、`MEMORY_CAPACITY`。審查 S-12：`sys.executable` 是空的（沒有直譯器可跑包裝器）時照直接起、`resource_state` 記兩項沒做到、記一行 WARNING |
| `Hc/health.py`（沒列管） | `HealthMonitor` 多 keyword-only 的 `first_check_after`、`tolerance`、`auth_backoff`、`own_child_only`、`log`；`HEALTH_INTERVAL`、`AUTH_BACKOFF`、`auth_refused()`；`next_interval()`、`reset()`、`settle()`（有檢查在跑就等它的結果，不再探）；`test_saved` 照實回這次的結果；選項都不給時 `run()` 照舊（`asyncio.sleep(15)`） |
| `Hc/profiles.py` | `port_occupied()`（四種位址試綁）、`allocate_port(occupied=)`（不給時照 HM-07 不綁）、`memory_limit_mib()`、`available_memory_mib()`；說明文字。審查 S-6：IPv6 試綁遇到 EACCES、EPERM 時跳過那個位址，每個位址與 errno 每個程序一行 WARNING（`REFUSED_IPV6_BINDS`） |
| `Hc/profile_runtime.py` | `ProfileRuntime` 多 keyword-only 的 `hold`、`monitor_options`、`report_blocked`（不給時照舊）；`launch()`／`backend_changed()` 共用 `_relaunch`；沒設定連線時記缺哪些欄位（只列名稱）。`ProfileManager`：每帳號的看門狗、spawn 前檢查（`spawn_refusal`）、額外帳號的資源與 `_hold`（disabled、記憶體）、監看選項；`start_all()`、`stop_all()`、`monitor()`（DQ-21 的隔離）、`reevaluate()`、`free_port()`、`start_profile()`、`started`、`events`、`capacity`、`memory_limit`；開啟時讀 cgroup 記憶體上限；關閉時先 `stop_all()`。審查 S-12：`start_all` 裡某個帳號的啟動或就緒等待丟例外時記一行（`_start_failed`）、讓出名額、其他照起；那個帳號的監看在啟動結束後照起 |
| `Hc/gateway.py` | `make_apps` 多一個 keyword-only 的 `child_blocked`（只在開通的產品給）：`child/restart` 的 202 回應多 `blocked_reason` |
| `Hc/run_product.py` | 只改註解（`launch()`／`monitor()`／關閉現在做什麼）；程式一行沒改 |
| `tests/test_profile_lifecycle.py`（新，28 案） | 沒開通照舊 4 次後 failed、run_product 給預設帳號的 Supervisor 沒有任何新選項；看門狗表、不放棄、有上限時 failed、真的等、120 秒歸零（可控時鐘）、退避中停止立刻結束；spawn 失敗照退避重試（帶與不帶資源包裝；審查 E2）；T-13（SIGKILL 5 次、其他帳號 PID 不變、log）；log 事件的文字與節流；沒設定連線時列欄位名；並行停（`stop_all` 與關閉，各有 15 秒上限：審查 S-3）；DQ-21 兩種（額外帳號的監看停止後，面板重啟讓監看恢復並檢查新的子程式世代：審查 E10）；`remove()` 停掉該帳號的監看與子程式（審查 S-4）；`monitor()` 起額外帳號；開通的 run_product 走 `launch`→`monitor`→`stop_all` |
| `tests/test_profile_ports.py`（新，29 案） | 配 port；測試工具不讓同一個 rig 的兩個帳號同 port（複查，第 4.5 節）；四種位址各兩種 socket 的試綁；IPv6 試綁被平台擋（EACCES、EPERM）時跳過並記一行、IPv4 被擋仍當被佔（審查 S-6）；8081／8099；索引重複與 3000；別帳號在跑的子程式；spawn 前檢查本身丟例外時不起（審查 E3）；被佔時退避、第 8 次退避之後放開仍恢復；子程式當掉時 port 被搶、搶的程式收到 0 筆；索引變更後立刻重評三種（新變 disabled 的立刻停：審查 S-4）；`child/restart` 的 `blocked_reason`（開與關） |
| `tests/test_health_backoff.py`（新，41 案） | 退避表與間隔；各子程式認證被拒的文字（釘到原始碼）與 13 種不算的；退避 15→300、歸零、子程式沒回的檢查不動它（審查 S-12）；`run()` 照退避等（要求的秒數逐一比對、實際間隔只比下限：審查 S-7）；`reset()` 叫醒等待；面板存檔與 `child/restart` 經 `_relaunch` 歸零（審查 E9）；log 一分鐘一行；連兩次失敗（含新子程式世代、子程式沒回的檢查、面板的 `backend/test`、經閘道的 tools/call）；沒開通一次就判；`settle()` 等執行中的檢查；起點錯開的值、`run()` 真的等到起點（審查 E8）與自己的 client；五種不在跑的狀態都不探；沒開通照探、迴圈照舊 |
| `tests/test_staggered_start.py`（新，9 案） | 常數；預設先、同時最多 2 個、名額怎麼讓出；已回過健康檢查的不再查、執行中的檢查等它不另探；30 秒逾時；起不來的不擋人；某個帳號的等待丟例外時記一行、其他照起（審查 S-12）；disabled 不起；listener 在額外帳號還在起時就服務預設帳號 |
| `tests/test_extra_child_resources.py`（新，12 案） | 只有額外帳號經包裝器、exec 後的 cmdline 是真正的指令；包裝器不改 argv、環境、工作目錄、訊號；沒有直譯器可跑包裝器時照起並記一行（審查 S-12）；邊界；以非特權使用者（root 時是 uid 10001）拿到 500 與「加 5」（探針先把自己的 nice 加 2，子程式要是 7：審查 S-5）、拿不到時降級並一行 WARNING；記憶體檢查的時機與讀不到；cgroup 公式；讀檔；FD 不外洩；沒有 FD 預算時只起預設帳號 |
| `tests/lifecycle_runtime.py`（新，測試工具） | 開通的 `ProfileManager`＋真 Supervisor＋真的睡覺子程式（可以 SIGKILL、可以忽略 SIGTERM）＋每帳號 MockTransport；所有 port 都是臨時 port；關閉（`aclose`，先 `stop_all`）限 30 秒（審查 S-3） |
| `tests/child_resources_probe.py`（新，測試工具） | root 時先寫自己的 `oom_score_adj` 基準（200，同 Docker 給 add-on），降到 uid 10001 再起 Supervisor；起之前先把自己的 nice 加 `raise_nice`（審查 S-5）；回報子程式自己看到的值 |
| `tests/multi_profile_runtime.py` | HM-08 的測試工具：改成等 `ProfileManager` 自己起完額外帳號（`started`），不再自己 `launch()`；`STAGGER_SECONDS` 預設 0.05（沒回健康檢查的額外帳號立刻讓出名額，HM-08 的測試照舊一開始就起全部）；可指定 `stagger`；run_product 停機限 30 秒（`CLOSE_SECONDS`，審查 S-3：stop_all 卡住時讓測試失敗，不佔住整輪）；`free_port()` 不再發最近發過的 256 個 port（複查：連續兩次 bind port 0 可能拿到同一個，同一個 rig 的兩個帳號就同 port，第 4.5 節） |
| `tests/test_reply_mask_union.py` | HM-08 的一案：B 的健康原因要連兩次失敗才判 unreachable（DQ-25），多查一次 |
| `tests/test_profile_runtime.py` | HM-05 的兩案：`make_apps` 與 `app_options` 的名單加 `child_blocked` |
| `docs/multi-profile/decisions.md` | DQ-21、DQ-25 移到第 1 節（2026-11-15 11:2x 使用者採用建議），變更紀錄一列，題數 29／17 |
| `docs/multi-profile/contract.md` | 第 5 節記憶體檢查、第 7 節（DQ-21、DQ-25 改已定＋本片定的做法）、第 9 節 #14（spawn 失敗也重試）、第 10 節一列。審查後：第 7 節 port、錯開啟動、資源、log 事件四列（S-6、S-12）；第 9 節加第 89 列（S-6）並在說明寫明 #14 的附註出自 HM-09；第 10 節再一列 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表 HM-09 的五列與 HM-30 的 `test_health_tolerance.py` 說明（連兩次失敗的規則本片已做）。審查 MF-2：HM-09 五列照實際涵蓋範圍改寫（原本寫了「起點錯開」，但只驗屬性值） |
| `docs/provenance/runtime-patches.json` | 4 個列管檔照實際內容重算摘要並補說明（`gateway.py`、`run_product.py`、`profile_runtime.py`、`profiles.py`；rebase 後重算，審查修正後 `profile_runtime.py`、`profiles.py` 再算一次）；`lifecycle.py` 加進帳本（審查 S-10） |
| `docs/multi-profile/ledger-tracking.md` | 審查 S-10：`lifecycle.py` 從第 3 節（不列管）移到第 2 節（已列管）；`health.py` 維持不列管 |
| 本筆記 | — |

沒改：`products.py`、`configuration.py`、`profile_router.py`、`apps/`、`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、
`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、workflow、`tests/conftest.py`、HM-01 的守門測試檔。
`lifecycle.py` 依審查 S-10 改成列管（`EXEC_WRAPPER` 在每個額外帳號子程式 fork 之後、exec 之前執行）；`health.py` 審查沒有要求，照
`docs/multi-profile/ledger-tracking.md` 第 3 節維持不列管。本片沒有新模組。

## 3. 設計重點

### 3.1 看門狗（計畫 §5.4；契約 §7；DQ-20 (b)；FM-137；T-13）

- `Supervisor(spec, delays=…, max_attempts=…, stable_seconds=…)`：給了 `delays` 才是看門狗；不給就是今天的有界迴圈（`retries`＋1 次、
  `min(30, backoff×2^n)×uniform(1, 1.2)` 秒、不歸零、之後 `failed`），程式路徑和 HM-09 之前一樣（`_run` 只把一次 spawn 抽成 `_attempt()`）。
- `lifecycle.WATCHDOG`＝`{'delays': (2, 5, 15, 30, 60, 120, 300), 'max_attempts': None, 'stable_seconds': 120}`（PaaS `AUTO_RESTART_DELAYS`、
  `STABLE_SECONDS`）。算法照 PaaS `_schedule_auto_restart`：每次失敗（結束、spawn 失敗、spawn 前檢查拒絕）用表的下一格（用完就一直是最後一格）；
  剛結束的那次跑了 `stable_seconds`（含）以上就從頭算。PaaS 也一樣不因手動重啟歸零。
- 開通的產品每個帳號（含預設）都拿 `WATCHDOG`（`ProfileManager.add`）；沒開通時 run_product 照 HM-05 建 `ProfileRuntime(lifecycle={})`，
  Supervisor 沒有任何新選項（`test_switched_off_run_product_gives_the_default_profile_todays_supervisor`，7 個產品）。
- 狀態：退避中 `backoff`、被擋 `blocked`（`blocked_reason`）、`retry_in`＝現在在等的秒數。`retry_now()` 結束現在的等待（`reevaluate()` 用）。
- `clock`（預設 `time.monotonic`）只用來量「這次跑了多久」，測試換成可控時鐘證明 119 秒不歸零、120 秒歸零。

### 3.2 spawn 前檢查與 port（計畫 §5.4；契約 §7、§8；FM-38、39、40；T-15）

- `Supervisor(preflight=…)`：每次 spawn 前（第一次在 `start()` 裡同步做，所以 `child/restart` 回應時就知道結果；之後每次退避完再做一次）。
  回 `(原因碼, 固定說明)` 就不 spawn、`status=blocked`、記一行、照看門狗退避；檢查本身丟例外也當拒絕（`child_port_in_use`，fail closed）。
- `ProfileManager.spawn_refusal(profile_id)`（照 PaaS `_port_refusal`＋`ProfileRegistry.port_conflict`）：
  1. port 是 add-on 的 listener（`profiles.LISTENER_PORTS`＝8081、8099）→ `child_port_conflict`（HM-07 審查 MF-1：索引不列，這裡擋）；
  2. 別的帳號的子程式還在（`supervisor.process` 不是 None，包含還沒收完的前一代）而且用同一個 port → `child_port_conflict`；
  3. `profiles.port_occupied(port)` 試綁失敗 → `child_port_in_use`（說明只有位址族與 errno 名稱）。
  預設帳號也查（PaaS 也查），這樣預設帳號的 3000 被別的程式佔住時，健康監看也不會把 child bearer 送過去。
- `profiles.port_occupied`：照 PaaS 逐行移植意思（沒搬程式碼）：SO_REUSEADDR 試綁 127.0.0.1、0.0.0.0、::1、::（v6only），沒有 IPv6 就跳過。
  測試行程裡 `tests/owned_network.py` 不准綁 3000 與 18000～18099，所以每個測試都用臨時 port；守門丟的例外不是 `OSError`，不會被當成「沒人佔」
  （`test_the_test_bind_never_touches_a_production_child_port_in_these_tests`）。
- 索引本身的衝突（重複、等於 3000）照 HM-07 在開啟時就 `disabled_reason=port_conflict`：這種帳號不 spawn、不試綁、不重試（index 不變就不會好），
  `reevaluate()` 才重評。
- 配 port：`profiles.allocate_port(taken, occupied=profiles.port_occupied)` 跳過試綁失敗的；不給 `occupied` 時照 HM-07 不綁（HM-07 的測試照過）。
  `ProfileManager.free_port()` 給 HM-10 建帳號用：避開預設子程式 port、索引與登錄帳號的 port、3000／8081／8099。
- 審查 S-6（平台事實不假設）：IPv6 試綁遇到 EACCES、EPERM（AppArmor、seccomp 擋 bind）時跳過那個位址，每個位址與 errno 每個程序
  記一行 WARNING（logger `mcp_admin_core.profiles`）；IPv4 任何失敗仍當被佔。PaaS 會把它當成被佔：在擋 IPv6 bind 的平台上，開通後
  連預設帳號的子程式都永遠起不來，log 只說「另一個 socket 綁著」。跳過不會漏掉佔用者：子程式只綁 127.0.0.1，閘道與監看也只連
  127.0.0.1；別的程式的雙棧 socket 仍會讓 0.0.0.0 的試綁失敗。HM-03a 要在 add-on 容器實際試綁四種位址並記下 errno（第 11 節）。

### 3.3 錯開啟動與停機（計畫 §5.4；C2-SF-4；FM-46、133；T-14、T-17）

- run_product 照舊：`await profile.launch()`（預設帳號的子程式，在 listener 之前）→ listener → `monitor()` 任務。`ProfileManager.monitor()` 裡跑
  `start_all()`，所以 listener 一開始就服務預設帳號，額外帳號在背景依序起（`test_the_listeners_serve_the_default_profile_while_the_others_start`）。
- `start_all()`：先等預設帳號第一次健康檢查通過或 30 秒；再依索引順序、同時最多 2 個（`STAGGER_SLOTS`）；一個名額在「子程式回了健康檢查
  （`availability()['ready']`）」「不在 starting／running（被擋、沒設定、spec 失敗、結束退避中）」或 `STAGGER_SECONDS`（30 秒）時讓出。
  等的時候每 0.5 秒查一次；還沒 spawn（`starting`）時每 0.02 秒看一下。子程式還沒聽 port 時查詢只是連線被拒，後端沒有任何登入。
  已經回過健康檢查的子程式不再查；監看的檢查正在跑時等它的結果（`HealthMonitor.settle()`），不緊接著再探一次（設定好的子程式每次檢查都會
  登入後端一次）。
- `stop_all()`：先停額外帳號的監看，再 `asyncio.gather` 所有 Supervisor 的 `stop()`；`aclose()` 也先 `stop_all()` 再關各帳號的 runtime。
  每個子程式最壞約 3 秒寬限＋4 秒 SIGKILL 後等待＋1 秒輸出，並行時就是一個子程式的時間（測試：6 個都忽略 SIGTERM 的子程式 3.0～6 秒內收完）。
- 審查 S-12：`start_all` 裡某個帳號的啟動（`launch()` 本身不丟例外）或就緒等待丟例外時，記一行（`its staggered start failed
  (<例外類別>); the other profiles start anyway`）、讓出名額，其他帳號照起，`started` 照設；預設帳號的等待也一樣。目前找不到會丟的路
  （`_check_saved` 吃掉 `ConfigError`、`_check` 吃掉其他例外），這是「壞的標記、不擋其他」的保險。那個帳號的監看在它的啟動結束後照起
  （取消時不起）。

### 3.4 健康監看（DQ-25；契約 §7；§8.8 #18；FM-68、69、91；C2-MF-4 第 3 點）

- 每帳號一個 `HealthMonitor`，用自己帳號 runtime 的 child client（HM-05／HM-08 已經每帳號一個；本片測試確認 4 個帳號 4 個不同的 client）。
- 起點：預設帳號 `first_check_after=0`（開機就查，同今天）；第 k 個額外帳號 15×(1＋k÷(產品上限＋1)) 秒（Odoo 17.5、20、22.5…）。額外帳號的監看在
  `start_all` 把它的子程式起好之後才開始，`start_all` 的就緒檢查就是它的第一次檢查；之後間隔照舊 15 秒。
- 認證被拒：探測原因的開頭是各子程式固定的認證失敗文字（`health.AUTH_REFUSED`；測試把每段文字釘到子程式原始碼，原始碼改了測試就失敗）：
  Odoo、Hermes `BACKEND_AUTH_REJECTED`；Headscale `HEADSCALE_INVALID_CREDENTIAL`；Nextcloud `BACKEND_HTTP_ERROR status=401` 與登入失敗後的節流
  `status=429`；EMQX `EMQX rejected the API credentials (401)`；LiteLLM `LiteLLM rejected the credentials (401 `。連續被拒 n 次後下一次等
  `AUTH_BACKOFF[min(n-1, 4)]`＝15、30、60、120、300 秒；子程式回了別的答案就歸零（子程式沒回的檢查不動它）；存檔與面板重啟（新憑證）
  `reset()`：歸零、正在等的退避縮成 15 秒內。照這個表，一個帳密錯的帳號第一分鐘最多 3 次登入失敗（Odoo 18 預設累積 5 次失敗後，每次失敗
  都讓同一個來源 IP 冷卻 60 秒），之後最多每 5 分鐘一次：減少、但不能完全避免波及同一個 Odoo 的其他帳號（HM-19b 驗收第 10 點實測）。
- 連兩次失敗：判定「unreachable」（閘道拒絕 tools/call 的條件是「子程式有回、後端不通」）要同一個子程式世代連續兩次這種檢查；第一次維持前一次的判定
  （之前通就 reachable，剛起還沒判定就 unknown，都不拒絕）。子程式沒回的檢查照今天記成未就緒（本來就不拒絕 tools/call），不算一次也不打斷連續。
  面板的 `backend/test` 照實回這次的結果（`test_saved`），但它也算一次。
- 子程式不在 running（被擋、退避、failed、stopped、還沒 spawn）就不送任何東西，判定 `unknown`（T-15：port 可能是別的程式的）。
- 沒開通（選項都不給）：`run()` 照舊 `check(); asyncio.sleep(15)`，一次失敗就判，不退避，任何狀態都照探（測試鎖住）。

### 3.5 監看失敗（DQ-21）

- `ProfileManager.monitor()` 的結束只跟著預設帳號的監看：它丟例外，`monitor()` 就帶著同一個例外結束，run_product 照今天拋 `runtime component stopped`、
  add-on 結束、Supervisor 重啟（`test_the_default_profiles_monitor_stopping_ends_the_add_ons_monitoring`）。
- 額外帳號的監看各自一個任務（`_watched`）：結束時記一行 WARNING、`Supervisor.give_up()`（停子程式、標 `failed`），其他帳號的子程式與監看、
  `monitor()` 都照常；之後等到這個帳號的子程式被存檔或 `child/restart` 再起來，監看也跟著再跑。為什麼停子程式：監看停了，這個帳號的可用性
  判斷就不再更新，閘道不能照舊轉送；`failed` 也是「沒在跑」的意思。

### 3.6 額外帳號子程式的資源（計畫 §5.4；C2-SF-10；C4-SF-6）

- `ChildResources(oom_score_adj=500, nice=5)`（`EXTRA_CHILD_RESOURCES`）只給額外帳號；預設帳號的子程式照今天直接 spawn（argv、環境不變，
  HM-04 的快照照過）。
- 寫法：`sys.executable -I -S -c EXEC_WRAPPER <管線> 500 5 <原 LC_CTYPE> <程式> <原 argv…>`。包裝器是 fork 之後的全新單執行緒直譯器（管理程序
  有執行緒，`preexec_fn` 不安全；PaaS `child_identity` 也是這樣包），寫 `/proc/self/oom_score_adj`（絕對值）、`setpriority(+5)`，把做到的寫進
  管線（`o`、`n`）後關掉，還原自己啟動時改的東西（PEP 538 加的 `LC_CTYPE`；被設成忽略的 SIGPIPE、SIGXFZ、SIGXFSZ），再 `execv` 真正的指令
  （同一個 PID、同一個 process group，環境原封不動）。測試比對同一個 `/bin/sh` 子程式直接起與經包裝器起：argv、環境、工作目錄、忽略與阻擋的訊號
  都一樣；exec 之後 `/proc/<pid>/cmdline` 就是真正的指令。
- Supervisor 讀管線（最多 5 秒）：`resource_state`＝`{'oom_score_adj': bool, 'nice': bool}`；沒做到的記一行 WARNING
  `child resources not applied (oom_score_adj 500, nice +5); it runs without them`，子程式照跑（不假設、不擋）。
- 非特權證明：`tests/child_resources_probe.py`。測試以 root 跑（CI）時，探針先以 root 把自己的 `oom_score_adj` 寫成 200（特權寫入同時設下非特權
  程序不能低於的下限，和 Docker 給 add-on 的一樣），降到 uid／gid 10001、沒有附加群組與能力，才起 Supervisor：子程式自己讀到 500 與 nice＋5；
  換成非特權程序永遠做不到的值（`oom_score_adj` −1000、nice −5）時照起、兩項都記沒做到、一行 WARNING。不是 root（本機）時以本機使用者跑同一個探針。
  審查 S-5：探針起 Supervisor 前先把自己的 nice 加 2，所以「加 5」（7）和「設成 5」分得出來。
- 審查 S-12：`sys.executable` 是空的（Python 說不出自己的直譯器）時沒有東西可跑包裝器：子程式照直接起（同預設帳號），`resource_state`
  記兩項都沒做到，記一行 `child resources not applied (oom_score_adj 500, nice +5: no interpreter for the wrapper); it runs without them`。

### 3.7 記憶體檢查（契約 §5；DQ-07 (a)；C2-SF-3；FM-25）

- 只查額外帳號（`ProfileRuntime(hold=…)`→`ProfileManager._hold`）：面板要起子程式的時候（存後端、會重起子程式的存檔、`child/restart`）在舊子程式
  停下之後讀 `/proc/meminfo` 的 MemAvailable；少於「產品每子程式 MiB＋保留 256 MiB」（Odoo 356）就存檔但不起：`blocked`＋`memory_capacity`，
  `child/restart` 回 202＋`blocked_reason: "memory_capacity"`。開機（`start_all`）與看門狗重啟不查。讀不到就照起，記一行 WARNING。
- 讀得到 cgroup `memory.max`（`profiles.memory_limit_mib`，照 PaaS `_memory_limit_mib`）時，`ProfileManager` 開啟時用 PaaS 公式算容量（超出的帳號
  `disabled_reason=memory_capacity`、帶 `required_memory_mib`），不再讀 MemAvailable。HA add-on 通常沒有 cgroup 記憶體上限（待 HM-03a）。
- 建立帳號的 409 `profile_memory_insufficient` 是 HM-10（`ProfileManager.capacity`、`profiles.available_memory_mib` 可以直接用）。

### 3.8 log 事件（計畫 §5.4；契約 §7；C3-SF-3；FM-138；T-18）

- 開通的產品才寫（`ChildLog` 經 `LifecycleLog`，logger `mcp_admin_core.lifecycle`）；一律 WARNING：管理程序沒有設定 logging，add-on log 只看得到
  WARNING 以上（`logging.lastResort`）。每帳號每情況 60 秒一行，之後那一行帶 `suppressed=N`；最多記 256 種情況；刪帳號時 `forget()`。
  和 HM-08 的 `profile_router.Reports` 分開（不共用 64 種的名額，HM-08 的測試照舊只看它自己的 logger）。
- 格式照 PaaS `_tag`：`MCP child [profile=<default 或 id 前 8 碼> port=<p> pid=<n>]: <固定文字>`，沒有 process 時不帶 pid。文字：`started`、
  `exited with code N`、`next start in N s (attempt n)`、`failed after n starts; …`、`not started (<原因碼>): <說明>`、
  `child resources not applied (…)`、`could not be started (<例外類別>)`、`not started: no connection is saved yet (<欄位名>); …`、
  `the backend refused the credentials; next health check in N s`、`its health monitor stopped; …`、`MemAvailable cannot be read; …`。
  不含 token、網址、帳號名稱、後端的原文（log 掃描工具在每個新測試都開著）。
- 計畫 §5.4 清單裡的其他事件：撞號、孤兒、讀不到的帳號是 HM-08 寫的；隔離、還原守門逐帳號動作、休眠撤銷是 HM-13b。

### 3.9 `child/restart` 與索引變更後重評

- `make_apps(child_blocked=…)`（只在開通的產品給）：`child/restart` 的 202 回應多 `blocked_reason`（`null` 或原因碼）。spawn 前檢查在 `start()`
  裡同步做，所以回應時已經有答案（修 PaaS B-22：被拒的重啟看起來像成功）。沒開通的回應鍵集合照舊（測試鎖住）。
- `ProfileManager.reevaluate()`：HM-10 寫完索引、`adopt_index(view)` 之後呼叫。用新的索引重算每個額外帳號的 `disabled`：不再 disabled 的立刻起、
  新變 disabled 的停；spawn 前檢查擋住、正在退避的立刻再檢查一次（`retry_now()`）。測試：B、C 同 port（都 disabled），刪 C 後 B 立刻起，不用重啟
  （修 PaaS B-17）。

### 3.10 計畫沒寫死、本片定的做法（契約已同步）

1. spawn 失敗（`OSError`）也算一次失敗、照退避重試（PaaS 停住等手動）：HA 的指令固定在映像裡，spawn 失敗多半是暫時的。契約 §9 #14 加註。
2. disabled 帳號：不起、`blocked`，`blocked_reason` 是 `port_conflict`→`child_port_conflict`、`memory_capacity`→`memory_capacity`、
   `profile_limit`→`null`（契約沒有對應的原因碼，清單的 `disabled_reason` 說明；HM-10 定清單時可改）。不建 spec、不試綁、不重試。
3. 錯開啟動的名額規則（第 3.3 節）：先等預設帳號；名額的三種讓出條件；0.5 秒的檢查間隔。
4. 監看起點的算法（第 3.4 節）；額外帳號的監看從子程式起好後開始。
5. 「認證被拒」的判斷用各子程式固定文字，並把 Nextcloud 登入失敗後的 429 節流也算進去（同樣該退避）。
6. 「連兩次失敗」的算法（第 3.4 節）：只算「子程式有回、後端不通」的檢查；子程式沒回的不算也不打斷；`backend/test` 照實回但也算一次。
7. DQ-21 的「標記 failed」做成停掉該帳號的子程式，存檔或重啟後連監看一起恢復（第 3.5 節）。
8. 資源包裝器經管線回報、做不到就照起並記一行（第 3.6 節）。
9. 記憶體檢查的時機（存檔與 `child/restart`；開機與看門狗不查；在舊子程式停下後讀）與讀不到時照起（第 3.7 節）。
10. log 一律 WARNING、自己的節流器（第 3.8 節）。
11. 健康監看不探測不在 running 的子程式（第 3.4 節）。
12. 開通後預設帳號也做 spawn 前檢查（第 3.2 節；PaaS 也查預設帳號）。
13. 「連兩次失敗」由本片做：計畫 §12.3 把「健康檢查容忍」放 HM-30，但這一輪的工作指示與 DQ-25（負責片 HM-09、HM-30）要本片做規則本身；
    HM-30 留 CPU 飢餓下的整合測試（`tests/test_health_tolerance.py`；驗收矩陣登記表已改說明）。

14. IPv6 試綁被平台擋（EACCES、EPERM）時跳過並記一行（審查 S-6；契約 §9 #89）：PaaS 當成被佔。
15. 錯開啟動裡某個帳號的啟動或等待丟例外時記一行、其他照起（審查 S-12）；沒有直譯器可跑包裝器時照起並記一行（審查 S-12）。

這些都不是使用者要定的題目（DQ），是計畫範圍內的實作細節（審查也這樣認為）。審查 S-9 建議在 PR 說明逐條點名的是第 1、2（`profile_limit` 的
`blocked_reason` 是 `null`，面板要同時看 `health.child.state == 'blocked'`）、7、12、13 點；第 1 點（spawn 失敗也重試）與第 14 點是對
「照 PaaS」的偏離，PR 說明寫成「請使用者看過」。

## 4. 守門有效的證據

### 4.1 先紅後綠

測試先寫、先 commit（`8d090af`）。新模組的名稱都在測試執行時才查，所以實作前是每案各自失敗，不是整個檔收集失敗。

| 輪 | 範圍 | 結果 |
|---|---|---|
| 實作前（`cfdc487` 的程式＋新測試） | 新 5 檔 103 案 | 100 失敗、3 通過。通過的是鎖：`test_the_default_profiles_monitor_stopping_ends_the_add_ons_monitoring`（HM-08 的 `monitor()` 本來就只是預設帳號的監看）、`test_switched_off_child_restart_answers_as_before`、`test_switched_off_the_monitor_probes_as_before_whatever_the_childs_state`（沒開通照舊）。同一輪 HM-05、HM-08 的既有測試檔有 63 案失敗：測試工具改成等 `ProfileManager.started`、新名稱 `child_blocked`，實作前都還不存在（實作後全過） |
| 實作後 | 新 5 檔 104 案＋改過的 3 檔＋HM-08 的 4 檔＋`test_lifecycle.py`、`test_health.py`、`test_quality_core_regressions.py` | 291 案全過、0 skip |
| 加 `settle()` 與突變後補的測試之後 | 同上（新 5 檔 106 案） | 293 案全過；最後再補 1 案（M45）後 `test_staggered_start.py`＋`test_health_backoff.py` 47 案全過，全套見第 5 節 |

實作後第一次跑時找到、改掉的：

- 測試本身的錯（2 處）：log 事件的篩選用 `'started' in line`，連 `… when saved or restarted` 也算進去 → 改成比對 `]: started` 結尾；兩個計時斷言
  （`run()` 的退避間隔、30 秒逾時的錯開）在本機剛好過、CI 可能偶發 → 改成相對與寬鬆的上限（計畫 §10.1：計時型測試用可控時鐘或寬鬆上限）。
- 程式（3 處，測試抓到的）：`_started` 在子程式還沒 spawn（`starting`）時也睡滿 0.5 秒，預設帳號的等待拖慢了額外帳號 → 還沒 spawn 時每 0.02 秒看；
  disabled 帳號也建了 spec（產品的 `child_spec` 會建 `child/` 目錄）→ 先看 disabled 再建 spec；既有的 `test_quality_core_regressions.py` 的
  process 替身沒有 `pid`，舊路徑也去讀 → 改成 `getattr(…, 'pid', None)`。
- 實作中補的 1 案：`test_a_profile_without_a_connection_names_the_missing_fields`（計畫 §5.4 事件清單的「缺哪些連線鍵」，寫實作時才注意到；
  在 `cfdc487` 的程式上它也失敗：沒有 `start_all`）。
- 突變後補的 3 案與 1 處程式（第 4.2 節）：M23 沒擋下（`start_all` 對已回過健康檢查的子程式再查一次，多一次後端登入）→ 補
  `test_start_all_never_checks_a_child_that_already_answered`；順著看到「監看的檢查正在跑時 `start_all` 又自己探一次」→ 程式加
  `HealthMonitor.settle()`（有檢查在跑就等它的結果，不再探），補 `test_settle_waits_for_a_running_check_instead_of_probing_again` 與
  `test_start_all_waits_for_a_check_running_now_instead_of_probing_again`（M45、M46）。M41 第一次跑時卡住（沒開通的監看迴圈改走新路後永遠不呼叫
  `asyncio.sleep`，測試沒有逾時），占住共用鎖；停掉後 `test_switched_off_the_monitor_loop_is_todays` 加 5 秒逾時，重跑擋下。

### 4.2 臨時突變

每個突變只改正式程式的一處，跑本片的 5 個新檔加 `test_lifecycle.py`、`test_health.py`、`test_profile_runtime.py`（`-x`），跑完逐位元還原（SHA-256
比對）。腳本：`SP:hm09/bin/mutate.py`（repo 外；M45 的重跑在 `SP:hm09/bin/final_batch.sh`）。表上是第一個失敗的測試（`-x` 停在那裡）。

- 第一輪 M01～M44：M23 沒擋下；M41 卡住（見第 4.1 節），停掉後還原檔案並以 SHA-256 核對。補測試後重跑 M23、M41～M44，新增 M45、M46；
  M45 第一次沒擋下，補 manager 層的測試後重跑擋下。最後 46 個全部擋下。

| # | 突變（檔） | 結果 | 擋下的第一個測試 |
|---|---|---|---|
| M01 | 開通了也不用看門狗（走舊的有界迴圈）（`lifecycle.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_the_watchdog_backs_off_through_the_paas_table_and_never_gives_up` |
| M02 | 跑滿 120 秒也不歸零（`lifecycle.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_a_run_of_120_seconds_starts_the_table_again` |
| M03 | 永遠用表的第一格（`lifecycle.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_the_watchdog_backs_off_through_the_paas_table_and_never_gives_up` |
| M04 | 第一次被拒就不再重試（`lifecycle.py`） | 擋下 | `tests/test_profile_ports.py::test_a_profile_on_an_add_on_listener_port_is_blocked[8081]` |
| M05 | 第一次 spawn 前不檢查（`lifecycle.py`） | 擋下 | `tests/test_profile_ports.py::test_a_profile_on_an_add_on_listener_port_is_blocked[8081]` |
| M06 | 退避後再起時不檢查（`lifecycle.py`） | 擋下 | `tests/test_profile_ports.py::test_a_profile_on_an_add_on_listener_port_is_blocked[8081]` |
| M07 | 放行 8081／8099（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_a_profile_on_an_add_on_listener_port_is_blocked[8081]` |
| M08 | 不管別帳號在跑的子程式（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_a_port_another_profiles_running_child_uses_is_a_conflict` |
| M09 | 不試綁（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_an_occupied_port_backs_off_and_recovers_after_the_eighth_backoff` |
| M10 | 只試綁 127.0.0.1（`profiles.py`） | 擋下 | `tests/test_profile_ports.py::test_a_socket_on_any_of_the_four_addresses_makes_the_port_occupied[::1-listening]` |
| M11 | disabled 的帳號照起（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_an_index_port_conflict_stops_only_the_profiles_holding_it[duplicate]` |
| M12 | 記憶體不足也起（`profile_runtime.py`） | 擋下 | `tests/test_extra_child_resources.py::test_low_memory_holds_a_save_or_restart_but_never_the_boot` |
| M13 | 開機也查記憶體（`profile_runtime.py`） | 擋下 | `tests/test_extra_child_resources.py::test_low_memory_holds_a_save_or_restart_but_never_the_boot` |
| M14 | 額外帳號沒有資源設定（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_switched_on_every_profile_gets_the_watchdog_and_the_spawn_check` |
| M15 | 預設帳號也經包裝器（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_switched_on_every_profile_gets_the_watchdog_and_the_spawn_check` |
| M16 | 包裝器不還原 LC_CTYPE（`lifecycle.py`） | 擋下 | `tests/test_extra_child_resources.py::test_the_wrapper_hands_the_child_its_argv_environment_directory_and_signals` |
| M17 | 包裝器不還原 SIGPIPE 等（`lifecycle.py`） | 擋下 | `tests/test_extra_child_resources.py::test_the_wrapper_hands_the_child_its_argv_environment_directory_and_signals` |
| M18 | 資源沒寫成也不記（`lifecycle.py`） | 擋下 | `tests/test_extra_child_resources.py::test_resources_an_unprivileged_child_cannot_have_degrade_to_one_warning` |
| M19 | 資源一律當作寫成（`lifecycle.py`） | 擋下 | `tests/test_extra_child_resources.py::test_resources_an_unprivileged_child_cannot_have_degrade_to_one_warning` |
| M20 | stop_all 依序停（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_stop_all_stops_every_child_at_once_within_haos_30_seconds` |
| M21 | 不錯開（同時全起）（`profile_runtime.py`） | 擋下 | `tests/test_staggered_start.py::test_the_default_starts_first_then_at_most_two_others_at_once` |
| M22 | 不等預設帳號就起額外帳號（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_monitor_starts_the_additional_profiles_behind_the_default_one` |
| M23 | 已就緒的子程式也再查一次（`profile_runtime.py`） | 擋下 | `tests/test_staggered_start.py::test_start_all_never_checks_a_child_that_already_answered` |
| M24 | 額外帳號監看停止不標記（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_an_additional_profiles_monitor_stopping_marks_only_that_profile` |
| M25 | 額外帳號的監看不隔離（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_an_additional_profiles_monitor_stopping_marks_only_that_profile` |
| M26 | 一次失敗就判 unreachable（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_two_failed_checks_in_a_row_judge_the_backend_unreachable` |
| M27 | 子程式沒回的檢查打斷連續（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_a_child_that_does_not_answer_is_no_failure_of_the_backend` |
| M28 | 認證被拒不退避（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_refused_credentials_back_off_15_30_60_120_300_and_any_other_answer_resets` |
| M29 | 退避不歸零（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_refused_credentials_back_off_15_30_60_120_300_and_any_other_answer_resets` |
| M30 | 重設不叫醒等待（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_a_save_or_restart_resets_the_backoff_and_checks_within_one_interval` |
| M31 | 探測不在跑的子程式（`health.py`） | 擋下 | `tests/test_profile_ports.py::test_an_occupied_port_backs_off_and_recovers_after_the_eighth_backoff` |
| M32 | 監看起點不錯開（`profile_runtime.py`） | 擋下 | `tests/test_health_backoff.py::test_every_profile_has_its_own_monitor_client_and_staggered_start` |
| M33 | backend/test 回判定而不是這次的結果（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_the_panels_backend_test_reports_what_it_found` |
| M34 | child/restart 不帶 blocked_reason（`gateway.py`） | 擋下 | `tests/test_profile_ports.py::test_child_restart_answers_with_the_blocked_reason` |
| M35 | 索引變更不重評 disabled（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_deleting_the_other_holder_of_a_port_starts_the_one_left_at_once` |
| M36 | 索引變更不重試被擋的（`profile_runtime.py`） | 擋下 | `tests/test_profile_ports.py::test_reevaluating_retries_a_blocked_profile_at_once` |
| M37 | 401 之後不看邊界（4010 也算）（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_other_failures_are_no_refusal_of_the_credentials[BACKEND_HTTP_ERROR` |
| M38 | 生命週期 log 不節流（`lifecycle.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_one_child_killed_five_times_keeps_restarting_and_the_others_keep_their_pids` |
| M39 | 回報管線不關（`lifecycle.py`） | 擋下 | `tests/test_extra_child_resources.py::test_spawning_and_reaping_children_leaves_no_descriptor_open` |
| M40 | 每個 Supervisor 都成看門狗（含未開通）（`lifecycle.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_a_switched_off_supervisor_still_fails_after_four_starts` |
| M41 | 未開通的監看迴圈改走新路（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_switched_off_the_monitor_loop_is_todays` |
| M42 | 不記缺哪些連線欄位（`profile_runtime.py`） | 擋下 | `tests/test_profile_lifecycle.py::test_a_profile_without_a_connection_names_the_missing_fields` |
| M43 | 配 port 不跳過被佔的（`profiles.py`） | 擋下 | `tests/test_profile_ports.py::test_allocation_skips_reserved_taken_and_occupied_ports` |
| M44 | 不用 cgroup 公式（`profile_runtime.py`） | 擋下 | `tests/test_extra_child_resources.py::test_a_cgroup_memory_limit_disables_the_profiles_past_the_paas_formula` |
| M45 | start_all 不等執行中的檢查、自己再探（`profile_runtime.py`） | 擋下 | `tests/test_staggered_start.py::test_start_all_waits_for_a_check_running_now_instead_of_probing_again` |
| M46 | settle 不等執行中的檢查（`health.py`） | 擋下 | `tests/test_health_backoff.py::test_settle_waits_for_a_running_check_instead_of_probing_again` |

### 4.3 審查後補的測試：先紅後綠（審查修正的 commit：`1f4193a` 測試先、`f6b7fea` 程式後）

| 輪 | 範圍 | 結果 |
|---|---|---|
| 修正前的程式（`f6b7fea^`，和 `5eeb470` 相同）＋審查後的測試（`62b5186`） | 新 5 檔 118 案 | 4 失敗、114 通過。失敗的正是程式修正要擋的 4 案：S-6 的 `test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning[EACCES]`、`[EPERM]`（舊程式連 `_reported_binds` 都沒有，在 monkeypatch 那一步就失敗；行為本身由突變 N1、N2 證明擋得住）；S-12 的 `test_a_start_that_fails_is_named_and_never_stops_the_others`（`start_all` 把 `RuntimeError: the wait broke` 丟出來）與 `test_without_an_interpreter_for_the_wrapper_the_child_starts_and_says_so`（`resource_state` 是 None、沒有那一行）。其餘 7 個新案例與 6 個改過的案例測的是本來就對的行為（E2、E3、E8、E9、E10、S-3、S-4、S-5、S-7、S-12 (4)），由第 4.4 節的突變證明擋得住 |
| 修正後（`62b5186`） | 同上，連跑兩次 | 118 案全過兩次（23.9、23.4 秒），看偶發 |
| 測試工具的關閉上限之後（`1fc1913`） | 用到兩個測試工具的 9 個測試檔 | 214 案：213 過、1 失敗：`test_removing_a_profile_stops_its_monitor_and_its_child` 逾時，原因是測試工具的 port 相撞（第 4.5 節），不是關閉上限 |
| `free_port()` 修正之後（複查，`2334bcd`） | 同上 9 個檔（多了新的 1 案），連跑兩次 | 215 案全過兩次（45.6、45.3 秒）；新案在舊的 `free_port()` 上是紅的（預設帳號拿到 B 的 port） |

這些測試都寫在 `1f4193a`，在 `f6b7fea`（程式）之前 commit；測試工具的關閉上限（`1fc1913`）是跑突變時才發現要加的（第 4.4 節的 R03b）。

### 4.4 審查後的臨時突變（`SP:hm09-fix/mutate.py`；一次拿共用鎖，`SP:hm09-fix/batch.sh`）

每個突變只改正式程式的一處（舊字串剛好出現一次），跑審查用的同一批 8 個檔（本片 5 檔＋`test_lifecycle.py`、`test_health.py`、
`test_profile_runtime.py`；`-x`，外層 `timeout 300`），跑完逐位元還原並以 SHA-256 核對（每個都通過；跑完 6 個正式檔的 SHA-256 和開始前相同）。
R 開頭的是審查的突變（第一輪存活的 9 個與卡住的 R03b；R30 因為 `start_all` 改了，改成 R30b 跑新的位置），M34 是作者的（rebase 後
`gateway.py` 有變，審查 MF-1 要重跑），N 開頭的是這次修正新加的。

| # | 突變（檔） | 結果 | 擋下的第一個測試 | 秒數 |
|---|---|---|---|---|
| R03b | stop_all 逐一停而且卡住（`profile_runtime.py`） | **卡住**（外層 `timeout 300` 殺掉） | — | 300.0 |
| R08 | spawn 前檢查丟例外時放行（fail open）（`lifecycle.py`；S-2） | 擋下 | `tests/test_profile_ports.py::test_a_spawn_check_that_fails_refuses_the_start` | 13.8 |
| R09 | 看門狗遇到 spawn 失敗就停在 failed（PaaS 行為）（`lifecycle.py`；S-1） | 擋下 | `tests/test_profile_lifecycle.py::test_a_spawn_failure_backs_off_and_retries_under_the_watchdog[plain]` | 14.9 |
| R16 | 索引變更後新變 disabled 的帳號不停（`profile_runtime.py`；S-4） | 擋下 | `tests/test_profile_ports.py::test_reevaluating_stops_a_profile_the_new_index_disables` | 14.5 |
| R17 | `remove()` 不停該帳號的監看（`profile_runtime.py`；S-4） | 擋下 | `tests/test_profile_lifecycle.py::test_removing_a_profile_stops_its_monitor_and_its_child` | 13.2 |
| R19 | 存檔與面板重啟不重設認證退避（`profile_runtime.py`；MF-2） | 擋下 | `tests/test_health_backoff.py::test_the_panels_save_and_restart_reset_the_backoff` | 17.0 |
| R23 | nice 寫成絕對值 5（不是 +5）（`lifecycle.py`；S-5） | 擋下 | `tests/test_extra_child_resources.py::test_an_unprivileged_child_gets_oom_score_adj_500_and_nice_5` | 22.3 |
| R30b | `start_all` 起好的額外帳號不起監看（`profile_runtime.py`；審查 R30 的新位置） | 擋下 | `tests/test_profile_lifecycle.py::test_an_additional_profiles_monitor_stopping_marks_only_that_profile` | 22.1 |
| R39 | 子程式沒回的檢查也把認證退避歸零（`health.py`；S-12） | 擋下 | `tests/test_health_backoff.py::test_refused_credentials_back_off_15_30_60_120_300_and_any_other_answer_resets` | 14.8 |
| R40 | 監看不等起點（`first_check_after` 沒作用）（`health.py`；MF-2） | 擋下 | `tests/test_health_backoff.py::test_the_monitor_waits_its_start_point_before_the_first_check` | 16.9 |
| R41 | DQ-21：監看停了之後，存檔／重啟也不再恢復監看（`profile_runtime.py`；MF-2） | 擋下 | `tests/test_profile_lifecycle.py::test_an_additional_profiles_monitor_stopping_marks_only_that_profile` | 22.0 |
| M34 | `child/restart` 不帶 `blocked_reason`（`gateway.py`；作者的 M34，rebase 後重跑） | 擋下 | `tests/test_profile_ports.py::test_child_restart_answers_with_the_blocked_reason` | 14.7 |
| N1 | IPv6 試綁被平台擋仍當被佔（拿掉 S-6 的跳過）（`profiles.py`） | 擋下 | `tests/test_profile_ports.py::test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning[EACCES]` | 13.6 |
| N2 | IPv6 試綁被擋的 WARNING 每次都寫（`profiles.py`；S-6） | 擋下 | `tests/test_profile_ports.py::test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning[EACCES]` | 14.0 |
| N3 | 額外帳號的錯開啟動丟例外時不攔（`profile_runtime.py`；S-12） | 擋下 | `tests/test_staggered_start.py::test_a_start_that_fails_is_named_and_never_stops_the_others` | 22.2 |
| N4 | 預設帳號的就緒等待丟例外時不攔（`profile_runtime.py`；S-12） | 擋下 | `tests/test_staggered_start.py::test_a_start_that_fails_is_named_and_never_stops_the_others` | 21.7 |
| N5 | `sys.executable` 是空的時照舊不記（`lifecycle.py`；S-12） | 擋下 | `tests/test_extra_child_resources.py::test_without_an_interpreter_for_the_wrapper_the_child_starts_and_says_so` | 22.1 |
| N6 | `run()` 被拒後一律等退避表的最後一格（`health.py`；S-7） | 擋下 | `tests/test_health_backoff.py::test_the_monitor_waits_the_backoff_between_its_checks` | 16.8 |
| R03b（重跑） | 同上，加上兩個測試工具的關閉上限之後（`1fc1913`；同一批 8 檔） | 擋下 | `tests/test_profile_lifecycle.py::test_switched_on_every_profile_gets_the_watchdog_and_the_spawn_check`（第 10 案；測試工具關閉的 30 秒上限讓它失敗，不再卡住） | 32.8 |
| R03b（HM-08 的測試工具） | 同上，改跑 `tests/test_profile_routing.py`（經 `multi_profile_runtime` 的 run_product 停機） | 擋下 | `tests/test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]`（停機的 30 秒上限讓它失敗） | 32.3 |

- R03b 第一次卡在第 10 案 `test_switched_on_every_profile_gets_the_watchdog_and_the_spawn_check`，不是停機測試：每個測試的測試工具關閉時都會
  呼叫 `stop_all`（`ProfileManager.aclose`），所以只在兩個停機測試加逾時（審查 S-3 的建議）擋不住。審查當時記的「卡在第 10 案」也是這一案。
  改法：兩個測試工具的關閉都限 HA 的停機上限 30 秒（`multi_profile_runtime.CLOSE_SECONDS`：`manager_rig` 的 `aclose()`、`multi_profile_runtime`
  的 run_product 停機），超過就讓測試失敗；`test_stop_all_…` 只留 `stop_all` 本身的 15 秒。完全不理取消的卡住（被 shield 的停機永遠不結束）
  逾時救不了，只能靠 CI job 的上限。
- 每個突變跑完都以 SHA-256 核對還原（全部通過）；跑完 6 個正式檔的 SHA-256 和開始前相同；沒有殘留程序（`leftover_processes_killed` 都是空的）。

### 4.5 複查時找到的測試工具偶發失敗：`free_port()` 的 port 相撞（2026-11-16）

- 現象：本工作中斷後接續時，先重跑用到兩個測試工具的 9 個檔（第 4.3 節）：`test_removing_a_profile_stops_its_monitor_and_its_child`
  在 10 秒逾時。預設帳號的就緒檢查連續 20 次都是 401，`start_all` 一直在等預設帳號（最多 30 秒），B、C 都沒有起。同一個測試之前在新 5 檔
  連跑兩次與全套裡都過。
- 原因（讀程式找到，再強制重現）：`manager_rig` 先用 `free_port()` 抽 B、C 的 port，再抽預設帳號的。`free_port()` 每次都把 socket 關掉，
  連續兩次 bind port 0 可能拿到同一個 port（本機實測 2 萬次「連抽三個」有 5 次重複，約 4,000 分之 1）。預設帳號和 B 同 port 時，
  `children.by_port` 那個 port 先放預設帳號的替身子程式、再被 B 的蓋掉，預設帳號的檢查帶自己的 child bearer 打到 B 的替身，就是 401。
  用強制的抽號順序（B、C、再抽到 B 的 port）重現：B 的替身收到預設帳號的檢查（暫時的測試檔，在共用鎖下跑完就刪，沒進 repo）。
- 影響：只在測試工具。正式程式不會這樣配 port（額外帳號的 port 由索引決定，預設帳號是 3000；同 port 由 spawn 前檢查擋）。每個 rig
  3～7 個 port、全套約 70 個 rig，CI 每跑一次都有一點機會撞到（不一定每種相撞都讓測試失敗）。
- 修法（`2334bcd`，只改 `tests/`）：`tests/multi_profile_runtime.py` 的 `free_port()` 記住最近發過的 256 個 port（`HANDED_OUT`），不再發
  同一個；抽號抽成 `_draw()`。新測試 `test_a_rig_never_gives_two_profiles_one_port`：抽號照「B、C、再抽到 B 的 port」時，預設帳號拿到
  下一個 port，錯開啟動馬上完成。拿掉 `HANDED_OUT` 的檢查（舊寫法）時它是紅的：`assert (36751, 51083, 36751) == (36751, 51083, 56531)`；
  修正後 9 個檔 215 案連跑兩次全過。

## 5. 本機檢查（一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

rebase 到 `claude-delivery` `51bc4b7` 之後（2026-11-16，`1d42c2a`：程式、測試、帳本和最後的 head 相同，之後只改本筆記）重跑的是表的前
4 列。這次 rebase 只帶進 #100 的 `.github/workflows/woow-addon-release.yml` 與 `decisions.md`：`tests/` 裡沒有測試讀這兩個檔（`grep` 核對），
讀 workflow 的是 packaging 的檢查，所以 rebase 後沒有重跑 pytest（共用鎖當時排著 HM-14 審查的突變與 HM-10 的全套，估計要等兩小時以上）；
全套以 CI 為準。rebase 前（基準 `adfc4bf`）的結果在表的後半，SHA 都換成 rebase 後對應的 commit（程式與測試逐位元相同，對照在第 14.2 節）。
實作時（第一次 rebase 前）的數字留在第 4.1、4.2 節。

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（rebase 後；ci-venv 的 Python） | PASS |
| packaging unittest（rebase 後；同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`；短 TMPDIR） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準；本片沒動 `packaging/`） |
| `scripts/tool_inventory.py` 漂移檢查（rebase 後） | exit 0（沒動 `apps/runtime/*.py`、`apps/*/launch.py`） |
| 兩個預檢（rebase 後，base `origin/claude-delivery`） | 秘密預檢 0 命中、帳本預檢 OK（第 8 節） |
| rebase 前：全套 pytest（`62b5186`，當時是 `ca2dba2`；正式 conftest，排隊在共用鎖；`SP:hm09-fix/batch.sh`；Chromium 照 CI 的 `npm run browser:install` 裝在 `node_modules`） | 5395 案、0 skip、31 分 08 秒（1,869 秒）：5388 通過，7 個失敗都是已知要 root 的既有案例（`test_owned_executable.py` 1、HM-07 `test_profile_store.py` 1、HM-13a `test_restore_detection.py` 5；第 6 節）。本片新 5 檔當時 118 案全過；瀏覽器測試與帳本測試（`test_tool_inventory.py`、`test_ledger_precheck.py`）都過 |
| rebase 前：測試工具的關閉上限之後（`1fc1913`，只改 `tests/` 的 3 個檔） | 用到兩個測試工具的 9 個測試檔（本片 5 檔＋HM-08 的 4 檔）：214 案 213 過；1 個逾時是測試工具的 port 相撞（第 4.5 節）。其他測試檔不 import 這兩個工具 |
| rebase 前：`free_port()` 修正之後（`2334bcd`） | 同上 9 個檔：215 案連跑兩次全過（45.6、45.3 秒），本片新 5 檔 119 案都在裡面；新案在舊寫法上是紅的 |
| rebase 前：新 5 檔連跑兩次（`62b5186`） | 118 案×2 全過（23.9、23.4 秒） |
| rebase 前：先紅後綠（第 4.3 節） | 修正前的程式上 118 案 4 失敗、114 通過（失敗的正是程式修正要擋的 4 案） |
| rebase 前：突變（第 4.4 節） | 18 個：17 個擋下；R03b 第一次卡住（第 10 案，不是停機測試），在兩個測試工具的關閉加上 30 秒上限後重跑擋下（32.8 秒；改跑 HM-08 的 `test_profile_routing.py` 也擋下，32.3 秒） |
| rebase 前：`validate.py`、packaging unittest、tool-surface | PASS；`Ran 201`、`OK (skipped=5)`；exit 0 |
| commit 署名 | 本片 13 個 commit 都沒有 `Co-Authored-By`、`Generated with`；身分照 clone 的 git config（`woowtech`） |
| `git status` | 乾淨（未追蹤檔 0）；用過的 `/tmp/ha-mp-*` 都已用完整路徑刪除 |

## 6. 只在 CI 跑的測試

本片的 119 案在本機都跑過且全過，沒有只在 CI 跑的新測試。CI（root、0 skip）才是準：

- `tests/test_extra_child_resources.py` 的兩個探針案例在 root 下才是 uid 10001（探針先把自己的 `oom_score_adj` 寫成 200 再降權；直譯器與 venv
  複製到 `/tmp` 底下 0755 的目錄，同 HM-07、`test_owned_executable.py` 的做法）；本機以 uid 1000 跑同一個探針、同樣的斷言。root 下的這兩案
  只有 CI 會跑到。
- 已知要 root、本機一定失敗的既有案例（不是本片造成）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`
  （基準）、`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（HM-07）、`tests/test_restore_detection.py` 的 5 個 `test_root_*`（HM-13a）。
- 本片的測試在 root 下：真子程式（睡覺的 Python）以 root 起、以 root 停；臨時 port 的試綁與 root 無關；`/bin/sh`、`env`、`grep` 是 Ubuntu 內建；
  IPv6 的 `::1`、`::` 試綁假設 runner 有 IPv6 loopback（GitHub 的 Ubuntu runner 有；平台擋 IPv6 的情況用替身造，不靠 runner）。
- 計時：停機斷言 3.0～6 秒（依序停至少 18 秒），`stop_all` 與關閉各有 15 秒上限、兩個測試工具的關閉限 30 秒（卡住時變紅，不佔住整輪）；錯開的 30 秒逾時以 0.5 秒縮小並用
  相對斷言；退避間隔：`run()` 要求的秒數逐一比對，實際間隔只設下限與 +0.5 秒的寬鬆上限（審查 S-7：CI runner 比本機慢約 1.4 倍）。
- Python：CI 3.13.16、本機 3.13.15。

## 7. `checks` 秒數

開 PR 後補（後：本片 PR 的 `checks`）。前：`claude-delivery` 最近一個 PR（#100，`cf62c8f`，run 43705008744）的 `checks` 是 1,899 秒。
本片新測試 5 檔在本機約 22 秒（rebase 前全套 junit 的案例時間：lifecycle 11.3、ports 1.5、health 2.9、stagger 4.0、resources 2.6 秒）；root 時的探針另要複製一次直譯器與 venv，CI 會多幾秒（計畫 §10.1：每片增量 ≤1.5 分鐘）。#99 的 `checks` 是 2,079 秒；#100 已把上限
調到 60 分鐘。

## 8. 預檢結果（rebase 後；base 是 `origin/claude-delivery`＝`51bc4b7`）

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；`51bc4b7..HEAD` 的 13 個 commit（本片 5 個＋審查修正與複查 7 個＋本筆記最後一個）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 173 檔（`lifecycle.py` 加進來了）、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的列管檔 5 個（`gateway.py`、`lifecycle.py`、`profile_runtime.py`、`profiles.py`、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔；`health.py` 列為「沒列管、要看」（`ledger-tracking.md` 第 3 節）：**OK** |
| rebase 前（base `adfc4bf`，HEAD 當時是 `b0259b4`＝現在的 `1d42c2a`） | 同上兩個，`--base adfc4bfb38724945096c27267bd9fa0aebf7c9db` | 秘密預檢 12 個 commit＋整棵樹＋整個歷史 0 命中；帳本預檢 173／70／159 檔 0 漂移，OK |

測試資料：沒有 commit 任何隨機 token；token 都在測試執行時產生（沿用 HM-01、HM-08 的工具與 `create_profile`）；憑證 `DUMMY-…`、網址 `.invalid`。

## 9. PaaS 變動（`git log 69ac425..cf3d0d5 -- <相關檔>`，本機唯讀 PaaS repo）

| 範圍 | 結果 | 對本片 |
|---|---|---|
| `process.py`、`child_identity.py`、`profiles.py`、`launch_policy.py` 與 `test_process.py`、`test_watchdog_visibility.py`、`test_child_identity_live.py`、`test_profile_robustness.py`（`69ac425..cf3d0d5`） | 0 個 commit | 看門狗、spawn 前檢查、試綁、容量公式的期望值不變 |
| 核心模組（`git diff --stat 69ac425 cf3d0d5 -- packages/mcp-admin-core/mcp_admin_core/`） | 只動 `log_redaction.py`（HM-02 已收）、`gateway_pool.py`／`proxy.py` 的註解、`setup_status.py` 的說明文字 | 沒影響 |
| 本機 PaaS repo 的 `origin/main` 在本片進行中被別的工作線更新到 `5b84b5d`（reflog：`fetch -q origin main`；本片沒有 fetch、沒有 checkout） | `cf3d0d5..5b84b5d`（#152～#154）核心模組 0 變動，只動 `apps/emqx`、`apps/nextcloud`、`docs/` | 沒影響（Nextcloud 換身分撤銷 token 是 HM-22 的事） |
| 審查修正時再核對（2026-11-15 23 時，本機 PaaS repo 唯讀） | `origin/main` 仍是 `5b84b5d`；`69ac425..5b84b5d` 這三檔 0 個 commit；`cf3d0d5..5b84b5d` 核心模組 0 變動；`child_identity.port_occupied` @cf3d0d5 遇到 IPv6 的 EACCES、EPERM 回「被佔」 | 第 89 列的差異照實寫 |
| 接續時再核對（2026-11-16 06 時，本機 PaaS repo 唯讀） | `origin/main` 在 06:33 被別的工作線更新到 `d7f5849`（reflog：`fetch -q origin main`；#155「閘道請求內容位元組預算」，台北 06:28 合併；本片沒有 fetch、沒有 checkout）。`cf3d0d5..d7f5849`：`process.py`、`child_identity.py`、`launch_policy.py` 與上面 4 個測試檔 0 個 commit；`profiles.py` 只把容量公式抽成 `current_profile_capacity()`（`e6971c0`，公式一字不變）；核心另動 `app.py`、`gateway_pool.py`、`proxy.py`、`request_body.py`、`request_budget.py`（新）、`request_limits.py`（請求內容位元組預算、JSON 結構守門） | 本片沒影響。#155 是閘道的事（HM-08 已合併的每帳號位元組額度、之後的閘道片），交主對話決定由哪一片收 |

## 10. 本片用到的決策

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-20 (b) | 開通的產品所有帳號照 PaaS 看門狗；沒開通維持今天 | 第 3.1 節 |
| DQ-21 | 2026-11-15 11:2x 使用者採用建議：額外帳號的元件停止只標記該帳號、其他照常；預設帳號任何元件停止就讓 add-on 結束 | 第 3.5 節；`decisions.md` 寫入 |
| DQ-25 | 2026-11-15 11:2x 使用者採用建議：起點錯開、間隔不變；認證被拒 15→300 秒退避；開通後連兩次失敗才判 unreachable | 第 3.4 節；`decisions.md` 寫入 |
| DQ-07 (a)＋DQ-29 | MemAvailable 在建立、存後端、起子程式時檢查；`oom_score_adj` 500、`nice` +5；數值量測後定案 | 第 3.6、3.7 節（建立的 409 是 HM-10） |
| DQ-28 | OpenDesign、Odoo Manage 不開放 | 沒有額外帳號，`start_all` 只起預設帳號 |
| DQ-37 (a) | 同 uid 是同一個信任邊界 | spawn 前檢查與「只探自己的子程式」防誤配與殘留程序，不是安全邊界；listener 身分檢查是 HM-15（條件式） |
| DQ-19 | `/health/ready` 只代表預設帳號 | 不變 |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 5 節；commit |

沒有碰到待定題（審查也確認）。計畫沒寫死、本片定的實作細節列在第 3.10 節。#100（DQ-13、14、30、31、43 記成已定）在 `adfc4bf` 之後合併；
本片 rebase 到 `claude-delivery` 時以它的 `decisions.md` 為底，改成 34 題已定、12 題待定（第 14.2 節）。

## 11. 待 HM-03a 確認

程式都在執行時讀，做不到就降級並記一行 WARNING，不假設。

| 項目 | 本片怎麼處理 | 要 HM-03a（或 HM-19c）量什麼 |
|---|---|---|
| add-on 容器裡 uid 10001 能不能把 `/proc/self/oom_score_adj` 寫成 500（Supervisor 給 add-on 200；docker-default AppArmor 是否放行；容器的下限） | 包裝器寫；寫不進去就照起、`resource_state` 記下、一行 WARNING | 在 QA HAOS 的 add-on 容器裡實寫一次並讀回；讀容器的 `oom_score_adj` 基準 |
| `setpriority(+5)` 在容器裡能不能用 | 同上 | 實際的 nice 值 |
| 容器裡有沒有 IPv6（試綁 ::1、::） | 沒有 IPv6（`EAFNOSUPPORT`、`EADDRNOTAVAIL`）就跳過 | 容器的位址族；AppArmor 是否擋 bind |
| `/proc/meminfo` 讀不讀得到、MemAvailable 是主機的值（沒有 lxcfs） | 讀不到就照起、一行 WARNING | 容器內讀到的值與主機比 |
| cgroup `memory.max`（v2）／`memory.limit_in_bytes`（v1）看不看得到、是不是 `max` | 讀得到才用 PaaS 公式；`max`、讀不到就用 MemAvailable | 容器內的值（預期沒有上限） |
| HA 停 add-on 的流程（SIGTERM 後最多 30 秒；`backup: cold` 每次停再起） | `stop_all` 並行停 | HM-19c 在 J6412（可以的話 J1900）量 6 個 Odoo 帳號的停機秒數、錯開啟動到全部就緒的秒數（T-14、T-17） |
| 包裝器（`python -I -S`）多出的啟動時間 | 本機 AMD EPYC 7713 約 15～20 ms／次 | HM-19c 在目標硬體量 |
| `RLIMIT_NOFILE`（HM-08 的項目） | 不變；子程式 spawn 時多一條暫時的回報管線（讀完即關；`test_spawning_and_reaping_children_leaves_no_descriptor_open`） | 同 HM-08 筆記第 11 節 |
| 試綁 127.0.0.1、0.0.0.0、::1、:: 時的 errno（審查 S-6、審查報告第 8 節第 1 點） | IPv6 遇到 EACCES、EPERM 就跳過那個位址並記一行；IPv4 任何失敗仍當被佔 | 在 add-on 容器裡實際各試綁一次並記下 errno（AppArmor、seccomp 會不會擋 bind） |
| add-on 容器的 `oom_score_adj` 基準與下限（審查報告第 8 節第 2 點） | 寫 500；基準若大於 500，寫 500 是「調低」、要權限，會走降級（一行 WARNING），這時額外帳號的子程式不會比管理程序更容易被 OOM 選中 | 量到的值回填 DQ-29（數值量測後定案） |
| `/proc/<pid>` 能不能讀（HM-15） | 本片不讀別的程序的 `/proc`（只讀 `/proc/meminfo`，子程式只寫自己的 `/proc/self/oom_score_adj`） | 照計畫 HM-03a 表 |

## 12. 驗收條件（計畫 §12.3 HM-09）

| 條件 | 結果 |
|---|---|
| 全綠 | 本機：rebase 前的 `62b5186` 全套 5395 案、0 skip、31 分 08 秒（1,869 秒）：5388 通過，7 個失敗都是已知要 root 的既有案例；之後的兩個測試工具改動，用到它們的 9 個檔（本片 119 案在內）連跑兩次全過；rebase 後重跑 packaging 檢查與兩個預檢（第 5 節）。CI（root、0 skip）開 PR 後才知道 |
| 未開通的 `Supervisor` 仍「4 次後 failed」 | 通過：`test_a_switched_off_supervisor_still_fails_after_four_starts`（直接建 Supervisor：4 次、跑 200 秒也不歸零、之後 failed）、`test_switched_off_run_product_gives_the_default_profile_todays_supervisor`（7 個產品的 run_product 給預設帳號的 Supervisor 沒有任何新選項）；既有 `tests/test_lifecycle.py`、`test_quality_core_regressions.py`（4 次後 failed 的舊案例）照過；突變 M40、R02、R02b 擋下 |
| T-13 的 HA 期望值照 PaaS（其他帳號 PID 不變；看門狗 2→300 秒、不限次數、120 秒歸零） | 通過：`test_one_child_killed_five_times_keeps_restarting_and_the_others_keep_their_pids`、`test_the_watchdog_backs_off_through_the_paas_table_and_never_gives_up`、`test_a_run_of_120_seconds_starts_the_table_again`；spawn 失敗也重試（#14 的 HA 差異）由 `test_a_spawn_failure_backs_off_and_retries_under_the_watchdog` 鎖住；處理中那筆的 502＋`-32004` 是 HM-14 |
| T-15 的 HA 期望值照 PaaS（衝突只停相關帳號；被佔時照看門狗退避，放開後自動恢復） | 通過：PaaS 的四種做法在 HA 對應三種（HA 的 port 只在索引裡，沒有「改帳號設定檔讓兩帳號同 port」）：執行中當掉時被搶（`test_a_crashed_childs_port_taken_by_another_program_gets_it_nothing`：搶的程式收到 0 筆）、開機前就被佔（`test_an_occupied_port_backs_off_and_recovers_after_the_eighth_backoff`）、索引同 port（`test_an_index_port_conflict_stops_only_the_profiles_holding_it`），再加 listener port、別帳號在跑的子程式、檢查本身出錯（fail closed）與 IPv6 被平台擋（#89） |
| 測試照 §10.3（配 port；四類衝突不 spawn；第 8 次退避之後放開仍恢復；SIGKILL 5 次仍重試且 log 有紀錄；穩定 120 秒歸零；未開通 4 次後 failed；錯開啟動；`oom_score_adj`＝500、`nice` 在 uid 10001 子程序驗；FD soft limit；log 事件清單） | 通過（第 2 節的五個測試檔）；uid 10001 的部分在 root 時才是 uid 10001（CI），本機以本機使用者跑同一個探針 |
| DQ-21、DQ-25 的執行面（審查 MF-2） | 通過：起點錯開（`run()` 真的等）、存檔與面板重啟歸零退避、DQ-21 監看停止後恢復並檢查新世代，各有測試；突變 R40、R19、R41 擋下 |
| `decisions.md` 寫入 DQ-21、DQ-25，變更紀錄一列；契約的「待定」改已定 | 通過（rebase 到 `claude-delivery` 後 34 題已定、12 題待定；第 14.2 節） |
| 同 PR 更新帳本 | 通過（第 8 節；`lifecycle.py` 也列管了） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空集合；commit 沒有 AI 署名 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在執行時產生（沿用 HM-01、HM-08 的工具）；憑證 `DUMMY-…`、網址 `.invalid`；沒有 commit 任何像金鑰的字串 |

## 13. 還沒解決、交給後面的片

### 13.1 前面的片交給 HM-09 的事項

| 來源 | 事項 | 處理 |
|---|---|---|
| HM-04 第 11 節 | 額外帳號配 port、避開 8081／8099、spawn 前檢查 | 做了（第 3.2 節） |
| HM-05 第 11 節 | 看門狗參數經 `lifecycle` 傳給 Supervisor；`start_all`、`stop_all`、錯開啟動在 `profile_runtime.py` | 做了 |
| HM-06 第 12 節 | 額外帳號的子程式拿自己 state 的 child_token | 照 HM-05／HM-08：每帳號的 spec 用自己的 state，本片沒改；直連矩陣由 HM-06 的測試與 HM-16 的容器探針涵蓋 |
| HM-06 審查 S-07 | 子程式回 401 時監看只看到 readiness false（`MCP_SERVER_NOT_READY`），要不要加專屬原因碼 | 不加：契約的錯誤代碼不變；只有閘道自己的 child bearer 會送到子程式，401 代表設定錯，面板的 `backend/test` 與子程式輸出（diagnostics）看得到 |
| HM-07 審查 MF-1 | 索引 port 是 8081／8099 的帳號要在 spawn 前擋成 `child_port_conflict` | 做了（`test_a_profile_on_an_add_on_listener_port_is_blocked`） |
| HM-08 第 3.5、14.2 節 | `start_all`、`stop_all`、每帳號監看（DQ-21、DQ-25）、看門狗參數、spawn 前檢查；DQ-21、DQ-25 寫進 `decisions.md` | 做了 |

### 13.2 交給後面的片

- **HM-10**（審查 S-4、S-12 (2)）：`reevaluate()` 對新變 disabled 的帳號立刻停、`remove()` 停該帳號的監看，本片已有測試
  （`test_reevaluating_stops_a_profile_the_new_index_disables`、`test_removing_a_profile_stops_its_monitor_and_its_child`），HM-10 接線後
  經 API 再測一次（必測）。`start_all`、`reevaluate()` 走的 `launch()` 不拿 gateway 的 `mutation_lock`：開機時剛好有人在面板存同一個帳號，
  兩個 `_relaunch` 交錯時，存檔那邊判 `blocked` 之後 `launch()` 那邊仍可能把子程式起來（窗口很小）。HM-10 接線時讓 `_relaunch` 自己拿
  runtime 的 `mutation_lock`。
- **HM-10**：清單的 `status`、`blocked_reason` 讀 `entry.runtime.supervisor`（狀態有 `stopped`、`starting`、`running`、`backoff`、`blocked`、
  `failed`、`unconfigured`；契約第 3.6 節沒有 `stopped`，要對應）、`disabled_reason` 讀 `entry.disabled`；建立帳號的 409
  `profile_memory_insufficient`（`ProfileManager.capacity`、`profiles.available_memory_mib`）與 `profile_port_unavailable`（`free_port()`）；
  寫索引後 `adopt_index(view)`＋`reevaluate()`；建立後 `start_profile(id)`；刪除用 `remove(id)`（已停監看、清 log 狀態）；8099 把
  `child/restart` 等路由到額外帳號的管理 app。
- **HM-10／HM-11**：看門狗一直重試時，`configuration.apply_state` 在退避期間是 `pending`（今天的有界重試 4 次後變 `failed`）；清單用
  `status=backoff` 表示，面板要不要另外提示由 HM-11 定。
- **HM-13b**：開機順序（還原守門、休眠處理在 `launch()` 之前）；隔離、還原守門逐帳號動作、休眠撤銷的 log 事件。
- **HM-15**（條件式）：listener 身分檢查；要的話可在本片的包裝器加 `PR_SET_PDEATHSIG`（PaaS `child_identity` 的做法）。
- **HM-16**：容器探針的多帳號階段（SIGKILL 一個子程式其他 PID 不變、停機 <30 秒、真容器裡的 `oom_score_adj`／`nice`）。
- **HM-19c**：停機秒數、錯開啟動到全部就緒（T-14 的數字）、包裝器時間、MemAvailable 門檻在目標硬體上量。
- **HM-19b**：驗收第 10 點（Odoo 來源 IP 冷卻）在真 Odoo 上看認證退避的效果。
- **HM-30**：CPU 飢餓下的健康檢查容忍整合測試（`tests/test_health_tolerance.py`）疊在本片的「連兩次失敗」上；回覆工作執行緒。
- **HM-25**：`apps/n8n/run.py` 接上 `ProfileManager` 時，n8n 的監看與看門狗也拿同樣的選項。
- **HM-18**：文件寫明 `oom_score_adj` 只是讓核心傾向先殺額外帳號的子程式（不是保證，OOM 仍可能殺管理程序）、Odoo 管理員可調
  `base.login_cooldown_*`、log 事件的文字清單。
- **HM-18、HM-19a：計畫 §7.2 清單要補的項目**（審查 S-8；§7.2 第 5 點只寫看門狗與連兩次失敗，還寫「健康探測間隔不變」）：開通後
  預設帳號也會：(1) 後端認證被拒時監看退避到 300 秒（間隔平常仍是 15 秒）；(2) 子程式 port 3000 也做 spawn 前檢查，被佔就 `blocked`、
  照看門狗重試；(3) `child/restart` 的 202 回應多 `blocked_reason`；(4) add-on log 多生命週期 WARNING（含 IPv6 試綁被擋的一行）；
  (5) spawn 失敗也照退避重試；(6) 子程式不在 `running` 時監看不探測（`backend/test` 回 `unknown`、沒有原因）。要寫進該產品的 CHANGELOG、
  DOCS、`upgrade-notes.yaml`。
- **合併順序**（審查 S-11）：HM-08（#99）與 #100 都已合併，本片已 rebase 到 `claude-delivery` `51bc4b7`（第 14.1、14.2 節）。
  本片要在 HM-10 之前合（計畫 §12.2）。HM-14（第 4 波，基準 `b5d10c5`）也改 `gateway.py`：本片和 HM-14 誰後合，誰就
  rebase 並照實際內容重算 `gateway.py` 的摘要。計畫 §12.2 衝突表的 `Hc/gateway.py` 列要補 HM-09，`docs/multi-profile/contract.md` 列要補
  HM-08、HM-09（計畫在 repo 外，交主對話）。

## 14. rebase 紀錄

### 14.1 rebase 到 HM-08 的最終 head（審查 MF-1；2026-11-15 21:15）

- 指令：`git fetch <HM-08 clone> feat/ha-multiprofile-hm08-20261115`，再 `git rebase --onto adfc4bfb38724945096c27267bd9fa0aebf7c9db
  cfdc4876bc70578875af690390275a28a1a6085f`：只重放本片的 5 個 commit（`8d090af`→`5012f11`、`195977c`→`b69fbbc`、`d389939`→`a6042d6`、
  `4387dfe`→`657d831`、`24d72cc`→`57ec5c0`；第二次 rebase 後又換了，見第 14.2 節）。這一步是本工作前一次執行時做的（reflog 有紀錄），
  這次逐點核對結果。
- 3 處衝突，照審查的三點解：
  1. `Hc/gateway.py` 的 `make_apps` 說明：HM-08 修正加的「initialize 錯誤遮罩」與 `FORWARDED_BODY` 兩段、本片的 `child_blocked` 一段都留。
  2. `runtime-patches.json` 的 `gateway.py`：摘要照合併後的內容重算＝`466b0f2a97601fa317b718d1caa070cb92ed7cec44b1425c0f6cb94a0068c130`
     （和審查試 rebase 算的相同），說明＝HM-08 修正版＋本片那一段（核對：HM-08 的說明原文是本片說明的開頭）。
  3. `docs/multi-profile/contract.md` 第 9 節：#14 用本片的、#15／#16 用 HM-08 修正後的；第 10 節變更紀錄兩列都留。
- 解完之後其他 3 個列管檔（`run_product.py`、`profile_runtime.py`、`profiles.py`）也照實際內容重算過；`tests/test_reply_mask_union.py` 自動合併
  （本片只加一行第二次檢查）。

### 14.2 開 PR 前：rebase 到 `claude-delivery`（#100 已合併；2026-11-16）

- 指令：`git fetch origin claude-delivery`（`51bc4b7`，和 2026-11-15 19:10 #100 合併時相同，之後沒有新的合併），再
  `git rebase --onto origin/claude-delivery adfc4bfb38724945096c27267bd9fa0aebf7c9db`：只重放本片的 12 個 commit（本片 5 個＋審查修正與
  複查 7 個）。`git log origin/claude-delivery..HEAD` 只有本片的 commit。
- 衝突只在第 4 個 commit（決策與契約）的 `docs/multi-profile/decisions.md`，和之前在暫存複本試的一樣。解法（以 `claude-delivery` 的版本
  為底；46 題一題不少，表格逐列數過：第 1 節 34 列、第 2 節 2 列、第 3 節 10 列）：
  1. 結論第一行改「46 題裡 34 題已定」。
  2. 結論的時間序：本片的「2026-11-15 11:2x：DQ-21、DQ-25 採用計畫建議…」放在 17:4x 那點之前；#100 的「另外 11:2x … 15:3x …」那點改成
     只講 DQ-10 子題（「另外 2026-11-15 15:3x 使用者定了 DQ-10 子題（…），由 HM-20 的 PR 移到第 1 節；這裡先不動」）。
  3. 「其餘」那行改成「其餘 12 題（§13.2 的 2 題、§13.3 的 10 題）維持「待定」（DQ-21、DQ-25 已由 HM-09 的 PR 移到第 1 節）…」：#100 寫的
     「待 HM-09 的 PR 移列」改成已移列。
  4. 第 1 節標題用 #100 的，加上 DQ-21、DQ-25；第 2 節兩邊拿掉的列都拿掉（剩 DQ-35、DQ-42）；變更紀錄兩邊的列都留，本片那列排在 #100
     那列之後，題數寫「34 題已定、12 題待定」。
  5. 那個 commit 的說明同步改成 34／12（原本寫 29／17）。
- 其他 11 個 commit 都乾淨套上：`git range-diff` 只有決策那個 commit 不同；rebase 前後的 tree 只差 #100 帶進來的
  `.github/workflows/woow-addon-release.yml`（`checks` 上限 60 分鐘）與 `decisions.md`。
- 帳本：#100 沒有改列管檔。本片 5 個列管檔照實際內容核對，SHA-256 都沒變（`gateway.py` `466b0f2a…c130`、`lifecycle.py` `758cdc35…ddc9`、
  `profile_runtime.py` `b8ebbad0…9820`、`profiles.py` `d17bfc3f…f901`、`run_product.py` `59d281b1…f72b`），`ledger_precheck.py --base
  origin/claude-delivery` OK。沒動 `apps/runtime/*.py`、`apps/*/launch.py`，tool-surface 不用重產（漂移檢查 exit 0）。
- SHA 對照（rebase 前 → 後）：`5012f11`→`c03cd4d`、`b69fbbc`→`c08ff0f`、`a6042d6`→`2f88b58`、`657d831`→`20117cf`、`57ec5c0`→`5eeb470`、
  `e8055f0`→`1f4193a`、`f89f6ce`→`f6b7fea`、`ca2dba2`→`62b5186`、`07634b3`→`1fc1913`、`dbf3c8c`→`56c5a90`、`0144625`→`2334bcd`、
  `b0259b4`→`1d42c2a`。第 4、5、15 節的 SHA 都換成 rebase 後的；rebase 前跑的檢查，程式與測試和對應的 commit 逐位元相同。
- rebase 後重跑：`validate.py`、packaging unittest、tool-surface、兩個預檢（第 5、8 節）。沒有重跑 pytest：這次 rebase 只帶進 #100 的
  workflow 與 `decisions.md`，`tests/` 裡沒有測試讀這兩個檔；共用鎖當時排著 HM-14 審查的突變與 HM-10 的全套。全套以 CI 為準。

## 15. 獨立安全審查意見處理（2026-11-15）

報告：`artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-09.md`（repo 外；證據在同層的 `evidence-review-HM-09/`）。
審查判定「修正後通過」：必修 2 項、建議 12 項，沒有碰到待定題。每一項先核對再處理。

### 15.1 處理表

| # | 意見 | 核對 | 處理 | 證據 |
|---|---|---|---|---|
| MF-1 | 基準過時：HM-08 已以 #99 合併，本片還疊在審查前的 `cfdc487`；#100 也改 `decisions.md` | 成立：`b5d10c5^{tree}`＝`adfc4bf^{tree}`；#100 在 19:10 合併成 `51bc4b7` | **採用**：先 rebase 到 `adfc4bf`（本工作指定的基準，tree 和 `b5d10c5` 相同），3 處衝突照審查三點解；開 PR 前再 rebase 到 `claude-delivery` `51bc4b7`，`decisions.md` 以它為底改成 34／12；兩次都照實際內容核對帳本；第一次後重跑全套 pytest、兩個預檢、`validate.py`、packaging unittest、M34，第二次後重跑兩個預檢與 packaging 檢查（理由見第 14.2 節）；筆記第 1、5、8、12、14 節更新 | 第 5、8、14 節；M34 擋下（第 4.4 節；`gateway.py` 第二次 rebase 沒變） |
| MF-2 | DQ-21、DQ-25 三個執行面沒有測試（R40、R19、R41 存活）；驗收矩陣寫了「起點錯開」已測 | 成立：舊測試只驗 `first_check_after` 屬性、直接呼叫 `reset()`、DQ-21 讀到重啟前的 `settled` | **採用**：收 E8（`test_the_monitor_waits_its_start_point_before_the_first_check`）、E9（`test_the_panels_save_and_restart_reset_the_backoff`，存檔之外也測 `child/restart`）、E10（DQ-21 測試改成等 `settled[0]`＝新的 `starts`，並斷言舊結果不是新世代）；驗收矩陣 HM-09 五列照實改寫 | R40、R19、R41 擋下 |
| S-1 | spawn 失敗也重試是自訂的 PaaS 差異，沒有測試（R09 存活） | 成立：PaaS `process.py` @cf3d0d5 停住等手動 | **採用**：收 E2（`test_a_spawn_failure_backs_off_and_retries_under_the_watchdog`，帶與不帶資源包裝，加 log 斷言）；PR 說明的刻意差異段點名 #14，請使用者看過（要回到 PaaS 行為只改 `_watch` 一處） | R09 擋下 |
| S-2 | spawn 前檢查丟例外時 fail closed 沒有測試（R08 存活） | 成立 | **採用**：收 E3（`test_a_spawn_check_that_fails_refuses_the_start`，加「照退避再查仍被擋」與 log 斷言） | R08 擋下 |
| S-3 | 停機測試沒有逾時（R03b 卡住） | 成立，而且範圍更大：突變 R03b 卡在第 10 案，不是停機測試——每個測試的測試工具關閉時都會呼叫 `stop_all` | **採用並擴大**：`test_stop_all_…` 的 `stop_all` 限 15 秒、`test_closing_…` 的關閉限 15 秒；兩個測試工具的關閉都限 HA 的 30 秒（`CLOSE_SECONDS`；`1fc1913`） | R03b 重跑擋下（32.8 秒；HM-08 的測試工具也擋下，32.3 秒） |
| S-4 | `reevaluate()` 新變 disabled 的要停、`remove()` 要停監看，沒有測試（R16、R17 存活） | 成立 | **採用（本片補測試）**：`test_reevaluating_stops_a_profile_the_new_index_disables`、`test_removing_a_profile_stops_its_monitor_and_its_child`；HM-10 接線後經 API 再測（第 13.2 節） | R16、R17 擋下 |
| S-5 | 探針分不出「加 5」和「設成 5」（R23 存活） | 成立 | **採用**：探針起 Supervisor 前先 `os.nice(2)`，斷言子程式是探針的值＋5，而且不是 5 | R23 擋下 |
| S-6 | 試綁遇到 EADDRINUSE 以外的 errno 一律當被佔；擋 IPv6 bind 的平台上預設帳號永遠不起 | 成立：PaaS 同樣寫法（第 9 節） | **採用**：IPv6 的 EACCES、EPERM 跳過那個位址、每個位址與 errno 每個程序一行 WARNING；IPv4 維持當被佔；契約 §7、§9 #89；HM-03a 清單補試綁 errno（第 11 節）；PR 說明點名這個新差異 | `test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning`（EACCES、EPERM）；N1、N2 擋下 |
| S-7 | 計時上限只容許 +0.15 秒 | 成立 | **採用（兩種都做）**：上限放寬到 +0.5 秒；另外把 `run()` 要求的退避秒數逐一比對（只放寬上限的話，「一律等最後一格」的錯會漏掉） | N6 擋下 |
| S-8 | 開通後預設帳號會變的事沒列進 HM-18／HM-19a 交接 | 成立 | **採用**：第 13.2 節加「§7.2 清單要補的項目」六點 | — |
| S-9 | 本片的五個解讀要在 PR 說明逐條點名 | 成立 | **採用**：PR 說明逐條列出（第 3.10 節第 1、2、7、12、13 點），加上第 14 點（S-6） | — |
| S-10 | `lifecycle.py` 帶了 exec 前執行的程式，建議列管 | 成立 | **採用**：`runtime-patches.json` 加一筆；`ledger-tracking.md` 從第 3 節移到第 2 節；`health.py` 維持不列管 | 帳本預檢 OK |
| S-11 | 計畫衝突表漏列本片；HM-14 也改 `gateway.py` | 成立 | **採用（交接）**：第 13.2 節的合併順序；PR 說明也寫；計畫在 repo 外，衝突表交主對話補 | — |
| 複查 | （不是審查意見）中斷後接續時，重跑 9 個檔有 1 案逾時：`test_removing_a_profile_stops_its_monitor_and_its_child` | 成立：測試工具的 `free_port()` 可能連發同一個 port，同一個 rig 的兩個帳號就同 port（第 4.5 節） | **修正**：`free_port()` 不再發最近發過的 port；補 `test_a_rig_never_gives_two_profiles_one_port` | 舊寫法紅、新寫法綠；9 個檔連跑兩次全過 |
| S-12 | (1) `start_all` 一個帳號丟例外會取消其他；(2) `launch()` 不拿 `mutation_lock`；(3) `sys.executable` 空時不記；(4) R39 存活 | 成立（(1) 目前找不到會觸發的路） | **(1)(3)(4) 採用**：每個帳號各自攔例外並記一行；`sys.executable` 空時記一行；兩次被拒之間插一次 `probe='silent'`。**(2) 交 HM-10**（接線時讓 `_relaunch` 拿 `mutation_lock`；第 13.2 節） | N3、N4、N5、R39 擋下 |

審查的實驗 E5（錯開啟動中途停機）只是確認沒有殘留，審查說不必收；沒有收。

### 15.2 審查修正的 commit

| commit | 內容 |
|---|---|
| `1f4193a` | 測試（先紅：在修正前的程式上 118 案 4 失敗） |
| `f6b7fea` | 程式：S-6（`profiles.py`）、S-12（`profile_runtime.py`、`lifecycle.py`） |
| `62b5186` | 帳本：`profile_runtime.py`、`profiles.py` 重算 SHA-256 並補說明；`lifecycle.py` 列管；`ledger-tracking.md` |
| `1fc1913` | 測試工具：兩個工具的關閉限 30 秒（S-3；R03b 第一次跑才發現只包停機測試不夠） |
| `56c5a90` | 契約（§7、§9 #89、§10）與驗收矩陣 |
| `2334bcd` | 測試工具：`free_port()` 不再發最近發過的 port（複查找到的偶發失敗，第 4.5 節） |
| `1d42c2a` | 本筆記：審查修正、複查與 rebase 前的檢查（第 1～8、10～15 節） |
| 本筆記最後一個 commit | rebase 到 `claude-delivery` 之後的基準、SHA 對照與重跑的結果（結論、第 1、5、7、8、10、12～15 節） |
