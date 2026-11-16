# HA 多帳號 HM-12 面板 provenance：換身分換 token 的提示、新來源要重填秘密的文案與表單規則（2026-11-17）

## 結論

- **獨立審查（2026-11-17）判定通過，必修 0 項、建議 9 項；9 項都處理了**（第 15 節）。S-6 只能做 fixture 那一半：
  真後端形狀比對跑不了 n8n（HM-25 才上帳號 runtime），add-on 那一半本來就有測試（第 3.8 節）。要使用者定的 1 題（Q-1：存檔**前**
  要不要先提醒這次會換 token）照最保守的做法維持現狀，記在第 13 節。
  - S-2：換了 token 之後重新讀取失敗時，提示仍先說換 token，再接失敗的原因（錯誤樣式）；沒換 token 的存檔照今天（第 3.7 節）。
  - S-7：OpenDesign 不顯示秘密說明；withheld 網址的原因寫「伺服器不顯示原網址，無法確認是同一台伺服器」。
  - S-1、S-3：契約 #116、#117 的面板檔改成 `Hui/contracts.js`；PaaS 測試對照表照該檔的規則改產生器規格再重產，只差那一列。
  - S-4、S-5、S-6、S-8：新 spec 從 8 案加到 16 案（額外帳號、改回同來源保留已打的值、前端第二道檢查、伺服器文字不顯示、
    清掉的秘密不再要求、重新讀取失敗兩種、OpenDesign、withheld）；新測試資料的網址改成 `.invalid`。審查存活的 6 個變異
    （R08、R10、R11、R13、R14、F01b）與修正本身的 7 個變異，**13 個全部擋下**（第 6.1 節）。
  - 開關關：`7646f0f` 對本分支的比對多一個「存檔後重新讀取失敗」的動作，**216 個比較 0 差異**（第 7 節）。
- **本片是 HM-12 的面板部分**（主對話決定另開一個 PR；HM-12 後端是 PR #110，已合併）。HM-12 筆記第 11 節的待補 ①～⑦
  都做了（第 4 節逐項）。後端（`Hc/`）一行都沒改；面板要的東西後端都有。
- **開關關時，面板的畫面、請求與提示照今天**：
  - `MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空集合；開關關時伺服器不會送 `token_rotated`、422 新來源、形狀 D＋`token_rotated`。
  - 表單規則只在 `api.profile` 不是 null（伺服器開通）時才有；換 token 的提示只跟著伺服器開通後才有的回應。
  - 照 HM-11 的證明方式（repo 外的比對腳本）：7646f0f 的面板與本分支的面板，12 種設定 × 5 頁 × 動作（含本片碰到的部分編輯、
    整份取代、422、503），**204 個比較 0 差異**（DOM、送出的請求、fixture 收到的紀錄）。把一個開關關時會顯示的差異放進面板，
    同一個腳本找到 56 個差異（腳本有效）。審查修正後多一個動作重跑：216 個比較 0 差異。第 7 節。
  - 既有 9 個 spec 一個字都沒改，`single` 專案照過；`build-closure.mjs` 沒改、照過（N15 斷言）。
- **開通後（目前只有 fixture 與測試會開）**：
  - ① 換身分存檔成功（200＋`token_rotated:true`）：存檔提示後面加「後端身分已變更，這個帳號的 MCP 權杖已換新…請到「連線與權杖」
    顯示並複製新的權杖（或 Claude.ai 連線網址），更新所有用戶端。」；藏起已顯示的權杖、重抓 bootstrap（遮罩與權杖歷史都變了）。
  - 形狀 D（503 `config_apply_failed`＋`saved`＋`token_rotated`，而且回聲是送出時的帳號）：也重抓，錯誤提示把「已存檔、子行程沒起來」
    與換 token 兩件事都說出來。
  - ② 422 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN`（只認 422）：固定文字，不顯示送出的值與回應內容（回應本來就沒有回聲）。
    「修改個別欄位」把網址改到另一個來源（scheme、主機、有效 port）時，那條網址會送去、已存的秘密不能選「保留已儲存憑證」：
    改成必填（選填的可以明確清除）、旁邊寫明原因；改回同一來源就恢復；送出前就擋（`backendPatchPayload` 也擋）。
  - ③ `contracts.js` 的網址↔秘密表（`urlSecrets`＝後端 `identity_fields.URL_SECRETS`，管理 API 的名字）、`identityBound`
    （＝`products.IDENTITY_BOUND`）與來源算法（`urlOrigin`＝`backend_edit.origin` 的讀法）。`tests/test_identity_fields.py`
    加兩個同步測試：兩張表不一致、或任何一個列出的網址兩邊算出的來源不同，就紅。
  - ⑥ 開通、會換 token 的產品（Odoo）的後端存檔回 503 `{"error":"state unavailable"}`：今天的文字後面加「存檔結果不明時請重新啟動
    add-on，之後到「連線與權杖」確認 MCP 網址…」（HM-12 審查 S-7）。503 `request denied` 照今天的文字。
  - ⑦ `ETag`：照 HM-11 的寫法（存檔後重新讀取，下一次存檔用讀到的設定版本，等於回應的 `ETag`），不另加規則；測試釘住
    「換身分後的下一次存檔」與「形狀 D 之後的重啟」都帶新版本。
- **⑤ fixture 照回應表回答（只在開通模式）**，而且**和真後端一致**：`profile-api-cases.json` 加 4 個情境 10 案（換身分、只換密碼、
  新來源 422、同來源換路徑、整份取代、清空、三種故障），expect 錄自真的 8099 管理 app（`tests/test_panel_profile_api_shapes.py`，
  14 個情境全過）；`profile-api-parity.spec` 讓 fixture 跑同一份案例，14 個情境全過。
- **一個要主對話知道的取捨**：Playwright 的 `profiles-on` 專案略過 `partial-settings.spec.mjs` 的兩案（`grepInvert`，只改
  `playwright.config.mjs`，spec 沒改）。這兩案把 n8n 的網址改到別台卻保留已存金鑰；開通後這正是 DQ-40 ⑨ 要擋的事（面板要求重填、
  add-on 回 422），不可能「原封不動照過」。兩案在 `single` 專案照原樣跑（開關關照今天），開通的版本寫在新 spec。第 3.6 節。
- **先寫測試**（第一次交出時）：`7c418f2` 只有測試，在 7646f0f 的面板與 fixture 上：node 88 案 7 案紅、新 spec 8 案 7 案紅、parity 新 4 個情境紅、
  兩個 Python 同步測試紅；之後 fixture（`805c77b`）與面板（`3c0f539`）讓它們轉綠。自我檢查補的回聲案例也先紅（`f5ebdb3`）再修
  （`61357e3`）。只守現有行為的斷言用臨時突變證明：**21 個突變全部擋下**（面板與 fixture 18 個、Python 同步測試 3 個）。第 5、6 節。
- **本機（審查修正後，第 8.4 節）**：node 88 案全過；`build-closure` PASS；Playwright 135 案全過（`single` 117、`profiles-on` 18），
  4.0 分鐘；pytest 子集 23 檔 468 案全過、0 skip；`packaging/validate.py` PASS；packaging unittest Ran 203、OK（skipped=5）；`tool_inventory.py` exit 0。
  第一次交出時：Playwright 127、pytest 子集 22 檔 465（第 8 節）。
