# 0.4.14 映像發佈紀錄（草稿）

狀態：**草稿：來源候選，映像尚未建置**。這是 Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 六個商店產品的維修版；OpenDesign 只升來源版本
（商店停用），Headscale 維持自己的 0.4.18。合併升版 PR 就是發佈到 WOOW App Store：建置、推 GHCR、合併都要負責人逐步批准，
下面的驗收清單在做完並補上證據之前都是「待做」。這份共用紀錄不是 readiness 認的紀錄（見第 4 項）。

## 為什麼發這一版

- 這六支的 0.4.13 映像只認到 HA Core 2026.10.4。在 Core 2026.11.x 上管理面板拒絕每個請求（頁面顯示「這個 HA Core 版本尚未審核：<版本>」，
  API 回 403 `core_version_unreviewed`，add-on log 記一行）；MCP 端點不經這項檢查，照常服務。
- 主線的 #81（`d1cfd6c`）已為 Headscale 0.4.14 審過 Core 2026.11.0、2026.11.1（25 個契約與相鄰檔，見
  [ha-role-core-contract](../ha-role-core-contract.md)），重建發版就解開。負責人 2026-11-17 14:0x 決定安排這個維修版：先準備升版 PR、不合併；
  實機驗收由負責人或其他工作線做；builder 建置、推 GHCR、合併逐步等負責人批准。
- 2026-11-17 晚上負責人改了兩件事：
  - 20:0x：這條 HA add-on 線不用 PaaS（k3s、Gitea）的機器。建置與推 GHCR 改在本 repo 的 GitHub Actions（GitHub 託管機器；
    發版流程是 #121，2026-11-17 23:30 合併 `a5124c4`）。實機驗收改在負責人指定的展示機 woowtechshow，由本對話每步請負責人批准後做。
  - 20:2x：Core 2026.11.2（#120）併進這一版；展示機不升 Core（維持 2026.7.2），只測沒退步。
- 新版同時帶出 0.4.13 之後合併、不受多帳號開關管的所有變更，逐項寫在各產品的 CHANGELOG（來源清單
  [unreleased-changes](../multi-profile/unreleased-changes.md)，本 PR 把寫進去的項目移掉）。多帳號開關維持關閉：`MULTI_PROFILE_PRODUCTS`
  是空集合，這一版不是多帳號開通。

## 來源

- 升版 commit：`7252d9eb168afddbca11b8dfacedcb6730b33507`（基準 `claude-delivery` `40f6d10`，PR #118 的合併）。
  2026-11-17 用 merge commit 把 `claude-delivery` `4cc7bee`（#120 的合併）合進來；PR 已推，不 rebase、不 force push。
- 映像來源：觸發時本 PR 的 head（`source_sha`）。**六支都推完之前，不准再往分支推任何 commit（紀錄檔也不行）**：workflow_dispatch 永遠跑在分支 head，
  `source_sha` 又必須等於它，分支一動就不能用同一個 commit 重觸發（[release.md](release.md)「部分失敗」）。都推完之後的證據 commit 只加紀錄檔
  （發版鎖：同一時間只有一個凍結中的升版 PR，計畫 §11.5）。
  2026-11-17 查時沒有其他開著的升版 PR。
- 版號資料（[release.md](release.md)「升版時要改的版號資料」）：`VERSION` 0.4.13 → 0.4.14（`packaging/validate.py`、`packaging/inputs.json`、
  `mcp_admin_core/__init__.py`，帳本摘要同步）；`VERSION_OVERRIDES`、`PRODUCT_VERSIONS` 不動（Headscale 0.4.18）；7 個 manifest 與 Dockerfile 的
  `ARG BUILD_VERSION`；`ci.yaml` 2 處、`release.yaml` 4 處照 `validate.py` 產生的運算式（`<app> == 'headscale' && '0.4.18' || '0.4.14'`，
  和之前一樣是兩路形式，不需要先用拋棄式 workflow 驗多路運算式）。第 7 項（每個產品自己的發佈紀錄）見驗收清單第 4 項。
