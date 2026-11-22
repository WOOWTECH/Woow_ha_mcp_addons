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
  2. 受開關管、開關關時逐位元不變的片：只在第 4.2 節加一行說明，不寫 CHANGELOG 句子。例外：某個產品開通的功能 PR（HM-21～HM-26）
     可以在該產品節加「開通時要寫」，只列那個產品自己的句子；每個產品開通都一樣的改變不在產品節重複，以契約第 1.4 節（計畫 §7.2
     的完整清單，HM-18 定稿）與本檔第 7 節為準。
  3. 發版的 PR：句子寫進 CHANGELOG 之後，同一個 PR 改本檔：該產品節的「上次發版」換成新版號與升版 commit，寫進去的自身項目刪掉；
     共通項目在「已發」填產品與版號，適用的產品都發過才刪。
- **基準**：`claude-delivery` `907bd39`（2026-11-17，#117 的合併）。查法、每項出處與沒列進來的變更見
  `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。0.4.14 升版 PR（升版 commit `7252d9e`，基準 `40f6d10`）照第 3 點
  把 Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 與 OpenDesign（只升來源版本）寫進 CHANGELOG 的項目移掉。A7（HA Core 2026.11.2 審查，#120，基準 `40f6d10`）2026-11-17 加；使用者同日決定
  併進 0.4.14，七個產品的 0.4.14 CHANGELOG 都寫了它（和 B1 合成一句），只剩 Headscale 要寫。Headscale 0.4.19 升版（2026-11-18 準備，
  升版 commit 合併後補）照第 3 點把 A1～A7 寫進 Headscale 的 CHANGELOG；A1～A7 適用的產品都寫了，從第 1 節刪除。
  2026-11-19 HM-18（基準 `claude-delivery` `c90b214`）：0.4.14 與 Headscale 0.4.19 已在 2026-11-18 合併（#119，`53ffe61`），表與各產品節跟上；
  #108（HM-13b）、#112（HM-13c）、#116（HM-27）、#109（HM-16）合併時沒改本檔，照第 6 節原本寫的補進第 1、4 節（A8、A9）；加第 7 節：
  開通某個產品的那一版要寫的事（契約第 1.4 節的清單、兩個位元組變化的 CHANGELOG 建議句）。
- **本檔只管 CHANGELOG**。`upgrade-notes.yaml` 照 `AGENTS.md` 第 3 點與升版比對（`Upgrade comparison`）的要求另外判斷；版號資料照
  `docs/operations/release.md`「升版時要改的版號資料」。
- 「主對話補寫」：該片的筆記沒有英文句子，是照筆記的中文要點或程式照實寫的，最後的英文由發版片定。其他句子照筆記原文。

## 總表（2026-11-19）

| 產品 | 目前版號 | 上次升版 commit | 映像來源 | 要寫進 CHANGELOG 的項目 | 已合併、CHANGELOG 沒記的產品自身修正 |
|---|---|---|---|---|---|
| Odoo | 0.4.14（2026-11-18 合併，#119 `53ffe61`） | `7252d9e`（2026-11-17，0.4.14 升版 PR） | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |
| n8n | 0.4.14（同上） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |
| Hermes | 0.4.14（同上） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |
| EMQX | 0.4.14（同上） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |
| LiteLLM | 0.4.14（同上） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |
| Nextcloud | 0.4.14（同上） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 3（A8、A9、NC1） | NC1（候選，未合併） |
| OpenDesign | 0.4.14（只升來源版本，商店停用；同上） | 同上 | 沒有映像 | 2（A8、A9，寫成「applies to its source too」） | 無 |
| Headscale | 0.4.19（2026-11-18 合併，#119 `53ffe61`） | `5a7c191`（2026-11-18，0.4.19 升版 commit） | `24de6ec`（2026-11-18 推 GHCR） | 2（A8、A9） | 無 |

- 0.4.13：PR #76 在 2026-11-09 合併（`e2108f6`）。六個映像從 `4966f40` 建（`docs/operations/release-decision-0.4.13.md`）；`4966f40` 之後
  #76 只多一個紀錄 commit（`0913611`）。
- Headscale 0.4.18：映像從升版 commit `55f3528` 建（`docs/provenance/headscale-0.4.18-provenance.json`），PR #88 在 2026-11-12 合併（`bb48449`）。
- 0.4.14：升版 commit `7252d9e`（2026-11-17）。映像從凍結的 PR head 建（`24de6ec`），映像來源記在 `docs/operations/release-decision-0.4.14.md`
  與各產品自己的紀錄；PR #119 在 2026-11-18 合併（`53ffe61`）。
- Headscale 0.4.19：升版 commit `5a7c191`，和 0.4.14 同一個 PR #119 合併（`53ffe61`）。映像來源記在 `docs/operations/release-decision-headscale-0.4.19.md`。
- 2026-11-13 之後到 0.4.14 合併之前沒有任何產品發版。0.4.14 合併之後到 2026-11-19 也沒有（之後合併的是 #108、#112、#116、#109，都沒改版號）。

## 1. 所有產品共通（A：不受開關管的共用變更）

A1～A7 適用的產品都寫進 CHANGELOG 了，照檔頭「怎麼更新」第 3 點刪除：

- 已發：0.4.14（Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud；OpenDesign 只升來源版本；升版 commit `7252d9e`，A7 由 `2dab8c2` 合進來，
  和 B1 合成一句）與 Headscale 0.4.19（升版 commit 合併後補；A7 寫成主因那一句）。n8n 不適用 A2；A5 的 n8n 那一句只寫在 n8n。
- 刪掉的項目：A1 HM-02 紀錄遮罩（#98）、A2 HM-06 子程式 bearer（#94）、A3 HM-13a 還原標記（#97）、A4 HM-14 initialize 錯誤的遮罩（#103）、
  A5 HM-31 請求內容位元組預算與 JSON 結構守門（#105）、A6 HM-09 追補（#106）、A7 管理員驗證接受 HA Core 2026.11.2（#120）。原來的句子、
  看得到的變化與出處見 `4cc7bee`（#120 的合併）的本檔與 `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。寫進 CHANGELOG 時
  照 0.4.14 那批的寫法：A3、A6 補 PR 號，A4 寫明狀態碼、其他標頭與其餘文字不變、只有 `Content-Length` 跟著變；以各產品 CHANGELOG 為準。
