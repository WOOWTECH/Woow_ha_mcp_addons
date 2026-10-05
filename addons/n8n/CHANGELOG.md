# n8n Changelog

## 0.1.2 — 準備中（未發佈）

- 初始化時子程序沒有回覆（例如後端連不上、子程序無法建立連線階段），gateway 改回 HTTP 503＋JSON-RPC 錯誤 `BACKEND_UNAVAILABLE`（附 Retry-After），不再給出 200 空回應與失效的 session id；串流回應只保留回覆那個事件的 id／event／retry 行，其餘事件（heartbeat、通知）不轉送；過大或格式錯誤的回覆回 502。
- bootstrap 在 HA 還原修復後，等 `/data/mcp` 通過最後檢查才印 `re-owned` 訊息；修復時暫時調高的 soft `RLIMIT_NOFILE` 修完即還原，不再沿用到管理程序。
- 映像 `ghcr.io/woowtech/amd64-mcp-n8n:0.1.2` 尚未建置；0.1.0、0.1.1 tag 不覆寫。

## 0.1.1 — 2026-10-05 公開（experimental）

- 修正 HA 還原本 Add-on 後資料變成 root 擁有、無法啟動的問題：bootstrap 只在資料剛好屬 root 時，第一遍核准並握住每個 inode、第二遍只改這些重驗過的 inode（R1 修正 d687cad、19892a3，獨立 SPEC＋安全審）。
- 映像 `ghcr.io/woowtech/amd64-mcp-n8n:0.1.1`（候選 d2e1e3b，build／container／supply-chain gate 全過）；0.1.0 tag 不覆寫。

## 0.1.0 — 2026-10-05 公開（experimental）

- B1 新增 local node/workflow validation、安全 manualTrigger/noOp inactive draft create；新 create writer 僅 exact grant，沒有 activation/code/URL/credential references。

- 新增獨立 amd64 root-context 封裝、Supervisor 2026.09.3 安全子集 manifest。
- runtime：n8n-mcp 2.91.0 / Node 22.23.2；28 個來源工具中支援 10，18 個明列 withheld，
  [工具對照](../../docs/tool-surface.md) 尚未完成功能平齊。
- 8099 Ingress-only／8081 可選 LAN／3000 loopback；保護模式、init true；不設
  backend-dependent watchdog。上游已批准路徑 A，僅新 n8n 的 homeassistant_api:true；
  其他六類 false，hassio/auth/Docker API、預設 role、host 邊界不變。
- 此例外含廣泛 Core admin 及可能間接 Supervisor／host 影響，非唯讀角色 scope，
  不代表批准其他 HA 變更。bootstrap 只把 runtime token 傳給 n8n 管理程序。
- 正式 fixed-WS provider 已 component review；UI/HTML/assets/API 已本地整合；
  真 bootstrap→guard→n8n→fake WS/browser 覆蓋設定、token、精確授權。未建置 image、HA NOT TESTED。
- 七 Dockerfiles pinned Node UI build，完整字型/MDI/licenses；整合獨立規格／新安全審查待完成。
- 資料 v3：完整 v1/v2 migration、新增空 exact grants；UI 顯示 legacy 有效授權、保存完整 grants+global false，其他產品不可匯入 n8n state。
- 手動更新前做受控 cold backup（只中斷本 Add-on，含秘密）；rollback 必須使用相容
  image+完整資料，不可盲目 downgrade。請見 [完整步驟](../../docs/operations/update-backup-rollback.md)。
- 本權限批准不清除 source/license/secret/publication/image/HA 關卡，全部維持 false；
  仍需獨立規格／新安全審查及 backend／Ingress/client／備份還原驗收。
