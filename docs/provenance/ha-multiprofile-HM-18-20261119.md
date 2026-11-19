# HA 多帳號 HM-18 provenance：文件與契約定稿（不開通）（2026-11-19）

## 結論

- **2026-11-19 補記**：負責人 08:4x 照計畫建議定 DQ-04、DQ-22（主對話 AskUserQuestion），記進 `decisions.md`（41 題已定、5 題待定）與契約
  （#28、#47、#62、第 4.2、8 節；#47 類型改部署、#62 改既有；還待決的剩 #10、#65）；本筆記其他地方的「待決」「39 題」是定稿當時的狀態。
  HM-25（#129）合併時，它寫的「使用者還沒確認」跟著改成已定。第 7.1、7.2 節交主對話的 repo 外工具同日改好（`gen_trace.py` 五處、
  `negative_tests.py` 兩處改用 DQ-46、`SHA256SUMS`）：重產的 `deviation-trace.md` 逐位元相同，C1～C5、C7～C9 通過（C6 照舊），22 種改壞如期失敗。
- **只改文件**（`docs/` 17 個檔，含新檔 2 個：發版前預驗的紀錄與本筆記；審查後多改 `ledger-tracking.md` 一個）：程式、測試、`addons/`、README、版號、
  CHANGELOG、`upgrade-notes.yaml`、`.github/`、帳本與 tool-surface 都沒動；`MULTI_PROFILE_PRODUCTS` 維持空集合，沒有產品開通。
- **獨立審查**（2026-11-19，`wave5/review-HM-18-correctness.md`，修正後通過）：必修 3 項、建議 10 項（S-9 含三件）、小地方 8 項全部照改
  （N-8 只在本筆記寫決定），沒有不採用的；逐項見第 13 節。
- **契約定稿**（`docs/multi-profile/contract.md`，R1 用）：新的第 1.4 節是計畫 §7.2 的完整清單（開通後預設帳號會變的事，20 點加「不變的」），
  收進 HM-10 審查 S-6 的兩個位元組變化（PATCH、DELETE 沒過 identity 從 405 變 403；表外方法的 `Allow` 從 4 個方法變 6 個，本機核對過）；
  第 9 節跟上 2026-11-17 的決定與 HM-03a 的實測，#50、#60、#85 的類型不再是「待決」；還待決、不擋 R1 的列（#10、#28、#47、#62、#65）
  列在第 10 節的 HM-18 定稿列（審查修正另記一列）。#75 早已是 60 分鐘（HM-10 rebase 的 `b51cf8c`），沒再改。
- **交升版片**：兩個位元組變化的 CHANGELOG 建議句與「開通那一版要寫的事」放在 `docs/multi-profile/unreleased-changes.md` 第 7 節（新）；
  同一個檔補上 #108、#112、#116、#109 合併時沒改的地方（共通項 A8、A9 與第 4 節）。
- **決策**（`docs/multi-profile/decisions.md`）：DQ-23、DQ-24、DQ-42、DQ-45（2026-11-17 13:5x）與 DQ-35（14:0x，「不承諾天數」）記成已定，
  39 題已定、7 題待定。HM-10 審查 S-5 定為**不補** `tests/contract/profiles_v1_cases.json` 的管理面案例（理由在第 5 節），檔案沒改。
  任務列的其他 DQ 與 HM-30 的 D1～D3 都已記過，沒改。
- **使用與維運文件**（`docs/operations/`、`docs/runtime-configuration.md`、`docs/management-capabilities-v1.md`）：都寫成「產品開通後」的語氣；
  `clients.md` 更正「Claude.ai 不能帶標頭」（能帶，但 Bearer 帶 Origin 403、送不送 Origin 等 S14，所以仍用密鑰網址）。
- **兩個更正**：`acceptance.md` 的 T-24 照 HM-27 定案改寫（S14 交 HM-19b）；HM-27 筆記第 6 節「真子程式由容器探針涵蓋」用有日期的第 21 節更正。
- **發版前預驗的紀錄**：`docs/operations/ha-test-odoo-multiprofile-early.md`（新），2026-11-19 Odoo 多帳號實測的摘要，明寫**不是 HM-19b 的證據**；
  `acceptance.md` 的多帳號狀態連過去，寫「發版前預驗；HM-19b 仍要在正式映像上重做」。
- **對照表**：`deviation-trace.md` 用 repo 外產生器的暫存複本重產（FM-28、FM-122、FM-128 的說明；第 118～128 列經 T-21、T-24 對到）；
  產生器與 `negative_tests.py` 要改的字交主對話（第 7 節）。HM-00 對照腳本 C1～C5、C7～C9 通過；C6 不過是既有的：本機唯讀 PaaS repo 的
  `origin/main` 前進到 `5ef1046`（K8s MCP），和本片無關（第 7.3 節）。
- **預檢**：秘密預檢 0 命中、帳本預檢 OK、`packaging/validate.py` PASS、packaging unittest 366 案 OK（5 個 root 才跑的 skip）；文件引用的五個
  測試檔 pytest 219 案全過（第 8 節）。
