# HA 多帳號 HM-16 provenance：驗收工具（容器探針多帳號階段與還原樹、P9 kit、Store hook、acceptance.md）（2026-11-16）

## 結論

- **2026-11-19 疊到 HM-27 上（第 21 節）**：merge commit `71e1fca` 把 HM-27 的 `bc4ac31`（#116，已合進 `claude-delivery` `fcd0b22`）
  合進來，#109 疊在 #116 上。文字衝突只在驗收矩陣。合起來才壞的兩處在多帳號階段的布局名稱：`profiles.RECEIPT_ARCHIVE_NAMES` 多一個
  名稱（不改的話每個產品的容器探針 import 就失敗），以及 HM-27 的守門還原時寫的 Origin 政策收據檔（`TOP_NAMES` 要收）。守門沒有
  還原做完時會出現的新 log 行，`check_restore_log` 不用改、`BASE` 照舊。契約、帳本、tool-surface 不用改。
- **2026-11-18 第二輪獨立審查「修正後通過」（必修 0 項、建議 4 項），4 項都改了（第 20 節）**：`acceptance.md` T-21 沒開通的 app
  那一輪照實際行為重寫（只有訊號 1 時才有 `KEPT_NOTICE` 與面板提示，前置只剩預設帳號）；第 16 節補 HM-03a 寫回的局部還原；
  第 13 節與下面「實際容器沒跑」補 0.4.14 起的發版路線；`check_restore_log` 不准有守門的其他行（刻意改單帳號路徑，`BASE` 移到
  `d922d3c`）。帳本、契約、tool-surface 不用改。
- **2026-11-18 和 HM-13b／HM-13c 合併，第 12 節 7 點都做了（第 19 節）**：merge commit 把 HM-13c 的 `c5dd7d3`（含 HM-13b `090081c`、
  `claude-delivery` `53ffe61`）合進來；容器探針的還原階段讀 stderr（`re-owned N` 與守門通知各一行）、多帳號階段改成 HM-13b 之後的行為
  （執行期建 sentinel、還原後每個帳號撤銷、紀錄、舊憑證被拒、sentinel 重建）、布局名稱從 `profiles.py` 取、`acceptance.md` 補 T-21 的
  HAOS 步驟；單帳號路徑的 AST 比對基準移到 `573bb21`（第 1 點刻意改了單帳號路徑，理由與差異見第 19.4 節）。帳本、契約不用改。
- **只改驗收工具與文件，不改執行期**：沒有動 `packages/mcp-admin-core/`、`packages/mcp-admin-ui/src/`、`apps/`、
  `packaging/entrypoint.py`、`management_launcher.py`，也沒有動 `addons/`、版號、CHANGELOG。帳本與 tool-surface 不用改（第 9 節）。
  `MULTI_PROFILE_PRODUCTS` 維持空集合，開關只在測試裡開。
- **容器探針的多帳號階段**（`packaging/container_profiles.py`，新）：只在開通的候選映像、單帳號路徑之後跑。預設加 2 個額外帳號、
  交叉 token 與 session、每個 session 是自己子程式的（直接問每個子程式）、子程式 bearer 交叉、`oom_score_adj`／`nice`、SIGKILL 一個
  子程式其他 PID 不變、30 秒內並行停、sentinel 沒被動過、`/data/mcp` 符合修復規則與項目預算、照 Supervisor 的方式還原整棵多帳號樹後
  修好且兩個訊號都成立（第 3.1 節）。n8n 開通（HM-25）前不收 n8n（第 14 節）。
- **單帳號探針路徑逐位元不變，有測試證明**：`container_probe.py` 只加兩個 import 與三個「開通才走」的 `if`。測試把現在的檔和 `f4c7718`
  的檔**兩邊都剝掉開通的部分**再比 AST：完全相同，而且多出來的剛好是本片的那幾個（第 3.2 節）。HM-13b 合併後只要移 `BASE`（已拿 HM-13b
  的實際檔案模擬過）。`container_acceptance.py` 對沒開通的每個產品，docker 指令與 180 秒逐字照舊。2026-11-18 起 `BASE` 是 `573bb21`：
  HM-13b／HM-13c 審過的探針加上第 12 節第 1 點（還原階段讀 stderr，第 19.4 節）；同日第二輪審查後是 `d922d3c`：再加審查建議的
  一條 log 斷言（第 20 節）。本片刻意改單帳號路徑的只有這兩處。
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
  0.4.14 起發版改走 GitHub-hosted 的 `release.yaml`：HM-19a 的乾跑照它當時的發版路線做；第 12 節第 1 點的單帳號還原 log 檢查，
  任何產品下一次發版時 `release.yaml` 的 candidate job 就會先跑到（第 13、19.7 節）。
- `checks` 秒數：開 PR 後補。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-16（計畫 §12.3：驗收工具；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm16-20261116`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `f4c7718`（HM-00～HM-11、HM-13a、HM-14、HM-17、HM-02、HM-20、#100、HM-31（#105）、HM-09 追補（#106）、HM-11（#107）都已合併）；2026-11-18 用 merge commit 合進 HM-13c `c5dd7d3`（含 HM-13b `090081c`、`claude-delivery` `53ffe61`），第 19 節；2026-11-19 用 merge commit 合進 HM-27 `bc4ac31`（#116），第 21 節 |
| 依據 | 計畫 §11（交付、§11.3 升版逐檔清單）、§12.3 HM-16（含 2026-11-15 HM-20 審查 MF-2 的補充）、§10（T-01～T-29、§10.4、§10.6）、§8.4（還原守門）、C4-SF-5、C4-SF-14；FM-16、63、101、102、107、108、135、147；契約第 2.2、2.3、9 節（#72、#73） |
| 對齊的 PaaS | `woow-mcp-server` 的 `public_probe.py --temp-profile`（repin `d7f58493` 的版本，`artifacts/mcp-security-release-20261112/repin-d7f58493-20261116/public_probe.py`，repo 外）；PaaS CI 映像 smoke（`.gitea/workflows/ci.yml`）只看預設帳號，HA 的多帳號容器階段沒有 PaaS 對應（契約 §9 #73） |
| 獨立審查 | `artifacts/ha-multiprofile-parity-20261114/wave4/review-HM-16.md`（判定「修正後通過」；證據 `wave4/evidence-review-HM-16/`）。修正的腳本、log、變異結果：`wave4/evidence-fix-HM-16/`（repo 外）。第二輪（2026-11-18，合併 HM-13c 之後）：判定「修正後通過」，第 20 節 |
| PaaS 變動 | 第 4 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packaging/container_profiles.py`（新） | 容器探針的多帳號階段（第 3.1 節）：`stage()` 與它的每一段（`tree_snapshot`、`create_profiles`、`detect_as_runtime`、`child_ports`、`listeners`、`profiles_up`、`check_resources`、`kill_one`、`stop_within`、`check_routing`、`ping_child`、`check_child_bearers`）、`private_mock_host`。`stage()` 一開始就拒絕 n8n（第 14 節） |
| `packaging/container_probe.py` | 兩個 import（`features`、`container_profiles`）與三個「開通才走」的 `if`：`mock_bind_host`（私有位址）、`fixture_snapshot`（多帳號快照）、`run()` 最後呼叫 `container_profiles.stage`。其他逐句照 `f4c7718`；2026-11-18 起另有 HM-13b／HM-13c 的改動，與本片兩處刻意改的單帳號路徑（還原階段讀 stderr、`check_restore_log` 不准有守門的其他行；第 19.4、20.3 節） |
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

