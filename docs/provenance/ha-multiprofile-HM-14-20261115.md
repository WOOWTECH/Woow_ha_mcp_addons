# HA 多帳號 HM-14 provenance：閘道收尾對齊 PaaS #148（2026-11-15；審查修正、rebase 2026-11-16）

## 結論

- **產品沒開通時，回應的形狀和今天相同，只有一個例外**：子程式回的 initialize 錯誤現在會遮本帳號的憑證（不受開關管，理由與範圍見
  `docs/multi-profile/contract.md` 第 1.2 節）。轉送名額逾時仍是 503 `{"error":"request denied"}`、子程式斷線仍是 502
  `{"error":"request denied"}`、SSE 斷線仍安靜結束、token 換掉時仍把 `ClientDisconnect` 丟給 uvicorn；沒有排隊上限、沒有保留名額、
  不看排隊中斷線（程式走原本的路徑：`make_apps` 沒拿到 `slot_busy`）。這些回應的位元組都有開關關的測試（第 5 節）。repo 裡的
  `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開），閘道照 PaaS #148（`woow-mcp-server` @`69ac425`，到 main 只改註解、文件與測試）：
  - 轉送名額分兩組：一般名額（預設 32、額外 16）與通知保留名額（4）；**每組各自的排隊上限**（預設 32、額外 16），超過立刻回
    200＋`-32003`（有 id）或 503（沒 id），都帶 `Retry-After: 5`；等 1 秒逾時同形狀；GET 串流滿 429＋`Retry-After: 30`（HM-08 已做）。
  - **排隊中用戶端關閉連線就移除、絕不送出**；名額剛好同一刻空出也還回去、不送（PaaS Q6 的寫入不會在名額空出後被執行）。
  - **保留名額的判斷照 PaaS `_carries_no_request`**（`Pc/proxy.py:336`）與它的 51 個正反例；HA 的政策只轉送 `notifications/initialized`，
    所以實際走保留名額的只有它（§8.8 #90）。
  - **子程式中途斷線改 `-32004`，依原因三種文字**（仍在執行／停止了、會自動重新啟動／停止了、目前沒有在重新啟動；看轉送那一刻的世代，
    最多等 0.25 秒；停止了的兩種看 HM-09 的 `Supervisor.status`，rebase 後加，第 16 節）：標頭前 502＋`-32004`，SSE 補一則同 id 的事件後
    正常結束；帳號 WARNING 一行，不帶 traceback。
  - **標頭後換 token**：SSE 補 `-32005`、正常結束；標頭卡在背壓還沒送出時改送乾淨的 401／404（逐位元同今天的拒絕）；
    **不把 `ClientDisconnect` 丟給 uvicorn**。一次送完的 JSON 標頭已送出時不能改內容（`Content-Length`），閘道返回、連線關掉（§8.8 #91）。
  - **initialize 世代**：session 只在 initialize 送去的世代仍在執行時才交給用戶端，否則 503 `BACKEND_UNAVAILABLE`、不 DELETE。
  - `-32003` 文字定稿：HM-08 的四種照原文，加保留名額與排隊兩種，每種寫那一組自己的條數。
- 已知限制照 PaaS 文件後續（19f36e2、`091dfbc`）寫進契約第 2.4 節與威脅模型第 3 節：SDK 層級的逾時與取消、MCP Python SDK 2.3.0 預設
  `terminate_on_close=True` 的關閉路徑看不到斷線，排隊中的寫入在名額空出後照樣被執行（HA 最多等 1 秒）。審查後再加一條：
  保留名額只在准入還有空位時有用（准入＝轉送＋排隊；MF-2。主對話 2026-11-16 定案：不改 DQ-07 的數值，交 HM-31 改分派器）。
- 測試：新 5 檔 117 案＋1 個測試工具模組，本機 15.5 秒；PaaS 四個測試檔 43 個案例逐案對照（第 4 節）。**先寫測試**：新測試在
  `b5d10c5` 的程式上 117 案 106 失敗（第 6.1 節），程式 commit 之後全過。臨時突變 28 個全部擋下（第 6.2 節）。審查修正再加 11 案
  （4 檔，合計 128 案），先紅後綠與突變見第 15 節。rebase 到 HM-09 之後再加 7 案（合計 135 案），先紅後綠、突變與全套見第 16 節。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 9 節）。全套 pytest 5394 案只剩 7 個要 root 的既有案例（第 7 節）。rebase 後：全套 5531 案只剩 7 個要 root 的既有案例與 22 個這個 clone 沒有 Chromium 跑不了的瀏覽器測試（第 16.7 節），兩個預檢見第 16.9 節。
- **獨立安全審查（2026-11-16）判定「修正後通過」**（第 15 節）：必修 MF-1 加測試；MF-2 寫明並先釘住現況，(b) 由主對話 2026-11-16 定案
  （不改 DQ-07 的數值；准入滿時讓通知走保留名額交 HM-31 改分派器；第 11 節）；建議 S-1～S-6 採用（S-1、S-4 改程式），S-7 只寫明、不改程式。
- **rebase 到 `claude-delivery` `c523474`（HM-09 合併後，2026-11-16；第 16 節）**：`gateway.py` 的 `make_apps` 參數與說明、帳本、契約
  第 9 節與變更紀錄照兩邊意圖合併，三個列管檔的帳本摘要照合併後的內容重算；HM-14 的差異列改成第 90～98 列（HM-09 用了第 89 列），
  引用一起改，再補第 99 列；`-32004` 的「會自動重新啟動」只在 HM-09 的看門狗會再起子程式時說（`blocked`、`failed`、`stopped`、
  `unconfigured` 說目前沒有在重新啟動），加 1 個測試（7 種狀態）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-14（計畫 §12.3；風險中、工作量 L；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm14-20261115`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `c523474`（HM-00～HM-09、13a、17、#100 已合併）；原本是 `b5d10c5`，2026-11-16 rebase（第 16 節） |
| 依據 | 計畫 §5.1、§5.2、§10.3、§12.3 HM-14；契約 §1.2、§2.4、§2.5、§4.2（含「其他既有回應」）、§5、§9；HM-08 審查報告（`artifacts/…/wave3/review-HM-08.md`，S-4 (a)）與 HM-08 筆記第 14.2 節；FM-34、43、44、50、51、52 |
| 對齊的 PaaS | 沒有移植 PaaS 程式。行為與期望值：`Pc/gateway_pool.py`（排隊、保留名額、`_hand_back`、`_watch_client`）、`Pc/proxy.py`（`_carries_no_request`、`_busy_message`、`_child_stopped`、`_Interruption`、`CHILD_*_MESSAGE`、`ACCESS_CHANGED_MESSAGE`）、`Pc/mcp_access.py`（`_finish_interrupted`、`INTERRUPTED_FINISH_TIMEOUT`）、`Pc/initialize_fence.py`（標頭卡在背壓時的拒絕）、`P:docs/mcp-gateway-limits.md`（@`69ac425`，與 main 上 19f36e2、`091dfbc` 的已知限制）；四個測試檔 @`69ac425`（含 main 上 `82c6929` 的測試補強） |
| PaaS clone | 本機唯讀（沒 fetch、沒 checkout）；`origin/main` 寫筆記時是 `5b84b5d`，審查修正與 rebase 時是 `d7f5849`（都是別的流程 fetch 的；見第 10 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/gateway.py` | `SlotBusy`（`make_apps slot_busy` 的型別：排隊上限、保留名額、等候、回答與 WARNING）；`carries_no_request`（PaaS 規則原樣）；`Lane`、`take_slot`（排隊、上限、斷線監看、同一刻的還回）；`client_gone`、`interrupted`、`gateway_event`；`Ending`（token 換掉時閘道自己的結尾）；`OwnedInitializeResponse` 的世代 fence；`make_apps`：開通時兩組名額、`-32004`（標頭前、JSON 讀到一半、SSE 補事件）、`-32005`、initialize 世代、`mcp_app.state.lanes`（給診斷與測試）；initialize 錯誤不論開關都遮（不受開關管） |
| `Hc/access.py` | `Delivery`（回應走到哪：開始送、伺服器收下標頭、最後收下的本體、整個送完）；`LeasedResponse` 多一個 `ending`（沒給時行為不變） |
| `Hc/gateway.py`（審查修正） | 閘道補的 `-32004` 事件記成那個請求的回答（`owner.reply_event`，伺服器收下後 `owner.answered`）：之後換 token 不再補 `-32005`（S-1）；`make_apps slot_busy` 的型別註記改成 `SlotBusy \| None`（S-5） |
| `Hc/gateway.py`（rebase 後） | `CHILD_RESTARTING_STATES`、`CHILD_HALTED_TEXT`、`make_apps` 的 `interruption_text`：子程式停止了時，`-32004` 只在 HM-09 的看門狗會再起它時說會自動重新啟動（第 16.4 節）；rebase 時 `make_apps` 的參數照兩邊合併（`slot_busy: SlotBusy \| None`、HM-09 的 `child_blocked`） |
| `Hc/profile_router.py` | `ProfileGate.slot_busy` 改成 `gateway.SlotBusy`（從帳號的名額組成）；`forward_busy`、`forward_abandoned`、`child_interrupted`（帳號的回答與 WARNING）；`forward_text` 多保留名額、新 `queue_text`；模組說明。審查修正：`MAX_REPORT_KEYS` 64→256（S-4） |
| `tests/switched_gateway.py`（新，測試工具） | 開通的帳號閘道從頭到尾驅動：可操控的子程式替身 `GatewayChild`、手動驅動 ASGI 的 `Exchange`（用戶端離開、不讀）、`quota()`、`supervisor()` |
| `tests/test_carries_no_request.py`（新） | PaaS 的 51 個本體逐一照 HA 的解析分類；只限 POST；端到端：保留名額只載 `notifications/initialized`、其他都在名額前被擋或自答；保留名額滿；保留名額 0 |
| `tests/test_gateway_queue_ha.py`（新） | `take_slot` 的機制（PaaS 案例 8～11、13、15、18、20、23、24，含會記帳的 semaphore）；真 listener 上排隊中放棄的寫入不送（Q6）；用戶端離開立刻出佇列；排隊上限；每帳號 client 放得下名額與保留名額 |
| `tests/test_gateway_busy_shapes.py`（新） | 忙碌回應照 PaaS 表、session 不受影響；文字與 WARNING 寫各組自己的條數（含 WARNING 全文）；initialize 等名額；開關關時一概不適用 |
| `tests/test_gateway_stream_endings.py`（新） | `-32004` 依原因（三種錯誤、停止兩種、晚 50 ms 才看到、GET、JSON 讀到一半、SSE 兩種、log、真的 TCP 重設）；`-32005`（SSE、已送到的回覆不補、標頭卡住的乾淨拒絕、標頭收下同一刻、用戶端完全不讀、只處理換 token）；子程式回錯的東西照舊 502（開關開與關）；開關關的斷線逐位元 |
| `tests/test_initialize_generation.py`（新） | 換代、結束、被停時不交出 session、不 DELETE；正常時逐位元；重啟不等卡住的回應；開關關照舊；initialize 錯誤遮罩（開關關兩案、開關開一案） |
| `tests/test_reply_mask_union.py` | 只改一個說明字串（HM-08 寫「開關關時原樣轉回，留給 HM-14」） |
| 審查修正的測試（4 檔，11 案） | Q：佇列不跨帳號［B 滿｜預設滿］（MF-1）、GET 串流整段佔住一般名額（UC-31，S-3）；C：保留名額只在准入還有空位時有用［15｜16］（MF-2，釘住現況）；E：initialize 回覆讀到一半斷線［仍在執行｜停止了］、`-32004` 之後換 token 不再補 `-32005`、回覆還沒被收下就換 token 要補 `-32005`、最後一則被收下那一刻換 token 之後不再送（S-1、S-2）；B：每帳號每情況 60 秒一行在 6 個帳號、11 種情況下仍成立（S-4） |
| rebase 後的測試（1 檔，7 案） | E：`test_a_stopped_child_is_said_to_restart_only_while_it_comes_back_by_itself`［backoff｜starting｜replaced｜blocked｜failed｜stopped｜unconfigured］：標頭前的 502 與 SSE 事件都驗（第 16.4 節） |
| `docs/multi-profile/contract.md` | 第 1.2 節（不受開關管的 initialize 錯誤遮罩）、第 2.4、2.5 節（HM-14 定案）、第 4.2 節、第 9 節第 90～94 列與 #81、第 10 節。審查修正：第 2.4 節三點（MF-2、UC-31、S-7）、第 2.5 節兩點（S-1、S-5）、第 4.2 節、第 5 節一點、第 9 節第 95～98 列、第 10 節一列。rebase 後：HM-14 的列從第 89～97 列改成第 90～98 列（HM-09 用了第 89 列）、第 2.5 節 `-32004` 三種文字、第 4.2 節 `-32004` 列、第 9 節第 99 列、第 2.4、5 節與 #95 寫明 MF-2 (b) 的定案、第 10 節一列 |
| `docs/multi-profile/threat-model.md` | 第 3 節補兩條已知限制。審查修正：I8 測試欄補佇列不跨帳號（MF-1）、第 3 節補保留名額與准入（MF-2）。rebase 後：第 3 節寫明 MF-2 (b) 的定案與 `-32004` 依子程式狀態的文字 |
| `docs/provenance/runtime-patches.json` | `gateway.py`、`access.py`、`profile_router.py` 重算 SHA-256、補說明。rebase 時以 `claude-delivery` 的帳本為底、照合併後的內容重算；rebase 後 `gateway.py` 再重算一次 |
| 本筆記 | — |

沒改：`profile_runtime.py`、`run_product.py`、`lifecycle.py`、`health.py`、`profiles.py`（`ProfileManager.add` 照舊傳
`slot_busy=gate.slot_busy`，只是它現在是 `SlotBusy`；照計畫 §12.2 的衝突表，HM-14 不碰 HM-09 會改的檔）、`apps/`、`packaging/`、
`addons/<x>/`、版號、CHANGELOG、`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、`decisions.md`（本片用到的決策都已定；
見第 11 節）、`paas-test-mapping.md`、`deviation-trace.md`（兩份由 repo 外的產生器重產，不手改；差異見第 4 節與契約第 9 節的說明）。
FM-52（超過上限先讀完 128 MiB 再回錯誤）是「HM-14 選做」，沒做（契約 #81 註明仍延後）。

