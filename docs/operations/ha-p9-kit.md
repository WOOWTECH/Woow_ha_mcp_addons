# P9 工具：在 HA 實機上量測一個 MCP app

`packaging/ha_p9_driver.mjs`（操作端，Node ≥ 22）＋`packaging/ha_p9_probe.py`（HA 主機端，只用 python3 標準庫）。
對象是**一個**已安裝的本專案 app；不碰其他 app、Core、Supervisor。2026-10-05 先在 n8n app 實跑，之後用於 0.1.1–0.1.5 各支的 HA 回歸（`ha-test-0.1.*.md`）。
開通多帳號的 app 另有帳號參數、交叉矩陣與暫時帳號模式（[多帳號](#多帳號hm-16只對開通的-app)；HM-16）。

0.4.7 起，driver 使用與管理畫面相同的設定版本及操作識別契約。每次設定寫入會帶入已讀取的版本；token 輪替／撤銷會帶唯一操作識別碼並核對收據。遇到衝突或回應不明時立即停止，**不會自動重送**。若輸出未確認的操作識別碼，先透過同一管理員身分查詢 `GET api/operations/<id>` 並核對目前設定，再決定後續處理；不要重新執行整個 driver。識別碼只在程序記憶體及不含秘密的診斷輸出中保留。此 driver 的寫入測試需使用 0.4.7 以上契約；舊版請使用對應版本的 kit。

## 前提

- 真 HA 管理員帳號（owner 或 system-admin）；帳密只從環境變數讀，不印、不寫檔。
- 能 SSH 到 HA 主機的 shell（例如 Advanced SSH & Web Terminal），有 `ha` CLI；`restart`、`childkill` 另需 Docker CLI。
- app 的 MCP 埠 8081 已對應到主機埠（`PROBE_PORT`），probe 在 HA 主機上連 `127.0.0.1:<PROBE_PORT>`。

## 用法

```sh
HA_URL=https://<ha> HA_USER=<admin> HA_PASS=<password> APP_SLUG=<repository slug>_woow_mcp_<product> \
SSH_TARGET=<ssh host> PROBE_PORT=18081 PROBE_TOOL=<唯讀工具> PROBE_TOOL_ARGS='{"...":"..."}' \
node packaging/ha_p9_driver.mjs --tokens --modes restart,childkill,bench,cycle
```

driver 以 HA 登入流程取得管理員 token → WebSocket `supervisor/api` 讀 app 的 ingress URL、建立 Ingress session →
呼叫 app 管理 API；每個 MCP token 只經 SSH stdin 傳給 probe。結束時撤銷本次的 HA refresh token；任一 probe 失敗時列出失敗的模式並以 exit 1 結束（外層腳本不會再把內層失敗算成通過）。

| 選項／模式 | 做什麼 | 會改變什麼 |
|---|---|---|
| `--tokens` | 無 CSRF 的 rotate 應 403；reveal T1 → rotate T2（T1 失效）→ revoke（全部失效）→ 再 rotate T3 | **輪替 MCP token**：既有 client 要換新 token |
| `restart` | `ha apps restart <slug>`，量到 MCP 可用的秒數與首呼叫；重啟前後 token 必須相同 | 重啟這個 app |
| `childkill` | 在 app 容器內 SIGKILL management launcher 的子程序，量恢復時間；容器不應重啟。注意：0.2.2 起子程式沒在跑時閘道自己回 initialize（`woow-local-` session），所以印的 `recovered in` 是殺掉後 MCP 埠第一次回 initialize 的秒數（多半是閘道自答，接近 0），不是子程式回來的時間；子程式有沒有回來要看 `child pids now` 是不是新的 PID。開通的 app 用下方多帳號的 `childkill` | 中斷這個 app 的 MCP 連線數秒 |
| `bench` | initialize×5、tools/list×50、`PROBE_TOOL`×50 的 p50／p95 | 無（只用唯讀工具） |
| `cycle` | 25 次 initialize＋DELETE，確認 session 名額有釋放 | 無 |
| `--backend-file F` | 用 0600 JSON（n8n `{"url","key"}`；其他各支 `{"connection":{...}}`）填面板後端，內容不印 | 改這個 app 的後端設定、重啟它的 MCP child |
| `--plan P` | 依清單呼叫工具：reads 必須成功（HTTP 200、非 isError、無 `success:false`）；denials 必須被 gateway 拒絕（HTTP 403；0.1.14 起在 session 內為 HTTP 200 的 JSON-RPC `-32602`／`-32603` 錯誤、沒有 result） | 無（防護失效時見下方說明） |
| `--outage-url U` | 搭配前兩者：後端所有網址欄位（`url`、`gateway_url`、`dashboard_url`…）換成不通的 U，每個 read 都須回 HTTP 200（本機工具照常、後端工具回結構化錯誤），且至少一個 read 回結構化錯誤（只有加 `--outage-refusal` 的產品——每個連線階段都要先連後端的 Odoo Manage（已下架）——可改以「0.1.2 gateway 在初始化就回 503 `BACKEND_UNAVAILABLE` 且不帶 session id」為準，此時只檢查拒絕）；改回原設定後清單須再次全過 | 暫時改這個 app 的後端設定 |

probe 開的每個 session 都會 DELETE，不吃掉 app 的共用 session 名額（n8n 為 20 個、閒置 10 分鐘回收）。

### 清單（plan）

`python packaging/p9_plan.py <product> [--overrides args.json] > plan.json` 從 `docs/tool-surface.json` 產生。
已支援的工具有兩種：`supported-bounded`（已下架的 Odoo Manage；閘道用 `accepted_schema` 驗參數）和 `supported-full`
（0.2.0 起的其他產品；`accepted_schema` 是 null，閘道原樣轉送參數、子程式自己驗）。完整工具的參數規則取自子程式自己的
inputSchema，也就是打包的 tools/list 快照 `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py`（只解析、不 import；
`--snapshot` 可換檔）。

- reads：已支援的讀取工具（或讀取操作），帶最小參數。有界工具照 `accepted_schema` 推。完整工具的必填參數只用 schema 自己
  寫明的值（`default`、`enum` 的第一個、`const`）。推不出安全參數的列在 `needs_args`：有界工具是自由或有格式的字串；完整工具是
  schema 沒寫明值的必填參數（id、名稱、數字、清單），或快照裡沒有這支工具。用 overrides（`{"tool" 或 "tool:operation": {參數}}`）
  補上實際後端的值。
- denials：已支援的寫入、寫入授權是整支工具的工具（effect 不是 read 或 mixed，例如 `n8n_manage_agents`、`n8n_test_workflow`）的
  每個操作（寫入全關時閘道整支拒絕，讀取操作也一樣）、暫不支援的工具與一個不存在的工具。有界工具的參數符合 schema 但指向
  **不可能存在**的資料（整數 id 取允許的最大值、名稱用 `p9-denied`），即使寫入防護失效也不會動到真資料。完整工具只帶操作參數：
  閘道在子程式看到參數前就照寫入授權拒絕；防護失效時，缺必填參數的呼叫會被子程式拒絕。兩種都仍須照試點程序在後端核對前後無變化。
- 清單記錄兩個來源的 sha256：`tool_surface_sha256`（tool-surface）、`tool_snapshot_sha256`（快照）。
- 子程式只寫在說明文字、沒寫進 inputSchema `required` 的條件式必填，產生器看不到。例如 n8n 的 `n8n_workflow_versions` list 要
  `workflowId`、`search_templates` 預設的 keyword 要 `query`：這些讀取仍在 reads，要用 overrides 補參數，否則會失敗。
**前提：受測 add-on 的寫入必須全部關閉。**全新安裝的寫入預設開啟（2026-10-15 起，見 [寫入預設開啟](guide.md#寫入預設開啟)），跑 plan 前先在管理面板「工具與寫入授權」取消全部寫入並儲存（或沿用寫入全關的既有 state），否則 denials 裡的寫入會真的送到後端。
`PROBE_TOOL` 只能填無副作用的工具；寫入防護、後端斷線、備份還原屬 P9 其他項目，不在本工具內。

## 多帳號（HM-16；只對開通的 app）

產品開通後（`features.MULTI_PROFILE_PRODUCTS`；升版 PR 才會開），管理 API 的每個帳號範圍請求都要帶 `X-MCP-Profile`。
driver 的管理用戶端（`packaging/ha_p9_admin.mjs` 包面板的 `AdminApi`）自己決定帶哪個帳號；呼叫端的標頭不能帶它。
沒開通的 app 照上面的用法，輸出和以前相同（只有預設帳號）。

| 選項 | 做什麼 | 會改變什麼 |
|---|---|---|
| `--profile ID` | `--backend-file`、`--tokens`、`--plan`、`--modes` 都對這個帳號做（`default` 或 24 位小寫 hex）；沒給就是預設帳號 | 同上表，只動這個帳號 |
| `childkill`（開通的 app） | 只 SIGKILL `--profile` 那個帳號的子程式：driver 從帳號清單取它的 port，probe 以 `--child-port` 依子程式命令列的 `--port` 找出它（預設帳號的 Hermes／OpenDesign 子程式沒寫 port，就是 3000 那個）。找不到唯一一個就什麼都不殺、失敗。看門狗第一次重起要等 2 秒，這段時間閘道自己回 initialize，所以 probe 殺掉後每 0.5 秒看一次子程式清單（最多 60 秒），直到剛好一個新 PID 服務那個 port；期間別的帳號子程式的 PID 一變就失敗。接著要等到那個帳號的 token 開得到子程式自己的 session 才算恢復（最多再 60 秒；閘道自答的 `woow-local-` session 一律結束、只計數）。輸出 `new pid … after N s (K looks)` 與 `child's session after M s more (J gateway sessions before it …)`。新 PID 沒出現、session 一直是閘道自答的、或別的 PID 變了，probe 都 exit 1。n8n 開通（HM-25）前認不出 n8n 的子程式（port 只在環境變數裡），什麼都不殺、失敗 | 中斷這個帳號的 MCP 連線數秒 |
| `--cross` | 交叉矩陣（T-05）：帳號清單裡每個帳號的 token（各自在自己的 `X-MCP-Profile` 下 reveal）用 Bearer 與密鑰網址兩種接法都開得了 session、列得出工具；每個 session 拿任何別帳號的 token（兩種接法）都 404；隨機 token：Bearer 401、密鑰網址 404。開 session 時一律帶 `X-MCP-Profile: default`：MCP port 不看這個標頭，要是它照標頭選了預設帳號，交叉那一步就會變 200。沒有啟用中 token 的帳號跳過並印一行 | 無（只讀；每個 session 都 DELETE） |
| `--temp-profile` | 暫時帳號模式（照 PaaS `public_probe.py --temp-profile`）：用剛讀到的索引版本建一個名為 `p9-temp-<8 hex>` 的帳號 →（有 `--backend-file` 就存到它身上、有 `--plan` 就用它的 token 跑；沒有後端又有 `PROBE_TOOL` 時，它的工具呼叫要被閘道拒絕（`Backend not configured`），不會借用預設帳號的後端）→ 它和預設帳號做交叉矩陣 → 刪掉它（重讀索引版本；前面失敗也照刪）→ 它的舊 token 必須被拒（Bearer 401、密鑰網址 404）。`--plan` 要搭 `--backend-file`；不能和 `--profile`、`--tokens`、`--modes`、`--outage-url` 一起用 | **建立並刪除一個帳號**；預設帳號不變 |

- **不自動重送**（同 0.4.7 起的契約）：建立或刪除帳號的回應不明時，driver 印出操作識別碼與路由後立刻停止，絕不重送。
  先在面板核對帳號清單與收據；刪除不明時還要印「暫時帳號可能還在」，請在面板刪掉它再跑下一輪。
- 輸出只用帳號的 log id（`default` 或 id 前 8 碼），不印帳號名稱、token、cookie。暫時帳號的名稱是合成的。
- probe 直接連 app 對應到主機的 MCP 埠，不走 HA 主機 shell 的 `http_proxy`、`https_proxy`、`all_proxy` 等代理設定
  （密鑰網址的 token 在路徑上；HM-16 起所有模式都一樣）。
- 開通的 app 才有這些模式；沒開通的 app 帶 `--cross` 或 `--temp-profile` 會直接失敗，帶 `--profile` 非 `default` 也是。
- 刪除後帳號目錄真的清掉、port 釋放（T-09）不在這個工具裡：本機測試 `tests/test_profile_admin_api.py` 涵蓋，HAOS 上看面板清單與孤兒
  卡片（不該多一筆孤兒）。
- 真後端的多身分驗收（同一個 Odoo 資料庫的多個受限使用者、N×N 標記）不在這個工具裡：要先有使用者批准的測試身分，
  照 [分層驗收](acceptance.md#多帳號驗收t-01t-29-的-ha-版hm-16) 的 T-04、T-10 做。

## 證據

probe 每個模式最後印一行 `SUMMARY {...}`（不含 token），連同 driver 輸出存到試點紀錄；依
[試點程序](n8n-haos-pilot.md) 的格式記 UTC、app 版本與 image ID（HA 主機 `docker inspect <container> --format '{{.Image}}'`）。
多帳號的紀錄另記：Core、Supervisor、HAOS 版本（`ha core info`、`ha supervisor info`、`ha os info`）、帳號數與各帳號的 log id，
以及這次是不是用了 `--temp-profile`（建立與刪除的時間）。
