# HA 多帳號 HM-23 provenance：EMQX 開通的功能 PR（2026-11-19）

## 結論

- **本片是 EMQX 的功能 PR**（計畫 §9 EMQX 列、§12.3 HM-21～HM-26）。`features.MULTI_PROFILE_PRODUCTS` 維持空集合，沒碰 `addons/`。
  之後 EMQX 的升版 PR 只要把 `'emqx'` 加進開關與開關釘選（`SWITCHED_ON`，審查 S-2）、升版號（版號資料與它們在帳本裡的摘要）就開通；
  第 4 節把 EMQX 打開實跑過，證明這件事。
- **EMQX 不需要自己的執行期程式**（第 3 節）。對照 Odoo 的產品專屬部分逐項看過：
  - EMQX 的 token 不綁後端身分。EMQX 的帳號就是它的 API key（秘密欄位），`identity_fields.TOKEN_ROTATING` 沒有 EMQX。
    所以 `products.IDENTITY_BOUND` 與面板的 `identityBound` 都不加 EMQX。
  - 政策只經子程式的啟動環境（`EMQX_MCP_READONLY`、`EMQX_MCP_DISABLED_TOOLS`）到該帳號的子程式；存政策時
    `configuration.launch_revision` 已把 EMQX 的政策算進去，只重起那個帳號的子程式。
  - 子程式不另外讀政策（DQ-27，照計畫建議）；停用的操作只在閘道擋。
  - 帳號上限（3）、子程式記憶體估計（160 MiB）、認證被拒的退避（EMQX 的 401 文字）、新來源要重填 `api_key` 與 `api_secret`
    （DQ-40 ⑨）、容器多帳號階段，都已經在通用程式裡涵蓋 EMQX。
- **新測試 `tests/test_emqx_multi_profile.py`**（兩案；真的 EMQX 子程式，每個帳號一個假 broker 與自己的 API key）：
  - 開通：三個子程式各自只認自己的 child bearer（每個子程式 14 種錯的寫法都 401，`tests/test_child_bearer.py` 的 `refusals`）；兩種接法，每把 token 只開到自己子程式的 session；
    沒有帳號持有的 token 回 HM-01 的 401／404；別帳號的 session 404；每個呼叫只到自己帳號的 broker、帶自己的 key（對角線；審查後改用健康檢查不打的工具，第 19 節）。
  - 政策各自：停用的工具在閘道與子程式都沒有；停用的操作只在閘道擋；子程式拿不到任何政策或 state 檔。
  - 存 B 的政策只重起 B 的子程式（新 PID、新政策）；預設帳號與 C 的 PID、啟動次數、環境、state 位元組都不變。
  - 開關關：同一份資料只起預設帳號；B、C 的 token 被開機守門撤銷，回 401／404；子程式的 bearer 矩陣照樣；存政策照舊重起預設帳號的子程式。
  - 受限帳號（沒有任何寫入授權）的子程式仍是 `READONLY=false`：混合工具要靠它註冊讀取操作。這是文件建議受限帳號用唯讀角色 key 的理由（UC-22）。
- **讓升版 PR 只動開關、開關釘選與版號**（第 4 節）：在拋棄式複本把 EMQX 打開跑相關測試，tests 有 78 個失敗、packaging 有 2 個；原因都是測試讀了 repo 的開關，
  不是程式錯。做法：`tests/switch_modes.py` 的 `switched_off` fixture，套在 25 個只測開關關的測試檔（或其中幾個測試）；
  `multi_profile_runtime(switch=False)` 改成每個產品都關（審查後 `test_monitor_cancel.py` 的 `run_until_sigterm` 也是）；
  開關釘選照舊是精確的集合（`SWITCHED_ON`，升版 PR 和 `features.py` 一起改一行；審查後改回，第 19 節），另加第二道「開通的產品版號至少 0.5.0、而且支援額外帳號」；
  `test_real_products.py` 的假後端在開通時綁私有位址、斷線等一個健康檢查間隔。改完再把 EMQX 打開跑一次（33 個檔 1,289 案）：只剩升版 PR
  本來就要改的 3 案（開關釘選要 EMQX 版號 0.5.0、`features.py` 的帳本摘要 2 案）與複本才有的 2 案（n8n 的 `node_modules` 是連結）；packaging 全過。
- **PaaS #153 對齊**（第 5、6 節；不受開關管，跟著 EMQX 下一版出去）：`match_topic` 的說明照 PaaS 逐字改；`emqx_prometheus_stats` 送
  `Accept: text/plain`、空的文字回 `EMQX_INVALID_RESPONSE`；超長或無法編碼的識別字送出前回固定的 `EMQX_DESTINATION_DENIED`。
  每個請求都經 `deps.EmqxHttp.request`，Accept 只收兩個固定值、請求選項只收四種。HM-01 黃金回歸 EMQX 的兩個 tools/list 摘要照檔頭規則更新；
  新的回答就是舊的回答只換掉兩段說明（逐位元核對，第 8 節）。
- **契約**：第 9 節加第 129、130 列（列號暫定，第 13 節）、#65 附註；第 1.2 節加 HM-23 一項；第 10 節一列。
- **HM-29 交來的 20 條連線**：EMQX 生效的後端並行連線上限是 4（`backend_policy` 的傳輸層），和 PaaS 的 `BrokerTransport` 相同；
  `lifespan.py` 寫的 20 從沒生效。本片只記進契約 #129，改不改交使用者（第 17 節）。
- **UC-22**：EMQX 的唯讀角色叫 `viewer`（REST API 只能 GET）。API key 角色在 EMQX Enterprise 5.4 的發行說明出現，5.9 起所有版本都有（第 15 節）。
- **檢查**（第 10～12 節）：開關關 52 個檔 1,972 案只有 1 案失敗（要 root 的既有案例），另兩個檔 163 案全過；開關開的複本 1,289 案只剩
  升版 PR 本來就要改的 3 案與複本才有的 2 案；#153 的測試先紅後綠（20 紅 → 29 綠）；五個突變都讓開通那案變紅；packaging 366 案 OK
  （開關開也 OK）；`validate.py` PASS；帳本預檢、秘密預檢都 OK。CI（root、0 skip）才是準。
  審查處理後重跑（第 19 節）：改到的三個檔與相關的 10 個檔 427 案全過；複本的對照 3 紅 4 綠如預期；packaging、`validate.py`、兩個預檢照舊過。
- **獨立審查**（第 19 節）：修正後通過。必修 MF-1（健康檢查讓「沒有 broker 被叫到」偶發紅）與建議 S-1、S-2、S-4 照改；
  S-3（和 HM-26 的同一套工具）要主對話選一套，本片不改；備註只改 N-2。
- **要使用者決定的事**：第 17 節。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-23 EMQX 開通（計畫 §12.3 HM-21～HM-26；工作量 M（4）；FM-92、FM-37、FM-45、FM-109） |
| 性質 | 功能 PR。受開關管的部分沒有新的執行期程式（只有測試與文件）；PaaS #153 的對齊不受開關管 |
| 分支 | `feat/ha-multiprofile-hm23-emqx-20261119`（clone `ha-mp-hm23-20261119`）；獨立審查處理完才 push（第 19 節），沒開 PR |
| 基準 | `claude-delivery` `c90b214`（#109 HM-16 的合併；2026-11-19 10:0x 再 fetch 一次，`claude-delivery` 沒動） |
| 對齊的 PaaS | GitHub 鏡像 `WOOWTECH/woow-mcp-server` main `5ef1046`（2026-11-18；只讀 GitHub API）：#153 合併 `5b84b5d`（`cd1ed89`、`4b4fd16`、`574c805`、`e59c9b2`、`fabb192`） |
| 同時在準備的片 | HM-18、HM-21、HM-22、HM-24、HM-25、HM-26（各自的 clone；本片只讀過它們的狀態，沒動） |
| 證據 | 這份筆記；腳本與 log 在本片的暫存區（用完刪除），結果寫在下面各節 |

