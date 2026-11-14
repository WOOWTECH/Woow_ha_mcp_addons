# HA 多帳號 HM-01 provenance：守門測試與預檢工具（2026-11-14）

## 結論

- 範圍：只加測試、測試替身、兩個預檢腳本與本筆記（`tests/`、`scripts/`、`docs/provenance/`）。
  沒有改執行期檔（`packages/`、`apps/`、`packaging/`）、版號、`addons/<x>/`、CHANGELOG、帳本、tool-surface、workflow。
- 新測試 6 檔 104 案，在 `bb48449` 上全部通過、0 skip、沒有條件式 skip；本機合計 27.8 秒，推估 CI 增加不到 1 分鐘。
- 黃金回歸與契約凍結把 `bb48449` 預設帳號的行為逐位元凍結（8 個產品、兩條接法、錯誤回應、`/health/ready`、bootstrap 欄位、
  `state.json` 不變；契約 77 案，含 PaaS 的 31 種網址變形）。HM-04～HM-30 每一片都要照過。
- 14 個臨時突變（不 commit、跑完還原）全部讓新測試失敗，證明它們會擋。
- 秘密預檢：本分支 5 個 commit 0 命中；建置機同款的 HEAD 原始碼與全歷史掃描也 0 命中。帳本預檢：0 漂移，本片沒動列管檔。
- 既有測試：import 改過替身的 44 檔 787 案，786 通過，唯一失敗是已知要 root 的那一個；全套 pytest 3705 案 3704 通過、1 失敗（同一個要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`）、0 skip。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-01（計畫 §10.2、§12.3；風險低、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm01-20261114`（一般 clone，不是 worktree） |
| HA 基準 | `claude-delivery` @ `bb48449` |
| 對齊的 PaaS | 本片沒有移植 PaaS 程式或測試。契約檔的 31 種網址變形、未知 token、標頭冒用，名稱、目標與替代值照 PaaS 2026-11-13 Odoo 多帳號實機測試（T-05：receipt `s04-token-routing.json`、harness `s04_routing.py`，都在 repo 外）；PaaS 的狀態碼只當對照欄，不斷言 |
| 使用者決定 | 2026-11-14 13:4x 全部採用計畫 §13.1 的 15 項建議，並同意開始第 0 波（HM-00、HM-01） |
| 接續 | 15:00 左右因帳號用量上限中斷；留下的半成品（備份在 repo 外的 `wave0/hm01-partial-20261114-1501/`）逐檔讀過、重跑，好的留下，問題修掉（第 3 節）；半成品筆記裡的結果全部重新驗證過，沒有照抄 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `tests/log_scan.py`、`tests/test_log_scan.py` | `log_scan` fixture。測試期間包住 `Logger.handle`：logger 分派每筆 record 的當下就轉成文字（record factory 的遮罩之後、任何 handler filter 之前），root 降到 DEBUG。teardown 時掃合成 token（含任 16 字元片段）、憑證與帳號名稱（不分大小寫），0 命中才算過；報告只寫種類、logger、等級與原始碼行，不寫值。其他 5 個新測試模組都用它（`pytestmark`）。 |
| `tests/owned_network.py`、`tests/owned_network.cjs` | 測試程序（含衍生的 Python 與 Node，也含 UI 的 fixture 伺服器）在 socket 操作前擋 3000 與 18000～18099。port 照呼叫端自己的讀法解析：Python 是 int，或 `getaddrinfo` 會讀成數字的文字（前後空白、一個 `+`、前導 0）；Node 是 `+port`（`' 18000.0 '`、`'0x4650'` 也算）。 |
| `tests/owned_runtime.py`、`tests/owned_child.py` | `private_spec`、`Endpoint`、owned_child 接受 `production_port`（預設 3000；額外帳號 18000～18099），只換那個 port；預設時 argv／env 與原本位元相同。`Endpoint.client()` 對「沒帶 `Authorization`」的請求補 child bearer：spec 自己的（n8n `AUTH_TOKEN`；HM-06 起 Python 子程式的 `WOOW_MCP_CHILD_TOKEN`，每次送出時讀，換代後跟得上），沒有就每個 endpoint 一個執行時產生的值；閘道自己的請求一律帶 child token，照舊送出。`bearer=False` 不帶、字串就帶那個值。 |
| `tests/test_owned_ports_bearer.py` | 上列替身行為；另起 `bb48449` 的 8 支真子程式，用預設帶 bearer 的共用客戶端直連 initialize／tools/list／DELETE：7 支 Python 子程式收到多的 `Authorization` 照常回應，n8n 只認這個值（不帶就 401）。 |
| `tests/test_single_profile_golden.py` | 8 個產品×「新安裝」「已設後端」的單帳號黃金回歸。跑真的 `run_product.run`／`apps/n8n/run.py` 的 `run`（ProductStore、owner-defaults 啟動步驟、`make_apps`、HealthMonitor、ConfigurationState、`child_spec`、紀錄遮罩），只換掉外部：listener 不開 socket、Supervisor 不起程序、子程式改成只認 child bearer 的假 MCP server、HA 管理員檢查回 yes。凍結：預設 token 經 Bearer `/mcp` 與 `/private_<token>/mcp` 的 initialize／initialized／tools/list（整個回覆的 SHA-256）／tools/call／DELETE；錯 token 401／404（與未知路徑同位元）、query 400、`/mcp/` 404；`/health/ready` 兩種形狀；bootstrap 欄位集合與固定值；啟動、讀取、列清單前後 `state.json` SHA-256 與資料目錄清單不變；子程式只收到閘道自己的 bearer，看不到用戶端 token 與 Origin。 |
| `tests/test_mcp_contract_freeze.py`、`tests/contract/profiles_v1_cases.json` | 契約第一批（`ha` 欄）77 案：錯誤契約 28、連線 2、未知 token 8、標頭冒用 7、I1 交叉案例 1（另一個交叉案例是 `switch-authorization`）、PaaS 的 31 種網址變形。每案用原始 HTTP/1.1 請求目標打每個產品正式接線的真 uvicorn listener（h11），比對狀態碼、指定標頭、本文位元、有沒有碰到子程式。27 案註明 HA 和 PaaS 不同所依據的計畫 §8.8 列（#1、#3、#9、#10）；其他和 PaaS 不同的案例都有說明（測試會檢查）。產品差異只有兩處：n8n 的錯誤 JSON 是 JSON-RPC -32700、Headscale 的密鑰網址只放 `https://claude.ai`。 |
| `scripts/secret_precheck.py`、`tests/test_secret_precheck.py` | 秘密預檢。`install` 只收 `packaging/scanner-pins.json` 釘選的 gitleaks（目前 8.28.0；壓縮檔 SHA-256 相符才解出，另記執行檔摘要）；掃描前核對執行檔摘要與版本；設定就是 `packaging/supply_chain.py` 的 `gitleaks_config()`；旗標與建置機 history 掃描相同，只多 `--exit-code 0` 與 commit 範圍；掃 `merge-base(--base, HEAD)..HEAD` 的每個 commit；`--full` 另跑建置機的 HEAD 原始碼與全歷史掃描。命中只印規則、檔案、行號、commit；exit 0／1／2＝乾淨／有命中／無法判定。CI 沒有 gitleaks，測試用記錄呼叫的替身逐項比對建置機的呼叫。 |
| `scripts/ledger_precheck.py`、`tests/test_ledger_precheck.py` | 帳本預檢（由 R10 研究用的暫存腳本收進 repo 並補強）：`runtime-patches.json`（含 guarded sources）、`runtime-sources.json`（`apps/<產品>/vendor/<路徑>`，與 `tests/test_tool_inventory.py` 同規則）、`tool-surface.json` 的摘要漂移與缺檔；本分支對 base 改到的列管檔、帳本有沒有一起改、沒列管的執行期檔（只提醒）。只讀。 |
| `docs/provenance/ha-multiprofile-HM-01-20261114.md` | 本筆記 |

