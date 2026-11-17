# HA 多帳號 HM-27 provenance：密鑰網址的服務層級 Origin 清單，預設 report-only（2026-11-17）

## 結論

- **照 DQ-11 (a)（使用者 2026-11-14 採用）做完**：開通的產品，密鑰網址（`/private_<token>/mcp`）在驗過 token 之後檢查 Origin，
  全 add-on 一份服務層級清單、所有帳號共用；沒存過時＝`report-only`＋`https://claude.ai`。
  - report-only：清單外（清單外、畸形、`null`、兩個以上）**照常服務，回應逐位元不變**，記一行 `decision=would_deny`，帶帳號 id
    前 8 碼，每帳號節流（每帳號每個來源 60 秒一行、每帳號每分鐘最多 20 行，壓下的補一行）。
  - enforce：**只擋清單外**（403 `{"error":"request denied"}`，閘道固定本體；記 `decision=deny`）；清單內與沒帶 Origin 照舊。
  - **不加任何 CORS**（FM-74）；Bearer `/mcp` 帶 Origin 照舊一律 403、不記；Headscale 照舊只放 `https://claude.ai`；
    DQ-11 第二問沒有動（第 14 節）。
  - 設定存在 `/data/mcp/origin-policy.json`（不進預設帳號的 state），面板經共用管線改：`GET`／`PUT {base}/api/origin-policy`、
    If-Match、Idempotency-Key、收據放在旁邊的 `.origin-policy.json.operations.json`。面板在「連線與權杖」頁加一張卡片
    「瀏覽器來源檢查（全 add-on 共用）」。
- **受開關管**：產品不在 `MULTI_PROFILE_PRODUCTS` 時不建 ProfileManager，所以不讀不寫那個檔、沒有路由（`/api/origin-policy` 是
  未知操作，404）、密鑰網址照今天、面板不畫卡片也不送請求。HM-01 的黃金回歸與兩個契約凍結的期望值一個字都沒改，照過。
  `MULTI_PROFILE_PRODUCTS` 維持空集合。
- **計畫沒寫的細節**照 PaaS（節流的速率與呈現規則、正規化、壞值時 503、預設值）；PaaS 沒有的取最保守的做法（檔名、上限 16 個、
  重複拒收、存檔前不寫檔、enforce 用固定本體、面板放在既有頁面），逐項寫在第 4 節，交審查一起看。
- **先紅後綠**：Python 測試先 commit（`4ba896b`，152 案紅），實作後全綠；面板測試先 commit（`ec7381a`，面板退回上一版時
  node 11 案、Playwright 10 案、形狀比對 4 個情境紅），實作後全綠（第 5 節）。
- **突變**：Python 25 個、面板 16 個，全部擋下（第 7 節；Python 另有 2 個不跑：1 個等價、1 個只差同 uid 的競態）。P26（存檔讀與寫
  之間檔案被換掉）原本沒有測試擋得下，補了一案（`0bf5d19`，第 5 節）。Python 突變前兩次跑因為複本少了 git 不收的目錄、基準失敗而作廢，
  照實留在證據裡（第 7 節）。
- **開關關逐位元**：面板照 HM-11／HM-12 的方法，`165dbaf` 對本分支 276 個比較 0 差異；放進「開關關也畫卡片」的突變，同一個比對
  找到 60 個差異（第 8 節）。Python 側：8 個產品開關關時檔案不讀不寫、沒有路由、照今天（`test_switched_off_the_policy_does_not_exist`），
  HM-01 黃金回歸與兩個凍結照過。
- **本機**：全套 pytest 6,389 案（7 個要 root 的既有失敗，沒有新的）、packaging、Playwright 150、node 99、build-closure 見第 9 節；
  兩個預檢 OK、雙向控制字元 0（第 12 節）。
- **要使用者決定的事**：本片範圍內沒有；DQ-11 第二問仍待 S14，`decisions.md` 第 4 節寫的期限「HM-27 合併前」排不到 S14 之後，
  交主對話（第 14 節）。