- **要負責人決定的**：緊急發版範本（`update-backup-rollback.md`）要預先核准；DQ-11 第二問等 S14（第 11 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-18（計畫 §12.3 HM-18 與它的 2026-11-16、11-17 的註；§6、§7.2、§7.4、§8.1、§8.4、§8.10；FM-35、48、55、72、78、94、121、122、125、126、127） |
| 分支 | `feat/ha-multiprofile-hm18-20261119`（一般 clone `ha-mp-hm18-20261119`） |
| 基準 | `claude-delivery` `c90b214`（#109 HM-16 合併後；#108、#112、#116 也已合併） |
| 依據 | 計畫 §12.3 HM-18；契約與各片筆記交給 HM-18 的事；`decisions.md`；計畫 §13 的 2026-11-17 註與進度紀錄；HM-03a／b 的實機結果（repo 外 `probe-haos/RESULTS-zh-TW.md`）；Odoo 多帳號發版前預驗（repo 外 `probe-haos/ODOO-MULTIPROFILE-20261119-zh-TW.md`） |
| 對齊的 PaaS | 沒有對齊新的 PaaS 行為（只改文件）；PaaS 的變動見第 7.3 節 |
| 受開關管 | 不適用（不改程式） |
| 合併順序 | 計畫 §12.2：HM-16（合併）→ HM-18 → HM-19a；`contract.md` 是 HM-00 → HM-10 → HM-18，`update-backup-rollback.md` 是 HM-13c → HM-18 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `docs/multi-profile/contract.md` | 第 4 節：定稿 |
| `docs/multi-profile/decisions.md` | 第 5 節 |
| `docs/multi-profile/unreleased-changes.md` | A8、A9、第 4.1、4.2 節補列、第 5 節第 3 點、第 6 節清空、第 7 節（新）、總表與各產品節跟上 0.4.14 已合併 |
| `docs/multi-profile/deviation-trace.md` | 第 7 節：重產 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表的狀態（檔已存在的「計畫」「新增」改成「已有」，56 列）；`tests/contract/profiles_v1_cases.json` 一列；檔頭狀態 |
| `docs/multi-profile/threat-model.md` | 檔頭與第 3、4 節的「HM-18 寫進文件／DOCS」改成已寫進的文件；暫時性錯誤那一條寫明 HM-18 不改程式；Bearer 帶 Origin 那條寫 S14 交 HM-19b |
| `docs/multi-profile/README.md` | 契約、威脅模型、`unreleased-changes.md` 三列 |
| `docs/multi-profile/ledger-tracking.md` | 審查 S-9 後才改（第 13 節）：`profiles.py` 一列拿掉「還沒合併」、`packaging/entrypoint.py` 移到第 2 節 |
| `docs/operations/clients.md` | 開頭的接法表與 legacy SSE（DQ-23）；「接法二」的 Claude.ai 更正；「多帳號（產品開通後）」一節；還原那一點 |
| `docs/operations/guide.md` | 「支援的 Core 版本」補 DQ-35；子程式 bearer 那段改成 0.4.14 起並補 n8n 與 Odoo Manage（HM-06 審查 S-07）；「多帳號（產品開通後）」一節 |
| `docs/operations/update-backup-rollback.md` | 版本混搭、還原後看 Origin 政策、開機守門的 log 表；「回退與緊急關閉（多帳號產品開通後）」一節與緊急發版範本 |
| `docs/runtime-configuration.md`、`docs/management-capabilities-v1.md` | 各加一節「多帳號（產品開通後）」（英文文件裡的繁中段落：照本線規則，repo 文件一律繁中） |
| `docs/operations/acceptance.md` | 多帳號的狀態（發版前預驗、HM-03a／b 寫回的項目）；T-24；「每次升版都要重驗」最後一點 |
| `docs/operations/ha-test-odoo-multiprofile-early.md` | 新檔（第 6.2 節） |
| `docs/provenance/ha-multiprofile-HM-27-20261117.md` | 結論最前面一行、第 21 節（2026-11-19 補記）；第 1～20 節沒改 |
| `docs/provenance/ha-multiprofile-HM-18-20261119.md` | 本筆記 |

沒改：程式、測試（含 `tests/conftest.py`、`tests/contract/profiles_v1_cases.json`）、`addons/`、README、版號、CHANGELOG、`upgrade-notes.yaml`、
`.github/`、`packaging/`、`features.py`（`MULTI_PROFILE_PRODUCTS` 仍是空集合）、帳本（`runtime-patches.json` 等）、tool-surface、`paas-test-mapping.md`、
repo 外的計畫、FEATURE-MATRIX 與 HM-00 工具（要改的字交主對話，第 7 節）。

## 3. 任務逐項與落點

| # | 交辦 | 落點 |
|---|---|---|
| 1 | 契約定稿；§7.2 的兩個位元組變化並交升版片；#75 改 60 分鐘；#85 的類型；歷史一列；找其他「待決」「HM-18」 | 契約第 1.4 節、第 3.1 節那一點、第 10 節最後一列；`unreleased-changes.md` 第 7 節。契約沒有第 7.2 節：交辦的「Section 7.2」是計畫 §7.2（repo 外），所以清單放進契約第 1.4 節，計畫 §7.2 本身沒改（交主對話，第 10 節）。#75 已是 60 分鐘。#85 改成「加嚴（建議回補）」。其他標記見第 4.3 節 |
| 2 | `profiles_v1_cases.json` 要不要補管理面的案例（HM-10 審查 S-5） | `decisions.md` 第 1.1 節 2026-11-19 那列；`acceptance-matrix.md` 登記表那一列；檔案沒改（第 5 節） |
| 3 | 使用與維運文件 | `clients.md`、`guide.md`、`update-backup-rollback.md`、`runtime-configuration.md`、`management-capabilities-v1.md`（第 6 節） |
| 4 | 2026-11-17 的決定與其他 DQ 的核對 | `decisions.md`（第 5 節） |
| 5 | T-24 與 HM-27 筆記第 6 節的更正 | `acceptance.md` T-24；HM-27 筆記第 21 節（第 6.3 節） |
| 6 | 2026-11-19 Odoo 多帳號實測的公開摘要 | `ha-test-odoo-multiprofile-early.md`；`acceptance.md` 的連結（第 6.2 節） |
| 7 | 功能對照表的狀態 | `deviation-trace.md` 重產；`acceptance-matrix.md` 登記表的狀態（第 7 節） |
| 8 | provenance 筆記 | 本筆記 |

## 4. 契約定稿

### 4.1 第 1.4 節（新）：開通後預設帳號會變的事

計畫 §7.2 原本 11 點。照各片的實作與交接補齊成 20 點，分面板與管理 API、8081、子程式與健康檢查、後端設定、資料與還原五組；每點指到契約裡寫細節的節：

