# HA 多帳號 HM-30 provenance：回覆處理公平排程、待送回覆額度、健康檢查容忍（2026-11-16）

## 結論

- **rebase 到 `claude-delivery` `7646f0f` 與使用者對 Q1、Q2、Q4 的回答（2026-11-17，第 18 節）**：第 1～17 節照當時寫，commit 編號是
  這次 rebase 前的（對照在第 18.9 節）。
  - 基準 `7646f0f`（HM-11 #107、HM-12 #110 合併後）。34 個 commit 照原順序重放，10 個有衝突，都是兩邊在同一處各加東西：新基準的行在前、
    本片的在後；HM-11、HM-12 的行一行都沒少。帳本照 JSON 重組，當資料核對 0 個問題。
  - 和 HM-12 的換身分沒有語意衝突：發布那一刻舊 token 的請求都結束，工作執行緒上排隊的撤回、處理中的結果丟掉，名額與待送回覆位元組都還
    回來（暫存區實驗 X12 三案都過）。
  - 使用者 2026-11-17 03:1x：Q1、Q2 接受，Q4 維持現狀，都是 HM-19c 實測再定；門檻都沒放寬。
  - 本機：本片 4 檔 251 案、相關 28 檔 836 案、HM-12 與 HM-11 的 87 案、`test_output_schemas.py` 189 案全過；全套 6,211 案只有 7 個要 root 的既有案例紅、0 skip。量停頓的
    測試各單獨 5 次都綠（D1 70 案次最高 42.7 ms；D3 整段 29.3～36.9 ms）。CI 紅了先由主對話回報使用者，不放寬門檻、不加重試。
- **第二輪獨立安全審查（2026-11-17，第 17 節）判定「修正後通過」**（報告在 repo 外：
  `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-30-phase2.md`，審查 `37160d6`）。程式本身沒有找到安全漏洞。
  - 必修 5 項都處理了：MF-1 扁平陣列在解析、遮罩、成本計算、放掉時都喘息（數字陣列本機過門檻）；MF-2 改程式，讓一次湧入的上界 800／416 MiB
    成立（真額度實測 792／408 MiB），使用者接受的 D2 不用重問；MF-3 補遮罩的測試；MF-4 寫進契約與威脅模型；MF-5 PR 說明重寫。
  - 建議 6 項：S-2～S-6 採用；S-1 沒採用（量了，把用戶端移出被量的迴圈沒有效果，第 17.6 節）。另外修了前一段寫出來的一個錯（值與 twin 是
    同一個容器時 KeyError）。
  - **合併前要使用者答的三題**（第 17.10 節；使用者 2026-11-17 03:1x 已答，第 18.6 節）：Q1 沒有物件也沒有數字的陣列，解析仍是一次 C 呼叫（8 MiB 本機 0.03～0.19 秒）；Q2 D1 讓別的帳號
    等更久（A 同時送 3 個大量小物件回覆時 B 的 p95 3.5 秒）；Q4 請求端的停頓（一個大請求 0.09～0.25 秒）。
  - 量停頓的測試本機偶爾紅（照實記，第 17.6 節）：D3 整段 11 次紅 1 次（63.3 ms，讀取期間，最長那一下在請求端），D1 真實回覆 98 案次紅
    1 次（浮點數 50.5 ms，判斷是共用主機讓整個程序停住）；小而忙的機器上 D3 會紅（審查 S-1）。CI 跑完把數字補進第 17.6 節。
- **rebase 到 `claude-delivery` 與 D1～D3（2026-11-16，第 16 節）**：第 1～15 節照 rebase 前寫，commit 編號是 rebase 前的（對照在
  第 16.13 節）。
  - rebase：基準換成 `df686dd`（HM-31 #105、HM-09 追補 #106 等都已合併）。11 個 commit 照原順序重放；衝突兩邊都留，順序照交辦；
    待送回覆檢查放在 HM-14 的排隊之前；帳本以新基準為底重算。兩個合併點用突變確認過。
  - 使用者 2026-11-16 14:0x 對 D1～D3 都選 (a)，本片都做了，門檻沒放寬：
    - D1：工作執行緒分段序列化（和 `json.dumps` 逐位元相同）。七種形狀與兩種事件的真實 8 MiB 回覆，迴圈最長停頓本機 7.3～46.3 ms
      （D1 之前 9 案裡 6 案超過 50 ms，最高 125.9 ms）。
    - D3：CPU 飢餓改量整段。修了測試工具的錯，開通時每段只查一次 token。本機整段最長停頓 34.4～45.9 ms（6 次）。
    - D2：契約與威脅模型寫明軟上限與一次湧入的最壞值（預設帳號 800 MiB、額外帳號 416 MiB）。
  - **餘裕只有約 4 ms**（D1 跳脫字元多的長字串、D3 的 32 個請求同時開始那一下）：CI 或目標硬體可能紅，紅了照定案回報使用者
    （第 16.14 節）。
  - 還沒解決、交主對話：請求端（本片審查 S-5；結構守門那部分是 HM-31 審查 S-3）一個大請求本機仍讓迴圈停 0.09～0.25 秒（第 16.14 節）。
  - D1、D3 的程式是審查之後加的，還沒有獨立審查（第二輪審查已審，第 17 節）。