1. **fixture（停機時）**（2026-11-18 起照 HM-13b、HM-13c 合併後的行為，第 19 節）：
   - 確認單帳號還原階段的 `.restore-detected` 已不在：那次啟動的守門在 F 步最後刪了它（`check_marker_ended`，這裡什麼都不刪）。
   - 以執行期使用者（uid／gid 10001，`subprocess` 的 `user`／`group`／`extra_groups=[]`）跑 `restore_detect.detect(enabled=True)`：
     要是 `consistent`。sentinel 與 record 是執行期自己的：開通產品第一次開機時守門建（在帳號資料出現之前），單帳號還原後守門重建；
     探針不建（合併前探針自己建，要求 `established`）。detect 一定要由 10001 跑（root 碰了再 chown 會改 ctime，之後就被當成還原）。
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
9. **多帳號還原樹**（2026-11-18 起照 DQ-03 (b) A2 與 HM-13b 的守門，第 19 節）：先記下每個 state 與索引（`restore_picture`），用單帳號
   還原階段的 `restore_as_supervisor()` 把整棵樹改成 root（檔案 0644、目錄 0755），再起一次，stderr 收到沒有名字的暫存檔：
   - `check_revoked_restore`：標記不在；每個還原的項目改回 10001 與 0700／0600（單帳號階段留下的 `restore-notice.json` 是唯一被守門刪掉的：
     預設帳號撤銷了，提示不成立）；sentinel、record、`restore-record.json` 是 10001 的 0600 單連結檔，紀錄照 `restore_lock.check_record`、兩個
     訊號都在、每個帳號都是 `revoked`；每個帳號的 token 是 null、歷史多一筆 `revoke`、child token 換新（不等於還原前任何一個、互不相同）、
     其他欄位不變；索引位元不變；
   - 三個子程式都重新起來；`check_refused`：還原前的每個 token 兩種接法都被拒（Bearer 401、密鑰網址 404）、每個子程式拒絕還原前的 child token；
   - 停機後讀 log（`container_probe.check_restore_log`）：entrypoint 的 `re-owned N`（N＝還原的項目加標記）一行、每個帳號（含 `default`）的
     `REVOKED` 一行、`REVOKED_NOTICE` 一行、沒有 `KEPT_NOTICE`，守門沒有別的行（第二輪審查，第 20 節）；detect 是「沒有標記＋`consistent`」
     （sentinel 已重建）；守門留下的樹再過一次 `tree_snapshot`。
   合併前（HM-13a 行為）這一步要求標記留著、每個 state 與 record 位元不變、停機後「有標記＋`mismatch`」。

`stage()` 自己的判定（第 1 步與第 8 步的 `consistent`、第 9 步停機後的「沒有標記＋`consistent`」）和它交給每一步的參數（等哪些 port、殺哪個
帳號、routing、child bearer 與還原後被拒的舊憑證拿到哪些帳號、log 的項目數與撤銷的帳號）都有測試守著（審查 MF-1，第 5、18、19 節）。

最後印一行（沒有秘密）：`PASS multi-profile: default + 2 profiles up in N s; routing, child bearer, resources, SIGKILL, stop in N s; N entries;
restore tree: every profile revoked and its old credentials refused, sentinel rebuilt`。等不到時只寫 port（例如
`children up on [3000] of [3000, 18000, 18001]`）：探針從不印執行期輸出。

時間：單帳號路徑之外多兩次啟動、一次看門狗重起與一次還原後啟動，推估 40～60 秒；開通的候選映像把 `docker run` 上限從 180 改 360 秒
（HM-13a 交辦「180 秒上限要跟著看」）。容器的 open file 上限要 ≥680（Odoo 的 `open_file_budget` 要求；其他產品 530）：
docker 預設的 1024 夠；不夠時額外帳號不服務，第 2 步會失敗在上面那行訊息。

### 3.2 單帳號探針路徑逐位元不變的證明

- `packaging/test_container_probe.py::SingleProfilePathTests`：拿 `git show <BASE>:packaging/container_probe.py`（CI 的 checkout 是完整歷史；
  `BASE` 原本是 `f4c7718`，2026-11-18 起是 `573bb21`，同日第二輪審查後是 `d922d3c`，見下一點、第 19.4 與 20 節）和現在的檔，
  **兩邊都**拿掉開通的部分（`features`、`container_profiles` 兩個 import，以及「條件呼叫 `features.enabled`」的 `if`，不管在哪一層）再比：
  - 剩下的 AST 完全相同（`ast.dump`，同一個直譯器當場算，不怕版本差）；
  - `BASE` 原有的開通部分一個都不能少、不能改（逐個比 `ast.dump`）；
  - 相對 `BASE` 多出來的開通部分要和 `ADDED_BEYOND_BASE` 相同、多出來的分支都要交給 `container_profiles`。`BASE` 是 `f4c7718` 時，多出來的
    剛好是 `import container_profiles`、三個交給 `container_profiles` 的 `if`（`mock_bind_host`、`fixture_snapshot`、`run()`）與 `features`
    import；`573bb21`、`d922d3c` 都已經有它們，所以現在是空的。另一案釘住 `BASE` 自己的開通部分：HM-13b 的 `features` import 與
    `check_restored_start` 的分支（不交給 `container_profiles`）、本片的 import 與三個交給它的分支。
- 證明的鏈（2026-11-18）：`f4c7718`→`c5dd7d3` 是 HM-13b、HM-13c 改的單帳號路徑（`check_restored_start` 改成守門之後的檢查，各自審查過；
  合併 commit `f3b31ce` 當時把 `BASE` 移到 `c5dd7d3`，測試全綠）；`c5dd7d3`→`573bb21` 兩邊都剝掉開通部分後只差第 12 節第 1 點（第 19.4 節
  逐項列出；第二輪審查一起看過，沒有必修）；`573bb21`→`d922d3c` 只差第二輪審查建議第 4 點的三處（第 20.3 節逐項列出）；`d922d3c` 之後
  單帳號路徑沒有再改（現在的測試）。
- 另驗 `run()` 只有一個這種分支、是 `httpx.AsyncClient` 區塊的最後一句、內容是 `await container_profiles.stage(sys.modules[__name__], client)`。
- 審查 MF-3 (b) 之前的寫法只剝現在這份、計數寫死 5，HM-13b（PR #108）自己也加了 `features` import 與還原檢查的開通分支，只移 `BASE` 會紅。
  現在拿 HM-13b 的實際檔案模擬過（GitHub fetch 的 `ebab019`；`git merge-file` 三方合併，`evidence-fix-HM-16/logs/x3-real-hm13b.txt`）：
  `BASE` 換成 HM-13b 的版本、本片的改動接上去並拿掉合併留下的重複 `features` import 後就過；重複的 import 留著會紅（要求拿掉）。