- 之後不受開關管的共用變更照檔頭第 1 點加在這一節，從 A8 編起（A1～A7 已用在各 PR 與發版紀錄裡）。

A8、A9 是 0.4.14 合併之後才合併的（2026-11-18～19），適用全部 8 個產品（n8n 的守門與提示在 `apps/n8n/run.py`；OpenDesign 只有來源，照前例寫一行
「applies to its source too」）；兩項都還沒有產品寫進 CHANGELOG。0.4.14 的 CHANGELOG 寫過 A3（還原標記「之後的版本會讀並刪掉它，在那之前一直留著」），
A8 就是那個之後的版本；寫的時候和 A3 那句對得起來。

- **A8　HM-13b 開機守門（#108，合併 `f5e296f`；不受開關管）**
  - 看得到的變化（今天的安裝：沒開通、沒有帳號資料）：還原之後的那次開機，管理程序在任何子程式與 listener 之前讀 entrypoint 留下的
    `.restore-detected`，記一行 WARNING（`restore_lock.KEPT_NOTICE`：權杖已回到備份當時的值、什麼都沒撤銷、可能外洩時到面板重新產生），存 A9 的
    還原提示 `restore-notice.json`，然後刪掉標記；除了這個提示檔，`/data/mcp` 其他一個位元組都不動。還原提示存不下或標記刪不掉時照常啟動、多記一行
    （`MARKER_LEFT`），標記留著、下次開機再試。沒有還原的開機只多查幾個名稱，什麼都不寫。
  - 看不到的部分（只在磁碟上有帳號資料時動作，今天沒有安裝有）見第 4.1 節。
  - CHANGELOG 建議句（HM-18 補寫，照契約第 1.2、1.3 節與 `restore_lock.py` 的原文；英文最後由發版片定）：

    ```text
    - Restore guard (groundwork for multiple profiles; PR #108): after Home Assistant restores this add-on's backup, the next start now reads the restore marker `.restore-detected` before any listener or MCP child starts, logs one warning that the MCP token is back to its value at the time of that backup (nothing is revoked without multi-profile data; rotate the token in the panel if it may have leaked since), saves the panel's restore notice (`restore-notice.json`, next entry) and removes the marker. Apart from that notice file, nothing else in `/data/mcp` changes. If the notice cannot be saved or the marker cannot be removed, the add-on still starts, logs one more line and tries again at the next start. A start without a restore only checks a few file names and writes nothing.
    ```
  - 出處：`docs/provenance/ha-multiprofile-HM-13b-20261116.md` 第 13 節（「各產品 CHANGELOG 的「還原標記」段落改成新行為」）；契約第 1.3 節。

