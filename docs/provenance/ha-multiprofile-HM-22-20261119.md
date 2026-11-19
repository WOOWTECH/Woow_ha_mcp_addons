# HA 多帳號 HM-22 provenance：Nextcloud 開通的功能片（換 url／username 換 token、存政策只重啟該帳號、探測退避）（2026-11-19）

## 結論

- **本片是 Nextcloud 的功能 PR，不開通**。`MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空集合，`addons/` 一個檔都沒動；測試裡用 monkeypatch
  開（`tests/multi_profile_runtime.py` 的做法）。之後的升版 PR 只要把 `nextcloud` 加進開關、重算帳本那一列、照計畫 §11.3 升版號，再改
  `unreleased-changes.md` 第 3.6 節列的說明與一個釘選（第 9.4 節）。
- **開通的 Nextcloud，token 綁它的帳號**（DQ-40 ⑩ (a)；對齊 PaaS #154 `0f94aa4`；契約第 3.1 節、§8.8 #40、#129）：`products.IDENTITY_BOUND`
  加 `nextcloud`。存檔（`backend`、`backend/patch`）讓 url 或 username 改了，就照 HM-12 的順序換 token：先停舊子程式、一次寫入新連線＋
  新 token＋一筆 `rotate` 歷史、發布、在新帳號上起子程式。舊 token 兩條入口都拒（Bearer 401、密鑰網址 404）。只換 app password、
  初次設定、token 已撤銷不換；清空連線會換。HM-12 的換身分流程本來就不分產品，本片沒有改 `gateway.py`。
- **網址照它指的伺服器比**（`products.same_identity`、`identity_fields.SAME_SERVER_URLS`；§8.8 #129）：scheme、host 不分大小寫，寫不寫
  預設 port 都一樣，再比存的路徑（結尾斜線本來就去掉，大小寫算）。只差這些寫法不換 token，對齊 PaaS 的 `normalize_base_url`。路徑不同就換，
  包括大小寫不同與貼上的頁面路徑：HA 存檔不切路徑，存的網址就是子程式的根網址（PaaS 會切掉，這是差異）。username 逐字比（同 PaaS）。
  Odoo 照舊逐字比（同 PaaS #131）。
- **存政策只重啟該帳號**（T-07；FM-47）：HM-10 起就是每帳號自己的 `backend_changed`，本片補 Nextcloud 的測試（程序內三個帳號；兩個真子程式
  的 PID）。HA 每次存政策都重啟該帳號的子程式，沒變也重啟（PaaS 只在放寬時重啟；§8.8 #54、#130）。
- **探測退避**：`health.py` 不用改。HM-09 已經把 Nextcloud 的 401 與 429 文字算成「認證被拒」，退避 15→30→60→120→300 秒；Nextcloud 子程式
  自己的 auth latch 讓同一組錯誤帳密在子程式重起前只登入失敗一次。本片用兩個真的 Nextcloud 子程式驗：錯密碼的帳號只退避自己，檢查再多次
  後端也只看到一次失敗登入，另一個帳號照常；存對的密碼後退避歸零、恢復可連。**Nextcloud 的節流單位沒有實測（UC-12）**，留給 HAOS 驗收（第 12 節）。
- **PaaS #152（存檔過 SSRF）**：HM-20 已對齊（§8.8 #39）。本片補 Nextcloud 兩條存檔路由的測試：開通後 loopback、link-local、metadata 主機、
  前後空白都 400，什麼都不寫、子程式不停、token 不換。
- **bearer 401／密鑰網址 404 矩陣**：開通時三個帳號（輪替、撤銷、隨機 token；密鑰網址不看 `Authorization`；8081 不看 `X-MCP-Profile`），
  沒開通時帳號資料休眠、只有預設帳號的 token 能用；兩個真的 Nextcloud 子程式的子程式 bearer 矩陣（互拿對方的 child token 也是 401）。
- **面板**：`contracts.js` 的 `identityBound` 加 `nextcloud`（HM-12 面板的同步測試要求；開通時 503 state unavailable 與待核對的提示跟 Odoo 一樣）。
- **測試**：新檔 `tests/test_nextcloud_multi_profile.py` 39 案，改既有 3 檔（兩個 pytest 檔、一個面板 node 測試；另外兩個 Nextcloud 測試檔
  與它們的測試工具檔只加開關模式，見下一點）。先紅後綠：在基準的程式上 89 案 24 案失敗（新檔 39 案失敗 23 案）、node 2 案失敗，本片的
  程式全過（第 6.1 節）；臨時突變 7 個全部擋下（第 6.2 節）。
- **Nextcloud 的測試自己指定開關模式**：`tests/nextcloud_fixtures.py` 加 `switched_off` fixture；`test_nextcloud_child.py`、
  `test_nextcloud_error_secrets.py` 整個模組、本片開關關的三案各自指定。開關關時測的東西不變；開通時不再讀倉庫的開關（第 9.2 節）。
- **HM-01 黃金回歸與契約凍結逐位元照過**，期望值一個都沒改（第 7 節）。
- **開通乾跑**（把 `nextcloud` 暫時加進開關、不 commit；第 9 節）：加開關模式之前 80 案失敗：60 案是 Nextcloud 自己的測試讀倉庫的開關
  （本片已改）；17 案是共用測試讀倉庫的開關（HM-23 的 `e803d58` 不分產品地改了，還沒合併）；2 案是升版 PR 本來就要改的釘選與帳本；1 案是
  本機不是 root 的既有案例。本片改完、再暫時套上 HM-23 那個 commit 開著跑：703 案只剩升版 PR 要做的 2 案（版號、帳本）。
- **契約第 9 節的列號是暫定**：本片用 #129～#131（基準 `c90b214` 的最後一列是 #128）。HM-21、HM-23～HM-26 同時在準備，後合併的一方接在當時的
  最後一列後面重編（同 HM-27 的做法）。
- **兩個預檢**：秘密預檢 0 命中、帳本預檢 OK（第 14 節）。

## 1. 範圍與基準

- 基準：`claude-delivery` `c90b214`（PR #109 HM-16 合併）。分支 `feat/ha-multiprofile-hm22-nextcloud-20261119`，一般 clone
  `/data/pi-agent/home/woow-sec-sweep/.worktrees/ha-mp-hm22-20261119`；沒有 push（獨立審查之後由收尾步驟 push）。
- 範圍：計畫 §9 Nextcloud 列、§12.3「HM-21～HM-26｜各產品開通」的 HM-22 與 2026-11-17 的註（identityBound 同步）、§8.8 刻意差異表、
  契約第 9 節、`docs/operations/acceptance.md` 的 T-01～T-29。
- 對齊的 PaaS：pin `69ac425`（DQ-06）之後的 #152、#154，經 GitHub 鏡像 `WOOWTECH/woow-mcp-server` 唯讀讀取（第 4 節）。
- 不在範圍：升版（`addons/`、版號、CHANGELOG、`MULTI_PROFILE_PRODUCTS`）；HAOS 實機（第 12 節）；Hermes（HM-24）。

## 2. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hc/products.py`（列管） | `IDENTITY_BOUND` 加 `nextcloud`；新 `same_identity(product, name, before, after)`；`identity_rebound` 用它比每個身分欄位。只有開通、綁身分的存檔會走到（`backend_edit.origin` 在函式內 import） |
| `Hc/identity_fields.py`（列管） | `SAME_SERVER_URLS = {'nextcloud': ('url',)}`；註解寫明 Nextcloud 已接上 |
| `Hui/contracts.js`（列管） | `identityBound` 加 `nextcloud` |
| `docs/provenance/runtime-patches.json` | 上面 3 個檔照實際內容重算 `sha256`，`change` 各補一段 HM-22（照 JSON 結構逐列改，沒有用 `--write`） |
| `tests/test_nextcloud_multi_profile.py`（新） | 第 5 節逐案對照；39 案。開關關的三案指定 `switched_off` |
| `tests/test_odoo_identity_rotation.py` | `Journal` 也讀 `NEXTCLOUD_MCP_USERNAME`（`spec_username`）；「其他產品開通後不換 token」拿掉 Nextcloud；說明兩處 |
| `tests/test_identity_fields.py` | 加 `test_the_urls_compared_as_servers`（照伺服器比的網址只放綁身分產品的網址欄位） |
| `tests/nextcloud_fixtures.py` | 加 `switched_off` fixture：測試期間所有產品都沒開通，不管倉庫開了什麼（第 9.2 節） |
| `tests/test_nextcloud_child.py`、`tests/test_nextcloud_error_secrets.py` | 整個模組指定 `switched_off`（`pytestmark`）；案例沒改 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs` | `identityBound` 的斷言加 `nextcloud`；S-7 那案加 Nextcloud 開通與沒開通各一行 |
| `docs/multi-profile/contract.md` | 第 3.1 節 `backend` 列；第 9 節說明段一行、#40 的 PaaS 欄（#154）與 HA 欄、新列 #129～#131；第 10 節一列 |
| `docs/multi-profile/threat-model.md` | 狀態一行；第 1 節後端節流那列；I11 的不變式與測試欄；第 3 節加 Nextcloud 節流單位一條 |
| `docs/multi-profile/acceptance-matrix.md` | 狀態一行；T-03、T-04、T-05、T-07、T-23 的 Nextcloud 部分；登記表 `test_nextcloud_multi_profile.py` 由「暫定名」改「新增」，`test_identity_fields.py`、`test_odoo_identity_rotation.py` 各補一句 |
| `docs/multi-profile/decisions.md` | DQ-05 列補記 HM-22 的實作細分（網址的比法）；變更紀錄一列。不是新題目 |
| `docs/multi-profile/ledger-tracking.md` | 狀態一句；`identity_fields.py` 一列的「之後會改的片」加 HM-22 |
| `docs/multi-profile/unreleased-changes.md` | 第 3.6 節：開通 Nextcloud 的升版 PR 要寫的 CHANGELOG 句子（一項一行）與同一個 PR 另外要改的檔；第 4.2 節加 HM-22 一列 |
| `docs/operations/acceptance.md` | 新節「Nextcloud 開通的 HAOS 驗收（HM-22 交來）」 |
| 本筆記 | 新增 |

沒改：`addons/`、版號、CHANGELOG、`MULTI_PROFILE_PRODUCTS`；`gateway.py`、`health.py`、`profile_runtime.py`、`backend_edit.py`（HM-12、HM-09 的
程式不分產品，照用）；`apps/`（沒有動 `apps/runtime/*.py` 或 `apps/*/launch.py`，tool-surface 不用重產）；`tests/conftest.py`；repo 外產生器
輸出的 `deviation-trace.md`、`paas-test-mapping.md`（第 15 節）。

## 3. 設計重點

### 3.1 換身分換 token（沿用 HM-12）

- 條件照 `products.identity_rebound`：開通（呼叫時讀 `features.enabled`）、token 有效、已存的連線完整，這次存檔讓 url 或 username 指到另一個
  身分（含 `{"connection":null}` 清空）。Nextcloud 的連線三欄都必填，所以「完整」就是「存過」；PaaS 的 seed 只有網址、只有帳號那幾種部分狀態
  在 HA 不會出現。
- 換的流程、失敗處理、回應形狀、面板提示都是 HM-12 的（`gateway.rebind_identity`、`ProductStore.rebind`、`ProfileRuntime.stop_child`；
  §8.8 #113～#117），不分產品，本片沒改。失敗的故障注入在 HM-12 的測試，本片不重複。
- 歷史動作照 HM-12 記 `rotate`（PaaS 記 `backend_identity_change`；§8.8 #59）。
- 還原後待核對（HM-13c 審查 S-3）：會換 token 的存檔一樣回 409 `restore_review_required`，因為關卡掛在 `identity_rebound` 上，Nextcloud
  加進來就一起生效。

### 3.2 網址怎麼比（對照 PaaS #154 `normalize_base_url`）

| 寫法 | PaaS #154 | HA（本片） |
|---|---|---|
| scheme、host 大小寫不同 | 同一個（存檔小寫） | 同一個（`backend_edit.origin`）；存新寫法 |
| 寫出預設 port（`:443`、`:80`） | 同一個（存檔去掉） | 同一個；存新寫法 |
| 結尾斜線 | 同一個（存檔去掉） | 同一個（`http_url` 本來就去掉） |
| 前後空白 | 去掉後同一個 | 400（`http_url` 本來就拒絕；什麼都不寫） |
| 貼上的頁面路徑（`/index.php/…`、`/remote.php/…` 等） | 切掉後同一個 | 另一個網址，換 token（HA 不切；子程式用的就是存的那條） |
| 路徑大小寫不同 | 換（寧可多換一次） | 換 |
| 另一個 host、scheme、port、路徑 | 換 | 換（換 host、scheme、port 時 `backend/patch` 還要重填 app password：DQ-40 ⑨） |
| username 不同（含只差大小寫） | 換 | 換 |
| 存檔值只差寫法 | 沿用存檔的寫法 | 照新寫法存（下一次存回舊寫法也不換） |

- 為什麼只放 Nextcloud：PaaS 的 Odoo 走核心的逐字比對（#131），HA 的 Odoo 照它；Nextcloud 在 PaaS 先正規化再比。兩個產品各自對齊 PaaS。
  Odoo、Hermes 要不要也照伺服器比，是另一個決定（第 15 節）。
- 判斷寫在 `identity_fields.SAME_SERVER_URLS`（資料）與 `products.same_identity`（比法），測試同時釘住兩者（`test_identity_fields.py` 要求
  這張表只放綁身分產品的網址欄位）。

### 3.3 存政策只重啟該帳號

- `gateway.admin_action` 的 `policy` 對 EMQX、LiteLLM、Nextcloud、Headscale 呼叫該帳號自己的 `backend_changed`（HM-05 起每帳號一份，HM-10 經
  8099 分派器選帳號）。本片的測試：B 存政策只有 B 的 `starts` 加一、子程式環境的 `NEXTCLOUD_MCP_DISABLED_TOOLS` 換成 B 的政策；預設帳號與 C
  的 state、環境、`starts` 與已開的 session 都不變；預設帳號存政策時反過來。兩個真子程式那案：B 存政策後 B 的 PID 換了、預設帳號的沒換，
  預設帳號的 session 照用，B 的舊 session 隨舊子程式消失（404），新 session 的工具清單照 B 的政策。
- HA 每次存政策都重啟（收緊 #54、沒變 #130 都重啟）。PaaS 只在放寬而且子程式在跑時重啟。HA 沒有管理員停掉子程式的操作，所以 PaaS
  「停著時放寬不啟動」沒有對應。

### 3.4 探測退避與節流單位（UC-12）

- 計畫 §12.2 的衝突表把 `Hc/health.py` 排給 HM-22（HM-04 → HM-09 → HM-30 → HM-22），那時 HM-09 還沒寫。HM-09 已經把 Nextcloud 的兩種文字
  （`BACKEND_HTTP_ERROR status=401`、登入失敗後的節流 `status=429`）算進認證被拒（`health.AUTH_REFUSED`，`tests/test_health_backoff.py` 釘住
  子程式的原文），所以本片不改 `health.py`。
- Nextcloud 子程式（`apps/nextcloud/vendor/nextcloud_mcp_server/client.py:140-217`）的 auth latch：同一組帳密收到 401 之後，到子程式重起前不再
  連 Nextcloud；429 之後停 5 分鐘（子程式自己讀 `Retry-After`、上限 15 分鐘，但經 HA 的 `backend_policy` 收到的 429 沒有標頭，
  一律用預設的 5 分鐘：`tests/test_nextcloud_child.py::test_throttle_latch_expires_and_errors_keep_public_codes`）。健康探測用新的 client，但共用這個 latch，而且探測不會被取消（慢的
  401 也會記下）。所以同一組錯誤帳密，每個子程式行程只會失敗登入一次；監看的退避管的是探測子程式的次數。
- 本片的真子程式測試（`test_a_refused_login_backs_off_only_its_own_profile`，退避縮短成 0.3、0.6、1.2… 秒）：B 的錯密碼讓 B 的監看連三次
  認證被拒、間隔變長，假 Nextcloud 只看到 B 一次失敗登入；預設帳號的監看照常、後端可連，只有 B 的 log 說它在退避；B 存對的 app password
  （不換 token）後子程式重起、退避歸零、恢復可連。
- **沒確認的**：Nextcloud 的暴力破解防護以什麼為單位計（來源位址、使用者、動作），HA 上每個帳號都從 add-on 的同一個位址連。現有 DOCS 與
  FEATURE-MATRIX FM-91 推定是來源位址；那樣的話，一個帳號的錯誤密碼會讓同一台 Nextcloud 上的其他帳號登入也變慢。latch 把傷害壓到「每次子程式
  啟動一次」，但不能歸零。實測方法見第 12 節第 6 點。

### 3.5 PaaS #152：存檔與測試連線過 SSRF

- PaaS 在管理程序存檔時解析 DNS、擋私網與 loopback、metadata（400 `ssrf_blocked`），「測試連線」與健康探測也在連線前擋；Nextcloud 子程式
  本身連線時不檢查。HA：HM-20 起，開通的產品存檔時擋 loopback、link-local 與 metadata（不解析 DNS、區網照放），子程式連線時再擋一次
  （`WOOW_MCP_DENY_LOOPBACK=1`）；「測試連線」經子程式，也被擋。差異已在 §8.8 #39（HM-20 核對過 #152）。
- 本片補的是 Nextcloud 兩條存檔路由的端到端案例（`test_a_refused_url_stores_nothing_and_rotates_nothing`）：存檔檢查在換身分之前，被拒的
  網址不會先停子程式、不會換 token。

### 3.6 bearer 401、密鑰網址 404 與子程式 bearer

- 8081 只看 token（HM-08）：HM-08 的契約案例本來就逐產品跑（`test_profile_routing.py` 參數化 `SWITCHABLE`，含 Nextcloud）。本片加 Nextcloud
  的情境：輪替與撤銷後的舊 token、隨機 token 兩條入口都拒；預設帳號的密鑰網址帶 B 的 `Authorization` 仍是預設帳號；帶 `X-MCP-Profile: <B>`
  的 Bearer 仍是預設帳號；B 的 session 拿預設帳號的 token 是 404。
- 沒開通：同一份磁碟，開機守門把 B、C 當休眠帳號撤銷（I13），兩條入口都拒，預設帳號照今天。
- 真子程式（T-23）：每個 Nextcloud 子程式只認自己的 child token；不帶、隨機、另一個帳號的、空的、只有 scheme、兩個標頭（都是自己的、自己的
  加別人的）都 401。

### 3.7 開關關

- `identity_rebound` 開關關時一律回 False（`same_identity` 不會被呼叫），存檔照今天：先寫入、再重啟子程式，token 與歷史不變，回應照舊
  （`test_switched_off_a_changed_account_keeps_todays_answer_order_and_token`）。DQ-40 ⑨ 的新來源規則也一樣在開關後面。
- 面板的 `identityBound` 只在選了帳號（開通）時讀。
- 本片全部受開關管，契約第 1.2 節不用加項；`unreleased-changes.md` 第 4.2 節加一列。

## 4. PaaS 變動清單（GitHub 鏡像 `WOOWTECH/woow-mcp-server`，唯讀；2026-11-19 讀）

| commit | 內容 | 對本片 |
|---|---|---|
| `0f43fd3`（#152，main `671d2e7` 合併） | Nextcloud `base_url` 存檔與測試連線過核心 SSRF | HM-20 已對齊（§8.8 #39）；本片補 Nextcloud 兩條存檔路由的測試（第 3.5 節） |
| `4f1a77f`（#152） | Nextcloud 管理端 log 遮罩保留 args 形狀 | 不適用：PaaS 管理 app 自己的紀錄遮罩；HA 的遮罩在 HM-02（`paas-test-mapping.md` 已對照） |
| `0f94aa4`（#154，main `a175150` 合併） | Nextcloud 換使用者或網址撤銷舊 MCP 網址：`IDENTITY_KEYS`＝`base_url`、`username`；`normalize_base_url` 與 `_keep_stored_spelling`；身分換了一定重啟（`restart:false` 也一樣）；回應 `token_rotated` 與 `message`；成功另記一行不含值的 INFO | 本片對齊（第 3.1、3.2 節）；差異寫進 §8.8 #129、#131（回應形狀 #113 照 HM-12） |
| `bf4460b`（2026-11-12） | Nextcloud 多設定檔工具政策重啟的修正（B-05） | pin 之前就有；對照到 §8.8 #54、#130 |
| `1637a0f`、`3b135ca`（#155） | 閘道位元組預算與結構守門（動到 `apps/nextcloud` 的測試） | HM-31 已對齊，和本片無關 |

- 鏡像的 main 是 `5ef1046`（2026-11-18 03:00Z，#159 合併）；`apps/nextcloud` 最後一次被改是 `1637a0f`（#155）。`48f394d` 之後的 #157～#159
  只動 K8s。

## 5. PaaS 測試逐案對照

`apps/nextcloud/tests/test_identity_bound_token.py`（#154，22 個函式；`paas-test-mapping.md` 已指到本檔）：

| PaaS 測試 | HA 的測試（`tests/test_nextcloud_multi_profile.py`，另註明的除外） |
|---|---|
| `test_launch_policy_declares_base_url_and_username_as_the_identity` | `test_nextcloud_is_bound_to_its_url_and_username`；`test_identity_fields.py::test_the_token_rotating_fields` |
| `test_update_response_model_carries_token_rotated` | §8.8 #113：HA 只有換了 token 的回應帶 `token_rotated`（HM-12 的測試） |
| `test_identity_change_revokes_the_old_url_and_issues_a_new_one`（username、base_url、兩者 × restart） | `test_a_changed_account_stops_the_old_child_then_rotates_the_token_in_one_write`（9 案）；HA 沒有 restart 旗標，每次存後端都重啟 |
| `test_changing_only_the_app_password_keeps_the_token` | `test_an_app_password_change_or_the_first_setup_keeps_the_token`；`test_which_saves_rebind_the_token[app password]` |
| `test_a_different_spelling_of_the_same_url_is_not_an_identity_change`（7 種寫法） | `test_which_saves_rebind_the_token`（大小寫、預設 port、結尾斜線）、`test_the_same_server_written_another_way_keeps_the_token`；前後空白 HA 400（`test_a_refused_url_stores_nothing_and_rotates_nothing`），貼上的頁面路徑 HA 換（§8.8 #129） |
| `test_a_really_different_url_is_an_identity_change`（5 種） | `test_which_saves_rebind_the_token` 的 `OTHER_ACCOUNT`、`test_a_changed_account_…` |
| `test_a_legacy_unnormalized_stored_url_is_not_rotated_by_resaving_the_form` | `test_the_same_server_written_another_way_keeps_the_token`（存回原來的寫法也不換；HA 照新寫法存，§8.8 #129） |
| `test_first_time_setup_keeps_the_issued_url`（4 種起始狀態） | `test_an_app_password_change_or_the_first_setup_keeps_the_token`、`test_the_first_setup_a_revoked_token_and_a_cleared_connection`；HA 的連線三欄必填，PaaS seed 的部分狀態不會出現 |
| `test_a_revoked_or_missing_token_is_not_replaced_by_an_identity_change` | 同上兩案（撤銷後換帳號不發 token） |
| `test_clearing_the_identity_rotates_and_filling_it_back_does_not` | `test_a_cleared_connection_rotates_the_token_and_the_next_setup_keeps_it`（HA 只能整份清空） |
| `test_the_old_child_is_stopped_before_the_new_identity_becomes_durable` | `test_a_changed_account_…`（journal：停 → 寫入時子程式已停 → 發布 → 起；一次 replace） |
| `test_a_failed_write_leaves_the_old_token_and_the_old_child_intact` | §8.8 #114；HM-12 的故障注入不分產品（`tests/test_odoo_identity_rotation.py`），本片不重複 |
| `test_an_extra_account_rotates_only_its_own_token` | `test_one_profiles_new_account_rotates_only_its_own_token`；真子程式那案的換帳號 |
| `test_the_shared_settings_route_rotates_the_token_too` | HA 只有一套管理操作（§8.8 #86）：`backend`、`backend/patch` 兩條都在 `test_a_changed_account_…` |
| `test_the_shared_route_keeps_the_token_for_a_password_or_a_same_url_spelling` | `test_the_same_server_written_another_way_keeps_the_token`、`test_an_app_password_…` |
| `test_the_shared_route_validates_the_url_like_the_connection_page` | §8.8 #86；`NextcloudConnection` 的既有驗證與 `test_a_refused_url_…` |
| `test_a_stale_or_missing_revision_does_nothing` | HM-10 的 `tests/test_profile_admin_api.py`（不分產品），本片不重複 |
| `test_a_blocked_url_stores_nothing_and_does_not_rotate` | `test_a_refused_url_stores_nothing_and_rotates_nothing`（兩條路由；§8.8 #39） |
| `test_the_response_message_says_the_old_url_was_revoked_and_the_child_restarted` | §8.8 #113、#116：HA 回應不帶文字，面板依 `token_rotated` 提示（HM-12 面板） |
| `test_a_failed_restart_after_a_rotation_still_tells_the_admin_the_url_changed` | HM-12 的形狀 D（`token_rotated` 加 `config_apply_failed`），不分產品 |
| `test_a_password_only_save_adds_no_notice_and_keeps_the_restart_flag_semantics` | `test_an_app_password_…`（沒有 `token_rotated`）；HA 沒有 restart 旗標 |
| `test_the_identity_change_log_line_has_no_values` | 每個程序內案例的 log 掃描另外盯 username、主機名與 app password；HA 成功時沒有換身分的 log 行（§8.8 #131） |

`apps/nextcloud/tests/test_main.py` 的政策重啟三案、`test_tool_policy_profiles.py`：

| PaaS 測試 | HA |
|---|---|
| `test_enabling_write_tool_restarts_child` | `test_saving_one_profiles_policy_restarts_only_its_child`（HA 每次存都重啟該帳號） |
| `test_unchanged_policy_does_not_restart` | 同上：HA 沒變也重啟（§8.8 #130） |
| `test_widening_while_stopped_does_not_start` | 不適用：HA 沒有管理員停掉子程式的操作（§8.8 #130） |
| `test_policy_update_only_restarts_selected_real_child`（root_path、mount 兩種） | `test_two_users_of_one_server_stay_in_their_own_profiles_with_real_children`（真子程式的 PID、session）；程序內兩個方向（額外帳號、預設帳號）在 `test_saving_one_profiles_policy_restarts_only_its_child`。HA 的 Ingress 掛載由 HM-10、HM-11 測 |

`apps/nextcloud/tests/test_base_url_ssrf.py`（#152，80 案）：`paas-test-mapping.md` 已對到 HM-20 的測試與 §8.8 #39；本片另加 Nextcloud 存檔路由的案例（第 3.5 節）。

## 6. 守門有效的證據

### 6.1 先紅後綠

- 紅（`c90b214` 的 `products.py`、`identity_fields.py`、`contracts.js`＋本片最後的測試；2026-11-19 10:01）：pytest 89 案，**24 失敗、65 通過**
  （47.8 秒）。

| 檔 | 案數 | 失敗 | 通過的是什麼 |
|---|---|---|---|
| `tests/test_nextcloud_multi_profile.py` | 39 | 23 | 16 案守今天或別的片已有的行為：同一台伺服器的寫法、只換 app password、初次設定與撤銷、被拒的網址、存政策只重啟該帳號（HM-10 起就是）、開關關兩案、token 矩陣、休眠、退避（HM-09＋子程式 latch） |
| `tests/test_identity_fields.py` | 18 | 1 | `test_the_urls_compared_as_servers` 紅；面板同步那案照過（基準上兩邊都只有 Odoo，本來就一致） |
| `tests/test_odoo_identity_rotation.py` | 32 | 0 | 改的是 `Journal` 的變數名與「其他產品」清單（拿掉 Nextcloud），兩邊都過 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs`（node） | 30 | 2 | `identityBound` 的斷言、S-7 的 Nextcloud 提示 |

