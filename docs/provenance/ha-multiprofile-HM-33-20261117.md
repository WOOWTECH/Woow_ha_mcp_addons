# HA 多帳號 HM-33 provenance：對齊 PaaS #156，Hermes 排程工具 `hermes_cron` 的說明補 enabled=false 與 trigger 的實際行為（2026-11-17）

## 結論

- **做了什麼**：`apps/hermes/vendor/hermes_mcp_server/server.py` 的 `hermes_cron` 說明照 PaaS #156（woow-mcp-server `34769c2`，合併 `48f394d`）
  逐字補兩句，docstring 的換行也一樣：
  - create：`enabled=false creates it paused, so it does not run until resumed`
  - trigger：`Hermes v0.22.x also resumes a paused job when it is triggered; call pause afterwards if it should stay paused`
  - 不改版號、不碰 `addons/`、`MULTI_PROFILE_PRODUCTS` 維持空的。
- **程式行為不變**（第 5 節）：去掉 docstring 後，`server.py` 的語法樹和基準 `7646f0f` 相同；編譯後 58 個 code object 只有 `hermes_cron` 的
  第一個常數（說明本身）不同。改過的說明和 PaaS `34769c2` 的逐字相同。PaaS 自己的說法（`7087280` → `34769c2` 去掉 docstring 後語法樹相同）
  用同一支腳本重算也成立。反向對照：把 `"paused": not enabled` 改成 `"paused": enabled`，腳本會抓到（exit 1）。
- **說明和程式一致**（第 7 節）：`claude-delivery` 的 create 在同一個 POST 同時送 `paused`（`not enabled`）與 `enabled`（PaaS #138）。
  這是 PR #85（`b50f1c7`，2026-11-12 合併）的行為，**還沒發版**：發行的 Hermes 0.4.13 只送 `enabled`，下一版才出去（審查 MF-1、S-2）。
  trigger 只送一個 `POST /api/cron/jobs/<id>/trigger`，子程式不會自己再 pause 或 resume，所以「要維持停用，之後要再呼叫 pause」對 HA 也成立；
  審查後由新測試守（S-1）。
- **用戶端看到的變化**（第 6 節）：只有 `hermes_cron` 的 `description` 多這兩句：8081 的 tools/list（子程式自己的、閘道轉回的、閘道自答的都一樣；
  整個回答多 187 個位元組），以及 8099 `/api/capabilities` 工具目錄的同一個欄位（管理面板的工具頁）。工具名稱、輸入與輸出 schema、
  annotations、寫入權限、tools/call 都逐位元不變。這就是使用者選項說明寫的代價。這些只說本片：同一個 Hermes 下一版另帶 PR #85 的
  create 請求改變（多送 `paused`），CHANGELOG 另記一行（第 13 節）。
- **跟著改的工具表面、帳本與釘選**（第 4、6 節；都照檔手改、照檔重算 SHA-256，沒用 `tool_inventory.py --write`，也沒用
  `WOOW_WRITE_TOOL_SNAPSHOT=1` 重產）。任務列的三處：`runtime-sources.json`、`tool-surface.json`、`test_output_schemas.py`。照規則另外要改的四處：
  - `tool_snapshot.py`：閘道內附的工具清單。`tests/test_tool_snapshot.py` 要它等於真子程式。
  - `runtime-patches.json`：`tool_snapshot.py` 的摘要，以及 `n8n_arguments.py` 的 `guarded_sources` 裡同一個摘要。
  - `tool-surface.json`：`hermes_webhook` 的行號 1161 → 1164（說明多 3 行）。
  - `tests/test_single_profile_golden.py`：HM-01 黃金回歸的 Hermes `LISTING_SHA256`、`LISTED_SHA256`。測試檔頭的規則是：刻意的工具表面變更
    時兩個一起更新。新的回答就是舊的回答只換掉這段說明（逐位元核對過）。
- **測試**（第 8 節）：新 `tests/test_hermes_cron_description.py`（3 案，跑在 HM-01 的 log 掃描下）。
  - 說明的 2 案：先紅（`67530b9`＝基準＋新測試：2 案都紅在 `description == PAAS`），後綠（`2952ebe` 起 2 案過）。
  - 審查 S-1 加的 trigger 一案（`80ab565`）：真子程式、假 dashboard，trigger 只送一個 POST。在拋棄式複本做 5 個突變（trigger 後自己再 pause、
    再 resume、送兩次、trigger 前先 pause、trigger 後讀一次排程），每個都讓它紅；沒突變的對照組與 clone 本身都過。
- **檢查**（第 9、11 節）：相關 38 個檔 1,158 案全過、0 skip、0 失敗（新檔、工具表面、output schema、Hermes 13 檔、expansion 6 檔、HM-01 黃金回歸
  與兩個契約凍結、真子程式）。審查後的修正輪再跑 27 個檔 551 案全過（第 9.1 節）。`tool_inventory.py` exit 0、`validate.py` PASS、兩個預檢 OK、
  雙向控制字元 0 個。
- **交發版片**（第 13 節）：Hermes 下一版 `addons/hermes/CHANGELOG.md` 的兩行英文建議稿（HM-33 一行；PR #85 一行，審查 MF-1），
  以及 PaaS README 安裝前提那句的英文原文。HA 的 `apps/hermes/` 底下沒有 README，`addons/hermes/` 的 README 也沒有安裝前提段落，
  所以本片沒有可補的 README。
