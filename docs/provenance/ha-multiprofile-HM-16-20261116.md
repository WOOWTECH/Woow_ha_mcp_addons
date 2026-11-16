# HA 多帳號 HM-16 provenance：驗收工具（容器探針多帳號階段與還原樹、P9 kit、Store hook、acceptance.md）（2026-11-16）

## 結論

- **只改驗收工具與文件，不改執行期**：沒有動 `packages/mcp-admin-core/`、`packages/mcp-admin-ui/src/`、`apps/`、
  `packaging/entrypoint.py`、`management_launcher.py`，也沒有動 `addons/`、版號、CHANGELOG。帳本與 tool-surface 不用改（第 9 節）。
  `MULTI_PROFILE_PRODUCTS` 維持空集合，開關只在測試裡開。
- **容器探針的多帳號階段**（`packaging/container_profiles.py`，新）：只在開通的候選映像、單帳號路徑之後跑。預設加 2 個額外帳號、
  交叉 token 與 session、每個 session 是自己子程式的（直接問每個子程式）、子程式 bearer 交叉、`oom_score_adj`／`nice`、SIGKILL 一個
  子程式其他 PID 不變、30 秒內並行停、sentinel 沒被動過、`/data/mcp` 符合修復規則與項目預算、照 Supervisor 的方式還原整棵多帳號樹後
  修好且兩個訊號都成立（第 3.1 節）。n8n 開通（HM-25）前不收 n8n（第 14 節）。
- **單帳號探針路徑逐位元不變，有測試證明**：`container_probe.py` 只加兩個 import 與三個「開通才走」的 `if`。測試把現在的檔和 `f4c7718`
  的檔**兩邊都剝掉開通的部分**再比 AST：完全相同，而且多出來的剛好是本片的那幾個（第 3.2 節）。HM-13b 合併後只要移 `BASE`（已拿 HM-13b
  的實際檔案模擬過）。`container_acceptance.py` 對沒開通的每個產品，docker 指令與 180 秒逐字照舊。
- **開通的產品的假後端**：照 Headscale 開一次性 internal bridge、`mock_bind_host` 回容器私有位址、探針上限 360 秒（HM-20 審查 MF-2）。
  HM-20 的兩個 tripwire 改成對規則本身的斷言（每個產品開與關各驗一次），另留「repo 的開關決定它」的測試（第 3.3 節）。
- **`fixture_snapshot` 只對開通的產品放寬**（C4-SF-5）：開通時改走多帳號布局的快照（名稱照布局、修復規則、512 項／8 層預算、子程式
  工作目錄是空的）；沒開通的照舊（最多 16 個一般檔）。
- **P9 kit**：`--profile`、`--cross`（交叉矩陣）、`--temp-profile`（暫時帳號）、開通的 app 的 `childkill` 只殺那個帳號的子程式，殺掉後
  輪詢到新 PID、再等到子程式自己的 session 才算恢復；建立或刪除結果不明就停、絕不重送；不走主機 shell 的代理；輸出只用帳號 log id
  （第 3.4 節）。對照 PaaS `public_probe.py --temp-profile` 補了兩項（第 4 節）。
- **Store hook 草稿**：`packaging/hooks/seed`、`verify`（只讀、與版本無關、只用標準庫、不跟隨連結）；對真的 runtime 也有測試。HM-19a
  升版時才搬進 `addons/odoo/upgrade-check/`（第 3.5、13 節）。
- **`tests/owned_executable.py` 修好**（HM-01 的工具，HM-20 交來）：開通的產品的預設帳號現在起得來；額外帳號仍不支援，明確拒絕
  （第 3.6 節）。
- **`docs/operations/acceptance.md`**：T-01～T-29 的 HA 版（每列寫明每一層實際驗哪幾項、Odoo 首發欄）、每次升版重驗 UC-08／UC-10／
  sentinel 並記 Supervisor 版本；HM-03a／b 沒有結果，寫明不得宣稱（第 3.7 節）。`ha-p9-kit.md` 補多帳號一節。
- **獨立審查「修正後通過」，意見都處理了**（第 18 節）：必修 3 項（MF-1 stage 的判定與參數加測試、MF-2 P9 childkill 輪詢、MF-3 交 HM-13b
  清單與 AST 比對）都改了；建議 9 項採用 8 項，SF-2（n8n）照審查的「至少」寫進文件與交 HM-25，另讓探針明確拒絕 n8n。審查沒抓到的 10 個
  變異，加上本輪新加的，共 64 個變異全部抓到。
- **本機**（修正後，第 7 節）：packaging unittest `Ran 259`、`OK (skipped=5)`；node 93 過；validate 過；pytest 審查的 19 檔目標組重跑
  862 案：855 過、7 個失敗都是要 root 的既有案例、0 skip。兩個預檢：秘密 0 命中、帳本 OK（第 8 節）。
