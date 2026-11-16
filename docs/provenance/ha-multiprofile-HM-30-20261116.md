# HA 多帳號 HM-30 provenance：回覆處理公平排程、待送回覆額度、健康檢查容忍（2026-11-16）

## 結論

- **產品沒開通時，行為一行都不變**：`run_product` 不建工作執行緒，`make_apps` 沒拿到 `reply_worker`，每個回覆照今天在事件迴圈裡
  處理。處理步驟抽成 `relayed_reply`、`relayed_event` 兩個函式，迴圈內那條路跑的就是今天那幾行（讀 state 的次數、順序、例外都一樣；
  `strict_json` 不帶檢查點）。HM-01 的黃金回歸與兩個契約凍結照過（開關關與開兩種都跑），斷言一個字都沒改。repo 裡的
  `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開）：
  - **一條工作執行緒**（新模組 `Hc/reply_worker.py`，全 add-on 一條）：`run_product` 在 listener 服務前啟動、停了之後才停。JSON 回覆與
    SSE 每個帶資料的事件都交給它（`strict_json`→回覆檢查→`redact_secrets`→`filter_list`→`json.dumps`）；state 與遮罩清單在迴圈裡、
    交出的當下讀好。**依帳號輪流**：每帳號一個佇列，有一筆在處理的帳號暫時不排班，每帳號（也是全部）同時最多 1 筆。
  - **GIL convoy 與「喘息」（計畫沒寫到、本片量到的事）**：只靠 GIL 的 5 ms 切換間隔做不到計畫要的效果：迴圈每次系統呼叫都放掉 GIL，
    忙著的工作執行緒立刻拿走，迴圈的一次小檔讀取從 0.02 ms 變 30～60 ms；第一版（沒有喘息）在 CPU 飢餓測試下 B 的 p99 4.5 秒、
    迴圈最長停 1.3 秒，比在迴圈內處理沒有好。所以工作執行緒在檢查點（工作之間、步驟之間、解析器每建一個 JSON 物件時）連續跑滿 5 ms
    就睡 2 ms，迴圈還忙就繼續讓、最多 10 ms（第 3.2 節）。
  - **待送回覆額度**（每帳號 32 MiB，常數只在 `profiles.ProfileQuota.pending_reply_bytes`，HM-07 就定了）：回覆交給 server 起扣、server
    收走才還；扣到或超過時，該帳號下一個 tools/call 在轉送前回 200＋`-32003`。宣告長度的回覆分 64 KiB 交出（線上位元組不變）。
    已轉送的回覆一律交出（軟上限）。
  - **例外不讓 add-on 卡住**：工作的例外照今天的回應；執行緒自己停了，排隊中的工作立刻 502、add-on 結束由 Supervisor 重啟；停機時排隊
    中的立刻結束，處理中的最多等 5 秒。工作執行緒有自己的 16 MiB 堆疊（巢狀很深的回覆照樣 502，不當掉）。
  - **輸出位元組和今天相同**：同一個 `make_apps` 的兩條路逐案對照（JSON 24 案、SSE 14 案×整段與 7 位元組一段、GET 串流 1 案）全部逐位元
    相同；開通後的黃金回歸與契約凍結也走工作執行緒。
- **契約第 6 節的門檻（第 11 節）**：CPU 飢餓（可控注入）四項都達到：A 的回覆處理期間迴圈最長停 13.9～27 ms（≤50）、B 的 tools/call
  p99 0.36～0.44 秒（≤0.7；開工前在迴圈內處理是 4.47 秒）、B 與 C 的健康檢查 0 次逾時（每次在該做之後最晚 31～50 ms 做完；開工前
  4.4 秒）、每帳號同時 1 筆。慢讀 RSS 增量 121 MiB（≤296）。
- **兩項沒達到（或在目標硬體上一定達不到），照契約第 6 節回報使用者再定（第 14 節），門檻沒放寬**：
  1. 真實 8 MiB 回覆（C2 的 mixed 形狀）：最後版本迴圈最長停 42～45 ms，本機剛好在 50 ms 內；主因是整個值一次 `json.dumps`（拆不開的
     一次 C 呼叫，本機 45～66 ms），J6412／J1900 慢數倍，一定超過。
  2. 待送回覆額度是軟上限：預設帳號一次湧入 32 個不讀的 8 MiB 回覆時帳上 224 MiB、RSS 增量 469 MiB（契約的 296 MiB 是照硬上限寫的）。
- 新測試 2 檔 76 案＋測試工具 1 檔（`tests/reply_load.py`）；改 2 個既有測試檔。**先寫測試**：`test_reply_worker.py` 74 案在
  `dbf3c8c` 上全紅（61 錯誤、13 失敗）；`test_health_tolerance.py` 第 1 案（改量法之後）在 `dbf3c8c` 上紅（檢查在該做之後 4.4 秒才
  做完），第 2 案是 HM-09 的規則，本來就該綠；`test_profile_runtime.py` 的 2 個名單案例紅（第 4.1 節）。
- 臨時突變 24 個全部抓到（第一輪 22 個裡 1 個沒抓到、1 個寫錯測試名稱，補了測試與 2 個突變後重跑；第 4.2 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest：5,471 案、0 skip、31 分 35 秒，5,464 通過；7 個失敗都是已知要 root
  的既有案例（第 5 節）。
- 這個階段只 commit，不 push、不開 PR。合併前要做獨立安全審查（本片標「審查」）。

## 1. 範圍與基準

縮寫同計畫：`Hc/`＝`packages/mcp-admin-core/mcp_admin_core/`；`SP:`＝這次工作的暫存區（不進 repo）。

| 項目 | 值 |
|---|---|
| 切片 | HM-30（計畫 §12.3；風險中、工作量 M；標「審查」：合併前要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm30-20261116`（一般 clone），疊在 HM-09 的修正 head `dbf3c8c` 上 |
| 基準 | `dbf3c8c`＝HM-08 最終 head `adfc4bf`＋HM-09 的實作與審查修正。`claude-delivery` 已合併 HM-00～HM-08、HM-13a、HM-17、HM-02 與 #100；本分支沒有 #100，rebase 時處理 |
| 依據 | 計畫 §5.5（全部）、§5.2、§5.4、§10.3 的 HM-30 列、§12.0、§12.3 HM-30；契約 §2.4、§5、§6、§7、§9 #15、#17、#18；`threat-model.md` I8；FM-129、FM-130、FM-149；C2-MF-4、C1-M5；DQ-07 (a)、DQ-21、DQ-25；HM-06、HM-08、HM-09 的 provenance 筆記交給 HM-30 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有。PaaS 在事件迴圈內處理回覆（§8.8 #17 是 HA 的部署差異）；第 9 節列出 pin 之後的 PaaS 變動 |
| commit（`dbf3c8c` 之後 7 個） | `092b827` 測試先寫；`8a2703e` 工作執行緒；`73d6cfd` 待送回覆額度；`2552106` 契約、威脅模型、帳本；`33798ad` 兩個測試改寫（第 4.1、4.2 節）；`c43eefd` 只刪測試檔裡重複的區段標題（AST 相同）；最後一個是契約第 6 節量測數字、第 9 節 #17 附註、第 10 節一列與本筆記 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/reply_worker.py`（新，列管） | `ReplyWorker`：全 add-on 一條工作執行緒（`mcp-reply-worker`、daemon、自己的 16 MiB 堆疊 `STACK_BYTES`）；`run(profile, function, *args)` 把純函式交給它、在呼叫者的迴圈拿回結果或例外；每帳號一個佇列、輪流（`_next`、`_done`）；被取消的撤回（`_withdraw`）；執行緒自己停時全部 `WorkerStopped`、`ended`、`failure`、一行 WARNING（`_main`、`_end`）；`stop()`（排隊的立刻結束、處理中的最多等 `STOP_SECONDS` 5 秒）；`Lane`（一個帳號的班次）；`breathe()`（檢查點：`SLICE_SECONDS` 5 ms、`BREATH_SECONDS` 2 ms、`YIELD_SECONDS` 10 ms；`_loop_busy()` 看迴圈的 ready 佇列與迴圈執行緒的 frame）；`handed`（每帳號交出幾筆） |
| `Hc/config.py`（列管） | `strict_json` 多一個 keyword-only 的 `checkpoint`：每建一個 JSON 物件前呼叫一次；不給時 hook、值與每個錯誤都照舊 |
| `Hc/gateway.py`（列管） | `make_apps` 多一個 keyword-only 的 `reply_worker`（只在開通的產品給）。回覆處理抽成 `relayed_reply`（JSON）與 `relayed_event`（SSE 事件），兩條路都跑它們：沒給時在迴圈裡、照今天讀 state、不帶檢查點；給了時 `prepared()` 在迴圈裡先讀 state 與遮罩，工作執行緒跑 `worker_reply`／`worker_event`（解析器與步驟之間呼叫 `breathe`），回應用 `encoded_reply`（`json_reply` 也改用它，位元組相同）。`WorkerStopped` → 502（JSON）或串流結束。新的 request-state 名稱 `PENDING_REPLIES`：tools/call 轉送前（政策與閘道自答之後、轉送名額之前）問一次 |
| `Hc/profile_router.py`（列管） | `ProfileGate` 多 `reply_bytes`（交給 server、還沒收走的回覆位元組）與 `pending_reply()`（`PENDING_REPLIES`：達上限回 200＋`-32003`，WARNING 每帳號 60 秒一行）；`counted_send` 交出回覆時扣、下一則被收走或請求結束時還；宣告長度的回覆分 `REPLY_PIECE`（64 KiB）交出、最後補一則空的；`pending_text()`（暫定文字，HM-14 定稿 `-32003` 文字時一起看）；模組說明 |
| `Hc/profile_runtime.py`（列管） | `ProfileRuntime` 多 keyword-only 的 `reply_worker`（存成 `runtime.reply_worker`、加進 `RUNTIME_OPTIONS`）；`ProfileManager` 多 `reply_worker`，每個帳號（含預設）拿自己的 `Lane` |
| `Hc/run_product.py`（列管） | 開通的產品建一個 `ReplyWorker` 交給 `ProfileManager`；listener 服務前 `start()`、和其他元件一起看 `ended`（執行緒停了＝`runtime component stopped`）、listener 與 monitor 都停了之後、帳號關閉之前 `stop()`。沒開通：`worker=None`，流程與元件照舊 |
| `tests/test_reply_worker.py`（新） | 工作執行緒本身 9 案（含 GIL convoy、自己的堆疊）；JSON 24 案、SSE 14×2 案、GET 串流 1 案的逐位元對照；例外、停掉的 worker、state 在迴圈讀；開關開與關的 runtime；執行緒自己停、停機；CPU 飢餓；真實 8 MiB 回覆；待送回覆額度 2 案；慢讀 RSS |
| `tests/test_health_tolerance.py`（新） | CPU 飢餓下 B、C 的健康檢查；飢餓中失敗一次不擋、兩次才擋 |
| `tests/reply_load.py`（新，測試工具） | CPU 飢餓的情境：A 的 16 個 8 MiB 與 16 個 2 MiB 回覆（64 KiB 一段送）、佔住 GIL 的可控處理成本 `GilWork`（啟動時校準成每次約 10 ms 的 `json.loads`、以執行緒 CPU 時間計 d）、迴圈延遲探針 `LoopLag` |
| `tests/multi_profile_runtime.py` | HM-08 的工具：`Runtime.task`（run_product 的 task）與 `may_stop`（讓「worker 停了 add-on 就結束」的測試讀得到結果，其他測試照舊斷言「只會被取消」） |
| `tests/test_profile_runtime.py` | HM-05 的兩案：`make_apps` 與 `app_options` 的名單加 `reply_worker` |
| `docs/multi-profile/contract.md` | 第 2.4 節「待送回覆」列、第 5 節定義與最壞值的補充、第 6 節「HM-30 定案」與「HM-30 本機量測」、第 9 節 #17 的附註、第 10 節一列；門檻都沒改 |
| `docs/multi-profile/threat-model.md` | I8 的測試欄寫明待送回覆額度是軟上限 |
| `docs/multi-profile/ledger-tracking.md` | `reply_worker.py` 那列改成實際路徑、HM-30 起列管 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表 HM-30 的兩列 |
| `docs/provenance/runtime-patches.json` | 新增 `reply_worker.py`；5 個列管檔（`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`run_product.py`）重算摘要並補說明 |
| 本筆記 | — |

沒改：`health.py`（「連兩次失敗」是 HM-09 做的，本片只加整合測試）、`lifecycle.py`、`profiles.py`（`pending_reply_bytes` 32 MiB 是 HM-07 就定好的
常數，本片只用它）、`products.py`、`apps/`、`packaging/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`
（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、workflow、`tests/conftest.py`、HM-01 的守門測試檔、`decisions.md`（沒有新定的題）。

## 3. 設計重點

### 3.1 工作執行緒（計畫 §5.5 做法 1；契約 §6）

- 全 add-on 一條，由 `run_product` 管：只有 `features.enabled(product)` 時才建，listener 服務前啟動。沒開通的產品不建，`make_apps` 沒拿到
  `reply_worker`，回覆照今天在迴圈內處理。
- 交給它的只有純函式：`relayed_reply`（`strict_json`→「是這個請求的回覆」檢查→讀 state→`redact_secrets`→`filter_list`）＋`json.dumps`，
  與 `relayed_event`（SSE 一個事件）。state 與遮罩清單由 `prepared()` 在迴圈裡、交出的當下讀；工作執行緒不碰 store、不碰 asyncio 物件
  （結果用 `call_soon_threadsafe` 交回）。
- 迴圈內那條路跑的是同一組函式，`state_of` 就是 `store.load`、`masks_of` 就是 `masks`：讀 state 的次數、順序、例外都和今天一樣
  （JSON：解析、檢查之後讀一次；SSE：遮罩前一次、`filter_list` 前一次）。
- state 讀不到時：迴圈內照今天（JSON 回 503、SSE 結束）。工作執行緒那條路：`prepared()` 先接住 `ConfigError`，工作在「迴圈會讀 state 的
  那一步」才丟出來，所以「回覆格式不對（502）先於 state 讀不到（503）」的順序不變。
- 遮罩的時點：回覆位元組在交出之前已經讀完，交出的當下讀的遮罩含「那時 add-on 持有的每個 token」。之後才產生的 token 不可能出現在已經
  讀完的回覆裡，所以和今天「處理當下讀」等價。政策（`filter_list` 的 state）同理。
- 自己的堆疊：glibc 給執行緒的預設堆疊是 `RLIMIT_STACK`（無限時 2 MiB）；本機實測 1 MiB 的執行緒 `json.loads` 9,000 層就 segfault。
  主執行緒今天是 `RecursionError`（502），所以工作執行緒固定 16 MiB（4 MiB 已足夠 json 的 C 遞迴上限），啟動時設、設完還原程序的預設。
- 不交給它的：子程式的 initialize 回覆（閘道自己重建結果；後端左右不了大小）、閘道自答的 tools/list（`listed_reply`）、健康檢查自己的解析
  （`health.protocol_reply`）、拒絕小額度讀出 id 的解析（最多 8 個 × 64 KiB）。

### 3.2 GIL convoy 與工作執行緒的喘息（計畫沒寫到、本片量到的事）

- 計畫假設「迴圈每個 GIL 切換間隔（預設 5 ms）就拿回控制」（§5.5 做法 2、C2-MF-4 修法 2）。實際上迴圈每次系統呼叫（epoll_wait、socket、
  讀 state 檔：一次 `store.load` 就 open／fstat／read／fchmod／close 五個）都會放掉 GIL，忙著的工作執行緒立刻拿走；迴圈的系統呼叫一回來
  又要等工作執行緒到下一個 bytecode 邊界（或它手上的 C 呼叫結束）。這就是 GIL convoy。
- 量到的（第 11.1、11.2 節）：工作執行緒連續做 10 ms 的 C 呼叫時，迴圈一次小檔讀取的中位數從 0.02 ms 變 30～60 ms。第一版（沒有喘息）在 CPU
  飢餓測試下 B 的 p99 4.5 秒、迴圈最長停 1.3 秒，和在迴圈內處理（4.4 秒）差不多。
- 做法：`breathe()` 檢查點。工作執行緒在工作之間、步驟之間、解析器每建一個 JSON 物件時（`config.strict_json` 的 `checkpoint`）檢查；
  連續跑滿 `SLICE_SECONDS`（5 ms）就 `time.sleep(BREATH_SECONDS)`（2 ms，真的放掉 GIL），之後只要迴圈還忙（asyncio 的 ready 佇列有東西，
  或迴圈執行緒不在 selector 裡等 I/O：`sys._current_frames()`）就每 0.5 ms 再讓一次，最多 `YIELD_SECONDS`（10 ms）。只看 frame 會漏掉
  「因為有 callback 要跑而用 0 逾時輪詢 selector」的迴圈，只看佇列會漏掉「正在跑的那個 callback」，所以兩個都看。
- 代價：忙到底（佇列一直有工作）時工作執行緒約讓出三分之一的時間（CPU 飢餓測試：A 的 5.2 秒注入成本約 7 秒做完）；閒時不讓；
  沒開通的產品沒有檢查點（`breathe()` 在工作執行緒以外什麼都不做）。
- 參數是量出來的（獨立腳本 `SP:hm30/bench/driver.py`）：喘息 1 ms 時迴圈最長停 37～57 ms，2 ms 時 34～38 ms（量讀取＋處理全程）；最後的版本另加「迴圈忙就繼續讓」。
- 拆不開的：單一 C 呼叫（掃一個長字串、整個值的 `json.dumps`、長字串的 `str.replace`）。所以迴圈最長停頓是「一筆回覆裡最長的那一次
  C 呼叫」，真實 8 MiB 回覆約 45 ms（第 11.3 節、第 14 節）。

### 3.3 依帳號輪流（做法 2）

- 每帳號一個佇列；`_turns` 是「有排隊、又沒有一筆在處理」的帳號，照順序輪；拿走一筆的帳號離開 `_turns`，那筆做完、還有排隊才排到最後。
  所以每帳號同時最多 1 筆在處理；只有一條執行緒，全部也最多 1 筆（`peak`＝1），維持今天「一次只放大一筆」。
- A 有 32 筆排隊、B 來一筆：B 最多等 A 正在處理的那一筆（契約第 6 節「≤2d＋0.2 秒」的依據）。
- 被取消的呼叫者（`lease.run` 在 token 換了時取消、停機、用戶端離開造成的取消）：還在排隊就撤回；處理中的做完、結果丟掉。

### 3.4 例外與停機（`run_product`：例外不讓 add-on 卡住）

| 情況 | 行為 |
|---|---|
| 工作丟例外（任何 BaseException） | 交回呼叫者、在迴圈裡照今天處理（`ValueError`、`RecursionError` → 502；其他照今天往上丟）；先清掉例外的 frame（工作持有的回覆不會跟著例外留在記憶體）；執行緒繼續 |
| `StopIteration`（future 不收） | 變成 `RuntimeError` 交回（asyncio 對 coroutine 的同一條規則） |
| 執行緒本身停了（本模組的錯，不是工作的錯） | 排隊中、處理中（拿了還沒交回的）與之後的工作立刻 `WorkerStopped`（JSON 502、SSE 結束）；`failure` 記下；一行 WARNING `MCP reply worker: its thread stopped (<例外類別>); replies cannot be processed and the add-on stops`；`ended` → `run_product` 丟 `runtime component stopped` → add-on 結束、Supervisor 重啟（同 DQ-21 對預設帳號元件的規則） |
| 停機（SIGTERM 或取消） | listener 停、monitor 停（最多 5 秒）之後才 `stop()`：排隊中的立刻 `WorkerStopped`（502）；處理中的最多等 `STOP_SECONDS`（5 秒）；執行緒是 daemon，卡在一次很長的 C 呼叫也擋不住程序結束；然後才關帳號（停子程式） |

### 3.5 待送回覆額度（做法 3；契約 §2.4、§5、§6）

- 量什麼：帳號 app 交給 server 的回覆本體位元組，交出起扣、server 收走才還。h11（uvicorn）要等自己的緩衝寫出才收下一則
  （`flow.drain()` 在每次 `send` 開頭），所以一則要等同一請求的下一則被收走、或請求結束，才算收走。
- 為什麼要分段：JSON 回應只有一則本體、`more_body=False`。整則交出去時 server 立刻收下（`transport.write` 只是放進緩衝），請求馬上結束，
  8 MiB 還在 server 的緩衝裡、帳上卻已經是 0（今天「最壞 64×8 MiB」就是這樣來的）。所以宣告長度的回覆分 64 KiB 一段交出、最後補一則空的：
  每段 server 都要先把前面的寫出才收，請求要等全部被收走才結束；線上的位元組不變（`Content-Length` 的回應不分 chunk，`tests/test_mcp_contract_freeze.py`
  開關開時用真 listener 逐位元照過）。SSE（chunked）照子程式的事件一則一則交出，框架不變；它的結尾那則空訊息本來就要等前面寫出。
- 什麼時候擋：扣到或超過上限（≥，和其他「已達上限」相同）時，該帳號下一個 tools/call 在轉送名額之前回 200＋`-32003`（帶 id、`Retry-After: 5`、
  `Cache-Control: no-store`）。其他方法照常轉送（契約只擋 tools/call）；在轉送名額之前判斷，所以不等那 1 秒（契約「立刻」）。
- 已轉送的回覆一律處理並交出，不扣住：照順序讀回覆的用戶端（先等第 1 則、第 2～5 則先到）若第 1 則被扣住，就要等到逾時。所以這是**軟上限**：
  帳號最多持有「上限＋達到上限時正在轉送的回覆」。後者最多轉送名額個（額外帳號 16、預設 32），每個最多 8 MiB 原始大小，和今天相同。
- 常數只有一處：`profiles.ProfileQuota.pending_reply_bytes`（預設、額外都是 32 MiB；HM-07 定的）；分段大小 `profile_router.REPLY_PIECE`。

### 3.6 開關關時完全照今天

- `run_product` 不建 worker；`ProfileRuntime` 沒拿到 `reply_worker`；`make_apps` 走迴圈內那條路（就是今天那幾行）。沒有分派器、沒有 gate，
  所以也沒有待送回覆額度、沒有分段。
- 證據：HM-01 的黃金回歸與兩個契約凍結（開關關）照過、斷言沒改；`test_switched_off_there_is_no_worker_and_replies_are_processed_on_the_loop`
  （沒有 `mcp-reply-worker` 執行緒、回覆在主執行緒解析）；逐位元對照測試的「迴圈內」那條路就是沒開通時跑的那條（第 3.1 節）。

### 3.7 計畫沒寫死、本片定的做法（契約第 6 節已同步）

1. 工作執行緒的堆疊固定 16 MiB（第 3.1 節）；喘息的檢查點與參數（第 3.2 節）。
2. initialize 回覆、閘道自答的 tools/list、健康檢查的解析不交給它（第 3.1 節）。
3. state 與遮罩「交出的當下」讀；讀不到的 `ConfigError` 留到工作「迴圈會讀的那一步」才丟（第 3.1 節）。
4. 執行緒自己停了就讓 add-on 結束（第 3.4 節）；停機時排隊的回 502、處理中的最多等 5 秒。
5. 待送回覆的量法、64 KiB 分段、≥ 就擋、只擋 tools/call、在轉送名額之前判斷、軟上限（第 3.5 節）。
6. `-32003` 文字 `pending_text()` 暫定（HM-14 定稿其他 `-32003` 文字時一起看）。

這些都不是使用者要定的題目（DQ），是計畫範圍內的實作細節；審查若認為某一項要問使用者，再回報。
真實 8 MiB 回覆做不到 50 ms 門檻、待送上限是軟上限這兩件，照契約第 6 節回報使用者（第 14 節）。

## 4. 守門有效的證據

### 4.1 先紅後綠

- 紅：HM-30 的三個測試檔（`test_reply_worker.py`、`test_health_tolerance.py`、改過的 `test_profile_runtime.py`）在 `dbf3c8c` 的核心套件上跑
  （`-o pythonpath=<dbf3c8c 的 packages/mcp-admin-core 複本> apps/n8n`，複本裡 `apps/`、`packages/mcp-admin-ui` 用連結指回 clone，
  讓 `products.ROOT` 找得到子程式的 venv）：3 檔 141 案：15 失敗、61 錯誤、65 通過（`test_reply_worker.py` 74 案全紅；`test_profile_runtime.py` 63 個既有案例照過、2 個名單案例紅；`test_health_tolerance.py` 的第一版 2 案綠，見下）。
  - 紅的原因是對的：`reply_worker` 不存在（工作執行緒本身、逐位元對照、runtime 的案例：ImportError 或 fixture 錯）；CPU 飢餓在拿
    `reply_worker` 時就失敗（同情境在迴圈內處理，用臨時探針量：迴圈最長停 4,417 ms、B 的 p99 4.47 秒，第 11.1 節）；待送回覆額度
    不存在（`pending_text`、`reply_bytes`）；`test_profile_runtime.py` 的兩個名單案例（`reply_worker`）。
  - `test_health_tolerance.py` 第 1 案的第一版只量檢查本身的耗時，在 `dbf3c8c` 上也綠：測試的子程式在同一個程序裡（MockTransport），
    檢查一開始就一路做完、不讓出，量不到「等了多久才輪到它」。改成從「該做的時候」量到做完、門檻 d（0.25 秒）後重跑
    （`SP:hm30/f2.sh`）：`dbf3c8c` 上紅（B、C 各 15 次檢查，最晚 4,409 ms、4,403 ms 才做完）；HM-30 上綠（各 85 次，最晚 32 ms、
    35 ms）。第 2 案（飢餓中失敗一次不擋、兩次才擋）是 HM-09 的規則，`dbf3c8c` 上本來就綠。
  - 堆疊測試改成在小的平台預設下跑之後（第 4.2 節 W7），在 `dbf3c8c` 上照樣紅（子直譯器 `ImportError`；`SP:hm30/f3.sh`）。
  - 第一次紅的嘗試（複本沒有連結 `apps/`）有 36 個 `test_profile_runtime.py` 的既有案例因找不到子程式 venv 而失敗，不算數，改連結後
    重跑。
- 測試先寫、先 commit（`092b827`），實作在後（`8a2703e`、`73d6cfd`）。
- 綠：第 5 節。
- 實作中途另外發現、先寫測試再修的：
  - `serve()` 裡新的區域變數 `body` 遮住了模組的 `body()`，讓 GET、DELETE 的 `lambda: body(request)` 變成 `NameError`（開關關的黃金
    回歸、SSE 測試一起紅）；改名 `encoded`，並用 AST 掃一遍 `gateway.py` 沒有別的遮蔽。
  - `processed` 在交回結果之後才加：改成先記帳再交回。
  - 「8 MiB」SSE 回覆加上框架會超過 `MAX_RESPONSE`，被當成截斷的事件丟掉：測試的 SSE 回覆改成連框架 8 MiB。
  - GIL convoy（第 3.2 節）：CPU 飢餓測試在第一版實作上紅（迴圈最長 1.27 秒、B p99 4.5 秒），加了喘息才綠。

### 4.2 臨時突變

`SP:hm30/mutate.py`：每個突變只改實作的一處，跑該抓住它的測試，再用原位元組還原並以 SHA-256 確認。最後一輪（`SP:hm30/f3.sh`，
HEAD `33798ad`）：24 個全部抓到，每個都是「1 failed」，共 88 秒。

（測試名稱沒寫檔名的都在 `tests/test_reply_worker.py`。）

| # | 突變 | 抓住它的測試 | 結果 |
|---|---|---|---|
| W1 | 做完的帳號不再排班 | `test_one_thread_takes_the_profiles_in_turn_one_job_of_each_at_a_time` | 抓到（1 failed in 10.66s） |
| W2 | 帳號一被取走工作就排回去（同時 2 筆） | `test_one_thread_takes_the_profiles_in_turn_one_job_of_each_at_a_time` | 抓到（1 failed in 0.64s） |
| W3 | 失敗工作的 frame 沒清掉 | `test_a_jobs_exception_is_its_callers_and_the_worker_goes_on` | 抓到（1 failed in 0.64s） |
| W4 | 被取消的呼叫者沒撤回排隊的工作 | `test_a_cancelled_caller_withdraws_its_queued_job` | 抓到（1 failed in 0.62s） |
| W5 | 停機時排隊的工作沒有立刻結束 | `test_stop_ends_queued_jobs_at_once_and_waits_for_the_one_in_process` | 抓到（1 failed in 1.62s） |
| W6 | 執行緒自己停時排隊的工作沒有結束 | `test_a_worker_whose_thread_ended_answers_every_job_at_once` | 抓到（1 failed in 5.64s） |
| W7 | 執行緒用平台預設的堆疊 | `test_the_worker_thread_has_a_stack_of_its_own_for_deeply_nested_replies` | 抓到（1 failed in 0.74s） |
| W9 | 工作執行緒自己的堆疊只有 1 MiB | `test_the_worker_thread_has_a_stack_of_its_own_for_deeply_nested_replies` | 抓到（1 failed in 0.74s） |
| W10 | 程序的執行緒堆疊設定沒還原 | `test_the_worker_thread_has_a_stack_of_its_own_for_deeply_nested_replies` | 抓到（1 failed in 0.67s） |
| W8 | 停機時無限等處理中的工作 | `test_stop_waits_no_longer_than_its_bound_for_a_job_that_does_not_end` | 抓到（1 failed in 10.60s） |
| G1 | 給了 worker，JSON 回覆仍在迴圈內處理 | `test_a_json_reply_is_byte_for_byte_what_the_loop_answered[ascii]`、`test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace` | 抓到（1 failed in 0.70s） |
| G2 | 給了 worker，SSE 事件仍在迴圈內處理 | `test_an_event_stream_is_byte_for_byte_what_the_loop_answered[reply-whole]` | 抓到（1 failed in 0.66s） |
| G3 | 閘道從不問待送回覆額度 | `test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call` | 抓到（1 failed in 0.81s） |
| G4 | 停掉的 worker 變成 500（不是 502） | `test_a_stopped_worker_is_answered_as_a_reply_the_gateway_cannot_process` | 抓到（1 failed in 0.64s） |
| R1 | 請求結束時不還扣的額度 | `test_the_charge_is_given_back_however_a_request_ends` | 抓到（1 failed in 0.74s） |
| R2 | 宣告長度的回覆整則交出（不分段） | `test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call` | 抓到（1 failed in 0.86s） |
| R3 | 超過上限才擋（等於上限不擋） | `test_a_slow_reader_holds_no_more_than_its_pending_reply_budget` | 抓到（1 failed in 7.32s） |
| R4 | 回覆交出時不扣額度 | `test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call` | 抓到（1 failed in 10.74s） |
| P1 | manager 不給帳號 lane | `test_switched_on_every_profile_has_its_turn_on_the_add_ons_one_worker` | 抓到（1 failed in 0.71s） |
| RP1 | worker 停了 add-on 不結束 | `test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits` | 抓到（1 failed in 0.73s） |
| RP2 | worker 從不停止 | `test_switched_on_every_profile_has_its_turn_on_the_add_ons_one_worker` | 抓到（1 failed in 0.73s） |
| B1 | 檢查點從不睡 | `test_a_busy_worker_lets_the_loop_have_the_gil_at_its_checkpoints`、`test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace` | 抓到（1 failed in 1.03s） |
| B2 | 解析器不帶檢查點 | `test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace` | 抓到（1 failed in 8.69s） |
| B3 | 迴圈忙時不多讓 | `test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace`、`test_health_tolerance.py::test_idle_profiles_health_checks_keep_their_pace_while_another_profile_starves_the_cpu` | 抓到（1 failed in 9.42s） |

第一輪（`SP:hm30/final2.sh f1`，22 個）有兩個不算數，都已處理：

- W7（執行緒用平台預設的堆疊）**沒被抓到**：測試只把程序自己的設定（`threading.stack_size`）調小，本機平台的預設（RLIMIT_STACK
  8 MiB）夠大。改成子直譯器在 512 KiB 的 RLIMIT_STACK 下啟動（glibc 用它當執行緒的預設堆疊）：平台預設與程序設定都小，9,000 層的
  解析都會當掉（本機量：1 MiB 就會），只有工作執行緒自己的 16 MiB 不會。另加 W9（工作執行緒自己的堆疊只有 1 MiB）、W10（沒有把程序的
  設定還原）。產品映像是 glibc（`python:3.13.18-slim-bookworm`），執行緒的預設堆疊跟著容器的 RLIMIT_STACK；`STACK_BYTES` 讓結果和它無關。
- G2 的測試名稱寫錯（`[whole-reply]`，實際是 `[reply-whole]`）：pytest 一個測試都沒跑、回非 0，被腳本當成「抓到」。改正名稱；腳本也改成
  pytest 回 4、5（沒有測試跑）時另外標出來，不算抓到。

## 5. 本機檢查（2026-11-16，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

| 檢查 | 結果 |
|---|---|
| 先紅後綠（共用鎖；`SP:hm30/final2.sh f1`、`SP:hm30/f2.sh`、`SP:hm30/f3.sh`） | 第 4.1 節 |
| HM-30 的測試與用到改過的工具、程式路徑的 7 檔（`test_reply_worker`、`test_health_tolerance`、`test_profile_runtime`、`test_router_passthrough`、`test_profile_quotas`、`test_profile_routing`、`test_reply_mask_union`；f1） | 237 案全過，66.4 秒 |
| 改測試之後的兩檔（`test_reply_worker.py`＋`test_health_tolerance.py`）：f2 是健康檢查改量法之後；f3 是堆疊測試也改之後（HEAD `33798ad`） | f2：76 案全過，38.1 秒；f3：76 案全過，39.0 秒 |
| 全套 pytest（`packaging/unit.sh` 的同一組指令，一般使用者；f1，HEAD `2552106`，工作區另有契約第 9 節 #17 的附註） | 5,471 案、0 skip、31 分 35 秒：5,464 通過；7 失敗＝已知要 root 的既有案例（`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`）；2 個警告是既有的 websockets 棄用警告。這一輪的 `test_health_tolerance.py` 與堆疊測試是改之前的版本，改之後的見上一列 |
| `packaging/validate.py`（CI 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt` 雜湊安裝；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準；本片沒動 `packaging/`） |
| `scripts/tool_inventory.py`（工具表面漂移檢查） | 通過：`docs/tool-surface.json`、`.md` 與原始碼一致，9 個產品的上游／支援工具數照舊；本片沒改 `apps/runtime/*.py`、`apps/*/launch.py`，不用重產 |
| 臨時突變 | 第 4.2 節 |
| f3 之後的改動 | `c43eefd` 只刪測試檔裡重複的區段標題與空行（改前改後 AST 相同）；最後一個 commit 只有文件 |
| 照 CI 裝 Chromium（`npm run browser:install --prefix packages/mcp-admin-ui`，裝在不進 git 的 `node_modules`） | 全套 pytest 前裝好，瀏覽器測試一起跑 |
| 秘密預檢、帳本預檢 | 第 8 節 |
| commit 署名 | 本片 commit 都沒有 `Co-Authored-By`、`Generated with`；身分照 clone 的 git config |
| `git status` | 乾淨（未追蹤檔 0）；用過的 `/tmp/ha-mp-*` 都已刪除；暫時的量測探針（`SP:hm30/probes/`）沒有進 repo |