- **獨立審查：修正後通過**（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-33.md`；必修 2、建議 4，沒有要使用者決定的題）。
  每項怎麼處理見第 17 節。
- **還沒做**（第 15 節）：開 PR 後補 `checks` 秒數。HM-32（#113）已合併；HM-12 面板（#114）會先合，之後由主對話把本片 rebase 到當時的
  `claude-delivery` 再開 PR。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-33（計畫 §12.3，2026-11-17 新增；風險低、工作量 S；FEATURE-MATRIX FM-156） |
| 性質 | 不受開關管（契約第 1.2 節）；只改文字；`MULTI_PROFILE_PRODUCTS` 維持空的 |
| 分支 | `docs/ha-hermes-cron-trigger-paused-20261117`（一般 clone，不是 worktree；只 commit，沒 push、沒開 PR） |
| 基準 | `claude-delivery` `7646f0f`（#110 HM-12 的合併） |
| 決策 | 使用者 2026-11-17 06:3x「現在就補」（第 2 節原文；`docs/multi-profile/decisions.md` 第 1.1 節） |
| 對齊的 PaaS | `woow-mcp-server` main `48f394d`（本機唯讀 repo，沒 fetch、沒 checkout、沒寫入）：#156 `34769c2`（合併 `48f394d`，`34769c2` 的父 commit 是 `7087280`） |
| 套件（都沒動，`uv.lock` 未改） | Hermes venv：mcp 2.3.0、pydantic 2.14.1、httpx 0.28.1；根目錄 pytest 8.4.2；CPython 3.13.15（本機）／3.13.16（CI） |
| 證據目錄（repo 外） | `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-33/`（腳本 `tools/`、比對輸入 `inputs/`、結果 `logs/`） |
| 獨立審查 | 修正後通過（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-33.md`，審查 head `5f2db2b`；必修 2、建議 4，沒有要使用者決定的題）。處理表在第 17 節；修正輪的證據在 `evidence-HM-33/fix/` |

## 2. 使用者的決定（原文）

2026-11-17 06:3x 使用者選「現在就補」，選項說明原文：

> 開一個只改說明的小 PR，做法同 HM-32：不改版號，Hermes 工具說明照 PaaS 補兩句，帳本與工具表面的摘要照規則重算。CI 綠就合併，Hermes 下一版帶出去，CHANGELOG 記一行。代價：Hermes 下一版的工具說明會變（用戶端看到的文字多兩句），程式行為不變。

本片怎麼照做：

| 決定的項目 | 本片 |
|---|---|
| 只改說明的小 PR，做法同 HM-32 | commit 的切法同 HM-32：測試（先紅）→ 修正＋帳本 → 契約與決策文件 → 本筆記 |
| 不改版號 | 沒改任何版號，沒碰 `addons/` |
| 說明照 PaaS 補兩句 | 逐字，換行也一樣（第 3、5 節） |
| 帳本與工具表面的摘要照規則重算 | 第 4、6 節：七個檔、十處摘要或行號，都照檔重算 |
| CI 綠就合併 | 交主對話（本片只 commit） |
| Hermes 下一版帶出去 | 不受開關管，跟著 Hermes 下一版的映像出去 |
| CHANGELOG 記一行 | 第 13 節 HM-33 一行的英文建議稿，交發版片（CHANGELOG 在 `addons/` 底下）。審查 MF-1 後另附 PR #85 一行：同一個 Hermes 下一版的 create 請求會變，照既有規則（單帳號行為改變寫進該產品下一版 CHANGELOG）補記，不是新題目 |
| 代價：用戶端看到的文字多兩句 | 第 6 節：8081 tools/list 與 8099 工具目錄的 `hermes_cron` 說明 |
| 程式行為不變 | 第 5 節語法樹與編譯結果的比對 |

## 3. PaaS 對照（本機唯讀 PaaS repo；`origin/main`＝`48f394d`）

`git log --oneline 7087280..origin/main`：

```
48f394d Merge pull request '⛔ 勿代 merge｜待安全及平台覆核 — docs: Hermes 排程工具說明補上 enabled=false 與 trigger 的實際行為' (#156) …
34769c2 docs: Hermes 排程工具說明補上 enabled=false 與 trigger 的實際行為
```

`7087280` 以前的變動由 HM-32 筆記第 4 節核對過（`69ac425..7087280`）；`7087280..48f394d` 只有 `34769c2` 動到 `apps/hermes`。

| PaaS `34769c2` 的檔 | PaaS 改了什麼 | HA 本片 |
|---|---|---|
| `apps/hermes/hermes_mcp_server/server.py` | `hermes_cron` 的 docstring：create 那行補一句（多 1 行）、trigger 那行補一句（多 2 行） | `apps/hermes/vendor/hermes_mcp_server/server.py` 同一段逐字照改。PaaS 第 974～988 行與 HA 第 1024～1038 行 `diff` 完全相同 |
| `apps/hermes/README.md` | 安裝前提 `Hermes Agent v0.17.0` → `Hermes Agent v0.17.0 or v0.22.x (production runs v0.22.5)` | HA 的 `apps/hermes/` 底下沒有 README。`addons/hermes/README.md` 沒有安裝前提段落，最接近的是 `addons/hermes/DOCS.md` 的「需確認 gateway/dashboard 版本與實際 port」。都在 `addons/` 底下，不碰；英文原文交發版片（第 13 節） |
| `apps/hermes/CHANGELOG.md` | `[Unreleased] - 2026-11-17` 一段（繁中，原文見下） | `addons/hermes/CHANGELOG.md` 不碰；英文一行交發版片（第 13 節） |
| — | PaaS 沒有閘道內附的工具清單、黃金回歸摘要、帳本 | HA 另外要改 `tool_snapshot.py`、`runtime-sources.json`、`runtime-patches.json`、`tool-surface.json`、`test_output_schemas.py`、`test_single_profile_golden.py`（第 4、6 節） |
| — | 沒加測試（commit 說明：`apps/hermes` 測試 151 passed） | HA 另加 `tests/test_hermes_cron_description.py`（第 8 節） |

PaaS CHANGELOG 那段原文（參考；HA 的 CHANGELOG 用英文，第 13 節）：

```
## [Unreleased] - 2026-11-17

### Changed（排程說明，只改文字、行為不變）
- `hermes_cron` 的工具說明補上兩件事：
  - `enabled=false` 會建成停用的排程。#138 起，建立時同時送 `paused`；目前的 Hermes 只認這個欄位。
  - Hermes v0.22.x 對停用的排程執行 `trigger` 時，會一併把它改回啟用；要維持停用，需要之後再呼叫 `pause`。
- 第二點是 2026-11-16 用真 Hermes Agent v0.22.5（和正式站同一個映像）實測確認的。不經 MCP、直接呼叫 Agent API 也一樣，屬於上游行為。
- README 的安裝前提標明正式站使用 v0.22.5。
```

## 4. 改了什麼、沒改什麼

