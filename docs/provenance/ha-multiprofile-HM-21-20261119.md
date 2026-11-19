# HA 多帳號 HM-21 provenance：LiteLLM 開通的功能 PR（2026-11-19）

## 結論

- **2026-11-19 合併 `claude-delivery` `95b7e9d`**（#122 HM-18 定稿、#123 P9 清單產生器、#124 測試工具的 port 撞號；merge commit，不 rebase、
  不 force push）：衝突只在 `docs/multi-profile/` 的契約、驗收矩陣與 `unreleased-changes.md`，以 HM-18 的定稿文字為底、本片加的照原樣接上
  （契約第 10 節本片兩列改標「v1 定稿」、加一列記這次合併；`unreleased-changes.md` 檔頭第 2 點與第 3.5 節改指契約第 1.4 節與該檔第 7 節）；
  HM-18 沒有加列，#129 列號照舊、仍是暫定；`deviation-trace.md` 照 HM-18 的做法用產生器的暫存複本重產（只多 #129 的出處與檔頭一句，產生器
  要加的一筆交主對話）；本片的測試沒用到 #123、#124 改的工具，不用改；第 15 節交 HM-18 的兩件（`acceptance.md` T-05 的通用列，現在是第 132 行；
  契約表頭的 PaaS commit）HM-18 沒改，仍開著。本筆記其他地方寫的「HM-18 合併後」「HM-18 同時在準備」是合併前的狀態；檢查結果寫在合併 commit。
- **本片是 LiteLLM 開通的功能 PR**（計畫 §12.3 HM-21～HM-26、§11.3）：LiteLLM 自己要的都在這裡；升版 PR 把 `litellm` 加進
  `features.MULTI_PROFILE_PRODUCTS`、照 §11.3 的清單升 0.5.0（第 12 節列了 LiteLLM 的部分）。但開關開的實驗查到，共用的單帳號測試要先有
  通用做法，升版 PR 才能只改開關（第 8 節，交負責人）。本片不改版號、不碰 `addons/`，`MULTI_PROFILE_PRODUCTS` 在 repo 裡維持空集合，
  **今天任何產品都沒有新行為**；測試裡用 monkeypatch 開（同 HM-12 的做法）。
- **沒有產品專屬程式**（計畫 §9 LiteLLM 列：「不需產品專屬程式；文件建議每帳號不同 virtual key」；FM-87；PaaS 也沒有，研究 R06 §3.4、
  PR-litellm-01）。LiteLLM 的帳號就是存進去的那把 key，共用的多帳號程式已經做到 LiteLLM 需要的每一件事（第 3 節）：每個帳號自己的子程式、
  key、port、政策與唯讀設定；換 key 或網址不換 MCP token（和 PaaS 一樣，LiteLLM 不在 `products.IDENTITY_BOUND`）；開通後網址改到另一台
  伺服器要重填 key（DQ-40 ⑨，HM-12 已涵蓋全部產品）。所以本片只有測試與文件，`apps/`、`packages/`、`packaging/` 都沒改。
- **測試**（第 6 節）：新 `tests/test_litellm_multi_profile.py`，11 案（審查後加 2 案），開關開與關兩種模式。真的 LiteLLM 子程式（`apps/litellm/.venv`，
  `run_product` 的 ProfileManager、真的 Supervisor）加一台假的 LiteLLM（綁本機私有位址，HM-20 的 loopback 規則照常生效），知道兩把各限一個
  模型的假 virtual key：
  - N×N：兩個帳號的 token 兩種接法都只列出自己 key 的模型；
  - bearer 401／密鑰網址 404 矩陣：child token、virtual key、隨機 token、撤銷後的 token 在閘道都是原樣的 401／404；`X-MCP-Profile`、
    密鑰網址上的 `Authorization` 不換帳號；跨帳號 session 404；直連每個子程式，別帳號的 child token、空值、兩個標頭等 14 種都 401；
  - 每個帳號的政策：存 B 的政策只重啟 B 的子程式（收回寫入授權後以唯讀起、停用的工具子程式不註冊），反過來也是；
  - 每個帳號的後端連線池：一個帳號 4 條占滿時另一個帳號照常（契約第 9 節 #129 的事實）；健康檢查也要用這 4 條：占滿時開關開連兩次、
    開關關一次檢查逾時，閘道對這個帳號回 `-32603`「Backend unreachable」直到下一次檢查通過（現況；審查 MF-1 查到，審查後加兩案釘住）；
  - 開關關：同一份資料只服務預設帳號，B 休眠（token 已撤銷、子程式不起、key 從沒送出），`/api/profiles` 404；
  - 兩種模式不起子程式的兩案：子程式環境只差 key、child token、目錄、port 與政策兩個變數；換 key 或網址不換 token。
- **先紅後綠**（第 6.2、6.3 節）：本片沒有產品程式可以「先紅」：共用程式已經做對，新測試在基準 `c90b214` 上一寫就是綠的（第一輪紅的
  一案是測試寫錯：LiteLLM 的寫入授權是逐支的 `enabled_write_tools`，不是 `writes_enabled`，改了測試）。守門有效的證據用 8 個臨時突變
  （分派器、子程式 bearer、連線池上限、存政策不重啟、休眠處理、`IDENTITY_BOUND`、唯讀設定；審查後的 M8：連線池上限，對健康檢查那兩案），
  **每個都被它的那一案擋下**。
- **契約第 9 節加第 129 列**（暫定列號）：LiteLLM 的後端並行連線上限 PaaS 每個子程式 50、HA 4（`backend_policy` 的傳輸層；`lifespan.py`
  寫的 50 不生效），類型既有，取捨寫在列裡（第 9 節）；健康檢查也要用這 4 條，占滿夠久時這個帳號暫時被拒成「Backend unreachable」
  （審查 MF-1 補）。這是計畫 HM-29 記下、HM-32 審查 S-4 (b) 交來的列。**要不要改由負責人決定，本片不改**。
  列號暫定：HM-22～HM-26 與 HM-18 同時在準備，誰後合併誰往後重編（同 HM-27）。
- **開關開的實驗**（第 8 節；臨時把 `litellm` 放進開關、跑完還原，沒有 commit）：packaging 單元測試 366 案照過；pytest 選 339 案
  （LiteLLM 相關＋開關相關），46 個失敗、9 個錯誤（錯誤是跑法造成的，第二次重跑 7 個失敗）。LiteLLM 自己的程式不缺東西、本片的 9 案（審查前）照過，
  但 50 個**共用的單帳號測試**
  （HM-01 的 golden 與契約凍結、真子程式配 loopback 假後端、子程式環境快照、單帳號的管理 API 案）假設 repo 的開關是關的，開通就紅。
  每個產品開通都一樣（Odoo 第一個）。本片不改這些共用測試，交主對話與負責人定通用做法，在 HM-19a 之前由一片做完（第 8、15 節）。
  所以「升版 PR 只加 `litellm`」要等那一片合併之後才成立。
- **文件**：契約（第 9 節 #129、說明段、第 10 節）、驗收矩陣（T-04、T-05、T-07、T-23 與測試檔登記表）、`docs/operations/acceptance.md`
  （LiteLLM 開通的 HAOS 做法）、`unreleased-changes.md`（第 3.5 節：LiteLLM 開通時 LiteLLM 自己的 CHANGELOG 句子 L2～L6，每個產品
  開通都一樣的改變照檔頭第 2 點的單一來源，審查 S-1；檔頭第 2 點加開通片的例外；第 4.2 節：本片開關關時沒有變化）。
