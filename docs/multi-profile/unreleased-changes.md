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
  `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。0.4.14 升版 PR（升版 commit `7252d9e`，基準 `40f6d10`）照第 3 點
  把 Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 與 OpenDesign（只升來源版本）寫進 CHANGELOG 的項目移掉。A7（HA Core 2026.11.2 審查，#120，基準 `40f6d10`）2026-11-17 加；使用者同日決定
  併進 0.4.14，七個產品的 0.4.14 CHANGELOG 都寫了它（和 B1 合成一句），只剩 Headscale 要寫。Headscale 0.4.19 升版（2026-11-18 準備，
  升版 commit 合併後補）照第 3 點把 A1～A7 寫進 Headscale 的 CHANGELOG；A1～A7 適用的產品都寫了，從第 1 節刪除。
- **本檔只管 CHANGELOG**。`upgrade-notes.yaml` 照 `AGENTS.md` 第 3 點與升版比對（`Upgrade comparison`）的要求另外判斷；版號資料照
  `docs/operations/release.md`「升版時要改的版號資料」。
- 「主對話補寫」：該片的筆記沒有英文句子，是照筆記的中文要點或程式照實寫的，最後的英文由發版片定。其他句子照筆記原文。

## 總表（2026-11-18）

| 產品 | 目前版號 | 上次升版 commit | 映像來源 | 要寫進 CHANGELOG 的項目 | 已合併、CHANGELOG 沒記的產品自身修正 |
|---|---|---|---|---|---|
| Odoo | 0.4.14（升版 PR 待合併） | `7252d9e`（2026-11-17，0.4.14 升版 PR） | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| n8n | 0.4.14（升版 PR 待合併） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| Hermes | 0.4.14（升版 PR 待合併） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| EMQX | 0.4.14（升版 PR 待合併） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| LiteLLM | 0.4.14（升版 PR 待合併） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| Nextcloud | 0.4.14（升版 PR 待合併） | 同上 | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.14） | 無 |
| OpenDesign | 0.4.14（只升來源版本，商店停用） | 同上 | 沒有映像 | 0（都寫進 0.4.14） | 無 |
| Headscale | 0.4.19（升版 PR 待合併） | `5a7c191`（2026-11-18，0.4.19 升版 commit） | `24de6ec`（2026-11-18 推 GHCR） | 0（都寫進 0.4.19） | 無 |

- 0.4.13：PR #76 在 2026-11-09 合併（`e2108f6`）。六個映像從 `4966f40` 建（`docs/operations/release-decision-0.4.13.md`）；`4966f40` 之後
  #76 只多一個紀錄 commit（`0913611`）。
- Headscale 0.4.18：映像從升版 commit `55f3528` 建（`docs/provenance/headscale-0.4.18-provenance.json`），PR #88 在 2026-11-12 合併（`bb48449`）。
- 0.4.14：升版 commit `7252d9e`（2026-11-17）。映像從凍結的 PR head 建，建好後在 `docs/operations/release-decision-0.4.14.md` 與
  各產品自己的紀錄補映像來源；PR 合併前本表的版號仍是「待合併」。rebase 之後升版 commit 換成新的 SHA。
- Headscale 0.4.19：升版 commit 合併後補（2026-11-18 準備；cherry-pick 或 rebase 之後 SHA 會變）。映像從凍結的 PR head 由 GitHub 發版流程建，
  建好後在 Headscale 自己的紀錄 `docs/operations/release-decision-headscale-0.4.19.md` 補映像來源；PR 合併前本表的版號仍是「待合併」。
- 2026-11-13 之後到 0.4.14 合併之前沒有任何產品發版。

## 1. 所有產品共通（A：不受開關管的共用變更）

A1～A7 適用的產品都寫進 CHANGELOG 了，照檔頭「怎麼更新」第 3 點刪除：

- 已發：0.4.14（Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud；OpenDesign 只升來源版本；升版 commit `7252d9e`，A7 由 `2dab8c2` 合進來，
  和 B1 合成一句）與 Headscale 0.4.19（升版 commit 合併後補；A7 寫成主因那一句）。n8n 不適用 A2；A5 的 n8n 那一句只寫在 n8n。
- 刪掉的項目：A1 HM-02 紀錄遮罩（#98）、A2 HM-06 子程式 bearer（#94）、A3 HM-13a 還原標記（#97）、A4 HM-14 initialize 錯誤的遮罩（#103）、
  A5 HM-31 請求內容位元組預算與 JSON 結構守門（#105）、A6 HM-09 追補（#106）、A7 管理員驗證接受 HA Core 2026.11.2（#120）。原來的句子、
  看得到的變化與出處見 `4cc7bee`（#120 的合併）的本檔與 `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。寫進 CHANGELOG 時
  照 0.4.14 那批的寫法：A3、A6 補 PR 號，A4 寫明狀態碼、其他標頭與其餘文字不變、只有 `Content-Length` 跟著變；以各產品 CHANGELOG 為準。
