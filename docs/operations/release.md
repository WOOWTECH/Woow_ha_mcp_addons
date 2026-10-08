# 建置、CI 與人工發佈關卡

## 固定輸入與執行狀態

目標 Supervisor **2026.09.3**（非 Core 版本），source commit
`64ea3be4322537fd5dcfbf620c4dc25490c1f56d`；validator 僅實作本專案允許的嚴格
schema 子集。參考 `supervisor/apps/validate.py` 454–557/589–606 與
`supervisor/store/validate.py` 10–17。未知 key 不准被 Supervisor 靜默丟棄。

Base image 精確 linux/amd64 manifest digest 記錄於 `packaging/inputs.json`：
Python 3.13.16 slim-bookworm、Node 22.23.2 bookworm-slim、uv 0.12.10。
2026-10-03 以 Docker Hub 公開匿名 metadata 查得（Python 基底 2026-10-05 升到 3.13.16、2026-10-06 改釘 Docker Hub 重建版），不是編造 hash，也不是
映像安全掃描／license approval／成功 build。匿名 registry 短效 pull challenge
不涉及既有帳號憑證。未使用 curl|sh、NodeSource 或 runtime 未固定下載。

原 core worker 本地使用 Python3.13.2，本封裝選支援範圍內固定 patch3.13.16；
不同 patch/base/native libraries 仍須真正 image build 和 container gate 才可接受。

**開發容器本身仍無 Docker；映像改在專用一次性 builder 建置。** 2026-10-05 起映像都在專用一次性 KubeVirt builder（Docker classic store）建置，container/mock 驗收與 supply-chain gate（source／history／image secrets、SBOM、CVE、license）全數通過才推送 GHCR（0.1.0 是七類候選 `f75fe32`，證據在協作區 `claude-delivery/evidence-real-f75fe32/`；0.1.5 是六支候選 `0c66bd0`，見 [發佈紀錄](release-decision-0.1.5.md)）。建置與推送都不經 remote Actions；0.1.0–0.1.5 已發佈，
0.1.1–0.1.5 已在測試 HA 回歸（[ha-test-0.1.5](ha-test-0.1.5.md) 等）。靜態與本地 packaging tests 不能升格成 image PASS。

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

## PR/main CI（只讀）

`.github/workflows/ci.yaml`：contents read、checkout 不保留 credentials、hosted
ubuntu-24.04、有 timeout/concurrency；不讀 secrets、不 login、不 push、不用
pull_request_target、不使用 production self-hosted runner。

1. Python3.13.16／Node22.23.2／uv0.12.10，hash-pinned PyYAML。
2. strict packaging validator + packaging tests。
3. 既有 TCP tests 固定 subprocess PATH=/usr/bin:/bin；只在 disposable hosted runner
   將 /usr/bin/node 指向 setup-node 已安裝的確切 binary，並檢查 v22.23.2，避免
   意外測到 runner 系統舊 Node。不改 core/tests；此操作未在本地工作環境執行。
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

## Manual GHCR（保持關閉）

`.github/workflows/release.yaml` 只有 workflow_dispatch，app 是固定 choices；
**沒有任意 source ref/version input**，只能 main，checkout dispatch 的確切 SHA。
預設 contents read；只有 protected environment **public-release** 的 publisher job
有 packages write，僅 ephemeral `GITHUB_TOKEN`，不讀 PAT／登入檔／舊 token。
此 job 只 build 一次，再由 `supply_chain.py candidate` 測試、匯出與掃描 **同一個 image ID**；
缺失／錯誤／政策不明／subject 不符一律拒絕。通過後才 login，push 同一個已測 ID，不另 rebuild。
拒絕既有 version tag；registry 錯誤不是「tag 不存在」。首次未能確認 namespace/
新 package tag 缺失時亦 fail closed，需要 publisher 解決，不繞過 gate。

`RELEASE-GATES.json` 是額外 checked-in 授權，不是 CI 自動產生的許可：