## 2. 改了什麼、沒改什麼

| commit | 內容 |
|---|---|
| `e803d58` test(core) | 測試自己指定開關模式（第 4 節）：`tests/switch_modes.py`（新）；25 個既有測試檔加 `switched_off`（整個模組或單一測試）；`tests/multi_profile_runtime.py`（`switch=False` 是每個產品都關）；`tests/test_upgrade_zero_rewrite.py`（開關釘選改寫、加一案、零改寫那案關的一半）；`tests/test_real_products.py`（開通時的假後端位址與斷線等待）；`packaging/test_container_probe.py`、`packaging/test_container_acceptance.py`（各一處包進 `switched()`） |
| `b85722e` test(emqx) | `tests/test_emqx_multi_profile.py`（新，兩案） |
| `9635e09` test(emqx) | `tests/test_emqx_field_findings.py`（新，29 案；這個 commit 上是紅的，第 7 節） |
| `e991dbc` fix(emqx) | PaaS #153 的三個修正：`apps/emqx/vendor/emqx_mcp_server/` 的 `deps.py`、`errors.py`、`tools/_common.py`、`tools/cluster.py`、`tools/topics.py`；`tool_snapshot.py` 只重產 EMQX；帳本與釘選（第 9 節）；黃金回歸 EMQX 的兩個摘要（第 8 節） |
| `ee44bd5` docs(multi-profile) | `contract.md`（第 1.2 節、第 9 節 #129、#130 與 #65 附註、第 10 節）、`acceptance-matrix.md`（T-04、T-05、T-07、T-23、登記表三列、檔頭狀態）、`unreleased-changes.md`（E3 與 HM-23 一列） |
| `24df882` docs(provenance) | 本筆記 `docs/provenance/ha-multiprofile-HM-23-20261119.md` |
| `05bf35f` test(emqx) | 審查 MF-1、S-1：`tests/test_emqx_multi_profile.py`（健康檢查的請求不算、對角線換工具） |
| `938643c` test(core) | 審查 S-2：`tests/test_upgrade_zero_rewrite.py`（精確釘選 `SWITCHED_ON` 加第二道） |
| `98c9cb7` test(core) | 審查 S-4：`tests/test_monitor_cancel.py`（`run_until_sigterm(switch=False)` 是所有產品都關） |
| `83165b6` docs(multi-profile) | 審查之後：`acceptance-matrix.md`（檔頭狀態、登記表兩列）、`contract.md`（第 9 節說明段，審查備註 N-2） |
| 本筆記的審查處理 | 第 19 節，與結論、第 1、2、4、16、17、18 節跟著改的地方 |

沒改：任何版號、`addons/`、`features.MULTI_PROFILE_PRODUCTS`、`tests/conftest.py`、面板（`packages/mcp-admin-ui/`）、`products.py`（含
`IDENTITY_BOUND`）、`identity_fields.py`、`apps/runtime/*.py`、`apps/*/launch.py`（所以不重產 `tool-surface.md`；`tool-surface.json` 只動 #153
改到的五個檔的摘要與一個工具的簽章文字）、`docs/multi-profile/deviation-trace.md` 與 `paas-test-mapping.md`（repo 外的產生器重產）、
`decisions.md`（DQ-27 仍待定）。

## 3. EMQX 不需要產品專屬程式的理由（對照 Odoo）

| Odoo 的產品專屬部分 | 在哪 | EMQX |
|---|---|---|
| token 綁後端身分（換 url／database／username 換 token） | `products.IDENTITY_BOUND`、`identity_fields.TOKEN_ROTATING`（HM-12） | 不綁。EMQX 的帳號由 API key 決定（`api_key`、`api_secret` 都是秘密欄位），沒有身分欄位會換帳號；`TOKEN_ROTATING` 本來就沒有 EMQX。改 `url` 到別的來源要重填兩個秘密（DQ-40 ⑨），`identity_fields.URL_SECRETS` 已列、`tests/test_new_origin_secret.py` 已測 EMQX |
| 面板的換 token 提示 | `Hui/contracts.js` 的 `identityBound`（HM-12 面板） | 不加：不換 token，就沒有要提示的事；`tests/test_identity_fields.py` 要兩邊一致 |
| 每帳號一個子程式（審批 token 是行程全域） | `profile_runtime.ProfileRuntime`、`run_product`（通用） | 同一套；EMQX 的子程式沒有跨帳號的行程全域狀態，但照樣每帳號一個 |
| 政策進子程式 | Odoo 的四個寫入開關在啟動環境（`child_spec`） | `EMQX_MCP_READONLY`、`EMQX_MCP_DISABLED_TOOLS` 在啟動環境；`configuration.launch_revision` 把 EMQX 的政策算進去，存政策就重起那個帳號的子程式（`gateway.make_apps` 的 policy 存檔分支） |
| 子程序前置碼開開關的測試 | `tests/test_upgrade_zero_rewrite.py` 等 | 新測試用 `multi_profile_runtime`（同一個程序裡 monkeypatch 開關，repo 的開關不動） |
| 容器多帳號階段 | `packaging/container_profiles.py`（HM-16，通用） | 通用；`packaging/test_container_profiles.py` 的 fixture 本來就是 EMQX。開通的 EMQX 候選映像第一次跑它是在升版 PR 的建置 |
| 帳號上限、記憶體估計 | `profiles.EXTRA_PROFILE_LIMITS`、`CHILD_MEMORY_MIB` | 已有：3 個額外帳號、每個子程式估 160 MiB（HM-19c／升版 PR 實測再定） |
| 認證被拒的健康檢查退避 | `health.AUTH_REFUSED`（DQ-25） | 已有 EMQX 的 401 文字 |
| 回覆遮罩 | HM-08：本帳號秘密＋所有帳號 token | 同一套。PaaS EMQX 的全域秘密集合（FM-92）HA 不需要：每個子程式只知道自己帳號的 key（契約 #38） |

DQ-27（EMQX 子程式再擋一次政策）在 `decisions.md` 仍是待定，計畫建議「不做」，計畫 §9 也照這個寫。本片照建議做，沒有把政策檔或
`EMQX_MCP_DISABLED_OPERATIONS` 交給子程式，並用測試釘住（第 7 節的突變 M3、M5）。使用者要確認（第 17 節）。

## 4. 讓升版 PR 只動開關：測試自己指定開關模式

做法：在拋棄式複本（本 clone 的複本，venv 用連結）把 `features.py` 改成 `frozenset({'emqx'})`，跑兩批測試（都排在共用鎖後面）：

| 批次 | 選法 | 開關關（本 clone） | 開關開（複本） |
|---|---|---|---|
| A | `tests -k emqx` | 315 passed（3 分 38 秒） | **76 failed**、239 passed（4 分 27 秒） |
| B | 提到產品或開關的 68 個檔，去掉帶產品名的參數 | — | 8 failed、1,097 passed：要 root 的 2 案（既有）、`features.py` 改了所以帳本摘要對不上 2 案（升版 PR 本來就重算）、複本的面板 `dist` 是連結所以 `/` 回 503 的 2 案（複本才有）、開關釘選 1 案、`test_product_runtime_failure` 1 案 |
| packaging | `unittest discover -s packaging` | OK | 2 failed |

失敗的原因都是「測試讀了 repo 的開關」，不是程式錯：

