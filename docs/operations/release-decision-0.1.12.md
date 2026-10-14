# 0.1.12 候選發佈紀錄

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

本版有兩項變更。一、把七支 manifest 的開機預設由 `boot: manual` 改為 `boot: auto`。起因：PaaS 正式測試 HAOS VM 重開機後，`boot: manual` 的 MCP 與後端 add-on 都沒有自動回來（Supervisor 只自動啟動 `boot: auto`）；使用者 2026-10-14 決定「要自動」。`packaging/validate.py` 的 manifest 精確規則同步改為 `boot='auto'`，`packaging/test_validate.py` 的反向 mutation 改為 `boot: manual` 必須被拒。其他權限、`startup: application`、protection mode、auto-update 與工具面皆不變。

二、共用 gateway 新增 Claude.ai 網頁版自訂連接器用的密鑰網址 `/private_<token>/mcp`（Claude.ai 自訂連接器無法帶 Authorization header）：用同一把 Add-on 權杖（rotate／revoke 同時生效），以 sha256 摘要經 `hmac.compare_digest` 比對；權杖錯誤、空白、未設定或已撤銷（含請求途中的重驗）一律回與不存在路徑相同的 Starlette 404；忽略請求自帶的 Authorization；允許 Origin 且不轉給子程序；`/mcp` 的 Bearer 行為不變（含 Origin 403）。新增 `mcp_admin_core/redact.py`，在 LogRecord factory 與 uvicorn handlers 兩層把 `/private_…/` 遮成 `/private_[REDACTED]/`（`access_log` 仍關閉）。管理面板新增「顯示 Claude.ai 連線網址」（沿用 token reveal 的 CSRF 流程，需先設定對外端點）。說明見 [client 設定](clients.md)；測試見 `tests/test_secret_path.py` 與 UI 測試。尚未以真實 Claude.ai 或 HA 實機驗證。

三、manifest 移除 `ingress_entry: /`（2026-10-14 實機發現）：Supervisor 2026.09（`supervisor/apps/app.py` 的 `ingress_url`）回傳 `f"/api/hassio_ingress/{token}/{ingress_entry}"`，舊值使 HA 側邊欄開啟 `…/<token>//`，管理面板回 404（0.1.11 實例同樣受影響）。不設此鍵時入口為 `…/<token>/`。PaaS 測試 VM 以本機 add-on 實測：移除並 rebuild 後 ingress_url 結尾單一 `/`、GET 200。`packaging/validate.py` 不再接受此鍵（`exact()` 拒絕），`test_validate` 加入反向案例。映像 label 只含 name/description/version，此變更不影響已建置與已推送的 0.1.12 映像。

此 repo 七個產品共用 VERSION、initialize 身分、manifest、Dockerfile 與 CI/release 版本，因此一致準備 0.1.12；不新增版號分流機制。新版本改變 core VERSION、image labels 及 source revision，必須產生新 image ID，不能 retag 或繼承 0.1.11 映像驗收。

後續由主控核對 hosted CI、builder admission 與候選 image/test/scan receipts，再在 PaaS 已建立的 HAOS VM 完成實機驗收（含重開機後七支自動啟動）。已安裝且使用者曾手動切換「開機時啟動」的實例，可能保留其個別設定，升版後需在 HA 上逐支確認。主控統一 release/merge/部署；本紀錄不宣告商用 PASS。
