# 多帳號中立契約（v1，HM-00 起草）

- 狀態：HM-00 起草（2026-11-14）。HM-10 依實作補了第 3、4.1 節的細節（2026-11-15，見第 10 節），HM-18 定稿；合併順序 HM-00 → HM-10 → HM-18。
- 「中立」：PaaS `WOOWTECH/woow-mcp-server` 的行為（pin `69ac425`）是期望值；HA 和它不同的地方，每一條都列在第 9 節的刻意差異表
  （計畫 §8.8，下稱「§8.8 #n」），沒列的就要相同。FEATURE-MATRIX 每一列（含「HA 平台差異」欄是「—」的列）對到哪一列、
  或為什麼相同，見 `deviation-trace.md`。
- 來源：計畫 `PLAN-zh-TW.md` §2～§8（repo 外，`artifacts/ha-multiprofile-parity-20261114/`）。決策見 `decisions.md`；
  驗收見 `acceptance-matrix.md`；威脅模型見 `threat-model.md`。
- 標「暫定」的細節：計畫沒寫死、本檔先定一個做法，由括號裡的切片實作時定案；改了要同時改本檔。
- 路徑縮寫：`Hc/`＝HA `packages/mcp-admin-core/mcp_admin_core/`（bb48449）；`Hui/`＝HA `packages/mcp-admin-ui/src/`；
  `Pc/`＝PaaS `packages/mcp-admin-core/mcp_admin_core/`（@69ac425）；其他 PaaS 路徑相對 PaaS repo 根目錄。

## 0. 先講結論

1. 產品沒開通（不在 `MULTI_PROFILE_PRODUCTS`）而且磁碟上沒有帳號資料時，**8081 與 8099 的回應和今天逐位元相同**，本檔的新行為都不生效；例外只有第 1.2 節「不受開關管」的變更（例如直連子程式要帶 bearer、log 遮得更多、還原時多一個標記檔；HM-31 起，超過請求內容位元組預算、讀取閒置或 JSON 結構上限的請求被拒）。
2. MCP 請求屬於哪個帳號**只看 token**；8081 永遠不讀 `X-MCP-Profile`、cookie、query。
3. 管理 API 開通後，帳號範圍路徑**一定要剛好一個** `X-MCP-Profile`；缺了 400、格式錯 400、不存在 404，絕不退回預設帳號。
4. 管理 API 全部走一條共用管線：先驗 HA 管理員，才看任何帳號狀態；非管理員在任何帳號狀態下拿到逐位元相同的 403。
5. 每個帳號（含預設帳號）讀 body 前有准入；一個帳號用不到別的帳號的名額（隔離在請求層，第 2.4、5 節）。請求內容位元組預算（HM-31，不受開關管）是全 add-on 一份、每帳號一個份額：一個帳號用滿自己的份額，別的帳號照常；全 add-on 的預算是帳號之間唯一共用的位元組（同 PaaS #155）。
6. 新增的錯誤代碼放在 `detail.code`，不帶伺服器文字；既有回應的本體形狀照今天（第 4.1 節開頭列了五種）。
   每個代碼的狀態碼、時機、欄位與 PaaS 對應見第 4 節。

## 1. 範圍、名詞與開關

### 1.1 名詞

| 名詞 | 意思 |
|---|---|
| 帳號（profile） | 一組後端連線與憑證、一把 MCP token、一份工具政策、一個子程式；帳號之間隔離 |
| 預設帳號 | id `default`，就是今天的 `/data/mcp/state.json`；升級後 token、網址、設定都不變 |
| 額外帳號 | id 是 24 位小寫 hex，目錄 `/data/mcp/profiles/<id>/`；最多 min(5、產品上限、記憶體條件) 個（各產品見第 5 節） |
| 帳號範圍路徑 | `{base}/api/*` 裡第 3.1 節全域路徑以外的路徑 |
| 開通 | 產品在 `features.MULTI_PROFILE_PRODUCTS` 裡；判斷一律呼叫 `features.enabled(product)`，呼叫時才讀 |
| 休眠帳號 | 產品沒開通、磁碟上卻有帳號資料時的額外帳號；開機在任何 listener 前撤銷 token |
| 孤兒 | `profiles/` 底下有、索引沒有的 24 hex 目錄；不開、不路由、只能刪 |
| 隔離目錄 | `profiles/.quarantine-<id>-<UTC>/`；還原守門讀不到的帳號改名放這裡；不路由、只能刪（刪除路由暫定，HM-13c 定案；第 3.1 節） |

### 1.2 開關與「不受開關管」

| 狀態 | 8081 | 8099 管理 API | 開機 |
|---|---|---|---|
| 沒開通、沒有帳號資料（＝今天） | 不掛分派器，回應逐位元同今天 | `/api/profiles*` 404；不要求 `X-MCP-Profile`；管線順序同今天 | 還原標記只記一行 WARNING 後刪除 |
| 沒開通、有帳號資料（休眠） | 只服務預設帳號 | 同上；bootstrap 只多 `dormant_profiles`（數字） | 撤銷每個額外帳號與孤兒的 token、重產 child_token（I13） |
| 開通 | 分派器依 token 選帳號 | 第 3 節全部規則 | 還原偵測、守門、預設帳號、錯開起額外帳號 |

不受開關管（任何產品下一次發版都會帶出去；保證方式見計畫 §3.3）：紀錄遮罩（HM-02）、port 參數化（HM-04）、
執行套件抽出（HM-05）、子程式 bearer（HM-06）、資料層函式庫（HM-07）、收據格式（HM-11）、entrypoint 還原標記（HM-13a）、
開機守門的存在檢查與休眠處理（HM-13b）、子程式 initialize 錯誤的遮罩（HM-14，見下）、請求內容位元組預算與 JSON 結構守門（HM-31，見下）、
驗收與發版工具（HM-16、HM-17）。

**HM-14 的不受開關管變更：子程式 initialize 錯誤遮本帳號憑證**（2026-11-15；HM-08 審查 S-4 (a) 交給 HM-14）

- 缺口：子程式對 initialize 回 JSON-RPC 錯誤時，錯誤的 `message` 與 `data` 是子程式自己的文字。其他每一條轉回子程式或後端文字的路徑
  （JSON 回覆、SSE 事件、閘道自答的 tools/list、被拒 tools/call 的健康原因、`backend/test`、`diagnostics`）今天都用本帳號的憑證遮
  （`redact.secret_values`）；只有這一條原樣轉回，連本帳號的 token、child token、後端密碼都沒遮。子程式把收到的設定原樣寫進錯誤
  （例如「用這組密碼登入失敗」）時，持有這把 token 的 MCP 用戶端就看得到 child token 與後端密碼（用戶端本來不該知道這兩樣）。
- 為什麼開關關時也改：這是今天就有、和多帳號無關的缺口。放在開關後面，每個產品在開通之前的每一版都會繼續帶著它；改了只會把憑證換成
  `[REDACTED]`，不會讓任何請求變得可行或不可行，也不改任何狀態碼或標頭。
- 改了什麼回應：只有「子程式回的 initialize 錯誤」這一種回應，而且只有錯誤文字裡出現本帳號的憑證（`redact.secret_values`：token、
  child token、後端秘密欄位與它們的 Basic 形式）時，那幾段換成 `[REDACTED]`（`Content-Length` 跟著變）；狀態碼、其他標頭、其他文字
  逐位元不變。錯誤裡沒有憑證時，和今天逐位元相同。開通的產品照 HM-08 另外遮全 add-on 每個帳號的 token（第 2.7 節）。
- HM-01 的契約凍結不用改：凍結的案例沒有 initialize 錯誤（`tests/contract/profiles_v1_cases.json`、黃金回歸都照過）。
- 測試：`tests/test_initialize_generation.py`（開關關：本帳號三種憑證都遮、沒有憑證時逐位元相同；開關開：照 HM-08 的聯集）。

**HM-31 的不受開關管變更：請求內容位元組預算、大請求讀取閒置逾時、JSON 結構守門**（2026-11-16；對齊 PaaS #155，woow-mcp-server
`d7f5849`）

- 決定：2026-11-16 07:1x 使用者決定對齊 PaaS #155，**所有產品都生效**（不受開關管）；計畫 §12.3 HM-31。
- 缺口：沒開通的產品今天沒有任何位元組上限：8081 外框 64 條連線，每條最多讀 16 MiB 進記憶體（最壞 1 GiB），解析成本另外再乘數倍到
  24 倍（大量小物件；HM-08 量測）；UTF-16／32 的 body 也照樣解析。PaaS 沙盒實測 1 GiB 的 pod 被 32 個 4 MiB 的請求打到 OOM。
- 為什麼開關關時也改：這是今天就有、和多帳號無關的缺口；放在開關後面，每個產品在開通之前的每一版都帶著它。只有超過上限的請求會被拒，
  上限內的請求逐位元照舊。
- 改了什麼回應（單帳號，逐項；各產品下一版 CHANGELOG 照 HM-31 的 provenance 筆記第 8 節）：
  1. 宣告的 `Content-Length` 超過 64 KiB、放不進預算的請求：讀完丟掉（只留頭尾各 4 KiB），回 200＋`-32003`＋`Retry-After: 5`（頭尾認得出 id）
     或 503＋`-32003`、`id: null`；以前照常處理。
  2. 沒帶 `Content-Length`、讀到一半放不進預算的請求：停止讀取，回 200＋`-32003`（開頭認得出 id）或 503；以前照常處理。
  3. 重新序列化後要轉送給子程式的大小放不進預算（中文、emoji 等非 ASCII 內容）：200＋`-32003`（有 id），子程式收不到；以前照常轉送。
  4. 已登記的大請求（宣告超過 64 KiB 或沒帶長度）連續 30 秒沒有新位元組：408＋`-32003`＋`id: null`＋`Retry-After: 5`＋`Connection: close`；
     以前等到整體 60 秒才回 408 `{"error":"request denied"}`（整體 60 秒的回應照舊）。
  5. JSON 巢狀超過 64 層或元素（逗號＋容器）超過 20 萬個：200＋`-32602`（頭尾認得出 id）或 413＋`-32602`、`id: null`；以前照常解析
     （n8n：以前 413、`id: null`、「MCP JSON exceeds 64 levels of nesting」）。
  6. 不是 UTF-8 的 body（UTF-16／32、BOM、不合法的 UTF-8）：413（或 200）＋`-32602`、編碼專用的訊息；以前 UTF-16／32 照常解析，n8n 以前
     400＋`-32700`。
  7. 上面每一種拒收與超過 16 MiB 的 413 各記一行節流的 WARNING（每帳號每情況 60 秒一行；只有情況、HTTP 狀態與不含內容的短原因）。
- HM-01 的契約凍結逐案核對（`tests/contract/profiles_v1_cases.json` 的 99 案、黃金回歸、管理契約凍結）：**沒有一案的回應改變，凍結檔不用改**。
  理由：每一案的 body 都是 1 KiB 以內、合法 UTF-8、巢狀 4 層以內的 JSON（或沒有 body），全部 ≤64 KiB，不登記預算、不受閒置逾時，結構與
  編碼都在上限內；逐組（connect 2、error 46（含 order-）、unknown_token 8、header_switch 7、cross_profile 1、url_variant 31、token_change 4）的
  核對見 HM-31 筆記第 7 節。
- 測試：`tests/test_request_budget.py`、`tests/test_request_structure.py`、`tests/test_request_budget_gateway.py`（開關關與開兩種模式）；
  `tests/test_n8n_request_bounds.py` 的深度一案改成新回應。

## 2. MCP（8081）

### 2.1 路徑與方法

| 路徑 | 方法 | 沒開通（今天） | 開通後 |
|---|---|---|---|
| `/mcp` | GET、POST、DELETE；其他方法在 token 檢查之後回 405（`Allow: GET, POST, DELETE`） | Bearer 對預設帳號 | 剛好一個 `Authorization`、字面 `Bearer <token>`，依 token 選帳號 |
| `/private_<token>/mcp` | 同上 | 密鑰網址對預設帳號 | 依路徑裡的 token 選帳號；路徑上的 `Authorization` 一律不看 |
| `/health/ready` | GET | `{"ready":bool}`，200／503，只看預設帳號 | 不變（DQ-19 已定：只看預設帳號） |
| 其他路徑（含 `/mcp/`、裸 `/private_<token>`） | — | 404 | 404（交預設 app） |

- MCP 路徑帶 query：400（在 token 檢查之後，同今天）。
- Bearer `/mcp` 帶任何 `Origin`：403（同今天；§8.8 #10）。密鑰網址的 Origin 見第 2.6 節。

### 2.2 帳號解析（分派器，開通才掛）

1. 只看 `scope["path"]` 與 `Authorization`。`/private_{secret}/mcp` 用 Starlette 自己的 `Route` 比對取出 secret；
   `/mcp` 要剛好一個 `Authorization`、字面 `Bearer <token>`；其他路徑交預設 app。
2. 候選 token 先 sha256 一次，再和每個帳號的摘要 `hmac.compare_digest`：預設帳號＋索引內讀得到、沒休眠、沒隔離的帳號；
   撤銷的略過。**全部比完、不提早結束。**
3. 快取：每帳號只存 state 的 stat 簽章與 token 摘要（回覆遮罩另記目前的 token 與 child_token，只拿來遮）；簽章變了才重讀。
   簽章：st_dev、st_ino、st_mtime_ns、st_size、st_nlink、st_mode，額外帳號再加 st_ctime_ns（它的讀取不 chmod；預設帳號的 store
   每次讀都 fchmod，ctime 一直變）。額外帳號的目錄還要是開啟時那一個（st_dev、st_ino；HM-07 審查 S-08），不是就不路由。
4. 命中後、讀 body **之前**做該帳號的准入。位元組預算（HM-31 起和 PaaS #155 合成一套，開關開與關都生效；第 1.2 節）由帳號 app
   在 token 驗過之後扣：全 add-on 一份預算，每個帳號一個份額（第 5 節），兩層都放得下才放行。
   - 扣什麼：大請求（宣告的 `Content-Length` 超過 64 KiB，或沒帶）的請求內容，取「收到的」與「轉送給子程式的」兩者較大的；兩者都 ≤64 KiB 的
     小請求不扣、也不會被預算拒絕（PaaS）。宣告的長度在讀第一個位元組之前就扣；沒帶的邊讀邊扣；超過單一請求上限（16 MiB，n8n 4 MiB）的
     不扣（照舊回 413）。
   - 扣到什麼時候：扣到請求結束（回應送完，SSE 串流的最後一個位元組也算，或用戶端離開；`gateway.AnyMethod` 在請求結束時一定歸還）。
     理由（HM-08 審查 MF-1）：子程式對 POST 預設回 SSE，標頭在工具開始跑之前就送出（mcp 2.3.0、FastMCP 4.1.3 都是）；閘道轉送的那份內容被
     httpx 的回應物件引用，留在記憶體直到串流結束。PaaS 也是扣到送往子行程的回應結束。
   - 為什麼扣轉送的大小（HM-08 審查 S-1；HA 加嚴，第 9 節）：閘道轉送前重新序列化（ASCII 跳脫），中文 1 字 3 位元組變 6、emoji 4 位元組
     變 12；數字也照 Python 的寫法重寫（`1e15` 變 `1000000000000000.0`）。帳號 app 在送出前扣；放不下就不送，回第 2.4 節的忙碌回應。
   - 宣告的長度放不下時，讀之前就拒絕：內容讀完丟掉，只留頭尾找 id（第 2.4 節）。
