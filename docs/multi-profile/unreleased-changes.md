# 各產品下一版會帶出去、CHANGELOG 還沒記的變更（發版交接清單）

- **用途**：列出每個產品**上一次發版之後**合併進 `claude-delivery`、會跟著它下一版出去，但 `addons/<產品>/CHANGELOG.md` 還沒記的變更，
  每項附 CHANGELOG 建議句子（英文，各產品 CHANGELOG 的語言）。依據是計畫 §11.5（repo 外，
  `artifacts/ha-multiprofile-parity-20261114/PLAN-zh-TW.md`）：任何產品下一次發版，CHANGELOG 都要寫明帶出去的不受開關管變更；
  升版前逐一核對上一版以來合併、但 CHANGELOG 沒記的修正。
- **為什麼別人的改動也會跟著出去**：每個產品的映像都整包複製 `packages/mcp-admin-core`、面板（`packages/mcp-admin-ui`）、`apps/runtime`、
  `packaging/entrypoint.py`、`packaging/management_launcher.py` 與 `docs/provenance/`（見 `apps/<產品>/Dockerfile` 的 `COPY`）。共用程式一改，
  下一個發版的產品就帶出去，不管是哪條工作線改的。
- **誰讀、什麼時候讀**：任何產品的升版 PR（含其他工作線替某個產品發的修補版）開 PR 之前。寫 `addons/<產品>/CHANGELOG.md` 與根目錄
  `CHANGELOG.md` 時照這裡逐項核對，並做第 5 節「發版時要另外驗的事」。
- **怎麼更新**：
  1. 之後每個不受開關管的片，或任何改到映像行為、使用者看得到的修正，在自己的 PR 裡加一項（產品節或共通節）：PR 號、片名、看得到的變化、
     CHANGELOG 建議句子與出處。commit 寫合併 commit；還沒合併就寫「合併後補」，由合併的人或下一個改本檔的 PR 補上。
  2. 受開關管、開關關時逐位元不變的片：只在第 4.2 節加一行說明，不寫 CHANGELOG 句子。
  3. 發版的 PR：句子寫進 CHANGELOG 之後，同一個 PR 改本檔：該產品節的「上次發版」換成新版號與升版 commit，寫進去的自身項目刪掉；
     共通項目在「已發」填產品與版號，適用的產品都發過才刪。
