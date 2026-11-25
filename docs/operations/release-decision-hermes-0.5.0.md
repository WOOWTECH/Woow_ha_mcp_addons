# Hermes 0.5.0（多帳號 train B）發佈紀錄（草稿）

狀態：**草稿：映像尚未建置、尚未推 GHCR、尚未驗收**（待補：run、digest、展示機結果）。這是 `woow_mcp_hermes` 一個產品的發版：Hermes 開通多帳號（預設帳號＋最多 3 個額外帳號）、版號 0.4.15 → 0.5.0，與 n8n、Headscale 的 0.5.0 同一批（火車 B；一個升版 PR、各產品各自的 `release.yaml` run）。
Odoo 0.5.2、EMQX／LiteLLM／Nextcloud 0.5.1 是同日 2026-11-25 的維修版，不在這一批；OpenDesign 的來源版本留在 0.4.15（商店停用、沒有映像）。
合併升版 PR 即上架 WOOW App Store；合併前只補這份紀錄與驗收紀錄（只改 `docs/`）。

## 為什麼發這一版

負責人 2026-11-25 的決定（主對話 AskUserQuestion「火車 B 要怎麼做？」）：選「三個一起，照建議做」：Hermes、n8n、Headscale 一起開通多帳號，並照安全審查的建議做三件事（n8n 的 webhook、chat、form 連線只多擋 loopback；Headscale 新帳號預設不給 `headscale_api_keys` 的寫入；Headscale 的子程式只認自己帳號的 child token）。
發佈核准與合併沿用 2026-11-23「整套一次授權」：每個產品過完所有關卡（CI、審查、驗收）才發佈；GitHub 的發佈核准以 API 代按，改版號 PR 也代為合併，每一步回報；容量與極端壓力只記錄、不擋發版。

功能依據：HM-24（Hermes 開通的功能 PR #128）在整合分支上的樣子：換 Gateway 網址、Dashboard 網址或 Dashboard 使用者（含補上或清空 Dashboard）**保留 MCP 權杖**（負責人 2026-11-20 定案，與 PaaS 一致；HM-24 筆記第 9 節第 2 句的「換身分換 token」已被取代，CHANGELOG 沒有照抄）、Dashboard 登入限流在帳號之間共用、長 `hermes_chat` 佔該帳號自己的轉送名額。

這一版建在 2026-11-25 的維修版（[Hermes 0.4.15 發佈紀錄](release-decision-hermes-0.4.15.md)；PR #138）之上，所以也帶出維修版的內容：管理員驗證接受 HA Core 2026.11.3 並自動放行已審查月份的後續修補版、Node 26.13.1 基底。**維修版要先合併**，這一批再與新的 `claude-delivery` 合併。
另外帶出本機分支 `feat/duplicate-jsonrpc-id-20261125`（PaaS #161 的重複 JSON-RPC id 防護，不受開關管；Claude.ai 與 ChatGPT 的用戶端不重複使用 id，不會觸發）。

Hermes 一節（負責人 2026-11-25 照建議）：**60 分鐘負載量測用免費模型，只記錄、不擋發版**。量測（`docs/operations/acceptance.md`「Hermes 開通（HM-24）」第 7 項）要打真的 Gateway 與 Dashboard，`hermes_chat` 會花模型費用：展示機的 Hermes 接免費模型（或測試用 Gateway），預設帳號加 3 個額外帳號、每個帳號一個用戶端混合呼叫至少 60 分鐘，每 30 秒記每個子程式的 RSS／PSS、管理程序 RSS 與 MemAvailable，停止負載後再記 10 分鐘；結果只寫進驗收紀錄，`profiles.CHILD_MEMORY_MIB['hermes']`（暫定 160）要改另開功能 PR，不在這一版。

## 範圍

