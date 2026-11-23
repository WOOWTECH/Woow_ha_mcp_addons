# Nextcloud 0.5.0（多帳號 train A）發佈紀錄（草稿）

狀態：**升版分支準備完成、尚未建 PR、映像尚未建置；所有關卡都還是待做**。這是 `woow_mcp_nextcloud` 一個產品的發版：Nextcloud 開通多帳號、版號 0.4.14 → 0.5.0，與 train A 的另外兩個產品同一批（LiteLLM、Nextcloud、EMQX；train A，一個升版 PR、各產品各自 `release.yaml`）。
Hermes、Headscale、n8n 的開關與版號都不動，OpenDesign 不跟著升來源版本；Odoo 0.5.0 是更早一個、獨立的發版（[Odoo 發佈紀錄](release-decision-odoo-0.5.0.md)）。
合併升版 PR 就是發佈到 WOOW App Store：下面每一步都**待批准**。這份草稿**不宣稱映像、HAOS、真後端或商店驗收**；那些要先過關卡，再取證，再把本檔改成最終紀錄（HM-17：readiness 只認推送之後寫的、並寫明版本與 slug 的發佈紀錄）。

## 範圍

- **只有 Nextcloud**（`woow_mcp_nextcloud`）：`features.MULTI_PROFILE_PRODUCTS` 加 `nextcloud`（與 `odoo`、其他兩個火車 A 產品一起），`addons/nextcloud/`、`apps/nextcloud/Dockerfile` 的版號 0.5.0。功能依據：#126（HM-22，含 11/20 的 PaaS 對齊提交 `b15e9a2`，整合於 PR #134）。
- 不在範圍：Hermes（#128）、Headscale（#130）、n8n（#129）的開關與版號（第二批，各自另有缺口，見 `docs/multi-profile/`）；OpenDesign 與 Odoo Manage 不開放多帳號（DQ-28）。共用預設版號 `VERSION` 維持 0.4.14，0.5.0 是 Nextcloud 自己的版號線（DQ-32），和 Odoo 0.5.0、Headscale 0.4.19 一樣寫在 `VERSION_OVERRIDES`。
- 路線：這條線只用 GitHub（`.github/workflows/release.yaml`：gate → candidate → publish，publish 在 `public-release` environment 核准，只收 `release/*` 分支）。

## 來源

