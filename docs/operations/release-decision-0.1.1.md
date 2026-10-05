# 0.1.1 發佈紀錄（2026-10-05）

**依據：** 0.1.0 公開決定（[release-decision-2026-10-05](release-decision-2026-10-05.md)）；負責人 2026-10-05 核准另外六支
`homeassistant_api`、woowtech-ha 為測試環境，並於 12:56Z 決定 0.1.1 收尾由 Claude 交付線接手（Pi 停滯）。

## 內容（映像來源 `d2e1e3b65b89f42445fbb9b87eb447018044a5db`）

- 另外六支開 `homeassistant_api`，管理面板以 HA owner／system-admin 驗證（provider 90153cb：SPEC＋安全 APPROVE）。
- bootstrap 只把 runtime `SUPERVISOR_TOKEN` 交給七支管理程序（2626bc7：SPEC＋安全 APPROVE，child 不繼承）。
- HA 還原後屬 root 的資料一次改回 10001（8588b97＋R1 修正 d687cad、19892a3：第一遍握住核准的 inode，第二遍只改重驗過的；獨立 SPEC 與安全審見 Claude 交付線 reports）。
- LiteLLM 五個有界 metadata 讀取（cf7fea1）與其回歸修正（57609d1）。

## 已通過

- builder VM：七支 build、container/mock、supply-chain gate（source／history／image／evidence secrets、SBOM、CVE、license）全過。
- 全套 `tests/`（含瀏覽器）、packaging unittest、validate；證據保存在 Claude 交付線。

| 產品 | 已測 image ID（推送的就是這個 ID，不重建） |
|---|---|
| n8n | `sha256:bc4852a2a7b58ab625e9edf8705ca3270b285ca5558076e96c3be950342cc5ed` |
| odoo | `sha256:4df1c275be1b0f137d24b476512bd11b0d75608e1c22444bf91bcb015d33847f` |
| odoo-manage | `sha256:e3444aed4d8794f52a05c9ae882482a33c7f8d4aa969127a6c4144ea2b4280c8` |
| hermes | `sha256:d2683f1b47c0df98115208714e999f6623cef8bda57243acf55cc16239bb8c5b` |
| opendesign | `sha256:72e728d5af30003fe319919e91595fae9aed2aca21ac643f736b9208551bb43b` |
| emqx | `sha256:8ad5933a9a6f66cee61b7ab18154fe6299e68639651473f37aadb1de4a49d37f` |
| litellm | `sha256:06aa6f122794e5e0ba323defb69b1a51a1c744909ec9a1f7e11cf5bb97c4291f` |

## 未通過／未驗

- 真 HA（2026-10-05，測試 HA，[紀錄](ha-test-0.1.1.md)）：七支映像身分與上表一致；n8n 升版與 HA 還原 PASS；六支有真後端、
  LiteLLM 沒有後端（工具未測）。已知問題：Odoo Manage 後端斷線時 session 失效、OpenDesign `list_agents` 逾時、
  Odoo 兩個 metadata 工具需「存取權限」群組。一般使用者進不了七支面板（403）。未測：LAN client；aarch64 未建。
- 文件（DOCS／CHANGELOG／授權清單）在映像建置後更新，不在映像內，不影響已測映像。
