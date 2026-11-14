# HA 多帳號 HM-00 provenance（2026-11-14）

## 結論

- 範圍：HM-00「決策紀錄、中立契約、刻意差異表、驗收矩陣、PaaS 測試對照」，**只改 `docs/`**（新增 10 個檔，含本筆記）。
  沒有改程式、測試、版號、`addons/<x>/`、CHANGELOG、帳本（`runtime-patches.json`）或 tool-surface。
- 獨立審查（2026-11-14 15:03～15:40，判定「修正後通過」）的 2 項必修、12 項建議都處理了（第 11 節）：錯誤代碼表改成和
  bb48449 的程式、PaaS pin 一致；刻意差異表 79 → 86 列；FEATURE-MATRIX「HA 平台差異」欄是「—」的 44 列逐列寫了結論。
- 對照腳本 9 項全部通過（第 8 節）。審查後多了兩道機械檢查：C7 從 bb48449 原始碼列出所有錯誤代碼並比對狀態碼；C9 要求「—」的
  列都有結論。腳本仍只驗結構與引用存在，語意（對到的列說的是不是同一件事）靠人工抽查。
- 工作期間 PaaS 合併了 #149（14:19，main `7d111b1`）：已照 DQ-06 收進來（第 7 節）；16:07 重查沒有再變。
- 本機檢查全綠；秘密預檢 0 命中、帳本預檢 0 漂移。完整的 `checks`（pytest 以 root、0 skip）只在 GitHub CI 跑。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-00（計畫 §12.3；工作量 L；FM-36、72、100、108） |
| 分支 | `feat/ha-multiprofile-hm00-20261114`（一般 clone，不是 worktree） |
| HA 基準 | `claude-delivery` @ `bb48449`（16:07 重查沒變） |
| 對齊的 PaaS | pin `69ac425`（DQ-06 採 (a)）；`origin/main` `7d111b1`（含 #150 與 #149 兩次合併；16:07 重查沒變） |
| 使用者決定 | 2026-11-14 13:4x 全部採用計畫 §13.1 的 15 項建議，並同意開始第 0 波（HM-00、HM-01） |
| 審查 | repo 外 `artifacts/ha-multiprofile-parity-20261114/wave0/review-HM-00.md`（審查時的 head `8d47c96`） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `docs/multi-profile/README.md` | 目錄 |
| `docs/multi-profile/contract.md` | 中立契約：路徑、方法、管線順序、欄位、錯誤代碼逐欄（既有回應的五種本體形狀）、`X-MCP-Profile` 規則、回聲、寫入保護、過載回應、名額數值（含各產品上限）、回覆排程的門檻、Ingress 備援、刻意差異表 86 列（計畫 43 列＋對照補 36 列＋審查後補 7 列） |
| `docs/multi-profile/decisions.md` | DQ-01～DQ-46：16 題「2026-11-14 使用者採用建議」、30 題「待定」＋負責片與最晚何時 |
| `docs/multi-profile/threat-model.md` | 角色與信任邊界、同 uid 邊界、不變式 I1～I13、已知限制、事故處理 |
| `docs/multi-profile/acceptance-matrix.md` | T-01～T-29 的 HA 期望值、Odoo 首發標準、測試檔登記表（56 個檔） |
| `docs/multi-profile/paas-test-mapping.md` | PaaS 多帳號測試逐檔逐案對照（產生器輸出） |
| `docs/multi-profile/deviation-trace.md` | FEATURE-MATRIX 與 G6 §5 逐列對照，含「—」的 44 列的人工結論（產生器輸出） |
| `docs/multi-profile/ledger-tracking.md` | 新模組 14 個的帳本列管清單與規則 |
| `docs/provenance/multi-profile-parity-baseline.md` | PaaS pin、#150、#149、相關檔清單、變動檢查指令與三次檢查紀錄 |
| `docs/provenance/ha-multiprofile-HM-00-20261114.md` | 本筆記 |

沒改：任何程式與測試、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、帳本、tool-surface、workflow。

