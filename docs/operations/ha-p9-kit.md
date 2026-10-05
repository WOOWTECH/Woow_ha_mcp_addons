# P9 工具：在 HA 實機上量測一個 MCP app

`packaging/ha_p9_driver.mjs`（操作端，Node ≥ 22）＋`packaging/ha_p9_probe.py`（HA 主機端，只用 python3 標準庫）。
對象是**一個**已安裝的本專案 app；不碰其他 app、Core、Supervisor。2026-10-05 已在 n8n app 實跑。

## 前提

- 真 HA 管理員帳號（owner 或 system-admin）；帳密只從環境變數讀，不印、不寫檔。
- 能 SSH 到 HA 主機的 shell（例如 Advanced SSH & Web Terminal），有 `ha` CLI；`restart`、`childkill` 另需 Docker CLI。
- app 的 MCP 埠 8081 已對應到主機埠（`PROBE_PORT`），probe 在 HA 主機上連 `127.0.0.1:<PROBE_PORT>`。

## 用法

```sh
HA_URL=https://<ha> HA_USER=<admin> HA_PASS=<password> APP_SLUG=<repository slug>_woow_mcp_<product> \
SSH_TARGET=<ssh host> PROBE_PORT=18081 PROBE_TOOL=<唯讀工具> PROBE_TOOL_ARGS='{"...":"..."}' \
node packaging/ha_p9_driver.mjs --tokens --modes restart,childkill,bench,cycle
```

driver 以 HA 登入流程取得管理員 token → WebSocket `supervisor/api` 讀 app 的 ingress URL、建立 Ingress session →
呼叫 app 管理 API；每個 MCP token 只經 SSH stdin 傳給 probe。結束時撤銷本次的 HA refresh token。

| 選項／模式 | 做什麼 | 會改變什麼 |
|---|---|---|
| `--tokens` | 無 CSRF 的 rotate 應 403；reveal T1 → rotate T2（T1 失效）→ revoke（全部失效）→ 再 rotate T3 | **輪替 MCP token**：既有 client 要換新 token |
| `restart` | `ha apps restart <slug>`，量到 MCP 可用的秒數與首呼叫；重啟前後 token 必須相同 | 重啟這個 app |
| `childkill` | 在 app 容器內 SIGKILL management launcher 的子程序，量恢復時間；容器不應重啟 | 中斷這個 app 的 MCP 連線數秒 |
| `bench` | initialize×5、tools/list×50、`PROBE_TOOL`×50 的 p50／p95 | 無（只用唯讀工具） |
| `cycle` | 25 次 initialize＋DELETE，確認 session 名額有釋放 | 無 |
| `--backend-file F` | 用 0600 JSON（n8n `{"url","key"}`；其他六支 `{"connection":{...}}`）填面板後端，內容不印 | 改這個 app 的後端設定、重啟它的 MCP child |
| `--plan P` | 依清單呼叫工具：reads 必須成功（HTTP 200、非 isError、無 `success:false`）；denials 必須 HTTP 403 | 無（防護失效時見下方說明） |
| `--outage-url U` | 搭配前兩者：後端所有網址欄位（`url`、`gateway_url`、`dashboard_url`…）換成不通的 U，每個 read 都須回 HTTP 200（本機工具照常、後端工具回結構化錯誤），且至少一個 read 回結構化錯誤（或 0.1.2 起 gateway 在初始化就回 503 `BACKEND_UNAVAILABLE`：子程序沒有後端無法建立連線階段時，此時只檢查拒絕）；改回原設定後清單須再次全過 | 暫時改這個 app 的後端設定 |

probe 開的每個 session 都會 DELETE，不吃掉 app 的共用 session 名額（n8n 為 20 個、閒置 10 分鐘回收）。

### 清單（plan）

`python packaging/p9_plan.py <product> [--overrides args.json] > plan.json` 從 `docs/tool-surface.json` 產生：
已支援的讀取工具（或讀取操作）以 schema 推得的最小參數放進 reads，推不出安全參數的列在 `needs_args`，用 overrides
（`{"tool" 或 "tool:operation": {參數}}`）補上實際後端的值；已支援的寫入、暫不支援的工具與一個不存在的工具放進
denials。denials 的參數符合 schema 但指向**不可能存在**的資料（整數 id 取允許的最大值、名稱用 `p9-denied`），
即使寫入防護失效也不會動到真資料；仍須照試點程序在後端核對前後無變化。清單記錄來源 tool-surface 的 sha256。
`PROBE_TOOL` 只能填無副作用的工具；寫入防護、後端斷線、備份還原屬 P9 其他項目，不在本工具內。

## 證據

probe 每個模式最後印一行 `SUMMARY {...}`（不含 token），連同 driver 輸出存到試點紀錄；依
[試點程序](n8n-haos-pilot.md) 的格式記 UTC、app 版本與 image ID（HA 主機 `docker inspect <container> --format '{{.Image}}'`）。
