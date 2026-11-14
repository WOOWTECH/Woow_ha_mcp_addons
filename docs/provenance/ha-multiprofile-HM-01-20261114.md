# HA 多帳號 HM-01 provenance：守門測試與預檢工具（2026-11-14）

## 結論

- 範圍：只加測試、測試替身、兩個預檢腳本與本筆記（`tests/`、`scripts/`、`docs/provenance/`）。
  沒有改執行期檔（`packages/`、`apps/`、`packaging/`）、版號、`addons/<x>/`、CHANGELOG、帳本、tool-surface、workflow。
- 新測試 7 檔 131 案，在 `bb48449` 上全部通過、0 skip、沒有條件式 skip；本機合計 29.5 秒。
- 凍結 `bb48449` 預設帳號的行為，逐位元：
  - 黃金回歸：8 個產品×「新安裝」「已設後端」，兩條接法、錯誤回應、`/health/ready`、bootstrap 欄位、子程式收到與送回的標頭、
    `state.json` 不被寫入、資料目錄不變。
  - MCP（8081）契約 99 案：錯誤契約（含檢查順序）、PaaS 的 31 種網址變形、未知 token、標頭冒用、token 輪替與撤銷之後。
  - 管理 API（8099）：HM-00 契約 §4.1 的五種回應形狀，與沒有代碼的固定回應。
  - HM-04～HM-30 每一片都要照過。
- 守門有效：37 個臨時突變（第 3 節），36 個讓新測試失敗。剩下 1 個是 `ProductStore.load()` 自己會改回的權限
  （`config.py:162` 每次讀取都 `fchmod 0600`）；權限放寬留著不改回時，同一個檢查就擋下。