| 檔 | 內容 | 為什麼要改 |
|---|---|---|
| `apps/hermes/vendor/hermes_mcp_server/server.py` | `hermes_cron` 的 docstring 補兩句（+5／−2 行）；SHA-256 `922ff27d…` → `e21dbca5507b03a5c124fc238020c308dabaf2c826b5ecfecff0f125c74f38b0` | 本片 |
| `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` | `LISTED['hermes']` 裡 `hermes_cron` 的 `description`（+5／−2 行）；`0270329c…` → `72ff46ca1ec9634b662f6781cc66c1cce42feab836a34fc9fb90c4ea100db7f7` | 沒有子程式能回答時，閘道用它回 tools/list；`tests/test_tool_snapshot.py` 要它等於真子程式 |
| `docs/provenance/runtime-sources.json` | Hermes `server.py` 那筆的 `local_sha256` 與 `modification`（補 HM-33 一句） | vendored 檔的帳本 |
| `docs/provenance/runtime-patches.json` | `tool_snapshot.py` 那筆的 `sha256` 與 `change`；`n8n_arguments.py` 那筆 `guarded_sources` 裡 `tool_snapshot.py` 的摘要與 `change`（`n8n_arguments.py` 本身沒改，n8n 的列逐位元相同） | 兩處都列管 `tool_snapshot.py` |
| `docs/tool-surface.json` | `source_digests` 裡 `server.py` 的摘要；`hermes_webhook` 的 `line` 1161 → 1164 | `scripts/tool_inventory.py` 記每個工具 `def` 的行號，說明多 3 行，排在後面的 `hermes_webhook` 跟著移；`hermes_cron` 自己的 `def` 在 1016 行沒動 |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES` 裡 `server.py` 的目前位元組，加一行註解 | `output_schemas.json` 記的是來源 commit `c7baac6` 的位元組，之後改過的檔另釘目前位元組（輸入、輸出 schema 與 handler 都沒變） |
| `tests/test_single_profile_golden.py` | Hermes 的 `LISTING_SHA256` `2430f369…` → `326ec974c2abbe8fc59c95975f38de6c11354f0e1e74a085525b7cfc66428111`、`LISTED_SHA256` `8461b58e…` → `a8f5083fe3e19d8583513cffca632b602755eece9c8ee0e087caeeb255bc09d9`，加註解 | HM-01 的規則：刻意的工具表面變更，兩個一起更新（第 6.2 節） |
| `tests/test_hermes_cron_description.py`（新） | 3 案（第 8 節；第 3 案是審查 S-1 加的 trigger） | 計畫 §12.3 HM-33 的測試；審查 S-1 |
| `docs/multi-profile/contract.md` | 第 1.2 節「不受開關管」清單加一項，另加一段（照 HM-32、HM-09 追補的寫法）；第 10 節一列。第 9 節不加列：說明和 PaaS 一致 | 契約 |
| `docs/multi-profile/decisions.md` | 第 1.1 節一列（使用者 2026-11-17 06:3x，選項說明原文）；第 5 節一列；DQ 題數不變 | 決策紀錄 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表在 HM-31 的列後面加新檔 | 驗收矩陣 |
| 本筆記 | — | — |

沒改：
- 任何版號、`addons/`（README、DOCS、CHANGELOG、`upgrade-notes.yaml`）、`.github/`、`tests/conftest.py`、`features.py`（`MULTI_PROFILE_PRODUCTS` 照舊是空的）。
- `uv.lock`、`packaging/`、`docs/tool-surface.md`（`tool_inventory.py` 的 markdown 比對照過）。
- `docs/provenance/six-runtimes.md`（本地修改的檔數不變：`server.py` 本來就是本地修改過的檔）。
- `packages/mcp-admin-core/mcp_admin_core/output_schemas.json`（Hermes 11 個輸出 schema 的釘選與 `c7baac6` 的來源位元組都不變）。
- `docs/multi-profile/ledger-tracking.md`（沒有新模組、沒有新列管檔）、`paas-test-mapping.md`、`deviation-trace.md`（repo 外的產生器重產，不手改）。

## 5. 語法樹比對（程式行為不變）

腳本 `evidence-HM-33/tools/ast_compare.py`（只讀；用 `.venv/bin/python -I` 跑，CPython 3.13.15）：
- 語法樹：兩個檔各自去掉模組、每個 class 與每個函式的 docstring（第一個敘述是字串常數就拿掉），比 `ast.dump`（不含行號與欄號）。
- 編譯結果：兩個原始檔各自 `compile()`，同樣順序走過每個 code object，逐欄比 `co_code`、`co_names`、`co_varnames`、`co_freevars`、`co_cellvars`、
  `co_flags`、參數個數與每個常數（行號表不比：加了行，後面的行號一定會移）。每個不同處列成（code object、欄位、常數位置）。
- 改過的 docstring 和第三個檔（PaaS）的同一個函式比。

| 比對 | 前 → 後（SHA-256） | 去掉 docstring 後的語法樹 | 編譯結果的差異 | 改過的 docstring |
|---|---|---|---|---|
| HA：`7646f0f` → 本片 | `922ff27d…` → `e21dbca5…` | **相同**（兩邊都是 `67c4d659…`） | 58／58 個 code object，只有 `hermes_cron` 的 `co_consts[0]`（說明本身） | 只有 `hermes_cron`；和 PaaS `34769c2` 的**逐字相同** |
| PaaS：`7087280` → `34769c2`（重算 PaaS 的說法） | `c0f02df0…` → `8173e222…` | **相同**（`b29dc976…`） | 52／52，只有 `hermes_cron` 的 `co_consts[0]` | 只有 `hermes_cron` |
| 反向對照：本片的檔把 `"paused": not enabled` 改成 `"paused": enabled` | — | **不同** | `hermes_cron` 的 `co_code` 與 `co_consts[0]` | — |

結果檔：`logs/ast-compare-ha.json`、`logs/ast-compare-paas.json`、`logs/ast-compare-negative-control.json`；比對的輸入在 `inputs/`
（`git show 7646f0f:…`、PaaS 唯讀 repo 的 `git show 34769c2^:…`、`git show 34769c2:…`）。

另外，`git diff 7646f0f..HEAD -- apps/hermes/vendor/hermes_mcp_server/server.py` 只動 docstring：刪 2 行、加 5 行，沒有別的行。

**為什麼不做成常駐測試**：計畫 §12.3 列的「去掉說明後語法樹和基準相同」是這次改動的證明，本片照任務說明實際比對、結果寫在這裡（PaaS #156 也是這樣做）。
做成常駐測試就得把 `server.py` 去掉說明後的樣子釘在某個 commit，以後任何正當的程式修改都要改它；`server.py` 的位元組已經由
`runtime-sources.json`、`tool-surface.json`、`test_output_schemas.py` 三處釘住，任何改動都會被看到。常駐的是說明本身的釘選（第 8 節）。

## 6. 工具清單、HM-01 黃金摘要與帳本

### 6.1 閘道內附的工具清單（`tool_snapshot.py`）

- 檔頭寫「由 `tests/test_tool_snapshot.py` 從真子程式產生，不要手改」；本片的規則是不用批次重寫。做法：照產生器的格式手改那兩行
  （`pprint.pformat(..., width=120, sort_dicts=False)`），再核對兩件事（腳本 `tools/snapshot_check.py`，只讀、不 import，`ast.literal_eval`）：
  - 檔案和產生器 `write_snapshot` 對這份 `LISTED` 會寫出的位元組**完全相同**（`HEADER` 取自 `tests/test_tool_snapshot.py`）。
  - 和基準的 `LISTED` 比，8 個產品、各自的工具數（41、28、11、15、39、40、9、11）都相同，不同的只有一處：`/hermes[hermes_cron]/description`。
- `tests/test_tool_snapshot.py` 11 案全過：8 個產品的真子程式（假後端）列出的工具都等於這份清單，Hermes 也是；閘道自答的回答等於轉回的回答。
- 結果檔：`logs/snapshot-check.json`。

### 6.2 HM-01 黃金回歸的兩個 tools/list 摘要

- `tests/test_single_profile_golden.py` 檔頭：工具清單改了（`tool_snapshot.py` 重產）就是刻意的工具表面變更，要檢查新的回答，並把該產品的
  `LISTING_SHA256` 與 `LISTED_SHA256` 一起更新。本片照做。
- 檢查新的回答（腳本 `tools/listed_answer.py`：用黃金回歸自己的 `production_runtime`，真的 `run_product` runtime、MockChild、不起程序、
  不開 socket、不連網；Hermes 的兩種狀態 × 兩條連線路徑）：
  - 用基準的清單跑，算出的兩個摘要等於 `7646f0f` 釘的值（`2430f369…`、`8461b58e…`），harness 有效。
  - 用本片的清單跑：`LISTING_SHA256` `326ec974c2abbe8fc59c95975f38de6c11354f0e1e74a085525b7cfc66428111`、`LISTED_SHA256`
    `a8f5083fe3e19d8583513cffca632b602755eece9c8ee0e087caeeb255bc09d9`；兩種狀態、兩條路徑的回答相同。
  - 新的回答**就是舊的回答只把 `hermes_cron` 的說明換掉**：舊回答裡舊說明（JSON 編碼後）出現 1 次，換成新說明後和新回答逐位元相同；
    解析後比也相同。回答 8,461 → 8,648 位元組（+187：說明多 184 個字元，加上 3 個 `\n` 跳脫各多 1）。
- 結果檔：`logs/listed-answer.json`。之後 `tests/test_single_profile_golden.py` 17 案全過。
- 兩個契約凍結（`tests/test_mcp_contract_freeze.py` 9 案、`tests/test_admin_contract_freeze.py` 19 案）沒改，照過。

### 6.3 帳本與其他釘選

- `runtime-sources.json`：`server.py` 的 `local_sha256` 改成 `e21dbca5…`；`modification` 尾端補一句 HM-33（PaaS #156 `34769c2`、兩句的內容、只改文字、
  去掉 docstring 後語法樹相同、測試檔名）。`source`、`upstream_sha256` 照舊（不是重新 vendor）。
- `runtime-patches.json`：`tool_snapshot.py` 那筆 `sha256` 改成 `72ff46ca…`，`change` 補一句（只有 `hermes_cron` 的說明改、其他七個產品與 Hermes 其他
  欄位逐位元相同、照產生器格式手改並核對過）；`n8n_arguments.py` 那筆 `guarded_sources` 的同一個摘要改成 `72ff46ca…`，`change` 補「只是帳本摘要，
  `n8n_arguments.py` 沒改、它讀的 n8n 列逐位元相同」（照之前幾次的寫法）。
- `tool-surface.json`：`source_digests` 裡 `server.py` 改成 `e21dbca5…`；`hermes_webhook` 的 `line` 1161 → 1164。`scripts/tool_inventory.py`（不帶
  `--write`）exit 0：`build()` 和 `tool-surface.json` 相同、`tool-surface.md` 也相同。
- `test_output_schemas.py`：`CURRENT_POST_SOURCE_BYTES` 裡 `server.py` 改成 `e21dbca5…`，上面加一行註解（HM-33：說明多 PaaS #156 的兩句，輸入、
  輸出 schema 與 handler 不變）。189 案全過。

## 7. 說明和程式一致（#138 與 trigger）

- create（`server.py` 1077～1080 行）：`client.post("/api/cron/jobs", json={..., "paused": not enabled, "enabled": enabled}, ...)`，一個 POST，
  `enabled=false` 就送 `paused: true`。`tests/test_hermes_cron_paused_contract.py`（真的 Hermes 子程式、假 dashboard）4 案全過：停用、啟用、
  預設啟用三種 create 送的內容，以及嚴格後端回 422 時不拿掉 `paused` 重送。
  - **這是 PR #85 的行為，還沒發版**（審查 MF-1、S-2）：#85（`b50f1c7`，合併 `b68e437`，2026-11-12）不在 0.4.13 裡。0.4.13 的升版 commit
    `1cbfcb9` 與映像來源 `4966f40`（`docs/provenance/release-0.4.13-images.json`）都不含 `b50f1c7`，那時的 `server.py` 只送 `"enabled": enabled`。
    照 PaaS #138 的說明，現在的 Hermes 只看 `paused`，所以 0.4.13 帶 `enabled=false` 建的排程其實是啟用的，下一版才修好。
    `addons/hermes/CHANGELOG.md` 也還沒有 #85 的一行，第 13 節補一行交發版片。
- `enabled` 參數：輸入 schema 照舊是 `{"default": true, "title": "Enabled", "type": "boolean"}`（新測試也釘住），排程預設會跑，帶 `false` 才停用。
- trigger（`server.py` 1134～1138 行）：只送一個 `POST /api/cron/jobs/<id>/trigger`，回 `{"ok": true, "triggered": <id>}`；子程式不會在 trigger 前後
  自己呼叫 pause 或 resume。所以「要維持停用，之後要再呼叫 pause」對 HA 也成立。審查前只靠讀程式；審查 S-1 後由新測試的第 3 案守（第 8 節）。
  - 補充（審查第 3.3 節）：dashboard 回 401 時，`_relogin_on_401` 重新登入後把同一個 POST 再送一次；第一次已被拒、沒執行，實際生效的 trigger
    仍是一次，和 PaaS 相同。
- trigger 會把停用的排程改回啟用，是 Hermes v0.22.x 的上游行為（PaaS 2026-11-16 用真 Hermes Agent v0.22.5 實測，直接呼叫 Agent API 也一樣）。
  本片照規則不連任何實機，HA 這邊沒有另外實測（第 15 節）。說明寫的是「v0.22.x」，接其他版本 Hermes 的用戶看得出適用範圍。

## 8. 測試（先紅後綠）

新 `tests/test_hermes_cron_description.py`（照 `tests/test_n8n_delete_workflow_description.py`、`tests/test_odoo_write_descriptions.py` 的寫法；
`pytestmark` 用 HM-01 的 `log_scan`）：

| 測試 | 內容 |
|---|---|
| `test_the_child_lists_the_paas_text` | 在 `apps/hermes/.venv`（CI 由 `packaging/unit.sh` 裝）裡 import 釘版的子程式（`PYTHONPATH` 照 `products.child_spec`），取 `mcp.list_tools()` 裡 `hermes_cron` 的說明與輸入 schema；import 不發任何請求 |
| `test_the_gateways_packaged_listing_carries_the_same_text` | 閘道內附的清單 `LISTED['hermes']` 的同一個工具 |
| `test_trigger_is_one_post_and_never_pauses_or_resumes_by_itself`（審查 S-1，`80ab565`） | 照 `tests/test_hermes_cron_paused_contract.py` 的寫法：真的 Hermes 子程式、假 dashboard 記下收到的每個請求（不分方法）。trigger 一次，回 `{"ok": true, "triggered": "synthetic-job"}`；dashboard 只收到 `POST /auth/password-login` 與 `POST /api/cron/jobs/synthetic-job/trigger` |

說明的兩案都斷言：說明逐字等於 PaaS `34769c2` 的（`PAAS`，含換行）；兩句（去掉換行後）各出現一次；把兩句的補充拿掉就等於原本的說明（`BEFORE`，
`7646f0f`；其他字都沒變）；`enabled` 照舊是預設 true 的布林。

| 輪 | 程式 | 結果 | 證據 |
|---|---|---|---|
| 紅（`67530b9`＝`7646f0f`＋新測試） | 修正前 | 2 failed（1.36 秒），兩案都紅在 `assert description == PAAS`（子程式與內附清單都還是原本的說明） | `logs/red-tests-only-7646f0f.txt` |
| 綠（`2952ebe` 起） | 修正後 | 2 passed（子程式那案約 1.3 秒，清單那案 1 ms 以內） | `logs/related.txt`、`logs/related.junit.xml` |
| trigger 那案（`80ab565`；程式本來就對，所以用突變證明它會紅） | 拋棄式複本（`git clone --no-hardlinks` 自本 clone，連到 clone 的 venv；只改複本的 `server.py`，每次 `git checkout` 還原並確認乾淨） | 沒突變的對照組 1 passed；5 個突變都 1 failed，每個都紅在 `events ==`：trigger 後自己再 pause（多一個 `/pause`）、再 resume（多一個 `/resume`）、送兩次 trigger、trigger 前先 pause（第 2 個請求變成 `/pause`）、trigger 後讀一次排程（多一個 GET）。clone 本身 3 passed | `fix/trigger-mutations.json`（`tools/trigger_mutations.py`）、`fix/new-tests-clone.txt` |

## 9. 本機檢查（2026-11-17，一般使用者 uid 1000；AMD EPYC 7713、CPython 3.13.15；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排在共用鎖後面）

| 檢查 | 結果 | 證據 |
|---|---|---|
| 新測試：紅、綠 | 第 8 節 | `logs/red-tests-only-7646f0f.txt`、`logs/related.txt` |
| 相關測試（工作樹＝`2952ebe` 的內容；正式 conftest、0 skip） | **38 個檔 1,158 案全過**、0 失敗、0 skip，576 秒。junit 記 1,160 筆：新檔因為同時寫了檔名與 `tests/test_hermes_*.py`，被收了兩次 | `logs/related.txt`、`logs/related.junit.xml` |
| 其中 | 新檔 2；工具表面 `test_tool_snapshot` 11（8 個真子程式）、`test_tool_inventory` 8、`test_full_surface` 28、`test_tool_metadata` 17、`test_declared_schemas` 57、`test_unconfigured_connect` 61；output schema `test_output_schemas` 189、`test_output_schema_runtime` 20；HM-01 黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19；`test_ledger_precheck` 8；Hermes 13 檔 99（不含新檔；含 `test_hermes_cron_paused_contract` 4）、`test_tool_error_text` 5；expansion 6 檔 154；`test_real_products` 9（真子程式）；`test_migration_preview` 226、`test_owner_defaults` 139、`test_writes_default_on` 43、`test_upgrade_zero_rewrite` 37 | 同上 |
| `scripts/tool_inventory.py` | exit 0（0 漂移；`tool-surface.md` 相同） | `logs/tool-inventory.txt`、`logs/validate-inventory-c22cc88.txt` |
| `packaging/validate.py`（ci-venv 的 Python） | PASS | `logs/validate-inventory-c22cc88.txt` |
| 雙向控制字元（U+202A～U+202E、U+2066～U+2069） | 改到的 11 個檔、前 3 個 commit 的訊息：0 個（本筆記與本 commit 的訊息另掃，結果在交回主對話的回報與 PR 說明草稿） | `logs/bidi-check-c22cc88.txt`（`tools/bidi_check.py`） |
| commit 身分與署名 | 作者、提交者都是 woowtech；commit 訊息沒有 AI 署名 | `git log` |

本機一定失敗的既有 7 案（要 root：`test_owned_executable` 的 uid10001、`test_profile_store::test_mode_and_owner_as_the_add_on_user`、
`test_restore_detection` 的 `test_root_*` ×5）不在上面這些檔裡，本片沒跑全套。

### 9.1 審查後的修正輪（2026-11-17 07:3x～07:4x；證據在 `evidence-HM-33/fix/`）

本輪只加 trigger 一案、改測試檔頭與文件（`apps/`、帳本、其他測試都沒動），所以重跑新測試、Hermes 相關、工具表面、output schema、
黃金回歸與兩個契約凍結；第 9 節那次的 38 個檔涵蓋其他部分，CI 照常全跑。

| 檢查 | 結果 | 證據 |
|---|---|---|
| 新測試（clone，`80ab565` 的內容） | 3 passed（3.9 秒） | `fix/new-tests-clone.txt` |
| trigger 那案的突變（拋棄式複本，用完以完整路徑刪除） | 對照組過；5 個突變都紅（第 8 節） | `fix/trigger-mutations.json` |
| 相關測試（工作樹＝`c3d5bcf` 的內容；正式 conftest、排在共用鎖後面） | **27 個檔 551 案全過**、0 失敗、0 skip，372 秒：新檔 3；Hermes 13 檔 99；`test_tool_error_text` 5；`test_tool_snapshot` 11（8 個真子程式）、`test_tool_inventory` 8、`test_full_surface` 28、`test_tool_metadata` 17、`test_declared_schemas` 57、`test_unconfigured_connect` 61；`test_output_schemas` 189、`test_output_schema_runtime` 20；HM-01 黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19；`test_ledger_precheck` 8 | `fix/related-fix.txt`、`fix/related-fix.junit.xml` |
| `scripts/tool_inventory.py` | exit 0 | `fix/validate-inventory-c3d5bcf.txt` |
| `packaging/validate.py`（ci-venv 的 Python） | PASS | 同上 |
| 雙向控制字元 | 改到的檔、本輪之前的 commit 訊息：0 個（本 commit 另掃，結果在交回主對話的回報與 PR 說明草稿） | 交回的回報 |

## 10. 只在 CI 跑的測試、`checks` 秒數

- 全套 pytest 交 CI（root、0 skip；任務規則：本機只跑相關的）。要 root 的 7 案、瀏覽器測試只在 CI 跑；本片沒動它們測的東西。
- 新測試在 CI：root 下照樣跑（不依賴 uid、不開 port、不連網），用 `packaging/unit.sh` 裝的 `apps/hermes/.venv`；本機約 1.3 秒，對 `checks` 的影響可以忽略。
- `checks` 秒數：開 PR 後補（前：`claude-delivery` 最近一次 PR run；後：本片 PR）。

## 11. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 7646f0f --head HEAD --full` | `c22cc88`（前 3 個 commit＋HEAD 整棵樹＋整個歷史；gitleaks 8.28.0 釘版已驗）：`result: OK, 0 findings`。加上本筆記的 commit 後重跑的結果寫在交回主對話的回報與 PR 說明草稿（筆記記不到自己那個 commit） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 7646f0f` | `c22cc88`：`result: OK`。`runtime-patches.json` 176 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的 2 個列管檔（`server.py`、`tool_snapshot.py`）都有帳本更新；沒有未列管的執行期檔 |
| `packaging/validate.py` | ci-venv 的 Python | PASS |
| 秘密預檢（修正輪） | 同第一列 | `c3d5bcf`（6 個 commit＋HEAD 整棵樹＋整個歷史）：`result: OK, 0 findings`。加上本 commit 後重跑的結果寫在交回的回報與 PR 說明草稿 |
| 帳本預檢（修正輪） | 同第二列 | `c3d5bcf`：`result: OK`（176／70／159，0 漂移、0 缺；本輪沒動列管檔與帳本） |

帳本預檢的一個盲點（審查 S-4）：`n8n_arguments.py` 那筆 `guarded_sources` 裡的 `tool_snapshot.py` 摘要，預檢看不到（被 `tool_snapshot.py` 自己那筆
蓋掉），只有 `tests/test_tool_inventory.py` 會擋；本片兩處都改對了，`test_tool_inventory` 8 案本機兩輪都過。工具修正交 HM-29（第 15 節）。

`SP:`＝`/data/pi-agent/tmp/claude-1000/-data-pi-agent-home-woow-sec-sweep/9a04e4b3-b708-497b-b300-75c6a25db75e/scratchpad/`。

測試資料：本片的測試沒有 token、密碼或網址；本筆記也沒有（帳本摘要是檔案內容的 SHA-256）。

## 12. 本片用到的決策（`docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| 第 1.1 節，2026-11-17 06:3x（使用者） | PaaS #156 現在就補；做法同 HM-32、不改版號、Hermes 下一版的 CHANGELOG 記一行 | 本片照做（第 2 節） |
| DQ-36 | 不改版號的功能 PR、標題前綴、commit 與 PR 說明不加 AI 署名 | 本分支的 commit 沒有 AI 署名；不 push、不開 PR（本階段） |
| HM-01 黃金回歸檔頭的規則 | 工具清單刻意改版時，該產品的 `LISTING_SHA256`、`LISTED_SHA256` 一起更新 | 第 6.2 節 |