- **A9　HM-13c 單帳號還原後的面板提示（#112，合併 `e108a12`；不受開關管；使用者 2026-11-16 核准的代價）**
  - 看得到的變化：還原而且預設帳號的權杖沒撤銷時（今天的每個安裝都是），A8 那次開機在刪標記之前另存 `/data/mcp/restore-notice.json`
    （只有時間、不含秘密），面板顯示還原提示，bootstrap 多一個鍵 `restore_notice`，到預設帳號重新產生或撤銷權杖為止。沒有還原過的安裝逐位元照舊。
  - CHANGELOG 建議句（HM-13c 筆記第 15 節原文）：

    ```text
    - After a backup restore that keeps the MCP token (no multi-profile data on disk: nothing is revoked, as before), the admin panel now also shows "偵測到還原；權杖已回到備份當時的值。若備份後曾輪替或撤銷，請立即重新產生" until the token is rotated or revoked. Meanwhile the bootstrap carries one more field, `restore_notice` (`{"at"}`), and `/data/mcp` holds `restore-notice.json` (its time only, no secret). An installation that was never restored answers byte for byte as before; no management route is added.
    ```
  - 出處：`docs/provenance/ha-multiprofile-HM-13c-20261116.md` 第 15 節；契約第 1.2 節「HM-13c 的不受開關管變更」。`upgrade-notes.yaml` 要不要列，
    照升版比對的報告定（只多一個欄位，不是破壞性變更）。

## 2. 0.4.13 這條線共通（B：Headscale 以外的 7 個產品）

Headscale 那條線改了共用程式，Headscale 自己已經發版、CHANGELOG 也記了；其他 7 個產品在 0.4.14 帶出去（OpenDesign 只升來源版本）。

