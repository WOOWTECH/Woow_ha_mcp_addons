# Odoo 0.5.0（多帳號首發 R1）發佈紀錄（草稿）

> **2026-11-23 註記：0.5.0 已推到 GHCR 但從未上架 Store（Store 上是 0.4.14），已由 0.5.1 取代**（HM-19b 驗收重現 F1，負責人決定修好再發 0.5.1）。這份草稿保留作歷史；現行紀錄見 [release-decision-odoo-0.5.1.md](release-decision-odoo-0.5.1.md)。

狀態：**升版 PR 準備中（HM-19a）：本機兩個 commit，等獨立審查後才推送、開 PR；映像還沒建置**。這是 Odoo 一個產品的發版：Odoo 開通多帳號、
版號 0.4.14 → 0.5.0；其他產品（n8n、Hermes、EMQX、LiteLLM、Nextcloud、Headscale）的版號與開關都不動，OpenDesign 不跟著升來源版本。
合併升版 PR 就是發佈到 WOOW App Store：下面計畫 §11.3 的第 3～11 步（建置、量測、推 GHCR、HAOS 驗收、合併）每一步都**待負責人批准**。
這份共用紀錄不是 readiness 認的紀錄：readiness 只認推送之後才寫的 `release-decision-odoo-0.5.0.md`（HM-17；[release](release.md)「升版時要改的版號資料」第 7 項）。

## 範圍

- **只有 Odoo**（`woow_mcp_odoo`）：`features.MULTI_PROFILE_PRODUCTS` 從空集合改成 `{'odoo'}`，`addons/odoo/`、`apps/odoo/Dockerfile` 的版號 0.5.0。
- 不在範圍：其他產品的開關與 `addons/<產品>/`（R2 起各自的升版 PR，計畫 §11.4）；OpenDesign 與 Odoo Manage 不開放多帳號（DQ-28）。
  共用的預設版號 `VERSION` 維持 0.4.14：0.5.0 是 Odoo 自己的版號線（DQ-32），和 Headscale 0.4.19 一樣寫在 `VERSION_OVERRIDES`。
- 依據：多帳號計畫（repo 外，`artifacts/ha-multiprofile-parity-20261114/PLAN-zh-TW.md`）§11.3（升版 PR 逐檔核對清單與批准表）、§11.4（R1 前提）、
  §12.3「HM-19a」、§10.6（HM-19b 的通過標準）；[多帳號契約](../multi-profile/contract.md)第 1.4 節（開通後預設帳號會變的事）；
  [各產品下一版的變更清單](../multi-profile/unreleased-changes.md)第 1、7 節。
- 路線：負責人 2026-11-17 決定這條線只用 GitHub。計畫寫的「repo 外 builder」各步改成本 repo 的 `.github/workflows/release.yaml`（GitHub 託管機器；
  gate → candidate → publish，publish 要負責人在 `public-release` environment 核准；只收 `release/*` 分支），見 [release](release.md)「發版：GitHub 託管機器」。

## 為什麼發這一版

- R1（計畫 §11.4）：Odoo 是第一個開通多帳號的產品，PaaS 的首發場景（同一個 Odoo 資料庫、每個 AI 代理一個受限使用者，U-03）。前提 HM-00～HM-18、
  HM-20、HM-30、HM-27 都已合併（最後是 #122 HM-18，`95b7e9d`）。HM-15 條件式 listener 身分檢查已在 #132 實作、獨立安全審查並合入本候選分支；
  #132 尚未合入主線，CI 與實際 HAOS uid 10001／額外帳號的檢查能力仍待驗。檢查不可用時依契約第 9 節 #13 降級並保留子程式 bearer 主防線。
- 開通後：預設帳號（今天的設定與權杖）之外最多 5 個額外帳號，每個帳號一組 Odoo 連線、一把權杖與兩條網址、一份工具政策、一個子程式；只看權杖決定帳號。
  只用預設帳號的安裝，權杖、兩條網址、`state.json` 位元組、政策、子程式 port 3000 都不變；仍看得到的改變是契約第 1.4 節的 20 點（含 HM-10 審查 S-6 的
  兩個位元組變化），逐項寫在 [Odoo CHANGELOG](../../addons/odoo/CHANGELOG.md) 0.5.0 段與根目錄 [upgrade-notes.yaml](../../upgrade-notes.yaml)。