- 兩個預檢：秘密預檢對本分支 9 個 commit 0 命中，建置機同款的 HEAD 與全歷史掃描也 0 命中；帳本預檢 0 漂移。
- 既有測試：全套 pytest 3732 案，3731 通過、1 失敗（已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`）、0 skip，28 分 23 秒。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-01（計畫 §10.2、§12.3；風險低、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm01-20261114` |
| HA 基準 | `claude-delivery` @ `bb48449` |
| 依據 | 計畫 §5.1、§5.3、§8.2、§8.8、§10.2；HM-00 中立契約 `docs/multi-profile/contract.md` §2.2、§4.1、§4.2（同一波的另一個 PR） |
| 對齊的 PaaS | 本片沒有移植 PaaS 程式或測試。契約檔的 31 種網址變形、未知 token、標頭冒用，名稱、目標與替代值照 PaaS 2026-11-13 Odoo 多帳號實機測試（T-05：receipt `s04-token-routing.json`、harness `s04_routing.py`）；PaaS 的狀態碼只當對照欄，不斷言 |
| FM | FM-02、FM-29、FM-95、FM-96、FM-141 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `tests/log_scan.py`、`tests/test_log_scan.py` | `log_scan` fixture。測試期間包住 `Logger.handle`：logger 分派每筆 record 的當下就轉成文字（record factory 的遮罩之後、任何 handler filter 之前），root 降到 DEBUG，`warnings.warn()` 轉進 `py.warnings` logger（`logging.captureWarnings`，最後一個掃描停止時還原；掃描前就開著的不動）。teardown 時掃合成 token（含任 16 字元片段）、憑證與帳號名稱（不分大小寫），0 命中才算過；報告只寫種類、logger、等級與原始碼行，不寫值。掃不到的：`print()`、子程式輸出、有自己 level 的 logger 不會建立的 record（uvicorn 的 logger 是 WARNING）、`catch_warnings(record=True)` 或 `pytest.warns()` 收走的 warning、覆寫 `handle()` 的 Logger 子類。其他 6 個新測試模組都用它（`pytestmark`）。 |
| `tests/owned_network.py`、`tests/owned_network.cjs`、`tests/batch2_owned_port.py` | 測試程序（含衍生的 Python 與 Node，也含 UI 的 fixture 伺服器）在 socket 操作前擋 3000 與 18000～18099。port 照呼叫端自己的讀法解析：Python 是 int，或 `getaddrinfo` 會讀成數字的文字（前後空白、一個 `+`、前導 0）；Node 是 `+port`。`batch2_owned_port` 的 `reserve_port`、`private_spec`、`owned_listener` 也用同一條規則（`owned_network.forbidden_port`）。 |
| `tests/owned_runtime.py`、`tests/owned_child.py` | `private_spec`、`Endpoint`、owned_child 接受 `production_port`（預設 3000；額外帳號 18000～18099），只換那個 port；預設時 argv／env 與原本位元相同。`Endpoint.client()` 對「沒帶 `Authorization`」的請求補 child bearer：spec 自己的（n8n `AUTH_TOKEN`；HM-06 起 Python 子程式的 `WOOW_MCP_CHILD_TOKEN`，每次送出時讀），沒有就每個 endpoint 一個執行時產生的值。`bearer=False` 不帶、字串就帶那個值。 |
| `tests/test_owned_ports_bearer.py` | 上列替身行為；另起 `bb48449` 的 8 支真子程式，用預設帶 bearer 的共用客戶端直連 initialize／tools/list／DELETE：7 支 Python 子程式收到多的 `Authorization` 照常回應，n8n 只認這個值。 |
| `tests/test_single_profile_golden.py` | 黃金回歸。跑真的 `run_product.run`／`apps/n8n/run.py` 的 `run`，只換掉外部（注入點寫在檔頭：`Supervisor`、`httpx.AsyncClient`、`make_ha_admin_verifier`、`Listener`、n8n 的 `prepare_catalog`；HM-05 只准改這幾行）。子程式是只認 child bearer 的假 MCP server，回應另帶 `Location`、`WWW-Authenticate`、`X-Child-Extra`。凍結：兩條接法的整個 session（tools/list 用兩個摘要：打包清單 `surface.listing` 與整個回覆；清單變了提示「刻意改版，兩個一起更新」，清單沒變、回覆變了才判閘道改寫退步）；錯 token 401／404、query 400、`/mcp/` 404；`/health/ready`；bootstrap 欄位；子程式只收到閘道自己的標頭（`CHILD_HEADERS`）與 child bearer；回覆的標頭逐位元（子程式多帶的標頭一個都不轉回）；`state.json` 的位元組、inode、mtime、mode、擁有者、連結數不變；資料目錄每一項的 mode 不變。 |
| `tests/test_mcp_contract_freeze.py`、`tests/contract/profiles_v1_cases.json` | 契約第一批（`ha` 欄）99 案：錯誤 46（其中檢查順序 12）、連線 2、未知 token 8、標頭冒用 7、I1 交叉 1、網址變形 31、token 輪替與撤銷之後 4。每案用原始 HTTP/1.1 請求目標打每個產品正式接線的真 uvicorn listener（h11），比對狀態碼、指定標頭、不該有的標頭、本文位元、有沒有碰到子程式，以及子程式收到的標頭（只有閘道自己的、`Authorization` 只有 child bearer）。37 案註明 HA 和 PaaS 不同所依據的計畫 §8.8 列（#1 28 案、#3 7 案、#9、#10 各 1 案）。產品差異只有 n8n 的錯誤 JSON 是 JSON-RPC -32700、Headscale 的密鑰網址只放 `https://claude.ai`。 |
| `tests/test_admin_contract_freeze.py` | 管理 API（8099）凍結，比整個回應（狀態碼、每個標頭、本文）。8 個產品的正式 runtime：形狀 A（`config_revision_required`、`operation_id_required`）、B（格式錯與過期的 If-Match）、C（沒有標記時 restore、dismiss）、D（存後端、子程式起不來）、E（`backend_check_failed`），與沒有代碼的固定回應（403 五種、400 五種、415、404 兩種、405）。只有 builtin 接法會出現的 E（`unsupported` 三條路由、`backend_fixed`）用 `make_apps` 不接那些 hook 凍結；形狀 D 的 owner-defaults restore 版本用遷移過的舊版 state（emqx、litellm、nextcloud）。 |
| `scripts/secret_precheck.py`、`tests/test_secret_precheck.py` | 秘密預檢。`install` 只收 `packaging/scanner-pins.json` 釘選的 gitleaks（8.28.0；壓縮檔 SHA-256 相符才解出，另記執行檔摘要）；掃描前核對執行檔摘要與版本；設定就是 `packaging/supply_chain.py` 的 `gitleaks_config()`；旗標與建置機 history 掃描相同，只多 `--exit-code 0` 與 commit 範圍；`--full` 另跑建置機的 HEAD 與全歷史掃描。命中只印規則、檔案、行號、commit；exit 0／1／2＝乾淨／有命中／無法判定。git 不拿 optional lock，`git status` 不會順手改 index。 |
| `scripts/ledger_precheck.py`、`tests/test_ledger_precheck.py` | 帳本預檢：`runtime-patches.json`（含 guarded sources）、`runtime-sources.json`、`tool-surface.json` 的摘要漂移與缺檔；本分支對 base 改到的列管檔、帳本有沒有一起改。執行期檔＝`packages/mcp-admin-core/`、`packages/mcp-admin-ui/src/`、`apps/` 的程式檔，加上每個 Dockerfile 都複製的 `packaging/entrypoint.py`、`management_launcher.py`。沒列管的執行期檔：改到的只列出、要人看；**本分支新增的就失敗**（HM-00 `ledger-tracking.md` 規則 1：建立模組的那一片同 PR 列管）。只讀：`git diff` 會刷新它讀的 index，所以讀 index 的私有複本；git 不拿 optional lock。 |
| `docs/provenance/ha-multiprofile-HM-01-20261114.md` | 本筆記 |

