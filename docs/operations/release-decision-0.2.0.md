# 0.2.0 候選發佈紀錄（完整版）

狀態：準備中，尚未發佈或部署；release gates 維持關閉。前一版 0.1.14 已於 2026-10-14 發佈（[0.1.14 紀錄](release-decision-0.1.14.md)）。

## 決定

使用者 2026-10-15：HA MCP add-on 做「完整版」，與原始 GitHub／Gitea MCP server 及 PaaS woow-mcp-server 功能對齊，
所有工具（含高風險）全部開放、全部預設開啟，管理介面可逐一關閉；既有安裝升級時遷移成全開。七支共用版本規則，一致升 0.2.0
（major 行為改變：預設寫入、工具面、state schema）。同日使用者再決定四項：Odoo `ODOO_MCP_ALLOW_UNKNOWN_METHODS=1`、
`MCP_CHATTER_DIRECT=1`；後端錯誤回傳原始訊息（與 PaaS 一致），但 add-on 持有的憑證要換成 `[REDACTED]`；升級遷移時清空停用清單。

## 變更

一、Gateway 直通子程序的完整工具面（`packages/mcp-admin-core/mcp_admin_core/surface.py`、`policy.py`、`products.py`、
`apps/n8n/n8n_adapter.py`）：七支開放 Odoo 41、n8n 28、Hermes 11、OpenDesign 15、EMQX 39、LiteLLM 40、Nextcloud 9 個工具。
tools/list 用子程序自己的 inputSchema（0.1.6 provider-safe 正規化；讀不懂時列為 object）；tools/call 參數原樣轉送，由子程序驗證。
gateway 仍檢查：名字在分類名單內、未停用、寫入工具或混合工具寫入 operation 的 grant（省略 operation 時為原始碼預設的讀取，
未分類的值需該工具全部寫入 grant）、參數是物件。分類（read／write／mixed／unverified）由 `scripts/tool_inventory.py` 移入
`surface.py`，測試比對 pinned 原始碼名單。

二、預設與遷移（`products.py`）：state schema 4。新 state 與從 3（或 1／2 經 3）遷移一次的 state：每個寫入 grant 開、
`writes_enabled=true`，0.1.x 的停用清單清空（升級後所有工具全開），token、child token、連線、對外端點保留；之後照存檔載入，
管理員之後停用的工具與取消的寫入都保留。Odoo Manage（已下架）不變。
0.1.x 不接受 schema 4：回退要還原升級前備份（[更新、備份與回復](update-backup-rollback.md)）。

三、子程序全開（`apps/*`）：
- Odoo：PaaS 的 `fix_cross_session_token_store`、`fix_direct_writes` 逐字收進 `apps/odoo/patches`，Dockerfile 在 uv sync 後套用並檢查
  marker，`packaging/unit.sh` 同樣套用；launch.py 對 patch 後的 tools_write／server_core 守門。環境 `ODOO_MCP_ENABLE_WRITES=1`、
  `ODOO_MCP_ALLOW_DIRECT_WRITES=1`、`ODOO_MCP_ALLOW_UNKNOWN_METHODS=1`（任意方法，含 `action_confirm`、`action_post` 等）、
  `MCP_CHATTER_DIRECT=1`（chatter 直接送出；帶 approval／confirm 也照樣送出）。未套用
  `fix_remove_3step_tools`（它在直接寫入開啟時會隱藏 preview／validate／execute_approved_write）。移除 B1 aggregate 投影與
  B2 res.partner 限定（`apps/runtime/odoo_b2_scope.py` 刪除）。
- EMQX／LiteLLM／Nextcloud：READONLY=false、Nextcloud ALLOW_DELETE=true，DISABLED_TOOLS 只放停用或沒有 grant 的寫入工具。
- Hermes、OpenDesign、LiteLLM vendor 的輸出投影移除，回到 PaaS 614ae66／Woow_litellm_mcp_server 4d41903 的行為；
  `apps/runtime/output_policy.py`、LiteLLM `metadata.py`、n8n `metadata_reads.cjs` 刪除；n8n 建立 workflow 回原始結果。
- 後端錯誤回傳原始訊息：`apps/runtime/backend_policy.py` 的 Odoo XML-RPC fault 原樣交給 odoo-mcp，HTTP 傳輸把非 2xx 回應交給子程序
  自己處理（原本丟出不帶 body 的 BACKEND_HTTP_ERROR），傳輸失敗為「代碼: 原因」；EMQX、LiteLLM 的 `errors.py` 與 Nextcloud 的
  `tools.py` 回到上游，Nextcloud `client.py` 恢復回報 server message；n8n 移除固定訊息與 handler 錯誤邊界；`odoo_read_exists`
  回原因。gateway 在每個轉送的回覆（JSON 與 SSE、result 與 error）中把 add-on 持有的憑證換成 `[REDACTED]`（`redact.py`）。

四、請求上限 256 KiB → 16 MiB（`gateway.MAX_REQUEST`），body 讀取時限 10 → 60 秒（仍在權杖檢查之後）。

五、Odoo `chatter_post`：0.1.14 以前照說明把 preview 的 `approval` 原樣帶回必定 -32602。完整版直接轉送參數，且
`MCP_CHATTER_DIRECT=1` 直接送出；`tests/test_expansion_runtime.py` 以真實子程序實測直接送出、帶 approval／confirm 也送出。
0.1.x 的有界模型也一併修正（保留在 BOUNDED_TOOLS）。

六、管理面板：工具頁顯示預設全開的風險提示；儲存仍取代全部 grants 並送 `writes_enabled:false`。

## 刻意保留的安全層

權杖（Bearer、密鑰網址 404、撤銷即時生效）、log 遮罩、session 規則、32 個 slot、請求／回應大小上限、SSE 與 JSON-RPC 回覆整形、
子程序出站（DNS pin、只連設定的後端、redirect／proxy 拒絕、TLS、metadata 位址拒絕）、回覆中的憑證遮罩、原始碼 digest 守門、
子程序環境隔離與私有 readiness probe、管理面板 HA 管理員驗證與 CSRF、停用與寫入 grant。

## 測試

`tests/test_full_surface.py`（名單＝pinned 原始碼、七支真實子程序 tools/list 完整且 schema provider-safe、參數原樣、13 MiB 請求、
非物件參數、未知／停用／未授權、混合 operation grant、密鑰網址 404）、`tests/test_writes_default_on.py`（新 state 全開、
schema 3／2／1 遷移一次、撤銷後重啟維持、面板 UI 序列化）、`tests/test_chatter_approval.py`、`tests/test_expansion_runtime.py`
（含 Odoo `execute_method` 直接寫入與 `action_confirm`、chatter 直發）、`tests/test_raw_backend_errors.py`
（憑證清單與 Basic 形式、gateway 遮罩 result 與 error、真實 Odoo 子程序回 AccessError 原文且密碼遮罩、真實 LiteLLM 子程序回錯誤 body
且 master key 遮罩）。移除只驗證已拆除縮限的測試（LiteLLM metadata、Odoo B2 runtime／scope、n8n B3
runtime／boundaries／unicode、OpenDesign slow reads）；其餘 0.1.x 有界模型測試改針對 BOUNDED_TOOLS。

## 後續

主控核對 hosted CI、builder admission 與候選 image／test／scan receipts，再在 PaaS HAOS VM 實機驗收：0.1.x 升級的遷移結果
（寫入全開、停用保留）、七支完整工具實測（含高風險寫入只對測試後端）、真實 Claude.ai 連線與 tools/list 被接受、P9 前先關閉寫入。
本紀錄不宣告商用 PASS。
