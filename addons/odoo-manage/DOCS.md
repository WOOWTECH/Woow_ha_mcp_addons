# Odoo Manage 操作說明

## 現況與範圍

**0.1.4（experimental）**：映像 `ghcr.io/woowtech/amd64-mcp-odoo-manage:0.1.4` 由候選 73a40eb 建置，通過 container/mock 與 supply-chain gate（2026-10-06）；修正見 [CHANGELOG](CHANGELOG.md)，2026-10-06 已在測試 HA 回歸（[0.1.4 回歸紀錄](../../docs/operations/ha-test-0.1.4.md)；0.1.3 見 [0.1.3 回歸紀錄](../../docs/operations/ha-test-0.1.3.md)）。管理面板經 HA 管理角色驗證後可設定後端。0.1.1 於 2026-10-05 已在測試 HA 以真 Woow Odoo 18 實測（[HA 實測紀錄](../../docs/operations/ha-test-0.1.1.md)）：讀取 5 個、寫入 6 個全部拒絕通過。0.1.1 的已知問題（後端連不上時 initialize 回 200 但沒有內容、之後 404 `Session not found`）已在 0.1.2 修正：改回 HTTP 503＋`BACKEND_UNAVAILABLE`（不給 session id、Retry-After 5），後端恢復後重新 initialize 即可。最小權限帳號的 `list_models` 回空清單。同一台 HA 上的 Woow Odoo 預設擋掉 MCP 容器的連線（nginx `lan_networks`），需另行放行。0.1.0 的面板 fail closed，請使用 0.1.1。
0.1.1 起與 n8n 相同（負責人 2026-10-05 核准 `homeassistant_api`）：管理程序以 runtime `SUPERVISOR_TOKEN`
連固定 `ws://supervisor/core/websocket`，只查 `config/auth/list`，確認 Ingress 使用者是 active 的 owner 或
system-admin 才放行；token 只給管理程序，child 不繼承。此 token 具**廣泛 Core 管理能力**，負責人已知情核准。
不得注入 test verifier 或直接編輯 state 解鎖；`panel_admin` 不是角色授權。

本產品 runtime：**mcp-server-odoo 0.7.1**。完整來源 10 tools，局部支援 9，
暫不支援 1；七類合計 184/65/119，**不是 full functional parity**。
model list、res.partner read/search 與有界 name create/update、delete；新增 active 分組 id:count、固定 template metadata（resources/read 仍 deny）。`post_message` 須獨立 exact grant，只寫 plain internal note（mail.mt_note），無 recipients/attachments/HTML；不開 arbitrary method。後端 override 仍可有副作用，不宣稱絕無通知。
`mode=read` 不允許 writer grants；`mode=module` 要求後端 MCP module **已存在**、由 ACL 授權，
原生 YOLO=off，不安裝 Odoo-side module、不開 full YOLO。
逐名 schema／預設／operation／啟用限制／deferred reason 以
[工具對照](../../docs/tool-surface.md) 與 [machine manifest](../../docs/tool-surface.json)
為準。未知與 withheld tools 即使開啟 writes 也不放行。

## 後端與設定主權

一個 Add-on 只有一組後端：**url、database、username、api_key、mode=read/module**。
後端憑證／URL、token、policy、顯式 client endpoint 由 GUI/state 擁有；HA options
目前為空，不放 credentials、不覆寫 state。typed 表單已經 test-only role 連真 Core 驗證，
**不是正式 HA 管理可用宣稱**。初始化需要真的 backend authentication；MPL-2.0 covered source／notice 義務尚待公開分發審查。

工具頁依實際 v3 metadata 顯示 exact tool/operation grants；保存取代全部
`enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；失配／過期契約停止保存。
119 個延期工具是透明內部 backlog，並非完整遷移完成。

## 網路與認證

- `8099`：Ingress-only，無主機 mapping；不是 MCP endpoint。
- `8081/mcp`：Bearer Streamable HTTP；`8081/tcp: null` 預設不公開 LAN mapping。
- `3000`：child loopback-only，永不暴露。七容器內部 ports 可相同，LAN host ports 必須各異。
- 同一台 HA 的 Woow Odoo 18 add-on：它的 8069 只放行 `lan_networks` 來源，HA add-on 網路（172.30.32.0/23）固定排除，所以從本 Add-on 用內部主機名或主機 LAN IP 連線都會被直接斷線；只有 Host 等於它 `public_url` 主機名的請求進入 public 層（只擋 db service）。本版連線固定目的主機、不能改 Host，可行做法是讓 `public_url` 網域可解析並經 tunnel 連入，backend url 填 `https://<public host>`。**不要**把 172.30.x 加進 Odoo 的 `lan_networks`：那會讓同網路的 tunnel 取得 LAN 層權限（含資料庫管理）。
- 使用實際安裝後 DNS placeholder，不能猜 repository hash 或從 iframe origin 推導。
  [client 範例](../../docs/operations/clients.md) 不含真實秘密。

## 操作、健康與更新

Stock image `init: true`；保護模式維持 on。bootstrap 只建立新 `/data/mcp`，之後
runtime/child uid/gid10001；0700 directory、0600 state。其他錯 owner、連結或特殊檔
停止不接管。**HA 還原**：0.1.0 還原後資料屬 root、啟動被拒（2026-10-05 實測）。0.1.1 起 bootstrap 只在資料剛好屬 root 時，第一遍核准有界的一般資料夾與單一連結檔（身分＝dev／inode／ctime），第二遍只把這些重驗身分後的項目改回 10001 與 0700／0600；任何新增、移除、替換、連結或外來擁有者仍拒絕。0.1.1 已在 HA 實測（n8n，2026-10-05）：cold backup→還原後 7 秒內啟動，log `bootstrap: re-owned 2 restored entries in /data/mcp`，權杖回到備份當時的值（還原後請輪替）；其他產品用同一份 bootstrap，未逐支做還原。管理／child／backend 三種 health 不同；backend outage readiness503
不重啟 Add-on，故意不設 watchdog。0.1.4 起後端狀態只驗證能否連線並登入 Odoo（沒有 `ir.model` 讀取權的最小權限帳號也算可連線），健康檢查以自己的連線在自己的執行緒執行，不碰 session 共用的連線。詳見 [操作指南](../../docs/operations/guide.md)。

更新須手動、固定版本且先讀 [CHANGELOG](CHANGELOG.md)；只有本 Add-on cold backup
會短暫停止 MCP，**不停止既有 backend／Core／Supervisor**。完整 `/data/mcp` backup
含秘密，限制存取／加密保管，不入 Git 或 artifacts。v1/v2 升 v3 保存設定並新增空 exact grants；v3 回退需相容的更新前
backup，不能只降 image 或改 schema。依 [更新備份回復](../../docs/operations/update-backup-rollback.md)
與 [失敗接受條件](../../docs/operations/acceptance.md) 逐產品驗證。

## 發佈與尚未通過關卡

本產品仍需 source/license/secret、image、HA／真實版本與受限 credentials、
管理員及 non-admin、Ingress UX、同 HA／LAN clients、stream、backup/restore、
CPU/RSS/latency 證據。初始化需要真的 backend authentication；MPL-2.0 covered source／notice 義務尚待公開分發審查。
[發佈關卡](../../docs/operations/release.md) 預設關閉；其他產品通過不能替本產品背書。
