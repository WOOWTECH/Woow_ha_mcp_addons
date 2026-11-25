# HA provenance：同月份修補版自動放行的獨立安全審查與真實 Core 驗證（2026-11-25）

## 結論

- **獨立安全審查（審查者不是作者）：修正後通過。** 程式不需要改；必修 4 項（M1–M4）全是文字與紀錄，這個分支都處理了；建議 7 項（S1–S7）採用
  S1、S2、S3、S7，S4、S5 不做（交負責人決定），S6 維持。逐項見第 3、4 節。負責人的條件是「同月份修補版自動放行」放進維修版之前先做這項審查
  （`docs/multi-profile/decisions.md` DQ-35）：已做。
- **真實 Core 驗證（主對話）：通過。** 用 PyPI 的官方 `homeassistant` 2026.11.3、2026.11.2、2026.11.0，前面接照 Supervisor 2026.11.0 `api/proxy.py`
  （git blob `cab849dc`）寫的代理替身，對維修版的 `ha_role.py`（git blob `2bab641a`，就是現在分支上的這一份）：真 2026.11.3 上 67／67 項全過，
  2026.11.2 與 2026.11.0 各 30／30 項全過；修正前的 `ha_role.py`（git blob `ea5ad34e`，`092b1b5`）在真 2026.11.3 上拒絕擁有者與一般使用者，而且送權杖
  之前就拒絕。第 5 節。
- **規則的實際範圍**：規則對每個已審查月份都成立（2026.7.9、2026.10.9 這類也會放行；修補號最多三位數，所以 2026.11.999 也放行），這是程式註解寫的設計。
  但 HA 已不再出舊月份的修補版（最後是 7.4、8.3、9.4、10.4），實際效果只在 2026.11.4 起。

## 1. 審查範圍與方法

| 項目 | 內容 |
|---|---|
| 受審的 commit | `092b1b5..40574ce` 的 4 個：`529c8c0`（放行規則與 2026.11.3）、`131d1a9`（審查紀錄與文件）、`635f800`（面板讀弱 ETag，F2）、`40574ce`（F2 的文件）。`40574ce..3bcfa1f` 沒有動到受審的檔案（只有 EMQX 的 `emqx_list_topics` 說明），`3bcfa1f` 的 CI（`checks`、`readiness`、`Upgrade comparison`）全綠：pytest 7,024 過、Node 單元測試 122 過、Playwright 168 過 |
| 審查的事項 | 放行規則是否精確、風險與 HA Core 修補版的歷史、2026.11.3 逐版審查的證據、F2 弱 ETag、文件與測試、commit 掃描（作者、AI 署名、秘密、不可動的檔、帳本） |
| 差分與模糊 | 獨立寫的預期集合（只依負責人的決定與文件表格，不看 `ha_role.py`）對照：年 2018–2031、月 −1…15、修補 −1…1104 共 263,228 條字串 0 不符；25 萬條模糊字串（含各種文字的數字、空白與控制字元、NUL、`v` 前綴、b／rc／dev 後綴）0 不符，放行的 810 條不同字串全是 ASCII 的 `2026.(7..11).N`；21 個審過版本的單字元編輯鄰居 10,109 條 0 不符；端到端 722 種組合（19 個版本字串 × 19 個版本字串 × 2 種角色答案）：「有送權杖」恆等於「`auth_required` 的版本被接受」，「有送 `config/auth/list`」恆等於「兩邊版本都被接受且相等」 |
| 狀態機與並行 | 真 loopback WebSocket：同一個驗證器連續 450 個連線（隨機版本對與使用者記錄）、9 步翻轉序列（同一使用者角色變動、版本在放行與拒絕間來回）、12 波各 8 個並行、第 9 個並行被拒且不建連線、卡在 hello 或 result 都在 2.9 秒內關閉 |
| 突變 | Python 23 個、JavaScript 10 個。作者的測試殺 21 個，審查者另寫的檢查殺 17 個，兩套合起來只剩 2 個活下來：`>` 改 `>=`（在驗證器這一層是等價突變，見 S3）與放行 log 放到送權杖之後（與授權無關）；JavaScript 的 10 個全被 122 個單元測試殺掉 |
| Core 修補版歷史 | 2026.7.0 到 2026.11.3 的 18 個相鄰修補區間（642 個 commit、1,340 筆檔案異動）：`components/config/auth.py`、`components/config/__init__.py`、`components/websocket_api/` 全部、`auth/models.py`、`auth/permissions/__init__.py`、`auth/const.py`、`auth/auth_store.py` 一次都沒被改過；Supervisor 2026.07.0 到 2026.11.0 的 18 個 tag 的 `api/proxy.py`，三個 frame（`auth_required`、`auth_ok`、`auth_invalid`）的程式行每一版都相同 |
| 2026.11.3 的證據 | `ha-core-2026-11-3-blobs.json` 的 25 個檔，每個檔在 2026.11.2 與 2026.11.3 兩個 tag 都重新下載、自己重算 git blob，共 50 次，與 JSON 和 GitHub git trees 三方比對 0 不符；`compare` 43 個 commit、76 個檔與文件相同；`indieauth.py` 與 `core_config.py` 的 diff 讀過，都不在 `config/auth/list` 的路徑上 |
| F2 弱 ETag | 面板送出的 `If-Match` 仍是強形式（10 種帶 `W/`、引號、空白、換行的 revision 全在送出前被拒）；伺服器三處比對（索引 `p1-`、Origin 政策 `o1-`、帳號 `c1-`）沒改、沒放寬；6,780 個 ETag 標頭對獨立預期集合 0 不符；revision 是伺服器用程序金鑰對內容算的 HMAC，弱 ETag 被污染時寫入衝突保護不會失效 |