| Clearance | 必須審查的獨立證據 |
|---|---|
| source | 來源/owner/publication 權限、allowlisted clean history、namespace 授權 |
| license | 真正 copied files、OpenDesign owner grant、MPL source/notice、FastMCP Apache 及 image 全依賴 |
| secret | tree、完整新歷史、dependencies、image layers/config、docs/releases 的正式 scanner + 人工 review |
| publisher | 安全 GitHub 身分、repo/package 可見性、保護政策、無曝光 PAT 使用 |
| products.APP.image | 該產品真實 amd64 build/tests、exact release inputs、SBOM/CVE/licenses/secret/provenance/digest review |
| products.APP.ha | 該產品另行批准的 HA/Ingress/admin/non-admin/client/backup/fault 驗收與回復 |

目前全部 false、approved_commit=null。0.1.0–0.1.5 沒有經過這個 workflow：依負責人 2026-10-05 的公開決定
（[紀錄](release-decision-2026-10-05.md)），由私有 builder 推送已測的同一 image ID，再以匿名 `registry_gate.py public` 核對。
允許 PUBLIC/source 與 HA 安裝批准分開管理，
但本初版發布流程保守要求兩者都完成；可先在隔離核准環境測候選 image，不能借
「experimental」跳過未批准的公開 source/license/secret gate。

每個 true 必須指向 tracked `docs/operations/evidence/*.md`（目前無成功 evidence），
超過空白模板且經人審。`approved_commit` 是 protected main 上**已審完整內容**；
之後到 dispatch HEAD 的差異只准 `RELEASE-GATES.json`，避免 commit hash 自我引用。
新增/修改 evidence、Dockerfile、workflow、source 都要重新審核新的 approved_commit。
文件存在本身不是授權，owner/reviewer/保護設定需外部管理員建立：

- public-release required reviewers、禁止自己批准、只准 main。
- main branch protection、required CI checks、CODEOWNERS 必審；禁止任意 bypass。
- 唯一 publisher／固定 tag 不覆寫政策；workflow concurrency 不能防另一個未受控 writer。

供應鏈已改為**可執行的必要 gate**，不是外部手動 waiver：公開 checksum 固定的
Gitleaks 8.28.0、Syft 1.54.0、Grype 0.120.0（Grype 0.89.0 下載 v6 DB 會 panic，2026-10-05 升級；掃描前先單獨 `grype db update`）；完整 fetched refs 的 history、HEAD tree、
Docker save 所有 layer/config 秘密掃描；整個 image 的 all-layers Syft/SPDX SBOM；
CVE／license fail-closed policy。原始 scanner stdout/stderr/report 不印出、不上傳；
Docker action 的自動 build record/summary 也停用。詳見 [精確映像與信任界線](hardening.md)。
這些 commands 自 2026-10-05 起在私有 builder 對每版真實 image 執行並通過（0.1.0 為七類候選 f75fe32；0.1.5 為六支候選 0c66bd0）；
0.1.1–0.1.5 另在測試 HA 回歸；`RELEASE-GATES.json` 的 manual gates 仍全部 false（實際公開依負責人決定，見
[release-decision-2026-10-05](release-decision-2026-10-05.md)）。

Push 前再核對 local ID、source、SBOM/scan/provenance hashes；push 後以匿名 manifest
的 SHA256、config digest、空 Docker config 的 immutable pull、實際 pulled diffIDs
核對**先前測過的 image**，而非只相信 tag/RepoDigest。成功才產生含實際 registry
manifest digest 的 published provenance/receipt，並保留原始 candidate image ID 關聯。
GHCR visibility 不由 repo public 自動決定；失敗停止、不更換／覆寫 version。

只上傳已經 secret gate 的 SBOM、sanitized summary 與 digest-linked provenance/receipt，
GitHub artifact 保留 **90 天**；publisher 需在到期前保存這些證據以供長期 release review。
這是 **unsigned CI receipt，不是 signed attestation 或 SLSA 認證**；未索取 id-token/write。
不聲稱 buildx load 保留 attestations。正式 release/stable/HA acceptance 仍需全表驗收。
