# 建置、CI 與人工發佈關卡

## 固定輸入與執行狀態

目標 Supervisor **2026.09.3**（非 Core 版本），source commit
`64ea3be4322537fd5dcfbf620c4dc25490c1f56d`；validator 僅實作本專案允許的嚴格
schema 子集。參考 `supervisor/apps/validate.py` 454–557/589–606 與
`supervisor/store/validate.py` 10–17。未知 key 不准被 Supervisor 靜默丟棄。

Base image 精確 linux/amd64 manifest digest 記錄於 `packaging/inputs.json`：
Python 3.13.16 slim-bookworm、Node 26.13.1 bookworm-slim（0.4.15 起，為 26.12.1 執行檔的 7 個 High 漏洞；0.4.0 到 0.4.14 是 26.12.1，0.3.4 是 22.23.4；Node 22.23.4 起這個 pin 是 multi-arch index digest，之前的 22.23.2 是 linux/amd64 child digest）、uv 0.12.10。
Node 26 的官方執行檔另外連結 `libatomic.so.1`：node 映像本身裝有 Debian 的 libatomic1；n8n 映像把 node 複製到 Python 基底，連同這個函式庫一起複製（與 libstdc++、libgcc_s 相同做法，映像內不裝套件），複製後立刻檢查 `node --version` 等於 v26.13.1。
2026-10-03 以 Docker Hub 公開匿名 metadata 查得（Python 基底 2026-10-05 升到 3.13.16、2026-10-06 改釘 Docker Hub 重建版），不是編造 hash，也不是
映像安全掃描／license approval／成功 build。匿名 registry 短效 pull challenge
不涉及既有帳號憑證。未使用 curl|sh、NodeSource 或 runtime 未固定下載。

原 core worker 本地使用 Python3.13.2，本封裝選支援範圍內固定 patch3.13.16；
不同 patch/base/native libraries 仍須真正 image build 和 container gate 才可接受。

**開發容器本身仍無 Docker；映像改在專用一次性 builder 建置。** 2026-10-05 起映像都在專用一次性 KubeVirt builder（Docker classic store）建置，container/mock 驗收與 supply-chain gate（source／history／image secrets、SBOM、CVE、license）全數通過才推送 GHCR（0.1.0 是七類候選 `f75fe32`，證據在協作區 `claude-delivery/evidence-real-f75fe32/`；0.1.5 是六支候選 `0c66bd0`，見 [發佈紀錄](release-decision-0.1.5.md)）。建置與推送都不經 remote Actions；0.1.0–0.1.5 已發佈，
0.1.1–0.1.5 已在測試 HA 回歸（[ha-test-0.1.5](ha-test-0.1.5.md) 等）。靜態與本地 packaging tests 不能升格成 image PASS。
2026-11-17 起（負責人決定，HA add-on 線不用 PaaS 的 k3s、Gitea）改由 `.github/workflows/release.yaml` 在 GitHub 託管機器上建置、
驗收、推送，見下面「發版：GitHub 託管機器」；0.1.0–0.4.13 與 Headscale 0.4.14–0.4.18 是上述 builder VM 推的。

各支的 `homeassistant_api:true` **權限已批准**（n8n 路徑 A 2026-10-03；其他六支 0.1.1 起，負責人 2026-10-05 核准；Nextcloud 2026-10-08，0.1.7 起），不是 publication clearance。
hassio/auth API、預設 role、host 邊界不變。真實 fixed-URL／
fresh-query fail-closed verifier、child token 隔離與 UI 已整合。審查範圍分開看：本地整合（當時只有 n8n 接 provider）
2026-10-03 經有界 SPEC／安全審，只核准本地整合；0.1.1 的獨立 SPEC＋安全審只涵蓋 provider 接線與 token 傳遞兩段程式，
明確不含映像、HA 與發佈（[0.1.1 發佈紀錄](release-decision-0.1.1.md)）。
本地真 bootstrap/guard/n8n/fake WS/browser 不替代映像／HA；真 HA 的 owner／non-admin 已在 0.1.1–0.1.5 實測，
但對應的 `products.<app>.image`／`ha` gates 仍是 false。不可用此批准清除下列任何 gate。

## Root-context 獨立 builds（商店產品，見 `packaging/inputs.json`）

```sh
# 範例而非已執行紀錄；在有 Docker 的 disposable runner
APP=n8n # 僅可選 checked-in 商店產品 allowlist（packaging/inputs.json）
VERSION=0.1.5 # 須等於 packaging/inputs.json 的 version（container_acceptance 會檢查）
docker build --platform linux/amd64 --file "apps/$APP/Dockerfile" \
  --build-arg "BUILD_VERSION=$VERSION" --tag "local/mcp-$APP:$VERSION" .
python packaging/container_acceptance.py "$APP" "local/mcp-$APP:$VERSION"
```

最後 `.` 是 repo root，不是 app/addon 目錄。核心及 `apps/runtime` 必須同時存在；
每個 image 只有 selected app，child venv path 保留 `/opt/woow/apps/<app>/.venv`。
不要把 n8n 以外各支的 FastMCP deps 安裝進 core venv。n8n Node builder 執行 pinned `npm ci
--ignore-scripts`，runtime 只有 node binary/libs 與 locked node_modules（sql.js
fallback），不包含 uv/npm installer 或 dependency cache。
每個 Dockerfile 另有同一 pinned Node UI stage，使用 UI 自己的 lock；runtime 只 COPY
完整 `dist` 到 `/opt/woow/packages/mcp-admin-ui/dist`（Core 固定路徑），含 self-host fonts、
MDI、全部 licenses/NOTICE。`.dockerignore` 僅開 build inputs，不開 fixture/tests/dist/node_modules。
本地 npm build 可驗 closure；image builds 只在 builder 執行。

Manifest `image` 是**未帶 tag**的 lowercase ref，`version` 固定為 `packaging/inputs.json` 的版本（目前 0.1.5）；不使用 latest、
aarch64 或偽造 OCI license umbrella。HA 子目錄 fallback build 不支援 root context；
必須先有可匿名 pull 的已核准預建 image。`io.hass.type=app` 不是 legacy addon。

## WOOW App Store 正式 Release（自動）

WOOW App Store 只出貨本 repo 的正式 Release（Store registry `ref_policy: release`，`required_workflows` 是
`.github/workflows/woow-addon-release.yml`）。放行就是合併一個升了 add-on 版本、且通過必要檢查的 PR，沒有手動發 Release 的步驟
（母專案 ADR-0005）。`woow-addon-release.yml` 在 PR 與推送 `claude-delivery` 時執行：

