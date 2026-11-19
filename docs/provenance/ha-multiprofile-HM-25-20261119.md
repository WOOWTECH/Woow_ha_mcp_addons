# HA 多帳號 HM-25 provenance：n8n 開通的功能片（2026-11-19）

## 結論

- **本片是 n8n 開通的功能 PR**（計畫 §9 n8n 列、§12.3「HM-21～HM-26｜各產品開通」）。之後 n8n 的升版 PR 只要把 `'n8n'` 加進
  `features.MULTI_PROFILE_PRODUCTS`、照發版規則升 `addons/n8n/` 的版號與文件。本片沒動 `MULTI_PROFILE_PRODUCTS`、沒動 `addons/`、沒改版號。
- **`apps/n8n/run.py` 收斂到 ProfileRuntime**：n8n 的 runtime 改走 `run_product.run`，由 `run.py` 帶 n8n 的 adapter
  （`run_product.ProductAdapter`：`n8n_adapter` 的工具表與 child spec、預設帳號的 catalog 副本、額外帳號的 catalog 副本、刪帳號時的清理）。
  開關關時就是預設帳號單獨一份 `ProfileRuntime`（和其他產品一樣）；開關開時是 `ProfileManager`。`run.py` 自己的 listener、Supervisor、
  httpx client、健康監看、`make_apps` 都拿掉了。
- **額外帳號的子程式**（只在開通時；`features.enabled('n8n')` 呼叫時讀）：
  - 沒後端就不起子程式（DQ-22）。閘道自答 initialize 與 tools/list；**每支工具（含 7 支文件工具）都回 `-32603`「Backend not configured」**，
    不再出現「try again shortly」。健康檢查、套用狀態、帳號清單都是 `unconfigured`。判斷集中在 `profiles.documentation_child`：
    只有 n8n 的預設帳號沒後端也起文件子程式。
  - HOME 與 cwd 是 `profiles/<id>/child/`（不是帳號目錄本身、不和 `state.json` 同層）。不存在就建 0700；每次起之前都要是空目錄、
    不是連結。UC-01 確認了 n8n-mcp 不寫 HOME（第 3.4 節），所以照 Python 子程式的規則要求空目錄。
  - `nodes.db` 每帳號一份（DQ-04 照計畫建議）：`/tmp/woow-n8n-mcp/profiles/<id>/nodes.db`，不在 `/data`、不進備份。這個管理程序第一次
    起它的子程式前，在工作執行緒裡複製（67 MiB 的複製與 fsync 不卡事件迴圈），之後重起沿用；做不成就不起子程式，絕不用預設帳號的副本
    或映像內的檔（UC-09：單一租戶模式下 `instance_id` 一律是空字串，共用一份就會互看、互刪、互相回滾版本快照）。刪帳號時一起刪。
  - 命令列在入口後面多 `--port N`（n8n-mcp 不讀，照舊聽 `PORT`），P9 kit 與容器探針因此認得出每個帳號的子程式（HM-16 審查 SF-2）。
  - session 名額與逾時看自己 state 的 `n8n_session`（沒存過是 20 個、10 分鐘；新帳號不複製，DQ-02）：每個帳號 20 個。
  - 預設帳號的 HOME 與 cwd 仍是 `/data/mcp`、`nodes.db` 仍是 `/tmp/woow-n8n-mcp/nodes.db`，spec 逐位元同今天（快照
    `tests/contract/child_spec_default.json` 沒改）。
- **`x-n8n-*` 不轉送**：閘道本來就只轉自己的標頭與 3 個 session 標頭；本片在開關開與關、每個帳號、兩種接法加測試鎖住。
- **HM-12 交來的三件**：「沒存過的秘密不用帶」錄進 `profile-api-cases.json`（情境 `new-origin-unset-secret`，標
  `rerecord_on_real_backend`）；形狀比對改用面板看到的已存連線（`backend_edit.view`，n8n 的 `url`）；n8n 的 key 與 MCP access token
  交給 log 掃描（存的與請求送的都看）。
- **HM-16 kit 交來的一件**：P9 kit 的 `childkill --child-port` 與容器探針的多帳號階段都認得 n8n 的子程式了（不讀環境變數，只讀命令列）。
  容器探針不再拒絕 n8n，另外檢查每個額外帳號讀自己的 catalog 副本。