- **實際容器沒跑**：多帳號階段第一次真跑在 HM-19a 前的 builder 乾跑（要使用者授權），本片不跑 builder、不跑 docker（第 13 節）。
- `checks` 秒數：開 PR 後補。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-16（計畫 §12.3：驗收工具；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm16-20261116`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `f4c7718`（HM-00～HM-11、HM-13a、HM-14、HM-17、HM-02、HM-20、#100、HM-31（#105）、HM-09 追補（#106）、HM-11（#107）都已合併） |
| 依據 | 計畫 §11（交付、§11.3 升版逐檔清單）、§12.3 HM-16（含 2026-11-15 HM-20 審查 MF-2 的補充）、§10（T-01～T-29、§10.4、§10.6）、§8.4（還原守門）、C4-SF-5、C4-SF-14；FM-16、63、101、102、107、108、135、147；契約第 2.2、2.3、9 節（#72、#73） |
| 對齊的 PaaS | `woow-mcp-server` 的 `public_probe.py --temp-profile`（repin `d7f58493` 的版本，`artifacts/mcp-security-release-20261112/repin-d7f58493-20261116/public_probe.py`，repo 外）；PaaS CI 映像 smoke（`.gitea/workflows/ci.yml`）只看預設帳號，HA 的多帳號容器階段沒有 PaaS 對應（契約 §9 #73） |
| 獨立審查 | `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-16.md`（判定「修正後通過」；證據 `wave4/evidence-review-HM-16/`）。修正的腳本、log、變異結果：`wave4/evidence-fix-HM-16/`（repo 外） |
| PaaS 變動 | 第 4 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/container_profiles.py`（新） | 容器探針的多帳號階段（第 3.1 節）：`stage()` 與它的每一段（`tree_snapshot`、`create_profiles`、`detect_as_runtime`、`child_ports`、`listeners`、`profiles_up`、`check_resources`、`kill_one`、`stop_within`、`check_routing`、`ping_child`、`check_child_bearers`）、`private_mock_host`。`stage()` 一開始就拒絕 n8n（第 14 節） |
| `packaging/container_probe.py` | 兩個 import（`features`、`container_profiles`）與三個「開通才走」的 `if`：`mock_bind_host`（私有位址）、`fixture_snapshot`（多帳號快照）、`run()` 最後呼叫 `container_profiles.stage`。其他逐句照 `f4c7718` |
| `packaging/container_acceptance.py` | 讀 repo 的開關（`mcp_admin_core.features`）；開通的產品照 Headscale 開一次性 internal bridge（網路名 `woow-<產品>-candidate-<hex>`，Headscale 不變）、`docker run` 上限 360 秒；沒開通的照舊 180 秒 |
| `packaging/ha_p9_probe.py` | `cross` 模式；`Client` 的密鑰網址接法與額外標頭，改用不讀環境代理的 opener（所有模式）；`childkill --child-port` 與 `CHILD_PORT_SCRIPT`、殺掉後輪詢（`CHILD_BACK_SECONDS`、`CHILD_LOOK_SECONDS`）與 `wait_child_session`；cross 與 childkill（帶 port 時）失敗 exit 1。沒給新參數的模式除了 opener 和以前逐行相同 |
| `packaging/ha_p9_admin.mjs` | `logId`、`revealToken`、`crossLine`、`crossLines`、`temporaryLabel`、`withTemporaryProfile`、`childPortOf`；審查 SF-3 後再加 driver 的三段組裝：`childkillArguments`、`runCross`、`runTemporaryProfile`（probe 由參數傳入） |
| `packaging/ha_p9_driver.mjs` | `--profile`、`--cross`、`--temp-profile`（呼叫上面三個函式）；開通的 app 的 `childkill` 帶 `--child-port`；沒開通的 app 照舊 |
| `packaging/hooks/seed`、`verify`（新） | Store 升版比對 hook 草稿（第 3.5 節）；可執行、`#!/usr/bin/env python3`、LF |
| `tests/owned_executable.py` | 開通的產品：Supervisor 與 HealthMonitor 替身收下開通時的選項，spawn 檢查改試綁私有 port；只服務預設帳號。沒開通的照舊（第 3.6 節） |
| `packaging/test_container_profiles.py`（新） | 多帳號階段每一段、整個階段的順序、每一步拿到的參數與 stage 自己的判定（第 5 節） |
| `packaging/test_container_probe.py` | HM-20 tripwire 改成規則本身；單帳號路徑 AST 比對（兩邊都剝）；`fixture_snapshot` 開與關 |
| `packaging/test_container_acceptance.py` | 沒開通的逐字照舊、開通的走 bridge 與 360 秒、repo 的開關決定它 |
| `packaging/test_ha_p9_probe.py` | `cross` 模式、`childkill --child-port`（含延後重起與閘道自答）、`CHILD_PORT_SCRIPT`、不走環境代理 |
| `packages/mcp-admin-ui/tests/p9-admin.test.mjs` | P9 的帳號流程（暫時帳號、不重送、刪除前重讀索引版本、交叉輸入、childkill 的 port、driver 三段組裝的順序與參數） |
| `tests/test_upgrade_hooks.py`（新） | hook 只讀、與版本無關、升級不該做的事都讓 verify 失敗、索引不跟隨連結、在自己的程序裡不走代理、對真 runtime、檔案照 Store 規則 |
| `tests/test_owned_executable.py` | 開通的產品經 owned executable 起預設帳號 |
| `docs/operations/acceptance.md`、`ha-p9-kit.md` | 第 3.7 節 |
| `docs/multi-profile/acceptance-matrix.md` | 審查 SF-7：測試檔登記表更新本片的檔；T-15 的容器欄寫明只驗自己的 port；檔頭狀態加一句 |
| `docs/provenance/ha-multiprofile-HM-16-20261116.md` | 本筆記 |

沒改：`docs/multi-profile/` 的其他文件（契約第 9 節不加列，理由見第 10 節；決策沒有新定案）；`addons/`；版號；CHANGELOG；
`packaging/test_entrypoint.py`（多帳號目錄樹的修復由容器還原階段與 `tests/test_restore_detection.py` 涵蓋，FM-16 第 3.1 節）。

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
3. **路由（T-05）**：每個帳號的 token 用兩種接法都開得了 session，而且是子程式的 session（不是閘道自答的 `woow-local-`）。閘道把子程式
   自己的 session id 原樣交給用戶端，所以開完後**直接問每個子程式**（帶它自己的 child token 與那個 session id，送 `ping`）：只有開這個
   session 的帳號的子程式回 200，別的子程式回 404（MCP SDK 2.3.0 對不認得的 session）。兩個帳號一致互用對方的子程式（審查 SF-1、實驗 X1）
   因此會失敗。兩種接法列的工具相同，三個帳號也相同（建立時複製政策，DQ-02）；每個 session 拿任何別帳號的 token（兩種接法）都 404；
   隨機 token：Bearer 401、密鑰網址 404。開過的 session 一律 DELETE（失敗時也結束）。
4. **子程式 bearer（T-23、HM-06）**：每個子程式照 HM-06 的 `assert_child_bearer`（不帶、隨機 401，自己的 200 並結束 session），另加「每個別帳號的
   child token 都 401、沒有 session」。
5. **子程式資源（HM-09）**：額外帳號 `oom_score_adj` 500、`nice` 是管理程序的值加 5；預設帳號子程式和管理程序相同。
6. **SIGKILL（T-13）**：殺第一個額外帳號的子程式：看門狗以新 PID 重起、重新在自己的 port 上聽；其他子程式全程 PID 不變；被殺的帳號之後照常服務
   （開得到不是 `woow-local-` 的 session）。
7. **停機**：SIGTERM 後 30 秒內（HA 的停止上限）exit 0、每個子程式都回收；秒數印在最後一行。
8. **sentinel 與布局**：停機後 detect 是 `consistent`、沒有標記（起停、三個子程式、看門狗重起都沒碰到 sentinel）；`tree_snapshot`
   （`fixture_snapshot` 的開通版）通過：每一項是一般目錄或單一連結的一般檔、同一個檔案系統、10001、0700／0600、名稱是布局裡的、
   每個子程式工作目錄是空的、總數 ≤512 與深度 ≤8（`packaging/entrypoint.py` 的修復上限：這棵樹的備份還原得回來，FM-16）。
9. **多帳號還原樹**：先記下每個 state、索引、record 的位元，用單帳號還原階段的 `restore_as_supervisor()` 把整棵樹改成 root（檔案 0644、
   目錄 0755），再起一次：`check_restored_start()`（標記存在且私有、每一項改回 10001 與 0700／0600、預設 state 位元不變）、其他 state、索引、
   record 位元都不變、三個子程式都重新起來；停機後 detect 是「有標記＋`mismatch`」：兩個訊號都成立。

`stage()` 自己的判定（第 1 步的 `established`、第 8 步的 `consistent`、第 9 步的位元不變與「標記＋`mismatch`」）和它交給每一步的參數
（等哪些 port、殺哪個帳號、routing 與 child bearer 拿到哪些帳號）都有測試守著（審查 MF-1，第 5、18 節）。

最後印一行（沒有秘密）：`PASS multi-profile: default + 2 profiles up in N s; routing, child bearer, resources, SIGKILL, stop in N s; N entries;
restore tree and both signals`。等不到時只寫 port（例如 `children up on [3000] of [3000, 18000, 18001]`）：探針從不印執行期輸出。