## 13. 交給後面的片（發版片）

本片不改 `addons/`。Hermes 下一次發版時，`addons/hermes/CHANGELOG.md` 記兩行（英文，照既有 CHANGELOG 的寫法；PaaS 的 PR 號寫成
`woow-mcp-server #…`，免得和本 repo 的 PR 號混淆）。下面是審查 MF-1 附的建議稿，最後的英文由發版片定：

- HM-33（本片）：
  "- The `hermes_cron` description now says two things Hermes does, as the PaaS server's description does (woow-mcp-server #156): `create` with `enabled=false` makes the job paused, so it does not run until resumed; and Hermes v0.22.x also resumes a paused job when it is triggered (Hermes's own behaviour, which PaaS measured on Hermes Agent v0.22.5), so call `pause` afterwards if it should stay paused. Text only: this change alone changes no tool name, input or output schema, grant, request or reply."
- PR #85（`b50f1c7`，2026-11-12 合併；發行的 0.4.13 沒有，CHANGELOG 也還沒記；第 7 節）：
  "- `hermes_cron` `create` with `enabled=false` now also sends `paused: true` in the same request, as the PaaS server does (woow-mcp-server #138; PR #85). Per PaaS, current Hermes reads only `paused`, so such a job used to be created enabled. If a backend refuses the extra field (HTTP 422), the add-on reports that error and does not send a second request without it."