- **檢查**（第 10、11 節）：新測試 11 passed（審查後，53.1 秒）；相關測試與 HM-01 黃金回歸 7 個檔 120 passed（0 skip；審查後沒改 runtime，沒重跑）；packaging 單元測試 366 OK（skipped=5，要 root）；`validate.py` PASS；帳本預檢 OK；秘密預檢 0 命中。面板沒改，node 測試沒跑。以 GitHub CI（root、0 skip）為準。
- **交負責人**（第 15 節）：LiteLLM 後端並行上限維持 4（建議）或放寬，連同健康檢查和工具共用連線池要不要另開一片處理（第 9.2 節 (d)）；
  產品開通時共用的單帳號測試的通用做法（第 8 節）；DQ-44（0.5.0 之後的升版比對怎麼驗有額外帳號的資料）；HAOS 實測要用的兩把限模型
  virtual key 與主機。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-21「LiteLLM 開通」的功能 PR（計畫 §12.3 HM-21～HM-26；風險低、工作量 M；FM-87） |
| 性質 | 受開關管：本片沒有程式，開關關時沒有任何變化；升版 PR 才開通（計畫 §11.2、§11.3） |
| 分支 | `feat/ha-multiprofile-hm21-litellm-20261119`（一般 clone `ha-mp-hm21-20261119`，不是 worktree） |
| 基準 | `claude-delivery` `c90b214`（2026-11-19，#109 HM-16 的合併；已含 HM-00～HM-14、HM-16、HM-17、HM-20、HM-27、HM-30～HM-33、0.4.14 與 Headscale 0.4.19 的發版） |
| 對齊的 PaaS | pin `69ac425`（DQ-06）。PaaS 的 GitHub 鏡像 `WOOWTECH/woow-mcp-server` 唯讀核對：main＝`5ef1046`（2026-11-18 03:00 UTC，#159 的合併；第 4 節） |
| 平行的片 | HM-18、HM-22～HM-26 同時從 `c90b214` 開工（契約第 9 節列號、驗收矩陣的 T 列、`unreleased-changes.md` 會和它們衝突，誰後合併誰處理） |
| 證據（repo 外） | `/data/pi-agent/tmp/claude-1000/-data-pi-agent-home-woow-sec-sweep/9a04e4b3-b708-497b-b300-75c6a25db75e/scratchpad/HM-21/`（log、突變腳本、開關開的實驗；完成後刪除，本筆記記下結果） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `tests/test_litellm_multi_profile.py`（新） | 11 案（第 6 節；審查後加健康檢查兩案、拆開一個斷言） |
| `docs/multi-profile/contract.md` | 狀態列一句；第 9 節說明段記第 129 列的出處與暫定列號；第 9 節加第 129 列（審查後補健康檢查）；第 10 節兩列 |
| `docs/multi-profile/acceptance-matrix.md` | 狀態列一句；T-04、T-05、T-07、T-23 補 LiteLLM 的測試（T-04 另補 HAOS 做法；T-05、T-07、T-23 的切片補 HM-21）；測試檔登記表本片那列由暫定名改成新增並寫明驗什麼 |
| `docs/operations/acceptance.md` | 「LiteLLM 開通」一小節：在測試副本上做、HAOS 要的後端身分、T-02、T-04、T-05、T-07、T-13／T-14／T-17、只在本機驗的（含健康檢查）、清理 |
| `docs/multi-profile/unreleased-changes.md` | 檔頭第 2 點加開通片的例外；第 3.5 節：開通時要寫的 LiteLLM 自己的句子 L2～L6；第 4.2 節：本片一列 |
| 本筆記 | — |

沒改：`apps/`、`packages/`（核心、面板）、`packaging/`、`scripts/`、`addons/`、版號、CHANGELOG、`upgrade-notes.yaml`、
`features.MULTI_PROFILE_PRODUCTS`、`tests/conftest.py`、帳本（`runtime-patches.json`、`runtime-sources.json`；沒動任何列管檔）、
tool-surface（沒動 `apps/runtime/*.py`、`apps/*/launch.py`）、`decisions.md`（沒有新決定）、`ledger-tracking.md`（沒有新模組）、
`deviation-trace.md`、`paas-test-mapping.md`（由 repo 外的產生器重產，不手改；第 129 列不是 FEATURE-MATRIX 的列）。

## 3. 為什麼沒有產品專屬程式

- LiteLLM 的帳號由 key 決定（研究 R06 §3.4：`base_url`＋`master_key`，帳號就是貼進去的 key：master key、`proxy_admin_viewer` 使用者的
  key，或限定模型的 virtual key；PaaS 沒有程式宣告，換 key 不換 MCP token）。add-on 看不出 key 屬於誰，所以和 Odoo、Nextcloud 不同：
  沒有「換身分換 token」（DQ-40 ⑩ 只列 Odoo、Nextcloud、Hermes；`identity_fields.TOKEN_ROTATING` 沒有 LiteLLM）。
- 共用程式已經給每個帳號自己的一份：
  - 子程式環境：`products.child_spec(state, directory, port)` 照該帳號的 state 組 `LITELLM_MCP_BASE_URL`、`LITELLM_MCP_MASTER_KEY`、
    `WOOW_MCP_CHILD_TOKEN`、`HOME`／cwd（`profiles/<id>/child`）、`--port`；
  - 政策與唯讀：`LITELLM_MCP_READONLY` 與 `LITELLM_MCP_DISABLED_TOOLS` 由該帳號的 state 算（PaaS 的唯讀是每帳號一個 Settings 開關，
    HA 是逐支授權：契約第 9 節 #64）；存政策時 `gateway.admin_action` 對 LiteLLM 重啟子程式，開通後只重啟那個帳號的（HM-10）；
  - 後端：每個子程式自己的 `backend_policy` 傳輸層（連線池、解析閘門）；開通後子程式一律帶 `WOOW_MCP_DENY_LOOPBACK=1`（HM-20）；
  - 新來源重填秘密：`identity_fields.URL_SECRETS['litellm'] = {'url': ('master_key',)}`（HM-12，開通後生效）；
  - 帳號上限與記憶體：`profiles.EXTRA_PROFILE_LIMITS['litellm'] = 3`、`CHILD_MEMORY_MIB['litellm'] = 160`（HM-07、契約第 5 節）；
  - 面板：`contracts.js` 的 `identityBound` 沒有 LiteLLM（`tests/test_identity_fields.py` 核對和 `IDENTITY_BOUND` 一致）、
    `urlSecrets.litellm = {url: ['master_key']}`、`policyRestartProducts` 有 LiteLLM、「這個帳號」的重啟提示（HM-11）。
- 文件建議每帳號不同 virtual key：產品 DOCS 在 `addons/litellm/DOCS.md`，本片不能改；建議的句子交升版 PR（第 12 節）。
  `unreleased-changes.md` L2 的 CHANGELOG 句子已寫這個建議；`docs/operations/acceptance.md` 的 HAOS 做法也照它（不用 master key）。

## 4. PaaS 變動清單（GitHub 鏡像，唯讀；沒有連 Gitea）

`git log 69ac425..origin/main -- <PaaS 相關檔>` 要在連得到 Gitea 的地方跑（計畫 §11.1）；本線照 2026-11-17 的路線變更不碰 PaaS，
改用 GitHub 鏡像的 commit API 查（`list_commits`，path 篩選；唯讀）：

| PaaS 檔（基準文件第 2 節本片那列） | 結果 |
|---|---|
| `apps/litellm/litellm_mcp_admin/main.py` | 2026-11-01 之後沒有 commit（pin `69ac425` 在 11-14），和 pin 相同 |
| `apps/litellm/`（整個目錄，pin 之後） | `009dc99`（#139，不留閒置連線：HM-32 已對齊）、`3b135ca`、`1637a0f`（#155：HM-31 已對齊）、`8bfb12e`（VK 下架，只改註解）。查詢另列出的 `f9f0a30`（Logs 頁每帳號緩衝區）在 pin 之前，已在 pin 裡（契約第 9 節 #29） |
| PaaS main | `5ef1046`（2026-11-18，#159 K8s）；LiteLLM 後端連線設定（`apps/litellm/woow_litellm_mcp_server/lifespan.py`）在這個 commit 讀過：`max_connections=50, max_keepalive_connections=0`、一般的 `httpx.AsyncClient`（第 9 節） |