- 證據：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-27/`（`logs/` 紅綠與本機檢查、`compare/` 第 8 節、
  `mutations/` 第 7 節、`tools/` 用到的腳本）。用過的 `/tmp/ha-mp-XXXXXX` 記在 `tmpdirs.txt`，都已刪掉。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-27（計畫 §12.3 HM-27；§8.7「Origin 與 loopback」；§3.3 受開關管；§7.1；§7.2 第 10 點；驗收 T-24；R1 清單 §11.4） |
| 分支 | `feat/ha-multiprofile-hm27-20261117`（一般 clone） |
| 基準 | `claude-delivery` `165dbaf`（HM-12 面板 PR #114 合併後） |
| 依據 | `decisions.md` DQ-11（2026-11-14 採 (a)）；FEATURE-MATRIX FM-73、FM-74、FM-123；契約第 2.6 節與第 9 節 #9、#10、#42（HM-00 草稿） |
| 對齊的 PaaS | pin `69ac425`；本機唯讀 PaaS repo 的 `origin/main`＝`48f394d`（第 10 節：Origin 的程式與測試 pin 之後沒變） |
| 受開關管 | 是（計畫 §3.3）；不受開關管的部分：無 |

## 2. 改了什麼、沒改什麼

| 檔 | 改了什麼 |
|---|---|
| `Hc/origin_policy.py`（新，列管） | 政策檔（`PolicyFile`：讀、外改重讀、原子寫入）、檢查（`OriginPolicy.check`）、紀錄與每帳號節流（`Denials`）、PaaS 的正規化與紀錄呈現（`normalize_origin`、`classify_denial`、`sanitize_origin_text`）、請求的形狀與規則（`request_shape`、`requested`）、ETag |
| `Hc/gateway.py`（列管） | `make_apps` 新選項 `origin_policy`：密鑰網址在方法檢查之後、query 之前呼叫（Headscale 規則的位置）；和 `secret_path_allowed_origins` 不能同時給 |
| `Hc/profile_runtime.py`（列管） | `ProfileRuntime(origin_policy=…)`、`RUNTIME_OPTIONS`；`ProfileManager.origin`（Headscale 以外建一份，開機讀一次）、每個帳號拿到自己的檢查 |
| `Hc/profile_router.py`（列管） | 全域路徑 `origin-policy`（GET、PUT）；`GlobalRoute.shape`（第 ⑤ 步的形狀檢查，帳號名稱的照舊） |
| `Hc/profile_admin.py`（列管） | `origin_policy`、`save_origin_policy` 兩個處理（第 ⑧～⑪ 步）；`_if_match`、`_idempotency`、`_complete`、`_replay` 可以指定 ETag 形式與收據檔 |
| `Hui/api.js`、`Hui/app.js`、`Hui/operation-identity.js`（列管） | 讀與存政策、卡片、待確認卡、識別紀錄的新範圍 |
| `packages/mcp-admin-ui/fixtures/server.mjs` | 開通模式的 origin 路由（照伺服器的順序）、`originUnusable`、`/__fixture/origin`；開關關時這條路徑 404 |
| `packages/mcp-admin-ui/README.md` | 新一節「瀏覽器來源檢查（HM-27）」 |
| `tests/test_origin_policy.py`（新） | 150 案（第 5、6、7 節；最後一案是突變 P26 補的） |
| `tests/test_admin_pipeline_matrix.py` | 全域路由的本體：origin-policy 給正確形狀（`GLOBAL_BODIES`） |
| `tests/test_panel_profile_api_shapes.py`、`packages/mcp-admin-ui/tests/browser/profile-api-parity.spec.mjs`、`packages/mcp-admin-ui/tests/profile-api-cases.json` | ETag 類別 `o1`、`if_match: origin`、`setup.origin_policy`；3 個新情境（`origin-policy` 17 案、`origin-policy-unusable` 4 案、`origin-policy-headscale` 2 案）與開關關情境的 1 案 |
| `tests/test_request_budget_gateway.py`、`tests/test_profile_runtime.py` | 釘住選項的兩案多列 `origin_policy` |
| `packages/mcp-admin-ui/tests/origin-policy.test.mjs`（新）、`packages/mcp-admin-ui/tests/browser/origin-policy.spec.mjs`（新） | node 11 案、Playwright 12 案 |
| `docs/provenance/runtime-patches.json` | 新模組一列；7 個列管檔的 SHA-256 照檔重算、`change` 補一段（照 JSON 結構改，沒有用 `--write`） |
| `docs/multi-profile/contract.md` | 第 1.2、2.6、3.1、3.5、4.1、4.2 節；第 9 節 #9、#10、#42 改寫、加 #118～#122；第 10 節一列 |
| `docs/multi-profile/decisions.md` | DQ-11 列補實作；變更紀錄一列 |
| `docs/multi-profile/threat-model.md` | 第 1 節一列、I7 測試欄、第 3 節五條 |
| `docs/multi-profile/acceptance-matrix.md` | T-24 定案；登記 3 個測試檔 |
| `docs/multi-profile/ledger-tracking.md` | `origin_policy.py` 那列 |
| 本筆記 | 新增 |

沒改：`addons/`、任何版號、CHANGELOG、`upgrade-notes.yaml`、`.github/`、`tests/conftest.py`、`Hc/features.py`（`MULTI_PROFILE_PRODUCTS`
仍是空集合）、`Hc/run_product.py`、`apps/`（含 `apps/n8n/run.py`）、`packaging/`、HM-01 的黃金回歸與兩個契約凍結（`tests/contract/`）、
`build-closure.mjs`、既有的面板 spec、`docs/tool-surface.*`（沒動 `apps/runtime/*.py` 或 `apps/*/launch.py`）、`paas-test-mapping.md`、
`deviation-trace.md`（兩個都是 repo 外的產生器產的，第 13 節）。

## 3. PaaS 對照（做法）

PaaS（`Pc/origin_security.py`、`P:docs/security/mcp-origin-policy.md`；R01 D-01、R04 S-09／S-10、R07 X-17）：`McpOriginMiddleware` 在認證與
選帳號之前看 `/private_*` 的 Origin，清單是環境變數 `MCP_ADMIN_ALLOWED_ORIGINS`、模式是 `MCP_ADMIN_ORIGIN_MODE`（預設 report-only）；
清單外在 report-only 記一行 would_deny、交給 #136 之前的 CORS（反射任意來源），在 enforce 回 403 `ORIGIN_DENIED`；清單內來源回精確
CORS 與 preflight；Headscale 一律 enforce、清單是自己的網址；壞值啟動失敗、執行中 503；紀錄整台一份節流。

| 項目 | PaaS | HA（本片） | 來源 |
|---|---|---|---|
| 範圍 | 服務層級（不分帳號） | 同：全 add-on 一份，所有帳號共用 | FM-73、計畫 §8.7 |
| 預設 | report-only、chart 預設 `https://claude.ai`（程式內預設空） | report-only＋`https://claude.ai`（沒有檔案時） | 計畫 §8.7、DQ-11 (a) |
| 「沒通過」 | 清單外、畸形、`null`、重複 | 同（`normalize_origin` 原樣移植：只認 ASCII、小寫、去預設 port、IPv6） | PaaS 規則 |
| report-only | 記 would_deny、交舊 CORS（反射） | 記 would_deny、**回應逐位元不變**、不加 CORS | DQ-11 (a)、FM-74、§8.8 #42 |
| enforce | 403 `{"detail":"ORIGIN_DENIED"}` | 403 `{"error":"request denied"}` | §8.8 #119（第 4 節 f） |
| 位置 | 認證之前 | token 驗過、方法檢查之後 | FM-73 HA 欄、§8.8 #118 |
| 紀錄 | 一行、PaaS 呈現規則、整台節流 | 同呈現規則、帶帳號 id、每帳號節流 | 計畫 §12.3、§8.8 #121 |
| 設定入口 | 環境變數；壞值 exit 3、執行中 503 | `/data/mcp/origin-policy.json`＋面板；壞檔密鑰網址 503、不拒絕啟動 | 計畫 §12.3、§8.8 #120 |
| CORS、preflight | 清單內精確 CORS；report-only 清單外反射 | 都沒有（OPTIONS 照今天 405） | FM-74、§8.8 #42 |
| Headscale | 一律 enforce、清單是自己的網址、記 deny | 照舊只放 `https://claude.ai`、原字串比對、不記、沒有政策 | 計畫 §8.7、§8.8 #9 |
| Bearer | （沒有） | 照舊一律 403、不記 | DQ-11 第二問待 S14 |

## 4. 自己定的細節與理由（計畫沒寫的；照 PaaS，PaaS 也沒有的取最保守）