- 之後有片要刻意改單帳號路徑，就把 `BASE` 改成它自己審過的基準 commit，並在筆記寫明理由（本片 2026-11-18 就是這樣移到 `573bb21`，
  第二輪審查後再移到 `d922d3c`）；新基準的開通部分若和 `d922d3c` 的不同，連帶改釘住它們的那一案。只加開通分支、沒改單帳號路徑的片，
  把它列進 `ADDED_BEYOND_BASE`。
  2026-11-18 合併時重複的 `features` import 確實出現，拿掉的是本片那個（第 19.2 節）。
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
| HM-13b 審查 S-3（PR #108 未合併；`wave4/pr-HM-13b.md` 的意見處理表與「後續片」） | 容器探針的還原階段收 stderr，斷言 entrypoint 的 `re-owned N` 與守門通知各一行；要在 HM-19a 前的 builder 乾跑之前做好 | **交 HM-13b 合併後、本片 rebase 時做**（第 12 節第 1 點）：守門通知那一行要 HM-13b 才有；收 stderr 要改單帳號路徑的 `start()`，一起改才只動一次 `BASE`。HM-19a 乾跑前一定要有。**2026-11-18 做了**（合併 HM-13c 之後，`573bb21`、`9f7451e`；第 19.3 節） |
| HM-20 第 13 節（審查 MF-2） | 開通的產品：`container_acceptance` 開一次性 internal bridge、`mock_bind_host` 回私有位址；HM-20 的 tripwire | 做了；tripwire 改成規則本身的斷言（第 3.3 節） |
| HM-20 第 13 節、HM-01 的工具 | `tests/owned_executable.py` 起不了開通的產品（Supervisor 替身 `assert not kwargs`） | **修好**（預設帳號）；額外帳號明確拒絕（第 3.6 節；這個拒絕沒有專門的測試，審查列為小事，額外帳號的測試本來就用 `multi_profile_runtime.py`）。開通 Odoo 時既有 Odoo 測試的 loopback 假後端仍交 HM-19a |
| `decisions.md` DQ-44（負責片含 HM-16 的工具） | 0.5.0 之後的升版比對怎麼驗「有額外帳號」的資料 | **待定，沒做**：hook 草稿不寫合成帳號樹、不要 `ha_core`，只斷言與版本無關的事與索引位元不變；DQ-44 照表在 R2 升版 PR 前定 |
| `acceptance-matrix.md` 檔頭 | 把它寫進 `docs/operations/acceptance.md` 與 P9 kit | 做了（第 3.7 節）；測試檔登記表也更新（審查 SF-7） |
| FM-16 | `packaging/test_entrypoint.py` 補多帳號目錄樹 | 改由容器的多帳號還原階段（真 entrypoint、真映像）與 `tree_snapshot` 的修復規則檢查涵蓋；`packaging/test_entrypoint.py` 不改（CI 那一步不以 root 跑，root 才造得出的情境放 `tests/`，計畫 §10.1） |

## 12. 交 HM-13b／HM-13c 之後補

**2026-11-18 全部做了**（本片合進 HM-13c `c5dd7d3` 之後；不是 rebase，是 merge commit）：每一點怎麼做、在哪個 commit，見第 19.3 節。下面保留
原本的交辦文字。

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
  要先合併 HM-13b、HM-13c；第 12 節的探針改動（含第 1 點的 stderr 斷言）2026-11-18 已做（第 19 節）。docker 的 nofile soft 上限要 ≥680。
  乾跑時最後那行改成 `… restore tree: every profile revoked and its old credentials refused, sentinel rebuilt`（第 3.1 節）。
- **發版路線已換（2026-11-18 第二輪審查建議第 3 點）**：上一點是寫這節時的 builder 路線。0.4.14 起發版走 GitHub-hosted 的 `release.yaml`
  （gate → candidate → publish；candidate job 跑同一個 `supply_chain.py candidate` → `container_acceptance`）：HM-19a 的乾跑照它當時的
  發版路線做，上面的拋棄式 commit、不推 GHCR、要使用者授權照舊。第 12 節第 1 點的單帳號還原 log 檢查不用等 HM-19a：任何產品下一次
  發版時 `release.yaml` 的 candidate job 就會先跑到（第 19.7 節）。
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
  copytree 產生新 inode，要實機看）。局部還原（一般、加密）已由 HM-03a 寫回：兩個訊號都觸發（契約第 10 節 2026-11-18 HM-13b 那列）；
  完整還原仍未測，是 Odoo 發版前的關卡（第二輪審查建議第 2 點）。
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
| packaging 測試綠 | 本機 `Ran 259`、`OK (skipped=5)`；2026-11-18 合併 HM-13c 並補第 12 節後 `Ran 362`、`OK (skipped=5)`（第 19.6 節）；第二輪審查修正後 `Ran 364`、`OK (skipped=5)`（第 20.5 節）；CI 待 PR |
| 單帳號探針路徑不變 | 有測試證明（第 3.2 節）：兩邊都剝掉開通的部分後 AST 和 `f4c7718` 相同；`container_acceptance` 逐字相同。2026-11-18 起基準是 `573bb21`（HM-13b／HM-13c 加第 12 節第 1 點，第 19.4 節），第二輪審查後是 `d922d3c`（再加一條 log 斷言，第 20.3 節） |
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

## 19. 和 HM-13b／HM-13c 合併，補第 12 節（2026-11-18）

### 19.0 結論

- 用 merge commit `f3b31ce` 把 HM-13c 的 `c5dd7d3`（含 HM-13b `090081c` 與 `claude-delivery` `53ffe61`：#117～#121、0.4.14 發版）合進本片；
  不 rebase、不 force push。HM-27（#116）這一步不合（另有人同時在更新）。合併順序照舊：#108 → #112 → #116 → #109。
- 第 12 節 7 點都做了（第 19.3 節）。單帳號路徑的 AST 比對基準移到 `573bb21`（第 19.4 節）。
- 只改驗收工具、測試與文件：`addons/`、版號、CHANGELOG、執行期檔、`tests/conftest.py` 都沒動；帳本與 tool-surface 不用改；契約不改。
- 本機：validate 過；packaging unittest `Ran 362`、`OK (skipped=5)`；node 106 過；pytest 3 檔 165 案，153 過，12 個失敗都是本機環境
  （6 個要 root、6 個 UNIX socket 路徑太長），第 19.6 節。兩個預檢 OK。這一步沒有推送。

### 19.1 commit

| commit | 內容 |
|---|---|
| `f3b31ce` | merge：HM-13c `c5dd7d3` 合進本片（第一個 parent `c7c04f9`）。三處文字衝突、重複的 import、`BASE`→`c5dd7d3`（第 19.2 節） |
| `573bb21` | 第 1 點：還原階段讀 stderr（改單帳號路徑；只有這個 commit 的 `SingleProfilePathTests` 是紅的，照第 3.2 節的規則） |
| `dc98b23` | 第 5 點：`BASE`→`573bb21` |
| `9f7451e` | 第 2、3、4、6 點：多帳號階段 |
| `b4ca6d8` | 第 1 點的交叉驗證：`tests/test_restore_detection.py` 拿真的 entrypoint 與守門的輸出驗 `check_restore_log` |
| 本 commit | 第 7 點與文件：`docs/operations/acceptance.md`、`docs/multi-profile/acceptance-matrix.md`、本筆記 |

相對 `c5dd7d3` 改到 21 個檔：本片原本的 20 個，加 `tests/test_restore_detection.py`（一案多驗 log）。

### 19.2 衝突與處理

| 檔 | 衝突 | 處理 |
|---|---|---|
| `docs/multi-profile/acceptance-matrix.md` | 檔頭狀態那一行 | HM-13c 那句在前，本片那句（含「登記本片的測試檔」）在後；登記表兩邊的列 git 自動合併 |
| `docs/operations/acceptance.md` | 容器探針那段的還原句 | 用 HM-13b 改過的句子（守門處理並刪掉標記），接本片「開通的候選映像另跑多帳號階段」；HM-13c 的還原提示與第 1 點在本 commit 補 |
| `packaging/test_container_probe.py` | 模組說明 | 兩邊的描述都留 |
| `packaging/container_probe.py`（git 自動合併，但合出兩個 `from mcp_admin_core import features`） | 不是文字衝突 | 拿掉本片那個、留 HM-13b 的（第 12 節第 5 點）。`BASE` 用 `c5dd7d3` 跑 AST 比對時，重複的那個被算成多出來的開通部分而紅；拿掉後綠 |
| `packaging/test_container_probe.py` 的 `BASE` | 不是文字衝突：HM-13b 改了單帳號路徑的 `check_restored_start`，`BASE`＝`f4c7718` 一定紅 | 合併 commit 裡移到 `c5dd7d3`（合併後的探針＝`c5dd7d3` 的探針加本片的開通部分），packaging unittest `Ran 341`、`OK (skipped=5)` |