- `checks`：本頁下一節 `ci.yaml` 的第 1–3 項（validator、packaging tests、`packaging/unit.sh`），不含 builder admission。
- `readiness`：`packaging/release_gate.py` 對 Store registry 啟用的每一支（`woow_mcp_opendesign` 已停用，不檢查）確認：
  - manifest 版本的 amd64 映像可以從 GHCR 匿名拉取；
  - 還沒有正式 Release（tag `<slug>-v<版本>`）的版本，有該產品自己的發佈紀錄 `docs/operations/release-decision-<產品>-<版本>.md`
    （`<產品>` 是 `addons/` 下的目錄名，例如 `release-decision-odoo-0.5.0.md`），內文寫到 `<slug>` 和這個版本。這份紀錄寫明映像由哪一次
    `release.yaml` 執行建置、驗收、推送，以及負責人 HAOS 實機驗收的結果；readiness 不會去查那次執行，所以**升版的 PR 要先推好映像、
    寫好發佈紀錄**（步驟見「發版：GitHub 託管機器」）。共用紀錄
    （`release-decision-<版本>.md`）和別的產品的紀錄都不算：各產品的版號線會重複（Headscale 用過 0.4.14～0.4.18；多帳號開通時每個產品
    各自升到 0.5.0），只比版號字串會讓別的產品的紀錄放行（HM-17）。一個 PR 同時升幾個產品，就每個產品各寫一份。
- `release`：只在推送 `claude-delivery` 且上面兩項都通過時執行，呼叫 Store 的 `woow-addon-release.yml`，替每支還沒有 Release 的版本發
  `<slug>-v<版本>` 正式 Release。已發過的版本不會重發，所以沒升版號的推送不會發 Release，catalog 也不會前進。
- `woow-addon-sync.yml` 在這個 workflow 完成後經由 `workflow_run` 執行，通知 Store；不必手動執行。

舊的整個 repo 一個 `v<版本>` tag（`v0.1.0`…`v0.2.2`）保留不動；`v0.2.2` 是改制時的種子正式 Release。
改制後第一次推送 `claude-delivery`（`17b6ebd`，run 39558332683）替 6 支啟用的 add-on 各發了 `<slug>-v0.2.2`，`woow_mcp_opendesign` 沒有發。

### 升版時要改的版號資料

版號只寫在下面這些資料裡，`packaging/validate.py` 把它們綁在一起，漏改一處就失敗（HM-17）：

1. `packaging/validate.py` 的 `VERSION_OVERRIDES`（只升某幾個產品，例如 `{'odoo': '0.5.0', 'headscale': '0.4.18'}`，寫在一行、
   和這個例子同樣的寫法：`packaging/test_validate.py` 照這個寫法找它）或 `VERSION`（預設版號線）。
2. `packaging/inputs.json` 的 `version_overrides`／`version`，和第 1 項相同。
3. `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS`／`VERSION`（`initialize` 回報的版號）。這個檔列在
   `docs/provenance/runtime-patches.json`，同一個 PR 要更新它的摘要（`scripts/ledger_precheck.py` 會查）。
4. `addons/<產品>/config.yaml` 的 `version`。
5. `apps/<產品>/Dockerfile` 的 `ARG BUILD_VERSION=<版號>` 預設值。
6. `.github/workflows/ci.yaml`（tags、build-args，共 2 處）與 `release.yaml`（tags、build-args、推送的 `IMAGE`、證據名稱，共 4 處）
   的版號運算式。改完前 5 項後跑 `python packaging/validate.py`：失敗訊息會印出由 `VERSION_OVERRIDES` 產生的運算式
   （`<app> == '<產品>' && '<版號>' || … || '<預設版號>'`），照著逐字換掉這 6 處。
7. 那個產品自己的發佈紀錄 `docs/operations/release-decision-<產品>-<版號>.md`（見上面的 `readiness`）；一個 PR 升幾個產品就寫幾份。

這兩個 workflow 在 PR 不跑：`ci.yaml` 的 `images` job 是硬鎖的 BLD2 路線；`release.yaml` 是發版時在 `release/*` 分支上手動觸發的
（下面「發版：GitHub 託管機器」），照這個運算式建置、打 tag、推送，`check_release.py` 另外要求 `version_for(產品)` 等於 manifest
版號。所以運算式由 `validate.py` 逐字比對、`packaging/test_validate.py` 照 GitHub Actions 文件的運算規則（`&&` 先於 `||`）求值；
萬一 GitHub 算出別的版號，建出的 tag 不是 `local/mcp-<產品>:<version_for>`，`supply_chain.py candidate` 在推送前就停。0.4.14 與
Headscale 0.4.19 只有 Headscale 一個 override（兩路形式，GitHub 算過）；Odoo 0.5.1 的升版 PR（HM-19a）起有 Odoo、Headscale 兩個
override，workflow 第一次帶三路串接（`<app> == 'odoo' && '0.5.1' || <app> == 'headscale' && '0.4.19' || '0.4.14'`）。多個 override
串接的寫法還沒被 GitHub 實際算過，第一次觸發 `release.yaml` 之前先用拋棄式 workflow 只印出運算式的值確認（不建置；要負責人批准，見
[0.5.1 發佈紀錄](release-decision-odoo-0.5.1.md)）。
火車 A 的 0.5.0（LiteLLM、Nextcloud、EMQX）升版起有 Odoo、EMQX、LiteLLM、Nextcloud、Headscale 五個 override，workflow 帶六路串接
（`<app> == 'odoo' && '0.5.1' || <app> == 'emqx' && '0.5.0' || <app> == 'litellm' && '0.5.0' || <app> == 'nextcloud' && '0.5.0' || <app> == 'headscale' && '0.4.19' || '0.4.14'`，
`validate.py` 產生、本機求值過：odoo 是 0.5.1，emqx、litellm、nextcloud 是 0.5.0，headscale 是 0.4.19，其餘 0.4.14）。三路形式 GitHub 在 Odoo 0.5.0 的候選（0.5.0 已建置但未上架）
（2026-11-22，tag `local/mcp-odoo:0.5.0`）算對了；六路是同一種串接寫法多幾段，還沒被 GitHub 算過，第一個火車 A 的候選建置的 tag 檢查就是驗證
（算錯時 `supply_chain.py candidate` 在推送前停）。
火車 B 的 0.5.0（Hermes、n8n、Headscale）升版起，七個商店產品各有自己的版號線：`VERSION_OVERRIDES` 有 Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud、Headscale 七個 override，workflow 帶七路串接
（`<app> == 'odoo' && '0.5.2' || <app> == 'n8n' && '0.5.0' || <app> == 'hermes' && '0.5.0' || <app> == 'emqx' && '0.5.1' || <app> == 'litellm' && '0.5.1' || <app> == 'nextcloud' && '0.5.1' || <app> == 'headscale' && '0.5.0' || '0.4.15'`，
`validate.py` 產生、本機求值過：odoo 是 0.5.2，n8n、hermes、headscale 是 0.5.0，emqx、litellm、nextcloud 是 0.5.1，其餘只有 OpenDesign 的來源版本，0.4.15）。六路形式 GitHub 在火車 A 的候選建置（2026-11-24）算對了；
七路是同一種串接寫法多一段，還沒被 GitHub 算過，第一個火車 B 的候選建置的 tag 檢查就是驗證（算錯時 `supply_chain.py candidate` 在推送前停）。預設版號 `VERSION`（0.4.15）現在只有 OpenDesign 的來源版本在用；
`validate.py` 要求它不等於任何一個 override 的版號。
本節只列版號資料；CHANGELOG、`upgrade-notes.yaml`（見 `AGENTS.md`）等其他升版要改的檔不在這裡。
寫 CHANGELOG 前先看 `docs/multi-profile/unreleased-changes.md`：上一版以來已合併、會跟著這個產品下一版出去但 CHANGELOG 還沒記的變更，
每項的 CHANGELOG 句子，以及發版時要另外驗的事（多帳號計畫 §11.5；其他工作線的修補版也一樣）。

