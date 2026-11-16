# HA 多帳號 HM-16 provenance：驗收工具（容器探針多帳號階段與還原樹、P9 kit、Store hook、acceptance.md）（2026-11-16）

## 結論

- **只改驗收工具與文件，不改執行期**：沒有動 `packages/`、`apps/`、`packaging/entrypoint.py`、`management_launcher.py`，也沒有動
  `addons/`、版號、CHANGELOG。帳本與 tool-surface 不用改（第 9 節）。`MULTI_PROFILE_PRODUCTS` 維持空集合，開關只在測試裡開。
- **容器探針的多帳號階段**（`packaging/container_profiles.py`，新）：只在開通的候選映像、單帳號路徑之後跑。預設加 2 個額外帳號、
  交叉 token 與 session、子程式 bearer 交叉、`oom_score_adj`／`nice`、SIGKILL 一個子程式其他 PID 不變、30 秒內並行停、sentinel 沒被動過、
  `/data/mcp` 符合修復規則與項目預算、照 Supervisor 的方式還原整棵多帳號樹後修好且兩個訊號都成立（第 3.1 節）。
- **單帳號探針路徑逐位元不變，有測試證明**：`container_probe.py` 只加兩個 import 與三個「開通才走」的 `if`；測試把它們拿掉後，
  和 `f4c7718` 的 `container_probe.py` AST 完全相同（`git show` 比對）。`container_acceptance.py` 對沒開通的每個產品，docker 指令與
  180 秒逐字照舊（第 3.2 節）。
- **開通的產品的假後端**：照 Headscale 開一次性 internal bridge、`mock_bind_host` 回容器私有位址、探針上限 360 秒（HM-20 審查 MF-2）。
  HM-20 的兩個 tripwire 改成對規則本身的斷言（每個產品開與關各驗一次），另留「repo 的開關決定它」的測試（第 3.3 節）。
- **`fixture_snapshot` 只對開通的產品放寬**（C4-SF-5）：開通時改走多帳號布局的快照（名稱照布局、修復規則、512 項／8 層預算、子程式
  工作目錄是空的）；沒開通的照舊（最多 16 個一般檔）。
- **P9 kit**：`--profile`、`--cross`（交叉矩陣）、`--temp-profile`（暫時帳號）、開通的 app 的 `childkill` 只殺那個帳號的子程式；
  建立或刪除結果不明就停、絕不重送；輸出只用帳號 log id（第 3.4 節）。對照 PaaS `public_probe.py --temp-profile` 補了兩項（第 4 節）。
- **Store hook 草稿**：`packaging/hooks/seed`、`verify`（只讀、與版本無關、只用標準庫）；HM-19a 升版時才搬進 `addons/odoo/upgrade-check/`
  （第 3.5、13 節）。
- **`tests/owned_executable.py` 修好**（HM-01 的工具，HM-20 交來）：開通的產品的預設帳號現在起得來；額外帳號仍不支援，明確拒絕
  （第 3.6 節）。
- **`docs/operations/acceptance.md`**：T-01～T-29 的 HA 版、每次升版重驗 UC-08／UC-10／sentinel 並記 Supervisor 版本；HM-03a／b 沒有
  結果，寫明不得宣稱（第 3.7 節）。`ha-p9-kit.md` 補多帳號一節。
- **先紅後綠**：每組新測試都先在基準的實作上跑紅，再寫實作跑綠（第 6 節）。
- **本機**：packaging unittest `Ran 248`、`OK (skipped=5)`（基準 203）；node 88 過；validate 過；pytest 目標 11 檔 586 案：580 過、
  6 個失敗都是要 root 的既有案例（第 7 節）。兩個預檢：秘密 0 命中、帳本 OK（第 8 節）。
