# HA 多帳號 HM-11 provenance：面板的帳號選單、切換、回聲、收據、建立後切換（先對 fixture，2026-11-15）

## 結論

- **2026-11-16 rebase 到 `claude-delivery` `df686dd`**（HM-31 的 PR #105、HM-09 監看修正的 PR #106 合併後；第 18 節）：35 個 commit
  照原順序重放，衝突只在 3 個文件 commit（契約、`decisions.md`），程式、測試、fixture 逐位元不變。契約第 9 節本片的列改成 #109～#112
  （HM-31 已用掉 #101～#108）。帳本逐列核對，5 個面板檔的 SHA-256 照實際內容重算（值不變）。真後端形狀比對在新基準照過，不用重錄。
  本機 node 81、Playwright 117、pytest 子集 525、全套 5,978 過（7 個要 root 的既有案例失敗）；兩個預檢 OK；沒有原始雙向控制字元。
- **2026-11-16 已 rebase 到 HM-10（`684a2dd`）並對齊真後端**（第 16 節）：HM-10 交給 HM-11 的待辦逐條處理；fixture 與真的 8099
  管理 app 對同一份案例逐案一致（`packages/mcp-admin-ui/tests/profile-api-cases.json`，Python 對真後端、Playwright 對 fixture；
  對齊時 93 案，對齊審查後 94 案）；審查 S-2（清單不能用時鎖住整個面板）在這一輪做完。
- **對齊這一輪的獨立安全審查也做了**（`wave4/review-HM-11-align.md`）：判定通過、沒有必修，建議 10 項，處理見第 17 節。
  補了 7 段測試，守住審查時存活的突變；補一個案例，釘住刪除的檢查順序；契約 #111、DQ-31 的字改正；
  push 前改寫歷史，拿掉原始 U+202E（第 17.3 節，最後的樹不變）。最後的數字在第 17.5 節。
  下面第 1～15 節是對 fixture 那一階段的紀錄，第 16 節是對齊那一輪的紀錄（commit 是改寫前的編號，對照在第 17.3 節）。
  第 18 節是 rebase 到 `df686dd` 的紀錄；第 1～17 節的 commit 編號是這次 rebase 前的（對照在第 18.11 節），列號已改成新的。
- **產品沒開通時，面板畫出來的東西與送出的請求都不變**：DOM、送出的請求（方法、路徑、標頭集合）、fixture 收到的紀錄，和 `b5d10c5` 的面板逐項相同
  （第 5.3 節：6 種設定、5 頁、幾種動作，72 個比較 0 差異；審查修正後在 `155022e` 重跑仍是 0 差異）。
  **CI 也守得住**：`profiles.spec` 有一案在開關關時逐頁確認沒有帳號介面、帳號字樣與帳號標頭（審查 MF-1）。
  既有 9 個 Playwright spec 一個字都沒改照過。repo 裡的 `MULTI_PROFILE_PRODUCTS` 維持空集合；這一片只動面板、fixture、P9 kit 的 client 與文件，沒有動任何正式的 Python（對齊時只新增 pytest 測試 `tests/test_panel_profile_api_shapes.py`，第 16.4 節）。
- **開通後**（目前只有 fixture 會開；真後端是 HM-10）：
  - 頂列有帳號選單（`<select aria-label="帳號">`）與「新增帳號」「改名」「刪除帳號」；標題列固定顯示目前帳號與 id 前 8 碼；
    每個確認對話框寫出帳號。預設帳號不能改名、刪除；刪除要確認兩次並寫明後果（DQ-14）。名稱一律以文字節點顯示。
  - 帳號選擇只在頁面記憶體（DQ-18），重新整理回預設帳號。第一次 bootstrap 不帶帳號；伺服器回 400 `profile_id_required`
    就改成**每個**帳號範圍請求都帶 `X-MCP-Profile`（含明確的 `default`）；`/api/profiles*` 永遠不帶。
  - 每個帳號範圍回應都比對回聲，沒有本體的 204 也算不符（審查 S-4）；`mutate(…, profile)` 開頭就鎖定帳號，取 CSRF 的 bootstrap 與變更帶同一個標頭、兩個回聲都比對；
    不符就不顯示、藏起 token、提示並重新讀取（C1-S11、I12）。換帳號之後才到的回應一律丟掉（帳號世代）。
  - 切換：藏 token、清密碼欄與草稿、整頁重畫；切換中只剩選單可用，再選一次就取代前一次切換；其他操作進行中選單停用。
  - 建立後自動切到新帳號（DQ-31）；任何帳號範圍請求回 `profile_not_found` 就回預設帳號並說明。
  - **被刪帳號的待確認收據**：面板一得知帳號已刪除就清掉並說明，不叫人切回（審查 S-1，第 3.3 節列出五條路徑）。
  - 收據：預設帳號的 key（`woow-admin-operation-v1:<mount>`）與 4 鍵紀錄完全不變；額外帳號 `…:<mount>:<id>`、5 鍵；
    帳號增刪 `…:<mount>:profiles`。`get()` 每個 key 只收自己的格式，升級前分頁留下的舊紀錄照常可查（Playwright 案例）。
- **fixture 階段的獨立安全審查已做**：判定「修正後通過」（必修 1、建議 9；報告 `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-11.md`）。
  必修 MF-1 已修；建議 S-1、S-3～S-9 已處理；S-2（清單不合規時整個面板鎖住）當時留到收尾，2026-11-16 對齊時做完（第 15 節、第 16.2 節第 15 點）。
  S-1 核對時另找到兩條收據留著的路徑，也一起修了（`842dfed`）。
- **先寫測試**：`6ba92bb` 只有測試與 fixture，在 `b5d10c5` 的面板上紅；`df146d4` 起綠。審查後的修正也是先 commit 測試（`3e32c2f`、`ded9d01`）再修；
  只守現有行為或守新條件的案例（MF-1、索引壞那段）用突變證明會紅；`507314d` 那段沒有先紅，審查後補了紅的紀錄（第 4 節）。
- 新測試：node 16 案（約 0.2 秒）、Playwright `profiles.spec` 11 案（逐案加總 24.1 秒）＋開關開專案 20 案（32.5 秒）。本機 Playwright 全套
  2 分 28 秒 → 3.6 分鐘，推估 CI `checks` 多約 1.0 分鐘（第 7 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。
