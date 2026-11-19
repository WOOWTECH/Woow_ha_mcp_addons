# HA 多帳號 HM-19a provenance：Odoo 0.5.0 升版 PR（多帳號首發 R1）（2026-11-19）

## 結論

- **Odoo 開通多帳號，版號 0.4.14 → 0.5.0**：`features.MULTI_PROFILE_PRODUCTS = frozenset({'odoo'})`；版號資料照 `docs/operations/release.md`
  「升版時要改的版號資料」（`VERSION_OVERRIDES` 加 Odoo，共用的 `VERSION` 維持 0.4.14；workflow 第一次帶三路版號運算式）。其他產品的開關、版號與
  `addons/<產品>/` 都沒動，OpenDesign 不跟著升來源版本。
- **只準備到計畫 §11.3 第 2 步**：本機兩個 commit，沒有推送、沒開 PR、沒有觸發任何 workflow、沒碰展示機或任何 HA 主機與後端。第 3～11 步（候選建置與
  容器驗收、Store 乾跑、HM-19c、推 GHCR、HAOS 驗收、證據、合併、合併後）都**待負責人批准**，逐步列在 `docs/operations/release-decision-odoo-0.5.0.md`。
- **路線**：計畫寫的「repo 外 builder」照負責人 2026-11-17 的決定改成本 repo 的 `.github/workflows/release.yaml`（GitHub 託管機器；gate → candidate →
  publish，publish 要負責人核准 `public-release`；只收 `release/*` 分支）。本分支 `release/odoo-0.5.0-20261119` 符合它的分支規則。
- **測試**：開關一開，整套 pytest 第一次跑 6,638 案、125 案失敗（35 分 51 秒）：29 案是本機環境（不是 root、沒有 Chromium），和開關無關；96 案讀到倉庫的開關。寫給「沒開通」的
  測試改成自己指定模式（新的 `tests/switch_modes.py` 的 `switched_off`，或兩個 harness 的 `switch=False` 改成「所有產品都關」），HM-01 黃金回歸與
  兩個契約凍結的**期望值一個字都沒改**，對每個產品照舊逐位元；開通的版本照舊由 `tests/test_router_passthrough.py` 開著再跑一次。釘開關的測試改成
  精確釘 `SWITCHED_ON = frozenset({'odoo'})`，加「能有帳號、版號至少 0.5.0」的第二道（照 HM-23 審查 S-2 的做法）。逐檔理由在第 4 節。修完後全套 6,607 過、32 失敗：29 案需要 root 或 Chromium；2 案因本機 Node 22 與釘選的 Node 26 原生模組不相容，隔離副本換用 Node 26 後相關兩檔 51 過；1 案的 loopback 假後端綁錯位址，修正後兩種模式皆過。
- **Store hook**：HM-16 的草稿 `packaging/hooks/seed`、`verify` 搬進 `addons/odoo/upgrade-check/`（`git mv`，可執行位元保留）。
- **文件**：Odoo 的 CHANGELOG（契約第 1.4 節 20 點、兩個位元組變化、A8／A9 的守門通知與 `restore_notice`）、DOCS（「多帳號（0.5.0 起）」：每帳號網址、
  面板帳號頁、一個代理一個帳號、還原核對、事故處理，連到 HM-18 的 repo 文件）、README；根目錄 CHANGELOG、README、`upgrade-notes.yaml`；
  `unreleased-changes.md` 照「怎麼更新」第 3 點；repo 文件裡「還沒有產品開通」的狀態句；緊急發版範本照本版核對、改了一處。
