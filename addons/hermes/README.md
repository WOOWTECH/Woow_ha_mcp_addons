# WOOW Hermes MCP（實驗／未發佈）

獨立 amd64 Add-on；固定候選版 **0.1.0**。此 manifest 可被 HA 探索，**不代表 GHCR
映像已存在**。此批沒有映像建置或 HA／真實 backend E2E。

來源工具 11 個，支援 7 個，暫不支援 4 個；不是完整功能遷移。
管理 GUI 已本地 Core 整合（七類合計184/65/119），但本產品 production verifier fail closed，現在不能正常設定後端或取得 token。
`homeassistant_api: false`，不可自行提高權限解鎖。

請先看 [本產品操作](DOCS.md)、[變更紀錄](CHANGELOG.md)、
[共用繁中指南](../../docs/operations/guide.md) 與 [逐名工具對照](../../docs/tool-surface.md)。