時間：單帳號路徑之外多兩次啟動、一次看門狗重起與一次還原後啟動，推估 40～60 秒；開通的候選映像把 `docker run` 上限從 180 改 360 秒
（HM-13a 交辦「180 秒上限要跟著看」）。容器的 open file 上限要 ≥680（Odoo 的 `open_file_budget` 要求；其他產品 530）：
docker 預設的 1024 夠；不夠時額外帳號不服務，第 2 步會失敗在上面那行訊息。

### 3.2 單帳號探針路徑逐位元不變的證明

- `packaging/test_container_probe.py::SingleProfilePathTests`：拿 `git show <BASE>:packaging/container_probe.py`（CI 的 checkout 是完整歷史；
  `BASE` 現在是 `f4c7718`）和現在的檔，**兩邊都**拿掉開通的部分（`features`、`container_profiles` 兩個 import，以及「條件呼叫
  `features.enabled`」的 `if`，不管在哪一層）再比：
  - 剩下的 AST 完全相同（`ast.dump`，同一個直譯器當場算，不怕版本差）；
  - `BASE` 原有的開通部分一個都不能少、不能改（逐個比 `ast.dump`）；
  - 相對 `BASE` 多出來的，剛好是 `import container_profiles`、三個交給 `container_profiles` 的 `if`（`mock_bind_host`、`fixture_snapshot`、
    `run()`），以及 `BASE` 沒有時的 `features` import。
- 另驗 `run()` 只有一個這種分支、是 `httpx.AsyncClient` 區塊的最後一句、內容是 `await container_profiles.stage(sys.modules[__name__], client)`。
- 審查 MF-3 (b) 之前的寫法只剝現在這份、計數寫死 5，HM-13b（PR #108）自己也加了 `features` import 與還原檢查的開通分支，只移 `BASE` 會紅。
  現在拿 HM-13b 的實際檔案模擬過（GitHub fetch 的 `ebab019`；`git merge-file` 三方合併，`evidence-fix-HM-16/logs/x3-real-hm13b.txt`）：
  `BASE` 換成 HM-13b 的版本、本片的改動接上去並拿掉合併留下的重複 `features` import 後就過；重複的 import 留著會紅（要求拿掉）。
- 之後有片要刻意改單帳號路徑，就把 `BASE` 改成它自己審過的基準 commit，並在筆記寫明理由；不用改其他地方。
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
- `childkill`（開通的 app）：driver 從帳號清單取那個帳號的 port（`childkillArguments`），probe 以 `--child-port` 依命令列找出唯一一個子程式；
  找不到唯一一個就什麼都不殺。審查 MF-2 之後：
  - 看門狗第一次重起要等 2 秒（`lifecycle.AUTO_RESTART_DELAYS[0]`），這段時間閘道自己回 initialize（200＋`woow-local-` session），
    所以殺掉後每 0.5 秒看一次子程式清單、最多 60 秒，直到剛好一個新 PID 服務那個 port；期間別的帳號子程式出現新 PID 就立刻停下、失敗。
  - 「恢復」要那個帳號的 token 開得到子程式自己的 session（`wait_child_session`，最多再 60 秒）；閘道自答的 session 一律 DELETE、只計數。
  - 殺之前開的 session 也 DELETE。輸出 `new pid … after N s (K looks)`、`child's session after M s more (J gateway sessions before it …)`。
  - 新 PID 沒出現、一直是閘道自答、或別的 PID 變了，exit 1。
  - 沒帶 `--child-port` 的舊 childkill 不改；它印的 `recovered in` 是閘道自答的時間，`ha-p9-kit.md` 寫明要看 `child pids now`。
- `--cross`（`runCross`）：每個帳號在自己的 `X-MCP-Profile` 下 reveal token；probe 的 `cross` 模式驗兩種接法、session 不跨帳號（404）、
  隨機與已刪的 token 被拒；開 session 時都帶 `X-MCP-Profile: default`，證明 MCP port 不看它（契約第 2.2 節）。
- `--temp-profile`（`runTemporaryProfile`）：用剛讀到的索引版本建 `p9-temp-<8 hex>` →（`--backend-file`、`--plan`；沒後端又有 `PROBE_TOOL`
  時工具呼叫要被拒）→ 和預設帳號交叉 → 刪除（重讀索引版本；前面失敗也照刪）→ 舊 token 被拒。
- **不自動重送**：建立、刪除、token 操作的結果不明就印識別碼與路由、停止；刪除不明時另印「暫時帳號可能還在」。
- **不走環境代理**（審查 SF-5）：probe 的所有模式都改用 `ProxyHandler({})` 的 opener。密鑰網址模式的 token 在 URL 路徑上，HA 主機 shell 若設了
  `http_proxy` 就會進代理；以前的 `urlopen` 也會把 loopback 的請求送進代理（沒設 `no_proxy` 時），只會連不到。
- driver 本身一載入就登入 HA，沒有測試；三段組裝搬進 `ha_p9_admin.mjs` 後由 node 測試斷言呼叫順序與參數（審查 SF-3）。

### 3.5 Store 升版比對 hook 草稿（FM-102、FM-135；C4-SF-14）

- `seed`（舊版起來後）：`/data/mcp` 與 `state.json` 屬 10001 且私有；預設 token（從 `state.json` 讀，不印、不存）兩種接法都開得了 session 並結束；
  隨機 token 被拒；沒有還原標記；在 `$HOOK_STATE_DIR` 留 `state.json` 與索引的 SHA-256 與三個名稱在不在。
- `verify`（新版起來後）：seed 的檢查再做一次；`state.json` 位元不變（I6、零改寫）；索引與 `profiles/` 和升級前一樣（沒有的不能冒出來，有的
  位元不變）；沒有還原標記（升級不是還原）。
- **只讀**：兩支都不寫 add-on 的資料（測試比每一項的位元、擁有者、mode、大小、mtime、ctime）。**與版本無關**：不比版本、serverInfo、工具清單，
  不讀 `ADDON_VERSION`、`ADDON_IMAGE`、`PHASE`（測試換三組值結果相同，原始碼也不提）。**DQ-44 待定**：不寫合成帳號樹，只斷言索引位元不變。
- **不跟隨連結**（審查 SF-8）：`state.json` 與索引都用 `read_plain`（`O_NOFOLLOW`、只收一般檔、64 KiB 上限）讀；索引是連結或讀不到時記
  `unreadable`，`verify` 對這種索引判失敗（確認不了位元不變）。
- `verify` 用 `SourceFileLoader` 載入同目錄的 `seed`（Store 掛整個 `upgrade-check/`），兩個階段同一套規則。
- 直接連 add-on：HTTP 用不讀環境代理設定的 opener（`ProxyHandler({})`）。測試讓每個 hook 在自己的程序裡、帶代理環境變數跑（像 Store 那樣；
  審查 SF-9：原本在 hook 載入之後才設代理，改回 `build_opener()` 也照綠）。
