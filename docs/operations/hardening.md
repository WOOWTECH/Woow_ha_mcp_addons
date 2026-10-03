# 封裝安全界線與精確候選映像

此文件描述可執行 gate，不是 image／HA／publication 成功證據。所有人工 clearance
保持 false；來源授權、OpenDesign owner grant、MPL 對應 source availability、publisher
權限與真正 HA 驗收不能由 scanner 自動核准。

## 管理 process 的 token 界線

所有七個 fixed bootstrap command 最後 exec `packaging/management_launcher.py`。
它在 **final exec 之後、任何 core/app import/child 之前**設定並讀回
`PR_SET_DUMPABLE=0`、`RLIMIT_CORE=(0,0)`、`no_new_privs=1`。任何失敗停止。
然後只以 `runpy` 執行固定 n8n script／其他六類 core module；**不能改成再次 exec**，
否則 exec 可重設 dumpability。保持 uid/gid10001、無 extra caps、protection/AppArmor。

只有 n8n 管理端保留 runtime `SUPERVISOR_TOKEN`；六類不接收，child 仍必須使用
allowlisted env。Linux 測試用虛構 token、真正 bootstrap/drop/exec 與同 UID child，
確認 `/proc/<parent>/environ`、`/proc/<parent>/mem`、`process_vm_readv` 都拒絕；
unguarded control 能讀到虛構 procfs token。這不是 HA AppArmor 實測，也不防 root /
CAP_SYS_PTRACE 或已被攻陷的可信管理 process。本地已另跑真正 entrypoint→guard→n8n
→正式 factory/protocol（owned fake WS），實際 Node child 驗 parent environ/mem 拒絕，
machine token 不入 state/argv/client/log/child；這不是 image／HA 實測。

## Write denial 的正確證據

七类都有 schema-valid supported write fixture：n8n delete、OpenDesign delete UUID、
Odoo chatter、Manage create_record、Hermes skill:disable、EMQX kick、LiteLLM team create。
HTTP403 **且 backend counter delta=0** 才通過，未知／畸形參數分開。
Mutation test 僅移除 dispatch whole-tool/operation grant 檢查，保留 schema、list filter、
disabled check；七個合法 write assertions 必須失敗，不靠 native gating 或無效參數假證明。
只有 owned fake 接收副作用，不接真實後端。
容器健康探針若恰好並行增加 counter，該次測試保守失敗，不忽略 backend activity。

## Build 一次、test/scan 同一 identity

CI image jobs 與 protected `public-release` job 都執行以下流程：

1. `fetch-depth: 0`，固定 root-context amd64 build **一次**、load 本地 image。
   Docker action 自動 build artifact/summary 關閉。沒有 latest 或任意 ref/version。
2. `install_scanners.py` 從 `scanner-pins.json` 的公開版本 URL 下載 archive，**先核對
   checked-in SHA256 再解出單一 executable**；無系統安裝、remote shell、可變 tag。
   SHA256 來自各版本官方公開 checksums；不是上游程式安全審查或簽署信任。
3. `supply_chain.py candidate APP TOOLS OUTPUT` 以 Docker inspect ID 固定 candidate。
   真正 container acceptance 以該 ID 執行一次；Docker 不存在或測試失敗不能 skip。
   輸出 revision 必須是 checkout HEAD；要求 clean checkout，拒絕 shallow/submodule。
4. Gitleaks 掃描 HEAD 的完整 Git archive（含 docs），以及 `git --all --full-history -m`
   的完整 fetched refs commit patches（含 merge，不只是 reviewed_commit→HEAD net diff）。
   **發佈範圍只包含 checkout/fetched refs 可到達歷史**；不聲稱已掃描未 fetch 的 remote refs、
   reflogs、dangling objects 或另一個 repository。公開 Git 必須另經 source gate 核准。
5. Docker save 同 ID，逐一驗 config SHA256=image ID、所有 uncompressed layer SHA256=
   config diffIDs。逐層獨立取出 regular-file bytes（不跟 symlink、不套 tar 路徑/owner，
   不用 whiteout 抹去舊層），再掃所有 layers/config。Gitleaks decode/archive depth=5、
   無檔案大小 skip；不用 repo config、baseline、inline allow 或 .gitleaksignore。
   掃描命中、非零 exit、warning/error stderr、缺報告一律拒絕。Scanner 有偵測能力與
   深度限制，不能證明任何編碼的秘密都不存在；人工 secret gate 仍獨立必要。
6. Syft 對**相同 Docker archive**作 all-layers 完整 image catalog（不是僅 lockfile），
   列所有檔案 metadata、OS/Python/npm 等 package catalog、indexed/unindexed archives，
   產生 Syft JSON 與 SPDX 2.3。驗 imageID、scope、非空 files/packages、必要 package types。
   掃描器的 catalog 能力不是「每個檔案都有可判定 license」保證。
7. Grype 掃該 Syft SBOM；required schema6 DB checksum/build timestamp 與 120 小時 freshness。
   DB 無法取得／過舊／scanner error 都停止。High/Critical/Unknown severity、未知 severity
   拒絕，**不忽略 unfixed CVE**；Low/Medium/Negligible 仍記錄計數並交人工 image review。
   每一 package 的 license 必須非空且逐項符合 `supply-chain-policy.json` 明確 allowlist；
   NOASSERTION、未知、自訂/複合 expression 不猜測，全部拒絕。此保守初始 policy 很可能
   拒絕 Debian image 中尚未審的 licenses；必須審核後明確改 policy，不可忽略或假成功。
8. SBOM 本身再過 secret gate。只有 sanitized scan summary、完整 SBOM、source commit /
   imageID / diffIDs / archive hash、evidence hashes 與 unsigned provenance 可以離開私有
   暫存區；raw reports 自動刪除、不上傳。缺失／subject/hash/policy/tools 不符全部拒絕。

## Push 與 provenance 信任層級

`check_release.py` 只是人工 source/license/secret/publisher/image/HA prerequisite；
就算全變 true，也不能略過上述實際候選 gate。Push 前 `supply_chain.py verify` 再驗
source、local image ID 與 evidence hashes。只 tag 已測 ID，不重新 build。

Push 後 `registry_gate.py public APP OUTPUT` 匿名取得固定 tag manifest，驗其實際
SHA256、config digest=已測 ID；乾淨 Docker config 以 immutable digest pull，Docker
驗 blob/config hash 與 uncompressed diffIDs，再比對 pulled ID/diffIDs/RepoDigest。
失敗不產生 published receipt，不上傳成功證據；已 push 的 tag **不自動覆寫/刪除**，
由批准 publisher 處理。唯一 publisher/immutable-tag 政策與 protected environment
reviewers 必須實際在 GitHub 設定，checked-in YAML 不是外部保護已生效的證據。

成功後的 `published-provenance.json` 同時保留 tested config/image ID 與**實際 registry
manifest digest**，連結相同 SBOM/summary hashes。原 candidate provenance 不被替換。
與 SPDX/Syft SBOM 一起保存到 GitHub Actions evidence artifact（90 天，須長期封存），
不是 registry referrer 或 signed attestation。信任來源是受保護 workflow/runner/reviewer，
**不是可自行生成 JSON 的密碼學可信性，也不宣稱任何 SLSA level**。無 id-token 權限。

本地測試的 synthetic evidence／mock registry 只驗 negative gates；不能當 scanner、
真實 Docker layers/push/digest 或 HA 成功。Docker build、完整七 image gates、Grype 對
真正 image SBOM、registry anonymous pull/digest 對應、HA AppArmor/Ingress/provider 整合
都要在有權限的隔離環境另跑，並經規格與新的安全審查。
