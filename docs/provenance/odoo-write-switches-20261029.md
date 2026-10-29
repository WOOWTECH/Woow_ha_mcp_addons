# HA Odoo 四開關：來源與執行邊界（候選 PR，未發版）

比對基準：PaaS #89 `38a9041fb44de6d8848166473facd2f443e04710`，HA #26 合併後 `f71fb756baf5ca3458b32c5c20635e0689c13118`。PaaS #89 已在平台服務；本 HA 變更只在獨立 PR 的來源與隔離假後端測試，沒有映像、ws97 或正式環境驗收。#29 是 0.4.3；#30 預定 0.4.4；本 PR 不指定 0.4.4，合併與可能的 0.4.5 發布要在兩者之後協調。

## 為何不是把四個環境變數直接接到畫面

HA 基準版在 `products.child_spec` 把四項固定為 `1`，但安裝的 `odoo-mcp 1.3.0` 與 HA 的 `fix_direct_writes.py` 仍使用舊判斷：`ODOO_MCP_ENABLE_WRITES=0` 只擋已核准寫入，`ODOO_MCP_ALLOW_DIRECT_WRITES=0` 搭配未知方法開啟時仍可能執行 `action_*`，`MCP_CHATTER_DIRECT=0` 不阻止 `execute_method` 直接呼叫張貼訊息的方法，未列入審核讀取的 `get_*` 仍可能被名稱啟發式當成讀取。PaaS #89 已用 `odoo_mcp_admin.write_gates` 收緊四項的聯合判斷。單純加設定會讓介面宣稱關閉、實際仍放行。

`packages/mcp-admin-core/mcp_admin_core/odoo_write_gates.py` 是 PaaS #89 `apps/odoo/odoo_mcp_admin/write_gates.py` 的逐位元複本；兩者 SHA-256 均為 `b4852fb0ebd78b6d10c4a3fcd401d0d16eeb21a129ea3b2ece3b19e30c4a4b8d`。`apps/odoo/odoo_switch_overlay.py` 在已釘選的 HA wheel 上裝入同一決定、五支工具說明及 health posture；先核對四個 wheel 檔案與工具身份，再改任何處理器。`apps/odoo/start_switches.py` 先安裝覆蓋層，再執行原本已做來源檢查、運輸約束、工作佇列與私有 probe 的 `launch.py`。因此不改 #30 的啟動器、錯誤包裝或 wheel 補丁；後續 rebase 仍需重新跑精確來源測試。

| 設定欄位 | 子行程環境 | 關閉後的 PaaS #89 語意 |
| --- | --- | --- |
| `enable_writes` | `ODOO_MCP_ENABLE_WRITES` | `execute_method` 只允許審核讀取；`chatter_post`、`execute_approved_write` 拒絕；預覽與驗證可回覆但不能執行。 |
| `allow_direct_writes` | `ODOO_MCP_ALLOW_DIRECT_WRITES` | `execute_method` 的 create/write/unlink 拒絕，需三步核准；未審查方法不因 unknown 開啟而直接放行。 |
| `allow_unknown_methods` | `ODOO_MCP_ALLOW_UNKNOWN_METHODS` | 未審查方法（含非審核清單的 `get_*`）拒絕；只有總閘門與直接寫入也開時，開啟這項才真正放行。 |
| `chatter_direct` | `MCP_CHATTER_DIRECT` | `chatter_post` 先預覽、再核准；`execute_method` 的明確張貼訊息呼叫拒絕。Odoo 業務方法自動寫入的追蹤訊息仍取決於該方法的權限。 |

HA 的外層 `enabled_write_tools`、`writes_enabled` 舊授權、`disabled`、`denied_operations` 仍先作用；四項子設定不能增加外層權限。特別是 `execute_method` 在 HA 外層是整支寫入工具，若外層 grant 已撤銷，連它的審核讀取也無法呼叫；專用讀取工具仍可用。PaaS 的 `ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS`／政策檔精確白名單不在這四項裡，HA 目前也沒有白名單編輯；這是明確剩餘差異，不能把 unknown 關閉後的單一方法例外說成可由畫面設定。

## 舊設定與管理安全

新安裝及舊 schema 4 沒有 `odoo_write_switches` 的 state 都解讀成四項全開，等同既有 HA 子行程的實際值；**不改外層 grants、disabled、denies、token、backend**。欄位只在明確儲存時出現，且必須是完整四布林值，非 Odoo 產品拒絕。schema 1/2/3 的一次 owner-defaults 升級流程保持 #26 的既有規則，新欄位不會出現在舊版資料或復原紀錄；restore 會保留管理員在升級後另行收緊的四開關。`ProductStore._decode` 與 `migration._validate` 都只准 schema 4 擁有這個可選欄位，顯式 `null`、多餘鍵、非布林值拒絕，不自動修復錯誤狀態。

`PUT /api/odoo/write-switches` 使用既有 HA 管理員身份、CSRF、單寫入鎖、嚴格 JSON、必填 `If-Match` 與原子儲存；成功後同一提交所有權等待子行程重啟。回覆的 `configuration` 區分已儲存與套用中／失敗。UI 只在新版 Odoo bootstrap 有完整四開關契約時提供儲存；舊 API 及其他產品沒有可用控制項。子行程不在線時，管理端 `tools/list` 備用快照的五項說明也按儲存值變化，避免宣稱已關閉的行為仍可直接使用。

## 隔離驗證

- 純判斷測試涵蓋 16 種組合、審核讀取、標準寫入、未知方法、`get_portal_url`、chatter、白名單優先順序。
- 真實 `odoo-mcp 1.3.0` 子行程連本機假 XML-RPC：全開及四個單項關閉；含直接寫入、三步核准、chatter 預覽後核准、health posture，檢查假後端實際 mutation 次數。
- 管理 API 測試含角色、CSRF、必填／過期 ETag、完整鍵集合、舊 state、owner restore 與外層 grant 保留；UI 有 Node 契約與 Playwright 假服務測試（320、360、1440 px）。