- **預檢**：帳本與封裝設定驗證通過；packaging unittest 370 案通過（5 skip）；面板 Node 測試 118 過。秘密掃描必須在提交後重跑。
- **要負責人決定的**：第 10 節（HM-15 首發前做不做、三路運算式怎麼驗、Store 乾跑、HM-19c 的機器與規格、緊急發版範本的預先核准、測試開關工具的去留，以及第 3～11 步）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-19a（計畫 §12.3 HM-19a：§11.3 第 1～4 步的準備、逐檔核對清單、緊急關閉版範本、`upgrade-notes.yaml` 條目、hook `seed`／`verify`；FM-02、09、70、102、103、104、106、136、146） |
| 分支 | `release/odoo-0.5.0-20261119`（一般 clone `ha-mp-hm19a-20261119`，從 `origin/claude-delivery` 開） |
| 基準 | `claude-delivery` `95b7e9d`（#122 HM-18 的合併；之前 #123、#124、#109、#116、#112、#108 都已合併） |
| 版號 | 計畫 §11.2、DQ-32：開通的產品升 0.5.0。計畫與版號線都寫 0.5.0，分支名不用改 |
| 依據 | 計畫 §11.3、§11.4、§12.3 HM-19a、§10.6；`docs/operations/release-decision-0.4.14.md`（格式）；PR #119（`53ffe61`）各 commit 改到的檔；`docs/multi-profile/unreleased-changes.md`（第 1、7 節）；`docs/operations/update-backup-rollback.md` 的緊急發版範本；HM-16 筆記第 13 節、HM-20 筆記第 13 節、HM-18 筆記第 10 節交給 HM-19a 的事；`wave5/review-HM-23-correctness.md` 的 S-2、S-4（repo 外） |
| 對齊的 PaaS | 不適用：不改執行期程式，只打開開關；開通後的行為由各片照它們的 PaaS pin 對齊過（契約第 9 節） |
| 受開關管 | 本片就是開關本身：`odoo` 進 `MULTI_PROFILE_PRODUCTS` |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/features.py` | `MULTI_PROFILE_PRODUCTS = frozenset({'odoo'})` 與上面一行註解 |
| `packages/mcp-admin-core/mcp_admin_core/__init__.py` | `PRODUCT_VERSIONS` 加 `'odoo': '0.5.0'`；註解改成兩個 override |
| `packaging/validate.py`、`packaging/inputs.json` | `VERSION_OVERRIDES`／`version_overrides` 加 Odoo |
| `addons/odoo/config.yaml`、`apps/odoo/Dockerfile` | `0.5.0` |
| `.github/workflows/ci.yaml`（2 處）、`release.yaml`（4 處） | `validate.py` 產生的三路運算式 |
| `docs/provenance/runtime-patches.json` | 只重算 `__init__.py`、`features.py` 兩列的摘要與說明 |
| `addons/odoo/upgrade-check/seed`、`verify` | 從 `packaging/hooks/` 搬來（`git mv`），說明各改兩句 |
| `addons/odoo/CHANGELOG.md`、`DOCS.md`、`README.md` | 0.5.0 段；「多帳號（0.5.0 起）」與第 26 行那句、密鑰網址與 3000 那兩點；多帳號一點與 Claude.ai 那句 |
| `CHANGELOG.md`、`README.md`、`upgrade-notes.yaml`（根目錄） | Odoo 0.5.0 段；狀態段與第 46～47 行；0.5.0 條目 |
| `tests/switch_modes.py`（新）、`tests/multi_profile_runtime.py` 與 37 個測試檔 | 第 4 節 |
| `docs/multi-profile/unreleased-changes.md` | 照「怎麼更新」第 3 點：總表、第 1、3.1、4、7 節 |
| `docs/multi-profile/acceptance-matrix.md` | 登記 `tests/switch_modes.py`；`test_upgrade_zero_rewrite.py`、`test_upgrade_hooks.py` 兩列；Odoo 首發標準的 0.4.13 → 0.4.14（0.4.14 已發） |
| `docs/operations/` 的 `guide.md`、`clients.md`、`acceptance.md`、`release.md`、`update-backup-rollback.md`；`docs/runtime-configuration.md`、`docs/management-capabilities-v1.md`；`packages/mcp-admin-ui/README.md` | 「還沒有產品開通」改成「Odoo 從 0.5.0 起開通」；`release.md` 三路運算式那句；`acceptance.md` hook 的位置；緊急發版範本的釘選測試一項與核對紀錄 |
| `docs/operations/release-decision-odoo-0.5.0.md`（新） | Odoo 專用發佈紀錄草稿；正式驗收證據待補 |
| 本筆記（新） | |

沒改：執行期程式（開關一行以外）、`tests/conftest.py`、HM-01 黃金回歸與兩個契約凍結的期望值、`tests/contract/*`、`packaging/` 的程式與測試（`container_probe.py`、
`container_acceptance.py` 不用改，第 3.3 節）、其他產品的 `addons/<產品>/`、`ha_role.py` 與 `docs/ha-role-core-contract.md`（Core 沒有新版）、`translations/*`、
`docs/tool-surface.*`（`apps/runtime`、`apps/*/launch.py` 沒動；`tool_inventory.py` 沒有漂移）、`packaging/secret-triage.json`、`addons/odoo/upgrade-notes.yaml`（等升版比對要求）、
`release-decision-odoo-0.5.0.md`（推送之後才寫）。

## 3. 版號資料、開關與 hook

### 3.1 版號資料與三路運算式

- `VERSION_OVERRIDES = {'odoo': '0.5.0', 'headscale': '0.4.19'}`（照 `release.md` 的寫法寫在一行，`packaging/test_validate.py` 照 `repr()` 找它）。
  `validate.py` 印出的運算式是 `${{ <app> == 'odoo' && '0.5.0' || <app> == 'headscale' && '0.4.19' || '0.4.14' }}`（`PRODUCTS` 的順序：Odoo 在前），
  照著逐字換掉 `ci.yaml` 2 處、`release.yaml` 4 處，`validate.py` PASS。
- 這是 workflow 第一次帶三路串接。`packaging/test_validate.py` 已照 GitHub Actions 的規則（`&&` 先於 `||`）求值過多路運算式；GitHub 實際算的值還沒看過
  （`release.md` 原本寫「要用之前先用拋棄式 workflow 只印出運算式的值確認」）：本片不觸發任何 workflow，交負責人決定（發佈紀錄「版號資料」一節）。
  算錯的話 `supply_chain.py candidate` 在推送前就停，不會推錯 tag。
- 綁版號的測試不用改：HM-17 之後讀 `version_for()` 與 `packaging/inputs.json`（Headscale 0.4.19 的升版也沒改）。

### 3.2 開關

`features.py` 只改 `MULTI_PROFILE_PRODUCTS` 那一行（加一行註解）。`enabled()`、`KNOWN_PRODUCTS` 不動。帳本兩列照 `ledger-tracking.md` 第 4 節只重算改到的檔
（沒有整本 `--write`）。

### 3.3 容器驗收的假後端位址（計畫 §11.3 清單、HM-16、HM-20）

HM-16 已讓 `container_probe.mock_bind_host` 與 `container_acceptance.main` 看開關（開通的產品給一次性 internal bridge、假後端綁容器的私有位址；探針跑完再跑
多帳號階段），HM-20 的 tripwire 測試在開關一開時照樣過：packaging unittest 開著 Odoo 跑 370 案 OK（5 個要 root 的 skip）。所以這兩檔不用改；
多帳號階段第一次在真容器跑是 §11.3 第 3 步（`release.yaml` 的 candidate）。

### 3.4 Store hook

- `git mv packaging/hooks/{seed,verify} addons/odoo/upgrade-check/`，`tests/test_upgrade_hooks.py` 的 `HOOKS` 改指新位置（HM-16 筆記第 13 節）。說明各改兩句
  （「草稿、HM-19a 會搬」改成「HM-16 起草、HM-19a 搬來」）；程式一個字沒改。不需要 `settings.yaml`（預設 600 秒 hook 上限、300 秒啟動上限）。
- 同一個測試檔的真 runtime 案例：舊版「沒開通」原本是「不寫前置碼」（讀倉庫的開關），倉庫開了 Odoo 之後舊版就變成開通的：改成前置碼明寫
  `frozenset()`（第 4 節）。
- UC-19（hook 能不能以 root 讀 0600 的 `state.json`、連到 8081）要等本 PR 的 `Upgrade comparison` 第一次在 Store 的 CI 跑才知道；不行就停下回報，不改成
  走管理 API（HM-16 筆記第 13 節）。

## 4. 測試：開關一開，讀到倉庫開關的測試

### 4.1 找法與原則

- 照 HM-23 的找法：倉庫開著 Odoo 跑整套 pytest，看失敗的是哪些。第一次（15:18～15:54）6,638 案：6,513 過、125 失敗；失敗的 96 案分在 44 個檔（第 4.2 節），另 29 案是本機環境（第 4.3 節）。
- 原則（`tests/switch_modes.py` 的說明）：寫給「沒開通的 add-on」的測試，倉庫開了某個產品之後要照樣測同一件事，所以不讀倉庫的開關，自己要
  `switched_off`（測試期間所有產品都沒開通）。寫給開通的 add-on 的測試自己開（`switched_on`、`multi_profile_runtime`、子程序前置碼）。這樣：
  - 期望值不用改，每個測試照舊測它原本測的東西；HM-01 黃金回歸與兩個契約凍結對**每個產品**（含 Odoo 的關閉狀態）照舊逐位元。
  - 沒開通的 add-on 仍是其他七個產品出貨的樣子，也是 Odoo 緊急關閉版會回到的樣子（`update-backup-rollback.md` 的範本），所以要留著測。
  - 關閉版只要改 `features.py` 與 `SWITCHED_ON`，這些測試都不用改回（範本已照改）。
- `tests/switch_modes.py` 的 fixture 和 HM-23（#127）、HM-26（#130）收斂的同名工具同一個名字、同一個意思（所有產品都關）；說明文字不同，所以那兩片
  合併時這個檔會衝突，選一份就好（要不要先拆成一個只含工具的小 PR 先合，負責人還沒定：2026-11-19 待決事項第 5 點）。各檔的改法也照 HM-23
  `e803d58` 的寫法（整個模組用 `pytestmark`，或單一測試加參數），註解寫 HM-19a。

### 4.2 逐檔

| 檔 | 失敗的案（第一次全套） | 為什麼讀到開關 | 改法 |
|---|---|---|---|
| `tests/test_single_profile_golden.py` | odoo 兩案 | HM-01 黃金回歸用 `production_runtime`：Odoo 開了就走分派器，bootstrap 沒帶 `X-MCP-Profile` 回 400 | 整個模組 `switched_off`；期望值不動；開著的版本在 `test_router_passthrough.py` |
| `tests/test_admin_contract_freeze.py`、`tests/test_mcp_contract_freeze.py` | 各 odoo 一案 | 同上（管理契約凍結、8081 契約凍結） | 同上 |
| `tests/test_admin_pipeline_matrix.py` | `[switched off]` | 參數的「switched off」那半用 `production_runtime`（讀倉庫） | 那半 `request.getfixturevalue('switched_off')` |
| `tests/test_child_bearer.py` | odoo 兩案 | 子程式 spec 開通後多 `WOOW_MCP_DENY_LOOPBACK=1`；真子程式拒連 loopback 假後端（HM-20） | 整個模組 `switched_off`（HM-20 的兩種模式在 `test_backend_loopback.py`） |
| `tests/test_child_port_param.py` | odoo 四案 | 預設子程式 spec 快照是沒開通的（同上）；`production_runtime` | 整個模組 `switched_off`；快照不動 |
| `tests/test_profile_runtime.py` | odoo 三案 | 沒開通時 `run_product` 只服務預設帳號的 runtime；`production_runtime` | 整個模組 `switched_off` |
| `tests/test_connection_patch.py`、`test_product_boundary.py`、`test_product_ha_role.py`、`test_role_lifecycle.py` | 各 odoo 1、1、7、3 案 | 單帳號 runtime 與它的替身（例：替身 Manager 不收開通後才傳的 `delays`；新來源要重填秘密是開通後才有，422） | 整個模組 `switched_off` |
| `tests/test_expansion_runtime.py`、`test_output_schema_runtime.py`、`test_protocol_clients.py`、`test_six_hardening.py`、`test_odoo_allowed_methods_runtime.py`、`test_odoo_child_switch_runtime.py`、`test_odoo_probe_auth_rejected.py`、`test_odoo_tool_timeout.py`、`test_odoo_overlay_parity.py`、`test_odoo_health_probe.py` | 1、2、4、3、5、5、7、3、6、1 案 | 真 Odoo 子程式接 loopback 假後端：開通後子程式拒連（`BACKEND_DESTINATION_DENIED`，HM-20） | 整個模組 `switched_off`：測的是子程式的工具行為，兩種模式相同；loopback 規則在 `test_backend_loopback.py` 兩種模式都測 |
| `tests/test_odoo_read_exists.py`、`test_raw_backend_errors.py` | 各一案 | 同上（其他案和開關無關） | 那一案 `switched_off` |
| `tests/test_dormant_profiles.py` | 一案 | 「休眠」＝沒開通、有帳號資料：`production_runtime` 讀倉庫 | 那一案 `switched_off` |
| `tests/test_odoo_identity_rotation.py`、`test_profile_admin_api.py`、`test_profile_ports.py`、`test_origin_policy.py`、`test_profile_lifecycle.py`、`test_saved_destinations.py` | 各一案（都叫 `switched_off…` 或測沒開通的存檔） | `production_runtime` 或產品的管理 app 讀倉庫 | 那一案 `switched_off` |
| `tests/test_request_budget_gateway.py` | 兩案 | 沒開通時 8081 是預設帳號自己的 app（測試讀它的 `state`）；開通後是分派器 | 兩案 `switched_off` |
| `tests/test_restore_review.py` | 七案 | 單帳號還原提示（沒開通）與沒開通時沒有的路由 | 五個測試函式（七案）`switched_off` |
| `tests/test_restore_detection.py` | 一案；**另一個 root 才跑的同名案（CI）也會** | 容器探針的還原階段照倉庫開關分支：Odoo 開了就檢查開通的還原檔（`restore files missing`）；守門那半本來就寫死 `enabled=False` | 兩案（一般與 `test_root_…`）都 `switched_off`；fork 出來的 uid 10001 子程序沿用同一份開關 |
| `tests/multi_profile_runtime.py` | （經它）`test_gateway_busy_shapes`、`test_gateway_stream_endings`、`test_initialize_generation`、`test_panel_profile_api_shapes`（兩個情境）、`test_profile_quotas`、`test_reply_mask_union`、`test_reply_worker`、`test_router_passthrough` 各一到兩案 | `switch=False` 原本是「不動倉庫的開關」 | `switch=False` 改成所有產品都關（同 HM-23） |
| `tests/test_monitor_cancel.py` | 一案 | `run_until_sigterm(switch=False)` 同上（HM-23 審查 S-4 預告的） | 同上 |
| `tests/test_real_products.py` | odoo 一案 | 子程序（owned executable）讀倉庫開關：開通的 Odoo 子程式拒連 loopback 假後端；健康檢查連兩次失敗才判斷線 | **照出貨的模式測**（同 HM-23）：產品拒 loopback 時假後端綁本機私有位址（和 Headscale 一樣，真的目的地檢查照舊生效）；開通時等斷線多一個 `HEALTH_INTERVAL` |
| `tests/test_upgrade_zero_rewrite.py` | 兩案 | 釘「開關是空集合」；零改寫那案的「沒開通」那半讀倉庫 | 釘選改成 `SWITCHED_ON = frozenset({'odoo'})`＋第二道（能有帳號、版號至少 0.5.0）＋反向對照（照 HM-23 審查 S-2 的做法）；零改寫的「沒開通」那半用 `switched_off_runtime`。另：子程序前置碼那案原本把 Odoo 打開，倉庫開著時證明不了什麼，改成打開 EMQX、關掉 Odoo |
| `tests/test_upgrade_hooks.py` | （沒失敗） | 真 runtime 的「舊版沒開通」原本不寫前置碼 | 前置碼明寫 `frozenset()`（第 3.4 節）；`HOOKS` 指新位置 |

### 4.3 本機環境的失敗（和開關無關；CI 是 root、有 Chromium）

和 0.4.14 那次本機全套一樣是 29 案（7 個要 root、22 個瀏覽器），訊息逐案看過，都不是開關造成的：

- 要 root（CI 是 root；本機 uid 1000，測試開頭就照設計失敗）：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`tests/test_restore_detection.py` 的 `test_root_backup_restore_and_repair`、
  `test_root_start_without_a_restore_changes_nothing`、`test_root_marker_name_taken_by_a_directory`（兩案）、
  `test_root_the_container_probes_restore_stage_meets_the_entrypoint`（這一案在 CI 會讀到開關，已一起改，第 4.2 節）。
- 瀏覽器（這個 clone 的 Playwright 沒有 Chromium headless shell：`browserType.launch: Executable doesn't exist`）：
  `tests/test_owned_browser_redirect.py` 16 案、`tests/test_owned_browser_ipc.py` 5 案（`[*-True]`，拿不到瀏覽器的回覆）、
  `tests/test_owned_ui.py::test_standalone_ownership_boundaries[browser]`。這三個檔都不起任何產品的 runtime。