| 來源 | 補了什麼 |
|---|---|
| 計畫 §7.2 第 1～11 點 | 照實作改寫（例如第 3 點的位元組額度：HM-31 起預算開關開與關都有，開通後變的是推導用的帳號數，份額可能變小，第 7 點） |
| HM-10 審查 S-6 | 第 4 點：兩個位元組變化 |
| HM-09 審查 S-8（HM-09 筆記第 13.2 節的六點） | 第 11～14 點：認證被拒的退避、port 3000 的 spawn 前檢查、`blocked_reason`、生命週期 WARNING、spawn 失敗照退避、子程式不在 `running` 時不探測 |
| HM-08、HM-09 | 第 15 點：FD 不夠時只服務預設帳號 |
| HM-11 | 第 1 點：第一個 bootstrap 的 400、帳號選擇只放記憶體 |
| HM-12、HM-12 面板 | 第 16 點：換身分換權杖的條件、409、503 與重啟後確認網址；預設帳號結果不明時 8081 全部 503 |
| HM-13b、HM-13c | 第 19、20 點：sentinel 兩檔、有帳號資料時還原連預設帳號一起撤銷、核對後才重發、收據換新 |
| HM-20 | 第 18 點：後端網址不能填 loopback（含開通前存的 loopback 網址） |
| HM-27 | 第 10 點：would_deny、壞檔時每個帳號 503、關掉後 enforce 靜默失效、還原帶回舊政策 |
| HM-30 | 第 7、9 點：待送回覆、工作執行緒 |

兩個位元組變化的本機核對（暫存區的腳本，不進 repo；`PYTHONPATH=packages/mcp-admin-core`）：`gateway.management_app` 用沒開通的方法表
（`MANAGEMENT_METHODS`）與開通後分派器的方法表（`profile_router.ALL_METHODS`）各建一次，送 OPTIONS、TRACE：兩種都是 405 `Method Not Allowed`，
`Allow` 沒開通是 `GET`、`HEAD`、`POST`、`PUT`，開通是加上 `PATCH`、`DELETE` 的六個（順序是集合順序）。PATCH、DELETE 在開通後先過 identity
（outside caller 403）的斷言已在 `tests/test_admin_pipeline_matrix.py::test_the_dispatcher_routes_every_route_of_its_table`；表外方法的 `Allow`
沒有測試斷言（第 10 節）。

### 4.2 第 9 節逐列

| # | 原本 | 現在 | 依據 |
|---|---|---|---|
| 5 | 理由「DQ-24 待定」 | DQ-24 已定：端點細節維持 HA | 2026-11-17 13:5x |
| 6 | 理由「DQ-23 待定，建議不支援」 | DQ-23 已定：不支援、文件寫明（`clients.md`） | 同上 |
| 50 | 待決：看 UC-10 | 部署：HM-03a 實測 Ingress 照原樣轉 `X-MCP-Profile` 與 PATCH、DELETE，第 3.7 節的備援不做；每次升版重驗 | HM-03a（2026-11-18，HAOS 18.1、Supervisor 2026.11.0；echo add-on 收到的方法、標頭、內容都原樣） |
| 55 | 「`task()` 期間選單停用」 | 其他操作進行中選單停用；切換中只剩選單可用，再選一次取代前一次切換 | HM-11 審查 S-3（交 HM-18 的用字）；照 `Hui/app.js` 的 `onProfileChange`、`renderLoading` 核對過 |
| 56 | 理由「DQ-31 面板細節待定」 | DQ-31 已定 | 2026-11-15 17:4x |
| 60 | 待決（DQ-30 待定） | 既有：DQ-30 已定，首發維持 1 | 同上 |
| 84 | — | 補「得知帳號已刪的每一條路徑都清」 | HM-11 筆記第 3.3 節的五條 |
| 85 | 待決（DQ-31）；HA 欄寫「暫定」、行號過時 | 加嚴（建議回補）；HA 欄照 HM-11 的實作（`Hui/profiles.js` 的 `clientName`：額外帳號 `woow-<產品>-<id 前 8 碼>`，預設帳號 `woow`） | DQ-31（2026-11-15）；文件同步交來（計畫 HM-18 段 2026-11-17 的註） |
| 87 | 「待 HM-03a 實測」 | 寫 HM-03a 量到的 soft 1024、hard 524288（提得上去），其他主機照樣讀、不假設 | HM-03a（同上） |
| 75 | 交辦要改成 60 分鐘 | 不用改：已是「上限 60 分鐘（DQ-43，2026-11-15 定案，PR #100）」 | HM-10 rebase 的 `b51cf8c`；`.github/workflows/woow-addon-release.yml` 的 `checks` 是 `timeout-minutes: 60` |

列沒有加、沒有改號（128 列）。

### 4.3 其他「待決」與「HM-18」標記

| 位置 | 處理 |
|---|---|
| 第 2.4 節「HM-18 寫進 DOCS」（排隊中斷線看不到的兩種情況） | 寫進 `guide.md` 已知限制；契約改成已寫進的文件 |
| 第 2.6 節「交 HM-18 寫進 DOCS」（關掉後 enforce 靜默失效） | 寫進 `guide.md`、`update-backup-rollback.md`；契約跟著改 |
| 第 2.6 節 DQ-11 第二問「待 S14（HM-03b／HM-19b）」 | HM-03b 沒做 S14，改寫成由 HM-19b 量；仍待決（第 10 節） |
| 第 3.1 節「交 HM-18 或升版片」（兩個位元組變化） | 第 1.4 節第 4 點與 `unreleased-changes.md` 第 7 節 |
| 第 6 節「DOCS 由 HM-18 寫」（D2） | 寫進 `guide.md` 已知限制 |
| §9 #10 類型「第二問待決」 | 留著：S14 之後才定 |
| §9 #28、#62（DQ-22）、#47 與第 8 節（DQ-04） | 留著：n8n，HM-25 前定 |
| §9 #65（DQ-27） | 留著：EMQX，HM-23 前定 |
| §9 #89 理由「待 HM-03a 實測」（IPv6 試綁被平台擋） | 留著：HM-03a 沒量這一項 |
| §9 #111 理由「待 HM-03a」（`ETag` 回應標頭經 Ingress） | 留著：HM-03a 沒量；發版前預驗看到照轉（建立帳號要用清單的 `ETag`，經 Ingress 成功），但那不是 HM-19b 的證據，等 HM-19b 在正式映像上確認再改 |
| 第 5、6 節「暫定，HM-19c 量測後定案」 | 留著：HM-19c |
| 第 10 節歷史列裡的「HM-18」 | 歷史，不改 |

另外照 HM-11 的交接（HM-11 筆記第 13、16.11、17.8 節）補：第 3.3 節第一個 bootstrap 的探測例外、第 3.5 節「全域收據沒有查詢路徑」（規則不變）。

