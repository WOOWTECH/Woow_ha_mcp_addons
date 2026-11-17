# HA 多帳號 HM-13c provenance：還原核對與全部撤銷的路由與面板，單帳號還原後的面板提示（2026-11-16～17）

## 結論

- **合併與 S-3 這一輪的獨立審查：通過（必修 0、建議 2，沒有要使用者決定的題；第 20 節）。** S-1 改還原手冊與 `profile_runtime.py` 的說明
  （`f7d2f10`）；S-2 把審查實驗 X1～X3 改寫成 4 個正式測試，選做的 U03 也補一個面板測試（`67a326e`）；在拋棄式複本套突變 M03、M08、M09、M13、
  U03 都會紅。
- **和 HM-13b（已合進 `claude-delivery` `165dbaf`）合併，補審查 S-3（2026-11-17；第 19 節）。** HM-13b 的 PR #108 把 `claude-delivery`
  （HM-12 後端 #110、HM-30 #111、HM-32 #113、HM-12 面板 #114）合進去之後（`fc70404`），本片用 merge commit 把它合進來（`0f3d064`），
  不 rebase、不 force push。衝突在 15 個檔：程式、面板、測試與文件 34 塊，帳本 7 塊照 JSON 重組。面板 `app.js` 只有 import 衝突，`api.js`
  三塊照語意合：還原提示卡、核對卡、全部撤銷、隔離目錄，和 HM-12 換 token 的提示、重新讀取都在。契約第 9 節本片的兩列改成 #122、#123
  （`849d9ba`）。
  - 審查 S-3（主對話 2026-11-17 定）：開通後 HM-12 的換身分換 token 也過還原核對的關卡，帳號還在等核對時回 409 `restore_review_required`，
    子程式不停、什麼都不寫（`0cf5520`）；面板沿用待核對的文字，再補一句為什麼存檔也要等（`e2d28b5`）；契約 §1.2、§3.1、§4.1、威脅模型、
    驗收矩陣、還原手冊（`ba3b63d`）。先寫測試（`3c3f1b4`）：伺服器 4 案紅、3 案照今天綠，面板 1 案紅，改完全綠。
  - 合併後的語意：HM-12 換身分換掉還原保留的預設帳號權杖時，還原提示一起消失（同 `token/rotate`；伺服器 `0cf5520`，LOCAL MOCK 
    `e74d4c0`，Playwright 先紅後綠 `14e435f`）。
  - 08:28 主線又合了 HM-33（PR #115，`f239157`）：HM-13b 再合一次並 push（`369d80b`），本片再把它合進來（`fedaad5`，衝突只在契約與
    `decisions.md` 的表尾；第 19.12 節）。
  - 本機：pytest 全套（`ba3b63d`：合併與 S-3 之後）6,411 案、0 skip，6,404 過，只有 7 個要 root 的既有案例失敗（34 分 48 秒）；第二次合併後（`fedaad5`）pytest 子集 28 檔 992 案、0 skip，只有 5 個要 root 的 `test_root_*` 失敗；Playwright 兩個專案 150 案全過、node 94 案、build closure PASS；packaging unittest `Ran 205`、`OK (skipped=5)`、`validate.py` PASS、`tool_inventory.py` exit 0；兩個預檢 OK、雙向控制字元 0 個。
- **獨立安全審查（2026-11-17，判定「修正後通過」）已處理**（第 18 節）：
  - 必修 MF-1 修好：休眠開機（例如緊急關閉版）改寫還原紀錄時，不再丟掉還在等的核對；修好前，還原後沒核對預設帳號，發緊急關閉版再開通，
    預設帳號不必核對就能重發。上一份紀錄讀不到時休眠開機不改它。
  - 建議 S-1（三個測試缺口）、S-2（紀錄讀不到時全部撤銷會重建，格式要向後相容）、S-4（全部撤銷遇到意外的例外也 fail closed）、
    S-5（隔離目錄超過 64 個時清單照常可用）都改了程式或補了測試；S-6 補文件，全部撤銷的耗時交 HM-19c 量；S-3（待核對不一定是已撤銷，
    HM-12 依賴）寫進契約與威脅模型，交主對話協調 HM-12。
  - 待確認 Q-1（面板「知道了」只藏到重新整理）照現狀，等主對話確認或轉問使用者（第 17 節）。
  - 這一輪 4 個 commit（測試、核心、面板、文件）＋本筆記；沒有新決策，沒有碰到待定題；沒有 push、沒有開 PR。
- **疊在 HM-13b 的 PR #108 head `ebab019` 上**（`claude-delivery` `f4c7718`＋HM-13b 的 26 個 commit）。HM-13b 要等 HM-03a 的實機結果才合併；
  之後由主對話把本片 rebase 到 `claude-delivery`。本片只 commit，沒有 push、沒有開 PR。
- **單帳號還原後的面板提示（使用者 2026-11-16 21:xx 對 HM-13b 審查 Q-1 的定案，不受開關管）**：
  - 守門看到還原、而且預設帳號的權杖沒撤銷（沒有帳號資料，開通與否）時，在刪還原標記**之前**存 `/data/mcp/restore-notice.json`
    （`{"version":1,"at":"<UTC 秒>"}`，不含秘密；暫存檔＋fsync＋replace＋目錄 fsync、0600、本程序的 uid；被目錄占用時照 #120 移開；不碰 sentinel）。
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
  都換新，`Pc/restore_guard.py:513-516`），備份後才做、隨還原消失的操作 id 回 410。沒有帳號資料時預設帳號的收據照原樣（#121），單帳號
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
- **沒有碰到要使用者定的待定題**。本片自己定的實作細節（契約原本標「暫定，HM-13c」）寫在第 4 節與契約第 9 節 #122、#123（合併前是 #117、#118）。

## 1. 範圍與基準

證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-13c/`（`logs-first/`：第一段的紅；`logs/`：第二段；`tools/`：用到的
腳本，副檔名多加 `.txt`）。審查處理這一輪：`wave4/evidence-fix-HM-13c/`（`logs/`、`mutations/`、`tools/`，第 18 節）。log 先掃過像 token 的字串（43 個 URL 安全字元、不是同一個字母重複），0 個；全套的 junit 只留每個模組的摘要（`logs/full-junit-per-module.txt`）。
`SP:`＝本機的 scratchpad。

| 項目 | 值 |
|---|---|
| 切片 | HM-13c｜還原核對與全部撤銷的路由與面板（計畫 §6、§7.4、§8.4、§10.3、§12.3；風險高、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm13c-20261116`（一般 clone，不是 worktree） |
| HA 基準 | **2026-11-17 起：合併 HM-13b 的 `fc70404`**（merge commit `0f3d064`，第一個 parent 是本片 `a453b2a`、第二個是 `fc70404`；HM-13b 已合進 `claude-delivery` `165dbaf`；第 19 節）。合併前：`ebab019`：HM-13b 的 PR #108 head（`claude-delivery` `f4c7718`＋HM-13b 的 26 個 commit） |
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

### 4.1 單帳號還原後的提示（不受開關管；契約 §1.2、§8、#122）

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

### 4.2 還原時的收據（契約 §3.5、#67、#121）

- `operations.archive_for_restore(renew_missing=True)`：收據檔與 `.restored` 都沒有時也寫一份新收據檔（`restored_before_ms`＝還原當下），
  備份後才做、隨還原消失的操作 id 回 410，不會被當成新操作（PaaS 的 `_write_journal` 對每份設定都寫，`Pc/restore_guard.py:513-516`）。
- 守門處理的每個收據檔：開通或有帳號資料時，預設帳號（被撤銷時）、每個帳號目錄、索引旁。
- 沒有帳號資料時預設帳號的收據照原樣、沒有也不寫（#121，DQ-03 (b)）：單帳號安裝的行為不變，所以不用停下回報。開通但沒有帳號資料時索引旁
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

### 4.5 隔離目錄（契約 §1.1、§3.1、#123）

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

第二段的結果；審查處理這一輪的本機檢查見第 18.3 節。

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
- 審查處理這一輪新增的測試與時間見第 18.4 節（沒有新的 root 案例、沒有起真子程式）。

## 9. `checks` 秒數

開 PR 後補。

## 10. 預檢結果