### 4.4 沒改的

- packaging 的兩個測試（`test_container_probe.py`、`test_container_acceptance.py`）照倉庫的開關算期望值，開著 Odoo 照樣過（第 3.3 節），沒改（HM-23 為 EMQX
  改成 `switched()`，是它自己的選擇）。
- 通過的測試沒有逐一改：用 Odoo、讀倉庫開關、開著也過的測試，現在測的是開通的 Odoo（出貨的模式）。
- `tests/conftest.py` 沒改（任務規定；要加「預設關、測試自己開」的 fixture 要負責人核准，待決事項第 5 點）。

## 5. 文件

- CHANGELOG 的來源：`unreleased-changes.md` 第 1 節（A8、A9）與第 7 節（契約第 1.4 節 20 點與兩個位元組變化的建議句）。Odoo 是開通的版本，所以：
  - 兩個位元組變化的建議句拿掉「once multiple profiles are switched on」；
  - A8、A9 併進還原那兩點（開通後沒有帳號資料的還原另寫 `restore-record.json`、換新索引旁與 Origin 政策旁的收據；有帳號資料時撤銷每個帳號；守門沒做完時
    什麼都不服務，這是開通後的規則：A8 原句「提示存不下或標記刪不掉照常啟動」只對沒開通又沒有帳號資料的成立，`restore_lock.guard` 照讀過）；
  - 第 4 節「多帳號基礎、開關關時看不到」那句不寫（開通了都看得到），改寫「之前的映像關著帶的多帳號基礎在這個映像打開」。
