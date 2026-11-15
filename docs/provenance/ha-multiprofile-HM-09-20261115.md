# HA 多帳號 HM-09 provenance：子程式生命週期（port、看門狗、錯開啟動、停機）（2026-11-15）

## 結論

- **產品沒開通時，行為一行都不變**：Supervisor 照舊「同一次啟動最多 4 次（約 1、2、4 秒間隔）、跑多久都不歸零、之後 failed」，不寫 log、
  不做 spawn 前檢查、不經包裝器；健康監看照舊每 15 秒一次、一次失敗就判 unreachable、不退避、子程式什麼狀態都照探；`child/restart` 的回應
  照舊。HM-01 的黃金回歸、兩個契約凍結照過（開關關與開兩種都跑），斷言一個字都沒改。repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開），每個帳號（含預設帳號）：
  - **看門狗照 PaaS**（DQ-20 (b)）：異常結束、spawn 失敗、spawn 前檢查拒絕，都照 2、5、15、30、60、120、300 秒退避，之後一直 300 秒、
    不限次數；連續跑 120 秒（含）以上歸零。
  - **spawn 前檢查**：port 是 add-on 自己的 listener（8081、8099）或別的帳號執行中的子程式在用 → `blocked`＋`child_port_conflict`；
    試綁 127.0.0.1、0.0.0.0、::1、::（照 PaaS `port_occupied`）失敗 → `blocked`＋`child_port_in_use`；這兩種照看門狗退避重試，
    port 放開就自動恢復（T-15）。索引內重複或等於 3000 的帳號（HM-07 `port_conflicts`）開啟時就 `disabled`，起子程式時
    `blocked`＋`child_port_conflict`、不試綁、不重試，索引變了（`reevaluate()`）才重評（修 PaaS B-17）。被擋的子程式不 spawn，
    健康監看也不送任何東西到那個 port（搶 port 的程式收到 0 筆）。
  - **錯開啟動**：預設帳號照今天在 listener 之前起；額外帳號等預設帳號第一次健康檢查通過或 30 秒後，依索引順序、同時最多 2 個在起，
    名額在「子程式回了健康檢查」「不在起了（被擋、沒設定、spec 失敗、子程式結束）」或 30 秒時讓出，壞的標記、不擋其他。
  - **並行停**：關閉時所有子程式同時停（6 個都要 SIGKILL 的子程式約 3 秒收完，HA 上限 30 秒）。
  - **健康監看**（DQ-25，2026-11-15 11:2x 使用者採用建議）：每帳號自己的 client、起點錯開（預設帳號開機就查；第 k 個額外帳號在自己的
    子程式起好後 15×(1＋k÷(產品上限＋1)) 秒）、間隔不變 15 秒；後端認證被拒時 15→30→60→120→300 秒退避；開通後連兩次失敗才判
    unreachable。
  - **監看失敗**（DQ-21，同時採用建議）：額外帳號的監看停止只標記該帳號 `failed`（停它的子程式），其他帳號與 add-on 照常，存檔或
    `child/restart` 後恢復；預設帳號維持今天：監看停止就讓 add-on 結束，由 Supervisor 重啟。
  - **額外帳號子程式**：`oom_score_adj` 500、`nice` +5，由子程式在 exec 前自己寫（`python -I -S -c` 的包裝器，不用 `preexec_fn`）；
    寫不進去就照起、記一行 WARNING，不假設。存檔與面板重啟時讀 MemAvailable，不夠就存檔、不起（`blocked`＋`memory_capacity`）；
    開機與看門狗不查；讀得到 cgroup `memory.max` 時改用 PaaS 公式。
  - **log 事件**（契約第 7 節）：`MCP child [profile=<id 前 8 碼> port=<p> pid=<n>]: …`，每帳號每情況 60 秒一行（`suppressed=N`）。
  - `child/restart` 的 202 回應多 `blocked_reason`（修 PaaS B-22）。