B1（#81：管理員驗證接受 HA Core 2026.11.0、2026.11.1）與 B2（#77：儲存工具政策會重啟子程式的提示變短）適用的產品都在 0.4.14
寫進 CHANGELOG（升版 commit `7252d9e`），照檔頭「怎麼更新」第 3 點刪除。原來的句子與出處見 `40f6d10` 的本檔與
`docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。

## 3. 各產品

每個產品要寫的共通項目見第 1 節；這裡列上次發版、產品自己的項目與發版時要另外驗的事（每個產品都要做的見第 5 節）。

### 3.1 Odoo

- 上次發版：0.4.14（升版 commit `7252d9e`；映像來源 `24de6ec`；#119 在 2026-11-18 合併）。
- 要寫：A8、A9（第 1 節）。A1～A7、B1 已寫進 0.4.14。
- 自己的修正：沒有。`apps/odoo`、`addons/odoo` 在 0.4.13 之後沒改。Odoo 專屬的 HM-12（#110、#114：換身分換 token、新來源重填秘密）受開關管，
  開關關時沒有可見變化（第 4.2 節）。
- 發版時另外驗：第 5 節。

### 3.2 n8n

- 上次發版：0.4.14（同 Odoo）。
- 要寫：A8、A9（第 1 節）。A1、A3、A4、A5 含 n8n 那一句、A6、A7、B1 已寫進 0.4.14；A2 不適用。
- 自己的修正：沒有。`apps/n8n` 的兩次改動都沒有可見變化：HM-04（#91，port 參數化，預設 3000 時 `PORT` 照舊）、HM-20（#102，開通後才拒絕
  loopback 與檢查存檔）。
- 發版時另外驗：第 5 節。另外，n8n 若自己升版號（不跟預設版號一起升），`apps/n8n/run.py` 沒傳 `product_version`，`serverInfo` 與面板會報
  預設版號，HM-17 的升版模擬會擋：先改 `run.py` 與相關測試（HM-17 筆記第 12 節）。

### 3.3 Hermes

- 上次發版：0.4.14（同 Odoo）。
- 要寫：A8、A9（第 1 節）。A1～A7、B1、H1 #85、H2 HM-33 #115 已寫進 0.4.14；H1、H2 照檔頭第 3 點刪除。
- 發版時另外驗：第 5 節。HM-33 筆記交發版片定的兩件，0.4.14 這樣處理：`addons/hermes/README.md`、`DOCS.md` 沒補「Hermes Agent v0.17.0
  or v0.22.x」那句（這兩個檔沒有安裝前提的段落，HA 也沒在 v0.22.x 上實測；要補另開文件 PR）；trigger 會把停用的排程改回啟用寫在 H2 的
  CHANGELOG 句子裡（Hermes 自己的行為，PaaS 在 Hermes Agent v0.22.5 量過），HA 沒有實測。

### 3.4 EMQX

- 上次發版：0.4.14（同 Odoo）。
- 要寫：A8、A9（第 1 節）。A1～A7、B1、B2、E1 #87、E2 HM-32 #113 已寫進 0.4.14；E1、E2 照檔頭第 3 點刪除。
- 發版時另外驗：第 5 節。

### 3.5 LiteLLM

- 上次發版：0.4.14（同 Odoo）。
- 要寫：A8、A9（第 1 節）。A1～A7、B1、B2、L1 HM-32 #113 已寫進 0.4.14；L1 照檔頭第 3 點刪除。
- 發版時另外驗：第 5 節。
- **開通時要寫（HM-21 交，PR 號合併後補）**：HM-21 是 LiteLLM 開通的功能 PR，沒有程式（計畫 §9：LiteLLM 不需要產品專屬程式），開關關時
  沒有任何變化（第 4.2 節）。LiteLLM 的升版 PR 把 `litellm` 加進 `features.MULTI_PROFILE_PRODUCTS`、升 0.5.0 時，L2～L6 是 **LiteLLM 自己的**
  句子，一行一個變化（檔頭第 2 點的例外；DOCS 與 `upgrade-notes.yaml` 要寫的見 `docs/provenance/ha-multiprofile-HM-21-20261119.md` 第 12 節）。
  每個產品開通都一樣的改變（帳號選單與 `X-MCP-Profile`、8081 的每帳號准入、看門狗與健康檢查的容忍、還原、全部撤銷、Origin 清單、記憶體檢查、
  8099 的兩個位元組變化等）不在這裡列，照檔頭第 2 點的單一來源（契約第 1.4 節、本檔第 7 節）寫；Odoo 首發（HM-19a）先寫了就照那裡的
  句子對齊（審查 S-1）。L3 後半與 L6 是共通項（HM-12 新來源重填秘密、HM-20 loopback：契約第 1.4 節第 17、18 點）的 LiteLLM 寫法：
  寫了它們，共通的那兩句就不再寫一次。數值以發版當時的契約第 5 節為準（HM-19c 量測前都是暫定）；PR 號照當時已合併的多帳號 PR 補。
  - L2：`- LiteLLM can now serve up to three profiles besides the default one, as memory allows: each profile has its own MCP token on both connection methods (Bearer /mcp and /private_<token>/mcp), its own LiteLLM URL and key, its own tool policy and its own MCP child, and the token alone decides which profile a request reaches. A profile can do what its key allows, so give each profile its own key: a virtual key limited to that profile's models, or a proxy_admin_viewer user's key, not the master key.`
  - L3：`- Changing a profile's LiteLLM key or URL keeps its MCP token and URLs, as before and as on the PaaS server; only that profile's MCP child restarts with the new values. New: moving the URL to another server (scheme, host or port) needs the key again: the panel asks for it before saving, and the server refuses the save without it (HTTP 422, CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN).`
  - L4：`- Saving a profile's tool policy restarts only that profile's MCP child; the other profiles keep their sessions. As before, with every write grant revoked the child runs read-only (LITELLM_MCP_READONLY=true) and registers no write tool.`
  - L5：`- Each profile's MCP child keeps its own pool of at most four backend connections to LiteLLM (four per child as before; the PaaS server allows 50): a fifth call at once on one profile waits for a free connection (up to 60 s), and a profile that keeps four calls busy does not delay another profile. The profile's health check needs one of these connections too: if four calls keep them busy through two health checks in a row (each check waits 5 s for one; checks come every 15 s; before, one such check was enough), the profile's new tool calls get -32603 Backend unreachable until a check passes, although LiteLLM itself is fine.`
  - L6：`- A LiteLLM URL can no longer point at loopback (127.0.0.0/8, ::1, localhost): saving one is refused, and the MCP child refuses to connect to one (PR #102). Inside the add-on, loopback only ever reached the add-on's own ports; use the LiteLLM host's LAN address or name.`

### 3.6 Nextcloud

- 上次發版：0.4.14（同 Odoo）。
- 要寫：A8、A9（第 1 節）與 NC1。A1～A7、B1、B2 已寫進 0.4.14。
- **NC1：Nextcloud PaaS 正規化與政策重啟對齊**（候選，PR／合併 commit 待補；不受多帳號開關管）：存檔正規化貼上的頁面網址與帳密空白；政策收緊或不變不重啟，放寬且子程式執行中才重啟，停著不啟動。換身分換 token 仍只在開通後生效。HA 保留目的地與跨來源秘密檢查。建議 CHANGELOG：

  `Nextcloud connection saves normalize pasted page URLs and credentials; policy restrictions apply without restarting, while enabling tools restarts only a running child.`

  出處：`docs/multi-profile/nextcloud-paas-parity-20261120.md`；實機 HAOS 驗收另行完成。Nextcloud 專屬的 HM-22 換身分換 token 受開關管（第 4.2 節）。
