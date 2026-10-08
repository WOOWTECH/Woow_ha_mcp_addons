# Nextcloud 操作說明

## 現況與範圍

**尚未發佈（預定 0.1.7，experimental）**：映像 `ghcr.io/woowtech/amd64-mcp-nextcloud` 尚未建置，也還沒在 HA 上實測；
目前只有本機的單元／整合測試（真實子程序＋假 Nextcloud 後端）與一次對測試用 Nextcloud 35.0.1 的本機端到端讀取。
[發佈關卡](../../docs/operations/release.md) 全部維持關閉。

管理面板與其他產品相同：管理程序以 runtime `SUPERVISOR_TOKEN` 連固定 `ws://supervisor/core/websocket`，只查
`config/auth/list`，確認 Ingress 使用者是 active 的 owner 或 system-admin 才放行；token 只給管理程序，child 不繼承。
此 token 具**廣泛 Core 管理能力**（`homeassistant_api: true`），負責人已於 2026-10-08 核准本 Add-on 使用（與其他六支相同，
只用於管理面板確認 HA owner／管理員）。`panel_admin` 不是角色授權。

本產品 runtime：**FastMCP 3.4.5**，子程序是 WOOWTECH 的 MIT 套件 `nextcloud_mcp_server` v0.1.3（commit 6228f88）
放在 `apps/nextcloud/vendor`，對上游的修改逐檔記在 `docs/provenance/runtime-sources.json`。上游 9 個工具全部支援：

| 工具 | 類型 | 預設 |
|---|---|---|
| `get_file_tree` | 讀：列出資料夾（深度 1–3，最多 500 筆） | 開 |
| `get_file_content`、`read_text_file` | 讀：UTF-8 文字檔（最大 1 MiB），後者另回 etag | 開 |
| `list_calendars`、`list_tasks` | 讀：行事曆與任務（VTODO，不能改） | 開 |
| `create_text_file` | 寫：只建新檔，從不覆寫 | 關，需授權 |
| `update_text_file` | 寫：etag 相符才整份取代 | 關，需授權 |
| `upload_file` | 寫：上傳任意檔案（base64），不帶 etag 只建新檔 | 關，需授權 |
| `delete_file_checked` | 寫：etag 相符才刪單一檔案（進垃圾桶） | 關，需授權 |

逐名 schema／預設以 [工具對照](../../docs/tool-surface.md) 與 [machine manifest](../../docs/tool-surface.json) 為準。
寫入授權只認逐工具的 exact grant；舊的全域寫入開關不授權任何 Nextcloud 工具。停用（disabled）永遠優先。
政策一變更，子程序就以新的環境變數重啟：有授權寫入工具才 `NEXTCLOUD_MCP_READONLY=false`，有授權
`delete_file_checked` 才 `NEXTCLOUD_MCP_ALLOW_DELETE=true`，其他沒開放的工具列入 `NEXTCLOUD_MCP_DISABLED_TOOLS`，
子程序根本不註冊；gateway 另外再以本地 schema 檢查每個呼叫，tools/list 也由 gateway 依本地定義重建。

## 後端與設定主權

一個 Add-on 只有一個 Nextcloud 帳號：**url（Nextcloud 根網址）、username、app_password**。

