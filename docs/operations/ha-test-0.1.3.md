# 0.1.3 HA 回歸紀錄（2026-10-06 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。負責人以 `ha apps update` 把七支由 0.1.2 更新到 0.1.3（00:10Z 前完成）。
更新前先做了七支的冷備份（指令直接列出 `--app`，這次成功）；備份含 MCP 權杖與後端金鑰，回歸通過後刪除。
原始紀錄在 Claude 交付線 `pilot-p9/p9-013-*`、`run-013.log`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.3、running、restarts 0；image ID 與 manifest digest 和 [發佈紀錄](release-decision-0.1.3.md) 及 GHCR 完全相同，
以程式逐項比對 7/7（n8n `a4fe3ec2…`／`eae07f0a…`、odoo `50b2f1d7…`／`063d0dbd…`、odoo-manage `3a52564e…`／`7c79becd…`、
hermes `e1d0cc6d…`／`d80c6755…`、opendesign `d8e131fd…`／`3d5ff9cd…`、emqx `4cefe5c6…`／`b26bd653…`、litellm `3459b3bb…`／`a248db41…`）。

## 0.1.3 修正在真 HA 上的驗證

| 修正 | 結果 |
|---|---|
| Odoo 健康探測不佔工作槽 | **PASS**：Woow Odoo 重啟後 16 秒開始測（與 0.1.2 出現 BUSY 的時機相同），讀取 10/12、`BACKEND_BUSY` 0 次；斷線恢復後與重啟測試後也是 0 次。0.1.2 同一流程有兩個窗口、各 12 個讀取全回 `BACKEND_BUSY` |
| Odoo 最小權限帳號可連線 | **PASS**：白名單開啟時 8081 `/health/ready` 回 200 `{"ready":true}`（需要後端 reachable）；0.1.2 這個帳號因探測需要讀 `ir.model` 而一律 unreachable |
| `/mcp` 所有方法先驗證 | **PASS**：七支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 未帶權杖都回 401（0.1.2 是在驗證前回 405） |
| protocolVersion 驗證 | **PASS**：有後端設定的六支健康檢查 `transport_ready: true`，真子程序的 protocolVersion 都通過；不合規時的處理由單元測試把關 |

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.5 s | 25/25 | 16／27 ms |
| odoo | 10/12 | 30/30 | PASS | 7.1 s／5.6 s | 25/25 | 29／35 ms |
| odoo-manage | 5/5 | 6/6 | PASS（initialize 503） | 8.0 s／6.5 s | 25/25 | 52／73 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／4.6 s | 25/25 | 78／98 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.6 s／4.6 s | 25/25 | 16／26 ms |
| emqx | 8/8 | 32/32 | PASS | 9.2 s／7.1 s | 25/25 | 22／41 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- #1／#3／#4：七支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發皆 PASS（LiteLLM 沒有後端：有效權杖 502、失效權杖 401）。
- #2 non-admin：**PASS**，臨時一般使用者對七支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200，沒有
  cookie 401；使用者已刪。
- 未過的讀取：n8n `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）；Odoo `list_models`、`schema_catalog`（測試帳號是最小權限、讀不到
  `ir.model`，回 `BACKEND_RPC_FAULT`）。
- Odoo 依負責人決定 B 暫時把兩個 MCP 容器 IP/32 加進 Woow Odoo `lan_networks`（00:15:55Z 重啟），測完改回原值並重啟（00:24:21Z），
  改回後 MCP 容器的連線被拒（已確認恢復封鎖）。

## 8081 readiness（白名單開啟、最後一次後端變更後 40 秒以上）

| n8n | odoo | odoo-manage | hermes | opendesign | emqx | litellm |
|---|---|---|---|---|---|---|
| 200 | 200 | 503 | 200 | 503 | 200 | 503（無後端） |

兩個 503 不是 0.1.3 造成的（探測與 0.1.2 相同，0.1.2 沒有量這一項），讀取都正常，列入 0.1.4：

- OpenDesign：這台的 OpenDesign 0.21.1 的 health 回 `{"ok": true, "version": "0.21.1"}`，探測只認 `status` 為 ok／healthy
  （[six-adapters](../six-adapters.md) 的保守設定，等版本確認）。
- Odoo Manage：探測用 `list_models`，最小權限帳號讀不到 `ir.model`，回錯誤分支（`operations.read` 為 false）；與 0.1.3 修好的 Odoo 同類。

## 未測

- LAN client（需區網內機器）、LiteLLM 工具（沒有後端）、aarch64。
