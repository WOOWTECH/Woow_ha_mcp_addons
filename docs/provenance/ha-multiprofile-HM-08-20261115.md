# HA 多帳號 HM-08 provenance：MCP token 路由、每帳號准入與位元組額度、過載回應、回覆遮罩聯集（2026-11-15）

## 結論

- **產品沒開通時，行為一行都不變**：`run_product` 照舊建預設帳號的 `ProfileRuntime`，8081 掛預設帳號自己的 app，兩個
  listener 都是 `limit_concurrency=64`，不讀索引、不掃 `profiles/`、不碰 FD 上限（測試用「一呼叫就失敗」的替身鎖住）。
  HM-01 的黃金回歸與兩個契約凍結照過，斷言一個字都沒改。repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **產品開通後**（測試用 monkeypatch 打開）：
  - 8081 改掛新的分派器 `profile_router.McpDispatcher`：只看路徑與 `Authorization`，候選 token sha256 一次，和每個可路由帳號的
    摘要全部比完（`hmac.compare_digest`，不提早結束）。剛好一個 → 該帳號的准入與額度 → 該帳號自己的 app（再驗一次 token）；
    零個 → 預設 app 原樣回 404／401（逐位元同今天）；兩個以上 → 503 `{"error":"state unavailable"}`（DQ-09）；索引壞、索引被外改
    （到重啟為止）、預設 state 讀不到 → 每個 token 都 503（DQ-12），`/health/ready` 回 not ready（DQ-19）。
  - 每個帳號（含預設帳號）自己的准入（64／32）、位元組額度（64 MiB）、GET 串流上限（24／8）、轉送名額（32／16）、子程式
    httpx client（40／24）。沒有共用池。
  - 過載回應照 PaaS 表：讀 body 前就拒絕的請求，用全 add-on 共用的「拒絕小額度」（同時 8 個、合計 512 KiB、每個 ≤64 KiB、2 秒）
    只讀出 JSON-RPC id：有 id 200＋`-32003`＋`Retry-After: 5`，其他 503；轉送名額等 1 秒逾時同形狀；串流滿 429＋`Retry-After: 30`。
    WARNING 每帳號每情況 60 秒一行（id 前 8 碼、`suppressed=N`）。
  - 回覆遮罩＝本帳號的 `secret_values` ∪ 全 add-on 每個帳號（含孤兒）目前的 token 與 child_token（DQ-40 ⑧）。
  - `ProfileManager` 骨架（登錄、查詢、每帳號 httpx client、共用 `SharedAdmin`）。**額外帳號的子程式還不起**：HM-09 加
    `start_all`／`stop_all`（介面寫在第 3.5 節與 `ProfileManager` 的說明）。
- 新測試 4 檔共 89 案（路由 22、開關 49、名額 12、遮罩 6）＋1 個測試工具模組；改 2 個既有測試檔（HM-05、HM-07 交代要改的地方）。
  **先寫測試**：實作前 191 案裡 71 失敗、120 通過（通過的是「開關開時照舊」的鎖與既有測試），實作後全過（第 4.1 節）。
  臨時突變 32 個，全部被擋下（第 4.2 節）。
- 6 帳號解析成本（第 12 節）：本機（AMD EPYC 7713）每次解析平均約 70～100 µs（12 次 `lstat`，0 次讀檔）；6 份 state 都換過時約 0.73 ms。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。全套 pytest（帳本更新前）：5270 案、0 skip、30 分 30 秒，5239 通過；
  31 失敗＝帳本還沒更新的 2 案（更新後重跑通過）＋這個 clone 沒裝 Chromium 的 22 個瀏覽器測試（照 CI 裝好後重跑通過）＋7 個已知
  要 root 的既有案例（只在 CI 驗）（第 5 節）。