- 新測試 5 檔 107 案＋測試工具 2 檔（`tests/lifecycle_runtime.py`、`tests/child_resources_probe.py`）；改 3 個既有測試檔。
  **先寫測試**：實作前新 5 檔 103 案裡 100 失敗、3 通過（通過的是「沒開通照舊」的鎖），實作後全過；實作中與突變後補 4 案（第 4.1 節）。
  臨時突變 46 個（第 4.2 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest：5377 案、0 skip、30 分 49 秒，5370 通過；7 個失敗都是已知要 root 的
  既有案例（只在 CI 驗；第 5、6 節）。
- `decisions.md` 記 DQ-21、DQ-25；契約第 7 節的「待定」改成已定，並寫明本片定的做法（第 3.10 節）。
- 平台事實都在執行時讀，做不到就降級並記一行 WARNING；HM-03a 要確認的項目在第 11 節。這個階段只 commit，不 push、不開 PR。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-09（計畫 §12.3；風險中、工作量 L；不是「審查」片） |
| 分支 | `feat/ha-multiprofile-hm09-20261115`（一般 clone），疊在 HM-08 實作完的 `cfdc487` 上 |
| 基準 | `claude-delivery` `76c1d78`（HM-00、01、02、04、05、06、07、13a、17 已合併）＋ HM-08 的 5 個 commit（還沒合併；HM-08 審查中，介面可能小改，修正階段本片會 rebase 到 HM-08 的最終 head） |
| 依據 | 計畫 §5.4、§3.3、§7.1、§7.2 第 5 點、§10.1、§10.3 的 HM-09 列、§12.0、§12.3 HM-09；契約 §1.2、§3.1、§3.6、§5、§7、§9 #14、#18、#19、#29、#53；驗收矩陣 T-13、T-14、T-15、T-17、T-18；FM-13、25、37、38、39、40、45、46、68、69、133、134、137、138；C2-SF-3、SF-4、SF-5、SF-10、C2-MF-4 第 3 點、C3-MF-1、C3-SF-3、C4-SF-6；HM-04～HM-08 的 provenance 筆記交給 HM-09 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425`：`process.py`（`AUTO_RESTART_DELAYS`、`STABLE_SECONDS`、`_schedule_auto_restart`、`_port_refusal`、`CHILD_PORT_CONFLICT`、`CHILD_PORT_IN_USE`、`_tag`）、`child_identity.py`（`port_occupied`、exec 包裝器的寫法）、`profiles.py`（`port_conflict`、`start_all`、`_memory_limit_mib`、容量公式）。到 `cf3d0d5` 這幾個檔都沒變（第 9 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/lifecycle.py`（沒列管） | `Supervisor` 多 keyword-only 的 `delays`、`max_attempts`、`stable_seconds`（看門狗；`WATCHDOG`＝PaaS 的值）、`preflight`（spawn 前檢查）、`log`（`ChildLog`）、`resources`（`ChildResources`）；新屬性 `blocked_reason`、`failures`、`retry_in`、`resource_state`、`clock`；新方法 `block()`、`retry_now()`、`give_up()`；一次 spawn 抽成 `_attempt()`，舊的有界迴圈照舊（`_run`），看門狗另走 `_watch()`；`EXEC_WRAPPER`（exec 前寫 `oom_score_adj` 與 `nice`）；`LifecycleLog`、`ChildLog`（每帳號每情況 60 秒一行）；原因碼常數 `CHILD_PORT_CONFLICT`、`CHILD_PORT_IN_USE`、`MEMORY_CAPACITY` |
| `Hc/health.py`（沒列管） | `HealthMonitor` 多 keyword-only 的 `first_check_after`、`tolerance`、`auth_backoff`、`own_child_only`、`log`；`HEALTH_INTERVAL`、`AUTH_BACKOFF`、`auth_refused()`；`next_interval()`、`reset()`、`settle()`（有檢查在跑就等它的結果，不再探）；`test_saved` 照實回這次的結果；選項都不給時 `run()` 照舊（`asyncio.sleep(15)`） |
| `Hc/profiles.py` | `port_occupied()`（四種位址試綁）、`allocate_port(occupied=)`（不給時照 HM-07 不綁）、`memory_limit_mib()`、`available_memory_mib()`；說明文字 |
| `Hc/profile_runtime.py` | `ProfileRuntime` 多 keyword-only 的 `hold`、`monitor_options`、`report_blocked`（不給時照舊）；`launch()`／`backend_changed()` 共用 `_relaunch`；沒設定連線時記缺哪些欄位（只列名稱）。`ProfileManager`：每帳號的看門狗、spawn 前檢查（`spawn_refusal`）、額外帳號的資源與 `_hold`（disabled、記憶體）、監看選項；`start_all()`、`stop_all()`、`monitor()`（DQ-21 的隔離）、`reevaluate()`、`free_port()`、`start_profile()`、`started`、`events`、`capacity`、`memory_limit`；開啟時讀 cgroup 記憶體上限；關閉時先 `stop_all()` |
| `Hc/gateway.py` | `make_apps` 多一個 keyword-only 的 `child_blocked`（只在開通的產品給）：`child/restart` 的 202 回應多 `blocked_reason` |
| `Hc/run_product.py` | 只改註解（`launch()`／`monitor()`／關閉現在做什麼）；程式一行沒改 |
| `tests/test_profile_lifecycle.py`（新，25 案） | 沒開通照舊 4 次後 failed、run_product 給預設帳號的 Supervisor 沒有任何新選項；看門狗表、不放棄、有上限時 failed、真的等、120 秒歸零（可控時鐘）、退避中停止立刻結束；T-13（SIGKILL 5 次、其他帳號 PID 不變、log）；log 事件的文字與節流；沒設定連線時列欄位名；並行停（`stop_all` 與關閉）；DQ-21 兩種；`monitor()` 起額外帳號；開通的 run_product 走 `launch`→`monitor`→`stop_all` |
| `tests/test_profile_ports.py`（新，24 案） | 配 port；四種位址各兩種 socket 的試綁；8081／8099；索引重複與 3000；別帳號在跑的子程式；被佔時退避、第 8 次退避之後放開仍恢復；子程式當掉時 port 被搶、搶的程式收到 0 筆；索引變更後立刻重評兩種；`child/restart` 的 `blocked_reason`（開與關） |
| `tests/test_health_backoff.py`（新，39 案） | 退避表與間隔；各子程式認證被拒的文字（釘到原始碼）與 13 種不算的；退避 15→300、歸零；`run()` 真的照退避等；存檔／重啟重設；log 一分鐘一行；連兩次失敗（含新子程式世代、子程式沒回的檢查、面板的 `backend/test`、經閘道的 tools/call）；沒開通一次就判；`settle()` 等執行中的檢查；起點錯開與自己的 client；五種不在跑的狀態都不探；沒開通照探、迴圈照舊 |
| `tests/test_staggered_start.py`（新，8 案） | 常數；預設先、同時最多 2 個、名額怎麼讓出；已回過健康檢查的不再查、執行中的檢查等它不另探；30 秒逾時；起不來的不擋人；disabled 不起；listener 在額外帳號還在起時就服務預設帳號 |
| `tests/test_extra_child_resources.py`（新，11 案） | 只有額外帳號經包裝器、exec 後的 cmdline 是真正的指令；包裝器不改 argv、環境、工作目錄、訊號；邊界；以非特權使用者（root 時是 uid 10001）拿到 500 與 +5、拿不到時降級並一行 WARNING；記憶體檢查的時機與讀不到；cgroup 公式；讀檔；FD 不外洩；沒有 FD 預算時只起預設帳號 |
| `tests/lifecycle_runtime.py`（新，測試工具） | 開通的 `ProfileManager`＋真 Supervisor＋真的睡覺子程式（可以 SIGKILL、可以忽略 SIGTERM）＋每帳號 MockTransport；所有 port 都是臨時 port |
| `tests/child_resources_probe.py`（新，測試工具） | root 時先寫自己的 `oom_score_adj` 基準（200，同 Docker 給 add-on），降到 uid 10001 再起 Supervisor；回報子程式自己看到的值 |
| `tests/multi_profile_runtime.py` | HM-08 的測試工具：改成等 `ProfileManager` 自己起完額外帳號（`started`），不再自己 `launch()`；`STAGGER_SECONDS` 預設 0.05（沒回健康檢查的額外帳號立刻讓出名額，HM-08 的測試照舊一開始就起全部）；可指定 `stagger` |
| `tests/test_reply_mask_union.py` | HM-08 的一案：B 的健康原因要連兩次失敗才判 unreachable（DQ-25），多查一次 |
| `tests/test_profile_runtime.py` | HM-05 的兩案：`make_apps` 與 `app_options` 的名單加 `child_blocked` |
| `docs/multi-profile/decisions.md` | DQ-21、DQ-25 移到第 1 節（2026-11-15 11:2x 使用者採用建議），變更紀錄一列，題數 29／17 |
| `docs/multi-profile/contract.md` | 第 5 節記憶體檢查、第 7 節（DQ-21、DQ-25 改已定＋本片定的做法）、第 9 節 #14（spawn 失敗也重試）、第 10 節一列 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表 HM-09 的四列與 HM-30 的 `test_health_tolerance.py` 說明（連兩次失敗的規則本片已做） |
| `docs/provenance/runtime-patches.json` | 4 個列管檔重算摘要並補說明（`gateway.py`、`run_product.py`、`profile_runtime.py`、`profiles.py`） |
| 本筆記 | — |