- **獨立安全審查（2026-11-16）判定「修正後通過」**（報告在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-30.md`）。
  必修 3 項都處理了：MF-1 不穩的測試改成先等執行緒結束；MF-2 預設帳號的待送回覆額度補測試；MF-3 待使用者決定的數字照實更正、新增 D3。
  建議 7 項：S-1～S-5、S-7 採用，S-6 留到之後（理由見第 15 節）。審查修正只改測試、文件與 `reply_worker.py` 兩處說明文字，門檻與行為都沒改。
  **合併前要有使用者對 D1～D3 的答案**（第 14 節；使用者已定，做法見第 16 節）。審查看的是 rebase 前的 `5b6d4a5`；D1、D3 的程式是審查之後加的。
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
  4.4 秒）、每帳號同時 1 筆。慢讀 RSS 增量 121 MiB（≤296）。審查修正後重跑：處理期間 11.1～28.0 ms、B 的 p99 0.31～0.44 秒、
  健康檢查最晚 26～54 ms、慢讀 RSS 增量 ASCII 116～120 MiB、emoji 116 MiB（第 11 節）。
- **三項回報使用者，照契約第 6 節（第 14 節），門檻沒放寬**。使用者 14:0x 都選 (a)，做法與重量的數字在第 16 節。下面是回報時的數字
  （審查 MF-3 更正後的）：
  1. D1 真實大回覆的迴圈停頓：mixed 形狀 42～49 ms；單一長字串一次 `json.dumps` emoji 66～69 ms（審查）／46～48 ms（本片重量）、
     CJK 43～45／32～33 ms；J6412／J1900 慢數倍，一定超過。
  2. D2 待送回覆額度是軟上限，扣的是跳脫後的大小：預設帳號一次湧入 32 個不讀的 8 MiB 回覆，ASCII 時 RSS 增量 469 MiB、emoji 時
     632 MiB（審查 X2；契約的 296 MiB 是照硬上限寫的）。
  3. D3（審查新列）讀取期間的停頓算不算進門檻：讀取與處理重疊時 48.5～59.0 ms，8 次裡 5 次超過 50 ms。原本寫「不算進門檻」，已改成待決。
- 新測試 2 檔 76 案＋測試工具 1 檔（`tests/reply_load.py`）；改 2 個既有測試檔。審查修正後 2 檔 88 案（第 15 節）。**先寫測試**：`test_reply_worker.py` 74 案在
  `dbf3c8c` 上全紅（61 錯誤、13 失敗）；`test_health_tolerance.py` 第 1 案（改量法之後）在 `dbf3c8c` 上紅（檢查在該做之後 4.4 秒才
  做完），第 2 案是 HM-09 的規則，本來就該綠；`test_profile_runtime.py` 的 2 個名單案例紅（第 4.1 節）。
- 臨時突變 24 個全部抓到（第一輪 22 個裡 1 個沒抓到、1 個寫錯測試名稱，補了測試與 2 個突變後重跑；第 4.2 節）。審查存活的 7 個突變
  用審查自己的改法重跑，另加 4 個（F01、M27、M04、M26），審查修正的新測試都抓到（第 4.3 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest：5,471 案、0 skip、31 分 35 秒，5,464 通過；7 個失敗都是已知要 root
  的既有案例（第 5 節）。以上是 rebase 前的；rebase 後的在第 16.11 節。
- 這個階段只 commit，不 push、不開 PR。獨立安全審查已做（本片標「審查」）：修正後通過（第 15 節）。

## 1. 範圍與基準

縮寫同計畫：`Hc/`＝`packages/mcp-admin-core/mcp_admin_core/`；`SP:`＝這次工作的暫存區（不進 repo）。

| 項目 | 值 |
|---|---|
| 切片 | HM-30（計畫 §12.3；風險中、工作量 M；標「審查」：合併前要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm30-20261116`（一般 clone），疊在 HM-09 的修正 head `dbf3c8c` 上；2026-11-16 rebase 到 `claude-delivery` `df686dd`（第 16 節）；2026-11-17 再 rebase 到 `7646f0f`（第 18 節） |
| 基準 | `dbf3c8c`＝HM-08 最終 head `adfc4bf`＋HM-09 的實作與審查修正。`claude-delivery` 已合併 HM-00～HM-08、HM-13a、HM-17、HM-02 與 #100；本分支沒有 #100，rebase 時處理。rebase 後的基準是 `df686dd`（第 16.1 節）；2026-11-17 的基準是 `7646f0f`（HM-11 #107、HM-12 #110 合併後，第 18.1 節） |
| 依據 | 計畫 §5.5（全部）、§5.2、§5.4、§10.3 的 HM-30 列、§12.0、§12.3 HM-30；契約 §2.4、§5、§6、§7、§9 #15、#17、#18；`threat-model.md` I8；FM-129、FM-130、FM-149；C2-MF-4、C1-M5；DQ-07 (a)、DQ-21、DQ-25；HM-06、HM-08、HM-09 的 provenance 筆記交給 HM-30 的事項（第 13.1 節） |
| 對齊的 PaaS | 沒有。PaaS 在事件迴圈內處理回覆（§8.8 #17 是 HA 的部署差異）；第 9 節列出 pin 之後的 PaaS 變動 |
| commit（`dbf3c8c` 之後 11 個） | `092b827` 測試先寫；`8a2703e` 工作執行緒；`73d6cfd` 待送回覆額度；`2552106` 契約、威脅模型、帳本；`33798ad` 兩個測試改寫（第 4.1、4.2 節）；`c43eefd` 只刪測試檔裡重複的區段標題（AST 相同）；`5b6d4a5` 契約第 6 節量測數字、第 9 節 #17 附註、第 10 節一列與本筆記。審查修正（第 15 節）：`503fb3d` 測試（MF-1、MF-2、S-1～S-4、S-7，與驗證時找到的另一個競態）；`6e073c3` `reply_worker.py` 兩處說明與帳本；`e84bd8f` 契約、威脅模型、驗收表；最後一個是本筆記。這些是 rebase 前的編號；rebase 後的編號與之後加的 commit 見第 16.13 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/reply_worker.py`（新，列管） | `ReplyWorker`：全 add-on 一條工作執行緒（`mcp-reply-worker`、daemon、自己的 16 MiB 堆疊 `STACK_BYTES`）；`run(profile, function, *args)` 把純函式交給它、在呼叫者的迴圈拿回結果或例外；每帳號一個佇列、輪流（`_next`、`_done`）；被取消的撤回（`_withdraw`）；執行緒自己停時全部 `WorkerStopped`、`ended`、`failure`、一行 WARNING（`_main`、`_end`）；`stop()`（排隊的立刻結束、處理中的最多等 `STOP_SECONDS` 5 秒）；`Lane`（一個帳號的班次）；`breathe()`（檢查點：`SLICE_SECONDS` 5 ms、`BREATH_SECONDS` 2 ms、`YIELD_SECONDS` 10 ms；`_loop_busy()` 看迴圈的 ready 佇列與迴圈執行緒的 frame）；`handed`（每帳號交出幾筆）。審查修正：`ended`、`handed` 兩處說明（MF-1、S-7） |
| `Hc/config.py`（列管） | `strict_json` 多一個 keyword-only 的 `checkpoint`：每建一個 JSON 物件前呼叫一次；不給時 hook、值與每個錯誤都照舊 |
| `Hc/gateway.py`（列管） | `make_apps` 多一個 keyword-only 的 `reply_worker`（只在開通的產品給）。回覆處理抽成 `relayed_reply`（JSON）與 `relayed_event`（SSE 事件），兩條路都跑它們：沒給時在迴圈裡、照今天讀 state、不帶檢查點；給了時 `prepared()` 在迴圈裡先讀 state 與遮罩，工作執行緒跑 `worker_reply`／`worker_event`（解析器與步驟之間呼叫 `breathe`），回應用 `encoded_reply`（`json_reply` 也改用它，位元組相同）。`WorkerStopped` → 502（JSON）或串流結束。新的 request-state 名稱 `PENDING_REPLIES`：tools/call 轉送前（政策與閘道自答之後、轉送名額之前）問一次 |
| `Hc/profile_router.py`（列管） | `ProfileGate` 多 `reply_bytes`（交給 server、還沒收走的回覆位元組）與 `pending_reply()`（`PENDING_REPLIES`：達上限回 200＋`-32003`，WARNING 每帳號 60 秒一行）；`counted_send` 交出回覆時扣、下一則被收走或請求結束時還；宣告長度的回覆分 `REPLY_PIECE`（64 KiB）交出、最後補一則空的；`pending_text()`（暫定文字，HM-14 定稿 `-32003` 文字時一起看）；模組說明 |
| `Hc/profile_runtime.py`（列管） | `ProfileRuntime` 多 keyword-only 的 `reply_worker`（存成 `runtime.reply_worker`、加進 `RUNTIME_OPTIONS`）；`ProfileManager` 多 `reply_worker`，每個帳號（含預設）拿自己的 `Lane` |
| `Hc/run_product.py`（列管） | 開通的產品建一個 `ReplyWorker` 交給 `ProfileManager`；listener 服務前 `start()`、和其他元件一起看 `ended`（執行緒停了＝`runtime component stopped`）、listener 與 monitor 都停了之後、帳號關閉之前 `stop()`。沒開通：`worker=None`，流程與元件照舊 |
| `tests/test_reply_worker.py`（新） | 工作執行緒本身 9 案（含 GIL convoy、自己的堆疊）；JSON 24 案、SSE 14×2 案、GET 串流 1 案的逐位元對照；例外、停掉的 worker、state 在迴圈讀；開關開與關的 runtime；執行緒自己停、停機；CPU 飢餓；真實 8 MiB 回覆；待送回覆額度 2 案；慢讀 RSS。審查修正（第 15 節）：不穩的測試改一行（MF-1）；待送回覆額度預設帳號一案（MF-2）；慢讀 emoji 一案（S-1）；轉送名額之前判斷、state 讀不到時兩條路的順序（S-2）；token 換了時排隊的工作撤回（S-3）；檢查點與解析器檢查點的計數型測試（S-4）；啟動與停止的順序（S-7）；CPU 飢餓測試的說明不再寫「讀取期間不算進門檻」（MF-3） |
| `tests/test_health_tolerance.py`（新） | CPU 飢餓下 B、C 的健康檢查；飢餓中失敗一次不擋、兩次才擋 |
| `tests/reply_load.py`（新，測試工具） | CPU 飢餓的情境：A 的 16 個 8 MiB 與 16 個 2 MiB 回覆（64 KiB 一段送）、佔住 GIL 的可控處理成本 `GilWork`（啟動時校準成每次約 10 ms 的 `json.loads`、以執行緒 CPU 時間計 d）、迴圈延遲探針 `LoopLag`。審查修正：`Starved` 的說明改成「讀取期間算不算進門檻待使用者決定」（MF-3） |
| `tests/multi_profile_runtime.py` | HM-08 的工具：`Runtime.task`（run_product 的 task）與 `may_stop`（讓「worker 停了 add-on 就結束」的測試讀得到結果，其他測試照舊斷言「只會被取消」） |
| `tests/test_profile_runtime.py` | HM-05 的兩案：`make_apps` 與 `app_options` 的名單加 `reply_worker` |
| `docs/multi-profile/contract.md` | 第 2.4 節「待送回覆」列、第 5 節定義與最壞值的補充、第 6 節「HM-30 定案」與「HM-30 本機量測」、第 9 節 #17 的附註、第 10 節一列；門檻都沒改。審查修正：第 5 節慢用戶端讓准入與位元組額度扣得較久（S-7）；第 6 節「HM-30 定案」加請求端 CPU（S-5）與 SSE 事件的 state 讀取（S-6）兩條；量測表的讀取期間改「未定、待使用者決定（D3）」、真實回覆補長字串、湧入補 emoji、慢讀補 emoji（MF-3、S-1）；第 10 節一列 |
| `docs/multi-profile/threat-model.md` | I8 的測試欄寫明待送回覆額度是軟上限。審查修正：I8 的測試欄補預設帳號的待送回覆額度與 emoji 慢讀；第 3 節補請求端 CPU（MF-2、S-1、S-5） |
| `docs/multi-profile/ledger-tracking.md` | `reply_worker.py` 那列改成實際路徑、HM-30 起列管 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表 HM-30 的兩列。審查修正：`test_reply_worker.py` 那列補新測試 |
| `docs/provenance/runtime-patches.json` | 新增 `reply_worker.py`；5 個列管檔（`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`run_product.py`）重算摘要並補說明。審查修正：`reply_worker.py` 照實際內容重算、說明補一句 |
| 本筆記 | 審查修正：結論、第 1、2、4.3、5、7、8、11、12、13、14 節，新增第 15 節 |

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
  帳號最多持有「上限＋達到上限時正在轉送的回覆」。後者最多轉送名額個（額外帳號 16、預設 32），每個最多 8 MiB 原始大小，和今天相同。帳上扣的是閘道序列化之後的大小：
  非 ASCII 的回覆跳脫後變大（CJK 約 2 倍、emoji 約 3 倍；審查 MF-3、S-1），一個 8 MiB 的 emoji 回覆就扣約 24 MiB。
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

### 4.3 審查修正的守門證據

- MF-1：同一個測試參數化 200 次（只在暫存區、沒進 repo 的檔 `SP:hm30fix/scratch-tests/test_zz_hm30fix_flaky.py`）。HEAD `5b6d4a5`：
  20 失敗、180 通過（11.5 秒），失敗都是 `not worker.alive`；修正後：200 次全過；驗證時找到的另一個競態（`test_a_worker_that_stops_by_itself…`，第 15 節表末）修正後 50 次全過（兩個一起 250 案 12.8 秒）。
- 突變（`SP:hm30fix/mut/mutate.py`，在 clone 的複本上；審查的改法逐字照用，每個只跑為它加的測試，`-x`；還原後以 SHA-256 與複本的
  `git status` 確認）：

| # | 突變 | 抓住它的測試 | 結果 |
|---|---|---|---|
| M15 | 預設帳號不受待送回覆額度限制 | `test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call[default-profile]` | 抓到（1 failed in 0.99s） |
| M16 | 待送回覆檢查移到拿轉送名額之後 | `test_a_profile_past_its_pending_reply_budget_is_answered_before_it_waits_for_a_slot` | 抓到（1 failed in 2.02s） |
| M19 | 等工作執行緒時不在 token 租約下 | `test_a_queued_reply_whose_token_changes_is_withdrawn_at_once` | 抓到（1 failed in 8.99s） |
| M22 | `prepared()` 讀不到 state 就當場丟（503 先於 502） | `test_a_state_that_cannot_be_read_fails_the_worker_where_it_fails_the_loop` | 抓到（1 failed in 0.85s） |
| M25 | 工作執行緒在 listener 服務之後才啟動 | `test_the_worker_starts_before_the_listeners_serve_and_stops_once_they_stopped` | 抓到（1 failed in 1.39s） |
| F01 | 工作執行緒在 listener 停下之前就停（本片自加） | 同上 | 第一次**沒抓到**：測試只記最後一次 `stop()`（停機時 `stop()` 會再被呼叫一次），改成每次都記、每次都要求 listener 已停之後抓到（1 failed in 0.87s） |
| M27 | 檢查點從不睡 | `test_a_checkpoint_gives_way_for_as_long_as_the_loop_is_busy` | 抓到（1 failed in 0.77s） |
| M28 | 迴圈忙時不多讓（只睡固定 2 ms） | 同上 | 抓到（1 failed in 0.74s） |
| M29 | 解析器不帶檢查點 | `test_the_parser_gives_the_worker_a_checkpoint_at_every_object` | 抓到（1 failed in 0.90s） |
| M04 | 執行緒自己停時排隊的工作不結束（確認改過的競態測試照樣守） | `test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits` | 抓到（1 failed in 1.13s） |
| M26 | 工作執行緒停了 add-on 不結束（同上） | 同上 | 抓到（1 failed in 1.10s） |

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

審查修正後（2026-11-16，`SP:hm30fix/session1.sh`～`session5.sh`，每次都排在共用鎖後面；TMPDIR 照舊用 `/tmp/ha-mp-XXXXXX`，每個都用完整路徑刪除）：

| 檢查 | 結果 |
|---|---|
| 本片 2 檔（`SP:hm30fix/s3`，最後版本） | 88 案全過、0 skip，40.7 秒（`test_reply_worker.py` 86 案 22.5 秒、`test_health_tolerance.py` 2 案 17.4 秒）；`SP:hm30fix/s1` 那一輪也 88 案全過（49.1 秒，含等共用鎖 9 秒） |
| 第一次跑（`SP:hm30fix/s1-red1`） | 87 過、1 紅：既有的 `test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits`（第一個回覆被 add-on 停機截斷，第 15 節表末）；修正後見上一列 |
| 兩個競態測試重複跑 | MF-1 那個 200 次、驗證時找到的那個 50 次：250 案全過、12.8 秒 |
| 重跑量數字（CPU 飢餓、真實 8 MiB、慢讀 ascii／emoji、健康檢查容忍 2 案；2 次） | 都過；數字在第 11 節 |
| HM-01 黃金回歸＋兩個契約凍結（開關關） | 45 案全過、15.5 秒；三檔與 `tests/contract/` 沒改 |
| 相關 35 檔（開關開的黃金回歸 `test_router_passthrough.py`、HM-05／08／09 的 runtime、路由、額度、健康、SSE、遮罩、租約等，清單同審查） | 1,404 案全過、0 skip、336 秒 |
| 審查實驗重跑（X2 預設帳號 32 個 emoji 湧入、X5 讀取期間停頓的拆解 4 次；另加讀取期間停頓的時間點 4 次） | 數字在第 11 節；實驗檔只在暫存區，跑時暫放 `tests/`、跑完刪除 |
| 突變（第 4.3 節） | 11 個，最後都抓到（F01 第一次沒抓到，改測試後抓到） |
| `packaging/validate.py`（CI 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（離線暫存 venv：`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt` 雜湊安裝） | `Ran 201`、`OK (skipped=5)` |
| `scripts/tool_inventory.py` | exit 0（沒動 `apps/runtime/*.py`、`apps/*/launch.py`） |
| 獨立腳本 | 長字串的單次 C 呼叫（`SP:hm30fix/bench/long_string_c_calls.py`）、請求端成本（審查的 `request_side_cost.py`，數字和審查一致） |
| 全套 pytest | 沒重跑：審查修正只改兩個測試檔、`reply_worker.py` 的說明文字與文件；`reply_worker.py` 只改說明字串與註解（去掉說明字串後兩版的 AST 相同），兩個測試檔與相關 35 檔都跑過 |
| `git status` | 乾淨；每個 `/tmp/ha-mp-*` 都已用完整路徑刪除（`SP:hm30fix/tmpdirs.txt`） |

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
審查修正後：`test_reply_worker.py` 86 案 22.5 秒、`test_health_tolerance.py` 2 案 17.4 秒；審查加的 12 案合計約 3 秒（emoji 慢讀 2.1 秒最長）。CI 推估：本片合計多約 45～65 秒，仍在每片 1.5 分鐘內。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base dbf3c8c --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；`dbf3c8c..HEAD` 的 7 個 commit＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base dbf3c8c` | `runtime-patches.json` 174 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的列管檔 6 個（`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`reply_worker.py`（新）、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔：**OK** |

審查修正後重跑（HEAD `e84bd8f`；之後只加本筆記）：

| 預檢 | 結果 |
|---|---|
| 秘密預檢（同上指令） | gitleaks 8.28.0（釘版、已驗）；`dbf3c8c..e84bd8f` 10 個 commit＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢（同上指令） | 174／70／159 筆 0 漂移、0 缺；改到的 6 個列管檔都有帳本更新（`reply_worker.py` 照實際內容重算）；沒有沒列管的新執行檔：**OK** |

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
| A 的回覆還在進來時（迴圈以 64 KiB 一段讀；工作執行緒同時在處理先到的回覆） | — | — | 51.6、49.2、51.9 ms；獨立腳本 34～56 ms；審查 50.9、59.0、48.8、48.5、57.7 ms；審查修正後重跑 49.8、58.8、60.6、52.0 ms（pytest 4 次） | **未定（D3，第 14 節）** |
| B 的 tools/call p50／p99 | 53／4,466 ms | 64／4,534 ms | 295／397、307／419、316／357 ms；獨立腳本 p99 381～440 ms | p99 ≤2d＋0.2＝700 ms |
| B、C 的健康檢查 | 沒有逾時，但在該做之後最晚 4,409／4,403 ms 才做完（各 15 次） | — | 0 次逾時、判定一直 reachable；在該做之後最晚 32／35、31／50 ms 做完（f2、f3，各 85 次） | 0 次逾時 |
| 每帳號同時處理 | — | 1 | 1 | ≤1 |

- 注入的單次 C 呼叫在啟動時校準（目標 10 ms）：三次 pytest 量到 9.9、6.8、5.7 ms（機器忙時校準偏短，仍比 GIL 的 5 ms 切換間隔長）；
  總成本以執行緒 CPU 時間計，每次都付滿（5.1～5.2 秒）。最短 5.7 ms 的那一輪，B1～B3 三個喘息的突變照樣抓到（第 4.2 節）。
- 開工前本機沒有逾時（4.4 秒 < 8＋5 秒的時限），但檢查晚了 4.4 秒；目標硬體慢數倍時就會逾時（C2 的 `cross_profile_probe_sim`）。
  所以測試的門檻是「該做之後 d 內做完」，比逾時嚴得多。
- f1 的健康檢查是改量法之前的版本（只量檢查本身：最慢 24 ms），不列。
- 讀取期間那一列原本寫「（不算）」，等於沒經同意就放寬（審查 MF-3），已改成待決（D3）。審查 X5 拆原因：注入成本設 0 時同一段 34.6 ms，
  有成本時 57.7 ms；審查修正後重跑 X5：注入成本 0 時 50.6～52.9 ms、有成本時 36.5～61.6 ms，兩者重疊；按時間點拆開（暫存區實驗 `SP:hm30fix/scratch-tests/test_zz_hm30fix_reading_stops.py`，4 次），沒有注入成本時最長的停頓都在 A 的 32 個請求同時開始的頭 0.1 秒（36.8、51.9 ms），之後 ≤28 ms；有成本時頭 0.1 秒 33.0～49.0 ms、和處理重疊的中段最長 33.3～40.5 ms。

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

審查 4 次：mixed 形狀 43.3、43.5、47.2、48.9 ms（一次 `json.dumps` 46～49 ms）；審查修正後重跑 42.2、44.6、50.4、48.0 ms（一次 `json.dumps` 45.6～50.9 ms；pytest 4 次）。

單一長字串的回覆（審查 X8；本片另用獨立腳本 `SP:hm30fix/bench/long_string_c_calls.py` 重量，7 次的最小／中位數／最大）：

| 回覆的文字 | 閘道輸出的大小 | 一次 `json.dumps`（審查） | 一次 `json.dumps`（本片） | `json.loads` 掃一個 8 MiB 字串（審查／本片） |
|---|---|---|---|---|
| ASCII | 8.00 MiB（1 倍） | 32～34 ms | 27.1／28.2／28.7 ms | 21 ms／21.6～23.5 ms |
| CJK | 16.00 MiB（2 倍） | 43～45 ms | 32.0／32.4／33.4 ms | 17 ms／17.9～18.9 ms |
| emoji | 24.00 MiB（3 倍） | 66～69 ms | 45.9／47.3／48.2 ms | 20 ms／18.8～20.5 ms |

數字看機器多忙；結論一樣：emoji 在本機就到 50 ms 邊上或超過，目標硬體約 4 倍一定超過；解析端掃長字串也是一次 C 呼叫（目標硬體 70～85 ms）。

**目標硬體上做不到契約的 ≤50 ms**（本機 42～45 ms，剛好在邊上；一次 `json.dumps` 就 45～66 ms，J6412／J1900 慢數倍）。原型（`SP:hm30/bench/pieces.py`，沒有進 repo）：
序列化分段（大的 list、dict 逐個元素用 C 編碼器、再接起來；輸出位元組逐位元相同）時迴圈最長停 15 ms，處理時間 1.8 倍；大量小物件的形狀
仍有 62 ms，來自工作執行緒配置大量物件時觸發的全代 GC。原型只拆大的 list、dict，拆不了單一長字串（審查 MF-3 第 2 點）。交使用者決定（第 14 節 D1）。

### 11.4 慢讀與一次湧入（`test_a_slow_reader_holds_no_more_than_its_pending_reply_budget`；湧入是臨時探針 `SP:hm30/probes/`）

| 情境（B 的用戶端都不讀；真 listener、h11） | 帳上（待送回覆） | 位元組額度（請求端） | 管理程序 RSS 增量 | 門檻 |
|---|---|---|---|---|
| 依序 2 個 JSON＋2 個 SSE 回覆各 8 MiB，SSE 的請求各帶 4 MiB 參數；之後 B 的 tools/call 立刻 200＋`-32003`、預設帳號與 C 照常 | 32.0 MiB | 8.0 MiB（兩條開著的 SSE 的轉送內容） | 121 MiB（審查 121～124 MiB；審查修正後 116～120 MiB） | ≤296 MiB：達到 |
| emoji（審查 S-1）：依序 1 個 JSON＋1 個 SSE 回覆各 8 MiB emoji（閘道跳脫後各約 24 MiB），SSE 的請求帶 4 MiB emoji 參數（UTF-8 送，轉送 12 MiB）；兩個就過 32 MiB，之後同上 | 48.0 MiB（額度 32 MiB 加上達到前已交出的那一則） | 12.0 MiB（一條開著的 SSE：4 MiB 參數跳脫成 12 MiB） | 116 MiB（pytest 4 次） | ≤296 MiB：達到 |
| 一次湧入：額外帳號同時 16 個 8 MiB（它的轉送名額） | 128 MiB | — | 276 MiB | 在 296 以內，但幾乎貼著 |
| 一次湧入：預設帳號同時 32 個 8 MiB（只有 28 個在達到上限前轉送出去） | 224 MiB | — | 469 MiB | **超過 296**：軟上限的代價（第 14 節） |
| 一次湧入（審查 X2）：預設帳號同時 8 個 8 MiB emoji | 192 MiB | — | 267 MiB | 在 296 以內 |
| 一次湧入（審查 X2）：預設帳號同時 32 個 8 MiB emoji（19 個在達到上限前轉送出去）；審查修正後重跑 20 個轉送、帳上 480 MiB、RSS 增量 657 MiB | 456 MiB | — | 632 MiB | **超過 296**（2.1 倍）；理論上限約 32＋32×24≈800 MiB（第 14 節 D2） |

loopback 上每條連線核心先吃掉約 4 MiB（`SO_SNDBUF` 自動長到 4 MiB），剩下的才留在程序裡；帳上算的是整個回覆（`Response` 一直持有它）。

### 11.5 待 HM-19c 量測的門檻（契約第 5、6 節；都還是暫定）

rebase 與 D1～D3 之後的數字在第 16.7、16.8 節；本表的「本片的結果」欄已照它們改。

| 門檻 | 本片的結果 | HM-19c 要量的 |
|---|---|---|
| 迴圈單次停頓 ≤50 ms（可控注入） | rebase 前：處理期間 11.1～28.0 ms、讀取期間 48.5～60.6 ms。D3 定 (a) 之後量整段：34.4～45.9 ms（pytest 6 次）（第 16.8 節） | J6412（可以的話 J1900）同情境，量整段（D3） |
| 迴圈單次停頓 ≤50 ms（真實 8 MiB 回覆，D1） | 七種形狀與兩種事件 7.3～46.3 ms（pytest 4 輪）（第 16.7 節） | 真實回覆的停頓：mixed、CJK、emoji 三種一定要量，另量大量小物件、長字串、跳脫字元、100 層加 emoji 的巢狀；過不了回報、考慮子程序（D1） |
| B 的 tools/call p99 ≤2d＋0.2 秒（單元）；HAOS 上 p95 增量 ≤1 秒 | rebase 前 0.31～0.44 秒；rebase 與 D1、D3 之後 0.29～0.31 秒（第 16.8 節） | HAOS 上的 p95 增量 |
| B、C 健康檢查 0 次逾時（8＋5 秒） | 0 | HAOS 上同情境 |
| 慢讀 RSS ≤296 MiB | ASCII 121 MiB；emoji 116 MiB（pytest 4 次）；rebase 與 D1 之後 ASCII 96～116 MiB、emoji 76～112 MiB（pytest 2 次） | 目標硬體的 RSS 與 MemAvailable（ASCII、CJK、emoji）；一次湧入的 RSS（D2 定 (a) 接受；用非 ASCII 的值） |
| 待送回覆 32 MiB（每帳號） | 照契約；一次湧入的最壞值預設帳號約 800 MiB、額外帳號約 416 MiB（D2，契約第 5 節） | 對 MemAvailable 比對全域最壞值時一起看，每個帳號算進「轉送名額×跳脫後最多 24 MiB」（D2） |
| 喘息參數（5 ms／2 ms／10 ms） | 本機量的；D3 沒改 | J6412／J1900 上 B 的延遲與工作執行緒的吞吐（A 的回覆要多久做完；D1 的分段讓大量小物件的一筆多花約 2.7～2.9 倍時間，第 16.7 節） |
| 請求端的迴圈停頓（審查 S-5；結構守門那部分是 HM-31 審查 S-3；本片範圍外） | 審查 X4：一個 16 MiB 請求 0.36～1.9 秒；HM-31 合併後重量 0.09～0.25 秒（第 16.8 節） | 目標硬體上請求的結構守門、解析與重新序列化的停頓 |
| SSE 通知多的串流（審查 S-6） | 每個事件都在迴圈讀一次 state | 目標硬體上通知多的 POST 串流對迴圈與 B 的延遲的影響；量到問題再改成需要時才讀 |
| 真 socket 分段寫出（審查 S-7） | CPU 飢餓測試用程序內的 ASGI client | 真機上 64 KiB 一段的 `send` 在工作執行緒忙時的成本 |

## 12. 驗收條件（計畫 §12.3 HM-30）

| 條件 | 結果 |
|---|---|
| 輸出位元組不變 | 通過：同一個 `make_apps` 兩條路逐案對照（JSON 24、SSE 14×2、GET 1）全部相同；HM-01 黃金回歸與兩個契約凍結開關開與關都照過、斷言沒改 |
| CPU 飢餓測試達契約門檻 | 通過（第 11.1 節：處理期間的停頓、B 的 p99、健康檢查、每帳號 1 筆）。D3 定 (a) 之後量整段：34.4～45.9 ms（pytest 6 次），通過（第 16.8 節）。D1 定 (a) 之後真實 8 MiB 回覆（七種形狀與兩種事件）7.3～46.3 ms（pytest 4 輪），通過（第 16.7 節）。目標硬體由 HM-19c 量 |
| 慢讀測試達契約門檻 | 依序慢讀通過（第 11.4 節）；一次湧入時預設帳號超過（軟上限），回報（第 14 節）；使用者定 D2 (a) 接受並寫進文件（第 16.9 節） |
| 開關關時完全照今天 | 通過（第 3.6 節；D1、D3 也只在開通的產品，第 16.7、16.8 節） |
| 獨立安全審查 | 做了：修正後通過；必修 3 項都處理、建議 7 項處理或寫明理由（第 15 節）。D1～D3 使用者已定（第 16 節）。D1、D3 的程式（`reply_worker.py`、`gateway.py`、`redact.py`、`access.py`）是審查之後加的，沒有審查過（第 16.14 節） |
| 同 PR 更新帳本；契約「暫定」細節同步並在變更紀錄加一列 | 通過（第 8 節；契約第 6 節「HM-30 定案」與量測、第 9 節 #17 附註、第 10 節一列）。rebase 與 D1～D3：帳本重算（第 16.5 節）、契約第 2.4、5、6 節與 #17、變更紀錄一列（第 16.9 節） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空集合；commit 沒有 AI 署名 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過 |

## 13. 前面的片交給 HM-30 的事項，與交給後面的片

### 13.1 前面的片交給 HM-30 的事項（逐條 grep `docs/provenance/ha-multiprofile-HM-*.md`）

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-08 第 14.2 節 | 待送回覆位元組額度（C1-M5「預設帳號當攻擊方＋大回覆」那一半） | 做了：第 3.5 節；預設帳號也是 32 MiB（`DEFAULT_PROFILE_QUOTA.pending_reply_bytes`），`pending_reply()` 對每個帳號的 gate 都有效。原本只測了額外帳號；預設帳號的測試是審查 MF-2 補的（第 15 節） |
| HM-08 第 14.2 節 | 回覆工作執行緒 | 做了：第 3.1～3.3 節 |
| HM-08 第 14.2 節、HM-08 審查報告第 9 節 | 「慢讀 RSS」的量測要含 SSE 串流期間的轉送內容（位元組額度扣到請求結束）；HM-19c 量測放「SSE 期間的轉送內容」與「非 ASCII 內容 3 倍」 | 慢讀測試做了：四個 8 MiB 回覆裡兩個是 SSE、請求各帶 4 MiB 的參數，斷言串流開著時該帳號的位元組額度仍扣著轉送內容（≥8 MiB）、RSS 增量含它（第 11.4 節）。非 ASCII 的 3 倍：原本以「屬請求端」轉給 HM-19c，理由不對（回覆端的 `json.dumps` 也放大，帳上記的就是放大後的大小；審查 S-1）。已做：慢讀測試加 emoji 一案（回覆 emoji、SSE 的請求參數也是 emoji，第 11.4 節）；目標硬體的記憶體量測仍交 HM-19c |
| HM-09 第 3.10 節第 13 點、第 13.2 節 | 「連兩次失敗」的規則 HM-09 已做；HM-30 留 CPU 飢餓下的整合測試 `tests/test_health_tolerance.py` | 做了：疊在 HM-09 的規則上（第 11.1 節）；`health.py` 沒改 |
| HM-06 第 12.3 節（審查 S-07） | 子程式回 401 時健康監看只看到 `MCP_SERVER_NOT_READY`，要不要加專屬原因碼，由 HM-09／HM-30 決定 | HM-09 已決定不加（它的筆記第 13.1 節：只有閘道自己的 child bearer 會送到子程式，401 代表設定錯，`backend/test` 與 diagnostics 看得到）。本片沒動健康探測，沿用、不加 |
| HM-00 第 10 節 | 回覆排程的停頓門檻 ≤50 ms 可能做不到：用真實 8 MiB 回覆量，做不到就回報使用者再定，不自行放寬 | 量了：mixed 形狀本機 42～50 ms、單一長字串（emoji）一次 `json.dumps` 46～69 ms，目標硬體一定做不到（第 11.3 節）；回報使用者（第 14 節 D1，審查 MF-3 補了長字串），門檻沒改 |
| HM-01 第 1 節 | HM-04～HM-30 每一片都要照過黃金回歸與契約凍結 | 照過：開關關與開兩種都跑（第 5 節），斷言沒改 |
| HM-05 第 443 行（合併順序） | `profile_runtime.py` 照 HM-05 → HM-08 → HM-09 → HM-13b → HM-30 → HM-25 | 本片疊在 HM-09 上；HM-13b 還沒合併，rebase 時照順序重產帳本（第 13.2 節） |

其他各片（HM-02、HM-04、HM-07、HM-13a、HM-17）的筆記沒有交給 HM-30 的事項。

### 13.2 交給後面的片與主對話

2026-11-16 rebase 之後，本節各點的現況寫在每點的最後；rebase 之後才有的交辦在第 16.14 節。

- **rebase**（主對話）：`gateway.py` 照 HM-10 → HM-14 → HM-30 合併；`profile_runtime.py` 照 HM-09 → HM-13b → HM-30；`run_product.py` 照
  HM-09 → HM-13b → HM-30。rebase 後一律重算帳本（`runtime-patches.json` 的 6 列，含新的 `reply_worker.py`）、重跑兩個預檢與 CI；契約第 2.4、5、6、10 節和 HM-10、HM-14
  可能改的地方相鄰。本分支沒有 #100（checks 上限 60 分鐘、`decisions.md` 的 DQ-13／14／30／31／43），rebase 時一起進來。
  現況：做了（第 16 節；HM-31 也在新基準裡，順序照交辦的 HM-10 → HM-14 → HM-31 → HM-30、HM-09 → HM-10 → HM-31 → HM-30）。HM-13b 還沒合併，
  它之後 rebase 的那一片照順序處理 `profile_runtime.py`、`run_product.py`。
- **HM-09 介面若小改**：本片用到 HM-09 的地方集中在兩處：`HealthMonitor.check()`／`availability()`（`tests/test_health_tolerance.py`）與
  `ProfileManager.add()` 建 `ProfileRuntime` 的那一行（`reply_worker=` 參數）；`multi_profile_runtime` 的 `Runtime.task`／`may_stop` 是新加的。
- **HM-14**：排隊上限與通知保留名額放在轉送名額那裡；本片的待送回覆檢查在轉送名額**之前**（`serve()` 的 `PENDING_REPLIES`），rebase 時要維持
  在排隊之前（被擋的 tools/call 不該先排隊再被擋）。`-32003` 文字定稿時一起看 `profile_router.pending_text()`。開關關時子程式 initialize 錯誤
  沒遮罩（HM-08 審查 S-4）仍是 HM-14 的事；本片的 initialize 回覆照舊在迴圈內處理。現況：HM-14 已合併；rebase 後待送回覆檢查在 HM-14 的
  `if lanes is None:` 之前，`pending_text()` 照 HM-14 定稿的寫法補說明、文字不變（第 16.2 節）。
- **HM-19c**：在 J6412（可以的話 J1900）重量契約第 6 節：B 的 tools/call p95 增量 ≤1 秒、健康檢查 0 次逾時；也量真實回覆（第 11.3 節的
  mixed 形狀、大量小物件、CJK 與 emoji 的長字串）的迴圈停頓、讀取期間的停頓（D3）與一次湧入時的 RSS（第 11.4 節，用非 ASCII 的值），對
  MemAvailable 比對；另量請求端的迴圈停頓（審查 S-5）、通知多的 SSE 串流（S-6）、真 socket 分段寫出的成本（S-7），見第 11.5 節。
  現況：D1～D3 定案後的量測清單在第 16.14 節。
- **HM-18**：文件寫明待送回覆額度是軟上限、工作執行緒停了 add-on 會重啟、真實大回覆仍會讓迴圈停一次 C 呼叫那麼久；請求端的 CPU 仍在
  迴圈裡（威脅模型第 3 節，審查 S-5）。現況：D2 定案後要寫的句子在第 16.14 節。
- **HM-31**（審查 S-5）：驗收加「請求的解析與重新序列化在迴圈內的停頓」：PaaS #155 的元素上限下約 0.1～0.15 秒；契約第 6 節與威脅模型
  第 3 節的那一條，HM-31 做完後改寫。現況：HM-31 已合併；本片在它之上重量（0.09～0.25 秒，第 16.8 節）、改寫了那兩處，超過 50 ms 的部分交主對話（第 16.14 節）。
- **使用者**：D1～D3（第 14 節），合併前要有答案。現況：2026-11-16 14:0x 都選 (a)（`decisions.md` 第 1.1 節），本片做了（第 16.7～16.9 節）。
- **獨立安全審查**（計畫 §12.0 第 9 點；本片標「審查」）：已做，報告在 `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-30.md`；
  處理見第 15 節。

## 14. 待使用者決定（照契約第 6 節回報，門檻都沒放寬；數字以審查報告第 2、3 節為準）

**已定（2026-11-16 14:0x，`decisions.md` 第 1.1 節）**：D1、D2、D3 都選 (a)，都照建議。做法與結果在第 16.7～16.9 節；下面保留回報時的內容。

獨立審查（MF-3）指出原本這一節數字偏低、也漏了一項。下面是更正後的三題（D1～D3），合併前要有使用者的答案。

1. **D1 真實大回覆的迴圈停頓**：一筆 8 MiB 回覆裡拆不開的單一 C 呼叫，迴圈就停那麼久。
   - C2 的 mixed 形狀：工作執行緒 42～45 ms（作者 3 次）、43.3～48.9 ms（審查 4 次）、42.2～50.4 ms（本片重跑 4 次）；一次 `json.dumps`
     45.6～50.9 ms。沒有解析器檢查點時 52～82 ms。
   - 單一長字串的回覆（審查 X8）：一次 `json.dumps` emoji 66～69 ms、CJK 43～45 ms、ASCII 32～34 ms。本片重量（獨立腳本
     `SP:hm30fix/bench/long_string_c_calls.py`，7 次取中位數）：emoji 47 ms、CJK 32 ms、ASCII 28 ms。數字看機器多忙，結論一樣：
     emoji 在本機就到 50 ms 邊上或超過；CJK 是這個產品線很常見的回覆內容（Odoo 中文欄位、Nextcloud 檔案）。
   - 解析端也有拆不開的一次 C 呼叫：`json.loads` 掃一個 8 MiB 字串 17～21 ms（審查）、18～23 ms（本片），目標硬體約 4 倍就是 70～85 ms。
   - 選項：
     - (a) 序列化分段：大的 list、dict 逐元素用 C 編碼器再接起來（原型 15 ms、輸出逐位元相同、處理時間約 1.8 倍）。**還要另外把長字串切段
       編碼**（原型拆不了單一長字串）。解析端掃長字串的那一次 C 呼叫仍在，所以 (a) 單獨可能到不了 J1900 上的 50 ms。大量小物件另有 GC 的
       停頓（62 ms），可能還要 `gc.freeze()` 或分段配置。
     - (b) 改用子程序處理回覆（沒有 GIL 共用；新的子程序生命週期、IPC 複製、記憶體另算）。
     - (c) 接受，HM-19c 以 HAOS 上「B 的 p95 增量 ≤1 秒、健康檢查 0 次逾時」為發版門檻（單次停頓門檻改成只對可控注入）。這等於放寬，要使用者同意。
   - 建議：(a)（含長字串切段）；HM-19c 在 J1900 上量 mixed、CJK、emoji 三種，過不了再考慮 (b)。
2. **D2 待送回覆額度是軟上限**：已轉送的回覆一律交出（照順序讀回覆的用戶端才不會卡死），所以一次湧入時帳號最多持有「上限＋轉送名額個回覆」；
   而且扣的是跳脫後的大小（CJK 約 2 倍、emoji 約 3 倍）。
   - 預設帳號一次湧入 32 個不讀的 8 MiB 回覆：ASCII 帳上 224 MiB、RSS 增量 469 MiB；emoji（審查 X2）19 個在達到上限前轉送出去、帳上
     456 MiB、RSS 增量 632 MiB（契約 296 MiB 的 2.1 倍）。理論上限約 32 MiB＋32（轉送名額）×24 MiB≈800 MiB。
   - 選項：(a) 接受並寫進文件（今天沒開通時是 64 條連線各一個、跳脫後最多 24 MiB 的回覆，還更大）；(b) 轉送前另外用「轉送中的 tools/call
     數 × 估計值」預扣（會讓大量小回覆的並行也被擋）；(c) 降低預設帳號的轉送名額（32 → 16）；(d) 工作執行緒在帳號超過上限時暫停處理它的回覆
     （照順序讀的用戶端會卡到逾時：不建議）。
   - 建議：(a)（審查同意）。HM-19c 對 MemAvailable 比對全域最壞值時，把「轉送名額 × 單一回應跳脫後最多 24 MiB」算進去，用非 ASCII 的值。
3. **D3 讀取期間的停頓算不算進門檻（審查新列）**：契約第 6 節的情境是「A 並行 16 個 8 MiB 與 16 個 2 MiB 回覆時」，沒有排除回覆還在進來的
   那一段；正式環境裡讀取與處理一定重疊。原本契約寫「不算進門檻」，等於沒經同意就放寬，已改成「未定、待使用者決定」。
   - 讀取與處理重疊時迴圈的最長停頓：作者 51.6／49.2／51.9 ms；審查 50.9／59.0／48.8／48.5／57.7 ms（8 次裡 5 次超過 50 ms）；
     本片重跑 49.8、58.8、60.6、52.0 ms（pytest 4 次）。
   - 審查 X5 拆原因（各一次）：注入成本設 0 時同一段 34.6 ms（迴圈自己以 64 KiB 一段讀、每段約三次 `store.load` 的租約檢查、測試裡程序內的
     假子程式）；有成本時 57.7 ms，推論多出的 15～24 ms 是和工作執行緒的 GIL convoy。
   - 本片重跑 X5 四次，結論不同：注入成本 0 時 50.6～52.9 ms、有成本時 36.5～61.6 ms，兩者重疊；按時間點拆開（暫存區實驗 `SP:hm30fix/scratch-tests/test_zz_hm30fix_reading_stops.py`，4 次），沒有注入成本時最長的停頓都在 A 的 32 個請求同時開始的頭 0.1 秒（36.8、51.9 ms），之後 ≤28 ms；有成本時頭 0.1 秒 33.0～49.0 ms、和處理重疊的中段最長 33.3～40.5 ms。所以讀取期間超過 50 ms 的，主要是 32 個請求同時進來時迴圈自己的工作（准入、授權、轉送；請求端，
     審查 S-5、HM-31 的範圍），加上測試裡程序內的假子程式；和工作執行緒重疊的那段最長約 33～41 ms。
   - 選項：(a) 算進門檻：測試改量整段（現在會紅），要再調喘息參數、減少每段的租約檢查，或把測試裡假子程式的成本另外扣掉再比；照上一點，
     主要的那一塊在請求端，(a) 也要看 HM-31 之後的數字；(b) 不算，但契約寫明「只量處理期間」並經使用者同意。
   - 建議：(a)（審查同意）：正式環境沒有「只處理、不讀取」的時段；HM-19c 的「B 的 p95 ≤1 秒、健康檢查 0 次逾時」才是發版門檻，可以一起看。
   - 測試目前只印出這一段、不斷言；`test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace` 與 `tests/reply_load.py`
     的說明已改成「待使用者決定」，不再寫「不算進門檻」。

## 15. 獨立安全審查與意見處理（2026-11-16）

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-30.md`（repo 外；審查 `5b6d4a5`，證據 `wave4/evidence-review-HM-30/`）。
  判定「修正後通過」：程式本身沒有找到安全漏洞；必修 3 項、建議 7 項、待使用者決定 3 項（D1～D3）。
