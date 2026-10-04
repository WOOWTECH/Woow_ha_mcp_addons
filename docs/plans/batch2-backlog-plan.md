# 第二批：內部工具 backlog 與隔離驗證

上游已接受`f746b9402ce6ce6d29a62fcacecaabad8036a026`第一批55工具里程碑並解除停止點。**整體任務未完成，不重訪產品範圍，不把內部backlog全部說成外部障礙。** Historical MILESTONE／team-evidence.final不是當前完成宣稱。

## B1：已完成有界實作與雙審

新增10工具，現**65/184支援、119延期**：
- Odoo：build_domain、generate_json2_payload、diagnose_odoo_call、aggregate_records。
- Odoo Manage：aggregate_records、list_resource_templates、post_message。
- n8n：validate_node、validate_workflow、n8n_create_workflow（bounded inactive manualTrigger/noOp draft）。

真source handlers、exact new-writer grants、unknown deny保留；schema及兩writer錯誤邊界修復均獨立SPEC→NEW SECURITY。另確認的既有n8n readonly error P1已修目前7個enabled API公開error邊界，不改成功output／內部retry/fallback；174focused及独立owned probes雙審。未沿用無結果的abandoned probe。

## BT1：已整合、coordinator新回歸通過

從MAIN262來源snapshot＋已審8檔sync隔離；逐步遷移legacy real child、health、raw、actual executable、UID10001/nondumpable joined及browser/Node路徑。Production3000不改，未知3000不bind/connect/probe/kill。三個歷史B1交集為明准test migration surfaces，原斷言保留。

修復過程依次發現並關閉：forwarding併發造成人工503、fulfilled redirect繞proof、terminal IPC coalesced frame放行，以及standalone Playwright prelaunch／per-send缺proof。各有實際owned RED→GREEN及獨立SPEC→NEW SECURITY；完整記錄在repo外worker/review報告，不以green count抵銷finding。

最終284-file snapshot全新security批准後，重建`bt1-approved-integration-files.json`，MAIN20既有baseline與20新目的檔均精確核對，**40個test/config檔已整合**，production／既有治理更新未覆蓋。舊pendingmanifest已淘汰，不作整合依據。

Coordinator於MAIN串行新跑：**792Python＋獨立joined1＋65packaging＋13UIunit＋21browser**，零failure/error/skip；validator/actionlint/inventory/offline locks／syntax／既有assetclosure全exit0。Own PID/PGID/deadline/cleanup有record，沒有deadline signal。`coordinator-bt1-main-verification.json`為新證據；之前636/731/739/756/774 worker／reviewer數字仍只作歷史。

歷史empty90s timeout、REDUID-child及失敗UI probe Node4153791 descendant cleanup缺口仍unknown；不倒推、不掃殺外部PID。Current freshcleanup與reviewer adversarial cancellation證據分開保存。Test proof/send仍非原子、Playwright1.61.1 seam非通用sandbox。

## B2：Odoo 有界讀取已完成雙審與新回歸

新增三個真pinned handlers，**68/184支援、116延期**。P2 source-drift cache清除修復後SPEC重審及全新SECURITY批准；coordinator新跑804Python＋独立joined1＋65packaging＋13unit＋21browser，零failure/error/skip，source/provenance/inventory/locks／其他靜態檢查過。17delivery hashes保持已審值，證據repo外`coordinator-b2-main-verification.json`。

已落實契約：
- `schema_catalog`：res.partner固定model/query/limit，實際ir.model.search_read精確domain／fields／limit1；六欄位正向fields_get。每client/lifespan兩cache variants；source-drift／failed refresh清空，恢復freshRPC；無URL/database/context／backend labels。
- `inspect_model_relationships`：live-only六個欄位metadata，parent_id/child_ids僅self res.partner、depth1；保留真algorithm counts／readonly filtering，不開放相關records values或compute expressions。
- `data_quality_report`：僅missing_required、name/active的type/required/store metadata與最多兩次精確search_count。保留真field-occurrence sum，不是unique-records／sample scan／DB工作上限；無私人sample，duplicates/formats/orphans仍deny。