- **開關關時逐位元不變**：HM-01 黃金回歸的期望值沒改（只搬注入點，第 6 節），兩個契約凍結、child spec 快照、零改寫都照過。
- **先紅後綠**：新測試檔 `tests/test_n8n_multi_profile.py` 先寫 26 案，在改程式之前（`apps/n8n`、`packages/mcp-admin-core` 退回基準）
  7 失敗、19 錯誤；改完 26 全過。之後再補 2 案對齊 PaaS（名額跟記憶體上限、還原撤銷每個帳號），共 28 案全過（第 5 節）。
- **要使用者決定**：DQ-04、DQ-22 照計畫建議實作，使用者還沒確認（第 11 節）。n8n webhook 網址的 `permissive` 照舊，交本片之後的
  獨立安全審查（威脅說明在第 4 節）。
- 契約第 9 節新加第 129～131 列。**列號暫定**：其他產品的開通片（HM-21～HM-24、HM-26）同時在準備，後合併的片照 HM-27 的前例往後重編。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-25 n8n 開通（計畫 §9、§12.3；風險高、工作量 L；受開關管；要獨立審查） |
| 分支 | `feat/ha-multiprofile-hm25-n8n-20261119`（本機 commit；push 由之後的收尾步驟做） |
| 基準 | `claude-delivery` `c90b214`（#109 HM-16 的合併；已含 HM-13b、HM-13c、HM-27） |
| 依據 | 計畫 §3.3、§4.1、§5.1、§8.7、§8.8、§9、§12.0、§12.2、§12.3（含 11/17 的 HM-12 面板交接）；契約第 1.2、3.5、4.2、7、8、9 節；`acceptance.md` 的 T-01～T-29；FEATURE-MATRIX FM-15、84、140 |
| 對齊的 PaaS | pin `69ac425`；PaaS 本機 repo 的 `origin/main` `5ef1046`。n8n 的多帳號做法照計畫刻意不同（DB 位置、沒後端不起子程式），差異寫在契約第 9 節 |
| 不做的事 | 不改 `MULTI_PROFILE_PRODUCTS`、版號、`addons/`、`tests/conftest.py`；不碰任何 HA 主機、PaaS 或真後端 |

## 2. 改了什麼

縮寫同契約：`Hc/`＝`packages/mcp-admin-core/mcp_admin_core/`。

| 檔 | 內容 |
|---|---|
| `apps/n8n/run.py` | `run()` 建 n8n 的 adapter，交給 `run_product.run`（產品固定是 n8n；adapter 的名字每次啟動時才讀，測試能換）。`before_start` 就是原來的 `prepare_catalog()` 與它那一行訊息。`main()` 不變 |
| `apps/n8n/n8n_adapter.py` | `profile_of(directory)`（從目錄認帳號）；額外帳號的 child spec（沒後端回 None、HOME 與 cwd、自己的 catalog、`--port N`）；`prepare_profile_catalog`、`profile_catalog`、`prepare_child`（工作執行緒）、`remove_profile_catalog`（不跟隨連結）；`PACKAGED_CATALOG` 常數。預設帳號的 spec 不變 |
| `Hc/run_product.py` | `ProductAdapter`；`run(..., adapter=None)`：不給就是本 package 的工具表與 `products.child_spec`，和以前一樣 |
| `Hc/profile_runtime.py` | `ProfileRuntime(prepare_child=...)`：允許起子程式時、建 spec 之前 await；`ProfileManager(prepare_child=..., profile_removed=...)` 與 `removed(id)`；每個帳號的監看拿到 `profile_id`（只在開通時） |
| `Hc/profile_admin.py` | 刪帳號（含孤兒）與刪隔離目錄之後呼叫產品清理（`Registry.removed`） |
| `Hc/profiles.py` | `documentation_child(product, profile_id)` |
| `Hc/gateway.py` | 沒有子程式在跑、閘道自答 tools/call 時：沒後端而且這個帳號的子程式沒後端就不跑，每支工具都回 `backend_not_configured` |
| `Hc/health.py`、`Hc/configuration.py` | 「沒後端就是 unconfigured」改看 `documentation_child`（n8n 預設帳號照舊） |
| `packaging/container_profiles.py` | 多帳號階段收 n8n；`check_n8n_catalogs`（每個額外帳號自己的副本：0600、單一連結、目錄 0700、沒有共用） |
| `packaging/ha_p9_probe.py` | 只改註解（`CHILD_PORT_SCRIPT` 本來就讀命令列的 `--port`） |
| 測試 | 新 `tests/test_n8n_multi_profile.py`（28 案）；`packaging/test_ha_p9_probe.py`、`test_container_profiles.py` 補 n8n；`tests/multi_profile_runtime.py` 收 n8n（`SWITCHABLE` 加 n8n，所以 `test_router_passthrough.py`、`test_profile_routing.py`、`test_origin_policy.py` 的參數化案例也跑 n8n）；`tests/test_panel_profile_api_shapes.py`；其他檔只搬注入點（第 6 節） |
| 面板 | `packages/mcp-admin-ui/tests/profile-api-cases.json` 加情境與一條說明；`README.md` 一段。面板程式沒改 |
| 文件 | 契約（第 1.2、3.5、4.2、7、8、9、10 節）、`decisions.md`、`acceptance-matrix.md`、`threat-model.md`、`unreleased-changes.md`、`docs/operations/acceptance.md`、`clients.md`、`ha-p9-kit.md` |
| 帳本 | `runtime-patches.json` 8 個列管檔的摘要與說明（第 8 節）；`tests/test_output_schemas.py` 的兩個 n8n 檔摘要 |

