# HA 多帳號 HM-20 provenance：後端網址拒絕 loopback（R1 前）（2026-11-15）

## 結論

- **產品開通後，後端網址不能指向 add-on 自己**：存檔與執行期都拒 127.0.0.0/8、::1、`localhost`（計畫 §8.7、DQ-10、DQ-40 ⑦；
  契約第 9 節 #39）。HA 的 add-on 跑在 Supervisor 的 bridge 網路（`host_network: false`），loopback 只會連到 add-on 自己的
  listener（8081、8099、子程式 3000 與 18000 起的 port），永遠不是後端。
- **誰決定**：`products.loopback_refused(product)`，就是 `features.enabled(product)`，每次呼叫時讀；沒有選項、請求、檔案或
  環境變數能改它。`MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空的，所以**今天任何產品都沒有新行為**。
- **存檔**：`check_saved_destinations`（含 n8n）多擋「這次改到的網址」裡指向 add-on 自己的主機：`localhost`、
  `localhost.localdomain`、`*.localhost`（大小寫、結尾點），127.0.0.0/8 與 ::1 的各種寫法（十進位、八進位、十六進位、
  省略段、結尾點、IPv4-mapped），以及數字寫法落在不允許位址的主機（`0` 是 0.0.0.0）。回應是既有的
  400 `{"error":"request denied"}`。n8n 的後端網址開通後也走整套既有檢查（它原本沒有任何存檔檢查）。區網照放。
- **執行期**：開通的產品的子程式環境多一個 `WOOW_MCP_DENY_LOOPBACK=1`（`products.child_spec`、`n8n_adapter.child_spec`）。
  - Python 子程式（`apps/runtime/backend_policy.py`）：連設定的後端的四個地方（httpx sync／async、XML-RPC HTTP／HTTPS），
    在 `checked_answers` 驗過全部答案之後、第一次連線之前，任何一個答案是 127.0.0.0/8 或 ::1 就整組拒絕
    （`BACKEND_DESTINATION_DENIED`）。字面位址、名稱解析到 127.0.0.1（DNS 指到 loopback）、混合答案都擋。
  - n8n（`apps/n8n/backend_policy.cjs`）：API 用戶端的 pinned agents，以及官方 MCP 用戶端的 pinned fetch（同一個設定的
    n8n 來源加 `/mcp-server/http`，帶 instance-level MCP access token）都拒 127.0.0.0/8、::1、0.0.0.0（含 IPv4-mapped）。
  - 變數只在載入時讀一次；沒設＝照舊；值不是 `1` 就拒絕啟動（固定訊息）。
- **n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 沒動**（使用者 2026-11-15 15:3x 定案）：webhook、chat、form 的網址照舊；
  多帳號時要不要收緊，交 HM-25 前的獨立安全審查。`decisions.md` 的 DQ-10 已記成已定，契約補 #87。
- **測試用替身開關**：`tests/loopback_backends.py` 在測試自己的程序裡換掉 `products.loopback_refused`，讓開通的產品也能用
  loopback 假後端（存檔照收、子程式不帶變數）。它在 `tests/`，沒有映像會複製；沒有執行期檔 import 它（測試鎖住）。
- **沒開通時一行行為都不變**：子程式 spec 與 HM-04 快照逐位元相同；HM-01 黃金回歸與兩個契約凍結的期望值一個都沒改，照過。
- 先寫測試：四個執行期檔換回基準時，兩個測試檔 192 案 134 失敗、58 通過（既有 31 案＋27 個「沒開通照舊」、區網照放、替身開關照舊一半的
  對照案）；換回本片的程式 192 案全過、0 skip（第 4 節）。
- 本機：全套 pytest 5342 案（commit 後的程式）5313 通過、29 失敗，都和本片無關：7 個要 root（同 HM-07、HM-13a 已知）、22 個瀏覽器測試
  是 clone 沒裝 Chromium（照 CI 補裝後重跑，66 案全過，第 6 節）。packaging unittest `Ran 201`、`OK (skipped=5)`；`validate.py` PASS；
  `tool_inventory.py` 0 漂移。兩個預檢：秘密 0 命中、帳本 OK（第 9 節）。
- 獨立安全審查：還沒做（要另一個代理；計畫 §12.0 第 9 點，合併前）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-20（計畫 §8.7、§12.3；風險中、工作量 M；受開關管；要獨立安全審查） |
| 分支 | `feat/ha-multiprofile-hm20-20261115`（這一階段只 commit，不 push、不開 PR；主對話等 HM-08、HM-09 合併後 rebase、送審） |
| HA 基準 | `claude-delivery` `76c1d78`（#98 HM-02 的合併；含 HM-00、HM-01、HM-02、HM-04～HM-07、HM-13a、HM-17） |
| 依據 | 計畫 §8.7「後端網址拒絕 loopback」、§7.2 第 9 點、§8.8 #39、§12.0、§12.3 HM-20；FM-77；契約第 3.1、4.1、7、9 節；`threat-model.md` 的同 uid 信任邊界 |
| 決策 | DQ-10（loopback 部分依 DQ-40 (a)；子題 2026-11-15 15:3x 使用者定）、DQ-40 ⑦；第 11 節 |
| 對齊的 PaaS | 加嚴，不是移植：PaaS pin `69ac425`（DQ-06）只有宣告 `url_connection_keys` 的 n8n、EMQX 在存檔過核心 SSRF（`Pc/connection_apply.py:69-87`、`Pc/routers/settings.py:416-417`、`P:apps/n8n/n8n_mcp_admin/main.py:31`、`P:apps/emqx/emqx_mcp_admin/main.py:18`）。名稱規則照 PaaS strict 的 `LOCALHOST_NAMES` 與 `*.localhost`（`Pc/util/ssrf.py`）；沒有移植 PaaS 程式或測試。PaaS 變動見第 10 節 |
| FM | FM-77（HA 加強，CF-06） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/products.py` | `loopback_refused`、`DENY_LOOPBACK_ENV`、`LOOPBACK_NAMES`、`_ipv4_number`、`numeric_host`、`loopback_host`；`saved_destination(value, *, loopback=False)`；`check_saved_destinations` 開通時多擋 loopback、n8n 加入；`child_spec` 開通時加變數（`WOOW_MCP_CHILD_TOKEN` 後面；Odoo Manage 在 `PYTHONPATH` 後面）。import `features`（第一個讀它的執行期檔） |
| `apps/n8n/n8n_adapter.py` | `child_spec` 在 `products.loopback_refused("n8n")` 時加變數（`WEBHOOK_SECURITY_MODE` 前面）；`WEBHOOK_SECURITY_MODE=permissive` 照舊，註解補 2026-11-15 的定案 |
| `apps/runtime/backend_policy.py` | `DENY_LOOPBACK_ENV`、`loopback_denied()`、`DENY_LOOPBACK`（載入時讀一次）、`connectable(answers)`；四個連線點改成 `connectable(resolve_…)`。`checked_answers`、`resolve_sync`、`resolve_async`、`allowed_address` 不變 |
| `apps/n8n/backend_policy.cjs` | `denyLoopback`（載入時讀一次）、`thisHost()`；`getPinnedAgents` 多一個條件；變數開時包住 `SSRFProtection.createPinnedFetch`。檔頭註解補一句。檔頭的上游 source hash 守門清單沒動 |
| `tests/test_saved_destinations.py` | 既有檔，加 HM-20 一節（第 4 節）；既有測試沒改 |
| `tests/test_backend_loopback.py`（新） | 子程式環境、Python 與 n8n 的執行期拒絕、每個產品的子程式用自己的環境與客戶端、真管理程序＋真 Odoo 子程式、替身開關（第 4 節） |
| `tests/loopback_backends.py`（新） | 測試用替身開關（第 3.5 節） |
| `tests/test_upgrade_zero_rewrite.py`（HM-07） | `UNWIRED` 拿掉 `features`（本片讓 `products.py` 讀它）；docstring 與註解照實改。HM-08 也會接線 `features`，rebase 時這一行可能衝突（第 13 節） |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES`：`apps/n8n/n8n_adapter.py` 換新摘要、`apps/n8n/backend_policy.cjs` 加一筆（`output_schemas.json` 記的是來源 commit 的位元組，照這個檔的規則另釘目前的位元組） |
| `docs/provenance/runtime-patches.json` | 四個列管檔換 SHA-256（用實際內容算）並加 HM-20 說明；`features.py` 只補說明（檔案沒變） |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只換 `apps/runtime/backend_policy.py`、`apps/n8n/backend_policy.cjs` 兩個摘要；`docs/tool-surface.md` 重產後沒有差異（工具清單不變） |
| `docs/multi-profile/decisions.md` | DQ-10 子題記成已定（日期、內容、交 HM-25 再評估）；DQ-17 記 UC-10 的做法；第 4 節待辦、變更紀錄各一列 |
| `docs/multi-profile/contract.md` | 第 3.1 節 `backend` 列、第 7 節「後端 loopback」列、第 9 節 #39 改寫、補 #87、第 10 節一列 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表：`tests/test_saved_destinations.py` 改寫、加 `tests/test_backend_loopback.py` |
| 本筆記 | — |

沒改：`features.py`（`MULTI_PROFILE_PRODUCTS` 維持空的）、`gateway.py`（存檔的 400 走既有的 `ValueError` → `BadRequest()`）、
`config.py`、`health.py`、Headscale 的 `http_policy.py`（本來就一律拒 loopback）、Hermes 的 MCP server 註冊守門
（`guards.py`，有自己的 loopback 訊息）、`WEBHOOK_SECURITY_MODE`、各產品 launcher、`session_idle.py`、`run_child.py`、
HM-01 的黃金回歸與契約凍結、HM-04 的快照（`tests/contract/child_spec_default.json`）、`conftest.py`、版號、`addons/<x>/`、
CHANGELOG、`upgrade-notes.yaml`、workflow、`packaging/`。

## 3. 設計

### 3.1 誰決定

- `loopback_refused(product)` 只有一行：`return features.enabled(product)`（測試用 AST 鎖住）。存檔檢查與兩個 `child_spec`
  每次都在呼叫當下查它，所以開關、替身開關都只要換這一個地方。
- 新增的錯誤不另開代碼：存檔被擋就是既有的 `ValueError` → 400 `{"error":"request denied"}`（契約第 4.1 節「格式驗證不過」）。
  這樣沒開通時的回應形狀不會多一種，面板也不用改。

### 3.2 存檔

- 只檢查這次改到的網址（既有規則）：開通前存下的 loopback 網址照樣讀得出來，也不擋改其他欄位；子程式連線時會擋（第 3.3 節）。
- 名稱：`localhost`、`localhost.localdomain`、`*.localhost`，大小寫不分、去掉結尾的點（照 PaaS strict 的 `LOCALHOST_NAMES`
  與 `*.localhost`，也和 Hermes MCP server 守門的名單相同）。
- 數字：`numeric_host` 先試 `ipaddress`，再照 inet_aton(3) 與 WHATWG URL 的 IPv4 解析器讀（1～4 段、十進位／八進位／十六進位、
  一個結尾點）。glibc 的 getaddrinfo 讀數字主機就是 inet_aton 的寫法；n8n 的 Node 子程式用 WHATWG 解析網址
  （`http://0x7f.1`、`http://2130706433`、`http://0177.0.0.1` 都是 127.0.0.1）。測試逐案比對兩邊的結果（第 4 節）。
