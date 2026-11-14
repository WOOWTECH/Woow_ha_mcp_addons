# HA 多帳號 HM-02 provenance：紀錄遮罩對齊 PaaS（含 #149，原樣 vendor）（2026-11-15）

## 結論

- 範圍：原樣 vendor PaaS 的 `log_redaction.py`（woow-mcp-server main `7d111b1`，#149 合併版）與它的 4 個純測試；
  HA 的紀錄遮罩（record factory、`RedactSecretPaths`）與子程式輸出遮罩改成「PaaS 規則先、HA 規則後」；子程式輸出補遮
  `key=`。沒改版號、`addons/<x>/`、CHANGELOG、workflow、`apps/`、UI。
- 97 種密鑰網址寫法（原樣／解碼／access 寫法，兩種 token）：bb48449 在紀錄裡漏 10／40／4、子程式輸出漏 9／39／3；
  改完 5 個地方都是 1／22／0，和 pin 版 PaaS 一樣（門檻在測試當下用 PaaS 模組算），沒有任何一種寫法比 bb48449 退步。
- #149 的 query 憑證：27 個鍵名加 `token`、`access_token`，共 189 種拼法 × 8 種樣板，5 個地方全部遮住
  （bb48449 在紀錄裡 1512 個全露、子程式輸出露 528 個）。
- 單純「PaaS 先、HA 後」在少數寫法會露出 bb48449 原本藏住的值。新增 `redact.shows_hidden` 守門：這種結果改成 PaaS 的
  `[redacted: ambiguous URL encoding]`（fail closed）。本機差分 fuzz 40 萬行、測試內 2400 行，都 0 違反。
