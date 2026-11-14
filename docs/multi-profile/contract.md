# 多帳號中立契約（v1，HM-00 起草）

- 狀態：HM-00 起草（2026-11-14）。HM-10 依實作補細節，HM-18 定稿；合併順序 HM-00 → HM-10 → HM-18。
- 「中立」：PaaS `WOOWTECH/woow-mcp-server` 的行為（pin `69ac425`）是期望值；HA 和它不同的地方，每一條都列在第 9 節的刻意差異表
  （計畫 §8.8，下稱「§8.8 #n」），沒列的就要相同。FEATURE-MATRIX 每一列（含「HA 平台差異」欄是「—」的列）對到哪一列、
  或為什麼相同，見 `deviation-trace.md`。
- 來源：計畫 `PLAN-zh-TW.md` §2～§8（repo 外，`artifacts/ha-multiprofile-parity-20261114/`）。決策見 `decisions.md`；
  驗收見 `acceptance-matrix.md`；威脅模型見 `threat-model.md`。
- 標「暫定」的細節：計畫沒寫死、本檔先定一個做法，由括號裡的切片實作時定案；改了要同時改本檔。
- 路徑縮寫：`Hc/`＝HA `packages/mcp-admin-core/mcp_admin_core/`（bb48449）；`Hui/`＝HA `packages/mcp-admin-ui/src/`；
  `Pc/`＝PaaS `packages/mcp-admin-core/mcp_admin_core/`（@69ac425）；其他 PaaS 路徑相對 PaaS repo 根目錄。

## 0. 先講結論

1. 產品沒開通（不在 `MULTI_PROFILE_PRODUCTS`）而且磁碟上沒有帳號資料時，**8081 與 8099 的回應和今天逐位元相同**，本檔的新行為都不生效；例外只有第 1.2 節「不受開關管」的變更（例如直連子程式要帶 bearer、log 遮得更多、還原時多一個標記檔）。
2. MCP 請求屬於哪個帳號**只看 token**；8081 永遠不讀 `X-MCP-Profile`、cookie、query。
3. 管理 API 開通後，帳號範圍路徑**一定要剛好一個** `X-MCP-Profile`；缺了 400、格式錯 400、不存在 404，絕不退回預設帳號。
4. 管理 API 全部走一條共用管線：先驗 HA 管理員，才看任何帳號狀態；非管理員在任何帳號狀態下拿到逐位元相同的 403。
5. 每個帳號（含預設帳號）讀 body 前有准入、讀 body 時有位元組額度；一個帳號用不到別的帳號的名額。
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
開機守門的存在檢查與休眠處理（HM-13b）、驗收與發版工具（HM-16、HM-17）。

## 2. MCP（8081）

### 2.1 路徑與方法

| 路徑 | 方法 | 沒開通（今天） | 開通後 |
|---|---|---|---|
| `/mcp` | GET、POST、DELETE；其他方法在 token 檢查之後回 405（`Allow: GET, POST, DELETE`） | Bearer 對預設帳號 | 剛好一個 `Authorization`、字面 `Bearer <token>`，依 token 選帳號 |
| `/private_<token>/mcp` | 同上 | 密鑰網址對預設帳號 | 依路徑裡的 token 選帳號；路徑上的 `Authorization` 一律不看 |
| `/health/ready` | GET | `{"ready":bool}`，200／503，只看預設帳號 | 不變（DQ-19 待定，計畫建議維持只看預設帳號） |
| 其他路徑（含 `/mcp/`、裸 `/private_<token>`） | — | 404 | 404（交預設 app） |

- MCP 路徑帶 query：400（在 token 檢查之後，同今天）。
- Bearer `/mcp` 帶任何 `Origin`：403（同今天；§8.8 #10）。密鑰網址的 Origin 見第 2.6 節。

### 2.2 帳號解析（分派器，開通才掛）

1. 只看 `scope["path"]` 與 `Authorization`。`/private_{secret}/mcp` 用 Starlette 自己的 `Route` 比對取出 secret；
   `/mcp` 要剛好一個 `Authorization`、字面 `Bearer <token>`；其他路徑交預設 app。
2. 候選 token 先 sha256 一次，再和每個帳號的摘要 `hmac.compare_digest`：預設帳號＋索引內讀得到、沒休眠、沒隔離的帳號；
   撤銷的略過。**全部比完、不提早結束。**
3. 快取：每帳號只存 state 的 stat 簽章與 token 摘要；簽章變了才重讀。
4. 命中後、讀 body **之前**做該帳號的准入；讀 body **時**逐塊扣該帳號的位元組額度，帶 `Content-Length` 時讀之前先比一次
   （暫定，HM-08 定案；第 2.4 節）。
5. 帳號 app 裡是今天的流程：再驗 token → 租約 → 方法 → Origin → query 400 → 讀 body → 政策 → session →
   轉送名額 → 重驗 → 轉發。只轉閘道自己的 child bearer 與 3 個 session 標頭（`mcp-session-id`、`mcp-protocol-version`、
   `last-event-id`）；只轉回 4 個標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`）。

### 2.3 解析結果

| 情況 | 回應 | 備註 |
|---|---|---|
| 剛好一個帳號 | 交該帳號 app，用自己的 store 再驗一次 | 路由錯只會被拒 |
| 零個 | 交預設 app：密鑰網址 404、Bearer 401＋`WWW-Authenticate: Bearer` | 與今天逐位元相同；不佔准入、不讀 body |
| 兩個以上（撞號） | 503 `{"error":"state unavailable"}`，不轉任何帳號 | WARNING 每組 60 秒一行（id 前 8 碼）；DQ-09 待定，計畫建議 503 |
| 預設 state 讀不到、索引結構壞 | 503 `{"error":"state unavailable"}`（含預設帳號） | 索引壞的處理見第 3.6 節 `profile_index_state` |
| 索引被面板以外改動（簽章不符） | 503 `{"error":"state unavailable"}`，直到重啟 | 簽章含 st_dev、st_ino、st_mtime_ns、st_ctime_ns、st_size、st_nlink；同 uid 下不是安全邊界 |
| 全部撤銷時寫入失敗的帳號 | 該帳號 503，直到重試成功 | 重啟時 `.revoke-all-pending` 讓守門在 listener 前重做 |

### 2.4 准入、位元組額度與過載回應

數值見第 5 節。拒絕的形狀：

| 情況 | HTTP | 內容 | 附註 |
|---|---|---|---|
| 讀 body 前就知道不夠（准入滿，或宣告的 `Content-Length` 超過剩餘的位元組額度），`Content-Length` ≤64 KiB（或沒帶，但 2 秒內讀完且 ≤64 KiB），解析得出 JSON-RPC id | 200，`Retry-After: 5` | 每個 id 一則 `-32003` | 用全 add-on 共用的「拒絕小額度」讀：同時 8 個、合計 512 KiB |
| 同上，但沒有 id、太大、讀不完或不是 JSON | 503，`Retry-After: 5` | `-32003`，`id: null` | 大於 64 KiB 的帶 id 請求拿 503（PaaS 200）：§8.8 #16 |
| 讀 body 途中位元組額度用完（沒帶 `Content-Length`，或實際內容比宣告的多） | 503，`Retry-After: 5` | `-32003`，`id: null` | 立刻停讀、釋放已讀的部分，不改用拒絕小額度（暫定，HM-08 定案） |
| 轉送名額等 1 秒逾時（body 已讀），有 id | 200，`Retry-After: 5` | 每個 id 一則 `-32003` | #148 形狀（HM-14） |
| 轉送名額等 1 秒逾時，沒有 id（GET、DELETE、保留名額也用完的通知） | 503，`Retry-After: 5` | `-32003`，`id: null` | 同上 |
| 排隊已達上限（每個佇列各自計數） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003` | 不等；WARNING 每帳號每情況 60 秒一行 |
| 排隊時用戶端關閉連線 | （沒有人收得到） | — | 請求從排隊移除、絕不送出；只記 WARNING |
| GET 串流已達上限 | 429，`Retry-After: 30` | `-32003`，`id: null` | 預設帳號 24 條、額外帳號 8 條 |
| 該帳號待送回覆位元組超過上限 | 200 | 新的 tools/call 在轉送前回 `-32003` | 只在開通的產品（第 6 節） |