第二段的結果；審查處理這一輪見第 18.5 節。

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
- 審查處理這一輪（2026-11-17 04:3x）再唯讀查一次：本機 PaaS repo 的 `origin/main` 已是 `48f394d`（有別的代理 fetch 過；本片沒有 fetch），
  比 `7087280` 多一個 #156：只改 `apps/hermes/` 的 CHANGELOG、README 與 `hermes_mcp_server/server.py` 的排程工具說明（3 檔），和多帳號、還原、
  撤銷無關。`restore_guard.py`、`restore_inplace.py` 在 `69ac425..48f394d` 仍然沒變。
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
| HM-13b 第 13 節／第 18.12 節（審查 Q-1） | 使用者定案：單帳號還原後的面板提示，接在守門上另留一筆提示紀錄 | 做了（第 4.1 節）：另開 `restore-notice.json`（理由同節）；`decisions.md` 第 1.1 節、契約 §1.2、#122 |
| HM-13b 第 13 節 | 備份時沒有收據檔的帳號：要不要對範圍 S 的每個帳號都寫新收據檔 | 做了：照 PaaS 每份設定都換新（第 4.2 節）；#121 的預設帳號除外，單帳號安裝不變。契約 §3.5、#67 |
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
| HM-12 審查第 4 節（給 HM-13c 的觀察；HM-13c 審查 S-3 指出第二段沒有接） | 維持「待核對＝已撤銷」：HM-12 的換身分換 token 要求 token 有效，待核對的帳號 token 已撤銷，所以換身分不會在核對前發新 token | 有例外，不改程式（HM-12 在別的 clone）：開關關時沒有關卡，還原撤銷的預設帳號可以直接重新產生，重新開通後那一列仍待核對、權杖卻有效（審查實驗 X7）。契約 §3.1、§4.1、威脅模型第 3 節寫明；交主對話：HM-12 與本片後合併的那一片，在換身分換 token 的路徑也檢查 `review_required`（有就 409 `restore_review_required`，同 rotate），或在契約 §4.1 改寫成允許（第 15 節）。2026-11-17 和 HM-12 合併時照主對話的決定接上關卡（第 19.5 節） |

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
- **主對話／HM-12（審查 S-3）**：「待核對＝已撤銷」有例外（上一列）。HM-12 與本片後合併的那一片，在 Odoo 換 url／database／username 換 token 的
  路徑也檢查 `ProfileAdmin.review_required`（有就 409 `restore_review_required`、什麼都不寫，同 `token/rotate`），或在契約 §4.1 寫明允許；
  兩片的假設要一致。本片沒有 HM-12 的程式可改（不在基準上）。
- **主對話（審查 Q-1）**：面板「知道了」只藏到重新整理，計畫的例子是「只在這個瀏覽器藏起來」。本片照現狀（審查建議 (a)），沒有自己定；
  要改成 (b)（放寬 N15、用 `localStorage` 記住這次還原已看過）或 (c)（加一條「關掉提示」的管理路由，超出使用者 2026-11-16 只核准的代價）
  都要另外決定（第 17 節）。
- **HM-19c（審查 S-6 (d)）**：全部撤銷在所有鎖裡逐一重起撤銷了的子程式，每個最多約 4 秒；在目標硬體量 Odoo 6 個帳號的全部撤銷時間
  （含 SD 卡上的 fsync），太長就改成平行重起（同 `stop_all`）或放開鎖後再重起。
- **HM-18（DOCS；審查 S-2、S-6）**：還原紀錄讀不到時的出路（按全部撤銷、之後逐帳號核對）；開關關、有帳號資料時還原（沒有核對卡與關卡，
  重新開通後仍要核對）；隔離區超過 64 筆時面板只列前 64 筆。`update-backup-rollback.md` 已寫，DOCS 照抄。
- **之後改還原紀錄格式的片（審查 S-2）**：`restore-record.json` 的格式（`RECORD_KEYS`、`RECORD_VERSION`、列的鍵）要向後相容，舊版寫的紀錄
  要照樣讀得懂（契約 §3.6、`ledger-tracking.md`）。
- **HM-03a**：第 13 節。
- **HM-25**：n8n 開通時，`apps/n8n/run.py` 已讀提示並交給 `make_apps`；接 `ProfileManager` 時把提示交給 manager（同 `run_product`）。
- **HM-29**：回補 PaaS 的題目照舊（#82 全部撤銷）；#122 是 HA 專屬（PaaS 還原一律撤銷）。
- **合併順序**：本片疊在 HM-13b 上。HM-12、HM-30、HM-16 若先合併並用掉契約第 9 節 #117 之後的列號，本片 rebase 時接在當時最後一列後面重排
  （本片的列：#117、#118）。帳本與 `gateway.py`、`profile_runtime.py`、`profile_admin.py` 照「後合者重算」。

## 16. 驗收條件（計畫 §12.3 HM-13c）

| 條件 | 狀態 |
|---|---|
| 全綠 | 合併 HM-13b（含 `claude-delivery`）、補 S-3 之後（第 19.7 節）：pytest 全套 6,411 案（`ba3b63d`）只剩 7 個要 root 的既有案例、0 skip；第二次合併後（`fedaad5`）子集 992 案只剩 5 個要 root 的；Playwright 150、node 94、packaging 205 全過；CI（root、0 skip）待 push 後的 run。本機（審查處理後，第 18.3 節）：pytest 全套只剩 7 個要 root 的既有案例、0 skip；Playwright 130、node 87、packaging 205 全過。CI（root、0 skip）待開 PR |
| 核對前不能重發 | 通過：還原（預設帳號與額外帳號）與重新開通後的休眠帳號（含休眠前就撤銷的），rotate 409 `restore_review_required`、什麼都不寫；紀錄讀不到 503（出路：全部撤銷重建）；核對後 200、8081 服務新權杖。審查 MF-1 修好：還原後沒核對的帳號，經過休眠開機改寫紀錄、再開通，仍要核對（第 18 節）。例外：開關關時沒有關卡（S-3）。和 HM-12 合併後，開通時 HM-12 的換身分換 token 也過關卡（409、什麼都不做；第 19.5 節） |
| 全部撤銷第 k 個失敗時的回應與 8081 行為 | 通過：k＝預設帳號、B、C 各一案：409＋逐帳號 `results`、收據結果未知、標記留著；失敗帳號撤銷前的權杖在 8081 兩種接法都 503，其他 401／404；做完的全部撤銷解除。另有連開始都沒有、沒收尾兩案 |
| 單帳號還原提示照使用者定案 | 通過：9 個產品存提示、8 個產品的正式 runtime bootstrap 只多 `restore_notice`、權杖兩種接法照用；輪替或撤銷後消失；沒還原的安裝什麼都不多（連 ctime）；開關關時新路由都是 404；面板「知道了」不用瀏覽器儲存 |
| 不受開關管的例外寫進契約、凍結測試逐案理由、CHANGELOG 一行 | 契約 §1.2、§8、#122；HM-01 凍結沒有要改的案例（第 5 節）；CHANGELOG 原文交 HM-19a（第 15 節） |
| 同 PR 更新帳本；契約第 9 節接在當時最後一列後面、變更紀錄 | 通過：帳本 12 列重算、新增 `restore.js`；#122、#123 接在 #121 後面（合併 HM-13b 與 `claude-delivery` 前是 #117、#118，接在 #116 後面；第 19.4 節）；第 10 節四列 |
| 測試資料規則 | 通過：token 都在執行時產生或用 `T`／`M`×43，憑證 `DUMMY-…`、網址 `.invalid` |
| 獨立安全審查 | 做了（`wave4/review-HM-13c.md`，修正後通過）；必修與建議的處理見第 18 節 |

## 17. 碰到而沒有自己定的事

- 「知道了」要不要在這個瀏覽器記住：要放寬面板的儲存不變式（N15、DQ-18；`build-closure.mjs` 擋 `localStorage`），本片沒做。現在的最小方案
  （重新產生或撤銷權杖、頁面記憶體裡隱藏）不需要新路由，所以沒停下來問；使用者覺得提示太常出現時再定。
  - 獨立審查把它列成 Q-1（請主對話確認或轉問使用者），選項：(a) 維持現狀（審查建議）；(b) 放寬 N15，只為這則提示用 `localStorage` 記住
    「這次還原（以 `at` 為鍵）已看過」，要改 `build-closure.mjs` 與 N15 的文件；(c) 加一條「關掉提示」的管理路由，開關關時多一條路由，超出使用者
    2026-11-16 只核准的代價。審查處理這一輪照計畫最保守的做法**維持現狀**，不改程式，寫進回報的待決事項。