沒改：`packages/`、`apps/`、`packaging/` 的任何檔、`addons/<x>/`、版號、CHANGELOG、`upgrade-notes.yaml`、帳本、tool-surface、
workflow、`tests/conftest.py`；既有的測試檔一個都沒改（改的只有 4 個測試替身：`owned_network.py`、`owned_network.cjs`、
`owned_runtime.py`、`owned_child.py`，與 `batch2_owned_port.py`）。

## 3. 守門有效的證據

### 3.1 先紅後綠

先寫測試，再拿改動前的檔跑一次：

| 改動 | 改動前的檔跑新測試 | 新版 |
|---|---|---|
| 4 個替身參數化（`bb48449` 的替身跑 `test_owned_ports_bearer.py` 當時的 48 案） | 47 失敗（3000 原本就擋的 1 案通過） | 全過 |
| `batch2_owned_port` 用同一條 port 規則（`bb48449` 版） | 新的 4 案 3 失敗（18000、18042、18099；3000 原本就擋） | 全過 |
| log 掃描收 `warnings.warn()`（本片第一版） | 1 案失敗（warning 裡的 token 沒被看到） | 全過 |
| 帳本預檢：新增而沒列管的執行期檔失敗、`packaging/` 兩個檔要人看、不改 index（本片第一版） | 7 案 3 失敗 | 全過 |
| 秘密預檢的 git 不拿 optional lock（本片第一版） | 新的 1 案失敗（stat 過期的 checkout 被刷新 index） | 全過 |
| 帳本預檢只加 `--no-optional-locks`、不讀 index 複本 | `test_it_only_reads` 失敗：`git diff` 不理 optional lock，照樣刷新 index | 讀私有複本後通過 |

### 3.2 凍結現狀：用突變證明會擋

黃金回歸與三個凍結測試是「現狀就該綠」。期望值先讀程式（`gateway.py` 的 `serve`、`admin_action`、`error_handler`，
`access.py`、`config.py`、`health.py`、`configuration.py`、`ui.py`），再實際跑出來核對。為確認它們會擋，在暫存複本做臨時突變：
每次只改一處，跑完 `git checkout` 還原，沒有 commit。跑的是黃金回歸＋兩個凍結測試（45 案）；X07b、X25、X26 只跑黃金回歸（17 案）。