- 數字寫法落在不允許位址也擋（開通時才擋）：`0`、`0x0`、`00` 是 0.0.0.0，在 Linux 會連到本機；`0xa9fea9fe` 是 metadata 位址。
  執行期本來就擋這些，存檔時擋只是讓錯誤提早出現。
- 存檔不解析 DNS：管理程序沒有載入 `backend_policy`，存檔時解析也只是當下的答案（之後可以改）。名稱指到 loopback 留給執行期
  解析後擋（PaaS 是存檔時解析；差異寫在契約 #39）。
- n8n：開通後 `backend_url` 走整套 `saved_destination`（metadata、路徑、port 0、zone id…），不只 loopback：計畫寫「n8n 也納入
  存檔檢查」，FM-77 的 HA 欄寫「n8n 不在 URL_FIELDS」。沒開通時 n8n 照舊不檢查。

### 3.3 執行期：Python 子程式

- `DENY_LOOPBACK` 在 `backend_policy.py` 載入時讀一次。子程式的環境是 `child_spec` 從頭組的（不繼承），launcher 與 vendored
  程式都不改 `os.environ`（本片 grep 過），所以只有管理程序決定這個值。
- `connectable(answers)`：在四個連線點，`checked_answers` 驗完全部答案之後、第一次 `connect` 之前檢查；任何一個是 loopback 就
  整組拒絕（和 `checked_answers`「先驗全部再連」的規則一樣）。`allowed_address` 已經擋 ::1 以外的 IPv6 寫法（含 IPv4-mapped）
  與 0.0.0.0/8，所以這裡只要看 127.0.0.0/8 與 ::1。