| # | 細節 | 做法 | 理由 |
|---|---|---|---|
| a | 檔名、位置 | `/data/mcp/origin-policy.json`；收據 `/data/mcp/.origin-policy.json.operations.json`（`OperationJournal` 的命名規則） | 「`/data/mcp` 的服務層級檔」；名稱照 HM-13c 的 `restore-notice.json`、`restore-record.json`。收據不放進索引的 `.profiles.json.operations.json`：那份檔只認帳號操作的 kind 與 subject，加新 kind 會讓舊版讀到時整份收據不能用 |
| b | 檔案格式 | 剛好 `{"version":1,"mode":…,"allowed_origins":[…]}`；0600、單一連結的一般檔、本 uid、16 KiB 以內；來源存正規化後的寫法 | 同 HA 其他 state 的精確鍵集合與 0600（`profiles.read_index` 的檢查）；讀時不 chmod（簽章不變） |
| c | 模式的值 | 剛好 `report-only`、`enforce`（大小寫、空白都不收） | PaaS（chart 的 render 檢查與 `MODES`） |
| d | 來源的上限與重複 | 最多 16 個；正規化後重複 → 422（不默默合併）；不去頭尾空白（面板會先去） | PaaS 是環境變數、沒有上限、重複合併；HA 的檔與請求要有界，取最保守 |
| e | 沒存過時 | 不寫任何檔，讀不到檔＝預設值 | 計畫 §7.2 第 8 點：開通後只多 sentinel 兩檔；第一次存檔才產生（同 `profiles.json`「第一次建立額外帳號才產生」） |
| f | enforce 的拒絕本體 | 403 `{"error":"request denied"}` | HA 的 MCP 端錯誤只用固定本體（同 Bearer 帶 Origin 與 Headscale；契約第 4.2 節）；不新增本體形狀 |
| g | 位置 | token 檢查、方法檢查（405）之後，query（400）之前 | 計畫：「HA 在 token 之後判斷，紀錄可帶帳號 id、未認證請求灌不進來」（FM-73）；放在今天 Headscale 規則的位置，HM-01 的 `order-` 案例照過。所以 PUT、OPTIONS 照今天 405、不記，report-only 的每一行 would_deny 都對應 enforce 的一次 403（PaaS 的性質） |
| h | 紀錄的速率 | 每帳號每個（判定、原因、來源）60 秒一行、每帳號每 60 秒最多 20 行、壓下的行數在下一行之前或時間窗結束時（事件迴圈的計時器）補一行、狀態有界（每帳號最多 256 個鍵、最多 32 個帳號的時間窗） | PaaS 的數字與機制（`DenialLogLimiter`），照計畫改成每帳號一份 |
| i | 紀錄的格式 | `MCP gateway [profile=<id8>]: an Origin the secret path does not allow (report-only: served as usual) decision=would_deny mode=report-only reason=… origin="…"`；WARNING、logger `mcp_admin_core.origin_policy` | HA 閘道其他 WARNING 的前綴與英文（`MCP gateway [profile=…]`）；PaaS 的 key=value 欄位照留（grep `decision=would_deny` 一樣有用）；PaaS 的 `env=` 換成帳號 |
| j | 呈現規則 | PaaS 的 `classify_denial`、`sanitize_origin_text`、URL 形狀與非 URL 摘要原樣移植（Headscale 的尾端點規則不要） | PaaS |
| k | 壞檔 | 密鑰網址每個驗過 token 的請求（帶不帶 Origin）503 `{"error":"state unavailable"}`；Bearer、`/health/ready` 不受影響；開機與每換一次檔案狀態記一行 WARNING（不含內容）；面板用那個檔自己的 ETag 存一份蓋過去 | PaaS 執行中讀到壞值：MCP 路徑一律 503、含不帶 Origin 的請求；PaaS 啟動時壞值 exit 3，HA 若拒絕啟動，壞檔就沒有修復途徑（add-on options 鎖死），所以只取執行中的做法 |
| l | 外改 | 每個這種請求看一次檔（lstat），簽章變了就重讀；有效的替換立即生效（不像索引 DQ-12 那樣黏住到重啟） | HA 其他 state 每請求重讀、外改立即生效（§8.8 #46）；政策檔不決定 token 屬於誰，沒有索引外改那種路由風險 |
| m | ETag | `"o1-<64 hex>"`：這個程序的隨機金鑰對政策內容（模式＋清單）算的 HMAC，同一份政策（存過或預設）ETag 相同；壞檔對檔案簽章與原始位元組算 | HM-10 索引 ETag 的規則（內容一樣就一樣、重啟後全變；壞索引用簽章與位元組） |
| n | 路由與寫入保護 | 全域路徑 `{base}/api/origin-policy`（不在 `profiles/` 底下）；GET、PUT；PUT 照 HM-10 建立帳號的順序：If-Match 有無 → Idempotency-Key（重送先回）→ ETag → 規則（422）→ 收據開始 → 寫檔 → 收據完成；政策自己的鎖（2 秒，503）；寫檔失敗 409 `operation_outcome_unknown`、收據停在未知 | 任務指定共用管線、If-Match、Idempotency-Key、收據；順序與失敗處理照 HM-10 |
| o | 422 的代碼 | 新代碼 `origin_policy_invalid`（形狀 A，不回顯任何值） | HM-10 名稱規則的做法（`profile_label_invalid`）；PaaS 沒有（環境變數） |
| p | Headscale | 不建政策、不讀檔、不記；路由兩個方法都回未知操作的 404 | 「Headscale 照舊只放 `https://claude.ai`」；PaaS Headscale 被拒會記 deny，HA 取照舊（不加紀錄）。HM-26 開通 Headscale 時要不要在面板顯示固定規則，交 HM-26 |
| q | 面板的位置 | 「連線與權杖」頁加一張卡片，開通（`api.profile` 不是 null）而且不是 Headscale 才畫；每個帳號的畫面都是同一份、都能存 | 任務寫「面板加設定頁」。面板的頁面路徑是伺服器的固定清單（`ui.PAGES`），加一個新路徑會讓開關關時 `GET {base}/<新頁>` 從 404 變成回面板，違反逐位元相同；放在既有頁面最保守。Claude.ai 連線網址的卡片也在這一頁。**交審查確認** |
| r | 面板先擋的錯 | 只看形狀（`http(s)://主機[:port]`、不分大小寫與預設 port 的重複、16 個）；其餘交伺服器（422 固定文字）；訊息不回顯打的值 | 伺服器是唯一的規則；面板只提早回答 |
| s | 啟動時的生效政策行 | 不記（PaaS 記一行 INFO） | HA 沒有 INFO 層級的 add-on 紀錄慣例；只在壞檔時記 WARNING，紀錄最少 |
| t | n8n | `apps/n8n/run.py` 還沒有 ProfileManager（HM-25 才接）；HM-25 改用 ProfileManager 時，`origin_policy.applies` 對 n8n 是真，政策自動套上 | 不碰 `apps/` |

## 5. 先紅後綠

| commit | 內容 | 紅（在它之前的程式上） | 綠 |
|---|---|---|---|
| `4ba896b` | Python 測試：`tests/test_origin_policy.py`、形狀比對的 origin 情境、矩陣的本體 | 152 失敗（模組不存在 102、路由不存在 32、其他）、既有 19 案照過（`logs/red-python.log`） | `00cbbab` 後全過；同一組加相關 10 個檔 489 案全過（`logs/backend-subset-1.log`） |
| `ec7381a` | 面板測試：node `origin-policy.test.mjs`、Playwright `origin-policy.spec.mjs` | 面板與 fixture 退回 `00cbbab`：node 11 案全紅、Playwright 新 spec 10 案紅、形狀比對 origin 情境與開關關情境 4 個紅（`logs/red-node.log`、`logs/red-pw.log`）；開關關與 Headscale 兩案本來就成立，留作守門（第 7 節的突變 U01、U02 證明它們有效） | `983e8a2` 後 node 99 案、Playwright 150 案全過 |

測試本身在綠燈階段改過兩處（都記在 commit 訊息）：`00cbbab` 修正 `tests/test_origin_policy.py` 的一個常數（503 state unavailable 的
`content-length` 是 29，寫成 30）；`0e445e9` 在兩個釘住 `make_apps` 選項的既有測試補 `origin_policy`（`00cbbab` 那個 commit 上
`test_request_budget_gateway.py` 的順序案例會紅，PR head 照過）。

