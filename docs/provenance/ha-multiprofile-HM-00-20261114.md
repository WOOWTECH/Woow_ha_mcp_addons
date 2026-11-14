# HA 多帳號 HM-00 provenance（2026-11-14）

## 結論

- 範圍：HM-00「決策紀錄、中立契約、刻意差異表、驗收矩陣、PaaS 測試對照」，**只改 `docs/`**（新增 10 個檔，含本筆記）。
  沒有改程式、測試、版號、`addons/<x>/`、CHANGELOG、帳本（`runtime-patches.json`）或 tool-surface。
- 對照腳本 8 項全部通過（第 8 節）：FEATURE-MATRIX 109 列與 G6 §5 的 29 列「差異」欄逐列對到刻意差異表或測試；PaaS 56 檔 606 案
  每案有歸屬；28 個管理 API 錯誤代碼與 11 種 MCP 回應逐欄標註；DQ-01～DQ-46 都有結論或「待定＋負責片」。
- 工作期間 PaaS 合併了 #149（14:19，main `7d111b1`）：已照 DQ-06 收進基準文件與 PaaS 對照（第 7 節）。
- 本機檢查全綠；秘密預檢 0 命中、帳本預檢 0 漂移。完整的 `checks`（pytest 以 root、0 skip）只在 GitHub CI 跑。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-00（計畫 §12.3；工作量 L） |
| 分支 | `feat/ha-multiprofile-hm00-20261114`（一般 clone，不是 worktree） |
| HA 基準 | `claude-delivery` @ `bb48449` |
| 對齊的 PaaS | pin `69ac425`（DQ-06 採 (a)）；`origin/main` `7d111b1`（14:20 fetch；含 #150 與 #149 兩次合併） |
| 使用者決定 | 2026-11-14 13:4x 全部採用計畫 §13.1 的 15 項建議，並同意開始第 0 波（HM-00、HM-01） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `docs/multi-profile/README.md` | 目錄 |
| `docs/multi-profile/contract.md` | 中立契約：路徑、方法、管線順序、欄位、錯誤代碼逐欄、`X-MCP-Profile` 規則、回聲、寫入保護、過載回應、名額數值、回覆排程的 CPU 門檻、Ingress 備援、刻意差異表 79 列（計畫 43 列＋對照補 36 列） |
| `docs/multi-profile/decisions.md` | DQ-01～DQ-46：16 題「2026-11-14 使用者採用建議」、30 題「待定」＋負責片與最晚何時 |
| `docs/multi-profile/threat-model.md` | 角色與信任邊界、同 uid 邊界、不變式 I1～I13、已知限制、事故處理 |
| `docs/multi-profile/acceptance-matrix.md` | T-01～T-29 的 HA 期望值、Odoo 首發標準、測試檔登記表（56 個檔） |
| `docs/multi-profile/paas-test-mapping.md` | PaaS 多帳號測試逐檔逐案對照（產生器輸出） |
| `docs/multi-profile/deviation-trace.md` | FEATURE-MATRIX 與 G6 §5 的差異欄逐列對照（產生器輸出） |
| `docs/multi-profile/ledger-tracking.md` | 新模組 14 個的帳本列管清單與規則 |
| `docs/provenance/multi-profile-parity-baseline.md` | PaaS pin、#150、#149、相關檔清單、變動檢查指令與兩次檢查紀錄 |
| `docs/provenance/ha-multiprofile-HM-00-20261114.md` | 本筆記 |

沒改：任何程式與測試、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、帳本、tool-surface、workflow。

## 3. 本機檢查（2026-11-14，一般使用者，TMPDIR 用 `/tmp/ha-mp-XXXXXX`、跑完刪除）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（CI venv，Python 3.13.15＋`packaging/requirements-ci.txt`） | PASS |
| packaging unittest（`.venv` 先裝 `requirements-ci.txt`，同 CI 順序） | `Ran 184 tests`、`OK (skipped=5)`；5 個是 `skipUnless(root)`，和本機基準相同 |
| `scripts/tool_inventory.py`（漂移檢查，`packaging/unit.sh` 第 28 行） | 通過，9 個產品的工具數和基準相同 |
| `pytest tests/test_tool_inventory.py`（帳本與 tool-surface 摘要） | 8 passed |
| 對照腳本 `check_hm00.py`（第 8 節） | 8 項全部通過 |

本片沒有跑 pytest 全套：只改 `docs/`，新加的檔沒有任何測試或建置步驟會讀（`packaging/` 只讀 `docs/operations/` 的發佈紀錄）。

## 4. 只在 CI 跑的測試

- `checks` job 的其餘步驟：pytest 全套（root、0 skip；本機基準 3601 個）、n8n 與 UI 的 node 測試、Playwright、build closure、
  `packaging/unit.sh` 的其他步驟。
