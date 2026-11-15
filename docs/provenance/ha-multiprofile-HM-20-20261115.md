# HA 多帳號 HM-20 provenance：後端網址拒絕 loopback（R1 前）（2026-11-15）

## 結論

- **產品開通後，後端網址不能是 loopback**：存檔與執行期都拒 127.0.0.0/8、::1、`localhost`（計畫 §8.7、DQ-10、DQ-40 ⑦；
  契約第 9 節 #39）。HA 的 add-on 跑在 Supervisor 的 bridge 網路（`host_network: false`），loopback 只會連到 add-on 自己的
  listener（8081、8099、子程式 3000 與 18000 起的 port），永遠不是後端。範圍只有 loopback：add-on 自己的 bridge 位址與主機名
  不在規則裡（DQ-10 的範圍；已知限制寫在 `threat-model.md` 第 3 節）。
- **誰決定**：`products.loopback_refused(product)`，就是 `features.enabled(product)`，每次呼叫時讀；沒有選項、請求、檔案或
  環境變數能改它。`MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空的，所以**今天任何產品都沒有新行為**。
- **存檔**：`check_saved_destinations`（含 n8n）多擋「這次改到的網址」裡是 loopback 的主機：`localhost`、
  `localhost.localdomain`、`*.localhost`（大小寫、結尾點），127.0.0.0/8 與 ::1 的各種寫法（十進位、八進位、十六進位、
  省略段、結尾點、IPv4-mapped），以及數字寫法落在不允許位址的主機（`0` 是 0.0.0.0）。回應是既有的
  400 `{"error":"request denied"}`。n8n 的後端網址開通後也走整套既有檢查（它原本沒有任何存檔檢查）。區網照放。
- **執行期**：開通的產品的子程式環境多一個 `WOOW_MCP_DENY_LOOPBACK=1`（`products.child_spec`、`n8n_adapter.child_spec`），
  預設帳號與每個額外帳號（18000 起）的子程式都有。
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
  所以映像裡用不了：產品開通時，容器驗收要照 Headscale 的做法（第 13 節；packaging 測試鎖住）。
- **沒開通時一行行為都不變**：子程式 spec 與 HM-04 快照逐位元相同；HM-01 黃金回歸與兩個契約凍結的期望值一個都沒改，照過。
- 先寫測試：四個執行期檔換回基準時，兩個測試檔 192 案 134 失敗、58 通過（既有 31 案＋27 個「沒開通照舊」、區網照放、替身開關照舊一半的
  對照案）；換回本片的程式 192 案全過、0 skip（第 4 節）。
- **獨立安全審查：修正後通過**（必修 2、建議 8；報告在 repo 外：`artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-20.md`）。
  兩個必修都處理了；8 個建議都採用，只有 S-8 的一半（Hermes `guards.py` 的註解）照審查建議交 HM-24。執行期程式沒改：
  `products.py` 只改註解與 docstring（去掉 docstring 後的 AST 和審查時的 `af581d1` 相同）。處理表在第 14 節。
  - MF-1：補額外帳號子程式的測試（HM-04 的 16 個案例 × 18000、18042、18099，48 案）。
  - MF-2：第 13 節補容器驗收的交接；packaging 加 2 個測試，產品一開通 CI 就紅。
- 本機（審查修正後）：相關 30 檔 1,379 案全過、0 skip、594.6 秒；packaging unittest `Ran 203`、`OK (skipped=5)`；`validate.py` PASS；`tool_inventory.py` 0 漂移；
  兩個預檢 OK（第 6、9 節）。全套 pytest 是審查前跑的（5342 案，失敗的 29 個都和本片無關）；rebase 後要再跑一次（第 13 節）。

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
| 獨立安全審查 | 2026-11-15，修正後通過（必修 2、建議 8）；報告 `artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-20.md`，證據在同層的 `evidence-review-HM-20/`（都在 repo 外）；處理見第 14 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/products.py` | `loopback_refused`、`DENY_LOOPBACK_ENV`、`LOOPBACK_NAMES`、`_ipv4_number`、`numeric_host`、`loopback_host`；`saved_destination(value, *, loopback=False)`；`check_saved_destinations` 開通時多擋 loopback、n8n 加入；`child_spec` 開通時加變數（`WOOW_MCP_CHILD_TOKEN` 後面；Odoo Manage 在 `PYTHONPATH` 後面）。import `features`（第一個讀它的執行期檔）。審查後只改註解與 docstring：規則叫「loopback」、不說「add-on 自己」（S-4）；`child_spec` 的註解寫明每個 port 的子程式都帶變數（MF-1） |
| `apps/n8n/n8n_adapter.py` | `child_spec` 在 `products.loopback_refused("n8n")` 時加變數（`WEBHOOK_SECURITY_MODE` 前面）；`WEBHOOK_SECURITY_MODE=permissive` 照舊，註解補 2026-11-15 的定案 |
| `apps/runtime/backend_policy.py` | `DENY_LOOPBACK_ENV`、`loopback_denied()`、`DENY_LOOPBACK`（載入時讀一次）、`connectable(answers)`；四個連線點改成 `connectable(resolve_…)`。`checked_answers`、`resolve_sync`、`resolve_async`、`allowed_address` 不變 |
| `apps/n8n/backend_policy.cjs` | `denyLoopback`（載入時讀一次）、`thisHost()`；`getPinnedAgents` 多一個條件；變數開時包住 `SSRFProtection.createPinnedFetch`。檔頭註解補一句。檔頭的上游 source hash 守門清單沒動。審查後沒再改（第 14 節 S-4） |
| `tests/test_saved_destinations.py` | 既有檔，加 HM-20 一節（第 4 節）；既有測試沒改。審查後：註解改說 loopback（S-4）；API 案先比 state 的位元組、再斷言，失敗時不印 state（S-6） |
| `tests/test_backend_loopback.py`（新） | 子程式環境、Python 與 n8n 的執行期拒絕、每個產品的子程式用自己的環境與客戶端、真管理程序＋真 Odoo 子程式、替身開關（第 4 節）。審查後加 3 個測試（MF-1、S-2、S-3）；4 處斷言改成先算好、刪掉環境再斷言（S-6） |
| `tests/loopback_backends.py`（新） | 測試用替身開關（第 3.5 節） |
| `tests/test_upgrade_zero_rewrite.py`（HM-07） | `UNWIRED` 拿掉 `features`（本片讓 `products.py` 讀它）；docstring 與註解照實改。HM-08 也會接線 `features`，rebase 時這一行可能衝突（第 13 節） |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES`：`apps/n8n/n8n_adapter.py` 換新摘要、`apps/n8n/backend_policy.cjs` 加一筆（`output_schemas.json` 記的是來源 commit 的位元組，照這個檔的規則另釘目前的位元組） |
| `packaging/test_container_acceptance.py`、`packaging/test_container_probe.py` | 審查後各加 1 個測試（MF-2）：`features.MULTI_PROFILE_PRODUCTS` 裡的產品（今天是空的，所以只驗 Headscale）的容器驗收要開一次性 internal bridge、假後端要綁容器的私有位址。`container_acceptance.py`、`container_probe.py` 本身沒改 |
| `docs/provenance/runtime-patches.json` | 四個列管檔換 SHA-256（用實際內容算）並加 HM-20 說明；`features.py` 只補說明（檔案沒變）。審查後 `products.py` 再換一次摘要並補一句（只改註解） |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只換 `apps/runtime/backend_policy.py`、`apps/n8n/backend_policy.cjs` 兩個摘要；`docs/tool-surface.md` 重產後沒有差異（工具清單不變）。審查後不用再產（`products.py` 不在 tool-surface；檢查模式 exit 0） |
| `docs/multi-profile/decisions.md` | DQ-10 子題記成已定（日期、內容、交 HM-25 再評估）；DQ-17 記 UC-10 的做法；第 4 節待辦、變更紀錄各一列。審查後第 4 節的 DQ-10 補 HM-25 審查要看的事實（S-7） |
| `docs/multi-profile/contract.md` | 第 3.1 節 `backend` 列、第 7 節「後端 loopback」列、第 9 節 #39 改寫、補 #87、第 10 節一列。審查後：#39 補 n8n 開通後的整套存檔檢查、和 PaaS n8n 的差異、範圍只有 loopback（S-1、S-4），第 3.1 節同步；第 7 節補額外帳號的子程式與 Headscale 的代碼（MF-1、S-8）；第 10 節那一列補一句 |
| `docs/multi-profile/threat-model.md` | 審查後第 3 節加一行已知限制：add-on 自己的主機名與 bridge 位址不在規則裡（S-4） |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表：`tests/test_saved_destinations.py` 改寫、加 `tests/test_backend_loopback.py`。審查後補新測試的內容與兩個 packaging 測試 |
| 本筆記 | — |

沒改：`features.py`（`MULTI_PROFILE_PRODUCTS` 維持空的）、`gateway.py`（存檔的 400 走既有的 `ValueError` → `BadRequest()`）、
`config.py`、`health.py`、Headscale 的 `http_policy.py`（本來就一律拒 loopback）、Hermes 的 MCP server 註冊守門
（`guards.py`，有自己的 loopback 訊息；註解交 HM-24）、`WEBHOOK_SECURITY_MODE`、各產品 launcher、`session_idle.py`、`run_child.py`、
HM-01 的黃金回歸與契約凍結、HM-04 的快照（`tests/contract/child_spec_default.json`）、`conftest.py`、版號、`addons/<x>/`、
CHANGELOG、`upgrade-notes.yaml`、workflow、`packaging/` 的程式（只加測試）。

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
  存檔檢查」，FM-77 的 HA 欄寫「n8n 不在 URL_FIELDS」。沒開通時 n8n 照舊不檢查。位址的部分和 n8n 執行期的 `allowedAddress`
  是同一組，帶帳密、非空的 `?`／`#` 執行期本來就拒，所以今天連得上的位址開通後照樣連得上；真正新擋的是網址的寫法（`.`／`..`
  路徑段、反斜線、空的 `?`／`#`、空帳密的 `@`、非 ASCII 主機…），這些今天經 WHATWG 正規化後照連，開通後要改填正規的寫法。
  寫進契約 #39（審查 S-1）。