- 新檔失敗的 23 案：`test_which_saves_rebind_the_token` 的 9 種換帳號、`test_a_changed_account_…` 9 案、綁身分的表、清空會換、只換該帳號、
  單元的清空，以及真子程式那案（前面的 token 與 bearer 矩陣、存政策只重啟 B 都過，停在換帳號那一步：回應沒有 `token_rotated`）。
- 綠（本片的程式）：上面三個 pytest 檔 89 案全過；node 118 案全過。
- 開關模式（第 9.2 節）：紅＝第二次開通乾跑時三個 Nextcloud 測試檔 60 案失敗（第 9.1 節）；綠＝加了 `switched_off` 之後同樣開著跑
  三個檔 106 案全過（第 9.3 節），開關關時也全過（第 8 節）。
- 寫測試時的兩次紅不算數（測試自己的錯，已修）：`all()` 包 `await` 寫成非同步產生器；`httpx` 不送結尾有空白的標頭值
  （`Bearer `），改照 `tests/test_child_bearer.py` 的寫法送空字串與只有 scheme。另外 `test_backend_loopback.py` 不能在 runtime 起來之後才
  import（它載入的 `backend_policy` 要繼承被替身換掉的 `httpx.AsyncClient`），`running_its_program` 在本檔另寫一份。

