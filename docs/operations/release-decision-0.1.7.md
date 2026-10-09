# 0.1.7 發佈紀錄（2026-10-08）

**狀態：** 2026-10-08 發佈（experimental）。七支映像由 7cc8bcb 建置、通過 gate，以測過的 image ID 推送 GHCR，並以匿名 registry_gate public
驗證（Nextcloud 在負責人把新的 GHCR package 改為公開之後）；2026-10-08 已在測試 HA 回歸（[ha-test-0.1.7](ha-test-0.1.7.md)）。

**依據：** 0.1.6 紀錄中「不在 0.1.6」的第七支 Nextcloud（另一條開發線，[release-decision-0.1.6](release-decision-0.1.6.md)）在 0.1.7 首次發佈；
所有 add-on 共用同一個版號，所以既有六支隨同重建，功能不變。負責人 2026-10-08：核准 defusedxml 0.7.1 以版本釘選的
`known_package_licenses` 條目判為 PSF-2.0；核准 Nextcloud 和其他六支一樣有 `homeassistant_api: true`、`SUPERVISOR_TOKEN` 只給管理程序；
把新的 GHCR package `amd64-mcp-nextcloud` 改為公開（新 package 預設私有，GitHub 沒有 API 可改）。以及 Nextcloud 各輪審查（R1、R2、R3）
與交付線最後的差異檢查。

## 內容（映像來源 `7cc8bcb69c05ef156a0b0e1cee93e3967244007e`）

- 新產品 WOOW Nextcloud MCP（`addons/nextcloud`、`apps/nextcloud`）：一個 Add-on 連一個 Nextcloud 帳號（根網址、使用者名稱、App 密碼，
  在管理面板設定）。子程序是 WOOWTECH 的 MIT 套件 `nextcloud_mcp_server`，vendored 上游 `WOOWTECH/Woow_nextcloud_mcp_server` v0.1.5
  （commit 4e09c86），本地修改三處（client.py、server.py、tools.py），原因逐檔記在 `docs/provenance/runtime-sources.json`。上游 9 個工具
  全部支援：5 個讀取預設開啟，4 個寫入預設關閉、要逐項授權；行為與限制見 [Nextcloud DOCS](../../addons/nextcloud/DOCS.md) 與 CHANGELOG。
- 共用核心、封裝與管理 UI 加入第七支產品：連線與工具定義、policy 變更時重啟子程序（同 EMQX／LiteLLM）、entrypoint／launcher／validate／
  inputs、CI 與 release matrix、RELEASE-GATES（維持關閉）、管理面板的後端表單。
- 負責人決定的落實（36a763e）：`packaging/supply-chain-policy.json` 的 `python:defusedxml:0.7.1` = `PSF-2.0`（metadata 只有 `PSFL`，
  附的授權文字是 PSF License 2）；Nextcloud 的 `homeassistant_api: true` 與管理程序的 `SUPERVISOR_TOKEN`（child 不繼承）。
- 程式 commit：16667cd（vendor v0.1.0）、40f81ad（第七支產品）、7bc4994（經真實子程序與 gateway 的測試）、95b5d46（R1 修正）、
  e3fbf1e（跟上已發佈的 0.1.6 版號；`vendor_runtimes.py --stage` 一次只重新 vendor 一個產品）、77edffc（re-vendor v0.1.3）、36a763e（負責人決定）、
  9c1416a（R2 修正）、051f4bb（re-vendor v0.1.4）、371c47c（R3 修正）、62d1f7b（re-vendor v0.1.5）；版號 0.1.6→0.1.7（獨立 commit）：7cc8bcb。
- 既有六支：所有 add-on 共用同一個版號與共用核心，所以隨同重建（映像內的共用核心也帶著新增的 Nextcloud 定義），功能沒有變動，
  各支 CHANGELOG 已註明。0.1.6 留下的 0.1.7 待辦本版刻意不做，改列 0.1.8（見文末）。
- 不在 0.1.7：Odoo Manage 維持下架、不建置（版號維持 0.1.4）。

## 已通過