- 契約、帳本：本片沒改，git 不用合；`runtime-patches.json` 等就是 HM-13c 的版本。
- 合併後只有在容器裡才會出錯、單元測試抓不到的（第 12 節本來就列了）：`end_restore_marker` 要求標記還在、第 1 步要求 `established`、第 9 步要求
  標記留著與位元不變、`TOP_NAMES` 沒有 `restore-notice.json`（開通的候選映像在單帳號路徑的 `fixture_snapshot` 就會失敗）。都在 `9f7451e` 改了。

### 19.3 第 12 節各點

| 點 | 做了什麼 | commit |
|---|---|---|
| 1 還原階段收 stderr | `container_probe.start(log=None)`：沒給 log 照舊全丟；還原後那次啟動把 stderr 交給 `tempfile.TemporaryFile()`（容器的 `/tmp`，沒有名字、關掉就不見，不印）。`check_restore_log(log, entries, revoked=())` 停機後讀：entrypoint 的 `bootstrap: re-owned N restored entries in /data/mcp` 剛好一行（N＝還原的項目加標記，`entrypoint._repair_restored` 的計數）；守門通知剛好一行、另一種一行都沒有（單帳號：`restore_lock.KEPT_NOTICE`；多帳號：`REVOKED_NOTICE`）；`REVOKED` 每個撤銷的帳號剛好一行、沒有別的。字串直接取 `restore_lock` 的。entrypoint 那行在 `entrypoint.py` 沒有常數（它是執行期檔，本片不改），探針留一份 `REOWNED`：packaging 測試比對 `entrypoint.py` 的原始碼，`tests/test_restore_detection.py` 拿真的 entrypoint 輸出驗。和原本交辦文字不同的一處：多帳號還原時 `REVOKED` 不只額外帳號，預設帳號也有一行（`restore guard [profile=default]: …`：守門連預設帳號一起撤銷也記；對真的守門跑的測試證實），探針照實際要求 | `573bb21`、`9f7451e`、`b4ca6d8` |
| 2 標記 | `end_restore_marker` 改成 `check_marker_ended`：只確認單帳號階段的標記已不在，什麼都不刪 | `9f7451e` |
| 3 sentinel | 第 1 步 detect 期望 `consistent`（執行期建、單帳號還原後守門重建），探針不再建；`StageTests` 改成「執行期沒建（含探針的 detect 自己建出 `established`）就在任何啟動前失敗」 | `9f7451e` |
| 4 多帳號還原（DQ-03 (b) A2） | `check_revoked_restore`：標記不在；每個還原的項目修好（單帳號階段的 `restore-notice.json` 是唯一被守門刪掉的）；sentinel、record、`restore-record.json` 是 10001 的 0600 單連結檔；紀錄照 `restore_lock.check_record` 的格式、兩個訊號、每個帳號 `revoked`；每個帳號 token 是 null、歷史多一筆 `revoke`、child token 換新（不等於還原前任何一個、互不相同）、其他欄位不變；索引位元不變。三個子程式都重新起來。`check_refused`：還原前的 token 兩種接法都被拒（Bearer 401、密鑰網址 404；開到的 session 照樣結束），每個子程式拒絕自己還原前的 child token。停機後讀 log（第 1 點，多帳號版）；detect 是「沒有標記＋`consistent`」（sentinel 已重建）；守門留下的樹再過一次 `tree_snapshot`。`kept_bytes` 換成 `restore_picture` | `9f7451e` |
| 5 AST 比對 | `BASE`→`573bb21`（理由第 19.4 節）；合併留下的重複 `features` import 拿掉本片那個 | `f3b31ce`、`dc98b23` |
| 6 布局名稱 | `TOP_NAMES` 加 `profiles.RESTORE_NOTICE_NAME` 與索引旁封存的收據，`PROFILE_NAMES` 加每個帳號目錄（與頂層）封存的收據；兩個都從 `profiles.RECEIPT_ARCHIVE_NAMES` 拆出來，`JOURNAL` 改由 `operations.journal_path` 算，都不另寫字串。測試釘住守門自己的每個名稱（`profiles.ASIDE_NAMES`）都在 `TOP_NAMES` 裡。守門把目錄移到旁邊時用的名稱（`<名稱>.quarantine-<UTC>`）不收：探針的 fixture 不會有，出現就是錯 | `9f7451e` |
| 7 T-21 | `acceptance.md`：T-21 列的容器欄寫實際驗的項目，HA 欄連到新的「T-21 在 HAOS 的步驟」（full、partial、加密各一輪：兩種 log 行、兩個訊號怎麼看、核對卡、獨立驗證、舊收據 410、核對後才重發、重開不再處理、沒開通的 app 一輪）；容器段落與多帳號段落照合併後的行為改寫；狀態一行照契約第 10 節記的 HM-03a 結果更新。P9 kit 不加模式：HM-13c 沒加，而且權杖全撤銷後 `--cross` 沒有可測的帳號（步驟裡寫明這時不要跑）。hook 不受 HM-13c 影響：只看索引、`profiles`、標記三個名稱，不看 bootstrap，升級也不會產生提示檔 | 本 commit |

### 19.4 新的 `BASE`：`573bb21`

- 不用 `c5dd7d3`：第 1 點刻意改了單帳號路徑（每個候選映像都跑的還原階段），`c5dd7d3` 沒有它，比對一定紅。
- `573bb21`＝`c5dd7d3` 的探針（HM-13b、HM-13c 的改動各自審查過）＋本片的開通部分（第一輪審查過）＋第 1 點。兩邊都剝掉開通部分後，
  `c5dd7d3`→`573bb21` 的差異只有下面這些（剝完用 `ast.unparse` 逐行比）：
  1. `import tempfile`
  2. `from mcp_admin_core import restore_lock`
  3. `REOWNED = 'bootstrap: re-owned %d restored entries in /data/mcp'`
  4. `start()` 改成 `start(log=None)`：加說明，`stderr=subprocess.DEVNULL if log is None else log`
  5. `check_restored_start` 說明的最後一句
  6. 新的 `check_restore_log(log, entries, revoked=())`
  7. `restored_start`：加說明；`with tempfile.TemporaryFile() as log:` 裡 `start(log)`，停機後 `check_restore_log(log, len(restored) + 1)`
- `573bb21` 單獨看 `SingleProfilePathTests` 是紅的（那時 `BASE` 還是 `c5dd7d3`）：刻意改單帳號路徑就要把 `BASE` 移到那個 commit，commit 不能
  指向自己，所以下一個 commit `dc98b23` 才移；之後每個 commit 都綠。
- 「審過」：第 1 點由本片下一輪獨立審查一起看；在那之前，上面 7 項就是單帳號路徑相對 HM-13b／HM-13c 的全部差異。
- 測試跟著改：「多出來的開通部分」改成相對 `BASE` 列（`ADDED_BEYOND_BASE`，現在是空的）；另一案釘住 `BASE` 自己的開通部分（HM-13b 的
  `features` import 與 `check_restored_start` 的分支、本片的 `container_profiles` import 與三個交給它的分支）。第 3.2 節已照新基準改寫。

### 19.5 測試與變異

