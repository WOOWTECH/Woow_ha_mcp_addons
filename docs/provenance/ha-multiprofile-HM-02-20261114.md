# HA 多帳號 HM-02 provenance：紀錄遮罩對齊 PaaS（含 #149，原樣 vendor）（2026-11-15）

## 結論

- 範圍：原樣 vendor PaaS 的 `log_redaction.py`（woow-mcp-server main `7d111b1`，#149 合併版）與它的 4 個純測試；
  HA 的紀錄遮罩（record factory、`RedactSecretPaths`）與子程式輸出遮罩改成「PaaS 規則先、HA 規則後」；子程式輸出補遮
  `key=`。沒改版號、`addons/<x>/`、CHANGELOG、workflow、`apps/`、UI。
- 97 種密鑰網址寫法（原樣／解碼／access 寫法，兩種 token）：bb48449 在紀錄裡漏 10／40／4、子程式輸出漏 9／39／3；
  改完 5 個地方都是 1／22／0，和 pin 版 PaaS 一樣（門檻在測試當下用 PaaS 模組算），沒有任何一種寫法比 bb48449 退步。
- #149 的 query 憑證：27 個鍵名加 `token`、`access_token`，共 189 種拼法 × 8 種樣板，5 個地方全部遮住
  （bb48449 在紀錄裡 1512 個全露、子程式輸出露 528 個）。
- 單純「PaaS 先、HA 後」在少數寫法會露出 bb48449 原本藏住的值，由 `redact.shows_hidden` 守門：結果露出「HA 規則單獨
  會藏住」的片段，就整段改成 PaaS 的 `[redacted: ambiguous URL encoding]`（fail closed）。
- **獨立安全審查（2026-11-15 第 2 次，判定「修正後通過」）後的修正**：
  - MF-1：守門原本只比 4 個字元以上的英數片段，密碼這類「短片段＋符號」的值看不到。現在另外比 2、3 個字元的視窗
    （任何字元，最多一個不是英數）。審查的 fuzz 露出 3590 → 0；擴大的 fuzz 120 萬次比對剩 1 次、只露一個字母
    （第 3.2 節的保證範圍）。紀錄那一路也有同樣的洞（擴大 fuzz 3 個種子露 155 個），一起補上。
  - MF-2：守門改用 vendored 模組自己的解碼（`log_redaction._unquote`），原文、結果、被藏的值各只解碼一次。病態
    8 KiB 子程式行 64.6 → 18.2 ms、128 KiB 紀錄 1196 → 491 ms（第 3.3 節）。時間上限改成 PaaS 單獨耗時的相對倍數。
  - SF-1：子程式輸出遮罩失敗時不再丟例外，整行換成 `line withheld (redaction failed)`。
  - SF-2：補上變異沒擋下的 3 個測試缺口；本輪 19 個變異（第 7 節）。
- 先紅後綠：`tests/test_redaction_matrix.py` 107 案。換回 bb48449 的遮罩，61 案失敗；換回審查前（`37fe574`）的
  遮罩，14 案失敗（都是本輪新增的）；改完全過。vendored PaaS 測試 574 案全過。
- 既有測試 0 修改；`[REDACTED]` 格式不變；秘密預檢 0 命中；帳本預檢 0 漂移。本機全套 pytest 見第 8 節。
- Release train 不比對新 vendored 的檔，不擋（第 5 節）。
- **要主對話決定或確認**（第 12 節）：MF-3 `runtime-sources.json` 的記法（本片維持記在 `runtime-patches.json`）；
  MF-4 上一輪作者的兩次唯讀遠端讀取（Gitea fetch、GitHub API）要不要接受；vendored 計時測試若在 CI 偶發失敗怎麼處理；
  `THIRD_PARTY_NOTICES.md` 要不要註記。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-02（計畫 §8.6、§12.3；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm02-20261114`（本機；這一波不 push、不開 PR） |
| HA 基準 | HM-01 分支 head `32ecac8`（＝`bb48449`＋HM-01，PR #90 等合併）；`redact.py`、`diagnostics.py` 在 `32ecac8` 與 `bb48449` 逐位元相同 |
| 對齊的 PaaS | `WOOWTECH/woow-mcp-server` main `7d111b175fbbcdf692ff579cc5793bf8c7de3a7b`（#149 合併）；上一輪 fetch 時 `origin/main`＝`cf3d0d5`（第 6 節） |
| 依據 | 計畫 §8.6、§11.1、§12.0、§12.3「HM-02」；HM-00 `ledger-tracking.md`、`paas-test-mapping.md`、`acceptance-matrix.md`（T-25、`tests/test_redaction_matrix.py` 登記列） |
| FM | FM-75（另含 FM-65 的 `?key=`） |
| 審查 | 獨立安全審查（2026-11-15 第 2 次，審 `37fe574`，判定「修正後通過」；報告路徑附在 PR 說明）；處理見第 13 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/log_redaction.py`（新） | PaaS `7d111b1` 同路徑的檔，逐位元相同（SHA-256 `1fec42aab78201e5c2bd892586e19ee640f0214905189ff9dbfea29d729b1f91`）。本 repo 不改它；PaaS 之後再改就整檔同步。 |
| `packages/mcp-admin-core/mcp_admin_core/redact.py` | `scrub()`：先 `log_redaction.scrub_record`，再照舊套 HA 規則，最後 `_fail_closed`。`scrub_text()`：子程式輸出用，同樣的組合與守門，失敗時回 `LINE_WITHHELD`、不丟例外（SF-1）。守門 `shows_hidden()`：比 `PIECE`（4）個字元的英數片段與 `WINDOWS`（2、3）個字元的視窗（MF-1）；`_forms()` 用 `log_redaction._unquote` 解碼（MF-2）。其他新名稱：`PATH_RULES`、`apply_rules`、`_windows`、`_parts`、`_not_shown`、`LINE_WITHHELD`。`install()` 先編好 PaaS 延遲編譯的 pattern。`redact()`、`leaks()`、`REDACTED`、`SECRET_MASK`、`secret_values`、`redact_secrets` 不變。 |
| `packages/mcp-admin-core/mcp_admin_core/diagnostics.py` | `scrub_line()`：已知秘密換掉之後，`redact.scrub_text(text, RULES)`；整段包起來，失敗時回 `redact.LINE_WITHHELD`（SF-1）。`RULES`＝bb48449 的四條規則（`PRIVATE_SEGMENT`、`AUTH`、`ASSIGNMENT`、`USERINFO`，regex 與順序都不變）＋新的 `KEY`。 |
| `docs/provenance/runtime-patches.json` | 新增 `log_redaction.py` 一筆（`sha256`、`change` 寫來源 repo、commit、路徑、SHA-256；`guarded_sources` 是 `{}`）。 |
| `tests/vendor_paas/test_log_redaction_{encoded_boundaries,linear,segments,single_pass}.py`（新） | PaaS `7d111b1` 的 `packages/mcp-admin-core/tests/` 同名檔，逐位元相同（574 案）。 |
| `tests/vendor_paas/conftest.py`、`__init__.py`（新，HA 寫的） | 每個 PaaS 測試前換回標準 record factory、拿掉 HA 的 `RedactSecretPaths`；跑完還原 record factory、每個 logger 與 handler 的 filter，以及 root 以外每個 logger 的 level、propagate、handler（測試中才建立的 logger 回到剛建立的樣子）。兩個方向都需要：沒有前半，`test_secret_path.py::test_real_uvicorn_logs_never_show_the_secret` 之後有 2 個 PaaS 測試失敗；沒有後半，PaaS 測試排在前面時那個 HA 測試失敗（PaaS 的 `test_log_redaction_linear.py` 借用 `uvicorn.error` 後留下 INFO、不往上傳）。 |
| `tests/test_redaction_matrix.py`（新，107 案） | 見第 7 節。所有案例都在 HM-01 的 `log_scan` 下跑。 |
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

