# HA 多帳號 HM-02 provenance：紀錄遮罩對齊 PaaS（含 #149，原樣 vendor）（2026-11-15；審查後、rebase 後更新）

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
- 既有測試 0 修改；`[REDACTED]` 格式不變；秘密預檢 0 命中；帳本預檢 0 漂移（rebase 後重跑，第 8.2 節）。
  rebase 前的本機全套 pytest 見第 8.3 節。
- Release train：上一輪離線核對，清冊不比對新 vendored 的檔；以本 PR 上的 `Release train / wvt check` 為準（MF-4 定案，第 5 節）。
- **主對話 2026-11-15 08:2x 的定案**（第 10、12 節）：
  - MF-3：vendored 的 `log_redaction.py` 維持記在 `runtime-patches.json`，不擴充 `runtime-sources.json`（那本只收
    `apps/<產品>/vendor/`）。#96 已寫進 `docs/multi-profile/decisions.md`（DQ-38 補充）與 `ledger-tracking.md`。
  - MF-4：接受上一輪的兩次唯讀遠端讀取（從 Gitea fetch PaaS；從 GitHub 下載公司自家 repo 的 Release train 檔、在本機離線執行）。
  - vendored 計時測試先照原樣放；CI 不穩時，由主對話決定把那個計時檔從 vendor 清單拿掉、改用 HA 自己的相對門檻。
  - `THIRD_PARTY_NOTICES.md` 不改：公司自家程式，DQ-38 已同意公開。
- rebase（2026-11-15，兩次，第 14 節）：
  - 第一次：從 HM-01 分支 head `32ecac8` 移到 `claude-delivery` `8e02ac1`（含 HM-00 #89、HM-01 #90、HM-04 #91、HM-17 #92、
    HM-07 #93、HM-06 #94、HM-05 #95）。7 個 commit 重放，只有第 1 個 commit 的帳本有文字衝突（兩邊都在檔尾加項目）。
  - 第二次：HM-13a（#97）與文件同步（#96）合併後，從 `8e02ac1` 移到 `dc90c32`。8 個 commit 重放，沒有衝突。
  - 兩次的帳本都以 `claude-delivery` 的為底、只加回本片 1 筆；最後 58 個列管檔的 SHA-256 全部用合併後的內容重算，
    `claude-delivery` 的 57 筆一筆都沒變。第二次照資料重建的帳本和 git 自動合併的結果逐位元相同。
  - 本片其他 13 個檔兩次 rebase 前後都逐位元相同。本片沒動 `apps/`，tool-surface 不用重產（檢查模式通過）。
- 第二次 rebase 後的本機檢查（第 8.1 節）：本片 681 案和 HM-13a 的 `test_restore_detection.py`、`test_upgrade_zero_rewrite.py`
  一起跑 857 案，只有 HM-13a 已知要 root 的 5 案失敗；35 檔＋vendored 照 CI 順序 1672 案全過；全部 0 skip。
  packaging unittest `Ran 201`、`OK (skipped=5)`；`validate.py` PASS。第一次 rebase 後的結果也在第 8.1 節。全套 pytest 以 CI 為準。
- PaaS 變動（第 6 節）：主對話 06:2x fetch 時 main 是 `cf3d0d5`。`7d111b1..cf3d0d5` 在核心模組只改 `setup_status.py`（說明文字）；
  `log_redaction.py` 與 4 個純測試都沒變，vendored 檔仍等於 PaaS main 的版本。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-02（計畫 §8.6、§12.3；風險中、工作量 M） |
