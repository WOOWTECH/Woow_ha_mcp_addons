# HA 多帳號 HM-13c provenance：還原核對與全部撤銷的路由與面板，單帳號還原後的面板提示（2026-11-16～17）

## 結論

- **疊在 HM-13b 的 PR #108 head `ebab019` 上**（`claude-delivery` `f4c7718`＋HM-13b 的 26 個 commit）。HM-13b 要等 HM-03a 的實機結果才合併；
  之後由主對話把本片 rebase 到 `claude-delivery`。本片只 commit，沒有 push、沒有開 PR。
- **單帳號還原後的面板提示（使用者 2026-11-16 21:xx 對 HM-13b 審查 Q-1 的定案，不受開關管）**：
  - 守門看到還原、而且預設帳號的權杖沒撤銷（沒有帳號資料，開通與否）時，在刪還原標記**之前**存 `/data/mcp/restore-notice.json`
    （`{"version":1,"at":"<UTC 秒>"}`，不含秘密；暫存檔＋fsync＋replace＋目錄 fsync、0600、本程序的 uid；被目錄占用時照 #115 移開；不碰 sentinel）。
    中途斷電時標記還在，下次開機重存。
  - bootstrap 只多一個鍵 `restore_notice`（`{"at"}`），到預設帳號的權杖變了才消失：`token/rotate`、真的撤銷了的 `token/revoke`、開通後的全部撤銷。
    權杖照還原的原樣，不撤銷；其他回應一個位元組都不變。
  - 沒有還原的安裝（每個安裝的平常開機）：開機只多查一個名稱，沒有就不建任何提示物件，bootstrap、其他回應與磁碟都和今天逐位元相同
    （HM-01 的黃金回歸與兩個契約凍結一案都沒改照過，另有本片的測試）。
  - 開關關時沒有加任何管理路由。提示怎麼消失的最小方案：重新產生或撤銷權杖（既有路由）；面板「知道了」只在這個頁面的記憶體裡藏，
    重新整理會再出現。沒有用 localStorage：面板的儲存不變式（N15、DQ-18）由 `build-closure.mjs` 擋，要「這個瀏覽器記住」得先放寬它，
    是另一個決定（第 17 節）。不需要新路由，所以沒有停下來問。
- **開通後的管理路由**（`profile_admin.py`，全部走共用管線；開關關時一條都沒有）：
  - `POST profiles/revoke-all`：拿全 add-on 的帳號鎖、預設帳號的鎖、依 id 拿每個已登錄帳號的鎖，之後才做第二次角色檢查；`restore_lock.revoke_all`
    在工作執行緒跑（8081、8099 與健康檢查照常）；每個帳號 `TokenAccess.committed()`、撤銷了的重起子程式（新的 child token）。沒做完：409
    `operation_outcome_unknown`＋逐帳號 `results`、收據停在結果未知，沒撤銷成功的帳號撤銷前的權杖在 8081 回 503，直到一次全部撤銷做完或重開
    （重開時守門在 listener 前補完）。索引不能用時收壞索引的 ETag（緊急止血）。
  - `GET profiles/restore-record`（上限 1 MiB、照守門寫的形狀逐鍵驗、不含秘密）；`POST profiles/<id>/restore-review`（寫一次 `reviewed_at`）；
    守門撤銷的帳號在核對前 `token/rotate` 回 409 `restore_review_required`（紀錄讀不到時 503，一律擋）。
  - 隔離目錄：清單另帶 `quarantined`（`<id>-<UTC>[-n]`，`parse_quarantine_name`），`POST profiles/quarantine/<name>/delete` 只能刪（照刪除的規則：
    讀得到的先撤銷、抹憑證，再不跟隨連結地刪）。
- **面板**（`app.js`、新模組 `restore.js`）：單帳號與預設帳號的還原提示、休眠卡、核對卡（逐帳號還原時間、名稱、身分欄位、政策摘要、目前狀態；
  按「已核對」才開放重新產生，也可以直接刪除）、隔離目錄只能刪、全域「全部撤銷」兩段確認、匯出帳號清單（不含憑證）。備份帶回的名稱與欄位
  一律當文字插入。開關關、沒有還原時面板逐位元不變（既有 Playwright spec 一案都沒改照過）。
- **還原時每個收據檔都換新**（HM-13b 交本片定）：守門處理的每個收據檔都寫新的，備份時還沒有收據檔的帳號與索引旁也寫（同 PaaS 每份設定
  都換新，`Pc/restore_guard.py:513-516`），備份後才做、隨還原消失的操作 id 回 410。沒有帳號資料時預設帳號的收據照原樣（#116），單帳號
  安裝的行為不變。
- **這一輪是第二段**（第 2 節）：第一段在 2026-11-17 00:4x 前後中斷，留下 3 個 commit 與沒 commit 的契約、決策草稿。這一段核對後補了：
  3 個伺服器測試、4 個案例（休眠帳號重新開通後的關卡、還原後索引不能用、全部撤銷連開始都沒有與沒收尾）、3 個面板測試與修正（提示的時間、
  索引不能用時的核對卡、全部撤銷沒做完的三種說法）、文件（契約、決策、威脅模型、驗收矩陣、列管清單、`update-backup-rollback.md`）。
- 先寫測試：第一段的測試 commit 在舊程式上收集就失敗／17 案紅／面板 7 案紅；這一段的面板 3 案在舊 `app.js` 上紅、新程式上綠；
  伺服器 3 個測試（4 個案例）用 5 個突變確認咬得到（第 6 節）。
