# 火車 B 0.5.0：發佈與實機驗收覆核（2026-11-26）

三個映像已發佈到 GHCR，必要 CI 與商店升級乾跑通過。**實機驗收仍有未完成項目，PR #140 尚未合併，不能宣稱已上架或全部驗收通過。** 本次接續先核對原始結果，再補 Hermes 中斷後的驗收；未以監看通知或腳本結束碼代替逐項結果。

## 發佈基準

- 維修版 [PR #138](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/138) 已合併：`7dbec9ae84ae8ed6bc4b8a60e250ab24d2ef77ec`。
- 火車 B [PR #140](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/140)：`release/train-b-0.5.0-20261125` → `claude-delivery`；覆核時為 draft、open、未合併。
- 已發佈映像共同來源：`22705ce853af679fd235f32aa5bac2fe8a6fcd27`。後續驗收紀錄只改 `docs/`，不重建或覆寫既有 0.5.0 tag。下列 CI 成功結論綁定映像來源；後續文件提交仍須通過自己那一輪必要檢查才可合併。
- [CI 45615872782](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45615872782)：映像來源 `22705ce` 的最新 attempt：`checks`、`readiness`、`Upgrade comparison / compare`、`Upgrade comparison / runtime` 全部 success；[Release train 45615873358](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45615873358) success。

| 產品 | 升級 | gate / candidate / publish | 映像與候選檔摘要 |
|---|---|---|---|
| Hermes | 0.4.15 → 0.5.0 | [45615946222](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45615946222)，全部 success | [發佈紀錄](release-decision-hermes-0.5.0.md) |
| n8n | 0.4.15 → 0.5.0 | [45615960847](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45615960847)，全部 success | [發佈紀錄](release-decision-n8n-0.5.0.md) |
| Headscale | 0.4.20 → 0.5.0 | [45615974030](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45615974030)，全部 success | [發佈紀錄](release-decision-headscale-0.5.0.md) |

新 head 的 Store 乾跑在 2026-11-25 22:01（台北）結束：三產品各自的 std、官方 HA Core 2026.11.3 e2e 共六份報告 PASS，舊新面板均可開啟、`ALL_DONE fail=0`、遠端結束碼 0、hassio network identity/IPAM 不變。證據包 SHA-256：`ad38ce3bca5a24e2583e772e738ecc5d27700dfb3e60191ef2b11aedd8e2c3f9`。舊 head `20292de` 的失敗建置與乾跑不作為本次放行證據。

實機驗收版本（2026-11-26 唯讀核實）：Core **2026.7.2**、Supervisor **2026.11.0**、HAOS **18.1**；這與上方使用官方 Core 2026.11.3 的獨立 Store 乾跑是不同證據。

## Headscale：已取得的證據與限制

2026-11-25 的實機結果：N×N 9/9、三帳號 cross 18/18、加入暫時帳號時 cross 32/32、child bearer 18/18；輪替、撤銷、刪除與短效後端 key 撤銷隔離均有成功斷言。子程式故障後 2.49 秒出現新 PID，約再 6.3 秒恢復子程式 session，其他帳號不受影響。一般負載及 25 次連線建立／刪除完成。

一般、加密局部還原均有每帳號撤銷與還原訊號；備份前後的四個舊操作收據回 410，核對後重發才能連線。回退 0.4.20 與再升 0.5.0 保留預設 state 雜湊與備份時的 token。清理後測試 key 清單回到兩台各一把的原始基準、標記使用者刪除、第二個後端停止並還原、臨時 HA 管理員刪除、測試副本卸載、鎖釋放；保護備份保留。

不能宣稱全過的項目：

- `headscale_policy` 讀取為 26/27 plan 唯一失敗；舊版、新版及後端 CLI 都因未設定 ACL 路徑而失敗。這是已重現的後端前置條件，尚未取得真後端政策讀取成功的證據，也未修改正式 ACL 來遷就測試。
- 認證拒絕只記錄到 15 秒階段，沒有完整量到 300 秒退避；PSS 因權限無法讀取，舊量測程式印的 0 不代表實際為零。
- 掃描的 credential-values 為零，但 11 個檔案命中 `hskey-api-` 前綴樣式（公開 key prefix）；原始掃描結果是 FAIL，不能改寫成零命中。
- 回退時工具錯把指定舊 image ID 配上新 tag，造成驗證器誤報；另在舊版讀不存在的多帳號 restore record 得到 traceback。這些屬工具假設與舊版不支援欄位，不是「所有步驟無錯誤」。

## Hermes：實機結果與限制

2026-11-25 已完成舊新版 plan 各 34/34、額外帳號上限、暫時帳號建立／刪除、七種身分切換且 token 不變、N×N、cross 與輪替撤銷。2026-11-26 恢復時仍有四個帳號、第二個後端與測試副本執行中；原鎖 owner 相符，資源守門通過，先補做加密局部備份。

新增實測結果：

- 政策停用／重新啟用前後四個 PID 全相同；指定帳號工具被拒、其他三個成功（4/4）。同身分重存後端只有該帳號 PID 改變，token 不變。
- 殺掉指定子程式後 2.51 秒恢復 PID、約再 4.2 秒取得子程式 session；其他三個 PID 與容器啟動狀態不變。
- add-on 重啟指令 1.08 秒、其後 8.21 秒 MCP 就緒，第一次工具呼叫 HTTP 200、無工具錯誤。50 次 Gateway status 的 p95 242.4 ms；25 次 initialize／DELETE 都是 200/200。
- cross 32/32、child bearer 28/28、重啟後 N×N 10/10；四帳號皆啟用且無孤兒。
- 四帳號輕負載後：子程式 RSS 約 81、77、77、77 MiB，管理程序約 66 MiB；容器約 283.3 MiB。PSS 無法讀取，記為 unknown，不當作零。

一般與加密局部還原均已通過：每輪四帳號各撤銷一次、五張舊收據均回 410，核對重發後 cross 32/32、N×N 10/10。兩個還原偵測訊號均觸發（re-owned、marker true / sentinel mismatch）。加密輪在變更演練後曾被 Supervisor 工作守門攔下；重新查驗全部工作完成、守門通過後，才從已建立的加密備份接續，沒有重做帳號變更。另以只保留在展示機程序記憶體內的舊權杖，分別做一般／加密局部備份還原，兩輪 Bearer 401／密鑰網址 404 都是 8/8；重發後 cross 32/32。回退 0.4.15 與再升 0.5.0 已完成：兩次的 state SHA-256 前 16 碼均為 `880764f0deb8a939`，預設 token 摘要回到備份時的值；舊版只有一行 KEPT_NOTICE、沒有撤銷，無多帳號索引／sentinel。再升級後只有預設帳號，plan 34/34，明確撤銷與重發後兩種接法 2/2。最後清理已完成：223 個結果／證據／步驟日誌掃描零命中；測試副本停機 1 秒後卸載、兩個標記排程刪除、第二個後端停止、臨時管理員移除（HA 使用者數回到 9）、演練備份及回合密碼刪除，保留第二後端的加密保護備份。執行中容器回到 39，Store Hermes 仍為停止的 0.4.15、Store Headscale 仍為執行中的 0.4.20。第二個 Hermes 後端只曾啟停，沒有呼叫 prepare 或修改選項。證據已歸檔，2026-11-26 09:41（台北）鎖已釋放。未確認免費模型，因此未呼叫真後端長 chat、未做 60 分鐘模型負載；60 分鐘容量量測依既有決定只記錄、不擋發版，其他未驗功能不自行改標 PASS。現有後端日誌沒有可用的 `password-login` 記錄，尚不能按帳號證明登入次數，也不能把日誌零命中解讀成未發生 429。

## n8n 與上架前剩餘工作

n8n 尚未開始真後端實機驗收，指定位置未找到兩把短效 API key：本機需要可建立／讀取／刪除測試工作流程，第二後端只能讀取。key 不在聊天、repo 或 pi1 檔案中傳遞；等待安全準備位置。已唯讀查過展示機安裝版的 `n8n --help`，提供的命令沒有 API key 建立指令。

第二後端目前限定只讀，因此 UC-09「兩邊更新同一個 workflow id」也尚無可執行條件；需要合適的可寫測試後端或另行確認驗收安排，不能拿只讀 N×N 替代。完成必要真後端驗收與清理後，才進行 PR 放行、合併、Store 同步及 Store 安裝／升級後回歸。

## 驗收工具覆核

原 `run_mp.sh` 在管線後印日誌路徑、driver 在執行後印結束碼，兩者會吞掉失敗退出碼；舊步驟還有未啟用 `set -e` 的情況。本輪在 repo 外建立隔離工具副本，保留原始 guard 與遮罩，傳回真正的管線／driver 結束碼；用假 ssh/node 的成功及失敗各兩條路徑驗證，4/4 通過。接續步驟使用 `set -euo pipefail` 並另斷言帳號數、PID 範圍、還原撤銷與收據結果。

工具適配的中途失敗亦保留：Hermes 預設子程式不帶 `--port`，第一次 PID 收集漏列預設帳號，修正為契約規定的 3000；還原演練的操作識別碼擷取最初未包含時間戳後綴，斷言停下後依實際格式修正。均未放寬產品行為斷言。卸載腳本曾因 HA CLI 對 `result:error` 仍退出 0 而誤印 STILL-INSTALLED；另以 API 結果、已安裝清單、容器及設定檔驗證測試副本已不存在。

另修正驗收清單 n8n T-07 的過時文字：政策儲存不重啟任何子程序；後端或 session 設定才重啟該帳號，與產品測試及 runbook 一致。

本輪沒有做 full restore、主機重開或 Supervisor 更新測試（依既有範圍限制），不宣稱那些情境成立。

原始日誌、報告與清理證據保留在 repo 外的 train B 證據目錄；本紀錄不含後端憑證、真實內網位址或原始 token。