### 3.3 執行期：Python 子程式

- `DENY_LOOPBACK` 在 `backend_policy.py` 載入時讀一次。子程式的環境是 `child_spec` 從頭組的（不繼承），launcher 與 vendored
  程式都不改 `os.environ`，所以只有管理程序決定這個值。審查後這一點改由測試看原始碼鎖住
  （`test_no_child_code_names_or_removes_the_variable`，第 4.1 節）。
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

### 4.1 新測試（兩個檔共 211 案是本片的；本機 0 skip）

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

`tests/test_backend_loopback.py`（152 案；審查後加的 3 個測試共 50 案標 ★）：

| 測試 | 案數 | 驗什麼 |
|---|---|---|
| `test_a_switched_on_product_s_child_gets_the_variable_and_nothing_else_changes` | 16 | HM-04 快照的 16 個案例：開通＝快照＋一個 `WOOW_MCP_DENY_LOOPBACK=1`，其他逐位元（含順序）相同；沒開通、替身開關＝快照 |
| ★ `test_an_additional_profile_s_child_gets_the_variable_too` | 48 | 同 16 個案例 × 額外帳號的 port（`test_child_port_param.PORTS`：18000、18042、18099）：開通＝沒開通的 spec 加一個 `WOOW_MCP_DENY_LOOPBACK=1`，argv、cwd 與其他變數（含順序）相同；沒開通、替身開關都沒有這個變數。先算好布林值、刪掉 spec 再斷言（MF-1、S-6） |
| `test_the_rule_is_the_product_switch_alone` | 1 | `loopback_refused` 的本體只有 `return features.enabled(product)`（AST） |
| `test_no_variable_of_the_management_process_turns_the_rule_off` | 1 | 全新程序、只跑正式程式、帶一堆看起來像開關的變數：開通的 Odoo、n8n 存檔照擋、子程式照帶變數 |
| ★ `test_no_child_code_names_or_removes_the_variable` | 1 | 看 `apps/` 的原始碼（`node_modules`、`.venv`、`tests` 除外，91 個檔）：只有兩個政策檔與 `n8n_adapter.py` 提到 `DENY_LOOPBACK`；沒有檔案從自己的環境拿掉變數（`os.environ.pop`／`popitem`／`clear`、`del os.environ[…]`、`os.unsetenv`）、換掉整個環境（`os.environ = …`）、用自己的一份環境起別的程式（`exec*e`、`spawn*e`、`posix_spawn`、帶 `env=` 的 `subprocess`／`asyncio`）；Node 檔不換掉 `process.env`、不 `delete` 裡面的變數（S-3 的 (a)） |
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
| `test_n8n_webhooks_stay_permissive_with_the_variable` | 1 | 開通後 webhook 驗證照 permissive、`createPinnedAgents` 照常；`createPinnedFetch` 擋 7 種 loopback 與 0.0.0.0 的位址（127.0.0.1、127.9.9.9、::1、0.0.0.0、`::`、兩個 IPv4-mapped），放 2 個區網 |
| ★ `test_the_official_mcp_pinned_fetch_refuses_a_mixed_answer` | 1 | 官方 MCP 用戶端的 pinned fetch：`[10.0.0.2, 127.0.0.1]`、`[127.0.0.1, 10.0.0.2]`、`[fd12::1, ::1]` 都整組拒絕，`[10.0.0.2, fd12::1]` 照放（S-2） |
| `test_the_n8n_child_starts_only_without_the_variable_or_with_1` | 11 | n8n 子程式：沒設與 `1` 能啟動，9 種其他值拒絕啟動 |
| `test_only_the_official_mcp_client_makes_a_pinned_fetch` | 1 | 掃 n8n-mcp 的 `dist/`：呼叫 `createPinnedFetch` 的只有官方 MCP 用戶端；它的端點是設定的來源 |
| `test_the_double_is_test_code_no_image_carries`、`test_the_double_is_on_only_inside_its_block`、`test_the_double_in_a_subprocess_preamble` | 3 | 替身開關：沒有執行期檔 import 它、Dockerfile 不複製 `tests/`；只在區塊內有效（例外時也還原）；子程序前置碼裝上才有效 |
| `test_a_switched_on_odoo_refuses_its_loopback_fake_backend_end_to_end` | 2 | 真管理程序（`run_product`，前置碼開通 Odoo）＋真 Odoo 子程式：子程式的 `/proc` 環境有變數（只看這一項；審查後先算好、刪掉環境再斷言）、一直在線的 loopback 假後端收到 0 個請求、用戶端的 tools/call 被拒；前置碼加替身開關時變數不在、同一個呼叫到得了假後端 |

