# WOOW n8n MCP（實驗／未發佈）

獨立 amd64 Add-on；固定候選版 **0.1.0**。此 manifest 可被 HA 探索，**不代表 GHCR
映像已存在**。此批沒有映像建置或 HA／真實 backend E2E。

來源工具 28 個，支援 13 個，暫不支援 15 個；不是完整功能遷移。
**路徑 A 權限已批准，僅此新 n8n 試點 `homeassistant_api: true`**；其他六類 false。
此 token 具有廣泛 Core 管理能力（含可能間接 Supervisor／host 影響），非唯讀角色權限，
不表示所有 HA 變更獲准。hassio/auth API 仍 false、role 預設、無新增 host 權限。
正式 fixed-WS provider 已實作並經 component review；UI/HTML/assets/API/v3 grants
已本地 Core 整合，實際 bootstrap→guard→n8n→fake WS 與 Chromium 驗證，並非 HA。
七類合計184/71/113；B3 metadata reads 待獨立 SPEC → NEW SECURITY；HA NOT TESTED，映像未建置；整合独立規格／新安全審查待完成。
不得注入 trust bypass；公開發佈關卡仍全部 false。

請先看 [本產品操作](DOCS.md)、[變更紀錄](CHANGELOG.md)、
[共用繁中指南](../../docs/operations/guide.md) 與 [逐名工具對照](../../docs/tool-surface.md)。
