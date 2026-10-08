# Woow MCP 管理介面（本地 Core 整合；HA 未驗收）

繁體中文共用介面，產品取自實際 bootstrap；原生 DOM/ES modules + esbuild。
無 CDN、storage、service worker、登入密碼、production mock 或角色繞過。
`mcp_admin_core/ui.py` 與 gateway 已供應真實 HTML/static/API；七個 Dockerfile
從 pinned Node stage 建置完整 dist。**映像未建置、HA 未安裝／未測、真後端未驗收。**
僅 n8n 有已批准並經 component review 的正式 HA provider；六類 production 管理仍 403。
本地 Chromium 已連真正 Core，n8n 經實際 bootstrap→post-exec guard→run.py→固定
WS provider（僅 owned fake transport）；六類表單使用 test-only 注入 role，不是 HA 證據。
本地整合與測試 ownership 修復已通過獨立規格及全新安全審查；不清除任何 release gate。

## 建置與測試

Node 22+，package-local exact pins/lock；build 與 fixture 分離：

```sh
npm ci --prefix packages/mcp-admin-ui --ignore-scripts --no-audit --no-fund
npm test --prefix packages/mcp-admin-ui
npm run build --prefix packages/mcp-admin-ui
npm run browser:install --prefix packages/mcp-admin-ui # 隔離 Chromium，無 apt
npm run test:browser --prefix packages/mcp-admin-ui # dynamic loopback port，LOCAL MOCK fixture
# repository root；需已安裝 core/n8n locked runtimes，Linux local root 可 drop uid10001
# 此明確測試不列入一般非 root pytest collection；不安裝到正式 runtime：
env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -s -p no:cacheprovider tests/integration_local_runtime.py
```

Standalone 測試由擴充 fixture 管理自有 child，child 綁定 ephemeral port0；
每次 readiness／API／browser 送出前驗證 retained PID/starttime/fd/inode ownership。
所有 `UI_PORT` 覆寫都拒絕；不再支援手動 `npm run fixture`／固定4178啟動。
Fixture 不連後端、不是正式 verifier，也不進 image/dist。Guard 依賴固定 Playwright1.61.1
私有 request seam，升版須重審／回歸；不是任意 browser/native code sandbox。
需要使用既有建置時可設 `OWNED_UI_DIST` 指向已建置 assets，測試只複製到自有暫存目錄。
瀏覽器 evidence 以 `UI_EVIDENCE_DIR` 指向 repository 外的專屬目錄；
只截總覽／空白表單，禁止 secret screenshot、trace、video。不要輸入真實憑證。

## 實際 typed backend API

| 產品 | PUT `/api/backend` |
|---|---|
| n8n | `{url,key}` |
| Odoo | `{connection:{url,database,username,password}}` |
| Odoo Manage | `{connection:{url,database,username,api_key,mode:"read"或"module"}}` |
| Hermes | `{connection:{gateway_url,gateway_api_key,dashboard_url,dashboard_username,dashboard_password}}` |
| OpenDesign | `{connection:{url}}`，無虛構 token |
| EMQX | `{connection:{url,api_key,api_secret}}`，URL 不附 `/api/v5` |
| LiteLLM | `{connection:{url,master_key}}` |
| Nextcloud | `{connection:{url,username,app_password}}`，url 是 Nextcloud 根網址，主機名稱含非 ASCII 字元（IDN）時要填 `xn--` 形式（表單會顯示）；username／app_password 不可空白、前後不可有空白 |

- Manage `module` 要求**後端 MCP module 已存在**，UI 不安裝／變更 Odoo；read 不允許 writer grants。
- 保留完全不發 PUT；替換是完整 typed connection，必要秘密需重新輸入，不 trim。
- 清除需確認：n8n `{url:null,key:null}`，其他 `{connection:null}`。若現有 Manage grants
  與 read/clear 不相容，server 拒絕；先在工具頁明確撤銷 grants，不靜默保留權限。
- Hermes Dashboard 三欄整組提供或全 null；不把空白當個別 secret-preserve。
- 秘密使用 password/new-password；提交成功或錯誤、離頁均清除。不造假既有欄位值。

## v3 精確授權（不是舊 MOCK proposal）

Bootstrap 明確宣告 `policy_contract:"woow-v3-exact-grants"`，回傳
`enabled_write_tools` 陣列、`writes_enabled`、`disabled`，及各工具
`write`、`write_grants`、`operation_parameter`、`legacy_write`、`inputSchema`。
UI 驗證契約並依實際 metadata 產生每工具／每 operation 控制；不硬編工具數。

```json
{"writes_enabled":false,"disabled":[],"enabled_write_tools":["n8n_manage_folders:create"]}
```

PUT 取代**全部** exact grants。disabled 優先並清除該列選擇。原兩個 legacy writers
在 `writes_enabled:true` 時顯示實際有效授權；儲存轉為明確 grants 並關閉 global。
未知契約禁止儲存，絕不降到只送 global false 而留下隱藏 grants。每次保存重新
bootstrap；product/contract/tools/schema/disabled/global/grants 任一變更即停止、要求刷新。
這不是跨管理員原子 compare-and-swap 保證；server 仍逐次強制 dispatch。UI 不執行工具。

## 正式 listener 與 Ingress

- 只有 admin listener。每頁、asset、license、API 都走實際 socket peer172.30.32.2、
  單一 user ID、固定正式 provider fresh role；沒有 verifier 即403。
- 共用既有16 admission slots、bounded body、2秒 lock wait、role timeout/cancel join。
  不對 fonts 啟動無界 WS，也不放寬 mutator body/lock/final-role/owned-restart 順序。
- prefix 只允許空字串或 `(?:/[A-Za-z0-9_-]+)+`、最長512、單一 header。
  所有 `__MCP_UI_BASE__` 替換；prefix retained/stripped 均支援。
- HTML 只供 `/`、`/overview`、`/backend`、`/tools`、`/access`；API、未知路徑、
  assets 不假成功 fallback。固定 dist root，no-follow descriptor walk、bounded regular
  files、拒絕 encoded path/query/symlink。缺 build503，不回 fixture。
- no-store、nosniff、no-referrer、self-host CSP 與 `frame-ancestors 'self'` 保留同源 HA iframe；
  這不是實際 HA iframe 相容性證據。無 Host/origin 推測 MCP endpoint。

## Endpoint、token 與健康

Explicit HTTP(S) endpoint 以 `/mcp` 結尾、無 credentials/query/fragment。
一般複製只含 `<YOUR_ADDON_TOKEN>`；未設定顯示 placeholder。
reveal/rotate/revoke 各需確認、fresh bootstrap/CSRF、空 body POST。
client Bearer 可刻意揭露，不是管理內部 Supervisor machine token。
reveal60秒、blur、hidden、導航、pagehide、錯誤清除；失焦後延遲回應不可復活秘密。
剪貼簿需明確操作，不能保證 OS/extension/clipboard 自動清除。
health 分 management、child.state/transport_ready、backend，不把管理可用當後端成功。

## 品牌／資產與限制

共享 CSS、warm white/gray、少量 #6183FC；Poppins、Outfit、Noto Sans TC、單一
Yellowtail `Welcome`、固定 MDI7.4.47，完整 self-host/fonts/licenses。
Yellowtail5.2.8 是 Apache-2.0，其餘 font licenses/NOTICE 隨 dist 保留。
320/360/1440 的 root/prefix 導航刷新、字型實際載入與 overflow 有本地 browser 覆蓋。
不是完整 WCAG、讀屏、Safari/Firefox、HA clipboard、Docker 或客戶端驗收。