## PR/main CI（只讀）

`.github/workflows/ci.yaml`（推送 `main` 或手動執行；PR 改由上一節的 `checks` 檢查，因為 builder admission 依設計會拒絕每個 PR）：contents read、checkout 不保留 credentials、hosted
ubuntu-24.04、有 timeout/concurrency；不讀 secrets、不 login、不 push、不用
pull_request_target、不使用 production self-hosted runner。

1. Python3.13.16／Node26.13.1（0.4.15 起；0.4.0 到 0.4.14 是 26.12.1，0.3.4 是 22.23.4，之前 22.23.2）／uv0.12.10，hash-pinned PyYAML。
2. strict packaging validator + packaging tests。
3. 既有 TCP tests 固定 subprocess PATH=/usr/bin:/bin；只在 disposable hosted runner
   將 /usr/bin/node 指向 setup-node 已安裝的確切 binary，並檢查 v26.13.1，避免
   意外測到 runner 系統舊 Node。0.4.0 起 /usr/local/bin/node 也指向它並以 `sudo -n -- node --version` 檢查：
   pytest 以 sudo 執行，sudo 的 secure PATH 先找到 runner 自帶的 /usr/local/bin/node，而 n8n 子程序從 PATH 取 node
   （映像中也是 /usr/local/bin/node），CI 的 n8n 子程序因此可能跑在 runner 自帶的 Node（0.4.0 第一次 CI 是
   22.23.3，由 `tests/test_boundary.py` 新增的子程序 Node 版本斷言發現）。不改 core；此操作未在本地工作環境執行。
   `sh packaging/unit.sh` 真正安裝 `packaging/unit.sh` 列出的每個 runtime lock（各 Python app 含封存的 Odoo Manage 原始碼與 Nextcloud，加上 n8n）、inventory drift、全 core/
   adapter tests，Junit 明確拒絕 skipped/empty/failure。
4. 固定商店產品 matrix（與 packaging/inputs.json 相同），root context amd64 `push:false load:true`。
5. 每個 build 執行 `packaging/container_acceptance.py`，network-none owned mocks，
   不以 health smoke 取代 protocol/auth/policy/lifecycle/data 驗證。

Actions 都 pin 40-char commit，不以 tag 作執行輸入。checkout/buildx/build-push/login/
upload pins 採已提供的公開查證報告；補充 setup-python v6
`ece7cb06caefa5fff74198d8649806c4678c61a1`、setup-node v4
`49933ea5288caeca8642d1e84afbd3f7d6820020`、setup-uv v7
`37802adc94f370d6bfd71619e3f0bf239e1f3b78` 由公開 GitHub tag metadata 解析；uv 為
annotated tag，已解到 commit。固定來源不等於 action code 已完成安全批准。

## 發版：GitHub 託管機器（`release.yaml`）

負責人 2026-11-17 決定：HA add-on 這條線不用 PaaS 的基礎設施（k3s 叢集、Gitea）。映像在本 repo 自己的 GitHub Actions、GitHub
託管的 ubuntu-24.04 機器上建置、驗收、推 GHCR，和 `Woow_ha_hermes_add_on`、`Woow_ha_omnigent_addon` 一樣只用每次執行才發的
`GITHUB_TOKEN`：不用 PAT、不讀其他 secret、不用 self-hosted runner。舊的 BLD2 路線見 [builder-runner](builder-runner.md)（歷史）。

### workflow 做什麼

`.github/workflows/release.yaml` 只接受手動觸發（`workflow_dispatch`），一次一個產品，分三個 job，全部在 GitHub 託管的
ubuntu-24.04 上跑。負責人看過測試結果、image ID 已經定下來之後，才批准推送。

- 輸入：`app`（商店產品；OpenDesign 沒有映像，會被擋）與必填的 `source_sha`（完整 40 位小寫 hex）。
- 只能在 `release/<名稱>` 分支上觸發（`<名稱>` 只有一段，不含 `/`）。這種分支是開著的升版 PR，那個 PR 要先有映像才過得了
  readiness。PR、tag 和其他分支一律不行。
- re-run 一律不收：三個 job 的 `check_release.py` 都要求 `GITHUB_RUN_ATTEMPT` 是 1（主對話 2026-11-17 確認）。**任何一段失敗都要
  重新觸發，不能 re-run**，包括 gate 或 candidate 因為網路之類的暫時問題失敗。GitHub 的 re-run 會沿用原本的 commit 和 inputs，30 天
  內都能按，而一次批准只綁一次 attempt。
- `gate`（`contents: read`、`actions: read`，限時 60 分鐘，沒有 job 條件）：
  1. `check_release.py`：從別的 ref 觸發就在這裡失敗（紅燈），不是被略過的綠燈。
  2. `environment_gate.py gate`：用這次執行的 `GITHUB_TOKEN` 讀 `public-release` 的設定。只打 `https://api.github.com`、不跟轉址、
     不走 proxy。下面任何一項不符就停：
     - environment 必須存在（404 就停：GitHub 會在第一次用到時自動建一個沒有保護的同名 environment）；
     - 保護規則只能是 required_reviewers、branch_policy、wait_timer，恰好一條 required_reviewers，唯一的審查者是
       User id 165237880（WOOWTECH，用 id 比，不用名字）；
     - `can_admins_bypass` 是 false（沒有這個欄位也算失敗）；
     - `deployment_branch_policy` 恰好是 `{"protected_branches": false, "custom_branch_policies": true}`，唯一的部署分支規則是
       branch `release/*`。
     `prevent_self_review` 不要求，但如果開著、而觸發的人（`GITHUB_ACTOR_ID`）就是唯一的審查者，gate 直接失敗，因為那樣永遠等不到
     批准。用 `GITHUB_ACTOR_ID` 的理由：它是 `github.actor` 的數字 id，可以和審查者一樣用 id 比；第一次 attempt（`check_release.py`
     只收這個）時 `github.actor` 就是觸發的人，`GITHUB_TRIGGERING_ACTOR` 只在 re-run 時才會不同，而且沒有數字 id。HTTP 403、429、
     5xx 和網路錯誤（包括連線中斷、回應不完整這類 `http.client` 錯誤）重試一次（照 Retry-After，最多等 60 秒），再失敗就印一行訊息
     停止；其他錯誤馬上停。
  3. `validate.py`、packaging 單元測試、`packaging/unit.sh`。