- 先核對審查：MF-1 的競態在 HEAD 上重現（同一個測試 200 次 20 次失敗，審查是 32 次）；審查存活的 7 個突變用審查自己的改法重跑，
  另加 4 個，新測試都抓到（第 4.3 節）；長字串的單次 C 呼叫、請求端成本（X4）、emoji 湧入（X2）都重量過，數字和審查一致或在同一級
  （第 11 節、契約第 6 節）。審查的必修與建議都成立，只有兩處要補充：(1) emoji 長文字一次 `json.dumps` 本片重量 46～48 ms（審查
  66～69 ms），看機器多忙，結論一樣（第 14 節 D1）；(2) D3 讀取期間的停頓，審查推論多出的部分是 GIL convoy；本片重跑 X5 四次、
  再按時間點拆開，超過 50 ms 的主要是 32 個請求同時進來時迴圈自己的工作，不是工作執行緒（第 14 節 D3）。
- 修正的 commit：`503fb3d` 測試（MF-1、MF-2、S-1～S-4、S-7，與驗證時找到的另一個競態）；`6e073c3` `reply_worker.py` 兩處說明與帳本；`e84bd8f` 契約、威脅模型、驗收表；最後一個是本筆記。

| 編號 | 意見 | 處理 | 證據 |
|---|---|---|---|
| MF-1（必修） | `test_a_worker_whose_thread_ended_answers_every_job_at_once` 在 `ended` 一設好就斷言 `not worker.alive`，是測試的競態（`_end()` 用 `call_soon_threadsafe` 設 `ended`，那時執行緒還沒返回） | 已修：先 `await until(lambda: not worker.alive, 5)` 再斷言 `failure`；`ReplyWorker` 的說明改成「`ended` 在執行緒正在結束時設，`alive` 稍後才變 False、`stop()` 會等」 | 同一個測試 200 次：HEAD 20 失敗／180 通過；修正後 200 次全過；驗證時找到的另一個競態（`test_a_worker_that_stops_by_itself…`，本表最後一列）修正後 50 次全過（兩個一起 250 案 12.8 秒） |
| MF-2（必修） | 預設帳號的待送回覆額度沒有測試（C1-M5「預設帳號當攻擊方」）；拿掉預設帳號的檢查（M15）140 案全過 | 已補：`test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call` 參數化成預設帳號與額外帳號兩案（審查 X1 的情境；斷言 200＋`-32003`、`Retry-After: 5`、`Cache-Control: no-store`、沒轉送、tools/list 照轉、另兩個帳號照常、WARNING 一行、讀完歸 0、再轉送） | M15：新案紅（第 4.3 節）；HEAD 綠 |
| MF-3（必修） | 待使用者決定的內容不完整、數字偏低：讀取期間寫成「不算進門檻」（等於自行放寬）；「真實回覆剛好在邊上」只對 mixed 形狀成立；湧入只量 ASCII | 已改，程式與門檻都不改：契約第 6 節三列（讀取期間改「未定、待使用者決定（D3）」；真實回覆補長字串 CJK／emoji 與 (a) 的限制；湧入補 emoji）；本筆記第 14 節改成 D1～D3；測試與 `tests/reply_load.py` 的說明不再寫「不算進門檻」 | 第 14 節；契約第 6 節 |
| S-1 | HM-08 審查交辦的「慢讀 RSS 放非 ASCII 內容」被轉給 HM-19c，理由「屬請求端」不對 | 已做：慢讀測試參數化 ascii、emoji。emoji 案：1 個 JSON＋1 個 SSE 回覆各 8 MiB emoji（各扣約 24 MiB），SSE 的請求帶 4 MiB emoji 參數（UTF-8 送，轉送 12 MiB）；兩個就過 32 MiB，下一個 tools/call 立刻 `-32003`；帳上的位元組逐位元照閘道自己的序列化算 | 本機：帳上 48.0 MiB、位元組額度 12.0 MiB、RSS 增量 116 MiB（pytest 4 次；門檻 296 MiB），約 2.1 秒；第 13.1 節那一列已改 |
| S-2 | 兩個契約寫明的順序沒有測試：待送檢查在拿轉送名額之前（M16）；回覆格式錯（502）先於 state 讀不到（503）（M22） | 已補兩個測試：(1) B 的 16 個轉送名額被 16 個 ping 占住（子程式扣著）、B 也已超額 → 下一個 tools/call 1 秒內拿到待送回覆的文字，不是名額的文字；(2) 只讓「回覆處理讀 state」的那幾個函式讀不到（token 檢查照常），三種情況兩條路結果相同：不是這個請求的回覆 502、這個請求的回覆 503、SSE 先轉 list_changed 再在回覆處結束 | M16、M22：新測試紅 |
| S-3 | token 換了時排隊中的回覆工作要撤回，沒有測試（M19） | 已補：審查 X3 併進測試（預設帳號的回覆占住工作執行緒、B 的排在後面、換 B 的 token → B 3 秒內 401、B 的工作沒跑、預設帳號照常 200） | M19：新測試紅 |
| S-4 | 喘息的兩個細節沒有確定性的測試（M28、M29） | 已補兩個計數型測試：(1) 檢查點的睡眠序列（`time` 換成只記錄的替身）：跑滿切片後先睡 `BREATH_SECONDS`，迴圈忙時再以 `YIELD_STEP_SECONDS` 讓到 `YIELD_SECONDS`，迴圈閒時只睡一次，切片內不睡；(2) 解析器每建一個 JSON 物件就呼叫一次檢查點（JSON 與 SSE 各一案：300 筆紀錄的回覆至少 300＋2 次），迴圈內那條路一次都沒有 | M28、M29（另加 M27）：新測試紅 |
| S-5 | 請求端的解析與重新序列化仍在迴圈裡，I8 的 CPU 飢餓保證只對回覆成立，文件沒寫 | 已寫明：契約第 6 節「HM-30 定案」一條、威脅模型第 3 節一條；交 HM-19c 量請求端的迴圈停頓、HM-31 的驗收加這一項（第 13.2 節） | 審查 X4；PaaS `d7f5849` `docs/mcp-gateway-limits.md`（元素上限下約 0.1～0.15 秒） |
| S-6 | POST SSE 串流的每個事件都在迴圈讀 state 與每個帳號的憑證，連會被略過的通知也讀 | **留到之後**，理由：不是安全問題（審查也這樣判）；要省掉這些讀取，做法是工作執行緒先解析分類、是回覆才回迴圈讀 state 再交第二步，這樣每個回覆事件要在工作執行緒排兩次班，別的帳號最多要等 A 的兩筆，契約「B 的 p99 ≤2d＋0.2 秒」更難達到；改在迴圈上先分類，又得在迴圈上解析，正是本片要避免的。實際的 POST 串流通常只有幾則通知加一則回覆。已寫進契約第 6 節，交 HM-19c 在目標硬體量通知多的串流，量到問題再改 | 契約第 6 節 |
| S-7 (1) | 「工作執行緒在 listener 服務前啟動」沒有測試（M25） | 已補：`test_the_worker_starts_before_the_listeners_serve_and_stops_once_they_stopped`（啟動時兩個 listener 都還沒服務；停的時候兩個 listener 的 `serve()` 都已結束） | M25 與本片自加的 F01（listener 停之前就停工作執行緒）：新測試紅 |
| S-7 (2) | `ReplyWorker.handed` 的說明寫「給面板診斷用」，實際只有測試用 | 已改說明 | — |
| S-7 (3) | 64 KiB 分段之後，讀得慢的用戶端讓請求一直到收完才結束，自己帳號的准入與位元組額度扣得比之前久 | 已寫明：契約第 5 節 | — |
| S-7 (4) | CPU 飢餓測試用程序內的 ASGI client，沒測到真 socket 分段寫出的成本 | 交 HM-19c 在真機量（第 11.5 節） | — |
| D1～D3 | 待使用者決定 | 第 14 節；PR 說明列出；合併前要有答案 | — |
| 審查第 7 節的觀察 | `_done` 之後、`_deliver` 之前若出現非 `RuntimeError` 的例外（例如 `MemoryError`），那一筆等不到結果；同一個例外也讓執行緒停止、add-on 結束重啟 | 接受，不改（審查也判可接受：只在記憶體耗盡時發生） | — |
| 驗證時另外找到（不在審查裡） | 既有的 `test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits` 第一次跑就紅了一次：第一個回覆在送到用戶端前被 add-on 停機截斷（`ClientDisconnect`）。測試用的是程序內的 ASGI client，繞過 listener，停機時沒有東西等它；正式環境的 uvicorn 會等進行中的回應送完（`run_product` 給 listener 5 秒） | 已修（只改測試）：讓執行緒等第一個回覆送到用戶端之後才停；說明寫明原因。斷言沒有放寬：第一個 200、排隊的 502、add-on 結束都照舊 | 修正後同一個測試 50 次全過；突變 M04（排隊的不結束）、M26（不看 `ended`）照樣讓它紅（第 4.3 節） |

審查第 8 節「前面各片交給 HM-30 的待辦」核對：除了 HM-08 審查第 9 節那一項（S-1，已做），其他都和第 13.1 節一致；第 13.1 節的兩列已照實更新。

## 16. rebase 到 claude-delivery 與 D1～D3（2026-11-16）

第 1～15 節照 rebase 前寫，裡面的 commit 編號是 rebase 前的（對照在第 16.13 節）。數字以本節為準。

### 16.0 結論

- **rebase 做完**：基準換成 `claude-delivery` `df686dd`。本片 11 個 commit 照原順序重放，6 個有衝突，兩邊的意圖都留（第 16.2 節）。
  - 順序照交辦：`gateway.py` HM-10 → HM-14 → HM-31 → HM-30；`profile_runtime.py` HM-09 → HM-10 → HM-31 → HM-30。
  - 待送回覆檢查放在 HM-14 的排隊**之前**（既有的 S-2 測試守這個順序）。
  - HM-31 重寫了 `ProfileGate.serve`，本片的計數改疊在它上面，有一行不是文字衝突、但一定要改（第 16.2 節）。
  - 帳本以新基準為底重算（第 16.5 節）。
- **D1 做了（分段轉換）**：工作執行緒那條路分段序列化，長字串也切段，和 `json.dumps` 一次做完逐位元相同（第 16.7 節）。
  - 七種形狀的真實 8 MiB 回覆（JSON 七案、SSE 兩案），工作執行緒那條路的迴圈單次停頓本機 7.3～46.3 ms（pytest 單獨 3 次加整檔 1 次，
    門檻 50 ms）；最高的是跳脫字元多的長字串（解析端那一次 C 呼叫），離門檻約 4 ms。
  - D1 之前同一組測試：9 案裡 6 案超過 50 ms（紅：大量小物件 125.9、巢狀 72.8、emoji 事件 60.6、長 ASCII 字串 55.7、emoji 52.8、
    mixed 50.5 ms）。
- **D3 做了（讀取期間也算）**：CPU 飢餓測試改量整段（第 16.8 節）。門檻沒放寬，喘息參數沒動。
  - 改之前（rebase 後）貼著門檻：前一段一次整檔跑 60.9 ms（紅）；後一段同一組 6 次都在門檻內（38.5～47.4 ms）。紅不穩定。
  - 找到兩處、都改了：測試工具的錯（A 的健康檢查拿到 8 MiB 的填充回覆、在迴圈上解析），與讀取期間每段 3 次的 token 檢查
    （開通時改成每段 1 次）。後者讓讀取期間從約 3 秒縮到約 1.3 秒；前者在 pytest 量不出差別，是讓測試照實的修正。
  - 改完：整段最長 34.4～45.9 ms（pytest 單獨 6 次）、整檔 41.1 ms。剩下最長的停頓多半在 A 的 32 個請求同時開始那一下，
    注入成本設 0 也有（38.1、50.5 ms），不是工作執行緒造成的。**餘裕只有約 4 ms**，CI 與目標硬體可能超過（第 16.14 節）。
- **D2 做了（接受並寫進文件）**：契約第 5、6 節寫明軟上限與一次湧入的最壞值（ASCII、emoji 兩組實測，理論上限預設帳號 800 MiB、
  額外帳號 416 MiB）；威脅模型第 3 節加一條；交 HM-18、HM-19c 的事在第 16.14 節。
- **`decisions.md`** 第 1.1 節補 4 列：13:4x HM-09 追補全部產品都修（#106）；14:0x D1、D2、D3（第 16.10 節）。
- **本機檢查都過**（第 16.11 節）：全套 6,110 案只有 7 個要 root 的既有案例紅、0 skip；`validate.py`、packaging unittest、工具表面、
  兩個預檢都過；突變 8 個都抓到。
- **這一階段分兩段做**：前一段做到 `85324e8`（rebase、D1／D3 的測試與程式、帳本）就中斷了，沒有跑驗證，文件也沒寫完。後一段接著做：
  逐項核對前一段的改動、補兩個測試（D1：每種串流在工作執行緒切框；D3：磁碟上換 token）與兩處說明（第 16.7、16.8 節）、
  跑全部檢查、寫完文件。
- **還沒解決、交主對話**（第 16.14 節）：請求端一個大請求本機仍讓迴圈停 0.09～0.25 秒，不在契約第 6 節的情境裡，本片沒改。

### 16.1 範圍與做法

- 先開本機備份分支 `backup/hm30-before-rebase-20261116`（＝`8b015d5`，不 push）。`git fetch origin` 後 `origin/claude-delivery`＝`df686dd`。
- `dbf3c8c` 不是 `claude-delivery` 的祖先（HM-09 rebase 前的修正 head）。`git log --oneline dbf3c8c..feat/ha-multiprofile-hm30-20261116`
  只有本片 11 個 commit，所以用 `git rebase --onto origin/claude-delivery dbf3c8c feat/ha-multiprofile-hm30-20261116`。
- 新基準和本片 11 個 commit 重疊的檔：`gateway.py`、`profile_router.py`、`profile_runtime.py`、`tests/multi_profile_runtime.py`、契約、
  威脅模型、驗收表、`ledger-tracking.md`、帳本。D3 改的 `access.py` 是 rebase 之後才改的，疊在新基準 HM-14 改過的版本上。
- `config.py`、`run_product.py`、`redact.py` 在 `dbf3c8c` 與新基準之間沒變，所以 `run_product.py` 照 HM-09 → HM-10 → HM-31 → HM-30
  的順序也沒有衝突。
- 依賴（`uv.lock`、`package-lock.json`）沒變，沒有重跑 `setup_repo_env.sh`。
- 解衝突與核對的腳本與紀錄都在 repo 外（`SP:hm30r/bin/`、`SP:hm30r/logs/rebase-log.md`；HM-31 rebase 的 `merge_ledger.py`、`compare.py` 照用）。
- PaaS（本機唯讀 repo，沒有 fetch、沒有 checkout）：`origin/main` 現在是 `7087280`。`d7f5849` 之後只多 #135（EMQX）、#139（LiteLLM）
  不保留閒置連線與 #138（Hermes cron 的 paused），`packages/mcp-admin-core/` 與 `docs/mcp-gateway-limits.md` 都沒動，對本片沒影響。

### 16.2 衝突與處理

| rebase 後（原本） | 衝突 | 處理 |
|---|---|---|
| `15bc2a3`（`092b827`） | `tests/multi_profile_runtime.py` 的簽名與說明 | HM-10 的 `verifier` 在前、本片的 `may_stop` 在後；說明兩句都留 |
| `e83889d`（`8a2703e`） | `profile_runtime.py` 七處 | 模組說明：HM-10、HM-31 兩段之後接本片那段。`RUNTIME_OPTIONS`、`ProfileRuntime` 的參數與 `gateway_options`：HM-10 的 `default_endpoint`、`bootstrap_fields`、HM-31 的 `body_budget` 之後加 `reply_worker`。`ProfileRuntime` 說明：HM-10 那段之後接本片那段。`ProfileManager` 說明：用新基準 HM-10 改寫過的那段，之後接本片那段。`add()`：HM-10、HM-31 的參數之後加 `reply_worker=…lane(profile_id)` |
| 同上 | `gateway.py` 六處 | 常數：新基準的全留（HM-31 的 `BODY_RESERVATION`、HM-14 的 `SlotBusy`、`Lane`、`take_slot` 等）；HM-08 的 `FORWARDED_BODY`（HM-31 拿掉了）不加回；`PENDING_REPLIES` 放在 `BODY_RESERVATION` 後面。`make_apps` 簽名：`body_budget` 之後接 `reply_worker`。說明：HM-14、HM-10、HM-31 三段之後接本片那段。參數檢查：HM-09、HM-10、HM-31 的之後接本片的。`serve()`：待送回覆檢查放在 HM-14 的 `if lanes is None:` **之前**（被擋的 tools/call 不先排隊）；本片原本那段 HM-08 的 `slots.acquire`＋`slot_busy(message)` 不加回（HM-14 取代了）。JSON 回覆：HM-14 的 `interrupted_answer` 在前，再來是迴圈內那條路與工作執行緒那條路（自動合併）。SSE：自動合併（本片的 `relayed_event`、HM-14 的 `reply_event`／`answered` 都在） |
| `c2c764d`（`73d6cfd`） | `profile_router.py` 六處 | HM-31 重寫了 `ProfileGate.serve`（位元組預算改在帳號 app 扣，沒有 `counted_receive`、`forwarding`、`refuse`、拒絕小額度）。本片只留自己的：`reply_bytes`、`pending_reply`、`counted_send`／`hand_over`、把 `PENDING_REPLIES` 放進請求 state 的副本、`finally` 還 `held`；HM-14 的回呼與 HM-31 的 `budget_share` 都留。**不是文字衝突、但一定要改**：HM-31 把那一行改成 `await app(scope, receive, send)`，diff3 取了它；本片改成 `await app(scope, receive, counted_send)`，否則待送回覆額度完全不扣（突變 M-R1 證實：改回去之後待送回覆的測試紅，第 16.6 節）。`beyond_admission`（HM-31 審查 MF-2 (b)）不動：它只服務不帶請求的 POST，閘道回 202、沒有本體。`pending_text` 補說明（照 HM-14 定稿的 `-32003` 文字寫法），文字不變 |
| `307f998`（`2552106`） | 契約、威脅模型、帳本 | 契約第 5 節：新基準 HM-31 改寫的各段都留，本片的「HM-30 補：軟上限」接在 HM-31 的全域最壞記憶體例子後面；第 2.4、5、6 節本片的其他改動自動合併；變更紀錄：新基準的列在前、本片的在後。威脅模型：狀態行與 I8 測試欄都是新基準的文字加本片那句。帳本：第 16.5 節 |
| `4382ac8`（`5b6d4a5`） | 契約三處 | 第 9 節說明段：新基準各行照原文，另加一行「#17 的附註出自 HM-30 的實作」。#15、#16 用新基準（HM-31 改寫）的，#17 用本片加附註的。變更紀錄：新基準的列、本片那列 |
| `d5f2e03`（`e84bd8f`） | 契約一處、威脅模型三處 | 契約第 5 節：新基準的文字＋本片審查 S-7 那段（「位元組額度」改成 HM-31 的「請求內容位元組預算的份額」）。威脅模型：新基準的文字＋本片審查的三處插入；第 3 節的請求端 CPU 一條放在 HM-31 的結構守門 CPU 一條後面（D3 時再改寫，第 16.8 節） |
| 其他 4 個 | 沒有衝突 | `b6a2c85`、`2dc496e`、`bcd0628`（測試）、`22409db`（`reply_worker.py` 說明與帳本） |

### 16.3 rebase 剛做完時的核對

- `git range-diff dbf3c8c..8b015d5 origin/claude-delivery..dfd0766`：5 個完全相同、5 個有改（上表），`73d6cfd` 改得多到 range-diff 當成另一個
  commit（`profile_router.py` 疊在 HM-31 重寫的 `serve` 上）。
- `compare.py`（逐檔比兩個 diff 的增刪行；`SP:hm30r/logs/compare-*.txt`）：本片的改動在 `config.py`、`reply_worker.py`、`run_product.py` 與
  4 個測試檔逐行相同，其他檔只差第 16.2 節那幾處；反方向，新基準的程式（HM-09、HM-10、HM-14、HM-31、#106）一行都沒少。
- 帳本預檢（還沒加新 commit 時）：`runtime-patches.json` 176、`runtime-sources.json` 70、`tool-surface.json` 159 檔，0 漂移、0 缺，OK。

### 16.4 契約第 9 節的列號

- 本片在第 9 節**沒有自己的列**：本片的差異都寫在 #17 的附註裡（rebase 前就是這樣）。`claude-delivery` 最後是第 108 列，不用接、不用重編，
  D1～D3 也只補 #17 的附註（它們都是「回覆處理」這一列的做法，PaaS 沒有對應的機制）。
- 本片引用的列號在新基準都沒動，舊 commit 訊息裡的「contract 9 #17」照原文：

| 本片寫的 | 新基準 | 內容 |
|---|---|---|
| #15、#16 | #15、#16（HM-31 改寫了內容） | 名額、讀 body 前拒絕的回應碼 |
| #17 | #17（本片的附註照留，D1～D3 各補一句） | 回覆處理 |
| #18 | #18 | 健康檢查 |
| 第 89 列（HM-09 審查 S-6） | 第 89 列 | 試綁被平台擋 |

- 第 9 節說明段改成新基準的一片一行。變更紀錄加一列（「HM-30 rebase 與 D1～D3」）。

### 16.5 帳本（`docs/provenance/runtime-patches.json`）

- 重放 `2552106` 時以當下 HEAD 的帳本為底（HM-31 的 `merge_ledger.py`：先確認底的帳本能逐位元重現；原 commit 只在列尾追加，把那段接到
  底的文字後面；新列照原位置；SHA-256 照當下的檔重算；`SP:hm30r/logs/ledger-2552106.txt`）。`reply_worker.py` 是新列，放在
  `profile_runtime.py` 後面。