- **兩個預檢**：秘密預檢 0 命中、帳本預檢 OK（第 11 節）。commit 與檔案都沒有雙向控制字元。
- **還沒做**：`checks` 秒數開 PR 後補；push、開 PR 由主對話做。獨立審查已做（第 15 節）。
- 證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-12-panel/`（`logs/` 紅綠與本機檢查的 log；`compare/` 第 7 節；
  `mutations/` 第 6 節；`tools/` 用到的腳本，副檔名多加 `.txt`；`screens/` 開通時部分編輯的畫面，1440 與 320 寬，320 寬沒有橫向捲動）。
  用過的 `/tmp/ha-mp-XXXXXX` 記在 `tmpdirs.txt`，都已用完整路徑刪掉。審查修正的證據在 `wave4/evidence-fix-HM-12-panel/`（第 15 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-12 的面板部分（計畫 §12.3 HM-12「做法」最後一項：`Hui/app.js` 的 `token_rotated` 提示、422 文案；HM-12 筆記第 11 節待補 ①～⑦） |
| 分支 | `feat/ha-multiprofile-hm12-panel-20261117`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `7646f0f`（HM-00～HM-11、HM-13a、HM-14、HM-17、HM-20、HM-31、HM-09 追補、#100、HM-12 後端 PR #110 都已合併） |
| 依據 | HM-12 筆記第 11 節（回應表）、第 17 節（審查 S-7）、第 18.6 節；審查報告 `artifacts/…/wave4/review-HM-12.md`；HM-11 筆記（開關關逐位元、build-closure N15、fixture 兩種模式、parity spec）；契約第 3.1、4.1 節與第 9 節 #113～#115；`decisions.md` DQ-05、DQ-40 (a) ⑨ |
| 對齊的 PaaS | pin `69ac425`；本機唯讀 repo 的 `origin/main` 寫這份筆記時是 `7087280`，審查修正時是 `48f394d`（第 9 節；只用 `git log`／`show`／`grep`／`diff --stat`，沒有 fetch、checkout） |
| 獨立審查 | `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-12-panel.md`（判定通過；處理見第 15 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hui/contracts.js`（列管） | `urlSecrets`、`identityBound`、`urlOrigin`、`newOriginSecrets`；`backendPatchPayload(bootstrap, selections, values, switchedOn = false)`：`switchedOn` 時擋「網址改到別的來源卻保留已存秘密」。預設值照今天 |
| `Hui/api.js`（列管） | `TOKEN_ROTATED`（文案）；`CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 只認 422、固定文案；錯誤回應：形狀 D＋`token_rotated`（而且回聲是送出的帳號）標 `tokenRotated`、文案加換 token 那句；503 `{"error":"state unavailable"}` 標 `stateUnavailable`，`mutate` 對開通、會換 token 的產品的後端存檔加 S-7 提示 |
| `Hui/app.js`（列管） | `savedNotice`（200＋`token_rotated` 的提示）；`followUp` 對形狀 D＋`token_rotated` 重新讀取再提示；`reload(message, error)`；部分編輯：開通時的說明、每個秘密的原因說明（必填時連到欄位的 `aria-describedby`）、`requireMovedSecrets`、把 `switchedOn` 交給 `backendPatchPayload` |
| `packages/mcp-admin-ui/fixtures/server.mjs` | 只在開通模式：新來源 422（全部產品）；Odoo 換身分換 token（下一個字母、遮罩、歷史）；`profiles.rebindFault`（`stop`、`write`、`start`，只用一次）；`saveCode` 配 `saveStatus`。開關關的回應不變 |
| `packages/mcp-admin-ui/playwright.config.mjs` | `profiles-on` 專案略過 `partial-settings` 兩案（第 3.6 節） |
| `packages/mcp-admin-ui/tests/profiles.test.mjs` | HM-12 的 7 案；「面板送出的請求＝錄下的案例」那案多比兩種後端存檔 |
| `packages/mcp-admin-ui/tests/browser/backend-identity.spec.mjs`（新） | 8 案（第 4 節） |
| `packages/mcp-admin-ui/tests/profile-api-cases.json`、`tests/browser/profile-api-parity.spec.mjs` | 4 個情境 10 案；setup 的 `backend_edit`、extra 的 `connection`、`fault` 對到 fixture |
| `tests/test_panel_profile_api_shapes.py` | 支援 extra 的已存連線（核對真後端存的就是案例寫的）、`fault`（照 `test_odoo_identity_rotation.py` 的 `Journal`、`record_writes` 在 B 上布置）；案例送出的密碼也交給 log 掃描 |
| `tests/test_identity_fields.py` | 兩個同步測試：網址↔秘密表與 `identityBound`；來源算法逐案（19 個網址） |
| `docs/provenance/runtime-patches.json` | 3 個列管檔的 SHA-256 照實際內容重算，`change` 各補一段（沒寫契約列號，HM-12 審查 S-6 的做法） |
| `docs/multi-profile/contract.md` | 第 9 節 #116、#117，說明段一行、第 10 節一列 |
| `docs/multi-profile/acceptance-matrix.md` | 登記新 spec；`test_identity_fields.py` 那列補一句 |
| `packages/mcp-admin-ui/README.md` | 新一節「換後端身分與新來源（HM-12）」；`profiles-on` 略過兩案的原因 |
| 本筆記 | 新增 |

審查修正（第 15 節）另外改的：

| 檔 | 改了什麼 |
|---|---|
| `Hui/app.js`（列管） | `savedNotice` 換成 `reloadSaved`／`reloadRotated`（S-2）；形狀 D 的 `followUp` 用 `reloadRotated`；表單上方的秘密說明只在網址帶秘密的產品（S-7 a）；withheld 網址的原因（S-7 b） |
| `docs/provenance/runtime-patches.json` | `app.js` 的 SHA-256 照實際內容重算，`change` 補一段（`api.js`、`contracts.js` 這次沒改） |
| `packages/mcp-admin-ui/tests/browser/backend-identity.spec.mjs` | 8 案 → 16 案；n8n 那案多一次存檔（S-6）；網址改成 `.invalid`（S-8） |
| `packages/mcp-admin-ui/tests/profiles.test.mjs` | 形狀 D 案的回應加伺服器文字（S-5）；n8n 的網址改成 `.invalid`（S-8） |
| `docs/multi-profile/contract.md` | #116、#117 的 HA 欄（S-1，另補 S-2、S-4、S-5、S-7 的行為）；第 10 節一列 |
| `docs/multi-profile/paas-test-mapping.md` | `connection-secret-clear-browser.py` 那一列，由 HM-00 產生器改規格後重產（S-3） |
| `docs/multi-profile/acceptance-matrix.md`、`packages/mcp-admin-ui/README.md` | 記下本次補的行為與測試 |
| repo 外 | `artifacts/…/wave0/hm00-check/paas_mapping_spec.py` 與同目錄 `SHA256SUMS`（S-3；改前的原檔在 `evidence-fix-HM-12-panel/tools/`） |

沒改：`packages/mcp-admin-core/`（後端）、`apps/`、`addons/`、任何版號、CHANGELOG、`upgrade-notes.yaml`、`.github/`、
`tests/conftest.py`、`packaging/`、`build-closure.mjs`、既有 9 個 spec、`Hui/profiles.js`、`Hui/operation-identity.js`、`Hui/styles.css`、
`MULTI_PROFILE_PRODUCTS`（空集合）、`decisions.md`、威脅模型。審查修正也沒改 `Hui/api.js`、`Hui/contracts.js`、fixture、
`playwright.config.mjs`、`profile-api-cases.json`、`profile-api-parity.spec.mjs`、任何 Python 測試。

## 3. 設計重點

### 3.1 換身分換 token（①、⑦）

- 回應只帶旗標、不帶文字（契約 #113）。面板依 `token_rotated===true` 自己提示，不管是哪個產品（之後 HM-22、HM-24 開通 Nextcloud、
  Hermes 也一樣）。
- 200：`reloadSaved`（第一次交出時是 `savedNotice`，第 3.7 節）在原本的存檔提示後面加 `TOKEN_ROTATED`；`reload` 先 `hideToken()`（清掉畫面上的權杖、計時器與進行中的顯示），
  再抓 bootstrap、重畫。存檔頁本身不顯示權杖；這一步保證「已顯示的權杖」在任何狀況都藏起來，新權杖只能再按「顯示權杖」取得。
- 形狀 D：`exchange` 只在 503＋`config_apply_failed`＋`saved:true`＋`token_rotated:true`＋回聲是送出的帳號時標 `tokenRotated`；
  `followUp` 在 `task` 的鎖放開後重新讀取，再用錯誤樣式顯示兩件事。回聲不是送出的帳號時照今天的 `config_apply_failed` 文字
  （I12：別的帳號的回答一點都不用；其他錯誤回應的回聲照 HM-11 的規則仍不比）。
- ⑦ 面板今天就不讀存檔回應的 `ETag`：存檔後重新讀 bootstrap，下一次存檔帶讀到的 `configuration.revision`。換身分回應的 `ETag`
  就是下一次 bootstrap 的（HM-12 審查 S-3 的測試），所以結果相同。沒有另加規則；新 spec 釘住換身分後第二次存檔的 If-Match 是
  新版本（`c1-…2`），形狀 D 之後「重新啟動子行程」的 If-Match 也是新版本。

### 3.2 新來源要重填秘密（②、③）

- 表（`urlSecrets`）用管理 API 的名字（n8n 是 `url`、`key`、`mcp_access_token`），就是 `backend_edit.url_secrets` 的輸出。
- 來源（`urlOrigin`）照後端 `backend_edit.origin`（Python `urlsplit`）的讀法：scheme 與主機轉小寫、IPv6 去括號、zone 照寫、沒寫 port
  用 80／443；其他都不正規化（結尾的點、IPv4 的其他寫法、非 ASCII 主機與 xn-- 形式都算不同），和後端一樣偏安全。後端讀不了的 port
  回 null（不判定，交給網址驗證擋）。同步測試逐案比 19 個網址。
- 判定（`newOriginSecrets`）：網址選「提供新值」、新值是合法網址、來源和已存的不同 → 那條網址會送去、而且已存（`secret_set`
  是 true）的秘密都要帶。網址沒存過（第一次設定）、清空、還不是合法網址：不用帶。伺服器不顯示值（withheld）的網址：一律當成換了
  （面板不知道原來的來源，偏安全）。同一個來源只換路徑：不用帶（DQ-40 ⑨ 的範圍；已知限制，威脅模型第 3 節）。
- 表單（`requireMovedSecrets`，只在開通時掛）：網址欄位每次改動重算。要帶的秘密：停用「保留」選項；原本是「保留」就自動改成
  「提供新值」並標記；欄位必填、`aria-describedby` 指到說明；說明顯示。不再需要時：恢復「保留」選項；自動改的、而且沒打字的
  改回「保留」；使用者自己選的照留。送出時 `backendPatchPayload(…, true)` 再擋一次。
- 仍收到 422（例如 withheld 以外的情況兩邊算法不一致）：固定文字、打過的秘密照今天清掉、網址草稿留著。

### 3.3 503 兩種（⑥）

- 503 `request denied`（停不下舊子程式，什麼都沒存）：照今天的 503 文字。
- 503 `state unavailable`：`exchange` 只認這個固定值（標 `stateUnavailable`），`mutate` 只在開通（`profile` 不是 null）、
  `backend` 或 `backend/patch`、產品在 `identityBound` 時加提示。開關關、別的操作、不會換 token 的產品：照今天。
- 提示的寫法是條件句（「若這次換了後端身分，權杖可能已換新」）：同一個 503 也可能是「什麼都沒寫」，面板分不出來。

### 3.4 fixture（⑤）

- 新行為都在 `switchedOn()` 之後；`addProfile` 只在開通時呼叫（extra 現在可以帶 `connection`）；預設帳號多記一個內部的
  `identity`（不出現在任何回應）。開關關的回應逐位元相同（第 7 節的比對也包含 fixture 收到的紀錄）。
- 網址↔秘密表與來源寫在 fixture 自己裡，不引用面板的（面板錯了，fixture 不會跟著錯；兩邊各自由同步測試與 parity 綁到真後端）。
- 故障只用一次：`delete config.profiles.rebindFault`。`start` 時把 `applyState` 設成 `failed`，面板重新讀取後看得到。

### 3.5 開關關

- `partialBackendCard` 只在 `api.profile !== null` 時加說明、說明元素與監聽；`el()` 會略過 null 的子元素，所以 DOM 相同。
- `backendPatchPayload` 第 4 個參數預設 false。`reload(message, error = false)` 的預設等於今天的 `notice(message)`。
- 新 spec「switched off: moving the URL keeps every secret choice as before…」在開關關時逐項確認：沒有說明、沒有原因元素、沒有標記、
  「保留」照常可選（突變 M01、M15、M16 都擋下）。審查修正後另有「switched off, or a save that rotated nothing…」（第 3.7 節）。

### 3.6 `profiles-on` 專案略過 `partial-settings` 兩案

- HM-11 讓四個既有 spec 在 `profiles-on` 專案（fixture 預設開通）原封不動再跑一次。`partial-settings.spec.mjs` 的
  「partial URL edit sends only URL…」與「partial edit conflict retains draft…」把 n8n 網址從 `http://old.test` 改到別台，
  已存的金鑰選「保留」。開通後這是 DQ-40 ⑨ 要擋的：面板送出前要求重填（本片）、add-on 回 422（HM-12 後端）。