## 3. 設計重點

### 3.1 開關怎麼傳進閘道（`make_apps slot_busy`）

- HM-08 已用「`make_apps` 有沒有拿到 `slot_busy`」分開通與沒開通：只有 `ProfileManager`（開通的產品）會給。HM-14 沿用同一個訊號，
  把 `slot_busy` 從「一個回答函式」擴成 `gateway.SlotBusy`（排隊上限、保留名額、等候秒數、回答、兩種 WARNING）。
- `ProfileGate.slot_busy` 從方法改成屬性（`SlotBusy`），`ProfileManager.add` 照舊傳 `slot_busy=gate.slot_busy`：**`profile_runtime.py`
  一行都沒改**。理由：計畫 §12.2 的衝突表裡 `profile_runtime.py` 沒有 HM-14，而 HM-09 會在 `add()` 那一段加看門狗參數；不碰它，HM-14
  rebase 到 HM-09 之後不會在那裡衝突。
- 沒給 `slot_busy`（每個沒開通的產品、n8n 的 `run.py`）：`lanes` 是 `None`，`serve()` 走原本的程式路徑（一組 semaphore、等 1 秒、
  503 `{"error":"request denied"}`）；`leased_serve` 不給 `ending`；`OwnedInitializeResponse` 沒有 fence。

### 3.2 兩組名額、排隊上限、排隊中斷線（`gateway.take_slot`；契約 §2.4）

- 照 PaaS `gateway_pool._acquire`／`_wait_for_slot`：有空位立刻拿（不讓出事件迴圈）；沒有空位時，那一組的排隊數已到上限就立刻回
  「queue」，否則排隊，最多等 `slot_busy.wait`（1 秒），同時看用戶端在不在（`client_gone`：body 已讀完、回應還沒開始時的
  `http.disconnect`）。
- 用戶端走了：回「abandoned」，請求絕不送出；名額剛好同一刻空出時，那個名額由 `_hand_back` 還回去（PaaS 同）。等不到、被取消時，
  排隊中的 `acquire` 一律取消並掛 `_hand_back`，不留孤兒 waiter（PaaS N9）。監看本身出錯不算斷線（PaaS `_watch_client`）。
- 「abandoned」回 499（`CLIENT_CLOSED`），沒有人收得到：uvicorn 0.38 的 `send` 在用戶端斷線後直接返回、也不記 access 行
  （`h11_impl.py` 的 `if self.disconnected: return`）；只記帳號的 WARNING。
- 數值（契約 §5）：一般名額 32／16、保留 4／4、每組排隊 32／16、等 1 秒。注意：預設帳號准入 64＝轉送 32＋排隊 32，額外帳號 32＝16＋16，
  所以正式數值下一般名額的排隊上限實際上碰不到（准入先擋）；它是第二道上限，機制測試用小的名額值驗。同一件事也讓保留名額在一般名額與
  佇列都滿時到不了（審查 MF-2；第 3.3 節）。
- `mcp_app.state.lanes`：開通時兩組名額的物件（名額數、排隊數），給診斷與測試；沒開通是 `None`。

### 3.3 通知保留名額（`gateway.carries_no_request`；契約 §2.4；§8.8 #90）

- 判斷函式照 PaaS `_carries_no_request` 原樣（POST、可解析、物件或非空陣列、沒有任何請求、每則是通知或回應），PaaS 的 51 個本體
  逐一對照（第 4 節）。輸入是 HA 自己解析的結果：strict JSON 拒絕重複鍵與 NaN（400，在任何名額之前），所以 PaaS 會走保留名額的
  「重複 id、最後一個是 null」在 HA 根本拿不到名額（更嚴）。
- HA 的政策只收單一訊息：batch、對伺服器請求的回應、沒有 id 的工具呼叫在名額之前就 403；`notifications/initialized` 以外的通知由閘道
  自己回 202。所以實際走保留名額的只有 `notifications/initialized`；GET 串流與 DELETE 一律走一般名額（PaaS 同）。
- **保留名額只在准入還有空位時有用**（審查 MF-2；契約 §2.4、§5、§9 #95；威脅模型第 3 節）：准入（HM-08）在讀 body 前算，讀 body 中、
  排隊中、轉送中的請求與開著的 GET 串流都算；准入＝轉送＋排隊（64＝32＋32、32＝16＋16）。一般名額與它的佇列都滿時准入也滿，`notifications/initialized`
  在讀 body 前就拿 503（`-32003`、`id: null`、准入的文字），到不了保留名額。PaaS（@69ac425）讀 body 前沒有准入，所以照樣送到。
  只影響同一個帳號自己。主對話 2026-11-16 定案（MF-2 (b)；第 11 節）：不改 DQ-07 的數值；交 HM-31（對齊 PaaS #155）改分派器，准入滿時
  仍讀 ≤64 KiB 的小請求，是通知或回應就走保留名額。本片照現況寫明，
  `tests/test_carries_no_request.py::test_the_reserve_is_reached_only_while_the_profiles_admission_has_room` 先釘住現況（排 15 個 202、
  排滿 16 個 503），HM-31 再改。

### 3.4 子程式中途斷線 `-32004`（契約 §2.5；FM-44）

- 「中途斷線」＝`httpx.TransportError` 裡連上之後的讀、寫、協定錯誤（`interrupted()`：排除逾時與 `ConnectError`）。`ConnectError`
  照今天走自答或 session 結束（listing 有給時），逾時與子程式回錯的東西照今天 502 `{"error":"request denied"}`。
- 三個地方：送出後拿不到標頭（`serve` 的 except）、JSON 回覆讀到一半（`chunks()` 記下 `owner.interrupted`）、SSE 串流途中（`stream()`
  迴圈結束後補事件）。initialize 的回覆讀到一半也是 `-32004`；子程式正常結束卻沒有回覆照今天 503 `BACKEND_UNAVAILABLE`。
- 原因：轉送那一刻記下世代＝健康監看快照裡子程式的 `starts`（每次 spawn 加一）；斷線後 start 數變了或狀態不是 `running` 就是停止了，
  看起來還在跑時每 20 ms 看一次、最多 0.25 秒（`CHILD_EXIT_GRACE_SECONDS`，同 PaaS）。沒有健康監看（測試替身）時一律說停止了（PaaS 同）。
  子程式停止時，它為 initialize 開的 session 不 DELETE。
- 停止了的兩種文字（rebase 到 HM-09 之後加；第 16.4 節）：判定停止的那一刻（`interruption_text`，和 `child_stopped` 之間沒有 await）看
  `Supervisor.status`：`backoff`、`starting` 或新世代的 `running`（`CHILD_RESTARTING_STATES`）用 PaaS 的「會自動重新啟動」
  （`CHILD_STOPPED_TEXT`）；`blocked`、`failed`、`stopped`、`unconfigured` 用「目前沒有在重新啟動」（`CHILD_HALTED_TEXT`；§8.8 #99）。
- WARNING：帳號的 `child_interrupted`，每帳號每種原因 60 秒一行（§8.8 #92），只有 HTTP 方法與錯誤類別名，不帶路徑（密鑰網址的路徑就是
  token）、traceback 或內容。

### 3.5 標頭後換 token `-32005` 與不丟例外（`gateway.Ending`、`access.Delivery`；契約 §2.5；FM-34）

- `LeasedResponse` 記下回應走到哪（`Delivery`：開始送、伺服器收下標頭＝`send` 返回、最後收下的本體物件、整個送完）。開通時
  `leased_serve` 給它一個 `Ending`；token 在「開始送」之後才換掉時，交給 `Ending`，而不是把 `ClientDisconnect` 丟給 uvicorn。
- 標頭還沒被收下（背壓：uvicorn 在 `flow.drain()` 等用戶端讀，被取消就什麼都沒寫）：送和今天一樣的拒絕（Bearer 401
  `{"error":"request denied"}`、密鑰網址 404 Not Found；測試逐位元比對「回應開始前就換 token」的那條例外路徑）。不能改成丟例外：
  Starlette 的例外包裝在 `send` 之前就把 `response_started` 設成 True，丟例外會變成 RuntimeError 與 500。
- SSE 標頭已出去：回覆還沒送到就補一則同 id 的 `-32005` 事件，再送結束訊息。「送到」＝產生器在回覆之後被續跑（`answered`），或
  token 正好在伺服器收下回覆的那一刻換掉（最後收下的本體就是回覆那個事件物件）；後者是寫測試時找到的競態：PaaS 的 `_Interruption`
  只看前者，會在已送到的回覆後面再補一則同 id 的錯誤。GET 串流不補。
- 「回覆」也包括閘道自己補的 `-32004` 事件（審查 S-1）：原本 `-32004` 事件沒記成 `owner.reply_event`、yield 後也沒設 `answered`，伺服器
  收下它之後 token 才換掉時，`Ending` 會再補一則同 id 的 `-32005`（一個請求兩則錯誤）。修正後兩個條件都照回覆的規則；PaaS 同樣會補兩則
  （`Pc/proxy.py:1192-1194`），和上一點一起列契約 §9 #96（加嚴，建議回補 PaaS，HM-29）。
- 一次送完的 JSON 標頭已出去：`Content-Length` 已定（HM-01 黃金回歸逐位元），內容不能換；子程式的位元組也不再送。閘道返回，uvicorn
  記一行 `ASGI callable returned without completing response.`（沒有 traceback）並關掉連線（§8.8 #91；PaaS 的回覆不帶 `Content-Length`，
  所以能改送 `-32005`）。
- 結尾最多送 `ENDING_SECONDS`＝2 秒（PaaS `INTERRUPTED_FINISH_TIMEOUT`）；用戶端完全不讀時放棄、不丟例外（§8.8 #94）。
- 沒給 `ending`（每個沒開通的產品）：一行都沒變（`tests/test_active_token_leases.py` 照舊斷言 `ClientDisconnect`）。

### 3.6 initialize 世代（FM-43；契約 §2.5；§8.8 #93）

- 送出 initialize 時記下世代（同 3.4）；回覆的標頭送出前一刻（`OwnedInitializeResponse` 的 fence）再看一次：那個世代不再是執行中的
  那一個（換代、結束、被停），用戶端拿 503 `BACKEND_UNAVAILABLE`＋`Retry-After: 5`（HA 既有「initialize 等不到回覆」的回應）、沒有
  session id，那個 session 不 DELETE（會打到下一個世代）。
- HA 沒有 PaaS 的派送登記與 drain：Supervisor 的重啟不經過閘道。標頭已經在送的 session 收不回來；用戶端之後在那個 session 的請求拿到
  新子程式的 404，照 MCP 重新 initialize（測試 `test_a_restart_never_waits_for_an_initialize_answer_still_going_out`）。
- 「listener 仍是同一個程序」要 FM-41 的身分檢查，屬 HM-15（條件式）；HM-14 只比世代。

### 3.7 不受開關管：子程式 initialize 錯誤的遮罩（契約 §1.2）

- `make_apps` 對 initialize 錯誤一律 `redact.redact_secrets(value, masks(store.load()))`：沒開通時 `masks` 就是本帳號的
  `redact.secret_values`，開通時再加 HM-08 的聯集。這是 HM-08 審查 S-4 (a) 交給 HM-14 的既有缺口；理由、改了什麼回應、HM-01 契約凍結
  不用改，都寫在契約第 1.2 節。
- 開關關的兩個測試：本帳號的 token、child token、後端密碼都變成 `[REDACTED]`；沒有憑證的錯誤逐位元同今天。HM-08 的突變 K11（「開關關時
  initialize 錯誤也遮」）這一片起就是程式本身，K11 的反向（開關關時不遮）由本片的突變 M01 擋（第 6.2 節）。