沒改：`addons/`、版號、CHANGELOG、`features.py`、`apps/runtime/*.py`、`apps/*/launch.py`（所以 tool-surface 不用重產）、
`backend_policy.cjs`、`tests/conftest.py`、`tests/owned_runtime.py`、`tests/owned_child.py`、`tests/contract/*.json`。

## 3. 設計與理由（計畫沒寫死的細節）

### 3.1 為什麼讓 `run.py` 呼叫 `run_product.run`

- 計畫寫「`run.py` 收斂到 ProfileRuntime」。照抄一份 `run_product.run` 會讓之後改 runtime 的片要改兩處，所以改成同一個 runtime 加 adapter。
- `run_product` 不能 import `apps/n8n`（核心 package 不依賴 app），所以由 `run.py` 把 n8n 的東西交進去。
- 開關關時和以前比：同樣的 store、遷移、守門、還原提示、catalog 副本（同一個位置與訊息）、Supervisor、client（40 條）、健康監看、
  `make_apps` 的產品參數。差別只在用戶端看不到的地方：帳號 ETag 的 HMAC domain 帶 `default`（隨機金鑰，本來就不跨程序）；`make_apps`
  多拿到 runtime 建的 TokenAccess、鎖與 `stop_child`（沒開通不會用）；關閉順序是先關 client 再停子程式；`product_version` 傳
  `version_for_product('n8n')`（今天等於 `VERSION`）。黃金回歸與兩個契約凍結照過。
- 附帶修好一件：n8n 以前不傳 `product_version`，n8n 自己升版號時 `serverInfo` 會報預設版號（`unreleased-changes.md` 第 3.2 節原本要升版
  PR 先改 `run.py`）。現在照其他產品，所以黃金回歸對 n8n 也改讀 `version_for_product`（今天位元組相同）。

### 3.2 從目錄認帳號

- `ProfileRuntime` 只用 `child_spec(state, directory, port=...)` 呼叫 child spec；HM-04 的測試也用預設帳號的目錄配別的 port。
  所以「是不是額外帳號」看目錄：額外帳號的 store 一定在 `<data>/profiles/<24 hex>`（`profiles.Layout.profile`）。
- port 不拿來判斷：HM-04 的規則是「換 port 只改 port」，`tests/test_child_port_param.py` 照舊全過。
- 開關關時看到額外帳號的目錄就拒絕（`RuntimeError`）：關掉時不會有額外帳號的 runtime，這是多一道防線。

### 3.3 catalog 副本

- 位置照 DQ-04 的建議。PaaS 放在帳號設定目錄、進備份；HA 放 `/tmp`，和預設帳號今天的語意相同（管理程序重啟或容器重建就重做，
  版本歷史跟著清掉）。