- 做法：`playwright.config.mjs` 的 `profiles-on` 專案加 `grepInvert`，只略過這兩案；spec 一個字都沒改。這兩案在 `single` 專案照跑
  （開關關照今天）。開通的版本在 `backend-identity.spec.mjs`：「a URL moved to another server asks again…」（重填金鑰、清掉 MCP token
  後存檔；同一台換路徑沿用）與「…the conflict keeps the draft…」。
- 這是對 HM-11「四個 spec 開通時原封不動照過」的一個例外，原因是開通後的規則本來就不同；請主對話與審查者知道。

### 3.7 審查修正：重新讀取失敗時的換 token 說明（S-2）、說明文字（S-7）

- S-2：`savedNotice` 換成 `reloadSaved(text, result)`。回應沒有 `token_rotated:true` 時就是 `reload(text)`（開關關時永遠走這條，
  和 `7646f0f` 相同）；有的時候走 `reloadRotated(`${text} ${TOKEN_ROTATED}`)`。形狀 D 的 `followUp` 也改用 `reloadRotated(error.message, true)`。
- `reloadRotated`：`reload` 失敗時，把原本要顯示的提示接在錯誤文字前面，再丟出**同一個**錯誤（類別、狀態碼、代碼都不變），
  所以 `fail` 與 `followUp` 照舊處理：
  - 連線中斷或逾時（E1、E2）：錯誤樣式顯示「提示＋連線中斷或逾時；無法確認操作結果。請重新整理狀態後再操作。」；
  - 401／403：照舊換成拒絕頁，文字前面多了提示；回聲不符：照 HM-11 重新開啟，提示帶著；
  - 帳號已不存在：照舊切回預設帳號（那個帳號的權杖已撤銷，不需要換 token 的提示）；晚到的回應：照舊丟掉；
  - 不是 `UiError` 的例外：換成「提示＋操作未完成。請重新整理狀態後再試。」（`fail` 原本的文字）。
  - `reload` 第一步就 `hideToken()`，讀任何東西之前畫面上的權杖已藏起；`fail` 也會再藏一次。
- 沒換 token 的存檔（開關關，或開通後只換密碼）重新讀取失敗時，照今天只顯示錯誤（審查也說今天一樣會蓋掉「已儲存」；
  本片不改，新 spec 一案守住，突變 S2-M3）。
- S-7 (a)：表單上方「不會沿用已儲存的密碼或金鑰」那段，只在 `urlSecrets[產品]` 有秘密時才加（OpenDesign 的網址不帶秘密）。
- S-7 (b)：伺服器不顯示原值（`backend_edit.withheld_fields`）的網址，它帶的秘密的原因說明改成「伺服器不顯示原網址，無法確認是同一台
  伺服器：請重新輸入（或明確清除），不會沿用已儲存的憑證。」。判定本身不變（withheld 一律當成換了）。
  - 沒改的兩處：送出時第二道檢查（`backendPatchPayload`）的文字仍是「網址改到另一台伺服器時不會沿用已儲存的憑證：…」，只有把
    「保留」強制打開才看得到；表單上方說明的「只改路徑時沿用已儲存的憑證」不適用 withheld 網址，原因寫在欄位旁。