- **只有 Hermes**（`woow_mcp_hermes`）：`features.MULTI_PROFILE_PRODUCTS` 加 `hermes`、`n8n`、`headscale` 三個產品（與 `odoo`、`emqx`、`litellm`、`nextcloud` 一起，是 7 個），`addons/hermes/`、`apps/hermes/Dockerfile` 的版號 0.5.0。
- 不在範圍：Odoo、EMQX、LiteLLM、Nextcloud 的版號（維修版的 0.5.2、0.5.1 不動）；OpenDesign 與 Odoo Manage 不開放多帳號（DQ-28）。Hermes 的 0.5.0 是它自己的版號線（DQ-32），和其他產品一樣寫在 `VERSION_OVERRIDES`；共用預設版號 `VERSION` 維持 0.4.15，現在只有 OpenDesign 的來源版本在用。
- 路線：這條線只用 GitHub（`.github/workflows/release.yaml`：gate → candidate → publish，publish 在 `public-release` environment 核准，只收 `release/*` 分支）。

## 來源

- 分支 `release/train-b-0.5.0-20261125`（本機，尚未推送；基準：整合分支 `integ/train-b-20261125` 的 `0ab5393`，PR #139 草稿的 head）。分支上依序有：
  - `d1217a2`：merge commit，併入維修版分支 `release/maintenance-20261125`（PR #138，head `fec2e3ec292d`；Odoo 0.5.2、EMQX／LiteLLM／Nextcloud 0.5.1、n8n／Hermes 0.4.15、Headscale 0.4.20）。衝突只在文件與帳本（契約第 1.2 節與第 10 節、`decisions.md`、`unreleased-changes.md`、`runtime-patches.json` 的 `api.js` 一列），解法寫在 commit 內文。
  - `153f6d3`：merge commit，併入本機分支 `feat/duplicate-jsonrpc-id-20261125`（PaaS #161 重複 JSON-RPC id 防護，4 個 commit；不受開關管）。契約第 9 節的列號 134 → 145（維修版之後合併的重編）、未發佈清單的項目 A10 → A12（和維修版的 A10 撞號）、帳本摘要照合併後的檔重算，`deviation-trace.md` 手改（它的產生器不在這台主機，照 `90fa0be` 的前例）。
  - `93cc365`：開關（`features.MULTI_PROFILE_PRODUCTS` 加 `hermes`、`n8n`、`headscale`）、版號資料 7 處、帳本，以及 24 個測試檔改成自己要 `switched_off`（整套在開關已開的狀態下跑出來的，原因是 HM-20：開通的產品的子程式拒絕 loopback 假後端；沒有改任何斷言）。
  - `7b5929f`：容器探針的單元測試 8 案（只加測試，探針本身沒改）。
  - `94068f1`：三個產品的 CHANGELOG 0.5.0 段、根目錄 CHANGELOG 與 `upgrade-notes.yaml`。
  - `7045d3f`：DOCS、README、操作指南與驗收清單。
  - `8b96f40`：未發佈清單。
  - 本紀錄三份（`release-decision-{hermes,n8n,headscale}-0.5.0.md`，同一個 commit，hash 待補）。
- 映像來源：觸發 `release.yaml` 時這個分支的 head（`source_sha`，待補）。**三支都推完之前，不准再往分支推任何 commit（紀錄檔也不行）**：`workflow_dispatch` 永遠跑在分支 head，`source_sha` 又必須等於它（[release](release.md)「部分失敗怎麼辦」）。都推完之後的證據 commit 只加紀錄檔。
- 發版鎖：同一時間只有一個凍結中的升版 PR（計畫 §11.5）；維修版的 PR（#138）先合併，這個分支再與新的 `claude-delivery` 合併、解衝突、重跑檢查，之後才觸發。觸發前再查一次有沒有別的開著的升版 PR。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION_OVERRIDES` | `{'odoo': '0.5.2', 'emqx': '0.5.1', 'litellm': '0.5.1', 'nextcloud': '0.5.1', 'headscale': '0.5.0', 'hermes': '0.5.0', 'n8n': '0.5.0'}`（`VERSION` 維持 0.4.15） |
| 2 | `packaging/inputs.json` 的 `version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS` | 同上；帳本 `runtime-patches.json` 的摘要與 `change` 同步（`scripts/ledger_precheck.py` 0 漂移） |
| 4 | `addons/hermes/config.yaml` 的 `version` | `0.5.0` |
| 5 | `apps/hermes/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.0` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的七路運算式：`<app> == 'odoo' && '0.5.2' || <app> == 'n8n' && '0.5.0' || <app> == 'hermes' && '0.5.0' || <app> == 'emqx' && '0.5.1' || <app> == 'litellm' && '0.5.1' || <app> == 'nextcloud' && '0.5.1' || <app> == 'headscale' && '0.5.0' || '0.4.15'` |
| 7 | `docs/operations/release-decision-hermes-0.5.0.md` | 本檔（推 GHCR、展示機驗收之後補證據） |

