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
| EMQX | `{connection:{url,api_key,api_secret}}`，URL 填 Broker 的基底網址；貼上帶 `/api/v5` 的網址也可以，存檔時（畫面與伺服器都）會去掉它 |
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

新安裝的 state 預設所有寫入 grants 與 `writes_enabled` 都開啟（2026-10-15），工具頁一開始全部勾選並顯示風險提醒；管理員取消勾選並儲存後即關閉，既有 state 不被預設改寫。
PUT 取代**全部** exact grants。disabled 優先並清除該列選擇。原兩個 legacy writers
在 `writes_enabled:true` 時顯示實際有效授權；儲存轉為明確 grants 並關閉 global。
未知契約禁止儲存，絕不降到只送 global false 而留下隱藏 grants。每次保存重新
bootstrap；product/contract/tools/schema/disabled/global/grants 任一變更即停止、要求刷新。
這不是跨管理員原子 compare-and-swap 保證；server 仍逐次強制 dispatch。UI 不執行工具。

## 舊版升級的一次性全開通知（下一版，2026-10-27）

舊版安裝（state schema 1/2/3）在第一次以新版啟動時已自動全開（`mcp_admin_core/owner_defaults.py`），不再有啟動前的升級確認頁
（`upgrade.js` 已移除）。Bootstrap 只在被遷移過的設定帶 `owner_defaults`：`at`、`from_schema`、`restored_at`、`acknowledged_at`、
`notice`、`recovery`（available／missing／invalid）、`upgrade`（升級前後差異）、`restore`（還原會做的變更與 `available`）。
`notice` 為 true 時每一頁頂端顯示「已自動套用預設全開」；之後在「診斷與維護」頁保留紀錄。兩個動作都是無 body 的 POST，
需 CSRF 與目前 revision 的 `If-Match`（缺少回 428、過期回 409）：

| 動作 | API | 結果 |
|---|---|---|
| 還原升級前的限制 | `POST /api/owner-defaults/restore` | 忠實還原：舊設定停用的工具再停用；寫入只保留舊設定授權過的（新版的寫入也取消）；新版工具不會被停用（讀取照常可用）；記 `restored_at` |
| 保持全開，不再提示 | `POST /api/owner-defaults/dismiss` | 記 `acknowledged_at`；之後仍可在診斷頁還原 |

格式不符的通知不顯示任何內容（`ownerDefaultsView` 整個拒絕），改在每一頁顯示固定的「升級通知無法顯示」卡片
（不含伺服器送來的值、沒有動作，請重新整理或更新 add-on），不再整個隱藏。名稱一律以文字節點顯示，時間照伺服器的 UTC 顯示。

## 多帳號（HM-11；還沒有產品開通）

伺服器沒開通多帳號時，面板的畫面、請求與收據和以前完全一樣。開通後（bootstrap 帶 `profiles_supported`）：

- 頂列多一個帳號選單（`<select aria-label="帳號">`）與「新增帳號」「改名」「刪除帳號」；預設帳號不能改名或刪除，刪除要確認兩次。
  標題下固定顯示目前帳號名稱與 id 前 8 碼；名稱一律以文字節點顯示。
- 帳號選擇只放在頁面記憶體（DQ-18），重新整理回到預設帳號。第一次 bootstrap 不帶帳號；伺服器回 400 `profile_id_required`
  就改成每個帳號範圍請求都帶 `X-MCP-Profile`（含明確的 `default`）；`/api/profiles*` 永遠不帶。
- 每次變更先鎖定帳號：取 CSRF 的 bootstrap 與變更本身帶同一個標頭，兩個回應的帳號回聲都要符合，否則不顯示結果、藏起權杖並重新讀取。
- 切換帳號：藏起已顯示的權杖、清掉密碼欄與未存的草稿、整頁重畫；切換中只剩帳號選單可用，再選一次會取代前一次，前一次晚到的回應丟掉。
  其他操作進行中選單停用。
- 帳號被刪：面板一得知就清掉該帳號未確認的收據並說明，不會叫人切回。得知的路徑有：在面板刪除（孤兒也是）、重送刪除
  （確認完成；或回 `profile_not_found`、`config_conflict` 而重讀的清單已沒有它，這時說的是要刪的帳號）、建立的重送只回 id
  （建好之後已被刪）、帳號範圍請求回 `profile_not_found`、切換時新清單裡已沒有剛離開的帳號
  （替代清單不算，收據留著：索引壞、或清單讀不到或格式不合時只剩預設帳號的清單）。
  目前帳號被刪就切回預設帳號。
- 額外帳號的 MCP 端點唯讀（全 add-on 共用，只在預設帳號修改）；手動範例的名稱是 `woow-<產品>-<id 前 8 碼>`。
- 收據：預設帳號的 key 與 4 鍵紀錄不變；額外帳號另一個 key、多一個 `profile` 鍵；帳號增刪用 `…:profiles`（見 `docs/admin-write-contracts.md`）。
- 孤兒（DQ-14：索引沒有的帳號資料夾，不服務、不自動刪）：「診斷與維護」逐筆列出，刪除要確認兩次；選單下方提示筆數。
- 索引不能用（DQ-12）：預設帳號照常可用，「帳號索引無法使用」卡片有「隔離帳號索引」（確認兩次；送 bootstrap 的
  `profile_index_etag`）。隔離後預設帳號立刻恢復 MCP 服務，原本的帳號都變成孤兒。409 時重讀狀態並說明原因
  （索引已可用、索引檔又變了、或沒有索引檔可隔離：要修好後重啟 add-on）；503（別的帳號拿著鎖）保留識別碼，可重送。
- 清單不能用時不鎖面板（審查 S-2）：清單讀不到或格式不合，選單只剩預設帳號（與目前帳號），新增改名刪除停用並說明；
  清單沒帶 `ETag` 時照列但唯讀；這個瀏覽器顯示不了的名稱只藏那一列的名稱（以 id 前 8 碼稱呼；建立後的提示也一樣）。
- `profiles_supported` 是 false 的產品（OpenDesign、Odoo Manage，DQ-28）沒有「新增帳號」；`limit` 0（可開的檔案數不夠，
  只服務預設帳號）另有說明。
- fixture 以 `profiles` 選項開關多帳號；Playwright 的 `profiles-on` 專案讓四個既有 spec 在開關開時原封不動再跑一次；
  `profiles.spec.mjs` 另有一案在開關關時逐頁確認沒有任何帳號介面、帳號字樣與帳號標頭。
- fixture 和真後端一致的證明：`tests/profile-api-cases.json` 列出面板開通後用到的每條管理路由與要處理的每種拒絕，
  每案的 `expect` 錄自真的 8099 管理 app（repo 根目錄 `tests/test_panel_profile_api_shapes.py`，pytest）；
  `tests/browser/profile-api-parity.spec.mjs` 讓 fixture 跑同一份案例、比同一份 `expect`。改了任何一邊，兩個測試之一會紅；
  真後端變了，先重錄 `expect`（照 Python 測試失敗時印出的形狀改），再改 fixture 與面板。

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