- **實際容器沒跑**：多帳號階段第一次真跑在 HM-19a 前的 builder 乾跑（要使用者授權），本片不跑 builder、不跑 docker（第 13 節）。
- `checks` 秒數：開 PR 後補。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-16（計畫 §12.3：驗收工具；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm16-20261116`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `f4c7718`（HM-00～HM-11、HM-13a、HM-14、HM-17、HM-02、HM-20、#100、HM-31（#105）、HM-09 追補（#106）、HM-11（#107）都已合併） |
| 依據 | 計畫 §11（交付、§11.3 升版逐檔清單）、§12.3 HM-16（含 2026-11-15 HM-20 審查 MF-2 的補充）、§10（T-01～T-29、§10.6）、§8.4（還原守門）、C4-SF-5、C4-SF-14；FM-16、63、101、102、107、108、135、147；契約第 2.2、2.3、9 節（#72、#73） |
| 對齊的 PaaS | `woow-mcp-server` 的 `public_probe.py --temp-profile`（repin `d7f58493` 的版本，`artifacts/mcp-security-release-20261112/repin-d7f58493-20261116/public_probe.py`，repo 外）；PaaS CI 映像 smoke（`.gitea/workflows/ci.yml`）只看預設帳號，HA 的多帳號容器階段沒有 PaaS 對應（契約 §9 #73） |
| PaaS 變動 | 第 4 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/container_profiles.py`（新） | 容器探針的多帳號階段（第 3.1 節）：`stage()` 與它的每一段（`tree_snapshot`、`create_profiles`、`detect_as_runtime`、`child_ports`、`listeners`、`profiles_up`、`check_resources`、`kill_one`、`stop_within`、`check_routing`、`check_child_bearers`）、`private_mock_host` |
| `packaging/container_probe.py` | 兩個 import（`features`、`container_profiles`）與三個「開通才走」的 `if`：`mock_bind_host`（私有位址）、`fixture_snapshot`（多帳號快照）、`run()` 最後呼叫 `container_profiles.stage`。其他逐句照 `f4c7718` |
| `packaging/container_acceptance.py` | 讀 repo 的開關（`mcp_admin_core.features`）；開通的產品照 Headscale 開一次性 internal bridge（網路名 `woow-<產品>-candidate-<hex>`，Headscale 不變）、`docker run` 上限 360 秒；沒開通的照舊 180 秒 |
| `packaging/ha_p9_probe.py` | `cross` 模式；`Client` 的密鑰網址接法與額外標頭；`childkill --child-port` 與 `CHILD_PORT_SCRIPT`；cross 與 childkill（帶 port 時）失敗 exit 1。沒給新參數的模式和以前逐行相同 |
| `packaging/ha_p9_admin.mjs` | `logId`、`revealToken`、`crossLine`、`crossLines`、`temporaryLabel`、`withTemporaryProfile`、`childPortOf`（driver 可測的部分） |
| `packaging/ha_p9_driver.mjs` | `--profile`、`--cross`、`--temp-profile`；開通的 app 的 `childkill` 帶 `--child-port`；沒開通的 app 照舊 |
| `packaging/hooks/seed`、`verify`（新） | Store 升版比對 hook 草稿（第 3.5 節）；可執行、`#!/usr/bin/env python3`、LF |
| `tests/owned_executable.py` | 開通的產品：Supervisor 與 HealthMonitor 替身收下開通時的選項，spawn 檢查改試綁私有 port；只服務預設帳號。沒開通的照舊（第 3.6 節） |
| `packaging/test_container_profiles.py`（新） | 多帳號階段每一段與整個順序（第 5 節） |
| `packaging/test_container_probe.py` | HM-20 tripwire 改成規則本身；單帳號路徑 AST 比對；`fixture_snapshot` 開與關 |
| `packaging/test_container_acceptance.py` | 沒開通的逐字照舊、開通的走 bridge 與 360 秒、repo 的開關決定它 |
| `packaging/test_ha_p9_probe.py` | `cross` 模式、`childkill --child-port`、`CHILD_PORT_SCRIPT` |
| `packages/mcp-admin-ui/tests/p9-admin.test.mjs` | P9 的帳號流程（暫時帳號、不重送、交叉輸入、childkill 的 port） |
| `tests/test_upgrade_hooks.py`（新） | hook 只讀、與版本無關、升級不該做的事都讓 verify 失敗、檔案照 Store 規則 |
| `tests/test_owned_executable.py` | 開通的產品經 owned executable 起預設帳號 |
| `docs/operations/acceptance.md`、`ha-p9-kit.md` | 第 3.7 節 |
| `docs/provenance/ha-multiprofile-HM-16-20261116.md` | 本筆記 |

沒改：`docs/multi-profile/` 的任何文件（契約第 9 節不加列，理由見第 10 節；決策沒有新定案；`acceptance-matrix.md` 的測試檔登記表照 HM-11
的做法維持「計畫」、新檔不登記，交 HM-18 定稿時一起看）；`addons/`；版號；CHANGELOG；`packaging/test_entrypoint.py`（多帳號目錄樹的
修復由容器還原階段與 `tests/test_restore_detection.py` 涵蓋，FM-16 第 3.1 節）。

## 3. 設計重點

### 3.1 容器探針的多帳號階段（`container_profiles.stage`）

只在 `features.enabled(APP)`、單帳號路徑跑完（停機、預設帳號接在探針自己的假後端）之後：

1. **fixture（停機時）**：
   - 刪掉單帳號還原階段留下的 `.restore-detected`（守門 F 步的最後一步；HM-13a 期間沒有人刪）。
   - 以執行期使用者（uid／gid 10001，`subprocess` 的 `user`／`group`／`extra_groups=[]`）跑 `restore_detect.detect(enabled=True)`：
     建 sentinel 與 record（`established`）。這是 HM-13b 接線後開通產品第一次開機會做的事；要在帳號資料出現之前（否則是 `record_missing`），
     而且一定要由 10001 建（root 建了再 chown 會改 ctime，之後就被當成還原）。
   - 照面板的建立方式（HM-10 的程式庫呼叫：`profile_initial_state`、`ProductStore(create=…)`、索引）建 2 個額外帳號（port 18000、18001），
     接上預設帳號的假後端，最後把建出來的每一項交給 10001（探針以 root 寫，照 `fixture_update` 的規則）。
   - **不送管理請求**：容器裡沒有受信任的 Ingress、沒有 HA 角色查詢，探針的規則是不繞過管理身分檢查。管理 API 的增刪改查由
     `tests/test_profile_admin_api.py`（CI）與 HAOS 上 P9 的 `--temp-profile` 涵蓋（HM-10 交辦，第 11 節）。
2. **起一次**：每個帳號的子程式在跑、只聽自己的 port、只聽 IPv4 loopback（`/proc/net/tcp`、`tcp6`）。子程式和 port 的對應看命令列的 `--port`
   （Hermes／OpenDesign 的預設帳號子程式沒寫 port，就是 3000；額外帳號的 exec 包裝器也帶真正的命令列；還沒回收的子程式命令列是空的，略過）。
