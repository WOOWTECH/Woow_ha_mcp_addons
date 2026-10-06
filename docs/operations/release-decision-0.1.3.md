# 0.1.3 發佈紀錄（2026-10-06）

**依據：** 0.1.2 在測試 HA 的回歸（[ha-test-0.1.2](ha-test-0.1.2.md)）中，Odoo 剛重啟時使用者讀取全回 `BACKEND_BUSY`；
根因是健康探測佔住 Odoo 子程序唯一的工具工作槽（Woow Odoo nginx log 佐證）。另含 0.1.2 審查留下的兩個 NIT。

## 內容（映像來源 `a0db7d7cb2bb6d0c73d1a9b8233c6a705bb941d1`）

- Odoo：健康探測改為子程序私有 `woow_backend_probe`（不在工具清單，gateway 不列出也不授權）：只驗證登入，在自己的
  1-thread owned executor 執行，不再佔用工具工作槽；沒有 `ir.model` 讀取權的最小權限帳號，後端狀態與 8081 readiness 也正確。
- gateway：`/mcp` 的所有 HTTP 方法先驗 Bearer 再 405（`Allow: GET, POST, DELETE`）。
- 健康檢查：子程序的 `protocolVersion` 須符合與 session id 相同的規則（可列印 ASCII、不含空白、1–256 字元）才沿用為標頭，否則該輪失敗並照常帶 session id 關閉 session。

## 已通過

- 獨立審查（subagent 只讀）：Odoo 健康探測 R1 SPEC＋安全 APPROVE WITH NOTES → ac4b182（測試斷言、文件、同名工具檢查）；
  發佈候選完整審查（e497443..a0db7d7）APPROVE WITH NOTES，意見（測試把關、文件、七份 README 與商店描述）在映像來源之後以只改測試與文件的
  commit 處理。歷程與原文見 Claude 交付線 reviews-013/。修正以變異測試確認有測試把關
  （探測改回 list_models → unreachable；探測放上唯一工作槽 → 與 HA 相同的 `BACKEND_BUSY`；探測排隊 → 2 秒內失敗；
  方法檢查改成不分大小寫 → 小寫 `get` 等 4 個失敗；清理 DELETE 不帶 session id → 失敗）。
- 全套 `tests/`（a0db7d7）1154 passed／0 failed／0 error／0 skipped；
  packaging 146 OK；以 uid 65534 跑 bootstrap 測試 OK；validate、tool inventory PASS。
  映像來源之後的 9dcdfd0（只有測試與文件）：全套 1161 passed／0 failed／0 error／0 skipped，packaging 146 OK，validate、tool inventory PASS。
- builder VM：七支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）全過。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） |
|---|---|
| n8n | `sha256:a4fe3ec2eefe7b413875e723a258e67121964171518da46bd2a5aa3759a57e22` |
| odoo | `sha256:50b2f1d7c9db5df002c8169f3979c4b21b9852ba34d2fc054455d66badeb3754` |
| odoo-manage | `sha256:3a52564e03b9dc7aa75ec64968293a4faecbe01d7c303dd46ea17a082dc8167d` |
| hermes | `sha256:e1d0cc6da6409280c95c1c2eae1ebd758552d767e6d21a1f43ebe937acb02501` |
| opendesign | `sha256:d8e131fd0a837ed1707edcc2eca089b376ef2f1bb303d2d0de3906c718a09b10` |
| emqx | `sha256:4cefe5c68ba05264c818d21f0a839ce0f4a86cd04897b54bb40350c6b62bc48c` |
| litellm | `sha256:3459b3bbb21fc4adf0571c4a63b469dd984553d5675e20bb51e84a000b6444df` |

## 未通過／未驗

- 真 HA：2026-10-06 已在測試 HA 回歸（[ha-test-0.1.3](ha-test-0.1.3.md)）：執行中映像＝發佈、Odoo 剛重啟時 `BACKEND_BUSY` 0 次、Odoo 最小權限帳號 readiness 200、七支非常見方法先回 401、non-admin 403。aarch64 未建；LAN client、LiteLLM 工具（無後端）未測。
- 0.1.3 回歸新發現（舊探測，非 0.1.3 造成，列 0.1.4）：OpenDesign 0.21.1 的 health 形狀 `{"ok": true, "version": …}` 不被探測接受；Odoo Manage 的 `list_models` 探測需要 `ir.model` 讀取權。兩者讀取都正常，只影響後端狀態與 8081 readiness。
- 0.1.4 待辦：0.1.2 審查留下的四項 NIT／INFO 仍開著（非 2xx 內容帶子程序文字、`-32042` 錯誤碼、通知轉送範圍、JSON 回覆完整緩衝的記憶體）；
  0.1.3 RC 審查 #6（`child_spec` 為 EMQX／LiteLLM 保留的原生探測名稱取自 `PROBES`，HealthMonitor 用 `health_probe()`，目前一致；
  改成同一來源要動映像內程式，延到 0.1.4）。
- 已知且不變：admin app（Ingress）對 GET／HEAD／PUT／POST 以外的方法仍由框架在身分檢查前回 405（與 0.1.2 相同，不洩漏資訊；RC 審查 #9）。
- 文件（DOCS／CHANGELOG／授權清單）在映像建置後更新，不在映像內，不影響已測映像。