- 之後不受開關管的共用變更照檔頭第 1 點加在這一節，從 A8 編起（A1～A7 已用在各 PR 與發版紀錄裡）。

## 2. 0.4.13 這條線共通（B：Headscale 以外的 7 個產品）

Headscale 那條線改了共用程式，Headscale 自己已經發版、CHANGELOG 也記了；其他 7 個產品在 0.4.14 帶出去（OpenDesign 只升來源版本）。

B1（#81：管理員驗證接受 HA Core 2026.11.0、2026.11.1）與 B2（#77：儲存工具政策會重啟子程式的提示變短）適用的產品都在 0.4.14
寫進 CHANGELOG（升版 commit `7252d9e`），照檔頭「怎麼更新」第 3 點刪除。原來的句子與出處見 `40f6d10` 的本檔與
`docs/provenance/ha-multiprofile-unreleased-changes-20261117.md`。

## 3. 各產品

每個產品要寫的共通項目見第 1 節；這裡列上次發版、產品自己的項目與發版時要另外驗的事（每個產品都要做的見第 5 節）。

### 3.1 Odoo

- 上次發版：0.4.14（升版 commit `7252d9e`；映像來源待建置後補）。
- 要寫：無（A1～A7、B1 已寫進 0.4.14）。
- 自己的修正：沒有。`apps/odoo`、`addons/odoo` 在 0.4.13 之後沒改。Odoo 專屬的 HM-12（#110、#114：換身分換 token、新來源重填秘密）受開關管，
  開關關時沒有可見變化（第 4.2 節）。
- 發版時另外驗：第 5 節。

### 3.2 n8n

- 上次發版：0.4.14（同 Odoo）。
- 要寫：無（A1、A3、A4、A5 含 n8n 那一句、A6、A7、B1 已寫進 0.4.14；A2 不適用）。
- 自己的修正：沒有。`apps/n8n` 的兩次改動都沒有可見變化：HM-04（#91，port 參數化，預設 3000 時 `PORT` 照舊）、HM-20（#102，開通後才拒絕
  loopback 與檢查存檔）。
- 發版時另外驗：第 5 節。另外，n8n 若自己升版號（不跟預設版號一起升），`apps/n8n/run.py` 沒傳 `product_version`，`serverInfo` 與面板會報
  預設版號，HM-17 的升版模擬會擋：先改 `run.py` 與相關測試（HM-17 筆記第 12 節）。

### 3.3 Hermes

- 上次發版：0.4.14（同 Odoo）。
- 要寫：無（A1～A7、B1、H1 #85、H2 HM-33 #115 已寫進 0.4.14；H1、H2 照檔頭第 3 點刪除）。
- 發版時另外驗：第 5 節。HM-33 筆記交發版片定的兩件，0.4.14 這樣處理：`addons/hermes/README.md`、`DOCS.md` 沒補「Hermes Agent v0.17.0
  or v0.22.x」那句（這兩個檔沒有安裝前提的段落，HA 也沒在 v0.22.x 上實測；要補另開文件 PR）；trigger 會把停用的排程改回啟用寫在 H2 的
  CHANGELOG 句子裡（Hermes 自己的行為，PaaS 在 Hermes Agent v0.22.5 量過），HA 沒有實測。

### 3.4 EMQX

- 上次發版：0.4.14（同 Odoo）。
- 要寫：無（A1～A7、B1、B2、E1 #87、E2 HM-32 #113 已寫進 0.4.14；E1、E2 照檔頭第 3 點刪除）。
- 發版時另外驗：第 5 節。

### 3.5 LiteLLM

- 上次發版：0.4.14（同 Odoo）。
- 要寫：無（A1～A7、B1、B2、L1 HM-32 #113 已寫進 0.4.14；L1 照檔頭第 3 點刪除）。
- 發版時另外驗：第 5 節。

### 3.6 Nextcloud

- 上次發版：0.4.14（同 Odoo）。
- 要寫：無（A1～A7、B1、B2 已寫進 0.4.14）。
- 自己的修正：沒有（`apps/nextcloud`、`addons/nextcloud` 在 0.4.13 之後沒改）。Nextcloud 專屬的 HM-22（合併後補 PR 號：換 url、username
  換 token，存政策只重啟該帳號）受開關管，開關關時沒有可見變化（第 4.2 節）。