| 突變 | 結果 |
|---|---|
| M1 錯的密鑰 token 回 403（不是 404） | 24 個失敗 |
| M2 Bearer 401 不帶 `WWW-Authenticate` | 24 個失敗 |
| M3 MCP 路徑接受 query | 24 個失敗 |
| M4 打開斜線轉址（`/mcp/` 307） | 24 個失敗 |
| M5 `/health/ready` 多一個欄位 | 24 個失敗 |
| M6 bootstrap 多一個欄位 | 16 個失敗 |
| M7 啟動時改寫 `state.json`（加一個空白） | 14 個失敗（7 個 Python 產品；n8n 的啟動在 `apps/n8n/run.py`） |
| M8 啟動時在資料目錄多建一個目錄 | 14 個失敗 |
| M9 轉給子程式的是用戶端 token | 17 個失敗 |
| M10 Bearer 路徑接受 Origin | 8 個失敗 |
| M11 密鑰路徑改看 `Authorization` | 24 個失敗 |
| M12 關掉紀錄遮罩（`redact.install` 不做事） | 16 個 log 掃描失敗 |
| M13 閘道自己回的 tools/list 少一個工具 | 8 個失敗 |
| M14 一行 log 寫出 child token | 24 個 log 掃描失敗 |
| X03 Bearer 的 Origin 檢查移到 token 之前 | 8 個失敗（`order-bearer-origin-wrong-token`、`order-bearer-put-with-origin`） |
| X04 query 檢查移到 token 之前 | 8 個失敗（`order-*-query-wrong-token`、`order-bearer-origin-and-query`） |
| X05 把用戶端的 `X-MCP-Profile`、`Cookie` 轉給子程式 | 8 個失敗（子程式收到的標頭） |
| X06 啟動時用相同位元組重寫 `state.json`（換 inode、mtime） | 14 個失敗 |
| X07 啟動時把 `state.json` 改成 0644 | 0 個：`ProductStore.load()` 每次讀都改回 0600（`config.py:162`），結束時的權限和原本相同 |
| X07b 同上，而且 `load()` 不再改回 | 7 個失敗（mode） |
| X13b 回程多轉子程式的 `Location` | 17 個失敗（黃金回歸 9、契約 8） |
| X14 形狀 B 加 `error` 欄 | 8 個失敗 |
| X15 形狀 E（`backend_check_failed`）改成 `detail.code` | 8 個失敗 |
| X16 Headscale 密鑰網址的 Origin 檢查移到方法之前 | 1 個失敗（Headscale：`order-secret-put-with-origin`） |
| X17 query 檢查移到 Origin 之前 | 8 個失敗 |
| X18 Content-Type 檢查移到 query 之前 | 8 個失敗 |
| X19 撤銷後的 token 回 403 | 8 個失敗（`token-revoked-*`） |
| X20 非管理員的 403 多帶 `detail.code` | 8 個失敗 |
| X22 閘道自己對子程式多送 `X-MCP-Profile: default` | 17 個失敗 |
| X23 restore 的形狀 D 把 `detail` 移到最前面 | 3 個失敗 |
| X24 `unsupported` 多帶 `detail` | 8 個失敗 |
| X25 打包的工具清單變了 | 16 個失敗，訊息是「刻意的工具面改版，兩個摘要一起更新」 |
| X26 閘道自己的 tools/list 改寫變了 | 16 個失敗，訊息是「清單沒變、回覆變了：閘道改寫退步」 |
| X27 GET、DELETE 帶 body 不再 400 | 8 個失敗 |
| X28 重複的 session 標頭不再 400 | 8 個失敗 |
| X29 未知通知改回 400 | 8 個失敗 |
| X30 沒有 session 的拒絕 tools/call 改回 400 | 8 個失敗 |

### 3.3 設計理由

- log 掃描在 logger 分派當下就轉成文字。`redact.guard_handlers` 在 handler 上掛的遮罩 filter 會就地改 record；等 teardown 才轉文字，
  關掉第一層遮罩（M12）也看不出來。
- `CHILD_EXTRA` 不含 `Set-Cookie`：閘道的子程式 client 會把 cookie 存起來、之後送回子程式（第 11 節 HM-05、HM-08）。
- 405 的 `Allow` 只比方法集合：Starlette 從 set 組這個標頭，順序每次執行可能不同。8081 的 `Allow: GET, POST, DELETE` 是閘道自己的
  固定字串，照字面比。
- `state.json` 不比 ctime：`load()` 每次讀都 `fchmod`，ctime 本來就會變。

## 4. HM-00 契約指給 HM-01 的項目，與擋它的測試

「契約」＝本分支的 `tests/test_mcp_contract_freeze.py` 的案例 id；「管理」＝`tests/test_admin_contract_freeze.py`；「黃金」＝
`tests/test_single_profile_golden.py`。`contract.md` 是 HM-00 分支的檔。

### 4.1 管理 API（8099）

