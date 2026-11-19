# HA 多帳號 HM-16 追補 provenance：P9 清單產生器認得完整工具表面（2026-11-19）

## 結論

- **現象**：`docs/tool-surface.json` 從 0.2.0（`a52aad0`）起把七個原有產品與 Headscale 標成 `supported-full`，`accepted_schema` 是 null。
  `packaging/p9_plan.py` 只認 `supported-bounded`，所以這八個產品的清單都是 0 個讀取，讀取工具也被列成拒絕
  （`ha-test-0.4.14.md`、`ha-test-headscale-0.4.13.md` 已記下）。2026-11-18 HAOS 試跑用的暫用副本只把這一行改成兩種都收，
  結果需要參數的工具被當成讀取、以 `{}` 送出：Odoo 33 個讀取有 21 個缺必填參數，n8n 另有 8 個讀取屬於寫入全關時整支被拒的工具。
- **修法**（只改 `packaging/p9_plan.py`）：
  - 接受 `supported-full`，`supported-bounded` 照舊（Odoo Manage 的清單逐位元不變）。
  - 完整工具的參數規則取自子程式自己的 inputSchema：打包的 tools/list 快照 `mcp_admin_core/tool_snapshot.py`（只解析、不 import；
    `--snapshot` 可換檔）。必填參數只用 schema 寫明的值（`default`、`enum` 的第一個、`const`）；其他必填參數（id、名稱、數字、清單）
    或快照裡沒有這支工具，就列進 `needs_args`，不再以 `{}` 當讀取送出。
  - 寫入授權是整支工具的工具（effect 不是 read、mixed）每個操作都列進 denials：寫入全關時閘道整支拒絕，讀取操作也一樣
    （`policy.Tool.grants`、`policy.enabled`）。HAOS 上 `n8n_manage_agents` 7 個、`n8n_test_workflow` 1 個讀取就是這樣被拒（`Unknown tool`）。
- **清單格式不變**：`reads`、`denials`、`needs_args`、`tool_surface_sha256` 照舊；另加 `tool_snapshot_sha256`（快照的 sha256）。
  driver 與 probe 只讀 `reads`、`denials`，不受影響。
- **完整工具的拒絕參數照舊只帶操作參數**（和 2026-11-18 HAOS 試跑相同；第 3 節）。
- **測試**：`packaging/test_p9_plan.py` 加 3 個、改 2 個；先紅後綠；8 個突變全抓到（第 4 節）。
- **本機檢查**（第 5 節）：`validate.py` PASS；packaging unittest `Ran 369`、`OK (skipped=5)`；兩個預檢 OK、0 命中。
- **沒處理的**（第 7 節）：只寫在說明文字的條件式必填（n8n 9 個讀取）、後端本身不支援或狀態造成的失敗，產生器看不到，要用 overrides。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-16 追補（計畫 §12.3 HM-16 的 P9 kit；FM-107） |
| 性質 | 只改操作端工具、它的測試與 `ha-p9-kit.md`；不改執行期、`addons/`、版號；`MULTI_PROFILE_PRODUCTS` 維持空的 |
| 分支 | `fix/ha-multiprofile-p9plan-20261119`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `c90b214`（#109 HM-16 的合併） |
| 依據（repo 外） | 2026-11-18 HAOS 試跑的暫用副本 `p9_plan_full.py`（和基準只差狀態那一行）、它產生的 `*.full.json` 清單與試跑紀錄 |

## 2. 改了什麼

| 檔 | 內容 |
|---|---|
| `packaging/p9_plan.py` | 收兩種狀態；完整工具的讀取參數只取快照 inputSchema 寫明的值；整支寫入的工具每個操作都拒絕；`snapshot_schemas()` 解析快照；`--snapshot`；記 `tool_snapshot_sha256`；說明改寫 |
| `packaging/test_p9_plan.py` | 新 3 案：完整工具的讀取與 `needs_args`、整支寫入的工具（有界與完整各一個子案）、CLI 讀快照檔（檔裡的 `raise` 證明沒有 import）；改 2 案：repo 的 tool-surface 每個產品都有讀取、完整工具的讀取帶齊必填參數、effect 規則和寫入授權一致；CLI 記快照摘要 |
| `docs/operations/ha-p9-kit.md` | 「清單（plan）」一節照新規則改寫 |
| 本筆記 | — |

沒改：`ha_p9_driver.mjs`、`ha_p9_probe.py`、`ha_p9_admin.mjs`、`tool_snapshot.py`、`docs/tool-surface.*`、帳本、`tests/`。
`ha-test-0.4.14.md`、`ha-test-headscale-0.4.13.md` 是當時的試跑紀錄，照原樣保留。

## 3. 設計

- **完整工具只用 schema 寫明的值**：有界工具的 `accepted_schema` 是 add-on 自己審過、有上下限的模型，猜 1 或空清單是安全的
  （例如 Odoo Manage 固定 `res.partner`、id 1）。完整工具的 inputSchema 是上游的，必填的整數多半是紀錄 id、清單多半是查詢條件，
  猜的值在真後端常常不存在或沒意義（`read_attachment` id 1、`build_domain` 空清單），讀取會失敗。所以這些列進 `needs_args`，由
  overrides 補真值。
