# 多帳號中立契約（v1，HM-00 起草）

- 狀態：HM-00 起草（2026-11-14）。HM-10 依實作補了第 3、4.1 節的細節（2026-11-15，見第 10 節）；HM-13b 補了第 1.3 節（開機守門）、第 3.5、3.6 節的還原收據與還原紀錄、第 7、8 節（2026-11-16），依獨立審查改第 1.3 節、#67、#119、#120（同日），rebase 到 `claude-delivery` 之後本片的列改成 #113～#116（同日），合併 `claude-delivery` `165dbaf` 之後改成 #118～#121（2026-11-17）；HM-13c 定案全部撤銷、還原紀錄、核對與刪除隔離目錄的路由（第 3.1、3.5、3.6、4.1 節），補第 1.2 節單帳號還原後的面板提示（使用者 2026-11-16 定案）、第 8 節單帳號的檔案與第 9 節 #117、#118（2026-11-17），合併 HM-13b 與 `claude-delivery` 之後本片的列改成 #122、#123（同日），並依審查 S-3 讓 HM-12 的換身分換 token 也過核對關卡、換了還原保留的權杖時清掉提示（第 1.2、3.1、4.1 節；同日）；HM-27 定案第 2.6 節的 Origin 清單與它的管理路由（第 3.1、3.2、3.5、4.1、4.2 節，第 9 節 #9、#10、#42 改寫並加列；2026-11-17），合併 HM-13c 之後本片的列由 #118～#122 改成 #124～#128（2026-11-18）；HM-18 定稿；合併順序 HM-00 → HM-10 → HM-18。
- 「中立」：PaaS `WOOWTECH/woow-mcp-server` 的行為（pin `69ac425`）是期望值；HA 和它不同的地方，每一條都列在第 9 節的刻意差異表
  （計畫 §8.8，下稱「§8.8 #n」），沒列的就要相同。FEATURE-MATRIX 每一列（含「HA 平台差異」欄是「—」的列）對到哪一列、
  或為什麼相同，見 `deviation-trace.md`。
- 來源：計畫 `PLAN-zh-TW.md` §2～§8（repo 外，`artifacts/ha-multiprofile-parity-20261114/`）。決策見 `decisions.md`；
  驗收見 `acceptance-matrix.md`；威脅模型見 `threat-model.md`。
- 標「暫定」的細節：計畫沒寫死、本檔先定一個做法，由括號裡的切片實作時定案；改了要同時改本檔。
- 路徑縮寫：`Hc/`＝HA `packages/mcp-admin-core/mcp_admin_core/`（bb48449）；`Hui/`＝HA `packages/mcp-admin-ui/src/`；
  `Pc/`＝PaaS `packages/mcp-admin-core/mcp_admin_core/`（@69ac425）；其他 PaaS 路徑相對 PaaS repo 根目錄。

## 0. 先講結論

1. 產品沒開通（不在 `MULTI_PROFILE_PRODUCTS`）而且磁碟上沒有帳號資料時，**8081 與 8099 的回應和今天逐位元相同**，本檔的新行為都不生效；例外只有第 1.2 節「不受開關管」的變更（例如直連子程式要帶 bearer、log 遮得更多、還原時多一個標記檔；HM-31 起，超過請求內容位元組預算、讀取閒置或 JSON 結構上限的請求被拒；HM-13c 起，還原後保留預設帳號權杖時多一個提示檔、bootstrap 多 `restore_notice`，到權杖變了為止）。
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
| 休眠帳號 | 產品沒開通、磁碟上卻有帳號資料時的額外帳號；開機在任何 listener 前撤銷 token（第 1.3 節） |
| 孤兒 | `profiles/` 底下有、索引沒有的 24 hex 目錄；不開、不路由、只能刪 |
| 隔離目錄 | `profiles/.quarantine-<id>-<UTC>/`（同一秒已有這個名稱就加 `-2`、`-3`…，不覆蓋；HM-13b）；還原守門讀不到的帳號改名放這裡；不路由、只能刪（HM-13c 定案：帳號清單另列 `quarantined`、`POST {base}/api/profiles/quarantine/<id>-<UTC>[-n]/delete`；第 3.1 節） |

### 1.2 開關與「不受開關管」

| 狀態 | 8081 | 8099 管理 API | 開機 |
|---|---|---|---|
| 沒開通、沒有帳號資料（＝今天） | 不掛分派器，回應逐位元同今天；密鑰網址不看 Origin 政策（HM-27：不讀不寫 `origin-policy.json`） | `/api/profiles*`、`/api/origin-policy` 404（未知操作）；不要求 `X-MCP-Profile`；管線順序同今天；還原後 bootstrap 只多 `restore_notice`（HM-13c，見下） | 還原標記記一行 WARNING、存還原提示（HM-13c）後刪除 |
| 沒開通、有帳號資料（休眠） | 只服務預設帳號 | 同上；bootstrap 只多 `dormant_profiles`（數字：守門之後還在的額外帳號目錄數，每一個的 token 都已撤銷；HM-13b；面板只顯示、沒有管理動作，HM-13c） | 撤銷每個還沒撤銷的額外帳號與孤兒的 token、重產 child_token；已撤銷的不動（I13；第 1.3 節） |
| 開通 | 分派器依 token 選帳號 | 第 3 節全部規則 | 還原偵測、守門、預設帳號、錯開起額外帳號 |

各產品下一版會帶出去、但 CHANGELOG 還沒記的變更（下面這些項目，加上各產品自己的修正）、每一項的 CHANGELOG 句子與發版時要另外驗的事，
見 `unreleased-changes.md`（計畫 §11.5；2026-11-17 起）。不受開關管的片合併時，在那裡加一項。

不受開關管（任何產品下一次發版都會帶出去；保證方式見計畫 §3.3）：紀錄遮罩（HM-02）、port 參數化（HM-04）、
執行套件抽出（HM-05）、子程式 bearer（HM-06）、資料層函式庫（HM-07）、收據格式（HM-11）、entrypoint 還原標記（HM-13a）、
開機守門的存在檢查與休眠處理（HM-13b）、子程式 initialize 錯誤的遮罩（HM-14，見下）、請求內容位元組預算與 JSON 結構守門（HM-31，見下）、
健康監看照停止要求停下（HM-09 追補，見下）、LiteLLM 與 EMQX 不保留閒置的後端連線（HM-32，見下；行為不變）、
Hermes 排程工具 `hermes_cron` 的說明補兩句（HM-33，見下；只改文字）、
單帳號還原後的面板提示（HM-13c，見下）、驗收與發版工具（HM-16、HM-17）。

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
  1. 宣告的 `Content-Length` 超過 64 KiB（16 MiB 以內）、放不進預算的請求：讀完丟掉（只留頭尾各 4 KiB），回 200＋`-32003`＋`Retry-After: 5`
     （頭尾認得出 id）或 503＋`-32003`、`id: null`；以前照常處理。
  2. 沒帶 `Content-Length`（或同時帶 `Transfer-Encoding`：這時 `Content-Length` 不算宣告，RFC 9112 §6.3）、讀到一半放不進預算的請求：停止讀取，
     回 200＋`-32003`（開頭認得出 id）或 503；以前照常處理。收到的位元組一律照數，宣告值不是上限（HM-31 審查 MF-1）。
  3. 重新序列化後要轉送給子程式的大小放不進預算：200＋`-32003`（有 id），子程式收不到；以前照常轉送。轉送的大小也扣：中文約 2 倍、emoji 約
     3 倍（份額 16 MiB 時，6 MiB 的 emoji body 轉送約 18 MiB，會被拒）。
  4. 已登記的大請求（宣告超過 64 KiB、沒帶長度，或帶 `Transfer-Encoding`）連續 30 秒沒有新位元組：408＋`-32003`＋`id: null`＋`Retry-After: 5`＋
     `Connection: close`；以前等到整體 60 秒才回 408 `{"error":"request denied"}`（整體 60 秒的回應照舊）。
  5. JSON 巢狀超過 64 層或元素（逗號＋容器）超過 20 萬個：200＋`-32602`（頭尾認得出 id）或 413＋`-32602`、`id: null`。以前：合法的 JSON 照常
     解析、照一般請求處理（政策、轉送；深到 Python 解析器遞迴上限的 400）；不是 JSON 的 400 `{"error":"request denied"}`，現在結構超過上限的先被
     守門拒收（例如 65 個沒關的 `[`、30 萬個逗號）。n8n：以前 413、`id: null`、「MCP JSON exceeds 64 levels of nesting」。
  6. 不是 UTF-8 的 body：413（或 200）＋`-32602`、編碼專用的訊息。以前：UTF-16／32（含它們的 BOM）照常解析、照一般請求處理；不合法的 UTF-8
     400 `{"error":"request denied"}`；n8n 400＋`-32700`。UTF-8 BOM 開頭的照舊放行（結構照樣檢查）。
  7. 上面每一種拒收與超過 16 MiB 的 413 各記一行節流的 WARNING（每帳號每情況 60 秒一行；只有情況、HTTP 狀態與不含內容的短原因）。
- 回應沒變、只是時機提早（HM-31 審查 MF-3）：宣告超過 16 MiB（而且沒有 `Transfer-Encoding`）的 body，改在讀第一個位元組之前就回今天的
  413 `{"error":"request denied"}`（以前讀到 16 MiB 才回；n8n 的 4 MiB 本來就在讀之前回）。不扣預算、不會變成可重試的 `-32003`（PaaS 不扣、
  回 413）。8099 管理 API 也經過同一段讀取（`gateway.body`），宣告超過 16 MiB 的同樣在讀之前回同一個 413。
- HM-01 的契約凍結逐案核對（`tests/contract/profiles_v1_cases.json` 的 99 案、黃金回歸、管理契約凍結）：**沒有一案的回應改變，凍結檔不用改**。
  理由：每一案的 body 都是 1 KiB 以內、合法 UTF-8、巢狀 4 層以內的 JSON（或沒有 body），全部 ≤64 KiB，不登記預算、不受閒置逾時，結構與
  編碼都在上限內；逐組（connect 2、error 46（含 order-）、unknown_token 8、header_switch 7、cross_profile 1、url_variant 31、token_change 4）的
  核對見 HM-31 筆記第 7 節。
- 測試：`tests/test_request_budget.py`、`tests/test_request_structure.py`、`tests/test_request_budget_gateway.py`（開關關與開兩種模式）；
  `tests/test_n8n_request_bounds.py` 的深度一案改成新回應。

**HM-09 追補的不受開關管變更：健康監看一定照停止要求停下**（2026-11-16；使用者 13:4x 定「全部產品都修」）

- 所有產品：健康監看在停止時一定停下（anyio 連線吃掉取消的競態；只改關閉，回應不變）。
- 缺口：每次健康檢查的請求都經 httpx 開新連線；anyio 4.15.1 的連線 task group 連上時取消自己的 scope，停止要求（收到 SIGTERM 時
  run_product 的 `monitor.cancel()`；開通後的 `_stop_monitors`、`remove()`）剛好在那一步之後、task 再跑之前到，就被併進 anyio 自己的
  `CancelledError` 吞掉。監看照常查下去，關閉一直等，直到 HA 的停止上限到了強制結束。開通後（HM-20 的端到端測試，PR #103 的 CI）
  每 0.5 秒查一次時遇到過；沒開通的單帳號每 15 秒一次檢查，同樣的競態機率低很多，但已發行的每個產品都有。
- 為什麼開關關時也改：今天就有、和多帳號無關的缺口；改了只讓關閉照要求完成。
- 改了什麼：`HealthMonitor.check()` 做完時，task 的 `Task.cancelling()` 比檢查前多（有停止要求沒以例外送到），就以 `CancelledError`
  結束。只影響停止時那次檢查之後的事；8081、8099 的回應、狀態碼、標頭、健康狀態與 log 都逐位元不變。
- HM-01 的黃金回歸與兩個契約凍結不用改，照過。
- 測試：`tests/test_monitor_cancel.py`（沒開通：ProfileRuntime 的監看、SIGTERM；開通：一次檢查的每條連線、讀取期限、`settle()`、
  rig 的取消、SIGTERM）。

**HM-32 的不受開關管變更：LiteLLM 與 EMQX 不保留閒置的後端連線**（2026-11-17；對齊 PaaS #135、#139，woow-mcp-server
`3c06b98`、`009dc99`）

- 決定：2026-11-17 02:3x 使用者決定現在就補，不等 HM-21、HM-23（`decisions.md` 第 1.1 節）；計畫 §12.3 HM-32。
- PaaS 的缺口：網路短暫中斷再恢復後，連線池裡看起來還活著的閒置連線，會讓恢復後的第一個請求等到讀取逾時。PaaS 把兩個產品的連線池
  改成不保留閒置連線（`max_keepalive_connections=0`），每個請求開新連線，不加重送。
- HA 今天的實際行為已經一樣（HM-32 實作時查到）：兩個產品的 client 都經 `backend_policy.async_client` 建立，它丟掉產品給的 `limits`，
  傳輸層自己的連線池固定 `max_keepalive_connections=0`。`lifespan.py` 寫的「保留 20 條、30 秒」（LiteLLM）與「保留 10 條」（EMQX）
  從來沒生效：每個請求本來就開新連線、重新解析名稱、重新檢查目的地。
- 改了什麼：兩個 `lifespan.py` 要的連線池改成不保留閒置連線（LiteLLM `max_keepalive_connections` 20 → 0、拿掉 `keepalive_expiry=30.0`；
  EMQX 10 → 0），和實際生效的值、PaaS 一致；`backend_policy` 以後若改成採用呼叫端的 `limits`，也不會把閒置連線帶回來。不加重送；逾時、
  `trust_env`、轉址與代理拒絕、DNS 釘選、目的地檢查（含 HM-20 的 loopback 拒絕）都沒動。
- 改了什麼回應：沒有。8081、8099 的回應、狀態碼、標頭，後端收到的請求與連線都逐位元不變（實際生效的連線池沒變）。
- 為什麼不受開關管：和多帳號無關；只改這兩個產品自己的檔，跟著它們的下一版出去。
- HM-01 的黃金回歸與兩個契約凍結不用改，照過。
- 測試：`tests/test_fresh_backend_connections.py`（兩個產品 × 兩種連線池：子程式實際建的、照產品要的 `limits` 建的。每個請求各解析一次、
  各開一條連線；名稱改指被拒的位址後，下一個請求在連線前就被拒；恢復後第一個工具呼叫不碰舊連線、不等逾時；不重送）。

**HM-33 的不受開關管變更：Hermes 排程工具 `hermes_cron` 的說明補兩句**（2026-11-17；對齊 PaaS #156，woow-mcp-server `34769c2`，
合併 `48f394d`）

- 決定：2026-11-17 06:3x 使用者決定現在就補（`decisions.md` 第 1.1 節）；計畫 §12.3 HM-33。
- PaaS 的缺口：說明只寫「create: new job (requires name, schedule, prompt)」「trigger: run job now (requires job_id)」，沒寫兩件實際行為。
  一是 create 帶 `enabled=false` 會建成停用的排程，resume 之前不會跑。二是 Hermes v0.22.x 對停用的排程執行 trigger 時，會一併把它改回啟用；
  要維持停用，之後要再呼叫 pause。第二件是 PaaS 2026-11-16 用真 Hermes Agent v0.22.5（PaaS 正式站的映像）實測的，直接呼叫 Agent API 也一樣，
  屬於上游行為。HA 的說明和 PaaS 修正前逐字相同，也沒有這兩句。
- 改了什麼：`apps/hermes/vendor/hermes_mcp_server/server.py` 的 `hermes_cron` 說明照 PaaS 逐字補這兩句（docstring 的換行也一樣）；閘道內附的
  工具清單（`tool_snapshot.py`，沒有子程式能回答時用它回 tools/list）跟著改同一段說明。
- 改了什麼回應：只有 `hermes_cron` 的 `description` 多這兩句：8081 的 tools/list（子程式自己的回答、閘道轉回的回答、閘道自答的回答都一樣；
  整個回答多 187 個位元組，`Content-Length` 跟著變），以及 8099 `/api/capabilities` 工具目錄的同一個欄位（管理面板的工具頁顯示它）。
  工具名稱、輸入與輸出 schema、annotations、寫入權限、tools/call 的請求與回應都逐位元不變。程式行為不變：去掉 docstring 後的語法樹和
  改之前相同，編譯後也只有這段說明的常數不同。這些只說本片；同一個 Hermes 下一版另帶 PR #85 的 create 請求改變（見下一點）。
- 說明和程式一致：`claude-delivery` 的 create 在同一個 POST 同時送 `paused`（`not enabled`）與 `enabled`（PaaS #138；
  `tests/test_hermes_cron_paused_contract.py`）。這是 PR #85（`b50f1c7`，2026-11-12 合併）的行為，**還沒發版**：發行的 Hermes 0.4.13 只送
  `enabled`，跟著 Hermes 下一版出去（HM-33 審查 MF-1、S-2）。trigger 是一個 `POST /api/cron/jobs/<id>/trigger`，子程式不會自己再 pause、
  resume 或再 trigger 一次（`tests/test_hermes_cron_description.py` 的 trigger 一案；HM-33 審查 S-1）。
- 為什麼不受開關管：和多帳號無關；只改 Hermes 自己的說明，跟著 Hermes 的下一版出去。
- HM-01：黃金回歸的 Hermes 兩個 tools/list 摘要（`LISTING_SHA256`、`LISTED_SHA256`）照測試檔頭的規則一起更新（刻意的工具表面變更：
  `tool_snapshot.py` 改了）；新的回答就是舊的回答只換掉這段說明（逐位元核對過）。兩個契約凍結不用改，照過。
- 測試：`tests/test_hermes_cron_description.py`（子程式自己的 tools/list 與閘道內附的清單都逐字是 PaaS 的說明；拿掉這兩句就是原本的說明；
  trigger 只送一個 POST，自己不會再 pause 或 resume）。

**HM-13c 的不受開關管變更：還原後保留預設帳號權杖時的面板提示**（2026-11-16；使用者對 HM-13b 審查 Q-1 的定案）

- 決定：2026-11-16 21:xx 使用者選「照 DQ-03 原文補面板提示」（DQ-03 (b)：單帳號安裝的還原行為和今天一樣，面板與 log 提示
  「權杖已回到備份當時的值」）。使用者只核准一個代價：所有產品下一版的 bootstrap 多一個欄位，單帳號回應會變；契約與單帳號凍結測試
  逐案寫理由，各產品 CHANGELOG 記一行（交發版片）。開關關時不加任何管理路由（計畫 §8.4 休眠處理那條的原則）。`decisions.md` 第 1.1 節。
- 缺口：HM-13b 起，沒開通又沒有帳號資料的安裝還原後只記一行 WARNING；管理員多半不看 add-on log，MCP 用戶端連不上（它用的是備份後才
  輪替的新權杖）時不知道原因，備份後才撤銷的外洩權杖也在不知不覺中復活。
- 做法（接在 HM-13b 的守門上）：守門看到還原、而且預設帳號的權杖沒有撤銷（沒有帳號資料；開通與否都一樣）時，在刪還原標記**之前**存
  `/data/mcp/restore-notice.json`：`{"version":1,"at":"<還原當下，UTC 秒>"}`，沒有任何秘密；暫存檔＋fsync＋replace＋目錄 fsync、0600、
  本程序的 uid（同其他 `/data/mcp` 檔）；名稱被目錄占用時照 #120 移開；不碰 sentinel。中途斷電時標記還在，下次開機重存。沒開通又沒有
  帳號資料時存不下也照常啟動（標記留著、多記一行，下次再存；同標記刪不掉）；其他情況和守門的其他寫入一樣停下。撤銷預設帳號的還原、
  開機補完的全部撤銷會刪掉舊提示（備份裡帶回的、或之前留下的：已不成立）。沒有選擇重用 `restore-record.json`：它的格式是給開通後的
  核對卡（每列身分欄位與政策），單帳號只需要時間；而且 HM-13b 定了單帳號還原不寫它（容器探針也這樣驗）。
- 怎麼消失：預設帳號的權杖變了就刪（`token/rotate`，或真的撤銷了的 `token/revoke`；開通後的全部撤銷、HM-12 換身分換了這把權杖也刪，後者是和 HM-12 合併時補的）；檔刪不掉時記一行，重開後會
  再出現到下一次權杖變更。面板的「知道了」只在這個頁面的記憶體裡藏（重新整理會再出現）：面板不用任何瀏覽器儲存（N15、DQ-18；
  `packages/mcp-admin-ui/tests/build-closure.mjs` 擋 `localStorage`），要「這個瀏覽器記住」得放寬這條不變式，是另一個決定。
- 改了什麼回應（單帳號，逐項）：
  1. 還原後（直到權杖變了）的 bootstrap 多一個鍵 `restore_notice`（`{"at":…}`），接在最後；其他每個鍵與值照舊。
  2. 其他回應一個位元組都不變；`token/rotate`、`token/revoke` 的回應照舊，只多一個副作用（刪提示檔）。
  3. 權杖不撤銷（同今天）；收據照還原的原樣（#121）。
  4. 磁碟：還原後多 `restore-notice.json`，到權杖變了刪掉。計畫 §3.3、§7.1「單帳號安裝一個新檔都不產生（只有還原時 entrypoint 多一個
     標記、開機就刪）」多這一個例外。
- 沒有還原的安裝（每個安裝的平常開機）：開機只多查一個名稱（`restore_lock.read_notice`；沒有就什麼都不讀、不寫，連 ctime 都不變）；
  沒有提示時不建任何提示物件，bootstrap 與其他回應、磁碟都和今天逐位元相同。
- HM-01 的凍結：黃金回歸（`tests/test_single_profile_golden.py`）、兩個契約凍結（`tests/test_admin_contract_freeze.py`、
  `tests/test_mcp_contract_freeze.py`，`tests/contract/profiles_v1_cases.json`）都沒有「備份還原」的案例（`owner-defaults/restore` 是另一件事），
  所以**沒有一案要改**，照過就是「沒還原逐位元不變」的證明。還原的案例在 `tests/test_restore_review.py`（八個產品各一案：同一份資料
  還原與否，bootstrap 只差 `restore_notice`、其他鍵值相同、權杖兩條接法都通）與 `tests/test_restore_lock.py`（HM-13b 的單帳號還原那案
  改成「只多提示檔」，理由寫在測試裡）。
- 測試：`tests/test_restore_review.py`（存、讀、存不下、中途停、被目錄占用、輪替與撤銷後消失、沒還原時不建）、
  `tests/browser/restore-review.spec.mjs`（面板）。

### 1.3 開機守門（HM-13b 定案；不受開關管；計畫 §8.4）

- 位置：`run_product` 與 `apps/n8n/run.py` 每次開機在 legacy 遷移與預設帳號的 store 之後、任何子程式與 listener 之前跑
  `restore_lock.guard`。失敗一律 `ConfigError`：什麼都不服務（`runtime unavailable`）、標記都保留，下次開機重跑。
- 觸發：還原（HM-13a 的訊號 1 標記或訊號 2 sentinel）、`.revoke-all-pending` 存在（任何種類的項目都算）、休眠（沒開通但有帳號資料，每次開機）。
- 沒開通、沒有帳號資料（今天的每個安裝）：只查四個名稱、什麼都不寫（HM-13c 起 `run_product` 另查一個名稱：還原提示）。遇到還原：記一行
  WARNING（權杖已回到備份當時的值，DQ-03 (b)）、存還原提示（HM-13c，第 1.2 節）、刪標記，其他一個位元組都不動；提示存不下或標記刪不掉
  也照常啟動、多記一行（沒有帳號資料，沒有東西要撤銷），標記留到下次。
- 範圍 S：預設帳號、`profiles/` 底下每個 24 hex 目錄（索引內、孤兒、索引壞都算；索引只拿來顯示名稱）、既有的隔離目錄（只讀 token 進快照）；
  其他名稱只記數量。`profiles` 不是目錄（一般檔、連結）時裡面沒有東西能開或路由，照第 9 節 #119 繼續；`profiles` 是目錄（或查不出是什麼）
  卻一時列不出來（EMFILE、ENFILE、ENOMEM、EIO、權限、別的 uid）時，裡面可能還有備份裡的 token：守門沒做完（`not finished (the profiles
  directory cannot be listed)`），標記都留著、什麼都不服務，下次開機列得出來才做完（HM-13b 審查 MF-2）。步驟照計畫 §8.4 A～F：快照 → 預設帳號（有帳號資料才撤銷並重產 child_token、封存收據；沒有就原樣保留）→ 每個帳號目錄
  （撤銷、重產 child_token、封存收據；開不了的改名隔離，但 writer lock 被別人拿著的只算失敗、不搬）→ 索引旁與 Origin 政策旁（HM-27）的收據封存 →
  `restore-record.json`（第 3.6 節）→ 獨立驗證（從磁碟重讀，不經寫入的 store）→ 重建 sentinel 與 record → 刪 `.revoke-all-pending`、最後刪還原標記。
  每一步都能中途斷電後重做（冪等；見第 9 節 #118）。
- 休眠：每次開機撤銷還沒撤銷的額外帳號與孤兒（已撤銷的不寫任何東西）；開不了的隔離；預設帳號不動（同時偵測到還原時照上一點）。有撤銷或隔離時
  寫 `restore-record.json` 的休眠段落並記一行 WARNING；上一份紀錄還在等的核對不丟（預設帳號那一列、還原段落），上一份讀不到就不改它
  （第 3.6 節；HM-13c 審查 MF-1）。
- 全部撤銷（HM-13c 的路由 `POST profiles/revoke-all` 用；`restore_lock.revoke_all`）：先寫 `.revoke-all-pending`（fsync），逐帳號撤銷（含預設；預設帳號 → 帳號目錄依 id），
  獨立驗證（前面有沒有失敗都跑：store 說成功、磁碟沒變的也算失敗），全部成功、`profiles/` 也列得出來才刪標記；任一失敗或驗證不過就留標記、
  回傳逐帳號結果（`revoked`、`failed`、`quarantined`）。開機看到標記就在 listener 前做完，不看開關。呼叫端（執行中的管理器）要把它拿著的
  store 傳進來（只收額外帳號）：`profiles/` 列不出來時這些照樣撤銷、逐一列進結果，但 `finished=false`、標記留著，下次開機補完。呼叫端要拿著
  `ProfileAdmin.lock`（建立、刪除、索引隔離都拿的那把鎖）與每個已登錄帳號的鎖，並在執行緒裡呼叫（同步、每帳號兩次寫入與 fsync）。HM-13c 的
  路由照做（另拿預設帳號的鎖），之後每個帳號 `TokenAccess.committed()`、撤銷了的重起子程式（新 child token），沒做完時失敗帳號的舊權杖在
  8081 回 503（第 4.2 節）。還原時守門處理的每個收據檔都換新（HM-13c，第 3.5 節）；撤銷預設帳號時刪掉還原提示（第 1.2 節）。