| 分支 | `feat/ha-multiprofile-hm02-20261114`（第二次 rebase 後 push、開 PR；本片作者不合併） |
| HA 基準 | `claude-delivery` `dc90c32`（#97 HM-13a 的合併；含 #89 HM-00、#90 HM-01、#91 HM-04、#92 HM-17、#93 HM-07、#94 HM-06、#95 HM-05、#96 文件同步）。開發與審查時是 HM-01 分支 head `32ecac8`（＝`bb48449`＋HM-01）；2026-11-15 rebase 兩次（`8e02ac1`、`dc90c32`；第 14 節）。`redact.py`、`diagnostics.py` 在 `bb48449`、`32ecac8`、`dc90c32` 逐位元相同 |
| 對齊的 PaaS | `WOOWTECH/woow-mcp-server` main `7d111b175fbbcdf692ff579cc5793bf8c7de3a7b`（#149 合併）；主對話 2026-11-15 06:2x fetch 時 main＝`cf3d0d5`，`log_redaction.py` 和 `7d111b1` 相同（第 6 節） |
| 依據 | 計畫 §8.6、§11.1、§12.0、§12.3「HM-02」；HM-00 `ledger-tracking.md`、`paas-test-mapping.md`、`acceptance-matrix.md`（T-25、`tests/test_redaction_matrix.py` 登記列） |
| FM | FM-75（另含 FM-65 的 `?key=`） |
| 審查 | 獨立安全審查（2026-11-15 第 2 次，審 `37fe574`，rebase 後是 `e03f836`；判定「修正後通過」；報告路徑附在 PR 說明）；處理見第 13 節 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `packages/mcp-admin-core/mcp_admin_core/log_redaction.py`（新） | PaaS `7d111b1` 同路徑的檔，逐位元相同（SHA-256 `1fec42aab78201e5c2bd892586e19ee640f0214905189ff9dbfea29d729b1f91`）。本 repo 不改它；PaaS 之後再改就整檔同步。 |
| `packages/mcp-admin-core/mcp_admin_core/redact.py` | `scrub()`：先 `log_redaction.scrub_record`，再照舊套 HA 規則，最後 `_fail_closed`。`scrub_text()`：子程式輸出用，同樣的組合與守門，失敗時回 `LINE_WITHHELD`、不丟例外（SF-1）。守門 `shows_hidden()`：比 `PIECE`（4）個字元的英數片段與 `WINDOWS`（2、3）個字元的視窗（MF-1）；`_forms()` 用 `log_redaction._unquote` 解碼（MF-2）。其他新名稱：`PATH_RULES`、`apply_rules`、`_windows`、`_parts`、`_not_shown`、`LINE_WITHHELD`。`install()` 先編好 PaaS 延遲編譯的 pattern。`redact()`、`leaks()`、`REDACTED`、`SECRET_MASK`、`secret_values`、`redact_secrets` 不變。 |
| `packages/mcp-admin-core/mcp_admin_core/diagnostics.py` | `scrub_line()`：已知秘密換掉之後，`redact.scrub_text(text, RULES)`；整段包起來，失敗時回 `redact.LINE_WITHHELD`（SF-1）。`RULES`＝bb48449 的四條規則（`PRIVATE_SEGMENT`、`AUTH`、`ASSIGNMENT`、`USERINFO`，regex 與順序都不變）＋新的 `KEY`。 |
| `docs/provenance/runtime-patches.json` | 新增 `log_redaction.py` 一筆（`sha256`、`change` 寫來源 repo、commit、路徑、SHA-256；`guarded_sources` 是 `{}`）。兩次 rebase 都以 `claude-delivery` 的帳本為底，只加回這 1 筆，摘要全部用合併後的內容重算（第 14 節）。 |
| `tests/vendor_paas/test_log_redaction_{encoded_boundaries,linear,segments,single_pass}.py`（新） | PaaS `7d111b1` 的 `packages/mcp-admin-core/tests/` 同名檔，逐位元相同（574 案）。 |
| `tests/vendor_paas/conftest.py`、`__init__.py`（新，HA 寫的） | 每個 PaaS 測試前換回標準 record factory、拿掉 HA 的 `RedactSecretPaths`；跑完還原 record factory、每個 logger 與 handler 的 filter，以及 root 以外每個 logger 的 level、propagate、handler（測試中才建立的 logger 回到剛建立的樣子）。兩個方向都需要：沒有前半，`test_secret_path.py::test_real_uvicorn_logs_never_show_the_secret` 之後有 2 個 PaaS 測試失敗；沒有後半，PaaS 測試排在前面時那個 HA 測試失敗（PaaS 的 `test_log_redaction_linear.py` 借用 `uvicorn.error` 後留下 INFO、不往上傳）。 |
| `tests/test_redaction_matrix.py`（新，107 案） | 見第 7 節。所有案例都在 HM-01 的 `log_scan` 下跑。 |
| `tests/fixtures/redact_bb48449.py`、`diagnostics_bb48449.py`（新） | bb48449 的兩個檔，逐位元相同（測試釘 SHA-256），當不退步差分的對照組。 |
| `docs/provenance/ha-multiprofile-HM-02-20261114.md` | 本筆記 |

沒改：`apps/`（含 `apps/runtime/*.py`、`apps/*/launch.py`，所以不用重產 tool-surface）、`packaging/`、`addons/<x>/`、版號、
CHANGELOG、`upgrade-notes.yaml`、`runtime-sources.json`、`tool-surface.json`／`.md`、workflow、`THIRD_PARTY_NOTICES.md`、
UI、`tests/conftest.py`、`docs/multi-profile/`（rebase 後本分支有 HM-00 起的這些文件，本片沒改；MF-3 的定案 #96 已寫進
`decisions.md` 與 `ledger-tracking.md`）；既有的測試檔一個都沒改（rebase 後 `git diff origin/claude-delivery HEAD` 只有本片的 14 個檔）。
`redact.py`、`diagnostics.py` 照 HM-00 `ledger-tracking.md` 第 3 節維持不列管（帳本預檢列為「要人看」）。

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
  MIT `LICENSE`，是因為那個上游 app 自己宣告了 MIT，這裡上游沒有宣告。主對話 2026-11-15 08:2x 定案：不改（公司自家程式，
  DQ-38 已同意公開；第 12 節）。

## 5. Release train（UC-29、C4-SF-9）

- 結論（上一輪離線核對）：清冊不比對新 vendored 的檔，不擋。**最後以本 PR 上的 `Release train / wvt check` 為準**
  （審查 MF-4；主對話 2026-11-15 08:2x 定案）。
- 讀過的來源（GitHub 鏡像 `WOOWTECH/woow-release-train` main `1f80663`，和 Gitea `woow-paas/woow-release-train` main 相同）：
  `.github/workflows/wvt-check.yml`、`woow-versions.yaml`、`tools/wvt.py`。
- `wvt check --leg ha` 只看清冊裡這個 repo 的釘點：n8n 的 `package.json`／lock、odoo 的 `pyproject.toml`／`uv.lock`、
  `runtime-sources.json` 裡 litellm、hermes、emqx、nextcloud 的紀錄（依 `product` 篩）、litellm 與 nextcloud vendor 的
  `__version__`、5 個子程式的 `mcp` 版本。沒有任何釘點指到 `packages/mcp-admin-core/`；`woow-mcp-server` 產品只有 paas 腿；
  `shared_files` 的消費者是別的 repo（`Woow_ha_litellm`）。
- 離線實跑（`python3 -I tools/wvt.py check --leg ha --repo github:WOOWTECH/Woow_ha_mcp_addons`，對 `32ecac8` 與當時分支 head
  的 `git archive`）：兩邊輸出與 JSON 完全相同，17 個釘點、通過、0 個會擋、1 個既有警告（nextcloud 的 `json_select` 有兩個
  不同來源 commit，本片沒動）。審查修正只改 `packages/mcp-admin-core/` 與 `tests/`，不影響這個結論。