- `packaging/test_container_probe.py`：21 → 31 案。`StartTests`（stderr 只在給 log 時交出去）、`RestoreLogTests` 6 案（單帳號與多帳號各自的
  正例與 8 種反例、訊息不帶 log 內容、`REOWNED` 和 `entrypoint.py` 的原始碼相同）、`GuardLogTests`（真的 `restore_lock.guard`，沒開通與開通
  但沒有帳號資料兩種，寫出的 log 照樣過）、還原階段多一案（log 不對時停機後失敗；檢查失敗時不讀 log；讀完就關）、AST 比對多一案（`BASE`
  自己的開通部分）。
- `packaging/test_container_profiles.py`：35 → 46 案。布局名稱 2 案、`RevokedRestoreTests` 3 案（真的守門：開通的預設帳號先單帳號還原一次、
  建兩個帳號、再還原；守門跑完第 9 步的檢查都過、log 照樣過、detect 是 `consistent`、`tree_snapshot` 過；守門沒跑就失敗；守門不會留下的 14 種
  改法各自失敗、訊息不帶 token）、`RevokedStateTests` 2 案、`RefusedTests` 2 案（用假閘道與假子程式：還原前的 token 只當 Bearer、只在密鑰網址、
  兩種都被服務，或子程式收舊的 child token，各自失敗、開到的 session 都結束）、`StageTests` 照新步驟改寫並多兩案。
- `tests/test_restore_detection.py`：「容器探針還原階段對上 entrypoint」那案多驗 log（真的 entrypoint 輸出＋真的守門 log）。
- 變異 41 個（在本 clone 每次換一段字、跑對應測試、逐位元還原並核對 SHA-256；腳本在 repo 外，跑完刪掉）：
  - 探針 11 個全紅：單帳號路徑多一步、少檢查 log、log 檢查藏到「沒開通才跑」、不交給 `container_profiles` 的開通分支、stderr 照丟、`re-owned`
    不比數字、通知兩次也過、另一種通知也過、`REVOKED` 不查、數字少算標記、停機前就讀 log。
  - 多帳號階段 29 個全紅：探針又自己刪標記、又自己建 sentinel、還原後要求兩個訊號還在（HM-13a 行為）、提示可以留著、任何還原的項目可以不見、
    紀錄的列／訊號／格式不查、修復不查、token 沒撤銷、child token 沒換、新 child token 重複、歷史不查、其他欄位不比、索引不比、舊 Bearer 被服務、
    舊密鑰網址被服務、舊 child token 被服務、開到的 session 不結束、不試舊憑證、log 當成沒撤銷、還原後的啟動不給 log、停機前讀 log、守門留下的樹
    不檢查、還原後的檔案不檢查、少了提示檔名、少了帳號目錄的封存收據名、索引旁的封存收據名也收在帳號目錄、還原前的狀態在還原後才記。
    其中「舊 Bearer 被服務」第一次沒抓到（`RefusedTests` 的假閘道兩種接法一起服務），補「只有 Bearer 被服務」一案後紅。
  - `tests/test_restore_detection.py` 1 個：探針的 `REOWNED` 改一個字，紅。

### 19.6 本機檢查（一般使用者；這一輪的 TMPDIR 規定用 scratch 目錄、不用 `/tmp`，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（有 PyYAML 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv，`python -m unittest discover -s packaging -p 'test_*.py'`） | `f3b31ce`：`Ran 341`、`OK (skipped=5)`；`573bb21`：`Ran 350`、1 failure（`SingleProfilePathTests`，照設計）；`dc98b23`：`Ran 351`、`OK (skipped=5)`；`9f7451e` 起：`Ran 362`、`OK (skipped=5)`，約 28 秒（`test_container_profiles` 46 案約 6 秒、`test_container_probe` 31 案約 3 秒）。5 個 skip 是既有的 `skipUnless(root)` |
| node（`packages/mcp-admin-ui`，`node --test tests/*.test.mjs`） | 106 過、0 失敗；`node --check` driver、admin 過（合併帶進 HM-12 面板與 HM-13c 改的 `api.js` 後，P9 的組裝照樣過） |
| pytest（`.venv/bin/python -m pytest -q -p no:cacheprovider`） | `tests/test_restore_detection.py`、`tests/test_upgrade_hooks.py`、`tests/test_owned_executable.py`：165 案，153 過，12 失敗。要 root 的 6 個：`test_restore_detection.py` 的 5 個 `test_root_*`、`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`。`AF_UNIX path too long` 的 6 個：`test_upgrade_hooks.py` 對真 runtime 的 4 案、`test_owned_executable.py` 的 `test_ipc_rejects_other_own_process_before_tcp` 與開通產品經 owned executable 那案（`tests/owned_executable.py` 的 UNIX socket 放在 pytest 的暫存目錄，這一輪的 scratch 路徑太長，超過 108 位元組；前幾輪用短的 `/tmp/ha-mp-XXXXXX` 都過，這一輪不准用 `/tmp`，交 CI）。`b4ca6d8` 之後 `test_restore_detection.py` 139 案：134 過、5 個 `test_root_*` |
| 秘密預檢（`scripts/secret_precheck.py --tools …/scan0414/tools`） | gitleaks 8.28.0（釘選、驗過）；本 commit 之前跑：`53ffe61..b4ca6d8` 86 個 commit，**OK，0 命中**。本 commit 只加文件，提交後再跑一次（結果寫在回報） |
| 帳本預檢（`scripts/ledger_precheck.py`） | 三本帳本 0 drift、0 missing；相對 `c5dd7d3` 沒有列管檔、帳本沒改、沒有新的執行期檔：**OK** |

### 19.7 只在 CI 跑的、本機沒跑的

- 要 root 的（同前幾輪）與 `AF_UNIX` 的 6 個（這一輪，第 19.6 節）；Playwright 瀏覽器測試；`packaging/unit.sh`（root、0 skip）。
- 實際容器不在 PR 的 CI：`ci.yaml` 的 `builder-admission` 依設計拒絕 PR 的映像執行，`images` 不跑。第 1 點的單帳號還原 log 檢查第一次真跑是
  **任何產品下一次發版**時 `release.yaml` 的 candidate job（GitHub-hosted）；多帳號階段第一次是 HM-19a 的乾跑（開通的拋棄式映像）。在那之前只有
  上面這些單元測試（含對真的 entrypoint 與真的守門跑的那幾案）。

### 19.8 契約、帳本、tool-surface

- 契約不改：本輪改的是驗收工具，沒有新的 PaaS 可觀察差異；HM-13b 的 #118～#121、HM-13c 的 #122、#123 照舊，本片沒有第 9 節的列，也不加變更紀錄。
- 帳本：沒有改到列管檔（`container_probe.py`、`container_profiles.py` 只在 builder 跑容器驗收時掛進候選容器，不進映像，第 9 節）；`apps/runtime/*.py`、
  `apps/*/launch.py` 沒改，tool-surface 不用重產。

## 20. 第二輪審查意見處理（2026-11-18）

### 20.0 結論

- 第二輪獨立審查看的是合併 HM-13c、補完第 12 節之後的本片（審查時 HEAD 是 `f5c1cf8`）：判定「修正後通過」，必修 0 項、建議 4 項。
  報告由主對話的工作流程交來，下面逐項記要點與處理。
- 4 項都採用（第 20.1 節）。第 4 點刻意改單帳號路徑（`check_restore_log` 多一條斷言），`BASE` 從 `573bb21` 移到 `d922d3c`（第 20.3 節）；
  其他 3 點只改文件。