- 開關關：`partialBackendCard` 的說明與原因元素照舊只在 `api.profile !== null` 時才有；存檔回應沒有 `token_rotated`，走 `reload(text)`。
  第 7 節的比對另外加了「存檔後重新讀取失敗」的動作，0 差異。

### 3.8 S-6：「沒存過的秘密不用帶」為什麼沒有真後端案例

- 這種狀態（網址有值、它帶的秘密沒存）只有 n8n 碰得到：其他產品的秘密都是必填（`Hc/products.py` 的 `Credential`），Hermes 的
  Dashboard 網址、使用者、密碼三個一組（`HermesConnection.dashboard_complete`）。n8n 的 MCP Access Token 是選填。
- n8n 到 HM-25 才上帳號 runtime（`tests/multi_profile_runtime.py` 的 `SWITCHABLE` 沒有 n8n）：真後端形狀比對加 n8n 情境，
  `run_product.py` 的 `TOOLS['n8n']` 直接 `KeyError`（`evidence-fix-HM-12-panel/handoff-HM-25/shapes-n8n-keyerror.log`）。所以這個情境退回、
  不 commit；形狀比對與 `profile-api-cases.json` 沒有改。
- add-on 這邊的同一條規則已有測試：`tests/test_new_origin_secret.py::test_a_secret_brought_as_null_or_never_stored_is_not_carried`
  （`never` 那段：MCP token 沒存、網址換 port、只帶 key → 200；開通用 monkeypatch，HM-12 後端）。
- fixture 這邊：新 spec「a URL moved to another server asks again…」多一次存檔：MCP token 清掉之後再把網址換到別台，表單只要求
  API 金鑰（MCP token 照舊「保留未設定狀態」），fixture 照收。突變 F01b（fixture 連沒存的也要求）由這案擋下。
- 情境草稿留給 HM-25：`evidence-fix-HM-12-panel/handoff-HM-25/new-origin-unset-secret.scenario.json`（`expect` 是預期值、還沒錄；
  n8n 上帳號 runtime 後，照 HM-11 的方法在真後端錄、fixture 跑同一份）。

## 4. HM-12 筆記第 11 節待補 ①～⑦ 的處理

| # | 待補 | 處理 | 測試 |
|---|---|---|---|
| ① | `token_rotated` 提示與藏 token、重抓 | 做了：200 與形狀 D 都提示、重新讀取（`hideToken` 在 `reload` 裡）；形狀 D 要回聲是送出的帳號。審查後：重新讀取失敗時提示仍在（S-2）；伺服器文字不顯示有測試（S-5） | node「a save that rotated the token…」「shape D…」；Playwright「an identity change rotates the token…」（遮罩、歷史、新權杖、舊權杖不在頁面）、「on an additional profile…」（只換那個帳號的；整份取代）、「…shape D…」；審查後「a rotated token is said even when the new state cannot be read again…」「switched off, or a save that rotated nothing…」「server text in an answer that says token_rotated…」 |
| ② | 422 文案與表單的必填規則 | 做了：只認 422、固定文字；部分編輯在來源改了時把該網址的已存秘密改成必填，改回恢復。審查後：額外帳號、改回同來源保留已打的值、前端第二道檢查、清掉的秘密不再要求都有測試（S-4、S-6）；OpenDesign 不顯示說明、withheld 網址的原因（S-7） | node「the new-origin 422…」「switched on, a URL moved…」；Playwright「a URL moved to another server asks again…」「…stale revision…」「a save the add-on refuses as a new origin (422)…」；審查後「on an additional profile a URL moved…」「a secret typed for another server stays typed…」「keep forced back on…」「…OpenDesign…」「a URL the server withholds…」 |
| ③ | `contracts.js` 的網址↔秘密對照與同步測試 | 做了：`urlSecrets`、`identityBound`、`urlOrigin`；`tests/test_identity_fields.py` 兩個同步測試（照 `test_the_connection_page_fields_and_kinds_agree` 的作法用 node 讀面板） | 同步測試在舊面板上紅（`identityBound`、`urlOrigin` 不存在）；突變 P1～P3 都擋下 |
| ④ | `profiles.test.mjs`／瀏覽器測試補這幾種回應 | 做了：200＋`token_rotated`、形狀 D＋`token_rotated`、422（沒有回聲）、503 兩種 | node 7 案＋請求比對 2 項；新 spec 8 案（審查後 16 案） |
| ⑤ | fixture server 照上表回 | 做了（只在開通模式）；4 個情境錄自真後端，fixture 與真後端都照過 | `test_panel_profile_api_shapes.py`、`profile-api-parity.spec`（各 14 個情境） |
| ⑥ | 503 state unavailable（結果不明）補「重啟 add-on 後到 Tokens 確認網址，可能已換」 | 做了：只在開通、會換 token 的產品的後端存檔；request denied 照今天 | node「…503 state unavailable…」（含開關關、別的操作、EMQX 照今天）；Playwright「a failed identity change…」 |
| ⑦ | 換身分回應的 `ETag` 照用（照 HM-11 的寫法） | 照 HM-11：重新讀取後用讀到的版本，不另加規則 | Playwright 第一案的第二次存檔 If-Match、形狀 D 那案的重啟 If-Match |

## 5. 先紅後綠

| 檢查 | 紅 | 綠 |
|---|---|---|
| node（`7c418f2` 的測試＋7646f0f 的面板） | 88 案：81 過、7 案失敗（都是 HM-12 新案：`TOKEN_ROTATED` 不存在、422 是通用文字、503 沒有提示、`urlSecrets`／`urlOrigin`／`newOriginSecrets` 不存在） | `3c0f539` 起 88 案全過 |
| 新 spec（同上，`single`） | 8 案：7 案失敗（提示沒有換 token 那句、沒有故障回應、沒有必填規則、422 是通用文字）；開關關那案過（守現有行為，紅由突變證明） | `3c0f539` 起 8 案全過 |
| parity（`7c418f2` 的案例＋7646f0f 的 fixture） | 14 個情境：舊的 10 個過、新的 4 個失敗 | `805c77b` 起 14 個情境全過 |
| Python 同步測試（`7c418f2` 的拋棄式複本，`git archive`；共用鎖下跑） | `test_identity_fields.py` 17 案：15 過、2 案失敗（node 讀不到 `identityBound`、`urlOrigin`） | 第 8 節 |
| 真後端形狀比對 | 不會紅：expect 就是真後端的形狀（HM-11 的作法）。`7c418f2` 的內容在 clone 裡先跑過：14 個情境全過、3.2 秒（03:19）。拋棄式複本沒有各產品的 venv，執行環境起不來，這個檔在複本裡的結果不算 | 第 8 節 |
| 回聲案例（`f5ebdb3` 的測試＋`3c0f539` 的面板） | 88 案 1 案失敗（形狀 D 的回聲是別的帳號，卻說這個帳號的 token 換了） | `61357e3` 起 88 案全過 |
| 審查修正（`325f862` 的測試＋`4fbf530` 的面板，`single`） | 新 spec 15 案 3 案紅：S-2（提示只剩「連線中斷或逾時…」）、S-7 (a)（OpenDesign 的表單有「密碼或金鑰」）、S-7 (b)（原因寫「網址改到另一台伺服器」）；其他 12 案（守現有行為的 S-4、S-5、S-6）照過；node 88 案全過 | `04f0654` 起 15 案全過；之後 `19dcc52` 加的 1 案守現有行為（修正前後都過），由突變 S2-M3 證明 |

## 6. 臨時突變