- **操作的分支**：Headscale 的 inputSchema 每個操作是一個 `oneOf` 分支；讀取照分支的必填參數判斷（`headscale_nodes:get` 要
  `node_id`，列 `needs_args`）。子程式的 schema 不收某個讀取操作時，也列 `needs_args`（今天的表面沒有這種）。
- **完整工具的拒絕只帶操作參數**：閘道對完整工具不驗參數，在子程式看到參數前就照寫入授權拒絕（`policy.authorize` 先
  `enabled()`，混合工具再查操作的授權），所以不需要湊符合 schema 的參數。防護失效時，缺必填參數的呼叫會被子程式拒絕
  （回覆是子程式的結果，probe 判失敗），不會用 `p9-denied` 這類佔位值真的建出紀錄（例如 EMQX 的 ban、OpenDesign 的專案）。
  沒有必填參數的寫入工具兩種做法一樣，仍須照試點程序在後端核對前後無變化。
- **整支寫入的判斷**：用 tool-surface 的 effect（不是 read、mixed）。測試另斷言這條規則和每支已支援工具的 `write_grants` 一致
  （整支寫入的授權名稱就是工具名）。

新舊清單（`docs/tool-surface.json` 現況）：

| 產品 | 基準：讀取 | 暫用副本：讀取（缺必填參數／整支寫入） | 本片：讀取／`needs_args`／拒絕 |
|---|---|---|---|
| odoo | 0 | 33（21／0） | 12／21／9 |
| odoo-manage | 5 | 5（0／0） | 5／0／6（不變） |
| hermes | 0 | 12（0／0） | 12／0／22 |
| opendesign | 0 | 12（4／0） | 8／4／4 |
| emqx | 0 | 27（6／0） | 21／6／17 |
| litellm | 0 | 15（5／0） | 10／5／26 |
| nextcloud | 0 | 5（2／0） | 3／2／5 |
| headscale | 0 | 9（3／0） | 6／3／22 |
| n8n | 0 | 37（11／8） | 19／10／52 |

## 4. 先紅後綠

- **紅**（基準 `c90b214` 的產生器）：新與改的 5 案全紅。新介面不存在（`input_schemas`、`snapshot_schemas`、`tool_snapshot_sha256`）；
  行為面另用 repo 外的腳本量第 3 節的表：基準每個完整產品 0 個讀取；暫用副本 52 個讀取缺必填參數、8 個讀取屬於整支寫入的工具。
- **綠**：`test_p9_plan.py` 8 案全過（0.43 秒）。原有 3 案（有界工具）一字未改照樣過。
- **突變**（拋棄式複本，每次只改一處）：只收 `supported-bounded`、完整工具照有界的猜值、整支寫入的讀取操作當讀取、完整工具的拒絕
  照子程式 schema 湊參數、不記快照摘要、import 快照、沒有 schema 時以 `{}` 讀取、不看 `oneOf` 分支：**8 個全抓到**。

## 5. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（PyYAML venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（`discover -s packaging -p 'test_*.py'`） | `Ran 369`、`OK (skipped=5)`，27.9 秒（5 個 `skipUnless(root)`，既有） |
| `tests/test_tool_snapshot.py`（共用鎖；產生器讀的快照和真子程式一致） | 11 passed，60.3 秒 |
| 秘密預檢（`scripts/secret_precheck.py --tools <gitleaks>`） | gitleaks 8.28.0（釘選、驗過）；`c90b214..HEAD`：OK，0 命中 |
| 帳本預檢（`scripts/ledger_precheck.py`） | 0 drift、0 missing；改到的檔沒有列管的、沒有新的執行期檔：OK |

pytest 其他檔沒跑：本片沒有改 `tests/` 與執行期，`tests/` 也沒有測 `packaging/p9_plan.py` 的檔。

## 6. 只在 CI 跑的、`checks` 秒數

- 沒有只在 CI 跑的新測試：packaging unittest 在 CI 的 `unit` job 照同一個指令跑。
- `checks` 秒數：開 PR 後補。本機增量約 0.4 秒（`test_p9_plan.py` 5 案 → 8 案）。

## 7. 沒處理的

1. **只寫在說明文字的條件式必填**：子程式的 inputSchema 沒有 `if`／`then`、`dependentRequired` 這類寫法（快照全查過），
   n8n 的「某個操作才必填」只在說明文字與 handler 裡。下面 9 個讀取仍在 reads；2026-11-18 HAOS 上只帶操作參數時，子程式以參數錯誤
   拒絕（缺 `workflowId`、`versionId`、`query`，或 `Invalid input`）：`n8n_manage_credentials` 的 get、getSchema，
   `n8n_manage_datatable` 的 getTable、getRows，`n8n_manage_folders` 的 get，`n8n_workflow_versions` 的 list、get、diff，
   `search_templates`（預設 keyword 要 `query`）。要用 overrides 補參數。
2. **後端本身的限制**：同一份紀錄裡 `n8n_manage_folders` 的 list 被 n8n 授權擋下（社群版沒有資料夾功能）；Headscale 的
   `headscale_policy` get 回後端 HTTP 500（照清單順序對到 get）。這兩個和參數無關，照實記錄。
3. 下一次 HAOS P9 回歸要用新產生器重產清單，並照上兩點準備 overrides；要用主機的步驟照既有規定先取得負責人同意。
