# 0.4.14（與 Headscale 0.4.19）映像發佈紀錄（草稿）

狀態：**映像已發佈並驗證（2026-11-18）；展示機單帳號回歸已做（[ha-test-0.4.14](ha-test-0.4.14.md)），合併待負責人**。這是 Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 六個商店產品的維修版；OpenDesign 只升來源版本
（商店停用）。**Headscale 自己的版號線同一個 PR 升到 0.4.19**（負責人 2026-11-18 的決定，見下）。合併升版 PR 就是發佈到 WOOW App Store：建置、推 GHCR、合併都要負責人逐步批准，
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
- Headscale 原本不在這一版（自己的版號線，0.4.18 已發）。**2026-11-18 改成同一個 PR 發 0.4.19**：0.4.18 只認到 Core 2026.11.1，在 2026.11.2 上管理面板也會被鎖，而且還沒帶 0.4.18 之後的共用改動 A1～A7。負責人 04:5x 選「六支照跑，同時準備 0.4.19」，並先同意「六支結果要改程式才修得好，就把 Headscale 一起放進去、七支重跑」；第一次建置正是這種情況（見下一節）。Headscale 的升版 commit（版號資料只動 Headscale 的 override、manifest、Dockerfile、ci 2 處、release 4 處；CHANGELOG 寫 A1～A7）在本 PR，運算式變成 `<app> == 'headscale' && '0.4.19' || '0.4.14'`。

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

## 第一次建置（2026-11-18，`93f31a4`，放棄）

- 負責人 04:4x 批准觸發；20:42Z 觸發六支（odoo 44172025080、n8n 44172030303、hermes 44172036656、emqx 44172042788、litellm 44172047498、nextcloud 44172052735）。
- 結果：odoo、n8n、hermes 的 gate 與 candidate 都通過（含容器驗收 1a／1b、J1900），publish 停在等待核准；emqx、litellm、nextcloud 的 candidate 在供應鏈閘門失敗。
- 原因（本機用同一版 syft 1.54.0、grype 0.120.0 與 `supply-chain-policy.json` 重現於已發佈的 0.4.13 映像）：子程式環境的 dnspython 2.9.0 有 GHSA-vvf4-9x63-8xvv（CVE-2026-128089，High，2.9.2 修補；zone 檔 WKS 紀錄的服務編號沒檢查範圍，可耗盡記憶體與 CPU），政策對「有修補版的 High」一律擋。odoo 對照組沒有這個命中。0.4.13 發佈之後才公布（11/04 發布、11/13 進 GitHub 資料庫），已發佈的 0.4.13（以及 Headscale 0.4.18）都帶著 2.9.0。
- 修法（要改來源，照規則全部重來）：emqx、litellm、nextcloud、headscale 的 `uv.lock` 只把 dnspython 升到 2.9.2（`uv lock --upgrade-package dnspython==2.9.2`，wheel sha256 `af15f7d3…`，2026-11-03 上傳）；`tests/test_output_schemas.py` 補這四個 `uv.lock` 的新位元組釘選（不影響執行期的輸出 schema）；四份 CHANGELOG 與根目錄各加一行。
- 確認不會帶進新問題：用同一版 gitleaks 8.28.0 和 repo 的設定掃 2.9.0 與 2.9.2 的 wheel，兩者都是同樣 6 處命中（`dns/dnssecalgs/mldsa.py`、`eddsa.py`），雜湊都在 `secret-triage.json` 已核准的清單；授權一樣是 ISC。
- 舊的三個等待中的 publish 不核准，新 head 推上去之前先取消或 Reject；之後七支（加 Headscale 0.4.19）用新 head 重新觸發。

## 第二次建置（2026-11-18，`b24a2d7`，放棄）

- head `b24a2d7`（`5a7c191` Headscale 0.4.19、`b24a2d7` dnspython 2.9.2）；21:46:59Z～21:47:09Z 觸發七支（odoo 44183380073、n8n 44183384363、
  hermes 44183389190、emqx 44183394315、litellm 44183399366、nextcloud 44183403936、headscale 44183408135）。
- 結果：七支的供應鏈閘門都過（dnspython 修正有效）。odoo、n8n、hermes 全過、publish 等待核准；emqx、litellm、nextcloud、headscale 的 J1900 失敗：
  `<產品>-child: modules differ under -cpu Nehalem: caio.linux_aio`。