- **獨立安全審查還沒做**（計畫 §12.0 第 9 點：合併前做；報告放 `artifacts/`）。這個階段只 commit，不 push、不開 PR。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-08（計畫 §12.3；風險高、工作量 L；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm08-20261115`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `76c1d78`（HM-00、01、02、04、05、06、07、13a、17 已合併） |
| 依據 | 計畫 §3、§5.1、§5.2、§7.2、§7.3、§8.2（I1、I2、I3、I7、I8）、§8.6、§8.8、§10.3、§12.3 HM-08；契約 §1.2、§2、§4.2、§5、§9；FM-05、13、14、27、28、29、30、32、49、50、67、76、149、150、151；HM-01、HM-05、HM-07 provenance 筆記交給 HM-08 的事項（第 14.1 節） |
| 對齊的 PaaS | 沒有移植 PaaS 程式。行為期望值來自 `woow-mcp-server` @`69ac425`：`profiles.py` `resolve_token`（逐帳號比、撞號 503、壞的額外帳號略過）、`proxy.py` `_gateway_error`／`_busy_message`／`_stream_limit_message`（`-32003`、有 id 200、Retry-After 5／30）、`gateway_pool.py` 的 60 秒 WARNING、`docs/mcp-gateway-limits.md`「超過上限時用戶端拿到什麼」表。到 main `cf3d0d5` 這些檔只改了註解、文件與測試（第 9 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/profile_router.py`（新） | `McpDispatcher`（8081 分派器）、`ProfileGate`（每帳號准入、位元組額度、串流上限、`slot_busy`）、`RefusalAllowance`（拒絕小額度）、`Reports`（60 秒一行的 WARNING）、`Credentials`（每帳號 token 摘要與簽章快取、額外帳號目錄比對）、四段 `-32003` 文字 |
| `Hc/profile_runtime.py` | `ProfileRuntime` 多 4 個 keyword-only 參數（`child_connections`、`forward_slots`、`slot_busy`、`reply_secrets`；不給時照舊）與類別屬性 `mcp_listener_limit = 64`；新 `ProfileManager`、`RegisteredProfile`、`open_file_budget`、`raise_open_file_limit`、`held_tokens`（只讀孤兒的 token 給遮罩用） |
| `Hc/gateway.py` | `make_apps` 多 3 個 keyword-only 參數：`forward_slots`、`slot_busy`、`reply_secrets`（不給時照舊：32 個名額、逾時 503 `{"error":"request denied"}`、只用本帳號秘密遮）；`masks(state)` 統一 5 處遮罩與被拒 tools/call 的健康原因；路由樣板常數 `MCP_ROUTE`、`SECRET_ROUTE`、`READY_ROUTE`（分派器用同一份）；`FORWARD_SLOTS`、`FORWARD_WAIT_SECONDS`（值同原本的 32、1）；`request_id`、`busy_reply`、`stream_busy_reply`；`PROFILE_ID` 改從 `profiles.py` 來 |
| `Hc/run_product.py` | `features.enabled(product)` 時建 `ProfileManager`，否則照舊建 `ProfileRuntime`；8081 的 `limit_concurrency` 改讀 `profile.mcp_listener_limit`（`ProfileRuntime` 是 64） |
| `Hc/profiles.py` | `PROFILE_ID`（`default` 或 24 位小寫 hex）的唯一來源（HM-05 審查「其他觀察」4）；模組說明改寫（已接線） |
| `tests/test_profile_routing.py`（新） | 路由矩陣：HM-01 契約案例在兩個帳號角色下各跑一次（31 種網址變形、兩個交叉案例、標頭／cookie／query 冒用、token 換掉）；零命中逐位元；撞號 503 與 60 秒 WARNING；索引壞、索引外改到重啟、預設 state 讀不到；額外帳號讀不到、目錄不見、目錄被換（S-08）；孤兒不路由；輪替只影響自己；每帳號政策；session 不跨帳號；cookie 不跨帳號；比對次數＝帳號數；6 帳號解析成本 |
| `tests/test_router_passthrough.py`（新） | 開關關：不掛分派器、不讀索引、不碰 FD、64／64；磁碟上有帳號資料也一樣。開關開：HM-01 黃金回歸、MCP 契約凍結、管理契約凍結全部照過；8081 外框＝64＋32×上限；FD 預算算法；FD 提高或降級 |
| `tests/test_profile_quotas.py`（新） | 三種過載情況對照 PaaS 表（准入滿、位元組額度滿、轉送名額逾時）；串流上限 429；拒絕小額度；預設帳號當攻擊方（C1-M5）；真 socket 的 S5、S6；每帳號 client；各種結束方式都歸還；WARNING 節流；開關關時的逐位元回應 |
| `tests/test_reply_mask_union.py`（新） | JSON 與 SSE 回覆遮掉所有帳號（含孤兒）的 token 與 child_token、不遮別帳號的後端密碼；別處輪替後立即遮；健康原因；`backend/test`；開關關時只遮本帳號 |
| `tests/multi_profile_runtime.py`（新，測試工具） | 開關開的正式 runtime（照 HM-01 `production_runtime` 的換法）、在磁碟上建額外帳號、每帳號一個子程式替身（依 port）、真 loopback 子程式 `RealChild` |
| `tests/test_profile_runtime.py` | HM-05 交代的：子程式 client 依帳號斷言（給 24 就是 24）；`make_apps` 與 `ProfileRuntime` 的新參數也是 keyword-only、不能經 `app_options` 給 |
| `tests/test_upgrade_zero_rewrite.py` | HM-07 交代的：`UNWIRED` 拿掉 `features`、`profiles`（HM-08 接線），留 `identity_fields`、`restore_detect`；說明跟著改 |
| `docs/multi-profile/contract.md` | HM-08 定案的暫定項目（第 2.2 節第 3、4 點、第 2.3 節、第 2.4 節、第 5 節 FD）與第 10 節一列（第 3.8 節） |
| `docs/provenance/runtime-patches.json` | 新增 `profile_router.py`；更新 `gateway.py`、`run_product.py`、`profile_runtime.py`、`profiles.py` 的摘要與說明 |
| 本筆記 | — |

沒改：`apps/n8n/run.py`（n8n 到 HM-25 才接線：開了 n8n 的開關，它也照單帳號跑）、`lifecycle.py`、`health.py`、`config.py`、`products.py`、
`redact.py`、`access.py`、`packaging/`、`apps/`、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、`docs/tool-surface.*`（沒動
`apps/runtime/*.py`、`apps/*/launch.py`，不用重產）、`decisions.md`（本片用到的決策都已定；DQ-21、DQ-25 由 HM-09 寫進去）、workflow。

## 3. 設計重點

### 3.1 分派器（計畫 §5.1；契約 §2.2、§2.3）

- **只看路徑與 `Authorization`**。密鑰路徑用 Starlette 自己的 `Route` 比對 `gateway.SECRET_ROUTE`（預設 app 也用這一份樣板），
  兩邊對「哪一段是 token」永遠一致；這條路徑上絕不讀 `Authorization`（I1 的交叉案例「密鑰路徑屬於 A＋`Authorization` 屬於 B」：A 服務）。
  `/mcp` 要剛好一個 `Authorization`、字面 `Bearer <token>`（同 `gateway.token_valid`）。其他情況（沒有候選）原封不動交預設 app。
  8081 永遠不讀 `X-MCP-Profile`、cookie、query（契約案例裡 `X-MCP-Profile` 的值換成第三個帳號的真 id 也一樣不理）。
- **比對**：sha256 一次，和預設帳號＋每個登錄的額外帳號的摘要比，全部比完；撤銷的沒有摘要（不比）。測試數 `compare_digest` 的呼叫次數＝持有 token 的帳號數。
- **快取**（`Credentials`）：每帳號存 state 檔的簽章（st_dev、st_ino、st_mtime_ns、st_size、st_nlink、st_mode；額外帳號再加
  st_ctime_ns）與 token 摘要，簽章變了才重讀。預設帳號不含 ctime：它的 store 每次讀都 fchmod（HM-01 凍結），ctime 一直變，含了就等於
  每個請求都重讀。額外帳號的讀取不 chmod（HM-07 審查 S-09），可以含 ctime。另外記住目前的 token 與 child_token，只給回覆遮罩用。
- **額外帳號目錄比對**（HM-07 審查 S-08）：登錄時記下目錄的 (st_dev, st_ino)，每次解析 lstat 比一次；不同（同名換成別的目錄）就不路由。
  同 uid 下不是安全邊界（DQ-37），只防誤改與誤拷。管理 API 與其他走路徑的地方（收據、owner-defaults、child_spec）交 HM-10。
