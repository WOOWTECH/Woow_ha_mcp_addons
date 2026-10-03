# 公開發佈與 HA 試點關卡

這份文件不是發佈授權，也不是驗收結果。

## Gate 1：公開來源

上游必須確認以下證據，再授權建立 GitHub repo/push：

- 新 Git 歷史不含原 repo 歷史、研究 inventory、客戶部署或 runtime 設定。
- 每個導入檔案有來源 URL、commit/artifact hash、原授權、修改說明。新寫程式另記錄作者/參考來源與非複製證據；W1 共用 boundary 為新寫替代，未納入的 legacy core/UI 授權疑義不阻擋所有新碼。實際複製 legacy shared 片段才需要該片段授權確認，不能自行補 MIT 當取得授權。
- Odoo Manage `mcp-server-odoo==0.7.1` 的 MPL-2.0 notices / covered source 可取得方式與變更符合義務；所有 image/web bundles/依賴各自有正確 license，不用單一 MIT 假概括。
- tree、完整新歷史、產物、映像 layers/config、release/docs 均完成去密掃描與人工審查。自製 regex 只能是輔助，不等於完整 clearance。
- GitHub 名稱、帳號控制權及 secure publisher 確認；404 不是名稱預約。不得使用曾曝光 PAT。授權供應渠道不在聊天、repo 或文件中保存秘密。

## Gate 2：映像

- 真實 amd64 建置成功，root build context、固定 inputs、完整測試及版本/labels 檢查。
- 每類 image 獨立、tag 固定、不發布 latest、不覆寫版本；記錄 digest/SBOM/provenance。
- GHCR public 可匿名 pull 已證明（公開 repo 並不自動代表 package 公開）。
- 只能宣告已建置且測試的類型；不能以七份 YAML 宣稱七個可用產品。

## Gate 3：新 n8n Add-on 試點

上游批准前不得安裝。安裝前核对 exact image digest、唯一 slug、repository 身分、8099 Ingress-only、8081 MCP 及可選不衝突 LAN mapping、獨立 `/data`、移除/回復程序。

- 使用受限非正式 workflow 測試 API key，安全渠道注入；不修改正式 workflow。
- 管理員與非管理員都要真實測試；`panel_admin`、trusted ingress user ID、mock verifier 均不能替代 HA admin-role 證據。
- MCP initialize/initialized/list/無副作用 call；missing/wrong/revoked token；disabled 直接 call 確實拒絕；同機與 LAN client 實測。
- 在批准的測試影響範圍中測 child crash、restart、backend offline、backup/restore、migration/rollback；不重啟或改動任何既有後端、Core/Supervisor。
- 記錄目標 CPU/RSS/延遲，不猜同時可跑數量。

## Gate 4：其餘六類

逐類重複 source/build/HA/protocol/security/persistence/client 驗收，不從 n8n 成功外推。EMQX 既有 error 不自動授權修復；LiteLLM/Odoo/Hermes/OpenDesign 契約不明即停止該項，繼續不相依工作。
