# Headscale MCP 0.4.13：隔離 HAOS 驗收

2026-11-11 02:38–03:10 UTC。對象是隔離 KubeVirt HAOS 測試機，Core 2026.10.4、Supervisor 2026.10.5、OS 18.3；不是正式 HA。測試機從來源 commit `1b45bdfa5338170d2b397ef5940bb4c241f8b343` 暫時載入本地 Add-on，再由 Supervisor **匿名拉取**公開的 `ghcr.io/woowtech/amd64-mcp-headscale:0.4.13`。實際執行的 amd64 manifest digest 是 `sha256:613b216622e68b188e4b7d61a93a82ba895834f82e52dae2a2b085ffc98b898d`，與 [映像決策](release-decision-headscale-0.4.13.md)一致；它不是 config digest。

只為此測試暫時開放測試 VM 對單一 Headscale 後端的連線，並建立一小時有效的專用 Headscale API 金鑰。沒有使用既有正式 API 金鑰，也沒有修改 Headscale 使用者、節點、政策或路由。以下是實際觀察，不以 `tools/list` 代替工具呼叫。

| 項目 | 實測結果 |
|---|---|
| Supervisor 安裝與啟動 | `ha apps install`、`ha apps start` 成功；`ha apps info` 顯示 0.4.13、`started`、Ingress 啟用。執行中的容器 digest 與公開 manifest 相同，初次啟動重啟數為 0。 |
| Ingress 與權限 | 真實 HA 登入後，`system-admin` 可以讀管理 `bootstrap` 與診斷；無 Ingress cookie 為 401，直接存取容器面板為 403。同一個 session 在帳號降為 `system-users` 後，管理 API 立即回 403；重新登入的一般使用者仍回 403。測試帳號之後恢復管理員以完成驗收，結束時刪除；每次登入取得的 HA refresh token 均撤銷。 |
| 後端連線 | 管理面板儲存單一 Headscale API origin 與短效金鑰後，子行程 `transport_ready=true`、後端 `reachable`。金鑰也在 Headscale 原生 v1 API 上獨立驗證為有效。 |
| 真實 MCP 唯讀 | 用封裝映像內的 MCP SDK 執行 initialize、tools/list 和九項實際讀取：使用者 list、節點 list/get、預先授權金鑰 list、API 金鑰 list、政策 get/check/diff、健康檢查。九項均無 `isError`；健康檢查的 `databaseConnectivity=true`。政策 `check`／`diff` 使用不套用的候選內容。關閉寫入授權後，客戶端只看見六個具讀取能力的工具。 |
| 寫入防護 | 透過 MCP 直接呼叫 `headscale_users create`、`headscale_routes_replace`、`headscale_debug_node` 均被閘門拒絕；前後使用者清單數量相同（2）。未對正式後端執行寫入。 |
| 後端中斷與恢復 | 將此 Add-on 的後端設定暫時改為不可達埠，管理健康狀態回 `unreachable`；恢復原服務網址後回 `reachable`，子行程重新 ready。沒有停掉 Headscale 服務。 |
| 重啟與資料 | `ha apps restart` 後九項讀取及三項寫入拒絕仍通過；另一次重啟前後，MCP token 的 SHA-256 完全一致。 |
| 局部備份還原 | 用 Supervisor 建立僅含此 Add-on 的冷備份，對同一 Add-on 執行局部還原。還原後設定可連到原後端、MCP token 雜湊相同、`writes_enabled=false`、精確寫入授權數 0；`/data/mcp/state.json` 為 UID 10001、0600。九項唯讀與三項拒寫再次通過。 |

清理已完成：專用 Headscale API 金鑰到期前主動撤銷，重放得 401；局部備份、臨時 HA 使用者、測試 Add-on 及其資料、本地測試來源、臨時網路規則都已刪除。這份紀錄不包含 token、密碼、cookie、金鑰、備份內容或私有拓樸。

**界線：** 此次 HAOS 驗收使用暫載的本地 Add-on；Store PR 合併後的商店安裝、正式 HA、外部 MCP 客戶端、瀏覽器 iframe 操作及 29 個原生 API 的逐項實際寫入未由本測試證明。29 個原生 API 的覆蓋清單與容器／模擬後端測試屬來源與映像層證據。`packaging/p9_plan.py` 目前只將 `supported-bounded` 納入計畫，Headscale 的 `supported-full` 工具會得到空的 reads；這次九項唯讀用真實 MCP SDK 明確列出，沒有把空計畫當通過。