### 6.2 臨時突變（一次改一處、跑相關的測試、用 git 還原；工作樹最後是乾淨的）

| 突變 | 擋下的測試 |
|---|---|
| M1 網址逐字比（`same_identity` 不認同一台伺服器） | 4 案：`test_which_saves_rebind_the_token[scheme and host in capitals]`、`[default port written out]`、`test_the_same_server_written_another_way_keeps_the_token` 兩種路由 |
| M2 只比伺服器、不比路徑 | 7 案：路徑不同、路徑大小寫、沒有路徑、貼上的頁面路徑（單元與經 runtime 兩邊） |
| M3 路徑不分大小寫 | 1 案：`test_which_saves_rebind_the_token[path in capitals]` |
| M4 `IDENTITY_BOUND` 拿掉 Nextcloud | 3 案：只換該帳號、綁身分的表、面板 `identityBound` 同步 |
| M5 `identity_rebound` 不看開關 | 10 案：單元的開關關一半、`test_switched_off_a_changed_account_keeps_todays_answer_order_and_token` |
| M6 `SAME_SERVER_URLS` 加 Odoo | 2 案：`test_the_urls_compared_as_servers`、綁身分的表 |
| M7 面板 `identityBound` 拿掉 Nextcloud | 1 案：`test_identity_fields.py` 的面板同步；node 另 2 案（第 6.1 節） |