都在拋棄式複本裡（`git archive` 出 `b5b5b29`，node_modules 用連結；之後的程式只多了形狀 D 的回聲條件與說明），一次改一處
（原文必須剛好出現一次），改到 `src/` 就重 build，
跑要擋它的測試，跑完還原並比 SHA-256。工具與 log 在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-12-panel/`
（`tools/mutate.mjs.txt`、`tools/py_mutate.py.txt`、`mutations/`）。

| # | 突變 | 結果 | 擋下的測試 |
|---|---|---|---|
| M01 | 表單規則開關關時也有 | 擋下 | 新 spec「switched off…」（出現說明） |
| M02 | S-7 提示開關關時也有 | 擋下 | node「…503 state unavailable…」 |
| M03 | S-7 提示對任何存檔都有 | 擋下 | 同上（policy） |
| M04 | S-7 提示對任何產品都有 | 擋下 | 同上（EMQX） |
| M05 | 形狀 D 不看狀態碼 | 擋下 | node「shape D…」（500 那案） |
| M06 | 形狀 D 不看 `saved` | 擋下 | 同上 |
| M07 | 新來源代碼不看狀態碼 | 擋下 | node「the new-origin 422…」（400 那案） |
| M08 | 形狀 D 不重新讀取 | 擋下 | 新 spec「…shape D…」（套用狀態還是 applied） |
| M09 | 200 不說 token 換了 | 擋下 | 新 spec 第一、二案 |
| M10 | 改回同一來源不恢復「保留」 | 擋下 | 新 spec「a URL moved…」 |
| M11 | 來源忽略寫出來的 port | 擋下 | node 來源與必填兩案 |
| M12 | 表漏了 n8n 的 MCP token | 擋下 | node 表與必填兩案 |
| M13 | withheld 的網址當成沒換 | 擋下 | node 必填那案 |
| M14 | fixture 的 422 開關關時也有 | 擋下 | `partial-settings` 第一案（`single`） |
| M15 | 說明開關關時也有 | 擋下 | 新 spec「switched off…」 |
| M16 | 原因元素開關關時也有 | 擋下 | 同上（元素數 2，應為 0） |
| M17 | fixture 的停不下帶回聲與 ETag | 擋下 | parity `identity-stop-fails` |
| M18 | fixture 換身分卻不換 token | 擋下 | 新 spec 第一案（遮罩） |
| P1 | 面板的表漏 n8n 的 MCP token | 擋下 | `test_the_panels_url_secrets_and_identity_bound_products_are_the_servers` |
| P2 | 面板多綁一個產品（nextcloud） | 擋下 | 同上 |
| P3 | 面板的來源去掉主機結尾的點 | 擋下 | `test_the_panels_origin_is_the_servers` |

形狀 D 的回聲條件沒有另做突變：拿掉它就是 `3c0f539` 的程式，第 5 節最後一列就是它的紅。

### 6.1 審查修正的臨時突變（`git archive 19dcc52` 的拋棄式複本，node_modules 用連結；工具 `evidence-fix-HM-12-panel/tools/mutate.py`）

一次改一處（原文剛好出現一次）、改 `src/` 就重 build、跑要擋它的測試、還原並比 SHA-256、再 build 回來。log 在 `mutations/js/`，
總表 `mutations/js/summary.json`。**13 個全部擋下**。

| # | 突變 | 擋下的測試 |
|---|---|---|
| R08 | 送出時不傳 `switchedOn`（審查存活） | 新 spec「keep forced back on…」 |
| R10 | 表單規則只在預設帳號（審查存活） | 新 spec「on an additional profile a URL moved…」 |
| R11 | 改回同來源時連已打的秘密也丟掉（審查存活） | 新 spec「a secret typed for another server stays typed…」 |
| R13 | 200 換 token 的提示改顯示伺服器的 `message`（審查存活） | 新 spec「server text in an answer…」 |
| R14 | 形狀 D 的提示改顯示伺服器的 `message`（審查存活） | node「shape D…」、新 spec「server text in an answer…」 |
| F01b | fixture 連沒存的秘密也要求（審查存活） | 新 spec「a URL moved to another server asks again…」（第三次存檔） |
| S2-M1 | `reloadRotated` 不把提示接上（只剩錯誤） | 新 spec「a rotated token is said even when…」 |
| S2-M2 | 形狀 D 的 `followUp` 改回 `reload` | 同上（形狀 D 那段） |
| S2-M3 | 每個存檔都走 `reloadRotated`（沒換 token、開關關也留著提示） | 新 spec「switched off, or a save that rotated nothing…」 |
| S2-M4 | 不看 `token_rotated`（一律 `reload(text)`） | 新 spec 5 案（第一案、額外帳號、重新讀取失敗、伺服器文字…） |
| S7-M1 | 秘密說明每個產品都顯示 | 新 spec「…OpenDesign…」 |
| S7-M2 | withheld 網址的原因照舊寫「網址改到另一台伺服器」 | 新 spec「a URL the server withholds…」 |
| S7-M3 | 每個原因都寫「伺服器不顯示原網址」 | 新 spec「a URL moved to another server asks again…」 |

## 7. 開關關時面板不變的比對（repo 外的腳本，不 commit：`evidence-HM-12-panel/tools/compare.mjs.txt`）

- 基準＝`git archive 7646f0f` 取出的 `packages/mcp-admin-ui` 與 `tests/owned_network.cjs`，自己 build；新版＝本分支。兩個 fixture
  各起一個，用同一個 Chromium。方法照 HM-11 筆記第 5.3 節。
- 設定：HM-11 的 6 種，加本片的 6 種（Odoo 已設定、n8n 已設定、Odoo 存檔回 422、Odoo 存檔回 503、n8n 存檔回 422、Hermes 已設定）；
  5 頁；每頁「不動」與「重新整理狀態」，連線與權杖頁加「顯示權杖」「重新產生」，後端頁加五個動作（網址打成別台不存、網址改到別台
  保留秘密存檔、改帳號存檔、改秘密存檔、整份取代）。
- 比 `document.body.innerHTML`、fixture 的 `calls`（操作識別碼換成固定字）、瀏覽器送出的每個 `/api/` 請求的方法、路徑與標頭名稱集合。
- 結果：`b5b5b29` 上 204 個比較 0 差異（03:39）；最後的程式（`aab9b12`，03:54）再跑一次，仍是 0 差異。
- 腳本有效：另一支探查腳本確認後端頁的動作真的存檔（fixture 收到 `backend/patch` 的 url、username、password、key 與 `backend`），
  兩邊的提示相同；在複本裡把「開關關時也顯示說明」（突變 M15）放進面板，同一個比對找到 56 個差異。
- 這個腳本只在本機跑、不在 CI。CI 的守門是新 spec 的開關關那案（M01、M15、M16）與既有 9 個 spec（`single`）。
- **審查修正後重跑**（`evidence-fix-HM-12-panel/tools/compare.mjs` 是作者的腳本多加一個動作 `lostReload`：部分編輯存檔後，之後的
  bootstrap 都斷線，比對重新讀取失敗時的畫面）：`7646f0f` 自己 build（`dist/assets/app.js` `674a1d95…`）對本分支（`b0f7e7ad…`），
  **216 個比較 0 差異**（`compare/switched-off-compare.log`）。放進突變 S2-M3（每個存檔都走 `reloadRotated`），同一個比對找到 4 個差異，
  都在 `lostReload`（`compare/switched-off-compare-sensitivity-S2-M3.log`：新動作有效）。開關關那案與「switched off, or a save that rotated
  nothing…」是 CI 的守門。

## 8. 本機檢查（2026-11-17，一般使用者 uid 1000；`ha_env.sh` 的 TMPDIR，每次跑完用完整路徑刪掉；pytest 都排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 88 案全過、約 0.23 秒（基準 81 案） |
| `npm run build`＋`node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`；`--output` 與 `UI_EVIDENCE_DIR` 放 TMPDIR） | 127 案全過（`single` 109、`profiles-on` 18），3.9 分鐘（`8ac163f`，03:50～03:54，開始時工作樹乾淨）；基準 7646f0f：117 案（97／20）、3.6 分鐘。之後的 `c928058` 只改說明：重新 build 的 `dist/assets/app.js`、`app.css` 和 `8ac163f` 的逐位元相同（SHA-256 `38806022…`、`c8b43515…`），node 88 案、build-closure 再跑照過 |
| 新 Playwright 案 | `backend-identity.spec` 8 案逐案加總約 17.2 秒；parity 新 4 個情境約 0.5 秒；`profiles-on` 少跑的兩案約 3.1 秒 |
| 真後端形狀比對 `tests/test_panel_profile_api_shapes.py` | 14 個情境全過、3.2 秒（03:19，新案例與 fault 支援的內容） |
| pytest 子集 22 檔（見下；正式 conftest、`-rfEs`） | 465 案全過、0 skip、93.2 秒（`dd61760`；04:03 排進共用鎖，04:26 拿到，04:28 跑完；跑的時候工作樹只多本筆記這個未追蹤的檔） |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15） | PASS |
| packaging unittest（CI 的做法：離線暫存 venv，`uv sync --frozen --no-dev` 再裝 `requirements-ci.txt`） | Ran 203、OK（skipped=5） |
| `scripts/tool_inventory.py` | exit 0 |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`packages/mcp-admin-core/`、`apps/`、`packaging/`、`build-closure.mjs` 與既有 9 個 spec 對 7646f0f 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |

pytest 子集的 22 檔：本片改的 `test_identity_fields`、`test_panel_profile_api_shapes`；讀面板原始碼的 `test_b2_odoo_policy`、
`test_batch2_admin`、`test_n8n_selectors`、`test_writes_default_on`；owned UI 工具 `test_owned_browser`、`test_owned_browser_ipc`、
`test_owned_browser_redirect`、`test_owned_ui`、`test_admin_ui`、`test_owned_ports_bearer`；HM-01 黃金回歸與兩個契約凍結；帳本
`test_tool_inventory`、`test_ledger_precheck`；HM-12 後端 `test_odoo_identity_rotation`（形狀比對引用它的 `Journal`）、
`test_new_origin_secret`、`test_saved_destinations`；HM-10 `test_profile_admin_api`、`test_admin_pipeline_matrix`。
全套 pytest 沒跑：本片沒有改任何正式的 Python，也沒有改 pytest 讀的面板以外的檔（HM-11 的作法）；以 CI 為準。

### 8.1 只在 CI 跑的測試

- 本片新增與改過的測試都在本機跑過、全過，沒有只在 CI 跑的新測試。
- 已知要 root、本機一定失敗的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5）不在
  本片的子集裡；CI 以 root、0 skip 跑全套。
- Node：本機 v26.12.1（`ha_env.sh`）；pytest 裡用 `/usr/bin/node` 的兩個同步測試，本機是 v22.23.3、CI 是 v26.12.1（unit.sh 前一步
  把 `/usr/bin/node` 指到 v26），寫法兩邊都能跑。Playwright 1.61.1（Chromium headless shell 149，照 CI 用 `npm run browser:install` 裝）。

### 8.2 `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本機增量：Playwright 約 +14.6 秒
（新 17.7 秒－少跑的 3.1 秒），node 約 +0.005 秒，pytest 約 +1.5 秒（形狀比對 4 個情境、兩個同步測試）。推估 `checks` 多約 0.3 分鐘。

