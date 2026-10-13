# 0.1.11 候選發佈紀錄

狀態：準備中，尚未發佈或部署；release gates 維持關閉。

本版納入 PR2 的 LiteLLM metadata dict 128 → 256 修正，接受實測的 156 欄位 model_info。256 KiB、depth 8、nodes 10000、list 100、string 16384 與欄位投影限制不變。此 repo 七個產品共用 VERSION、initialize 身分、manifest、Dockerfile 與 CI/release 版本，因此一致準備 0.1.11；其他六支產品無功能修正，不新增版號分流機制。

原 hosted CI 的完整 pytest 有 1845 PASS、1 FAIL：UID10001 nondumpable proof 要求 UID 0，hosted runner 是 UID 1001。只將 packaging/unit.sh 的完整 pytest 階段改為 sudo -n；依賴安裝、Node/UI 與其他步驟仍使用一般帳號。原測試和 assertions 不變，沒有 skip、選擇性排除或 continue-on-error。builder-admission 與 publication 權限模型保持原狀：未核准 builder 仍明確 DENIED，不能把 images skipped 稱為 CI 全綠。

先前 2bd6a5755391 的未發佈 731f5643… 映像標示 0.1.10，已驗證 installed handler、真實 child/gateway、UID proof 與 unchanged-policy sidecar 掃描。這些是既有版本的證據；新版本改變 core VERSION、image labels 及 source revision，必須產生新 image ID，不能直接 retag 或繼承為 0.1.11 映像驗收。相同 metadata 原碼 SHA、dependency/base pins 與安全政策可作對照，掃描/測試收據仍須綁定新候選。

交付使用獨立 operator builder run 與 unpublished tag，保留 source bundle/archive/hash closure、失敗嘗試及 cleanup。專用 operator adapter 不代表 GitHub BLD2 admission 已開啟。既有 0.1.10 public/local tags 不覆寫；不更動 RELEASE-GATES、scanner policy 或 dependency pins。

後續由主控整合審查後的精確 source，重新核對 hosted unit job 與 builder admission 結果，核驗候選 image/test/scan receipts，再在 PaaS 已建立的 HAOS VM 完成實機驗收。舊主機實測只作歷史證據，isolated runtime 的 owned mock backend 不等於真 HA。若整合改變 image inputs，需針對最後 source 重建重驗；各產品發布仍需各自 image/HA clearance。主控統一 release/merge/部署，本紀錄不宣告七產品或完整八套商用 PASS。