- 守門自己的名稱（sentinel、record、record 暫存檔、兩個標記、`restore-record.json`、收據封存 `.state.json.operations.json.restored` 與
  `.profiles.json.operations.json.restored`，HM-27 起加 `.origin-policy.json.operations.json.restored`）被目錄占用（偽造的備份）時改名放到
  `<名稱>.quarantine-<UTC>[-n]`，不刪（HM-13a 審查 SF-7；`restore-record.json` 與前兩個收據封存是 HM-13b 審查 S-1 補的）。
- Origin 政策（HM-27，和 HM-13b、HM-13c 合併後；第 2.6 節）：`origin-policy.json` 不是守門的名稱、不含憑證，守門從不開、不改名、不刪：
  還原把它照備份當時的樣子帶回來（存過的、沒有、不能用的都一樣，開機照常做完；開通的產品服務時政策照它，不能用就密鑰網址 503）。
  它旁邊的收據檔 `.origin-policy.json.operations.json` 照索引旁的收據封存（第 3.5 節）；封存不了（例如收據檔是目錄、旁邊的封存名稱是檔案）
  就記 `the operation receipts beside the Origin policy could not be archived`、這次開機停下，同索引旁的收據。沒開通、沒有帳號資料的還原
  照上面只存提示、刪標記，政策檔與收據檔都照還原的原樣（同 #121 預設帳號的收據）。
- log：logger `mcp_admin_core.restore_lock`，一律 WARNING，固定文字，帳號只寫 id 前 8 碼（第 7 節）。

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
   - 扣什麼：大請求（宣告的 `Content-Length` 超過 64 KiB，或沒帶；帶 `Transfer-Encoding` 時 `Content-Length` 不算宣告，RFC 9112 §6.3，HM-31
     審查 MF-1）的請求內容，取「收到的」與「轉送給子程式的」兩者較大的；兩者都 ≤64 KiB 的小請求不扣、也不會被預算拒絕（PaaS）。宣告的長度在讀
     第一個位元組之前就扣，收到的位元組也一律邊讀邊數（宣告值不是上限）；宣告超過單一請求上限（16 MiB，n8n 4 MiB）的在讀之前就回今天的 413、
     不扣（HM-31 審查 MF-3）；沒宣告、讀超過上限的也不扣（照舊回 413）。
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
| 大請求宣告的 `Content-Length`（16 MiB 以內、沒有 `Transfer-Encoding`）放不進預算（帳號的份額或全 add-on 的預算） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003`（哪一層預算已滿；PaaS 原文） | 讀第一個位元組前就拒絕，內容讀完丟掉，只留頭尾各 4 KiB 找 id（PaaS `_refuse_over_budget`：先送完內容才讀回應的用戶端看得到回應，不是連線重設）；丟的時候用戶端離開回 499（沒有人收得到）；閒置 30 秒或整體 60 秒就不再等、照樣回答。子程式收不到 |
| 沒帶 `Content-Length`（或帶 `Transfer-Encoding`），讀到一半放不進預算 | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003` | 立刻停讀、已扣的還回去，id 從已讀到的開頭找（PaaS N5）；子程式收不到。收到的位元組一律照數：同時帶 `Content-Length` 與 `Transfer-Encoding: chunked` 的請求，h11 0.16.0 照 chunked 讀、把 `Content-Length` 原樣交給 app，閘道當成沒宣告（HM-31 審查 MF-1；§9 #108） |
| 宣告的 `Content-Length` 超過單一請求上限 16 MiB（沒有 `Transfer-Encoding`） | 413 | `{"error":"request denied"}`（今天的回應） | 讀第一個位元組之前就回，不扣預算、不會變成可重試的 `-32003`（HM-31 審查 MF-3；PaaS 不扣、413）；n8n 的 4 MiB 本來就在讀之前回自己的 413 |
| body 已讀完，閘道重新序列化後要轉送的大小放不進預算（非 ASCII 內容；第 2.2 節第 4 點） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003` | HM-08 審查 S-1 起；子程式收不到這個請求；WARNING 和「位元組預算」同一種情況 |
| 已登記的大請求（宣告超過 64 KiB、沒帶，或帶 `Transfer-Encoding`）讀取中連續 30 秒沒有新位元組 | 408，`Retry-After: 5`，`Connection: close` | `-32003`，`id: null` | 放棄這個請求、已扣的還回去（PaaS P2-D）。整體讀取上限仍是今天的 60 秒（`BODY_SECONDS`，每個請求都有；PaaS 300 秒、只有登記的大請求）：到了照今天回 408 `{"error":"request denied"}`（§9 #105） |
| POST 的 JSON 巢狀超過 64 層、元素（逗號＋容器，字串內的不算）超過 20 萬個，或不是 UTF-8（UTF-16／32、BOM、不合法的 UTF-8） | 頭尾認得出 id 200，否則 413 | `-32602`，訊息只寫哪一項超過或「不是 UTF-8」，不含內容 | 在解析之前、只掃描結構字元（`request_limits.structure_violation`、`not_utf8`；PaaS 原樣）；n8n 先跑同一道守門再跑自己的上限；子程式收不到 |
| 轉送名額等 1 秒逾時（body 已讀），有 id | 200，`Retry-After: 5` | 每個 id 一則 `-32003` | #148 形狀（開通的產品 HM-08 起；HM-14 定案：一般名額與保留名額各自計時、文字寫那一組自己的條數） |
| 轉送名額等 1 秒逾時，沒有 id（GET、DELETE、保留名額也用完的通知） | 503，`Retry-After: 5` | `-32003`，`id: null` | 同上 |
| 排隊已達上限（每個佇列各自計數：一般名額 32／16 個、保留名額另 32／16 個） | 有 id 200、沒有 id 503，都帶 `Retry-After: 5` | `-32003`（排隊的文字） | 不等、不排隊、不送出；WARNING 每帳號每情況 60 秒一行（HM-14） |
| 排隊時用戶端關閉連線（那個請求的連線被關掉） | （沒有人收得到：程式內部回 499，伺服器不送給已離開的用戶端） | — | 請求從排隊移除、絕不送出；名額剛好同一刻空出時也還回去、不送；只記 WARNING（HM-14） |
| GET 串流已達上限 | 429，`Retry-After: 30` | `-32003`，`id: null` | 預設帳號 24 條、額外帳號 8 條 |
| 該帳號待送回覆位元組已達上限（還沒被 server 收走的回覆；第 5、6 節） | 200，`Retry-After: 5` | 新的 tools/call 在轉送前回 `-32003`（帶它的 id） | 只在開通的產品。HM-30 定案：只擋 tools/call（其他方法照常轉送）；在轉送名額與 HM-14 的排隊之前判斷、不等（被擋的不先排隊）；已轉送的回覆一律處理並交出（軟上限，最壞值見第 5 節；使用者 2026-11-16 定 D2 (a) 接受）；WARNING 每帳號 60 秒一行 |

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
    一定送到（`tests/test_carries_no_request.py::test_a_newly_connected_clients_initialized_reaches_the_child_with_the_queue_and_admission_full`、
    `tests/test_carries_no_request.py::test_the_reserve_is_reached_even_once_the_profiles_admission_is_full`）。
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

### 2.6 Origin（DQ-11 採 (a)，HM-27 定案）

開通的產品才有（`features.enabled`；HM-27 的 `Hc/origin_policy.py`）；沒開通照今天：密鑰網址接受任何 Origin、不記錄，
Headscale 只放 `https://claude.ai`（第 1.2 節）。

- **Bearer `/mcp` 帶 Origin**：一律 403（同今天；§8.8 #10）。不記錄、不看政策。DQ-11 第二問（Claude.ai 送 `https://claude.ai`
  時要不要精確放行）待 S14 實測後交使用者決定（HM-03b／HM-19b），HM-27 沒有放行。
- **密鑰網址**：全 add-on 一份服務層級政策（所有帳號共用，不分帳號；FM-73）。
  - 存在 `/data/mcp/origin-policy.json`（不進預設帳號的 state）：剛好 `{"version":1,"mode":…,"allowed_origins":[…]}`，
    0600、單一連結的一般檔、本 uid、16 KiB 以內；`mode` 只能是 `report-only` 或 `enforce`；來源最多 16 個、正規化後的寫法、
    不重複。沒有檔案時＝`report-only`＋`["https://claude.ai"]`（PaaS chart 0.1.10 的預設），**面板存檔之前不寫任何檔**
    （例外只有還原：開通或有帳號資料的產品還原後，開機守門換新收據檔，政策檔照樣不寫；見下面「還原」）。
    收據在旁邊的 `.origin-policy.json.operations.json`。
  - 位置：token 驗過之後、方法檢查（405）之後、query 檢查（400）之前，也就是今天 Headscale 規則的位置（§8.8 #124）。錯 token
    照今天 404，碰不到政策、也寫不出紀錄。
  - 通過：沒帶 Origin，或剛好一個、正規化後在清單內（照 PaaS `normalize_origin`：只認 ASCII，scheme 與主機轉小寫、去掉預設
    port；`*`、`null`、路徑、尾端斜線或點、帳密、query 都不是來源）。IPv6 主機寫成 RFC 5952 的十六進位（瀏覽器 Origin 用的
    WHATWG 寫法；IPv4-mapped 也是 `::ffff:7f00:1`，不寫點分）：Python 的 `str()` 在較新的版本把 IPv4-mapped 寫成點分（本機實測：3.12.14、3.13.2 起是點分，3.11.2、3.12.3 是十六進位），
    正規寫法不能跟著映像的 Python 變（PaaS 用 `str()`；HM-27 審查 S-9）。
  - **改正規化規則要遷移舊檔**：存檔與讀檔用同一個正規化，檔內每個來源都要是它的正規寫法。之後哪一版改了正規化規則，要在讀檔前
    把舊檔遷移成新寫法，否則存過的檔會變成壞檔，全部密鑰網址 503（HM-27 審查 S-9）。
  - 不通過（清單外、畸形、`null`、兩個以上）：`report-only` **照常服務，回應逐位元不變**，記一行 `decision=would_deny`；
    `enforce` 回 403 `{"error":"request denied"}`（閘道固定本體，同 Bearer 與 Headscale；PaaS `{"detail":"ORIGIN_DENIED"}`，
    §8.8 #125），子程式收不到，記一行 `decision=deny`。
  - **不加任何 CORS 標頭**（FM-74；兩種模式都是）；OPTIONS 照今天在 token 之後回 405，沒有 preflight 回答（§8.8 #42）。
  - 紀錄（WARNING，`mcp_admin_core.origin_policy`）：`MCP gateway [profile=<id 前 8 碼>]: an Origin the secret path does not
    allow (report-only: served as usual) decision=would_deny mode=report-only reason=<not_allowed|malformed|duplicate|null>
    origin="<…>"`（`enforce` 是 `(enforce: refused, 403) decision=deny mode=enforce`）。`origin` 照 PaaS 的呈現規則：正規化的
    `scheme://host[:port]`；畸形的只記它的 `scheme://host[:port]` 與有哪幾段（`(has=userinfo+path+query+fragment)`），否則只記摘要
    （長度與字元類別），一律可印 ASCII、120 字以內；**不記路徑、token、query、其他標頭與內容**。每帳號每個（判定、原因、來源）
    60 秒一行、每帳號每分鐘最多 20 行，壓下的行數在下一行之前或時間窗結束時補一行 `Origin lines held back suppressed=N`
    （PaaS 是整台一份：§8.8 #127）。紀錄寫不出來不影響回應。
  - 政策檔不能用（不是上面的格式、模式錯、來源不是字串、重複或超過 16 個、權限不是 0600、是連結、硬連結、FIFO、目錄、別的 uid
    的、超過 16 KiB、讀不到）：**所有帳號**的密鑰網址上每個驗過 token 的請求（帶不帶 Origin 都一樣，包括不帶 Origin 的 Claude.ai）
    回 503 `{"error":"state unavailable"}`，直到面板存一份新的蓋過去；Bearer 與 `/health/ready` 不受影響。存檔是換名蓋過去：
    目錄這類換名蓋不過去的東西，存檔回 409 `operation_outcome_unknown`，只能還原備份。開機與之後
    每換一次檔案狀態記一行 WARNING（不含檔案內容）。每個這種請求看一次檔（lstat），檔案換了就重讀：有效的替換立即生效
    （同 HA 其他 state，§8.8 #46）。PaaS 壞值啟動失敗、執行中 503（§8.8 #126）。
- **Headscale**：密鑰網址維持只放 `https://claude.ai`（enforce，原字串比對、不記紀錄，同今天；§8.8 #9）；沒有政策、不讀這個檔。
  開通後 `/api/origin-policy` 的 GET 與形狀正確的 PUT 回空本體 404（和未知操作逐位元相同，在角色檢查之後）；其他方法在第 ⑤ 步回
  405 `Allow: GET, PUT`，形狀錯的 PUT 回 400（⑤ 不讀狀態，非管理員也只看到固定位元組；HM-27 審查 S-5）。HM-26 開通 Headscale 前
  決定照這樣寫定，或讓 Headscale 的方法表不含這條路由。
- **開通之後又關掉**（產品移出 `MULTI_PROFILE_PRODUCTS`，計畫 §7.4 的緊急關閉）：政策檔留著、不讀，密鑰網址回到今天（任何
  Origin 都放行、不記錄），enforce **靜默失效**；再開通又照檔生效（HM-27 審查 S-6，交 HM-18 寫進 DOCS）。
- **還原**（HM-13b 的開機守門，第 1.3 節；HM-27 和 HM-13b、HM-13c 合併時定）：政策檔照備份當時的樣子回來，守門不讀不改：備份之後
  才切的 enforce 或改的清單，還原後回到備份當時的值（存過的照它、沒有就是預設、不能用就密鑰網址 503），**沒有另外的提示**（威脅模型
  第 3 節）。收據檔照索引旁的封存：還原前（含備份之後、隨還原消失）的存檔 id 重送一律 410 `operation_restored`（第 3.5 節）。
- 管理路由見第 3.1、3.5 節（`{base}/api/origin-policy`）。

### 2.7 回覆遮罩與不讀的東西

- 回覆遮罩＝本帳號 `secret_values(state)` ∪ **所有帳號**（含預設、孤兒、休眠）目前的 token 與 child_token；後端密碼仍只用本帳號
  （§8.8 #38，DQ-40 ⑧）。
- 8081 永遠不讀 `X-MCP-Profile`、cookie、query 來選帳號；密鑰網址上絕不改看 `Authorization`（I1）。

## 3. 管理（8099）

### 3.1 路徑與方法

**全域路徑**（不看 `X-MCP-Profile`；開通後才存在，沒開通 404）：

| 路徑 | 方法 | 用途 | 寫入保護 | 成功回應 |
|---|---|---|---|---|
| `{base}/api/profiles` | GET | 帳號清單 | — | 200 `{"profiles":[列…],"orphans":[{"id"}…]}`（孤兒：`profiles/` 底下有、索引沒有的帳號目錄，列出可刪；HM-10）；有隔離目錄時另帶 `"quarantined":[{"name":"<id>-<UTC>[-n]","id"}…]`（依名稱排序，沒有就不帶這個鍵；HM-13c）；`ETag: "p1-<64 hex>"`（索引 ETag） |
| `{base}/api/profiles` | POST | 建立 `{"label":…}` | If-Match（索引）＋Idempotency-Key | 201 該列（**不含 token**）＋`operation`；同一 key 重送回 200＋目前那一列＋`operation`（`replayed:true`；帳號已被刪掉時只回 `{"id","operation"}`；HM-10） |
| `{base}/api/profiles/<id>` | PATCH | 改名 `{"label":…}` | If-Match（索引） | 200 該列 |
| `{base}/api/profiles/<id>` | DELETE | 刪除（含孤兒與讀不到的帳號；DQ-14 已定（2026-11-15 17:4x 使用者採用建議）：先撤銷 token 並抹掉後端憑證再刪、孤兒不自動刪、面板列出可刪、不做軟刪除、兩段確認在面板（HM-11）） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<id>","operation":…}`；重送同 |
| `{base}/api/profiles/revoke-all` | POST | 全部撤銷（含預設） | If-Match（索引；索引不能用時是壞索引的 ETag，bootstrap 的 `profile_index_etag`：緊急止血，索引壞也能用）＋Idempotency-Key | 200 `{"revoked":"all","results":[{"id","result":"revoked"}…],"operation":…}`（預設帳號先，再依 id；HM-13c）；同一個 key 重送 200 `{"revoked":"all","operation":…}`；有失敗見第 4.1 節 `operation_outcome_unknown`。還原紀錄讀不到或不是守門寫的形狀時，做完的全部撤銷會重寫一份（每個帳號 `revoked`、`reviewed_at: null`，沒有還原與休眠段落；第 3.6 節；HM-13c 審查 S-2） |
| `{base}/api/profiles/restore-record` | GET | 還原與休眠核對紀錄（不含秘密） | — | 200 `{"record":<第 3.6 節的紀錄>\|null}`、`ETag` 是索引的（索引不能用時是壞索引的，同 bootstrap 的 `profile_index_etag`）；索引壞也能用；紀錄讀不到或不是守門寫的形狀 503 `{"error":"state unavailable"}`（HM-13c；出路：全部撤銷做完會重寫紀錄，第 3.6 節） |
| `{base}/api/profiles/<id>/restore-review` | POST | 標記「已核對」 | If-Match（索引）＋Idempotency-Key | 200 `{"reviewed":"<id>","reviewed_at":"<UTC 秒>","operation":…}`；已核對過的照舊回第一次的時間；同一個 key 重送同（HM-13c 定案） |
| `{base}/api/profiles/index/quarantine` | POST | 隔離不能用的帳號索引（壞掉或被外改；DQ-12） | If-Match（壞索引的 ETag，bootstrap 的 `profile_index_etag`）＋Idempotency-Key | 200 `{"quarantined":"<改名後的檔名>","operation":…}`；重送同；索引能用時 409 `config_conflict`（HM-10） |
| `{base}/api/profiles/quarantine/<名稱>/delete` | POST | 刪除一個隔離目錄（`<名稱>`＝目錄名去掉 `.quarantine-` 的 `<id>-<UTC>[-n]`；同一個 id 可能有多個） | If-Match（索引）＋Idempotency-Key | 200 `{"deleted":"<名稱>","operation":…}`；重送同；不存在 404 `profile_not_found`；照刪除的規則（DQ-14）：讀得到的先撤銷權杖、抹憑證，再從驗過的 `profiles/` 往下刪、不跟隨連結（HM-13c 定案） |
| `{base}/api/origin-policy` | GET | 密鑰網址的 Origin 政策（全 add-on 一份；HM-27，第 2.6 節） | — | 200 `{"mode","allowed_origins","origin_policy_state"}`（`default`：沒有檔案；`saved`；`unusable`：檔案不能用，`mode`、`allowed_origins` 都是 `null`）；`ETag: "o1-<64 hex>"`。Headscale：未知操作（404，沒有本體） |
| `{base}/api/origin-policy` | PUT | 存政策 `{"mode":…,"allowed_origins":[…]}`（剛好這兩個鍵，第 ⑤ 步驗形狀） | If-Match（政策）＋Idempotency-Key | 200 存下的政策（正規化後）＋`origin_policy_state:"saved"`＋`operation`（`kind` `origin.policy`）；同一個 key 重送回 200＋目前的政策＋`operation`（`replayed:true`）。Headscale：404 |
| 頁面與靜態檔 | GET、HEAD | 面板 | — | 同今天（開通後改由預設帳號的動作回，多一次角色檢查；PUT、POST 照今天 404，PATCH、DELETE 照今天 405 的位元組，但在 identity 之後；HM-10） |

**帳號範圍路徑**（其他 `{base}/api/*`；開通後一定要剛好一個 `X-MCP-Profile`）：

| 操作 | 方法 | 開通後的變化 |
|---|---|---|
| `bootstrap` | GET | 多 `profile`、`profiles_supported`；預設帳號另帶索引狀態、休眠與還原通知（第 3.6 節） |
| `configuration`、`capabilities` | GET | 回應帶 `profile:{id}` |
| `diagnostics` | GET | 只回選定帳號的子程式緩衝 |
| `operations/<id>` | GET | 收據依帳號 |
| `backend`、`backend/patch` | PUT | Odoo 的 token 綁一個後端身分（HM-12；DQ-05 已定，照計畫 §9；Nextcloud、Hermes 由 HM-22、HM-24 接）：token 有效、已存的連線完整，而這次存檔讓 url、database、username 任一改變（含 `{"connection":null}` 清空：不換的話，先清空、再存別的帳號就成了初次設定，舊 token 會留下來）時，依序 ① 先停舊子程式（丟掉它的 spec，之後只有重起才會再起它）② 一次寫入新連線＋新 token＋一筆 history（`rotate`，§8.8 #59）③ 發布 token 變更（`TokenAccess.committed()`：舊 token 進行中與排隊等名額的請求立刻結束，兩條入口都照「沒有帳號持有的 token」回 401／404；8081 分派器照 state 檔簽章重讀，舊 token 不再對到任何帳號，帳號自己的 app 也再驗一次：兩層都拒絕）④ 在寫入的 state 上起新子程式；回 200 `{"saved":true,"token_rotated":true,"configuration":…}`（＋回聲；不含 token，新 token 照舊經 `token/reveal` 取得；`ETag` 是新 state 的，面板下一次存檔直接拿來當 If-Match）。只換密碼、初次設定、token 已撤銷：照今天（先寫入再重起，不換 token，回應沒有 `token_rotated`）。失敗（§8.8 #114）：舊子程式停不下來 → 什麼都不寫、用舊 state 重起子程式、503 `{"error":"request denied"}`。寫入失敗一律照今天回 503 `{"error":"state unavailable"}`（不管丟出什麼例外，不會 500），之後看磁碟上的 token 決定：還是舊的（store 拒絕寫入、或新的 state 檔寫不出來而還沒取代舊檔）→ 什麼都沒寫，用舊 state 重起子程式（同存檔的重起：額外帳號照樣先看記憶體），舊 token 照舊可用；不是舊的或讀不到 → 不重起舊子程式（磁碟上可能已是新 token）。取代 state 檔途中失敗（`os.replace` 或之後的目錄 fsync）屬後者：不知道寫成了沒有，store 照今天毒化，該帳號到 add-on 重啟前 503（額外帳號的新 state 檔已換上時，分派器讀不到就不路由它，兩把 token 都是未知 token）；**預設帳號**的 `os.replace` 失敗只關預設帳號，預設帳號的新 state 檔已換上時（目錄 fsync 失敗）8081 所有帶 token 的請求都 503 到重啟（同第 2.3 節「預設 state 讀不到」）。寫入丟出例外、但新 token 已在磁碟上而 store 照常（取代之後的清理失敗）也屬後者：新 token 只拿到閘道自己的回答，舊 token 401／404。重啟後照磁碟上的（token 與身分一定一起）。新子程式起不來 → 503 形狀 D 另帶 `token_rotated:true`，舊子程式不再起。每種失敗各記一行 WARNING（`multi-profile: the backend identity change of profile <id 前 8 碼> …`，寫明子程式有沒有重起；不含 token、網址、名稱）。`backend/patch` 把網址改到另一個來源（scheme、host、port）卻沒帶那條網址會送去的已存秘密 → 422 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN`（DQ-40 ⑨，全部產品，第 4.1 節；同一來源只換路徑不算，已知限制見威脅模型第 3 節）；`backend` 整份取代本來就帶全部秘密，不會 422。沒開通：照今天逐位元。這次存檔改到的後端網址是 loopback（127.0.0.0/8、::1 的各種寫法、`localhost`）或是不允許位址的數字寫法，一律 400 `{"error":"request denied"}`；n8n 也一樣，而且開通後另外套上既有的整套存檔檢查（同其他產品，HM-20；§8.8 #39）。還原或休眠後還沒「已核對」的帳號（`token/rotate` 列的關卡）：會換 token 的這種存檔也回 409 `restore_review_required`，在 If-Match 與新來源檢查（422）之後、停舊子程式之前判斷，什麼都不做（子程式不停、不寫、不發布）；紀錄讀不到時 503 `{"error":"state unavailable"}`；不換 token 的存檔照常（HM-13c 審查 S-3）。換掉的是還原保留的預設帳號權杖時，還原提示一起清掉（第 1.2 節） |
| `backend/test` | POST | 測選定帳號已存的設定 |
| `policy`、`odoo/write-switches`、`odoo/allowed-methods`、`n8n/session` | PUT | 只重啟選定帳號的子程式 |
| `endpoint` | PUT | 額外帳號 409 `endpoint_global`、什麼都不寫；額外帳號的 bootstrap 顯示預設帳號的 `endpoint`（全域設定只存在預設 state；DQ-13 已定，2026-11-15 17:4x 使用者採用建議） |
| `token/reveal`、`token/revoke` | POST | 只動選定帳號 |
| `token/rotate` | POST | 還原或休眠後未核對前 409 `restore_review_required`（HM-13c：還原紀錄裡這個帳號的權杖是守門撤銷的（`revoked`、`already_revoked`）而且 `reviewed_at` 還是 `null`；在 If-Match、Idempotency-Key 之後、什麼都不寫；紀錄讀不到時 503）。開關關時沒有關卡（也沒有核對路由）：還原撤銷了預設帳號時，管理員直接重新產生；重新開通後紀錄那一列仍待核對，下一次重新產生前要先核對（這時權杖是有效的：待核對不一定是已撤銷，第 4.1 節；HM-13c 審查 S-3、S-6）。HM-12 的換身分換 token 也照這個關卡（`backend`、`backend/patch` 列） |
| `child/restart` | POST | 回應帶 `blocked_reason` |
| `owner-defaults/restore`、`owner-defaults/dismiss` | POST | 只在預設帳號；額外帳號 409 `owner_defaults_unavailable`（形狀 C，在 If-Match 之後），不管它的目錄裡有什麼；額外帳號的 bootstrap 也一律沒有 `owner_defaults` 通知（FM-08；HM-10） |