- `85324e8`：rebase 的說明（`gateway.py`、`profile_router.py`）、D1（`gateway.py`、`reply_worker.py`）、D3（`gateway.py`、`access.py`）各接一段。
- `5f61a94`：`access.py` 那句 D3 說明改成精確的寫法（本分支自己的、還沒合併的文字，第 16.8 節），`access.py`、`gateway.py` 重算。
- `9f1facc`：`reply_worker.py` 的兩處量測數字照 pytest 改（只改註解與說明字串），重算。
- SHA-256（前 12 碼）：

| 列管檔 | `claude-delivery` `df686dd` | rebase 前 `8b015d5` | `85324e8` | 現在（`5f61a94`、`9f1facc` 之後） |
|---|---|---|---|---|
| `gateway.py` | `1f954cf11cde` | `8c378a028908` | `a5699b344fb0` | `077f024fdaae` |
| `profile_router.py` | `bb6b6feb79f3` | `2f6b7e9e0483` | `76bcc814f3dc` | 同左 |
| `profile_runtime.py` | `048e73896820` | `324d0aa27afe` | `60f27add408c` | 同左 |
| `reply_worker.py`（新列） | — | `d156c6d0657d` | `4743482fb64b` | `2ccdc2c37127` |
| `run_product.py` | `59d281b17549` | `78d511c9b82e` | `78d511c9b82e` | 同左 |
| `config.py` | `78a2f79d76fd` | `c42173d17815` | `c42173d17815` | 同左 |
| `access.py` | `5d78bcea515e` | （本片沒改） | `b1bd935dd60d` | `0a830599e82d` |

- `redact.py` 本來就沒列管（`ledger-tracking.md`）。D1 加了 `checkpoint` 參數，帳本預檢照預期把它列成「沒列管、要人看」（同 #106 的
  `health.py`），結果 OK。

### 16.6 rebase 後的測試配合

| commit | 改了什麼 | 為什麼 |
|---|---|---|
| `a4c42a5` | 待送回覆額度與慢讀的 4 處 `gate.body_bytes` 改成 `body_bytes(gate)`（帳號在全 add-on 請求內容預算的份額） | HM-31 拿掉了 HM-08 的每帳號計數；斷言的數值不變 |
| `52926ae` | HM-31 的 `test_make_apps_takes_only_a_share_of_a_budget_beside_hm09s_and_hm10s_options` 比 `make_apps` 最後 5 個參數 | 本片的 `reply_worker` 接在 HM-31 的 `body_budget` 後面；原本比最後 4 個（rebase 後第一次跑紅，`SP:hm30r/s1/f-related.log`） |

`test_a_profile_past_its_pending_reply_budget_is_answered_before_it_waits_for_a_slot`（審查 S-2）在 rebase 後照過。

兩個合併點用突變確認（`SP:hm30r2/bin/mutate_order.py`，在 `cb93e08` 的複本跑；每個只跑該抓住它的測試）：

| # | 突變 | 抓住它的測試 | 結果 |
|---|---|---|---|
| M-R1 | 帳號 app 改回 HM-31 那一行的 `send`（diff3 取的那行） | `test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call[additional-profile]` | 抓到（一直等不到 `-32003`、逾時；1 failed in 11.07s） |
| M-R2 | 待送回覆檢查移到 HM-14 的排隊之後 | `test_a_profile_past_its_pending_reply_budget_is_answered_before_it_waits_for_a_slot` | 抓到（先排隊、等滿名額的 1 秒才回答；1 failed in 2.19s） |

### 16.7 D1：分段轉換

**做法**（`reply_worker.py`、`gateway.py`、`redact.py`；只在工作執行緒那條路，沒開通的產品一行不變）：

| 原本一次 C 呼叫（或一段不喘息的 Python） | 現在 |
|---|---|
| `json.dumps` 整個值（mixed 45～50 ms、大量小物件 0.1 秒以上、emoji 長字串 46～69 ms） | `reply_worker.encoded`：一次後序走訪（`_plan`，不遞迴）算出每個 list／dict 最多編成幾個位元組（字串每個碼位以最長的跳脫 12 位元組算，數字 24，大整數照位數），超過 `PIECE_BYTES`（64 KiB）的才拆：成員照順序分段，每段一次 json 的 C 編碼器；長字串一次 `STRING_PIECE`（8,192）個碼位；呼叫之間有檢查點。json.dumps 自己會轉換的值（非字串鍵、tuple、子類別）照它一次做 |
| 全代回收（工作執行緒配置大量物件時觸發，一次走過整個 add-on 的物件：59～75 ms） | 處理一筆工作時 `gc.disable()`，工作結束一律恢復（例外也是；本來就關著的不動）。回覆沒有參照循環，答完就放掉 |
| 一次放掉解析出的值與遮罩後的值（大量小物件各 15～35 ms） | 編碼完 `released()`：大的容器一段段清空（只放掉參照），解析出的值同形狀的容器一起清；`filter_list` 重建過工具清單的回覆不分段放（裡面有政策自己的 schema：`releasable`） |
| `redact_secrets` 走過整個回覆（Python、不喘息：迴圈每次系統呼叫都要再等 GIL） | `redact_secrets(…, checkpoint)`：每個 list／dict 一次、長字串的每個秘密之間一次；`_plan` 每個容器一次 |
| 大的 SSE 事件在迴圈上切框（複製、`LONE_CR`、`split`、`sse_data`、組成事件：8 MiB 一次 35～50 ms） | 大於 `WORKER_FRAME_BYTES`（64 KiB）的事件整個交給工作執行緒（`relayed_frame`：迴圈原本那幾步、同樣順序）；回覆事件在 `encoded` 裡一次組成 |
| 解析前 `bytes(raw)`（8 MiB 一次複製約 10 ms） | 工作執行緒直接解析 bytearray（`json.loads` 兩種都收，結果與錯誤都相同） |

**還是一次 C 呼叫的**：`json.loads` 掃一個長字串（8 MiB：ASCII 約 20 ms、跳脫字元多的 25～46 ms）、bytes 解碼成 str（5～20 ms）、
最後把各段接起來（一次複製）。D1 的定案接受解析端這一次（「過不了再考慮子程序」），交 HM-19c 在 J1900 量。

**核對（後一段做的）**：

- 逐位元相同的理由：json 的字串跳脫一次只看一個碼位（astral 碼位寫成一對 `\uXXXX`，單獨代理字元寫成自己的 `\uXXXX`），所以長字串切開
  接回位元組相同；list／dict 的一段是「同一個 C 編碼器編同一批成員」再去掉括號、段與段之間補逗號；`_encode` 就是 `json.dumps(…,
  separators=(",", ":"))` 用的同一個 `JSONEncoder.encode`。`_plan` 的成本只決定在哪裡切，不影響位元組。
- `released()` 只放掉參照：外面還拿著的物件不動；解析出的值和遮罩後的值鍵的順序不同時，對不上的 twin 就不清（只是放得慢），不會錯。
- 回收器關著會不會讓循環垃圾一直收不掉（暫存區實驗 `SP:hm30r2/exp/gc_starve.py`：4 個帳號接連交工作、每筆約 40 ms 配置 15 萬個
  物件，迴圈同時每 1 ms 做 100 個互相參照的物件，每次 15 秒，關著、不關各 3 次）：關著時回收照樣在工作之間跑（第 0 代 125～127 次、
  第 1 代 11 次、第 2 代 1 次），還活著的循環物件最多 2,018～2,132 個，沒有一直長；不關時第 0 代 36,230～38,481 次、最多 114 個。
  工作做完的筆數：關著 813～855、不關 531～564。迴圈最長停頓（後兩次量）：關著 14.8、18.7 ms，不關 13.8、38.5 ms。

**測試**（`773014a`、`dd1098f` 先寫；實作 `086159f`）：

- `test_in_pieces_the_bytes_are_json_dumps_own`［4 組分段大小］：隨機值 300 個（ASCII、控制字元、引號與反斜線、Latin-1、U+2028、CJK、U+FFFD、
  單獨代理字元、astral、很長的整數、各種浮點數、巢狀、長鍵）加邊界值；分段大小調到 1～16，每個值在能切的地方都被切到，和 `json.dumps`
  逐位元相同；json.dumps 自己轉換的值照它的轉法。
- `test_long_strings_and_large_values_go_out_between_checkpoints`：長字串一次最多 `STRING_PIECE` 個碼位、大的 list／dict 一段最多
  `PIECE_BYTES`、呼叫之間有檢查點；小值一次 C 呼叫。
- `test_a_real_8_mib_reply_is_the_loops_bytes_and_stops_the_loop_briefly`［9 案］：七種形狀（C2 的 mixed、大量小物件、CJK、emoji、單一長
  ASCII 字串、跳脫字元、64 層的巢狀樹）的 JSON 回覆，加 mixed、emoji 的 SSE 事件。子程式以 64 KiB 一段送，直接經 ASGI 收：迴圈內處理
  與工作執行緒處理的回應逐位元相同，工作執行緒那條路的迴圈單次停頓 ≤50 ms，印出分佈。
- `test_a_job_runs_with_the_cyclic_collector_held_off`、`test_a_large_value_is_let_go_of_in_pieces_and_nothing_it_does_not_own_is_touched`、
  `test_a_large_tool_list_is_relayed_the_same_twice_on_the_worker`。
- 既有的逐位元對照（JSON 24 案、SSE 14×2 案、GET 1 案）照過。
- `test_an_event_framed_on_the_worker_is_byte_for_byte_what_the_loop_answered`［28 案，後一段補的，`cb93e08`］：前一段只有兩個真實
  8 MiB 事件（一行 data）走到工作執行緒切框那條路，其他框（註解、id／event／retry、priming、略過的通知與請求、別的 id、batch、壞的
  JSON、兩個都有、單獨的 CR、多行 data、帶秘密的工具清單、截斷）只在迴圈上切框的那條路測過。這一案把 `WORKER_FRAME_BYTES` 設成 0，
  14 種串流×整段與 7 位元組一段都走工作執行緒切框：回應和迴圈內處理逐位元相同，切過的框一樣多、都在工作執行緒上。

**先紅後綠**（pytest；紅＝`6601e9b`：D1、D3 的測試都在、核心還沒改；綠＝`cb93e08`）：

| 案例 | D1 之前（`6601e9b`） | D1 之後（`cb93e08`） |
|---|---|---|
| 逐位元 4 組、長字串與大值分段 | 紅（5 案）：`encoded` 不存在 | 綠 |
| 回收器關著 | 紅：工作期間回收器開著 | 綠 |
| 分段放掉、工具清單不分段放 | 紅（2 案）：`released` 不存在 | 綠 |
| 真實 8 MiB 回覆（工作執行緒那條路的迴圈最長停頓） | 9 案裡 6 案紅：大量小物件 125.9、巢狀 72.8、emoji 事件 60.6、長 ASCII 字串 55.7、emoji 52.8、mixed 50.5 ms；在門檻內的 3 案：mixed 事件 49.5、跳脫字元 39.4、CJK 39.2 ms | 9 案全綠（下表） |

同一輪（`-k` 選 D1、D3 的新測試，20 案）：16 紅、4 綠。綠的 4 案是 D3 沒開通那一案（釘住今天的每段 3 次）與上表在門檻內的 3 案。

**本機最大值與分佈**（綠，每次一個 pytest 程序、3 次；迴圈延遲探針每 2 ms 取樣；單位 ms）：

| 形狀 | 迴圈內處理：迴圈最長停頓 | 工作執行緒：最長停頓（3 次） | 工作執行緒：p99 | 一筆的時間：工作執行緒（D1 之前） |
|---|---|---|---|---|
| mixed | 258～266 | 25.1、30.0、32.1 | 5.6～11.6 | 656～672 ms（401 ms） |
| 大量小物件 | 886～895 | 16.5、19.6、44.1 | 5.5～5.7 | 3,301～3,523 ms（1,214 ms） |
| CJK | 70～92 | 14.2、20.3、21.4 | 14.2～21.4 | 130～145 ms（157 ms） |
| emoji | 86～116 | 10.7、14.0、19.0 | 10.7～19.0 | 143～150 ms（169 ms） |
| 長 ASCII 字串 | 65～71 | 13.7、17.4、28.4 | 13.7～28.4 | 95～125 ms（160 ms） |
| 跳脫字元 | 60～63 | 23.3、30.3、45.5 | 23.3～45.5 | 100～123 ms（134 ms） |
| 64 層巢狀 | 585～622 | 7.3、7.6、8.4 | 5.4～5.5 | 1,469～1,592 ms（773 ms） |
| mixed（事件） | 293～316 | 16.7、25.8、29.0 | 5.5～8.2 | 757～777 ms（520 ms） |
| emoji（事件） | 140～156 | 11.7、31.3、40.6 | 11.7～40.6 | 256～273 ms（326 ms） |

- 本片的檔整檔跑一次（`g1`）：同一組最長 8.6～46.3 ms，最高也是跳脫字元（46.3 ms）。四輪合計 7.3～46.3 ms，都在 50 ms 內。
- p50 約 5 ms 的是要切很多段的形狀：迴圈要等工作執行緒跑完一個 5 ms 的切片（`SLICE_SECONDS`）才拿回 GIL，照設計。
- 最高的停頓都是解析端拆不開的那一次 C 呼叫：跳脫字元多的長字串 `json.loads` 一次掃完（本機最高約 46 ms），離門檻只剩約 4 ms。
- 處理時間：大量小物件約 2.7～2.9 倍、巢狀約 2 倍、mixed 約 1.7 倍（分段編碼、分段放掉與喘息）；長字串的幾種不變或更快（不再整段複製）。

巢狀語料是 64 層（結構守門允許請求的最深）、中文註記（`dd1098f`）。100 層加 emoji 的版本另外量過（前一段的獨立腳本：解碼成 UCS-4 的
字串一次就約 20 ms，加上放掉整棵樹 31～65 ms），交 HM-19c 一起看。

**突變**（各改 `5f61a94` 的一處，在暫存區的複本跑該抓住它的測試；`SP:hm30r2/bin/mutate.py`）：

| # | 突變（`cb93e08` 的複本） | 抓住它的測試 | 結果 |
|---|---|---|---|
| M-D1a | 處理工作時不關回收器 | `test_a_job_runs_with_the_cyclic_collector_held_off` | 抓到（工作裡回收器開著；1 failed in 1.11s） |
| M-D1b | 長字串的切段迴圈壞掉（步長改成整個字串長，只交出第一段） | `test_long_strings_and_large_values_go_out_between_checkpoints` | 抓到（位元組不同；1 failed in 0.95s） |
| M-D1c | 重建過的工具清單也分段放掉 | `test_a_large_tool_list_is_relayed_the_same_twice_on_the_worker` | 抓到（`released` 被呼叫；1 failed in 1.03s） |
| M-D1d | 工作執行緒切框時丟掉事件的其他行（`id:` 等） | `test_an_event_framed_on_the_worker_is_byte_for_byte_what_the_loop_answered[priming-comments-fields-whole]` | 抓到（位元組不同；1 failed in 1.03s） |

### 16.8 D3：讀取期間也算

**測試改量整段**（`360efd0`）：`test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace` 斷言
`max(讀取期間, 處理期間) ≤ 50 ms`，兩段都印分佈；`tests/reply_load.py` 的 `Starved` 說明改寫。

**原因與處理**：

1. **測試工具的錯**（`6481f7f`）：A 的假子程式（`LargeChild`）以 JSON-RPC id 判斷要不要回大回覆。預設帳號健康檢查的 tools/call 用 id 3，
   正好是 A 的請求 id 之一，所以 A 的每次健康檢查都拿到 8 MiB 的填充回覆，在迴圈上讀進來並解析（`health.protocol_reply`）。真的
   子程式對健康檢查回的是小回覆（`products.health_probe`：Odoo、Nextcloud 是私有的認證探針，其他是小的公開讀取）。改成只對 A 的工具
   （`search_records`）回大回覆；A 的 32 個請求、160 MiB、注入成本與門檻都不變。前一段的獨立腳本量到它是讀取期間最長停頓的主因；
   後一段用 pytest 拆（下表）量不出差別，所以只當成「讓測試照實」的修正。
2. **讀取期間的 token 檢查**（`6601e9b` 測試、`ebc15a2` 實作）：讀取期間迴圈的 CPU 大半在 `store.load`（前一段用 cProfile 量：9,215 次、
   累計 3.1 秒）。子程式的回覆以 64 KiB 一段讀，每段 3 次（開始前、watcher 立刻一次、結束後）。開通的產品改成每段 1 次
   （`TokenLease.run(checked=True)`）；沒開通照舊。讀取期間從約 3 秒縮到約 1.3 秒，B 的 p99 也降一些。
3. 喘息參數（5 ms／2 ms／10 ms）沒改，門檻沒放寬。
4. **剩下的**：最長的停頓多半落在 A 的 32 個請求同時開始那一下（第 0.03 秒），四種設定都一樣，連注入成本設 0（工作執行緒幾乎不搶
   GIL）也有。那一下是測試裡用戶端、閘道與假子程式都在同一個迴圈上處理 32 個請求；正式環境裡用戶端與子程式不在 add-on 的迴圈上。
   要再壓低，得動請求端（每個請求的 `store.load`、授權、HM-31 的守門、轉送）或改測試的用戶端，都不是小改動，本片沒做（第 16.14 節）。

**後一段的核對與修正**（`179a080`、`5f61a94`）：

- `checked` 的說明原本寫「呼叫者剛查過、之後沒有 await」，不成立：上一段的檢查之後，`run` 的 finally 會等 watcher 結束，閘道也會把那一段
  交給用戶端或工作執行緒。安全性靠的是另外兩件事，說明改成照實寫：透過管理 API 換 token 會設租約的 event，watcher 立刻醒；其他改變
  （state 損壞或被換掉）由操作結束後的那次檢查擋下。所以換了之後讀到的東西都不會交出。只改說明（去掉說明字串後兩版 AST 相同）。
- 補測試：`test_a_lease_checked_just_before_runs_without_reading_the_state_again_first` 加一段，`checked=True` 的操作裡在磁碟上換掉
  token（不經管理 API、沒有 event）→ `AccessChanged`，操作讀到的沒有交回。

**改前改後**（pytest，每次一個程序；整段＝讀取期間與處理期間的最大值。後一段在改之前跑的 6 次都沒紅，紅的只有前一段那一次，見表末）：

| 版本（pytest，每次一個程序） | 跑法 | 整段最長（ms） | 讀取期間的取樣數 | B 的 p99（ms） |
|---|---|---|---|---|
| `52926ae`：量整段；測試工具沒修；每段 3 次檢查 | 單獨 5 次 | 38.5、39.1、41.3、43.9、47.4 | 202～225 | 313～434 |
| 同上 | 兩檔整檔 1 次 | 39.3 | 197 | 331 |
| `6601e9b`：測試工具修了；每段 3 次檢查 | 單獨 3 次 | 37.0、46.0、47.8 | 198～217 | 385～397 |
| `cb93e08`：兩個都改（最後的程式） | 單獨 6 次 | 34.4、35.7、37.1、37.8、43.9、45.9 | 114～131 | 288～308 |
| 同上 | 本片 4 檔整檔 1 次（`g1`） | 41.1 | 122 | 304 |
| 前一段（`360efd0`＝`52926ae` 的測試、少 HM-31 一個測試的配合） | 本片整檔 1 次（`SP:hm30r/s1/a-red-slice.log`） | **60.9（紅）** | 206 | 418 |

拆解（暫存區實驗 `test_zz_d3_whole_scratch.py`，在 `cb93e08` 的複本跑同一個情境，把修正各關回一個；各 3 次；`SP:hm30r2/sb/`）：

| 設定 | 整段最長（ms） | 讀取期間 | 最長停頓落在 | B 的 p99（ms） |
|---|---|---|---|---|
| 兩個都改 | 34.5、36.2、38.3 | 1.24～1.45 秒 | 0.03 秒（兩次）、1.42 秒 | 289～312 |
| 租約改回每段 3 次 | 35.8、39.8、45.0 | 2.87～3.03 秒 | 0.03 秒（兩次）、0.69 秒 | 312～385 |
| 測試工具改回（健康檢查拿 8 MiB） | 37.6、38.5、38.6 | 1.23～1.37 秒 | 0.03 秒（三次） | 292～296 |
| 兩個都改回 | 37.9、38.3、44.2 | 2.88～3.10 秒 | 0.03、0.91、2.46 秒 | 333～383 |
| 兩個都改、注入成本 0 | 38.1、50.5 | 0.83～0.88 秒 | 0.03、0.35 秒 | 80～142 |

- 單看最長停頓，四種設定差不多（34.5～45.0 ms）；租約檢查的修正讓讀取期間短一半、B 的 p99 低一些。
- 注入成本 0 時一次到 50.5 ms（在第 0.35 秒），工作執行緒那時幾乎沒在搶 GIL：這一段的停頓來自迴圈自己的工作。

**突變**：

| # | 突變（`cb93e08` 的複本） | 抓住它的測試 | 結果 |
|---|---|---|---|
| M-D3a | `checked` 的操作連結束後的檢查也跳過 | `test_a_lease_checked_just_before_runs_without_reading_the_state_again_first` | 抓到（state 讀取次數；1 failed in 0.98s） |
| M-D3b | 開通時每段照舊查 3 次（不帶 `checked`） | `test_a_switched_on_reply_is_read_with_one_state_read_a_piece[switched-on]` | 抓到（846 次讀取／272 段；1 failed in 1.09s） |

**請求端一起量**（HM-30 審查 S-5 交給 HM-31 的「請求的解析與重新序列化在迴圈內的停頓」；結構守門那部分是 HM-31 審查 S-3。交辦寫成
「HM-31 審查 S-5」，但那一項是 MemAvailable 重複計算，這裡照內容量）。一個請求、沒有別的負載、開關關的 `make_apps`，HM-31 的結構守門與
預算都在（暫存區實驗 `test_zz_request_side_scratch.py`，在複本裡跑、沒有進 repo；每種 2 次）：

| 請求 | 迴圈最長停頓（2 次） | 結構守門 | `strict_json` | 前一段量的（同一個實驗） |
|---|---|---|---|---|
| 16 MiB ASCII 字串 | 157、160 ms | 18～19 ms | 46～47 ms | 150～170 ms |
| 16 MiB 中文字串 | 134、190 ms | 30～44 ms | 37～55 ms | 139～140 ms |
| 16 MiB emoji 字串 | 216、222 ms | 45～46 ms | 55～57 ms | 150～157 ms |
| 19.9 萬個浮點數（0.9 MiB） | 91、124 ms | 2 ms | 56～73 ms | 88～89 ms |
| 99,990 個 `{"a":1}`（1 MiB） | 183、245 ms | 129～132 ms（慢路徑） | 31～96 ms | 212～216 ms |
| 同上再補到 16 MiB | 0 ms（宣告超過 16 MiB，讀之前就 413） | — | — | — |

其餘是單獨代理字元的檢查（`json.dumps(ensure_ascii=False)` 一份）與轉送前的重新序列化（`json.dumps`）。

HM-31 把審查 X4 的 0.36～1.9 秒壓到 0.09～0.25 秒，但都還超過 50 ms。這不在契約第 6 節的情境裡（D3 的整段量測裡 A 的請求都是小請求）。
要把請求端也交給工作執行緒是另一件事（守門、解析、授權與重新序列化都要搬，回應要逐位元相同），本片沒做，交主對話（第 16.14 節）。

### 16.9 D2：寫進文件

- 契約第 5 節「HM-30 補」之後加「一次湧入的最壞值」：帳上扣的是跳脫後的大小，一個帳號最多持有「待送上限 32 MiB＋轉送名額×跳脫後最多
  24 MiB」，預設帳號 800 MiB、額外帳號 416 MiB（理論上限）；本機實測 ASCII 與 emoji 兩組；HM-19c 用非 ASCII 的數字。
- 契約第 6 節：使用者定案一段（D1～D3）；「慢讀用戶端」補一句（296 MiB 是依序慢讀的門檻，一次湧入的最壞值由使用者接受）；量測表的
  「一次湧入」列改成「使用者接受（D2 (a)）」；第 2.4 節的列補「軟上限，最壞值見第 5 節」。
- 威脅模型：第 3 節加一條（一個 token 持有人最多可以讓管理程序多用的記憶體）；I8 的測試欄寫明跳脫後最多 24 MiB。
- 交 HM-18 的 DOCS 句子、HM-19c 的量測清單：第 16.14 節。

### 16.10 `decisions.md`