- 做法照預設帳號的 `prepare_catalog`：每一層目錄都是這個 uid 的 0700、不是連結（每一層都 `lstat` 看）；檔 0600、寫完 fsync、原子換上。
- 時機：子程式第一次要起的時候（開機的錯開啟動、建立後存後端、面板重啟），由 `ProfileRuntime._relaunch` 在建 spec 之前 await，
  複製在工作執行緒（`asyncio.to_thread`）。錯開啟動同時最多 2 個帳號在起，所以同時最多 2 份在複製。沒後端不複製（不起子程式）。
- 做不成：記一行 WARNING（`n8n: profile <id 前 8 碼>: no catalog copy could be made; its child does not start`），spec 拒絕、子程式不起
  （`child_start_failed`）。PaaS 也是拒絕啟動。預設帳號照舊退回映像內的唯讀檔（沒改）。
- 刪除：`profile_admin` 在刪掉帳號目錄之後呼叫 `removed(id)`，n8n 的 `remove_profile_catalog` 從 `/tmp/woow-n8n-mcp` 開始不跟隨連結地刪
  （`O_NOFOLLOW` 開目錄、檢查擁有者與權限、`rmtree(dir_fd=...)`）。孤兒與隔離目錄刪除也叫（隔離目錄只在那個 id 沒在服務時）。

### 3.4 HOME 與 cwd（UC-01）

- 讀 n8n-mcp 2.96.2 的 dist：會寫 HOME 的只有遙測設定（`telemetry/config-manager.js` 寫 `~/.n8n-mcp/telemetry.json`）。
  每個路徑都先問 `isEnabled()`，而 `N8N_MCP_TELEMETRY_DISABLED=true` 時在讀設定檔之前就回 false。child spec 一律帶這個變數，
  環境是自己組的、不繼承。其他寫檔的地方（sql.js 存回 DB、`templates/batch-processor.js`、`node-documentation-service.js`）只有
  `scripts/` 會用到，或寫到 `NODE_DB_PATH`。用 `process.cwd()` 的地方都是讀（找 `data/nodes.db`、docs、`package.json`）。
- 真子程式驗證：`test_the_real_child_of_an_additional_profile_leaves_its_home_empty` 用額外帳號的真 spec 起 n8n-mcp，跑文件工具、
  `search_nodes`、對假後端的 `n8n_list_workflows`，停掉之後 `child/` 仍是空的。本機是 Node 22（原生 better-sqlite3 是 Node 26 的，退回
  sql.js），CI 是 Node 26 加原生模組。
- 所以照 Python 子程式的規則要求空目錄：每次起之前檢查。不是連結、不是一般檔、裡面沒東西。
- 另外注意：沒有 `NODE_DB_PATH` 時 n8n-mcp 先找 `<cwd>/data/nodes.db`。額外帳號的 cwd 必須是空目錄，而且一定有自己的副本，
  所以不會讀到 cwd 裡被放進去的檔。

### 3.5 沒後端的額外帳號（DQ-22）

- 子程式不起（spec 回 None，同 Python 產品）。省一個約 300 MiB 的子程式（`CHILD_MEMORY_MIB['n8n']`）。
- 閘道：沒有子程式時本來就自答 initialize、tools/list（照政策過濾的完整清單）；tools/call 以前是「需要後端的工具回 `backend_not_configured`，
  文件工具回 `MCP_SERVER_NOT_READY …; try again shortly`」。現在這個帳號的子程式沒後端就不跑時，每支工具都回 `backend_not_configured`。
  判斷用帳號回聲的 id（開通時才有回聲；沒開通就是預設帳號）。n8n 預設帳號與其他產品的回答都不變（其他產品的工具本來就全部需要後端）。
- 健康檢查與套用狀態：以前寫死 `product != 'n8n'`，改成 `documentation_child`，額外帳號沒後端就是 `unconfigured`。
- 政策先於後端判斷：格式錯、被停用、沒授權的工具照舊先回各自的拒絕（和其他產品一樣）；格式對的呼叫才回 `backend_not_configured`。

### 3.6 命令列的 `--port`

