# HA 多帳號 HM-26 provenance：Headscale 開通前的產品片（2026-11-19）

## 結論

- **範圍**：Headscale 的功能 PR（計畫 §9 Headscale 列、§12.3 HM-21～HM-26；FM-88、FM-89、FM-90、FM-109；CF-15）。不改
  `features.MULTI_PROFILE_PRODUCTS`、不碰 `addons/`。之後 Headscale 的升版 PR（0.4.19 → 0.5.0）只要加開關、改發版資料（第 14 節）。
- **計畫 §9 的四件，三件前面各片已經做好**，本片用測試在開關開與關兩種模式釘住，補文件：
  - 每帳號 `HEADSCALE_MCP_STATE_PATH`：`products.child_spec` 用帳號自己的目錄（HM-04、HM-05、HM-08）。vendored `policy.py` 在帳號目錄
    照樣成立（`ProductStore(create=…)` 建的 0700 目錄、0600 單一連結檔、同 uid、路上沒有連結），不用改 vendored 程式。還原放寬的權限
    子程式會拒絕（fail closed），entrypoint 與帳號的 store 在子程式起來之前收回 0700／0600。
  - 改 url 到別台沒帶新 api_key → 422：HM-12 的 `backend_edit.new_origin_refused` 已涵蓋全部產品（開通才有，DQ-40 ⑨）；loopback 存檔
    400 是 HM-20。本片補一個額外帳號、Headscale `/api/v1` 寫法的測試。
  - Origin 維持只放 `https://claude.ai`：產品的選項由管理程序交給每個帳號的 app（HM-08、HM-27）。本片補每個帳號的測試，並把 HM-27
    交來的三件定案（第 4 節）。
  - 文件「API key 是整台管理權限，建議每帳號不同 key」：DOCS 段落交升版片（`unreleased-changes.md` 第 3.8 節）、契約第 9 節 #129、
    威脅模型第 3 節；面板「後端設定」的說明在開通時換成每個帳號的版本（受開關管，第 3.3 節）。
- **找到並修的缺口（受開關管）**：DQ-25 的認證退避對 Headscale 從來沒生效。Headscale 伺服器拒絕 key（401）時，子程式只在錯誤物件裡寫
  `HEADSCALE_UPSTREAM_ERROR`、`http_status` 401，健康檢查的 reason 是通用的 `BACKEND_INVALID_RESPONSE`；HM-09 釘的
  `HEADSCALE_INVALID_CREDENTIAL` 只出現在 client 拒絕送出格式錯的 key 時（存檔就擋了，到不了）。新 `health.refused_login` 讀探測回覆，
  只給帶 `auth_backoff` 的監看用（開通才有）；記下的 reason 與任何回應都不變（第 3.2 節）。
- **開關一開就會紅的既有測試**：把 `headscale` 暫時加進開關（只在本機、沒有 commit）跑全套：pytest 23 案紅（另 1 案是本機少 n8n 的
  原生模組，和開關無關）、packaging unittest 2 案紅。原因都一樣：測試寫的是沒開通的 add-on，卻靠 repo 的開關是空的。新
  `tests/product_switch.py` 讓這些測試把自己的產品釘成沒開通（fixture、子程序前置碼、`multi_profile_runtime(switch=False)`），
  HM-01 黃金回歸與兩個契約凍結的期望值一字不改；改之後同樣暫時開通，53 個相關測試檔只剩 3 案紅：兩案要 root（本機本來就紅），
  一案是釘開關值的 `test_multi_profile_is_switched_off_for_every_product`（交升版 PR 改）；packaging unittest 全過（第 3.4、7 節）。
  所有產品通用：其他產品片同時在準備，會撞到同一批測試（第 14 節）。
- **先紅後綠**：新測試先 commit（`fbbc287`，2 案紅：`refused_login` 不存在；其餘 12 案照前面各片的實作就綠），`7d6e438` 修好；面板測試
  先 commit（`95bf0b5`，node 整檔紅、Playwright 1 案紅），`7c82b17` 修好；`7e9e1d9` 補還原守門那案（HM-13b 已做好，一加就綠）。
  開關開時的既有測試見上一點。突變 11 個：10 個第一次就抓到；M10（子程式不檢查帳號目錄 0700）第一次活下來，
  `1996759` 把測試改成目錄與檔案分開放寬後抓到，另加的 M11（不檢查檔案 0600）也抓到（第 7 節）。
- **秘密預檢第一次 1 命中，已處理**：新測試檔一個 DUMMY 測試值（`REPLACEMENT_KEY`）被 builder 的 gitleaks `generic-api-key` 規則判成秘密。
  分支還沒推，照「不改已發布的歷史」，用 `git commit-tree` 重建這 7 個沒推過的 commit：只把這個值換成同一把 gitleaks 0 命中的值，訊息、
  作者、作者時間不變，每個 commit 和舊的只差這一行；之後秘密預檢 0 命中（第 7.3、9 節）。
- **要使用者決定的事**：DQ-26（Headscale 形態）還是待定，本片照計畫建議做（兩種形態都支援、建議每帳號不同 key、不強制），使用者確認或改
  決定都要在升版 PR 前（`decisions.md`）。其餘第 15 節。
- **本機**：53 個相關檔的 pytest 兩種模式（開關關 2,032 過、暫時開通 2,031 過；紅的只有要 root 的 2 案，與開通時交升版 PR 的 1 案）、
  新檔 15 案、packaging unittest 兩種模式、`validate.py`、node 119 案、Playwright 167 案全過。兩個預檢 OK（第 9 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-26（計畫 §12.3 HM-21～HM-26；§9 Headscale 列；§8.7；§8.8 #9、#39、#41；§3.3 受開關管；驗收 T-02、T-04、T-05、T-07、T-20、T-21、T-23、T-24、T-27、T-29） |