沒有新的 PaaS 變動要 HM-21 跟進。

## 5. PaaS 測試對照

- PaaS 沒有 LiteLLM 專屬的多帳號測試（R06 PR-litellm-02）；core 的 `tests/test_origin_product_children.py` 涵蓋兩個帳號，HA 對照的是
  HM-27 的 `tests/test_origin_policy.py`（`paas-test-mapping.md` 已有歸屬）。本片沒有新的 PaaS 案例要對照。
- PaaS 的多帳號實測（`ART/mcp-isolation-three-20261111/litellm.json`：同一台 LiteLLM 兩把限模型的 key，MCP 只列出各自的模型）對到
  本片的 N×N 測試（假後端）與之後的 HAOS T-04（第 13 節）。

## 6. 測試

### 6.1 新測試（`tests/test_litellm_multi_profile.py`，11 案；第 10、11 案是審查後加的，檔案裡排在第 3 案後面）

共用的做法：`multi_profile_runtime`（HM-08 的 rig：`run_product.run` 本身，只換掉外面）配真的 `lifecycle.Supervisor` 與真的子程式；
健康檢查每 0.5 秒一次（開關關的監看是 HM-09 之前那一種、固定 15 秒，該案改成子程式一跑起來就自己查一次）；記憶體讀數用測試的值
（沒有 cgroup、4 GiB）。假的 LiteLLM（`FakeLiteLLM`）綁本機私有位址（`socket.gethostbyname(socket.gethostname())`，CI 的 Headscale
測試同樣用法），只認兩把假 key：`GET /v1/models`、`GET /model/info` 只列那把 key 的模型，其他 key 回 401；只記「哪個帳號的 key、哪條路徑」，
不記 key 本身，不印請求列。HM-01 的 log 掃描看每個 token、child token、兩把 key 與帳號名稱。

| # | 案 | 模式 | 驗什麼 | 秒（本機） |
|---|---|---|---|---|
| 1 | `test_two_virtual_keys_on_one_litellm_each_profile_sees_only_its_own_models` | 開 | 兩個子程式的環境各是自己的 key、同一個網址、都有 `WOOW_MCP_DENY_LOOPBACK=1`；兩個帳號 × 兩種接法的 `litellm_list_models` 只列自己 key 的模型（N×N 只有對角線），後端只見過這兩把 key；`X-MCP-Profile: <B>` 配預設帳號的 Bearer、預設帳號的密鑰網址配 B 的 `Authorization`：都還是預設帳號；預設帳號的 session 拿 B 的 token（兩種接法）404；兩個 child token、兩把 virtual key、隨機 token 當 MCP token：Bearer 401、密鑰網址 404，和 HM-01 凍結的位元組相同；B 在自己的管理 API 撤銷 token 後，舊 token 兩種接法 401／404，預設帳號照常 | 4.0 |
| 2 | `test_each_real_child_serves_only_its_own_child_bearer` | 開 | 直連兩個真子程式（各自的 index port）：`test_child_bearer.refusals` 的 14 種（不帶、別帳號的 child token、空字串、只有 `Bearer`、只有 token、小寫、兩個空白、Basic、長一字、短一字、一個標頭兩個值、兩個標頭、自己的＋別人的、別人的＋自己的）都 401、沒有 session、沒有內容；自己的 child token 開得了 session，再 DELETE 掉 | 3.5 |
| 3 | `test_each_profiles_child_keeps_its_own_four_backend_connections` | 開 | 假後端扣住預設帳號的 `/model/info`：預設帳號同時 6 個 `litellm_model_info`（6 個 session），後端同時最多 4 個（等 1 秒也不會有第 5 個）；這時 B 的同一支工具照常回 B 的模型；放開後 6 個都回預設帳號的模型（契約 #129） | 4.9 |
| 4 | `test_saving_one_profiles_policy_restarts_only_its_own_child` | 開 | B 存政策（`enabled_write_tools` 清空、停用 `litellm_model_info`）：只有 B 的子程式換了 PID、以 `LITELLM_MCP_READONLY=true` 起、`DISABLED_TOOLS` 有那支工具；預設帳號的 PID、唯讀設定不變，`state.json` 位元組不變；閘道的 tools/list：B 沒有寫入工具與那支工具、呼叫它被閘道拒絕，預設帳號都有、呼叫得到自己的模型；直連子程式的 tools/list：B 的子程式根本沒註冊寫入工具與那支工具。反過來預設帳號存政策（停用 `litellm_list_models`）只重啟預設帳號的子程式，B 的 PID 與 `state.json` 不變 | 9.9 |
| 5 | `test_switched_off_the_default_profile_alone_is_served_and_b_stays_dormant` | 關（測試裡明確關掉，不管 repo 的開關） | 同一份資料（預設帳號＋B、B 在索引裡）：沒有 ProfileManager；只有預設帳號的子程式（自己的 key、沒有 `WOOW_MCP_DENY_LOOPBACK`）；開機守門在服務前撤銷 B（token 變 null、child token 換新）；預設帳號兩種接法照常；B 的舊 token、舊與新 child token、B 的 key 當 MCP token 都 401／404；`/api/profiles` 404；bootstrap 有 `dormant_profiles: 1`、沒有帳號回聲；存預設帳號的政策照今天重啟它的子程式（唯讀），B 的 `state.json` 不變；假後端從沒見過 B 的 key | 6.2 |
| 6、7 | `test_two_profiles_children_differ_only_in_key_token_directory_port_and_policy[on／off]` | 開、關 | `products.child_spec` 給兩個帳號（同網址、不同 key、B 收回寫入並停用一支工具）：環境只差 key、child token、`HOME`、唯讀與停用清單；命令列只差 port；cwd 是各自的 `child/`；`WOOW_MCP_DENY_LOOPBACK` 開時兩個都有、關時都沒有；閘道的政策判斷各看各的 state | <1 |
| 8、9 | `test_a_new_key_or_url_never_rotates_the_mcp_token[on／off]` | 開、關 | LiteLLM 不在 `IDENTITY_BOUND`、沒有換 token 的身分欄位、`URL_SECRETS` 是 url → master_key；換 key、換網址、兩個都換、清空，`identity_rebound` 都是 False | <1 |
| 10 | `test_four_busy_connections_fail_that_profiles_health_check_until_they_end` | 開 | 現況（審查 MF-1）：健康探測（`litellm_list_models`，5 秒逾時）要用同一個 4 條的連線池。假後端扣住預設帳號 4 個 `litellm_model_info`：預設帳號連兩次檢查逾時後判 `unreachable`（原因 `BACKEND_TIMEOUT: the health check got no answer within 5 s`），扣住的呼叫都還沒回；新的 `litellm_list_models` 被閘道自己拒絕（HTTP 200＋`-32603`「Backend unreachable」，`data` 是工具名與那個原因）；B 照常 `reachable`、照常回 B 的模型。放開後 4 個呼叫都回預設帳號的模型，下一次檢查通過就恢復，同一個 session 再呼叫照常 | 15.2 |
| 11 | `test_switched_off_one_check_on_four_busy_connections_refuses_new_calls` | 關（測試裡明確關掉） | 同一件事在已發行的單帳號行為（HM-09 之前的監看，容忍 1）：4 條被扣住時，測試自己做一次檢查（等於監看每 15 秒的下一次）就判 `unreachable`，新的呼叫被拒成「Backend unreachable」；放開後檢查通過、照常服務 | 8.4 |

### 6.2 先紅：臨時突變（`mutations.py`：一次改一處、跑擋它的那一案、還原；跑完核對 `git status` 和跑之前相同）

