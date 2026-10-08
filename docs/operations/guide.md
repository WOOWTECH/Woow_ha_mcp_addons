# 操作指南（繁體中文；experimental）

## 目前狀態與安全邊界

六份 manifest 是可從 HA 商店安裝的實驗版產品（0.1.6，映像已公開；Odoo Manage 已下架）。工具支援僅
174/67/107（六支合計：來源／支援／暫不支援；工具表另列已下架的 Odoo Manage），[完整逐名工具表](../tool-surface.md)
包含混合 operation、預設、啟用限制及未完成原因。唯讀分類不是由名字推測，
unknown／未審工具即使開啟寫入仍拒絕。六支都有有界 writers／mixed operations，
仍不是完整 writer parity；107 個暫不支援是明列內部工作，不假稱全部完成。

**映像已發佈（目前 0.1.6），0.1.1–0.1.6 已在測試 HA 回歸（[0.1.6 紀錄](ha-test-0.1.6.md)）。** 六支都批准
`homeassistant_api: true`（n8n 自 0.1.0、其他自 0.1.1 起，負責人 2026-10-05 核准）；正式 fixed-WS provider 已實作並經審查，
六支共用同一個驗證器（n8n 經 `apps/n8n/run.py`、其他五支經 `run_product.py`），下方的 Core 版本清單六支一體適用。
管理 HTML/assets/API 與 UI 已串接：真 HA 上已實測 owner 經 Ingress 的後端設定與 token reveal/rotate/revoke（管理 API），
一般使用者 403；瀏覽器 UI 只在本地 Chromium（真 Core + fake HA transport）測過。
不要直接修改 state、搬入 test verifier 或映射8099 LAN。

此 token 具有**廣泛 Core administrator 能力**，包括使用者管理及透過服務間接
影響 Supervisor／host，非可強制的「唯讀角色查詢」權限。只查角色的程式限制
不能縮小 token 遭竊後的能力。批准不是修改所有 HA 的授權，不可變更／重啟
既有 Core、Supervisor、後端或主機。`hassio_api:false`、`auth_api:false`、預設
Supervisor role、protection mode 不變；不新增 Docker socket、host PID/network、
full_access、devices 或共享 HA 設定／備份 mounts。

核准 provider 只能用固定 `ws://supervisor/core/websocket` 發 `config/auth/list`，
URL／command 不可由 options、state、client 或環境覆寫。必須核對可信 Ingress
socket peer 與唯一 forwarded ID 的目前 active、人類、owner 或 system-admin
身分；敏感操作於 body／lock 等等待後再次 fresh query，無正向角色快取。
停權／降權／缺失／錯誤／timeout 一律拒絕。角色撤銷不等於立即撤銷既有 browser
Ingress session，亦不保證已在執行的跨系統操作能原子撤銷。provider 與 token 傳遞在 0.1.1 經獨立
SPEC＋安全審，範圍只有這兩段程式，不含映像、HA 或發佈（[0.1.1 發佈紀錄](release-decision-0.1.1.md)）。
映像與真實 admin/non-admin 驗收對應 `RELEASE-GATES.json` 的 `products.<app>.image`／`ha`：測試 HA 已實測
owner／non-admin（0.1.1–0.1.5），但這些 gates 和其他人工 gates 一樣仍全部 false。

**支援的 Core 版本**：六支的管理面板只在該版 add-on 審查過的 HA Core 版本運作（`ha_role._HA_VERSIONS`；0.1.6：2026.7.2–2026.9.4
與 2026.10.0，0.1.5 及更早只有 2026.7.2；審查紀錄見 [ha-role-core-contract](../ha-role-core-contract.md)）。其他版本（含之後的 patch
與 beta）整個管理面板都回 403，看起來和「不是管理員」完全一樣（add-on 紀錄也沒有訊息）；MCP 端點（Bearer token）不受影響。
新的 Core 版本要等 add-on 發新版才支援，升級 Core 前請先對照這份清單。

## 批准後的安裝檢查表（不是現在的操作授權）

1. 取得上游對**確切新 Add-on** source SHA、映像 digest／固定版本、slug、
   repository 身分、8099/8081、獨立 `/data` 及回復計畫的批准。
2. 發佈者先證明 GHCR 匿名 pull 與映像 gate（見各版 `release-decision-*.md`）。測試 HA 加入的商店網址是
   `https://github.com/WOOWTECH/Woow_ha_mcp_addons#claude-delivery`（[逐步指令](n8n-pilot-commands.md) H1）。
   Supervisor 以網址轉小寫後的 sha1 前 8 碼當 repository slug：這個網址是 `1ee8889c`，app slug 為
   `1ee8889c_woow_mcp_<product>`。換網址（例如拿掉 `#claude-delivery`，slug 會變成 `f1d622e7`）會讓所有 app 的
   slug 跟著變，不是原地更新；已安裝者維持原網址，要換網址需另做資料遷移計畫（見[更新、備份與回復](update-backup-rollback.md)）。
3. 首試 n8n，使用批准的非正式 workflow 受限測試 key。其他五支逐支批准。
4. 保留 protection mode（預設 on）；`protected` 是使用者狀態，不是假造
   manifest key。手動更新設定（auto-update off）要在安裝後確認；`boot: manual`
   只控制開機啟動，不代表自動更新開關。
5. MCP 8081 預設主機映射為空；如需 LAN，選未使用的唯一 host port 並檢查
   防火牆。各容器內相同 8081/8099 不衝突；主機映射不可重複。
6. 8099 僅 Ingress（真實 peer `172.30.32.2`）；3000 僅容器 loopback，永不對外。
   不使用 Ingress origin 作 MCP endpoint。[client 文件](clients.md) 必讀。