- 問題：組合有兩種方式會露出 HA 規則單獨會藏住的值（都有測試）。
  1. PaaS 的解碼後規則遮到東西時，它回整行解碼後的字串；HA 規則接著停在解碼出來的空白、引號、逗號、`@`、`/`。
     例：`/private_abc?a=1%20<T>&token=%2Fv` 露出 `<T>`；`password=x7%20Kq%219z /x?token=%2Fv` 露出 `Kq!9z`；
     `url http://u:p%20q%20r@h.invalid/?token=%2Fv` 露出整段 userinfo。
  2. PaaS 的遮罩吃掉 HA 規則需要的字，或在 HA 規則不停的地方停下。例：`/x?token=abc/private_<T>#<V>/x`（PaaS 的值停在
     `#`，HA 卻把 `#<V>` 當成同一段密鑰路徑）；`http://user:<T>&key=@host/x`（PaaS 遮 `&key=@…` 吃掉 userinfo 的 `@`）；
     `;access_token=Basic HJ#P…`（PaaS 把 `Basic` 遮成 `***`，AUTH 規則就看不到後面的值）；`&key=cookie: H;L`。
- 做法：同一段原文，用 HA 規則單獨套一次（`alone`），記下被換掉的值。組合後的結果（`shown`）若有「`alone` 沒顯示、
  而被藏的值裡有」的片段，就整段改成 placeholder。片段有兩種：
  - `PIECE`：4 個字元以上連續的英數、`_`、`-`（原本的設計；和 `redact.MIN_SECRET` 一樣）。
  - `WINDOWS`（審查 MF-1 後新增）：2 或 3 個連續字元，任何字元都可以，但最多一個不是英數。密碼、`user:pw` 這類由
    1～3 個字元加符號組成的值沒有 4 個字元的片段，靠這個看得到。
  - 為什麼這樣判斷是對的：組合只會拿掉文字（遮罩）或把整行解碼，`alone` 也用原樣與解碼後兩種比；所以結果裡
    `alone` 沒有的片段，只可能來自 `alone` 藏住的文字，視窗再小也不會因為巧合多擋（測試語料與一般行的 placeholder
    數沒有增加，見下）。只看結果裡 `alone` 沒有原樣出現的部分（遮罩之間的文字），被藏的值只在需要時才組。
  - 紀錄裡分別看訊息、例外文字、stack；uvicorn access record 維持 5 個參數，先換 path，不夠再換其他字串參數（和 PaaS 相同）。
- **實際保證範圍**（取代上一版「40 萬行、0 違反」的說法；那只對當時的長值產生器成立）：
  - 看得到：被藏的值露出 4 個字元以上的英數片段，或任何 2、3 個字元（最多一個非英數）的片段，而且 `alone` 別處沒有
    原樣或解碼後顯示同樣的片段。
  - 看不到：只露出一個英數字元、它旁邊的字元 `alone` 也顯示（例：`/private_U+Y%20GR?token=a%2Fb%27N'N/mcp` 多露一個
    `N`，旁邊緊接著 `alone` 也顯示的 `'N`）；露出的片段剛好 `alone` 在別處也顯示（照原設計允許）。
  - 實測（值都是合成的；腳本與結果留在本機暫存區）：

