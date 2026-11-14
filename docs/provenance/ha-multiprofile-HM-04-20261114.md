# HA 多帳號 HM-04 provenance：子程式 port 參數化（行為不變）（2026-11-14）

## 結論

- 子程式的 loopback port 從寫死的 3000 改成參數，預設仍是 3000。唯一來源是 `lifecycle.CHILD_PORT` 與
  `lifecycle.child_url()`：spec 的 argv（或 n8n 的 `PORT`）、健康檢查、閘道轉送、能力探測都從同一個值組出。
- 單帳號（預設帳號）行為不變：九個產品、16 種狀態的子程式 argv、env（含順序）、cwd 和 `bb48449` 逐位元相同
  （快照 `tests/contract/child_spec_default.json`）。HM-01 的黃金回歸、兩個契約凍結與它的替身一個字都沒改，照過。
- 給別的 port（多帳號計畫的額外帳號，18000 起）時只差 port：`--port` 的值、n8n 的 `PORT`；Hermes、OpenDesign 在尾端加
  `--port N`，launcher 讀它。`run_product.run`、`apps/n8n/run.py` 給 `child_port=18000` 時，子程式收到的每個請求都打
  `http://127.0.0.1:18000/mcp`，客戶端拿到的回覆和黃金回歸相同。
- 新測試 1 檔 163 案（另有快照 1 檔）。先紅後綠：改程式前 39 通過、124 失敗；改完 163 全過、0 skip。
  18 個臨時突變，18 個都讓新測試失敗（第 4.3 節）。
- 兩個預檢：秘密預檢對本片 3 個 commit 0 命中（全分支 12 個 commit 與建置機同款的 `--full` 也 0）；帳本預檢 OK（0 漂移）。
- 本機全套 pytest：3895 案，3872 通過、23 失敗、0 skip。22 個失敗是這個 clone 沒裝 Playwright 的 Chromium
  （`browserType.launch` 找不到執行檔），照 CI 的 `unit.sh` 補跑 `npm run browser:install` 後，那 3 個檔 52 案重跑全過；
  剩下 1 個是已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-04（計畫 §5.4、§12.3；風險中、工作量 M）。不受開關管（契約 §1.2；計畫 §3.3 的保證方式是「快照」） |
