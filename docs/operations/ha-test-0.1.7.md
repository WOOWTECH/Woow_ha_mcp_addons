# 0.1.7 HA 回歸紀錄（2026-10-08 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。這台測試 HA 是 Core 2026.7.2、Supervisor 2026.09.3（自動更新已關）、OS 18.1。
更新、安裝與回歸照負責人核准的窗口清單 U-017 由 Claude 執行：

- 前置檢查：六支都是 0.1.6、running；bootstrap 與 0.1.6 回歸收尾時相同；沒有進行中的 Supervisor 工作；可用記憶體約 8.8 GB，
  磁碟可用 749.6 GB。
- 09:44Z：`ha store reload` 一次就看到六支 0.1.7 與新的 Nextcloud MCP。六支一起做更新前冷備份（`pre-0.1.7 woow mcp apps`），回歸通過後已刪除。
- 09:44–10:20Z：六支依序更新到 0.1.7，每支一次成功（這台主機拉映像較慢，每支約 5–15 分鐘）。
- 10:2xZ：安裝並啟動 Nextcloud MCP 0.1.7。預設沒有主機埠（`8081/tcp: null`），回歸時從 HA 主機經內部網路位址連線。
- Nextcloud 後端：同一台 HA 的 woow-nextcloud-office（NC 35.0.1），對外網址 `https://woowtech-nextcloud.woowtech.io`。
  以 `occ` 新建專屬一般使用者 `woow-mcp-test`（不屬於任何群組；登入密碼隨機產生、只經環境變數傳遞、不保存），App 密碼只寫進
  測試機的 0600 檔。測試資料只在這個使用者自己的家目錄（`WOOW-MCP-TEST/hello.txt`）。不在這台做錯密碼測試：Nextcloud 的
  暴力破解防護會限速來源 IP，影響正式使用者。

原始紀錄在 Claude 交付線 `pilot-p9/p9-017-*`、`run-017.log` 與 `e2e/U-017-*`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.7、started；image ID 與 [發佈紀錄](release-decision-0.1.7.md) 的已測 image ID 逐項相同 7/7（n8n `16875a6f…`、odoo `bf41b7ec…`、
hermes `884c2acc…`、opendesign `c088352b…`、emqx `107f4a11…`、litellm `de2fcd69…`、nextcloud `1d0688fc…`）。六支更新前後，bootstrap
的後端設定、權杖狀態、policy、工具數，除了版本以外完全相同。

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.5 s | 25/25 | 18／24 ms |
| odoo | 10/12 | 30/30 | PASS | 7.1 s／5.1 s | 25/25 | 32／44 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／4.6 s | 25/25 | 78／97 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.6 s／5.1 s | 25/25 | 17／33 ms |
| emqx | 8/8 | 32/32 | PASS | 9.2 s／7.1 s | 25/25 | 23／29 ms |
| nextcloud（新） | 6/6 | 5/5 | PASS | 9.1 s／7.1 s | 25/25 | 374／918 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- 六支的結果與 0.1.6 相同。未過的讀取也一樣：n8n `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）；Odoo `list_models`、`schema_catalog`
  （測試帳號讀不到 `ir.model`）。
- **Nextcloud（第一次實機）**：
  - tools/list 只列 5 支讀取工具。`get_file_tree`（根目錄與 `WOOW-MCP-TEST`）、`read_text_file`、`get_file_content` 讀到測試檔；
    `list_calendars`、`list_tasks` 回空清單（這個使用者還沒有行事曆）。
  - 4 支寫入工具（`create_text_file`、`update_text_file`、`upload_file`、`delete_file_checked`）與未知工具都 403，Nextcloud 端沒有變動。
  - 後端斷線：後端網址換成連不到的位址，6 個讀取都回 `BACKEND_UNAVAILABLE: Could not reach Nextcloud (connection failed).`；還原後讀取恢復。
  - 延遲較高是因為後端走對外網址（經 Cloudflare tunnel）；其他產品的後端都在 HA 內網或同一條 tunnel 但呼叫較輕。
- #1／#3／#4：七支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發與重啟後保留皆 PASS（LiteLLM 沒有後端：有效權杖 502、失效權杖 401）。
  回歸輪替過權杖，MCP client 要改用目前的權杖。
- #2 non-admin：**PASS**，臨時一般使用者對七支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200，沒有
  cookie 401；使用者已刪、兩邊的 refresh token 已撤銷。

## 8081 readiness 與方法閘門

| n8n | odoo | hermes | opendesign | emqx | litellm | nextcloud |
|---|---|---|---|---|---|---|
| 200 | 200 | 200 | 200 | 200 | 503（無後端） | 200 |

七支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 與 POST 未帶權杖都回 401。

## 收尾

測試用 HA 帳號的 refresh token 全部撤銷；HA `/tmp` 的暫存探測檔與更新腳本已刪；更新前備份已刪；證據秘密掃描 0 命中。
Nextcloud 測試使用者 `woow-mcp-test` 與它的測試檔保留給之後的 e2e 實測，e2e 結束後以 `occ user:delete woow-mcp-test` 刪除。
