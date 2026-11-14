# 多帳號（multi-profile）文件

同一個 add-on 開「預設帳號＋最多 5 個額外帳號」、對齊 PaaS `woow-mcp-server` 的設計文件。**目前沒有任何產品開通**
（`MULTI_PROFILE_PRODUCTS` 還不存在）；這裡的行為要等該產品的升版 PR 合併才生效，README 與 `addons/<x>/` 底下的文件到那時才改。

| 檔 | 內容 | 誰維護 |
|---|---|---|
| `contract.md` | 中立契約：路徑、方法、管線順序、欄位、錯誤代碼、名額數值、刻意差異表（§8.8） | HM-00 起草 → HM-10 → HM-18 定稿 |
| `decisions.md` | DQ-01～DQ-46 的結論、日期或「待定＋負責片」 | 每次有決定就改 |
| `threat-model.md` | 角色與信任邊界、安全不變式 I1～I13、已知限制、事故處理 | HM-00、HM-18 |
| `acceptance-matrix.md` | T-01～T-29 的 HA 期望值、Odoo 首發標準、測試檔登記表 | HM-00 → HM-16 |
| `paas-test-mapping.md` | PaaS 多帳號測試逐檔逐案對照（pin 的 53 檔 541 案，加 pin 之後併進來的 3 檔 65 案） | 由 repo 外的產生器重產（腳本與輸入的 SHA-256、重產指令見 HM-00 provenance 筆記第 8 節） |
| `deviation-trace.md` | FEATURE-MATRIX 每一列（含「HA 平台差異」欄是「—」的列）與 G6 §5 逐列對到差異表、測試，或寫明為什麼相同 | 同上 |
| `ledger-tracking.md` | 新模組的帳本列管清單與規則 | HM-00 定案 |

相關：`docs/provenance/multi-profile-parity-baseline.md`（PaaS pin 與變動檢查）、各片的
`docs/provenance/ha-multiprofile-<片>-YYYYMMDD.md`。計畫本身在 repo 外（`artifacts/ha-multiprofile-parity-20261114/PLAN-zh-TW.md`）。