| 分支 | `feat/ha-multiprofile-hm04-20261114`（只 commit；還沒 push、沒開 PR） |
| 基準 | `32ecac8`＝`bb48449`＋HM-01（PR #90 等合併）。`packages/`、`apps/`、`packaging/`、`addons/`、`.github/` 和 `bb48449` 相同 |
| 依據 | 計畫 §4.1、§5.4、§12.0、§12.2 衝突表、§12.3 HM-04；HM-00 契約 §1.2、§7（預設 3000、額外帳號 18000 起）、§8.8 #52；`ledger-tracking.md`；`acceptance-matrix.md`（`tests/test_child_port_param.py` 一列） |
| 對齊的 PaaS | 本片沒有移植 PaaS 程式或測試，只把 PaaS 額外帳號 port 的起點（`Pc/profiles.py` 的 `FIRST_PROFILE_PORT = 18000`，FM-38）當測試值。HM-00 `paas-test-mapping.md` 指給本片兩案：`test_uvicorn_command_line_port`（不適用：HA 的 port 由 `child_spec` 組出，對應本片 `test_another_port_changes_the_port_only`）、`test_registry_reloads_saved_profiles_and_child_env_uses_their_files`（port 的部分在本片，其餘在 HM-05） |
| FM | FM-38、FM-86（Hermes launcher 寫死 3000 的部分）、FM-96 |
| 決策 | 只用到 §13.1 已採用的做法；沒有碰到待定題（DQ-09、DQ-12、DQ-19、DQ-38 等都沒用到） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `Hc/lifecycle.py` | `CHILD_PORT = 3000`、`child_port_text(port)`（只收 1～65535 的 `int`；`bool`、字串、浮點數、`None` 都 `ValueError`）、`child_url(port=CHILD_PORT)`、`CHILD_URL`。 |
| `Hc/products.py` | `child_spec(state, directory, port=CHILD_PORT)`：先驗 port（沒設定後端也驗），四處 argv 的 `--port` 用它。Hermes、OpenDesign 只在不是 3000 時加 `--port N`，預設 argv 不變。 |
| `H:apps/n8n/n8n_adapter.py` | `child_spec(state, directory, port=CHILD_PORT)`：`PORT` 用它（位置不變）；`CHILD_URL = child_url()`（同一個值）。 |
| `H:apps/hermes/launch.py`、`H:apps/opendesign/launch.py` | 讀 `--port N`（argparse `parse_known_args`，不加 `-h`）：沒給是 3000；位置參數照舊忽略；不認得的選項、範圍外或不是數字的 port 在 `session_idle.install()` 之前結束（exit 2）。 |
| `Hc/run_product.py`、`H:apps/n8n/run.py` | `run(args, *, child_port=CHILD_PORT)`：spec、`HealthMonitor`、`make_apps`（閘道與能力探測）的 `child_url` 都從它組出。`main()` 不加 CLI 選項；「監聽 port 不能用 3000」的檢查與訊息逐字不變。計畫寫的 `run.py` 就是 `apps/n8n/run.py`（repo 根目錄沒有 `run.py`）。 |
| `Hc/health.py`、`Hc/gateway.py` | `HealthMonitor`、`make_apps` 的預設 `child_url` 改用 `lifecycle.CHILD_URL`（同一個 `http://127.0.0.1:3000/mcp`）。 |
| `tests/test_child_port_param.py`、`tests/contract/child_spec_default.json` | 新測試與快照（第 4 節）。 |
| `tests/owned_executable.py` | 替身原本斷言 `make_apps` 不收 `child_url`。現在正式程式一律傳，替身改成「只接受正式網址（`http://127.0.0.1:<production_port>/mcp`），再換成私有 endpoint 的」，和 `private_spec` 只換正式 port 同一個原則；沒傳時照舊（`test_owned_executable.py` 的直接呼叫）。 |
| `tests/test_role_lifecycle.py`、`tests/test_product_ha_role.py`、`tests/test_product_runtime_failure.py`、`tests/integration_runtime_wrapper.py` | 這些替身的簽名寫死（`child_spec(state, directory)`、`Monitor.__init__(self, *args)`），改成也收 `port`、`child_url`；測試內容沒改。 |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES` 補 `apps/n8n/n8n_adapter.py`、`apps/n8n/run.py`、`apps/hermes/launch.py` 的現行摘要（`output_schemas.json` 記的是 schema 審查當時的位元組；工具、schema、handler 都沒變）。 |
| `docs/provenance/runtime-patches.json` | 7 筆的 `sha256` 與 `change`：`products.py`、`gateway.py`、`run_product.py`、`n8n_adapter.py`、`n8n/run.py`、`hermes/launch.py`、`opendesign/launch.py`。 |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只變兩個 launcher 的摘要；`docs/tool-surface.md` 沒變。 |
| `docs/provenance/ha-multiprofile-HM-04-20261114.md` | 本筆記 |

沒改：版號、`addons/<x>/`、CHANGELOG、`upgrade-notes.yaml`、`packaging/`、workflow、`tests/conftest.py`、UI；HM-01 的守門檔
（`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、`tests/contract/profiles_v1_cases.json`、
`log_scan.py`、`owned_runtime.py`、`owned_child.py`、`owned_network.py`、`owned_network.cjs`、`batch2_owned_port.py`、兩個預檢腳本與它們的
測試）一個字都沒改（`git diff 32ecac8 HEAD` 對這些檔是空的）。

