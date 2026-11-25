# LiteLLM 0.5.0（多帳號 train A）發佈紀錄

狀態：**映像已發佈到 GHCR 並通過展示機驗收（2026-11-24），待合併上架**。這是 `woow_mcp_litellm` 一個產品的發版：LiteLLM 開通多帳號、版號 0.4.14 → 0.5.0，與火車 A 的另外兩個產品同一批（LiteLLM、Nextcloud、EMQX；一個升版 PR #136、各產品各自的 `release.yaml` run）。
Hermes、Headscale、n8n 的開關與版號都不動，OpenDesign 不跟著升來源版本；Odoo 0.5.1 是先一步、獨立的發版（[Odoo 0.5.1 發佈紀錄](release-decision-odoo-0.5.1.md)，2026-11-24 已上架）。
合併 PR #136 即上架 WOOW App Store；合併前只補這份紀錄與驗收紀錄（只改 `docs/`）。

## 範圍

- **只有 LiteLLM**（`woow_mcp_litellm`）：`features.MULTI_PROFILE_PRODUCTS` 加 `litellm`（與 `odoo`、其他兩個火車 A 產品一起），`addons/litellm/`、`apps/litellm/Dockerfile` 的版號 0.5.0。功能依據：#125／#133 的 LiteLLM 部分（HM-21，整合於 PR #134）。
- 不在範圍：Hermes（#128）、Headscale（#130）、n8n（#129）的開關與版號（第二批，各自另有缺口，見 `docs/multi-profile/`）；OpenDesign 與 Odoo Manage 不開放多帳號（DQ-28）。共用預設版號 `VERSION` 維持 0.4.14，0.5.0 是 LiteLLM 自己的版號線（DQ-32），和 Odoo 0.5.1、Headscale 0.4.19 一樣寫在 `VERSION_OVERRIDES`。
- 路線：這條線只用 GitHub（`.github/workflows/release.yaml`：gate → candidate → publish，publish 在 `public-release` environment 核准，只收 `release/*` 分支）。

## 來源

- 分支 `release/train-a-0.5.0-clean-20261123`（PR #136，base `claude-delivery`）：乾淨重建的火車 A（Nextcloud #126、LiteLLM／EMQX #133 與整合審查 F-1～F-4 修正）
  先併入 Odoo 0.5.0 的發版頭 `1e9adfb`（`26fbaa2`），Odoo 改發 0.5.1 之後再以 merge commit 併入 Odoo 0.5.1 的發版頭 `403e4c8`（`bd772e6`，PR #137）；
  之後只加兩個容器探針修正（`33a5989` 開通產品的停機判定給兩次檢查的時間、`84483b7` 對應埠時略過還沒 exec 的子程式；負責人 2026-11-24 同意）。
