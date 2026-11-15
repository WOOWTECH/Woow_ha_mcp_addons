# HA 多帳號 HM-11 provenance：面板的帳號選單、切換、回聲、收據、建立後切換（先對 fixture，2026-11-15）

## 結論

- **產品沒開通時，面板畫出來的東西與送出的請求都不變**：DOM、送出的請求（方法、路徑、標頭集合）、fixture 收到的紀錄，和 `b5d10c5` 的面板逐項相同
  （第 5.3 節：6 種設定、5 頁、幾種動作，72 個比較 0 差異）。既有 9 個 Playwright spec 一個字都沒改照過。repo 裡的
  `MULTI_PROFILE_PRODUCTS` 維持空集合；這一片只動面板、fixture、P9 kit 的 client 與文件，沒有動任何 Python。
- **開通後**（目前只有 fixture 會開；真後端是 HM-10）：
  - 頂列有帳號選單（`<select aria-label="帳號">`）與「新增帳號」「改名」「刪除帳號」；標題列固定顯示目前帳號與 id 前 8 碼；
    每個確認對話框寫出帳號。預設帳號不能改名、刪除；刪除要確認兩次並寫明後果（DQ-14）。名稱一律以文字節點顯示。
  - 帳號選擇只在頁面記憶體（DQ-18），重新整理回預設帳號。第一次 bootstrap 不帶帳號；伺服器回 400 `profile_id_required`
    就改成**每個**帳號範圍請求都帶 `X-MCP-Profile`（含明確的 `default`）；`/api/profiles*` 永遠不帶。
  - 每個帳號範圍回應都比對回聲；`mutate(…, profile)` 開頭就鎖定帳號，取 CSRF 的 bootstrap 與變更帶同一個標頭、兩個回聲都比對；
    不符就不顯示、藏起 token、提示並重新讀取（C1-S11、I12）。換帳號之後才到的回應一律丟掉（帳號世代）。
  - 切換：藏 token、清密碼欄與草稿、整頁重畫；切換中只剩選單可用，再選一次就取代前一次切換；其他操作進行中選單停用。
  - 建立後自動切到新帳號（DQ-31）；任何帳號範圍請求回 `profile_not_found` 就回預設帳號並說明，清掉該帳號未確認的收據。
  - 收據：預設帳號的 key（`woow-admin-operation-v1:<mount>`）與 4 鍵紀錄完全不變；額外帳號 `…:<mount>:<id>`、5 鍵；
    帳號增刪 `…:<mount>:profiles`。`get()` 每個 key 只收自己的格式，升級前分頁留下的舊紀錄照常可查（Playwright 案例）。
- **先寫測試**：`6ba92bb` 只有測試與 fixture；在 `b5d10c5` 的面板上 node 1 檔載入失敗（15 案沒跑）、build-closure 新斷言失敗、
  Playwright 100 案 29 失敗（新 spec 9 案＋開關開的 20 案），既有 71 案全過（證明新 fixture 開關關時相容）；`df146d4` 起全綠（第 4 節）。
  `507314d` 補上 FM-60／FM-64 的「這個帳號」說明與 FM-98 的工具隔離案例，之後重跑全套仍全綠。
- 新測試：node 15 案（約 0.2 秒）、Playwright 9 案（約 20 秒）＋開關開專案 20 案（約 35 秒）。本機 Playwright 全套 2 分 28 秒 →
  約 3 分 15 秒，推估 CI `checks` 多約 0.8 分鐘（第 7 節）。
