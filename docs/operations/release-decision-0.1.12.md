# 0.1.12 候選發佈紀錄

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

本版只把七支 manifest 的開機預設由 `boot: manual` 改為 `boot: auto`。起因：PaaS 正式測試 HAOS VM 重開機後，`boot: manual` 的 MCP 與後端 add-on 都沒有自動回來（Supervisor 只自動啟動 `boot: auto`）；使用者 2026-10-14 決定「要自動」。`packaging/validate.py` 的 manifest 精確規則同步改為 `boot='auto'`，`packaging/test_validate.py` 的反向 mutation 改為 `boot: manual` 必須被拒。其他權限、`startup: application`、protection mode、auto-update 與工具面皆不變。

此 repo 七個產品共用 VERSION、initialize 身分、manifest、Dockerfile 與 CI/release 版本，因此一致準備 0.1.12；不新增版號分流機制。新版本改變 core VERSION、image labels 及 source revision，必須產生新 image ID，不能 retag 或繼承 0.1.11 映像驗收。

後續由主控核對 hosted CI、builder admission 與候選 image/test/scan receipts，再在 PaaS 已建立的 HAOS VM 完成實機驗收（含重開機後七支自動啟動）。已安裝且使用者曾手動切換「開機時啟動」的實例，可能保留其個別設定，升版後需在 HA 上逐支確認。主控統一 release/merge/部署；本紀錄不宣告商用 PASS。