- 發版時另外驗：第 5 節。
- 開通那一版（Nextcloud 的升版 PR，把 `nextcloud` 加進 `MULTI_PROFILE_PRODUCTS`）才寫：Nextcloud 自己的 CHANGELOG 句子與同一個 PR
  另外要改的檔在 HM-22 筆記第 9.5 節（`docs/provenance/ha-multiprofile-HM-22-20261119.md`；HM-22 審查 S-5，照檔頭第 2 點，同 HM-24
  審查 S-7 的做法）。HM-22 受開關管，還沒開通的版本不寫、也不刪這一行；開通那一版寫進 CHANGELOG 之後照第 3 點刪。

### 3.7 OpenDesign（商店停用，只升來源版本）

- 上次發版：0.4.14 只升來源版本（升版 commit `7252d9e`），沒有建映像，也沒有 HAOS 驗收；CHANGELOG 照前例寫「source only (disabled)」，
  共通項目寫成一行「applies to its source too」。
- 要寫：A8、A9（第 1 節，寫成一行「applies to its source too」）。A1～A7、B1、D1 #86 已寫進 0.4.14；D1 照檔頭第 3 點刪除。
- 發版時另外驗：沒有映像，第 5 節的映像項目不適用；商店開放它的那一版才全部適用。

### 3.8 Headscale

- 上次發版：0.4.19（升版 commit `5a7c191`；映像來源 `24de6ec`；和 0.4.14 同一個 PR #119，2026-11-18 合併）。
- 要寫：A8、A9（第 1 節）。A1～A7 已寫進 0.4.19；0.4.18 的來源 `55f3528` 已含 #77～#88，B1、B2 也在內。
- 自己的修正：沒有（`apps/headscale`、`addons/headscale` 在 `55f3528` 之後只改了 0.4.19 的版號、CHANGELOG 與文件）。
- 發版時另外驗：第 5 節。Headscale 第一次走 GitHub 發版流程（之前每一版都是 builder VM 推的）：觸發前負責人要先給 `amd64-mcp-headscale`
  套件設 Actions 權限（`docs/operations/release.md`「負責人要在 GitHub 設定的項目」第 4 項）。

## 4. 沒有可見變化的片（不用逐項寫 CHANGELOG）

### 4.1 不受開關管、但對沒開通的產品看不到

| 片 | PR | commit | 為什麼看不到 |
|---|---|---|---|
| HM-04 子程式 port 參數化 | #91 | `e5e6e74` | 預設 3000 時子程式的 argv、env、cwd 和以前逐位元相同（快照 `tests/contract/child_spec_default.json`） |
| HM-05 每帳號執行套件 | #95 | `8e02ac1` | 預設帳號的行為逐位元不變，`/data/mcp` 不多任何檔 |
| HM-07 帳號資料層 | #93 | `e5fa5c7` | 函式庫還沒接進開機流程；`MULTI_PROFILE_PRODUCTS` 是空集合 |
| HM-11 收據格式 | #107 | `f4c7718` | 預設帳號的收據 key 與 4 個鍵的紀錄不變 |
| HM-17 發版基礎 | #92 | `56f22f7` | 只改發版工具（`packaging/`、workflow），不在映像裡；影響發版步驟（第 5 節第 6 點） |
| HM-13b 開機守門（A8 以外） | #108 | `f5e296f` | 撤銷每個帳號（連預設帳號）、隔離讀不到的帳號、獨立驗證、寫還原紀錄、休眠處理，對沒開通的產品都只在磁碟上有帳號資料時動作；全部撤銷的標記（`.revoke-all-pending`）不看帳號資料、一樣撤銷預設帳號，但只有開通的路由寫得出來。沒有產品開通過，今天沒有安裝有帳號資料或這個標記（2026-11-19 HM-18 補列） |
| HM-16 驗收工具 | #109 | `c90b214` | 只改 `packaging/`（容器探針的多帳號階段、P9 kit 的帳號參數、升版比對 hook 的草稿）、測試與文件，探針與 P9 kit 不在映像裡；影響發版時的容器驗收（第 5 節第 3 點）（2026-11-19 HM-18 補列） |