- DOCS：照 HM-18 的 `guide.md`、`clients.md`、`update-backup-rollback.md`，連回 repo 文件（GitHub 網址，同既有寫法）。HM-20 交的 loopback 那句、HM-12 交的換身分換權杖與
  503 後確認網址、HM-27 交的 Origin 三件事（政策檔壞掉每個帳號 503、關掉後 enforce 失效、還原帶回政策）、HM-13b 交的守門 log 與快照還原都寫了。
- `upgrade-notes.yaml`：根目錄的人讀條目（計畫 §7.3、FM-136；0.4.7 前例）。`addons/odoo/upgrade-notes.yaml` 是 Store 機讀的，照 `AGENTS.md` 第 3 點等升版比對要求
  才建（options、schema、ports 都沒改，第 1 類比對預期不報；FM-103 寫的「違反規則 3」指的是這個檔）。
- 計畫 §10.6 第 1 點寫「0.4.13 → 0.5.0」：0.4.14 在 2026-11-18 發了，HM-19b 要測 0.4.14 → 0.5.0；`acceptance-matrix.md` 與發佈紀錄照實寫，計畫本身交主對話。

## 6. 本機檢查（2026-11-19，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

- 全套 pytest：6,607 過、32 失敗（第 4.3 節與上方摘要）；修正 loopback 測試後針對性重跑 2 過。root 與 Chromium 由 CI 驗，n8n 兩個測試檔在 Node 26 隔離環境 51 過。
- `packaging/validate.py` PASS；`ledger_precheck.py` result OK；packaging unittest 370 案 OK（5 skip）；Node 面板測試 118 過。
- 預檢的秘密掃描當時沒有掃描未提交檔案：必須提交後重跑，不能把那次結果視為已掃描本次變更。