| 分支 | `feat/ha-multiprofile-hm26-headscale-20261119`（一般 clone `ha-mp-hm26-20261119`） |
| 基準 | `claude-delivery` `c90b214`（HM-16 PR #109 合併後） |
| 依據 | 計畫 §9 Headscale 列；FEATURE-MATRIX FM-88、FM-89、FM-90、FM-109、FM-152、CF-15；`decisions.md` DQ-26（待定）、DQ-40 ⑨、DQ-11、DQ-25；契約第 2.6 節、第 9 節 #9、#41、#115 |
| 對齊的 PaaS | pin `69ac425`；本機唯讀 PaaS repo 的 `origin/main`＝`5ef1046`（2026-11-18）：pin 之後 `apps/headscale` 只有 `3b135ca`、`1637a0f`（閘道的 JSON 結構守門與位元組預算，HM-31 已對齊），`routers/tools.py`、`routers/settings.py` 沒變 |
| 受開關管 | 是。程式的兩處改動都只在開通時生效（監看的 `auth_backoff`、面板的 `api.profile`）；開關關時回應、面板、`/data/mcp` 逐位元同今天 |

## 2. 改了什麼、沒改什麼

| 類別 | 檔 | 做什麼 |
|---|---|---|
| 程式 | `packages/mcp-admin-core/mcp_admin_core/health.py` | `refused_login(reply)`；`HealthMonitor` 只在有 `auth_backoff` 時把它算進認證退避（第 3.2 節） |
| 面板 | `packages/mcp-admin-ui/src/contracts.js`、`app.js` | `connectionHelpFor(product, scoped)`；開通時 Headscale 的後端設定說明換成每個帳號的版本（第 3.3 節） |
| 新測試 | `tests/test_headscale_multi_profile.py` | 15 案（第 6 節） |
| 測試工具 | `tests/product_switch.py`（新）、`tests/multi_profile_runtime.py` | 把測試的產品釘成沒開通；`multi_profile_runtime(switch=False)` 照這樣做（第 3.4 節） |
| 既有測試 | 15 個 `tests/test_*.py`、`packaging/test_container_probe.py` | 開關關的測試釘自己的產品（第 3.4 節）；`tests/test_upgrade_hooks.py` 的真 runtime 測試加 Headscale |
| 面板測試 | `packages/mcp-admin-ui/tests/contracts.test.mjs`、`tests/browser/backend-identity.spec.mjs` | 說明的兩種模式 |
| 文件 | 契約、驗收矩陣、決策、威脅模型、`unreleased-changes.md`、`docs/operations/acceptance.md`、本筆記 | 第 10、11 節 |
| 帳本 | `docs/provenance/runtime-patches.json` | `app.js`、`contracts.js` 的摘要與說明（第 9 節） |

沒改：`features.MULTI_PROFILE_PRODUCTS`、`addons/`、`apps/`（vendored Headscale 子程式、`launch.py`、`apps/runtime`）、`products.py`、
`gateway.py`、`profile_runtime.py`、`run_product.py`、`docs/tool-surface.*`、`tests/conftest.py`。

## 3. 設計重點

### 3.1 每個帳號只讀自己的 state（FM-88）

- 計畫的高風險點：同一台 Headscale、同一把 key 的兩個帳號，子程式比對 state 裡的網址與 key 等於自己的環境變數，這比對分不出兩個帳號；
  子程式要是讀到別的帳號的 state，就照別人的政策（可能更寬）。政策是同 key 帳號之間唯一的分權。
- 實際的路徑：`ProfileManager` 用帳號的 store 目錄（額外帳號 `/data/mcp/profiles/<id>`）建 `ProfileRuntime`，`child_spec(state, directory,
  port)` 給 `HEADSCALE_MCP_STATE_PATH=<目錄>/state.json`、cwd 與 HOME `<目錄>/child`、`WOOW_MCP_CHILD_TOKEN` 是該帳號的 child token。
  本片沒改這條路，只把它釘住：測試拿管理程序**真的建出來**的每個 spec（Supervisor 替身記下每次啟動的 spec），對每個帳號比路徑、
  cwd、HOME、child token、key，並確認 argv 與環境裡沒有任何別的帳號的目錄、token、child token；再用那個 spec 的直譯器與環境跑
  vendored 子程式的 `execute_tool`（伺服器在記憶體裡）：三個帳號對同一組呼叫各照自己的政策（第 6 節 `LETS_THROUGH`），被擋的不送
  任何請求，送出的都帶自己的 key。
- vendored `policy.py` 對帳號目錄：要本 uid 的 0700 目錄、單一連結的 0600 檔、路上沒有連結、schema 4 與鍵集合。`ProductStore(create=…)`
  建的帳號目錄就是這樣；Supervisor 式還原留下 0755／0644 時子程式每個呼叫都 `HEADSCALE_POLICY_UNAVAILABLE`（不送任何請求），帳號的 store
  以 existing-only 開啟（管理程序在任何子程式之前做）就收回 0700／0600，子程式照常。add-on 裡 entrypoint 的還原修復本來就先做這件事
  （HM-13a），測試另外證明「沒修好時是拒絕，不是放行」。
- 真子程式（`run_product` 的 ProfileManager＋真 Supervisor，額外帳號經 HM-09 的 exec wrapper）三個帳號、一台假伺服器（綁本機私有位址，
  Headscale 子程式拒 loopback）：經 8081 時閘道先照政策擋；**直連 loopback**（拿得到 child token 的呼叫者，T-23）時子程式自己照自己帳號
  的政策擋；別帳號的 child token 一律 401。存 B 的政策只換 B 的 PID，之後 B 的子程式照新政策放行。

### 3.2 Headscale 伺服器拒絕 key 時的認證退避（DQ-25；受開關管）

- DQ-25（HM-09）：開通後每個帳號的監看在後端拒絕憑證時退避 15、30、60、120、300 秒，避免拿錯的 key 一直打後端。`auth_refused(reason)`
  只認探測 reason 開頭的固定文字；Headscale 那條釘的是 `HEADSCALE_INVALID_CREDENTIAL`，那是 client 拒絕送出格式錯的 key 時才有
  （存檔的 `HeadscaleConnection` 已經擋掉，到不了）。
- 實測：真的 Headscale 子程式（vendored 程式在自己的直譯器裡）在伺服器回 401 時回錯誤物件
  `{"code":"HEADSCALE_UPSTREAM_ERROR","http_status":401,"grpc_code":16,"outcome":"rejected","retryable":false,"category":"authentication"}`，
  `probe_reason` 只留 `error`／`message`，reason 變成通用的 `BACKEND_INVALID_RESPONSE: the health check answer was not the expected one`，
  退避從來沒生效（403、500 也是同一句 reason）。