沒改：`products.py`、`configuration.py`、`profile_router.py`、`apps/`、`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、
`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、workflow、`tests/conftest.py`、HM-01 的守門測試檔。
`lifecycle.py`、`health.py` 照 `docs/multi-profile/ledger-tracking.md` 第 3 節維持不列管（沒有審查要求列管）；本片沒有新模組，不加帳本項目。

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

這些都不是使用者要定的題目（DQ），是計畫範圍內的實作細節；審查若認為某一項要問使用者，再回報。

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

## 5. 本機檢查（2026-11-15，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

| 檢查 | 結果 |
|---|---|
| 全套 pytest（實作、帳本、文件都 commit 之後，HEAD `4387dfe`；正式 conftest，排隊在共用鎖；`SP:hm09/bin/final_batch.sh`） | 5377 案、0 skip、30 分 49 秒：5370 通過；7 失敗＝已知要 root 的既有案例（`test_owned_executable.py` 1、HM-07 1、HM-13a 5；第 6 節）。瀏覽器測試（裝好 Chromium）與帳本測試（`test_tool_inventory.py`、`test_ledger_precheck.py`）都過。本筆記在這之後才 commit，不影響任何測試 |
| 本片的 5 個新檔＋改過的 3 檔＋HM-08 的 4 檔＋`test_lifecycle.py`、`test_health.py`、`test_quality_core_regressions.py` | 293 案全過、0 skip；最後一版的 `test_staggered_start.py`＋`test_health_backoff.py` 47 案全過（`final_batch.sh`，7 秒） |
| 影響面較大的既有測試 24 檔（HM-01 黃金回歸、兩個契約凍結、HM-04 port、HM-06 bearer、HM-07 三檔、`test_initialize_cleanup.py`、`test_quality_core_regressions.py` 等） | 1030 案：1024 通過；6 失敗＝1 個要 root 的既有案例（HM-07 `test_mode_and_owner_as_the_add_on_user`）＋5 個 `test_quality_core_regressions.py` 的 process 替身沒有 `pid`（程式改成 `getattr` 後重跑 21 案全過，第 4.1 節） |
| 新 5 檔連跑兩次（當時 104 案） | 208 案全過（看偶發） |
| 照 CI 裝 Chromium（`npm run browser:install --prefix packages/mcp-admin-ui`，裝在不進 git 的 `node_modules`） | 全套 pytest 前裝好，瀏覽器測試一起跑 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`；短 TMPDIR） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準；本片沒動 `packaging/`） |
| `scripts/tool_inventory.py` 漂移檢查 | 沒動 `apps/runtime/*.py`、`apps/*/launch.py`；帳本預檢的 `tool-surface.json` 159 檔 0 漂移 |
| 臨時突變 | 46 個（第 4.2 節） |
| commit 署名 | 本片 commit 都沒有 `Co-Authored-By`、`Generated with`；身分照 clone 的 git config |
| `git status` | 乾淨（未追蹤檔 0）；用過的 `/tmp/ha-mp-*` 都已刪除 |

## 6. 只在 CI 跑的測試

本片新增的 107 案在本機都跑過且全過，沒有只在 CI 跑的新測試。CI（root、0 skip）才是準：

- `tests/test_extra_child_resources.py` 的兩個探針案例在 root 下才是 uid 10001（探針先把自己的 `oom_score_adj` 寫成 200 再降權；直譯器與 venv
  複製到 `/tmp` 底下 0755 的目錄，同 HM-07、`test_owned_executable.py` 的做法）；本機以 uid 1000 跑同一個探針、同樣的斷言。root 下的這兩案
  只有 CI 會跑到。
- 已知要 root、本機一定失敗的既有案例（不是本片造成）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`
  （基準）、`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（HM-07）、`tests/test_restore_detection.py` 的 5 個 `test_root_*`（HM-13a）。
- 本片的測試在 root 下：真子程式（睡覺的 Python）以 root 起、以 root 停；臨時 port 的試綁與 root 無關；`/bin/sh`、`env`、`grep` 是 Ubuntu 內建；
  IPv6 的 `::1`、`::` 試綁假設 runner 有 IPv6 loopback（GitHub 的 Ubuntu runner 有）。
- 計時：停機斷言 3.0～6 秒（依序停至少 18 秒）、錯開的 30 秒逾時以 0.5 秒縮小並用相對斷言、退避間隔只設下限與 0.15 秒的寬鬆上限。
- Python：CI 3.13.16、本機 3.13.15。

## 7. `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本片新測試 5 檔在本機約 20 秒（全套 junit 的案例時間：lifecycle 10.0、ports 1.4、health 2.2、stagger 4.2、resources 2.5 秒；root 時的探針另要複製一次
直譯器與 venv，CI 會多幾秒）（計畫 §10.1：每片增量 ≤1.5 分鐘）。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；`76c1d78..HEAD` 的 10 個 commit（HM-08 的 5 個＋本片 5 個）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 172 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的列管檔（本片 4 個＋HM-08 的 `profile_router.py`）都有帳本更新；沒有沒列管的新執行檔；`lifecycle.py`、`health.py` 列為「沒列管、要看」（`ledger-tracking.md` 第 3 節）：**OK** |

