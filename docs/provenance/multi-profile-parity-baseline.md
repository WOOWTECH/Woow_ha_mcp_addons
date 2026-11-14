# 多帳號對齊 PaaS 的基準與變動檢查（HM-00，2026-11-14）

## 結論

- 對齊基準（DQ-06 採 (a)）：PaaS `WOOWTECH/woow-mcp-server` main **`69ac425`**。之後的 PaaS 變動不自動收進來，每片開工前用第 4 節的指令列出、
  逐片寫進 provenance 筆記。
- 2026-11-14 14:20（台北）fetch 後：`origin/main` 是 **`7d111b1`**，比 pin 多兩次合併（第 3 節）：
  - #150（`091dfbc` 那條 #148 後續）：只改文件、測試與註解，可執行碼和 pin 相同。對 HA：HM-14 的已知限制與 HM-08 的位元組額度佐證改引新文件。
  - **#149（紀錄遮罩的 query 憑證）已在 14:19 合併**：正式碼只動 `log_redaction.py`。對 HA：照 DQ-06 收進來，HM-02 以
    `7d111b1` 的 `log_redaction.py` 與測試為對照來源（vendor 或移植看 DQ-38）；`paas-test-mapping.md` 把它的測試併進 D 組。
- 除了 `log_redaction.py`，第 2 節清單上的正式碼在 `7d111b1` 和 pin 相同（只改註解的兩個檔以 AST 比對確認）。
- HA 基準：`WOOWTECH/Woow_ha_mcp_addons` `claude-delivery` @ `bb48449`。

## 1. 基準 commit

| 名稱 | commit | 時間（UTC） | 內容 | 狀態 |
|---|---|---|---|---|
| PaaS pin | `69ac425cd28b`（全長 `69ac425cd28ba4665319939b33ae6eefc8e67281`） | 2026-11-14 02:32 | `443e95a`（正式站）＋#147 `e85f21e`（還原手冊後續）＋#148（閘道排隊、通知保留名額、`-32004` 依原因、子程式長行） | 對齊基準 |
| PaaS 正式站 | `443e95a942c7` | — | 24 台正式站跑的版本；和 pin 的正式碼只差 `gateway_pool.py`、`initialize_fence.py`、`process.py`、`proxy.py` | 參考 |
| #150 合併 | `5a06d533eb43` | 2026-11-14 04:47 | `docs/gateway-148-followups-20261114`（`19f36e2`、`82c6929`、`091dfbc`） | pin 之後（第 3 節） |
| #149 合併 | `7d111b175fbb` | 2026-11-14 06:19 | `fix/log-redaction-query-credentials-20261113`，head `3d33bc5`（計畫定稿時是 `72066b6`，之後只多 `3d33bc5`，只改 `CLAUDE.md`） | pin 之後（第 3 節）；目前的 `origin/main` |
| HA 基準 | `bb48449` | 2026-11-12 | `claude-delivery`（#88 Headscale 0.4.18 合併） | 實作起點 |

#149 改的檔（`T/` ＝ `packages/mcp-admin-core/tests/`）：`CLAUDE.md`、`packages/mcp-admin-core/mcp_admin_core/log_redaction.py`、
`T/fixtures/log_redaction_443e95a.py`、`T/test_log_redaction.py`、`T/test_log_redaction_query_credentials.py`、
`T/test_log_redaction_query_credentials_review.py`。後兩個測試檔有字面 64 hex 值，vendor 前要先過秘密預檢、換成執行時產生（計畫 §8.6）。

## 2. PaaS 相關檔清單（HA 對齊時要看的檔）

路徑相對 PaaS repo 根目錄；`C/` ＝ `packages/mcp-admin-core/mcp_admin_core/`。測試檔另見 `docs/multi-profile/paas-test-mapping.md`
（pin 的 53 檔，加上 pin 之後併進來的 3 檔）。