- 同時帶出 0.4.14 之後合併、Odoo 映像裡多的程式：#108（HM-13b 開機守門，含共通項 A8）、#112（HM-13c 還原核對與單帳號還原提示，含 A9）、
  #116（HM-27 密鑰網址的 Origin 清單）。#109、#122、#123、#124 只改發版工具、測試與文件（`docs/provenance/` 的筆記跟著映像出去，沒有行為）。

## 來源

- 基準：`claude-delivery` `95b7e9d0fc4a`（#122 的合併，2026-11-19）。分支 `release/odoo-0.5.0-20261119`（`release.yaml` 只收 `release/<一段名稱>`）。
- 升版 commit：`dfd146d`（開關、版號資料、hook 搬家、測試、文件）；本紀錄與 HM-19a 筆記在下一個 commit。推送後 head 只能再加 commit、不 rebase、
  不 force push；映像從觸發當下凍結的 PR head 建，之後的證據 commit 只加紀錄檔（發版鎖，計畫 §11.5）。
- 發版鎖：2026-11-19 16:2x（台北）用公開 API 唯讀查，開著的 PR 只有 #125～#130，沒有其他升版 PR。HM-21～HM-26（#125～#130）是不改版號的功能片，照計畫在 HM-19b 之後才合；它們先合會逼本 PR 合併
  `claude-delivery`、重產帳本，已觸發的建置要重來。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION_OVERRIDES` | `{'odoo': '0.5.0', 'headscale': '0.4.19'}`（`VERSION` 維持 0.4.14） |
| 2 | `packaging/inputs.json` 的 `version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS` | 同上（註解改成兩個 override）；帳本 `runtime-patches.json` 的摘要同步 |
| 4 | `addons/odoo/config.yaml` 的 `version` | `0.5.0` |
| 5 | `apps/odoo/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.0` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的三路運算式 `<app> == 'odoo' && '0.5.0' \|\| <app> == 'headscale' && '0.4.19' \|\| '0.4.14'` |
| 7 | `docs/operations/release-decision-odoo-0.5.0.md` | 推 GHCR 之後寫（第 9 步）；本檔不算 |

- **三路運算式是第一次**：0.4.14 與 Headscale 0.4.19 都是兩路（GitHub 算過）。`packaging/test_validate.py` 照 GitHub Actions 的運算規則求值過，
  但 GitHub 實際算的值還沒看過（[release](release.md) 那一節）。第一次觸發 `release.yaml` 之前，先用拋棄式 workflow 只印出運算式的值（不建置）：
  要一個 workflow 檔與一次觸發，**待負責人批准**。不做的話，算錯時 `supply_chain.py candidate` 在推送前就停（tag 不是 `local/mcp-odoo:0.5.0`），
  不會推錯，但那次 candidate 白跑；這個取捨由負責人定。
- 開關：`packages/mcp-admin-core/mcp_admin_core/features.py` 只改 `MULTI_PROFILE_PRODUCTS` 那一行（帳本摘要同步）。

## 改了什麼（升版 commit）

- **開關與版號**：上一節。升版重算 `__init__.py`、`features.py` 的帳本；HM-15 合入後另更新 listener 相關列管檔，`scripts/ledger_precheck.py` OK；`apps/runtime`、`apps/*/launch.py`
  沒改，`docs/tool-surface.*` 不用重產（`tool_inventory.py` 沒有漂移）。
- **Store 升版比對 hook**：HM-16 的草稿 `packaging/hooks/seed`、`verify` 用 `git mv` 搬到 `addons/odoo/upgrade-check/`（保留可執行位元，只改說明的兩句），
  `tests/test_upgrade_hooks.py` 改指新位置。只讀、與版本無關；第一次在 Store 的 CI 跑是本 PR 的 `Upgrade comparison`（UC-19：hook 能不能以 root 讀
  `state.json`、連到 8081；不行就停下回報，不改成走管理 API，HM-16 筆記第 13 節）。
- **CHANGELOG 與文件**：`addons/odoo/CHANGELOG.md` 0.5.0 段（契約第 1.4 節 20 點、兩個位元組變化、守門的通知與 `KEPT_NOTICE`、`restore_notice`）、
  `addons/odoo/DOCS.md`「多帳號（0.5.0 起）」、`addons/odoo/README.md`、根目錄 `CHANGELOG.md`、`README.md`（第 46～47 行那句與 Odoo 0.5.0 狀態）、
  根目錄 `upgrade-notes.yaml`（0.5.0 條目，計畫 §7.3）；`unreleased-changes.md` 照「怎麼更新」第 3 點；repo 文件裡「還沒有產品開通」的狀態句改成
  「Odoo 從 0.5.0 起開通」。翻譯（`translations/*.yaml`）只有 8081 的說明，沒有新字串，沒改。`addons/odoo/upgrade-notes.yaml` 照 `AGENTS.md` 第 3 點
  等升版比對要求才建（options、schema、ports 都沒改，第 1 類比對預期不報）。
- **測試**：開關一開，寫給「沒開通」的測試會讀到倉庫的開關。逐案改法與理由在 [HM-19a 筆記](../provenance/ha-multiprofile-HM-19a-20261119.md)：
  寫給沒開通的測試自己指定 `switched_off`（新的 `tests/switch_modes.py`，和 HM-23、HM-26 收斂的同名工具同一個意思），HM-01 黃金回歸與兩個契約凍結
  對每個產品照舊逐位元（期望值一個字都沒改）；開通的版本由 `tests/test_router_passthrough.py` 開著再跑一次；釘開關的測試改成精確釘
  `{'odoo'}`。

## HA Core 版本（2026-11-19 07:26Z 查公開來源，唯讀）

- home-assistant/core 的 GitHub release 與 tag：最新是 **2026.11.2**（2026-11-16T20:03:59Z，tag commit `ff5d56b8`），沒有 2026.11.3，也沒有 2026.12.0
  的預覽版；Supervisor 最新 2026.11.0。`ha_role.py` 已認到 2026.11.2（#120），所以 Core 白名單不用補審，`ha_role.py`、`docs/ha-role-core-contract.md` 沒改。
- 之後出的 Core 版本照 [ha-role-core-contract](../ha-role-core-contract.md)「Adding a release」另開一片審；HM-19b 的 HAOS 若 Core 比 2026.11.2 新，面板會拒絕，
  要先補審（`unreleased-changes.md` 第 5 節第 4 點）。

## 計畫 §11.3 的批准表（GitHub 路線）

| 步驟 | 誰做 | 要負責人批准 | 狀態 |
|---|---|---|---|
| 1. 開升版 PR（§11.3 逐檔核對清單，下一節） | 代理 | 否（只開 PR） | 本機完成（升版 commit `dfd146d`）；獨立審查後推送、開 PR，標題「⛔ 勿代 merge｜待覆核 — HM-19a …」 |
| 2. 秘密預檢、帳本預檢；PR `checks` 綠 | 代理／CI | 否 | 本機兩個預檢 OK（「本機檢查」一節）；PR `checks` 推送後由 CI（root、0 skip）跑，以它為準 |
| 3. 建候選映像＋容器驗收（含多帳號階段、root 還原樹、sentinel）＋供應鏈閘門＋J1900；不推 GHCR。GitHub 路線：在本分支觸發 `release.yaml`（`app=odoo`、`source_sha`＝凍結的 head），gate 與 candidate 沒有推送權限。這也是計畫的「HM-19a 前的開關開乾跑」：publish 停在等待時按 Reject 就什麼都不推、不燒版號 | 代理觸發／GitHub 託管機器 | **要**（每次觸發；先定三路運算式怎麼驗，上一節） | **待負責人批准** |
| 4. 推 GHCR 前乾跑 Store 升級測試：0.4.14 的 Release 映像 → 候選映像（第 2、3 類，加 `upgrade-check/seed`、`verify`） | 代理 | **要** | **待負責人批准**：Store 的升級測試只拉已發佈的映像。乾跑要一台有 Docker 的機器，用 Store 的 `upgrade_runtime.py` 跑 candidate 留的 `image.tar`（artifact 只留 3 天）；依計畫須在推送前完成並記錄結果 |
| 5. 容量量測（HM-19c）：J6412（可以的話 J1900）上 1～6 個 Odoo 帳號；全域最壞值對「MemAvailable－保留量」；CPU 飢餓；冷開機全部就緒 | 代理 | **要**（主機、硬體） | **待負責人批准**；展示機是 J6412（目標硬體，下面「發版前預驗」），J1900 與出貨機的記憶體規格（DQ-29）還沒給。**擋發版**：契約第 5 節「HM-19c 放行條件」與 HM-30 的 D1～D3 量測，過不了就回功能片改常數，不改不能發版 |
| 6. 要改常數 → 回功能 PR 改、重建（回第 3 步） | 代理 | 否 | **待負責人批准**（看第 5 步） |
| 7. 推 GHCR（`release.yaml` 的 publish；推了就燒 0.5.0，R10 RG-15） | 負責人在 GitHub 核准 `public-release` | **要** | **待負責人批准** |
| 8. HAOS 驗收（§10.6；HM-19b；下面的清單） | 代理依清單 | **要**（主機；真後端身分的建立與清理） | **待負責人批准** |
| 9. 證據 commit（`release-decision-odoo-0.5.0.md`、provenance JSON，只加紀錄檔）→ `checks`、`readiness`、`Upgrade comparison`、`Release train` 在 PR head 綠 | 代理／CI | 否 | **待負責人批准**（跟著第 7、8 步） |
| 10. 合併（＝上架 WOOW App Store），merge commit | 負責人本人 | **要** | **待負責人批准** |
| 11. 合併 commit 上 `woow-addon-release.yml` 與 `release-train.yml` 的非 PR run 成功（Store registry 的 `required_workflows`）、`woow_mcp_odoo-v0.5.0` 正式 Release；Store 同步後從商店安裝或升級再驗一次（UC-08、UC-10、sentinel；記 Supervisor 版本） | 代理（負責人決定何時） | **要** | **待負責人批准** |

- 步驟 3～11 的順序照計畫：先候選與容器驗收、再量測、最後才推 GHCR；HAOS 驗收在正式映像上做（計畫 §0.2「先建映像與容器驗收、再側載量測、最後才推 GHCR」）。
- HM-19c 要在推 GHCR 前量。計畫寫「UC-20 是『可以』時把候選映像側載到 QA HAOS 量；『不行』時用不改版號的拋棄式開關開映像量（建、不推），或明文接受燒號並預留 0.5.1」；
  HM-03a 量到 UC-20 是「不行」（Supervisor 安裝時一定去拉映像）。用哪一種、在哪台量（展示機是 J6412）由負責人定。
- 每次觸發前照 [release](release.md)「負責人批准前的檢查清單」：`.github/` 與 `packaging/` 相對 `claude-delivery` 只改了版號資料（本 PR 另有 `packaging/hooks/`
  搬走，`packaging/` 只剩 `validate.py`、`inputs.json` 兩個版號檔，見下一節）。

## 計畫 §11.3 逐檔核對清單

| 清單的檔 | 本 PR |
|---|---|
| `Hc/features.py`（加產品） | 加 `odoo` |
| `packaging/validate.py`（`VERSION_OVERRIDES`）、`packaging/inputs.json`、`Hc/__init__.py`（`PRODUCT_VERSIONS`） | 改（上面「版號資料」） |
| `.github/workflows/ci.yaml`、`release.yaml` | 改，`validate.py` 產生的三路運算式 |
| `apps/odoo/Dockerfile`（`ARG BUILD_VERSION`） | 改 |
| `addons/odoo/config.yaml`、`CHANGELOG.md`、`DOCS.md`、`README.md` | 改；`description` 不用改 |
| `addons/odoo/translations/*` | 沒改（沒有新的使用者字串） |
| `upgrade-check/seed`、`verify` | 從 `packaging/hooks/` 搬進 `addons/odoo/upgrade-check/` |
| 根 `CHANGELOG.md`、根 `README.md`（Odoo 一句）、根 `upgrade-notes.yaml` | 改 |
| `Hc/ha_role.py`（Core 白名單補審）、`docs/ha-role-core-contract.md` | 不用改（上面「HA Core 版本」） |
| `docs/provenance/runtime-patches.json`（`__init__.py`、`features.py` 摘要） | 改 |
| `docs/operations/release-decision-odoo-0.5.0.md`、`ha-test-odoo-0.5.0.md`、provenance JSON | 推 GHCR 與 HAOS 驗收之後寫（第 8、9 步）；這份共用紀錄先寫 |
| `packaging/container_probe.py`、`container_acceptance.py` 的假後端位址（HM-16、HM-20） | 不用改：HM-16 已讓兩檔看開關（開通的產品給一次性 internal bridge、假後端綁容器的私有位址），HM-20 的 tripwire 測試開關一開照樣過；容器驗收的多帳號階段第一次真跑是第 3 步 |
| 綁版號的測試 | 不用改：HM-17 之後讀 `version_for()` 與 `packaging/inputs.json` |
| `packaging/secret-triage.json` | 不用改（秘密預檢 0 命中） |

## J1900 指令集檢查（DQ-42：每次發版都跑）

- 在第 3 步的 candidate job 裡（`packaging/j1900_check.py`：QEMU user-mode `-cpu Nehalem`，比 J1900 嚴格；核心與子程式兩個 venv 的原生擴充模組，
  原生與 QEMU 兩邊 import 比對、SIGILL 一律擋），結果寫進 `j1900-odoo.json` 與 publish 的證據。publish 的 `image_handoff.py load` 要求 J1900 紀錄
  `passed` 而且 image ID 就是要推的那個，所以沒過就推不出去。
- Odoo 的允許清單只有 `_tkinter`（官方 python slim 映像不帶 Tcl/Tk）；Odoo 的子程式沒有 caio。0.5.0 沒改任何相依（`uv.lock`、Dockerfile 的相依段都沒動），
  預期和 0.4.14 一樣（子程式 venv 83 個、核心 venv 79 個原生模組原生 import 成功，[0.4.14 的 Odoo 紀錄](release-decision-odoo-0.4.14.md)）。這是預期，
  不是結果；狀態：**待做（第 3 步）**。

## 緊急發版範本（關閉版）照本版核對（HM-18；仍要負責人預先核准）

[更新、備份與回復](update-backup-rollback.md)「緊急發版範本（關閉版）」逐點對本版：

1. 分支：從 `claude-delivery` 開 `release/<名稱>`。本版用的就是這種分支（`release/odoo-0.5.0-20261119`），合格。Odoo 關閉版的版號要大於 0.5.0（例如 0.5.1）。
2. 改的檔：
   - `features.py`：本版只在 `MULTI_PROFILE_PRODUCTS` 加 `odoo`，關閉版拿掉它（或 revert 出事的那一片），合格。
   - 釘住開通集合的測試：範本寫的 `test_multi_profile_is_switched_off_for_every_product` 在本版改成 `test_a_product_is_switched_on_only_by_its_release`
     （照 HM-23 審查 S-2 的做法：精確釘 `SWITCHED_ON`，另加「能有帳號、版號至少 0.5.0」的第二道），`SWITCHED_ON` 要和 `features.py` 一起改回（範本已照改）。本版為開通改的其他測試都改成自己指定模式（`switched_off`，或在子程序前置碼
     明說開關），開關關了照樣測同一件事，**關閉版不用改回**；逐檔清單在 [HM-19a 筆記](../provenance/ha-multiprofile-HM-19a-20261119.md)第 4 節。
   - 版號資料 7 處：和本版改的同一組（`VERSION_OVERRIDES` 裡 Odoo 改成關閉版的版號），合格。
   - CHANGELOG、根目錄 CHANGELOG、`upgrade-notes.yaml`（比對要求時）、`release-decision-odoo-<版號>.md`：合格。`addons/odoo/upgrade-check/` 的 hook 與版本無關，
     關閉版不用改（關閉版第一次開機不建索引，verify 的「索引照舊」照樣過）。
3. PR 標題、兩個預檢、`checks` 綠：合格。
4. 批准點：和本版第 3、7～11 步相同（觸發 → candidate（含 J1900）→ 負責人核准 publish → HAOS 驗收 → 證據 commit → 合併 → Release 與商店同步）。
   本版發現要補一點：三路版號運算式由本版第一次帶進 workflow；本版的 candidate 通過之後，關閉版的同形運算式就不用再另外驗。
5. 時間：candidate 約 35～40 分鐘，加建置與檢查、PR `checks` 約 30～40 分鐘、等批准與 HAOS、商店同步；推估一個工作天以上。合格。

結論：範本照本版改了一處（釘選測試的名稱），其餘照用。**範本還沒經負責人預先核准**（計畫 §7.4 要「預先核准」，出事時只填版號）：交負責人。

## HM-19b 的驗收（計畫 §10.6；推 GHCR、從商店安裝或升級之後才做）

1. 單帳號升級：0.4.14 → 0.5.0，預設帳號的權杖、兩條網址、`state.json` 位元、`tools/list`、政策 0 差異（Store `verify`＋HAOS）。先單帳號，再多帳號。
2. 同一個 Odoo 資料庫預設＋5 個受限使用者：N×N 只有對角線（管理員那一列照 Odoo 的規則看得到全部，預驗已見）；跨帳號寫入全擋；A 的寫入審批 token
   在 B 被拒；換使用者就換 token、兩條舊網址都失效。
3. 31 種網址變形、標頭與 cookie 冒用、兩個交叉案例：0 次跨帳號；錯 token 404／401。
4. 負載中輪替、撤銷、刪除只影響該帳號；刪除後 port 釋放、目錄清除；重建拿新 id 與新 token。
5. 第 6 個額外帳號 409；J6412（可以的話 J1900）上 1～6 個帳號的 RSS／PSS、CPU、冷啟動到全部就緒（錯開啟動）、第一次 initialize、停機 <30 秒；
   七支 add-on 同時開的整機 MemAvailable；全域最壞值不超過「MemAvailable－保留量」（和 HM-19c 一起）。
6. 還原演練：建 N 帳號 → 冷備份 → 撤銷 B、輪替 C、刪 D、建 E → 局部還原 → 照 DQ-03（D 回來也是撤銷、E 消失、核對卡出現、舊收據 410）；
   記下兩個訊號各自有沒有觸發；完整還原、加密備份各一次。版本混搭：0.4.14 的備份還原後再升級（預期不撤銷，面板與文件提示「全部撤銷」）；
   0.5.0 的備份還原到之後的版本（沒有之後的版本就同版本）。
7. 升級 → 回退（還原升級前備份）→ 再升級：照計畫 §7.4 (a) 的期望值；再升級後按「全部撤銷」並確認。
8. 公開網址：兩個帳號經使用者的代理或 tunnel 各自可連；真 Claude.ai 兩個帳號同時用；代理 log 遮掉 `/private_`；記下 Claude.ai 送的 Origin（S14）。
9. A 撐滿准入、位元組額度、轉送名額，或並行 16 個大回覆時，B、C 照常、健康不逾時；預設帳號撐滿時額外帳號照常；慢讀用戶端下管理程序 RSS 不超過預算。
10. Odoo 來源 IP 冷卻：一個錯密碼帳號連打 5 次，看同庫其他帳號是否被擋；add-on log 與診斷 0 token、0 帳號名稱；合成憑證掃描 0 命中、清理證明。
11. Store 同步後從 Store 安裝或升級再驗一次；記 Supervisor 版本；重跑 UC-08、UC-10、sentinel 穩定性。

另外（計畫 §12.3 HM-19b 的 2026-11-17 註、HM-18 交辦）：HA 前端 iframe 實機看換身分換權杖的提示、網址換伺服器時秘密必填、422 的文案，確認 Ingress
原樣轉送 422 與 503 的本體；契約 #111（`ETag` 經 Ingress）、#89（IPv6 試綁）在正式映像上確認後改理由欄；T-11、T-12、T-20 的回退演練、T-24
（Origin，S14）；完整還原與主機重開（sentinel 的穩定性）。

## 發版前預驗（2026-11-19，展示機；**不是 HM-19b 的證據**）

- 第一輪：[Odoo 多帳號發版前預驗](ha-test-odoo-multiprofile-early.md)。負責人指定的展示機（HAOS 18.1、Core 2026.7.2、Supervisor 2026.11.0），
  拋棄式的本機 add-on（以已發佈的 0.4.14 映像為底、換上 `claude-delivery` `fcd0b22` 的程式，開關關與開各一份），不是本 PR 的映像、沒經過商店。
  結果：單帳號基準 18/18；開通零差異（權杖、`state.json`、兩條網址不變，只多 sentinel 兩檔）；T-02（第 6 個 409）、T-03、T-04（對角線）、
  T-05（交叉 133/133）、T-08、T-09、T-10、T-13、T-14、T-17（記憶體）、T-18、T-21（一般與加密局部還原、單帳號還原提示）都照期望。
- 第二輪（同日 08:50～11:10 台北，負責人批准；同一種拋棄式 add-on；repo 的預驗紀錄只寫了第一輪，這裡是不含主機與備份細節的摘要）：
  T-20 升級 → 回退（還原升級前備份）→ 再升級（回退後映像回到沒開通的那份、權杖＝備份當時的值、額外帳號消失、守門只有 `KEPT_NOTICE`、沒有撤銷；
  再升級後按「全部撤銷」、重發，兩種接法都通）、T-11（5 個帳號並行 30 秒，0 串號、0 錯誤）、T-12（負載中輪替一個、刪一個，只有那兩個帳號開始 401，
  其他帳號沒有錯誤）、完整還原（UC-08：兩個訊號都觸發、每個帳號撤銷、核對後重發，交叉全過）、主機重開（sentinel 不變、沒有誤判成還原）都照期望。
  展示機的 CPU 是 Intel Celeron J6412，就是 HM-19c 指定的目標硬體：第一輪的記憶體數字（6 個帳號整個容器約 422 MiB、每個子程式約 82 MiB）是在
  目標硬體上量的；HM-19c 要的其他數字（CPU、冷啟動到全部就緒、全域最壞值對 MemAvailable、J1900）仍要量。
- 仍沒做：T-24（Origin；S14 交 HM-19b）。本 PR 的程式比 `fcd0b22` 多 #109、#122～#124（只有驗收工具、測試與文件），執行期程式相同，只多開關這一行。
  上面每一項在 HM-19b 都要在正式映像、從商店安裝或升級之後重做。

## 本機檢查（一般使用者；以 GitHub CI 為準）

- 全套 pytest：6,607 過、32 失敗；29 案需要 root 或 Chromium，2 案為本機 Node 22 與 Node 26 原生模組不相容，隔離環境使用 Node 26 後相關兩個檔案 51 過；1 案 loopback 假後端綁錯位址，修正後兩種情境皆過。CI 的 root、瀏覽器與釘選環境仍須驗證。
- packaging 驗證、帳本預檢通過；packaging unittest 370 案通過（5 skip）；面板 Node 測試 118 過。秘密掃描待提交後重跑。

## 發佈前的預期

- 映像推上 GHCR 之前，`readiness` 會因 `amd64-mcp-odoo:0.5.0` 拉不到、`release-decision-odoo-0.5.0.md` 不在而失敗，`Upgrade comparison` 也會因新版映像還沒發佈
  而失敗（0.4.14 同樣）。不放寬規則。
- `Upgrade comparison` 第一次跑本 PR 的 hook（UC-19）。0.4.14 的 Release 映像先在空的 `/data` 起來（沒開通），再起 0.5.0（開通）：升級測試只看 8099 回
  HTTP < 500 與撐 60 秒；開通後面板第一個沒帶 `X-MCP-Profile` 的 bootstrap 是 400，不是 5xx。
- 升版比對要求時才建 `addons/odoo/upgrade-notes.yaml`（照報告的 `change`／`key`，或新增可修補 Critical／High 漏洞的 `id`／`package`）；接受漏洞先請負責人同意。

## 要負責人決定的事

1. HM-15（listener 身分檢查）為 R1 條件式前提：#132 已實作並經獨立安全審查，待 CI、主線整合及實際 HAOS 子程式能力驗證。
2. 第 3 步（觸發 `release.yaml`）之前：三路版號運算式要不要先用拋棄式 workflow 驗（要一個 workflow 檔與一次觸發），或接受 candidate 在推送前擋。
3. 第 4 步的 Store 升級乾跑在哪台有 Docker 的機器執行；須使用 candidate 的 `image.tar` 並在推送前完成。
4. 第 5 步 HM-19c：在哪台量（展示機就是 J6412；J1900 有沒有機器）、出貨機的記憶體規格（DQ-29）；HM-03a 量到 UC-20 是「不行」（Supervisor 一定去拉映像），
   所以候選映像不能直接側載，要用計畫寫的拋棄式開關開映像（不改版號、不推）量，或明文接受先推再量。
5. 緊急發版範本（關閉版）的預先核准（上面核對過，改了一處）。
6. 測試的產品開關工具：本 PR 加的 `tests/switch_modes.py` 和 HM-23、HM-26 收斂的那份同名、同一個意思（說明文字不同）；要不要先拆成一個只含工具的小 PR
   （待決事項第 5 點），或本 PR 先合、那兩片合併時改用這份。
7. 第 3～11 步照表逐步批准。

這份紀錄不宣稱映像、HAOS、正式後端或商店驗收；那些要在負責人批准後另外取證。