`health.py`、`lifecycle.py` 不進帳本：照 HM-00 `ledger-tracking.md` 第 3 節維持不列管。帳本預檢把它們列為「沒列管、要人看」，
不算失敗；審查要求列管時再加。

## 3. 設計理由

- **唯一來源放 `lifecycle.py`**：`products.py`、`n8n_adapter.py` 本來就從它 import `ChildSpec`；`gateway.py` 經 `capabilities.py` 已經載入它；
  `health.py` 多 import 一個名字（`lifecycle.py` 不 import `health.py`）。沒有新的相依方向，也沒有循環。計畫列的檔沒有
  `lifecycle.py`，照「以實際原始碼為準」加上。
- **Hermes、OpenDesign 的預設 argv 不加 `--port`**：驗收要求單帳號 argv 和 `bb48449` 位元相同，launcher 的預設就是 3000。
  HM-01 的 `owned_runtime.private_spec` 也是這樣設計（預設 argv 完全不變，別的 port 才帶 `--production-port`）。
- **launcher 用 `parse_known_args`**：`bb48449` 的兩支 launcher 完全不看參數；既有兩個測試的包裝（`test_resolver_regressions.py` 的
  DNS 包裝、`test_stream_error_redaction.py` 的 late-fault 包裝）會在 `sys.argv` 留自己的位置參數。不認得的選項一律拒絕，
  打錯字的 `--port` 不會悄悄落回 3000（那是預設帳號的 port）。
- **`run()` 用 keyword-only 參數、不加 CLI 選項**：CLI 只管部署欄位（`run_product.py` 檔頭），子程式 port 不是部署選項；
  HM-05 的每帳號執行套件會傳每個帳號自己的 port。
- **監聽 port 檢查仍只看 3000**：行為不變。額外帳號配 port、避開 8081／8099、spawn 前檢查是 HM-09（計畫 §5.4、契約 §7）。
- **port 先驗、再看有沒有設定後端**：錯的 port 是呼叫端的錯，不管狀態都拒絕。
- **快照的寫法**：env 存成依序的 `NAME=value`，順序也比（`ChildSpec` 的相等只把 env 當 dict 比）；路徑（checkout、資料目錄、
  n8n 型錄複本、node）與 child token 用佔位字，其他照字面。測試資料用 `DUMMY-port-…` 與 `.invalid`（計畫 §12.0 第 4 點）。

## 4. 新測試、先紅後綠、突變

### 4.1 新測試

`tests/test_child_port_param.py`（全部用 HM-01 的 `log_scan`；另有 autouse 檢查：測試期間 `owned_network` 的拒絕計數不能增加，
也就是沒有任何操作碰到 3000 或 18000～18099）：