- 對真 runtime（審查 SF-6）：`run_product` 經 owned executable，舊版沒開通、新版開通或也沒開通（Odoo、EMQX）：seed、verify 都過，不改 `/data`，
  開通後第一次啟動不會冒出索引或 `profiles/`。兩次都跑這個 checkout 的程式：驗的是 hook 對現在閘道的假設，不是 0.4.13。
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
  門檻、五層與工具（LOCAL/MOCK 含 `packaging/unit.sh` 與 packaging unittest）、容器多帳號階段驗什麼、T-01～T-29 每列「怎麼驗」（每一層實際驗
  哪幾項，沒寫到的只在 LOCAL）、「通過標準」與「Odoo 首發」欄、「每次升版都要重驗」（UC-08 三種還原、sentinel 穩定性含主機重開、UC-10，記
  Supervisor／Core／HAOS 版本）。可執行 gate 一節補多帳號階段。審查 SF-4 逐列對過計畫 §10.4。
- `docs/operations/ha-p9-kit.md` 加「多帳號（HM-16；只對開通的 app）」一節與證據要記的版本；childkill 的輪詢與恢復標準、舊 childkill 的
  `recovered in` 是閘道自答的時間、probe 不走代理、n8n 開通前認不出子程式。

## 4. PaaS 對照與變動

- `public_probe.py --temp-profile`（repin `d7f58493`）逐項：建第二帳號 → 用它自己的網址測 → 沒後端的工具呼叫不能成功（不借預設帳號的連線）→
  帶 `X-MCP-Profile: default` 不會切到預設帳號 → 拿預設帳號的 session 被拒 → 刪除 → 舊網址被拒 → 預設帳號照常。HA 的 P9 kit 每一項都有
  （錯 token 是 HA 的 404／401，不是 PaaS 的 403，契約 §9 #1）。PaaS 另印「刪除後資料夾還在嗎」：HA 交本機測試與面板（`ha-p9-kit.md`）。
- PaaS 的 CI 映像 smoke 只看預設帳號（FM-101），HA 的容器多帳號階段沒有 PaaS 對應（§9 #73 已涵蓋發佈流程的不同）。
- 本機唯讀 PaaS repo（`…/mcp-path-param-guard-20261106-claude/paas-repo`，沒 fetch、沒 checkout；`origin/main`＝`7087280`）：
  `git log --oneline d7f5849..origin/main` 是 #135（EMQX 不留閒置連線）、#139（LiteLLM 同）、#138（Hermes cron 停用建立）三次合併，改的是
  `apps/emqx`、`apps/hermes`、`apps/litellm` 的子程式，和驗收工具無關。`git log 69ac425..origin/main -- .gitea/workflows/ci.yml 'apps/*/scripts/ci_smoke_child.py'`
  只有 `36bde7b`（移除 VK）；`packages/mcp-admin-core/mcp_admin_core/profiles.py`、`restore_*.py` 只有 #155 的 `e6971c0`（HM-31 已對齊）。
  審查時重查一致（`review-HM-16.md` 第 4 節）。

## 5. 測試（新與改過的）

| 檔 | 案例 | 驗什麼 |
|---|---|---|
| `packaging/test_container_profiles.py`（新） | 35 | 布局快照（設計的樹照收、13 種布局外的東西各自失敗、預算與深度、別的檔案系統、journal 名稱）；fixture（兩個帳號照面板建立、政策複製、token 互異、預設 state 不動、建的每一項而且只有它們交給 10001、沒後端就不建）；detect 以子程序跑（建、保持、被當成還原、標記；帳號資料先出現是 `record_missing`；容器裡用 10001、沒有附加群組）；子程式 port、listener、資源（加 5 不是設成 5）；SIGKILL（只殺那個、它回來、別的重起或回不來都失敗）；停機（量秒數、逾時、非 0、孤兒）；路由（9 種壞法各自失敗、訊息不含 token 或 child token、失敗也結束 session；B、C 互用對方子程式）；子程式 bearer 交叉；整個階段的順序、每一步的參數、stage 自己的 4 個判定各自失敗並停掉 runtime、n8n 被拒 |
| `packaging/test_container_probe.py` | +6（共 19） | 私有位址（每個產品開／關、repo 開關）、單帳號路徑 AST 比對（兩邊都剝）、stage 的位置、`fixture_snapshot` 開與關 |
| `packaging/test_container_acceptance.py` | +2（共 6：加 3 個、拿掉 HM-20 的 1 個） | 沒開通的逐字照舊、開通的 bridge 與 360 秒、repo 開關 |
| `packaging/test_ha_p9_probe.py` | +13（共 26） | cross 模式（通過、已刪的 token、三種壞法、輸入格式）、`childkill --child-port`（只殺那個、預設帳號、延後重起且閘道先自答、一直沒回來、一直是閘道自答、別的重起或回不來、找不到唯一一個）、`CHILD_PORT_SCRIPT`、在自己的程序裡帶代理環境變數也直連 |
| `packages/mcp-admin-ui/tests/p9-admin.test.mjs` | +12（共 16） | log id 與 reveal、沒有啟用 token 的帳號、暫時帳號（成功且刪除用重讀的索引版本、用的時候失敗也刪、建立或刪除回應遺失就停不重送、沒有索引版本不建立）、childkill 的 port；driver 組裝：childkill 參數、`--cross`、`--temp-profile`（有後端與 plan、沒後端的 `PROBE_TOOL`、用的時候失敗） |
| `tests/test_upgrade_hooks.py`（新） | 22（其中參數化 11＋4） | hook 只讀、與版本無關、11 種升級不該做的事各讓 verify 失敗、已有索引位元不變、索引是連結時不跟隨、seed 的失敗、在自己的程序裡不走環境代理、對真 runtime（4 案）、檔案照 Store 規則 |
| `tests/test_owned_executable.py` | +1 | 開通的產品經 owned executable 起預設帳號 |

測試資料：token 一律在測試執行時產生（`secrets.token_urlsafe`），node 測試用 `T`×43、`C`×43、`S`×43；憑證 `DUMMY`、網址 `.invalid`；沒有 commit
任何隨機 token。新 pytest 檔都在 HM-01 的 log 掃描下跑（token 已登記）。沒有條件式 skip。

## 6. 先紅後綠