## 3. 本機檢查（審查修正後重跑，2026-11-14 16:00～16:22；一般使用者，TMPDIR 用 `/tmp/ha-mp-XXXXXX`、跑完刪除）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（CI venv，Python 3.13.15＋`packaging/requirements-ci.txt`） | PASS |
| packaging unittest（`.venv` 先裝 `requirements-ci.txt`，同 CI 順序） | `Ran 184 tests`、`OK (skipped=5)`；5 個是 `skipUnless(root)`，和本機基準相同 |
| `scripts/tool_inventory.py`（漂移檢查，`packaging/unit.sh` 第 28 行） | 通過，9 個產品的工具數和基準相同 |
| `pytest tests/test_tool_inventory.py`（帳本與 tool-surface 摘要） | 8 passed（另一個代理的全套 pytest 佔著本機測試鎖，等它放開後才跑） |
| 對照腳本 `check_hm00.py`（第 8 節） | 9 項全部通過 |
| 對照腳本的負向測試 `negative_tests.py` | 17 種改壞都如期失敗 |

本片沒有跑 pytest 全套：只改 `docs/`。`docs/provenance/*.md`（含本筆記與基準文件）會被每個產品的 Dockerfile 複製進映像
（`COPY docs/provenance ./docs/provenance`；`.dockerignore` 放行 `docs/provenance/*.md`），但沒有任何測試或閘門讀它們；
`docs/multi-profile/` 不進映像。因為會隨映像公開出貨，基準文件拿掉了 PaaS 正式站的台數。

## 4. 只在 CI 跑的測試

- `checks` job 的其餘步驟：pytest 全套（root、0 skip；本機基準 3601 個）、n8n 與 UI 的 node 測試、Playwright、build closure、
  `packaging/unit.sh` 的其他步驟。
- 需要 root 的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`；packaging 的 5 個
  `skipUnless(root)` 在 CI 那一步也不是 root，同樣 skip。
- `readiness`、`Upgrade comparison`、`Release train`：本片不改版號，預期照舊通過。

## 5. `checks` 秒數

- 前：`bb48449` 的 push run 43222889894，`checks` 1380 秒（23 分 00 秒）。
- 先前寫的 29 分 35 秒是 PR #88（`feaca19`）的 PR run 43218199101（`checks` 1775 秒），不是基準 commit 的 run（審查 SF-07）。
- 後：本片 PR 的第一個 CI run 跑完後補。只改 `docs/`，預期增量約 0。

## 6. 預檢

HM-01 的 `scripts/secret_precheck.py`、`scripts/ledger_precheck.py` 還沒合併，本片照同樣做法手動跑：

- **秘密預檢**：釘選的 gitleaks 8.28.0（tarball SHA-256 和 `packaging/scanner-pins.json` 的 `a65b5253…40eb` 核對過，重新解壓）、
  設定用本 repo 的 `packaging/supply_chain.gitleaks_config()`，旗標同 `supply_chain.secret_scan`（`--redact=100`、
  `--max-decode-depth 5`、`--ignore-gitleaks-allow`…）。審查修正後重跑：

  | 範圍 | 命中 |
  |---|---|
  | HM-00 的 10 個檔（審查修正後、commit 前，dir 模式） | 0 |
  | `bb48449..HEAD`（git 模式；審查修正的 commit `adb454c` 之後，4 個 commit） | 0 |
  | `git archive HEAD` 的 838 個一般檔（builder 同款） | 0 |
  | 全歷史 `--all --full-history -m`（553 個 commit，builder 同款） | 0 |

  含本筆記的最後一個 commit，push 前再掃一次，結果寫在 PR 說明。
- **帳本預檢**（研究線的 `ledger_precheck.py`，只讀）：`runtime-patches` 50 檔、`runtime-sources` 38 筆、`tool-surface` 80 檔，
  0 漂移；要安裝環境的項目（115、79）只計數，由 `tests/test_tool_inventory.py`（8 passed）一起驗過。

## 7. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`）

`origin/main`＝`7d111b1`（14:20 fetch；16:07 用 `ls-remote` 重查仍是 `7d111b1`）。對 `docs/provenance/multi-profile-parity-baseline.md`
第 2 節的相關檔，結果是 6 個 commit（標題摘要，完整清單見基準文件第 3 節）：

| commit | 摘要 |
|---|---|
| `7d111b1` | 合併 #149（紀錄遮罩的 query 憑證） |
| `091dfbc` | docs：惡意 Location 一段改成沙盒實際試過的範圍 |
| `19f36e2` | docs：#148 合併後的文件更正 |
| `d587fd3` | fix：紀錄遮罩守住單調性與冪等 |
| `83526e8` | fix：query 憑證值不再留在 log |
| `ce78bf5` | perf：log 遮罩少掃幾遍整串（結果與 443e95a 逐字相同） |