- HM-16 審查 SF-2：n8n 子程式的 port 只在環境變數，P9 kit 與容器探針認不出誰是誰；讀別人的 `/proc/<pid>/environ` 要 CAP_SYS_PTRACE。
- 額外帳號在入口後面加 `--port N`。n8n-mcp 2.96.2 只看 `argv[2] == 'telemetry'`（`telemetry/telemetry-cli.js`），其他參數不讀。
  命令列只有 port，沒有任何 token（`test_child_bearer.py` 的規則：token 不放 argv）。預設帳號的 argv 不變。

### 3.7 per-profile 政策隔離（T-07）

- n8n 的政策由閘道判斷，存政策**不重啟任何子程式**（`gateway.py` 只對 EMQX、LiteLLM、Nextcloud、Headscale 的政策重啟），只改那個帳號的回答。
  會重啟子程式的是後端、`backend/patch`、`n8n/session`，都只重啟那個帳號的子程式。測試兩種都驗。

## 4. 威脅說明（交獨立安全審查）

| 面向 | 本片的做法 | 剩下的風險 |
|---|---|---|
| webhook 打 loopback（配合 HM-20） | 照舊 `WEBHOOK_SECURITY_MODE=permissive`（契約 #90）；開通後設定的 n8n 後端（API 與官方 MCP 端點）拒 loopback（`WOOW_MCP_DENY_LOOPBACK=1`，每個帳號的子程式都有） | 任何帳號的 `n8n_test_workflow` 都能打 127.0.0.1。別帳號子程式（3000、18000 起）要那個帳號的 child bearer，子程式環境只有自己的；8081 要某個帳號的 token；8099 從 127.0.0.1 來不是 Ingress，一律 403。要不要收緊交審查 |
| HOME 與 cwd | 額外帳號 `profiles/<id>/child/`（0700、空、不是連結，每次起都查）；預設帳號照舊 `/data/mcp` | 同 uid 的子程式讀寫得到每個帳號的檔（DQ-37 已接受）；預設帳號的 cwd 是 `/data/mcp`（今天就是，C1-S4 定不搬） |
| catalog 副本 | 每帳號一份、目錄 0700、檔 0600、不跟隨連結、沒有自己的就不起 | 只讓 n8n-mcp 的版本歷史分開，不是安全邊界（同 uid）；`/tmp` 佔磁碟，每帳號約 67 MiB（最多 2 個額外帳號） |
| 標頭 | 只轉閘道自己的標頭與 3 個 session 標頭；`x-n8n-url`、`x-n8n-key`、`x-n8n-mcp-token`、`x-instance-id`、`x-session-id` 都不轉（開關開與關都測） | 無新增 |
| session | 每帳號自己的子程式與 20 個 session；一個帳號用完不影響別的帳號 | 一個帳號的 20 個仍可被它自己的持有人用完（HA 既有，429） |
| 子程式 bearer | n8n-mcp 驗 `AUTH_TOKEN`（每帳號自己的 child token）；契約 #37 的三種額外寫法照舊（都要先有自己的 token） | 無新增 |
| 命令列 | 額外帳號多 `--port N` | 只有 port，任何人都讀得到命令列本來就沒有秘密 |
| 沒後端的額外帳號 | 不起子程式 | 攻擊面變小（少一個可被打的程序） |

## 5. 先紅後綠

- 紅：寫好 `tests/test_n8n_multi_profile.py` 與 `tests/multi_profile_runtime.py` 的 n8n 支援之後，把 `apps/n8n` 與
  `packages/mcp-admin-core` 退回基準（`git stash`）跑：26 案裡 7 失敗、19 錯誤（`n8n_adapter` 沒有 `PACKAGED_CATALOG`、
  `prepare_profile_catalog`、`profile_of` 等；額外帳號仍起文件子程式；`run.py` 還是自己的 runtime）。
  `test_no_x_n8n_header_reaches_a_child` 兩案在基準其實成立（閘道本來就不轉），紅是因為測試夾具要的新名字還沒有；它是鎖住既有行為的測試。
- 綠：程式還原後 26 案全過。
- 之後補的 2 案（綠之後才寫，沒在基準跑）：`test_the_n8n_profile_count_follows_the_memory_limit` 對齊 PaaS
  `apps/n8n/tests/test_profile_capacity.py`（512 MiB 0 個、1 GiB 1 個、2 GiB 2 個額外帳號），常數本來就有，是鎖住既有行為的測試；
  `test_a_restore_revokes_every_n8n_profile_and_their_children_start_apart` 對齊 PaaS `test_restore_guard_n8n_integration`
  （還原後每個帳號的 token 都撤銷、子程式換新 child token，各自的 HOME 與 catalog 副本）。