突變補的一案（綠燈之後）：`0bf5d19` 加 `test_a_save_never_replaces_a_file_changed_after_it_was_read`。突變 P26（拿掉
`PolicyFile.write` 寫入前的 lstat 簽章比對）原本沒有測試擋得下，起初以為「存檔讀完、寫入之前檔案被換掉」在程序內做不出來；
用 monkeypatch 包住 `PolicyFile.write`、在它之前寫一份外面的檔就做得出來。實作 `00cbbab` 就有這個檢查，所以這案一寫就綠
（不是先紅後綠）；它有效由 P26 證明（第 7 節）。

## 6. PaaS 測試逐案對照（pin `69ac425`；`origin/main` `48f394d` 這幾個檔沒變）

HA 測試沒寫路徑的都是 `tests/test_origin_policy.py`。

### `packages/mcp-admin-core/tests/test_origin_policy.py`（8 案）

| # | PaaS 案例 | HA |
|---|---|---|
| 1 | `test_untrusted_origin_with_valid_token_cannot_initialize` | `test_enforce_refuses_bad_origins_whatever_the_host_or_proxy_headers`、`test_enforce_refuses_only_what_the_list_does_not_hold`（enforce 由面板切；本體 §8.8 #119） |
| 2 | `test_rejects_bad_origins_even_if_host_or_proxy_headers_are_spoofed`（9） | `test_enforce_refuses_bad_origins_whatever_the_host_or_proxy_headers`（同 9 種＋Kelvin） |
| 3 | `test_preflight_is_limited_to_explicitly_trusted_origins` | §8.8 #42（沒有 preflight）：`test_no_cors_header_in_either_mode` |
| 4 | `test_trusted_origin_still_requires_token_and_exposes_session_header` | `test_a_wrong_token_never_learns_the_policy`；`Expose-Headers` 不適用（§8.8 #42） |
| 5 | `test_misconfigured_allowlist_fails_closed_even_without_origin`（4） | `test_what_a_policy_may_not_be`（PUT 422）；檔案裡的同樣值：`test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one`（帶不帶 Origin 都 503） |
| 6 | `test_misconfigured_allowlist_prevents_service_start` | §8.8 #120（不拒絕啟動）：`test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one` |
| 7 | `test_default_cors_does_not_reflect_untrusted_origins_on_other_routes` | `test_readiness_and_the_management_api_ignore_the_policy`（HA 沒有 CORS，§8.8 #42） |
| 8 | `test_non_headscale_rejects_trailing_dot_allowlist` | `test_what_a_policy_may_not_be`、`test_anything_else_is_no_origin` |

### `packages/mcp-admin-core/tests/test_origin_report_only.py`（16 案）

| # | PaaS 案例 | HA |
|---|---|---|
| 1 | `test_mode_origin_method_matrix`（4 模式×6 情況×4 方法） | `test_report_only_answers_every_request_as_without_the_check`（5 產品×9 情況×9 請求）、`test_enforce_refuses_only_what_the_list_does_not_hold`；「沒設」「空字串」兩種模式：§8.8 #120（沒有環境變數；沒有檔案＝report-only，檔案裡的空模式是壞檔） |
| 2 | `test_report_only_hands_would_deny_requests_to_the_pre_136_cors_unchanged` | §8.8 #42：HA 的對照組是「同一個請求不帶 Origin」：`test_report_only_answers_every_request_as_without_the_check` |
| 3 | `test_allowed_origin_preflight_outside_the_mcp_scope` | §8.8 #42：`test_no_cors_header_in_either_mode` |
| 4 | `test_allowed_and_absent_origins_are_identical_in_both_modes_at_the_middleware` | `test_enforce_refuses_only_what_the_list_does_not_hold`（清單內與沒帶的 enforce 前後相同） |
| 5 | `test_report_only_logs_one_would_deny_line_to_stdout_and_ring_buffer_without_secrets` | `test_report_only_answers_every_request_as_without_the_check`（每個情況一行）、`test_a_hostile_origin_value_cannot_inject_or_leak_into_the_line`；Logs 頁 ring buffer：§8.8 #121（HA 只有 add-on log） |
| 6 | `test_would_deny_lines_share_the_rate_limit` | `test_one_line_per_origin_then_twenty_a_minute_per_profile_then_one_summary`（§8.8 #121） |
| 7 | `test_logging_failure_never_blocks_a_report_only_request` | `test_a_line_that_cannot_be_written_never_changes_the_answer` |
| 8 | `test_non_mcp_routes_ignore_the_mode` | `test_readiness_and_the_management_api_ignore_the_policy` |
| 9 | `test_startup_line_names_mode_allowlist_size_and_env`（7） | §8.8 #120（沒有啟動時的 INFO 行，第 4 節 s） |
| 10 | `test_invalid_mode_fails_startup_validation_without_echoing_the_value`（13） | `test_what_a_policy_may_not_be`（模式的 6 種寫法 422）；檔案裡的 `Enforce`：`test_an_unusable_policy_file…`（WARNING 不含檔案內容） |
| 11 | `test_invalid_mode_stops_the_lifespan_before_any_config_write` | §8.8 #120（不適用：HA 照常服務，檢查從不寫檔） |
| 12 | `test_invalid_mode_at_runtime_fails_closed_like_an_invalid_allowlist`（2） | `test_an_unusable_policy_file…`、`test_a_policy_file_changed_behind_the_add_ons_back_is_read_again` |
| 13 | `test_headscale_shared_layer_always_enforces`（4） | `test_headscale_keeps_only_claude_ai_and_has_no_policy`（§8.8 #9） |
| 14 | `test_headscale_product_returns_403_with_report_only_set` | 同上 |
| 15 | `test_real_uvicorn_exits_3_on_an_invalid_mode_and_serves_with_a_valid_one` | 不適用（§8.8 #120：不拒絕啟動） |
| 16 | `test_real_uvicorn_product_app_exits_3_on_an_invalid_mode` | 不適用（同上） |

### `packages/mcp-admin-core/tests/test_origin_denial_log.py`（13 案）

| # | PaaS 案例 | HA |
|---|---|---|
| 1 | `test_denied_origin_logs_one_line_to_stdout_and_ring_buffer_without_path_or_secrets` | `test_enforce_refuses_only_what_the_list_does_not_hold`（deny 行）、`test_a_hostile_origin_value_cannot_inject_or_leak_into_the_line` |
| 2 | `test_reason_codes_and_normalized_origins`（8） | `test_reason_codes_and_rendered_origins`（同 8 種） |
| 3 | `test_allowed_absent_and_non_mcp_origins_produce_no_line` | `test_readiness_and_the_management_api_ignore_the_policy`；清單內與沒帶的沒有紀錄：`test_report_only_answers…` |
| 4 | `test_malicious_origin_values_are_escaped_truncated_and_cannot_inject`（8） | `test_a_hostile_origin_value_cannot_inject_or_leak_into_the_line`（同 8 種＋`Bearer <token>`，兩種模式） |
| 5 | `test_sanitizer_escapes_everything_outside_printable_ascii` | `test_the_sanitizer_escapes_everything_outside_printable_ascii` |
| 6 | `test_duplicate_shows_at_most_four_values` | `test_duplicates_show_at_most_four_values_each_escaped_once` |
| 7 | `test_headscale_env_keeps_its_legacy_trailing_dot_rendering` | 不適用（§8.8 #9：HA Headscale 原字串比對、不記） |
| 8 | `test_one_line_per_origin_per_interval_global_cap_then_one_summary` | `test_one_line_per_origin_then_twenty_a_minute_per_profile_then_one_summary`、`test_a_profiles_flood_never_holds_back_another_profiles_lines`（§8.8 #121） |
| 9 | `test_state_is_bounded_under_a_flood_of_distinct_origins` | `test_the_state_stays_bounded_under_a_flood_of_distinct_origins`（另驗帳號數有界） |
| 10 | `test_summary_is_flushed_when_the_window_ends_without_new_rejections` | `test_the_summary_is_written_when_the_window_ends_without_another_line` |
| 11 | `test_logging_failure_never_changes_the_response` | `test_a_line_that_cannot_be_written_never_changes_the_answer` |
| 12 | `test_duplicate_values_are_escaped_exactly_once` | `test_duplicates_show_at_most_four_values_each_escaped_once` |
| 13 | `test_url_credentials_in_a_malformed_origin_are_masked_without_the_global_record_factory` | `test_a_url_shaped_malformed_origin_shows_only_its_origin_and_which_parts_it_had`、`test_a_hostile_origin_value…` |