### 3.8 計畫沒寫死、本片定的做法（契約已同步）

1. 開通的訊號與 `SlotBusy` 的形狀（3.1）。
2. 「中途斷線」的錯誤範圍；initialize 讀到一半斷線也是 `-32004`（3.4）。
3. 世代＝健康監看快照的 `starts`（3.4、3.6）。
4. 一次送完的 JSON 標頭已出去時的處理（3.5；§8.8 #91）；標頭卡在背壓時的拒絕也是 2 秒（§8.8 #94）。
5. initialize 換代的回應用 HA 既有的 503 `BACKEND_UNAVAILABLE`（§8.8 #93）。
6. `-32004` 的 WARNING 照 HA 規則 60 秒一行（§8.8 #92）。
7. 「回覆已送到」也看最後收下的本體物件（3.5 的競態）。

這些都不是使用者要定的題目（DQ），是契約寫明「HM-14 定案」或計畫範圍內的實作細節；審查若認為某一項要問使用者，再回報。

## 4. PaaS 四個測試檔逐案對照（pin `69ac425`；案例行號是 pin 的）

HA 的測試檔：`Q`＝`tests/test_gateway_queue_ha.py`、`B`＝`tests/test_gateway_busy_shapes.py`、`E`＝`tests/test_gateway_stream_endings.py`、
`C`＝`tests/test_carries_no_request.py`、`G`＝`tests/test_initialize_generation.py`。`paas-test-mapping.md`（HM-00 的產生器產出，不手改）
指的檔和下表一致；下表多寫了實際的案例名與差異。

### 4.1 `packages/mcp-admin-core/tests/test_gateway_queue.py`（25 案）

| # | 行 | PaaS 案例 | HA |
|---|---|---|---|
| 1 | 123 | `test_request_abandoned_while_queued_never_reaches_the_child` | Q `test_request_abandoned_while_queued_never_reaches_the_child_on_a_real_listener`（真 uvicorn＋TCP，用戶端 0.5 秒逾時關連線） |
| 2 | 159 | `test_client_leaving_the_queue_is_noticed_at_once_and_returns_nothing_it_did_not_take` | Q `test_clients_leaving_the_queue_are_noticed_at_once_and_take_nothing`（5 個 POST＋1 個 GET，行程內驅動） |
| 3 | 194 | `test_queue_is_capped_per_profile_and_the_overflow_gets_a_clean_busy_answer_with_a_warning` | Q `test_the_queue_is_capped_per_profile_and_the_overflow_gets_a_clean_busy_answer` |
| 4 | 241 | `test_zero_queue_means_no_waiting_at_all` | §8.8 #45（HA 沒有設定入口）；機制照驗：Q `test_queue_cap_refuses_the_overflow_at_once_and_other_lanes_are_unaffected`（queue 0）、B `test_an_initialize_waiting_for_a_slot_gets_the_normal_busy_answer[0]` |
| 5 | 262 | `test_limits_from_environment_include_the_queue` | 不適用：HA 沒有環境變數（§8.8 #45）；數值由 `tests/test_profile_index.py` 與 Q `test_every_profiles_own_client_has_room_for_its_slots_and_its_reserve` 鎖住 |
| 6 | 288 | `test_notifications_get_through_when_every_ordinary_slot_is_busy` | C `test_the_reserve_carries_notifications_initialized_while_every_ordinary_slot_is_busy`（含 82c6929 的「事件不是時間」寫法；HA 只轉送 `notifications/initialized`：§8.8 #90） |
| 7 | 337 | `test_get_streams_never_use_the_notification_reserve` | 同上（GET 等一般名額、503） |
| 8 | 395 | `test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent` | Q 同名 |
| 9 | 423 | `test_slot_granted_in_the_same_instant_the_client_leaves_is_given_back_not_used` | Q 同名（含 82c6929 的記帳 semaphore：沒還過頭） |
| 10 | 456 | `test_cancelling_a_queued_request_returns_nothing_and_leaks_no_slot` | Q 同名（同上） |
| 11 | 484 | `test_a_broken_disconnect_watcher_does_not_look_like_a_disconnect` | Q 同名 |
| 12 | 503 | `test_request_without_hints_behaves_exactly_as_before` | 開關關時照舊：B `test_switched_off_nothing_of_the_lanes_applies`；`tests/test_profile_quotas.py::test_switched_off_a_busy_slot_and_a_client_leaving_answer_as_before`（HM-08，逐位元） |
| 13 | 518 | `test_queue_cap_refuses_the_overflow_at_once_and_other_profiles_are_unaffected` | Q `test_queue_cap_refuses_the_overflow_at_once_and_other_lanes_are_unaffected`；Q #3 的測試另驗預設帳號照常 |
| 14 | 547 | `test_notification_lane_is_separate_from_the_ordinary_slots` | C #6 的測試後半（保留名額滿、第 5 則 503 保留名額的文字）；C `test_without_a_reserve_a_notification_takes_an_ordinary_slot` |
| 15 | 571 | `test_slot_accounting_survives_random_cancellation_disconnects_timeouts_and_overflow` | Q 同名（6 個種子，兩組名額都換成記帳 semaphore） |
| 16 | 635 | `test_shared_pool_has_room_for_every_profiles_slots_and_reserve` | §8.8 #15（HA 沒有共用池）；Q `test_every_profiles_own_client_has_room_for_its_slots_and_its_reserve` |
| 17 | 654 | `test_initialize_waiting_for_a_slot_during_startup_gets_the_normal_busy_answer` | B `test_an_initialize_waiting_for_a_slot_gets_the_normal_busy_answer[1\|0]`（HA 子程式沒起時自答 initialize，在名額之前：§8.8 #68） |
| 18 | 809 | `test_a_request_that_waited_for_a_slot_keeps_holding_it_until_its_response_closes` | Q 同名［ordinary｜reserved］ |
| 19 | 844 | `test_shared_pool_size_is_pinned_to_the_documented_formula` | §8.8 #15；Q 每帳號 client 的那個測試；8081 外框算式由 `tests/test_router_passthrough.py`（HM-08）鎖住 |
| 20 | 861 | `test_queue_limit_counts_each_lane_on_its_own` | Q 同名 |
| 21 | 897 | `test_busy_message_names_the_limit_of_the_lane_that_timed_out` | B `test_busy_texts_and_warnings_name_the_limit_of_their_own_lane`［ordinary｜reserved］（含 82c6929 的 WARNING 全文） |
| 22 | 930 | `test_queue_full_message_names_the_limit_of_the_lane_that_is_full` | 同上 |
| 23 | 964 | `test_closing_the_same_response_twice_returns_the_slot_only_once` | Q `test_closing_the_same_answer_twice_returns_the_slot_only_once`（`UpstreamOwner.close`） |
| 24 | 982 | `test_requests_that_timed_out_leave_no_orphan_waiter_on_the_semaphore` | Q 同名 |
| 25 | 1003 | `test_queue_limit_environment_variable_accepts_its_ceiling_and_rejects_one_more` | 不適用：HA 沒有環境變數（§8.8 #45） |

### 4.2 `packages/mcp-admin-core/tests/test_proxy_interrupted_cause.py`（9 案）

| # | 行 | PaaS 案例 | HA |
|---|---|---|---|
| 1 | 84 | `test_connection_error_with_the_child_still_running_says_so`（3 種錯誤） | E `test_a_connection_broken_with_the_child_still_running_says_so`［ReadError｜RemoteProtocolError｜WriteError］ |
| 2 | 105 | `test_child_that_stopped_during_the_request_keeps_the_established_message` | E `test_a_child_that_stopped_during_the_request_is_reported_stopped`［exited｜generation replaced］ |
| 3 | 126 | `test_manager_noticing_the_exit_a_moment_later_is_still_reported_as_stopped` | E `test_the_supervisor_noticing_the_exit_a_moment_later_still_reports_stopped` |
| 4 | 145 | `test_batch_and_streams_get_the_same_wording` | E `test_a_get_stream_and_a_buffered_answer_follow_the_same_rule`（GET 502、id null）；batch：HA 從不轉送（403；§8.8 #16 附註），同一個測試裡驗 |
| 5 | 161 | `test_mid_sse_disconnect_with_the_child_still_running` | E `test_an_event_stream_broken_mid_reply_gets_one_minus_32004_event_and_ends[still running]` |
| 6 | 173 | `test_mid_sse_disconnect_when_the_child_stopped` | 同上 `[stopped]` |
| 7 | 186 | `test_buffered_tools_list_disconnect_follows_the_same_rule`（2） | E #4 的測試（JSON 回覆讀到一半斷線，兩種原因） |
| 8 | 198 | `test_log_line_names_the_cause_without_a_traceback_or_token` | E 同名（§8.8 #92：60 秒一行）；所有新測試都在 HM-01 的 log 掃描下跑 |
| 9 | 234 | `test_real_child_killed_mid_request_is_reported_as_stopped` | E `test_a_real_connection_reset_mid_request_is_reported`（真的 TCP 連線被 RST、真的 httpx transport；子程式行程用測試替身。真的行程被 SIGKILL 在 HAOS 驗收 T-13，HM-19b） |

### 4.3 `packages/mcp-admin-core/tests/test_initialize_fence_backpressure.py`（5 案）

| # | 行 | PaaS 案例 | HA |
|---|---|---|---|
| 1 | 72 | `test_token_rotated_while_the_headers_are_stuck_gets_a_clean_403_and_no_exception` | E `test_a_token_changed_while_the_headers_wait_gets_the_clean_refusal_and_no_exception`［bearer｜secret］（§8.8 #1：401／404；任何回應都適用，不只 initialize） |
| 2 | 109 | `test_token_rotated_in_the_same_instant_the_headers_are_accepted_ends_cleanly` | E `test_a_token_changed_as_the_headers_are_taken_ends_without_an_exception`（一次送完的 JSON：§8.8 #91）；SSE：E `test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event`、`test_a_reply_delivered_before_the_token_changed_gets_no_minus_32005` |
| 3 | 142 | `test_old_token_stays_rejected_after_the_fence_answered` | E #1 的測試後半（舊 token 401／404） |
| 4 | 219 | `test_only_the_fences_own_rejection_is_swallowed_never_another_error`（10） | E `test_only_a_changed_token_is_ended_never_another_error`［ValueError｜KeyError｜CancelledError］；HA 沒有例外群組（MCP app 沒有 BaseHTTPMiddleware；§8.8 #94） |
| 5 | 235 | `test_a_client_that_reads_nothing_does_not_hold_the_rejection_forever` | E `test_a_client_that_reads_nothing_does_not_hold_the_ending` |

### 4.4 `packages/mcp-admin-core/tests/test_proxy_carries_no_request.py`（4 案）

| # | 行 | PaaS 案例 | HA |
|---|---|---|---|
| 1 | 112 | `test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane`（42 個本體） | C 同名，42 個本體逐字相同（HA 照自己的 strict JSON 解析） |
| 2 | 117 | `test_only_notifications_and_responses_use_the_reserved_lane`（9 個） | C 同名 8 個；「重複 id、最後一個是 null」另列 C `test_a_duplicate_key_is_refused_before_any_slot`（HA 400、不拿任何名額） |
| 3 | 122 | `test_only_post_can_use_the_reserved_lane` | C 同名 |
| 4 | 131 | `test_nothing_parsed_means_the_ordinary_lane` | C 同名 |

本體逐字相同：用 `ast` 從 PaaS pin 的檔與 HA 的檔各自抽出 (名稱, 本體) 串列比對，51 筆、順序相同。

### 4.5 `paas-test-mapping.md` 另外指給 HM-14 的：`test_initialize_stop_recovery.py`（10 案裡的 9 案）

PaaS 的這組測試驗「生命週期轉換等在途的 initialize 派送（drain）」。HA 沒有這個機制（Supervisor 的停止與重啟不經過閘道，§8.8 #93），
所以不逐案搬；HA 對應的性質是「重啟不等閘道、標頭已在送的 session 收不回來、用戶端照 MCP 重連」，由 G
`test_a_restart_never_waits_for_an_initialize_answer_still_going_out` 驗；收據與重啟的部分照 `paas-test-mapping.md` 對到既有的
`tests/test_admin_operations.py`。

## 5. 開關關時形狀與今天相同（驗收）

開關關（repo 的狀態）時，HM-14 改到的每一條路徑都照舊，證據：