### 4.2 受開關管：開關關時沒有可見變化

這些片的程式都在映像裡，但 `MULTI_PROFILE_PRODUCTS` 是空集合，沒有產品開通，**開關關時沒有可見變化**：`state.json` 位元組不變、不產生新檔、
bootstrap 不變、兩條 MCP 網址同一把 token 同一組錯誤碼、名額／看門狗／健康檢查／管理管線照舊（計畫 §3.3、§7.1）。各片產品開通後的改變，
由該產品的升版片照契約第 1.4 節（計畫 §7.2 的完整清單，HM-18 定稿）寫進 CHANGELOG（第 7 節）。

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
| HM-13c（A9 以外） | #112 | `e108a12` | 全部撤銷、還原紀錄、核對、刪除隔離目錄的路由與面板的核對卡；8081 擋全部撤銷沒撤銷成功的權杖 | 沒有這些路由（`/api/profiles*` 照舊 404），面板不畫核對卡；只有 A9 的還原提示（2026-11-19 HM-18 補列） |
| HM-27 | #116 | `fcd0b22` | 密鑰網址的服務層級 Origin 清單（預設 report-only）、`/api/origin-policy`、面板「瀏覽器來源檢查」卡片；還原時封存政策旁的收據 | 不讀不寫 `origin-policy.json`、`/api/origin-policy` 照舊 404、密鑰網址照舊不看 Origin、面板不畫卡片（2026-11-19 HM-18 補列） |
| HM-21 LiteLLM 開通的功能 PR | 合併後補 | 合併後補 | 沒有程式：只有測試（`tests/test_litellm_multi_profile.py`）與文件；映像只多 `docs/provenance/` 的筆記 | 沒有任何變化；開通時的句子見第 3.5 節 |
| HM-22 | 合併後補 | 合併後補 | Nextcloud 開通的功能片：換 url、username 換 token（url 照伺服器與存的路徑比）、面板 `identityBound` 加 Nextcloud；面板等核對時被擋的存檔說明寫自己產品的身分欄位（`identityChange`，HM-22 審查 MF-1） | 換身分不換 token，回應沒有新欄位；面板的提示與請求不變（Odoo 的說明文字逐字不變） |

要用一句話交代第 4 節（可選；主對話補寫，照計畫 §3.3、§7.1）：

```text
- This image also carries the groundwork for multiple profiles per add-on (PRs #91, #93, #95, #99, #101–#104, #107, #110, #111 and #114). It stays switched off for this add-on: requests, responses, the admin panel and the files in `/data/mcp` are unchanged apart from the changes listed above.
```

0.4.14 的六個產品與 Headscale 0.4.19 的 CHANGELOG 都寫了這一句；下一版只交代那之後合併的片：映像裡多帶、開關關時看不到的是 #108（A8 以外；
不受開關管，第 4.1 節）、#112（A9 以外）、#116（#109 不在映像裡）；HM-22 合併後也在其中（第 4.2 節；PR 號合併後補，建議句的 PR 清單跟著加）。
建議句（HM-18 補寫）：

```text
- This image also carries more groundwork for multiple profiles per add-on (PRs #108, #112 and #116). It stays switched off for this add-on: requests, responses, the admin panel and the files in `/data/mcp` are unchanged apart from the changes listed above.
```

## 5. 發版時要另外驗的事（每個發映像的產品；計畫 §11.5）

1. 走完整的既有發版流程，不能只看單帳號黃金回歸（HM-05、HM-06 合併後的規定）。
2. 該產品的 HAOS P9 回歸（`docs/operations/ha-p9-kit.md`；要用主機的步驟照既有規定先取得負責人同意）。
3. 建置時的容器驗收（`supply_chain.py candidate` → `container_acceptance.py` 跑 `packaging/container_probe.py`）這兩段都要過，不要放寬：
   - 子程式 bearer 的直連 401 檢查（`assert_child_bearer`；n8n 驗 n8n-mcp 的同一個 child token）。
   - HM-13a 的 root 還原樹（Supervisor 式還原後的啟動：標記在、還原項目改回 10001、`state.json` 位元不變）。
   - 0.4.14 與 Headscale 0.4.19 的 candidate（2026-11-18，GitHub 託管機器）已在真容器跑過這兩段，都通過（`docs/operations/release-decision-0.4.14.md`
     第 1a、1b 項）。之後 HM-13b、HM-13c、HM-16 改了還原階段的檢查：守門刪掉標記、留下還原提示（A8、A9），log 裡 `re-owned N` 與守門的
     `KEPT_NOTICE` 各剛好一行、守門沒有別的行（`docs/operations/acceptance.md`）。下一版的 candidate 是第一次在真容器跑這些新檢查；失敗時先查
     探針、entrypoint 與守門（HM-06 筆記第 12.3 節、HM-13a 筆記第 11 節、HM-16 筆記），不要放寬。（2026-11-19 HM-18 改寫：原本寫「還沒在真容器跑過」）