- 原因（讀原始碼判定）：caio 0.12.10 的 `caio/linux_aio.c` 在 import 時呼叫 `io_setup`，失敗就丟 `ImportError: Error on io_setup with code <errno>`；
  QEMU 8.2.2 linux-user 沒實作 AIO 系統呼叫（`linux-user/syscall.c` 預設回 ENOSYS 38），原生 Docker 可以。是模擬器缺系統呼叫，不是指令集問題，
  沒有 SIGILL。caio 由 aiofile 帶進來，只有這四支有。
- 負責人 06:5x 選「修檢查、七支重跑」。修正 `66b393b`、`24de6ec`（兩輪獨立審查）：
  - `packaging/j1900-allowlist.json` 加只在 QEMU 下才算的條目：只限 `caio.linux_aio`，原生必須成功，QEMU 錯誤必須恰好是
    `ImportError: Error on io_setup with code 38`。
  - 審查另外找到 `caio.linux_uring` 在 Docker 預設 seccomp 下原生 import 就失敗（io_uring 被擋，EPERM），之前被 QEMU 差異蓋掉：加原生條目，
    文字恰好是 `ImportError: io_uring_setup probe failed: Operation not permitted`。
  - 檢查改成一次報完原生不許可與 QEMU 差異，並驗模組名稱；SIGILL 檢查不變。審查從已發佈的 0.4.13／0.4.18 映像分析四支 child venv 的
    10 個原生模組，只有 caio 這兩個會失敗。
- 三個等待中的 publish 不核准，取消；七個執行都結束，GHCR 七個新版 tag 匿名查都是 404（版號沒燒）。

## 第三次建置（2026-11-18，`24de6ec`，發佈）

- 00:56Z（台北 08:56）用 head `24de6ec` 觸發七支，都是 attempt 1：odoo 44211876006、n8n 44211880072、hermes 44211883565、emqx 44211887012、
  litellm 44211890753、nextcloud 44211894426、headscale 44211897773。
- 台北 09:37 前七支的 gate、candidate 全過（容器驗收含 1a／1b、供應鏈閘門、J1900）。J1900 的放行訊息和預測一致：七支的 `_tkinter` 原生
  （`libtk8.6.so` 不在映像裡）；emqx、litellm、nextcloud、headscale 的 child 另有 `caio.linux_uring` 原生、`caio.linux_aio` 只在 QEMU。
  環境：`qemu-x86_64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`、Docker 28.0.4（classic overlay2）、grype DB built 2026-11-17T06:20:58Z。
- 核准：負責人約 09:4x（台北）看過七個 image ID、閘門與 J1900 結果和核准前檢查清單後，授權本對話代為核准這七個 publish（原話「准許你去幫我處理我切手動了」），
  只限這七個執行；這次改了 2026-11-17 22:0x「核准一律由負責人在 GitHub 按」的做法。01:58Z 本對話用負責人帳號（User 165237880）的權杖經 API 核准
  `public-release`；工具只准這七個 run（`24de6ec`、attempt 1、正在等待），內容只准 `{environment_ids: [27603699551], state: approved, comment}`。
- 台北 10:00 七支 publish 全部成功。匿名核對 GHCR：七個 manifest 都在，config digest＝測過的 image ID；另逐層下載核對 122 層（約 620 MiB），
  壓縮 digest、大小與 diffID 都相符。各產品的細節在七份產品紀錄，證據 commit `0627c7f` 只加紀錄與狀態行。

## 合併前的 CI（PR head）

- `checks`：`0627c7f` 上 `test_release_gate` 的舊假設失敗（以為沒有別的產品有 0.4.14 紀錄），`b3781da` 改成每份 Headscale 紀錄單獨檢查，
  另驗每份產品紀錄只放行自己的產品；`b3781da` 上一次 `test_unconfigured_connect[litellm]` 隨機埠撞號，重跑後綠。
- `readiness`、`Upgrade comparison / runtime`（升級測試）、`Release train`：綠。
- `Upgrade comparison / compare`：`0627c7f` 一次、`b3781da` 三次（含兩次重跑）都在「SBOMs of the comparison targets' images」失敗。商店
  `woow-addon-upgrade-check.yml` 在 ubuntu-latest（26.04、Docker 29.4.2）用 `syft scan docker:ghcr.io/woowtech/amd64-mcp-n8n:0.4.14`，Syft 在 Docker
  匯出的 tar 裡找不到 config blob（`file blobs/sha256/5afcfda1… not found in tar`）。映像本身沒問題：GHCR 逐層核對過，runtime job 拉起來正常，
  發版時 Docker 28 存下的 archive 讀得到，同一台機器讀 0.4.13 n8n 也正常。