- `candidate`（`contents: read`；沒有 environment、沒有 packages 權限；只在 `release/*`；限時 150 分鐘）：在推送權限出現之前把映像建好、
  驗完：
  1. 在這台機器上再跑一次 `validate.py` 與 `check_release.py`。
  2. 託管機器預檢 `packaging/hosted_runner.py`（建置之前）：`runner.environment` 必須是 `github-hosted`（Linux X64）；沒有把 Docker
     或 Buildx 指到別處的環境變數，目前 context 是本機 socket；建置輸入每個人都讀得到（映像以 UID 10001 執行）；Docker 必須用
     classic overlay2 image store，因為閘門靠「image ID＝config digest」。這台機器用完即丟：開著 containerd image store 時，
     在 `/etc/docker/daemon.json` 設 `features.containerd-snapshotter: false`（其他設定保留）、重啟 Docker，再確認 `docker info`
     是 overlay2、沒有 containerd snapshotter。Docker client／server／API／元件與 Buildx 的版本寫進 `release-evidence/hosted-runner.json`。
  3. `docker/build-push-action`（釘 commit）只建一次：`builder: default`、`linux/amd64`、`load: true`、`push: false`、
     provenance／sbom 關閉、revision label＝`github.sha`。
  4. `install_scanners.py`：checksum 固定的 Gitleaks、Syft、Grype。
  5. `supply_chain.py candidate`：對同一個 image ID 跑 `container_acceptance.py`（`container_probe.py`，含探針 1a 子程式 bearer
     直連 401、1b HM-13a 還原樹）、source／完整 history／全部 layer 的 Gitleaks、Syft 與 SPDX SBOM、Grype、授權政策。
  6. J1900 指令集檢查 `packaging/j1900_check.py`（DQ-42：每次發版都做）：
     - 先用 `supply_chain.verify_current` 確認本機 tag 仍是測過的 image ID、證據沒變；
     - `qemu-user-static` 從這台機器的 apt 裝，記下套件版本、`qemu-x86_64-static --version` 與執行檔 SHA-256；
     - 核心 venv `/opt/woow/.venv` 和子程式 venv `/opt/woow/apps/<app>/.venv`：`packaging/j1900_probe.py` 分開列出直譯器自己的
       （lib-dynload）和套件的（site-packages）原生擴充模組，先全部原生 import。每個 venv 至少要有一個 site-packages 模組原生
       import 成功；原生 import 失敗的模組，除非 `packaging/j1900-allowlist.json` 為這個產品列出審過的理由，**而且**原生的錯誤訊息
       （`型別: 訊息`）含有那一條的 `error_contains`（唯一已知的原因），否則整個檢查失敗（同一個模組換了別的原因照樣擋；什麼時候報、
       怎麼報見下面「一次報完」）。允許清單裡的模組如果原生其實 import 成功，照樣送去 QEMU 測，不會因為列在清單就跳過。原生成功的那一批再用
       `qemu-x86_64-static -cpu Nehalem` import 一次，兩邊必須一樣（唯一的例外是下面的 QEMU-only 條目），而且不能有 SIGILL；小
       smoke（hashlib、ssl、zlib、sqlite3、decimal、re）兩邊結果相同；
     - QEMU-only 條目（`qemu_error_contains`；和 `error_contains` 二選一，同一條兩種都有就整個清單不收）：給原生 import 成功、只在
       QEMU 下因為模擬器缺系統呼叫而失敗的模組。一個模組要同時符合四點才從 QEMU 的比對拿掉：這個產品的清單有它的 QEMU-only 條目、
       它原生 import 成功、它在 QEMU 下失敗、QEMU 下的錯誤訊息（`型別: 訊息`）含有 `qemu_error_contains`。拿掉之後，QEMU 下成功的
       必須剛好是原生成功的減掉拿掉的（順序也一樣），失敗的必須剛好就是拿掉的；「送去的每個模組恰好回答一次」的檢查不變；SIGILL
       檢查不變而且先做，清單怎麼寫都擋；smoke 比對不變。列在清單、但 QEMU 下其實成功的模組照常比對，不拿掉；原生就失敗的模組不能
       靠 QEMU-only 條目放行。拿掉的模組和它在 QEMU 下的錯誤訊息記在證據的 `qemu_allowlisted`；
     - 一次報完（審查第三輪 中-1）：「原生失敗而清單沒放行」和「QEMU 下不一樣而沒有 QEMU-only 條目放行」這兩種不當場丟出，先收集起來，
       核心和子程式 venv 都跑完之後由 `check()` 一起報，有任何一筆就失敗。訊息是一行，分「原生」和「QEMU」兩段，每筆寫成
       `<venv> <模組> (<型別: 訊息>)`（單行、每筆最多 300 字），每段最多 1500 字，超過就截斷並註明總筆數；兩種都有時兩段都一定
       會出現。下面這幾種照舊當場失敗：SIGILL、執行失敗（exit 不是 0、逾時、超過 60 分鐘）、沒有 JSON、回答沒交代每個送去的模組
       （不多不少、不重複；QEMU 那一輪還要照送去的順序）、模組名稱不是點分隔的 Python 識別字、列不出原生模組或沒有任何模組／任何
       site-packages 模組原生成功（等於沒得檢查）。smoke 也照舊當場失敗：smoke 自己 import hashlib、ssl、sqlite3、zlib、
       decimal、re，前提是這些模組在 QEMU 下 import 得一樣，模組比對有差異時它可能跟著失敗。當場失敗時，訊息後面會接著寫出在它
       之前已經收集到的問題（`found before it: …`），原因還是一次看得到；
     - 模組名稱（審查第三輪 低-1）：映像回報的模組名稱（清單、`ok`、`err`、`detail` 的鍵）和允許清單的模組名稱，都必須是點分隔的
       Python 識別字，否則當場失敗；失敗訊息裡「最後一個 `TRY`」也只顯示合格的名稱。這樣映像裡的名稱沒辦法在 log 裡換行、冒充
       workflow 指令（`::…`）；
     - 允許清單的內容：一開始是空的（審查 M1）。主對話 2026-11-17 決定，替有映像的七個產品（odoo、n8n、hermes、emqx、litellm、
       nextcloud、headscale；OpenDesign 沒有映像，不加）加 `_tkinter`，`error_contains` 是
       `ImportError: libtk8.6.so: cannot open shared object file`。理由：官方 python slim 映像的 lib-dynload 帶著
       `_tkinter.cpython-313-x86_64-linux-gnu.so`，但刻意不裝 Tcl/Tk，所以原生 import 一定是缺 libtk 的 ImportError；add-on 的
       程式和依賴都不 import tkinter，J1900 要擋的是實際會執行的程式碼在 Nehalem 上的 SIGILL。依據是 0.4.16 Headscale 候選映像的
       SBOM（發版證據，在 repo 外：`artifacts/headscale-ha-closure-20261111/candidate-0416/sbom.syft.json`）：lib-dynload 有
       `_tkinter`，沒有任何 Tcl/Tk 函式庫或套件。之後基底映像換了 Tk 版本、或 `_tkinter` 換了失敗原因，都會被擋下、重新審；
     - QEMU-only 條目的內容：主對話 2026-11-18 決定、負責人在 #119 覆核，替子程式裝了 caio 的四個產品（emqx、litellm、nextcloud、
       headscale）加 `caio.linux_aio`，`qemu_error_contains` 是 `ImportError: Error on io_setup with code 38`。caio 0.12.10 由
       aiofile 帶進來，只在這四個子程式的 `uv.lock`，核心 venv 和其他產品都沒有（單元測試核對 lock 檔）。依據：caio 0.12.10 的
       `caio/linux_aio.c` 在 `PyInit_linux_aio` 先用 uname 檢查核心版本，再呼叫 `io_setup(1, &ctx)`，失敗就
       `PyErr_Format(PyExc_ImportError, "Error on io_setup with code %d", errno)`；QEMU 的 linux-user 模式沒有實作 AIO 系統呼叫，
       io_setup 拿到 `-TARGET_ENOSYS`，所以 QEMU 下 import 失敗、code 38（ENOSYS）；同一個映像原生 import 成功（Docker 預設的
       seccomp 允許 io_setup），真的 J1900 主機上 io_setup 也能用。#119（head `b24a2d7`）第二次在 GitHub 託管機器建置時，這四支
       就是卡在這裡（`modules differ under -cpu Nehalem: caio.linux_aio`），沒有 SIGILL。模擬器缺系統呼叫，不是指令集問題；SIGILL
       檢查不變。限制：code 38 是從原始碼推出來的，沒有實測，訊息不一樣照樣擋，失敗訊息會帶出實際的錯誤；QEMU 下這個模組
       io_setup 之後的程式沒有跑到；
     - caio 的原生條目（審查第三輪 中-1）：同樣是主對話 2026-11-18 決定、負責人在 #119 覆核，替這四個產品加 `caio.linux_uring`，
       `error_contains` 是 `ImportError: io_uring_setup probe failed: Operation not permitted`。依據：caio 0.12.10 的 wheel 也帶
       `caio/linux_uring.cpython-313-x86_64-linux-gnu.so`；`caio/linux_uring.c` 的 `PyInit_linux_uring` 先用 uname 確認核心至少
       5.6，再用 `io_uring_setup(1, …)` 試探，失敗而且不是 ENOSYS 就丟
       `PyErr_Format(PyExc_ImportError, "io_uring_setup probe failed: %s", strerror(errno))`（ENOSYS 是另一段訊息）。Docker 預設的
       seccomp（moby v28.0.4 的 `profiles/seccomp/default.json`）沒有任何 io_uring 項目，沒列的系統呼叫一律回
       `defaultErrnoRet` 1（EPERM），J1900 的容器用的就是預設 seccomp，所以原生 import 會得到這段 EPERM 訊息，這個模組也就不會送去
       QEMU。HAOS 上的 add-on 容器也套預設 seccomp，io_uring 一樣被擋；caio 的 `__init__.py` 依序試 linux_uring、linux_aio、
       thread_aio、python_aio，所以會退回 `linux_aio`，正式環境除了那段失敗的試探，`linux_uring` 的程式不會執行。限制：哪天
       io_uring 被放行，`linux_uring` 就會在沒有 J1900 覆蓋的情況下執行（如果是託管機器的 Docker 放行，檢查會發現：那時它原生
       import 得起來，送去 QEMU 會失敗，因為 QEMU 也沒有 io_uring_setup）。#119（head `b24a2d7`）第二次託管建置沒看到這個錯誤，
       是因為當時檢查在 QEMU 差異那裡就先失敗了，現在改成一次報完；
     - n8n 沒有子程式 venv，改跑 Node：載入 better-sqlite3、建 FTS5、crypto、zlib，原生和 QEMU 結果相同；
     - 容器一律 `--network none --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges`，只唯讀掛探針和
       QEMU；整個 J1900 檢查最多 60 分鐘，每次容器執行只拿剩下的時間；
     - 遇到 SIGILL（exit 132 或 QEMU 的 `uncaught target signal 4`）就失敗，允許清單怎麼寫都一樣，訊息寫出最後一個 `TRY <模組>`；
     - 結果寫成 `release-evidence/j1900-<app>.json`，PASS 那一行寫出每個 venv 各類模組的數目（含 QEMU-only 拿掉幾個）。限制：QEMU
       只檢查實際跑到的程式（import 與 smoke），不是完整執行路徑。
  7. `image_handoff.py save`：確認本機 tag 仍是測過的 image ID，用 `docker image save` 存成 `image.tar`，檢查裡面恰好是那一個
     映像（config digest＝image ID、tag、diffID），寫 `handoff.json`，並把 image ID 寫成 job output `image_id`。tar 裡的成員只准
     `docker image save` 會寫的名稱（`manifest.json`、`index.json`、`oci-layout`、`repositories`、`blobs/sha256/<64 位 hex>`，
     加 `blobs`、`blobs/sha256` 兩個目錄；依據是 Docker 28.0.4 也就是 moby v28.0.4 的 `image/tarexport/save.go` 與 `pkg/archive`），
     每個名稱只能出現一次，`./manifest.json` 這種不是標準寫法的名稱、連結、裝置都擋：Docker 和這個檢查必須讀到同一個成員。
  8. 上傳兩個 artifact：`candidate-image-<app>-<sha>`（`image.tar` 與 `handoff.json`，**只留 3 天**；public repo 的 artifact
     儲存不收費，1 天對等批准太緊）與 `candidate-evidence-<app>-<sha>`（candidate 證據、`hosted-runner.json`、`j1900-<app>.json`，
     留 90 天）。