- 改測試的過程（照實記）：DQ-22 那一案第一版用空參數呼叫每支工具，`n8n_manage_agents` 這類嚴格選擇器的工具先被政策拒絕
  （`Operation not permitted`），改成帶合法的讀取操作；健康狀態那一段要先跑一次監看（額外帳號的第一次監看錯開 15 秒以上）；真子程式那一案
  一開始檢查狀態太早（`starting`）。
- 面板：`profile-api-parity.spec.mjs` 用 fixture 跑新情境照錄的回答過（本機有 Playwright 的瀏覽器，見第 7 節）；
  `tests/test_panel_profile_api_shapes.py` 用真的 8099 app 跑過（新情境以前會在 `run_product` 的 `TOOLS['n8n']` KeyError）。

## 6. 開關關時逐位元不變

- HM-01 黃金回歸（`tests/test_single_profile_golden.py`）：期望值、常數、摘要都沒改。改的是注入點：n8n 的 runtime 是 run_product 的，
  所以 `Supervisor`、`httpx.AsyncClient` 改 patch 在 `profile_runtime`，`Listener`、`make_ha_admin_verifier` 改 patch 在 `run_product`
  （檔頭本來就寫「HM-05 may move these lines when the names they patch move」，本片照做並寫進檔頭）；n8n 的 `serverInfo.version` 改讀
  `version_for_product`（和其他產品同一條；今天值相同，位元組相同）。
- 兩個契約凍結、child spec 快照（`tests/contract/child_spec_default.json` 沒改）、`test_upgrade_zero_rewrite.py`（n8n 開關開時改用
  `multi_profile_runtime`，期望值不變）都照過。
- 其他只搬注入點的測試：`tests/owned_executable.py`（n8n 的 profile 也是 `profile_runtime`）、`test_role_lifecycle.py`、
  `test_product_runtime_failure.py`、`test_restore_lock.py`、`test_runtime_failure.py`、`test_owner_defaults.py`、`test_ha_role.py`。
  `test_secret_path.py`、`test_initialize_identity.py` 原本讀 `run.py` 的原始碼確認它自己開 listener、自己給 server name，改成確認
  `run.py` 交給 `run_product.run`（那兩件由 `run_product` 做，原本的檢查照樣對 `run_product.py` 做）。`test_unconfigured_connect.py`、
  `test_real_n8n.py` 的 n8n 版本改讀 `version_for_product`。`test_profile_runtime.py` 的「run_product 用 ProfileRuntime 建預設帳號」加 n8n。

## 7. 本機檢查（一般使用者 uid 1000；短 TMPDIR `/tmp/ha-mp-…`，跑完刪掉；pytest 排在共用鎖後面）

最後一輪（2026-11-19；程式與測試＝`dcf8bbe`，之後只加本筆記）：

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（`ha-gh-release-20261117` 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv；`discover -s packaging -p 'test_*.py'`） | `Ran 369`、`OK (skipped=5)`（5 個 `skipUnless(root)`），27.3 秒 |
| node（`node --test packages/mcp-admin-ui/tests/*.test.mjs`） | 118 過、0 失敗 |
| Playwright（`profile-api-parity.spec.mjs`、`backend-identity.spec.mjs`，`--project=single`） | 36 過（含新情境 `new-origin-unset-secret`）；其他 spec 以 CI 為準 |
| pytest 改到的面 43 檔（新測試檔、HM-01 黃金回歸、兩個契約凍結、零改寫、搬注入點的檔、多帳號 runtime 與面板的檔） | 1964 案：1962 過、2 失敗（第 7.1 節），356 秒 |
| pytest 其餘 146 檔 | 4136 案：4129 過、7 失敗（第 7.1 節），1904 秒 |
| pytest 合計（兩輪合起來就是 `tests/test_*.py` 全部 189 檔） | **6100 案：6091 過、9 失敗、0 skip**。9 個失敗都是本機跑不了的既有案例（第 7.1 節），沒有本片造成的失敗 |
| `scripts/secret_precheck.py --tools <scan0414/tools>` | `result: OK, 0 findings`（gitleaks 8.28.0；`c90b214..dcf8bbe` 7 個 commit） |
| `scripts/ledger_precheck.py` | `result: OK`：三本帳 0 漂移；改到的 8 個列管檔都在本分支更新了；`health.py` 列成「沒列管、要人看」（第 8 節） |

