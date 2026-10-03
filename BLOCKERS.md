# 本地里程碑以外的阻礙

此清單不代表任何產品已通過驗收。

- **HA 管理員授權：n8n 權限已批准，MAIN程式雙審通過，封裝guard整合／HA未實測**：上游2026-10-03T06:42Z確認使用者已知 broad Core admin（含潛在間接 Supervisor/host 能力）後，批准只對新n8n試點 `homeassistant_api:true`。固定 `ws://supervisor/core/websocket` + `config/auth/list`，runtime SUPERVISOR_TOKEN僅管理端使用，敏感操作fresh active/human/owner/system-admin查核、no positive cache、錯誤failclosed。保持hassio_api/auth_api false、default role/protection；不外推六類或既有服務。主tree真實WS provider與fresh final-action/lifecycleownership修後已獲獨立spec+新security批准（436tests）；隔離packaging已修postexec/prechild dumpable/core-limit guard並獲bounded spec+security批准，86個newfiles已按reviewed fingerprint無覆寫複製MAIN；真實bootstrap→guard→新provider＋pinned n8n child／procfs隔離與Chromium→Core聯合本地測試（owned fake WS/Ingress simulation）已通過獨立整合spec＋全新security雙審，協調者最終重跑568Python＋1聯測＋39packaging＋13UIunit＋21browser全部exit0。envstrip不是OSsandbox；本地聯測不是image/HA驗收。權限與程式均已落實，真實HA admin/non-admin/撤權/timeout與client/Ingress驗收仍待執行。
- **其他六類管理權限**：共用UI與runtime已有本地測試，但production role provider／broad Core API例外僅准n8n。六類維持fail-closed，需上游逐類批准擴用已審provider與homeassistant_api，不能假稱都可在HA管理。
- **內部功能backlog（不是外部阻礙）**：184來源工具目前55項有界支援、129項逐名延期，部分mixed工具亦非所有operation皆支援。`docs/tool-review.json`/`docs/tool-surface.md` 列安全契約、projection與測試等後續工作；普通尚未實作功能不能全推給憑證/HA/授權。此本地里程碑不等於七類完整功能migration。
- **映像建置**：本機無 Docker、Podman、Buildx。允許產出 Dockerfile/CI，但不得稱映像建置成功。
- **敏感掃描gate仍未清除，metadata誤判已有去密證明**：歷史checkpoint313ab01的7筆與最終246檔source export的8筆Gitleaks findings均逐項重新SHA256程式bytes相符，屬content-digest metadata誤判，不是已洩漏的API keys。proof在repo外reports/SECRET-SCAN-TRIAGE.md及final-source-scan-hash-proof.json，無match/secret輸出。未改scanner規則/allowlist/history/gates，實際exit1仍DENY；最窄metadata處理策略仍需security review，不能以分類證明宣稱整體source/history/dependency/image清除。
- **公開授權與來源**：W1 shared boundary 為新寫，未直接匯入 legacy shared core/UI；需逐檔 provenance/比對確認，未納入的 legacy shared license 不作新寫碼永久 blocker。若後續實際複製 shared 片段，僅對該片段追授權範圍。Odoo Manage 0.7.1 為 MPL-2.0，需對應源碼與通知義務審查；app notices、OpenDesign vendor provenance、所有依賴 SBOM/NOTICE 與 code/history/image/docs 敏感掃描仍待完成。新 repo 尚不公開。
- **GitHub/GHCR 身分與名稱**：公開 lookup 404 不證明名稱可用；WOOWTECH 是 user account。需上游安全供應最小權限 publisher（repo 寫入、package publish；優先 ephemeral GITHUB_TOKEN）。不使用曾曝光 PAT、不讀 credential 檔、不在聊天貼秘密。
- **受限測試後端**：每類需安全傳入只供非正式資料的 API key/DB 身分；n8n 首個試點不得操作正式 workflow。只給需要的 read API；write測試限 mock 或經批准測試環境。
- **EMQX**：HA 既有 error 根因無足夠去密證據，不修復、不重啟。需另可用的測試 REST API v5 後端。
- **LiteLLM/Hermes/OpenDesign**：LiteLLM 真實後端版本/部署/API權限，Hermes HA API port/version，OpenDesign daemon port/auth需確認；不從 UI Ingress port 猜 API。
- **真實驗收**：HA 安裝/Ingress/同機及 LAN client/MCP E2E/備份還原/目標 CPU RSS 延遲均須上游批准並實測。本團隊停在本地里程碑。