- 先紅後綠：新測試 86 案，在 bb48449 的遮罩上 43 案失敗，改完全過；vendored PaaS 測試 574 案全過。
- 既有測試 0 修改；`[REDACTED]` 格式不變；秘密預檢 0 命中；帳本預檢 0 漂移。本機全套 pytest 4392 案，失敗的 23 案都和本片無關（1 個要 root、22 個是這個 clone 沒裝 Chromium 的瀏覽器測試）。
- Release train 不比對新 vendored 的檔，不擋（第 5 節）。
- **和指示不同的一點，要主對話決定**：`docs/provenance/runtime-sources.json` 只收 `apps/<產品>/vendor/<路徑>` 的檔，
  加一筆 `packages/` 的檔會讓既有測試失敗。來源 repo、commit、路徑、SHA-256 改記在 `runtime-patches.json`（第 12 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-02（計畫 §8.6、§12.3；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm02-20261114` |
| HA 基準 | HM-01 分支 head `32ecac8`（＝`bb48449`＋HM-01，PR #90 等合併）；`redact.py`、`diagnostics.py` 在 `32ecac8` 與 `bb48449` 逐位元相同 |
| 對齊的 PaaS | `WOOWTECH/woow-mcp-server` main `7d111b175fbbcdf692ff579cc5793bf8c7de3a7b`（#149 合併）；fetch 時 `origin/main`＝`cf3d0d5`（第 6 節） |
| 依據 | 計畫 §8.6、§11.1、§12.0、§12.3「HM-02」；HM-00 `ledger-tracking.md`、`paas-test-mapping.md`、`acceptance-matrix.md`（T-25、`tests/test_redaction_matrix.py` 登記列） |
| FM | FM-75（另含 FM-65 的 `?key=`） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/log_redaction.py`（新） | PaaS `7d111b1` 同路徑的檔，逐位元相同（SHA-256 `1fec42aab78201e5c2bd892586e19ee640f0214905189ff9dbfea29d729b1f91`）。本 repo 不改它；PaaS 之後再改就整檔同步。 |
| `packages/mcp-admin-core/mcp_admin_core/redact.py` | `scrub()`：先 `log_redaction.scrub_record`，再照舊套 HA 規則，最後 `_fail_closed`。新常數 `PATH_RULES`、`PIECE`，新函式 `apply_rules`、`shows_hidden`、`scrub_text`；`install()` 先編好 PaaS 延遲編譯的 pattern。`redact()`、`leaks()`、`REDACTED`、`SECRET_MASK`、`secret_values`、`redact_secrets` 不變。 |
| `packages/mcp-admin-core/mcp_admin_core/diagnostics.py` | `scrub_line()`：已知秘密換掉之後，`redact.scrub_text(text, RULES)`。`RULES`＝bb48449 的四條規則（`PRIVATE_SEGMENT`、`AUTH`、`ASSIGNMENT`、`USERINFO`，regex 與順序都不變）＋新的 `KEY`。 |
| `docs/provenance/runtime-patches.json` | 新增 `log_redaction.py` 一筆（`sha256`、`change` 寫來源 repo、commit、路徑、SHA-256；`guarded_sources` 是 `{}`）。 |
| `tests/vendor_paas/test_log_redaction_{encoded_boundaries,linear,segments,single_pass}.py`（新） | PaaS `7d111b1` 的 `packages/mcp-admin-core/tests/` 同名檔，逐位元相同（574 案）。 |
| `tests/vendor_paas/conftest.py`、`__init__.py`（新，HA 寫的） | 每個 PaaS 測試前換回標準 record factory、拿掉 HA 的 `RedactSecretPaths`；跑完還原 record factory、每個 logger 與 handler 的 filter，以及 root 以外每個 logger 的 level、propagate、handler（測試中才建立的 logger 回到剛建立的樣子）。兩個方向都需要：沒有前半，`test_secret_path.py::test_real_uvicorn_logs_never_show_the_secret` 之後有 2 個 PaaS 測試失敗（HA 的遮罩層留在同一個 pytest 程序裡）；沒有後半，PaaS 測試排在前面時那個 HA 測試失敗（PaaS 的 `test_log_redaction_linear.py` 借用 `uvicorn.error` 後留下 INFO、不往上傳，traceback 改寫到 `logging.lastResort`）。 |
| `tests/test_redaction_matrix.py`（新，86 案） | 見第 7 節。所有案例都在 HM-01 的 `log_scan` 下跑。 |
| `tests/fixtures/redact_bb48449.py`、`diagnostics_bb48449.py`（新） | bb48449 的兩個檔，逐位元相同（測試釘 SHA-256），當不退步差分的對照組。 |
| `docs/provenance/ha-multiprofile-HM-02-20261114.md` | 本筆記 |

沒改：`apps/`（含 `apps/runtime/*.py`、`apps/*/launch.py`，所以不用重產 tool-surface）、`packaging/`、`addons/<x>/`、版號、
CHANGELOG、`upgrade-notes.yaml`、`runtime-sources.json`、`tool-surface.json`／`.md`、workflow、`THIRD_PARTY_NOTICES.md`、
UI；既有的測試檔一個都沒改。`redact.py`、`diagnostics.py` 照 HM-00 `ledger-tracking.md` 第 3 節維持不列管（帳本預檢列為「要人看」）。

## 3. 設計

### 3.1 組合順序

- 紀錄（`redact.scrub`，即 record factory 與 `RedactSecretPaths`）：`log_redaction.scrub_record` → HA 的逐參數遮罩 →
  `_fail_closed`。PaaS 先把 `/private_<token>` 遮成 `/private_***`，HA 規則再換成 `/private_[REDACTED]`，所以顯示照舊；
  query 憑證的值顯示 PaaS 的 `***`。
- 子程式輸出（`diagnostics.scrub_line`）：ANSI → 已知秘密（照舊）→ PaaS 規則 → HA 的五條規則 → 守門 → 可列印字元與長度
  （照舊）。`token=` 這類值最後仍顯示 `[REDACTED]`（ASSIGNMENT 會把 `token=***` 換掉）。