| `contract.md` 的項目 | 擋它的測試 |
|---|---|
| 形狀 A（§4.1 開頭；`config_revision_required`、`operation_id_required`） | 管理 `test_management_answer_shapes`（整個回應）。其他 A 代碼經同一段 `error_handler`；`detail.code` 另有 `tests/test_admin_operations.py` |
| 形狀 B `config_conflict`（`Hc/gateway.py:466`、`:484`） | 管理 `test_management_answer_shapes`（格式錯、過期各一案） |
| 形狀 C `owner_defaults_unavailable` | 管理 `test_management_answer_shapes`（restore、dismiss） |
| 形狀 D `config_apply_failed`：存後端（`:639`） | 管理 `test_management_answer_shapes` |
| 形狀 D：owner-defaults restore（`:624`，另帶 `owner_defaults`） | 管理 `test_owner_defaults_restore_apply_failure_shape` |
| 形狀 E `backend_check_failed`（§4.1 表「HM-01 凍結」） | 管理 `test_management_answer_shapes` |
| 形狀 E `unsupported`（同上） | 管理 `test_builtin_only_answer_shapes`（`backend/test`、`diagnostics`、`child/restart`） |
| 形狀 E `backend_fixed`（同上） | 管理 `test_builtin_only_answer_shapes`；既有 `tests/test_management_capabilities.py::test_fixed_builtin_metadata_blocks_backend_mutation_and_version_override`（只看 `error`） |
| 固定回應 403：identity、CSRF、cross-site、非管理員 | 管理 `test_management_answer_shapes` |
| 固定回應 400：query、不該有 body、`X-Ingress-Path`、`%`、格式驗證；415；404（頁面路徑寫入、未知操作）；405 | 管理 `test_management_answer_shapes` |
| 固定回應 503（管理名額滿、拿鎖逾時、state 讀不到）、408、413、斷線 403 | 本片沒做逐位元案例。本體和上面凍結的 400、403 出自同一段 `error_handler`；名額滿、拿鎖逾時、408、413 連狀態碼都沒有直接的既有測試（斷線另有 `tests/test_management_capabilities.py::test_restart_retains_lock_and_joins_on_cancellation` 等管生命週期的測試）。交 HM-10：它的否定矩陣（`tests/test_admin_pipeline_matrix.py`）補未開通時的逐位元案例 |

### 4.2 MCP（8081）