## 2. 為什麼可以過

1. 放行規則只決定「可以對哪些 Core 版本發問」。管理員判斷本身（`ha_role._allowed`）一個字沒動；`ha_role.py` 的 diff 是 +67／−9，`ui.py` 是 +2／−1，只加了版本閘門、
   一個 log 函式與 `__call__` 裡的兩行呼叫。
2. 現有資料下不會把非管理員當管理員：定義這個判斷的檔案在 18 個相鄰修補區間一次都沒被改過（第 1 節）。
3. F2 只改面板「怎麼讀 revision」，送出的 `If-Match` 仍是強形式，伺服器的比對沒放寬。

## 3. 必修（M1–M4）與處理

| 編號 | 審查發現 | 處理 |
|---|---|---|
| M1 | 契約把「Core 只對管理員建立 `panel_admin` 面板的 Ingress 工作階段」寫成獨立防線，事實不成立：Core 專用指令的檢查（`_async_check_ingress_access`）從 2026.11.0 才有，而且可經通用的 `supervisor/api` 繞過；真正擋人的是 Supervisor 2026.10.2 起每個 Ingress 請求的 `panel_admin` 檢查，它與 add-on 讀同一份 `config/auth/list`，兩者不獨立 | **採用。** 契約「Later patch releases of a reviewed month」改寫成事實，附上游行號與版本邊界（這次重新下載上游檔案逐一核對過）；`ha-core-2026-11-3-blobs.json` 的 `also_read[0].why` 是同一個說法，一併改；寫明今天實際新增的曝險只有 2026.11.4 起 |
| M2 | 靜態拒絕頁（`ui.py`）寫「這個 Core 版本不是（新的月份、……）」，看到這一頁的人正好就是括號裡那幾類，意思寫反了 | **採用。** 改成「不在這兩類之內（它是……）」，`test_the_unreviewed_core_page_is_static_text` 補斷言（先紅後綠） |
| M3 | 審查結果還沒記進紀錄（`decisions.md` 寫「尚未做」「結果待補」，契約用過去式寫「was reviewed separately」） | **採用。** 本筆記、`decisions.md` 的 DQ-35 兩處、`unreleased-changes.md` 的 A10、契約那一句改成現在式事實，七份發佈紀錄的關卡與驗收表 |
| M4 | 「帳號清單也受影響」與實測不符：真 HA 加 Cloudflare 上只有 `api/origin-policy` 變弱，`api/profiles` 仍是強的；舊說法會被抄進之後 n8n、Hermes、Headscale 開通那版的 CHANGELOG | **採用。** `unreleased-changes.md` 的 A11（含英文建議句）與 `packages/mcp-admin-ui/README.md` 已改成實測事實；`profiles.test.mjs`、`profiles.spec.mjs`、`fixtures/server.mjs` 三處把「清單變弱」歸因於 Cloudflare 的註解改成「模擬代理」。程式的共用讀法保留（風險為零，改了會牽動 UI 測試與帳本）。`635f800`、`40574ce` 的 commit 內文是歷史，不改，PR 描述寫更正 |