4. HA Core 版本：管理員驗證只認到 2026.11.2（#81、#120）。目標 HAOS 的 Core 比它新，要先補審（計畫 §11.3 的升版 PR 清單：`Hc/ha_role.py` 與
   `docs/ha-role-core-contract.md`），不然面板拒絕每個請求。
5. HM-31 的預算常數是暫定（契約第 5 節）。那裡的「HM-19c 放行條件」（在目標硬體量閘道＋子程式的放大倍數與 MemAvailable，不過就不能發版）
   是為 Odoo 首發寫的，但 A5（HM-31，#105）不受開關管，任何產品下一版都會帶出去。HM-19c 量測之前要發版，先請負責人決定要不要先量。
6. 版號資料 7 處照 `docs/operations/release.md`「升版時要改的版號資料」；readiness 只認該產品自己的
   `docs/operations/release-decision-<產品>-<版號>.md`（HM-17）。
7. 發版鎖：同一時間只有一個凍結中的升版 PR（含其他產品的修補版；計畫 §11.5）。
8. 根目錄 `CHANGELOG.md` 照前例寫這一版包含哪些 PR（例如 0.4.13 那段的「Includes the merged post-0.4.12 source changes in PRs #73–#75」）。
9. J1900 指令集檢查（DQ-42，負責人 2026-11-17 定每次發版都跑）：QEMU user-mode `-cpu Nehalem` 跑候選映像（做法見
   `docs/operations/release-decision-0.1.7.md`「0.1.8 待辦」最後一點）。

## 6. 還沒合併、合併後要來改本檔的片

目前沒有。2026-11-17 這裡列的四片都已合併：#108（HM-13b，`f5e296f`）、#112（HM-13c，`e108a12`）、#116（HM-27，`fcd0b22`）、
#109（HM-16，`c90b214`）。它們合併時沒改本檔；HM-18（2026-11-19）照這一節原本寫的「合併時要改本檔的地方」補了：第 1 節 A8（HM-13b）、
A9（HM-13c），第 4.1 節 HM-13b 的其餘部分與 HM-16，第 4.2 節 HM-13c 的其餘部分與 HM-27。之後的片照檔頭「怎麼更新」在自己的 PR 裡改。

## 7. 開通某個產品的那一版（升版片把它加進 `MULTI_PROFILE_PRODUCTS`；2026-11-19 HM-18 加）

- **誰讀**：開通某個產品的升版 PR（Odoo 是 HM-19a，之後 HM-21～HM-26）。第 1～6 節照舊（不受開關管的共通項）；這一節是「開通」才出現的改變，
  只寫進被開通的那個產品。
- **CHANGELOG**：契約第 1.4 節（計畫 §7.2 的完整清單，HM-18 定稿）逐項寫進該產品的 `addons/<產品>/CHANGELOG.md`，只有預設帳號的安裝也看得到。
  標「Headscale 除外」的點（Origin 政策：第 5、10、19 點）開通 Headscale 時不寫（HM-26）。第 4.2 節各片的「映像多帶了什麼」在開通那一版變成看得到的
  改變，以第 1.4 節的寫法為準。
- **DOCS**：`addons/<產品>/DOCS.md` 照 repo 的 `docs/operations/clients.md`、`guide.md`、`update-backup-rollback.md` 的多帳號段落改寫（HM-18 寫的是
  repo 層的文件；產品 DOCS 與 README 只在升版 PR 改，計畫 §11.1）。