| PaaS 檔 | 對應的 HA 片 |
|---|---|
| `C/profiles.py`、`C/routers/profiles.py` | HM-07、HM-09、HM-10 |
| `C/proxy.py`、`C/gateway_pool.py` | HM-08、HM-14 |
| `C/initialize_fence.py` | HM-14 |
| `C/process.py`、`C/child_identity.py` | HM-09、HM-15 |
| `C/restore_guard.py`、`C/restore_inplace.py` | HM-13b |
| `C/restore_marker.py` | HM-13a |
| `C/owner_defaults.py` | HM-13b（`RESTORE_POLICY_HOLD`，§8.8 #66） |
| `C/launch_policy.py` | HM-07（身分欄位）、HM-09 |
| `C/log_redaction.py` | HM-02 |
| `C/origin_security.py` | HM-27 |
| `C/setup_status.py` | HM-09（§8.8 #68 的對照） |
| `C/config/store.py`、`C/connection_apply.py` | HM-07、HM-12 |
| `C/routers/logs.py` | HM-09（§8.8 #29 的對照） |
| `C/routers/tokens.py`、`C/routers/settings.py`、`C/operations.py` | HM-10、HM-13b |
| `C/app.py` | HM-05 |
| `C/security_headers.py` | HM-11（§8.8 #57） |
| `packages/mcp-admin-ui/src/api.js`、`profileStatus.js`、`useDurableOperation.js` | HM-11 |
| `apps/odoo/odoo_mcp_admin/main.py` | HM-12 |
| `apps/litellm/litellm_mcp_admin/main.py` | HM-21 |
| `apps/nextcloud/nextcloud_mcp_admin/main.py` | HM-22 |
| `apps/emqx/emqx_mcp_admin/main.py` | HM-23 |
| `apps/hermes/hermes_mcp_admin/main.py` | HM-24 |
| `apps/n8n/n8n_mcp_admin/main.py` | HM-25 |
| `apps/headscale/headscale_mcp_admin/main.py`、`connection.py` | HM-26 |
| `docs/mcp-gateway-limits.md`、`docs/shared-token-lifecycle.md` | HM-08、HM-14 |
| `docs/security/mcp-child-identity.md` | HM-06、HM-15 |
| `docs/paas-config-restore-runbook.md` | HM-13b、HM-13c |
| `docs/security/mcp-origin-policy.md` | HM-27 |

上表每個檔在 `69ac425` 都存在（`git cat-file -e 69ac425:<檔>` 逐一確認）。

## 3. pin 之後的變動（`git log 69ac425..origin/main`，`origin/main`＝`7d111b1`）

| commit | 時間（台北） | 內容 | 動到的相關檔 | 對 HA 的影響 |
|---|---|---|---|---|
| `19f36e2` | 11-14 12:00 | #148 合併後的文件更正：斷線保護的準確範圍、access log、惡意 Location 的殘留、背壓說法、排隊請求的記憶體估算 | `docs/mcp-gateway-limits.md`、`C/gateway_pool.py`、`C/proxy.py`（註解與 docstring）、`CLAUDE.md` | HM-14 的已知限制照新文字寫（MCP Python SDK 2.3.0 預設 `terminate_on_close=True` 時排隊中的寫入仍可能被執行）；HM-08 的位元組額度佐證（「排隊上限算個數不算位元組，1 GiB pod 上 32 個約 4 MiB 的請求就可能 OOM」）改引新文件 |
| `82c6929` | 11-14 12:00 | 補 #148 增量覆核的測試缺口 | `T/test_gateway_queue.py`（只改既有案例，沒有新增或刪除案例） | HM-14 對照 `test_gateway_queue.py` 時以新內容為準；歸屬不變 |
| `091dfbc` | 11-14 12:22 | 惡意 Location 一段改成沙盒實際試過的範圍與沒驗證的部分 | `docs/mcp-gateway-limits.md` | 沒有：HA 不轉子程式的 Location（§8.8 #4） |
| `5a06d53` | 11-14 12:47 | 合併 #150 | — | — |
| `4c27e78`、`ce78bf5`、`dde6e15`、`83526e8`、`c3443a5`、`d587fd3`、`db1b9f8`、`72066b6`、`3d33bc5` | 11-14 01:13～12:53 | #149：query 憑證值（`?token=` 前後夾編碼分隔字元、`api_key`／`key`／`secret`／`password`／`sig` 等鍵名）不再留在 log；單調性與冪等；效能；回歸測試；`CLAUDE.md` | `C/log_redaction.py`（正式碼）、`T/fixtures/log_redaction_443e95a.py`、`T/test_log_redaction.py`、`T/test_log_redaction_query_credentials.py`、`T/test_log_redaction_query_credentials_review.py` | HM-02：對照來源改成 `7d111b1` 的 `log_redaction.py` 與兩個新測試檔（64 案併進 `paas-test-mapping.md` D 組）；「不比 pin 版 PaaS 差」的動態門檻用合併版重算；vendor 前先處理測試檔裡的字面 64 hex |
| `7d111b1` | 11-14 14:19 | 合併 #149 | — | — |