- 解析器本身不改：Hermes 的 MCP server 註冊守門（`guards.check_mcp_server_url`）也用 `resolve_async`，它檢查的是 Hermes 之後要連
  的網址、不是本子程式的後端，維持自己的 loopback 訊息（和 PaaS 同一句）。
- Headscale 的傳輸（`http_policy.py`）本來就一律拒 loopback，不受影響；它載入 `backend_policy` 時同樣會讀變數。

### 3.4 執行期：n8n

- `getPinnedAgents`（API 用戶端）：多一個條件，變數開時答案是 `thisHost()`（127.0.0.0/8、::1、0.0.0.0、`::`，IPv4-mapped 先轉回
  IPv4）就拒絕。
- 官方 MCP 用戶端（`services/n8n-official-mcp-client.js`）：設了 N8N_MCP_ACCESS_TOKEN 時，它連設定的 n8n 的
  `<origin>/mcp-server/http`，先用 webhook 的驗證（permissive，會放行 loopback），再用 `SSRFProtection.createPinnedFetch(答案)`
  釘住連線。這是同一個設定的後端，所以也要擋：變數開時包住 `createPinnedFetch`，答案裡有 `thisHost()` 就拒絕；釘住的就是
  實際連的位址，沒有檢查後再解析的空窗。n8n-mcp 2.96.2 裡只有這個用戶端呼叫 `createPinnedFetch`（webhook、chat、form 用
  `createPinnedAgents`）；測試掃描 `dist/` 鎖住這一點，n8n-mcp 升版若多了呼叫點會失敗、要重審。
- webhook、chat、form：完全不動（使用者 2026-11-15 定案）；`validateWebhookUrl`、`createPinnedAgents` 都沒包。
- `backend_policy.cjs` 檔頭的上游 source hash 守門清單沒改（沒有新增要釘的上游檔；上面那條假設改由測試守）。

### 3.5 替身開關：誰能設、為什麼安全

- 正式路徑只有兩個開關：產品開關（`features.MULTI_PROFILE_PRODUCTS`，只有升版 PR 改、使用者合併）與子程式的
  `WOOW_MCP_DENY_LOOPBACK`（只有 `child_spec` 設）。子程式的拒絕除了這個變數沒有別的開關；管理程序的環境變數、add-on 選項
  （維持 `{}`）、HTTP 請求、`/data` 的檔案都碰不到（測試在全新程序裡帶一堆看起來像開關的變數驗過）。