packaging（審查後加，MF-2；unittest，只用 mock，不要 Docker 也不要 root）：

| 測試 | 驗什麼 |
|---|---|
| `test_container_acceptance.py::CandidateInvocationTests::test_every_product_whose_child_refuses_loopback_gets_the_one_use_bridge` | Headscale 與 `MULTI_PROFILE_PRODUCTS` 裡的每個產品：`container_acceptance` 先開 `--internal` 的 bridge、探針容器跑在那個網路、最後刪掉它 |
| `test_container_probe.py::SwitchedOnMockBackendTests::test_every_product_whose_child_refuses_loopback_gets_a_private_mock_address` | 同一組產品：`container_probe.mock_bind_host` 回容器的私有位址（不是 127.0.0.1） |

### 4.2 先紅後綠

| 輪 | 程式 | 測試 | 結果 |
|---|---|---|---|
| 紅 | 四個執行期檔拿掉（`git stash`，在共用鎖裡做，跑完放回並核對 SHA-256） | 兩個檔 192 案（新 161 案＋既有 31 案） | 135 失敗、57 通過、61.8 秒。通過的是既有 31 案與 26 個新的對照案（沒開通照舊、區網照放、替身開關的「照舊」那一半、`dist/` 掃描） |
| 綠（第一輪） | 本片的程式 | 兩個檔＋相關的既有檔共 23 檔 1064 案 | 1061 通過、3 失敗，都是測試本身的錯：Dockerfile 有 9 個（Odoo Manage 也有）不是 8 個；一致性測試解析到 HM-01 禁止的 port 3000（改用 8069，位址規則不看 port）；端到端測試原本期待回覆帶 `BACKEND_DESTINATION_DENIED`，但 Odoo 的 private probe 只回固定的 `BACKEND_UNAVAILABLE`（`apps/odoo/launch.py` `probe_failure`），改成驗子程式環境的變數、假後端 0 個請求、回覆被拒 |
| 綠（第二輪） | 同上 | 兩個檔 192 案 | 192 通過、0 skip、63.5 秒 |
| 紅（第二輪，最後的測試） | 四個執行期檔換回基準 `76c1d78` 的內容（共用鎖裡做，跑完從私有備份放回並核對 SHA-256） | 兩個檔 192 案 | 134 失敗、58 通過、61.4 秒。通過的是既有 31 案與 27 個對照案（上一輪的 26 個，加上修好的 `test_the_double_is_test_code_no_image_carries`：它檢查的是映像與 import，本來就和實作無關） |
| 綠（第三輪，最後的測試） | 本片的程式 | 兩個檔 192 案 | 192 通過、0 skip、65.5 秒 |
| 審查後：新測試對突變 | 直接呼叫新測試（不經 pytest；只組 spec、跑 node、看 `apps/` 的暫存複本；clone 的檔一個都沒改，前後 SHA-256 相同） | MF-1 的 48 案 | 本片的程式 48 過；M17（Python 子程式只有 3000 帶變數）42 失敗（14 個 Python 案例 × 3 個 port）、M17n（n8n 同樣）6 失敗；失敗訊息只有 `None`，不含環境 |
| 同上 | 同上 | S-2 的 1 案 | 本片的程式過；M24（pinned fetch 只看第一個答案）失敗 |
| 同上 | 同上 | S-3 的 1 案 | 本片的程式過；`apps/` 複本上的 M39（`run_child.py` 拿掉變數）、M40（Hermes `launch.py` 用 `from os import environ` 拿掉）、M41（`session_idle.py` 清空環境）、M43（launcher 用另一份環境 exec）、M44（launcher 重設 `backend_policy.DENY_LOOPBACK`）、M45（`del os.environ[…]`）都失敗；M46（帶 `env=` 的 `subprocess.run`）、M47（`os.environ = {}`）也找得到；複本放回後照過 |
| 同上 | CI 式的離線暫存 venv | packaging 的 2 案 | 開關空的：2 案過；暫時開 `odoo`（`container_acceptance.py`、`container_probe.py` 沒改）：2 案失敗；開 `odoo`、`n8n`：4 個 subtest 失敗 |
| 綠（審查修正後） | 本片的程式（`products.py` 只改註解） | 相關 30 檔（第 6.2 節） | 1,379 通過、0 失敗、0 skip、594.6 秒；兩個 HM-20 測試檔 242 案（`test_backend_loopback.py` 152、`test_saved_destinations.py` 90）；審查後加的 50 案合計約 0.7 秒 |