- 修正在商店：WOOWTECH/Woow_HA_App_Store#124（MattLinP 核准，台北 14:15 合併，`ca19c7d`）把已發佈映像的 SBOM 改成
  `syft scan registry:<image> --platform linux/amd64`，直接從 GHCR 讀；在 runner 上重建的映像照舊從 Docker 讀。
- 重跑舊執行沒用：44224368229 第 3 次（台北 14:16）仍用該執行原本解析的商店流程 `1369a33`（log：`Uses:
  …/woow-addon-upgrade-check.yml@refs/heads/main (1369a33…)`），一樣失敗。compare 要用 `ca19c7d` 就要有新 commit 觸發的新執行。

## 驗收清單

| # | 項目 | 誰做 | 要負責人批准 | 狀態 |
|---|---|---|---|---|
| 1 | 從凍結的 PR head 建六個 amd64 映像；`supply_chain.py candidate` → `container_acceptance.py`（`container_probe.py`）＋ 供應鏈閘門（source／history／all-layer 秘密掃描、Syft／SPDX SBOM、Grype、license）；不推 GHCR | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要**（每次觸發） | 完成（第三次建置，七支；結果見各產品紀錄） |
| 1a | 容器驗收：子程式 bearer 的直連 401（`assert_child_bearer`；n8n 驗 n8n-mcp 的同一個 child token）。第一次在真容器跑，失敗先查探針與 entrypoint，不放寬 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | 同第 1 項 | 完成（第三次建置） |
| 1b | 容器驗收：HM-13a 的 root 還原樹（`restored_start`：還原標記在、還原項目改回 10001、`state.json` 位元不變）。第一次在真容器跑，同上 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | 同第 1 項 | 完成（第三次建置） |
| 2 | J1900 指令集檢查：QEMU user-mode `-cpu Nehalem`（比 J1900 嚴格）跑六個候選映像（DQ-42，負責人 2026-11-17 定每次發版都跑；做法見 [0.1.7 發佈紀錄](release-decision-0.1.7.md)「0.1.8 待辦」最後一點） | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要**（和第 1 項同一個核准計畫） | 完成（第三次建置；允許清單在第二次建置後修正） |
| 3 | 推 GHCR（推了就燒版號）：只推測過的同一個 image ID，匿名以不可變 digest 讀回 | GitHub 託管機器跑 `release.yaml`（#121；本對話在負責人批准後逐產品觸發，負責人在 GitHub 核准 `public-release`） | **要** | 完成（台北 10:00；負責人授權代為核准，見「第三次建置」；匿名逐層核對） |
| 4 | 每個產品自己的發佈紀錄 `release-decision-<產品>-0.4.14.md` × 6 ＋ `release-decision-headscale-0.4.19.md`（寫 `woow_mcp_<產品>` 與版號、映像 digest、第 1～3 項的結果）＋ provenance JSON；readiness 只認這七份，本檔不算（HM-17） | 代理 | 否（證據 commit 只加紀錄檔） | 完成（`0627c7f`；測試修正 `b3781da`） |
| 5 | CI 在 PR head 全綠：`checks`、`readiness`（六個映像可匿名拉取＋第 4 項）、`Upgrade comparison / compare`（設定比對、0.4.13 → 0.4.14 升級測試、漏洞比對）、`Release train` | CI | 否 | 完成（`370bed0`：`checks`、`readiness`、`compare`、升級測試、`Release train` 全綠；之後只加紀錄的 commit 照樣要再綠） |
| 6 | 升版比對要求時才建 `addons/<產品>/upgrade-notes.yaml`（照報告的 `change`／`key`，或新增可修補 Critical／High 漏洞的 `id`／`package`） | 代理 | 接受漏洞要負責人同意 | 不需要（compare 七支都 Passed：沒有破壞性設定變更、沒有新的可修補漏洞；emqx、litellm、nextcloud、headscale 各少 1 個，就是 dnspython） |
| 7 | 每個產品的 HAOS P9 回歸（[ha-p9-kit](ha-p9-kit.md)）；Hermes 另看 `enabled=false` 建出的排程是停用的。展示機不升 Core（負責人 2026-11-17 20:2x），所以只驗 Core 2026.7.2 上沒退步；Core 2026.11.x 上面板能開（這一版的目的）靠 CI 與單元測試，不在實機驗 | 本對話在負責人指定的展示機 woowtechshow 做，每步負責人批准 | **要**（主機） | 完成（2026-11-18，[ha-test-0.4.14](ha-test-0.4.14.md)；沒有退步；Hermes 暫停排程實測通過；Odoo、EMQX 沒有後端實測） |
| 8 | HM-31 的「HM-19c 放行條件」（[契約](../multi-profile/contract.md)第 5 節）對這一版適不適用：HM-31 不受開關管，這一版就會帶出去 | 負責人 2026-11-17 14:4x 決定：**不擋這次維修版**（和 0.4.13 比只多了限制、沒有更寬；上界還沒在出貨機驗證，記在這裡）；這個條件仍擋多帳號開通（HM-19a） | 已定 | 已定（不擋） |
| 9 | 合併（＝上架 WOOW App Store），merge commit | 負責人本人 | **要** | 待做 |
| 10 | 合併 commit 上 `woow-addon-release.yml` 與 `release-train.yml` 的非 PR run 成功；六個 `<slug>-v0.4.14` 正式 Release；Store 同步後從商店升級再驗一次 | 代理（負責人決定何時）／負責人或其他工作線 | **要** | 待做 |