- **結果**：剛好一個 → 該帳號的 `ProfileGate` → 該帳號的 app（它用自己的 store 再驗一次；快取舊了只會被拒，不會被別的帳號服務）。
  零個 → 預設 app（不佔准入、不讀 body；位元組同今天：測試逐一比對分派器與預設 app 的回應）。兩個以上 → 503，WARNING 每組 60 秒
  一行（成員 id 前 8 碼，`default` 就寫 default，不寫 token）。
- **不能信任時**（`ProfileManager.check()`）：啟動時 `profiles/` 列不出來、索引 corrupt、索引被外改（`recheck_index`，一旦 modified
  就維持到重啟）→ 每個 token 503；預設 state 讀不到 → 每個 token 503（撞號無法排除；預設 token 本來就是 503）。額外帳號讀不到只略過它
  （它的 token 變成未知 token，FM-05）。
- **`/health/ready`**：只代表預設帳號（DQ-19），照交預設 app；只有在「不能信任」時由分派器直接回 503 `{"ready":false}`（位元組同預設 app
  的 not ready），因為預設帳號那時也不服務。其他非 MCP 路徑照預設 app（404）。

### 3.2 每帳號名額（計畫 §5.2；契約 §5）

| 項目 | 預設帳號 | 額外帳號 | 在哪裡做 |
|---|---|---|---|
| 讀 body 前准入 | 64 | 32 | 分派器（`ProfileGate.active`） |
| 位元組額度 | 64 MiB | 64 MiB | 分派器（`ProfileGate.body_bytes`） |
| GET 串流上限 | 24 | 8 | 分派器（`ProfileGate.streams`） |
| 轉送名額／等候 | 32／1 秒 | 16／1 秒 | 帳號 app（`make_apps forward_slots`） |
| 子程式 httpx client | 40 | 24 | `ProfileRuntime(child_connections=…)` |
| 8081 外框 | 64＋32×產品上限（Odoo 224） | — | `run_product`（`ProfileManager.mcp_listener_limit`） |

- 數值全部讀 `profiles.DEFAULT_PROFILE_QUOTA`／`EXTRA_PROFILE_QUOTA`（HM-07 定的暫定值），`ProfileManager` 開啟時才讀（測試可縮小）。
- **位元組額度怎麼扣**（契約 §2.2 第 4 點的暫定，本片定案）：每個請求扣 max(宣告的 `Content-Length`（最多算到 `gateway.MAX_REQUEST`
  16 MiB）, 已讀的位元組)。准入時就先扣宣告的長度，所以宣告的長度放不下時讀之前就拒絕（不讓用戶端先傳一半才被切）；沒宣告的
  逐塊扣。從准入扣到帳號 app 送出回應標頭為止：那時 `serve()` 已經回傳，請求內容不在記憶體（JSON 回覆的 8 MiB 是 HM-30 的待送回覆額度）。
  宣告超過 16 MiB 的只扣 16 MiB，照舊由 app 回 413（n8n 回它的 JSON-RPC 錯誤），不改成忙碌回應。
- **讀途中超過**：那一塊不交給 app，改回「用戶端斷線」，app 照舊回 403，分派器把它換成 503＋`-32003`（`id: null`）；已讀的部分立刻還，
  子程式收不到任何東西（契約 §2.4 第 3 列定案）。
- 一個帳號的計數只在事件迴圈裡同步加減（檢查和加之間沒有 await），結束、例外、取消都在 `finally` 還。

### 3.3 過載回應與 PaaS 表（契約 §2.4；C3-MF-2）

| 情況 | PaaS（`docs/mcp-gateway-limits.md` @`69ac425`，到 `cf3d0d5` 沒變） | HA（本片） | 測試 |
|---|---|---|---|
| 准入滿，有 id、≤64 KiB | （PaaS 先讀 body 再排隊）200＋`-32003`＋Retry-After 5 | 同 PaaS | `test_admission_full_answers_as_the_paas_table` |
| 准入滿，通知／GET／DELETE | 503＋`-32003` id null＋Retry-After 5 | 同 PaaS | 同上 |
| 准入滿，有 id、>64 KiB | 200 | **503**（§8.8 #16：讀 body 前准入） | 同上 |
| 位元組額度：宣告長度放不下，有 id、≤64 KiB | —（PaaS 沒有位元組額度） | 200＋`-32003` | `test_the_byte_budget_answers_as_the_paas_table` |
| 位元組額度：讀途中超過 | — | 503＋`-32003` id null | 同上 |
| 轉送名額等候逾時，有 id | 200＋`-32003`＋Retry-After 5 | 同 PaaS（等 1 秒，PaaS 10 秒：§8.8 #15） | `test_a_busy_forwarding_slot_answers_as_the_paas_table` |
| 轉送名額等候逾時，沒 id（DELETE） | 503＋`-32003` id null | 同 PaaS | 同上 |
| GET 串流滿 | 429＋`-32003` id null＋Retry-After 30，不等 | 同 PaaS（24／8 條，PaaS 32） | `test_the_stream_cap_answers_429_at_once_and_posts_still_work` |

- 「解析得出 id」：`application/json`、strict JSON、單一物件、`jsonrpc` 是 `"2.0"`、`method` 是字串、`id` 是字串或整數（閘道 `authorize`
  收的請求）。batch 算沒有 id（HA 閘道從不回 batch；PaaS 會每個 id 回一則）。列在契約 §2.4。
- `-32003` 文字是固定的中英雙語（照 PaaS 寫法，子程序在 HA 叫「子程式」）：寫出是哪一種上限與「稍後再試」，不含 token、網址、帳號名稱。
  文字由 HM-14 定稿。
- **轉送名額逾時的形狀在本片先做**：計畫 §10.3 要求本片的測試對照「轉送名額逾時」；計畫 HM-14 與契約 §2.4 寫的是 HM-14。本片只在開通的
  產品、經 `make_apps slot_busy` 換回應形狀；排隊上限、通知保留名額、排隊中斷線、`-32004`／`-32005`、文字定稿仍是 HM-14（第 14.2 節）。
