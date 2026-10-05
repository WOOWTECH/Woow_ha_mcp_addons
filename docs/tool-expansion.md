# W2b 工具功能擴展（有界，不是完整 migration）

目前 source universe **184**；支援 **71**、逐名延期 **113**（BATCH2 B1 新增10；B2 新增3；B3 新增3與folder get操作，B3 待獨立 SPEC → NEW SECURITY）。完整來源 signature/schema、接受 schema、effects、operation、grants、測試和剩餘工作見 `tool-surface.json` / `tool-surface.md`；人工逐名理由另存 `tool-review.json`。Python 是 pinned decorator/handler AST；不假稱條件註冊工具全部出现在 tools/list。本地 fake API 測試不是 HA／真後端／發佈驗收。

| 產品 | 原支援 → 現支援 | 新正常功能 | 尚未支援 |
|---|---:|---|---:|
| Odoo | 10 → 13 | B2 partner schema catalog、自關係 metadata、required name/active 缺值統計；保留 B1 | 28 |
| Odoo Manage | 6 → 9 | 既有 partner CRUD；B1 active 分組 count、固定 template metadata、exact-grant internal note | 1 |
| Hermes | 5 → 7 | skill/toolset enable/disable、gateway restart；session metadata/delete、cron metadata/pause/delete | 4 |
| OpenDesign | 10 → 11 | 有界 run metadata；既有 project delete opt-in 保留 | 4 |
| EMQX | 3 → 11 | clients/topics/subscriptions、history/alarms；kick/subscribe/unsubscribe | 28 |
| LiteLLM | 2 → 7 | team metadata；有界 team create、alias update、team/model delete | 33 |
| n8n | 10 → 13 | B3 tags、execution metadata、service status、folder get；既有 B1/older 契約保留 | 15 |

## BATCH2 B3 n8n metadata reads（待獨立 SPEC → NEW SECURITY）

- 三個新工具名：`n8n_list_catalog` 僅 `kind=tags`、query<=256、limit1..250/default20。真 handler 固定一次 `/api/v1/tags?limit=250`，先驗最多250筆 id/name，再用原 filter/slice；回 scanLimit250、scope=first-page、hasMore。不是全catalog搜尋；不循環追cursor，不走projects／personal／official MCP。
- `n8n_executions` 僅 `action=list`、limit1..100/default20、includeData固定false（真API參數，不是取payload後才過濾）。cursor1..512、workflowId/projectId1..128 ASCII segment、明確非personal project、status僅success/error/waiting；optional欄位需省略而不是null。單次 `/api/v1/executions`，只回 id/workflowId/status、有限ISO timestamps與cursor；get/run/retry/delete不授權。
- `n8n_health_check` 僅 `mode=status`（default）。真 handleHealthCheck/client.healthCheck，先同backend derived `/healthz`，失敗才真 `/api/v1/workflows?limit=1`，最多兩GET。只回 status=ok、scope=service-availability、authentication=not-verified；服務可達不是key權限證明。source-guarded版本/settings、npm registry global fetch、official-MCP建構/transport在發生DNS/connect前停用；沒有假造backend成功。diagnostic、URL/config/env/metrics/versionwarnings不開放。既有 credential HealthMonitor probe 不改。
- 既有 `n8n_manage_folders` 只新增 `get` readonly operation：明確非personal projectId和folderId；一次 `/api/v1/projects/{project}/folders/{folder}`，正向bounded id/name/parentFolderId/ISO timestamps/projectId，不帶workflows。舊list/create/rename、預設personal、writer grants不改，move/delete仍deny。此操作不增加工具名count。
- 新路徑每HTTP最多64KiB解壓body、5秒socket/total transport deadline、零redirect與零新增retry；health最多兩次5秒HTTP（既有DNS policy不变），非整個工具5秒保證。原client auth、DNS全答案驗證、pin/TLS/origin不變；舊七API成功identity、retry/settingsfallback不改。新bounded投影拒絕key/URL反射與非法metadata；不是任意business content的通用DLP。
- **明准shared policy例外**：Tool新增default-OFF `requires_backend`／`backend_required_operations`，僅三新API及folder:get opt-in。驗參數後、修改wire前檢查現有ProductState.configured；legacy State需URL+key兩者。gateway早期與fresh presend共用authorize，缺任一配置均零child send/RPC，拒絕不更改caller args。沒有gateway名稱特例或state migration。**不是零child startup**：n8n原有unconfigured本機docs/search/validators啟動照常，tools/list/initialize/ping/filter_list語義不變。
- `tests/test_b3_n8n_{policy,runtime,boundaries}.py`：schema/runtime/private parity、真owned ChildSpec與API paths/params/call budgets、genuine handler/client identity、auxiliary fetch/DNS/connect spies、partial configs、fresh presend clear、收到dummykey之error/body/metadata canaries。B3 source guard在載入前驗server/manager/API/error及catalog/official/npm helper。無依賴/UI/HA/lifecycle或其他adapter變更；須獨立SPEC後不同NEW SECURITY，不自我approve。