共用測試鎖：每次 pytest 都用 `flock <wave1-pytest.lock>` 排隊；量測與除錯另用 repo 外的獨立腳本（`SP:hm30/bench/`，不經 pytest、
不開 3000／18000～18099，只用 MockTransport 與臨時 port），結果只當參考，數字以 pytest 為準的地方註明。

## 6. 只在 CI 跑的測試

本片新增的案例在本機都跑過且全過，沒有只在 CI 跑的新測試。CI（root、0 skip）才是準：

- 已知要 root、本機一定失敗的既有案例（不是本片造成）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`
  （基準）、`tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（HM-07）、`tests/test_restore_detection.py` 的 5 個
  `test_root_*`（HM-13a）。
- 本片的測試在 root 下沒有差別（不換身分、不碰權限）。`test_the_worker_thread_has_a_stack_of_its_own_for_deeply_nested_replies` 經
  `/bin/sh` 的 `ulimit -S -s 512` 降低 RLIMIT_STACK 的軟上限（降低誰都可以，root 也一樣）再起一個子直譯器（`-I`，只跑工作執行緒與 json，
  不開 port）；子直譯器先斷言軟上限真的是 512 KiB，沒降成功就失敗，不會悄悄變綠。
- 計時：CPU 飢餓的注入成本在 runner 上校準（每次 C 呼叫目標 10 ms，本機量到 5.7～9.9 ms；以執行緒 CPU 時間計 d），門檻和 runner 速度無關；迴圈延遲探針、B 的
  延遲、健康檢查的耗時是牆上時間。GitHub runner（4 vCPU）和本機一樣是兩個執行緒各一顆核心。慢讀的 RSS 用 `/proc/self/statm` 取樣。
