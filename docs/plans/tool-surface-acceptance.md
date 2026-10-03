# 工具功能對照驗收要求

上游要求：四工具 n8n tracer 只是垂直切片，**不代表完整 n8n 遷移**。任何縮減必須明示，不能把 unknown-deny 當作全部產品完成。

W2 worker 必須根據每類 exact pinned source/runtime 列完整對照，提供機器可驗證 manifest 與繁中文件：

| 原有/上游 exact tool 名稱 | 本地支援狀態 | 唯讀/寫入/混合及逐 operation | 預設 | 管理員如何啟用 | 暫不支援原因/需要的補強 | 來源/測試 |
|---|---|---|---|---|---|---|

- tool inventory 必須來自 pinned runtime tools/list 或 decorator/handler 源碼，不生成虛构清單。兩者證據等級區分。
- 支援的工具 schema 與 call gate 一致；依真實 handler 副作用分類，不能只依名稱/annotation/dangerous 欄位。
- 混合工具須參數級限制；未知/disabled/未稽核工具 fail closed。
- 原本 writer 要有可啟用路徑與 mock 正/反測試；不以僅支援一個刪除工具聲稱全部寫入完成。
- 無法本批安全支援者需逐名列出原因、剩餘任務與驗收 gate。不得隱性刪除或宣稱完整。
- n8n backend API 操作只能 mock 或經批准非正式測試憑證；文件工具成功不等於 backend E2E。
- 每次來源升版 inventory 漂移測試必須失敗，直到新工具完成分類/審查；絕不預設 unknown read-only。

目前 W1：n8n 僅 `tools_documentation`、`search_nodes`、`n8n_list_workflows`、`n8n_delete_workflow`，其餘未納入 tracer。W2 必須補完整盤點與支援/不支援明細，再作 release completeness 判定。

## 授權歸屬同步要求

新共用 boundary 是本次新寫而非直接複製舊 core/UI；以逐檔 provenance/比對證據確認。**沒有納入的 legacy shared 檔案授權疑義不能當成新寫程式的永久 blocker**。若後續複製舊 shared 片段，才對該片段追 scope/notice。各 vendored app、npm/Python依賴、OpenDesign provenance、Odoo Manage MPL 對應源碼/NOTICE 與整體公開敏感稽核仍個別處理。
