# W2b 工具功能擴展（有界，不是完整 migration）

目前 source universe **184**；支援 **55**、逐名延期 **129**。完整來源 signature/schema、接受 schema、effects、operation、grants、測試和剩餘工作見 `tool-surface.json` / `tool-surface.md`；人工逐名理由另存 `tool-review.json`。Python 是 pinned decorator/handler AST；不假稱條件註冊工具全部出现在 tools/list。本地 fake API 測試不是 HA／真後端／發佈驗收。

| 產品 | 原支援 → 現支援 | 新正常功能 | 尚未支援 |
|---|---:|---|---:|
| Odoo | 2 → 6 | res.partner 指定欄位 read/search/fields；token 預覽+confirm 的 chatter comment | 35 |
| Odoo Manage | 1 → 6 | res.partner 指定欄位 read/search；name create/update、record delete | 4 |
| Hermes | 5 → 7 | skill/toolset enable/disable、gateway restart；session metadata/delete、cron metadata/pause/delete | 4 |
| OpenDesign | 10 → 11 | 有界 run metadata；既有 project delete opt-in 保留 | 4 |
| EMQX | 3 → 11 | clients/topics/subscriptions、history/alarms；kick/subscribe/unsubscribe | 28 |
| LiteLLM | 2 → 7 | team metadata；有界 team create、alias update、team/model delete | 33 |
| n8n | 4 → 7 | pinned local node info、workflow minimal、folder list/create/rename | 21 |

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

任意 execute/method、agent/chat/code、成本/provider health 永遠不按名稱/hint 降為 read；本批未能安全限制者仍拒絕。`tool-review.json` 對每個延期工具列出確切技術阻礙和補強工作，包括更寬 Odoo 模型、完整 approval flow、私密檔案/trace/credentials、遠端 connector/agent egress 與 workflow 內容。不能把 55/184 宣稱七產品完整完成。

## 本地驗證契約

`tests/conftest.py` 自動持有 `/tmp/woow-ha-mcp-local-tests-<uid>.lock`；不要再外層 flock 或終止其他 listener。所有命令使用 `env -u SUPERVISOR_TOKEN PYTHONDONTWRITEBYTECODE=1`。writer 測試只能連 owned fake backend，明確允許才增加 mutation counter；unknown/extra/disabled/default deny 要保持 child/backend counter=0。

`test_native_probe_separation.py` 以兩個真實 native child、真正 policy API 和 owned fake backend 驗證 default／write-grant × probe-disabled／all-disabled：同 session 在 restart 前即拒絕、owned restart/reap、raw/private 與 public tools/list 分離、拒絕呼叫零 child/backend dispatch、internal monitor 實際 GET、健康 200／失效 503／恢復 200 且 PID 穩定；`test_expansion_native_restart.py` 經真正 policy API 由 readonly child 啟用 writer、重啟、實際 fake mutation、再停用；`test_expansion_runtime.py` 實際啟動七類 pinned runtime 並以同一 session 執行正反工具呼叫；`test_expansion_security.py` 檢查 grants、遷移、API callback 與 scope；`test_expansion_schemas.py` 用已鎖定 JSON-schema validator 驗證 conditional schema/default/normalized wire；`test_manage_module_adapter.py` 覆蓋 module REST 真傳輸拒絕/redirect/非 bool/error redaction。現有完整 suite 的 egress/stream/lifecycle/role 測試仍必須通過。

規格審查後仍需全新 security review；packaging OS guard、HA／真後端／影像／公開發佈 gate 沒有由本文件清除。