- Python：CI 3.13.16、本機 3.13.15。

## 7. `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本片新測試在本機的時間（全套的 junit）：`test_reply_worker.py` 74 案 19.4 秒、`test_health_tolerance.py` 2 案 17.7 秒；大宗是 CPU 飢餓的
三個案例，各約 9 秒（契約要的情境：A 的 5 秒注入成本）。CI 推估：多約 40～60 秒（計畫 §10.1：每片增量 ≤1.5 分鐘）。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base dbf3c8c --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；`dbf3c8c..HEAD` 的 7 個 commit＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base dbf3c8c` | `runtime-patches.json` 174 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的列管檔 6 個（`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`reply_worker.py`（新）、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔：**OK** |

測試資料：沒有 commit 任何隨機 token；token 都在測試執行時產生（沿用 HM-01、HM-08 的工具與 `create_profile`）；別帳號的 token 用
`'O'*43`、`'P'*43`；憑證 `DUMMY-…`、網址 `.invalid`。

## 9. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`，本機唯讀 PaaS repo；沒有 fetch、沒有 checkout）

本機 PaaS repo 的 `origin/main` 是 `d7f5849`（2026-11-15 22:28 UTC，#155 合併；別的工作線 fetch 的）。

| 範圍 | 結果 | 對本片 |
|---|---|---|
| `69ac425..d7f5849` 基準文件第 2 節清單上的檔 | `5b84b5d` 之後新增 #155 的 5 個 commit（`7ba572d`、`3b135ca`、`e6971c0`、`1637a0f`、`a2f8905`，合併 `d7f5849`）：閘道的請求內容位元組預算（全域＋每帳號，放大倍數 20）、所有產品的 JSON 結構守門（深度、元素個數）、卡住的上傳逾時；動到 `proxy.py`、`gateway_pool.py`、`profiles.py`、`app.py`、`request_body.py`、`request_limits.py`、`setup_status.py` 與新的 `request_budget.py`、`docs/mcp-gateway-limits.md` | 都是請求端（HM-08、HM-14 的範圍，也和 HM-08 交使用者決定的「元素數上限」有關）；PaaS 仍在事件迴圈內處理回覆（`proxy.py` 沒有 `to_thread`／執行緒），§8.8 #17 不變。交主對話：HM-14 開工時對照 #155 |
| 再之前的（HM-09 筆記已列）：#151～#154 | 核心模組只有 VK 移除與 Nextcloud、EMQX 的修正 | 沒影響 |

