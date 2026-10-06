# 0.1.4 發佈紀錄（2026-10-06）

**依據：** 0.1.3 在測試 HA 的回歸（[ha-test-0.1.3](ha-test-0.1.3.md)）找到兩個舊探測問題（OpenDesign 0.21.1 的 health 形狀、
Odoo Manage 的探測需要 `ir.model` 讀取權），以及 0.1.2／0.1.3 審查留下的 gateway 與探測名稱建議。

## 內容（映像來源 `73a40eb5409f96662e6e448fd075eda7cf8f3896`）

- Odoo Manage：健康探測改為子程序私有 `woow_backend_probe`（不在工具清單，gateway 不列出也不授權）：每次以新的連線只做連線與登入，
  在自己的 1-thread owned executor 執行、不碰 session 共用連線；最小權限帳號的後端狀態與 8081 readiness 也正確。
- OpenDesign：健康探測接受 0.21.1 的 `{"ok": true, "version": "…"}`（舊的 `status` ok／healthy 仍接受）。
- gateway：子程序 4xx／5xx 保留狀態碼與 Retry-After，內容改由 gateway 產生（不轉送子程序文字）、失敗的 initialize 不帶 session id；
  子程序 401／403 與任何 1xx／3xx 回 502；子程序通知只轉固定內容的 `notifications/tools/list_changed`；回覆須正好帶 result 或 error；
  錯誤碼非 JSON 整數或為 URL elicitation（-32042）時改成 gateway 自己的錯誤。解析 JSON 回覆的記憶體放大寫入合約。
- 共用核心：原生探測名稱改由健康檢查實際使用的探測取得。

## 已通過

- 發佈候選完整獨立審查：RC1（49b3206..970263a）APPROVE WITH NOTES，-32042 繞過、progress 帶子程序文字、DELETE 的 1xx／3xx 等意見
  修正後重新建置；複審 APPROVE WITH NOTES。歷程、原文與對照見 Claude 交付線 reviews-014/。修正以變異測試確認有測試把關（共 17 個變異全部失敗，
  例如探測佔 event loop、initialize 留 -32042、早回應留 slot、字串錯誤碼、progress 照轉、DELETE 的 3xx、子程序 401 照轉）。
- 全套 `tests/`（73a40eb）1209 passed／0 failed／0 error／0 skipped；
  packaging 146 OK；以 uid 65534 跑 bootstrap 測試 OK；validate、tool inventory PASS。
  映像來源之後的 515231e（只有測試與文件，複審意見）：全套 1213 passed／0 failed／0 error／0 skipped，packaging 146 OK。
- builder VM：七支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）全過。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） |
|---|---|
| n8n | `sha256:7a346581931d7a3500790a81a058f5184ab20db9da8c1185aa7b640bd0a542f7` |
| odoo | `sha256:08395df481b84ebd496b7de7c8332b9fe2b9ca0641fd21bb6684a9c4915e924a` |
| odoo-manage | `sha256:daf0fd85c3b0ae10794e238c5a0ce977f33c2ba6574ae6371f7b6d19e0a3c4c6` |
| hermes | `sha256:da0efc382e091d0373edf75c86f04909544970898f62a0de941b9186b5521a74` |
| opendesign | `sha256:e22301fca285c835ff9667661931c023a6d7771728bee541f525bb5f7fd7a7c0` |
| emqx | `sha256:ec0d81c0c6d0916dcff457cf46f03fa1931b38a82ab81afae784905b9d1f166a` |
| litellm | `sha256:ff10ddfc04308b87adc1ce7aff482a706f0d4ac093f7b680e3d8750bab4eca74` |

## 未通過／未驗

- 真 HA：0.1.4 尚未在 HA 回歸測試（待負責人執行更新指令）；aarch64 未建；LAN client、LiteLLM 工具（無後端）。
- 已知且不變：admin app（Ingress）對 GET／HEAD／PUT／POST 以外的方法仍由框架在身分檢查前回 405（與 0.1.2、0.1.3 相同）。
- 0.1.5 待辦（複審意見，0.1.2 起即有的縱深防禦）：POST SSE 串流中 id 與請求不同的回覆、回覆裡的未知頂層欄位仍照轉（釘住的 TS client 可能放進錯誤訊息）；ledger 未列 `backend_policy.py` 守的 httpx／httpcore 原始碼；超出 32 位元的錯誤碼照轉。
- 文件（DOCS／CHANGELOG／授權清單）在映像建置後更新，不在映像內，不影響已測映像。