沒改：`packages/`、`apps/`、`packaging/` 的任何檔、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、帳本、tool-surface、
workflow、`tests/conftest.py`；既有測試檔一個都沒改。

## 3. 先紅後綠、現狀就該綠，與接續時修掉的問題

- **替身參數化**（`tests/test_owned_ports_bearer.py`）：先寫測試。把 4 個替身換回 `bb48449` 原版跑：48 案 47 失敗、1 通過
  （3000 原本就擋的 Python 哨兵案例）；換回新版 48 案全過。
- **黃金回歸、契約凍結**：凍結 `bb48449` 現況，「現狀就該綠」。期望值先讀 `gateway.py`（`serve`、`leased_serve`、`token_valid`、
  `secret_valid`、路由、bootstrap 組裝）、`access.py`、`config.py`、`health.py`、`configuration.py`，再實際跑出來逐項核對。
  為確認它們真的會擋，做了 14 個臨時突變（每個只改一處執行期檔、跑完 `git checkout` 還原、核對 `packages/`、`apps/`
  與 `bb48449` 相同；沒有 commit）。最後一版測試的結果：

  | 突變 | 跑的測試 | 結果 |
  |---|---|---|
  | M1 錯的密鑰 token 回 403（不是 404） | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M2 Bearer 401 不帶 `WWW-Authenticate` | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M3 MCP 路徑接受 query | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M4 打開斜線轉址（`/mcp/` 307） | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M5 `/health/ready` 多一個欄位 | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M6 bootstrap 多一個欄位 | 黃金回歸 | 16 個失敗 |
  | M7 啟動時改寫 `state.json`（加一個空白） | 黃金回歸 | 14 個失敗（7 個 Python 產品；n8n 的啟動在 `apps/n8n/run.py`，沒有突變） |
  | M8 啟動時在資料目錄多建一個目錄 | 黃金回歸 | 14 個失敗（同上） |
  | M9 轉給子程式的是用戶端 token | 黃金回歸＋契約凍結 | 17 個失敗（沒有子程式的 7 個「新安裝」不經過這段） |
  | M10 Bearer 路徑接受 Origin | 契約凍結 | 8 個失敗 |
  | M11 密鑰路徑改看 `Authorization` | 黃金回歸＋契約凍結 | 24 個失敗 |
  | M12 關掉紀錄遮罩（`redact.install` 不做事） | 黃金回歸 | 16 個 log 掃描失敗 |
  | M13 閘道自己回的 tools/list 少一個工具 | 黃金回歸 | 8 個失敗（8 個「新安裝」） |
  | M14 一行 log 寫出 child token | 黃金回歸＋契約凍結 | 24 個 log 掃描失敗 |