## 4. 建議（S1–S7）與處理

| 編號 | 建議 | 處理 |
|---|---|---|
| S1 | 契約補最壞情況、偵測、回復 | **採用。** 誤放行的人能 `token/reveal`、`token/rotate`、改後端連線與憑證、改工具政策；偵測只有 add-on log 的一行；沒有執行時開關，只能發新版或停 add-on |
| S2 | 威脅模型第 3 節沒有這項新接受的風險 | **採用。** `threat-model.md` 第 3 節新增一條（窗口、最壞、防線、偵測、回復），與契約一致 |
| S3 | 測試補強：函式層釘住 `>`；`_HA_VERSIONS` 每個元素都符合 `_PATCH_RELEASE`；寫明清單只收 `年.月.修補` | **採用。** `tests/test_ha_role.py` 補兩條，契約「Adding a release」步驟 3 寫明。**沒有動 `ha_role.py`**：第 5 節的真實 Core 驗證與這次審查測的就是這個檔案（blob `2bab641a`），位元組不變 |
| S4 | 可選：規則只對有 Core 側專用檢查的月份（2026.11 起）生效，或在文件寫明舊月份已不再出修補版 | **不做，交負責人決定。** 實際效果幾乎為零（HA 不再出舊月份修補版）；改規則要動程式與測試。文件已寫明今天的實際曝險與「每個已審月份都成立」 |
| S5 | 可選：在面板 diagnostics 加唯讀一行，讓人看得到「被規則放行、沒有逐版審查」 | **不做，交負責人決定。** 不影響授權；要動面板與 diagnostics 的格式（帳本與面板測試重跑）。目前偵測只有 add-on log，契約與威脅模型已寫明 |
| S6 | `_report_later_patch` 先 `add` 再 `print`，stderr 寫入失敗時那次請求被拒 | **維持。** 屬 fail-closed：被拒的那次權杖還沒送出，之後的請求正常（審查者用壞掉的 stderr 實測：第一次 `False`，之後 `True`） |
| S7 | 契約 #111 與第 10 節補 F2 一行 | **採用。** `contract.md` 第 9 節 #111 補面板讀弱 ETag 與實測，第 10 節補一列（與 S1、S2 同一個 commit） |

## 5. 真實 Core 驗證（主對話，2026-11-25）

用本機的 Python 套件跑真的 Home Assistant Core，經 Supervisor WebSocket 代理的替身驗證 `ha_role`。沒有碰叢集、展示機與 GitHub。

| Core | PyPI wheel sha256（下載後與 PyPI 的 digests 逐一比對一致） | 執行中 Core 回報的版本（WS `auth_required`／`auth_ok`、`GET /api/config`） | 結果 |
|---|---|---|---|
| 2026.11.3 | `1812e29d14ae2554…fd97348d` | 2026.11.3 | 維修版 67／67 全過 |
| 2026.11.2 | `7a026d4324a59b9f…58800cc0` | 2026.11.2 | 維修版與修正前各 30／30 全過（相容沒有退步） |
| 2026.11.0 | `7ca5fbde9dea879a…391b00f7` | 2026.11.0 | 維修版與修正前各 30／30 全過（相容沒有退步） |