- 本機（第 7 節）：pytest 全套（`277c053`）6,142 案、0 skip，6,135 過，只有 7 個要 root 的既有案例失敗（32 分 53 秒）；子集 896 案只剩 5 個要 root 的；
  Playwright 128 案、node 87 案全過；build closure、packaging unittest（`Ran 205`、`OK (skipped=5)`）、`validate.py`、`tool_inventory.py` 都通過；
  雙向控制字元 0 個。CI（root、0 skip）待開 PR。
- 兩個預檢（`--base ebab019`，`277c053`）：秘密預檢 0 命中；帳本預檢 OK（第 10 節）。本筆記 commit 之後再跑一次，結果記在回報（與之後的 PR 說明）。
- **待 HM-03a 確認**（第 13 節）：UC-08 與 sentinel（照 HM-13b）；Ingress 轉不轉清單的 `ETag`（核對、刪除隔離目錄、全部撤銷都要）；守門沒做完時
  Watchdog 會不會自動再起。
- **沒有碰到要使用者定的待定題**。本片自己定的實作細節（契約原本標「暫定，HM-13c」）寫在第 4 節與契約第 9 節 #117、#118。

## 1. 範圍與基準

證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-13c/`（`logs-first/`：第一段的紅；`logs/`：第二段；`tools/`：用到的
腳本，副檔名多加 `.txt`）。log 先掃過像 token 的字串（43 個 URL 安全字元、不是同一個字母重複），0 個；全套的 junit 只留每個模組的摘要（`logs/full-junit-per-module.txt`）。
`SP:`＝本機的 scratchpad。

| 項目 | 值 |
|---|---|
| 切片 | HM-13c｜還原核對與全部撤銷的路由與面板（計畫 §6、§7.4、§8.4、§10.3、§12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm13c-20261116`（一般 clone，不是 worktree） |
| HA 基準 | `ebab019`：HM-13b 的 PR #108 head（`claude-delivery` `f4c7718`＋HM-13b 的 26 個 commit） |
| PaaS | pin `69ac425`；本機唯讀 PaaS repo 的 `origin/main` 是 `7087280`（第 11 節） |
| 開關 | `MULTI_PROFILE_PRODUCTS` 在 repo 裡仍是空集合；測試用 monkeypatch 開 |
| 不改的 | 版號、`addons/`（含各產品 CHANGELOG）、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`features.py` |

## 2. 接續紀錄（第二段，2026-11-17 01:3x 起）

- 第一段（2026-11-16 23:2x～2026-11-17 00:4x）留下 3 個 commit（`9a46c1c` 測試、`922680f` 核心、`d5a4301` 面板）、沒 commit 的
  `contract.md`、`decisions.md` 草稿，以及一個 `/tmp/ha-mp-h4q9Lo`。這一段的任務文字寫「目前沒有本片的 commit」，和 clone 的實況不同；
  沒有重來（重來會丟掉已做好、可驗證的工作），改成先核對再接著做。
- 先確認沒有程序還在用這個 clone 與那個暫存目錄，再用完整路徑刪掉 `/tmp/ha-mp-h4q9Lo`（裡面的 pytest 目錄有本片才有的測試名稱，是第一段的）。
  其他 `/tmp/ha-mp-*` 屬別的片，沒碰。
- 讀過三個 commit 的 diff、草稿與第一段的先紅後綠 log（證據目錄的 `logs-first/`），逐項對照任務與計畫：
  - 面板測試：d5a4301 上 Playwright 全套 126 案全過、node 87 案全過、build 與 build closure 通過。
  - 找到三個面板問題，先寫測試看到紅再改（第 6 節）：提示的時間對 HM-13a 留下的舊標記不成立；索引不能用時核對卡的按鈕按了沒反應、清單
    讀不到的帳號被寫成「已刪除」；全部撤銷沒做完時沒有結果或沒有失敗帳號的兩種情況說錯。
  - 補了 3 個伺服器測試（4 個案例）：休眠帳號重新開通後的關卡（I13 寫的「未核對前不能重發」沒有測試）、還原後索引不能用、全部撤銷連開始都沒有
    與沒收尾（參數兩種）。`dae41e6` 的 commit 訊息寫成「4 個測試（5 個案例）」，數錯了；照寫的當時，不改寫歷史。
  - 補完文件（第 3 節）。

