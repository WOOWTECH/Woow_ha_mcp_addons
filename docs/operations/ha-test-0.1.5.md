# 0.1.5 HA 回歸紀錄（2026-10-06 UTC，woowtech-ha）

環境與工具同 [0.1.1 實測](ha-test-0.1.1.md)。0.1.5 只有六支（Odoo Manage 已下架）。每一步都經負責人核准後由 Claude 執行：

- 09:12Z：先移除已下架的 Odoo Manage（先做這支的部分備份，再 uninstall）。
- 09:55Z：六支一起做更新前冷備份（含 MCP 權杖與後端金鑰），回歸通過後已刪除。
- 第一次 `ha store reload` 沒有觸發 git 更新（Supervisor 只重新載入既有內容），六支更新都回 rc=1 而沒有變動；再 reload 一次，
  商店才看到 0.1.5，Odoo Manage 也同時從商店消失（158 → 157 個 app）。
- 10:08–10:27Z 依序把六支更新到 0.1.5（rc=0）；這台主機拉映像較慢（emqx、litellm 各約 7–8 分鐘）。

更新與回歸期間主機上沒有其他 Supervisor 工作。原始紀錄在 Claude 交付線 `pilot-p9/p9-015-*`、`run-015.log`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

六支 0.1.5、running、restarts 0；image ID 與 manifest digest 和 [發佈紀錄](release-decision-0.1.5.md) 及 GHCR 完全相同，
以程式逐項比對 6/6（n8n `fe1f1e82…`／`defb41e4…`、odoo `3f834556…`／`a2bcd52e…`、hermes `c62a44df…`／`895e85e7…`、
opendesign `94d6869f…`／`ab630fa6…`、emqx `537a3028…`／`08b36ab9…`、litellm `2a2d780b…`／`73dd0819…`）。

## 0.1.5 變更在真 HA 上

| 變更 | 結果 |
|---|---|
| gateway 回覆重組、POST SSE 回覆後結束、GET 不轉回覆、ping `{}`、protocolVersion 檢查 | 真子程序、真後端下的讀取、拒絕、斷線、重啟、child 異常、25 次開關、權杖輪替／撤銷，結果都和 0.1.4 相同，沒有回歸。這些規則的邊界由單元測試與審查者用真的 TS／Python client 驗證 |
| 基底改釘（python 3.13.16 的 2026-10-06 重建版） | 六支正常啟動；重啟與 child 恢復時間和 0.1.4 相同 |
| Odoo Manage 下架 | 商店已不提供；測試 HA 上那支已移除 |

## 全部結果

| 產品 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 | #10 tools/call p50／p95 |
|---|---|---|---|---|---|---|
| n8n | 10/11 | 24/24 | PASS | 4.5 s／2.5 s | 25/25 | 16／18 ms |
| odoo | 10/12 | 30/30 | PASS | 7.1 s／5.1 s | 25/25 | 31／43 ms |
| hermes | 8/8 | 19/19 | PASS | 6.6 s／5.1 s | 25/25 | 78／98 ms |
| opendesign | 10/10 | 6/6 | PASS | 6.6 s／5.1 s | 25/25 | 16／22 ms |
| emqx | 8/8 | 32/32 | PASS | 9.2 s／7.1 s | 25/25 | 23／32 ms |
| litellm | 無後端 | — | — | 重啟正常、權杖保留；無 child | 502（無 child） | — |

- #1／#3／#4：六支 owner Ingress、PUT 後端、權杖輪替／撤銷／重發與重啟後保留皆 PASS（LiteLLM 沒有後端：有效權杖 502、失效權杖 401）。
- #2 non-admin：**PASS**，臨時一般使用者對六支面板、`api/bootstrap`、`api/token/reveal`、`PUT api/backend` 全部 403，owner 200，沒有
  cookie 401；使用者已刪、兩邊的 refresh token 已撤銷。
- 未過的讀取與 0.1.4 相同：n8n `n8n_manage_folders`（n8n 2.12 沒有資料夾 API）；Odoo `list_models`、`schema_catalog`（測試帳號是最小
  權限、讀不到 `ir.model`，回 `BACKEND_RPC_FAULT`）。
- Odoo 依負責人決定 B 暫時把 Odoo MCP 容器 IP/32 加進 Woow Odoo `lan_networks`（10:32:57Z 重啟），測完改回原值並重啟（10:40:39Z），
  改回後 MCP 容器的連線被斷開（已確認恢復封鎖）。

## 8081 readiness（白名單開啟、最後一次後端變更後 40 秒以上）與方法閘門

| n8n | odoo | hermes | opendesign | emqx | litellm |
|---|---|---|---|---|---|
| 200 | 200 | 200 | 200 | 200 | 503（無後端） |

六支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 與 POST 未帶權杖都回 401。

## 之後：Woow Odoo 改走對外網址（負責人選 C，2026-10-06 11:0xZ）

負責人決定一般都用外網連線。Claude 經負責人提供的 Cloudflare token，在這台 HA 的 tunnel 新增 `woowtech-odoo.woowtech.io`
（指向 `http://homeassistant:8069`）與對應 DNS；Woow Odoo 的 `public_url` 原本是 `https://woowtech-odooo.woowtech.io`（多一個 o、
沒有 DNS），改成同一個網址並重啟（11:09:15Z）；Odoo MCP 的後端網址改成這個對外網址。結果：讀取 10/12（同上）、拒絕全過、
斷線 8 項結構化錯誤、8081 readiness 200，全程沒有改 `lan_networks`。之後的回歸不再需要決定 B。

## 未測

- LAN client（需區網內機器）、LiteLLM 工具（沒有後端）、aarch64。
