# n8n 驗證工具輸出契約：修正後再對外發布

PaaS 既有 n8n 服務的 `tools/list` 有 `validate_node`、`validate_workflow` 兩份 `outputSchema`，HA 0.4.9 gateway 兩份皆無。原本兩側固定的 n8n-mcp 2.96.2 child 宣告 `validate_workflow.errors[*].details` 與 `warnings[*].details` 是字串，實際驗證器在節點群組、AI 節點及屬性錯位時回傳物件。用真 HA gateway 呼叫兩筆合成流程，Python MCP 2 與 TypeScript SDK 1.32.2 都拒絕舊 schema 下的有效結果。因此先前 PR #48 的 n8n pin 已撤回，只保留 Odoo 41 份。

PaaS [Gitea PR #103](https://git-prod.woowtech.io/WOOWTECH/woow-mcp-server/pulls/103)已於 2026-10-31 合併至 main `b3ea39c8e6b0d88d58e8ff82739c7c43a052361c`；24 項 PR／push CI 狀態全綠，包含 n8n 候選映像建置 smoke。GitHub main 亦已讀回相同 merge commit。PaaS 現有 accea 服務及平台範本 c195 的部署更新仍待執行；原始碼合併不代表租戶已升級。

HA 此來源變更先以 `91aceb072dd86ba430545b207d75ad228e27a178` 加入精確 npm 2.96.2 patch：`dist/mcp/tools.js` 原 SHA-256 `acb4d2a3ec74b5f2b41d327a93340a0f9a799e99947656afd010a76390fb10cb`，修後 `e30bddb3967661d36ae5dd8c6b5eb8b7e1b56f6053b2bb972543d7bbc4d57803`；只改兩處 details 型別，版本或來源不符即拒絕建置。隨後才把**修正後的 child** 兩份確定輸出 schema 釘入 gateway，並加到固定 fallback 清單。產品名稱、28 支工具名稱／輸入 schema、授權與其他產品中繼資料不變。來源檔案雜湊、精確 product/tool/schema binding 及執行期 ledger 均已更新。

本機用固定 child、真 gateway、假 n8n 後端及兩種真 SDK 呼叫乾淨流程、含物件型 warning 與含物件型 error 的合成流程，均通過輸出驗證；無 n8n 業務後端寫入。還需正式來源 CI、六映像發行閘門、已發布映像的同呼叫與 HAOS Supervisor 實機讀回。此來源變更沒有版本號、映像或 ws97 變更。
