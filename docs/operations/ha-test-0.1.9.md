# 0.1.9 HA 回歸紀錄（2026-10-11 UTC，woowtech-ha）

**2026-10-11 獨立收斂審查 PASS，依主對話裁定完成原範圍驗收，回歸符合 U-019 基準。窗口前根 client 登入 1 筆保留未更動、兩個 u018 probe 屬原 S5/S6 指定 runner 本輪暫存清理範圍；原追加 strict comparison exit=1 保留。推送／HA 交還以 S7/S8 實際回執為準，不以審查 PASS 代替執行成功。**

這台測試 HA 是 Core 2026.7.2、Supervisor 2026.09.3（自動更新已關）、OS 18.1。更新與回歸依負責人整份核准的 U-019 清單執行，
原更新程序完成後由 Pi 接續唯讀回歸：不輪替 MCP 權杖、不改後端或 policy、不重啟。Core 2026.10.1 沒有在這台實機測試，也沒有升級 Core。

- 原前置（01:53Z）：七支 0.1.8、started；bootstrap 寫入全關、沒有 grant；未完成 Supervisor jobs=0，MemAvailable=8158628 kB、磁碟可用 748.2 GB。
- 商店重載後七支 version_latest 都是 0.1.9；01:55Z 建立七支冷備份 `2d755b1b`（pre-0.1.9 woow mcp apps）。
- 01:56:00–02:23:12Z：原 detached updater 依 n8n、odoo、hermes、opendesign、emqx、litellm、nextcloud 更新，每支第一次成功（rc=0），沒有重試。
- 接手時原 updater 已結束，未完成 jobs=0；七支已是 0.1.9，故沒有重新更新。04:15:04–04:20:29Z 執行原 `VERSION=0.1.9 run-018.sh`。

紀錄在交付線 `e2e/U-019-20261011T015304Z/`（不在 repo）；舊證據保留，新證據另名追加。

## 執行中的映像（HA 主機 `docker inspect`，與發佈一致）

七支 0.1.9、started；接手前置與 S5 identity 的 image ID 均與[發佈紀錄](release-decision-0.1.9.md)逐項相同 7/7。

| 產品 | 執行中的 image ID |
|---|---|
| n8n | `sha256:f7649b4e59bd0f61a9aa84e252f6a4b32c2ea277a3da6c081b30769e9943eda2` |
| odoo | `sha256:93d76737d60183662cd4a7fa85f58564b5850556d0a8ef0e4cf86a1c58ae7ec1` |
| hermes | `sha256:c892e92d6449c969237fd9a9b109b97cc8c17358ffac9251f581e2d3bbd32275` |
| opendesign | `sha256:17f0d660dd163148369cdfc9cc43ff9775442a161546e8726569e81fa7cf9039` |
| emqx | `sha256:79b2c3ddef3cef671f27717d3817c2dd8cfae5231f7d11050ecc257d70709515` |
| litellm | `sha256:9a5b7d9e1da57f8dbe6be584162165ad1c0b2be34c0ea54d72eb60ba03248f93` |
| nextcloud | `sha256:5b811fa2f874719054ad1a66292050ad159239470a1c6b4c507b56563221c4b7` |

## 讀取計畫（與 0.1.8 同一份）

| 產品 | 讀取＋拒絕 | 與 0.1.8 比較 |
|---|---|---|
| n8n | 34/35 | 相同：`n8n_manage_folders` 回 NOT_FOUND（n8n 2.12 沒有資料夾 API） |
| odoo | 40/42 | 相同：`list_models`、`schema_catalog` 回 BACKEND_RPC_FAULT（測試帳號讀不到 `ir.model`） |
| hermes | 27/27 | 相同 |
| opendesign | 16/16 | 相同 |
| emqx | 40/40 | 相同 |
| nextcloud | 11/11 | 相同（只讀測試使用者自己的檔案） |
| litellm | 無後端 | 相同：initialize 502（沒有 child），不是工具測試通過 |

## 0.1.8 行為檢查（`u018_probe.py`，serverInfo 預期 0.1.9）

| 檢查 | n8n | odoo | hermes | opendesign | emqx | litellm | nextcloud |
|---|---|---|---|---|---|---|---|
| 沒帶 session 的 tools/list → 400 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| initialize：serverInfo＝`woow-mcp-<產品>` 0.1.9、capabilities 只有 tools | PASS | PASS | PASS | PASS | PASS | 502（無 child） | PASS |
| 四個審查過的 protocolVersion 協商成審查清單內版本 | PASS | PASS | PASS | PASS | PASS | 502 | PASS |
| session 內 tools/list、DELETE 結束 session | PASS | PASS | PASS | PASS | PASS | — | PASS |

- 六支已配置產品的行為檢查全過：Odoo 14/14（包含 RR-03 兩項），其餘各 12/12。n8n 的版本協商與 Nextcloud instructions 均沿用原測試預期，沒有調整 oracle。
- RR-03：只讀 `id`，不存在的 partner 2147483647 回 not found；測試帳號自己的 partner 12 回 `success=true`、`result={id:12}`。
- LiteLLM 原 probe 統計是 2 pass／7 fail：400 檢查通過，另一 pass 是空回覆沒有 child instructions；後者不代表 initialize 成功。其餘均來自既有未配置的 502。
- GATEWAY-3 在本版未變，依核准清單不重做 31 分鐘閒置測試；既有結果見 [0.1.8 紀錄](ha-test-0.1.8.md)。

