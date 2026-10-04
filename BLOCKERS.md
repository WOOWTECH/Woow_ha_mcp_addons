# 本地里程碑以外的阻礙

第一批55工具里程碑已獲接受並解除停止點。B1＋BT1、B2、B3均已雙審、coordinator新回歸；**71/184支援、113內部backlog繼續**。這不是商用／HA／公開驗收完成。

- **內部功能backlog**：B1新增10工具、schema／writer／n8n public-error修復已有bounded SPEC→NEW SECURITY。B2另新增三個真Odoo metadata／missing-required count工具並修source-drift cache生命週期；SPEC及全新SECURITY批准，coordinator新804Python＋joined1＋65packaging＋13unit＋21browser／靜態檢查過。B3另新增n8n三個metadata讀取與folder get，shared-policy opt-in及Unicode修復也已雙審；coordinator新891Python＋joined1＋65packaging＋13unit＋21browser／靜態檢查過。113延期及mixed operations仍需實作／安全契約／測試，不能全部推給外部權限。逐名ledger：`docs/tool-review.json`、`docs/tool-surface.md`。
- **測試隔離已恢復安全回歸基線**：未知3000不接觸，production3000不改。BT1 privateports／fresh own-listener proof／Python-Node-browser guards及redirect／terminalIPC／standalone readiness修復已雙審批准。40test/config檔逐hash/base核對合MAIN，coordinator新跑792Python＋獨立joined1＋65packaging＋13unit＋21browser，零failure/error/skip；validator/actionlint/inventory/offline locks／assetclosure過。證據repo外`coordinator-bt1-main-verification.json`。這不是images／HA通過。
- **歷史cleanup證據缺口**：原empty90s timeout、故意RED UID-helper child、失敗UI probe Node4153791的descendant cleanup仍unknown。已披露，不以finalgreen倒推、不掃殺foreign PID。測試proof/send仍非原子、不是通用browser/native sandbox；Playwright1.61.1 privateAPI升級須重審。
- **n8n HA管理員授權**：上游2026-10-03T06:42Z批准只對新n8n試點`homeassistant_api:true`，已知broad Core admin潛在間接Supervisor/host能力。固定`ws://supervisor/core/websocket`／`config/auth/list`、fresh active/human/owner/system-admin、no positive cache、錯誤failclosed；hassio_api/auth_api false、保護不變。真bootstrap→UID10001/post-exec guard→provider＋n8n SDK與Chromium/Core本地joined通過；transport為owned fake，非HA驗收，envstrip不等於OSsandbox。
- **其他六類管理權限**：production provider仍failclosed；需上游逐類批准既審provider及broad Core API，不用test role注入冒稱HA可管理。
- **映像建置**：readonly preflight顯示builder/runtime binaries缺、UID0無subuid/helper、無FUSE、readonly cgroups／無獨立資源delegation；當時共享RAM約2.4–2.7GiB。Userns/overlay未實測，不稱kernel不支援。建議專用private disposable amd64 runner（估算4–8vCPU／16GiB／60GiB／2–4h），最小需求見repo外`UPSTREAM-BUILDER-REQUEST-BATCH2.md`。未安裝／升權／接socket／build。
- **BLD2 hosting阻擋**：explicit docker driver、hash-before-exec與helper/proxy隔離proposal已雙審及65mock/package checks，按hash/base合MAIN；WOOWTECH為USER，所需runner-group／selected-workflow保護不可用，code hardBLOCKED。不能靠env/labels繞過或自行移namespace/public source。Operator-controlled privateVM替代需另批准審核，沒有真builder執行。
- **Secret scanner gate仍DENY**：歷史313ab01七筆及最終246檔export八筆Gitleaks findings已逐項SHA256內容核對為code-digest metadata誤判；證據repo外`SECRET-SCAN-TRIAGE.md`／`final-source-scan-hash-proof.json`。無secret輸出；未改規則／allowlist／history。分類證明不等於整體source/history/dependency/image clearance。
- **公開授權與來源**：共用boundary/UI為新寫，未複製的legacy shared license不作永久blocker；實際複製片段仍需逐檔provenance。Odoo Manage0.7.1 MPL-2.0對應源碼／NOTICE、OpenDesign原上游權利人、所有依賴SBOM/NOTICE及掃描待公開前審核。Repo不公開。
- **GitHub/GHCR**：公開lookup404不證明名稱可用。需安全供應最小publisher（優先ephemeral GITHUB_TOKEN）；不使用曝光PAT、不讀credential stores。沒有public push／publish批准。
- **真實測試後端**：需各類受限非正式key／DB身份；n8n不得操作正式workflow，write測試限owned fake或另准環境。EMQX既有HA error根因未明，不修／重啟；需可用REST API v5測試後端。LiteLLM版本／API權限、Hermes HA API、OpenDesign daemon port/auth待確認，不從Ingress猜API。
- **真實驗收**：HA安裝／Ingress／admin/non-admin撤權／同機與LAN client MCP E2E／backup/rollback／目標CPU RSS延遲需批准並實測。外部gate不停止內部下一批工具實作與逐批雙審。