- 修法：`health.refused_login(reply)`：探測回覆是錯誤、只有一段文字、內容是 `code` 為 `HEADSCALE_UPSTREAM_ERROR` 而且 `http_status` 是整數
  401 的物件。`HealthMonitor` 在這次檢查的 `_check` 裡算出 `login_refused`，**只有帶 `auth_backoff` 的監看**（ProfileManager 給的，開通才有）
  才把它算進 `auth_refusals`；記下的 reason、面板、任何回應都不變。開關關時監看照今天（每 15 秒、不退避）。
- 沒做：把 reason 改成看得出是 401（例如 `HEADSCALE_UPSTREAM_ERROR status=401`）。那會改開關關時面板與診斷頁看得到的文字（不受開關管的
  改變），列進第 15 節。

### 3.3 面板「後端設定」的說明（受開關管）

- 今天 Headscale 的說明寫「這個 Add-on 只管理同一個 Headscale 執行個體」。開通後每個帳號各自連一台（DQ-26：同一台不同政策或多台），
  這句會讓人以為所有帳號都要同一台；計畫 §9 的「建議每帳號不同 key」最該出現在輸入 key 的地方。
- `connectionHelpFor(product, scoped)`：`scoped` 是 `api.profile !== null`（面板有帳號＝開通）。開通時 Headscale 換成「填這個帳號要管理的
  Headscale …API 金鑰是整台 Headscale 的管理權限：建議每個帳號在 Headscale 各建一把，不要共用；共用同一把金鑰的帳號之間只靠工具權限
  分權，在 Headscale 撤銷它也會同時停掉這些帳號」；其他產品與開關關時逐字照 `connectionHelp`（node 測試逐產品比）。
- 不做（HM-27 交來的另一件）：面板不另外顯示「密鑰網址固定只放 `https://claude.ai`」。這條規則開關關時今天也沒在面板顯示，開通不改它；
  寫在 DOCS（`unreleased-changes.md` 第 3.8 節）。

### 3.4 開關一開就會紅的既有測試（`tests/product_switch.py`）

- 做法：只在本機、不 commit，把 `features.py` 的 `MULTI_PROFILE_PRODUCTS` 暫時改成 `frozenset({'headscale'})`，跑 pytest 與 packaging
  unittest（腳本與輸出在 repo 外 `scratchpad/HM-26/`，跑完一律 `git checkout` 還原）。
- 紅的原因都一樣：這些測試寫的是**沒開通**的 add-on（HM-01 黃金回歸、兩個契約凍結、沒開通的 runtime、子程式 spec 的快照、單帳號的真
  runtime、單帳號還原的探針檢查），卻靠 repo 的開關是空的。開關一有 headscale，Headscale 那一格就變成開通的 add-on：管理 API 沒帶
  `X-MCP-Profile` 回 400、spec 多 `WOOW_MCP_DENY_LOOPBACK`、loopback 假後端被拒、健康監看要兩次失敗、8081 是分派器……
- 改法（測試，不動任何期望值）：
  - `tests/product_switch.py`：`switched_off` fixture（測試的 `product` 參數那個產品，在這個測試期間從開關拿掉；別的產品照 repo）、
    `off(product)` context manager、`preamble(product)`（子程序前置碼）。fixture 只對 pytest 自己跑的測試生效：`test_router_passthrough.py`
    在 `switched_on(product)` 裡直接呼叫黃金回歸與兩個凍結的測試函式，照樣是開通的版本。
  - 加 `@pytest.mark.usefixtures('switched_off')` 的（12 個檔、14 個測試函式）：`test_single_profile_golden.py::test_default_profile_golden`；
    `test_admin_contract_freeze.py` 的 `test_management_answer_shapes`、`test_builtin_only_answer_shapes`（後者開關開時沒紅，它是同一個
    凍結的另一半，一起釘）；`test_mcp_contract_freeze.py::test_mcp_contract_freeze`；
    `test_child_bearer.py::test_child_spec_gives_the_seven_python_children_their_child_token`；
    `test_child_port_param.py::test_one_port_reaches_every_child_request`；`test_origin_policy.py::test_switched_off_the_policy_does_not_exist`；
    `test_product_boundary.py::test_config_api_typed_secret_safe_and_restart_on_rotation`；
    `test_profile_lifecycle.py::test_switched_off_run_product_gives_the_default_profile_todays_supervisor`；`test_profile_runtime.py` 的
    `test_run_product_serves_the_default_profiles_runtime`、`test_starting_the_default_profile_adds_no_file`；
    `test_request_budget_gateway.py::test_every_products_runtime_reads_under_the_budget_and_the_guard`；
    `test_restore_review.py::test_after_a_single_profile_restore_the_bootstrap_only_adds_the_notice`；
    `test_role_lifecycle.py::test_committed_runtime_backend_transition_is_joined`。
  - `off(product)`：`test_child_port_param.py` 的 spec 快照（參數是 case）、`test_upgrade_zero_rewrite.py` 沒開通的那一格。
  - `preamble(product)`：`test_real_products.py` 的單帳號真 runtime、`test_upgrade_hooks.py` 的舊版（一律沒開通）與「兩邊都沒開通」。
  - `multi_profile_runtime(switch=False)`：從「不動開關」改成「這個產品從開關拿掉」（`test_router_passthrough.py` 兩個沒開通的測試用它）。
  - `packaging/test_container_probe.py` 的還原階段（探針的 app 是 Headscale）：`setUp` 把它從開關拿掉，要開通的案例自己再打開。
  - `tests/test_upgrade_hooks.py` 的真 runtime 測試加 Headscale（0.5.0 升版比對會跑這兩個 hook）。
- 沒改、交升版片：`test_upgrade_zero_rewrite.py::test_multi_profile_is_switched_off_for_every_product` 釘「開關是空的」，那是「只有升版 PR
  能開通」的守門，升版 PR 加開關時一起改（計畫 §11.3 的逐檔清單本來就有 `features.py`）。