| 語料 | 範圍 | 37fe574（審查前） | 審查原型 | 本片 |
|---|---|---|---|---|
| 審查 MF-1 的 fuzz（`x04`：13 種子程式樣板 × 6 種觸發，2 萬行） | bb48449 藏住 18583 個值 | 露 3590 | 露 0 | 露 0 |
| 擴大 fuzz（加字面分隔字元、PaaS 遮罩觸發、觸發放在值裡；3 個種子 × 2 萬行） | 子程式 43962、紀錄各 14801 | 子程式 3083、紀錄 155／155 | 子程式 1614、紀錄 155／155 | 0／0／0 |
| 同上，20 個種子（101～120）× 2 萬行 × 3 個地方 | 子程式 293860、紀錄各 98891 | — | — | 子程式 1（只露一個字母）、紀錄 0 |
| 測試自己的長值 fuzz（種子 11～14 × 5 萬行 × 5 個地方） | 每個地方 1.5～3.6 萬個值 | — | — | 0 退步、0 比 PaaS 差 |
| placeholder：測試語料 6750 行（子程式） | | 339 | 339 | 339 |
| placeholder：測試 fuzz 2400 行（刻意造怪行） | | 604 | 610 | 635 |
| placeholder：一般子程式行 8 行 | | 0 | 0 | 0 |

  - 審查原型（`_decoding_shows_hidden`：只看「解碼後整段原樣出現在 PaaS 結果裡」的值）沒有採用：上面第 2 種情況它看不到，
    而且只加在子程式那一路，紀錄那一路的洞還在。本片在試做時也加過結構式的解碼檢查，視窗之外沒有多擋任何一行，所以沒有放進來。
  - 測試 fuzz 的 placeholder 比審查前多 31 個：本片比審查原型多擋 29 行、少擋 4 行。多擋的 29 行裡，19 行是原型會露出 bb48449
    藏住的部分（照審查的算法），其餘是 `key=` 規則（新的，bb48449 沒有）藏住的值的尾巴（`?key=…%20/mcp` 的 ` /mcp`）；少擋的
    4 行，本片的結果沒有露出 bb48449 藏住的部分（原型多擋）。
- `key=` 是最後一條規則，不併進 `ASSIGNMENT`：併進去會先把 `key=…@` 換掉，前面的 userinfo 就露出來（守門的對照組用到
  bb48449 的規則，所以 bb48449 的四條規則維持原樣、原順序）。
- 為什麼不改成「HA 先」或「兩種都算再選」：HA 先會讓 PaaS 看不到密鑰路徑原本的形狀（97 種寫法的 291 行裡，15 行 PaaS 遮得住、
  HA 先就露）；兩種都算也找不到同時「不比 PaaS 差」又「不比 bb48449 差」的保證，只有 placeholder 兩邊都滿足。

### 3.3 效能

- 線性：原文只看到 PaaS 自己的上限 `MAX_REDACT_CHARS`（128 KiB；PaaS 顯示的內容也不超過這段）；只看結果裡 `alone` 沒有
  原樣出現的部分；片段少時用子字串搜尋，多時改用集合；被藏的值只在需要時才解碼、組起來。
- 解碼用 `log_redaction._unquote`（vendored 模組為了效能寫的 C 層版本，和 `urllib.parse.unquote(errors="replace")` 逐字
  相同；測試在 2 萬筆產生的字串上核對）。原本用 stdlib `unquote`，守門比 PaaS 單獨慢 4～6.5 倍（審查 MF-2）。
- 本機量測（取 3 次最好，ms；這台機器同時有其他代理在跑測試，數字有少量雜訊；比值以同一程序量的 PaaS 單獨為準）：

| 形狀 | bb48449 | PaaS 單獨 | 37fe574 | 本片 |
|---|---|---|---|---|
| 子程式行 8 KiB：`/private_x`＋14 輪編碼的跳脫＋`?sig=abc`＋大量 `%` | 0.8 | 9.7 | 64.6 | 18.2 |
| 子程式行 8 KiB：`password=Kx`＋同上 | 0.8 | 6.4 | 61.3 | 14.4 |
| 紀錄 128 KiB：`/private_x`＋14 輪編碼＋`?token=abc`＋大量 `%` | 0.1 | 314 | 1196 | 491 |
| 紀錄 128 KiB：同上，`?sig=abc` | 0.1 | 291 | 1184 | 406 |
| 紀錄 128 KiB：2 萬個短密鑰路徑（`/private_abc%2x`） | 2.7 | 4.1 | 18.8 | 9.8 |

- 一般的行（中位數）：子程式 0.03～0.12 ms（bb48449 0.01～0.03 ms、PaaS 單獨 0.004～0.04 ms），紀錄 0.02～0.09 ms（PaaS
  單獨 0.01～0.08 ms）。
- `test_the_guard_is_bounded_on_pathological_lines`：7 種形狀（原本 4 種＋審查的 3 種），紀錄與子程式行分開量，上限是
  「同一段文字 PaaS 單獨耗時 × 3 ＋ 30 ms」（即時量，不寫死）。本機最緊的一格是 128 KiB 的 `?token=` 形狀（491 ms，上限
  約 970 ms）。換回 stdlib `unquote` 時這個測試失敗（紀錄 1196 ms＞約 970 ms）。
- PaaS 模組本身在「深層編碼＋大量 `%`」的形狀成本也高（審查 SF-4）：64 KB 76.6 ms、16 KB 19.7 ms（線性、常數大），超過 PaaS
  自己線性測試對它那 48 種形狀的 50 ms 標準（這個形狀不在它的清單裡）。HA 原樣 vendor 改不了，列進給 PaaS 的回補建議
  （第 12 節）。