- `publish`（`environment: public-release`；`contents: read`、`packages: write`、`actions: read`；只在 `release/*`；needs gate 與
  candidate；限時 60 分鐘）：負責人批准之後才開始：
  1. 再跑一次 `validate.py` 與 `check_release.py`（只收第一次 attempt）。
  2. `environment_gate.py publish`：gate 那套檢查全部再做一次，加上這次執行的審查紀錄（`GET /actions/runs/<run>/approvals`）
     必須有 User 165237880 對 `public-release` 的 approved，而且沒有任何 rejected。查不到 approved 時，間隔約 10 秒再查兩次（job
     開始時紀錄可能還沒寫進去）；看到 rejected 立刻失敗，不再查。紀錄寫進 `publish-evidence/approval.json`：run id、attempt、
     commit、觸發者、environment 的 `updated_at`、每筆審查的狀態、審查者、environment，以及**有沒有留言和留言長度**（不收錄留言
     全文）。
  3. 託管機器預檢 → `publish-evidence/hosted-runner.json`（`docker load` 只有在 classic store 下才保留 image ID）。
  4. 下載兩個 artifact，各放進 `$RUNNER_TEMP` 底下自己的目錄：映像到 `$RUNNER_TEMP/handoff`、證據到
     `$RUNNER_TEMP/candidate-evidence`（不進 checkout，也不會和 runner 自己放在 `$RUNNER_TEMP` 的檔案混在一起）。
     `actions/download-artifact` 釘 v4.3.0 的 commit
     `d3f86a106a0bac45b974a628896c90dbdf5c8093`：2026-11-17 以公開 API 核對過，這是正式 release tag（不是 draft 或 prerelease），
     和 `upload-artifact` v4.6.2 同一代。
  5. `image_handoff.py load`：candidate 的 job output（和 artifact 分開的管道）＝`handoff.json`＝`subject.json` 的 image ID；
     J1900 紀錄 `j1900-<app>.json` 的 `passed` 是 true、`image_id` 就是這次要推的 ID；`image.tar` 的 SHA-256 符合紀錄、成員名稱
     合規、裡面恰好是那一個映像；這台機器上還沒有那個 tag；`docker load` 前後比對映像清單，只能多出那一個 ID 和那一個 tag；載入後
     tag 指向的就是那個 ID 與 diffID。
  6. `supply_chain.py verify`：載入的映像和整份 candidate 證據相符。
  7. `registry_gate.py unused`（用 `GITHUB_TOKEN` 確認這個版號在 GHCR 還不存在；registry 錯誤不當成「不存在」）→
     `docker/login-action` 用 `GITHUB_TOKEN` 登入 → 推送步驟（再 verify 一次，用測過的 ID 打 tag，確認 tag 指向同一個 ID 才
     `docker push`，只推那一個 ID，不重建）→ `registry_gate.py public`（乾淨設定匿名以不可變 digest 拉回，核 manifest、
     config digest＝測過的 ID、diffID）。
  8. 上傳 `published-evidence-<app>-<版號>-<sha>`（留 90 天）：candidate 證據加 published provenance／digest、兩個 job 的
     `hosted-runner.json`、`j1900-<app>.json`、`handoff.json`、`approval.json`。candidate 證據過了證據的秘密掃描；其餘幾個沒經
     Gitleaks：`hosted-runner.json`、`handoff.json`、`approval.json` 是程式自己組的欄位（版本、計數、ID、審查狀態與留言長度），
     `j1900-<app>.json` 另外帶著**映像產生的錯誤訊息**（原生 import 失敗的，以及 `qemu_allowlisted` 拿掉的模組在 QEMU 下的
     「型別: 訊息」，每筆最多 300 字），這部分不是固定欄位。