## 10. 本片用到的決策（都已定；`decisions.md` 不用改）

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-07 (a) | 回覆一條工作執行緒依帳號輪流；開通後預設帳號也有待送回覆 32 MiB；量測後定案 | 第 3.1～3.4 節；數值沒動 |
| DQ-25 | 開通後連兩次失敗才判 unreachable（HM-09 已做） | `tests/test_health_tolerance.py` 疊在上面 |
| DQ-21 | 預設帳號的元件停止就讓 add-on 結束 | 工作執行緒是全 add-on 共用的元件，停了就讓 add-on 結束（第 3.4 節） |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 5 節；commit |

沒有碰到待定題；量測做不到契約門檻的部分照契約第 6 節回報使用者（第 14 節），沒有放寬。

## 11. 量測

本機：AMD EPYC 7713（上限 2.0 GHz）、Python 3.13.15。以 GitHub CI 為準，HM-19c 在目標硬體重量。

### 11.1 CPU 飢餓（契約第 6 節的單元測試；`tests/reply_load.py`）

情境：預設帳號（A）同時 16 個 8 MiB、16 個 2 MiB 回覆（64 KiB 一段送進來）；每個回覆的處理成本是注入的 d＝每 8 MiB 0.25 秒（佔住 GIL、
每次目標 10 ms 的 `json.loads`，在解析器的檢查點之間），內容本身幾乎不花成本；B 一直呼叫工具，B、C 的監看一直檢查。