- **開通後會變錯、要一起改的句子**（FM-94；計畫 §17 交 HM-18、HM-19a）：改成「每個帳號一組後端、一把權杖；同產品可多帳號（不宣稱多租戶）」，
  並補該產品的帳號上限與注意事項：
  - 根目錄 `README.md` 第 46～47 行「每個 Add-on 一組後端、獨立 token／資料／版本；不宣稱多租戶或同產品多 profile」：第一個開通的產品就要改，
    寫明哪些產品開通了。
  - 被開通的產品的 `addons/<產品>/DOCS.md`：「一個 Add-on 只有一組後端：…」（Odoo 第 26 行；n8n、Hermes、EMQX、LiteLLM、OpenDesign 同一句）、
    Nextcloud 的「一個 Add-on 只有一個 Nextcloud 帳號」、Headscale 開頭「填入一台 Headscale 控制伺服器的網址」那段。
  - `addons/n8n/DOCS.md` 第 55 行「所有 client 共用 20 個同時 session」：開通後每個帳號有自己的子程式，HM-25 照實際行為改。
  - `addons/nextcloud/config.yaml` 的 `description`「one Nextcloud account」（HM-22）。
  - 面板 `packages/mcp-admin-ui/src/contracts.js` 的 Headscale 說明「這個 Add-on 只管理同一個 Headscale 執行個體」（HM-26；面板改了照規則重算帳本）。
- **`upgrade-notes.yaml`**：照 `AGENTS.md` 第 3 點，升版比對要求時才建；建的話內容照計畫 §7.3：契約第 1.4 節的全部項目、回退的三條路
  （`docs/operations/update-backup-rollback.md`「回退與緊急關閉」）、還原守門的涵蓋範圍（同一份文件「涵蓋範圍」一點）。
- **兩個位元組變化**（HM-10 審查 S-6；契約第 1.4 節第 4 點、第 3.1 節；HM-18 在本機用 8099 的兩種方法表核對過）的 CHANGELOG 建議句
  （HM-18 補寫；英文最後由升版片定）：

  ```text
  - Admin API (port 8099), once multiple profiles are switched on for this add-on: a PATCH or DELETE request that fails the identity check (for example one without the CSRF header) now gets HTTP 403 `{"error":"request denied"}` from that check (HTTP 400 with the same body when its `X-Ingress-Path` header is malformed) instead of HTTP 405 `Method Not Allowed`, because the identity check now runs before the method check.
  - Admin API (port 8099), once multiple profiles are switched on: a request with any method other than GET, HEAD, POST, PUT, PATCH and DELETE (for example OPTIONS) still gets HTTP 405 `Method Not Allowed`, but its `Allow` header now lists six methods instead of four (`PATCH` and `DELETE` are added). The order of the methods in that header has never been fixed.
  ```
- **其他項目的原句**：各片筆記交給升版片的句子，用的時候以契約第 1.4 節的事實為準：HM-20 筆記第 13 節（後端網址不能填 loopback，中文）、
  HM-12 筆記第 15 節（換身分換 token、新來源重填秘密、503 時重啟後確認網址）、HM-27 筆記第 13 節（Origin 清單）、HM-09 筆記第 13.2 節
  （§7.2 要補的六點）、HM-13b 筆記第 13 節（還原會變的事）、HM-22 筆記第 9.5 節（Nextcloud 開通那一版自己的句子與同一個 PR 另外要改的檔，
  第 3.6 節；HM-22 合併 `claude-delivery` 時補）。
- **發版時另外驗**：第 5 節，加上計畫 §10.6（Odoo 首發標準）與 `docs/operations/acceptance.md` 的多帳號驗收；容器驗收的多帳號階段第一次真跑是
  HM-19a 前的乾跑。


### 2026-11-20 EMQX 子程式政策候選

依使用者指示，EMQX 子程式每次列出或呼叫工具讀取並驗證本帳號 state，拒絕停用工具、操作與未授權寫入；state 不安全、損壞或身分不符時關閉。固定唯讀健康探測保留；政策儲存仍重啟本帳號子程式。未發布、未合併。

**火車 A 審查 F-1（2026-11-23）修正**：帶 `EMQX_MCP_STATE_PATH` 時，子程式**不再**改用空的 `ToolGate`。環境閘（`EMQX_MCP_READONLY`、`EMQX_MCP_DISABLED_TOOLS`）在每個模式都照常生效，`PolicyMiddleware` 是疊在上面的第二層（即時讀 state），不是取代。所以 `child_spec` 設的兩個環境變數仍然有作用，防線維持閘道＋子程式環境閘＋子程式即時政策三層。單帳號、沒開通的行為不變（`tests/contract/child_spec_default.json` 的環境本來就含這兩個變數）。測試：`tests/test_emqx_child_gate.py` 在 EMQX 自己的 venv 以映像相同的 `PYTHONPATH` 起 server，證明有 state path 時 READONLY 與 DISABLED_TOOLS 仍擋住註冊，同時證明該 venv 能 import `mcp_admin_core.products` 與 `emqx_child_policy`（`apps/emqx/Dockerfile` 複製 `packages/mcp-admin-core` 並把它放進 `PYTHONPATH`）。
