# HA 多帳號 HM-17 provenance：發版基礎（多產品版號運算式、readiness 只認產品自己的紀錄）（2026-11-14）

## 結論

- 範圍：發版工具與測試（`packaging/`、兩個 `tests/` 測試檔、三個 workflow 的註解、`docs/`）。沒有改執行期檔
  （`packages/`、`apps/`）、版號、`addons/<x>/`、CHANGELOG、帳本、tool-surface。這片不受產品開關管（計畫 §3.3），
  對任何產品的映像與行為都沒有影響。
- **版號照舊**：`VERSION` 0.4.13、`VERSION_OVERRIDES` `{'headscale': '0.4.18'}` 沒動。由它產生的 `CI_VERSION`、
  `RELEASE_VERSION` 和 `32ecac8` 的兩個常數逐字相同；五個 workflow 以 YAML 解析後和 `32ecac8` 完全相同（只改註解）。
- **job 條件 0 處改動**：必要檢查（`checks`、`readiness`、`Upgrade comparison / compare`）只會更嚴、不會變寬鬆（第 4 節）。
- `packaging/validate.py`：
  - `version_expression()` 由 `VERSION_OVERRIDES` 產生多路運算式 `a == 'x' && 'v1' || a == 'y' && 'v2' || 'v0'`
    （計畫 §11.2；不用 `fromJSON`）。
  - builder workflow 裡讀 app 的運算式只准是產生的那一個；release.yaml 的證據 artifact 名稱也逐字比對（原本沒比）。
  - 每個產品 Dockerfile 的 `ARG BUILD_VERSION` 預設值要等於 `version_for()`（原本要到 builder 的容器驗收才發現）。
  - 發版資料錯（例如 override 等於預設版號）時，`validate.py` 與每個 import 它的 packaging 工具都只印一行
    `packaging validation failed: …`（原本是 traceback）。
- `packaging/release_gate.py`：readiness 只認產品自己的紀錄 `docs/operations/release-decision-<add-on>-<version>.md`，
  內文要寫到 slug 和版本。共用紀錄、別的產品的紀錄都不算。補掉 R10 RG-12 的盲點（0.4.14～0.4.18 會被 Headscale 的
  紀錄放行）。新規則只會更嚴。
- 綁版號的測試：packaging 讀 `version_for()`；`tests/` 讀發版資料 `packaging/inputs.json`，不讀受測的 runtime。
  `validate.py` 把 `inputs.json` 綁到 `VERSION`、`VERSION_OVERRIDES`，再綁到 manifest、Dockerfile 預設值、workflow 與 core 的
  `PRODUCT_VERSIONS`，所以之後的升版 PR 只改資料。in-process 測試照兩個 launcher 給 gateway 版號（n8n 不帶），gateway 的
  預設版號因此也有測試；新的 pytest 測試用 HM-01 的 log 掃描。
- `docs/operations/release.md` 加「升版時要改的版號資料」：7 處資料、照 `validate.py` 印出的運算式換 workflow 的 6 處。
- 先紅後綠：新測試在 `32ecac8` 的程式上 10 個測試方法失敗；改完全過（第 3.1 節）。只改資料的升版模擬：Odoo 0.5.0 全過；
  n8n 0.5.0 被擋，因為 `apps/n8n/run.py` 不傳版號（第 3.2 節）。拿掉 runtime 的版號對應或 gateway 的預設版號，
  5 個變異都被擋（第 3.3 節）。
- 本機：`validate.py` PASS；packaging 192 個 `OK (skipped=5)`（5 個要 root，和基準相同）；兩個改過的 pytest 檔 70 案
  全過、0 skip；HM-01 的守門測試與會讀 packaging 檔的測試 125 案全過、0 skip；整套 pytest 收集 3747 案、0 收集錯誤。
- 兩個預檢：秘密預檢 6 個 commit 0 命中；帳本預檢 0 漂移、沒有改到列管檔。
- 獨立審查判「修正後通過」：必修 3 項都改了；建議 4 項都採用，其中 SF-3 要等 PR 的 CI，開 PR 後核對（第 13 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-17（計畫 §11.2、§12.3；風險中、工作量 M；不受開關管） |
| 分支 | `feat/ha-multiprofile-hm17-20261114` |
| HA 基準 | `32ecac8`（`claude-delivery` @ `bb48449`＋HM-01，PR #90 還沒合併） |
| 依據 | 計畫 §11.2、§11.3、§12.3 HM-17；審查 C4-SF-1、C4-SF-2；研究 R10（RG-11、RG-12）；FM-104；本片的獨立審查（MF-1～MF-3、SF-1～SF-4，第 13 節） |
| 對齊的 PaaS | 不適用：PaaS 以 commit＋digest 釘版（FM-104 的 PaaS 欄），沒有對應的程式可移植 |
| FM | FM-104 |

commit（依序，都在 `32ecac8` 之上；rebase 到 `claude-delivery` 後 hash 會變，所以這裡只寫標題）：

