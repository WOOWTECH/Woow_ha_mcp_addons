# 0.1.6 發佈紀錄（草稿）

**狀態：** 2026-10-08 起草，映像尚未建置。發佈日期與標「（建置後填入）」的地方在映像建置、推送 GHCR 後補上；發佈時標題改成發佈日期。

**依據：** 0.1.5 留下的 0.1.6 待辦（[release-decision-0.1.5](release-decision-0.1.5.md)）；0.1.5 只認 Core 2026.7.2，Core 升級後管理面板
整個 403；AI 測試第 0 階段（B0）經 OpenRouter 發現 Claude、GPT 拒收 n8n、Odoo、Hermes 的工具清單（負責人決定 D21）；Core 2026.10.0
（2026-10-07 發佈）；以及 0.1.6 各輪審查（R1、R2-harole、R3-init-cleanup、R4-schema-flatten、RC）的意見。

## 內容（映像來源 （建置後填入））

- 管理面板（HA 角色驗證，六支共用同一個驗證器）：原本只認 Core 2026.7.2，改為經原始碼審查的 13 個版本：2026.7.2–2026.9.4 與
  2026.10.0（`ha_role._HA_VERSIONS`，審查紀錄 [ha-role-core-contract](../ha-role-core-contract.md)）；`auth_required` 與 `auth_ok`
  回報的版本必須相同。清單外的版本（含之後的 patch 與 beta）照樣拒絕：整個管理面板回 403，看起來和非管理員相同；MCP 端點
  （Bearer）不受影響。六支 DOCS.md、README 與操作指南已寫明支援的版本與這個限制。
- gateway：tools/list 由 gateway 重新組成：只留工具清單與字串型 nextCursor，同名只留第一個；名稱與 inputSchema 用 gateway 自己的定義，
  title、description、annotations.title 只在是字串時保留，四個 hint 只留保守值（本地沒有寫入路徑的工具才留放寬值）；outputSchema、
  execution、icons、_meta 與其他欄位不再轉送（0.1.5 RC F3）。
- gateway：拒絕 initialize 時，子程序已開的 session 由 gateway 送一次 `DELETE /mcp` 結束（只限 gateway 會轉送、且不是 client 自帶的 id；
  在同一個請求名額內、最多等 2 秒，回應不讀、不轉送，session id 不寫紀錄）；client 收到的回覆不變（0.1.5 R2 觀察）。
- gateway：tools/list 宣告的 inputSchema 頂層一律是 `type: object`。7 個工具（n8n `n8n_manage_folders`；Odoo `diagnose_odoo_call`、
  `generate_json2_payload`；Hermes `hermes_skill`、`hermes_tools`、`hermes_session`、`hermes_cron`）拿掉頂層 oneOf／allOf，分支規則改寫成
  description 的英文短句；驗證不變，gateway 仍用原本嚴格的 pydantic 模型檢查每個呼叫（D21）。
- 程式 commit：518253a、a7dfcd0（tools/list）；79302e1、c8f601e、d9b50ac（Core 版本清單）；37013ca（initialize 收尾）；df3aaae（schema
  扁平化）。e4828da 合併商店分支到 797d4e1（含 92e9695；只改 README、docs/operations 與 `addons/odoo/DOCS.md` 一段，都不在映像內）。
  RC 文件修正：（建置後填入）；版號 0.1.5→0.1.6（20 處，獨立 commit）：（建置後填入）。
- 不在 0.1.6：Nextcloud（第七支 add-on，在另一條開發線）；Odoo Manage 維持下架、不建置。
- 0.1.5 留下的 0.1.6 待辦：RC F3 與「initialize 回 502 時子程序 session 沒關」已在本版處理；RC F7 延到 0.1.7（見文末）；ledger 罕見的
  動態載入仍靠審查（0.1.5 R2 #1，本版未改）。

## 已通過

- 審查（唯讀子代理；原文在 Claude 交付線 reviews-016/）：
  - R1（518253a）APPROVE WITH NOTES：F1–F5 於 a7dfcd0 處理；F6 延後（見文末）。
  - R2-harole（79302e1）APPROVE WITH NOTES：L1–L3 於 c8f601e 處理；M1（2026.10.0 一出清單就過時）新增 Core 契約監看工具，2026.10.0
    正式版逐行審查後於 d9b50ac 加入。
  - R3-init-cleanup：實作、審查 APPROVE WITH NOTES、修正，成為 37013ca。
  - R4-schema-flatten：實作、審查 APPROVE WITH NOTES、修正、真供應商重驗，成為 df3aaae。
  - RC 發佈候選完整審查（8b7ce2d..d9b50ac）REQUEST CHANGES（high 0／medium 1／low 7），沒有 0.1.6 引入的程式回歸。唯一的 medium
    RELEASE-3（使用者文件沒寫支援的 Core 版本）與 HAROLE-3、HAROLE-4、RELEASE-6、RELEASE-7 都是文件缺口，在 RC 文件修正 commit 處理
    （RC：RELEASE-3 修正後沒有 high／medium，符合 APPROVE WITH NOTES 的條件）；GATEWAY-2、GATEWAY-3、RELEASE-4（F7）是 0.1.6 之前就有的程式問題，延到 0.1.7，寫進六支 CHANGELOG 的已知問題與
    [client 文件](clients.md)。
