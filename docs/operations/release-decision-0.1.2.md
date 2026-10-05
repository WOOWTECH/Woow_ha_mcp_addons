# 0.1.2 發佈紀錄（2026-10-06）

**依據：** 0.1.1 在測試 HA 的實測（[ha-test-0.1.1](ha-test-0.1.1.md)）找到的問題；負責人 2026-10-05 決定由 Claude 交付線
全權執行實作、審查、建置、測試與發佈（Pi 做最終驗收）。

## 內容（映像來源 `114f23ae070b638897b12e8b1ac3e946347e2966`）

- gateway：initialize 一定要拿到 child 對這次請求的 JSON-RPC 回覆，否則回 503 `BACKEND_UNAVAILABLE`（不給 session id）；
  過大或格式錯誤 502；SSE 事件依 gateway 看得懂的行重組、單獨 CR 拒絕、Content-Type 固定；initialize／tools/list 只接受 200。
- Odoo：B2 工具整體失敗時照實回固定傳輸錯誤碼（如 `BACKEND_RPC_FAULT`）。
- OpenDesign：`/api/agents` 讀取可等 20 秒。
- gateway 加固（審查發現，多為舊版即有）：成功回應只轉送 gateway 解析、過濾過的格式（其他 2xx 即使宣稱長度 0 也回 502、不轉送任何位元組）；
  JSON 回覆一律比對 id 後重新序列化；反向請求、通知與 DELETE 的回應內容不轉送；轉送標頭值驗證；失敗的回應不再佔住連線名額；溢位數字拒絕。
- 健康檢查：子程序的異常回應只讓就緒狀態為 false，不再讓 add-on 停止；session id 驗證後才重用。
- bootstrap：還原修復的成功訊息在最後檢查後才印；修復時調高的 `RLIMIT_NOFILE` 修完即還原。

## 已通過

- 獨立審查六輪（每輪 subagent 只讀；歷程見 Claude 交付線 0.1.2-PLAN.md）：R1 SPEC 與安全 APPROVE WITH NOTES → a83a0a0、2977bdd；
  R2 REQUEST CHANGES（SSE 重組只在 Content-Type 剛好相符時生效，舊版即有）→ 477c91e；R3 REQUEST CHANGES（477c91e 的
  `Content-Length: 0` 放行可被假長度繞過）→ 7919d93；R4 APPROVE WITH NOTES（slot 外洩，舊版即有）→ 52c26aa；R5 APPROVE WITH NOTES
  （健康檢查可讓 add-on 停止，舊版即有）→ 114f23a；R6 APPROVE WITH NOTES（只剩測試與文件）→ db0f5c4、6990781。每項修正都以變異測試確認有測試把關。
- 全套 `tests/`（6990781）1149 passed／0 failed／0 error／0 skipped；
  packaging 146 OK；以 uid 65534 跑 bootstrap 測試 OK；validate、tool inventory PASS。映像來源之後只有測試與文件變動。
- builder VM：七支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）全過。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） |
|---|---|
| n8n | `sha256:a7e81f1bc215d605e8d720de0ff1ce6c550e665128e58cf72b6e5aa0d5245bf4` |
| odoo | `sha256:6d99737029703e2ff77412c480b4dd311550a8c54cf5c5dfefbde82600aff7a9` |
| odoo-manage | `sha256:aaa51c647be56a9be60b2bb5f5401416b20840a07a5db3c54adfac74d0340705` |
| hermes | `sha256:10bb90bda30c68f0d2719ae38807a190fe331d666ae8eda24d1f08ca87f32e9b` |
| opendesign | `sha256:2669d3becdb54733e4195d3e37df457223f4956fc7c2d3a485b2aa07988f08a6` |
| emqx | `sha256:37a699ace1a64fce1c2c352ed6cff0a3f86999673c44314640807928b14dbce0` |
| litellm | `sha256:007bac720469ed043dcb944999c861cd0b123ac027478dc21039009b9b94abe3` |

## 未通過／未驗

- 真 HA（2026-10-05，[回歸紀錄](ha-test-0.1.2.md)）：七支映像身分與上表一致；Odoo Manage 斷線 503、OpenDesign `list_agents`、Odoo 固定錯誤碼、還原修復皆 PASS；一般使用者 403。Odoo 一次性 `BACKEND_BUSY` 未能重現，列 0.1.3。未測：LAN client、LiteLLM 工具；aarch64 未建。
- 0.1.3 待辦（審查的 NIT／INFO）：其他 HTTP 方法在驗證前 405、健康檢查未驗證子程序的 protocolVersion、非 2xx 內容帶子程序文字、
  `-32042` 錯誤碼、通知轉送範圍、JSON 回覆完整緩衝的記憶體、健康探測佔住單一工作槽（Odoo）。
- 文件（DOCS／CHANGELOG／授權清單）在映像建置後更新，不在映像內，不影響已測映像。