## 7. HM-01 黃金回歸與契約凍結（開關關；開通重跑）

- 期望值一個都沒改：`tests/test_single_profile_golden.py`、`tests/test_mcp_contract_freeze.py`、`tests/test_admin_contract_freeze.py`、
  `tests/contract/*.json` 都沒動。
- 結果：`test_single_profile_golden.py`、`test_upgrade_zero_rewrite.py`、`test_mcp_contract_freeze.py`、`test_admin_contract_freeze.py`、
  `test_router_passthrough.py`（開通重跑三組凍結）共 139 案全過。
- 為什麼不用改：開關關時 `identity_rebound` 回 False，存檔照今天；`same_identity` 只在開通、綁身分的存檔被呼叫；面板的 `identityBound` 只在
  選了帳號時讀。開通重跑（`test_router_passthrough.py`）的存檔是「欄位值不變的部分編輯」，不換身分。
- 倉庫的開關一開，黃金回歸與兩個凍結的 Nextcloud 案會讀到開著的開關而失敗（第 9.1 節）；HM-23 的 `e803d58` 讓它們固定測開關關、開著的
  那一次交給 `test_router_passthrough.py`（第 9.3 節）。本片沒有動這些共用檔。

## 8. 本機檢查（2026-11-19，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排在團隊的共用佇列與 conftest 的鎖後面）