| 測試 | 案數 | 內容 |
|---|---|---|
| `test_the_snapshot_covers_every_product` | 1 | 快照涵蓋九個產品（`products.PRODUCTS`＋n8n）的 16 種狀態 |
| `test_the_default_child_spec_is_bb48449s` | 16 | 預設 port 的 argv、env（含順序）、cwd 和快照逐位元相同；失敗訊息印出目前的（已正規化）spec |
| `test_port_3000_is_the_default_spec` | 16 | 明確給 3000（關鍵字與位置參數）是同一份 spec |
| `test_another_port_changes_the_port_only` | 48 | 18000、18042、18099：只差 port；HM-01 的 `Endpoint(production_port=N)` 照收，期望 3000 的 `private_spec` 拒收 |
| `test_an_unconfigured_product_has_no_child_on_any_port` | 8 | 沒設定後端：任何 port 都是 `None`，不建 `child/` |
| `test_a_port_that_is_no_tcp_port_is_refused` | 8 | 0、65536、-1、`True`、`False`、`None`、`'18000'`、`18000.0`：`ValueError`（含沒設定後端的狀態與 `child_url`） |
| `test_one_value_names_the_default_child` | 1 | `CHILD_PORT`、`CHILD_URL` 與各處預設值是同一個值；`run()` 的 `child_port` 是 keyword-only |
| `test_the_launcher_runs_on_its_port` | 16 | 兩支 launcher（換掉 SDK 模組、照子程式的方式以 `__main__` 執行）：`run()` 拿到的 port；位置參數照舊忽略 |
| `test_the_launcher_refuses_a_bad_port_or_option` | 22 | 0、65536、-1、`x`、缺值、`--port=`、`--prot`、縮寫 `--p`、多帶 `--host`、`-h`、`--help`：exit 2，什麼都沒做 |
| `test_the_real_launcher_serves_the_port_its_spec_names` | 4 | 真的 Hermes、OpenDesign 子程式，正式 port 3000 與 18000（`owned_child` 核對 launcher 傳給 `run()` 的 port，再換成私有 port） |
| `test_one_port_reaches_every_child_request` | 16 | 八個上架產品的正式 runtime（黃金回歸的注入點），預設與 `child_port=18000`：子程式收到的請求（健康檢查、能力探測、客戶端）都打同一個網址；客戶端整段 session 照黃金回歸；Supervisor 拿到的 spec 是預設的或只差 port |
| `test_the_listeners_still_refuse_the_default_child_port` | 6 | 兩個 `main()`：監聽 port 用 3000 或兩個相同時，錯誤訊息逐字不變 |
| `test_the_default_child_port_is_outside_the_profile_child_ports` | 1 | 測試用的 port 都在 HM-01 擋的範圍內 |

快照的產生方式：在 runtime 檔等於 `bb48449` 的樹上，用測試檔自己的 `case_state()`、`normalized()` 對 16 種狀態各產生一次寫進 JSON
（產生腳本在暫存區，沒有 commit）。證據是下一節：在只加測試、runtime 等於 `bb48449` 的 commit 上，快照比對 16 案全過；
改程式之後同一份快照照過。

### 4.2 先紅後綠

在 `fcd1b3a`（只加測試、還沒改程式；`git diff bb48449 fcd1b3a -- packages apps` 是空的）與改完的 `bd5fc7c` 各跑一次
`tests/test_child_port_param.py`（2026-11-15 重跑，結果和 11-14 第一次相同）：

| 測試 | `fcd1b3a`（改程式前） | `bd5fc7c`（改完） |
|---|---|---|
| 快照涵蓋、快照比對（17 案） | 17 通過（快照就是 `bb48449` 的 spec） | 17 通過 |
| 監聽 port 的錯誤訊息（6 案） | 6 通過 | 6 通過 |
| `test_the_launcher_runs_on_its_port`（16 案） | 8 通過（預設 port：沒給參數、`--port 3000`、只有位置參數）、8 失敗（給了別的 port） | 16 通過 |
| `test_one_port_reaches_every_child_request`（16 案） | 8 通過（預設）、8 失敗（`child_port=18000`） | 16 通過 |
| 其他 8 個測試（`port` 參數、`ValueError`、launcher 拒收、真子程式、常數；108 案） | 108 失敗 | 108 通過 |
| 合計 | 39 通過、124 失敗 | 163 通過、0 skip |

### 4.3 突變（暫時改一處、跑新測試、`git checkout` 還原，沒有 commit）

18 個突變都讓新測試失敗（每次跑 163 案）。M1～M13 在 2026-11-14 對同一個 commit 跑過一次，M14～M18 是這次補的；2026-11-15 在全套測試鎖裡全部重跑。
同一時間別的 worktree 在跑 pytest 時，`tests/conftest.py` 的本機測試鎖（`/tmp/woow-ha-mcp-local-tests-<uid>.lock`）等 120 秒就讓整個 session 失敗；
突變一律先等那把鎖空出來再跑，只算真正跑完的結果（這次 18 個都一次跑完）。

