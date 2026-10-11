# 0.1.9 發佈紀錄（草稿，準備中）

> 本機分支 `local/claude-0.1.9`（以已發佈的 0.1.8 為基礎）。負責人 2026-10-11「現在就發 0.1.9」，只為了支援 Core 2026.10.1；
> 之後的 Core patch 維持逐版審查。推上 GHCR、商店與測試 HA 都要負責人核准（窗口 P-019／U-019）。

## 內容

### 管理面板支援 Core 2026.10.1

- 問題：Core 2026.10.1 在 2026-10-10 發佈（stable）。0.1.8 的管理面板只接受審查過的 Core 版本（到 2026.10.0），
  所以 Core 升到 2026.10.1 的 HA 上整個管理面板回 403（看起來像「不是管理員」）；MCP 端點（Bearer token）不受影響。
- 審查：Core 2026.10.1（tag commit `abe1fdd7`）的 21 個合約檔和 2026.10.0 的 git blob 逐一相同，四個相鄰檔案也相同；兩個 tag
  之間唯一和登入有關的改動（`components/auth/indieauth.py`、`login_flow.py`）不在本 add-on 用的 `config/auth/list` 路徑上。
  Supervisor 端：2026.09.3／2026.10.0 的 proxy blob `fc11251d` 與 2026.10.1 的 `002174e5` 都已審查，握手 frame 不變。
  紀錄見 [ha-role-core-contract](../ha-role-core-contract.md)。
- 修改：`ha_role._HA_VERSIONS` 加 `2026.10.1`；審查表加 `10.1` 欄；測試的精確集合加入它，near miss 改成 `2026.10.2`、
  `2026.10.1b1`、`2026.10.1.0`、`2026.10.10`、前後空白等；新測試要求審查表的欄位與 `_HA_VERSIONS` 完全相同。
  七支 CHANGELOG、DOCS、README、guide、n8n-ha-role 寫明版本。
- 審查（631b0ce）：沒有 High／Medium；Low 與 Note 已於 8c39a68 處理。

## 待辦（0.1.9 範圍內）

- 之後的 Core patch（例如 2026.10.2）照樣要比對或審查後發新版（負責人決定逐版審查）。