### 3.4 顯示上的變化（不是退步）

- 紀錄裡的 query 憑證值顯示 PaaS 的 `***`（bb48449 不遮）；HA 原有的 `[REDACTED]`、`/private_[REDACTED]` 格式不變。
- PaaS 判斷不了編碼的行，或守門擋下的行，顯示 `[redacted: ambiguous URL encoding]`；PaaS 超過 128 KiB 的字串截斷並加
  `…[truncated N chars]`。
- 子程式輸出遮罩失敗（目前找不到會觸發的輸入）時顯示 `line withheld (redaction failed)`。
- 格式字串和參數對不上的 record（`logging.warning('%s %s', 'a')`）：bb48449 顯示 `log record withheld (redaction failed)`，
  現在先由 PaaS 換成 `[redacted: invalid log message]`。兩者都不顯示內容；沒有測試依賴前者的文字。
- 第一次遮罩可能留下 `/private_[REDACTED]\***`（PaaS 把 `/private_` 後的反斜線當雜訊留下，HA 規則停在反斜線），
  第二次遮罩（`RedactSecretPaths`）變成 `/private_[REDACTED]`。兩種都不露值，第二次起穩定（`test_composition_is_stable_on_the_corpora`）。
- 子程式輸出補遮 `key=` 會多遮一般文字裡的 `key: value`、`"key": …`（例如 `cache key: x`）。

## 4. vendor 前的秘密預檢、測試改動與授權

- 工具：本 repo 釘的 gitleaks 8.28.0（`scripts/secret_precheck.py install` 從 `packaging/scanner-pins.json` 核對過的壓縮檔裝），
  設定是 `packaging/supply_chain.py` 的 `gitleaks_config()`，對 repo 外的 `7d111b1` 檔案目錄跑（只印規則、檔名、行號）。
- 結果：33 個命中，全部在 `test_log_redaction_query_credentials_review.py`（generic-api-key 30、jwt 3）；`log_redaction.py`、
  4 個純測試、`private_separators`、`query_credentials`、`test_log_redaction.py`、`fixtures/log_redaction_443e95a.py` 都 0。
- 字面 64 位 hex：只在 `test_log_redaction_query_credentials.py`（1 行）與 `…_review.py`（7 行）。
- 這兩個檔與 `private_separators`、`test_log_redaction.py` 不是純測試（要 PaaS 的 `routers.logs`／FastAPI 或起 PaaS 的 app），
  不帶進來；它們的情境由 `tests/test_redaction_matrix.py` 涵蓋（HM-00 `paas-test-mapping.md` 也這樣歸屬）。
- 所以帶進來的 4 個純測試：0 個字面 64 位 hex、0 個命中、**0 項改動**（連 import 都不用改：本來就是
  `from mcp_admin_core import log_redaction`）。
- 授權（審查 SF-5）：上游沒有宣告授權（PaaS `packages/mcp-admin-core/pyproject.toml` 沒有 license 欄位，repo 根目錄沒有
  LICENSE）。woow-mcp-server 是 WOOWTECH 自己的 repo，擁有者在 DQ-38 同意把這個模組與純測試公開放進本 repo，所以以本 repo
  的授權（Apache-2.0）發佈。`THIRD_PARTY_NOTICES.md` 沒改：它列的是第三方程式；同一來源的 Headscale vendor 檔另附
  MIT `LICENSE`，是因為那個上游 app 自己宣告了 MIT，這裡上游沒有宣告。要不要另外註記，由主對話定（第 12 節）。

## 5. Release train（UC-29、C4-SF-9）

- 結論：**不比對新 vendored 的檔，不擋。**
- 讀過的來源（GitHub 鏡像 `WOOWTECH/woow-release-train` main `1f80663`，和 Gitea `woow-paas/woow-release-train` main 相同）：
  `.github/workflows/wvt-check.yml`、`woow-versions.yaml`、`tools/wvt.py`。
- `wvt check --leg ha` 只看清冊裡這個 repo 的釘點：n8n 的 `package.json`／lock、odoo 的 `pyproject.toml`／`uv.lock`、
  `runtime-sources.json` 裡 litellm、hermes、emqx、nextcloud 的紀錄（依 `product` 篩）、litellm 與 nextcloud vendor 的
  `__version__`、5 個子程式的 `mcp` 版本。沒有任何釘點指到 `packages/mcp-admin-core/`；`woow-mcp-server` 產品只有 paas 腿；
  `shared_files` 的消費者是別的 repo（`Woow_ha_litellm`）。
- 離線實跑（`python3 -I tools/wvt.py check --leg ha --repo github:WOOWTECH/Woow_ha_mcp_addons`，對 `32ecac8` 與當時分支 head
  的 `git archive`）：兩邊輸出與 JSON 完全相同，17 個釘點、通過、0 個會擋、1 個既有警告（nextcloud 的 `json_select` 有兩個
  不同來源 commit，本片沒動）。審查修正只改 `packages/mcp-admin-core/` 與 `tests/`，不影響這個結論。
- 注意：若之後把這個檔加進 `runtime-sources.json`，只要 `product` 不是清冊用的名字，`json_select` 也比對不到。
- **取得方式與規則例外（審查 MF-4，要主對話確認）**：上面的 3 個檔是上一輪作者在 2026-11-15 00:49～00:50 從
  `api.github.com` 下載的（`WOOWTECH/woow-release-train` commit `1f80663` 的 commit 與 tree 回應，再取這 3 個檔；
  11-14 22:09 也下載過一份 commits 清單），`tools/wvt.py` 是在本機離線執行（`python3 -I`）。都是唯讀；審查沒有看到憑證外流
  的跡象。這一波的規則是「只在本機跑、不連遠端，違反就停下回報」，當時沒有標成例外，也沒有停下回報。本輪（處理審查
  意見）沒有任何連線，也沒有再執行下載的程式。接受的話本節結論沿用；不接受的話，開 PR 時在允許連線的步驟重做。