3. **路由（T-05）**：每個帳號的 token 用兩種接法都開得了 session，而且是子程式自己的 session（不是閘道自答的 `woow-local-`）；兩種接法列的
   工具相同，三個帳號也相同（建立時複製政策，DQ-02）；每個 session 拿任何別帳號的 token（兩種接法）都 404；隨機 token：Bearer 401、
   密鑰網址 404。開過的 session 一律 DELETE（失敗時也結束）。
4. **子程式 bearer（T-23、HM-06）**：每個子程式照 HM-06 的 `assert_child_bearer`（不帶、隨機 401，自己的 200 並結束 session），另加「每個別帳號的
   child token 都 401、沒有 session」。
5. **子程式資源（HM-09）**：額外帳號 `oom_score_adj` 500、`nice` 是管理程序的值加 5；預設帳號子程式和管理程序相同。
6. **SIGKILL（T-13）**：殺第一個額外帳號的子程式：看門狗以新 PID 重起、重新在自己的 port 上聽；其他子程式全程 PID 不變；被殺的帳號之後照常服務。
7. **停機**：SIGTERM 後 30 秒內（HA 的停止上限）exit 0、每個子程式都回收；秒數印在最後一行。
8. **sentinel 與布局**：停機後 detect 是 `consistent`、沒有標記（起停、三個子程式、看門狗重起都沒碰到 sentinel）；`tree_snapshot`
   （`fixture_snapshot` 的開通版）通過：每一項是一般目錄或單一連結的一般檔、同一個檔案系統、10001、0700／0600、名稱是布局裡的、
   每個子程式工作目錄是空的、總數 ≤512 與深度 ≤8（`packaging/entrypoint.py` 的修復上限：這棵樹的備份還原得回來，FM-16）。
9. **多帳號還原樹**：先記下每個 state、索引、record 的位元，用單帳號還原階段的 `restore_as_supervisor()` 把整棵樹改成 root（檔案 0644、
   目錄 0755），再起一次：`check_restored_start()`（標記存在且私有、每一項改回 10001 與 0700／0600、預設 state 位元不變）、其他 state、索引、
   record 位元都不變、三個子程式都重新起來；停機後 detect 是「有標記＋`mismatch`」：兩個訊號都成立。

最後印一行（沒有秘密）：`PASS multi-profile: default + 2 profiles up in N s; routing, child bearer, resources, SIGKILL, stop in N s; N entries;
restore tree and both signals`。等不到時只寫 port（例如 `children up on [3000] of [3000, 18000, 18001]`）：探針從不印執行期輸出。

時間：單帳號路徑之外多兩次啟動、一次看門狗重起與一次還原後啟動，推估 40～60 秒；開通的候選映像把 `docker run` 上限從 180 改 360 秒
（HM-13a 交辦「180 秒上限要跟著看」）。容器的 open file 上限要 ≥680（Odoo 的 `open_file_budget` 要求；其他產品 530）：
docker 預設的 1024 夠；不夠時額外帳號不服務，第 2 步會失敗在上面那行訊息。

### 3.2 單帳號路徑逐位元不變的證明

- `packaging/test_container_probe.py::SingleProfilePathTests`：拿 `git show f4c7718:packaging/container_probe.py`（CI 的 checkout 是完整歷史）
  和現在的檔比 AST：把 `features`、`container_profiles` 兩個 import 與「條件呼叫 `features.enabled`」的 `if`（不管在哪一層）拿掉，
  剛好 5 處，剩下的和 `f4c7718` 完全相同（`ast.dump`，同一個直譯器當場算，不怕版本差）。另驗 `run()` 只有一個這種分支、是
  `httpx.AsyncClient` 區塊的最後一句、內容是 `await container_profiles.stage(sys.modules[__name__], client)`。
- 之後有片要刻意改單帳號路徑（例如 HM-13b 改標記的斷言），就把 `BASE` 改成它自己審過的基準 commit，並在筆記寫明理由。
- `container_acceptance.py`：`test_a_candidate_not_switched_on_is_invoked_as_before` 對 `inputs.json` 的每個產品比完整的 docker 指令（逐字）
  與 180 秒。
- `mock_bind_host`、`fixture_snapshot` 沒開通時的行為另有測試（每個產品 127.0.0.1，Headscale 照舊；最多 16 個一般檔、目錄或第 17 項就失敗）。

### 3.3 開通的產品的假後端（HM-20 審查 MF-2）

- `container_acceptance.main`：`app == 'headscale' or features.enabled(app)` → `docker network create --internal --driver bridge`、檢查
  `Internal`、沒有別的容器，跑完一定刪（失敗也刪）。開關讀 repo 的 `packages/mcp-admin-core`（`supply_chain.candidate` 已確認映像的
  revision label＝這個 checkout 的 HEAD，所以和映像裡的那份相同）。
- `container_probe.mock_bind_host`：開通的產品（Headscale 以外）回 `container_profiles.private_mock_host()`：和 Headscale 同一條規則
  （IPv4、私有、不是 loopback 或 link-local、`products.allowed_address`）。`tests/loopback_backends.py` 的替身不在映像裡，救不了。
- HM-20 的兩個 tripwire（「開關一開、探針沒改就紅」）改成規則本身：每個產品開與關各驗一次；另留 `test_the_repository_switch_decides_it`
  兩個（repo 的開關裡有的產品就走 bridge 與私有位址）。