## 5. 決策紀錄（`decisions.md`）

- **2026-11-17 13:5x、14:0x**（計畫 §13 的註原文：「DQ-23 不支援舊版 SSE、文件寫明；DQ-24 端點細節維持 HA 現行；DQ-42 每次發版都在模擬舊 CPU
  （QEMU `-cpu Nehalem`）上跑一次 J1900 指令集檢查；DQ-45 額外帳號的 `serverInfo.name` 不改。都照計畫建議。DQ-35：主對話補說明前因後果後，使用者
  14:0x 選「不承諾天數」」；進度紀錄 11/17 13:0x～14:3x 那一段同）：五題移到第 1 節，狀態寫日期與依據（「使用者採用建議」或「使用者選」，C8 收的寫法）。
  DQ-35 的 DOCS 要求（「Core 升級到沒審過的版本時管理頁會鎖住、MCP 照常、等 add-on 新版」）寫進 `guide.md`「支援的 Core 版本」。
- **HM-10 審查 S-5**（第 1.1 節 2026-11-19 那列）：`tests/contract/profiles_v1_cases.json` **不補**管理面的案例。理由：它是 HM-01 的守門檔，格式只描述 8081
  （HM-08 用它對每個帳號跑，`tests/test_profile_routing.py`）；管理面已有三層：路由表自動產生的否定矩陣（`tests/test_admin_pipeline_matrix.py`）、
  HM-01 的 8099 凍結（`tests/test_admin_contract_freeze.py`）、面板用到的每個開通後管理回應錄自真的 8099 app（`tests/test_panel_profile_api_shapes.py`＋
  `packages/mcp-admin-ui/tests/profile-api-cases.json`）。逐項核對沒找到只有資料檔才擋得住的缺口；附帶查到的 8099 缺口（表外方法的 `Allow`）屬 8099
  測試，交後面的片（第 10 節）。誰定：計畫的 2026-11-16 註寫「交 HM-18 決定」，本片照主對話當時的方向定。
- **核對**：DQ-09、DQ-12（2026-11-14 21:5x）、DQ-13、DQ-14、DQ-30、DQ-31（2026-11-15 17:4x）、DQ-19（2026-11-14 21:5x）、DQ-38（21:5x，補充 2026-11-15 08:2x）、
  DQ-43（2026-11-15 18:1x）、HM-30 的 D1～D3（2026-11-16 14:0x）都已記在第 1、1.1 節，日期和計畫 §13、進度紀錄相同（進度紀錄寫 17:4x 的四題，
  使用者記憶裡寫 17:5x，以進度紀錄為準），沒改。

## 6. 使用與維運文件

### 6.1 寫了什麼（對到的 FM）

| 文件 | 內容 | FM |
|---|---|---|
| `clients.md` | 每個帳號一把權杖、兩條網址（Bearer 與 `/private_<token>/mcp`）、端點全域、只看權杖選帳號、範例名稱帶帳號 id、一個代理只接一個帳號、Claude.ai 兩個帳號各一個連接器、legacy SSE 不支援、密鑰網址的 Origin、忙碌與中斷的 JSON-RPC 代碼；Claude.ai 能帶標頭的更正 | FM-28、35、63、122、123 |
| `guide.md` | 帳號與上限、一組管理身分管全部帳號、同 uid＝完全控制、六步事故處理、換身分換權杖、新來源重填秘密、503 與預設帳號結果不明、刪除與孤兒與隔離、`profiles/` 壞掉要重啟、FD 不夠不能新增、健康與 log（含 Odoo 的登入冷卻參數、`oom_score_adj` 不是保證、console 的 400）、Origin、已知限制；DQ-35；子程式 bearer（n8n 收下的三種寫法、Odoo Manage） | FM-48、55、78、121、122、127 |
| `update-backup-rollback.md` | 版本混搭、還原後看 Origin 政策、守門每一行 log 的意思與處理、計畫 §7.4 的三條路與時間、緊急發版範本、還原涵蓋範圍（沿用 HM-13c 已寫的「涵蓋範圍」與「回退後再升級」兩點，不重寫） | FM-125、126 |
| `runtime-configuration.md`、`management-capabilities-v1.md` | 照契約：每個帳號一份設定、`X-MCP-Profile`、回聲、帳號 ETag、端點全域、權杖各自撤銷、換身分換權杖、新來源、loopback、還原後先核對；全域路由、帳號範圍路由、管線、各產品上限、新錯誤代碼 | FM-72、94 |

產品的 DOCS 與 README 在 `addons/<產品>/`，只在升版 PR 改（計畫 §11.1）：本片寫的是 repo 層的文件，`unreleased-changes.md` 第 7 節交升版片照這些段落改寫產品 DOCS。

### 6.2 發版前預驗的紀錄（`ha-test-odoo-multiprofile-early.md`）

- 摘自 repo 外的 `probe-haos/ODOO-MULTIPROFILE-20261119-zh-TW.md`（2026-11-19 主對話在展示機做的實測）。開頭與結尾都寫明：本機建的映像、本機 add-on、
  不經商店、不在目標硬體，不是 HM-19b 的證據，HM-19b 要在正式映像上重做。
- 公開 repo：不寫主機名稱、帳號（含測試使用者的名字）、網址、資料庫名稱、帳號 id、token 的雜湊、備份代號、IP 或網段；本機 add-on 的 slug、映像 digest
  也拿掉。寫完用規則掃過（主機名稱、`.io`、網址、IPv4、8 碼 hex、`@`、測試庫與使用者的名字）：0 命中。
- 清理那一段照負責人 2026-11-19 的指示補寫：測試前的保護備份也已刪除，這條線沒有在展示機留下備份。
- 「順便看到的」：建立帳號經 Ingress 成功，表示這台的 Ingress 照轉 `ETag` 回應標頭；契約 #111 等 HM-19b 確認再改（第 4.3 節）。

### 6.3 兩個更正