| 指標 | 開工前（開通、在迴圈內處理；臨時探針、`dbf3c8c` 上的紅） | 第一版（工作執行緒、沒有喘息） | 最後版本（pytest 3 次：f1、f2、f3；另有獨立腳本 4 次） | 門檻 |
|---|---|---|---|---|
| A 的回覆處理期間迴圈最長停頓 | 4,417 ms | 1,266 ms | 25.0、13.9、25.3 ms；獨立腳本 17～27 ms | ≤50 ms |
| A 的回覆還在進來時（迴圈自己讀取，不是處理） | — | — | 51.6、49.2、51.9 ms；獨立腳本 34～56 ms | （不算） |
| B 的 tools/call p50／p99 | 53／4,466 ms | 64／4,534 ms | 295／397、307／419、316／357 ms；獨立腳本 p99 381～440 ms | p99 ≤2d＋0.2＝700 ms |
| B、C 的健康檢查 | 沒有逾時，但在該做之後最晚 4,409／4,403 ms 才做完（各 15 次） | — | 0 次逾時、判定一直 reachable；在該做之後最晚 32／35、31／50 ms 做完（f2、f3，各 85 次） | 0 次逾時 |
| 每帳號同時處理 | — | 1 | 1 | ≤1 |

- 注入的單次 C 呼叫在啟動時校準（目標 10 ms）：三次 pytest 量到 9.9、6.8、5.7 ms（機器忙時校準偏短，仍比 GIL 的 5 ms 切換間隔長）；
  總成本以執行緒 CPU 時間計，每次都付滿（5.1～5.2 秒）。最短 5.7 ms 的那一輪，B1～B3 三個喘息的突變照樣抓到（第 4.2 節）。