- 拒絕小額度全 add-on 共用：一個帳號大量被拒時，別的帳號「也被拒」的那些請求可能拿 503 而不是 200（只在兩個帳號同時過載時）；記憶體有界優先。

### 3.4 回覆遮罩聯集（計畫 §5.1 第 8 點；DQ-40 (a) ⑧；契約 §2.7）

- `make_apps(reply_secrets=…)` 給了時，`masks(state)`＝`redact.secret_values(state)` ∪ `reply_secrets()`（長度 ≥4，長的先換）。用在：轉送的
  JSON 回覆、SSE 事件、閘道自答的 tools/list、`backend/test`、`diagnostics`；被拒 tools/call 的健康原因另外再遮一次（健康監看只用本帳號秘密遮）。
- `ProfileManager.reply_secrets()`：每個登錄帳號目前的 token 與 child_token（先依簽章重讀；讀不到就用上次讀到的，寧可多遮）＋啟動時讀到的
  每個孤兒目錄的值（`held_tokens`：不拿鎖、不改任何東西、只讀 `state.json` 的兩個欄位）。
- 別帳號的後端密碼不在聯集裡（計畫 §5.1 第 8 點：人設的密碼可被寫進後端再讀回來猜；256 位元的 token 不行）。
- 開關關時 `reply_secrets` 不給，遮罩和今天逐位元相同（磁碟上的休眠帳號 token 也不遮：它沒被路由，HM-13b 開機時撤銷）。

### 3.5 `ProfileManager` 骨架與交給 HM-09 的介面（計畫 §12.2）

- 放在 `profile_runtime.py`（計畫 §12.2：HM-09 在這個檔加 `start_all`／`stop_all`；`profile_router.py` 的合併順序裡沒有 HM-09）。
  分派器在 `profile_router.py`，不 import `profile_runtime`（單向依賴）。
- 它像一個 `ProfileRuntime` 一樣給 `run_product` 用：`async with`、`admin_app`、`mcp_app`、`mcp_listener_limit`、`launch()`、`monitor()`。
- 開啟（`open()`）的順序：`SharedAdmin`（一份 `AdminAuthority`，用產品的 `verify_admin`）→ 預設帳號（用 run_product 開的 store）→
  分派器 → 讀索引 → 掃 `profiles/` → FD 預算 → 每個索引帳號（`existing_only` 開 store、建 runtime 與 gate；開不了的記一行 WARNING、不服務）
  → 孤兒（只讀 token 給遮罩，記一行 WARNING）→ 一致性報告（共用 token 或 child_token 的帳號記一行 WARNING）。
- **HM-09 要接的地方**（也寫在 `ProfileManager` 的 docstring）：
  - `start_all()`：取代 run_product 現在呼叫的 `launch()`（只起預設帳號）。逐一 `entry.runtime.launch()`；`entry.disabled`（`disabled_reasons`：
    `profile_limit`、`memory_capacity`、`port_conflict`）有值的不起；錯開啟動（同時最多 2 個、前一個健康檢查通過或 30 秒）。
  - `stop_all()`：所有 `entry.runtime.aclose()`（client 再 Supervisor）並行、30 秒內收完；目前 `aclose()` 依序關（額外帳號先、預設帳號最後）。
  - 監看：`monitor()` 目前只回預設帳號的；HM-09 讓每個帳號都有監看，額外帳號的監看停止只標記該帳號（DQ-21），起點錯開（DQ-25）。
  - 看門狗參數：`ProfileRuntime(lifecycle=…)` 已經可以傳 Supervisor 的參數（HM-05）；`ProfileManager.add()` 目前不傳，HM-09 加。
  - `entry.port` 是索引 port；spawn 前檢查（8081／8099、被佔）在 HM-09。
- **HM-10 要接的地方**：`add(profile_id, store, port=…, label=…, disabled=…)` 與 `remove(profile_id)` 在執行中登錄或移除帳號（移除前先撤銷、
  提交索引）；寫索引後用 `adopt_index(view)` 換比對基準（不能重新 `read_index`，HM-07 第 12 節第 9 點）；`shared.pipeline` 放共用管線；
  每帳號的管理 app 是 `get(id).runtime.admin_app`。

### 3.6 開關與 `run_product`

- `features.enabled(product)` 每次啟動時讀（不在 import 時綁）。沒開通時 `run()` 的路徑：同一個 `ProfileRuntime`、同樣的 `make_apps` 參數
  （HM-05 的測試 `test_run_product_serves_the_default_profiles_runtime` 照過，`make_apps` 沒有收到新參數）、`limit_concurrency` 兩個都是 64。
- import 的變化：`run_product` 多 import `features`，`gateway` 多 import `profiles`（`PROFILE_ID` 的來源），`profile_runtime` 多 import
  `profile_router`、`products`、`resource`。這些模組 import 時沒有副作用；`tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED` 照 HM-07 的交代改成只剩
  `identity_fields`、`restore_detect`。沒開通時不讀索引、不掃目錄，由 `test_switched_off_run_product_serves_the_default_profile_alone` 用替身鎖住。
- n8n（`apps/n8n/run.py`）沒改，到 HM-25；OpenDesign、Odoo Manage 不能開通（DQ-28；就算開了，`supports_profiles` 是 False，也不開任何額外帳號）。

### 3.7 FD 上限（計畫 §5.2；C2-SF-5）

- 需要量（`open_file_budget(product)`，照產品上限算，因為 HM-10 之後執行中會加帳號）＝8081 外框＋8099 的 64＋預設 40＋額外 24×上限＋角色查詢 8
  ＋每個子程式 4＋基本 64；目標＝需要量×1.25。Odoo：544、680；其他產品 400、500。
- `raise_open_file_limit`：執行時讀 `RLIMIT_NOFILE`；soft ≥ 目標就不動；否則在 hard 允許下設成 min(目標, hard)（不需權限）。讀不到、hard 比需要量小、
  設不上：**不假設夠**，記一行 WARNING（只有數字），不開額外帳號、8081 外框維持 64、只服務預設帳號（分派器照掛）。