第 1.1 節（2026-11-16 07:1x PaaS #155 那一列所在的表）補 4 列，標題補「HM-30 補」，變更紀錄加一列；DQ 的題數不變：

| 日期 | 題目 | 結論（選項、理由） | 負責片 |
|---|---|---|---|
| 13:4x | HM-09 追補：監看的取消被 HTTP 堆疊吞掉 | 全部產品都修（不受開關管）；只改關閉 | HM-09 追補（#106） |
| 14:0x | D1 真實大回覆的迴圈停頓 | (a) 分段轉換；(b) 子程序成本高、(c) 等於放寬；HM-19c 在 J1900 量三種內容，過不了再考慮 (b) | HM-30、HM-19c |
| 14:0x | D2 待送回覆額度是軟上限 | (a) 接受並寫進文件；(d) 扣住回覆會卡死照順序讀的用戶端、(b)(c) 擋到正常並行；HM-19c 用非 ASCII 的數字並算進轉送名額×24 MiB | HM-30、HM-18、HM-19c |
| 14:0x | D3 讀取期間的停頓算不算 | (a) 也算；正式環境沒有只處理的時段；HM-19c 超標就回功能片改；請求端一起量 | HM-30、HM-19c |

### 16.11 本機檢查（2026-11-16，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪除；pytest 都排在共用鎖後面）

pytest 都在 repo 外的複本跑（`git archive` 該 commit 的樹，`.venv`、`apps/`、`packages/mcp-admin-ui` 連回 clone；`SP:hm30r2/bin/snap.sh`），
只有全套在 clone 裡跑。每次 pytest 一個程序，排在共用鎖後面（`SP:hm30r2/bin/sessionA.sh`、`sessionB.sh`、`sessionC.sh`）。

| 檢查 | 範圍 | 結果 |
|---|---|---|
| 先紅：D1、D3 的新測試（`6601e9b`：測試都在、核心還沒 D1／D3） | `test_reply_worker.py -k "<D1、D3 的新測試>"`，20 案 | 16 紅、4 綠（第 16.7 節）；紅的原因都是缺函式、缺參數、停頓超過 50 ms 或讀 state 太多次 |
| 改前：D3 整段（`52926ae`） | CPU 飢餓一案單獨 5 次；兩檔整檔 1 次 | 都綠（38.5～47.4 ms；整檔 39.3 ms），整檔那次的 10 紅是 D1 的新測試（核心還沒 D1）。前一段同一組測試整檔 60.9 ms 紅（第 16.8 節） |
| 中間：只修測試工具（`6601e9b`） | CPU 飢餓一案單獨 3 次 | 都綠（37.0～47.8 ms） |
| 綠：本片的檔＋HM-31 的 `test_request_budget_gateway.py`（`cb93e08`） | `test_reply_worker.py`、`test_health_tolerance.py`、`test_profile_runtime.py`、`test_request_budget_gateway.py` | **237 案全過**、0 skip，68.2 秒（`test_reply_worker.py` 133 案 33.7 秒、`test_health_tolerance.py` 2 案 16.1 秒） |
| 綠：D3 整段 | CPU 飢餓一案單獨 6 次 | 都綠：34.4～45.9 ms（第 16.8 節） |
| 綠：D1 真實 8 MiB 回覆 | 9 案 × 3 次 | 27 案全過：7.3～45.5 ms（第 16.7 節） |
| 拆解 D3（暫存區實驗） | 5 種設定 × 2～3 次 | 第 16.8 節 |
| 相關的檔 | HM-31 的預算與結構（`test_request_budget.py`、`test_request_structure.py`、`test_n8n_request_bounds.py`）；HM-14 的 5 檔（`test_carries_no_request.py`、`test_gateway_queue_ha.py`、`test_gateway_stream_endings.py`、`test_gateway_busy_shapes.py`、`test_initialize_generation.py`）＋`test_reply_mask_union.py`；HM-10 的 3 檔（`test_profile_admin_api.py`、`test_admin_pipeline_matrix.py`、`test_router_passthrough.py`）；`test_monitor_cancel.py`；HM-01 黃金回歸與兩個契約凍結（開關關時逐位元；`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`）；另 11 檔用到改過的程式路徑的（額度、路由、生命週期、健康、租約、遮罩、後端錯誤、錯開啟動、port、子程式資源、HM-20 的 loopback） | 927 案：**925 過**、2 紅（HM-31 的 206 案、HM-14 的 5 檔＋遮罩 144 案、HM-10 的 86 案、`test_monitor_cancel.py` 13 案、HM-01 的 45 案都過；0 skip）。紅的 2 案是 HM-20 的 `test_backend_loopback.py::test_a_switched_on_product_s_child_gets_the_variable_and_nothing_else_changes[n8n/documentation]`、`[n8n/configured]`：複本的 `apps/` 是連回 clone 的連結，n8n 子程式的路徑解析成 clone 的路徑，和快照比對的正規化對不上；全套在 clone 裡跑時這 2 案過（下面全套那列） |
| 突變 8 個 | 第 16.6～16.8 節 | 8 個都抓到（每個都是 1 failed） |
| 請求端重量（暫存區實驗） | 6 種請求 × 2 次 | 第 16.8 節 |
| 全套 pytest（clone，`packaging/unit.sh` 的同一組 pytest 指令，一般使用者；瀏覽器測試照 CI 先 `npm run browser:install` 裝 Chromium） | `pytest tests` | HEAD `d853c3e`：**6,110 案：6,103 過、7 紅、0 skip**，33 分 38 秒。7 紅＝已知要 root 的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 的 5 個 `test_root_*`）；`packaging/check_results.py` 因這 7 案照預期 exit 1。複本裡紅的 HM-20 loopback 2 案在這裡過。2 個警告是既有的 websockets 棄用警告。本片的檔在大程序裡也都過（量停頓的案例都在 50 ms 內）：`test_reply_worker.py` 38.7 秒、`test_health_tolerance.py` 15.5 秒 |
| `packaging/validate.py`（CI 的 venv） | | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（離線暫存 venv：`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt` 雜湊安裝） | `unittest discover -s packaging` | `Ran 203 tests`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py` | | exit 0（沒動 `apps/runtime/*.py`、`apps/*/launch.py`，工具表面不用重產） |
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | HEAD `d853c3e`：gitleaks 8.28.0（釘版、已驗）；`df686dd..d853c3e` 27 個 commit＋HEAD 整棵樹＋整個歷史：**0 命中**。之後只有本 commit（只改本筆記） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | HEAD `d853c3e`：`runtime-patches.json` 176、`runtime-sources.json` 70、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的列管檔 7 個（`access.py`、`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`reply_worker.py`、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔；`redact.py` 照預期列成「沒列管、要人看」：**OK** |
| commit 署名、雙向控制字元 | `git log --format=%B`、diff 掃 U+202A～202E、U+2066～2069 | 都沒有；身分照 clone 的 git config（woowtech） |
| `git status`、暫存目錄 | | 乾淨（未追蹤檔 0）。本段用過的 60 個與前一段留下的 7 個 `/tmp/ha-mp-*` 都已用完整路徑刪除（`SP:hm30r2/tmpdirs.txt`、`SP:hm30r/tmpdirs.txt`）；別的代理的暫存目錄沒動 |

### 16.12 只在 CI 跑的測試、CI 時間

- 本片新增的案例在本機都跑過、都過，沒有只在 CI 跑的新測試。CI（root、0 skip）才是準。
- 已知要 root、本機一定失敗的既有案例（不是本片造成）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`。
- D1、D3 的新測試本機（`g1` 的 junit）：48 案約 15.5 秒，大宗是真實 8 MiB 回覆 9 案 12.5 秒（每案也跑一次迴圈內處理當基準）；
  `test_reply_worker.py` 合計 133 案 33.7 秒（rebase 前 86 案 22.5 秒）。CI 推估：本片這一段多約 15～20 秒；本片合計（rebase 前的推估
  45～65 秒）約 60～85 秒，在每片 1.5 分鐘內，也在交辦的 2 分鐘內。每個量停頓的測試都是固定次數、固定上限（50 ms），沒有重試。
- CI 風險（照實記）：D3 整段本機最高 45.9 ms、D1 跳脫字元那案最高 46.3 ms，離 50 ms 約 4 ms。CI 的 runner 較慢或較忙時可能紅；紅了就是
  那台機器上的實際資訊，照 D1、D3 的定案回報使用者，不放寬門檻（第 16.14 節）。
- 全套本機 6,110 案 33 分 38 秒（一般使用者、Chromium 照 CI 裝）。`checks` 秒數：開 PR 後補（前：`claude-delivery` 最近的 #106 `checks` 1,639 秒；後：本片 PR 的 `checks`）。

### 16.13 commit 對照

rebase 過來的 11 個（第 1～15 節寫的是左欄的編號）：

| rebase 前 | rebase 後 | 內容 |
|---|---|---|
| `092b827` | `15bc2a3` | 測試先寫 |
| `8a2703e` | `e83889d` | 工作執行緒 |
| `73d6cfd` | `c2c764d` | 待送回覆額度 |
| `2552106` | `307f998` | 契約、威脅模型、帳本 |
| `33798ad` | `b6a2c85` | 兩個測試改寫 |
| `c43eefd` | `2dc496e` | 刪重複的區段標題 |
| `5b6d4a5` | `4382ac8` | 本筆記、契約 #17 附註 |
| `503fb3d` | `bcd0628` | 審查修正的測試 |
| `6e073c3` | `22409db` | `reply_worker.py` 說明、帳本 |
| `e84bd8f` | `d5f2e03` | 審查修正的文件 |
| `8b015d5` | `dfd0766` | 本筆記（審查修正） |

rebase 後加的：

| commit | 內容 |
|---|---|
| `a4c42a5` | 測試：HM-31 的預算（rebase 配合） |
| `773014a` | 測試：D1（逐位元、分段、真實 8 MiB 回覆、回收器） |
| `360efd0` | 測試：D3（量整段） |
| `52926ae` | 測試：`make_apps` 最後的參數（rebase 配合，HM-31 的測試） |
| `dd1098f` | 測試：D1（分段放掉、工具清單、巢狀語料） |
| `6481f7f` | 測試工具：A 的健康檢查照子程式的回法（D3） |
| `6601e9b` | 測試：D3（租約、每段一次 token 檢查） |
| `086159f` | 程式：D1 |
| `ebc15a2` | 程式：D3 |
| `85324e8` | 帳本 |
| `179a080` | 測試：D3（checked 的租約在磁碟上換 token 照樣擋下） |
| `5f61a94` | 說明：checked 的租約靠什麼；帳本 |
| `cb93e08` | 測試：D1（每種串流在工作執行緒切框也逐位元相同） |
| `9f1facc` | 說明：`reply_worker.py` 的兩處量測數字照 pytest 改；帳本 |
| `f548912` | 文件：契約、威脅模型、`decisions.md`、驗收表 |
| 最後兩個 | 本筆記：第 16 節，與結論、第 1、11.5、12、13.2、14 節的更新；最後一個補全套 pytest、packaging 與兩個預檢的結果 |

### 16.14 交給後面的片與主對話

- **主對話**：
  - 請求端一個大請求本機仍讓迴圈停 0.09～0.25 秒（第 16.8 節），超過 50 ms，但不在契約第 6 節的情境裡（契約已寫明 CPU 飢餓保證只對回覆
    成立）。選項：(a) 開通的產品把請求端（結構守門、解析、單獨代理字元的檢查、轉送前的重新序列化）也交給工作執行緒；(b) 開通時降低單一
    請求的上限或元素上限；(c) 維持現狀，HM-19c 在目標硬體量，超標再定。建議 (c)，數字不好再做 (a)。
  - 交辦裡「HM-31 審查 S-5」的名稱對不上（HM-31 的 S-5 是 MemAvailable 重複計算）；本片照括號裡的內容量了請求端（上一點）。
  - CI：D1 的真實回覆停頓測試本機最高 46.3 ms（跳脫字元多的長字串：解析端那一次 C 呼叫）。CI 的 runner 若慢很多可能逼近 50 ms；真的紅了是
    實際的資訊（那個形狀在那台機器做不到），照 D1 的定案回報使用者，不放寬。
  - HM-11（#107）用了第 9 節第 109～112 列；本片沒有第 9 節的列，不會撞號。兩片都在契約第 10 節與 `decisions.md` 的變更紀錄最後加列，
    後合的那片 rebase 時只有這兩處的文件衝突。
- **HM-18（DOCS 要寫的句子，D2 定案）**：
  - 「開通多帳號後，每個帳號『已處理、還沒被用戶端收完』的回覆上限是 32 MiB。這是軟上限：達到上限時已經轉送給 MCP 子程式的請求，回覆
    照樣交出。一個帳號的用戶端一次送滿轉送名額、又都不讀回應時，add-on 最多多用約 800 MiB（預設帳號）或 416 MiB（每個額外帳號）的記憶體。」
  - 「回覆在一條工作執行緒上依帳號輪流處理，大回覆分段處理；單一長字串的解析仍會讓 add-on 停一下（本機約 20～40 ms，小主機數倍）。」
  - 「請求（送給 MCP 的內容）仍在 add-on 的主迴圈裡檢查與解析：一個很大的請求會讓所有帳號短暫變慢。」
  - 「工作執行緒停了，add-on 會結束並由 Supervisor 重新啟動。」（第 13.2 節原有的）
- **HM-19c（量測清單補）**：
  - 比對 MemAvailable 時，全域最壞值用非 ASCII（emoji）的數字，每個帳號算進「轉送名額×跳脫後最多 24 MiB」（D2）。
  - J1900 上量 mixed、CJK、emoji 三種真實 8 MiB 回覆的迴圈停頓（D1），另量大量小物件、長字串、跳脫字元與 100 層加 emoji 的巢狀；
    過不了回報、考慮子程序。
  - 整段（讀取＋處理）的停頓、B 的 p95 增量、健康檢查（D3）；請求端一個大請求的停頓（上面第一點）。
  - 處理時間變長：分段處理與分段放掉讓一筆大回覆在工作執行緒上多花時間（大量小物件最多，第 16.7 節），量 A 的回覆在目標硬體要多久做完。
- **獨立審查**：D1、D3 的程式（`reply_worker.py` 的 `encoded`／`_plan`／`released`／回收器、`gateway.py` 的大事件與 `releasable`、
  `redact.py` 的 `checkpoint`、`access.py` 的 `checked`）是審查之後加的，還沒審查過。

## 17. 第二輪獨立安全審查與意見處理（2026-11-17）

第 16 節之後的事。數字以本節為準。`SP:`＝這次工作的暫存區（不進 repo）：前一段 `SP:hm30r3/`、後一段 `SP:hm30r4/`。

### 17.0 結論

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-30-phase2.md`（repo 外；審查 `37160d6`、28 個 commit；證據
  `wave4/evidence-review-HM-30-phase2/`）。判定「修正後通過」：程式本身沒有找到安全漏洞。必修 5 項、建議 6 項、要使用者決定 4 題
  （Q3 只有 MF-2 選 (b) 時才問）。
- **必修 5 項都處理了**：
  - MF-1：改程式。扁平陣列的解析（每 1,024 個數字）、遮罩與成本計算（每 1,024 個成員）都喘息，放掉從尾端切、不先整個複製。數字陣列本機
    都過門檻（工作執行緒那條路最長 5.5～24.1 ms，pytest 7 次；另一次浮點數 50.5 ms，第 17.6 節；審查量的是 41～185 ms）。**沒有物件也沒有數字的陣列**（短字串、true／false／null、空陣列）
    解析仍是 json 的一次 C 呼叫，8 MiB 本機 0.03～0.19 秒：交使用者（Q1）。
  - MF-2：照審查建議 (a) 改程式：JSON 回覆在放掉轉送名額之前就扣，排隊的 tools/call 拿到名額之後再查一次。契約原本的上界成立：真額度一次湧入
    預設帳號 33 個轉送、帳上 792 MiB（上界 800），額外帳號 17 個、408 MiB（上界 416；審查量的是 19 個、456 MiB）。使用者接受的 D2 不用重問
    （Q3 不用問）。
  - MF-3：補測試（審查的 R4 併進來）：秘密放在切段邊界、長字串、3 萬列、5 千個鍵，JSON 與大 SSE 事件。突變 N09 等三個都抓到。
  - MF-4：寫進契約第 6 節與威脅模型第 3 節，本機重量：A 同時送 3 個大量小物件回覆時 B 的 tools/call p95 3.5 秒（一次 `json.dumps` 的對照
    1.9 秒）。要不要改，交使用者（Q2）。
  - MF-5：PR 說明草稿重寫（`wave4/pr-HM-30.md`）。
- **建議 6 項**：S-2～S-6 採用（S-2 列成 Q4）；**S-1 沒採用**：量了，把用戶端移出被量的迴圈，讀取期間的最長停頓沒有變短；最長的那一下
  是 A 的 32 個請求同時進來時閘道自己的請求端工作（第 17.6 節）。
- **另外找到並修好（不在審查裡）**：前一段的 MF-1 寫法在「值與 twin 是同一個容器」時（沒有秘密可遮，`redact_secrets` 原樣交回）一步會
  popitem 兩個成員，跑到一半 KeyError，已編好的回覆變成 500。改成不當 twin，加測試（突變 M1e 抓到）。
- **先核對審查**：MF-1～MF-4 的數字本片都重量過，和審查一致或同一級（第 17.2～17.6 節）；N02、N09 用審查的改法重做，新測試都抓到。審查的
  必修與建議都成立，只有 S-1 建議的做法量起來沒有效果。
- **這一輪分兩段做**：前一段寫了測試與 MF-1、MF-2 的程式（3 個 commit）就中斷了。MF-2 那個 commit 照審查 S-6 把變數改名成 `body`，
  遮住 `make_apps` 讀請求 body 的函式，`serve()` 裡讀 body 的請求全部 NameError（前一段本片 4 檔整檔跑 14 案紅：11 案是這個 NameError，
  3 案是新測試自己的錯：陣列不夠大、子程式計數的時機）。後一段接手：改名 `serialized`、修 twin、修那 3 案、補測試案例，重寫這 3 個
  commit（都沒 push；重寫前開本機備份分支 `backup/hm30-review2-before-rewrite-20261117`＝`d9a51bb`；之後為了把 allocation 測試縮小、省 CI
  時間，測試那個 commit 又重寫一次，後面 3 個照原樣重放），再加帳本與文件。前一段留下的 7 個 `/tmp/ha-mp-*` 已用完整路徑刪除。
- **本機檢查都過**（第 17.8 節），只有量停頓的測試偶發紅：D3 整段 11 次紅 1 次、D1 真實回覆 98 案次紅 1 次（第 17.6 節，照實記）。CI 推估：
  本片這一輪多約 30～40 秒（第 17.9 節）。
- **合併前要使用者答 Q1、Q2、Q4**（第 17.10 節）。使用者 2026-11-17 03:1x 已答（第 18.6 節）。

### 17.1 意見處理表

| 編號 | 意見 | 處理 | 證據 |
|---|---|---|---|
| MF-1（必修） | D1 只對作者的 7 種形狀成立：扁平陣列（ID、短字串、`[[時間, 值]]`、浮點數）在工作執行緒那條路本機停 70～185 ms。原因一：沒有物件的陣列解析是一次 C 呼叫；原因二：`_plan`、`redact_secrets`、浮點數 hook 有 0.4～1.1 秒不喘息的 Python 迴圈（GIL convoy） | 已改（`a02b108`）：解析器每 1,024 個數字一次檢查點，整數也經 `parse_int`（比審查的原型多做：整數陣列不再是一次 C 呼叫）；遮罩、成本計算每 1,024 個成員一次；放掉時從尾端切、不先整個複製（原型沒做：前一段量到幾百萬個成員一次複製 40～70 ms）。測試（`fb0b0e6`）：計數型一案、真實 8 MiB 回覆加 5 種數字陣列（斷言 ≤50 ms）、短字串清單一案只印。文件：契約第 6 節、威脅模型 I8 與第 3 節、`reply_worker.py` 說明。原因一裡沒有數字的那一半拆不開：Q1 | 第 17.2 節；突變 M1a～M1f |
| MF-2（必修） | D2 的最壞值少算約一倍：上界其實是准入×24 MiB | 選 (a) 改程式（`a22a97f`）：JSON 回覆在放掉名額之前經 `PENDING_CHARGE` 先扣（交給 server 時抵掉、請求先結束也還）；排隊的 tools/call 拿到名額之後、轉送之前再查一次。測試：審查的 R2 型（縮小額度）、提早扣的還回去。文件：契約第 5、6 節、威脅模型、`decisions.md` D2 那列加註 | 第 17.3 節；突變 M2a～M2d |
| MF-3（必修） | 工作執行緒遮罩長字串沒有測試（N09 存活） | 已補（`fb0b0e6`）：審查的 R4 併進 `test_reply_worker.py`（4 案） | 第 17.4 節；突變 N09、N09c、N09d |
| MF-4（必修） | D1 讓其他帳號等更久，契約與使用者都不知道 | 契約第 6 節（「一筆變長，別的帳號等得也久」一點、量測表的 B p99 標明是注入成本、加「真實回覆時 B 的延遲」列）、威脅模型第 3 節、`reply_worker.py` 說明；本機重量（X3）；HM-19c 清單；本片測試不量（一次要 10 秒以上，CI 時間）。要不要改：Q2 | 第 17.5 節 |
| MF-5（必修） | PR 說明草稿是第一階段的 | 重寫 `wave4/pr-HM-30.md`（基準 `df686dd`、commit 數、兩輪審查、D1～D3 的做法、Q1、Q2、Q4、本機檢查與預檢） | — |
| S-1 | D3 整段測試在小而忙的機器上會紅；建議把測試的用戶端與假子程式移出被量的迴圈 | **沒採用**。量了用戶端那一半（X4：A 的 32 個請求改成直接呼叫 ASGI app，不經程序內的 httpx 用戶端）：讀取期間最長停頓一般 34.1～38.1 ms（原本 26.3～36.8）、2 顆 CPU 加忙迴圈 72.4～75.7 ms（原本 62.5～67.3），沒有變短；最長的都在第 1～2 個取樣，也就是 32 個請求同時進來時閘道的請求端工作（token、HM-31 守門、授權、轉送），正式環境也在迴圈上（Q4 的範圍）。假子程式每個請求只切一段事先配好的 bytes，移到子程序要改成真 socket 的子程式伺服器，是整個測試工具的改寫。門檻沒放寬；CI 第一次跑完把數字補進本節（紅了照 D3 的定案回報） | 第 17.6 節 |
| S-2 | 請求端的停頓要列成 PR 的待決題 | 已列成 Q4（PR 說明與第 17.10 節）；建議 (c) | 審查 R7；第 16.8 節 |
| S-3 | D1 讓一筆回覆的記憶體高峰變高 | 已寫：契約第 5 節（全域最壞值的回覆放大）與第 6 節（慢讀用戶端、量測表一列）；HM-19c 用 27.6 倍（審查；本片重量 27.5 倍）。重量（`peak_rss.py`，審查的腳本） | 第 17.6 節 |
| S-4 | `_plan` 的成本估計沒有測試（N02 存活） | 已補（`fb0b0e6`）：短的 emoji／中文字串清單，每次 C 編碼器的輸出不超過 `PIECE_BYTES` | N02 抓到 |
| S-5 | `gc.disable()` 是整個程序的 | 已寫：`reply_worker.py` 模組說明、契約第 6 節；HM-19c 清單加「長時間大回覆時看 RSS」 | — |
| S-6 | (1) `encoded` 遮住模組函式；(2) 契約一句矛盾；(3) N04b 不用改 | (1) 改名 `serialized`（審查建議的 `body` 會讓 `serve()` 裡讀請求 body 的 lambda NameError，見上）；(2) 契約第 5 節改寫（今天沒開通時是 listener 64 條連線各一個回覆）；(3) 同意，不改 | — |
| Q1～Q4 | 待使用者決定 | Q1、Q2、Q4 列在 PR 說明與第 17.10 節；Q3 不用問（MF-2 選 (a)） | — |
| 另外找到 | 值與 twin 是同一個容器時，前一段的 `released` 一步 popitem 兩個成員 | 已修（`a02b108`）＋測試（`fb0b0e6`） | 突變 M1e |

### 17.2 MF-1：扁平陣列

**做法**（`a02b108`；只在工作執行緒那條路，沒開通的產品不經過）：