## BATCH2 B2 Odoo 有界 metadata／品質統計

- `schema_catalog` 固定 `models=["res.partner"]`、query=null、limit=1，include_fields/refresh 為 boolean。真 handler 的 client facade **先限制實際 RPC**：`ir.model.search_read([["model","=","res.partner"]], fields=["model"], limit=1)`；不使用上游全模型 search/read，不取名稱。fields_get 明確指定 id/name/display_name/active/parent_id/child_ids 與 type/required/readonly/store/relation，正向驗證後才交給 handler/cache。SDK model label 僅空預設值，非後端 label。Cache 至多兩個 key（include_fields），依 lifespan/真 client identity 隔離；憑證改動由既有 lifecycle 更換 process。命中仍核對 source；refresh=true 重新查詢，無 TTL／自動新鮮度承諾。
- `inspect_model_relationships` 必須 live metadata、res.partner、fields_metadata=null、use_live_metadata/include_computed=true；include_readonly 可選。只回上述六個欄位與 parent_id/child_ids 的 res.partner 自關係 metadata，深度1；不取 compute expression、label/help/context/default/selection，移除 create/write hints。這不是 record 值或 relation 展開授權；既有 read/search fields 不擴張。
- `data_quality_report` 只開 `checks=["missing_required"]`、`key_fields=["name"]`、sample_limit1..100（default100）。真來源演算法取得 **name/active 的 type/required/store metadata**，最多兩次 `res.partner.search_count([[field,"=",false]])`。只回 counts/固定 field identifiers，無 record samples、IDs、values；sample_limit 保留上游 envelope，但這個 check 不抽樣。統計按後端 ACL／預設 active context，是各 required stored 欄位缺值次數之和，不是唯一 records；若無可見 required fields，真結果明示 fields_checked=[]。任一 nested error 全體回固定失敗，不偽稱 clean。
- duplicates 的來源 read_group 無 limit；任意加 limit 會扭曲全量統計，因此該 check 仍拒絕。format_anomalies 需 email/phone/vat，orphaned_references 需 relation values/IDs，同樣不開放。不承諾完整品質工具。
- 每次先驗參數/source、XMLRPC scope/DNS/TLS/redirect 與既有 single-worker/cancellation 保持；成功只取正向 metadata/statistics，source 捕捉的 nested error 與 malformed metadata/count 都轉固定 `BACKEND_RESPONSE_INVALID`，不回 raw backend context/key。0.1.2 起，工具整體失敗且錯誤**恰好**是傳輸層固定碼（`BACKEND_RPC_FAULT`、`BACKEND_TIMEOUT`、`BACKEND_UNAVAILABLE`、`BACKEND_BUSY`、`BACKEND_DESTINATION_DENIED`、`BACKEND_STREAM_ERROR`、`BACKEND_INVALID_RESPONSE`、`BACKEND_HTTP_ERROR status=NNN`）時照實回該碼（例如帳號沒有 `ir.model` 讀取權限時 `BACKEND_RPC_FAULT`）；其他文字一律仍是 `BACKEND_RESPONSE_INVALID`。三工具 default readonly，disabled/unknown/extra/跨 instance 仍拒絕；六類 production HA 管理仍 fail closed，無新 permissions/UI。
- `tests/test_b2_odoo_{policy,runtime,scope}.py`：公開 JSONSchema/runtime/private validator parity、真 owned child 的精確 XMLRPC、genuine source invocation、正結果與 error canary、有限 cache/generation/source-drift、逐工具 cancellation/BACKEND_BUSY、disabled 零 RPC、未設定不 spawn/probe、動態 UI advertisement。僅本地 fake backend 證據；獨立雙審／image／HA／真後端 gate 不因此解除。