## B3：n8n有界讀取已完成雙審與新回歸

`n8n_list_catalog`僅tags public API first-page250；`n8n_executions`僅API includeData=false的list metadata；`n8n_health_check`真healthz／workflows fallback，最多2GET、scope僅service-availability/authentication-not-verified，npm/version/settings/official輔助路徑invocation-only拒絕；既有folder增加get readonly、explicitnonpersonal IDs，不增move/delete grants。三新名字＋一operation，現**71/184、113延期**。

明准shared `policy.py`例外：Tool backend requirement defaultoff，只新三API及folderget opt-in；strictnormalize/grants後、兩次authorize均檢查configured，旧n8n unconfigured native/local tools保留。Unicode P2已改early-exit codepoint計長，public256不縮小，24新regressions及原重現過；SPEC→不同NEW SECURITY批准整份295state。Coordinator新**891Python＋獨立joined1＋65packaging＋13unit＋21browser**／static全過、零failure/error/skip；證據`coordinator-b3-main-verification.json`。

## B4：下一組EMQX營運metadata（候選，尚未交付）

八個source-backed候選：`emqx_get_client`、`emqx_client_subscriptions`、`emqx_node_detail`、`emqx_get_rule_metrics`、`emqx_list_rules`、`emqx_list_connectors`、`emqx_list_actions`、`emqx_list_listeners`。保留真pinned handlers及GET路徑，先精確identifier／欄位／numeric-status／page-call／stream-body契約，再test-first；正向metadata投影，不回私人session／IP/username／SQL／credential／URL／TLS config／payload。新工具使用已審default-off backend requirement opt-in，不改generic policy。缺pagination的來源不得暗示完整掃描，超budget拒絕或明確bounded view，不任意while-loop。

候選不得先標supported或fake handler／合成成功。B4不開authn/authz、ban/unban、publish、rule toggle/test SQL、trace、retained payload或外部連線能力。若某來源路徑不能安全保留，逐項說明並保持deny，完成其他可實作項；不重新整庫scout或整批停在報告。

本批不開任意method/code/agent、cross-instance、HR/財務資料、attachment、local index或async job權限。後續n8n metadata/folder等常用工具繼續依逐名source/effect契約排批。

## BLD1／BLD2與外部gate

唯讀preflight完成：usernamespace可行性未證明，並非實測kernel拒絕；未安裝／daemon／mount／socket／升權。專用disposable private amd64 runner最小請求在repo外`UPSTREAM-BUILDER-REQUEST-BATCH2.md`。

BLD2九檔pipeline契約proposal雙審／65mock-package通過，已合MAIN；embedded docker driver、hash-before-execution、helper/proxy隔離。Current USER-owned hosting缺必要runner-group保護，hardBLOCKED；env/labels不能繞過。Hosting／VM／software／egress／資源另待批准，沒有實際image builder操作。

## 不變契約與節奏

- Default readonly、新writer每tool/operation exact grants；兩legacy例外不擴、disabled優先、unknown拒絕。
- 真SDK/handler、v3 migration、fresh HA role、postcommit lifecycle、OSguard、UI契約及七packaging有效write-denial probes保留。
- 同backend scope、DNS pin/TLS/redirect/error redaction、bounded output/work ownership；全read/RPC/async路徑都須審查。
- 每交付獨立SPEC，之後全新SECURITY；fix後重驗，不自行approve。
- 每bash／診斷／test command explicit timeout；長job own PID/PGID與boundedcleanup；不輪詢agent，不猜pending結果。
- 最多3active、共用production一writer；並行只在隔離worktree且檔案scope明確不交集。
- 公開push／source-license／secret／image／HA／真backend gates closed；僅n8n HA API例外，六類仍failclosed。External gate不停止內部backlog，71工具不是整體done。