- **替身**：依 Supervisor 2026.11.0 的 `api/proxy.py`（git blob `cab849dc`）：先送 `auth_required`、收 `auth`、驗機器權杖、送 `auth_ok`（同版本），之後才連 Core 並雙向轉送。
  被測程式是 `git archive` 取出的 `ha_role.py`：維修版（blob `2bab641a`）與修正前 `092b1b5`（blob `ea5ad34e`，白名單到 2026.11.2、沒有 `_later_patch`），只把 `ha_role._URL` 換成替身位址。
- **真 Core 2026.11.3 的 `config/auth/list`**：擁有者與一般管理員允許；一般使用者、唯讀使用者、停用的管理員、系統帳號（含 `system_generated` 且在管理員群組、啟用的帳號：只靠
  `system_generated` 條件擋住）、不存在的 id 都拒絕；空字串、含逗號、含空白、超長的 id 不連線就拒絕；改角色或停用後，同一個驗證器的下一次查詢立刻反映，每次都是新連線，沒有快取。
- **修正前在真 2026.11.3 上**：拒絕擁有者與一般使用者，送權杖之前就拒絕（`Unreviewed('2026.11.3')`）。同一個真 Core，只把替身宣告的版本改成已審查的 2026.11.2，修正前的程式就
  放行擁有者、拒絕一般使用者：被鎖的唯一原因是版本白名單，`config/auth/list` 的資料契約在真 2026.11.3 沒變。
- **版本字串**（替身宣告、真 11.3 的資料路徑）：2026.11.4、2026.11.10、2026.11.999、2026.10.9 放行並各記一行 log，一般使用者仍被拒；2026.12.0、2026.11.4b0、2026.11.04、空字串、`null`、
  `v` 前綴、前後空白、尾端換行、第四段、rc、dev、月份 13 與 0、月份補零、四位數修補號、2026.7.1、未審年份、全形數字、負號、數字與陣列與物件型別，一律在送權杖之前拒絕；
  `auth_required` 與 `auth_ok` 版本不同時不再送 `config/auth/list`；三種逾時各約 2.25 秒拒絕；同一個驗證器內每個放行版本只記一行 log，且不含權杖與使用者 id。
- **限制**：沒有真的 2026.11.4 以上的 Core（尚未釋出），後續修補版規則是用替身宣告版本字串加真 11.3 的資料路徑驗的；替身不是真的 Supervisor；沒有跑 `hassio` 整合；
  只驗了 `ha_role` 這一層，沒有驗面板的 `admin_auth.denial_detail` 顯示、閘道的 3 秒保護與並行上限 8；驗證用 Python 3.13.11，正式映像是 3.13.18（函式庫版本與鎖檔一致）。
  結果檔與驗證程式在 repo 外，不含任何憑證。

## 6. 審查沒有驗證到的事

- 真 HA 加真 Cloudflare 的行為：用主對話的實測，審查者沒有親測；Playwright 瀏覽器測試本機沒有 Chromium，以 CI 的 168 過為準。
- `test_real_n8n_executable_tcp_uses_production_factory` 與 `test_credentials_and_peer_listener_separation`：審查者的機器沒裝 n8n 執行環境而失敗，以 CI 的 pytest 7,024 過為準。
- Supervisor 2026.10.2 到 2026.10.4 的 `api/ingress.py` 只用 grep 確認請求時檢查出現的版本邊界，沒逐行讀差異；Supervisor 快取使用者記錄造成降權不立即生效的行為沒驗（與本變更無關）。
- 沒逐行讀的 Core 修補版：`hassio/update.py`（+1）、`hassio/strings.json`、2026.10.0→10.1 的 `auth/indieauth.py`（+51／−12）；都不在 `config/auth/list` 的路徑上（檔名與文件記載一致）。
- 只看原始碼與 tag，沒在真機跑過任何 Core 修補版；規則放行的版本字串必然是 Supervisor 真實記錄的版本，這是既有的信任假設，這次沒有改變。