## BATCH2 B1 有界正常功能

- Odoo `build_domain`：最多10個 typed partner conditions（id/name/display_name/active）、and/or；無 metadata/context。`generate_json2_payload`／`diagnose_odoo_call` 僅 res.partner search_read/search_count、有限 kwargs；args/base_url/database/error/metadata 不開放，debug/live metadata=false。真 pinned handler 純計算，永不執行生成 JSON2；placeholder API key 不是秘密。生成 OR domain 也不使 search_records 的有限 conjunction 契約放寬。
- 兩種 `aggregate_records`：僅 active 分組、id:count、limit1..100（default10）、offset<=10000，既有有限 domain、無 context。source handler 依版本使用 read_group/formatted_read_group；新增 source-guarded output adapter 只回 active/id:count/__count，去除 drilldown domain/context/任意欄位；不是原始財務／私人欄位彙總。
- Manage `list_resource_templates` 回四個固定本機模板與有限 partner 可見性，**resources/read 仍禁止**。`post_message` 是 writer，獨立 exact grant；module 必須已存在、後端 write ACL 必須允許。只允許 plain internal note（mail.mt_note），message_type=comment、無 recipients/attachments/HTML。後端自訂 override 仍可能通知或有其他副作用；不宣稱絕無通知。
- n8n `validate_node`／`validate_workflow` 是本機 pinned DB validator；僅 manualTrigger/noOp 空參數，圖2..20 nodes、有界 typed main connections，拒絕 prototype keys、重複/未知 node references、credentials/code/URL/settings。mode/profile/options 保持來源 defaults。
- `n8n_create_workflow` 需要 exact grant（舊 global=true 不授權），只對相同安全圖呼叫既有 scoped POST /workflows，建立 inactive draft；沒有 activation、existing workflow update、project/folder override 或 execute。API 回應僅接受有界 id/name/active=false/nodeCount；異常回應拒絕**不代表已提交寫入回滾**。inactive 語義依 pinned create API 契約，真後端版本仍需驗收。
- 本批無新 network client/任意filesystem path、依賴、UI 契約、六類 HA role 權限；使用既有 adapter、v3 exact grants 與真管理 metadata。counts 是工具名，不是全 operation parity。更寬 Odoo metadata/quality、其他 node config/get_node modes/catalog/folders 等是可接續內部實作，不是缺 credential 的外部 blocker。

### B1 writer error boundary（P1 修復，待獨立複審）