| 突變 | 失敗 | 擋下它的測試 |
|---|---|---|
| M1 Hermes、OpenDesign 的 argv 一律加 `--port`（3000 也加） | 16 | 快照 3、只差 port 9、真子程式 2、runtime 2 |
| M2 n8n 的 `PORT` 不理參數（固定 `"3000"`） | 7 | 只差 port 6、runtime 1 |
| M3 `run_product`：`HealthMonitor` 用預設網址 | 7 | runtime 7 |
| M4 `run_product`：`make_apps` 用預設 `child_url` | 7 | runtime 7 |
| M5 `run_product`：spec 用預設 port | 7 | runtime 7 |
| M6 `apps/n8n/run.py`：`make_apps` 用預設 `child_url` | 1 | runtime 1 |
| M7 Hermes launcher 不理 `--port` | 5 | launcher 的 port 4、真子程式 1 |
| M8 OpenDesign launcher 接受不認得的選項 | 5 | launcher 拒收 5 |
| M9 `child_port_text` 接受 `bool`、字串、浮點數 | 4 | 拒收錯的 port 4 |
| M10 Python 子程式 env 的順序對調兩個鍵（鍵與值都相同） | 14 | 快照 14 |
| M11 只在設定了後端時才驗 port | 8 | 拒收錯的 port 8 |
| M12 閘道的預設 child URL 換成別的 port | 1 | 唯一來源 1 |
| M13 `apps/n8n/run.py`：spec 用預設 port | 1 | runtime 1 |
| M14 EMQX、LiteLLM、Nextcloud（`run_child`）的 `--port` 固定 3000 | 21 | 只差 port 18、runtime 3 |
| M15 Odoo 的 `--port` 固定 3000 | 7 | 只差 port 6、runtime 1 |
| M16 Hermes launcher 接受不認得的選項 | 5 | launcher 拒收 5 |
| M17 健康監看的預設 child URL 換成別的 port | 1 | 唯一來源 1 |
| M18 OpenDesign launcher 不理 `--port` | 5 | launcher 的 port 4、真子程式 1 |

M12、M17 只有一案失敗：兩個 runtime 都明確傳 `child_url`，預設值只剩直接呼叫的地方用，由 `test_one_value_names_the_default_child` 釘成 `CHILD_URL`。M6、M13 只影響 n8n 給 18000 的那一案。

## 5. 本機檢查（2026-11-15，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

環境：2026-11-14 21:51 照 `packaging/unit.sh` 的安裝步驟裝好（uv sync 根目錄與 8 個子程式、Odoo／n8n patch、n8n 與 UI 的 `npm ci`、
UI build）；當時沒跑 `npm run browser:install`，2026-11-15 全套跑完後補裝（見下表）。全套 pytest 與突變在多個 clone 共用的
全套測試鎖裡跑，開跑前先等 `tests/conftest.py` 的本機測試鎖空出來。