- 方法：只有 `profiles/<id>` 接受 PATCH、DELETE；其他路徑的 PATCH、DELETE 回 405。開通後 8099 的路由要收 PATCH、DELETE，
  方法表改在管線第 ⑤ 步檢查（identity 之後）；沒開通照今天（路由層直接 405）。HM-10 定案：405 的位元組同今天 Starlette 的
  （純文字 `Method Not Allowed`、`Allow` 列這個路徑收的方法：帳號範圍路徑與頁面 `GET, HEAD, POST, PUT`，`profiles` `GET, POST`，
  `profiles/<id>` `PATCH, DELETE`，`profiles/index/quarantine` `POST`；HM-13c：`profiles/revoke-all`、`profiles/<id>/restore-review`、
  `profiles/quarantine/<名稱>/delete` `POST`，`profiles/restore-record` `GET`；HM-27：`origin-policy` `GET, PUT`）；全域路徑用表外的方法也是 405。
  路徑裡的 `<id>`、`<名稱>` 格式錯在第 ⑤ 步回固定 400。`profiles/` 底下其他路徑是
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
  - ⑤：全域路徑的方法表、本體剛好 `{"label": <字串>}`（`origin-policy` 的 PUT 是剛好 `{"mode": <字串>, "allowed_origins":
    [<字串>…]}`，HM-27）、路徑裡的 `<id>` 是 `default` 或 24 位小寫 hex；帳號範圍路徑只有方法表
    （PATCH、DELETE 回 405），本體的格式驗證照今天在該帳號的動作裡（⑨），所以非管理員連格式錯都看不到，在 ⑥ 就 403。
  - 帳號是在 ⑥ 之後才選的，所以入口不能是任何一個帳號的 app：分派器自己跑管線，再呼叫選定帳號的動作（⑧～⑪，今天的
    `admin_action`）。頁面與靜態檔交預設帳號的動作（照今天：拿鎖、角色檢查、回檔案）。
  - 全域路徑的 ⑧～⑪（`profile_admin.ProfileAdmin`）：清單是讀取，不拿鎖；建立、改名、刪除、索引隔離拿全 add-on 的帳號鎖，
    刪除再拿目標帳號的 `mutation_lock`，索引隔離再依 id 順序拿每個已登錄額外帳號的 `mutation_lock`（HM-10 審查 S-1）；一律先全域、
    再帳號，不會互鎖；每把最多等 2 秒（503，已拿到的鎖放掉、什麼都不做）。⑩ 在拿完所有鎖之後。刪除拿著目標帳號的鎖到它移除登錄為止，
    索引隔離拿著每個帳號的鎖到它移除登錄為止：該帳號進行中的 token 變更、存檔、重啟先做完再被撤銷；途中才來的請求拿到鎖時 store 已關
    （503）。⑩ 之後到提交（寫索引）之間不 await。HM-13c：全部撤銷拿全 add-on 的帳號鎖、預設帳號的鎖，再依 id 拿每個已登錄額外帳號的鎖，
    拿完才做 ⑩；之後 `restore_lock.revoke_all` 在工作執行緒跑（8081、8099 與健康檢查照常），撤銷後才 `committed()`、重起子程式，都在鎖裡。
    核對與刪除隔離目錄只拿全 add-on 的帳號鎖；還原紀錄是讀取，不拿鎖。
    Origin 政策（HM-27）：存檔拿政策自己的鎖（`OriginPolicy.lock`，不是帳號鎖；最多等 2 秒，逾時 503），⑩ 在拿到這把鎖之後，
    之後到寫完檔不 await（`tests/test_profile_admin_api.py` 第二次角色檢查的測試有這一輪；HM-27 審查 MF-2）；讀取不拿鎖，⑥、⑩
    各問一次角色。
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
| 建立、刪除、全部撤銷 | 索引 ETag `"p1-<64 hex>"`（全部撤銷在索引不能用時收壞索引的 ETag；HM-13c） | 要 | `/data/mcp/.profiles.json.operations.json` |
| 索引隔離 | 壞索引的 ETag（格式同 `"p1-…"`；bootstrap 的 `profile_index_etag`） | 要 | 同上 |
| 改名 | 索引 ETag | 不要 | — |
| 還原核對（restore-review） | 索引 ETag | 要 | 全域收據 |
| 刪除隔離目錄（HM-13c） | 索引 ETag | 要 | 全域收據 |
| Origin 政策（HM-27） | 政策 ETag `"o1-<64 hex>"`（這個程序的金鑰對政策內容算的 HMAC：同一份政策、存過或預設，ETag 相同；檔案不能用時對它的簽章與原始位元組算，只有存檔收它） | 要 | `/data/mcp/.origin-policy.json.operations.json` |

- 缺 If-Match 428 `config_revision_required`；不只一個或過期 409 `config_conflict`。
- 缺 Idempotency-Key 428 `operation_id_required`；不只一個 400 `operation_id_invalid`；同一個 key 還沒完成就重送 409
  `operation_outcome_unknown`；還原前的舊操作 id 410 `operation_restored`。HM-13b 定案：守門把還原帶回的收據檔改名成 `<收據檔>.restored`（每個收據檔只留 1 份，新的蓋舊的），換上一份空的新收據檔，多一個鍵 `restored_before_ms`（還原當下的毫秒，但不早於被封存的收據檔裡最新的 id 或下限：主機時鐘慢 24 小時以內也一樣，同 PaaS `_read_journal_floor`；最多比還原當下晚 24 小時：偽造的遠未來 id 不會讓新操作好幾年都 410。主機時鐘慢超過 24 小時時，備份裡較新的 id 在時鐘校正後可能被當成新操作，見 `threat-model.md` 第 3 節）：id 的時間不晚於它就回 410 `operation_restored`（在 24 小時保留期的 `operation_id_expired` 之前判斷），備份之後才做、隨還原消失的操作也算。只有守門寫的收據檔有這個鍵，其他收據檔逐位元照舊。沒有收據的收據檔不再封存（重做時不會用空檔蓋掉封存），只把時間往後推；收據檔不見但旁邊有封存（中途停掉）就補新檔（時間同樣不早於封存裡最新的 id）；HM-13c 起兩個都沒有也寫一份新收據檔（備份時某帳號還沒有收據檔，備份後才做的操作 id 隨還原消失，之後重送一樣回 410、不會被當成新操作；同 PaaS「每份設定都換新收據檔」），範圍 S 的每個帳號與索引旁都是；HM-27 起 Origin 政策旁的 `.origin-policy.json.operations.json` 也是（開通或有帳號資料時；Headscale 沒有政策，這份收據檔沒有人讀）。預設帳號沒被撤銷時（DQ-03 (b)，沒有帳號資料）它的收據照原樣、沒有就不寫（第 9 節 #121）。全部撤銷不封存收據（不是還原）。
- 建立的回應與同一個 key 的重送**都不回 token**；token 只經 `token/reveal`＋`X-MCP-Profile: <新 id>`＋回聲比對取得。
- HM-10 定案：
  - 帳號 ETag 的 HMAC domain 是 `edit:<帳號 id>`（套用狀態的 `launch:<帳號 id>` 同理）：`ProfileRuntime` 建的每個帳號都帶，沒開通時的
    預設帳號也是（ETag 是這個程序的隨機金鑰算的，本來就不跨程序、不能預測，沒開通時用戶端看到的沒有差別）；n8n
    （`apps/n8n/run.py`）到 HM-25 前不帶。兩個帳號就算 state 逐位元相同、金鑰也相同，ETag 也不同。
  - 索引 ETag＝這個程序的隨機金鑰對「索引的每一筆（id、名稱、port）照順序」算的 HMAC：內容一樣 ETag 就一樣，改名、換順序、
    增刪就變；重啟後全部變。壞索引的 ETag＝同一把金鑰對索引檔的 lstat 簽章與原始位元組（最多 64 KiB＋1）算的 HMAC，換檔或改任何
    一個位元組都會變；只有索引隔離收它，其他寫入一律 409。
  - 收據放索引旁、格式同今天，另多一個 `subject`（建立與刪除是帳號 id、索引隔離是改名後的檔名；都不是秘密），讓重送回得出做了什麼。
    種類：`profile.create`、`profile.delete`、`profile.index_quarantine`。帳號自己的收據檔格式不變。HM-13c 加三種：`profile.revoke_all`
    （subject `all`）、`profile.restore_review`（subject 是帳號 id，含 `default`）、`profile.quarantine_delete`（subject 是 `<id>-<UTC>[-n]`）。
    全部撤銷沒做完時收據停在未完成（結果未知），同一個 key 再送是 409 `operation_outcome_unknown`、不會再做一次；要重試用新的 key。
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
HM-10）、還原與休眠通知（HM-13c 定案）：
- 預設帳號：`restore_review`（只在還原紀錄裡有帳號等核對時出現）＝`{"pending":<還在的帳號（預設帳號與索引列的帳號；索引不能用時只算預設帳號）裡權杖被守門撤銷、還沒核對的數目>,
  "restore_at":<還原時間或 null>,"dormant_at":<休眠撤銷時間或 null>}`；紀錄讀不到或不是守門寫的形狀時三個都是 `null`（面板說紀錄讀不到、
  重新產生暫停，出路是全部撤銷）；`pending` 是數字而兩個時間都是 `null`：全部撤銷重建的紀錄（HM-13c 審查 S-2）。
- 每個帳號：`restore_review_required: true`（只在這個帳號的新權杖要等核對時出現；第 3.1 節 `token/rotate`）。
- 預設帳號：`restore_notice`（`{"at":…}`）同第 1.2 節（開通的產品沒有帳號資料時還原也會有；開關關時同樣）。
沒開通但有帳號資料時只多 `dormant_profiles`（數字；預設帳號還留著還原提示時另帶 `restore_notice`）；沒開通、沒有帳號資料時只在還原後多 `restore_notice`（第 1.2 節）。

**請求本體**：建立與改名都是剛好一個鍵 `{"label": <字串>}`。名稱規則（DQ-16 已定，照計畫 §8.5；負責片 HM-10、HM-11；§8.8 #35）：去頭尾空白後 1～80 個 code point；
拒絕 Cc、Cf（含 bidi、零寬）、Zl、Zp、Cs、Co、未指派；NFKC＋casefold 判重；`default` 與「預設帳號」保留。名稱只存在索引，
不進目錄名、log、MCP 回覆。

**還原紀錄**（`restore-record`，HM-13b 寫、HM-13c 讀；HM-13b 定案寫入的格式，HM-13c 讀的時候可以再定顯示與核對的欄位）：
`/data/mcp/restore-record.json`（0600，暫存檔＋fsync＋replace＋目錄 fsync，最多 1 MiB：每列是 state 的一部分，state 最多 64 KiB；預設帳號、索引裡的 5 個加 10 個孤兒的 state 都到上限也放得下，超過只會是手工拼的備份，守門停下），守門最近寫的一份紀錄（還原、休眠撤銷，或全部撤銷重建的；下面 HM-13c 審查修正那段）：
`{"version":1,"restore":null|{"at","marker","sentinel"},"dormant":null|{"at"},"index":"absent"|"ok"|"corrupt","profiles":[列…],`
`"quarantined":[{"name","id","new"}…],"profiles_directory":"absent"|"present"|"unlistable","other_entries":<數字>}`（`unlistable`：`profiles`
不是目錄；是目錄卻列不出來時守門停下、不寫紀錄，第 1.3 節；`restore-record.json` 的名稱被目錄占用時先移開，#120）；每列鍵照這個順序：
`id`、`label`（預設帳號 `Default`；索引讀不到或孤兒是 `null`）、`is_default`、`token`（`revoked`、`kept`（DQ-03 (b) 沒撤銷的預設帳號）、
`already_revoked`（休眠時之前就撤銷的））、`identity`（`identity_fields` 的身分欄位，沒設定是 `null`）、`policy`（政策與 n8n session 欄位）、
`reviewed_at`（守門寫 `null`；HM-13c 的核對寫一次 UTC 秒，之後不改；紀錄其他位元組照守門寫的）。HM-13c 讀的時候照守門寫的形狀逐鍵驗
（`restore_lock.check_record`），不符就當讀不到（失敗時一律擋重發）；面板只把它當文字顯示（可能來自偽造的備份）。被隔離的帳號不在列裡，在 `quarantined`。時間是 UTC 秒（`2026-11-16T09:30:15+00:00`）。
沒開通、沒有帳號資料的還原不寫這個檔（只有一行 log）。暫定時的原文：還原時間；逐帳號 `id`、`label`、身分欄位（`identity_fields` 分類）、
政策摘要（寫入開關、停用工具、逐項寫入授權、禁止的操作、Odoo 方法清單、n8n session）、`reviewed_at`（`null` 或時間）、目前狀態；
隔離目錄清單；休眠段落。不含任何 token 或密碼，網址裡的帳密也不記。

HM-13c 審查修正（MF-1、S-2）：
- 沒看到還原的開機（休眠開機）寫紀錄時，不丟掉上一份還在等的核對：上一份預設帳號那列還在等（`revoked` 或 `already_revoked`、`reviewed_at: null`），而這次預設帳號沒動（`kept`）時，那一列照上一份原樣；上一份的 `restore` 段落在它還有列在等時保留（這次的 `dormant` 照寫）。其他列都是這次的（休眠開機的帳號目錄列一律待核對）。
- 上一份讀不到或不是守門寫的形狀時，休眠開機不改它（記一行 log），新權杖照舊一律 503。出路是全部撤銷：做完時紀錄若讀不到，重寫一份，每個帳號 `revoked`、`reviewed_at: null`，`restore`、`dormant` 都是 `null`（關卡恢復可用，逐帳號核對）；讀得到時不改。
- 格式要向後相容：之後改紀錄格式（加鍵、改 `version`、改列的鍵）時，舊版寫的紀錄要照樣讀得懂；否則已核對完的安裝升級後，每個帳號的重新產生都 503，直到全部撤銷重建紀錄。

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
| `profile_not_found` | 404 | 格式對但帳號不存在（含孤兒、隔離目錄、已刪除的帳號；標頭）；全域路徑的 `<id>` 不在索引也不是孤兒；要刪的隔離目錄不存在、要核對的帳號不在還原紀錄或已不在索引（HM-13c） | `code` | ⑦（標頭）／⑪（全域路徑） | 不出現（整條路由 404） | 404 `"Profile not found"`（字串） | 本體多 `code` | 新 | HM-10；`tests/test_profile_admin_api.py`；面板收到就切回預設（HM-11） |
| `profile_label_invalid` | 422 | 名稱違反第 3.6 節規則 | `code` | ⑪ | 不出現 | 422 字串（只檢長度 1～80） | §8.8 #35 | 新 | HM-10、HM-11 |
| `profile_default_immutable` | 422 | 改名或刪除預設帳號 | `code` | ⑪ | 不出現 | 422 字串 | 本體多 `code` | 新 | HM-10 |
| `profile_label_conflict` | 409 | NFKC＋casefold 後和既有名稱或保留名稱相同 | `code` | ⑪ | 不出現 | 409 `"Profile label already exists"` | §8.8 #35（判重較嚴） | 新 | HM-10 |
| `profile_limit_reached` | 409 | 已到 min(5、產品上限)（各產品見第 5 節）；HM-10 定案：FD 上限提不到額外帳號要的量、add-on 只服務預設帳號時（第 5 節，HM-08）`limit` 是 0，什麼都不寫（重啟後它也不會被服務） | `code`、`limit` | ⑪ | 不出現 | 409，同欄位＋`message`（PaaS 沒有 FD 預算） | 同（少 `message`） | 新 | HM-10；`tests/test_profile_admin_api.py` |
| `profile_memory_insufficient` | 409 | 記憶體條件不夠再開一個 | `code`、`limit`、`required_memory_mib`、`memory_limit_mib`（讀得到 cgroup 才有）、`available_memory_mib`（HA 另帶） | ⑪ | 不出現 | 409，`limit`、`memory_limit_mib`、`required_memory_mib`＋`message` | §8.8 #19 | 新 | HM-09、HM-10；`tests/test_profile_admin_api.py`。HM-10 定案：讀得到 cgroup 時照 PaaS（`limit`＝記憶體容得下的額外帳號數、`required_memory_mib`＝256＋(現有額外帳號數＋2)×每子程式 MiB、`memory_limit_mib`，`available_memory_mib` 是 MemAvailable 或讀不到時 `null`）；讀不到 cgroup 時看 MemAvailable 夠不夠再起一個子程式（每子程式 MiB＋256，同 HM-09 起子程式的規則）：`limit`＝現有額外帳號數、`required_memory_mib`＝每子程式 MiB＋256、`available_memory_mib`；MemAvailable 讀不到就照建立並記一行 WARNING（不假設夠） |
| `profile_port_unavailable` | 409 | 18000～18099 找不到空 port（避開 3000、8081、8099、索引與執行中子程式的 port、試綁失敗的；HA 只用這 100 個，PaaS 到 65535，帳號最多 5 個所以沒差） | `code` | ⑪ | 不出現 | 409 `"No child port available"` | 本體多 `code` | 新 | HM-09、HM-10 |
| `profile_product_unsupported` | 409 | 產品不在七產品（OpenDesign、Odoo Manage）卻收到建立；正常不會開通，屬防呆 | `code` | ⑪ | 不出現 | OpenDesign 可開 3 個 | §8.8 #43 | 新 | HM-07、HM-10 |
| `endpoint_global` | 409 | 對額外帳號 `PUT endpoint`（在 If-Match 之後，什麼都不寫；DQ-13） | `code` | ⑪ | 不出現 | 不存 endpoint | §8.8 #27 | 新 | HM-10；`tests/test_profile_admin_api.py` |
| `restore_review_required` | 409 | 還原或休眠後、該帳號還沒「已核對」就 `token/rotate`，或開通後會換 token 的 `backend`、`backend/patch`（HM-12 換 Odoo 身分；HM-13c 審查 S-3）（HM-13c：還原紀錄裡它的權杖是守門撤銷的、`reviewed_at` 是 `null`；在 If-Match、Idempotency-Key 之後判斷，什麼都不寫、不留收據，面板放掉識別碼；紀錄讀不到時改回 503 `{"error":"state unavailable"}`，一律擋，出路是全部撤銷重建紀錄）。待核對不一定是已撤銷：開關關時沒有關卡，開關關期間重新產生的權杖（例如還原撤銷後的預設帳號）重新開通後那一列仍待核對、權杖卻有效；所以發新權杖的兩條路徑都接這個關卡：`token/rotate`，與 HM-12 的換身分換 token（在 If-Match 與新來源檢查之後、停舊子程式之前判斷，子程式不停、什麼都不寫、不發布；紀錄讀不到時同樣 503；只換密碼、初次設定、token 已撤銷這些不換 token 的存檔照常）。後者是 HM-13c 審查 S-3，主對話 2026-11-17 定、和 HM-12 合併時補；面板在存檔收到它時沿用這個代碼的文字，再說明換後端身分會換權杖、這次沒存 | `code` | ⑪ | 不出現 | 手冊步驟 9 核對後才發 | §8.8 #58 | 新 | HM-13c；`tests/test_restore_review.py` |
| `profile_index_corrupt` | 503 | 帳號索引不能用（結構壞、被外改，或啟動時 `profiles/` 列不出來）：清單、建立、改名、刪除、額外帳號範圍路徑。預設帳號的帳號範圍路徑照常（bootstrap 帶 `profile_index_state:"corrupt"` 與 `profile_index_etag`）；索引隔離照常可用（HM-10 定案）；HM-13c 定案：全部撤銷照常可用（If-Match 是壞索引的 ETag，緊急止血）、還原紀錄照常可讀；核對、刪除隔離目錄同建立與刪除，回這個代碼 | `code` | ⑦／⑪ | 不出現 | 整台 503（含管理 API） | §8.8 #25 | 新 | HM-07、HM-10；`tests/test_profile_admin_api.py` |
| `origin_policy_invalid` | 422 | `PUT origin-policy` 的模式不是剛好 `report-only` 或 `enforce`，或來源超過 16 個、有一個不是精確的 http(s) 來源（`*`、`null`、路徑、尾端斜線或點、帳密、query、空白、無效的主機或 port、非 ASCII）、正規化後重複。在 If-Match、Idempotency-Key、ETag 比對之後，什麼都不寫、不留收據（同一個 key 修正後可以再送） | `code`（形狀 A，不回顯任何值） | ⑪ | 不出現（沒有這條路由） | 沒有（環境變數，壞值啟動失敗） | §8.8 #126、#128 | 新 | HM-27；`tests/test_origin_policy.py` |
| `config_conflict` | 409 | If-Match 過期、格式錯或不只一個；拿 A 的 ETag 寫 B；索引 ETag 不符；索引能用時的索引隔離、沒有索引檔可隔離（HM-10）。回應的 `ETag` 標頭是目前的 ETag | `code`（形狀 B：本體只有 `detail`） | ⑪ | 照今天 | 帳號設定有；帳號 CRUD 不收 If-Match | §8.8 #34 | 既有（擴大） | HM-05、HM-10；`tests/test_profile_admin_api.py` |
| `config_revision_required` | 428 | 該帶 If-Match 卻沒帶（含帳號增刪改、核對、索引隔離） | `code` | ⑪ | 照今天 | 帳號 CRUD 沒有 | §8.8 #34 | 既有（擴大） | HM-10 |
| `operation_id_required` | 428 | 建立、刪除、全部撤銷、索引隔離、核對沒帶 Idempotency-Key | `code` | ⑪ | 照今天 | 帳號 CRUD 沒有 | §8.8 #34 | 既有（擴大） | HM-10 |
| `operation_id_invalid` | 400 | Idempotency-Key 不只一個、格式錯或時間在未來 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_id_expired` | 410 | Idempotency-Key 的時間早於 24 小時保留期 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10（帳號增刪的收據沿用） |
| `operation_id_conflict` | 409 | 同一個 Idempotency-Key 用在不同的請求（操作種類或內容不同） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_not_found` | 404 | 查詢的收據不存在，或屬於別的 HA 使用者（`operations/<id>`） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10、HM-11 |
| `operation_journal_full` | 503 | 收據已到上限（128 筆） | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10 |
| `operation_journal_unavailable` | 503 | 收據檔讀不到或寫不了 | `code` | ⑪ | 照今天 | 同義代碼 | 同 | 既有 | HM-10、HM-13b |
| `operation_outcome_unknown` | 409 | 同一個 key 還沒完成就重送；提交後失敗；全部撤銷沒做完（有帳號失敗、驗證不過、`profiles/` 列不出來、標記刪不掉或標記存不下：另帶逐帳號 `results`，`operation.state` 是 `unknown`；HM-13c。`results` 是空的：沒有任何帳號的結果，這次執行期間每個已登錄帳號撤銷前的權杖在 8081 回 503。可能是標記存不下（什麼都沒撤銷、沒有標記，重開後權杖恢復有效），也可能標記已存、之後才停（讀不到預設帳號的 state，或任何意外的例外：可能已撤銷一部分，log 記一行例外的類別；標記在，重開時守門在服務前補完；HM-13c 審查 S-4、S-6），面板兩種都講；每個帳號都撤銷了、只是沒收尾時，沒有權杖被擋成 503，標記留著，下次開機再做一次全部撤銷） | `code`；可帶 `operation`、`results`（`[{"id","result":"revoked"\|"failed"\|"quarantined"}…]`） | ⑪／提交 | 照今天 | 同義代碼 | 全部撤銷的逐帳號結果是 HA 加的 | 既有（擴大） | HM-10、HM-13b、HM-13c；`tests/test_revoke_all.py`、`tests/test_restore_review.py` |
| `operation_restored` | 410 | 還原後重送還原前的操作 id（舊收據封存成 `.restored`；HM-13c 起備份時沒有收據檔的帳號也換新收據檔，所以備份後才做、隨還原消失的 id 也是；HM-27 起 Origin 政策旁的收據也是（開通或有帳號資料時），`PUT origin-policy` 重送還原前的 id 也回這個，If-Match 是不是最新的都一樣） | `code` | ⑪ | 不出現（單帳號安裝的收據照還原的原樣，#121） | 410 `operation_id_expired`（新 journal 的保留期下限設在還原當下） | 代碼名不同；§8.8 #67（封存只留 1 份） | 新 | HM-13b、HM-13c、HM-27；`tests/test_restore_lock.py`、`tests/test_restore_review.py`、`tests/test_origin_policy.py`；面板 HM-13c 起有自己的文字，HM-27 起 Origin 政策的存檔收到它也用這段，識別紀錄留著、按「已核對來源設定」才清掉（`packages/mcp-admin-ui/tests/origin-policy.test.mjs`） |
| `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` | 422 | 開通的產品 `backend/patch` 把一條後端網址改到另一個來源（scheme、host 或 port；沒寫 port 用 80／443），卻沒帶那條網址會送去、而且已存的秘密（`identity_fields.URL_SECRETS`：Odoo `password`；Odoo Manage `api_key`；n8n `key` 與 `mcp_access_token`；Hermes `gateway_url`→`gateway_api_key`、`dashboard_url`→`dashboard_password`；EMQX `api_key` 與 `api_secret`；LiteLLM `master_key`；Nextcloud `app_password`；Headscale `api_key`；OpenDesign 沒有秘密）。帶了就算（值不限；可為 null 的帶 null＝清掉，不會送過去）；同一個來源（只改路徑、大小寫、寫出預設 port）不需要；網址清空或第一次設定不需要；同一台主機的其他寫法（結尾的點、IPv4 的其他寫法）算不同來源（安全的方向）；`backend` 整份取代一定帶秘密，不檢查。HM-12 定案：在 If-Match 與 `backend_fixed` 之後，什麼都不寫、不重起子程式 | `code`（本體 `{"error":"request denied","detail":{"code":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}`；以例外回，沒有回聲） | ⑪ | 不出現（沒開通照今天：`Hc/backend_edit.py:1-5` 刻意允許換網址沿用已存的秘密） | 只有 Headscale，422 `{"detail":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}`（字串）；比整條網址（`base_url`、`paas_base_url`） | §8.8 #41、#115（DQ-40 ⑨） | 新 | HM-12、HM-26；`tests/test_new_origin_secret.py` |
| `owner_defaults_unavailable` | 409 | 額外帳號的 owner-defaults 操作（HM-10 定案：不管目錄裡有什麼，在 If-Match 之後）；沒有標記的 state | `code`（形狀 C：本體另帶 `error:"owner_defaults_unavailable"`） | ⑪ | 照今天 | 沒有同名代碼（owner-defaults 只在預設帳號） | HA 既有 | 既有 | HM-10；`tests/test_profile_admin_api.py` |
| `config_apply_failed` | 503 | 已存檔，但重啟該帳號子程式失敗。開通的 Odoo 換身分時 token 已換，本體在 `saved` 後多帶 `token_rotated:true`（HM-12） | `code`（形狀 D：`saved:true`＋`detail`＋`configuration`，沒有 `error`） | 提交後 | 照今天 | 沒有同名代碼 | HA 既有 | 既有 | HM-09、HM-10、HM-12 |
| `core_version_unreviewed` | 403 | HA Core 版本不在白名單（只有角色檢查會帶；identity 的 403 沒有 detail） | `code`、`ha_version` | ⑥／⑩ | 照今天 | 沒有平台門檻 | §8.8 #30 | 既有 | HM-19a（每次升版補審） |
| `unsupported` | 409 | 產品沒提供 `backend/test`、`child/restart` 或 `diagnostics`（`child/restart` 在 If-Match、Idempotency-Key 檢查之後才判斷） | 沒有 `detail`（形狀 E：`{"error":"unsupported"}`） | ⑪ | 照今天 | 沒有同名回應 | HA 既有 | 既有 | HM-10（帳號範圍照今天）；HM-01 凍結 |
| `backend_check_failed` | 503 | `backend/test` 20 秒內沒做完或丟出例外 | 沒有 `detail`（形狀 E：`{"error":"backend_check_failed"}`） | ⑪（執行測試時） | 照今天 | 各產品的連線測試失敗回 200 `{"success":false,"message":<文字>}`（例如 `apps/odoo/odoo_mcp_admin/routers/config.py:143-166`） | HA 既有（不回伺服器文字，同 §8.8 #49） | 既有 | HM-10（測選定帳號）；HM-01 凍結 |
| `backend_fixed` | 409 | 產品不允許從面板改後端（`backend_can_edit` 為否）時 `PUT backend`、`backend/patch`（在 If-Match 檢查之後） | 沒有 `detail`（形狀 E：`{"error":"backend_fixed"}`） | ⑪ | 照今天 | 沒有同名回應 | HA 既有 | 既有 | HM-10；HM-01 凍結 |