- **運算式本機求值**（`packaging/test_validate.py` 的規則，`&&` 先於 `||`）：`odoo`→0.5.2、`n8n`／`hermes`／`headscale`→0.5.0、`emqx`／`litellm`／`nextcloud`→0.5.1、`opendesign`→0.4.15，`ci.yaml` 與 `release.yaml` 兩組結果相同；`packaging/validate.py` 通過。六路形式在火車 A（2026-11-24）的候選建置已被 GitHub 算對；七路是同一種串接寫法多一段，**GitHub 還沒算過**，候選建置的 tag 檢查就是驗證（算錯時 `supply_chain.py candidate` 在推送前停，不燒版號）。
- 開關：`features.py` 的 `MULTI_PROFILE_PRODUCTS` 是 `{'odoo', 'emqx', 'litellm', 'nextcloud', 'hermes', 'n8n', 'headscale'}`，`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON` 同步（精確釘選）。
- 測試釘選：`tests/test_output_schemas.py` 的 n8n `Dockerfile` 位元組釘選換成新的 SHA-256（`ARG BUILD_VERSION` 的預設值；沒有工具、schema 或 handler 的改動）。HM-01 黃金回歸與兩個契約凍結照 `switched_off` 釘住關著的答案，不用改；寫給沒開通 add-on、用 loopback 假後端的既有測試（n8n 的後端網路與錯誤投影測試等）改成釘 `switched_off`，理由寫在開關與版號那個 commit 的內文。

## 內容（寫進 CHANGELOG 的項目）

項目編號（A11、A12、HS1～HS9 等）是 [未發佈清單](../multi-profile/unreleased-changes.md) 的編號；寫進 CHANGELOG 之後，那份清單把它們移掉。這個產品的 CHANGELOG 0.5.0 段（`addons/hermes/CHANGELOG.md`）逐項寫了契約第 1.4 節的 20 點、產品自己的項目、重複 JSON-RPC id 防護（A12）與面板讀弱 ETag（A11）。

## 驗收與批准

依負責人 2026-11-23「整套一次授權」：每個產品過完所有關卡才發佈。