## 6. PaaS 變動清單（DQ-06）

- 2026-11-15 00:43～00:48（上一輪作者）從 Gitea（`git-prod.woowtech.io/WOOWTECH/woow-mcp-server`）fetch：
  `origin/main`＝`cf3d0d5`（#151，移除 VK）。`7d111b1..origin/main` 共 5 個 commit。
- `log_redaction.py`：沒有變動（`git diff 7d111b1 origin/main` 0 行）。
- 遮罩測試：只有 `f5223be` 改 `test_log_redaction.py` 的 APPS 清單（拿掉 vk，端到端測試，本片沒有帶進來）；4 個純測試沒變。
- HM-00 基準文件第 4 節的清單：`36bde7b` 刪 `apps/vk/vk_mcp_admin/main.py`、改 `docs/paas-config-restore-runbook.md`；
  `8bfb12e` 改 `apps/opendesign/opendesign_mcp_admin/main.py`、`setup_status.py` 的註解。都和 HM-02 無關（HA 沒有 VK）。
- 本片仍以 `7d111b1` 為準。
- **取得方式與規則例外（審查 MF-4，要主對話確認）**：這次 fetch 和第 5 節的下載同屬上一輪、同樣沒有標成例外。計畫 §11.1 本來就
  要求「`git log <pin>..origin/main -- <PaaS 相關檔>` 在連得到 Gitea 的地方跑」；開 PR 時（rebase 到 claude-delivery 之後）
  在允許連線的步驟重跑一次，把結果更新到本節。本輪沒有連線。

## 7. 新測試與先紅後綠

`tests/test_redaction_matrix.py`（107 案；5 個地方＝訊息、參數、例外、uvicorn access record、子程式輸出）：

| 群組 | 案例 |
|---|---|
| 輸入釘選 | vendored 模組與 4 個 PaaS 測試的 SHA-256、帳本那一筆；bb48449 凍結檔；97 種寫法的數量與分組（和 harness、PaaS 的清單逐項相同）；#149 回報的鍵名都在清單裡 |
| 門檻（即時算） | 97 種寫法 × 3 種形式 × 2 種 token × 5 個地方：HA 露的 ⊆ pin 版 PaaS 露的；query 值的 97 種寫法 × 4 個鍵名 × 2 種網址 × 2 種結尾 × 3 種形式（4656 行）同樣比 |
| 不退步 | 同樣的語料：HA 露的 ⊆ bb48449 露的 |
| #149 | 189 種鍵名拼法 × 8 種樣板，5 個地方全遮；一般參數（`keys`、`key_id`、`token_type`、`signature_version`…）照常可讀 |
| 順序 | PaaS 先、HA 後的例子；反過來的順序在語料上會露 PaaS 遮得住的；`install()` 編好 pattern、不掛 PaaS 的 logger filter，經 logger 送出的 1500 多行都不露 |
| HA 格式與 `key=` | `/private_[REDACTED]`、`[REDACTED]` 不變，bb48449 會遮的子程式行輸出逐字相同；`key=` 13 種寫法遮、10 種相似字不遮；`key=` 規則在最後 |
| 守門 | 4 個長值反例；access record 維持 5 個參數；`shows_hidden` 與 `apply_rules` 的判斷；PIECE 片段、3 個字元的視窗各自看得到的例子；stack_info 也守；兩層編碼要解兩輪才看得到的值 |
| 短值（審查 MF-1） | 7 個反例（審查的 4 個＋擴大 fuzz 找到的 3 個：PaaS 遮掉 `Basic`、遮掉 `cookie:`、只露一個字母）：先確認 bb48449 藏住、單純組合會露，再確認結果是 placeholder；紀錄的 4 個地方不比 bb48449 差。短值差分 fuzz：2 個種子 × 1500 行 × 5 個地方，算法照審查（值的任 3 個連續字元、其中 2 個是值的字母），bb48449 或 pin 版 PaaS 藏住的都藏住 |
| 一般行 | PaaS 回解碼後字串的一般子程式行照常可讀（4 行，輸出逐字釘住） |
| 解碼與效能（審查 MF-2） | `_forms` 用 `log_redaction._unquote`、輪數和 PaaS 一樣；`_unquote` 和 stdlib 在 2 萬筆產生的字串上相同；病態形狀的時間上限（第 3.3 節） |
| 失敗時（審查 SF-1） | vendored 模組丟例外時 `scrub_text`、`scrub_line` 回 `LINE_WITHHELD`；含 lone surrogate 的已知秘密（bb48449 會丟 `UnicodeEncodeError`）也是；`ChildLogs.collect` 每行都失敗時照樣讀完 |
| 穩定 | 語料再遮一次不會多露，第二次起不變 |
| 長值差分 fuzz | 2 個種子 × 1200 行 × 5 個地方：bb48449 或 pin 版 PaaS 藏住的值都藏住；bb48449 藏住 ≥ 200、PaaS 藏住 ≥ 200（確認有咬合） |

先紅後綠（同一份新測試、vendored 模組與帳本，只把 `redact.py`、`diagnostics.py` 換掉）：

