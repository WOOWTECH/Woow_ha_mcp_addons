# 執行計畫與本地里程碑狀態

依據：`2026-10-03-mcp-haos-approved-design.md`、`acceptance-matrix.md`。本批停在本地整合里程碑等待上游；**不是全部產品／公開發佈／HA驗收完成**。

## 範圍與來源

- 僅 Odoo、Odoo Manage、n8n、Hermes、OpenDesign、EMQX、LiteLLM；Kubernetes／Vibe Kanban 排除，沒有第二階段。
- Legacy SHA `614ae663fadd91c76972f60017a76d2627bea87e` 唯讀；新 repo 無舊 Git 歷史、環境設定、inventory 或憑證。
- EMQX／LiteLLM 已取得 commit-pinned 真實公開來源；不是目前生產 image→commit attestation。
- 共用 boundary/UI 為新寫替代；實際 copied app/runtime/NOTICE 有逐檔 provenance。不把未納入的 legacy shared license 當永久阻礙。OpenDesign 舊上游授權、Manage MPL 對應源碼、依賴通知仍需公開前審核。
- 目標 amd64／Supervisor 2026.09.3／Core 2026.7.2。沒有 aarch64 或真實 image/HA 相容性通過宣稱。

## 工作狀態

| ID | 產物／驗證契約 | 本批狀態 |
|---|---|---|
| S1 | 三名獨立 scout、真實 herdr pane／dispatch 證據 | 完成，reports 保存在 repo 外；指定 pi-herdr-subagents、預設模型繼承，最多三 active |
| P1 | 新 Git、七目錄、來源 allowlist/provenance、固定依賴 | 完成；未建立 remote／push |
| W1/R1 | n8n test-first tracer、双 listener、Bearer、call gate、持久化、health/lifecycle、雙審修復 | 本地有界切片完成；後續回歸保留 |
| W2/R2 | 六個真實 runtime、型別設定/v3 migration、explicit tool/operation grants、bounded egress/output、雙審 | **55/184 有界支援**通過本地雙審；**129 項仍 open**，見完整逐名 ledger；不是完整 migration |
| AROLE | 真實 HA 管理員 verifier 與機器 token 隔離 | 僅 n8n 權限已准；固定 WS/config-auth-list provider、fresh final role 與 OS guard 已本地聯測＋雙審；HA未測，六類不擴權 |
| W3/R3 | 共用 Woow UI、七 manifests/Dockerfile、CI/GHCR gate、繁中 docs/client/backup/notice | 元件及整合 code 通過有界雙審；UI資產建置通過；映像未建置 |
| W4 | 真實 bootstrap→post-exec guard→n8n executable/provider/child；Chromium→Core UI/API | LOCAL owned fake HA transport/backend 聯測通過；非Node假server替代、非HA E2E |
| V1 | 協調者獨立最終重跑 | **568 Python + 1獨立聯測 + 39 packaging + 13 UI unit + 21 browser**，全部 exit0，無 skips；validator/actionlint/locks/inventory/原repo唯讀diff檢查 exit0 |
| M1 | 本地 commit、分層MILESTONE/TEAM-STATUS/BLOCKERS | 本地里程碑交付；精確SHA及證據見 repo外 `reports/MILESTONE.md` |
| G1 | 七映像建置/掃描、來源授權、publisher、HA安裝/實測 | **未通過／本次不跨越**；all release gates false |

最終有界整合的独立報告：`review-integration-spec.md`、全新 reviewer 的 `review-integration-security.md`。所有重現缺陷與修復、RED/GREEN、命令/exit、session/pane，留於 repo外團隊報告與 `team-evidence.json`；沒有以 test count 掩蓋發現。

## 不得混淆的四層證據

1. **程式/本地runtime測試：已過。** 七個 pinned real child + fake backend；n8n actual固定provider與fake WS、Linux token guard、真Chromium/Core。
2. **映像：未建置／未執行。** Docker/Podman/Buildx 不可用；Dockerfile/CI/容器探針是已實作程式，不是建置成功。
3. **HA：未安裝／未測。** 不改現有 Core、Supervisor 或後端；角色變更測試僅ownedfake資料。
4. **真實 client→Add-on→真後端 MCP E2E：未驗證。** 本地協定流程不能替代同機Pi/Omnigent/Hermes、LAN、實際後端credentials、備份還原與資源量測。

## 尚未完成（不是全部外部阻礙）

- 129來源工具及部分mixed operations的功能、安全契約、projection與測試：**內部backlog**，逐名在 `docs/tool-review.json`、`docs/tool-surface.md`。未知/延期fail closed，不能偷偷刪除清單或宣稱完整。
- 六類 production 管理 provider/廣泛Core權限需另批准擴用；現在仍fail closed，測試注入role不構成授權。
- 受限非正式後端、HA實際client/Ingress/撤權/backup/rollback/CPU RSS延遲證據未取得。
- 公開前來源/依賴/歷史/image掃描、OpenDesign權利人確認、MPL來源交付、GHCR安全publisher/名稱/可匿名pull與immutable digest待關卡。歷史七筆metadata checksum誤判的去密證明不是整體secret clearance；不改scanner規則/allowlist/history來假通過。

## 保持的契約

部署options不覆寫GUI backend/token/policy；0600/0700 durable原子設定、錯誤/未來版本拒絕；fixed child argv/env，未知tool/action禁止；新writer逐項grant，只有兩個既有writer保留明示legacy例外，disabled最高優先；管理與MCP/Bearer入口分離；n8n machine token不進child／UI／state／log，post-exec guard阻止同UID parent procfs/memory讀取；backend outage不觸發無限重啟，internal probe與publicdisable分離。

下一步由上游檢查本地milestone與未完清單，再決定後續功能實作與逐項外部關卡；不是自行部署或公開推送的許可。