| # | 步驟 | 結果 |
|---|---|---|
| 1 | 推送分支、開 PR | 待補（本機分支 `release/train-b-0.5.0-20261125`，尚未推送；整合分支的草稿 PR 是 #139） |
| 2 | 獨立審查 | 功能審查已在整合分支做完（HM-24、HM-25、HM-26 各兩份審查，修正後通過；筆記在 `docs/provenance/`）；升版片沒有新的程式，只有開關、版號、文件與測試的調整（測試只改 SHA-256 與釘 `switched_off`，沒有改任何斷言；看 `93cc365` 的內文） |
| 3 | CI：`checks`、`Release train`、`Upgrade comparison`（`compare`、`runtime`） | 待補 |
| 4 | 候選建置與容器驗收（`release.yaml` 的 gate → candidate：容器驗收含多帳號階段、子程式 bearer 401 與 HM-13a 還原樹；source／history／全部 layer 的 Gitleaks、SBOM、Grype、授權） | 待補（run、`image.tar` SHA-256、image ID）。這是這個產品第一次在真容器跑多帳號階段（見「發版前的關卡」第 5 點） |
| 5 | J1900 指令集檢查（candidate job 內建，QEMU `-cpu Nehalem`） | 待補 |
| 6 | Store 升級乾跑（展示機，0.4.15 → 候選 `image.tar`；兩個 phase 都要撐過 60 秒、不退出、不重啟） | 待補 |
| 7 | 推 GHCR（`public-release` 核准後的 publish） | 待補（run、manifest digest、image ID） |
| 8 | PR 檢查：映像發佈後重跑 `readiness` 與 `Upgrade comparison` | 待補 |
| 9 | 展示機 HAOS 驗收：多帳號項目 | 待補：`acceptance.md`「Hermes 開通（HM-24）」第 1～6 項：後端身分（使用者批准）、T-02 上限 3、T-03 換連線不換權杖（舊網址照樣可用並連到新後端）、T-04 N×N、Dashboard 登入共用的 429 記錄、T-07／T-12／T-19 長 chat 與名額 |
| 10 | Hermes 60 分鐘負載量測（免費模型；只記錄、不擋發版） | 待補（第 7 項；證據放 repo 外，repo 內只放不含秘密的摘要） |
| 11 | 容量 | 只記錄、不擋發版（負責人 2026-11-23）；驗收記 T-17（閘道、子程式、容器記憶體與停機秒數） |
| 12 | 合併上架 | 待補（三個產品都驗收通過、維修版先合併之後；批准與合併沿用 2026-11-23 的整套一次授權） |

待補：run、digest、展示機結果。

## 發版前的關卡（草稿時列的阻擋事項）

1. **維修版先合併**：這一批建在維修版（PR #138）之上；維修版的映像也要先推完、PR 合併，這一批才與新的 `claude-delivery` 合併並凍結 head。
2. **映像尚未建置**：這份草稿寫成時，沒有建置、沒有推 GHCR、沒有展示機驗收；上面的表每一格都要等實際執行後補。
3. **`upgrade-notes.yaml`**：根目錄的 `upgrade-notes.yaml` 已有火車 B 的人讀條目；`addons/hermes/upgrade-notes.yaml`（`AGENTS.md` 第 3 點）沒有建，`Upgrade comparison / compare` 要求時照它的報告補（`change` 與 `key` 照報告抄）。
4. **七路版本運算式**：GitHub 還沒算過（見上）；候選建置的 tag 檢查是第一次驗證。
5. **容器驗收的多帳號階段第一次在真容器跑這個產品**：本機沒有 Docker，只有單元測試與真子程序的測試；候選建置失敗時先查探針、entrypoint 與守門，不要放寬（`docs/multi-profile/unreleased-changes.md` 第 5 節第 3 點）。
6. **HA Core**：`ha_role.py` 審過到 Core 2026.11.3 並放行已審查月份的後續修補版；展示機 Core 2026.7.2 沒問題，更新的月份（2026.12.0 起）要先補審。

## 本機檢查（一般使用者；以 GitHub CI 為準）