| 類別 | 案數 | 例子 | 改法 |
|---|---|---|---|
| 子程式拒絕 loopback 的假後端（HM-20） | 44 | `test_emqx_retained_errors` 24、`test_protocol_clients` 4、`test_native_probe_separation` 4 | 這些測的是子程式本身，和開關無關：整個檔用 `switched_off` |
| 管理 API 沒帶 `X-MCP-Profile`（開通後 400） | 12 | 黃金回歸、兩個契約凍結、`test_profile_runtime` 3 | HM-01 那三個檔整檔用 `switched_off`（`test_router_passthrough.py` 本來就在開通下再跑它們）；其他同 |
| Supervisor 替身不收開通後的選項 | 11 | `test_product_ha_role` 7、`test_role_lifecycle` 3 | 整檔用 `switched_off` |
| 測開關關結果的測試 | 5 | `test_router_passthrough` 的兩案（`multi_profile_runtime(switch=False)` 原本是「不改 repo 的開關」） | `switch=False` 改成每個產品都關；其他三案加 `switched_off` 參數 |
| 子程式環境快照（開通多 `WOOW_MCP_DENY_LOOPBACK`） | 3 | `test_child_port_param`、`test_child_bearer` 的環境鍵 | 整檔用 `switched_off`（開通時的那個變數由 `tests/test_backend_loopback.py` 測） |
| 存檔規則（開通後新來源要重填秘密 422） | 2 | `test_connection_patch`、`test_saved_destinations` 一案 | `switched_off` |
| 開關釘選（`MULTI_PROFILE_PRODUCTS == frozenset()`） | 1 | `test_upgrade_zero_rewrite.py` | 改成「開通的產品支援額外帳號、版號至少 0.5.0（DQ-32）」，並加一案反向對照（0.4.99 被擋、0.5.0 過、OpenDesign 永遠被擋）；測試名稱跟著改。審查 S-2 之後：精確釘選照舊（`SWITCHED_ON`，升版 PR 一起改），這兩項是第二道（第 19 節） |
| packaging | 2 | 容器驗收的指令數、假後端綁的位址 | 包在既有的 `switched()`（關） |

`test_real_products.py` 不用 `switched_off`：它的端到端子程序本來就讀 repo 的開關，所以改成照開關決定假後端綁哪裡（開通時綁私有位址，和 Headscale 一樣，
HM-20 的規則照樣生效）、斷線後多等一個健康檢查間隔（開通後要連兩次失敗才算 unreachable，DQ-25）。這樣 EMQX 開通後它測的就是出貨的設定。

`switched_off` 只決定測試在哪個模式跑：開關關（repo 現狀）時它什麼都不改，所以這些測試在本 clone 照舊全過（第 10 節）。測試裡面自己再開
（`switched_on`、`multi_profile_runtime`、自己的 monkeypatch）照樣有效。

最後一次（本片 HEAD `ee44bd5`，`git archive` 到拋棄式目錄、`.git` 複製一份、venv 與 node_modules 用連結、面板的 `dist` 實際複製；只把
`features.py` 改成 `frozenset({'emqx'})`）：

| 範圍 | 結果 | 秒數 |
|---|---|---|
| 第一次失敗的 28 個檔全部（不再用 `-k`）、兩個新測試檔、`test_ledger_precheck.py`、`test_tool_inventory.py`、`test_tool_snapshot.py` | 1,289 案：1,284 過、5 失敗、0 skip、0 error | 806 |
| packaging unittest（同一個複本） | `Ran 366`、`OK (skipped=5)` | 28 |

- 升版 PR 本來就要改的 3 案：`test_a_product_is_switched_on_only_by_its_release`（EMQX 的版號還是 0.4.14，開關釘選要 0.5.0；審查 S-2 之後先在
  精確釘選那行紅，升版 PR 改 `SWITCHED_ON` 與版號）；
  `test_ledger_precheck::test_this_checkout_has_no_ledger_drift` 與 `test_tool_inventory::test_runtime_patch_ledger_and_guarded_wheel_sources`
  （`features.py` 改了，`runtime-patches.json` 的摘要對不上）。
- 複本才有的 2 案：`test_child_port_param::test_the_default_child_spec_is_the_snapshot` 的 `n8n/documentation`、`n8n/configured`。複本的
  `apps/n8n/node_modules` 是連到本 clone 的連結，n8n 子程式規格裡 `index.js` 的實際路徑是本 clone 的、不是 `{ROOT}`。這個模組整個固定在開關關，
  本 clone 照過（第 10 節）。
- 其他都過：新測試 2＋29 案、`test_real_products` 9 案（含 EMQX 開通後的真子程式與假後端）、`test_router_passthrough` 49 案、黃金回歸 17 案。
  第一次的 78 個與 packaging 的 2 個失敗都沒了。

升版 PR 還要改、本片沒辦法先做的：`features.py`（加 `'emqx'`）、`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON`（加 `'emqx'`，審查 S-2）、
版號資料（`docs/operations/release.md` 的 7 處，含 `__init__.py`）、`runtime-patches.json` 裡 `features.py` 與 `__init__.py` 的摘要、
`addons/emqx/` 底下的文件（第 16 節）。

這批改動不只對 EMQX：套了 `switched_off` 的檔不管哪個產品開通都不讀 repo 的開關。但只用 EMQX 實跑過；LiteLLM、Nextcloud、Hermes、Headscale
開通時，可能還有別的測試讀了開關（例如只測那個產品的檔），各自的功能 PR 照同樣的方法把它打開跑一次。HM-21、HM-22、HM-24、HM-26 同時在準備，
它們若也改了同一批測試檔，誰後合併誰要合衝突（第 17 節）。

**Odoo（HM-19a，R1，比 EMQX 早）一定要再跑一次**（審查 S-4）：本片的找法只找出「EMQX 打開會紅」的測試。Odoo 專屬的「開關關」測試很多直接用
`production_runtime`、讀 repo 的開關，例如 `test_odoo_identity_rotation.py` 的 `test_switched_off_an_identity_change_keeps_todays_answer_order_and_token`
（斷言 `not features.enabled(PRODUCT)`）、`test_profile_admin_api.py` 的 `test_switched_off_the_profile_paths_are_unknown_and_no_header_is_needed`、
`test_restore_review.py` 的 `test_switched_off_the_new_routes_are_unknown`、`test_profile_ports.py` 的 `test_switched_off_child_restart_answers_as_before`。
HM-19a 在拋棄式複本把 `features.py` 改成 `frozenset({'odoo'})` 跑全套，照第 4 節的分類改（多半是加 `switched_off`）。本片只先改了
`test_monitor_cancel.py` 的 `run_until_sigterm(switch=False)`（`PRODUCT` 是 `'odoo'`）：它原本不動 repo 的開關，現在和
`multi_profile_runtime(switch=False)` 一樣所有產品都關；第 19 節用「repo 的開關有 Odoo」的對照驗過。

## 5. PaaS 變動與 #153 的對齊

- 讀法：GitHub 鏡像 `WOOWTECH/woow-mcp-server`，只用 GitHub API 讀（commit、檔案）；沒碰 Gitea、沒 clone、沒寫入。main 是 `5ef1046`（2026-11-18）。
- `apps/emqx` 在 2026-11-13 之後的 commit：#153（`cd1ed89`、`4b4fd16`、`574c805`、`e59c9b2`、`fabb192`，合併 `5b84b5d`）、#155 的兩個
  （`3b135ca`、`1637a0f`，HM-31 已對齊）、#135（`3c06b98`，HM-32 已對齊）。`3c06b98` 之後 EMQX 沒有新 commit。