| commit 標題 | 內容 |
|---|---|
| `feat(packaging): generate the per-product version expressions from VERSION_OVERRIDES (HM-17)` | `version_expression()`、`workflow_versions()`、`build_version_default()` 與 `packaging/test_validate.py`；ci.yaml、release.yaml 只加註解 |
| `fix(release-gate): count only the product's own release record (HM-17)` | readiness 只認產品自己的紀錄；`packaging/test_release_gate.py`、`docs/operations/release.md`、`woow-addon-release.yml` 的註解 |
| `test: read the expected release version from packaging/inputs.json (HM-17)` | `tests/test_real_products.py`、`tests/test_unconfigured_connect.py`：期望值讀發版資料、in-process 照 launcher 給版號、log 掃描、新增「runtime 給的版號＝發版資料」一案 |
| `fix(packaging): report invalid release data in one line at import (HM-17)` | `validate.py` 載入時的資料錯誤改成一行訊息；`packaging/test_validate.py` 加一個測試 |
| `docs(operations): list the version data a version bump changes (HM-17)` | `docs/operations/release.md` 的升版步驟與多路運算式的前提 |
| `docs(provenance): add HM-17 multi-profile provenance note` | 本筆記 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/validate.py` | `version_expression(selector, overrides, default)`：每個 override 一段 `<selector> == '<產品>' && '<版號>'`，依 `PRODUCTS` 順序，用 `\|\|` 串起來，最後接預設版號；沒有 override 時是裸版號（0.4.14 以前的寫法）。拒絕：不認得的 selector、`PRODUCTS` 以外的產品（含已封存的 Odoo Manage）、不是 `x.y.z` 的版號（版號也因此不會帶引號）、等於預設版號的 override。`CI_VERSION`、`RELEASE_VERSION` 改成在模組載入時由它產生（`Invalid`、`require` 移到檔頭）；資料錯時以 `SystemExit('packaging validation failed: …')` 停止：一行、exit 1，和 `validate.py` 其他錯誤同一個格式，import 它的 `check_release.py`、`supply_chain.py`、`registry_gate.py`、`container_acceptance.py`、`pilot_variant.py` 也一樣。`workflow_versions()`：workflow 裡每個讀 app（`matrix.app`、`inputs.app`、`github.event.inputs.app` 與 `['app']` 寫法，不分大小寫）的運算式，除了 app 本身，都必須逐字等於產生的運算式；release.yaml 的 `published-evidence-…` 名稱逐字比對；`builder_workflow()` 一開始就呼叫它。`build_version_default()`：Dockerfile 只有一個 `ARG BUILD_VERSION`、預設值等於 `version_for(product)`、只有一個 `io.hass.version` 而且用 `${BUILD_VERSION}`；`validate()` 對每個產品都檢查 |
| `packaging/test_validate.py` | 測試自帶 GitHub Actions 運算式求值器（字串、單一屬性、`==`、`&&`、`\|\|`；`&&` 優先於 `\|\|`、回傳運算元、字串比較不分大小寫），用「GitHub 會算出什麼」驗，不是比產生器自己的字串。新增 5 個、改寫 1 個測試（20 → 25）：產生的形式與 5 組合成資料下每個產品的值；拒絕的資料 12 種；兩個 workflow 每個 app 在每個位置（tags、build-args；release 另有 IMAGE、證據名稱）都拿到 `version_for(app)`；模擬升版（多一個 override）時，沒重產的 workflow 被擋、全部重產就過、只留一個位置沒重產或改成固定版號就擋、等價但手寫的運算式也擋、別處多一個讀 app 的運算式也擋；資料錯時（override 等於預設版號、override 不是現有產品），在暫存複本上直接執行 `validate.py` 與 `import validate` 都只印那一行、exit 1（這個測試照 `repr()` 的寫法在一行裡找 `VERSION_OVERRIDES` 再換掉；找不到時失敗訊息會說明）；原本的 `test_headscale_version_is_independent_and_fixed_at_every_boundary` 改成讀資料的 `test_every_release_version_is_bound_at_every_boundary`（manifest、Dockerfile 預設值、`inputs.json` 都等於 `version_for()`，別的版號線的版號被擋） |
| `packaging/release_gate.py` | `record_name(slug, version)`：`woow_mcp_<x>` → `release-decision-<x 的 _ 換成 ->-<版號>.md`；slug 或版號不合格式就回報失敗。`own_record()`：那個檔存在、內文寫到 slug（字邊界）與確切版號（`0.2.2` 不比中 `0.2.20`）才算。`check_decisions()` 只用 `own_record()`；拿掉「只有 Headscale 要寫 slug」的特例；組不出檔名時記為失敗、其他 add-on 照常檢查。取代 `decision_records()`（repo 裡沒有別的呼叫者） |
| `packaging/test_release_gate.py` | 改寫 2 個、新增 3 個（8 → 11）：共用紀錄不再放行；別的產品的紀錄（含寫到這個 slug 的）不放行；一份寫了兩個 slug 的共用紀錄兩個都不放行；紀錄要寫到 slug 和確切版號；檔名規則與錯誤格式；repo 裡 Headscale 的 6 份紀錄都符合新規則，而且不放行任何別的產品 |
| `tests/test_real_products.py` | `release_version(product)`：發版資料 `packaging/inputs.json` 的 `version_overrides`／`version`（不在發佈清單的 Odoo Manage 得預設版號）。CI 的 pytest 環境在 `uv sync` 之後沒有 PyYAML，所以讀 JSON、不 import `validate.py`。`serverInfo.version` 期望 `release_version(product)`（原本 `'0.4.18' if product == 'headscale' else VERSION`）；拿掉不再用的 `VERSION` 匯入 |
| `tests/test_unconfigured_connect.py` | `released(product)`：照兩個 launcher 給 gateway 的值，Python 產品帶 `version_for_product(product)`（`run_product`），n8n 不帶（`apps/n8n/run.py`）。三處期望值改讀 `release_version(product)`：未設定後端的連線測試、版號測試、真 launcher 的連線測試（最後這處 `32ecac8` 讀 `version_for_product`）。Headscale 專屬的版號測試改成 8 個產品×兩條 initialize 路徑（2 案變 16 案），網址改用 `.invalid`，用 `log_scan` 掃 token、child token 與憑證。新增 `test_each_add_on_is_given_the_version_of_the_release_data`：9 個產品（含 Odoo Manage）的 `version_for_product()` 都等於發版資料。整檔 46 → 61 案 |
| `.github/workflows/ci.yaml`、`release.yaml` | 只加註解：運算式由 `validate.py` 產生、逐字比對 |
| `.github/workflows/woow-addon-release.yml` | 只改檔頭 readiness 的註解（4 行換 6 行） |
| `docs/operations/release.md` | readiness 的說明改成新規則：檔名、內文、共用與別的產品的紀錄不算、一個 PR 升幾個產品就寫幾份。新增「升版時要改的版號資料」：`VERSION_OVERRIDES`（寫在一行）或 `VERSION`、`inputs.json`、core 的 `PRODUCT_VERSIONS`（同 PR 更新帳本摘要）、manifest、Dockerfile 預設值、照 `validate.py` 印出的運算式換 ci.yaml 2 處與 release.yaml 4 處、產品自己的發佈紀錄；並寫明多路運算式的前提與第一次開 `release.yaml` 前要乾跑 |
| `docs/provenance/ha-multiprofile-HM-17-20261114.md` | 本筆記 |

沒改：`packages/`、`apps/`（含 `apps/n8n/run.py`，見第 12 節）、`addons/<x>/`、`packaging/inputs.json`、
`mcp_admin_core/__init__.py`、任何版號、CHANGELOG、`upgrade-notes.yaml`、帳本、tool-surface、`unit.sh`、HM-01 的守門測試檔、
其他 packaging 工具（`supply_chain.py`、`container_acceptance.py`、`registry_gate.py`、`check_release.py` 照舊讀 `version_for()`；
`check_release.py` 從 `validate` 匯入的 `Invalid`、`require` 名稱不變）。

## 3. 先紅後綠

### 3.1 先寫的測試，拿 `32ecac8` 的程式跑

`packaging/test_validate.py`、`packaging/test_release_gate.py` 先寫好，`validate.py`、`release_gate.py` 暫時換回 `32ecac8`
的版本（跑完 `git checkout` 還原）：35 個測試裡 10 個測試方法失敗（2 FAIL、8 ERROR；unittest 連 subTest 一起計，報
`FAILED (failures=2, errors=85)`）。

| 測試 | `32ecac8` 的程式 | 改完 |
|---|---|---|
| `test_version_expressions_are_generated_from_the_overrides` | ERROR：沒有 `version_expression` | 通過 |
| `test_version_expression_refuses_data_it_cannot_express` | ERROR（同上） | 通過 |
| `test_every_app_dependent_workflow_value_is_the_release_version` | ERROR：沒有 `workflow_versions` | 通過 |
| `test_a_stale_or_hand_written_version_expression_is_refused` | ERROR：沒有 `version_expression` | 通過 |
| `test_every_release_version_is_bound_at_every_boundary` | ERROR：沒有 `build_version_default` | 通過 |
| `test_unreleased_version_needs_its_own_decision_record` | FAIL：失敗訊息沒有指出 `release-decision-n8n-0.3.0.md`（舊規則讓共用紀錄放行） | 通過 |
| `test_another_products_record_never_counts` | FAIL：`0 != 1`。舊程式印出 `woow_mcp_n8n 0.3.0: release record release-decision-headscale-0.3.0.md`，就是 RG-12 的盲點 | 通過 |
| `test_record_must_name_the_slug_and_the_exact_version` | ERROR：沒有 `own_record` | 通過 |
| `test_the_record_is_named_after_the_add_on_directory` | ERROR：沒有 `record_name` | 通過 |
| `test_the_repository_records_follow_the_rule` | ERROR：沒有 `own_record` | 通過 |

審查後加的 `test_release_data_no_expression_can_carry_stops_every_tool_in_one_line`：`32ecac8` 的運算式是手寫常數、載入時
不產生，所以拿「一行訊息之前」的 `validate.py`（運算式已在載入時產生）跑：4 個 subTest 全失敗（`FAILED (failures=4)`；stderr 是
traceback，最後一行是 `Invalid: <原因>`，exit 1）；改完通過。

不靠新函式名稱的行為探針（repo 外的一支探針腳本，直接呼叫 `builder_workflow`；同一支腳本對兩版的 `validate.py` 各跑一次）：

| 探針 | `32ecac8` | 改完 |
|---|---|---|
| release.yaml 的證據名稱改成固定的 `0.4.13` | 接受 | 擋（`published evidence named with the release version`） |
| ci.yaml 的 `concurrency.group` 多一個 `matrix.app == 'odoo' && 'a' \|\| 'b'` | 接受 | 擋（訊息附上應有的運算式） |
| 8 個產品的 Dockerfile 預設值改成 `99.0.0` | 沒有這項檢查（`32ecac8` 的 `validate.py` 只比 workflow 的 build-args，不看 Dockerfile 的 `ARG BUILD_VERSION`） | 8 個都擋 |

升版時的訊息（模擬 R1：`VERSION_OVERRIDES` 加 `'odoo': '0.5.0'`，workflow 沒重產）：
`ci.yaml: the version expression generated from VERSION_OVERRIDES is ${{ matrix.app == 'odoo' && '0.5.0' || matrix.app == 'headscale' && '0.4.18' || '0.4.13' }}`；
release.yaml 同樣印出 `inputs.app` 的那一個。照著換掉就過（`test_a_stale_or_hand_written_version_expression_is_refused`）。

### 3.2 綁版號的測試：模擬「只改資料」的升版

`tests/` 的兩個檔是重構，在真的 runtime 上改前改後都該綠。為了證明它們跟著資料走，在 clone 裡暫時做一次只改資料的升版
（7 個檔：`validate.py` 的 `VERSION_OVERRIDES`、`inputs.json`、`PRODUCT_VERSIONS`、manifest、Dockerfile 預設值、ci.yaml 2 處與
release.yaml 4 處的運算式；發佈紀錄與帳本摘要不在模擬裡，這些測試不看），跑完用 `git checkout` 還原（`git status` 乾淨）：

| 情境 | 跑的檢查 | 結果 |
|---|---|---|
| Odoo 0.5.0 | `packaging/validate.py` | `PASS` |
| Odoo 0.5.0 | packaging unittest | `Ran 192`、`OK (skipped=5)` |
| Odoo 0.5.0 | 兩個檔 `-k "odoo or release_data"`（含真的 Odoo、Odoo Manage 子程式） | 11 passed：未設定後端 2 案、版號測試 2 案、「runtime 給的版號＝發版資料」、後端連不到的 in-process 1 案、真 launcher 2 案（未設定、連不到）、真子程式 3 案（Odoo、Odoo Manage、Odoo Manage 沒有後端時的初始化） |
| Odoo 0.5.0 | HM-01 黃金回歸 `-k odoo` | 2 passed |
| n8n 0.5.0 | `packaging/validate.py` | `PASS` |
| n8n 0.5.0 | `tests/test_unconfigured_connect.py -k "n8n or release_data"` | 5 failed、3 passed：未設定後端的 `[bearer-n8n]`、`[secret-n8n]`，版號測試 `[False-n8n]`、`[True-n8n]`，真 launcher 的 `test_unconfigured_connect_runtime[n8n]`（都報 `0.4.13`、期望 `0.5.0`）；過的是「runtime 給的版號＝發版資料」與兩個後端連不到的案例 |

- Odoo：測試跟著資料走，不用改。`32ecac8` 的兩個檔在升版時要改測試本身：實作時暫改 `PRODUCT_VERSIONS`（emqx 合成版號
  `99.0.0`）跑 `32ecac8` 的兩個檔，3 案失敗（寫死 0.4.13 的 2 案與 `test_real_child_fake_backend_and_boundary[emqx]`）。
- n8n：`apps/n8n/run.py` 不傳 `product_version`，資料升了，n8n 照樣報預設版號；照 launcher 的 in-process 案例與真 launcher 的
  案例都擋。這是既有的缺口，n8n 有自己的版號線之前要先修 launcher（第 12 節）。

### 3.3 期望值獨立於受測程式：runtime 變異

在 clone 裡暫時改 runtime 一處，只跑相關案例，跑完用 `git checkout` 還原（`git status` 乾淨）。審查時拿改前的測試跑過
PT_A～PT_D：PT_A、PT_B、PT_D 全部存活，只有 PT_C 被擋。

| 變異 | 改了什麼 | 結果 |
|---|---|---|
| PT_A | `version_for_product()` 一律回 `VERSION`（Headscale 會報 0.4.13） | 擋：`-k "headscale or release_data"` 7 案全失敗（未設定後端 2、版號測試 2、「runtime 給的版號＝發版資料」、真 launcher、真子程式） |
| PT_B | `version_for_product()` 一律回 Headscale 的版號 | 擋：`-k "emqx or release_data"` 7 failed、2 passed（同上 7 案的 emqx 版；過的是兩個後端連不到的案例，不看版號） |
| PT_C（正向對照） | `run_product` 不傳 `product_version` | 擋：`-k headscale` 2 failed、4 passed（真 launcher 與真子程式；in-process 案例不經過 `run_product`） |
| PT_D | gateway 自己回 initialize（沒有子程式）時拿掉 `or VERSION` | 擋：1 failed、31 passed，`test_the_release_version_is_reported_by_both_initialize_paths[False-n8n]`（版號變 `None`） |
| PT_E | gateway 改寫子程式的 initialize 回覆時拿掉 `or VERSION` | 擋：3 failed、29 passed，未設定後端的 `[bearer-n8n]`、`[secret-n8n]` 與版號測試 `[True-n8n]` |

PT_D、PT_E 在正式環境只會碰到 n8n（`run_product` 一定帶版號）；改前的 in-process 測試讓 n8n 也帶版號，走不到這兩條預設路徑。

## 4. Workflow 與必要檢查（PR 說明用）

**改了哪些 job 條件：沒有。** 三個 workflow 只動註解；五個 workflow 以 YAML 解析後（PyYAML `safe_load`，註解拿掉、key
保留 PyYAML 的型別，遞迴正規化後取 SHA-256）和 `32ecac8` 逐一相同：

| workflow | 解析後的摘要（前 16 碼，前後相同） | 文字 |
|---|---|---|
| `ci.yaml` | `c38d75300f1dd40b` | 加 2 行註解 |
| `release.yaml` | `39e7c9a6d65a5850` | 加 3 行註解 |
| `woow-addon-release.yml` | `80dd1a6973c023e4` | 檔頭 readiness 註解 4 行換 6 行 |
| `release-train.yml` | `580b6c485e72d011` | 沒動 |
| `woow-addon-sync.yml` | `46cd1f31bda0edf9` | 沒動 |

所以 job、step、`if`、`needs`、`on`、`permissions`、`runs-on`、`timeout-minutes`、`concurrency`、job 名稱、`uses` 都沒變。
`ci.yaml` 在 PR 不跑（push `main`／手動），`release.yaml` 只能在 `main` 手動觸發；它們只被 `validate.py` 逐字比對（C4-SF-1）。

為什麼三個必要檢查不會變寬鬆：

- **`checks`**：步驟不變。它跑的 `packaging/validate.py` 只多檢查、沒少檢查：既有的 tags、build-args、IMAGE 逐字比對還在，
  比對的值（`CI_VERSION`、`RELEASE_VERSION`）和 `32ecac8` 逐字相同；另外多三項（讀 app 的運算式只准是產生的那一個、
  證據名稱、Dockerfile 預設值與標籤）。資料錯時只是訊息改成一行，照樣失敗。packaging 測試 184 → 192。改寫的 3 個 packaging
  測試沒有少檢查：寫死的版號值改成讀資料（資料仍由 `validate.py` 綁到 manifest、Dockerfile、`inputs.json`、`PRODUCT_VERSIONS`
  與 workflow），其餘斷言（未知產品被擋、manifest 換成別條版號線的版號被擋、build-args 換成固定版號被擋、只認確切版號）都在；
  刻意改變的只有「共用紀錄不再放行」（readiness 變嚴）。`unit.sh` 不變；pytest 只改兩個檔，案數只增不減（兩個檔 55 → 70）：
  - 期望值讀發版資料 `packaging/inputs.json`，不讀受測的 runtime。`32ecac8` 寫死的兩項獨立檢查（Headscale `0.4.18`、其他
    產品 `VERSION`）改成「每個產品的 `version_for_product()` 等於發版資料」一案，涵蓋 9 個產品；發版資料由 `validate.py` 綁到
    `VERSION_OVERRIDES` 與其他位置。把 runtime 的對應改錯，新測試會失敗（第 3.3 節 PT_A、PT_B）。
  - `32ecac8` 的未設定後端測試不帶 `management`，順帶驗 gateway 沒拿到 `product_version` 時報預設版號。現在的 in-process 測試
    照兩個 launcher 給版號：Python 產品帶，n8n 不帶（`apps/n8n/run.py` 本來就不帶），所以 n8n 的案例驗兩條預設路徑：gateway
    自己回 initialize（版號測試 `[False-n8n]`）與改寫子程式的回覆（`[True-n8n]` 與未設定後端測試的兩個 n8n 案）。拿掉任一條的
    預設值，對應的案例失敗（第 3.3 節 PT_D、PT_E）。
- **`readiness`**：映像檢查不變。發佈紀錄檢查只會更嚴：新規則接受的紀錄一定寫到這個版號（舊規則對非 Headscale 只要求這個）
  也寫到 slug（舊規則對 Headscale 要求這兩個），而且檔名就是那個產品的，所以「新規則接受」是「舊規則接受」的子集。
  已經有正式 Release 的版本照舊跳過。今天的結果不變：Store 啟用的 7 個 add-on 是 6 個 0.4.13（#76 合併）與 Headscale 0.4.18
  （#88 合併），clone 裡有這 7 個 Release 的 tag（`woow_mcp_{odoo,n8n,hermes,emqx,litellm,nextcloud}-v0.4.13`、
  `woow_mcp_headscale-v0.4.18`，`git tag -l`，跟著 clone 下來的；本機沒有查 GitHub API），所以 7 個都走「already released」、
  不看紀錄。6 個 0.4.13 的 add-on 沒有自己的 0.4.13 紀錄（只有共用的 `release-decision-0.4.13.md`），能過完全靠 GitHub 上已有
  正式（非草稿）Release，tag 本身證明不了。所以 PR 的 readiness log 必須是 7 行 `already released`，開 PR 後把那段 log
  放進 PR 說明；有任何一個不是，先釐清那個產品的 Release 狀態或補它自己的紀錄，不放寬規則。Headscale 0.4.18 的紀錄本身就
  符合新規則。
- **`Upgrade comparison / compare`**：是 Store 的共用 workflow（`uses: WOOWTECH/Woow_HA_App_Store/...@main`），這個 job 的
  `uses`、`permissions` 都沒動；本片不改版號，比對照舊幾秒內通過。
- 不是必要檢查但相關的 `release` job：`needs: [checks, readiness]` 與 `if` 都沒動。

多路運算式的前提：它的值靠 GitHub Actions 文件寫的運算子優先序（`&&` 先於 `||`）；`packaging/test_validate.py` 的求值器照
同一個假設寫，所以單元測試證明的是「照文件語意」，不是 GitHub 實跑。今天只有一個 override，兩路寫法在「`&&` 先於 `||`」與
「同級、由左到右」兩種讀法下值都一樣，多路寫法不一樣。`ci.yaml`、`release.yaml` 的建置 job 在 PR 不跑、builder 也不用它們，
第一次真的被 GitHub 求值會是開 `release.yaml` 的時候（第 12 節）。

## 5. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

2026-11-14 實作時跑過一輪；2026-11-15 處理審查意見後重跑，下表是重跑的結果。

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（用另一個裝了 `packaging/requirements-ci.txt` 的 Python，和 CI 一樣） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（根目錄 `.venv`＋`packaging/requirements-ci.txt`，和 CI 一樣 `discover -s packaging`） | `Ran 192`、`OK (skipped=5)`，21 秒。5 個 skip 都是「要 root」，和基準相同（`32ecac8` 是 184 個） |
| `tests/test_unconfigured_connect.py`（in-process 與真 launcher，整檔） | 61 passed、0 skip，24 秒（`32ecac8` 是 46 案） |
| `tests/test_real_products.py`（真子程式，整檔） | 9 passed、0 skip，151 秒 |
| HM-01 的守門測試與會讀 packaging 檔的測試（`test_initialize_identity.py`、`test_secret_precheck.py`、`test_ledger_precheck.py`、`test_tool_inventory.py`、`test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、`test_log_scan.py`，整檔） | 125 passed、0 skip，15 秒（`test_initialize_identity.py` 38、`test_admin_contract_freeze.py` 19、`test_single_profile_golden.py` 17、`test_secret_precheck.py` 14、`test_log_scan.py` 13、`test_mcp_contract_freeze.py` 9、`test_tool_inventory.py` 8、`test_ledger_precheck.py` 7） |
| 整套 pytest 只收集（`--collect-only`，不執行） | 3747 案、0 收集錯誤（審查時 `3166245` 是 3746 案；多的 1 案是新增的那一案） |
| 第 3 節的先紅後綠、升版模擬與變異 | 第 3 節 |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨；`git diff 32ecac8 -- packages apps addons packaging/inputs.json CHANGELOG.md upgrade-notes.yaml` 空白 |