### 3.4 P9 kit（FM-107）

- `--profile ID`：driver 的管理用戶端（面板的 `AdminApi`）在每個帳號範圍請求帶 `X-MCP-Profile`；`--backend-file`、`--tokens`、`--plan`、
  `--modes` 對那個帳號做。
- `childkill`（開通的 app）：driver 從帳號清單取那個帳號的 port，probe 以 `--child-port` 依命令列找出唯一一個子程式；找不到唯一一個就什麼都
  不殺。被殺的要回來（新 PID）、其他 PID 不變，否則 exit 1。沒給 `--child-port` 時和以前逐行相同。
- `--cross`：每個帳號在自己的 `X-MCP-Profile` 下 reveal token；probe 的 `cross` 模式驗兩種接法、session 不跨帳號（404）、隨機與已刪的 token
  被拒；開 session 時都帶 `X-MCP-Profile: default`，證明 MCP port 不看它（契約第 2.2 節）。
- `--temp-profile`：用剛讀到的索引版本建 `p9-temp-<8 hex>` →（`--backend-file`、`--plan`；沒後端又有 `PROBE_TOOL` 時工具呼叫要被拒）→
  和預設帳號交叉 → 刪除（重讀索引版本；前面失敗也照刪）→ 舊 token 被拒。
- **不自動重送**：建立、刪除、token 操作的結果不明就印識別碼與路由、停止；刪除不明時另印「暫時帳號可能還在」。

### 3.5 Store 升版比對 hook 草稿（FM-102、FM-135；C4-SF-14）

- `seed`（舊版起來後）：`/data/mcp` 與 `state.json` 屬 10001 且私有；預設 token（從 `state.json` 讀，不印、不存）兩種接法都開得了 session 並結束；
  隨機 token 被拒；沒有還原標記；在 `$HOOK_STATE_DIR` 留 `state.json` 與索引的 SHA-256 與三個名稱在不在。
- `verify`（新版起來後）：seed 的檢查再做一次；`state.json` 位元不變（I6、零改寫）；索引與 `profiles/` 和升級前一樣（沒有的不能冒出來，有的
  位元不變）；沒有還原標記（升級不是還原）。
- **只讀**：兩支都不寫 add-on 的資料（測試比每一項的位元、擁有者、mode、大小、mtime、ctime）。**與版本無關**：不比版本、serverInfo、工具清單，
  不讀 `ADDON_VERSION`、`ADDON_IMAGE`、`PHASE`（測試換三組值結果相同，原始碼也不提）。**DQ-44 待定**：不寫合成帳號樹，只斷言索引位元不變。
- `verify` 用 `SourceFileLoader` 載入同目錄的 `seed`（Store 掛整個 `upgrade-check/`），兩個階段同一套規則。
- 直接連 add-on：HTTP 用不讀環境代理設定的 opener（`ProxyHandler({})`）。`urlopen` 會照 `http_proxy` 走，hook 容器若帶了代理設定就連不到
  add-on（本機重現：環境設一個沒人聽的 loopback 代理時 `urlopen` 失敗、這個 opener 照常 200）。
- 未確認（UC-19）：Store 的 hook 容器能不能以 root 讀 0600 的 `state.json`、連到 add-on 的 8081；第一次升版 PR 的 `Upgrade comparison` 才看得到。

### 3.6 `tests/owned_executable.py`（HM-01 的工具；HM-20 第 13 節交來）

- 問題：HM-08 起，開通的產品的 `run_product` 建 ProfileManager，每個帳號的 Supervisor 帶看門狗、spawn 檢查、生命週期 log，HealthMonitor 帶監看
  選項；替身 `assert not kwargs`、不收監看選項，所以開通的產品起不來。
- 修法：產品開通時（子程序前置碼改開關，呼叫時讀），Supervisor 替身收下選項，只把 spawn 檢查換成「試綁私有 port」（正式的檢查會試綁 3000，
  `tests/owned_network.py` 不准任何測試碰）；HealthMonitor 替身收下監看選項。這個工具只服務一個帳號：第二個 Supervisor（額外帳號）直接
  `OwnershipError`（ProfileManager 記一行、不服務那個帳號），額外帳號的測試用 `tests/multi_profile_runtime.py`。沒開通的產品逐行照舊
  （`assert not kwargs` 還在）。
- 新測試：開通的 EMQX 預設帳號經 owned executable 起來、initialize 由真子程式回答、8081 是開通後的分派器（外面冒出的 `profiles.json`
  讓所有 token 503，DQ-12）、log 檔沒有 token。
- 沒做（交 HM-19a）：Odoo 一開通，用 loopback 假後端的既有 Odoo 測試要照 HM-20 第 13 節改（`loopback_backends`）；這是開通那一片的事。

### 3.7 文件

- `docs/operations/acceptance.md` 加「多帳號驗收（T-01～T-29 的 HA 版；HM-16）」：狀態先講（工具備好、沒有 HA 實測、HM-03a／b 沒有結果）、
  門檻、五層與工具、容器多帳號階段驗什麼、T-01～T-29 每列「怎麼驗」與「通過標準」、「每次升版都要重驗」（UC-08 三種還原、sentinel 穩定性含
  主機重開、UC-10，記 Supervisor／Core／HAOS 版本）。可執行 gate 一節補多帳號階段。