- `acceptance.md` T-24：原本只寫「HA：記下 Claude.ai 送的 Origin」與「密鑰網址清單外只記 would_deny、不擋；Bearer 帶 Origin 403」，是 HM-27 定案前的寫法。
  改成：預設清單有 `https://claude.ai`，Claude.ai 送它時不會有 would_deny 行；S14 交 HM-19b 用 echo 端點；通過標準照矩陣 T-24（HM-27 定案的
  enforce、壞檔 503、還原後的政策）。HM-16 疊到 HM-27 上時（HM-16 筆記第 21.5 節）交下來的。
- HM-27 筆記第 6 節：「真子程式由 HM-16 的容器探針涵蓋」說得太滿（探針不送 `Origin`、不驗政策，只收檔名）。照交辦不改原文，加第 21 節（2026-11-19 補記）
  寫實際的涵蓋，結論最前面加一行指到它。

## 7. 功能對照表

### 7.1 `deviation-trace.md` 重產

- 本片改的決策讓三格說明過時：FM-122（「DQ-45 待定」）、FM-128（「DQ-35 待定」）、FM-28（「由 HM-18 更正 `clients.md`」）。
- repo 外的產生器（`wave0/hm00-check/gen_trace.py`，`5eb30044d99e5136`）照原樣已經跑不起來：契約第 9 節的第 118～128 列（HM-13b、HM-13c、HM-27）
  合併時沒有重產，產生器要求「沒對到的列要寫出處」，直接失敗（`沒對到的列要寫出處：缺 [118, …, 128]`）。
- 做法（照 2026-11-17 文件同步的方式，但不改 repo 外的檔）：把產生器複製到暫存區，只改五處（下方），用 artifacts 裡的 FEATURE-MATRIX 與 G6（唯讀）和本 clone
  的契約重產，輸出寫回 `docs/multi-profile/deviation-trace.md`。和 `c90b214` 的檔相比只差：檔頭兩行、結論的列數、FM-28、FM-122、FM-128 的說明、
  T-21 與 T-24 的「對到」、反查表多 #118～#128 十一列（都由 T-21、T-24 對到，沒有新的出處）。產出 `5f4309aed2f3d53d…`（前 16 碼）。
  1. T-21 對到 #20、#21 → 加 #118～#123（同 `acceptance-matrix.md` 的 T-21）。
  2. T-24 對到 #9、#10、#42 → 加 #124～#128（同矩陣的 T-24），測試的「HM-27，暫定名」→「HM-27」（HM-27 筆記第 13 節交辦）。
  3. FM-28 的說明：「已由 HM-18 更正（`docs/operations/clients.md`，2026-11-19）；Claude.ai 送不送 Origin 等 S14」。
  4. FM-122、FM-128（「—」列的結論）：DQ-45、DQ-35 已定的日期與結論。
  5. 檔頭：補「2026-11-19 HM-18 重產」一句與本筆記；原本用 `{max(contract)}` 寫的「2026-11-17 文件同步重產（…第 87～N 列…）」改成寫死 117（那一次只到 117）。
- **交主對話**（repo 外，本片不改）：把同樣五處改進 `gen_trace.py`、更新 `SHA256SUMS`，之後用裝好的產生器重產會和 commit 的檔逐位元相同
  （暫存區改過的產生器 `3556d8a46b95a61b…`）。不改的話，下一次重產會在第 118～128 列失敗。

### 7.2 HM-00 對照腳本與負向測試

- `check_hm00.py`（repo 外，沒改；`--base origin/claude-delivery --source-base bb48449`，`--paas` 指唯讀 worktree）：
  - 基準 `c90b214`：C1 不過（還沒有變更）、C6 不過（第 7.3 節），其他通過。
  - 本片：**C1～C5、C7～C9 通過**；C8 是「46 題；已定 39 題（§13.1 採用 16、§13.2／§13.3 23，其中依 DQ-40 (a) 7）；待定 7 題（§13.2 0、§13.3 7）」；
    C2 128 列、類型都合法；C3 112／112；C5 登記 71 個測試檔；C6 同基準不過。
- `negative_tests.py`（repo 外）：照原樣在第 11 種改壞停下（`沒改到`：它要找還在待定的 DQ-42，DQ-42 已定）。這和 2026-11-17 文件同步遇到 DQ-13 的情形一樣。
  暫存區改兩處後 22 種改壞**全部如期失敗**：「待定沒有負責片」改用 DQ-04（§13.3、HM-25）；「§13.3 的題放進第 2 節」改成插在第 2 節表頭的分隔線後面
  （第 2 節現在沒有任何一列）。兩種 C6 的改壞會「如期失敗」部分是因為既有的 C6 不過，不算有效的驗證。**交主對話**把這兩處改進 repo 外的檔。

### 7.3 `paas-test-mapping.md` 沒重產

- 本片的改動不影響它（沒有加差異表的列、沒有改測試檔）。
- C6 不過是既有的：本機唯讀 PaaS repo 的 `origin/main` 是 `5ef1046`（2026-11-18，PaaS #157～#159：K8s MCP 的安全對齊、上游 v0.1.3、刪帳號清 kubeconfig），
  比對照表的基準 `48f394d` 多 6 個 K8s 測試檔（54 案）。`48f394d..5ef1046` 的正式碼只在 `apps/k8s/`；共用核心 `packages/mcp-admin-core/mcp_admin_core/`
  沒變（核心只改了三個測試檔）。HA 沒有 K8s 產品，歸屬會是「不適用」，但補規格要改 repo 外的 `paas_mapping_spec.py`（`POST_PIN_NOTES`、
  `POST_PIN_SUMMARY`），**交主對話**。

### 7.4 `acceptance-matrix.md` 登記表

HM-08、HM-14 交 HM-18「登記表的『計畫』狀態一起更新」：照 `c90b214` 核對，檔已存在的 56 列由「計畫」「新增」（含括號的 root、資料、工具）改成「已有」；
還不存在的（`tests/test_child_identity.py` 與 6 個產品片的暫定名）照舊。C5 只要求「既有」的檔存在，「已有」不受影響。

## 8. 本機檢查（2026-11-19，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪掉）

