# n8n 操作說明

## 現況與範圍

**0.1.0 已公開（experimental）**：映像 `ghcr.io/woowtech/amd64-mcp-n8n:0.1.0` 由候選 f75fe32 建置，通過 container/mock 與 supply-chain gate（2026-10-05），可從本 repository 的 HA 商店安裝。**HA 試點部分通過**（2026-10-05，一台 HA 實機）：管理員 Ingress 面板、Bearer 拒絕與 token 輪替／撤銷、未設定後端時的本機工具 MCP E2E、Add-on 重啟與 MCP child 異常重啟、資源量測；**尚未測**：真 n8n 後端工具、寫入防護、後端斷線、backup/restore、non-admin、升版。
**路徑 A 權限已批准**：僅此新 n8n 試點 `homeassistant_api: true`，其他六類 false。
正式 fixed-WS verifier 已實作並經 component review；管理 HTML/assets/API 與 UI 已本地整合。
本地真 bootstrap→guard→n8n→provider fake WS／Chromium 已覆蓋設定與 token 操作；
真 HA 上管理員 Ingress 與 token 操作已通過（見上）；整合獨立規格及新安全審查仍待完成。
不得注入 test verifier 或直接編輯 state 解鎖；`panel_admin` 不是角色授權。

此 token 授予**廣泛 Core 管理能力**（使用者管理、可能透過服務間接影響
Supervisor／host），不是可強制的唯讀角色權限。批准不授權所有 HA 變更，亦不
允許修改／重啟既有 HA／後端。hassio_api/auth_api 保持 false，role 省略／預設，
protection mode 保持 on，無新增 host mounts、Docker socket 或 capabilities。

核准 verifier 固定連線 `ws://supervisor/core/websocket`，只查 `config/auth/list`；
不接受 options/state/client/env 覆寫 URL／command。runtime `SUPERVISOR_TOKEN`
只傳給 n8n 管理程序，不入 config/options/argv/log，不回傳 client；n8n child
以 allowlisted env 剝除；實際同 UID child 在 post-exec guard 下讀 parent procfs/mem 被拒（本地非 HA）。可信 Ingress socket peer＋唯一 user ID 必須
匹配目前 active、人類 owner 或 system-admin；敏感操作前 fresh query、無正向
快取，停權／降權／缺失／timeout／錯誤一律 fail closed。role query 不保證即時
撤銷 browser Ingress session 或已在執行的跨系統操作。詳見共用驗收文件。

本產品 runtime：**n8n-mcp 2.91.0 / Node 22.23.2**。完整來源 28 tools，局部支援 13，
暫不支援 15；七類合計 184/71/113，**不是 full functional parity**。
文件/search/get_node、workflow list/minimal read、folder list/create/rename，加上 local validate_node/validate_workflow（manualTrigger/noOp 空參數圖）。`n8n_create_workflow` 僅建立2..20節點 inactive draft，不允許 code/URL/credentials/settings/activation；必須 exact grant，legacy global 不授權。delete_workflow 与 folder writes 權限不變。
B3 新增 tags catalog（只掃第一頁最多250、本地query/limit）、executions list metadata（API includeData=false、最多100）、health status（服務availability，不證明APIkey權限），以及 folder get（明確非personal project/folder IDs、無workflow內容）。新API及get缺URL或key均在child send前拒絕；unconfigured本機docs/search/validators仍啟動。health不讀npm/official-MCP/settings、不回URL/config/env/metrics/version；既有credential health monitor不變。B3待獨立SPEC→NEW SECURITY。
逐名 schema／預設／operation／啟用限制／deferred reason 以
[工具對照](../../docs/tool-surface.md) 與 [machine manifest](../../docs/tool-surface.json)
為準。未知與 withheld tools 即使開啟 writes 也不放行。

## 後端與設定主權

一個 Add-on 只有一組後端：**backend_url、backend_key（API base 不附 /api/v1）**。
後端憑證／URL、token、policy、顯式 client endpoint 由 GUI/state 擁有；HA options
目前為空，不放 credentials、不覆寫 state。UI 支援保留／完整替換／確認清除與三維健康，
**本地串接不代表已通過 HA**。第一個核准試點，僅受限非正式 workflow key；sql.js fallback，npm ci --ignore-scripts；沒有 runtime npm download。

工具頁依實際 v3 metadata 顯示 exact tool/operation grants；保存取代全部
`enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；失配／過期契約停止保存。
舊 delete_workflow global true 會顯示有效授權；保存轉為 exact grants，不靜默留寫入。
113 個延期工具是透明內部 backlog，並非完整遷移完成。

## 網路與認證

- `8099`：Ingress-only，無主機 mapping；不是 MCP endpoint。
- `8081/mcp`：Bearer Streamable HTTP；`8081/tcp: null` 預設不公開 LAN mapping。
- `3000`：child loopback-only，永不暴露。七容器內部 ports 可相同，LAN host ports 必須各異。
- Session：所有 client **共用 20 個**同時 session，閒置 10 分鐘回收。client 用完要送 `DELETE /mcp`（帶 `Mcp-Session-Id`），額滿時 initialize 回 429「Session limit reached」。MCP child 重啟（含 Add-on 重啟）後舊 session 失效，client 需重新 initialize；token 不變。
- 使用實際安裝後 DNS placeholder，不能猜 repository hash 或從 iframe origin 推導。
  [client 範例](../../docs/operations/clients.md) 不含真實秘密。

## 操作、健康與更新

Stock image `init: true`；保護模式維持 on。bootstrap 只建立新 `/data/mcp`，之後
runtime/child uid/gid10001；0700 directory、0600 state。既有 wrong-owner restore
停止不接管。管理／child／backend 三種 health 不同；backend outage readiness503
不重啟 Add-on，故意不設 watchdog。詳見 [操作指南](../../docs/operations/guide.md)。

更新須手動、固定版本且先讀 [CHANGELOG](CHANGELOG.md)；只有本 Add-on cold backup
會短暫停止 MCP，**不停止既有 backend／Core／Supervisor**。完整 `/data/mcp` backup
含秘密，限制存取／加密保管，不入 Git 或 artifacts。v1/v2 升 v3 保存設定並新增空 exact grants；v3 回退需相容的更新前
backup，不能只降 image 或改 schema。依 [更新備份回復](../../docs/operations/update-backup-rollback.md)
與 [失敗接受條件](../../docs/operations/acceptance.md) 逐產品驗證。

## 發佈與尚未通過關卡

source/license/secret、image 已通過 gate；管理員 Ingress、同 HA client 本機工具、
CPU/RSS/latency 已有 HA 證據。仍需真 n8n 後端與受限 credentials、non-admin、LAN client、
stream、backup/restore、升版證據。第一個核准試點，僅受限非正式 workflow key；sql.js fallback，npm ci --ignore-scripts；沒有 runtime npm download。
[發佈關卡](../../docs/operations/release.md) 預設關閉；其他產品通過不能替本產品背書。