### `packages/mcp-admin-core/tests/test_origin_p3.py`（18 案）

| # | PaaS 案例 | HA |
|---|---|---|
| 1 | `test_vary_lists_origin_at_most_once_on_every_mcp_response`（24） | §8.8 #42（沒有 CORS，不加 `Vary`）：`test_no_cors_header_in_either_mode`；回應標頭和不帶 Origin 的相同：`test_report_only_answers…` |
| 2 | `test_allowed_origin_actual_request_has_exactly_one_origin_in_vary` | 不適用（§8.8 #42） |
| 3 | `test_vary_helper_keeps_existing_tokens_and_handles_star_and_separate_lines` | 不適用（HA 沒有 CORS 中介層） |
| 4 | `test_normalize_origin_rejects_non_ascii_instead_of_case_folding`（6） | `test_anything_else_is_no_origin`（5 種非 ASCII）、`test_an_origin_is_normalized_as_paas_does`（ASCII 大小寫） |
| 5 | `test_kelvin_sign_does_not_match_an_ascii_allowlist` | `test_enforce_refuses_bad_origins_whatever_the_host_or_proxy_headers`（清單有 `https://k.example`） |
| 6 | `test_malformed_non_url_values_never_appear_verbatim_in_the_log`（9） | `test_a_non_url_value_never_shows_verbatim`（7 種）、`test_any_other_malformed_origin_shows_a_summary_only` |
| 7 | `test_malformed_summary_shows_length_and_character_classes` | `test_a_non_url_value_never_shows_verbatim`（`len=`） |
| 8 | `test_malformed_summary_keeps_a_recognisable_scheme_prefix_only` | 同上（`ftp`、`javascript:`） |
| 9 | `test_url_shaped_malformed_values_log_only_scheme_host_port_and_flags` | `test_a_url_shaped_malformed_origin_shows_only_its_origin_and_which_parts_it_had` |
| 10 | `test_duplicate_header_values_also_summarise_non_url_shapes` | `test_duplicates_show_at_most_four_values_each_escaped_once` |
| 11 | `test_end_to_end_log_line_has_no_raw_malformed_text`（4） | `test_a_hostile_origin_value_cannot_inject_or_leak_into_the_line` |
| 12 | `test_url_shaped_malformed_origin_logs_only_normalised_origin_and_flags`（16） | `test_a_url_shaped_malformed_origin_shows_only_its_origin_and_which_parts_it_had`（13 種；沒搬的 3 種是 query 的其他寫法） |
| 13 | `test_url_shaped_origin_without_a_parsable_host_falls_back_to_the_non_url_summary`（7） | `test_any_other_malformed_origin_shows_a_summary_only` |
| 14 | `test_url_shaped_origin_with_overlong_host_is_truncated_and_leaks_nothing` | `test_an_overlong_host_is_cut_and_shows_nothing_of_it` |
| 15 | `test_url_shaped_origin_with_control_characters_gets_the_non_url_summary`（5） | `test_any_other_malformed_origin_shows_a_summary_only`（4 種） |
| 16 | `test_duplicate_header_renders_each_url_shaped_value_without_secrets` | `test_duplicates_show_at_most_four_values_each_escaped_once` |
| 17 | `test_headscale_legacy_host_rule_is_kept_for_the_summary` | 不適用（§8.8 #9） |
| 18 | `test_decision_is_unchanged_malformed_url_shapes_are_still_denied`（4） | `test_anything_else_is_no_origin`、`test_enforce_refuses_bad_origins…` |

### 其他

| 檔 | 案例 | HA |
|---|---|---|
| `test_origin_product_children.py` | `test_origin_boundary_with_real_product_and_two_profiles`（root_path×7 產品×2 模式） | `test_every_profile_takes_the_one_policy_and_its_lines_name_the_profile`（預設帳號＋B，各自的子程式）、`test_report_only_answers…`／`test_enforce_refuses_only…`（5 個產品）；root_path 不適用（HA 8081 沒有前綴）；真子程式由 HM-16 的容器探針涵蓋 |
| `test_origin_root_path.py` | 5 案 | `paas-test-mapping.md` 已有歸屬（#1 照它寫「HA：`tests/test_origin_policy.py`」：enforce 對所有方法：HA 先方法檢查，PUT、OPTIONS 等照今天 405，§8.8 #118；#2 §8.8 #42；#3～#5 HM-10、HM-08） |
| `apps/headscale/tests/test_origin_security.py` | 14 案 | PaaS Headscale 自己的邊界（清單是自己的管理網址、管理 API 跨來源寫入同一份清單、登入）：§8.8 #9（HA Headscale 只放 `https://claude.ai`，既有 `tests/test_mcp_contract_freeze.py` 的 Headscale 例外與本片 `test_headscale_keeps_only_claude_ai_and_has_no_policy`）；管理面不適用（§8.8 #11：Ingress＋HA 角色） |

面板沒有 PaaS 對應（PaaS 用環境變數）：node 與 Playwright 的案例都是 HA 自己的。

## 7. 臨時突變（拋棄式複本；`evidence-HM-27/mutations/`）

**Python**（`git archive 0bf5d19` 的複本，git 不收的 `.venv`、`apps/*/.venv`、`apps/n8n/node_modules`、`packages/mcp-admin-ui/dist` 與
`node_modules` 連到 clone 的；`tools/py_mutate.py`，環境同全套（`ha_env.sh`，不帶 `SUPERVISOR_TOKEN`），共用鎖下一次跑完；先跑不改的基準，
每個突變只改一處、跑 `-x`、跑完還原並核對 SHA-256；`mutations/python/summary.json`）：

**25 個全部擋下**（每個都是測試失敗、exit 1；P20、P24 不跑，見表下）。每個突變的完整輸出在 `mutations/python/<id>.log`。

