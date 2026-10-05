# 0.1.1 HA 實測紀錄（2026-10-05，woowtech-ha）

環境：負責人指定的測試 HA `woowtech-ha`（Supervisor 2026.09.3、Core 2026.7.2，amd64）。七支 0.1.1 由負責人以
`ha apps` 指令從本 repository 商店安裝（n8n 由 0.1.0 升版）。工具：[HA 實測工具](ha-p9-kit.md)。測試帳密只存在測試機
的 0600 檔，未進 Git。原始紀錄在 Claude 交付線 `pilot-p9/p9-011-*.log`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈證據一致）

| 產品 | config digest（image ID） | manifest digest |
|---|---|---|
| n8n | `sha256:bc4852a2a7b58ab625e9edf8705ca3270b285ca5558076e96c3be950342cc5ed` | `sha256:c00923fdf060a739d0bf097b272a43bd83faf433fb5b4da6f1f8ea1e8d5b6037` |
| odoo | `sha256:4df1c275be1b0f137d24b476512bd11b0d75608e1c22444bf91bcb015d33847f` | `sha256:706596c94630f4ebee14bd8f93cfdf1f591de5db26cd996bccdff0cd439c0791` |
| odoo-manage | `sha256:e3444aed4d8794f52a05c9ae882482a33c7f8d4aa969127a6c4144ea2b4280c8` | `sha256:1bdbe9b8d98a27f4e4a9ae6dc9d217623ca9b34d8cc1866663bbf41cf9b9551b` |
| hermes | `sha256:d2683f1b47c0df98115208714e999f6623cef8bda57243acf55cc16239bb8c5b` | `sha256:3a640a385b8bc9a50a1aa3a17c7e6ab708bf18e140fae4ab293db532287c10f6` |
| opendesign | `sha256:72e728d5af30003fe319919e91595fae9aed2aca21ac643f736b9208551bb43b` | `sha256:5d0e7ec4cde3d6c014ae8e92700fb52c122ba68407fae66598caed8a788257dd` |
| emqx | `sha256:8ad5933a9a6f66cee61b7ab18154fe6299e68639651473f37aadb1de4a49d37f` | `sha256:89028bb975b00542fb23a13eae3286eba79d4ffbf5937f145a30b94a58c8ee53` |
| litellm | `sha256:06aa6f122794e5e0ba323defb69b1a51a1c744909ec9a1f7e11cf5bb97c4291f` | `sha256:536f61610a59def5b5864922a13edf600e097775ccdb70167c447f4448fcf043` |

## 結果

編號同 [n8n 試點](n8n-haos-pilot.md) 的 P9 項目。讀取＝每個支援的讀取工具／operation 呼叫一次，須 200 且無錯誤；
拒絕＝寫入、暫不支援、schema 不接受的 operation 與一個不存在的工具，須 403。

| 產品 | 真後端 | #4 權杖 | #5 讀取 | #6 拒絕 | #7 後端斷線 | #7 重啟後可用／child 恢復 | 25 次開關 session |
|---|---|---|---|---|---|---|
| n8n | Woow n8n 2.12.3 | PASS | 10/11 | 24/24 | PASS | 5.0 s／3.1 s | 25/25 |
| odoo | Woow Odoo 18，最小權限帳號 | PASS | 10/12 | 30/30 | PASS | 7.1 s／5.1 s | 25/25 |
| odoo-manage | 同上（API key，read 模式） | PASS | 5/5 | 6/6 | **FAIL**（見已知問題 1） | 8.0 s／6.5 s | 25/25 |
| hermes | Woow Hermes（gateway＋dashboard） | PASS | 8/8 | 19/19 | PASS | 6.6 s／4.6 s | 25/25 |
| opendesign | Woow OpenDesign 0.21.1 | PASS | 9/10 | 6/6 | PASS | 6.6 s／5.1 s | 25/25 |
| emqx | Woow EMQX 5.8.9 | PASS | 8/8 | 32/32 | PASS | 11.3 s／7.1 s | 25/25 |
| litellm | 無（HA 上沒有 LiteLLM） | PASS（僅驗證） | NOT RUN | NOT RUN | NOT RUN | 重啟正常、權杖保留；無 child | 502（無 child） |

- **#1 管理面板／#3 設定**：真 HA owner 經 Ingress 進入七支面板（HA 管理角色驗證）；PUT 後端 200，重啟後設定與權杖保留。
- **#4 權杖**：沒有 CSRF 標頭的輪替 403；輪替後舊權杖 401、新權杖 200；撤銷後 401；重新發行後只有新權杖可用。
  LiteLLM 沒有後端：錯誤權杖 401，正確權杖 502（沒有 child 可轉），屬預期。
