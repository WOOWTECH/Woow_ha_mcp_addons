# 多帳號（multi-profile）文件

同一個 add-on 開「預設帳號＋最多 5 個額外帳號」、對齊 PaaS `woow-mcp-server` 的設計文件。**目前沒有任何產品開通**
（HM-07 起 `features.py` 有 `MULTI_PROFILE_PRODUCTS`，內容是空的）；這裡的行為要等該產品的升版 PR 合併才生效，README 與 `addons/<x>/` 底下的文件到那時才改。

| 檔 | 內容 | 誰維護 |
|---|---|---|
| `contract.md` | 中立契約：路徑、方法、管線順序、欄位、錯誤代碼、名額數值、刻意差異表（§8.8）；開通後預設帳號會變的事（第 1.4 節，計畫 §7.2 的完整清單） | HM-00 起草 → HM-10 → HM-18 定稿（2026-11-19）；之後 HM-19c 改第 5、6 節的暫定數值，各產品開通片加列 |
| `decisions.md` | DQ-01～DQ-46 的結論、日期或「待定＋負責片」 | 每次有決定就改 |
| `threat-model.md` | 角色與信任邊界、安全不變式 I1～I13、已知限制、事故處理（使用者看的版本在 `docs/operations/guide.md`「多帳號（產品開通後）」） | HM-00、HM-18 |
| `acceptance-matrix.md` | T-01～T-29 的 HA 期望值、Odoo 首發標準、測試檔登記表 | HM-00 → HM-16 |
| `paas-test-mapping.md` | PaaS 多帳號測試逐檔逐案對照（pin 的 53 檔 541 案，加 pin 之後併進來的 26 檔 282 案；PaaS 基準 `48f394d`） | 由 repo 外的產生器重產（重產指令見 HM-00 provenance 筆記第 8 節；2026-11-17 起 `gen_paas_mapping.py` 另加 `--main 48f394d`，輸入版本見 `docs/provenance/ha-multiprofile-docs-sync-20261117.md`；腳本與輸入的 SHA-256 以 repo 外的 `wave0/hm00-check/SHA256SUMS` 為準） |
| `deviation-trace.md` | FEATURE-MATRIX 每一列（含「HA 平台差異」欄是「—」的列）與 G6 §5 逐列對到差異表、測試，或寫明為什麼相同；文末反查差異表每一列從哪裡來 | 同上（2026-11-17 起另讀 `contract.md` 第 9 節） |
| `ledger-tracking.md` | 新模組的帳本列管清單與規則 | HM-00 定案 |
| `unreleased-changes.md` | 各產品下一版會帶出去、`addons/<x>/CHANGELOG.md` 還沒記的變更與 CHANGELOG 句子、發版時要另外驗的事（計畫 §11.5）；**任何產品的升版 PR 前讀**，其他工作線的修補版也一樣；開通某個產品的那一版另看第 7 節（2026-11-19 起） | 不受開關管的片（或任何改到映像行為的修正）合併時加一項；發版的 PR 把寫進 CHANGELOG 的項目移掉或標「已發」（2026-11-17 起，HM-17 補正） |

相關：`docs/provenance/multi-profile-parity-baseline.md`（PaaS pin 與變動檢查）、各片的
`docs/provenance/ha-multiprofile-<片>-YYYYMMDD.md`。計畫本身在 repo 外（`artifacts/ha-multiprofile-parity-20261114/PLAN-zh-TW.md`）。