新測試在基準 `c90b214` 上一寫就綠：共用程式已經做對，本片沒有產品程式可以先紅。第一輪紅的一案是測試寫錯：以為 `writes_enabled:false`
會讓 LiteLLM 子程式唯讀，實際上 HA 的寫入授權是逐支的 `enabled_write_tools`（`policy.has_grant`；面板的政策契約 `woow-v3-exact-grants`），
改成清空 `enabled_write_tools`。守門有效的證據用 7 個突變，**全部擋下**（第一輪 7 個都跑完、`git status` 核對相同；第二輪只重跑 M3，M5 等不到鎖停掉，那一輪的 `git status` 因為中間 commit 了測試與文件而不同，改用 `git diff HEAD` 逐檔核對：7 個改過的檔都和 HEAD 相同）。審查後加的兩案另用 M8（表的最後一列；`m8_run.sh`：收集完在核心裡等 conftest 的鎖，跑完立刻還原）：

| 突變 | 改了什麼 | 擋下的案 | 結果 |
|---|---|---|---|
| M1 | 分派器把每個認得的 token 都交給預設帳號（`profile_router.McpDispatcher.resolve`） | 1 | 紅：B 的 token 送進預設帳號的 app 被拒，開 session 就失敗 |
| M2 | 子程式的 bearer 閘門收任何 `Bearer ` 開頭的值（`apps/runtime/session_idle.py`） | 2 | 紅：預設帳號的子程式收下 B 的 child token（200） |
| M3 | 子程式後端連線池上限 4 改成 8（`backend_policy.AsyncTransport`） | 3 | 紅：後端同時 6 個（`(6, 6) == (4, 4)`）。第一輪的測試等「剛好 4 個」，突變時等到逾時才紅；改成等「至少 4 個」後重跑，直接在斷言紅 |
| M4 | 存 LiteLLM 的政策不重啟子程式（`gateway.admin_action` 的產品清單拿掉 `litellm`） | 4 | 紅：B 的 PID 沒變 |
| M5 | 開關關時不處理休眠帳號（`restore_lock.guard`） | 5 | 紅：B 的 token 沒被撤銷。那一輪的斷言失敗訊息帶出了 B 的 token 值（測試當下產生、暫存目錄裡的合成值，暫存目錄已刪，log 在 repo 外、本片結束時刪除）；之後把測試裡涉及 token 的斷言改成只比真假、訊息不帶值。改過的那一案沒有再跑這個突變（共用鎖排太久，第二次重跑停掉），擋的是同一個斷言 |
| M6 | LiteLLM 加進 `IDENTITY_BOUND` | 8 | 紅 |
| M7 | 子程式的唯讀設定不看帳號自己的政策（`products.child_spec` 固定 `READONLY=false`） | 6 | 紅：兩個帳號的環境差異少了 `LITELLM_MCP_READONLY` |
| M8（審查後） | 子程式後端連線池上限 4 改成 8（`backend_policy.AsyncTransport`，同 M3），只跑第 10、11 案 | 10、11 | 紅：第 10 案 25 秒內一直沒有判成 `unreachable`（`until` 逾時：8 條時探測拿得到連線）；第 11 案那一次檢查是 `('reachable', None)`。跑完 `backend_policy.py` 和 HEAD 相同、`git status` 和跑之前相同 |

### 6.3 後綠

- 新檔（`bb71ca6` 的內容；跑的時候只差模組說明的一句，之後才補）：**9 passed、0 skip，32.4 秒**（正式 conftest、排在共用鎖後面；一般使用者 uid 1000；CPython 3.13.15）。
- 改過的兩個測試（等「至少 4 個」、開關關的案在測試裡關掉、token 的斷言不帶值）之後，M3 重跑仍紅（第 6.2 節）。
- 審查後（第 17 節；加第 10、11 案，第 5 案的環境斷言拆成兩個；`700ab75` 的內容）：**11 passed、0 skip，53.1 秒**（第 10 案 15.2 秒、
  第 11 案 8.4 秒；正式 conftest、排在共用的排隊鎖後面、等 conftest 的鎖空出來才跑）。第一次排到時 conftest 的鎖被別的工作線先拿走，
  120 秒後 11 案都是 setup 的「lock busy」錯誤、沒有跑到測試，重來一次就是上面的結果。

## 7. HM-01 黃金回歸與契約凍結

本片沒有改任何 runtime 程式（`apps/`、`packages/`、`packaging/`），HM-01 的期望值一個都沒動。本機（`c90b214` 之後的兩個 commit 上；正式 conftest）
跑 7 個檔、選 `golden or identity or fresh or zero_rewrite or litellm`：**120 passed、0 failed、0 skip，116.8 秒**：

| 檔 | 案 | 內容 |
|---|---|---|
| `tests/test_single_profile_golden.py` | 17 | 開關關：8 個產品 × fresh／configured 的黃金回歸逐位元，加上產品清單的覆蓋檢查 |
| `tests/test_router_passthrough.py` | 17 | LiteLLM：開關關時只服務預設帳號、休眠帳號的 token 被撤銷；開關開時預設帳號的 golden（6 個可開通產品 × 2）、MCP 與管理契約凍結、8081 外框 64＋32×3 |
| `tests/test_mcp_contract_freeze.py`、`tests/test_admin_contract_freeze.py` | 1＋3 | LiteLLM 的參數（開關關） |
| `tests/test_identity_fields.py` | 17 | 身分與秘密欄位分類、面板的 `identityBound`／`urlSecrets` 和後端一致 |
| `tests/test_fresh_backend_connections.py` | 20 | HM-32：LiteLLM、EMQX 不留閒置連線；子程式的連線池上限 4（契約 #129 的事實） |
| `tests/test_upgrade_zero_rewrite.py` | 45 | 零改寫、開關在呼叫時讀、沒有東西在 import 時綁定開關 |

## 8. 開關開的實驗：升版 PR 只加 `litellm` 時會遇到什麼

做法（臨時、沒有 commit）：把 `features.py` 的 `MULTI_PROFILE_PRODUCTS` 改成 `frozenset({'litellm'})`，跑完一定寫回（腳本的 EXIT trap；
跑完核對 `git diff` 沒有 `features.py`），等於升版 PR 只改這一行時的 repo。

- packaging 單元測試（`python -m unittest discover -s packaging`，gh-release 的 venv）：**Ran 366、OK（skipped=5，要 root）**。容器驗收、
  容器探針、P9、validate 的測試在 LiteLLM 開通時都照過（HM-16、HM-20 已經依 `features.enabled(app)` 分流）。
- pytest 第一次：`tests -k "litellm or zero_rewrite or owned_executable or upgrade_hooks"` 選到 339 案：**293 過、46 失敗、9 錯誤**（211 秒）。
  9 個錯誤是這次跑法造成的（`-p no:logging` 讓 `caplog` fixture 不存在：`test_origin_policy` 3 案、`test_product_ha_role` 6 案）。
- pytest 第二次（不帶那個參數；本片的開關關案已改成在測試裡關掉之後）：`test_origin_policy.py`、`test_product_ha_role.py` 的 LiteLLM 案加上
  本片的 9 案，20 案：**12 過、8 失敗**。本片 9 案全過；`test_origin_policy` 的 report-only、enforce 2 案過，開關關那一案失敗；
  `test_product_ha_role` 7 案失敗（第一次已算進失敗的 1 案也在內）。

兩次合起來，除了本片的案（已修）、升版 PR 本來就要改的一案與要 root 的一案，**共用的測試有 50 個失敗**：