沒有代碼的固定回應（同今天；本體是 `{"error":"request denied"}`，另有註明的除外）：

- 403：identity（來源、`X-Remote-User-Id`）、CSRF、cross-site、非管理員、斷線。
- 400：第 ① 步 `X-Ingress-Path` 不只一個或格式錯（`Hc/admin_auth.py:25-32`）；格式驗證不過、帶 query、`raw_path` 含 `%` 或 `\\`、
  不該有 body 卻有。
- 415：要 JSON 的路徑 `Content-Type` 不是 `application/json`（`Hc/gateway.py:280-281`）。
- 503：管理名額滿、拿鎖逾時、開通的 Odoo 換身分時舊子程式停不下來（什麼都沒寫，HM-12）；state 讀不到或寫不進去時本體是 `{"error":"state unavailable"}`。
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
| `{"error":"state unavailable"}` | 503 | 撞號、預設 state 或索引讀不到、索引外改、全部撤銷失敗的帳號（HM-13c：全部撤銷沒撤銷成功的已登錄帳號（沒有任何結果時是每個已登錄帳號：標記存不下、讀不到預設帳號的 state 或意外的例外），它撤銷前的權杖不論 state 現在寫什麼都回 503，密鑰網址與 Bearer 都是，直到一次全部撤銷做完或重開；`ProfileManager.revoke_fence`。名單只擋之後才經分派器比對的請求；全部撤銷結束時已比對過、還沒建 token lease 的請求（例如准入滿時正在讀的小通知，最多 2 秒）之後照磁碟上的權杖建 lease，失敗帳號的權杖還在就照常服務；已建 lease 的請求都由 `committed()` 結束（HM-13c 審查 S-6）） | 固定本體 | 只有預設 state 讀不到 | 503 | DQ-09 已定（同 PaaS 503） | 既有（擴大） | HM-08、HM-13c；`tests/test_restore_review.py` |
| `{"error":"request denied"}` | 400 | MCP 路徑帶 query | 固定本體 | 同 | 原樣轉發 | §8.8 #3 | 既有 | HM-01 |
| `{"error":"request denied"}` | 403 | Bearer 帶 Origin；Headscale 密鑰網址的來源不在清單；HM-27 起開通的產品政策是 `enforce` 時，密鑰網址的 Origin 不在清單（第 2.6 節） | 固定本體 | 前兩種同；沒有第三種 | Origin 清單 403 `{"detail":"ORIGIN_DENIED"}` | §8.8 #9、#10、#125 | 既有（擴大） | HM-27；`tests/test_origin_policy.py` |
| `{"error":"state unavailable"}` | 503 | HM-27：開通的產品的 Origin 政策檔不能用時，密鑰網址每個驗過 token 的請求（帶不帶 Origin） | 固定本體 | 不出現 | MCP 路徑 503 `ORIGIN_POLICY_UNAVAILABLE`（執行中讀到壞值） | §8.8 #126 | 既有（擴大） | HM-27；`tests/test_origin_policy.py` |
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
- 408（讀 body 超過 60 秒）、413（超過 16 MiB；HM-31 審查起，宣告超過的在讀之前就回，回應不變）、415（`Content-Type` 不是 `application/json`）；n8n 另有 4 MiB、10,000 元素、深度 64 的
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
| 待送回覆位元組（已處理、還沒送完：交給 server 起、server 收走才還；JSON 回覆在放掉轉送名額之前就先扣（HM-30 第二輪審查 MF-2）；軟上限，一次湧入的最壞值見下方「一次湧入的最壞值」（D2）；HM-30 定案見第 6 節） | 32 MiB | 32 MiB | 無（最壞 64 條連線各一個：64×8 MiB 原始大小，跳脫後最多 64×24 MiB） |
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
  - 已知限制：
    - MemAvailable 是開機那一刻的值（HA Core 還沒載完時偏高），之後 HA Core 與其他 add-on 會用掉更多；預算不隨它調整。
    - 同一台機器裝了多個 WOOW add-on 時，每個 add-on 都拿同一份 MemAvailable 減 256 MiB 推導自己的預算，等於重複計算（HM-31 審查 S-5）。
      沒開通時每個 add-on 有份額上限 64 MiB 限住；開通時全 add-on 預算可以更大。
    - 預算滿時閘道用到的記憶體＝預算×實際的放大倍數（下面「單一帳號有界」一點）。公式假設的 20 是 PaaS 閘道＋子程式的實測；HM-19c 量測後決定
      要不要再壓低（例如只取 MemAvailable 的一部分，或依同機的 WOOW add-on 數分攤）。
    - 預算落在下限 16 MiB 時，份額＝min(64 MiB, max(16 MiB, 16÷2))＝16 MiB＝整份預算（HM-31 審查 S-1）：一個帳號扣著一個大請求（tools/call
      最長 330 秒、SSE 到串流結束），其他帳號所有超過 64 KiB 的請求都拿 `-32003`；小請求不受影響。開通的 Odoo（6 個帳號）在 MemAvailable 約
      1.4 GiB 以下都落在下限；約 1.7 GiB 以下，一個帳號的份額超過全 add-on 的一半（例：1.7 GiB 時全 add-on 30.9 MiB、份額 16 MiB）。PaaS 的
      1 GiB pod 一樣（`P:docs/mcp-gateway-limits.md` 已知限制 (6)、(9)）。要不要給開通的產品加「全 add-on 至少 2×16 MiB」或「份額不超過
      全 add-on−16 MiB」：主對話 2026-11-16 定案交 HM-19c，量測後一起定（會改對齊 PaaS 的公式；不是 DQ-07 的數值；`decisions.md` 第 1.1 節）。
- 全域最壞記憶體（推算，全部帳號同時被打滿；HM-31 審查 MF-2 改寫）＝閘道基線＋全 add-on 預算×實際的請求放大＋沒扣預算的請求（小請求與
  元素多的小 body：同時進行的請求數×每個請求的解析高峰，下一點）＋Σ每帳號待送回覆上限＋工作執行緒一筆的回覆解析放大（8 MiB×27.6：D1 之後大量小物件一筆的實測高峰約 220 MiB，第二輪審查 S-3；D1 之前用 25 倍）＋
  子程式（帳號數×每子程式 MiB）。全 add-on 預算是照「上限＝基線＋子程式＋預算×20＋安全邊際 150」反推的：(上限−76−帳號數×子程式 MiB−150)÷20。
  實際的請求放大不超過 20 時，大請求、基線與子程式合計留得住 150 MiB 的安全邊際；超過 20 時，超過的部分直接吃掉邊際。沒扣預算的請求、待送回覆
  與回覆解析都不在這個式子裡（待送回覆由 HM-30 另算）。
  例：MemAvailable 2 GiB、開通的 Odoo（6 帳號）：上限 1,792 MiB，預算 48.3 MiB；放大 20 時大請求約 966 MiB，加基線 76、子程式 600，剩 150；
  放大 27.6（下一點的最壞結構）時大請求約 1,333 MiB，邊際變成約 −217 MiB。HM-08 的舊算式（每帳號 64 MiB×放大 2.5，約 1,352 MiB）不再適用。
  HM-30 補：待送回覆上限是**軟上限**（第 6 節）：已轉送的回覆一律交出，所以每帳號另有「正在轉送中的回覆」：最多轉送名額
  （額外帳號 16、預設帳號 32）×單一回應 8 MiB（原始大小；跳脫後最多約 3 倍），一次湧入時才會用到（第 6 節的量測）。上式的「Σ每帳號待送
  回覆上限」沒有算進去。今天沒開通時沒有待送上限：最壞是 listener 的 64 條連線各一個回覆（上表：64×8 MiB 原始大小、跳脫後最多
  64×24 MiB），比開通後一個帳號的最壞值大（HM-30 第二輪審查 S-6 改：原本寫「今天也是轉送名額×8 MiB」，和上表矛盾）。
  **一次湧入的最壞值**（D2，使用者 2026-11-16 定 (a) 接受並寫進文件）：帳上扣的是閘道序列化之後的大小（ASCII 跳脫：CJK 約 2 倍、
  emoji 約 3 倍，8 MiB 的 emoji 回覆扣約 24 MiB），所以一個帳號最多持有「待送上限 32 MiB＋轉送名額×跳脫後最多 24 MiB」：預設帳號
  32＋32×24＝800 MiB、額外帳號 32＋16×24＝416 MiB（理論上限，每個回覆都是 8 MiB 的 emoji、用戶端都不讀時）。
  這個上界靠兩件事（HM-30 第二輪審查 MF-2 改的程式，`gateway.PENDING_CHARGE`）：JSON 回覆在工作執行緒做好、**放掉轉送名額之前**就扣進
  待送額度（交給 server 時抵掉、不重複扣；請求在交出前結束也還回去）；在 HM-14 排隊的 tools/call **拿到名額之後、轉送之前再查一次**
  （被擋的回 200＋`-32003`，從沒轉送）。SSE 串流到結束都持有名額，回覆交出時扣，本來就成立。所以任何時候「已轉送、還沒扣」的回覆最多是
  轉送名額個。審查之前只在排隊前查一次、JSON 回覆要等交給 server 才扣：已通過檢查、還在排隊的請求會在名額放掉後照樣轉送，上界其實是
  准入×24 MiB（預設帳號約 1,536 MiB、額外帳號約 768 MiB）；審查 R2b 實測額外帳號真額度 32 個 8 MiB emoji 回覆：19 個轉送、帳上 456 MiB、
  RSS 增量 632～634 MiB（超過上面的 416 MiB）。改了之後的本機實測見第 6 節量測表「一次湧入」列。
  審查之前本機量到的（真 listener、用戶端都不讀；HM-30 與第一輪審查）：預設帳號 32 個 8 MiB 回覆，ASCII 帳上 224 MiB、管理程序 RSS 增量
  469 MiB；emoji 19～20 個轉送出去、帳上 456～480 MiB、RSS 增量 632～657 MiB；額外帳號 16 個 ASCII 帳上 128 MiB、RSS 增量 276 MiB。HM-19c 對
  MemAvailable 比對全域最壞值時用非 ASCII 的數字，並把每個帳號的「轉送名額×跳脫後最多 24 MiB」算進去。
  HM-30 審查 S-7 補：宣告長度的回覆分 64 KiB 交出之後，讀得慢的用戶端會讓請求一直到 server 收走最後一段才結束（之前整則交給 server
  就結束），所以該帳號的准入（32／64）與請求內容位元組預算的份額也扣得比之前久。只影響這個帳號自己。
- **單一帳號有界，倍數看內容**（HM-08 審查 MF-1、S-1 修正後；HM-31 加結構守門；HM-31 審查 MF-2 改成實測值）：
  - 帳上扣的是「收到的」與「轉送的」兩者較大的位元組；一個帳號最多扣到它的份額（最多 64 MiB），SSE 串流期間也算。
  - 實際用到的記憶體是扣款的好幾倍：閘道同時存著 body、解析後的物件、為了擋單獨代理字元做的整份 `json.dumps` 複本、轉送前重新序列化的
    str 與 bytes。HA 閘道自己（子程式不解析）一個請求的高峰，本機 tracemalloc 實測（HM-31 審查 E2；括號是高峰÷扣款）：16 MiB ASCII 字串
    68.0 MiB（4.3）；16 MiB 中文 83.9 MiB（扣 32 MiB，2.6）；16 MiB emoji 125.2 MiB（扣 48 MiB，2.6）；ASCII 大字串夾一個 emoji 224.0 MiB
    （14.0：Python str 整段變成每字 4 位元組，PEP 393）；99,990 個 `{"a":1}`（0.76 MiB）20.8 MiB（27.6）。子程式還要再解析一次，閘道＋子程式
    只會更高。
  - 所以一個 token 的持有人用滿 64 MiB 份額時，閘道自己最多約 4×224＝896 MiB（4 個 16 MiB、夾一個 emoji 的大字串）；元素接近上限的小 body
    每個約 21 MiB、扣款不到 1 MiB，同時進行的數量只由准入（開通：預設帳號 64、額外帳號 32）或 8081 外框 64（沒開通）限住，最壞約
    64×21 MiB≈1.3 GiB（推算；扣款約 49 MiB）。以前寫的「字串為主約份額的 3 倍以內、一個 token 約 224 MiB」不成立。
  - 放大倍數 20 是 PaaS 閘道（原樣轉送、不重新序列化）＋子程式的實測（最壞 17.8 倍：大字串裡一個非 BMP 字元，加上守門上限內最壞的結構）；
    HA 閘道會重新序列化，自己就到 14 倍（astral）與 27.6 倍（約 0.8 MiB 的最多元素結構）。HA 的倍數待 HM-19c（最後一點）。
  - 結構（HM-31，PaaS #155 的守門，不受開關管）：巢狀超過 64 層或元素超過 20 萬個的請求在解析前就拒收，所以 HM-08 量到的 24 倍
    （`[{},{},…]` 16 MiB 解析約 390 MiB）不會再出現。守門上限內最壞的結構，閘道自己的解析（`strict_json`）本機量到：4 MiB 的 body 約 26 MiB、
    16 MiB 的約 50 MiB（10 萬個 `{"a":1}`；元素數決定、不隨 body 變大）；1 MiB 的 body 約 20 MiB（19.5 倍，小 body 的倍數最高、絕對值最小；
    HM-31 筆記第 10 節）。
  - 小請求（≤64 KiB）不扣預算：同時大量進行時的總量由准入（開通）或 8081 外框 64（沒開通）限住，最壞約 64×64 KiB 的 body 加上解析
    （PaaS 已知限制 (2)，同樣適用）。
  - **HM-19c 放行條件**（HM-31 審查 MF-2）：在 J6412（可以的話 J1900）量 HA 閘道＋子程式的放大倍數與 MemAvailable，至少包含「16 MiB ASCII
    大字串夾一個 emoji」與「約 0.8 MiB、元素接近 20 萬的結構」兩種，各並行 64 條；另量 ASCII、中文、emoji、大量小物件。放大倍數超過 20，或
    全域最壞值超過「MemAvailable－保留量」，就回功能 PR 改 `AMPLIFICATION`、減少閘道內的副本（例如單獨代理字元的檢查不做整份
    `json.dumps`）、限制元素多的小 body 的並行數，或改保留量與份額；不改就不能發版。
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

**HM-30 回報後的使用者定案（2026-11-16 14:0x；`decisions.md` 第 1.1 節）**：

- D1 選 (a) 分段轉換：大回覆的序列化分段做、長字串也切段，中間讓迴圈先跑；輸出位元組和今天完全相同；HM-30 合併前做（下方
  「HM-30 定案」的 D1 一點）。HM-19c 在 J1900 量 mixed、CJK、emoji 三種內容，過不了再考慮子程序。
- D2 選 (a) 接受並寫進文件：待送回覆額度是軟上限（已轉送的一律交出）；一次湧入的最壞值寫在第 5 節與下方「慢讀用戶端」；DOCS 由
  HM-18 寫；HM-19c 比對 MemAvailable 時用非 ASCII 的數字，並算進「轉送名額×跳脫後最多 24 MiB」。
- D3 選 (a) 讀取期間也算：本節的門檻量整段，從 A 的 32 個請求同時開始、160 MiB 還在讀進來，到工作執行緒全部處理完；HM-19c 在目標
  硬體超標就回功能片改，不改不能發版。

**HM-30 第二輪審查回報後的使用者定案（2026-11-17 03:1x；`decisions.md` 第 1.1 節；門檻都沒放寬）**：

- Q1（第二輪審查 MF-1）接受，HM-19c 實測再定：沒有物件也沒有數字的大陣列（短字串、true／false／null、空陣列組成的陣列），解析仍是
  json 的一次 C 呼叫（本機 8 MiB 0.03～0.19 秒），測試只印不斷言。HM-19c 在 J1900 量，超標再從「開通時回覆也設元素個數上限」或「子程序
  處理回覆」選一個。
- Q2（第二輪審查 MF-4）接受，HM-19c 實測再定：分段處理期間別的帳號要等 A 正在處理的那一整筆（本機 B 的 p95 3.5 秒，不分段 1.9 秒；
  一筆 8 MiB 最久約 7 秒）。HM-19c 用真實回覆量 B 的 p95，過不了再改成工作執行緒在分段之間換帳號。
- Q4（第二輪審查 S-2）維持現狀，HM-19c 實測再定：請求端的大請求仍在主迴圈解析（本機一個 0.09～0.25 秒）。超標再從「開通的產品把請求端
  也交給工作執行緒」或「開通時降低單一請求上限或元素上限」選一個。
- 量停頓的測試（下面量測表的整段與真實 8 MiB 回覆兩列）門檻、次數都不改，也不加「超過再量一次」：本機偶爾紅、CI 紅了，先由主對話回報
  使用者再定。

**慢讀用戶端**：A 的用戶端不讀回應時，管理程序 RSS 增量 ≤ A 的待送回覆上限 32 MiB＋一筆處理放大 200 MiB＋餘裕 64 MiB＝296 MiB；
A 超過待送上限後，新的 tools/call 立刻回 200＋`-32003`。D2 定案：296 MiB 是「依序」慢讀的門檻（待送上限擋得住的情況）；待送上限是
軟上限，達到上限那一刻已轉送的回覆照樣交出，所以一次湧入時一個帳號最多持有「待送上限＋轉送名額×跳脫後最多 24 MiB」（預設帳號約
800 MiB、額外帳號約 416 MiB；第 5 節；這個上界靠 JSON 回覆在放掉轉送名額之前就扣、排隊的 tools/call 拿到名額之後再查一次，HM-30 第二輪
審查 MF-2），這個最壞值由使用者接受（D2 (a)），HM-19c 算進全域最壞記憶體。「一筆處理放大 200 MiB」是 D1 之前的估計；D1 之後最壞的形狀
（大量小物件）一筆約 220 MiB（27.6 倍；第二輪審查 S-3，本片重量 27.5 倍；量測表「一筆回覆的記憶體高峰」列），已吃掉一部分 64 MiB 的餘裕，HM-19c 的全域最壞值用 27.6 倍。

**HAOS 量測（HM-19c；J6412，可以的話 J1900）**：同一個情境下 B 的 tools/call p95 增量 ≤1 秒、健康檢查 0 次逾時；
過不了就調額度或回功能 PR，不能發版。健康檢查開通後連續兩次失敗才判 unreachable（今天一次就判）。

**HM-30 定案（2026-11-16；門檻本身沒改，仍是暫定、HM-19c 定案）**：

- 工作執行緒：全 add-on 一條（`reply_worker.ReplyWorker`，執行緒名 `mcp-reply-worker`，daemon，自己的 16 MiB 堆疊：回覆巢狀超過
  CPython 的 C 遞迴上限時照樣是 `RecursionError`＝502，不因平台給執行緒的預設堆疊小而當掉）。只有開通的產品由 `run_product` 建立與
  啟動；沒開通的產品不建，回覆照今天在迴圈內處理：跑的是同一組函式（`relayed_reply`、`relayed_event`），讀 state 的次數、順序與例外
  都和今天一樣。
- 交給它的：每個轉送的 JSON 回覆、SSE 每個帶資料的事件（`strict_json`→回覆檢查→`redact_secrets`→`filter_list`→`json.dumps`）。
  state 與遮罩清單在迴圈裡、交出的當下讀（工作執行緒不碰 store）；回覆位元組那時已經讀完，所以「回覆讀完時 add-on 持有的每個 token」
  都在遮罩裡，和今天一樣。不交的：子程式的 initialize 回覆（閘道自己重建結果，後端左右不了大小）、閘道自答的 tools/list、
  健康檢查自己的解析。
- 依帳號輪流：每帳號一個佇列；有一筆在處理的帳號暫時不排班，所以每帳號同時最多 1 筆，全部也最多 1 筆。等候中的呼叫者被取消
  （token 換了、用戶端離開、停機）時撤回它的工作；處理中的做完、結果丟掉。
- 例外：工作丟的例外照今天的回應（`ValueError`、`RecursionError` → 502 `{"error":"request denied"}`；state 讀不到 → 503
  `{"error":"state unavailable"}`）。執行緒本身停了（本模組的錯，不是工作的錯）：排隊中與之後的工作立刻得到 `WorkerStopped`（JSON 回 502、
  SSE 就此結束，沒有請求會一直等），記一行 WARNING（只有例外類別），`run_product` 把它當成元件停止讓 add-on 結束，由 Supervisor 重啟。
  停機：listener 停了之後才停；排隊中的立刻結束（502），處理中的最多等 5 秒（`STOP_SECONDS`）。
- 待送回覆位元組：帳號 app 把回覆的本體交給 server 起扣，server 收走才還（h11 要等自己的緩衝寫出才收下一則，所以一則要等同一請求的
  下一則被收走、或請求結束才算收走）。宣告長度的回覆（JSON）分成 64 KiB 一段交出、最後補一則空的：線上的位元組不變，server 自己的
  緩衝最多 64 KiB 加一段，請求要等 server 全部收走才結束。SSE 照子程式的事件交出（chunked 框架不變；h11 的框架會再複製一份，送完前約
  佔兩倍）。扣到或超過上限時，該帳號下一個 tools/call 在轉送名額之前回 200＋`-32003`＋`Retry-After: 5`（其他方法照常）。
  HM-30 第二輪審查 MF-2：JSON 回覆在工作執行緒做好之後、**放掉轉送名額之前**就先扣（`gateway.PENDING_CHARGE`：帳號 app 交給 server 時
  抵掉、不重複扣；請求在交出前結束也還回去），在 HM-14 排隊的 tools/call **拿到名額之後、轉送之前再查一次**（被擋的照樣 200＋`-32003`、
  不轉送、放掉名額）。只有 tools/call 會被擋：其他會轉送的方法（initialize、ping、tools/list）的回覆由閘道自己重建或很小。
- 已轉送的回覆一律處理並交出，不扣住：照順序讀回覆的用戶端要是等的那一則被扣住，會等到逾時。所以待送上限是**軟上限**：
  達到上限時正在轉送的回覆仍會交出，帳號最多持有「上限＋那時正在轉送的回覆」（最多轉送名額個，每個最多 8 MiB 原始大小；上一點的
  「放掉名額之前就扣」與「拿到名額之後再查一次」讓這個上界成立，第 5 節）。
- **GIL convoy 與工作執行緒的「喘息」**（HM-30 量到、計畫沒寫到的事）：事件迴圈每次系統呼叫（epoll_wait、socket、讀 state 檔：
  一次 `store.load` 就五個）都會放掉 GIL，忙著的工作執行緒立刻拿走，迴圈要等到它下一個 bytecode 邊界才拿得回來。只靠 GIL 的 5 ms
  切換間隔，迴圈一次小檔讀取從 0.02 ms 變 30～60 ms，B 的 tools/call p99 4.5 秒、迴圈最長停 1.3 秒（比在迴圈內處理還差）。所以工作
  執行緒在每個檢查點（工作之間、步驟之間、解析器每建一個 JSON 物件時與每 1,024 個數字：`config.strict_json` 的 `checkpoint`；遮罩、
  成本計算與放掉時大的 list／dict 每 1,024 個成員：HM-30 第二輪審查 MF-1）連續跑滿 5 ms 就睡
  2 ms，之後只要迴圈還忙（asyncio 的 ready 佇列有東西，或迴圈執行緒不在 selector 裡等 I/O）就繼續讓，最多 10 ms；忙到底時工作
  執行緒約讓出三分之一的時間，閒時不讓。拆不開的只有單一 C 呼叫（掃一個長字串、整個值的 `json.dumps`）。