### 8.3 pytest 子集與 Python 突變的結果

- pytest 子集：見第 8 節的表（465 案全過）。其中真後端形狀比對 14 個情境、`test_identity_fields.py` 17 案（含兩個新的同步測試）都過；
  HM-12 後端的測試（`test_odoo_identity_rotation`、`test_new_origin_secret`、`test_saved_destinations`）與形狀比對在同一個 session
  一起跑也照過（形狀比對引用 `Journal`、`record_writes`，沒有影響它們）。
- Python 突變（拋棄式複本，共用鎖下一次跑完，04:26）：P0（沒有突變）17 案全過；P1、P2 都由
  `test_the_panels_url_secrets_and_identity_bound_products_are_the_servers` 擋下；P3 由 `test_the_panels_origin_is_the_servers`
  擋下（各 1 案失敗、16 案過）。記錄在 `evidence-HM-12-panel/mutations/python/`。

### 8.4 審查修正後（2026-11-17；`ha_env.sh` 的 TMPDIR，每次跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 88 案全過 |
| `npm run build`＋`node tests/build-closure.mjs` | PASS；`dist/assets/app.js` `b0f7e7ad…`、`app.css` `c8b43515…`（沒變） |
| Playwright 全套（`single`＋`profiles-on`，照 CI） | 135 案全過（`single` 117、`profiles-on` 18），4.0 分鐘（`5e0f04f`）。`backend-identity.spec` 16 案逐案加總約 29.2 秒 |
| `checks` 增量（推估，第 8.2 節的更新） | Playwright 約 +26 秒（新 spec 約 29.2 秒－`profiles-on` 少跑的兩案約 3.1 秒）；node 與 pytest 沒有新案例。推估 `checks` 多約 0.5 分鐘 |
| 開關關比對 | 216 個比較 0 差異（第 7 節） |
| pytest 子集 23 檔（審查用的同一組：多了 `test_odoo_multi_profile`；正式 conftest、`-rfEs`） | 468 案全過、0 skip、96.3 秒（`5e0f04f`） |
| `packaging/validate.py`、packaging unittest（離線暫存 venv）、`scripts/tool_inventory.py` | `validate.py` PASS；unittest Ran 203、OK（skipped=5）；`tool_inventory.py` exit 0（`5e0f04f`） |
| 臨時突變 | 13 個全部擋下（第 6.1 節） |
| 離線重產 PaaS 測試對照表、HM-00 的 C2／C6 | 改規格前＝HEAD 的檔逐位元相同；改後只差一列；C2（117 列）、C6 PASS（`logs/paas-mapping-regen.diff`、`logs/offline-c6.log`） |

## 9. PaaS 變動清單（本機唯讀 PaaS repo；`git log --oneline 69ac425..origin/main -- <相關檔>`，`origin/main`＝`7087280`；審查修正時 `48f394d`）

查的路徑：`packages/mcp-admin-ui`、`apps/headscale/static`、`apps/odoo/odoo_mcp_admin/routers/config.py`、
`packages/mcp-admin-core/mcp_admin_core/routers/settings.py`、`…/connection_apply.py`、`…/config/store.py`、
`apps/headscale/headscale_mcp_admin/connection.py`、`apps/nextcloud/nextcloud_mcp_admin/routers/config.py`、`apps/nextcloud/README.md`。

| commit | 內容 | 對本片 |
|---|---|---|
| `0f94aa4`（#154） | Nextcloud 換使用者或網址時換 token | 不在本片（HM-22）。它的 README 寫明「共用前端只顯示回應的 `message`、不讀 `token_rotated`」，和 `69ac425` 的面板一樣（契約 #116 的 PaaS 欄） |
| `0f43fd3`（#152） | Nextcloud `base_url` 的 SSRF 檢查 | 不在本片（HM-22／HM-20） |
| `4f1a77f` | Nextcloud log 遮罩 | 不在本片 |
| `f5223be` | 共用測試拿掉 VK | 只改 `packages/mcp-admin-ui/tests/browser-capabilities.py`；面板行為沒變 |

`git diff --stat 69ac425 origin/main -- packages/mcp-admin-ui apps/headscale/static` 只有上面那一個測試檔。
審查修正時（2026-11-17 06:26）本機唯讀 repo 的 `origin/main` 已是 `48f394d`（別的流程 fetch；`7087280..48f394d` 只有 #156 的 Hermes
排程工具說明 `34769c2`，改 `apps/hermes/` 的 CHANGELOG、README、`server.py` 工具說明，不在本片）。上面的路徑 `69ac425..48f394d` 仍是
同 4 個 commit（`evidence-fix-HM-12-panel/logs/paas-readonly.log`）。PaaS 的
`token_rotated` 文字（`apps/odoo/odoo_mcp_admin/routers/config.py:136-138`、`Pc/routers/settings.py:477-487`）與 Headscale 的
`CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` 文案（`apps/headscale/static/assets/app.js:10`）在這段期間沒有改。本片照它們的方向
（換了 token 就叫人到 Tokens 頁複製新網址；新來源要替換或清除原有金鑰），文字用 HA 面板的語氣。