- 注意：MF-3 已定不把這個檔加進 `runtime-sources.json`；就算之後加，只要 `product` 不是清冊用的名字，`json_select` 也比對不到。
- **取得方式（審查 MF-4；主對話 2026-11-15 08:2x 接受）**：上面的 3 個檔是上一輪作者在 2026-11-15 00:49～00:50 從
  `api.github.com` 下載的（`WOOWTECH/woow-release-train` commit `1f80663` 的 commit 與 tree 回應，再取這 3 個檔；
  11-14 22:09 也下載過一份 commits 清單），`tools/wvt.py` 是在本機離線執行（`python3 -I`）。都是唯讀；審查沒有看到憑證外流
  的跡象。當時沒有標成規則例外、也沒有停下回報；主對話接受這次讀取（公司自家 repo 的檔、唯讀、離線執行），本節結論沿用。
  處理審查意見與 rebase 這兩輪都沒有連 Gitea 或 Release train，也沒有再執行下載的程式（rebase 這一輪的連線只有照指示
  `git fetch origin claude-delivery`，GitHub）。

## 6. PaaS 變動清單（DQ-06）

- 結論：本片仍以 `7d111b1` 為準。PaaS main 到 `cf3d0d5` 為止，`log_redaction.py` 和 4 個純測試都沒變；vendored 檔仍等於 PaaS main 的版本。
- 來源：主對話 2026-11-15 06:2x fetch，PaaS main＝`cf3d0d5`（#151，移除 VK）。`7d111b1..cf3d0d5` 共 5 個 commit：`f5223be`、`36bde7b`、
  `7412dae`、`8bfb12e` 與合併 `cf3d0d5`。
- 本輪核對：用本機 PaaS clone 唯讀（`git log`、`git diff`、`git show`；沒有 fetch、沒有 checkout），`origin/main` 是 `cf3d0d5`，和主對話的
  結果相同。
- 核心模組（`packages/mcp-admin-core/mcp_admin_core/`）：只改 `setup_status.py`（`8bfb12e`，模組說明拿掉 VK，2 行刪、2 行加；去掉 docstring
  後 AST 相同）。
- `log_redaction.py`：`7d111b1` 和 `cf3d0d5` 的 SHA-256 都是 `1fec42aa…1b1f91`，0 行差異；本 repo 的 vendored 檔也是這個值。
- 遮罩測試（PaaS 共 8 個 `test_log_redaction*.py`）：
  - 帶進來的 4 個純測試：`cf3d0d5` 和 `7d111b1` 逐位元相同。
  - `test_log_redaction.py`（端到端，要起 PaaS 的 app，沒有帶進來）：`f5223be` 因移除 VK 改了參數列：`APPS` 拿掉 `"vk"`，上面的註解
    「九個 app」改成「七個 app」（`git diff --numstat`：2 行刪、2 行加）。照 DQ-06 記下差異：vendored 的測試以 `7d111b1` 為準；這個差異只在
    沒帶進來的檔，HA 沒有 VK，不影響本片。
  - 另外 3 個沒帶進來的（`private_separators`、`query_credentials`、`query_credentials_review`）與 `tests/fixtures/`：沒變。
- 基準文件第 4 節的清單（pin 換成 `7d111b1`）：只有 `36bde7b`（刪 `apps/vk/vk_mcp_admin/main.py`、改 `docs/paas-config-restore-runbook.md`）
  與 `8bfb12e`（改 `apps/opendesign/opendesign_mcp_admin/main.py` 與 `setup_status.py` 的說明文字；去掉 docstring 後 AST 都相同）。
  都和 HM-02 無關（HA 沒有 VK）。
- 測試檔（`git diff --name-status 7d111b1 origin/main -- '*test*'`）：17 個改（含 UI 的 1 個）、3 個刪（VK 的），沒有新增的測試檔。
- 取得方式：上一輪作者 2026-11-15 00:43 那次 fetch（審查 MF-4）主對話已接受；06:2x 那次是主對話自己做的。本輪沒有連 Gitea。

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

rebase 後本片的檔（帳本除外）逐位元相同，先紅後綠與變異沒有重做。

## 8. 本機檢查

### 8.1 rebase 後（2026-11-15）

兩次 rebase 後都用正式的 `tests/conftest.py` 與共用測試鎖（先確認沒有人在用才開始）；每次用新的 `/tmp/ha-mp-*`，跑完用完整路徑刪除。

**第二次 rebase 後（`claude-delivery` `dc90c32` 之上，最終）**：pytest 在第二次 rebase 後的樹上跑（工作樹乾淨；和最終 HEAD 只差
本筆記這一版，沒有測試讀它）。`claude-delivery` 在 `8e02ac1` 之後沒有動本片的檔，也沒有動 `redact.py`、`diagnostics.py`、
`lifecycle.py`、`run_product.py`、`gateway.py`、`apps/`、`tests/conftest.py`、`tests/log_scan.py`；新的是 HM-13a 的還原偵測
（`restore_detect.py`、`profiles.py`、`packaging/entrypoint.py`、`packaging/container_probe.py` 與它們的測試）和 `docs/`。

| 檢查 | 結果 |
|---|---|
| `tests/test_redaction_matrix.py`、HM-13a 的 `tests/test_restore_detection.py`、HM-13a 改過的 `tests/test_upgrade_zero_rewrite.py`、`tests/vendor_paas/`，照 CI 的檔名順序一次跑 | 857 案：852 通過、5 失敗、0 skip，55 秒。本片 681 全過；`test_restore_detection.py` 139 案裡 134 通過，5 個失敗都是 HM-13a 已知要 root 的 `test_root_*`（停在 `require_root()`；HM-13a provenance 也寫只在 CI 驗）；`test_upgrade_zero_rewrite.py` 37 全過 |
| 35 檔＋`tests/vendor_paas/`（和第一次同一組），照 CI 的檔名順序一次跑 | 1672 通過、0 失敗、0 skip，655 秒；逐檔案數和第一次相同 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest（和第一次同樣的暫存 venv 做法） | `Ran 201`、`OK (skipped=5)`（比第一次多 7 案：HM-13a 在 `test_container_probe.py` 加的） |
| `scripts/tool_inventory.py`（檢查模式，CI 同款） | 通過（rc 0）；本片沒動 `apps/`，不用 `--write` |
| 兩個預檢 | 第 8.2 節 |