| 步驟 | 之前 | 現在 |
|---|---|---|
| 解析（`config.strict_json`） | 只在建物件（`object_pairs_hook`）與浮點數（`parse_float`）時回到 Python，只在物件呼叫檢查點；整數、字串、陣列都在 C 裡 | 每 1,024 個數字呼叫一次檢查點；整數也經 `parse_int`（`int` 本身：值相同，超過位數上限一樣 `ValueError`） |
| 遮罩（`redact.redact_secrets`） | 每個 list／dict 開頭一次 | 大的 list、dict 每 1,024 個成員一次；鍵也帶著檢查點遮（長鍵和長字串一樣）；小的照舊一次推導式。鍵遮罩後相撞時，順序與值照推導式 |
| 成本計算（`reply_worker._plan`） | 每個容器結束時一次 | 另外每 1,024 個成員一次 |
| 放掉（`reply_worker.released`） | 先複製整個容器（list 與 twin 各一份、dict 的 items）再清空 | list 從尾端一段段切掉，dict 一個一個 popitem（twin 同順序）；twin 就是值自己的容器時不當 twin |

**每一步之間最長不喘息多久**（獨立腳本 `SP:hm30r4/exp/gaps2.py`：主執行緒、回收器關著、檢查點只記時間；8 MiB；3 次）：

| 形狀 | `37160d6`（審查的版本） | 現在 | 最長那一段在哪 |
|---|---|---|---|
| ID 清單 | 260～269 ms | 5.0～5.3 ms | — |
| 小整數 | 1,031～1,081 ms | 5.3～5.9 ms | — |
| `[[ts, 整數]]` | 112～115 ms | 4.9～5.6 ms | — |
| `[[ts, 浮點]]` | 220～237 ms | 4.9～5.1 ms | — |
| 浮點數 | 560～778 ms | 7.0～7.4 ms | — |
| 大量小物件 | 16～25 ms | 5.3～7.7 ms | — |
| 短字串清單 | 400～406 ms | 107～110 ms | 解析（一次 C 呼叫） |
| 空字串清單 | 677～686 ms | 71～73 ms | 解析 |
| `true`／`null` 清單 | 318～331 ms | 27～35 ms | 解析 |
| 中文短字串 | 161～169 ms | 64～66 ms | 解析 |
| 空陣列的陣列、`[["ab"]]` | 170～228 ms | 177～191 ms | 解析 |

**經過真的 `make_apps` 與工作執行緒**（暫存區實驗 X1＝審查的 R1：迴圈延遲探針每 2 ms，迴圈上另外每 2 ms 一次 `store.load` 並計時；
`SP:hm30r4/logs/sA/x1.log`）：

| 8 MiB 回覆 | 工作執行緒那條路的迴圈最長停頓：審查 R1（`37160d6`）→ 現在 | 同時的 `store.load` p99：審查 → 現在 | 一筆的時間（現在） |
|---|---|---|---|
| mixed | 20.6～44.1 → 27.4 ms | 0.4～0.5 → 0.31 ms | 0.70 秒 |
| ID 清單 | 103.4～103.6 → 8.7 ms | 36.2～40.8 → 0.48 ms | 1.5 秒 |
| 小整數 | 177～185 → 9.8 ms | 36.2～41.4 → 0.44 ms | 4.0 秒 |
| `[[ts, 整數]]` | 102.7～113.6 → 5.7 ms | 0.4～0.7 → 0.40 ms | 2.5 秒 |
| `[[ts, 浮點]]` | 35.7～41.0 → 6.1 ms | 20.6～30.6 → 0.48 ms | 2.6 秒 |
| 浮點數 | 69.9～80.1 → 13.4 ms | 39.4～41.1 → 0.59 ms | 3.2 秒 |
| 短字串 | 97.3～105.5 → **113.9 ms** | 25.6～41.1 → 0.66 ms | 2.4 秒 |
| 中文短字串 | — → **52.6 ms** | — → 0.44 ms | 0.9 秒 |
| 空字串 | — → **61.2 ms** | — → 4.1 ms | 2.4 秒 |
| `true` | — → 22.9 ms | — → 0.35 ms | 1.6 秒 |
| 空陣列 | — → **126.2 ms** | — → 9.2 ms | 6.8 秒 |

- GIL convoy 沒了：所有形狀的 `store.load` p99 回到 0.3～0.7 ms（空陣列 9.2、空字串 4.1 ms：成本計算、遮罩與放掉的 Python 迴圈最多）。
- 數字陣列都過 50 ms。超過的都是「沒有物件也沒有數字」的陣列，停在解析那一次 C 呼叫：Q1。
- 一筆變長：小整數 2.8→4.0 秒（審查的原型 3.7 秒）、空陣列 6.8 秒。第 17.5 節（MF-4）。

**pytest**（`test_a_real_8_mib_reply_is_the_loops_bytes_and_stops_the_loop_briefly`，12 種形狀＋2 種事件）：最後的測試檔 7 次（第二次取鎖
4 次、第四次取鎖 3 次；每次一個 pytest 程序；單位 ms）：

| 形狀 | 工作執行緒那條路的迴圈最長停頓（7 次） | 一筆的時間 | 同一筆在迴圈內處理 |
|---|---|---|---|
| mixed | 20.8～38.5 | 0.65～0.90 秒 | 256～335 |
| 大量小物件 | 8.8～15.6 | 3.4～3.9 秒 | 851～969 |
| CJK | 6.9～31.5 | 0.10～0.15 秒 | 64～73 |
| emoji | 9.9～29.7 | 0.12～0.16 秒 | 85～91 |
| 長 ASCII 字串 | 15.1～26.1 | 0.09～0.14 秒 | 61～78 |
| 跳脫字元 | 21.1～41.3 | 0.09～0.12 秒 | 60～70 |
| 64 層巢狀 | 5.6～12.5 | 1.5～1.7 秒 | 573～614 |
| ID 清單 | 5.5～12.5 | 1.4～1.7 秒 | 264～288 |
| 小整數 | 9.0～21.8 | 3.8～4.7 秒 | 724～790 |
| `[[ts, 整數]]` | 5.5～13.3 | 2.4～2.9 秒 | 579～656 |
| `[[ts, 浮點]]` | 5.8～8.8 | 2.5～2.7 秒 | 797～905 |
| 浮點數 | 7.5～24.1，另一次 **50.5（紅）** | 3.0～3.7 秒 | 983～1,229 |
| mixed（事件） | 18.9～31.7 | 0.77～0.91 秒 | 270～383 |
| emoji（事件） | 12.8～34.1 | 0.25～0.27 秒 | 135～142 |
| 短字串清單（只印） | 82.8～110.4 | 1.8～2.3 秒 | 470～680 |

- 98 案次（14 案×7 次）裡 97 案次在 41.3 ms 以內，最高的是跳脫字元多的長字串（解析端那一次 C 呼叫）。
- 浮點數那一次 50.5 ms 的分析在第 17.6 節（判斷是共用主機讓整個程序停住）。第一次取鎖另 4 次（3 次的測試檔還有 state 讀取，
  1 次沒有；只差在量法），數字陣列都在 5.5～12.9 ms；2 顆 CPU 加忙迴圈 1 次 9.9～18.0 ms。

測試檔另外試過「迴圈上同時每 2 ms 讀一次 state」（前一段加的，沒有 commit）：最長停頓 mixed 從 12.6 ms 變 37.6～45.6 ms、emoji 事件從
14.5 變 30.5～42.7 ms（長字串那一次 C 呼叫期間剛好在讀 state 的，每個系統呼叫都要等 GIL），離門檻太近、CI 容易隨機紅，所以沒放進測試。
convoy 的回歸由計數型測試守（確定性：每一步的檢查點數），數字記在上表（X1）。

### 17.3 MF-2：一次湧入的上界

- **做法**（`a22a97f`）：
  - `gateway.serve`：tools/call 拿到轉送名額之後、轉送之前再呼叫一次 `PENDING_REPLIES`（同一個函式；被擋的回 200＋`-32003`、放掉名額，
    子程式沒收到）。工作執行緒交回 JSON 回覆時，先呼叫 request state 的 `PENDING_CHARGE`（新名稱）扣它的位元組，`finally` 才放掉名額。
  - `profile_router.ProfileGate.serve`：`PENDING_CHARGE` 是每個請求自己的 `charge()`：扣進 `reply_bytes`（`early`），帳號 app 交給 server
    時抵掉、不重複扣；請求結束時還沒交出的還回去。
  - 為什麼兩件都要：只在名額之後多查一次，攔不到放掉名額的那一筆（那時它還沒交給 server、還沒扣）；只提早扣，已經過了第一次檢查、
    在排隊的照樣轉送。SSE 串流到結束都持有名額，本來就成立。只有 tools/call 會被擋；其他會轉送的方法（initialize、ping、tools/list）的
    回覆由閘道自己重建或很小。
- **測試**（`fb0b0e6`）：
  - `test_answers_that_arrive_at_once_hold_no_more_than_the_budget_and_a_reply_a_slot`［json、event-stream］（審查的 R2 型）：額度縮小
    （准入 8、名額 2、排隊 6、待送 1 MiB），8 個 600 KiB 的回覆一次湧入、都不讀。JSON：3 個轉送、帳上 1,802 KiB（上界 2,224 KiB；審查前
    8 個全轉、4,800 KiB）；SSE：2 個、1,203 KiB。名額放掉後停 50 ms（像真的連線關閉要一點時間），讓等名額的請求在這時候做第二次檢查：
    少了任一件，這一刻都會轉送（M2a、M2b 都紅）。
  - `test_an_answer_charged_before_it_is_handed_over_gives_the_charge_back_when_it_never_is`：放掉名額之後、交給 server 之前取消請求：
    扣的 300 KiB 還回去。
- **真額度**（暫存區實驗 X2＝審查的 R2b：32 個（預設帳號 64 個）8 MiB emoji 回覆、都不讀，子程式先扣住轉送名額那麼多個，等全部進來
  才回答；`SP:hm30r4/logs/sA/x2.log`）：

| 帳號 | 審查前（審查 R2b） | 現在 | 契約第 5 節的上界 |
|---|---|---|---|
| 預設帳號（准入 64、名額 32、排隊 32） | — | 33／64 個轉送、帳上 792 MiB、RSS 增量 1,088 MiB | 800 MiB |
| 額外帳號（准入 32、名額 16、排隊 16） | 19／32 個、456 MiB、RSS 增量 632～634 MiB | 17／32 個、408 MiB、RSS 增量 536 MiB | 416 MiB |

- RSS 增量比帳上多約 1.3～1.4 倍（物件、h11 的緩衝等）。HM-19c 比對 MemAvailable 時用 RSS 的數字（交給 HM-19c 的清單，第 17.10 節）。

### 17.4 MF-3 與 S-4：遮罩與成本計算的測試

- `test_every_secret_is_masked_on_the_worker_wherever_it_cuts_and_breathes`［at-cuts、elsewhere × json、event-stream］：審查的 R4。秘密
  （這個帳號的 token、子程式 token、後端金鑰、兩個別的帳號的 token）放在：40 處長字串裡（跨在 8,192 碼位的切段邊界上，或不在邊界；字串
  長過 64 Ki 碼位，遮罩時每個秘密之間喘息）、3 萬列、5 千個鍵（都超過 1,024 個成員，走分段的路）。JSON 與 SSE 事件（大於 64 KiB，在工作
  執行緒切框）：工作執行緒的回應和迴圈內處理逐位元相同、沒有秘密、至少 35,040 個遮罩。本機 4 案約 1 秒。
- `test_long_strings_and_large_values_go_out_between_checkpoints` 加一組短的 emoji／中文字串清單（每個碼位的成本以 12 位元組算才不超過）：
  每次 C 編碼器的輸出都不超過 `PIECE_BYTES`。
- 突變（審查的改法；第 17.7 節）：N09（長字串喘息後跳過替換）、N09c（大 list 每段漏一個成員）、N09d（大 dict 的鍵不遮）、N02（字串成本每碼位
  算 1 位元組）：都抓到。

### 17.5 MF-4：別的帳號等 A 正在處理的一筆

- 工作執行緒一次只處理一筆，B 的回覆最多等 A 正在處理的那一整筆。D1 的分段、喘息與分段放掉讓一筆變長（第 17.2 節的「一筆的時間」）。
- 暫存區實驗 X3（審查的 R8；A 同時送 3 個真實 8 MiB 回覆，不注入成本；B 期間每 50 ms 呼叫一次工具；`SP:hm30r4/logs/sA/x3.log`）：

| A 的回覆 | 設定 | A 的 3 筆做完 | B 的 tools/call p50 | p95／最長 |
|---|---|---|---|---|
| 大量小物件 | 現在（D1） | 10.7 秒 | 3,338 ms | 3,521 ms |
| 大量小物件 | 工作執行緒上一次 `json.dumps`、不分段放掉（只為對照） | 5.8 秒 | 1,784 ms | 1,889 ms |
| mixed | 現在（D1） | 2.2 秒 | 582 ms | 718 ms |
| mixed | 一次 `json.dumps`（對照） | 1.5 秒 | 356 ms | 455 ms |

- 和審查的 R8 一致（D1 p95 3,922 ms、對照 1,781 ms）。契約第 6 節的「B 的 p99 ≤2d＋0.2 秒」只量可控注入（d＝0.25 秒）；量測表的那一列已
  標明，另加「真實回覆時 B 的延遲」列。HM-19c 的放行條件（B 的 p95 增量 ≤1 秒）在目標硬體遇到物件多的 8 MiB 回覆幾乎過不了：Q2。
- 本片測試不量（一次要 10 秒以上；CI 時間）。

### 17.6 S-1、S-3

**S-1（沒採用）**：暫存區實驗 X4（`SP:hm30r4/logs/sA/x4-*.log`、`n-x4-*.log`）：同一個 CPU 飢餓情境，A 的 32 個請求用程序內的 httpx 用戶端
（現在的測試）或直接呼叫 ASGI app（不經用戶端），各 2 次；「2 顆 CPU」＝`taskset` 綁 2 顆 CPU、旁邊 2 個忙迴圈（審查的 f-*）：

| 設定 | 用戶端 | 整段最長 | 讀取期間最長（落在第幾個取樣） | 處理期間最長 | B 的 p99 |
|---|---|---|---|---|---|
| 一般 | httpx | 36.8、26.3 ms | 36.8（第 1 個）、26.3 ms | 26.1、21.6 ms | 297、296 ms |
| 一般 | 直接 ASGI | 38.1、34.1 ms | 38.1（第 1 個）、34.1 ms（第 2 個） | 11.4、15.7 ms | 327、311 ms |
| 2 顆 CPU＋忙迴圈 | httpx | 62.5、67.3 ms | 62.5、67.3 ms（第 2 個） | 37.7、28.2 ms | 563、565 ms |
| 2 顆 CPU＋忙迴圈 | 直接 ASGI | 75.7、72.4 ms | 75.7、72.4 ms（第 2 個） | 50.9、49.4 ms | 549、553 ms |

- 用戶端移出去沒有變短（處理期間的數字不能直接比：注入成本的校準在兩種設定下不同，直接 ASGI 那邊每段約 4.6～4.9 ms、忙的機器上 26 ms）。
- 最長的停頓都在開頭（第 1～2 個取樣）：32 個 task 同時開始，各自跑到第一個真的等待點才讓出，迴圈一輪裡就做完 32 個請求的請求端工作
  （token 檢查、HM-31 的守門、授權、轉送給子程式）。正式環境 32 個請求同時到達時，uvicorn 也是在同一輪把它們交給 app，所以這是閘道自己的
  工作，不是測試工具的；要再壓低是請求端的事（Q4）。
- 本片 3 次（第一次取鎖，`SP:hm30r4/logs/sA/g2-d3-*.log`）：49.5、37.8、37.8 ms（這 3 次旁邊有一支卡住、CPU 重的獨立腳本在跑：`peak_rss.py`
  一直重建 8 MiB 的 JSON；之後停掉）；最後的測試檔 8 次：30.9、34.7、38.7、32.3、36.1 ms（第二次取鎖）與 35.7、34.0、**63.3 ms（紅）**
  （第四次取鎖；讀取期間 63.3 ms、處理期間 22.2 ms；這幾次前後容器的 CPU 節流計數 `nr_throttled` 都沒變）。處理期間 16.7～22.2 ms，B 的 p99 0.29～0.31 秒。11 次裡紅 1 次：最長的那一下
  在讀取期間（上表 X4：開頭 32 個請求同時進來時的請求端工作），不是工作執行緒，也不是 CPU 節流。
- 結論：門檻不放寬、測試照舊。CI 第一次跑完把數字補進本節；紅了就是那台機器的實際資訊，照 D3 的定案回報使用者。

**量停頓的測試偶發的紅（照實記）**：

- D3 整段：上一點，11 次紅 1 次，在讀取期間（請求端）。
- D1 真實回覆：98 案次紅 1 次（浮點數 50.5 ms；同一形狀另 6 次 7.5～24.1 ms）。工作執行緒自己最長的不喘息區間只有 5～7 ms（`gaps2.py`，
  第 17.2 節），解釋不了 50 ms。暫存區實驗 X6（`SP:hm30r4/logs/sC/x6.log`；浮點數、小整數、跳脫字元各 6 次，迴圈延遲探針與工作執行緒的
  每個檢查點都記時間，另記每次回收）：
  - 跳脫字元 6 次最長 25.3～45.9 ms，都落在工作開始到第一個檢查點之間：解析端掃那一個長字串的 C 呼叫（已知、D1 接受的）。
  - 浮點數 6 次最長 6.3～36.2 ms；36.2 那次落在工作開始之前（迴圈還在讀子程式的回覆）。
  - 小整數一次 **59.0 ms**：落在兩個平常只隔 0.5 ms 的檢查點之間（編碼的兩段之間），這 59 ms 裡迴圈與工作執行緒都沒前進，也沒有回收；
    那段時間容器沒有被 CPU 節流（`/sys/fs/cgroup/cpu.stat` 的 `nr_throttled` 沒變；這個容器有 32 顆 CPU 的配額，別的時候被節流過）。
  - 判斷：這種偶發的整個程序停頓來自多個代理共用的主機（當時 load average 約 20～47），不是程式；GitHub 的 runner 不和別的工作共用，
    應該少見，但 runner 的鄰居很忙時也可能遇到。

**S-3（記憶體高峰）**：審查的 `peak_rss.py`（新程序、一筆 8 MiB 回覆；迴圈內處理 → 工作執行緒；`SP:hm30r4/logs/peak_rss-snapW.out`、
`SP:hm30r4/logs/sB/peak_rss.out`）：

| 一筆 8 MiB 回覆 | 迴圈內處理 | 工作執行緒（D1） | 審查（迴圈內 → 工作執行緒） |
|---|---|---|---|
| 大量小物件 | 209 MiB（26.1 倍） | 220 MiB（27.5 倍） | 201～209 → 220～221 MiB（27.6 倍） |
| 64 層巢狀 | 73 MiB | 98 MiB | 73 → 100 MiB |
| 小整數 | 72 MiB | 111 MiB | 64 → 112 MiB |
| ID 清單 | 46 MiB | 69 MiB | 53 → 79 MiB |
| `[[ts, 整數]]` | 111 MiB | 131 MiB | 109 → 131 MiB |
| 浮點數 | 96 MiB | 127 MiB | — |
| 短字串清單 | 102 MiB | 130 MiB | — |
| emoji 長字串 | 32 MiB | 54 MiB | — |


- 和審查一致（大量小物件 201～209 → 220～221 MiB）：從尾端放掉不先複製，高峰沒變（高峰在解析與遮罩之後、放掉之前，兩份值都在）。
- 契約第 5 節的全域最壞值（原本 8 MiB×25）與第 6 節的慢讀門檻用的「一筆處理放大 200 MiB」是 D1 之前的估計；已寫明 D1 之後最壞約
  220 MiB（審查 27.6 倍、本片 27.5 倍），全域最壞值與 HM-19c 用 27.6 倍。

### 17.7 先紅後綠與突變

**先紅**（`SP:hm30r4/snaps/snapHT`＝`37160d6`＋最後的 `tests/test_reply_worker.py`，核心還沒改）：新測試 16 案（第二次取鎖；`SP:hm30r4/logs/sB/b-red-new.log`）：**7 紅、9 綠**。

- 紅：計數型（解析、遮罩、成本計算都沒有每 1,024 個的檢查點）、一次湧入（JSON：8 個全部轉送）、提早扣的還回去（沒有 `PENDING_CHARGE`）、
  從尾端放掉的配置量（舊寫法整個複製：3.2 MB／6.4 MB 超過上限）、ID、小整數、`[[ts, 整數]]` 的真實回覆（舊程式解析整數陣列是一次 C 呼叫）。
- 綠的 9 案都說得出原因：S-4 與遮罩 4 案擋的是突變（舊程式本來就對：N02、N09 系列才會紅）；一次湧入的 SSE（串流本來就持有名額）；
  短字串（只印）；`[[ts, 浮點]]` 與浮點數的真實回覆（舊程式的浮點數 hook 本來就讓 GIL 換手，convoy 只在迴圈另有系統呼叫時才顯出來：
  第 17.2 節 X1 的 `store.load`；這兩種的回歸由計數型測試擋，M1f）。
- allocation 測試縮到 20 萬個成員之後，在 `37160d6` 上照樣紅（第四次取鎖：3,202,968 位元組 ＞ 上限 2,400,000）。

**後綠**：最後的 HEAD 本片 4 檔 251 案全過（第 17.8 節）。

**突變**（各改最後的程式一處，在暫存區的複本跑該抓住它的測試；`SP:hm30r4/bin/mutate.py`；最後的測試檔）：

| # | 突變 | 抓住它的測試 | 結果 |
|---|---|---|---|
| N09 | 長字串喘息後跳過替換（審查的改法） | 遮罩 4 案 | 4 紅 |
| N09c | 遮罩大 list 時每段漏一個成員 | 遮罩、計數型 | 5 紅 |
| N09d | 遮罩大 dict 時鍵不遮 | 遮罩、計數型 | 5 紅 |
| N02 | 字串成本每碼位算 1 位元組（審查的改法） | S-4（每次編碼不超過 64 KiB） | 紅 |
| M1a | `_plan` 不每 1,024 個成員喘一次 | 計數型 | 紅 |
| M1b | 整數不經 `parse_int`（整數陣列又是一次 C 呼叫） | 計數型、ID 的真實回覆 | 2 紅 |
| M1c | `released` 改回整個複製的版本 | 從尾端放掉的配置量 | 紅（第二、四次取鎖；第一次取鎖時還沒有這個斷言，只有浮點數的真實回覆以 51.2 ms 紅，靠時間不穩，所以補了確定性的斷言） |
| M1d | 遮罩大 list 的段與段之間不喘息 | 計數型 | 紅 |
| M1e | twin 就是值本身時照樣當 twin | twin 一案 | 紅（KeyError） |
| M1f | 浮點數不計數 | 計數型（浮點數的真實回覆照過） | 1 紅 1 綠 |
| M2a | 拿到名額之後不再查一次 | 一次湧入（JSON） | 紅 |
| M2b | 放掉名額之前不先扣 | 一次湧入（JSON）、提早扣的還回去 | 2 紅 |
| M2c | 請求結束時不還提早扣的 | 提早扣的還回去 | 紅 |
| M2d | 交出時不抵掉提早扣的（重複扣） | 一次湧入（JSON） | 紅 |

第一次取鎖時同一組 14 個也都抓到（測試檔還有 state 讀取那一版）。每個突變的複本都只差那一處（SHA-256 核對過）。

### 17.8 本機檢查（2026-11-17，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪除；pytest 都排在共用鎖後面）

pytest 都在 repo 外的複本跑（`git archive`，`.venv`、`apps/`、`packages/mcp-admin-ui` 連回 clone；`SP:hm30r4/bin/snap.sh`）。

共取鎖 4 次（`SP:hm30r4/logs/sA`～`sD/`）。