| 回應 | 開關關時 | 測試 |
|---|---|---|
| 轉送名額等 1 秒逾時 | 503 `{"error":"request denied"}`（逐位元）；沒有排隊上限、沒有保留名額（`notifications/initialized` 也等同一組 32 個名額）；`mcp_app.state.lanes` 是 `None` | B `test_switched_off_nothing_of_the_lanes_applies`；`tests/test_profile_quotas.py::test_switched_off_a_busy_slot_and_a_client_leaving_answer_as_before`（HM-08） |
| 子程式中途斷線（ReadError、RemoteProtocolError、WriteError；JSON 讀到一半） | 502 `{"error":"request denied"}`（逐位元）；SSE 斷線安靜結束、沒有事件；沒有 WARNING | E `test_switched_off_a_broken_connection_keeps_todays_answers` |
| 子程式回錯的東西（3xx、401、403、格式錯、id 不對、超過 8 MiB、協定版本不在清單） | 502 `{"error":"request denied"}`（逐位元；開關開也一樣） | E `test_a_childs_wrong_answer_keeps_todays_502[switched off]`（契約 §4.2「其他既有回應」交給 HM-14 的逐位元案例） |
| token 換掉、回應已開始 | `ClientDisconnect` 丟給 uvicorn（今天的行為） | `tests/test_active_token_leases.py`（既有，斷言照舊）；突變 E05（開關關也用閘道的結尾）被它擋下 |
| initialize 換代 | session 照舊交出 | G `test_switched_off_the_session_is_handed_out_as_before` |
| initialize 錯誤（**唯一的例外**，契約 §1.2） | 本帳號憑證換成 `[REDACTED]`；沒有憑證時逐位元同今天 | G `test_switched_off_a_childs_initialize_error_is_masked_with_the_profiles_own_credentials`、`test_switched_off_an_initialize_error_without_a_credential_is_relayed_as_before` |

HM-01 的黃金回歸、MCP 與管理契約凍結（開關關與開關開各一次，`tests/test_router_passthrough.py`）斷言一個字都沒改，照過（第 7 節）。
HM-01 的契約凍結不用改：凍結的案例沒有 initialize 錯誤。

## 6. 守門有效的證據

### 6.1 先寫測試，先紅後綠

測試在 `543eabc`（只有測試）；程式在 `c06eb43`。先紅的跑法：三個正式檔（`gateway.py`、`access.py`、`profile_router.py`）換回
`b5d10c5` 的內容、測試用新的，跑新 5 檔＋`test_reply_mask_union.py`；跑完用暫存區的備份逐位元還原並以 SHA-256 核對（3 個 OK）。

| 輪 | 範圍 | 結果 |
|---|---|---|
| 先紅（`b5d10c5` 的程式＋新測試，＝`543eabc` 的樹） | 新 5 檔 117 案＋`test_reply_mask_union.py` 8 案 | **106 失敗、19 通過**。失敗：`test_carries_no_request.py` 58／59、`test_gateway_queue_ha.py` 19／20、`test_gateway_stream_endings.py` 20／23、`test_gateway_busy_shapes.py` 5／6、`test_initialize_generation.py` 4／9。通過的 19 案：`test_reply_mask_union.py` 8 案（本片沒改它測的程式）＋11 個「今天就成立、本片要釘住」的案例：開關關的 4 案（子程式回錯照舊 502、斷線照舊 502、session 照舊交出、沒有憑證的 initialize 錯誤逐位元）、開關開的 7 案（子程式回錯照舊 502、每帳號 client 放得下名額、保留名額 0 時走一般名額、HM-08 已做的 initialize 等名額逾時形狀、正常世代照舊交出、重啟不等卡住的回應、HM-08 的 initialize 錯誤聯集遮罩）。紅的原因都是缺函式、缺屬性、缺參數或行為不同，不是環境 |
| 綠（`c06eb43` 的程式） | 新 5 檔 | **117 案全過，15.5 秒** |
| 綠 | HM-08 的 4 檔、HM-01 守門 3 檔、`test_profile_runtime.py`、`test_upgrade_zero_rewrite.py`、`test_active_token_leases.py`、閘道相關既有 14 檔、`test_profile_index.py`（共 24 檔） | **1217 案全過，209 秒** |

寫測試時找到、改掉的（程式）：SSE 回覆在 token 換掉的那一刻被伺服器收下時，原本會在回覆後面再補一則同 id 的 `-32005`（第 3.5 節；
PaaS 的 `_Interruption` 同樣只看「產生器有沒有續跑」）。測試 `test_a_reply_delivered_before_the_token_changed_gets_no_minus_32005`
釘住，突變 E03 擋下。測試工具本身改過的：測試自己的 httpx 用戶端要用 `GENUINE_CLIENT`（執行期間 `httpx.AsyncClient` 被換成
MockTransport）；`hold_start` 只擋第一個標頭（閘道自己的拒絕要送得出去）；三個計時斷言放寬（等候改 0.6 秒、門檻 0.5 秒；不看 runner 快慢）。

### 6.2 臨時突變

每個突變只改正式程式的一處（文字剛好出現一次、改完仍可編譯），跑新 5 檔（`-x`；E05 另加 `test_active_token_leases.py`、M01 另加
`test_reply_mask_union.py`），跑完逐位元還原並以 SHA-256 核對。腳本在 repo 外（`SP:hm14/bin/mutate.py`）。**28 個全部擋下**。E04 第一次的寫法改壞了語法（收集就失敗，不算數），改成可編譯的寫法後重跑，被
`test_a_token_changed_while_the_headers_wait_gets_the_clean_refusal_and_no_exception[bearer]` 擋下（下表是重跑的結果）。

| # | 突變 | 檔 | 擋下的第一個測試 |
|---|---|---|---|
| Q01 | 排隊時不看用戶端（斷線永遠看不到） | `gateway.py` | `tests/test_gateway_queue_ha.py::test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent` |
| Q02 | 名額與斷線同一刻：照樣送出 | `gateway.py` | `tests/test_gateway_queue_ha.py::test_slot_granted_in_the_same_instant_the_client_leaves_is_given_back_not_used` |
| Q03 | 不設排隊上限 | `gateway.py` | `tests/test_gateway_queue_ha.py::test_queue_cap_refuses_the_overflow_at_once_and_other_lanes_are_unaffected` |
| Q04 | 放棄等候時不還晚到的名額 | `gateway.py` | `tests/test_gateway_queue_ha.py::test_slot_granted_in_the_same_instant_the_client_leaves_is_given_back_not_used` |
| Q05 | 逾時後不取消排隊中的 acquire（孤兒 waiter） | `gateway.py` | `tests/test_gateway_queue_ha.py::test_requests_that_timed_out_leave_no_orphan_waiter_on_the_semaphore` |
| N01 | 保留名額不用（通知走一般名額） | `gateway.py` | `tests/test_carries_no_request.py::test_the_reserve_carries_notifications_initialized_while_every_ordinary_slot_is_busy` |
| N02 | 任何 POST 都走保留名額 | `gateway.py` | `tests/test_carries_no_request.py::test_the_reserve_carries_notifications_initialized_while_every_ordinary_slot_is_busy` |
| N03 | 判斷不擋請求（有 id 的請求也算通知） | `gateway.py` | `tests/test_carries_no_request.py::test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane[request]` |
| N04 | 判斷不限 POST | `gateway.py` | `tests/test_carries_no_request.py::test_only_post_can_use_the_reserved_lane[GET]` |
| N05 | 空陣列也算 | `gateway.py` | `tests/test_carries_no_request.py::test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane[empty batch]` |
| I01 | 斷線一律說「停止了」 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_connection_broken_with_the_child_still_running_says_so[ReadError]` |
| I02 | 不等子程式結束（0.25 秒的寬限拿掉） | `gateway.py` | `tests/test_gateway_stream_endings.py::test_the_supervisor_noticing_the_exit_a_moment_later_still_reports_stopped` |
| I03 | SSE 斷線不補 -32004 事件 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_an_event_stream_broken_mid_reply_gets_one_minus_32004_event_and_ends[still running]` |
| I04 | 標頭前斷線照舊 502 request denied | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_connection_broken_with_the_child_still_running_says_so[ReadError]` |
| I05 | 逾時也算中途斷線 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_childs_wrong_answer_keeps_todays_502[switched on]` |
| I06 | JSON 回覆讀到一半斷線不補 -32004 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_get_stream_and_a_buffered_answer_follow_the_same_rule` |
| E01 | 標頭卡住時換 token：照舊丟 ClientDisconnect | `access.py` | `tests/test_gateway_stream_endings.py::test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event` |
| E02 | SSE 換 token 不補 -32005 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event` |
| E03 | 已送到的回覆後面也補 -32005 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_reply_delivered_before_the_token_changed_gets_no_minus_32005` |
| E04 | 標頭還沒收下就當作收下（不送拒絕） | `access.py` | `tests/test_gateway_stream_endings.py::test_a_token_changed_while_the_headers_wait_gets_the_clean_refusal_and_no_exception[bearer]`（重跑） |
| E05 | 開關關時也用閘道的結尾 | `gateway.py` | `tests/test_active_token_leases.py::test_real_socket_two_established_streams_close_and_reissue_works[POST-revoke]` |
| E06 | 結尾不設時限 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_client_that_reads_nothing_does_not_hold_the_ending` |
| G01 | 不檢查 initialize 世代 | `gateway.py` | `tests/test_initialize_generation.py::test_an_initialize_whose_generation_changed_is_not_handed_out[restarted]` |
| G02 | 世代變了仍 DELETE 舊 session | `gateway.py` | `tests/test_initialize_generation.py::test_an_initialize_whose_generation_changed_is_not_handed_out[restarted]` |
| G03 | 世代只看狀態、不看 start 數 | `gateway.py` | `tests/test_gateway_stream_endings.py::test_a_child_that_stopped_during_the_request_is_reported_stopped[generation replaced]` |
| M01 | 開關關時 initialize 錯誤照舊不遮 | `gateway.py` | `tests/test_initialize_generation.py::test_switched_off_a_childs_initialize_error_is_masked_with_the_profiles_own_credentials` |
| W01 | 放棄等候不記 WARNING | `gateway.py` | `tests/test_gateway_queue_ha.py::test_request_abandoned_while_queued_never_reaches_the_child_on_a_real_listener` |
| W02 | 保留名額的文字寫一般名額的條數 | `profile_router.py` | `tests/test_carries_no_request.py::test_the_reserve_carries_notifications_initialized_while_every_ordinary_slot_is_busy` |

上表是實作時的突變。獨立審查另做的 16 個突變裡，T03、R05、R06、R12、R22 用上面的測試擋不下（W04、ICE 是等價突變）；
審查修正加測試後的重跑（含新的 S1R、S4R）見第 15.4 節。

## 7. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 都排隊在共用鎖）

| 檢查 | 結果 |
|---|---|
| 新 5 檔 | 117 案全過、0 skip，15.5 秒（最慢的 2.6 秒、2.5 秒是忙碌回應要真的等滿 0.6 秒的兩個端到端案例） |
| 相關既有 24 檔（第 6.1 節） | 1217 案全過、0 skip，209 秒 |
| 全套 pytest（`tests/`，Chromium 照 CI 裝在 `packages/mcp-admin-ui/node_modules`；程式＝`c06eb43`） | 5394 案、0 skip、31 分 1 秒：5387 通過；7 失敗＝第 8 節列的 7 個要 root 的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5），沒有別的失敗；瀏覽器測試都過；2 個 warning 是既有測試裡 websockets 的 DeprecationWarning |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| packaging unittest（照 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py`（漂移檢查，同 unit.sh） | exit 0（沒動 `apps/runtime`、`launch.py`） |
| `git status` | 乾淨 |

上表是實作時（2026-11-15）的結果；審查修正後（2026-11-16）的重跑見第 15.3 節（全套沒有重跑，理由寫在那裡）。

## 8. 只在 CI 跑的測試、`checks` 秒數

- 本片新增的 117 案（審查修正後 128 案，rebase 後 135 案）都在本機跑過、全部通過，**沒有只在 CI 跑的新測試**。CI（root、0 skip）才是準：
  - 已知要 root、本機一定失敗的既有案例（不是本片造成）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
    `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`tests/test_restore_detection.py` 的 5 個 `test_root_*`。
  - 本片的測試在 root 下：不看 uid、檔案權限或 `str()` 的格式；真 socket 只綁 127.0.0.1 的隨機 port（`tests/owned_network.py` 擋 3000 與
    18000～18099）；計時只用寬鬆上限或可控的值（等候 0.6 秒配 0.5 秒門檻、寬限 3 秒）。
  - Python：CI 3.13.16、本機 3.13.15。
- `checks` 秒數：**開 PR 後補**（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本片新測試本機 15.5 秒，
  審查修正再加 11 案、約 2.2 秒（新 5 檔＋遮罩聯集合計 18.6 秒）；CI 的 runner 比本機慢、又以 root 跑，推估 `checks` 增加約 35～55 秒
  （計畫 §10.1：每片 ≤1.5 分鐘；基準 `b5d10c5` 的上限 40 分鐘，#100 起 60 分鐘）。起真子程式的案例：0（真 socket 的兩個案例用行程內的
  uvicorn 與 asyncio 伺服器，各 1 秒以內；審查修正的 11 案都在行程內）。

## 9. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；本片 5 個 commit（`b5d10c5..HEAD`，含本筆記）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 172 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的 3 個列管檔（`access.py`、`gateway.py`、`profile_router.py`）都有帳本更新；沒有沒列管的新執行檔：**OK** |
| 秘密預檢（審查修正後，2026-11-16） | 同上 | `b5d10c5..HEAD` 10 個 commit（含審查修正的 5 個與本筆記）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢（審查修正後，2026-11-16） | 同上 | 172／70／159 檔：0 漂移、0 缺；改到的 3 個列管檔都有帳本更新（`gateway.py`、`profile_router.py` 依審查修正後的內容重算）；沒有沒列管的新執行檔：**OK** |