| | bb48449 的遮罩（`32ecac8`） | 審查前（`37fe574`） | 本片 |
|---|---|---|---|
| `tests/test_redaction_matrix.py` | 61 失敗、46 通過 | 14 失敗（都是本輪新增）、93 通過 | 107 通過 |
| `tests/vendor_paas/` | 574 通過（只測 PaaS 模組本身） | 574 通過 | 574 通過 |

變異（每個只改一處，跑 `tests/test_redaction_matrix.py`）：

| id | 改壞了什麼 | 結果 |
|---|---|---|
| M09 | `PIECE` 4 → 8（審查沒擋下的） | 擋下：`test_a_run_of_PIECE_characters_counts_where_its_windows_show_elsewhere` |
| M16 | 拿掉 `_fail_closed` 的 stack_info 分支（審查沒擋下的） | 擋下：`test_the_guard_checks_the_stack_too` |
| M18 | 守門只解碼 1 輪（審查沒擋下的） | 擋下（3 案），含 `test_the_guard_decodes_every_round_the_paas_module_decodes` |
| W1 | 拿掉視窗，只比 `PIECE` 片段（＝審查前） | 擋下（10 案）：短值反例、短值 fuzz、3 個字元的視窗 |
| W2 | 視窗只留 3 個字元 | 擋下（2 案）：只露一個字母的兩個反例 |
| W3 | 視窗只留 2 個字元 | 擋下：`test_a_window_of_three_counts_where_its_pairs_show_elsewhere` |
| W4 | 視窗要求每個字元都是英數 | 擋下（4 案） |
| W5 | 不在遮罩處切開（遮罩的字當成顯示的文字） | 擋下（2 案） |
| W6 | 不豁免 HA 單獨也顯示的片段 | 擋下（4 案） |
| W7 | HA 單獨的結果只用原樣比、不用解碼後比 | 擋下（2 案）：`test_child_lines_the_paas_module_answers_decoded_stay_readable` |
| U1 | 解碼換回 stdlib `unquote`（＝審查前） | 擋下（2 案）：時間上限、解碼器 |
| F1、F2、F3 | `scrub_text`、`scrub_line`、兩者都不接例外 | 各自擋下（1、1、2 案） |
| P1 | 拿掉 `PIECE` 片段，只比視窗 | 擋下：`test_a_run_of_PIECE_characters_counts_where_its_windows_show_elsewhere` |
| W6b | 不先排除「HA 單獨原樣顯示的整段」 | 沒擋下：等效（只是少做工，結果相同） |
| B1 | 永遠走集合那條路，不用子字串搜尋 | 沒擋下：等效（兩種做法結果相同，差在成本） |
| J1 | 含換行的視窗也用接起來的字串比 | 沒擋下：只影響多行文字裡跨換行的視窗，結果又和集合順序有關，沒有穩定的測試；實作逐段比對 |
| H1 | 被藏的值不在遮罩處切開 | 沒擋下：只影響結果在遮罩之外剛好有 `REDACTED` 這類字的情況（只會多擋） |

## 8. 本機檢查

| 檢查 | 結果 |
|---|---|
| `tests/test_redaction_matrix.py`＋`tests/vendor_paas/` | 681 通過、0 skip，約 52 秒（新 107＋vendored 574；審查前 660 案約 42 秒） |
| 全套 pytest（`flock wave1-pytest.lock`，短 TMPDIR；跑在 `bdfe7fd`，HEAD 寫在 log 第一行；之後只改了前一個 commit 的訊息，`8bee5d8` 的樹逐位元相同） | 4413 案（HM-01 的 3732＋本片 681）：4389 通過、24 失敗、0 skip，28 分 39 秒。本片的 681 案全過（照 CI 的檔名順序：`test_redaction_matrix.py` 107 案 26.1 秒、`tests/vendor_paas/` 574 案 24.3 秒）。24 個失敗都和本片無關：22 個瀏覽器測試（本機沒有 Chromium，第 9 節）；1 個要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`；1 個 `tests/test_ledger_precheck.py::test_drift_and_pinned_changes`，是 HM-01 的檔會偶發失敗（`scripts/ledger_precheck.py` 用 `shutil.copyfile` 複製 git index，測試在同一秒內改的檔有時偵測不到；HM-04 審查的 O-1 已回報），本片沒動這兩個檔，單獨重跑 10 次 9 次通過。之後的 docs commit 只改本筆記，沒有測試讀它 |
| `packaging/validate.py`（ci-venv） | PASS |
| packaging unittest | ci-venv：178 案跑完、5 個 skip（要 root），`test_container_probe`、`test_denial_probe` 兩個模組在 ci-venv 沒有 httpx 無法 import；這兩個模組改用 repo 的 `.venv` 跑，各 3 案 OK。和審查前的基準相同 |
| `scripts/tool_inventory.py`（漂移檢查） | 通過（rc 0） |
| 秘密預檢 `scripts/secret_precheck.py`（gitleaks 8.28.0，從 SHA-256 等於 pin 的壓縮檔離線安裝） | `--base 32ecac8`：本片 7 個 commit（含本筆記）0 命中；`--full`：另加 HEAD 原始碼與全歷史，0 命中 |
| 帳本預檢 `scripts/ledger_precheck.py --base 32ecac8` | `runtime-patches` 153、`runtime-sources` 70、`tool-surface` 159，0 漂移、0 缺檔；列管檔 `log_redaction.py` 與帳本同 PR；`redact.py`、`diagnostics.py` 列為「要人看」（不列管，見第 2 節） |
| Release train 離線檢查 | 上一輪：base 與 head 相同，通過（第 5 節）；本輪沒有重跑 |
| 實驗（不在 repo） | 第 3.2、3.3 節的 fuzz 與量測；腳本與輸出留在本機暫存區，不進 repo（值都是合成的） |

- 本機測試的方式：repo 的 `tests/conftest.py` 有整個 session 的本機測試鎖，其他代理跑全套時會等滿 120 秒後全部 error；
  所以只跑純函式測試（新測試與 vendored）時，在暫存區的複本把那把鎖換成私有路徑（只改複本），全套才在 clone 裡照原本的鎖跑。

## 9. 只在 CI 跑的測試

- pytest 在 CI 以 root（`sudo`）跑；本機是一般使用者。已知只在本機失敗的是 `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root）。
- pytest 裡要 Chromium 的 22 案（`test_owned_browser_ipc.py::test_terminal_coalesced_proof` 5 案、
  `test_owned_browser_redirect.py::test_chromium_redirect_denied_before_fulfill` 16 案、`test_owned_ui.py::test_standalone_ownership_boundaries[browser]`）：
  根因是本機沒有 Chromium（`PLAYWRIGHT_BROWSERS_PATH` 指的目錄裡沒有瀏覽器；`setup_repo_env.sh` 不跑 `npm run browser:install`，
  CI 的 `packaging/unit.sh` 會跑）。其中 16＋1 案的訊息是 `browserType.launch: Executable doesn't exist`，5 個
  `test_terminal_coalesced_proof` 的訊息是下游的 `JSONDecodeError`（審查 SF-5 指正，上一版寫成全部是 Executable doesn't exist）。