| 檢查 | 結果 |
|---|---|
| 秘密預檢（`python3 scripts/secret_precheck.py --tools …/scratchpad/scan0414/tools`） | gitleaks 8.28.0（釘選、驗過）；`c90b214..e490bcd` 4 個 commit：**OK，0 命中**。本筆記的 commit 之後再跑一次（結果寫在回報） |
| 帳本預檢（`python3 scripts/ledger_precheck.py`） | 三本帳本 0 drift、0 missing；相對 `origin/claude-delivery` 15 個檔（本筆記之前），沒有列管檔、帳本沒改、沒有新的執行期檔：**result: OK**。本筆記的 commit 之後再跑一次（結果寫在回報） |
| `packaging/validate.py`（`ha-gh-release-20261117` 的 venv，有 PyYAML） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv，`-m unittest discover -s packaging -p 'test_*.py'`） | `Ran 366 tests`、`OK (skipped=5)`，約 26 秒；5 個 skip 是既有的 `skipUnless(root)` |
| pytest（`.venv/bin/python -m pytest -q -p no:cacheprovider`；排在共用鎖 `scratchpad/wave1-pytest.lock` 後面：09:20:50 排隊、09:25:28 拿到、09:26:17 放掉） | 本片不改程式與測試；跑文件引用的五個檔：`test_admin_pipeline_matrix.py`、`test_admin_contract_freeze.py`、`test_mcp_contract_freeze.py`、`test_panel_profile_api_shapes.py`、`test_origin_policy.py`：**219 passed**，48 秒。黃金回歸與 `test_upgrade_zero_rewrite.py` 沒跑（沒有改執行期程式） |
| node（面板） | 不適用：面板與它的契約沒改 |
| HM-00 對照（C1～C9） | 第 7.2 節 |
| 雙向控制字元與控制字元（改到的檔，含本筆記） | 0 |
| 公開紀錄的私有資料掃描（`ha-test-odoo-multiprofile-early.md`） | 0（第 6.2 節） |
| 兩個位元組變化 | 本機核對過（第 4.1 節） |

## 9. 只在 CI 跑的、`checks` 秒數

- CI（root、0 skip）照常跑全套；本片只改文件，預期和基準一樣。要 root 的測試（`test_root_*` 等）本機沒跑，本片也沒有改到它們涵蓋的東西。
- `checks` 秒數：開 PR 後補在 PR 說明。

## 10. 交給後面的片、還沒解決的事

- **主對話（repo 外）**：
  - `gen_trace.py` 的五處（第 7.1 節）、`negative_tests.py` 的兩處（第 7.2 節）、`SHA256SUMS`；`paas_mapping_spec.py` 補 PaaS `5ef1046` 的 K8s 測試檔（第 7.3 節）。
  - 計畫 §7.2：清單現在在契約第 1.4 節（20 點），計畫可以改成指到它，並補兩個位元組變化；計畫 HM-18 段可以記本片做完。
  - 計畫的兩句跟著審查改（第 13 節）：§8.10 第 5 步「（守門會撤銷 token）」要加「備份裡有帳號資料時」與沒有時的做法（MF-2）；§7.4「(a) 之後再升級：
    舊 entrypoint 只修擁有者、不建標記」只對 0.4.13（Headscale 0.4.18）以前成立，0.4.14 起的舊版建標記（S-5）。
  - 審查請主對話確認：`profiles_v1_cases.json` 不補管理面案例（偏離計畫 §10.3；計畫交 HM-18 決定，理由在第 5 節）。
- **HM-19a**（Odoo 首發的升版 PR）：照 `unreleased-changes.md` 第 1 節（A8、A9）與第 7 節寫 CHANGELOG、DOCS、`upgrade-notes.yaml`；照 `update-backup-rollback.md`
  的緊急發版範本核對一次、交負責人預先核准；容器驗收的多帳號階段第一次真跑。
- **HM-19b**：S14（Claude.ai 的 Origin，echo 端點）與 DQ-11 第二問；契約 #111（`ETag` 經 Ingress）、#89（IPv6 試綁）在正式映像上確認後改理由欄；
  完整還原、主機重開、T-11、T-12、T-20 的回退演練、T-24；回退與版本混搭照 `update-backup-rollback.md`（審查 MF-3 後寫了期望值：還原後先記下
  add-on 的版本，Supervisor 會換回備份當時的版本）。
- **8099 測試的缺口**：開通後表外方法（OPTIONS 等）的 405 `Allow` 是 6 個方法，沒有測試斷言（行為本機核對過）。下一個動 8099 測試的片在
  `tests/test_admin_pipeline_matrix.py` 補一案（開關關 4 個、開 6 個；順序不固定，比集合）。
- **面板的 Claude.ai 卡片**仍寫「Claude.ai 網頁版的自訂連接器無法帶 Authorization header」（`Hui/app.js`、`Hui/contracts.js` 的註解）：本片只改文件。
  要改面板的字，等 S14 結果一起改（另開一片，帳本照規則重算）。
- **HM-13b 審查 S-4**（暫時性錯誤讓好的帳號被隔離）：HM-18 只改文件，寫明「同一份備份再還原一次就會重做」；要不要改 `Store` 帶出原因、把暫時性錯誤改成這次開機停下，
  動到所有產品共用的 `config.py`，交主對話另開一片。
- **容器探針與 Origin**：要不要讓容器探針送一次帶 `Origin` 的請求（report-only、enforce 各一次），交下一個改探針的片或 HM-19a（HM-27 筆記第 21 節）。
- **HM-27 審查建議 3**：還原後 Origin 政策靜默回到備份當時的值，要不要在核對卡或還原提示加一句，仍由主對話決定；本片照交辦寫進 DOCS。
- `unreleased-changes.md` 第 4 節那句「多帳號基礎」的新 PR 清單（#108、#112、#116）是建議句，最後的英文由發版片定。

## 11. 要負責人決定的事

- **緊急發版範本**（`docs/operations/update-backup-rollback.md`「緊急發版範本（關閉版）」）：計畫 §7.4 要「預先核准」，出事時只填版號。本片寫好了範本，
  還沒經負責人核准；HM-19a 照它核對一次後交負責人。
- **DQ-11 第二問**：S14（HM-19b）量到 Claude.ai 送的 Origin 之後，Bearer `/mcp` 要不要精確放行 `https://claude.ai`。

## 12. commit