**第一次 rebase 後（`claude-delivery` `8e02ac1` 之上）**：pytest 在第一次 rebase 後的 `07773df`（第一次 rebase 的 SHA，見第 14 節）跑
（工作樹乾淨）。

| 檢查 | 結果 |
|---|---|
| `tests/test_redaction_matrix.py`＋`tests/vendor_paas/` | 681 通過、0 skip，50 秒（107＋574；和 rebase 前相同） |
| 依賴遮罩的既有測試、HM-01 守門、HM-05／HM-06、帳本與預檢的測試：35 檔＋`tests/vendor_paas/`，照 CI 的檔名順序一次跑 | 1672 通過、0 失敗、0 skip，658 秒（明細在下面） |
| `claude-delivery` 在 `32ecac8` 之後新增或改過、上一列沒有的測試檔 12 個，加 `tests/test_redaction_matrix.py`、`tests/vendor_paas/`，照 CI 的檔名順序一次跑 | 1621 案：1620 通過、1 失敗、0 skip，424 秒。失敗的是 HM-07 已知要 root 的 `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（`assert os.geteuid() == 0`；只在 CI 驗，第 9 節）。12 檔：`test_identity_fields.py` 15、`test_initialize_cleanup.py` 293、`test_native_probe_separation.py` 12、`test_nextcloud_child.py` 47、`test_output_schemas.py` 189、`test_product_ha_role.py` 122、`test_product_runtime_failure.py` 3、`test_profile_consistency.py` 14、`test_profile_index.py` 111、`test_profile_store.py` 81、`test_session_idle.py` 24、`test_upgrade_zero_rewrite.py` 29；本片 681 全過 |
| `packaging/validate.py`（ci-venv 的 PyYAML） | PASS |
| packaging unittest | 照 CI 的步驟用暫存 venv（放在這次的 TMPDIR，跑完一起刪）：`UV_PROJECT_ENVIRONMENT=<暫存> uv sync --frozen --no-dev --offline`＋`uv pip install --offline --require-hashes --only-binary=:all: -r packaging/requirements-ci.txt`（離線、沒有下載；不動 clone 的 `.venv`；沒有用 `PYTHONPATH`），再 `-m unittest discover -s packaging -p 'test_*.py' -v`：`Ran 194`、`OK (skipped=5)`（5 個要 root）。比 rebase 前的 184 多 10 案：HM-17 的 8 案（`test_validate.py` 5、`test_release_gate.py` 3）、HM-06 的 2 案（`test_container_probe.py`）。registry 都是測試裡的假物件，沒有連網 |
| `scripts/tool_inventory.py`（檢查模式，CI 同款） | 通過（rc 0）；本片沒動 `apps/`，不用 `--write` |
| 兩個預檢 | 第 8.2 節（第一次 rebase 後那一輪也記在那裡） |
| 全套 pytest | 沒有跑（以 CI 為準）。本片的檔 rebase 前後逐位元相同（帳本除外，第 14 節） |
| `git status` | 乾淨（commit 之後）；用過的 TMPDIR 都已刪除 |

第一次 rebase 後 35 檔那一次的明細（第二次的逐檔數字相同，見上表）：

- 本片：`test_redaction_matrix.py` 107、`tests/vendor_paas/` 574（`encoded_boundaries` 20、`linear` 349、`segments` 194、`single_pass` 11）。
- HM-01 守門：`test_single_profile_golden.py` 17、`test_mcp_contract_freeze.py` 9、`test_admin_contract_freeze.py` 19、`test_log_scan.py` 13、
  `test_owned_ports_bearer.py` 52；期望值與案例檔沒改。
- HM-05、HM-06、HM-04：`test_profile_runtime.py` 65、`test_child_bearer.py` 28、`test_child_port_param.py` 233。
- 直接用到遮罩或 `[REDACTED]` 的既有測試：`test_secret_path.py` 20、`test_child_diagnostics.py` 4、`test_raw_backend_errors.py` 8、
  `test_stream_error_redaction.py` 42、`test_six_hardening.py` 30、`test_nextcloud_error_secrets.py` 20、`test_hermes_config_redaction.py` 1、
  `test_hermes_session_child.py` 13、`test_n8n_mcp_access_token.py` 5、`test_n8n_test_run_errors.py` 3、`test_batch2_n8n_public_errors.py` 12、
  `test_batch2_writer_errors.py` 1、`test_litellm_regression_followup.py` 2、`test_odoo_error_result_parity.py` 1、`test_odoo_overlay_parity.py` 7、
  `test_odoo_read_exists.py` 3、`test_owner_defaults.py` 139、`test_management_capabilities.py` 12、`test_full_surface.py` 28、
  `test_claude_ai_connector.py` 68、`test_unconfigured_connect.py` 61。
- 起真子程式（`run_product` 的 `redact.install()`、`guard_handlers`）：`test_real_products.py` 9、`test_role_lifecycle.py` 36。
- 帳本與預檢：`test_tool_inventory.py` 8、`test_ledger_precheck.py` 8、`test_secret_precheck.py` 14。

### 8.2 兩個預檢

**最終 HEAD（第二次 rebase 後）**：數字含本筆記這一版的 commit；本筆記這一版 commit 前後各掃一次，結果相同。指令：

```text
.venv/bin/python -I scripts/secret_precheck.py --tools <暫存區的 gitleaks-tools> --repo . --base origin/claude-delivery --head HEAD --full
.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery
```

- **秘密預檢**：gitleaks 8.28.0（釘選、執行檔摘要相符；用暫存區既有的執行檔，沒有下載）；設定是本 repo 的 `gitleaks_config()`。

  | 範圍 | 命中 |
  |---|---|
  | 本片的 commit（`dc90c32..HEAD`，git 模式；共 8 個，含本筆記這一版） | 0 |
  | `--full`：HEAD 的全部檔（建置機同款） | 0 |
  | `--full`：全歷史（建置機同款） | 0 |

  本筆記這一版修訂之前（第 8 個 commit 還是重放過來的上一版 `73eea31`，已被這一版取代），8 個 commit 與 `--full` 也先掃過，都 0 命中。

- **帳本預檢**：OK。`runtime-patches.json` 171 個路徑（第一次 rebase 後 169；多的 2 個是 HM-13a 新列管的 `packaging/entrypoint.py`、
  `restore_detect.py`）、`runtime-sources.json` 70 個、`tool-surface.json` 159 個，都 0 漂移、0 缺檔、0 個要 CI 安裝才有的檔。對
  `origin/claude-delivery`（merge base `dc90c32`）改 14 個檔：列管檔 1 個（`log_redaction.py`）與帳本 `runtime-patches.json` 一起改；
  新增而沒列管的執行期檔 0 個；改到而沒列管的執行期檔 2 個（`redact.py`、`diagnostics.py`，列為要人看；照 `ledger-tracking.md`
  第 3 節不列管）。

**第一次 rebase 後（當時的 HEAD `96618de`，`8e02ac1` 之上）**：秘密預檢本片 8 個 commit 0 命中，`--full` 的 HEAD 全部檔與全歷史也 0；
帳本預檢 OK：`runtime-patches.json` 169 個路徑（rebase 前 153；多的 16 個是 `claude-delivery` 帶來的：HM-07 新列管的 `config.py`、
`features.py`、`identity_fields.py`、`profiles.py`，HM-05 的 `profile_runtime.py`，加 HM-06 在 `session_idle.py` 多列的 11 個 guarded
sources）、`runtime-sources.json` 70 個、`tool-surface.json` 159 個，都 0 漂移、0 缺檔；改 14 個檔，結果同最終 HEAD 那一輪。

### 8.3 rebase 前（`32ecac8` 之上；當時的 HEAD `b124411`）

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

- pytest 在 CI 以 root（`sudo`）跑；本機是一般使用者。已知只在本機失敗的是 `tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（要 root）；
  rebase 後多一個 HM-07 的同類案例 `tests/test_profile_store.py::test_mode_and_owner_as_the_add_on_user`（`geteuid() != 0` 照預期失敗；它的探針
  只用 `profiles`、`config`，`log_scan` 用到的 `redact.secret_values` 本片沒改）；第二次 rebase 後再多 HM-13a 的 5 個 `test_root_*`
  （`tests/test_restore_detection.py`，停在 `require_root()`；HM-13a provenance 也寫只在 CI 驗）。