- **log 掃描**：接續時發現半成品的做法擋不住 M12。它在 teardown 才把 record 轉成文字，而 `redact.guard_handlers` 已在 pytest
  的 root handler 掛上遮罩 filter，同一個 record 早被就地改掉，關掉第一層遮罩也看不出來。改成 logger 分派當下就轉成文字
  （包住 `Logger.handle`，在任何 handler filter 之前）後，M12 讓 16 個黃金回歸失敗；並新增「只有 handler filter 遮掉的值仍算
  命中」的測試。
- **其他接續時的修正**：
  - 契約檔：`random_hex64_with_X-MCP-Profile` 的名稱與 PaaS receipt 不符（應為 `…_B`）；補上 receipt 有、半成品漏掉的
    `profile_id_as_token`、`X-MCP-Profile=default_on_B_url`，I1 交叉案例 `cross-bearer-b`，Bearer 路徑的 `X-MCP-Profile` 冒用
    （`P24`＝額外帳號 id 的形狀：24 位小寫 hex，執行時產生）；PaaS 與 HA 不同的案例補註 §8.8 列，並由測試要求每個不同都有說明。
  - `Endpoint.client()` 的 bearer 改成每次送出時讀；`production_port` 只收 int。
  - Node 與 Python 的 port 解析照各自的讀法（半成品只認純數字）。
  - log 掃描的遮罩測試不再綁 `redact` 失敗時的字樣（HM-02 可能改）。
  - 秘密預檢的測試改讀釘選版本，不寫死 8.28.0；載入 `supply_chain.py` 時不在 checkout 寫 bytecode。
  - 黃金回歸的「錯誤回應不碰子程式」改用排除健康監看的計數（監看每 15 秒一次，慢機器上可能剛好插進來）。
- **兩個預檢工具**：工具與測試同片新寫。秘密預檢的測試用替身 gitleaks 逐項比對建置機 `supply_chain.secret_scan` 的呼叫、
  allowlist 就是 `gitleaks_config()`、六種失敗都 exit 2 且不回顯掃描器輸出。另用真的 gitleaks 8.28.0 做正向對照：臨時 repo
  裡一個執行時產生的假金鑰 commit 被抓到（`generic-api-key`，exit 1，只印規則、檔案、行號、commit）。帳本預檢的測試在臨時
  repo 造漂移、缺檔、沒列管的檔。

## 4. 本機檢查（2026-11-14，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，使用者同意，每次跑完刪除）