## 3. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hc/restore_lock.py` | 還原提示：`_save_notice`（刪標記之前）、`read_notice`、`Notice`（`view`、`clear`）；撤銷預設帳號的還原與全部撤銷補完時刪舊提示；`check_record`、`review`；還原時每個收據檔都換新（`renew_missing`）；`_write_json` 給紀錄與提示共用 |
| `Hc/gateway.py` | `make_apps(restore_notice=, review_required=)`：bootstrap 的 `restore_notice`；`token/rotate`、撤銷了的 `token/revoke` 清提示；`token/rotate` 的 409 `restore_review_required`（If-Match 與 Idempotency-Key 之後、什麼都不寫） |
| `Hc/run_product.py`、`apps/n8n/run.py` | 守門之後讀提示，交給預設帳號（沒有就不建） |
| `Hc/profile_admin.py` | 四條新路由、清單的 `quarantined`、bootstrap 的 `restore_review`／`restore_review_required`、核對關卡（`review_required`） |
| `Hc/profile_router.py` | `GLOBAL_ROUTES` 加四條（每一段都比對；`{id}`、`{name}` 在第 ⑤ 步驗格式）；8081 對 `revoke_fence` 裡的權杖回 503 |
| `Hc/profile_runtime.py` | 傳 `restore_notice`、`review_required` 給 `make_apps`；`ProfileManager` 持有提示與 `revoke_fence` |
| `Hc/profiles.py` | `RESTORE_NOTICE_NAME`（也是守門會移開的名稱）、`Layout.restore_notice`、隔離目錄在 API 上的名稱與刪除 |
| `Hc/operations.py` | 三種新收據（`profile.revoke_all`、`profile.restore_review`、`profile.quarantine_delete`）與 subject；`archive_for_restore(renew_missing=)` |
| `packaging/container_probe.py` | 還原階段多檢查提示檔（0600、10001；開通的候選映像也要有） |
| `Hui/restore.js`（新） | 讀 bootstrap 的三種通知、還原紀錄、清單的隔離目錄、全部撤銷的結果並先驗格式；匯出（允許清單） |
| `Hui/app.js`、`Hui/api.js`、`Hui/operation-identity.js` | 提示卡、休眠卡、核對卡、隔離目錄、全部撤銷、匯出；新的帳號操作與它們的收據識別；HM-11 審查觀察 2、4 |
| `packages/mcp-admin-ui/fixtures/server.mjs`（LOCAL MOCK） | 上面每一種情況；`profile-api-cases.json` 多兩個情境，由真後端比對 |
| 測試 | 新：`tests/test_restore_review.py`、`Hui` 的 `tests/restore.test.mjs`、`tests/browser/restore-review.spec.mjs`；改：第 5 節 |
| 文件 | `contract.md`、`decisions.md`、`threat-model.md`、`acceptance-matrix.md`、`ledger-tracking.md`、`docs/operations/update-backup-rollback.md`、本筆記 |
| 帳本 | `runtime-patches.json`：12 列重算並補說明、新增 `restore.js`（65 列）；沒動 `apps/runtime/*.py`、`apps/*/launch.py`，tool-surface 不用重產 |

沒改：版號、`addons/`、各產品 CHANGELOG、`upgrade-notes.yaml`、`features.py`（開關仍空）、`config.py`（HM-18 的 S-4 只寫建議，第 15 節）、
`profiles.js`（新卡片在 `app.js`、`restore.js`）、`tests/conftest.py`、HM-01 的凍結測試（第 5 節）。

## 4. 行為

### 4.1 單帳號還原後的提示（不受開關管；契約 §1.2、§8、#117）

| 情況 | 結果 |
|---|---|
| 沒開通、沒有帳號資料，有還原 | WARNING 一行（同 HM-13b）→ 存提示 → 刪標記。權杖、收據、其他每一項照還原的原樣 |
| 同上，提示存不下（磁碟滿、唯讀） | 照常啟動、標記留著、多一行 `MARKER_LEFT`（原因 `the panel notice could not be saved`），下次開機再存 |
| 開通但沒有帳號資料，有還原 | 同上，另寫還原紀錄（預設帳號那列 `token: kept`、不用核對）；存不下時和守門其他寫入一樣停下 |
| 有帳號資料的還原、開機補完全部撤銷 | 撤銷預設帳號，順手刪掉舊提示（備份帶回的或之前留下的：已不成立） |
| 之後每次開機 | 讀到提示就給預設帳號的 runtime；bootstrap 帶 `restore_notice` |
| 預設帳號 `token/rotate`、撤銷了的 `token/revoke`、全部撤銷 | 刪提示檔（fsync 目錄）；刪不掉記一行，重開後會再顯示到下一次權杖變更 |
| 沒有還原 | 開機只多查一個名稱（`read_notice`；連 ctime 都不變），不建 `Notice`；每個回應與磁碟逐位元同今天 |

為什麼另開一個檔、不重用 `restore-record.json`：紀錄的格式是給開通後的核對卡（每列身分欄位與政策），單帳號只需要時間；HM-13b 定了單帳號
還原不寫紀錄（容器探針也這樣驗），重用會讓單帳號安裝多出一份含政策的檔。提示檔只有時間。

提示的時間是守門看到還原的時間。HM-13a 先發、HM-13b 還沒發的映像留下的舊標記，要到含守門的版本第一次啟動才提示，所以面板寫「偵測到還原的
時間（add-on 啟動時發現的時間）」，不寫「還原時間」（HM-13a 交下：通知文字要涵蓋這種情況）。

### 4.2 還原時的收據（契約 §3.5、#67、#116）

- `operations.archive_for_restore(renew_missing=True)`：收據檔與 `.restored` 都沒有時也寫一份新收據檔（`restored_before_ms`＝還原當下），
  備份後才做、隨還原消失的操作 id 回 410，不會被當成新操作（PaaS 的 `_write_journal` 對每份設定都寫，`Pc/restore_guard.py:513-516`）。
- 守門處理的每個收據檔：開通或有帳號資料時，預設帳號（被撤銷時）、每個帳號目錄、索引旁。
- 沒有帳號資料時預設帳號的收據照原樣、沒有也不寫（#116，DQ-03 (b)）：單帳號安裝的行為不變，所以不用停下回報。開通但沒有帳號資料時索引旁
  會多一份新收據檔（開通後才有的功能；它擋的正是備份後才做的帳號操作被重送）。

### 4.3 核對與關卡（契約 §3.1、§3.6、§4.1、#58）

- 紀錄每列 `token` 是 `revoked` 或 `already_revoked`、`reviewed_at` 是 `null`：這個帳號的 `token/rotate` 回 409 `restore_review_required`
  （在 If-Match、Idempotency-Key 之後，什麼都不寫、不留收據）。`kept`（DQ-03 (b) 沒撤銷的預設帳號）不用核對。休眠撤銷的帳號重新開通後一樣。
- 紀錄讀不到或形狀不符（`check_record` 逐鍵驗）：rotate 回 503，一律擋；預設 bootstrap 的 `restore_review` 三個值都是 `null`。
- 核對：拿全 add-on 的帳號鎖、索引的 If-Match、Idempotency-Key、收據；帳號要在紀錄裡、而且還在索引（或是預設帳號），否則 404；索引不能用時
  503 `profile_index_corrupt`（先隔離索引）。只寫一次 `reviewed_at`，紀錄其他位元組不變。