- pytest 裡要 Chromium 的 22 案（`test_owned_browser_ipc.py::test_terminal_coalesced_proof` 5 案、
  `test_owned_browser_redirect.py::test_chromium_redirect_denied_before_fulfill` 16 案、`test_owned_ui.py::test_standalone_ownership_boundaries[browser]`）：
  根因是本機沒有 Chromium（`PLAYWRIGHT_BROWSERS_PATH` 指的目錄裡沒有瀏覽器；`setup_repo_env.sh` 不跑 `npm run browser:install`，
  CI 的 `packaging/unit.sh` 會跑）。其中 16＋1 案的訊息是 `browserType.launch: Executable doesn't exist`，5 個
  `test_terminal_coalesced_proof` 的訊息是下游的 `JSONDecodeError`（審查 SF-5 指正，上一版寫成全部是 Executable doesn't exist）。
- packaging unittest 裡 5 個要 root 的案例（本機 skip）。
- UI：`npm test`、build closure、Playwright 瀏覽器測試（本片沒改 UI，本機沒跑）。
- Release train（`wvt-check.yml`）、`readiness`、`Upgrade comparison / compare`：GitHub 上跑。
- vendored 的 `test_redact_is_fast_on_pathological_inputs`（64 KB ≤ 50 ms、取 3 次最好）：本機最慢 17.5～21.3 ms（`&token=x`），
  餘裕約 2.3～2.9 倍；這些檔本 repo 不改。主對話 2026-11-15 08:2x 定案：先照原樣放；CI 不穩時，由主對話決定把這個計時檔從
  vendor 清單拿掉、改用 HA 自己的相對門檻（第 12 節）。rebase 後本機跑了 5 次（第 8.1 節，兩次 rebase 各自的前幾列），都過。
- `checks` 前後秒數：CI 跑完再補（本片新增 681 案，本機約 50 秒）。

