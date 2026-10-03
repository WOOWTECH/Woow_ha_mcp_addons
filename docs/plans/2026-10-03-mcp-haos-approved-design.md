# HAOS MCP Add-ons：已確認設計決策

狀態：使用者已確認範圍，其餘採一次性問卷的建議答案。這是需求與設計基線，不是實作、安裝或驗收完成報告。

## 1. 目標與範圍

每台 HA 自行選擇安裝所需 MCP Add-on，優先服務該台的應用；允許設定 LAN 或雲端後端 URL。不是中央多租戶服務遷移，不變更既有 k3s 生產服务。

核准七類：

1. Odoo
2. Odoo Manage
3. n8n
4. Hermes
5. OpenDesign
6. EMQX
7. LiteLLM

**排除 Kubernetes MCP 與 Vibe Kanban MCP，不保留為第二階段工作。**

第一版每類 Add-on 只有一組後端連線，不承諾同類多 profile、多租戶或任意多 instance。

## 2. 封裝與來源

- 一個新 GitHub monorepo，建議名稱 `WOOWTECH/Woow_ha_mcp_addons`（尚未確認名稱可用性或建立）。
- 七類為七個獨立 Add-on／映像，保留共用 core 與 UI，避免整包共同故障或強制一起升級。
- 原 Gitea `WOOWTECH/woow-mcp-server` 保留；遷移以新專案實作，不替換舊 k3s runtime。
- 原共用專案含五個納入範圍的 app；EMQX、LiteLLM 需補查實際來源、版本、啟動與 API 契約後整合。
- GitHub repo 與 GHCR image 採公開發佈；**先完成來源授權／敏感資訊檢查才公開**。
- 第一版直接把新 repo 加入 HA 商店；不在既有 Woow_HA_App_Store 重複提供同一產品。

## 3. 管理與資料流

### 管理面

HA 管理員 → HA Ingress → 專用 ingress listener → 共用 MCP 管理 UI/API。

- 採 HA 管理員登入，不另外維護一組 MCP 管理密碼。
- 僅受信任 Ingress 流量可取得管理身分，不得在 MCP／LAN listener 以任意 Header 繞過認證。
- UI 需支援 Ingress base path、靜態資源、API、導覽与重新整理。
- MCP client URL 應明確設定／產生，不使用 Ingress iframe 的 window.location.origin 推測。

### MCP 資料面

同機 AI／LAN client → 獨立 MCP listener → Bearer 驗證與 server-side 工具權限檢查 → MCP runtime → 設定的後端。

- 同台 HA 的 Pi／Omnigent／Hermes 與 LAN MCP client 為必要驗收場景；具體已安裝 client 與 transport 相容性需實測。
- 外網存取為可選啟用；預設不建立公網入口。若後續啟用，另確認 TLS、網域與路由。
- 每個 Add-on 一把獨立 Bearer token，能重新產生／撤銷。不採 URL-path token 為新部署契約。
- 第一版不承諾每 client 一把 token 或 OAuth／特定 SaaS client 相容性。
- 預設唯讀；寫入工具由管理員明確啟用。限制必須 server-side enforce，不能只隱藏 UI 或工具列表。
- 既有來源不支援強制工具限制時，要補上攔截與測試後才能宣稱符合；未知工具不得默認當成唯讀。

## 4. 設定與持久化

- HA Add-on options 負責部署選項；Admin GUI 負責後端 URL／憑證、token、工具權限。
- 同一欄位只保留一個設定主權，禁止每次重啟以 options 覆蓋 GUI 設定。
- `/data` 保存 runtime config、憑證與必要狀態；敏感檔案維持最小權限、原子寫入。
- 首次 bootstrap 產生所需啟動設定與安全 token，不保留通用預設管理密碼或空 command 的假可用狀態。
- 版本 migration 要保留使用者設定，能識別不相容版本；不允許靜默改寫或回退造成損失。