- 開工前本機沒有逾時（4.4 秒 < 8＋5 秒的時限），但檢查晚了 4.4 秒；目標硬體慢數倍時就會逾時（C2 的 `cross_profile_probe_sim`）。
  所以測試的門檻是「該做之後 d 內做完」，比逾時嚴得多。
- f1 的健康檢查是改量法之前的版本（只量檢查本身：最慢 24 ms），不列。

### 11.2 GIL convoy（`test_a_busy_worker_lets_the_loop_have_the_gil_at_its_checkpoints`；另有獨立量測腳本 `SP:hm30/bench/convoy.py`、`coop.py`）

| 工作執行緒在做什麼 | 迴圈每次小檔讀取（中位數） |
|---|---|
| 沒有工作執行緒 | 0.02 ms |
| 連續 10 ms 的 C 呼叫、不喘息（switch interval 5 ms 或 1 ms 都一樣） | 30～62 ms |
| 同上，每次 C 呼叫後 `time.sleep(0)` | 約 10 ms |
| 同上，每次 C 呼叫後睡 1 ms | 0.03 ms（p99 10 ms） |
| 本片的檢查點（`breathe`） | 0.03～0.05 ms（pytest 3 次：0.049、0.049、0.051 ms；同一輪不喘息 43～59 ms） |