| 組 | 紅（新測試在基準的實作上） | 綠 |
|---|---|---|
| 容器探針與驗收（`test_container_*.py`） | `1d69c8c` 的測試＋`f4c7718` 的 `container_probe.py`／`container_acceptance.py`、沒有 `container_profiles.py`：`Ran 26`、failures=57、errors=3（`test_container_profiles` 匯入失敗；沒開通的測試在基準照過，證明行為是基準的） | `Ran 53`、OK |
| P9 kit（`test_ha_p9_probe.py`、`p9-admin.test.mjs`） | 基準的 kit：packaging failures=3、errors=5；node 測試檔匯入失敗（沒有新匯出）。兩個在基準因為 argparse 拒絕新參數而「照過」的測試，改成斷言各自的拒絕訊息 | packaging `Ran 22`、OK；node 11 過 |
| cross 的 `X-MCP-Profile` | probe 開 session 不帶這個標頭時，「switches by header」子案例失敗 | 過 |
| hook 與 owned executable（pytest，一次排隊在共用鎖裡先紅後綠） | `packaging/hooks/` 不在、`tests/owned_executable.py` 是基準：`tests/test_upgrade_hooks.py` 收集就失敗（`FileNotFoundError`：沒有 hook）；新的 owned executable 測試失敗（子程序的 log 是 `assert not kwargs` 的 `AssertionError`，就是交來的問題）。1 failed、1 error、0.83 秒 | 目標 11 檔 586 案：580 過、6 個要 root 的既有案例失敗 |
| 審查修正的新測試（2026-11-17；`evidence-fix-HM-16/logs/red-on-957c639.txt`） | 修正後的測試＋`957c639` 的 `ha_p9_probe.py`、`container_profiles.py`、`ha_p9_admin.mjs`：P9 `Ran 26`、failures=1（代理）、errors=7（childkill 輪詢）；容器多帳號 `Ran 35`、failures=2（參數、n8n）、errors=11（路由問子程式）；node 測試檔匯入失敗（沒有 driver 組裝的匯出）。MF-1 的判定測試在舊實作照過（判定本來就對，缺的是守住它的測試），用變異證明 | 第 7 節 |
| 審查修正的變異（`evidence-fix-HM-16/mutations/`） | 64 個：packaging 42、node 10、pytest 12，**全部紅**。含審查沒抓到的 10 個（PM10～PM15、NM03、NM07、NM08、HM06；NM07、NM08 跟著程式搬進 `ha_p9_admin.mjs`），與新加的 PS1～PS3（子程式的 session）、PP1～PP5（childkill 輪詢；PP1 就是審查的問題本身：只看一次）、PX1～PX2（P9 代理）、HS1～HS2（hook 的索引連結）、PA1（開通分支不交給 `container_profiles`）、PN1（n8n）、NM09～NM10 | — |

## 7. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排隊在共用鎖）

第一輪（2026-11-16，`957c639`）：

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（CI 的 PyYAML venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（照 CI：離線暫存 venv＝`uv sync --frozen --no-dev --offline`＋`requirements-ci`；`discover -s packaging`） | `Ran 248`、`OK (skipped=5)`（5 個 `skipUnless(root)`，同基準）；27.9 秒（基準 `Ran 203`、22.0 秒） |
| node（`npm test --prefix packages/mcp-admin-ui`） | 88 過、0 失敗（基準 81） |
| pytest 目標 11 檔 | 586 案：580 過、6 失敗（都是要 root 的既有案例）、0 skip，262 秒 |

審查修正後（2026-11-17，`6fd1320`，之後只改本筆記；log 在 `evidence-fix-HM-16/logs/`）：

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（CI 的 PyYAML venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（照 CI 的離線 venv；`discover -s packaging -v`） | `Ran 259`、`OK (skipped=5)`，24.3 秒（`packaging-unittest-dev.txt`）。新模組：`test_container_profiles` 35 案 5.6 秒、`test_ha_p9_probe` 26 案 3.6 秒、`test_container_probe` 19 案 2.9 秒 |
| node | `npm test --prefix packages/mcp-admin-ui`：93 過、0 失敗；`p9-admin.test.mjs` 16 過；`node --check` driver、admin 過 |
| pytest 本輪目標（共用鎖；00:21:30 排隊就拿到，00:22:11 放掉；`t-pytest-targets.txt`） | `tests/test_upgrade_hooks.py` 22 案全過（9.3 秒；對真 runtime 4 案各約 2 秒）、`tests/test_owned_executable.py` 4 案 3 過＋1 個要 root 的既有案例、`tests/test_log_scan.py` 13 案全過：39 案 38 過、13.9 秒 |
| pytest 審查的 19 檔目標組（共用鎖；00:24:41 排隊就拿到，00:29:46 放掉；`t-pytest-broad.txt`） | **862 案：855 過、7 失敗、0 skip**，303.6 秒（審查在 `957c639` 是 857 案：850 過、7 失敗）。7 個失敗都是要 root 的既有案例（`test_owned_executable` 的 uid10001 1、`test_restore_detection` 的 `test_root_*` 5、`test_profile_store` 的 mode／owner 1）；HM-20 的 `test_backend_loopback` 全過、HM-01 守門全過 |
| 全套 pytest | 沒在本機跑：本片改到的 pytest 面只有 `tests/test_upgrade_hooks.py`（與它用到的 `owned_executable`），上面兩輪涵蓋；另查過沒有別的測試讀 `packaging/hooks/`、`docs/operations/`。以 CI 為準 |

### 7.1 只在 CI 跑的測試

- 新測試沒有只在 CI 跑的：全部在本機以一般使用者跑過（對真 runtime 的 hook 測試在 CI 以 root 跑：runtime 也是 root，hook 的擁有者參數用測試
  自己的 uid／gid，和本機同一條路）。
- 既有、要 root、本機一定失敗的（同基準）：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`、`test_restore_detection.py` 的 5 個 `test_root_*`。packaging 的 5 個
  `skipUnless(root)`。
- 實際容器（多帳號階段、開通的假後端 bridge）不在 CI：HM-19a 前的 builder 乾跑（第 13 節）。

### 7.2 `checks` 秒數與新測試的時間

- 開 PR 後補（前後兩個 run 的 `checks`）。
- 本機推估的增量（對基準 `f4c7718`）：packaging unittest ＋2.3 秒（22.0 → 24.3；假伺服器停機用 0.05 秒輪詢，P9 的輪詢上限在測試裡改小）；
  node ＋不到 0.1 秒；pytest：`test_upgrade_hooks.py` 22 案 9.3 秒（其中對真 runtime 4 案約 8 秒）、新的 owned executable 測試約 3.7 秒。
  CI（root、runner 較慢）推估合計 ＋20～30 秒，在每片 1.5 分鐘的預算內。

## 8. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密 | `.venv/bin/python -I scripts/secret_precheck.py --tools <gitleaks-tools> --repo . --base f4c7718 --head HEAD --full` | gitleaks 8.28.0（釘選、驗過）；`f4c7718..HEAD` 全部 23 個 commit（含本筆記）：**OK，0 命中** |
| 帳本 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base f4c7718` | 三本帳本 0 drift、0 missing；改到的 20 個檔沒有列管的、沒有新的執行期檔：**OK** |

## 9. 帳本與 tool-surface

沒有動任何列管檔，也沒有新的執行期檔（`scripts/ledger_precheck.py` 的執行期檔＝`packages/mcp-admin-core/`、`packages/mcp-admin-ui/src/`、
`apps/`、`packaging/entrypoint.py`、`management_launcher.py`）。新檔都不進映像：`container_profiles.py` 只在 builder 跑容器驗收時掛進
候選容器（和 `container_probe.py` 一樣不列管）；`packaging/hooks/*` 是 Store 的 CI 跑的；`packaging/ha_p9_*.mjs` 是操作端的工具；`tests/`
不進映像。所以 `runtime-patches.json`、`docs/tool-surface.*` 都沒改。HM-19a 把 hook 搬進 `addons/odoo/upgrade-check/` 後，它們算 Store 的
執行期內容指紋，不是映像的帳本。

## 10. 契約第 9 節

不加列。本片加的是驗收工具：P9 的暫時帳號與交叉檢查照 PaaS `public_probe.py`；錯 token 的狀態碼差異已是 #1；升級驗證是 #72；容器多帳號階段
屬發佈流程的不同（#73）。審查修正（容器問子程式的 session、P9 輪詢與不走代理、hook 不跟隨連結）也只在驗收工具裡，沒有新的 PaaS 可觀察差異。