- 紀錄的讀取以 lstat 簽章快取（換檔就重讀）。

### 4.4 全部撤銷（契約 §1.3、§3.1、§3.2、§4.1、§4.2、#82）

| 情況 | 回應 | 8081 | 標記 |
|---|---|---|---|
| 全部成功 | 200 `{"revoked":"all","results":[…],"operation"}` | 舊權杖 404／401 | 刪 |
| 第 k 個帳號失敗 | 409 `operation_outcome_unknown`＋逐帳號 `results` | 失敗帳號撤銷前的權杖 503，其他 404／401 | 留（重開補完） |
| 每個都撤銷、沒收尾（驗證不過、`profiles/` 列不出來、標記刪不掉） | 409＋`results`（沒有失敗） | 沒有 503 | 留（重開再做一次） |
| 標記存不下（什麼都沒撤銷） | 409＋`results: []` | 每個已登錄帳號的權杖 503（這次執行期間） | 沒有：重開後權杖恢復有效 |

- 503 名單（`ProfileManager.revoke_fence`）存權杖的 sha256，下一次做完的全部撤銷清空；只在記憶體。
- 收據停在未完成：同一個 key 再送 409（不會再做一次），要重試用新的 key（面板：先「已核對帳號清單」再按一次）。
- 每個帳號 `committed()` 之後才重起撤銷了的子程式，都在鎖裡；重起失敗記一行（新的 child token 等下一次重起）。
- 撤銷了預設帳號就清還原提示；撤銷後刷新孤兒的回覆遮罩。

### 4.5 隔離目錄（契約 §1.1、§3.1、#118）

清單有隔離目錄時另帶 `"quarantined":[{"name":"<id>-<UTC>[-n]","id"}]`（沒有就不帶這個鍵）。刪除：全 add-on 帳號鎖、索引 If-Match、Idempotency-Key、
收據；讀得到 state 的先撤銷權杖、抹後端憑證（DQ-14），再從 `profiles/` 不跟隨連結地刪（同刪帳號）；刪不乾淨記一行、清單照樣列出可再刪。
隔離目錄不能選擇、不路由、不能改名或重發。

### 4.6 面板（計畫 §6）

- 單帳號（與開通後的預設帳號）：提示卡在每一頁上方，文字照計畫 §6；「前往重新產生權杖」「知道了」（只藏到重新整理）。
- 沒開通、有帳號資料：休眠卡（數字、權杖已撤銷），沒有任何管理動作。
- 開通後的預設帳號頁：核對卡（`restore_review` 出現才畫）。待核對的帳號在「連線與權杖」停用「重新產生」並說明。帳號清單沒有版本（索引不能用、
  清單讀不到）時核對與刪除停用並說明；清單沒有的帳號寫「狀態不明」或「孤兒」，不寫「已刪除」。
- 「診斷與維護」：隔離目錄（只能刪，兩段確認）、全部撤銷（兩段確認；沒做完時依結果說三種話：哪些帳號失敗、每個都撤銷但沒收尾、連開始都沒有）、
  匯出帳號清單（允許清單：清單列的 id、名稱、port，後端的非秘密欄位，政策；沒有任何權杖、CSRF 或憑證）。
- 收據識別：profiles 範圍多三種紀錄（全部撤銷、核對、刪除隔離目錄），丟失的回應可以原識別碼重送。

## 5. 為了新行為改的既有測試（逐案理由；測試裡也有）

| 檔 | 改了什麼、為什麼 |
|---|---|
| `tests/test_restore_lock.py`（HM-13b） | 單帳號還原那案改名 `…_removes_the_marker_and_only_adds_the_notice`：原本斷言「什麼都不多」，使用者定案後多提示檔（9 個產品）；有帳號資料的還原那案：B 沒有收據也有新收據檔（`renew_missing`）；守門會移開的名稱多提示檔 |
| `tests/test_admin_pipeline_matrix.py`（HM-10） | 否定矩陣替新路由的 `{name}` 填一個格式正確的隔離目錄名 |
| `tests/test_request_budget_gateway.py`（HM-31） | `make_apps` 參數順序的釘選多 `restore_notice`、`review_required`（同 HM-13b 改 `dormant_profiles` 的做法） |
| `tests/test_output_schemas.py` | `apps/n8n/run.py` 的位元組釘選換成現在的（只多讀還原提示；工具、schema、handler 沒變） |
| `tests/test_restore_detection.py`、`packaging/test_container_probe.py`（HM-13a） | 容器探針的還原階段多檢查提示檔 |
| `tests/test_panel_profile_api_shapes.py`（HM-11） | 新情境的設定（還原、預設帳號的政策、隔離）、`learn_quarantine`；no-index-file 情境先建 sentinel（不是還原，否則索引旁的收據換新、案例的 key 變成還原前） |
| `Hui` 的 `tests/browser/profile-api-parity.spec.mjs`、`tests/profile-api-cases.json`（HM-11） | 多兩個情境（`restore`、`switched-off-restored`）；parity spec 把新情境的設定（還原、隔離、提示）對應到 mock 的設定、認得 `learn_quarantine`；規則的 bootstrap 投影多三個鍵（`restore_notice`、`restore_review`、`restore_review_required`）、字面鍵多 `result`、`revoked`（沒有這些鍵的回應投影不變）。既有情境的案例一個都沒改 |