沒跑全套 pytest：本片沒有改執行期檔、共用替身或 conftest；`tests/` 只改兩個檔，兩個都整檔跑過。改過的 `validate.py`、
`test_validate.py`、`release.md`、`release_gate.py` 在 `tests/` 裡只有 `tests/test_initialize_identity.py`（讀 `validate.py` 的
`VERSION = '0.4.13'` 字樣，仍在）和 `tests/test_secret_precheck.py`（用替身載入沒改過的 `supply_chain.py`）碰到，上一列已整檔
跑過；`test_real_products.py` 拿掉了 `VERSION` 的匯入，另外 50 個從它匯入共用函式的測試檔只用 `backend`、`connection`、
`free_port`、`rpc`（都沒改；AST 逐檔查過），整套收集 0 錯誤；tool-surface 的 159 個來源摘要 0 漂移（第 8 節）。全套由 PR 的 CI 跑。

## 6. 只在 CI 跑的測試

- 本片沒有只能在 CI 跑的新測試；改過與新增的測試都在本機（一般使用者）跑過。
- CI 以 root 跑 pytest：兩個改過的檔在 root 下的結果只有 CI 驗得到。改的只有期望的版號值與 launcher 給的選項，不靠執行身分
  判斷，預期相同。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。新的一行訊息測試在 packaging unittest
  那一步跑（那一步的環境有 PyYAML）。