- `docs/operations/ha-p9-kit.md` 加「多帳號（HM-16；只對開通的 app）」一節與證據要記的版本。

## 4. PaaS 對照與變動

- `public_probe.py --temp-profile`（repin `d7f58493`）逐項：建第二帳號 → 用它自己的網址測 → 沒後端的工具呼叫不能成功（不借預設帳號的連線）→
  帶 `X-MCP-Profile: default` 不會切到預設帳號 → 拿預設帳號的 session 被拒 → 刪除 → 舊網址被拒 → 預設帳號照常。HA 的 P9 kit 每一項都有
  （錯 token 是 HA 的 404／401，不是 PaaS 的 403，契約 §9 #1）。PaaS 另印「刪除後資料夾還在嗎」：HA 交本機測試與面板（`ha-p9-kit.md`）。
- PaaS 的 CI 映像 smoke 只看預設帳號（FM-101），HA 的容器多帳號階段沒有 PaaS 對應（§9 #73 已涵蓋發佈流程的不同）。
- 本機唯讀 PaaS repo（`…/mcp-path-param-guard-20261106-claude/paas-repo`，沒 fetch、沒 checkout；`origin/main`＝`7087280`）：
  `git log --oneline d7f5849..origin/main` 是 #135（EMQX 不留閒置連線）、#139（LiteLLM 同）、#138（Hermes cron 停用建立）三次合併，改的是
  `apps/emqx`、`apps/hermes`、`apps/litellm` 的子程式，和驗收工具無關。`git log 69ac425..origin/main -- .gitea/workflows/ci.yml 'apps/*/scripts/ci_smoke_child.py'`
  只有 `36bde7b`（移除 VK）；`packages/mcp-admin-core/mcp_admin_core/profiles.py`、`restore_*.py` 只有 #155 的 `e6971c0`（HM-31 已對齊）。

## 5. 測試（新與改過的）

| 檔 | 案例 | 驗什麼 |
|---|---|---|
| `packaging/test_container_profiles.py`（新） | 28 | 布局快照（設計的樹照收、13 種布局外的東西各自失敗、預算與深度、別的檔案系統、journal 名稱）；fixture（兩個帳號照面板建立、政策複製、token 互異、預設 state 不動、建的每一項而且只有它們交給 10001、沒後端就不建）；detect 以子程序跑（建、保持、被當成還原、標記；帳號資料先出現是 `record_missing`；容器裡用 10001、沒有附加群組）；子程式 port、listener、資源（加 5 不是設成 5）；SIGKILL（只殺那個、它回來、別的重起或回不來都失敗）；停機（量秒數、逾時、非 0、孤兒）；路由（7 種壞法各自失敗、訊息不含 token、失敗也結束 session）；子程式 bearer 交叉；整個階段的順序與失敗時停掉 runtime |
| `packaging/test_container_probe.py` | +6（共 19） | 私有位址（每個產品開／關、repo 開關）、單帳號路徑 AST 比對、stage 的位置、`fixture_snapshot` 開與關 |
| `packaging/test_container_acceptance.py` | +2（共 6：加 3 個、拿掉 HM-20 的 1 個） | 沒開通的逐字照舊、開通的 bridge 與 360 秒、repo 開關 |
| `packaging/test_ha_p9_probe.py` | +9（共 22） | cross 模式（通過、已刪的 token、三種壞法、輸入格式）、`childkill --child-port`（只殺那個、預設帳號、別的重起或回不來、找不到唯一一個）、`CHILD_PORT_SCRIPT` |
| `packages/mcp-admin-ui/tests/p9-admin.test.mjs` | +7（共 11） | log id 與 reveal、沒有啟用 token 的帳號、暫時帳號（成功、用的時候失敗也刪、建立或刪除回應遺失就停不重送、沒有索引版本不建立）、childkill 的 port |
| `tests/test_upgrade_hooks.py`（新） | 17（其中參數化 11） | hook 只讀、與版本無關、11 種升級不該做的事各讓 verify 失敗、已有索引位元不變、seed 的失敗、不走環境代理、檔案照 Store 規則 |
| `tests/test_owned_executable.py` | +1 | 開通的產品經 owned executable 起預設帳號 |

測試資料：token 一律在測試執行時產生（`secrets.token_urlsafe`），node 測試用 `T`×43、`C`×43、`S`×43；憑證 `DUMMY`、網址 `.invalid`；沒有 commit
任何隨機 token。新 pytest 檔都在 HM-01 的 log 掃描下跑（token 已登記）。沒有條件式 skip。

## 6. 先紅後綠