| # | 突變 | 檔 | 結果 | 第一個失敗的測試（`-x`） |
|---|---|---|---|---|
| P00 | 基準（不改） | — | 通過（167 案、12.2 秒：`test_origin_policy.py` 150＋形狀比對 17） | — |
| P01 | report-only 也擋 | `origin_policy.py` | 擋下 | `test_report_only_answers_every_request_as_without_the_check[odoo]` |
| P02 | enforce 什麼都不擋 | `origin_policy.py` | 擋下 | `test_enforce_refuses_only_what_the_list_does_not_hold[odoo]` |
| P03 | Origin 不正規化、照原字串比 | `origin_policy.py` | 擋下 | `test_report_only_answers_every_request_as_without_the_check[odoo]` |
| P04 | 兩個以上 Origin 各自在清單內就放行 | `origin_policy.py` | 擋下 | `test_report_only_answers_every_request_as_without_the_check[odoo]` |
| P05 | 不記 decision 行 | `origin_policy.py` | 擋下 | `test_report_only_answers_every_request_as_without_the_check[odoo]` |
| P06 | 紀錄不帶帳號（寫死 default） | `origin_policy.py` | 擋下 | `test_a_profiles_flood_never_holds_back_another_profiles_lines` |
| P07 | 所有帳號共用一個時間窗（PaaS 的整台節流） | `origin_policy.py` | 擋下 | `test_a_profiles_flood_never_holds_back_another_profiles_lines` |
| P08 | 時間窗放寬到 200 行 | `origin_policy.py` | 擋下 | `test_one_line_per_origin_then_twenty_a_minute_per_profile_then_one_summary` |
| P09 | 壞檔全部放行 | `origin_policy.py` | 擋下 | `test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one[not JSON-{-384]` |
| P10 | 檢查移到方法檢查（405）之前 | `gateway.py` | 擋下 | `test_enforce_refuses_only_what_the_list_does_not_hold[odoo]` |
| P11 | Bearer 改照政策走 | `gateway.py` | 擋下 | `test_the_bearer_path_still_refuses_any_origin_and_writes_no_line` |
| P12 | Headscale 也套政策（閘道兩條規則一起給：啟動失敗） | `origin_policy.py` | 擋下 | `test_headscale_keeps_only_claude_ai_and_has_no_policy` |
| P13 | 開關關的產品也套政策 | `run_product.py` | 擋下 | `test_switched_off_the_policy_does_not_exist[odoo]` |
| P14 | 過期的 If-Match 也存得進去 | `profile_admin.py` | 擋下 | `test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one[not JSON-{-384]` |
| P15 | 重送不照收據回答 | `profile_admin.py` | 擋下 | `test_the_route_reads_and_saves_through_the_shared_pipeline` |
| P16 | 重複的來源收下 | `origin_policy.py` | 擋下 | `test_what_a_policy_may_not_be[body14]` |
| P17 | ETag 對檔案、不對政策 | `origin_policy.py` | 擋下 | `test_the_etag_names_the_policy_not_the_file` |
| P18 | 別的權限位元的檔也用 | `origin_policy.py` | 擋下 | `test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one[another mode bit set…]` |
| P19 | 檔案寫成 0644 | `origin_policy.py` | 擋下 | `test_the_policy_is_saved_beside_the_index_never_in_the_default_state` |
| P20 | （不跑：等價）紀錄裡清單外的來源不再過 sanitize | `origin_policy.py` | 不跑 | 見下 |
| P21 | 畸形 Origin 照原樣寫進紀錄 | `origin_policy.py` | 擋下 | `test_reason_codes_and_rendered_origins[origins0-malformed-https…]` |
| P22 | 第 ⑤ 步收多出來的鍵 | `origin_policy.py` | 擋下 | `test_what_a_policy_may_be` |
| P23 | 第 ⑤ 步每條路由都用帳號名稱的形狀 | `profile_router.py` | 擋下 | `test_enforce_refuses_only_what_the_list_does_not_hold[odoo]` |
| P24 | （不跑）讀檔不看是不是一般檔 | `origin_policy.py` | 不跑 | 見下 |
| P25 | 跟著連結讀 | `origin_policy.py` | 擋下 | `test_a_policy_file_changed_behind_the_add_ons_back_is_read_again` |
| P26 | 寫入前不比對簽章（讀與寫之間被換掉照樣蓋過去） | `origin_policy.py` | 擋下 | `test_a_save_never_replaces_a_file_changed_after_it_was_read` |
| P27 | 額外帳號不檢查 | `profile_runtime.py` | 擋下 | `test_every_profile_takes_the_one_policy_and_its_lines_name_the_profile` |

不跑的兩個：P20 是等價突變（清單外的來源已經正規化成可印的 ASCII，`sanitize_origin_text` 不會改它）。P24 只拿掉「一般檔」的檢查：目錄仍然不能用（nlink 不是 1）、socket 打不開、沒有寫入端的 FIFO 讀到空的（不是 JSON）；只有「讀的當下有寫入端送進一份政策的 FIFO」結果不同，這是同 uid 的競態（DQ-37：同 uid 本來就能直接寫那個檔），這裡的測試做不出來。P26 起初也以為做不出來，後來補了一案（第 5 節）。

前兩次跑作廢（`mutations/python-invalid-env/`，留作紀錄）：第一次的複本沒有 `apps/*/.venv`（`products.child_spec` 拒絕起子程式），
基準在第一個起 runtime 的案例就逾時失敗，P01～P03 的「擋下」都是同一個失敗，跑到一半停掉；第二次少了 `apps/n8n/node_modules`，
基準在 n8n 的開關關案例失敗，腳本在基準失敗時就停（這是第一次之後加的檢查），沒有跑任何突變。上表是補齊連結後的第三次。

**面板**（`git archive 0e445e9` 的 `packages/mcp-admin-ui` 與它要的幾個根目錄檔，`node_modules` 用連結；`tools/mutate.py` 照 HM-12 面板：
改 `src/` 的先 build 再跑、跑完 build 回原樣；`mutations/panel/summary.json`）：**16 個全部擋下**。

| # | 突變 | 檔 | 擋下的測試（node／Playwright `single` 失敗數） |
|---|---|---|---|
| U01 | 開關關也畫卡片（`originApplies` 不看 `api.profile`） | `app.js` | PW 1：`switched off: no Origin card and no request for it…` |
| U02 | Headscale 也畫卡片 | `app.js` | PW 1：`Headscale switched on: no card and no request…` |
| U03 | 存檔帶帳號（送 `X-MCP-Profile`） | `api.js` | node 1（`save: PUT with a fresh CSRF value…`）、PW 2 |
| U04 | 422 `origin_policy_invalid` 不放掉識別紀錄 | `api.js` | node 1、PW 1（`the add-on refuses the list (422)…`） |
| U05 | 不送 If-Match | `api.js` | node 2、PW 6 |
| U06 | 重複的來源面板不擋 | `api.js` | node 2、PW 1（`what the panel can tell is wrong…`） |
| U07 | 409 之後不重新讀取 | `app.js` | PW 1（`changed by another administrator meanwhile…`） |
| U08 | 沒有待確認卡 | `app.js` | PW 2 |
| U09 | 重送換一個新的 key | `api.js` | node 1、PW 1（`a lost answer…`） |
| U10 | 只有預設帳號畫卡片 | `app.js` | PW 1（`switched on, an additional profile shown…`） |
| U11 | 壞檔當成預設值顯示 | `app.js` | PW 1（`an unusable policy file…`） |
| U12 | fixture 收下畸形來源 | `fixtures/server.mjs` | PW 1：形狀比對 `origin-policy` 情境 |
| U13 | 不認得的模式也顯示 | `api.js` | node 1（`read: an unusable file is shown as such; an answer of any other shape is not shown`） |
| U14 | 識別紀錄不留請求內容（重送送空清單） | `operation-identity.js` | node 2、PW 4 |
| U15 | 確認框不說 enforce 會擋什麼 | `app.js` | PW 1 |
| U16 | fixture 開關關也回 origin 路由 | `fixtures/server.mjs` | PW 1：形狀比對開關關情境 |

