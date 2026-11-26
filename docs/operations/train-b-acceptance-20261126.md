# 火車 B 0.5.0：發佈與實機驗收覆核（2026-11-26）

三個映像已發佈到 GHCR，映像來源及前一文件 head 的必要 CI、商店升級乾跑已通過。**三產品必要實機補驗、清理與 PR head 必要 CI 全數通過；PR #140 已於 19:34（台北）合併，正式 Release、商店同步與實機短回歸的最新結果統一記於 [PR #140](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/140)。** n8n 的資料夾功能保留後端版本／授權限制，不宣稱 62/62；Hermes 60 分鐘模型負載依既有決定只記錄、不擋發版。所有結論依逐項原始結果，未以監看通知或腳本結束碼代替。

## 發佈基準

- 維修版 [PR #138](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/138) 已合併：`7dbec9ae84ae8ed6bc4b8a60e250ab24d2ef77ec`。
- 火車 B [PR #140](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/140)：`release/train-b-0.5.0-20261125` → `claude-delivery`；2026-11-26 19:34（台北）已合併，merge commit `49bc4b772717387b314241a11470b59b7ec91d27`。
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

2026-11-26 接續補驗：以同一個已發佈 0.5.0 映像安裝新的測試副本，另起原生 Headscale **0.29.4**，使用全新 tmpfs 資料庫、明確的唯測試政策檔、零節點與兩把一小時 key。正式 Headscale 的使用者、節點與 ACL 都未修改。透過原生 v1 API 的政策讀取成功，MCP 完整 plan **27/27**，兩帳號 cross **8/8**。原先在未設定 ACL 的正式後端所得 26/27 保留為環境前置條件紀錄，不覆蓋原始失敗。

撤銷其中一把 QA key 後，用僅轉送請求並記錄時間／狀態／測試 key 標籤的代理觀察原版健康監看；未改任何計時常數。連續六次 401 的間隔為 **15.18、30.20、60.19、120.19、300.19 秒**，共觀察 531.8 秒；另一帳號同時有 **35 次成功健康檢查**。

重存有效 key 後，受影響帳號再次通過 27/27、兩帳號 cross 8/8，MCP token 不變。兩把 QA key 最後都已撤銷並驗證 HTTP 401；測試副本、QA Headscale／觀測代理、臨時 HA 管理員及本輪備份已清理，39 個執行中容器與原有服務狀態恢復，hassio identity/IPAM 不變，18:38（台北）釋放鎖。30 個證據檔的實際憑證值命中為零；原始掃描 FAIL 的五個格式命中均為 QA key 的公開 prefix，覆核逐項對上已知 prefix，沒有忽略其他秘密樣式。補驗 manifest SHA-256：`eebf84a37668a3e7a60c6db4b55dae007d1768f90606b8547a4af8ce1d70aa33`。

先前結果與仍須保留的限制：

- `headscale_policy` 讀取為 26/27 plan 唯一失敗；舊版、新版及後端 CLI 都因未設定 ACL 路徑而失敗。這是已重現的後端前置條件；本輪已在有政策檔的隔離真後端補成 27/27，正式 ACL 未修改。
- 先前認證拒絕只記錄到 15 秒階段；本輪已補齊實測到 300 秒。PSS 因權限無法讀取，舊量測程式印的 0 不代表實際為零。
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

一般與加密局部還原均已通過：每輪四帳號各撤銷一次、五張舊收據均回 410，核對重發後 cross 32/32、N×N 10/10。兩個還原偵測訊號均觸發（re-owned、marker true / sentinel mismatch）。加密輪在變更演練後曾被 Supervisor 工作守門攔下；重新查驗全部工作完成、守門通過後，才從已建立的加密備份接續，沒有重做帳號變更。另以只保留在展示機程序記憶體內的舊權杖，分別做一般／加密局部備份還原，兩輪 Bearer 401／密鑰網址 404 都是 8/8；重發後 cross 32/32。回退 0.4.15 與再升 0.5.0 已完成：兩次的 state SHA-256 前 16 碼均為 `880764f0deb8a939`，預設 token 摘要回到備份時的值；舊版只有一行 KEPT_NOTICE、沒有撤銷，無多帳號索引／sentinel。再升級後只有預設帳號，plan 34/34，明確撤銷與重發後兩種接法 2/2。最後清理已完成：223 個結果／證據／步驟日誌掃描零命中；測試副本停機 1 秒後卸載、兩個標記排程刪除、第二個後端停止、臨時管理員移除（HA 使用者數回到 9）、演練備份及回合密碼刪除，保留第二後端的加密保護備份。執行中容器回到 39，Store Hermes 仍為停止的 0.4.15、Store Headscale 仍為執行中的 0.4.20。第二個 Hermes 後端只曾啟停，沒有呼叫 prepare 或修改選項。證據已歸檔，2026-11-26 09:41（台北）鎖已釋放。前次未確認免費模型，因此當時未呼叫長 chat、未做 60 分鐘模型負載；60 分鐘容量量測依既有決定只記錄、不擋發版，其他未驗功能不自行改標 PASS。前次後端日誌沒有可用的 `password-login` 記錄，當時無法按帳號證明登入次數；本次已用下方計數代理補驗，仍保留原始紀錄。

2026-11-26 接續補驗使用同一個已發佈 0.5.0 映像。聊天接可控制延遲的 QA Gateway，沒有模型呼叫或模型費用；Dashboard 透過僅允許登入與狀態／排程讀取的代理，連到展示機既有的原生 Hermes 0.1.14。兩個 MCP 帳號使用完全相同的 Dashboard URL 與既有上游帳號，各自子程序保存登入快取。第一個帳號三次狀態查詢只登入一次；加入第二個後再分別查詢共六次，累計恰好兩次成功登入，沒有 429。這驗證的是兩個 MCP 帳號的獨立快取，未聲稱建立了兩個不同 Dashboard 使用者。

在 QA Gateway 明確保持一個聊天請求進行中後，儲存指定帳號政策（停用 `hermes_chat`）不改兩個子程序 PID，原聊天在解除等待後成功，另一帳號聊天約 0.084 秒完成。換指定帳號後端時，原聊天在約 12.025 秒收到 HTTP 200 的 SSE JSON-RPC `-32004`，MCP token 不變，另一帳號 PID 不變；換完後兩個帳號都可立即聊天。

明確撤銷指定帳號時，進行中的聊天約 14.207 秒收到 HTTP 200 的 SSE JSON-RPC `-32005`；舊 token 的 Bearer／密鑰網址均失效，另一帳號 PID 不變且能正常聊天，重發後指定帳號也恢復。

先建立量測與工作 session，再逐步加入聊天，確認 QA Gateway 同時有 **16 個在途請求**。滿額時新 initialize 收到 HTTP 200／`-32003`；預先建立的量測 session 送第 17 個工具請求，約 **1.017 秒**回 `-32003`，另一帳號約 **0.258 秒**成功。解除等待後 16 個聊天全完成，指定帳號可再次成功呼叫，名額已釋放。全輪共觀察四次真 Dashboard 登入，都是 HTTP 200，沒有 429。

並行驗收的兩次工具失敗保留：第一次在滿額後才建立量測 session，忽略 initialize 的 busy 回應後繼續送工具，因缺少 session 而得到 400；改為先建量測 session 後，仍有兩個工作連線未在觀察期限內進入 Gateway，因此沒有把該輪算成滿額成功。最後先建好所有 session，再逐步填入工作，仍嚴格要求 16 個實際在途請求及第 17 個請求的拒絕結果。沒有修改產品的名額、逾時或映像，也沒有把前兩次失敗刪除。

補驗清理完成：29 個證據檔憑證掃描零命中；測試副本、QA Gateway、臨時管理員、本輪備份與憑證均清除，39 個容器與原有服務狀態恢復。原 Hermes 後端選項的完整雜湊符合測前基準，hassio identity/IPAM 不變。18:54（台北）釋放鎖並移除工作目錄，manifest SHA-256：`611e7265e600dc2482cccf11bb2168d8bf54125e7d77592d19ba7f1c2365933a`。這輪驗證真 MCP 子程序、HAOS 閘道與真 Dashboard；聊天內容由 QA Gateway 回覆，未驗證模型品質或真模型效能，亦未執行非阻擋的 60 分鐘容量量測。

## n8n：真後端驗收與限制

2026-11-26 使用展示機 n8n 2.12.3（後端 add-on 2.12.17）與 PaaS n8n 2.43.6。使用者提供的兩段 key 相同，核實只適用 PaaS；另依授權建立展示機 24 小時測試 key。PaaS 即使 key 權限較寬，工作流程仍只做讀取；工作流程寫入限於展示機自建的停用標記流程、無外部作用的 webhook，以及一次性 QA 後端。原有帳號 ID、工作流程與設定保留。

- 0.4.15 → 0.5.0 的 state SHA-256 前 16 碼均為 `f717dae9fa070d87`，預設 MCP token 不變。舊新版 plan 均為 **61/62**，逐列一致；唯一失敗是原生 n8n 2.12.3 不支援 `n8n_manage_folders` 所需資料夾 API。其餘 9 個讀取與 52 個拒絕案例通過，不能寫成全過。另在 PaaS 2.43.6 做相同唯讀呼叫，也因實例授權未開啟 `feat:folders` 失敗；較寬 API key 無法代替該功能授權。
- 額外帳號上限 2、第三個拒絕 409；N×N 6/6、三帳號 cross 18/18、P9 完整 cross 31/31。未設後端時，七個文件工具與一個後端工具均拒絕，沒有子程序或目錄副本（8/8）。暫時帳號刪除後舊 token 的兩種接法均拒絕，無孤兒。
- 政策變更不改任何子程序 PID；後端與 session 設定只重啟指定帳號，MCP token 不變。session 上限 20 時第 21 個回 429、改成 5 時第 6 個回 429，其他帳號仍可建立 session；關閉後可重新開啟，最後還原 600 秒／20 個。
- child bearer 最初 12/18：前段反覆拒絕及 session 超額測試觸發上游每 15 分鐘 20 次失敗的 limiter，預設子程序回 429。重啟測試副本、重新測完整矩陣後為 18/18；原始失敗保留，不以成功覆蓋。指定子程序被終止後 2.53 秒恢復 PID、約再 0.73 秒取得 session；其他 PID 與容器啟動狀態不變。
- 重啟指令 1.16 秒、其後 5.6 秒 MCP 就緒，第一次呼叫 HTTP 200；50 次 health 的 p95 60.1 ms、tools/list p95 76.3 ms；25 次 initialize／DELETE 都是 200/204。三子程序 RSS 約 148、150、131 MiB，管理程序約 67 MiB，容器約 336.2 MiB；PSS 無權讀取，記 unknown。
- **UC-09 已通過**：另建一次性 n8n QA 容器，與展示機標記流程共用同一個 workflow ID；透過兩個 MCP 帳號更新無外部作用的測試流程，版本清單與快照只回各自內容。數字版本 ID 可在不同目錄中碰撞，仍不洩漏另一後端快照；切換後端後舊歷史不可取得。QA 容器測完即移除，PaaS 工作流程沒有寫入。
- 區網 webhook 經兩個 MCP 帳號觸發皆成功（2/2）；後端網址設成 `127.0.0.1`／`localhost` 均回 400。另在已發佈映像內以 mcp 使用者直接呼叫原生 webhook、chat、form handler，六種 loopback／unspecified／IPv4-mapped 位址都回固定政策拒絕（18/18）。這份 handler 證據與真 MCP 區網觸發分開記錄，沒有宣稱做過 DNS rebinding 實機情境。

一般與加密局部還原均通過：每輪三個帳號各撤銷一次、舊權杖 Bearer 401／密鑰網址 404 共 6/6、四張備份前後的舊操作收據均回 410；未核對前重發回 409 `restore_review_required`。核對重發後 cross 18/18、N×N 6/6。兩種還原均同時觸發 re-owned／marker 與 sentinel mismatch；三份節點目錄重建，各自 inode、檔案 0600／父目錄 0700。

`new-origin-unset-secret` 面板情境已用真後端重錄：清空未設定的 instance-level access token 回 200；只改 origin、未補原已儲存的 API key 回 422 `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN`；同時補上新 key 回 200。成功回應帶 ETag／saved／指定 profile，拒絕回應無 ETag，MCP token 不變；與既有 fixture 的三項預期一致。測完接回 PaaS 並重驗隔離。

「全部撤銷」已在三帳號一起驗證，六種舊權杖接法皆失效（6/6），三個帳號都顯示 token inactive；核對後可重新發行。

回退 0.4.15 與再升 0.5.0 均通過：執行中映像各自符合既定 image ID，兩次 state SHA-256 前 16 碼都是 `f717dae9fa070d87`，預設 token 回到升級前備份的值。舊版只有一行 KEPT_NOTICE、沒有撤銷，沒有多帳號索引／sentinel；再升級只有預設帳號，plan 61/62 與原始結果逐列相同。明確撤銷、重發後兩種接法均成功（2/2）。測試標記與 webhook 刪除後查詢均回 404，相關執行紀錄均為空；展示機原有 24 個流程的數量、ID 與完整資料雜湊全部符合測前基準。展示機短效 key 與使用者提供的 PaaS 測試 key 都已精確撤銷，舊 key 讀取均回 401，登入工作階段登出。憑證掃描的原始結果為 FAIL：三個檔案各命中同一個公開的 43 字元 UC-09 成功標記，實際 credential-values 命中均為零。247 個檔案的覆核只豁免這三個指定檔案中的完整固定標記，沒有豁免其他 token 樣式，原始報告保留。

測試副本停機 1 秒後卸載，API 已確認沒有測試 add-on 註冊、容器與設定檔。臨時 HA 管理員刪除，HA 使用者回到 9；演練備份及回合密碼清除，保留後端加密保護備份。憑證暫存目錄為空，hassio network identity/IPAM 不變，執行中容器回到 39。原 n8n 後端仍為執行中的 add-on 2.12.17，Store n8n／Hermes 仍為停止的 0.4.15、Store Headscale 仍為執行中的 0.4.20。證據歸檔後，2026-11-26 **14:08（台北）**釋放鎖並移除工作目錄；證據 manifest SHA-256：`15bad65086d8e66eb8dbcff20ca991558da93a8a380621e5dfcbb41124d71bef`。

## 發佈判斷與下一步

n8n 的 API key 與可寫 QA 後端前置條件已排除；Headscale 政策讀取、完整退避，以及 Hermes 長請求隔離／名額與 Dashboard 登入快取均已補驗並清理。n8n 資料夾功能在舊新版均有相同後端限制，符合 [P9 kit](ha-p9-kit.md) 已列的社群版／授權限制，屬既有相容性限制；保留 61/62 的原始結果，不以其他通過項目取代它。三產品依既有整套授權一起交付；PR head `6d128a8` 的 [CI 45805906972](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45805906972) 與 [Release train 45805907598](https://github.com/WOOWTECH/Woow_ha_mcp_addons/actions/runs/45805907598) 全數成功，已合併為 `49bc4b7`。正式 Release、Store 同步與安裝／升級後短回歸結果統一記在 [PR #140](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/140)，與前述 GHCR 發佈及隔離乾跑分開核實。

## 驗收工具覆核

原 `run_mp.sh` 在管線後印日誌路徑、driver 在執行後印結束碼，兩者會吞掉失敗退出碼；舊步驟還有未啟用 `set -e` 的情況。本輪在 repo 外建立隔離工具副本，保留原始 guard 與遮罩，傳回真正的管線／driver 結束碼；用假 ssh/node 的成功及失敗各兩條路徑驗證，4/4 通過。接續步驟使用 `set -euo pipefail` 並另斷言帳號數、PID 範圍、還原撤銷與收據結果。

n8n 工具適配的原始失敗同樣保留：外部端點需要瀏覽器 User-Agent；PID 收集不能讀取不同 uid 的 environ，改由命令列與預設埠辨識；一次性 QA 後端要等設定 API 回 JSON 且進入初始化狀態，不能只看健康檢查；單節點標記流程不符上游結構驗證，改為兩個無外部作用的節點。名稱更新不建立快照，UC-09 改用結構更新並比較新增版本，而非假設版本 ID 從 1 起算。這些調整只在 repo 外的驗收工具，未修改產品映像。

工具適配的中途失敗亦保留：Hermes 預設子程式不帶 `--port`，第一次 PID 收集漏列預設帳號，修正為契約規定的 3000；還原演練的操作識別碼擷取最初未包含時間戳後綴，斷言停下後依實際格式修正。均未放寬產品行為斷言。卸載腳本曾因 HA CLI 對 `result:error` 仍退出 0 而誤印 STILL-INSTALLED；另以 API 結果、已安裝清單、容器及設定檔驗證測試副本已不存在。

另修正驗收清單 n8n T-07 的過時文字：政策儲存不重啟任何子程序；後端或 session 設定才重啟該帳號，與產品測試及 runbook 一致。

本輪沒有做 full restore、主機重開或 Supervisor 更新測試（依既有範圍限制），不宣稱那些情境成立。

原始日誌、報告與清理證據保留在 repo 外的 train B 證據目錄；本紀錄不含後端憑證、真實內網位址或原始 token。