測試資料：沒有 commit 任何隨機 token；token 都在測試執行時產生（沿用 HM-01、HM-08 的工具與 `create_profile`）；憑證 `DUMMY-…`、網址 `.invalid`。

## 9. PaaS 變動（`git log 69ac425..cf3d0d5 -- <相關檔>`，本機唯讀 PaaS repo）

| 範圍 | 結果 | 對本片 |
|---|---|---|
| `process.py`、`child_identity.py`、`profiles.py`、`launch_policy.py` 與 `test_process.py`、`test_watchdog_visibility.py`、`test_child_identity_live.py`、`test_profile_robustness.py`（`69ac425..cf3d0d5`） | 0 個 commit | 看門狗、spawn 前檢查、試綁、容量公式的期望值不變 |
| 核心模組（`git diff --stat 69ac425 cf3d0d5 -- packages/mcp-admin-core/mcp_admin_core/`） | 只動 `log_redaction.py`（HM-02 已收）、`gateway_pool.py`／`proxy.py` 的註解、`setup_status.py` 的說明文字 | 沒影響 |
| 本機 PaaS repo 的 `origin/main` 在本片進行中被別的工作線更新到 `5b84b5d`（reflog：`fetch -q origin main`；本片沒有 fetch、沒有 checkout） | `cf3d0d5..5b84b5d`（#152～#154）核心模組 0 變動，只動 `apps/emqx`、`apps/nextcloud`、`docs/` | 沒影響（Nextcloud 換身分撤銷 token 是 HM-22 的事） |

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

