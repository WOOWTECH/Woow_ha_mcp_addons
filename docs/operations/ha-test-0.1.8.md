# 0.1.8 HA 回歸紀錄（2026-10-10／11 UTC，woowtech-ha）

這台測試 HA 是 Core 2026.7.2、Supervisor 2026.09.3（自動更新已關）、OS 18.1，CPU Intel Celeron J6412。更新與回歸照負責人
2026-10-11 核准的窗口清單 U-018 由 Claude 執行（整份核准，清單外即停）。本輪回歸只讀：不輪替權杖、不改後端或 policy、不重啟。

- 前置檢查（17:57Z）：七支都是 0.1.7、started；bootstrap 寫入全關、沒有開著的 grant；沒有進行中的 Supervisor 工作；可用記憶體約 7.2 GiB，
  磁碟可用 748.4 GB。
- 17:57Z：`ha store reload` 一次就看到七支 0.1.8。七支一起做更新前冷備份（`pre-0.1.8 woow mcp apps`），回歸通過後已刪除。
- 17:59–18:37Z：七支依序更新到 0.1.8，每支第一次就成功（n8n 約 18 分鐘，其他每支 2–5 分鐘，共用的映像層已在主機上）。
- 更新後七支的顯示名稱都換成「Woow ○○ MCP Server」（Supervisor 只在安裝或更新時讀名稱；0.1.7 紀錄提過）。

原始紀錄在 Claude 交付線 `e2e/U-018-20261010T1757Z/`（不在 repo）。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.8、started；image ID 與 [發佈紀錄](release-decision-0.1.8.md) 的已測 image ID 逐項相同 7/7（n8n `191380f9…`、odoo `413d5e83…`、
hermes `5287db15…`、opendesign `3cb95d46…`、emqx `6d6d693c…`、litellm `635ade10…`、nextcloud `644614d7…`）。

## 讀取計畫（與 0.1.7 同一份）

| 產品 | 讀取＋拒絕 | 與 0.1.7 比較 |
|---|---|---|
| n8n | 34/35 | 相同：未過的仍是 `n8n_manage_folders`（n8n 2.12 沒有資料夾 API） |
| odoo | 40/42 | 相同：`list_models`、`schema_catalog` 回 BACKEND_RPC_FAULT（測試帳號讀不到 `ir.model`） |
| hermes | 27/27 | 相同 |
| opendesign | 16/16 | 相同 |
| emqx | 40/40 | 相同 |
| nextcloud | 11/11 | 相同（只讀測試使用者自己的檔案） |
| litellm | 無後端 | 相同：initialize 502（沒有 child） |

## 0.1.8 的新行為（`u018_probe.py`，每支一輪）

| 檢查 | n8n | odoo | hermes | opendesign | emqx | litellm | nextcloud |
|---|---|---|---|---|---|---|---|
| 沒帶 session 的 tools/list → 400（GATEWAY-2） | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| initialize：serverInfo＝`woow-mcp-<產品>` 0.1.8、capabilities 只有 tools（F6） | PASS | PASS | PASS | PASS | PASS | 502（無 child） | PASS |
| 四個審查過的 protocolVersion 都協商成審查清單內的版本 | PASS | PASS | PASS | PASS | PASS | 502 | PASS |
| session 內 tools/list、DELETE 結束 session | PASS | PASS | PASS | PASS | PASS | — | PASS |

- n8n 子程序把 2025-06-18 協商成 2025-03-26（n8n-mcp 支援的最新版，在審查清單內）；測試原本要求回同一版，是測試過嚴。
- Nextcloud 的 initialize 帶 instructions：這是設計（只有 Nextcloud 由 gateway 送審查過的副本，見發佈紀錄 F6）；測試原本要求沒有，是測試過嚴。
  其他六支都沒有 instructions。
- **RR-03（Odoo）**：`read_record` 只讀 `id` 查不存在的聯絡人（ID 2147483647）回 `{"success": false, "error": "Record not found: res.partner ID 2147483647"}`；
  查測試帳號自己的聯絡人（ID 12）回 `{"success": true, "result": {"id": 12}}`。兩個都是純讀取。
- **GATEWAY-3（EMQX）**：00:15:53Z 開一個 session（initialize、tools/list）後不再使用，1882 秒（約 31 分鐘）後在同一個 session 發 tools/list，回 **404**（閒置 30 分鐘的 session 已被子程序結束）。

## 8081 readiness 與方法閘門

| n8n | odoo | hermes | opendesign | emqx | litellm | nextcloud |
|---|---|---|---|---|---|---|
| 200 | 200 | 200 | 200 | 200 | 503（無後端） | 200 |

七支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 與 POST 未帶權杖都回 401。

## 收尾

更新前備份 `ea2110e2`（pre-0.1.8 woow mcp apps）已刪；HA `/tmp` 的更新腳本、探測檔與紀錄（先打包到交付線）已刪；16 次 HA 登入的 refresh token
都在各自結束時撤銷，沒有留下臨時使用者；七支 bootstrap 的寫入、停用工具、權杖與後端設定和更新前相同（寫入全關、沒有 grant）。
證據秘密掃描 0 命中（只有工具名稱、OpenDesign 專案 ID 與 Nextcloud 測試檔的 etag）。本輪沒有輪替權杖，MCP client 不需要更換權杖。