| `contract.md` 的項目 | 擋它的測試 |
|---|---|
| 錯 token：密鑰網址 404、Bearer 401（§4.2 表，含撤銷） | 黃金（錯 token 兩條接法）；契約 `error-*-wrong-token`、`unknown-*`、`order-*-wrong-token` 6 案；撤銷、輪替：`token-revoked-*`、`token-rotated-*` |
| MCP 路徑帶 query 400，在 token 檢查之後（§2.1、§4.2 表） | 契約 `error-bearer-query`、`error-secret-query`、`switch-query-*`；順序：`order-bearer-query-wrong-token`、`order-secret-query-wrong-token`、`order-bearer-origin-and-query`、`order-secret-origin-and-query`、`order-bearer-query-and-content-type`、`order-secret-query-and-malformed-body` |
| Bearer 帶 Origin 403；Headscale 密鑰網址只放 `https://claude.ai` | 契約 `error-bearer-origin`、`error-secret-origin-*`；順序：`order-bearer-origin-wrong-token`、`order-secret-origin-wrong-token`、`order-bearer-put-with-origin`、`order-secret-put-with-origin` |
| 帳號 app 裡今天的流程順序（§2.2 第 5 點；計畫 §5.1 第 6 點） | 契約 `order-*` 12 案 |
| 只轉閘道自己的 child bearer 與 3 個 session 標頭（§2.2 第 5 點；FM-29；§8.8 #4） | 契約每一案都檢查子程式收到的標頭；黃金每個子程式請求 ⊆ `CHILD_HEADERS`、`Authorization` 只有 child bearer |
| 只轉回 4 個標頭（§2.2 第 5 點） | 黃金（`MockChild` 多帶 3 個標頭，回覆標頭逐位元）；契約 `responses.initialize.absent`；既有 `tests/test_streaming_and_storage.py`（`Set-Cookie`） |
| 其他既有回應：405＋`Allow: GET, POST, DELETE` | 契約 `error-*-put`、`error-*-put-wrong-token`、`order-*-put-with-origin`；既有 `tests/test_sse_sanitize.py::test_other_methods_authenticate_then_405` |
| 自答 session 的 GET 405＋`Allow: POST, DELETE` | 既有 `tests/test_unconfigured_connect.py::test_the_own_answers_follow_the_policy_and_the_session_rules` |
| 400：GET、DELETE 帶 body；session 標頭重複或格式錯；沒有 `mcp-session-id` | 契約 `error-bearer-get-with-body`、`-delete-with-body`、`-session-header-twice`、`-session-header-malformed`、`*-without-session` 5 案；既有 `tests/test_session_required.py` |
| 403：政策拒絕的 tools/call 沒帶 session | 契約 `error-bearer-refused-call-without-session` |
| 403：讀 body 時斷線；其他 `Denied` | 本片沒做逐位元案例（本體同 `denied_403`）。交 HM-08：它改讀 body 的地方（准入、位元組額度），`tests/test_profile_quotas.py` 補未開通時的斷線案例 |
| 415；413；408；n8n 的上限 | 415：契約 `error-bearer-wrong-content-type`；413：既有 `tests/test_boundary.py::test_duplicate_keys_and_body_limit`、`tests/test_n8n_request_bounds.py`；408：既有 `tests/test_n8n_request_bounds.py::test_n8n_body_read_timeout_is_bounded_before_child`（n8n）；n8n 的錯誤本體：契約 `parse_error_n8n` |
| 政策拒絕、帶 session 的 tools/call：200＋`-32602` | 既有 `tests/test_full_surface.py::test_unknown_disabled_and_ungranted_tools_never_reach_the_child` 等 |
| 未知方法：有 id 200＋`-32601`；通知 202 | 契約 `error-bearer-unknown-method`、`error-bearer-unknown-notification`；既有 `tests/test_claude_ai_connector.py::test_unknown_method_takes_no_slot` |
| 子程式未就緒時自答（§8.8 #68）；就緒後自答 session 404 | 黃金「新安裝」整個 session；既有 `tests/test_unconfigured_connect.py` |
| 子程式回 4xx、5xx：原狀態碼＋`-32000` 狀態片語 | 既有 `tests/test_sse_sanitize.py::test_non_2xx_replies_keep_status_but_never_child_bytes` |
| initialize 等不到回覆：503＋`BACKEND_UNAVAILABLE`＋`Retry-After: 5` | 既有 `tests/test_initialize_reply.py::test_sse_without_the_reply_is_backend_unavailable_without_a_session` |
| 502 `{"error":"request denied"}`：3xx、格式錯、超過 8 MiB、協定版本 | 既有 `tests/test_sse_sanitize.py::test_a_child_redirect_is_bad_gateway`、`::test_oversize_json_reply_is_bad_gateway`、`::test_unknown_or_duplicate_media_types_are_bad_gateway`、`tests/test_initialize_identity.py::test_any_other_protocol_version_is_refused`（只看狀態碼；本體同 `error_handler`）。交 HM-14：它改這條路徑，`tests/test_gateway_stream_endings.py` 補未開通時的逐位元案例 |
| 轉送名額等 1 秒逾時：503 | 既有 `tests/test_claude_ai_connector.py::test_unknown_method_takes_no_slot`（只看狀態碼）。交 HM-14（`tests/test_gateway_busy_shapes.py`，開通後改成 `-32003`，未開通照今天） |

`contract.md` 第 274、319～321、350 行寫「HM-01 的契約凍結」。依上表，第 274、319～321 行現在成立；第 350 行的其他既有回應是
「HM-01 的契約凍結與既有測試」；其中只有狀態碼（或連狀態碼都沒有測試）的 4 列，已寫明交給 HM-08、HM-10、HM-14。

## 5. 本機檢查（2026-11-14，一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完刪除）