| 檢查 | 結果 |
|---|---|
| pytest：本片動到與涵蓋的檔，開關關（最後的程式與測試，2026-11-19 11:39） | 268 案全過（407 秒）：`test_nextcloud_multi_profile.py`、`test_identity_fields.py`、`test_odoo_identity_rotation.py`、`test_nextcloud_child.py`、`test_nextcloud_error_secrets.py`、會 import `nextcloud_fixtures` 的 `test_expansion_runtime.py`、`test_native_probe_separation.py`、`test_six_hardening.py`，加 HM-01 的 `test_single_profile_golden.py`、`test_upgrade_zero_rewrite.py` |
| pytest 回歸，開關關（本片的程式改完後，09:18～09:34） | 4 組 1,016 案全過：黃金回歸、零改寫、兩個凍結、`test_router_passthrough.py` 139 案；`test_new_origin_secret.py`、`test_saved_destinations.py`、`test_restore_review.py`、`test_panel_profile_api_shapes.py`、`test_dormant_profiles.py`、`test_odoo_multi_profile.py`、`test_identity_fields.py` 250 案；`test_profile_admin_api.py`、`test_profile_routing.py`、`test_health_backoff.py`、`test_profile_runtime.py`、`test_tool_inventory.py`、`test_ledger_precheck.py`、`test_secret_path.py`、`test_initialize_identity.py`、`test_admin_pipeline_matrix.py` 240 案；`test_nextcloud_child.py`、`test_nextcloud_error_secrets.py`、`test_backend_loopback.py`、`test_profile_lifecycle.py`、`test_owner_defaults.py` 387 案 |
| 開通乾跑（nextcloud 暫時開著） | 第 9 節 |
| node（`packages/mcp-admin-ui/tests/*.test.mjs`） | 118 案全過（Node 26.12.1；Node 22.23.3 也全過） |
| 面板建置、build closure、Playwright | `npm run build` 成功；build closure PASS；Playwright 166 案全過（6.0 分鐘；`contracts.js` 改完後跑） |
| `packaging/validate.py`（`ha-gh-release` 的 venv） | PASS（8 個 manifest、翻譯、pin、workflow 政策） |
| packaging unittest（同一個 venv，短 TMPDIR） | Ran 366、OK（skipped=5）；兩次開通乾跑時也都 OK |
| HM-00 對照腳本的子集（C2～C5、C7～C9；C1 只適用純文件片，C6 要讀本機 PaaS repo） | 全部通過：C2 差異表 131 列；C3 FEATURE-MATRIX 112 列；C4 G6 §5 29 列；C5 29 個情境、登記 71 個測試檔；C7 錯誤代碼；C8 46 題；C9 44 列 |
| 臨時突變 | 7 個全部擋下（第 6.2 節） |
| 帳本預檢、秘密預檢 | 第 14 節 |