## 11. 前面各片交給 HM-16 的待辦

| 來源 | 待辦 | 處理 |
|---|---|---|
| HM-05 第 11 節 | `acceptance/real_backends/ha_runtime.py` 還 patch `run_product.make_apps`（HM-05 起在 `profile_runtime`），拿新映像重跑會在 import 時失敗 | **不改**。這套真後端驗收凍結在 HA 0.4.6（source `28b8317`）與 `images.json` 的 digest，`controller.source_proof` 只認那個 commit 的位元；只改注入點也跑不了新映像，反而讓 0.4.6 的重跑和紀錄對不上。下次真後端驗收重新釘版時（source、映像、注入點一起改）再處理；它失敗得很明顯，不會默默失效。交 HM-19b／HM-29 |
| HM-06 | 探針多帳號階段沿用 `assert_child_bearer`（每個帳號的子程式 port 與 child_token） | 做了：`check_child_bearers`，另加別帳號 child token 401 |
| HM-09 | 容器探針多帳號階段：SIGKILL 一個其他 PID 不變、停機 <30 秒、真容器裡的 `oom_score_adj`／`nice` | 做了：`kill_one`、`stop_within`、`check_resources` |
| HM-10 | P9 kit 與容器探針的管理請求帶 `X-MCP-Profile`；多帳號的增刪改查與隔離在容器裡跑一次 | P9：做了（`AdminApi` 帶；`--temp-profile` 經真的管理 API 建與刪）。容器：**不在容器裡跑管理 API**：容器沒有 HA 管理員與 Supervisor，探針的規則是不繞過管理身分檢查；帳號照面板的建立方式以程式庫在停機時建，隔離（路由、session、子程式 bearer）在容器裡驗。管理 API 的增刪改查與索引隔離由 `tests/test_profile_admin_api.py`（CI）與 HAOS 的 P9 涵蓋 |
| HM-11 第 16.11、17.8 節 | P9 driver 的帳號參數與交叉矩陣（`createP9AdminClient(…, {profile})` 已就緒） | 做了 |
| HM-13a 第 11 節 | 容器探針的多帳號階段（含 sentinel 的 root 還原樹）接在 HM-13a 的還原階段之後；`docker run` 180 秒上限要跟著看 | 做了：階段在單帳號路徑（含 HM-13a 的還原階段）之後；開通的候選映像 360 秒。HM-13b 合併後要改的見第 12 節 |
| HM-13b 審查 S-3（PR #108 未合併；`wave4/pr-HM-13b.md` 的意見處理表與「後續片」） | 容器探針的還原階段收 stderr，斷言 entrypoint 的 `re-owned N` 與守門通知各一行；要在 HM-19a 前的 builder 乾跑之前做好 | **交 HM-13b 合併後、本片 rebase 時做**（第 12 節第 1 點）：守門通知那一行要 HM-13b 才有；收 stderr 要改單帳號路徑的 `start()`，一起改才只動一次 `BASE`。HM-19a 乾跑前一定要有 |
| HM-20 第 13 節（審查 MF-2） | 開通的產品：`container_acceptance` 開一次性 internal bridge、`mock_bind_host` 回私有位址；HM-20 的 tripwire | 做了；tripwire 改成規則本身的斷言（第 3.3 節） |
| HM-20 第 13 節、HM-01 的工具 | `tests/owned_executable.py` 起不了開通的產品（Supervisor 替身 `assert not kwargs`） | **修好**（預設帳號）；額外帳號明確拒絕（第 3.6 節；這個拒絕沒有專門的測試，審查列為小事，額外帳號的測試本來就用 `multi_profile_runtime.py`）。開通 Odoo 時既有 Odoo 測試的 loopback 假後端仍交 HM-19a |
| `decisions.md` DQ-44（負責片含 HM-16 的工具） | 0.5.0 之後的升版比對怎麼驗「有額外帳號」的資料 | **待定，沒做**：hook 草稿不寫合成帳號樹、不要 `ha_core`，只斷言與版本無關的事與索引位元不變；DQ-44 照表在 R2 升版 PR 前定 |
| `acceptance-matrix.md` 檔頭 | 把它寫進 `docs/operations/acceptance.md` 與 P9 kit | 做了（第 3.7 節）；測試檔登記表也更新（審查 SF-7） |
| FM-16 | `packaging/test_entrypoint.py` 補多帳號目錄樹 | 改由容器的多帳號還原階段（真 entrypoint、真映像）與 `tree_snapshot` 的修復規則檢查涵蓋；`packaging/test_entrypoint.py` 不改（CI 那一步不以 root 跑，root 才造得出的情境放 `tests/`，計畫 §10.1） |

## 12. 交 HM-13b／HM-13c 之後補

HM-13b（開機守門）還沒合併，本片照 HM-13a 已合併的行為與計畫 §8.4 做。計畫規定本片在 HM-13c 之後合併：HM-13b、HM-13c 合併後，本片 rebase
時一起做下面幾點（不然 HM-19a 前的 builder 乾跑會失敗）：

1. **還原階段收 stderr（HM-13b 審查 S-3 交來）**：單帳號與多帳號的還原後那次啟動，把 entrypoint 與管理程序的 stderr 收到容器 `/tmp` 的暫存檔
   （不印、跑完刪；探針從不印執行期輸出），斷言：
   - entrypoint 的 `bootstrap: re-owned N restored entries in /data/mcp` 剛好一行，N＝還原的項目加標記（以 `entrypoint._repair_restored` 的計數為準）；
   - 守門通知剛好一行：單帳號（沒開通、沒有帳號資料）是 `restore_lock.KEPT_NOTICE`；多帳號還原（有帳號資料）是 `REVOKED_NOTICE`，另每個額外帳號
     一行 `REVOKED`（帶 id 前 8 碼）。
   要改 `container_probe.start()`（現在 stdout、stderr 都丟 DEVNULL）：這是單帳號路徑的改動，`BASE` 照第 5 點移到它審過的基準。HM-19a 乾跑前一定要有。
2. 單帳號還原階段：守門在還原後那次啟動就刪標記（HM-13b 的 `check_restored_start` 已改成「標記不在」）；`container_profiles.end_restore_marker`
   那時要改成「確認標記已不在」。
3. sentinel 的 fixture：HM-13b 接線後，開通產品第一次開機自己建 sentinel 與 record（開通的候選映像在單帳號還原階段就會有 sentinel、record 與
   `restore-record.json`）。`stage()` 第 1 步的 `detect_as_runtime` 要從「建出來（`established`）」改成「執行期已建好（`consistent`）」，不再由探針建；
   `StageTests` 的判定測試跟著改。
4. 多帳號還原之後（DQ-03 採 (b) A2：有帳號資料就連預設一起撤銷）：每個帳號的 token 撤銷、child_token 重產（`kept_bytes` 的「位元不變」改成
   「token 是 null、child_token 不同、其他欄位不變」）、多出 `restore-record.json`、還原前的 token 兩種接法都被拒（404／401）、標記被刪、
   sentinel 重建（最後的 detect 從「有標記＋`mismatch`」改成「沒有標記＋`consistent`」）。