- 開關、版號與文件：`bb99908`（開關、版號資料、測試釘選與帳本）、`81b2671`（CHANGELOG、DOCS、README、upgrade notes）、`4f97b10`／`6635624`（本紀錄草稿與本機檢查）。
- Odoo 0.5.1 已於 2026-11-24 合併（`5f7ee36`）並上架；本分支與新的 `claude-delivery` 合併無衝突。映像從 PR head `84483b7` 建（發版鎖），之後的證據提交只改 `docs/`。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION_OVERRIDES` | `{'odoo': '0.5.1', 'emqx': '0.5.0', 'litellm': '0.5.0', 'nextcloud': '0.5.0', 'headscale': '0.4.19'}`（`VERSION` 維持 0.4.14） |
| 2 | `packaging/inputs.json` 的 `version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS` | 同上；帳本 `runtime-patches.json` 的摘要與雜湊同步 |
| 4 | `addons/litellm/config.yaml` 的 `version` | `0.5.0` |
| 5 | `apps/litellm/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.0` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的六路運算式（`odoo` 是 0.5.1，`emqx`、`litellm`、`nextcloud` 是 0.5.0，`headscale` 是 0.4.19，其餘 0.4.14） |
| 7 | `docs/operations/release-decision-litellm-0.5.0.md` | 本檔（推 GHCR、展示機驗收之後補證據，本次） |

- **運算式本機求值**（`packaging/test_validate.py` 的規則，`&&` 先於 `||`）：`app=odoo`→0.5.1（併入 Odoo 0.5.1 之後）、`emqx`→0.5.0、`litellm`→0.5.0、`nextcloud`→0.5.0、`headscale`→0.4.19、`n8n`／`hermes`／`opendesign`→0.4.14，`ci.yaml` 與 `release.yaml` 兩組結果相同；`packaging/validate.py` 通過。三路形式 GitHub 在 Odoo 的候選（2026-11-22，tag `local/mcp-odoo:0.5.0`）算過；六路是同一種串接多幾段，**GitHub 還沒算過**，候選建置的 tag 檢查就是驗證（算錯時 `supply_chain.py candidate` 在推送前停，不燒版號）。
- 開關：`features.py` 的 `MULTI_PROFILE_PRODUCTS` 是 `{'odoo', 'emqx', 'litellm', 'nextcloud'}`，`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON` 同步（精確釘選；EMQX 那一行見 HM-23 審查 S-2）。Hermes、Headscale、n8n 仍關。

## 驗收與批准

依負責人 2026-11-23「整套一次授權」：每個產品過完所有關卡（CI、審查、驗收）才發佈；GitHub 的發佈核准以 API 代按，改版號 PR 也代為合併，每一步回報。
容量與極端壓力只記錄、不擋發版；不做完整備份還原與主機重開（同一天的決定）。

| # | 步驟 | 結果 |
|---|---|---|
| 1 | 推送分支、開 PR | PR #136（`release/train-a-0.5.0-clean-20261123`，頭 `84483b7`，以 Odoo 0.5.1 的發版頭為底；取代舊的火車 A 分支） |
| 2 | 審查 | 整合分支審查 F-1～F-4 已修（PR #134）；兩個容器探針修正負責人 2026-11-24 同意（「單純放寬等待時間」、「照建議修探測」） |
| 3 | 候選建置與容器驗收 | `release.yaml` run 45299044628（`app=litellm`、source `84483b7`）：gate（2026-11-24 00:40:22–01:22:45Z）、candidate（01:22:48–01:27:20Z）成功；`image.tar` sha256 `42b59e4bdd09c705eb89955a14bdd37130b546a4f17c41a87e227dd64144c8b4`、226,699,776 位元組；映像 ID 由 tar 內 config 自行算出，與 handoff 一致 |
| 4 | Store 升級乾跑（展示機，0.4.14 → 候選 `image.tar`） | PASS（2026-11-24 12:46–13:01 台北，三個產品依序）：兩個 phase 都 60 秒不退出、不重啟 |
| 5 | 推 GHCR | 以 API 核准 `public-release`，publish 成功（2026-11-24 05:33:55–05:34:54Z）：manifest `sha256:7487f1dd30950a66140beb13e68953d00118a184b50e4e8b0147f7503a93b4a6`、映像 ID `sha256:4c391c21ebd2af65e9f8d3f6187fd2b9f78307e016db229028512df03a6a4219` |
| 6 | PR 檢查 | 映像發佈後重跑 readiness 與 Upgrade comparison：checks、readiness、Upgrade comparison（compare、runtime）、Release train 全部 success |
| 7 | 展示機 HAOS 驗收 | PASS（2026-11-24 15:43–16:43 台北，J6412、Core 2026.7.2、OS 18.1、Supervisor 2026.11.0）；細節、偏離與已知限制見 [ha-test-litellm-0.5.0](ha-test-litellm-0.5.0.md) |
| 8 | 容量 | 只記錄、不擋發版；驗收時記了 T-17（閘道、子程式、容器記憶體與停機秒數，見驗收紀錄）；縮減容量跑沒有跑 |
| 9 | 合併上架 | 三個產品（LiteLLM、Nextcloud、EMQX）都驗收通過；本證據提交之後合併 #136 |

## 展示機真後端驗收

做完了，結果在 [ha-test-litellm-0.5.0](ha-test-litellm-0.5.0.md)：測的是發佈到 GHCR 的映像（由 Supervisor 自己拉），升級起點是 Store 上的 0.4.14（映像 ID `e9e31155baa5`）；
每個改狀態的步驟前有加密的局部備份、守門通過才動；測完刪除測試 add-on、測試憑證、HA 測試管理員與這一輪的備份，只留後端的加密保護備份給負責人決定。

## 發版前的關卡（草稿時列的阻擋事項，現況）

1. **Odoo HM-19c**：負責人 2026-11-23 決定 HM-19c 極端壓力只記錄、不擋發版；Odoo 0.5.1 已上架（#137，2026-11-24）。
2. **Odoo 先合併**：Odoo 改發 0.5.1（#137 取代 #131／#135）；本分支以 Odoo 0.5.1 的發版頭 `403e4c8` 為底（`bd772e6`），候選全部在 `84483b7` 上重建；#137 合併後與新 `claude-delivery`（`5f7ee36`）合併無衝突。
3. **容量（未量測）**：只記錄、不擋發版；展示機驗收記了 T-17（閘道 61 MiB、子程式 102 MiB、容器 129 MiB、停機 2 秒）。發版前要量的 FD／TLS／慢速 DNS 飽和沒有量（縮減容量跑沒有跑），列為已知限制。
4. **整合審查殘留 F-6**：併入上一項。真映像冒煙由候選的容器驗收與展示機驗收完成。
5. **LiteLLM 的工具權限變更**（三個主動工具要 `create`、唯讀 18 → 15）：已寫進 CHANGELOG 與 `upgrade-notes.yaml`，Upgrade comparison success。
6. **CI 與候選首次真跑**：CI 綠。候選容器驗收的多帳號階段第一次真跑時，探針的停機判定太短、對應埠時撞到還沒 exec 的子程式；兩個探針修正（不改產品）後通過。
7. **J1900 指令集檢查**：candidate job 內建（QEMU `-cpu Nehalem`），candidate 成功。
8. **HA Core**：`ha_role.py` 只認到 Core 2026.11.2；展示機 Core 2026.7.2 沒問題，列已知限制。

## 本機檢查（一般使用者；以 GitHub CI 為準）

- 2026-11-23，分支 head 推送前，一般使用者、Python 3.13、`/tmp/ha-mp-*` 短 TMPDIR（用完刪除）：`scripts/secret_precheck.py` 0 命中、`scripts/ledger_precheck.py` OK（0 漂移）、`packaging/validate.py` 通過；`packaging` unittest 371 案過（5 skip）；面板 Node 測試 119 過、建置與 closure 檢查過；全套 pytest 分兩輪（第一輪中途短 TMPDIR 被外部清掉，之後的案例重跑）加受影響檔案的最後一輪：沒有開關相關的失敗，唯一因為開通而紅的案例（LiteLLM 真子程式的錯誤本體測試讀到開著的開關）已改成自己指定 `switched_off`。
- 本機沒跑到或不能算的案例（以 CI 為準，root、CPython 3.12.3、Node 26、Chromium、0 skip）：需要 root 的（`test_restore_detection` 的 root 案例、`test_owned_executable`、`test_profile_store` 的 uid 10001 案例）；需要 Chromium 與 playwright 的（`test_owned_browser*`、`test_owned_ui`）；n8n 的 better-sqlite3 原生模組在本機 Node 22 回退成 sql.js 的兩個案例（`test_boundary`、`test_n8n_catalog_copy`，CI 用 Node 26）；`test_request_structure` 的 CPU 比較案例（Odoo 發版頭的測試，本機負載高時 guard 比 decode 慢，兩次都 0.0354 對 0.0318 秒）。這些不宣稱 CI 綠。

## 已知限制（不擋這一版，細節見 [ha-test-litellm-0.5.0](ha-test-litellm-0.5.0.md)）

- **經 Cloudflare 開 HA 時，面板不能儲存「瀏覽器來源檢查」設定**（F2，與 Odoo 0.5.1 同一份面板）：Cloudflare 壓縮把 ETag 改成弱 ETag，面板只接受強 ETag。只影響這一張卡片，預設值照常運作；從區網開 HA 可以儲存。下一版三個產品與 Odoo 一起修。負責人 2026-11-24 決定先發。
- 後續（2026-11-25）：F2 在維修版修好了：面板也把 Cloudflare 這類代理改成的弱 ETag（`W/"…"`）當成同一個版本，送出時照舊送強的 `If-Match`，add-on 的比對沒有放寬；帳號清單的 ETag 用同一個讀法，一起修；但在 Cloudflare 上量到不受影響（2026-11-25 在真的 HA 加 Cloudflare 上量，瀏覽器的 `Accept-Encoding: gzip, deflate, br, zstd`）：`api/origin-policy`（94 位元組）被 Cloudflare 壓成 br、ETag 變弱，所以卡片不能存；`api/profiles`（161 位元組）由 Home Assistant 自己先壓 gzip、ETag 維持強；只有前面的代理改寫 HA 沒壓縮的回應時才可能變弱，例如用戶端不收壓縮（`docs/multi-profile/unreleased-changes.md` A11）。上面寫的是這一版映像的行為，沒有改。
- 容量：每帳號最多 50 條後端連線、四個帳號 200 條的 FD／記憶體／TLS 飽和沒有在 J6412 量（縮減容量跑只記錄、這一版沒有跑）。
- HA Core：`ha_role.py` 只認到 Core 2026.11.2；目標 HAOS 比 2026.11.2 新時要先補審。
