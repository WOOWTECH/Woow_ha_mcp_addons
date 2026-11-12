# 0.1.4 HA 回歸紀錄（2026-10-06 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。七支由 0.1.3 更新到 0.1.4（03:30–03:59Z）：負責人改用手動確認後由 Claude 執行更新指令。
更新前先做了七支的冷備份（成功）；備份含 MCP 權杖與後端金鑰，回歸通過後刪除。

更新期間另有一個本機建置的 add-on（`local_woow_nextcloud_candidate`，0.2.0 → 0.2.1）在同一台主機上建置，主機負載升高，
SSH 與網頁斷斷續續。Claude 的更新迴圈因此在第一支（n8n）之後隨 SSH 斷線中止；其餘六支改在 HA 端背景執行，odoo 第一次在建置期間
立即失敗（沒有錯誤紀錄），建置結束後單獨補更新成功。該 add-on 不是本線觸發（自動更新關閉，03:53Z 由他人經 SSH 停止），本線未碰。
原始紀錄在 Claude 交付線 `pilot-p9/p9-014-*`、`run-014.log`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.4、running、restarts 0；image ID 與 manifest digest 和 [發佈紀錄](release-decision-0.1.4.md) 及 GHCR 完全相同，
以程式逐項比對 7/7（n8n `7a346581…`／`21530a31…`、odoo `08395df4…`／`c5536d70…`、odoo-manage `daf0fd85…`／`c49d4f34…`、
hermes `da0efc38…`／`fb8aafb3…`、opendesign `e22301fc…`／`4bf8bdb2…`、emqx `ec0d81c0…`／`a7125dbd…`、litellm `ff10ddfc…`／`9aa8939d…`）。

## 0.1.4 修正在真 HA 上的驗證

| 修正 | 結果 |
|---|---|
| Odoo Manage 私有健康探測 | **PASS**：白名單開啟時 8081 `/health/ready` 回 200（0.1.3 最小權限帳號一律 503）；讀取 5/5 |
| OpenDesign 0.21.1 health 形狀 | **PASS**：8081 `/health/ready` 回 200（0.1.3 一律 503）；讀取 10/10 |
| gateway 規則 | 七支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 未帶權杖都回 401；讀取、拒絕、斷線、開關全過，沒有回歸。4xx／5xx 內容、通知與錯誤碼改寫由單元測試把關（真子程序不會送出這些情況） |
| Odoo（0.1.3 的探測修正仍有效） | Woow Odoo 重啟後 16 秒開始測，讀取 10/12、`BACKEND_BUSY` 0 次 |

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.4 s | 25/25 | 17／29 ms |
| odoo | 10/12 | 30/30 | PASS | 7.1 s／5.1 s | 25/25 | 30／40 ms |
| odoo-manage | 5/5 | 6/6 | PASS（initialize 503） | 8.0 s／6.5 s | 25/25 | 48／66 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／4.6 s | 25/25 | 78／97 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.6 s／5.1 s | 25/25 | 16／23 ms |
| emqx | 8/8 | 32/32 | PASS | 9.2 s／7.1 s | 25/25 | 22／29 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- #1／#3／#4：七支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發與重啟後保留皆 PASS（LiteLLM 沒有後端：有效權杖 502、失效權杖 401）。
- #2 non-admin：**PASS**，臨時一般使用者對七支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200，沒有
  cookie 401；使用者已刪。
- 未過的讀取：n8n `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）；Odoo `list_models`、`schema_catalog`（測試帳號是最小權限、讀不到
  `ir.model`，回 `BACKEND_RPC_FAULT`）。
- Odoo 依負責人決定 B 暫時把兩個 MCP 容器 IP/32 加進 Woow Odoo `lan_networks`（04:06:02Z 重啟），測完改回原值並重啟（04:14:54Z），
  改回後 MCP 容器的連線被拒（已確認恢復封鎖）。

## 8081 readiness（白名單開啟、最後一次後端變更後 40 秒以上）

| n8n | odoo | odoo-manage | hermes | opendesign | emqx | litellm |
|---|---|---|---|---|---|---|
| 200 | 200 | **200** | 200 | **200** | 200 | 503（無後端） |

## 未測

- LAN client（需區網內機器）、LiteLLM 工具（沒有後端）、aarch64。