- 2026-11-25，本機分支 `release/train-b-0.5.0-20261125` 推送前（尚未推送），一般使用者、Python 3.13、`/tmp/ha-mp-*` 短 TMPDIR（用完刪除）：`scripts/ledger_precheck.py` OK（0 漂移）、`packaging/validate.py` 通過、gitleaks（`origin/integ/train-b-20261125..HEAD`，33 個 commit）0 命中；`packaging` unittest 389 案過（5 skip；其中 8 案是這一批新加的探針測試）；面板 Node 測試 126 過。
- 指名的 13 個測試檔在最後的樹上（開關已開）：`test_upgrade_zero_rewrite`、`test_single_profile_golden`、`test_mcp_contract_freeze`、`test_admin_contract_freeze`、`test_output_schemas`、`test_product_boundary`、`test_product_ha_role`、`test_hermes_multi_profile`、`test_n8n_multi_profile`、`test_headscale_multi_profile`、`test_ha_role`、`test_backend_loopback`、`test_tool_inventory`：1,056 案全過。
- 全套 pytest（209 個測試檔，開關已開）：共用鎖一次只能跑一個 pytest，所以分批跑完。第一輪（釘選前）紅 168 案：**122 案（24 個檔）是開關造成**，Hermes 與 n8n 的真子程式碰 loopback 假後端，開通後被 HM-20 拒絕（`BACKEND_DESTINATION_DENIED`）；這 24 個檔已改成自己要 `switched_off`（`93cc365`，沒有改任何斷言），重跑它們與兩個已知的環境檔共 26 檔：638 過、7 敗，剩下的 7 案都是環境問題。其餘 46 案是本機環境，不是這一批造成的：需要 root 的 2 案（`test_owned_executable`、`test_profile_store` 的 uid 10001）與 `test_restore_detection` 的 5 案；需要 Chromium 與 playwright 的 22 案（`test_owned_browser_ipc` 5、`test_owned_browser_redirect` 16、`test_owned_ui` 1）；本機的 `localhost` 只解析到 127.0.0.1、沒有 `::1` 的 3 案（`test_resolver_regressions` 的 `test_fallback_after_refused_address[localhost-*]`）；程序群組清理在本機逾時的 3 案（`test_review_regressions` 2、`test_lifecycle` 1）；`test_profile_lifecycle` 的 30 秒停止 1 案；CPU／記憶體比較的 9 案（`test_request_structure` 7、`test_reply_worker` 1、`test_profile_quotas` 1，機器負載高時 guard 比 decode 慢）；本機 Node 是 26.12.1、釘的是 26.13.1，`test_boundary` 的原生模組 1 案。**除了最後那案，其餘 45 案在基準 commit `0ab5393` 上同樣失敗**（在基準匯出上重跑過；CPU 比較那幾案隨機器負載，哪幾個參數變體敗不固定，但同樣的案例在基準上也敗；Node 那案在基準上會過，因為基準釘的 Node 版本剛好是 26.12.1）。這些案例以 GitHub CI 為準（root、CPython 3.12.3、Node 26.13.1、Chromium、0 skip），不宣稱 CI 綠。
- 容器探針：本機沒有 Docker，只有單元測試（`packaging/test_container_probe.py`、`test_container_profiles.py` 的火車 B 8 案）與真子程序的手動量測（n8n 約 1 秒、Hermes 約 3.3 秒、Headscale 約 6 秒開始監聽；n8n 不在 HOME 留東西，Hermes 與 Headscale 的 `child/` 是空的）。探針的多帳號階段第一次在真容器跑這三個產品是候選建置，失敗時先查探針與 entrypoint，不要放寬。

## 已知限制（不擋這一版）

- **Hermes 每個子程式的記憶體**：`CHILD_MEMORY_MIB` 的 160 MiB 是暫定值（PaaS 量到 160～168 MiB 且負載後不回落）；60 分鐘量測只記錄，不改常數。
- **Dashboard 登入限流共用**：所有帳號的子程式從同一個來源位址登入 Dashboard，指向同一個 Dashboard 的帳號共用 Hermes 的限流（每位址每分鐘 10 次，成功也算）；驗收記有沒有 429。
- **換連線不換權杖**：舊網址的持有人在換連線之後仍連到新後端；要收回存取須明確輪替或撤銷（DOCS 與 CHANGELOG 已寫）。
- HA Core：管理員驗證只審過到 2026.11.3（後續修補版自動放行）；新月份的 Core 要等 add-on 新版。
- 容量：每個子程式 160 MiB 是暫定值；FD、記憶體飽和、TLS 與慢速 DNS 的壓力沒有在目標硬體量（只記錄、不擋發版）。