- 只改驗收工具、測試與文件：`addons/`、版號、CHANGELOG、執行期檔、`tests/conftest.py` 都沒動；帳本、契約、tool-surface 不用改（第 20.7 節）。
- 本機（第 20.5 節）：validate 過；packaging unittest `Ran 364`、`OK (skipped=5)`；pytest `tests/test_restore_detection.py` 139 案，134 過，
  5 個要 root 的 `test_root_*` 失敗（同前幾輪）。兩個預檢 OK。
- `claude-delivery` 已是 `e108a12`（#108、#112 合併）：樹和本片合進來的 `c5dd7d3` 相同，這一輪不用再合。

### 20.1 意見與處理

| 建議 | 審查的意見 | 處理 | commit |
|---|---|---|---|
| 1 `acceptance.md`「T-21 在 HAOS 的步驟」第 6 點（沒開通的 app） | 寫成「還原後 log 只有 `KEPT_NOTICE` 一行（有訊號 1 時另有 `re-owned` 一行）」，像是沒有訊號 1 也會有 `KEPT_NOTICE`。沒開通、沒有帳號資料時 `restore_detect.detect` 不看 sentinel，`restore_lock.guard` 只在標記存在時才記 `KEPT_NOTICE`、存提示檔。「照步驟 1～4 做」又帶進開通 app 才有的前置（2 個額外帳號、P9 `--cross`） | 採用，第 6 點改寫成四小點：前置只有預設帳號（不加帳號、不跑 `--cross`，測試用戶端接預設帳號）；備份後重新產生一次權杖，再還原；不查舊收據（沒開通又沒有帳號資料時守門不封存收據）；有 `re-owned` 那行（訊號 1）時才有 `KEPT_NOTICE` 一行與面板提示，沒有那行時什麼都沒有，照實記下。另寫明 entrypoint 記了「標記存不成」的 WARNING 時也沒有（它照樣修擁有者、記 `re-owned`）。對過的程式：`restore_detect.detect`（`if not (enabled or profile_data)`）、`restore_lock.guard` 的第一段（沒開通又沒有帳號資料：只在 `detection.restored` 時記通知、存提示、刪標記）、`packaging/entrypoint.py` 的 `prepare_data` | 本 commit |
| 2 本筆記第 16 節 UC-08 | 仍把局部還原列為完全未確認；同一個 commit 的 `acceptance.md` 已照契約第 10 節 2026-11-18 HM-13b 那列，寫成 HM-03a 已寫回局部還原 | 採用：第 16 節補一句（一般與加密的局部還原兩個訊號都觸發；完整還原未測，是 Odoo 發版前的關卡）。HM-03a 的其他結果（UC-10、sentinel 在重啟等之後不變）還沒寫回 repo 的文件，本片照契約只寫這一項 | 本 commit |
| 3 本筆記第 13 節與結論「實際容器沒跑」 | 仍寫 builder 乾跑（`supply_chain.py candidate` → `container_acceptance`）；第 19.7 節卻寫第 1 點第一次真跑在 `release.yaml` 的 candidate job（GitHub-hosted），前後不一致 | 採用：兩處各補一句（0.4.14 起發版走 GitHub-hosted 的 `release.yaml`；HM-19a 的乾跑照它當時的發版路線做；第 1 點的單帳號 log 檢查會在任何產品下一次發版的 candidate job 先跑到）。原本的文字留著，那是寫的時候的路線。已對過 `release.yaml` 的 candidate job 跑 `supply_chain.py candidate`（它呼叫 `container_acceptance`） | 本 commit |
| 4 `packaging/container_probe.py` 的 `check_restore_log`（加強，不是缺陷） | 只確認預期的行各一行，沒拒絕守門的其他行（`NOT_REVOKED`、`QUARANTINED`、`SET_ASIDE`、`NOTICE_NOT_REMOVED`、`MARKER_LEFT`、`UNFINISHED`、`DORMANT_NOTICE` 等）。這些情況多半會被別的檢查抓到，但 HM-13b S-3 要的是 log 完整 | 採用：以 `GUARD`（`'restore guard'`）開頭的每一行，都要是這次該有的通知（`KEPT_NOTICE` 或 `REVOKED_NOTICE`）或撤銷的帳號各自的 `REVOKED`，否則失敗，訊息固定 `another line of the boot guard`。`RestoreLogTests` 加審查要的反例（`SET_ASIDE` 等 11 種）與一案釘住 `GUARD` 認得守門的每一行（第 20.4 節）。這是刻意改單帳號路徑，`BASE` 移到 `d922d3c`（第 20.3 節） | `d922d3c`、`b696679` |

### 20.2 commit

| commit | 內容 |
|---|---|
| `d922d3c` | 建議第 4 點：`check_restore_log` 的新斷言與 `GUARD`、`RestoreLogTests` 兩案、`container_profiles` 模組說明第 9 步補一句。照第 3.2 節的規則，`SingleProfilePathTests` 只在這個 commit 是紅的（`BASE` 還是 `573bb21`） |
| `b696679` | `BASE`→`d922d3c`（`packaging/test_container_probe.py` 的常數與說明） |
| 本 commit | 建議第 1～3 點與文件：`docs/operations/acceptance.md`（第 6 點改寫；容器還原檢查的三處加「守門沒有別的行」）、`docs/multi-profile/acceptance-matrix.md`（`test_container_probe.py` 那列）、本筆記 |

相對 `c5dd7d3` 改到的檔仍是 21 個：這一輪的 6 個檔都已在裡面。

### 20.3 新的 `BASE`：`d922d3c`

- 為什麼移：建議第 4 點改的是 `check_restore_log`，每個候選映像都跑的單帳號還原階段（`restored_start`）也呼叫它，所以是刻意改單帳號路徑；
  不移 `BASE`，比對一定紅。
- `573bb21`→`d922d3c` 兩邊都剝掉開通部分後（`ast.unparse` 逐行比），差異只有下面三處：
  1. `GUARD = 'restore guard'`（守門每一行的開頭；說明寫明由測試逐一核對）
  2. `check_restore_log` 的說明多一句：守門沒有別的行（移到旁邊、隔離、撤銷失敗、標記留著、沒做完……）
  3. 最後一條斷言：`assert all(line in (notice, *told) for line in lines if line.startswith(GUARD)), 'another line of the boot guard'`
- 兩邊的開通部分相同（HM-13b 的 `features` import 與 `check_restored_start` 的分支、本片的 `container_profiles` import 與三個交給它的分支）：
  `ADDED_BEYOND_BASE` 仍是空的，釘住 `BASE` 開通部分的那一案不用改。
- 「審過」：這三處照第二輪審查建議的寫法做；它們本身由下一次審查或使用者合併前的覆核一起看。在那之前，上面三處就是單帳號路徑相對
  `573bb21` 的全部差異。

### 20.4 測試與變異

- `packaging/test_container_probe.py`：31 → 33 案，新的兩案都在 `RestoreLogTests`：
  - 守門的其他 11 種行（`SET_ASIDE`、`SET_ASIDE_IN_PROFILE`、`QUARANTINED`、`NOT_REVOKED`、`NOT_ARCHIVED`、`NOTICE_NOT_REMOVED`、`MARKER_LEFT`、
    `UNFINISHED`、`DORMANT_NOTICE`、`REVOKE_ALL_NOTICE`、`RECORD_KEPT`）各多一行，單帳號與多帳號的 log 都失敗，訊息固定、不帶 log 的內容。
  - `restore_lock` 記的每一行（logger 呼叫的第一個參數、`_Sweep._fail` 的第三個；條件式兩邊都算）都是它的常數，共 18 個，每個都以 `GUARD`
    開頭：守門以後加新行也認得，`GUARD` 不只是另抄的一份字串。