## 8. 開關關時逐位元不變的比對

- **面板**（repo 外的腳本，不 commit：`evidence-HM-27/tools/compare.mjs`，是 HM-12 面板審查版的腳本多一個動作）：基準＝`git archive 165dbaf` 取出的
  `packages/mcp-admin-ui` 與它要的檔，自己 build（`dist/assets/app.js` `b0f7e7ad…`，和 HM-12 面板筆記記的相同）；新版＝本分支
  （`559aa02f…`）。12 種設定×5 頁×動作，比 `document.body.innerHTML`、fixture 的 `calls`、瀏覽器送出的每個 `/api/` 請求的方法、路徑與
  標頭名稱。多的動作 `originRecord`：分頁的 sessionStorage 留著開通版本寫的 Origin 政策識別紀錄（`…:origin-policy`），重新載入。
  **276 個比較 0 差異**（`compare/switched-off-compare.log`）。
- 腳本有效：把「開關關也畫卡片」（`originApplies` 不看 `api.profile`）放進一份複本，同一個比對找到 **60 個差異**，都在「連線與權杖」頁
  （12 種設定×5 個動作；`compare/switched-off-compare-sensitivity.log`）。
- **Python**：`test_switched_off_the_policy_does_not_exist` 對 8 個產品（含 n8n、OpenDesign、Headscale）：磁碟上留一份「全部擋」的政策檔，
  `PolicyFile`、`OriginPolicy` 被換成一建立就失敗，照樣啟動、密鑰網址照今天（Headscale 照它的規則）、路由是今天的未知操作（GET、沒本體的 PUT
  404，帶本體的 PUT 照今天 400）、目錄項目與那個檔的位元組不變、沒有任何紀錄。HM-01 的黃金回歸與兩個契約凍結照過（第 9 節）；
  `tests/test_router_passthrough.py`、`tests/test_profile_routing.py` 開通後照 HM-01 的案例跑，預設 report-only 也逐位元照過。
- 這兩個比對只在本機；CI 的守門是上面的 Python 測試與 Playwright 的開關關、Headscale 兩案。

## 9. 本機檢查（2026-11-17，一般使用者 uid 1000；`ha_env.sh` 的 TMPDIR，每次跑完刪掉；pytest 都排在共用鎖後面）

照規則沒做到的兩處，照實記下：`/tmp/ha-mp-LmPgUv` 是用驗過的變數（`rm -rf "$T"`）刪的，其餘都用完整的字面路徑；有一次
`pytest --co`（只收集、沒有跑任何測試）沒有排共用鎖。

| 檢查 | 結果 |
|---|---|
| 全套 pytest（`tests`，`0e445e9`；`logs/full-suite.log`、`full-suite.xml`） | 6,389 案：6,382 通過、7 失敗、0 skip，2,086 秒（34 分 46 秒）。失敗的 7 案都是要 root 的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5），基準本來就會失敗；沒有新的失敗 |
| `tests/test_origin_policy.py`（`0bf5d19`，加了 P26 那案；`logs/origin-policy-0bf5d19.log`） | 150 案全過，8.9 秒。`0bf5d19` 只在這個檔加一個測試函式，所以全套沒有重跑；本筆記與威脅模型只改文件，沒有測試讀它們 |
| pytest 增量（全套的 junit） | `0e445e9`：+152 案（新檔 149、形狀比對 3 個新情境），呼叫時間合計約 9.4 秒；`0bf5d19` 再 +1 案 |
| `npm test --prefix packages/mcp-admin-ui` | 99 案全過（基準 88 案） |
| `npm run build`＋`node tests/build-closure.mjs` | PASS；`dist/assets/app.js` `559aa02f…`、`app.css` `c8b43515…`（沒變） |
| Playwright 全套（`single`＋`profiles-on`，照 CI） | 150 案全過，4.8 分鐘（`logs/green-pw-full-1.log`；基準 135 案）；新 spec 12 案、parity 新 3 個情境 |
| `packaging/validate.py`（ci-venv 的 Python 3.13.15，不加 `-I`） | PASS（`logs/packaging.log`） |
| packaging unittest（CI 的做法：離線暫存 venv） | Ran 203、OK（skipped=5） |
| `scripts/tool_inventory.py` | exit 0 |
| HM-00 對照腳本（repo 外 `wave0/hm00-check/check_hm00.py`） | C2（122 列）、C4、C5、C8、C9 過；C1（diff 不只 docs/）是本片的性質；C3、C6、C7 的失敗基準 `165dbaf` 就有（FM-154～156 沒對到、PaaS main 新增的測試檔、契約第 2.4 節兩個測試名稱被當成代碼），本片沒有新增問題 |

### 9.1 只在 CI 跑的測試

- 本片新增與改過的測試都在本機跑過；沒有只在 CI 跑的新測試。
- 已知要 root、本機一定失敗的既有案例（`test_owned_executable.py` 1、`test_profile_store.py` 1、`test_restore_detection.py` 5）不受影響；
  CI 以 root、0 skip 跑全套。
- Node：本機 v26.12.1（`ha_env.sh`），Playwright 1.61.1（Chromium headless shell 1228；從同版本的 HM-12 面板 clone 複製 `.local-browsers`，
  等同 `npm run browser:install`）。

### 9.2 `checks` 秒數

開 PR 後補（前：`claude-delivery` 最近一個 PR run 的 `checks`；後：本片 PR 的 `checks`）。本機增量：Playwright 約 +34 秒（新 spec 12 案、parity
3 個情境）；node 約 +0.15 秒；pytest +153 案、約 +9.5 秒（junit 的呼叫時間）。

## 10. PaaS 變動清單（本機唯讀 PaaS repo；`git log --oneline 69ac425..origin/main -- <相關檔>`，`origin/main`＝`48f394d`）

查的路徑：`packages/mcp-admin-core/mcp_admin_core/origin_security.py`、`…/app.py`、`docs/security/mcp-origin-policy.md`、
`packages/mcp-admin-core/tests/test_origin_*`、`apps/headscale/headscale_mcp_admin/origin_security.py`、`apps/headscale/tests/test_origin_security.py`。