- readiness 對真的 Store registry、GitHub API、GHCR 的檢查（`release_gate.py all`）只在 CI 跑；本機只跑離線的
  `packaging/test_release_gate.py`。7 行 `already released` 要在 PR 的 CI 確認（第 4 節）。
- 全套 pytest（第 5 節最後一段）。

## 7. `checks` 秒數

開 PR 後補（前：`32ecac8`／PR #90 的 run；後：本片 PR 的 run）。推估：packaging 測試多 8 個（本機共約 21 秒），pytest 多
15 案（in-process，約 1 秒），增加遠低於 1 分鐘。

## 8. 預檢結果

兩個預檢都在最終 HEAD（本筆記的 commit）上跑。

- **秘密預檢**（`scripts/secret_precheck.py --base 32ecac8`；gitleaks 8.28.0，用 `secret_precheck.py install --tarball` 從本機已存的
  壓縮檔安裝：壓縮檔 SHA-256 符合 `packaging/scanner-pins.json` 才解出，掃描前再核對執行檔摘要與版號；設定是本 repo 的
  `gitleaks_config()`）：`32ecac8..HEAD` 共 6 個 commit（含本筆記），`result: OK, 0 findings`。
- **帳本預檢**（`scripts/ledger_precheck.py --base 32ecac8`）：`runtime-patches.json` 152 個、`runtime-sources.json` 70 個、
  `tool-surface.json` 159 個，0 漂移、0 缺檔；本片改了 11 個檔，列管檔 0 個、帳本 0 個、新增或改到而沒列管的執行期檔 0 個。
  `result: OK`。`packaging/validate.py`、`release_gate.py`、`docs/operations/release.md` 不在任何帳本。