- 原稿只有一行，已作廢（審查 MF-1）。它寫「(the add-on already sends `paused` together with `enabled`)」，對發行版不成立；寫「Only the description
  text changes; tool names, inputs, grants and requests do not」，和 #85 放在同一版時不成立（create 的請求會變）；也沒寫明 trigger 那句是 Hermes
  自己的行為。
- 計畫 §11.5 主對話已加一條：每個產品升版前，核對上一版以來合併、但 CHANGELOG 沒記的修正（例子就是 #85）。
- 可以順便告訴使用者（審查第 4 節）：Hermes 下一版其實含一個真的行為修正：#85 之後，`enabled=false` 建的排程在現在的 Hermes 上才真的是停用的。
- PaaS README 安裝前提那句（英文原文，`apps/hermes/README.md`）：
  - 改之前："- **Hermes Agent v0.17.0** running with Gateway API (:8642) and Dashboard API (:9119) accessible"
  - 改之後："- **Hermes Agent v0.17.0 or v0.22.x** (production runs v0.22.5) running with Gateway API (:8642) and Dashboard API (:9119) accessible"
  - HA 沒有對應的段落：`apps/hermes/` 底下沒有 README；`addons/hermes/README.md` 沒有安裝前提；`addons/hermes/DOCS.md` 只在「後端與設定主權」與
    「發佈與尚未通過關卡」兩處寫「需確認 gateway/dashboard 版本與實際 port」。要不要補、補在哪裡由發版片決定。注意 "production" 指的是 PaaS
    的正式站；HA 的 add-on 接的是用戶自己的 Hermes，照抄時要寫成 PaaS 的正式站（例如 "the PaaS production runs v0.22.5"），不要寫成 HA 的。