| 類別 | 失敗的案（LiteLLM 的參數或案例） | 原因 |
|---|---|---|
| 單帳號 runtime 的管理請求沒帶 `X-MCP-Profile`（400 `profile_id_required`），共 12 | `test_single_profile_golden` 2、`test_mcp_contract_freeze` 1、`test_admin_contract_freeze` 1、`test_child_port_param` 的 one-port 2、`test_profile_runtime` 3、`test_product_boundary` 1、`test_upgrade_zero_rewrite` 的 bb48449 state（`litellm-False`）1、`test_restore_review` 的單帳號還原 1 | 這些測試照「產品沒開通」寫：開通後帳號範圍的管理路徑一定要帶帳號（HM-10） |
| rig 的替身只配沒開通的 runtime，共 11 | `test_product_ha_role` 7、`test_role_lifecycle` 3（`Supervisor`／`HealthMonitor` 的替身不收 ProfileManager 給的參數，runtime 起不來，等 listener 逾時變 `CancelledError`）、`test_request_budget_gateway` 1（直接拿預設帳號 app 的 `state`，開通後 8081 是分派器） | 同上：開通後 `run_product` 走 ProfileManager |
| 假後端在 loopback（`BACKEND_DESTINATION_DENIED`；健康檢查判 unreachable），共 18 | `test_real_products` 1、`test_child_bearer` 的真子程式 1、`test_expansion_runtime` 1、`test_expansion_native_restart` 1、`test_native_probe_separation` 4、`test_output_schema_runtime` 2、`test_path_param_segments` 的 LiteLLM 案 1、`test_raw_backend_errors` 的 LiteLLM 案 1、`test_stream_error_redaction` 4、`test_six_hardening` 2 | 開通後子程式一律帶 `WOOW_MCP_DENY_LOOPBACK=1`（HM-20），這些測試的假後端在 127.0.0.1 |
| 子程式環境多一個變數，共 3 | `test_child_port_param` 的預設 spec 快照 2、`test_child_bearer` 的環境鍵集合 1 | 同上 |
| 新來源要重填秘密（422），共 2 | `test_connection_patch` 1、`test_saved_destinations` 的「政策接受的網址照樣存」1 | DQ-40 ⑨ 開通後生效（HM-12） |
| 「開關關」的測試其實沒關，共 4（不算本片的案） | `test_router_passthrough` 的兩個 switched_off 案、`test_profile_lifecycle` 的 switched_off 案、`test_origin_policy` 的開關關案 | `multi_profile_runtime(switch=False)` 只是不打開，repo 開著就是開著。本片的開關關案原本也是這樣（第一次失敗），已改成在測試裡明確關掉，第二次照過（第 6.1 節第 5 案） |
| 升版 PR 本來就要改 | `test_upgrade_zero_rewrite::test_multi_profile_is_switched_off_for_every_product` | 斷言開關是空的 |
| 和開關無關 | `test_owned_executable::test_uid10001_nondumpable_self_and_own_child_proof` | 要 root（既有，CI 用 root 跑） |

**結論**：LiteLLM 自己的程式不缺東西，本片的 9 案在 repo 開著 LiteLLM 時也照過；但「升版 PR 只加 `litellm`」**現在做不到**：50 個共用的
單帳號測試（以 LiteLLM 的參數量）假設 repo 的開關是關的。每個產品開通都會遇到一樣的事，Odoo（HM-19a）是第一個。這是共用測試的寫法，不是 LiteLLM 的程式，而且 HM-22～HM-26 同時在
準備，各片各改同一批共用檔會互相衝突、做法也會不一致，所以本片**不改這些共用測試**，交主對話與負責人定一個通用做法（第 15 節），在 HM-19a
之前由一片做完。建議的做法：單帳號的測試（golden、契約凍結、真子程式、子程式環境快照、管理 API 的單帳號案）明確把受測產品關掉（行程內用
monkeypatch，子程序用前置碼），開通的情境留給多帳號測試（`test_router_passthrough` 已經用 `switched_on()` 跑開通的 golden 與契約凍結）；
`multi_profile_runtime(switch=False)` 改成真的關掉。另一種是在 `tests/conftest.py` 加「預設關、測試自己開」的 fixture，但子程序的測試照樣要
前置碼，而且 `tests/conftest.py` 本線不能改，要負責人准。

## 9. LiteLLM 的後端並行連線上限：PaaS 50、HA 4（契約第 9 節 #129；交負責人決定）

來由：HM-32 審查 S-4 (b) 把這一列交給 HM-29，計畫 HM-29 記成「要不要改，和 HM-21、HM-23 一起看」。本片照任務加列、寫取捨、交負責人，
**不改上限**（改了要動共用的 `backend_policy`，不在本片範圍）。

### 9.1 事實

| 項目 | PaaS（GitHub 鏡像 `5ef1046`） | HA（`c90b214`） |
|---|---|---|
| 子程式的後端 client | `apps/litellm/woow_litellm_mcp_server/lifespan.py`：一般的 `httpx.AsyncClient(limits=httpx.Limits(max_connections=50, max_keepalive_connections=0))`，沒有自訂傳輸層，設定生效 | `apps/litellm/vendor/woow_litellm_mcp_server/lifespan.py` 也寫 50，但 `backend_policy.async_client` 先 `kwargs.pop('limits', None)`，傳輸層 `AsyncTransport` 固定 `max_connections=4, max_keepalive_connections=0`（`apps/runtime/backend_policy.py:523-527、583-586`），50 不生效 |
| 名稱解析 | 作業系統的解析器，沒有並行上限 | 每條新連線經 `resolve_future`：`RESOLVER_CAPACITY` 4，拿不到名額**直接** `BackendBusy`（不排隊；`backend_policy.py:67-69、365-373`） |
| 第 5 個同時的請求 | 50 條以內不排隊 | 在 httpx 連線池排隊；`pool` 逾時＝子程式的 `request_timeout`（`LITELLM_MCP_REQUEST_TIMEOUT`，HA 沒設，預設 60 秒）；逾時是工具錯誤「Request to LiteLLM timed out … BACKEND_TIMEOUT」（`errors.py` 的 `litellm_request`）；健康檢查也在這裡排隊（下一列） |
| 健康檢查（審查 MF-1） | 本片沒比（只比上限） | 閘道每 15 秒對子程式呼叫 `litellm_list_models`（`GET /v1/models`；`products.health_probe`），探測刻意走子程式同一個 client（`health.py:318-321` 的註解），所以要拿這 4 條裡的一條；5 秒沒回就算失敗（`asyncio.timeout(5)`，原因 `BACKEND_TIMEOUT: the health check got no answer within 5 s`）。4 條被超過 5 秒的呼叫占住又碰上檢查時，沒開通一次、開通後連兩次（容忍 2）就判 `unreachable`，閘道對這個帳號之後的 tools/call 在送子程式之前就回 HTTP 200＋`-32603`「Backend unreachable」（`gateway.py:2027-2028`），直到下一次檢查通過；後端其實是好的，扣住的呼叫之後照常回答；別的帳號不受影響（第 6.1 節第 10、11 案）。換算到每 15 秒的間隔：沒開通時占滿超過 5 秒、剛好碰上一次檢查就會發生，開通後要連兩次（兩次探測的 5 秒之間隔 15 秒，約 25 秒以上的占滿），之後最多再等約 15 秒到下一次檢查 |
| 多帳號 | 每個帳號一個子程式，每個 50 條 | 每個帳號一個子程式，每個 4 條；一個帳號占滿，別的帳號照常（本片測試，第 6 節）；整個 add-on 最多 4×(1＋3)＝16 條（LiteLLM 額外帳號上限 3） |
| 歷史 | #139（`009dc99`）把閒置連線改成 0，上限 50 沒動 | `313ab01`（2026-10-03）起就是 4；HM-32 對齊閒置 0 時沒動上限，測試釘住（`tests/test_fresh_backend_connections.py`） |

閘道這一側不是瓶頸：閘道到子程式的 loopback 連線預設帳號 40、額外帳號 24，轉送名額 32／16（契約第 5 節）。

### 9.2 取捨與選項

- (a) **維持 4（本片的建議）**：不改程式。
  - 好處：所有產品共用一個傳輸層，連線池上限和解析閘門都是 4，一陣同時的工具呼叫在子程式裡只會排隊、不會變成 `BACKEND_BUSY`；小硬體
    （J1900、J6412，沒有 cgroup）上 socket、TLS 握手與記憶體有界；開通後每個帳號各自 4 條，一個帳號占不到別人的。
  - 代價：同一個帳號同時超過 4 個 LiteLLM 呼叫時後面的要等，最多 60 秒。耗時的呼叫（chat completion 要等模型生成完、花費報表）會
    占住連線直到做完。占滿夠久時（超過 5 秒又碰上健康檢查，開通後連兩次），這個帳號暫時被判 unreachable：新的呼叫（連便宜的讀取）
    都被閘道拒成「Backend unreachable」，直到下一次檢查通過（最多約 15 秒），錯誤說的是後端連不上，會誤導排查（第 9.1 節；審查 MF-1）。
    今天已發行的單帳號 LiteLLM 也一樣，而且一次就判。一般 MCP 用戶端（Claude.ai 等）同時只發一兩個工具呼叫，影響小；還沒有使用者回報。