### 4.3 突變

- 作者這邊沒做（共用的 pytest 鎖一直被其他工作流的全套佔著）。
- 獨立審查做了 44 個：38 個被擋，6 個存活（M05 是等價突變；M17、M17n、M24、M39、M40）。審查修正後，5 個非等價的存活突變都被
  新測試擋下（第 4.2 節）；M41 原本只有端到端擋，現在靜態守門也擋。

## 5. 受影響的既有測試

- `tests/test_upgrade_zero_rewrite.py`（HM-07）：`UNWIRED` 拿掉 `features`，docstring 與註解照實改（第 2 節）。
  `test_no_runtime_file_imports_the_unwired_modules` 與 `test_no_entry_point_imports_the_unwired_modules` 照過；
  `test_nothing_binds_the_switch_at_import` 照過（`products.py` 只呼叫 `features.enabled`）。
- `tests/test_output_schemas.py`：`CURRENT_POST_SOURCE_BYTES` 兩筆（第 2 節）。
- `packaging/test_container_acceptance.py`、`packaging/test_container_probe.py`：各加一個測試，既有測試沒改（審查 MF-2）。
- 其餘既有測試一個都沒改，期望值也沒改；沒開通時的行為由下列照過的測試鎖住：HM-01 的
  `test_single_profile_golden.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`，HM-04 的
  `test_child_port_param.py`（快照沒改），`test_saved_destinations.py` 的既有 31 案、`test_six_egress.py`、
  `test_backend_network.py`、`test_backend_policy_python.py`、`test_real_products.py`、`test_real_n8n.py` 等（第 6 節）。

## 6. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除）

全部 pytest 都用 `flock …/wave1-pytest.lock` 排隊（共用鎖；沒動 `conftest.py`、沒刪鎖檔）。

### 6.1 審查前