- `48f394d..5ef1046`（基準文件最後一次核對之後）：只有 #157～#159，都是 K8s MCP；HA 沒有這個產品，和 EMQX、多帳號無關。
- PaaS 的 EMQX 管理程序（`apps/emqx/emqx_mcp_admin/main.py`）多帳號相關的只有：每個帳號的 key 進全域遮罩集合（HA 不需要，第 3 節）、
  子程式每次呼叫讀政策（`child_policy.py`，DQ-27 不做）。

| PaaS commit | PaaS 改了什麼 | HA 本片 |
|---|---|---|
| `cd1ed89` | `tools/topics.py`：`match_topic` 的參數說明與工具說明（只改文字） | 同一段逐字照改（`apps/emqx/vendor/emqx_mcp_server/tools/topics.py`）；閘道內附清單重產 |
| `4b4fd16` | `http_policy.py`：`BrokerClient.request` 加 `accept`（只收兩個值）；`errors.py` 加 `text_body`；`tools/cluster.py` 的 Prometheus 請求送 text/plain | HA 沒有 `BrokerClient`，每個請求經 `deps.EmqxHttp.request`（後面是 `backend_policy` 的 client）：在這裡加同樣的 `accept` 規則與「只收四種請求選項」，拒絕時丟 `backend_policy.BackendDenied`（`emqx_request` 本來就把它對成 `EMQX_DESTINATION_DENIED`）；`text_body`、`cluster.py` 照 PaaS。`text_body` 的說明拿掉 PaaS 那句「大小與壓縮的上限在傳輸層」（HA 的傳輸層沒有，見下） |
| `574c805` | `BrokerClient.request` 接住 `httpx.InvalidURL`、`UnicodeError`，網址超過 65,536 字元先擋；`tools/_common.py` 的 `path_segment` 對無法編碼的值回固定碼 | 同樣三件事做在 `EmqxHttp.request` 與 `path_segment`；先擋的長度在任何路徑檢查之前（HA 是 `backend_policy.no_dot_segments` 與傳輸層的目的地檢查） |
| `e59c9b2`、`fabb192` | PaaS 的 `README.md`、`VENDORED.md`、`source-manifest.json` | HA 沒有這三個檔。使用者看得到的說明交升版 PR 的 DOCS（第 16 節）；vendor 的改動記在 `runtime-sources.json` |

沒照抄的（PaaS `BrokerClient` 本來就有、不是 #153 的內容）：4 MiB 回應上限、拒絕壓縮的回應、`Accept-Encoding: identity`。HA 的 EMQX 傳輸層
（`backend_policy`）沒有這三樣，本片不加；契約第 1.2 節 HM-23 那段寫明。

## 6. PaaS 測試逐案對照（#153 的三個測試檔，`5ef1046`）

| PaaS 測試 | HA |
|---|---|
| `test_subscription_match_topic.py`：說明不再是相反的方向、參數說明寫明 broker 的做法、工具說明寫明怎麼回答「誰會收到」 | `tests/test_emqx_field_findings.py` 同名三案；另加「說明逐字是 PaaS 的」與「閘道內附清單是同一段」兩案 |
| 同上：`match_topic` 原樣轉成查詢參數（8 個值）、其他篩選參數名稱不變、回傳不在閘道比對 | 同名三案（8 個值在一案裡） |
| `test_prometheus_accept.py`：這支送 text/plain 回文字、截在 `max_bytes`、broker 還回 JSON 時照舊、其他 38 支照舊 JSON | 同名四案（不斷言 `Accept-Encoding: identity`：HA 不送，見第 5 節） |
| 同上：空的文字、204、401／404／500、其他工具的空或畸形 JSON | 同名四案 |
| 同上：超過 4 MiB 拒絕、剛好 4 MiB、壓縮的回應拒絕 | 不適用：PaaS `BrokerClient` 自己的規則，不是 #153 的內容，HA 的傳輸層沒有（第 5 節） |
| 同上：傳輸層只認兩個 Accept 值、其他 Accept 值（11 種）與請求選項（5 種）送出前拒絕 | `test_the_door_serves_text_only_when_asked_with_the_fixed_value`、`test_any_other_accept_value_is_refused_before_io`、`test_callers_still_cannot_pass_headers_or_other_request_options`（在 `EmqxHttp.request`） |
| `test_long_identifiers.py`：18 個超長參數固定碼、不回顯、沒有請求、沒有 traceback；四種組成 | 同名兩案（18 個與 4 種各在一案裡） |
| 同上：真的子行程的 stdout 沒有 traceback | `test_the_real_child_prints_no_traceback_for_an_overlong_identifier`：真的子程式行程（`run_child`）在閘道後面，讀 Supervisor 收的原始輸出 |
| 同上：路徑的單獨 surrogate、組不出來的請求（3 種）、先擋再分析、工具參數的 surrogate、正常長度、CJK 的編碼長度 | 同名六案；「先擋再分析」看的是 `backend_policy.no_dot_segments` 沒被呼叫 |
| — | HA 另加：整個 harness 沒有任何 traceback 的 log record |

## 7. 先紅後綠與突變

| 測試 | 紅 | 綠 |
|---|---|---|
| `tests/test_emqx_field_findings.py`（29 案） | `9635e09`（測試已在、vendor 還是基準的）：20 案紅、9 案過。紅的：說明 4、Prometheus 與請求的門 7、識別字 7、harness 有 traceback 1、真的子程式 1（用戶端拿到被遮掉的「Error calling tool 'emqx_get_client'」）。過的 9 案是釘住「不改行為」的（參數原樣轉送、其他篩選名稱、回傳不比對、閘道清單和子程式說明一致、broker 回 JSON 照舊、其他 38 支照舊 JSON、錯誤狀態碼、其他工具的空或畸形 JSON、正常長度照舊送到），同 PaaS 的做法 | `e991dbc` 之後 29 案全過（第 10 節的開關關那批；開關開的複本也過） |
| `tests/test_emqx_multi_profile.py`（2 案） | 沒有新的產品程式，所以用突變證明它會紅（下表） | 2 案過（開關關那批；開關開的複本也過） |
| 測試自己指定模式（第 4 節） | 開關開：tests 78 個、packaging 2 個失敗 | 第 4 節最後一次 |

突變（拋棄式複本，一次一處、跑 `tests/test_emqx_multi_profile.py`、還原並核對位元組相同）：

| 突變 | 改了哪裡 | 結果 |
|---|---|---|
| M1 存 EMQX 政策不重起子程式 | `gateway.py`：存政策後重起子程式的產品名單拿掉 `'emqx'` | 紅：開通那案（存 B 的政策後，B 的子程式啟動次數沒變） |
| M2 子程式拿不到停用的工具 | `products.py`：EMQX 的 `EMQX_MCP_DISABLED_TOOLS` 永遠是空的 | 紅：開通那案（B 的子程式環境裡沒有停用的工具） |
| M3 子程式拿到政策檔（DQ-27 的反面） | `products.py`：EMQX 子程式的環境多 `MCP_ADMIN_CONFIG`（該帳號的 `state.json`） | 紅：開通那案（預設帳號的子程式環境有 `MCP_ADMIN_CONFIG`） |
| M4 子程式 bearer 放行任何值 | `apps/runtime/session_idle.py`：bearer 比對永遠成立 | 紅：開通那案（預設帳號的子程式不帶 `Authorization` 也回 200，T-23 矩陣的第一種） |
| M5 閘道不擋停用的操作 | `policy.py`：`denied_operations` 永遠當成空的 | 紅：開通那案（C 的 `emqx_manage_authn_users` delete 沒被擋） |

五個都是一個突變只跑一次（`-x`，第一個失敗就停），每次跑完把檔案換回原本的位元組並核對；最後四個檔都和 `ee44bd5` 相同。