- 其他產品的 CHANGELOG 不用寫：它們的程式沒變（每個映像都會帶到更新過的 `docs/provenance/` 與閘道內附的工具清單，但只有 Hermes 那一段變了，
  其他產品的回答逐位元不變）。

## 14. 驗收條件（計畫 §12.3 HM-33）

| 條件 | 狀態 |
|---|---|
| 全綠 | **本機能跑的都綠**：相關 38 個檔 1,158 案（修正輪再跑 27 個檔 551 案）、`tool_inventory.py`、`validate.py`、兩個預檢都過；全套等 CI（root、0 skip） |
| 只改 `hermes_cron` 的說明，文字照 PaaS；程式行為不變（去掉說明後語法樹和基準相同） | 通過：第 5 節（HA 與 PaaS 兩邊都比；反向對照會抓到） |
| 帳本、工具表面摘要、output schema 釘選照規則重算 | 通過：第 4、6 節（另含 `tool_snapshot.py`、`runtime-patches.json` 兩處、HM-01 兩個摘要、`hermes_webhook` 行號） |
| HA 的 README 有對應的安裝前提段落才補版本那句 | 沒有對應段落，不補；原文交發版片（第 13 節） |
| 測試：釘住工具說明有這兩句；去掉說明後語法樹和基準相同 | 第 8 節（先紅後綠）；第 5 節（實際比對）；審查 S-1 另加 trigger 只送一個 POST（第 8 節，突變證明） |
| 不改版號、不碰 `addons/` | 通過 |
| Hermes 下一版的 CHANGELOG 記一行（交發版片） | 第 13 節：HM-33 一行；審查 MF-1 後另附 PR #85 一行 |
| 獨立審查 | **修正後通過**（`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-33.md`）；必修 2、建議 4 都已處理（第 17 節） |