### 7.1 本機跑不了、只在 CI 驗的

- Node 26 的原生 better-sqlite3（2 案）：本機 Node 22（ABI 127）載不到 ABI 147 的模組，n8n-mcp 退回 sql.js（沒有 FTS5）。
  `tests/test_n8n_catalog_copy.py::test_version_history_is_written_natively_on_the_copy_of_a_database_the_child_cannot_write`
  在基準也失敗；`tests/test_boundary.py::test_the_n8n_child_loads_the_one_pinned_native_addon_and_n8n_mcp_uses_it` 用的是預設帳號的
  spec（本片沒改，快照照過），在本機直接 `require('better-sqlite3')` 就報 `NODE_MODULE_VERSION 147`。CI 是 Node 26。
- 要 root（7 案；CI 以 root 跑 pytest）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`tests/test_restore_detection.py` 的 5 個 `test_root_*`。
  packaging 的 5 個 `skipUnless(root)` 也是。
- Playwright：CI 跑全部；本機只跑了上表那兩個 spec。
- 實際容器（n8n 的多帳號階段、`check_n8n_catalogs`）不在 CI：交 n8n 升版前的 builder 乾跑（第 9 節）。

## 8. 帳本與工具面

- `docs/provenance/runtime-patches.json`：照 `ledger-tracking.md` 逐筆更新 8 個列管檔的 `sha256` 並在 `change` 補 HM-25 的說明：
  `apps/n8n/run.py`、`apps/n8n/n8n_adapter.py`、`run_product.py`、`profile_runtime.py`、`profile_admin.py`、`gateway.py`、`configuration.py`、
  `profiles.py`。`health.py` 照 `docs/multi-profile/ledger-tracking.md` 第 3 節維持不列管（帳本預檢照預期把它列成「沒列管、要人看」；
  審查要求列管時再加）。沒有新模組。
- `tests/test_output_schemas.py` 的 `CURRENT_POST_SOURCE_BYTES` 釘了 `apps/n8n/run.py` 與 `n8n_adapter.py` 的摘要，照它的規則更新並寫明
  「沒有工具、schema 或 handler 的改變」。
- tool-surface：沒改 `apps/runtime/*.py`、`apps/*/launch.py`，`docs/tool-surface.*` 不用重產（它釘的 n8n 檔是 n8n-mcp 的 dist 與
  `backend_policy.cjs`，都沒動）。

## 9. 之後的 HAOS 實機驗收要什麼（n8n 升版 PR；要使用者批准）

- **後端身分**（建立與刪除都要使用者批准）：兩個 n8n 帳號要用的兩組 n8n API key。建議同一台 n8n 的兩個受限使用者（各自的 API key），
  或兩台 n8n；要驗官方 MCP 端點時再各加一把 instance-level MCP access token。預設帳號用既有的那一組。
- **T 列**：T-22（n8n 名額與逾時：兩帳號各自 20 個 session、存 session 只重啟該帳號；沒後端的額外帳號每支工具 `backend_not_configured`）、
  T-04（N×N：各帳號建一個標記 workflow，只在對角線看得到）、T-05（P9 `--cross`）、T-07、T-09（刪帳號後舊 token 失效、`/tmp` 副本也刪掉）、
  T-13（P9 `childkill --child-port` 打 n8n 的額外帳號）、T-14、T-17（三個 n8n 子程式的記憶體，`CHILD_MEMORY_MIB` 是 300 MiB）、
  T-21（還原後重做副本）、T-23、T-29（合成憑證掃描與清理）。
- **UC-09 真機確認**：兩個帳號各自更新同一個 id 的 workflow，`n8n_workflow_versions` 只看得到自己的。
- **面板情境重錄**：`profile-api-cases.json` 的 `new-origin-unset-secret`（標了 `rerecord_on_real_backend`）在真後端重錄，回應不同就改情境與 fixture。
- **容器驗收**：n8n 的候選映像（開通的 flag-on 乾跑）跑多帳號階段，含 `check_n8n_catalogs`。