- n8n create 在既有真 API client reject 後、真 handler 格式化之前，僅由 source-guarded `N8nApiError` 的 status/code 產生固定 public error；不回傳 backend message/details/exception 字串。400/401/403/404/429/5xx 分別保留 validation/auth/forbidden/not-found/rate-limit/server 類別，無回應為 `NO_RESPONSE`，未知失敗為 `BACKEND_UNAVAILABLE`；成功但 metadata 不合法為 `BACKEND_INVALID_RESPONSE`。不更換 cleaner、handler、DNS/TLS/redirect 規則。
- Manage 保留真 post handler 與 module write ACL。對 `res.partner.message_post` 真 `execute_kw` 回傳先驗證 ID，再讓原 handler 處理，避免原 list→首元素 coercion 掩蓋 bool/多元素/無效 ID。只接受 int 1..2147483647 或單元素同型 list；成功僅輸出 success/message_id。外層依型別與有界 explicit cause chain 回固定 `BACKEND_INVALID_RESPONSE`／`BACKEND_ACCESS_DENIED`／`BACKEND_UNAVAILABLE`，不檢查錯誤文字，取消與 process signals 不攔截。既有 XML transport 將 RPC fault 轉固定錯誤後，原 connection wrapper 已無可安全區分的 fault code；此處誠實歸 unavailable，不從文字猜測。
- **錯誤不是 rollback／exactly-once 保證。** malformed success、HTTP 5xx、斷線或 RPC fault 都可能在 backend commit 後發生。n8n 既有 client 仍會對特定 preconnection error 做最多3次 retry；POST 不重試 ECONNRESET/timeout，但 cleaner 自帶 settings 的特定 HTTP400 rejection 可觸發既有 settings fallback，再 POST。owned test 實證此路徑兩次 POST、一次 fake commit、最終固定 server error；本修復未新增 retry，也不宣稱所有失敗只有一次 POST。不要自動重送未知結果的 write。
- `tests/test_batch2_writer_errors.py` 使用 OS ephemeral loopback ports 與每次 child HTTP 前 own-PID/fd/LISTEN proof；真 pinned handlers 收到 fake backend **實際收到的 dummy key** 反射錯誤／malformed return，raw MCP SSE/text/JSON 與 decoded structured content 不得洩漏。另有 genuine positive mutation、default-off/legacy-global/同 session revoke/disable、post-error committed counter 區分。`test_batch2_writer_boundaries.py` 補 source-drift、no-stringification、取消傳播契約。這些不是實際 HA、production 或 full-suite 驗收。

### n8n enabled API public errors（相鄰既有 P1，待 SPEC → NEW SECURITY）

- 獨立 review 證實：沒有 writer grants 的 `n8n_list_workflows` HTTP404 會把 backend 實際收到的 dummy key 反射到 public error。這是既有 read-path 問題，不是已核准 B1 writer 修復造成；現在以 test-first raw MCP SSE regression 修復。
- `backend_policy.cjs` 在載入 runtime 前嚴格核對 API client、error mapper/formatter、manager handlers、server dispatch 四個 digests。只包住七個**真 handler**：workflow list／get minimal／delete／create，folder list／create／rename。shared formatter 僅依 typed status／known code 產生固定訊息；每個 invocation 的 AsyncLocalStorage 只記固定 public classification，不記 raw error。handler 完成後，失敗統一為 `{success:false,error,code}`，不读取原 error/message/details/stack 或 stringify；一般 raised error／非 typed failure 也不洩漏。403 不再帶 publish-shaped backend 訊息，folder hints 也不轉傳。
- 400/401/403/404/429/500..599 → `VALIDATION_ERROR`／`AUTHENTICATION_ERROR`／`FORBIDDEN`／`NOT_FOUND`／`RATE_LIMIT_ERROR`／`SERVER_ERROR`；typed `NO_RESPONSE` 與既有 create `BACKEND_INVALID_RESPONSE` 保留，其餘 `BACKEND_UNAVAILABLE`。writer 固定提示結果可能未知，先確認再重試。API mapper 的 raw errors 保留到 public boundary；cleaner/settings fallback、preconnection retry、folder personal resolver 的 `/projects`→`/workflows` fallback 均不改。
- **成功 business strings 不是 error diagnostics；這不是通用 DLP。** 原 success projection、folder name/ID 語義、delete 空回應成功語義、grants、65 tools、DNS/TLS/redirect policy 均未擴張或重新設計。尚未允許的 handlers 仍 withheld；不宣稱所有 upstream 日誌／任意成功內容都已清理。
- `tests/test_batch2_n8n_public_errors.py` 以真 source handlers、owned fake backend 實際收到的 invented key、私有 OS-ephemeral runtime 驗證所有七分支及 personal resolver，raw MCP SSE/text/JSON（含任何 structuredContent）不得洩漏；default-deny／同 session revoke-disable 必須零 child/backend dispatch。另驗證讀取、folder、delete 成功輸出不變。`test_batch2_n8n_public_boundaries.py` 補四個 before-load drift negatives、formatter 不讀 private getters／不變更 raw errors、真 handler ordinary/AbortError failures 與並行分類隔離。既有 B1 writer commit/fallback/cancellation/positive cases 必須重跑；不是 full-suite／HA／release approval。