5. 帳號 app 裡是今天的流程：再驗 token → 租約 → 方法 → Origin → query 400 → 讀 body → 政策 → session →
   轉送名額 → 重驗 → 轉發。只轉閘道自己的 child bearer 與 3 個 session 標頭（`mcp-session-id`、`mcp-protocol-version`、
   `last-event-id`）；只轉回 4 個標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`）。

### 2.3 解析結果

| 情況 | 回應 | 備註 |
|---|---|---|
| 剛好一個帳號 | 交該帳號 app，用自己的 store 再驗一次 | 路由錯只會被拒 |
| 零個 | 交預設 app：密鑰網址 404、Bearer 401＋`WWW-Authenticate: Bearer` | 與今天逐位元相同；不佔准入、不讀 body |
| 兩個以上（撞號） | 503 `{"error":"state unavailable"}`，不轉任何帳號 | WARNING 每組 60 秒一行（id 前 8 碼）；DQ-09 已定：503 |
| 預設 state 讀不到、索引結構壞 | 503 `{"error":"state unavailable"}`（含預設帳號） | 索引壞的處理見第 3.6 節 `profile_index_state`；`/health/ready` 這時回 503 `{"ready":false}`（它只代表預設帳號，DQ-19，而預設帳號這時不服務）；其他非 MCP 路徑照預設 app（404） |
| 索引被面板以外改動（簽章不符） | 503 `{"error":"state unavailable"}`，直到重啟 | 簽章含 st_dev、st_ino、st_mtime_ns、st_ctime_ns、st_size、st_nlink；同 uid 下不是安全邊界 |
| 全部撤銷時寫入失敗的帳號 | 該帳號 503，直到重試成功 | 重啟時 `.revoke-all-pending` 讓守門在 listener 前重做 |

### 2.4 准入、位元組預算與過載回應

數值見第 5 節。准入與 GET 串流上限只在開通的產品（分派器）；位元組預算、讀取閒置逾時與 JSON 結構守門開關開與關都生效（HM-31，第 1.2 節）。
拒絕的形狀：

| 情況 | HTTP | 內容 | 附註 |
|---|---|---|---|
| 准入滿，`Content-Length` ≤64 KiB（或沒帶，但 2 秒內讀完且 ≤64 KiB）的 POST，不是通知也不是回應，解析得出 JSON-RPC id | 200，`Retry-After: 5` | 每個 id 一則 `-32003`（准入的文字） | HM-31（HM-14 審查 MF-2 (b)）起照 PaaS：准入滿時仍讀這種小請求，讀的數量不設上限（PaaS 小請求不計入、讀取中的數量不設限；8081 外框限住總數）；拒絕小額度（同時 8 個、合計 512 KiB）拿掉 |
| 准入滿，同上但只有通知或回應（`gateway.carries_no_request`） | 照常處理（`notifications/initialized` 經保留名額送到子程式，202） | — | 超出准入照常交帳號 app（`ProfileGate.beyond` 計數，不佔准入）；保留名額有自己的 4 條與佇列，滿了照第 6、7 列回答 |
| 准入滿，其他（沒有 id、解析不了、讀不完、大於 64 KiB 或沒帶長度又超過、GET、DELETE） | 503，`Retry-After: 5` | `-32003`，`id: null` | 大於 64 KiB 的不讀（PaaS 讀全部 body：§8.8 #16） |
| 大請求宣告的 `Content-Length` 放不進預算（帳號的份額或全 add-on 的預算） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003`（哪一層預算已滿；PaaS 原文） | 讀第一個位元組前就拒絕，內容讀完丟掉，只留頭尾各 4 KiB 找 id（PaaS `_refuse_over_budget`：先送完內容才讀回應的用戶端看得到回應，不是連線重設）；丟的時候用戶端離開回 499（沒有人收得到）；閒置 30 秒或整體 60 秒就不再等、照樣回答。子程式收不到 |
| 沒帶 `Content-Length`，讀到一半放不進預算 | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003` | 立刻停讀、已扣的還回去，id 從已讀到的開頭找（PaaS N5）；子程式收不到 |
| body 已讀完，閘道重新序列化後要轉送的大小放不進預算（非 ASCII 內容；第 2.2 節第 4 點） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003` | HM-08 審查 S-1 起；子程式收不到這個請求；WARNING 和「位元組預算」同一種情況 |
| 已登記的大請求（宣告超過 64 KiB 或沒帶）讀取中連續 30 秒沒有新位元組 | 408，`Retry-After: 5`，`Connection: close` | `-32003`，`id: null` | 放棄這個請求、已扣的還回去（PaaS P2-D）。整體讀取上限仍是今天的 60 秒（`BODY_SECONDS`，每個請求都有；PaaS 300 秒、只有登記的大請求）：到了照今天回 408 `{"error":"request denied"}`（§9 #105） |
| POST 的 JSON 巢狀超過 64 層、元素（逗號＋容器，字串內的不算）超過 20 萬個，或不是 UTF-8（UTF-16／32、BOM、不合法的 UTF-8） | 頭尾認得出 id 200，否則 413 | `-32602`，訊息只寫哪一項超過或「不是 UTF-8」，不含內容 | 在解析之前、只掃描結構字元（`request_limits.structure_violation`、`not_utf8`；PaaS 原樣）；n8n 先跑同一道守門再跑自己的上限；子程式收不到 |
| 轉送名額等 1 秒逾時（body 已讀），有 id | 200，`Retry-After: 5` | 每個 id 一則 `-32003` | #148 形狀（開通的產品 HM-08 起；HM-14 定案：一般名額與保留名額各自計時、文字寫那一組自己的條數） |
| 轉送名額等 1 秒逾時，沒有 id（GET、DELETE、保留名額也用完的通知） | 503，`Retry-After: 5` | `-32003`，`id: null` | 同上 |
| 排隊已達上限（每個佇列各自計數：一般名額 32／16 個、保留名額另 32／16 個） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003`（排隊的文字） | 不等、不排隊、不送出；WARNING 每帳號每情況 60 秒一行（HM-14） |
| 排隊時用戶端關閉連線（那個請求的連線被關掉） | （沒有人收得到：程式內部回 499，伺服器不送給已離開的用戶端） | — | 請求從排隊移除、絕不送出；名額剛好同一刻空出時也還回去、不送；只記 WARNING（HM-14） |
| GET 串流已達上限 | 429，`Retry-After: 30` | `-32003`，`id: null` | 預設帳號 24 條、額外帳號 8 條 |
| 該帳號待送回覆位元組超過上限 | 200 | 新的 tools/call 在轉送前回 `-32003` | 只在開通的產品（第 6 節） |

- 只有通知或回應、沒有任何請求的 POST 走保留名額（每帳號 4 條，有自己的佇列）；判斷照 PaaS `_carries_no_request`
  （`gateway.carries_no_request`，HM-14）：POST、可解析、物件或非空陣列、裡面沒有任何請求（有字串 method、id 不是 null）、每則都是
  通知或回應；看不懂的一律走一般名額。HA 的政策只收單一訊息（`policy.authorize`：batch、對伺服器請求的回應、沒有 id 的工具呼叫在任何
  名額之前就 403；`notifications/initialized` 以外的通知由閘道自己回 202、從不轉送），所以實際走保留名額的只有
  `notifications/initialized`（§8.8 #91）。GET 串流、DELETE 一律走一般名額。
- **准入滿時保留名額照樣送到**（HM-14 審查 MF-2；2026-11-16 07:5x 主對話定案 (b)，照 PaaS 的語意，HM-31 實作；DQ-07 的數值不改）：
  - 准入在讀 body 前算，進行中的每個請求（讀 body 中、排隊中、轉送中）與開著的 GET 串流都各佔一個。照第 5 節的數值，准入剛好是轉送名額＋排隊上限
    （預設 64＝32＋32，額外 32＝16＋16），所以一般名額和它的佇列都滿時，准入也滿。
  - 這時 ≤64 KiB 的 POST 仍讀進來（2 秒內，同時讀幾個不設上限）：只有通知或回應的照常處理，`notifications/initialized` 經保留名額送到子程式
    （202）；其他小請求回准入的忙碌回應（有 id 200）。PaaS 讀 body 前沒有准入、小請求不計入預算也不限讀取中的數量，保留名額的目的是讓通知
    一定送得到（MCP Python SDK 1.x 收到非 2xx 會結束 session、TS SDK 的 `connect()` 失敗、SDK 2.x 丟掉這則通知）。
  - 剛連上的用戶端：它的 initialize 是帶 id 的請求，准入滿時拿忙碌回應（200＋`-32003`）；在准入有空位時連上的，之後的 `notifications/initialized`
    一定送到（`tests/test_carries_no_request.py` 的
    `test_a_newly_connected_clients_initialized_reaches_the_child_with_the_queue_and_admission_full`、
    `test_the_reserve_is_reached_even_once_the_profiles_admission_is_full`）。
- GET 串流整段佔住一條一般名額和一個准入（UC-31，HM-14 審查 S-3）：額外帳號開滿 8 條串流時 POST 剩 8 條名額，預設帳號開滿 24 條時
  剩 8 條（`tests/test_gateway_queue_ha.py::test_get_streams_hold_ordinary_slots_for_their_whole_life`）。
- 排隊中 token 被輪替或撤銷：請求拿到名額或等滿 1 秒後重驗時被拒（Bearer 401、密鑰網址 404），子程式收不到；最多多佔 1 秒的排隊位置
  （PaaS 把排隊包在 token 租約裡、立刻取消：§8.8 #98；HM-14 審查 S-7）。
- 等名額的期間閘道看用戶端在不在：只認「那個請求的連線被關掉」（HTTP 層逾時、斷線、關閉 transport）。下面兩種看不到，不在保護範圍
  （PaaS `docs/mcp-gateway-limits.md` 的已知限制，19f36e2、`091dfbc`；HA 同樣適用，寫進威脅模型第 3 節，HM-18 寫進 DOCS）：
  - MCP SDK 層級的請求逾時（例如 `read_timeout_seconds`）與取消只送 `notifications/cancelled`，不關閉那個 POST 的連線；
  - MCP Python SDK 2.3.0 預設的關閉路徑：`terminate_on_close=True`（預設）時，離開 transport 會先送 DELETE 並等回應，才取消 POST。
    名額被佔滿時那個 DELETE（沒有 JSON-RPC 內容，走一般名額）排在 POST 後面，POST 的連線一直開著，**排隊中的寫入在名額空出後照樣被
    執行**。`terminate_on_close=False` 時 transport 立刻關閉，寫入被丟掉。
  這兩種請求最多等 1 秒（HA 的等候；PaaS 10 秒），等不到就回 `-32003`、不送出。
- `-32003` 的訊息是固定文字（HM-14 定稿）：寫出是哪一種上限與「稍後重試」，不含 token、網址或帳號名稱。HM-08 的准入、轉送名額、GET 串流
  三種照原文定稿；位元組預算的改成 PaaS 原文（HM-31：`request_budget.budget_text`，寫出是「這個 MCP 網址」的份額還是「這台 MCP 伺服器
  （所有網址合計）」的預算與上限）；讀取閒置的 408 也是 PaaS 原文（`request_budget.idle_text`）；HM-14 加保留名額與排隊兩種，每種都寫
  那一組自己的條數（`profile_router.forward_text`、`queue_text`；PaaS 審查 N8）。WARNING 每帳號每情況 60 秒一行（`suppressed=N`），帳號只寫
  id 前 8 碼（沒開通的產品寫 `profile=default`）。
- 「解析得出 JSON-RPC id」＝`Content-Type: application/json`、strict JSON、單一物件、`jsonrpc` 是 `"2.0"`、`method` 是字串、
  `id` 是字串或整數（閘道 `authorize` 收的請求）。batch、通知、回應、布林或小數 id 都算「沒有 id」：HA 閘道從不回 batch
  （HM-08 定案）。GET、DELETE 沒有 body，一律 `id: null`。沒有解析的 body（位元組預算與結構守門的拒收；HM-31）照 PaaS
  `request_body._request_id` 只看頭尾：開頭是 `{"jsonrpc":"2.0","id":…,"method":` 或開頭是 `{"method":"` 而結尾是
  `,"jsonrpc":"2.0","id":…}`（MCP SDK 的寫法），id 是整數或 256 字以內的字串；其他寫法都算沒有 id（`request_limits.head_tail_id`）。
- 沒開通的產品照今天：8081 外框 `limit_concurrency=64`，超過時是 uvicorn 純文字 503。開通後每個帳號的上限改成上表的 JSON-RPC
  忙碌回應（計畫 §7.2 第 3 點）；8081 外框（64＋32×產品上限）仍是**全 add-on 共用的連線數**：閒置的 keep-alive 連線、沒帶 token
  的連線也算，外框滿時任何人（不分帳號）的新連線拿到的仍是 uvicorn 純文字 503（既有，G2 S7，不在計畫範圍；HM-08 審查 S-5 實測：
  223 條不帶 token 的 keep-alive 連線就讓 B 的新連線拿到 503）。所以每帳號隔離只在請求層成立（第 5 節）。

### 2.5 回應途中與子程式斷線（HM-14）

只在開通的產品（`make_apps` 給了 `slot_busy`）；沒開通照今天（第 4.2 節：502 `{"error":"request denied"}`、SSE 安靜結束、
token 換掉時 `ClientDisconnect` 丟給 uvicorn）。HM-14 定案：

| 情況 | 標頭送出前 | 標頭送出後（SSE） | 標頭送出後（一次送完的 JSON） |
|---|---|---|---|
| token 被輪替、撤銷或帳號被刪 | 密鑰網址 404、Bearer 401（PaaS 403：§8.8 #1）；標頭卡在背壓、伺服器還沒收下時也一樣（閘道自己送這個拒絕，逐位元同） | 還沒送到的回覆補一則同 id 的 `-32005`（GET 串流不補），正常結束 | 不能再送（`Content-Length` 已定）：閘道直接返回、伺服器關掉連線（§8.8 #92） |
| 子程式中途斷線 | 502＋`-32004`（帶得出 id 就帶，通知、GET、DELETE 是 `id: null`） | 補一則同 id 的 `-32004` 事件後正常結束（GET 串流不補） | （JSON 回覆是讀完才送：算「標頭送出前」） |

- 「子程式中途斷線」＝連上之後的讀、寫或協定錯誤（`httpx.ReadError`、`RemoteProtocolError`、`WriteError`…）。連不上（`ConnectError`）照今天
  （有內附清單的產品由閘道自答 initialize 或回 session 已結束的 404，其他 502）；逾時、子程式回錯的東西（3xx、401、403、格式錯、超過 8 MiB、
  協定版本不在清單）照今天 502 `{"error":"request denied"}`。initialize 的回覆讀到一半斷線也是 `-32004`；子程式正常結束串流卻沒有回覆，
  照今天 503 `BACKEND_UNAVAILABLE`。
- `-32004` 依原因用三種固定文字：「子程式停止了（會自動重新啟動）」、「子程式停止了，目前沒有在重新啟動（被擋下、失敗、已停止或沒有設定，
  原因見 add-on 的 log）」或「連線中斷，子程式仍在執行」，都寫「操作可能已完成也可能沒有，請先確認再重試」（`gateway.CHILD_STOPPED_TEXT`、
  `CHILD_HALTED_TEXT`、`CHILD_CONNECTION_TEXT`）。看的是轉送那一刻的世代（`Supervisor.starts`，健康監看的子程式欄位）：之後 start 數變了、
  或狀態不是 `running`，就是停止了；看起來還在跑時最多再等 0.25 秒（`CHILD_EXIT_GRACE_SECONDS`）。
  子程式停止時，它為 initialize 開的 session 不再 DELETE（跟著子程式結束）。
- 停止了的兩種文字看停止之後那一刻的狀態（HM-09 的 `Supervisor.status`；`gateway.CHILD_RESTARTING_STATES`）：`backoff`（看門狗等退避後再起）、
  `starting`（正在起）或新世代的 `running` 才說「會自動重新啟動」；`blocked`（停用的帳號、記憶體不夠、spawn 前檢查拒絕）、`failed`（監看停止，
  DQ-21）、`stopped`（帳號被刪、add-on 在停）、`unconfigured`（沒有存連線）說「目前沒有在重新啟動」（HM-14 rebase 到 HM-09 之後；
  PaaS 一律說會自動重新啟動：§8.8 #100）。沒有健康監看可比（沒有世代）時照原本的說法（停止了、會自動重新啟動）。WARNING 照舊只分「停止了」與
  「仍在執行」兩種原因。
- log：帳號的 WARNING 一行（id 前 8 碼、HTTP 方法、httpx 錯誤的類別名、哪一種原因），每帳號每種原因 60 秒一行，不帶 traceback、路徑、
  token 或內容（PaaS 每次一行：§8.8 #93）。
- `-32005` 的文字固定（`gateway.ACCESS_CHANGED_TEXT`）：token 被輪替或撤銷、閘道已停止這個回應、請用目前的網址或權杖重新連線。閘道的
  結尾（拒絕、`-32005`、結束訊息）最多送 2 秒（`ENDING_SECONDS`，同 PaaS 的 2 秒）；用戶端完全不讀時放棄、不丟例外（之後 uvicorn
  記一行 `ASGI callable returned without starting response.`，用戶端恢復讀取時拿到純文字 500；PaaS 同樣的取捨）。
- 「回覆已送到」＝伺服器收下了那個請求的回答：子程式的回覆，或閘道自己補的 `-32004` 事件（HM-14 審查 S-1）。收下之後 token 才換掉，
  不再補 `-32005`（JSON-RPC 一個請求只回一則）。PaaS 的 `_Interruption` 只看子程式的回覆、而且只在產生器續跑時記「已送到」：回覆在
  token 換掉那一刻被收下，或 `-32004` 已送出後 token 才換掉，都會再補一則同 id 的錯誤（§8.8 #97）。回應已完整送出（最後一則訊息已被收下）
  時，閘道什麼都不再送。
- **initialize 世代**（FM-43）：閘道記下 initialize 送去的世代（`Supervisor.starts`），子程式的 session 只在那個世代仍是執行中的那一個
  時才交給用戶端（標頭送出前一刻檢查）。換代、結束或被停時用戶端拿 503 `BACKEND_UNAVAILABLE`＋`Retry-After: 5`、沒有 session id
  （§8.8 #94），那個 session 不 DELETE（會打到下一個世代）。標頭已經在送的 session 收不回來：用戶端之後在那個 session 的請求拿到新子程式的
  404，照 MCP 重新 initialize。HA 沒有 PaaS 的 drain（重啟不等閘道送完）。listener 是不是同一個程序屬 HM-15（FM-41，條件式）。
- 不把例外丟給 uvicorn：上面每一種結尾都由閘道自己送完並返回。有兩個例外會讓 uvicorn 記一行（都沒有 traceback）：
  - 「一次送完的 JSON 標頭已出去」：閘道返回，uvicorn 記 `ASGI callable returned without completing response.` 並關掉連線；
  - 用戶端完全不讀、結尾 2 秒內送不出去（上面 `-32005` 那一點）：uvicorn 記 `ASGI callable returned without starting response.`。

### 2.6 Origin（DQ-11 採 (a)，HM-27）

- Bearer `/mcp` 帶 Origin：一律 403（同今天）。
- 密鑰網址：服務層級清單（全部帳號共用）預設 `https://claude.ai`、模式 report-only；清單外來源**照常放行**，記一行 would_deny
  （帶帳號 id 前 8 碼、每帳號節流）；**不加任何 CORS 標頭**。report-only 不改任何回應位元組。
- Headscale：密鑰網址維持只放 `https://claude.ai`（enforce，同今天；§8.8 #9）。
- 第二問（Claude.ai 送 `https://claude.ai` 時 Bearer 要不要精確放行）：待定，S14 實測後再問（HM-03b／HM-19b）。

### 2.7 回覆遮罩與不讀的東西

- 回覆遮罩＝本帳號 `secret_values(state)` ∪ **所有帳號**（含預設、孤兒、休眠）目前的 token 與 child_token；後端密碼仍只用本帳號
  （§8.8 #38，DQ-40 ⑧）。
- 8081 永遠不讀 `X-MCP-Profile`、cookie、query 來選帳號；密鑰網址上絕不改看 `Authorization`（I1）。

## 3. 管理（8099）

### 3.1 路徑與方法

**全域路徑**（不看 `X-MCP-Profile`；開通後才存在，沒開通 404）：

| 路徑 | 方法 | 用途 | 寫入保護 | 成功回應 |
|---|---|---|---|---|
| `{base}/api/profiles` | GET | 帳號清單 | — | 200 `{"profiles":[列…],"orphans":[{"id"}…]}`（孤兒：`profiles/` 底下有、索引沒有的帳號目錄，列出可刪；HM-10）；`ETag: "p1-<64 hex>"`（索引 ETag） |
| `{base}/api/profiles` | POST | 建立 `{"label":…}` | If-Match（索引）＋Idempotency-Key | 201 該列（**不含 token**）＋`operation`；同一 key 重送回 200＋目前那一列＋`operation`（`replayed:true`；帳號已被刪掉時只回 `{"id","operation"}`；HM-10） |
| `{base}/api/profiles/<id>` | PATCH | 改名 `{"label":…}` | If-Match（索引） | 200 該列 |
| `{base}/api/profiles/<id>` | DELETE | 刪除（含孤兒與讀不到的帳號；DQ-14 已定（2026-11-15 17:4x 使用者採用建議）：先撤銷 token 並抹掉後端憑證再刪、孤兒不自動刪、面板列出可刪、不做軟刪除、兩段確認在面板（HM-11）） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<id>","operation":…}`；重送同 |
| `{base}/api/profiles/revoke-all` | POST | 全部撤銷（含預設） | If-Match（索引）＋Idempotency-Key | 200 逐帳號 `results:[{id,result:"revoked"}]`；有失敗見第 4.1 節 `operation_outcome_unknown` |
| `{base}/api/profiles/restore-record` | GET | 還原與休眠核對紀錄（不含秘密） | — | 200（欄位第 3.6 節） |
| `{base}/api/profiles/<id>/restore-review` | POST | 標記「已核對」 | If-Match（索引）＋Idempotency-Key | 200 `{"profile":{"id"},"reviewed_at":…,"operation":…}`（暫定，HM-13c） |
| `{base}/api/profiles/index/quarantine` | POST | 隔離不能用的帳號索引（壞掉或被外改；DQ-12） | If-Match（壞索引的 ETag，bootstrap 的 `profile_index_etag`）＋Idempotency-Key | 200 `{"quarantined":"<改名後的檔名>","operation":…}`；重送同；索引能用時 409 `config_conflict`（HM-10） |
| `{base}/api/profiles/quarantine/<名稱>/delete` | POST | 刪除一個隔離目錄（`<名稱>`＝目錄名去掉 `.quarantine-` 的 `<id>-<UTC>`；同一個 id 可能有多個） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<名稱>","operation":…}`（暫定：路徑、名稱格式與回應都由 HM-13c 定案） |
| 頁面與靜態檔 | GET、HEAD | 面板 | — | 同今天（開通後改由預設帳號的動作回，多一次角色檢查；PUT、POST 照今天 404，PATCH、DELETE 照今天 405 的位元組，但在 identity 之後；HM-10） |

**帳號範圍路徑**（其他 `{base}/api/*`；開通後一定要剛好一個 `X-MCP-Profile`）：

| 操作 | 方法 | 開通後的變化 |
|---|---|---|
| `bootstrap` | GET | 多 `profile`、`profiles_supported`；預設帳號另帶索引狀態、休眠與還原通知（第 3.6 節） |
| `configuration`、`capabilities` | GET | 回應帶 `profile:{id}` |
| `diagnostics` | GET | 只回選定帳號的子程式緩衝 |
| `operations/<id>` | GET | 收據依帳號 |
| `backend`、`backend/patch` | PUT | Odoo 換 url／database／username 換 token、回 `token_rotated:true`（HM-12；DQ-05 已定，照計畫 §9）；改 url 來源沒帶新秘密 422（DQ-40 ⑨）；這次存檔改到的後端網址是 loopback（127.0.0.0/8、::1 的各種寫法、`localhost`）或是不允許位址的數字寫法，一律 400 `{"error":"request denied"}`；n8n 也一樣，而且開通後另外套上既有的整套存檔檢查（同其他產品，HM-20；§8.8 #39） |
| `backend/test` | POST | 測選定帳號已存的設定 |
| `policy`、`odoo/write-switches`、`odoo/allowed-methods`、`n8n/session` | PUT | 只重啟選定帳號的子程式 |
| `endpoint` | PUT | 額外帳號 409 `endpoint_global`、什麼都不寫；額外帳號的 bootstrap 顯示預設帳號的 `endpoint`（全域設定只存在預設 state；DQ-13 已定，2026-11-15 17:4x 使用者採用建議） |
| `token/reveal`、`token/revoke` | POST | 只動選定帳號 |
| `token/rotate` | POST | 還原或休眠後未核對前 409 `restore_review_required` |
| `child/restart` | POST | 回應帶 `blocked_reason` |
| `owner-defaults/restore`、`owner-defaults/dismiss` | POST | 只在預設帳號；額外帳號 409 `owner_defaults_unavailable`（形狀 C，在 If-Match 之後），不管它的目錄裡有什麼；額外帳號的 bootstrap 也一律沒有 `owner_defaults` 通知（FM-08；HM-10） |

- 方法：只有 `profiles/<id>` 接受 PATCH、DELETE；其他路徑的 PATCH、DELETE 回 405。開通後 8099 的路由要收 PATCH、DELETE，
  方法表改在管線第 ⑤ 步檢查（identity 之後）；沒開通照今天（路由層直接 405）。HM-10 定案：405 的位元組同今天 Starlette 的
  （純文字 `Method Not Allowed`、`Allow` 列這個路徑收的方法：帳號範圍路徑與頁面 `GET, HEAD, POST, PUT`，`profiles` `GET, POST`，
  `profiles/<id>` `PATCH, DELETE`，`profiles/index/quarantine` `POST`）；全域路徑用表外的方法也是 405。`profiles/` 底下其他路徑是
  未知操作：角色檢查之後回空本體的 404（同今天的未知操作），不看 `X-MCP-Profile`。
- 開通後預設帳號看得到的兩個位元組變化（HM-10 審查 S-6；不影響安全，要寫進計畫 §7.2 的清單、該產品的 CHANGELOG 與
  `upgrade-notes.yaml`，交 HM-18 或升版片）：(1) PATCH、DELETE 沒帶 CSRF：沒開通是路由層的 405（identity 之前），開通後是 identity 的
  403；(2) 8099 收到這六個方法以外的方法（OPTIONS 等）：開通前後都是路由層的 405（identity 之前），但 `Allow` 列的方法從
  `GET`、`HEAD`、`POST`、`PUT` 四個變成六個（多 `PATCH`、`DELETE`）。列的順序是 Starlette 的集合順序，開通前後都不固定。
- 管理請求帶 query、`raw_path` 含 `%` 或 `\\`：400（同今天，§8.8 #48）。

### 3.2 共用管線（開通後**所有**路由都走，含全域路徑）

| 步 | 做什麼 | 失敗回應 | 看不看帳號狀態 |
|---|---|---|---|
| ① | identity：來源 172.30.32.2、剛好一個 `X-Remote-User-Id`、非 GET 要 CSRF、不是 cross-site；`X-Ingress-Path` 格式 | 403（沒有 detail）；`X-Ingress-Path` 不只一個或格式錯 400 | 不看 |
| ② | 管理名額 16（全 add-on 共用） | 503 | 不看 |
| ③ | 有界讀 body（同今天） | 400／403（讀到一半斷線）／408／413／415（要 JSON 的路徑 `Content-Type` 不是 `application/json`） | 不看 |
| ④ | 斷線監看 | 403 | 不看 |
| ⑤ | 方法表與**不讀任何 state** 的格式檢查（JSON 形狀、鍵集合）；未知的 `/api/*` 操作照今天在角色檢查之後才回 404 | 固定 400／405，沒有細節 | 不看 |
| ⑥ | **角色檢查一**（`final_role`） | 403（Core 未審帶 `core_version_unreviewed`） | 不看 |
| ⑦ | 解析 `X-MCP-Profile`（帳號範圍路徑） | 400 `profile_id_required`／`profile_id_invalid`；404 `profile_not_found`；索引壞 503 `profile_index_corrupt` | 看 |
| ⑧ | 拿鎖：帳號增刪改用全域 CRUD 鎖，帳號範圍用該帳號 `mutation_lock`；最多等 2 秒 | 503 | — |
| ⑨ | 讀 state、依 state 驗證（今天 `admin_action` 的格式驗證） | 固定 400 | 看 |
| ⑩ | **角色檢查二**（最後一次；之後到揭露或提交之間不得 await） | 403 | — |
| ⑪ | If-Match、Idempotency-Key、名稱規則與衝突、容量、全域路徑的帳號存在、新來源秘密等狀態相依判斷 → 提交 | 404／409／410／422／428（第 4.1 節） | 看 |

- 非管理員最遠只到 ⑥：名稱存不存在、到上限沒有、帳號存不存在、缺不缺標頭，拿到的都是逐位元相同的 403（I10）。
- 沒開通（且沒有帳號資料）的產品維持今天的順序；開通後預設帳號只多一次 Core 角色查詢、角色檢查提早，回應位元組不變。
- 新增路由沒進「路由表自動產生的否定矩陣」就測試失敗（HM-10 `tests/test_admin_pipeline_matrix.py`）。
- HM-10 定案的做法：
  - 開通後 8099 是管理分派器（`profile_router.AdminDispatcher`）。頁面檢查（identity、`%`、`\\`、query、頁面寫入）與 ①～④ 是從
    `make_apps` 的 `admin_page`、`admin_api` 抽出來的同一段程式（`gateway.management_operation`、`management_exchange`），沒開通時
    `make_apps` 照舊用它們，位元組不變。路由表是 `gateway.PROFILE_OPERATIONS`（帳號範圍）與 `profile_router.GLOBAL_ROUTES`（全域）。
  - ⑤：全域路徑的方法表、本體剛好 `{"label": <字串>}`、路徑裡的 `<id>` 是 `default` 或 24 位小寫 hex；帳號範圍路徑只有方法表
    （PATCH、DELETE 回 405），本體的格式驗證照今天在該帳號的動作裡（⑨），所以非管理員連格式錯都看不到，在 ⑥ 就 403。
  - 帳號是在 ⑥ 之後才選的，所以入口不能是任何一個帳號的 app：分派器自己跑管線，再呼叫選定帳號的動作（⑧～⑪，今天的
    `admin_action`）。頁面與靜態檔交預設帳號的動作（照今天：拿鎖、角色檢查、回檔案）。
  - 全域路徑的 ⑧～⑪（`profile_admin.ProfileAdmin`）：清單是讀取，不拿鎖；建立、改名、刪除、索引隔離拿全 add-on 的帳號鎖，
    刪除再拿目標帳號的 `mutation_lock`，索引隔離再依 id 順序拿每個已登錄額外帳號的 `mutation_lock`（HM-10 審查 S-1）；一律先全域、
    再帳號，不會互鎖；每把最多等 2 秒（503，已拿到的鎖放掉、什麼都不做）。⑩ 在拿完所有鎖之後。刪除拿著目標帳號的鎖到它移除登錄為止，
    索引隔離拿著每個帳號的鎖到它移除登錄為止：該帳號進行中的 token 變更、存檔、重啟先做完再被撤銷；途中才來的請求拿到鎖時 store 已關
    （503）。⑩ 之後到提交（寫索引）之間不 await。
    建立提交後，在新帳號自己的 `mutation_lock` 裡起它的子程式（和存檔起子程式一樣；這段時間有人對新帳號發的請求會等這把鎖，
    不會同時重起它；HM-09 審查 S-12）。開機的錯開啟動（`start_all`）與索引變更後的重評（`reevaluate()`）起子程式時
    （`ProfileRuntime.launch()`）也拿該帳號的 `mutation_lock`（HM-09 審查 S-12 第 2 點，HM-10 接線時做）：存檔或面板重啟正在
    重起它時就等它做完，兩邊不會交錯。
  - ⑪ 的順序：If-Match（缺 428；多個或格式錯 409）→ Idempotency-Key（缺 428、多個 400、重送：已完成照收據回、還沒完成 409
    `operation_outcome_unknown`）→ ETag 不符 409 → 各操作自己的判斷：建立是名稱規則 422 → 產品不開放 409 → 上限 409（FD 預算不夠、
    只服務預設帳號時 `limit` 是 0）→ 記憶體 409 → 名稱衝突 409 → 沒有 port 409（容量與衝突的先後照 PaaS）；改名是預設帳號 422 →
    不存在 404 → 名稱規則 422 → 名稱衝突 409；刪除是預設帳號 422 → 不存在 404；索引隔離是索引能用、ETag 不符或沒有索引檔可隔離 409。

### 3.3 `X-MCP-Profile` 規則（DQ-17 已定，照計畫 §5.3；負責片 HM-10）

| 情況 | 開通後的回應 |
|---|---|
| 帳號範圍路徑、沒帶 | 400 `profile_id_required`（§8.8 #31；PaaS 當 `default`） |
| 帶兩個以上 | 400 `profile_id_invalid`（§8.8 #83；PaaS 取第一個值，第一個值存在就照常服務） |
| 值不是 `default`、24 位小寫 hex | 400 `profile_id_invalid`（§8.8 #32；PaaS 404） |
| 格式對、不存在（含孤兒、隔離目錄、已刪除的帳號） | 404 `profile_not_found`；絕不退回預設帳號 |
| 存在但讀不到（`profile_unavailable`），或目錄已不是開啟時那一個（HM-07 審查 S-08 的管理面；8081 那一側見 §8.8 #88） | 503 `{"error":"state unavailable"}`；仍可刪除 |
| 額外帳號而索引不能用（壞掉或被外改） | 503 `profile_index_corrupt`；`default` 照常 |
| 全域路徑 | 不看這個標頭；路徑裡的 `<id>` 格式錯在第 ⑤ 步回固定 400（沒有細節），格式對但不存在在第 ⑪ 步回 404 `profile_not_found` |
| 沒開通的產品 | 不要求、不看（同今天） |
| 8081 | 永遠不看 |

面板開通後**每個**帳號範圍請求都帶這個標頭，包括明確的 `default`（第 3.4 節）。

### 3.4 帳號回聲

- `bootstrap` 回 `profile:{"id","label","is_default"}` 與 `profiles_supported`（產品有額外帳號時 `true`；OpenDesign、Odoo Manage
  就算被開通也是 `false`，面板不顯示新增按鈕，DQ-28）。預設帳號的 `label` 是 `Default`；改名後下一個回應就是新名稱。
- 其他帳號範圍的 JSON 回應都帶 `profile:{"id"}`。
- HM-10 定案（HM-05 的暫定照用）：回聲只加在帳號動作自己回的 JSON 物件（都在它最後一次角色檢查之後）；以例外拒絕的回應
  （`error_handler`：403、428、400…）與分派器自己的回應（⑤～⑦ 的拒絕）都不帶，所以非管理員拿不到任何帳號 id（I10）。加回聲時
  保留動作設定的每個標頭（含同名多值）與狀態碼。
- 面板一次變更內鎖定帳號：bootstrap 與變更兩個請求帶同一個標頭，兩個回應的回聲都要比對；不符就不顯示、藏起已顯示的 token、
  提示並重抓（I12；HM-11）。
- 任何帳號範圍請求回 `profile_not_found`：面板立刻重抓清單、切回預設帳號並提示。

### 3.5 寫入保護（DQ-15 已定，照計畫 §5.3 第 7 點；負責片 HM-10；§8.8 #34）

| 對象 | If-Match | Idempotency-Key | 收據放哪 |
|---|---|---|---|
| 帳號設定（`backend`、`policy`…） | 帳號 ETag `"c1-<64 hex>"`；HMAC domain 加帳號 id，拿 A 的 ETag 寫 B → 409 `config_conflict` | 照今天（`token/rotate`、`token/revoke`、`child/restart`） | 該帳號目錄的 `.state.json.operations.json` |
| 建立、刪除、全部撤銷 | 索引 ETag `"p1-<64 hex>"` | 要 | `/data/mcp/.profiles.json.operations.json` |
| 索引隔離 | 壞索引的 ETag（格式同 `"p1-…"`；bootstrap 的 `profile_index_etag`） | 要 | 同上 |
| 改名 | 索引 ETag | 不要 | — |
| 還原核對（restore-review） | 索引 ETag | 要 | 全域收據 |
| 刪除隔離目錄（暫定，HM-13c） | 索引 ETag | 要 | 全域收據 |

- 缺 If-Match 428 `config_revision_required`；不只一個或過期 409 `config_conflict`。
- 缺 Idempotency-Key 428 `operation_id_required`；不只一個 400 `operation_id_invalid`；同一個 key 還沒完成就重送 409
  `operation_outcome_unknown`；還原前的舊操作 id 410 `operation_restored`。
- 建立的回應與同一個 key 的重送**都不回 token**；token 只經 `token/reveal`＋`X-MCP-Profile: <新 id>`＋回聲比對取得。
- HM-10 定案：
  - 帳號 ETag 的 HMAC domain 是 `edit:<帳號 id>`（套用狀態的 `launch:<帳號 id>` 同理）：`ProfileRuntime` 建的每個帳號都帶，沒開通時的
    預設帳號也是（ETag 是這個程序的隨機金鑰算的，本來就不跨程序、不能預測，沒開通時用戶端看到的沒有差別）；n8n
    （`apps/n8n/run.py`）到 HM-25 前不帶。兩個帳號就算 state 逐位元相同、金鑰也相同，ETag 也不同。
  - 索引 ETag＝這個程序的隨機金鑰對「索引的每一筆（id、名稱、port）照順序」算的 HMAC：內容一樣 ETag 就一樣，改名、換順序、
    增刪就變；重啟後全部變。壞索引的 ETag＝同一把金鑰對索引檔的 lstat 簽章與原始位元組（最多 64 KiB＋1）算的 HMAC，換檔或改任何
    一個位元組都會變；只有索引隔離收它，其他寫入一律 409。
  - 收據放索引旁、格式同今天，另多一個 `subject`（建立與刪除是帳號 id、索引隔離是改名後的檔名；都不是秘密），讓重送回得出做了什麼。
    種類：`profile.create`、`profile.delete`、`profile.index_quarantine`。帳號自己的收據檔格式不變。
  - 提交後失敗（目錄建不起來、寫索引失敗、收據寫不進去）：409 `operation_outcome_unknown`，收據停在未完成，同一個 key 再送也是 409，
    不會做第二次；寫索引失敗時用手上的索引複查，被外改就維持 503（DQ-12），已建的目錄刪掉（它從沒被路由過）。

### 3.6 欄位

**清單列**（都不含秘密）：

| 欄位 | 值 |
|---|---|
| `id` | `default` 或 24 位小寫 hex |
| `label` | 預設帳號固定 `Default`（面板顯示「預設帳號」）；其他是使用者給的名稱 |
| `port` | 預設帳號 3000；額外帳號 18000 起 |
| `is_default` | bool |
| `disabled_reason` | `null`、`profile_limit`、`memory_capacity`、`port_conflict`（順序照 PaaS：產品上限 → 記憶體 → port）；HA 另有 `profile_unavailable`、`quarantined`、`dormant`（§8.8 #51；HM-10 寫 `profile_unavailable`：索引有、add-on 開不了的帳號，例如目錄不見或 state 讀不到） |
| `required_memory_mib` | 只在 `disabled_reason=memory_capacity` 時出現 |
| `status` | `running`、`starting`、`backoff`、`unconfigured`、`blocked`、`failed`、`dormant`（HM-10：子程式還沒起或正在重起的 `stopped` 算 `starting`；`profile_unavailable` 的帳號是 `failed`） |
| `blocked_reason` | `null`、`child_port_conflict`、`child_port_in_use`、`memory_capacity`（只在 `status=blocked` 時有值） |

列的鍵照這個順序：`id`、`label`、`port`、`is_default`、`disabled_reason`、（`required_memory_mib`）、`status`、`blocked_reason`；
清單另回 `orphans`（`[{"id"}…]`，依 id 排序）。都不含 token、child token、連線或憑證。

**bootstrap 增加的欄位**（開通後）：`profile`（第 3.4 節）、`profiles_supported`、`profile_index_state`（只在預設帳號；`ok` 或
`corrupt`；`corrupt` 包含被外改（DQ-12），這時另帶 `profile_index_etag`：由檔案簽章與原始位元組算出的 ETag，給「隔離帳號索引」用；
HM-10）、還原與休眠通知（欄位名 HM-13c 定案）。
沒開通但有帳號資料時只多 `dormant_profiles`（數字）。

**請求本體**：建立與改名都是剛好一個鍵 `{"label": <字串>}`。名稱規則（DQ-16 已定，照計畫 §8.5；負責片 HM-10、HM-11；§8.8 #35）：去頭尾空白後 1～80 個 code point；
拒絕 Cc、Cf（含 bidi、零寬）、Zl、Zp、Cs、Co、未指派；NFKC＋casefold 判重；`default` 與「預設帳號」保留。名稱只存在索引，
不進目錄名、log、MCP 回覆。

**還原紀錄**（`restore-record`，HM-13b 寫、HM-13c 讀；暫定）：還原時間；逐帳號 `id`、`label`、身分欄位（`identity_fields` 分類）、
政策摘要（寫入開關、停用工具、逐項寫入授權、禁止的操作、Odoo 方法清單、n8n session）、`reviewed_at`（`null` 或時間）、目前狀態；
隔離目錄清單；休眠段落。不含任何 token 或密碼，網址裡的帳密也不記。

**索引隔離**：先撤銷 `profiles/` 底下每個帳號目錄（與每個已登錄的額外帳號）的 token，再把 `profiles.json` 改名成
`profiles.json.quarantine-<UTC>`（同一秒已有這個名稱就加 `-2`、`-3`…，不覆蓋；HM-07 審查 S-15）；預設帳號立刻恢復（8081 不用重啟），
已登錄的額外帳號停掉、不再路由，帳號目錄都變孤兒、可逐一刪除。讀不到 state 而撤銷不了的目錄只記一行 WARNING（數量）：它本來就不會被
路由。HM-10 審查 S-1：撤銷之前先依 id 順序拿每個已登錄額外帳號自己的鎖（第 3.2 節 ⑧；任一把 2 秒拿不到就 503，什麼都不撤銷、不改名、
不留收據），一直拿到該帳號移除登錄為止，所以撤銷只做一次：索引改名之後，8081 不再路由任何帳號目錄的 token（含隔離開始時正在輪替的
新 token），隔離前拿的 If-Match 也寫不進被撤銷的 state。
面板 403（Core 未審）時這個動作也用不了。HM-10 定案：開機時 `profiles/` 列不出來（不是目錄、是連結或別的 uid 的）也算索引不能用
（8081 全部 503、bootstrap 是 `corrupt`，HM-08）；這時若沒有索引檔可隔離，隔離回 409 `config_conflict`，什麼都不撤銷、不留收據：
修好 `profiles/` 之後重啟 add-on 才恢復（隔離解決不了）。

**刪除**（DQ-14；HM-10）：撤銷 token（`TokenAccess.committed()`：帶著它的請求立刻結束）→ 抹掉後端欄位（`connection`、`backend_url`、
`backend_key`、`mcp_access_token`）→ 不再路由、停監看與子程式、關 client 與 store → 從索引移除（這時 port 才空出來）→ 刪目錄（從不跟隨
連結開啟、確認是本 uid 目錄的 `profiles/` 往下走，不跟隨任何連結；帳號自己的名稱是連結、或 `profiles/` 被換成連結都不刪；刪不乾淨只記
一行 WARNING，剩下的是孤兒）→ 立刻重評每個被擋的帳號（PaaS B-17）。孤兒與讀不到的帳號照同一順序刪（沒有的步驟
略過）。計畫 §4.4 的順序是「停子程式 → 移出索引 → 關 store 與 client」；HA 把關 store 與 client 放在移出索引之前（ProfileManager 的
`remove()` 一次做完），寫索引若失敗，那個帳號留在索引裡、已撤銷已抹除、不再服務，再刪一次即可。

### 3.7 Ingress 備援（只在 UC-10 證實 Ingress 不轉 `X-MCP-Profile` 或 PATCH／DELETE 時用；§8.8 #50）

- 使用者 2026-11-15 15:3x 決定（UC-10）：照 PaaS 用 `X-MCP-Profile` 標頭選帳號，**不做**網址路徑備案；HM-03a 實機探針證實 Ingress 不轉
  時才補。HM-10 沒有實作下面的路徑：`{base}/api/p/<id>/…` 是未知的帳號範圍操作（要標頭，角色檢查之後 404）。

- 帳號範圍改用路徑：`{base}/api/p/<id>/<操作>`，`<id>` 是 `default` 或 24 位小寫 hex。
- `PATCH {base}/api/profiles/<id>` 改成 `POST {base}/api/profiles/<id>/rename`；`DELETE` 改成 `POST …/<id>/delete`。
- 分派器先拒絕含 `%` 的 `raw_path`（400），再**同時**改寫 `path` 與 `raw_path`；帳號 id 只取 `raw_path` 裡未解碼的片段。
- 其餘規則（管線、回聲、寫入保護、錯誤代碼）不變；面板與 P9 驗收工具同版改用路徑。

## 4. 錯誤代碼（逐欄）

### 4.1 管理 API（8099）

回應本體：**新增的代碼**一律是 `{"error":"request denied","detail":{"code":"<代碼>", …欄位}}`。**既有回應**的本體照今天
（bb48449）有五種形狀；HM-01 的契約凍結照這裡凍結，HM-10 不把它們改成新形狀（否則沒開通時就不再逐位元相同）：

- 形狀 A：`{"error":"request denied","detail":{"code":…}}`。`config_revision_required`、`operation_id_required`、`operation_id_invalid`、
  `operation_id_expired`、`operation_id_conflict`、`operation_not_found`、`operation_journal_full`、`operation_journal_unavailable`、
  `operation_outcome_unknown`（可另帶 `operation`）、`core_version_unreviewed`（另帶 `ha_version`）。來源：`Hc/gateway.py:328`、
  `Hc/operations.py:35-36`、`Hc/admin_auth.py:18-22`。
- 形狀 B：`{"detail":{"code":"config_conflict"}}`，沒有 `error`（`Hc/gateway.py:466`、`:484`）。
- 形狀 C：`{"error":"owner_defaults_unavailable","detail":{"code":"owner_defaults_unavailable"}}`（`Hc/gateway.py:613-614`）。
- 形狀 D：`{"saved":true,"detail":{"code":"config_apply_failed"},"configuration":…}`，沒有 `error`；`owner-defaults/restore` 另帶
  `owner_defaults`（`Hc/gateway.py:624`、`:639`）。
- 形狀 E：只有 `{"error":"<字串>"}`、沒有 `detail`：`unsupported`、`backend_check_failed`、`backend_fixed`。面板不認得這些字串，
  只顯示狀態碼的通用文字（`Hc/gateway.py:558`、`:563`、`:568`、`:580`、`:629`；`Hui/api.js:48-61`）。

PaaS 另帶 `message` 文字，HA 不帶（面板只認代碼，§8.8 #49）。

| 代碼 | HTTP | 什麼時候 | `detail` 欄位 | 管線步驟 | 沒開通時 | PaaS（@69ac425） | 差異 | 新舊 | 負責片／測試 |
|---|---|---|---|---|---|---|---|---|---|
| `profile_id_required` | 400 | 帳號範圍路徑沒帶 `X-MCP-Profile` | `code` | ⑦ | 不出現 | 沒帶當 `default` | §8.8 #31 | 新 | HM-10；`tests/test_profile_admin_api.py`、`tests/test_admin_pipeline_matrix.py` |
| `profile_id_invalid` | 400 | 帶兩個以上，或值不是 `default`、24 位小寫 hex | `code` | ⑦ | 不出現 | 格式錯 404 `{"detail":"Profile not found"}`；帶兩個以上時取第一個值（`Pc/profiles.py:612`），第一個值存在就照常服務 | §8.8 #32、#83 | 新 | HM-10；同上 |
| `profile_not_found` | 404 | 格式對但帳號不存在（含孤兒、隔離目錄、已刪除的帳號；標頭）；全域路徑的 `<id>` 不在索引也不是孤兒；要刪的隔離目錄不存在（暫定，HM-13c） | `code` | ⑦（標頭）／⑪（全域路徑） | 不出現（整條路由 404） | 404 `"Profile not found"`（字串） | 本體多 `code` | 新 | HM-10；`tests/test_profile_admin_api.py`；面板收到就切回預設（HM-11） |
| `profile_label_invalid` | 422 | 名稱違反第 3.6 節規則 | `code` | ⑪ | 不出現 | 422 字串（只檢長度 1～80） | §8.8 #35 | 新 | HM-10、HM-11 |
| `profile_default_immutable` | 422 | 改名或刪除預設帳號 | `code` | ⑪ | 不出現 | 422 字串 | 本體多 `code` | 新 | HM-10 |
| `profile_label_conflict` | 409 | NFKC＋casefold 後和既有名稱或保留名稱相同 | `code` | ⑪ | 不出現 | 409 `"Profile label already exists"` | §8.8 #35（判重較嚴） | 新 | HM-10 |
| `profile_limit_reached` | 409 | 已到 min(5、產品上限)（各產品見第 5 節）；HM-10 定案：FD 上限提不到額外帳號要的量、add-on 只服務預設帳號時（第 5 節，HM-08）`limit` 是 0，什麼都不寫（重啟後它也不會被服務） | `code`、`limit` | ⑪ | 不出現 | 409，同欄位＋`message`（PaaS 沒有 FD 預算） | 同（少 `message`） | 新 | HM-10；`tests/test_profile_admin_api.py` |
| `profile_memory_insufficient` | 409 | 記憶體條件不夠再開一個 | `code`、`limit`、`required_memory_mib`、`memory_limit_mib`（讀得到 cgroup 才有）、`available_memory_mib`（HA 另帶） | ⑪ | 不出現 | 409，`limit`、`memory_limit_mib`、`required_memory_mib`＋`message` | §8.8 #19 | 新 | HM-09、HM-10；`tests/test_profile_admin_api.py`。HM-10 定案：讀得到 cgroup 時照 PaaS（`limit`＝記憶體容得下的額外帳號數、`required_memory_mib`＝256＋(現有額外帳號數＋2)×每子程式 MiB、`memory_limit_mib`，`available_memory_mib` 是 MemAvailable 或讀不到時 `null`）；讀不到 cgroup 時看 MemAvailable 夠不夠再起一個子程式（每子程式 MiB＋256，同 HM-09 起子程式的規則）：`limit`＝現有額外帳號數、`required_memory_mib`＝每子程式 MiB＋256、`available_memory_mib`；MemAvailable 讀不到就照建立並記一行 WARNING（不假設夠） |
| `profile_port_unavailable` | 409 | 18000～18099 找不到空 port（避開 3000、8081、8099、索引與執行中子程式的 port、試綁失敗的；HA 只用這 100 個，PaaS 到 65535，帳號最多 5 個所以沒差） | `code` | ⑪ | 不出現 | 409 `"No child port available"` | 本體多 `code` | 新 | HM-09、HM-10 |
| `profile_product_unsupported` | 409 | 產品不在七產品（OpenDesign、Odoo Manage）卻收到建立；正常不會開通，屬防呆 | `code` | ⑪ | 不出現 | OpenDesign 可開 3 個 | §8.8 #43 | 新 | HM-07、HM-10 |
| `endpoint_global` | 409 | 對額外帳號 `PUT endpoint`（在 If-Match 之後，什麼都不寫；DQ-13） | `code` | ⑪ | 不出現 | 不存 endpoint | §8.8 #27 | 新 | HM-10；`tests/test_profile_admin_api.py` |
| `restore_review_required` | 409 | 還原或休眠後、該帳號還沒「已核對」就 `token/rotate` | `code` | ⑪ | 不出現 | 手冊步驟 9 核對後才發 | §8.8 #58 | 新 | HM-13c；`tests/test_restore_review.py` |
| `profile_index_corrupt` | 503 | 帳號索引不能用（結構壞、被外改，或啟動時 `profiles/` 列不出來）：清單、建立、改名、刪除、額外帳號範圍路徑。預設帳號的帳號範圍路徑照常（bootstrap 帶 `profile_index_state:"corrupt"` 與 `profile_index_etag`）；索引隔離照常可用（HM-10 定案）；全部撤銷、還原紀錄由 HM-13c 定（暫定：照常可用） | `code` | ⑦／⑪ | 不出現 | 整台 503（含管理 API） | §8.8 #25 | 新 | HM-07、HM-10；`tests/test_profile_admin_api.py` |
| `config_conflict` | 409 | If-Match 過期、格式錯或不只一個；拿 A 的 ETag 寫 B；索引 ETag 不符；索引能用時的索引隔離、沒有索引檔可隔離（HM-10）。回應的 `ETag` 標頭是目前的 ETag | `code`（形狀 B：本體只有 `detail`） | ⑪ | 照今天 | 帳號設定有；帳號 CRUD 不收 If-Match | §8.8 #34 | 既有（擴大） | HM-05、HM-10；`tests/test_profile_admin_api.py` |
| `config_revision_required` | 428 | 該帶 If-Match 卻沒帶（含帳號增刪改、核對、索引隔離） | `code` | ⑪ | 照今天 | 帳號 CRUD 沒有 | §8.8 #34 | 既有（擴大） | HM-10 |
| `operation_id_required` | 428 | 建立、刪除、全部撤銷、索引隔離、核對沒帶 Idempotency-Key | `code` | ⑪ | 照今天 | 帳號 CRUD 沒有 | §8.8 #34 | 既有（擴大） | HM-10 |
| `operation_id_invalid` | 400 | Idempotency-Key 不只一個、格式錯或時間在未來 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_id_expired` | 410 | Idempotency-Key 的時間早於 24 小時保留期 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10（帳號增刪的收據沿用） |
| `operation_id_conflict` | 409 | 同一個 Idempotency-Key 用在不同的請求（操作種類或內容不同） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_not_found` | 404 | 查詢的收據不存在，或屬於別的 HA 使用者（`operations/<id>`） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10、HM-11 |
| `operation_journal_full` | 503 | 收據已到上限（128 筆） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_journal_unavailable` | 503 | 收據檔讀不到或寫不了 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10、HM-13b |
| `operation_outcome_unknown` | 409 | 同一個 key 還沒完成就重送；提交後失敗；全部撤銷有帳號失敗（另帶逐帳號 `results`） | `code`；可帶 `operation`、`results` | ⑪／提交 | 照今天 | 同義代碼 | 全部撤銷的逐帳號結果是 HA 加的 | 既有（擴大） | HM-10、HM-13b、HM-13c；`tests/test_revoke_all.py` |
| `operation_restored` | 410 | 還原後重送還原前的操作 id（舊收據封存成 `.restored`） | `code` | ⑪ | 不出現 | 410 `operation_id_expired`（新 journal 的保留期下限設在還原當下） | 代碼名不同；§8.8 #67（封存只留 1 份） | 新 | HM-13b；`tests/test_restore_lock.py` |
| `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` | 422 | 開通的產品改 url 的 scheme、host 或 port，卻沒帶新秘密 | `code` | ⑪ | 不出現（HA 今天任何產品都沒有這條檢查；`Hc/backend_edit.py:1-5` 刻意允許換網址沿用已存的秘密） | 只有 Headscale，422 `{"detail":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}`（字串） | §8.8 #41（DQ-40 ⑨） | 新 | HM-12、HM-26；`tests/test_new_origin_secret.py` |
| `owner_defaults_unavailable` | 409 | 額外帳號的 owner-defaults 操作（HM-10 定案：不管目錄裡有什麼，在 If-Match 之後）；沒有標記的 state | `code`（形狀 C：本體另帶 `error:"owner_defaults_unavailable"`） | ⑪ | 照今天 | 沒有同名代碼（owner-defaults 只在預設帳號） | HA 既有 | 既有 | HM-10；`tests/test_profile_admin_api.py` |
| `config_apply_failed` | 503 | 已存檔，但重啟該帳號子程式失敗 | `code`（形狀 D：`saved:true`＋`detail`＋`configuration`，沒有 `error`） | 提交後 | 照今天 | 沒有同名代碼 | HA 既有 | 既有 | HM-09、HM-10 |
| `core_version_unreviewed` | 403 | HA Core 版本不在白名單（只有角色檢查會帶；identity 的 403 沒有 detail） | `code`、`ha_version` | ⑥／⑩ | 照今天 | 沒有平台門檻 | §8.8 #30 | 既有 | HM-19a（每次升版補審） |
| `unsupported` | 409 | 產品沒提供 `backend/test`、`child/restart` 或 `diagnostics`（`child/restart` 在 If-Match、Idempotency-Key 檢查之後才判斷） | 沒有 `detail`（形狀 E：`{"error":"unsupported"}`） | ⑪ | 照今天 | 沒有同名回應 | HA 既有 | 既有 | HM-10（帳號範圍照今天）；HM-01 凍結 |
| `backend_check_failed` | 503 | `backend/test` 20 秒內沒做完或丟出例外 | 沒有 `detail`（形狀 E：`{"error":"backend_check_failed"}`） | ⑪（執行測試時） | 照今天 | 各產品的連線測試失敗回 200 `{"success":false,"message":<文字>}`（例如 `apps/odoo/odoo_mcp_admin/routers/config.py:143-166`） | HA 既有（不回伺服器文字，同 §8.8 #49） | 既有 | HM-10（測選定帳號）；HM-01 凍結 |
| `backend_fixed` | 409 | 產品不允許從面板改後端（`backend_can_edit` 為否）時 `PUT backend`、`backend/patch`（在 If-Match 檢查之後） | 沒有 `detail`（形狀 E：`{"error":"backend_fixed"}`） | ⑪ | 照今天 | 沒有同名回應 | HA 既有 | 既有 | HM-10；HM-01 凍結 |

沒有代碼的固定回應（同今天；本體是 `{"error":"request denied"}`，另有註明的除外）：

- 403：identity（來源、`X-Remote-User-Id`）、CSRF、cross-site、非管理員、斷線。
- 400：第 ① 步 `X-Ingress-Path` 不只一個或格式錯（`Hc/admin_auth.py:25-32`）；格式驗證不過、帶 query、`raw_path` 含 `%` 或 `\\`、
  不該有 body 卻有。
- 415：要 JSON 的路徑 `Content-Type` 不是 `application/json`（`Hc/gateway.py:280-281`）。
- 503：管理名額滿、拿鎖逾時；state 讀不到時本體是 `{"error":"state unavailable"}`。
- 408、413：讀 body 超過 60 秒、超過 16 MiB。
- 405：路由層回 Starlette 的純文字與 `Allow`（8099 只收 GET、HEAD、PUT、POST）。開通後是分派器的方法表回同樣的位元組（第 3.1 節），
  在 identity 之後（HM-10）。
- 404：未知的 `/api/*` 操作在角色檢查之後回、本體是空的；頁面路徑用 PUT、POST 在第 ① 步之後就回（`Hc/gateway.py:714-716`）。

其中 403（斷線除外）、400、415、405、404 由 HM-01 的管理 API 契約凍結逐位元凍結；503、408、413 與斷線的 403 今天沒有逐位元案例
（名額滿、拿鎖逾時、408、413 連狀態碼都沒有直接的既有測試），HM-10 補了：`tests/test_admin_pipeline_matrix.py` 的
`test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte`，沒開通與開通（經分派器）兩種，位元組相同。

### 4.2 MCP（8081）

| 代碼或形狀 | HTTP | 什麼時候 | 內容 | 沒開通時 | PaaS（@69ac425） | 差異 | 新舊 | 負責片／測試 |
|---|---|---|---|---|---|---|---|---|
| 錯 token：密鑰網址 | 404 | 零命中、撤銷、沒設 | Starlette 預設 404，沒有 `WWW-Authenticate` | 同 | 403 | §8.8 #1 | 既有 | HM-01、HM-08；`tests/test_profile_routing.py` |
| 錯 token：Bearer | 401 | 零命中、撤銷、沒設 | 空本體＋`WWW-Authenticate: Bearer` | 同 | （沒有 Bearer） | §8.8 #1、#2 | 既有 | 同上 |
| `{"error":"state unavailable"}` | 503 | 撞號、預設 state 或索引讀不到、索引外改、全部撤銷失敗的帳號 | 固定本體 | 只有預設 state 讀不到 | 503 | DQ-09 已定（同 PaaS 503） | 既有（擴大） | HM-08 |
| `{"error":"request denied"}` | 400 | MCP 路徑帶 query | 固定本體 | 同 | 原樣轉發 | §8.8 #3 | 既有 | HM-01 |
| `{"error":"request denied"}` | 403 | Bearer 帶 Origin；Headscale 密鑰網址的來源不在清單 | 固定本體 | 同 | Origin 清單 403 `ORIGIN_DENIED` | §8.8 #9、#10 | 既有 | HM-27 |
| JSON-RPC `-32003` | 200／503／429／408 | 准入、位元組預算、讀取閒置、轉送名額逾時、排隊上限、GET 串流上限、待送回覆上限 | 第 2.4 節 | 位元組預算與讀取閒置同開通（HM-31，不受開關管）；其他沒有（uvicorn 503、名額逾時 503） | 200／503／429／408（先讀 body） | §8.8 #15、#16、#96、#101～#105 | 新 | HM-08、HM-14、HM-30、HM-31；`tests/test_profile_quotas.py`、`tests/test_gateway_busy_shapes.py`、`tests/test_request_budget_gateway.py` |
| JSON-RPC `-32602`（結構守門） | 200／413 | POST 的 JSON 巢狀超過 64 層、元素超過 20 萬個、不是 UTF-8 | 第 2.4 節；頭尾認得出 id 才 200 | 同（HM-31，不受開關管） | 同（#155） | §8.8 #106、#107 | 新 | HM-31；`tests/test_request_structure.py` |
| JSON-RPC `-32004` | 502／SSE 事件 | 子程式在處理途中斷線 | 依原因三種文字（第 2.5 節） | 502 `{"error":"request denied"}`、SSE 安靜結束 | 同（#148）；停止了一律說會自動重新啟動 | §8.8 #93（WARNING 節流）、#100（停止了的文字） | 新 | HM-14；`tests/test_gateway_stream_endings.py` |
| JSON-RPC `-32005` | SSE 事件 | 標頭送出後 token 被換掉 | 每個未回應 id 一則（第 2.5 節） | 直接斷線（`ClientDisconnect` 丟給 uvicorn） | 同（JSON 回覆也補：它不帶 `Content-Length`） | §8.8 #92、#97 | 新 | HM-14；`tests/test_gateway_stream_endings.py` |
| `backend_not_configured`（`-32603`） | 200 | 帳號沒填後端、工具需要後端；n8n 額外帳號沒後端時所有工具（含文件工具） | `ToolCallRefused` 形狀 | 照今天 | n8n 額外帳號起文件模式 | §8.8 #28（DQ-22 待定） | 既有（擴大） | HM-25 |
| `backend_unreachable`（`-32603`） | 200 | 最近的健康檢查說後端連不上 | 帶檢查的原因 | 照今天 | 沒有定期監看 | §8.8 #18 | 既有 | HM-09、HM-30 |
| 429 GET 串流 | 429 | GET 串流已達上限 | `-32003`、`id: null`、`Retry-After: 30` | 不設上限 | 同（32 條） | §8.8 #15 | 新 | HM-08 |

上表只列多帳號會新增或改變的回應。**其他既有回應照今天**（開通後每個帳號 app 照舊）。這些回應由 HM-01 的契約凍結與既有測試鎖住；
其中讀 body 時斷線的 403 與其他 `Denied`（交 HM-08）、502 與轉送名額等候逾時的 503（交 HM-14）今天只驗狀態碼或沒有測試，
由負責片補未開通時的逐位元案例（逐項對照見 HM-01 的 provenance 筆記第 4 節；HM-14 補的 502 見 `tests/test_gateway_stream_endings.py` 的 `test_a_childs_wrong_answer_keeps_todays_502`、`test_switched_off_a_broken_connection_keeps_todays_answers`，轉送名額逾時的 503 由 HM-08 的 `tests/test_profile_quotas.py::test_switched_off_a_busy_slot_and_a_client_leaving_answer_as_before` 鎖住）：

- 405＋`Allow: GET, POST, DELETE`：MCP 路徑用其他方法（token 檢查之後；`Hc/gateway.py:1021-1022`）。自答 session 的 GET 是 405＋`Allow: POST, DELETE`。
- 400：GET、DELETE 帶 body；session 標頭不只一個或格式錯；initialize 以外沒帶 `mcp-session-id`（有 id 的 POST 回 `-32000`「Bad Request」）。
- 403：讀 body 時斷線；政策拒絕的 tools/call 沒帶 session；其他政策拒絕（`Denied`）。
- 408（讀 body 超過 60 秒）、413（超過 16 MiB）、415（`Content-Type` 不是 `application/json`）；n8n 另有 4 MiB、10,000 元素、深度 64 的
  上限，超過時回 JSON-RPC 錯誤本體（`Hc/request_limits.py`、`Hc/gateway.py:1034-1055`）。HM-31 起（不受開關管）：n8n 先跑結構守門，深度超過 64
  改回上一表的 `-32602`（認得出 id 就 200），不是 UTF-8 的 body 改回編碼拒收（以前 400＋`-32700`）；整體 60 秒的 408 照舊。
- 政策拒絕、帶 session 的 tools/call：200＋`-32602`（`Unknown tool`、`Invalid params`、`Operation not permitted`；`Hc/policy.py:42-68`）。
- 未知方法：有 id 200＋`-32601`「Method not found」；通知 202。
- 子程式未就緒時閘道自答 initialize、ping、tools/list（§8.8 #68）；就緒後自答 session 回 404（有 id 的 POST 帶 `-32000`「Not Found」）。
- 子程式回 4xx、5xx（401、403 除外）：照原狀態碼，本體換成 `-32000`＋狀態片語（`Hc/gateway.py:153-160`；§8.8 #62 的 429 就是這樣來的）。
- initialize 等不到子程式的回覆：503＋`-32000`「BACKEND_UNAVAILABLE」＋`Retry-After: 5`（`Hc/gateway.py:119-122`）。
- 502 `{"error":"request denied"}`：連不上子程式、子程式逾時（PaaS 504：§8.8 #99）、子程式回 3xx／401／403、回覆格式不對或超過 8 MiB、協定版本不在審過的清單
  （`Hc/gateway.py:1204-1206`、`:1230`、`:1258`、`:1288-1291`、`:1301`）。
- 轉送名額等 1 秒逾時：503 `{"error":"request denied"}`（開通後改成第 2.4 節的 `-32003`；沒開通時也沒有排隊上限、保留名額與排隊中斷線監看）。

## 5. 名額與記憶體數值（DQ-07＋DQ-29 採 (a)；暫定，HM-19c 量測後定案）

| 項目 | 預設帳號（開通後） | 每個額外帳號 | 今天（沒開通） |
|---|---|---|---|
| 讀 body 前准入（同時進行中的請求） | 64 | 32 | listener 64 |
| 請求內容位元組預算：全 add-on（HM-31，不受開關管；大請求收到與轉送兩者較大的位元組，從讀第一個位元組起扣到請求結束；第 2.2 節第 4 點） | 全 add-on 一份：依記憶體推導（下方），至少 16 MiB | （同一份） | 同（今天：無，最壞 64×16 MiB） |
| 請求內容位元組預算：每帳號份額 | min(64 MiB, max(16 MiB, 全 add-on÷2)) | 同左 | 預設帳號同左 |
| 大請求讀取閒置（宣告超過 64 KiB 或沒帶長度）／整體讀取 | 30 秒／60 秒 | 同左 | 同左（今天：沒有閒置逾時／60 秒） |
| JSON 結構上限（整個請求） | 巢狀 64 層、元素 20 萬個、只收 UTF-8 | 同左 | 同左（今天：n8n 只有深度 64） |
| 轉送名額／等候 | 32／1 秒 | 16／1 秒 | 32／1 秒 |
| GET 串流上限 | 24 | 8 | 不設 |
| 排隊上限（每個佇列）／通知保留名額 | 32／4 | 16／4 | 無 |
| 待送回覆位元組（已處理、還沒送完） | 32 MiB | 32 MiB | 無（最壞 64×8 MiB） |
| httpx 子程式連線（自己的 client） | 40 | 24 | 40（全 add-on 共用） |
| 單一請求／單一回應 | 16 MiB／8 MiB | 16 MiB／8 MiB | 16 MiB／8 MiB（n8n 請求 4 MiB） |
| uvicorn `limit_concurrency`（8081 外框） | 64＋32×產品額外帳號上限（各產品見下表） | （全 add-on 一個外框） | 64 |
| 回覆處理 | 一條工作執行緒、依帳號輪流 | 同左 | 事件迴圈內同步 |
| 管理名額（8099） | 16（全 add-on 共用） | （共用） | 16 |
| HA Core 角色查詢並行 | 8（全 add-on 共用） | （共用） | 8 |

- 原則：每個帳號（含預設）讀 body 前受准入（開通的產品）；一個帳號用不到別的帳號的名額或份額。共用的只有兩樣：全 add-on 的請求內容
  位元組預算（HM-31，照 PaaS #155：兩層都放得下才放行，一個帳號最多用到自己的份額，其他帳號仍有全 add-on 預算減去它的份額），和 8081 外框的
  連線數（第 2.4 節最後一點）。HM-08 的拒絕小額度（同時 8 個、合計 512 KiB）HM-31 拿掉（第 2.4 節）。
- 准入＝轉送名額＋排隊上限（預設 64＝32＋32、額外 32＝16＋16），數值不改（DQ-07）。一般名額和它的佇列都滿時准入也滿，這時 ≤64 KiB 的 POST
  仍讀進來，只有通知或回應的照常處理，所以 `notifications/initialized` 照樣經保留名額送到（HM-14 審查 MF-2 (b)，2026-11-16 主對話定案，HM-31；
  第 2.4 節、§8.8 #96）。
- **位元組預算的推導**（HM-31；常數照 PaaS `d7f5849`，暫定，HM-19c 量測後定案）：
  - 全 add-on 預算＝(上限 − 閘道基線 76 MiB − 帳號數×每子程式 MiB − 安全邊際 150 MiB) ÷ 放大倍數 20，至少 16 MiB（單一請求上限：每個份額
    任何時候都放得下一個最大的請求，除非別的帳號已用光全 add-on 預算）、至多 16 GiB；每帳號份額＝min(該帳號的位元組額度 64 MiB, max(16 MiB,
    全 add-on÷2))。啟動時（建立閘道時）讀一次。
  - 上限的來源：讀得到容器的 cgroup 記憶體上限（v2 `memory.max`，或 v1 `memory.limit_in_bytes` 而且不是「無上限」）就用它（PaaS）；HA 的
    add-on 通常沒有（Supervisor 不設記憶體上限，HM-03a 實測確認），改用 `/proc/meminfo` 的 MemAvailable 減保留量 256 MiB（計畫 §5.2 的
    「MemAvailable－保留量」；`profiles.PROFILE_MEMORY_RESERVE_MIB`）；兩者都讀不到：固定 32 MiB（PaaS 的無上限預設值）。
  - 帳號數：沒開通 1（只有預設帳號）；開通 1＋產品的額外帳號容量（PaaS：1＋`current_profile_capacity().limit`）。每子程式 MiB：
    `profiles.CHILD_MEMORY_MIB`（Odoo 100、n8n 300、其他 160）。
  - 例（推算）：MemAvailable 2 GiB 的機器，沒開通的 Odoo：全 add-on (2048−256−76−100−150)÷20≈73 MiB，份額≈37 MiB；開通（6 個帳號）：
    (2048−256−76−600−150)÷20≈48 MiB，份額 24 MiB。MemAvailable 1 GiB：沒開通的 Odoo 約 22 MiB（份額落在下限 16 MiB），開通的落在下限
    16 MiB（一次一個大請求）。
  - 已知限制：MemAvailable 是開機那一刻的值，之後 HA Core 與其他 add-on 會用掉更多；預算不隨它調整。add-on 和整台機器共用記憶體，預算滿時
    閘道最多用到約「MemAvailable−保留量−安全邊際」（推算，放大 20 倍的最壞情況），HM-19c 量測後決定要不要再壓低（例如只取 MemAvailable 的一部分）。
- 全域最壞記憶體（推算，全部帳號同時被打滿）＝Σ每帳號（位元組額度×請求放大＋待送回覆上限）＋工作執行緒一筆的解析放大
  （8 MiB×25）＋子程式。請求放大用 PaaS 沙盒實測的 2.5 時，Odoo 6 個帳號約 6×(64×2.5＋32)＋200＝1,352 MiB（推算）。
- **單一帳號有界，倍數看內容**（HM-08 審查 MF-1、S-1 修正後；HM-31 加結構守門）：
  - 一個帳號的大請求，閘道最多持有它份額那麼多的轉送內容，SSE 串流期間也算（帳上就是轉送的大小）。
  - 另加讀進來的 body 與解析後的物件。字串為主的內容（ASCII、中文、emoji）合計約是份額的 3 倍以內，一個 token 的持有人約
    64×3＋32＝224 MiB，加上共用的一筆放大。PaaS 量到閘道＋子程式合計最壞 17.8 倍（大字串裡一個非 BMP 字元，加上守門上限內最壞的結構），
    所以全 add-on 預算用放大倍數 20 推導（上一點）。
  - 結構（HM-31，PaaS #155 的守門，不受開關管）：巢狀超過 64 層或元素超過 20 萬個的請求在解析前就拒收，所以 HM-08 量到的 24 倍
    （`[{},{},…]` 16 MiB 解析約 390 MiB）不會再出現。守門上限內最壞的結構，閘道自己的解析（`strict_json`）本機量到：4 MiB 的 body 約 26 MiB、
    16 MiB 的約 50 MiB（10 萬個 `{"a":1}`；元素數決定、不隨 body 變大）；1 MiB 的 body 約 20 MiB（19.5 倍，小 body 的倍數最高、絕對值最小；
    HM-31 筆記第 10 節）。
  - 小請求（≤64 KiB）不扣預算：同時大量進行時的總量由准入（開通）或 8081 外框 64（沒開通）限住，最壞約 64×64 KiB 的 body 加上解析
    （PaaS 已知限制 (2)，同樣適用）。
  - HM-19c 在 J6412（可以的話 J1900）用 ASCII、中文、emoji、大量小物件（守門上限內）四種內容量 MemAvailable 與閘道＋子程式的放大倍數；
    超過「MemAvailable－保留量」或放大倍數超過 20，就回功能 PR 改推導（倍數、保留量或份額），不改就不能發版。
- FD：開通後啟動時把 soft `RLIMIT_NOFILE` 提到「需要量＋25%」（最壞約 500，推估），不超過 hard；hard 不夠就不開額外帳號、記一行 WARNING。
  HM-08 定案：需要量＝8081 外框＋8099 的 64＋預設帳號 40＋每個額外帳號 24（照產品上限算）＋角色查詢 8＋每個子程式 4＋基本 64
  （Odoo 544，＋25% 是 680）；讀不到或設不上也算不夠（不假設，HM-03a 實測 HAOS 的值）。不夠時 8081 外框維持 64、只服務預設帳號；
  HM-10：這時建立帳號回 409 `profile_limit_reached`（`limit` 0），什麼都不寫。
- 零命中的請求（錯 token）不佔准入（`tests/test_profile_quotas.py::test_a_wrong_token_takes_no_admission_and_gets_todays_answer`）。
- 未帶 token 的半開連線、閒置的 keep-alive 連線撐滿 8081 外框是既有問題（G2 S7），不在範圍：外框是全 add-on 共用的連線數，滿了之後
  任何人的新連線都拿 uvicorn 純文字 503。每帳號隔離只在請求層成立（HM-08 審查 S-5）；要不要給外框加餘裕、或加第一個請求的讀取逾時，
  留給後續。
- 記憶體檢查：建立帳號、存後端（子程式第一次要起）、手動重啟時讀 `/proc/meminfo` 的 MemAvailable；不足「產品每子程式 MiB＋保留量」時，
  建立回 409 `profile_memory_insufficient`，存後端照存但子程式不起（`blocked`＋`memory_capacity`）。開機時不擋。讀得到 cgroup
  `memory.max` 時照 PaaS 公式。HM-09 定案（建立的 409 是 HM-10）：只檢查額外帳號；面板要起子程式的時候（存後端、存政策等會重起子程式的存檔、
  `child/restart`）在舊子程式停下之後讀；開機（`start_all`）與看門狗重啟不讀；讀不到就照起並記一行 WARNING（不假設夠）。讀得到 cgroup
  `memory.max` 時改由 ProfileManager 開啟時的 PaaS 公式決定（超出的帳號 `disabled_reason=memory_capacity`），不再讀 MemAvailable。

**各產品的額外帳號上限與每子程式記憶體**（暫定照 PaaS；HM-07 定常數，HM-19c 在目標硬體量測後定案，改了要同時改本表）：

| 產品 | 額外帳號上限 | 每子程式 MiB | 8081 外框（64＋32×上限） | PaaS（@69ac425） |
|---|---|---|---|---|
| Odoo | 5 | 100 | 224 | 5／100 MiB（`apps/odoo/odoo_mcp_admin/main.py:47-48`） |
| n8n | 2 | 300 | 128 | 2／300 MiB（`apps/n8n/n8n_mcp_admin/main.py:35-36`） |
| Hermes | 3 | 160（HM-24 在 HAOS 至少 60 分鐘負載量測後定） | 160 | 預設 3／160 MiB |
| EMQX、LiteLLM、Nextcloud、Headscale | 3 | 160 | 160 | 預設 3／160 MiB（`Pc/launch_policy.py:152-154`） |
| OpenDesign、Odoo Manage | 0（不開放，DQ-28） | — | 64（不會開通：開關只能列支援額外帳號的產品，`tests/test_upgrade_zero_rewrite.py` 擋；萬一列進去，分派器會掛上，但不開任何額外帳號） | OpenDesign 預設 3／160 MiB |

- 保留量 256 MiB（照 PaaS `PROFILE_MEMORY_RESERVE_MIB`，`Pc/profiles.py:47`）；上限另受總上限 5 限制（`Pc/profiles.py:45`）。
- 讀得到 cgroup `memory.max` 時照 PaaS 公式：額外帳號上限＝min(產品上限, max(1, ⌊(memory.max－256)÷每子程式 MiB⌋)－1)；
  `required_memory_mib`＝256＋(額外帳號數＋1)×每子程式 MiB（`Pc/profiles.py:170-174`、`:309-314`）。
- 這張表的數字也用在 FD 預算（上一段）與 T-02（第 6 個額外帳號 409）；計畫的暫定上限也是 Odoo 5、n8n 2、其他 3（計畫 §8.4 DQ-03 的說明）。

## 6. 回覆處理公平排程的門檻（HM-30；暫定：HM-30 實作、HM-19c 在目標硬體量測後定案；要放寬須使用者同意）

只在開通的產品生效；沒開通照今天在事件迴圈內處理。下面的數字是本片先訂的、還沒量過。

**單元測試（可控注入，不靠 runner 速度）**：每筆回覆的處理時間用注入的工作 d 模擬（測試用 d＝0.25 秒，
對照 EPYC 7713 上 8 MiB 回覆 0.28～0.47 秒）。**注入的工作要像真的回覆處理一樣佔住 GIL**（例如一次對大字串 `json.loads`）：
`sleep` 會放掉 GIL、純 Python 迴圈每 5 ms 讓出一次，放在工作執行緒都量不到真正的停頓。另加一個用真實 8 MiB 回覆
（`strict_json`→`redact_secrets`→`filter_list`→`json.dumps`）量迴圈停頓的案例。A 並行 16 個 8 MiB 與 16 個 2 MiB 回覆時：

| 指標 | 門檻 |
|---|---|
| 事件迴圈單次停頓（迴圈延遲探針） | ≤50 ms |
| B、C 的健康檢查逾時次數（時限照今天 8＋5 秒） | 0 |
| B 的 tools/call 額外延遲 p99 | ≤2d＋0.2 秒（依帳號輪流：B 最多等 A 正在處理的一筆，再加自己的一筆） |
| 輸出位元組 | 和今天相同（golden） |
| 每帳號同時在處理的回覆 | ≤1 筆 |

注意：C 層的 `json.loads`（掃描一個大字串時）、`json.dumps`、`re.sub` 一次呼叫期間不放 GIL，一條工作執行緒處理一筆 8 MiB 回覆時，
事件迴圈的單次停頓可能超過 50 ms。HM-30 用真實回覆量到做不到時，回報使用者再定（例如分段處理或改用子程序），不自行放寬。

**慢讀用戶端**：A 的用戶端不讀回應時，管理程序 RSS 增量 ≤ A 的待送回覆上限 32 MiB＋一筆處理放大 200 MiB＋餘裕 64 MiB＝296 MiB；
A 超過待送上限後，新的 tools/call 立刻回 200＋`-32003`。

**HAOS 量測（HM-19c；J6412，可以的話 J1900）**：同一個情境下 B 的 tools/call p95 增量 ≤1 秒、健康檢查 0 次逾時；
過不了就調額度或回功能 PR，不能發版。健康檢查開通後連續兩次失敗才判 unreachable（今天一次就判）。

## 7. 子程式、port 與生命週期（給測試用的數值）

| 項目 | 規則 |
|---|---|
| port | 預設帳號 3000；額外帳號 18000 起找第一個空號，避開 3000、8081、8099、索引內 port、執行中子程式的 port；試綁四種位址確認沒人佔（HM-09：`profiles.allocate_port(occupied=profiles.port_occupied)`、`ProfileManager.free_port()`；試綁照 PaaS `port_occupied`：127.0.0.1、0.0.0.0、::1、::（v6only），都帶 SO_REUSEADDR）。HM-09 審查（S-6）：IPv6 試綁被平台擋（EACCES、EPERM：AppArmor、seccomp）時跳過那個位址，每個位址與 errno 每個程序記一行 WARNING（PaaS 當成被佔；第 9 節 #89）；IPv4 任何失敗仍當被佔 |
| spawn 前檢查 | port 衝突或被佔就不 spawn，`status=blocked`＋`blocked_reason`。HM-09 定案的四類：add-on 自己的 listener port（8081、8099）、別的帳號執行中的子程式在用 → `child_port_conflict`；試綁失敗 → `child_port_in_use`；這三種照看門狗退避重試（同 PaaS 每次拒絕都重試）。索引內重複或等於 3000 的帳號開啟時就 `disabled_reason=port_conflict`，起子程式時 `blocked`＋`child_port_conflict`、不重試、也不試綁，索引變了（HM-10 寫入後 `adopt_index`＋`reevaluate()`）才重評。被擋的子程式不 spawn，健康監看也不送任何東西到那個 port |
| 看門狗（DQ-20 採 (b)） | 開通的產品所有帳號（含預設）：退避 2、5、15、30、60、120、300 秒，不限次數，連續跑 120 秒歸零；OOM 殺掉也照退避。沒開通維持今天「同一次啟動最多 4 次、不歸零、之後 failed」。HM-09：spawn 失敗（`OSError`）與 spawn 前檢查的拒絕也算一次失敗、照退避重試（PaaS 的 spawn 失敗會停在 failed；HA 的子程式指令固定在映像裡，spawn 失敗多半是暫時的，例如 fork 時記憶體不夠）；退避期間 `status=backoff`，被擋時維持 `blocked` |
| 錯開啟動 | 預設帳號先起；額外帳號依序起、同時最多 2 個，前一個健康檢查通過或 30 秒逾時才起下一個。HM-09 定案：預設帳號在 listener 之前起（同今天，`launch()`）；額外帳號等預設帳號第一次健康檢查通過或 30 秒後才開始，依索引順序、同時最多 2 個在起，一個名額在「子程式回了健康檢查」「不在起了（被擋、沒設定、spec 失敗、子程式結束）」或 30 秒時讓出（壞的標記、不擋其他）。等的時候每 0.5 秒檢查一次（子程式還沒聽 port 時只是連線被拒，後端看不到）。HM-09 審查（S-12）：某個帳號的啟動或就緒等待丟例外時（目前找不到會丟的路），記一行、讓出名額，其他帳號照起；預設帳號的等待也一樣。HM-10：每個帳號起子程式時拿它自己的 `mutation_lock`（第 3.2 節），面板正在存檔或重啟它時先等做完 |
| 啟動順序 | legacy 遷移（只對預設）→ 還原偵測、守門、休眠處理 → 預設帳號 → 錯開起額外帳號（壞的標記、不擋其他） |
| 關閉 | 所有 `Supervisor.stop()` 並行，在 HA 停止上限 30 秒內收完（HM-09：`ProfileManager.stop_all()`，關閉時先停額外帳號的監看再並行停子程式；6 個都要 SIGKILL 的子程式約一個寬限期 3 秒收完） |
| 健康監看 | 每帳號一個、自己的 httpx client、起點錯開；認證被拒 15→30→60→120→300 秒退避；開通後連兩次失敗才判 unreachable（DQ-25 已定：2026-11-15 11:2x 使用者採用建議；負責片 HM-09、HM-30）。HM-09 定案：起點＝預設帳號開機就查（同今天）、第 k 個額外帳號在自己的子程式起好後 15×(1＋k÷(產品額外帳號上限＋1)) 秒（Odoo：17.5、20、22.5…秒），之後每 15 秒；「認證被拒」＝健康探測原因開頭是各子程式固定的認證失敗文字（Odoo、Hermes `BACKEND_AUTH_REJECTED`；Headscale `HEADSCALE_INVALID_CREDENTIAL`；Nextcloud `BACKEND_HTTP_ERROR status=401`，以及登入失敗後的節流 `status=429`；EMQX、LiteLLM 的 401 文字），子程式回了其他答案就歸零，存檔與面板重啟（新的憑證）也歸零並在 15 秒內再查；「連兩次失敗」＝同一個子程式世代連續兩次「子程式有回、後端不通」才判 unreachable（才拒絕 tools/call），第一次維持前一次的判定（之前通就 reachable，剛起還沒判定就 unknown）；子程式沒回的檢查照今天記成未就緒（本來就不拒絕 tools/call），不算一次也不打斷連續；面板的 `backend/test` 照實回這一次的結果。子程式不在 running 時不送任何東西（port 可能是別的程式的，T-15）。沒開通照今天（每 15 秒、一次就判、不退避） |
| 監看失敗 | 額外帳號只標記 `failed`；預設帳號維持今天「任何元件停止就退出」（DQ-21 已定：2026-11-15 11:2x 使用者採用建議）。HM-09 定案：額外帳號的健康監看停止時，記一行 WARNING、停掉它的子程式並標成 `failed`（監看停了，那個帳號的可用性判斷就不再更新，不能照舊轉送）；其他帳號與 add-on 照常；面板存檔或 `child/restart` 讓子程式再起時，監看也一起恢復 |
| 資源 | 額外帳號子程式 exec 前寫 `/proc/self/oom_score_adj`＝500（絕對值）與 `setpriority(+5)`。HM-09 定案：由一個全新的單執行緒直譯器（`python -I -S -c`，同 PaaS `child_identity` 的包裝）在 fork 之後、exec 真正的指令之前寫，經管線回報結果；真正的指令拿到原本的 argv、環境（還原 PEP 538 加的 `LC_CTYPE`）、工作目錄與訊號處置。寫不進去（平台不准）就照起、`resource_state` 記下、每帳號每 60 秒一行 WARNING，不假設寫成功；沒有直譯器可跑包裝器（`sys.executable` 是空的）時也一樣照直接起、記一行（HM-09 審查 S-12）。預設帳號的子程式照今天直接 spawn |
| 記憶體 | 見第 5 節（HM-09 定案的部分） |
| 被擋的狀態 | HM-09 定案：`disabled_reason` 有值的帳號不起（開機、看門狗、面板重啟都不起）：`status=blocked`，`blocked_reason` 是 `port_conflict`→`child_port_conflict`、`memory_capacity`→`memory_capacity`、`profile_limit`→`null`（沒有對應的原因碼，看清單的 `disabled_reason`）。開通後 `child/restart` 的 202 回應多 `blocked_reason`（沒被擋是 `null`）；沒開通照今天 |
| 子程式 bearer（HM-06，不受開關管） | 剛好一個 `Authorization`、`hmac.compare_digest` 比對 `Bearer <WOOW_MCP_CHILD_TOKEN>`；不符 401（不寫細節）；環境變數缺、空或不符 `[A-Za-z0-9_-]{43}` 就拒絕啟動 |
| 後端 loopback（HM-20，受開關管） | 開通的產品的子程式環境多一個 `WOOW_MCP_DENY_LOOPBACK=1`，預設帳號與每個額外帳號的子程式都有（沒開通就沒有這個變數，spec 逐位元同今天）；子程式連設定的後端時，網址的字面位址或名稱解析出的任何一個位址是 127.0.0.0/8 或 ::1，整組拒絕、不連線（Python 子程式 `BACKEND_DESTINATION_DENIED`；Headscale 的子程式本來就一律拒 loopback、不看這個變數，回 `HEADSCALE_DESTINATION_DENIED`；n8n 另擋 0.0.0.0 與 IPv4-mapped，API 與官方 MCP 端點都擋）；變數的值不是 `1` 就拒絕啟動。n8n 的 webhook、chat、form 網址不受這條管（§8.8 #90） |
| log 事件 | 子程式啟動、結束（結束碼）、退避（下次秒數）、`failed`、`blocked`（原因碼）、監看認證退避、撞號、孤兒、隔離、還原守門逐帳號動作、休眠撤銷、缺哪些連線鍵（只列鍵名）；格式 `[profile=<id 前 8 碼> port=<p> pid=<n>]`；每帳號每情況 60 秒一行（`suppressed=N`）。HM-09 寫的（開通的產品才寫，logger `mcp_admin_core.lifecycle`，一律 WARNING，因為 add-on log 只顯示 WARNING 以上）：`MCP child [profile=… port=… pid=…]: started`／`exited with code N`／`next start in N s (attempt n)`／`failed after n starts; …`／`not started (<原因碼>): <固定說明>`／`child resources not applied (…)`／`could not be started (<例外類別>)`／`not started: no connection is saved yet (<欄位名>); …`／`the backend refused the credentials; next health check in N s`／`its health monitor stopped; …`／`MemAvailable cannot be read; …`／`its staggered start failed (<例外類別>); the other profiles start anyway`（HM-09 審查 S-12）；`child resources not applied (…: no interpreter for the wrapper); …` 也是同一行的一種。另外 logger `mcp_admin_core.profiles` 的 `multi-profile: the IPv6 test bind on <位址> is refused (<errno 名稱>); the spawn check skips that address`（HM-09 審查 S-6；每個位址與 errno 每個程序一行，不帶帳號）。撞號、孤兒、讀不到的帳號是 HM-08 寫的（logger `mcp_admin_core.profile_runtime`、`profile_router`）；隔離、還原守門逐帳號動作、休眠撤銷是 HM-13b |

## 8. 資料（摘要）

- 布局：預設帳號在 `/data/mcp/`（`state.json` 一個鍵都不加）；索引 `/data/mcp/profiles.json`；額外帳號 `/data/mcp/profiles/<24 hex>/`；
  還原用 `.instance-sentinel`、`.instance-record`、`.restore-detected`、`.revoke-all-pending`、`restore-record.json`（都不含秘密）。
  n8n 額外帳號的 `nodes.db` 在 `/tmp/woow-n8n-mcp/profiles/<id>/`（DQ-04 待定）。
- 索引格式（和 PaaS `profile_index` 同形狀）：

  ```json
  {"version": 1, "profile_index": {"0123456789abcdef01234567": {"label": "會計", "port": 18000}}}
  ```

  0600、擁有者 10001、單一連結、≤64 KiB、`O_NOFOLLOW`、`strict_json`（拒絕重複鍵）；頂層鍵剛好 `version`、`profile_index`；
  每筆鍵剛好 `label`、`port`；id 24 位小寫 hex；port 是 int 不是 bool、1024～65535；≤5 筆；物件順序＝建立順序。
- 索引裡的 port 照 PaaS 逐字一致（HM-07 審查 MF-1，2026-11-15 定案）：
  - 1024～65535 都不算結構錯（PaaS `_index_entries`）。
  - port 重複，或等於預設帳號子程式的 3000：只停持有它的額外帳號（`disabled_reason=port_conflict`；PaaS `_port_collisions`）。
  - port 是 add-on 自己的 listener（8081、8099）：索引階段不檢查（PaaS `_port_collisions` 也不列），起子程式前才擋：
    `status=blocked`、`blocked_reason=child_port_conflict`（HM-09；PaaS `_port_refusal`）。
  - 和 PaaS 相同，所以第 9 節沒有這一列。配 port 照樣避開 3000、8081、8099（第 7 節）。
- 額外帳號 store 只開既有（`existing_only`）：缺 state 不補建、檢查擁有者 uid；建立一次寫入最終初值（新 token、新 child_token、
  連線全空、`endpoint=None`、政策照 DQ-02 複製預設帳號當下的值、`n8n_session` 不複製、建立不記 history）。
- 項目預算：5 個帳號加隔離與封存約 50 項、最深 4 層，在 entrypoint 還原修復上限（512 項、8 層）內；超過 400 項時面板警示。

## 9. 刻意差異表（§8.8）

類型：**既有**＝HA 今天就不同、不是多帳號造成；**部署**＝平台差異；**加嚴**＝HA 比 PaaS 嚴（DQ-40 的 10 項已一次確認；
其餘加嚴的列和它們一起列入給 PaaS 的回補建議，HM-29）；**待決**＝看還沒定的決策。第 1～43 列是計畫 §8.8 原表（2026-11-14 的決策已套用）；
第 44～79 列是 HM-00 對照腳本把 FEATURE-MATRIX「HA 平台差異」欄與 G6 §5「HA 期望值與差異」欄逐列對照後補的列；第 80～86 列是
審查後把 FEATURE-MATRIX「HA 平台差異」欄是「—」的 44 列人工逐列看過後補的列；第 87、88 列是 HM-08 獨立審查（S-6）補的列，
#15、#16 的附註也是；#14 的附註是 HM-09 的實作補的，第 89 列是 HM-09 獨立審查（S-6）補的列。逐列的來源與結論見
`deviation-trace.md`（第 87～89 列與三個附註出自 HM-08、HM-09 的實作，不是 FEATURE-MATRIX 的列）。
第 90 列是 HM-20 補的列（DQ-10 子題 2026-11-15 定案；FM-84 的對齊作法欄；`deviation-trace.md` 沒有這一列）。
第 91～95 列出自 HM-14 的實作，第 96～99 列是 HM-14 獨立審查（MF-2、S-1、S-7、S-5）補的列，第 100 列是 HM-14 rebase 到 HM-09
之後補的列（都不是 FEATURE-MATRIX 的列；`deviation-trace.md` 由 repo 外的產生器重產，沒有這幾列）。
第 101～107 列出自 HM-31（對齊 PaaS #155），#15、#16、#96 也由 HM-31 改寫（都不是 FEATURE-MATRIX 的列；`deviation-trace.md` 由 repo 外的產生器重產，沒有這幾列）。

| # | 項目 | PaaS（@69ac425） | HA | 理由 | 類型 |
|---|---|---|---|---|---|
| 1 | 錯 token | 403 | 密鑰網址 404、Bearer 401 | HA 既有契約（Hc/gateway.py:932-947） | 既有 |
| 2 | Bearer 接法 | 沒有 | 有，依 token 選帳號 | HA 主推接法（DQ-01 採 (a)） | 既有 |
| 3 | MCP 路徑帶 query、`/mcp/` | 轉發、等同 `/mcp` | 400、404 | HA 較嚴 | 既有 |
| 4 | 轉送的用戶端標頭 | 大部分（含 `x-n8n-*`） | 只有 3 個 session 標頭；回程只轉 4 個固定標頭（不含 Location） | n8n-mcp 會依 `x-n8n-*` 換後端（G5-13） | 既有 |
| 5 | 工具呼叫逾時 | 110 秒回 `-32001`（Pc/proxy.py:44-46） | 330 秒（Hermes chat 300 秒） | HA 既有（R07 X-20；DQ-24 待定） | 既有 |
| 6 | legacy SSE | 轉送 `/sse`、`/messages/` | 不支援 | HA 子程式只開 Streamable HTTP（DQ-23 待定，建議不支援） | 既有 |
| 7 | readiness | `/healthz` 恆 200 | `/health/ready` 200／503，只代表預設 | FM-67；DQ-19 已定 | 既有 |
| 8 | 新帳號 token 歷史 | 記一筆 `auto_issue`（R03 §1.4） | 不記 | HA history 只收 rotate／revoke（Hc/products.py:264-268）；DQ-02 採 (a) | 既有 |
| 9 | Headscale Origin 清單 | 只放自己的管理網址（claude.ai 403；R07 X-17） | 只放 `https://claude.ai` | 使用者對 HA Headscale 的決定（R01 H-08） | 既有 |
| 10 | Bearer 帶 Origin | （沒有 Bearer） | 一律 403；DQ-11 第二問（S14 實測後）再定要不要精確放行 `https://claude.ai` | 瀏覽器不在 Bearer 契約 | 既有／待決 |
| 11 | 管理身分 | 密碼＋JWT | Ingress＋HA 角色，每請求查 | 平台不同 | 部署 |
| 12 | 管理管線 | 中介層先驗登入 | 看狀態前先驗角色、提交前再驗一次（第 3.2 節） | I10；HA 角色每請求查 | 部署 |
| 13 | listener 身分檢查 | 轉發前必過 | 讀得到才做，讀不到降級（HM-15，條件式） | HA AppArmor 未確認；不讓整台停擺 | 部署 |
| 14 | 子程式重啟 | 2→300 秒、不限次數、120 秒歸零；spawn 失敗（指令找不到等）就停住，等手動重啟 | 開通的產品相同（DQ-20 採 (b)），spawn 失敗也照退避重試（HM-09）；沒開通維持 4 次後 failed | 沒開通維持今天；HA 的子程式指令固定在映像裡，spawn 失敗多半是暫時的（fork 時記憶體不夠等） | 部署 |
| 15 | 名額 | 每帳號連線 64、串流 32、等 10 秒、排隊 32＋保留 8；共用池；請求內容位元組預算全域＋每帳號份額（#155） | 讀 body 前准入（64／32）、轉送 32／16 等 1 秒、串流 24／8、排隊 32／16＋保留 4、待送回覆額度；沒有共用池。請求內容位元組預算照 PaaS（HM-31）：全 add-on 一份＋每帳號份額（差異見 #101～#104）。附註（HM-08 審查 S-5、S-6；HM-31 改）：全 add-on 共用的只有兩樣：(1) 請求內容位元組預算（PaaS 同；HM-08 的拒絕小額度 HM-31 拿掉）；(2) 8081 外框的連線數（閒置 keep-alive、沒帶 token 的連線也算），滿了任何人都拿 uvicorn 純文字 503（既有，G2 S7）。每帳號隔離在請求層 | HA 沒有 cgroup、硬體小（G3-24）；DQ-07 採 (a) | 部署 |
| 16 | 讀 body 前拒絕的回應碼（准入） | 先讀 body，帶 id 一律 200＋`-32003` | 准入滿：≤64 KiB 讀出 id 回 200＋`-32003`；更大的不讀、503。位元組預算放不下的照 PaaS（HM-31：讀完丟掉、從頭尾找 id，200 或 503），不在這一列。附註（HM-08 審查 S-6）：batch 算沒有 id。HA 閘道平常就不收 batch（`policy.authorize` 的 `single JSON-RPC request required` → 403；PaaS 會轉送），過載時 HA 回 503＋`id: null`，PaaS 每個 id 一則 200 | 讀 body 前准入防單一帳號吃光 listener（C3-MF-2） | 部署 |
| 17 | 回覆處理 | 事件迴圈內 | 一條工作執行緒、依帳號輪流 | HA 硬體慢、單一迴圈（第 6 節） | 部署 |
| 18 | 健康檢查 | 沒有定期後端監看（FM-68） | 每帳號監看、連兩次失敗才判壞、認證退避 | HA 既有監看；Odoo 以來源 IP 冷卻 | 部署 |
| 19 | 容量檢查 | cgroup 公式（建立時）；沒有 FD 預算 | MemAvailable（建立、存後端、起子程式時）；讀得到 cgroup 才用公式；錯誤多帶 `available_memory_mib`。另有 FD 預算（#87）：開機時 FD 上限提不到額外帳號要的量，就只服務預設帳號（HM-08），這時建立回 409 `profile_limit_reached`、`limit` 0、什麼都不寫（HM-10） | HA 沒有 cgroup；add-on 容器的 FD 上限由容器決定（第 5 節；HM-03a 實測） | 部署 |
| 20 | 還原 | 手冊＋restore_guard（k8s Job） | entrypoint＋sentinel 偵測、開機守門、讀不到就隔離 | Supervisor 沒有 hook | 部署 |
| 21 | 還原時預設帳號 | 一律撤銷 | DQ-03 採 (b) A2：只有磁碟上有帳號資料的還原才撤銷預設帳號 | 白名單落後＋還原換回舊版 | 部署 |
| 22 | 還原後 token 歷史 | 清空（R04 S-15） | 保留，加一筆 revoke | 不改 schema | 部署 |
| 23 | 孤兒 | 讓還原停機（Pc/restore_guard.py:443-446） | 只隔離、不擋開機 | 不讓含孤兒的備份永遠起不來（G1:435） | 加嚴（建議回補） |
| 24 | 休眠帳號 | 沒有（沒有產品開關） | 沒開通的版本撤銷休眠帳號 token | 開關＝發版（第 1.2 節） | 部署 |
| 25 | 索引壞 | 整台 503（含管理 API；R03 §1.6） | 8081 503、面板照開、「隔離帳號索引」 | HA 沒有手動修復途徑（DQ-12 已定） | 部署 |
| 26 | 手改索引 | 重啟才生效（R03 §4.12） | 503 到重啟 | 外改＝繞過鎖 | 加嚴 |
| 27 | endpoint | 不存，用瀏覽器 origin | 存在預設 state、全域；額外帳號的 bootstrap 顯示它，`PUT endpoint` 409 `endpoint_global` | Ingress 和 MCP 不同源（FM-12）；DQ-13 已定（2026-11-15 17:4x） | 部署 |
| 28 | 沒填連線的子程式 | 5 個產品照起；n8n 額外帳號起文件模式（R06 PR-n8n-01） | 都不起；n8n 預設照起；n8n 額外帳號沒後端時所有工具回 `backend_not_configured`（DQ-22 待定） | 省記憶體（FM-45） | 部署 |
| 29 | 日誌 | 每帳號 Logs 5,000 筆／2 MiB、SSE；保留 2 個剛刪除帳號（Pc/routers/logs.py:59-65） | 每帳號子程式輸出 200 筆／128 KiB 快照；管理程序紀錄在 add-on log（帶 id 前 8 碼）；刪除就釋放 | HA 既有診斷模型（FM-65） | 部署 |
| 30 | 面板 403（Core 未審） | 沒有平台門檻 | 整個面板 403，任何帳號都撤銷不了，只能停 add-on | HA 角色驗證契約（FM-70） | 部署 |
| 31 | 管理 API 沒帶帳號 | 當 default | 開通後 400 `profile_id_required` | fail closed（I12；DQ-40 ①） | 加嚴 |
| 32 | `X-MCP-Profile` 格式錯 | 404（Pc/profiles.py:611-614） | 400 `profile_id_invalid`（在角色檢查後） | 分清「格式錯」與「不存在」 | 加嚴 |
| 33 | 管理回應帶帳號回聲 | 沒有 | 有，面板比對 | fail closed（DQ-40 ②） | 加嚴 |
| 34 | 帳號 CRUD 寫入保護 | 不收 If-Match、不走收據；刪除 204；只刪索引裡的帳號（其他 404），撤銷 token 後直接刪目錄（Pc/profiles.py:428-460）；本體格式錯是 pydantic 的 422（Pc/routers/profiles.py 的 `ProfileInput`） | 全部 If-Match；建立、刪除、全部撤銷、索引隔離要 Idempotency-Key；刪除 200＋收據。HM-10：刪除也收孤兒與讀不到的帳號；刪目錄前先抹後端欄位（`connection`、`backend_url`、`backend_key`、`mcp_access_token`）；建立、改名的本體不是剛好 `{"label": <字串>}` 時固定 400、沒有細節 | HA 既有規則（Hc/gateway.py:456-484；DQ-40 ③）；孤兒不自動刪、列出可刪，先撤銷並抹憑證再刪（DQ-14）；格式錯照 HA 管理 API 既有的固定 400（第 4.1 節） | 加嚴 |
| 35 | 帳號名稱 | 接受控制、bidi、零寬字元 | 拒絕；NFKC 判重 | 防管理員誤認（DQ-16；DQ-40 ④） | 加嚴 |
| 36 | 帳號選擇保存 | sessionStorage | 只放記憶體 | 保留 HA 儲存不變式（DQ-18；DQ-40 ⑤） | 加嚴 |
| 37 | 子程式 bearer | 只有 n8n 驗 | 7 支 Python 子程式也驗、驗格式（第 7 節）。註：n8n 維持現狀（n8n-mcp 驗 `AUTH_TOKEN`＝同一個 child_token）：只看值是不是 `Bearer ` 開頭、比對前去掉前後空白，重複的 `Authorization` 只看第一個，所以另外收下三種寫法：`Bearer` 後兩個空白、兩個標頭都是自己的、第一個是自己的＋第二個是別帳號的。三種都要先有自己的 child token，沒有越權 | port 錯置時不跨帳號執行（DQ-40 ⑥）。n8n 不另外擋那三種（審查 MF-1 選 (a)，2026-11-15）：閘道只轉送自己的 child bearer、只送一個標頭（HM-01 黃金回歸鎖住，用戶端塞不進第二個）；能直連子程式 port 的只有 add-on 容器內同 uid 的程序，在 DQ-37 接受的信任邊界內 | 加嚴 |
| 38 | 回覆遮罩 | 子程式只知道自己帳號的憑證（FM-76） | 本帳號秘密＋所有帳號 token／child_token | 一個 add-on 持有多個帳號的 token（DQ-40 ⑧） | 加嚴 |
| 39 | 後端網址 loopback | 只有 n8n、EMQX 存檔過核心 SSRF（宣告 `url_connection_keys`，Pc/connection_apply.py:69-87）：部署端預設 strict，存檔時解析 DNS，擋 loopback、私網、metadata、帶帳密，400 `detail.code=ssrf_blocked`（另帶 `field`、`reason`、`message`）；n8n 子程式的上游客戶端連線時再驗一次（同一模式），其他產品子程式不再檢查。#152（main `671d2e7` 合併，2026-11-15）起 Nextcloud 的 `base_url` 也照這套在存檔時檢查，「測試連線」與健康探測也在管理程序連線前先檢查（被擋的一個請求都不送，訊息只有原因）；Nextcloud 子程式本身連線時仍不檢查（PaaS 自己寫明） | 開通後全部產品（含 n8n）存檔與執行期都拒。存檔（HM-20）：不解析 DNS；擋 `localhost`、`localhost.localdomain`、`*.localhost`（大小寫、結尾點）與 127.0.0.0/8、::1 的各種寫法（十進位、八進位、十六進位、省略段、結尾點、IPv4-mapped），數字寫法落在不允許位址也擋（`0` 是 0.0.0.0）；只檢查這次改到的網址；回 400 `{"error":"request denied"}`，同既有的存檔檢查（第 4.1 節）。n8n 開通後另外套上既有的整套存檔檢查（同其他產品；計畫 §8.7「n8n 也納入存檔檢查」、FM-77）：除了 loopback，也擋 `.`／`..` 路徑段、解碼後的 `%`、反斜線、`?`、`#`、`@`、metadata 名稱、非 ASCII 主機（要改填 `xn--`）、zone id、port 0 與不允許位址的 IP 字面。位址那部分和 n8n 執行期的 `allowedAddress`（H:apps/n8n/backend_policy.cjs）是同一組，帶帳密、非空的 `?`／`#` 執行期本來就拒，所以今天連得上的位址開通後照樣連得上；真正新擋的是網址的寫法（例如 `.`／`..` 路徑段、反斜線、空的 `?`／`#`、空帳密的 `@`、非 ASCII 主機），這些今天經 WHATWG 正規化後照連，開通後要改填正規的寫法（非 ASCII 主機改填 `xn--`）。和 PaaS n8n 的差異：PaaS 擋私網、不看路徑寫法；HA 放私網、擋路徑寫法。執行期：子程式（`WOOW_MCP_DENY_LOOPBACK=1`，第 7 節）對字面與解析後的每個位址都拒，名稱指到 127.0.0.1 也擋。區網照放；沒開通完全照今天。Nextcloud（對照 PaaS #152）：`url` 存檔一直走既有的存檔檢查（metadata 名稱、不允許位址的 IP 字面、路徑寫法，HM-20 前就有），開通後加 loopback；「測試連線」（`backend/test`）測已存的設定、經子程式連線，子程式連線前對每個解析出的位址檢查（metadata 與 link-local 位址一律擋；開通後含 loopback），被擋的一個請求都不送。範圍只有 loopback：add-on 自己的 bridge 位址與主機名不在規則裡（`threat-model.md` 第 3 節） | 縱深防禦（DQ-10；DQ-40 ⑦）：HA bridge 網路下 loopback 只連到 add-on 自己（8081、8099、子程式 port）；HA 後端多在區網，所以不擋私網；存檔不查 DNS，名稱留到連線時解析後擋 | 加嚴 |
| 40 | 換身分換 token | 只有 Odoo（#131） | Odoo；加 Nextcloud url／username、Hermes gateway_url／dashboard_url／dashboard_username | 使用者原則「每條網址永久綁一個後端身分」（R01:85；DQ-40 ⑩） | 加嚴 |
| 41 | 新來源要重填秘密 | 只有 Headscale（FM-89） | 開通後全部產品改 url 的 scheme／host／port 沒帶新秘密 → 422 | 防把存好的密碼送到新伺服器（DQ-40 ⑨） | 加嚴 |
| 42 | 密鑰路徑 Origin | 清單＋report-only（記 would_deny）、反射 CORS | 清單（預設 `https://claude.ai`）＋report-only 記 would_deny、不加 CORS | 不放寬（FM-74；DQ-11 採 (a)） | 加嚴 |
| 43 | 不開放的產品 | OpenDesign 可開 3 個（R06 §3.8） | 409 `profile_product_unsupported`；不顯示新增按鈕 | 不在七產品：OpenDesign 商店停用、Odoo Manage 已下架（DQ-28 採不開放） | 部署 |
| 44 | 帳號索引的位置與建立時點 | 預設帳號 `config.json` 內的 `profile_index`；下次寫入就多一個空索引 | 獨立檔 `/data/mcp/profiles.json`，第一次建立額外帳號才產生；預設 `state.json` 一個鍵都不加 | HA state 鍵集合精確比對，舊映像讀不了新鍵（Hc/products.py:529-538） | 部署 |
| 45 | 部署層設定入口 | 名額、排隊、Origin 等用 chart 或環境變數調 | 全部是程式常數；add-on options 維持 `{}`；改數值要回功能 PR、發版 | Store 第 1 類比對與 validate.py 的精確 manifest | 部署 |
| 46 | 手改帳號 state | 讀一次就快取，手改要重啟管理程序 | 每請求重讀，手改立即生效、壞檔立即 fail closed（索引另見 #26） | HA 既有每請求重讀與租約 | 既有 |
| 47 | n8n `nodes.db` 位置 | 每帳號在設定目錄（持久、進備份，約 67 MiB／帳號） | 預設不變（`/tmp/woow-n8n-mcp/nodes.db`）；額外帳號 `/tmp/woow-n8n-mcp/profiles/<id>/`（不進備份） | 不加大備份；DQ-04 待定（HM-25） | 待決 |
| 48 | 管理請求的網址規則 | 沒有這條限制 | 帶 query、`raw_path` 含 `%` 或 `\\` 一律 400（Hc/gateway.py:706-711） | HA 既有 | 既有 |
| 49 | 錯誤的顯示 | 面板顯示伺服器回的 `detail`／`message` 文字 | 面板只認固定代碼，文字由面板對照（Hui/api.js:48-61）；伺服器不回文字 | HA 既有 | 既有 |
| 50 | 帳號範圍的選擇方式 | `X-MCP-Profile` 標頭 | 標頭；UC-10 證實 Ingress 不轉時改路徑 `{base}/api/p/<id>/…`，PATCH／DELETE 改 POST（第 3.7 節） | 看 HM-03a 的 UC-10 結果 | 待決 |
| 51 | 帳號清單欄位 | 清單只有 `{"profiles":[…]}`；列有 `id`、`label`、`port`、`is_default`、`disabled_reason`（3 種）、`required_memory_mib` | 另加 `status`、`blocked_reason`；`disabled_reason` 多 `profile_unavailable`、`quarantined`、`dormant`；清單另回 `orphans`（`[{"id"}…]`：索引沒有的帳號目錄；HM-10） | 沒有 operator 監看，補 PaaS 只有預設帳號有健康的缺口（K-02）；孤兒不自動刪、面板列出可刪（DQ-14） | 部署 |
| 52 | 子程式預設 port | 多數 8000（n8n 3000） | 3000；額外帳號同 PaaS 從 18000 起 | HA 既有；容器網路私有，不影響外部 | 既有 |
| 53 | 啟動與關閉順序 | 先起預設、再逐一 activate＋start；關閉先 stop_all 再停預設 | 預設先起，額外帳號錯開（同時最多 2 個，等健康或 30 秒）；關閉全部並行、30 秒內收完 | HA 停止上限 30 秒；J1900 低速；冷備份每次停再起 | 部署 |
| 54 | 存政策重啟子程式 | Nextcloud 收緊工具不重啟 | 收緊也重啟（只重啟該帳號） | HA 子程式環境由 state 組（既有），不影響隔離 | 既有 |
| 55 | 切換帳號時的進行中請求 | React 版整頁重掛，不檢查進行中的請求 | `task()` 期間選單停用；帳號世代＋1，晚到的回應丟掉；切換就藏 token | HA 既有 `task()` 鎖 | 加嚴 |
| 56 | 輪替後的新 token | 前端丟掉回應裡的新 token | 輪替後立刻顯示 60 秒（同既有單帳號行為） | HA 既有；DQ-31 面板細節待定 | 既有 |
| 57 | 安全標頭 | XFO DENY、`frame-ancestors 'none'` | `frame-ancestors 'self'`（Ingress iframe），不加 XFO DENY | Ingress iframe（FM-71） | 部署 |
| 58 | 還原前盤點與核對 | 手冊步驟 1 事前盤點（不含憑證）、步驟 9 三段核對後才在步驟 10 發 token | 看不到還原前狀態：事後核對卡，逐帳號「已核對」才可重發；事前匯出帳號清單選做 | Supervisor 還原先刪資料、沒有 hook | 部署 |
| 59 | 換身分換 token 的歷史動作名 | `backend_identity_change` | 沿用 `rotate` | history 只收 rotate／revoke，不改 schema（FM-09） | 部署 |
| 60 | Odoo 讀取並行 | 讀取工具預設 8 條工作緒 | 1 條 | 不同時改並行度與多帳號（DQ-30 待定，建議維持 1） | 待決 |
| 61 | Odoo reviewed methods 的預設來源 | 沒存過時讀容器 env（全帳號共用） | 只從各帳號 state 組，不繼承容器 env | HA 既有（隔離更好） | 既有 |
| 62 | n8n session 名額與滿了的回應 | 每帳號 20、逾時 900 秒；上游 429 原文轉回；`AUTH_RATE_LIMIT_MAX` 1000 | 每帳號 20、逾時 600 秒；閘道回 429「Too Many Requests」；上游預設限流 | HA 既有；DQ-22 細節待定 | 待決 |
| 63 | Hermes Dashboard | 管理端有 Dashboard 代理（cookie 快取 key 帶帳號，刪帳號清除） | 沒有管理端代理；子程式內 cookie 每個子程式一份 | HA 沒有 Dashboard 代理頁 | 既有 |
| 64 | LiteLLM 寫入權限 | `LITELLM_MCP_READONLY` 一個開關 | 逐支工具授權 | HA 既有政策模型 | 既有 |
| 65 | EMQX 子程式端政策 | 子程式每次呼叫讀自己帳號的設定再擋一次 | 只在閘道擋；子程式只收 READONLY 與 DISABLED_TOOLS | 閘道政策＋每帳號子程式＋bearer（DQ-27 待定，建議不做） | 待決 |
| 66 | 還原的舊 schema 預設 state | restore guard 設 `RESTORE_POLICY_HOLD`，保留還原回來的舊政策 | 照 2026-10-27 決定做全開遷移，留復原紀錄與面板通知；額外帳號一出生就是 schema 4 | HA owner-defaults 規則；只在還原拉不到舊映像時發生（UC-24） | 既有 |
| 67 | 還原收據封存 | 封存 bundle、可壓縮，重複還原保留每一份；還原前的舊操作 id 回 410 `operation_id_expired` | 每帳號只留最近 1 份 `.restored`；舊操作 id 回 410 `operation_restored` | entrypoint 修復項目上限（512 項、8 層）；代碼分開，看得出是還原造成（FM-07） | 部署 |
| 68 | 子程式未就緒時的回應 | 503「MCP child is not ready」，或只有一支 setup_status 工具的佔位伺服器 | 閘道自答 initialize、ping、tools/list（內附清單），tools/call 回 JSON-RPC 錯誤；就緒後自答 session 404、要求重連 | HA 既有（0.2.2） | 既有 |
| 69 | 還原涵蓋範圍 | 手冊涵蓋任何備份 | 只涵蓋各產品第一個含 HM-13 的版本以後做的備份；更早的備份還原後升到最新版並按「全部撤銷」 | 還原會換回備份當時的映像，舊 entrypoint 不建標記 | 部署 |
| 70 | 平台建立路徑 | workspace API 建服務 | 商店安裝 add-on → 面板加帳號（併入 T-20） | 平台不同 | 部署 |
| 71 | 回退 | helm rollback，升降版實測 0 差異 | 只有三條路：還原升級前備份、發版號更大的修正版、使用者停 add-on（計畫 §7.4） | Supervisor 不能裝回舊版、Store 不收降版（UC-18 已確認） | 部署 |
| 72 | 升級驗證 | helm 升級與回退實測 | Store 升版比對 hook（`seed`／`verify`，只讀、與版本無關）＋HAOS 驗收；`upgrade-notes.yaml` 條目 | Store 規則 | 部署 |
| 73 | 發佈與版號 | main CI 映像 → 沙盒 → 釘版 PR → tag → /approve → CD | 功能 PR 不改版號；版號 PR 合併＝上架 WOOW App Store；repo 外 builder 建映像（要批准）→ 容器驗收 → 推 GHCR（燒版號）；`addons/<x>/` 底下的文件只在升版 PR；發版鎖 | Store 同步規則；版號 PR 合併＝發佈 | 部署 |
| 74 | 產品開關 | 沒有（靠釘版隔離） | `MULTI_PROFILE_PRODUCTS` 逐產品，開關＝發版；不受開關管的切片隨任何產品出貨（第 1.2 節） | 每個映像整包複製核心 | 部署 |
| 75 | CI | Gitea Actions | GitHub Actions `checks`（root、0 skip、Python 3.13.16、上限 60 分鐘（DQ-43，2026-11-15 定案，PR #100））；拆 job 要保留 `checks` 名稱 | Store 必要檢查名稱（DQ-43：先調上限，拆 job 等真的太慢再議） | 部署 |
| 76 | 面板測試 | 只有 `node --test` 進 CI，瀏覽器測試手動跑 | node 與 Playwright 都進 CI | HA 既有 | 加嚴（建議回補） |
| 77 | 帳本 | 沒有 | `docs/provenance/runtime-patches.json`、tool-surface 摘要；新模組全部列管（`ledger-tracking.md`） | HA 既有供應鏈規則 | 既有 |
| 78 | 秘密掃描與測試資料 | 沒有 builder 全歷史掃描 | builder 用 gitleaks 掃原始碼與全歷史、零容忍；`claude-delivery` 禁止 force push → 測試資料正規化、每片預檢 | 歷史改不掉 | 部署 |
| 79 | 上線後監看 | watch_fleet 唯讀監看全部服務 | 看不到客戶主機；只能對自營 HAOS 做唯讀檢查（範圍 HM-29 定） | 客戶自己更新 | 部署 |
| 80 | 手動指定 token | `PUT /api/tokens`（`set_token`）；撞號 409 `token_in_use`，不回顯值、不說是哪個帳號（Pc/routers/tokens.py:141-142；Pc/profiles.py:488-503） | 沒有這個 API：token 只由伺服器隨機產生，只能輪替與撤銷（Hc/gateway.py:582-606）；撞號只會來自還原或複製，回 503（第 2.3 節） | FM-31「不新增」；將來要加就照 PaaS 回 409，並同時擋目前與歷史 token | 既有 |
| 81 | 請求內容超過上限 | 最多再讀 128 MiB 丟掉才回錯誤，讓經反向代理的用戶端看得到錯誤、不是 RST（Pc/request_limits.py:16） | 一超過就 413（n8n 是 JSON-RPC 錯誤本體）、不再讀後面的內容（Hc/gateway.py:270-271；Hc/request_limits.py:51-70） | FM-52 延後：只在前面有 Cloudflare Tunnel 或反向代理時有感（HM-14 選做；HM-14 沒做，仍延後） | 既有 |
| 82 | 全部撤銷 | 沒有面板或 API；還原時照手冊撤銷全部（docs/paas-config-restore-runbook.md） | `POST {base}/api/profiles/revoke-all`（含預設帳號）＋`.revoke-all-pending`；逐帳號結果，寫入失敗的帳號 503、重啟時守門重做（第 2.3、3.1 節） | HA 沒有 shell 跑手冊；事故止血第一步、回退後再升級都要靠它（threat-model.md 第 4 節；§8.8 #69）；FM-120 | 加嚴（建議回補） |
| 83 | 管理請求帶兩個以上 `X-MCP-Profile` | 取第一個值（`request.headers.get`，Pc/profiles.py:612）；第一個值存在就照常服務 | 開通後 400 `profile_id_invalid`（在角色檢查後；第 3.3 節） | 一個請求只能對一個帳號，哪個值生效不該看中介層實作；fail closed（同 #31、#32；DQ-40 ①；DQ-17 已定） | 加嚴 |
| 84 | 帳號在別處被刪時的面板 | 等清單下次重抓才回 default，期間帳號範圍請求 404（依程式推論，R05 §6） | 任何帳號範圍請求回 `profile_not_found` 就立刻重抓清單、切回預設帳號並提示；被刪帳號的待確認收據明說並清掉（第 3.4 節） | 不讓下一個操作落到別的帳號、不留無法確認的收據（I12；FM-59） | 加嚴 |
| 85 | 用戶端範例的名稱 | 只給網址與 `claude mcp add --transport http my-<app>-mcp "<網址>"`；名稱不含帳號，同產品兩帳號照抄會撞名 | 今天是 `mcpServers` JSON、名稱固定 `woow`、帶 Bearer（Hui/contracts.js:319-321；§8.8 #2）；開通後名稱帶帳號 id 前 8 碼（例如 `woow-<產品>-<id 前 8 碼>`，暫定） | 同產品兩個帳號照抄不撞名；建議 PaaS 一起改（FM-63） | 待決（DQ-31） |
| 86 | 帳號範圍的管理操作與本體 | FastAPI 路由（`/api/settings/<section>`、`/api/tokens`、`/api/tools` 等），各自的本體與 ETag（Pc/config/store.py:276-289） | HA 既有管理契約的操作：`bootstrap`、`backend`、`policy`、`token/rotate`…（docs/management-capabilities-v1.md）、ETag `"c1-<64 hex>"`；開通後只加 `X-MCP-Profile`、回聲與帳號範圍（第 3.1、3.4 節）。帳號增刪改查的路徑、方法與欄位照 PaaS（FM-18、FM-19、FM-22） | HA 既有的單帳號契約，不因多帳號改寫；面板與 P9 kit 都照它 | 既有 |
| 87 | FD 上限不夠 | 沒有這條降級（程式不讀也不調 `RLIMIT_NOFILE`） | 開通後啟動時讀 soft／hard `RLIMIT_NOFILE`；讀不到、hard 不夠或設不上：只服務預設帳號、8081 外框維持 64、記一行 WARNING（第 5 節） | HA 不能假設 HAOS 容器的上限（待 HM-03a 實測）；不夠時寧可不開額外帳號 | 部署 |
| 88 | 額外帳號目錄被換掉 | 只在開啟當下比對 fd 與路徑是同一個目錄（`Pc/profiles.py:212-218`），之後快取 store、不再比對 | 開啟時記下目錄的 (st_dev, st_ino)，之後不同就不路由，它的 token 變成未知 token（第 2.2 節第 3 點；HM-07 審查 S-08） | 防誤拷與誤改；同 uid 下不是安全邊界（DQ-37） | 加嚴 |
| 89 | 試綁被平台擋 | IPv6 試綁除了 EADDRNOTAVAIL、EAFNOSUPPORT 之外的失敗都當成 port 被佔（`child_identity.port_occupied`） | IPv6 試綁遇到 EACCES、EPERM 時跳過那個位址，每個位址與 errno 每個程序記一行 WARNING；IPv4 任何失敗仍當被佔（第 7 節） | 平台事實不假設（HAOS 的 AppArmor、seccomp 可能擋 IPv6 bind，待 HM-03a 實測）；照 PaaS 的話，開通後預設帳號的子程式會因此永遠起不來。子程式只綁 127.0.0.1，別的程式的雙棧 socket 仍會讓 IPv4 萬用位址的試綁失敗，跳過不會漏掉佔用者 | 部署 |
| 90 | n8n webhook、chat、form 網址的 SSRF 模式 | 子程式讀部署端的 `WEBHOOK_SECURITY_MODE`，預設 strict（擋 loopback、私網；和存檔檢查同一個模式，Pc/util/ssrf.py） | 固定 `permissive`（只擋雲端 metadata 與隧道內嵌的位址，可以指到區網與 loopback；H:apps/n8n/n8n_adapter.py）。開通後只有設定的 n8n 本身（API 與官方 MCP 端點）拒 loopback（#39），webhook 照舊 | 負責人 2026-10-15 的決定（`n8n_test_workflow` 要打 HA 網路上的 n8n）；2026-11-15 使用者定維持不動（DQ-10 子題），多帳號時要不要收緊交 HM-25 前的獨立安全審查 | 既有（HM-25 前再評估） |
| 91 | 保留名額載的東西 | 通知與對伺服器請求的回應都轉送（`notifications/cancelled`、roots、progress…），走每帳號另外 8 條保留名額 | 每帳號 4 條、有自己的佇列；判斷函式照 PaaS 原樣（`gateway.carries_no_request`）。HA 的政策只轉送 `notifications/initialized`：其他通知閘道自己回 202、不轉送；對伺服器請求的回應、batch、沒有 id 的工具呼叫在任何名額之前 403；重複鍵 400（strict JSON），所以實際走保留名額的只有 `notifications/initialized` | HA 從不把子程式對用戶端的請求（elicitation、sampling、roots）轉給用戶端，沒有要回的回應；HA 既有政策（0.1.13、0.1.14） | 既有 |
| 92 | token 換掉時標頭已送出的 JSON 回覆 | 回覆不帶 `Content-Length`（chunked），一個位元組都還沒送時改送 `-32005` 本體 | 帶 `Content-Length`（HM-01 黃金回歸逐位元），標頭已送出就不能改：閘道返回、伺服器關掉連線（uvicorn 記一行，沒有 traceback）；SSE 照 PaaS 補 `-32005` | HM-01 的逐位元契約；token 換掉之後子程式的位元組一律不送 | 既有 |
| 93 | `-32004` 的 log | 每次一行（方法、token 之後的路徑、錯誤類別、原因） | 每帳號每種原因 60 秒一行（`suppressed=N`）：帳號 id 前 8 碼、HTTP 方法、錯誤類別、原因；不寫路徑（密鑰網址的路徑就是 token） | 子程式當掉時同時在跑的請求一起斷；HA 的 WARNING 規則（第 2.4 節） | 部署 |
| 94 | initialize 換代的回應 | 503 `{"detail":"MCP child is not ready; reconnect after checking its status"}`；送出前登記在途派送，生命週期轉換最多等數秒（drain） | 503 `BACKEND_UNAVAILABLE`＋`Retry-After: 5`（HA 既有「initialize 等不到回覆」的回應）、沒有 session id、不 DELETE；沒有 drain：重啟不等閘道，標頭已在送的 session 收不回來（下一個請求拿新子程式的 404，用戶端重新 initialize） | HA 既有回應形狀；Supervisor 不經過閘道、沒有派送登記的介面 | 既有 |
| 95 | 標頭卡在背壓時換 token | initialize 在最外層 fence 最多等 0.25 秒送 403；其他回應最多 2 秒 | 一律最多 2 秒送 401／404（只有一層 `LeasedResponse`）；送不出去就放棄、不丟例外 | HA 的 MCP app 沒有 BaseHTTPMiddleware，不需要另一層 fence | 部署 |
| 96 | 保留名額與准入 | 讀 body 前沒有准入；一般名額的佇列滿時，通知照樣走保留名額送到（`P:docs/mcp-gateway-limits.md:39-40`）；小請求的讀取沒有時限 | 讀 body 前的准入＝轉送名額＋排隊上限（64＝32＋32、32＝16＋16）。准入滿時仍讀 ≤64 KiB 的 POST（2 秒內、同時讀幾個不設上限），只有通知或回應的照常交帳號 app，`notifications/initialized` 經保留名額送到（HM-31）；剩下的差異：准入滿時的讀取只到 64 KiB、2 秒，更大或更慢的拿 503（PaaS 讀完每個 body） | HM-14 審查 MF-2 (b)：2026-11-16 07:5x 主對話定案照 PaaS 的語意（DQ-07 的數值不改）；准入仍在讀 body 前（C3-MF-2），超出准入的讀取要有界 | 部署 |
| 97 | 一個請求只回一則（SSE 的 `-32005`） | `_Interruption` 只看子程式的回覆、而且只在產生器續跑時記「已送到」：回覆在 token 換掉那一刻被收下，或閘道補的 `-32004` 已送出後 token 才換掉，同一個 id 會再補一則 `-32005`（`Pc/proxy.py:487-516`、`:1192-1194`） | 伺服器收下的那個請求的回答（子程式的回覆或閘道的 `-32004` 事件）之後不再補 `-32005`（第 2.5 節） | JSON-RPC 一個請求只回一則；MCP Python 與 TS SDK 對多出來的那則只記錯誤 | 加嚴（建議回補） |
| 98 | 排隊中換 token | 排隊包在 token 租約裡（`Pc/proxy.py:986`），token 一換就取消、回 403 | 排隊不在租約裡：拿到名額或等滿 1 秒後重驗才拒（Bearer 401、密鑰網址 404），子程式收不到；最多多佔 1 秒的排隊位置（第 2.4 節） | 把 `take_slot` 放進 `lease.run` 時，「拿到名額」與「token 換掉」同一刻會漏掉名額，要另寫歸還與測試；結果相同（一定被拒、子程式收不到），HM-14 審查 S-7 列為可選 | 部署 |
| 99 | 子程式逾時（回應標頭前） | 504 `{"detail":"MCP server timed out"}`（`Pc/proxy.py:1078-1079`）；工具呼叫的逾時另見 #5 | 502 `{"error":"request denied"}`，開通前後都一樣（第 2.5 節、第 4.2 節「其他既有回應」） | HA 既有回應形狀（HM-01 黃金回歸） | 既有 |
| 100 | 子程式停止後 `-32004` 的文字 | 停止了一律說「會自動重新啟動」（`CHILD_INTERRUPTED_MESSAGE`，`Pc/proxy.py:57-62`；註解寫當掉、被 kill、重啟、被擋下都算） | 看停止之後那一刻的 `Supervisor.status`：`backoff`、`starting` 或新世代的 `running` 才說會自動重新啟動；`blocked`、`failed`、`stopped`、`unconfigured` 說「目前沒有在重新啟動」（`gateway.CHILD_HALTED_TEXT`；第 2.5 節） | HM-09 的被擋下（停用的帳號、記憶體不夠）與 `failed`（監看停止，DQ-21）不會自己再起；說會再起，用戶端會以為稍後重試就好 | 加嚴（建議回補） |
| 101 | 位元組預算的每帳號份額 | 全域的一半（至少 16 MiB），沒有上限 | min(該帳號的位元組額度 64 MiB, max(16 MiB, 全 add-on÷2))：開關關的預設帳號也一樣 | DQ-07 的 64 MiB 保留成份額的上限（不改使用者定的數值）；HA 的 add-on 和整台機器共用記憶體，一個 token 的持有人最壞只用到 64 MiB×放大 20 倍 | 加嚴 |
| 102 | 位元組預算扣的大小 | 收到的位元組（轉送原樣的 body） | 收到的與轉送給子程式的兩者較大的（閘道重新序列化：中文 2 倍、emoji 3 倍、數字最多約 4.5 倍）；轉送的大小放不下就不送、回 `-32003` | HA 閘道轉送前重新序列化（既有）；只算收到的會少算轉送的那份（HM-08 審查 S-1） | 加嚴 |
| 103 | 位元組預算的推導來源 | cgroup 記憶體上限；沒有上限固定 32 MiB | cgroup 上限；沒有就用 MemAvailable 減保留量 256 MiB（啟動時讀一次）；兩者都讀不到固定 32 MiB；帳號數沒開通算 1 | HA 的 add-on 沒有 Pod 記憶體上限（計畫 §5.2 的記憶體檢查）；HM-19c 量測後定案 | 部署 |
| 104 | 位元組預算與逾時的設定入口 | `MCP_GATEWAY_MAX_BUFFERED_BYTES`、`…_PER_PROFILE`、`MCP_GATEWAY_BODY_IDLE_SECONDS`、`…_TOTAL_SECONDS` 環境變數，不合法記 WARNING | 程式常數，不讀環境變數 | 同 #45（add-on options 維持 `{}`，改數值要回功能 PR） | 部署 |
| 105 | 大請求的整體讀取上限 | 已登記的大請求 300 秒（`MCP_GATEWAY_BODY_TOTAL_SECONDS`），逾時 408＋`-32003`；小請求沒有上限 | 每個請求 60 秒（`BODY_SECONDS`，既有），逾時照今天 408 `{"error":"request denied"}`；閒置 30 秒照 PaaS（408＋`-32003`＋`Connection: close`） | HA 既有的整體上限比 PaaS 嚴，涓流上傳最多佔住預算 60 秒（PaaS 300 秒）；回應形狀照今天，不改單帳號既有的 408 | 既有 |
| 106 | Headscale 的結構上限 | Headscale 自己的 `McpRequestLimits`：1 MiB、8,192 個工具參數元素、深度 32；整個請求 20 萬個元素 | 和其他產品一樣：16 MiB、深度 64、20 萬個元素（`gateway.STRUCTURE_LIMITS`） | HA 的 Headscale 今天就沒有自己的請求上限（既有差異，不在 #155） | 既有 |
| 107 | 不是 JSON 的 body | 照舊轉給子程式（結構守門不判違規） | 照今天 400 `{"error":"request denied"}`（strict JSON，在任何名額之前） | HA 既有的 strict JSON（重複鍵、NaN、單獨代理字元都 400） | 既有 |

## 10. 變更紀錄

| 版本 | 日期 | 片 | 內容 |
|---|---|---|---|
| v1 草案 | 2026-11-14 | HM-00 | 依計畫 §5、§6、§8.8 起草；套用 2026-11-14 的 §13.1 決策；差異表由 43 列補到 79 列 |
| v1 草案（審查修正） | 2026-11-14 | HM-00 | 依獨立審查修正：錯誤代碼表對齊 bb48449 與 PaaS pin（既有回應的五種本體形狀；補 `unsupported`、`backend_check_failed`、`backend_fixed` 三列與 415、第 ① 步的 400；`core_version_unreviewed` 在 ⑥／⑩；重複 `X-MCP-Profile` 的 PaaS 行為）；差異表補第 80～86 列；第 4.2 節補既有回應範圍；第 5 節加各產品上限；待定題目標示；隔離目錄刪除路由與讀 body 途中額度用完的回應（暫定）；第 6 節門檻寫法 |
| v1 草案（HM-07） | 2026-11-15 | HM-07 | 第 8 節索引 port 規則照 PaaS 逐字一致（審查 MF-1 定案）：拿掉「不是 3000／8081／8099」；重複與 3000 只停相關帳號；listener port 交 HM-09 的 spawn 前檢查（`child_port_conflict`）；第 9 節不加列。DQ-09、DQ-12、DQ-19 改標已定（`decisions.md`） |
| v1 草案（HM-06） | 2026-11-15 | HM-06 | 第 9 節 #37 加註：n8n 維持 n8n-mcp 現狀，另外收下三種都要先有自己 child token 的寫法（審查 MF-1 選 (a)，主對話 2026-11-15 08:0x 定案）；同步 `acceptance-matrix.md` T-23 與 `threat-model.md` I4。第 7 節「子程式 bearer」列不變（DQ-08 的 HM-06 部分照它，`decisions.md`） |
| v1 草案（文件同步） | 2026-11-15 | HM-00 補正 | DQ-05、DQ-15、DQ-16、DQ-17 的「細節待定」改標已定（依 DQ-40 (a)，照計畫 §9、§5.3 第 7 點、§8.5、§5.3；`decisions.md`）：第 3.1 節 `backend` 列、第 3.3 節、第 3.5 節、第 3.6 節的名稱規則、第 9 節 #83。規則內容不變；DQ-10、DQ-18 在本檔沒有標待定的地方 |
| v1 草案（HM-08） | 2026-11-15 | HM-08 | 第 2.2 節第 3、4 點：簽章欄位、額外帳號目錄比對、位元組額度怎麼扣（宣告長度先扣、讀到的超過再扣、送出回應標頭就還）定案；第 2.3 節：索引不能用時 `/health/ready` 回 not ready；第 2.4 節：讀途中額度用完的做法定案、轉送名額逾時的 `-32003` 在開通的產品由 HM-08 先做、「解析得出 id」的定義（batch 算沒有）；第 5 節：FD 需要量的算法與不夠時的降級 |
| v1 草案（HM-08 審查） | 2026-11-15 | HM-08 | 依獨立安全審查修正：第 2.2 節第 4 點位元組額度改成扣到請求結束、並扣轉送給子程式的大小（MF-1、S-1；原本「送出回應標頭就還、那時請求內容已不在記憶體」與事實不符）；第 2.4 節加「轉送大小放不下」一列、第 2 列補「拒絕小額度正被占滿」、最後一點寫明 8081 外框是全 add-on 共用的連線數（S-5）；第 5 節位元組額度的定義、「單一帳號有界」改寫成看內容的倍數（字串約 3 倍、大量小物件約 24 倍；元素數上限待定）、零命中與外框兩點、OpenDesign／Odoo Manage 列改成「不會開通」（S-7）；第 9 節 #15、#16 加附註、補第 87、88 列（S-6） |
| v1 草案（HM-09） | 2026-11-15 | HM-09 | 第 7 節：DQ-21、DQ-25 改標已定（2026-11-15 11:2x 使用者採用建議；`decisions.md`），並寫明 HM-09 定案的做法：spawn 前檢查四類與重試、看門狗把 spawn 失敗與拒絕也算一次、錯開啟動的名額規則、並行停、監看起點與認證被拒的判斷、「連兩次失敗」的算法、監看失敗時停該帳號子程式、資源包裝與降級、被擋的狀態與 `child/restart` 的 `blocked_reason`、log 事件的文字與層級；第 5 節：記憶體檢查的時機與讀不到時的做法 |
| v1 草案（HM-09 審查） | 2026-11-15 | HM-09 | 依獨立安全審查（修正後通過）：第 7 節 port 列加 IPv6 試綁被平台擋時跳過並記一行（S-6）、錯開啟動列加「某個帳號的啟動丟例外時記一行、其他照起」（S-12）、資源列加「沒有直譯器可跑包裝器時照起並記一行」（S-12）、log 事件列補這三種文字；第 9 節加第 89 列（S-6）並在說明寫明 #14 的附註出自 HM-09（spawn 失敗也重試，審查 S-1 要使用者看過） |
| v1 草案（HM-20） | 2026-11-15 | HM-20 | 後端網址拒絕 loopback 照實作寫明（DQ-10；DQ-40 ⑦）：第 3.1 節 `backend` 列加存檔的 400；第 7 節加「後端 loopback」列（`WOOW_MCP_DENY_LOOPBACK=1`、整組拒絕、值不是 1 就不啟動）；第 9 節 #39 的 PaaS 欄與 HA 欄寫明兩邊的範圍、存檔時查不查 DNS、回應本體與區網；補 #90（n8n webhook 模式維持 permissive，DQ-10 子題 2026-11-15 使用者定，HM-25 前再評估）。安全審查後（S-1、S-4、S-8）：#39 補「n8n 開通後套上整套既有存檔檢查」與和 PaaS n8n 的差異、範圍只有 loopback（bridge 位址不在規則裡）；第 3.1 節同步、改說「是 loopback」；第 7 節補「額外帳號的子程式也帶變數」與 Headscale 的代碼。rebase 到 HM-09 之後（2026-11-16）：HM-08 補了 #87、#88、HM-09 補了 #89，本片的列改成 #90（原稿 #87），第 7 節與本列的引用同步；#39 的 PaaS 欄照 #152 的實際合併（`671d2e7`）改寫，HA 欄補 Nextcloud 的存檔與測試連線對照。沒開通時的行為不變 |
| v1 草案（HM-14） | 2026-11-15 | HM-14 | 第 1.2 節：不受開關管多一項（子程式 initialize 錯誤遮本帳號憑證；理由、改了什麼、HM-01 凍結不用改）；第 2.4 節：排隊上限每個佇列各自計數、排隊中斷線不送（含同一刻拿到名額）、保留名額的判斷照 PaaS `_carries_no_request` 且 HA 實際只有 `notifications/initialized` 會用到、SDK 層級逾時與 `terminate_on_close=True` 看不到斷線的已知限制、`-32003` 文字定稿；第 2.5 節：哪些錯誤算子程式中途斷線、`-32004` 的世代判斷與 0.25 秒、`-32005` 與標頭卡在背壓時的乾淨拒絕、一次送完的 JSON 標頭已出去時的處理、結尾最多 2 秒、initialize 世代；第 4.2 節：`-32004`、`-32005` 兩列與「其他既有回應」的 502 測試；第 9 節補第 91～95 列、#81 註明 HM-14 沒做 FM-52 |
| v1 草案（HM-14 審查） | 2026-11-16 | HM-14 | 依獨立安全審查補寫（程式改 S-1、S-4 與一個型別註記，見 HM-14 筆記第 15 節）：第 2.4 節加三點（保留名額只在准入還有空位時有用，MF-2，待使用者決定；GET 串流整段佔住一般名額與准入，UC-31；排隊中換 token 最多多佔 1 秒，S-7）；第 2.5 節：閘道補的 `-32004` 事件也算那個請求的回答、之後不再補 `-32005`（S-1），uvicorn 記一行的情況改成「兩個例外」（S-5）；第 4.2 節：`-32003`、`-32005` 兩列補差異列號，502 的既有回應補「逾時」；第 5 節加准入＝轉送＋排隊一點；第 9 節補第 96～99 列 |
| v1 草案（HM-14 rebase） | 2026-11-16 | HM-14 | rebase 到 `claude-delivery`（HM-09 合併後，`c523474`）：HM-14 的差異列往後移一列（HM-09 已用第 89 列），引用一起改；第 2.5 節 `-32004` 停止了的文字依停止之後的狀態分兩種（HM-09 的 `blocked`、`failed` 等不會自動重新啟動），第 4.2 節 `-32004` 列跟著改，第 9 節補第 100 列；第 2.4、5 節與 #96 寫明 MF-2 (b) 的定案（主對話 2026-11-16：不改 DQ-07 的數值，交 HM-31 改分派器讀小請求；#96 的類型維持「待決」） |
| v1 草案（HM-14 rebase 到 HM-20 之後） | 2026-11-16 | HM-14 | rebase 到 `claude-delivery`（HM-20 #102 合併後，`269f5a5`）：HM-14 的差異列再往後移一列，成為第 91～100 列（HM-20 用了第 90 列），第 2.4、2.5、4.2、5 節與第 10 節的引用一起改；第 9 節說明段把 HM-14 的列另寫一行（HM-09、HM-20 的說明照原文）。規則內容不變 |
| v1 草案（HM-10） | 2026-11-15 | HM-10 | 第 3 節：DQ-13、DQ-14 改標已定（2026-11-15 17:4x 使用者採用建議，`decisions.md` 由 PR #100 記）；UC-10 照使用者 15:3x 的決定用標頭、不做路徑備案（第 3.7 節）；HM-10 定案的做法：分派器與抽出的共用管線、⑤ 的內容、⑪ 的順序、鎖、405 的位元組、`profiles/` 底下未知路徑、清單的 `orphans` 與 `status` 對應、`profile_unavailable`、建立的重送、刪除與索引隔離的回應與步驟、壞索引的 ETag 與 `profile_index_etag`、索引 ETag 的算法、收據的 `subject`、提交後失敗的處理、回聲的範圍與標頭、`profiles_supported`、額外帳號的 endpoint 與 owner-defaults、帳號 ETag 的 domain、建立後在新帳號自己的鎖裡起子程式、開機與重評起子程式也拿該帳號的鎖（HM-09 審查 S-12 第 2 點）、刪目錄從驗過的 `profiles/` 往下走、`profiles/` 列不出來又沒有索引檔時的隔離；第 4.1 節：`profile_not_found`、`profile_limit_reached`（FD 預算不夠時 `limit` 0）、`profile_memory_insufficient`（兩種記憶體算法的欄位）、`profile_port_unavailable`（18000～18099）、`endpoint_global`、`profile_index_corrupt`、`config_conflict`、`owner_defaults_unavailable` 的細節，固定回應的 405 與 HM-01 交下的逐位元案例；第 9 節 #27 |
| v1 草案（HM-10 審查修正） | 2026-11-16 | HM-10 | 依 HM-10 的獨立安全審查（報告路徑見 PR 描述）：第 3.2 節，索引隔離依 id 順序拿每個已登錄額外帳號的 `mutation_lock`，⑩ 在拿完所有鎖之後，拿到該帳號移除登錄為止（S-1）；第 3.6 節，索引隔離因此只撤銷一次；第 3.1 節，開通後預設帳號看得到的兩個位元組變化（PATCH／DELETE 沒帶 CSRF 從 405 變 403、表外方法的 `Allow` 從 4 個方法變 6 個；S-6，交 HM-18 或升版片寫進計畫 §7.2、CHANGELOG、`upgrade-notes.yaml`）；第 9 節 #19（FD 預算）、#34（刪除也收孤兒與讀不到的帳號、刪目錄前先抹後端欄位、本體格式錯固定 400）、#51（清單的 `orphans`）補上和 PaaS 的差異（S-2） |
| v1 草案（HM-10 rebase 到 HM-14 之後） | 2026-11-16 | HM-10 | rebase 到 HM-14（PR #103，`8ff259b`；它之前已合併 HM-08 審查修正、HM-09、HM-20 與 PR #100）之上：本片在第 9 節沒有自己的列（差異併在既有的 #19、#27、#34、#51），列號不用改；#19 的 FD 預算指到 HM-08 審查補的 #87；第 3.3 節「目錄已不是開啟時那一個」指到 8081 那一側的 #88；第 7 節錯開啟動列 HM-09 審查（S-12）與本片（帳號的鎖）兩段都留；#75 改成上限 60 分鐘（DQ-43，2026-11-15 定案，PR #100）；HM-10 列的「由 #100 記」寫明是 PR #100（第 9 節現在有第 100 列）。規則內容不變 |
| v1 草案（HM-31） | 2026-11-16 | HM-31 | 對齊 PaaS #155（`d7f5849`；使用者 2026-11-16 07:1x 決定所有產品都生效）：第 0 節第 1、5 點；第 1.2 節加不受開關管的一項（請求內容位元組預算、大請求讀取閒置、JSON 結構守門：缺口、理由、單帳號逐項改變、HM-01 凍結 99 案逐組核對沒有一案改變）；第 2.2 節第 4 點改成一套預算（全 add-on＋每帳號份額，token 驗過才扣，小請求不扣）；第 2.4 節表格改寫（准入滿時讀小請求、通知照常處理：HM-14 審查 MF-2 (b) 2026-11-16 07:5x 主對話定案；拒絕小額度拿掉；預算拒絕讀完丟掉、從頭尾找 id；讀取閒置 408；結構守門），`-32003` 文字與沒解析 body 的 id 規則；第 4.2 節 `-32003` 一列與新的 `-32602` 一列、n8n 的既有回應；第 5 節表格與推導（cgroup → MemAvailable−256 MiB → 32 MiB、份額上限 64 MiB、例子與已知限制）、「單一帳號有界」改寫（結構守門之下的解析成本）；第 9 節改 #15、#16、#96（待決 → 部署），加 #101～#107 |