- 全套 `tests/` 1644 passed／0 failed／0 error／0 skipped；packaging 147 OK；validate PASS（Claude 交付線 tests-016/run7，tree `9913ce7b`
  ＝d9b50ac）。之後的商店合併、RC 文件修正與版號 commit 都不在其中，要在版號 commit 上重跑：（建置後填入）。
- 供應商重驗（B0 複驗 016，2026-10-07，經 OpenRouter；Claude 交付線 e2e/B0-recheck-016-20261007T1040Z/）：宣告的 schema 送五個模型 ×
  六支，接受度由 B0 的 24/30 變成 30/30（Claude、GPT 對 n8n、Odoo、Hermes 都回 200）；直連 Anthropic／OpenAI API 與實際 client 未測。
- builder VM：六支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）：（建置後填入）。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） | GHCR manifest digest（匿名 registry_gate public） |
|---|---|---|
| n8n | （建置後填入） | （建置後填入） |
| odoo | （建置後填入） | （建置後填入） |
| hermes | （建置後填入） | （建置後填入） |
| opendesign | （建置後填入） | （建置後填入） |
| emqx | （建置後填入） | （建置後填入） |
| litellm | （建置後填入） | （建置後填入） |

商店分支：0.1.6 已先合併商店分支的 797d4e1（e4828da），發佈後商店分支可 fast-forward 到 0.1.6。映像來源：（建置後填入）；
發佈文件 commit：（建置後填入）；release tag v0.1.6 指向映像來源：（建置後填入）。

## 未通過／未驗

- 真 HA：只有 Core 2026.7.2 有真機證據（woowtech-ha，Supervisor 2026.09.3；Claude 交付線 e2e/ 的 M1a、O-D11 報告，2026-10-07）：
  測試用 HA 管理員經 Ingress 讀六支的管理 API，角色驗證放行；當時執行的是 0.1.5 映像。2026.7.3–2026.10.0 只靠原始碼審查與本機
  loopback 測試，沒有真機證據。0.1.6 映像在測試 HA 的回歸：（建置後填入）。
- 發佈前要用 core-contract-watch 再確認 Core 2026.10.1 是否已發佈（2026-10-08 查詢時最新是 2026.10.0）。若已發佈，0.1.6 在該版的
  管理面板整個 403；要納入就照 [ha-role-core-contract](../ha-role-core-contract.md) 的「Adding a release」。
- aarch64 未建；LAN client、LiteLLM 工具（無後端）未測；真實 MCP client（同 HA Pi／Omnigent／Hermes、HA Assist、n8n AI Agent 等）未驗收。
- 文件（DOCS 的版本行、README 與 client 文件的目前版本、CHANGELOG 的「準備中」、授權清單）在映像建置後更新，不在映像內，不影響已測映像。

## 0.1.7 待辦（審查留下、0.1.6 未改程式的部分）

- 被 policy 拒絕的 tools/call 仍回 HTTP 403（0.1.5 RC F7、0.1.6 RC RELEASE-4，既有問題）：Python MCP SDK 1.x client 會整段斷線、
  不送 DELETE，每次留下一個子程序 session（n8n 共用的 20 個 session 用完後，所有 client 的 initialize 都回 429，要等閒置 10 分鐘回收；
  其他五支累積到子程序重啟）。設計筆記 f7-design.md 建議只把 policy 拒絕的 tools/call 改回 HTTP 200、body 為固定的 isError
  「request denied」（C 方案），待負責人決定。
- initialize 回覆的 serverInfo、instructions 仍是子程序內容（Claude Code 會把 instructions 放進 system prompt；R1 F6）。
- 五支 Python 子程序沒有 `session_idle_timeout`（RC GATEWAY-3，既有問題）：一般 session 只在 client 送 DELETE 或子程序重啟時結束。
  兩種做法：在各支啟動處讓 session manager 帶 `session_idle_timeout`（FastMCP 不轉這個參數，要包一層），或由 gateway 記錄交出的
  session、對閒置過久的送 DELETE；都要先量測單一閒置 session 的記憶體再定上限。
- 沒帶 `Mcp-Session-Id` 的 initialize 以外請求照樣轉給子程序（RC GATEWAY-2，既有問題）：五支 Python 子程序每次開一個 session 並留下來。
  做法：gateway 直接回 400、不轉送，或放寬結束 session 的條件；補「沒有 session 的 ping／GET／DELETE 不會增加子程序 session」的測試。
- Core 版本清單：目前每個新的 Core 版本（含 patch）都要審查並發 add-on 新版；R2-harole 提的「已審 minor 的後續 patch 也接受，
  加上監看」待真機測試後由負責人決定。