| 檢查 | 結果 |
|---|---|
| 綠（第一輪）：23 檔（兩個新檔＋`test_upgrade_zero_rewrite`、`test_child_port_param`、HM-01 三檔、`test_backend_network`、`test_backend_policy_python`、`test_six_egress`、`test_headscale_product`、`test_n8n_permissive_webhooks`、`test_child_bearer`、`test_nextcloud_child`、`test_boundary`、`test_output_schemas`、`test_tool_inventory`、`test_hermes_mcp_url_guard`、`test_ledger_precheck`、`test_resolver_regressions`、`test_raw_backend_errors`、`test_real_products`、`test_real_n8n`） | 1064 案：1061 通過、3 個測試本身的錯（第 4.2 節），568.6 秒 |
| 綠（第二輪）：兩個新檔 | 192 通過、0 skip、63.5 秒 |
| 全套 pytest（commit 後的程式：當時的 HEAD `a199d33`，和 `8fc07ab`＋`e55af02` 只差 `test_saved_destinations.py` 的 7 行 log 掃描標記；那兩個檔在紅、綠第二、三輪已用最後的版本重跑） | 5342 案、0 skip、30 分 57 秒：5313 通過、29 失敗。7 個要 root：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`（基準就要 root，CI 以 root 跑）。22 個瀏覽器測試（`test_owned_browser_ipc.py` 5、`test_owned_browser_redirect.py` 16、`test_owned_ui.py` 1）：這個 clone 當時沒裝 Playwright 的 Chromium（`Executable doesn't exist …/.local-browsers/chromium_headless_shell-1228`）。照 CI 用 `npm run browser:install --prefix packages/mcp-admin-ui` 補裝後重跑這 3 個檔再加 `test_owned_browser.py`、`test_admin_ui.py`：66 通過、0 失敗、39.2 秒 |
| `scripts/tool_inventory.py --write` 後再跑一次檢查模式 | exit 0；`docs/tool-surface.md` 0 差異 |
| packaging unittest（同 CI：暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt`，`discover -s packaging`；沒動 clone 的 `.venv`） | `Ran 201`、`OK (skipped=5)`（5 個 `skipUnless(root)`，和基準相同） |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| `node --check apps/n8n/backend_policy.cjs` | 通過 |

### 6.2 審查修正後

| 檢查 | 結果 |
|---|---|
| 相關 30 檔（審查跑的 29 檔：上面 23 檔＋`test_connection_patch`、`test_n8n_mcp_access_token`、`test_odoo_shared_transport`、`test_odoo_xmlrpc_recovery`、`test_profile_runtime`、`test_unconfigured_connect`；再加讀帳本的 `test_redaction_matrix`） | 1,379 通過、0 失敗、0 skip、594.6 秒（共用鎖排了 24 分鐘）。其中 HM-01 黃金回歸 17 案、MCP 與管理契約凍結 9＋19 案、HM-04 快照 233 案、`test_upgrade_zero_rewrite` 37 案、兩個 HM-20 測試檔 152＋90 案、`test_redaction_matrix` 107 案 |
| 新測試對突變的直接驗證、packaging 守門的開關驗證 | 第 4.2 節 |
| packaging unittest（同上的離線暫存 venv） | `Ran 203`、`OK (skipped=5)`（多的 2 案是 MF-2 的測試） |
| `packaging/validate.py`（ci-venv 的 Python） | PASS |
| `scripts/tool_inventory.py`（檢查模式） | exit 0；9 個產品的工具數不變 |
| `node --check apps/n8n/backend_policy.cjs` | 通過（審查後沒改） |
| 全套 pytest | 沒重跑：審查後只改測試、註解與文件。rebase 到 HM-08、HM-09 之後一定要跑（第 13 節） |

## 7. 只在 CI 跑的測試

- 本片的新測試都不需要 root，本機（一般使用者）全跑過；CI 以 root 跑，結果應該相同（測試不靠執行身分判斷）。
- 端到端測試讀子程式的 `/proc/<pid>/environ`：一般使用者讀得到自己的子程式；CI 的 root 也讀得到。
- `_whatwg_hosts` 與 n8n 的測試用 `node`：本機是 v26.12.1；CI 把 `/usr/bin/node`、`/usr/local/bin/node` 都釘成 v26.12.1。
- packaging 的兩個新測試在 CI 的 packaging unittest（一般使用者、離線 venv）跑；本機用同樣做法跑過。
- 全套 pytest：審查前本機 5313 通過，失敗的 29 個都和本片無關（第 6 節）；7 個要 root 的案例只在 CI 驗。以 CI（root、0 skip）為準。
- Playwright 與面板測試：本片沒改面板，結果以 CI 為準。

## 8. `checks` 秒數

開 PR 後補（前：基準 `76c1d78` 的 run；後：本片 PR 的 run）。推估：本片兩個測試檔本機約 64 秒（其中 32 個子程式案約 41 秒、
端到端兩案約 7 秒）；審查後加的 50 案只組 spec、跑一次 node、看原始碼，本機合計約 0.7 秒。CI 推估多 50～80 秒。

## 9. 預檢結果

- **秘密預檢**（`.venv/bin/python -I scripts/secret_precheck.py --tools …/hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full`；
  gitleaks 8.28.0，釘版並核對過；設定是 `packaging/supply_chain.py gitleaks_config()`）：
  - 審查前：程式與文件的 2 個 commit（`8fc07ab`、`e55af02`）`result: OK, 0 findings`；`--full` 的 HEAD 全部檔與全歷史也 0。
    （重建 commit 前的 `29041e4`、`a199d33` 與 `d042816`、`597de6b` 也各跑過一次，同樣 0；內容只差 7 行 log 掃描標記與 commit 訊息。）
    加上本筆記的 commit（`af581d1`，3 個 commit）也是 0（審查重跑一致）。
  - 審查修正後：`76c1d78..87e377c`（前面 3 個＋審查後的程式與文件 2 個：`7df884b`、`87e377c`）共 5 個 commit：
    `result: OK, 0 findings`；`--full` 的 HEAD 全部檔與全歷史也 0。加上本筆記的 commit（最終 HEAD）在 commit 之後重跑，結果寫在
    交回報告與 PR 說明。
  - 新的 64 hex 只有帳本摘要與 `tests/test_output_schemas.py` 的兩筆目前位元組（同 HM-04 的寫法），都沒有命中。
- **帳本預檢**（`.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery`）：
  - 審查前：`runtime-patches.json` 171 個、`runtime-sources.json` 70 個、`tool-surface.json` 159 個，0 漂移、0 缺檔；改到的列管檔
    4 個，兩本帳本都改了；新增或改到而沒列管的執行期檔 0 個（`tests/loopback_backends.py` 在 `tests/`，不是執行期檔）。`result: OK`。
  - 審查修正後（`87e377c`）：同樣 171、70、159 個，0 漂移、0 缺檔；這個分支改到的 18 個檔裡有 4 個列管檔，兩本帳本
    （`runtime-patches.json`、`tool-surface.json`）都改了；新增或改到而沒列管的執行期檔 0 個。`result: OK`。

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
- 審查修正時重查一次（同一組路徑，每條路徑都確認在 `origin/main` 上存在）：本機 `origin/main` 還是 `5b84b5d`，結果和上面相同。
  PaaS 的 `util/ssrf.py` 不看網址路徑（S-1 寫的「PaaS 不看路徑寫法」）。

## 11. 本片用到的決策

- DQ-10（後端網址拒絕 loopback）：loopback 部分依 DQ-40 (a)（2026-11-14 13:4x），照計畫 §8.7。子題（n8n
  `WEBHOOK_SECURITY_MODE=permissive`）2026-11-15 15:3x 使用者定：**維持不動**（負責人 2026-10-15 的決定）；HM-20 只管設定的後端
  網址；多帳號時要不要收緊 webhook，留到 HM-25（n8n 開通）前的獨立安全審查。`decisions.md` 已記。
- DQ-40 ⑦：後端網址拒絕 loopback 是 HA 加嚴、列入給 PaaS 的回補建議（HM-29）。
- DQ-32：開關＝發版；本片不加任何產品。DQ-28：OpenDesign、Odoo Manage 不開放（規則對它們一樣成立，只是永遠不會開通）。
- DQ-37：同 uid 信任邊界（第 3.5 節最後一點）。DQ-36：commit 不加 AI 署名。DQ-33：本機 TMPDIR 規則。
- UC-10 的做法（2026-11-15 15:3x 使用者定：HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭，探針實測不通再補網址路徑備案）：本片沒用到，
  照任務只記在 `decisions.md` 的 DQ-17。
- 審查後沒有用到新的決策。S-4 的範圍照 DQ-10（127.0.0.0/8、::1、`localhost`）；要不要連 add-on 自己的 bridge 位址一起擋是新的決定，
  不在本片（第 14 節）。
- 實作時做的選擇（不是 §13 的題目；審查認為都在 DQ-10、§8.7 的範圍內，不用另問使用者）：
  1. 存檔的拒絕不另開錯誤代碼，用既有的 400 `{"error":"request denied"}`（第 3.1 節）。
  2. 名稱名單照 PaaS strict（`localhost`、`localhost.localdomain`、`*.localhost`）；`ip6-localhost` 這類 `/etc/hosts` 別名不列，
     交給執行期解析後擋。
  3. 開通時，數字寫法落在不允許位址也在存檔時擋（例如 `0`＝0.0.0.0），不只 loopback。
  4. 開通時 n8n 走整套既有存檔檢查，不只 loopback（審查後照 S-1 寫進契約 #39）。
  5. 存檔不解析 DNS（第 3.2 節）。
  6. n8n 的官方 MCP 端點算「設定的後端」，一起擋；n8n 這邊另擋 0.0.0.0（webhook 驗證在 permissive 下會放行它）。
  7. 變數的值只收 `1`，其他值拒絕啟動（和 HM-06 的 bearer 一樣 fail closed）。

## 12. 驗收條件（計畫 §12.3 HM-20、§12.0）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 PR 的 CI（這一階段不 push、不開 PR）。本機：第 6 節 |
| 開關關時 HM-01 逐位元 | 通過：HM-01 的黃金回歸與兩個契約凍結照過、期望值沒改；子程式 spec 等於 HM-04 快照（16 案）；存檔照舊（既有 31 案＋新的「沒開通照舊」案） |
| 開關開時存檔拒 loopback | 通過：全部 9 個產品（含 n8n）、兩條存檔路徑、33 種寫法；400＋既有本體；區網照放 |
| 開關開時執行期拒 loopback（含 DNS 指到 127.0.0.1） | 通過：8 個 Python 產品各用自己的子程式環境與客戶端（字面、DNS、混合答案）；三種傳輸對真的假後端 0 個請求；n8n 的 API 與官方 MCP 用戶端（含混合答案）；真管理程序＋真 Odoo 子程式端到端；額外帳號的子程式也帶變數（48 案） |
| 每個產品至少一個案例 | 通過：存檔 9 個產品、執行期 9 個產品（含 n8n） |
| 替身開關只在測試裡打開、正式路徑不能被環境變數以外的方式關掉 | 通過：第 3.5 節；`test_the_double_*` 三案、`test_the_rule_is_the_product_switch_alone`、`test_no_variable_of_the_management_process_turns_the_rule_off`、`test_no_child_code_names_or_removes_the_variable`、變數的值只收 `1`。映像裡用不了替身：packaging 的兩個測試逼開通的產品照 Headscale 做（第 13 節） |
| n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 不動 | 通過：快照照舊；`test_n8n_webhooks_stay_permissive_with_the_variable` |
| 先寫測試、記下先紅後綠 | 通過（第 4.2 節） |
| 新測試用 HM-01 的 log 掃描、不得條件式 skip | 通過：新測試都在 `log_scan` 下（`test_backend_loopback.py` 整個檔用 `pytestmark`；`test_saved_destinations.py` 的新測試逐一標記，既有 31 案不動；API 案另外監看 state 的 token 與憑證）；0 skip。packaging 的兩個測試是 unittest，不用 log 掃描（同檔既有測試的寫法） |
| 測試資料規則（§12.0 第 4 點） | 通過：網址用 `.invalid`、憑證 `DUMMY-…`、token `T`×43／`C`×43；packaging 測試只有 mock 的 ID 與私有位址 `172.18.0.2`；沒有 commit 隨機 token；秘密預檢 0 命中。測試失敗時不印子程式環境與 state（審查 S-6） |
| 同 PR 更新帳本、tool-surface | 通過：第 2、9 節 |
| 不改版號、不碰 `addons/<x>/`、不改 CHANGELOG；`MULTI_PROFILE_PRODUCTS` 維持空的 | 通過 |
| 比 PaaS 嚴的部分對到契約第 9 節 | 通過：#39 改寫（範圍、執行期、數字寫法、回應本體、區網、存檔不查 DNS、n8n 開通後的整套存檔檢查與和 PaaS n8n 的差異）；n8n webhook 模式補 #87 |
| 獨立安全審查 | 通過：修正後通過（2026-11-15；報告 `artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-20.md`）；必修 2 項都處理了（第 14 節）。PR 要附報告路徑 |

## 13. 還沒解決、交給後面的片

- **rebase（HM-08、HM-09 合併後；主對話做）**：
  - `tests/test_upgrade_zero_rewrite.py` 的 `UNWIRED`：HM-08 也會接線 `features`，同一行可能衝突；兩片都拿掉 `features` 就好。
  - 帳本：`products.py`、`features.py` 的說明與摘要，照衝突規則以 `claude-delivery` 為底重產、重算 SHA-256；`tool-surface` 也重產。
  - `products.py`：計畫的檔案順序是 HM-04 → HM-06 → HM-07 → HM-20 → HM-12；HM-09 若改 `child_spec`（帳號 port、資源），變數的位置
    照本片（`WOOW_MCP_CHILD_TOKEN` 後面）。額外帳號的子程式也用 `child_spec`，所以開通後同樣帶變數。
  - `test_an_additional_profile_s_child_gets_the_variable_too`（MF-1）就是為了擋這次解衝突時的遺漏：HM-09 若讓 `child_spec` 多了帳號
    專屬的參數，照新簽名改這個測試，不要拿掉。
  - HM-09 的 `EXEC_WRAPPER`（HM-09 審查報告：`Hc/lifecycle.py` 裡，fork 之後、exec 之前跑，會碰額外帳號子程式的環境；本片沒讀
    HM-09 的分支）：確認它把 `WOOW_MCP_DENY_LOOPBACK` 原樣傳下去。最好補一個起真的額外帳號子程式、只看 `/proc/<pid>/environ` 裡
    這一個變數（不印）的測試；本片的靜態守門只看 `apps/`，看不到 `lifecycle.py`。
  - HM-08、HM-09 的測試若在開關開時用 loopback 假後端起真的子程式，rebase 後子程式會帶變數、拒連那個假後端：那些測試改用
    `loopback_backends.allowed()` 或 `install()`（審查 S-5）。
  - 新增到 `apps/` 的檔若會換環境或用自己的一份環境起程式，`test_no_child_code_names_or_removes_the_variable` 會紅：確認變數照傳後，
    在測試裡寫明理由再放行。
  - rebase 後跑**全套** pytest（不只兩個新檔、HM-01 守門與 `test_child_port_param.py`），再跑兩個預檢與 packaging unittest。
- **HM-16、HM-19a、HM-21～HM-26（產品開通與容器驗收；審查 MF-2）**：產品一開通，`packaging/container_probe.py` 的假後端
  （`mock_bind_host` 今天除了 Headscale 都回 127.0.0.1）會被子程式拒連，`/health/ready` 一直不是 200，builder 的容器驗收與供應鏈閘門
  （`packaging/supply_chain.py` → `container_acceptance`）會失敗。替身開關在 `tests/`，映像裡沒有，救不了。要照 Headscale 現成的做法：
  開通的產品，`container_acceptance` 給一次性的 internal bridge（`--internal`，用完刪掉），`container_probe.mock_bind_host` 回容器的
  私有位址。本片加的兩個 packaging 測試會在產品加進 `MULTI_PROFILE_PRODUCTS`、這兩處還沒改時就讓 CI 紅，不用等到 builder。
  計畫 §11.3 的 HM-19a 逐檔清單與 §12.3 的 HM-16 要補這兩個檔。HM-19a 前的拋棄式 flag-on 乾跑（要使用者授權 builder）也會撞到。
- **HM-19a（Odoo 0.5.0 把 `odoo` 加進 `MULTI_PROFILE_PRODUCTS`）**：
  - 開通後 Odoo 存檔與子程式都拒 loopback，所以用 loopback 假後端的既有 Odoo 測試（例如 HM-01 黃金回歸、`tests/test_real_products.py`
    的 Odoo 案、各個 `test_odoo_*` 執行期測試）會失敗：要在 fixture 裡用 `loopback_backends.allowed()`，或在子程序前置碼呼叫
    `loopback_backends.install()`。本片沒動那些測試。
  - 發版文件（CHANGELOG、DOCS、`upgrade-notes.yaml`）寫計畫 §7.2 第 9 點，可以直接用這句：「後端網址不能填 loopback
    （127.0.0.0/8、::1、`localhost`）。開通前存的 loopback 網址開通後照樣讀得出來，但連不上；Odoo 的健康檢查只顯示
    `BACKEND_UNAVAILABLE`。」
- **HM-24（Hermes 開通）**：`apps/hermes/vendor/hermes_mcp_server/guards.py:167-169` 的註解說 `backend_policy` 放行 loopback，
  現在只在沒開通時成立，開通時順手改（審查 S-8；vendored 檔，改了要更新帳本）。
- **HM-25（n8n 開通）**：開工前的獨立安全審查要評估「多帳號時 n8n webhook 要不要收緊」（DQ-10 子題的待辦，`decisions.md` 第 4 節，
  審查要看的事實已記：webhook 網址＝設定的 n8n 來源＋路徑、路徑與標頭由呼叫者決定、同一來源 API 擋 webhook 不擋、API key 不跟著送）。
  `run.py` 收斂到 ProfileRuntime 時，`n8n_adapter.child_spec` 的變數要留著。n8n-mcp 升版時
  `test_only_the_official_mcp_client_makes_a_pinned_fetch` 會擋下「多了 `createPinnedFetch` 的呼叫點」。
- **HM-18（文件）**：`threat-model.md` 第 3 節的已知限制（add-on 自己的主機名與 bridge 位址不在規則裡）寫進產品 DOCS。
- **使用面**：開通前存的 loopback 網址開通後照樣讀得出來，但子程式連不上；Odoo 的健康檢查只回 `BACKEND_UNAVAILABLE`（不說是被
  loopback 規則擋），用戶端看到「Backend unreachable」。HA 的 bridge 網路下 loopback 本來就連不到真的後端，所以正常安裝不會有這種
  網址；要不要在面板或健康原因寫明是 loopback 規則，留給 HM-18（文件）或主對話決定。
- **PaaS 回補（HM-29）**：PaaS 的 Nextcloud 從 #152 起存檔過 SSRF，但子程式連線時沒有第二道（PaaS 自己寫明）；HA 的執行期檢查
  （連線前驗每個答案）可列入回補建議（DQ-40 ⑦）。
- `checks` 秒數：開 PR 後補。

## 14. 安全審查意見處理

審查報告：`artifacts/ha-multiprofile-parity-20261114/wave3/review-HM-20.md`（repo 外）。每一項都先核對過再改（審查也可能錯）。

| # | 意見 | 核對 | 處理 |
|---|---|---|---|
| MF-1 | 額外帳號（18000 起）的子程式有沒有拿到變數，沒有測試看（M17、M17n 存活） | 成立：既有測試都用 3000；用替身重現 M17、M17n，新測試前一樣全過 | **已修**：加 `test_an_additional_profile_s_child_gets_the_variable_too`（16 案例 × 3 個 port＝48 案），開通時剛好多一個變數、其他逐項相同，沒開通與替身開關都沒有；連替身開關、cwd 也比。M17 下 42 案、M17n 下 6 案失敗，訊息只有 `None`。第 13 節寫明 rebase 時照新簽名改、不要拿掉 |
| MF-2 | 交接漏寫：產品開通後容器驗收的 loopback 假後端會被拒，替身進不了映像 | 成立：`container_probe.mock_bind_host` 除了 Headscale 都回 127.0.0.1，探針等 `/health/ready` 200；`tests/` 不在映像裡 | **已修**：第 13 節補 HM-16、HM-19a、HM-21～HM-26 的交接；也做了可選的守門：兩個 packaging 測試（開關空的照過；暫時開 `odoo` 就紅） |
| S-1 | 契約沒寫 n8n 開通後套上整套既有存檔檢查 | 成立：`check_saved_destinations` 對 n8n 跑 `saved_destination(…, loopback=True)`；n8n 執行期的 `backend()` 本來就拒帶帳密與非空的 `?`／`#`；PaaS 的 `util/ssrf.py` 不看路徑 | **採用**：契約 #39 的 HA 欄補整套檢查、新擋的只有網址寫法、和 PaaS n8n 的差異；第 3.1 節同步 |
| S-2 | 官方 MCP 的 pinned fetch 沒有混合答案的測試（M24 存活） | 成立 | **採用**：加 `test_the_official_mcp_pinned_fetch_refuses_a_mixed_answer`；M24 下失敗 |
| S-3 | 真的子程式入口只驗了 Odoo（M39、M40 存活） | 成立：其他產品的子程式測試直接 import 客戶端 | **採用 (a)**：加 `test_no_child_code_names_or_removes_the_variable`，比建議的範圍大（也看用自己的一份環境起程式、換掉整個環境、`del os.environ[…]`、重設 `DENY_LOOPBACK`、Node 的 `process.env`）。M39～M41、M43～M47 都找得到。(b) 的端到端擴充沒做：每個產品多起一個真子程式，成本高，(a) 已擋下存活的突變 |
| S-4 | 用詞比範圍大：add-on 自己的主機名、bridge 位址不在規則裡 | 成立：規則只看 loopback；子程式只聽 127.0.0.1，8099 只收 `172.30.32.2`，8081 要 token | **採用**：`products.py` 的註解與 docstring、`test_saved_destinations.py` 的註解、契約 #39 與第 3.1 節、本筆記改說「loopback」；`threat-model.md` 第 3 節加一行已知限制。`backend_policy.cjs` 的註解沒改：它已逐一列出擋的位址（127.0.0.0/8、::1、0.0.0.0），改它要再換三本帳本與 `test_output_schemas.py` 的位元組。要不要連 bridge 位址一起擋是新的決定，不在本片 |
| S-5 | rebase 與後續片的提醒 | 成立（HM-08、HM-09 的分支沒有讀，只寫成檢查項） | **採用**：寫進第 13 節的 rebase 清單（用替身改寫那些測試、rebase 後跑全套）與 HM-19a 的發版文件句子；PR 說明的「開 PR 前要做」也列了 |
| S-6 | 測試失敗時會把子程式環境（含測試 token）印出來 | 成立：端到端測試先斷言、才刪環境 | **採用**：端到端、`test_the_child_refuses_a_loopback_backend_when_it_connects`、兩個 n8n 測試改成先取出要比的值、刪掉 spec 或環境再斷言；`test_saved_destinations.py` 的 API 案先比 state 的位元組再斷言；新測試照同樣寫法 |
| S-7 | 給 HM-25 前安全審查的事實 | 成立：`base-handler.js` 的 `getBaseUrl`、`webhook-handler.js` 用呼叫者給的路徑與標頭，`triggerWebhook` 用 `createPinnedAgents` | **採用**：`decisions.md` 第 4 節 DQ-10 補三點事實，另補「n8n 的 API key 不會跟著送（`X-N8N-API-KEY` 設成 undefined）」 |
| S-8 | 契約第 7 節的代碼漏 Headscale；Hermes `guards.py` 的註解過時 | 成立 | **契約已修**：第 7 節補 Headscale 回 `HEADSCALE_DESTINATION_DENIED`、不看變數一律拒。`guards.py` 照審查建議交 HM-24（vendored 檔，第 13 節） |

- 突變：審查的 44 個裡 5 個非等價的存活突變（M17、M17n、M24、M39、M40）現在都被擋下；M05 是等價突變，不用補。
- 審查後的程式改動只有 `products.py` 的註解；Python 與 n8n 的政策檔、`n8n_adapter.py` 都沒再改。