- (b) **只放寬 LiteLLM**（例如 16 或對齊 PaaS 的 50）：要在 `backend_policy` 加每產品的參數（或讓 LiteLLM 自己建傳輸層），**同時**放寬
  解析閘門（不然名稱解析慢時，一陣請求會從「排隊」變成 `BACKEND_BUSY` 錯誤，比現在差）；`backend_policy.py`、`lifespan.py` 的帳本摘要、
  tool-surface 與 `test_output_schemas.py` 的釘選照規則重算；改 `tests/test_fresh_backend_connections.py` 釘住的 4；獨立審查；最好等
  HM-19c 在目標硬體量過 TLS 握手與記憶體。HM-32 審查 S-5（`lifespan.py` 的註解補「這些 `limits` 不生效」）可以一起做。
- (c) **全部產品一起放寬**：Hermes、EMQX、Nextcloud、OpenDesign 也共用這個傳輸層，影響面最大，要逐產品看後端能不能承受。
- (d) **維持 4，但讓健康檢查不和工具搶連線**（審查 MF-1 提的選項）：例如探測不必等工具占住的連線，或把「探測在連線池等到逾時」
  算成子程式沒回答（不計數、不判 unreachable）。改的是共用的 `backend_policy` 或 `health.py`，用這個傳輸層的產品都受影響；要另開一片、
  獨立審查，最好等 HM-19c；第 6.1 節第 10、11 案就是那一片的先紅（照新行為改寫）。

建議 (a)，有實際需求（使用者回報排隊或「Backend unreachable」、或 HM-19c 量到）再照 (b) 或 (d) 開一片；(d) 不放寬資源上限，只修「後端其實是好的
卻被判 unreachable」，負責人看 (a) 時一起看。契約 #129 寫的是現況；選了 (b)、(c) 或 (d) 時改那一列與 L5 的 CHANGELOG 句子，也改第 10、11 案。

## 10. 本機檢查（2026-11-19，一般使用者 uid 1000；AMD EPYC 7713、CPython 3.13.15；TMPDIR 用短的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 都在 conftest 的本機鎖下跑：前幾次也排了共用的排隊鎖，最後兩次別的工作線大多沒排、等太久，改成只靠 conftest 的鎖、拿不到就重來）

| 檢查 | 結果 |
|---|---|
| `python3 scripts/secret_precheck.py --tools …/scan0414/tools`（gitleaks 8.28.0 釘選） | 第 11 節：0 命中 |
| `python3 scripts/ledger_precheck.py` | `result: OK`：`runtime-sources.json` 70 檔 0 漂移、`tool-surface.json` 159 檔 0 漂移；本片沒動任何列管檔 |
| `packaging/validate.py`（gh-release 的 venv，有 PyYAML） | PASS（8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape） |
| packaging 單元測試（`python -m unittest discover -s packaging -p 'test_*.py'`，短 TMPDIR） | Ran 366、OK（skipped=5，要 root） |
| 新測試 `tests/test_litellm_multi_profile.py` | 9 passed、0 skip（第 6.3 節） |
| 相關測試與 HM-01 黃金回歸（第 7 節） | 7 個檔 120 passed、0 failed、0 skip（116.8 秒） |
| `node --test packages/mcp-admin-ui/tests/*.test.mjs` | 沒跑：面板與它的 contracts 沒改 |
| 臨時突變（第 6.2 節） | 7 個都紅；跑完每個改過的檔都和 HEAD 相同 |
| 開關開的實驗（第 8 節，沒有 commit） | packaging 366 OK；pytest 第一次 339 案 46 失敗、9 錯誤，第二次 20 案 8 失敗（本片 9 案全過）；共用測試 50 個失敗（第 8 節） |
| 審查後：新測試檔（`700ab75`） | 11 passed、0 skip，53.1 秒（第 6.3 節） |
| 審查後：M8（第 6.2 節） | 2 案都紅；跑完 `backend_policy.py` 和 HEAD 相同、`git status` 和跑之前相同 |
| 審查後：帳本預檢 | `result: OK`：70 檔、159 檔 0 漂移；變更的檔沒有列管檔（M8 還原之後跑） |
| 審查後：`packaging/validate.py` | PASS |
| 審查後：packaging 單元測試（短 TMPDIR） | Ran 366、OK（skipped=5，要 root），26.7 秒 |
| 審查後：秘密預檢 | 第 11 節：0 命中 |
| 審查後：HM-01 黃金回歸 | 沒重跑：審查後沒有改 runtime 程式（只有測試與文件），第 7 節的結果照舊 |