## 8. HM-01 黃金回歸與契約凍結

- 開關關：黃金回歸逐位元照舊，只有 EMQX 的兩個 tools/list 摘要因 #153 的說明改了而更新（測試檔頭的規則：刻意的工具表面變更，兩個一起更新）。
  核對（暫存區的腳本：黃金回歸自己的 `production_runtime`、MockChild、不起程序、不開 socket；EMQX 兩種狀態 × 兩條接法；每個產品都關）：
  - 用基準 `c90b214` 的內附清單算出的兩個摘要，等於基準釘的值（`646abdc0…`、`5140e30f…`）：核對工具有效。
  - 用本片的清單：`LISTING_SHA256` `dad5f8fc8843c047a3adfca67fe4962f4be628e5dc196a13f651b3e01ddbf5cd`、`LISTED_SHA256`
    `ca83692edc778cfc7b211bf313518c5e71d0d89c100001a2a3d0fc1b7d347c34`；兩種狀態、兩條接法的回答相同。
  - 新的回答**就是舊的回答只把兩段說明換掉**：舊回答裡的兩段舊說明（JSON 編碼後）各出現一次，換成新說明後和新回答逐位元相同；解析後比也相同。
    回答 31,486 → 32,306 位元組。
- 多帳號那部分沒有任何黃金位元組改變：受開關管的部分沒有新的程式。
- 兩個契約凍結（MCP、管理）沒改，照過。HM-01 三個檔加 `switched_off`（第 4 節）只決定它們在哪個開關模式跑，釘的值一個都沒動；
  `tests/test_router_passthrough.py` 照舊在開通下再跑它們（含 EMQX；它直接呼叫測試函式，不受模組的 `pytestmark` 影響）。

## 9. 帳本、工具表面與釘選（照各檔的結構重算，沒有整批 `--write`）

| 檔 | 改了什麼 |
|---|---|
| `docs/provenance/runtime-sources.json` | EMQX 五筆：`errors.py`、`tools/_common.py`、`tools/cluster.py` 更新 `local_sha256` 並在 `modification` 補一句；`tools/topics.py`、`deps.py` 原本和上游相同，加 `local_sha256` 與 `modification` |
| `docs/provenance/runtime-patches.json` | `apps/emqx/vendor/emqx_mcp_server/errors.py` 的 `sha256` 與 `change`；`tool_snapshot.py` 的 `sha256` 與 `change`；`n8n_arguments.py` 的 `guarded_sources` 裡 `tool_snapshot.py` 的摘要與 `change`（`n8n_arguments.py` 本身沒改，照之前幾次的寫法） |
| `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` | 只用產生器重產 EMQX 那一個產品（`WOOW_WRITE_TOOL_SNAPSHOT=1`，`tests/test_tool_snapshot.py -k emqx`）；和基準比，8 個產品、各自的工具數都相同，不同的只有 `emqx_list_subscriptions` 的 `description` 與 `match_topic` 的 `description` 兩處 |
| `docs/tool-surface.json` | `scripts/tool_inventory.py` 的 `build()` 和現在的檔逐欄比：五個檔的 `source_digests`，加 `emqx_list_subscriptions` 的 `source_signature`（簽章文字含參數的 Field 說明）；沒有別的差異、沒有行號移動，`tool-surface.md` 不變。只寫這些之後 `tool_inventory.py` exit 0 |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES` 加五個檔的目前位元組與一段註解（`output_schemas.json` 記的是來源 commit 的位元組；輸入、輸出 schema 都沒變） |
| `tests/test_single_profile_golden.py` | EMQX 的 `LISTING_SHA256`、`LISTED_SHA256`（第 8 節），加註解 |

`docs/multi-profile/ledger-tracking.md` 不用改：沒有新模組、沒有新的列管檔。`docs/provenance/six-runtimes.md` 也不改：它寫的「17 個本地差異」是當時那一輪的數字
（本片之後是 40 個），HM-33 同樣沒改。

## 10. 本機檢查（2026-11-19，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 或 `mktemp -d /tmp/ha-mp-XXXXXX` 給的短目錄，每次跑完刪除；pytest 都排在共用鎖後面）

| 檢查 | 結果 | 秒數 |
|---|---|---|
| 開關關（本 clone 當時的工作目錄：程式、帳本與測試和 `e991dbc` 相同，之後只改了 `tests/test_emqx_multi_profile.py` 的 docstring 與一段註解（引用的列號改成 #130）、`tests/switch_modes.py` 一個沒用到的常數）：改到的 30 個測試檔＋相關 22 個檔（EMQX、工具表面、帳本、HM-01 守門、`test_router_passthrough`、`test_tool_snapshot` 等） | 1,972 案：1,971 過、1 失敗（`test_owned_executable` 的 uid10001，要 root，既有）、0 skip、0 error。新檔：`test_emqx_field_findings` 29 案、`test_emqx_multi_profile` 2 案、黃金回歸 17 案、`test_upgrade_zero_rewrite` 46 案都過 | 1,041 |
| 開關關：`switch=False` 的另外兩個使用者（`test_profile_quotas.py`、`test_reply_worker.py`；本 clone `ee44bd5`） | 163 案全過（它們測的不是 EMQX；開關空的時候新舊 `switch=False` 一樣） | 72 |
| 開關開（拋棄式複本，第 4 節最後一次；33 個檔） | 1,289 案：1,284 過、5 失敗（升版 PR 本來就要改的 3 案、複本才有的 2 案，第 4 節） | 806 |
| 紅（`9635e09` 的 `git archive` 複本，`tests/test_emqx_field_findings.py`） | 20 失敗、9 過（第 7 節） | 82 |
| 突變 | 第 7 節 | — |
| `packaging/validate.py`（ha-gh-release clone 的 venv，Python 3.13.15） | PASS | 0 |
| packaging unittest（同一個 venv，`discover -s packaging -p 'test_*.py'`，同 CI） | `Ran 366`、`OK (skipped=5)`；開關開的複本也是 `Ran 366`、`OK (skipped=5)` | 26／28 |
| `scripts/tool_inventory.py` | exit 0（0 漂移） | — |
| 面板的 node 與 Playwright 測試 | 沒跑：面板沒改 | — |
| 雙向控制字元與零寬字元 | 改到的檔、本筆記、commit 訊息：0 個 | — |

本機一定失敗的既有案例（要 root）：`test_owned_executable` 的 uid10001、`test_profile_store::test_mode_and_owner_as_the_add_on_user`、
`test_restore_detection` 的 `test_root_*`。本片沒動它們測的東西。

這一節是審查前（`ee44bd5`）的結果；審查處理後的重跑見第 19 節。

## 11. 只在 CI 跑的測試、`checks` 秒數

- 本片新增與改過的測試都在本機跑過（第 10 節）。新測試要 EMQX 自己的 venv（`apps/emqx/.venv`），CI 的 `packaging/unit.sh` 先裝好；本機也有。
  CI（root、0 skip）才是準；全套 pytest 只在 CI 跑。
- 要 root 的既有案例（第 10 節）只在 CI 過。
- 本片的測試在 root 下：不依賴 uid 或檔案權限；假 broker 綁本機的私有位址或 127.0.0.1 的臨時 port（不是 3000、18000～18099）；子程式的
  child port 用臨時 port。
- `checks` 秒數：開 PR 後補（前：`claude-delivery` 最近一次 PR run；後：本片 PR）。
- 新測試的時間（本機 AMD EPYC 7713、Python 3.13.15）：`test_emqx_multi_profile` 兩案 4.8 與 3.3 秒（真的子程式啟動）；
  `test_emqx_field_findings` 29 案共 4.9 秒（harness 約 2.9 秒、真的子程式那案 1.9 秒）。CI 推估約兩倍，對 `checks` 的影響可以忽略。

## 12. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:scan0414/tools --repo . --base origin/claude-delivery --head HEAD` | 前 5 個 commit（`c90b214..ee44bd5`；gitleaks 8.28.0 釘版已驗）：`result: OK, 0 findings`。加上本筆記的 commit 後重跑的結果寫在交回主對話的回報（筆記記不到自己那個 commit） |
| 帳本預檢 | `python3 scripts/ledger_precheck.py` | `ee44bd5`：`result: OK`：`runtime-patches.json` 180 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的 6 個列管檔都有帳本更新；沒有未列管的新 runtime 檔 |