## 7. 只在 CI 跑的、`checks` 秒數

- CI（root、0 skip）跑全套；本機不是 root、沒有 Chromium 的案在第 4.3 節，CI 會跑到。和開關有關的 root 案只有 `test_root_the_container_probes_restore_stage_meets_the_entrypoint`，
  已照一般那案一起改（第 4.2 節）；其他 root 案（`test_root_backup_restore_and_repair` 等）寫死 `enabled=True`／`False` 或不經開關，看過程式碼確認。
- Playwright 面板測試（`tests/browser/*.spec.mjs`，CI 的 `unit.sh` 跑 single 與 profiles-on 兩組）本機沒跑：面板程式沒改，伺服器端的開關不影響它的 fixture。
- `checks` 秒數：開 PR 後補在 PR 說明。

## 8. 帳本與 tool-surface

- `runtime-patches.json`：`__init__.py`、`features.py` 兩列重算摘要、補說明；其他列不動。`ledger_precheck.py`：三本帳本 0 drift、0 missing，result OK。
- `docs/tool-surface.*`：`apps/runtime`、`apps/*/launch.py` 沒動，不用重產；`tool_inventory.py`（不寫）沒有漂移。
- hook 搬進 `addons/odoo/upgrade-check/` 之後算 Store 的執行期內容，不是映像的帳本（HM-16 筆記第 9 節）。

