# 0.1.6 HA 回歸紀錄（2026-10-08 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。這台測試 HA 是 Core 2026.7.2、Supervisor 2026.09.3（自動更新已關）、OS 18.1。
更新與回歸照負責人核准的窗口清單 U-016 由 Claude 執行：

- 前置檢查：六支都是 0.1.5、running；bootstrap 與 2026-10-07 M1a 收窗的基線相同；沒有進行中的 Supervisor 工作；可用記憶體約 8.7 GB，
  磁碟可用 749.7 GB。
- 00:28Z：`ha store reload` 一次就看到 0.1.6。六支一起做更新前冷備份（`pre-0.1.6 woow mcp apps`，含 MCP 權杖與後端金鑰），回歸通過後已刪除。
- 00:28–00:30Z：n8n 更新成功。odoo 第一次更新時，主機暫時查不到 `ghcr.io`（Supervisor 紀錄 `lookup ghcr.io: no such host`），回 rc=1，
  仍以 0.1.5 照常執行；DNS 恢復後，其餘五支各一次就更新成功。
- 更新前後，六支 bootstrap 的後端設定、權杖狀態、policy、工具數，除了版本以外完全相同。

原始紀錄在 Claude 交付線 `pilot-p9/p9-016-*`、`run-016*.log` 與 `e2e/U-016-*`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

六支 0.1.6、started；image ID 與 [發佈紀錄](release-decision-0.1.6.md) 的已測 image ID 逐項相同 6/6（n8n `7f2d06d0…`、odoo `9d3238c1…`、
hermes `b47cb7b2…`、opendesign `32ea0687…`、emqx `7b621fed…`、litellm `fd4bfcf3…`）。

## 0.1.6 變更在真 HA 上

| 變更 | 結果 |
|---|---|
| 管理面板接受審查過的 Core 版本清單 | Core 2026.7.2（清單內）：六支 owner Ingress 200、bootstrap 正常；一般使用者 403（見下）。2026.7.3–2026.10.0 沒有真機證據（負責人決定這台測試 HA 暫不升級 Core），靠原始碼審查與本機測試 |
| tools/list 由 gateway 重新組成 | 五支（LiteLLM 沒有後端，列不出工具）每個工具只有 `name`、`inputSchema`、`title`、`description`、`annotations`；`annotations` 只有 MCP 的五個提示 |
| 宣告的 schema 頂層扁平化 | 五支每個工具的 `inputSchema` 頂層都是 `type: object`，沒有 oneOf／anyOf／allOf／enum／const／not／if／then／else／$ref；改寫的 7 個工具（n8n `n8n_manage_folders`；Odoo `diagnose_odoo_call`、`generate_json2_payload`；Hermes `hermes_skill`、`hermes_tools`、`hermes_session`、`hermes_cron`）都在清單裡 |
| initialize 被拒時結束子程序的 session | 真 HA 上沒有可安全觸發的情境，由單元測試與審查驗證 |
| n8n 子程序的 MCP SDK 1.31.0 | n8n 的讀取、拒絕、斷線、重啟、child 恢復、25 次開關都和 0.1.5 相同 |

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.4 s | 25/25 | 15／23 ms |
| odoo | 10/12 | 30/30 | PASS | 7.1 s／5.6 s | 25/25 | 31／44 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／5.1 s | 25/25 | 78／96 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.6 s／5.1 s | 25/25 | 17／23 ms |
| emqx | 8/8 | 32/32 | PASS | 9.2 s／7.1 s | 25/25 | 23／33 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- #1／#3／#4：六支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發與重啟後保留皆 PASS（LiteLLM 沒有後端：有效權杖 502、失效權杖 401）。
  回歸輪替過權杖，MCP client 要改用目前的權杖。
- #2 non-admin：**PASS**，臨時一般使用者對六支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200，沒有
  cookie 401；使用者已刪、兩邊的 refresh token 已撤銷。
- 未過的讀取與 0.1.5 相同：n8n `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）；Odoo `list_models`、`schema_catalog`（測試帳號讀不到
  `ir.model`，回 `BACKEND_RPC_FAULT`；2026-10-07 以暫時授權實測過這兩支的正向案例，見 Claude 交付線 O-D11／O-D11b 報告）。
- Odoo 後端走對外網址（負責人 2026-10-06 選 C），沒有改 `lan_networks`。
- Cloudflare tunnel 不穩：第一輪 hermes 的重啟測試與 odoo 一開始上傳探測檔時 SSH 斷線，兩支重跑。odoo 重跑全部完成；hermes 的讀取、
  拒絕、斷線與還原在第一輪完成（還原後 27/27），重啟、child 恢復、效能、25 次開關在重跑完成。

## 8081 readiness（最後一次後端變更後 40 秒以上）與方法閘門

| n8n | odoo | hermes | opendesign | emqx | litellm |
|---|---|---|---|---|---|
| 200 | 200 | 200 | 200 | 200 | 503（無後端） |

六支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 與 POST 未帶權杖都回 401。

## 收尾

測試用 HA 帳號的 refresh token 全部撤銷（含一個因斷線沒撤銷到的，已刪）；HA `/tmp` 的暫存探測檔與更新腳本已刪；更新前備份已刪；
證據秘密掃描 0 命中。
