# 0.1.10 候選發佈紀錄

狀態：**已發佈**：2026-10-13 上架商店，七支（含 OpenDesign）（GitHub tag／release `v0.1.10`，以映像建置 commit `9762a94` 為準）。以下為發佈前的候選紀錄，內文的「準備中」「待驗收」等字樣是當時的狀態。

LiteLLM MCP 的 metadata 投影接受 mode=responses，以連接已實測的 HA Woow LiteLLM 0.1.1。未知模式仍拒絕，私密欄位仍排除。

此 repo 的七個產品共用固定版本、initialize 身分與 packaging gate；沿用既有發佈模式一同升到 0.1.10，不引入產品版號分流機制。其他六支產品無功能修正。本輪 HA 更新先限定 LiteLLM MCP，其他 add-on 不更新。

使用既有專用 builder VM，以精確 source bundle 建置、container_acceptance 及 supply_chain gate 驗證；GitHub BLD2 路線仍關閉，不改寫 RELEASE-GATES、不略過映像掃描。通過後才評估發佈同一測過的 image ID，既有 tag 不覆寫。

HA 接線前需保留原 MCP state 與 token，僅更新本支、使用 HA 管理面板 API 設定內部 LiteLLM URL，維持 writes disabled；核對實際 model/group metadata 與兩帳號部署，重啟後再驗，失敗復原本輪設定。帳密只在 RAM，證據只留非敏感投影。

尚未宣告 0.1.10 映像、HA 或完整八產品商用 PASS。