- **rebase 後重跑**（2026-11-15 07:2x，主對話）：本分支從 `32ecac8` rebase 到 `claude-delivery` `e5e6e74`（HM-00 #89、HM-01 #90、
  HM-04 #91 都已合併），6 個 commit 都沒有衝突，內容沒變。
  - `packaging/validate.py`：PASS。
  - packaging unittest：`Ran 192 tests`、`OK (skipped=5)`（5 個要 root，和基準相同）。
  - 帳本預檢：OK。
  - `scripts/tool_inventory.py` 漂移檢查：exit 0。
  - 秘密預檢：`e5e6e74..HEAD` 的 6 個 commit、`--full`（HEAD 全部檔、全歷史）都 0 命中。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

- 本片是 HA 自己的發版工具，沒有移植 PaaS 程式或測試；PaaS 以 commit＋digest 釘版，沒有對應的程式。
- 主對話 2026-11-15 06:2x 在本機 PaaS git 查過：PaaS main 是 `cf3d0d5`。`69ac425..cf3d0d5` 動到核心模組的只有
  `log_redaction.py`（#149）、`gateway_pool.py`／`proxy.py`（#148 後的註解與文件更正）、`setup_status.py`（移除 VK 的說明文字），
  都和本片無關。

## 10. 本片用到的決策

