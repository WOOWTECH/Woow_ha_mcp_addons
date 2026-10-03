# W2 執行細分（承接 W1 雙審，不另訪談）

## W2a：七類 runtime 契約與六類 adapter

循序一個 worker 寫共用檔。根據 repo 外已完成 `adapter-contracts.md`（完整 source hash/安全 tool/action/entrypoint）、legacy/emqx-litellm 報告實作，不重複全量 scout。

- 保留一組 backend/每 app，型別化 product config；不要用任意 command/env/credential dictionaries 回復 legacy 風險。若擴 schema，明確 migration 保留 n8n v1 token/backend/policy，future/incorrect-product state fail closed，migration/rollback tests。
- 六類須 real upstream runtime，不做假工具回應或空 adapter。Odoo 1.1.0 與 Manage 0.7.1 已核對 native Streamable HTTP/stdio；Manage 無 module server singleton。優先固定 loopback native HTTP，避免不必要新 bridge。
- Hermes/OpenDesign 僅 allowlist 必要 runtime source，保留 app MIT notices/provenance。移除 legacy 私有預設主機/預設 credential，未配置即 truthful unconfigured。不要複製舊 admin/auth/UI/K8s/.env/.git。
- EMQX/LiteLLM 來源已找到 full pinned commits；只拉必要 `.py` runtime/license/metadata，不複製 examples/deployment/auth config。保留來源內容hash與修改記錄，不宣稱取自現行 image。
- Standalone FastMCP3.4.5 需 slim extras/Starlette>=1.0.1，若與 core lock 不合，獨立每 app child venv/lock，不能盲目升 core 或假裝依賴已可用。uv isolated 本地安裝允許；不能 system-wide/production 安裝。
- 固定 argv/env/clean CWD，限制 child 直連只 loopback；Supervisor token 永不傳 child。每類 backend health 用實際 read-only語義，不只 PID/TCP 或 generic success；缺 backend credential 呈現 unconfigured。
- 測本地真实 runtime initialize/initialized/tools/list 及無後端 safe call 或 fake-backend call；無憑證需要阻擋的 Manage initialization 明示，不以 mock算真實。
- 完整盤點 pinned upstream tool surface（AST/real tools-list 區分）→ 支援/read/write/mixed/暫不支援理由，新增 drift tests。不得以少量 read工具宣稱完整類別。

## W2b：功能完整性／政策擴展

- 依 `tool-surface-acceptance.md` 補齊 n8n 上游及六類已核准功能；對可直接由 source證明且有mock正反測試的 read/write工具提供明確管理員啟用路徑。
- Mixed-action 逐參數 gate，generic arbitrary execution/secret read/file traversal 等未能安全界定者逐名明示未支援和補強需求，不能 default allow；也不能不列清單而偷偷移除。
- 支援 schema 與真正 handler/normalization/default一致；所有寫入預設關閉；unknown/disabled/direct call 不得到 child/backend。
- 測試真實讀取或寫入只能對 disposable fake backend；原生 runtime docs/health safe calls 與 production E2E分開。

## 每次交付 gate

worker 報告 RED/GREEN 命令+exit、artifact/授權、檔案/未完項；coordinator 先 spec reviewer，再全新 security reviewer；缺陷交修，不以 test count代替 review。

W3 共用 Woow UI／七 manifests／CI／文件與 local image-build feasibility 隨後接續。來源/工具 completeness若仍有缺口，MILESTONE 必須逐類標示，不能宣稱完整七產品驗收。
