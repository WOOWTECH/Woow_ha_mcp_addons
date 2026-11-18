# 0.4.14（與 Headscale 0.4.19）：展示機單帳號回歸

2026-11-18 07:17–09:05 UTC。對象是負責人指定的展示機 woowtechshow（正式 HAOS，Core 2026.7.2、Supervisor 2026.11.0）。負責人決定展示機不升 Core，所以這裡只驗「沒退步」；
Core 2026.11.x 上管理面板能開（這一版的目的）靠 CI 與單元測試。本 PR 的分支（`release/six-products-0.4.14-20261117`）暫時加成商店 repo，裝七個測試副本；Supervisor 匿名拉取公開映像，
執行中的 image ID 與各產品發佈紀錄相同（odoo `d6b4d85c2119`、n8n `5afcfda1f5dd`、hermes `8c52b11eb7de`、emqx `408478b76ee0`、litellm `e9e31155baa5`、nextcloud `1ed1a0040708`、
headscale `5603dd22b76f`）。展示機原本的 app（商店裝的 MCP、各後端與其他 app）沒有動。

做法：[P9 工具](ha-p9-kit.md)（`ha_p9_driver.mjs`＋`ha_p9_probe.py`），用測試專用的 HA 管理員（system-admin）登入。每個副本測之前先在管理 API 把寫入全關
（policy：`writes_enabled=false`、精確寫入授權 0，伺服器確認）。後端：

- Hermes、LiteLLM、Nextcloud、Headscale：展示機上的真後端（Headscale 用 48 小時到期的專用 API 金鑰）。
- n8n：負責人指定的 PaaS 上 woowtech 的 n8n，用只有讀取／列表 scopes、1 天到期的專用 API 金鑰（展示機上的 n8n 沒有可用的擁有者登入）。
- Odoo、EMQX：不接後端。展示機的 Odoo 只接受區網來源、也沒有測試帳號，要改正式 Odoo 的網路設定並重啟才能測，負責人決定併入之後的 Odoo 多帳號實測；EMQX 後端本來就停著。

| 項目 | 結果 |
|---|---|
| 寫入全關 | 七支新安裝都是寫入全開（odoo 8、n8n 33、hermes 21、emqx 16、litellm 25、nextcloud 4、headscale 21 個寫入授權），都改成 0 並經伺服器確認。 |
| token | 七支：沒有 CSRF 的輪替回 403；reveal 的 T1 可用 → rotate 後 T1 401、T2 可用 → revoke 後 T2 401、`token_active=false` → 重新發出後只有 T3 可用。 |
| 讀取 | Hermes 12/12、LiteLLM 13/15、Nextcloud 5/5、Headscale 7/9、n8n 23/37（含用列表結果裡的真實 ID 補測的讀取；ID 不記錄）。沒有實測到的讀取見下一節。 |
| 寫入拒絕 | Hermes 22、LiteLLM 26、Nextcloud 5、Headscale 22、n8n 44 項都被 gateway 拒絕（session 內 HTTP 200 的 JSON-RPC `-32602`；只有寫入操作的工具在寫入關閉時不列出，回 Unknown tool）。參數指向不可能存在的資料；沒有任何寫入送到後端。 |
| 後端斷線 | 五支有後端的都把後端網址換成解析不到的主機：每個讀取都回 HTTP 200 的結構化錯誤，沒有卡住或崩潰；換回原設定後清單再跑一次，結果與斷線前相同。 |
| 重啟 | `ha apps restart` 後 MCP 5.1～12.8 秒可用，第一次呼叫成功，MCP token 前後相同。 |
| 子程序被殺 | 有子程序的五支（含不接後端的 n8n）在容器內 SIGKILL MCP 子程序：容器沒有重啟，gateway 0.02～0.04 秒內照常回應，子程序自動重生後工具呼叫成功。Odoo、EMQX 沒設後端就沒有子程序（`products.child_spec` 回 None，設計如此），不適用。 |
| 效能 | tools/list p50 17～62 ms；工具呼叫 p50：LiteLLM 42 ms、Headscale 161 ms、Hermes 247 ms、n8n 262 ms、Nextcloud `list_calendars` 2.5 s（展示機 Nextcloud 的 CalDAV 本身慢）。 |
| 連線數 | 七支各 25 次 initialize＋DELETE 都成功，session 名額有釋放。 |
| Hermes 暫停排程（PR #85） | 另外暫時重裝 Hermes 副本、只開 `hermes_cron` 的 create 與 delete 兩個寫入授權（負責人同意）：`create` 帶 `enabled=false` 建的測試排程，讀回是 `enabled=false`、`state=paused`、沒有下次執行時間；隨即 `delete`，列表裡已經沒有它，再把寫入全關。排程設在 2 月 29 日（最快 2028 年），即使沒暫停也不會執行。 |

## 沒有實測到的讀取

- LiteLLM：`litellm_plugin_info` 後端沒有任何 plugin；`litellm_key_info` 要用金鑰雜湊，依負責人決定不測。
- Headscale：`headscale_policy` 的 get 與 diff。展示機的 Headscale 是 `policy.mode: file` 且沒設路徑，Headscale 自己的 `GET /api/v1/policy` 就回 500，MCP 照實回結構化的上游錯誤（`HEADSCALE_UPSTREAM_ERROR`，不可重試）。
- n8n：
  - `n8n_manage_agents`（7 個讀取操作）與 `n8n_test_workflow` 的 prepare：這兩支在 `surface.py` 是整支寫入授權（2026-10-15 `70d7dfb` 起，0.4.13 相同），寫入全關時整支不列出；它們的讀取操作另需 n8n 的 instance-level MCP access token（選填，這次沒設）。
  - `n8n_manage_folders`：這台 n8n 的授權不含 folders 功能（n8n 自己回的）。
  - `n8n_workflow_versions` 的 get／diff、`n8n_evaluations` 的 get_run／list_cases：後端沒有本機版本紀錄與評估執行可用。

## 測試中發現的工具問題（不是產品問題）

- `packaging/p9_plan.py` 只把 `supported-bounded` 的工具當讀取，tool-surface 自 `a52aad0` 起是 `supported-full`，所以原樣產生的清單沒有任何讀取、把讀取工具也列成拒絕。這次用只改這一行的本機副本產生清單。
  另外 tool-surface 的 `accepted_schema` 沒有子程序 schema（`tool_snapshot`）裡的必填欄位，清單有一部分讀取缺參數（上表的補測就是補這些）。兩者在本 PR 之外另開修正。
- 後端斷線測試第一次用了文件保留網段的 IP，存檔就被 `products.saved_destination` 拒絕（400；SSRF 防護，行為正確），改用解析不到的主機名稱。

清理：七個測試副本與資料、暫加的 repo、測試管理員、Headscale 與 n8n 的測試金鑰都已刪除；展示機原本的 app 狀態和測試前相同。測試前做了一份局部備份（HA 設定不含資料庫＋Headscale app），
留給負責人決定。這份紀錄不包含 token、密碼、cookie、金鑰、後端資料或私有拓樸。

**界線：** 從本 PR 分支暫加的 repo 安裝，不是商店同步後的安裝；展示機是 Core 2026.7.2；Odoo、EMQX 沒有後端實測；除了 Hermes 暫停排程那一筆（建立後立即刪除），寫入只驗證會被拒絕，沒有實際寫入；多帳號（開關仍關）不在這次範圍。