| commit | 內容 |
|---|---|
| `42478b9` | 契約定稿、`decisions.md`、`deviation-trace.md` 重產、`acceptance-matrix.md`、`threat-model.md`、`README.md` |
| `c7a3fe3` | `unreleased-changes.md`：A8、A9、第 4、5、6 節、第 7 節（新） |
| `d836915` | `docs/operations/` 五個檔（含新的發版前預驗紀錄）、`runtime-configuration.md`、`management-capabilities-v1.md` |
| `e490bcd` | HM-27 筆記第 21 節（2026-11-19 補記） |
| `b1f5eca` | 本筆記；`guide.md` 一句（預設帳號不能改名或刪除） |
| 審查後第 1 個（`bec7054`） | 照獨立審查改 11 個文件（第 13 節） |
| 審查後第 2 個（`d123173`） | 本筆記：第 13 節與結論、第 2、10、12 節；`guide.md` 生命週期 log 表 `not started` 那一格（寫明哪些情況不會自己重試：記憶體不夠、帳號清單標了 `disabled_reason`；第 1 個 commit 之後再核對 `lifecycle.py` 的 `block` 補的） |
| 定案補記（2026-11-19，負責人定 DQ-04、DQ-22 之後） | `decisions.md`；`contract.md` 開頭、第 4.2、8、9、10 節；本筆記結論第一點與本列 |

commit 身分都是 woowtech；英文標題、繁中內文；訊息裡沒有任何署名行。定案補記的 commit 的 SHA 寫在回報（同一個 commit 寫不進自己的 SHA）。

## 13. 審查與處理（2026-11-19）

- 報告：repo 外 `artifacts/ha-multiprofile-parity-20261114/wave5/review-HM-18-correctness.md`（獨立審查代理，審 `b1f5eca`）。判定「修正後通過」：
  必修 3 項、建議 10 項、小地方 8 項。
- 處理：全部照改，沒有不採用的。改之前逐項對 `c90b214` 的程式核對過審查寫的事實（`restore_lock.py` 的 `guard`、`archive`、log 常數，
  `operations.archive_for_restore`、`admin_auth.prefix`、`gateway.py` 的 `BadRequest` 回應、`run_product.py` 讀還原提示、`lifecycle.py`、
  `profile_admin.py`、`tests/test_restore_lock.py`、`tests/test_upgrade_zero_rewrite.py`），都成立。
- 範圍照舊：只改 `docs/`；程式、測試、`addons/`、README、版號、帳本都沒動。

| id | 審查說的 | 處理 | 在哪裡 |
|---|---|---|---|
| MF-1 | A8 寫「`/data/mcp` 其他一個位元組都不動」，和 A9 的 `restore-notice.json` 矛盾 | 照改：中文與英文建議句都寫「存 A9 的還原提示，除了這個檔其他都不動」；`MARKER_LEFT` 那句補「還原提示存不下」 | `unreleased-changes.md` A8 |
| MF-2 | 事故處理第 5 步寫成還原後一定撤銷每個帳號 | 照改：分成備份有帳號資料（撤銷、核對後重發）與沒有帳號資料（預設帳號不撤銷，DQ-03 (b)：照提示立刻重新產生或再按全部撤銷）；補「還原帶回備份當時的憑證、網址與政策，重做第 2、3 步」。來源句一起改 | `guide.md` 事故處理；`threat-model.md` 第 4 節第 5 步 |
| MF-3 | 緊急關閉版上還原開通版本的備份，漏了 Supervisor 會換回開通的那一版 | 照改：寫明會換回出事的那一版、守門照那一版跑、**還原後立刻再更新到緊急關閉版**、拉不到舊映像時是關閉版直接跑；HM-19b 版本混搭演練補期望值 | `update-backup-rollback.md`「版本混搭」 |
| S-1 | 「定稿之後改本檔的只有」漏了 HM-19b | 照改：改成「主要是」並加 HM-19b（#89、#111 的理由欄）；`README.md` 那列同 | `contract.md` 開頭；`docs/multi-profile/README.md` |
| S-2 | 第 9 節開頭還說第 118～128 列不在 `deviation-trace.md` | 照改：寫成 HM-18 重產後經 T-21、T-24 對到 | `contract.md` 第 9 節開頭 |
| S-3 | 第 1.4 節少三件 | 照改：第 20 點補「開通而沒有帳號資料的還原也寫 `restore-record.json`（預設帳號記為保留、不用核對），並換新索引旁與 Origin 政策旁的收據檔」（`guard` 的 `cutoff` 那段用 `renew_missing`）；第 19 點補兩個收據檔；第 5、10、19 點標「Headscale 除外」；`unreleased-changes.md` 第 7 節跟著寫 | `contract.md` 第 1.4 節；`unreleased-changes.md` 第 7 節 |
| S-4 | 「每一行守門 log」的表不全；生命週期 log 清單沒寫 | 照改：守門的表補齊 `restore_lock.py` 其餘 9 行（含 `profiles` 不是目錄時單獨一行），寫明哪些後面會接 `not finished`；另一張表列 `profile_admin` 的 4 行（審查說的 3 行加「全部撤銷結果不明」）。`guide.md` 加生命週期 log 常見 10 行與幾行不帶 `MCP child` 的，完整清單指到契約第 7 節 | `update-backup-rollback.md`「開機守門的 log」；`guide.md`「健康、重啟與 log」 |
| S-5 | 「舊版不建還原標記、新版看不出曾經還原」對 0.4.14 起的版本不成立 | 照改：「涵蓋範圍」「回退後再升級」「版本混搭」第一點、「(a) 之後再升級」都照版本分開寫：0.4.13（Headscale 0.4.18）以前不建標記；0.4.14（Headscale 0.4.19）起建標記，到含守門的版本才提示、不撤銷。契約 #69 的理由是同一件事，一起改（項目、類型不變，`deviation-trace.md` 不受影響） | `update-backup-rollback.md`；`contract.md` #69 |
| S-6 | 緊急發版範本少了釘住開通集合的測試 | 照改：加 `tests/test_upgrade_zero_rewrite.py` 的 `test_multi_profile_is_switched_off_for_every_product`；開通片為開通改過的其他測試也改回，HM-19a 核對範本時列全 | `update-backup-rollback.md` 緊急發版範本 |
| S-7 | 「全部撤銷沒做完時，只有沒撤銷成功的帳號 503」不完整 | 照改：獨立成一點，補「連一個結果都沒有時，每個帳號撤銷前的權杖都 503」與那行 log | `guide.md`「健康、重啟與 log」 |
| S-8 | 已知限制的停頓數字是 HM-30 第一輪的 | 照改：8 MiB 長字串約 20～50 ms；補沒有物件也沒有數字的大陣列 0.03～0.19 秒（負責人 2026-11-17 接受，HM-19c 量） | `guide.md` 已知限制 |
| S-9 | 區塊層級回滾、時鐘依賴沒寫進操作文件；`ledger-tracking.md` 過時 | 照改：`guide.md` 已知限制加兩點、`update-backup-rollback.md` 加「快照還原看不到」、威脅模型偵測那條補一句；`ledger-tracking.md` 第 1 節 `profiles.py` 拿掉「還沒合併」，`packaging/entrypoint.py` 從第 3 節移到第 2 節（帳本 `runtime-patches.json` 早已列它；HM-13a 筆記第 11 節的交接） | `guide.md`、`update-backup-rollback.md`、`threat-model.md`、`ledger-tracking.md` |
| S-10 | 開通那一版的交接沒點名 FM-94 會變錯的句子 | 照改：第 7 節逐一列出根目錄 README 第 46～47 行、各產品 DOCS 的「一個 Add-on 只有一組後端」（Nextcloud、Headscale 的寫法）、n8n DOCS 第 55 行、Nextcloud `config.yaml` 的 `description`、面板 `contracts.js` 的 Headscale 說明 | `unreleased-changes.md` 第 7 節 |
| N-1 | `unreleased-changes.md` 兩處用字 | 照改：#108 不受開關管；`.revoke-all-pending` 不看帳號資料、但只有開通的路由寫得出 | `unreleased-changes.md` 第 4.1 節、第 4 節最後一段 |
| N-2 | 沒過 identity 不一定是 403 | 照改：`X-Ingress-Path` 格式錯時是同一個本體的 400（只有 Supervisor 自己的位址送得到） | `contract.md` 第 1.4 節第 4 點；`unreleased-changes.md` 第 7 節英文句；`management-capabilities-v1.md` |
| N-3 | 「形狀 D」在這份文件沒有定義 | 照改：寫成同一份文件上面那種 HTTP 503（`saved:true`、`config_apply_failed`）另帶 `token_rotated:true` | `runtime-configuration.md` |
| N-4 | 公開紀錄寫了展示機 Odoo 的存取設定與加固細節 | 照改：改成概括的寫法（網路限制、一般的刪除方式不能用、改回的設定） | `ha-test-odoo-multiprofile-early.md` |
| N-5 | 還原說明少「還原後跑的版本沒開通而有帳號資料」 | 照改 | `clients.md` |
| N-6 | 各產品上限沒標暫定 | 照改 | `guide.md` |
| N-7 | 第 9 節 HM-18 那段的待決列漏 #28 | 照改；「第 10 節最後一列」三處改指 HM-18 的列（審查修正另記一列） | `contract.md` |
| N-8 | HM-10 筆記交 HM-18：S-14（名稱檢查綁執行中 Python 的 Unicode 資料）要不要寫進 DOCS | 決定不寫進操作文件：使用者碰不到。Unicode 指派過的字不會再變未指派；舊 Python 讀到新 Python 寫的名稱只會在還原舊備份時，帶回的索引是當時驗過的；商店不收降版（理由同 HM-10 筆記第 13.1 節）。名稱規則本身在契約第 3.6 節 | 本筆記 |