## 5. Runtime 與故障處理

- 管理 process、MCP 子行程、後端連線三種健康狀態分開呈現。
- watchdog 不能只檢查無條件 ok 的管理 `/healthz`。
- 子行程退出需要可觀察的退避／重啟策略、終止訊號傳遞與孤兒行程測試。
- 後端暫時離線不能形成無限重啟循環。
- 普通 MCP 保持 protection mode，不要求 Docker socket、host PID、Supervisor admin 或 full_access。
- 備份包含敏感資料，需驗證備份／還原並限制存取；避免將 token 寫入 log、Git 或 release artifact。

## 6. 建置與發佈

- 第一版正式驗收架構是 amd64；aarch64 是後續相容工作，通過建置和實測前不得宣稱支援。
- GitHub Actions 建置，GHCR 保存固定版本映像與固定依賴；保留 monorepo root build context。
- 使用者手動更新，不預設自動追蹤 latest。
- 每次發佈提供 changelog、設定 migration／備份與回復說明。
- 公開前補齊來源 provenance、授權、必要 NOTICE，並檢查程式、歷史、映像與文件是否有秘密。

## 7. 試點與授權邊界

第一個試點：n8n MCP，使用受限測試 API key，不操作正式 workflow。

已允許：安裝／重啟／移除**本次新增的 MCP Add-on**，不修改既有服務。安裝前先確認映像、slug、port、資料目錄及回復方式，不造成與既有服務衝突。

未授權：

- 修改／重啟既有 n8n、Odoo、EMQX、HA Core 或 Supervisor。
- 自動修復既有 EMQX error。
- 變更 k3s deployment、切換既有客戶 URL、關閉舊 MCP。
- 對正式資料執行有副作用的工具呼叫。

升級、還原與故障注入先列出影響、步驟與回復方案；不得影響既有後端。只讀補查不需重問已決定的產品選項。

## 8. 驗收

不能以成功安裝或 tools/list 就判定完成。每類應有：

- MCP initialize → initialized → tools/list → 無副作用 tools/call 證據。
- 缺失／錯誤／撤銷 token 被拒。
- 停用工具即使直接 tools/call 仍被拒；唯讀預設的分類與授權驗證。
- Ingress 登入、權限、導覽、API、重新整理與正確 endpoint 範例。
- 實際支援 transport 的握手與 streaming 行為。
- 設定持久化、重啟、子行程退出、後端斷線、版本更新／回復與備份還原。
- 實際 CPU／RSS 與延遲量測，不猜測可同時運行數量。
- README、繁體中文操作文件、client 連線範例與故障排查方式。

## 9. 尚待查證的技術條件（不是重新詢問產品決策）

1. EMQX／LiteLLM 的現行來源、啟動方式、授權、依賴、transport 與認證差異。
2. HA EMQX 的 error 原因與可用測試後端。只診斷，不擅自修復。
3. LiteLLM 後端的實際部署位置、API 契約、可用受限測試權限。
4. Hermes／OpenDesign 在 HA 的 API port 與版本相容性。
5. 新 repo 名稱是否可用、可用的安全 GitHub 發佈身分與最小權限。
6. 每类測試憑證以安全方式供應；不要求在聊天重貼秘密。

對話中曾出現的 GitHub PAT 不納入文件、不直接使用；建議撤銷換新。需要 GitHub 寫入時，先確認安全憑證來源。

## 10. 執行順序

1. 補查 EMQX／LiteLLM 及來源授權、敏感資料風險。
2. 在新工作目錄整理可公開的新 repo 基線與 CI 設計，確認 GitHub 安全寫入身分。
3. 以 n8n 完成 Add-on adapter、Ingress/Bearer 分離、權限、健康與設定契約。
4. 建置、測試、旁路安裝新 Add-on，記錄完整驗收證據。
5. 推廣到其餘六類，每類獨立測試與發佈；既有 k3s 部署維持不動。