| 檢查 | 範圍 | 結果 |
|---|---|---|
| 先紅 | 新測試 16 案，在 `37160d6` 上 | 7 紅、9 綠（第 17.7 節） |
| 本片 4 檔（最後的 HEAD `9331fe1`） | `test_reply_worker.py`、`test_health_tolerance.py`、`test_profile_runtime.py`、`test_request_budget_gateway.py` | **251 案全過**、0 skip、95.7 秒（`test_reply_worker.py` 147 案 61.2 秒）；第二次取鎖（allocation 測試 100 萬個成員那版）251 案、100.6 秒 |
| 相關 28 檔（第一次取鎖；程式和最後的 HEAD 去掉說明字串後 AST 逐檔相同） | HM-31 預算與結構 3 檔、HM-14 的 5 檔＋`test_reply_mask_union.py`、HM-10 的 3 檔、`test_monitor_cancel.py`、HM-01 黃金回歸與兩個契約凍結、額度、路由、生命週期、健康退避、租約、後端錯誤、遮罩矩陣、錯開啟動、port、子程式資源、SSE 錯誤遮罩、Nextcloud 秘密 | **836 案全過**、0 skip、284 秒。HM-01 的三檔 45 案（17＋9＋19）；三檔與 `tests/contract/` 沒改 |
| 用到改過的程式、第一次沒跑的 15 檔（第二次取鎖，在 clone 裡跑：`test_backend_loopback.py` 的 n8n 案例要 clone 自己的 `apps/` 路徑） | `test_backend_loopback.py`、`test_sse_sanitize.py`、`test_initialize_reply.py`、`test_tool_call_refusals.py`、`test_session_required.py`、`test_secret_path.py`、`test_streaming_and_storage.py`、`test_child_bearer.py`、`test_claude_ai_connector.py`、`test_protocol_clients.py`、`test_review_regressions.py`、`test_quality_core_regressions.py`、`test_tool_inventory.py`、`test_initialize_identity.py`、`test_initialize_cleanup.py` | **907 案全過**、178 秒（2 個既有的 websockets 棄用警告）；跑完 clone 只有還沒 commit 的文件 |
| 帳本的 pytest | `test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources`、`test_ledger_precheck.py` | 9 案全過 |
| D3 整段 | CPU 飢餓一案，11 次 | 10 次 30.9～49.5 ms、1 次 63.3 ms 紅（第 17.6 節） |
| D1 真實 8 MiB 回覆 | 14 案＋短字串，7 次 | 98 案次 97 次 ≤41.3 ms、1 次 50.5 ms 紅（第 17.2、17.6 節） |
| 健康檢查容忍 | 2 案 | 都過；最晚在該做之後 21～37 ms 做完 |
| 突變 | 14 個 | 都抓到（第 17.7 節） |
| 2 顆 CPU＋2 個忙迴圈（第一次取鎖） | 真實回覆、健康檢查容忍、X4 | 真實回覆 15 案全過（最長 37.5 ms；短字串只印 153 ms）；健康檢查容忍 2 案過（最晚 47、51 ms）；X4 第 17.6 節 |
| 暫存區實驗（都沒進 repo） | X1～X6、`gaps2.py`、`peak_rss.py`、`released_peak*.py` | 第 17.2～17.6 節 |
| `packaging/validate.py`（CI 的 venv） | | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| 全套 pytest | | 沒重跑：第一階段在 `d853c3e` 跑過（6,110 案、7 個已知要 root 的紅、0 skip）。這一輪改的程式只在開通的產品那條路：沒開通時 `serve()` 只多一個 `pending = None`，`strict_json` 與 `redact_secrets` 不帶檢查點時一行不變；受影響的 4＋28＋15 檔都跑過 |
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | HEAD `9fa8f89`：gitleaks 8.28.0（釘版、已驗）；`df686dd..9fa8f89` 33 個 commit＋HEAD 整棵樹＋整個歷史：**0 命中**。之後只有本 commit（只改本筆記） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | HEAD `9fa8f89`：`runtime-patches.json` 176、`runtime-sources.json` 70、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的列管檔 7 個（`access.py`、`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`reply_worker.py`、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔；`redact.py` 照預期列成「沒列管、要人看」：**OK** |
| commit 署名、雙向控制字元 | `git log --format=%B`、diff 掃 U+202A～202E、U+2066～2069 | 都沒有；身分照 clone 的 git config（woowtech） |
| `git status`、暫存目錄 | | 乾淨；用過的 `/tmp/ha-mp-*` 與前一段留下的 7 個都已用完整路徑刪除（`SP:hm30r4/tmpdirs.txt`、`bin/cleanup-*.sh`）；別的代理的暫存目錄沒動 |

### 17.9 CI 時間

- 本片 4 檔本機 95.7 秒；`test_reply_worker.py` 147 案 61.2 秒（第一階段結束時 133 案 33.7 秒）、`test_health_tolerance.py` 2 案 15.9 秒。
- 這一輪加的 14 案本機約 28 秒：5 種數字陣列的真實回覆 20.7 秒（每案也跑一次迴圈內處理當對照）、短字串 3.3 秒、一次湧入 1.8 秒、遮罩 1.3 秒、
  從尾端放掉的配置量 0.7 秒（改小之前 4.5 秒）、其他在 1 秒以內。
- CI 推估：GitHub 的 runner 單核速度和本機差不多，這一輪多約 30～40 秒；本片兩個新檔合計約 80～100 秒，在交辦的 2 分鐘內。量停頓的測試都是
  固定次數、固定上限（50 ms），沒有重試。
- CI 風險（照實記）：本機 D3 整段 11 次紅 1 次、D1 真實回覆 98 案次紅 1 次（第 17.6 節）。CI 紅了就是那台機器的實際資訊，照 D1、D3 的定案
  回報使用者，不放寬門檻；要不要改成「超過門檻時再量一次」（固定最多兩次）也是門檻的事，要使用者同意（第 17.10 節）。

### 17.10 commit 對照、待使用者決定與交給後面的片

**commit**（`37160d6` 之後；前一段的 3 個重寫過，對照在右欄）：

| commit | 內容 | 前一段的 commit（重寫前） |
|---|---|---|
| `fb0b0e6` | 測試：MF-1（計數型、5 種數字陣列的真實回覆、短字串清單只印、twin 就是值本身、從尾端放掉的配置量）、MF-2（一次湧入、提早扣的還回去）、MF-3（遮罩）、S-4 | `adb79ef`：後一段修了 3 案自己的錯（陣列不夠大、子程式計數的時機），補 twin、鍵相撞、tracemalloc 三處 |
| `a02b108` | 程式：MF-1（解析、遮罩、成本計算的檢查點；從尾端放掉；twin 修正）；模組說明補 S-5、Q1、MF-4 與量測數字 | `0c80dc2`：後一段補 twin 修正與說明 |
| `a22a97f` | 程式：MF-2（拿到名額之後再查一次、放掉名額之前就扣）；S-6 改名 `serialized` | `d9a51bb`：前一段改名 `body`，NameError；後一段改 `serialized` |
| `9331fe1` | 帳本：`config.py`、`gateway.py`、`profile_router.py`、`reply_worker.py` 重算並補說明 | — |
| `9fa8f89` | 文件：契約、威脅模型、`decisions.md`、驗收表 | — |
| 最後一個 | 本筆記：第 17 節與結論 | — |

前一段的 3 個 commit（`adb79ef`、`0c80dc2`、`d9a51bb`）留在本機備份分支 `backup/hm30-review2-before-rewrite-20261117`（沒 push）；
重寫後的樹和「前一段＋後一段的修正」逐檔相同（`git diff` 只差上表說的幾處）。

**待使用者決定**（合併前要有答案；門檻都沒放寬；使用者 2026-11-17 03:1x 已答：Q1、Q2 接受，Q4 維持現狀，都是 HM-19c 實測再定，第 18.6 節）：

| # | 題目 | 現況（本機 EPYC 7713） | 選項 | 建議 |
|---|---|---|---|---|
| Q1（MF-1） | 沒有物件也沒有數字的陣列，解析是一次 C 呼叫 | 數字陣列已拆開（本片）。剩短字串、true／false／null、空陣列：8 MiB 0.03～0.19 秒（短字串約 0.1 秒、空陣列約 0.18 秒），超過 50 ms；目標硬體慢數倍 | (a) 接受並寫明，HM-19c 在 J1900 量；(b) 開通時回覆也設元素個數上限（例如比照請求的 20 萬，超過回 502；會擋到很大的正常清單）；(c) 子程序（D1 原本的 (b)）；(d) 自己寫分段解析（Python 迴圈逐元素呼叫 C 解析器：程式量大、要和 `json.loads` 逐一等價，在信任邊界上，不建議） | (a)＋HM-19c 量；目標硬體超標再定 (b) 或 (c) |
| Q2（MF-4） | D1 讓別的帳號等更久 | A 同時送 3 個大量小物件回覆時，B 的 tools/call p95 3.5 秒（一次 `json.dumps` 的對照 1.9 秒）；一筆 8 MiB 最久約 7 秒（空陣列） | (a) 接受並寫明，HM-19c 用真實回覆量 B 的 p95；(b) 工作執行緒在分段之間換帳號（同時有兩筆在記憶體裡放大：記憶體最壞值多一筆）；(c) 別的帳號沒在排隊時少喘息、少分段放掉（A 單獨時快一點，B 的最壞不變） | (a)，HM-19c 過不了再做 (b) |
| Q4（審查 S-2） | 請求端的停頓 | 一個大請求本機 92～187 ms（審查 R7）、0.09～0.25 秒（第 16.8 節）；D3 整段測試最長的那一下也在這裡（第 17.6 節） | (a) 開通的產品把請求端（守門、解析、單獨代理字元的檢查、轉送前的重新序列化）也交給工作執行緒；(b) 開通時降低單一請求的上限或元素上限；(c) 維持現狀，HM-19c 在目標硬體量，超標再定 | (c)（審查同意） |

Q3（MF-2 選 (b) 時才問）不用問：本片選 (a)，契約原本的數字成立。

**交給主對話**：

- 量停頓的測試在本機偶發紅（D3 整段 11 次 1 次、D1 真實回覆 98 案次 1 次；第 17.6 節）。CI 紅了先看是不是這兩個；要不要改成「超過門檻時
  再量一次」（固定最多兩次，門檻本身不變）會改變門檻怎麼判，要使用者同意，本片沒做。D3 那一次在請求端，和 Q4 一起看。
- `claude-delivery` 現在是 `f4c7718`（HM-11 #107 等已合併；本片照交辦以 `df686dd` 為基準）。開 PR 前要再 rebase：本片在契約第 9 節沒有列，
  文件衝突只會在契約第 10 節與 `decisions.md` 變更紀錄的最後一列（第 16.14 節已預告）。2026-11-17 已 rebase 到 `7646f0f`（HM-12 #110 也已合併，第 18 節）。

**交給後面的片**（第 16.14 節之外再加）：

- HM-18（DOCS）：第 16.14 節「一次湧入」那句照舊成立（帳上最多約 800／416 MiB）；另補「實際記憶體比帳上多約 1.3～1.4 倍（本機預設帳號帳上
  792 MiB 時 RSS 多約 1.1 GB）」與「一個帳號的大回覆會讓別的帳號的回覆等它處理完（本機最久約 7 秒；小主機數倍）」。
- HM-19c（量測清單補）：
  - 比對 MemAvailable 用 RSS 的數字：一次湧入預設帳號帳上 792 MiB 時 RSS 增量 1,088 MiB、額外帳號 408 MiB 時 536 MiB（emoji）；一筆回覆的
    放大用 27.6 倍。
  - J1900 上量沒有物件也沒有數字的陣列（短字串、空陣列）的停頓（Q1）、真實回覆時 B 的 p95（Q2）、一筆的處理時間（空陣列、小整數最久）。
  - 長時間大回覆時看 RSS 會不會一直長（循環回收器在工作期間是整個程序都關著，S-5）。
  - D3 整段在目標硬體的數字；CI 的數字。
- 第 16.14 節最後一點「D1、D3 的程式還沒審查過」：第二輪審查已審（就是本節的報告）。

## 18. rebase 到 claude-delivery `7646f0f` 與使用者對 Q1、Q2、Q4 的回答（2026-11-17）

第 1～17 節照當時寫，裡面的 commit 編號是這次 rebase 前的（對照在第 18.9 節）。數字以本節為準。`SP:`＝這次工作的暫存區（不進 repo）：`SP:hm30r5/`。

### 18.0 結論

- **rebase 做完**：基準換成 `claude-delivery` `7646f0f`（HM-11 #107、HM-12 #110 合併後）。本片 34 個 commit 照原順序重放：22 個完全相同，
  10 個有衝突，2 個只差上下文（第 18.2 節）。
  - 衝突都是兩邊在同一處各加東西：新基準的行照原文在前，本片的行照原文在後。只有 HM-31 的參數順序測試，兩邊的斷言要合成一個。
  - 兩個方向逐檔比對：HM-11、HM-12 的行一行都沒少；本片的行只差衝突那幾行；HM-31、HM-09 追補照舊都在。
  - 帳本照 JSON 重組、SHA-256 照檔重算；當資料核對 0 個問題，帳本預檢 OK（第 18.3 節）。
- **語意衝突：沒有，程式不用改**（第 18.4 節）。HM-12 換身分在發布那一刻結束舊 token 的每個請求；本片在工作執行緒上等的那段也在同一個
  租約裡：排隊的工作撤回、處理中的結果丟掉，名額與待送回覆位元組都還回來，新 token 不受影響。暫存區實驗 X12 三案都過：舊 token 的請求在
  存檔開始後 0.015～0.019 秒結束（401，沒有回覆內容），不等工作執行緒。
- **使用者 2026-11-17 03:1x 回答 Q1、Q2、Q4**：Q1、Q2 接受，Q4 維持現狀，都是 HM-19c 實測再定；門檻都沒放寬。已寫進 `decisions.md`、契約、
  威脅模型、驗收表、本筆記與 PR 說明（第 18.6 節）。
- **本機檢查**（第 18.7 節）：本片 4 檔 251 案、相關 28 檔 836 案、HM-12 的 3 檔與 HM-11 的面板形狀 87 案、`test_output_schemas.py` 189 案
  全過；全套 6,211 案只有 7 個要 root 的既有案例紅、0 skip；packaging、工具表面、兩個預檢都過；雙向控制字元與 AI 署名都沒有。
- **量停頓的測試**（rebase 後的 head，各單獨跑 5 次；門檻與次數照舊，沒有重試；第 18.8 節）：D1 真實 8 MiB 回覆 70 案次全綠，最高 42.7 ms；
  D3 整段 5 次 29.3～36.9 ms 全綠（本片 4 檔整檔那次 39.5 ms）。這次本機沒有紅（上一輪 D3 11 次紅 1 次、D1 98 案次紅 1 次，第 17.6 節）。
  **CI 紅了先由主對話回報使用者，不放寬門檻、不加重試**。
- 還沒解決：`reply_worker.py` 與 `tests/test_reply_worker.py` 幾處說明仍寫 Q1「待使用者決定」，這次沒改（第 18.6 節）；`checks` 秒數 CI 跑完再補。

### 18.1 範圍與做法

- 先開本機備份分支 `backup/hm30-before-rebase-20261117`（＝`2a74494`，不 push）。`git fetch origin` 後 `origin/claude-delivery`＝`7646f0f`。
  前一輪的 `backup/hm30-before-rebase-20261116`、`backup/hm30-review2-before-rewrite-20261117` 沒動。
- `df686dd` 是 `7646f0f` 的祖先；`git log --oneline df686dd..2a74494` 是本片 34 個 commit，所以直接 `git rebase origin/claude-delivery`。
- 新基準多的是 HM-11（#107，面板）與 HM-12 後端（#110：Odoo 換身分換 token；`gateway.py`、`products.py`、`backend_edit.py`、
  `identity_fields.py`、`config.py` 的 `Store._write` 多 `poison_before_replace`、`profile_runtime.py` 的 `stop_child`）。兩邊都改過的檔：
  `config.py`、`gateway.py`、`profile_runtime.py`、`tests/test_profile_runtime.py`、`tests/test_request_budget_gateway.py`、契約、
  `decisions.md`、威脅模型、驗收表、帳本。
- 指令：`git -c merge.conflictStyle=diff3 rebase --exec <帳本檢查> origin/claude-delivery`。每個重放的 commit 之後，若它動了帳本，就核對
  「上一個 commit 的帳本＋原 commit 加的那段說明，列管檔的 SHA-256 照當下的檔重算」，不符就停下（`SP:hm30r5/bin/ledger_exec.sh`、
  `ledger_rebuild.py`；紀錄 `SP:hm30r5/logs/ledger-exec.log`）。
- 依賴（`uv.lock`、`package-lock.json`）沒變，沒有重跑 `setup_repo_env.sh`。
- PaaS（本機唯讀 repo，沒有 fetch、沒有 checkout）：`origin/main` 現在是 `48f394d`。`7087280` 之後只多 #156（Hermes 排程工具的說明），
  `packages/mcp-admin-core/` 與 `docs/mcp-gateway-limits.md` 都沒動，對本片沒影響。

### 18.2 衝突與處理

原則照交辦：新基準的行照原文在前，本片的行照原文在後；同一段程式兩邊都改時，兩邊的行為都留。10 個 commit 有衝突，都是兩邊在同一個
地方各加東西；只有一處要把兩個斷言合成一個（`3261b95`）。

| rebase 後（原本） | 衝突 | 處理 |
|---|---|---|
| `f4271f9`（`15bc2a3`） | `tests/test_profile_runtime.py`：`make_apps` 的 keyword-only 選項清單 | HM-09 `child_blocked`、HM-12 `stop_child`（新基準）之後接本片的 `reply_worker`。同檔另一處（「runtime 拒絕不是自己的選項」清單）自動合併：本片加 `reply_worker`；HM-12 當初沒把 `stop_child` 加進那份清單，照 HM-12 寫的留著 |
| `c7ff421`（`e83889d`） | `gateway.py` 三處、`profile_runtime.py` 兩處 | `gateway.py`：`make_apps` 簽名 `body_budget` → HM-12 `stop_child` → 本片 `reply_worker`；說明 HM-12 那段之後接本片那段；參數檢查 HM-12 的 `invalid child stop` 之後接本片的 `invalid reply worker`。import 自動合併（本片的 `from .reply_worker import …` 在前；HM-12 的 `log_id`、`logger`、`NEW_ORIGIN_SECRET`、`REBIND_WARNING` 在後）。`profile_runtime.py`：模組說明 HM-12 那段之後接本片那段；`RUNTIME_OPTIONS` 是 `'body_budget', 'stop_child', 'reply_worker'`；其他處（`ProfileRuntime`、`ProfileManager` 的 `reply_worker`）自動合併，HM-12 的 `stop_child` 方法與交給 `make_apps` 的那一行沒動。`config.py` 自動合併：HM-12 改 `Store._write`、本片改 `strict_json`，不在同一處 |
| `9e0df89`（`307f998`） | 契約第 10 節、威脅模型狀態行、帳本 | 契約：新基準 HM-11 三列、HM-12 三列之後接本片那列。威脅模型：HM-12 兩行之後接本片那行。帳本：第 18.3 節 |
| `48850f1`（`4382ac8`） | 契約第 9 節說明段、第 10 節 | 說明段：HM-11、HM-12 兩行之後接「#17 的附註出自 HM-30 的實作」。第 10 節：新基準六列之後接本片那列（本 commit 改過的版本） |
| `779fbeb`（`d5f2e03`） | 威脅模型狀態行 | HM-12 兩行之後接本片那行（本 commit 改過的版本） |
| `3261b95`（`52926ae`） | `tests/test_request_budget_gateway.py`：`make_apps` 最後的參數 | 新基準釘「最後 5 個＝…、`body_budget`、`stop_child`」，本片釘「最後 5 個＝…、`body_budget`、`reply_worker`」。兩個選項都在之後，原文的兩個斷言不能同時成立，合成一個：最後 6 個＝`child_blocked`、`default_endpoint`、`bootstrap_fields`、`body_budget`、`stop_child`、`reply_worker`。HM-12 那行註解照留（行尾多一個逗號），加一行本片的註解。HM-12 自己的 `stop_child` 選項測試（`test_odoo_identity_rotation.py`）不看位置，不用改 |
| `3caa49c`（`85324e8`）、`d080a8d`（`5f61a94`）、`07cfce2`（`9331fe1`） | 帳本 | 第 18.3 節 |
| `586e423`（`f548912`） | `decisions.md` 變更紀錄 | 新基準 HM-11、HM-12 兩列之後接本片那列 |
| 其他 24 個 | 沒有衝突 | 其中 `b919f7b`（`086159f`）、`0c06236`（`9fa8f89`）只有上下文不同（HM-12 的 import、新基準加的列），自己的增刪行和原本相同 |

**核對**（`SP:hm30r5/logs/`）：

- `git range-diff df686dd..2a74494 origin/claude-delivery..HEAD`：22 個完全相同、12 個有差（上表 10 個衝突加 2 個只差上下文）。
- `compare.py`（逐檔比兩個 diff 的增刪行，同第 16.3 節）兩個方向：
  - 本片的改動（`df686dd..2a74494` 對 `origin/claude-delivery..HEAD`）：21 檔裡 16 檔逐行相同；其餘 5 檔只差上表那幾行（`gateway.py` 8 行、
    `profile_runtime.py` 4 行、`tests/test_profile_runtime.py` 4 行、`tests/test_request_budget_gateway.py` 10 行：清單尾端的逗號、說明字串結尾的引號移到本片那段之後、合成的斷言；
    帳本 24 行是 SHA-256 與說明）。
  - 新基準的改動（`df686dd..origin/claude-delivery` 對 `2a74494..HEAD`）：39 檔裡 34 檔逐行相同；其餘 5 檔就是上面那 5 檔、同樣幾行。HM-11 的面板
    （`packages/mcp-admin-ui/` 15 檔與 `packaging/ha_p9_admin.mjs`）、HM-12 的 `products.py`、`backend_edit.py`、`identity_fields.py`、`config.py` 的 `Store._write` 與 3 個新測試檔
    一行都沒少。HM-31、HM-09 追補的程式在 `df686dd` 就有：本片對新舊兩個基準的增刪行相同（上一點），所以它們的行也和 rebase 前一樣都在。

### 18.3 帳本（`docs/provenance/runtime-patches.json`）

- 以新基準的帳本為底：HM-11 加了 `profiles.js` 一列，HM-12 改了 6 列（`gateway.py`、`config.py`、`profile_runtime.py`、`products.py`、
  `backend_edit.py`、`identity_fields.py`）的說明與 SHA-256。不解文字衝突，照 JSON 重組（`SP:hm30r5/bin/ledger_rebuild.py`）：
  - 原 commit 只在列尾加字的：把那段接在底的文字後面（新基準的在前、本片的在後）。
  - 新列 `reply_worker.py` 照原位置（`profile_runtime.py` 後面）。
  - SHA-256 照重放當下的檔重算。
  - `5f61a94` 改的是本片自己加的 `access.py` 那句（不是在尾端加字）：把本片那段換成改過的版本。新基準沒動 `access.py`，結果和原 commit
    逐字相同。
- 動帳本的 6 個 commit：4 個有衝突（`307f998`、`85324e8`、`5f61a94`、`9331fe1`），2 個自動合併（`22409db`、`9f1facc`）；6 個重放後都由
  exec 檢查核對過（`SP:hm30r5/logs/ledger-*.txt`、`ledger-exec.log`）。
- 重放完再當資料核對一次（`SP:hm30r5/bin/ledger_verify.py`）：64 列＝新基準 63 列＋`reply_worker.py`；每列的說明＝新基準的文字＋本片在
  `df686dd` 之後加的那段（6 列有本片的字）；其他欄位照新基準；順序照新基準；每列的 SHA-256＝HEAD 的檔。0 個問題。
- 這次沒有改任何列管檔的內容（衝突只動清單、說明與測試），所以帳本沒有新加說明；SHA-256（前 12 碼）：

| 列管檔 | `df686dd` | `claude-delivery` `7646f0f` | rebase 前 `2a74494` | 現在 |
|---|---|---|---|---|
| `gateway.py` | `1f954cf11cde` | `84e331a9006f` | `fc83f7d81eb8` | `92cb8313a108` |
| `config.py` | `78a2f79d76fd` | `c00cae167d7e` | `01bcc791acc2` | `e58eb2299557` |
| `profile_runtime.py` | `048e73896820` | `198afd436a3b` | `60f27add408c` | `012bc7ba24d7` |
| `profile_router.py` | `bb6b6feb79f3` | 同左 | `ebcf83324658` | 同左 |
| `reply_worker.py`（本片的新列） | — | — | `00b7f14a1365` | 同左 |
| `run_product.py` | `59d281b17549` | 同左 | `78d511c9b82e` | 同左 |
| `access.py` | `5d78bcea515e` | 同左 | `0a830599e82d` | 同左 |

- 沒動 `apps/runtime/*.py`、`apps/*/launch.py`：不用 `tool_inventory.py --write`；`scripts/tool_inventory.py` 檢查 exit 0。
- `redact.py` 照舊沒列管，帳本預檢照預期列成「沒列管、要人看」。

### 18.4 語意衝突：HM-12 換身分 × 本片（回覆工作執行緒、待送回覆額度、名額）

**結論：沒有語意衝突，程式不用改。** 兩邊靠的是同一套 token 租約（HM-08 的 `TokenLease`）：HM-12 在發布（`token_access.committed()`）
那一刻結束舊 token 的每個請求，本片在工作執行緒上等的那段也在同一個租約裡。

逐項讀程式（HM-12 的順序：停舊子程式 → 一次寫入新連線、新 token → 發布 → 起新子程式；`gateway.make_apps` 的 `rebind_identity`）：

| 情況 | 會怎樣 | 依據 |
|---|---|---|
| 換身分時，同一個帳號有一筆大回覆在工作執行緒上處理、另一筆在它的佇列裡 | 停舊子程式的那段 `await` 期間舊 token 還有效：這時處理完的回覆照常交出（是換身分之前問、之前讀完的）。寫入與發布之間沒有 `await`，迴圈上沒有東西插得進來。發布時租約的 event 被設起，舊 token 的每個租約立刻結束：排隊的工作撤回（沒跑過），處理中的那筆做完、結果丟掉；用戶端拿到 401／404（回應還沒開始），拿不到回覆內容 | `gateway.serve` 用 `lease.run(lambda: reply_worker.run(...))` 等工作執行緒；`ReplyWorker.run` 被取消時撤回排隊的工作、立刻往上丟，不等處理中的那筆；`TokenAccess.committed()` |
| 處理中的那筆還佔著工作執行緒 | 最多一筆：新 token 的第一個回覆可能要等它做完（結果會被丟掉）。和 Q2 是同一個上界 | 每帳號同時最多 1 筆；帳號的 `Lane` 屬於帳號，換身分不換 runtime、不換 `Lane` |
| 待送回覆額度 | 額度是每帳號的（`ProfileGate`），不是每個 token 的，換身分後還在。舊 token 已交給 server 的回覆：發布時那些請求結束（HM-14 的 ending；用戶端不讀時最多 `ENDING_SECONDS`＝2 秒），請求結束時帳號扣著的（交出的與提早扣的）都還回去；提早扣（`PENDING_CHARGE`）只在工作執行緒交回結果之後才做，被取消的請求不會扣。所以新 token 不會因為舊 token 的回覆被擋成 `-32003` | `ProfileGate.serve` 的 `finally`；`access.LeasedResponse`、`gateway.Ending` |
| 轉送名額（HM-14） | 舊 token 的請求被取消時在 `finally` 放掉名額；排隊等名額的那個拿到名額後先重驗 token、被拒（HM-12 的測試已釘住）。本片在拿到名額之後的第二次待送回覆檢查（第二輪審查 MF-2）只在 token 還有效時才走得到 | `gateway.serve` |
| D3 的 `checked` 租約（每段只查一次 token） | 發布設起 event，watcher 立刻醒。HM-12 失敗、沒有發布的兩種情況（取代 state 檔途中失敗：store 毒化；寫入丟例外但新 token 已在磁碟上）：每一段讀完之後的那次檢查讀 store，拿到 `ConfigError` 或不同的 token，這一段就不交出（第 16.8 節的規則，HM-12 不用另外處理） | `TokenLease.run`、`invalidated` |
| 停舊子程式 | 工作執行緒不碰子程式；已讀完的回覆照常處理；還在讀的那段因子程式斷線結束（HM-14 的 `-32004`），和本片無關 | `ProfileRuntime.stop_child` |
| 別的帳號 | HM-12 只停、寫、起 B 自己的；A 在工作執行緒上的那筆照常做完、照常交出 | — |

**HM-12 的測試現在也走工作執行緒**：`tests/multi_profile_runtime.py` 開著開關跑 `run_product`，rebase 後 `run_product` 會建工作執行緒，所以 HM-12
那 3 個測試檔裡經過 8081 的回覆都在工作執行緒上處理；它們全過（第 18.7 節）。

**暫存區實驗 X12**（沒進 repo；`SP:hm30r5/exp/test_zz_hm12_x_hm30_scratch.py`，在 `815cc2f` 的複本跑；開通的 Odoo、HM-12 測試的 `Journal`
記順序、讓工作執行緒卡在某一筆的解析上）：

| 實驗 | 情境 | 結果 |
|---|---|---|
| X12a | B 的一筆 2 MiB 回覆卡在工作執行緒上（處理中），B 的另一筆排在它的佇列裡；這時經 8099 用 `backend/patch` 改 B 的 username | 存檔 0.018 秒回 200（`token_rotated`）；兩個舊 token 的請求在存檔開始後 0.019 秒都結束：401、26 位元組，沒有回覆內容，那時工作執行緒還卡著。順序 stop → write → publish → start。放開之後，工作執行緒只多做了卡著的那一筆（結果丟掉）與新 token 的一筆，排隊的那筆沒跑過。B 的待送回覆位元組、准入、名額與排隊都歸零；舊 token 兩條入口都被拒；新 token 的 tools/call 經工作執行緒回 200、位元組正確 |
| X12b | 預設帳號的一筆卡在工作執行緒上，B 的一筆排在後面；改 B 的 username | B 的舊 token 請求 0.015 秒結束（401）；預設帳號那筆放開後照常 200、逐位元正確；B 的那筆沒跑過；兩個帳號的待送回覆位元組與准入都歸零；B 的新 token 照常 |
| X12c | B 的待送回覆額度縮成 1 MiB，兩個 600 KiB 的舊 token 回覆被不讀的用戶端扣著（帳上 1,228,800 位元組，下一個 tools/call 回 `-32003`）；改 B 的 username | 兩個舊 token 的回應在存檔開始後 0.016 秒結束（HM-14 的 ending：標頭已送、本體一段都沒送出，閘道就此結束、伺服器關連線）；B 帳上歸零；新 token 的 tools/call 照常轉送、回 200、614,400 位元組，不是 `-32003` |

3 案全過（`SP:hm30r5/logs/s1/x12.log`）。

### 18.5 契約第 9、10 節

- 第 9 節：本片仍沒有自己的列（差異都在 #17 的附註）。HM-11 的 #109～#112、HM-12 的 #113～#115 照新基準，最後仍是 #115；這次沒有要加的列。
- 第 9 節說明段：新基準的兩行（HM-11、HM-12）在前，「#17 的附註出自 HM-30 的實作」在後。
- 第 10 節：新基準的列（HM-11 三列、HM-12 三列）在前，本片的四列在後；最後再加一列（本次 rebase 與 Q1、Q2、Q4）。

### 18.6 使用者對 Q1、Q2、Q4 的回答（2026-11-17 03:1x；門檻都沒放寬）

| # | 題目（第 17.10 節） | 使用者的回答 | 之後 |
|---|---|---|---|
| Q1（第二輪審查 MF-1） | 沒有物件也沒有數字的大陣列，解析是一次 C 呼叫（本機 8 MiB 0.03～0.19 秒） | **接受，HM-19c 實測再定** | HM-19c 在 J1900 量；超標再從「開通時回覆也設元素個數上限」或「子程序處理回覆」選一個。測試照舊只印不斷言 |
| Q2（第二輪審查 MF-4） | 大回覆分段後別的帳號等更久（本機 B 的 p95 3.5 秒，不分段 1.9 秒；一筆 8 MiB 最久約 7 秒） | **接受，HM-19c 實測再定** | HM-19c 用真實回覆量 B 的 p95；過不了再改成工作執行緒在分段之間換帳號 |
| Q4（第二輪審查 S-2） | 請求端的大請求在主迴圈解析（本機一個 0.09～0.25 秒） | **維持現狀，HM-19c 實測再定** | 超標再從「請求端交給工作執行緒」或「開通時降低單一請求上限」選一個 |

寫在哪裡：

- `decisions.md` 第 1.1 節加三列（照 D1～D3 那幾列的寫法，記成使用者 2026-11-17 03:1x 定案），變更紀錄加一列。
- 契約第 6 節：D1～D3 那段之後加「第二輪審查回報後的使用者定案」一段（含「量停頓的測試門檻、次數都不改，也不加重試；CI 紅了先由主對話
  回報使用者」）；D1 的兩處（一筆變長別的帳號等得也久、沒有物件也沒有數字的陣列）與量測表三列（整段、真實回覆時 B 的延遲、真實 8 MiB
  回覆）的「待使用者決定」改成定案。第 10 節加一列。
- 威脅模型：狀態行補一句；I8 的測試欄、第 3 節三條（請求端 CPU、別的帳號等 A 的一筆、沒有物件也沒有數字的陣列）的「待使用者決定」改成定案。
- 驗收表：`test_reply_worker.py` 那列的「（MF-1，待使用者決定）」改成定案。
- 本筆記：結論、第 1 節的表、第 17.0、17.10 節標明已答。PR 說明（repo 外 `wave4/pr-HM-30.md`）：「合併前要使用者決定」改成已答。
- 計畫 §12.3 HM-30 已由主對話寫進同樣的定案（repo 外，本片沒改計畫）。
- 沒改的：`reply_worker.py` 模組說明第 57 行（「HM-30 review 2 Q1, the user's to decide」）與 `tests/test_reply_worker.py` 幾處說明
  （「until the user decides」）。交辦只列了文件；改說明字串就要動列管的程式、重算帳本，量過的程式也跟著變。行為不變（照舊只印不斷言），
  交主對話決定要不要之後順手改（第 18.10 節）。

### 18.7 本機檢查（2026-11-17，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪除；pytest 都排在共用鎖後面）

- pytest 除了全套與 `test_output_schemas.py`，都在 repo 外的複本跑（`git archive 815cc2f`，`.venv`、`apps/`、`packages/mcp-admin-ui` 連回
  clone；`SP:hm30r5/bin/snap.sh`）。`815cc2f` 是 rebase 後的 head；之後的兩個 commit 只改文件，量過的程式就是最後的程式。
- 一次取鎖（04:28～05:13；`SP:hm30r5/bin/session1.sh`，紀錄 `SP:hm30r5/logs/s1/`）。每次 pytest 一個程序。

| 檢查 | 範圍 | 結果 |
|---|---|---|
| 本片 4 檔 | `test_reply_worker.py`、`test_health_tolerance.py`、`test_profile_runtime.py`、`test_request_budget_gateway.py` | **251 案全過**、0 skip、95.5 秒（147＋2＋65＋37；`test_reply_worker.py` 61.2 秒、`test_health_tolerance.py` 15.6 秒） |
| 相關 28 檔（第 17.8 節同一組） | HM-31 預算與結構 3 檔、HM-14 的 5 檔＋`test_reply_mask_union.py`、HM-10 的 3 檔、`test_monitor_cancel.py`、HM-01 黃金回歸與兩個契約凍結、額度、路由、生命週期、健康退避、租約、後端錯誤、遮罩矩陣、錯開啟動、port、子程式資源、SSE 錯誤遮罩、Nextcloud 秘密 | **836 案全過**、0 skip、280 秒。HM-01 的三檔 45 案（17＋9＋19，三檔與 `tests/contract/` 沒改）；HM-31 的 3 檔 206 案（61＋83＋62）；`test_monitor_cancel.py` 13 案 |
| HM-12 的 3 檔、HM-11 的面板形狀 | `test_odoo_identity_rotation.py`、`test_odoo_multi_profile.py`、`test_new_origin_secret.py`、`test_panel_profile_api_shapes.py` | **87 案全過**、9.5 秒（33＋3＋41＋10）。HM-12 的測試開著開關跑 `run_product`，回覆都經工作執行緒（第 18.4 節） |
| `test_output_schemas.py`（在 clone 裡跑：它對 repo 跑 git） | | **189 案全過**、1.6 秒 |
| 暫存區實驗 X12 | 3 案 | 全過（第 18.4 節） |
| D1 真實 8 MiB 回覆 | 14 案＋短字串清單（只印），單獨 5 次 | 75 案次全過，第 18.8 節 |
| D3 整段 | CPU 飢餓一案，單獨 5 次 | 5 次全過，第 18.8 節 |
| 全套 pytest（clone，`packaging/unit.sh` 的同一組 pytest 指令，一般使用者；Chromium 是 clone 裡照 CI 裝的那份） | `pytest tests` | **6,211 案：6,204 過、7 紅、0 skip**，34 分 32 秒（程式是 `815cc2f` 的；跑的期間 clone 多了 `f27c7dd`，只改文件）。7 紅＝已知要 root 的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 的 5 個 `test_root_*`；訊息都是「需要 root」，uid 是 1000）；`packaging/check_results.py` 因這 7 案照預期 exit 1。2 個警告是既有的 websockets 棄用警告。本片的檔在大程序裡也都過（`test_reply_worker.py` 147 案 70.7 秒、`test_health_tolerance.py` 2 案 15.5 秒；量停頓的案例都在 50 ms 內）；HM-12 的 3 檔、HM-11 的面板形狀、`test_output_schemas.py`、HM-01 的三檔、HM-31 的 3 檔、`test_monitor_cancel.py` 也都過 |
| `packaging/validate.py`（CI 的 venv） | | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（離線暫存 venv：`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt` 雜湊安裝） | `unittest discover -s packaging -p 'test_*.py'` | `Ran 203 tests`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py` | | exit 0（沒動 `apps/runtime/*.py`、`apps/*/launch.py`，工具表面不用重產） |
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗）。HEAD `815cc2f`：`7646f0f..815cc2f` 34 個 commit＋HEAD 整棵樹＋整個歷史，**0 命中**。HEAD `f27c7dd`：35 個 commit＋HEAD 整棵樹＋整個歷史，**0 命中**。之後只有本 commit（只改本筆記） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | HEAD `815cc2f`：`runtime-patches.json` 177、`runtime-sources.json` 70、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的列管檔 7 個（`access.py`、`config.py`、`gateway.py`、`profile_router.py`、`profile_runtime.py`、`reply_worker.py`、`run_product.py`）都有帳本更新；沒有沒列管的新執行檔；`redact.py` 照預期列成「沒列管、要人看」：**OK**。HEAD `f27c7dd` 同樣 OK（177／70／159 檔，0 漂移、0 缺）。之後只有本 commit（只改本筆記） |
| 雙向控制字元、署名、身分 | `origin/claude-delivery..HEAD` 每個 commit：訊息，與它新增或改的每個檔在那個 commit 的全文（`SP:hm30r5/bin/bidi_check.py`） | HEAD `f27c7dd`：35 個 commit、74 個檔版本，**0 個**雙向控制字元（U+202A～202E、U+2066～2069）；commit 訊息沒有 AI 署名（沒有 Co-Authored-By、Generated with）；作者與 committer 都是 woowtech。英文標題、繁中內文 |
| `git status`、暫存目錄 | | 只有還沒 commit 的本筆記。這一段用過的 17 個 `/tmp/ha-mp-*` 都已用完整路徑刪除（`SP:hm30r5/tmpdirs.txt`、`tmpdirs-deleted.txt`）；別的代理的暫存目錄沒動 |

