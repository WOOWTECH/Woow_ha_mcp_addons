# 0.1.9 發佈紀錄（2026-10-11）

**狀態：** 2026-10-11 發佈（experimental）。七支映像由 57c96f2 建置、通過 gate，以測過的 image ID 推送 GHCR，並以匿名 registry_gate public 驗證；2026-10-11 已在測試 HA 回歸（[ha-test-0.1.9](ha-test-0.1.9.md)，窗口 U-019；既有後端限制不變）。2026-10-11 獨立收斂審查 PASS，依主對話裁定完成原範圍驗收；依主對話 `U019-MAIN-DECISION.md`（2026-10-11）裁定，本輪 14/14 與診斷登入已撤銷、指定 e2e client=0、temporary users=0，窗口前根 client 登入 1 筆保留未更動；兩個 u018 probe 屬原 S5/S6 指定 runner 本輪暫存清理範圍，非事後補授權。原追加兩相關 client strict comparison exit=1 保留，不代表所有 HA client inventory；詳細依據見回歸文件。審查通過不等於推送或 HA 交還已成功，S7/S8 結果以實際回執為準；既有映像發佈不等於本次窗口已交還。

**依據：** 負責人 2026-10-11「現在就發 0.1.9」，只為了支援 Core 2026.10.1；之後的 Core patch 維持逐版審查。發佈與 woowtech-ha 更新清單（P-019＋U-019）整份核准。

## 已通過（映像來源 `57c96f27a6a98e78aee0439e041ae6936b04b573`）

- 全套 `tests/`：1845 passed、1 failed——唯一的失敗是要求以 root 執行的 `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof`（這個容器是 uid 1000），與本版無關；packaging unittest 149 OK（5 skipped）；validate PASS。
- builder VM：候選 57c96f2（rc-57c96f2，2026-10-11 01:07–01:35Z）七支 P1–P5 全過；以測過的 image ID 推送（不重建），匿名 registry_gate public 七支 PASS。證據在 Claude 交付線 evidence-rc-57c96f2/。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） | GHCR manifest digest（匿名 registry_gate public） |
|---|---|---|
| odoo | `sha256:93d76737d60183662cd4a7fa85f58564b5850556d0a8ef0e4cf86a1c58ae7ec1` | `sha256:b43bfeb1ede1f66d609ca48d2ed1a458f5400a2ef94ef79b86ef94c97a3ede28` |
| n8n | `sha256:f7649b4e59bd0f61a9aa84e252f6a4b32c2ea277a3da6c081b30769e9943eda2` | `sha256:a24d78b9fe0b804cdd3435ba5806342910a23edad2dde320ca3a762420dce8d2` |
| hermes | `sha256:c892e92d6449c969237fd9a9b109b97cc8c17358ffac9251f581e2d3bbd32275` | `sha256:d6b2ee2b0f0e523a6f2ae327e94f0ed9b06329de6748fa7e1c8321e0d5eb6dfa` |
| opendesign | `sha256:17f0d660dd163148369cdfc9cc43ff9775442a161546e8726569e81fa7cf9039` | `sha256:14ae0e753035c27b2e2ade68c31c4ff47a1b93ce66acd9526d928dd15ac366ad` |
| emqx | `sha256:79b2c3ddef3cef671f27717d3817c2dd8cfae5231f7d11050ecc257d70709515` | `sha256:ed783acba241e43061594b3dfe99f4171653be8b8e96d48305bd44e7a7144b21` |
| litellm | `sha256:9a5b7d9e1da57f8dbe6be584162165ad1c0b2be34c0ea54d72eb60ba03248f93` | `sha256:01c8b9f8586b30f96ad7b991e86e1a84b1745b86ac7dcea072ac12909d68617e` |
| nextcloud | `sha256:5b811fa2f874719054ad1a66292050ad159239470a1c6b4c507b56563221c4b7` | `sha256:962f4e0731dc5d63d169b58327b14027472c0fa63eb9df1fb13994590bb8257a` |

商店分支：發佈後 `claude-delivery` fast-forward 到發佈文件 commit（緊接在 57c96f2 之後，只改文件）；release tag v0.1.9 指向映像來源 57c96f2。

## 未驗

- Core 2026.10.1 上的管理面板沒有實機測（woowtech-ha 是 Core 2026.7.2），由單元測試與合約檔比對涵蓋。


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
