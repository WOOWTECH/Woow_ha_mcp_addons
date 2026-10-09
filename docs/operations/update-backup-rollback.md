# 手動更新、備份與回復

以下是批准後的受控程序。HA 實證（測試 HA）：n8n 0.1.0→0.1.1 升版、0.1.1 cold backup→partial
restore（[0.1.1 紀錄](ha-test-0.1.1.md)）與 0.1.2 還原修復（[0.1.2 紀錄](ha-test-0.1.2.md)；權杖延續本輪沒驗到）皆成功；0.1.1→0.1.5 每版都以
`ha apps update` 更新全部產品並回歸（[0.1.5 紀錄](ha-test-0.1.5.md) 等），0.1.3 起更新前先做冷備份。其餘五支（Odoo、Hermes、
OpenDesign、EMQX、LiteLLM）未逐支做還原，版本回退（降版＋相容備份）也還沒演練。
只允許操作本次新增的 MCP Add-on，不重啟現有 backend、Core、Supervisor 或 k3s。
映像在私有 builder 建置並通過 supply-chain gate 後發佈到 GHCR（0.1.0–0.1.5；Odoo Manage 只到 0.1.4）；HA 安裝依 [逐步指令](n8n-pilot-commands.md) 逐步批准。

## 更新前

1. 逐產品檢查 CHANGELOG、固定 version／immutable digest、支援工具差異、
   typed backend schema、migration 相容性、必要 notices 與來源／安全審查。
2. 確認實際安裝 slug、repository 身分未變，8099/3000 沒有外部 mapping，
   可選 MCP host port 不衝突。改 slug/repo 不是原地更新，要另做資料遷移計畫。
3. 確認 auto-update 關閉。不要追 latest 或覆寫既有版本 tag；六個產品各自更新，
   不要求其他五個一起停止。依序一次更新一支，每支都要在核准清單內。
4. 提前定義可容許中斷、timeout、失敗停止點、回復映像 digest、相容 backup、
   恢復 client 的方法與負責人。受限非正式測試帳號不能擴展到正式副作用。

## 保護備份

manifest `backup: cold`：HA 會停止**這個新 Add-on**來取得一致狀態，MCP clients
短暫中斷，需要重新連線。它不是停止 backend 或整台 HA 的許可。事前告知使用者
此影響、預估窗口、驗證及失敗回復程序。

備份必須包含完整 `/data/mcp`，包含 `state.json`、writer marker 和必要狀態；
只抽一個 JSON 會破壞 missing-state fail-closed 判斷。保存 uid/gid **10001:10001**、
目錄 **0700**、敏感檔 **0600**。不添加共用 HA config/share/backup mounts。

實測（2026-10-05，HA partial restore 本 Add-on）：Supervisor 把 `/data/mcp` 還原成 root 擁有、檔案 0644，
0.1.0 啟動被拒（`bootstrap unavailable`）→ 0.1.0 的 HA 還原不可用（已知問題）。0.1.1 起 bootstrap 只在資料剛好
屬 root 時，檢查後一次改回 10001／0700／0600。還原後一律輪替 MCP token（備份含舊 token）。
0.1.1 實測（n8n）：cold backup 3.1 s（app 隨即 started）→ 輪替 token → partial restore → 7 s 內 started，log `re-owned 2`，
10001:10001、0700／0600，token 回到備份當時的值；之後輪替，工具清單與還原前相同。

0.1.1 修復的邊界與現象（`packaging/entrypoint.py`；獨立 SPEC 與安全審 2026-10-05）：

| 項目 | 行為 |
|---|---|
| 觸發條件 | 既有 `/data/mcp` 本身屬 root（0:0），且 bootstrap 以 root 執行；其他擁有者照舊拒絕 |
| 接受的內容 | 只有一般資料夾與單一連結的一般檔，擁有者為 root 或 10001，與 `/data/mcp` 在同一檔案系統 |
| 上限 | 最多 512 個項目、8 層；列目錄時邊讀邊數，超過立即拒絕 |
| 描述子 | 修復期間每個核准項目各占一個 descriptor；soft `RLIMIT_NOFILE` 低於 576 時拉到 576（只在修復那次開機；0.1.1 的管理程序會沿用，0.1.2 起修完即還原原值）；hard 低於 576 則拒絕 |
| 依賴 | 需要容器內的 `/proc`（一般檔經 `/proc/self/fd` 改 owner／mode）；沒有 `/proc` 時拒絕 |
| 不處理 | ACL、xattr 不檢查也不保留 |
| 成功 | log 一行 `bootstrap: re-owned N restored entries in /data/mcp`，之後一般啟動（0.1.2 起在 `/data/mcp` 通過最後檢查後才印） |
| 中斷 | 每項先改 mode 再改 owner；修到一半中斷時，未完成的項目仍屬 root，下次啟動會再修 |
| 拒絕 | log `bootstrap unavailable; ...`、app 停在 error。第一遍檢查拒絕時不改任何項目；第二遍途中發現變動時，之前已改的只會是核准過的項目。回報負責人，比對 `/data/mcp` 內容與上表後人工處理，不要放寬權限或手動 chmod 繞過 |