| 組 | 紅（新測試在基準的實作上） | 綠 |
|---|---|---|
| 容器探針與驗收（`test_container_*.py`） | `1d69c8c` 的測試＋`f4c7718` 的 `container_probe.py`／`container_acceptance.py`、沒有 `container_profiles.py`：`Ran 26`、failures=57、errors=3（`test_container_profiles` 匯入失敗；沒開通的測試在基準照過，證明行為是基準的） | `Ran 53`、OK |
| P9 kit（`test_ha_p9_probe.py`、`p9-admin.test.mjs`） | 基準的 kit：packaging failures=3、errors=5；node 測試檔匯入失敗（沒有新匯出）。兩個在基準因為 argparse 拒絕新參數而「照過」的測試，改成斷言各自的拒絕訊息 | packaging `Ran 22`、OK；node 11 過 |
| cross 的 `X-MCP-Profile` | probe 開 session 不帶這個標頭時，「switches by header」子案例失敗 | 過 |
| hook 與 owned executable（pytest，一次排隊在共用鎖裡先紅後綠） | `packaging/hooks/` 不在、`tests/owned_executable.py` 是基準：`tests/test_upgrade_hooks.py` 收集就失敗（`FileNotFoundError`：沒有 hook）；新的 owned executable 測試失敗（子程序的 log 是 `assert not kwargs` 的 `AssertionError`，就是交來的問題）。1 failed、1 error、0.83 秒 | 目標 11 檔 586 案：580 過、6 個要 root 的既有案例失敗（第 7 節） |
| hook 不走環境代理 | 本機以 `urlopen` 重現（不是 pytest）：環境帶一個沒人聽的 loopback 代理時，`urlopen` 對 loopback 上的伺服器失敗（`URLError`），不讀環境代理的 opener 回 200 | 新測試過 |

## 7. 本機檢查（2026-11-16，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排隊在共用鎖）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（CI 的 PyYAML venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（照 CI：離線暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 248`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準）；27.9 秒（基準 `Ran 203`、22.0 秒） |
| node（`npm test --prefix packages/mcp-admin-ui`） | 88 過、0 失敗（基準 81） |
| `node --check` driver、admin | 過 |
| pytest（同 CI 的指令，只是不用 root；一次排隊在共用鎖：先紅、還原實作（SHA-256 核對）、再綠） | 目標 11 檔：`test_upgrade_hooks`、`test_owned_executable`、`test_restore_detection`（載入容器探針）、`test_real_products`、`test_unconfigured_connect`、`test_runtime_failure`、`test_real_n8n`、`test_ha_role`（這幾個用 `owned_executable`）、`test_backend_loopback`。**586 案：580 過、6 失敗、0 skip**，262 秒。6 個失敗都是要 root 的既有案例（`geteuid` 斷言）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、`test_restore_detection.py` 的 5 個 `test_root_*`。瀏覽器測試（`test_owned_browser_*`）沒跑：這個 clone 沒裝 Chromium，它們只從 `owned_executable` 拿兩個沒改的函式 |
| 全套 pytest | 沒在本機跑：共用鎖前面排著其他片的全套（這一輪 21:38 排、22:29 才輪到，約 50 分鐘）；本片改到的 pytest 面只有上面 11 檔（另查過沒有別的測試掃 `packaging/`、`tests/` 或 `docs/operations/`）。以 CI 為準 |

### 7.1 只在 CI 跑的測試