**HM-01 的凍結測試一案都沒改**：黃金回歸（`tests/test_single_profile_golden.py`）、兩個契約凍結（`tests/test_admin_contract_freeze.py`、
`tests/test_mcp_contract_freeze.py`、`tests/contract/profiles_v1_cases.json`）都沒有「備份還原」的案例（裡面的 restore 是 owner-defaults 的還原，
另一件事），所以沒有要改的；照過就是「沒還原逐位元不變」的證明。還原的案例在 `tests/test_restore_review.py`（同一份資料還原與否，bootstrap 只差
`restore_notice`，8 個產品）與 `tests/test_restore_lock.py`（上表）。既有的 Playwright spec 一案都沒改。

## 6. 先紅後綠與突變

### 6.1 第一段（`9a46c1c` 只有測試，程式是 `ebab019` 的；log 在證據目錄的 `logs-first/`）

| 檢查 | 結果 |
|---|---|
| `tests/test_restore_review.py` | 收集就失敗（`profiles.RESTORE_NOTICE_NAME` 不存在） |
| 改到的既有測試與真後端形狀比對（448 案） | 17 案紅：`test_restore_lock` 12、`test_request_budget_gateway` 1、`test_output_schemas` 1、`test_restore_detection` 1、`test_panel_profile_api_shapes` 2（`restore`、`switched-off-restored`） |
| 面板 node | `tests/restore.test.mjs` 紅（`restore.js` 不存在），其他 81 案過 |
| 面板 Playwright（`restore-review`、`profile-api-parity`） | `restore-review` 7 案全紅；parity 12 案過（mock 跟測試一起改） |

`922680f`、`d5a4301` 之後全綠（第 7 節）。

### 6.2 第二段

- 面板：新測試與 mock 放在 `d5a4301` 的匯出樹上（repo 外；`app.js` 是舊的），`restore-review.spec.mjs` 9 案 3 紅：提示的時間、索引不能用時的
  核對卡、全部撤銷沒做完的說法（`logs/red2-ui-browser-oldapp.txt`）。改 `app.js` 後 21 案（加 parity）全綠。
- 伺服器：3 個新測試（4 個案例）測的是第一段已寫好的行為，所以直接綠；改用突變確認它們咬得到（`tools/mutate.py.txt`，在 repo 外的副本上一次
  改一處、跑相關測試、改回；`logs/mutations.txt`）：基準 4 案全過；5 個突變全被擋：

  | 突變 | 擋下的案例 |
  |---|---|
  | M1 關卡只看還原、不看休眠（`review_required` 多一個 `record['restore'] is not None`） | 休眠帳號重新開通後的關卡 |
  | M2 索引不能用時也收核對（`_usable_view` 換成不檢查） | 還原後索引不能用 |
  | M3 索引不能用時待核對數也算額外帳號 | 還原後索引不能用 |
  | M4 全部撤銷連開始都沒有時不擋舊權杖（`done is None` 也解除 503 名單） | 標記存不下 |
  | M5 標記刪不掉也算做完 | 沒收尾 |

  第一次跑突變時副本沒有連各產品的 `.venv`，基準就紅（正式 runtime 起不來）；照 HM-13b 的匯出樹連好後重跑，結果如上。

## 7. 本機檢查（一般使用者 uid 1000；TMPDIR `/tmp/ha-mp-5YExOX`，跑完用完整路徑刪掉；pytest 都排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| 面板 node（`npm test`） | 87 案全過 |
| `npm run build`＋`build-closure.mjs` | PASS（`dist/` 是忽略的檔） |
| Playwright 全套（`d5a4301`，第一段的最終程式） | 126 案全過（3.9 分） |
| Playwright 全套（最終：面板檔＝`111e76d`） | 128 案全過（4.0 分；`d5a4301` 的 126 案＋第二段的 2 案） |
| pytest 子集（23 檔：本片與 HM-13b 的新檔、HM-13a、HM-10 三檔、HM-11 形狀比對、HM-31 的參數順序、`test_output_schemas`、HM-01 守門 7 檔、零改寫、帳本、路由、監看取消、執行套件；`277c053`，正式 conftest，排在共用鎖後面） | 896 案：891 過，5 個失敗都是要 root 的 `test_restore_detection.py::test_root_*`；94.7 秒。`tests/test_restore_review.py` 50 案全過（第一段 46 案＋第二段 4 案） |
| pytest 全套（`tests`，CI 的指令加 `-rfEs --durations=30`、junit；`277c053`，開始與結束時 HEAD 相同，工作樹只多本筆記的草稿；02:22～02:55） | 6,142 案、0 skip：6,135 過、7 個失敗都是要 root 的既有案例（`test_restore_detection` 5、`test_profile_store` 1、`test_owned_executable` 1，都停在要求 root 的那一行）；1,973.4 秒（32 分 53 秒）；2 個 warnings 是既有的 websockets 棄用警告 |
| packaging unittest（照 CI 的離線暫存 venv，不用 PYTHONPATH；`d5a4301` 之後 `packaging/` 沒再改） | `Ran 205`、`OK (skipped=5)` |
| `packaging/validate.py`（ci-venv） | PASS |
| `scripts/tool_inventory.py` | exit 0 |
| 雙向控制字元（U+202A～202E、U+2066～2069；另查 U+200E、U+200F、U+061C） | `ebab019..277c053` 6 個 commit 的訊息與每個改到的檔的全文、加上工作樹的本筆記：0 個（`tools/bidi_scan.py.txt`） |

## 8. 只在 CI 跑的測試與 CI 時間

- 要 root 的既有 7 案本機一定失敗（`test_restore_detection` 5、`test_profile_store` 1、`test_owned_executable` 1）；其中
  `test_restore_detection.py::test_root_*` 的容器探針還原階段這次多檢查提示檔（root 版本只在 CI 跑）。
