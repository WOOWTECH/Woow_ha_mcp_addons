# dnspython 2.9.0 映像掃描誤報來源審查

2026-10-24 的 Codex 安全來源審查確認：下列唯一新增的 `generic-api-key` 值雜湊，來自公開 Python class 識別字的型別註記與 class 屬性引用，並非憑證。`packaging/secret-triage.json` 僅加入這一組既有機制所使用的 rule／值 SHA256 配對；不記錄匹配原值，也不宣稱專案擁有者曾個別核准此命中。

| 證據 | 值 |
| --- | --- |
| Gitleaks rule | `generic-api-key` |
| 匹配值 SHA256 | `781bd224e8e21d7cf18c3a5496921ed312b19188b66af12a4a361f2d1f5b684b` |
| 套件與版本 | `dnspython 2.9.0`，由映像內 `METADATA` 與 `RECORD` 確認 |
| 上游檔案 | `dns/dnssecalgs/mldsa.py` 第 56、57 行 |
| 映像與上游檔案 SHA256 | `3bf183c3e72c4d4ab3b4633b24cea2d460af2843ec4264d07ea90acd4c365459` |
| 已觀察產品 | EMQX，同一檔案兩個命中 |

官方 [v2.9.0 原始檔](https://github.com/rthalley/dnspython/blob/v2.9.0/dns/dnssecalgs/mldsa.py#L56) 的第 56 行是型別註記，第 57 行將同一公開 class 綁定至 class 屬性；兩處均非字串憑證、私鑰內容或執行期產生的秘密。獨立 HTTPS 取得的[原始檔位元組](https://raw.githubusercontent.com/rthalley/dnspython/v2.9.0/dns/dnssecalgs/mldsa.py)與實際映像檔案的 SHA256 完全一致；版本亦對應 [PyPI 官方 2.9.0 發布](https://pypi.org/project/dnspython/2.9.0/)。

本次定位對象為來源 `921955b23b31b2862cb6f8704042351fe503c0c8` 所建 EMQX image ID `sha256:d2e5163eb9de630fa1517945c2fdc1e8e5f5792096deeb12f2abee6c3155ebbf`。原容器功能測試通過，供應鏈 gate 則於映像秘密掃描正確拒絕未核准命中；沒有 EMQX gate 成功或發布收據。

獨立診斷以 tar 索引對回 layer 10、member 1474，檔案為 `/opt/woow/apps/emqx/.venv/lib/python3.13/site-packages/dns/dnssecalgs/mldsa.py`，layer diff ID 為 `sha256:4aa40fb0d2cab7674ab3aaa54e6a7d19bf18cedb5fb43d67e5d89ecc69ad89cd`。原始失敗日誌保持不變；診斷只定位原因，不作為 accepted release gate。去除匹配原值的來源定位收據 SHA256 為 `e99e2fafcb84051897de93ec1f00e716819c7cac11ef26e5fe4ccb30bb8d5e99`，獨立上游核對收據 SHA256 為 `f9ff93dff249e3475ed8684d62c30b6c16aa9b9f4ead312639bb28b43e8d57af`。

此配對依既有 `approved_image_findings()`／`secret_scan()` 機制適用於映像與衍生證據掃描；`apps` 與 `seen` 記錄實際觀察來源，不是新增的執行期路徑或產品限制。不同 rule、不同值雜湊及其他未核准命中仍拒絕。來源／完整歷史掃描維持去值與零命中要求；既有記錄雜湊的精確 allowlist 機制保持原狀。

本次未修改 scanner、CVE／license 政策、秘密掃描函式、任何既有 triage 項目、產品執行期程式或版本。此 triage 與證據文件形成新的來源 commit；須先通過該 head 的來源 checks／Release train，再從新 head 建置六個新映像並完成全部 gates。舊 revision 標籤的映像不能冒充新來源產物。本紀錄不宣稱 0.3.4 已發布、正式 Release／Store 已完成或 HAOS 已更新。