- OpenDesign 跟著升來源版本（負責人 2026-11-17 14:4x 確認照前例一起升）的理由：0.4.10～0.4.13 每一版都只同步來源版本（0.4.13 是 `1cbfcb9`）；它的 DOCS 寫「版本號照共用規則一起升」；
  Store registry 停用它，readiness 不檢查它；不跟著升就要加一個 `opendesign` override，運算式變成 GitHub 沒算過的三路串接。不建映像、
  不做 HAOS 驗收。
- Headscale 不在這一版：自己的版號線，0.4.18 已發。共通變更（清單第 1 節 A1～A6）等它下一版才帶出去。

## HA Core 版本（2026-11-17 查公開來源，唯讀）

- home-assistant/core 的 GitHub release 與 tag：2026.11.1 之後有 **2026.11.2**（2026-11-16T20:03:59Z 發布，tag commit
  `ff5d56b825a0fb66b03d01bc297d49e206cdaba3`）；沒有 2026.11.3，也沒有 2026.12.0 或它的預覽版。
- 25 個契約與相鄰檔的 git blob（GitHub contents API）在 2026.11.1 與 2026.11.2 逐一相同；2026.11.1 那一側和
  `docs/provenance/headscale-ha-core-2026-11-blobs.json` 的紀錄逐一相同。Supervisor 2026.11.0（2026-11-06，tag commit
  `c1c6f0a754c0656eb1af189f11009f1cfc4b3e28`）的 `supervisor/api/proxy.py` 仍是審過的 blob `cab849dc`。
- 這只是查詢，不是審查。**負責人 2026-11-17 14:4x 決定不等 2026.11.2，先發 0.4.14**：0.4.14 只認到 2026.11.1，Core 已經升到
  2026.11.2 的主機上管理面板仍會拒絕（各 CHANGELOG 第一行已寫明「之後的修正版在審過之前照樣拒絕」）。2026.11.2 照
  [ha-role-core-contract](../ha-role-core-contract.md)「Adding a release」另開一片審，在 0.4.14 合併之後才合併，跟下一版出去。
- **後來改了**：0.4.14 改走 GitHub 發版流程，本來就要多等，負責人 2026-11-17 20:2x 決定把 2026.11.2 併進 0.4.14。審查片 #120
  （`a1daf9c`＋`5431d98`，合併 `4cc7bee`）照「Adding a release」審過：25 個檔和 2026.11.1 逐位元相同，Supervisor 2026.11.0 的 proxy 不變。
  0.4.14 因此認到 2026.11.2；各 CHANGELOG 第一行、DOCS、README、guide 跟著改。之後的 2026.11.3 等仍要另審。

## 建置與推送的流程（#121，[release.md](release.md)「發版：GitHub 託管機器」）

- 每個產品觸發一次 `release.yaml`（`app`、`source_sha`＝本 PR head），在這個 `release/*` 分支上跑三段：
  - `gate`：放行條件與 `public-release` 設定檢查、validate、packaging 測試、`unit.sh`。
  - `candidate`（沒有推送權限）：建置、容器驗收（含 1a、1b）、供應鏈閘門、J1900，存下測過的 image ID。
  - `publish`：負責人在 GitHub 核准 `public-release` 才開始；核對核准紀錄與 image ID，推那一個 ID，匿名讀回。
- 核准前：**六支的 candidate 都通過**，主對話把六個 image ID、閘門與 J1900 結果整理給負責人，負責人照 release.md 的檢查清單核對後才核准。
  要改來源才修得好的失敗就全部 Reject；暫時性的（網路、API 5xx、apt／Docker Hub、artifact 服務）同一個 commit 重觸發那一支，最多一次，記在這裡。
- 任何一段失敗都要重新觸發，不能 re-run。

## 驗收清單