- **#5 未過的讀取**：n8n `n8n_manage_folders` list 回結構化 NOT_FOUND（n8n 2.12 沒有資料夾 API）；Odoo 與 OpenDesign 見已知問題。
- **#6 寫入防護**：除了全部回 403，也比對同一批讀取工具在拒絕與斷線測試前後的輸出（紀錄擷取的前段），六支 48 個讀取完全相同。
- **#7 後端斷線**：後端所有網址換成不通的位址後，MCP 仍可連線、本機工具照常、後端工具回結構化錯誤；改回後清單再次全過。
- **#7 生命週期**：`ha apps restart` 後 5–11 s 可用、第一個呼叫 0.03–0.27 s，權杖不變；kill child 後舊 session 502、
  3–7 s 內新 child 接手、容器不重啟。
- **#10 延遲**（HA 主機同機，經 gateway）：tools/call p50 16–77 ms、p95 22–98 ms；tools/list p50 15–43 ms。

### #8 備份還原、#9 升版（n8n）

- **#9 升版 PASS**：n8n 從 0.1.0（因 0.1.0 的還原缺陷停在 error）升 0.1.1 後啟動，log `bootstrap: re-owned 2 restored
  entries in /data/mcp`，資料 10001:10001、0700／0600，後端設定沿用，權杖＝0.1.0 備份當時的值。
- **#8 還原 PASS**：0.1.1 cold partial backup（3.1 s，app 隨即 started）→ 輪替權杖 → partial restore → 7 s 內 started，
  `re-owned 2`，10001:10001、0700／0600，權杖回到備份當時的值；還原後再輪替。之後工具清單 34/35（與還原前相同）。
  測試備份已刪除（含權杖與 n8n 測試 key）。
- 其他六支用同一份 bootstrap，未逐支做還原。

## 已知問題（0.1.2 候選）

1. **Odoo Manage 後端斷線時 session 失效**：initialize 回 200 但沒有內容，之後同一 session 回 404 `Session not found`、
   工具不列出（上游 server 建立 session 時連 Odoo 失敗）。後端恢復後立即正常，client 要重新連線。方向：gateway 對沒有
   結果的 initialize 回結構化錯誤，或讓 child 延後連線。
2. **OpenDesign `list_agents` 逾時**：後端 `/api/agents`（偵測 agent CLI）在這台 HA 約 8 s，上游 MCP 讀取逾時固定 5 s，
   回 `BACKEND_TIMEOUT`。方向：只放寬這個讀取的逾時。
3. **Odoo `list_models`、`schema_catalog` 需要讀 `ir.model`**：Odoo 18 只有「存取權限」群組（`base.group_erp_manager`）可讀，
   一般內部使用者明確為 0。最小權限帳號會回 `BACKEND_RPC_FAULT`／`BACKEND_RESPONSE_INVALID`（後者訊息不夠明確）。
   要用這兩個工具，帳號需該群組（權限很大）；否則接受這兩個工具不可用。Odoo Manage 的 `list_models` 會回空清單。
4. 既有：bootstrap 成功訊息在最後檢查前印出；修復那次開機把 soft `RLIMIT_NOFILE` 提高到 576 後，管理程序會沿用。
5. 設定或改回後端後，面板的 `health.backend` 約 1 分鐘內仍顯示舊值。

## Woow Odoo 同機連線

Woow Odoo add-on 的 nginx 只放行 `lan_networks`，同一台 HA 上的 MCP 容器預設被擋（連線直接關閉）。測試期間依負責人決定，
暫時把兩個 MCP 容器的 IP/32 加進 `lan_networks`；15:41Z 改回原值 `192.168.2.0/24 192.168.50.0/24` 並重啟 Odoo，確認兩個
MCP 又被擋。容器重新建立時 IP 可能改變，長期做法待負責人決定。

## 未測

- #2 non-admin（需 HA 一般使用者測試帳號，屬 Core 變更，待負責人）。
- LAN client（另一台機器經主機埠 18081–18088 連入）。
- LiteLLM 工具（沒有後端）；aarch64 映像未建。

## 同日修正的測試工具

首輪的部分「失敗」是測試清單本身的問題：schema 不接受的 operation 被當成讀取（n8n executions get、Hermes session get），
oneOf 分支要求的參數沒補（n8n folders get），`hermes_model` 的空參數其實是讀取；Hermes 斷線只換掉 gateway 網址
（dashboard 仍通）。修正後（`p9_plan.py`、`ha_p9_driver.mjs`、`ha_p9_probe.py`）重跑 n8n、Hermes、Odoo Manage，
結果如上表。