- 本機常見的 soft 1024 已經大於 680，所以一般情況什麼都不改。HAOS 上 add-on 容器的實際值待 HM-03a（第 11 節）。

### 3.8 計畫沒寫死、本片定的做法（契約已同步）

1. 位元組額度的扣法（第 3.2 節）：契約 §2.2 第 4 點。
2. 讀途中超過的回應與做法（第 3.2 節）：契約 §2.4。
3. 「解析得出 id」的定義、batch 算沒有 id（第 3.3 節）：契約 §2.4。
4. 索引不能用時 `/health/ready` 回 not ready（第 3.1 節）：契約 §2.3。
5. FD 需要量的算法與降級的樣子（第 3.7 節）：契約 §5。
6. `profiles/` 列不出來時每個 token 503（fail closed；計畫只寫了索引壞的情況）。
7. 檢查順序：GET 先比串流上限、再比准入；其他請求先比准入、再比位元組額度。
8. 轉送名額逾時的 `-32003` 在本片先做（第 3.3 節）。

這些都不是使用者要定的題目（DQ），是契約自己寫明「由 HM-08 定案」或計畫範圍內的實作細節；審查若認為某一項要問使用者，再回報。

## 4. 守門有效的證據

### 4.1 先紅後綠

測試先寫（測試裡要用的新模組在測試執行時才 import，所以每案各自失敗，不是整個檔收集失敗）。

| 輪 | 範圍 | 結果 |
|---|---|---|
| 實作前（`76c1d78` 的程式＋新測試） | 4 個新檔＋改過的 2 個既有檔，191 案 | 71 失敗、120 通過。失敗：`test_profile_routing.py` 22／22、`test_router_passthrough.py` 28／49、`test_profile_quotas.py` 12／12、`test_reply_mask_union.py` 6／6、`test_profile_runtime.py` 3（新參數）。通過：`test_router_passthrough.py` 21（「開關開時黃金回歸與契約凍結照過」的鎖：實作前開關不做事，所以照過；實作後必須照過）、既有測試 99 |
| 實作後 | 同上，加 HM-01 的 3 個守門檔 | 236 案全過、0 skip |

實作後第一次跑時找到、改掉的測試本身的錯（不是程式的錯）：

- `test_router_passthrough.py` 3 個測試沒有放預設帳號的子程式替身，`settle()` 等不到健康檢查 → 測試工具在沒給替身時自動放 golden 的 `MockChild`。
- `test_profile_quotas.py` 的 `HoldingChild.opened` 和 `ProfileChild.opened`（session 計數）撞名 → 改名 `free`。
- `RealChild` 的 ASGI app 是綁定方法，uvicorn 自動判斷成 ASGI2 → 明寫 `interface='asgi3'`。
- 開關開時重跑的管理契約凍結裡，owner-defaults 還原那一案直接呼叫 `make_apps`、不經過 `run_product`，開關影響不到它 → 拿掉（原檔照跑）。
- FD 預算的介面在實作時從 (產品, 帳號數) 改成 (產品)（照產品上限算）→ 測試跟著改；啟動時的 WARNING 由 `profile_runtime` 的 logger 寫 → 測試改看那個 logger。

全套 pytest 跑完後只再改了 `test_profile_quotas.py` 兩處，都是加強測試：(1) 多驗「回應一開始就還位元組、請求結束才還准入」
（PaaS `test_already_read_response_returns_its_slot_at_once`；突變 M11 就是它擋下的）；(2) 真 socket 的測試在離開 runtime 前先關掉
32 條慢連線，runtime 不必等滿 5 秒才結束。之後的目標測試、瀏覽器重跑與突變都用改後的版本（第 5 節）。

### 4.2 臨時突變

每個突變只改正式程式的一處，跑 HM-08 的 6 個測試檔（`-x`），跑完逐位元還原（SHA-256 比對）。腳本：
`SP:hm08/bin/mutate.py`（repo 外）。32 個全部被擋下；表上是第一個失敗的測試（`-x` 停在那裡，之後的測試沒跑）。