- 新測試沒有只在 CI 跑的：全部在本機以一般使用者跑過。
- 既有、要 root、本機一定失敗的（同基準）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`。packaging 的 5 個
  `skipUnless(root)`。
- 實際容器（多帳號階段、開通的假後端 bridge）不在 CI：HM-19a 前的 builder 乾跑（第 13 節）。

### 7.2 `checks` 秒數與新測試的時間

- 開 PR 後補（前後兩個 run 的 `checks`）。
- 本機推估的增量：packaging unittest ＋5.9 秒（22.0 → 27.9；新假伺服器停機用 0.05 秒輪詢）；node ＋不到 0.1 秒；pytest：新的 owned executable
  測試 3.79 秒、`test_upgrade_hooks.py` 17 案每案都低於 1.98 秒（不在最慢 25 名）。CI 推估合計 ＋15 秒左右，在每片 1.5 分鐘的預算內。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools <gitleaks-tools> --repo . --base f4c7718 --head HEAD --full` | gitleaks 8.28.0（釘選、驗過）；`f4c7718..HEAD` 全部 commit（含本筆記）：**OK，0 命中** |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base f4c7718` | 三本帳本 0 drift、0 missing；改到的檔沒有列管的、沒有新的執行期檔：**OK** |

## 9. 帳本與 tool-surface

沒有動任何列管檔，也沒有新的執行期檔（`scripts/ledger_precheck.py` 的執行期檔＝`packages/mcp-admin-core/`、`packages/mcp-admin-ui/src/`、
`apps/`、`packaging/entrypoint.py`、`management_launcher.py`）。新檔都不進映像：`container_profiles.py` 只在 builder 跑容器驗收時掛進
候選容器（和 `container_probe.py` 一樣不列管）；`packaging/hooks/*` 是 Store 的 CI 跑的；`tests/` 不進映像。所以 `runtime-patches.json`、
`docs/tool-surface.*` 都沒改。HM-19a 把 hook 搬進 `addons/odoo/upgrade-check/` 後，它們算 Store 的執行期內容指紋，不是映像的帳本。

## 10. 契約第 9 節

不加列。本片加的是驗收工具：P9 的暫時帳號與交叉檢查照 PaaS `public_probe.py`；錯 token 的狀態碼差異已是 #1；升級驗證是 #72；容器多帳號階段
屬發佈流程的不同（#73）。沒有新的 PaaS 可觀察差異。

## 11. 前面各片交給 HM-16 的待辦

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-05 第 11 節 | `acceptance/real_backends/ha_runtime.py` 還 patch `run_product.make_apps`（HM-05 起在 `profile_runtime`），拿新映像重跑會在 import 時失敗 | **不改**。這套真後端驗收凍結在 HA 0.4.6（source `28b8317`）與 `images.json` 的 digest，`controller.source_proof` 只認那個 commit 的位元；只改注入點也跑不了新映像，反而讓 0.4.6 的重跑和紀錄對不上。下次真後端驗收重新釘版時（source、映像、注入點一起改）再處理；它失敗得很明顯，不會默默失效。交 HM-19b／HM-29 |
| HM-06 | 探針多帳號階段沿用 `assert_child_bearer`（每個帳號的子程式 port 與 child_token） | 做了：`check_child_bearers`，另加別帳號 child token 401 |
| HM-09 | 容器探針多帳號階段：SIGKILL 一個其他 PID 不變、停機 <30 秒、真容器裡的 `oom_score_adj`／`nice` | 做了：`kill_one`、`stop_within`、`check_resources` |
| HM-10 | P9 kit 與容器探針的管理請求帶 `X-MCP-Profile`；多帳號的增刪改查與隔離在容器裡跑一次 | P9：做了（`AdminApi` 帶；`--temp-profile` 經真的管理 API 建與刪）。容器：**不在容器裡跑管理 API**：容器沒有 HA 管理員與 Supervisor，探針的規則是不繞過管理身分檢查；帳號照面板的建立方式以程式庫在停機時建，隔離（路由、session、子程式 bearer）在容器裡驗。管理 API 的增刪改查與索引隔離由 `tests/test_profile_admin_api.py`（CI）與 HAOS 的 P9 涵蓋 |
| HM-11 第 16.11、17.8 節 | P9 driver 的帳號參數與交叉矩陣（`createP9AdminClient(…, {profile})` 已就緒） | 做了 |
| HM-13a 第 11 節 | 容器探針的多帳號階段（含 sentinel 的 root 還原樹）接在 HM-13a 的還原階段之後；`docker run` 180 秒上限要跟著看 | 做了：階段在單帳號路徑（含 HM-13a 的還原階段）之後；開通的候選映像 360 秒。HM-13b 合併後要改的見第 12 節 |
| HM-20 第 13 節（審查 MF-2） | 開通的產品：`container_acceptance` 開一次性 internal bridge、`mock_bind_host` 回私有位址；HM-20 的 tripwire | 做了；tripwire 改成規則本身的斷言（第 3.3 節） |
| HM-20 第 13 節、HM-01 的工具 | `tests/owned_executable.py` 起不了開通的產品（Supervisor 替身 `assert not kwargs`） | **修好**（預設帳號）；額外帳號明確拒絕（第 3.6 節）。開通 Odoo 時既有 Odoo 測試的 loopback 假後端仍交 HM-19a |
| `decisions.md` DQ-44（負責片含 HM-16 的工具） | 0.5.0 之後的升版比對怎麼驗「有額外帳號」的資料 | **待定，沒做**：hook 草稿不寫合成帳號樹、不要 `ha_core`，只斷言與版本無關的事與索引位元不變；DQ-44 照表在 R2 升版 PR 前定 |
| `acceptance-matrix.md` 檔頭 | 把它寫進 `docs/operations/acceptance.md` 與 P9 kit | 做了（第 3.7 節） |
| FM-16 | `packaging/test_entrypoint.py` 補多帳號目錄樹 | 改由容器的多帳號還原階段（真 entrypoint、真映像）與 `tree_snapshot` 的修復規則檢查涵蓋；`packaging/test_entrypoint.py` 不改（CI 那一步不以 root 跑，root 才造得出的情境放 `tests/`，計畫 §10.1） |

## 12. 交 HM-13b／HM-13c 之後補

HM-13b（開機守門）還沒合併，本片照 HM-13a 已合併的行為與計畫 §8.4 做。HM-13b 合併時要一起改探針（不然 HM-19a 前的 builder 乾跑會失敗）：

1. 單帳號還原階段：守門在還原後那次啟動就刪標記（HM-13a 第 11 節已交代）；`container_profiles.end_restore_marker` 那時要改成「確認標記已不在」。
2. sentinel 的 fixture：HM-13b 接線後，開通產品第一次開機自己建 sentinel 與 record。`stage()` 第 1 步的 `detect_as_runtime` 要從「建出來
   （`established`）」改成「執行期已建好（`consistent`）」，不再由探針建。
3. 多帳號還原之後（DQ-03 採 (b) A2：有帳號資料就連預設一起撤銷）：每個帳號的 token 撤銷、child_token 重產（`kept_bytes` 的「位元不變」改成
   「token 是 null、child_token 不同、其他欄位不變」）、多出 `restore-record.json`、還原前的 token 兩種接法都被拒（404／401）、標記被刪、
   sentinel 重建（最後的 detect 從「有標記＋`mismatch`」改成「沒有標記＋`consistent`」）。
4. 布局名稱：HM-13b 若加新名稱（例如封存的 journal `.restored`、隔離目錄裡的檔），要加進 `container_profiles` 的 `TOP_NAMES`／`PROFILE_NAMES`
   （從 `profiles.py` 的常數取，不要另寫字串）；`.quarantine-<id>-<UTC>` 目錄本片已收。
5. 單帳號路徑的 AST 比對：HM-13b 改了單帳號路徑，就把 `test_container_probe.py` 的 `BASE` 改成它自己審過的基準，並寫明理由。
6. HM-13c：還原核對卡、全部撤銷、刪隔離目錄是管理 API 的事，容器探針碰不到；HAOS 的演練照 `acceptance.md` 的 T-21（核對後才重發、舊收據 410），
   P9 kit 要不要加對應模式由 HM-13c 決定。`acceptance.md` 的 T-21 列在那時補具體步驟。

## 13. 交 HM-19a（與 builder 乾跑）

- **builder 乾跑（要使用者授權）**：拋棄式 commit 把 `odoo` 加進 `MULTI_PROFILE_PRODUCTS`、不推 GHCR，跑 `supply_chain.py candidate` →
  `container_acceptance`。這是多帳號階段與開通的 bridge 第一次真跑；把最後那行 `PASS multi-profile …`（含秒數）記進證據；失敗先查探針，不要放寬。
  要先合併 HM-13b 並照第 12 節改好探針。docker 的 nofile soft 上限要 ≥680。
- **搬進 `addons/odoo/upgrade-check/` 的檔**（`git mv`，保留可執行位元）：
  - `packaging/hooks/seed` → `addons/odoo/upgrade-check/seed`
  - `packaging/hooks/verify` → `addons/odoo/upgrade-check/verify`
  - 同時把 `tests/test_upgrade_hooks.py` 的 `HOOKS` 改指新位置（之後的產品各自一份時，改成逐目錄參數化）。不需要 `settings.yaml`（預設的 600 秒
    hook 上限與 300 秒啟動上限夠）。
  - 第一次升版 PR 的 `Upgrade comparison` 會看到 UC-19（hook 能不能以 root 讀 `state.json`、連到 8081）；不行就停下回報，不要改成走管理 API。
- 計畫 §11.3 的逐檔清單已列 `container_probe.py`、`container_acceptance.py` 的假後端位址：本片已改成看開關，升版 PR 不用再改這兩檔。
- 既有 Odoo 測試用 loopback 假後端的（HM-01 黃金回歸、`test_real_products.py` 的 Odoo 案等）：開通後要用 `loopback_backends`（HM-20 第 13 節）。
  經 `owned_executable` 起的測試現在起得來（第 3.6 節）。

## 14. 本片用到的決策

| DQ | 用在哪裡 |
|---|---|
| DQ-02（新帳號複製預設帳號當下的政策） | 容器路由檢查要求三個帳號列的工具相同 |
| DQ-03 (b) A2 | 第 12 節：HM-13b 之後多帳號還原的期望值 |
| DQ-10／DQ-40 ⑦（開通後拒 loopback） | 開通的產品的假後端改走 bridge 與私有位址 |
| DQ-12（索引被外改就 503） | owned executable 的新測試用它證明 8081 是開通後的分派器 |
| DQ-14（刪除先撤銷） | 暫時帳號刪除後舊 token 被拒 |
| DQ-15（帳號增刪 If-Match＋Idempotency-Key） | P9 的暫時帳號（`AdminApi.createProfile`／`deleteProfile`） |
| DQ-17（管理 API 用 `X-MCP-Profile`；UC-10） | P9 kit；`acceptance.md` 的每次升版重驗 |
| DQ-19（`/health/ready` 只代表預設帳號） | 容器階段看子程式與 listener，不看 readiness |
| DQ-20 (b)（看門狗照 PaaS） | SIGKILL 後重起 |
| DQ-28（OpenDesign、Odoo Manage 沒有帳號） | 不影響工具；測試照所有已知產品跑規則 |
| DQ-33（短 TMPDIR） | 本機檢查 |
| DQ-36（不改版號、不碰 `addons/`、commit 不加 AI 署名） | 全片 |
| DQ-39 (a)（UC-08 證實偵測不到就不出貨） | `acceptance.md` 每次升版重驗 |
| DQ-44（待定） | 沒做，第 11 節 |

## 15. 待 HM-03a／b 確認的項目（本片沒有量）

- UC-08：full、partial、加密三種還原各自有沒有觸發兩個訊號（容器裡的還原是在原地改擁有者與權限，sentinel 靠 ctime 判出；Supervisor 真的
  copytree 產生新 inode，要實機看）。
- UC-25：sentinel 的 inode 與 ctime 在 add-on 重啟、主機重開、add-on 更新、Supervisor 更新後不變。
- UC-10：Ingress 照原樣轉送 `X-MCP-Profile` 與 PATCH、DELETE（P9 kit 的帳號流程靠它）。
- HAOS 上額外帳號子程式的 `oom_score_adj` 能不能寫成 500（add-on 容器本身是 200）、`nice` 能不能加 5（容器階段只在 docker 驗）。
- HAOS 上 add-on 的 open file 上限（`raise_open_file_limit` 讀到的值）。
- UC-19 不在 HAOS：第一次升版 PR 的 Store CI。

## 16. 驗收條件（計畫 §12.3 HM-16）

| 條件 | 狀態 |
|---|---|
| packaging 測試綠 | 本機 `Ran 248`、`OK (skipped=5)`；CI 待 PR |
| 單帳號探針路徑不變 | 有測試證明（第 3.2 節）：AST 和 `f4c7718` 相同；`container_acceptance` 逐字相同 |
| 實際容器在 HM-19a 前的 builder 乾跑 | 本片不跑（規則），交 HM-19a（第 13 節） |
| 計畫的「做法」各項 | 容器多帳號階段、`fixture_snapshot` 放寬、P9 kit、hook 草稿與測試、`acceptance.md`、`ha-p9-kit.md`：都做了（第 3 節）。DQ-44 的合成帳號樹待定 |