- packaging unittest 裡 5 個要 root 的案例（本機 skip）。
- UI：`npm test`、build closure、Playwright 瀏覽器測試（本片沒改 UI，本機沒跑）。
- Release train（`wvt-check.yml`）、`readiness`、`Upgrade comparison / compare`：GitHub 上跑。
- vendored 的 `test_redact_is_fast_on_pathological_inputs`（64 KB ≤ 50 ms、取 3 次最好）：本機最慢 17.5～21.3 ms（`&token=x`），
  餘裕約 2.3～2.9 倍；這些檔不能改，CI 若偶發失敗的處理方式待主對話定（第 12 節）。
- `checks` 前後秒數：開 PR 後補（本輪新增的測試本機約多 10 秒）。

## 10. 本片用到的決策（主對話之後同步到 `docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| DQ-38 | (a) 原樣 vendor；使用者 2026-11-14 21:5x 確認 PaaS 的 `log_redaction.py`（#149 合併版）與純測試可以公開放進 HA 的公開 repo | 三個前提都滿足：使用者確認、先跑秘密預檢（第 4 節）、Release train 不比對（第 5 節；取得方式見 MF-4）。授權說明見第 4 節 |
| DQ-06 | 對齊基準含 #149；之後的 PaaS 變動每片列出 | 以 `7d111b1` 為準；`cf3d0d5` 的變動列在第 6 節 |
| §13.1（15 項建議全採用） | 使用者合併、不改版號、HA 不加 AI 署名、PR 標題前綴、本機短 TMPDIR 用完刪、以 GitHub CI 為準 | commit 沒有 AI 署名；不 push、不開 PR（這一波的規則） |

沒有用到 DQ-09、DQ-12、DQ-19；沒有碰到 §13.2、§13.3 還沒問的題目。審查提出的 MF-3（帳本記法）是新的問題，沒有自己定（第 12 節）。

## 11. 驗收條件（計畫 §12.3 HM-02）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 未驗證：這一波不 push；本機見第 8 節 |
| 新測試在 bb48449 的遮罩上會失敗、改完通過 | 達成：61 失敗 → 107 通過（第 7 節） |
| 既有測試 0 修改 | 達成：`git diff 32ecac8 --stat` 只有新檔與 `redact.py`、`diagnostics.py`、`runtime-patches.json` |
| `[REDACTED]` 格式不變 | 達成：`/private_[REDACTED]`、`[REDACTED]`、`Bearer [REDACTED]`、`token=[REDACTED]`、`http://[REDACTED]@` 照舊；bb48449 會遮的子程式行輸出逐字相同（`test_the_ha_forms_are_unchanged`） |
| 秘密預檢 0 命中 | 達成（第 8 節） |
| §8.6 現行遮得到的寫法不退步 | 達成到第 3.2 節的保證範圍（已知殘留：只露一個字母、旁邊的字 HA 單獨也顯示） |
| （做法）vendored 檔記進 `runtime-sources.json` | **沒做到，要決定**：見第 12 節第 1 點，改記在 `runtime-patches.json` |

## 12. 待辦與未解

1. **`runtime-sources.json`（審查 MF-3，要主對話或使用者決定）**：計畫、HM-00 `ledger-tracking.md` 與這一波的指示都說 vendored
   檔記進 `runtime-sources.json`。但那本帳的每一筆都被當成 `apps/<product>/vendor/<path>`：
   `tests/test_tool_inventory.py::test_vendored_content_hashes_and_license_notices` 照這個路徑讀檔比 SHA-256，`scripts/ledger_precheck.py`
   也一樣。加一筆 `packages/mcp-admin-core/…` 會讓既有測試失敗，要過就得改既有測試（違反「既有測試 0 修改」）。本片把來源
   repo、commit、路徑、SHA-256 寫在 `runtime-patches.json` 那一筆的 `change`，並由 `tests/test_redaction_matrix.py` 釘住（改一個字
   就紅）。可選：(a) 維持這樣，寫進 decisions.md（作者與審查都建議）；(b) 另開一片擴充 `runtime-sources.json` 的格式並同步改
   `test_tool_inventory.py` 與 `ledger_precheck.py`。