- **D1：分段轉換**（使用者 2026-11-16 定 (a)；只在工作執行緒那條路，沒開通照今天）：
  - 序列化分段（`reply_worker.encoded`）：和 `json.dumps(value, separators=(",", ":")).encode()` 逐位元相同。先一次走訪算出每個
    list／dict 最多編成幾個位元組（字串每個碼位以最長的跳脫 12 位元組算），超過 64 KiB 的才拆：成員照順序分段、每段一次 json 的
    C 編碼器；長字串一次 8,192 個碼位（json 的跳脫只看單一碼位，切開接回一樣）；呼叫之間有檢查點。
  - 一筆大回覆在工作執行緒上的其他長停頓一起處理：處理一筆工作時關掉循環回收器（工作結束一律恢復；全代回收一次走過整個 add-on 的
    物件，回覆的幾十萬個也在內）；編碼完把解析出的值與遮罩後的值分段放掉（一次放掉幾十萬個物件是一次 C 呼叫；filter_list 重建過
    工具清單的不分段放）；遮罩（`redact_secrets`）與成本計算也喘息；解析前不先複製 8 MiB 的 bytes。
  - 循環回收器是整個程序共用的（HM-30 第二輪審查 S-5）：工作期間迴圈執行緒的配置也不會觸發回收，A 一直送大回覆時回收器幾乎一直關著，
    迴圈那段時間產生的循環垃圾要等工作之間才收。合成負載量過循環物件有界（provenance 筆記第 16.7 節）；HM-19c 跑長時間大回覆時看 RSS
    會不會一直長。
  - 扁平陣列（HM-30 第二輪審查 MF-1）：沒有物件的大陣列（ID 清單、時間序列 `[[ts, v]]`、浮點數清單）之前只在容器結束時喘息，解析、遮罩、
    成本計算都是 0.4～1.1 秒不喘息的一段（迴圈每個系統呼叫都要再等 GIL：同時迴圈上的 `store.load` p99 從 0.3 ms 變 25～41 ms），解析整數
    陣列更是一次 C 呼叫。現在解析器每 1,024 個數字呼叫一次檢查點（整數也經 `parse_int` 交給 Python：`int` 本身，值與超過位數上限的
    錯誤都相同）；遮罩、成本計算每 1,024 個成員一次；放掉時從尾端切、不先整個複製。位元組不變；沒開通的產品不經過這些。
  - 一筆變長，別的帳號等得也久（HM-30 第二輪審查 MF-4）：工作執行緒一次只處理一筆，B 的回覆最多等 A 正在處理的那一整筆；分段、喘息與
    分段放掉讓一筆變長（本機一筆真實 8 MiB 回覆的時間見量測表「真實 8 MiB 回覆」列），A 一次送幾個大量小物件的回覆時，B 的 tools/call
    要等好幾秒（量測表「真實回覆時 B 的延遲」列）。上面門檻表的「B 的 p99 ≤2d＋0.2 秒」只用可控注入（d＝0.25 秒）量；真實回覆下 B 的延遲
    交 HM-19c（B 的 p95 增量 ≤1 秒），本片測試不量。使用者 2026-11-17 定（Q2）：接受，HM-19c 用真實回覆量，過不了再改成在分段之間換帳號。
  - 大於 64 KiB 的 SSE 事件，切框（`sse_frame`、`sse_data`）、處理、組成事件都改在工作執行緒（迴圈原本那幾步、同樣順序；組成事件
    只複製一次）：每一步都會複製或掃過整個事件，8 MiB 的事件在迴圈上一次 35～50 ms。小的事件照舊在迴圈切框。
  - 還是一次 C 呼叫的：`json.loads` 掃一個長字串（8 MiB 約 20～50 ms，跳脫字元多的最慢）、bytes 解碼成 str（5～20 ms）、最後把
    各段接起來（一次複製）。目標硬體慢數倍，HM-19c 量。另外，**沒有物件也沒有數字的陣列**（短字串清單、true／false／null、空陣列，
    任何深度）json 的 C 解析器整段一次解析，沒有地方喘息（HM-30 第二輪審查 MF-1）：8 MiB 本機約 0.03～0.19 秒（短字串清單約 0.1 秒），
    超過 50 ms。使用者 2026-11-17 定（Q1）：接受，HM-19c 在 J1900 量，超標再從開通時回覆元素上限或子程序選一個；測試只印不斷言。
- **D3：讀取期間也算**（使用者 2026-11-16 定 (a)）：門檻量整段（A 的 32 個請求同時開始、160 MiB 以 64 KiB 一段讀進來，到工作執行緒
  全部處理完）。HM-31 合併後重量：改之前本機 pytest 6 次 38.5～47.4 ms（前一段一次整檔跑 60.9 ms，紅），貼著門檻。找到兩處，都改了：
  - 測試工具的錯（`tests/reply_load.py`）：A 的假子程式以 JSON-RPC id 判斷要不要回大回覆，健康檢查的 tools/call 用 id 3，正好是
    A 的請求 id 之一，所以 A 的每次健康檢查都拿到 8 MiB 的填充回覆，在迴圈上讀與解析（`health.protocol_reply`）。真的子程式對健康檢查
    回的是小回覆（`products.health_probe`）。改成只對 A 的工具回大回覆。pytest 量不出它對最長停頓的差別，是讓測試照實的修正。
  - 讀取期間的 token 檢查：子程式的回覆以 64 KiB 一段讀，每段 `store.load` 3 次（開始前、watcher 立刻一次、結束後），工作執行緒忙時
    每個系統呼叫都要再等 GIL。開通的產品改成每段 1 次（`TokenLease.run` 的 `checked`：上一個操作（子程式的標頭、
    上一段）結束時剛查過，所以開始前不再查，watcher 等過一次才看；透過管理 API 換 token 照樣立刻中斷，其他改變由結束後的那次
    檢查擋下，換了之後讀到的都不交出）。沒開通照舊。讀取期間從約 3 秒縮到約 1.3 秒，B 的 tools/call p99 也降一些。
  - 改完：pytest 6 次 34.4～45.9 ms、整檔 41.1 ms，門檻沒放寬，喘息參數（5 ms／2 ms／10 ms）沒改。剩下最長的停頓多半落在 A 的 32 個
    請求同時開始那一下（測試裡用戶端、閘道、假子程式都在同一個迴圈上），注入成本設 0 也有（38.1、50.5 ms）：不是工作執行緒造成的。
    餘裕只有約 4 ms；HM-19c 在目標硬體量整段，超標就回功能片改。
  - 第二輪審查 S-1：2 顆 CPU 加 2 個忙迴圈的機器上 68.2～73.2 ms（5 次全紅，都在讀取期間）。把 A 的 32 個請求改成不經程序內的 httpx
    用戶端、直接呼叫 ASGI app，讀取期間沒有變短（一般 34.1～38.1 ms、2 顆 CPU 加忙迴圈 72.4～75.7 ms）：最長的那一下是 32 個 task 同時
    開始、在迴圈的同一輪裡各自做完請求端的工作（token、HM-31 的守門、授權、轉送）。正式環境 32 個請求同時到達時 uvicorn 也在同一輪把它們
    交給 app，所以這是閘道自己的工作，要再壓低是請求端的事（下一點）。測試照舊、門檻不放寬；第二輪修正後本機 pytest 11 次：10 次 30.9～49.5 ms、1 次 63.3 ms（紅，讀取期間；那段時間容器沒有被 CPU 節流），處理期間 16.7～22.2 ms。
- 請求端（HM-30 審查 S-5；HM-31 合併後重量）：請求的結構守門、解析（`strict_json`）、單獨代理字元的檢查與轉送前的重新序列化仍在
  事件迴圈裡同步做，本節的 CPU 飢餓保證只對回覆成立。HM-31 的元素上限（20 萬）把審查 X4 的 0.36～1.9 秒壓下來了，但一個大請求仍讓
  迴圈停 0.09～0.25 秒（本機，一個請求、沒有別的負載，pytest 各 2 次）：16 MiB 的 ASCII／CJK／emoji 字串 134～222 ms（結構守門
  18～46 ms、`strict_json` 37～57 ms，其餘是單獨代理字元的檢查與轉送前的 `json.dumps`）、19.9 萬個浮點數（0.9 MiB）91～124 ms、
  99,990 個 `{"a":1}`（1 MiB）183～245 ms（結構守門的慢路徑 129～132 ms）。D3 的整段量測裡 A 的請求是小請求，不受影響。要把請求端也移到工作執行緒是另一件事（不在本片），
  交主對話與 HM-19c（在目標硬體量；超過時的選項見 provenance 筆記）。
- SSE 事件的 state 讀取（HM-30 審查 S-6）：POST 串流每個帶資料的事件交出前，迴圈都讀一次 state 與遮罩清單（`prepared()`：一次
  `store.load` 約 5 個系統呼叫，另加每個帳號的憑證 1～2 次 `lstat`），連會被略過的通知也讀，實際只有回覆事件用得到。這是效率與 I8 的
  餘裕，不是安全問題。改成「工作執行緒先分類、是回覆才回迴圈讀 state 再交第二步」，每個回覆事件就要在工作執行緒排兩次班（B 最多等 A
  的兩筆），所以本片不改，交 HM-19c 在目標硬體量通知多的串流，量到問題再改。

**HM-30 本機量測（AMD EPYC 7713，上限 2.0 GHz，Python 3.13.15；以 GitHub CI 為準，HM-19c 在目標硬體重量）**：

| 項目 | 結果 | 門檻 |
|---|---|---|
| CPU 飢餓（可控注入：每 8 MiB 0.25 秒、單一 C 呼叫在啟動時校準成約 10 ms（機器忙時偏短，量到 5.7～9.9 ms）、在解析器的檢查點之間；A 並行 16×8 MiB＋16×2 MiB），A 的回覆處理期間迴圈最長停頓 | 13.9～27 ms（pytest 3 次、獨立腳本 4 次）；審查 13.1～23.7 ms；審查修正後重跑 11.1～28.0 ms（pytest 4 次）；rebase 與 D1、D3 之後 15.5～26.2 ms（pytest 6 次）；第二輪審查修正後 16.7～22.2 ms（pytest 8 次） | ≤50 ms：達到 |
| 同上，整段（D3：A 的 32 個請求同時開始、160 MiB 以 64 KiB 一段讀進來，到工作執行緒全部處理完） | rebase 與 D1、D3 之後：整段最長 34.4～45.9 ms（pytest 單獨跑 6 次；最長的都在讀取期間，處理期間 15.5～26.2 ms；整檔跑 1 次 41.1 ms）。改之前（rebase 後、測試工具還沒修、每段 3 次 token 檢查）：本機 38.5～47.4 ms（單獨 5 次）、整檔 39.3 ms，前一段一次整檔跑 60.9 ms（紅），貼著門檻。拆解（pytest，最後的程式各關回一個修正，各 3 次）：兩個都改 34.5～38.3 ms、讀取期間 1.24～1.45 秒；只把租約改回每段 3 次 35.8～45.0 ms、讀取期間 2.87～3.03 秒；只把測試工具改回 37.6～38.6 ms；兩個都改回 37.9～44.2 ms、讀取期間 2.88～3.10 秒。最長的停頓多半落在 A 的 32 個請求同時開始那一下（測試裡用戶端、閘道、假子程式都在同一個迴圈上），注入成本設 0 也有（38.1、50.5 ms，2 次）：不是工作執行緒造成的。rebase 前只量讀取期間：作者 49.2～51.9 ms、審查 48.5～59.0 ms、審查修正後 49.8～60.6 ms（provenance 筆記第 11.1 節）。第二輪審查：一般 32.9～40.8 ms、4 顆 CPU 34.5～36.4 ms、2 顆 CPU 加 2 個忙迴圈 68.2～73.2 ms（5 次全紅，都在讀取期間）；修正後本機 pytest 11 次：10 次 30.9～49.5 ms、1 次 63.3 ms（紅，讀取期間；那段時間容器沒有被 CPU 節流），處理期間 16.7～22.2 ms；把 A 的 32 個請求改成不經程序內的 httpx 用戶端、直接呼叫 ASGI app，讀取期間沒有變短（一般 34.1～38.1 ms、2 顆 CPU 加忙迴圈 72.4～75.7 ms）：最長的那一下是 32 個請求同時進來時閘道自己的請求端工作（provenance 筆記第 17.6 節）。rebase 到 `7646f0f` 之後（2026-11-17）：pytest 單獨 5 次 29.3～36.9 ms（最長都在讀取期間；處理期間 15.9～25.5 ms；B 的 p99 297～323 ms）、本片 4 檔整檔 1 次 39.5 ms，6 次都綠（provenance 筆記第 18.8 節） | ≤50 ms（D3 (a)：讀取期間也算）：本機多半達到，11 次紅 1 次；小而忙的機器上超過（審查 S-1）。最長的那一下在請求端：使用者 2026-11-17 定（Q4）維持現狀、HM-19c 實測再定（provenance 筆記第 17.10 節） |
| B 的 tools/call p99（可控注入 d＝0.25 秒；真實回覆見下一列） | 0.36～0.44 秒（開工前在迴圈內處理：4.47 秒）；審查修正後重跑 0.31～0.44 秒；rebase 與 D1、D3 之後 0.29～0.31 秒（pytest 6 次）；第二輪審查修正後 0.29～0.31 秒（pytest 11 次） | ≤2d＋0.2＝0.7 秒：達到 |
| 真實回覆時 B 的 tools/call 延遲（第二輪審查 MF-4；A 同時送 3 個真實 8 MiB 回覆、不注入成本，B 期間每 50 ms 呼叫一次工具） | 大量小物件：A 的 3 筆 10.7 秒做完，B 的 p50 3.3 秒、p95 3.5 秒（審查 R8：p95 3.9 秒）；mixed：2.2 秒做完，B 的 p50 0.58 秒、p95 0.72 秒。對照（工作執行緒上一次 `json.dumps`、不分段放掉）：大量小物件 B 的 p95 1.9 秒、mixed 0.46 秒。一筆真實 8 MiB 回覆在工作執行緒上的時間：mixed 約 0.7 秒、64 層巢狀 1.4～1.7 秒、大量小物件 3.2～3.5 秒、扁平數字陣列 1.4～4.1 秒、空陣列的陣列約 6.8 秒（provenance 筆記第 17.2、17.5 節） | 本片測試不量；HM-19c：B 的 p95 增量 ≤1 秒（目標硬體遇到物件多的 8 MiB 回覆幾乎過不了）；使用者 2026-11-17 定（Q2）：接受，HM-19c 用真實回覆量，過不了再改成在分段之間換帳號 |
| B、C 的健康檢查（時限 8＋5 秒） | 0 次逾時、判定一直是 reachable；每次在該做之後最晚 31～50 ms 做完（審查修正後重跑 26～54 ms；rebase 與 D1、D3 之後最晚 24、30 ms（整檔跑 1 次）；開工前在迴圈內處理：最晚 4.4 秒才做完；本機還沒到逾時，目標硬體慢數倍時就會） | 0：達到 |
| 每帳號同時在處理的回覆 | 1（全部也是 1） | ≤1：達到 |
| 真實 8 MiB 回覆迴圈最長停頓（D1） | D1 之後（工作執行緒分段處理）：七種形狀（mixed、大量小物件、CJK、emoji、長 ASCII 字串、跳脫字元、64 層巢狀）的 JSON 回覆與兩種事件（mixed、emoji），工作執行緒那條路 7.3～46.3 ms（pytest 3 次；最高的是跳脫字元多的長字串：解析端那一次 C 呼叫）；同一筆在迴圈內處理 60～895 ms。D1 之前（同一組測試、一次 `json.dumps`）：9 案裡 6 案超過 50 ms（大量小物件 125.9、巢狀 72.8、emoji 事件 60.6、長 ASCII 字串 55.7、emoji 52.8、mixed 50.5 ms）。D1 回報時的數字（mixed 42～50 ms、一次 `json.dumps` emoji 46～69 ms 等）在 provenance 筆記第 11.3、14 節。第二輪審查 MF-1：扁平陣列在工作執行緒那條路本機 70～185 ms（審查 R1）；修正後加 5 種數字陣列（ID、小整數、整數與浮點數的時間序列、浮點數），12 種形狀與 2 種事件 工作執行緒那條路最長 5.5～41.3 ms（pytest 7 次、98 案次；最高的是跳脫字元多的長字串），其中一次浮點數 50.5 ms（紅；同一形狀另 6 次 7.5～24.1 ms）：工作執行緒自己最長的不喘息區間只有 5～7 ms（獨立腳本），另一個實驗量到一次 59 ms 落在兩個平常只隔 0.5 ms 的檢查點之間、迴圈與工作執行緒一起停，判斷是多個代理共用的主機讓整個程序停住，不是程式（provenance 筆記第 17.6 節）；X1（迴圈上另外每 2 ms 一次 `store.load`）數字陣列 5.7～13.4 ms、`store.load` p99 0.4～0.6 ms（審查前 20.6～41.4 ms）。沒有物件也沒有數字的陣列仍是解析的一次 C 呼叫：短字串清單 85～153 ms（pytest 只印不斷言）、空陣列的陣列 126 ms、空字串 61 ms、中文短字串 53 ms、true 23 ms（X1）。rebase 到 `7646f0f` 之後（2026-11-17）：14 案 pytest 單獨 5 次（70 案次）與本片 4 檔整檔 1 次，工作執行緒那條路最長 5.5～42.7 ms，0 次紅（最高仍是跳脫字元多的長字串）；短字串清單（只印）81.8～98.5 ms（provenance 筆記第 18.8 節） | 數字的形狀與長字串：≤50 ms 本機達到（D1 (a)；98 案次紅 1 次，見左欄）。拆不開的只剩解析端（`json.loads` 掃一個長字串、bytes 解碼成 str、沒有物件也沒有數字的陣列）與最後接起各段的一次複製；沒有物件也沒有數字的陣列本機就超過：使用者 2026-11-17 定（第二輪審查 Q1）接受、HM-19c 實測再定。目標硬體慢數倍：HM-19c 在 J1900 量 mixed、CJK、emoji 與扁平陣列，過不了再考慮子程序 |
| 慢讀 ASCII（2 個 JSON＋2 個 SSE 回覆各 8 MiB、SSE 的請求各帶 4 MiB 參數，用戶端都不讀） | 帳上 32 MiB、位元組額度（HM-31 之後是請求內容預算的份額）扣著 8 MiB 轉送內容、RSS 增量 121 MiB（審查修正後重跑 116～120 MiB；rebase 與 D1 之後 96～116 MiB）；下一個 tools/call 立刻 200＋`-32003` | ≤296 MiB：達到 |
| 慢讀 emoji（審查 S-1：1 個 JSON＋1 個 SSE 回覆各 8 MiB emoji，SSE 的請求帶 4 MiB emoji 參數，UTF-8 送；用戶端都不讀） | 帳上 48 MiB（閘道跳脫後每個約 24 MiB：額度 32 MiB 加上達到前已交出的那一則，軟上限）、位元組額度（HM-31 之後是請求內容預算的份額）扣著 12 MiB 轉送內容（4 MiB 參數跳脫成 12 MiB）、RSS 增量 116 MiB（pytest 4 次；rebase 與 D1 之後 76～112 MiB）；下一個 tools/call 立刻 200＋`-32003` | ≤296 MiB：達到 |
| 一次湧入（同時 N 個 8 MiB 回覆都不讀；軟上限） | ASCII：額外帳號 16 個帳上 128 MiB、RSS 增量 276 MiB；預設帳號 32 個帳上 224 MiB、RSS 增量 469 MiB。emoji（審查 X2；待送額度扣的是跳脫後的大小，emoji 約 3 倍）：預設帳號 8 個帳上 192 MiB、RSS 增量 267 MiB；32 個時 19 個在達到上限前轉送出去、帳上 456 MiB、RSS 增量 632 MiB（重跑一次：20 個、480 MiB、657 MiB）；理論上限：預設帳號 32＋32×24＝800 MiB、額外帳號 32＋16×24＝416 MiB（第 5 節）。第二輪審查：上面的程式其實讓已通過檢查、還在排隊的請求在名額放掉後照樣轉送，上界是准入×24 MiB（審查 R2b：額外帳號 19／32 個、帳上 456 MiB、RSS 增量 632～634 MiB）。改程式（JSON 回覆在放掉名額之前就扣、排隊的拿到名額後再查一次，MF-2）之後，真額度、32 個（預設帳號 64 個）8 MiB emoji 回覆都不讀：預設帳號 33 個轉送、帳上 792 MiB、RSS 增量 1,088 MiB；額外帳號 17 個、408 MiB、RSS 增量 536 MiB。縮小額度的 pytest（准入 8、名額 2、待送 1 MiB、600 KiB 回覆）：JSON 3／8 個、1,802 KiB（上界 2,224 KiB；修正前 8／8、4,800 KiB），SSE 2／8 個 | 296 MiB 是依序慢讀的門檻；一次湧入的最壞值由使用者接受（D2 (a)，2026-11-16）；HM-19c 對 MemAvailable 比對時用非 ASCII 的值，並算進「轉送名額×跳脫後最多 24 MiB」 |
| 一筆回覆的記憶體高峰（第二輪審查 S-3；新程序、一筆 8 MiB 回覆的 RSS 增量：迴圈內處理 → 工作執行緒） | 大量小物件 209 → 220 MiB（27.5 倍；審查 201～209 → 220～221 MiB、27.6 倍）、64 層巢狀 73 → 98、小整數 72 → 111、ID 清單 46 → 69、`[[ts, 整數]]` 111 → 131、浮點數 96 → 127、短字串清單 102 → 130、emoji 長字串 32 → 54 MiB（審查的 `peak_rss.py`，本片重量） | 契約的「一筆處理放大 200 MiB」（慢讀門檻 296 MiB）是 D1 之前的估計；D1 之後最壞約 220 MiB（審查 27.6 倍、本片 27.5 倍），第 5 節的全域最壞值與 HM-19c 用 27.6 倍 |

## 7. 子程式、port 與生命週期（給測試用的數值）

| 項目 | 規則 |
|---|---|
| port | 預設帳號 3000；額外帳號 18000 起找第一個空號，避開 3000、8081、8099、索引內 port、執行中子程式的 port；試綁四種位址確認沒人佔（HM-09：`profiles.allocate_port(occupied=profiles.port_occupied)`、`ProfileManager.free_port()`；試綁照 PaaS `port_occupied`：127.0.0.1、0.0.0.0、::1、::（v6only），都帶 SO_REUSEADDR）。HM-09 審查（S-6）：IPv6 試綁被平台擋（EACCES、EPERM：AppArmor、seccomp）時跳過那個位址，每個位址與 errno 每個程序記一行 WARNING（PaaS 當成被佔；第 9 節 #89）；IPv4 任何失敗仍當被佔 |
| spawn 前檢查 | port 衝突或被佔就不 spawn，`status=blocked`＋`blocked_reason`。HM-09 定案的四類：add-on 自己的 listener port（8081、8099）、別的帳號執行中的子程式在用 → `child_port_conflict`；試綁失敗 → `child_port_in_use`；這三種照看門狗退避重試（同 PaaS 每次拒絕都重試）。索引內重複或等於 3000 的帳號開啟時就 `disabled_reason=port_conflict`，起子程式時 `blocked`＋`child_port_conflict`、不重試、也不試綁，索引變了（HM-10 寫入後 `adopt_index`＋`reevaluate()`）才重評。被擋的子程式不 spawn，健康監看也不送任何東西到那個 port |
| 看門狗（DQ-20 採 (b)） | 開通的產品所有帳號（含預設）：退避 2、5、15、30、60、120、300 秒，不限次數，連續跑 120 秒歸零；OOM 殺掉也照退避。沒開通維持今天「同一次啟動最多 4 次、不歸零、之後 failed」。HM-09：spawn 失敗（`OSError`）與 spawn 前檢查的拒絕也算一次失敗、照退避重試（PaaS 的 spawn 失敗會停在 failed；HA 的子程式指令固定在映像裡，spawn 失敗多半是暫時的，例如 fork 時記憶體不夠）；退避期間 `status=backoff`，被擋時維持 `blocked` |
| 錯開啟動 | 預設帳號先起；額外帳號依序起、同時最多 2 個，前一個健康檢查通過或 30 秒逾時才起下一個。HM-09 定案：預設帳號在 listener 之前起（同今天，`launch()`）；額外帳號等預設帳號第一次健康檢查通過或 30 秒後才開始，依索引順序、同時最多 2 個在起，一個名額在「子程式回了健康檢查」「不在起了（被擋、沒設定、spec 失敗、子程式結束）」或 30 秒時讓出（壞的標記、不擋其他）。等的時候每 0.5 秒檢查一次（子程式還沒聽 port 時只是連線被拒，後端看不到）。HM-09 審查（S-12）：某個帳號的啟動或就緒等待丟例外時（目前找不到會丟的路），記一行、讓出名額，其他帳號照起；預設帳號的等待也一樣。HM-10：每個帳號起子程式時拿它自己的 `mutation_lock`（第 3.2 節），面板正在存檔或重啟它時先等做完 |
| 啟動順序 | legacy 遷移（只對預設）→ 還原偵測、守門、休眠處理 → 預設帳號 → 錯開起額外帳號（壞的標記、不擋其他）。HM-13b 定案：守門在預設帳號的 store 開好之後、`ProfileManager` 或單帳號 runtime 建立之前跑（第 1.3 節）；守門沒做完就什麼都不起（沒有子程式、沒有 listener），下次開機重做；開關每次開機只讀一次，守門與 runtime 看到同一個答案 |
| 關閉 | 所有 `Supervisor.stop()` 並行，在 HA 停止上限 30 秒內收完（HM-09：`ProfileManager.stop_all()`，關閉時先停額外帳號的監看再並行停子程式；6 個都要 SIGKILL 的子程式約一個寬限期 3 秒收完）。HM-09 追補（2026-11-16，PR #103 的 CI；所有產品，不受開關管，第 1.2 節）：每個帳號的健康監看（沒開通的單帳號也是）與錯開啟動的就緒等待被取消時，就算 HTTP 堆疊把這次取消吃掉（anyio 4.15.1：每次新連線的 task group 取消自己的 scope、httpcore 的讀取期限；外部的 `cancel()` 剛好在那之後、task 再跑之前到，就併進 anyio 自己的 `CancelledError` 被吞掉），也在那次檢查做完時停（`HealthMonitor.check()` 比較檢查前後的 `Task.cancelling()`），所以 `_stop_monitors`、`remove()` 與收到 SIGTERM 的關閉不會被拖住；只改關閉，回應不變 |
| 健康監看 | 每帳號一個、自己的 httpx client、起點錯開；認證被拒 15→30→60→120→300 秒退避；開通後連兩次失敗才判 unreachable（DQ-25 已定：2026-11-15 11:2x 使用者採用建議；負責片 HM-09、HM-30）。HM-09 定案：起點＝預設帳號開機就查（同今天）、第 k 個額外帳號在自己的子程式起好後 15×(1＋k÷(產品額外帳號上限＋1)) 秒（Odoo：17.5、20、22.5…秒），之後每 15 秒；「認證被拒」＝健康探測原因開頭是各子程式固定的認證失敗文字（Odoo、Hermes `BACKEND_AUTH_REJECTED`；Headscale `HEADSCALE_INVALID_CREDENTIAL`；Nextcloud `BACKEND_HTTP_ERROR status=401`，以及登入失敗後的節流 `status=429`；EMQX、LiteLLM 的 401 文字），子程式回了其他答案就歸零，存檔與面板重啟（新的憑證）也歸零並在 15 秒內再查；「連兩次失敗」＝同一個子程式世代連續兩次「子程式有回、後端不通」才判 unreachable（才拒絕 tools/call），第一次維持前一次的判定（之前通就 reachable，剛起還沒判定就 unknown）；子程式沒回的檢查照今天記成未就緒（本來就不拒絕 tools/call），不算一次也不打斷連續；面板的 `backend/test` 照實回這一次的結果。子程式不在 running 時不送任何東西（port 可能是別的程式的，T-15）。沒開通照今天（每 15 秒、一次就判、不退避） |
| 監看失敗 | 額外帳號只標記 `failed`；預設帳號維持今天「任何元件停止就退出」（DQ-21 已定：2026-11-15 11:2x 使用者採用建議）。HM-09 定案：額外帳號的健康監看停止時，記一行 WARNING、停掉它的子程式並標成 `failed`（監看停了，那個帳號的可用性判斷就不再更新，不能照舊轉送）；其他帳號與 add-on 照常；面板存檔或 `child/restart` 讓子程式再起時，監看也一起恢復 |
| 資源 | 額外帳號子程式 exec 前寫 `/proc/self/oom_score_adj`＝500（絕對值）與 `setpriority(+5)`。HM-09 定案：由一個全新的單執行緒直譯器（`python -I -S -c`，同 PaaS `child_identity` 的包裝）在 fork 之後、exec 真正的指令之前寫，經管線回報結果；真正的指令拿到原本的 argv、環境（還原 PEP 538 加的 `LC_CTYPE`）、工作目錄與訊號處置。寫不進去（平台不准）就照起、`resource_state` 記下、每帳號每 60 秒一行 WARNING，不假設寫成功；沒有直譯器可跑包裝器（`sys.executable` 是空的）時也一樣照直接起、記一行（HM-09 審查 S-12）。預設帳號的子程式照今天直接 spawn |
| 記憶體 | 見第 5 節（HM-09 定案的部分） |
| 被擋的狀態 | HM-09 定案：`disabled_reason` 有值的帳號不起（開機、看門狗、面板重啟都不起）：`status=blocked`，`blocked_reason` 是 `port_conflict`→`child_port_conflict`、`memory_capacity`→`memory_capacity`、`profile_limit`→`null`（沒有對應的原因碼，看清單的 `disabled_reason`）。開通後 `child/restart` 的 202 回應多 `blocked_reason`（沒被擋是 `null`）；沒開通照今天 |
| 子程式 bearer（HM-06，不受開關管） | 剛好一個 `Authorization`、`hmac.compare_digest` 比對 `Bearer <WOOW_MCP_CHILD_TOKEN>`；不符 401（不寫細節）；環境變數缺、空或不符 `[A-Za-z0-9_-]{43}` 就拒絕啟動 |
| 後端 loopback（HM-20，受開關管） | 開通的產品的子程式環境多一個 `WOOW_MCP_DENY_LOOPBACK=1`，預設帳號與每個額外帳號的子程式都有（沒開通就沒有這個變數，spec 逐位元同今天）；子程式連設定的後端時，網址的字面位址或名稱解析出的任何一個位址是 127.0.0.0/8 或 ::1，整組拒絕、不連線（Python 子程式 `BACKEND_DESTINATION_DENIED`；Headscale 的子程式本來就一律拒 loopback、不看這個變數，回 `HEADSCALE_DESTINATION_DENIED`；n8n 另擋 0.0.0.0 與 IPv4-mapped，API 與官方 MCP 端點都擋）；變數的值不是 `1` 就拒絕啟動。n8n 的 webhook、chat、form 網址不受這條管（§8.8 #90） |
| log 事件 | 子程式啟動、結束（結束碼）、退避（下次秒數）、`failed`、`blocked`（原因碼）、監看認證退避、撞號、孤兒、隔離、還原守門逐帳號動作、休眠撤銷、缺哪些連線鍵（只列鍵名）；格式 `[profile=<id 前 8 碼> port=<p> pid=<n>]`；每帳號每情況 60 秒一行（`suppressed=N`）。HM-09 寫的（開通的產品才寫，logger `mcp_admin_core.lifecycle`，一律 WARNING，因為 add-on log 只顯示 WARNING 以上）：`MCP child [profile=… port=… pid=…]: started`／`exited with code N`／`next start in N s (attempt n)`／`failed after n starts; …`／`not started (<原因碼>): <固定說明>`／`child resources not applied (…)`／`could not be started (<例外類別>)`／`not started: no connection is saved yet (<欄位名>); …`／`the backend refused the credentials; next health check in N s`／`its health monitor stopped; …`／`MemAvailable cannot be read; …`／`its staggered start failed (<例外類別>); the other profiles start anyway`（HM-09 審查 S-12）；`child resources not applied (…: no interpreter for the wrapper); …` 也是同一行的一種。另外 logger `mcp_admin_core.profiles` 的 `multi-profile: the IPv6 test bind on <位址> is refused (<errno 名稱>); the spawn check skips that address`（HM-09 審查 S-6；每個位址與 errno 每個程序一行，不帶帳號）。撞號、孤兒、讀不到的帳號是 HM-08 寫的（logger `mcp_admin_core.profile_runtime`、`profile_router`）；隔離、還原守門逐帳號動作、休眠撤銷是 HM-13b。HM-13b 寫的（logger `mcp_admin_core.restore_lock`，不受開關管，一律 WARNING，只在守門有事做的那次開機）：`restore guard [profile=<default 或 id 前 8 碼>]: token revoked, child token renewed`／`…: its state cannot be read; its directory was moved to the quarantine (…)`／`…: its token could not be revoked (<例外類別>)`／`…: its state cannot be read and its directory could not be moved to the quarantine`／`…: its state is held by another writer; …`／`…: its operation receipts could not be archived`；不帶帳號的：權杖已回到備份當時的值（`… the MCP token is back to its value at the time of that backup …`）、全部撤銷（`… the MCP token of every profile (the default profile's included) was revoked …`）、休眠（`… the MCP token of <N> dormant profile(s) is revoked …`）、全部撤銷補完（`… a "revoke all" had not finished …`）、`the operation receipts beside the profile index could not be archived`、`the operation receipts beside the Origin policy could not be archived`（HM-27，和 HM-13b、HM-13c 合併後）、`the profiles directory cannot be listed; …`、`<名稱> was not a plain file; it was moved aside to <名稱>.quarantine-<UTC>`（帳號目錄裡的收據封存是 `restore guard [profile=<id 前 8 碼>]: <名稱> was not a plain file; …`）、`not finished (<原因>); nothing is served and no child is started. …`（原因是固定字串）、標記刪不掉的那一行；原文常數在 `restore_lock.py`。HM-13c：同一行 `MARKER_LEFT` 的原因多一種 `the panel notice could not be saved`（沒開通又沒有帳號資料時存不下還原提示）；`the panel notice of the restore could not be removed after the token changed; …`（提示檔刪不掉）；logger `mcp_admin_core.profile_admin` 的 `multi-profile: the child of profile <id 前 8 碼> did not start again after "revoke all" …`、`multi-profile: a quarantine directory of profile <id 前 8 碼> could not be removed completely; …`、`multi-profile: the credentials of a quarantine directory of profile <id 前 8 碼> could not be wiped before its deletion` |