| # | 突變（檔） | 擋下的第一個測試 |
|---|---|---|
| M01 | 比到第一個就停（不全部比完）（`profile_router.py`） | `test_profile_routing.py::test_a_token_two_profiles_hold_is_refused_and_logged_once_a_minute[directory]` |
| M02 | 8081 讀 `X-MCP-Profile` 選帳號（`profile_router.py`） | `test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]` |
| M03 | 密鑰路徑上改看 `Authorization`（`profile_router.py`） | `test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]` |
| M04 | 零命中由分派器自己回 404（不交預設 app）（`profile_router.py`） | `test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]` |
| M05 | 撞號交給第一個帳號（`profile_router.py`） | `test_profile_routing.py::test_a_token_two_profiles_hold_is_refused_and_logged_once_a_minute[directory]` |
| M06 | 索引壞或被外改仍照常服務（`profile_runtime.py`） | `test_profile_routing.py::test_a_corrupt_index_refuses_every_token_and_the_panel_still_opens` |
| M07 | 預設 state 讀不到時略過它（`profile_router.py`） | `test_profile_routing.py::test_an_unreadable_default_state_refuses_every_token` |
| M08 | 不比對額外帳號目錄（S-08）（`profile_router.py`） | `test_profile_routing.py::test_a_profile_that_cannot_be_read_is_not_routed_and_the_others_are[replaced directory]` |
| M09 | 拿掉准入（`profile_router.py`） | `test_profile_quotas.py::test_admission_full_answers_as_the_paas_table` |
| M10 | 讀到的位元組不扣額度（`profile_router.py`） | `test_profile_quotas.py::test_the_byte_budget_answers_as_the_paas_table` |
| M11 | 位元組到請求結束才還（不是回應開始時）（`profile_router.py`） | `test_profile_quotas.py::test_admission_bytes_and_streams_are_given_back_however_a_request_ends` |
| M12 | 串流數不歸還（`profile_router.py`） | `test_profile_quotas.py::test_the_stream_cap_answers_429_at_once_and_posts_still_work[default]` |
| M13 | 拒絕小額度不限 64 KiB（`profile_router.py`） | `test_profile_quotas.py::test_the_refusal_allowance_reads_little_and_few` |
| M14 | 拒絕小額度不限同時數與總量（`profile_router.py`） | `test_profile_quotas.py::test_the_refusal_allowance_reads_little_and_few` |
| M15 | 帶 id 的忙碌回應也回 503（`gateway.py`） | `test_profile_quotas.py::test_admission_full_answers_as_the_paas_table` |
| M16 | 拿掉串流上限（`profile_router.py`） | `test_profile_quotas.py::test_the_stream_cap_answers_429_at_once_and_posts_still_work[default]` |
| M17 | 轉送名額一律 32（不分帳號）（`gateway.py`） | `test_profile_quotas.py::test_a_busy_forwarding_slot_answers_as_the_paas_table` |
| M18 | 轉送名額逾時照舊 503 request denied（`gateway.py`） | `test_profile_quotas.py::test_a_busy_forwarding_slot_answers_as_the_paas_table` |
| M19 | 遮罩不含聯集（`gateway.py`） | `test_reply_mask_union.py::test_a_reply_never_carries_any_token_the_add_on_holds[json]` |
| M20 | 被拒 tools/call 的健康原因不遮聯集（`gateway.py`） | `test_reply_mask_union.py::test_a_health_reason_with_another_profiles_token_is_masked_in_the_refusal` |
| M21 | 開關判斷反過來（`run_product.py`） | `test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]` |
| M22 | 開通後 8081 外框仍是 64（`run_product.py`） | `test_router_passthrough.py::test_switched_on_the_mcp_listener_bound_follows_the_product_limit[odoo]` |
| M23 | FD 不夠也照開額外帳號（`profile_runtime.py`） | `test_router_passthrough.py::test_the_file_limit_is_raised_or_the_add_on_serves_the_default_profile_only[hard too low]` |
| M24 | 額外帳號用預設帳號的名額（40、32、64）（`profile_runtime.py`） | `test_profile_quotas.py::test_admission_full_answers_as_the_paas_table` |
| M25 | WARNING 不節流（`profile_router.py`） | `test_profile_routing.py::test_a_token_two_profiles_hold_is_refused_and_logged_once_a_minute[directory]` |
| M26 | 索引壞時 `/health/ready` 照交預設 app（`profile_router.py`） | `test_profile_routing.py::test_a_corrupt_index_refuses_every_token_and_the_panel_still_opens` |
| M27 | 摘要快取永不失效（`profile_router.py`） | `test_profile_routing.py::test_the_contract_cases_route_by_token_alone[odoo]` |
| M28 | 孤兒的 token 不進遮罩（`profile_runtime.py`） | `test_reply_mask_union.py::test_a_reply_never_carries_any_token_the_add_on_holds[json]` |
| M29 | 孤兒也當帳號路由（`profile_runtime.py`） | `test_profile_routing.py::test_a_corrupt_index_refuses_every_token_and_the_panel_still_opens` |
| M30 | 宣告的長度不先扣（`profile_router.py`） | `test_profile_quotas.py::test_the_byte_budget_answers_as_the_paas_table` |
| M31 | 讀途中超過時 app 的 403 不換成 503（`profile_router.py`） | `test_profile_quotas.py::test_the_byte_budget_answers_as_the_paas_table` |
| M32 | `backend/test` 只用本帳號秘密遮（`gateway.py`） | `test_reply_mask_union.py::test_the_management_answers_carry_no_token_either` |

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

| 檢查 | 結果 |
|---|---|
| 全套 pytest（實作完成、帳本更新前；正式 conftest，排隊在共用鎖；`SP:hm08/bin/full_suite.sh`） | 5270 案、0 skip、30 分 30 秒：5239 通過；31 失敗＝`test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources` 與 `test_ledger_precheck.py::test_this_checkout_has_no_ledger_drift`（帳本還沒更新）＋22 個瀏覽器測試（`test_owned_browser_ipc.py` 5、`test_owned_browser_redirect.py` 16、`test_owned_ui.py::test_standalone_ownership_boundaries[browser]`；找不到 Chromium）＋7 個要 root 的既有案例（第 6 節） |
| 帳本更新後：HM-08 的 4 個新檔、改過的 2 個既有檔、HM-01 守門 3 檔、`test_tool_inventory.py`、`test_ledger_precheck.py`、HM-07 的 3 檔、`test_restore_detection.py` | 597 案：591 通過、6 失敗（要 root：HM-07 1、HM-13a 5） |
| 照 CI 裝 Chromium（`npm run browser:install --prefix packages/mcp-admin-ui`，裝在不進 git 的 `node_modules`）後重跑那 22 個瀏覽器測試與 `test_profile_quotas.py` | 49 案全過 |
| 新測試 4 檔單獨跑 | 89 案、19 秒 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準）。註：TMPDIR 沒設成短的 `/tmp/ha-mp-*` 時（工具預設的 `/data/pi-agent/tmp` 有 setgid 位元），`test_entrypoint.py` 有 2 案因為新目錄繼承 setgid、mode 不是 0700 而失敗；是本機環境，和本片無關（本片沒動 `packaging/`） |
| `scripts/tool_inventory.py`（漂移檢查，同 unit.sh） | 通過 |
| 6 帳號解析成本 | 第 12 節 |
| `git status` | 乾淨 |

## 6. 只在 CI 跑的測試

本片新增的 89 案都在本機跑過、全部通過，沒有只在 CI 跑的新測試。CI（root、0 skip）才是準：

- 已知要 root、本機一定失敗的既有案例（不是本片造成，本片也沒動它們測的程式）：
  `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（基準）、
  `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（HM-07）、`tests/test_restore_detection.py` 的 5 個 `test_root_*`（HM-13a）。
- 本片的測試在 root 下：擁有者檢查（`read_index`、`Store(existing_only)`、`held_tokens`）都比對 `os.geteuid()`，root 建的檔就是 root
  擁有，照樣成立；FD 測試用 `resource` 的替身；開關開時重跑的黃金回歸用真的 `RLIMIT_NOFILE`（soft ≥ 目標就不呼叫 `setrlimit`；就算
  呼叫，也只提高測試程序自己的 soft，在 hard 之內）；真 socket 的測試只綁 127.0.0.1 的隨機 port（`tests/owned_network.py` 擋 3000 與
  18000～18099）。