## 10. 本片用到的決策（#96 已同步到 `docs/multi-profile/decisions.md`；本片不改 `docs/multi-profile/`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| DQ-38 | (a) 原樣 vendor；使用者 2026-11-14 21:5x 確認 PaaS 的 `log_redaction.py`（#149 合併版）與純測試可以公開放進 HA 的公開 repo | 三個前提都滿足：使用者確認、先跑秘密預檢（第 4 節）、Release train 上一輪離線核對不比對（第 5 節；最後以本 PR 的 check 為準）。授權說明見第 4 節 |
| DQ-38 補充（審查 MF-3；主對話 2026-11-15 08:2x 定案，#96 已寫進 `decisions.md` 與 `ledger-tracking.md`） | vendored 的 `log_redaction.py` 維持記在 `docs/provenance/runtime-patches.json`，不擴充 `runtime-sources.json`（那本只收 `apps/<產品>/vendor/`） | 帳本那一筆照舊（來源 repo、commit、路徑、SHA-256，`tests/test_redaction_matrix.py` 釘住）；不改 `runtime-sources.json`、`tests/test_tool_inventory.py`、`scripts/ledger_precheck.py` |
| 審查 MF-4（主對話 2026-11-15 08:2x 接受） | 上一輪的兩次唯讀遠端讀取：從 Gitea fetch PaaS（允許）；從 GitHub 下載公司自家 repo 的 Release train 檔、在本機離線執行 | 第 5、6 節的結論沿用；Release train 會不會比對 vendored 檔，以本 PR 上的 `Release train / wvt check` 為準 |
| vendored 計時測試（審查 SF-3；主對話 2026-11-15 08:2x 定案） | `tests/vendor_paas/test_log_redaction_linear.py` 的 64 KB ≤ 50 ms 先照原樣放；CI 不穩時，由主對話決定把那個計時檔從 vendor 清單拿掉、改用 HA 自己的相對門檻 | 現在不改 |
| `THIRD_PARTY_NOTICES.md`（審查 SF-5；主對話 2026-11-15 08:2x 定案） | 不改：公司自家程式，DQ-38 已同意公開 | 不改 |
| DQ-06 | 對齊基準含 #149；之後的 PaaS 變動每片列出 | 以 `7d111b1` 為準；到 `cf3d0d5` 的變動列在第 6 節 |
| DQ-36（已定，§13.1；2026-11-15 06:1x 補合併授權） | commit 與 PR 說明不加 AI 署名；標題加「⛔ 勿代 merge｜待覆核 — HM-02 …」；不改版號的多帳號功能 PR 由本工作的主對話在 CI 全綠後依序合併，其他人或代理不合併 | 本片不改版號、不碰 `addons/`；commit 沒有 AI 署名；本片作者不合併 |
| §13.1（15 項建議全採用） | 不改版號、本機短 TMPDIR 用完刪、以 GitHub CI 為準 | 每次測試用新的 `/tmp/ha-mp-*`，跑完用完整路徑刪除 |

沒有用到 DQ-09、DQ-12、DQ-19；沒有碰到 §13.2、§13.3 還沒問的題目。審查提出的 MF-3（帳本記法）由主對話定案（上表），作者沒有自己定。

## 11. 驗收條件（計畫 §12.3 HM-02）

| 條件 | 狀態 |
|---|---|
| CI 綠 | 待 CI：第二次 rebase 後 push、開 PR；本機見第 8 節 |
| 新測試在 bb48449 的遮罩上會失敗、改完通過 | 達成：61 失敗 → 107 通過（第 7 節） |
| 既有測試 0 修改 | 達成：rebase 後 `git diff origin/claude-delivery HEAD --stat` 只有新檔與 `redact.py`、`diagnostics.py`、`runtime-patches.json` |
| `[REDACTED]` 格式不變 | 達成：`/private_[REDACTED]`、`[REDACTED]`、`Bearer [REDACTED]`、`token=[REDACTED]`、`http://[REDACTED]@` 照舊；bb48449 會遮的子程式行輸出逐字相同（`test_the_ha_forms_are_unchanged`） |
| 秘密預檢 0 命中 | 達成（rebase 後重跑，第 8.2 節） |
| §8.6 現行遮得到的寫法不退步 | 達成到第 3.2 節的保證範圍（已知殘留：只露一個字母、旁邊的字 HA 單獨也顯示） |
| （做法）vendored 檔的記法 | 記在 `runtime-patches.json`，不記進 `runtime-sources.json`：主對話 2026-11-15 08:2x 定案（MF-3；#96 已把 DQ-38 補充寫進 `decisions.md`）；計畫 §12.3 也改成這個做法 |

## 12. 待辦與未解

1. **`runtime-sources.json`（審查 MF-3）：已定**（主對話 2026-11-15 08:2x）。vendored 的 `log_redaction.py` 維持記在 `runtime-patches.json`，
   不擴充 `runtime-sources.json`（那本每一筆都被當成 `apps/<product>/vendor/<path>`：`tests/test_tool_inventory.py`、`scripts/ledger_precheck.py`）。
   #96 已合併：`docs/multi-profile/decisions.md`（DQ-38 補充）與 `ledger-tracking.md` 都改成這個做法；計畫 §12.3 也是。本片不改
   `docs/multi-profile/`。
2. **上一輪的兩次唯讀遠端讀取（審查 MF-4）：已接受**（主對話 2026-11-15 08:2x）。第 5、6 節的結論沿用；Release train 會不會比對 vendored 檔，
   以本 PR 上的 `Release train / wvt check` 為準。PaaS 變動清單由主對話 06:2x 代查，本輪用本機 PaaS clone 唯讀核對（第 6 節）。
3. **vendored 計時測試（審查 SF-3）：已定**。先照原樣放；CI 不穩時，由主對話決定把 `tests/vendor_paas/test_log_redaction_linear.py` 從 vendor
   清單拿掉、改用 HA 自己的相對門檻。現在不改。本機餘裕約 2.3～2.9 倍（第 9 節）。
4. **給 PaaS 的回補建議（審查 SF-4，留給 HM-29）**：PaaS 模組在「深層編碼＋大量 `%`」的形狀 64 KB 要 76.6 ms，超過它自己線性測試
   的 50 ms 標準；由 PaaS 修正後整檔同步。