- 只有通知或回應、沒有任何請求的 POST 走保留名額（每帳號 4 條）；判斷照 PaaS `_carries_no_request`：POST、可解析、
  物件或非空陣列、裡面沒有任何請求、每則都是通知或回應（HM-14）。
- `-32003` 的訊息是固定文字（HM-14 定稿）：寫出是哪一種上限與「稍後重試」，不含 token、網址或帳號名稱。
- 沒開通的產品照今天：8081 外框 `limit_concurrency=64`，超過時是 uvicorn 純文字 503；開通後改成上表的 JSON-RPC 忙碌回應（計畫 §7.2 第 3 點）。

### 2.5 回應途中與子程式斷線（HM-14）

| 情況 | 標頭送出前 | 標頭送出後（SSE） |
|---|---|---|
| token 被輪替、撤銷或帳號被刪 | 密鑰網址 404、Bearer 401（PaaS 403：§8.8 #1） | 每個還沒回應的 id 補一則 `-32005`，正常結束、不把例外丟給 uvicorn |
| 子程式中途斷線 | 502＋`-32004`（帶得出 id 就帶） | 補一則同 id 的 `-32004` 事件後結束 |

`-32004` 依原因用兩種固定文字：「子程式停止了（會自動重新啟動）」或「連線中斷，子程式仍在執行」，都寫「操作可能已完成也可能沒有，
請先確認再重試」；看當下那個世代的 `Supervisor.status`，最多等 0.25 秒下結論。log 只記一行 WARNING，不帶 traceback。

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
| `{base}/api/profiles` | GET | 帳號清單 | — | 200 `{"profiles":[列…]}`；`ETag: "p1-<64 hex>"`（索引 ETag） |
| `{base}/api/profiles` | POST | 建立 `{"label":…}` | If-Match（索引）＋Idempotency-Key | 201 該列（**不含 token**）＋`operation`；同一 key 重送回同一列（200） |
| `{base}/api/profiles/<id>` | PATCH | 改名 `{"label":…}` | If-Match（索引） | 200 該列 |
| `{base}/api/profiles/<id>` | DELETE | 刪除（含孤兒；DQ-14 待定，照計畫建議：先撤銷並抹憑證再刪、孤兒不自動刪、不做軟刪除、面板兩段確認；負責片 HM-10） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<id>","operation":…}`（暫定，HM-10） |
| `{base}/api/profiles/revoke-all` | POST | 全部撤銷（含預設） | If-Match（索引）＋Idempotency-Key | 200 逐帳號 `results:[{id,result:"revoked"}]`；有失敗見第 4.1 節 `operation_outcome_unknown` |
| `{base}/api/profiles/restore-record` | GET | 還原與休眠核對紀錄（不含秘密） | — | 200（欄位第 3.6 節） |
| `{base}/api/profiles/<id>/restore-review` | POST | 標記「已核對」 | If-Match（索引）＋Idempotency-Key | 200 `{"profile":{"id"},"reviewed_at":…,"operation":…}`（暫定，HM-13c） |
| `{base}/api/profiles/index/quarantine` | POST | 隔離壞掉的帳號索引 | If-Match（原始位元組算的 ETag）＋Idempotency-Key | 200（暫定，HM-10） |
| `{base}/api/profiles/quarantine/<名稱>/delete` | POST | 刪除一個隔離目錄（`<名稱>`＝目錄名去掉 `.quarantine-` 的 `<id>-<UTC>`；同一個 id 可能有多個） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<名稱>","operation":…}`（暫定：路徑、名稱格式與回應都由 HM-13c 定案） |
| 頁面與靜態檔 | GET、HEAD | 面板 | — | 同今天 |

**帳號範圍路徑**（其他 `{base}/api/*`；開通後一定要剛好一個 `X-MCP-Profile`）：

| 操作 | 方法 | 開通後的變化 |
|---|---|---|
| `bootstrap` | GET | 多 `profile`、`profiles_supported`；預設帳號另帶索引狀態、休眠與還原通知（第 3.6 節） |
| `configuration`、`capabilities` | GET | 回應帶 `profile:{id}` |
| `diagnostics` | GET | 只回選定帳號的子程式緩衝 |
| `operations/<id>` | GET | 收據依帳號 |
| `backend`、`backend/patch` | PUT | Odoo 換 url／database／username 換 token、回 `token_rotated:true`（HM-12；DQ-05 細節待定）；改 url 來源沒帶新秘密 422（DQ-40 ⑨） |
| `backend/test` | POST | 測選定帳號已存的設定 |
| `policy`、`odoo/write-switches`、`odoo/allowed-methods`、`n8n/session` | PUT | 只重啟選定帳號的子程式 |
| `endpoint` | PUT | 額外帳號 409 `endpoint_global`（全域設定只存在預設 state；DQ-13 待定，照計畫建議） |
| `token/reveal`、`token/revoke` | POST | 只動選定帳號 |
| `token/rotate` | POST | 還原或休眠後未核對前 409 `restore_review_required` |
| `child/restart` | POST | 回應帶 `blocked_reason` |
| `owner-defaults/restore`、`owner-defaults/dismiss` | POST | 只在預設帳號；額外帳號 409 `owner_defaults_unavailable`（暫定，HM-10） |

