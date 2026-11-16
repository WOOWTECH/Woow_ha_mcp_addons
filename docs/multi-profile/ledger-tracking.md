# 帳本列管清單（多帳號新模組）

- 狀態：HM-00 定案（2026-11-14；計畫 §11.1、C4-SF-13：新模組全部列管）。2026-11-15 文件同步：第 1～3 節照 `claude-delivery` `9c5dd88`
  （HM-01、HM-04、HM-17、HM-07、HM-06 已合併）的帳本逐檔核對。
- 帳本：`docs/provenance/runtime-patches.json`（bb48449 列管 50 個檔；`9c5dd88` 列管 54 個，多的是 HM-07 的 `features.py`、`profiles.py`、
  `identity_fields.py`、`config.py`）；工具面：`docs/tool-surface.json`、`docs/tool-surface.md`。

## 結論

1. 下表的新模組，**建立它的那一片**就在同一個 PR 把它加進 `runtime-patches.json`；之後每一片改到它都要更新摘要與說明。
2. HM-00 不改帳本：這些檔還不存在，先列進帳本會讓 `tests/test_tool_inventory.py` 失敗。
3. 動到 `apps/runtime/*.py` 或 `apps/*/launch.py` 的片要重產 tool-surface。

## 1. 新模組

| 模組 | 建立的片 | 之後會改的片（照合併順序） | 帳本 | tool-surface | 用途 |
|---|---|---|---|---|---|
| `packages/mcp-admin-core/mcp_admin_core/features.py` | HM-07 | 每個產品的升版片（加產品；受發版鎖）。HM-17 沒改它：HM-17 先合併，那時這個檔還不存在 | 列管（HM-07 起） | — | 產品開關 `MULTI_PROFILE_PRODUCTS`；`enabled(product)` 呼叫時讀 |
| `packages/mcp-admin-core/mcp_admin_core/profiles.py` | HM-07 | HM-13a（還原標記的檔名常數；還沒合併）→ HM-09 → HM-10 → HM-31（只改註解）→ HM-13b（隔離名稱不覆蓋、守門的移開名稱）→ HM-25 | 列管（HM-07 起） | — | 索引、簽章、布局、一致性、容量常數、名稱規則、port 配發 |
| `packages/mcp-admin-core/mcp_admin_core/identity_fields.py` | HM-07 | HM-12、HM-13b | 列管（HM-07 起） | — | 八個產品的身分欄位與秘密欄位分類 |
| `packages/mcp-admin-core/mcp_admin_core/profile_runtime.py` | HM-05 | HM-08 → HM-09 → HM-13b → HM-30 → HM-31 → HM-25 | 列管 | — | 每帳號執行套件（store、Supervisor、監看、收據） |
| `packages/mcp-admin-core/mcp_admin_core/profile_router.py` | HM-08 | HM-10 → HM-14 → HM-31 → HM-27 | 列管 | — | 8081 token 分派器；8099 分派、方法表、Ingress 備援改寫 |
| `packages/mcp-admin-core/mcp_admin_core/profile_admin.py` | HM-10 | HM-13c → HM-27 | 列管 | — | 帳號增刪改查、索引隔離、全部撤銷、還原核對 |
| `packages/mcp-admin-core/mcp_admin_core/restore_detect.py` | HM-13a | HM-13b | 列管 | — | sentinel 與 record 的建立、比對、重建 |
| `packages/mcp-admin-core/mcp_admin_core/restore_lock.py` | HM-13b | HM-13c | 列管 | — | 開機守門 A～F 步、休眠處理、`.revoke-all-pending` |
| `packages/mcp-admin-core/mcp_admin_core/request_budget.py` | HM-31 | HM-30（如果回覆額度要共用它）；HM-19c 量測後改常數的功能 PR | 列管（HM-31 起） | — | 閘道的請求內容位元組預算（全 add-on＋每帳號份額，對齊 PaaS #155）、讀取閒置、讀完丟掉的拒絕、每帳號每情況 60 秒一行的 WARNING（`Reports`，從 `profile_router.py` 移來）；不受開關管 |
| `packages/mcp-admin-core/mcp_admin_core/log_redaction.py` | HM-02 | PaaS 遮罩之後再變時的同步 PR（#149 已在 `7d111b1` 合併，HM-02 直接用合併版） | 列管（記在 `runtime-patches.json`；不另記 `runtime-sources.json`，那本只收 `apps/<產品>/vendor/`。DQ-38 的補充，HM-02 審查 MF-3，2026-11-15 08:2x 定案） | — | 紀錄遮罩（PaaS 規則先、HA 規則後） |
| 回覆工作執行緒模組（暫定名 `reply_worker.py`） | HM-30 | — | 列管 | — | 回覆處理的工作執行緒與依帳號輪流的佇列 |
| `packages/mcp-admin-core/mcp_admin_core/origin_policy.py` | HM-27 | — | 列管 | — | 密鑰網址的服務層級 Origin 清單（report-only） |
| `packages/mcp-admin-core/mcp_admin_core/child_identity.py` | HM-15（條件式） | — | 列管 | — | listener 身分檢查 |
| `packages/mcp-admin-ui/src/profiles.js` | HM-11 | HM-13c | 列管 | — | 面板帳號選單、建立／改名／刪除對話框 |
| `apps/runtime/child_auth.py` | 不建：HM-06 把子程式 bearer 寫進已列管的 `apps/runtime/session_idle.py`，同一個 PR 更新帳本摘要、重產 tool-surface | — | — | — | 子程式 bearer 驗證 |