## 10. 本片用到的決策（`docs/multi-profile/decisions.md`）

| DQ | 本片怎麼用 |
|---|---|
| DQ-05（Odoo 換身分換 token；HM-12 的細分已向使用者說明） | 換 token 的提示與重新讀取；結果不明（S-7）的提示 |
| DQ-40 (a) ⑨（開通後改 url 來源要重填秘密） | 部分編輯的必填規則與 422 文案；全部產品；同來源換路徑不算（已知限制） |
| DQ-31（面板用「帳號」） | 「帳號」只指 profile；後端那邊寫「後端身分」，避免混淆 |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 |

沒有碰到待定題。

## 11. 預檢結果

下面是本筆記之前的結果；本筆記 commit 之後再跑一次（第 11.1 節）。

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 7646f0f --head HEAD --full` | `b5b5b29`：OK，0 命中（gitleaks 8.28.0，pin、驗過；5 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 7646f0f` | `dd61760`：OK。`runtime-patches.json` 176、`runtime-sources.json` 70、`docs/tool-surface.json` 159 個摘要 0 漂移、0 缺；改到的列管檔 3 個（app.js、api.js、contracts.js）都隨帳本更新；沒有新的未列管執行檔 |
| 雙向控制字元 | HM-12 的 `bidi_scan.py`（逐 commit：碰過的檔全文、新增的行、commit 訊息） | `b5b5b29`：U+202A～202E、U+2066～2069 合計 0；U+200E、U+200F、U+061C 也是 0 |

### 11.0 審查修正後

| 預檢 | 結果 |
|---|---|
| 秘密（`--base 7646f0f --head HEAD --full`） | `5e0f04f`：OK，0 命中（gitleaks 8.28.0，pin、驗過；17 個 commit＋HEAD 的樹＋整段歷史） |
| 帳本（`--base 7646f0f`） | `5e0f04f`：OK（`runtime-patches.json` 176、`runtime-sources.json` 70、`docs/tool-surface.json` 159 個摘要 0 漂移、0 缺；17 個檔，列管的 3 個都隨帳本更新；沒有未列管的執行檔） |
| 雙向控制字元（同上的 `bidi_scan.py`） | `5e0f04f`：17 個 commit、17 個檔：U+202A～202E、U+2066～2069 合計 0；U+200E、U+200F、U+061C 也是 0 |

### 11.1 本筆記 commit 之後

本筆記 commit 之後在最後的 HEAD 再跑兩個預檢與雙向控制字元掃描，結果記在交給主對話的回報（PR 說明照抄）：本筆記不能記自己
commit 之後的結果。

## 12. 驗收條件（任務與計畫 §12.3 HM-12）

| 條件 | 狀態 |
|---|---|
| 面板測試全綠（node、build-closure、Playwright 兩種模式） | 本機通過（審查修正後）：node 88、build-closure PASS、Playwright 135（`single` 117、`profiles-on` 18）；pytest 子集 23 檔 468 案（第一次交出時 127、465）。CI 待 PR |
| 開關關時面板不變 | 通過：既有 9 個 spec 沒改、`single` 照過；`build-closure.mjs` 沒改、照過；204 個比較 0 差異，審查修正後 216 個 0 差異（第 7 節）；新 spec 的開關關兩案（突變證明） |
| HM-11 的真後端形狀比對照過（需要時加 backend 的情境） | 通過：加 4 個情境 10 案，14 個情境全過；fixture 也全過 |
| 先寫測試、先紅後綠 | 通過（第 5 節）；只守現有行為的斷言用突變證明（第 6 節） |
| 同一系列 commit 更新帳本 | 通過：`79e0b0e`、`8ac163f`；帳本預檢 OK |
| 不改版號、不碰 `addons/`、不改 CHANGELOG；開關維持空集合；後端沒改 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：網址 `.invalid`（審查 S-8 後本片新加的都是；既有 `partial-settings.spec.mjs` 的 `http://old.test` 沒動）、憑證 `DUMMY-…`、token 是一個字母重複 43 次（fixture 換身分用 N、P、Q、R）；秘密預檢 0 命中 |
| 獨立審查 | 通過（必修 0、建議 9 都已處理；第 15 節） |

## 13. 還沒解決、交給後面的片

- **Q-1（要使用者定；審查第 4 節）**：開通後 Odoo 改 url／database／username 時，要不要在「確認儲存」對話框**先**提醒「這次會換 MCP
  權杖，舊網址立即失效，所有用戶端都要更新」？本片照最保守的做法**維持現狀**（只在存檔後提示，PaaS 也是存檔後）。這是新的面板規則，
  計畫與 DQ-05 都沒寫；不擋本片。要做的話放之後的片或 HM-18（面板算得出來：`identityBound`＋身分欄位有沒有改）。
- **HM-25（n8n 開通）**：n8n 上帳號 runtime 後，把「沒存過的秘密不用帶」的情境錄進 `profile-api-cases.json`（草稿：
  `artifacts/…/wave4/evidence-fix-HM-12-panel/handoff-HM-25/new-origin-unset-secret.scenario.json`；`expect` 要在真後端重錄），
  `tests/test_panel_profile_api_shapes.py` 那時要能比 n8n 的已存連線（`backend_edit.view`），送出的 n8n `key` 也交給 log 掃描（第 3.8 節）。
- **PaaS 測試對照表的產生器規格**（repo 外，S-3）：`wave0/hm00-check/paas_mapping_spec.py` 已改，新列引用的
  `backend-identity.spec.mjs` 只在本分支；本分支合併前，別的分支不要用新規格重產 `paas-test-mapping.md`（`SHA256SUMS` 也寫了）。
  另外 `SHA256SUMS` 裡 `FEATURE-MATRIX-zh-TW.md`、`PLAN-zh-TW.md` 兩行在本片之前就和實際檔不同了（之後的片改過計畫），本片沒動。
- **主對話（開 PR 前）**：`checks` 秒數；PR 說明寫明面板只在開通後有新行為、`profiles-on` 的例外；`claude-delivery` 若已前進，
  rebase 後重跑兩個預檢、node、Playwright、形狀比對。契約第 9 節本片用 #116、#117；別的片先合併佔號時，後合併的一方 rebase 後
  接在當時最後一列後面重排（程式與帳本 `change` 沒寫列號）。另一個代理在做的 HM-13c 也改 `Hui/app.js`：後合併的一方要重釘帳本。
- **HM-18（文件定稿）**：DOCS 寫「開通後換 Odoo 的 url／database／username，存檔提示會說權杖已換、到「連線與權杖」複製新的」、
  「網址改到另一台伺服器，表單會要求重新輸入密碼／金鑰」「存檔回 503 時面板會提示重啟後確認網址」；HM-12 審查 S-2（預設帳號
  結果不明時 8081 全部帳號 503 到重啟）面板沒有另外提示，放 DOCS。
- **HM-22／HM-24（Nextcloud、Hermes 開通）**：把產品加進 `products.IDENTITY_BOUND` 時，`tests/test_identity_fields.py` 的同步測試會紅，
  提醒同時把它加進 `Hui/contracts.js` 的 `identityBound`（S-7 提示才會出現）；`token_rotated` 的提示面板已經不分產品。
- **HM-26（Headscale 開通）**：面板規則已涵蓋 Headscale（只在開通時）。
- **HM-19b（HAOS 驗收）**：開通的 Odoo 在 HA 前端 iframe 裡實際看一次提示、必填規則與 422（Ingress 原樣轉送 422、503 的本體：
  HM-12 筆記第 12 節）。

## 14. commit（`7646f0f` 之後）