- 開關空的時候（repo 今天）這些改動都是空操作：拿掉一個不在集合裡的產品，集合不變；HM-01 的期望值、兩個凍結的案例、快照一個字都沒改。

### 3.5 考慮過、沒做的

- 子程式用 child token 確認 state 是自己的：vendored `policy.py` 可以多比 `state.child_token == WOOW_MCP_CHILD_TOKEN`，接錯 state 時
  （同網址同 key）也會 fail closed。計畫沒要求，路徑已由測試釘住；這是改 vendored 子程式、開關關也生效的改變，列第 15 節交審查判斷。
- 照 PaaS 記 Headscale 被拒 Origin 的 deny 行：HA 今天不記，開通也照舊（契約 #9）。
- 另做 Headscale 的方法表讓 `/api/origin-policy` 的其他方法也回 404：只把 405 變 404，不擋任何東西，還要多一條產品分支（第 4 節）。

## 4. 本片定的事（計畫沒寫死的細節、HM-27 交來的三件）

| 事 | 定案 | 理由 |
|---|---|---|
| DQ-26 Headscale 形態 | 照計畫建議實作：同一台不同政策與多台都支援；建議每帳號不同 key（DOCS、開通時的面板說明），不強制、不檢查 | 計畫 §13.3 的建議；題目仍待使用者確認（`decisions.md`，最晚 Headscale 升版 PR 前） |
| `/api/origin-policy` 對 Headscale（HM-27 審查 S-5 交來） | 照契約第 2.6 節寫定：GET 與形狀正確的 PUT 回未知操作的 404，其他方法 405、形狀錯的 PUT 400 | 方法表全 add-on 一份、第 ⑤ 步不看產品；另做一份只是 405 變 404，不擋任何東西 |
| 面板顯示「固定只放 claude.ai」（HM-27 交來） | 不顯示；DOCS 寫 | 開關關的面板今天也沒顯示這條規則，開通不改規則 |
| Headscale 被拒 Origin 記 deny 行（HM-27 交來） | 照舊不記（契約 #9） | 和今天的單帳號行為一致；PaaS 的節流與呈現規則屬 HM-27 的政策檔，Headscale 沒有政策 |
| 認證退避怎麼認 Headscale 拒絕的 key | 讀探測回覆的錯誤物件（`code`＋`http_status` 401），只給帶 `auth_backoff` 的監看 | 改 reason 文字會改開關關時看得到的文字；只讀回覆不改任何輸出 |
| 403、500 算不算 | 不算（只有 401） | Headscale 的 API key 只有整台權限，403 不是 key 錯；500 是伺服器自己的問題，不該拉長檢查間隔 |
| 開關一開就紅的既有測試 | 在本片改成釘自己的產品沒開通（`tests/product_switch.py`），全部產品通用 | 任務要升版 PR 只加開關與版號；釘的是測試的前提，不是期望值 |

## 5. PaaS 對照

- pin `69ac425`：Headscale 新來源 422 在 `apps/headscale/headscale_mcp_admin/connection.py:104-109`（比整條正規化後的網址；HA 比來源，
  契約 #115）；子程式讀 `MCP_ADMIN_CONFIG`（`launcher.py:27-31`）；私網要部署宣告 `HEADSCALE_MCP_ALLOWED_PRIVATE_CIDRS`
  （`headscale_mcp_server/http_policy.py:59-110`）；存政策不重啟子程式（`Pc/routers/settings.py:429-446`、`Pc/routers/tools.py:69-70,171-174`）。
- pin 之後（本機唯讀 PaaS repo `origin/main`＝`5ef1046`，2026-11-18）：`git log 69ac425..origin/main -- apps/headscale` 只有 `3b135ca`、
  `1637a0f`（閘道的 JSON 結構守門與位元組預算，HM-31 已對齊）；`routers/tools.py`、`routers/settings.py` 沒變。Headscale 的多帳號行為
  pin 之後沒變。只用 `git log`、`show`、`grep`；沒有 fetch、checkout 或寫入。
- PaaS 的 Headscale 多帳號測試（`paas-test-mapping.md` 第 22 檔 `test_headscale_volume_crash_after_each_step_then_rerun_converges`）
  是還原工具的崩潰重做，HA 對到 `tests/test_restore_lock.py`（HM-13b）；本片的測試不重做它。

## 6. 測試（新與改過的）

`tests/test_headscale_multi_profile.py`（新，15 案；開關開與關兩種模式的用 `switched-on`／`switched-off` 標）：

| 案例 | 驗什麼 |
|---|---|
| `test_each_child_is_started_on_its_own_profiles_state_and_applies_its_policy`（兩種） | 管理程序真的建出來的每個 spec：`HEADSCALE_MCP_STATE_PATH`、cwd、HOME、child token、key 都是自己帳號的，argv 與環境沒有別的帳號的目錄、token、child token；開通時有 `WOOW_MCP_DENY_LOOPBACK`。用那個 spec 的直譯器與環境跑 vendored 子程式：三個帳號（B 與預設同 key、C 自己的 key）對同一組呼叫各照自己的政策、被擋的不送請求、送出的帶自己的 key。開關關：B、C 休眠（沒有 spec，token 撤銷） |
| `test_a_profile_directory_a_restore_widened_is_refused_until_its_store_tightens_it` | 只放寬目錄（0755／0600）、只放寬檔案（0700／0644）、兩個都放寬（0755／0644，還原留下的）：子程式每個呼叫 `HEADSCALE_POLICY_UNAVAILABLE`、不送請求；store 以 existing-only 開過就收回 0700／0600、照常 |
| `test_a_restore_revokes_every_profile_and_each_child_then_applies_the_backups_policy` | HM-13b 的守門對 Headscale 卷：三個帳號撤銷、child token 換新；還原紀錄有網址與政策、沒有 key 與 token；子程式照備份的政策（備份後存的政策隨還原消失） |
| `test_real_children_keep_their_own_policy_and_key_through_8081_and_on_loopback` | 三個真 Headscale 子程式、一台假伺服器：經 8081 照政策、每個請求帶該帳號的 key；直連 loopback：別帳號的 child token 401、自己的子程式照自己的政策擋；存 B 的政策只換 B 的 PID，之後 B 照新政策 |
| `test_each_token_opens_only_its_own_profile_on_both_connection_methods`（兩種） | 每把 token 兩種接法只開自己的子程式、別的子程式收不到；跨帳號 session 404；陌生、撤銷、輪替掉的 token：Bearer 401、密鑰網址 404、沒有子程式收到。開關關：B、C 的舊 token 是陌生 token |
| `test_every_profiles_secret_url_takes_only_claude_ai_as_origin`（兩種） | 每個帳號：不帶 Origin 與剛好 `https://claude.ai` 200；8 種別的寫法與兩個 Origin 403 固定本體、子程式收不到；Bearer 帶 Origin 403；開通時 `/api/origin-policy` 是未知操作；沒有紀錄、沒有政策檔 |
| `test_saving_one_profiles_policy_restarts_only_its_child`（兩種） | 存 B 的政策：只有 B 的子程式多啟動一次、只有 B 的工具清單變；開關關：預設帳號的子程式重啟（今天） |
| `test_a_profiles_url_moved_to_another_origin_needs_its_api_key_again`（兩種） | 開通（B）：只改網址到別的來源 422、什麼都沒寫、沒重啟；同一來源的三種寫法不用 key；帶 key 存檔只重啟 B、token 不換；loopback 400。開關關（預設帳號）：key 跟著網址、loopback 照存（今天） |
| `test_a_key_the_headscale_server_refuses_backs_the_profiles_checks_off`（兩種） | 真子程式對 401／403／500 的回覆；`refused_login` 只認 401；開通的監看 15→30→60，403、500、成功都歸零；開關關照舊每 15 秒；reason 兩種模式一樣 |

