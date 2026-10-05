# 0.1.2 HA 回歸紀錄（2026-10-05 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。負責人以 `ha apps update` 把七支由 0.1.1 更新到 0.1.2（21:16Z 前後）。
更新前備份沒有做成：給負責人的指令用 `$A` 組 `--app` 清單，HA SSH add-on 的 shell 是 zsh、不會拆字，`ha backups new` 失敗而更新照跑。
0.1.2 沒有改資料格式，未造成影響；指令已改成直接列出 `--app`。原始紀錄在 Claude 交付線 `pilot-p9/p9-012-*.log`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.2、started、restarts 0；image ID 與 manifest digest 和 [發佈紀錄](release-decision-0.1.2.md) 及 GHCR 完全相同
（n8n `a7e81f1b…`／`c1d619eb…`、odoo `6d997370…`／`b78f7a95…`、odoo-manage `aaa51c64…`／`87310118…`、hermes `10bb90bd…`／`04134aad…`、
opendesign `2669d3be…`／`5c33dcb8…`、emqx `37a699ac…`／`9d95166e…`、litellm `007bac72…`／`b6a2447e…`）。

## 0.1.2 修正在真 HA 上的驗證

| 修正 | 結果 |
|---|---|
| Odoo Manage 後端斷線 | **PASS**：initialize 回 HTTP 503 `BACKEND_UNAVAILABLE`、不帶 session id；拒絕仍 403（7/7）。0.1.1 是 200 空回應後 404 |
| OpenDesign `list_agents` | **PASS**：讀取 10/10（0.1.1 為 9/10，逾時） |
| Odoo 固定錯誤碼 | **PASS**：`schema_catalog` 權限不足時回 `BACKEND_RPC_FAULT`（0.1.1 為 `BACKEND_RESPONSE_INVALID`）；`list_models` 同為 `BACKEND_RPC_FAULT`。測試帳號是最小權限、讀不到 `ir.model`，這兩個工具本來就不可用 |
| bootstrap（還原修復） | **PASS**（n8n）：cold backup → partial restore → 5 s 內 started，log `re-owned 2`，10001:10001、0700／0600；測試備份已刪。權杖延續本輪沒驗到（讀取時 Ingress 尚在回 HA 錯誤頁），工具已改成等待就緒 |

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.5 s | 25/25 | 16／21 ms |
| odoo | 10/12（見下） | 30/30 | PASS | 7.1 s／5.6 s | 25/25 | 30／38 ms |
| odoo-manage | 5/5 | 6/6 | PASS（initialize 503） | 8.0 s／6.5 s | 25/25 | 48／67 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／5.1 s | 25/25 | 78／97 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.7 s／5.1 s | 25/25 | 16／43 ms |
| emqx | 8/8 | 32/32 | PASS | 9.1 s／7.2 s | 25/25 | 23／34 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- #1／#3／#4：七支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發皆 PASS。
- #2 non-admin：**PASS**，臨時一般使用者對七支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200；使用者已刪。
- n8n 未過的一項是 `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）。
- Odoo 依負責人決定 B 暫時把兩個 MCP 容器 IP/32 加進 Woow Odoo `lan_networks`，測完改回原值並重啟 Odoo（21:32Z、21:39Z 兩次，皆已確認改回）。

## 待追蹤

- **Odoo `BACKEND_BUSY` 一次**：第一輪 Odoo 的 12 個讀取全部回 `BACKEND_BUSY`（白名單生效、Odoo 重啟後約 20 秒內，以及斷線測試後還原時）；add-on
  重啟後立即正常。對照重跑（Odoo 重啟後 17 秒、以及 3 分鐘後）兩次都是 10/12、沒有 BUSY，未能重現。Odoo 的 child 只有一個工作槽，
  健康檢查每 15 秒用 `list_models` 探測後端；推測是 Odoo 剛重啟、回應慢時探測佔住工作槽。列入 0.1.3：避免健康探測讓單一工作槽的產品拒絕使用者呼叫。

## 未測

- LAN client（需區網內機器）、LiteLLM 工具（沒有後端）、aarch64。