| 檢查 | 結果 |
|---|---|
| 新測試（junit；`packaging/check_results.py` PASS：163 executed, no skips） | 163 通過、0 skip；pytest 報 9.4 秒（真子程式 4 案 7.0 秒、runtime 16 案 1.2 秒，其他合計約 0.5 秒） |
| 全套 pytest（`tests/`） | 3895 案（HM-01 的 3732＋本片 163）：3872 通過、23 失敗、0 skip，28 分 13 秒。失敗的是：(1) 22 個瀏覽器測試（`test_owned_browser_ipc.py` 5、`test_owned_browser_redirect.py` 16、`test_owned_ui.py` 1），都在 `browserType.launch` 找不到 Chromium：本機環境沒跑 CI `unit.sh` 的 `npm run browser:install`。裝好（Playwright 1.61.1 的 chromium-headless-shell v1228）後這 3 個檔重跑：52 通過、0 skip、`check_results.py` PASS。(2) 已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof` |
| HM-01 的黃金回歸與契約凍結（全套裡） | 黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19、替身 52（`test_owned_ports_bearer.py`）、log 掃描 13、兩個預檢工具的測試 14＋7：131 案全過 |
| 18 個臨時突變 | 第 4.3 節 |
| `packaging/validate.py`（PyYAML 的 Python） | PASS |
| packaging unittest | `Ran 184`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `scripts/tool_inventory.py`（漂移檢查，CI 同款） | 通過 |
| UI `npm test`、`build-closure.mjs` | 58 pass；PASS |
| Playwright（`npm run test:browser`，裝好 Chromium 後） | 71 passed（2.5 分）；本片沒改 UI，只是把 CI 的 `checks` 步驟補齊 |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨；`git diff 32ecac8 HEAD -- addons packaging .github CHANGELOG.md upgrade-notes.yaml` 空白 |

## 6. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。CI 以 root 跑 pytest；新測試不看執行身分（暫存目錄、資料目錄、
  子程式都由同一個身分建立），快照的路徑與 node 都是佔位字（CI 的 node 是 `/usr/local/bin/node`），預期 root 下結果相同。
- 既有、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root 切到 uid 10001）。
  它經 `tests/owned_uid_probe.py` 用 `Endpoint(port=...)`，不經本片改的 `install_runner`；`install_runner` 的兩條路徑在本機跑過：
  沒傳 `child_url` 的 `test_callback_is_not_serialized_behind_health`，與傳正式 `child_url` 的整合測試（`test_real_products.py`、
  `test_real_n8n.py`、`test_unconfigured_connect.py`、`test_runtime_failure.py`、`test_ha_role.py` 經 `Executable`）。
- `tests/integration_runtime_wrapper.py`（本片改了替身簽名）：只有本機 root 明確執行的 `tests/integration_local_runtime.py` 用它，
  CI 與一般 collection 都不跑（`docs/operations/acceptance.md`）；本片沒跑（要 root）。改法只是把 `port` 原樣傳給真的 `child_spec`。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。

## 7. `checks` 秒數

- 前：`bb48449` 的 push run 43222889894 `checks` 1380 秒、同一個 commit 的 pull_request run 43222899526 1834 秒（HM-01 筆記第 7 節）；
  HM-01 的 PR #90（run 43587407864）1434 秒。
- 後：開 PR 後補。
- 推估：新測試本機約 9 秒（4 個真子程式＋16 個 runtime），推估 CI 增加不到 30 秒。

## 8. 預檢結果

指令同 HM-01 筆記第 8 節（`--tools` 指到暫存區裝好的 gitleaks）。gitleaks 是 `secret_precheck.py install` 裝的釘選版：安裝時核對
壓縮檔 SHA-256 與 `packaging/scanner-pins.json`，每次掃描前再核對執行檔摘要與版本（輸出 `gitleaks 8.28.0 (pinned, verified)`）。

- **秘密預檢**（gitleaks 8.28.0；設定是本 repo 的 `gitleaks_config()`）：

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`32ecac8..HEAD`，git 模式） | 0（3 個 commit，含本筆記） |
  | 本分支的 commit（`bb48449..HEAD`，含 HM-01 的 9 個） | 0（12 個 commit） |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

- **帳本預檢**（`scripts/ledger_precheck.py`）：`runtime-patches.json` 152 個路徑、`runtime-sources.json` 70 個、`tool-surface.json`
  159 個，都 0 漂移、0 缺檔。對 `origin/claude-delivery`（`bb48449`）改了 37 個檔（含 HM-01 的 17 個）：列管檔 7 個
  （第 2 節）、帳本 2 個（`runtime-patches.json`、`tool-surface.json`）一起改；新增而沒列管的執行期檔 0 個；改到而沒列管的
  `health.py`、`lifecycle.py` 列為要人看（第 2 節）。結果 OK。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

不適用：本片沒有移植 PaaS 程式或測試，只用了 PaaS 額外帳號 port 的起點（18000）當測試值。這一波規定不連遠端，沒有在 PaaS repo
跑 `git log`。

## 10. 驗收條件（計畫 §12.3 HM-04）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR 的 CI（這一波不 push）。本機：新測試 0 skip、`check_results.py` PASS；全套只有已知要 root 的 1 個失敗 |
| 單帳號子程式 argv／env 與 `bb48449` 位元相同 | 通過：16 種狀態的快照在 `bb48449` 的 runtime 上產生、在 `fcd1b3a` 與 `bd5fc7c` 都全過（含 env 順序）；runtime 測試核對 Supervisor 拿到的就是預設 spec。HM-06 加 env 時同 PR 重定快照（C4-SF-4） |
| HM-01 照過 | 通過：黃金回歸、兩個契約凍結、替身都沒改，全套裡 HM-01 的 131 案全過（第 5 節） |
| 給 18000 時 argv、env、健康檢查、child_url 各處一致 | 通過：`test_another_port_changes_the_port_only`、`test_one_port_reaches_every_child_request` |
| 照 HM-01 `owned_network` 擋 3000 與 18000～18099 | 通過：autouse 檢查拒絕計數不變；真子程式一律在私有 port |
| 先寫測試、先紅後綠 | 通過（第 4.2 節） |
| 新測試沒有條件式 skip、用 log 掃描 | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail`；`pytestmark` 用 `log_scan` |
| 同 PR 更新帳本、重產 tool-surface | 通過：帳本 7 筆；tool-surface 重產；`tool_inventory.py` 漂移檢查通過 |
| `ledger_precheck` OK | 通過（第 8 節） |
| `secret_precheck` 對本片 commit 0 命中 | 通過：本片 3 個 commit 0 命中（第 8 節） |
| 不改版號、不碰 `addons/<x>/`、CHANGELOG | 通過 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：憑證 `DUMMY-port-…`、網址 `.invalid`、token 執行時產生（快照用佔位字）；新增的 64 hex 只有帳本與 `test_output_schemas.py` 的檔案摘要；秘密預檢 0 命中 |