- 發版時另外驗：第 5 節。
- 開通那一版（Nextcloud 的升版 PR，把 `nextcloud` 加進 `MULTI_PROFILE_PRODUCTS`）才寫：Nextcloud 自己的 CHANGELOG 句子與同一個 PR
  另外要改的檔在 HM-22 筆記第 9.5 節（`docs/provenance/ha-multiprofile-HM-22-20261119.md`；HM-22 審查 S-5，照檔頭第 2 點，同 HM-24
  審查 S-7 的做法）。HM-22 受開關管，還沒開通的版本不寫、也不刪這一行；開通那一版寫進 CHANGELOG 之後照第 3 點刪。

### 3.7 OpenDesign（商店停用，只升來源版本）

- 上次發版：0.4.14 只升來源版本（升版 commit `7252d9e`），沒有建映像，也沒有 HAOS 驗收；CHANGELOG 照前例寫「source only (disabled)」，
  共通項目寫成一行「applies to its source too」。
- 要寫：無（A1～A7、B1、D1 #86 已寫進 0.4.14；D1 照檔頭第 3 點刪除）。
- 發版時另外驗：沒有映像，第 5 節的映像項目不適用；商店開放它的那一版才全部適用。

### 3.8 Headscale

- 上次發版：0.4.19（升版 commit `5a7c191`；映像來源 `24de6ec`）。
- 要寫：無（A1～A7 已寫進 0.4.19；0.4.18 的來源 `55f3528` 已含 #77～#88，B1、B2 也在內）。
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
| HM-22 | 合併後補 | 合併後補 | Nextcloud 開通的功能片：換 url、username 換 token（url 照伺服器與存的路徑比）、面板 `identityBound` 加 Nextcloud；面板等核對時被擋的存檔說明寫自己產品的身分欄位（`identityChange`，HM-22 審查 MF-1） | 換身分不換 token，回應沒有新欄位；面板的提示與請求不變（Odoo 的說明文字逐字不變） |

要用一句話交代第 4 節（可選；主對話補寫，照計畫 §3.3、§7.1）：

```text
- This image also carries the groundwork for multiple profiles per add-on (PRs #91, #93, #95, #99, #101–#104, #107, #110, #111 and #114). It stays switched off for this add-on: requests, responses, the admin panel and the files in `/data/mcp` are unchanged apart from the changes listed above.
```

0.4.14 的六個產品與 Headscale 0.4.19 的 CHANGELOG 都寫了這一句；下一版只交代那之後合併的片。

## 5. 發版時要另外驗的事（每個發映像的產品；計畫 §11.5）

1. 走完整的既有發版流程，不能只看單帳號黃金回歸（HM-05、HM-06 合併後的規定）。
2. 該產品的 HAOS P9 回歸（`docs/operations/ha-p9-kit.md`；要用主機的步驟照既有規定先取得負責人同意）。
3. 建置時的容器驗收（`supply_chain.py candidate` → `container_acceptance.py` 跑 `packaging/container_probe.py`）這兩段都要過，不要放寬：
   - 子程式 bearer 的直連 401 檢查（`assert_child_bearer`；n8n 驗 n8n-mcp 的同一個 child token）。
   - HM-13a 的 root 還原樹（Supervisor 式還原後的啟動：標記在、還原項目改回 10001、`state.json` 位元不變）。
   - 這兩段還沒在真容器跑過：第一次是 0.4.14 的建置（2026-11-17 起改在 GitHub 託管機器）或 HM-19a 前的乾跑，看哪個先。失敗時先查探針與 entrypoint（HM-06 筆記第 12.3 節、
     HM-13a 筆記第 11 節）。
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

## 6. 還沒合併、合併後要來改本檔的片（2026-11-17）

| 片 | PR | 不受開關管的部分 | 合併時要改本檔的地方 |
|---|---|---|---|
| HM-13b | #108 | 開機守門的存在檢查、休眠處理（計畫 §3.3） | 開機時刪還原標記並記一行 WARNING：A3（標記一直留著）已在 0.4.14 與 Headscale 0.4.19 寫進 CHANGELOG、從第 1 節刪除，HM-13b 合併時照它筆記的交接在第 1 節加一個新的共通項，寫新行為 |
| HM-13c | #112 | 單帳號還原後的面板提示（使用者 2026-11-16 定案） | 加一個共通項；CHANGELOG 句子在 HM-13c 筆記交 HM-19a 的那一段 |
| HM-16 | #109 | 驗收工具（`packaging/`） | 沒有可見變化，加到第 4.1 節 |
| HM-27 | #116 | 無（受開關管，report-only） | 加到第 4.2 節 |