改過的既有測試：第 3.4 節（`product_switch` 的標記、`off`、`preamble`、`multi_profile_runtime(switch=False)`、
`packaging/test_container_probe.py` 的還原階段）；`tests/test_upgrade_hooks.py` 的真 runtime 測試加 Headscale（舊版沒開通、新版開通或
也沒開通；兩個 hook 只讀、照樣過）。面板：`contracts.test.mjs` 一案、`backend-identity.spec.mjs` 一案。

## 7. 先紅後綠與突變

輸出都在 repo 外 `scratchpad/HM-26/logs/`（暫存，交出後刪）。

### 7.1 先紅後綠

| 步驟 | commit | 結果 |
|---|---|---|
| 新測試 | `fbbc287`（重建前 `557401a`） | 14 案：2 案紅（`test_a_key_the_headscale_server_refuses_backs_the_profiles_checks_off` 兩種模式：`health.refused_login` 不存在），12 案綠（前面各片做好的行為，本片釘住）。第一次跑時另有 2 案紅是測試自己的錯（健康監看的 `GET /api/v1/health` 混進工具請求的比對、caplog 抓到 httpx 的 INFO 行），commit 前修好測試 |
| 修 | `7d6e438`（`9141e2c`） | 新檔 14 案全過 |
| 面板測試 | `95bf0b5`（`4ffcef7`） | node：`contracts.test.mjs` 整檔紅（`connectionHelpFor` 不存在，import 失敗；用 `git archive 4ffcef7` 重跑確認，面板的檔和 `95bf0b5` 相同）；Playwright：這案紅（面板顯示今天的說明），其餘 166 案過 |
| 面板修 | `7c82b17`（`90452c3`） | `contracts.test.mjs` 18 案全過（`git archive 90452c3` 重跑）；面板全套見第 8 節 |
| 還原守門那案 | `7e9e1d9`（`9330bd1`） | 加 1 案，一加就綠（HM-13b 已做好，本片釘住 Headscale 卷）；新檔 15 案全過 |
| 目錄與檔案分開放寬 | `1996759` | 突變 M10 在原本的測試活下來（第 7.2 節）；改測試後照綠（不改程式），M10、M11 都抓到 |
| 開關一開的既有測試 | `d59be1e`（`2d69b7f`）；本機模擬（不 commit） | 改之前（全套）：pytest 23 案、packaging unittest 2 案紅（第 3.4 節）。改之後（53 個相關檔）：2,034 案，2,031 通過、3 案紅（要 root 的 2 案、`test_multi_profile_is_switched_off_for_every_product`）；packaging unittest 366 案 OK（skipped=5） |

### 7.2 突變（每個單獨套上、只跑相關案例、跑完 `git checkout` 還原；腳本 `scratchpad/HM-26/mutate.py`）

| 突變 | 改了什麼 | 跑的案例（`-k`） | 結果 |
|---|---|---|---|
| M1 | 額外帳號的子程式讀預設帳號的 state（`products.child_spec` 的 `HEADSCALE_MCP_STATE_PATH`；FM-88 的風險本身） | `test_each_child_is_started…`、`test_real_children…` | 抓到：開通那案，spec 的 state 路徑不是自己帳號的 |
| M2 | Headscale 存政策不重啟子程式（`gateway.py` 的重啟產品表拿掉 headscale） | `test_saving_one_profiles_policy…`、`test_real_children…` | 抓到：真子程式那案等不到 B 換 PID（逾時） |
| M3 | 額外帳號的 app 拿不到 Headscale 的 Origin 規則（`profile_runtime.py`） | `test_every_profiles_secret_url…` | 抓到：開通那案，B 的密鑰網址收下 `https://evil.invalid` |
| M4 | `refused_login` 沒接上監看（`health.py`） | `test_a_key_the_headscale_server_refuses…` | 抓到：開通那案，401 之後的間隔是測試的 `HEALTH_INTERVAL`（0.5 秒），不是 15 |
| M5 | 沒開通也顯示每帳號的說明（`contracts.js`） | node `contracts.test.mjs` | 抓到：HM-26 那案紅（17 過、1 紅） |
| M6 | 改網址到別的來源照用舊 key（`backend_edit.new_origin_refused` 一律不擋） | `test_a_profiles_url_moved…` | 抓到：開通那案回 200，不是 422 |
| M7 | 開通後 loopback 照存（`products.py` 的 loopback 判斷一律 False） | `test_a_profiles_url_moved…` | 抓到：loopback 回 200，不是 400 |
| M8 | 子程式不看操作層級的拒絕（vendored `policy.py`） | `test_each_child_is_started…`、`test_a_restore_revokes…` | 抓到：開通那案，C 的子程式放行了政策拒絕的操作 |
| M9 | 403、500 也算拒絕 key（`health.refused_login` 不看 401） | `test_a_key_the_headscale_server_refuses…` | 抓到：403 被當成拒絕 key |
| M10 | 子程式不要求帳號目錄是 0700（vendored `policy.py`） | `test_a_profile_directory_a_restore_widened…` | **第一次活下來**：原本的測試同時放寬目錄與檔案，檔案那關先擋。`1996759` 改成三種組合後抓到（0o755／0o600 那組） |
| M11 | 子程式不要求 state 檔是 0600（vendored `policy.py`；M10 之後加的） | 同上 | 抓到（`1996759`；0o700／0o644 那組） |

