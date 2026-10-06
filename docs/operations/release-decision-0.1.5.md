# 0.1.5 發佈紀錄（2026-10-06）

**依據：** 0.1.4 兩輪審查留下的 gateway 縱深防禦建議（[release-decision-0.1.4](release-decision-0.1.4.md)），0.1.5 審查（R1、R2、RC）的意見，
負責人 2026-10-06 決定 Odoo Manage MCP 整體下架封存，以及 Docker Hub 2026-10-06 重建的 Python 基底。

## 內容（映像來源 `0c66bd0a1e4af7f26ca5b6c8c7abdf3663bcc037`）

- gateway：client 收到的每個回覆都由 gateway 重新組成（jsonrpc、id，加上 result 或 error 其中一個；error 只留整數 code、message、data）；
  ping 成功一律 `{}`；POST 的 SSE 串流只轉送這個請求自己的回覆，送出後立即結束；GET 串流不轉送回覆；32 位元以外的 code 或非字串 message
  改成 gateway 自己的錯誤；initialize 回覆必須是物件且 `protocolVersion` 為日期格式（YYYY-MM-DD），否則 502。
- Odoo Manage：自 HA 商店、建置與發佈移除（0.1.4 為最後一版；已發佈映像保留，已安裝的不會再收到更新，請改用 WOOW Odoo MCP）。
  原始碼與測試保留封存。PaaS 端由另一條線處理（範本隱藏 odoo-addons/woow_paas_platform#1507、WOOWTECH/woow-mcp-server#38）。
- 基底：`python:3.13.16-slim-bookworm` 改釘 Docker Hub 2026-10-06 重建版（amd64 `f0408636…`），已內含 libpcre2-8-0 10.42-1+deb12u2 與
  perl-base 5.36.0-7+deb12u4；原本從 Debian snapshot 升級 libpcre2 的步驟移除。
- 來源紀錄（ledger）：補列各守門在所有實際執行的 venv 中守住的上游原始碼；測試以語法樹推導守門在哪些服務執行。

## 已通過

- 審查（唯讀子代理）：R1（862faf5..948cc90）REQUEST CHANGES，修正於 b0e518f；R2 複審（b0e518f）APPROVE WITH NOTES；發佈候選完整
  獨立審查（862faf5..0c66bd0）APPROVE WITH NOTES。兩份意見都只動測試、文件與 builder 端工具，於 853eb06 處理，映像不重建。原文與對照見 Claude 交付線
  reviews-015/。修正以變異測試確認有測試把關（tests-015/）。
- 全套 `tests/`（0c66bd0）1231 passed／0 failed／0 error／0 skipped；
  packaging OK；validate（六支）、tool inventory PASS。同一套測試在 9012ff8（只加測試、文件、builder 端工具與商店的 0.1.4 HA 文件）再跑一次：1231 passed／0 failed。
- builder VM：六支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）全過。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） | GHCR manifest digest（匿名 registry_gate public PASS） |
|---|---|---|
| n8n | `sha256:fe1f1e82c8759a48d9db7d4761c74a454692316a62713e4c09c343429bf8c91e` | `sha256:defb41e4d0de05a9b822eaebc1844a7a8973e4f9ded24fbc40b144453e245290` |
| odoo | `sha256:3f834556cb8bf5842ede35b9d0abce785761847989e2496c1c71a002d78e38a4` | `sha256:a2bcd52e57766251b536ab2492712f857a1ba7742a59c37635af5d3b9492e2bf` |
| hermes | `sha256:c62a44dfba5ff7668a100417af571f8dd8ab0de5560d83e2ba55a7251bd303f1` | `sha256:895e85e7dafd766b5d7d8fb4976914b5fc719225288f986fcb77a58f5607709b` |
| opendesign | `sha256:94d6869fae713aa502cbd09a3c87145a3afd1617ffc3d3cd8c7b51c30cd14a3a` | `sha256:ab630fa6740ee85fffc83328edb6c7cc161baac2c71ef80972da2b0c63a906c9` |
| emqx | `sha256:537a3028427e33486c428a4479206c9d39329938cf75dfac13b22fd96af829f2` | `sha256:08b36ab9ae0e2e5cef71d425a83718e2e749f746b1e0011504efdb5f51a07ff3` |
| litellm | `sha256:2a2d780b13bfa1e8cf45d503634d7ebe70d93cd3ef8405721604727344f152eb` | `sha256:73dd0819f2622cd53da2b00b8c06076f52998e8894ad5533c16ae79dcb56b189` |

商店分支：映像來源 `0c66bd0a1e4af7f26ca5b6c8c7abdf3663bcc037` 之後只有測試與文件的 commit（853eb06 審查意見、9012ff8 合併商店的 0.1.4 HA 文件 a92a442），
加上本紀錄所在的發佈文件 commit；release tag v0.1.5 指向映像來源。

## 未通過／未驗

- 真 HA：2026-10-06 已在測試 HA 回歸（[ha-test-0.1.5](ha-test-0.1.5.md)）：執行中映像＝發佈（6/6）、讀取／拒絕／斷線／重啟／開關與 0.1.4 相同、六支非常見方法先回 401、non-admin 403；測試 HA 上的 Odoo Manage 已移除（負責人核准，先備份）。aarch64 未建；LAN client、LiteLLM 工具（無後端）。
- 其他主機是否裝過 Odoo Manage 無資料；商店移除後它們仍可執行 0.1.4，但不會再有更新。
- 文件（DOCS／CHANGELOG／授權清單）在映像建置後更新，不在映像內，不影響已測映像。

## 0.1.6 待辦（審查留下、0.1.5 未改程式的部分）

- 工具中繼資料：policy 只重組 `inputSchema`，`outputSchema`、`execution` 等欄位照轉，子程序文字可進 client 錯誤、
  `taskSupport: required` 會讓 client 拒絕呼叫；改為白名單（RC F3，既有問題）。
- Python SDK client 遇到 gateway 403（未授權工具）會整段 session 斷線，TS 只失敗那次呼叫；考慮改以 JSON-RPC error 回應或寫進
  clients.md（RC F7，既有問題）。
- initialize 因 protocolVersion 不合格回 502 時，子程序的 session 沒有被關閉（與其他 initialize 502 相同，只在子程序異常時發生；R2 觀察）。
- ledger 測試涵蓋常見與常數參數的動態載入，判定不了的寫法會讓測試失敗；更罕見的載入方式仍要靠審查（R2 #1）。