- 兩個預檢：秘密預檢 0 命中、帳本預檢 OK（第 8 節）。**獨立安全審查還沒做**（實作者不能自審；第 14 節列出自查重點）。
- 照契約假設、要等 HM-10 對齊的地方列在第 11 節（「收尾」不在這一階段）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-11（計畫 §12.3；風險高、工作量 L；要獨立安全審查）。這一階段只對 fixture；和 HM-10 真後端對齊的「收尾」不在這一階段 |
| 分支 | `feat/ha-multiprofile-hm11-20261115`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `b5d10c5`（HM-00、01、02、04、05、06、07、08、13a、17 已合併） |
| 依據 | 計畫 §6、§10.3、§12.3 HM-11；契約 §1.2、§3（管理 API、`X-MCP-Profile`、回聲、寫入保護、欄位）、§4.1、§9 #31～#36、#55、#56、#84、#85；FM-12、20、21、22、23、26、53、56～66、71、98、145；`decisions.md` |
| 對齊的 PaaS | 沒有移植 PaaS 程式。期望值來自 `woow-mcp-server` @`69ac425` 的 `packages/mcp-admin-ui/src/api.js`（標頭規則）、`profileStatus.js`（停用說明）、`useDurableOperation.js`（收據 key：預設帳號沿用舊 key）、`components/ProfileChooser.jsx` 與 `AdminApp.jsx`（建立後切換、刪除後回預設）、`apps/headscale/static/assets/app.js`（帳號世代、晚到回應丟掉、「前一個設定檔有未確認的請求」）。HA 刻意不同的地方見契約 §9 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hui/profiles.js`（新） | 帳號 id、回聲比對、清單列驗證、名稱規則（DQ-16）、選單文字與停用／無法啟動說明、用戶端名稱（DQ-31）、頂列選單與建立／改名對話框（DOM 工具由 app.js 傳入） |
| `Hui/api.js` | `AdminApi` 的 `profile`、`epoch`、`open()`（探測開關）、`select()`；每個帳號範圍請求帶標頭並比對回聲（`ProfileEchoError`）、舊世代的回應丟掉（`StaleProfileError`）；`mutate(operation, payload, revision, profile)`；`profileList`、`createProfile`、`renameProfile`、`deleteProfile`、帳號增刪的收據與重送；帳號錯誤代碼的固定文案 |
| `Hui/operation-identity.js` | 三種 key 與各自的紀錄格式；`get()`、`start()`、`clear()` 帶範圍；`profile.create`／`profile.delete` 兩種收據 |
| `Hui/app.js` | 選單、切換（`show()`）、建立／改名／刪除流程、`profile_not_found` 與回聲不符的後續處理、各頁的帳號文字、額外帳號唯讀的端點、讀不到的帳號仍可刪、索引壞的橫幅、帳號增刪的待確認卡 |
| `Hui/contracts.js` | `policyFingerprint` 含帳號 id；`policyRestartNotice(product, scoped)`；`clientExample(endpoint, token, name)`。單帳號輸出不變 |
| `Hui/styles.css` | 帳號選單、說明、對話框的版面 |
| `packages/mcp-admin-ui/fixtures/server.mjs` | 多帳號替身（開關兩種）與測試勾子（第 3.4 節） |
| `packages/mcp-admin-ui/playwright.config.mjs`、`tests/owned-fixture.mjs` | `single`、`profiles-on` 兩個專案；`profilesOn` 選項 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs`（新）、`tests/browser/profiles.spec.mjs`（新） | 第 4、5 節 |
| `packages/mcp-admin-ui/tests/build-closure.mjs` | N15 兩個字面斷言保留；加額外帳號與帳號增刪的格式、key 形式、帳號選擇不進瀏覽器儲存、打包後有 `X-MCP-Profile` |
| `H:packaging/ha_p9_admin.mjs` | 透過 `AdminApi` 自動帶標頭；`{profile}` 指定額外帳號；呼叫端 headers 帶 `X-MCP-Profile` 直接拒絕 |
| `docs/provenance/runtime-patches.json` | app.js、api.js、contracts.js、operation-identity.js 重新釘摘要並補說明；新增 `profiles.js` |
| `packages/mcp-admin-ui/README.md`、`docs/admin-write-contracts.md` | 多帳號的面板行為與收據格式 |
| `docs/multi-profile/decisions.md` | DQ-31 記成已定（獨立 commit `b567f68`；rebase 時若 HM-10 已記可整個丟掉） |
| commit 順序 | `6ba92bb` 測試與 fixture → `df146d4` 實作 → `ff49bd0` 帳本 → `b484450` README 與寫入契約文件 → `b567f68` DQ-31 → `507314d` 後端與工具頁的帳號說明、工具隔離案例、帳本重新釘 app.js → 本筆記 |
| 本筆記 | — |