- 索引不能用時，核對預設帳號也要先隔離索引（核對要能用的索引 ETag）。這是本片照「建立、刪除同規則」定的實作細節，不是決策題；若要讓預設帳號
  在索引壞時也能核對，可以改成收壞索引的 ETag（同全部撤銷），交審查時一併看。

## 18. 獨立安全審查的處理（2026-11-17 04:1x 起）

審查報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13c.md`（審查對象 `8ee89f4`；證據 `wave4/evidence-review-HM-13c/`）。
判定「修正後通過」：必修 1 項、建議 6 項、請主對話確認 1 題。先核對每一項（審查實驗 X1、X6 的情境在本線重寫成測試；X7、S-6 (c) 對照程式），
再改。本輪的腳本與 log：`wave4/evidence-fix-HM-13c/`（log 先遮掉像 token 的字串，掃描 0 命中）。

### 18.1 處理表

| # | 意見（摘要） | 處理 | commit | 測試／證據 |
|---|---|---|---|---|
| MF-1 | 休眠開機用只有休眠段落的紀錄蓋掉還原紀錄，預設帳號那列變 `kept`：沒核對就能重發 | 修。照審查草稿，另外兩點不同：(1) 上一份紀錄讀不到時**不改它**（記一行 `RECORD_KEPT`），新權杖照舊一律 503，出路是全部撤銷重建（S-2）；草稿是當成沒有、整份重寫，會丟掉預設帳號那列。(2) 還原段落只在上一份還有列「這次仍在等」時保留；草稿是上一份有任何待核對列就保留。預設帳號那列照上一份原樣（`_carried`）。(1) 的代價：若只是那次開機一時讀不到，之後讀到的是舊紀錄，這次休眠撤銷的帳號不在裡面（權杖已撤銷，重新開通後不必核對）；選這個方向是為了不丟掉還原的核對（威脅模型第 3 節寫明） | `df9d8fc`（測試）、`ba2fe54` | X1 重寫成 `test_after_a_dormant_start_the_default_profile_still_waits_for_its_review`；`test_a_dormant_start_never_drops_a_review_the_last_record_waits_for`（三種核對情況）；`test_a_dormant_start_leaves_a_record_it_cannot_read_as_it_is`。舊程式上 4 案紅；突變 F04～F08 都被擋 |
| S-1 | M05、M22、M32 存活：三個行為沒有測試 | 採用：補三個測試（M19 照審查，等價、不補） | `df9d8fc` | M05：`test_a_profile_revoked_before_the_dormant_start_waits_for_its_review_too`（F01 被擋）；M22：`test_a_quarantine_directory_whose_state_opens_is_revoked_and_wiped_before_it_goes`（隔離目錄是改名的正常帳號目錄、刪除被 monkeypatch 成刪不掉；F02 被擋）；M32：`test_a_start_stopped_anywhere_on_the_way_saves_the_notice_at_the_next` 加 `enabled=True`（F03 被擋）。三個測的都是既有行為，舊程式上照過 |
| S-2 | 紀錄讀不到時每個 rotate 永遠 503、面板沒有出路；格式日後要向後相容 | 採用 (a)＋(c)：全部撤銷做完時紀錄若讀不到，重寫一份（每個帳號 `revoked`、`reviewed_at: null`，沒有還原與休眠段落；讀得到就不改；`record_usable()`）；面板說明出路，重建的紀錄有自己的標題；契約 §3.6、`ledger-tracking.md`、`restore_lock.py` docstring 寫明格式要向後相容。沒採 (b)（核對完就刪紀錄）：會丟掉核對紀錄，已刪帳號的列也讓「沒有待核對」不好判斷；(a) 已涵蓋格式改壞的出路 | `ba2fe54`、`48a8ef9`、`c6f99c6` | `test_revoke_all_rebuilds_a_record_that_cannot_be_read`（含讀得到時不改）；Playwright 一案；突變 F09、F10、F12、G03、G04 都被擋 |
| S-3 | 「待核對＝已撤銷」有例外，HM-12 的換身分換 token 依賴這個前提 | 本片不改程式（HM-12 的路徑不在本片基準上，也不能動別的 clone）：契約 §3.1 `token/rotate`、§4.1 `restore_review_required`、威脅模型第 3 節寫明例外；交主對話（第 15 節）；第 14 節補 HM-12 審查那一列 | `c6f99c6` | 審查實驗 X7（`evidence-review-HM-13c/logs/x-experiments-3.txt`） |
| S-4 | 全部撤銷碰到 `ConfigError`、`OSError`、`ValueError` 以外的例外時回 500、沒有 fail closed | 採用：其他例外也當成沒有結果：409 `operation_outcome_unknown`、收據未知、每個已登錄帳號 `committed()`、撤銷前的權杖全進 503 名單；log 一行固定文字，只寫例外的類別（`REVOKE_ALL_STOPPED`） | `ba2fe54` | `test_revoke_all_stopped_by_an_unexpected_error_fails_closed`：半途停（預設帳號已撤銷、B 還沒），B 留在磁碟上的舊權杖兩條接法都 503；例外的文字故意含 B 的權杖，log 掃描確認沒外露；之後做完的全部撤銷解除。舊程式上紅；突變 F11 被擋 |
| S-5 | 隔離目錄超過 64 個時整份帳號清單讀不到，也刪不掉 | 採用：清單不因數量拒絕（每一筆照舊驗格式）；面板只列前 64 筆（`QUARANTINE_SHOWN`）並說還有幾筆，刪掉上面的之後其餘依序出現 | `48a8ef9` | node 斷言（70 筆照收）；Playwright 一案（70 筆：列 64、說另有 6 筆、選單是真的清單、全部撤銷可按；刪一筆後剩 5 筆沒列）；突變 G01、G02 都被擋 |
| S-6 | 文件與量測落差 | (a) `update-backup-rollback.md` 分開寫開關關、有帳號資料的還原，契約 §3.1 `token/rotate` 補「開關關時沒有關卡」；(b) 契約 §4.1 `operation_outcome_unknown` 寫 `results` 空的兩種意思；(c) 照程式核對後改寫：轉送名額是在建 token lease **之後**才等（`gateway.py` 的 `take_slot`），已建 lease 的請求都由 `committed()` 結束（之後 `lease.run` 一檢查就停），所以視窗只是「分派器比對過、還沒建 lease」的請求（例如准入滿時正在讀的小通知，最多 2 秒），不是審查寫的「准入、名額」排隊；契約 §4.2、威脅模型第 3 節、`profile_admin.py` docstring 照這個寫；(d) 交 HM-19c（第 15 節），威脅模型第 3 節記一條 | `ba2fe54`（docstring）、`c6f99c6` | — |
| Q-1 | 面板「知道了」只藏到重新整理 | 不自己定：照計畫最保守的做法維持現狀（審查建議 (a)），寫進第 17 節、第 15 節與回報 | — | — |

### 18.2 先紅後綠與突變

- 先寫測試（`df9d8fc`），在舊程式上跑：伺服器新測試 11 案，**6 案紅**（MF-1 四案：三種核對情況的前兩種、X1、讀不到的紀錄不改；S-2 一案；
  S-4 一案），5 案綠（S-1 的三個測試共 4 案與 MF-1 第三種情況：測的是既有行為或修正前後相同的情況）。面板：舊的 `restore.js`、`app.js`
  上 node 1 檔紅（缺 `QUARANTINE_SHOWN`）、Playwright 新的 2 案紅。log：`logs/red-server-old-source.txt`、`logs/red-ui-old-source.txt`。
  `df9d8fc` 的 commit 訊息把綠的 5 案都算成 S-1，實際是 S-1 的 4 案加 MF-1 第三種情況 1 案；照寫的當時，不改寫歷史。
- 新程式上：`tests/test_restore_review.py` 60 案全過（`logs/green-server-new-tests.txt`，開發用的無 session 鎖跑法：只選 in-process 的測試；
  正式 conftest 的結果在第 18.3 節）；`restore-review.spec.mjs` 11 案全過。
- 突變（`tools/mutate.py.txt`、`tools/mutate_ui.py.txt`；每次改一處、跑選定的測試、從複本放回並核對 SHA-256，不用 git 還原）：伺服器 12 次、面板 4 次，
  **16 次全被擋**；基準 F00 60 案全過。總表 `mutations/summary.json`、`mutations/summary-ui.json`。
- 審查的 7 個實驗（`evidence-review-HM-13c/scripts/test_review_hm13c_experiments.py`，不 commit，從 scratchpad 跑）在修正後重跑：7 案全過；
  X1 轉綠（預設帳號 rotate 409 `restore_review_required`），X6 的請求都結束、503 名單 2 個，X7 照舊（S-3 的例外，寫進文件）
  （`logs/review-experiments-after-fix.txt`）。

  | # | 突變 | 擋下的測試 |
  |---|---|---|
  | F01 | `REVIEWED_TOKENS` 拿掉 `already_revoked`（審查 M05） | 休眠前就撤銷的帳號 |
  | F02 | 刪隔離目錄前不撤銷、不抹憑證（審查 M22） | 讀得到的隔離目錄 |
  | F03 | 開通、沒有帳號資料時刪標記之後才存提示（審查 M32） | 逐步中斷 `[True]` |
  | F04 | 休眠紀錄什麼都不保留（回到審查前） | 三種核對情況的兩種、X1 |
  | F05 | 只保留預設帳號那列、丟掉還原段落 | 同上 |
  | F06 | 上一份有還原段落就一律保留 | 三種核對情況的第三種 |
  | F07 | 已核對的預設帳號那列也保留 | 三種核對情況的兩種 |
  | F08 | 上一份讀不到時照樣整份重寫（審查草稿的做法） | 讀不到的紀錄不改 |
  | F09 | 全部撤銷不重建讀不到的紀錄 | 重建 |
  | F10 | 重建時也走「讀不到就不改」 | 重建 |
  | F11 | 拿掉 `except Exception` | 意外的例外 |
  | F12 | 重建的紀錄把預設帳號寫成 `kept` | 重建 |
  | G01 | 面板拿回 64 筆上限 | node＋Playwright |
  | G02 | 面板不切前 64 筆 | Playwright |
  | G03 | 讀不到的紀錄用舊說明 | Playwright |
  | G04 | 不認重建的紀錄 | Playwright |

### 18.3 本機檢查（一般使用者 uid 1000；TMPDIR 都是 `ha_env.sh` 給的，跑完用完整路徑刪掉）

| 檢查 | 結果 |
|---|---|
| 面板 node（`npm test`） | 87 案全過（`logs/t2-ui-node-build.txt`） |
| `npm run build`＋`build-closure.mjs` | PASS |
| Playwright 全套（面板檔＝`48a8ef9`；之後的 commit 只改文件） | **130 案全過**（4.2 分；第二段的 128 案＋本輪 2 案；`logs/t3-ui-browser-full.txt`） |
| pytest 相關 22 檔（本片與 HM-13b 三檔、HM-13a、HM-10 兩檔、HM-11 形狀比對、HM-01 黃金回歸與兩個契約凍結、零改寫、`test_output_schemas`、HM-31 的參數順序、路由、passthrough、log 掃描、執行套件、生命週期、store、兩個帳本測試） | 取自全套的 junit（`logs/t5-full-suite.summary.txt`）：936 案，930 過，6 個失敗都是要 root 的（`test_restore_detection` 5、`test_profile_store` 1），86.3 秒。先排的子集跑法有引號錯誤（檔名清單的換行把指令拆開），只跑到前 4 檔（157 案全過，`logs/t1-related.txt`），所以改從全套的 junit 取這 22 檔 |
| pytest 全套（`tests`，CI 的指令加 `-rfEs --durations=30`、junit；正式 conftest、排在共用 wave1 鎖後面；`logs/t5-full-suite.txt`） | `c6f99c6`（工作樹只多本筆記的草稿；05:13～05:46）：**6,152 案、0 skip，6,145 過**，7 個失敗都是要 root 的既有案例（`test_restore_detection` 5、`test_profile_store` 1、`test_owned_executable` 1，都停在要求 root 的那一行）；1,977.6 秒（32 分 58 秒）；2 個 warnings 是既有的 websockets 棄用警告。比第二段多 10 案（本輪新增） |
| packaging unittest（照 CI 的離線暫存 venv，不用 PYTHONPATH；本輪沒動 `packaging/`） | `Ran 205`、`OK (skipped=5)`（`logs/t4-packaging*.txt`） |
| `packaging/validate.py`（ci-venv） | PASS |
| `scripts/tool_inventory.py` | exit 0（沒動 `apps/runtime/*.py`、`apps/*/launch.py`，不用 `--write`） |
| 雙向控制字元（U+202A～202E、U+2066～2069；另查 U+200E、U+200F、U+061C） | `ebab019..HEAD` 12 個 commit 的訊息與每個改到的檔的全文（含本筆記的 commit）：0 個（`tools/bidi_scan.py.txt`、`logs/bidi-scan.txt`）；PR 說明草稿另掃也是 0 個 |

### 18.4 只在 CI 跑的測試與 CI 時間

- 只在 CI 跑的照第 8 節（要 root 的既有 7 案）；本輪沒有新的 root 案例、沒有起真子程式的新案例（都在暫存目錄的守門或 `NoProcessSupervisor`＋MockTransport）。
- 新測試的本機時間（全套的 junit）：`tests/test_restore_review.py` 60 案 5.4 秒，其中本輪新增的 10 案 1.6 秒（最慢的是開通時的逐步中斷，約 0.6 秒）；Playwright 新的 2 案約 3.4 秒；node 不到 1 秒。
- CI 推估：`checks` 比第二段多不到 10 秒；開 PR 後照實補。

### 18.5 預檢（本筆記 commit 之後再跑一次，結果記在回報與 PR 說明）

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base ebab019 --head HEAD --full` | `c6f99c6`：OK，0 命中（gitleaks 8.28.0；`ebab019..c6f99c6` 11 個 commit，另掃 HEAD 的樹與整段歷史；`logs/secret-precheck-c6f99c6.txt`） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base ebab019` | `c6f99c6`：OK：`runtime-patches.json` 178 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的檔裡列管的都由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔（`logs/ledger-precheck-c6f99c6.txt`） |

### 18.6 本輪用到的決策、待 HM-03a 確認、PaaS

- 決策照第 12 節（DQ-03 (b)、DQ-13、DQ-14、DQ-37、DQ-39 (a)、DQ-40 (a)、使用者 2026-11-16 的定案）；本輪沒有新決策、沒有碰到待定題。
  S-2 選 (a)＋(c) 是審查列的實作選項，不是決策題。
- 待 HM-03a 確認的項目照第 13 節，本輪沒有新增（S-6 (d) 的耗時是 HM-19c 的量測，不是 HM-03a）。
- PaaS：第 11 節（`69ac425..7087280` 的 10 個 PR 與本片無關；本機 `origin/main` 已到 `48f394d`，多的 #156 只改 Hermes，也無關）。

## 19. 和 HM-13b（含 claude-delivery）合併，補審查 S-3（2026-11-17）

第 1～18 節照合併前寫；契約列號的現行指標已改成合併後的（第 19.4 節）。第 15 節「合併順序」那點與第 18 節是當時的紀錄，照原文。
證據在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-merge-HM-13c/`（`tools/`：用到的腳本，副檔名多加 `.txt`；`logs/`：log；
`conflicts-diff3/`：解衝突前的 15 個檔，diff3 格式的衝突標記）。HM-13b 這一半的紀錄在 HM-13b 筆記第 19 節。