- **基準**：`claude-delivery` `907bd39`（2026-11-17，#117 的合併）。查法、每項出處與沒列進來的變更見
  `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。
- **本檔只管 CHANGELOG**。`upgrade-notes.yaml` 照 `AGENTS.md` 第 3 點與升版比對（`Upgrade comparison`）的要求另外判斷；版號資料照
  `docs/operations/release.md`「升版時要改的版號資料」。
- 「主對話補寫」：該片的筆記沒有英文句子，是照筆記的中文要點或程式照實寫的，最後的英文由發版片定。其他句子照筆記原文。

## 總表（2026-11-17）

| 產品 | 目前版號 | 上次升版 commit | 映像來源 | 要寫進 CHANGELOG 的項目 | 已合併、CHANGELOG 沒記的產品自身修正 |
|---|---|---|---|---|---|
| Odoo | 0.4.13 | `1cbfcb9`（2026-11-08，PR #76） | `4966f40` | 7：A1～A6、B1 | 無 |
| n8n | 0.4.13 | 同上 | `4966f40` | 6：A1、A3～A6（A5 另加一句）、B1 | 無 |
| Hermes | 0.4.13 | 同上 | `4966f40` | 9：A1～A6、B1、H1、H2 | #85（H1）；HM-33 #115（H2） |
| EMQX | 0.4.13 | 同上 | `4966f40` | 10：A1～A6、B1、B2、E1、E2 | #87（E1）；HM-32 #113（E2） |
| LiteLLM | 0.4.13 | 同上 | `4966f40` | 9：A1～A6、B1、B2、L1 | HM-32 #113（L1） |
| Nextcloud | 0.4.13 | 同上 | `4966f40` | 8：A1～A6、B1、B2 | 無 |
| OpenDesign | 0.4.13（只升來源版本，商店停用） | 同上 | 沒有映像 | 8：A1～A6、B1、D1 | #86 的 OpenDesign 部分（D1） |
| Headscale | 0.4.18 | `55f3528`（2026-11-12，PR #88） | `55f3528` | 6：A1～A6 | 無（#77～#88 都已在 0.4.18 的來源裡） |

- 0.4.13：PR #76 在 2026-11-09 合併（`e2108f6`）。六個映像從 `4966f40` 建（`docs/operations/release-decision-0.4.13.md`）；`4966f40` 之後
  #76 只多一個紀錄 commit（`0913611`）。
- Headscale 0.4.18：映像從升版 commit `55f3528` 建（`docs/provenance/headscale-0.4.18-provenance.json`），PR #88 在 2026-11-12 合併（`bb48449`）。
- 2026-11-13 之後沒有任何產品發版。

## 1. 所有產品共通（A：多帳號計畫不受開關管的片）

### A1 HM-02 紀錄遮罩對齊 PaaS（#98，`76c1d78`，2026-11-15）

- 產品：8 個都帶。
- 看得到的變化：add-on log 與診斷頁（子程式輸出）遮得更多。log 裡網址 query 的憑證值顯示 `***`；格式字串和參數對不上的紀錄改顯示
  `[redacted: invalid log message]`。log 與子程式輸出遇到判斷不了的網址編碼、或新規則會露出舊規則藏住的片段時，整段換成
  `[redacted: ambiguous URL encoding]`；超過 128 KiB 的字串截斷。子程式輸出多遮 `key=`，`cache key: x` 這類一般文字也會被遮；遮罩失敗時
  整行顯示 `line withheld (redaction failed)`。`[REDACTED]`、`/private_[REDACTED]` 的格式不變。
- CHANGELOG（主對話補寫；照 HM-02 筆記第 3.4 節與第 12 節第 6 點）：

  ```text
  - Log redaction now applies the PaaS server's rules first and then the add-on's own (PR #98). In the add-on log, credential values in URL query strings show as `***`, and a record whose format string does not match its arguments shows `[redacted: invalid log message]`. In the log and in child output on the diagnostics page, a line whose URL encoding cannot be judged, or where the combined rules would show a part the old rules hid, is replaced as a whole with `[redacted: ambiguous URL encoding]`, and strings over 128 KiB are cut short. Child output also masks `key=` values, so ordinary text such as `cache key: x` is masked too, and a child line whose masking fails shows `line withheld (redaction failed)`. The `[REDACTED]` and `/private_[REDACTED]` forms are unchanged.
  ```

- 已發：—

### A2 HM-06 子程式 bearer（#94，`9c5dd88`，2026-11-15）

- 產品：7 支 Python 子程式的產品（Odoo、Hermes、OpenDesign、EMQX、LiteLLM、Nextcloud、Headscale）。**n8n 不寫**：n8n-mcp 本來就只認同一個
  child token，沒有變。
- 看得到的變化：容器內直連子程式（loopback 3000）時，沒帶、帶錯或多帶 `Authorization: Bearer <child token>` 一律 401、沒有本文；子程式沒有
  有效的 `WOOW_MCP_CHILD_TOKEN` 就不啟動。經 8081 與管理面板的請求不變（閘道、健康檢查、能力探測本來就帶這個 bearer）。
- CHANGELOG（主對話補寫；照 HM-06 筆記第 12.3 節「容器內直連子程式要帶 child bearer」與 `docs/operations/guide.md` 第 6 點）：

  ```text
  - The MCP child on the container's loopback port 3000 now serves only the gateway's own child bearer (PR #94): a direct request inside the container without exactly one `Authorization: Bearer <child token>` header gets HTTP 401 with no body, and the child refuses to start without a valid child token. Requests through port 8081 and the admin panel are unchanged.
  ```

- 已發：—

### A3 HM-13a 還原標記（#97，`dc90c32`，2026-11-15）

- 產品：8 個都帶（`packaging/entrypoint.py`）。
- 看得到的變化：HA 還原這個 add-on 的備份後，第一次啟動在 `/data/mcp` 留下空的 `.restore-detected`（只有擁有者能讀寫），還原修復那一行 log 的
  數字多 1。HM-13b 合併前沒有程式讀或刪它，之後的備份也會帶著。建不出標記時記一行原因（磁碟上有帳號資料就拒絕啟動，今天沒有）。
  沒還原的啟動不變。
- CHANGELOG（照 HM-13a 筆記第 3.4 節原文）。**只適用 HM-13b（#108）合併之前的發版**；之後改寫成 HM-13b 的新行為（第 6 節）。
  不要照抄計畫 §3.3 的表：那是 HM-13b 之後的行為。

  ```text
  - Restore detection (groundwork for multiple profiles): after Home Assistant restores this add-on's backup, the first
    start leaves an empty, owner-only marker file `.restore-detected` in `/data/mcp`, and the restore repair log line
    counts it (`re-owned N restored entries`). A later version reads and removes it; until then it stays, also in later
    backups. If the marker cannot be saved, that start logs one line with the reason (an errno name such as `ENOSPC`, or
    `name in use`); with multi-profile data on disk (none today) the start is refused and retried at the next start.
    Starts without a restore are unchanged.
  ```

- 已發：—

### A4 HM-14 子程式 initialize 錯誤的遮罩（#103，`7c6f80c`，2026-11-16）

- 產品：8 個都帶。HM-14 其他部分受開關管（第 4.2 節）。
- 看得到的變化：子程式對 initialize 回的 JSON-RPC 錯誤裡，出現本 add-on 自己的憑證（MCP token、child token、後端秘密欄位與它們的 Basic 形式）時，
  那幾段換成 `[REDACTED]`（`Content-Length` 跟著變）。其他轉回子程式或後端文字的路徑本來就遮；錯誤裡沒有憑證時逐位元照舊。
- CHANGELOG（主對話補寫；筆記沒有英文句子，照契約第 1.2 節 HM-14 那段）：

  ```text
  - If the MCP child answers `initialize` with an error that contains this add-on's own credentials (the MCP token, the child token, a backend secret or its Basic form), those parts now reach the client as `[REDACTED]`, as every other text the gateway passes on from the child or the backend already did (PR #103). Status codes and other headers are unchanged; an error without credentials is returned exactly as before.
  ```

- 已發：—

### A5 HM-31 請求內容位元組預算與 JSON 結構守門（#105，`7ac41aa`，2026-11-16）

- 產品：8 個都帶；n8n 另加一句。
- 看得到的變化：超過 64 KiB 的大請求放不進預算時回 `-32003`；大請求 30 秒沒有新位元組回 408；巢狀超過 64 層或元素超過 20 萬的 JSON、
  不是 UTF-8 的 body 在解析前被拒；宣告超過 16 MiB 的改在讀之前回同一個 413（8099 也是）；每種拒收每分鐘一行 WARNING。
  上限內的請求逐位元照舊。逐項見契約第 1.2 節 HM-31 那段。
- CHANGELOG（照 HM-31 筆記第 8 節原文，`#NNN` 換成 `#105`）：

  ```text
  - Gateway request limits aligned with the PaaS server (PR #105): a request body over 64 KiB is read under a byte budget derived at startup from the container's memory limit, or from MemAvailable less 256 MiB when there is none (at least 16 MiB, at most 64 MiB for the add-on's profile). What counts is the larger of the body as received and as forwarded to the add-on's MCP server, which escapes non-ASCII text, so Chinese text counts about twice its size and emoji about three times (with the smallest 16 MiB share, a 6 MiB body of emoji is refused); a Content-Length sent together with Transfer-Encoding is ignored and the bytes that arrive are counted. A large body the budget cannot hold is answered with JSON-RPC error -32003 and `Retry-After: 5` (HTTP 200 under its id when its head or tail shows it, else 503) instead of being processed, and one that sends nothing for 30 seconds is dropped with HTTP 408 (`-32003`, `Connection: close`); the 60-second whole-read limit and its 408 are unchanged. A body that declares more than 16 MiB gets the same HTTP 413 as before, now before any of it is read. A JSON body nested deeper than 64 levels or with more than 200,000 elements is refused before it is parsed (HTTP 200 with `-32602` under its id when its head or tail shows it, else 413); so is a body that is not UTF-8 (UTF-16 and UTF-32 bodies were processed before; invalid UTF-8, and malformed JSON with that much structure, got HTTP 400 before). Requests within these limits are answered exactly as before; each kind of refusal writes one warning a minute.
  ```

  n8n 另加：

  ```text
  - n8n: a body nested deeper than 64 levels now gets HTTP 200 with `-32602` under its id (it was 413 with a null id), and a body that is not UTF-8 gets the encoding refusal (it was 400 with `-32700`).
  ```

- 已發：—

### A6 HM-09 追補：健康監看一定照停止要求停下（#106，`df686dd`，2026-11-16）

- 產品：8 個都帶（使用者 2026-11-16 13:4x 定「全部產品都修」）。
- 看得到的變化：停止 add-on 時，極少數情況下健康監看吃掉停止要求，一直等到 HA 的 30 秒停止上限被強制結束；現在那次檢查做完就停、
  照順序關完。8081、8099 的回應、健康狀態與 log 不變。
- CHANGELOG（照 HM-09 追補筆記第 4 節原文）：

  ```text
  - Fixed: stopping the add-on could wait for Home Assistant's 30 s stop timeout in rare cases.
  ```

- 已發：—

## 2. 0.4.13 這條線共通（B：Headscale 以外的 7 個產品）

Headscale 那條線改了共用程式，Headscale 自己已經發版、CHANGELOG 也記了；其他 7 個產品還在 0.4.13，下一版才帶出去。

### B1 管理員驗證接受 HA Core 2026.11.0、2026.11.1（#81，`d1cfd6c`，2026-11-11）

- 產品：Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud、OpenDesign。Headscale 從 0.4.14 起就有，已記在它的 CHANGELOG。
- 看得到的變化：0.4.13 的管理員驗證只認到 Core 2026.10.4。在 Core 2026.11.x 上，管理面板拒絕每個請求（顯示 Core 版本還沒審查的頁面，
  add-on log 記一行），MCP 端點不受影響。下一版起接受 2026.11.0 與 2026.11.1；之後的 2026.11 修補版與預覽版仍拒絕，要另外審查。
- CHANGELOG（主對話補寫；照 Headscale 0.4.14 的 CHANGELOG 與 `ha_role.py` 的說明）：

  ```text
  - The administrator check now accepts Home Assistant Core 2026.11.0 and 2026.11.1, reviewed against the same 25 Core contract and adjacent files as Headscale 0.4.14 (PR #81). Version 0.4.13 refuses every admin panel request on Core 2026.11.x; later patches and pre-releases stay refused until reviewed. MCP endpoints do not use this check.
  ```

- 已發：—

### B2 面板「儲存工具政策會重啟子程式」的提示變短（#77，`069b681`，2026-11-11）

- 產品：EMQX、LiteLLM、Nextcloud（工具政策在子程式啟動時套用的三個產品）。
- 看得到的變化：提示從「儲存後會重新啟動 MCP 子行程（這個產品的工具政策在子行程啟動時套用），現有連線可能中斷。」改成「儲存後會重新啟動
  MCP 子行程，現有連線可能中斷。」#77 其餘的共用改動只為 Headscale 加表項，別的產品不變。
- CHANGELOG（主對話補寫；只是文字，要不要寫由發版片定）：

  ```text
  - The admin panel's notice after a tool-policy save is shorter: it says the MCP child restarts and existing connections may drop, without the reason in parentheses (PR #77).
  ```

- 已發：—

## 3. 各產品

每個產品要寫的共通項目見第 1、2 節；這裡列上次發版、產品自己的項目與發版時要另外驗的事（每個產品都要做的見第 5 節）。

### 3.1 Odoo

- 上次發版：0.4.13（升版 commit `1cbfcb9`；映像來源 `4966f40`）。
- 要寫：A1～A6、B1（7 項）。
- 自己的修正：沒有。`apps/odoo`、`addons/odoo` 在 0.4.13 之後沒改。Odoo 專屬的 HM-12（#110、#114：換身分換 token、新來源重填秘密）受開關管，
  開關關時沒有可見變化（第 4.2 節）。
- 發版時另外驗：第 5 節。

### 3.2 n8n

- 上次發版：0.4.13（同 Odoo）。
- 要寫：A1、A3、A4、A5（含 n8n 那一句）、A6、B1（6 項）。A2 不寫。
- 自己的修正：沒有。`apps/n8n` 的兩次改動都沒有可見變化：HM-04（#91，port 參數化，預設 3000 時 `PORT` 照舊）、HM-20（#102，開通後才拒絕
  loopback 與檢查存檔）。
- 發版時另外驗：第 5 節。另外，n8n 若自己升版號（不跟預設版號一起升），`apps/n8n/run.py` 沒傳 `product_version`，`serverInfo` 與面板會報
  預設版號，HM-17 的升版模擬會擋：先改 `run.py` 與相關測試（HM-17 筆記第 12 節）。

### 3.3 Hermes

- 上次發版：0.4.13（同 Odoo）。
- 要寫：A1～A6、B1、H1、H2（9 項）。
- 發版時另外驗：第 5 節。另外兩件交發版片定（HM-33 筆記第 13、15 節）：`addons/hermes/README.md` 或 `DOCS.md` 要不要補「Hermes Agent v0.17.0
  or v0.22.x」那句（照抄要寫成 PaaS 的正式站跑 v0.22.5，不是 HA 的）；trigger 會把停用的排程改回啟用是 Hermes 的上游行為，HA 沒有實測。

#### H1 `hermes_cron` create 帶 `enabled=false` 時同時送 `paused`（#85，合併 `b68e437`，commit `b50f1c7`，2026-11-12）

- 看得到的變化：發行的 0.4.13 只送 `enabled`；照 PaaS，現在的 Hermes 只讀 `paused`，所以 `enabled=false` 建出來其實是啟用的。下一版起同一個 POST
  另送 `paused`，建出來才真的是停用的。
- CHANGELOG（照 HM-33 筆記第 13 節原文）：

  ```text
  - `hermes_cron` `create` with `enabled=false` now also sends `paused: true` in the same request, as the PaaS server does (woow-mcp-server #138; PR #85). Per PaaS, current Hermes reads only `paused`, so such a job used to be created enabled. If a backend refuses the extra field (HTTP 422), the add-on reports that error and does not send a second request without it.
  ```

#### H2 HM-33 `hermes_cron` 的說明補兩句（#115，`f239157`，2026-11-17）

- 看得到的變化：用戶端看到的 `hermes_cron` 說明多兩句（tools/list 回答多 187 位元組；8099 `/api/capabilities` 的同一個欄位，面板的工具頁）。
  程式行為不變。
- CHANGELOG（照 HM-33 筆記第 13 節原文；原文沒寫本 repo 的 PR 號，要不要照前例加 `PR #115` 由發版片定）：

  ```text
  - The `hermes_cron` description now says two things Hermes does, as the PaaS server's description does (woow-mcp-server #156): `create` with `enabled=false` makes the job paused, so it does not run until resumed; and Hermes v0.22.x also resumes a paused job when it is triggered (Hermes's own behaviour, which PaaS measured on Hermes Agent v0.22.5), so call `pause` afterwards if it should stay paused. Text only: this change alone changes no tool name, input or output schema, grant, request or reply.
  ```

### 3.4 EMQX

- 上次發版：0.4.13（同 Odoo）。
- 要寫：A1～A6、B1、B2、E1、E2（10 項）。
- 發版時另外驗：第 5 節。

#### E1 `emqx_test_rule_sql` 標成需要寫入權限（#87，合併 `14578a7`，commit `a4f4439`，2026-11-12）

- 看得到的變化：用戶端看到的標題改成「Test EMQX Rule SQL (write permission)」，`readOnlyHint`、`idempotentHint` 改成 false。閘道本來就把它當
  寫入、要寫入授權；`POST /rule_test` 的參數、輸出 schema 與預設授權都沒變。
- CHANGELOG（主對話補寫；照 `docs/provenance/emqx-sql-write-hint-parity-20261112.md`）：

  ```text
  - `emqx_test_rule_sql` is now labeled as needing write permission, matching the write grant the gateway already required for it (PR #87): its title is "Test EMQX Rule SQL (write permission)" and `readOnlyHint` and `idempotentHint` are false. Its request (`POST /rule_test`), inputs, output schema and default grants are unchanged.
  ```

#### E2 HM-32 EMQX 不保留閒置的 broker 連線（#113，`a709b97`，2026-11-17）

- 看得到的變化：沒有。HA 實際上本來就每個請求開新連線（`backend_policy` 丟掉產品給的 `limits`），本片只對齊設定；使用者 2026-11-17 02:3x 決定
  CHANGELOG 照樣記一行、寫明行為不變。
- CHANGELOG（照 HM-32 筆記第 12 節原文；原文沒寫本 repo 的 PR 號，要不要加 `PR #113` 由發版片定）：

  ```text
  - The EMQX client's connection pool now asks for no idle broker connections, as the PaaS server does (woow-mcp-server #135): every request opens a fresh connection and nothing is retried, so the first request after a network outage never waits on a stale connection. The add-on's backend policy already kept no idle connection, so behavior does not change.
  ```

### 3.5 LiteLLM

- 上次發版：0.4.13（同 Odoo）。
- 要寫：A1～A6、B1、B2、L1（9 項）。
- 發版時另外驗：第 5 節。

#### L1 HM-32 LiteLLM 不保留閒置的後端連線（#113，`a709b97`，2026-11-17）

- 看得到的變化：沒有（理由同 E2）。
- CHANGELOG（照 HM-32 筆記第 12 節原文；PR 號同 E2）：

  ```text
  - The LiteLLM client's connection pool now asks for no idle backend connections, as the PaaS server does (woow-mcp-server #139): every request opens a fresh connection and nothing is retried, so the first tool call after a network outage never waits on a stale connection. The add-on's backend policy already kept no idle connection, so behavior does not change.
  ```

### 3.6 Nextcloud

- 上次發版：0.4.13（同 Odoo）。
- 要寫：A1～A6、B1、B2（8 項）。
- 自己的修正：沒有（`apps/nextcloud`、`addons/nextcloud` 在 0.4.13 之後沒改）。
- 發版時另外驗：第 5 節。

### 3.7 OpenDesign（商店停用，只升來源版本）

- 上次發版：0.4.13 只升來源版本（升版 commit `1cbfcb9`），沒有建映像，也沒有 HAOS 驗收。下一版照它的前例寫「source only (disabled)」，
  共通項目照樣寫（0.4.12 前例：共用的 #70 寫成「applies to its child too」）。
- 要寫：A1～A6、B1、D1（8 項）。
- 發版時另外驗：沒有映像，第 5 節的映像項目不適用；商店開放它的那一版才全部適用。

#### D1 `read_file` 公開輸出 schema（#86，合併 `3f1c292`，commit `1613be1`，2026-11-12）

- 看得到的變化：公開 tools/list 的 `read_file` 多一個輸出 schema（物件，含字串 `result`），照釘選的子程式宣告；子程式的 schema 或受審來源變了，
  閘道照樣省略。其他 OpenDesign 工具的子程式沒有宣告，照舊沒有。#86 的 Headscale 部分已在 0.4.18 發出。
- CHANGELOG（主對話補寫；照 `docs/provenance/headscale-opendesign-output-schema-parity-20261112.md`）：

  ```text
  - `read_file` now lists the output schema its pinned child declares (an object with a `result` string), reviewed and pinned in PR #86; the gateway still omits it if the child's schema or the reviewed source changes. Source only: OpenDesign stays disabled in the Store.
  ```

### 3.8 Headscale

- 上次發版：0.4.18（升版 commit＝映像來源 `55f3528`）。
- 要寫：A1～A6（6 項）。0.4.18 的來源 `55f3528` 已含 #77～#88（B1、B2 也在內），Headscale 該寫的已寫進它的 CHANGELOG。
- 自己的修正：沒有（`apps/headscale`、`addons/headscale` 在 `55f3528` 之後沒改）。
- 發版時另外驗：第 5 節。

## 4. 沒有可見變化的片（不用逐項寫 CHANGELOG）

### 4.1 不受開關管、但對沒開通的產品看不到

| 片 | PR | commit | 為什麼看不到 |
|---|---|---|---|
| HM-04 子程式 port 參數化 | #91 | `e5e6e74` | 預設 3000 時子程式的 argv、env、cwd 和以前逐位元相同（快照 `tests/contract/child_spec_default.json`） |
| HM-05 每帳號執行套件 | #95 | `8e02ac1` | 預設帳號的行為逐位元不變，`/data/mcp` 不多任何檔 |
| HM-07 帳號資料層 | #93 | `e5fa5c7` | 函式庫還沒接進開機流程；`MULTI_PROFILE_PRODUCTS` 是空集合 |
| HM-11 收據格式 | #107 | `f4c7718` | 預設帳號的收據 key 與 4 個鍵的紀錄不變 |
| HM-17 發版基礎 | #92 | `56f22f7` | 只改發版工具（`packaging/`、workflow），不在映像裡；影響發版步驟（第 5 節第 6 點） |

### 4.2 受開關管：開關關時沒有可見變化

這些片的程式都在映像裡，但 `MULTI_PROFILE_PRODUCTS` 是空集合，沒有產品開通，**開關關時沒有可見變化**：`state.json` 位元組不變、不產生新檔、
bootstrap 不變、兩條 MCP 網址同一把 token 同一組錯誤碼、名額／看門狗／健康檢查／管理管線照舊（計畫 §3.3、§7.1）。各片產品開通後的改變，
由該產品的升版片照計畫 §7.2 寫進 CHANGELOG。

| 片 | PR | commit | 映像多帶了什麼 | 開關關時 |
|---|---|---|---|---|
| HM-08 | #99 | `b5d10c5` | MCP token 路由、每帳號准入與位元組額度、過載回應、回覆遮罩聯集 | 不掛分派器、不讀索引；8081 回應逐位元照舊 |
| HM-09 | #101 | `c523474` | 子程式生命週期（port、看門狗、錯開啟動、監看退避） | 看門狗照舊（同一次啟動最多 4 次後 failed），監看照舊每 15 秒、不退避 |
| HM-20 | #102 | `269f5a5` | 後端網址拒絕 loopback（存檔與子程式） | 子程式不帶 `WOOW_MCP_DENY_LOOPBACK`，存檔不擋 loopback |
| HM-14（A4 以外） | #103 | `7c6f80c` | 排隊上限、保留名額、`-32004`／`-32005` | 轉送名額逾時仍 503、子程式斷線仍 502、token 換掉時照舊 |
| HM-10 | #104 | `d00a338` | 管理 API 的帳號路由與共用管線 | 管理 API 一個位元組都不變：`/api/profiles*` 照舊 404、不要求 `X-MCP-Profile` |
| HM-11 面板 | #107 | `f4c7718` | 帳號選單、切換、回聲、建立後切換 | 面板畫面與送出的請求不變（HM-11 筆記：72 個比較 0 差異） |
| HM-12 | #110 | `7646f0f` | Odoo 換身分換 token、新來源重填秘密（後端） | 換身分不換 token，回應沒有新欄位 |
| HM-30 | #111 | `ebefebe` | 回覆處理工作執行緒、待送回覆額度、健康檢查容忍 | 不建工作執行緒，回覆照舊在事件迴圈處理 |
| HM-12 面板 | #114 | `165dbaf` | 換 token 的提示、新來源重填秘密的表單 | 面板畫面、請求與提示不變（HM-12 面板筆記：216 個比較 0 差異） |

要用一句話交代第 4 節（可選；主對話補寫，照計畫 §3.3、§7.1）：

```text
- This image also carries the groundwork for multiple profiles per add-on (PRs #91, #93, #95, #99, #101–#104, #107, #110, #111 and #114). It stays switched off for this add-on: requests, responses, the admin panel and the files in `/data/mcp` are unchanged apart from the changes listed above.
```

## 5. 發版時要另外驗的事（每個發映像的產品；計畫 §11.5）

1. 走完整的既有發版流程，不能只看單帳號黃金回歸（HM-05、HM-06 合併後的規定）。
2. 該產品的 HAOS P9 回歸（`docs/operations/ha-p9-kit.md`；要用主機的步驟照既有規定先取得負責人同意）。
3. builder 容器驗收（`supply_chain.py candidate` → `container_acceptance.py` 跑 `packaging/container_probe.py`）這兩段都要過，不要放寬：
   - 子程式 bearer 的直連 401 檢查（`assert_child_bearer`；n8n 驗 n8n-mcp 的同一個 child token）。
   - HM-13a 的 root 還原樹（Supervisor 式還原後的啟動：標記在、還原項目改回 10001、`state.json` 位元不變）。
   - 這兩段還沒在真容器跑過：第一次是 HM-19a 前的 builder 乾跑或這次發版，看哪個先。失敗時先查探針與 entrypoint（HM-06 筆記第 12.3 節、
     HM-13a 筆記第 11 節）。
4. HA Core 版本：管理員驗證只認到 2026.11.1（B1）。目標 HAOS 的 Core 比它新，要先補審（計畫 §11.3 的升版 PR 清單：`Hc/ha_role.py` 與
   `docs/ha-role-core-contract.md`），不然面板拒絕每個請求。
5. HM-31 的預算常數是暫定（契約第 5 節）。那裡的「HM-19c 放行條件」（在目標硬體量閘道＋子程式的放大倍數與 MemAvailable，不過就不能發版）
   是為 Odoo 首發寫的，但 A5 不受開關管，任何產品下一版都會帶出去。HM-19c 量測之前要發版，先請負責人決定要不要先量。
6. 版號資料 7 處照 `docs/operations/release.md`「升版時要改的版號資料」；readiness 只認該產品自己的
   `docs/operations/release-decision-<產品>-<版號>.md`（HM-17）。
7. 發版鎖：同一時間只有一個凍結中的升版 PR（含其他產品的修補版；計畫 §11.5）。
8. 根目錄 `CHANGELOG.md` 照前例寫這一版包含哪些 PR（例如 0.4.13 那段的「Includes the merged post-0.4.12 source changes in PRs #73–#75」）。

## 6. 還沒合併、合併後要來改本檔的片（2026-11-17）

| 片 | PR | 不受開關管的部分 | 合併時要改本檔的地方 |
|---|---|---|---|
| HM-13b | #108 | 開機守門的存在檢查、休眠處理（計畫 §3.3） | 開機時刪還原標記並記一行 WARNING：A3 的句子只適用 HM-13b 之前的版本，照 HM-13b 筆記的交接改寫 A3 |
| HM-13c | #112 | 單帳號還原後的面板提示（使用者 2026-11-16 定案） | 加一個共通項；CHANGELOG 句子在 HM-13c 筆記交 HM-19a 的那一段 |
| HM-16 | #109 | 驗收工具（`packaging/`） | 沒有可見變化，加到第 4.1 節 |
| HM-27 | #116 | 無（受開關管，report-only） | 加到第 4.2 節 |
