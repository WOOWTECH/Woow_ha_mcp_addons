# 執行計畫與本地里程碑狀態

依據：`2026-10-03-mcp-haos-approved-design.md`、`acceptance-matrix.md`。上游已接受第一批55工具里程碑並解除停止點；**持續第二批內部backlog，整體產品／公開發佈／HA驗收未完成**。不重新訪談核准範圍。

## 範圍與來源

- 僅 Odoo、Odoo Manage、n8n、Hermes、OpenDesign、EMQX、LiteLLM；Kubernetes／Vibe Kanban排除。
- Legacy SHA `614ae663fadd91c76972f60017a76d2627bea87e`唯讀；新repo不匯入舊Git歷史／環境／憑證。
- 七個pinned真runtime；EMQX／LiteLLM來源固定commit，但非生產image→commit attestation。
- 共用boundary/UI為新寫替代；實際copied app/runtime/NOTICE有逐檔provenance。OpenDesign原上游授權、Manage MPL對應源碼與依賴通知仍有公開前關卡。
- 目標amd64／Supervisor2026.09.3／Core2026.7.2；無aarch64、image或HA相容性通過宣稱。

## 工作狀態

| ID | 產物／驗證契約 | 狀態 |
|---|---|---|
| S1/P1 | 三scout、新Git、七目錄、來源allowlist/provenance與固定依賴 | 已完成；pi-herdr-subagents、繼承預設模型、最多3active；無remote/push |
| W1/R1 | n8n boundary、Bearer/call gate、持久化、health/lifecycle | 第一批本地切片雙審完成，回歸保留 |
| W2/R2 | 六真runtime、typed config、v3 exact grants、bounded egress/output | 第一批55/184、129延期；不是完整migration |
| AROLE | 真HA verifier及machine-token隔離 | 僅n8n權限獲准；固定WS/config-auth-list、fresh role、UID10001/post-exec guard本地雙審，六類仍failclosed；HA未測 |
| W3/R3 | 共用Woow UI、七manifests/Dockerfiles、CI/GHCR gate、繁中文件 | 元件／本地整合雙審；已有UI資產；映像未建置 |
| V1/M1 | 第一批歷史coordinator回歸／commit | f746b9402ce6ce6d29a62fcacecaabad8036a026：568Python＋1joined＋39packaging＋13unit＋21browser；已獲上游接受，不冒充本批新結果 |
| B1 | n8n/Odoo/Manage十個新工具及error/schema修復 | **65/184支援、119延期**；各有界SPEC→NEW SECURITY完成，真handlers/exact grants保留 |
| BLD1 | builder唯讀preflight | 已完成；需專用private disposable amd64 runner；userns未證明而非測失敗；無安裝／升權／socket |
| BLD2 | 明確driver/version/runner與hash-before-exec/helper/proxy契約 | 9檔proposal雙審後合MAIN；USER-owned hosting路線hardBLOCKED；沒有builder實際執行批准 |
| BT1 | private-port／own-listener proof／Python-Node-browser guards | 全284-file state經SPEC及全新SECURITY批准；redirect／terminalIPC／standalone readiness P1各關閉。40test/config檔逐hash/base核對合MAIN，無production覆蓋 |
| V2 | MAIN整合後coordinator新回歸 | **792Python＋獨立joined1＋65packaging＋13UIunit＋21browser**，零failure/error/skip；validator/actionlint/assetclosure/inventory/offline locks／syntax全exit0。Own jobs無deadline signal |
| B2/V3 | Odoo schema／relationships／required-value counts | 三個真handler與cache修復獨立SPEC→NEW SECURITY批准；現68/184、116延期。Coordinator新跑804Python＋joined1＋65packaging＋13unit＋21browser及靜態檢查全過 |
| B3 | 下一組n8n常用讀取 | 候選catalog tags／execution metadata／status-only health及既有folder get；先審source與間接egress，不新增執行／credentials／instance-MCP或公共站權限，再test-first與雙審 |
| G1 | 映像／授權／publisher／HA安裝與實測 | 未通過；external gate不停止不相依本地backlog |

B2新證據在repo外：`coordinator-b2-main-verification.json`、`review-b2-cache-lifecycle-spec.md`、`review-b2-odoo-metadata-quality-security.md`。B1/BT1證據：`bt1-approved-integration-files.json`、`coordinator-bt1-main-verification.json`、`review-bt1-ui-fixture-{spec,security}.md`、`team-evidence.json.current`。Historical `MILESTONE.md`／`.final`仍屬第一批。

## 四層證據，不得混淆

1. **本地runtime／fixture：本批已新驗證。** 真pinned child／SDK、Core、bootstrap／OSguard、Chromium；後端與HA transport都是自有fake。Standalone mock UI與真Core joined分開記錄，不互相替代。
2. **映像：未建置／執行。** Dockerfile、CI及mock/package checks不是image成功。
3. **HA：未安裝／未測。** 不改現有Core／Supervisor／後端；僅n8n權限例外，不外推其他六類。
4. **真client→Add-on→真backend MCP E2E：未驗證。** 同機Pi/Omnigent/Hermes、LAN、Ingress、真credentials、backup/rollback與CPU/RSS/latency仍需批准與實測。

## 尚未完成與保留限制

- 剩116工具及mixed operations的功能／schema／projection／測試是內部backlog；逐名ledger在`docs/tool-review.json`與`docs/tool-surface.md`，unknown/deferred仍failclosed。
- 六類production role provider／broad Core API需逐類批准，測試role注入不是授權。
- OpenDesign權利人、MPL對應源碼、依賴NOTICE、source/history/dependency/image掃描與安全publisher gates仍closed。Checksum metadata誤判證明不是scanner clearance，不改allowlist／history／規則假通過。
- Historical empty90s timeout、RED UID-helper child、失敗UI probe Node4153791的descendant cleanup證據缺口仍unknown；本批clean回歸不能倒推。禁止foreign PID掃殺。
- Test ownership是受信Linux/IPv4及固定Playwright1.61.1契約，proof/send非原子，非通用browser/native OS sandbox。版本升級須重審；production3000不變，測試不接觸未知3000。

## 持續契約

GUI設定不被deployment options覆寫；0600/0700 durable原子state、未知／未來schema拒絕；fixed child argv/env；新writer逐項exact grant，僅兩個既有legacy例外，disabled優先；admin/MCP/Bearer隔離；machine token不進child/UI/state/log；post-exec guard限制同UID parent procfs/memory；backend outage不無限重啟，internal probe與publicdisable分離。

接續下一工具批次，不停在68工具或報告。只有需要新決策／資源的個別項提出精確需求；無自行部署、公開push、擴權或要求未知服務讓埠的許可。