- 每個突變都只在本機工作目錄套上，跑完 `git checkout` 還原，最後 `git status` 乾淨。M1～M4、M6～M10 第一次跑在 `f158b20` 的樹上，
  M10 重跑與 M11 在 `1996759` 上。
- 開關關時沒有對應的突變：開關關的行為由兩種模式的案例與 HM-01 黃金回歸、兩個契約凍結守住（第 8 節）。

### 7.3 重建沒推過的 commit（秘密預檢）

- 第一次跑秘密預檢（`cfffb24`）：1 命中，`generic-api-key`，`tests/test_headscale_multi_profile.py:66`，最早在 `557401a`。是測試的假值
  `REPLACEMENT_KEY`（`DUMMY-hm26-…`，照 `tests/fixtures/owner_defaults/README.md` 的寫法），但字元種類多、熵過了規則的門檻。builder 的
  歷史掃描（`packaging/supply_chain.py` 的 `source_scans`，整個 repo 的歷史、零容忍）合併後也會掃到它，只在之後的 commit 改值去不掉。
- 這 7 個 commit 都還沒推（沒有任何遠端 ref 含它們；交出後由 finalize 推）。照「不改已發布的歷史」，用 `git commit-tree` 一個一個重建
  （腳本 `scratchpad/HM-26/rewrite.sh`；沒有用 rebase、amend、force push，工作目錄沒動，最後用 `git update-ref` 把分支移到重建的
  commit，舊的 commit 沒有任何 ref 指著）：只把這個值換成
  `DUMMY-hm26-headscale-new-key`（同一把 gitleaks、同一份設定掃整個檔 0 命中；先用 7 個候選值試過），訊息、作者、作者時間不變；腳本逐一
  核對每個新 commit 和舊的只差這一行、訊息逐位元相同，全部過了才移分支。
- 舊 → 新：`557401a` → `fbbc287`、`9141e2c` → `7d6e438`、`4ffcef7` → `95bf0b5`、`90452c3` → `7c82b17`、`9330bd1` → `7e9e1d9`、
  `2d69b7f` → `d59be1e`、`cfffb24` → `f158b20`。第 7.1 節的紅綠紀錄是在舊 SHA 上跑的，兩邊只差這個值。
- 重建後（`f158b20`）秘密預檢 OK、0 命中；新檔換值之後重跑見第 8 節。

## 8. 本機檢查（一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，跑完刪掉；pytest 都排在共用的 conftest 鎖後面）

| 檢查 | 結果 |
|---|---|
| pytest，開關關（repo 現狀）：53 個相關檔（新檔、改過的 15 個、用到 `multi_profile_runtime`／`product_switch` 等測試工具的、讀開關的、Headscale 與健康監看的；含 HM-01 黃金回歸 `test_single_profile_golden.py`、`test_upgrade_zero_rewrite.py`、`test_router_passthrough.py`、`test_upgrade_hooks.py`、`test_real_products.py`；`logs/j-off-53.log`） | 2,034 案：2,032 通過、2 案紅，637 秒。紅的 2 案要 root（`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`），基準本來就紅。跑的是 `2d69b7f` 的樹（和 `d59be1e` 只差那個值） |
| pytest，暫時開通 headscale（同 53 個檔；`sim-after-on/chunk1.txt`） | 2,034 案：2,031 通過、3 案紅，683 秒：要 root 的同 2 案、`test_upgrade_zero_rewrite.py::test_multi_profile_is_switched_off_for_every_product`（釘開關的值，交升版 PR）。跑的時候測試還沒 commit，和 `d59be1e` 只差 `multi_profile_runtime.py` 一段 docstring 的換行 |
| 新檔（`logs/m-base.log`、`m-final.log`） | `f158b20`（換過值）：15 案全過；`1996759`（M10 補強後）：15 案全過，15.8 秒 |
| packaging unittest（開關關；`ha-gh-release-20261117` 的 venv，Python 3.13.15） | Ran 366、OK（skipped=5），27 秒 |
| packaging unittest（暫時開通 headscale） | Ran 366、OK（skipped=5）；改之前 2 案紅 |
| `packaging/validate.py`（同一個 venv） | PASS |
| `scripts/tool_inventory.py`（檢查模式） | exit 0（工具面沒變） |
| `node --test packages/mcp-admin-ui/tests/*.test.mjs`（node v22.23.3） | 119 案全過（基準 118） |
| `npm run build`＋build closure | PASS |
| Playwright 全套（`single`＋`profiles-on`，照 CI；面板的檔和 `f158b20` 相同） | 167 案全過，5.4 分鐘（基準 166；新案 1） |
| 雙向控制字元（`c90b214..f158b20` 新增的 1,159 行、commit 訊息、碰過的 31 個檔全文） | 0 |

### 8.1 只在 CI 跑的、本機沒跑的

- 本機沒跑全套 pytest（共用鎖要排隊）：跑了上面 53 個相關檔、兩種模式；改之前的全套模擬找到的 23 案都在這 53 個檔裡。CI 跑全套。
- 要 root 的既有案例本機一定紅：上表 2 案；`test_restore_detection.py` 的 `test_root_*`（HM-27 筆記記 5 案）不在 53 個檔裡、沒跑。
  CI 以 root 跑；本片沒碰它們測的程式。
- `test_boundary.py::test_the_n8n_child_loads_the_one_pinned_native_addon_and_n8n_mcp_uses_it`：本機少 n8n 的原生模組，改之前的全套模擬
  就紅、和開關無關；不在 53 個檔裡。