### 8.1 只在 CI 跑的測試

- 本片新增與改過的測試都在本機跑過；它們不依賴 uid 或檔案權限（真子程式的案例一般使用者也起得來），在 root 下也成立。
- 要 root、本機一定失敗的 7 個既有案例（不是本片造成，本片沒動）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`。CI 用 root 跑。
- 全套 pytest 本機沒跑（共用鎖排很久；只跑動到與涵蓋的檔），以 GitHub CI 為準。

### 8.2 `checks` 秒數與新測試的時間

- `checks`：開 PR 後補（前：`claude-delivery` 最近的 PR run 約 30～40 分鐘；後：本片 PR）。
- 新測試的本機秒數：`test_nextcloud_multi_profile.py` 39 案；兩個真子程式的案例 8.3 秒（`test_two_users_of_one_server_stay_in_their_own_profiles_with_real_children`）、
  7.3 秒（`test_a_refused_login_backs_off_only_its_own_profile`），其他每案都在 7.2 秒以下（第 8 節那次的最慢 12 案沒有它們）。三個 pytest 檔
  89 案在紅的那次跑 47.8 秒。

## 9. 開通乾跑與升版 PR 要做的事

做法：`features.py` 暫時改成 `frozenset({'nextcloud'})`（不 commit；腳本結束時用 `git checkout` 還原，事後 `git status` 確認乾淨），跑跟開關
有關的測試檔，再跑 packaging unittest。第一次分三批跑，被共用鎖搶到逾時（`LOCAL TEST lock busy`），停掉重來，不算數。

### 9.1 第二次乾跑（本片的程式與測試，加開關模式之前；2026-11-19 10:21～10:33）

- 31 個檔：HM-01 的黃金回歸與兩個凍結、`test_router_passthrough.py`、`test_upgrade_zero_rewrite.py`、`test_real_products.py`、子程式 bearer 與
  port、單帳號 runtime 的幾個檔、Nextcloud 的子程式測試、本片的三個檔等。pytest 1,391 案，**80 失敗**（11 分 21 秒）；packaging unittest
  366 案 OK（5 skip）。

| 失敗的原因 | 案數 | 誰處理 |
|---|---|---|
| Nextcloud 自己的測試讀倉庫的開關：開通的子程式拒絕 loopback 假後端（HM-20：`BACKEND_DESTINATION_DENIED`、假後端收不到請求、環境多 `WOOW_MCP_DENY_LOOPBACK=1`）；`production_runtime` 不帶 `X-MCP-Profile`，管理 API 回 400；開關關的案例斷言 `not features.enabled` | 60：`test_nextcloud_child.py` 37、`test_nextcloud_error_secrets.py` 20、本片開關關的 3 案 | 本片（第 9.2 節） |
| 共用測試讀倉庫的開關（同上兩種原因）：黃金回歸 2、兩個凍結各 1、`test_router_passthrough.py` 開關關 2、零改寫那案的開關關一半 1、`test_real_products.py` 1、`test_child_bearer.py` 2、`test_child_port_param.py` 4、`test_profile_lifecycle.py` 1、`test_restore_review.py` 1、`test_six_hardening.py` 1 | 17 | HM-23 的 `e803d58`（不分產品；第 9.3 節） |
| `test_multi_profile_is_switched_off_for_every_product` 釘住開關是空的 | 1 | 升版 PR（第 9.4 節） |
| `test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources`：帳本的 `features.py` sha256 | 1 | 升版 PR 重算帳本那列（每個升版 PR 都一樣） |
| `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`：本機不是 root | 1 | 不是開關造成，開關關也一樣失敗；CI 跑（第 8.1 節） |

### 9.2 本片的處理：Nextcloud 的測試自己指定開關模式

- `tests/nextcloud_fixtures.py` 加 `switched_off` fixture：測試期間所有產品都沒開通，不管倉庫開了什麼；測試裡面再開（`multi_profile_runtime`）
  照樣有效。測試起的子程序讀的是倉庫的開關，不是這個 fixture（這幾個檔的子程序只拿 `child_spec` 給的環境，不讀開關）。
- `test_nextcloud_child.py`、`test_nextcloud_error_secrets.py` 整個模組指定（`pytestmark`），本片開關關的三案各自指定。案例本身沒改。
- 為什麼不用 `loopback_backends.allowed()`：這兩個檔測的是今天的 add-on（單帳號、子程式照今天的環境），開通的子程式拒絕 loopback 已經在
  `test_backend_loopback.py`（逐產品，含 Nextcloud）測，開通的 Nextcloud 在本片的新檔測。
- 和 HM-23 的 `tests/switch_modes.py` 是同一個做法（HM-23 用 EMQX 開著找出共用測試，加同名的 fixture）。HM-23 還沒合併，本片不依賴它，
  fixture 放在 Nextcloud 自己的測試工具檔；兩片都合併後可以只改 import、留一個（第 15 節）。

### 9.3 第三次乾跑（本片加了開關模式，另外暫時套上 HM-23 的 `e803d58`；2026-11-19 11:39～11:50）

- HM-23 的 `e803d58`（`test(core): tests that pin one switch mode name it…`，31 個測試檔）還沒合併：從 HM-23 的 clone 唯讀匯出 patch，套在本片的
  工作樹上、不 commit，跑完連同 `features.py` 一起還原、刪掉它新增的 `tests/switch_modes.py`。目的是確認本片與 HM-23 都合併之後，開通
  Nextcloud 的升版 PR 只剩第 9.4 節的事。
- 17 個檔：第二次乾跑有失敗的 16 個檔裡的 15 個（`test_owned_executable.py` 要 root，除外），加本片改過的 `test_identity_fields.py`、
  `test_odoo_identity_rotation.py`。pytest 703 案，**2 失敗、701 通過**（9 分 51 秒）；
  packaging unittest 366 案 OK（5 skip）；還原後 `tests/`、`packaging/`、`features.py` 沒有留下改動。
- 失敗的 2 案正好是第 9.4 節升版 PR 要做的事：HM-23 版的 `test_a_product_is_switched_on_only_by_its_release`（Nextcloud 還是 0.4.14，
  開通要 0.5.0 以上）、`test_tool_inventory.py` 帳本的 `features.py` sha256。三個 Nextcloud 測試檔 106 案全過，第 9.1 節的 17 個共用案也都過。

### 9.4 開通 Nextcloud 的升版 PR 要做的事

- `Hc/features.py` 加 `nextcloud`；`docs/provenance/runtime-patches.json` 的 `features.py` 那列照實際內容重算（`test_tool_inventory.py` 會比）。
- 計畫 §11.3 的升版逐檔清單（版號 0.5.0、`addons/nextcloud/config.yaml`、CHANGELOG、DOCS、README、`upgrade-notes.yaml`、`packaging/validate.py` 與
  `inputs.json` 的版本覆寫、workflow 運算式、`Hc/__init__.py`、Dockerfile 的 `ARG BUILD_VERSION`、Core 白名單補審等）。
- CHANGELOG 的 Nextcloud 句子與 `config.yaml`、DOCS、README 的「一個 Nextcloud 帳號」說法、DOCS 的節流說明：`unreleased-changes.md` 第 3.6 節。
- `test_upgrade_zero_rewrite.py::test_multi_profile_is_switched_off_for_every_product`：HM-23 合併前它釘住「開關是空的」，要改；HM-23 合併後
  它是「產品只能由它的發行版開通」（開著的產品要能有帳號、版本 0.5.0 以上），升版號就過，不用改。
- HM-23 的 `e803d58`（或同樣的改法）要在升版 PR 之前合併；沒合併的話，第 9.1 節那 17 個共用案要在升版 PR 裡照它的做法改。
- 容器探針不用改：開通的產品的假後端已經綁容器私有位址（HM-16、HM-20），第二次乾跑時 packaging unittest 也照過（`test_container_probe.py`、
  `test_container_acceptance.py` 在裡面）。實際容器的驗收在升版 PR 的 builder 步驟（計畫 §11.3 第 3 步）。

## 10. 契約第 9 節的列號（暫定）

- 本片的三列：#129 換身分時網址怎麼比、#130 存政策何時重啟子程式、#131 換身分成功時的 log。另改 #40（PaaS 欄照 #154 補、HA 欄寫明負責片）。
- 基準 `c90b214` 的最後一列是 #128（HM-27）。HM-21、HM-23～HM-26 同時在準備，也可能加列：後合併的一方 rebase 或合併時，把自己的列接在
  當時的最後一列後面重編，改引用的地方（契約第 3.1 節 `backend` 列、第 9 節說明段、第 10 節；威脅模型；驗收矩陣 T-03、T-07；`decisions.md`
  DQ-05 列；`unreleased-changes.md` 第 3.6 節；本筆記）。程式、測試與帳本的 `change` 沒有寫列號，不用為列號重算帳本。

## 11. 前面各片交來的待辦處理表

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-12 筆記第 15 節 | Nextcloud 加進 `IDENTITY_BOUND`、沿用 `rebind_identity`、`ProductStore.rebind`、`stop_child`、補自己的測試；#152 對照 HM-20 | 做了（第 3.1、3.5 節） |
| HM-12 面板筆記第 13 節、計畫 §12.3 的 2026-11-17 註 | 加進 `IDENTITY_BOUND` 時 `Hui/contracts.js` 的 `identityBound` 一起加，否則同步測試會紅 | 做了；`profiles.test.mjs` 的斷言跟著改 |
| 計畫 §9 Nextcloud 列 | 存政策只重啟該帳號；探測退避（節流單位 UC-12）；`config.yaml`「one Nextcloud account」在升版 PR 改；DQ-40 採用時換 url／username 換 token | 前兩項做了（第 3.3、3.4 節；UC-12 留給 HAOS）；第三項列進升版 PR 的清單（第 9.4 節、`unreleased-changes.md` 第 3.6 節）；最後一項做了 |
| 計畫 §12.2 衝突表 `Hc/health.py` → HM-22 | 探測退避 | 不用改：HM-09 已涵蓋 Nextcloud 的文字（第 3.4 節） |
| 進度紀錄（README）、HM-20 筆記第 10 節 | PaaS #152、#154 交 HM-22 對照 | 做了（第 4、5 節） |
| `paas-test-mapping.md` | #154 的 22 案、`test_main.py` 三案、`test_tool_policy_profiles.py` 指到 `tests/test_nextcloud_multi_profile.py`（暫定名） | 檔名照用，逐案在第 5 節；產生器的「暫定名」由 repo 外的產生器下次重產時拿掉（第 15 節） |
| 驗收矩陣登記表 | `tests/test_nextcloud_multi_profile.py`（暫定名）：兩個使用者、存政策只重啟該帳號、換 url／username 換 token | 做了，改成「新增」 |
| FEATURE-MATRIX FM-47、FM-69、FM-91、FM-153 | 存政策只重啟該帳號、探測退避、Nextcloud 多使用者、換使用者欄位換 token | 做了；FM-153 的 PaaS 欄（「只有 Odoo」）在 #154 之後過時，交主對話改（第 15 節） |

## 12. HAOS 實機驗收要什麼（交 Nextcloud 的升版片；本片沒碰任何主機或後端）

- 步驟寫在 `docs/operations/acceptance.md`「Nextcloud 開通的 HAOS 驗收」。
- **要使用者批准的後端身分**：同一台測試用 Nextcloud 上三個專用使用者 A、B、C（C 只給換帳號用），各一個 App 密碼；建立與刪除都要批准。
  節流單位那一步會在真的 Nextcloud 留下失敗登入紀錄，做完要在 Nextcloud 管理頁重設暴力破解防護（也要批准）。
- **T 列**：T-01（版本與 digest）、T-03（換帳號換 token、只換 App 密碼不換、主機大小寫不換）、T-04（兩個使用者的 WebDAV 互看不到）、T-05、
  T-23（P9 `--cross`、容器探針的多帳號階段）、T-07（存政策只重啟該帳號）、T-29（清理與合成憑證掃描）；外加 UC-12 的節流單位。
- 容器探針不用改：開通的產品的假後端已經綁容器私有位址（HM-16、HM-20），多帳號階段不分產品；Nextcloud 的假後端是探針自己的（使用者 `tester`）。

## 13. 本片用到的決策（`docs/multi-profile/decisions.md`）

| DQ | 結論 | 本片怎麼用 |
|---|---|---|
| DQ-05 | Odoo 換身分換 token；比照的範圍照 DQ-40 ⑩ | Nextcloud 照做；網址的比法是實作細分（記進 DQ-05 列，不是新題目） |
| DQ-40 (a) ⑩ | 換使用者欄位換 token 擴到 Nextcloud url／username、Hermes | Nextcloud 做了；Hermes 是 HM-24 |
| DQ-40 (a) ⑨ | 開通後改 url 來源要重填秘密（全部產品） | HM-12 已做；本片的換 host、scheme、port 案例都帶 app password |
| DQ-40 (a) ⑦、DQ-10 | 後端網址拒絕 loopback | HM-20 已做；本片補 Nextcloud 存檔路由的案例 |
| DQ-25 | 認證被拒退避 15→300 秒 | HM-09 已做；本片補 Nextcloud 真子程式的案例 |
| DQ-02 (a) | 新帳號複製預設帳號當下的政策 | 測試的額外帳號照這樣建（`create_profile`） |
| DQ-36 | 不署名、不合併 | commit 沒有任何署名；本片不 push、不開 PR |

沒有碰到待定題。

## 14. 預檢結果

在 `d6f5b47`（最後一個改程式、測試與文件的 commit；工作樹只有這份筆記還沒 commit）跑；`65a61d8` 上也跑過，結果相同（秘密預檢 5 個
commit、0 命中）。本筆記的 commit 只加這份筆記的文字；commit 之後在最後的 HEAD 再跑一次兩個預檢，結果寫在交接報告。

- 秘密預檢：`python3 scripts/secret_precheck.py --tools <scan0414 的 gitleaks>`：gitleaks 8.28.0（pin、驗過），`c90b214..d6f5b47` 6 個
  commit，**0 命中**。
- 帳本預檢：`python3 scripts/ledger_precheck.py`：`runtime-patches.json` 180、`runtime-sources.json` 70、`tool-surface.json` 159 個摘要都
  0 漂移、0 缺；對 `claude-delivery` 的合併基準改 19 個檔（含這份筆記），列管的 3 個（`products.py`、`identity_fields.py`、`contracts.js`）
  都隨 `runtime-patches.json` 更新；沒有新的未列管 runtime 檔：**OK**。
- tool-surface：沒有動 `apps/runtime/*.py`、`apps/*/launch.py`，不用重產（上面 159 個摘要 0 漂移）。

## 15. 還沒解決、交給後面的片與待決問題

- **UC-12（Nextcloud 的節流單位）**：沒實測，見第 3.4 節與第 12 節。
- **Odoo、Hermes 的網址要不要也照伺服器比**：本片只讓 Nextcloud 照伺服器比（對齊 PaaS 各產品自己的做法）。Odoo 的 host 只差大小寫時 HA、PaaS
  都會換 token；要一致可以把 Odoo 的 url 加進 `SAME_SERVER_URLS`（安全上沒有差：同一台伺服器）。Hermes（HM-24）開通時一起決定。
- **PaaS 沿用存檔寫法、HA 照新寫法存**（§8.8 #129）：結果一樣不換 token，只差存下來的字。要不要對齊，回補 PaaS 時（HM-29）一起說明。
- **存政策沒變也重啟**（§8.8 #130）：HA 既有行為；要改成「沒變不重啟」是另一片，不受開關管的話會改到所有產品。
- **repo 外的文件**（交主對話）：FEATURE-MATRIX FM-153 的 PaaS 欄「只有 Odoo（#131）」在 #154 之後過時；`deviation-trace.md`、`paas-test-mapping.md`
  由產生器重產時，HM-22 的「暫定名」拿掉、#40 的 PaaS 欄跟上（本片改了契約 #40）。
- **`unreleased-changes.md` 第 6 節過時**（觀察，不是本片的事）：HM-13b（#108）、HM-13c（#112）、HM-16（#109）、HM-27（#116）都已合併，
  但第 1、4 節沒照第 6 節的說明補；下一個發版片或 HM-18 要補。本片只加自己的列。
- **升版 PR**：第 9.4 節的清單。
- **和同時在做的片會撞的地方**（2026-11-19 唯讀看各 clone；後合併的一方手動合併，合併 commit，不 rebase）：
  - HM-24（Hermes）也改 `IDENTITY_BOUND`（`{'odoo', 'hermes'}`）、`contracts.js` 的 `identityBound`、`profiles.test.mjs`、
    `test_odoo_identity_rotation.py`（說明兩處、`OTHERS` 拿掉 Hermes）、`identity_fields.py` 的註解與帳本那三列。合起來是
    `{'odoo', 'nextcloud', 'hermes'}`、`OTHERS` 兩個都拿掉、帳本照合併後的內容重算。
  - 契約第 9 節：HM-21、HM-23～HM-26 也都從 #129 起編（第 10 節）。
  - HM-23（EMQX）的 `e803d58` 加 `tests/switch_modes.py`（同樣的 `switched_off`）並改 25 個共用測試檔，涵蓋本片乾跑的 17 個共用失敗（第 9.3 節）。
    本片的 fixture 放在 `tests/nextcloud_fixtures.py`，不依賴 HM-23；兩片都合併後可以改成用同一個（只改 import）。
- **面板的假伺服器只模擬 Odoo 換 token**：`packages/mcp-admin-ui/fixtures/server.mjs` 存 Nextcloud 的新帳號不會回 `token_rotated`。面板處理
  `token_rotated` 不分產品，node 測試有 Nextcloud 開通與沒開通的提示（S-7），瀏覽器測試的換 token 情境用 Odoo（`backend-identity.spec.mjs`）；
  本片沒改假伺服器。要拿它示範 Nextcloud 換 token 時再補（HM-24 加 Hermes 時可以一起）。

## 16. commit（`c90b214` 之後）

| commit | 內容 |
|---|---|
| `16994f6` | test(core)：本片的測試（先紅：在 `c90b214` 的程式上失敗，第 6.1 節） |
| `5ec208d` | feat(core)：開通的 Nextcloud 的 MCP token 綁它的 url 與 username；面板 `identityBound` 加 Nextcloud；3 個列管檔的帳本重算 |
| `b65afec` | test(core)：每個 Nextcloud 案例寫明它驗什麼；開關關時存政策的重啟也記 journal |
| `9ec145d` | test(nextcloud)：Nextcloud 的測試自己指定開關關（第 9.2 節） |
| `65a61d8` | docs(multi-profile)：契約、威脅模型、驗收矩陣、決策、帳本清單、未發版變更與 HAOS 驗收步驟 |
| `d6f5b47` | docs(multi-profile)：開通的 CHANGELOG 句子哪幾行是計畫 §7.2 的共通項目；之前存的 loopback 網址照樣顯示但連不上 |
| 本筆記的 commit | docs(provenance)：本筆記 |

都是一般 commit，沒有 rebase、amend 或 force push；沒有 push（獨立審查之後由收尾步驟 push）。
