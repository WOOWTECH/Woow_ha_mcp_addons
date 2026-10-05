# LiteLLM 操作說明

## 現況與範圍

**0.1.0 已公開（experimental）／未做 HA E2E**：映像 `ghcr.io/woowtech/amd64-mcp-litellm:0.1.0` 由候選 f75fe32 建置，通過 container/mock 與 supply-chain gate（2026-10-05）。本版管理面板 fail closed（見下），裝上 HA 也無法設定後端，請先不要安裝。
只有新 n8n 已獲路徑 A 批准，正式 provider 已實作並經 component review；
共用 UI 已本地 Core 整合，但此批准不適用本產品，無正式角色 verifier，管理 fail closed；
目前無正常後端設定或 token reveal/rotate 路徑。不得改權限、注入 test verifier 或
直接編輯 state 解鎖。`panel_admin` 不是角色授權；`homeassistant_api` 保持 false。

本產品 runtime：**FastMCP 3.4.5 / pinned public vendor**。完整來源 40 tools，局部支援 7，
暫不支援 33；七類合計 184/65/119，**不是 full functional parity**。
models/readiness、team metadata；有界 team create/alias update/team delete/model delete 需 exact grants。chat、key/user 任意 mutation、付費 provider health 不開放；private health 僅 GET /v1/models。
逐名 schema／預設／operation／啟用限制／deferred reason 以
[工具對照](../../docs/tool-surface.md) 與 [machine manifest](../../docs/tool-surface.json)
為準。未知與 withheld tools 即使開啟 writes 也不放行。

## 後端與設定主權

一個 Add-on 只有一組後端：**url、master_key**。
後端憑證／URL、token、policy、顯式 client endpoint 由 GUI/state 擁有；HA options
目前為空，不放 credentials、不覆寫 state。typed 表單已經 test-only role 連真 Core 驗證，
**不是正式 HA 管理可用宣稱**。使用批准之受限測試 credentials，master_key 欄位名稱不代表批准全權正式 key；實際 backend 位置與版本待確認。

工具頁依實際 v3 metadata 顯示 exact tool/operation grants；保存取代全部
`enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；失配／過期契約停止保存。
119 個延期工具是透明內部 backlog，並非完整遷移完成。

## 網路與認證

- `8099`：Ingress-only，無主機 mapping；不是 MCP endpoint。
- `8081/mcp`：Bearer Streamable HTTP；`8081/tcp: null` 預設不公開 LAN mapping。
- `3000`：child loopback-only，永不暴露。七容器內部 ports 可相同，LAN host ports 必須各異。
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

本產品仍需 source/license/secret、image、HA／真實版本與受限 credentials、
管理員及 non-admin、Ingress UX、同 HA／LAN clients、stream、backup/restore、
CPU/RSS/latency 證據。使用批准之受限測試 credentials，master_key 欄位名稱不代表批准全權正式 key；實際 backend 位置與版本待確認。
[發佈關卡](../../docs/operations/release.md) 預設關閉；其他產品通過不能替本產品背書。