- Playwright：本機 1.61.1，Chromium 1228（`.local-browsers` 從同版本的面板 clone 複製，等同 `npm run browser:install`，不進 git）。
- TMPDIR：手動建的都用完整的字面路徑刪；`pt.sh`、`simulate.sh`、`post.sh` 的迴圈用 `mktemp` 剛建的變數刪（`rm -rf "$T"`），最後逐一核對
  `tmpdirs.txt` 列的路徑都不在了。

## 9. 預檢與帳本

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `python3 scripts/secret_precheck.py --tools …/scratchpad/scan0414/tools` | `cfffb24`（重建前）：1 命中（第 7.3 節）；`f158b20`（重建後）：OK，0 命中（gitleaks 8.28.0，pin、驗過；7 個 commit） |
| 帳本 | `python3 scripts/ledger_precheck.py` | OK：`runtime-patches.json` 180、`runtime-sources.json` 70、`docs/tool-surface.json` 159 個摘要 0 漂移、0 缺；列管的 `app.js`、`contracts.js` 隨 `runtime-patches.json` 更新；沒有新的執行檔；`health.py` 是沒列管的既有執行檔（ledger-tracking 第 3 節本來就不列，列為 review） |

- 帳本：`runtime-patches.json` 的 `app.js`、`contracts.js` 兩列重算 sha256，說明補「2026-11-19 HM-26（…）」。`docs/tool-surface.*` 沒變
  （沒有工具改動；`scripts/tool_inventory.py` exit 0）。
- 本筆記 commit 之後兩個預檢再跑一次，結果在交給主對話的回報裡（本筆記不能記自己 commit 之後的結果）。

## 10. 文件

| 檔 | 改了什麼 |
|---|---|
| `docs/multi-profile/contract.md` | 第 2.6 節 Headscale 那段定案；第 7 節健康監看列補 Headscale 的 401；第 9 節開頭（列號暫定）、#9、#129～#132；第 10 節一列 |
| `docs/multi-profile/acceptance-matrix.md` | 登記表：本片的測試檔定名（新增）、`tests/product_switch.py`；T-04、T-05、T-07、T-23、T-24 補 Headscale |
| `docs/multi-profile/decisions.md` | DQ-26 列補實作狀態、最晚期限改「Headscale 升版 PR 前」；變更紀錄一列 |
| `docs/multi-profile/threat-model.md` | 第 3 節 Headscale 一點 |
| `docs/multi-profile/unreleased-changes.md` | 第 3.8 節：HM-26 一點、開通版 CHANGELOG 的 HS1～HS7、DOCS 段落；第 4.2 節一列 |
| `docs/operations/acceptance.md` | 「Headscale 開通版（0.5.0）在 HAOS 要加的項目」 |
| 本筆記 | — |

## 11. 契約第 9 節（列號暫定）

- 新列 #129～#132（Headscale 帳號的形態 DQ-26／子程式讀的政策／存政策時的子程式／子程式能連的位址），#9 補「開通後每個帳號都一樣」；
  第 2.6 節 Headscale 那段定案；第 7 節健康監看列補 Headscale 的 401；第 10 節一列。
- **列號暫定**：基準 `c90b214` 的最後一列是 #128。HM-21～HM-25 同時在準備，各自接在 #128 之後；後合併的一方接在當時最後一列之後重編，
  引用自己列號的地方跟著改（契約第 9 節開頭、#129 列裡的 #130、第 10 節本片那列；`acceptance-matrix.md` T-04、T-07、T-23 的 §8.8 欄；
  `docs/operations/acceptance.md` Headscale 的 T-04；本筆記），同 HM-27 合併 HM-13c 時的做法。契約第 2.6 節與 `decisions.md` 沒有引用。
  注意：#40 列 PaaS 欄的「（#131）」是 PaaS 的編號，本來就有，和本片的 #131 無關。
- 這四列不是 FEATURE-MATRIX 的列（FM-88、FM-90 說到同一件事）；`deviation-trace.md`、`paas-test-mapping.md` 由 repo 外的產生器產，
  兩處「`tests/test_headscale_multi_profile.py`（HM-26，暫定名）」下次重產時改成定案（產生器的規格 `gen_trace.py`、`paas_mapping_spec.py`
  寫死了「暫定名」，交主對話；同 HM-27 的前例）。本片只改了 `acceptance-matrix.md` 的登記表（狀態「新增」）。

## 12. 威脅筆記（短；給接著做的獨立安全審查）

- 資產：每個帳號的 Headscale API key（整台管理權限；Headscale 沒有 key 層級的權限）與 MCP token；工具政策是同一台、同一把 key 的帳號
  之間唯一的分權（FM-88）。
- 威脅與現有防線：
  1. 帳號 A 的 token 持有人想用帳號 B 的權限：8081 只看 token 選帳號（HM-08）；閘道照 A 的政策擋；A 的子程式只讀 A 的 state（本片測試釘
     住 spec 與執行期）。剩下的風險只在「子程式拿錯 state 路徑」這種程式錯誤，測試會紅（突變 M1）。
  2. 同一個容器裡拿得到某個 child token 的呼叫者直連 loopback：子程式只認自己的 child bearer（HM-06），政策照自己帳號（本片真子程式測試）。
  3. 把已存的 key 送到別台：開通後改網址到別的來源要重填 key（HM-12，422）；loopback 存檔與執行期都拒（HM-20；Headscale 子程式本來就拒）。
  4. 外洩的密鑰網址被別的網頁拿去用：每個帳號的密鑰網址只放 `https://claude.ai`、Bearer 帶 Origin 403（本片測試）。
  5. 還原把舊 token 帶回來：守門撤銷每個帳號、換 child token（HM-13b），還原後的權限放寬時子程式拒絕而不是放行（本片測試）。
  6. 被拒的 key 讓監看一直打 Headscale：開通後照 DQ-25 退避（本片修）；開關關照舊每 15 秒（Headscale 沒有 key 的暴力破解鎖定，影響小）。
- 已知限制（不在本片修）：同 uid＝同一個信任邊界，被攻破的子程式讀得到每個帳號的 key（威脅模型第 1 節）；同 key 帳號之間只靠政策；
  建議每帳號不同 key 但不強制（DQ-26）；子程式不核對 state 的 child token（第 3.5 節，交審查判斷要不要加）。