測試資料：沒有 commit 任何隨機 token 或像金鑰的字串；token 都在執行時產生（`create_profile`、`secrets.token_urlsafe`），憑證沿用 HM-01 的
`DUMMY-…`、網址 `.invalid`。PaaS 的 51 個 `_carries_no_request` 本體是合成的 JSON（工具名 `x`）。

## 10. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`，本機唯讀 PaaS repo）

本機 PaaS clone 的 `origin/main` 寫筆記時是 `5b84b5d`，審查修正時是 `d7f5849`（任務說 `cf3d0d5`；`cf3d0d5..5b84b5d` 是 #152～#154，
Nextcloud 與 EMQX，HM-08 審查已記；`5b84b5d..d7f5849` 是 #155；都是別的流程 fetch 的，本片沒 fetch、沒 checkout）。
查的檔：`proxy.py`、`gateway_pool.py`、`initialize_fence.py`、`mcp_access.py`、`docs/mcp-gateway-limits.md`、
`docs/shared-token-lifecycle.md`、`test_gateway_queue.py`、`test_proxy_interrupted_cause.py`、`test_initialize_fence_backpressure.py`、
`test_proxy_carries_no_request.py`。

| commit | 內容 | 對本片 |
|---|---|---|
| `19f36e2` | #148 合併後的文件更正：`docs/mcp-gateway-limits.md`、`gateway_pool.py` 與 `proxy.py` 的 docstring 和註解（可執行碼不變） | 已知限制（SDK 層級逾時、`terminate_on_close=True`）寫進契約第 2.4 節與威脅模型第 3 節；排隊中斷線的 499「沒有人收得到」寫進契約第 2.4 節。「排隊請求的記憶體只有個數上限」不適用（HA 的位元組額度從准入扣到請求結束，涵蓋排隊中的請求；審查 S-5 更正：原本寫成已寫進文件） |
| `82c6929` | 只改 `test_gateway_queue.py`：還過頭的名額（記帳 semaphore）、保留名額逾時 WARNING 的全文、舊測試的時間餘裕（事件取代時間） | HA 的對應測試照新版寫（第 4.1 節的 #6、#9、#10、#15、#21） |
| `091dfbc` | 只改 `docs/mcp-gateway-limits.md` 惡意 Location 那一段 | 沒影響（HA 只轉回 4 個固定標頭、不轉 Location：§8.8 #4） |
| `8bfb12e` | `test_proxy_carries_no_request.py` 一行註解（拿掉已移除的 vk） | 沒影響 |
| `7ba572d`、`3b135ca`、`e6971c0`、`1637a0f`、`a2f8905`（#155，合併 `d7f5849`，2026-11-16 06:28 台北） | 閘道請求內容位元組預算（全域＋每帳號份額，掛在 transport 上、和連線名額同時歸還）、JSON 結構守門（深度、元素個數）、上傳閒置與總時間逾時 408；改 `proxy.py`、`gateway_pool.py`、`docs/mcp-gateway-limits.md` | **不影響本片**（審查 S-6，本機重查）：`_carries_no_request`、`_busy_message`、`_child_stopped`、`_Interruption`、`CHILD_*`／`ACCESS_CHANGED` 文字、`_finish_interrupted`、排隊與保留名額都沒改；HM-14 的符號只多一行 `CLIENT_CLOSED_REQUEST`（上傳讀到一半用戶端離開的回應，不是排隊）；四個測試檔沒動。對齊 #155 是 **HM-31**（使用者 2026-11-16 07:1x 決定：對齊 PaaS、所有產品都生效），排在本片之後 |

`git diff 69ac425 5b84b5d -- packages/mcp-admin-core/mcp_admin_core/proxy.py gateway_pool.py` 只有註解與 docstring；`5b84b5d..d7f5849`
（#155）見上表。DQ-06 第 4 節
「#150（`091dfbc`）由 HM-14 開工時對照」：本節即是，結論沒有要改的程式。

## 11. 本片用到的決策（都已定；`decisions.md` 不用改）

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-06 (a) | 對齊基準 `69ac425`，之後的變動每片列出；#150（`091dfbc`）由 HM-14 對照 | 第 10 節 |
| DQ-07 (a)＋DQ-29 | 名額規則與數值（契約第 5 節：轉送 32／16、等 1 秒、排隊 32／16、保留 4） | 第 3.2 節 |
| DQ-20 (b) | 開通的產品看門狗照 PaaS、不限次數重啟（HM-09） | HM-09 已合併（rebase 到 `c523474`）：子程式停止了時，看門狗退避中、正在起或新世代在跑才說「會自動重新啟動」；`blocked`、`failed`、`stopped`、`unconfigured` 說目前沒有在重新啟動（第 16.4 節） |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 7 節；commit |
| DQ-37 (a) | 同 uid 是同一個信任邊界 | listener 身分留給 HM-15（第 3.6 節） |
| DQ-40 (a) ⑧ | 回覆遮罩含所有帳號的 token | initialize 錯誤在開通時照 HM-08 的聯集遮（第 3.7 節） |

沒用到：DQ-13、14、21、25、30、31（使用者已定，HM-09～HM-12 記進 `decisions.md`）；UC-10、DQ-10 子題（HM-10、HM-20）。legacy SSE：HA 今天就沒有（§8.8 #6；DQ-23 待定、屬 HM-18），PaaS legacy SSE 的那幾列不適用，本片不需要它的決定。
實作時沒有碰到待定題。

**審查帶出的 MF-2 (b) 已定（主對話 2026-11-16 07:5x）**：保留名額要不要在准入滿時也有效。審查列的兩個做法：
(1) 准入留出保留名額的空間（准入＝轉送＋排隊＋保留，例如預設 68、額外 36；會改 DQ-07 (a) 的數值）——**不採用**，DQ-07 的數值不改；
(2) 准入滿時，對宣告 ≤64 KiB 的請求先讀完，是通知或回應（`carries_no_request`）就放行到保留名額（改 HM-08 的分派器）——**採用，交 HM-31**
（對齊 PaaS #155 一起做，照 PaaS 的語意）。本片照現在的寫法：契約 §2.4、§5、§9 #95（類型維持「待決」，說明改成交 HM-31 與這個定案）與
威脅模型第 3 節寫明現況與定案；`test_the_reserve_is_reached_only_while_the_profiles_admission_has_room` 先釘住現況，HM-31 再照定案改。
`decisions.md` 不加新題。

## 12. 待 HM-03a 確認

HM-03a／b 的實機探針還沒做。本片的行為不依賴 HAOS 特有的平台事實（uvicorn 0.38.0、httpx 0.28.1 都由映像釘死，行為和本機相同），
下面幾項是假設，等實機或 HAOS 驗收確認：

| 項目 | 本片的假設 | 要量什麼（誰） |
|---|---|---|
| MCP 用戶端與 8081 之間若有代理或 tunnel（使用者自己的反向代理、Cloudflare Tunnel） | 用戶端放棄時代理會關掉送往 8081 的連線，排隊中斷線監看才看得到（PaaS 也沒實測 cloudflared） | 用戶端逾時放棄時，代理是否關閉原點連線（HM-03b 或 HM-19b 的 T-19、T-27） |
| 真的子程式行程被殺時的時序 | 連線斷開與 Supervisor 看到結束差不到 0.25 秒（本機 PaaS 實測如此；HA 的 Supervisor 收屍與讀完 pipe 最多 1 秒。審查 E5 本機量 HA 真的 `Supervisor` 被 SIGKILL：20 次中位 2.9 ms、最多 4.1 ms） | HAOS 上 SIGKILL 子程式時 `-32004` 說「停止了」（HM-19b 的 T-13）；如果常說成「仍在執行」，再調寬限 |
| add-on log 看得到 uvicorn 的那兩行 ERROR（JSON 標頭已出去、用戶端完全不讀） | 只有一行、沒有 traceback | HAOS 的 add-on log（HM-19b） |

## 13. 驗收條件（計畫 §12.3 HM-14、§12.0）

| 條件 | 結果 |
|---|---|
| 全綠 | 本機：新 117 案、相關 1217 案全過；全套 5394 案只剩 7 個要 root 的既有案例（第 7 節）。rebase 後（第 16.7 節）：新 5 檔 135 案、相關 33 檔 1424 案全過；全套 5531 案只剩 7 個要 root 的既有案例與 22 個本機沒有 Chromium 的瀏覽器測試。CI（root、0 skip）待開 PR |
| 開關關時形狀與今天相同（initialize 錯誤遮罩除外） | 通過：第 5 節；HM-01 黃金回歸與兩個契約凍結斷言沒改、照過；突變 E05 擋下 |
| PaaS 四個測試檔逐案對照 | 通過：第 4 節，43 案每案都有 HA 測試或不適用的理由；`_carries_no_request` 的 51 個本體逐字相同 |
| 獨立安全審查 | **已做**（2026-11-16，`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-14.md`）：修正後通過；必修 2 項、建議 7 項的處理見第 15 節 |
| 不受開關管的修補照契約 §1.2 寫明、加開關關的測試 | 通過：契約 §1.2（為什麼、改了什麼回應、HM-01 凍結不用改）；G 的兩個開關關測試；突變 M01 擋下 |
| 已知限制照 PaaS 文件後續寫進 HA 文件 | 通過：契約 §2.4、威脅模型第 3 節（HM-18 寫進產品 DOCS） |
| 同 PR 更新帳本（新模組照 `ledger-tracking.md`） | 通過：三個列管檔重算 SHA-256；沒有新的執行期檔（`tests/` 不列管）；帳本預檢 OK |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過：`git diff --stat b5d10c5..HEAD` 只動 `packages/`、`tests/`、`docs/` |
| commit 沒有 AI 署名；英文標題、繁中內文 | 通過：`git log --format=%B b5d10c5..HEAD` 沒有 Co-Authored-By、Generated with |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：秘密預檢 0 命中（第 9 節） |
| provenance 欄位（計畫 §11.1） | 本筆記：只在 CI 跑的測試、兩個預檢、本片用到的決策、PaaS 變動、待 HM-03a 確認；`checks` 秒數開 PR 後補 |
| CI 時間預算 | 新測試本機 15.5 秒，推估 `checks` 增加 30～45 秒；沒有起真子程式的案例（第 8 節） |

## 14. 還沒解決、交給後面的片

- **MF-2 (b) 交 HM-31**（主對話 2026-11-16 定案；第 11 節）：准入滿時仍讀 ≤64 KiB 的小請求，是通知或回應就走保留名額；HM-31 改分派器、
  改釘住現況的那個測試，契約 §9 #95 那時再改類型與說明。DQ-07 的數值不改。
- **HM-09 合併後重看**：已做（第 16.4 節）。`blocked` 被 `child_runs` 判成「停止了」沒問題；`-32004` 停止了的文字改成看狀態分兩種。
- **給 PaaS 的回補建議（HM-29）**：一個請求只回一則（§8.8 #96：回覆在換 token 那一刻被收下、`-32004` 之後換 token）；`_MAX_REPORT_KEYS`
  64 不夠（#155 又多了 `body-*` 情況；審查 S-4）；子程式停止後不會自己再起時，`-32004` 不說會自動重新啟動（§8.8 #99）。
- **HM-31**（PaaS #155 對齊，使用者已定）：排在本片之後；它的位元組預算要和 HM-08 的額度整合，准入與保留名額的關係（第 3.3 節）一起看。
- **HM-18**：把契約第 2.4、2.5 節本片定案的文字與威脅模型第 3 節本片加的三條已知限制（審查後加了保留名額與准入）寫進產品 DOCS；
  `acceptance-matrix.md` 測試檔登記表的「計畫」狀態一起更新（HM-08 也留給 HM-18）。
- **HM-15**（條件式）：initialize 世代之外的「listener 仍是同一個程序」（FM-41）。
- **HM-19b**：第 12 節三項的實機確認；T-19 照第 3.2 節的數值驗。
- **後續可做（PaaS 文件也列為後續，不在 HM-14）**：同一個 session 的 `notifications/cancelled` 或 DELETE 到達時丟掉它排隊中的請求
  （補 SDK 層級逾時與 `terminate_on_close=True` 的缺口）；FM-52（超過上限先讀完再回錯誤）。
- **rebase 注意**：HM-09 之後的 rebase 已做（第 16 節）。開 PR 前還要再 rebase 一次：HM-20（後端網址擋 loopback）會先合併，它也改帳本、
  契約第 9 節（會補列）與 `decisions.md`。到時候帳本照實際內容重算 `gateway.py`、`access.py`、`profile_router.py`，契約列號若又衝突就再重編
  （連同本筆記、測試說明、PR 草稿的引用），重跑受影響的測試與兩個預檢。HM-10 若比本片先合併、改了 `make_apps` 的參數或 `ProfileGate`，
  `slot_busy` 的型別要跟著（`gateway.SlotBusy`）。`profile_runtime.py` 本片沒改。