沒改：任何 Python（`packages/mcp-admin-core/`、`apps/`、`tests/*.py`）、`tests/owned_ui.mjs` 等 repo 根目錄的測試工具、`conftest.py`、
`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、workflow、`docs/tool-surface.*`（沒動 `apps/runtime/*.py`、`launch.py`）、
`docs/multi-profile/contract.md`（計畫 §12.2 的衝突表只排 HM-00、10、18；要改的字句列在第 13 節交給 HM-10／HM-18）、
`docs/multi-profile/acceptance-matrix.md`（測試檔登記表照舊是「計畫」，和前面各片一致）、`H:packaging/ha_p9_driver.mjs`（帳號參數是 HM-16）。

## 3. 設計重點

### 3.1 開關怎麼探測（契約 §3.3）

- 第一次 bootstrap 不帶 `X-MCP-Profile`：沒開通的伺服器照今天回 200（請求與今天逐位元相同）；開通的伺服器在角色檢查之後回
  400 `profile_id_required`，面板就改成帶 `X-MCP-Profile: default` 再讀一次，之後每個帳號範圍請求都帶。非管理員照樣只拿到 403。
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

### 3.4 fixture（LOCAL MOCK）

- 沒開（預設）：和以前逐位元相同（第 5.3 節），不看 `X-MCP-Profile`；`calls` 只有在請求真的帶標頭時才多 `profileHeader` 一欄，
  所以既有 spec 的 `toEqual` 不受影響。
- 開了（`profiles: true | {extra, limit, memory, indexCorrupt, listStatus}`）：照契約 §3.3 的標頭規則與 §3.4 的回聲；`/api/profiles`
  清單（ETag 標頭）、建立（201＋收據、同 key 重送 200、名稱規則與上限）、改名、刪除；額外帳號 `PUT endpoint` 409 `endpoint_global`；
  讀不到的帳號 503 `state unavailable`；新帳號複製預設帳號當下的政策（DQ-02）。
- 勾子：`/__fixture/defaults`（profiles-on 專案）、`/__fixture/profile`（外部刪除／改名／新增、切換開關＝模擬升級，保留狀態與收據）、
  `/__fixture/profiles`（各帳號狀態，給斷言）、`/__fixture/reads`（清單讀取，不算 calls）、`wrongEcho`、`createToken`（契約違規的建立回應）。

## 4. 先紅後綠

| 檢查 | `6ba92bb`（測試）＋ `b5d10c5` 的面板 | `df146d4` 起（實作） |
|---|---|---|
| `npm test`（node） | 59 案：58 過、1 失敗（`profiles.test.mjs` 找不到 `src/profiles.js`，15 案沒跑） | 73 案全過 |
| `build-closure.mjs` | 失敗（第 54 行，新加的格式斷言） | PASS |
| Playwright（`single`＋`profiles-on`） | 100 案：71 過（既有 spec 全過）、29 失敗（`profiles.spec` 9 案、`profiles-on` 20 案），12.3 分鐘（失敗案等到逾時） | 100 案全過（第 5.1 節） |

做法：先 commit 測試與 fixture，再把實作 `git stash`（只限 `packages/mcp-admin-ui/src` 與 `packaging/ha_p9_admin.mjs`）跑一輪，
`stash pop` 後 commit 實作。沒有做臨時突變。

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

### 5.1 面板測試

| 檢查 | 結果 |
|---|---|
| `npm test --prefix packages/mcp-admin-ui` | 73 案全過（新 15 案約 0.2 秒；全部約 0.4 秒） |
| `npm run build` ＋ `node tests/build-closure.mjs` | PASS |
| Playwright 全套（`single`＋`profiles-on`，照 CI 裝 Chromium） | `507314d`（最後一個程式 commit）：100 案全過、3.2 分鐘（另一次在別的工作流同時跑 pytest 時 3.5 分鐘）；基準 `b5d10c5`：71 案、2 分 28 秒 |
| 只跑 `profiles.spec.mjs` | 9 案、約 20 秒 |
| 只跑 `profiles-on` 專案 | 20 案、約 35 秒 |

### 5.2 其他

| 檢查 | 結果 |
|---|---|
| pytest：碰到面板、fixture、帳本與 P9 的檔（`test_tool_inventory.py`、`test_ledger_precheck.py`、`test_owned_ui.py`、`test_owned_browser*.py`、`test_admin_ui.py`、`test_identity_fields.py`、`test_batch2_admin.py`、`test_n8n_selectors.py`、`test_b2_odoo_policy.py`、`test_writes_default_on.py`；排隊在共用鎖） | 151 案全過（第 5.4 節） |
| 全套 pytest | 沒跑：這一片沒有改任何 Python，也沒有改 pytest 會讀的面板以外的檔；以 CI 為準 |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 201`、`OK (skipped=5)`，同基準 |
| `scripts/tool_inventory.py`（漂移檢查） | exit 0 |
| `git status` | 乾淨 |

### 5.3 開關關時面板不變的比對（repo 外 `SP:hm11-dom/bin/compare.mjs`，不 commit）

- 基準＝`git show b5d10c5:` 取出的面板原始碼與當時的 fixture，自己 build；新版＝本分支。兩個 fixture 各起一個，用同一個 Chromium。
- 6 種設定（預設 n8n；Odoo＋parity046＋已設定；n8n＋操作限制＋條件寫入；Hermes＋端點＋遮罩與歷史；EMQX 固定後端＋離線＋套用失敗；
  Hermes＋升級通知格式不符）× 5 頁（總覽、後端、工具、連線與權杖、診斷）；每頁比「不動」與「按重新整理狀態」兩種，
  連線與權杖頁另比「開『顯示權杖』對話框」與「重新產生權杖」（每種設定 12 個，共 72 個）。
- 比 `document.body.innerHTML`、fixture 的 `calls`（操作識別碼換成固定字）、瀏覽器送出的每個 `/api/` 請求的方法、路徑與標頭名稱集合。
- 結果：72 個比較 0 差異。

### 5.4 pytest 子集

- 指令：`flock SP:wave1-pytest.lock env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`
  加第 5.2 節第一列的 12 個檔（`HEAD`＝`507314d`，正式 conftest；在共用鎖排了約 33 分鐘）。
- 結果：151 案全過、0 skip、44.8 秒。其中 `test_ledger_precheck.py::test_this_checkout_has_no_ledger_drift` 與
  `test_tool_inventory.py` 的帳本檢查證明帳本與實際內容一致；`test_owned_ui.py`、`test_owned_browser*.py` 用新 fixture 與新 build 的面板。

## 6. 只在 CI 跑的測試

- 本片新增的 node 15 案與 Playwright 9＋20 案都在本機跑過、全部通過，沒有只在 CI 跑的新測試。
- 本片沒跑的：全套 pytest（沒改 Python；CI 以 root、0 skip 跑）；`tests/integration_local_runtime.py`（要 root，不在 pytest 收集範圍，
  CI 也不跑；用真 Core 驗新面板的單帳號路徑，這一片改用第 5.3 節的比對）。
- 已知要 root、本機一定失敗的既有案例（同 HM-08 筆記第 6 節）：`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5。
- Node：CI 與本機都是 v26.12.1；Playwright 1.61.1（Chromium headless shell 149）。

## 7. `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本機增量：Playwright 約 +45 秒（新 spec 約 20 秒、
`profiles-on` 約 35 秒，扣掉各自的啟動成本）、node 約 +0.2 秒、pytest 0。推估 CI `checks` 多約 0.8 分鐘（約 34.6 → 35.4 分鐘），在每片 1.5 分鐘內；
若要省，`profiles-on` 可只留 1440／320 兩種寬度的變體（要改 config，不改 spec）。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full` | gitleaks 8.28.0（釘版、已驗），設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`；本筆記的 commit 為 HEAD 時，本片全部 commit（`b5d10c5..HEAD`）＋HEAD 整棵樹＋整個歷史：**0 命中**（筆記前的 5 個 commit 時也是 0） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | 本筆記的 commit 為 HEAD 時：`runtime-patches.json` 173 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔：0 漂移、0 缺；改到的 5 個列管檔（app.js、api.js、contracts.js、operation-identity.js、profiles.js）都有帳本更新；沒有沒列管的新執行檔：**OK** |

測試資料：沒有 commit 任何隨機 token。固定的 token 形字串只有每個帳號一個字母重複 43 次（`M`、`T`、`U`…，低熵、沒人持有）與
既有的 `S`×43；遮罩 `TTTT`＋`*`×20＋`TTTT`；網址 `.test`、`.example`（同既有 spec）；操作識別碼在執行時由瀏覽器產生。

## 9. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`，本機唯讀 PaaS repo；任務寫的 origin/main 是 `cf3d0d5`，clone 裡已被別的流程 fetch 到 `5b84b5d`，本片沒有 fetch、沒有 checkout）

| commit | 內容 | 對本片 |
|---|---|---|
| `f5223be` | 只改測試：共用測試拿掉 VK（含 `packages/mcp-admin-ui/tests/browser-capabilities.py` 的產品清單） | 沒影響：帳號相關的面板與 API 沒變 |

查的檔：`packages/mcp-admin-ui/`、`apps/headscale/static/`、`apps/headscale/tests/browser/`、`packages/mcp-admin-core/mcp_admin_core/profiles.py`、
`routers/profiles.py`、`routers/operations.py`、`app.py`。`git diff --stat 69ac425 origin/main -- packages/mcp-admin-ui/` 只有上面那一檔。

## 10. 本片用到的決策

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-31（2026-11-15 17:4x 定，本片記進 `decisions.md`） | 面板用「帳號」；額外帳號範例名稱帶 id 前 8 碼；建立後自動切換；不做總覽與帳號層級權限 | 全部照做；預設帳號的範例名稱維持 `woow` |
| DQ-13（同時定，HM-10 記） | endpoint 全域一個、只存在預設帳號 | 額外帳號的端點唯讀並說明；fixture 對額外帳號 `PUT endpoint` 回 409 |
| DQ-14（同時定，HM-10 記） | 先撤銷並抹憑證再刪、孤兒不自動刪、面板列出可刪、不做軟刪除、兩段確認 | 兩段確認與後果文字；孤兒清單沒做（第 11 節第 17 點） |
| DQ-16、DQ-17、DQ-18 | 名稱規則；標頭規則；帳號選擇只放記憶體 | 第 3 節 |
| DQ-40 (a) ①～⑤ | 必帶帳號、回聲、CRUD 寫入保護、名稱加嚴、只放記憶體 | 第 3 節 |
| DQ-02、DQ-12、DQ-28 | 新帳號複製政策；索引壞時面板照開；OpenDesign 與 Odoo Manage 不開放 | 建立對話框的說明；索引壞的橫幅與只剩預設帳號；這兩個產品不顯示新增按鈕 |
| UC-10（主對話已定） | HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭 | 面板用標頭；備案路徑（契約 §3.7）沒做 |
| DQ-33、DQ-36 | 本機短 TMPDIR、以 CI 為準；commit 不加 AI 署名 | 第 5 節；commit |

沒用到、也沒碰到待定題：DQ-21、DQ-25（HM-09）、DQ-30（HM-12）、DQ-45（`serverInfo.name`，HM-18）。

## 11. 照契約假設、要等 HM-10 對齊的地方（「收尾」做）

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
17. DQ-14「孤兒面板列出可刪」：契約沒有孤兒清單的形狀，本片沒做；隔離目錄、全部撤銷、還原核對卡、索引隔離的按鈕是 HM-13c／HM-10。
18. 沒開通但有帳號資料時 bootstrap 的 `dormant_profiles`（「休眠帳號 N 個，權杖已撤銷」）：面板顯示是 HM-13b／HM-13c，本片沒做（單帳號模式不看這個鍵）。

## 12. 待 HM-03a 確認

| 項目 | 本片怎麼處理 | 要 HM-03a 量什麼 |
|---|---|---|
| UC-10：Ingress 轉送 `X-MCP-Profile` 與 PATCH／DELETE | 照主對話的決定先用標頭；沒轉送時第二次 bootstrap 仍 400，面板顯示「可能是 Home Assistant 沒有轉送帳號標頭」，不無限重試 | 真 HAOS 上兩段 Ingress 是否原樣轉送這個標頭與兩個方法；不行就照契約 §3.7 改路徑（面板與 P9 kit 同版改） |
| Ingress 把回應的 `ETag` 標頭傳給瀏覽器 | 面板從 `ETag` 讀索引版本，拿不到就說清單版本格式不符、不送變更 | 帳號清單回應經 Ingress 後瀏覽器看得到 `ETag`；看不到就請 HM-10 在本體另帶版本 |
| HA 前端 iframe 裡的 `<select>`、`<dialog>`、`\p{…}` 正規式 | 既有面板已用 `<dialog>`；`\p{…}` 需要 Chrome 64、Safari 11.1、Firefox 78 以上 | 實機（含手機 App 的 WebView）開啟面板、切換帳號 |

## 13. 交給後面的片

- **HM-10（與本片收尾）**：第 11 節逐點對齊；真後端下 node 與 Playwright 照跑（fixture 照真後端修正）；`tests/integration_local_runtime.py` 視需要加兩帳號（FM-98）。
- **HM-18（或 HM-10）改 `contract.md`**：§9 #85 的「待決（DQ-31）」改成已定；#56 的「DQ-31 面板細節待定」拿掉；#55 補一句「切換中只剩選單可用，
  再選一次取代前一次切換」；§3.1 帳號增刪的收據種類名與全域收據查詢（第 11 節第 7、8 點）；§10 變更紀錄。本片沒改契約，避免和 HM-10 衝突。
- **HM-13c**：還原與休眠核對卡、全部撤銷、隔離目錄刪除、`restore_review_required` 文案；`profiles.js` 照帳本列管規則接著改。
- **HM-16**：`ha_p9_driver.mjs` 的帳號參數（`createP9AdminClient(…, {profile})` 已就緒）、交叉矩陣。
- **HM-12**：`token_rotated` 提示與 422 文案（`Hui/app.js`）。
- **待決**：DQ-45（`serverInfo.name` 要不要帶 id）由 HM-18 問；DQ-13、DQ-14、DQ-30 由 HM-10、HM-12 寫進 `decisions.md`。

## 14. 驗收條件（計畫 §12.3 HM-11，這一階段）

| 條件 | 結果 |
|---|---|
| `unit.sh` 的 node＋Playwright 綠 | 本機通過：node 73 案、build-closure、Playwright 100 案（第 5.1 節）。CI 待 PR |
| 開關關時既有 9 個 spec 不改照過 | 通過：9 個 spec 檔沒有改；`single` 專案 71 案全過；四個 spec 另在 `profiles-on` 原封不動照過；開關關時 DOM／請求／紀錄和 `b5d10c5` 逐項相同（第 5.3 節） |
| 舊格式收據案例過 | 通過：node「a record the previous panel left (4 keys)…」與 Playwright「a receipt kept across the upgrade…」 |
| 多帳號 spec（切換、建立後切換、刪除兩段確認、token 不外洩到別帳號、晚到回應丟掉） | 通過：`tests/browser/profiles.spec.mjs` 9 案 |
| 測試先寫、先紅後綠 | 通過：第 4 節 |
| 同一系列 commit 更新帳本；新模組列管 | 通過：`ff49bd0`；帳本預檢 OK |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；開關維持空集合 | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過（第 8 節）；秘密預檢 0 命中 |
| 獨立安全審查 | **還沒做**（實作者不能自審）。建議審查重點：回聲比對與探測不會落到錯的帳號（I12）；切換與晚到回應；收據三種格式與 `get()` 的分隔；帳號增刪的 CSRF／If-Match／Idempotency-Key；名稱只以文字節點顯示；token 不跨帳號顯示；P9 kit 不讓呼叫端帶標頭；開關關時逐位元不變的證據 |