## 8. 資料（摘要）

- 布局：預設帳號在 `/data/mcp/`（`state.json` 一個鍵都不加）；索引 `/data/mcp/profiles.json`；額外帳號 `/data/mcp/profiles/<24 hex>/`；
  還原用 `.instance-sentinel`、`.instance-record`、`.restore-detected`、`.revoke-all-pending`、`restore-record.json`（都不含秘密）。
  HM-13b 定案的其他名稱：`.instance-record.tmp`（record 換上之前的暫存檔，HM-13a）；`.state.json.operations.json.restored` 與
  `.profiles.json.operations.json.restored`（還原時封存的收據，每個收據檔只留 1 份）；`profiles/.quarantine-<id>-<UTC>[-n]`（隔離目錄）；
  `<守門的名稱>.quarantine-<UTC>[-n]`（守門自己的名稱被目錄占用時移開的項目，含還原紀錄與收據封存的名稱；只有偽造的備份會有）；寫到一半的暫存檔
  （`.restore-record.json.tmp-<hex>`、`.<收據檔>.tmp.<hex>`）只在中途斷電後留下，沒有人讀。HM-13c：`restore-notice.json`（還原後保留預設帳號
  權杖時的面板提示，只有時間；不受開關管，第 1.2 節）與它的暫存檔 `.restore-notice.json.tmp-<hex>`（同上，只在中途斷電後留下）；它也是守門
  被目錄占用時會移開的名稱（#120）。HM-27（開通的產品才有）：`origin-policy.json`（密鑰網址的 Origin 政策，面板第一次存檔才產生；
  不含秘密）、它的收據 `.origin-policy.json.operations.json`、存檔寫到一半的暫存檔 `.origin-policy.json-<hex>`（只在中途斷電後留下，
  沒有人讀）；還原時收據封存成 `.origin-policy.json.operations.json.restored`（同上，每個收據檔只留 1 份；也是守門被目錄占用時會移開的
  名稱）。政策檔不是守門的名稱：還原照原樣（第 1.3 節）。