## 15. 獨立安全審查意見處理（2026-11-16）

報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-14.md`（repo 外；證據在同層的 `evidence-review-HM-14/rerun-20261116/`）。
審查判定「修正後通過」：必修 2 項、建議 7 項；沒有碰到必須停下的待定題，但 MF-2 的第二步要使用者決定。每一項先核對再處理（審查員也可能錯）。
修正的證據在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-14/`（腳本、log、突變結果；log 裡測試執行時產生的
43 字元 token 已遮成 `[TOKEN43-REDACTED]`）。

### 15.1 處理表

| # | 意見 | 核對 | 處理 | 證據 |
|---|---|---|---|---|
| MF-1 | 「一個帳號的佇列滿了，別的帳號照樣排隊」沒有測試；突變 T03（排隊數跨帳號合計）存活 | 成立。程式本身對：每次 `make_apps` 各建一組 `Lane`，`take_slot` 只看自己的 `lane.waiting`。但唯一用到兩個帳號的佇列測試裡，預設帳號的名額是空的、走快速路徑，碰不到排隊上限。本機重跑 T03：作者的測試照過，存活（156 案全過：新 5 檔＋`test_profile_quotas.py`、`test_profile_routing.py`，本次新增的 11 案 deselect） | **採用**：`tests/test_gateway_queue_ha.py::test_one_profiles_full_queue_never_refuses_another_profiles_waiting_request`［B 滿｜預設滿］：兩個帳號唯一的名額都佔住、一方的佇列（上限 1）滿：那一方的下一個立刻拿佇列文字的 `-32003`；另一方的下一個照樣排在自己的佇列，名額空出後拿到結果。威脅模型 I8 的測試欄補上；第 15.4 節列 T03 | T03：加測試前存活、加測試後擋下（第 15.4 節） |
| MF-2 | 正式數值下，保留名額在准入滿時到不了；契約與 §9 沒寫 | 成立。准入（HM-08）在讀 body 前算，讀 body 中、排隊中、轉送中與開著的 GET 串流都算；准入＝轉送＋排隊（64＝32＋32、32＝16＋16）。本機重現：額外帳號排 15 個時通知 202，排滿 16 個時 503＋准入的文字 | **(a) 採用（寫明）**：契約 §2.4 一點、§5 一點、§9 #95（類型「待決」）；威脅模型第 3 節一條；本筆記第 3.3、11 節。審查的 E9 收成 `tests/test_carries_no_request.py::test_the_reserve_is_reached_only_while_the_profiles_admission_has_room`［15｜16］，**先釘住現況**，使用者選定做法後照選的改。**(b) 沒有自己定**：給准入留出保留名額的空間（例如預設 68、額外 36，改 DQ-07 的數值），或准入滿時先讀小請求、是通知就放行（改 HM-08 的分派器），交使用者在 HM-19c 前決定（第 11 節）。→ 2026-11-16 主對話定案：不改 DQ-07 的數值，交 HM-31 改分派器讀小請求（第 11、16.5 節） | 新測試在修正前後都過（釘住現況） |
| S-1 | SSE 已補 `-32004`，token 才在伺服器收下之後換掉：同一個 id 再補一則 `-32005` | 成立。`stream()` 補的 `-32004` 事件沒記成 `owner.reply_event`，yield 後也沒設 `owner.answered`，`Ending` 判斷回答沒送到。PaaS 同樣：`Pc/proxy.py:1192-1194` yield tail 之後直接 return、沒有 `delivered`。新測試在修正前紅：`[(7, -32004), (7, -32005)] == [(7, -32004)]` | **採用**：`gateway.py` 照審查的修法（事件設成 `owner.reply_event`，yield 後 `owner.answered = True`）；`UpstreamOwner`、`Ending` 的說明跟著改。契約 §2.5 一點、§9 #96（加嚴，建議回補；和第 3.5 節作者找到的同類競態放同一列）；列入給 PaaS 的回補建議（HM-29） | `tests/test_gateway_stream_endings.py::test_the_minus_32004_event_is_the_answer_and_no_minus_32005_follows_it`：修正前紅、修正後綠；突變 S1R（拿掉修法）擋下 |
| S-2 | 契約寫了、卻沒有測試擋住的四個行為（R05、R06、R12、R22 存活） | 成立。本機重跑四個突變，作者的測試都過：R05 117 案、R06 117 案、R12 124 案、R22 117 案全過（本次新增的 11 案 deselect） | **採用**：審查的 E2 收成 `test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session`［仍在執行｜停止了］（拿掉審查原本的 0.3 秒等待：`interrupted_answer` 先 `await owner.close()`，DELETE 在回應送出前就做完）；P2、P3 收成 `test_a_reply_the_server_had_not_taken_when_the_token_changed_gets_minus_32005`、`test_a_token_changed_as_the_last_message_is_taken_adds_nothing_after_it`（都在 `tests/test_gateway_stream_endings.py`） | 四個突變加測試後都擋下（第 15.4 節） |
| S-3 | 計畫 §16 的 UC-31 沒回答 | 成立 | **採用**：審查的 E6 收成 `tests/test_gateway_queue_ha.py::test_get_streams_hold_ordinary_slots_for_their_whole_life`（額外帳號的正式數值：8 條串流開著時同時只能跑 8 個 POST，第 9 個等 0.3 秒後拿 `-32003`，第 9 條串流立刻 429）；契約 §2.4 一點；UC-31 的答案見第 15.2 節 | 新測試 |
| S-4 | `MAX_REPORT_KEYS=64` 不夠：Odoo 6 個帳號 × 11 種情況＝66 時節流失效 | 成立。新測試在 64 時紅：3 輪寫了 198 行（應 66 行） | **採用**：`profile_router.MAX_REPORT_KEYS` 改 256，註解寫算法（66，加撞號組最多 57）。加 `tests/test_gateway_busy_shapes.py::test_every_situation_of_every_profile_stays_one_warning_a_minute`：經各帳號 gate 自己的回答走過 11 種情況、6 個帳號、同一分鐘 3 輪只寫 66 行；遠多於上限的 key 時記住的數量仍有界（HM-08 那個 200 個 key 的測試在 256 時碰不到淘汰，改由這個測試涵蓋）。PaaS `_MAX_REPORT_KEYS` 也是 64（#155 又加了 `body-*` 情況），列入回補建議 | 新測試：64 紅、256 綠；突變 S4R（改回 64）擋下 |
| S-5 | 四處文件或註記不準 | 成立（四處都核對過） | **採用**：(1) 契約 §2.5「唯一的例外」改成兩個例外；(2) 本筆記第 10 節 19f36e2 那列改成「不適用（HA 的位元組額度涵蓋排隊中的請求）」；(3) `gateway.py` 的 `slot_busy` 型別註記改成 `SlotBusy \| None`；(4) 可選的也做了：契約 §9 補 #98（子程式逾時 HA 502、PaaS 504，`Pc/proxy.py:1078-1079`），第 4.2 節「其他既有回應」的 502 補「逾時」 | — |
| S-6 | PaaS main 已到 `d7f5849`（#155） | 成立。本機唯讀重查：`5b84b5d..d7f5849` 是 #155（`7ba572d`、`3b135ca`、`e6971c0`、`1637a0f`、`a2f8905`）；HM-14 的符號只多一行 `CLIENT_CLOSED_REQUEST`（上傳讀到一半用戶端離開的回應，不是排隊）；四個測試檔沒動 | **採用**：第 1、10 節改列到 `d7f5849`，寫明 #155 不影響本片。要不要另開片：使用者 2026-11-16 07:1x 已決定對齊 #155、所有產品都生效，計畫已新增 **HM-31**（排在本片之後），不用再問 | — |
| S-7 | 排隊中 token 被換掉時，HA 最多多等 1 秒才拒（PaaS 立刻取消） | 成立；結果相同（一定被拒、子程式收不到；審查 E4） | **只寫明，不改程式**：契約 §2.4 一點、§9 #97。理由：把 `take_slot` 放進 `lease.run` 時，「拿到名額」與「token 換掉」在同一刻完成會漏掉名額（`lease.run` 丟 `AccessChanged`、呼叫端拿不到 "taken"），要另寫歸還與測試，動到本片最細的名額帳目；換到的只是最多 1 秒的排隊位置。留到後續（HM-29 整理回補時一起看） | — |

### 15.2 UC-31 與審查的其他觀察

- **UC-31（計畫 §16）：是。** GET 串流整段佔住一條一般名額與一個准入（新測試；審查 E6）。額外帳號開滿 8 條串流時 POST 剩 8 條名額，
  預設帳號開滿 24 條時剩 8 條；這和 PaaS「串流上限小於連線上限，POST 仍有名額」的設計一致。這個事實也是 MF-2 的一部分。
- HM-09 合併後重看：HM-09 加的 `blocked` 狀態（預檢失敗就不再自動重啟）會被 `child_runs` 判成「停止了」，判斷沒問題；但 `-32004`
  文字的「會自動重新啟動」對 `blocked` 的子程式不成立。rebase 時看要不要改文字（第 14 節）。→ rebase 後已改（第 16.4 節）。
- `-32005` 的文字讓舊 token 的持有人知道「token 被輪替或撤銷」：和密鑰網址「錯 token 一律 404、不說原因」不同，但只發生在已經連上的串流，
  PaaS 同樣；審查認為可以接受，照舊。
- 計畫 §5.2 的表格（repo 外）建議補一句准入與保留名額的關係：交主對話。
- 審查的 W04（密鑰網址的 `-32004` WARNING 帶出路徑）與 ICE（`ConnectError` 也算中途斷線）是等價突變：W04 被 HM-02 的 record factory
  遮成 `/private_[REDACTED]`，ICE 在可開通的產品都先走 listing 的 `ConnectError` 分支。本片照審查的判斷，沒有為它們加測試。

### 15.3 審查修正後的本機檢查（2026-11-16，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 都排隊在共用鎖）