## 11. 還沒解決、交給後面的片

- `checks` 的「後」秒數：PR 的 CI 跑完後補。
- **HM-06**：`child_spec` 加 `WOOW_MCP_CHILD_TOKEN` 後，`test_the_default_child_spec_is_bb48449s` 的 Python 產品案例會失敗；同 PR 更新
  `tests/contract/child_spec_default.json`（child token 已經是 `{child_token}` 佔位字，失敗訊息印出目前的 spec；只該多那一個 env）。
  `products.py` 的衝突：本片改 `child_spec` 的簽名、四處 `--port`、Hermes／OpenDesign 的 argv；HM-06 改 env。照 §12.2 順序 HM-04 先合，
  HM-06 rebase 後重產帳本與 tool-surface、重跑 CI。
- **HM-05**：`run()` 的 `child_port` 給每帳號執行套件用；抽出執行套件時，`owned_executable`、`test_role_lifecycle`、`test_product_ha_role`、
  `test_product_runtime_failure` 的替身注入點跟著搬（替身已經收 `port`／`child_url`）。本片的 `test_one_port_reaches_every_child_request`
  用黃金回歸的 `production_runtime`，注入點搬了它跟著動。
- **HM-09**：配 port（18000 起、避開 3000／8081／8099 與在用的 port）、spawn 前檢查都還沒做。`run(args, child_port=N)` 不擋 N 和
  監聽 port 相同（`main()` 只擋 3000，而且 `main()` 不傳 `child_port`）；交給 HM-09 的 spawn 前檢查（契約 §7）。
- 兩支 launcher 的 `--port` 解析各寫一份（和 Headscale 的 launcher 一樣自帶）；要共用得在 `apps/runtime/` 新增模組（列管、重產
  tool-surface），本片沒做。