- 沒開通、沒有帳號資料的安裝（今天的每個安裝；計畫 §3.3、§7.1）：上面的名稱一個都不產生（沒有索引、`profiles/`、sentinel、還原紀錄），
  只有偵測到還原時 entrypoint 多建一個標記、開機就刪。HM-13c 起多一個例外：還原後（預設帳號的權杖沒撤銷）多 `restore-notice.json`
  （只有時間，不含秘密），到預設帳號的權杖變了才刪（第 1.2 節）。沒有還原時開機只多查這一個名稱，什麼都不寫。
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
第 90 列是 HM-20 補的列（DQ-10 子題 2026-11-15 定案；FM-84 的對齊作法欄）。
第 91～95 列出自 HM-14 的實作，第 96～99 列是 HM-14 獨立審查（MF-2、S-1、S-7、S-5）補的列，第 100 列是 HM-14 rebase 到 HM-09
之後補的列（都不是 FEATURE-MATRIX 的列）。
第 101～107 列出自 HM-31（對齊 PaaS #155），#15、#16、#96 也由 HM-31 改寫；第 108 列與 #81、#101 的補寫出自 HM-31 獨立審查（MF-1、MF-3、MF-2）（寫的時候 FEATURE-MATRIX 還沒有對應的列；之後補的 FM-154 對到它們）。
第 109～112 列是 HM-11 對齊 HM-10 的真後端時補的面板列（不是 FEATURE-MATRIX 的列）。
第 113～115 列出自 HM-12 的實作（換身分換 token 與新來源重填秘密的細節；不是 FEATURE-MATRIX 的列）。原稿是第 109～111 列：HM-11 先合併、用掉第 109～112 列，本片 rebase 後往後重編（第 10 節）。
#17 的附註出自 HM-30 的實作（不是 FEATURE-MATRIX 的列；`deviation-trace.md` 由 repo 外的產生器重產，沒有這個附註）。
第 116、117 列是 HM-12 的面板部分（另一個 PR）補的面板列（不是 FEATURE-MATRIX 的列）。
第 118～121 列出自 HM-13b 的實作（開機守門；不是 FEATURE-MATRIX 的列，`deviation-trace.md` 沒有）；#24、#67、#82 的附註也是。
第 122、123 列出自 HM-13c 的實作（單帳號還原後的面板提示：使用者 2026-11-16 定案；隔離目錄的清單與刪除；不是 FEATURE-MATRIX 的列，`deviation-trace.md` 沒有）；#58、#67、#82 的 HM-13c 附註也是。HM-13c 獨立審查的修正只補 #58、#82、#123 的附註，沒有新列。
第 124～128 列出自 HM-27 的實作（密鑰網址的服務層級 Origin 清單；#9、#10、#42 由 HM-27 定案改寫；不是 FEATURE-MATRIX 的列，`deviation-trace.md` 沒有這幾列）。原稿是第 118～122 列：HM-13b（#108）、HM-13c（#112）先合併、用掉第 118～123 列，本片合併時往後重編（第 10 節）。
2026-11-17 文件同步重產 `deviation-trace.md`（到第 117 列）：第 87 列以後的列，FEATURE-MATRIX 有說到同一件事的列就加進那一列的「對到」
（例如 FM-154 → #101～#108、FM-81 → #113、#114）；沒有任何 FEATURE-MATRIX、G6 §5 的列對到的（#22、#33、#83、#88、#89、#90、#99），
出處寫在 `deviation-trace.md` 文末「差異表每一列的來處」。

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
| 9 | Headscale Origin 清單 | 只放自己的管理網址（claude.ai 403；R07 X-17）；一律 enforce，被拒記一行 deny；清單內來源回精確 CORS 與 preflight | 只放 `https://claude.ai`；HM-27 起開通後也照舊：原字串比對、不正規化、不記紀錄、沒有 CORS，沒有服務層級政策（`/api/origin-policy` 的 GET 與形狀正確的 PUT 回未知操作的 404，其他方法 405、形狀錯的 PUT 400；第 2.6 節） | 使用者對 HA Headscale 的決定（R01 H-08） | 既有 |
| 10 | Bearer 帶 Origin | （沒有 Bearer） | 一律 403，不記紀錄、不看服務層級政策（HM-27 定案：照舊，沒有放行）；DQ-11 第二問（S14 實測後要不要精確放行 `https://claude.ai`）仍待使用者決定 | 瀏覽器不在 Bearer 契約 | 既有（HM-27 定案照舊；第二問待決） |
| 11 | 管理身分 | 密碼＋JWT | Ingress＋HA 角色，每請求查 | 平台不同 | 部署 |
| 12 | 管理管線 | 中介層先驗登入 | 看狀態前先驗角色、提交前再驗一次（第 3.2 節） | I10；HA 角色每請求查 | 部署 |
| 13 | listener 身分檢查 | 轉發前必過 | 讀得到才做，讀不到降級（HM-15，條件式） | HA AppArmor 未確認；不讓整台停擺 | 部署 |
| 14 | 子程式重啟 | 2→300 秒、不限次數、120 秒歸零；spawn 失敗（指令找不到等）就停住，等手動重啟 | 開通的產品相同（DQ-20 採 (b)），spawn 失敗也照退避重試（HM-09）；沒開通維持 4 次後 failed | 沒開通維持今天；HA 的子程式指令固定在映像裡，spawn 失敗多半是暫時的（fork 時記憶體不夠等） | 部署 |
| 15 | 名額 | 每帳號連線 64、串流 32、等 10 秒、排隊 32＋保留 8；共用池；請求內容位元組預算全域＋每帳號份額（#155） | 讀 body 前准入（64／32）、轉送 32／16 等 1 秒、串流 24／8、排隊 32／16＋保留 4、待送回覆額度；沒有共用池。請求內容位元組預算照 PaaS（HM-31）：全 add-on 一份＋每帳號份額（差異見 #101～#104）。附註（HM-08 審查 S-5、S-6；HM-31 改）：全 add-on 共用的只有兩樣：(1) 請求內容位元組預算（PaaS 同；HM-08 的拒絕小額度 HM-31 拿掉）；(2) 8081 外框的連線數（閒置 keep-alive、沒帶 token 的連線也算），滿了任何人都拿 uvicorn 純文字 503（既有，G2 S7）。每帳號隔離在請求層 | HA 沒有 cgroup、硬體小（G3-24）；DQ-07 採 (a) | 部署 |
| 16 | 讀 body 前拒絕的回應碼（准入） | 先讀 body，帶 id 一律 200＋`-32003` | 准入滿：≤64 KiB 讀出 id 回 200＋`-32003`；更大的不讀、503。位元組預算放不下的照 PaaS（HM-31：讀完丟掉、從頭尾找 id，200 或 503），不在這一列。附註（HM-08 審查 S-6）：batch 算沒有 id。HA 閘道平常就不收 batch（`policy.authorize` 的 `single JSON-RPC request required` → 403；PaaS 會轉送），過載時 HA 回 503＋`id: null`，PaaS 每個 id 一則 200 | 讀 body 前准入防單一帳號吃光 listener（C3-MF-2） | 部署 |
| 17 | 回覆處理 | 事件迴圈內 | 一條工作執行緒、依帳號輪流。附註（HM-30）：工作執行緒在檢查點讓迴圈先跑（GIL convoy，第 6 節）；回覆做好後到 server 收走前另有待送回覆額度（每帳號 32 MiB；JSON 回覆在放掉轉送名額之前就扣、排隊的 tools/call 拿到名額之後再查一次；軟上限：一次湧入最多上限＋轉送名額個回覆，第 5 節，D2）；D1：工作執行緒分段序列化（位元組相同）、大的 SSE 事件在工作執行緒切框、扁平陣列也每 1,024 個數字或成員喘息；D3：開通時回覆每段一次 token 檢查 | HA 硬體慢、單一迴圈（第 6 節） | 部署 |
| 18 | 健康檢查 | 沒有定期後端監看（FM-68） | 每帳號監看、連兩次失敗才判壞、認證退避 | HA 既有監看；Odoo 以來源 IP 冷卻 | 部署 |
| 19 | 容量檢查 | cgroup 公式（建立時）；沒有 FD 預算 | MemAvailable（建立、存後端、起子程式時）；讀得到 cgroup 才用公式；錯誤多帶 `available_memory_mib`。另有 FD 預算（#87）：開機時 FD 上限提不到額外帳號要的量，就只服務預設帳號（HM-08），這時建立回 409 `profile_limit_reached`、`limit` 0、什麼都不寫（HM-10） | HA 沒有 cgroup；add-on 容器的 FD 上限由容器決定（第 5 節；HM-03a 實測） | 部署 |
| 20 | 還原 | 手冊＋restore_guard（k8s Job） | entrypoint＋sentinel 偵測、開機守門、讀不到就隔離 | Supervisor 沒有 hook | 部署 |
| 21 | 還原時預設帳號 | 一律撤銷 | DQ-03 採 (b) A2：只有磁碟上有帳號資料的還原才撤銷預設帳號 | 白名單落後＋還原換回舊版 | 部署 |
| 22 | 還原後 token 歷史 | 清空（R04 S-15） | 保留，加一筆 revoke | 不改 schema | 部署 |
| 23 | 孤兒 | 讓還原停機（Pc/restore_guard.py:443-446） | 只隔離、不擋開機 | 不讓含孤兒的備份永遠起不來（G1:435） | 加嚴（建議回補） |
| 24 | 休眠帳號 | 沒有（沒有產品開關） | 沒開通的版本撤銷休眠帳號 token（HM-13b：每次開機只撤銷還沒撤銷的，已撤銷的不寫任何東西；開不了的隔離；bootstrap 只多 `dormant_profiles`） | 開關＝發版（第 1.2 節） | 部署 |
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
| 42 | 密鑰路徑 Origin | 服務層級清單＋模式（環境變數；預設 report-only）：清單外 report-only 記 would_deny、交給 #136 之前的 CORS（反射任意來源＋credentials），enforce 403；清單內來源回精確 CORS 與 preflight 200；沒有 Origin 放行 | 服務層級清單（全部帳號共用；預設 `https://claude.ai`、report-only；`/data/mcp/origin-policy.json`，面板改）：清單外 report-only 照常服務、回應逐位元不變、記 would_deny，enforce 403；兩種模式都不加 CORS、沒有 preflight 回答（OPTIONS 照今天 405）；沒有 Origin 放行（HM-27 定案，第 2.6 節） | 不放寬（FM-74；DQ-11 採 (a)，使用者 2026-11-14） | 加嚴（HM-27 定案） |
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
| 58 | 還原前盤點與核對 | 手冊步驟 1 事前盤點（不含憑證）、步驟 9 三段核對後才在步驟 10 發 token | 看不到還原前狀態：事後核對卡，逐帳號「已核對」才可重發；事前匯出帳號清單選做。HM-13c：`GET profiles/restore-record`、`POST profiles/<id>/restore-review`（寫 `reviewed_at`）；守門撤銷的帳號在核對前 `token/rotate` 409 `restore_review_required`（紀錄讀不到時 503，一律擋）；預設 bootstrap 的 `restore_review`、帳號的 `restore_review_required`；匯出由面板做（依允許清單從每個帳號的 bootstrap 取清單列、後端的非秘密欄位與政策，沒有新路由、不含任何權杖或憑證）。HM-13c 審查修正：休眠開機寫紀錄時保留上一份還在等的核對（預設帳號那一列、還原段落），上一份讀不到就不改它；紀錄讀不到時，全部撤銷做完會重寫（每個帳號待核對）；開關關時沒有關卡，重新開通後那一列仍待核對（MF-1、S-2、S-3） | Supervisor 還原先刪資料、沒有 hook | 部署 |
| 59 | 換身分換 token 的歷史動作名 | `backend_identity_change` | 沿用 `rotate` | history 只收 rotate／revoke，不改 schema（FM-09） | 部署 |
| 60 | Odoo 讀取並行 | 讀取工具預設 8 條工作緒 | 1 條 | 不同時改並行度與多帳號（DQ-30 待定，建議維持 1） | 待決 |
| 61 | Odoo reviewed methods 的預設來源 | 沒存過時讀容器 env（全帳號共用） | 只從各帳號 state 組，不繼承容器 env | HA 既有（隔離更好） | 既有 |
| 62 | n8n session 名額與滿了的回應 | 每帳號 20、逾時 900 秒；上游 429 原文轉回；`AUTH_RATE_LIMIT_MAX` 1000 | 每帳號 20、逾時 600 秒；閘道回 429「Too Many Requests」；上游預設限流 | HA 既有；DQ-22 細節待定 | 待決 |
| 63 | Hermes Dashboard | 管理端有 Dashboard 代理（cookie 快取 key 帶帳號，刪帳號清除） | 沒有管理端代理；子程式內 cookie 每個子程式一份 | HA 沒有 Dashboard 代理頁 | 既有 |
| 64 | LiteLLM 寫入權限 | `LITELLM_MCP_READONLY` 一個開關 | 逐支工具授權 | HA 既有政策模型 | 既有 |
| 65 | EMQX 子程式端政策 | 子程式每次呼叫讀自己帳號的設定再擋一次 | 只在閘道擋；子程式只收 READONLY 與 DISABLED_TOOLS | 閘道政策＋每帳號子程式＋bearer（DQ-27 待定，建議不做） | 待決 |
| 66 | 還原的舊 schema 預設 state | restore guard 設 `RESTORE_POLICY_HOLD`，保留還原回來的舊政策 | 照 2026-10-27 決定做全開遷移，留復原紀錄與面板通知；額外帳號一出生就是 schema 4 | HA owner-defaults 規則；只在還原拉不到舊映像時發生（UC-24） | 既有 |
| 67 | 還原收據封存 | 封存 bundle、可壓縮，重複還原保留每一份；還原前的舊操作 id 回 410 `operation_id_expired` | 每帳號只留最近 1 份 `.restored`；舊操作 id 回 410 `operation_restored`（HM-13b：新收據檔多一個 `restored_before_ms`；沒有收據的收據檔不再封存，重做時不會用空檔蓋掉封存；索引旁的收據也封存）。`restored_before_ms` 不早於被封存收據檔最新的 id 或下限（同 PaaS `max(cutoff_ms, journal_floors[...])`），但最多比還原當下晚 24 小時（`TTL_MS`；PaaS 沒有上限，`Pc/restore_guard.py:513-516`；HM-13b 審查 S-6）。HM-13c：守門處理的每個收據檔都換新，備份時沒有收據檔的帳號與索引旁也寫一份（同 PaaS 每份設定都換新），備份後才做、隨還原消失的操作 id 也回 410；#121 的預設帳號除外。HM-27（和 HM-13b、HM-13c 合併後）：Origin 政策旁的收據也一樣封存、換新 | entrypoint 修復項目上限（512 項、8 層）；代碼分開，看得出是還原造成（FM-07）。24 小時上限：偽造備份裡遠在未來的 id 不會讓之後的新操作好幾年都 410；代價是主機時鐘慢超過 24 小時時，備份裡較新的 id 在時鐘校正後可能被當成新操作（`threat-model.md` 第 3 節） | 部署 |
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
| 81 | 請求內容超過上限 | 最多再讀 128 MiB 丟掉才回錯誤，讓經反向代理的用戶端看得到錯誤、不是 RST（Pc/request_limits.py:16） | 一超過就 413（n8n 是 JSON-RPC 錯誤本體）、不再讀後面的內容（Hc/gateway.py:270-271；Hc/request_limits.py:51-70）；宣告超過的在讀第一個位元組之前就回同一個 413（HM-31 審查 MF-3；n8n 本來就這樣），不扣預算 | FM-52 延後：只在前面有 Cloudflare Tunnel 或反向代理時有感（HM-14 選做；HM-14 沒做，仍延後） | 既有 |
| 82 | 全部撤銷 | 沒有面板或 API；還原時照手冊撤銷全部（docs/paas-config-restore-runbook.md） | `POST {base}/api/profiles/revoke-all`（含預設帳號）＋`.revoke-all-pending`；逐帳號結果，寫入失敗的帳號 503、重啟時守門重做（第 2.3、3.1 節）。HM-13b：開機補完不看開關（沒開通、沒有帳號資料也撤銷預設帳號：管理員要求過）；標記內容不看，任何種類的項目都算；持有 writer lock 的帳號只算失敗、不隔離（第 1.3 節）。HM-13c：路由拿全 add-on 帳號鎖、預設帳號鎖與每個已登錄帳號的鎖（依 id）後才做第二次角色檢查；索引不能用時收壞索引的 ETag；在工作執行緒跑；撤銷了的重起子程式；沒做完回 409 `operation_outcome_unknown`＋逐帳號 `results`、收據停在結果未知，失敗帳號撤銷前的權杖在 8081 回 503，到下一次全部撤銷做完或重開（重開時守門補完）；撤銷了預設帳號就刪還原提示。HM-13c 審查修正：意外的例外也當結果未知（每個已登錄帳號的舊權杖 503）；503 名單只擋之後才經分派器比對的請求（S-4、S-6） | HA 沒有 shell 跑手冊；事故止血第一步、回退後再升級都要靠它（threat-model.md 第 4 節；§8.8 #69）；FM-120 | 加嚴（建議回補） |
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
| 101 | 位元組預算的每帳號份額 | 全域的一半（至少 16 MiB），沒有上限 | min(該帳號的位元組額度 64 MiB, max(16 MiB, 全 add-on÷2))：開關關的預設帳號也一樣 | DQ-07 的 64 MiB 保留成份額的上限（不改使用者定的數值；主對話 2026-11-16 定案）；HA 的 add-on 和整台機器共用記憶體，份額上限把一個 token 能扣的位元組限在 64 MiB。實際記憶體另乘放大倍數：HA 閘道自己最高約 14～28 倍（第 5 節「單一帳號有界」；HM-31 審查 MF-2），閘道＋子程式待 HM-19c | 加嚴 |
| 102 | 位元組預算扣的大小 | 收到的位元組（轉送原樣的 body） | 收到的與轉送給子程式的兩者較大的（閘道重新序列化：中文 2 倍、emoji 3 倍、數字最多約 4.5 倍）；轉送的大小放不下就不送、回 `-32003` | HA 閘道轉送前重新序列化（既有）；只算收到的會少算轉送的那份（HM-08 審查 S-1） | 加嚴 |
| 103 | 位元組預算的推導來源 | cgroup 記憶體上限；沒有上限固定 32 MiB | cgroup 上限；沒有就用 MemAvailable 減保留量 256 MiB（啟動時讀一次）；兩者都讀不到固定 32 MiB；帳號數沒開通算 1 | HA 的 add-on 沒有 Pod 記憶體上限（計畫 §5.2 的記憶體檢查）；HM-19c 量測後定案 | 部署 |
| 104 | 位元組預算與逾時的設定入口 | `MCP_GATEWAY_MAX_BUFFERED_BYTES`、`…_PER_PROFILE`、`MCP_GATEWAY_BODY_IDLE_SECONDS`、`…_TOTAL_SECONDS` 環境變數，不合法記 WARNING | 程式常數，不讀環境變數 | 同 #45（add-on options 維持 `{}`，改數值要回功能 PR） | 部署 |
| 105 | 大請求的整體讀取上限 | 已登記的大請求 300 秒（`MCP_GATEWAY_BODY_TOTAL_SECONDS`），逾時 408＋`-32003`；小請求沒有上限 | 每個請求 60 秒（`BODY_SECONDS`，既有），逾時照今天 408 `{"error":"request denied"}`；閒置 30 秒照 PaaS（408＋`-32003`＋`Connection: close`） | HA 既有的整體上限比 PaaS 嚴，涓流上傳最多佔住預算 60 秒（PaaS 300 秒）；回應形狀照今天，不改單帳號既有的 408（主對話 2026-11-16 定案） | 既有 |
| 106 | Headscale 的結構上限 | Headscale 自己的 `McpRequestLimits`：1 MiB、8,192 個工具參數元素、深度 32；整個請求 20 萬個元素 | 和其他產品一樣：16 MiB、深度 64、20 萬個元素（`gateway.STRUCTURE_LIMITS`） | HA 的 Headscale 今天就沒有自己的請求上限（既有差異，不在 #155） | 既有 |
| 107 | 不是 JSON 的 body | 照舊轉給子程式（結構守門不判違規） | 照今天 400 `{"error":"request denied"}`（strict JSON，在任何名額之前） | HA 既有的 strict JSON（重複鍵、NaN、單獨代理字元都 400） | 既有 |
| 108 | 宣告長度與 `Transfer-Encoding` | `proxy._declared_length` 只看 `content-length`；宣告了就只在讀之前扣宣告值（`_count_stream` 只在沒宣告時邊讀邊數）。PaaS 的 uvicorn 用 httptools，llhttp 預設拒絕同時帶 `Content-Length` 與 `Transfer-Encoding` 的請求（未實測） | HA 的 HTTP 解析器是 h11 0.16.0（根目錄 venv 是 `uvicorn==0.38.0`，沒有 httptools）：照 chunked 讀，`content-length` 原樣交給 app。帶 `Transfer-Encoding` 的請求，`Content-Length` 一律當成沒宣告（RFC 9112 §6.3）；收到的位元組不管宣告多少都照數（`request_budget.declared_length`、`watch`，准入滿時的讀取用同一條規則；HM-31 審查 MF-1、S-6）。CL＋TE 照 chunked 處理、不直接回 400，連線也照 h11 的規則不關（RFC 9112 §6.1 要求關；既有）。主對話 2026-11-16 定案：直接回 400 並關連線不在 HM-31 做（會改單帳號回應），列入已知限制（威脅模型第 3 節）與 HM-29 回補 PaaS 的題目 | 不這樣做時，宣告 10 位元組、實際用 chunked 送 10 MiB 的請求整個讀進記憶體，不扣預算、不看閒置（審查實測，開關關與開都中）；照實際收到的位元組計數列入給 PaaS 的回補建議 | 部署 |
| 109 | 刪除帳號與隔離帳號索引的確認 | 刪除只有一段確認（「Confirm delete profile」，`Pui/components/ProfileChooser.jsx`）；沒有索引隔離（索引壞整台 503，#25） | 刪除（含孤兒與讀不到的帳號）與索引隔離都要兩段確認：第一段寫明後果（權杖立即撤銷、後端憑證抹除、面板無法復原、只有還原備份才回來；隔離另說預設帳號立刻恢復、額外帳號變成孤兒），第二段「最後確認」（HM-11） | DQ-14 已定（兩段確認，2026-11-15 17:4x） | 加嚴 |
| 110 | 面板的第一個 bootstrap | 永遠帶目前的帳號（`Pui/api.js` 的 `X-MCP-Profile`，預設 `default`；沒帶時伺服器也當 `default`，#31） | 每次開面板的第一個 bootstrap 刻意不帶 `X-MCP-Profile`：沒開通的伺服器照今天回 200；開通的回 400 `profile_id_required`（角色檢查之後），面板就改成每個帳號範圍請求都帶（含明確的 `default`）。這是第 3.3 節「面板開通後每個帳號範圍請求都帶」的唯一例外，I12 仍成立（伺服器拒絕沒帶的請求）；瀏覽器 console 因此每次開面板記一筆 400（HM-11） | 同一份面板要服務開通與沒開通的產品；沒開通時請求逐位元不變（HM-01） | 部署 |
| 111 | 帳號清單不能用時的面板 | 清單讀不到，整個面板只剩「Could not load profiles」與 Retry（`Pui/AdminApp.jsx`） | 不鎖面板：預設帳號照常可用，選單只剩預設帳號（與目前顯示的帳號），新增、改名、刪除停用並顯示固定說明；清單沒帶格式正確的 `ETag`（索引版本）時照列、但唯讀；這個瀏覽器顯示不了的名稱只藏那一列的名稱（以 id 前 8 碼稱呼，仍可切換、改名、刪除），回聲的名稱只檢查形狀。索引壞、或清單讀不到或格式不合時的替代清單（只剩預設帳號）不當成帳號已刪除的證據（不清收據）；沒帶 `ETag` 的清單與藏名稱的列仍是伺服器給的完整清單，照常算（帳號不在裡面就當已刪除、清它的收據）（HM-11 審查 S-2、對齊審查 S-7） | 清單的版本只在 `ETag` 回應標頭，Ingress 與使用者的反向代理會不會保留待 HM-03a；伺服器（Python 3.13 的 Unicode 15.1）和舊 WebView 認得的字不同（DQ-16 拒絕未指派字元） | 部署 |
| 112 | 孤兒在面板 | 沒有孤兒清單（#51）；刪除只收索引裡的帳號（#34） | 「診斷與維護」列出清單的 `orphans`、逐筆刪除（兩段確認，#109）；選單下方提示筆數；刪除時一併清掉它在這個分頁的待確認收據（HM-11） | DQ-14 已定（孤兒不自動刪、面板列出可刪） | 加嚴 |
| 113 | 換身分存檔的回應 | Odoo 連線存檔的回應一律帶 `token_rotated`（true／false），另有 `status`、`apply_state`、`message` 等欄位，換了 token 時 `message` 多一句「到 Tokens 複製新網址」（`apps/odoo/odoo_mcp_admin/routers/config.py:66-73,136-138`） | 只有換了 token 的存檔帶 `"token_rotated":true`（200，與形狀 D 的 503）；沒換時回應照今天逐位元，沒有這個鍵（開通後預設帳號的 HM-01 管理契約凍結也不變）；不帶文字，面板依 `token_rotated===true` 自己提示 | HA 既有的管理契約（#86）：不為多帳號改既有回應；面板只認代碼與旗標（#49） | 既有 |
| 114 | 換身分途中失敗 | 在 store 的鎖內、寫入前停舊子程式；寫入失敗就重起舊子程式、舊 token 照舊（`Pc/connection_apply.py:23-45` `save_bound_connection`、`Pc/config/store.py:502-533`；快取沒變，檔案在 replace 之前失敗時也沒變）；停失敗也試著重起舊子程式後把例外丟出去 | 停不下：什麼都不寫、用舊 state 重起、503 `{"error":"request denied"}`；寫入失敗一律 503 `{"error":"state unavailable"}`（不管丟出什麼例外），是否重起看磁碟上的 token：store 拒絕寫入、或新的 state 檔寫不出來（取代舊檔之前）：同 PaaS（什麼都沒寫、舊 token 照舊可用、舊子程式用舊 state 重起）；取代 state 檔途中失敗（`os.replace` 或之後的目錄 fsync）：不知道寫成了沒有，store 照今天毒化（該帳號到 add-on 重啟前不服務：新檔還沒換上時舊 token 回 503，已換上時分派器不路由它、兩把 token 都是未知 token；預設帳號的新檔已換上時 8081 所有帶 token 的請求都 503，同第 2.3 節）、不重起舊子程式；寫入丟出例外但新 token 已在磁碟上（取代之後的清理失敗，store 照常）：也不重起，新 token 只拿到閘道自己的回答；重啟後照磁碟上的（token 與身分一起）；新子程式起不來：token 已換、舊子程式不再起，形狀 D＋`token_rotated:true`；每種失敗各記一行 WARNING（帳號 id 前 8 碼、子程式有沒有重起） | HA 的 store 寫入失敗一律毒化（`Hc/config.py` `_write`：結果不明就不再讀寫，fail closed）；只有這條路在取代舊檔之前的失敗不毒化（`_write(poison_before_replace=False)`：那時磁碟上一定還是舊檔，正是 PaaS 舊 token 照舊可用的情況）。PaaS 在 replace 之後失敗時快取留舊值、磁碟可能已是新值（兩邊不一致），HA 寧可 503 到重啟；新 token 可能已在磁碟上時，舊憑證的子程式不再服務任何人（UC-21） | 既有 |
| 115 | 新來源要重填秘密的判定 | 只有 Headscale：舊網址有值、正規化後的整條網址改了、舊秘密有值、秘密選「沿用」→ 422；`base_url`↔`api_key`、`paas_base_url`↔`paas_api_token`（`apps/headscale/headscale_mcp_admin/connection.py:104-109`） | 開通後全部產品的 `backend/patch`：網址的來源（scheme、host、有效 port）改了才算；每條網址只要它會送去、而且已存的秘密（`identity_fields.URL_SECRETS`）；只改路徑不算（HA 的 Headscale 網址本來就只存來源，等同 PaaS；其他產品同一來源依路徑分流到不同後端時，已存秘密會跟著送過去，列為已知限制，威脅模型第 3 節）；網址清空或第一次設定不算；`backend` 整份取代不檢查（一定帶秘密） | 秘密送到哪台伺服器由來源決定（RFC 6454）；DQ-40 ⑨ 的範圍是「scheme／host／port」；只有 Headscale 有這條規則的 PaaS 列入回補建議（HM-29） | 加嚴 |
| 116 | 換身分存檔後的面板 | 存檔的回應帶 `token_rotated` 與 `message`；Odoo 換了 token 時 `message` 多一句「Account changed: old MCP URL revoked. Copy the new URL from Tokens.」（`apps/odoo/odoo_mcp_admin/routers/config.py:136-138`；核心 `Pc/routers/settings.py:477-487`）；共用面板只顯示 `message`、不讀 `token_rotated`（`Pui/pages/ConnectionConfig.jsx:299`） | 面板依 `token_rotated===true` 自己提示（200 與形狀 D 都是）：「後端身分已變更，這個帳號的 MCP 權杖已換新…請到「連線與權杖」顯示並複製新的權杖」，藏起已顯示的權杖、重新讀取狀態（遮罩與權杖歷史變了）；形狀 D 的錯誤提示把「已存檔、子行程沒起來」與換 token 兩件事都說出來；換了 token 之後重新讀取狀態失敗（例如連線中斷）時，提示仍先說換 token、再接失敗的原因（錯誤樣式；HM-12 面板審查 S-2）；回應裡伺服器的文字一律不顯示；下一次存檔照今天用重新讀到的設定版本（等於回應的 `ETag`，#113）。開通、會換 token 的產品（`Hui/contracts.js` 的 `identityBound`＝`products.IDENTITY_BOUND`）的後端存檔回 503 `{"error":"state unavailable"}` 時另提示「存檔結果不明時請重新啟動 add-on，之後到「連線與權杖」確認 MCP 網址」（結果不明時重啟後 token 可能已換，這次的回應不會說，#114；HM-12 審查 S-7）；503 `{"error":"request denied"}` 照今天的文字。沒開通時這些回應不會出現，面板照今天（HM-12 面板） | 回應不帶文字（#113、#49），提示由面板依旗標決定；結果不明只在 HA 有（#114：寫入途中失敗毒化到重啟） | 既有 |
| 117 | 新來源要重填秘密的表單 | 只有 Headscale：送出後伺服器回 422，面板顯示「控制台位址已變更，請同時替換或清除原有金鑰。」（`apps/headscale/static/assets/app.js:10`）；送出前不檢查 | 開通後全部產品的「修改個別欄位」：網址改到另一個來源時，那條網址會送去、而且已存的秘密（`Hui/contracts.js` 的 `urlSecrets`＝`identity_fields.URL_SECRETS`）不能選「保留已儲存憑證」，改成必填（選填的可以明確清除）並寫明原因，送出前就擋；改回同一個來源就恢復（已打的值留著）；伺服器不顯示值（withheld）的網址當成換了（安全的方向），原因寫「伺服器不顯示原網址，無法確認是同一台伺服器」；表單上方的說明只在產品的網址帶秘密時才有（OpenDesign 沒有；HM-12 面板審查 S-7）。來源照後端 `backend_edit.origin` 的算法比（`urlOrigin`；兩張表與來源由 `tests/test_identity_fields.py` 逐案核對）。仍收到 422 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 時只顯示固定文字（沒有回聲、不顯示送出的值），打過的秘密清掉。沒開通照今天：可以沿用（HM-12 面板） | 送出前就要求重填，比收到 422 再重填少一次來回；後端規則見 #115 | 加嚴 |
| 118 | 還原後獨立驗證比對的基準 | `restore_inplace._verify` 比對來源備份裡的每個憑證（`_credentials(source)`）：備份本身一直在 | 比對這次開機在守門第 A 步讀到的快照（磁碟上當下的每個 token 與 child_token）；中途斷電後重做時，上一次已換掉的舊值已不在磁碟上，快照裡是當下的值，而備份裡還留在磁碟上的值一定在快照裡；child_token 每次重做都再換一次（第 1.3 節） | Supervisor 還原沒有留下備份副本可比；守門要能在任何一步斷電後重做 | 部署 |
| 119 | 還原樹裡 `profiles` 不是目錄 | 任何不在白名單的型別或名稱都讓還原停機（`RestoreError`） | `profiles` 確定不是目錄（一般檔、連結）時：記一行 WARNING、紀錄 `profiles_directory: unlistable`、照撤銷預設帳號（有帳號資料）後照常啟動；裡面什麼都不會被開或路由（開通後 HM-08 對每個 token 回 503，修好後重啟才恢復）。`profiles` 是目錄（或查不出是什麼）卻列不出來時和 PaaS 一樣停：守門沒做完、標記留著、什麼都不服務，下次開機列得出來才做完（HM-13b 審查 MF-2；全部撤銷也一樣不算做完） | 不讓一份怪的備份永遠起不來（同 #23 的理由）；裡面的東西同 uid 才放得進去（DQ-37）。列不出來的目錄裡可能有備份的 token，照常啟動會讓它們復活（I9），所以不放行 | 部署 |
| 120 | 守門自己的名稱被目錄占用 | 不在白名單的項目讓還原停機 | sentinel、record、record 暫存檔、還原標記、全部撤銷標記、`restore-record.json`、收據封存（`.state.json.operations.json.restored`、`.profiles.json.operations.json.restored`；HM-27 起加 `.origin-policy.json.operations.json.restored`）的名稱若是目錄（偽造的備份），改名放到 `<名稱>.quarantine-<UTC>[-n]` 再重建、刪標記、寫紀錄或封存，從不刪除（HM-13a 審查 SF-7：不改的話每次重建都失敗、add-on 再也起不來；紀錄與封存的名稱是 HM-13b 審查 S-1 補的） | 同 #119；不刪使用者的東西（同索引隔離） | 部署 |
| 121 | 沒有帳號資料時預設帳號的收據 | 每份設定都換新收據檔、舊 id 一律 410 | DQ-03 (b) 不撤銷預設帳號時，它的收據檔照還原的原樣（24 小時內重送備份前的 id 回 completed，不回 token，和今天一樣）；有帳號資料（預設帳號被撤銷）時才封存 | DQ-03 (b)：單帳號安裝的還原行為和今天一樣 | 部署 |
| 122 | 還原後沿用權杖的面板提示 | 沒有（還原一律撤銷全部 token，手冊步驟 10 重發；PaaS 沒有產品開關） | DQ-03 (b) 不撤銷預設帳號時（沒有帳號資料，開通與否），守門在刪還原標記前存 `restore-notice.json`（只有時間），bootstrap 多 `restore_notice`，到預設帳號的權杖變了（`token/rotate`、撤銷了的 `token/revoke`、全部撤銷）才刪；不受開關管（第 1.2 節）。面板「知道了」只藏到重新整理（面板不用瀏覽器儲存，N15）；沒開通時不加任何管理路由 | DQ-03 (b) 原文「面板與 log 提示權杖已回到備份當時的值」；使用者 2026-11-16 對 HM-13b 審查 Q-1 定案，只核准 bootstrap 多一個欄位 | 部署 |
| 123 | 隔離目錄的清單與刪除 | 沒有隔離目錄（還原遇到讀不到的設定就停機，#23） | 帳號清單有隔離目錄時另帶 `quarantined`（`<id>-<UTC>[-n]` 與 id）；`POST profiles/quarantine/<名稱>/delete`（If-Match、Idempotency-Key、全域收據；照刪除的規則：讀得到的先撤銷並抹憑證，再不跟隨連結地刪）；不能選擇、不路由、不能改名或重發；面板列前 64 個並說還有幾個，清單不會因為數量而讀不到（HM-13c 審查 S-5） | #23 只隔離、不擋開機，留下的資料要有出路；DQ-14 不自動刪 | 部署 |
| 124 | Origin 檢查的位置 | 中介層，在認證與選帳號之前：錯 token 的請求也判斷、也記，紀錄不知道帳號（R04 S-09） | token 驗過之後、方法檢查（405）之後、query 檢查（400）之前，今天 Headscale 規則的位置：錯 token 照今天 404，碰不到政策、寫不出紀錄；紀錄帶帳號 id 前 8 碼（HM-27） | 未認證的請求灌不進紀錄（比 PaaS K-09 好；FM-73 的 HA 平台差異欄）；HA 閘道既有的檢查順序（HM-01 凍結的 `order-` 案例） | 既有 |
| 125 | enforce 的拒絕本體 | 403 `{"detail":"ORIGIN_DENIED"}`，不帶 CORS | 403 `{"error":"request denied"}`（閘道的固定本體，同 Bearer 帶 Origin 與 Headscale；HM-27） | HA 的 MCP 端錯誤只用固定本體（第 4.2 節） | 既有 |
| 126 | Origin 政策的設定入口與壞值 | 環境變數 `MCP_ADMIN_ALLOWED_ORIGINS`、`MCP_ADMIN_ORIGIN_MODE`（chart values）；壞值啟動失敗（exit 3）、執行中讀到壞值 MCP 路徑一律 503 `ORIGIN_POLICY_UNAVAILABLE`；啟動時記一行生效政策（INFO） | `/data/mcp/origin-policy.json`，面板經共用管線 GET／PUT `{base}/api/origin-policy`（If-Match、Idempotency-Key、收據）；檔案不能用時密鑰網址一律 503 `{"error":"state unavailable"}`（不拒絕啟動，面板用那個檔自己的 ETag 存一份蓋過去），只記 WARNING；沒有啟動時的 INFO 行（HM-27） | add-on options 鎖死（#45），只有面板能改；拒絕啟動會讓壞檔沒有修復途徑 | 部署 |
| 127 | Origin 紀錄的節流 | 整台一份：每個來源 60 秒一行、全部每 60 秒最多 20 行，壓下的補一行；不標帳號，只進預設帳號的 Logs 頁（R04 S-10） | 每帳號一份：每帳號每個（判定、原因、來源）60 秒一行、每帳號每 60 秒最多 20 行，壓下的補一行；帶帳號 id 前 8 碼，寫在 add-on log（WARNING）（HM-27） | HA 在 token 之後判斷、知道帳號；一個帳號被灌爆不會蓋掉其他帳號的紀錄（PaaS 多帳號實測的 info，HANDOFF :241） | 部署 |
| 128 | Origin 清單的格式與上限 | 逗號分隔的環境變數、每項去空白、不限個數，正規化後的重複合併 | JSON 陣列、最多 16 個、每項要剛好是一個來源（不去空白）、正規化後重複 → 422 `origin_policy_invalid`；存正規化後的寫法（HM-27）；IPv6 寫成 RFC 5952 的十六進位、不寫點分，不跟 Python 版本變（HM-27 審查 S-9） | 檔案與請求有界；不默默合併；存過的檔換 Python 也照樣能用 | 加嚴 |

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
| v1 草案（HM-31 審查） | 2026-11-16 | HM-31 | 依獨立安全審查修正（報告 `artifacts/…/wave4/review-HM-31.md`）：第 1.2 節單帳號改變的清單補「帶 `Transfer-Encoding` 時 `Content-Length` 不算宣告、收到的位元組一律照數」（MF-1）、轉送大小也扣的倍數，第 5、6 點的「以前」寫精確（S-4），加「宣告超過 16 MiB 改在讀之前回同一個 413」（MF-3，8099 同）；第 2.2 節第 4 點、第 2.4 節表格（MF-1 改兩列、MF-3 加一列）；第 4.2 節的 413；第 5 節「單一帳號有界」改成 HA 閘道的實測倍數、全域最壞記憶體改用本片的公式、加 HM-19c 放行條件（MF-2），推導的已知限制補同機多個 add-on 重複計算（S-5）與預算在下限時一個帳號的份額就是整份預算（S-1，交主對話或 HM-19c 決定）；第 9 節 #81、#101 補寫，加 #108（MF-1） |
| v1 草案（HM-31 rebase 到 claude-delivery 之後） | 2026-11-16 | HM-31 | rebase 到 `claude-delivery` `d00a338`（HM-08 審查修正、PR #100、HM-09、HM-20、HM-14、HM-10 合併後）：本片的差異列往後移三列（`claude-delivery` 最後是第 100 列），原稿 #98～#105 成為第 101～108 列，順序不變；本片引用的 HM-14 列改成它合併後的列號（原稿 #89～#97 成為 #91～#99：保留名額與准入 #94 成為 #96）；第 2.4、4.2、5 節、第 9 節說明段與 #15、表格、第 10 節本片的列與威脅模型、`decisions.md`、`acceptance-matrix.md` 的引用一起改。#96 照本片改寫（准入滿時通知照樣送到，待決 → 部署），HM-14 rebase 時寫的「交 HM-31」那幾句由本片的做法取代；第 4.2 節 `-32004`、`-32005` 兩列照 `claude-delivery`。主對話 2026-11-16 對本片四題的定案寫進 #101、#105、#108 與第 5 節（份額上限 64 MiB；整體讀取 60 秒與今天的 408；S-1 交 HM-19c；CL＋TE 直接 400 不在本片做，列入已知限制與 HM-29）。規則內容不變 |
| v1 草案（HM-09 追補） | 2026-11-16 | HM-09 | 第 1.2 節：不受開關管多一項（所有產品：健康監看在停止時一定停下；使用者 2026-11-16 13:4x 定「全部產品都修」）；第 7 節「關閉」列補：所有產品的監看與錯開啟動的就緒等待被取消時，HTTP 堆疊吞掉取消也照停（PR #103 的 CI 失敗：HM-20 的端到端測試等了 30 秒；`tests/test_monitor_cancel.py`）。第 9 節不加列（PaaS 沒有對應的常駐監看迴圈，不是刻意差異）。只改關閉，8081、8099 的回應逐位元不變 |
| v1 草案（HM-11） | 2026-11-16 | HM-11 | 面板對齊 HM-10 的真後端（rebase 到 `684a2dd` 之後）：第 9 節補 #109～#112（刪除與索引隔離的兩段確認、第一個 bootstrap 不帶標頭的開關探測、清單不能用時不鎖面板與只藏顯示不了的名稱、孤兒在面板列出可刪），只加列、既有列號不變。第 3 節的管理 API 沒有改：面板與 fixture 對每條路由的狀態碼、欄位、回聲與 ETag 由 `packages/mcp-admin-ui/tests/profile-api-cases.json` 逐案錄自真的 8099 app（`tests/test_panel_profile_api_shapes.py`），fixture 對同一份案例比對（`tests/browser/profile-api-parity.spec.mjs`）。#55、#56、#84、#85 的用字與第 3.3 節例外的寫法仍交 HM-18 |
| v1 草案（HM-11 對齊審查修正） | 2026-11-16 | HM-11 | 依 HM-11 對齊這一輪的獨立安全審查（報告路徑見 PR 描述）：第 9 節 #111 最後一句改成只有索引壞、或清單讀不到或格式不合時的替代清單不當成帳號已刪除的證據，沒帶 `ETag` 的清單與藏名稱的列照常算（S-7；程式本來就是這樣，`profiles.spec` 加一段守住）。只改這一句，規則與列號不變 |
| v1 草案（HM-11 rebase 到 claude-delivery 之後） | 2026-11-16 | HM-11 | rebase 到 `claude-delivery` `df686dd`（HM-10 的 PR #104、HM-31 的 PR #105、HM-09 追補的 PR #106 合併後）：HM-31 已用掉第 101～108 列，本片的差異列往後移八列，原稿 #101～#104 成為第 109～112 列，順序不變；第 9 節說明段本片那行、#112 裡指到的兩段確認（原 #101，現 #109）、第 10 節本片的兩列跟著改。第 3 節的管理 API 沒有改，真後端錄的案例在新基準逐案照過（`tests/test_panel_profile_api_shapes.py`），不用重錄。規則內容不變 |
| v1 草案（HM-12） | 2026-11-16 | HM-12 | 第 3.1 節 `backend`、`backend/patch` 列：開通的 Odoo 換身分換 token 的條件（含清空）、順序（先停舊子程式 → 一次寫入連線＋token＋history → 發布 → 起新子程式）、回應（`token_rotated:true` 只在換了 token 時出現）、五種失敗（停不下、store 拒絕、新檔寫不出來、取代途中失敗、新子程式起不來）的回應、重起與 WARNING，新來源要重填秘密只檢查 `backend/patch`、`backend` 整份取代不檢查；第 4.1 節：`CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 列定案（哪些秘密、帶 null 算帶、同來源不需要、在 If-Match 與 `backend_fixed` 之後、本體形狀與沒有回聲）、`config_apply_failed` 列補換身分時的 `token_rotated`、沒有代碼的 503 補「舊子程式停不下來」；第 9 節加第 113～115 列（HM-11 的 PR 也加列：後合併的一方 rebase 後重編）。沒開通的產品回應逐位元不變（HM-12 沒有不受開關管的部分，第 1.2 節不用加項；`config.py` `_write` 的新參數預設照今天毒化，只有開通後換身分的那次寫入不用） |
| v1 草案（HM-12 審查修正） | 2026-11-17 | HM-12 | 依 HM-12 的獨立安全審查（報告 `artifacts/…/wave4/review-HM-12.md`）：第 3.1 節 `backend`、`backend/patch` 列：寫入失敗不管丟出什麼例外都回固定的 503 state unavailable，是否重起舊子程式改看磁碟上的 token（還是舊的才重起；S-5），補預設帳號的新 state 檔已換上時 8081 所有帶 token 的請求都 503 到重啟、預設帳號 `os.replace` 失敗只關預設帳號（S-2），寫明換身分回應的 `ETag` 是新 state 的（S-3）、舊 token 由分派器與帳號 app 兩層拒絕（S-4）、同一來源只換路徑不算新來源（S-8）；第 9 節 #114 同步（S-2、S-5）、#115 補已知限制（S-8）。規則的其他部分不變；沒開通的產品回應逐位元不變 |
| v1 草案（HM-12 rebase 到 claude-delivery 之後） | 2026-11-17 | HM-12 | rebase 到 `claude-delivery` `f4c7718`（HM-11 的 PR #107 合併後）：HM-11 已用掉第 109～112 列，本片的差異列往後移四列，原稿 #109～#111 成為第 113～115 列，順序不變；第 3.1 節 `backend`、`backend/patch` 列（#114）、第 4.1 節 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 列（#115）、第 9 節說明段本片那行與三列、第 10 節本片的兩列與威脅模型第 3 節的兩處引用一起改。規則內容不變 |
| v1 草案（HM-30） | 2026-11-16 | HM-30 | 第 2.4 節「待送回覆」列（只擋 tools/call、轉送名額之前判斷、`Retry-After: 5`、已轉送的一律交出）；第 5 節待送回覆位元組的定義（交給 server 起扣到 server 收走）與最壞值的補充（軟上限：另有轉送中的回覆，最多轉送名額 × 8 MiB，同今天）；第 6 節加「HM-30 定案」（工作執行緒與它的堆疊、交給它的與不交的、依帳號輪流、例外與停機、待送回覆怎麼扣、64 KiB 分段、軟上限、GIL convoy 與工作執行緒的喘息）與「HM-30 本機量測」。門檻都沒改，仍是暫定（HM-19c）。兩項做不到、照本節規定回報使用者再定，沒有放寬：真實 8 MiB 回覆的迴圈單次停頓（一次 `json.dumps` 就約 45 ms）、預設帳號一次湧入 32 個不讀的 8 MiB 回覆時的 RSS。第 9 節 #17 加附註（工作執行緒在檢查點讓迴圈先跑；待送回覆額度是軟上限） |
| v1 草案（HM-30 審查） | 2026-11-16 | HM-30 | 依獨立安全審查（修正後通過）：第 6 節量測表的讀取期間停頓從「不算進門檻」改成「未定、待使用者決定（D3）」（審查 MF-3：門檻的情境沒有排除讀取期間）；真實回覆一列補單一長字串的 CJK、emoji 數字與分段序列化要另外切長字串（D1）；一次湧入補 emoji（D2：扣的是跳脫後的大小）；慢讀補 emoji 一列（S-1）。第 6 節「HM-30 定案」加請求端 CPU（S-5：仍在迴圈內，由 HM-31 的元素上限限制）與 SSE 事件的 state 讀取（S-6：本片不改）兩條；第 5 節補慢用戶端讓准入與位元組額度扣得較久（S-7）。門檻都沒改 |
| v1 草案（HM-30 rebase 與 D1～D3） | 2026-11-16 | HM-30 | rebase 到 `claude-delivery` `df686dd`（HM-31 #105、HM-09 追補 #106 合併後）：本片在第 9 節沒有自己的列（差異都在 #17 的附註），列號不用改；第 9 節說明段照新基準一片一行，加「#17 的附註出自 HM-30」一行；第 2.4 節「待送回覆」列改成在轉送名額與 HM-14 的排隊之前判斷。使用者 2026-11-16 14:0x 對 D1～D3 的定案（都選 (a)，`decisions.md` 第 1.1 節）：第 5 節加一次湧入的最壞值（D2：帳上扣跳脫後的大小，預設帳號 800 MiB、額外帳號 416 MiB，ASCII 與 emoji 的實測）；第 6 節加使用者定案一段、「慢讀用戶端」補 D2、「HM-30 定案」加 D1（分段轉換）、D3（量整段；測試工具的錯、開通時每段一次 token 檢查）與 HM-31 之後請求端重量的數字；量測表的整段停頓、真實 8 MiB 回覆、一次湧入三列改成定案後的結果；#17 的附註補 D1～D3。門檻都沒改 |
| v1 草案（HM-30 第二輪審查） | 2026-11-17 | HM-30 | 依第二輪獨立安全審查（修正後通過；報告 `artifacts/…/wave4/review-HM-30-phase2.md`）：第 5 節待送回覆列與「HM-30 補」改寫（今天沒開通時是 listener 64 條連線各一個回覆，原本那句和表格矛盾，S-6）；「一次湧入的最壞值」寫明上界靠「JSON 回覆在放掉轉送名額之前就扣」與「排隊的 tools/call 拿到名額之後再查一次」（MF-2，程式已改）與審查前的實測。第 6 節：慢讀用戶端補上界成立的條件與一筆處理放大（S-3）；「HM-30 定案」的待送回覆一點補 MF-2 的做法、GIL convoy 一點補扁平陣列的檢查點；D1 加循環回收器是整個程序的（S-5）、扁平陣列（MF-1）、一筆變長別的帳號等得也久（MF-4）、沒有物件也沒有數字的陣列仍是一次 C 呼叫（待使用者決定）；量測表的 B 的 p99 標明是可控注入，加「真實回覆時 B 的延遲」與「一筆回覆的記憶體高峰」兩列，處理期間、整段、真實 8 MiB 回覆、一次湧入四列補第二輪的數字。#17 的附註補 MF-1、MF-2。第 9 節沒有新列（最後仍是 #108）。門檻都沒改 |
| v1 草案（HM-30 rebase 到 claude-delivery `7646f0f`，Q1、Q2、Q4） | 2026-11-17 | HM-30 | rebase 到 `claude-delivery` `7646f0f`（HM-11 的 PR #107、HM-12 的 PR #110 合併後）：本片在第 9 節仍沒有自己的列（差異都在 #17 的附註），HM-11 的 #109～#112、HM-12 的 #113～#115 照新基準，最後仍是 #115；第 9 節說明段與本節照新基準在前、本片在後。使用者 2026-11-17 03:1x 對第二輪審查交回的 Q1、Q2、Q4 的定案（`decisions.md` 第 1.1 節）：第 6 節加「第二輪審查回報後的使用者定案」一段（Q1、Q2 接受，Q4 維持現狀，都是 HM-19c 實測再定；量停頓的測試門檻、次數都不改、不加重試，CI 紅了先回報使用者）；D1 的兩處與量測表三列的「待使用者決定」改成定案；量測表的整段與真實 8 MiB 回覆兩列補 rebase 後的數字。門檻都沒改 |
| v1 草案（HM-32） | 2026-11-17 | HM-32 | 對齊 PaaS #135、#139（`3c06b98`、`009dc99`；使用者 2026-11-17 02:3x 決定現在就補，`decisions.md` 第 1.1 節）：第 1.2 節不受開關管多一項：LiteLLM 與 EMQX 不保留閒置的後端連線。HA 的實際行為本來就是這樣（`backend_policy.async_client` 丟掉產品給的 `limits`，傳輸層的連線池固定不保留），本片把兩個 `lifespan.py` 要的連線池對齊 PaaS、加測試；回應、後端收到的請求與連線都不變，不加重送。第 9 節不加列：保留閒置連線與否和 PaaS 一致 |
| v1 草案（HM-12 面板） | 2026-11-17 | HM-12 | 第 9 節加第 116 列（換身分存檔後的面板：依 `token_rotated` 提示、藏起權杖、重新讀取，形狀 D 也一樣；開通、會換 token 的產品的後端存檔回 503 state unavailable 時提示重啟後到「連線與權杖」確認網址，HM-12 審查 S-7）與第 117 列（新來源要重填秘密的表單：開通後部分編輯在網址的來源改了時，那條網址的已存秘密改成必填；422 的固定文字），說明段加一行。第 3、4 節的管理 API 與回應沒有改 |
| v1 草案（HM-12 面板審查修正） | 2026-11-17 | HM-12 | 依 HM-12 面板的獨立審查（報告 `artifacts/…/wave4/review-HM-12-panel.md`）：第 9 節 #116、#117 的 HA 欄把面板檔改成 `Hui/contracts.js`（原稿誤寫成 PaaS 面板的 `Pui/`；S-1）；#116 補換了 token 之後重新讀取失敗仍說明、伺服器文字不顯示（S-2、S-5）；#117 補改回同一個來源時已打的值留著、withheld 網址的原因、說明只在網址帶秘密的產品出現（S-4、S-7）。第 3、4 節的管理 API 與回應沒有改 |
| v1 草案（HM-33） | 2026-11-17 | HM-33 | 對齊 PaaS #156（`34769c2`，合併 `48f394d`；使用者 2026-11-17 06:3x 決定現在就補，`decisions.md` 第 1.1 節）：第 1.2 節不受開關管多一項：Hermes `hermes_cron` 的工具說明照 PaaS 逐字補兩句（create 帶 `enabled=false` 建成停用的排程，resume 之前不會跑；Hermes v0.22.x 對停用的排程 trigger 會一併改回啟用，要維持停用之後再呼叫 pause）。只改文字：去掉 docstring 後的語法樹相同，程式行為不變；tools/list 的 `hermes_cron` 說明多兩句，HM-01 黃金回歸的 Hermes 兩個 tools/list 摘要照測試檔頭的規則一起更新（刻意的工具表面變更）。第 9 節不加列：說明和 PaaS 一致 |
| v1 草案（HM-33 審查修正） | 2026-11-17 | HM-33 | 依 HM-33 的獨立審查（報告 `artifacts/…/wave4/review-HM-33.md`，修正後通過）：第 1.2 節 HM-33 那段寫明 create 送 `paused` 是 PR #85（`b50f1c7`，2026-11-12 合併）的行為、發行的 Hermes 0.4.13 還沒有，下一版才出去（MF-1、S-2），「逐位元不變」只說本片；trigger 不會自己再 pause 或 resume 改由測試守（S-1）。規則內容不變 |
| v1 草案（HM-13b） | 2026-11-16 | HM-13b | 第 1.3 節（新）：開機守門定案（位置與順序、觸發、沒開通又沒有帳號資料時只多一行 WARNING 並刪標記、範圍 S 與 A～F、休眠、全部撤銷、守門自己的名稱被目錄占用時移開、log）；第 1.1 節隔離目錄名加 `-n`（HM-07 審查 S-15）；第 1.2 節 `dormant_profiles` 的意思；第 3.5 節還原收據（`restored_before_ms`、`.restored` 只留 1 份、沒有收據的不再封存、DQ-03 (b) 時預設帳號的收據不動）；第 3.6 節還原紀錄的格式（原本暫定；HM-13c 讀時可再定）；第 7 節啟動順序與 log 文字；第 8 節布局補名稱（含 HM-13a 審查 SF-7 交 HM-18 的 `.instance-record.tmp`）；第 9 節補 #118～#121，#24、#67、#82 加附註。照用 DQ-03 (b)、DQ-13、DQ-14、DQ-21、DQ-39 (a)、DQ-40 (a)，沒有新決策 |
| v1 草案（HM-13b 獨立審查） | 2026-11-16 | HM-13b | 依獨立審查（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13b.md`）：第 1.3 節範圍 S 補「`profiles` 是目錄卻列不出來時守門沒做完、標記留著」（MF-2），全部撤銷補「列不出來時照樣撤銷呼叫端的 store、不算做完；驗證不管前面有沒有失敗都跑；呼叫端拿 `ProfileAdmin.lock`、在執行緒裡呼叫」（MF-2、S-5），守門的名稱補還原紀錄與收據封存（S-1）；第 3.5 節「主機時鐘慢」限 24 小時以內（S-6）；第 7 節 log 補帳號目錄裡移開的那一行；第 8 節移開的名稱；第 9 節 #67 補 24 小時上限（PaaS 沒有上限，S-6）、#119 分成「不是目錄」與「是目錄卻列不出來」（MF-2）、#120 補兩種名稱（S-1）。沒有新列、沒有新決策 |
| v1 草案（HM-13b rebase 到 claude-delivery 之後） | 2026-11-16 | HM-13b | rebase 到 `claude-delivery` `f4c7718`（HM-10 的 PR #104、HM-31 的 PR #105、HM-09 追補的 PR #106、HM-11 的 PR #107 合併後）：HM-31 已用掉第 101～108 列、HM-11 已用掉第 109～112 列，本片的差異列往後移十二列，原稿 #101～#104 成為第 113～116 列，順序不變；開頭的狀態、第 1.3、3.5、3.6 節、第 9 節說明段本片那行、#115 裡指到的 #114、第 10 節本片的兩列跟著改（`threat-model.md` 第 3 節、`acceptance-matrix.md` T-21 的引用同步）。解衝突時兩邊都留：第 1.2 節 HM-31 與 HM-09 追補的兩段在前、本片的第 1.3 節接在後面；第 7 節啟動順序列是本片的、關閉列是 HM-09 追補的；#81 是 HM-31 審查改的、#82 的附註是本片的。規則內容不變 |
| v1 草案（HM-13b 合併 claude-delivery 之後） | 2026-11-17 | HM-13b | 把 `claude-delivery` `165dbaf`（HM-12 的 PR #110、HM-30 的 PR #111、HM-32 的 PR #113、HM-12 面板的 PR #114 合併後）用 merge commit 合進本片（不 rebase、不 force push）：HM-12 已用掉第 113～115 列、HM-12 面板已用掉第 116、117 列，本片的差異列再往後移五列，第 113～116 列（原稿 #101～#104）成為第 118～121 列，順序不變；開頭的狀態、第 1.3、3.5、3.6 節、第 9 節說明段本片那行、#120 裡指到的 #119、第 10 節本片的第一、二列跟著改（`threat-model.md` 第 3 節、`acceptance-matrix.md` T-21 的引用同步）；第 10 節第三列是第一次 rebase 的紀錄，照原文。解衝突時兩邊都留：第 1.2 節尾 HM-32 那段在前、本片的第 1.3 節接在後面；第 9 節說明段、第 9 節表尾與本節都是新基準的行在前、本片的在後。規則內容不變 |
| v1 草案（HM-13c） | 2026-11-17 | HM-13c | 第 1.2 節：不受開關管多一項（單帳號還原後的面板提示：使用者 2026-11-16 對 HM-13b 審查 Q-1 的定案，照 DQ-03 (b) 原文；做法、怎麼消失、逐項改了什麼回應、沒有還原時逐位元不變、HM-01 凍結沒有要改的案例），表格兩列、第 0 節第 1 點、第 1.3 節（單帳號還原多存提示、全部撤銷路由的做法）；第 1.1 節隔離目錄的刪除路由定案；第 3.1 節全部撤銷、還原紀錄、核對、刪除隔離目錄的路由與回應定案（原本暫定），清單的 `quarantined`，`token/rotate` 的 409，方法表；第 3.2 節新路由的鎖；第 3.5 節還原時每個收據檔都換新（備份時沒有的也寫）、三種新收據、全部撤銷沒做完時的收據；第 3.6 節 bootstrap 的 `restore_review`、`restore_review_required`、`restore_notice`，`reviewed_at` 的寫法與讀時驗形狀；第 4.1 節 `restore_review_required`、`profile_not_found`、`profile_index_corrupt`（全部撤銷與還原紀錄照常可用；核對與刪除隔離目錄要能用的索引）、`operation_outcome_unknown`（含標記存不下、沒收尾兩種）、`operation_restored`；第 4.2 節全部撤銷失敗帳號的 503；第 7 節 log；第 8 節 `restore-notice.json` 與沒開通又沒有帳號資料的安裝會有哪些檔（計畫 §3.3、§7.1 的那一句，多一個例外）；第 9 節加 #122、#123，#58、#67、#82 補 HM-13c 附註。DQ-03 (b)、DQ-13、DQ-14、DQ-39 (a)、DQ-40 (a) 照用，新定案記在 `decisions.md` 第 1.1 節 |
| v1 草案（HM-13c 審查修正） | 2026-11-17 | HM-13c | 依獨立安全審查（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13c.md`，修正後通過）：第 3.6 節還原紀錄改寫成「守門最近寫的一份」，加一段：休眠開機寫紀錄時保留上一份還在等的核對（預設帳號那一列原樣、還原段落），上一份讀不到就不改它（MF-1）；紀錄讀不到時全部撤銷做完重寫一份、紀錄格式要向後相容（S-2）；bootstrap 的 `restore_review` 兩個時間都是 `null` 時是重建的紀錄；第 1.3 節休眠那一點同步。第 3.1 節全部撤銷、還原紀錄兩列寫出路，`token/rotate` 列補「開關關時沒有關卡」（S-3、S-6 (a)）。第 4.1 節 `restore_review_required` 補「待核對不一定是已撤銷」與 HM-12 的交接（S-3），`operation_outcome_unknown` 的 `results` 空的兩種意思與意外的例外（S-4、S-6 (b)）。第 4.2 節 503 名單只擋之後才經分派器比對的請求（S-6 (c)）。第 9 節 #58、#82、#123 補附註，沒有新列。Q-1（「知道了」只藏到重新整理）照現狀，待主對話確認 |
| v1 草案（HM-13c 合併 HM-13b 與 claude-delivery 之後） | 2026-11-17 | HM-13c | 把 HM-13b 的分支（PR #108 head `fc70404`：已合進 `claude-delivery` `165dbaf`，HM-13b 的列改成第 118～121 列）用 merge commit 合進本片（不 rebase、不 force push）：HM-12 用掉第 113～115 列、HM-12 面板用掉第 116、117 列、HM-13b 接在後面，本片的兩列再往後移五列，原稿 #117、#118 成為第 122、123 列，順序不變；本片引用 HM-13b 的列跟著改（#115→#120、#116→#121）：開頭的狀態、第 1.2 節本片那段、第 3.5 節、第 4.1 節 `operation_restored` 列、第 8 節、第 9 節說明段本片那行、兩列的列號、第 10 節本片的兩列（`decisions.md`、`acceptance-matrix.md` T-21、`docs/operations/update-backup-rollback.md` 的引用同步）。解衝突時兩邊都留：第 1.2 節清單與段落 HM-32 在前、本片在後；第 3.5 節用本片的那段、套上 HM-13b 的改號；第 4.1 節 `operation_outcome_unknown`、`operation_restored` 兩列用本片的、新來源那列用 HM-12 的；第 9 節說明段、表尾與本節都是新基準在前。規則內容不變 |
| v1 草案（HM-13c 審查 S-3） | 2026-11-17 | HM-13c | 依 HM-13c 審查 S-3（主對話 2026-11-17 定；HM-12 已先合併，本片合併時補）：開通後 HM-12 的換身分換 token（`backend`、`backend/patch` 會換 token 時）也過還原核對的關卡，待核對時回 409 `restore_review_required`，什麼都不做；紀錄讀不到時 503（第 3.1 節 `backend`、`token/rotate` 兩列、第 4.1 節 `restore_review_required` 列；原本寫「這個代碼只擋 `token/rotate`，合併時另接或寫明」）。和 HM-12 合併後的語意：換身分換掉還原保留的預設帳號權杖時，還原提示一起清掉（第 1.2 節「怎麼消失」）。沒有新列、沒有新決策 |
| v1 草案（文件同步） | 2026-11-17 | HM-00 補正 | 第 2.4 節「准入滿時保留名額照樣送到」引用的兩個測試改寫成 `tests/test_carries_no_request.py::…` 的寫法（HM-00 對照腳本 C7 把反引號裡結尾是 `_full` 的名稱當成錯誤代碼；內容不變）；第 9 節說明段照重產的 `deviation-trace.md` 改寫：拿掉「`deviation-trace.md` 沒有這幾列」的說法，補一句第 87 列以後怎麼對到、沒有列對到的 7 列出處寫在哪（`docs/provenance/ha-multiprofile-docs-sync-20261117.md`）。差異表本身沒改 |
| v1 草案（發版交接清單） | 2026-11-17 | HM-17 補正 | 第 1.2 節「不受開關管」清單前加一段：各產品下一版會帶出去、CHANGELOG 還沒記的變更、CHANGELOG 句子與發版時要另外驗的事，見新檔 `unreleased-changes.md`（計畫 §11.5）；之後不受開關管的片合併時在那裡加一項。規則內容、差異表、錯誤代碼都沒改 |
| v1 草案（HM-13b 再合併 claude-delivery） | 2026-11-18 | HM-13b | 把 `claude-delivery` `53ffe61`（HM-00 補正的 PR #117、HM-17 補正的 PR #118、0.4.14 發版的 PR #119～#121 合併後）用 merge commit 合進本片（不 rebase、不 force push）：主線第 9 節最後一列仍是第 117 列，本片的第 118～121 列不必再移；第 9 節說明段兩邊合併（保留主線文件同步的說明，加回本片第 118～121 列的出處）。HM-03a 的 UC-08＋sentinel 已在展示機實測（一般與加密局部還原兩個訊號都觸發；完整還原未測，改列為 Odoo 發版前的關卡）。規則內容、差異表、錯誤代碼都沒改 |
| v1 草案（HM-13c 再合併 HM-13b） | 2026-11-18 | HM-13c | 把 HM-13b 的分支（PR #108 head `090081c`：已合進 `claude-delivery` `53ffe61`，即 PR #117～#121 合併後）用 merge commit 合進本片（不 rebase、不 force push）：HM-13b 仍是第 118～121 列、本片仍是第 122、123 列，列號不必再移；第 9 節說明段保留主線文件同步的說明與兩片各自的出處。規則內容、差異表、錯誤代碼都沒改 |
| v1 草案（HM-27） | 2026-11-17 | HM-27 | 密鑰網址的服務層級 Origin 清單（DQ-11 採 (a)，使用者 2026-11-14；計畫 §8.7、§12.3 HM-27）：第 1.2 節沒開通那列補「不讀不寫 `origin-policy.json`、`/api/origin-policy` 404」；第 2.6 節照實作改寫成定案（全部帳號共用一份、存在 `/data/mcp/origin-policy.json`、預設 report-only＋`https://claude.ai`、存檔前不寫檔；位置在 token 與方法檢查之後、query 之前；report-only 回應逐位元不變、記 would_deny，enforce 403 固定本體、記 deny；不加 CORS、沒有 preflight；紀錄的格式、呈現規則與每帳號節流；政策檔不能用時密鑰網址一律 503 state unavailable、面板蓋過去；Headscale 照舊；Bearer 照舊 403，DQ-11 第二問待 S14）；第 3.1 節加 `{base}/api/origin-policy` 的 GET、PUT；第 3.5 節加政策的寫入保護（ETag `o1-`、Idempotency-Key、收據在政策檔旁）；第 4.1 節加 `origin_policy_invalid`（422）；第 4.2 節 403 列補 enforce、加 503 state unavailable 列；第 9 節改寫 #9、#10、#42（#42 定案；#10 照舊 403，第二問仍待決）並加第 124～128 列（檢查的位置、enforce 的本體、設定入口與壞值、紀錄的節流、清單的格式與上限）。沒開通的產品回應逐位元不變；HM-01 的黃金回歸與兩個契約凍結不用改 |
| v1 草案（HM-27 審查修正） | 2026-11-17 | HM-27 | 依 HM-27 的獨立審查（報告 `artifacts/…/wave4/review-HM-27.md`，修正後通過）：第 2.6 節 IPv6 的正規寫法改成 RFC 5952 的十六進位（不跟 Python 版本變）並寫明改正規化規則要遷移舊檔（S-9），不能用的政策檔列全、所有帳號的密鑰網址都 503、目錄只能還原備份（S-2、S-6），開通之後又關掉時 enforce 靜默失效（S-6），Headscale 的 `/api/origin-policy` 寫精確（S-5）；第 3.1 節 405 的 `Allow` 補 `origin-policy`，第 3.2 節 ⑤ 補它的本體、⑧～⑪ 補政策鎖與「⑩ 在鎖之後」（S-4、MF-2）；第 9 節 #9、#128 跟著改 |
| v1 草案（HM-27 合併 HM-13c 之後） | 2026-11-18 | HM-27 | 把 HM-13c 的分支（PR #112 head `c5dd7d3`：已含 HM-13b 的 `090081c` 與 `claude-delivery` `53ffe61`）用 merge commit 合進本片（不 rebase、不 force push）：HM-13b 用掉第 118～121 列、HM-13c 用掉第 122、123 列，本片的五列往後移六列，原稿 #118～#122 成為第 124～128 列，順序不變；本片引用自己列號的地方跟著改：開頭的狀態、第 2.6 節四處、第 4.1 節 `origin_policy_invalid` 列、第 4.2 節兩列、第 9 節說明段本片那行（原本「後合併的一方往後重編」那句改成改號的紀錄）、五列的列號、第 10 節本片的兩列（`decisions.md` DQ-11 列、`acceptance-matrix.md` T-24 的引用同步）。HM-13b、HM-13c 的 #118～#123 照原樣。解衝突時兩邊都留：第 1.2 節表格兩列與第 3.1 節路由表、方法表合成一份（HM-13c 定案的隔離目錄刪除列＋本片的兩列）；第 3.2 節鎖的說明、第 3.5 節表格、第 4.1 節、第 9 節說明段、表尾與本節都是 HM-13c 那側在前、本片在後。合併後另定 Origin 政策與開機守門的關係（本片筆記第 17 節交的事）：兩個檔名寫進版面（`profiles.py`）；還原時守門照索引旁的收據封存、換新 Origin 政策旁的收據（`.origin-policy.json.operations.json`，封存名稱加進守門的名稱），政策檔本身照還原的原樣、守門不讀不改，沒開通又沒有帳號資料時兩個都不動：第 1.3 節（步驟、守門的名稱、Origin 政策一點）、第 2.6 節（還原一點）、第 3.5 節、第 7 節 log 一行、第 8 節布局、#67、#120 跟著改（HM-13b 的兩列只加 HM-27 的那一句）。其他規則內容不變 |
| v1 草案（HM-27 合併後的審查） | 2026-11-18 | HM-27 | 依合併 HM-13c 之後的獨立審查（通過；本片筆記第 20 節）：第 4.1 節 `operation_restored` 列跟上第 2.6、3.5 節：HM-27 起 Origin 政策旁的收據也是（開通或有帳號資料時），`PUT origin-policy` 重送還原前的 id 也回 410；負責片加 HM-27，測試加 `tests/test_origin_policy.py` 與面板的 `origin-policy.test.mjs`（識別紀錄留著、「已核對來源設定」才清掉）。規則內容不變 |