- artifact 是公開的：這個 repo 是 public，任何登入 GitHub 的人都能下載它的 artifact。候選映像（`candidate-image-…`，含整個
  `image.tar`）在負責人批准之前就看得到；被 Reject 的也會留到過期（3 天）。證據 artifact 留 90 天。所以審查留言不要寫機密
  （`approval.json` 雖然只記留言長度，留言本身在執行頁的審查紀錄裡，有讀取權的人都看得到）。
- concurrency：每個產品一組（`public-release-<app>`），不同產品可以同時推；`cancel-in-progress: false`，進行中的執行永遠不取消。
  GitHub 的規則：同一組已有一個在跑時，新觸發的排隊等；再觸發一個，排隊中的那個會被新的取代（還沒開始，不會推任何東西）。
- 環境變數只有這些：candidate job 的 `APP` 和 `DOCKER_BUILD_SUMMARY`、`DOCKER_BUILD_RECORD_UPLOAD`（都是 `false`）；publish job 的
  `APP`；三個 `check_release.py` 步驟的 `SOURCE_SHA`（＝`inputs.source_sha`；gate 那步另有 `APP`）；兩個 `environment_gate.py`
  步驟的 `GH_TOKEN`；兩個預檢步驟的 `RUNNER_KIND`（＝`runner.environment`）；載入步驟的 `EXPECTED_IMAGE_ID`
  （＝`needs.candidate.outputs.image_id`）；`registry_gate.py unused` 的 `GHCR_TOKEN`。`GH_TOKEN`、`GHCR_TOKEN` 和登入密碼都只能是
  `${{ secrets.GITHUB_TOKEN }}`；其他任何地方（包括 workflow 名稱、步驟名稱和輸入說明）出現 `secrets`、`github.token` 或 `${{`
  都會被擋。不寫
  `GITHUB_ENV`、`GITHUB_PATH`；唯一的 job output 是 `image_handoff.py save` 寫的 `image_id`。`validate.py` 逐步比對整個檔：三個 job
  的步驟清單與順序、action 釘的 commit、env、needs、outputs、權限、environment、job 條件、限時、concurrency、run-name；多一個
  步驟、env 或 secret 都會失敗。
- 權限和原定案的差別：原定 publish 的權限「恰好 contents: read 加 packages: write」。為了讓 `environment_gate.py` 讀 environment 設定
  和這次執行的審查紀錄，gate 與 publish 多了 `actions: read`（審查 H1，主對話 2026-11-17 核准）。`actions: read` 只能讀 Actions
  的資料，不能觸發、批准或改設定。

`check_release.py` 的放行條件（三個 job 各跑一次）：

- 事件是 `workflow_dispatch`，`GITHUB_REF` 是 `refs/heads/release/<一段名稱>`；
- 是第一次 attempt；
- checkout 的 HEAD＝`GITHUB_SHA`＝`source_sha`（完整 40 位小寫 hex）。`GITHUB_SHA` 是**觸發當下**那個分支的 head：程式只保證三者
  相等，不能證明它現在還是 head，也不能證明它就是負責人看過的 PR head，這要負責人批准前核對（見下面的檢查清單）；