- 替身開關 `tests/loopback_backends.py`：`allowed()`（context manager）或 `install()`（給測試啟動的子程序前置碼）把
  `products.loopback_refused` 換成永遠回 False 的版本（未知產品照樣丟 `ValueError`）。效果等於「這個產品沒開通」：存檔照收
  loopback、子程式不帶變數。
- 誰能打開：只有在已經 import `mcp_admin_core` 的那個程序裡執行的程式碼。它在 `tests/`，`apps/*/Dockerfile` 只複製
  `packages/mcp-admin-core`、`apps/` 與兩個 packaging 檔，沒有映像帶著它；沒有任何執行期檔 import 它。兩點都有測試。
- 為什麼安全：能在管理程序裡執行程式碼的人本來就能做任何事（同 uid 信任邊界，DQ-37），替身開關沒有多給任何能力；它不讀環境
  變數、選項或檔案，所以外面打不開。子程式這邊沒有替身：子程式的拒絕只看變數。
- 這個規則是縱深防禦，不是隔離邊界：被攻破的子程式可以自己改掉 `os.environ` 或程式碼（DQ-37）；它防的是設定錯誤、被改過的
  後端網址把憑證送到 add-on 自己的 listener，以及 DNS 指到 127.0.0.1。

## 4. 新測試與先紅後綠

### 4.1 新測試（兩個檔共 161 案是本片的；本機 0 skip）

`tests/test_saved_destinations.py` 的 HM-20 一節（59 案；同檔既有 31 案不變）：

| 測試 | 案數 | 驗什麼 |
|---|---|---|
| `test_a_loopback_url_is_refused_when_saved_once_the_product_is_switched_on` | 9 | 每個產品（含 n8n、Hermes 兩個網址欄）× 33 種寫法：沒開通＝HM-20 之前的答案（只有兩個 IPv4-mapped 本來就擋）、開通全擋、替身開關內同沒開通、出了替身又擋 |
| `test_a_switched_on_product_still_saves_a_lan_public_or_named_backend` | 9 | 開通後區網、公網、名稱（含 `localhost.invalid`、`127-0-0-1.invalid`）、區網的數字寫法照存 |
| `test_n8n_gets_the_whole_check_once_switched_on` | 1 | n8n 開通前不檢查、開通後既有的 15 種拒絕寫法都擋 |
| `test_the_switch_is_per_product` | 1 | 只開 Odoo：其他 8 個產品照存 loopback |
| `test_only_a_url_this_save_changes_is_checked` | 1 | 開通後舊的 loopback 網址不擋改其他欄位；改網址照擋 |
| `test_the_admin_api_refuses_a_loopback_url_once_switched_on` | 18 | 9 產品 × `backend`、`backend/patch`：400、本體逐位元 `{"error":"request denied"}`、state 不變、沒重啟；區網 200 |
| `test_switched_off_or_with_the_double_a_loopback_url_is_saved_as_before` | 18 | 同上兩條路：沒開通、或開通＋替身開關時照存 |
| `test_numeric_hosts_are_read_as_the_resolver_and_n8n_read_them` | 1 | 44 個主機字串：`numeric_host` 和 glibc `inet_aton`、Node 的 WHATWG URL 讀出的位址逐案相同 |
| `test_saved_and_run_time_checks_agree_once_switched_on` | 1 | 開通時存檔與帶變數的子程式檢查一致（數字主機，55 個網址） |

`tests/test_backend_loopback.py`（102 案）：