2. **上一輪的兩次唯讀遠端讀取（審查 MF-4，要主對話確認）**：第 5、6 節。接受的話結論沿用；不接受的話開 PR 時重做。不管哪一種，
   開 PR 時都要在連得到 Gitea 的地方重跑 PaaS 變動清單（計畫 §11.1）。
3. **vendored 計時測試在 CI 偶發失敗的處理（審查 SF-3，待主對話定）**：`tests/vendor_paas/test_log_redaction_linear.py` 的上限不能在
   本 repo 改。本機餘裕約 2.3～2.9 倍（第 9 節）。
4. **給 PaaS 的回補建議（審查 SF-4，留給 HM-29）**：PaaS 模組在「深層編碼＋大量 `%`」的形狀 64 KB 要 76.6 ms，超過它自己線性測試
   的 50 ms 標準；由 PaaS 修正後整檔同步。
5. **`THIRD_PARTY_NOTICES.md`（審查 SF-5）**：沒改，理由見第 4 節；要註記的話由主對話定（根目錄檔案不在計畫 §11.1 功能 PR 的目錄內）。
6. **給發版片的提醒（審查 SF-6）**：本片不受產品開關管（HM-00 `contract.md`），下一個發版的產品會帶出這些看得到的變化，那個產品的
   CHANGELOG 要寫：紀錄裡 query 憑證的值顯示 `***`；診斷頁（子程式輸出）整行換成 `[redacted: ambiguous URL encoding]` 的機會變多
   （測試語料 5%，一般行 0%）；子程式輸出的 `key: value`、`"key": …` 這類一般文字也被遮；遮罩失敗時整行顯示
   `line withheld (redaction failed)`。
7. `checks` 前後秒數：開 PR 後補。
8. DQ-38 的「已定」與本片用到的決策，主對話開 PR 時同步到 `docs/multi-profile/decisions.md`（本分支沒有 `docs/multi-profile/`）。
9. HM-08 的回覆遮罩聯集（§5.1 第 8 點、DQ-40）不在本片。
10. 本機環境：`setup_repo_env.sh` 沒有 `npm run browser:install`，這個 clone 沒有 Playwright 的 Chromium，pytest 的 22 個瀏覽器測試
    在本機一定失敗（和本片無關）。要在本機跑，得在腳本加這一步（會從 Playwright 下載 Chromium）。
11. HM-01 的 `tests/test_ledger_precheck.py::test_drift_and_pinned_changes` 會偶發失敗（第 8 節；HM-04 審查的 O-1），CI 可能隨機紅；
    修不修、什麼時候修由負責人決定（#90 的檔，這一波不碰）。

## 13. 審查意見處理（獨立安全審查，2026-11-15 第 2 次）

| 意見 | 處理 | 結果與證據 |
|---|---|---|
| MF-1 守門只看 4 個字元以上的英數片段 | 改程式與測試（commit `1b2be85`） | 守門另比 2、3 個字元的視窗，紀錄與子程式兩路都用（審查原型只補子程式那一路，也看不到 PaaS 遮掉規則用字的情況，沒有採用，理由見第 3.2 節）。審查的 4 個例子與 fuzz 找到的 3 個釘成反例；短值差分 fuzz 進測試；第 3.2 節改寫成實際保證範圍並列出已知殘留 |
| MF-2 守門用 stdlib `unquote`，provenance 的效能數字不對 | 改程式與測試（commit `1b2be85`） | `_forms` 用 `log_redaction._unquote`，各段文字只解碼一次；時間上限改成 PaaS 單獨耗時 × 3 ＋ 30 ms，加入審查的形狀；`_unquote` 與 stdlib 的一致性進測試；第 3.3 節改成實測數字 |
| MF-3 `runtime-sources.json` 的記法 | 要主對話或使用者決定；本片維持現狀 | 第 12 節第 1 點；沒有改 decisions.md（本分支沒有 `docs/multi-profile/`） |
| MF-4 兩次唯讀遠端讀取沒有標成例外 | 要主對話確認；provenance 寫明 | 第 5、6 節寫明取得方式、時間與規則例外；本輪沒有任何連線 |
| SF-1 子程式輸出那一路沒有 fail-closed | 採用（commit `8bee5d8`） | `scrub_text`、`scrub_line` 都不再丟例外，回 `LINE_WITHHELD`；順便涵蓋 bb48449 就有的已知秘密編碼失敗；測試含 `ChildLogs.collect` |
| SF-2 變異沒擋下的測試缺口（M09、M16、M18） | 採用（commit `1b2be85`） | 3 個都有專門的測試擋下（第 7 節變異表）；M20 是等效變異、M23 由逐位元 pin 擋，維持審查的說法 |
| SF-3 計時測試的門檻與餘裕 | HA 的部分採用（MF-2）；vendored 的部分記錄 | 第 9 節記下餘裕；CI 偶發失敗的處理待主對話定（第 12 節第 3 點）；CI 增量開 PR 後用 `checks` 秒數確認 |
| SF-4 PaaS 模組本身的成本 | 記錄，留給 HM-29 | 第 3.3 節、第 12 節第 4 點 |
| SF-5 provenance 小修正 | 採用 | 授權（第 4 節）；全套 pytest 的 HEAD 寫進同一個 log 的第一行（第 8 節；上一輪的 log 第一行其實也記了 `d9b3b20`，對不上的是另一個排隊時寫的檔）；瀏覽器失敗的根因（第 9 節）；`THIRD_PARTY_NOTICES.md` 不改的理由（第 4 節） |
| SF-6 發版片的提醒 | 採用 | 第 12 節第 6 點 |
