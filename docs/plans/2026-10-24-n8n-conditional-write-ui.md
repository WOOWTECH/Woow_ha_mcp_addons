# n8n 條件寫入介面實作計畫

**目標：** 在工具權限介面明確顯示 exposeToMcp 的條件寫入與既有更新權限需求。

**架構：** 使用後端已覆核的條件描述，不從輸入 schema 推測授權。畫面分開顯示已儲存的相依權限、草稿與子行程狀態；沿用既有儲存與安全機制。

**技術：** 原生 JavaScript、Node 原生測試與 Playwright。

1. 先補上會失敗的條件描述／瀏覽器測試，涵蓋兩個工具、允許與禁止、草稿、成功儲存立即回讀，以及失敗儲存。
2. 沿用 capabilities 的 conditional_writes。在 contracts 與 app 工具列顯示條件說明，避免將含條件寫入的工具標為唯讀。延伸隔離 fixture 與 browser 測試。
3. 驗證既有 grant／操作限制不被修改、false／省略仍遵循原操作政策、未知相依狀態不顯示允許，以及 320／360／桌面寬度無溢出。
4. 執行相關 Python 政策測試、前端單元測試、建置與本地瀏覽器測試；將命令、結果與截圖寫入 ROOT/evidence/batch5/ui。
5. 更新 docs/operation-policy.md，檢查差異後本地提交，交由 root 審查。版本、依賴、部署機制與線上系統均不變。
