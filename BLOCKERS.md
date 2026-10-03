# 本地里程碑以外的阻礙

此清單不代表任何產品已通過驗收。

- **HA 管理員授權（已找到真實路徑，待權限批准）**：固定 `ws://supervisor/core/websocket` + `config/auth/list` 可查當前 user ID 的 active/human/owner/admin；最小 flag 為 `homeassistant_api:true`，但實際 token 有 broad Core admin（含潛在間接 Supervisor/host 操作），不是 role-only scope。已報上游只对 n8n 的最小例外請求；不得暗加 flag 或外推六類。若不批准，需新 trusted Core role-broker integration，涉及新增 Core 元件/可能 restart 的 scope，亦待批准。Ingress/panel_admin 不是 role。未批准前管理 fail closed，不冒稱完成；不相依 W2/W3 繼續。
- **映像建置**：本機無 Docker、Podman、Buildx。允許產出 Dockerfile/CI，但不得稱映像建置成功。
- **公開授權與來源**：W1 shared boundary 為新寫，未直接匯入 legacy shared core/UI；需逐檔 provenance/比對確認，未納入的 legacy shared license 不作新寫碼永久 blocker。若後續實際複製 shared 片段，僅對該片段追授權範圍。Odoo Manage 0.7.1 為 MPL-2.0，需對應源碼與通知義務審查；app notices、OpenDesign vendor provenance、所有依賴 SBOM/NOTICE 與 code/history/image/docs 敏感掃描仍待完成。新 repo 尚不公開。
- **GitHub/GHCR 身分與名稱**：公開 lookup 404 不證明名稱可用；WOOWTECH 是 user account。需上游安全供應最小權限 publisher（repo 寫入、package publish；優先 ephemeral GITHUB_TOKEN）。不使用曾曝光 PAT、不讀 credential 檔、不在聊天貼秘密。
- **受限測試後端**：每類需安全傳入只供非正式資料的 API key/DB 身分；n8n 首個試點不得操作正式 workflow。只給需要的 read API；write測試限 mock 或經批准測試環境。
- **EMQX**：HA 既有 error 根因無足夠去密證據，不修復、不重啟。需另可用的測試 REST API v5 後端。
- **LiteLLM/Hermes/OpenDesign**：LiteLLM 真實後端版本/部署/API權限，Hermes HA API port/version，OpenDesign daemon port/auth需確認；不從 UI Ingress port 猜 API。
- **真實驗收**：HA 安裝/Ingress/同機及 LAN client/MCP E2E/備份還原/目標 CPU RSS 延遲均須上游批准並實測。本團隊停在本地里程碑。