5. 單帳號路徑的 AST 比對：把 `test_container_probe.py` 的 `BASE` 改成 rebase 後的 `claude-delivery` commit（HM-13b、HM-13c 已合併、第 1 點的改動
   審過的基準），筆記寫明理由；其他不用改（兩邊都剝掉開通的部分，HM-13b 的還原檢查分支在兩邊都有）。合併若留下兩個
   `from mcp_admin_core import features`，拿掉本片那個（測試會要求）。已用 HM-13b 的實際檔案模擬（第 3.2 節）。
6. 布局名稱：HM-13b 若加新名稱（例如封存的 journal `.restored`、隔離目錄裡的檔），要加進 `container_profiles` 的 `TOP_NAMES`／`PROFILE_NAMES`
   （從 `profiles.py` 的常數取，不要另寫字串）；`.quarantine-<id>-<UTC>` 目錄本片已收。
7. HM-13c：還原核對卡、全部撤銷、刪隔離目錄是管理 API 的事，容器探針碰不到；HAOS 的演練照 `acceptance.md` 的 T-21（核對後才重發、舊收據 410），
   P9 kit 要不要加對應模式由 HM-13c 決定。`acceptance.md` 的 T-21 列在那時補具體步驟（「依 DQ-03」「獨立驗證」已寫）。HM-13c 的面板提示
   （使用者 2026-11-16 定案的 Q-1）若讓沒開通的單帳號還原後多一個 bootstrap 欄位，hook 不受影響（hook 不看 bootstrap）。

## 13. 交 HM-19a（與 builder 乾跑）

- **builder 乾跑（要使用者授權）**：拋棄式 commit 把 `odoo` 加進 `MULTI_PROFILE_PRODUCTS`、不推 GHCR，跑 `supply_chain.py candidate` →
  `container_acceptance`。這是多帳號階段與開通的 bridge 第一次真跑；把最後那行 `PASS multi-profile …`（含秒數）記進證據；失敗先查探針，不要放寬。
  要先合併 HM-13b、HM-13c 並照第 12 節改好探針（含第 1 點的 stderr 斷言）。docker 的 nofile soft 上限要 ≥680。
- 乾跑也是「每個 session 是自己子程式的」那一步（直接 `ping` 子程式，期望不認得的 session 回 404）第一次碰到真的 MCP SDK；SDK 換版時要重驗。
- **搬進 `addons/odoo/upgrade-check/` 的檔**（`git mv`，保留可執行位元）：
  - `packaging/hooks/seed` → `addons/odoo/upgrade-check/seed`
  - `packaging/hooks/verify` → `addons/odoo/upgrade-check/verify`
  - 同時把 `tests/test_upgrade_hooks.py` 的 `HOOKS` 改指新位置（mock 的與對真 runtime 的測試都用它；之後的產品各自一份時，改成逐目錄參數化）。
    不需要 `settings.yaml`（預設的 600 秒 hook 上限與 300 秒啟動上限夠）。
  - 第一次升版 PR 的 `Upgrade comparison` 會看到 UC-19（hook 能不能以 root 讀 `state.json`、連到 8081）；不行就停下回報，不要改成走管理 API。
- 計畫 §11.3 的逐檔清單已列 `container_probe.py`、`container_acceptance.py` 的假後端位址：本片已改成看開關，升版 PR 不用再改這兩檔。
- 既有 Odoo 測試用 loopback 假後端的（HM-01 黃金回歸、`test_real_products.py` 的 Odoo 案等）：開通後要用 `loopback_backends`（HM-20 第 13 節）。
  經 `owned_executable` 起的測試現在起得來（第 3.6 節）。

## 14. 交 HM-25（n8n 開通；審查 SF-2）

- n8n 子程式的 port 只在環境變數 `PORT`（`apps/n8n/n8n_adapter.py` 的 `child_spec`；同一個環境裡有 `AUTH_TOKEN`、`N8N_API_KEY`），命令列沒有 `--port`。
  容器階段的 `child_ports` 與 P9 的 `CHILD_PORT_SCRIPT` 都會把每個 n8n 子程式當成 3000（審查實驗 X2）：容器階段會報 `two children on one port`，
  P9 childkill 找不到唯一一個就什麼都不殺、失敗。都是失敗、不是假綠；本片另讓 `stage()` 在改任何東西前就明確拒絕 n8n。
- 不讀 `/proc/<pid>/environ`（會碰到秘密）。用 `/proc/net/tcp*` 的 socket inode 對 `/proc/<pid>/fd` 找 port 的主人，要以 root 讀另一個使用者的
  fd 連結，需要 CAP_SYS_PTRACE（docker 預設不給；本片沒有實測）。HM-25 的做法建議：讓 n8n 子程式的命令列帶一個看得到 port 的參數（或 exec 包裝器
  帶一個不含秘密的標記），探針與 P9 照命令列認；然後拿掉 `stage()` 的 n8n 拒絕。
- n8n 預設帳號子程式的 HOME 是它的目錄（預設帳號是 `/data/mcp`）：`tree_snapshot` 的名稱白名單要對 n8n-mcp 留下的檔重看（`nodes.db` 每帳號一份，
  計畫 HM-25）。
- T-22（`n8n_session` 每帳號一份、沒後端的額外帳號回 `backend_not_configured`）也在 HM-25。

## 15. 本片用到的決策

| DQ | 用在哪裡 |
|---|---|
| DQ-02（新帳號複製預設帳號當下的政策） | 容器路由檢查要求三個帳號列的工具相同 |
| DQ-03 (b) A2 | 第 12 節：HM-13b 之後多帳號還原的期望值；`acceptance.md` T-21 |
| DQ-10／DQ-40 ⑦（開通後拒 loopback） | 開通的產品的假後端改走 bridge 與私有位址 |
| DQ-12（索引被外改就 503） | owned executable 的新測試用它證明 8081 是開通後的分派器 |
| DQ-14（刪除先撤銷） | 暫時帳號刪除後舊 token 被拒 |
| DQ-15（帳號增刪 If-Match＋Idempotency-Key） | P9 的暫時帳號（`AdminApi.createProfile`／`deleteProfile`；刪除前重讀索引版本） |
| DQ-17（管理 API 用 `X-MCP-Profile`；UC-10） | P9 kit；`acceptance.md` 的每次升版重驗 |
| DQ-19（`/health/ready` 只代表預設帳號） | 容器階段看子程式與 listener，不看 readiness |
| DQ-20 (b)（看門狗照 PaaS） | SIGKILL 後重起；P9 childkill 的等待（第一次重起前 2 秒） |
| DQ-28（OpenDesign、Odoo Manage 沒有帳號） | 不影響工具；測試照所有已知產品跑規則 |
| DQ-33（短 TMPDIR） | 本機檢查 |
| DQ-36（不改版號、不碰 `addons/`、commit 不加 AI 署名） | 全片 |
| DQ-39 (a)（UC-08 證實偵測不到就不出貨） | `acceptance.md` 每次升版重驗 |
| DQ-44（待定） | 沒做，第 11 節 |