### 19.0 結論

- HM-13b（PR #108）原本的基準 `f4c7718` 和 `claude-delivery` 有衝突，GitHub 不替它跑 CI，疊在上面的本片（PR #112）也一樣。HM-13b 先用 merge commit 把
  `claude-delivery` `165dbaf` 合進去（`6bb7fcd`，列號改成 #118～#121，`fc70404` push）；本片再用 merge commit 把更新後的
  `origin/feat/ha-multiprofile-hm13b-20261116` 合進來（`0f3d064`：第一個 parent 是本片 `a453b2a`、第二個是 `fc70404`），不 rebase、不 force push；
  之後一般的 fast-forward push。
- 衝突在 15 個檔：程式 8 塊（`gateway.py` 1、`profile_runtime.py` 6、`run_product.py` 1）、面板 9 塊（`api.js` 3、`app.js` 1、`server.mjs` 1、
  `profile-api-parity.spec.mjs` 2、`profile-api-cases.json` 2）、測試 4 塊、文件 13 塊；帳本 7 塊照 JSON 重組。程式與面板都是「同一個地方各加一段」：
  兩邊的行為都留（第 19.2 節）。
- 契約第 9 節本片的兩列從 #117、#118 改成 #122、#123，本片引用 HM-13b 的列一起改（#115→#120、#116→#121；`849d9ba`）。
- 審查 S-3（主對話 2026-11-17 定）做了：HM-12 的換身分換 token 也過還原核對的關卡（第 19.5 節）。合併時另找到一個語意交集：換身分換掉還原保留的
  預設帳號權杖時，還原提示要一起消失（同 `token/rotate`），一起補。
