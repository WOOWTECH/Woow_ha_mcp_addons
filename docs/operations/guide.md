# 操作指南（繁體中文）

## 目前狀態與安全邊界

七份 manifest 是可從 HA 商店安裝的產品（0.1.7，映像已公開；Nextcloud 自 0.1.7 起；Odoo Manage 已下架）。0.2.1 起為完整版：
七支合計 183 個子程序工具全部開放（工具表另列已下架、維持有界版的 Odoo Manage），[完整逐名工具表](../tool-surface.md)
列出分類（read／write／mixed）與寫入 grants。分類不是由名字推測；子程序新增但未分類的工具一律拒絕。
全部工具與寫入預設開啟，見下方 [寫入預設開啟](#寫入預設開啟)。

**映像已發佈（目前 0.1.7），0.1.1–0.1.7 已在測試 HA 回歸（[0.1.7 紀錄](ha-test-0.1.7.md)）。** 七支都批准
`homeassistant_api: true`（n8n 自 0.1.0、其他五支自 0.1.1 起，負責人 2026-10-05 核准；Nextcloud 自 0.1.7 起，2026-10-08 核准）；正式 fixed-WS provider 已實作並經審查，
七支共用同一個驗證器（n8n 經 `apps/n8n/run.py`、其他六支經 `run_product.py`），下方的 Core 版本清單七支一體適用。
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
owner／non-admin（0.1.1–0.1.6；Nextcloud 尚未在 HA 實測），但這些 gates 和其他人工 gates 一樣仍全部 false。

**支援的 Core 版本**：八支的管理面板只在各自已發布映像審查過的 HA Core 版本運作（`ha_role._HA_VERSIONS`；0.1.6–0.1.8：2026.7.2–2026.9.4
與 2026.10.0，0.1.9 起再加 2026.10.1，0.4.2 起再加 2026.10.2–2026.10.4，Headscale 0.4.14 再加 2026.11.0–2026.11.1、0.4.19 起再加 2026.11.2（Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 0.4.14 起加 2026.11.0–2026.11.2），0.1.5 及更早只有 2026.7.2；這六支的 0.4.13 映像仍只支援到 2026.10.4，Headscale 0.4.18 只支援到 2026.11.1；審查紀錄見 [ha-role-core-contract](../ha-role-core-contract.md)）。其他版本（含之後的 patch
與 beta）整個管理面板都回 403；0.4.1 以前看起來和「不是管理員」完全一樣（add-on 紀錄也沒有訊息），下一版起管理面板改顯示「這個 HA Core 版本尚未審核：<版本>」，
API 回 `detail.code` = `core_version_unreviewed` 與版本，add-on 紀錄記一行（不含權杖）；MCP 端點（Bearer token）不經這項檢查，不受影響。
新的 Core 版本要等 add-on 發新版才支援，升級 Core 前請先對照這份清單。add-on 不承諾在 Core 發佈後幾天內出新版：有空或有人回報才發，每次發版
仍要負責人批准（負責人 2026-11-17 定，多帳號 DQ-35）。Core 先升級到沒審過的版本時，管理面板會鎖住（403）、MCP 照常，等 add-on 新版；
這段期間面板的任何動作都做不了（多帳號開通後也撤銷不了任何帳號），只能停止整個 add-on。

## 批准後的安裝檢查表（不是現在的操作授權）

1. 取得上游對**確切新 Add-on** source SHA、映像 digest／固定版本、slug、
   repository 身分、8099/8081、獨立 `/data` 及回復計畫的批准。
2. 發佈者先證明 GHCR 匿名 pull 與映像 gate（見各版 `release-decision-*.md`）。測試 HA 加入的商店網址是
   `https://github.com/WOOWTECH/Woow_ha_mcp_addons#claude-delivery`（[逐步指令](n8n-pilot-commands.md) H1）。
   Supervisor 以網址轉小寫後的 sha1 前 8 碼當 repository slug：這個網址是 `1ee8889c`，app slug 為
   `1ee8889c_woow_mcp_<product>`。換網址（例如拿掉 `#claude-delivery`，slug 會變成 `f1d622e7`）會讓所有 app 的
   slug 跟著變，不是原地更新；已安裝者維持原網址，要換網址需另做資料遷移計畫（見[更新、備份與回復](update-backup-rollback.md)）。
3. 首試 n8n，使用批准的非正式 workflow 受限測試 key。其他六支逐支批准。
4. 保留 protection mode（預設 on）；`protected` 是使用者狀態，不是假造
   manifest key。手動更新設定（auto-update off）要在安裝後確認；0.1.14 起 manifest 為 `boot: auto`
   （使用者 2026-10-14 決定；HAOS 重開機後由 Supervisor 自動啟動），只控制開機啟動，不代表自動更新開關；
   0.1.11 以前為 `boot: manual`，重開機後需手動啟動。
5. MCP 8081 預設主機映射為空；如需 LAN，選未使用的唯一 host port 並檢查
   防火牆。各容器內相同 8081/8099 不衝突；主機映射不可重複。
6. 8099 僅 Ingress（真實 peer `172.30.32.2`）；3000 僅容器 loopback，永不對外。
   不使用 Ingress origin 作 MCP endpoint。[client 文件](clients.md) 必讀。
   0.4.14 起（Headscale 0.4.19 起；多帳號計畫 HM-06）：3000 上的 Python 子程序只接受 gateway 自己的 child bearer（剛好一個
   `Authorization: Bearer <child token>`），容器內直連不帶、帶錯或多帶一律 401；沒有有效的 child token 就不啟動。
   n8n 的子程序本來就只認同一個 child token（n8n-mcp 的檢查，維持原狀）：它只看值是不是 `Bearer ` 開頭、比對前去掉前後空白、重複的
   `Authorization` 只看第一個，所以另外收下「`Bearer` 後兩個空白」「兩個標頭都是自己的」「第一個是自己的、第二個是別的」三種寫法；三種都要先有
   自己的 child token，沒有越權（多帳號契約 §8.8 #37）。已下架的 Odoo Manage 是唯一沒有 child bearer 的子程序，維持原狀、不開放多帳號（DQ-28）。

HA options/schema 目前為空 `{}`：runtime 沒有實作 options 讀取，不提供假的
log_level 開關。後端 URL、憑證、token、endpoint、工具政策由 GUI/state 擁有，
各支經有效 Ingress/provider 才有設定路徑；重啟不能用 options 覆寫。每支一組後端。
UI 保留不送 PUT；替換完整 typed connection，空白秘密不代表保留；清除整組需確認。
已下架的 Odoo Manage：mode=read/module，module 要求後端已有 MCP module，不做模組安裝或 full YOLO。
工具頁保存完整 `enabled_write_tools`、`writes_enabled:false`，disabled 優先。
舊 global 只授權原 n8n/OpenDesign 兩個 legacy writers，UI 顯示其有效狀態並可精確撤銷。
撤銷 exact grants 必須送空陣列，global false 本身不撤銷 grants。詳見 [v3契約](../tool-expansion.md)。

## 寫入預設開啟

使用者 2026-10-15 決定：HA add-on 做**完整版**，與原始 MCP server 及 PaaS woow-mcp-server 功能一致，所有工具（含高風險）
全部開放、全部預設開啟，管理介面可逐一關閉。0.2.1 起：

- 七支開放子程序的全部工具（Odoo 41、n8n 28、Hermes 11、OpenDesign 15、EMQX 39、LiteLLM 40、Nextcloud 9）；tools/list 用
  子程序自己的 inputSchema，tools/call 參數原樣轉給子程序驗證，輸出不再截斷或投影。細節見 [工具範圍](../tool-expansion.md)。
- **新安裝**：每個寫入工具與混合工具的每個寫入 operation 都有 grant，`writes_enabled` 為 true。
- **從 0.1.x 升級**（state schema 1/2/3→4，只遷移一次）：**下一版起（未發版，負責人 2026-10-27 決定）**第一次啟動時自動改成
  同樣的全開（**0.1.x 的停用清單清空**），token、後端連線與對外端點保留，MCP 立刻可用、不再停在 503 等確認；同一次寫入加上標記
  `owner_defaults_20261025`，並把舊設定的限制存成 `/data/mcp/owner-defaults-20261025-recovery.json`。管理面板事後顯示「已於
  <時間> 自動套用預設全開」與升級前後差異，可選「還原升級前的限制」（關回舊設定停用的工具；寫入只保留舊設定授權過的，
  新版才有的寫入操作也取消，與 0.1.x 實際能做的相同；新版才有的工具不會被停用（讀取照常可用））或「保持全開，
  不再提示」，見 [legacy migration](legacy-migration.md)。0.3.0–0.4.1 是先停在升級確認頁（預選 `all_on`），管理員確認後
  才遷移。
- 管理員在「工具與寫入授權」停用的工具或取消的寫入，儲存後重啟與後續升級都維持（schema 4 的 state 不再被預設值改寫）。
  停用優先於任何授權。已下架的 Odoo Manage 例外（寫入需 module 模式，升級時保留原政策）。
- 回退到 0.1.x：舊版不接受 schema 4，請還原升級前的備份。下一版自動遷移過的設定帶有標記，0.4.1 也不接受，同樣還原備份。
- Odoo：`execute_method` 可直接 create／write／unlink，也可呼叫**任意方法**，包括未審查的副作用方法（`action_confirm`、
  `action_post` 等，`ODOO_MCP_ALLOW_UNKNOWN_METHODS=1`）；`chatter_post` **直接送出**，不經 preview／confirm（`MCP_CHATTER_DIRECT=1`）。
- n8n：管理面板可另填選填的 **MCP Access Token**（n8n 設定 → Instance-level MCP），版本歷史、資料表欄位、`n8n_test_workflow`
  prepare／pinned／direct、`n8n_explore_node_resources`、`n8n_manage_agents` 需要它。n8n 的 webhook／URL SSRF 防護**已關閉**
  （`WEBHOOK_SECURITY_MODE=permissive`，使用者 2026-10-15 決定），以便連到 HA 內網的 n8n。
- 後端錯誤**回傳原始訊息**（與 PaaS 一致；例如 Odoo 的 AccessError 原文、LiteLLM／EMQX 的錯誤 body），不再只回固定代碼。
  gateway 在每個轉送的回覆中把 add-on 持有的憑證（Add-on 權杖、child token、後端 API key／密碼與其 Basic 認證形式，4 字元以上）
  換成 `[REDACTED]`；log 的密鑰網址遮罩不變。

**風險提醒：網址（或權杖）＝完整後端權限。**任何拿到 Add-on 權杖或 Claude.ai 密鑰網址的 MCP client（包括 AI 助理誤判時）
不需管理員再授權，就能以後端帳號的權限直接操作：例如以 Odoo `execute_method` 新增／修改／刪除任何紀錄、建立或刪除 n8n
credentials 與 workflow 並執行、產生或刪除 LiteLLM API key 並呼叫模型（產生費用）、修改 Hermes 設定或新增 MCP server、
發佈 MQTT 訊息或封鎖 client、刪除 Nextcloud 檔案；Odoo 還能呼叫任意方法（確認訂單、過帳發票等不可輕易回復的動作），
留言直接送出、不經確認；n8n 的 webhook／URL 檢查已關閉，**MCP 可經 n8n-mcp 連到 add-on 能到的任何內網位址**（HA 內網、
其他 add-on、區網裝置）。**原始錯誤訊息可能含後端內部資訊**（模型與欄位名稱、檔案路徑、帳號 user id、版本），一樣只給該拿到的人。請：

1. 後端帳號、API key、App 密碼一律只給需要的權限（這是真正的權限邊界）；
2. 安裝或升級後先到管理面板停用不需要的工具、取消不需要的寫入；
3. 權杖或密鑰網址外洩時立刻在管理面板「重新產生」。

工具名單（子程序新增但未分類的工具一律拒絕）、停用、寫入授權、出站 DNS／TLS 防護、回覆中的憑證遮罩與 log 遮罩仍由 add-on 強制。

## 映像／資料契約

- 固定 Python **3.13.16** slim-bookworm，符合既有 `>=3.13,<3.14`；未宣稱
  3.12 或 aarch64。核心 `.venv` 與 n8n 以外各支的 child `.venv` 分開，child 的
  Starlette 1.9.0 不覆蓋核心 1.3.1（0.3.4 起）。n8n 使用 Node **26.12.1**（0.4.0 起；0.3.4 是 22.23.4，n8n-mcp 2.96.2
  支援兩者）、npm lock、`npm ci --ignore-scripts`（仍不執行任何套件腳本）。**0.4.12 起**：better-sqlite3 固定在
  12.11.1（`apps/n8n/package.json` overrides，與 PaaS 映像相同），它在 Node 26（ABI 147）的預建原生檔是映像裡唯一的原生模組，
  只經 `packaging/native_addon.mjs` 從 `packaging/inputs.json` 固定的 GitHub release 資產取得：先驗檔案大小與 sha256 才開檔，
  tar 只准一個固定名稱、大小與 sha256 的一般檔，寫成 0644；建置期下載、執行期沒有下載，建置最後還要載入並跑 FTS5 才算過。
  n8n-mcp 因此用 FTS5 原生資料庫，不再退回 sql.js（0.4.11 以前的行為，`search_nodes` 的排序較差）；sql.js 仍在 npm 樹裡，只是不被選用。
  n8n-mcp 把工作流版本歷史（更新與 autofix 前的備份、`n8n_workflow_versions`）寫在同一個 `nodes.db`，映像裡那個檔案是 root 擁有、子行程以
  uid 10001 執行，原生引擎會把它當唯讀開、第一次寫入就失敗；所以管理程序啟動時（`n8n_adapter.prepare_catalog`）把它複製成私有工作副本
  `/tmp/woow-n8n-mcp/nodes.db`（目錄 0700、檔案 0600，每次啟動都從目前映像的目錄重做，子行程重啟不重做），以 `NODE_DB_PATH` 交給子行程（PaaS 映像
  同做法）。不在 `/data`，所以不進備份；歷史隨容器消失，與 sql.js 時記憶體裡的歷史相同。複製失敗時子行程仍會啟動，只是版本歷史寫不進去。
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
  或探測外部服務；n8n 可啟動內建文件 runtime，但 backend readiness 仍 503。0.2.2 起 client 這時仍能連線：
  gateway 自己回 initialize 與完整 tools/list（add-on 內附、與子程序一致的工具清單），tools/call 回 `-32603`
  「Backend not configured」；後端連不上時回「Backend unreachable」並附原因（[client 文件](clients.md#token-事件與故障)）。
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
`GET :8081/health/ready` 僅回 `{ready:boolean}`；未設定或 backend offline 為 503（0.2.2 起 MCP 端點在這兩種情況下
仍可連線、列工具，readiness 不變）。
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

## 多帳號（產品開通後）

**狀態（2026-11-19）：還沒有產品開通**（`MULTI_PROFILE_PRODUCTS` 是空的）。這一節寫開通之後的行為；哪一版、哪個產品開通，以該產品的 CHANGELOG
為準。連線與網址見 [client 文件](clients.md#多帳號產品開通後)；還原、回退與緊急關閉見 [更新、備份與回復](update-backup-rollback.md)。
完整規則在多帳號契約 `docs/multi-profile/contract.md`（開通後預設帳號會變的事：第 1.4 節）；威脅模型與已知限制在 `docs/multi-profile/threat-model.md`。

### 帳號是什麼、誰能管

- 一個 add-on 有一個預設帳號（就是今天的設定與權杖，開通後不變）和最多 5 個額外帳號。各產品的上限：Odoo 5、n8n 2，Hermes、EMQX、LiteLLM、
  Nextcloud、Headscale 各 3；OpenDesign、Odoo Manage 不開放（DQ-28）。記憶體或開檔數不夠時上限更低（下面兩點）。
- 每個帳號有自己的後端連線與憑證、一把 MCP 權杖、一份工具政策、一個子程式。新帳號複製預設帳號當下的工具政策（之後各自獨立），後端連線是空的，
  要另外設定（DQ-02）。「MCP 用戶端端點」全 add-on 一個，只在預設帳號設定（DQ-13）。
- **一組管理身分管全部帳號**：任何能開這個 add-on 面板的 HA 管理員（owner 或系統管理員），都能看、輪替、撤銷、刪除每個帳號的權杖，改每個帳號的
  後端與政策。沒有帳號層級的管理權限，也沒有跨帳號總覽（DQ-31）。

### 同 uid＝整個 add-on 與每個帳號都被完全控制

- 管理程序與每個帳號的子程式都以同一個 uid（10001）執行（多帳號計畫 §8.1，C1-S3；DQ-37）。**一個子程式被攻破（例如某個上游 MCP server 的漏洞），
  等於整個 add-on 與每個帳號都被完全控制，包括留後門**：
  - 讀得到每個帳號的設定，拿到全部權杖與後端帳密；
  - 改得了每個帳號的設定：植入自己知道的權杖、打開寫入權限、把後端網址改到自己的伺服器，下次重啟就收到憑證；
  - 改得了帳號索引；別的帳號的 port 空出來時可以先綁住；可以對別的子程式或管理程序送訊號。
- PaaS 也是同一個邊界。帳號之間的隔離只防「持有某個帳號權杖的用戶端」碰到別的帳號、拖垮別的帳號，不防同一個容器裡的程式。不要把多帳號當成
  多租戶：每個帳號的後端憑證只給它需要的權限，這才是真正的權限邊界。

### 事故處理：懷疑某個子程式或帳號被攻破

照多帳號計畫 §8.10（`docs/multi-profile/threat-model.md` 第 4 節）：

1. 止血：面板「診斷與維護」按「全部撤銷」（兩段確認）。面板打不開（403，例如 HA Core 版本還沒審過）就停止 add-on。
2. 在每個後端換掉這個 add-on 用的密碼或 API key：**全部帳號都要換**（同 uid 讀得到全部），再到面板逐帳號存新憑證。
3. 檢查每個帳號的政策（寫入開關、停用的工具、逐項寫入授權、禁止的操作）與後端網址有沒有被改。
4. 檢查帳號清單：有沒有多出來的帳號、孤兒或隔離目錄（面板的帳號選單與「診斷與維護」）。
5. 必要時還原「事故前」的備份：還原後 add-on 在服務前撤銷每個帳號的權杖，到核對卡逐帳號核對後再重新產生（[還原](update-backup-rollback.md#多帳號版本的還原回退與全部撤銷hm-13bhm-13c)）。
6. 留證：add-on log（帳號只記 id 前 8 碼）與診斷頁；不要貼權杖或密碼。

### 換後端身分會換權杖（Odoo）

- 開通的 Odoo 帳號改 url、database 或 username（包括清空連線）時，同一次存檔換一把新的 MCP 權杖：**兩條舊網址（Bearer 與密鑰網址）同時立即失效**，
  存檔提示會說權杖已換。到「連線與權杖」複製新的權杖或網址，更新所有用戶端。只改密碼、第一次設定、權杖已撤銷時不換（DQ-05；PaaS 同）。
- 把後端網址改到另一台伺服器（scheme、host 或 port 變了）時，表單要求一起重新輸入那條網址的密碼或金鑰，否則不存（422；所有產品，DQ-40 ⑨ (a)）：
  防止把存好的密碼送到新的伺服器。只改同一台伺服器的路徑不用重填，但已存的秘密會送到新路徑：換路徑前先確認兩條路徑後面是同一個服務。
- 存檔回 503（state unavailable）：這次寫入的結果不明。**重新啟動 add-on，重啟後到「連線與權杖」確認網址**：權杖可能已經換了（舊網址失效），
  只是這次沒收到「已換」的提示。
- 預設帳號換身分的結果不明時，重啟之前 8081 對**每個帳號**（不只預設帳號）都回 503；面板沒有另外的提示（HM-12 審查 S-2）。重新啟動 add-on 就恢復。
- 還原後還沒核對的帳號，會換權杖的存檔回 409（要先到核對卡按「已核對」；什麼都沒存）。

### 刪除帳號、孤兒與隔離

- **刪除帳號**：帳號選單的「刪除」，兩段確認。順序是先撤銷權杖、抹掉後端憑證，再停子程式、從索引移除、刪目錄；權杖立刻失效，不能復原。預設帳號
  不能改名或刪除（DQ-14）。
- **孤兒**（`profiles/` 底下有、索引沒有的帳號目錄，例如刪除到一半失敗留下的）：不會被使用，也不會自動刪；「診斷與維護」列出，可以逐筆刪除（兩段確認）。
- **隔離目錄**（`profiles/.quarantine-…`）：還原時讀不到設定的帳號會移到這裡，不服務、只能刪除；刪除前先撤銷讀得到的權杖、抹掉憑證。暫時性錯誤
  （例如開檔數不夠、I/O 錯誤）也可能讓一個好的帳號被隔離：同一份備份再還原一次就會重做。超過 64 筆時面板只列前 64 筆。
- **帳號索引壞掉或被面板以外的程式改過**：8081 對每個帳號都回 503（包括預設帳號），面板照開。到「診斷與維護」按「隔離帳號索引」（兩段確認）：
  預設帳號立刻恢復，額外帳號的權杖都先撤銷、變成孤兒，只能刪除後重建。HA 上沒有其他支援的手動修復方式（DQ-12）。索引不能用時，面板會放掉
  帳號增刪還沒確認的操作紀錄（好讓「隔離帳號索引」能用）。
- **`profiles/` 目錄壞掉**（開機時列不出來：不是目錄、是連結或擁有者不對）也算索引不能用：8081 全部 503。這時沒有索引檔可隔離，「隔離帳號索引」
  回衝突、什麼都不做；**修好 `profiles/` 之後重新啟動 add-on** 才恢復。
- 開機守門沒做完（log 有 `restore guard: not finished (…)`）時 add-on 什麼都不服務，下次開機再做；每一行守門 log 的意思與處理見
  [更新、備份與回復](update-backup-rollback.md#開機守門的-log)。

### 開檔數不夠時不能新增帳號

- 開通後 add-on 開機時把 soft `RLIMIT_NOFILE` 提到需要量＋25%（Odoo 約 680，不超過 hard）。讀不到、hard 不夠或提不上去時，**只服務預設帳號**：
  8081 外框維持 64、記一行 WARNING；這時新增帳號回 409（已達上限，`limit` 是 0），什麼都不寫，已有的額外帳號也不服務。
- 實測：HM-03a 在一台 HAOS 18.1（Supervisor 2026.11.0）的 add-on 容器裡量到 soft 1024、hard 524288，提得上去。其他主機照樣每次開機讀，不假設。

### 健康、重啟與 log

- 每個帳號自己的子程式與健康檢查。一個帳號的子程式當掉，看門狗照 2→300 秒退避重起、不限次數、穩定 120 秒歸零，其他帳號不受影響（DQ-20）；
  額外帳號的健康監看停了只標記那個帳號（`failed`），預設帳號的元件停了照今天讓 add-on 結束、由 Supervisor 重啟（DQ-21）。
- 健康檢查連兩次失敗才判後端連不上。後端拒絕憑證時退避 15→30→60→120→300 秒，存新憑證或面板重啟後歸零（DQ-25）。Odoo 依來源 IP 節流登入失敗
  （系統參數 `base.login_cooldown_after`、`base.login_cooldown_duration`）：同一個 add-on 的每個帳號都從同一個來源連 Odoo，一個帳號的密碼錯可能讓
  別的帳號一起被冷卻；Odoo 管理員可以視需要調這兩個參數。
- 額外帳號子程式的 `oom_score_adj` 是 500、`nice` 加 5：記憶體不夠時核心比較會先殺它們，但這不是保證，OOM 仍可能殺管理程序，所有帳號一起斷。
- add-on log 的帳號只寫 id 前 8 碼，不寫名稱、權杖或網址。開面板時瀏覽器 console 有一筆 400（`profile_id_required`）是預期的：面板用它探測產品
  開通了沒有。
- 8081 對每個帳號都回 503 時，常見原因：預設帳號的設定讀不到、帳號索引壞或被外改、`profiles/` 壞掉、預設帳號換身分的結果不明、Origin 政策檔壞掉
  （只影響密鑰網址）。先看 add-on log，再照上面對應的一點處理。全部撤銷沒做完時，只有沒撤銷成功的帳號的舊權杖回 503。

### 瀏覽器來源檢查（Origin）

- 開通後密鑰網址有全 add-on 一份來源清單（預設 `https://claude.ai`、模式 report-only，不擋；DQ-11 (a)）。清單外的請求照常服務，log 記一行
  `MCP gateway [profile=<id 前 8 碼>]: an Origin the secret path does not allow (report-only: served as usual) decision=would_deny …`；
  每帳號每個來源 60 秒一行、每分鐘最多 20 行。切 enforce 後清單外的回 403，log 是 `decision=deny`。
- 要擋就在「連線與權杖」的「瀏覽器來源檢查」卡片切 enforce；切之前先看 log 的 would_deny 行，把需要的來源加進清單。一行 would_deny 只說明有人送了
  這個來源，不證明是誰：任何持有權杖的用戶端都能送任意 Origin。預設清單有 `https://claude.ai`，Claude.ai 送它時不會留紀錄。
- 政策檔壞掉時，**每個帳號**的密鑰網址都回 503（包括不帶 Origin 的 Claude.ai），直到在面板存一份新的；Bearer 不受影響。
- 產品又被關掉（緊急關閉版）時，enforce 靜默失效：密鑰網址回到任何 Origin 都放行、不記錄；再開通又照存的政策生效。
- 還原把政策帶回備份當時的模式與清單，沒有提示：**還原後到「連線與權杖」看一次**。

### 已知限制（開通後）

完整清單與實測數字在 `docs/multi-profile/threat-model.md` 第 3 節。最常碰到的：

- 同 uid＝同一個信任邊界（上面）。
- 隔離在請求層，不在連線層：8081 的連線數上限全 add-on 共用；有人開滿連線（不需要權杖），每個人的新連線都拿到純文字 503。
- 請求內容位元組預算全 add-on 一份、每個帳號一個份額。記憶體小的機器（預算落在下限 16 MiB）一個帳號的一個大請求就佔滿預算，別的帳號超過 64 KiB
  的請求拿 `-32003`；小請求不受影響。
- 待送回覆額度是軟上限（負責人 2026-11-16 接受，D2）：每個帳號「已處理、還沒被用戶端收完」的回覆上限是 32 MiB，達到上限時已轉送給子程式的請求，
  回覆照樣交出。一個帳號的用戶端一次送滿轉送名額、又都不讀回應時，add-on 最多多用約 800 MiB（預設帳號）或 416 MiB（每個額外帳號）的帳上記憶體，
  實際記憶體還要多約 1.3～1.4 倍。
- 回覆在一條工作執行緒上依帳號輪流處理，大回覆分段處理：一個帳號的大回覆會讓別的帳號的回覆等它處理完（本機最久約 7 秒，小主機數倍）；單一長字串的
  解析仍會讓 add-on 停一下（本機約 20～40 ms，小主機數倍）。工作執行緒停了，add-on 會結束並由 Supervisor 重新啟動。
- 請求（送給 MCP 的內容）仍在 add-on 的主迴圈裡檢查與解析：一個很大的請求會讓所有帳號短暫變慢。
- 排隊中的請求只在「那個請求的連線被關掉」時才放棄：MCP SDK 層級的逾時或取消（只送 `notifications/cancelled`）看不到，排隊中的寫入在名額空出後
  照樣執行（最多等 1 秒，等不到就回 `-32003`、不送出）。
- 後端網址拒絕 loopback（127.0.0.0/8、::1、`localhost`）只看這些位址與名稱；add-on 自己的主機名與 Supervisor bridge 位址不在規則裡（從那裡只連得到
  要權杖的 8081 與只收 Ingress 的 8099）。開通前存的 loopback 網址開通後照樣讀得出來，但連不上；Odoo 的健康檢查只顯示 `BACKEND_UNAVAILABLE`。
- 面板 403（HA Core 版本還沒審過）時任何帳號都撤銷不了，只能停止整個 add-on（上面「支援的 Core 版本」）。
- 緊急關閉要發一版，推估一個工作天以上；期間只能停 add-on 或在面板撤銷（[回退與緊急關閉](update-backup-rollback.md#回退與緊急關閉多帳號產品開通後)）。
- 備份含全部帳號的權杖與後端帳密：一律用加密備份，保管方式同上面的備份規則。