- 新斷言對真守門照樣過：`GuardLogTests`（沒開通、開通但沒有帳號資料）、`test_container_profiles.RevokedRestoreTests`（多帳號還原）、
  `tests/test_restore_detection.py::test_the_container_probes_restore_stage_meets_the_entrypoint`（真的 entrypoint 與守門）。
- 變異 7 個全紅（在本 clone 每次換一段字、跑對應測試、逐位元還原並核對 SHA-256；腳本在 scratch 目錄，跑完刪掉）：
  - `RestoreLogTests` 5 個：拿掉新斷言、`GUARD` 只認冒號開頭的行、只認帳號開頭（`[profile=`）的行、任何帳號行都放過、結尾是括號的行放過。
  - `SingleProfilePathTests` 2 個（`BASE`＝`d922d3c`）：拿掉新斷言（單帳號路徑回到 `573bb21`）、把它藏進「沒開通才跑」的分支。

### 20.5 本機檢查（一般使用者；TMPDIR 用 scratch 目錄、不用 `/tmp`，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（有 PyYAML 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv，`python -m unittest discover -s packaging -p 'test_*.py'`） | 改之前（`f5c1cf8`）：`Ran 362`、`OK (skipped=5)`；`d922d3c`：`Ran 364`、1 failure（`SingleProfilePathTests`，照設計）；`b696679` 起：`Ran 364`、`OK (skipped=5)`，約 28 秒。5 個 skip 是既有的 `skipUnless(root)` |
| pytest（`.venv/bin/python -m pytest -q -p no:cacheprovider`；共用鎖 22:35:35 排隊、22:36:27 拿到、22:36:30 放掉，台北時間） | `tests/test_restore_detection.py`（涵蓋 `container_probe` 的 pytest 檔只有它）：139 案，134 過，5 個 `test_root_*` 要 root 而失敗（同前幾輪） |
| 秘密預檢（`scripts/secret_precheck.py --tools …/scan0414/tools`） | gitleaks 8.28.0（釘選、驗過）；本 commit 之前跑：`c5dd7d3..b696679` 31 個 commit，**OK，0 命中**。本 commit 只加文件，提交後再跑一次（結果寫在回報） |
| 帳本預檢（`scripts/ledger_precheck.py`） | 三本帳本 0 drift、0 missing；相對 `c5dd7d3` 21 個檔，沒有列管檔、帳本沒改、沒有新的執行期檔：**OK** |
| node | 沒跑：這一輪沒有改 JS |

### 20.6 只在 CI 跑的、本機沒跑的

- 要 root 的：`tests/test_restore_detection.py` 的 5 個 `test_root_*`（CI 以 root 跑 pytest）；packaging 的 5 個 `skipUnless(root)`。
- 這一輪沒跑 `tests/test_upgrade_hooks.py`、`tests/test_owned_executable.py`（沒改到它們涵蓋的東西）；`AF_UNIX` 路徑太長的那 6 個仍交 CI
  （第 19.6 節）。Playwright 瀏覽器測試、`packaging/unit.sh`（root、0 skip）也是 CI 跑。
- 實際容器同第 19.7 節：新斷言第一次真跑是任何產品下一次發版時 `release.yaml` 的 candidate job（單帳號還原階段）；多帳號版第一次是
  HM-19a 的乾跑。

### 20.7 契約、帳本、tool-surface

- 契約不改：改的是驗收工具的檢查與文件，沒有新的 PaaS 可觀察差異。
- 帳本：`runtime-patches.json` 在 `packaging/` 只列管 `entrypoint.py`；這一輪改的 `container_probe.py`、`container_profiles.py`、
  `test_container_probe.py` 都不列管（只在容器驗收時掛進候選容器，不進映像，第 9 節），不用重算。`apps/runtime/*.py`、`apps/*/launch.py`
  沒改，tool-surface 不用重產。

## 21. 疊到 HM-27 上（2026-11-19）

### 21.0 結論

- 用 merge commit `71e1fca` 把 HM-27 的 `bc4ac31` 合進本片（第一個 parent `ffbde21`），#109 疊在 #116 上；不 rebase、不 force push。
  #116 已合進 `claude-delivery`（`fcd0b22`，樹和 `bc4ac31` 相同），不用再合 `claude-delivery`。合併基準 `c5dd7d3`（兩邊都已含 HM-13c）。
- 文字衝突只有驗收矩陣（第 21.2 節）。合起來才壞的兩處在多帳號階段的布局名稱，在 merge commit 裡修；測試在下一個 commit 補（第 21.3 節）。
- 只改驗收工具、測試與文件：`container_probe.py` 沒動（單帳號路徑的 `BASE` 照舊 `d922d3c`）；`addons/`、版號、CHANGELOG、執行期檔、
  `tests/conftest.py` 都沒動；契約、帳本、tool-surface 不用改（第 21.5 節）。

### 21.1 commit

| commit | 內容 |
|---|---|
| `71e1fca` | merge：驗收矩陣的衝突；`container_profiles.py` 的三個名稱與 `TOP_NAMES`；`test_every_name_of_the_boot_guard_is_the_layout_s` 改成比三個名稱 |
| `41044e6` | 測試：Origin 政策的三個名稱、守門封存收據失敗的兩行、真的守門封存 Origin 收據的還原 |
| 本 commit | 文件：驗收矩陣的檔頭狀態與兩個 packaging 測試檔的登記列、本筆記 |

### 21.2 衝突與處理

`docs/multi-profile/acceptance-matrix.md` 三處，兩邊的內容都留：

| 衝突 | 處理 |
|---|---|
| 檔頭狀態 | 照前幾次合併：HM-13c 那句在前，HM-27 那句（含合併 HM-13c 之後的改動）其次，本片那句在後，最後是 HM-19b；本 commit 在本片那句補「合併 HM-27 之後」的改動 |
| T-21 列 | 期望值用 HM-27 的（Origin 政策旁的收據也 410、政策檔照還原的原樣）；測試欄本片的兩個 packaging 測試接在 HM-13c 的之後、HM-27 的「Origin 政策：」之前；負責片兩邊合起來（HM-16 照編號在 HM-13c 與 HM-19b 之間） |
| 登記表相鄰的兩列 | `tests/test_restore_detection.py` 用本片的（容器探針讀的 log）、`tests/test_restore_lock.py` 用 HM-27 的（Origin 政策）。merge commit 的說明寫成「git 自動合併」，其實這兩列是第三個衝突區塊，處理就是這樣；登記表其他的列 git 自動合併 |

- 契約第 9 節：本片沒有列，不用改號：HM-13b #118～#121、HM-13c #122、#123、HM-27 #124～#128 照舊；本片的文件沒有引用 HM-27 的列號。

### 21.3 探針與測試

1. **`profiles.RECEIPT_ARCHIVE_NAMES` 變成三個名稱**（HM-27 加 Origin 政策旁封存的收據）：`container_profiles.py` 原本拆成兩個名稱，
   import 時就 `ValueError`；`container_probe.py` 一開頭就 import 它，所以**每個產品**的容器探針（不只開通的）都會在 import 時失敗，
   packaging unittest 兩個測試模組載入失敗（`Ran 287`、`errors=2`）。改成拆三個（`ORIGIN_JOURNAL_ARCHIVE`）。