- 08:28 主線又合了 HM-33（PR #115，`f239157`），HM-13b 再合一次（`22f5766`、`369d80b`）；本片再把更新後的 HM-13b 合進來（`fedaad5`），所以也含
  `f239157`、和主線沒有衝突（第 19.12 節）。
- 和 HM-13b 的分支相比，本 PR 的改動仍是原本的 35 個檔。
- 本機：pytest 全套（`ba3b63d`：合併與 S-3 之後）6,411 案、0 skip，6,404 過，只有 7 個要 root 的既有案例失敗（34 分 48 秒）；第二次合併後（`fedaad5`）pytest 子集 28 檔 992 案、0 skip，只有 5 個要 root 的 `test_root_*` 失敗；Playwright 兩個專案 150 案全過、node 94 案、build closure PASS；packaging unittest `Ran 205`、`OK (skipped=5)`、`validate.py` PASS、`tool_inventory.py` exit 0；兩個預檢 OK、雙向控制字元 0 個。

### 19.1 範圍

- `git fetch origin`（2026-11-17 08:1x）：`origin/feat/ha-multiprofile-hm13b-20261116`＝`fc70404`；本片的遠端分支與本機 head 都是 `a453b2a`、工作樹乾淨。
  先開本機備份分支 `backup/hm13c-before-merge-20261117`（指向 `a453b2a`，不 push）。
- 新基準帶進來的（`ebab019..fc70404`）：87 個 commit（`claude-delivery` `f4c7718..165dbaf` 的 84 個、HM-13b 的 merge commit 與兩個 commit），共改 55 個檔。
- 兩邊都改的 20 個檔裡，`ledger-tracking.md`、`profile_router.py`、`restore_lock.py`、`tests/test_output_schemas.py`、`tests/test_restore_lock.py`
  git 自動合併（兩邊改的是不同行）；其餘 15 個有衝突。
- 依賴：新基準沒有動 `uv.lock`、`package-lock.json`、`package.json`、`pyproject.toml`、`requirements*`、`packaging/inputs.json`、patch 檔與 Dockerfile，
  沒有重跑 `setup_repo_env.sh`。面板原始碼有變（HM-12 面板），照 CI 先 `npm run build` 再 `node tests/build-closure.mjs`。
- PaaS：本機唯讀 PaaS repo 的 `origin/main` 是 `48f394d`（沒有 fetch），第 11 節之後只多 #156（Hermes 排程工具說明，HM-33 在補），和本片無關。

### 19.2 衝突與處理

解衝突用 repo 外的腳本：`blocks3.py`（diff3 格式，逐塊先斷言三邊的內容再組合）、`resolve_hm13c_merge.py`（每塊的規則）、`merge_ledger3.py`
（帳本三方照 JSON 重組）。原則：新基準那一側照原文、放在前面；本片的行接在後面、照原文（本片自己的列號在合併之後一起改，第 19.4 節）；
程式照語意合；兩邊都改的同一行，用本片的那行再套上新基準那一側的修改（套不上時留給改號的 commit，下表寫明）。

| 檔 | 衝突 | 處理 |
|---|---|---|
| `gateway.py` | 1 塊 | `make_apps` 的參數照合併順序：`stop_child`、`reply_worker`（HM-12、HM-30）、`dormant_profiles`（HM-13b），本片的 `restore_notice`、`review_required` 在最後。docstring、參數檢查、bootstrap、`token/rotate` 的關卡與提示都自動合併 |
| `profile_runtime.py` | 6 塊 | `RUNTIME_OPTIONS`、`ProfileRuntime.__init__`、`gateway_options` 收全部五個名稱；`ProfileManager` 的說明留 HM-30 那段（它收尾 docstring），`__init__` 收 `reply_worker` 與 `restore_notice`，欄位兩邊都留；每個帳號的 runtime 同時拿到工作執行緒的 Lane（HM-30）、還原提示（只有預設帳號）與核對關卡（本片） |
| `run_product.py` | 1 塊 | 開通時 `ProfileManager(..., reply_worker=worker, restore_notice=notice)` |
| `api.js` | 3 塊 | HM-12 的新來源 422 文案在前、本片的 `operation_restored` 文案在後；`known` 用本片的前兩行（`operation_restored` 410）接 HM-12 的 `PROFILE_CODES`、`SAVE_CODES`，錯誤照 HM-12 先建好再丟（換 token 的形狀 D、state unavailable 的旗標）；放掉操作識別碼時本片多認 `restore_review_required`，接著是 HM-12 審查 S-7 的存檔提示 |
| `app.js` | 1 塊 | 只有 import：`api.js`（多 `TOKEN_ROTATED`）、`contracts.js`（多 `newOriginSecrets`、`urlSecrets`）用 HM-12 面板的，`profiles.js`（多 `statusLabel`）與 `restore.js` 用本片的（先斷言另一邊那一行和基準相同）。還原提示卡、核對卡、全部撤銷、隔離目錄與換 token 的提示（`reloadSaved`、`reloadRotated`）、重新讀取都自動合併 |
| `fixtures/server.mjs` | 1 塊 | HM-12 的說明、`URL_SECRETS`、`IDENTITY`、`ROTATION_LETTERS` 與多 `rotations` 的那一行在前，本片的 `restoreRows` 等、`QUARANTINE`、`REVIEWED_AT` 在後 |
| `profile-api-parity.spec.mjs` | 2 塊 | 說明：HM-12 那一行在前、本片的還原說明與常數在後；`fixtureSetup`：HM-12 的 `rebindFault` 在前、本片的還原與隔離在後 |
| `profile-api-cases.json` | 2 塊 | 說明與情境都是 HM-12 的在前、本片的在後；照 JSON 的結構在 HM-12 那一行後面補逗號，合完 `json.loads` 驗過 |
| `tests/test_request_budget_gateway.py` | 2 塊 | HM-31 那案釘 `make_apps` 參數的最後幾個：改成最後九個（`..., 'stop_child', 'reply_worker', 'dormant_profiles', 'restore_notice', 'review_required'`）；本片原有的三個 keyword-only 檢查照留 |
| `tests/test_panel_profile_api_shapes.py` | 2 塊 | import 兩邊都收（`restore_detect`、`ConfigError`、`ProductStore`、`Journal`、`record_writes`）；HM-12 的 fault 先布好、本片的還原等待在後 |
| 契約 | 8 塊 | 開頭的狀態：本片那句，再套上 HM-13b 對這一行的兩處修改（先斷言 HM-13b 那邊只改了這兩處）；第 1.2 節清單與段落 HM-32 在前、本片在後；第 3.5 節用本片的那段，套上 HM-13b 的 #116→#121；第 4.1 節 `operation_outcome_unknown`、`operation_restored` 兩列用本片的、新來源那列用 HM-12 的；第 9 節說明段、表尾與第 10 節新基準在前、本片在後 |
| `acceptance-matrix.md` | 1 塊 | T-21：用本片那列（HM-13b 那邊只把 #113～#116 改成 #118～#121，先斷言）；本片的範圍 #113～#118 在改號的 commit 改成 #118～#123 |
| `threat-model.md` | 1 塊 | I8 用 HM-30 改的、I9 用本片改的（先斷言另一邊那一列和基準相同） |
| `decisions.md` | 3 塊 | 第 1.1 節標題寫成「HM-31 記，HM-30、HM-13c 補」；兩個表都是新基準的列在前 |
| 帳本 | 7 塊 | 不解文字，照 JSON 重組（第 19.6 節） |

- merge commit 的訊息：本機第一次寫成「兩邊都改的 8 列」，實際是 7 列。push 前改正：用 `git commit-tree` 以同一個樹、同樣兩個 parent 重做 merge commit
  （`0f3d064`，訊息只改這一處），之後的 5 個 commit 照樣重放，每個樹都和原本的相同（原本的 `4d24a98`、`8956480`、`8948397`、`20db799`、`27a59b7`、
  `b8ddca0` 留在本機分支 `backup/hm13c-after-merge-msg8-20261117`，不 push）。證據裡 08:23～08:39 的 log 寫的是原本的 commit 編號（樹相同）。

### 19.3 核對