| 檢查 | 結果 |
|---|---|
| 新測試 7 檔（junit；`packaging/check_results.py` PASS：131 executed, no skips） | 131 通過、0 skip，suite 29.5 秒（下表） |
| 全套 pytest（`tests/`） | 3732 案：3731 通過、1 失敗（同一個要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`，本機基準就是這一個）、0 skip；28 分 23 秒 |
| 37 個臨時突變 | 第 3.2 節 |
| 兩個預檢 | 第 8 節 |
| `git status` | 乾淨；`git diff bb48449 -- packages apps packaging addons .github` 空白 |

本片第一版另跑過、這次沒改到的：`packaging/validate.py` PASS；packaging unittest `Ran 184`、`OK (skipped=5)`（5 個
`skipUnless(root)`，和本機基準相同）；`scripts/tool_inventory.py` 與 `build-closure.mjs` 通過；UI `npm test` 58 pass、Playwright
71 passed（fixture 伺服器載入改過的 `owned_network.cjs`；這次沒改這個檔）。

新測試耗時（junit，含 setup／teardown）：

| 檔 | 案數 | 秒 |
|---|---|---|
| `tests/test_log_scan.py` | 13 | <0.1 |
| `tests/test_owned_ports_bearer.py` | 52 | 18.6（8 支真子程式各約 1～3 秒） |
| `tests/test_single_profile_golden.py` | 17 | 2.1 |
| `tests/test_mcp_contract_freeze.py` | 9 | 3.5 |
| `tests/test_admin_contract_freeze.py` | 19 | 0.5 |
| `tests/test_secret_precheck.py` | 14 | 3.2 |
| `tests/test_ledger_precheck.py` | 7 | 0.6 |
| 合計 | 131 | 28.6（pytest 報 29.5） |

## 6. 只在 CI 跑的測試

- 新測試：沒有只能在 CI 跑的，全部在本機（一般使用者）跑過。CI 以 root 跑 pytest，root 下的結果只有 CI 驗得到；新測試不靠執行
  身分或「權限不足」下判斷（臨時 repo、資料目錄、子程式都由同一個身分建立；mode 的比較是前後比，不是比固定值；唯一的固定
  mode 檢查是裝好的 gitleaks 為 0700），預期 root 下結果相同。
- 既有、會用到改過的替身、本機不能跑的：`tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`
  （要 root 才能切到 uid 10001；它的探針 `tests/owned_uid_probe.py` 用 `Endpoint(port=...)`，這條路徑本機由
  `tests/test_owned_runtime.py` 跑過）。
- packaging 的 5 個 `skipUnless(root)`：CI 那一步也不是 root，同樣 skip（和基準相同）。

## 7. `checks` 秒數

- 前（GitHub API jobs 時間）：`bb48449` 的 push run 43222889894 `checks` 1380 秒（23 分 00 秒）；同一個 commit 的
  pull_request run 43222899526 1834 秒。同一份程式碼的兩個 run 就差 454 秒，增量要看多個 run。
- 後：PR 的 CI 跑完後補在 PR 說明。
- 推估：新測試本機 29.5 秒，推估 CI 增加約 30 秒，在每片 1.5 分鐘的預算內。

## 8. 預檢結果

指令（每片 push 前；gitleaks 只要裝一次）：

```sh
python3 scripts/secret_precheck.py install ~/.cache/woow-secret-precheck   # 下載釘選的壓縮檔；手上已有就加 --tarball <檔>
python3 scripts/secret_precheck.py                  # 掃 merge-base(origin/claude-delivery, HEAD)..HEAD 的每個 commit
python3 scripts/secret_precheck.py --full           # 另跑建置機的 HEAD 原始碼與全歷史掃描
python3 scripts/ledger_precheck.py                  # 帳本漂移、本分支改到的列管檔、新增而沒列管的執行期檔
```

- **秘密預檢**：gitleaks 8.28.0（壓縮檔 SHA-256 與 `packaging/scanner-pins.json` 的 `a65b5253…40eb` 相符，執行檔摘要相符）；
  設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本分支的 commit（`bb48449..HEAD`，git 模式） | 0（9 個 commit，含本筆記） |
  | `--full`：`git archive HEAD` 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史 `--all --full-history -m`（建置機同款） | 0 |

- **帳本預檢**（本片的 `scripts/ledger_precheck.py`）：`runtime-patches.json` 152 個路徑（50 個補丁檔＋guarded sources）、
  `runtime-sources.json` 70 個 vendored 檔、`tool-surface.json` 159 個摘要，都 0 漂移、0 缺檔；對 `origin/claude-delivery` 改了
  17 個檔，列管檔 0 個、帳本 0 個、新增或改到而沒列管的執行期檔 0 個。結果 OK。
- **帳本預檢（研究用的原版，HM-00 也用這版）**：`runtime-patches` 50 檔、`runtime-sources` 38 筆、`tool-surface` 80 檔，0 漂移。

## 9. PaaS 變動（`git log <pin>..origin/main -- <相關檔>`）

不適用：本片沒有移植 PaaS 程式或測試，只用了 PaaS 實機測試的案例清單。PaaS 的 #149（main `7d111b1`）只動紀錄遮罩（HM-02）；
本片的測試只依賴 HA 自己的 `redact`（`/private_[REDACTED]` 的格式，HM-02 驗收要求不變），不受影響。

## 10. 驗收條件（計畫 §12.3 HM-01）

| 條件 | 狀態 |
|---|---|
| GitHub CI 綠、0 skip | 待 PR 的 CI。本機：新測試 0 skip、`check_results.py` PASS |
| 新測試沒有條件式 skip | 通過：沒有 `skip`／`skipif`／`importorskip`／`xfail`；本片沒有新增 root 才造得出的情境 |
| 沒有執行期檔變動 | 通過：`git diff bb48449 -- packages apps packaging addons .github` 空白；版號、CHANGELOG、帳本、tool-surface 都沒動 |
| CI 增加 <1.5 分鐘 | 推估通過（第 7 節）；PR 後補實測 |
| 在 `bb48449` 上全部通過 | 通過（本機；分支＝`bb48449`＋只有測試、腳本、文件） |
| 兩個預檢工具對本片自己的 commit 0 命中 | 通過（第 8 節） |
| 既有測試照過（特別是動到替身之後） | 通過：全套 3731／3732，唯一失敗是已知要 root 的那一個 |
| 動到帳本列管的檔就同 PR 更新帳本 | 不適用：本片沒有改到任何列管檔 |
| 黃金回歸、契約凍結的期望值以 `bb48449` 現況為準 | 通過：先讀程式再跑出來核對；突變見第 3.2 節 |
| 新測試用 log 掃描 | 通過：6 個新測試模組都經 `pytestmark` 用 `log_scan`；`test_log_scan.py` 測工具本身 |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：token 一律執行時產生或用 `T`×43／`C`×43（`tests/fixtures/owner_defaults/`），憑證 `DUMMY-…`，網址 `.invalid`；新增的 64 hex 只有 `LISTING_SHA256`、`LISTED_SHA256` 兩組公開清單的摘要；秘密預檢 0 命中 |

## 11. 還沒解決、交給後面的片

- `checks` 的「後」秒數：PR 的 CI 跑完後補。
- HM-04：正式程式的子程式 port 參數化後，額外帳號的測試用 `Endpoint(product, production_port=18000+n)`；`private_spec` 會核對
  spec 帶的就是那個 port。
- HM-05：黃金回歸的注入點寫在 `tests/test_single_profile_golden.py` 檔頭；抽出執行套件時只准改那幾行，期望值不動。
  另外：閘道的子程式 httpx client 會存子程式回的 `Set-Cookie`，之後的請求都帶回去，而且 cookie 不分 port（httpx 0.28.1 實測：
  `127.0.0.1:18000` 設的 cookie 也送到 `18001`）。今天單帳號只是同一個子程式收到自己的 cookie；多帳號時若有 client 被兩個帳號共用，
  A 的子程式設的 cookie 會送到 B 的子程式。
- HM-08：每帳號的子程式 client 關掉 cookie（或每帳號一個 client），並加「跨帳號 cookie 不外流」的測試。契約檔加額外帳號欄：`B`、
  `P24` 在 HM-01 不屬於任何帳號；`cross-bearer-b`、`switch-x-mcp-profile-default-on-b-url` 與 B 路徑上的網址變形，在 HM-08 會改成
  B 帳號的期望值；`order-*` 與 `token_change` 案例在每個帳號 app 都要照過。讀 body 時斷線的 403 見第 4.2 節。
- HM-06：`child_spec` 傳 `WOOW_MCP_CHILD_TOKEN` 之後，經 `Endpoint.client()` 的直連測試自動帶正確的 bearer。計畫寫「多數已由
  HM-01 的共用客戶端處理」，但沒有確切清單：HM-06 開工時，先用「子程式要求有 `Authorization`」的臨時突變跑一次直連測試，
  失敗的就是要逐檔處理的清單（不經 `Endpoint.client()`、自己開 httpx client 直接打 Python 子程式的測試）。
- HM-10、HM-14：第 4.1、4.2 節列的只有狀態碼的既有回應，在改到那條路徑的片補未開通時的逐位元案例。
- tools/list 的兩組摘要：產品工具面刻意改版（`tool_snapshot.py` 重產）時，該產品的 `LISTING_SHA256` 與 `LISTED_SHA256` 一起更新；
  測試的失敗訊息會分辨「清單變了」與「閘道改寫變了」。`docs/tool-surface.md` 由 `scripts/tool_inventory.py` 產生而且列管，本片
  不改它，說明寫在測試檔頭與失敗訊息。
- 秘密預檢只掃已 commit 的內容；有未 commit 的改動時工具會提示，要先 commit 再跑。