- 本片沒有新的 root 案例、沒有起真子程式的新案例：新測試都是 in-process（守門在暫存目錄、正式 runtime 用 `NoProcessSupervisor`＋MockTransport）。
- 新測試的本機時間（junit）：`tests/test_restore_review.py` 50 案 3.6 秒（第二段的 4 案 0.5 秒）；`test_panel_profile_api_shapes` 多的兩個情境約 2 秒
  （`restore` 情境等 1.1 秒讓操作識別碼晚於還原）；Playwright `restore-review.spec.mjs` 9 案約 25 秒；node 不到 1 秒。
- CI 推估：`checks` 多約 40 秒到 1 分鐘（HM-13b 的 PR 為基準）；開 PR 後照實補。
- 容器探針的還原階段只在 HM-19a 前的 builder 乾跑與各產品發版的容器驗收時真的跑。

## 9. `checks` 秒數

開 PR 後補。

## 10. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base ebab019 --head HEAD --full` | `277c053`：OK，0 命中（gitleaks 8.28.0；`ebab019..277c053` 6 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base ebab019` | `277c053`：OK：`runtime-patches.json` 178 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的檔裡 13 個列管檔由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔 |

## 11. PaaS 變動（本機唯讀 PaaS repo，`git log/diff 69ac425..7087280`；沒有 fetch、沒有 checkout）

`69ac425..7087280` 合了 10 個 PR：

| PR | 內容 | 和本片 |
|---|---|---|
| #150 | #148 之後的文件、測試與註解小修 | 無關 |
| #149 | 紀錄遮罩：query 憑證 | 無關（HM-02 已對齊） |
| #151 | 移除 VK 產品（還原手冊刪 VK 那幾列） | 無關：HA 沒有 VK；手冊步驟沒變 |
| #152、#154 | Nextcloud 存檔 SSRF、換使用者或網址撤銷舊網址（還原手冊步驟 11 改一句） | 無關（HM-22）；本片不碰後端身分 |
| #153 | EMQX 小修 | 無關（HM-23） |
| #155 | 閘道請求內容位元組預算 | 無關（HM-31 已對齊） |
| #135、#139、#138 | EMQX、LiteLLM 不保留閒置連線；Hermes 建立停用的 cron 時送 `paused` 與 `enabled` | **無關**：只改 `apps/emqx`、`apps/litellm`、`apps/hermes` 的產品後端（9 個檔），不碰多帳號、還原或撤銷 |

- `restore_guard.py`、`restore_inplace.py` 在這段範圍沒變。本片對齊的地方：每份設定都換新收據檔（`Pc/restore_guard.py:513-516`）、手冊步驟 1
  （事前盤點，不含憑證）＝匯出帳號清單、步驟 9（核對）＋步驟 10（核對後才發 token）＝核對卡與 `restore_review_required`。
- PaaS 沒有全部撤銷的 API（`git grep -n -i "revoke_all\|revoke-all" 7087280 -- '*.py'` 沒有結果；契約 #82）：HA 的全部撤銷是加嚴（建議回補）。

## 12. 本片用到的決策

| 決策 | 怎麼用 |
|---|---|
| DQ-03 (b) A2 | 只有磁碟上有帳號資料的還原才撤銷預設帳號；沒有帳號資料時權杖與收據照還原的原樣，面板與 log 提示「權杖已回到備份當時的值」 |
| 使用者 2026-11-16 21:xx（HM-13b 審查 Q-1） | 照 DQ-03 原文補面板提示；只核准 bootstrap 多一個欄位等代價；開關關時不加管理路由；提示怎麼消失由本片提最小方案（23:3x 主對話更正：沒有「管理員可以關掉」）。記在 `decisions.md` 第 1.1 節 |
| DQ-13 | 守門與新路由不碰 endpoint；還原紀錄不記 endpoint |
| DQ-14 | 隔離目錄與孤兒不自動刪；刪除先撤銷、抹憑證再刪；兩段確認在面板 |
| DQ-12 | 索引不能用時：全部撤銷收壞索引的 ETag、紀錄照讀；核對與刪除隔離目錄要先隔離索引 |
| DQ-18、N15 | 面板不用瀏覽器儲存：「知道了」只放記憶體 |
| DQ-37 | 同 uid 不是邊界：核對關卡靠守門寫的紀錄（威脅模型第 3 節） |
| DQ-39 (a) | HM-03a 證實偵測不到某種還原就不首發（提示與關卡都靠偵測） |
| DQ-40 (a) | ③ 全部撤銷要 If-Match＋Idempotency-Key（核對、刪除隔離目錄也是）；① 帳號範圍的 rotate 照舊要剛好一個 `X-MCP-Profile`，被關卡拒絕的回應不帶回聲（契約 §3.4） |

沒有碰到待定題（DQ-04、22～24、26、27、35、41、42、44～46 都沒用到）。

## 13. 待 HM-03a 確認

| 項目 | 本片的假設 | 不成立時 |
|---|---|---|
| UC-08：full、partial、加密備份各還原一次，訊號 1 或 2 觸發（照 HM-13b 第 11 節） | 觸發 | 單帳號提示與開通後的關卡都不會出現；照 DQ-39 (a) |
| sentinel 的 `st_ino`、`st_ctime_ns` 平常不變（照 HM-13b） | 不變 | 開通後每次開機都當成還原、撤銷全部 token、每次都要核對 |
| Ingress 轉清單回應的 `ETag` 標頭（HM-10 審查 S-4） | 轉 | 面板拿不到版本：核對、刪除隔離目錄、全部撤銷的按鈕停用並說明（全部撤銷在索引壞時用 bootstrap 的 `profile_index_etag`）；要改成從本體帶版本 |
| 守門沒做完時 Supervisor 會不會用 Watchdog 自動再起（照 HM-13b） | 不假設 | 全部撤銷沒做完時要使用者重新啟動才會補完；HM-18 的 DOCS 寫 |
| HA 備份包含 `restore-notice.json`（在 `/data/mcp`） | 包含 | 不影響安全：還原時守門重寫或刪掉它 |

