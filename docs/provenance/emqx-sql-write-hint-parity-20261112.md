# EMQX 規則 SQL 測試工具的授權提示（2026-11-12）

`emqx_test_rule_sql` 會對 EMQX `/rule_test` 發出 POST。HA 閘道已將它列為尚未證明無副作用的操作，要求明確寫入授權；但舊的 HA vendored 子服務把它標成 `readOnlyHint=true`、`idempotentHint=true`，標題也沒有提醒需要寫入權限。Podman PR #26 的同一工具使用 `write` tag 與 `writing("Test EMQX Rule SQL (write permission)")`。兩端的實際授權並未因這次更改放寬。

本修正只把 HA vendored 子服務的 tag、annotations 與標題對齊該保守契約。`POST /rule_test` 的參數、handler、回傳 schema、閘道的 `UNCERTAIN` 分類與預設寫入授權沒有改。`tool_snapshot.py` 已從釘選 FastMCP 4.1.3／MCP 2.3.0 真子服務重新產生，保持子服務可用與不可用時的公開清單一致。

`output_schemas.json` 的 39 個 EMQX 輸出 pin 仍指向原來的受審來源 commit `e142a6e43170625fed945bc3eb4a4e45327559bf`，其 schema 雜湊與每支工具的 binding 均未改。`tests/test_output_schemas.py` 另外釘選新的 `integration.py` 當前 bytes SHA-256 `89c6f167d6b9487a2ae6373ab498dd9eef9911895effe9e6d7c0c61c9ac4841d`，明確區分歷史 schema 證據與這次只更改 metadata 的來源。`runtime-sources.json` 記錄同一當前 SHA 及改動範圍。

本機以真 EMQX 子服務和假後端重新生成清單，沒有後端 mutation／failure；`tests/test_output_schemas.py`、`tests/test_migration_preview.py`、快照名稱檢查及 EMQX 真子服務清單共 **418 passed**。`packaging/validate.py` 通過。首次試跑因新工作樹沒有根目錄 `.venv` 導致三項 CLI 測試無法啟動，安裝鎖定的根目錄環境後，這 417 項在同一工作樹全部通過。其他產品的完整 runtime suite 留給 CI。

這是來源候選；沒有改 add-on 版本、映像或 QA HAOS。正式三方公開 `tools/list` 的對照仍需待 HA 新映像發布後重測。