## 9. 交給後面的片、還沒解決的事

- **HM-19b、HM-19c**：發佈紀錄的驗收清單與批准表。HM-19c 是放行條件（契約第 5 節）。
- **HM-23、HM-26 合併時**：`tests/switch_modes.py` 與本片改過的測試檔會和它們的同一批改動衝突（同一個意思、註解不同）；`SWITCHED_ON` 那一行要保留 `{'odoo'}`。
  HM-21～HM-26 合併本 PR 之後再跑一次整套：本片只修了 Odoo 開著時失敗的測試。
- **計畫（repo 外，主對話）**：§10.6 第 1、6 點的 0.4.13 改成 0.4.14；§11.3 的「repo 外 builder」各步照 2026-11-17 的路線改寫（發佈紀錄的批准表是改寫後的樣子）；
  §12.3 HM-19a 記本片做到第 2 步。
- **`docs/operations/acceptance.md`** 的 CONTAINER 那一列仍寫「repo 外 builder」：路線換了之後沒跟上，留給下一次文件同步（本片只改 hook 那一列與狀態）。
- **HM-18 交的其他事**：容器探針要不要送一次帶 `Origin` 的請求（HM-27 筆記第 21 節）本片沒做，留給下一個改探針的片；`tests/test_admin_pipeline_matrix.py`
  補「開關開時表外方法的 `Allow` 是 6 個」那一案，本片也沒做（只改那個檔的模式選擇）。