- 方法：只有 `profiles/<id>` 接受 PATCH、DELETE；其他路徑的 PATCH、DELETE 回 405。開通後 8099 的路由要收 PATCH、DELETE，
  方法表改在管線第 ⑤ 步檢查（identity 之後）；沒開通照今天（路由層直接 405）。
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

### 3.3 `X-MCP-Profile` 規則（DQ-17 細節待定，照計畫建議；負責片 HM-10）

| 情況 | 開通後的回應 |
|---|---|
| 帳號範圍路徑、沒帶 | 400 `profile_id_required`（§8.8 #31；PaaS 當 `default`） |
| 帶兩個以上 | 400 `profile_id_invalid`（§8.8 #83；PaaS 取第一個值，第一個值存在就照常服務） |
| 值不是 `default`、24 位小寫 hex | 400 `profile_id_invalid`（§8.8 #32；PaaS 404） |
| 格式對、不存在（含隔離目錄） | 404 `profile_not_found`；絕不退回預設帳號 |
| 存在但讀不到（`profile_unavailable`） | 503 `{"error":"state unavailable"}`；仍可刪除 |
| 全域路徑 | 不看這個標頭；路徑裡的 `<id>` 格式錯在第 ⑤ 步回固定 400（沒有細節），格式對但不存在在第 ⑪ 步回 404 `profile_not_found` |
| 沒開通的產品 | 不要求、不看（同今天） |
| 8081 | 永遠不看 |

面板開通後**每個**帳號範圍請求都帶這個標頭，包括明確的 `default`（第 3.4 節）。

### 3.4 帳號回聲

- `bootstrap` 回 `profile:{"id","label","is_default"}` 與 `profiles_supported:true`。
- 其他帳號範圍的 JSON 回應都帶 `profile:{"id"}`。
- 面板一次變更內鎖定帳號：bootstrap 與變更兩個請求帶同一個標頭，兩個回應的回聲都要比對；不符就不顯示、藏起已顯示的 token、
  提示並重抓（I12；HM-11）。
- 任何帳號範圍請求回 `profile_not_found`：面板立刻重抓清單、切回預設帳號並提示。

### 3.5 寫入保護（DQ-15 細節待定，照計畫建議；負責片 HM-10；§8.8 #34）

| 對象 | If-Match | Idempotency-Key | 收據放哪 |
|---|---|---|---|
| 帳號設定（`backend`、`policy`…） | 帳號 ETag `"c1-<64 hex>"`；HMAC domain 加帳號 id，拿 A 的 ETag 寫 B → 409 `config_conflict` | 照今天（`token/rotate`、`token/revoke`、`child/restart`） | 該帳號目錄的 `.state.json.operations.json` |
| 建立、刪除、全部撤銷 | 索引 ETag `"p1-<64 hex>"` | 要 | `/data/mcp/.profiles.json.operations.json` |
| 索引隔離 | 壞索引的原始位元組算出的 ETag（格式同 `"p1-…"`，暫定，HM-10） | 要 | 同上 |
| 改名 | 索引 ETag | 不要 | — |
| 還原核對（restore-review） | 索引 ETag | 要 | 全域收據 |
| 刪除隔離目錄（暫定，HM-13c） | 索引 ETag | 要 | 全域收據 |

- 缺 If-Match 428 `config_revision_required`；不只一個或過期 409 `config_conflict`。
- 缺 Idempotency-Key 428 `operation_id_required`；不只一個 400 `operation_id_invalid`；同一個 key 還沒完成就重送 409
  `operation_outcome_unknown`；還原前的舊操作 id 410 `operation_restored`。
- 建立的回應與同一個 key 的重送**都不回 token**；token 只經 `token/reveal`＋`X-MCP-Profile: <新 id>`＋回聲比對取得。

### 3.6 欄位

**清單列**（都不含秘密）：

| 欄位 | 值 |
|---|---|
| `id` | `default` 或 24 位小寫 hex |
| `label` | 預設帳號固定 `Default`（面板顯示「預設帳號」）；其他是使用者給的名稱 |
| `port` | 預設帳號 3000；額外帳號 18000 起 |
| `is_default` | bool |
| `disabled_reason` | `null`、`profile_limit`、`memory_capacity`、`port_conflict`（順序照 PaaS：產品上限 → 記憶體 → port）；HA 另有 `profile_unavailable`、`quarantined`、`dormant`（§8.8 #51） |
| `required_memory_mib` | 只在 `disabled_reason=memory_capacity` 時出現 |
| `status` | `running`、`starting`、`backoff`、`unconfigured`、`blocked`、`failed`、`dormant` |
| `blocked_reason` | `null`、`child_port_conflict`、`child_port_in_use`、`memory_capacity` |

**bootstrap 增加的欄位**（開通後）：`profile`（第 3.4 節）、`profiles_supported`、`profile_index_state`（`ok` 或 `corrupt`；
`corrupt` 時另帶一個由原始位元組算出的 ETag，給「隔離帳號索引」用）、還原與休眠通知（欄位名 HM-13c 定案）。
沒開通但有帳號資料時只多 `dormant_profiles`（數字）。

**請求本體**：建立與改名都是剛好一個鍵 `{"label": <字串>}`。名稱規則（DQ-16 細節待定，照計畫建議；負責片 HM-10、HM-11；§8.8 #35）：去頭尾空白後 1～80 個 code point；
拒絕 Cc、Cf（含 bidi、零寬）、Zl、Zp、Cs、Co、未指派；NFKC＋casefold 判重；`default` 與「預設帳號」保留。名稱只存在索引，
不進目錄名、log、MCP 回覆。

**還原紀錄**（`restore-record`，HM-13b 寫、HM-13c 讀；暫定）：還原時間；逐帳號 `id`、`label`、身分欄位（`identity_fields` 分類）、
政策摘要（寫入開關、停用工具、逐項寫入授權、禁止的操作、Odoo 方法清單、n8n session）、`reviewed_at`（`null` 或時間）、目前狀態；
隔離目錄清單；休眠段落。不含任何 token 或密碼，網址裡的帳密也不記。

**索引隔離**：先撤銷 `profiles/` 底下每個帳號目錄的 token，再把 `profiles.json` 改名成 `profiles.json.quarantine-<UTC>`；
預設帳號立刻恢復，帳號目錄都變孤兒、可逐一刪除。面板 403（Core 未審）時這個動作也用不了。