- Python：CI 3.13.16、本機 3.13.15。

## 7. `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本片新測試 4 檔在本機約 19 秒（計畫 §10.1：每片增量 ≤1.5 分鐘）。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；本片 5 個 commit（`76c1d78..HEAD`）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 172 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的 5 個列管檔都有帳本更新；沒有沒列管的新執行檔：**OK** |

測試資料：沒有 commit 任何隨機 token；固定的 token 形字串只有 `U`×21＋`n`×22（低熵、沒人持有）。

## 9. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`，本機唯讀 PaaS repo，origin/main `cf3d0d5`）

| commit | 內容 | 對本片 |
|---|---|---|
| `19f36e2` | #148 合併後的文件更正：`docs/mcp-gateway-limits.md`、`CLAUDE.md`、`gateway_pool.py` 與 `proxy.py` 的 docstring 和註解（commit 訊息：可執行碼去掉 docstring 後 `ast.dump` 與 main 逐一相同） | 沒影響：忙碌回應的形狀、Retry-After、WARNING 節流都沒變；「排隊上限算個數不算位元組」正是本片位元組額度的理由 |
| `82c6929` | 只改 `tests/test_gateway_queue.py`（名額還過頭、保留名額逾時 WARNING 全文、舊測試的時間餘裕） | 沒影響（排隊與保留名額是 HM-14） |
| `091dfbc` | 只改 `docs/mcp-gateway-limits.md` 惡意 Location 那一段 | 沒影響 |

查的檔：`proxy.py`、`gateway_pool.py`、`profiles.py`、`request_body.py`、`mcp_access.py`、`app.py`、`docs/mcp-gateway-limits.md`、
`docs/shared-token-lifecycle.md` 與 `test_gateway_pool.py`、`test_gateway_queue.py`、`test_profiles.py`、`test_profile_robustness.py`、
`test_profile_isolation.py`。`69ac425` 之後核心模組只動 `log_redaction.py`（HM-02 已收）、`gateway_pool.py`／`proxy.py` 的註解、`setup_status.py`
的說明文字（`git diff --stat 69ac425 origin/main -- packages/mcp-admin-core/mcp_admin_core/`）。沒有 fetch、沒有 checkout。

## 10. 本片用到的決策（都已定；`decisions.md` 不用改）

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-01 (a) | Bearer `/mcp` 也依 token 選帳號，和密鑰網址同一個解析器 | 第 3.1 節 |
| DQ-07 (a)＋DQ-29 | 名額與記憶體規則：預設帳號也有位元組額度；數值照契約 §5（暫定，HM-19c 量測後定案） | 第 3.2 節 |
| DQ-09 | 撞號 503 `{"error":"state unavailable"}`、不轉任何帳號 | 第 3.1 節 |
| DQ-12 | 索引壞與被外改：8081 全部 503（含預設帳號），外改到重啟為止；面板照開 | 第 3.1 節（隔離動作是 HM-10） |
| DQ-19 | `/health/ready` 只代表預設帳號 | 第 3.1 節 |
| DQ-28 | OpenDesign、Odoo Manage 不開放 | 第 3.6 節 |
| DQ-37 (a) | 同 uid 是同一個信任邊界 | 簽章與目錄比對只防誤改（第 3.1 節） |
| DQ-40 (a) ⑧ | 回覆遮罩含所有帳號 token | 第 3.4 節 |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 5 節；commit |

沒用到：DQ-21、DQ-25（2026-11-15 11:2x 使用者照建議定了；監看是 HM-09，由 HM-09 寫進 `decisions.md`）。沒有碰到待定題。

## 11. 待 HM-03a 確認

| 項目 | 本片怎麼處理 | 要 HM-03a 量什麼 |
|---|---|---|
| HAOS add-on 容器裡 uid 10001 的 `RLIMIT_NOFILE` soft／hard | 執行時讀；soft 不夠就在 hard 內提高；讀不到、hard 不夠、設不上就降級（不開額外帳號、8081 維持 64）並記一行 WARNING | 實際的 soft／hard（Supervisor／Docker 有沒有設 `ulimits`）；`setrlimit` 提高 soft 在容器內能不能成功 |
| FD 需要量的估計（每個子程式 4、基本 64） | 估計值寫在 `profile_runtime.py` 常數 | HM-19c 在 J6412（可以的話 J1900）量開通後實際用到的 FD |
| `oom_score_adj`、`setpriority`、`/proc` 可讀性 | 本片沒用到（HM-09、HM-15） | 照計畫 HM-03a 表 |

## 12. 6 帳號解析成本（驗收項目；FM-14、UC-02）

- 情境：預設帳號＋5 個額外帳號（Odoo），分派器的 `resolve()`（每個請求做的全部：索引 lstat 一次、5 個額外帳號目錄各 lstat 一次、6 份 state
  各 lstat 一次、sha256 一次、6 次 `compare_digest`；簽章沒變就 0 次讀檔）。
- 機器：本機開發機 AMD EPYC 7713（`/tmp` 底下的暫存目錄），Python 3.13.15。不是目標硬體：HM-19c 在 J6412（可以的話 J1900）重量。

| 量法 | 情況 | 平均 | p95 | 讀檔次數 |
|---|---|---|---|---|
| 測試 `test_resolving_a_token_among_six_profiles_is_cheap`（2000 次） | 簽章不變，命中最後一個額外帳號 | 97.8 µs | 105.4 µs | 0 |
| 同上 | 簽章不變，未知 token | 97.9 µs | 106.2 µs | 0 |
| 同上（300 次） | 每次 6 份 state 都換過（mtime 變） | 779.8 µs | 939.1 µs | 每次 6 |
| 獨立腳本（5000 次；`SP:hm08/bin/resolve_cost.py`） | 簽章不變（最後一個／預設／未知） | 71.4／71.7／70.2 µs | 78.9／79.1／78.4 µs | 0 |
| 同上（1000 次） | 每次 6 份都換過 | 734.1 µs | 893.9 µs | 6000 |
| 同上（1000 次） | 每次只有預設帳號換過 | 179.7 µs | 213.3 µs | 1000 |

