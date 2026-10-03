# 本地整合里程碑工作單（待 component 雙審後）

已合入 reviewed packaging 86 newfiles + UI 15 sourcefiles，這只是無覆寫檔案整合，不是 runtime/HA驗收。W2b55-tool slice 還在審查；所有core修改等其review完成或修復安全窗口。

## 1. 真實管理UI串接

- UI現在是isolated frontend，MOCK explicit-grants-v1 proposal不能直接當main契約。對齊main v3 `enabled_write_tools`、每tool `write_grants`/`operation_parameter`/`legacy_write`/`inputSchema`。
- 明確辨識已核准新契約；失配failclosed，不能用legacy fallback保存導致隱藏仍有效grants。顯示原2legacywriter有效授權，儲存逐tool/op精確grants並`writes_enabled:false`，disabled優先，unknownaction不選。
- Manage form需支援read/module且說明module必須既有、不安裝Odoo。由實際bootstrap schema決定，不虛構credential。
- 管理listener新增受trustedpeer+realHArole保護的HTML/assets/固定4route historyfallback，正確trusted Ingress prefix/template替換、APIbase、no-store/CSP/nosniff/referrer、避免阻擋HA同originiframe。不使用Host/window.origin推測MCP endpoint。
- assets/static禁止traversal/symlink/data洩漏；MCP listener不得有管理UI/API。missingbuild truthful unavailable，不能serveMOCKfixture。

## 2. 打包串接

- 七Dockerfile加pinned Node frontend buildstage，自host完整dist/fonts/MDI/licenses進每個獨立image；保持rootcontext、selected runtimeclosure、nonroot/data/guard、amd64pin。
- .dockerignore白名單僅必要UI buildsource，不入fixtures/browserreports/node_modules/localdata。
- 現packagingprobe是v2/27-tool snapshot；更新v3migration/55工具與全部每產品supportedwrite有效args＋counter0，不能老fixture假通過。
- 更新docs/README/addonDOCS/changelog目前counts、mode/grants、provider已實作已審vs HA未測；不把所有129延期當外部不可解blocker，保留後續功能工作。
- 本機無Docker：仍不得宣稱七imagebuild/containerruntime已過；可驗證所有fixture與script真實可執行邏輯、缺工具正確deny。

## 3. 聯合本地驗收

- 真實packaging bootstrap→postexec/prechild guard→實際n8n executable→實際fixedWS provider，只有private testtransport+Ingress socket simulation，dummy machine token不進state/argv/log/child，sameUID child procfs/mem讀取被拒。不得新增production testhook/URLoverride/allowallrole。
- Chromium連真實core routes/API（非原nodefixture），rolequery接ownedfakeWS，驗證owneradmin/nonadmin/demotion/errors、CSRF、prefix/refresh/fonts、forms、endpoint、rotation與pertool/opgrants；仍標LOCAL/MOCK不是HA。
- 全部Python/runtime回歸、UIunit/browser、packagingvalidator/tests/actionlint、sourceguard/inventory/NOTICE/hygiene聯合重跑；固定3000測試序列，長suite勿讓第二process超過lock120s。
- 整合worker交付後獨立spec→全新security；未修finding不得完成。

## 里程碑報告必須分層

程式/本機realchild+fakebackend測試、UI真browser但fakeHArole、映像NOTBUILT、HA NOTINSTALLED/NOTTESTED、productionMCP E2E NOTVERIFIED。列55/184有界支援与129剩餘工作（以最終inventory為準）、其他6管理role權限未擴、來源授權/掃描policy/建置工具/憑證等gate。最後停本地等待上游，不公開push、不改既有服務。