5. **`THIRD_PARTY_NOTICES.md`（審查 SF-5）：已定，不改**（公司自家程式，DQ-38 已同意公開；第 4 節）。
6. **給發版片的提醒（審查 SF-6）**：本片不受產品開關管（HM-00 `contract.md`），下一個發版的產品會帶出這些看得到的變化，那個產品的
   CHANGELOG 要寫：紀錄裡 query 憑證的值顯示 `***`；診斷頁（子程式輸出）整行換成 `[redacted: ambiguous URL encoding]` 的機會變多
   （測試語料 5%，一般行 0%）；子程式輸出的 `key: value`、`"key": …` 這類一般文字也被遮；遮罩失敗時整行顯示
   `line withheld (redaction failed)`。
7. `checks` 前後秒數：CI 跑完再補。
8. 已做：HM-13a（#97）合併後第二次 rebase 到 `dc90c32`，帳本照資料重建，重跑受影響的測試與兩個預檢（第 8.1、8.2 節，第 14 節第 6 點）。
9. HM-08 的回覆遮罩聯集（§5.1 第 8 點、DQ-40）不在本片。
10. 本機環境：`setup_repo_env.sh` 沒有 `npm run browser:install`，這個 clone 沒有 Playwright 的 Chromium，pytest 的 22 個瀏覽器測試
    在本機一定失敗（和本片無關）。要在本機跑，得在腳本加這一步（會從 Playwright 下載 Chromium）。
11. HM-01 的 `tests/test_ledger_precheck.py::test_drift_and_pinned_changes` 偶發失敗（第 8.3 節；HM-04 審查的 O-1）：#90 合併前已修
    （`1281abe`：`scripts/ledger_precheck.py` 複製 git index 時改用 `shutil.copy2`），rebase 後本分支也有這個修正。

## 13. 審查意見處理（獨立安全審查，2026-11-15 第 2 次）

| 意見 | 處理 | 結果與證據 |
|---|---|---|
| MF-1 守門只看 4 個字元以上的英數片段 | 改程式與測試（commit `1b2be85`，rebase 後 `342567d`） | 守門另比 2、3 個字元的視窗，紀錄與子程式兩路都用（審查原型只補子程式那一路，也看不到 PaaS 遮掉規則用字的情況，沒有採用，理由見第 3.2 節）。審查的 4 個例子與 fuzz 找到的 3 個釘成反例；短值差分 fuzz 進測試；第 3.2 節改寫成實際保證範圍並列出已知殘留 |
| MF-2 守門用 stdlib `unquote`，provenance 的效能數字不對 | 改程式與測試（commit `1b2be85`，rebase 後 `342567d`） | `_forms` 用 `log_redaction._unquote`，各段文字只解碼一次；時間上限改成 PaaS 單獨耗時 × 3 ＋ 30 ms，加入審查的形狀；`_unquote` 與 stdlib 的一致性進測試；第 3.3 節改成實測數字 |
| MF-3 `runtime-sources.json` 的記法 | 主對話 2026-11-15 08:2x 定案：維持記在 `runtime-patches.json` | 帳本那一筆照舊；不擴充 `runtime-sources.json`。#96 已把定案寫進 `decisions.md`（DQ-38 補充）與 `ledger-tracking.md`，本片不改 `docs/multi-profile/`（第 10 節、第 12 節第 1 點） |
| MF-4 兩次唯讀遠端讀取沒有標成例外 | 主對話 2026-11-15 08:2x 接受 | 第 5、6 節寫明取得方式與時間；Release train 以本 PR 上的 `Release train / wvt check` 為準；PaaS 變動清單由主對話 06:2x 代查、本輪用本機 PaaS clone 唯讀核對（第 6 節）；處理審查意見與 rebase 這兩輪都沒有連 Gitea 或 Release train |
| SF-1 子程式輸出那一路沒有 fail-closed | 採用（commit `8bee5d8`，rebase 後 `a294697`） | `scrub_text`、`scrub_line` 都不再丟例外，回 `LINE_WITHHELD`；順便涵蓋 bb48449 就有的已知秘密編碼失敗；測試含 `ChildLogs.collect` |
| SF-2 變異沒擋下的測試缺口（M09、M16、M18） | 採用（commit `1b2be85`，rebase 後 `342567d`） | 3 個都有專門的測試擋下（第 7 節變異表）；M20 是等效變異、M23 由逐位元 pin 擋，維持審查的說法 |
| SF-3 計時測試的門檻與餘裕 | HA 的部分採用（MF-2）；vendored 的部分記錄 | 第 9 節記下餘裕。主對話定案：vendored 的計時測試先照原樣放；CI 不穩時，由主對話決定把那個計時檔從 vendor 清單拿掉、改用 HA 的相對門檻（第 12 節第 3 點）。CI 增量等 CI 跑完用 `checks` 秒數確認 |
| SF-4 PaaS 模組本身的成本 | 記錄，留給 HM-29 | 第 3.3 節、第 12 節第 4 點 |
| SF-5 provenance 小修正 | 採用 | 授權（第 4 節）；全套 pytest 的 HEAD 寫進同一個 log 的第一行（第 8.3 節；上一輪的 log 第一行其實也記了 `d9b3b20`，對不上的是另一個排隊時寫的檔）；瀏覽器失敗的根因（第 9 節）；`THIRD_PARTY_NOTICES.md` 不改（主對話定案：公司自家程式，DQ-38 已同意公開；第 4 節） |
| SF-6 發版片的提醒 | 採用 | 第 12 節第 6 點 |

## 14. rebase（2026-11-15，兩次）

**第一次（`32ecac8` → `8e02ac1`）**