- 成本幾乎都在 `lstat`（cProfile：每次解析 12 次 `lstat` 約 80% 的時間）；HM-07 的研究值是「每檔 70～203 µs、六檔約 473 µs」（每次都讀），
  快取後少了一個數量級。測試的上限放寬（平均 <2 ms、全部重讀 <20 ms）避免 CI 偶發失敗。

## 13. 驗收條件（計畫 §12.3 HM-08）

| 條件 | 結果 |
|---|---|
| 開關關時 HM-01 逐位元 | 通過：HM-01 黃金回歸、MCP 契約凍結、管理契約凍結照過，斷言一個字都沒改；開關關時不掛分派器、不讀索引、不碰 FD 上限（`test_router_passthrough.py`）；全套 pytest 除了已知的環境與 root 案例都過（第 5 節） |
| 開關開時全過 | 本機通過：開關開時 HM-01 黃金回歸（6 產品×2 狀態）、MCP 契約凍結（6）、管理契約凍結（6）照過；HM-08 的 89 案全過。CI 待 PR |
| 6 帳號解析成本記在筆記 | 通過：第 12 節 |
| 獨立安全審查 | **還沒做**：合併前由主對話安排（計畫 §12.0 第 9 點），報告放 `artifacts/`、PR 附連結 |
| 測試照 §10.3（兩個交叉案例、三種過載情況對照 PaaS 表、預設帳號當攻擊方） | 通過：交叉案例在 `test_the_contract_cases_route_by_token_alone`（`cross-bearer-b`、`switch-authorization`，兩個角色）；PaaS 表在第 3.3 節；預設帳號當攻擊方在 `test_the_default_profiles_token_holder_cannot_exhaust_memory` |
| 同 PR 更新帳本（新模組照 `ledger-tracking.md` 列管） | 通過：第 8 節 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 都在執行時產生（或沿用 HM-01、HM-05 的工具）；不出現在任何 commit 的固定 token 只有 `U`×21＋`n`×22（低熵、沒人持有）；憑證 `DUMMY-…`、網址 `.invalid` |

## 14. 還沒解決、交給後面的片

### 14.1 前面的片交給 HM-08 的事項

| 來源 | 事項 | 處理 |
|---|---|---|
| HM-05 第 11 節 | 用 `ProfileRuntime` 建額外帳號（store 用「只開既有」）、一份 `SharedAdmin` | 做了（`ProfileManager.add`） |
| HM-05 第 11 節 | 額外帳號 client 上限 24；`test_each_runtime_makes_its_child_client_as_run_product_did` 依帳號斷言 | 做了 |
| HM-05 第 11 節 | `PROFILE_ID` 統一一個來源 | 做了（`profiles.PROFILE_ID`） |
| HM-05 審查 S-2(b)、突變 ME6 | 轉送名額每帳號一份的跨帳號案例 | 做了（`test_a_busy_forwarding_slot_answers_as_the_paas_table`：B 的 16 個滿了，預設帳號 20 個照常） |
| HM-01 第 11 節 | 每帳號的子程式 client（cookie 不跨帳號）與測試 | 做了（`test_a_childs_cookie_never_reaches_another_profiles_child`） |
| HM-01 第 11 節 | 契約檔加額外帳號欄：B 路徑、`cross-bearer-b`、`switch-x-mcp-profile-default-on-b-url` 改成 B 的期望值；`order-*`、token_change 每個帳號 app 都照過 | 做了，但沒有改 `tests/contract/profiles_v1_cases.json`（HM-01 的守門檔）：期望值的換法寫在 `test_the_contract_cases_route_by_token_alone`（`B_SERVED`），兩個角色都跑 |
| HM-01 第 4.2 節 | 讀 body 時斷線的 403：開關關時的逐位元案例 | 做了（`test_switched_off_a_busy_slot_and_a_client_leaving_answer_as_before`；順便補了轉送名額逾時 503 的逐位元案例，原本交 HM-14） |
| HM-07 第 12 節第 3 點 | `UNWIRED` 改掉 `features`、`profiles` | 做了 |
| HM-07 第 12 節第 6 點（S-08） | 已開的額外帳號 store 沒有釘住目錄 | MCP 路由這一側做了（目錄比對，不同就不路由）；管理 API、收據、owner-defaults、`child_spec` 仍走路徑：交 HM-10 |

### 14.2 交給後面的片

- **HM-09**：第 3.5 節的介面（`start_all`、`stop_all`、每帳號監看、看門狗參數、spawn 前檢查）；DQ-21、DQ-25 寫進 `decisions.md`；log 事件可沿用
  `profile_router.Reports`（每帳號每情況 60 秒一行）。HM-09 改 `profile_runtime.py`、`run_product.py`，照 §12.2 在 HM-08 之後合併、rebase 後重產帳本。
- **HM-10**：8099 分派器與共用管線、帳號增刪（`ProfileManager.add`／`remove`／`adopt_index`）、索引隔離動作；S-08 的管理面；契約 §3。
- **HM-14**：排隊上限、通知保留名額、排隊中斷線、`-32004`／`-32005`、initialize 世代、`-32003` 文字定稿；本片已做的轉送名額逾時形狀照 #148 再對一次。
- **HM-30**：待送回覆位元組額度（C1-M5 測試的「加上大回覆」那一半）、回覆工作執行緒、健康檢查連兩次失敗。
- **HM-25**：`apps/n8n/run.py` 改用 `ProfileManager`。
- **HM-18**：契約定稿時，把本片在契約 §2.2～§2.4、§5 定案的文字收進最終版。
- **合併前**：獨立安全審查；開 PR 後補 `checks` 秒數。
- 交互：HM-09 與本片同時開發，`profile_runtime.py`、`run_product.py`、帳本會衝突；照計畫 §12.2 本片先合、HM-09 rebase 後重產帳本。
  本片也改了 `docs/multi-profile/contract.md`（不在計畫衝突表的 HM-08 列），HM-09 若也改契約要注意第 2、5 節。