- DQ-32（2026-11-14 採用建議）：逐產品開關，每個產品各自升到 0.5.0，R2 三個產品合成一個升版 PR。⇒ 版號線會重複，readiness
  不能只比版號字串；R2 的升版 PR 要寫三份紀錄（每個產品一份）。
- DQ-36：commit 不加 AI 署名。
- DQ-33：本機用短的 `/tmp/ha-mp-XXXXXX` 當 TMPDIR，跑完刪除。
- 計畫 §11.2、審查 C4-SF-1（運算式用 `packaging/test_validate.py` 驗、維持已知可用的 `&&`／`||` 寫法、不用 `fromJSON`）、
  C4-SF-2（綁版號測試改讀 `version_for()`）、R10 RG-12（readiness 的盲點）。
- 2026-11-14 21:5x 的四題（DQ-12、DQ-09、DQ-19、DQ-38）本片沒用到。§13.2、§13.3 的題目本片沒碰到：沒改 job 名稱與必要檢查
  （DQ-43）、沒改發佈紀錄要寫的驗收項目（DQ-42）。
- 實作時做的選擇（不是 §13 的題目；請主對話判斷要不要寫進 `decisions.md`）：
  1. 「產品自己的紀錄」＝`docs/operations/release-decision-<add-on>-<version>.md`（`<add-on>` 是 `addons/` 下的目錄名；
     Headscale 的紀錄、計畫 §11.3 的 `release-decision-odoo-0.5.0.md` 都是這個形式），內文寫到 slug 與確切版號。共用紀錄
     （`release-decision-<version>.md`）不再算數。
  2. 運算式的段落依 `PRODUCTS` 順序；沒有 override 時是裸版號；override 等於預設版號、或版號不是 `x.y.z` 時直接拒絕。
  3. `validate.py` 加查 Dockerfile 的 `ARG BUILD_VERSION` 預設值與 `io.hass.version` 標籤（C4-SF-2：漏改要到 builder 才會失敗、
     要重新申請）。
  4. builder workflow 裡讀 app 的運算式只准是產生的那一個，release.yaml 的證據名稱也逐字比對。
  5. `tests/` 的期望版號讀發版資料 `packaging/inputs.json`，不讀受測的 runtime，也不 import `validate.py`（CI 的 pytest 環境在
     `uv sync` 之後沒有 PyYAML）。
  6. in-process 測試照兩個 launcher 給 gateway 版號：Python 產品帶 `version_for_product()`，n8n 不帶，和正式環境一致。
  7. 發版資料錯時，`validate.py` 在載入當下就以一行 `packaging validation failed: …` 停止（`SystemExit`）；不改成到 `validate()`
     才產生運算式，其他工具與測試照舊讀 `CI_VERSION`、`RELEASE_VERSION`。
  8. `VERSION_OVERRIDES` 寫在一行、照 `repr()` 的寫法（7 的測試在暫存複本照這個寫法換掉它）；`docs/operations/release.md` 寫明。