- 請在 Nextcloud「個人設定 → 安全性 → 裝置與工作階段」為本 Add-on 建立專用 **App 密碼**，不要填登入密碼。
  建議用權限最小的專用帳號，只分享需要的資料夾給它。url、使用者名稱與 App 密碼存檔時就會檢查：
  `backend_policy` 會拒絕的網址（路徑含 `.`／`..` 片段、解碼後含 `%` 或 `\`、metadata 類主機）與空白或前後有空白的帳密都存不進去。
- **帳密錯誤會鎖住，而不是一直重試**：Nextcloud 回 401（帳密錯誤）之後，子程序不再用這組帳密連 Nextcloud，工具與健康檢查
  都直接回 `BACKEND_HTTP_ERROR status=401`，直到子程序重啟（在面板重新儲存後端設定，或重新啟動 Add-on）。回 429（暴力破解防護
  擋下）時同樣停止連線，但只停 5 分鐘（gateway 的傳輸層看不到 Retry-After，所以一律用預設的 5 分鐘），之後再試一次。
  這是為了避免每 15 秒一次的健康檢查不斷送出失敗的登入，觸發 Nextcloud 的暴力破解防護、把 Add-on 所在的 IP
  （在家用 NAT 或沒設 trusted_proxies 的反向代理後面，常是整個網路共用的 IP）封鎖，連同一 IP 的網頁登入與其他用戶端一起被擋。
- **要撤銷或輪替 App 密碼，請先停用 Add-on**，在 Nextcloud 撤銷舊密碼、建立新密碼，到面板存入新密碼後再啟動。
- 若 IP 已被封鎖：Nextcloud 管理員可執行 `occ security:bruteforce:reset <ip>` 清除該 IP 的紀錄；長期可在
  「管理設定 → 安全性」的暴力破解 IP 白名單（Brute-force settings app）加入 Add-on 所在的 IP。修好密碼後也要等舊紀錄過期或先清除，
  否則登入可能被延遲到超過健康檢查的逾時，readiness 會停在 503。
- 後端憑證／URL、token、policy 由 GUI/state 擁有；HA options 為空，不放 credentials、不覆寫 state。
- 所有後端請求都經 gateway 的 `backend_policy`：DNS 只解析一次並檢查所有位址類別、連線釘在檢查過的位址、
  不跟隨轉址、不讀 proxy 環境變數、TLS 一定驗證。所以 URL 必須是最終位址（轉址會回 `BACKEND_HTTP_ERROR status=30x`）；
  私有 CA 的 Nextcloud 目前不支援（`CA_BUNDLE` 未提供，需另行審查），`http://` 只建議在可信任的內網使用。
- 錯誤一律是公開代碼，例如 `BACKEND_HTTP_ERROR status=404: "x" does not exist.`、`BACKEND_UNAVAILABLE`、
  `BACKEND_TIMEOUT`；Nextcloud 回應的錯誤內容不會轉給 client。

## 已知限制

- gateway 每個 MCP 請求最多 256 KiB：`create_text_file`／`update_text_file` 的內容與 `upload_file` 的 base64 都要小於此值。
- 檔名或路徑含 `%` 的檔案會被 `backend_policy` 拒絕（`BACKEND_DESTINATION_DENIED`）；直接讀寫這種檔案或資料夾都會失敗。
  `get_file_tree` 往下列子資料夾（depth 2–3）時，遇到名稱含 `%` 的子資料夾會略過它、不中斷整個列表，並把 `truncated` 設為 true。
- 不能建立資料夾、不能修改任務、不展開重複任務；`list_tasks` 描述截 500 字。
- Nextcloud 的 etag 大約以秒為單位：同一個檔案在一秒內連續寫兩次，etag 可能不變。這時 `update_text_file`／`upload_file`
  的結果會多一個 `note` 欄位提醒，下一次有條件寫入前請等一秒。

## 網路、健康與更新

- `8099`：Ingress-only，無主機 mapping；不是 MCP endpoint。
- `8081/mcp`：Bearer Streamable HTTP；`8081/tcp: null` 預設不公開 LAN mapping。
- `3000`：child loopback-only，永不暴露；子程序的 Host/Origin 檢查只接受 localhost／127.0.0.1。

後端健康檢查用子程序私有的 `woow_backend_probe`（不在工具清單，gateway 不列出也不授權）：每 15 秒用一個新的連線
讀一次 OCS `cloud/user`，只回 ok 與使用者 id，不佔用工具的連線，也不讀任何檔案；公開工具全部停用時照樣運作。
後端斷線時 readiness 回 503，但不重啟 Add-on（故意不設 watchdog）。資料夾權限、備份還原與更新流程同其他產品，
見 [操作指南](../../docs/operations/guide.md) 與 [更新備份回復](../../docs/operations/update-backup-rollback.md)。

## 發佈與尚未通過關卡

本產品尚需 source/license/secret、image、HA 實測（真實 Nextcloud 版本與受限帳號）、管理員及 non-admin、Ingress UX、
LAN client、backup/restore 與效能證據。其他產品通過不能替本產品背書。