HA options/schema 目前為空 `{}`：runtime 沒有實作 options 讀取，不提供假的
log_level 開關。後端 URL、憑證、token、endpoint、工具政策由 GUI/state 擁有，
各支經有效 Ingress/provider 才有設定路徑；重啟不能用 options 覆寫。每支一組後端。
UI 保留不送 PUT；替換完整 typed connection，空白秘密不代表保留；清除整組需確認。
已下架的 Odoo Manage：mode=read/module，module 要求後端已有 MCP module，不做模組安裝或 full YOLO。
工具頁保存完整 `enabled_write_tools`、`writes_enabled:false`，disabled 優先。
舊 global 只授權原 n8n/OpenDesign 兩個 legacy writers，UI 顯示其有效狀態並可精確撤銷。
撤銷 exact grants 必須送空陣列，global false 本身不撤銷 grants。詳見 [v3契約](../tool-expansion.md)。
不要在 options、URL query、Git、issue、聊天或 release artifact 放秘密。

## 映像／資料契約

- 固定 Python **3.13.16** slim-bookworm，符合既有 `>=3.13,<3.14`；未宣稱
  3.12 或 aarch64。核心 `.venv` 與 n8n 以外各支的 child `.venv` 分開，FastMCP 的
  Starlette 1.7.0 不覆蓋核心 0.49.3。n8n 使用 Node **22.23.2**、npm lock、
  `npm ci --ignore-scripts`，保留 sql.js fallback；不下載 native addon/script。
- Stock image 搭配 Supervisor `init: true`；不是 s6。映像啟動只有 bootstrap
  短暫 root，用 no-follow directory fd 建立**新的** `/data/mcp`，設定 10001:10001
  與 0700；不碰 Supervisor options。一般情況不遞迴 chown、不接管既有錯誤 owner；唯一例外（0.1.1 起）
  是既有 `/data/mcp` 剛好屬 root（HA 還原的結果）：先完整檢查只有一般資料夾與單一連結檔、擁有者只能是
  root 或 10001、數量與深度有上限，再以 no-follow fd 一次改回 10001:10001、0700／0600；其他情況照舊停止。
  隨後清空 supplementary groups、setgid/setuid 10001、no_new_privs，再 exec 固定
  management launcher。它在 final exec 後先驗證 dumpable=0／core limit=0，再以
  runpy 進入 runtime，不再 exec 重設 guard。正式程序與 child 非 root。
  [安全界線](hardening.md) 說明同 UID procfs/memory 測試與未測 HA 限制。
- 既有 `/data/mcp` 必須已屬 10001:10001/0700；state 是 0600。HA 還原**不保留** owner／權限
  （2026-10-05 實測：root 擁有、檔案 0644）；0.1.0 因此停止（已知問題），0.1.1 起依上述例外改回。
  其他不符合即停止並由核准維護流程恢復，不自動寬鬆 chmod。
- Bootstrap 產生獨立強 token，沒有共用密碼。缺 backend 的 n8n 以外各支不 spawn child
  或探測外部服務；n8n 可啟動內建文件 runtime，但 backend readiness 仍 503。
- child command/env 固定；bootstrap 只把 runtime `SUPERVISOR_TOKEN` 傳給管理程序（0.1.0 只有 n8n；
  0.1.1 起每支皆是，負責人 2026-10-05 核准），不寫 config/options/argv/log；child 以白名單 env 啟動、不繼承。proxy、Python
  注入及 provider URL／command 覆寫均不傳遞。n8n child 已使用不含 machine token 的 allowlist；
  本地實際 packaging→guard→run→provider fake-WS 與真正同 UID Node child 的 parent procfs/mem 拒絕已覆蓋。
  這不是 HA AppArmor／image 驗收。
  child 不能繞過 outer Bearer／逐請求 server-side policy。

每個 Dockerfile 的 pinned Node UI build stage 只複製完整 dist（含字型/MDI/licenses）進各自映像；
測試 fixture、node_modules、browser reports 不進 runtime。缺 build 如實503。
每頁／asset 仍需 trusted peer、唯一 ID、fresh role，no-store/CSP 保留同源 HA iframe。

## 健康與故障

分別觀察管理程序、child/protocol、backend reachability，不把綠色 PID 當後端成功。
`GET :8081/health/ready` 僅回 `{ready:boolean}`；未設定或 backend offline 為 503。
**故意省略 Supervisor watchdog**：此 endpoint 依賴 backend，不可拿來重啟容器。
需待真正 local-supervisor liveness endpoint 設計與測試才可新增 watchdog。
child 結束有有界退避／恢復，backend 中斷不 restart child/container。

公開錯誤如 `BACKEND_BUSY`、`BACKEND_TIMEOUT`、`BACKEND_STREAM_ERROR`、
`BACKEND_INVALID_RESPONSE`、`BACKEND_HTTP_ERROR` 表示受限／中斷／後端契約錯誤；
不要開 debug 傾倒 credentials 或原始 body。DNS 全 answers 先驗證，再數字位址
fallback；metadata/link-local/混合非法 answers 拒絕。合法 LAN/ULA/public 不等於
已驗證實際 backend 相容。HTTPS 必須驗證憑證，不跟 redirect、不用 proxy bypass。

先依 [故障驗收](acceptance.md) 記錄安全摘要。既有後端（例如 EMQX）的錯誤不授權自動修復；
不得重啟／修改既有後端、HA Core、Supervisor 或 k3s。容量只能在目標硬體量測，
不能從本地測試猜同時可裝數量。