## 11. 驗收條件（計畫 §12.3 HM-17）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR 的 CI（這一波不 push、不開 PR）。本機：`validate.py` PASS、packaging 192 個 OK（5 個要 root 的 skip，同基準）、兩個改過的 pytest 檔 70 案全過、HM-01 守門測試與會讀 packaging 檔的測試 125 案全過（第 5 節） |
| 運算式與 workflow 一致（`packaging/test_validate.py` 單元測試） | 通過：運算式由 `VERSION_OVERRIDES` 產生；獨立的求值器確認兩個 workflow 的每個 app、每個位置都拿到 `version_for(app)`；模擬升版時沒重產的位置逐一被擋 |
| 目前兩個版號照舊 | 通過：0.4.13 與 Headscale 0.4.18 沒動；`addons/`、`apps/`、`packages/`、`inputs.json` 0 差異；產生的運算式和原本逐字相同 |
| `release_gate.py` readiness 只認產品自己的發佈紀錄 | 通過（第 3.1 節）；PR 的 readiness log 要是 7 行 `already released`，開 PR 後確認（第 4 節） |
| 綁版號的測試改讀 `version_for()` | 通過。packaging：讀 `version_for()`（原 `packaging/test_validate.py` 241-242 行）。`tests/`：讀 `packaging/inputs.json`，`validate.py` 把它綁到 `version_for()` 用的 `VERSION`、`VERSION_OVERRIDES`（`tests/` 不能 import `validate.py`：沒有 PyYAML）；原 `tests/test_unconfigured_connect.py` 140、160-161、170 行與 `tests/test_real_products.py` 195 行。期望值不再和受測的 runtime 同源（第 3.3 節）；升版模擬見第 3.2 節 |
| 先寫測試、記下先紅後綠 | 通過（第 3 節） |
| 新測試用 HM-01 的 log 掃描（計畫 §12.0 第 3 點） | 通過：兩個新的 pytest 測試都帶 `log_scan`，版號測試掃 token、child token 與憑證，0 命中。packaging 的 unittest 不適用：`log_scan` 是 pytest fixture，這些測試也不經過 runtime 的 logger |
| 不得條件式 skip | 通過：新測試沒有 skip；packaging 既有的 5 個 `skipUnless(root)` 沒動 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG | 通過 |
| 動到帳本列管的檔就同 PR 更新帳本 | 不適用：沒有改到列管檔（第 8 節） |
| PR 說明寫清楚改了哪些 job 條件、為什麼必要檢查不會變寬鬆 | 內容在第 4 節（job 條件 0 處改動） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：網址用 `.invalid`；版號是公開的版號或合成的 `99.0.0`、`9.9.9`、`1.2.3`、`2.0.x`；token 在測試執行時產生；沒有 commit token、憑證或像金鑰的字串；秘密預檢 0 命中 |

## 12. 還沒解決、交給後面的片

- `checks` 的前後秒數：開 PR 後補。
- readiness：開 PR 後確認 PR 的 readiness log 是 7 行 `already released`，把那段 log 放進 PR 說明（第 4 節）。
- 開 `release.yaml` 的那一片：先在拋棄式 workflow 乾跑一次多路運算式（只印值、不建置），確認 GitHub 實際算出的值和
  `version_for()` 相同（第 4 節最後一段）。
- HM-19a（R1 Odoo 0.5.0）與之後的升版片：照 `docs/operations/release.md`「升版時要改的版號資料」改 7 處資料；紀錄檔名要是
  `release-decision-<add-on>-<版號>.md`，內文寫 `woow_mcp_<add-on>` 和版號；R2 合成一個升版 PR 時三個產品各一份。