可執行碼確認：`C/gateway_pool.py`、`C/proxy.py` 在 `69ac425` 與 `7d111b1` 之間，去掉 docstring 與註解後的 AST 完全相同；
`C/log_redaction.py` 不同（#149 的正式變動）。`git diff --name-only 69ac425 origin/main` 對第 2 節清單與 pin 的 53 個測試檔列出
`docs/mcp-gateway-limits.md`、`C/gateway_pool.py`、`C/log_redaction.py`、`C/proxy.py`、`T/test_gateway_queue.py` 五個檔。

## 4. 變動檢查指令（每片開工前跑；在連得到 Gitea 的 PaaS clone 裡，只讀）

```sh
P=<PaaS clone>                     # 不要 checkout、不要改工作目錄
C=packages/mcp-admin-core/mcp_admin_core
git -C "$P" fetch origin
git -C "$P" rev-parse --short origin/main
# 1) pin 之後，第 2 節清單上的檔有沒有變（測試檔清單見 paas-test-mapping.md）
git -C "$P" log --oneline 69ac425..origin/main -- \
  $C/profiles.py $C/routers/profiles.py $C/proxy.py $C/gateway_pool.py $C/initialize_fence.py \
  $C/process.py $C/child_identity.py $C/restore_guard.py $C/restore_inplace.py $C/restore_marker.py \
  $C/owner_defaults.py $C/launch_policy.py $C/log_redaction.py $C/origin_security.py $C/setup_status.py \
  $C/config/store.py $C/connection_apply.py $C/routers/logs.py $C/routers/tokens.py $C/routers/settings.py \
  $C/operations.py $C/app.py $C/security_headers.py \
  packages/mcp-admin-ui/src/api.js packages/mcp-admin-ui/src/profileStatus.js packages/mcp-admin-ui/src/useDurableOperation.js \
  apps/*/*_mcp_admin/main.py apps/headscale/headscale_mcp_admin/connection.py \
  docs/mcp-gateway-limits.md docs/shared-token-lifecycle.md docs/security/mcp-child-identity.md \
  docs/paas-config-restore-runbook.md docs/security/mcp-origin-policy.md
# 2) 變了哪些檔；只改註解的檔再比一次 AST（去掉 docstring 與註解）確認可執行碼沒變
git -C "$P" diff --stat 69ac425 origin/main
# 3) 新的測試檔或新案例：重產 paas-test-mapping.md（repo 外的產生器），新檔要補歸屬
git -C "$P" diff --name-only 69ac425 origin/main -- '*test*'
```

結果寫進該片的 provenance 筆記：有變動就列 commit、動到的檔與對 HA 的影響；沒有就寫「無變動」與 `origin/main` 的 commit。

## 5. 檢查紀錄

| 時間（台北） | origin/main | 結果 |
|---|---|---|
| 2026-11-14 13:39（HM-00 開工） | `5a06d53` | #150 的 3 個 commit；可執行碼和 pin 相同；#149 未合併（head `3d33bc5`） |
| 2026-11-14 14:20（HM-00 commit 前重查） | `7d111b1` | 多了 #149 合併；正式碼只動 `log_redaction.py`；已照第 3 節更新本檔與 `paas-test-mapping.md` |