沒有碰到待定題。計畫沒寫死、本片定的實作細節列在第 3.10 節。

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
| `/proc/<pid>` 能不能讀（HM-15） | 本片不讀別的程序的 `/proc`（只讀 `/proc/meminfo`，子程式只寫自己的 `/proc/self/oom_score_adj`） | 照計畫 HM-03a 表 |

## 12. 驗收條件（計畫 §12.3 HM-09）

| 條件 | 結果 |
|---|---|
| 全綠 | 本機：全套 5377 案 5370 通過，7 個失敗都是已知要 root 的既有案例；本片 107 案全過。CI（root、0 skip）開 PR 後才知道 |
| 未開通的 `Supervisor` 仍「4 次後 failed」 | 通過：`test_a_switched_off_supervisor_still_fails_after_four_starts`（直接建 Supervisor：4 次、跑 200 秒也不歸零、之後 failed）、`test_switched_off_run_product_gives_the_default_profile_todays_supervisor`（7 個產品的 run_product 給預設帳號的 Supervisor 沒有任何新選項）；既有 `tests/test_lifecycle.py`、`test_quality_core_regressions.py`（4 次後 failed 的舊案例）照過；突變 M40 擋下 |
| T-13 的 HA 期望值照 PaaS（其他帳號 PID 不變；看門狗 2→300 秒、不限次數、120 秒歸零） | 通過：`test_one_child_killed_five_times_keeps_restarting_and_the_others_keep_their_pids`、`test_the_watchdog_backs_off_through_the_paas_table_and_never_gives_up`、`test_a_run_of_120_seconds_starts_the_table_again`；處理中那筆的 502＋`-32004` 是 HM-14 |
| T-15 的 HA 期望值照 PaaS（衝突只停相關帳號；被佔時照看門狗退避，放開後自動恢復） | 通過：PaaS 的四種做法在 HA 對應三種（HA 的 port 只在索引裡，沒有「改帳號設定檔讓兩帳號同 port」）：執行中當掉時被搶（`test_a_crashed_childs_port_taken_by_another_program_gets_it_nothing`：搶的程式收到 0 筆）、開機前就被佔（`test_an_occupied_port_backs_off_and_recovers_after_the_eighth_backoff`）、索引同 port（`test_an_index_port_conflict_stops_only_the_profiles_holding_it`），再加 listener port 與別帳號在跑的子程式 |
| 測試照 §10.3（配 port；四類衝突不 spawn；第 8 次退避之後放開仍恢復；SIGKILL 5 次仍重試且 log 有紀錄；穩定 120 秒歸零；未開通 4 次後 failed；錯開啟動；`oom_score_adj`＝500、`nice` 在 uid 10001 子程序驗；FD soft limit；log 事件清單） | 通過（第 2 節的五個測試檔）；uid 10001 的部分在 root 時才是 uid 10001（CI），本機以本機使用者跑同一個探針 |
| `decisions.md` 寫入 DQ-21、DQ-25，變更紀錄一列；契約的「待定」改已定 | 通過 |
| 同 PR 更新帳本 | 通過（第 8 節） |
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
- **合併順序**：HM-08 先合；本片 rebase 到 HM-08 的最終 head 後重算帳本（`profile_runtime.py`、`profiles.py`、`gateway.py`、`run_product.py` 都會
  衝突），`docs/multi-profile/contract.md` 第 5、7、10 節與 HM-08 改過的地方相鄰，rebase 時注意。