真實 8 MiB 回覆（mixed）處理期間迴圈的小檔讀取：不喘息 16 次、p50 10.5 ms；步驟之間各睡 1 ms 107 次、p50 0.03 ms；再加解析器的檢查點
546 次、p99 10 ms；再加遮罩與序列化也分段 1,996 次、p99 5 ms（處理時間 2.4 倍）。

### 11.3 真實 8 MiB 回覆的迴圈停頓（`test_a_real_8_mib_reply_stops_the_loop_for_its_longest_c_call_only`）

C2 的 mixed 形狀（同一批紀錄一半是 JSON 文字、一半是 structuredContent），8.00 MiB：

| 在哪裡處理 | 迴圈最長停頓 | 這一筆的請求時間 |
|---|---|---|
| 迴圈內（今天） | 246～310 ms | 265～334 ms |
| 工作執行緒（最後版本） | 45.0、45.2、42.3 ms（pytest 3 次）；45.5 ms（獨立腳本）；沒有解析器檢查點的版本 52～82 ms | 297～343 ms |
| 一次 `json.dumps` 整個值（拆不開的單一 C 呼叫） | 44～66 ms（機器忙時較長） | — |

**目標硬體上做不到契約的 ≤50 ms**（本機 42～45 ms，剛好在邊上；一次 `json.dumps` 就 45～66 ms，J6412／J1900 慢數倍）。原型（`SP:hm30/bench/pieces.py`，沒有進 repo）：
序列化分段（大的 list、dict 逐個元素用 C 編碼器、再接起來；輸出位元組逐位元相同）時迴圈最長停 15 ms，處理時間 1.8 倍；大量小物件的形狀
仍有 62 ms，來自工作執行緒配置大量物件時觸發的全代 GC。交使用者決定（第 14 節）。

### 11.4 慢讀與一次湧入（`test_a_slow_reader_holds_no_more_than_its_pending_reply_budget`；湧入是臨時探針 `SP:hm30/probes/`）

| 情境（B 的用戶端都不讀；真 listener、h11） | 帳上（待送回覆） | 位元組額度（請求端） | 管理程序 RSS 增量 | 門檻 |
|---|---|---|---|---|
| 依序 2 個 JSON＋2 個 SSE 回覆各 8 MiB，SSE 的請求各帶 4 MiB 參數；之後 B 的 tools/call 立刻 200＋`-32003`、預設帳號與 C 照常 | 32.0 MiB | 8.0 MiB（兩條開著的 SSE 的轉送內容） | 121 MiB | ≤296 MiB：達到 |
| 一次湧入：額外帳號同時 16 個 8 MiB（它的轉送名額） | 128 MiB | — | 276 MiB | 在 296 以內，但幾乎貼著 |
| 一次湧入：預設帳號同時 32 個 8 MiB（只有 28 個在達到上限前轉送出去） | 224 MiB | — | 469 MiB | **超過 296**：軟上限的代價（第 14 節） |

loopback 上每條連線核心先吃掉約 4 MiB（`SO_SNDBUF` 自動長到 4 MiB），剩下的才留在程序裡；帳上算的是整個回覆（`Response` 一直持有它）。

### 11.5 待 HM-19c 量測的門檻（契約第 5、6 節；都還是暫定）

| 門檻 | 本片的結果 | HM-19c 要量的 |
|---|---|---|
| 迴圈單次停頓 ≤50 ms（可控注入） | 13.9～27 ms | J6412（可以的話 J1900）同情境；真實回覆（mixed、大量小物件）的停頓 |
| B 的 tools/call p99 ≤2d＋0.2 秒（單元）；HAOS 上 p95 增量 ≤1 秒 | 0.36～0.44 秒 | HAOS 上的 p95 增量 |
| B、C 健康檢查 0 次逾時（8＋5 秒） | 0 | HAOS 上同情境 |
| 慢讀 RSS ≤296 MiB | 121 MiB | 目標硬體的 RSS 與 MemAvailable；一次湧入的 RSS（第 14 節的決定之後） |
| 待送回覆 32 MiB（每帳號） | 照契約 | 對 MemAvailable 比對全域最壞值時一起看（含轉送中的回覆） |
| 喘息參數（5 ms／2 ms／10 ms） | 本機量的 | J6412／J1900 上 B 的延遲與工作執行緒的吞吐（A 的回覆要多久做完） |

## 12. 驗收條件（計畫 §12.3 HM-30）

| 條件 | 結果 |
|---|---|
| 輸出位元組不變 | 通過：同一個 `make_apps` 兩條路逐案對照（JSON 24、SSE 14×2、GET 1）全部相同；HM-01 黃金回歸與兩個契約凍結開關開與關都照過、斷言沒改 |
| CPU 飢餓測試達契約門檻 | 通過（第 11.1 節：停頓、B 的 p99、健康檢查、每帳號 1 筆）。另：真實 8 MiB 回覆的停頓本機 42～45 ms、目標硬體一定超過 50 ms，照契約回報（第 11.3、14 節） |
| 慢讀測試達契約門檻 | 依序慢讀通過（第 11.4 節）；一次湧入時預設帳號超過（軟上限），回報（第 14 節） |
| 開關關時完全照今天 | 通過（第 3.6 節） |
| 獨立安全審查 | 還沒做：合併前由主對話安排（本片標「審查」） |
| 同 PR 更新帳本；契約「暫定」細節同步並在變更紀錄加一列 | 通過（第 8 節；契約第 6 節「HM-30 定案」與量測、第 9 節 #17 附註、第 10 節一列） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空集合；commit 沒有 AI 署名 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過 |

## 13. 前面的片交給 HM-30 的事項，與交給後面的片