| commit | 內容 |
|---|---|
| `7c418f2` | test(ui)：HM-12 面板的測試、案例、真後端形狀比對的 fault 支援、新 spec、`profiles-on` 略過兩案（先紅） |
| `805c77b` | test(ui)：fixture 照 HM-12 的回應表回答（只在開通模式） |
| `3c0f539` | feat(ui)：換 token 的提示與重新讀取、新來源要重填秘密、S-7 提示 |
| `79e0b0e` | chore(provenance)：帳本重釘 app.js、api.js、contracts.js |
| `b5b5b29` | docs(multi-profile)：契約 #116、#117 與面板 README |
| `f5ebdb3` | test(ui)：形狀 D 的回聲是別的帳號時不說 token 換了（先紅） |
| `61357e3` | fix(ui)：形狀 D 的 `token_rotated` 只在回聲是送出的帳號時算數 |
| `8ac163f` | chore(provenance)：帳本重釘 api.js |
| `aab9b12` | docs(multi-profile)：驗收矩陣登記新 spec |
| `c928058` | refactor(ui)：說明不寫本片新列的列號（#116、#117 改成「HM-12 的面板列」；build 結果逐位元相同） |
| `dd61760` | chore(provenance)：帳本重釘 app.js、contracts.js |
| `4fbf530` | docs(provenance)：本筆記（第一次交出） |
| `325f862` | test(ui)：審查的測試（S-2、S-4、S-5、S-6、S-7、S-8；S-2、S-7 先紅） |
| `04f0654` | fix(ui)：換 token 後重新讀取失敗仍說明、withheld 網址的原因、OpenDesign 不顯示秘密說明（S-2、S-7） |
| `567ae35` | chore(provenance)：帳本重釘 app.js |
| `19dcc52` | test(ui)：沒換 token 的存檔重新讀取失敗照今天（守現有行為） |
| `5e0f04f` | docs(multi-profile)：契約 #116、#117（S-1）、PaaS 測試對照表重產（S-3）、README、驗收矩陣 |
| 本次 | docs(provenance)：本筆記加審查處理（第 15 節）與檢查結果 |

## 15. 獨立審查與意見處理（2026-11-17 審查；同日處理）

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-12-panel.md`（證據 `wave4/evidence-review-HM-12-panel/`）。
  判定**通過**，必修 0 項，建議 9 項（S-1、S-3 建議開 PR 前改）。要使用者定的題目 1 題（Q-1）。
- 處理的證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-fix-HM-12-panel/`（`session.log`、`logs/`、`mutations/`、`compare/`、
  `tools/`、`handoff-HM-25/`；用過的 `/tmp/ha-mp-XXXXXX` 記在 `tmpdirs.txt`，都已用完整路徑刪掉）。
- 先核對再改：S-2、S-7 用新 spec 在 `4fbf530` 的面板上重現（先紅，第 5 節）；S-1 用 `grep` 確認兩處；S-3 確認那一列是產生器寫的；
  S-6 試著在真後端加 n8n 情境時發現跑不了（第 3.8 節）；S-9 用 `git -C <PaaS> log` 確認。

| # | 意見 | 決定 | 怎麼處理 | 證據 |
|---|---|---|---|---|
| S-1 | 契約 #116、#117 的 HA 欄把面板檔寫成 PaaS 的 `Pui/contracts.js` | 採用 | 兩處改成 `Hui/contracts.js`；第 10 節加「HM-12 面板審查修正」一列 | `5e0f04f` |
| S-2 | 換了 token 之後重新讀取失敗，換 token 的說明被蓋掉 | 採用 | `reloadSaved`／`reloadRotated`（第 3.7 節）：先說換 token，再接失敗的原因，錯誤樣式；錯誤種類不變。200 與形狀 D 都是。沒換 token 的存檔照今天（另一案守住）。契約 #116、README 補 | `325f862`（紅）、`04f0654`、`19dcc52`；突變 S2-M1～M4 擋下 |
| S-3 | PaaS 測試對照表沒寫 `profiles-on` 略過兩案 | 採用（照該檔的規則：改產生器規格再重產，不手改表格） | 改 HM-00 產生器的 `paas_mapping_spec.py`（repo 外；`SHA256SUMS` 記了改前改後與原檔位置），用快取的 PaaS 案例（`7d111b1`）離線重產：改規格前重產＝現在的檔逐位元相同，改後只差那一列（補「HM-12 起 `profiles-on` 略過前兩案（DQ-40 ⑨）」與開通的版本 `backend-identity.spec.mjs`）。離線跑 HM-00 的 C2、C6：PASS | `5e0f04f`；`logs/paas-mapping-regen.diff`、`logs/offline-c6.log`、`tools/offline_regen.py.txt` |
| S-4 | 測試缺口：額外帳號、改回同來源保留已打的值、送出時的第二道檢查 | 採用 | 新 spec 三案：額外帳號（Odoo）的部分編輯要求重填密碼並帶該帳號標頭；打了 key 再改回同一台伺服器，「提供新值」與值都留著；用 `page.evaluate` 把「保留」打開再送出，前端擋下、0 個請求 | `325f862`；R10、R11、R08 擋下 |
| S-5 | 換 token 的兩條路沒釘住「伺服器文字不顯示」 | 採用 | node 形狀 D 案的回應加 `message` 與 `detail.message`（canary），斷言錯誤文字不含它；新 spec 一案用 `page.route` 在 200 與形狀 D 的回應加同樣的文字，斷言提示逐字等於面板自己的文字、頁面沒有 canary。200 的提示在 `app.js` 組成，node 載不進 `app.js`，所以 200 由 Playwright 守 | `325f862`；R13、R14 擋下 |
| S-6 | fixture 的「沒存過的秘密不用帶」沒有真後端案例 | 部分採用 | 真後端形狀比對做不到（第 3.8 節：只有 n8n 碰得到，n8n 到 HM-25 才上帳號 runtime，`KeyError`）。fixture 這邊：新 spec 的 n8n 案多一次存檔（MCP token 清掉後再換到別台，只要求 key、fixture 照收）；add-on 這邊已有 `tests/test_new_origin_secret.py` 的 `never` 段。n8n 情境草稿交 HM-25 | `325f862`；F01b 擋下；`handoff-HM-25/` |
| S-7 | (a) OpenDesign 也顯示秘密說明；(b) withheld 網址的原因寫錯 | 採用 | (a) 只在 `urlSecrets[產品]` 有秘密時加；(b) 原因改成「伺服器不顯示原網址，無法確認是同一台伺服器：請重新輸入…」。送出時第二道檢查的文字與說明段沒改（第 3.7 節） | `325f862`（紅）、`04f0654`；S7-M1～M3 擋下 |
| S-8 | 新測試資料用 `.test` 網址 | 採用 | 新 spec 與 node 的 HM-12 新案例改成 `.invalid`（既有 `partial-settings.spec.mjs` 沒動） | `325f862` |
| S-9 | 筆記第 9 節的 PaaS `origin/main` 舊了 | 採用 | 第 9 節補：現在是 `48f394d`，相關路徑沒有新 commit | 本筆記；`logs/paas-readonly.log` |

- **Q-1（要使用者定，不擋本片）**：開通後 Odoo 改 url／database／username 時，要不要在「確認儲存」對話框**先**提醒「這次會換 MCP 權杖，
  舊網址立即失效，所有用戶端都要更新」？照最保守的做法**維持現狀**（只在存檔後提示，和 PaaS `Pui/pages/ConnectionConfig.jsx:299` 一樣），
  記在第 13 節，交主對話問使用者；要做的話放之後的片或 HM-18。
- 審查第 6 節的觀察也照記：預設帳號結果不明時 8081 全部帳號 503 到重啟，面板只提示重啟與確認網址（交 HM-18 的 DOCS，第 13 節）；
  HM-22、HM-24 加產品到 `products.IDENTITY_BOUND` 時同步測試會紅（第 13 節）；HM-13c 也改 `Hui/app.js`，後合併的一方重釘帳本。