### 3.7 Ingress 備援（只在 UC-10 證實 Ingress 不轉 `X-MCP-Profile` 或 PATCH／DELETE 時用；§8.8 #50）

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
| `profile_not_found` | 404 | 格式對但帳號不存在（含隔離目錄）；全域路徑的 `<id>` 不存在；要刪的隔離目錄不存在（暫定，HM-13c） | `code` | ⑦（標頭）／⑪（全域路徑） | 不出現（整條路由 404） | 404 `"Profile not found"`（字串） | 本體多 `code` | 新 | HM-10；面板收到就切回預設（HM-11） |
| `profile_label_invalid` | 422 | 名稱違反第 3.6 節規則 | `code` | ⑪ | 不出現 | 422 字串（只檢長度 1～80） | §8.8 #35 | 新 | HM-10、HM-11 |
| `profile_default_immutable` | 422 | 改名或刪除預設帳號 | `code` | ⑪ | 不出現 | 422 字串 | 本體多 `code` | 新 | HM-10 |
| `profile_label_conflict` | 409 | NFKC＋casefold 後和既有名稱或保留名稱相同 | `code` | ⑪ | 不出現 | 409 `"Profile label already exists"` | §8.8 #35（判重較嚴） | 新 | HM-10 |
| `profile_limit_reached` | 409 | 已到 min(5、產品上限)（各產品見第 5 節） | `code`、`limit` | ⑪ | 不出現 | 409，同欄位＋`message` | 同（少 `message`） | 新 | HM-10；`tests/test_profile_admin_api.py` |
| `profile_memory_insufficient` | 409 | 記憶體條件不夠再開一個 | `code`、`limit`、`required_memory_mib`、`memory_limit_mib`（讀得到 cgroup 才有）、`available_memory_mib`（HA 另帶） | ⑪ | 不出現 | 409，`limit`、`memory_limit_mib`、`required_memory_mib`＋`message` | §8.8 #19 | 新 | HM-09、HM-10 |
| `profile_port_unavailable` | 409 | 18000～65535 找不到空 port | `code` | ⑪ | 不出現 | 409 `"No child port available"` | 本體多 `code` | 新 | HM-09、HM-10 |
| `profile_product_unsupported` | 409 | 產品不在七產品（OpenDesign、Odoo Manage）卻收到建立；正常不會開通，屬防呆 | `code` | ⑪ | 不出現 | OpenDesign 可開 3 個 | §8.8 #43 | 新 | HM-07、HM-10 |
| `endpoint_global` | 409 | 對額外帳號 `PUT endpoint` | `code` | ⑪ | 不出現 | 不存 endpoint | §8.8 #27 | 新 | HM-10 |
| `restore_review_required` | 409 | 還原或休眠後、該帳號還沒「已核對」就 `token/rotate` | `code` | ⑪ | 不出現 | 手冊步驟 9 核對後才發 | §8.8 #58 | 新 | HM-13c；`tests/test_restore_review.py` |
| `profile_index_corrupt` | 503 | 帳號索引結構壞：清單、建立、改名、刪除、額外帳號範圍路徑（預設帳號的 bootstrap 照回，帶 `profile_index_state:"corrupt"`；全部撤銷、還原紀錄、索引隔離照常可用，暫定，HM-10） | `code` | ⑦／⑪ | 不出現 | 整台 503（含管理 API） | §8.8 #25 | 新 | HM-07、HM-10 |
| `config_conflict` | 409 | If-Match 過期或不只一個；拿 A 的 ETag 寫 B；索引 ETag 不符 | `code`（形狀 B：本體只有 `detail`） | ⑪ | 照今天 | 帳號設定有；帳號 CRUD 不收 If-Match | §8.8 #34 | 既有（擴大） | HM-05、HM-10 |
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
| `owner_defaults_unavailable` | 409 | 額外帳號的 owner-defaults 操作（暫定）；沒有標記的 state | `code`（形狀 C：本體另帶 `error:"owner_defaults_unavailable"`） | ⑪ | 照今天 | 沒有同名代碼（owner-defaults 只在預設帳號） | HA 既有 | 既有 | HM-10 |
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
- 405：路由層回 Starlette 的純文字與 `Allow`（8099 只收 GET、HEAD、PUT、POST）。
- 404：未知的 `/api/*` 操作在角色檢查之後回、本體是空的；頁面路徑用 PUT、POST 在第 ① 步之後就回（`Hc/gateway.py:714-716`）。

其中 403（斷線除外）、400、415、405、404 由 HM-01 的管理 API 契約凍結逐位元凍結；503、408、413 與斷線的 403 今天沒有逐位元案例
（名額滿、拿鎖逾時、408、413 連狀態碼都沒有直接的既有測試），由 HM-10 的否定矩陣補未開通時的案例。

### 4.2 MCP（8081）

| 代碼或形狀 | HTTP | 什麼時候 | 內容 | 沒開通時 | PaaS（@69ac425） | 差異 | 新舊 | 負責片／測試 |
|---|---|---|---|---|---|---|---|---|
| 錯 token：密鑰網址 | 404 | 零命中、撤銷、沒設 | Starlette 預設 404，沒有 `WWW-Authenticate` | 同 | 403 | §8.8 #1 | 既有 | HM-01、HM-08；`tests/test_profile_routing.py` |
| 錯 token：Bearer | 401 | 零命中、撤銷、沒設 | 空本體＋`WWW-Authenticate: Bearer` | 同 | （沒有 Bearer） | §8.8 #1、#2 | 既有 | 同上 |
| `{"error":"state unavailable"}` | 503 | 撞號、預設 state 或索引讀不到、索引外改、全部撤銷失敗的帳號 | 固定本體 | 只有預設 state 讀不到 | 503 | DQ-09 待定 | 既有（擴大） | HM-08 |
| `{"error":"request denied"}` | 400 | MCP 路徑帶 query | 固定本體 | 同 | 原樣轉發 | §8.8 #3 | 既有 | HM-01 |
| `{"error":"request denied"}` | 403 | Bearer 帶 Origin；Headscale 密鑰網址的來源不在清單 | 固定本體 | 同 | Origin 清單 403 `ORIGIN_DENIED` | §8.8 #9、#10 | 既有 | HM-27 |
| JSON-RPC `-32003` | 200／503／429 | 准入、位元組額度、轉送名額逾時、排隊上限、GET 串流上限、待送回覆上限 | 第 2.4 節 | 沒有（uvicorn 503、名額逾時 503） | 200／503／429（先讀 body） | §8.8 #15、#16 | 新 | HM-08、HM-14、HM-30；`tests/test_profile_quotas.py`、`tests/test_gateway_busy_shapes.py` |
| JSON-RPC `-32004` | 502／SSE 事件 | 子程式在處理途中斷線 | 依原因兩種文字（第 2.5 節） | 502 `{"error":"request denied"}`、SSE 安靜結束 | 同（#148） | 同 | 新 | HM-14；`tests/test_gateway_stream_endings.py` |
| JSON-RPC `-32005` | SSE 事件 | 標頭送出後 token 被換掉 | 每個未回應 id 一則 | 直接斷線 | 同 | 同 | 新 | HM-14 |
| `backend_not_configured`（`-32603`） | 200 | 帳號沒填後端、工具需要後端；n8n 額外帳號沒後端時所有工具（含文件工具） | `ToolCallRefused` 形狀 | 照今天 | n8n 額外帳號起文件模式 | §8.8 #28（DQ-22 待定） | 既有（擴大） | HM-25 |
| `backend_unreachable`（`-32603`） | 200 | 最近的健康檢查說後端連不上 | 帶檢查的原因 | 照今天 | 沒有定期監看 | §8.8 #18 | 既有 | HM-09、HM-30 |
| 429 GET 串流 | 429 | GET 串流已達上限 | `-32003`、`id: null`、`Retry-After: 30` | 不設上限 | 同（32 條） | §8.8 #15 | 新 | HM-08 |