## 發佈前的預期

- 映像推上 GHCR 之前，`readiness` 會因六個映像拉不到、六份產品紀錄不在而失敗，`Upgrade comparison` 也會因新版映像還沒發佈而失敗
  （0.4.13 同樣）。不放寬規則。
- `upgrade-notes.yaml`：照 `AGENTS.md` 第 3 點，只在升版比對要求時建。比對要等映像推上 GHCR 才跑得出來，所以現在不建；`config.yaml` 只改了
  `version`。比對結果出來，要求宣告就補，接受漏洞先請負責人同意。

## 映像（2026-11-18 推送；匿名逐層驗證通過）

| 產品 | 不可變參考 |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo:0.4.14@sha256:5a672d7b654d554aeabd70d559a09f740a79d27152fb64cda22207f230c3b588`（image ID `sha256:d6b4d85c21195383dd94a74b9c33e9491f70a100e5c96ac5d2c19f63dd018880`；run 44211876006） |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n:0.4.14@sha256:e30438e2684d377200e0aea8313b19e532070899ef9b9599f011b11cca851d94`（image ID `sha256:5afcfda1f5ddf7d4f1c2f4678f2a59d52ae7f9818f577a116e5908c6430c3936`；run 44211880072） |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes:0.4.14@sha256:83d5d702c9de5d464da67b55ce1422ac78c63d33e5620b60ef46a3667cb8026b`（image ID `sha256:8c52b11eb7def4c9c0d6fc332ed0093d22d29261e54d574bebf6f366a498faff`；run 44211883565） |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx:0.4.14@sha256:2f355dc7bf5b13288282a374a8302d692a18c104079e4db1b318b98864b84491`（image ID `sha256:408478b76ee01764d9982bcb6d34c3567733027754f5809cc3acd38400c72b2b`；run 44211887012） |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm:0.4.14@sha256:fb3141fba524f90a65f94c876963762e21bd24abb5cc005fd65327c488768aa4`（image ID `sha256:e9e31155baa599880a7bc9975df9b38b3440c5455d5072acf0f4cc4190ac7827`；run 44211890753） |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud:0.4.14@sha256:982af33d752ef2bf648debf1dcebb507f8a7850d643c7595735ad38be4e321ea`（image ID `sha256:1ed1a00407089c6ebb2a7d06dc1d039a84a241e1822427b3d0423c4c86401c5f`；run 44211894426） |
| headscale | `ghcr.io/woowtech/amd64-mcp-headscale:0.4.19@sha256:a05e1a35fe3a048590b34fb542a38bd9a2fa2883d5151bd5732903d7c44baed9`（image ID `sha256:5603dd22b76f39947c9300abe658935e1f02c5002796d8488712f148ea096a25`；run 44211897773） |

這份紀錄不宣稱 HAOS、正式後端或商店驗收；那些要在正常的受保護合併之後另外取證。
