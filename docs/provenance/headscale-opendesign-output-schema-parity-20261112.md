# Headscale 與 OpenDesign 受審輸出 schema（2026-11-12）

來源基線為 `claude-delivery@659ad84b158616a3d51bb7de61fccabee17e36f5`。[Podman PR #26](https://github.com/WOOWTECH/Woow_podman__mcp_server/pull/26) 的完整子服務 `tools/list` 和 HA 釘選子服務在合成設定下比對：Headscale 11 支均宣告 `{"type":"object"}`；OpenDesign 只有 `read_file` 宣告包含 `result:string` 的物件。HA 閘道原本沒有這兩產品的輸出 schema pin，所以公開 `tools/list` 省略這 12 欄。工具名稱和 194 支共用工具的輸入 schema 已另行比對；這份變更只處理輸出宣告。

`output_schemas.json` 現新增 12 組精確 `(product, tool, schema)`、SHA-256 與 handler/source 檔雜湊；仍由既有有限 JSON Schema 字彙及大小上限驗證。子服務日後改動任何一份 schema 時，閘道會保守省略該欄，不能自動發布新 schema。`tool_snapshot.py` 是從 HA 釘選的真子服務重新產生，並以 live child／fallback gateway 相等測試驗證。沒有修改授權分類、工具輸入、連線設定或 backend handler。

本機證據：

- Headscale、OpenDesign 真子服務各一次啟動，`tools/list` 與公開閘道及 fallback 三者相等；假後端沒有 mutation／failure。
- `tests/test_output_schemas.py`、快照名稱檢查、兩個真子服務及兩個 live/fallback 端對端案例：合計 194 passed，包含兩產品上游 schema 變動時保守省略的反例。
- 其餘產品的 SDK runtime 測試需要它們各自的釘選 `.venv` 與 n8n Node 模組；本地候選工作樹未安裝它們。既有 CI 必須完整跑完，且版本／映像／HAOS 部署仍需另行發布驗收。

這是來源 PR 候選，不改已發布 0.4.16 映像，也不能替代 QA HAOS 的真管理登入與真後端呼叫。