- 不呼叫 PaaS 自己的 `install()`：它在 `uvicorn.access`、`uvicorn.error`、`httpx` 掛的 logger filter 會在 HA 規則之後再遮一次，
  沒有 `RedactSecretPaths` 的 handler（`logging.lastResort`）就會看到 `/private_***`。`redact.install()` 改呼叫
  `log_redaction._warm_patterns()`，和 PaaS `install()` 一樣在啟動時編好 pattern。
- 反過來的順序（HA 先、PaaS 後）在 97 種寫法上是 5／31／2，比 PaaS 差（測試 `test_the_reversed_order_would_not_meet_the_threshold`）。

### 3.2 不退步的守門（`redact.shows_hidden`）

- 問題（差分 fuzz 找到，都有測試）：
  1. PaaS 的解碼後規則遮到東西時，它回解碼後的字串；HA 規則接著停在解碼出來的空白或引號。例：`/private_abc?a=1%20<T>&token=%2Fv`，
     bb48449 整段藏住，單純組合會露出 `<T>`（PaaS 自己也露）。
  2. PaaS 的值規則停在 `#`、`&`，HA 規則卻把後面當成同一段密鑰路徑（不需要跳脫字元）。例：`/x?token=abc/private_<T>#<V>/x`。
  3. 子程式輸出：PaaS 遮 `&key=@…` 時吃掉 userinfo 的 `@`，`USERINFO` 就比對不到。例：`http://user:<T>&key=@host/x`。
- 做法：同一段原文，用 HA 規則單獨套一次，記下被換掉的值。組合後的結果若有 4 個字元以上連續（英數、`_`、`-`；原樣或解碼後）
  是「HA 規則單獨會藏住、而且 HA 單獨的結果別處也沒顯示」的片段，就整段改成 PaaS 的 `[redacted: ambiguous URL encoding]`。
  紀錄裡分別看訊息、例外文字、stack；uvicorn access record 維持 5 個參數，先換 path，不夠再換其他字串參數（和 PaaS 相同）。
- 4 個字元：和 `redact.MIN_SECRET` 一樣（更短的憑證，`secret_values` 也不收、`redact_secrets` 不換）。測試計算外洩時照 PaaS 測試用 8 個字元。
- `key=` 是最後一條規則，不併進 `ASSIGNMENT`：併進去會先把 `key=…@` 換掉，前面的 userinfo 就露出來（第 3 個例子，
  守門的對照組用到 bb48449 的規則，所以 bb48449 的四條規則維持原樣、原順序）。
- 為什麼不改成「HA 先」或「兩種都算再選」：HA 先會讓 PaaS 看不到密鑰路徑原本的形狀（97 種寫法的 291 行裡，15 行 PaaS 遮得住、
  HA 先就露）；兩種都算也找不到同時「不比 PaaS 差」又「不比 bb48449 差」的保證，只有 placeholder 兩邊都滿足。

### 3.3 效能

- 線性：原文只看到 PaaS 自己的上限 `MAX_REDACT_CHARS`（128 KiB；PaaS 顯示的內容也不超過這段）；只記住「結果裡有、HA 單獨
  結果裡沒有」的片段；被藏住的值少時用子字串搜尋，多時掃一遍。
- 本機量測（每次一筆，取 3 次最好）：一般 200 位元組的行 0.1～0.4 ms（PaaS 單獨 0.1～0.2 ms）；PaaS `test_log_redaction_linear.py`
  的 64 KB 病態形狀，紀錄 ≤ 37 ms（PaaS ≤ 36 ms）、uvicorn access record ≤ 14 ms（PaaS ≤ 2 ms）、子程式的 8 KiB 行 ≤ 12 ms；
  128 KiB 的病態行 ≤ 63 ms，1 MiB 3 ms（只看前 128 KiB）。
- 一開始的寫法（把原文、HA 結果、組合結果的所有片段都放進集合）在 128 KiB 要 1.7 秒、49 MB，512 KiB 要 5.4 秒、193 MB，
  所以改成上面的做法；`test_the_guard_is_bounded_on_pathological_lines` 每種形狀限 1.5 秒。