1. `git fetch origin claude-delivery`（`8e02ac1`），`git rebase --onto origin/claude-delivery 32ecac8`：本片 7 個 commit 依序重放。
   只有第 1 個 commit（`9aaefd0` → `23e5cca`）的 `docs/provenance/runtime-patches.json` 有文字衝突：`claude-delivery` 在檔尾加了
   HM-07 的 4 筆（`features.py`、`profiles.py`、`identity_fields.py`、`config.py`），本片也在檔尾加 1 筆。其他 6 個 commit 沒有衝突。
   - `claude-delivery` 在 `32ecac8` 之後沒有動 `redact.py`、`diagnostics.py` 與本片新增的檔（`git diff 32ecac8 origin/claude-delivery`
     對這些檔是空的）。HM-04 改了 `lifecycle.py`（加 `CHILD_PORT`、`child_url`）與 `health.py`（改用 `CHILD_URL`），沒有碰 `ChildLogs`；
     `run_product.py`（HM-04、HM-05 改過）照舊呼叫 `redact.install()` 與 `redact.guard_handlers(*redact.UVICORN_LOGGERS)`，這兩個名字
     本片都沒改。
   - 核對：本片 14 個檔裡，帳本以外的 13 個，內容（blob）和 rebase 前相同。`git range-diff 32ecac8..b124411 origin/claude-delivery..HEAD`：
     第 2～7 個 commit 是 `=`；第 1 個只差帳本衝突處的前後文。
2. 帳本沒有只解文字衝突。用暫存區的一次性腳本（不進 repo）照規則重建：
   - 以 `claude-delivery` 的帳本（55 筆）為底；`scope` 照 `claude-delivery`（本片沒改，HM-06 加的那句在）。
   - 加回本片的 1 筆（`log_redaction.py`，`change` 照原文），放在檔尾（HM-07 的 4 筆後面）。其他 55 筆照 `claude-delivery`，順序也照它。
   - 56 個列管檔的 SHA-256 全部用工作目錄裡合併後的檔重算，全部和帳本相同：`claude-delivery` 的 55 筆一筆都沒變；`log_redaction.py`
     是 `1fec42aa…`，和 rebase 前相同。guarded sources 由帳本預檢與 `tests/test_tool_inventory.py` 核對（第 8.1、8.2 節）。
   - 格式照原檔（`indent=2`、`ensure_ascii=False`、結尾換行）。本片加的那一筆和 rebase 前逐欄相同。
3. tool-surface：本片沒動 `apps/runtime/*.py`、`apps/*/launch.py`，不用 `--write`。`scripts/tool_inventory.py` 檢查模式通過；
   `docs/tool-surface.*` 和 `claude-delivery` 相同。
**第二次（`8e02ac1` → `dc90c32`，HM-13a #97 與文件同步 #96 合併後）**

4. `git fetch origin claude-delivery`（`dc90c32`），`git rebase --onto origin/claude-delivery 8e02ac1`：本片 8 個 commit 依序重放，
   **沒有衝突**；`git range-diff` 8 個都是 `=`。
   - `claude-delivery` 在 `8e02ac1` 之後：#96 只改 `docs/multi-profile/`（含 MF-3 的定案）；#97 HM-13a 新增 `restore_detect.py`，改
     `profiles.py`、`packaging/entrypoint.py`、`packaging/container_probe.py`、兩個 packaging 測試、`tests/test_upgrade_zero_rewrite.py`，
     新增 `tests/test_restore_detection.py`，另有文件與帳本。沒有動本片的 14 個檔，也沒有動 `redact.py`、`diagnostics.py`、
     `lifecycle.py`、`run_product.py`、`gateway.py`、`apps/`、`tests/conftest.py`、`tests/log_scan.py`。
   - 帳本：git 自動合併（HM-13a 在帳本中段加 `packaging/entrypoint.py`、`restore_detect.py` 兩筆，重釘 `profiles.py`；本片那一筆在
     檔尾）。沒有只信自動合併：用同一支一次性腳本照規則重建（以 `dc90c32` 的帳本 57 筆為底、`scope` 照它，加回本片 1 筆），
     58 個列管檔的 SHA-256 全部用合併後的內容重算，全部相符；重建結果和自動合併的帳本逐位元相同，所以不用再改。
   - 本片 13 個非帳本的檔，內容和第一次 rebase 後相同（也和 rebase 前相同）。
   - tool-surface：本片沒動 `apps/`，檢查模式通過。
   - 本筆記：第二次 rebase 後更新到 `dc90c32`，改的是重放過來的第 8 個 commit 本身（本分支這時還沒 push，不用 force push）。

**commit 對照**

5. `git log origin/claude-delivery..HEAD` 只剩本片的 8 個 commit：

   | 最終（`dc90c32` 上） | 第一次 rebase（`8e02ac1` 上） | 原本（`32ecac8` 上） | 標題 |
   |---|---|---|---|
   | `3070841` | `23e5cca` | `9aaefd0` | feat(core): vendor the PaaS log redaction module and its pure tests (HM-02) |
   | `6a23a69` | `e8c6f68` | `f16b041` | fix(core): run the PaaS redaction before the HA rules in log records and child output (HM-02) |
   | `18f72f2` | `b76f5fe` | `d9b3b20` | test(core): put back the logger state the vendored PaaS tests leave behind (HM-02) |
   | `e03f836` | `2775986` | `37fe574` | docs(provenance): add HM-02 multi-profile provenance note |
   | `342567d` | `660f5df` | `1b2be85` | fix(core): catch short hidden values in the guard and decode with the PaaS decoder (HM-02) |
   | `a294697` | `37e1bc0` | `8bee5d8` | fix(core): withhold a child output line when its scrub fails instead of raising (HM-02) |
   | `8043448` | `07773df` | `b124411` | docs(provenance): record the HM-02 review fixes and rechecks |
   | 本筆記這一版 | `96618de` | （新） | docs(provenance): record the HM-02 rebase, the MF-3 and MF-4 decisions and the PaaS change list |

6. 本機檢查見第 8.1 節，兩個預檢見第 8.2 節，PaaS 變動見第 6 節。
