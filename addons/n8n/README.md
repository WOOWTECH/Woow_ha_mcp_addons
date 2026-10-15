# Woow n8n MCP Server

獨立 amd64 Home Assistant Add-on：把 n8n 的部分工具以 MCP（Streamable HTTP）提供給 AI client。
目前發佈的版本、映像與在 HA 上的實測結果見 [本產品操作](DOCS.md) 開頭。

- 工具：上游 28 個中支援 13 個，全新安裝時讀取與寫入預設都開啟，寫入可在管理面板逐一關閉（已安裝者升版不變），其餘明列不支援
  （[逐名工具對照](https://github.com/WOOWTECH/Woow_ha_mcp_addons/blob/claude-delivery/docs/tool-surface.md)）。
- **寫入預設開啟的風險**：MCP client（例如 AI 助理）不需管理員先授權就能呼叫寫入工具，權杖或 Claude.ai 密鑰網址外洩也一樣；安裝後請到管理面板「工具與寫入授權」關掉不需要的寫入，後端帳號用最小權限（[說明](https://github.com/WOOWTECH/Woow_ha_mcp_addons/blob/claude-delivery/docs/operations/guide.md#寫入預設開啟)）。
- 連線：n8n 的網址與 Public API key。
- 管理面板在 HA 側邊欄（Ingress），只有 HA 的 owner 或系統管理員能設定後端與管理權杖；為了驗證這個身分，
  Add-on 需要 `homeassistant_api: true`，這個 token 具廣泛的 Core 存取能力。`hassio_api: false`、保護模式開啟、無 host 網路。
- MCP client 連 `8081/mcp` 並帶 Bearer 權杖；預設不對 LAN 開埠（`8081/tcp: null`）。Claude.ai 網頁版自訂連接器不能帶 header，改用管理面板產生的密鑰網址 `…/private_<token>/mcp`（0.1.14 起；網址等同密碼）。

請先看 [本產品操作](DOCS.md)、[變更紀錄](CHANGELOG.md)、[共用繁中指南](https://github.com/WOOWTECH/Woow_ha_mcp_addons/blob/claude-delivery/docs/operations/guide.md)
與 [client 設定](https://github.com/WOOWTECH/Woow_ha_mcp_addons/blob/claude-delivery/docs/operations/clients.md)。