- 只有 `app.py` 有兩個 commit：`3b135ca`（所有產品加 JSON 結構守門）、`e6971c0`（預算預設值、啟動時建立）——都是 #155，HM-31 已對齊；
  Origin 的程式、文件與測試 pin 之後沒變。
- 只用 `git log`、`show`、`ls-tree`、`diff`；沒有 fetch、checkout 或寫入。

## 11. 本片用到的決策（`docs/multi-profile/decisions.md`）

- DQ-11 (a)（2026-11-14 使用者採用）：本片照做；DQ-11 列已補實作。第二問沒有定（第 14 節）。
- DQ-40 (a)（2026-11-14）：Bearer 帶 Origin 的 403、固定本體等既有規則不變。
- DQ-37 (a)：同 uid 不是安全邊界（政策檔的外改寫進威脅模型第 3 節）。
- 計畫 §3.3、§7.1、§7.2 第 10 點：受開關管；開通後預設帳號看得到的變化只有「密鑰網址清單外的來源多記一行 would_deny，不擋」。

## 12. 預檢結果

下面是本筆記之前（`0bf5d19`）的結果；本筆記 commit 之後再跑一次（第 12.1 節）。

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools …/hm01/gitleaks-tools --repo . --base 165dbaf --head HEAD --full` | `0bf5d19`：OK，0 命中（gitleaks 8.28.0，pin、驗過；7 個 commit，另掃 HEAD 的樹與整段歷史；`logs/precheck-secret-0bf5d19.log`） |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 165dbaf` | `0bf5d19`：OK。`runtime-patches.json` 178、`runtime-sources.json` 70、`docs/tool-surface.json` 159 個摘要 0 漂移、0 缺；改到的列管檔 8 個（新模組 1、既有 7）都隨帳本更新；沒有未列管的執行檔（`logs/precheck-ledger-0bf5d19.log`） |
| 雙向控制字元 | `evidence-HM-27/tools/bidi_scan.py`（HM-12 面板的腳本；逐 commit：碰過的檔全文、新增的行、commit 訊息） | `0bf5d19`：7 個 commit、25 個檔：U+202A～202E、U+2066～2069 合計 0；U+200E、U+200F、U+061C 也是 0（`logs/bidi-0bf5d19.log`） |

### 12.1 本筆記 commit 之後

本筆記 commit 之後在最後的 HEAD 再跑兩個預檢與雙向控制字元掃描，結果記在交給主對話的回報（PR 說明照抄）：本筆記不能記自己
commit 之後的結果。

## 13. 交給後面的片、還沒解決的事

- **HM-18（DOCS、契約定稿）**：產品 DOCS 寫 Origin 清單（預設 report-only 不擋、怎麼在面板切 enforce、`decision=would_deny`／`deny` 的格式與
  怎麼查、紀錄不證明是誰送的、預設清單含 `https://claude.ai` 所以 Claude.ai 送它時不會留紀錄）；每個產品的 CHANGELOG 與 `upgrade-notes.yaml`
  在開通時寫計畫 §7.2 第 10 點；`docs/operations/clients.md` 的「Claude.ai 不能帶標頭」已過時（FM-123）。`paas-test-mapping.md` 與
  `deviation-trace.md` 由 repo 外的產生器產生：前者 HM-27 兩列的「暫定名」與後者的 T-24、FM-73 列，下次重產時照本筆記第 6 節更新
  （本片沒有改產生器的規格）。
- **HM-19b（HAOS 實測）**：S14 用 echo 端點實測 Claude.ai 送不送 Origin、送什麼（T-27「記下 Claude.ai 送的 Origin」）；預設清單含
  `https://claude.ai`，Claude.ai 送它時 would_deny 看不到，要看實際值得靠 echo 端點，或暫時把清單清空（只記不擋）再看紀錄。實機看
  add-on log 裡 would_deny 行的格式與節流。
- **S14／DQ-11 第二問**：實測後由代理問使用者「Claude.ai 送 `https://claude.ai` 時，Bearer `/mcp` 要不要精確放行」。本片 Bearer 照舊一律 403；
  若要放行，改在 `gateway.serve` 的 Bearer 分支，另開一片、要獨立審查。
- **HM-25（n8n）**：`apps/n8n/run.py` 改用 ProfileManager 時，政策自動套上（`origin_policy.applies`）；n8n 的開通測試要加 report-only／enforce 各一案。
- **HM-26（Headscale）**：Headscale 照舊沒有政策；要不要在面板顯示「固定只放 `https://claude.ai`」、要不要照 PaaS 記 deny 行，交 HM-26 與它的
  獨立安全審查。
- **契約第 9 節的列號**：本片從 #118 起編（#118～#122）。其他還沒合併、也從 #118 起編的 PR（任務提到 #108、#112 可能先合併、用掉
  #118～#123）先合併時，**後合併的一方 rebase 後往後重編**，並同步契約第 2.6、4.1、4.2 節、威脅模型、驗收矩陣與本筆記裡的列號。
- **帳本**：`runtime-patches.json` 動了 8 個項目（新模組 1、列管檔 7）；後合的一方 rebase 後照 JSON 結構重算 SHA-256（不要用 `--write` 批次重寫）。
- **gateway.py 的合併順序**（計畫 §12.2）：HM-27 在 HM-13c 之後、HM-15 之前；本片只在 `make_apps` 加一個選項與一處呼叫。

## 14. 要使用者決定的事

- 本片範圍內：**沒有**。計畫沒寫的細節都照 PaaS 或取最保守（第 4 節），交審查一起看；其中「面板放在既有頁面的一張卡片、不是新頁面」
  （第 4 節 q）是照字面「設定頁」的偏離，請審查確認。
- **還沒解決、要使用者的**：DQ-11 第二問（Bearer `/mcp` 要不要精確放行 `https://claude.ai`）仍待 S14 實測後問。`decisions.md` 第 4 節的待辦寫
  「最晚 HM-27 合併前」，但 S14 在 HM-03b 或 HM-19b，HM-19b 排在 HM-27 之後（計畫 §12.2）：這個期限照現況排不到；本片沒有改它，
  交主對話與使用者決定「HM-27 先合、第二問延到 S14 之後」或其他安排。

## 15. commit（`165dbaf` 之後）

| commit | 標題 |
|---|---|
| `4ba896b` | test(origin): pin the secret path's add-on-wide Origin allowlist, report-only by default (HM-27) |
| `00cbbab` | feat(origin): the secret path's add-on-wide Origin allowlist, report-only by default (HM-27) |
| `ec7381a` | test(ui): pin the Origin policy card on the connections page (HM-27) |
| `983e8a2` | feat(ui): the Origin policy card on the connections page (HM-27) |
| `434bcdf` | docs(multi-profile): settle the secret path's Origin allowlist in the contract (HM-27) |
| `0e445e9` | test: pin make_apps' and ProfileRuntime's origin_policy option (HM-27) |
| `0bf5d19` | test(origin): a save never replaces a policy file changed after it was read (HM-27) |
| （本筆記） | docs(provenance): the HM-27 Origin allowlist slice |

commit 身分都是 woowtech；英文標題、繁中內文；沒有 Co-Authored-By、Generated with 或任何 AI 署名。