| 測試 | 案數 | 驗什麼 |
|---|---|---|
| `test_a_switched_on_product_s_child_gets_the_variable_and_nothing_else_changes` | 16 | HM-04 快照的 16 個案例：開通＝快照＋一個 `WOOW_MCP_DENY_LOOPBACK=1`，其他逐位元（含順序）相同；沒開通、替身開關＝快照 |
| `test_the_rule_is_the_product_switch_alone` | 1 | `loopback_refused` 的本體只有 `return features.enabled(product)`（AST） |
| `test_no_variable_of_the_management_process_turns_the_rule_off` | 1 | 全新程序、只跑正式程式、帶一堆看起來像開關的變數：開通的 Odoo、n8n 存檔照擋、子程式照帶變數 |
| `test_the_variable_is_read_once_when_the_policy_loads`、`test_any_other_value_refuses_to_start` | 1＋9 | Python 政策：`1` 開、沒設關、9 種其他值拒絕啟動（固定訊息）；看起來像開關的變數無效 |
| `test_a_loopback_answer_is_refused_only_with_the_variable` | 4 | 127.0.0.1、127.1.2.3、127.255.255.254、::1 |
| `test_every_answer_a_name_resolves_to_is_checked` | 6 | 名稱解析出混合答案（區網＋loopback、loopback 在前或在後、IPv6）整組拒絕；全區網照放 |
| `test_each_transport_refuses_a_loopback_backend_before_any_request` | 6 | httpx sync、async、XML-RPC × 字面 127.0.0.1、名稱解析到 127.0.0.1：帶變數 `BACKEND_DESTINATION_DENIED`、真的假後端收到 0 個請求；不帶變數同一個請求到得了 |
| `test_xml_rpc_over_https_refuses_a_loopback_backend_before_the_handshake` | 1 | HTTPS 連線點也擋 |
| `test_a_lan_backend_still_connects_with_the_variable` | 3 | 帶變數時區網照連（三種傳輸） |
| `test_the_child_refuses_a_loopback_backend_when_it_connects` | 32 | 8 個 Python 產品（含 Headscale、Odoo Manage）用自己的 child_spec 環境與自己的客戶端程式：開通時字面、DNS 指到 127.0.0.1 都在連線前被擋；區網照連；沒開通照舊連 loopback（Headscale 一直擋） |
| `test_n8n_refuses_a_loopback_backend_once_switched_on` | 1 | n8n 開通：12 種 loopback 寫法（含 WHATWG 的十進位、八進位、十六進位、結尾點、`localhost`、DNS、混合）都擋，4 個區網照放；帶看起來像開關的變數 |
| `test_n8n_switched_off_connects_to_loopback_as_before` | 1 | n8n 沒開通：loopback 照放 |
| `test_the_api_and_the_official_mcp_client_reach_a_loopback_n8n_only_when_switched_off` | 2 | 真的假 n8n 在 127.0.0.1：開通時 API 與官方 MCP 用戶端 0 個請求；沒開通兩邊都到得了 |
| `test_n8n_webhooks_stay_permissive_with_the_variable` | 1 | 開通後 webhook 驗證照 permissive、`createPinnedAgents` 照常；`createPinnedFetch` 擋 7 種 add-on 自己的位址（127.0.0.1、127.9.9.9、::1、0.0.0.0、`::`、兩個 IPv4-mapped），放 2 個區網 |
| `test_the_n8n_child_starts_only_without_the_variable_or_with_1` | 11 | n8n 子程式：沒設與 `1` 能啟動，9 種其他值拒絕啟動 |
| `test_only_the_official_mcp_client_makes_a_pinned_fetch` | 1 | 掃 n8n-mcp 的 `dist/`：呼叫 `createPinnedFetch` 的只有官方 MCP 用戶端；它的端點是設定的來源 |
| `test_the_double_is_test_code_no_image_carries`、`test_the_double_is_on_only_inside_its_block`、`test_the_double_in_a_subprocess_preamble` | 3 | 替身開關：沒有執行期檔 import 它、Dockerfile 不複製 `tests/`；只在區塊內有效（例外時也還原）；子程序前置碼裝上才有效 |
| `test_a_switched_on_odoo_refuses_its_loopback_fake_backend_end_to_end` | 2 | 真管理程序（`run_product`，前置碼開通 Odoo）＋真 Odoo 子程式：子程式的 `/proc` 環境有變數（只看這一項、不印）、一直在線的 loopback 假後端收到 0 個請求、用戶端的 tools/call 被拒；前置碼加替身開關時變數不在、同一個呼叫到得了假後端 |

### 4.2 先紅後綠

| 輪 | 程式 | 測試 | 結果 |
|---|---|---|---|
| 紅 | 四個執行期檔拿掉（`git stash`，在共用鎖裡做，跑完放回並核對 SHA-256） | 兩個檔 192 案（新 161 案＋既有 31 案） | 135 失敗、57 通過、61.8 秒。通過的是既有 31 案與 26 個新的對照案（沒開通照舊、區網照放、替身開關的「照舊」那一半、`dist/` 掃描） |
| 綠（第一輪） | 本片的程式 | 兩個檔＋相關的既有檔共 23 檔 1064 案 | 1061 通過、3 失敗，都是測試本身的錯：Dockerfile 有 9 個（Odoo Manage 也有）不是 8 個；一致性測試解析到 HM-01 禁止的 port 3000（改用 8069，位址規則不看 port）；端到端測試原本期待回覆帶 `BACKEND_DESTINATION_DENIED`，但 Odoo 的 private probe 只回固定的 `BACKEND_UNAVAILABLE`（`apps/odoo/launch.py` `probe_failure`），改成驗子程式環境的變數、假後端 0 個請求、回覆被拒 |
| 綠（第二輪） | 同上 | 兩個檔 192 案 | 192 通過、0 skip、63.5 秒 |
| 紅（第二輪，最後的測試） | 四個執行期檔換回基準 `76c1d78` 的內容（共用鎖裡做，跑完從私有備份放回並核對 SHA-256） | 兩個檔 192 案 | 134 失敗、58 通過、61.4 秒。通過的是既有 31 案與 27 個對照案（上一輪的 26 個，加上修好的 `test_the_double_is_test_code_no_image_carries`：它檢查的是映像與 import，本來就和實作無關） |
| 綠（第三輪，最後的測試） | 本片的程式 | 兩個檔 192 案 | 192 通過、0 skip、65.5 秒 |

### 4.3 沒做的

- 臨時突變（拿掉單一條件看測試會不會失敗）這次沒做：共用的 pytest 鎖一直被其他工作流的全套佔著，排一次要等很久。
  獨立審查若要求，再補。

## 5. 受影響的既有測試