| 檢查 | 結果 |
|---|---|
| `packaging/validate.py`（Python 3.13.15＋`packaging/requirements-ci.txt`） | PASS |
| packaging unittest | `Ran 184 tests`、`OK (skipped=5)`；5 個是 `skipUnless(root)`，和本機基準相同 |
| `scripts/tool_inventory.py`、`build-closure.mjs` | 都通過 |
| UI `npm test`（`packages/mcp-admin-ui`） | 58 pass |
| UI Playwright（`npm run test:browser`；fixture 伺服器載入改過的 `owned_network.cjs`） | 71 passed（2.6 分） |
| 新測試 6 檔（junit；`packaging/check_results.py` PASS：104 executed, no skips） | 104 通過、0 skip，suite 27.8 秒（下表） |
| import 改過替身的既有測試 44 檔（直接，或經 `owned_executable`、`integration_*`、`owned_uid_probe`、`owned_browser` import `owned_runtime`／`owned_child`／`owned_network`；含新的 `test_owned_ports_bearer.py`） | 787 案：786 通過、1 失敗（`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`，要 root，本機基準就是這一個）；17 分 04 秒 |
| 全套 pytest（`tests/`） | 3705 案：3704 通過、1 失敗（同一個要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`）、0 skip；28 分 08 秒 |
| 14 個臨時突變 | 全部讓新測試失敗（第 3 節） |
| `git status` | 乾淨；`git diff bb48449 -- packages apps packaging addons` 空白 |

新測試耗時（junit，含 setup／teardown）：

| 檔 | 案數 | 秒 |
|---|---|---|
| `tests/test_log_scan.py` | 11 | <0.1 |
| `tests/test_owned_ports_bearer.py` | 48 | 18.7（8 支真子程式各約 1～3 秒） |
| `tests/test_single_profile_golden.py` | 17 | 2.0 |
| `tests/test_mcp_contract_freeze.py` | 9 | 2.7 |
| `tests/test_secret_precheck.py` | 13 | 3.0 |
| `tests/test_ledger_precheck.py` | 6 | 0.4 |
| 合計 | 104 | 26.9（pytest 報 27.8） |

## 5. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。CI 以 root（`sudo -n`）跑 pytest，root 下的結果只有 CI 驗得到；
  新測試不靠執行身分或「權限不足」下判斷（臨時 repo、資料目錄、子程式都由同一個身分建立；唯一的檔案模式檢查是裝好的
  gitleaks 為 0700，和身分無關），預期 root 下結果相同。
- 既有、會用到改過的替身、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`
  （要 root 才能切到 uid 10001；它的探針 `tests/owned_uid_probe.py` 用 `Endpoint(port=...)` 與 `supervisor(..., prepared=True)`，
  這兩條路徑本機由 `tests/test_owned_runtime.py` 跑過）。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。

## 6. `checks` 秒數

- 前（GitHub API jobs 時間）：`bb48449` 的 push run 43222889894 `checks` 1380 秒（23 分 00 秒）；同一個 commit 的
  pull_request run 43222899526 1834 秒；PR #88（`feaca19`）run 43218199101 1775 秒（29 分 35 秒，計畫 §10.1 引用的那個）。
  同一份程式碼的兩個 run 就差 454 秒，增量要看多個 run。
- 後：本階段只 commit、還沒開 PR；開 PR 後用 GitHub API 的 jobs 時間補。
- 推估：新測試本機 27.8 秒。本機全套 pytest 約 28 分，而 CI 的整個 `checks`（含安裝、UI、Playwright、packaging）只要 23～31 分，
  CI 跑 pytest 不比本機慢；推估 CI 增加約 30 秒，在每片 1.5 分鐘的預算內。

## 7. 預檢結果

指令（每片 push 前；gitleaks 只要裝一次）：

```sh
python3 scripts/secret_precheck.py install ~/.cache/woow-secret-precheck   # 下載釘選的壓縮檔；手上已有就加 --tarball <檔>
python3 scripts/secret_precheck.py                  # 掃 merge-base(origin/claude-delivery, HEAD)..HEAD 的每個 commit
python3 scripts/secret_precheck.py --full           # 另跑建置機的 HEAD 原始碼與全歷史掃描
python3 scripts/ledger_precheck.py                  # 帳本漂移與本分支改到的列管檔
```

- **秘密預檢**：gitleaks 8.28.0（本機的壓縮檔 SHA-256 與 `packaging/scanner-pins.json` 的 `a65b5253…40eb` 相符，用本工具的
  `install --tarball` 解出並記錄執行檔摘要）；設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | commit 前的 dir 模式：本片新增與改動的 15 個檔，另掃本筆記最後一版 | 0 |
  | 本分支的 commit（`bb48449..HEAD`，git 模式） | 0（5 個 commit，含本筆記） |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