上表只列多帳號會新增或改變的回應。**其他既有回應照今天**（開通後每個帳號 app 照舊）。這些回應由 HM-01 的契約凍結與既有測試鎖住；
其中讀 body 時斷線的 403 與其他 `Denied`（交 HM-08）、502 與轉送名額等候逾時的 503（交 HM-14）今天只驗狀態碼或沒有測試，
由負責片補未開通時的逐位元案例（逐項對照見 HM-01 的 provenance 筆記第 4 節）：

- 405＋`Allow: GET, POST, DELETE`：MCP 路徑用其他方法（token 檢查之後；`Hc/gateway.py:1021-1022`）。自答 session 的 GET 是 405＋`Allow: POST, DELETE`。
- 400：GET、DELETE 帶 body；session 標頭不只一個或格式錯；initialize 以外沒帶 `mcp-session-id`（有 id 的 POST 回 `-32000`「Bad Request」）。
- 403：讀 body 時斷線；政策拒絕的 tools/call 沒帶 session；其他政策拒絕（`Denied`）。
- 408（讀 body 超過 60 秒）、413（超過 16 MiB）、415（`Content-Type` 不是 `application/json`）；n8n 另有 4 MiB、10,000 元素、深度 64 的
  上限，超過時回 JSON-RPC 錯誤本體（`Hc/request_limits.py`、`Hc/gateway.py:1034-1055`）。
- 政策拒絕、帶 session 的 tools/call：200＋`-32602`（`Unknown tool`、`Invalid params`、`Operation not permitted`；`Hc/policy.py:42-68`）。
- 未知方法：有 id 200＋`-32601`「Method not found」；通知 202。
- 子程式未就緒時閘道自答 initialize、ping、tools/list（§8.8 #68）；就緒後自答 session 回 404（有 id 的 POST 帶 `-32000`「Not Found」）。
- 子程式回 4xx、5xx（401、403 除外）：照原狀態碼，本體換成 `-32000`＋狀態片語（`Hc/gateway.py:153-160`；§8.8 #62 的 429 就是這樣來的）。
- initialize 等不到子程式的回覆：503＋`-32000`「BACKEND_UNAVAILABLE」＋`Retry-After: 5`（`Hc/gateway.py:119-122`）。
- 502 `{"error":"request denied"}`：連不上子程式、子程式回 3xx／401／403、回覆格式不對或超過 8 MiB、協定版本不在審過的清單
  （`Hc/gateway.py:1204-1206`、`:1230`、`:1258`、`:1288-1291`、`:1301`）。
- 轉送名額等 1 秒逾時：503 `{"error":"request denied"}`（開通後改成第 2.4 節的 `-32003`）。

## 5. 名額與記憶體數值（DQ-07＋DQ-29 採 (a)；暫定，HM-19c 量測後定案）

| 項目 | 預設帳號（開通後） | 每個額外帳號 | 今天（沒開通） |
|---|---|---|---|
| 讀 body 前准入（同時進行中的請求） | 64 | 32 | listener 64 |
| 位元組額度（已讀進記憶體、還沒轉出的請求內容） | 64 MiB | 64 MiB | 無（最壞 64×16 MiB） |
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

- 原則：每個帳號（含預設）讀 body 前受准入、讀 body 時受位元組額度；一個帳號用不到別的帳號的名額或額度；沒有共用池。
- 全域最壞記憶體（推算，全部帳號同時被打滿）＝Σ每帳號（位元組額度×請求放大 2.5＋待送回覆上限）＋工作執行緒一筆的解析放大
  （8 MiB×25）＋子程式。Odoo 6 個帳號約 6×(64×2.5＋32)＋200＝1,352 MiB（推算）。**單一帳號有界**：一個 token 的持有人最多約 192 MiB，
  加上共用的一筆放大。HM-19c 在 J6412（可以的話 J1900）量 MemAvailable；超過「MemAvailable－保留量」就把額外帳號的位元組額度往下調，
  不調就不能發版。
- FD：開通後啟動時把 soft `RLIMIT_NOFILE` 提到「需要量＋25%」（最壞約 500，推估），不超過 hard；hard 不夠就不開額外帳號、記一行 WARNING。
- 零命中的請求（錯 token）不佔准入。未帶 token 的半開連線撐滿 listener 是既有問題，不在範圍。
- 記憶體檢查：建立帳號、存後端（子程式第一次要起）、手動重啟時讀 `/proc/meminfo` 的 MemAvailable；不足「產品每子程式 MiB＋保留量」時，
  建立回 409 `profile_memory_insufficient`，存後端照存但子程式不起（`blocked`＋`memory_capacity`）。開機時不擋。讀得到 cgroup
  `memory.max` 時照 PaaS 公式。

**各產品的額外帳號上限與每子程式記憶體**（暫定照 PaaS；HM-07 定常數，HM-19c 在目標硬體量測後定案，改了要同時改本表）：