- 照契約假設、要等 HM-10 對齊的地方列在第 11 節（「收尾」不在這一階段）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-11（計畫 §12.3；風險高、工作量 L；要獨立安全審查）。這一階段只對 fixture；和 HM-10 真後端對齊的「收尾」不在這一階段 |
| 分支 | `feat/ha-multiprofile-hm11-20261115`（一般 clone，不是 worktree） |
| 基準 | 現在：`claude-delivery` `df686dd`（HM-10 的 PR #104、HM-31 的 PR #105、HM-09 監看修正的 PR #106 都已合併；2026-11-16 rebase，第 18 節）。之前：fixture 階段是 `claude-delivery` `b5d10c5`（HM-00、01、02、04、05、06、07、08、13a、17 已合併）；對齊 HM-10 時是 PR #104 的 head `684a2dd`（第 16 節） |
| 依據 | 計畫 §6、§10.3、§12.3 HM-11；契約 §1.2、§3（管理 API、`X-MCP-Profile`、回聲、寫入保護、欄位）、§4.1、§9 #31～#36、#55、#56、#84、#85；FM-12、20、21、22、23、26、53、56～66、71、98、145；`decisions.md` |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425` 的 `packages/mcp-admin-ui/src/api.js`（標頭規則）、`profileStatus.js`（停用說明）、`useDurableOperation.js`（收據 key：預設帳號沿用舊 key）、`components/ProfileChooser.jsx` 與 `AdminApp.jsx`（建立後切換、刪除後回預設）、`apps/headscale/static/assets/app.js`（帳號世代、晚到回應丟掉、「前一個設定檔有未確認的請求」）。HA 刻意不同的地方見契約 §9 |
| 安全審查 | 兩輪。fixture 階段：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-11.md`（審查 `3a9feed`；證據 `wave4/evidence-review-HM-11/`），修正的證據在 `wave4/evidence-fix-HM-11/`（第 15 節）。對齊之後：`wave4/review-HM-11-align.md`（審查 `8421269`＝改寫歷史後的 `214c192`，同一棵樹；證據 `wave4/evidence-review-HM-11-align/`），處理的證據在 `wave4/evidence-fix-HM-11-align/`（第 17 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hui/profiles.js`（新） | 帳號 id、回聲比對、清單列驗證、名稱規則（DQ-16）、選單文字與停用／無法啟動說明、用戶端名稱（DQ-31）、頂列選單與建立／改名對話框（DOM 工具由 app.js 傳入） |
| `Hui/api.js` | `AdminApi` 的 `profile`、`epoch`、`open()`（探測開關）、`select()`；每個帳號範圍請求帶標頭並比對回聲（`ProfileEchoError`；開通後帳號範圍的 204 也算不符）、舊世代的回應丟掉（`StaleProfileError`）；`mutate(operation, payload, revision, profile)`；`profileList`、`createProfile`、`renameProfile`、`deleteProfile`、帳號增刪的收據與重送；帳號錯誤代碼的固定文案 |
| `Hui/operation-identity.js` | 三種 key 與各自的紀錄格式；`get()`、`start()`、`clear()` 帶範圍；`profile.create`／`profile.delete` 兩種收據 |
| `Hui/app.js` | 選單、切換（`show()`）、建立／改名／刪除流程、`profile_not_found` 與回聲不符的後續處理、各頁的帳號文字、額外帳號唯讀的端點、讀不到的帳號仍可刪、索引壞的橫幅、帳號增刪的待確認卡；`forget(id)`：被刪帳號的收據在每條得知路徑清掉並說明 |
| `Hui/contracts.js` | `policyFingerprint` 含帳號 id；`policyRestartNotice(product, scoped)`；`clientExample(endpoint, token, name)`。單帳號時行為不變（指紋字串多一個 `null`，只在頁面內比對） |
| `Hui/styles.css` | 帳號選單、說明、對話框的版面 |
| `packages/mcp-admin-ui/fixtures/server.mjs` | 多帳號替身（開關兩種）與測試勾子（第 3.4 節） |
| `packages/mcp-admin-ui/playwright.config.mjs`、`tests/owned-fixture.mjs` | `single`、`profiles-on` 兩個專案；`profilesOn` 選項 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs`（新）、`tests/browser/profiles.spec.mjs`（新） | 第 4、5 節 |
| `packages/mcp-admin-ui/tests/build-closure.mjs` | N15 兩個字面斷言保留；加額外帳號與帳號增刪的格式、key 形式、帳號選擇不進瀏覽器儲存、打包後有 `X-MCP-Profile` |
| `H:packaging/ha_p9_admin.mjs` | 透過 `AdminApi` 自動帶標頭；`{profile}` 指定額外帳號；呼叫端 headers 帶 `X-MCP-Profile` 直接拒絕 |
| `docs/provenance/runtime-patches.json` | app.js、api.js、contracts.js、operation-identity.js 重新釘摘要並補說明；新增 `profiles.js`。審查後 app.js 再釘兩次、api.js 一次 |
| `packages/mcp-admin-ui/README.md`、`docs/admin-write-contracts.md` | 多帳號的面板行為與收據格式；被刪帳號收據的全部得知路徑 |
| `docs/multi-profile/decisions.md` | DQ-31 記成已定（獨立 commit `b567f68`，變更紀錄順序由 `0eed62a` 修正；rebase 時若 HM-09／HM-10 已記，兩個一起丟掉） |
| 本筆記 | — |

commit 順序：

| commit | 內容 |
|---|---|
| `6ba92bb` | 測試與 fixture（先紅） |
| `df146d4` | 實作 |
| `ff49bd0` | 帳本 |
| `b484450` | README 與寫入契約文件 |
| `b567f68` | DQ-31 |
| `507314d` | 後端與工具頁的帳號說明、工具隔離案例、帳本重新釘 app.js |
| `3a9feed` | 本筆記初版（送審版本） |
| `3e32c2f` | 審查：MF-1 開關關的案例、S-1 兩案、S-4 node 一案（先紅） |
| `a6871c2` | 審查：S-1 `forget(id)`、S-4 204 當回聲不符 |
| `cef2d7c` | 審查：帳本重新釘 app.js、api.js；S-7 第 2、3 點的帳本用字 |
| `1339843` | 審查：S-7 第 4 點（寫入契約文件第一段）與 README |
| `0eed62a` | 審查：S-7 第 5 點（decisions.md 變更紀錄順序） |
| `ded9d01` | 審查：S-1 另外兩條路徑的案例（先紅） |
| `842dfed` | 審查：S-1 另外兩條路徑的修正 |
| `4f86a8f` | 審查：帳本重新釘 app.js |
| `038de6f` | 審查：README 與寫入契約文件列出全部得知路徑 |
| `155022e` | 審查：索引壞的替代清單不算刪除（守新條件，突變證明） |
| `fbb8b7f` | 本筆記：審查意見處理（第 15 節） |
| `87afe99` | 審查：README 與寫入契約文件寫明索引壞的替代清單不算刪除 |
| 本筆記 | 補本機檢查與預檢的結果 |

沒改：任何 Python（`packages/mcp-admin-core/`、`apps/`、`tests/*.py`）、`tests/owned_ui.mjs` 等 repo 根目錄的測試工具、`conftest.py`、
`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、workflow、`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`launch.py`）、
`docs/multi-profile/contract.md`（計畫 §12.2 的衝突表只排 HM-00、10、18；要改的字句列在第 13 節交給 HM-10／HM-18）、
`docs/multi-profile/acceptance-matrix.md`（測試檔登記表照舊是「計畫」，和前面各片一致）、`H:packaging/ha_p9_driver.mjs`（帳號參數是 HM-16）。

## 3. 設計重點

### 3.1 開關怎麼探測（契約 §3.3）

- 第一次 bootstrap 不帶 `X-MCP-Profile`：沒開通的伺服器照今天回 200（請求與今天逐位元相同）；開通的伺服器在角色檢查之後回
  400 `profile_id_required`，面板就改成帶 `X-MCP-Profile: default` 再讀一次，之後每個帳號範圍請求都帶。非管理員照樣只拿到 403。
  這是契約 §3.3「每個帳號範圍請求都帶」的唯一例外（I12 仍成立：伺服器拒絕沒帶的請求），交給 HM-10／HM-18 寫進契約（第 13 節）。
- 不帶標頭卻拿到帶回聲的回應（不該發生）：同樣改成明確帶 `default` 再讀，絕不顯示沒指定帳號就拿到的內容。
- 帶了標頭仍回 `profile_id_required`（例如平台沒轉送標頭）：直接顯示錯誤（「可能是 Home Assistant 沒有轉送帳號標頭」），不會無限重試。
- 帳號範圍回應的回聲在單帳號模式下不得出現、在多帳號模式下一定要指名被問的帳號；兩種錯配都是 `ProfileEchoError`，面板重新探測。

### 3.2 一次變更鎖定帳號（C1-S11）與帳號世代

- `mutate(operation, payload, revision, profile)`：開頭就比對呼叫端畫面的帳號與目前帳號，不同就什麼都不送；之後的 bootstrap
  與變更都帶同一個標頭，兩個回聲都比對；bootstrap 的回聲不符時變更不會送出。既有呼叫寫法 `mutate(op, payload, revision)` 照用
  （P9 kit 與既有 node 測試不用改），帳號預設取目前帳號。
- `AdminApi.epoch`：每次換帳號（`select()`、`open()`）加一。每個請求記下開始時的世代，回應（含錯誤回應）到的時候世代變了就丟掉。
  變更晚到時，它的待確認收據留在原帳號的 key，回到那個帳號時看得到。
- 面板的 `task()` 鎖照舊：任何操作進行中選單停用。**切換本身例外**：切換時整頁換成「正在切換到帳號…」，只剩選單可用，
  再選一次就以新的世代取代前一次切換（前一次的回應晚到就丟掉），卡住的切換不必重新整理頁面就能離開。這是 HA 面板唯一會出現
  「晚到回應」的路徑，Playwright 用它驗證丟掉（第 5 節）。

### 3.3 收據（C4-MF-3、FM-62、FM-145）

| 範圍 | key | 紀錄 |
|---|---|---|
| 預設帳號，或沒開通的伺服器 | `woow-admin-operation-v1:<mount>`（不變） | `{id, route, revision, product}`（不變） |
| 額外帳號 | `woow-admin-operation-v1:<mount>:<24 hex id>` | `{id, route, revision, product, profile}` |
| 帳號建立 | `woow-admin-operation-v1:<mount>:profiles` | `{id, route:"profiles/create", revision:"p1-…", product, label}` |
| 帳號刪除 | 同上 | `{id, route:"profiles/delete", revision:"p1-…", product, profile}` |

- 每個 key 只收自己的格式（4 鍵放在額外帳號的 key、5 鍵放在預設帳號的 key 都算不相容）；同一範圍有待確認的操作時，不能開始另一筆。
- 建立的紀錄存名稱：名稱不是秘密（選單與索引都看得到），存下來重送才是同一個請求（同一個 Idempotency-Key 必須同內容）。
- 帳號增刪的待確認卡只有「重送帳號操作」與「已核對帳號清單」：契約沒有全域收據的查詢路徑（第 11 節）。
- **被刪帳號的待確認收據**再也查不到（契約 §9 #84、FM-59）。面板一得知帳號已刪除，就用 `forget(id)` 清掉並說明，不會叫人切回：
  1. 在面板刪除成功（`a6871c2`）；
  2. 重送帳號刪除確認完成（`a6871c2`）；
  3. 帳號範圍請求回 `profile_not_found`（`gone()`，原有）；
  4. 重送帳號刪除回 `profile_not_found`：說的是要刪的帳號「帳號（id 前 8 碼）已不存在，不需要再刪除」，不是目前顯示的帳號（`842dfed`；原本在預設帳號上會說「帳號「預設帳號」（default）已不存在」）；
  5. 切換時，新讀的清單可信而且沒有剛離開的帳號（`842dfed`；原本會說「前一個帳號…請切回該帳號查詢結果」，但它已不在選單裡）。
  索引壞時的替代清單（只有預設帳號）**不算**，收據留著，索引恢復後還查得到（`155022e`）。沒有待確認收據時不加說明。
  沒涵蓋的只剩：在別處刪除、這個分頁之後再也沒碰到的帳號。它的收據留到分頁關閉，看不到也不會被使用，紀錄不含秘密。

### 3.4 fixture（LOCAL MOCK）

- 沒開（預設）：不看 `X-MCP-Profile`；`calls` 只有在請求真的帶標頭時才多 `profileHeader` 一欄，所以既有 spec 的 `toEqual` 不受影響。
  回應和以前逐位元相同，**只有一處例外**：`owner-defaults/*` 的 409 本體多了 `error: 'owner_defaults_unavailable'`，對齊真伺服器的形狀 C
  （契約 §4.1；審查 S-7 第 1 點。`6ba92bb` 的 commit 訊息寫「逐位元相同」，以這裡為準）。
- 開了（`profiles: true | {extra, limit, memory, indexCorrupt, listStatus}`）：照契約 §3.3 的標頭規則與 §3.4 的回聲；`/api/profiles`
  清單（ETag 標頭）、建立（201＋收據、同 key 重送 200、名稱規則與上限）、改名、刪除；額外帳號 `PUT endpoint` 409 `endpoint_global`；
  讀不到的帳號 503 `state unavailable`；新帳號複製預設帳號當下的政策（DQ-02）。帳號增刪先 replay 再查其他條件；刪除在比 If-Match 之前先查帳號存不存在。
- 勾子：`/__fixture/defaults`（profiles-on 專案）、`/__fixture/profile`（外部刪除／改名／新增、切換開關＝模擬升級，保留狀態與收據）、
  `/__fixture/profiles`（各帳號狀態，給斷言）、`/__fixture/reads`（清單讀取，不算 calls）、`wrongEcho`、`createToken`（契約違規的建立回應）。

### 3.5 沒有本體的回應（審查 S-4）

- 開通後，帳號範圍的 204 沒有本體、帶不了回聲，一律當回聲不符（`ProfileEchoError`：不顯示、重新探測；變更的待確認收據保留）。
- 開關關時、全域路徑（`/api/profiles*`）的 204 照舊回 `null`。今天 HA 的管理動作都回 JSON（`gateway.py:604-779`），沒有行為改變。

## 4. 先紅後綠

| 檢查 | 紅（測試在前、程式在後） | 綠 |
|---|---|---|
| `6ba92bb` 的測試＋`b5d10c5` 的面板：node | 59 案：58 過、1 失敗（`profiles.test.mjs` 找不到 `src/profiles.js`，15 案沒跑） | `df146d4` 起 73 案全過 |
| 同上：`build-closure.mjs` | 失敗（第 54 行，新加的格式斷言） | PASS |
| 同上：Playwright（`single`＋`profiles-on`） | 100 案：71 過（既有 spec 全過）、29 失敗（`profiles.spec` 9 案、`profiles-on` 20 案），12.3 分鐘（失敗案等到逾時） | 100 案全過 |
| `3e32c2f` 的測試＋`3a9feed` 的面板（S-1、S-4） | node 74 案：73 過、1 失敗（204 那案：`Missing expected rejection (ProfileEchoError)`）；`profiles.spec` 10 案：8 過、2 失敗（兩個 S-1 案例，提示仍是「前一個帳號…請切回該帳號查詢結果」）。審查後在拋棄式複本重跑過一次，結果相同 | `a6871c2`：node 74 案全過、`profiles.spec` 10 案全過、Playwright 全套 101 案全過 |
| `ded9d01` 的新案＋`0eed62a` 的面板（S-1 另外兩條路徑） | 失敗在切回預設帳號的提示：實際是「前一個帳號「會計」（01234567）有尚未確認的操作；請切回該帳號查詢結果，再決定是否重試。」 | `842dfed`：`profiles.spec` 11 案全過（新案 2.6 秒） |
| MF-1「開關關」案例（`3e32c2f`） | 守的是現有行為，在現有程式上本來就過；紅由突變證明（下表 N01～N08） | 1.7 秒 |
| 索引壞那段（`155022e`） | 守 `842dfed` 的新條件，在修正之後才補，沒有先紅；紅由突變 N13 證明 | 全案 2.0 秒 |
| `507314d`（FM-60／FM-64 的帳號說明、FM-98 工具隔離） | **這段沒有先紅**：測試與實作同一個 commit。審查後補做：把 `app.js`、`styles.css` 換回 `507314d^` 的版本，FM-64 的說明斷言（`profiles.spec` 第 116 行）失敗；拿掉那一行，FM-98 的隔離斷言在舊程式上也過，守的是 `df146d4` 起已有的行為 | `507314d` 起過 |

突變（`155022e` 的拋棄式複本；每個只改 `Hui/`、重 build、跑它要擋的那一案，跑完用 git 還原；工具與輸出在 `wave4/evidence-fix-HM-11/`）：

| # | 突變 | 擋住的案例與位置 |
|---|---|---|
| N01（＝審查 M14） | 開關關時頂列也有帳號選單與「目前帳號」 | 開關關：帳號介面數量要是 0 |
| N02（＝審查 M15） | 開關關時後端、工具頁多帳號說明 | 同上 |
| N03 | 開關關時診斷頁多「這是帳號…的子行程」 | 開關關：沒有帳號字樣 |
| N04 | 開關關時權杖頁換成多帳號文字 | 同上 |
| N05 | 開關關時重啟說明只說這個帳號的子行程 | 開關關：重啟說明是整個子行程 |
| N06 | 開關關時確認框多帳號行 | 開關關：帳號介面數量要是 0 |
| N07 | 開關關時多一次 bootstrap | 開關關：請求清單 |
| N08 | 開關關時請求帶 `X-MCP-Profile` | 同上 |
| N09 | `forget()` 沒有收據也說「已一併清除」 | 讀不到的帳號：不得宣稱有清除 |
| N10 | 開通時後端頁沒有帳號說明（FM-60） | 切換案例的說明全文 |
| N11 | 切換時不看剛離開的帳號還在不在 | 新案：切回預設帳號的提示 |
| N12 | 重送刪除的 `profile_not_found` 算在目前帳號 | 新案：實際是「帳號「預設帳號」（default）已不存在…」 |
| N13 | 索引壞的替代清單也當成「已刪除」 | 索引壞那段：收據被清、說「已不存在」 |
| N14 | 已不存在的帳號仍叫人切回 | 新案：不得有「請切回該帳號」 |

14 個都擋住。

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

### 5.1 面板測試

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 74 案全過（基準 58 案；新 16 案約 0.2 秒；全部約 0.4 秒） |
| `npm run build` ＋ `node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`，照 CI 裝 Chromium） | `155022e`（最後一個程式與測試 commit；在同一 commit 的拋棄式複本跑）：102 案全過（`single` 82、`profiles-on` 20），3.6 分鐘；基準 `b5d10c5`：71 案、2 分 28 秒 |
| `profiles.spec.mjs` | 11 案，逐案加總 24.1 秒 |
| `profiles-on` 專案 | 20 案，逐案加總 32.5 秒 |

### 5.2 其他

| 檢查 | 結果 |
|---|---|
| pytest 子集（第 5.4 節） | 見第 5.4 節 |
| 全套 pytest | 沒跑：這一片沒有改任何 Python，也沒有改 pytest 會讀的面板以外的檔；以 CI 為準 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS（最終 HEAD） |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`，同基準（最終 HEAD） |
| `scripts/tool_inventory.py`（漂移檢查） | exit 0（最終 HEAD） |
| `git status` | 乾淨 |

### 5.3 開關關時面板不變的比對（repo 外 `SP:hm11-dom/bin/compare.mjs`，不 commit）

- 基準＝`git show b5d10c5:` 取出的面板原始碼與當時的 fixture，自己 build；新版＝本分支。兩個 fixture 各起一個，用同一個 Chromium。
- 6 種設定（預設 n8n；Odoo＋parity046＋已設定；n8n＋操作限制＋條件寫入；Hermes＋端點＋遮罩與歷史；EMQX 固定後端＋離線＋套用失敗；
  Hermes＋升級通知格式不符）× 5 頁（總覽、後端、工具、連線與權杖、診斷）；每頁比「不動」與「按重新整理狀態」兩種，
  連線與權杖頁另比「開『顯示權杖』對話框」與「重新產生權杖」（每種設定 12 個，共 72 個）。
- 比 `document.body.innerHTML`、fixture 的 `calls`（操作識別碼換成固定字）、瀏覽器送出的每個 `/api/` 請求的方法、路徑與標頭名稱集合。
- 結果：72 個比較 0 差異（`507314d`，作者跑）；審查修正後在 `155022e` 重跑，仍是 72 個 0 差異。
- 這個腳本只跑一次、不在 CI。CI 的守門是 `profiles.spec` 的「switched off」案例（審查 MF-1；第 4 節的突變 N01～N08）。

### 5.4 pytest 子集

- 指令：`flock SP:wave1-pytest.lock env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rfEs` 加 16 個檔：
  `test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`、`test_tool_inventory`、`test_ledger_precheck`、`test_owned_ui`、
  `test_owned_browser`、`test_owned_browser_ipc`、`test_owned_browser_redirect`、`test_admin_ui`、`test_identity_fields`、`test_batch2_admin`、
  `test_n8n_selectors`、`test_b2_odoo_policy`、`test_writes_default_on`、`test_owned_ports_bearer`（審查員的 17 個檔，去掉要 root 的 `test_owned_executable`）。
- 先前的兩次：作者在 `507314d` 跑 12 個檔，151 案全過、0 skip、44.8 秒；審查員在 `3a9feed` 跑 17 個檔，250 過、1 失敗（`test_owned_executable.py`，要 root，本機預期）、0 skip、72.2 秒。
- 本次（程式與測試同 `155022e`，正式 conftest，在共用鎖排隊）：16 個檔 248 案全過、0 skip、71.8 秒（排隊約 65 分鐘，00:19 取得鎖；執行時 HEAD 是 `87afe99`，之後只多文件）。比審查員少 `test_owned_executable.py` 的 3 案：250＋1−3＝248，數字對得上。

## 6. 只在 CI 跑的測試

- 本片新增的 node 16 案與 Playwright 11＋20 案都在本機跑過、全部通過，沒有只在 CI 跑的新測試。
- 本片沒跑的：全套 pytest（沒改 Python；CI 以 root、0 skip 跑）；`tests/integration_local_runtime.py`（要 root，不在 pytest 收集範圍，
  CI 也不跑；用真 Core 驗新面板的單帳號路徑，這一片改用第 5.3 節的比對與 MF-1 案例）。
- 已知要 root、本機一定失敗的既有案例（同 HM-08 筆記第 6 節）：`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5。
- Node：CI 與本機都是 v26.12.1；Playwright 1.61.1（Chromium headless shell 149）。

## 7. `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本機增量：Playwright 新案逐案加總約 57 秒
（`profiles.spec` 11 案 24.1 秒＋`profiles-on` 20 案 32.5 秒；審查後比送審版多約 7 秒：MF-1 1.7 秒、S-1 新案 2.2 秒、兩個 S-1 案例與索引壞那段的擴充），
加兩個專案的啟動成本；node 約 +0.2 秒；pytest 0。推估 CI `checks` 多約 1.0 分鐘（約 34.6 → 35.6 分鐘，上限 40），在每片 1.5 分鐘內。
若要省，`profiles-on` 可只留 1440／320 兩種寬度的變體（要改 config，不改 spec）。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；本筆記最後一個 commit 為 HEAD 時，本片全部 commit（`b5d10c5..HEAD`，20 個）＋HEAD 整棵樹＋整個歷史：**0 命中** |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | 本筆記最後一個 commit 為 HEAD 時：`runtime-patches.json` 173 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的 5 個列管檔（app.js、api.js、contracts.js、operation-identity.js、profiles.js）都有帳本更新；沒有沒列管的新執行檔：**OK** |

測試資料：沒有 commit 任何隨機 token。固定的 token 形字串只有每個帳號一個字母重複 43 次（`M`、`T`、`U`…，低熵、沒人持有）與
既有的 `S`×43；遮罩 `TTTT`＋`*`×20＋`TTTT`；網址 `.test`、`.example`（同既有 spec）；操作識別碼在執行時由瀏覽器產生。

## 9. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`，本機唯讀 PaaS repo；任務寫的 origin/main 是 `cf3d0d5`，clone 裡已被別的流程 fetch 到 `5b84b5d`，2026-11-16 對齊審查時已是 `7087280`；本片沒有 fetch、沒有 checkout）

| commit | 內容 | 對本片 |
|---|---|---|
| `f5223be` | 只改測試：共用測試拿掉 VK（含 `packages/mcp-admin-ui/tests/browser-capabilities.py` 的產品清單） | 沒影響：帳號相關的面板與 API 沒變 |
| `e6971c0` | 閘道請求內容位元組預算：預設值扣掉子行程記憶體、啟動時建立、卡住的上傳逾時。`profiles.py` 只把帳號容量的算法從 `ProfileRegistry.capacity` 抽成 `current_profile_capacity`（同一份算法，兩邊共用）；`app.py` 在啟動時建預算 | 沒影響：8081 閘道的事（HA 這邊是 HM-31）；管理 API 的回應形狀與面板都沒變 |
| `3b135ca` | 閘道：所有產品加上 JSON 結構守門（深度與元素個數），只動 `app.py` 的閘道設定 | 沒影響：同上 |

查的檔：`packages/mcp-admin-ui/`、`apps/headscale/static/`、`apps/headscale/tests/browser/`、`packages/mcp-admin-core/mcp_admin_core/profiles.py`、
`routers/profiles.py`、`routers/operations.py`、`app.py`。`git diff --stat 69ac425 origin/main -- packages/mcp-admin-ui/` 只有上面那一檔。審查修正後重查（`69ac425..cf3d0d5`、`69ac425..5b84b5d`），結果相同。
對齊審查後重查 `69ac425..7087280`（只用 `git log`／`git show`／`git diff --stat`）：多了 `e6971c0`、`3b135ca` 兩個閘道 commit（對齊審查 S-8）；
`packages/mcp-admin-ui/`、`apps/headscale/static/`、`apps/headscale/tests/browser/`、`routers/profiles.py`、`routers/operations.py` 仍只有 `f5223be` 那一檔有變。

## 10. 本片用到的決策

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-31（2026-11-15 17:4x 定，本片記進 `decisions.md`） | 面板用「帳號」；額外帳號範例名稱帶 id 前 8 碼；建立後自動切換；不做總覽與帳號層級權限 | 全部照做；預設帳號的範例名稱維持 `woow` |
| DQ-13（同時定，HM-10 記） | endpoint 全域一個、只存在預設帳號 | 額外帳號的端點唯讀並說明；fixture 對額外帳號 `PUT endpoint` 回 409 |
| DQ-14（同時定，HM-10 記） | 先撤銷並抹憑證再刪、孤兒不自動刪、面板列出可刪、不做軟刪除、兩段確認 | 兩段確認與後果文字；孤兒清單沒做：API 由 HM-10 定，面板由本片收尾做（第 11 節第 17 點、第 13 節） |
| DQ-16、DQ-17、DQ-18 | 名稱規則；標頭規則；帳號選擇只放記憶體 | 第 3 節 |
| DQ-40 (a) ①～⑤ | 必帶帳號、回聲、CRUD 寫入保護、名稱加嚴、只放記憶體 | 第 3 節 |
| DQ-02、DQ-12、DQ-28 | 新帳號複製政策；索引壞時面板照開；OpenDesign 與 Odoo Manage 不開放 | 建立對話框的說明；索引壞的橫幅與只剩預設帳號；這兩個產品不顯示新增按鈕 |
| UC-10（主對話已定） | HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭 | 面板用標頭；備案路徑（契約 §3.7）沒做 |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 5 節；commit |

沒用到、也沒碰到待定題：DQ-21、DQ-25（HM-09）、DQ-30（HM-12）、DQ-45（`serverInfo.name`，HM-18）。

## 11. 照契約假設、要等 HM-10 對齊的地方（「收尾」做）

2026-11-16 逐點對 HM-10 真後端的核對結果在第 16.3 節。

1. 開通的產品對不帶標頭的 bootstrap 回 400 `profile_id_required`（角色檢查之後）；面板靠它探測開關。
2. 回聲照 HM-05 的 `gateway.echoed()`：bootstrap `profile:{id,label,is_default}`＋`profiles_supported:true`，其他成功回應 `profile:{id}`；錯誤回應的回聲面板不看。
3. `GET /api/profiles`：`{"profiles":[列…]}`，索引 ETag 在 `ETag` 標頭（`"p1-<64 hex>"`）；最多 6 列、剛好一列預設帳號（label `Default`）；列的欄位照契約 §3.6。
4. `POST /api/profiles`：本體剛好 `{"label"}`；CSRF＋If-Match（索引）＋Idempotency-Key；201 本體是該列的欄位（最上層）＋`operation`；同 key 重送 200 同一列；不回 token（面板也不看）。
5. `PATCH /api/profiles/<id>`：`{"label"}`＋If-Match；200 該列（名稱沒變的改名面板不送）。
6. `DELETE /api/profiles/<id>`：沒有本體；If-Match＋Idempotency-Key；200 `{"deleted":"<id>","operation":…}`。
7. 帳號增刪的收據種類名 `profile.create`、`profile.delete`（契約沒寫）。
8. 全域收據沒有查詢路徑（契約沒寫）：帳號增刪的待確認卡只能重送或結束追蹤。HM-10 若提供查詢路徑，收尾時加「查詢」。
9. 哪些拒絕發生在記下意圖之前：面板對 `config_conflict`、`config_revision_required`、`operation_id_required`、`operation_id_invalid`、名稱、上限、記憶體、port、產品不支援、預設帳號不可改、`profile_not_found` 釋放帳號增刪的識別碼。
10. 帳號路由的 CSRF 取自預設帳號的 bootstrap（CSRF 由共用的 AdminAuthority 發，HM-05）；讀不到的帳號因此仍可刪。
11. 額外帳號的 bootstrap 帶全 add-on 的 endpoint；額外帳號 `PUT endpoint` 409 `endpoint_global`。
12. 預設帳號的 bootstrap 帶 `profile_index_state`；索引壞時清單 503 `profile_index_corrupt`、額外帳號範圍請求 503 `profile_index_corrupt`、預設帳號照常。
13. `profile_unavailable` 的帳號：帳號範圍請求 503 `{"error":"state unavailable"}`、列的 `disabled_reason` 是 `profile_unavailable`、仍可刪。
14. 錯誤代碼只在契約寫的狀態碼下才認（例如 `profile_not_found` 只認 404）；`detail` 只取 `limit`、`required_memory_mib`、`available_memory_mib` 三個整數。
15. `status`、`blocked_reason`、`disabled_reason` 的值照契約 §3.6；不認得的值只顯示「未知狀態」或「已停用」。
16. 回應裡的 `profile` 鍵只用在回聲；HA 既有回應沒有這個鍵（已核對 `gateway.py`）。
17. DQ-14「孤兒在面板列出可刪」：契約沒有孤兒清單的形狀，本片沒做。孤兒（索引沒有的 24 hex 目錄）和隔離目錄是兩件事（契約 §1.1）：
    孤兒清單的 API 由 HM-10 定，面板由本片收尾做（計畫 §17 把 FM-23 排給 HM-07、HM-10、HM-11）；隔離目錄、全部撤銷、還原核對卡、索引隔離的按鈕是 HM-13c／HM-10（審查 S-9）。
18. 沒開通但有帳號資料時 bootstrap 的 `dormant_profiles`（「休眠帳號 N 個，權杖已撤銷」）：面板顯示是 HM-13b／HM-13c，本片沒做（單帳號模式不看這個鍵）。
19. **帳號增刪先 replay 再比 If-Match**（審查 S-5 第 1 點）：面板遇到 `config_conflict`、`profile_not_found` 會釋放帳號增刪的識別碼，這只有在伺服器「同一個 key 先回收據」時才對。
    現有 token 操作就是這個順序（`gateway.py:612-620` 先 replay，`:621` 才比 ETag）。HM-10 若先比 If-Match，建立成功但回應遺失後重送會拿到 409，面板會說「未送出任何變更」並丟掉識別碼，帳號其實已建好。
    刪除重送同理：先 replay，再查帳號存不存在。面板這邊已先補一層：重送刪除回 `profile_not_found` 時，說的是要刪的帳號（`842dfed`）。
20. **探測的 400 每次開面板都會出現一次**（審查 S-5 第 2 點）：瀏覽器 console 會記一筆 `Failed to load resource: 400`。HM-10 不要把 `profile_id_required` 記成 WARNING 以上；
    HM-18 在 DOCS 的疑難排解寫明這是預期行為。
21. **清單列數上限 6 與 id 不重複**（審查 S-5 第 3 點）：面板任何一列不合規就整份拒絕（S-2）。HM-10 若把隔離或孤兒也列成清單列（契約 §3.6 的 `disabled_reason` 有 `quarantined`），
    列數或 id 可能超出面板的假設；收尾時兩邊一起定。

## 12. 待 HM-03a 確認（含 HM-03b 指給本片的 UC-14）

| 項目 | 本片怎麼處理 | 要量什麼 |
|---|---|---|
| UC-10：Ingress 轉送 `X-MCP-Profile` 與 PATCH／DELETE | 照主對話的決定先用標頭；沒轉送時第二次 bootstrap 仍 400，面板顯示「可能是 Home Assistant 沒有轉送帳號標頭」，不無限重試 | 真 HAOS 上兩段 Ingress 是否原樣轉送這個標頭與兩個方法；不行就照契約 §3.7 改路徑（面板與 P9 kit 同版改） |
| **瀏覽器拿不拿得到帳號清單的 `ETag`**（優先：任何產品開通前一定要量） | 面板從 `ETag` 標頭讀索引版本。**拿不到或格式不符時，整個面板（含預設帳號、含撤銷權杖）無法使用**（審查實驗 E7；S-2 留到收尾修） | Ingress 是否把 `ETag` 傳給瀏覽器。另外推論（未實測）：使用者自己的反向代理（例如開 gzip 的 NGINX、Cloudflare）壓縮回應時，可能把強 ETag 改成 `W/"…"`，面板目前也不收。要一起量；會掉或變弱的話，請 HM-10 在清單本體另帶版本，面板優先讀本體 |
| HA App 的 WebView 支援的 Unicode 版本 | 名稱規則用瀏覽器的 `\p{Cn}`；伺服器用 Python 3.13（Unicode 15.1）。比 15.0 舊的 WebView 會把伺服器收下的名稱（例如 U+1FAE8）當成未指派字元，整份清單被拒、整個面板鎖住（審查實驗 E2；S-2） | iOS、Android 的 HA App WebView 與常見桌面瀏覽器的 Unicode 版本 |
| HA 前端 iframe 裡的 `<select>`、`<dialog>`、`\p{…}` 正規式 | 既有面板已用 `<dialog>`；`\p{…}` 需要 Chrome 64、Safari 11.1、Firefox 78 以上 | 實機（含手機 App 的 WebView）開啟面板、切換帳號 |
| UC-14（HM-03b）：面板重新整理後 Ingress iframe 的落點 | DQ-18 讓重新整理一定回預設帳號，落點只影響停在哪一頁 | 重新整理後 iframe 停在原頁還是總覽；有沒有回到別的 Ingress 工作階段 |

## 13. 交給後面的片

- **HM-10（與本片收尾）**：第 11 節逐點對齊；真後端下 node 與 Playwright 照跑（fixture 照真後端修正）；`tests/integration_local_runtime.py` 視需要加兩帳號（FM-98）。
- **本片收尾（HM-10 合併後、任何產品開通前）要做**：
  - S-2：fail closed 的範圍縮小。名稱不合規時這一列照列，名稱改顯示固定字，這一列仍可切換、改名、刪除；id、port、`is_default` 不合規或 id 重複照舊整份拒絕。
    清單讀不到或格式不符時，比照 `profile_index_corrupt`：預設帳號照常可用、新增／改名／刪除停用、顯示固定橫幅（不是「確認管理權限」）。
    **替代清單要標記**（像 `corrupt`），不能被當成「帳號已刪除」：`show()` 的「剛離開的帳號不在清單」檢查（`842dfed`）與「目前帳號不在清單就當 `profile_not_found`」都會用到。
    索引版本照 HM-10 的決定，從本體或 `ETag` 讀（第 12 節）。
  - 孤兒清單的面板（DQ-14；第 11 節第 17 點）。
  - 第 11 節第 8 點：HM-10 若提供全域收據查詢，帳號增刪的待確認卡加「查詢」。
- **HM-18（或 HM-10）改 `contract.md`**：
  - §9 #85 的「待決（DQ-31）」改成已定；#56 的「DQ-31 面板細節待定」拿掉。
  - #55 改寫成「其他操作進行中選單停用；切換中只剩選單可用，再選一次取代前一次切換」（審查 S-3）。
  - §9 補一列「刪除確認」：PaaS 一段（`components/ProfileChooser.jsx` @`69ac425` 只有「Confirm delete profile」），HA 兩段（DQ-14）（審查 S-3）。
  - §3.3 補例外：每次開面板的第一個 bootstrap 刻意不帶標頭，靠 400 `profile_id_required` 探測開關（I12 仍成立）（審查 S-3）。
  - #84 補：被刪帳號的待確認收據在每條得知路徑都清掉（第 3.3 節的五條）。
  - §3.1 帳號增刪的收據種類名與全域收據查詢（第 11 節第 7、8 點）；DOCS 寫明探測的 400 是預期行為（第 11 節第 20 點）；§10 變更紀錄。本片沒改契約，避免和 HM-10 衝突。
- **HM-13c**：還原與休眠核對卡、全部撤銷、隔離目錄刪除、`restore_review_required` 文案；`profiles.js` 照帳本列管規則接著改。
- **HM-16**：`ha_p9_driver.mjs` 的帳號參數（`createP9AdminClient(…, {profile})` 已就緒）、交叉矩陣。
- **HM-12**：`token_rotated` 提示與 422 文案（`Hui/app.js`）。
- **待決**：DQ-45（`serverInfo.name` 要不要帶 id）由 HM-18 問；DQ-13、DQ-14、DQ-30 由 HM-10、HM-12 寫進 `decisions.md`。

## 14. 驗收條件（計畫 §12.3 HM-11，這一階段）

| 條件 | 結果 |
|---|---|
| `unit.sh` 的 node＋Playwright 綠 | 本機通過：node 74 案、build-closure、Playwright 102 案（第 5.1 節）。CI 待 PR |
| 開關關時既有 9 個 spec 不改照過 | 通過：9 個 spec 檔沒有改；`single` 專案 71 案全過；四個 spec 另在 `profiles-on` 原封不動照過；開關關時 DOM／請求／紀錄和 `b5d10c5` 逐項相同（第 5.3 節），CI 由 MF-1 案例守住 |
| 舊格式收據案例過 | 通過：node「a record the previous panel left (4 keys)…」與 Playwright「a receipt kept across the upgrade…」 |
| 多帳號 spec（切換、建立後切換、刪除兩段確認、token 不外洩到別帳號、晚到回應丟掉） | 通過：`tests/browser/profiles.spec.mjs` 11 案 |
| 測試先寫、先紅後綠 | 通過：第 4 節（`507314d` 那段沒有先紅，已補紅的紀錄；MF-1 與索引壞那段用突變證明） |
| 同一系列 commit 更新帳本；新模組列管 | 通過：`ff49bd0`、`cef2d7c`、`4f86a8f`；帳本預檢 OK |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過（第 8 節）；秘密預檢 0 命中 |
| 獨立安全審查 | 已做：修正後通過（`wave4/review-HM-11.md`）；處理見第 15 節 |

## 15. 安全審查意見處理

| 編號 | 審查意見 | 處理 | commit |
|---|---|---|---|
| MF-1（必修） | 「開關關時 DOM 不變」沒有 CI 守門（突變 M14、M15 存活） | **已修**。`profiles.spec` 加「switched off」案例（EMQX）：逐頁走過總覽、後端連線、工具權限、連線與權杖、診斷與維護；開「顯示權杖」與「套用工具權限？」兩個確認框；按「重新整理狀態」。斷言帳號介面（`#profile-select`、`.profile-bar`、`.profile-current`、`.profile-scope`、`.profile-note`、`.dialog-profile`、兩張帳號卡）數量 0、沒有帳號字樣、重啟說明是整個子行程、範例名稱 `woow`、請求剛好是兩輪 bootstrap＋capabilities 且不帶標頭、fixture 沒收到變更。比審查員的版本多查字樣、請求清單與 fixture 紀錄。突變 N01（＝M14）、N02（＝M15）與 N03～N08 都被擋（第 4 節）。CI 約多 1.7 秒 | `3e32c2f` |
| S-1 | 面板刪除有待確認收據的帳號後，收據留著、提示叫人切回 | **已修並補完**。抽出 `forget(id)`：面板刪除、重送確認刪除、別處刪除三條路徑（`a6871c2`）。核對時另找到兩條：切換時新清單已沒有剛離開的帳號；重送刪除回 `profile_not_found`（原本說「帳號「預設帳號」（default）已不存在」，要刪的帳號的收據也沒清）（`ded9d01` 先紅、`842dfed`）。索引壞的替代清單不算刪除（`155022e`）。文件與帳本用字跟著改（`4f86a8f`、`038de6f`） | `3e32c2f`、`a6871c2`、`ded9d01`、`842dfed`、`155022e` |
| S-2 | 一列名稱不合規或清單少 ETag，整個面板（含預設帳號）無法使用 | **2026-11-16 對齊時已做**（第 16.2 節第 15 點）。原本的處理：**留到收尾**（HM-10 合併後、任何產品開通前；第 13 節寫了做法）。理由：(1) 清單形狀（列數、id 唯一、隔離或孤兒列，S-5 第 3 點）與索引版本放 `ETag` 還是本體，都是 HM-10 定，現在對 fixture 做可能要重做；(2) 替代清單要有標記，不能被當成「帳號已刪除」而清掉收據（本片 `842dfed` 的檢查已依賴這個），要和真後端的狀態一起設計；(3) 開關是空的，單帳號面板根本不讀清單（MF-1 案例守住），開通前不會有客戶碰到；(4) CI 時間。第 12 節把 `ETag` 與 WebView Unicode 列為開通前必量，並補一個推論：反向代理壓縮可能把 ETag 改成 `W/"…"` | — |
| S-3 | 契約要補三個和 PaaS 的差異 | **已處理**：寫進第 13 節的交接清單（刪除兩段確認、探測例外、#55），另加 #84 的收據路徑 | 本筆記 |
| S-4 | 開通後帳號範圍的 204 不經回聲比對 | **已修**：開通後帳號範圍 204 一律當回聲不符；開關關與全域路徑照舊。node 加一案（先紅） | `3e32c2f`、`a6871c2` |
| S-5 | 交給 HM-10 的三點 | **已處理**：第 11 節第 19～21 點。第 1 點已核對 `gateway.py:612-621`（先 replay，後比 ETag）。面板這邊先補一層：重送刪除回 `profile_not_found` 時說的是要刪的帳號 | 本筆記、`842dfed` |
| S-6 | 待 HM-03a／b 確認的清單要補兩項、改一項 | **已處理**：第 12 節補 UC-14 與 WebView 的 Unicode 版本；`ETag` 那列改寫影響（整個面板無法使用）並提高優先順序；另補反向代理把 ETag 改弱的推論 | 本筆記 |
| S-7 | provenance、帳本與文件幾處不準 | **已處理**：(1) fixture 說明改成「除了 `owner_defaults_unavailable` 對齊形狀 C」（第 3.4 節；`6ba92bb` 的 commit 訊息不改寫歷史，以本筆記為準）；(2)(3) 帳本 api.js 改成「before any change is sent」、contracts.js 改成「單帳號時行為不變」並寫明指紋多一個 `null`（`cef2d7c`）；(4) 寫入契約文件第一段補「單帳號與預設帳號」（`1339843`）；(5) decisions.md 變更紀錄把 HM-11 那列移到最後（`0eed62a`） | `cef2d7c`、`1339843`、`0eed62a`、本筆記 |
| S-8 | `507314d` 沒有先紅的紀錄 | **已處理**：第 4 節寫明「這段沒有先紅」，並補做紅的紀錄（舊程式上 FM-64 斷言失敗；FM-98 斷言守的是既有行為） | 本筆記 |
| S-9 | DQ-14「孤兒在面板列出可刪」沒有負責片 | **已處理**：API 由 HM-10 定，面板由本片收尾做（計畫 §17 的 FM-23）；隔離目錄是另一件事，仍是 HM-13c（第 11 節第 17 點、第 13 節） | 本筆記 |

審查第 8 節的其他觀察：分支的上游設成 `origin/claude-delivery`、`push.default` 沒設，開 PR 時要明確 `git push -u origin feat/ha-multiprofile-hm11-20261115`（列在 PR 說明的「開 PR 前要做」）。

## 16. rebase 到 HM-10 並對齊真後端（2026-11-16）

（本節正文的 commit 是 push 前改寫歷史之前的編號；`c8216d1` 起的對照見第 17.3 節，第 16.12 節已換成改寫後的編號。）

### 16.1 rebase

| 項目 | 結果 |
|---|---|
| 備份 | 先開本機分支 `backup/hm11-before-rebase-20261116`（指向 rebase 前的 `c251fbe`，沒有 push） |
| 新基準 | `git fetch origin feat/ha-multiprofile-hm10-20261115`，`FETCH_HEAD` 是 `684a2dd4f3d8931c0de85e1786ae502951078698`（HM-10 PR #104 的 head）；`b5d10c5` 是它的祖先，`git log 684a2dd..HEAD` 剛好是本片的 20 個 commit |
| 指令 | `git rebase 684a2dd`。重放 20 個，衝突 2 個，都在 `docs/multi-profile/decisions.md`；其餘 18 個 `git range-diff` 逐一相同 |
| `b567f68`（DQ-31） | 新基準的 #100（HM-08 補正 PR）已把 DQ-13、DQ-14、DQ-30、DQ-31 記成已定、題數 34／12。以新基準為底，只加回本片的變更：DQ-31 的結論寫成面板實際的做法（`woow-<產品>-<id 前 8 碼>`、預設帳號維持 `woow`、不做跨帳號總覽與帳號層級權限），變更紀錄加一列（2026-11-16）。commit 訊息照實際內容改寫（`e058882`）。對齊審查 S-9 之後，結論欄改回使用者採用的原句，面板的做法移到負責片欄（第 17.2 節） |
| `0eed62a`（變更紀錄順序） | 跳過（`git rebase --skip`）：它只把 HM-11 那列移到最後，上面的解法已經把新列放在最後 |
| 帳本 | 三個帳本 commit 自動合併。核對方式：新基準的 `runtime-patches.json` 與 rebase 後的只差 5 個面板檔（app.js、api.js、contracts.js、operation-identity.js、profiles.js），其他 57 列與 `scope` 逐字相同（收尾時重數：原本寫的 56 是算錯）；5 列的 SHA-256 照檔案實際內容重算全部一致（新基準沒有動面板檔，說明就是新基準的說明加本片的句子）。對齊後再釘一次（`2491f88`），建立名稱的修正後又釘一次（`04b4bce`） |
| 依賴 | `b5d10c5..684a2dd` 沒有動 `uv.lock`、`package-lock.json`、`pyproject.toml`、`requirements-ci.txt`：沒有重跑 `setup_repo_env.sh` |
| 其他衝突 | 沒有：HM-10 沒有碰 `packages/mcp-admin-ui/`、`packaging/ha_p9_admin.mjs`、`docs/admin-write-contracts.md` |

### 16.2 HM-10 交給 HM-11 的待辦（HM-10 筆記 §13.2）逐條

| # | 待辦 | 處理 |
|---|---|---|
| 1 | 每個帳號範圍請求都帶 `X-MCP-Profile`（含 `default`），比對回聲 | 早已做了（`26c7ec4`）。這一輪用案例核對：node「every management request the panel sends…」逐一比對面板送出的方法、路徑與標頭和案例（案例已對真後端錄過）；回聲的形狀由案例的 `profile` 欄位比對 |
| 2 | bootstrap 與變更兩個回應的回聲都比對 | 早已做了。調整兩點：`profiles_supported` 可以是 `false`（真後端對 OpenDesign、Odoo Manage 就是 false；原本會被當成回聲不符）；回聲的名稱只檢查形狀（不顯示，S-2） |
| 3 | 清單的 `orphans`（列出可刪） | 做了：「診斷與維護」列出、逐筆刪除（兩段確認），選單下方提示筆數；刪除時清掉它在這個分頁的待確認收據 |
| 4 | `profile_index_state:"corrupt"` 時「隔離帳號索引」，送 `profile_index_etag` | 做了：預設帳號的「帳號索引無法使用」卡片多一個按鈕；`If-Match` 原樣送 bootstrap 的值（含引號）、`Idempotency-Key`、CSRF，沒有本體、沒有 `X-MCP-Profile`；收據放帳號增刪的範圍（`profiles/quarantine`，4 鍵） |
| 5 | 刪除與隔離的兩段確認（DQ-14） | 刪除早已做了；隔離與孤兒刪除這一輪做（兩段，第一段寫明後果） |
| 6 | `profiles_supported:false` 不顯示新增 | 做了：新增按鈕改看 bootstrap 的 `profiles_supported`（原本看產品名稱），拿掉 `canCreateProfiles` |
| 7 | PATCH、DELETE 一定帶 CSRF | 早已做了。案例 `rename-without-csrf`、`delete-without-csrf` 錄下真後端 403；node 的請求比對確認面板有帶 |
| 8 | 建立的回應沒有 token，要另外 reveal | 早已做了（面板從不讀建立回應裡的 token；`createToken` 案例） |
| 9 | 建立重送回目前那一列；帳號已刪時只有 id | 做了：只有 `{id, operation}` 的重送算「已確認建立、但已被刪除」，識別碼清掉、說明、回預設帳號；其他形狀不算確認（識別碼保留） |
| 10 | `status`、`blocked_reason`、`disabled_reason` 的文字 | 早已做了，值和 HM-10 的一致（案例 `rows`）。HM-09 提到的「看門狗一直重試（`backoff`）要不要另外提示」：不另加，選單已顯示「退避等待」，總覽有子行程狀態 |
| 11 | fixture 照 HM-10 的回應形狀 | 做了（`35dfbdd`），並用案例證明一致（第 16.4 節） |
| 12 | `profile_limit_reached` 的 `limit` 可能是 0 | 做了：另一段文案（只服務預設帳號、刪除帳號也不會改變、請回報），不再說「最多 0 個」 |
| 13 | 隔離回 409 `config_conflict` 而索引仍是 `corrupt`：沒有索引檔可隔離，提示修好後重啟 | 做了：409 後重讀狀態，分三種說明：索引已可用；索引檔又變了（ETag 不同）；ETag 相同而仍是 corrupt＝沒有索引檔可隔離，請修好 `/data/mcp/profiles` 後重啟 add-on |
| 14 | 隔離拿不到某個帳號的鎖而 503（什麼都沒做） | 做了：說明另一個帳號的操作正在進行；識別碼保留（沒有代碼的 503 不能確定沒記下意圖），用「重送帳號操作」或重新整理後再試 |
| 15 | 清單的索引 ETag 只在回應標頭；拿不到時照審查 S-2 | 做了（S-2 一起）：清單沒帶格式正確的 `ETag` 照列但唯讀（新增、改名、刪除停用、說明）；清單讀不到或格式不合（除了 401／403、回聲不符與晚到的回應）不再鎖住整個面板，預設帳號照常可用、選單只剩預設帳號（與目前帳號）；這種替代清單（和索引壞時的一樣）不當成「帳號已刪除」的證據，沒帶 `ETag` 的清單仍是伺服器給的完整清單、照常算（對齊審查 S-7 改字）；瀏覽器顯示不了的名稱只藏那一列的名稱。`index_etag` 本體欄位照 HM-10 的決定先不做（HM-03a 實測拿不到才補） |

另外對齊時才發現、HM-10 筆記沒列的一點：**刪除的重送在帳號已被別處刪除時，真後端回 409 `config_conflict`、不是 404**（HM-10 先比索引
ETag 再找帳號；別處刪除一定改了索引）。面板原本只在 404 時說「帳號已不存在、不需要再刪除」並清掉它的收據（`368a53a`），對真後端會改成
說「設定已被其他操作更新」而收據留著。修法：重送刪除遇到 `config_conflict` 或 `profile_not_found` 時重讀清單，清單（不是替代清單）裡
已沒有這個帳號、也不是孤兒，才照「已不存在」處理；否則說清單已更新、沒有刪除。

收尾的自我檢查又找到兩點，都已修：

- **建立的回應也照清單規則讀名稱**（`39183dd` 先紅；`13bb1c8`、`04b4bce`、`4694e18`）：第 15 點把名稱規則放寬成「只藏那一列的名稱」
  之後，`createProfile()` 仍回傳回應裡的原始名稱，建立後的提示會把這個瀏覽器顯示不了的名稱顯示出來（放寬前這種回應會被當成沒有確認）。
  改成用清單規則讀過的那一列：顯示不了的名稱是 null，建立後與重送確認建立後的提示以 id 前 8 碼稱呼；帳本重新釘 app.js、api.js；README 補一句。
- **測試字串裡的原始雙向控制字元**（`f204761`）：`c8216d1` 與 `39183dd` 在 `profiles.test.mjs`、`browser/profiles.spec.mjs` 的字串裡
  各直接放了 2 個 U+202E（由右至左覆寫）。原始的雙向控制字元會讓編輯器與 GitHub 把那一行後面的程式顯示成另一種順序（Trojan Source），
  GitHub 的 diff 也會出警告；repo 其他測試都用跳脫寫法。四處改成跳脫寫法，字串值相同、測試內容不變。`684a2dd` 與最後 HEAD 的樹裡
  都沒有含雙向控制字元的文字檔（`git grep -P` 只碰到幾個 PNG 的位元組）。`39183dd` 的 commit 訊息也有一個 U+202E（只影響顯示）；
  要清掉得改寫它之後的 5 個 commit，當時沒有改（第 16.11 節）。對齊審查（S-5）之後，push 前已改寫：`c8216d1` 起的 commit 一開始就是跳脫寫法，
  訊息也是，`f204761` 因此變空、併掉（第 17.3 節）。

### 16.3 照契約假設的 21 點（第 11 節）對 HM-10 的核對

| 點 | 結果 |
|---|---|
| 1 探測的 400 `profile_id_required` | 成立（案例 `bootstrap-without-header`）；HM-10 說 ⑦ 的 400 不寫 log（第 20 點） |
| 2 回聲形狀 | 成立；另外：帳號動作「回傳」的錯誤 JSON（409 `config_conflict`、409 `owner_defaults_unavailable` 等）也帶 `profile:{id}`，「丟出」的拒絕（428、404 `operation_not_found`、409 `endpoint_global`、⑦ 的 400／404／503）不帶。面板不看錯誤回應的回聲，行為不變；fixture 照改 |
| 3 清單 | 成立，另有 `orphans`；ETag 在標頭 |
| 4～6 建立、改名、刪除 | 成立；成功與重送都另帶索引 `ETag` 標頭（面板沒用到）；建立的重送在帳號已刪時只回 id（第 16.2 節第 9 點） |
| 7 收據種類名 | 成立（`profile.create`、`profile.delete`），另有 `profile.index_quarantine` |
| 8 全域收據沒有查詢路徑 | 成立（HM-10 沒有開），待確認卡維持只能重送或結束追蹤 |
| 9 記下意圖之前的拒絕 | 成立：HM-10 的順序是索引不能用（503）→ If-Match（428；格式錯 409）→ Idempotency-Key（428、400、409 `operation_id_conflict`）→ 重送 → ETag 409 → 各路由的判斷，都在 `journal.begin` 之前。面板多釋放 `profile_index_corrupt` |
| 10 CSRF 取自預設帳號的 bootstrap | 成立（共用的 AdminAuthority） |
| 11 額外帳號的 endpoint | 成立（案例 `endpoint-B`、`bootstrap-B-shows-the-endpoint`） |
| 12 索引狀態 | 成立，另帶 `profile_index_etag`；索引不能用時任何額外帳號 id（含不存在的）都先 503，再看存不存在（fixture 原本先 404，已改） |
| 13 讀不到的帳號 | 成立（案例 `rows`：清單列 `profile_unavailable`／`failed`，bootstrap 503 `state unavailable`，刪除 200） |
| 14 代碼只在契約的狀態碼下認 | 成立（`PROFILE_CODES` 和契約第 4.1 節一致） |
| 15 列的值 | 成立 |
| 16 `profile` 鍵只在回聲 | 成立 |
| 17 孤兒清單 | 做了（第 16.2 節第 3 點） |
| 18 `dormant_profiles` | 仍是 HM-13b／c；面板沒開通時不看 |
| 19 先重送再比 If-Match | 成立（HM-10 審查核對過） |
| 20 探測的 400 不記 WARNING | 成立（HM-10 審查核對過）；DOCS 說明交 HM-18 |
| 21 清單 ≤6 列、id 不重複 | 成立：索引最多 5 個額外帳號（`profiles.MAX_EXTRA_PROFILES`），孤兒在另一個鍵 |

### 16.4 fixture 和真後端一致的證明

- `packages/mcp-admin-ui/tests/profile-api-cases.json`：10 個情境、93 個案例（對齊審查後 94 個，多了 `main/delete-gone-stale`，第 17.2 節 S-6），涵蓋面板開通後用到的每條管理路由（清單、建立、改名、
  刪除、索引隔離、bootstrap、configuration、capabilities、diagnostics、收據查詢、token reveal／rotate（含重送）、child/restart、
  endpoint、policy、owner-defaults）與面板要處理的每種拒絕（`X-MCP-Profile` 沒帶、兩個值、格式錯、不存在、孤兒、讀不到、索引壞；
  CSRF、If-Match、Idempotency-Key 缺或過期；名稱不合規、保留名稱、重名、本體格式錯；預設帳號不可改；上限（含 `limit` 0）、記憶體、
  port、產品不支援；同 key 不同請求；隔離時索引能用、ETag 不符、沒有索引檔；開關關）。每案記狀態碼、`ETag` 標頭的類別、本體的欄位名與
  型別（規則列的鍵比字面值：代碼、種類、狀態、名稱…；id 依角色；Idempotency-Key 依送出它的案例；ETag 與 revision 依類別）。
  帳號範圍的成功回應只比面板會讀的鍵（回聲、`csrf`、`endpoint`、`operation`、`token`…；單帳號那一大塊不在多帳號的範圍）。
- `tests/test_panel_profile_api_shapes.py`（pytest，`tests/multi_profile_runtime.py` 的正式 runtime、開關用 monkeypatch 開、HM-01 log
  掃描）逐案要求 `expect`：10 案（每個情境一案），最後 HEAD 的全套 pytest 裡合計 1.5 秒。`expect` 就是從它錄的：第一次在 repo 外用同一份程式跑出形狀（`SP:hm11-align/
  gen_shapes.py`，不 commit），寫進案例檔，再在共用鎖下用 pytest 正式跑一次全綠（`SP:hm11-align/gen1.log`，13:39）。
- `tests/browser/profile-api-parity.spec.mjs`（Playwright，只用 request、不開瀏覽器頁面）讓 fixture 跑同一份案例、比同一份 `expect`：
  10 案約 2.7 秒（最後 HEAD）。兩個測試的比對規則一樣（都讀案例檔的 `rules`）。
- 面板那一側：node「every management request the panel sends…」確認面板送出的 14 種請求和案例的方法、路徑、標頭集合、本體鍵一致；
  Playwright 讓面板對已對齊的 fixture 跑（`profiles.spec` 15 案、四個既有 spec 的 `profiles-on`）。所以「面板 → fixture → 真後端」
  兩段都有測試守住。
- 真後端以後變了：Python 測試會紅並印出新的形狀；照它改 `expect`，Playwright 那一案會紅，再改 fixture 與面板。

### 16.5 先紅後綠

| 檢查 | 紅 | 綠 |
|---|---|---|
| `profile-api-parity.spec`（`c8216d1` 的測試）對對齊前的 fixture（`959591d` 的 `fixtures/server.mjs`） | 10 個情境 8 個紅（`limit`、`memory` 兩個本來就一致）；差在：沒有 `orphans`、沒有索引 ETag 與 `profile_index_etag`、沒有隔離路由、建立改名刪除的檢查順序、索引壞時先 404、錯誤的形狀與回聲、開關關時 `/api/profiles` 不是 404、回應沒有 `ETag` | `35dfbdd` 起 10 案全過 |
| `test_panel_profile_api_shapes.py` 對真後端 | 不會紅：`expect` 就是真後端的形狀（它是基準） | 10 案全過 |
| node `profiles.test.mjs`（`c8216d1`）對對齊前的面板 | 新加的 `indexState`、`orphanIds` 還沒有，整檔載入失敗（59 案：58 過、1 檔失敗）；在拋棄式複本補兩個空的 export 再跑：22 案 7 紅（回聲名稱形狀、隱藏名稱與孤兒與沒有 ETag、`profiles_supported` false、建立重送只回 id、索引隔離、limit 0、請求和案例一致） | `5ea7850` 起 22 案全過 |
| Playwright `profiles.spec`（`c8216d1`）對對齊前的面板與 fixture | 15 案 5 紅（S-2 那案、孤兒、索引隔離、沒有 ETag／不支援的產品／limit 0、建立重送時帳號已刪） | `5ea7850` 起 15 案全過 |
| 對齊前的面板對對齊後的 fixture（全套 Playwright） | 116 案 6 紅：上面 5 案，加上「deleted elsewhere…resending its delete」（真後端的順序回 409，面板說「設定已被其他操作更新」、收據留著） | `5ea7850` 起 116 案全過 |
| node `profiles.test.mjs`（`39183dd` 的測試）對 `405643f` 的面板（建立的名稱） | 22 案 1 紅：建立回應的名稱這個瀏覽器顯示不了時，回傳的 label 應是 null，實際是原字串（`red-node-created-label.log`） | `13bb1c8` 起 22 案全過 |

紅的紀錄大多在拋棄式複本（`git archive` 出 `959591d` 的樹，只蓋上新測試）跑，跑完刪掉；log 在 `wave4/evidence-align-HM-11/`。有兩列是在 clone 本身跑的（對齊審查 S-8 指出，原本這裡寫成「都在複本」）：
- parity 那一列（`red-parity-old-fixture.log`）：堆疊路徑是 clone 本身。clone 的 reflog 顯示 `c8216d1`、`35dfbdd`、`5ea7850` 是 13:52 在 31 秒內接連 commit 的，跑的時候這些都還沒 commit，指不出是哪個 commit；工作樹的內容是新的 parity 測試＋對齊前的 fixture。失敗內容就是對齊前 fixture 和真後端的形狀差異，紅本身成立。
- 建立名稱那一列：在 clone 裡的 `39183dd`（測試已 commit、面板還沒改）直接跑。`f204761` 只改字串的寫法、不改行為，沒有先紅；改完重跑 node 80 案、Playwright 116 案全過。

### 16.6 本機檢查（一般使用者；`ha_env.sh` 給的 TMPDIR，跑完用完整路徑刪除；pytest 都排在共用鎖後面）

（這是對齊那一輪的數字；對齊審查處理後的數字在第 17.5 節。）

數字都在最後的程式與測試（`f204761`；之後的 commit 只改本筆記）上重跑過。node、build、build-closure、Playwright：2026-11-16
15:52～15:56，開始與結束時工作樹都乾淨、HEAD 都是 `f204761`（`04b4bce` 上 15:45～15:49 也全過一次，Playwright 3.7 分鐘）。

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 80 案全過、0.2 秒（rebase 前 74 案；新 6 案合計約 17 毫秒） |
| `npm run build` ＋ `node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`） | 116 案全過，3.9 分鐘（rebase 前 102 案、3.6 分鐘）；既有 9 個 spec 一個字沒改（對 `684a2dd`、`b5d10c5` 都是），`single` 71 案照過、四個在 `profiles-on` 20 案照過 |
| 新 Playwright 案 | `profile-api-parity.spec` 10 案 2.7 秒；`profiles.spec` 新 4 案 8.9 秒（孤兒 1.9、隔離 2.2、唯讀／不支援／limit 0 3.2、建立重送 1.6）；改過的 S-2 那案 2.1 秒 |
| 舊格式收據 | node「a record the previous panel left (4 keys)…」與 Playwright「a receipt kept across the upgrade (four keys, the old key)…」（2.4 秒）都過 |
| pytest（子集與全套） | 見第 16.6.1 節 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS（最後 HEAD） |
| 兩個預檢 | 見第 16.8 節 |

#### 16.6.1 pytest（子集與全套）

- 指令：`flock SP:wave1-pytest.lock env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rfEs`
  加 20 個檔：本片新的 `test_panel_profile_api_shapes`；HM-10 的 3 檔 `test_profile_admin_api`、`test_admin_pipeline_matrix`、
  `test_router_passthrough`；HM-01 黃金回歸與兩個契約凍結 `test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`；
  第 5.4 節的其餘 13 檔（`test_tool_inventory`、`test_ledger_precheck`、`test_owned_ui`、`test_owned_browser`、`test_owned_browser_ipc`、
  `test_owned_browser_redirect`、`test_admin_ui`、`test_identity_fields`、`test_batch2_admin`、`test_n8n_selectors`、`test_b2_odoo_policy`、
  `test_writes_default_on`、`test_owned_ports_bearer`）。
- 子集結果：`5ea7850` 上 344 案全過、0 skip、93.5 秒（13:56 取得鎖）。最後的程式（`04b4bce`；和 `f204761` 只差 README 與兩個測試檔的
  字串寫法，pytest 都不讀）上 15:15 取得鎖再跑一次：**344 案全過、0 skip、88.4 秒**。其中本片新測試 10 案、HM-10 的 3 檔 86 案
  （32＋5＋49，和 HM-10 筆記一致）、HM-01 的 3 檔 45 案（17＋9＋19）。
- 本片新測試另在 13:39 單獨正式跑過一次：10 案全過、2.3 秒。
- 全套（`tests`，CI 的同一個指令加 `-rfEs --durations=30`，正式 conftest）：`f204761` 上 16:14 取得鎖、16:47 跑完，
  開始與結束時工作樹都乾淨、HEAD 都是 `f204761`。**5,783 案過、7 案失敗、0 skip，32 分 25 秒**。失敗的 7 案就是第 16.9 節要 root 的既有案例（`test_owned_executable` 1、`test_profile_store` 1、`test_restore_detection` 5）。
  上面子集的 20 個檔在全套裡也全過（344 案）。
- 14:00～14:33 另跑過一次全套（5,783 過、7 失敗，同樣是那 7 案），但那時工作樹正在改建立名稱的修正，不算最後 HEAD 的證據。

### 16.7 CI 時間

新測試本機合計約 13 秒（最後 HEAD：Playwright 11.6 秒＝`profile-api-parity.spec` 2.7＋`profiles.spec` 新 4 案 8.9；pytest 1.5 秒；
node 約 0.02 秒），推估 `checks` 多不到 0.3 分鐘（Playwright 共用同一個 worker 與 fixture，沒有多開瀏覽器）。rebase 前推估本片多約 1.0 分鐘，合計約 1.3 分鐘；`checks` 目前約 28～35 分鐘、上限 60 分鐘。

### 16.8 預檢

| 預檢 | 指令 | 結果（最後 HEAD） |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 684a2dd --head HEAD --full` | OK，0 命中（gitleaks 8.28.0；`684a2dd..HEAD` 32 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 684a2dd` | OK：`runtime-patches.json` 175 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的 22 個檔裡 5 個由帳本釘住（app.js、api.js、contracts.js、operation-identity.js、profiles.js）、帳本本身有改；沒有帳本沒列的新執行檔 |

`04b4bce` 上也各跑過一次，結果相同（秘密預檢那時是 29 個 commit）。

### 16.9 只在 CI 跑的測試

- 這一輪新增與改過的測試都在本機跑過、全過，沒有只在 CI 跑的新測試。
- 已知要 root、本機一定失敗的既有案例（同第 6 節）：`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5。

### 16.10 待 HM-03a／b 確認（第 12 節照舊，這一輪的變化）

- 瀏覽器拿不到清單的 `ETag`：原本整個面板無法使用，現在照列但唯讀，預設帳號與各帳號設定照常可用；仍要量（拿不到就不能新增、改名、刪除）。
- HA App WebView 的 Unicode 版本：原本整份清單被拒，現在只藏那一列的名稱；仍要量。
- 隔離帳號索引的 `If-Match` 是 bootstrap 本體裡的值（含引號）原樣送：和其他 `If-Match` 一樣靠 Ingress 原樣轉送請求標頭（UC-10 那一組）。
- UC-10（`X-MCP-Profile`、PATCH、DELETE）、iframe 裡的 `<select>`、`<dialog>`、`\p{…}`、UC-14（重新整理後的落點）照第 12 節。

### 16.11 交給後面的片

- **HM-12**：`token_rotated` 提示與 422 文案（`Hui/app.js`），照計畫疊在本片上。
- **HM-13c**：還原與休眠核對卡、全部撤銷、隔離目錄（`.quarantine-*`）的刪除；隔離目錄可以放在本片的「孤兒帳號資料」卡片旁邊。索引隔離之後，原本帳號的
  待確認收據留到刪除那筆孤兒資料時才清（孤兒不能切換、看不到它的收據；本片沒有在隔離成功時一起清）。
- **HM-18**：契約第 3.3 節「面板每個帳號範圍請求都帶」改寫成有探測例外（本片補了 #110）；#55、#56、#84、#85 的用字；DOCS 寫探測的 400、
  孤兒、索引隔離、清單唯讀與隱藏名稱。要不要把管理面的資料案例做成正式的契約檔時，可以從 `profile-api-cases.json` 開始。
- **HM-16**：P9 driver 的帳號參數與交叉矩陣（`createP9AdminClient(…, {profile})` 已就緒，這一輪沒改）。
- **主對話**：契約第 9 節的新列是 #109～#112（對齊時是 #101～#104、接在 #100 後面；HM-31 先合併、用掉 #101～#108，rebase 後改號，第 18 節）；HM-13b、HM-30 若也在 #108 後面加列，後合併的要重排列號。
- **主對話（開 PR 前）**：對齊這一輪（`c8216d1`～`f204761`）還沒有獨立安全審查（第 16.13 節）；`39183dd` 的 commit 訊息含一個
  U+202E（第 16.2 節），要不要在 push 前改寫由主對話決定。兩件都已處理：審查做了（第 17 節），U+202E 在 push 前改寫拿掉（第 17.3 節）。

### 16.12 commit（`684a2dd` 之後）

對齊審查後在 push 前改寫過歷史（第 17.3 節）：下表是改寫後的編號，括號裡是改寫前的。每一對的差別只有兩個測試檔的原始 U+202E
換成跳脫寫法（`39183dd` 另有訊息裡的一個），作者、時間與其他內容都相同。

| commit | 內容 |
|---|---|
| `d4a0d4b`～`959591d`（19 個，沒有改寫） | rebase 前的 20 個 commit 重放：18 個逐一相同；`b567f68` 以新基準為底改寫成 `e058882`（DQ-31 的結論寫成面板實際的做法；對齊審查 S-9 後改回原句，第 17.2 節）；`0eed62a` 跳過（第 16.1 節） |
| `cc57bde`（原 `c8216d1`） | 測試：案例檔、真後端的 Python 測試、fixture 的 Playwright 比對、node 新 6 案、`profiles.spec` 新 4 案與 S-2 那案（先紅） |
| `895d70a`（原 `35dfbdd`） | fixture 照 HM-10 改 |
| `fc9d3cb`（原 `5ea7850`） | 面板：孤兒、索引隔離、清單不能用時不鎖、`profiles_supported` false、建立重送只回 id、limit 0、刪除重送的 409 |
| `61f30a0`（原 `2491f88`） | 帳本重新釘 app.js、api.js、profiles.js、operation-identity.js |
| `552af33`（原 `653c02d`） | 契約第 9 節 #109～#112 與變更紀錄；decisions.md 的 DQ-12、DQ-14 負責片 |
| `db5b0b3`（原 `bca1883`） | README 與寫入契約文件 |
| `931107e`（原 `405643f`） | 本筆記第 16 節（初版） |
| `2c2a30d`（原 `39183dd`） | 測試：建立回應的名稱這個瀏覽器顯示不了時不往下傳（先紅） |
| `c7ed817`（原 `13bb1c8`） | 面板：建立的那一列照清單規則讀，提示以 id 前 8 碼稱呼 |
| `805a2cb`（原 `04b4bce`） | 帳本重新釘 app.js、api.js |
| `0480d8d`（原 `4694e18`） | README：建立後的提示也只以 id 前 8 碼稱呼。改寫後它的樹就是原 `f204761` 的樹（`c073ed5`） |
| （原 `f204761`，已併掉） | 測試：四處原始 U+202E 改成跳脫寫法。改寫後前面的 commit 一開始就是跳脫寫法，這個 commit 變空，用 `--prune-empty` 拿掉 |
| `214c192`（原 `8421269`） | 本筆記：第 16 節補最後 HEAD 的檢查、預檢、驗收狀態與上面兩點修正（樹和原 `8421269` 相同，`4e83684`） |
| 第 17.7 節 | 對齊審查的處理 |

第 2 節「沒改」清單在對齊後的變化：新增 pytest 測試 `tests/test_panel_profile_api_shapes.py`（不是正式程式）；`docs/multi-profile/contract.md`
加了第 9 節 #109～#112 與一列變更紀錄（rebase 到 `df686dd` 後接在 HM-31 的 #108 後面；對齊時是 #101～#104，接在 #100 後面）。其他照舊：沒有動 `packages/mcp-admin-core/`、`apps/`、`conftest.py`、`addons/<x>/`、
版號、CHANGELOG；`MULTI_PROFILE_PRODUCTS` 仍是空集合。

### 16.13 驗收條件（計畫 §12.3 HM-11，對齊後）

| 條件 | 結果 |
|---|---|
| `unit.sh` 的 node＋Playwright 綠 | 本機通過（對齊那一輪的 HEAD）：node 80 案、build-closure、Playwright 116 案；對齊審查處理後見第 17.5 節。CI 待 PR |
| 開關關時既有 9 個 spec 不改照過 | 通過：9 個 spec 檔對 `684a2dd` 沒有改；`single` 專案 71 案全過；四個另在 `profiles-on` 原封不動照過（20 案）；`profiles.spec` 有開關關的逐頁案例（MF-1） |
| 舊格式收據案例過 | 通過：node 一案、Playwright 一案（第 16.6 節） |
| fixture 和真後端一致（任務第 4 點） | 通過：第 16.4 節（93 個案例，對齊審查後 94 個；Python 對真後端、Playwright 對 fixture、node 對面板送出的請求） |
| 獨立安全審查 | 兩輪都做了：fixture 階段（修正後通過，第 15 節）；對齊這一輪（通過、沒有必修、建議 10 項，第 17 節） |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點）、兩個預檢 | 通過：案例檔的 id 是重複字母、過期 ETag 全 0、端點是 `.invalid`，Idempotency-Key 在執行時產生；秘密預檢 0 命中、帳本預檢 OK（第 16.8 節） |

## 17. 對齊後的獨立安全審查與處理（2026-11-16）

### 17.1 審查

- 報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-11-align.md`（審查 `8421269`＝改寫歷史後的 `214c192`，同一棵樹；
  證據 `wave4/evidence-review-HM-11-align/`）。判定：**通過，沒有必修**；建議 10 項（S-1～S-10），另有 5 點觀察（報告第 3.1 節）。
- 審查員重跑作者的數字全部對上；41 個突變擋住 32 個。存活的 9 個：U06b 可接受（載入頁換掉整頁）；F06、F07 是 fixture 對真後端的覆蓋；
  其餘 6 個都是「程式現在對，但沒有測試守住」。
- 先核對再處理，審查的事實都成立：S-5 用 `bidi_scan.py` 逐 commit 重數（和審查一樣，13 個 commit）；S-7 讀 `readProfiles()`
  （沒帶 ETag 的清單沒有標 `substitute`）並在 HEAD 用斷言確認；S-8 用 PaaS 的唯讀 `git log`／`git show`、紅 log 的堆疊路徑與 clone 的
  reflog；S-9 對 `684a2dd` 與計畫 §13.2 比對；S-1～S-4、S-6、S-10 用審查員的突變跑新測試（第 17.4 節）。
- 處理的證據：`wave4/evidence-fix-HM-11-align/`（`tools/` 是用到的腳本，副檔名多加 `.txt`；`rewrite/`、`mutations/`、`checks/` 是 log）。

### 17.2 意見處理

| 編號 | 審查意見 | 處理 |
|---|---|---|
| S-1 | 重送刪除遇 409 而帳號其實還在：沒有測試（U24 存活） | **採用**。審查員的 G1 改成獨立案例「a resent delete refused while its profile still exists…」：B 有待確認收據、刪除的回應遺失；C 在別處改名，索引變了；重送得到 409。斷言提示是「帳號清單已被其他操作更新，這次沒有刪除任何帳號」、沒有「已不存在」；仍顯示 B、選單仍有 B、B 的待確認收據留著；帳號增刪的待確認卡消失（那筆刪除的識別碼已釋放）；fixture 裡 B 還在，只收到一次被拒的 DELETE。U24 上只有這一案紅 |
| S-2 | 帳號增刪遇 `operation_outcome_unknown` 保留識別碼：沒有測試（U19 存活） | **採用**。node 一案：建立與刪除各遇 409 `operation_outcome_unknown`（HM-10 提交後失敗的回應，同一個 key 再送也是 409）；識別碼保留，送出的 Idempotency-Key 就是保留的那個。U19 上這一案紅 |
| S-3 | 任務中按上一頁會重畫出可用的選單，擋住切換的那一行沒有測試（U16 存活） | **採用**。G3 併進「a slow switch…」那案的最後：工具權限頁開始一個慢的讀取，按上一頁（popstate 重畫、選單可用），選 B 被拒、提示「請等目前的操作完成後再切換帳號」、選單回到預設帳號；讀取結束後仍是預設帳號。U16 上紅 |
| S-4 | 名稱當文字顯示，後端／工具頁的帳號說明與確認框的帳號行沒有守住（U15a、U15c 存活） | **採用**。G4 併進 XSS 那案（`menu: …`）：建立 HTML 樣子的名稱後，走後端連線、工具權限兩頁，帳號說明照文字顯示、整頁沒有 `img`；開「刪除帳號」的確認框，帳號行照文字顯示、整頁沒有 `img`，取消後回總覽，照原案往下。審查員用的是「儲存工具權限」的確認框；那案是 Odoo，改用刪除確認框，不靠工具列，帳號行是同一個 `profileLine()`。U15a、U15c 上都紅 |
| S-5 | 歷史裡的原始 U+202E，push 前要決定 | **採用 (a)**：push 前用 `git filter-branch` 改寫（第 17.3 節）。理由：還沒 push，這是唯一能改的時機；本片本來就要 rebase 到新的 `claude-delivery`，commit 編號反正會變；改寫只把那幾個字元換成跳脫寫法，最後的樹完全相同，可以逐 commit 驗證；備份分支留著原來的 commit |
| S-6 | 案例沒有釘住「刪除先比 ETag、再查帳號」（F07 存活）；F06 附註 | **採用**。`main` 情境在 `delete-replay` 之後加 `delete-gone-stale`（N 已刪、過期 If-Match、新識別碼）。expect 照 HM-10 的檢查順序寫 409 `config_conflict`、ETag `p1`，Python 測試對真後端跑過、一致（第 17.5 節），fixture 也一致。F07 在 `profile-api-parity` 的 `main` 紅，差的就是這一案（404 `profile_not_found`）。F06 照審查的附註記下、不改：案例的 bootstrap 投影不含各帳號的 state 欄位；面板只畫回聲已比對的 bootstrap，各帳號 state 的隔離由 HM-10 的測試守 |
| S-7 | 契約 #111「這幾種替代清單都不當成刪除證據」把沒帶 ETag 的清單也算進去，和程式不一致 | **採用**。#111 最後一句照審查的建議改，契約變更紀錄加一列；第 16.2 節第 15 點同步改字。另把審查員只記錄行為的 G5 改成斷言，併進「a list without its ETag…」那案：清單沒帶 ETag 時，從在別處被刪的 B 切回預設帳號，提示 B 已不存在、它的收據清掉。新突變 N1（把沒帶 ETag 的清單也當替代清單）上紅。程式不用改 |
| S-8 | provenance 第 9 節與第 16.5 節要更新 | **採用**。第 9 節補 `e6971c0`、`3b135ca`（閘道，不影響面板；PaaS 只用唯讀 git）；第 16.5 節照實寫：parity 那列在 clone 的工作樹跑（堆疊路徑與 reflog） |
| S-9 | DQ-31 的結論欄被改寫 | **採用**。結論欄改回使用者採用的原句（＝`684a2dd`＝計畫 §13.2）；面板的做法（`woow-<產品>-<id 前 8 碼>`、預設帳號維持 `woow`、不做跨帳號總覽與帳號層級的管理權限）移到負責片欄；變更紀錄那列跟著改 |
| S-10 | 上一輪 S-1 在面板刪除時的 `forget()` 沒有測試守住（P4 存活） | **採用**。「deleting asks twice…」加 `not.toContainText('可能已在其他分頁或由其他管理員刪除')`；G6b（刪除後清單讀不到）改寫後併進同一案的最後（另加帳號「稽核」）：清單讀不到時仍說已清除、不叫人切回、收據清掉。P4 上紅；把新加的那一句斷言拿掉再跑 P4（P4b），仍紅在 G6b 那段，兩段各自擋得住 |
| 觀察 1 | `profile_index_corrupt` 也釋放帳號增刪的識別碼 | **不改**：審查員也認為是合理的取捨（不釋放的話，待確認的建立會擋住唯一的出路「隔離帳號索引」）。交 HM-18 在 DOCS 提一句 |
| 觀察 2 | 隔離遇沒有代碼的 503 時說「另一個帳號的操作正在進行」，原因也可能是管理名額滿或列不出帳號目錄 | **留到之後（HM-13c）**：要改 `app.js` 的文案並重新釘帳本；這一輪只補測試與文件，不動列管檔。「沒有執行隔離」那部分是對的 |
| 觀察 3 | 回聲不符後重新探測，不提醒剛離開的帳號有待確認收據 | **接受**：影響低，切回去時待確認卡會出現 |
| 觀察 4 | 讀不到的帳號在「無法載入」頁的「刪除帳號」，清單沒帶 ETag 時按了沒有反應 | **接受**：要同時遇到清單沒帶 ETag 與帳號讀不到，極少見；交 HM-13c 一起看 |
| 觀察 5 | 重送刪除得到「帳號清單已被其他操作更新」後，選單仍是舊的清單版本，再刪一次會先拿到 409 | **接受**：文案已叫人先確認清單；之後要改，可以讓那一段直接用剛讀到的清單重畫（同樣要改 `app.js`） |

### 17.3 push 前改寫歷史（S-5）

- 備份：本機分支 `backup/hm11-before-bidi-rewrite-20261116` 指向改寫前的 `8421269`（沒有 push）。rebase 時開的
  `backup/hm11-before-rebase-20261116`（`c251fbe`）沒有動。`git filter-branch` 另外留下
  `refs/original/refs/heads/feat/ha-multiprofile-hm11-20261115`（也指向 `8421269`）：不是分支、沒有 push，照留。
- 指令：`FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --prune-empty --msg-filter 'python3 -I msg_filter.py' --index-filter 'python3 -I index_filter.py' -- 959591d..feat/ha-multiprofile-hm11-20261115`。
  `index_filter.py` 只看 `profiles.test.mjs`、`browser/profiles.spec.mjs` 兩個檔，把原始 U+202E 換成原 `f204761` 用的 `\u202e`；
  `msg_filter.py` 把訊息裡的換成同樣寫法。不用 `rebase -i`（這個環境不支援互動），也不手改。
- 驗證（`verify_rewrite.py`、`bidi_scan.py`）：
  - 改寫前後最後的樹相同（`4e83684`）；13 個 commit 變 12 個（`f204761` 變空，`--prune-empty` 拿掉）。
  - 每一對只差那兩個測試檔，而且「舊內容的原始 U+202E 換成跳脫寫法」正好等於新內容；訊息也一樣（只有 `39183dd` 有一個）；
    作者、提交者與時間都相同。
  - `684a2dd..HEAD` 逐 commit 數原始雙向控制字元：改寫前合計 38 個（每個 commit 樹裡的加總，加上訊息裡的 1 個），改寫後 0 個。
- 對照（`959591d` 之前的 19 個沒有改寫）：

| 改寫前 | 改寫後 | 內容 |
|---|---|---|
| `c8216d1` | `cc57bde` | 測試：案例檔、真後端的 Python 測試、fixture 比對、node 與 Playwright 新案（先紅） |
| `35dfbdd` | `895d70a` | fixture 照 HM-10 改 |
| `5ea7850` | `fc9d3cb` | 面板對齊 HM-10 |
| `2491f88` | `61f30a0` | 帳本重新釘 |
| `653c02d` | `552af33` | 契約 #109～#112、decisions.md 負責片 |
| `bca1883` | `db5b0b3` | README 與寫入契約文件 |
| `405643f` | `931107e` | 本筆記第 16 節（初版） |
| `39183dd` | `2c2a30d` | 測試：建立回應的名稱（先紅）；訊息裡的 U+202E 改成 `\u202e` |
| `13bb1c8` | `c7ed817` | 面板：建立的那一列照清單規則讀 |
| `04b4bce` | `805a2cb` | 帳本重新釘 |
| `4694e18` | `0480d8d` | README；改寫後它的樹就是原 `f204761` 的樹（`c073ed5`） |
| `f204761` | （併掉） | 原本只把四處原始 U+202E 改成跳脫寫法；改寫後前面一開始就是跳脫寫法 |
| `8421269` | `214c192` | 本筆記第 16 節補完（樹相同，`4e83684`） |

- 影響：先紅後綠的紀錄不變（JS 的 `\u202e` 就是那個字元，測試字串的值相同）。範圍內的 commit 訊息與第 16 節正文仍用改寫前的編號
  （和 rebase 後的作法一樣），以這張表對照；`wave4/evidence-align-HM-11/` 與審查報告也是改寫前的編號，備份分支讓它們在本機仍查得到。

### 17.4 先紅後綠（突變）

新斷言守的是現在已經對的行為，在現在的程式上本來就過（同 MF-1 的作法）；紅由突變證明。每個突變只改拋棄式複本（`cp -a` 出 clone，
用完刪掉），重 build，跑 node 全部與 `profiles.spec`＋`profile-api-parity`（`single`），跑完還原、確認複本回到原本的差異。
工具 `run_mutations.py`，定義 `mutations.json`，log 與總表 `summary.json` 在 `mutations/`。

| # | 突變（只改複本） | node | Playwright（26 案） | 紅在哪裡 |
|---|---|---|---|---|
| U24 | 重送刪除遇 409／404 不重讀清單，一律當「已不存在」（審查時存活） | 81 過 | 1 紅 | S-1 新案例：提示變成「帳號（01234567）已不存在，不需要再刪除…」 |
| U19 | 帳號增刪遇 `operation_outcome_unknown` 也釋放識別碼（審查時存活） | 80 過、1 紅 | 26 過 | S-2 的 node 案：識別碼不見了 |
| U16 | 其他操作進行中也接受切換（審查時存活） | 81 過 | 1 紅 | S-3 那段：提示變成「已切換到帳號「會計」…」 |
| U15a | 後端／工具頁的帳號說明改用 `innerHTML`（審查時存活） | 81 過 | 1 紅 | S-4 那段：說明裡的名稱少了標籤字面 |
| U15c | 確認框的帳號行改用 `innerHTML`（審查時存活） | 81 過 | 1 紅 | S-4 那段：帳號行的名稱少了標籤字面 |
| P4 | 在面板刪除後不呼叫 `forget()`（審查時存活） | 81 過 | 1 紅 | S-10 新加的那一句：出現「可能已在其他分頁或由其他管理員刪除」 |
| P4b | P4，且拿掉 S-10 新加的那一句斷言 | 81 過 | 1 紅 | G6b 那段：提示叫人「請切回該帳號查詢結果」（上一輪 S-1 的錯） |
| F07 | fixture 的刪除先查帳號、再比 ETag（審查時存活） | 81 過 | 1 紅 | parity `main` 的 `delete-gone-stale`：404 `profile_not_found`，應是 409 |
| N1 | 沒帶 ETag 的清單也當替代清單（新） | 81 過 | 1 紅 | S-7 那段：提示變成「前一個帳號…有尚未確認的操作；請切回該帳號…」 |

9 個都擋住，每個只紅在要守的那一案。審查時存活、這一輪沒處理的只剩 U06b（可接受）與 F06（附註）。

### 17.5 本機檢查（一般使用者；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉）

這一輪的測試與案例跑的時候還沒 commit；之後 commit 的內容和跑的時候相同（之後只改本筆記）。

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 81 案全過、0.2～0.3 秒（跑了兩次；對齊那一輪 80 案；新 1 案） |
| `npm run build`＋`node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`，`--output` 放 TMPDIR） | 117 案全過（`single` 97、`profiles-on` 20），3.8 分鐘（審查時 116 案、3.8 分鐘） |
| `profiles.spec` | 16 案，逐案加總 37.2 秒（審查時 15 案 34.1 秒）；新案 1.9 秒 |
| `profile-api-parity.spec` | 10 案全過、2.5 秒（94 個案例） |
| 形狀比對（真後端）`tests/test_panel_profile_api_shapes.py` | 10 案全過、2.35 秒（94 個案例，含新的 `delete-gone-stale`）。指令同第 16.6.1 節，只跑這一檔；17:53 排進共用鎖，18:23 才拿到（排了約 30 分鐘） |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| `scripts/tool_inventory.py` | exit 0 |
| 規則核對 | `git diff --stat 684a2dd..HEAD -- addons/ CHANGELOG.md upgrade-notes.yaml .github/` 與既有 9 個 spec 都 0 行；`MULTI_PROFILE_PRODUCTS` 是空集合；這一輪的 commit 身分都是 woowtech、沒有 AI 署名；`684a2dd..HEAD` 逐 commit 沒有原始雙向控制字元 |

pytest 其他檔沒有重跑：這一輪沒有動任何 Python，也沒有動它們讀的檔（它們讀 `Hui/contracts.js` 等原始碼，沒改）；案例檔只有形狀比對讀，
已重跑。對齊那一輪的子集 20 檔 344 案、全套 5,783 過（第 16.6.1 節）對同一份原始碼仍成立。

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 684a2dd --head HEAD --full` | OK，0 命中（gitleaks 8.28.0；`684a2dd..5aebade` 34 個 commit，另掃 HEAD 的樹與整段歷史）。本筆記 commit 之後再跑一次，結果記在 PR 說明 |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 684a2dd` | OK：`runtime-patches.json` 175 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的 22 個檔裡 5 個由帳本釘住、帳本本身有改（這一輪沒動列管檔，帳本不用改）；沒有帳本沒列的新執行檔 |

### 17.6 CI 時間

- 這一輪：`profiles.spec` 比審查時多約 3 秒（新案 1.9 秒；其餘是併進既有案例的幾段，各約 0.1～0.6 秒）；node 新 1 案約 2 毫秒；
  pytest 只多一個案例（同一個情境，毫秒級）。Playwright 全套仍是 3.8 分鐘，推估 `checks` 多不到 0.1 分鐘。
- 本片合計：Playwright 新案逐案加總約 73 秒（`profiles.spec` 37.2＋parity 2.5＋`profiles-on` 33.0），node 約 0.03 秒，pytest 約 2 秒；
  推估 `checks` 多約 1.3～1.4 分鐘（目前約 28～35 分鐘，上限 60 分鐘）。補的測試都併在既有案例或共用同一個 fixture，沒有多開瀏覽器。

### 17.7 commit（接在 `214c192` 後面）

| commit | 內容 |
|---|---|
| `4e0a770` | 測試：S-1 新案例；S-10、S-3、S-4、S-7 併進既有案例的斷言；S-2 的 node 一案（守住現有行為，紅由突變證明） |
| `5fb333a` | 契約 #111 的一句與變更紀錄（S-7）；DQ-31 的結論欄改回原句（S-9） |
| `5aebade` | 案例：`main/delete-gone-stale`（S-6） |
| 本筆記 | 第 17 節；第 9 節（S-8）、第 16.5 節（S-8）、第 16.2 節第 15 點（S-7）、第 16.12 節的編號；結論、第 1 節、第 16.13 節同步 |

### 17.8 交給主對話與後面的片

- **HM-10 已合併**：2026-11-16 `git fetch` 看到 `claude-delivery` 是 `df686dd`，HM-10（#104，`d00a338`）、HM-31（#105）、
  HM-09 監看修正（#106）都已合併，`684a2dd` 是它的祖先。本片當時沒有 rebase（照任務，由主對話做；2026-11-16 已 rebase，見第 18 節）。rebase 時要注意（都已照做）：
  - 契約第 9 節：HM-31 已用掉 #101～#108，本片的 #101～#104 要改成 #109～#112（#104 列裡指到的「#101」跟著改），第 9 節開頭的
    說明句一起改；變更紀錄的兩列接在「v1 草案（HM-09 追補）」後面。本筆記與 PR 說明裡的列號跟著改（README、`admin-write-contracts.md` 與測試的註解沒寫列號）。
  - `decisions.md`：HM-31 加了第 1.1 節與兩列變更紀錄；本片那列接在最後。
  - 帳本：以新基準的 `runtime-patches.json` 為底，5 個面板檔照實際內容重算（新基準沒有動面板檔）。
  - 重跑：形狀比對（Python 對新基準的真後端、Playwright 對 fixture；HM-31 動的是 8081 那一側，`profile_admin.py` 沒變）、node、
    Playwright 全套、兩個預檢（base 改成新的 `claude-delivery`）。
- push：分支的上游設成 `origin/claude-delivery`，要明確 `git push -u origin feat/ha-multiprofile-hm11-20261115`。
  兩個備份分支與 `refs/original` 只在本機，不要 push。
- HM-18：DOCS 提一句 `profile_index_corrupt` 會釋放帳號增刪的識別碼（觀察 1）；其餘照第 16.11 節。
- HM-13c：隔離遇沒有代碼的 503 的文案（觀察 2）；清單沒帶 ETag 時讀不到的帳號的刪除鈕（觀察 4）。

## 18. rebase 到 claude-delivery（HM-31、HM-09 追補之後，2026-11-16）

第 1～17 節照 rebase 前寫，裡面的 commit 編號是 rebase 前的（對照在第 18.11 節）；列號已照 rebase 後的改（第 18.4 節）。
證據在 `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-rebase-HM-11/`（`tools/` 是用到的腳本，副檔名多加 `.txt`；`logs/` 是 log；
`conflicts/` 是三個衝突 commit 解衝突前的檔，含衝突標記）。

### 18.0 結論

- 基準換成 `claude-delivery` `df686dd`（HM-10 的 PR #104、HM-31 的 PR #105、HM-09 追補的 PR #106 合併後）。
  35 個 commit 照原順序重放，衝突在 3 個 commit，都是文件（契約、`decisions.md`）。程式、測試、fixture 和 rebase 前逐位元相同。
- 契約第 9 節本片的四列從 #101～#104 改成 #109～#112（HM-31 已用掉 #101～#108）。第 10 節加一列記這次改號（`51b51fd`）。
- 帳本由 git 自動合併，再逐列核對：58 列和新基準相同；5 個面板檔是新基準的說明接本片的句子，SHA-256 照 rebase 後的檔案重算，
  值和 rebase 前相同（新基準沒有動面板檔）。
- 真後端形狀比對在新基準照過（10 個情境、94 個案例），`expect` 與 fixture 都不用改。
- 本機：node 81、build-closure PASS、Playwright 117、pytest 子集 525、全套 5,978 過（7 個要 root 的既有案例失敗）；`validate.py` PASS、`tool_inventory.py` exit 0。
  兩個預檢 OK。`origin/claude-delivery..HEAD` 每個 commit 都沒有原始雙向控制字元。

### 18.1 範圍

- `git fetch origin`：`origin/claude-delivery`＝`df686dd`。先開本機備份分支 `backup/hm11-before-rebase2-20261116`（指向 `a262316`，不 push）。
  前兩個備份分支與 `refs/original` 照留，也不 push。
- `git log --oneline 684a2dd..a262316` 是 35 個。`684a2dd` 是 HM-10 PR #104 的 head；#104 用 merge commit 合併（`d00a338`，第二個 parent
  是 `684a2dd`，兩者的樹相同），所以直接 `git rebase origin/claude-delivery`，只重放這 35 個。
- 新基準帶進來的（`684a2dd..df686dd`，30 個 commit，含三個合併 commit）：HM-10 的合併 `d00a338`（樹和 `684a2dd` 相同）、HM-31（PR #105）
  與 HM-09 監看修正（PR #106）。改了 24 個檔：閘道與帳號 runtime
  （`gateway.py`、新的 `request_budget.py`、`request_limits.py`、`profile_router.py`、`profile_runtime.py`、`profiles.py`、`health.py`）、
  9 個測試檔、契約、威脅模型、`decisions.md`、`acceptance-matrix.md`、`ledger-tracking.md`、兩份筆記、帳本。
- 和本片重疊的只有 3 個檔：契約、`decisions.md`、帳本。`acceptance-matrix.md` 本片沒有改（第 2 節），沒有衝突，就是新基準的內容；
  本片新的兩個測試檔沒有被 `paas-test-mapping.md`、`deviation-trace.md` 引用，照規則不用登記。
- 依賴：`684a2dd..df686dd` 沒有動 `uv.lock`、`package-lock.json`、`package.json`、`pyproject.toml`、`requirements*`、`packaging/inputs.json`
  與 patch 檔，沒有重跑 `setup_repo_env.sh`。

### 18.2 衝突與處理

解衝突用 repo 外的腳本：`resolve_concat.py`（兩邊都留，新基準在前）、`resolve_rows.py`（逐塊先斷言兩邊的內容，再組合；本片的行只改列號）。
新基準那一側一律照原文、放在前面；本片的行接在後面。

| rebase 後（原本） | 衝突 | 處理 |
|---|---|---|
| `b5f8908`（`e058882`） | `decisions.md` 變更紀錄 1 塊：新基準在表尾接了 HM-31 兩列，本片接一列 | HM-31 兩列在前、本片那列在後。DQ-31 那列由 git 自動合併（新基準沒動它） |
| `6c0180c`（`552af33`） | 契約 3 塊：第 9 節說明段最後一行、表尾的列、第 10 節表尾。`decisions.md` 1 塊：變更紀錄 | 契約：HM-31 那行說明、#101～#108、HM-31 三列與 HM-09 追補一列照原文在前，本片的接在後面。本片的行只改列號：說明的「第 101～104 列是 HM-11」→「第 109～112 列」；四列 #101～#104 → #109～#112；#112（原 #104）裡的「兩段確認，#101」→「#109」；變更紀錄的「第 9 節補 #101～#104」→「#109～#112」。`decisions.md`：HM-31 兩列在前，本片那列用這個 commit 的寫法；DQ-12、DQ-14 的負責片由 git 自動合併 |
| `d24557e`（`5fb333a`） | 契約 2 塊：表尾的列、第 10 節表尾。`decisions.md` 1 塊：變更紀錄 | 契約：#101～#108 照新基準；本片四列用這個 commit 的寫法再改號（這個 commit 只改 #111（原 #103）的最後一句，腳本確認另外三列和上一個 commit 留下的相同）；第 10 節新基準四列在前、本片兩列在後，「第 9 節 #103 最後一句」→「#111」。`decisions.md`：HM-31 兩列在前，本片那列用這個 commit 的寫法；DQ-31 結論欄改回原句由 git 自動合併 |
| 帳本 5 個（`5addbc7`、`49bef0b`、`7b1cdce`、`7efb591`、`f5baee8`） | 沒有：新基準改的是閘道那幾列，本片改的是面板那幾列 | git 自動合併；合併後逐列核對（第 18.5 節） |
| 其他 27 個 | 沒有 | 照原樣重放 |

### 18.3 核對

- `git range-diff 684a2dd..a262316 origin/claude-delivery..87099fc`：32 個「=」（patch 相同，含帳本 5 個）。`b5f8908` 只差上下文（上面多了
  HM-31 兩列）；`6c0180c`、`d24557e` 差的是改號（range-diff 把 `d24557e` 當成另一個 commit 顯示）。
- 逐 commit：三個衝突 commit 的增刪行，和原 commit 的增刪行照上面的改號規則換過之後逐行相同（`renumber_check.py`；`decisions.md` 用
  `same_change.py`，三個都相同）。
- 整段（`git diff origin/claude-delivery 87099fc` 對 `git diff 684a2dd a262316`）：契約新增 7 行，改號後逐行相同；`decisions.md`（+4 −3）、
  帳本（+14 −8）逐行相同。其他 19 個檔和 `a262316` 逐位元相同；新基準改的 24 個檔，除了這 3 個，和 `df686dd` 逐位元相同。

### 18.4 列號對照（契約第 9 節；新基準最後是第 108 列）

| rebase 前（`684a2dd` 基準） | rebase 後（`df686dd` 基準） | 項目 |
|---|---|---|
| #101 | #109 | 刪除帳號與隔離帳號索引的確認 |
| #102 | #110 | 面板的第一個 bootstrap（開關探測） |
| #103 | #111 | 帳號清單不能用時的面板 |
| #104 | #112 | 孤兒在面板（列裡的「兩段確認，#101」→「#109」） |

- 新基準的 #101～#108 是 HM-31 的列（位元組預算等），本片沒有引用。#1～#100 沒有移動，本片引用的 #25、#31、#34、#51、#55、#56、#84、#85 不變。
- 改了的地方：契約第 9 節說明段本片那行、四列與 #112 的引用、第 10 節本片的兩列（都在解衝突時）；第 10 節另加一列（`51b51fd`）；
  本筆記 9 處（`4bff867`：結論、第 16.11、16.12、17.2、17.3、17.7 節；只改列號，其中兩處順便寫明對齊時的舊號）；PR 說明（repo 外的草稿）。
  第 1 節與各節的 #100、#104～#106 是 PR 編號，第 17.8 節講改號的那段是當時的交接，都照原文。
- 不用改的地方：`decisions.md`、`acceptance-matrix.md`、`packages/mcp-admin-ui/README.md`、`docs/admin-write-contracts.md`、測試與測試說明都沒有寫
  這幾個列號（`git grep` 核對）。
- commit 訊息照寫的當時，不改寫：`6c0180c`（原 `552af33`）的訊息寫 #101～#104，`d24557e`（原 `5fb333a`）寫 #103，就是上表左欄。
  兩份審查報告（`wave4/review-HM-11.md`、`review-HM-11-align.md`）與之前的證據目錄也是舊列號、舊 commit 編號。

### 18.5 帳本（`docs/provenance/runtime-patches.json`）

不只看文字合併：用 `check_ledger.py` 逐列核對最後的帳本。

- 新基準 62 列，rebase 後 63 列（新列 `profiles.js` 照原本放在 `operation-identity.js` 後面）。
- 58 列和新基準逐欄相同（含 HM-31 改的 `gateway.py`、`request_limits.py`、`profile_runtime.py`、`profile_router.py`、`profiles.py` 與新的 `request_budget.py`）。
- 本片改的 5 列：`change` 是新基準的文字接本片原本在列尾加的那段（腳本確認本片只在列尾追加）；`sha256` 照 rebase 後的實際內容重算：

| 列管檔 | 新基準 | rebase 前（`a262316`） | rebase 後 |
|---|---|---|---|
| `app.js` | `e93520e8eff0` | `8665b1dc4f06` | `8665b1dc4f06` |
| `api.js` | `5440e64e92f1` | `39b2cc9cf5f5` | `39b2cc9cf5f5` |
| `contracts.js` | `b2f6edd44b49` | `570189d5699e` | `570189d5699e` |
| `operation-identity.js` | `982ed6fd9d1b` | `b25346752d73` | `b25346752d73` |
| `profiles.js`（新列） | — | `1fb12ba38d36` | `1fb12ba38d36` |

- 重算的值和 rebase 前相同：新基準沒有動面板檔，rebase 後這 5 個檔和 `a262316` 逐位元相同。
- JSON 照 repo 的寫法（`indent=2`、`ensure_ascii=False`、結尾換行）：新基準、`684a2dd`、`a262316`、HEAD 四份帳本重新序列化都逐位元相同。
- 帳本預檢也 OK（第 18.8 節）。

### 18.6 形狀比對（真後端）

- `tests/test_panel_profile_api_shapes.py` 在新基準的真後端（`tests/multi_profile_runtime.py`）照過：10 個情境、94 個案例全過，2.28 秒
  （`87099fc` 上單獨跑；子集裡也過）。`expect` 是從 `684a2dd` 的後端錄的，一個都沒有改。
- 為什麼沒變：HM-31 在 8099 只改 `gateway.body()`：一個 `Content-Length` 宣告超過 16 MiB、又沒有 `Transfer-Encoding` 時，讀之前回 413；
  管理 API 的 `json_body` 不套結構守門。面板的案例都是小本體；`profile_admin.py` 沒有改；HM-09 追補只改關閉。
- fixture 也不用改：`profile-api-parity.spec` 10 案全過（同一份 `expect`）。

### 18.7 本機檢查（一般使用者；`ha_env.sh` 的 TMPDIR，跑完用完整路徑刪掉；pytest 都排在共用鎖後面）

`87099fc` 與 `51b51fd` 只差契約第 10 節一列（測試不讀契約），之後的 `4bff867` 與本筆記只改筆記，這幾個 head 上的結果都成立。

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 81 案全過、0.22 秒（`87099fc`） |
| `npm run build`＋`node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`，`--output` 放 TMPDIR） | 117 案全過（`single` 97、`profiles-on` 20），3.6 分鐘（`51b51fd`，18:41～18:45，開始與結束時工作樹都乾淨） |
| 其中 `profiles.spec` | 16 案，逐案加總 35.0 秒 |
| 其中 `profile-api-parity.spec`（fixture 對同一份案例） | 10 案全過、2.3 秒 |
| 其中 `profiles-on` 的四個既有 spec | 20 案全過、31.8 秒 |
| 既有 9 個 spec | 對新基準一個字沒改（`tests/browser/` 只多本片的兩個新檔） |
| pytest 子集 23 檔 | 525 案全過、0 skip、108.3 秒（`87099fc`，18:38 取得鎖）：本片的形狀比對；HM-10 的 3 檔（`test_profile_admin_api`、`test_admin_pipeline_matrix`、`test_router_passthrough`）；HM-31 的預算與結構 3 檔（`test_request_budget`、`test_request_structure`、`test_request_budget_gateway`）；HM-01 黃金回歸與兩個契約凍結；第 16.6.1 節其餘 13 檔 |
| 形狀比對單獨跑 | 10 案全過、2.28 秒（第 18.6 節） |
| pytest 全套（`tests`，CI 的指令加 `-rfEs --durations=30`，正式 conftest） | 5,978 案過、7 案失敗、0 skip，32 分 44 秒（`51b51fd`；18:48 取得鎖、19:21 跑完，開始與結束時工作樹都乾淨、HEAD 都是 `51b51fd`）。失敗的 7 案就是要 root 的既有案例（`test_owned_executable` 1、`test_profile_store` 1、`test_restore_detection` 5，都停在 `geteuid() == 0` 那一行斷言）。2 個 DeprecationWarning（websockets.legacy，既有）。上面子集的 23 個檔在全套裡也全過 |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15） | PASS（`51b51fd`） |
| `scripts/tool_inventory.py` | exit 0（`51b51fd`） |
| 規則核對 | `addons/`、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py` 對新基準 0 行差異；沒有改任何版號；`MULTI_PROFILE_PRODUCTS` 是空集合；commit 身分都是 woowtech、沒有 AI 署名 |

### 18.8 預檢（base 都是 `origin/claude-delivery`）

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | OK，0 命中（gitleaks 8.28.0；`df686dd..4bff867` 37 個 commit，另掃 HEAD 的樹與整段歷史） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | OK：`runtime-patches.json` 176 項、`runtime-sources.json` 70 項、`docs/tool-surface.json` 159 項，0 漂移、0 缺；改過的 22 個檔裡 5 個面板檔由帳本釘住、帳本本身有改；沒有帳本沒列的執行檔（`4bff867`）。比對齊時多的 1 項是 HM-31 新列的 `request_budget.py` |

本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 18.9 雙向控制字元

`bidi_scan.py` 逐 commit 查 `origin/claude-delivery..HEAD`：那個 commit 的樹裡、這段範圍碰過的每個文字檔的全文；那個 commit 自己新增的行；
commit 訊息（標題與內文）。`4bff867`（本筆記之前的 37 個 commit）上：U+202A～202E、U+2066～2069 合計 0 個；U+200E、U+200F、U+061C 也是 0 個。這段範圍碰過的 22 個檔都是文字檔，沒有跳過的檔。本筆記 commit 之後再跑一次，結果記在 PR 說明。

### 18.10 只在 CI 跑的測試、CI 時間

- 這次沒有新增或改動任何測試。照第 16.9、17.6 節：沒有只在 CI 跑的新測試；要 root 的 7 個既有案例本機一定失敗。
- `checks` 推估照第 17.6 節（多約 1.3～1.4 分鐘）。實際秒數 CI 跑完再補。

### 18.11 commit 對照

「相同」＝`git range-diff` 的「=」（patch 相同）。

| # | rebase 前 | rebase 後 | 說明 |
|---|---|---|---|
| 1 | `d4a0d4b` | `346e8b9` | 相同 |
| 2 | `26c7ec4` | `1841935` | 相同 |
| 3 | `488a07c` | `5addbc7` | 相同（帳本，自動合併） |
| 4 | `5e3f63d` | `49ec2a3` | 相同 |
| 5 | `e058882` | `b5f8908` | 衝突（`decisions.md`） |
| 6 | `c18ff9d` | `b22ced6` | 相同 |
| 7 | `1862d6c` | `4bc74e7` | 相同 |
| 8 | `4ee52d5` | `16cc6ce` | 相同 |
| 9 | `17a327b` | `d963847` | 相同 |
| 10 | `0a75d27` | `49bef0b` | 相同（帳本，自動合併） |
| 11 | `1158584` | `ddbe1f1` | 相同 |
| 12 | `fffe8fd` | `2235954` | 相同 |
| 13 | `368a53a` | `d6f3786` | 相同 |
| 14 | `43e752e` | `7b1cdce` | 相同（帳本，自動合併） |
| 15 | `0b5add5` | `9f31a42` | 相同 |
| 16 | `ceea550` | `7568b7c` | 相同 |
| 17 | `e6096fe` | `4b6aa03` | 相同 |
| 18 | `7f53b6c` | `de7c550` | 相同 |
| 19 | `959591d` | `d0afe99` | 相同 |
| 20 | `cc57bde` | `83eb002` | 相同 |
| 21 | `895d70a` | `b876026` | 相同 |
| 22 | `fc9d3cb` | `4f67802` | 相同 |
| 23 | `61f30a0` | `7efb591` | 相同（帳本，自動合併） |
| 24 | `552af33` | `6c0180c` | 衝突（契約、`decisions.md`）；改號 |
| 25 | `db5b0b3` | `7754354` | 相同 |
| 26 | `931107e` | `74c37d1` | 相同 |
| 27 | `2c2a30d` | `a18b8ca` | 相同 |
| 28 | `c7ed817` | `390a821` | 相同 |
| 29 | `805a2cb` | `f5baee8` | 相同（帳本，自動合併） |
| 30 | `0480d8d` | `0ad8206` | 相同 |
| 31 | `214c192` | `b43dfff` | 相同 |
| 32 | `4e0a770` | `ddd7370` | 相同 |
| 33 | `5fb333a` | `d24557e` | 衝突（契約、`decisions.md`）；改號 |
| 34 | `5aebade` | `7f16bee` | 相同 |
| 35 | `a262316` | `87099fc` | 相同 |

rebase 之後新加的 commit：

| commit | 內容 |
|---|---|
| `51b51fd` | 契約第 10 節加一列：本片的列改成 #109～#112 |
| `4bff867` | 本筆記改列號（9 處；第 18.4 節） |
| 本筆記 | 第 18 節；結論、第 1 節基準、第 17.8 節的狀態 |

### 18.12 交給主對話與後面的片

- push：`git push -u origin feat/ha-multiprofile-hm11-20261115`（分支的上游原本是 `origin/claude-delivery`）。三個備份分支與 `refs/original` 只在本機。
- 列號：HM-30、HM-13b 若也在契約第 9 節 #108 後面加列，後合併的要接在 #112 後面重排。
- 其餘照第 16.11、17.8 節（HM-12、HM-13c、HM-16、HM-18；HM-03a／b 待量的項目照第 16.10 節）。