### 13.1 前面的片交給 HM-30 的事項（逐條 grep `docs/provenance/ha-multiprofile-HM-*.md`）

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-08 第 14.2 節 | 待送回覆位元組額度（C1-M5「預設帳號當攻擊方＋大回覆」那一半） | 做了：第 3.5 節；預設帳號也是 32 MiB（`DEFAULT_PROFILE_QUOTA.pending_reply_bytes`），`pending_reply()` 對每個帳號的 gate 都有效 |
| HM-08 第 14.2 節 | 回覆工作執行緒 | 做了：第 3.1～3.3 節 |
| HM-08 第 14.2 節、HM-08 審查報告第 9 節 | 「慢讀 RSS」的量測要含 SSE 串流期間的轉送內容（位元組額度扣到請求結束）；HM-19c 量測放「SSE 期間的轉送內容」與「非 ASCII 內容 3 倍」 | 慢讀測試做了：四個 8 MiB 回覆裡兩個是 SSE、請求各帶 4 MiB 的參數，斷言串流開著時該帳號的位元組額度仍扣著轉送內容（≥8 MiB）、RSS 增量含它（第 11.4 節）。非 ASCII 的 3 倍屬 HM-19c 的記憶體量測（請求端，HM-08 的範圍），交 HM-19c（第 13.2 節） |
| HM-09 第 3.10 節第 13 點、第 13.2 節 | 「連兩次失敗」的規則 HM-09 已做；HM-30 留 CPU 飢餓下的整合測試 `tests/test_health_tolerance.py` | 做了：疊在 HM-09 的規則上（第 11.1 節）；`health.py` 沒改 |
| HM-06 第 12.3 節（審查 S-07） | 子程式回 401 時健康監看只看到 `MCP_SERVER_NOT_READY`，要不要加專屬原因碼，由 HM-09／HM-30 決定 | HM-09 已決定不加（它的筆記第 13.1 節：只有閘道自己的 child bearer 會送到子程式，401 代表設定錯，`backend/test` 與 diagnostics 看得到）。本片沒動健康探測，沿用、不加 |
| HM-00 第 10 節 | 回覆排程的停頓門檻 ≤50 ms 可能做不到：用真實 8 MiB 回覆量，做不到就回報使用者再定，不自行放寬 | 量了：本機 42～45 ms 剛好在邊上，目標硬體一定做不到（第 11.3 節）；回報使用者（第 14 節），門檻沒改 |
| HM-01 第 1 節 | HM-04～HM-30 每一片都要照過黃金回歸與契約凍結 | 照過：開關關與開兩種都跑（第 5 節），斷言沒改 |
| HM-05 第 443 行（合併順序） | `profile_runtime.py` 照 HM-05 → HM-08 → HM-09 → HM-13b → HM-30 → HM-25 | 本片疊在 HM-09 上；HM-13b 還沒合併，rebase 時照順序重產帳本（第 13.2 節） |

其他各片（HM-02、HM-04、HM-07、HM-13a、HM-17）的筆記沒有交給 HM-30 的事項。

### 13.2 交給後面的片與主對話

- **rebase**（主對話）：`gateway.py` 照 HM-10 → HM-14 → HM-30 合併；`profile_runtime.py` 照 HM-09 → HM-13b → HM-30；`run_product.py` 照
  HM-09 → HM-13b → HM-30。rebase 後一律重算帳本（`runtime-patches.json` 的 6 列，含新的 `reply_worker.py`）、重跑兩個預檢與 CI；契約第 2.4、5、6、10 節和 HM-10、HM-14
  可能改的地方相鄰。本分支沒有 #100（checks 上限 60 分鐘、`decisions.md` 的 DQ-13／14／30／31／43），rebase 時一起進來。
- **HM-09 介面若小改**：本片用到 HM-09 的地方集中在兩處：`HealthMonitor.check()`／`availability()`（`tests/test_health_tolerance.py`）與
  `ProfileManager.add()` 建 `ProfileRuntime` 的那一行（`reply_worker=` 參數）；`multi_profile_runtime` 的 `Runtime.task`／`may_stop` 是新加的。
- **HM-14**：排隊上限與通知保留名額放在轉送名額那裡；本片的待送回覆檢查在轉送名額**之前**（`serve()` 的 `PENDING_REPLIES`），rebase 時要維持
  在排隊之前（被擋的 tools/call 不該先排隊再被擋）。`-32003` 文字定稿時一起看 `profile_router.pending_text()`。開關關時子程式 initialize 錯誤
  沒遮罩（HM-08 審查 S-4）仍是 HM-14 的事；本片的 initialize 回覆照舊在迴圈內處理。
- **HM-19c**：在 J6412（可以的話 J1900）重量契約第 6 節：B 的 tools/call p95 增量 ≤1 秒、健康檢查 0 次逾時；也量真實回覆（第 11.3 節的
  mixed 形狀、大量小物件）的迴圈停頓與一次湧入時的 RSS（第 11.4 節），對 MemAvailable 比對。
- **HM-18**：文件寫明待送回覆額度是軟上限、工作執行緒停了 add-on 會重啟、真實大回覆仍會讓迴圈停一次 C 呼叫那麼久。
- **獨立安全審查**（計畫 §12.0 第 9 點；本片標「審查」）：合併前由主對話安排，報告放 `artifacts/`。

## 14. 待使用者決定（照契約第 6 節回報，門檻都沒放寬）

1. **真實大回覆的迴圈停頓**：一筆 8 MiB 回覆裡拆不開的單一 C 呼叫（整個值一次 `json.dumps` 本機 45～66 ms；長字串的掃描與取代）讓迴圈
   停 42～45 ms（沒有解析器檢查點時 52～82 ms），本機剛好在 50 ms 內，J6412／J1900 慢數倍，一定超過。選項：
   - (a) 序列化分段（大的 list、dict 逐元素用 C 編碼器再接起來；原型量到 15 ms、輸出逐位元相同、處理時間約 1.8 倍）；大量小物件另有
     GC 的停頓（62 ms），可能還要搭配 `gc.freeze()` 或分段配置。
   - (b) 改用子程序處理回覆（沒有 GIL 共用；新的子程序生命週期、IPC 複製、記憶體另算）。
   - (c) 接受，HM-19c 以 HAOS 上「B 的 p95 增量 ≤1 秒、健康檢查 0 次逾時」為發版門檻（單次停頓門檻改成只對可控注入）——這等於放寬，要
     使用者同意。
   建議：(a)，若 HM-19c 在 J1900 上仍過不了再考慮 (b)。
2. **待送回覆額度是軟上限**：已轉送的回覆一律交出（照順序讀回覆的用戶端才不會卡死），所以一次湧入時帳號最多持有「上限＋轉送名額個
   8 MiB」：預設帳號 32 個不讀的 8 MiB 回覆時 RSS 增量 469 MiB（契約 296 MiB）。選項：
   - (a) 接受並寫進文件（今天沒開通時的最壞是 64×8 MiB，開通後已減半以上）。
   - (b) 轉送前另外用「轉送中的 tools/call 數 × 估計值」預扣（會讓大量小回覆的並行也被擋）。
   - (c) 降低預設帳號的轉送名額（32 → 16）。
   - (d) 工作執行緒在帳號超過上限時暫停處理它的回覆（會讓照順序讀的用戶端卡到逾時：不建議）。
   建議：(a)，HM-19c 對 MemAvailable 比對時把「轉送名額 × 8 MiB」算進全域最壞值。