`SP:`＝本工作的暫存區（裡面的 gitleaks 是 8.28.0 釘版，預檢自己核對過摘要與版本）。

測試資料：假 broker 的憑證是 `DUMMY-emqx-<帳號>-key`、`DUMMY-emqx-<帳號>-secret`；token 與 key 的假值用 `T`×43、`C`×43；名稱用 `.invalid`
（`broker.invalid`、`emqx@hm23.invalid`；`tests/fixtures/owner_defaults/README.md`）。沒有 commit 隨機產生的 token 或像金鑰的字串。本筆記不含 token、密碼或像金鑰的字串
（帳本與黃金回歸的摘要是檔案內容或回答的 SHA-256）。

## 13. 契約第 9 節的列（列號暫定）

| 列 | 內容 | 類型 |
|---|---|---|
| #129 | EMQX 的後端並行連線上限：PaaS 的 `BrokerTransport` 與 HA 的 `backend_policy` 生效的都是 4、不保留閒置連線；`lifespan.py` 寫的 20 沒生效（HM-32 審查 S-4 (b)、MF-1，計畫 §12.3 HM-29 的 2026-11-17 註）；每個帳號各自一個連線池，N 個帳號最多 4×N 條 | 既有 |
| #130 | EMQX 受限帳號的子程式與後端金鑰：沒有寫入授權的帳號子程式仍 `READONLY=false`（混合工具的讀取操作），寫入操作只在閘道擋（#65）；文件建議受限帳號用 `viewer` 角色的 API key（UC-22） | 既有 |
| #65（附註） | HM-23 照計畫 §9 與 DQ-27 的建議做（子程式只從啟動環境拿到自己帳號的兩個值，不讀任何政策或 state 檔），DQ-27 仍待使用者確認 | 待決（不變） |

- 基準 `c90b214` 的最後一列是 #128（HM-27）。HM-21、HM-22、HM-24～HM-26 也在準備自己的列，**誰後合併誰往後重編**（照 HM-27 的做法：
  第 9 節說明段、第 10 節的列與筆記一起改）。本片的列在契約裡只被第 1.2 節、第 10 節與本筆記引用；`tests/test_emqx_multi_profile.py` 的
  docstring 與一行註解引用 #130，重編時一起改。
- LiteLLM 的同一件事（PaaS 50、HA 4，計畫 HM-29 的註）屬 HM-21；#129 寫明兩片誰後合併誰把兩列合成一列。
- `deviation-trace.md` 不手改（repo 外的產生器重產；HM-13b 以後的片都沒加）：下一次文件同步時，FM-92 那一列的「對到」可補 #130。

## 14. 本片用到的決策（`docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| DQ-27（待定，計畫建議不做；最晚「HM-23 開工前」） | EMQX 子程式要不要每次呼叫再讀政策 | 照建議不做，並用測試釘住；`decisions.md` 不改（使用者還沒定），交使用者確認（第 17 節） |
| DQ-28 | OpenDesign、Odoo Manage 不開放 | 開關釘選的新寫法照樣擋它們（`supports_profiles`） |
| DQ-32 | 開通的產品升 0.5.0；R2（LiteLLM、Nextcloud、EMQX）可合成一個升版 PR | 開關釘選改成要求開通的產品版號至少 0.5.0 |
| DQ-36 | 不改版號的功能 PR、標題前綴、commit 與 PR 說明不加署名行 | 本分支的 commit 只有 clone 設定的身分、沒有署名行；不 push、不開 PR（本階段） |
| DQ-40 ⑨ | 開通後改網址到別的來源要重填秘密 | EMQX 的 `url` 要重填 `api_key`、`api_secret`（既有規則與測試，本片沒改） |
| DQ-10、DQ-40 ⑦ | 開通後拒絕 loopback 後端 | 新測試的假 broker 綁私有位址，規則照樣生效 |
| DQ-25 | 開通後連兩次失敗才判 unreachable | `test_real_products.py` 的斷線等待多一個間隔 |

## 15. 之後的 HAOS 實測（EMQX 升版 PR，R2；每一步先經使用者批准）

- 現況：展示機上的 EMQX 是停的，EMQX 沒有任何真節點的多帳號證據（`docs/operations/acceptance.md` 也寫明 EMQX 真節點證據要逐產品確認）。
  容器的多帳號階段也還沒在 EMQX 的候選映像跑過（第一次是升版 PR 的建置）。本片照規則沒連任何 HA 主機或 broker。
- 使用者要提供或批准：
  1. 一台 QA 用的 EMQX broker（啟動展示機上的 EMQX，或另給一台），記下版本與版本別。`viewer` 角色要 EMQX Enterprise 5.4 以上，或 5.9 以上的任何版本；
     舊的開源版（5.8 以前）有沒有 API key 角色要查那個版本的文件（UC-22 剩下的部分）。
  2. broker 的網址要是 add-on 連得到的**非 loopback** 位址：開通後子程式拒絕 loopback（HM-20），同一台 HA 上的 EMQX 要填它的 hostname 或區網 IP。
  3. 批准建立、之後刪除這些後端身分（計畫 §10.7、G6-15）：至少兩把 API key，一把 `administrator`（預設帳號）、一把 `viewer`（受限的額外帳號）；
     做得到再加第二台 broker 的一把 key（FM-109 的「兩台 broker」）。用 Dashboard 建（REST API 改 key 時一定要帶 `role`：EMQX issue #18968，
     不帶會變回 administrator）。證據只記 key 名稱與角色，不記 secret。
  4. 合成的測試資料：測試用的 MQTT client id 與 topic（例如 `hm23/…`），測完清掉（retained 訊息、訂閱、ban、trace）。
- 要跑的 T（`docs/operations/acceptance.md` 的 HA 欄）：
  - T-01（版本、digest）、T-02（第 4 個額外帳號 409：EMQX 上限 3）、T-05（P9 `--cross`）、T-06、T-07（P9 `--profile … --plan`：存一個帳號的政策只重啟它）、
    T-08、T-09（`--temp-profile`）、T-13（`childkill`）、T-14、T-18、T-23（容器）、T-24、T-25、T-27、T-29（合成憑證掃描、清理證明）。
  - T-04：兩把 key 的對角線：`viewer` 帳號呼叫寫入工具被 EMQX 拒（`EMQX_API_ERROR status=403`），`administrator` 帳號成功；每個帳號只看到自己 key 的結果。
  - T-17：EMQX 子程式的 RSS（`CHILD_MEMORY_MIB['emqx']` 的 160 MiB 是估計）與 1～4 個帳號的整機數字。
  - T-20、T-21 與每次升版重驗的 UC-08、sentinel、UC-10。
  - T-03、T-10 不適用（EMQX 不換 token；跨帳號寫入的 record rule 是 Odoo 的）。

## 16. 交給 EMQX 的升版 PR（`addons/` 底下，本片不碰）