- 產品在商店清單、而且有映像（OpenDesign 擋）；
- `validate.py` 的 `version_for(產品)` 等於 `addons/<產品>/config.yaml` 的版號。

`RELEASE-GATES.json` 是 BLD2 時期的人工 clearance 檔（仍全部 false、`approved_commit` 是 null）：`validate.py` 只檢查它的格式，
發版不再讀它。0.1.0–0.4.13 與 Headscale 0.4.14–0.4.18 沒有經過 `release.yaml`：依負責人 2026-10-05 的公開決定
（[紀錄](release-decision-2026-10-05.md)），由私有 builder 推送已測的同一 image ID，再以匿名 `registry_gate.py public` 核對。

### 負責人要在 GitHub 設定的項目（workflow 自己做不到）

照這個順序做；第 3 項確認之前不要觸發 `release.yaml`。

1. Settings → Actions → Runners：確認沒有自架 runner（2026-11-17 用 API 查是 0 個）。
2. Settings → Environments → New environment，名稱 `public-release`：
   - Required reviewers：只加負責人帳號 WOOWTECH。gate 用 User id 165237880 比對，多加別人或團隊都會失敗。
   - Prevent self-reviews：不要勾。觸發的人就是唯一的審查者，勾了就永遠批不了。
   - Allow administrators to bypass configured protection rules：取消勾選（API 的 `can_admins_bypass` 會變成 false）。
   - Deployment branches and tags：選 Selected branches and tags，加一條 **Branch** 規則 `release/*`（`*` 不跨 `/`，只認一段名稱，
     和 `check_release.py` 一致）。不加 tag 規則。
   - 不加 environment secret 或 variable。wait timer 可以不設，設了只會被記錄。
3. 確認 gate 的檢查真的會過：在本機跑 `python3 -I packaging/environment_gate.py gate --anonymous`（匿名、唯讀，和 gate job 同一套
   檢查；在 Actions 裡不准用匿名模式），或用下面的 curl 逐項核對。
4. 每個要發的套件（WOOWTECH 的 Packages → `amd64-mcp-<產品>`；這次是 odoo、n8n、hermes、emqx、litellm、nextcloud，Headscale
   走這條時再加 `amd64-mcp-headscale`）：Package settings → Manage Actions access，`Woow_ha_mcp_addons` 的角色設 **Write**，
   不要 Admin。如果那一區顯示的是 Inherited access（從 repo 繼承），要先取消勾選 **Inherit access from repository**，才能改成
   Write。可見度維持 Public（`registry_gate.py public` 用匿名拉取核對）。這一項只是把權限收到最小，**不是保險**：Dockerfile 有
   `org.opencontainers.image.source`，套件連到這個 repo，這個 repo 的 workflow 宣告 `packages: write` 就能推（見「限制」）。
5. Repository 的 Actions 設定維持現狀：Workflow permissions 預設 read，allowed actions 是 all（2026-11-17 查得）。

手動 curl 核對（匿名；這個 repo 是 public）：

- `curl -s https://api.github.com/repos/WOOWTECH/Woow_ha_mcp_addons/environments/public-release`：`protection_rules` 恰好一筆
  `type` 是 `required_reviewers`，它的 `reviewers` 只有 `{"type": "User", "reviewer": {"id": 165237880, …}}`；其餘規則的 `type`
  只能是 `branch_policy` 或 `wait_timer`；`can_admins_bypass` 是 `false`；`deployment_branch_policy` 是
  `{"protected_branches": false, "custom_branch_policies": true}`。GitHub 文件的回應 schema 沒列 `can_admins_bypass`，但 GET 實際會回
  （2026-11-17 匿名查 astral-sh/uv 的 environment，有 true 也有 false）。
- 同一路徑加 `/deployment-branch-policies`：`total_count` 是 1，唯一一筆的 `name` 是 `release/*`、**`type` 是 `branch`**（不是 `tag`）。

### 負責人批准前的檢查清單（每一支 publish）

1. 這次要發的六支，candidate 都通過了，才批准任何一支的 publish。某一支因為要改來源才修得好的原因失敗，就全部 Reject；某一支是
   暫時性失敗，就等那一支重新觸發、candidate 通過之後再一起批准（見下一節）。
2. 以執行摘要頁上顯示的 commit 為準，不要看 run-name（它來自可以被改的 workflow）。那個 commit 要等於升版 PR 目前的 head。
3. 在 PR 的 Files changed 確認 `.github/` 和 `packaging/` 相對 `claude-delivery` 只改了版號資料（`validate.py` 的 `VERSION`／
   `VERSION_OVERRIDES`，`release.yaml`、`ci.yaml` 的版號運算式）。
4. 確認那個 SHA 在 PR 上的 checks（`checks`、`Release train`）是綠的。
5. 只批准第一次 attempt，不要批准 re-run（程式也會擋）。
6. `image.tar` artifact 只留 3 天：candidate 完成後三天內要批准，過期就 Reject、重新觸發（同一個 commit，見下一節）。

批准：Review deployments → 勾 `public-release` → Approve and deploy；不對就 Reject。批准只由負責人本人在網頁上按，代理不呼叫批准 API。

### 部分失敗怎麼辦

- **所有產品都推完之前，不准往 release 分支推任何 commit，紀錄檔也不行。** `workflow_dispatch` 永遠跑在分支的 head，`source_sha`
  又必須等於 `GITHUB_SHA`：分支一動，就沒辦法再用同一個 commit 重新觸發。紀錄檔在全部推完之後才加（發版步驟第 6 步）。
- 任何一段失敗都要重新觸發，不能 re-run（程式會擋 attempt 不是 1 的執行）。
- 暫時性失敗只有這幾種：網路、GitHub API 的 5xx、apt 或 Docker Hub 拉不到、artifact 服務出錯。測試、掃描、CVE、授權、J1900 的
  判定結果不是暫時性的，不准靠重跑到過。
- 同一支最多因暫時性失敗重新觸發一次（用同一個 commit），而且要寫進那個產品的發佈紀錄（失敗的 run、原因、重新觸發的 run）。再失敗
  就當成要修來源處理。
- candidate 有任何一支失敗（包括 J1900、原生 import 失敗而允許清單沒列）：要改來源才修得好的，全部 Reject，修好換新 head
  （新的 `source_sha`）重來；暫時性的，等那一支重新觸發、candidate 通過之後再一起批准。這時什麼都還沒推，不燒版號。