- 每個兩邊都改的檔（`both_sides_kept.py`，在合併的工作樹）：每一邊對基準加的行都在合併後的檔裡，除了上表合起來的那幾行（`logs/both-sides-kept.txt`）。
- 和 HM-13b 的分支相比改了 35 個檔，就是本片原本的 35 個；合併後只有 `profile_runtime.py`（多 2 行：選項換行）與 `test_request_budget_gateway.py`
  的增刪行數不同。改號與 S-3 之後另外多了契約、威脅模型、還原手冊、`gateway.py`、`api.js`、兩個測試檔的行（第 19.4、19.5 節）。
- 第 9 節的列號在 `849d9ba` 之後是 1～123 連號、沒有重複。

### 19.4 列號對照（契約第 9 節；新基準最後是第 121 列）

| 合併前（`ebab019` 基準） | 合併後（`fc70404` 基準） | 項目 |
|---|---|---|
| #117 | #122 | 還原後沿用權杖的面板提示 |
| #118 | #123 | 隔離目錄的清單與刪除 |

- 本片引用 HM-13b 的列：#115（守門自己的名稱被目錄占用）→ #120、#116（沒有帳號資料時預設帳號的收據）→ #121。HM-12 的 #113～#117 本片沒有引用。
- 解衝突時不改號（本片的行照原文；第 3.5 節那行例外：套上 HM-13b 的 #116→#121）。改號在合併後的一個 commit（`849d9ba`，`renumber_hm13c.py`）：
  每處是精確字串、次數固定，而且一定在本片自己加的行上（HM-13b 分支的檔沒有那一行），所以 HM-12 的 #113～#117、HM-13b 的 #118～#121，以及
  `profile-api-cases.json` 裡 HM-12 寫的「section 9 #113-#115」（合併只在那行後面補逗號）都改不到；改完再確認本片加的行沒有舊號。
- `849d9ba` 改的：契約 12 處（開頭的狀態加「合併 HM-13b 與 `claude-delivery` 之後本片的列改成 #122、#123」、第 1.2 節本片那段兩處、第 4.1 節
  `operation_restored` 列、第 8 節、第 9 節說明段兩處、#67 的 HM-13c 附註、兩列的列號、第 10 節本片的兩列），第 10 節加一列；`decisions.md` 2 處；`acceptance-matrix.md` T-21 1 處；
  `docs/operations/update-backup-rollback.md` 1 處；`restore_lock.py` docstring 1 處；`tests/test_restore_review.py` 5 處（都只是說明文字）；帳本
  `restore_lock.py` 那列的 SHA-256 重算（說明裡本片加的那段沒有列號）。
- 本筆記改的現行指標 12 處（本筆記的 commit；`renumber_hm13c_notes.py`）：結論兩處與最後一點、第 4.1、4.2、4.5 節標題與第 4.2 節一點、第 14 節兩列、
  第 15 節 HM-29、第 16 節兩列。第 15 節「合併順序」那點與第 18 節照原文。PR 說明（repo 外的草稿）也改了。
- commit 訊息照寫的當時，不改寫（`9a46c1c`～`a453b2a` 的訊息仍是 #117、#118）。

### 19.5 審查 S-3：HM-12 的換身分換 token 也過核對關卡

- 題目（審查報告第 3 節 S-3）：待核對不一定是已撤銷。開關關、有帳號資料時還原，守門撤銷預設帳號（紀錄那列 `revoked`、沒核對）；開關關時沒有關卡，
  管理員可以直接重新產生；再開通後預設帳號 `restore_review_required: true`、`token_active: true`。這時 HM-12 的換身分（Odoo 改 url／database／username）
  會在核對前換出一把新權杖。主對話 2026-11-17 定：這條路徑也過關卡，回 409 `restore_review_required`，同 `token/rotate`，什麼都不改。
- 做法（`0cf5520`，`gateway.py`）：`admin_action` 的存檔路徑在 If-Match、`backend_fixed`、`endpoint_global`、新來源（422）之後，`identity_rebound` 成立
  （會換 token）時先問 `review_required()`：要核對就 `BadRequest(409, {'code': 'restore_review_required'})`，在 `rebind_identity` 之前，所以子程式不停、
  `committed` 沒設、不寫、不發布；紀錄讀不到時 `review_required()` 丟 `ConfigError`，照 `token/rotate` 回 503 `{"error":"state unavailable"}`。
  不換 token 的存檔（只改密碼、第一次設定、token 已撤銷）不問關卡。開關關時沒有 `review_required`（也不會換身分），照今天。
- 合併後的語意（同一個 commit）：`rebind_identity` 在 `token_access.committed()` 之後清掉還原提示（`restore_notice.clear()`），同 `token/rotate`：
  提示寫的是「權杖已回到備份當時的值」，換身分換掉那把權杖後就不成立。只有寫入成功、發布之後才清；寫入失敗、結果不明時不動。
- 面板（`e2d28b5`，`api.js`）：`backend`、`backend/patch` 收到 409 `restore_review_required`（開通、Odoo）時，先沿用這個代碼現成的文字「這個帳號是從備份
  還原（或休眠）回來的，還沒有核對：請先到預設帳號頁的核對卡確認它的設定，按「已核對」後才能重新產生權杖。」，再補一句「改後端身分（Odoo 的網址、資料庫
  或使用者）會換新這個帳號的 MCP 權杖，所以也要先核對才能儲存；這次未儲存任何變更。」（寫法同 HM-12 審查 S-7 在 503 後面補提示）。`token/rotate` 與其他
  回應的文字不變；伺服器的文字照舊不顯示；存檔失敗時清掉打過的密碼、其他欄位留著（今天的行為）。
- LOCAL MOCK 沒有模擬這個關卡：Playwright 那一案用它現成的 `saveStatus`／`saveCode`（存檔照這個代碼拒絕，同 HM-12 面板測 422 的方式）。mock 的換身分
  不會碰到「待核對、權杖有效」的帳號（`reset()` 把待核對那幾列的權杖都設成撤銷），對照檔也沒有這個情境；真後端的行為由 pytest 驗（下面）。mock 只補了
  合併後的另一半：換身分換了預設帳號的權杖時清掉 `restoreNotice`（`e74d4c0`，同 add-on；`14e435f` 的 Playwright 案例先紅後綠）。
- 文件（`ba3b63d`）：契約第 4.1 節 `restore_review_required` 列（觸發條件、兩條發新權杖的路徑都接關卡、面板文字）、第 3.1 節 `backend`／`backend/patch` 與
  `token/rotate` 兩列、第 1.2 節「怎麼消失」、開頭的狀態、第 10 節一列；`threat-model.md` 第 3 節「待核對不一定是已撤銷」那條、I9 的測試欄、開頭的狀態；
  `acceptance-matrix.md` 的 `test_restore_review.py` 列；`docs/operations/update-backup-rollback.md` 的核對步驟（改 Odoo 網址、資料庫或使用者也要先核對）。
- 先紅後綠（`3c3f1b4` 只有測試，程式是合併後、`849d9ba` 的）：

| 測試（`tests/test_restore_review.py`，除非另寫） | 紅（沒有關卡） | 綠 |
|---|---|---|
| `test_an_identity_change_waits_for_the_profiles_review_too[backend]`、`[backend/patch]`：X7 的狀態，預設帳號待核對、權杖有效；換使用者 → 409、子程式沒停、磁碟樹與 state 不變、權杖照舊兩條接法都通、沒有 log；只改密碼照存 | 200 `token_rotated`（兩案） | 過 |
| `test_once_reviewed_an_identity_change_rotates_the_token_as_today`：按「已核對」後同樣的存檔 → 停、寫、發布、起，200 `token_rotated` | 過（照今天） | 過 |
| `test_switched_off_an_identity_change_after_a_restore_is_todays[without profile data]`、`[with profile data, reissued]`：開關關，單帳號或 X7 的狀態 → 今天的回應、權杖與 history 不變 | 過（照今天） | 過 |
| `test_a_record_that_cannot_be_read_holds_an_identity_change_too`：紀錄讀不到 → 503、什麼都不做；只改密碼照存 | 200（換了 token） | 過 |
| `test_an_identity_change_that_rotates_the_kept_token_ends_the_notice`：開通、沒有帳號資料的還原，提示在；只改密碼提示還在；換使用者後提示與 `restore-notice.json` 都不見 | 提示還在 | 過 |
| `restore-review.spec.mjs` 的 `a backend save held for the restore review …`：面板文字＝待核對的文字＋存檔那一句、錯誤樣式、伺服器文字不顯示、密碼清掉、使用者欄位留著 | 只有待核對的文字 | 過 |

  log：`logs/s3-red.log`（4 失敗、3 過）、`logs/s3-green.log`（`test_restore_review.py`＋`test_odoo_identity_rotation.py` 100 案全過）、
  `logs/s3-panel-red.log`（1 失敗）、`logs/s3-panel-green.log`（`restore-review.spec.mjs` 12 案全過）。