2. **`TOP_NAMES` 收 HM-27 的三個名稱**（都從 `profiles.py` 取：`ORIGIN_POLICY_NAME`、`ORIGIN_POLICY_OPERATIONS_NAME`、封存的收據）：
   開通的產品每次還原，守門都把 Origin 政策旁的收據封存成 `.restored`、寫一份新的（備份裡沒有也寫）；面板存的政策檔照還原的原樣。
   沒收時，開通的候選映像在單帳號路徑還原後的 `fixture_snapshot` 就失敗（`not a name of the layout`）。三個都只在 `/data/mcp` 頂層，
   不進 `PROFILE_NAMES`（政策是全 add-on 一份）。探針自己從來不存政策（不送管理請求），政策檔名是為了「備份前面板存過政策」的樹。
   HM-27 筆記第 13 節說探針「不用改」，說的是只檢查一定要有的檔的還原檢查（`check_restored_start`）；布局快照（`tree_snapshot`）只收
   布局裡的名稱，所以要加。
3. **還原 log**：HM-27 的守門只多一行 `ORIGIN_NOT_ARCHIVED`，和 `INDEX_NOT_ARCHIVED` 一樣只在封存失敗時記，守門接著停下（`UNFINISHED`、
   `ConfigError`，什麼都不服務）；還原做完時沒有新行。所以 `check_restore_log` 不用改，照舊拒絕這兩行。合併後兩行都改由
   `_Sweep.archive` 的參數 `line` 傳給 `_fail`（預設 `INDEX_NOT_ARCHIVED`）：「守門的每一行都以 `GUARD` 開頭」那案原本只看 logger 與
   `_fail` 的參數，合併後 `INDEX_NOT_ARCHIVED` 悄悄掉出檢查（18 個常數剩 17 個），改成也看 `archive` 給的 `line` 與預設值（19 個）。
4. **測試**（`41044e6`）：`test_container_profiles`：三個名稱是頂層的檔（放進帳號目錄、做成目錄都拒絕；收據檔名和
   `operations.journal_path` 算的一樣）；`RevokedRestoreTests`（真的守門）留下的樹有 Origin 政策旁的新收據檔、沒有政策檔。
   `test_container_probe`：「守門的其他行都失敗」加 `INDEX_NOT_ARCHIVED`、`ORIGIN_NOT_ARCHIVED`；`GuardLogTests` 多一案：備份前存過
   Origin 政策、收據有一筆存檔，還原後真的守門不動政策、把收據封存，log 只有通知一行，`check_restore_log` 過，`tree_snapshot` 收下。
   packaging unittest 364 → 366 案。
5. **變異 9 個全紅**（scratch 目錄的腳本，每次換一段字、跑對應測試、逐位元還原並核對 SHA-256，跑完刪掉）：三個名稱各少一個、Origin
   的名稱也收在帳號目錄、`check_restore_log` 放過含 `Origin` 或 `index` 的守門行（各一）、AST 不看 `archive`、守門封存 Origin 收據後
   多記一行、守門不封存 Origin 收據（後兩個暫改執行期的 `restore_lock.py`，已還原）。放過 `index` 那行的變異，`RestoreLogTests` 要有
   這次加進清單的 `INDEX_NOT_ARCHIVED` 才會紅（單帳號路徑的 AST 比對對 `check_restore_log` 的任何改動也會紅）。

### 21.4 本機檢查（一般使用者；TMPDIR 用 scratch 目錄、不用 `/tmp`，跑完用完整路徑刪掉；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（有 PyYAML 的 venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| packaging unittest（同一個 venv，`python -m unittest discover -s packaging -p 'test_*.py'`） | `71e1fca`：`Ran 364`、`OK (skipped=5)`；`41044e6`：`Ran 366`、`OK (skipped=5)`，約 28 秒。5 個 skip 是既有的 `skipUnless(root)` |
| node（`packages/mcp-admin-ui`，`node --test tests/*.test.mjs`，node 26.12.1） | 118 過、0 失敗（多的是 HM-27 的 `origin-policy.test.mjs`；`p9-admin.test.mjs` 對 HM-27 改過的 `api.js` 照樣過）；`node --check` driver、admin 過 |
| pytest（`.venv/bin/python -m pytest -q -p no:cacheprovider`；共用鎖 05:49:04 排隊就拿到、05:51:39 放掉，台北時間） | 21 檔 984 案：971 過、13 失敗，都是本機環境（第 21.5 節）。檔：`test_restore_lock`、`test_restore_detection`、`test_upgrade_hooks`、`test_owned_executable`、`test_origin_policy`、`test_profile_admin_api`、`test_profile_runtime`、`test_panel_profile_api_shapes`、`test_admin_pipeline_matrix`、`test_request_budget_gateway`、`test_restore_review`、`test_dormant_profiles`、`test_revoke_all`、`test_profile_index`、`test_profile_routing`、`test_profile_consistency`、`test_profile_store`、`test_tool_inventory`、`test_ledger_precheck`、`test_upgrade_zero_rewrite`、`test_single_profile_golden` |
| 秘密預檢（`scripts/secret_precheck.py --tools …/scan0414/tools`） | gitleaks 8.28.0（釘選、驗過）；本 commit 之前跑：`bc4ac31..41044e6` 34 個 commit，**OK，0 命中**。本 commit 只改文件，提交後再跑一次（結果寫在回報） |
| 帳本預檢（`scripts/ledger_precheck.py`） | 三本帳本 0 drift、0 missing；相對 `origin/claude-delivery`（合併基準 `bc4ac31`）21 個檔，沒有列管檔、帳本沒改、沒有新的執行期檔：**OK** |

### 21.5 只在 CI 跑的、沒做的

- 要 root 的 7 個（CI 以 root 跑 pytest）：`test_restore_detection.py` 的 5 個 `test_root_*`、`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`、
  `test_profile_store.py::test_mode_and_owner_as_the_add_on_user`；packaging 的 5 個 `skipUnless(root)`。
- `AF_UNIX path too long` 的 6 個（同第 19.6 節：UNIX socket 在 pytest 的暫存目錄，scratch 路徑超過 108 位元組）：`test_upgrade_hooks.py`
  對真 runtime 的 4 案、`test_owned_executable.py` 的 `test_ipc_rejects_other_own_process_before_tcp` 與開通產品經 owned executable 那案。
  合併後 runtime 是 HM-27 的：照程式看，`OriginPolicy` 與 `OperationJournal` 建起來、讀政策時都不寫檔，升級不該多出 Origin 的檔，
  但這 4 案本機沒跑到，以 CI 為準。
- Playwright：本機沒有瀏覽器，CI 跑。合併結果的 `packages/`、`apps/` 相對 `bc4ac31` 只多本片的 `p9-admin.test.mjs`（node 跑了），
  面板程式與瀏覽器測試和 #116 的相同。實際容器同第 19.7 節：第一次真跑是任何產品下一次發版的 candidate job（單帳號路徑）與 HM-19a 的乾跑（多帳號階段）。
- 契約不改（本片沒有第 9 節的列）。帳本：本片沒有列管檔，合併結果的列管檔和 `bc4ac31` 逐位元相同，`runtime-patches.json`、
  `runtime-sources.json`、`tool-surface.json`／`.md` 就是 HM-27 的版本，沒有重算、沒有 `--write`；`apps/` 沒變，tool-surface 不重產。
- 沒改、交下一步：`docs/operations/acceptance.md` 的 T-24 列仍是 HM-27 定案前的摘要（HA：記下 Claude.ai 送的 Origin）。預設清單含
  `https://claude.ai`，Claude.ai 送它時沒有 would_deny 行，HM-27 筆記交 HM-19b 用 S14 的 echo 端點看；enforce、政策檔不能用時 503、
  還原後的政策等期望值以矩陣 T-24 為準。HM-27 筆記第 6 節「其他」那列說真子程式由本片的容器探針涵蓋：探針確實跑每個帳號的真子程式，
  但不送 `Origin`、不驗 Origin 政策（只收它的檔名）。