| # | 項目 | 誰做 | 要負責人批准 | 狀態 |
|---|---|---|---|---|
| 1 | 從凍結的 PR head 建六個 amd64 映像；`supply_chain.py candidate` → `container_acceptance.py`（`container_probe.py`）＋ 供應鏈閘門（source／history／all-layer 秘密掃描、Syft／SPDX SBOM、Grype、license）；不推 GHCR | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要**（每次觸發） | 待做 |
| 1a | 容器驗收：子程式 bearer 的直連 401（`assert_child_bearer`；n8n 驗 n8n-mcp 的同一個 child token）。第一次在真容器跑，失敗先查探針與 entrypoint，不放寬 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | 同第 1 項 | 待做 |
| 1b | 容器驗收：HM-13a 的 root 還原樹（`restored_start`：還原標記在、還原項目改回 10001、`state.json` 位元不變）。第一次在真容器跑，同上 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | 同第 1 項 | 待做 |
| 2 | J1900 指令集檢查：QEMU user-mode `-cpu Nehalem`（比 J1900 嚴格）跑六個候選映像（DQ-42，負責人 2026-11-17 定每次發版都跑；做法見 [0.1.7 發佈紀錄](release-decision-0.1.7.md)「0.1.8 待辦」最後一點） | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要**（和第 1 項同一個核准計畫） | 待做 |
| 3 | 推 GHCR（推了就燒版號）：只推測過的同一個 image ID，匿名以不可變 digest 讀回 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要** | 待做 |
| 4 | 每個產品自己的發佈紀錄 `release-decision-<產品>-0.4.14.md` × 6（寫 `woow_mcp_<產品>` 與 0.4.14、映像 digest、第 1～3 項的結果）＋ provenance JSON；readiness 只認這六份，本檔不算（HM-17） | 代理 | 否（證據 commit 只加紀錄檔） | 待做 |
| 5 | CI 在 PR head 全綠：`checks`、`readiness`（六個映像可匿名拉取＋第 4 項）、`Upgrade comparison / compare`（設定比對、0.4.13 → 0.4.14 升級測試、漏洞比對）、`Release train` | CI | 否 | 待做 |
| 6 | 升版比對要求時才建 `addons/<產品>/upgrade-notes.yaml`（照報告的 `change`／`key`，或新增可修補 Critical／High 漏洞的 `id`／`package`） | 代理 | 接受漏洞要負責人同意 | 待做（比對跑出來才知道） |
| 7 | 每個產品的 HAOS P9 回歸（[ha-p9-kit](ha-p9-kit.md)）；Hermes 另看 `enabled=false` 建出的排程是停用的。展示機不升 Core（負責人 2026-11-17 20:2x），所以只驗 Core 2026.7.2 上沒退步；Core 2026.11.x 上面板能開（這一版的目的）靠 CI 與單元測試，不在實機驗 | 本對話在負責人指定的展示機 woowtechshow 做，每步負責人批准 | **要**（主機） | 待做 |
| 8 | HM-31 的「HM-19c 放行條件」（[契約](../multi-profile/contract.md)第 5 節）對這一版適不適用：HM-31 不受開關管，這一版就會帶出去 | 負責人 2026-11-17 14:4x 決定：**不擋這次維修版**（和 0.4.13 比只多了限制、沒有更寬；上界還沒在出貨機驗證，記在這裡）；這個條件仍擋多帳號開通（HM-19a） | 已定 | 已定（不擋） |
| 9 | 合併（＝上架 WOOW App Store），merge commit | 負責人本人 | **要** | 待做 |
| 10 | 合併 commit 上 `woow-addon-release.yml` 與 `release-train.yml` 的非 PR run 成功；六個 `<slug>-v0.4.14` 正式 Release；Store 同步後從商店升級再驗一次 | 代理（負責人決定何時）／負責人或其他工作線 | **要** | 待做 |

## 發佈前的預期

- 映像推上 GHCR 之前，`readiness` 會因六個映像拉不到、六份產品紀錄不在而失敗，`Upgrade comparison` 也會因新版映像還沒發佈而失敗
  （0.4.13 同樣）。不放寬規則。
- `upgrade-notes.yaml`：照 `AGENTS.md` 第 3 點，只在升版比對要求時建。比對要等映像推上 GHCR 才跑得出來，所以現在不建；`config.yaml` 只改了
  `version`。比對結果出來，要求宣告就補，接受漏洞先請負責人同意。

## 映像（待補）

| 產品 | 不可變參考 |
| --- | --- |
| odoo | 待補 |
| n8n | 待補 |
| hermes | 待補 |
| emqx | 待補 |
| litellm | 待補 |
| nextcloud | 待補 |

這份紀錄不宣稱 HAOS、正式後端或商店驗收；那些要在正常的受保護合併之後另外取證。