- `features.py` 加 `'emqx'`，`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON` 同時加 `'emqx'`（審查 S-2：開關的變化要在測試的 diff 裡看得到）；
  版號 0.5.0（DQ-32；開關釘選的第二道要求至少 0.5.0）與版號資料 7 處；`runtime-patches.json` 裡 `features.py`、`__init__.py` 的摘要。
- `addons/emqx/CHANGELOG.md`：`docs/multi-profile/unreleased-changes.md` 的 E3（#153 三句），加計畫 §7.2 開通後預設帳號會變的事。
- `addons/emqx/DOCS.md`：
  - 「一個 Add-on 只有一組後端」改成每個帳號一組（url、api_key、api_secret），最多 3 個額外帳號，存一個帳號的工具權限只重啟它的子程式。
  - 受限帳號的建議（草稿）：「只想讓模型查詢的帳號，除了在工具權限頁關掉寫入，建議在 EMQX 建一把 `viewer` 角色的 API key 給它：`viewer` 只能呼叫
    REST API 的 GET，模型呼叫寫入工具時 EMQX 自己會拒絕（`EMQX_API_ERROR status=403`）。原因：這種帳號的子程式仍會載入 authn 使用者與 authz 規則
    這兩支混合工具（讀取要用），它們的寫入只由 add-on 的閘道擋。API key 角色：EMQX Enterprise 5.4 起有，5.9 起所有版本都有（`administrator`、
    `viewer`、`publisher`）。用 REST API 改 key 時要一起送 `role`。」
  - #153 的三件事（`match_topic` 的意思、Prometheus 文字、超長識別字的固定錯誤碼），PaaS README 的同一段可參考（`e59c9b2`）。
- `config.yaml` 沒有「一組帳號」的字樣，不用改說明。

## 17. 還沒解決、要使用者決定的事

要使用者決定：
1. **DQ-27**：`decisions.md` 仍是待定（計畫建議不做，最晚「HM-23 開工前」）。本片照建議做（子程式不讀政策，停用的操作只在閘道擋），測試釘住。
   選項：(a) 確認不做（照現在）；(b) 只把停用的操作也交給子程式自己的閘門（`EMQX_MCP_DISABLED_OPERATIONS`，存政策本來就重起子程式，改動小；
   開關關時子程式環境會多一個變數，屬不受開關管的改動）；(c) 照 PaaS 讓子程式每次呼叫讀存檔的政策。建議 (a)：子程式只聽自己 child bearer 的請求，
   能直接打子程式的只有同 uid 的程序，那已經在 DQ-37 接受的信任邊界裡；後端用 `viewer` 角色的 key 是更實在的縱深防禦（UC-22）。
2. **PaaS #153 留在本 PR 或拆開**：計畫把 #153 交給 HM-23（README 2026-11-16 07:1x），但不像 HM-32、HM-33 有使用者「現在就補」的決定。它不受開關管，
   EMQX 下一版（不管開不開通）就會帶出去：`emqx_list_subscriptions` 的說明會變（HM-01 黃金回歸 EMQX 的兩個摘要照檔頭規則更新）、
   `emqx_prometheus_stats` 會回 Prometheus 文字、超長識別字回固定錯誤碼。commit 是分開的（`9635e09` 測試、`e991dbc` 修正），要拆成另一個 PR
   只要把這兩個 commit 拿出去。
3. **EMQX 的 20 條連線**（契約 #129）：生效的是 4，和 PaaS 一樣。選項：(a) 不動；(b) `lifespan.py` 的 `max_connections` 改成 4，只改設定、行為不變
   （和 HM-32 對齊閒置連線的做法相同）；(c) 讓 `backend_policy` 採用產品的上限（改行為、和 PaaS 不同，也會影響其他產品）。建議 (b) 或 (a)；
   和 HM-21 的 LiteLLM（PaaS 50、HA 4）一起定。
4. **測試自己指定開關模式這一批**（第 4 節，`e803d58`，審查後加 `938643c`、`98c9cb7`）對其他產品也有用（套了的檔不讀開關）。
   審查 S-3 查到 HM-26（`d59be1e`）做了同一件事的另一套：`tests/product_switch.py` 的 `switched_off` 同名，但要 `product` 參數、只關那個產品，
   `multi_profile_runtime(switch=False)` 是 `MULTI_PROFILE_PRODUCTS - {product}`；兩片改同一批檔的同一段（第 19 節）。HM-26 的審查（MF-2）也要求二選一。
   **要主對話選一套**（模組名、fixture 名與意思、`switch=False` 的值），建議拆成一個只含測試工具的小 PR 先合，另一片把主線合併進來之後改用它。
   兩套對「只跑一個產品的測試」效果相同；本片這套不要參數、模組層的 `pytestmark` 就能用，已用 EMQX 打開實跑過。
5. **HAOS 實測**（第 15 節）：要 QA 用的 EMQX broker、兩把 API key（`administrator`、`viewer`）的建立與刪除批准；broker 版本要支援 API key 角色。

還沒做、交給後面的：
- 升版 PR（第 16 節）。
- `deviation-trace.md` 的 FM-92 補 #130（下一次文件同步）。
- `paas-test-mapping.md` D 組 #153 的三個檔（`test_long_identifiers.py` 9 案、`test_prometheus_accept.py` 14 案、`test_subscription_match_topic.py`
  6 案）現在寫「HA 要不要跟進交 HM-23 對照」：下一次文件同步改成對到 `tests/test_emqx_field_findings.py`（逐案見第 6 節；4 MiB 與壓縮那幾案仍是
  不適用）。表由 repo 外的產生器重產，本片不手改。
- 計畫與 FEATURE-MATRIX（repo 外，給主對話）：UC-22 可改成「已確認：`viewer`（Enterprise 5.4 起、5.9 起所有版本）」；計畫 §12.3 HM-23 可補一句
  「功能 PR 沒有產品專屬的執行期程式；測試自己指定開關模式那一批讓升版 PR 只改開關、開關釘選與版號」；FM-92 的 HA 現況可補「HM-23 測試釘住」；
  計畫 §11.3 的升版 PR 清單加 `tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON`（和 `features.py` 一起改，審查 S-2）。
- HM-19a：把 Odoo 打開跑全套，改讀了 repo 開關的 Odoo 測試（第 4 節，審查 S-4）。
- `checks` 秒數（第 11 節，開 PR 後補）。

## 18. commit（`c90b214` 之後）