- HM-25（n8n 開通）：`apps/n8n/run.py` 沒有傳 `product_version`（Python 產品的 `run_product` 有傳）。n8n 有自己的版號線時，
  它的 `serverInfo` 與管理面板會報預設版號；第 3.2 節的 n8n 升版模擬證實 in-process 與真 launcher 的 n8n 案都會擋。
  修 `run.py` 時要一起改：`tests/test_unconfigured_connect.py` 的 `released()`（n8n 也帶版號），以及照現況寫 n8n 報 `VERSION`
  的 `tests/test_real_n8n.py:107`、`tests/integration_local_runtime.py:161`、HM-01 的 `tests/test_single_profile_golden.py:335`。
  本片不改執行期檔，留給 n8n 的片。
- 本片排在 HM-04、HM-06、HM-07、HM-13a、HM-02 之後送審；rebase 之後，兩個改過的測試檔與 HM-01 的守門測試要重跑（那幾片會改
  gateway 與共用替身）。
- `Hc/features.py`：HM-00 的 `ledger-tracking.md` 寫 HM-17「先」改 `features.py`，但 `32ecac8` 沒有這個檔（HM-07 建立），本片沒碰。
  要不要讓 `validate.py` 把 `MULTI_PROFILE_PRODUCTS` 和版號綁在一起（例如開通的產品版號要 ≥ 0.5.0），請主對話決定，交 HM-07 或
  HM-19a。
- FM-146（Store 要求發佈 commit 上兩個 workflow 都有成功的非 PR run）：HM-00 `deviation-trace.md` 寫「HM-17、升版片」，計畫 §17
  寫 HM-19a、HM-19b。這是升版步驟的確認，本片沒有對應的程式；留給升版片，請主對話對齊兩份文件。
- `decisions.md`：第 10 節的實作選擇（1～8）由主對話同步。

## 13. 審查意見處理

獨立審查判「修正後通過」（必修 3、建議 4）。逐項核對過審查的證據再處理；必修都改了，建議都採用。

| id | 意見（摘要） | 處理 | 驗證 |
|---|---|---|---|
| MF-1 | `tests/` 的期望值讀 runtime 自己的 `version_for_product()`，和受測程式同源：把它改成一律回 `VERSION`，新測試、HM-01 黃金回歸、`validate.py`、packaging 都照過 | 已修。期望值改讀發版資料 `packaging/inputs.json`（`release_version()`，4 處）；`released()` 照舊傳 `version_for_product()`（那是 `run_product` 真的傳的值，n8n 見 MF-2）；新增「每個產品的 `version_for_product()` 等於發版資料」一案。commit 標題改成 `test: read the expected release version from packaging/inputs.json (HM-17)`；第 2、4、11 節改寫。HM-01 的黃金回歸也以 `version_for_product()` 當期望值，本片不改 HM-01 的檔，這個缺口由新案例擋 | 第 3.3 節 PT_A、PT_B；第 3.2 節 Odoo 升版模擬 |
| MF-2 | 改成帶 `product_version` 後，gateway 自己回 initialize 時的預設版號沒人驗（n8n 正式環境會走到）；第 4 節說仍由其他 4 個檔驗，不正確 | 已修。`released()` 照兩個 launcher：n8n 不帶 `product_version`。n8n 的案例驗 gateway 自己回（`[False-n8n]`）與改寫子程式回覆（`[True-n8n]` 與未設定後端測試的兩個 n8n 案）兩條預設路徑。第 4 節改正（原本那句說法拿掉） | 第 3.3 節 PT_D、PT_E |
| MF-3 | 新的 pytest 測試沒用 HM-01 的 `log_scan`（計畫 §12.0 第 3 點） | 已修。兩個新測試都帶 `log_scan`；版號測試開 store 後 `log_scan.watch_state(store.load())`。packaging 的 unittest 不適用（理由見第 11 節） | 第 5 節整檔通過、0 命中 |
| SF-1 | 資料錯時 `validate.py` 在載入時只有 traceback，import 它的工具也一樣 | 採用：載入時把 `Invalid` 轉成 `SystemExit('packaging validation failed: …')`，一行、exit 1；加一個測試（兩種錯誤資料×直接執行與 `import`） | 第 3.1 節（改前 4 個 subTest 失敗、改完通過） |
| SF-2 | 升版時怎麼重產運算式只寫在 provenance，repo 的操作文件沒有 | 採用：`docs/operations/release.md` 加「升版時要改的版號資料」 | 第 2 節 |
| SF-3 | readiness 變嚴後，6 個 0.4.13 的 add-on 能過完全靠 GitHub 上已有正式 Release；本機驗不到 | 採用，開 PR 後做：PR 的 readiness log 必須是 7 行 `already released`，貼進 PR 說明；不是就先釐清 Release 狀態或補那個產品自己的紀錄，不放寬規則。本機只確認 repo 裡沒有這 6 個產品自己的 0.4.13 紀錄、7 個 tag 都在 | 第 4 節、第 12 節 |
| SF-4 | 多路運算式的正確性靠 GitHub 文件的優先序，測試的求值器是同一個假設 | 採用：前提記在第 4 節與 `docs/operations/release.md`；開 `release.yaml` 的那一片先在拋棄式 workflow 乾跑（第 12 節） | — |

審查之外，處理時順手改的三處（都在上面的 commit 裡，行為不變）：

- `validate.py` 的註解列出 import 它的工具時漏了 `pilot_variant.py`（它也在載入時 import `validate`），補上；SF-1 的 commit 訊息同步。
- 一行訊息的測試要先在 `validate.py` 找到 `VERSION_OVERRIDES` 那一行（照 `repr()` 的寫法）；找不到時原本只報 `0 != 1`，
  現在失敗訊息說明要寫在一行。
- `docs/operations/release.md` 第 1 項寫明 `VERSION_OVERRIDES` 要寫在一行、和例子同樣的寫法。

審查的證據與重跑用的腳本在審查代理的暫存區（不在 repo）；本筆記的數字是處理後在同一個 clone 重跑的結果（第 3、5、8 節）。
