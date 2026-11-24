# Odoo 0.5.1：上架後從 Store 升級再驗（第 11 項）

2026-11-24 16:50–17:41（台北）。展示機 woowtechshow（J6412，正式 HAOS：Supervisor 2026.11.0、Core 2026.7.2、OS 18.1、Docker 29.5.3）。

前提都成立才做：PR #137 已合併（`5f7ee36`）；合併 commit 上的 `woow-addon-release.yml`（run 45353460465）與 `release-train.yml`（run 45353461714）成功；
GitHub Release `woow_mcp_odoo-v0.5.1` 已發佈；Store repo 已同步成 0.5.1；展示機的 Store 顯示最新版 0.5.1。
對象是展示機上**從 Store 安裝的** `woow_mcp_odoo`（起點：0.4.14、停止、boot manual），不是測試用的本機 add-on。

做法：HM-19b 工具包的商店模式。改狀態前先做加密的局部備份；後端是展示機 Odoo 另開的測試庫（只裝 base）與 5 個受限使用者，用測試專用的 HA 管理員登入；
測完刪除測試庫、測試管理員、這一輪的備份與憑證，Store app 用升級前的備份還原成起點。

## 結果

| 項目 | 結果 |
|---|---|
| 升級前 | Store app 的局部備份（回退點）；暫時把 MCP 埠對到主機（事後還原）；寫入全關；預設帳號接測試庫 admin，token 不變，兩種接法都 200 |
| Store 升級 | Supervisor 從 Store 升級 0.4.14 → 0.5.1，執行中的映像 ID＝已發佈的 0.5.1（`12b97d0d5730…`）。升級前後快照只差版本、映像、容器啟動時間與新增的帳號清單列；token 指紋、`state.json`、兩條網址、工具數、政策都相同 |
| P9 | 預設帳號（Odoo admin）18/18：9 個真讀取、9 個寫入拒絕 |
| 多帳號 | 建 3 個額外帳號：4 個 token 互異，全部兩種接法 200；整個 add-on RSS 1 個帳號 339 MiB、4 個帳號 423 MiB |
| 局部還原（UC-08，一般與加密） | 兩種都 PASS：還原後 B、C、D 回來且一律撤銷、E 消失；還原前的 token 全被拒；舊收據 410 `operation_restored`；核對前重發 409 `restore_review_required`；核對後重發；演練備份自刪 |
| sentinel | 重啟前後 `.instance-sentinel`、`.instance-record` 的 inode 與 ctime 都相同；4 個 token 重啟後都還在；重啟後的 log 沒有還原、撤銷或守門行 |
| UC-10（自動部分） | 經 Ingress 的 `api/profiles` 200、有 ETag、`no-store`；條件式 GET 200。422 那一小項是工具包送錯格式（與 HM-19b 第二輪同一個工具包問題）；產品的 422 行為第二輪已在同一顆映像驗過 |
| 還原成起點 | 關閉暫時的埠，還原升級前的備份：0.4.14、停止、boot manual、沒有埠對應；展示機的 mcp-odoo 映像與起點完全相同 |
| 清理 | 合成憑證掃描 0 命中；清理完成；逐項驗證 CLEAN |

## 偏離與測試工具的問題（不是產品問題）

- 不做完整備份還原與主機重開（負責人 2026-11-23）。
- 工具包的清理驗證在商店模式把 Store app 本身當成「應已移除的測試 add-on」，這一項在商店模式永遠失敗；這一輪沒有裝本機測試 add-on，
  改以一般模式重跑同一支驗證（只差「測試 add-on」指的是本機那一顆），全部通過。工具包要修。
- UC-10 的 422 小項這一輪沒有另外補驗（見上表）。

## 證據

`artifacts/ha-multiprofile-parity-20261114/takeover-20261123/hm19b-kit/evidence-20261124T085026Z/`（`RESULT-item11-zh-TW.md`、各步驟 log；不含任何 token 或密碼）。