- 分支 `release/train-a-0.5.0-20261123`：底是整合分支 PR #134 的 head `d8fe2912487199e197ca2410ce51e2a34a108309`（Nextcloud #126、LiteLLM／EMQX #133 與審查 F-1～F-4 修正，CI 綠），再以 merge commit 併入 Odoo 發版頭 `27c17b3e99b6662d9afacec8a4234a0c71aa331e`（`release/odoo-0.5.0-20261119`，PR #131），讓它預期 #131 合併後的 `claude-delivery`。Odoo 若因修正而改 head（0.5.1），本分支要重新對齊、候選作廢重跑。
- 升版 commit：開關、版號資料、測試釘選與帳本（第一個）；CHANGELOG、DOCS、README、`upgrade-notes.yaml`、`unreleased-changes.md`（第二個）；本紀錄（第三個）。推送後 head 只能再加 commit、不 rebase、不 force push；映像從觸發當下凍結的 PR head 建，之後的證據 commit 只加紀錄檔（發版鎖）。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION_OVERRIDES` | `{'odoo': '0.5.0', 'emqx': '0.5.0', 'litellm': '0.5.0', 'nextcloud': '0.5.0', 'headscale': '0.4.19'}`（`VERSION` 維持 0.4.14） |
| 2 | `packaging/inputs.json` 的 `version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS` | 同上；帳本 `runtime-patches.json` 的摘要與雜湊同步 |
| 4 | `addons/nextcloud/config.yaml` 的 `version` | `0.5.0` |
| 5 | `apps/nextcloud/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.0` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的六路運算式（`odoo`、`emqx`、`litellm`、`nextcloud` 是 0.5.0，`headscale` 是 0.4.19，其餘 0.4.14） |
| 7 | `docs/operations/release-decision-nextcloud-0.5.0.md` | 本檔（推 GHCR 之後改成最終紀錄） |

- **運算式本機求值**（`packaging/test_validate.py` 的規則，`&&` 先於 `||`）：`app=odoo`→0.5.0、`emqx`→0.5.0、`litellm`→0.5.0、`nextcloud`→0.5.0、`headscale`→0.4.19、`n8n`／`hermes`／`opendesign`→0.4.14，`ci.yaml` 與 `release.yaml` 兩組結果相同；`packaging/validate.py` 通過。三路形式 GitHub 在 Odoo 的候選（2026-11-22，tag `local/mcp-odoo:0.5.0`）算過；六路是同一種串接多幾段，**GitHub 還沒算過**，候選建置的 tag 檢查就是驗證（算錯時 `supply_chain.py candidate` 在推送前停，不燒版號）。
- 開關：`features.py` 的 `MULTI_PROFILE_PRODUCTS` 是 `{'odoo', 'emqx', 'litellm', 'nextcloud'}`，`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON` 同步（精確釘選；EMQX 那一行見 HM-23 審查 S-2）。Hermes、Headscale、n8n 仍關。
- Nextcloud 另改 `config.yaml` 與 `apps/nextcloud/Dockerfile` 的 `description`（「one Nextcloud account」→「a Nextcloud account per profile」；validate 逐字比對兩處）。

## 批准表（GitHub 路線；全部待做）

| 步驟 | 誰做 | 要負責人批准 | 狀態 |
|---|---|---|---|
| 1. 升版分支（`release/train-a-0.5.0-20261123`）：Odoo 發版頭 `27c17b3` 併入整合分支 `d8fe291`，再加開關、版號與文件 commit | 代理 | 否（只推分支，不開 PR） | 本機完成，推送見「來源」 |
| 2. 秘密預檢、帳本預檢、packaging 驗證、受影響測試 | 代理 | 否 | 本機完成（「本機檢查」一節）；以 GitHub CI（root、Python 3.12.3、0 skip）為準 |
| 3. 建 PR（Odoo #131 合併之後以新 `claude-delivery` 為底再合併一次、確認 Odoo 內容零差異）；PR `checks` 綠 | 代理／CI | 開 PR 本身否；合併要 | **未做**（使用者指示「先不開 PR」） |
| 4. `release.yaml`（`app=nextcloud`、`source_sha`＝凍結的 head）gate＋candidate：建置、容器驗收（多帳號階段首次對此產品真跑）、供應鏈閘門、J1900；不推 GHCR | 代理觸發／GitHub 託管機器 | **要**（每次觸發；publish 停在等待時可 Reject，什麼都不推、不燒版號） | **待批准／未觸發** |
| 5. 推 GHCR 前乾跑 Store 升級測試（N100，0.4.14 Release 映像 → 候選 `image.tar`，加 `upgrade-check/seed`、`verify`） | 代理 | **要** | **未做** |
| 6. 展示機（J6412）真後端驗收（下一節），先局部備份、測後清理 | 代理依清單 | **要**（主機、真後端身分的建立與清理） | **未做** |
| 7. 推 GHCR（`release.yaml` 的 publish；推了就燒 0.5.0，之後修正只能發 0.5.1） | 負責人／被授權的代理在 GitHub 核准 `public-release` | **要** | **未做** |
| 8. 證據 commit（本檔改成最終紀錄、`ha-test-nextcloud-0.5.0.md`，只加紀錄檔）→ `checks`、`readiness`、`Upgrade comparison`、`Release train` 在 PR head 綠 | 代理／CI | 否 | **未做** |
| 9. 合併（＝上架 WOOW App Store），merge commit | 負責人（或明確授權的代理，記錄授權原文） | **要** | **未做** |
| 10. 合併 commit 上 `woow-addon-release.yml` 與 `release-train.yml` 的非 PR run 成功、`woow_mcp_nextcloud-v0.5.0` 正式 Release；Store 同步後從 Store 安裝或升級再驗（UC-08、UC-10、sentinel；記 Supervisor 版本） | 代理 | **要** | **未做** |

## 展示機真後端驗收（步驟 6 要做的）

- 驗收步驟寫在 `docs/operations/acceptance.md` 對應產品小節與 P9 套件（`docs/operations/ha-p9-kit.md`）；一次只測一個產品、先做局部備份、測後清理（移除測試 app、演練備份、測試庫、HA 測試管理員、`/share` 與 `/addons` 暫存、金鑰）、記錄當時 load。展示機近滿載（load 約 3.4／4 核、可用 RAM 約 6.9 GiB），不能和其他重負載並行；04:00 台北每日備份要避開 03:30–05:00。
- 後端：展示機（J6412 HAOS 18.1）上的 Nextcloud Office add-on `1b7b4ce7_woow-nextcloud-office` 0.2.3（執行中，約 327 MiB；**含哪個 Nextcloud 實例要先確認**）。
- 需要先備好、由主對話建立並事後刪除的後端身分：
  - 同一台測試用 Nextcloud 上三個專用使用者 A、B、C（C 只給換帳號用），各一個 App 密碼；建立與刪除都要記錄。
  - 節流單位那一步（UC-12）會在真的 Nextcloud 留下失敗登入紀錄，做完要用 `occ security:bruteforce:reset <ip>` 或管理頁重設暴力破解防護。
  - 合成的測試檔案與行事曆資料，測完清掉；展示機 Nextcloud 的 CalDAV 本身慢（`list_calendars` 約 2.5 s），逾時門檻要考慮。
- T 列：T-01（版本與 digest）、T-03（換帳號換 token、只換 App 密碼不換、主機大小寫不換、貼上頁面路徑不換）、T-04（兩個使用者的 WebDAV 互看不到）、T-05、T-07（存政策只重啟該帳號；11/20 起收緊不重啟、放寬才重啟）、T-23（P9 `--cross`、容器探針的多帳號階段）、T-29（清理與合成憑證掃描）；外加 UC-12 的節流單位與 T-02、T-06、T-08、T-09、T-11～T-14、T-17、T-18、T-20、T-21、T-24、T-25、T-27。
- 每次升版都要重驗的四項：UC-08（完整還原）、sentinel 穩定性、UC-10（Ingress）、Supervisor 版本記錄。

## 還擋著發版的事

1. **Odoo HM-19c 要先過**（共用核心）：閘道層的放大倍數、位元組預算與全域最壞值只在 Odoo 首發量，`unreleased-changes.md` 第 5 節第 5 點明說 HM-31 預算任何產品下一版都會帶出去，所以 Odoo 在 J6412 的容量放行（候選 run 45085095296，展示機量測進行中）通過之前，Nextcloud 不能發。這是**前置依賴，不是每產品重做一套閘道容量驗收**。
2. **Odoo #131 先合併**：本分支預期 #131 合併後的 `claude-delivery`；合併後要以新 `claude-delivery` 為底再合併一次（merge commit）、確認 Odoo 內容零差異、PR 的 checks 再綠。Odoo 若發 0.5.1，本分支候選全部作廢重跑。
3. **11/20 的 PaaS 對齊提交（`b15e9a2`）沒有獨立審查的原始紀錄**；火車 A 整合審查（F-1～F-6）覆核了合併與衝突處理，F-2、F-3、F-4 已解決，F-5（切路徑規則偏寬，裝在名為 `apps`、`login`、`settings` 的子路徑會被存成錯誤根網址）仍是已知限制，已寫進 CHANGELOG 與 DOCS，未補進 `nextcloud-paas-parity-20261120.md`。
4. **契約 #129／#130 的刻意差異**（存新寫法、貼上頁面路徑、存政策收緊不重啟）要被接受或回補 PaaS；Odoo 與 Hermes 的網址要不要也照伺服器比。
5. **真後端與帳密**：三個專用使用者與 App 密碼要由主對話建立並事後刪除；Nextcloud 暴力破解防護的節流單位推定以來源位址計，只有真後端能確認。
6. 容量：160 MiB／子程式、最壞 896 MiB，沒有 Nextcloud 實測數字（建議在真後端驗收時記冷啟動、RSS／PSS、停機時間）。
7. **CI 與候選首次真跑**：容器驗收的多帳號階段與 HM-20 tripwire 對 Nextcloud 是第一次、六路版號運算式是第一次；本機是 Python 3.13、一般使用者，29 案要 root／Chromium，CI 是 root＋CPython 3.12.3＋`/workspace/WOOWTECH` 路徑，本機綠不等於 CI 綠。
8. **J1900 指令集檢查**（DQ-42）在 candidate job 內建；J1900 沒有實機，以 QEMU `-cpu Nehalem` 檢查替代（使用者已接受只在 J6412 量測）。
9. **HA Core**：`ha_role.py` 只認到 Core 2026.11.2；展示機 Core 2026.7.2 沒問題，目標 HAOS 若比 2026.11.2 新要先補審。

## 本機檢查（一般使用者；以 GitHub CI 為準）

- 2026-11-23，分支 head 推送前，一般使用者、Python 3.13、`/tmp/ha-mp-*` 短 TMPDIR（用完刪除）：`scripts/secret_precheck.py` 0 命中、`scripts/ledger_precheck.py` OK（0 漂移）、`packaging/validate.py` 通過；`packaging` unittest 371 案過（5 skip）；面板 Node 測試 119 過、建置與 closure 檢查過；全套 pytest 分兩輪（第一輪中途短 TMPDIR 被外部清掉，之後的案例重跑）加受影響檔案的最後一輪：沒有開關相關的失敗，唯一因為開通而紅的案例（LiteLLM 真子程式的錯誤本體測試讀到開著的開關）已改成自己指定 `switched_off`。
- 本機沒跑到或不能算的案例（以 CI 為準，root、CPython 3.12.3、Node 26、Chromium、0 skip）：需要 root 的（`test_restore_detection` 的 root 案例、`test_owned_executable`、`test_profile_store` 的 uid 10001 案例）；需要 Chromium 與 playwright 的（`test_owned_browser*`、`test_owned_ui`）；n8n 的 better-sqlite3 原生模組在本機 Node 22 回退成 sql.js 的兩個案例（`test_boundary`、`test_n8n_catalog_copy`，CI 用 Node 26）；`test_request_structure` 的 CPU 比較案例（Odoo 發版頭的測試，本機負載高時 guard 比 decode 慢，兩次都 0.0354 對 0.0318 秒）。這些不宣稱 CI 綠。

## 發佈前的預期

- 映像推上 GHCR 之前，`readiness` 會因 `amd64-mcp-nextcloud:0.5.0` 拉不到、本檔不是最終紀錄而失敗，`Upgrade comparison` 也會因新版映像還沒發佈而失敗（0.4.14 同樣）。不放寬規則。
- 升版比對要求時才建 `addons/nextcloud/upgrade-notes.yaml`（根目錄 `upgrade-notes.yaml` 已有 0.5.0 條目）；接受漏洞先請負責人同意。

這份紀錄不宣稱映像、HAOS、正式後端或商店驗收；那些要在關卡通過、批准後另外取證。