**備份含 backend 密碼/API key、外部及 child token、endpoint／工具政策，視同秘密。**
限制下載與儲存人員、使用受控加密儲存與保留政策；不可入 Git、Actions artifact、
issue、聊天或公開 object storage。不要在終端傾倒 JSON。公開驗收只記錄 opaque
backup ID、版本、時間、保管位置類型、權限檢查結論，不記錄內容／金鑰。

## 執行與停止點

- 只用已批准且已匿名 pull 驗證的固定版本做 HA 手動更新。
- 檢查新 Add-on 啟動／三維健康、state 未丟失、endpoint／policy／token 持久化；
  做 initialize→initialized→list→已審無副作用 call 與拒絕測試。
- backend unreachable 不重啟 backend，也不將 readiness 接 watchdog。遇 state_error、
  unknown schema、source guard drift、角色 verifier 缺失、資料 owner 不符立即停止，
  保留原狀以便回復，不重新 bootstrap 或開寬權限硬闖。
- 六支的管理面板（`homeassistant_api`：n8n 自 0.1.0、其他自 0.1.1 起）已在測試 HA 以 owner 實測 Ingress、後端設定與 token；
  一般使用者一律 403（0.1.1–0.1.5 每版實測）。0.1.1→0.1.5 升版已在測試 HA 對每支實測；還原只在 n8n 實測過，
  其他產品的還原仍須逐支驗證，也不能擴及既有 HA 變更。

## Migration 與 rollback

完整有效 n8n v1／product v2 在 writer lock 下驗證後 atomic/fsync 遷移到 **v3**。
保留 token、child token、backend、endpoint、writes_enabled、disabled，新增
`enabled_write_tools=[]`。舊 global true 只保留原 n8n delete/OpenDesign delete 授權，
不會授權新增 writers。其他產品不能匯入 n8n state；unknown/duplicate grants、未知未來／
損毀／不完整 state 拒絕且不重寫。UI 保存取代全部 exact grants，disabled 永遠優先。

舊 v1/v2 executable **不接受 v3**：退 image 不等於退資料。必須使用升級前的
受保護相容 v1/v2 backup；不能手改 schema_version、刪 writer marker 或刪 state 讓系統
重建 token。若無相容 backup，先停用新 Add-on 並尋求核准恢復，不嘗試 lossy downgrade。

回復步驟：
1. 停止本次新 Add-on，記錄不含秘密的失敗摘要；不要移除備份或變更 backend。
2. 確認已核准回復 digest 和匹配的資料版本，保留失敗狀態的受控副本供調查。
3. 按 HA 核准還原流程，只恢復該 Add-on 的映像與完整資料；驗證 owner／權限。
4. 啟動該 Add-on，重新做協議/read／拒絕／policy／健康驗證。確認其他服務未變。
5. 還原可能使備份中的舊 token 復活、撤銷或寫入政策回到舊值；於正常管理功能
   可用時輪替 token，更新 clients。若管理仍封鎖，維持停用／隔離，不手改資料解鎖。
6. 記錄回復結果與實際中斷時間；未驗證成功不可宣告已復原。

移除也僅限新 Add-on；確認 HA 移除資料的行為與備份保管後再做，不刪既有服務。

## Odoo Manage 下架（0.1.5 起）

負責人 2026-10-06 決定 Odoo Manage MCP 整體下架封存，之後只用 Woow Odoo MCP Server（0.1.7 以前名為 WOOW Odoo MCP）。0.1.5 起商店不再提供，也不再建置或發佈；
0.1.4 是最後一版。已安裝的 Odoo Manage 仍以 0.1.4 執行，但不會再有更新或安全修正。它的設定保有 Odoo API key，並有
`homeassistant_api` 權限（廣泛的 Core 存取能力），建議：

1. 先改用 Woow Odoo MCP Server。它是不同的 MCP server（上游 odoo-mcp；工具、設定與權限模型都不同），要另外設定後端、建立 MCP
   endpoint 與 token，再更新 client。
2. 要保留設定就先做這支 add-on 的部分備份，再移除（`ha apps uninstall <slug>`）；移除會刪掉它的 `/data`。
3. 視需要在 Odoo 撤銷它用過的 API key；若其他服務共用同一把 key，先確認再撤銷。

已發佈的 `ghcr.io/woowtech/amd64-mcp-odoo-manage:0.1.0`–`0.1.4` 映像保留公開，舊備份仍可還原；不會再有新 tag。