## 14. 前面各片交給 HM-13c 的待辦

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-13b 第 13 節／第 18.12 節（審查 Q-1） | 使用者定案：單帳號還原後的面板提示，接在守門上另留一筆提示紀錄 | 做了（第 4.1 節）：另開 `restore-notice.json`（理由同節）；`decisions.md` 第 1.1 節、契約 §1.2、#117 |
| HM-13b 第 13 節 | 備份時沒有收據檔的帳號：要不要對範圍 S 的每個帳號都寫新收據檔 | 做了：照 PaaS 每份設定都換新（第 4.2 節）；#116 的預設帳號除外，單帳號安裝不變。契約 §3.5、#67 |
| HM-13b 第 13 節（審查 S-5） | 全部撤銷要拿 `ProfileAdmin.lock`、在執行緒裡跑、results 列出每個 store | 做了（第 4.4 節）；另拿預設帳號的鎖；`test_revoke_all_runs_in_a_worker_thread_and_8081_answers_meanwhile`、`test_the_new_routes_check_the_role_after_every_wait` |
| 同上 | `POST profiles/revoke-all`：依 id 拿鎖、`committed()`、重起子程式、409＋results、8081 的 503、收據結果未知 | 做了；store 中毒（寫入失敗）的帳號照既有規則 503 到重啟、重啟時守門補完 |
| 同上 | `restore-record`（1 MiB）、核對、`reviewed_at`、rotate 的 409、bootstrap 的通知欄位（含 HM-13a 過渡期的舊標記） | 做了：`restore_review`、`restore_review_required`、`restore_notice`；開通後第一次開機遇到舊標記：沒有帳號資料時寫紀錄（`kept`）＋提示，面板寫「偵測到還原的時間」 |
| 同上 | 刪除隔離目錄的路由，名稱 `<id>-<UTC>[-n]`（`parse_quarantine_name`） | 做了（第 4.5 節） |
| 同上 | `update-backup-rollback.md`：開通後的還原行為、涵蓋範圍、回退後按全部撤銷 | 做了：新的一節，另寫單帳號還原後的提示、核對卡、全部撤銷沒做完的三種情況；還原標記那列補提示檔 |
| HM-13b 第 13 節（審查 S-4，HM-18／HM-13c） | 暫時性錯誤讓好的帳號被永久隔離（要動 `config.py`） | 本片不改程式；建議寫在第 15 節交 HM-18；`threat-model.md` 第 3 節那條改寫交接 |
| HM-10 第 13.2 節 | 四條全域路由加進 `GLOBAL_ROUTES`（否定矩陣自動涵蓋）、rotate 的 409、索引壞時能不能用、每條新路由每一種等待之後的第二次角色檢查 | 做了：矩陣替 `{name}` 填值；索引壞時全部撤銷與紀錄能用、核對與刪隔離目錄 503（契約 §4.1）；`test_the_new_routes_check_the_role_after_every_wait`（全部撤銷 4 種等待、核對與刪除各 1 種） |
| HM-10 第 13.1 節（HM-00 第 10 節） | 還原紀錄欄位、全部撤銷失敗的狀態碼、索引壞時全部撤銷與紀錄能不能用 | 欄位照 HM-13b；狀態碼 409 `operation_outcome_unknown`＋`results`；能用（契約 §3.1、§4.1） |
| HM-00 第 10 節（審查 SF-09） | 刪除隔離目錄的路由與寫入保護（暫定，HM-13c 定案） | 定案：`POST profiles/quarantine/<name>/delete`、索引 If-Match＋Idempotency-Key、全域收據（契約 §1.1、§3.1、§3.5） |
| HM-11 第 11 節第 17、18 點、第 13 節 | 休眠的 `dormant_profiles` 面板顯示；核對卡、全部撤銷、隔離目錄刪除、`restore_review_required` 文案；`profiles.js` 照帳本規則 | 做了；新卡片放在新模組 `restore.js` 與 `app.js`，`profiles.js` 沒改（`ledger-tracking.md` 註明） |
| HM-11 審查觀察 2 | 隔離遇沒有代碼的 503 時的文字 | 改了：「管理服務暫時無法處理（例如另一個帳號的操作正在進行，或帳號資料夾暫時讀不到）」 |
| HM-11 審查觀察 4 | 清單沒帶 ETag 時讀不到的帳號的刪除鈕沒反應 | 改了：換成說明；核對卡的按鈕也照這個原則（第二段） |
| HM-05 第 3.1 節 | 全部撤銷用執行套件的 `TokenAccess` 與 `mutation_lock` | 做了 |
| HM-06 第 12.3 節（審查 S-07） | 重產 child token 之後要重啟子程式 | 做了：全部撤銷撤銷了的帳號都重起（開機補完時子程式還沒起，不用） |
| HM-13a 第 11 節 | 過渡期留下的舊標記，HM-13b、HM-13c 的通知文字要涵蓋 | 做了：提示寫「偵測到還原的時間（add-on 啟動時發現的時間）」；`update-backup-rollback.md` 寫明舊標記要到新版第一次啟動才提示 |

## 15. 交給後面的片

