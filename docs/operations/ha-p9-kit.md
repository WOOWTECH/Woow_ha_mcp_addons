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

probe 開的每個 session 都會 DELETE，不吃掉 app 的共用 session 名額（n8n 為 20 個、閒置 10 分鐘回收）。
`PROBE_TOOL` 只能填無副作用的工具；寫入防護、後端斷線、備份還原屬 P9 其他項目，不在本工具內。

## 證據

probe 每個模式最後印一行 `SUMMARY {...}`（不含 token），連同 driver 輸出存到試點紀錄；依
[試點程序](n8n-haos-pilot.md) 的格式記 UTC、app 版本與 image ID（HA 主機 `docker inspect <container> --format '{{.Image}}'`）。