### 3.4 顯示上的變化（不是退步）

- 紀錄裡的 query 憑證值顯示 PaaS 的 `***`（bb48449 不遮）；HA 原有的 `[REDACTED]`、`/private_[REDACTED]` 格式不變。
- PaaS 判斷不了編碼的行顯示 `[redacted: ambiguous URL encoding]`；PaaS 超過 128 KiB 的字串截斷並加 `…[truncated N chars]`。
- 格式字串和參數對不上的 record（`logging.warning('%s %s', 'a')`）：bb48449 顯示 `log record withheld (redaction failed)`，
  現在先由 PaaS 換成 `[redacted: invalid log message]`。兩者都不顯示內容；沒有測試依賴前者的文字。
- 第一次遮罩可能留下 `/private_[REDACTED]\***`（PaaS 把 `/private_` 後的反斜線當雜訊留下，HA 規則停在反斜線），
  第二次遮罩（`RedactSecretPaths`）變成 `/private_[REDACTED]`。兩種都不露值，第二次起穩定（`test_composition_is_stable_on_the_corpora`）。

## 4. vendor 前的秘密預檢與測試改動

- 工具：本 repo 釘的 gitleaks 8.28.0（`scripts/secret_precheck.py install` 從 `packaging/scanner-pins.json` 核對過的壓縮檔裝），
  設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`，對 repo 外的 `7d111b1` 檔案目錄跑（只印規則、檔名、行號）。
- 結果：33 個命中，全部在 `test_log_redaction_query_credentials_review.py`（generic-api-key 30、jwt 3）；`log_redaction.py`、
  4 個純測試、`private_separators`、`query_credentials`、`test_log_redaction.py`、`fixtures/log_redaction_443e95a.py` 都 0。
- 字面 64 位 hex：只在 `test_log_redaction_query_credentials.py`（1 行）與 `…_review.py`（7 行）。
- 這兩個檔與 `private_separators`、`test_log_redaction.py` 不是純測試（要 PaaS 的 `routers.logs`／FastAPI 或起 PaaS 的 app），
  不帶進來；它們的情境由 `tests/test_redaction_matrix.py` 涵蓋（HM-00 `paas-test-mapping.md` 也這樣歸屬）。
- 所以帶進來的 4 個純測試：0 個字面 64 位 hex、0 個命中、**0 項改動**（連 import 都不用改：本來就是
  `from mcp_admin_core import log_redaction`）。

## 5. Release train（UC-29、C4-SF-9）

- 結論：**不比對新 vendored 的檔，不擋。**
- 讀過的來源（GitHub 鏡像 `WOOWTECH/woow-release-train` main `1f80663`，和 Gitea `woow-paas/woow-release-train` main 相同）：
  `.github/workflows/wvt-check.yml`、`woow-versions.yaml`、`tools/wvt.py`。
- `wvt check --leg ha` 只看清冊裡這個 repo 的釘點：n8n 的 `package.json`／lock、odoo 的 `pyproject.toml`／`uv.lock`、
  `runtime-sources.json` 裡 litellm、hermes、emqx、nextcloud 的紀錄（依 `product` 篩）、litellm 與 nextcloud vendor 的
  `__version__`、5 個子程式的 `mcp` 版本。沒有任何釘點指到 `packages/mcp-admin-core/`；`woow-mcp-server` 產品只有 paas 腿；
  `shared_files` 的消費者是別的 repo（`Woow_ha_litellm`）。
- 離線實跑（`python3 -I tools/wvt.py check --leg ha --repo github:WOOWTECH/Woow_ha_mcp_addons`，對 `32ecac8` 與本分支 head
  的 `git archive`）：兩邊輸出與 JSON 完全相同，17 個釘點、通過、0 個會擋、1 個既有警告（nextcloud 的 `json_select` 有兩個
  不同來源 commit，本片沒動）。
- 注意：若之後把這個檔加進 `runtime-sources.json`，只要 `product` 不是清冊用的名字，`json_select` 也比對不到。

## 6. PaaS 變動清單（DQ-06）

- 2026-11-15 00:4x fetch：`origin/main`＝`cf3d0d5`（#151，移除 VK）。`7d111b1..origin/main` 共 5 個 commit。
- `log_redaction.py`：沒有變動（`git diff 7d111b1 origin/main` 0 行）。
- 遮罩測試：只有 `f5223be` 改 `test_log_redaction.py` 的 APPS 清單（拿掉 vk，端到端測試，本片沒有帶進來）；4 個純測試沒變。
- HM-00 基準文件第 4 節的清單：`36bde7b` 刪 `apps/vk/vk_mcp_admin/main.py`、改 `docs/paas-config-restore-runbook.md`；
  `8bfb12e` 改 `apps/opendesign/opendesign_mcp_admin/main.py`、`setup_status.py` 的註解。都和 HM-02 無關（HA 沒有 VK）。
- 本片仍以 `7d111b1` 為準。

## 7. 新測試與先紅後綠

`tests/test_redaction_matrix.py`（86 案；5 個地方＝訊息、參數、例外、uvicorn access record、子程式輸出）：

| 群組 | 案例 |
|---|---|
| 輸入釘選 | vendored 模組與 4 個 PaaS 測試的 SHA-256、帳本那一筆；bb48449 凍結檔；97 種寫法的數量與分組（和 harness、PaaS 的清單逐項相同）；#149 回報的鍵名都在清單裡 |
| 門檻（即時算） | 97 種寫法 × 3 種形式 × 2 種 token × 5 個地方：HA 露的 ⊆ pin 版 PaaS 露的；query 值的 97 種寫法 × 4 個鍵名 × 2 種網址 × 2 種結尾 × 3 種形式（4656 行）同樣比 |
| 不退步 | 同樣的語料：HA 露的 ⊆ bb48449 露的 |
| #149 | 189 種鍵名拼法 × 8 種樣板，5 個地方全遮；一般參數（`keys`、`key_id`、`token_type`、`signature_version`…）照常可讀 |
| 順序 | PaaS 先、HA 後的例子；反過來的順序在語料上會露 PaaS 遮得住的；`install()` 編好 pattern、不掛 PaaS 的 logger filter，經 logger 送出的 1500 多行都不露 |
| HA 格式與 `key=` | `/private_[REDACTED]`、`[REDACTED]` 不變，bb48449 會遮的子程式行輸出逐字相同；`key=` 13 種寫法遮、10 種相似字不遮；`key=` 規則在最後 |
| 守門 | 4 個反例：bb48449 藏住的照樣藏住，單純組合會露的地方都換成 placeholder；access record 維持 5 個參數；`shows_hidden` 與 `apply_rules` 的 9 個判斷；病態形狀的時間上限 |
| 穩定 | 語料再遮一次不會多露，第二次起不變 |
| 差分 fuzz | 2 個種子 × 1200 行 × 5 個地方：bb48449 或 pin 版 PaaS 藏住的值都藏住；bb48449 藏住 ≥ 200、PaaS 藏住 ≥ 200（確認有咬合） |

先紅後綠（同一份新測試、vendored 模組與帳本，只把 `redact.py`、`diagnostics.py` 換回 `32ecac8`＝bb48449）：

| | bb48449 的遮罩 | 本片 |
|---|---|---|
| `tests/test_redaction_matrix.py` | 43 失敗（38 個斷言、5 個是新函式不存在）、43 通過 | 86 通過 |
| `tests/vendor_paas/` | 574 通過（只測 PaaS 模組本身） | 574 通過 |

bb48449 上仍通過的 43 案：輸入釘選、「不比 bb48449 差」（拿自己比自己）、一般文字可讀、反向順序、時間上限等。

## 8. 本機檢查

| 檢查 | 結果 |
|---|---|
| `tests/test_redaction_matrix.py` | 86 通過，約 18 秒 |
| `tests/vendor_paas/` | 574 通過，約 27 秒 |
| 新測試＋相關既有測試，照 repo 的 conftest 在同一個程序跑（新測試與 PaaS 測試排在前面；既有的是 `test_secret_path`、`test_child_diagnostics`、`test_log_scan`、`test_nextcloud_error_secrets`、`test_raw_backend_errors`、`test_n8n_mcp_access_token`、`test_owner_defaults`、`test_hermes_config_redaction`、`test_claude_ai_connector`、`test_tool_inventory`、`test_ledger_precheck`、`test_secret_precheck`，與 HM-01 的三個凍結測試） | `f16b041`：1011 通過、1 失敗（`test_real_uvicorn_logs_never_show_the_secret`，原因是 PaaS 測試留下的 `uvicorn.error` 狀態，見第 2 節 conftest 一列）；修正後 `d9b3b20`：1012 通過、0 失敗、0 skip，232 秒 |
| 全套 pytest（`flock wave1-pytest.lock`，短 TMPDIR；`d9b3b20`） | 4392 案（HM-01 的 3732＋本片 660）：4369 通過、23 失敗、0 skip，29 分 05 秒。23 個都和本片無關：1 個是已知要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`；22 個是瀏覽器測試（`test_owned_browser_ipc.py::test_terminal_coalesced_proof` 5 案、`test_owned_browser_redirect.py::test_chromium_redirect_denied_before_fulfill` 16 案、`test_owned_ui.py::test_standalone_ownership_boundaries[browser]`），失敗訊息都是 `browserType.launch: Executable doesn't exist`：這個 clone 沒有裝 Playwright 的 Chromium（`setup_repo_env.sh` 不跑 `npm run browser:install`，CI 的 `packaging/unit.sh` 會跑）。 |
| `packaging/validate.py` | PASS |
| packaging unittest | 184 案 OK（5 skip，要 root）；`test_container_probe`、`test_denial_probe` 要 httpx，用 repo 的 `.venv` 跑 |
| `scripts/tool_inventory.py`（漂移檢查） | 通過 |
| 秘密預檢 `scripts/secret_precheck.py` | `--base 32ecac8`：本片 4 個 commit（含本筆記）0 命中；`--full`：本分支 13 個 commit、HEAD 原始碼、全歷史 0 命中 |
| 帳本預檢 `scripts/ledger_precheck.py` | `runtime-patches` 153、`runtime-sources` 70、`tool-surface` 159，0 漂移、0 缺檔；列管檔 `log_redaction.py` 與帳本同 PR；`redact.py`、`diagnostics.py` 列為「要人看」（不列管，見第 2 節） |
| Release train 離線檢查 | base 與 head 相同，通過（第 5 節） |
| 本機差分 fuzz（實驗，不在 repo；產生器和測試內的相同） | 最終版本：種子 11～14、21～24 各 5 萬行，共 40 萬行 × 3 個地方（訊息、參數、子程式輸出），0 違反；守門改成 placeholder 的比例：紀錄約 0.05%、子程式輸出約 1.4%（fuzz 刻意造怪行） |