- 審查（唯讀子代理；原文在 Claude 交付線 reviews-017/）：
  - R1（nextcloud-R1.md）REQUEST CHANGES（合併後 high 0／medium 1／low 9）：唯一的 medium 是私有健康探測在帳密錯誤時反覆送出失敗的登入，
    會觸發 Nextcloud 的暴力破解防護、封鎖 Add-on 所在的 IP。於 95b5d46 與 re-vendor 上游 v0.1.3（77edffc；401 鎖到子程序重啟、429 停
    5 分鐘是上游行為）處理。
  - R2（nextcloud-R2.md，6c4d2ba..77edffc，另看過 36a763e）APPROVE WITH NOTES（low 10）：R1 十項已修 7、部分 3；本輪問題於 9c1416a 與
    re-vendor 上游 v0.1.4（051f4bb）處理。
  - R3（nextcloud-R3.md，77edffc..051f4bb）APPROVE WITH NOTES（low 7）：R2 十項已修 9、部分 1；本輪問題於 371c47c 與 re-vendor 上游
    v0.1.5（62d1f7b）處理。
  - R3 之後的變更由交付線做最後的差異檢查。
  - 既有六支沒有功能變動，本版沒有另外審查它們。
- 全套 `tests/`（映像來源 7cc8bcb，tree `76ed9ada`）：第一次（Claude 交付線 tests-017/run1）31 failed／1724 passed。31 個都要用封存的
  Odoo Manage 的釘選子程序環境 `apps/odoo-manage/.venv`，而新的 0.1.7 worktree 還沒連結它（29 個是 odoo-manage 的測試，2 個 tool_inventory
  測試讀這個 venv 的原始碼）；連結後這 31 個都通過（tests-017/run1/NOTE.txt）。同一個 tree 重跑全套（tests-017/run2）：1755 passed／
  0 failed／0 error／0 skipped；packaging 147 OK；validate PASS（七份 manifest）。
- builder VM：候選 7cc8bcb（rc-7cc8bcb，2026-10-08 04:59–05:27Z）七支 P1–P5 全過：build、container/mock、supply-chain gate（source／history／
  image／evidence secrets、SBOM、CVE、license）；Nextcloud 第一次送 gate 就通過（license 檢查用的 policy 含 defusedxml 0.7.1 的條目）。
  以測過的 image ID 推送（不重建）；推送後匿名 registry_gate public 七支 PASS，Nextcloud 是在負責人 2026-10-08 把 `amd64-mcp-nextcloud`
  改為公開之後。證據在 Claude 交付線 evidence-rc-7cc8bcb/。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） | GHCR manifest digest（匿名 registry_gate public） |
|---|---|---|
| odoo | `sha256:bf41b7ec9fd225e8baacd6eef279f6c4face2fde30b9d3e6c4a3fb694dc11500` | `sha256:4a98095dd8f73dd65382ec81a0768b1cf883176f10f4c5487dc132d981e5c6bc` |
| n8n | `sha256:16875a6fc4c3a4df39e347511e159199b9ac1a61dea4e8229314e73fdd6518eb` | `sha256:2b70f836433220e7c63a94a4c993787dc62d66750002cfb3ec0a6878f7476956` |
| hermes | `sha256:884c2acc62d93fce9b1952bfbb5e3bca5cb47f3909d1bf05a8495467df020d32` | `sha256:6769208f635d55e5ddf10ea0f8af038cb47af5f23703d0a70a495f5c00de032b` |
| opendesign | `sha256:c088352b490a43535c0d9012622f63a9bf91b39a8f8e81dce6b020b3a5fbb1be` | `sha256:1575353632e5d1ed7c9cea3bb7d800901346ed9bfa5433defa6c07c630052f56` |
| emqx | `sha256:107f4a115304ef9103dd2da3a9f749ef8211ed81ab727621248aa1dd06d69893` | `sha256:c8ab850cd6e5e3a8032b57fb672e11d787758f30f86fe076f7a3e36402a216a5` |
| litellm | `sha256:de2fcd69470d0f20c107053863437ba9a5fc1442bb5fdf64adee6d694fbc63e3` | `sha256:ebfb1630d3b1be299b3d5189b4211ba3770e8c75134a2c2a057424eb0c485d34` |
| nextcloud | `sha256:1d0688fcb7bd218d86fbdc6745411d06f0426d49e5ca8b4da9e1c2b6585d1850` | `sha256:4d8002435da66809f53d0f7b6f4fd7e7e0a34f1c958c348f18ace3c2ff57aef3` |

商店分支：發佈後商店分支（`claude-delivery`）由 6c4d2ba fast-forward 到發佈文件 commit。映像來源：7cc8bcb；發佈文件 commit：本 commit
（緊接在 7cc8bcb 之後，只改文件）；release tag v0.1.7 指向映像來源 7cc8bcb。本 commit 改了 `THIRD_PARTY_NOTICES.md`（Nextcloud 那一列
不再寫 not yet released），這個檔案會複製進映像（`/opt/woow/THIRD_PARTY_NOTICES.md`）：已發佈映像內是 7cc8bcb 的版本，映像不重建
（[release-decision-2026-10-05](release-decision-2026-10-05.md)：映像內的是建置當時的版本，最新授權說明以 repo 的 `docs/licenses/` 為準）。
其他改動都不在映像內。

