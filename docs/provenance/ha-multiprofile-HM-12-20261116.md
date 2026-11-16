# HA 多帳號 HM-12 provenance：Odoo 換身分換 token、審批不跨帳號、新來源重填秘密（後端與 API 測試）（2026-11-16）

## 結論

- **本片只做後端與 API 測試；面板部分另開 PR，疊在本 PR 上**（主對話 2026-11-17 決定；第 11 節：後端給面板的回應形狀與待補清單 ①～⑦）。
  `MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空集合，**今天任何產品都沒有新行為**；測試裡用 monkeypatch 開。
- **開通的 Odoo，token 綁一個後端身分**（DQ-05，照計畫 §9；契約第 3.1 節、§8.8 #40、I11）。token 有效、已存的連線完整，而這次存檔
  （`backend` 或 `backend/patch`，經 8099 分派器）讓 url、database、username 任一改變（含 `{"connection":null}` 清空）時，依序：
  1. 先停舊子程式（新的 `ProfileRuntime.stop_child`：停掉並丟掉 spec，之後只有「在指定 state 上重起」才會再起它）；
  2. 一次寫入新連線＋新 token＋一筆 history（新的 `ProductStore.rebind`；動作沿用 `rotate`，§8.8 #59）；
  3. 發布 token 變更（`TokenAccess.committed()`）；
  4. 在寫入的 state 上起新子程式。
  回 200 `{"saved":true,"token_rotated":true,"configuration":…}`（＋帳號回聲），帶新 state 的 `ETag`（審查 S-3 補了測試），不含 token。
  只換密碼、初次設定、token 已撤銷：照今天（先寫入再重起、不換 token、回應沒有 `token_rotated`）。預設帳號與每個額外帳號都一樣
  （開通後預設帳號也是帳號；計畫 §7.2 第 7 點）。
  清空也換：不換的話，先清空、再存別的帳號就成了「初次設定」，舊 token 會留下來。
- **舊 token 在 8081 立刻失效**（HM-10 交來的待辦）：兩條入口都回「沒有帳號持有的 token」的 401／404；進行中的請求（HM-08 的 lease）
  與 HM-14 佇列中等名額的請求都結束，排隊的那個不會送到任何子程式；分派器照 state 檔簽章重讀，舊 token 不再對到任何帳號，帳號自己的 app
  也再驗一次（兩層都有測試釘住，審查 S-4；第 3.3 節）。
- **新 token 碰不到舊子程式**（UC-21）：寫入那一刻舊子程式已經停了（測試記下寫入當下子程式的狀態）；新子程式起來之前，新 token 的
  initialize 由閘道自己回答，子程式的 port 收不到任何請求。
- **失敗時**（PaaS `test_failed_account_rebind_restores_old_child_and_url` 的 HA 版；契約 §8.8 #114；第 3.2 節）：
  - 舊子程式停不下來：什麼都不寫，用舊 state 重起，503 `{"error":"request denied"}`。
  - 寫入失敗：不管丟出什麼例外，一律照今天回 503 `{"error":"state unavailable"}`（審查 S-5：以前 `ConfigError` 以外的例外會變 500）。
    要不要用舊 state 重起舊子程式，看磁碟上的 token，不看例外種類（審查 S-5 後改）：
    - 還是舊的（store 拒絕寫入；新的 state 檔寫不出來、還沒取代舊檔，例如磁碟滿；寫之前就丟出例外）：什麼都沒寫，用舊 state 重起，
      舊 token 照舊可用（PaaS 同）。
    - 讀不到（取代 state 檔途中失敗：`os.replace` 或之後的目錄 fsync）：不知道寫成了沒有，store 照今天的規則毒化（fail closed）。
      該帳號到 add-on 重啟前不服務（新檔還沒換上時舊 token 回 503；已換上時分派器讀不到、不路由，兩把 token 都是未知 token）。
      **預設帳號**的 `os.replace` 失敗只關預設帳號；預設帳號的新檔已換上時，8081 所有帶 token 的請求（其他帳號的也是）都 503 到重啟
      （契約第 2.3 節「預設 state 讀不到」；審查 S-2，測試釘住）。
    - 已經是新的（寫入丟出例外，但新 token 已在磁碟上、store 沒毒化，例如取代之後清理暫存檔失敗）：舊 token 401／404，新 token 只拿到
      閘道自己的回答，到 add-on 重啟或面板重啟子程式（在新身分上起）。
    - 後兩種舊子程式都**不重起**（磁碟上可能已是新 token）；重啟後照磁碟上的，token 與身分一定一起。為了分開「取代之前」與「取代途中」，
      `config.Store._write` 多一個 `poison_before_replace` 參數：預設照今天（任何失敗都毒化），只有 `rebind` 傳 False。
  - 新子程式起不來：token 已換、舊子程式不再起，503 形狀 D 另帶 `token_rotated:true`（也帶新 state 的 `ETag`）；面板的 `child/restart`
    會在新身分上起。
  - 每種失敗各記一行 WARNING（帳號 id 前 8 碼、子程式有沒有重起；不含 token、網址、名稱）。
  - DQ-05 原文是「提交失敗用舊 state 重起」；「結果不明不重起」是本片的細分（審查 S-1 同意安全上正確），已記進 `decisions.md` DQ-05 列；
    主對話 2026-11-17 已在合併前向使用者說明（`decisions.md` 跟著改，第 18 節）。
- **審批不跨帳號**（HM-10 交來的待辦；FM-82、T-10）：兩個真的 Odoo 子程式（預設帳號與一個額外帳號，同一個假 XML-RPC 後端，兩帳號
  state 除了 token 與 child token 完全相同）。預設帳號 `validate_write` 拿到的審批，在額外帳號的子程式被拒（「沒在這個 server session
  驗過」），後端 0 次寫入；預設帳號自己執行得了。對照：額外帳號自己驗同一筆寫入，拿到的審批 token **字串完全一樣**（odoo-mcp 的審批
  token 是寫入內容的摘要），只有它自己的子程式執行得了。所以不跨帳號靠的是「每帳號一個子程式」，不是 token 字串（第 3.5 節）。
  `chatter_post` 的 approval 只是預覽確認、沒有伺服器端紀錄，不是跨帳號邊界（威脅模型第 3 節；獨立安全審查用真子程式實測確認，E4）。
- **新來源要重填秘密**（DQ-40 ⑨；契約第 4.1 節、§8.8 #41、#115）：開通後**全部產品**的 `backend/patch`，把一條網址改到另一個來源
  （scheme、host、有效 port）卻沒帶那條網址會送去的已存秘密 → 422 `{"error":"request denied","detail":{"code":
  "CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}`，在 If-Match 與 `backend_fixed` 之後，什麼都不寫、不重起。每條網址對應哪些秘密寫在
  `identity_fields.URL_SECRETS`（本片把 HM-07 的 `identity_fields` 接上線）。同來源（只改路徑、大小寫、寫出預設 port）不需要；帶 null
  清掉可為 null 的秘密算帶了；網址清空或第一次設定不需要；`backend` 整份取代本來就帶全部秘密，不檢查。同一來源換路徑會沿用已存的
  秘密：DQ-40 ⑨ 定的範圍，列為已知限制（審查 S-8；威脅模型第 3 節）。
- **沒開通：逐位元照今天**（計畫 §3.3）：存檔先寫入、再重啟子程式，token 不換，回應照舊，新來源也照舊存。HM-01 的黃金回歸與兩個契約
  凍結（含開通重跑）照過、期望值一個都沒改（第 7 節）。HM-12 沒有不受開關管的部分，契約第 1.2 節不用加項。
- **其他產品開通後也不換 token**（只有 Odoo：`products.IDENTITY_BOUND`）：Nextcloud 歸 HM-22、Hermes 歸 HM-24（DQ-40 ⑩）。
- **測試**：新 3 檔 77 案（原本 73 案，審查後補 4 案）＋改既有 5 檔。先寫測試：在 `df686dd` 的程式上 215 案 54 案失敗（第 6.1 節）；
  實作後全過；臨時突變 17 個全部擋下（第 6.2 節）。審查後補的斷言與案例：紅（審查前的 `gateway.py`）6 案失敗、6 個突變全部擋下
  （第 6.3 節）。PaaS `test_config_store.py:102-170` 三案與另外三個 PaaS 測試逐案對照（第 5 節）。
- **本機**：全套 pytest 6,047 案，6,017 通過、30 失敗、0 skip；失敗的是 22 個瀏覽器測試（當時沒裝 Chromium）、7 個要 root 的既有案例、
  1 個本片造成的 HM-31 參數順序測試（已改，第 8 節）。之後在這個 clone 裝好 Chromium（Playwright 瀏覽器安裝），22 個瀏覽器測試、改過的兩個測試與
  `stop_child` 選項測試補跑：183 案全過。所以本機只剩 7 個要 root 的既有案例沒過（只在 CI 跑）。packaging unittest Ran 203、OK（skipped=5）；
  validate 過。以 CI 為準。審查修正後（2026-11-17）在這個 clone 重跑受影響的 7 組 1,886 案：只有同一個要 root 的既有案例沒過；
  packaging 照過（第 8 節）。
- **兩個預檢**（審查修正後重跑）：秘密預檢 0 命中、帳本預檢 OK（第 13 節）。rebase 後 base 改成 `origin/claude-delivery` 重跑：0 命中、OK（第 18.8 節）。
- **rebase 到 `claude-delivery` `f4c7718`**（2026-11-17，第 18 節）：衝突在 2 個 commit（契約 3 塊、`decisions.md` 1 塊），兩邊的行都照原文；契約第 9 節本片的列改成
  #113～#115（HM-11 已用掉 #109～#112）；帳本照 JSON 重建、63 列照檔案重算 0 漂移；HM-11 的真後端形狀比對照過，沒有語意衝突。本機：全套 6,062 案（7 案失敗、0 skip）、
  pytest 子集 2,229 案、node 81、Playwright 117；失敗的只有要 root 的既有案例。
- **獨立安全審查**（2026-11-16 23:00～23:45，審查者不是作者）：**通過**，必修 0 項、建議 9 項（報告
  `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-12.md`）。9 項都採用並處理（第 17 節）。
- **還沒做**：`checks` 秒數開 PR 後補；面板部分（第 11 節，另開 PR 疊在本 PR 上）。rebase 與重編列號（第 18 節）、DQ-05 的細分
  向使用者說明（S-1，主對話 2026-11-17）都已做。
- 接手說明：本片的 clone 開工時有同一個工作流前一次中斷時留下的草稿（三個新測試檔、幾個文件與測試的修改，沒有程式；最後修改 19:30）。
  開工前備份到 repo 外，逐條核對後保留，改了寫入失敗的設計（分成「取代之前」與「取代途中」）與對應的測試，並補了 store 層與
  `stop_child` 選項的測試。

## 1. 範圍與基準

- 基準：`claude-delivery` `f4c7718`（2026-11-17 rebase 後；已合併 HM-00～HM-10、HM-13a、HM-14（#103）、HM-17、HM-02、HM-20、#100、
  HM-31（#105）、HM-09 追補（#106）、HM-11（#107））。rebase 前是 `df686dd`：第 1～17 節照當時寫，rebase 見第 18 節。
- 分支：`feat/ha-multiprofile-hm12-20261116`（一般 clone；rebase 後才 push、開 PR，第 18.12 節）。
- 審查修正時（2026-11-17）`claude-delivery` 已前進到 `f4c7718`（HM-11 的 PR #107 合併，佔用契約第 9 節 #109～#112）。開 PR 前
  rebase 到 `f4c7718`、重編列號、帳本照資料重算、重跑預檢與測試（第 18 節）。
- 對齊的 PaaS：pin `69ac425`（DQ-06）。本機唯讀 PaaS repo 的 `origin/main` 是 `7087280`（任務說 `d7f5849`；本機另有 #135、#139、#138 三個
  合併，只動 EMQX、LiteLLM、Hermes 的 app，和本片無關；本片沒有 fetch、沒有 checkout）。
- 範圍（計畫 §12.3 HM-12「做法」與 DQ-05、DQ-40 ⑨）：`Hc/gateway.py`（`backend`、`backend/patch` 先停、再提交、再起；新來源 422）、
  `Hc/products.py`（一次寫入連線＋token＋history）、`Hc/backend_edit.py`（DQ-40 ⑨ 的判定）、`Hc/identity_fields.py`（`URL_SECRETS`）、
  `Hc/config.py`（寫入失敗分兩種）、`Hc/profile_runtime.py`（`stop_child`）。**面板（`Hui/app.js`）這次不做**：HM-11 正在開 PR，先合併；
  本片的面板部分之後疊在 HM-11 上另外做（第 11 節）。

## 2. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hc/gateway.py`（列管） | `make_apps` 多一個 keyword-only 參數 `stop_child`。`admin_action` 的提交步驟（⑪ 的 If-Match、`backend_fixed` 之後）：開通的產品 `backend/patch` 改到別的來源沒帶秘密 → 422（`NEW_ORIGIN_SECRET`）；`products.identity_rebound` 成立 → `rebind_identity`（停 → `store.rebind` → `token_access.committed()` → `backend_changed`；五種失敗的處理與 WARNING）。新的 module logger、`REBIND_WARNING`。沒開通的路徑一行都沒動（只多兩個延遲 import，判斷式在開關關時都回 False）。審查後：寫入失敗一律回固定的 503 state unavailable，是否重起舊子程式看磁碟上的 token（S-5）；說明拿掉第 9 節本片的列號（S-6） |
| `Hc/products.py`（列管） | `IDENTITY_BOUND`（Odoo）、`identity_rebound(previous, candidate)`、`ProductStore.rebind(changes, token)`；import `identity_fields`、`ConfigError`。審查後只改說明（拿掉列號，S-6） |
| `Hc/backend_edit.py`（列管） | `url_secrets`、`origin`、`new_origin_refused`；說明補 HM-12。審查後只改說明（同一來源換路徑不算新來源的已知限制，S-8；拿掉列號，S-6） |
| `Hc/identity_fields.py`（列管） | `URL_SECRETS`；說明改成「HM-12 接線」 |
| `Hc/config.py`（列管） | `Store._write(value, *, poison_before_replace=True)`：預設照今天；`False` 時 replace 之前的失敗不毒化 |
| `Hc/profile_runtime.py`（列管） | `ProfileRuntime.stop_child`（停子程式、丟掉 spec），交給 `make_apps`；`RUNTIME_OPTIONS` 多 `stop_child`；說明補 HM-12 |
| `docs/provenance/runtime-patches.json` | 上面 6 個列管檔的 `sha256` 用實際內容重算，`change` 各補一段 HM-12。審查後 `gateway.py`、`products.py`、`backend_edit.py` 再重算；四段 `change`（含沒改程式的 `config.py`）拿掉列號，`gateway.py` 那段寫明 S-5 的規則 |
| `tests/test_odoo_identity_rotation.py`（新） | 換身分換 token、順序、失敗、store 的一次寫入、`make_apps` 的 `stop_child` 選項、沒開通照今天、其他產品不換。審查後：回應的 `ETag`（S-3）、分派器層的路由（S-4）、非預期例外與新 token 已在磁碟上（S-5）、預設帳號結果不明（S-2） |
| `tests/test_odoo_multi_profile.py`（新） | 同庫五個帳號、A 的審批在 B 被拒（真子程式）、DQ-30 |
| `tests/test_new_origin_secret.py`（新） | DQ-40 ⑨：九個產品、每條網址、三種換法；同來源、null、整份取代、順序、沒開通、經分派器。審查後說明拿掉列號（S-6） |
| `tests/test_saved_destinations.py` | 開通後改到別的來源的 `backend/patch` 一起帶那條網址的秘密（HM-20 的 LAN 與替身開關案例；原本只帶網址會變 422） |
| `tests/test_upgrade_zero_rewrite.py` | `UNWIRED` 拿掉 `identity_fields`（HM-12 接線），說明跟著改；審查後函式名改正（S-9） |
| `tests/test_identity_fields.py` | 說明一行（「HM-12 接線」） |
| `tests/test_profile_runtime.py` | keyword-only 參數清單多 `stop_child` |
| `tests/test_request_budget_gateway.py` | HM-31 釘住的 `make_apps` 參數順序最後多 `stop_child`（全套 pytest 時發現，第 8 節） |
| `docs/multi-profile/contract.md` | 第 3.1 節 `backend` 列、第 4.1 節兩列與沒有代碼的 503、第 9 節說明段與 #113～#115（rebase 前是 #109～#111）、第 10 節一列。審查後改 `backend` 列、#114、#115，第 10 節再加一列（S-2～S-5、S-8）。rebase 後：本片的列改成 #113～#115、引用跟著改，第 10 節再加一列（第 18 節） |
| `docs/multi-profile/threat-model.md` | I11 的做法與測試欄；第 3 節兩條（取代途中失敗、chatter 預覽確認）；狀態列。審查後改寫取代途中失敗那一條（S-2、S-5、S-7）、加同一來源換路徑一條（S-8）。rebase 後：兩處列號改成 #114、#115 |
| `docs/multi-profile/acceptance-matrix.md` | 三個新測試檔「計畫」→「新增」並寫實際內容；`test_saved_destinations.py` 補 HM-12；審查後補案例 |
| `docs/multi-profile/decisions.md` | 審查後：DQ-05 列補記本片的實作細分（結果不明不重起），寫明待主對話在合併前向使用者說明；變更紀錄一列（S-1）。rebase 後：兩處改成「主對話 2026-11-17 已在合併前向使用者說明」（第 18 節）。不是新題目 |
| 本筆記 | 新增 |

沒改：`addons/`、版號、CHANGELOG、`MULTI_PROFILE_PRODUCTS`（維持空集合）、面板（`packages/mcp-admin-ui/`）、`apps/`（沒有動 `apps/runtime/*.py`
或 `apps/*/launch.py`，所以 tool-surface 不用重產）、`deviation-trace.md`（repo 外的產生器重產；FM-81 的「UC-21 未確認」由本片的
測試確認，第 10 節）。`decisions.md` 只在審查後補記 DQ-05 的實作細分（S-1），沒有新決定。

## 3. 設計重點

### 3.1 換身分的條件與順序（對照 PaaS `patch_connection_bound`）

| 項目 | PaaS（`Pc/config/store.py:502-533`、`Pc/connection_apply.py:23-45`） | HA（本片） |
|---|---|---|
| 條件 | 三個身分鍵原本都有值、合併後任一不同、token 有效沒撤銷 | 同：已存的連線完整（Odoo 三欄必填）、token 有效、`url`／`database`／`username` 任一不同；清空（`{"connection":null}`）算不同 |
| 誰算身分欄位 | `ODOO_IDENTITY_KEYS` | `identity_fields.rotating_fields('odoo')`（HM-07 的表，本片接線） |
| 範圍 | Odoo（#131），之後 Nextcloud（#154） | 開通的 Odoo（`products.IDENTITY_BOUND`）；Nextcloud、Hermes 交 HM-22、HM-24 |
| 停舊子程式 | 在 store 的鎖內、寫入前（`before_rotate`） | 在該帳號的 `mutation_lock` 內、寫入前（`stop_child`）；停掉後丟掉 spec |
| 寫入 | 新連線＋新 token＋history（`backend_identity_change`）一次 | 新連線＋新 token＋history（`rotate`，§8.8 #59）一次（`ProductStore.rebind`） |
| 發布 | 新的 generation、喚醒等待中的 lease | `TokenAccess.committed()`（HM-08 的 lease 與 HM-14 的結尾照既有規則） |
| 起新子程式 | 一定重啟（`restart:false` 也一樣） | 在寫入的 state 上起（`backend_changed`） |
| 回應 | 一律帶 `token_rotated`（true／false）＋文字 | 只有換了才帶 `"token_rotated":true`；沒換照今天逐位元（§8.8 #113） |
| 只換密碼、初次設定 | 不換 | 不換（照今天的路徑：先寫入、再重起） |
| 開關關 | （沒有開關） | 照今天：不換 token（計畫 §3.3） |

### 3.2 失敗處理（§8.8 #114）

| 哪一步失敗 | 寫了什麼 | 子程式 | 舊 token | 回應 | WARNING 的結尾 |
|---|---|---|---|---|---|
| 停舊子程式 | 沒有 | 用舊 state 重起（重起前再試一次停） | 照舊可用 | 503 `{"error":"request denied"}` | `was not saved: its child could not be stopped; its child was relaunched on the saved connection`（或 `could not be relaunched`） |
| store 拒絕（驗證不過、讀不到），或寫之前丟出其他例外（例如 `rebind` 的 `ValueError`；審查 S-5） | 沒有（磁碟上還是舊 token） | 用舊 state 重起 | 照舊可用 | 503 `{"error":"state unavailable"}`（今天的；不會 500） | `was not saved: the new state could not be written; …` |
| 新的 state 檔寫不出來（取代之前：開檔、寫入、fsync） | 沒有（`_write` 不毒化：舊檔一定還在） | 用舊 state 重起 | 照舊可用 | 同上 | 同上 |
| 取代 state 檔途中（`os.replace`、之後的目錄 fsync） | 不知道（store 毒化，讀不到） | **不重起**（磁碟上可能已是新 token） | 該帳號到重啟前不服務：新檔還沒換上 503；已換上時不路由（401／404）。預設帳號：`os.replace` 失敗只關預設帳號；新檔已換上時 8081 所有帶 token 的請求都 503（審查 S-2） | 同上 | `failed while its state file was being replaced: whether it was saved is unknown, so its child stays stopped until the add-on restarts and reads the state on disk` |
| 寫入丟出例外，但新 token 已在磁碟上（取代之後清理暫存檔失敗等，store 沒毒化；審查 S-5 後才分出來） | 新連線＋新 token | **不重起**（以前只要 store 讀得到就重起） | 已失效（401／404）；新 token 只拿到閘道自己的回答 | 同上 | 同上一列 |
| 新子程式起不來 | 新連線＋新 token | 不起舊的；面板重啟會在新身分上起 | 已失效 | 503 形狀 D＋`"token_rotated":true` | （照今天：沒有這一行；`apply_state` 顯示失敗） |

- 任務列的四種故障注入對到上表：停失敗＝第 1 列；寫入失敗＝第 2、3 列（store 拒絕、新檔寫不出來）；提交失敗＝第 4 列（取代 state 檔途中：
  rename 或之後的目錄 fsync，兩個時點各一案；預設帳號另兩案）、第 5 列（審查後補）；起新子程式失敗＝第 6 列。`TokenAccess.committed()` 只在記憶體換一個 Event、不做 I/O，
  不會失敗；就算沒發布，lease 每 0.2 秒也會重讀 state、自己結束（HM-08 既有的 `TokenLease.invalidated`）。
- 為什麼「取代途中」不重起舊子程式：這時磁碟上可能已是新 token。重起也沒有用：store 毒化後該帳號不服務任何請求（503 或不路由），沒有請求到得了子程式；
  但「新 token 可能存在時，沒有子程式跑在舊憑證上」這條不變式就破了（UC-21）。重啟 add-on 後照磁碟上的 state 起，token 與身分一定一起。
- 為什麼要分「取代之前」和「取代途中」：任務要求「任一步失敗用舊 state 重起，舊 token 照舊可用」。HA 的 store 今天任何寫入失敗都毒化
  （結果不明就不再讀寫）；但取代之前失敗時結果是確定的（舊檔還在），毒化反而讓舊 token 不能用。所以只在這條路放寬，而且只放寬確定的那一半
  （`_write(poison_before_replace=False)`）。其他每個寫入照今天。
- 審查 S-5 後，是否重起只看磁碟上的 token（`store.load().token == state.token`），不看丟出哪種例外：同一個條件涵蓋第 2～5 列，
  而且「新 token 可能在磁碟上時不重起」不再依賴「例外是不是 `ConfigError`」。以前的寫法在 store 讀得到時一律重起；取代之後才丟出的
  `OSError`（`_write` 的 `finally` 清理暫存檔，例如檔案系統變唯讀時 `unlink` 回 EROFS）不會毒化 store，舊子程式就會在新 token
  已在磁碟上時重起（UC-21 的破口，機率很低，但規則應該不依賴它）。測試用 `Path.unlink` 回 EROFS 重現。
- 「任一步」只到寫入為止：寫入成功後舊 state 已經不在（新的在磁碟上），新子程式起不來時不能「用舊 state 重起」（那會讓新 token 的帳號跑在
  舊憑證上），所以照 PaaS 與今天的存檔：存檔成功、套用失敗（形狀 D）。

### 3.3 舊 token 在 8081 的失效路徑

1. 舊子程式先停：進行中、已經在子程式裡的請求在子程式停下時結束（開通後是 HM-14 的 `-32004`；測試用的 in-process 子程式不會斷線，
   所以測試裡它們是在發布時結束）。
2. 寫入：舊 token 不在磁碟上了。之後的新請求：分派器照 state 檔簽章重讀（`Credentials.refresh`，新檔一定是新 inode），舊 token 對不到任何
   帳號 → 交給預設帳號的 app → 401／404（「沒有帳號持有的 token」）。
3. 發布（`TokenAccess.committed()`）：拿著舊 token 的 lease 立刻結束（401／404；回應已經開始的照 HM-14 的結尾）。HM-14 佇列裡等名額的請求
   拿到名額後先重驗 token（`gateway.serve` 的「Revalidate after yielding」），被拒，不會送到任何子程式。

- 兩層都拒絕舊 token：分派器不再把它對到任何帳號（`McpDispatcher.resolve` 回空；審查 S-4 後測試直接斷言），帳號自己的 app 也再查一次
  token。只拿掉其中一層，另一層照樣回同樣的 401／404（審查的 X18）。舊 token 的請求送不到新子程式也有兩道：排隊拿到名額後的重驗、lease
  每次轉送前重讀 store；兩道都拿掉測試才過不了（審查的 X19、X20）。

### 3.4 新來源要重填秘密（DQ-40 ⑨；§8.8 #41、#115）

- 每條網址會送去哪些秘密：`identity_fields.URL_SECRETS`（存檔名），`backend_edit.url_secrets` 轉成管理 API 的名字。Hermes 有兩台伺服器、
  各自一個秘密；n8n 的 API key 與 MCP access token 都送到同一台 n8n；OpenDesign 沒有秘密。測試要求每條網址都列出、每個秘密剛好出現一次。
- 來源＝scheme、host（小寫、IPv6 去括號）、有效 port（沒寫用 80／443）。同一台主機的其他寫法（結尾的點、IPv4 的其他寫法）算不同來源（安全的方向）。
- 只看 `backend/patch`：`backend` 整份取代一定帶全部秘密（模型必填；n8n 沒帶 MCP token 就是清掉），不會把已存的秘密帶到新地方。
- 帶了就算（值不限，同值也算：管理 API 從不回秘密，帶得出來就是使用者自己輸入的）；可為 null 的帶 null＝清掉、不會送過去；沒存的秘密不用帶；
  網址清空或第一次設定不用帶。
- 時機：⑪（If-Match、`backend_fixed` 之後），什麼都不寫、不重起；以例外回（`BadRequest(422, …)`），所以沒有帳號回聲（HM-10 的規則）。
- PaaS 只有 Headscale 有這條（比整條正規化後的網址，`apps/headscale/headscale_mcp_admin/connection.py:104-109`）。HA 比來源，是 DQ-40 ⑨ 寫的
  範圍；HA 的 Headscale 網址本來就只存來源，結果等同 PaaS。本片之後 Headscale 開通時（HM-26）不用再做這條。

### 3.5 審批 token 為什麼不跨帳號（FM-82）

- odoo-mcp 1.3.0 的 `validate_write` 把審批記在子程式行程內（`fix_cross_session_token_store.py` 讓同一行程的 session 共用一份），
  `execute_approved_write` 找不到紀錄就拒絕（`tools_write.py:442-453`）。每個帳號一個子程式，所以 A 的審批在 B 的子程式找不到紀錄。
- 審批 token 本身是寫入內容的摘要（`agent_tools.py:111-114`），和帳號無關：兩個帳號驗同一筆寫入會拿到同一個字串。測試用這個對照證明
  「不跨帳號靠的是子程式各自的紀錄」：B 自己驗過之後，B 的子程式才執行得了。
- `chatter_post` 的 approval 沒有伺服器端紀錄（子程式每次重算摘要比對，`tools_write.py:608,650`），所以 A 預覽拿到的 approval 在 B 也執行得了。
  這不是跨帳號授權：持有 B 的 MCP token 的用戶端本來就能自己預覽拿到同一個字串，執行時用 B 的憑證與政策。寫進威脅模型第 3 節，交獨立安全審查確認。

### 3.6 開關關

- `identity_rebound` 與 `new_origin_refused` 每次呼叫時讀 `features.enabled`，沒開通都回 False；提交步驟照今天：`store.update` → `committed.set()` →
  `backend_changed`，回應逐位元相同。`ProfileRuntime` 一律把 `stop_child` 交給 `make_apps`，沒開通時沒有任何路徑呼叫它。
- `Store._write` 的預設照今天（任何失敗都毒化）；只有開通後換身分的那次寫入傳 `poison_before_replace=False`。
- 契約第 1.2 節不用加項（本片沒有不受開關管的部分）。

## 4. PaaS 變動清單（本機唯讀 PaaS repo；`git log --oneline 69ac425..origin/main -- <相關檔>`，`origin/main`＝`7087280`）

查的路徑：`Pc/config/store.py`、`Pc/connection_apply.py`、`Pc/routers/settings.py`、`Pc/routers/tokens.py`、`apps/odoo/odoo_mcp_admin/`、
`apps/odoo/patches/`、`apps/headscale/headscale_mcp_admin/connection.py`、`apps/nextcloud/nextcloud_mcp_admin/routers/config.py`、
`packages/mcp-admin-core/tests/test_config_store.py`、`test_connection_type_parity.py`、`test_process_stdout_log.py`、`apps/odoo/tests/`。

| commit | 內容 | 對本片 |
|---|---|---|
| `0f94aa4`（#154） | Nextcloud 換使用者或網址時撤銷舊的 MCP 網址（改走核心 `save_bound_connection`） | 不在本片：DQ-40 ⑩、HM-22。核心的 `patch_connection_bound`、`save_bound_connection` 沒有改，本片對照的規則不變 |
| `0f43fd3`（#152） | Nextcloud 的 `base_url` 存檔與測試連線過 SSRF 檢查 | 不在本片：HM-22（HA 的存檔檢查是 HM-20） |
| `3b135ca`、`1637a0f`（#155） | `apps/odoo/tests/test_request_structure_guard.py`（結構守門） | HM-31 已對齊，和本片無關 |

`69ac425..7087280` 共 42 個 commit，其他的不碰上面的路徑。PaaS 這段期間沒有改 Odoo 換身分換 token 的規則。

## 5. PaaS 測試逐案對照（`69ac425`）

| PaaS 測試 | 情境 | HA 的測試 |
|---|---|---|
| `packages/mcp-admin-core/tests/test_config_store.py:102` `test_bound_connection_rotation_is_atomic_and_preserves_password_changes` | ① 只換密碼：不換 token；② 換 username：停舊子程式那一刻磁碟上還是舊 token、換了 token、generation 變、history 一筆；③ 寫入失敗：例外、檔案位元組不變、token 還是上一把 | ① `test_a_password_change_or_the_first_setup_keeps_the_token`；② `test_a_changed_identity_stops_the_old_child_then_rotates_the_token_in_one_write`（7 案：url／database／username × `backend`、`backend/patch`；停的那一刻磁碟上是舊 token、一次 replace、history `rotate`）、`test_the_store_writes_the_identity_and_its_token_at_once_and_fails_closed_only_when_unsure[None]`（store 層）；③ 同檔 `[new file]`（取代之前失敗：位元組不變、store 照用）、`test_a_failed_identity_change_keeps_the_old_identity_its_token_and_its_child[write]`（API 層：舊 token 兩條入口照舊可用）。HA 另加取代途中失敗（`[replace]`、`[directory sync]`、`test_a_write_whose_outcome_is_unknown_leaves_the_profile_closed_until_the_add_on_restarts`）：PaaS 沒有對應（它不毒化） |
| 同檔 `:137` `test_initial_bound_connection_setup_keeps_issued_url` | 初次設定不換 | `test_a_password_change_or_the_first_setup_keeps_the_token`（第一筆連線）、`test_five_accounts_of_one_database_stay_bound_to_their_own_profiles`（五個帳號都是初次設定） |
| 同檔 `:147` `test_failed_account_rebind_restores_old_child_and_url` | 寫入失敗：子程式停一次、起一次（還原） | `test_a_failed_identity_change_keeps_the_old_identity_its_token_and_its_child`（4 案：停不下、拒絕、拒絕且起不回、新檔寫不出來；journal 驗停與起的次數與順序） |
| `packages/mcp-admin-core/tests/test_connection_type_parity.py:89` `test_odoo_account_rebind_revokes_old_url_without_rotating_on_password_change`（兩條路由） | 換 username：`token_rotated` true、舊網址失效、新 token 不在回應、新網址可用；再只換密碼：`token_rotated` false、token 不變 | `test_a_changed_identity_…`（兩條路由；新舊 token 都不在回應；舊的兩條入口 401／404；新的兩條開得了子程式的 session）、`test_a_password_change_…`（HA 沒換時不帶 `token_rotated`：§8.8 #113） |
| `apps/odoo/tests/test_multi_profiles.py:21` `test_five_odoo_accounts_same_database_are_fixed_to_separate_profiles` | 同庫五個帳號：五把 token、五個 port、各自的連線 | `test_five_accounts_of_one_database_stay_bound_to_their_own_profiles`（另加：換其中一個只換它的 token、其他帳號與預設帳號不動） |
| `packages/mcp-admin-core/tests/test_process_stdout_log.py:157` `test_connection_apply_restore_failure_reaches_stdout_once` | 還原失敗記剛好一行 | 每個失敗案例都斷言剛好一行 WARNING（`[refused and no restart]` 寫明子程式起不回來）；HA 的 log 走 add-on log，不另掛 stdout handler |
| `apps/headscale/headscale_mcp_admin/connection.py:104-109`（規則，PaaS 沒有專屬測試檔對到這裡） | 改來源沿用秘密 422 | `tests/test_new_origin_secret.py`（九個產品；§8.8 #115 寫差異） |

## 6. 守門有效的證據

### 6.1 先紅後綠

- 紅（`df686dd` 的程式＋本片的測試，repo 外的快照 `snapR`；2026-11-16 21:18）：215 案，**54 失敗、161 通過**（13 秒）。

| 檔 | 案數 | 失敗 | 通過的是什麼 |
|---|---|---|---|
| `test_odoo_identity_rotation.py` | 28 | 23 | 5 案「其他產品開通後不換 token」（守今天的行為） |
| `test_new_origin_secret.py` | 41 | 11 | 30 案：同來源、帶 null、整份取代、順序、沒開通、OpenDesign（都是守今天的行為，本來就該過） |
| `test_odoo_multi_profile.py` | 3 | 1 | 審批不跨帳號（隔離來自每帳號一個子程式，HM-09 起就有；本片補測試釘住）、DQ-30 |
| `test_saved_destinations.py` | 90 | 18 | 72 案沒變；改過的 18 案（開通後改到別的來源的 `backend/patch` 一起帶秘密）用到還沒有的 `backend_edit.url_secrets` |
| `test_profile_runtime.py`（只跑改過的那一案） | 1 | 1 | — （`make_apps` 還沒有 `stop_child`） |
| `test_upgrade_zero_rewrite.py`、`test_identity_fields.py` | 37、15 | 0 | 只改說明與 `UNWIRED`（實作 import `identity_fields` 之後，舊的 `UNWIRED` 才會紅） |

- 失敗的原因（`E` 行歸類）：`ProductStore` 沒有 `rebind`、`backend_edit` 沒有 `url_secrets`／`origin`、`identity_fields` 沒有
  `URL_SECRETS`、改到別的來源今天回 200 而不是 422、回應沒有 `token_rotated`、`make_apps` 沒有 `stop_child`：都是「功能還沒有」。
  只有 1 案不是：`test_switched_off_…`（測試自己的錯，見下一點）。
- 第一次綠（21:18，實作後）：279 案中 1 案失敗：`test_switched_off_an_identity_change_keeps_todays_answer_order_and_token`。原因是測試
  自己的錯：第二次存檔的整份連線在迴圈開始前就組好，用了第一次存檔之前的 username。改成送出時才組（實作沒改）。這一案在紅的時候也是因為
  同一個錯而失敗，所以另外在 `df686dd` 的程式上重跑修好的這一案（21:21，`red2`）：**通過**（沒開通照今天）；對照的 7 案換身分仍然失敗。
- 綠（21:21，`green2`）：本片的 6 個測試檔＋`test_profile_runtime.py`，**279 案全過**（19.8 秒）。
- 全套之後改的兩個測試（HM-31 的參數順序、`stop_child` 選項）：在 `df686dd` 的程式上 2 案都失敗（22:35，`red3`），實作上全過（第 8 節）。

### 6.2 臨時突變（快照 `snapG`，一次改一處、跑相關的檔、還原；`-x`）

17 個全部擋下（每個 1～3 秒；M17 在全套之後補）：

| # | 突變 | 擋下的測試 |
|---|---|---|
| M01 | 不先停舊子程式 | `test_a_changed_identity_…[url-backend]`（journal：寫入時子程式還在跑） |
| M02 | 不發布 token 變更 | 同上（journal 沒有 publish） |
| M03 | 只換密碼也換 token | `test_a_password_change_or_the_first_setup_keeps_the_token` |
| M04 | 清空不換 | `test_a_cleared_connection_rotates_the_token` |
| M05 | 結果不明時也重起舊子程式 | `test_a_write_whose_outcome_is_unknown_…[replace]` |
| M06 | rebind 在取代之前失敗也毒化 | `test_a_failed_identity_change_…[write]` |
| M07 | 不檢查新來源 | `test_switched_on_a_url_moved_to_another_origin_must_bring_its_secrets[emqx]` |
| M08 | 比整條網址、不比來源 | `test_switched_on_a_url_on_its_own_origin_keeps_its_stored_secrets[emqx]` |
| M09 | 新來源檢查沒開通也做 | `test_switched_off_a_url_moved_to_another_origin_keeps_todays_save[emqx]` |
| M10 | 換身分沒開通也換 | `test_switched_off_an_identity_change_keeps_todays_answer_order_and_token` |
| M11 | 停掉的子程式留著 spec | `test_a_write_whose_outcome_is_unknown_…[replace]` |
| M12 | 沒存過的秘密也要帶 | `test_a_secret_brought_as_null_or_never_stored_is_not_carried` |
| M13 | 新來源檢查放在 `backend_fixed` 前面 | `test_the_refusal_comes_after_the_checks_that_precede_it` |
| M14 | 停失敗後不重起 | `test_a_failed_identity_change_…[stop]` |
| M15 | 回應沒有 `token_rotated` | `test_a_changed_identity_…[url-backend]` |
| M16 | 新子程式起不來時重起舊子程式 | `test_a_new_child_that_cannot_start_leaves_the_new_token_and_never_the_old_child` |
| M17 | `make_apps` 不檢查 `stop_child` 能不能呼叫 | `test_make_apps_takes_a_child_stop_it_can_call` |

### 6.3 審查後補的守門（2026-11-17；`scripts` 與 log 在 `artifacts/…/wave4/evidence-fix-HM-12/`）

- 紅（R0）：把 `gateway.py` 換回審查前（`8b56b70`），跑審查後的 `test_odoo_identity_rotation.py`（repo 外的複本，排共用鎖）：33 案 **6 失敗**、
  27 通過（3.2 秒）。行為上的 2 案：`[unexpected]`（`ValueError` 原樣丟出，正式環境是 500）、`test_a_write_that_raises_with_its_new_token_on_disk_…`
  （`OSError` 原樣丟出，而且會重起舊子程式）。另外 4 案只是結果不明 WARNING 的新文字（兩個結果不明案例、預設帳號兩案；這幾案在文字之前的
  行為斷言都過了）。ETag 與分派器層的斷言在審查前的程式上本來就會過（程式本來就對，S-3、S-4 是測試缺口），由下面的突變證明它們有用。
- 突變（同一個複本，一次改一處，`-x` 跑 `test_odoo_identity_rotation.py`，還原後用 SHA-256 驗證；複本 `git status` 前後相同）：**6 個全部擋下**。

| # | 突變 | 擋下的測試 |
|---|---|---|
| M1 | 審查的 X12：換身分回應不帶 `ETag` | `test_a_changed_identity_…[url-backend]`（S-3） |
| M2 | 審查的 X18：分派器把舊 token 留作別名 | `test_a_changed_identity_…[url-backend]`（S-4） |
| M3 | S-5 改回去：store 讀得到就重起舊子程式（不看磁碟上的 token） | `test_a_write_that_raises_with_its_new_token_on_disk_never_relaunches_the_old_child` |
| M4 | S-5 改回去：原樣丟出寫入的例外（`ValueError` 變 500） | `test_a_failed_identity_change_…[unexpected]` |
| M5 | 審查的 X07：不管磁碟上是什麼都重起舊子程式 | `test_a_write_whose_outcome_is_unknown_…[replace]` |
| M6 | S-2：分派器讀不到預設帳號的 state 時照額外帳號處理（不回 503） | `test_the_default_profiles_write_of_unknown_outcome_closes_what_reads_its_state[directory sync]` |

## 7. HM-01 黃金回歸與契約凍結（開關關；開通重跑）

- 期望值一個都沒改：`tests/test_single_profile_golden.py`、`tests/test_mcp_contract_freeze.py`、`tests/test_admin_contract_freeze.py`、
  `tests/contract/*.json` 都沒動。
- 結果（全套 pytest 的 junit，實作的最後版本）：`test_single_profile_golden.py` 17 案、`test_mcp_contract_freeze.py` 9 案、
  `test_admin_contract_freeze.py` 19 案、`test_router_passthrough.py`（開通重跑三組凍結）49 案，**全過**。
- 為什麼不用改：沒開通時 `identity_rebound`、`new_origin_refused` 都回 False，提交步驟照今天；`ProfileRuntime` 多交的 `stop_child` 沒開通時
  沒有路徑呼叫；`Store._write` 的預設照今天。開通重跑（`tests/test_router_passthrough.py` 的管理契約凍結）用的存檔是「欄位值不變的部分編輯」
  （`unchanged_field`）：不換來源、不換身分，所以也不帶 `token_rotated`、不會 422。
- 審查修正後重跑（2026-11-17）：同樣 45 案全過（`test_router_passthrough.py` 在 HM-08／HM-14 那一組，也全過）。
- 審查的觀察：「沒開通也換 token」（X16）與「沒開通也回 422」（X23）只有本片的兩個開關關測試擋得住，HM-01 的黃金回歸與兩個契約凍結
  本身擋不住（它們不換身分、不換來源）。`test_switched_off_an_identity_change_…`、`test_switched_off_a_url_moved_…` 要一直保留。

## 8. 本機檢查（2026-11-16，一般使用者 uid 1000；Python 3.13.15；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排隊在共用鎖）

| 檢查 | 結果 |
|---|---|
| 紅（`df686dd` 的程式＋本片的測試） | 215 案：54 失敗、161 通過（第 6.1 節） |
| 綠：本片的 6 個測試檔＋`test_profile_runtime.py` | 279 案全過（19.8 秒） |
| 臨時突變 | 17 個全部擋下（第 6.2 節；M17 是全套之後補的） |
| 全套 pytest（`tests`，實作的最後版本） | 6,047 案：6,017 通過、30 失敗、0 skip（1,962 秒）。失敗的 30 案：22 個瀏覽器測試（這個 clone 當時沒裝 Chromium）、7 個要 root 的既有案例、1 個本片造成的：HM-31 的 `test_make_apps_takes_only_a_share_of_a_budget_beside_hm09s_and_hm10s_options` 釘住 `make_apps` 最後四個參數，本片在後面加了 `stop_child`。改成釘住最後五個（最後是 `stop_child`），另加 `stop_child` 選項的測試 |
| 全套之後改的兩個測試＋瀏覽器測試（裝好 Chromium 後） | 紅：在 `df686dd` 的程式上這兩案都失敗（`red3`）。綠：`test_request_budget_gateway.py` 37 案、`test_odoo_identity_rotation.py` 29 案（含 `stop_child` 選項）、`test_profile_runtime.py` 65 案、三個瀏覽器測試檔 52 案（含全套時失敗的 22 案），共 **183 案全過**（59.5 秒） |
| packaging | `packaging/validate.py` PASS；`unittest discover -s packaging`：Ran 203、OK（skipped=5） |
| 審查修正後：受影響的 7 組（2026-11-17，修正後的工作樹；`evidence-fix-HM-12/logs/g1-*`、`g2-static`） | 本片 6 檔＋`test_profile_runtime.py`＋`test_request_budget_gateway.py` 321 案、HM-10 管理 API 64 案、HM-08／HM-14 路由與佇列 239 案、HM-01 黃金回歸與兩個契約凍結 45 案、其他相關 18 檔 698 案、讀帳本的 3 檔 123 案、讀原始碼與 log 遮罩的 7 檔 396 案：共 1,886 案，只有 1 案沒過（`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`，既有、要 root） |
| 審查修正後的紅與突變 | 第 6.3 節：紅 6 案失敗；突變 6 個全部擋下 |
| 最後一個改程式與文件的 commit（`dc837c5`）重跑 | `gateway.py` 最後只改了註解，重跑新 3 檔、讀帳本的 3 檔、`test_upgrade_zero_rewrite.py`、`test_secret_path.py`：257 案全過（38.5 秒） |
| packaging（審查修正後） | `packaging/validate.py` PASS；`unittest discover -s packaging`（離線暫存 venv）：Ran 203、OK（skipped=5） |
| 帳本預檢、秘密預檢 | 第 13 節 |

- 審查修正後沒有重跑全套 pytest：修正只動開通後換身分失敗的那段（`rebind_identity` 的 except）、說明文字與帳本；改到的路徑、讀原始碼
  與帳本的測試、HM-01 與各片相關的測試都在上表的 7 組裡。全套以 CI 為準。

### 8.1 只在 CI 跑的測試

- 要 root、本機一定失敗的 7 個既有案例（不是本片造成）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`。CI 用 root 跑。
- 瀏覽器測試（22 案）：全套時這個 clone 還沒裝 Chromium；裝好後補跑全過（第 8 節）。
- 本片新增與改過的測試都在本機跑過（沒有只在 CI 跑的）。它們在 root 下也成立：不依賴 uid 或檔案權限；故障注入換的是 `os.open`、
  `os.replace`、`os.fsync` 對特定路徑或目錄的行為，不靠權限；真子程式那一案只連 127.0.0.1 的臨時 port。
- Python：CI 3.13.16、本機 3.13.15。

### 8.2 `checks` 秒數與新測試的時間

- `checks`：開 PR 後補（前：`claude-delivery` 最近一次 PR run，約 27～29 分鐘；後：本片 PR）。
- 新測試的本機秒數（全套 pytest 的 junit）：`test_odoo_identity_rotation.py` 28 案 1.9 秒、`test_new_origin_secret.py` 41 案 1.5 秒、
  `test_odoo_multi_profile.py` 3 案 2.2 秒（真的兩個 Odoo 子程式那一案 2.1 秒），全套之後補的 `stop_child` 選項 1 案 0.02 秒，合計 73 案約
  5.6 秒；改過的檔沒有變慢。
  CI 推估：GitHub runner 約本機的 1.5～2 倍，新 3 檔約 8～11 秒。只有一案起真子程式（兩個，共用一個 runtime），其他都在同一個程序裡。
- 審查修正後（2026-11-17，`g1-a-hm12` 的 junit）：`test_odoo_identity_rotation.py` 33 案 2.6 秒、`test_new_origin_secret.py` 41 案 1.3 秒、
  `test_odoo_multi_profile.py` 3 案 3.7 秒（真子程式那案 3.4 秒；這台機器這時比較忙），合計 77 案約 7.6 秒。審查後加的 4 案共約 0.5 秒，
  都在同一個程序裡（沒有新的真子程式）。CI 推估約 11～15 秒（審查者估 10～15 秒），在預算內。
- 本機全套 1,962 秒（32 分 42 秒；含 22 個瀏覽器測試的快速失敗）。

## 9. 本片用到的決策（`docs/multi-profile/decisions.md`）

| DQ | 結論（使用者已定） | 本片怎麼用 |
|---|---|---|
| DQ-05 | 照計畫 §9：Odoo 換 url／database／username 時先停舊子程式 → 一次寫新連線＋新 token＋history（`rotate`）→ `TokenAccess.committed()` → 起新子程式；提交失敗用舊 state 重起；回 `token_rotated:true`；只換密碼或初次設定不換 | 全部照做。「提交失敗用舊 state 重起」再細分：磁碟上還是舊 token（store 拒絕、取代之前失敗、寫之前丟出例外）→ 重起；取代途中失敗（結果不明）或新 token 已在磁碟上 → 不重起（第 3.2 節，契約 #114）。審查 S-1：細分已記進 `decisions.md` DQ-05 列；主對話 2026-11-17 已在合併前向使用者說明。Nextcloud、Hermes 的比照不在本片 |
| DQ-40 (a) ⑨ | 改 url 來源要重填秘密：全部產品，產品開通後才生效 | `backend_edit.new_origin_refused`；九個產品都測；沒開通照今天 |
| DQ-40 (a) ⑩ | 換使用者欄位換 token 擴到 Nextcloud、Hermes | 不在本片（HM-22、HM-24）；`products.IDENTITY_BOUND` 只放 Odoo，`identity_fields.TOKEN_ROTATING` 已有它們的欄位 |
| DQ-30 | Odoo 讀取並行首發維持 1 | 沒改 `apps/odoo/launch.py`；`test_every_odoo_tool_still_runs_on_the_childs_one_worker` 釘住 `BoundedTools(capacity=1)` |
| DQ-02 (a) | 新帳號不記 history | 不受影響：建立帳號不是換身分（第一筆連線是初次設定，不換） |
| DQ-09 | 撞號 503 | 新 token 照 `token/rotate` 用 `secrets.token_urlsafe(32)`，不另外避開別的帳號的 token（機率可忽略；真的撞了照 DQ-09 回 503） |
| DQ-15、DQ-17 | 帳號 ETag 帶 id；`X-MCP-Profile` | 換身分後 ETag 照新 state 算；API 測試全部經 8099 分派器、帶 `X-MCP-Profile` |
| DQ-36 | 署名、不合併 | commit 不加署名；本片不合併（rebase 後 push、開 PR；合併由主對話在 CI 全綠後做） |
| DQ-37 (a) | 同 uid＝同一信任邊界 | chatter 預覽確認那一條的理由（威脅模型第 3 節） |

沒有碰到待定題（DQ-35、DQ-42、第 3 節各題都和本片無關）。

## 10. 前面各片交給 HM-12 的待辦處理表（grep 各片 provenance 的「HM-12」與「交給後面的片」）

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-10 筆記第 6 節（§3.1 `backend`、`backend/patch`）、第 13.2 節 | Odoo 換身分換 token，經分派器（`admin_action` 不變：分派器照舊呼叫帳號的動作） | 做了：`admin_action` 的提交步驟改走 `rebind_identity`；`test_odoo_identity_rotation.py` 的 API 案例全部經 8099 分派器（預設帳號與額外帳號） |
| HM-10 第 13.2 節（任務轉述） | 舊 token 立刻在 8081 失效 | 做了：兩條入口 401／404、分派器路由（state 檔簽章重讀）、HM-08 的 lease、HM-14 佇列中的請求（第 3.3 節；`test_the_new_token_reaches_no_child_before_the_new_one_and_the_old_tokens_requests_end`） |
| HM-10 第 13.2 節 | A 的審批 token 在 B 被拒 | 做了：`test_an_approval_is_executed_only_by_the_child_of_the_profile_that_approved_it`（真子程式；兩帳號 state 相同的對照） |
| HM-07 第 12 節第 3 點、`ledger-tracking.md`（`identity_fields.py` 之後會改的片：HM-12） | 接線時改 `UNWIRED`；改到就更新帳本 | 做了：`UNWIRED` 只剩 `restore_detect`；`identity_fields.py` 加 `URL_SECRETS`、帳本重算 |
| HM-07（`TOKEN_ROTATING` 含 Nextcloud、Hermes） | — | 本片只接 Odoo（`IDENTITY_BOUND`）；Nextcloud、Hermes 交 HM-22、HM-24 |
| `decisions.md` DQ-30（負責片 HM-12） | 讀取並行維持 1 | 做了（第 9 節） |
| 計畫 §16 UC-21、`deviation-trace.md` FM-81 | 「先提交再停」之間新 token 會不會打到舊子程式：未確認，由 HM-12 的測試確認 | 本片照「先停再提交」做，所以不會：寫入當下子程式已停（journal）、新子程式起來前新 token 碰不到任何子程式（測試）。`deviation-trace.md` 是 repo 外產生器的輸出，沒手改：下次重產時 FM-81 的說明欄改成「HM-12 先停再提交，已確認」（交 HM-18 或主對話） |
| `acceptance-matrix.md` T-03、T-10、測試檔登記表 | 三個測試檔 | 做了（登記表改「新增」；T-03、T-10 的 HAOS 實機部分仍是 HM-19b） |
| `paas-test-mapping.md` 第 115、339、658～660、683 列 | PaaS 測試對到 HM-12 的檔 | 做了（第 5 節逐案） |
| 契約第 3.1 節 `backend` 列、第 4.1 節 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 列（負責片「HM-12、HM-26」） | 定案 | 做了；Headscale 也在本片的規則裡（開通後生效），HM-26 不用再做這條，只要在它的開通測試裡涵蓋 |
| 威脅模型 I11 | 測試欄 | 做了 |
| HM-06、HM-08 | 沒有交給 HM-12 的事項 | 沿用 HM-08 的路由摘要與 lease、HM-14 的結尾，沒有改它們 |

## 11. 面板部分（另開 PR，疊在本 PR 上；本片不改 `Hui/`）

後端給面板的回應（開通後；沒開通照今天，面板不用分支）：

| 情況 | 狀態 | 本體 | 面板要做的事（建議） |
|---|---|---|---|
| 換身分存檔成功 | 200 | `{"saved":true,"token_rotated":true,"configuration":{…},"profile":{"id":…}}`；`ETag` 標頭是新 state 的（等於下一次 bootstrap 的，審查 S-3 有測試） | 提示「帳號換了：舊的 MCP 網址已撤銷，到 Tokens 複製新網址」；藏起畫面上已顯示的 token、重抓 bootstrap（`token_masked`、`token_history` 都變了）；下一次存檔可以直接用回應的 `ETag` 當 If-Match |
| 換身分存檔成功、新子程式起不來 | 503 | `{"saved":true,"token_rotated":true,"detail":{"code":"config_apply_failed"},"configuration":{…},"profile":{"id":…}}`；`ETag` 同上 | 同上，再加今天的「已存檔但子程式沒起來」文字 |
| 沒換 token 的存檔 | 200／503 | 照今天（沒有 `token_rotated` 鍵） | 不用改 |
| 改到別的來源沒帶秘密 | 422 | `{"error":"request denied","detail":{"code":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}`（沒有回聲） | 文案：「網址改到另一台伺服器，請重新輸入這個網址要用的密碼／金鑰（不會沿用已存的）」；送出前就提示更好：部分編輯表單在網址的來源改了時，把該網址的秘密欄位從「保留已儲存憑證」改成必填（對照表照 `identity_fields.URL_SECRETS`，放進 `contracts.js`，加一個和 `test_identity_fields.py` 一樣的同步測試） |
| 舊子程式停不下來 | 503 | `{"error":"request denied"}` | 今天 503 的通用文字（稍後再試） |
| 寫不進去（含結果不明；不管丟出什麼例外，審查 S-5） | 503 | `{"error":"state unavailable"}` | 今天的文字；結果不明時要重啟 add-on（DOCS，HM-18）。**重啟後 token 可能已經是新的**（舊網址失效，但這次沒收到 `token_rotated`）：提示「重啟後到 Tokens 確認網址，可能已換」（審查 S-7）。預設帳號結果不明時 8081 所有帳號都可能 503 到重啟 |

待補清單：① `token_rotated` 提示與藏 token、重抓；② 422 文案與表單的必填規則；③ `contracts.js` 的網址↔秘密對照與同步測試；
④ `profiles.test.mjs`／瀏覽器測試補這幾種回應（含形狀 D＋`token_rotated`、422 沒有回聲）；⑤ fixture server 照上表回；
⑥ 503 state unavailable（結果不明）的提示補「重啟 add-on 後到 Tokens 確認網址，可能已換」（審查 S-7）；⑦ 換身分回應的 `ETag` 照用
（面板今天怎麼處理存檔回應的 `ETag`，照 HM-11 合併後的寫法；不另加規則）。

## 12. 待 HM-03a 確認的項目

- 沒有本片必須等探針的項目（UC-21 已由測試確認：第 10 節）。
- 可以順便確認的（不擋本片）：① Ingress 對 422、503 的本體原樣轉送（面板只認 `detail.code`）；② HAOS 上 `/data` 的檔案系統在
  rename 失敗時不會改到檔案（本機 ext4 的 POSIX 語意；`_write` 的「取代之前」判斷依此）。

## 13. 預檢結果

審查修正後（2026-11-17）在 `dc837c5`（最後一個改程式與文件的 commit；工作樹乾淨）重跑；本筆記的 commit 只加這份筆記的文字，開 PR 前
rebase 後在最後的 HEAD 再跑一次（第 18.8 節）。

- 秘密預檢（`dc837c5`）：`--base df686dd --head HEAD --full`，gitleaks 8.28.0（pin、驗過），10 個 commit＋HEAD 樹＋整段歷史，**0 命中**。
- 帳本預檢（`dc837c5`）：`--base df686dd`：`runtime-patches.json` 175、`runtime-sources.json` 70、`tool-surface.json` 159 個摘要都 0 漂移、
  0 缺；本片改 20 個檔，列管的 6 個都隨 `runtime-patches.json` 更新；沒有新的未列管 runtime 檔：**OK**。

審查前（`8b56b70`，作者第一次交出時）：

- 秘密預檢：`.venv/bin/python -I scripts/secret_precheck.py --tools <gitleaks-tools> --repo . --base df686dd --head HEAD --full`：
  gitleaks 8.28.0（pin、驗過），本片 6 個 commit＋HEAD 樹＋整段歷史，**0 命中**。另外在 commit 之前用 gitleaks 的 dir 模式（預設規則、
  沒有 triage 允許清單）掃過本片改的檔：只有帳本裡 3 個既有的 guarded-source 摘要（`df686dd` 就有、本片沒動，builder 的設定用
  `packaging/secret-triage.json` 放行）。
- 帳本預檢：`.venv/bin/python -I scripts/ledger_precheck.py --repo . --base df686dd`：`runtime-patches.json` 175、`runtime-sources.json` 70、
  `tool-surface.json` 159 個摘要都 0 漂移、0 缺；本片改 19 個檔，列管的 6 個（`backend_edit.py`、`config.py`、`gateway.py`、
  `identity_fields.py`、`products.py`、`profile_runtime.py`）都隨 `runtime-patches.json` 更新；沒有新的未列管 runtime 檔：**OK**。

## 14. 驗收條件（計畫 §12.3 HM-12）

| 條件 | 狀態 |
|---|---|
| 全綠 | 本機：除了 7 個要 root 的既有案例（只在 CI 跑），全部通過（全套 6,047 案；全套之後改的與補跑的 183 案；審查修正後受影響的 7 組 1,886 案只剩其中 1 案；rebase 後見第 18.7 節）；CI（root、0 skip）開 PR 後才知道 |
| 非 Odoo 產品與開關關時行為不變（DQ-40 ⑨ 只在開通後） | 本機通過：沒開通的 Odoo 換身分照今天（`test_switched_off_an_identity_change_keeps_todays_answer_order_and_token`）、九個產品沒開通時新來源照今天存（`test_switched_off_a_url_moved_to_another_origin_keeps_todays_save`）、開通的 Hermes／Nextcloud／EMQX／LiteLLM／Headscale 不換 token（`test_switched_on_the_other_products_keep_their_token_on_a_changed_backend`）；HM-01 黃金回歸與兩個契約凍結（含開通重跑）照過（第 7 節） |
| 獨立安全審查 | **通過**（2026-11-16 23:00～23:45，審查者不是作者；報告 `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-12.md`）：必修 0 項、建議 9 項，都採用並處理（第 17 節）。S-1 的細分主對話 2026-11-17 已在合併前向使用者說明 |

## 15. 還沒解決、交給後面的片

- **面板（另開 PR，疊在本 PR 上；主對話 2026-11-17 決定）**：第 11 節的待補清單 ①～⑦。開關關時面板與回應逐位元照今天，
  所以分兩個 PR 合併不影響已發版的產品。
- **HM-22（Nextcloud 開通）**：換 url／username 換 token（DQ-40 ⑩，PaaS #154 `0f94aa4`）：把 `nextcloud` 加進 `products.IDENTITY_BOUND`，
  沿用本片的 `rebind_identity`、`ProductStore.rebind`、`stop_child`，補它自己的測試；PaaS #152 的存檔 SSRF 對照 HM-20。
- **HM-24（Hermes 開通）**：換 gateway_url／dashboard_url／dashboard_username 換 token，同上。注意 Hermes 的 dashboard 可以整組清空
  （三欄都 null）：清空算不算「換身分」照本片 Odoo 的規則（清空也換）再確認一次。
- **HM-13c**：還原或休眠後未核對前 `token/rotate` 409 `restore_review_required`。審查核對過：`identity_rebound` 要求 token 有效，還原與休眠
  的帳號 token 已撤銷，所以待核對期間換身分**不會**發新 token。HM-13c 只要維持「待核對＝已撤銷」，換身分不用另擋；要改這個前提時再回頭看。
- **HM-26（Headscale 開通）**：新來源要重填秘密已經涵蓋 Headscale（開通後生效），HM-26 只要在它的開通測試裡涵蓋，不用再實作。
- **HM-18（文件定稿）**：DOCS 寫「開通後換 Odoo 的 url／database／username 會換 token，舊網址立刻失效，到 Tokens 複製新網址；只換密碼不換」、
  「網址改到另一台伺服器要重新輸入密碼／金鑰」、「存檔回 503 state unavailable 時重啟 add-on，**重啟後到 Tokens 確認網址，可能已換**」（審查 S-7）、
  「預設帳號的換身分存檔結果不明時，8081 所有帳號都 503 到重啟」（審查 S-2）、「同一來源只換路徑會沿用已存秘密，換路徑前確認兩條路徑後面
  是同一個服務」（審查 S-8，已知限制）；`deviation-trace.md` 重產時 FM-81 的 UC-21
  改成已確認（第 10 節）；計畫 §7.2 第 7 點照本片的實際行為（含清空也換、失敗的回應）。
- **HM-19b（HAOS 驗收）**：T-03（換身分換 token、兩條舊網址都失效、只換密碼不換）與 T-10（A 的寫入審批在 B 被拒）的實機部分。
- **HM-29（回補 PaaS 的建議）**：① 新來源要重填秘密擴到全部產品（PaaS 只有 Headscale）；② PaaS 的寫入在 replace 之後失敗時，快取留舊值、
  磁碟可能已是新值（兩邊不一致；HA 毒化到重啟）；③ 新來源只比來源、同一來源換路徑不算（HA 的已知限制；PaaS Headscale 比整條網址），
  兩邊要不要一致一起說明（審查 S-8）。
- **開 PR 前（rebase 到 `claude-delivery`）**：2026-11-17 已做（第 18 節；本片的三列是 #113～#115）。以下是當時寫的待辦：
  HM-11 已合併（PR #107，`f4c7718`），佔用契約第 9 節 #109～#112。本片的三列改成接在當時的
  最後一列後面（若中間沒有別的片合併，是 #113～#115），一次改完：契約第 3.1 節 `backend` 列（「§8.8 #110」）、第 4.1 節
  `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 列（「#111」）、第 9 節說明段與三列、第 10 節本片兩列；威脅模型第 3 節（#110、#111）；
  本筆記；PR 說明。程式、測試、帳本的 `change` 文字已經不寫這三個列號（審查 S-6），rebase 不用為列號重算帳本；但 `runtime-patches.json`、
  `contract.md`、`decisions.md` 會和 HM-11 的改動相鄰或衝突，解完照資料重算帳本、重跑兩個預檢與受影響的測試（HM-11 新增的
  `tests/test_panel_profile_api_shapes.py` 也要跑）。
- **`checks` 秒數**（開 PR 後補）。

## 16. commit（`df686dd` 之後）

| commit | 內容 |
|---|---|
| `82a0323` | test(core)：本片的測試（先紅：在 `df686dd` 的程式上失敗） |
| `1abf02f` | feat(core)：換身分換 token、新來源要重填秘密（只在開通後） |
| `4cb0cac` | chore(provenance)：6 個列管檔的帳本重算 |
| `c855d2f` | docs(multi-profile)：契約、威脅模型、驗收矩陣 |
| `18141e9` | docs(multi-profile)：取代途中失敗的兩個時點各回什麼（只改文字） |
| `8b56b70` | docs(provenance)：本筆記（第一版） |
| `2b09336` | test(core)：審查後補的斷言與案例（S-2～S-6、S-9；在這個 commit 的程式上 6 案失敗，第 6.3 節） |
| `3f22c39` | fix(core)：寫入失敗一律 503、是否重起看磁碟上的 token（S-5）；程式說明拿掉列號（S-6）、補同來源換路徑的已知限制（S-8） |
| `0302ad1` | chore(provenance)：審查修正改到的 3 個列管檔的帳本重算（`change` 拿掉列號） |
| `dc837c5` | docs(multi-profile)：契約、威脅模型、`decisions.md`（DQ-05 細分）、驗收矩陣（S-1～S-5、S-7、S-8） |
| `d8d9ecf` | docs(provenance)：本筆記補審查意見處理表與重跑結果 |

rebase 後的編號與之後新加的 commit 見第 18.10 節。

## 17. 獨立安全審查與意見處理（2026-11-16 審查；2026-11-17 處理）

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-12.md`（證據 `wave4/evidence-review-HM-12/`）。判定**通過**，必修 0 項，
  建議 9 項（S-1～S-3 建議合併前處理）。
- 處理的證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-12/`（`session.log`、`logs/`、`junit/`、`mutations.json`、
  `mutations/`、`scripts/`；用過的 `/tmp/ha-mp-XXXXXX` 記在 `tmpdirs.txt`，都已用完整路徑刪掉）。
- 先核對再改：S-2（E2 與 `profile_router.py` 的 `resolve`）、S-5（E3 與 `rebind_identity`）、S-9（`git grep`）都照審查說的重現或確認；
  核對 S-5 時另外發現審查沒提到的一點（取代之後才丟出、不會毒化 store 的 `OSError`，舊子程式會在新 token 已在磁碟上時重起），一起修。

| # | 意見 | 決定 | 怎麼處理 | 證據 |
|---|---|---|---|---|
| S-1 | DQ-05「提交失敗用舊 state 重起」被細分成「結果不明不重起」，只寫在契約與 provenance | 採用 | `decisions.md` DQ-05 列補記細分（不是新題目），狀態欄與變更紀錄寫明**待主對話在合併前向使用者說明**；本筆記結論、第 9 節同步。向使用者說明要由主對話做（本片不能代答）。主對話 2026-11-17 已說明，兩處改成「已在合併前向使用者說明」 | `dc837c5`、`87af4cd` |
| S-2 | 預設帳號的新 state 檔已換上時 8081 所有帳號都 503，契約沒寫 | 採用 | 契約第 3.1 節 `backend` 列與 #114 補這句，另寫明預設帳號 `os.replace` 失敗只關預設帳號；威脅模型那一條同步；新測試 `test_the_default_profiles_write_of_unknown_outcome_closes_what_reads_its_state`（兩個時點）把兩種情況都釘住 | `2b09336`、`dc837c5`；M6 擋下 |
| S-3 | 換身分回應的 `ETag` 沒有測試（X12 存活） | 採用 | `test_a_changed_identity_…`（7 案）、預設帳號那案、`test_a_new_child_that_cannot_start_…` 都斷言回應的 `ETag` 等於下一次 bootstrap 的 `ETag`（也就是新 state 的 revision） | `2b09336`；M1（＝X12）擋下 |
| S-4 | 「分派器不再把舊 token 對到任何帳號」沒有測試（X18 存活） | 採用 | 換身分後斷言 `McpDispatcher.resolve(舊 token)` 是空的、`resolve(新 token)` 只有該帳號（額外帳號與預設帳號）；契約與第 3.3 節寫明兩層都拒絕 | `2b09336`；M2（＝X18）擋下 |
| S-5 | `rebind` 丟出 `ConfigError` 以外的例外時回 500 | 採用並擴大 | 寫入失敗一律回固定的 503 state unavailable；是否重起舊子程式改看磁碟上的 token（還是舊的才重起），不看例外種類，連帶補上「取代之後才丟出、不毒化 store 的 `OSError`」時不該重起的破口。新案例 `[unexpected]` 與 `test_a_write_that_raises_with_its_new_token_on_disk_never_relaunches_the_old_child` | `3f22c39`；紅 R0、M3、M4 擋下 |
| S-6 | 契約第 9 節列號會和 HM-11 撞，而且寫在 3 個列管檔 | 採用（審查給的第二個做法） | 程式說明、兩個測試檔說明、帳本 `change` 文字都拿掉 #109～#111（原稿的列號；rebase 後是 #113～#115，第 18 節），改寫成描述；文件裡的列號等 rebase 時一次重編（HM-11 已用掉 #109～#112，第 15 節列出要改的地方）。現在先不改文件的列號：其他片也可能先合併再佔號 | `2b09336`、`3f22c39`、`0302ad1` |
| S-7 | 面板待補清單漏「結果不明重啟後 token 可能已換」 | 採用 | 第 11 節表格與待補清單 ⑥、第 15 節 HM-18、PR 草稿、威脅模型那一條都補 | 本筆記、`dc837c5` |
| S-8 | 同一來源換路徑不要求重填秘密，威脅模型沒列 | 採用 | 威脅模型第 3 節加一條已知限制；契約 `backend` 列與 #115 補一句；`backend_edit.py` 說明補一句；第 15 節 HM-29 加一項 | `3f22c39`、`dc837c5` |
| S-9 | 測試說明寫了不存在的函式名 | 採用 | `tests/test_upgrade_zero_rewrite.py` 改成 `backend_edit.new_origin_refused` | `2b09336` |

- 沒處理的：無。審查第 4 節的觀察也照寫進來：HM-13c 不用另擋換身分（第 15 節）、開關關的兩個測試要保留（第 7 節）、兩道防線（第 3.3 節）。

## 18. rebase 到 claude-delivery（2026-11-17）

第 1～17 節照 rebase 前寫，裡面的 commit 編號是 rebase 前的（對照在第 18.10 節）；列號已照 rebase 後的改（第 18.4 節）。
證據在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-rebase-HM-12/`（`tools/` 是用到的腳本，副檔名多加 `.txt`；`logs/` 是 log
與 junit；`conflicts/` 是兩個衝突 commit 解衝突前的檔，含衝突標記）。

### 18.0 結論

- 基準換成 `claude-delivery` `f4c7718`（HM-11 的 PR #107 合併後）。11 個 commit 照原順序重放，衝突在 2 個 commit，都是文件
  （契約 3 塊、`decisions.md` 1 塊）。每塊都是兩邊各自加的行：新基準的行照原文放前面，本片的行照原文接在後面。
  程式、測試、帳本的 patch 和 rebase 前相同。
- 契約第 9 節本片的三列從 #109～#111 改成 #113～#115（HM-11 已用掉 #109～#112）。契約第 3.1、4.1、9、10 節與威脅模型第 3 節
  的引用一次改完，第 10 節加一列記這次改號（`6377159`）；本筆記另一個 commit 改（`77e8f96`）。
- `decisions.md` DQ-05 列與第 5 節本片那列改成「主對話 2026-11-17 已在合併前向使用者說明（審查判定安全上正確）」（`87af4cd`）。
- 帳本：git 自動合併。再以新基準的帳本為底照 JSON 重建（加回本片 6 列的說明、SHA-256 照 rebase 後的檔案重算），和合併結果
  逐位元相同；63 列全部照檔案重算，0 漂移。
- 語意衝突：沒有。HM-11 的真後端形狀比對沒有 `backend`、`backend/patch` 的案例，在新基準 10 個情境（94 個案例）照過；
  面板今天遇到本片的新回應也不會壞（第 18.6 節）。
- 本機：pytest 子集 10 組 2,229 案、全套 6,062 案（7 案失敗、0 skip），失敗的只有要 root 的既有案例；node 81、build-closure PASS、
  Playwright 117；`validate.py` PASS、packaging unittest Ran 203 OK（skipped=5）、`tool_inventory.py` exit 0。
- 兩個預檢 OK；`origin/claude-delivery..HEAD` 每個 commit 都沒有原始雙向控制字元（第 18.8、18.9 節）。

### 18.1 範圍

- `git fetch origin`：`origin/claude-delivery`＝`f4c7718`。先開本機備份分支 `backup/hm12-before-rebase-20261117`（指向 `d8d9ecf`，
  不 push）。開始時 clone 乾淨。
- `git log --oneline df686dd..d8d9ecf` 是 11 個。`df686dd` 是 `f4c7718` 的祖先（#107 用 merge commit 合併），所以直接
  `git rebase origin/claude-delivery`，只重放這 11 個。
- 新基準帶進來的（`df686dd..f4c7718`，39 個 commit）：HM-11（PR #107）。改了 22 個檔：面板（`packages/mcp-admin-ui/` 的
  `src/`、fixture、測試、README、Playwright 設定）、`packaging/ha_p9_admin.mjs`、`tests/test_panel_profile_api_shapes.py`、
  `docs/admin-write-contracts.md`、契約、`decisions.md`、HM-11 筆記、帳本。
- 和本片重疊的只有 3 個檔：契約、`decisions.md`、帳本。威脅模型、驗收矩陣、`gateway.py` 等新基準沒有改，沒有衝突。
- 依賴：`df686dd..f4c7718` 沒有動 `uv.lock`、`package.json`、`package-lock.json`、`pyproject.toml`、`requirements*`、
  `packaging/inputs.json` 與 patch 檔，沒有重跑 `setup_repo_env.sh`。

### 18.2 衝突與處理

解衝突用 repo 外的 `resolve_keep_both.py`：逐塊先斷言兩邊的行數與每行的開頭，再確認新基準那一側是 rebase 中 HEAD 的原文、
本片那一側是重放中 commit 的原文，最後寫成「新基準的行在前、本片的行在後」，兩邊都不改字。列號不在這一步改（第 18.4 節）。
兩邊改到同一列的情況沒有發生（各自只加列，或改不同的列）。

| rebase 後（原本） | 衝突 | 處理 |
|---|---|---|
| `aad73b1`（`c855d2f`） | 契約 3 塊：第 9 節說明段最後一行（HM-11 一行／本片一行）；表尾的列（HM-11 的 #109～#112／本片的 #109～#111）；第 10 節表尾（HM-11 三列／本片一列） | 每塊 HM-11 的行在前、本片的行在後，都照原文。威脅模型、驗收矩陣由 git 自動合併（新基準沒有改） |
| `6130ef3`（`dc837c5`） | `decisions.md` 1 塊：第 5 節表尾（HM-11 一列／本片一列） | HM-11 那列在前、本片那列在後。DQ-05 列由 git 自動合併（新基準改的是 DQ-12、DQ-14、DQ-31）；契約本片的 §3.1 `backend` 列、#110、#111 與第 10 節一列也自動合併 |
| 帳本 2 個（`9db93f5`（`4cb0cac`）、`2b868cc`（`0302ad1`）） | 沒有：新基準改的是 5 個面板檔的列，本片改的是 6 個核心檔的列 | git 自動合併；之後照 JSON 重建核對（第 18.5 節） |
| 其他 7 個 | 沒有 | 照原樣重放。`bb9226e`（`18141e9`）改的契約列只是上下文多了 HM-11 的列 |

### 18.3 核對

- `git range-diff df686dd..d8d9ecf origin/claude-delivery..ceb9aed`：8 個「=」（patch 相同，含帳本 2 個）；3 個「!」（`aad73b1`、
  `bb9226e`、`6130ef3`）差的只是上下文行（HM-11 的列），增刪行相同。
- 逐 commit（`same_change.py`，增刪行當多重集合比）：`c855d2f` 的契約 +9 −4、威脅模型 +10 −1、驗收矩陣 +4 −4；`dc837c5` 的契約
  +4 −3、威脅模型 +11 −4、驗收矩陣 +1 −1、`decisions.md` +2 −1：重放的都和原 commit 相同。
- 整段（`git diff origin/claude-delivery ceb9aed` 對 `git diff df686dd d8d9ecf`）：契約 +10 −4、`decisions.md` +2 −1、帳本 +12 −12
  逐行相同。本片其他 17 個檔和 `d8d9ecf` 逐位元相同；新基準改的 22 個檔，除了重疊的 3 個，和 `f4c7718` 逐位元相同；兩邊都沒碰的
  900 個檔和 `df686dd` 相同（`blob-compare.txt`）。

### 18.4 列號對照（契約第 9 節；新基準最後是第 112 列）

| rebase 前（`df686dd` 基準） | rebase 後（`f4c7718` 基準） | 項目 |
|---|---|---|
| #109 | #113 | 換身分存檔的回應 |
| #110 | #114 | 換身分途中失敗 |
| #111 | #115 | 新來源要重填秘密的判定 |

- 新基準的 #109～#112 是 HM-11 的面板列，本片沒有引用。#1～#108 沒有移動，本片引用的 #39、#40、#41、#49、#59、#60、#86 不變。
- 改了的地方（`6377159`，`renumber_docs.py`：每處先斷言原文剛好出現一次，HM-11 的列與引用斷言一字不變）：契約第 3.1 節 `backend`
  列（#110 → #114）、第 4.1 節 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 列（#111 → #115）、第 9 節說明段本片那行（寫明原稿
  列號與往後重編的原因）與三列、第 10 節本片的兩列；第 10 節另加一列記這次改號；威脅模型第 3 節兩處（#110 → #114、#111 → #115）。
  本筆記 12 處（`77e8f96`，`notes_renumber.py`；其中兩處順便寫明 rebase 前的列號）；PR 說明（repo 外的草稿）。
- 不用改的地方：程式、測試、帳本 `change` 文字（審查 S-6 已拿掉本片的列號；`git diff` 逐行查過，只剩沒有移動的 #40、#41、#59、
  #60 與「HM-12's row(s)」的描述）；驗收矩陣與 `decisions.md` 沒有寫這幾個列號（`git grep` 核對）。
- 本筆記第 15 節「開 PR 前」那段與 S-6 那列講的是當時的舊號，照原文（S-6 那列加一句指到新號）。
- commit 訊息照寫的當時，不改寫（舊號就是上表左欄）：`917d70d`（原 `1abf02f`）寫 #109、#110、#111；`aad73b1`（原 `c855d2f`）
  寫 #109～#111；`bb9226e`（原 `18141e9`）寫 #110；`6130ef3`（原 `dc837c5`）寫 #110、#111。`c72e172`、`9049bae`、`ceb9aed` 寫的
  #109～#112 是 HM-11 的列號。審查報告 `wave4/review-HM-12.md` 與之前的證據目錄也是舊列號、舊 commit 編號。

### 18.5 帳本（`docs/provenance/runtime-patches.json`）

不只看文字合併：用 `rebuild_ledger.py` 以新基準的帳本為底照 JSON 重建，再和 git 合併的結果逐位元比。

- 新基準 63 列，rebase 後 63 列（本片沒有新列）。57 列和新基準逐欄相同（含 HM-11 改的 5 個面板檔）。
- 本片改的 6 列：`change` 是新基準的文字接本片在列尾加的那段（腳本確認本片只在列尾追加）；`sha256` 照 rebase 後的實際內容重算：

| 列管檔 | 新基準 | rebase 前（`d8d9ecf`） | rebase 後 |
|---|---|---|---|
| `products.py` | `7fdf98c9d0e7` | `6ad274b238f3` | `6ad274b238f3` |
| `gateway.py` | `1f954cf11cde` | `84e331a9006f` | `84e331a9006f` |
| `profile_runtime.py` | `048e73896820` | `198afd436a3b` | `198afd436a3b` |
| `backend_edit.py` | `af3495130746` | `c926ace49e5b` | `c926ace49e5b` |
| `identity_fields.py` | `af6e130ceb36` | `2dbd605c1834` | `2dbd605c1834` |
| `config.py` | `78a2f79d76fd` | `c00cae167d7e` | `c00cae167d7e` |

- 重算的值和 rebase 前相同：新基準沒有動這 6 個檔。
- 63 列全部照 HEAD 的檔案重算 SHA-256：0 漂移。重建的帳本和 HEAD 的逐位元相同；兩個帳本 commit（`9db93f5`、`2b868cc`）各自
  照它們那時的檔案重建，也和 git 合併的結果逐位元相同。JSON 照 repo 的寫法（`indent=2`、`ensure_ascii=False`、結尾換行）。
- 沒有動 `apps/runtime/*.py`、`apps/*/launch.py`：不用 `tool_inventory.py --write`；檢查模式 exit 0。帳本預檢也 OK（第 18.8 節）。

### 18.6 語意衝突（HM-11 的面板、真後端形狀比對）

- `tests/test_panel_profile_api_shapes.py` 在新基準的真後端照過：10 個情境（94 個案例）全過，2.2 秒。`profile-api-cases.json`
  沒有 `backend`、`backend/patch` 的案例（錄的是帳號路由、bootstrap、token、policy、endpoint、收據、重啟），本片改的回應形狀
  不在裡面；`expect` 與 fixture 都不用改。fixture 對同一份案例的 `profile-api-parity.spec` 也 10 案全過。
- HM-11 的面板遇到本片的新回應（只在開通後出現；開關關時逐位元照今天）：
  - 換身分存檔 200：本體有 `profile:{id}` 回聲與 `saved:true`，`AdminApi.mutate` 照常接受；面板還不看 `token_rotated`，沒有提示。
  - 換身分、新子程式起不來（形狀 D＋`token_rotated`）：`config_apply_failed` 是面板認得的代碼，照今天的文字。
  - 422 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN`：錯誤回應不比回聲；代碼不在面板的已知表，顯示 422 的通用文字
    「欄位驗證未通過。請確認 URL、必要欄位與憑證格式。」
  - 503 `request denied`／`state unavailable`：照今天 503 的通用文字。
  - 所以不改面板也不會壞，只是沒有本片的專屬提示。這些放面板 PR（第 11 節待補 ①～⑦），疊在本 PR 上另開。`packages/mcp-admin-ui/`
    本片一個字都沒改。

### 18.7 本機檢查（一般使用者；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 都排在共用鎖後面）

程式在 `87af4cd` 之後沒有再改：之後的 commit 只改本筆記（測試不讀筆記），表裡的結果在最後的 HEAD 也成立。

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 81 案全過、0.24 秒（`87af4cd`） |
| `npm run build`＋`node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`；`--output` 與 `UI_EVIDENCE_DIR` 放 TMPDIR） | 117 案全過（`single` 97、`profiles-on` 20），3.8 分鐘（`87af4cd`，01:33～01:37，開始與結束時工作樹都乾淨）；其中 `profiles.spec` 16 案、`profile-api-parity.spec` 10 案 |
| pytest 子集 10 組（`87af4cd`，00:36 取得鎖、00:41 跑完） | 2,229 案，1 案失敗、0 skip：本片與相關 321（新 3 檔 77 案約 6.1 秒）、HM-10 管理 API 64、HM-08／HM-14 路由與佇列 239（含 `test_router_passthrough`）、HM-01 黃金回歸與兩個契約凍結 45、其他相關 18 檔 698（含 `test_monitor_cancel`）、讀帳本 3 檔 123、讀原始碼與 log 遮罩 7 檔 396、HM-11 形狀比對 10、HM-31 預算與結構 144（`test_request_budget`、`test_request_structure`；`test_request_budget_gateway` 在第一組）、`test_output_schemas` 189。失敗的 1 案是 `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（既有、要 root） |
| pytest 全套（`tests`，CI 的指令加 `-rfEs --durations=30`，正式 conftest） | 6,062 案：6,055 過、7 案失敗、0 skip，32 分 34 秒（`87af4cd`；01:33 取得鎖、02:05 跑完，開始與結束時工作樹都乾淨、HEAD 都是 `87af4cd`）。失敗的 7 案就是要 root 的既有案例（`test_owned_executable` 1、`test_profile_store` 1、`test_restore_detection` 5，都停在 uid 是不是 0 的那一行斷言）。2 個 DeprecationWarning（websockets.legacy，既有）。比 HM-11 rebase 時的全套（5,985 案）多 77 案，就是本片新 3 檔的案數 |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15） | PASS（`87af4cd`） |
| packaging unittest（CI 的做法：離線暫存 venv，`uv sync --frozen --no-dev` 再裝 `requirements-ci.txt`） | Ran 203、OK（skipped=5） |
| `scripts/tool_inventory.py` | exit 0 |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`packages/mcp-admin-ui/`、`apps/`、`packaging/` 對新基準 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |

### 18.8 預檢（base 都是 `origin/claude-delivery`）

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | OK，0 命中（gitleaks 8.28.0，pin、驗過；`f4c7718..77e8f96` 14 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | OK：`runtime-patches.json` 176 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的 20 個檔裡 6 個核心檔由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔（`77e8f96`） |

本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 18.9 雙向控制字元

`bidi_scan.py` 逐 commit 查 `origin/claude-delivery..HEAD`：那個 commit 的樹裡、這段範圍碰過的每個文字檔的全文；那個 commit
自己新增的行；commit 訊息（標題與內文）。`77e8f96`（本筆記之前的 14 個 commit）上：U+202A～202E、U+2066～2069 合計 0 個；
U+200E、U+200F、U+061C 也是 0 個。這段範圍碰過的 20 個檔都是文字檔，沒有跳過的檔。本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 18.10 commit 對照

「相同」＝`git range-diff` 的「=」（patch 相同）。

| # | rebase 前 | rebase 後 | 說明 |
|---|---|---|---|
| 1 | `82a0323` | `a5740d8` | 相同 |
| 2 | `1abf02f` | `917d70d` | 相同 |
| 3 | `4cb0cac` | `9db93f5` | 相同（帳本，自動合併；照 JSON 重建核對） |
| 4 | `c855d2f` | `aad73b1` | 衝突（契約 3 塊）；兩邊照原文 |
| 5 | `18141e9` | `bb9226e` | 增刪行相同（上下文多了 HM-11 的列） |
| 6 | `8b56b70` | `50924ff` | 相同 |
| 7 | `2b09336` | `c72e172` | 相同 |
| 8 | `3f22c39` | `9049bae` | 相同 |
| 9 | `0302ad1` | `2b868cc` | 相同（帳本，自動合併；照 JSON 重建核對） |
| 10 | `dc837c5` | `6130ef3` | 衝突（`decisions.md` 1 塊）；兩邊照原文 |
| 11 | `d8d9ecf` | `ceb9aed` | 相同 |

rebase 之後新加的 commit：

| commit | 內容 |
|---|---|
| `6377159` | 契約與威脅模型：本片的列改成 #113～#115，第 10 節加一列 |
| `87af4cd` | `decisions.md`：DQ-05 的細分主對話 2026-11-17 已在合併前向使用者說明 |
| `77e8f96` | 本筆記改列號（12 處；第 18.4 節） |
| 本筆記 | 第 18 節；結論、第 1、2、9、11、13～17 節的狀態 |

### 18.11 只在 CI 跑的測試、CI 時間

- 這次沒有新增或改動任何測試。照第 8.1 節：沒有只在 CI 跑的新測試；要 root 的 7 個既有案例本機一定失敗。
- 新 3 檔本機約 6.1 秒（第 18.7 節），和第 8.2 節的推估一樣；`checks` 實際秒數 CI 跑完再補。

### 18.12 交給主對話與後面的片

- push：`git push -u origin feat/ha-multiprofile-hm12-20261116`（push 前查過遠端沒有這個分支）。備份分支只在本機。PR 只開一個、不合併。
- 面板：另開 PR，疊在本 PR 上（第 11 節待補 ①～⑦）。開關關時面板與回應逐位元照今天，所以分兩個 PR 合併不影響已發版的產品。
- 列號：HM-13b（PR #108）的分支也在契約第 9 節加列（它那邊是 #113～#116）。先合併的拿號，後合併的一方 rebase 後接在當時最後一列後面重排。
- 其餘照第 15 節（HM-22、HM-24、HM-13c、HM-26、HM-18、HM-19b、HM-29）。