## 10. 要負責人決定的事

1. HM-15（listener 身分檢查）：計畫把它列為 R1 的條件式前提；DQ-37 已照 (a)，HM-03a 量到同 uid 讀得到 dumpable 子程式的 fd，條件看起來成立，
   但 `decisions.md` 仍寫待定、沒有人做。首發前完成實作與獨立安全審查，並驗證實際子程式是否可檢查；不可用時依契約第 9 節 #13 降級（子程式 bearer 是主防線）。
2. 三路版號運算式：第一次觸發 `release.yaml` 前要不要先用拋棄式 workflow 驗（要一個 workflow 檔與一次觸發），或接受 candidate 在推送前擋。
3. §11.3 第 4 步 Store 升級乾跑：決定用哪台有 Docker 的機器跑 candidate 的 `image.tar`；依計畫須在推送前完成。
4. §11.3 第 5 步 HM-19c：在哪台量（展示機就是 J6412）、J1900 與出貨機的記憶體規格（DQ-29）；UC-20 是「不行」，候選映像不能直接側載（計畫的替代做法：
   拋棄式開關開映像，不改版號、不推）。
5. 緊急發版範本（關閉版）的預先核准（本片核對過，改了一處）。
6. 測試的產品開關工具：本片的 `tests/switch_modes.py` 要不要先拆成只含工具的小 PR，或本 PR 先合、HM-23 與 HM-26 合併時改用這份。
7. §11.3 第 3～11 步逐步批准。

## 11. commit

| commit | 內容 |
|---|---|
| `dfd146d` | 升版：開關、版號資料、workflow 運算式、帳本、hook 搬家、測試、Odoo 與根目錄的 CHANGELOG／DOCS／README／`upgrade-notes.yaml`、repo 文件的狀態句 |
| 下一個（本筆記所在） | 發佈紀錄草稿 `release-decision-odoo-0.5.0.md`、本筆記 |

commit 身分都是 woowtech；英文標題、繁中內文；訊息裡沒有任何署名行。沒有 push。