對 pin 的 53 個測試檔：`82c6929`（#150，`test_gateway_queue.py` 只改既有案例）。

- 只改註解：`gateway_pool.py`、`proxy.py`（AST 比對相同）。正式碼變動：`log_redaction.py`（#149）→ HM-02 改以 `7d111b1` 為對照來源。
- 新測試：#149 的 `test_log_redaction_query_credentials.py`（23 案）、`…_review.py`（41 案）與差分 fixture，已併進
  `paas-test-mapping.md` 的 D 組，全部對到 HM-02。
- HM-00 開工時（13:39）`origin/main` 還是 `5a06d53`、#149 未合併；第一個 commit 之後重查（14:20 的 fetch）發現合併，
  已更新基準文件與對照表（第二個 commit）。

## 8. 對照腳本

腳本在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave0/hm00-check/`。完整的 SHA-256 在同目錄的 `SHA256SUMS`；
審查時的版本留在 `reviewed-8d47c96/`（和審查報告第 4 節記的值相同）。下表是前 16 碼：

| 檔 | 用途 | SHA-256（前 16 碼） |
|---|---|---|
| `check_hm00.py` | 驗收：C1～C9（只讀） | `7af7e8e539fec6c5` |
| `gen_trace.py`、`sources.py` | 產生 `deviation-trace.md`（原文每次從 FEATURE-MATRIX 與 G6 重讀；「—」列的結論寫在 `EMPTY`） | `ef83825684a7e5fd`、`a9241101ddbee7f7` |
| `gen_paas_mapping.py`、`paas_cases.py`、`paas_mapping_spec.py` | 產生 `paas-test-mapping.md`（案例每次用 `git -C` 從 PaaS 物件庫重列；歸屬寫在 spec） | `318fa3706e08cf32`、`f9dd3cd9ebc08215`、`dc17b6c8319a7d2a` |
| `negative_tests.py` | 負向測試（路徑改成參數） | `04d352767cf5c948` |
| `ast_same.py` | 確認 PaaS 只改註解的檔，可執行碼的 AST 沒變 | `c9fa9a4bf3ad365b` |

輸入（repo 外，`artifacts/ha-multiprofile-parity-20261114/`）：`FEATURE-MATRIX-zh-TW.md` `5a398da9f5892171`、`gaps/G6-delivery.md`
`b8285253e2738b60`、`PLAN-zh-TW.md` `49231c852cc60c62`（和審查時相同）；PaaS 用 git 物件 `69ac425` 與 `7d111b1`；HA 原始碼用 `bb48449`。

指令（在任何目錄跑都可以；`<A>`＝artifacts 目錄）：

```sh
python3 -I -B <A>/wave0/hm00-check/gen_trace.py <A> <HA clone>/docs/multi-profile/deviation-trace.md
python3 -I -B <A>/wave0/hm00-check/gen_paas_mapping.py <PaaS clone> <HA clone>/docs/multi-profile/paas-test-mapping.md
python3 -I -B <A>/wave0/hm00-check/check_hm00.py --repo <HA clone> --artifacts <A> --paas <PaaS clone>
python3 -I -B <A>/wave0/hm00-check/negative_tests.py --repo <HA clone> --artifacts <A> --paas <PaaS clone>
```

兩個產生器重產到暫存區，和 commit `adb454c` 的檔逐位元相同（`deviation-trace.md` `32573f5155dea867`、
`paas-test-mapping.md` `9e8993747893930e`）。`check_hm00.py` 的結果（審查修正後）：

```text
PASS C1 diff 只在 docs/: 10 個檔；docs/ 以外：無
PASS C2 刻意差異表: 86 列（1～86）；欄位或類型有問題的列：無；PaaS 欄和 HA 欄一樣的列：無
PASS C3 FEATURE-MATRIX「HA 平台差異」欄: 來源 109 列、對照 109 列；對到差異表 98 列、對到測試 43 列；問題：無
PASS C4 G6 §5「HA 期望值與差異」欄: 來源 29 列、對照 29 列；對到差異表 25 列、對到測試 27 列；問題：無
PASS C5 驗收矩陣與測試登記表: 29 個情境、登記 56 個測試檔；問題：無
PASS C6 PaaS 測試逐案對照: pin 69ac425、main 7d111b1；56 檔 606 案；pin 之後併進 D 組 65 案；#149 已合併；問題：無
PASS C7 錯誤代碼逐欄標註: 管理 API 31 個代碼、MCP 11 種回應；計畫 §5.3 第 9 點 19 個全在；bb48449 原始碼 17 個代碼與 error 字串（16 個在表裡比對）；排除清單列狀態值 15 個；問題：無
PASS C8 決策紀錄: 46 題；§13.1 採用 16 題；待定 30 題；問題：無
PASS C9「—」列的人工結論: 來源 44 列、結論 44 列（照 PaaS 19、只對到差異表 23、流程或文件 2）；問題：無
結果：全部通過
```

（C1 另印「未提交」的檔數，跑的時機不同會不一樣，上面省略。）

- 審查後新增的檢查：C2 比對每列的 PaaS 欄和 HA 欄（去掉括號裡的出處後）不能一樣；C7 從 `bb48449` 的
  `packages/mcp-admin-core/mcp_admin_core/*.py` 用 AST 列出 `fail()`、`BadRequest(<狀態>, {'code': …})`、`JSONResponse(…, status_code=…)`
  的代碼與 `{"error": "<字串>"}`，表裡沒有、狀態碼不同、新舊欄不是「既有」都不過（拿審查時的契約跑，會抓到漏掉的
  `unsupported`、`backend_check_failed`、`backend_fixed`）；C9 要求「—」的 44 列每列都有「照 PaaS」「§8.8 #n」或「不是執行期行為：…」。
- 負向測試 17 種都如期失敗：原本 11 種（對到不存在的差異列、少一列、原文被改、測試沒登記、少一個 PaaS 案例、歸屬空白、錯誤表空一欄、
  文中多一個沒列的代碼、§13.1 的題改成待定、待定沒有負責片、差異表跳號），加上既有代碼狀態碼改錯、表裡少一個既有的 error 字串、
  新代碼標成既有、差異表 HA 欄改成和 PaaS 一樣、「—」列少一列、「—」列沒有結論。
- 語意盲點：審查的 6 種語意改壞（`blindspot_probe.py`），現在抓得到 2 種（既有代碼狀態碼改錯、差異表 HA 欄改成和 PaaS 一樣）；
  另外 4 種（對到存在但不相干的差異列或測試、契約的 PaaS 欄寫錯、PaaS 案例歸屬改錯）只能靠人工抽查。

## 9. 驗收條件（計畫 §12.3 HM-00）

| 條件 | 狀態 |
|---|---|
| 使用者確認 §13.1 | 已確認（2026-11-14 13:4x 全部採用） |
| diff 只在 `docs/` | 通過（C1） |
| 每個錯誤代碼有標註 | 通過（C7：計畫 §5.3 第 9 點的 19 個代碼都在、狀態碼一致；bb48449 原始碼的 16 個代碼與 error 字串都在表裡、狀態碼一致；MCP 回應表 11 種，另列其他既有回應） |
| 每個 DQ 有結論或「待定＋負責片」 | 通過（C8）；契約裡照計畫建議寫的待定題都標了「待定＋負責片」 |
| FEATURE-MATRIX「HA 平台差異」欄與 G6 §5「HA 期望值與差異」欄逐列對到 §8.8 或某個測試 | 通過（C3、C4；對不上的補成差異表第 44～79 列）；「—」的 44 列也逐列寫了結論（C9；找到的差異補成第 80～86 列） |
| PaaS 對照每檔每案有歸屬 | 通過（C6；pin 的 53 檔 541 案，加 pin 之後併進來的 3 檔 65 案） |

## 10. 還沒解決、交給後面的片

- 契約裡標「暫定」的細節：刪除、索引隔離與刪除隔離目錄的路徑與回應本體（HM-10、HM-13c）、還原紀錄欄位、全部撤銷失敗時的狀態碼、
  額外帳號的 owner-defaults 代碼、索引壞時可用的路由（HM-10、HM-13b、HM-13c）、讀 body 途中位元組額度用完的回應（HM-08）、
  各產品上限與每子程式記憶體（HM-07 定常數、HM-19c 量測後定案；Hermes 看 HM-24 的 60 分鐘量測）。
- 回覆排程的停頓門檻 ≤50 ms 可能做不到：C 層的 `json.loads`、`json.dumps`、`re.sub` 不放 GIL，一條工作執行緒的設計下仍可能超過；
  HM-30 用真實 8 MiB 回覆量，做不到就回報使用者再定（契約第 6 節），不自行放寬。
- §13.2、§13.3 的 30 題還沒問；DQ-38 要在 HM-02 開工前問，DQ-12 在 HM-07 前，DQ-09、DQ-19 在 HM-08 前。
- 待使用者：出貨機記憶體規格與可量測硬體（DQ-07＋DQ-29）、HM-03a／HM-03b 的 QA HAOS 授權（DQ-34）。
- 產品片的測試檔名是暫定名（HM-21～HM-27）；改名時同時改登記表並重跑對照腳本。
- HM-02：#149 的兩個測試檔有字面 64 hex 值，vendor 前先過秘密預檢、換成執行時產生。
- FEATURE-MATRIX、G6 改版或 PaaS 再變時：重跑兩個產生器與 `check_hm00.py`，並更新第 8 節的 SHA-256。

## 11. 審查意見處理（`review-HM-00.md`，判定「修正後通過」）

| id | 處理 | 改在哪 |
|---|---|---|
| MF-1 | 採用。逐項打開 bb48449 與 PaaS pin 核對過，5 處都對：既有回應的本體形狀改成五種（A～E）；補 `unsupported` 409、`backend_check_failed` 503、`backend_fixed` 409 三列，固定回應補 415 與第 ① 步的 400；`core_version_unreviewed` 改 ⑥／⑩；`CREDENTIAL_REPLACEMENT…` 沒開通時改「不出現」；重複 `X-MCP-Profile` 的 PaaS 欄改「取第一個值」 | `contract.md` 第 0、3.2、3.3、4.1 節 |
| MF-2 | 採用 (a)。差異表補 #80 手動指定 token、#81 超過上限的讀法、#82 全部撤銷、#83 重複標頭；「—」的 44 列逐列人工看過，另找到 3 個差異補成 #84 帳號被刪時的面板、#85 範例名稱、#86 帳號範圍操作的既有契約；FM-31 的 4 案改指 #80；腳本加 C9 | `contract.md` 第 9 節；`deviation-trace.md` 文末；`paas-test-mapping.md`；`acceptance-matrix.md` T-08 |
| SF-01 | 採用：第 5 節加各產品上限、每子程式 MiB、保留量 256 MiB 與 PaaS 公式（暫定照 PaaS） | `contract.md` 第 5 節 |
| SF-02 | 採用：DQ-05、13、14、15、16、17、25 在契約裡標「待定＋負責片」 | `contract.md` 第 3.1、3.3、3.5、3.6、7 節 |
| SF-03 | 採用：第 4.2 節後面列出其他既有回應，寫明由 HM-01 凍結 | `contract.md` 第 4.2 節 |
| SF-04 | 採用：C7 從原始碼列代碼比狀態碼；C2 加 PaaS 欄≠HA 欄；本筆記寫明語意靠人工抽查 | 對照腳本；本筆記第 8 節 |
| SF-05 | 採用一半：記腳本與輸入的 SHA-256 與重產指令，`negative_tests.py` 改成參數。不把產生器搬進 repo：輸入檔（FEATURE-MATRIX、G6、PLAN）本來就在 repo 外，搬進來也重產不了，還會讓本片的 diff 超出 `docs/` | 本筆記第 8 節；`README.md`、兩個產生的檔的檔頭 |
| SF-06 | 採用：改寫「會被複製進映像，但沒有測試或閘門讀」；基準文件拿掉正式站台數 | 本筆記第 3 節；基準文件第 1 節 |
| SF-07 | 採用：「前」改用 `bb48449` 的 push run（1380 秒），兩個都列 | 本筆記第 5 節 |
| SF-08 | 採用：門檻改「暫定、量測後定案、放寬要使用者同意」；注入要佔住 GIL；加真實 8 MiB 案例；寫明 ≤50 ms 可能做不到 | `contract.md` 第 6 節 |
| SF-09 | 採用：補刪除隔離目錄的路由與寫入保護（暫定，HM-13c 定案） | `contract.md` 第 1.1、3.1、3.5、4.1 節 |
| SF-10 | 採用：#43 改「部署」 | `contract.md` 第 9 節 |
| SF-11 | 採用：`features.py` 補「HM-17（先）」 | `ledger-tracking.md` |
| SF-12 | 採用：補一列「讀 body 途中額度用完：503＋`Retry-After: 5`、`id: null`，立刻停讀並釋放」（暫定，HM-08 定案） | `contract.md` 第 2.2、2.4 節 |