- 請審查特別看：`health.refused_login` 只在 `auth_backoff` 時生效、不改任何輸出；`tests/product_switch.py` 只拿掉測試自己的產品、不放寬任何
  期望值；面板說明只在 `api.profile !== null` 時換。

## 13. HAOS 實測要什麼（Headscale 升版時；本片沒碰任何主機）

詳見 `docs/operations/acceptance.md` 新的「Headscale 開通版（0.5.0）在 HAOS 要加的項目」。要使用者批准的真後端身分：

- QA 用的 Headscale 上 2～3 把專用、短效期的 API key（同一台：一把給預設帳號與一個額外帳號共用、一把給另一個額外帳號自己用），驗完撤銷
  （`headscale apikeys expire`），清理證明進證據（T-29）。
- 寫入只對一個專用的測試使用者（例如 `hm26-test`）與它的 preauth key；不碰正式的使用者、節點、路由與 ACL 政策（`headscale_policy` 不做
  apply）。只有一台 Headscale 時，多台只在 CI 驗。
- T 列：T-01、T-02（上限 3）、T-04（Headscale 版）、T-05、T-07、T-08、T-09、T-13、T-14、T-20（0.4.19 → 0.5.0）、T-21、T-23、T-24、T-27、
  T-29，加上「每次升版都要重驗」的 UC-08、sentinel、UC-10、記 Supervisor 版本。

## 14. 交接

- **Headscale 升版片（0.4.19 → 0.5.0；不是本片）**：`features.MULTI_PROFILE_PRODUCTS` 加 `headscale`；
  `test_upgrade_zero_rewrite.py::test_multi_profile_is_switched_off_for_every_product` 跟著改（它釘的是開關的值）；版號資料 7 處
  （`docs/operations/release.md`）；`addons/headscale/`（`config.yaml`、`CHANGELOG.md` 照 `unreleased-changes.md` 第 3.8 節 HS1～HS7 與
  §7.2 的共通句子、`DOCS.md` 照同一節的段落；`upgrade-check/seed`、`verify` 從 `packaging/hooks/` 搬，本片已讓 hook 的真 runtime 測試跑
  Headscale）；容器驗收的假後端本來就照 Headscale 的 bridge 做；HAOS 驗收照第 13 節。開關一開，`product_switch` 已處理的既有測試照綠
  （第 7 節的模擬）。
- **其他產品片（HM-21～HM-25）**：同一批既有測試開關一開也會紅；`tests/product_switch.py` 的 fixture 對所有產品有效，哪一片後合併就保留
  一份、把自己的標記併進來（衝突時兩邊的 `usefixtures` 是同一個意思）。契約第 9 節列號見第 11 節。
- **HM-18**：DOCS 的「每帳號一把 key」與 Headscale 的 Origin 規則照 `unreleased-changes.md` 第 3.8 節；`docs/operations/guide.md` 事故處理
  第 2 步補 Headscale（威脅模型第 4 節）。
- **HM-29**：給 PaaS 的回補建議可以加「PaaS 的 Headscale 存政策不重啟子程式、子程式每次呼叫讀設定」與 HA 的差異說明（契約 #131）；不是缺陷。
- **主對話**：`deviation-trace.md`、`paas-test-mapping.md` 的產生器規格（第 11 節）；DQ-26 的確認（第 15 節）。

## 15. 要使用者決定的事

1. **DQ-26（Headscale 形態）**：計畫建議「同一台不同政策與多台都支援；建議每帳號不同 key，不強制」。本片照這個做了（DOCS、開通時的面板
   說明、契約 #129 類型「待決」）。使用者確認，或要改成「強制每帳號不同 key」（例如存檔時擋同一台同一把 key），都要在 Headscale 升版 PR 之前。
2. **要不要讓子程式核對 state 的 child token**（第 3.5 節）：接錯 state 時（同網址同 key）也 fail closed。是改 vendored 子程式、開關關也生效
   的改變；計畫沒要求，交接著做的獨立安全審查判斷，要做就另開一片。
3. **Headscale 健康檢查的 reason 文字**（第 3.2 節）：伺服器拒絕 key 時面板與診斷頁今天只看到 `BACKEND_INVALID_RESPONSE: the health check
   answer was not the expected one`。要改成看得出是 401，會改開關關時看得到的文字（不受開關管的改變），要另開一片並寫進各產品 CHANGELOG。

## 16. 開放問題

- 其他產品片（HM-21～HM-25）同時在改同一批既有測試；後合併的一方要合成一份（第 14 節）。
- 本機的 conftest 測試鎖是全機共用、等滿 120 秒就失敗，多條線同時跑 pytest 時要排很久；第 8 節的秒數是 pytest 自己報的執行時間，不含排隊。
- 子程式直連 loopback 的政策只在真子程式測試驗（CI 的 root 環境也跑）；HAOS 上要照第 13 節再驗。

## 17. commit

| commit | 內容 |
|---|---|
| `fbbc287` | test(headscale)：新測試檔 14 案（先紅） |
| `7d6e438` | fix(health)：`refused_login`，監看的認證退避 |
| `95bf0b5` | test(ui)：面板說明的 node 與 Playwright 測試（先紅） |
| `7c82b17` | feat(ui)：`connectionHelpFor`；帳本 |
| `7e9e1d9` | test(headscale)：還原守門那案 |
| `d59be1e` | test：`tests/product_switch.py`，開關關的測試釘自己的產品 |
| `f158b20` | docs(multi-profile)：契約、驗收矩陣、決策、威脅模型、`unreleased-changes.md`、HAOS 驗收 |
| `1996759` | test(headscale)：目錄與檔案分開放寬（突變 M10） |
| 本筆記 | docs(provenance) |

前 7 個是第 7.3 節重建後的 SHA（舊的沒推過）；`1996759` 在重建之後。

commit 身分（作者、提交者）都是 woowtech；英文標題、繁中內文；照 DQ-36 不加 AI 署名。本筆記不能記自己 commit 之後的結果：
最後一次的預檢結果在交給主對話的回報裡。