- **帳本預檢**：`runtime-patches.json` 152 個路徑（50 個補丁檔＋guarded sources）、`runtime-sources.json` 70 個 vendored 檔、
  `tool-surface.json` 159 個摘要，都 0 漂移、0 缺檔（本機裝好了 CI 的安裝，所以 `.venv`／`node_modules` 裡的也都核對到）；
  對 `origin/claude-delivery` 改了 15 個檔（含本筆記），列管檔 0 個、帳本 0 個、沒列管的執行期檔 0 個。結果 OK。

## 8. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

不適用：本片沒有移植 PaaS 程式或測試，只用了 PaaS 實機測試的案例清單（repo 外的 receipt 與 harness，不是 PaaS repo 的檔）。
HM-00 期間 PaaS 合併的 #149（14:19，main `7d111b1`）只動紀錄遮罩（HM-02）；本片的測試只依賴 HA 自己的 `redact`
（`/private_[REDACTED]` 的格式，HM-02 驗收要求不變），不受影響。

## 9. 驗收條件（計畫 §12.3 HM-01 與本片工作說明）

| 條件 | 狀態 |
|---|---|
| GitHub CI 綠、0 skip | 待 PR（本階段不 push）。本機：新測試 0 skip、`check_results.py` PASS |
| 新測試沒有條件式 skip | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail`；本片沒有新增 root 才造得出的情境 |
| 沒有執行期檔變動 | 通過：`git diff bb48449 -- packages apps packaging addons` 空白；版號、CHANGELOG、帳本、tool-surface 都沒動 |
| CI 增加 <1.5 分鐘 | 推估通過（第 6 節）；PR 後補實測 |
| 在 `bb48449` 上全部通過 | 通過（本機；分支＝`bb48449`＋只有測試、腳本、文件） |
| 兩個預檢工具對本片自己的 commit 0 命中 | 通過：秘密預檢 5 個 commit 0 命中，`--full` 也 0；帳本預檢 OK |
| 既有測試照過（特別是動到 owned_* 之後） | 通過：44 檔 786／787，唯一失敗是已知要 root 的那一個；全套 3704／3705，唯一失敗同上 |
| 動到帳本列管的檔就同 PR 更新帳本 | 不適用：帳本預檢顯示本片沒有改到任何列管檔 |
| 黃金回歸、契約凍結的期望值以 `bb48449` 現況為準 | 通過：先讀程式再跑出來核對；14 個突變全部擋下 |
| 新測試用 log 掃描 | 通過：5 個新測試模組都經 `pytestmark` 用 `log_scan`，碰到 token 的測試另外指定要掃的值；`test_log_scan.py` 測工具本身（其中一案用 fixture） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 一律執行時產生或用 `T`×43／`C`×43，憑證 `DUMMY-…`，網址 `.invalid`；commit 前後的秘密掃描都 0 命中 |

## 10. 還沒解決、交給後面的片

- `checks` 的「後」秒數：開 PR 後補（GitHub API jobs 時間）。
- HM-04：正式程式的子程式 port 參數化後，額外帳號的測試用 `Endpoint(product, production_port=18000+n)`；`private_spec` 會核對
  spec 帶的就是那個 port。
- HM-06：`child_spec` 傳 `WOOW_MCP_CHILD_TOKEN` 之後，經 `Endpoint.client()` 的直連測試（C4-SF-4 點名的
  `test_session_idle.py`、`test_nextcloud_child.py`、經 `test_six_hardening` 的 `test_hermes_safe_public_errors.py` 等）自動帶
  正確的 bearer；當閘道子程式 client 用的照舊（閘道自己帶 child token）。不經它、自己開 httpx client 直接打 Python 子程式的
  測試仍要逐檔處理，清單由 HM-06 列。
- HM-08：契約檔加額外帳號欄。`B`、`P24` 在 HM-01 不屬於任何帳號；`cross-bearer-b`、`switch-x-mcp-profile-default-on-b-url`
  與 B 路徑上的網址變形，在 HM-08 會改成 B 帳號的期望值。
- `LISTED_SHA256`（8 個產品 tools/list 的整個回覆）：產品工具面刻意改版時要一起更新；其他變動都算退步。
- log 掃描包的是 `logging.Logger.handle`：覆寫 `handle` 的自訂 Logger 子類看不到（目前 repo 沒有）；子程序輸出與 `print()`
  不是 log record，不在範圍內。
- 秘密預檢只掃已 commit 的內容；有未 commit 的改動時工具會提示，要先 commit 再跑。