| 產品 | 額外帳號上限 | 每子程式 MiB | 8081 外框（64＋32×上限） | PaaS（@69ac425） |
|---|---|---|---|---|
| Odoo | 5 | 100 | 224 | 5／100 MiB（`apps/odoo/odoo_mcp_admin/main.py:47-48`） |
| n8n | 2 | 300 | 128 | 2／300 MiB（`apps/n8n/n8n_mcp_admin/main.py:35-36`） |
| Hermes | 3 | 160（HM-24 在 HAOS 至少 60 分鐘負載量測後定） | 160 | 預設 3／160 MiB |
| EMQX、LiteLLM、Nextcloud、Headscale | 3 | 160 | 160 | 預設 3／160 MiB（`Pc/launch_policy.py:152-154`） |
| OpenDesign、Odoo Manage | 0（不開放，DQ-28） | — | 64（不掛分派器） | OpenDesign 預設 3／160 MiB |

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
| port | 預設帳號 3000；額外帳號 18000 起找第一個空號，避開 3000、8081、8099、索引內 port、執行中子程式的 port；試綁四種位址確認沒人佔 |
| spawn 前檢查 | port 衝突或被佔就不 spawn，`status=blocked`＋`blocked_reason` |
| 看門狗（DQ-20 採 (b)） | 開通的產品所有帳號（含預設）：退避 2、5、15、30、60、120、300 秒，不限次數，連續跑 120 秒歸零；OOM 殺掉也照退避。沒開通維持今天「同一次啟動最多 4 次、不歸零、之後 failed」 |
| 錯開啟動 | 預設帳號先起；額外帳號依序起、同時最多 2 個，前一個健康檢查通過或 30 秒逾時才起下一個 |
| 啟動順序 | legacy 遷移（只對預設）→ 還原偵測、守門、休眠處理 → 預設帳號 → 錯開起額外帳號（壞的標記、不擋其他） |
| 關閉 | 所有 `Supervisor.stop()` 並行，在 HA 停止上限 30 秒內收完 |
| 健康監看 | 每帳號一個、自己的 httpx client、起點錯開；認證被拒 15→30→60→120→300 秒退避；開通後連兩次失敗才判 unreachable（DQ-25 待定，照計畫建議；負責片 HM-09、HM-30） |
| 監看失敗 | 額外帳號只標記 `failed`；預設帳號維持今天「任何元件停止就退出」（DQ-21 待定） |
| 資源 | 額外帳號子程式 exec 前寫 `/proc/self/oom_score_adj`＝500（絕對值）與 `setpriority(+5)` |
| 子程式 bearer（HM-06，不受開關管） | 剛好一個 `Authorization`、`hmac.compare_digest` 比對 `Bearer <WOOW_MCP_CHILD_TOKEN>`；不符 401（不寫細節）；環境變數缺、空或不符 `[A-Za-z0-9_-]{43}` 就拒絕啟動 |
| log 事件 | 子程式啟動、結束（結束碼）、退避（下次秒數）、`failed`、`blocked`（原因碼）、監看認證退避、撞號、孤兒、隔離、還原守門逐帳號動作、休眠撤銷、缺哪些連線鍵（只列鍵名）；格式 `[profile=<id 前 8 碼> port=<p> pid=<n>]`；每帳號每情況 60 秒一行（`suppressed=N`） |

## 8. 資料（摘要）

- 布局：預設帳號在 `/data/mcp/`（`state.json` 一個鍵都不加）；索引 `/data/mcp/profiles.json`；額外帳號 `/data/mcp/profiles/<24 hex>/`；
  還原用 `.instance-sentinel`、`.instance-record`、`.restore-detected`、`.revoke-all-pending`、`restore-record.json`（都不含秘密）。
  n8n 額外帳號的 `nodes.db` 在 `/tmp/woow-n8n-mcp/profiles/<id>/`（DQ-04 待定）。
- 索引格式（和 PaaS `profile_index` 同形狀）：

  ```json
  {"version": 1, "profile_index": {"0123456789abcdef01234567": {"label": "會計", "port": 18000}}}
  ```

  0600、擁有者 10001、單一連結、≤64 KiB、`O_NOFOLLOW`、`strict_json`（拒絕重複鍵）；頂層鍵剛好 `version`、`profile_index`；
  每筆鍵剛好 `label`、`port`；id 24 位小寫 hex；port 是 int 不是 bool、1024～65535、不是 3000／8081／8099；≤5 筆；
  物件順序＝建立順序。port 重複或撞預設 port 不算結構錯（只停相關帳號）。
- 額外帳號 store 只開既有（`existing_only`）：缺 state 不補建、檢查擁有者 uid；建立一次寫入最終初值（新 token、新 child_token、
  連線全空、`endpoint=None`、政策照 DQ-02 複製預設帳號當下的值、`n8n_session` 不複製、建立不記 history）。
- 項目預算：5 個帳號加隔離與封存約 50 項、最深 4 層，在 entrypoint 還原修復上限（512 項、8 層）內；超過 400 項時面板警示。

## 9. 刻意差異表（§8.8）

類型：**既有**＝HA 今天就不同、不是多帳號造成；**部署**＝平台差異；**加嚴**＝HA 比 PaaS 嚴（DQ-40 的 10 項已一次確認；
其餘加嚴的列和它們一起列入給 PaaS 的回補建議，HM-29）；**待決**＝看還沒定的決策。第 1～43 列是計畫 §8.8 原表（2026-11-14 的決策已套用）；
第 44～79 列是 HM-00 對照腳本把 FEATURE-MATRIX「HA 平台差異」欄與 G6 §5「HA 期望值與差異」欄逐列對照後補的列；第 80～86 列是
審查後把 FEATURE-MATRIX「HA 平台差異」欄是「—」的 44 列人工逐列看過後補的列。逐列的來源與結論見 `deviation-trace.md`。