- 需要 root 的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`；packaging 的 5 個
  `skipUnless(root)` 在 CI 那一步也不是 root，同樣 skip。
- `readiness`、`Upgrade comparison`、`Release train`：本片不改版號，預期照舊通過。

## 5. `checks` 秒數

- 前：參考計畫 §10.1 記的 PR run 43218199101，`checks` 29 分 35 秒（不是本片的 run）。
- 後：本片在這個階段只 commit、還沒開 PR；開 PR 後由 GitHub API 的 jobs 時間補。只改 `docs/`，預期增量 0。

## 6. 預檢

HM-01 的 `scripts/secret_precheck.py`、`scripts/ledger_precheck.py` 還沒合併，本片照同樣做法手動跑：

- **秘密預檢**：釘選的 gitleaks 8.28.0（tarball SHA-256 和 `packaging/scanner-pins.json` 的 `a65b5253…40eb` 核對過，重新解壓）、
  設定用本 repo 的 `packaging/supply_chain.gitleaks_config()`，旗標同 `supply_chain.secret_scan`（`--redact=100`、
  `--max-decode-depth 5`、`--ignore-gitleaks-allow`…）。

  | 範圍 | 命中 |
  |---|---|
  | 新增的檔（commit 前，dir 模式） | 0 |
  | 本片的 commit（`git` 模式，`--log-opts=bb48449..HEAD`） | 0 |
  | `git archive HEAD` 的全部檔（builder 同款） | 0 |
  | 全歷史 `--all --full-history -m`（builder 同款） | 0 |

- **帳本預檢**（研究線的 `ledger_precheck.py`，只讀）：`runtime-patches` 50 檔、`runtime-sources` 38 筆、`tool-surface` 80 檔，
  0 漂移；要安裝環境的項目（115、79）只計數，由 `tests/test_tool_inventory.py`（8 passed）一起驗過。

## 7. PaaS 變動（`git log 69ac425..origin/main -- <相關檔>`）

`origin/main`＝`7d111b1`（14:20 fetch）。對 `docs/provenance/multi-profile-parity-baseline.md` 第 2 節的相關檔，結果是 6 個 commit
（標題摘要，完整清單見基準文件第 3 節）：

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

腳本在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave0/hm00-check/`

| 檔 | 用途 |
|---|---|
| `check_hm00.py` | 驗收：C1～C8（只讀） |
| `gen_trace.py`、`sources.py` | 產生 `deviation-trace.md`（原文每次從 FEATURE-MATRIX 與 G6 重讀） |
| `gen_paas_mapping.py`、`paas_cases.py`、`paas_mapping_spec.py` | 產生 `paas-test-mapping.md`（案例每次用 `git -C` 從 PaaS 物件庫重列；歸屬寫在 spec） |
| `ast_same.py` | 確認 PaaS 只改註解的檔，可執行碼的 AST 沒變 |

指令：

```sh
python3 -I check_hm00.py --repo <HA clone> --artifacts <artifacts/ha-multiprofile-parity-20261114> --paas <PaaS clone>
```

結果（全部 commit 後、乾淨工作樹）：

```text
PASS C1 diff 只在 docs/: 10 個檔；docs/ 以外：無；未提交：0 個
PASS C2 刻意差異表: 79 列（1～79）；欄位或類型有問題的列：無
PASS C3 FEATURE-MATRIX「HA 平台差異」欄: 來源 109 列、對照 109 列；對到差異表 98 列、對到測試 43 列；問題：無
PASS C4 G6 §5「HA 期望值與差異」欄: 來源 29 列、對照 29 列；對到差異表 25 列、對到測試 27 列；問題：無
PASS C5 驗收矩陣與測試登記表: 29 個情境、登記 56 個測試檔；問題：無
PASS C6 PaaS 測試逐案對照: pin 69ac425、main 7d111b1；56 檔 606 案；pin 之後併進 D 組 65 案；#149 已合併；問題：無
PASS C7 錯誤代碼逐欄標註: 管理 API 28 個代碼、MCP 11 種回應；計畫 §5.3 第 9 點 19 個全在；排除清單列狀態值 15 個；問題：無
PASS C8 決策紀錄: 46 題；§13.1 採用 16 題；待定 30 題；問題：無
結果：全部通過
```

負向測試：把對照表改壞的 11 種情況（對到不存在的差異列、少一列、原文被改、測試沒登記、少一個 PaaS 案例、歸屬空白、
錯誤表空一欄、文中多一個沒列的代碼、§13.1 的題改成待定、待定沒有負責片、差異表跳號）都如期失敗。

## 9. 驗收條件（計畫 §12.3 HM-00）

| 條件 | 狀態 |
|---|---|
| 使用者確認 §13.1 | 已確認（2026-11-14 13:4x 全部採用） |
| diff 只在 `docs/` | 通過（C1） |
| 每個錯誤代碼有標註 | 通過（C7：計畫 §5.3 第 9 點的 19 個代碼都在、狀態碼一致；另補 9 個既有代碼——收據 6 個、`owner_defaults_unavailable`、`config_apply_failed`、`core_version_unreviewed`——與 MCP 回應表 11 種） |
| 每個 DQ 有結論或「待定＋負責片」 | 通過（C8） |
| FEATURE-MATRIX「HA 平台差異」欄與 G6 §5「HA 期望值與差異」欄逐列對到 §8.8 或某個測試 | 通過（C3、C4；對不上的補成差異表第 44～79 列） |
| PaaS 對照每檔每案有歸屬 | 通過（C6；pin 的 53 檔 541 案，加 pin 之後併進來的 3 檔 65 案） |

## 10. 還沒解決、交給後面的片

- 契約裡標「暫定」的細節：刪除與索引隔離的回應本體、還原紀錄欄位、全部撤銷失敗時的狀態碼、額外帳號的 owner-defaults 代碼、
  索引壞時可用的路由（HM-10、HM-13b、HM-13c 定案）。
- §13.2、§13.3 的 30 題還沒問；DQ-38 要在 HM-02 開工前問，DQ-12 在 HM-07 前，DQ-09、DQ-19 在 HM-08 前。
- 待使用者：出貨機記憶體規格與可量測硬體（DQ-07＋DQ-29）、HM-03a／HM-03b 的 QA HAOS 授權（DQ-34）。
- 產品片的測試檔名是暫定名（HM-21～HM-27）；改名時同時改登記表並重跑對照腳本。
- HM-02：#149 的兩個測試檔有字面 64 hex 值，vendor 前先過秘密預檢、換成執行時產生。
- FEATURE-MATRIX、G6 改版或 PaaS 再變時：重跑兩個產生器與 `check_hm00.py`。