### 19.6 帳本（`docs/provenance/runtime-patches.json`）

- 合併（`merge_ledger3.py`）：以 HM-13b 分支的帳本（65 列）為底、照原順序；本片沒碰的列照新基準；只有本片碰的 5 列用本片的；兩邊都碰的 7 列
  （`gateway.py`、`run_product.py`、`profile_runtime.py`、`profile_router.py`、`app.js`、`api.js`、`restore_lock.py`），說明是新基準的文字接本片在列尾加
  的那段（本片只在列尾追加，先斷言；新基準那邊的文字整段照用：`claude-delivery` 的文字在 HM-13b 那段前面長出來、HM-13b 也在裡面改了號）；本片新加的
  `restore.js` 照原位置；SHA-256 一律照合併後的檔重算，最後全列 0 漂移。共 66 列。
- 改號（`849d9ba`）：只重算 `restore_lock.py` 的 SHA-256（docstring 一處）。
- S-3：`gateway.py`（`0cf5520`）、`api.js`（`e2d28b5`）兩列各加一句、SHA-256 照檔重算。

### 19.7 本機檢查（一般使用者 uid 1000；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `npm test`、`npm run build`、`node tests/build-closure.mjs` | 合併後（08:23，`8956480`，樹同 `849d9ba`）node 94 案全過、build closure PASS；最後（`fedaad5`）node 94 案全過、build、build closure PASS |
| pytest 快速子集（合併後、S-3 之前；08:23，`8956480`＝`849d9ba` 的樹；13 檔：本片與 HM-13b 的守門、HM-12 換身分、形狀比對、參數順序、黃金回歸、兩個契約凍結、HM-10） | 366 案全過（`logs/pytest-quick-after-merge.log`） |
| S-3 與提示的先紅後綠 | 第 19.5 節 |
| Playwright 全套（S-3 之後，08:35～08:39，`b8ddca0`＝`ba3b63d` 的樹） | 149 案全過（`single` 131、`profiles-on` 18；4.3 分） |
| pytest 全套（`ba3b63d`；CI 的指令加 `-rfEs --durations=30`、junit；正式 conftest、排在共用鎖後面；08:39～09:14） | 6,411 案、0 skip，6,404 過；7 個失敗都是要 root 的既有案例（`test_restore_detection` 5、`test_profile_store` 1、`test_owned_executable` 1，都停在要求 root 的那一行）；2,088.7 秒（34 分 48 秒）；2 個 warnings 是既有的 websockets 棄用警告（`logs/full-suite.log`、`logs/full-suite-by-module.txt`）。本片相關：`test_restore_review` 67、`test_odoo_identity_rotation` 33、`test_panel_profile_api_shapes` 16、`test_reply_worker` 147（量停頓的也綠）、`test_restore_lock` 71、黃金回歸 17、兩個契約凍結 28、`test_ledger_precheck` 8，全過 |
| LOCAL MOCK 的提示（`14e435f` 紅、`e74d4c0` 綠；09:15～09:16） | 紅 1 案（提示卡還在）；綠：`restore-review`、`backend-identity`、`profile-api-parity` 三個 spec 45 案全過 |
| pytest 子集（第二次合併後，`fedaad5`；28 檔：HM-33 的兩檔、黃金回歸、`test_output_schemas`、兩個契約凍結、帳本與秘密預檢工具、工具清單、log 掃描、owned ports、讀 LOCAL MOCK 的 `test_owned_ui` 與 `test_owned_browser`、形狀比對、本片與 HM-13b、HM-12、HM-31、HM-10、HM-30 的相關檔） | 992 案、0 skip，987 過，5 個失敗都是要 root 的 `test_root_*`；132.3 秒（別的線拿著共用鎖，排了 32 分；`logs/pytest-subset-final-by-file.txt`） |
| Playwright 全套（`fedaad5`；09:53～09:58） | 150 案全過（`single` 132、`profiles-on` 18；4.4 分） |
| packaging unittest（照 CI 的離線暫存 venv）、`validate.py`（ci-venv，不加 `-I`）、`tool_inventory.py`（`fedaad5`） | `Ran 205`、`OK (skipped=5)`；PASS；exit 0 |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`features.py` 對主線 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |

### 19.8 預檢（base 都是 `origin/claude-delivery`）

| 預檢 | 結果 |
|---|---|
| 秘密 `secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | `fedaad5`：OK，0 命中（gitleaks 8.28.0；`f239157..fedaad5` 52 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 `ledger_precheck.py --repo . --base origin/claude-delivery` | `fedaad5`：OK：`runtime-patches.json` 179、`runtime-sources.json` 70、`tool-surface.json` 159 項，0 漂移、0 缺；13 個改到的列管檔都由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔 |

本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 19.9 雙向控制字元

`bidi_scan.py` 逐 commit 查 `origin/claude-delivery..HEAD`，`bidi_merge_check.py` 查合併 commit（和兩個 parent 各比一次的新增行、訊息）與和 `claude-delivery`
不同的每個檔在 HEAD 的全文：`fedaad5` 上 U+202A～202E、U+2066～2069 合計 0 個（52 個 commit 的訊息、新增行與碰過的檔的全文；三個 merge commit 和各自兩個 parent 比的新增行；和主線不同的檔在 HEAD 的全文）；U+200E、U+200F、U+061C 也是 0 個。本筆記的 commit 之後再跑一次，結果記在 PR 說明。

### 19.10 只在 CI 跑的測試、CI 時間

- 新測試都在程序內（`NoProcessSupervisor`＋MockTransport；Playwright 用 LOCAL MOCK），沒有新的 root 案例、沒有起真子程式；要 root 的既有 7 案照第 8 節。
- 新測試的本機時間：`tests/test_restore_review.py` 的 7 個新案例在全套裡合計 1.1 秒（紀錄讀不到那案 0.39 秒最久）；Playwright 新的 2 案約 13 秒（存檔被擋 6 秒、換身分後提示消失 7 秒）。
- `checks` 推估：新基準（HM-13b＋`claude-delivery`）的全套已經比 `f4c7718` 多 HM-12、HM-30、HM-32 的測試（#114 的 CI 2,322 秒）；本片的增量照第 18.4 節，
  S-3 再多不到 5 秒。實際秒數 CI 跑完再補。

### 19.11 commit 與 push

| commit | 內容 |
|---|---|
| `0f3d064` | merge commit：把 HM-13b 的 `fc70404`（已合 `claude-delivery` `165dbaf`）合進本片（第 19.2 節的解法；訊息寫了每個檔怎麼解） |
| `849d9ba` | 契約第 9 節本片的列改成 #122、#123，本片引用 HM-13b 的列一起改；第 10 節加一列；帳本 `restore_lock.py` 重算 |
| `3c3f1b4` | 審查 S-3 的測試與合併後提示的測試（先寫；紅） |
| `0cf5520` | 審查 S-3 的關卡與換身分後清提示（`gateway.py`）；帳本 |
| `e2d28b5` | 面板：存檔被核對關卡擋下時的文字（`api.js`）；帳本 |
| `ba3b63d` | 契約、威脅模型、驗收矩陣、還原手冊 |
| `14e435f` | Playwright：換身分換掉保留的權杖後提示卡消失（先寫；LOCAL MOCK 還沒跟上，紅） |
| `e74d4c0` | LOCAL MOCK：換身分換了預設帳號的權杖時清掉還原提示（轉綠） |
| `fedaad5` | merge commit：再把 HM-13b 的 `369d80b`（已再合 `claude-delivery` `f239157`，HM-33）合進本片（第 19.12 節） |
| 本筆記 | 現行列號 12 處、結論、第 1、14、16 節的狀態、第 19 節 |

- push：一般的 `git push origin feat/ha-multiprofile-hm13c-20261116`（從 `a453b2a` 往前 fast-forward，不 force）。備份分支只在本機。

### 19.12 再合一次：HM-33（PR #115）

- 08:28 HM-33（PR #115）合進 `claude-delivery`：`165dbaf` → `f239157`（Hermes `hermes_cron` 的說明照 PaaS #156、`tool_snapshot.py`、契約第 1.2、10 節、
  `decisions.md` 兩個表尾、驗收矩陣表尾、帳本、`runtime-sources.json`、`tool-surface.json`、`test_output_schemas.py`、黃金回歸的 Hermes 兩個摘要、新測試
  `test_hermes_cron_description.py`；第 9 節沒加列）。HM-13b 先再合一次（`22f5766`）、筆記（`369d80b`）、push；本片 push 前再把它合進來：merge commit
  `fedaad5`（第一個 parent 是本片 `e74d4c0`、第二個是 `369d80b`），本片因此也含 `f239157`。
- 衝突（`resolve_hm13c_merge2.py`）：契約 2 塊（第 1.2 節清單：HM-33 那項在前、本片那項在後；段落：HM-33 那段在前、本片那段在後）、`decisions.md` 2 塊
  （第 1.1 節表、變更紀錄：HM-33 的列在前）；兩邊逐字保留（`both_sides_kept.py`：兩邊加的行都在、沒有新寫的行）。
- 自動合併：`acceptance-matrix.md`、帳本、`tests/test_output_schemas.py`（本片釘 `apps/n8n/run.py`、HM-33 釘 Hermes 的 `server.py`，兩個都在）；帳本另照
  JSON 重組核對（`merge_ledger3.py --check`），和自動合併的結果逐位元相同，66 列、0 漂移。本片沒改黃金回歸，HM-33 改的 Hermes 摘要照收。
- HM-33 沒有在第 9 節加列：本片的 #122、#123 不用改。合併後 `git merge-tree` 對 `origin/claude-delivery` 沒有衝突。
- 合併條件不變：HM-13b（#108）先合併；之後本片再把 `claude-delivery` 合進來（或 rebase），重跑 CI。列號：之後還有片在契約第 9 節 #123 後面加列時，
  後合併的接在當時最後一列後面重排。

## 20. 合併與 S-3 這一輪的獨立審查處理（2026-11-17 10:3x 起）

審查報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-13c-merge-S3.md`（審查對象 `4d654ec`；證據 `wave4/evidence-review-HM-13c-merge-S3/`）。
判定「通過」：必修 0、建議 2（S-1、S-2），選做 1（U03），沒有要使用者決定的題。本輪的 log 與突變：`wave4/evidence-merge-HM-13c/review2/`
（`logs/`、`mutations/`；腳本在 `evidence-merge-HM-13c/tools/` 的 `run_mutations.py.txt`、`review_mutations.py.txt`）。