## 15. 還沒解決、交給後面的片

- **`checks` 秒數**：開 PR 後補（第 10 節）。
- **合併順序**（審查 MF-2；2026-11-17 07:3x 的現況）：
  - HM-32（#113）07:0x 已合併，`claude-delivery` 是 `a709b97`。HM-12 面板是 PR #114（head `48e04eb`），CI 跑中，會比本片先合。
  - 本片等 #114 合併後，由主對話 rebase 到當時的 `claude-delivery` 再開 PR（本分支沒 push 過，可以 rebase；本修正輪照指示沒 rebase）。
    rebase 後重跑兩個預檢、`tool_inventory.py` 與 CI。
  - 審查的試做（`evidence-review-HM-33/logs/rebase-trials.md`）：疊到面板之後，衝突在 `tests/test_output_schemas.py`（`CURRENT_POST_SOURCE_BYTES`
    相鄰兩筆）、驗收矩陣（HM-31 列之後）、契約第 1.2 節兩處（清單那行與段落）與第 10 節表尾、`decisions.md` 第 1.1、5 節兩個表尾。都是兩邊各加
    的行，兩邊都留。`runtime-sources.json`、`tool-surface.json` 和 HM-32 自動合併；`runtime-patches.json` 和 HM-30（#111）、面板的改動自動合併。
    摘要不用重算（改的檔不重疊）；契約第 9 節不用重排（本片不加列）。
  - 本修正輪改的文件都在上面那幾處（契約第 1.2 節那段、第 10 節表尾多一列，`decisions.md` 本片兩列，驗收矩陣本片那列），不會多出新的衝突處。
  - 還沒合的 HM-13b（#108）、HM-13c（#112）也改契約與 `decisions.md`；比本片先合的，本片 rebase 時一樣兩邊都留。本片沒用契約第 9 節的列號，
    它們重排列號時不受影響。
- **發版片**：第 13 節的兩行 CHANGELOG；README（或 DOCS）要不要補 Hermes 版本那句。
- **trigger 的上游行為 HA 沒有實測**：本片照規則不連任何實機或 HA 主機。說明照 PaaS 寫（PaaS 用 v0.22.5 實測）；HA 的 QA 或展示機若之後接
  Hermes 做驗收，可順便確認 v0.22.x 的 trigger 會把停用的排程改回啟用。