## 16. 待 HM-03a／b 確認的項目（本片沒有量）

- UC-08：full、partial、加密三種還原各自有沒有觸發兩個訊號（容器裡的還原是在原地改擁有者與權限，sentinel 靠 ctime 判出；Supervisor 真的
  copytree 產生新 inode，要實機看）。
- UC-25：sentinel 的 inode 與 ctime 在 add-on 重啟、主機重開、add-on 更新、Supervisor 更新後不變。
- UC-10：Ingress 照原樣轉送 `X-MCP-Profile` 與 PATCH、DELETE（P9 kit 的帳號流程靠它）。
- HAOS 上額外帳號子程式的 `oom_score_adj` 能不能寫成 500（add-on 容器本身是 200）、`nice` 能不能加 5（容器階段只在 docker 驗）。
- HAOS 上 add-on 的 open file 上限（`raise_open_file_limit` 讀到的值）。
- HAOS 上 P9 childkill 的 60 秒等待夠不夠（子程式真的重起要多久；第一次跑時記下 `new pid … after` 與 `child's session after` 的秒數）。
- UC-19 不在 HAOS：第一次升版 PR 的 Store CI。
- 每次升版重驗 UC-08、UC-10、sentinel，並記 Supervisor 版本（`acceptance.md`「每次升版都要重驗」）；本片沒有量，也不得宣稱。

## 17. 驗收條件（計畫 §12.3 HM-16）

| 條件 | 狀態 |
|---|---|
| packaging 測試綠 | 本機 `Ran 259`、`OK (skipped=5)`；CI 待 PR |
| 單帳號探針路徑不變 | 有測試證明（第 3.2 節）：兩邊都剝掉開通的部分後 AST 和 `f4c7718` 相同；`container_acceptance` 逐字相同 |
| 實際容器在 HM-19a 前的 builder 乾跑 | 本片不跑（規則），交 HM-19a（第 13 節） |
| 計畫的「做法」各項 | 容器多帳號階段、`fixture_snapshot` 放寬、P9 kit、hook 草稿與測試、`acceptance.md`、`ha-p9-kit.md`：都做了（第 3 節）。DQ-44 的合成帳號樹待定 |

## 18. 審查意見處理（2026-11-17）

報告：`artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-16.md`（判定「修正後通過」）。修正的腳本、log、變異：同層 `evidence-fix-HM-16/`
（`scripts/mutate_fix.py` 改自審查者的 `mutate.py`；`scripts/x3_real_hm13b.py`；`scripts/pytest-run.sh`、`pytest-broad.sh`）。

| 意見 | 處理 | 證據 |
|---|---|---|
| MF-1 `stage()` 的判定與參數沒有測試守住 | 改（只改測試，`4bbe10a`）：4 個判定各一組反例（斷言訊息、起過的 runtime 都停了）；斷言 `profiles_up` 兩次都等 `[3000, 18000, 18001]`、殺的是 18000、routing 與 child bearer 拿到三個帳號、detect／kept／停機的參數 | 變異 PM10～PM15 全紅 |
| MF-2 P9 `childkill --child-port` 只看一次 | 改（`c3b6f67`）：殺掉後每 0.5 秒看、最多 60 秒到剛好一個新 PID；期間別的 PID 變了就失敗；恢復要子程式自己的 session（閘道自答的結束並計數）；殺之前的 session 也結束。測試加三案（延後出現且閘道先自答要過、一直沒回來 exit 1 且只殺一個、一直是閘道自答 exit 1）。`ha-p9-kit.md` 一起改，註明舊 childkill 的 `recovered in` 是閘道自答的時間 | 舊實作上新測試紅（`red-on-957c639.txt`）；變異 PP1～PP5、PM25、PM28 全紅 |
| MF-3 (a) 漏了 HM-13b 的 S-3 | 改：第 11 節加一列、第 12 節第 1 點寫明步驟（收 stderr、`re-owned N`、守門通知各一行、HM-19a 乾跑前做好） | 本筆記 |
| MF-3 (b) 「只改 `BASE`」做不到 | 改（`7bf8d9b`）：AST 比對兩邊都剝掉開通的部分，`BASE` 原有的不能少，多出來的照種類比（不是寫死 5）；第 12 節第 5 點改寫 | 用 HM-13b 實際檔案模擬（`x3-real-hm13b.txt`）；PM01～PM03、PA1 全紅 |
| SF-1 routing 分不出 B、C 互換 | 採用（`4bbe10a`）：開 session 後直接問每個子程式，只有自己的回 200、別的 404 | 新測試 `test_a_swap_names_…`；變異 PS1～PS3 全紅 |
| SF-2 n8n 的 port 在環境變數 | 照審查的「至少」做：模組說明、P9 註解、`ha-p9-kit.md`、第 14 節交 HM-25；另讓 `stage()` 明確拒絕 n8n。不做 `/proc/<pid>/fd` 方案：要 CAP_SYS_PTRACE，docker 預設不給 | 變異 PN1 紅 |
| SF-3 driver 的組裝沒有測試、刪除用的索引版本沒測到 | 採用（`42dd110`）：三段組裝搬進 `ha_p9_admin.mjs`；假伺服器每次建立或刪除換 ETag、舊版本回 409 `config_conflict`（契約第 3 節的實際碼；審查寫 412）；node 測試斷言順序與參數 | 變異 NM03、NM07、NM08（搬家後的同一處）、NM09、NM10 全紅 |
| SF-4 `acceptance.md` 的 T 表和計畫 §10.4 有落差 | 採用（`6fd1320`）：逐列補標準、寫明每層驗哪幾項、加「Odoo 首發」欄、LOCAL/MOCK 補 packaging unittest；T-15 改寫成容器只驗自己的 port（不在容器加「佔 port → 退避 → 恢復」：要多等看門狗退避，第一次真跑前不加，LOCAL 有完整測試） | — |
| SF-5 P9 probe 照環境代理走 | 採用（`c3b6f67`）：所有模式改用 `ProxyHandler({})` 的 opener；測試在自己的程序裡帶代理環境變數跑 | 舊實作上紅；變異 PX1、PX2 紅 |
| SF-6 hook 只對假 add-on 測過 | 採用（`9fcd04a`）：審查者的實驗收進 `tests/test_upgrade_hooks.py`（4 案約 8 秒） | `t-pytest-targets.txt` |
| SF-7 acceptance-matrix 的登記表沒更新 | 採用（`6fd1320`） | — |
| SF-8 hook 讀索引會跟隨連結 | 採用（`9fcd04a`）：`read_plain`（`O_NOFOLLOW`、只收一般檔、64 KiB）；連結或讀不到記 `unreadable`，verify 判失敗 | 變異 HS1、HS2 紅 |
| SF-9 「hook 不走代理」的測試守不住 | 採用（`9fcd04a`）：每個 hook 在自己的程序裡帶代理環境變數跑 | 變異 HM06 紅（審查時沒抓到） |

審查第 2 節另提：額外帳號在 owned executable 被明確拒絕這件事沒有專門的測試（小事）。不加：額外帳號的測試本來就用 `multi_profile_runtime.py`，
這個拒絕只是防止誤用。