### 18.8 量停頓的測試（rebase 後的 head `815cc2f`，各單獨跑 5 次；門檻 50 ms、次數照舊，沒有重試）

**D1 真實 8 MiB 回覆**（`test_a_real_8_mib_reply_is_the_loops_bytes_and_stops_the_loop_briefly` 14 案，加只印的短字串清單；每次一個 pytest
程序；迴圈延遲探針每 2 ms 取樣；單位 ms）：

| 形狀 | 工作執行緒那條路的迴圈最長停頓（單獨 5 次） | 本片 4 檔整檔那次 | 一筆的時間（單獨 5 次） | 同一筆在迴圈內處理 |
|---|---|---|---|---|
| mixed | 31.2、32.5、41.0、30.9、19.4 | 40.8 | 0.66～0.72 秒 | 253～347 |
| 大量小物件 | 14.2、11.5、7.5、12.6、7.4 | 10.9 | 3.4～3.6 秒 | 864～961 |
| CJK | 11.1、10.6、33.4、19.8、12.5 | 11.2 | 0.10～0.14 秒 | 67～71 |
| emoji | 19.2、21.5、19.6、21.6、11.8 | 29.6 | 0.12～0.15 秒 | 83～94 |
| 長 ASCII 字串 | 24.4、19.7、29.5、20.3、26.3 | 15.4 | 0.12～0.13 秒 | 62～68 |
| 跳脫字元 | 18.8、24.3、42.3、**42.7**、25.0 | 26.7 | 0.09～0.12 秒 | 59～65 |
| 64 層巢狀 | 9.2、12.6、12.7、8.9、7.8 | 5.6 | 1.5～1.9 秒 | 595～605 |
| ID 清單 | 7.5、5.6、5.6、5.5、8.9 | 5.5 | 1.4～1.5 秒 | 267～314 |
| 小整數 | 7.3、8.7、7.1、8.1、8.1 | 10.9 | 3.8～4.3 秒 | 724～757 |
| `[[ts, 整數]]` | 7.6、9.2、7.3、5.7、7.3 | 7.0 | 2.4～2.9 秒 | 572～625 |
| `[[ts, 浮點]]` | 10.9、6.1、5.8、8.0、6.7 | 7.3 | 2.6～3.0 秒 | 790～842 |
| 浮點數 | 12.0、9.2、8.4、10.2、8.0 | 10.1 | 3.0～3.1 秒 | 984～1,020 |
| mixed（事件） | 16.4、20.2、27.9、23.9、16.0 | 25.3 | 0.76～0.79 秒 | 285～300 |
| emoji（事件） | 39.0、22.2、30.6、23.0、11.5 | 30.0 | 0.23～0.27 秒 | 140～143 |
| 短字串清單（只印，Q1） | 94.6、98.5、92.8、97.0、90.0 | 81.8 | 1.8～2.2 秒 | 471～494 |

- 斷言的 14 案：單獨 5 次 70 案次＋整檔 1 次 14 案，**全在 50 ms 內，0 次紅**。最高 42.7 ms，仍是跳脫字元多的長字串（解析端那一次 C 呼叫，
  第 17.2 節）；離門檻約 7 ms。
- 短字串清單照舊只印不斷言（使用者 Q1：接受，HM-19c 實測再定）：81.8～98.5 ms。
- 上一輪（第 17.2、17.6 節）98 案次紅 1 次（浮點數 50.5 ms）；這次浮點數 8.0～12.0 ms。

**D3 整段**（`test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace`；整段＝讀取期間與處理期間的最大值；單位 ms）：

| 次 | 整段最長 | 讀取期間 | 處理期間 | 注入成本一次 C 呼叫（校準） | B 的 p50／p99 |
|---|---|---|---|---|---|
| 1 | 31.2 | 31.2 | 18.2 | 10.0 | 276／309 |
| 2 | 36.9 | 36.9 | 21.1 | 10.3 | 256／297 |
| 3 | 33.3 | 33.3 | 25.5 | 5.7 | 147／323 |
| 4 | 36.0 | 36.0 | 16.1 | 9.2 | 243／300 |
| 5 | 29.3 | 29.3 | 15.9 | 9.8 | 239／299 |
| 本片 4 檔整檔那次 | 39.5 | 39.5 | 17.5 | 7.2 | 273／319 |

- **6 次都綠**：整段最長 29.3～39.5 ms，最長的都在讀取期間（32 個請求同時進來時閘道的請求端工作，第 17.6 節；Q4 的範圍）；處理期間
  15.9～25.5 ms；B 的 p99 297～323 ms（≤0.7 秒）。注入成本的校準在機器忙時偏短（第 3 次 5.7 ms），照舊記下。
- 上一輪 11 次紅 1 次（63.3 ms，讀取期間）；這次 0 次。
- 本機是多個代理共用的 EPYC 7713（這段期間 load average 約 20～37，`SP:hm30r5/logs/s1/session.log` 每次都記）。
- **門檻、次數都沒改，沒有重試**。照使用者 2026-11-17 的定案：CI 紅了先由主對話回報使用者，不放寬門檻、不加重試；要不要改成「超過再量
  一次」等 CI 有數字再問。

### 18.9 commit 對照

rebase 過來的 34 個（第 1～17 節寫的是左欄的編號；內容見第 16.13、17.10 節）：

| rebase 前 | 現在 | range-diff | rebase 前 | 現在 | range-diff |
|---|---|---|---|---|---|
| `15bc2a3` | `f4271f9` | 有衝突 | `6601e9b` | `5b6e66c` | 相同 |
| `e83889d` | `c7ff421` | 有衝突 | `086159f` | `b919f7b` | 只差上下文 |
| `c2c764d` | `cfd8288` | 相同 | `ebc15a2` | `850340d` | 相同 |
| `307f998` | `9e0df89` | 有衝突 | `85324e8` | `3caa49c` | 有衝突 |
| `b6a2c85` | `2e75428` | 相同 | `179a080` | `e46d3a4` | 相同 |
| `2dc496e` | `ddb92fd` | 相同 | `5f61a94` | `d080a8d` | 有衝突 |
| `4382ac8` | `48850f1` | 有衝突 | `cb93e08` | `2f615cb` | 相同 |
| `bcd0628` | `1f7b905` | 相同 | `9f1facc` | `fa13613` | 相同 |
| `22409db` | `896f694` | 相同 | `f548912` | `586e423` | 有衝突 |
| `d5f2e03` | `779fbeb` | 有衝突 | `d853c3e` | `612c19f` | 相同 |
| `dfd0766` | `f14ceeb` | 相同 | `37160d6` | `3f0fa99` | 相同 |
| `a4c42a5` | `2ff8d77` | 相同 | `fb0b0e6` | `14d00cc` | 相同 |
| `773014a` | `7582ca9` | 相同 | `a02b108` | `4305c80` | 相同 |
| `360efd0` | `abfd9d8` | 相同 | `a22a97f` | `c28fff0` | 相同 |
| `52926ae` | `3261b95` | 有衝突 | `9331fe1` | `07cfce2` | 有衝突 |
| `dd1098f` | `da6f6dc` | 相同 | `9fa8f89` | `0c06236` | 只差上下文 |
| `6481f7f` | `a5e9902` | 相同 | `2a74494` | `815cc2f` | 相同 |

rebase 之後加的：

| commit | 內容 |
|---|---|
| `f27c7dd` | 文件：契約、威脅模型、`decisions.md`、驗收表（使用者對 Q1、Q2、Q4 的定案；量測表補 rebase 後的數字；契約第 10 節、`decisions.md` 變更紀錄各一列） |
| 最後一個 | 本筆記：第 18 節，與結論、第 1、17.0、17.10 節的更新 |

### 18.10 交給後面的片與主對話

- **主對話**：
  - CI 紅了先看是不是量停頓的兩個測試（D1 真實回覆、D3 整段）。照使用者 2026-11-17 的定案先回報使用者，不放寬門檻、不加重試。
  - `checks` 秒數：CI 跑完再補（PR 說明最後一行）。
  - `reply_worker.py` 模組說明第 57 行與 `tests/test_reply_worker.py` 幾處說明仍寫 Q1「待使用者決定」（第 18.6 節）。行為就是使用者定的
    「只印不斷言、HM-19c 實測再定」；要不要之後順手改說明字串（要重算 `reply_worker.py` 的帳本），由主對話決定。
  - 開 PR 時 `claude-delivery` 是 `7646f0f`。之後若別的片先合併（HM-12 面板、HM-13c、HM-32 等），後合的那片 rebase 時和本片會碰到的地方：
    契約第 9 節說明段與第 10 節、`decisions.md` 第 1.1 節與變更紀錄、威脅模型狀態行、帳本（`gateway.py`、`profile_runtime.py`、`config.py`
    的說明尾端）、`make_apps` 參數順序的兩個測試（`test_request_budget_gateway.py`、`test_profile_runtime.py`；本片的 `reply_worker` 現在
    是最後一個參數）。
- **HM-19c**：清單照第 16.14、17.10 節。Q1、Q2、Q4 都是「HM-19c 實測再定」，都已在清單裡：沒有物件也沒有數字的陣列（短字串、空陣列）的
  停頓（Q1）、真實回覆時 B 的 p95（Q2）、請求端一個大請求的停頓（Q4）。超標時的選項寫在第 18.6 節與 `decisions.md` 第 1.1 節。
- **HM-18**：照第 16.14、17.10 節。
- **HM-12 交來的事**：換身分與工作執行緒、待送回覆額度、名額之間沒有要後面的片處理的事（第 18.4 節）。