| 檢查 | 結果 |
|---|---|
| 先紅（`1ec350a` 的樹：測試是新的、程式是 `7df3138`；在複本跑） | 新 5 檔＋`test_reply_mask_union.py` 136 案：**2 失敗、134 通過**，18.4 秒。失敗的正是預期的兩案：S-1 `[(7, -32004), (7, -32005)] == [(7, -32004)]`；S-4 `64 == 198`（同一分鐘 3 輪寫了 198 行）。其餘 9 個新案釘住今天就成立的行為，用第 15.4 節的突變證明會紅 |
| 綠（程式＝`064a226`） | 同上 136 案全過、0 skip，18.6 秒；新 11 案本機合計 2.2 秒（最慢 0.46 秒，UC-31） |
| 相關既有 33 檔（審查的 31 檔＋讀帳本的 `test_tool_inventory.py`、`test_redaction_matrix.py`；含 HM-01 黃金回歸與兩個契約凍結、HM-08 的 routing／quotas／passthrough、log 掃描、兩個預檢的測試、`test_profile_runtime.py`、`test_upgrade_zero_rewrite.py`、`test_active_token_leases.py`、`test_profile_index.py`、閘道相關既有檔） | **1424 案全過、0 skip**，387.6 秒（審查重跑的 31 檔是 1309 案；加上 `test_tool_inventory.py` 8 案、`test_redaction_matrix.py` 107 案） |
| 突變 | 第 15.4 節 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| packaging unittest（照 CI：離線暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py`（漂移檢查，同 unit.sh） | exit 0（沒動 `apps/runtime`、`launch.py`） |
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full`：gitleaks 8.28.0（釘版、已驗）；`b5d10c5..HEAD` 10 個 commit（含審查修正的 5 個與本筆記）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery`：172／70／159 檔 0 漂移、0 缺；改到的 3 個列管檔都有帳本更新；沒有沒列管的新執行檔：**OK** |
| 全套 pytest | 審查修正後**沒有重跑**：程式只改 SSE `-32004` 那一段（開通時才走）、WARNING 節流上限與一個型別註記（`from __future__ import annotations`，執行時不求值）；走到這些路徑的測試都在上面兩列。實作時（`c06eb43`）全套 5394 案只剩 7 個要 root 的既有案例（第 7 節）。CI 以 root、0 skip 全跑 |
| 暫存目錄、`git status` | 每個 `/tmp/ha-mp-*` 都已用完整路徑刪除；審查修正用的複本也已刪除；`git status` 乾淨 |

### 15.4 突變（審查修正後）

腳本 `evidence-fix-HM-14/bin/mutate.py`（照審查的 `mutate.py`；GEV 改成修正後的程式文字，加 S1R、S4R）。每個突變只改正式程式一處、改完可編譯、
`pytest -x`，跑完逐位元還原並以 SHA-256 核對。「加測試前」在 `1ec350a` 的複本跑（程式＝`7df3138`），把本次新增的 8 個測試函式（11 案）deselect 掉；
「加測試後」在本 clone 跑（程式＝`064a226`），用全部測試。

| # | 突變 | 加測試前（作者的測試） | 加測試後（全部測試） |
|---|---|---|---|
| T01 | 名額等候逾時、帶 id 的請求回 503（不是 200＋-32003） | （沒重跑；審查：擋下） | 擋下（`test_a_busy_lane_answers_as_the_paas_table_and_the_session_goes_on`；1 failed in 1.83s） |
| T02 | GET 串流滿不回 429（改回 503＋-32003、Retry-After 5） | （沒重跑；審查：擋下） | 擋下（`test_the_stream_cap_answers_429_at_once_and_posts_still_work[default]`；1 failed, 3 passed in 3.93s） |
| T03 | 排隊上限改成全帳號共用（同一種佇列的排隊數跨帳號合計；名額仍每帳號一份） | 存活（156 passed, 11 deselected in 31.50s） | 擋下（`test_one_profiles_full_queue_never_refuses_another_profiles_waiting_request[B's queue full]`；1 failed, 19 passed in 3.46s） |
| T03b | 整組名額與佇列全帳號共用一個（共用池） | （沒重跑；審查：擋下） | 擋下（`test_request_abandoned_while_queued_never_reaches_the_child_on_a_real_listener`；1 failed, 16 passed in 17.50s） |
| T04 | 排隊中用戶端斷線，請求照樣在名額空出後送出（不看斷線） | （沒重跑；審查：擋下） | 擋下（`test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent`；1 failed in 31.12s） |
| T05 | 保留名額接受夾帶請求的 batch（非空陣列一律算沒有請求） | （沒重跑；審查：擋下） | 擋下（`test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane[batch of a notification and a request]`；1 failed, 9 passed in 1.03s） |
| T06 | 開通時 token 換掉仍把 ClientDisconnect 丟給 uvicorn（不用閘道的結尾） | （沒重跑；審查：擋下） | 擋下（`test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event`；1 failed, 13 passed in 5.77s） |
| T07 | 開關關時子程式的 initialize 錯誤又原樣轉回（只在開通時遮） | （沒重跑；審查：擋下） | 擋下（`test_switched_off_a_childs_initialize_error_is_masked_with_the_profiles_own_credentials`；1 failed, 6 passed in 1.56s） |
| R05 | initialize 斷線且子程式停止時仍 DELETE 那個 session（會打到下一代） | 存活（117 passed, 11 deselected in 15.68s） | 擋下（`test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session[stopped]`；1 failed, 8 passed in 3.48s） |
| R06 | initialize 回覆讀到一半斷線不回 -32004（照舊 502／503） | 存活（117 passed, 11 deselected in 15.58s） | 擋下（`test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session[still running]`；1 failed, 7 passed in 3.10s） |
| R12 | Ending 不看 delivery.completed（回應已完整送出後仍補結尾） | 存活（124 passed, 11 deselected in 18.08s） | 擋下（`test_a_token_changed_as_the_last_message_is_taken_adds_nothing_after_it`；1 failed, 17 passed in 6.18s） |
| R22 | SSE 回覆在被伺服器收下之前就算「已送到」（answered 提前設） | 存活（117 passed, 11 deselected in 15.57s） | 擋下（`test_a_reply_the_server_had_not_taken_when_the_token_changed_gets_minus_32005`；1 failed, 16 passed in 6.31s） |
| W04 | 密鑰網址上 -32004 的 WARNING 帶出路徑（路徑就是 token；只在 /private_ 路徑加） | （沒重跑；審查：存活（等價）） | 存活（128 passed in 17.68s）；等價（HM-02 的 record factory 已把 `/private_<secret>` 遮成 `/private_[REDACTED]`） |
| WL1 | 拿到名額的排隊請求不把排隊數減回去（排隊數漏算，佇列最後永遠「已滿」） | （沒重跑；審查：擋下） | 擋下（`test_a_request_that_waited_for_a_slot_keeps_holding_it_until_its_response_closes[ordinary]`；1 failed, 5 passed in 1.36s） |
| ICE | 連不上子程式（ConnectError）也算中途斷線（-32004，不走今天的自答／session 結束／502） | （沒重跑；審查：存活（等價）） | 存活（167 passed in 33.29s）；等價（可開通的產品都有 listing，`ConnectError` 先走自答或 session 結束） |
| GEV | GET 串流中途斷線也補一則 -32004 事件（id null） | （沒重跑；審查：擋下） | 擋下（`test_an_event_stream_broken_mid_reply_gets_one_minus_32004_event_and_ends[still running]`；1 failed, 9 passed in 4.10s） |
| S1R | 拿掉 S-1 修法：-32004 事件不記成那個請求的回答（之後換 token 會再補 -32005） | （新的突變） | 擋下（`test_the_minus_32004_event_is_the_answer_and_no_minus_32005_follows_it`；1 failed, 15 passed in 5.97s） |
| S4R | MAX_REPORT_KEYS 改回 64（Odoo 6 個帳號 66 種情況時節流失效） | （新的突變） | 擋下（`test_every_situation_of_every_profile_stays_one_warning_a_minute`；1 failed, 3 passed in 3.73s） |

每個突變跑完都逐位元還原並以 SHA-256 核對：全部 OK。

### 15.5 審查修正的 commit

| commit | 內容 |
|---|---|
| `1ec350a` | 測試（4 檔 11 案；先紅：在 `7df3138` 的程式上 S-1 與 S-4 的兩案紅，其餘 9 案釘住今天就成立的行為） |
| `064a226` | 程式：S-1、S-4、S-5 第 3 點 |
| `f6d2f8d` | 帳本：`gateway.py`、`profile_router.py` 重算 SHA-256、補說明 |
| `bbf6480` | 契約與威脅模型 |
| 本筆記的 commit | 本筆記的結論與第 1～3、6～15 節 |

## 16. rebase 到 `claude-delivery` `c523474`（HM-09 合併後，2026-11-16）

### 16.1 範圍

- 基準從 `b5d10c5` 換成 `c523474`（`git rebase --onto origin/claude-delivery b5d10c5`；`git fetch origin claude-delivery` 之後）。中間合併的是
  #100（`cf62c8f`：`checks` 上限 40→60 分鐘）與 HM-09（#101：`c03cd4d`～`7085bf7`，14 個 commit）。
- 和本片重疊的檔：`Hc/gateway.py`（HM-09：`make_apps` 多 `child_blocked`、說明多一段、`child/restart` 的 202 帶 `blocked_reason`）、
  `docs/multi-profile/contract.md`（HM-09：第 5、7 節、第 9 節第 89 列與 #14 的附註、說明段、第 10 節兩列）、`docs/provenance/runtime-patches.json`
  （HM-09：`gateway.py`、`lifecycle.py`（新列管）、`profile_runtime.py`、`profiles.py`、`run_product.py`）、`tests/test_reply_mask_union.py`
  （HM-09 在別的測試加一行）。`decisions.md`、`profile_router.py`、`access.py` 本片改、HM-09 沒改（或反之），沒有衝突。
- `git log origin/claude-delivery..HEAD` 只剩本片的 commit（rebase 過來的 10 個，加上 rebase 後的 7 個；第 16.11 節）。

### 16.2 衝突與處理

| rebase 後的 commit（原本） | 衝突 | 處理 |
|---|---|---|
| `7b49885`（`c06eb43`） | `gateway.py` 的 `make_apps` 說明：HM-09 加的那段與本片加的兩段 | 兩邊都留，照合併順序 HM-08 → HM-09 → HM-14；簽名由 git 自動合併（HM-09 的 `child_blocked` 在） |
| `d479ab0`（`148626d`）、`63b77e3`（`f6d2f8d`） | 帳本 `gateway.py` 的 `change` 與 `sha256` | 不只解文字：以 `claude-delivery` 的帳本為底，加回原 commit 在 `change` 後面補的那段（HM-09 的說明在前、本片的在後），三個列管檔的 `sha256` 用合併後的實際內容重算（腳本 `SP:hm14-rebase-20261116/bin/merge_ledger.py`；`access.py`、`profile_router.py` 兩邊只有本片改，摘要和原本相同；`gateway.py` 是新的值）。JSON 照 repo 的格式（`indent=2`、`ensure_ascii=False`）寫回，逐位元可重現 |
| `310229c`（`3366d9b`）、`28869c8`（`bbf6480`） | 契約第 9 節說明段、表格最後、第 10 節變更紀錄 | 說明段合寫（第 89 列是 HM-09 的、第 90～94 列出自 HM-14 的實作、第 95～98 列出自 HM-14 的審查）；表格留 HM-09 的第 89 列，本片的列改成第 90～98 列；變更紀錄兩邊的列都留（HM-09 的兩列在前）。本片加的行裡對這些列的引用一起加一（腳本 `SP:hm14-rebase-20261116/bin/renumber.py`：只改原 commit 加的行、而且不是 `claude-delivery` 本來就有的行；第 16.3 節） |
| `db89f24`（`064a226`） | `make_apps` 的簽名 | `slot_busy: SlotBusy \| None`（本片 S-5）與 HM-09 的 `child_blocked` 都留 |
| 其他 4 個 | 沒有衝突 | 測試 `3c12b71`、`d662684`；筆記 `288e1ab`、`69e132a`（筆記裡的列號在 `8b93111` 跟著改） |

核對：程式與 `test_reply_mask_union.py` 的「rebase 後減 rebase 前」逐行等於 HM-09 與 #100 帶進來的改動（`git diff b5d10c5 origin/claude-delivery`
對 `git diff 351666f HEAD`；`gateway.py` 只差說明段接在哪一行）；契約與威脅模型「本片的改動」rebase 前後只差列號加一與合寫的說明段。

### 16.3 列號重編（HM-09 用了第 89 列）

| 原本 | rebase 後 | 項目 |
|---|---|---|
| #89 | #90 | 保留名額載的東西 |
| #90 | #91 | token 換掉時標頭已送出的 JSON 回覆 |
| #91 | #92 | `-32004` 的 log |
| #92 | #93 | initialize 換代的回應 |
| #93 | #94 | 標頭卡在背壓時換 token |
| #94 | #95 | 保留名額與准入（待決；MF-2 (b) 交 HM-31） |
| #95 | #96 | 一個請求只回一則（SSE 的 `-32005`） |
| #96 | #97 | 排隊中換 token |
| #97 | #98 | 子程式逾時（回應標頭前） |
| — | #99 | 子程式停止後 `-32004` 的文字（rebase 後新加；第 16.4 節） |

引用改了：契約第 2.4、2.5、4.2、5 節、第 9 節說明段與表格、第 10 節；威脅模型第 3 節兩處（以上在 rebase 解衝突時）；本筆記 24 行與兩個測試說明
（`tests/test_carries_no_request.py`、`tests/test_gateway_stream_endings.py`；`8b93111`，只改數字）。PR 草稿（repo 外）照新列號寫。
本筆記第 1～15 節的文字照 rebase 前寫的，只有列號跟著改；commit 編號是 rebase 前的（對照見第 16.11 節）。HM-20 若先合併又補了第 9 節的列，
開 PR 前再照同樣的做法重編一次。

### 16.4 HM-09 合併後的重看：`blocked` 與 `-32004` 的文字

- 判斷沒問題：HM-09 加的 `blocked`（還有 `failed`、`backoff`）都不是 `running`，`child_runs` 判成「停止了」；停止時 initialize 的 session 照舊不 DELETE。
- 文字要改：PaaS 的「會自動重新啟動」（`CHILD_STOPPED_TEXT`）只在 HM-09 的看門狗會再起子程式時成立。照 HM-09 的語意（契約第 7 節）：

  | 停止那一刻的 `Supervisor.status` | 誰讓它再起 | `-32004` 的文字 |
  |---|---|---|
  | `backoff` | 看門狗等退避（2→300 秒）後自己再起 | 會自動重新啟動（PaaS 原文） |
  | `starting`、新世代的 `running` | 已經在起、已經起好（面板重啟、存檔、看門狗） | 會自動重新啟動 |
  | `blocked` | `Supervisor.block`（停用的帳號、記憶體不夠、索引內撞號）：沒有人自動再起，要存檔、面板重啟或索引改了；spawn 前檢查拒絕（port 衝突或被佔）：看門狗退避後再查，port 空出來才起 | 目前沒有在重新啟動（`CHILD_HALTED_TEXT`） |
  | `failed` | 監看停止（DQ-21）：存檔或面板重啟才再起 | 目前沒有在重新啟動 |
  | `stopped` | 帳號被刪、add-on 在停：不會再起 | 目前沒有在重新啟動 |
  | `unconfigured` | 沒有存連線：存了才起 | 目前沒有在重新啟動 |

  spawn 前檢查拒絕的 `blocked` 之後可能被看門狗再起，所以新文字只說「目前沒有在重新啟動」，不說永遠不會；原因寫在 add-on log（HM-09 的
  `not started (<原因碼>)` 等 WARNING）。
- 做法（`64105d4`）：`gateway.CHILD_RESTARTING_STATES`（`backoff`、`starting`、`running`）、`CHILD_HALTED_TEXT`（英文加繁中，同其他固定文字），
  `make_apps` 的 `interruption_text`：在 `child_stopped` 判定之後、沒有 await 之前讀狀態（`interrupted_answer` 在 `await owner.close()` 之前），
  標頭前的 502 與 SSE 事件共用。沒有健康監看可比（沒有世代）時照原本的說法。WARNING 照舊只分「停止了」與「仍在執行」（帳號的情況數不變，
  `MAX_REPORT_KEYS` 的算法不用改）。開關關的產品不受影響（`-32004` 只在開通時用）。
- 契約第 2.5 節（三種文字與狀態）、第 4.2 節 `-32004` 列、第 9 節第 99 列（加嚴，建議回補 PaaS：PaaS 的註解把「被擋下」也算進
  「會自動重新啟動」那一種；HM-29）；威脅模型第 3 節一句。
- 測試（`2333eca`）：`tests/test_gateway_stream_endings.py::test_a_stopped_child_is_said_to_restart_only_while_it_comes_back_by_itself`
  ［backoff｜starting｜replaced｜blocked｜failed｜stopped｜unconfigured］：子程式斷線那一刻把 `Supervisor` 放到那個狀態（`blocked` 用真的
  `Supervisor.block`），標頭前的 502 與已開始的 SSE 事件都驗文字；每種文字都有「操作可能已完成也可能沒有」；WARNING 說 the MCP server stopped。

### 16.5 MF-2 (b) 的定案（主對話 2026-11-16 07:5x）

不改 DQ-07 的數值；「保留名額在准入滿時也有效」交 HM-31（對齊 PaaS #155）一起做：照 PaaS 的語意，准入滿時仍讀 ≤64 KiB 的小請求，
是通知或回應就走保留名額。本片照現在的寫法：契約 §9 #95 類型維持「待決」、說明改成「交 HM-31，主對話 2026-11-16 定案：不改 DQ-07 數值，
改分派器讀小請求」；第 2.4、5 節與威脅模型第 3 節同步；`test_the_reserve_is_reached_only_while_the_profiles_admission_has_room` 照舊釘住現況
（只改說明）。`decisions.md` 不加新題（`61aee83`）。

### 16.6 HM-09 的錯開啟動與 initialize 世代的兩個測試

rebase 後第一輪跑新 5 檔，`tests/test_initialize_generation.py` 有 4 案紅（`test_an_initialize_whose_generation_changed_is_not_handed_out`
［restarted｜exited｜stopped］、`test_an_initialize_to_the_running_generation_is_handed_out_as_before`）：B 的子程式替身多開了一個 session
（`opened` 是 2、session 名稱是 `-session-2`）。原因在測試的假設，不在程式：HM-09 的錯開啟動（`ProfileManager.start_all` 的 `_started` →
`HealthMonitor.settle`）在測試開始前就讓 B 的子程式回一次健康檢查，那次檢查的 initialize（clientInfo `local-readiness`）也算進替身的
`opened`，結束時還送一個清理用的 DELETE（`health.py`）。HM-09 之前 `ProfileManager.monitor()` 只跑預設帳號的監看，額外帳號的子程式不會被
檢查。`915f9e6` 改成只看為用戶端開的 session：`opened` 和送出前比（多 1）、session 名稱照當下的 `opened` 而且不是健康檢查的 session
（`GatewayChild.checks`）、「沒有 DELETE」只算用戶端的 session。測試要證明的事沒變；其他 139 案在第一輪就全過。

### 16.7 本機檢查（2026-11-16，一般使用者；TMPDIR 用 ha_env.sh 給的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 都排隊在共用鎖）

證據在 repo 外：`SP:hm14-rebase-20261116/`（`bin/` 腳本、`logs/` 的 pytest log 與 junit、`evidence/` 的突變結果與 SHA-256 核對）。

| 檢查 | 結果 |
|---|---|
| 先紅（`gateway.py` 換成 `2333eca` 的內容＝只有新測試、程式還沒改；跑完逐位元還原並核對 SHA-256，3 個 OK） | 新測試 7 案：**4 失敗、3 通過**，1.75 秒。失敗的正是 blocked、failed、stopped、unconfigured（還說「會自動重新啟動」）；通過的 backoff、starting、replaced 釘住今天就成立的行為 |
| 第一輪新 5 檔＋`test_reply_mask_union.py`（程式＝`64105d4` 之後） | 143 案 **4 失敗**、139 通過：`test_initialize_generation.py` 的 4 案，原因是 HM-09 的錯開啟動先檢查了子程式（第 16.6 節）；`915f9e6` 改測試 |
| 第二輪新 5 檔＋`test_reply_mask_union.py`（head `915f9e6`） | **143 案全過、0 skip**，19.06 秒（新 5 檔 135 案：審查修正後 128 案＋rebase 後 7 案；新的 7 案合計 0.58 秒） |
| 相關既有 33 檔（第 15.3 節同一組） | **1424 案全過、0 skip**，388.1 秒 |
| 突變 | 第 16.8 節 |
| 全套 pytest（`tests/`；head `915f9e6`） | 5531 案、0 skip、31 分 52 秒：**5502 通過**；29 失敗＝7 個要 root 的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5，同第 7 節）＋22 個瀏覽器測試（`test_owned_browser_redirect.py` 16、`test_owned_browser_ipc.py` 5（只有 browser=True 的那幾個）、`test_owned_ui.py` 1）：這個 clone 沒有 Chromium（`packages/mcp-admin-ui/node_modules/playwright-core/.local-browsers` 不在：node_modules 在 2026-11-16 07:25 重裝過，之後沒裝瀏覽器；17 案直接寫 `Executable doesn't exist`，IPC 的 5 案是瀏覽器起不來、沒有回覆）。裝 Chromium 要從 Playwright 的下載站下載，任務規則不准連 GitHub 以外的網路，所以沒裝；CI 的 `packaging/unit.sh` 會先 `npm run browser:install` 再跑。這 22 案只測管理面板的瀏覽器擁有權，本片沒有動到它們或它們測的程式。沒有別的失敗；2 個 warning 是既有的 websockets DeprecationWarning |
| `packaging/validate.py`（ci-venv 的 Python） | PASS（head `61aee83`；之後只動 `tests/` 與筆記） |
| packaging unittest（照 CI：離線暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準） |
| `scripts/tool_inventory.py`（漂移檢查，同 unit.sh） | exit 0（沒動 `apps/runtime`、`launch.py`） |
| 暫存目錄 | 每個 `/tmp/ha-mp-*` 都已用完整路徑刪除（`logs/tmpdirs.txt`）；`git status` 只有本筆記沒 commit |

### 16.8 突變（rebase 後）

腳本 `SP:hm14-rebase-20261116/bin/mutate.py`（第 15.4 節的 18 個，錨點照 rebase 後的程式核對過；加 H01～H05）。每個只改正式程式一處、改完可編譯、
`pytest -x`（全部測試，沒有 deselect），跑完逐位元還原並以 SHA-256 核對：**23 個都還原 OK**。結果：**21 個擋下**；W04、ICE 照審查的判斷是等價突變（存活）。

| # | 突變 | 結果（擋下的第一個測試） |
|---|---|---|
| T01 | 名額等候逾時、帶 id 的請求回 503 | 擋下（`test_a_busy_lane_answers_as_the_paas_table_and_the_session_goes_on`） |
| T02 | GET 串流滿不回 429 | 擋下（`test_the_stream_cap_answers_429_at_once_and_posts_still_work[default]`） |
| T03 | 排隊上限跨帳號共用 | 擋下（`test_one_profiles_full_queue_never_refuses_another_profiles_waiting_request[B's queue full]`） |
| T03b | 名額與佇列全帳號共用一個 | 擋下（`test_request_abandoned_while_queued_never_reaches_the_child_on_a_real_listener`） |
| T04 | 排隊中斷線照樣送出 | 擋下（`test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent`） |
| T05 | 保留名額接受夾帶請求的 batch | 擋下（`test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane[batch of a notification and a request]`） |
| T06 | 開通時仍把 ClientDisconnect 丟給 uvicorn | 擋下（`test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event`） |
| T07 | 開關關時 initialize 錯誤原樣轉回 | 擋下（`test_switched_off_a_childs_initialize_error_is_masked_with_the_profiles_own_credentials`） |
| R05 | 子程式停止時仍 DELETE initialize 的 session | 擋下（`test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session[stopped]`） |
| R06 | initialize 讀到一半斷線不回 -32004 | 擋下（`test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session[still running]`） |
| R12 | Ending 不看 delivery.completed | 擋下（`test_a_token_changed_as_the_last_message_is_taken_adds_nothing_after_it`） |
| R22 | 回覆被收下之前就算已送到 | 擋下（`test_a_reply_the_server_had_not_taken_when_the_token_changed_gets_minus_32005`） |
| W04 | 密鑰網址 -32004 的 WARNING 帶出路徑 | 存活（135 passed；等價：HM-02 的 record factory 已遮） |
| WL1 | 拿到名額不把排隊數減回去 | 擋下（`test_a_request_that_waited_for_a_slot_keeps_holding_it_until_its_response_closes[ordinary]`） |
| ICE | ConnectError 也算中途斷線 | 存活（174 passed；等價：可開通的產品都有 listing） |
| GEV | GET 串流斷線也補 -32004 事件 | 擋下（`test_an_event_stream_broken_mid_reply_gets_one_minus_32004_event_and_ends[still running]`） |
| S1R | 拿掉 S-1 修法 | 擋下（`test_the_minus_32004_event_is_the_answer_and_no_minus_32005_follows_it`） |
| S4R | MAX_REPORT_KEYS 改回 64 | 擋下（`test_every_situation_of_every_profile_stays_one_warning_a_minute`） |
| H01 | `blocked` 也算會自己再起 | 擋下（`test_a_stopped_child_is_said_to_restart_only_while_it_comes_back_by_itself[blocked]`） |
| H02 | 停止了一律說會自動重新啟動（rebase 前的行為） | 擋下（同上［blocked］） |
| H03 | 停止了一律說目前沒有在重新啟動 | 擋下（`test_a_child_that_stopped_during_the_request_is_reported_stopped[exited]`） |
| H04 | SSE 的 -32004 事件不看狀態 | 擋下（新測試［blocked］的 SSE 那一半） |
| H05 | 標頭前的 502 不看狀態 | 擋下（新測試［blocked］的 502 那一半） |

### 16.9 預檢

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗）；`c523474..HEAD` 17 個 commit（含本筆記）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 173 檔（HM-09 起多列管 `lifecycle.py`）、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的 3 個列管檔都有帳本更新；沒有沒列管的新執行檔：**OK** |

兩個預檢跑的時候 `origin/claude-delivery` 已 fetch 到 `269f5a5`（HM-20 合併後）；兩個腳本都以 merge base（`c523474`）起算。

### 16.10 PaaS 變動

本機 PaaS clone（唯讀，沒 fetch、沒 checkout）的 `origin/main` 仍是 `d7f5849`，和第 10 節寫的相同；#155 由 HM-31 對齊，本片不做。
新的第 99 列引用的 `Pc/proxy.py:57-62`（`CHILD_INTERRUPTED_MESSAGE` 與它的註解）是 pin `69ac425` 的行號；`d7f5849` 上是第 59～64 行，文字相同。

### 16.11 commit（rebase 後）

rebase 過來的 10 個（第 1～15 節寫的是左欄的編號）：

| rebase 前 | rebase 後 | 內容 |
|---|---|---|
| `543eabc` | `3c12b71` | 測試（新 5 檔＋測試工具） |
| `c06eb43` | `7b49885` | 程式（`gateway.py`、`access.py`、`profile_router.py`） |
| `148626d` | `d479ab0` | 帳本（三個列管檔） |
| `3366d9b` | `310229c` | 契約與威脅模型 |
| `7df3138` | `288e1ab` | 本筆記 |
| `1ec350a` | `d662684` | 審查修正的測試 |
| `064a226` | `db89f24` | 審查修正的程式 |
| `f6d2f8d` | `63b77e3` | 審查修正的帳本 |
| `bbf6480` | `28869c8` | 審查修正的契約與威脅模型 |
| `351666f` | `69e132a` | 本筆記（審查修正） |

rebase 後加的 7 個：

| commit | 內容 |
|---|---|
| `8b93111` | 本筆記與兩個測試說明的列號跟著加一（只改數字） |
| `2333eca` | 測試：停止了的 `-32004` 文字看 HM-09 的狀態（7 案；先紅：4 失敗、3 通過） |
| `64105d4` | 程式：`CHILD_RESTARTING_STATES`、`CHILD_HALTED_TEXT`、`interruption_text` |
| `9232c77` | 帳本：`gateway.py` 重算 SHA-256、補說明 |
| `61aee83` | 契約與威脅模型：`-32004` 三種文字與第 99 列、MF-2 (b) 的定案；釘住現況的那個測試說明 |
| `915f9e6` | 測試：HM-09 的錯開啟動之後只看為用戶端開的 session（第 16.6 節） |
| 本筆記的 commit | 第 16 節與第 1～3、11、14、15 節的更新 |