只在 CI 跑的：要 root 的 `test_root_*` 與 `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（本片沒有新的）；
Playwright 瀏覽器測試（本片沒改面板）。以 GitHub CI（root、0 skip）為準。

## 11. 預檢結果

- 秘密預檢：`c90b2143ca0c..e7f4ebc33a5f` 2 個 commit：**result: OK, 0 findings**；加上本筆記的 commit 之後再跑一次，結果記在本片的回報（筆記記不了自己那個 commit 的結果；push 前 finalize 步驟照例重跑）。
  審查後：`c90b2143ca0c..c0fbaa78cf74` 5 個 commit（含審查後的測試與文件）：**result: OK, 0 findings**；本筆記這次的 commit 之後、push 前
  再跑一次，結果記在本片的回報。審查後新加的兩案沒有新的測試資料（同一組 `DUMMY-hm21-…` key 與模型名、執行時產生的 token）。測試資料：兩把 key 與模型名是
  `DUMMY-hm21-…`，token 都是執行時產生（`T`×43、`C`×43 只用在不起子程式的兩案），假後端的網址是執行時的私有位址。
- 帳本預檢：`result: OK`（第 10 節）。

## 12. 交給 LiteLLM 的升版 PR

升版 PR 照計畫 §11.3 的逐檔清單（版號、`features.py`、`VERSION_OVERRIDES`、`inputs.json`、`PRODUCT_VERSIONS`、workflow、Dockerfile、
`addons/litellm/` 的 config、CHANGELOG、DOCS、README、translations、upgrade-check、根目錄 CHANGELOG／README／`upgrade-notes.yaml`、
`ha_role.py` 的 Core 白名單、帳本、發版紀錄）。R2 照 DQ-32 可以和 Nextcloud、EMQX 合成一個升版 PR。LiteLLM 的部分：

1. **`features.py`**：`MULTI_PROFILE_PRODUCTS` 加 `'litellm'`（帳本 `runtime-patches.json` 的摘要跟著重算）。
2. **測試**（第 8 節的實驗）：通用做法那一片合併之前，只加 `litellm` 會讓 50 個共用的單帳號測試紅（第 8 節的表），升版 PR 不能只改開關。
   那一片合併之後，升版 PR 照例改 `tests/test_upgrade_zero_rewrite.py::test_multi_profile_is_switched_off_for_every_product`（它斷言開關是空的；
   Odoo 開通時就會改成「只有已開通的產品」）。本片審查前的 9 案在 repo 開著 LiteLLM 時也照過（第 8 節），升版 PR 不用動；審查後加的
   第 10、11 案一個在測試裡開、一個在測試裡關，不看 repo 的開關。
3. **CHANGELOG**：`docs/multi-profile/unreleased-changes.md` 第 3.5 節的 L2～L6（LiteLLM 自己的），一行一個變化；寫進去之後照那份檔頭第 3 點
   把它們移掉。每個產品開通都一樣的改變照那份檔頭第 2 點的單一來源寫（計畫 §7.2；HM-18 合併後是契約第 1.4 節），Odoo 首發若先寫了就照
   那裡的句子對齊；L3 後半與 L6 是共通項的 LiteLLM 寫法，寫了就不重複共通的那兩句。審查前的 L7～L15（共通句的草稿）不完整，依審查 S-1
   拿掉，原句在 `e7f4ebc` 的那份檔。
4. **DOCS**（`addons/litellm/DOCS.md`「後端與設定主權」第一句「一個 Add-on 只有一組後端：url、master_key。」要改）。建議：
   「每個帳號一組後端：**url、master_key**（預設帳號＋最多 3 個額外帳號；帳號在管理面板新增）。LiteLLM 的帳號就是存進去的那把 key：
   建議每個帳號用不同的 virtual key（只允許那個帳號要用的模型），或 `proxy_admin_viewer` 使用者的 key，不要用 master key。換 key 或網址
   不會換 MCP 權杖；網址改到另一台伺服器時要重新輸入 key。」另照計畫 §7.2 寫開通後預設帳號會變的事（面板帳號選單、管理 API 的
   `X-MCP-Profile`、名額與忙碌回應、看門狗、還原、loopback、Origin 紀錄）與每個帳號的後端連線上限 4，以及 4 條占滿夠久時健康檢查會讓
   這個帳號暫時回「Backend unreachable」（契約 #129）。
5. **`upgrade-notes.yaml`**：計畫 §7.3 最後一點：§7.2 全部項目、§7.4 的回退路徑（還原升級前的備份；升級後建立的帳號會消失）、§8.4 的
   還原涵蓋範圍（只涵蓋第一個含 HM-13 的版本以後做的備份）。
6. **Store 升版比對**（`addons/litellm/upgrade-check/`）：hook 草稿在 `packaging/hooks/`，HM-19a 搬進 Odoo 時照做。0.4.14 → 0.5.0 舊版沒有
   帳號資料，hook 照現在的寫法就夠；0.5.0 之後的升版怎麼驗有額外帳號的資料是 DQ-44（第 15 節）。
7. **容器驗收**：開通的產品走一次性 internal bridge、假後端綁容器私有位址、多帳號階段（HM-16、HM-20）；`packaging/` 的單元測試在開關開時
   照過（第 8 節），LiteLLM 沒有要另外補的地方。
8. **HAOS 驗收**：`docs/operations/acceptance.md`「LiteLLM 開通」一節（第 13 節）。

## 13. 之後的 HAOS 實測要準備的事

- **要負責人核准建立與刪除的後端身分**：同一台 LiteLLM 上兩把 virtual key，A 只允許一個模型、B 只允許另一個模型（例如兩個不同的小模型）；
  不用 master key。key 只經面板或 P9 的 `--backend-file`（0600）填，不印、不存。用完由負責人撤銷。哪一台 LiteLLM（展示機的 LiteLLM 或另外
  一台測試用的）由負責人定；展示機目前 LiteLLM MCP 0.4.11 停著（README 進度紀錄 11/14）。
- **在測試副本上做**（審查 S-3）：T-04 會把預設帳號的後端換成 key A，所以裝 LiteLLM 的測試副本（同 0.4.14 的做法），不動在用的 app；
  負責人若決定在在用的 app 上做，動手前記下預設帳號原本的後端（不記秘密），清理時由負責人還原。
- **T 列**（照 `docs/operations/acceptance.md` 的多帳號表）：T-01（映像 digest、版本）、T-02（第 4 個額外帳號 409 `profile_limit_reached`：LiteLLM
  上限 3）、T-03（每帳號 token 互異；LiteLLM 換 key 不換 token）、**T-04**（兩把 key 的 N×N）、T-05（P9 `--cross` 與 `--temp-profile`：已刪的
  token 只由 `--temp-profile` 驗，審查 S-2）、T-06、**T-07**（存 B 的政策只重啟 B）、T-08、T-09、T-11、T-12、T-13、T-14、T-17（LiteLLM 子程式
  的 RSS 對 160 MiB）、T-18、T-19（本機）、T-20、T-21、T-23（容器）、
  T-24、T-25、T-27、T-29。T-10（跨帳號寫入）在 LiteLLM 是「B 的 key 沒有權限的寫入被 LiteLLM 拒絕」，要一把沒有寫入權限的 key 才驗得到，
  負責人決定要不要做。T-22 不適用（n8n）、T-28 不適用。
- **每次升版都要重驗**的四項（UC-08、sentinel 穩定性、UC-10、Supervisor 版本）照 `acceptance.md`。
- 本機已涵蓋、HAOS 不再做：每個子程式 4 條後端連線與帳號之間不互相影響、占滿時健康檢查把這個帳號判成 unreachable（#129；要在 HAOS
  驗由負責人決定）、讀不到的帳號隔離、C1-M1 攻擊序。

## 14. 驗收條件（計畫 §12.3 HM-21～HM-26、§12.0）

| 條件 | 狀態 |
|---|---|
| 產品專屬程式（受開關管、呼叫時讀開關） | 不需要（計畫 §9；第 3 節）：沒有程式改動 |
| 先寫測試、先紅後綠、記在筆記 | 第 6 節：新測試在基準上就綠（共用程式已做對）；先紅的證據是臨時突變（第 6.2 節） |
| 開關開與關兩種模式都測 | 開：6 個真子程式案、2 個不起子程式案的 on；關：2 個真子程式案、2 個不起子程式案的 off（各含審查後加的一案） |
| bearer 401 與密鑰網址 404 矩陣、跨帳號 | 第 6 節第 1、2 案 |
| 政策各自（存一個帳號的政策只重啟它的子程式） | 第 6 節第 4 案（兩個方向） |
| 兩把假 virtual key | 第 6 節第 1 案 |
| HM-01 黃金回歸開關關逐位元 | 第 7 節 |
| 契約第 9 節的列 | #129（暫定列號；第 9 節） |
| 從 FEATURE-MATRIX 衍生的 repo 文件 | 驗收矩陣（T 列與登記表）；`deviation-trace.md`、`paas-test-mapping.md` 是產生的、不手改：FM-87 的列仍對到 #64，正確；#129 不是 FEATURE-MATRIX 的列 |
| `unreleased-changes.md` 一個變化一行 | 第 3.5 節 L2～L6（LiteLLM 自己的；共通的照檔頭第 2 點）；第 4.2 節本片一列 |
| 帳本、tool-surface | 不用改（沒動列管檔、沒動 `apps/runtime`、`launch.py`） |
| 測試資料規則（計畫 §12.0 第 4 點） | 憑證都是 `DUMMY-…`、token 是 `T`×43／`C`×43 或執行時產生、網址 `.invalid` 或執行時的私有位址；秘密預檢 0 命中（第 11 節） |
| 不改版號、不碰 `addons/`、不改 `MULTI_PROFILE_PRODUCTS`、不改 `tests/conftest.py` | 通過（實驗與突變都在 commit 之前還原，第 8 節、第 6.2 節） |

## 15. 還沒解決、待負責人決定

- **待負責人決定**：
  1. LiteLLM 後端並行連線上限：維持每個子程式 4（建議）或放寬（第 9 節的 (b)、(c)）。一起看審查 MF-1 查到的事：健康檢查也用這 4 條，
     占滿夠久時這個帳號暫時被拒成「Backend unreachable」；要不要照 (d) 另開一片讓健康探測不和工具搶連線（改共用的 `backend_policy`／
     `health.py`、獨立審查，最好等 HM-19c；第 6.1 節第 10、11 案是它的先紅）。
  2. DQ-44（`decisions.md` 第 3 節，負責片寫了 HM-21、期限「R2 升版 PR 前」）：0.5.0 之後的升版比對怎麼驗有額外帳號的資料：`seed` 以 root
     寫一份合成帳號樹（擁有者 10001），或請 Store 為本 repo 開 `ha_core`。LiteLLM 0.4.14 → 0.5.0 這一次用不到（舊版沒有帳號資料），
     0.5.0 之後的第一個 LiteLLM 版本就要。
  3. HAOS 實測用的 LiteLLM 與兩把限模型的 virtual key（哪一台、誰建、何時撤銷；第 13 節），以及 T-10 要不要做。
  4. 產品開通時共用的單帳號測試怎麼處理（第 8 節）：50 個測試（以 LiteLLM 量）假設 repo 的開關是關的，任何產品的升版 PR 只改開關都會紅（Odoo 第一個）。
     建議在 HM-19a 之前由一片統一處理（單帳號測試明確關掉受測產品，開通的情境留給多帳號測試；`multi_profile_runtime(switch=False)` 真的關），
     不讓 HM-21～HM-26 各自改同一批共用檔。若選「`tests/conftest.py` 加預設關的 fixture」要負責人准。
- **列號**：契約 #129 是暫定的；HM-22～HM-26、HM-18 先合併的話，本片合併時往後重編（契約說明段、第 10 節、驗收矩陣與本筆記引用的地方）。
- **產生的文件**：`deviation-trace.md`、`paas-test-mapping.md` 下次文件同步（或 HM-18）重產時，#129 的出處寫「HM-32 審查 S-4 (b)、計畫 HM-29、HM-21」。
- **CHANGELOG 共通句**：本片不再列（審查 S-1），以計畫 §7.2 為準，HM-18 合併後以契約第 1.4 節與它在 `unreleased-changes.md` 加的一節為準，
  Odoo 首發（HM-19a）寫了就照那裡對齊；L2～L6 的數值以發版當時的契約第 5 節為準（HM-19c 量測前都是暫定）。
- **交 HM-18（主對話轉）**：`docs/operations/acceptance.md` 第 125 行 T-05 通用列寫「P9 `--cross`（…隨機與已刪的 token…）」，已刪的 token
  只由 `--temp-profile` 驗（審查 S-2；HM-16 留下的行，HM-18 也在改這份文件，本片只改自己那行）；契約第 9 節表頭寫 PaaS `@69ac425`，#129
  （和 HM-31 的列）寫的是 `5ef1046` 的設定（審查 N-6；上限 50 兩個 commit 相同），定稿時統一寫法。
- **HM-32 審查 S-5**（`lifespan.py` 的註解補「這些 `limits` 不生效」）：本片沒動 `lifespan.py`，照 HM-32 筆記留到下次改這個檔時（選了第 9 節的
  (b) 就一起做）。
- **`checks` 秒數**：開 PR 後補。本片新增的測試本機約 53 秒（11 案，第 6.3 節；審查後加的兩案約 24 秒，其中約 15 秒是等健康探測的
  5 秒逾時：開關開兩次、關一次），在計畫 §10.1 每片 1.5 分鐘的增量之內。

## 16. commit（`c90b214` 之後）

| commit | 內容 |
|---|---|
| `bb71ca6` | 測試：`tests/test_litellm_multi_profile.py`（9 案） |
| `e7f4ebc` | 文件：契約第 9 節 #129 與說明段、狀態列、第 10 節；驗收矩陣；`docs/operations/acceptance.md` 的 LiteLLM 一節；`unreleased-changes.md` |
| `1f7a529` | 本筆記 |
| `700ab75` | 審查後的測試：健康檢查兩案（第 10、11 案）、第 5 案的斷言拆開（第 17 節） |
| `c0fbaa7` | 審查後的文件：契約 #129 與第 10 節、`unreleased-changes.md`、驗收矩陣、`docs/operations/acceptance.md`（第 17 節） |
| （本 commit） | 本筆記的審查處理 |

commit 身分是 clone 設定的 `woowtech`，沒有 AI 署名（DQ-36）。審查之後才 push（第 17 節）。

## 17. 審查與處理（2026-11-19）

獨立審查（正確性）：`artifacts/ha-multiprofile-parity-20261114/wave5/review-HM-21-correctness.md`（repo 外），判定**修正後通過**：必修 1 項、
建議 3 項、小地方 6 項。都照改（N-3、N-4 隨 S-1 拿掉的句子一起解決）；只有 N-6 與 S-2 的第 125 行交 HM-18（不是本片的行）：

| 項 | 審查說的 | 處理 |
|---|---|---|
| MF-1 (a) | 契約 #129 漏了健康檢查也用同一個 4 條的連線池，建議 (a) 的代價被低估 | 照改：HA 欄補健康檢查（每 15 秒、5 秒逾時；沒開通一次、開通後連兩次判 `unreachable`，閘道回 `-32603`「Backend unreachable」直到下一次檢查通過；別的帳號不受影響），「只會排隊」改成只說工具呼叫，理由欄補代價與另一條路；狀態列與第 10 節各一句 |
| MF-1 (b) | L5 對使用者不完整 | 照改：L5 補健康檢查那句（「before, one such check was enough」：今天的單帳號一次就判） |
| MF-1 (c) | 筆記第 9.1、9.2、15 節與 `acceptance.md` 的「只在 LOCAL 驗」要補；選做：描述現況的測試 | 照改：第 9.1 節加「健康檢查」列、第 9.2 節 (a) 的好處與代價、加 (d)、建議與第 15 節第 1 點；`acceptance.md` 補一句。選做的測試也加了：第 10、11 案（開、關；照審查的實驗改寫），M8 擋得下（第 6.2 節） |
| S-1 | 第 3.5 節的 L2～L15 和檔頭第 2 點衝突，L7～L15 不完整、會被各產品各抄一份 | 照改：只留 LiteLLM 自己的 L2～L6，L7～L15 拿掉（原句在 `e7f4ebc`）；共通的改指向單一來源（計畫 §7.2，HM-18 合併後契約第 1.4 節）；檔頭第 2 點加開通片的例外；L3 後半、L6 註明是共通項的 LiteLLM 寫法 |
| S-2 | T-05 寫 `--cross` 驗已刪的 token，其實只有 `--temp-profile` 驗 | 本片那行照改（`--cross` 與 `--temp-profile`）；同檔第 125 行的通用列是 HM-16 留下的，交 HM-18（第 15 節） |
| S-3 | HAOS 做法把預設帳號的後端換成 key A，清理沒寫怎麼還原；T-02 沒寫 LiteLLM 的數字 | 照改：寫明在測試副本上做，在在用的 app 上做要先記原來的後端、由負責人還原；補 T-02（第 4 個額外帳號 409、`limit` 3）；清理跟著改 |
| N-1 | T-05、T-23 的切片欄沒加 HM-21 | 照改 |
| N-2 | L3 前半、L4 後半是今天就有的行為 | 照改：寫成「as before」 |
| N-3、N-4 | L9 的主詞、L8 的 uvicorn 503 | 隨 S-1 拿掉 L8、L9，不用改 |
| N-5 | 第 5 案一個斷言失敗時會印出子程式環境（含 child token） | 照改：拆成兩個斷言，第二個只比真假 |
| N-6 | 契約表頭寫 PaaS `@69ac425`，#129 寫的是 `5ef1046` 的設定 | 不改：HM-31 的列也一樣，交 HM-18 定稿時統一（第 15 節） |

審查第 7 節給主對話的備註（合併順序、和 HM-18 的衝突、CI 要有私有位址）不是本片的缺點，照轉主對話。

審查後的檢查（第 6.3、10、11 節）：測試檔 11 passed（53.1 秒）；M8 兩案都紅、跑完還原；帳本預檢 OK；`validate.py` PASS；packaging
單元測試 366 OK（skipped=5）；秘密預檢到 `c0fbaa7` 0 命中。沒有改 runtime，HM-01 黃金回歸沒重跑。本筆記這次的 commit 之後、push 前再跑
秘密預檢、帳本預檢、`validate.py` 與 packaging 單元測試，結果記在本片的回報。