## 9. 只在 CI 跑的測試

- pytest 在 CI 以 root（`sudo`）跑；本機是一般使用者。已知只在本機失敗的是 `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root）。
- packaging unittest 裡 5 個要 root 的案例（本機 skip）。
- UI：`npm test`、build closure、Playwright 瀏覽器測試（本片沒改 UI，本機沒跑）；pytest 裡要 Chromium 的 22 案（第 8 節）本機沒有瀏覽器，只在 CI 跑。
- Release train（`wvt-check.yml`）、`readiness`、`Upgrade comparison / compare`：GitHub 上跑；Release train 已離線實跑（第 5 節）。
- `checks` 前後秒數：開 PR 後補。

## 10. 本片用到的決策（主對話之後同步到 `docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| DQ-38 | (a) 原樣 vendor；使用者 2026-11-14 21:5x 確認 PaaS 的 `log_redaction.py`（#149 合併版）與純測試可以公開放進 HA 的公開 repo | 三個前提都滿足：使用者確認、先跑秘密預檢（第 4 節）、Release train 不比對（第 5 節） |
| DQ-06 | 對齊基準含 #149；之後的 PaaS 變動每片列出 | 以 `7d111b1` 為準；`cf3d0d5` 的變動列在第 6 節 |
| §13.1（15 項建議全採用） | 使用者合併、不改版號、HA 不加 AI 署名、PR 標題前綴、本機短 TMPDIR 用完刪、以 GitHub CI 為準 | commit 沒有 AI 署名；不 push、不開 PR（這一波的規則） |