- `tests/test_upgrade_zero_rewrite.py`（HM-07）：`UNWIRED` 拿掉 `features`，docstring 與註解照實改（第 2 節）。
  `test_no_runtime_file_imports_the_unwired_modules` 與 `test_no_entry_point_imports_the_unwired_modules` 照過；
  `test_nothing_binds_the_switch_at_import` 照過（`products.py` 只呼叫 `features.enabled`）。
- `tests/test_output_schemas.py`：`CURRENT_POST_SOURCE_BYTES` 兩筆（第 2 節）。
- 其餘既有測試一個都沒改，期望值也沒改；沒開通時的行為由下列照過的測試鎖住：HM-01 的
  `test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`，HM-04 的
  `test_child_port_param.py`（快照沒改），`test_saved_destinations.py` 的既有 31 案、`test_six_egress.py`、
  `test_backend_network.py`、`test_backend_policy_python.py`、`test_real_products.py`、`test_real_n8n.py` 等（第 6 節）。

## 6. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

全部 pytest 都用 `flock …/wave1-pytest.lock` 排隊（共用鎖；沒動 `conftest.py`、沒刪鎖檔）。

| 檢查 | 結果 |
|---|---|
| 綠（第一輪）：23 檔（兩個新檔＋`test_upgrade_zero_rewrite`、`test_child_port_param`、HM-01 三檔、`test_backend_network`、`test_backend_policy_python`、`test_six_egress`、`test_headscale_product`、`test_n8n_permissive_webhooks`、`test_child_bearer`、`test_nextcloud_child`、`test_boundary`、`test_output_schemas`、`test_tool_inventory`、`test_hermes_mcp_url_guard`、`test_ledger_precheck`、`test_resolver_regressions`、`test_raw_backend_errors`、`test_real_products`、`test_real_n8n`） | 1064 案：1061 通過、3 個測試本身的錯（第 4.2 節），568.6 秒 |
| 綠（第二輪）：兩個新檔 | 192 通過、0 skip、63.5 秒 |
| 全套 pytest（commit 後的程式：當時的 HEAD `a199d33`，和現在的 `8fc07ab`＋`e55af02` 只差 `test_saved_destinations.py` 的 7 行 log 掃描標記；那兩個檔在紅、綠第二、三輪已用最後的版本重跑） | 5342 案、0 skip、30 分 57 秒：5313 通過、29 失敗。7 個要 root：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`（基準就要 root，CI 以 root 跑）。22 個瀏覽器測試（`test_owned_browser_ipc.py` 5、`test_owned_browser_redirect.py` 16、`test_owned_ui.py` 1）：這個 clone 沒裝 Playwright 的 Chromium（`Executable doesn't exist …/.local-browsers/chromium_headless_shell-1228`）。照 CI 用 `npm run browser:install --prefix packages/mcp-admin-ui` 補裝後重跑這 3 個檔再加 `test_owned_browser.py`、`test_admin_ui.py`：66 通過、0 失敗、39.2 秒 |
| `scripts/tool_inventory.py --write` 後再跑一次檢查模式 | exit 0；`docs/tool-surface.md` 0 差異 |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt`，`discover -s packaging`；沒動 clone 的 `.venv`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| `node --check apps/n8n/backend_policy.cjs` | 通過 |

## 7. 只在 CI 跑的測試

- 本片的新測試都不需要 root，本機（一般使用者）全跑過；CI 以 root 跑，結果應該相同（測試不靠執行身分判斷）。
- 端到端測試讀子程式的 `/proc/<pid>/environ`：一般使用者讀得到自己的子程式；CI 的 root 也讀得到。
- `_whatwg_hosts` 與 n8n 的測試用 `node`：本機是 v26.12.1；CI 把 `/usr/bin/node`、`/usr/local/bin/node` 都釘成 v26.12.1。
- 全套 pytest：本機 5313 通過，失敗的 29 個都和本片無關（第 6 節）；7 個要 root 的案例只在 CI 驗。以 CI（root、0 skip）為準。
- Playwright 與面板測試：本片沒改面板，結果以 CI 為準。

## 8. `checks` 秒數

開 PR 後補（前：基準 `76c1d78` 的 run；後：本片 PR 的 run）。推估：本片兩個測試檔本機約 64 秒（其中 32 個子程式案約 41 秒、
端到端兩案約 7 秒），CI 推估多 50～80 秒。

## 9. 預檢結果

- **秘密預檢**（`.venv/bin/python -I scripts/secret_precheck.py --tools …/hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full`；
  gitleaks 8.28.0，釘版並核對過；設定是 `packaging/supply_chain.py gitleaks_config()`）：
  - 程式與文件的 2 個 commit（`8fc07ab`、`e55af02`）：`result: OK, 0 findings`；`--full` 的 HEAD 全部檔與全歷史也 0。
    （重建 commit 前的 `29041e4`、`a199d33` 與 `d042816`、`597de6b` 也各跑過一次，同樣 0；內容只差 7 行 log 掃描標記與 commit 訊息。）
  - 加上本筆記的 commit（最終 HEAD，3 個 commit）：`result: OK, 0 findings`；`--full` 也 0（commit 之後馬上重跑，結果寫在交回報告）。
  - 新的 64 hex 只有帳本摘要與 `tests/test_output_schemas.py` 的兩筆目前位元組（同 HM-04 的寫法），都沒有命中。
- **帳本預檢**（`.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery`）：`runtime-patches.json` 171 個、
  `runtime-sources.json` 70 個、`tool-surface.json` 159 個，0 漂移、0 缺檔；改到的列管檔 4 個，兩本帳本都改了；
  新增或改到而沒列管的執行期檔 0 個（`tests/loopback_backends.py` 在 `tests/`，不是執行期檔）。`result: OK`。

## 10. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

- 在本機 PaaS git 唯讀查（`git -C … log/show`，沒有 fetch、沒有 checkout）。相關檔：`util/ssrf.py`、`connection_apply.py`、
  `routers/settings.py`、`launch_policy.py`、`apps/n8n/n8n_mcp_admin/`、`apps/emqx/emqx_mcp_admin/`、`apps/nextcloud/nextcloud_mcp_admin/`、
  `apps/headscale/headscale_mcp_admin/connection.py`、`packages/mcp-admin-core/tests/test_ssrf.py`。
- `69ac425..cf3d0d5`（任務給的 main）：這些檔 0 個 commit。
- 本機的 `origin/main` 已經是 `5b84b5d`（2026-11-14 23:08 UTC；不是本片 fetch 的）。`cf3d0d5..5b84b5d` 動到上面的檔有 3 個 commit，
  都在 Nextcloud 的管理端：
  - `0f43fd3`（#152）：Nextcloud 的 `base_url` 存檔與「測試連線」過核心的 SSRF 檢查（strict，擋 loopback、私網）。PaaS 自己寫明
    子程式連線時沒有第二道檢查。和本片的關係：PaaS 現在 n8n、EMQX、Nextcloud 三個產品存檔擋 loopback；HA 開通後全部產品都擋，
    而且執行期也擋。契約 #39 的 PaaS 欄已寫進。
  - `0f94aa4`（#154）：Nextcloud 換使用者或網址時撤銷舊的 MCP 網址（連線身分綁定 token）。屬 DQ-40 ⑩、HM-22，不是本片。
  - `4f1a77f`（#152）：Nextcloud 的 log 遮罩保留 args 形狀。屬 HM-02 一類，不是本片。

## 11. 本片用到的決策

- DQ-10（後端網址拒絕 loopback）：loopback 部分依 DQ-40 (a)（2026-11-14 13:4x），照計畫 §8.7。子題（n8n
  `WEBHOOK_SECURITY_MODE=permissive`）2026-11-15 15:3x 使用者定：**維持不動**（負責人 2026-10-15 的決定）；HM-20 只管設定的後端
  網址；多帳號時要不要收緊 webhook，留到 HM-25（n8n 開通）前的獨立安全審查。`decisions.md` 已記。
- DQ-40 ⑦：後端網址拒絕 loopback 是 HA 加嚴、列入給 PaaS 的回補建議（HM-29）。
- DQ-32：開關＝發版；本片不加任何產品。DQ-28：OpenDesign、Odoo Manage 不開放（規則對它們一樣成立，只是永遠不會開通）。
- DQ-37：同 uid 信任邊界（第 3.5 節最後一點）。DQ-36：commit 不加 AI 署名。DQ-33：本機 TMPDIR 規則。
- UC-10 的做法（2026-11-15 15:3x 使用者定：HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭，探針實測不通再補網址路徑備案）：本片沒用到，
  照任務只記在 `decisions.md` 的 DQ-17。
- 實作時做的選擇（不是 §13 的題目；請主對話判斷要不要寫進 `decisions.md`）：
  1. 存檔的拒絕不另開錯誤代碼，用既有的 400 `{"error":"request denied"}`（第 3.1 節）。
  2. 名稱名單照 PaaS strict（`localhost`、`localhost.localdomain`、`*.localhost`）；`ip6-localhost` 這類 `/etc/hosts` 別名不列，
     交給執行期解析後擋。
  3. 開通時，數字寫法落在不允許位址也在存檔時擋（例如 `0`＝0.0.0.0），不只 loopback。
  4. 開通時 n8n 走整套既有存檔檢查，不只 loopback。
  5. 存檔不解析 DNS（第 3.2 節）。
  6. n8n 的官方 MCP 端點算「設定的後端」，一起擋；n8n 這邊另擋 0.0.0.0（webhook 驗證在 permissive 下會放行它）。
  7. 變數的值只收 `1`，其他值拒絕啟動（和 HM-06 的 bearer 一樣 fail closed）。

## 12. 驗收條件（計畫 §12.3 HM-20、§12.0）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR 的 CI（這一階段不 push、不開 PR）。本機：第 6 節 |
| 開關關時 HM-01 逐位元 | 通過：HM-01 的黃金回歸與兩個契約凍結照過、期望值沒改；子程式 spec 等於 HM-04 快照（16 案）；存檔照舊（既有 31 案＋新的「沒開通照舊」案） |
| 開關開時存檔拒 loopback | 通過：全部 9 個產品（含 n8n）、兩條存檔路徑、33 種寫法；400＋既有本體；區網照放 |
| 開關開時執行期拒 loopback（含 DNS 指到 127.0.0.1） | 通過：8 個 Python 產品各用自己的子程式環境與客戶端（字面、DNS、混合答案）；三種傳輸對真的假後端 0 個請求；n8n 的 API 與官方 MCP 用戶端；真管理程序＋真 Odoo 子程式端到端 |
| 每個產品至少一個案例 | 通過：存檔 9 個產品、執行期 9 個產品（含 n8n） |
| 替身開關只在測試裡打開、正式路徑不能被環境變數以外的方式關掉 | 通過：第 3.5 節；`test_the_double_*` 三案、`test_the_rule_is_the_product_switch_alone`、`test_no_variable_of_the_management_process_turns_the_rule_off`、變數的值只收 `1` |
| n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 不動 | 通過：快照照舊；`test_n8n_webhooks_stay_permissive_with_the_variable` |
| 先寫測試、記下先紅後綠 | 通過（第 4.2 節） |
| 新測試用 HM-01 的 log 掃描、不得條件式 skip | 通過：新測試都在 `log_scan` 下（`test_backend_loopback.py` 整個檔用 `pytestmark`；`test_saved_destinations.py` 的新測試逐一標記，既有 31 案不動；API 案另外監看 state 的 token 與憑證）；0 skip |
| 測試資料規則（§12.0 第 4 點） | 通過：網址用 `.invalid`、憑證 `DUMMY-…`、token `T`×43／`C`×43；沒有 commit 隨機 token；秘密預檢 0 命中 |
| 同 PR 更新帳本、tool-surface | 通過：第 2、9 節 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空的 | 通過 |
| 比 PaaS 嚴的部分對到契約第 9 節 | 通過：#39 改寫（範圍、執行期、數字寫法、回應本體、區網、存檔不查 DNS）；n8n webhook 模式補 #87 |
| 獨立安全審查 | **還沒做**：要另一個代理，合併前做（計畫 §12.0 第 9 點）；報告放 `artifacts/`、PR 連結附上 |

## 13. 還沒解決、交給後面的片

- **獨立安全審查**：還沒做（第 12 節）。建議看：數字寫法的解析是否和 glibc／WHATWG 一致（第 3.2 節）、n8n 官方 MCP 路徑包住
  `createPinnedFetch` 的假設（第 3.4 節）、替身開關的安全論證（第 3.5 節）。
- **rebase（HM-08、HM-09 合併後）**：
  - `tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED`：HM-08 也會接線 `features`，同一行可能衝突；兩片都拿掉 `features` 就好。
  - 帳本：`products.py`、`features.py` 的說明與摘要，照衝突規則以 `claude-delivery` 為底重產、重算 SHA-256。
  - `products.py`：計畫的檔案順序是 HM-04 → HM-06 → HM-07 → HM-20 → HM-12；HM-09 若改 `child_spec`（帳號 port、資源），變數的位置
    照本片（`WOOW_MCP_CHILD_TOKEN` 後面）。額外帳號的子程式也用 `child_spec`，所以開通後同樣帶變數。
  - rebase 後重跑兩個新測試檔、HM-01 守門、`test_child_port_param.py`，重產帳本與 tool-surface。
- **HM-19a（Odoo 0.5.0 把 `odoo` 加進 `MULTI_PROFILE_PRODUCTS`）**：開通後 Odoo 存檔與子程式都拒 loopback，所以用 loopback 假後端的
  既有 Odoo 測試（例如 HM-01 黃金回歸、`tests/test_real_products.py` 的 Odoo 案、各個 `test_odoo_*` 執行期測試）會失敗：要在
  fixture 裡用 `loopback_backends.allowed()`，或在子程序前置碼呼叫 `loopback_backends.install()`。本片沒動那些測試。
  發版文件（CHANGELOG、DOCS、`upgrade-notes.yaml`）要寫計畫 §7.2 第 9 點：「後端網址不能填 loopback」。
- **HM-25（n8n 開通）**：開工前的獨立安全審查要評估「多帳號時 n8n webhook 要不要收緊」（DQ-10 子題的待辦，`decisions.md` 第 4 節）：
  開通後設定的 n8n（API、官方 MCP 端點）拒 loopback，但 webhook、chat、form 的網址照 permissive，仍可指到 add-on 自己的 listener。
  `run.py` 收斂到 ProfileRuntime 時，`n8n_adapter.child_spec` 的變數要留著。n8n-mcp 升版時 `test_only_the_official_mcp_client_makes_a_pinned_fetch`
  會擋下「多了 `createPinnedFetch` 的呼叫點」。
- **使用面**：開通前存的 loopback 網址開通後照樣讀得出來，但子程式連不上；Odoo 的健康檢查只回 `BACKEND_UNAVAILABLE`（不說是被
  loopback 規則擋），用戶端看到「Backend unreachable」。HA 的 bridge 網路下 loopback 本來就連不到真的後端，所以正常安裝不會有這種
  網址；要不要在面板或健康原因寫明是 loopback 規則，留給 HM-18（文件）或主對話決定。
- **PaaS 回補（HM-29）**：PaaS 的 Nextcloud 從 #152 起存檔過 SSRF，但子程式連線時沒有第二道（PaaS 自己寫明）；HA 的執行期檢查
  （連線前驗每個答案）可列入回補建議（DQ-40 ⑦）。
- `checks` 秒數：開 PR 後補。