## v3 狀態／管理 API（已本地串接 UI，HA 未驗收）

`ProductStore` 在獨占 writer lock 下把完整有效 v1 n8n／v2 product 狀態遷移成 v3。backend、token/child_token、endpoint、disabled、writes_enabled 原樣保留；新增 `enabled_write_tools=[]`。損壞、缺欄、未來版本、錯產品或未知/重複 grant 不重寫。舊 executable 回復需相容的受保護備份，不直接降 schema version。

新的 writer 不繼承 `writes_enabled=true`。**只有原有 `n8n_delete_workflow` 與 OpenDesign `delete_project` 保留舊開關語義**；它們也可用 exact grant。新 API 的 grants 是取代整個清單，不是追加。未送 grants 的舊 API 保留現有 grants；`writes_enabled=false` **不是**撤銷新 grants，撤銷請送 `enabled_write_tools=[]`。`disabled` 永遠優先。

管理員通過原有 HA role + CSRF 檢查後：

```json
PUT /api/policy
{
  "writes_enabled": false,
  "disabled": [],
  "enabled_write_tools": ["hermes_skill:disable", "hermes_session:delete"]
}
```

每個產品只能選自己的已支援 exact tool 或 `tool:operation`。`GET /api/bootstrap` 回傳目前 grants 與每工具 `write_grants`、`operation_parameter`、`legacy_write`、`inputSchema`，並宣告 `policy_contract:"woow-v3-exact-grants"`。
共用 UI 已接此實際契約：顯示精確 grants／legacy global 有效授權，保存取代全部 grants 並 global false；
未知契約或 fresh bootstrap 發現授權／工具定義變更時阻止保存，不做 legacy fallback。未知 action/operation、未知欄位、跨 instance、ctx/client 注入在 child dispatch 前拒絕。mixed 工具列表可包含 writer enum，但**列出不等於授權**；每次直接呼叫（含現有 session）重讀狀態。

僅 n8n 安裝已核准的正式 HA role provider；其他六類 production 管理 API 繼續 fail closed，沒有新增 provider/權限或繞過。測試注入 role 僅為 local API/lifecycle 驗證。

## 原生 runtime gating 與生命週期

- EMQX/LiteLLM 啟動使用固定 source name universe；未支援、未授權 writers 與 public disabled 工具送入原生 disabled_tools，**唯一例外是固定 internal read probe**：EMQX `emqx_cluster_status`（GET `/api/v5/nodes`）／LiteLLM `litellm_list_models`（GET `/v1/models`，不用 provider `/health`）。兩個 probe 都無 client arguments、無 writer/operation 分支；沿用 reviewed handler、同一受限 backend client 與 response validation，不新增網路路徑。private loopback child raw tools/list 因此刻意保留 probe，即使所有 public 工具 disabled；這不是 public tool 授權。parent `authorize`／`filter_list` 仍即時隱藏並 403 拒絕 disabled probe（含原 session），不發 child/backend request。沒有有效 writer grant 時 native readonly=true；存在精確有效且未 disabled writer 時才 false，其餘 writers 仍逐名禁止。LiteLLM handler `require_operation` 保留。HealthMonitor 真正執行 internal read；backend outage 仍是 unreachable／readiness 503，不以 public disable 偽造健康或啟動 restart。
- FastMCP banner/update check 明確關閉（`FASTMCP_CHECK_FOR_UPDATES=off`、`FASTMCP_SHOW_SERVER_BANNER=false`）。原預設會訪問 PyPI 並寫版本 cache，導致 clean-CWD 重啟被拒絕；現在保留原有空目錄／symlink 拒絕，不自動刪除檔案。先前版本若留下 cache，仍需管理員確認後離線恢復乾淨目錄。
- 兩者 policy PUT 先持久化當前 gate，再由既有 owned lifecycle callback 停止／重啟 child；disabled 於重啟等待中已阻止新 direct call。啟用操作可能需要 client 重新 initialize；不保證舊 child session 跨重啟有效。callback 沿用取消／disconnect 後 join 的 ownership，沒有 detached task。
- Manage writer 必須顯式配置 `connection.mode="module"`，連到**已安裝**的 MCP module。原生 mode=off 與後端 ACL 決定可寫權限；不啟用 full YOLO、不安裝/變更 Odoo backend。`mode="read"` 不能保存 writer grants。
- Manage module 的 auth/ACL 原本走 urllib；新 source-guarded launcher 將這兩條固定 REST 路徑導入既有 DNS-pinned HTTPX adapter，API-key-only，嚴格 consumed bool/user ID，沒有 session/password/redirect fallback。