### 20.1 處理表

| # | 意見（摘要） | 處理 | commit | 證據 |
|---|---|---|---|---|
| S-1 | 還原手冊把 S-3 的 409 寫在「每個帳號都已撤銷」那一段；那時權杖已撤銷，換身分不換權杖、照常存（審查實驗 X1）；紀錄讀不到那段沒提換身分；`profile_runtime.py` 的模組說明只寫 token/rotate | 照契約改正：「每個帳號都已撤銷」那段改成「改 Odoo 網址、資料庫或使用者的存檔不換權杖，照常儲存（核對照樣在等）」；409 改寫到權杖有效而還沒核對的兩種情況（開關關時還原後重新產生、緊急關閉期間重新產生，之後再開通）。紀錄讀不到那段補「會換權杖的 Odoo 換身分存檔也一樣失敗（503）；面板若說存檔結果不明、請重新啟動 add-on，重新啟動沒有用，出路是全部撤銷」。`profile_runtime.py` 的模組說明補「換身分會換權杖時也受關卡管」（只改說明）；這個檔列管，帳本照檔重算 SHA-256（`99e928032658` → `ab0ee2ebafb5`）、說明加一句 | `f7d2f10` | 帳本預檢 0 漂移（第 20.3 節） |
| S-2 | 四個行為沒有測試擋（突變 M03、M08、M09、M13 存活） | 審查實驗改寫成 `tests/test_restore_review.py` 的正式測試：`test_a_failed_identity_change_keeps_the_kept_tokens_notice[stop]`、`[refused]`（X2：換身分失敗時提示不清）、`test_a_revoked_profile_waiting_for_its_review_saves_an_identity_change_as_today`（X1：權杖已撤銷時換身分照常存，預設帳號與 B）、`test_a_new_origin_without_its_password_is_refused_before_the_review_gate`（X3：422 在 409 之前）。在現在的程式上 4 案都綠；在拋棄式複本套審查的突變後都會紅（第 20.2 節） | `67a326e` | `review2/logs/new-tests.log`、`review2/mutations/` |
| U03（選做） | 面板把 S-3 那句也加到 `token/rotate` 的 409 時沒有測試擋 | 做了（簡單）：`restore-review.spec.mjs` 加一案，用 LOCAL MOCK 現成的 `saveStatus`／`saveCode` 讓 rotate 收到 409 `restore_review_required`，斷言文字只有待核對那句、錯誤樣式、伺服器文字不顯示、rotate 只送一次。套 U03 後紅 | `67a326e` | `review2/mutations/U03.txt` |
| 觀察（第 7 節） | 結果不明時不清提示、待核對時清空連線也 409、面板沒有存檔前提醒、提示卡文字沒提換身分 | 審查寫明不用改，照現狀（存檔前提醒已交 HM-29，同 HM-12 面板審查 Q-1） | — | — |

### 20.2 突變（拋棄式複本 `SP:hm13c-mut`：`cp -a` 整個 clone；每次改一處、跑對應的新測試、`git checkout --` 還原並確認樹和改前相同；跑完用完整路徑刪掉複本）

| id | 改了什麼（審查的定義，`review_mutations.py`） | 新測試的結果 |
|---|---|---|
| M03 | 關卡移到新來源檢查之前（409 先於 422） | **紅**：`…refused_before_the_review_gate` |
| M08 | 提示在寫入之前就清 | **紅**：`…keeps_the_kept_tokens_notice[refused]`（`[stop]` 綠：停不下來時還沒走到那一行，同審查） |
| M09 | 提示在 `rebind_identity` 一開始就清 | **紅**：`[stop]`、`[refused]` 兩案 |
| M13 | 改了身分欄位就擋（含權杖已撤銷） | **紅**：`…saves_an_identity_change_as_today` |
| U03 | S-3 那句加到所有 `restore_review_required`（含 `token/rotate`） | **紅**：`a token/rotate held for the restore review keeps the review copy only…`（面板先 build 再跑 single 專案；還原後重 build） |

### 20.3 本輪的檢查（一般使用者 uid 1000；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| 新測試在現在的程式上（`67a326e` 之前的工作樹＝之後的程式；10:38） | 4 案全過（`review2/logs/new-tests.log`） |
| 突變（拋棄式複本，10:39） | M03、M08、M09、M13、U03 都紅（第 20.2 節；`review2/mutations/`） |
| pytest 相關 24 檔（`f7d2f10`；`review2/pytest-subset.txt`：本片與 HM-13b 的還原測試、HM-12 的換身分兩檔、`test_profile_runtime`、HM-10／HM-11 的管理與形狀比對、參數順序、零改寫、`test_output_schemas`、黃金回歸、兩個契約凍結、帳本與秘密預檢工具、工具清單、log 掃描、讀 LOCAL MOCK 的兩檔、HM-33 的說明測試） | 889 案、0 skip，884 過，5 個失敗都是要 root 的 `test_root_*`；85.6 秒；`test_restore_review` 71 案全過（`review2/logs/pytest-subset-by-file.txt`） |
| `npm test`、`npm run build`、`node tests/build-closure.mjs`（`f7d2f10`） | node 94 案全過；build、build closure PASS |
| Playwright 全套（`f7d2f10`） | 151 案全過（`single` 133、`profiles-on` 18；4.5 分）；`restore-review.spec.mjs` 新的 U03 一案在內 |
| packaging unittest（照 CI 的離線暫存 venv）、`validate.py`（ci-venv，不加 `-I`）、`tool_inventory.py`（`f7d2f10`） | `Ran 205`、`OK (skipped=5)`；PASS；exit 0 |
| 秘密預檢、帳本預檢（`--base origin/claude-delivery`）、雙向控制字元 | 本筆記 commit 之後跑，結果記在 PR 說明與回報 |

### 20.4 commit

| commit | 內容 |
|---|---|
| `67a326e` | S-2 的 4 個正式測試、U03 的面板測試 |
| `f7d2f10` | S-1：還原手冊、`profile_runtime.py` 模組說明、帳本 |
| 本筆記 | 第 20 節、結論 |

- push：一般的 fast-forward push（從 `4d654ec`），不 force；PR 不合併。