## 10. 交給後面的片、還沒解決的事

- `deviation-trace.md` 由 repo 外的產生器重產，本片沒改。下次文件同步時產生器要補：FM-15 → #47、#129 與 `tests/test_n8n_multi_profile.py`；
  FM-84 → #62 與同一個測試；FM-140 → #28、#130 與同一個測試；文末「差異表每一列的來處」加 #129～#131（HM-25）。
- `paas-test-mapping.md` 也是產生器寫的（檔頭寫明不要手改表格），本片沒改。它有 4 列寫 `tests/test_n8n_multi_profile.py`（HM-25，暫定名），
  `deviation-trace.md` 的 T-22 列也是；檔名已定，下次重產時拿掉「暫定名」。這 4 列對到的案例：
  - 刪帳號一起刪副本：`test_each_profile_runs_on_its_own_catalog_and_its_copy_goes_with_it`
  - 每帳號的 child bearer：`test_every_profile_reaches_only_its_own_child`
  - 兩個 n8n 帳號的還原：`test_a_restore_revokes_every_n8n_profile_and_their_children_start_apart`
  - 名額跟記憶體：`test_the_n8n_profile_count_follows_the_memory_limit`
- 契約第 9 節第 129～131 列號暫定（其他產品的開通片同時在準備）。
- n8n 升版 PR 要寫的 CHANGELOG 與 DOCS（`addons/n8n/DOCS.md` 的「共用 20 個」改每帳號、沒後端的額外帳號）列在
  `unreleased-changes.md` 第 3.2 節。
- webhook 模式要不要收緊：交本片之後的獨立安全審查（第 4 節）。
- 給 PaaS 的回補建議（HM-29）：PaaS 沒後端的 n8n 額外帳號起文件模式子程式、會轉送 `x-n8n-*`；HA 都不做。

## 11. 要使用者決定的事

- **DQ-04**（n8n `nodes.db` 放哪）：本片照計畫建議做成每帳號 `/tmp/woow-n8n-mcp/profiles/<id>/`、不進備份、預設路徑不變。選別的做法
  （例如照 PaaS 放帳號目錄、進備份）時回功能 PR 改。
- **DQ-22**（n8n 額外帳號細節）：本片照計畫建議做成沒後端不起子程式、所有工具回 `backend_not_configured`、逾時與限流維持 HA 現值。
- 兩題最晚都要在 n8n 的升版 PR 合併前定（`decisions.md` 已改）。

## 12. commit（`c90b214` 之後；都沒 push，push 由之後的收尾步驟做）

| commit | 內容 |
|---|---|
| `5237ad1` | 測試先寫（先紅：26 案 7 失敗、19 錯誤）：`tests/test_n8n_multi_profile.py`；`tests/multi_profile_runtime.py` 收 n8n |
| `ed86fcd` | 功能：`run.py` 改走 `run_product`（`ProductAdapter`）；額外帳號的子程式 spec、catalog 副本、DQ-22（閘道、健康、套用狀態）、刪帳號的清理；只搬注入點的測試 |
| `61ba44e` | P9 kit 與容器探針認得 n8n 的子程式（`--port`、`check_n8n_catalogs`）與測試；`ha-p9-kit.md` |
| `57766d5` | 面板：情境 `new-origin-unset-secret`、形狀比對用 n8n 的已存連線、log 掃描看 n8n 的 key；面板 `README.md` |
| `1adcfd0` | 文件：契約（第 1.2、3.5、4.2、7、8、9、10 節，新列 129～131）、`decisions.md`、驗收矩陣、威脅模型、`unreleased-changes.md`、`acceptance.md`、`clients.md` |
| `6ac1b0f` | 帳本：8 個列管檔的摘要與說明；`tests/test_output_schemas.py` 的兩個 n8n 摘要 |
| `dcf8bbe` | 對齊 PaaS 的 2 案（名額跟記憶體上限、還原撤銷每個帳號）；驗收矩陣的測試檔登記列 |
| （本 commit） | 本筆記（獨立審查的對象） |

`ed86fcd` 單獨看時 `tests/test_output_schemas.py` 的兩個摘要還沒更新（`6ac1b0f` 才更新）；以分支 head 為準。