| # | 項目 | PaaS（@69ac425） | HA | 理由 | 類型 |
|---|---|---|---|---|---|
| 1 | 錯 token | 403 | 密鑰網址 404、Bearer 401 | HA 既有契約（Hc/gateway.py:932-947） | 既有 |
| 2 | Bearer 接法 | 沒有 | 有，依 token 選帳號 | HA 主推接法（DQ-01 採 (a)） | 既有 |
| 3 | MCP 路徑帶 query、`/mcp/` | 轉發、等同 `/mcp` | 400、404 | HA 較嚴 | 既有 |
| 4 | 轉送的用戶端標頭 | 大部分（含 `x-n8n-*`） | 只有 3 個 session 標頭；回程只轉 4 個固定標頭（不含 Location） | n8n-mcp 會依 `x-n8n-*` 換後端（G5-13） | 既有 |
| 5 | 工具呼叫逾時 | 110 秒回 `-32001`（Pc/proxy.py:44-46） | 330 秒（Hermes chat 300 秒） | HA 既有（R07 X-20；DQ-24 待定） | 既有 |
| 6 | legacy SSE | 轉送 `/sse`、`/messages/` | 不支援 | HA 子程式只開 Streamable HTTP（DQ-23 待定，建議不支援） | 既有 |
| 7 | readiness | `/healthz` 恆 200 | `/health/ready` 200／503，只代表預設 | FM-67；DQ-19 待定 | 既有 |
| 8 | 新帳號 token 歷史 | 記一筆 `auto_issue`（R03 §1.4） | 不記 | HA history 只收 rotate／revoke（Hc/products.py:264-268）；DQ-02 採 (a) | 既有 |
| 9 | Headscale Origin 清單 | 只放自己的管理網址（claude.ai 403；R07 X-17） | 只放 `https://claude.ai` | 使用者對 HA Headscale 的決定（R01 H-08） | 既有 |
| 10 | Bearer 帶 Origin | （沒有 Bearer） | 一律 403；DQ-11 第二問（S14 實測後）再定要不要精確放行 `https://claude.ai` | 瀏覽器不在 Bearer 契約 | 既有／待決 |
| 11 | 管理身分 | 密碼＋JWT | Ingress＋HA 角色，每請求查 | 平台不同 | 部署 |
| 12 | 管理管線 | 中介層先驗登入 | 看狀態前先驗角色、提交前再驗一次（第 3.2 節） | I10；HA 角色每請求查 | 部署 |
| 13 | listener 身分檢查 | 轉發前必過 | 讀得到才做，讀不到降級（HM-15，條件式） | HA AppArmor 未確認；不讓整台停擺 | 部署 |
| 14 | 子程式重啟 | 2→300 秒、不限次數、120 秒歸零 | 開通的產品相同（DQ-20 採 (b)）；沒開通維持 4 次後 failed | 沒開通維持今天 | 部署 |
| 15 | 名額 | 每帳號連線 64、串流 32、等 10 秒、排隊 32＋保留 8；共用池 | 讀 body 前准入（64／32）、位元組額度、轉送 32／16 等 1 秒、串流 24／8、排隊 32／16＋保留 4、待送回覆額度；沒有共用池 | HA 沒有 cgroup、硬體小（G3-24）；DQ-07 採 (a) | 部署 |
| 16 | 讀 body 前拒絕的回應碼 | 先讀 body，帶 id 一律 200＋`-32003` | ≤64 KiB 讀出 id 回 200＋`-32003`；更大的 503 | 讀 body 前准入防單一帳號吃光 listener（C3-MF-2） | 部署 |
| 17 | 回覆處理 | 事件迴圈內 | 一條工作執行緒、依帳號輪流 | HA 硬體慢、單一迴圈（第 6 節） | 部署 |
| 18 | 健康檢查 | 沒有定期後端監看（FM-68） | 每帳號監看、連兩次失敗才判壞、認證退避 | HA 既有監看；Odoo 以來源 IP 冷卻 | 部署 |
| 19 | 容量檢查 | cgroup 公式（建立時） | MemAvailable（建立、存後端、起子程式時）；讀得到 cgroup 才用公式；錯誤多帶 `available_memory_mib` | HA 沒有 cgroup | 部署 |
| 20 | 還原 | 手冊＋restore_guard（k8s Job） | entrypoint＋sentinel 偵測、開機守門、讀不到就隔離 | Supervisor 沒有 hook | 部署 |
| 21 | 還原時預設帳號 | 一律撤銷 | DQ-03 採 (b) A2：只有磁碟上有帳號資料的還原才撤銷預設帳號 | 白名單落後＋還原換回舊版 | 部署 |
| 22 | 還原後 token 歷史 | 清空（R04 S-15） | 保留，加一筆 revoke | 不改 schema | 部署 |
| 23 | 孤兒 | 讓還原停機（Pc/restore_guard.py:443-446） | 只隔離、不擋開機 | 不讓含孤兒的備份永遠起不來（G1:435） | 加嚴（建議回補） |
| 24 | 休眠帳號 | 沒有（沒有產品開關） | 沒開通的版本撤銷休眠帳號 token | 開關＝發版（第 1.2 節） | 部署 |
| 25 | 索引壞 | 整台 503（含管理 API；R03 §1.6） | 8081 503、面板照開、「隔離帳號索引」 | HA 沒有手動修復途徑（DQ-12 待定） | 部署 |
| 26 | 手改索引 | 重啟才生效（R03 §4.12） | 503 到重啟 | 外改＝繞過鎖 | 加嚴 |
| 27 | endpoint | 不存，用瀏覽器 origin | 存在預設 state、全域 | Ingress 和 MCP 不同源（FM-12）；DQ-13 待定 | 部署 |
| 28 | 沒填連線的子程式 | 5 個產品照起；n8n 額外帳號起文件模式（R06 PR-n8n-01） | 都不起；n8n 預設照起；n8n 額外帳號沒後端時所有工具回 `backend_not_configured`（DQ-22 待定） | 省記憶體（FM-45） | 部署 |
| 29 | 日誌 | 每帳號 Logs 5,000 筆／2 MiB、SSE；保留 2 個剛刪除帳號（Pc/routers/logs.py:59-65） | 每帳號子程式輸出 200 筆／128 KiB 快照；管理程序紀錄在 add-on log（帶 id 前 8 碼）；刪除就釋放 | HA 既有診斷模型（FM-65） | 部署 |
| 30 | 面板 403（Core 未審） | 沒有平台門檻 | 整個面板 403，任何帳號都撤銷不了，只能停 add-on | HA 角色驗證契約（FM-70） | 部署 |
| 31 | 管理 API 沒帶帳號 | 當 default | 開通後 400 `profile_id_required` | fail closed（I12；DQ-40 ①） | 加嚴 |
| 32 | `X-MCP-Profile` 格式錯 | 404（Pc/profiles.py:611-614） | 400 `profile_id_invalid`（在角色檢查後） | 分清「格式錯」與「不存在」 | 加嚴 |
| 33 | 管理回應帶帳號回聲 | 沒有 | 有，面板比對 | fail closed（DQ-40 ②） | 加嚴 |
| 34 | 帳號 CRUD 寫入保護 | 不收 If-Match、不走收據；刪除 204 | 全部 If-Match；建立、刪除、全部撤銷、索引隔離要 Idempotency-Key；刪除 200＋收據 | HA 既有規則（Hc/gateway.py:456-484；DQ-40 ③） | 加嚴 |
| 35 | 帳號名稱 | 接受控制、bidi、零寬字元 | 拒絕；NFKC 判重 | 防管理員誤認（DQ-16；DQ-40 ④） | 加嚴 |
| 36 | 帳號選擇保存 | sessionStorage | 只放記憶體 | 保留 HA 儲存不變式（DQ-18；DQ-40 ⑤） | 加嚴 |
| 37 | 子程式 bearer | 只有 n8n 驗 | 7 支 Python 子程式也驗、驗格式 | port 錯置時不跨帳號執行（DQ-40 ⑥） | 加嚴 |
| 38 | 回覆遮罩 | 子程式只知道自己帳號的憑證（FM-76） | 本帳號秘密＋所有帳號 token／child_token | 一個 add-on 持有多個帳號的 token（DQ-40 ⑧） | 加嚴 |
| 39 | 後端網址 loopback | 只有 n8n、EMQX 存檔過 SSRF | 開通後全部產品存檔與執行期都拒 | 縱深防禦（DQ-10；DQ-40 ⑦） | 加嚴 |
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
| 51 | 帳號清單欄位 | `id`、`label`、`port`、`is_default`、`disabled_reason`（3 種）、`required_memory_mib` | 另加 `status`、`blocked_reason`；`disabled_reason` 多 `profile_unavailable`、`quarantined`、`dormant` | 沒有 operator 監看，補 PaaS 只有預設帳號有健康的缺口（K-02） | 部署 |
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
| 75 | CI | Gitea Actions | GitHub Actions `checks`（root、0 skip、Python 3.13.16、上限 40 分鐘）；拆 job 要保留 `checks` 名稱 | Store 必要檢查名稱（DQ-43 待定） | 部署 |
| 76 | 面板測試 | 只有 `node --test` 進 CI，瀏覽器測試手動跑 | node 與 Playwright 都進 CI | HA 既有 | 加嚴（建議回補） |
| 77 | 帳本 | 沒有 | `docs/provenance/runtime-patches.json`、tool-surface 摘要；新模組全部列管（`ledger-tracking.md`） | HA 既有供應鏈規則 | 既有 |
| 78 | 秘密掃描與測試資料 | 沒有 builder 全歷史掃描 | builder 用 gitleaks 掃原始碼與全歷史、零容忍；`claude-delivery` 禁止 force push → 測試資料正規化、每片預檢 | 歷史改不掉 | 部署 |
| 79 | 上線後監看 | watch_fleet 唯讀監看全部服務 | 看不到客戶主機；只能對自營 HAOS 做唯讀檢查（範圍 HM-29 定） | 客戶自己更新 | 部署 |
| 80 | 手動指定 token | `PUT /api/tokens`（`set_token`）；撞號 409 `token_in_use`，不回顯值、不說是哪個帳號（Pc/routers/tokens.py:141-142；Pc/profiles.py:488-503） | 沒有這個 API：token 只由伺服器隨機產生，只能輪替與撤銷（Hc/gateway.py:582-606）；撞號只會來自還原或複製，回 503（第 2.3 節） | FM-31「不新增」；將來要加就照 PaaS 回 409，並同時擋目前與歷史 token | 既有 |
| 81 | 請求內容超過上限 | 最多再讀 128 MiB 丟掉才回錯誤，讓經反向代理的用戶端看得到錯誤、不是 RST（Pc/request_limits.py:16） | 一超過就 413（n8n 是 JSON-RPC 錯誤本體）、不再讀後面的內容（Hc/gateway.py:270-271；Hc/request_limits.py:51-70） | FM-52 延後：只在前面有 Cloudflare Tunnel 或反向代理時有感（HM-14 選做） | 既有 |
| 82 | 全部撤銷 | 沒有面板或 API；還原時照手冊撤銷全部（docs/paas-config-restore-runbook.md） | `POST {base}/api/profiles/revoke-all`（含預設帳號）＋`.revoke-all-pending`；逐帳號結果，寫入失敗的帳號 503、重啟時守門重做（第 2.3、3.1 節） | HA 沒有 shell 跑手冊；事故止血第一步、回退後再升級都要靠它（threat-model.md 第 4 節；§8.8 #69）；FM-120 | 加嚴（建議回補） |
| 83 | 管理請求帶兩個以上 `X-MCP-Profile` | 取第一個值（`request.headers.get`，Pc/profiles.py:612）；第一個值存在就照常服務 | 開通後 400 `profile_id_invalid`（在角色檢查後；第 3.3 節） | 一個請求只能對一個帳號，哪個值生效不該看中介層實作；fail closed（同 #31、#32；DQ-40 ①，DQ-17 細節待定） | 加嚴 |
| 84 | 帳號在別處被刪時的面板 | 等清單下次重抓才回 default，期間帳號範圍請求 404（依程式推論，R05 §6） | 任何帳號範圍請求回 `profile_not_found` 就立刻重抓清單、切回預設帳號並提示；被刪帳號的待確認收據明說並清掉（第 3.4 節） | 不讓下一個操作落到別的帳號、不留無法確認的收據（I12；FM-59） | 加嚴 |
| 85 | 用戶端範例的名稱 | 只給網址與 `claude mcp add --transport http my-<app>-mcp "<網址>"`；名稱不含帳號，同產品兩帳號照抄會撞名 | 今天是 `mcpServers` JSON、名稱固定 `woow`、帶 Bearer（Hui/contracts.js:319-321；§8.8 #2）；開通後名稱帶帳號 id 前 8 碼（例如 `woow-<產品>-<id 前 8 碼>`，暫定） | 同產品兩個帳號照抄不撞名；建議 PaaS 一起改（FM-63） | 待決（DQ-31） |
| 86 | 帳號範圍的管理操作與本體 | FastAPI 路由（`/api/settings/<section>`、`/api/tokens`、`/api/tools` 等），各自的本體與 ETag（Pc/config/store.py:276-289） | HA 既有管理契約的操作：`bootstrap`、`backend`、`policy`、`token/rotate`…（docs/management-capabilities-v1.md）、ETag `"c1-<64 hex>"`；開通後只加 `X-MCP-Profile`、回聲與帳號範圍（第 3.1、3.4 節）。帳號增刪改查的路徑、方法與欄位照 PaaS（FM-18、FM-19、FM-22） | HA 既有的單帳號契約，不因多帳號改寫；面板與 P9 kit 都照它 | 既有 |

## 10. 變更紀錄

| 版本 | 日期 | 片 | 內容 |
|---|---|---|---|
| v1 草案 | 2026-11-14 | HM-00 | 依計畫 §5、§6、§8.8 起草；套用 2026-11-14 的 §13.1 決策；差異表由 43 列補到 79 列 |
| v1 草案（審查修正） | 2026-11-14 | HM-00 | 依獨立審查修正：錯誤代碼表對齊 bb48449 與 PaaS pin（既有回應的五種本體形狀；補 `unsupported`、`backend_check_failed`、`backend_fixed` 三列與 415、第 ① 步的 400；`core_version_unreviewed` 在 ⑥／⑩；重複 `X-MCP-Profile` 的 PaaS 行為）；差異表補第 80～86 列；第 4.2 節補既有回應範圍；第 5 節加各產品上限；待定題目標示；隔離目錄刪除路由與讀 body 途中額度用完的回應（暫定）；第 6 節門檻寫法 |