- **帳本預檢看不到的一個摘要**（審查 S-4，交 HM-29）：`scripts/ledger_precheck.py` 把各筆摘要用路徑當 key 合併。`tool_snapshot.py` 同時是自己那筆的
  `sha256`，也在 `n8n_arguments.py` 那筆的 `guarded_sources` 裡；後面那筆（`tool_snapshot.py` 自己那筆）蓋掉前面那筆，所以 `n8n_arguments.py`
  那筆的 guarded 摘要改錯時預檢照樣 OK，只有 `tests/test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources` 會擋（本機已跑過，
  第 9 節）。這是既有工具的限制，本片兩處都改對了。改成每筆 entry 的每個摘要分開檢查，交 HM-29（或 HM-01 的維護）。
- **repo 外（給主對話）**：
  - 計畫 §12.3 HM-33 的「做法」寫「帳本、工具表面摘要、output schema 釘選照規則重算」，實際另外還有閘道內附的工具清單（`tool_snapshot.py`）、
    `runtime-patches.json` 的兩個摘要與 HM-01 黃金回歸的兩個摘要（第 4 節），可在計畫或 FEATURE-MATRIX FM-156 補一句。
  - 審查 S-2：計畫 §12.3 HM-32 寫「#138（Hermes 建停用排程時同時送 `paused` 與 `enabled`）HA 已經有，不用動」，可加註「PR #85，0.4.13 還沒有，
    下一版才出去」。
  - 審查 S-3：計畫 §3.3 的 HM-33 列「保證方式」可補「黃金回歸的兩個 tools/list 摘要照 HM-01 檔頭的規則一起更新」。

## 16. commit（`7646f0f` 之後）

| commit | 內容 |
|---|---|
| `67530b9` | 測試（先紅：2 案都紅） |
| `2952ebe` | 說明照 PaaS 補兩句；閘道內附的工具清單；帳本（`runtime-sources.json`、`runtime-patches.json`、`tool-surface.json`）；`test_output_schemas.py` 與 HM-01 黃金回歸的釘選 |
| `c22cc88` | 文件：契約第 1.2、10 節，`decisions.md` 第 1.1、5 節，驗收矩陣的測試檔登記表 |
| `5f2db2b` | 本筆記（獨立審查的對象） |
| `80ab565` | 審查 S-1：新測試的 trigger 一案；測試檔頭補 S-2（#85 還沒發版） |
| `c3d5bcf` | 審查 MF-1、S-1～S-3 的文件：契約第 1.2 節那段與第 10 節一列，`decisions.md` 本片兩列（實作註），驗收矩陣本片那列 |
| （本 commit） | 審查 MF-1、MF-2、S-1～S-4 的筆記修正與處理表（第 17 節） |

## 17. 獨立審查意見處理表

審查：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-33.md`（審查 head `5f2db2b`；判定修正後通過：必修 2、建議 4，沒有要使用者
決定的題）。先核對再改：MF-1 的 #85 與 0.4.13 的關係自己重查過（下表）；S-1 的測試先用突變證明會紅。本修正輪照指示只 commit，不 push、
不開 PR、不 rebase。

| 編號 | 審查意見 | 處理 | commit | 證據 |
|---|---|---|---|---|
| MF-1 | 交發版片的 CHANGELOG 一行不準：發行的 0.4.13 沒送 `paused`（#85 還沒發版）；「requests do not」和 #85 同一版時不成立；沒寫明 trigger 那句是 Hermes 自己的行為 | **已修**：第 13 節改成兩行建議稿（HM-33 一行、#85 一行），原稿作廢；結論、第 2、7 節與契約第 1.2 節同步；PR 草稿同步（repo 外） | `c3d5bcf`（契約）、本 commit（筆記） | 自己重查：`git merge-base --is-ancestor b50f1c7 1cbfcb9` 與 `… b50f1c7 4966f40` 都是「不是祖先」（`1cbfcb9`＝0.4.13 的升版 commit、`4966f40`＝`release-0.4.13-images.json` 記的映像來源）；`git show 4966f40:apps/hermes/vendor/hermes_mcp_server/server.py` 沒有 `"paused": not enabled`；`addons/hermes/CHANGELOG.md` 沒有 `paused`、`#85` |
| MF-2 | 合併順序過時，也漏了 HM-12 面板；「`runtime-patches.json` 和 HM-32 自動合併」不對（HM-32 沒動這個檔，自動合併的是 HM-30 的改動） | **已修**：第 15 節照現況重寫（#113 已合併、#114 先合、之後主對話 rebase 再開 PR、審查試做的衝突處）；PR 草稿同步（repo 外） | 本 commit | 審查 `evidence-review-HM-33/logs/rebase-trials.md`。本修正輪沒 rebase |
| S-1 | 沒有測試守「trigger 只送一個 POST、子程式不會自己再停用」 | **採用**：新測試第 3 案（真子程式、假 dashboard 記下每個請求）。程式本來就對，所以在拋棄式複本做 5 個突變證明它會紅；對照組與 clone 本身都過 | `80ab565` | `evidence-HM-33/fix/trigger-mutations.json`（`tools/trigger_mutations.py`）、`fix/new-tests-clone.txt`；第 8 節 |
| S-2 | 「PaaS #138，HA 已有」沒說還沒發版 | **採用**：契約第 1.2 節、測試檔頭、筆記結論與第 7 節、PR 草稿都補「PR #85，2026-11-12 合併；0.4.13 還沒有，下一版才出去」。前兩個 commit（`67530b9`、`2952ebe`）的訊息照舊寫「HA 已有」：照指示不 rebase、不改寫歷史，以這裡與契約的說法為準 | `80ab565`（測試檔頭）、`c3d5bcf`（契約）、本 commit（筆記） | — |
| S-3 | `decisions.md` 第 1.1 節本片那列，決定欄混了實作的解讀（黃金回歸摘要算在「帳本與工具表面的摘要」裡） | **採用**：那句標成「實作註」，和使用者的原話分開；誰定欄寫「使用者（實作註：HM-33）」；第 5 節本片那列補一句 | `c3d5bcf` | — |
| S-4 | 帳本預檢看不到 `n8n_arguments.py` 那筆的 guarded 摘要 | **不改程式**：第 11、15 節記下，只有 `test_tool_inventory` 會擋（本機已跑過）；工具修正交 HM-29 | 本 commit | 審查的突變 N1（預檢 OK、`test_tool_inventory` 紅） |