另外，審查請主對話確認 `profiles_v1_cases.json` 不補管理面案例（第 5 節的決定）；計畫 §8.10、§7.4 的兩句也要跟著改（repo 外）：都寫在第 10 節。

### 13.1 審查修正後的檢查（2026-11-19，一般使用者 uid 1000；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，跑完用完整路徑刪掉）

| 檢查 | 結果 |
|---|---|
| HM-00 對照 `check_hm00.py`（repo 外、唯讀；`--base origin/claude-delivery --source-base bb48449`，`--paas` 指唯讀 worktree） | C1～C5、C7～C9 **PASS**（C1：17 個檔、`docs/` 以外 0；C2 128 列類型合法；C8 46 題、已定 39、待定 7）；C6 照舊不過（第 7.3 節：PaaS `main` 前進到 `5ef1046`，和本片無關） |
| `deviation-trace.md` 能不能照新契約重產 | 用審查者暫存區改過五處的產生器複本（SHA-256 `334b695a…`，改法同第 7.1 節）讀審查修正後的契約重產：和 commit 的檔**逐位元相同**（`5f4309ae…`）。第 9 節開頭與 #69 理由欄的改動不影響對照表 |
| `scripts/ledger_precheck.py` | 三本帳本 0 drift、0 missing；17 個檔沒有列管檔、帳本沒改、沒有新的執行期檔：**result: OK** |
| `packaging/validate.py`（`ha-gh-release-20261117` 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv） | `Ran 366 tests`、`OK (skipped=5)`，27 秒；5 個 skip 是既有的 `skipUnless(root)` |
| pytest | 不適用：只改文件，沒有測試讀這些文件（`grep` 過 `tests/`、`packaging/`、`scripts/`）。另外排隊重跑文件引用的 7 個檔（第 8 節的 5 個加 `test_restore_lock.py`、`test_upgrade_zero_rewrite.py`）：第一次 repo `conftest.py` 的本機測試鎖被別的工作線的全套 pytest 佔住，120 秒後每一案都是 setup error（354 個 error，沒有任何一案真的跑），不是測試結果；第二次排在兩把鎖後面，結果寫在回報 |
| 控制字元、雙向控制字元、Markdown 表格欄數（改到的 17 個檔） | 0 |
| 改到的文件裡的 repo 內連結與錨點 | 59 個都在 |
| 公開紀錄的私有資料掃描（`ha-test-odoo-multiprofile-early.md`：主機名稱、`.io`、網址、IPv4、8 碼 hex、`@`） | 0 |
| 秘密預檢 | `c90b214..bec7054`（審查後第 1 個 commit）：gitleaks 8.28.0（釘選、驗過）**OK，0 命中**；本筆記的 commit 之後再跑一次（結果寫在回報） |