## 8081 readiness 與方法閘門

| n8n | odoo | hermes | opendesign | emqx | litellm | nextcloud |
|---|---|---|---|---|---|---|
| 200 | 200 | 200 | 200 | 200 | 503（無後端） | 200 |

七支對 TRACE、PROPFIND、CONNECT、小寫 `get`、`XYZ` 與 POST 未帶權杖均回 401（42/42）。七支管理 bootstrap 均可讀取。

## 收尾、主對話裁定與獨立審查

裁定依據：交付線 `herdr-team-20261011/U019-MAIN-DECISION.md`（2026-10-11，§1–§3）。這是原已核准 U-019 的範圍解釋，非新增 HA 操作授權、非事後補授權，也不代替獨立複審；以下事實引用原 run 與裁定，並非文件修訂時重新連 HA 觀察。

- 更新暫存與備份建立結果先在記憶體掃描後歸檔為 `S6-ha-tmp-resume.tgz`；刪備份前未完成 jobs=0。
- 冷備份 `2d755b1b` 已刪並確認不存在；交接列名的 `/tmp/woow-u019`、`/tmp/u019-backup.json`、`/tmp/ha_p9_probe.py` 均已不存在。沒有刪除共用 e2e 或其他線暫存。
- **兩個 u018 probe 已刪除，主對話確認屬原範圍：** 實際另刪了 `/tmp/woow-u018/u018_probe.py` 與 `/tmp/woow_u018_nc_probe.py`。原 run 的 `S6-cleanup-resume.json` 記錄 `runner_probe_sha256_match=true` 及兩檔 absent；接續報告記錄刪前 SHA256 與指定 runner 原始檔相等，只刪這兩檔並嘗試 rmdir 空目錄。hash 是技術歸屬證據，不單獨替代授權依據。
- 裁定 §2 引用原 `e2e/windows/U-019.md` S5 沿用既有唯讀回歸、S6「刪 HA 暫存檔」及 `HANDOFF-PI-20261011.md` §3.5 指定原 `run-018.sh`。主對話直接核讀該 runner 的 `PROBE_REMOTE=/tmp/woow_u018_nc_probe.py` 與 S5 內 `rm -f /tmp/woow_u018_nc_probe.py`，以及其呼叫的 `driver.mjs` 固定 `REMOTE='/tmp/woow-u018/u018_probe.py'` 並由本輪上傳。因此兩檔屬原 S5/S6 生命周期；HANDOFF §3.6 漏列兩檔不改變原範圍。**此為依原安排的範圍解釋，非事後補授權，不回填為先前逐名批准。** 不重新上傳／刪除補證，不擴大清理整個 `/tmp/woow-u018` 或任何新路徑；共用 e2e 與其他線禁區不變。
- **本輪登入全撤銷：** 14/14 回歸 log 均有 `revoke HA refresh token: 200`；`S6-refresh-metadata-diagnostic.json` 另記診斷登入 revoke=200。指定 recover 的 e2e client 殘留 refresh tokens=0、temporary non-admin users=0。清理前後 bootstrap 的 writes_enabled／disabled／enabled_write_tools／token_active／connection_configured 與 S1 相同 7/7。
- **窗口前根 client 登入 1 筆未更動，依主對話裁定保留：** 該筆建立／最後使用均在 2026-10-09 05:23:34Z，早於 U-019（10-11 01:53Z），不是本輪登入。裁定 §1 以原窗口撤銷本輪臨時登入、指定 e2e client=0、temporary users=0 及 bootstrap 五項相同為驗收範圍；原 `driver.mjs` 的 finally 只撤銷本輪取得的 `tok.refresh_token`。不撤銷、不輪替未知歷史登入，也未授權 `--refresh-tokens` 廣泛刪除；未記錄權杖值或 ID。
- **原追加比較失敗保留：** `S6-postcleanup-verification.json` 的「兩個相關 client 均須為零」strict comparison exit=1 仍是 FAIL；指定 e2e client=0、根 client=1，recover exit=0 不能蓋掉此較廣比較的失敗。證據僅涵蓋這兩個指定 client，**不是所有 HA client 的完整 inventory**，不宣稱根 client 或所有 HA client 零殘留。主對話的範圍裁定不改寫原數字、exit 或失敗歷史。
- 證據 pattern secret scan：JWT／sk token／Bearer／credential assignment／未知 64-hex／email 有效命中均為 0；3 個 email 形狀候選經核對是 EMQX `node` 欄位的內部 Erlang 節點名稱，不是電子郵件。歸檔成員亦在記憶體內掃描；這不宣稱能偵測所有未知秘密格式。
- 2026-10-11T05:07:00Z 獨立收斂審查 PASS／APPROVED，無未解 review blocker（交付線 `herdr-team-20261011/u019-final-review.md` 收斂段）；依主對話裁定完成原 S4/S5/S6 範圍驗收，並非全 HA client 零殘留。唯一 publish-handover writer 依原 S7/S8 驗證、提交、fast-forward 推送，再核對本線 HA-LOCK ownership／無衝突工作後交還；實際 commit／remote SHA／解鎖與 LIFECYCLE-GO 結果另記交付線 `herdr-team-20261011/u019-publish-handover.md`，本文不預先宣稱執行成功。