- **HM-19a（各產品 CHANGELOG 的一行，使用者核准的代價之一）**：任何產品下一版都會帶出去（不受開關管）。建議原文（CHANGELOG 是英文）：

  > - After a backup restore that keeps the MCP token (no multi-profile data on disk: nothing is revoked, as before), the admin panel now also
  >   shows "偵測到還原；權杖已回到備份當時的值。若備份後曾輪替或撤銷，請立即重新產生" until the token is rotated or revoked. Meanwhile the
  >   bootstrap carries one more field, `restore_notice` (`{"at"}`), and `/data/mcp` holds `restore-notice.json` (its time only, no secret).
  >   An installation that was never restored answers byte for byte as before; no management route is added.

  另外 `upgrade-notes.yaml` 與計畫 §7.2 的清單要不要列，由發版片照升版比對的報告定（不是破壞性變更：只多一個欄位）。
- **HM-18**（審查 S-4 的建議，本片不改程式）：讓 `Store` 打不開時帶出原因（例如 `ConfigError` 的子類別或屬性：缺檔、擁有者不符、格式錯是「確定讀不到」；
  `EMFILE`、`ENFILE`、`ENOMEM`、`EIO`、`EAGAIN` 是「暫時」），守門遇到暫時的就這次開機停下、標記留著、下次重做，不改名隔離；確定讀不到的照舊隔離。
  動到所有產品共用的 `config.py`，要和 HM-13b 的守門測試（64 個改磁碟呼叫的中途停止）一起改。DOCS 另寫：還原提示、核對卡、全部撤銷沒做完的三種
  情況、隔離目錄只能刪、匯出帳號清單；計畫 §8.10 事故處理第 1 步。
- **HM-16**：容器探針的還原階段現在也檢查 `restore-notice.json`（沒開通：0600、10001；開通的候選映像：和 sentinel、record、還原紀錄一起）。
  HM-13b 交的 stderr 兩行（`re-owned N`、`KEPT_NOTICE`／`REVOKED_NOTICE`）照舊交 HM-16。
- **主對話**（計畫在 repo 外）：計畫 §3.3 的「不受開關管」表與 §7.1「新檔：一個都不產生」那一列，要加 HM-13c 的例外（還原後多 `restore-notice.json`、
  bootstrap 多 `restore_notice`，到權杖變了為止）；契約第 8 節已寫。
- **HM-03a**：第 13 節。
- **HM-25**：n8n 開通時，`apps/n8n/run.py` 已讀提示並交給 `make_apps`；接 `ProfileManager` 時把提示交給 manager（同 `run_product`）。
- **HM-29**：回補 PaaS 的題目照舊（#82 全部撤銷）；#117 是 HA 專屬（PaaS 還原一律撤銷）。
- **合併順序**：本片疊在 HM-13b 上。HM-12、HM-30、HM-16 若先合併並用掉契約第 9 節 #117 之後的列號，本片 rebase 時接在當時最後一列後面重排
  （本片的列：#117、#118）。帳本與 `gateway.py`、`profile_runtime.py`、`profile_admin.py` 照「後合者重算」。

## 16. 驗收條件（計畫 §12.3 HM-13c）

| 條件 | 狀態 |
|---|---|
| 全綠 | 本機：pytest 全套只剩 7 個要 root 的既有案例、0 skip；Playwright 128、node 87、packaging 205 全過。CI（root、0 skip）待開 PR |
| 核對前不能重發 | 通過：還原（預設帳號與額外帳號）與重新開通後的休眠帳號，rotate 409 `restore_review_required`、什麼都不寫；紀錄讀不到 503；核對後 200、8081 服務新權杖 |
| 全部撤銷第 k 個失敗時的回應與 8081 行為 | 通過：k＝預設帳號、B、C 各一案：409＋逐帳號 `results`、收據結果未知、標記留著；失敗帳號撤銷前的權杖在 8081 兩種接法都 503，其他 401／404；做完的全部撤銷解除。另有連開始都沒有、沒收尾兩案 |
| 單帳號還原提示照使用者定案 | 通過：9 個產品存提示、8 個產品的正式 runtime bootstrap 只多 `restore_notice`、權杖兩種接法照用；輪替或撤銷後消失；沒還原的安裝什麼都不多（連 ctime）；開關關時新路由都是 404；面板「知道了」不用瀏覽器儲存 |
| 不受開關管的例外寫進契約、凍結測試逐案理由、CHANGELOG 一行 | 契約 §1.2、§8、#117；HM-01 凍結沒有要改的案例（第 5 節）；CHANGELOG 原文交 HM-19a（第 15 節） |
| 同 PR 更新帳本；契約第 9 節接在 #116 後面、變更紀錄 | 通過：帳本 12 列重算、新增 `restore.js`；#117、#118；第 10 節一列 |
| 測試資料規則 | 通過：token 都在執行時產生或用 `T`／`M`×43，憑證 `DUMMY-…`、網址 `.invalid` |
| 獨立安全審查 | **還沒做**（本片只 commit；審查由主對話另開） |

## 17. 碰到而沒有自己定的事

- 「知道了」要不要在這個瀏覽器記住：要放寬面板的儲存不變式（N15、DQ-18；`build-closure.mjs` 擋 `localStorage`），本片沒做。現在的最小方案
  （重新產生或撤銷權杖、頁面記憶體裡隱藏）不需要新路由，所以沒停下來問；使用者覺得提示太常出現時再定。
- 索引不能用時，核對預設帳號也要先隔離索引（核對要能用的索引 ETag）。這是本片照「建立、刪除同規則」定的實作細節，不是決策題；若要讓預設帳號
  在索引壞時也能核對，可以改成收壞索引的 ETag（同全部撤銷），交審查時一併看。