## 2. 已列管、多帳號會改到的檔

每片改到就更新 `sha256` 與 `change`（照計畫 §12.2 的衝突表一次只送審一片）：`products.py`、`gateway.py`、`run_product.py`、
`configuration.py`、`operations.py`、`admin_auth.py`、`access.py`、`request_limits.py`、`backend_edit.py`、`__init__.py`、`config.py`（HM-07 起）、
`lifecycle.py`（HM-09 起；以上在 `packages/mcp-admin-core/mcp_admin_core/`）、`apps/runtime/session_idle.py`、`apps/runtime/run_child.py`、`apps/runtime/backend_policy.py`、
`apps/n8n/n8n_adapter.py`、`apps/n8n/backend_policy.cjs`、`apps/n8n/run.py`、`apps/hermes/launch.py`、`apps/opendesign/launch.py`、
`packages/mcp-admin-ui/src/app.js`、`api.js`、`contracts.js`、`operation-identity.js`。

## 3. 沒列管、多帳號會改到的檔

`packages/mcp-admin-core/mcp_admin_core/health.py`、`redact.py`、`diagnostics.py`、`ha_role.py`、
`packages/mcp-admin-ui/src/styles.css`：維持現狀不列管；該片審查要求列管時才加，決定寫進該片的 provenance 筆記。

原本在這一節、後來改成列管的：

- `packages/mcp-admin-core/mcp_admin_core/config.py`：HM-07 起列管（HM-07 審查 S-10），已移到第 2 節。
- `packaging/entrypoint.py`：HM-13a 起列管（HM-13a 還沒合併；合併前帳本裡沒有它）。
- `packages/mcp-admin-core/mcp_admin_core/lifecycle.py`：HM-09 起列管（HM-09 審查 S-10：`EXEC_WRAPPER` 在每個額外帳號子程式
  fork 之後、exec 之前執行），已移到第 2 節。`health.py` 審查沒有要求，維持不列管。

## 4. 規則

- 新增的帳本項目：`path`；`sha256`＝commit 當下檔案的 SHA-256；`change`＝這片做了什麼與對齊的 PaaS commit；`guarded_sources`＝檔內寫了
  source-guard 摘要時列出每個 app 的對應檔與摘要，沒有就 `{}`（`tests/test_tool_inventory.py::test_runtime_patch_ledger_and_guarded_wheel_sources` 會檢查）。
- 動到 `apps/runtime/*.py` 或 `apps/*/launch.py`：跑 `python scripts/tool_inventory.py --write` 重產 tool-surface；CI 的
  `packaging/unit.sh` 會跑不帶參數的版本檢查漂移。
- 同一時間只送審一片會動帳本的 PR；後合的 rebase 後一律重產帳本與 tool-surface、重跑 CI（摘要要重算，不是解完衝突就好）。
- 每片 push 前跑 `scripts/ledger_precheck.py` 與 `scripts/secret_precheck.py`（HM-01 收進 repo），結果寫進 provenance 筆記。
- 帳本新摘要被 gitleaks 命中時，才走 `packaging/secret-triage.json`（獨立審查＋使用者核准）。

## 5. HM-00 本片

只改 `docs/`；沒有新模組、沒有動任何列管檔，帳本與 tool-surface 都不變。預檢結果見 `docs/provenance/ha-multiprofile-HM-00-20261114.md`。

2026-11-15 的文件同步 PR 也一樣：只改 `docs/multi-profile/`，帳本與 tool-surface 都不變。