沒有用到 DQ-09、DQ-12、DQ-19；沒有碰到 §13.2、§13.3 還沒問的題目。

## 11. 驗收條件（計畫 §12.3 HM-02）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 未驗證：這一波不 push；本機見第 8 節 |
| 新測試在 bb48449 的遮罩上會失敗、改完通過 | 達成：43 失敗 → 86 通過（第 7 節） |
| 既有測試 0 修改 | 達成：`git diff 32ecac8 --stat` 只有新檔與 `redact.py`、`diagnostics.py`、`runtime-patches.json` |
| `[REDACTED]` 格式不變 | 達成：`/private_[REDACTED]`、`[REDACTED]`、`Bearer [REDACTED]`、`token=[REDACTED]`、`http://[REDACTED]@` 照舊；bb48449 會遮的子程式行輸出逐字相同（`test_the_ha_forms_are_unchanged`） |
| 秘密預檢 0 命中 | 達成（第 8 節） |
| （做法）vendored 檔記進 `runtime-sources.json` | **沒做到**：見第 12 節第 1 點，改記在 `runtime-patches.json` |

## 12. 待辦與未解

1. **`runtime-sources.json`（要主對話或使用者決定）**：計畫、HM-00 `ledger-tracking.md` 與這一波的指示都說 vendored 檔記進
   `runtime-sources.json`。但那本帳的每一筆都被當成 `apps/<product>/vendor/<path>`：`tests/test_tool_inventory.py::test_vendored_content_hashes_and_license_notices`
   照這個路徑讀檔比 SHA-256，`scripts/ledger_precheck.py` 也一樣。加一筆 `packages/mcp-admin-core/…` 會讓既有測試失敗，
   要過就得改既有測試（違反「既有測試 0 修改」）。本片先把來源 repo、commit、路徑、SHA-256 寫在 `runtime-patches.json` 那一筆的
   `change`，並由 `tests/test_redaction_matrix.py` 釘住。可選：(a) 維持這樣；(b) 另開一片擴充 `runtime-sources.json` 的格式並同步改
   `test_tool_inventory.py` 與 `ledger_precheck.py`。
2. `checks` 前後秒數：開 PR 後補。
3. DQ-38 的「已定」與本片用到的決策，主對話開 PR 時同步到 `docs/multi-profile/decisions.md`（本分支沒有 `docs/multi-profile/`）。
4. `THIRD_PARTY_NOTICES.md` 沒改：woow-mcp-server 是 WOOWTECH 自己的 repo，使用者已確認可公開；已經 vendor 的 Headscale 檔
   （同一來源）也沒列在那裡。要列的話另外處理。
5. 子程式輸出補遮 `key=` 會多遮一般文字裡的 `key: value`、`"key": …`（例如 `cache key: x`）；只影響診斷頁顯示。
6. HM-08 的回覆遮罩聯集（§5.1 第 8 點、DQ-40）不在本片。
7. 本機環境：`setup_repo_env.sh` 沒有 `npm run browser:install`，這個 clone 沒有 Playwright 的 Chromium，pytest 的 22 個瀏覽器測試
   在本機一定失敗（和本片無關）。要在本機跑，得在腳本加這一步（會從 Playwright 下載 Chromium）。