- publish 批准後中途失敗：
  - 推送前失敗：沒推，可以用同一個 commit 重新觸發那一支。暫時性的（例如 artifact 服務、網路）照上面的次數限制；artifact 過期
    也是重新觸發；load、verify 或 J1900 紀錄不符、`registry_gate.py unused` 判定版號已存在都不是暫時性的，先查原因。
  - 推送後失敗（例如 `registry_gate.py public`）：那一支的版號已燒，不覆寫、不刪 tag。
  - 已經推上去的產品保留，紀錄寫明映像來源（run、commit、digest）；剩下的用同一個 commit 重新觸發；需要改來源的，改發下一版。

### 發版步驟（每次）

前提：這條流程的 PR 已合併到 `claude-delivery`；升版 PR 的 `release/<名稱>` 分支已包含它（例如把 `claude-delivery` 合併進去，
`release.yaml` 的版號運算式照 `validate.py` 印出的那個）；PR head 已凍結（之後只加紀錄檔）；上面的設定已確認，gate 檢查會過。

1. 在升版 PR 的分支上逐產品觸發，帶 `source_sha`：Actions → `Manually approved GHCR publication` → Run workflow →
   Use workflow from 選 `release/<名稱>` → `app` 選產品 → `source_sha` 填那個分支目前 head 的完整 SHA
   （`git rev-parse origin/release/<名稱>`）。命令列：`gh workflow run release.yaml --ref release/<名稱> -f app=<產品> -f source_sha=<sha>`。
   六支都用同一個 `source_sha`，可以同時觸發；同一個產品不要重複觸發。
2. 等六支的 gate 和 candidate 都通過（約 35–40 分鐘加建置與檢查）；publish 會停在 Waiting。
3. 負責人照上面的檢查清單逐支批准。
4. readiness 和 Upgrade comparison：映像推上去後在升版 PR 重跑這兩項（Re-run，或第 6 步推紀錄時自動重跑）。
   `Upgrade comparison / compare` 拉 GHCR 上的新舊映像做設定比對、升級測試、漏洞比對；要求 `upgrade-notes.yaml` 時照
   `AGENTS.md` 第 3 點補。readiness 的映像部分會過，紀錄部分要等第 6 步。
5. 在負責人的 HAOS 實機驗收（[ha-p9-kit](ha-p9-kit.md)）。備份、安裝、更新這些會改狀態的步驟逐步等負責人批准，先備份。
6. 每個產品自己的發佈紀錄 `release-decision-<產品>-<版號>.md`（readiness 的規則見上面）：寫 slug、版號、`source_sha`、那次執行的
   連結與 attempt、`approval.json` 的重點（誰、何時批准）、不可變 digest、證據 artifact 的重點（image ID、scan summary、J1900 結果
   與 qemu 版本、Docker 與 Buildx 版本）、暫時性失敗而重新觸發的紀錄（如果有）和第 5 步的結果。證據 commit 只加紀錄檔，而且要等
   所有產品都推完才推（見「部分失敗怎麼辦」）。
7. 所有 required checks 通過後，負責人本人合併（merge commit），也就是上架 WOOW App Store。

### 限制

- 被觸發的分支決定一切：`workflow_dispatch` 跑的是被觸發分支上的 `release.yaml` 和 `packaging/` 程式，`validate.py` 是在被檢查的
  那份 workflow 裡檢查自己。分支上的程式一改，所有檢查（包括 `environment_gate.py`）都可能一起被改掉，所以批准前要看 PR 的差異
  （檢查清單第 3 項）。
- 每次升版都要改 `release.yaml`、`ci.yaml` 的版號運算式，所以能推 release 分支的憑證，一定也能改 workflow。
- 本機代理用的 gh 帳號就是 WOOWTECH 本人：技術上能觸發，也能用 pending_deployments API 批准自己的執行。「只有負責人本人在網頁上
  批准」是規則，不是技術邊界；`environment_gate.py publish` 只能證明 WOOWTECH 這個帳號批准了，不能證明是誰按的。
- 這個 repo 的任何 workflow 只要宣告 `packages: write` 就能推 GHCR（套件連到這個 repo，Actions 的存取是整個 repo，不分 workflow）；
  `public-release` 的批准只管 `release.yaml`。
- 負責人 2026-11-17 約 22:0x（台北）對上面這幾點的決定：「先照現況，靠規則」。代理沿用負責人的 WOOWTECH 權杖；代理的 GitHub 工具
  不准核准部署，核准一律由負責人在 GitHub 上按；限制照實寫在這裡。結構性的修法之後有需要再另案改：用獨立的機器帳號觸發（不給它
  批准權）；把版號運算式移出 workflow（升版就不必動 `.github/`，才能用規則鎖住 workflow）；開 Prevent self-reviews（觸發者和審查者
  要是不同的人）；用 ruleset 要求 `release/*` 或 `.github/` 的變更經過審查。
- 託管機器的 Docker、Buildx、QEMU 版本由 GitHub 與 Ubuntu 決定，不釘版本，只記進證據。containerd image store 的切換、QEMU 在容器裡
  跑、`docker save`／`docker load` 保留 image ID、environment 與審查 API 的實際回應，在第一次真的執行之前都只有單元測試（假的
  Docker 與 API）。

### 供應鏈閘門細節

供應鏈是**可執行的必要 gate**，不是外部手動 waiver：公開 checksum 固定的
Gitleaks 8.28.0、Syft 1.54.0、Grype 0.120.0（Grype 0.89.0 下載 v6 DB 會 panic，2026-10-05 升級；掃描前先單獨 `grype db update`）；完整 fetched refs 的 history、HEAD tree、
Docker save 所有 layer/config 秘密掃描；整個 image 的 all-layers Syft/SPDX SBOM；
CVE／license fail-closed policy。原始 scanner stdout/stderr/report 不印出、不上傳；
Docker action 的自動 build record/summary 也停用。詳見 [精確映像與信任界線](hardening.md)。
這些 commands 自 2026-10-05 起在私有 builder 對每版真實 image 執行並通過（0.1.0 為七類候選 f75fe32；0.1.5 為六支候選 0c66bd0），
2026-11-17 起改在 `release.yaml` 的 candidate job 執行（推送前在 publish job 以同一份證據再核一次）。

Push 前再核對 local ID、source、SBOM/scan/provenance hashes；push 後以匿名 manifest
的 SHA256、config digest、空 Docker config 的 immutable pull、實際 pulled diffIDs
核對**先前測過的 image**，而非只相信 tag/RepoDigest。成功才產生含實際 registry
manifest digest 的 published provenance/receipt，並保留原始 candidate image ID 關聯。
GHCR visibility 不由 repo public 自動決定；失敗停止、不更換／覆寫 version。

證據 artifact 保留 **90 天**；負責人或代理要在到期前把它保存下來，供長期 release review。
這是 **unsigned CI receipt，不是 signed attestation 或 SLSA 認證**；未索取 id-token/write。
不聲稱 buildx load 保留 attestations。正式 release/stable/HA acceptance 仍需全表驗收。