## 未通過／未驗

- 真 HA：2026-10-08 依負責人核准的窗口 U-017，woowtech-ha 六支更新到 0.1.7、安裝 Nextcloud MCP 並回歸通過（[ha-test-0.1.7](ha-test-0.1.7.md)）：
  映像身分 7/7；六支結果與 0.1.6 相同；Nextcloud 讀取 6/6、拒絕 5/5、後端斷線、重啟、child 恢復、權杖、一般使用者 403 皆通過（後端是
  同一台 HA 的 Nextcloud 35.0.1，專屬一般使用者）。仍未驗：Nextcloud 寫入工具的實機授權、管理員帳號以外的 Ingress UX、備份還原。
- 管理面板支援的 Core 版本與 0.1.6 相同（2026.7.2–2026.9.4 與 2026.10.0），真機證據只有 Core 2026.7.2（0.1.6 回歸）。清單外的 Core 版本
  （含之後的 patch）照樣整個管理面板 403，要照 [ha-role-core-contract](../ha-role-core-contract.md) 的「Adding a release」審查後發新版。
- aarch64 未建；LAN client、LiteLLM 工具（無後端）未測；真實 MCP client（同 HA Pi／Omnigent／Hermes、HA Assist、n8n AI Agent 等）未驗收。
- AI 供應商測試：0.1.7 沒有重做；2026-10-07 的複驗（30/30）是 0.1.6 六支的工具清單，Nextcloud 沒有做這項測試。
- 文件（DOCS 的版本行、README、操作指南與 client 文件的目前版本、CHANGELOG 的「準備中」、授權清單）在映像建置後由本 commit 更新；
  Nextcloud 的授權清單改成由映像 SBOM 產生的 `nextcloud-0.1.7.md`，原本由 lock 產生的暫代清單已移除。

## 0.1.8 待辦（0.1.6 留下的 0.1.7 待辦；0.1.7 刻意不改既有六支的行為，所以原樣延後）

- 映像標籤 `io.hass.name` 仍是 0.1.7 的「WOOW ○○ MCP」；2026-10-09 起顯示名稱是「Woow ○○ MCP Server」（manifest 已改，映像不變），下一版重建時一併改標籤。

這幾項是共用 gateway 或 Python 子程序的既有問題。0.1.7 新增的 Nextcloud 共用同一個 gateway，子程序和 EMQX 一樣是 FastMCP 3.4.5、
啟動時沒有帶閒置設定，預期也受影響（未另外實測）。

- 被 policy 拒絕的 tools/call 仍回 HTTP 403（0.1.5 RC F7、0.1.6 RC RELEASE-4，既有問題）：Python MCP SDK 1.x client 會整段斷線、
  不送 DELETE，每次留下一個子程序 session（n8n 共用的 20 個 session 用完後，所有 client 的 initialize 都回 429，要等閒置 10 分鐘回收；
  其他各支累積到子程序重啟）。設計筆記 f7-design.md 建議只把 policy 拒絕的 tools/call 改回 HTTP 200、body 為固定的 isError
  「request denied」（C 方案），待負責人決定。
- initialize 回覆的 serverInfo、instructions 仍是子程序內容（Claude Code 會把 instructions 放進 system prompt；0.1.6 R1 F6）。
- 五支 Python 子程序沒有 `session_idle_timeout`（0.1.6 RC GATEWAY-3，既有問題）：一般 session 只在 client 送 DELETE 或子程序重啟時結束。
  兩種做法：在各支啟動處讓 session manager 帶 `session_idle_timeout`（FastMCP 不轉這個參數，要包一層），或由 gateway 記錄交出的
  session、對閒置過久的送 DELETE；都要先量測單一閒置 session 的記憶體再定上限。
- 沒帶 `Mcp-Session-Id` 的 initialize 以外請求照樣轉給子程序（0.1.6 RC GATEWAY-2，既有問題）：五支 Python 子程序每次開一個 session 並留下來。
  做法：gateway 直接回 400、不轉送，或放寬結束 session 的條件；補「沒有 session 的 ping／GET／DELETE 不會增加子程序 session」的測試。
- Core 版本清單（待負責人決定，不是程式待辦）：目前每個新的 Core 版本（含 patch）都要審查並發 add-on 新版；0.1.6 R2-harole 提的
  「已審 minor 的後續 patch 也接受，加上監看」待真機測試後由負責人決定。