| commit | 標題 |
|---|---|
| `e803d58` | test(core): tests that pin one switch mode name it, so a version bump only flips the switch (HM-23) |
| `b85722e` | test(emqx): EMQX with additional profiles, both switch modes (HM-23) |
| `9635e09` | test(emqx): PaaS #153 field findings, red at this commit (HM-23) |
| `e991dbc` | fix(emqx): match_topic text, Prometheus text and a fixed code for identifiers a URL cannot carry (PaaS #153; HM-23) |
| `ee44bd5` | docs(multi-profile): EMQX contract rows, test registry and next-version items (HM-23) |
| `24df882` | docs(provenance): HM-23 note |
| `05bf35f` | test(emqx): leave the health probes out of the not-asked checks and take the diagonal with a tool they never call (HM-23 review) |
| `938643c` | test(core): pin the switched-on products exactly again, the 0.5.0 rule as a second guard (HM-23 review) |
| `98c9cb7` | test(core): the SIGTERM rig's switch=False is every product off, as multi_profile_runtime's (HM-23 review) |
| `83165b6` | docs(multi-profile): the review's T-04 diagonal, switch pin and SIGTERM rig in the matrix; where contract rows 129 and 130 come from (HM-23 review) |
| 本筆記的審查處理 | docs(provenance): the HM-23 review and how each point was handled in the HM-23 note |

作者、提交者都是 clone 設定的身分（woowtech）；commit 訊息沒有署名行。合併只用 merge commit，沒有 rebase、amend 或 force push。

## 19. 審查與處理（2026-11-19）

- 審查報告：`artifacts/ha-multiprofile-parity-20261114/wave5/review-HM-23-correctness.md`（repo 外）。結論「修正後通過」：必修 1、建議 4、備註 7。
- 處理：必修與 S-1、S-2、S-4 照改；S-3 要主對話選，本片不改；備註只改 N-2。基準 `claude-delivery` 仍是 `c90b214`，不用合併主線。

| 項目 | 處理 | commit |
|---|---|---|
| MF-1 開通那案「沒有 broker 被叫到」的兩個斷言，會被健康檢查打到 | 改。假 broker 加 `asked()`：某個位置之後、健康檢查的 `GET /api/v5/nodes` 以外的請求。閘道擋下時三台都要是空的；之後 B、C 兩台也要是空的 | `05bf35f` |
| S-1 T-04 對角線太弱 | 改。改用健康檢查不打的 `emqx_broker_stats`（`GET /api/v5/stats`）：每次呼叫只有自己的 broker 收到這一個請求、帶自己的 key，別台一個都沒有。測試開頭斷言健康檢查的工具是 `emqx_cluster_status`，排除的請求和它對得上 | `05bf35f` |
| S-2 開關釘選放寬 | 改，照建議。`SWITCHED_ON = frozenset()`，開關要正好等於它，升版 PR 和 `features.py` 一起改這一行；「能有帳號、版號至少 0.5.0」留作第二道。反向對照：每個能有帳號的產品，在 `SWITCHED_ON` 裡就拿掉、不在就加上（今天都是加上），都被釘選擋下（版號都設 0.5.0，只剩釘選）；EMQX 0.4.99 與 OpenDesign 被第二道擋。三種失敗各比對自己的訊息 | `938643c` |
| S-3 和 HM-26 同名不同義 | 不改：選哪一套要主對話定（第 17 節第 4 點）。合併時要注意的地方在下面 | — |
| S-4 Odoo 的測試還在讀 repo 的開關 | 改 `run_until_sigterm(switch=False)`：所有產品都關。第 4 節寫明 HM-19a 要把 Odoo 打開跑全套，列出審查舉的四案 | `98c9cb7` |
| N-1 `deps.py`、`errors.py` 對同一個 import 的處理不一致 | 不改。兩個都是列管的 vendor 檔，改一行註解也要重算帳本與 `test_output_schemas.py` 的位元組；正式環境與測試都有 `apps/runtime`，行為不受影響。下一個動 EMQX vendor 的片順手統一 | — |
| N-2 契約說明段的措辭 | 改：#130 是 FM-92 的建議（UC-22），#129 和 FM-155 是同一個原因 | `83165b6` |
| N-3 第 9 節列號撞號 | 照第 13 節：後合的往後重編；#129 和 HM-21 的 LiteLLM 列合成一列 | — |
| N-4 沒測「同一台 broker、不同 key」 | 不加：子程式環境的斷言已證明 key 各自分開；HAOS 的 T-04 用兩把 key 測（第 15 節） | — |
| N-5～N-7 | 只記錄：#153 放在本片是計畫的安排（要不要拆仍在第 17 節）；UC-22 的查證和第 15 節一致；DQ-27 仍待使用者確認 | — |

S-3 合併時要注意的地方（主對話選定之前）：
- 兩片都改 `tests/multi_profile_runtime.py` 的 `switch=False` 那一行，也都在 `tests/test_upgrade_zero_rewrite.py` 加 `switched_off_runtime`（同名、做法不同）；
  黃金回歸、兩個契約凍結、`test_child_bearer.py`、`test_child_port_param.py`、`test_profile_runtime.py`、`test_real_products.py` 等的 import 與 `usefixtures` 在同一個位置。
- 兩邊的 `switched_off` 不能都留：後 import 的生效。HM-26 的生效時，本片模組層的 `usefixtures('switched_off')` 套到沒有 `product` 參數的測試會直接出錯；
  反過來，HM-26 的意思被悄悄換掉。
- HM-25 拿掉 `tests/test_upgrade_zero_rewrite.py` 的 `import contextlib`（它刪了 `n8n_switched_on`），本片的 `switched_off_runtime` 要用它：後合的一方要留這一行。
- 本片這一批是 `e803d58`、`938643c`、`98c9cb7` 三個 commit，只動測試；拆成小 PR 時三個一起拿。

驗證（拋棄式複本，venv 用連結，clone 沒動；一次 pytest 跑 7 個變體）：

| 變體 | 預期 | 結果 |
|---|---|---|
| 審查前的開通那案（`24df882`），政策那段多等 0.45 秒 | 紅（重現 MF-1） | 紅：比請求數的斷言失敗（3.3 秒） |
| 修好的開通那案，對角線與政策兩段各多等 0.15、0.45、1.2 秒 | 綠 | 三個都綠（5.4、7.0、10.1 秒） |
| 修好的開通那案，B 的對角線呼叫改走預設帳號的 session（模擬串線） | 紅（S-1 的斷言抓得到） | 紅：`default` 收到 `GET /api/v5/stats`、`beta` 沒有（2.7 秒） |
| 審查前的 `test_monitor_cancel.py` 開關關那案，repo 的開關有 Odoo（HM-19a 之後的樣子） | 紅（S-4） | 紅：`run_product` 照開通的方式起，`run_until_sigterm` 等不到它要的 ProfileRuntime，15 秒逾時 |
| 修好的同一案，repo 的開關有 Odoo | 綠 | 綠（0.1 秒） |

合計 3 紅 4 綠，和預期一致（1,126 秒，大多是排隊等共用鎖）。

重跑的檢查（HEAD `83165b6`；一般使用者 uid 1000；短 TMPDIR，跑完刪除；pytest 排在共用鎖後面）：

| 檢查 | 結果 | 秒數 |
|---|---|---|
| pytest：改到的三個檔、兩個 EMQX 新檔、HM-01 的三個守門（黃金回歸、兩個契約凍結）、`test_router_passthrough`、`test_backend_loopback`、`test_restore_lock`（後三個 import 零改寫測試的 helper），共 10 個檔 | 427 passed、0 failed、0 skip、0 error | 580（含排隊等共用鎖） |
| packaging unittest（ha-gh-release clone 的 venv，`discover -s packaging -p 'test_*.py'`） | `Ran 366`、`OK (skipped=5)` | 28 |
| `packaging/validate.py`（同一個 venv） | PASS | 0 |
| 秘密預檢（`--tools SP:scan0414/tools`，gitleaks 8.28.0 釘版已驗） | `c90b214..83165b6` 10 個 commit：`result: OK, 0 findings` | — |
| 帳本預檢 | `result: OK`：`runtime-patches.json` 180、`runtime-sources.json` 70、`tool-surface.json` 159 項，0 漂移、0 缺；沒有新的列管檔改動（審查處理只改測試與文件） | — |
| 雙向控制字元與零寬字元、署名 | 改到的 48 個檔與 10 個 commit 訊息：0 個；沒有署名行；作者與提交者都是 woowtech | — |
| 面板的 node 與 Playwright 測試 | 沒跑：面板沒改 | — |

其他測試檔在審查處理中沒改，第 10 節的結果照舊有效。

- 本筆記這個 commit 之後，再跑秘密預檢與帳本預檢；結果寫在交回主對話的回報。之後 push 本分支（新分支，fast-forward），沒開 PR。
- 只在 CI 跑的：全套 pytest（root、0 skip）與要 root 的既有案例（第 10 節）；`checks` 秒數開 PR 後補。