## 輸出與安全界限

所有新 HTTP/RPC 呼叫沿用固定 origin/path、所有 DNS answers 驗證及 pin、metadata/redirect/proxy 拒絕、TLS、錯誤清理與既有非同步容量界限。Odoo XML-RPC 同步工具仍由有界 worker 執行；wheel 本身未修改。新的 native write 不是新 HTTP client。

新 session/cron/run/team metadata 用正向 scalar projection：最多 100 筆、每字串 256 字元，拒絕錯誤 envelope，去除未知／巢狀欄位。session messages、cron prompts、team keys/members/private metadata、run paths 不回傳。這**不是任意文字秘密清理器**；欄位內的人為商務內容仍屬該後端可見資料。既有 W2a 成功輸出契約未全面重新設計。

Odoo 家族僅 `res.partner` 的 id/name/display_name/active，必須明確指定 fields；domain 僅有界 conjunction，沒有 dotted relation/context/free-text 搜尋。寫入 name 或經确认的 chatter；chatter comment 可能通知既有訂閱者，是明確 writer 而非 read preview 授權繞過。後端自訂 computed fields/overrides 仍需最小權限帳號與實際相容性驗收。

任意 execute/method、agent/chat/code、成本/provider health 永遠不按名稱/hint 降為 read；本批未能安全限制者仍拒絕。`tool-review.json` 對每個延期工具列出確切技術阻礙和補強工作，包括更寬 Odoo 模型、完整 approval flow、私密檔案/trace/credentials、遠端 connector/agent egress 與 workflow 內容。不能把 71/184 宣稱七產品完整完成。

## 本地驗證契約

B1 `tests/test_batch2_{policy,bounds,runtime}.py` 覆蓋10個真 handler、18/19版 owned XML-RPC、pure calls 零 backend events、nested/prototype/schema 拒絕、兩個新 writer 舊 global deny→exact grant→同 session disable/revoke，且拒絕時零 child dispatch/副作用；Manage write ACL deny、resources/read deny、count response canary projection。

`tests/conftest.py` 自動持有 `/tmp/woow-ha-mcp-local-tests-<uid>.lock`；不要再外層 flock 或終止其他 listener。所有命令使用 `env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1`。writer 測試只能連 owned fake backend，明確允許才增加 mutation counter；unknown/extra/disabled/default deny 要保持 child/backend counter=0。

`test_native_probe_separation.py` 以兩個真實 native child、真正 policy API 和 owned fake backend 驗證 default／write-grant × probe-disabled／all-disabled：同 session 在 restart 前即拒絕、owned restart/reap、raw/private 與 public tools/list 分離、拒絕呼叫零 child/backend dispatch、internal monitor 實際 GET、健康 200／失效 503／恢復 200 且 PID 穩定；`test_expansion_native_restart.py` 經真正 policy API 由 readonly child 啟用 writer、重啟、實際 fake mutation、再停用；`test_expansion_runtime.py` 實際啟動七類 pinned runtime 並以同一 session 執行正反工具呼叫；`test_expansion_security.py` 檢查 grants、遷移、API callback 與 scope；`test_expansion_schemas.py` 用已鎖定 JSON-schema validator 驗證 conditional schema/default/normalized wire；`test_manage_module_adapter.py` 覆蓋 module REST 真傳輸拒絕/redirect/非 bool/error redaction。現有完整 suite 的 egress/stream/lifecycle/role 測試仍必須通過。

規格審查後仍需全新 security review；packaging OS guard、HA／真後端／影像／公開發佈 gate 沒有由本文件清除。
