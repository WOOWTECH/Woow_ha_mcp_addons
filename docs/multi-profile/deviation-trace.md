# 差異來源對照（FEATURE-MATRIX、G6 §5 → 刻意差異表或測試）

> HM-00 產出（2026-11-14）。表由 repo 外的產生器寫出（腳本與輸入的 SHA-256、重產指令見
> `docs/provenance/ha-multiprofile-HM-00-20261114.md` 第 8 節），「原文」欄逐字取自計畫產物（repo 外）：
> `FEATURE-MATRIX-zh-TW.md` 第 2 節的「HA 平台差異」欄、`gaps/G6-delivery.md` 第 5 節的「HA 期望值與差異」欄。
> 對照腳本會重讀來源逐列比對；原文變了、某列對不到差異表或測試、或「—」的列少了結論，就不過。
> 腳本只驗結構與引用存在；「對到的列說的是不是同一件事」靠人工抽查。

## 結論

- FEATURE-MATRIX 153 列裡，109 列有「HA 平台差異」，每列都對到 `contract.md` 第 9 節（§8.8）的列或某個測試。
- 其餘 44 列寫「—」（沒有平台差異），但「—」不等於行為相同：每列都人工看過、寫了結論（文末一節）。23 列有差異、對到差異表；19 列照 PaaS（有的另指差異表裡相關的列）；2 列是流程或文件。
- G6 §5 的 T-01～T-29 共 29 列，每列都對到 §8.8 的列或某個測試。
- 對不上的已經補成差異表第 44～79 列（HM-00 補列）；看「—」列時找到的差異補成第 80～86 列（審查後補列）。只對到測試的列，說明欄寫了為什麼不是差異。
- 「對到」欄的測試：「既有」是 bb48449 已有的檔；「HM-xx」是計畫中的新測試（`acceptance-matrix.md` 的測試檔登記表）。

## FEATURE-MATRIX「HA 平台差異」欄

| FM | 原文（HA 平台差異） | 對到 | 說明 |
|---|---|---|---|
| FM-01 | 位置不同（PaaS 放預設檔內）；第一次建立額外帳號才產生 | §8.8 #44；`tests/test_profile_index.py`（HM-07） | — |
| FM-02 | HA 不在預設 state 寫任何鍵（PaaS 會寫空索引） | §8.8 #44；`tests/test_upgrade_zero_rewrite.py`（HM-07） | — |
| FM-03 | HA Store.load 不檢查擁有者（Hc/config.py:157-162），建議補 uid 檢查（小強化） | `tests/test_profile_store.py`（HM-07） | 補擁有者 uid 檢查是和 PaaS 對齊，不是差異 |
| FM-04 | Supervisor 還原中途失敗不回滾、finally 仍可能啟動（G3 讀 Supervisor 原始碼） | §8.8 #20；`tests/test_restore_lock.py`（HM-13b） | 守門每一步冪等，中途當掉下次開機重做 |
| FM-05 | 錯 token 碼 PaaS 403、HA 401／404；索引壞時 HA 拒絕啟動或照跑 503：待決（DQ-12） | §8.8 #1、#25；`tests/test_profile_routing.py`（HM-08） | 索引壞的處理 DQ-12 待定（計畫建議 8081 全部 503、面板照開） |
| FM-08 | PaaS restore guard 另設 `RESTORE_POLICY_HOLD`（本表補充，見 UC-24）；HA 額外帳號一出生就是 schema 4，不會觸發遷移 | §8.8 #66；`tests/test_owner_defaults.py`（既有） | — |
| FM-09 | HA 舊映像讀不了新鍵，只能靠「不寫預設 state」達到同樣效果 | §8.8 #44；`tests/test_upgrade_zero_rewrite.py`（HM-07） | — |
| FM-10 | HA 沒有 `mcp_auth_revoked`／generation，靠 TokenAccess 事件＋重讀，不需補；建立時要不要記歷史：待決（DQ-02） | §8.8 #8；`tests/test_token_history.py`（既有） | DQ-02 採 (a)：建立不記歷史 |
| FM-11 | HA 沒有用 env 調名額的入口 | §8.8 #45 | — |
| FM-12 | 管理頁走 Ingress、和 MCP 入口不同源，不能用瀏覽器 origin | §8.8 #27 | DQ-13 待定（計畫建議 endpoint 全域一個） |
| FM-13 | PaaS 刪帳號 rmtree 失敗留下的孤兒會讓之後的備份過不了 restore_guard（G1 probe-paas；PaaS 端，不在本輪） | §8.8 #23 | PaaS 端的缺陷，列進給 PaaS 的回補建議（HM-29） |
| FM-14 | HA 手改帳號 state 立即生效、PaaS 要重啟（寫進文件）；目標硬體成本未量（UC-02）；比對方式見 CF-10 | §8.8 #46、#26；`tests/test_profile_routing.py`（HM-08） | N 份 state 的讀取成本（UC-02）記在 HM-08 筆記，HM-19c 在目標硬體量 |
| FM-15 | config.yaml 沒開 tmpfs，`/tmp` 推定佔磁碟（G5 依官方文件；G1 列未確認 UC-03） | §8.8 #47 | — |
| FM-16 | HA 沒有 restore_guard，對應的是 entrypoint 還原修復 | §8.8 #20；`tests/test_restore_detection.py`（HM-13a） | root 才造得出的還原樹放 `tests/` |
| FM-17 | 平台不同 | §8.8 #11 | — |
| FM-18 | 管理請求不能帶 query 或 `%`（Hc/gateway.py:707） | §8.8 #48 | — |
| FM-19 | HA 面板不顯示伺服器文字，只顯示固定代碼（Hui/api.js:48-61） | §8.8 #49 | — |
| FM-20 | 與負責人 2026-10-15「新安裝全開」衝突，要使用者決定（DQ-02）；`n8n_session` 要不要複製三份報告不一致（CF-05） | `tests/test_profile_store.py`（HM-07）；`tests/test_profile_admin_api.py`（HM-10） | DQ-02 採 (a) 複製預設帳號當下的政策、`n8n_session` 不複製，和 PaaS 相同，不是差異 |
| FM-22 | PATCH 經 Ingress 要 HAOS 實測（UC-10） | §8.8 #50；`tests/test_profile_admin_api.py`（HM-10） | — |
| FM-23 | profile_deleted 回呼在 HA 不需要（CF-18）；Supervisor 還原會帶回已刪帳號（FM-79）；停一個子程式約 4 秒、面板請求逾時 25 秒（Hui/api.js:46） | §8.8 #34、#20；`tests/test_profile_admin_api.py`（HM-10） | 每帳號資源都在自己的物件裡，不需要 profile_deleted 回呼；停一個子程式約 4 秒，在面板 25 秒逾時內 |
| FM-24 | 刻意比 PaaS 嚴；PaaS 要不要回補另議（DQ-15） | §8.8 #34 | — |
| FM-25 | HA 多半沒有 cgroup 與 CPU 上限、和 HA Core 共用主機；OOM 時整個 add-on 被殺、所有帳號一起斷（未實機確認，UC-15） | §8.8 #19、#15 | OOM 可能先殺管理程序，寫進已知限制（threat-model.md） |
| FM-26 | 原因集合依 HA 容量設計（FM-25） | §8.8 #19、#51 | — |
| FM-27 | 錯 token 維持 HA 404（PaaS 403），驗收期望值要改；HA 每請求重讀 N 份 state（FM-14） | §8.8 #1、#46 | — |
| FM-28 | PaaS 沒有這條路，文件要寫明是 HA 差異；HA 文件「Claude.ai 無法帶 Authorization」已過時（R07 X-06） | §8.8 #2 | 過時的「Claude.ai 不能帶標頭」由 HM-18 更正 `docs/operations/clients.md` |
| FM-29 | PaaS 轉送用戶端其他標頭（含 `x-n8n-*`，上游可能據此換後端，G5-13，PaaS 側未實測 UC-16）；HA 白名單應保留 | §8.8 #4 | — |
| FM-30 | 回應碼待決（DQ-09）：G2 建議 503 `{"error":"state unavailable"}`，G3 認為也可維持 404／401 | `tests/test_profile_routing.py`（HM-08） | 撞號 503 和 PaaS 相同；DQ-09 待定（計畫建議 503） |
| FM-33 | 錯 token 碼 HA 404／401（PaaS 403） | §8.8 #1 | — |
| FM-34 | 正式映像是否同樣留 traceback：未確認（UC-05） | `tests/test_gateway_stream_endings.py`（HM-14） | 標頭後補 `-32005`、不把例外丟給 uvicorn；UC-05 由這個測試在映像外證明 |
| FM-35 | n8n MCP Client Tool 是否支援 Streamable HTTP：未確認（UC-07） | §8.8 #6 | — |
| FM-36 | Cloudflare WAF、524 屬 PaaS 平台；HA 只在前接 Cloudflare Tunnel 時才遇到 | §8.8 #5、#3 | — |
| FM-37 | Supervisor 建構時呼叫 PR_SET_CHILD_SUBREAPER，多實例可行；改到的檔多在帳本列管（FM-99） | `tests/test_profile_runtime.py`（HM-05） | 多個 Supervisor 實例可行，是實作前提，不是差異 |
| FM-38 | 預設 port 不同（PaaS 8000、HA 3000），不影響外部；容器網路私有（host_network: false），不必改 manifest | §8.8 #52；`tests/test_child_port_param.py`（HM-04） | — |
| FM-39 | 其他異常結束要不要也改無限退避：待決（DQ-20） | §8.8 #14 | DQ-20 採 (b) |
| FM-41 | 全部同 uid 10001；HA AppArmor 是否允許管理程序讀子程式 `/proc/<pid>/fd`：未確認（UC-04）；需安全審查 | §8.8 #13 | — |
| FM-42 | 要安全審查並更新帳本（FM-99） | §8.8 #37；`tests/test_child_bearer.py`（HM-06） | — |
| FM-44 | 「分原因」屬 #148（DQ-06） | `tests/test_gateway_stream_endings.py`（HM-14） | DQ-06 採 (a)，#148 已在 pin 內；`-32004` 依原因 |
| FM-45 | HA 對小主機有利；工具清單一致、錯誤文字不同（已知差異） | §8.8 #28 | — |
| FM-46 | HA manifest 停止上限 30 秒 | §8.8 #53；`tests/test_profile_lifecycle.py`（HM-09） | — |
| FM-47 | HA 收緊政策也重啟（PaaS Nextcloud 收緊不重啟），不影響隔離 | §8.8 #54 | — |
| FM-48 | Odoo 修補檔是否改動 restrict_*：未確認（UC-13） | `tests/test_product_boundary.py`（既有） | 同 uid 信任邊界和 PaaS 相同（threat-model.md）；Odoo 本機檔案工具的選項維持關閉；UC-13 仍未確認 |
| FM-49 | HA 沒有 cgroup 上限（最壞 64×16 MiB≈1 GiB） | §8.8 #15 | — |
| FM-51 | #148 尚未合併 | §8.8 #15；`tests/test_gateway_queue_ha.py`（HM-14） | #148 已合併進 pin |
| FM-53 | Core 與 Supervisor 兩段 Ingress 原始碼都轉送自訂 header（G4），HAOS 未實測（UC-10）；沒帶 header 的預設與 id 格式錯的狀態碼兩份報告不一致（CF-07） | §8.8 #31、#32、#50 | — |
| FM-55 | HA 每請求重查角色，比 PaaS 共用密碼強 | §8.8 #11 | — |
| FM-56 | Ingress iframe 與 HA 前端同源，key 一定要帶 mount；HA 重整後 iframe 是否回到入口：未確認（UC-14） | §8.8 #36 | — |
| FM-57 | HA 的 task() 鎖比 PaaS React 版安全，和 Headscale 版相當 | §8.8 #55 | — |
| FM-58 | 哪些產品顯示選單和產品範圍有關（FM-93、DQ-28） | §8.8 #43 | — |
| FM-60 | Odoo、Nextcloud 健康探測是真登入，登入量隨帳號數成長（FM-69） | §8.8 #18 | — |
| FM-61 | 建立時自動發出要不要記入歷史、輪替後立刻顯示或丟掉：待決（DQ-02、DQ-31） | §8.8 #8、#56 | DQ-31 待定 |
| FM-65 | HA 維持有上限的 GET 快照、不改 SSE（部署差異）；子程式日誌遮罩沒遮 `?key=`（FM-75） | §8.8 #29；`tests/test_redaction_matrix.py`（HM-02） | 子程式緩衝補遮 `key=` |
| FM-67 | PaaS 恆 200；HA 依就緒回 200／503 | §8.8 #7 | — |
| FM-68 | 定期探測是 HA 獨有成本；健康監看共用 httpx 池，池滿時別帳號探測可能失敗（推論，UC-06） | §8.8 #18 | — |
| FM-69 | PaaS 不定期探測，所以沒有這個問題 | §8.8 #18；`tests/test_health_backoff.py`（HM-09） | — |
| FM-70 | HA 平台專屬門檻 | §8.8 #30 | — |
| FM-71 | Ingress iframe | §8.8 #57 | — |
| FM-73 | HA 在 token 之後判斷，紀錄可帶帳號 id、未認證請求灌不進來（比 PaaS K-09 好）；Headscale 清單兩邊相反（產品用途不同）；Claude.ai 實際送什麼 Origin 未確認（UC-11） | §8.8 #9、#10、#42 | — |
| FM-75 | HA 實際暴露面小（潛在問題）；兩邊保證都只涵蓋 raw 請求目標，真正防線是「不記路徑」 | `tests/test_redaction_matrix.py`（HM-02） | 對齊項目，不是差異；真正的防線是「不記路徑」 |
| FM-77 | 這是「HA 加強」不是 PaaS 對齊（CF-06）；HA bridge 網路下 loopback 只會連到 add-on 自己；目前只有 HA 管理員能改後端網址（設定錯誤與縱深防禦，不是越權） | §8.8 #39 | — |
| FM-79 | A 依賴 Supervisor 以 root copytree 的實作細節（失效時退回復活；誤判只會多撤銷）；用舊映像的備份還原時無法保護；整機遷移後全部網址要重發 | §8.8 #20、#21、#69；`tests/test_restore_detection.py`（HM-13a） | — |
| FM-80 | HA 看不到還原前狀態，只能事前匯出或事後核對 | §8.8 #58；`tests/test_restore_review.py`（HM-13c） | — |
| FM-81 | 新動作名會改 schema、影響降版（FM-09），所以用 rotate；Nextcloud 是否比照：PaaS 沒做、待決（DQ-05）；「先提交再停」之間新 token 會不會打到舊子程式：未確認（UC-21） | §8.8 #40、#59；`tests/test_odoo_identity_rotation.py`（HM-12） | UC-21 由這個測試確認（先停再提交） |
| FM-82 | 同庫多帳號時 Odoo 端負載＝帳號數×每帳號並行；主機 CPU 共用 | §8.8 #60；`tests/test_odoo_multi_profile.py`（HM-12） | — |
| FM-83 | PaaS「沒存 methods 時全帳號共用容器 env」在 HA 不適用（隔離更好） | §8.8 #61 | — |
| FM-84 | PaaS「兩種 429」只適用 PaaS；HA 監控要用閘道自己的訊號 | §8.8 #62 | — |
| FM-86 | K-14（兩 Dashboard 共用簽章金鑰時 cookie 互信）在 HA MCP 路徑不適用 | §8.8 #63 | — |
| FM-87 | PaaS 一個唯讀開關、HA 逐支授權；兩邊都每帳號一份 | §8.8 #64 | — |
| FM-88 | 同一台、同一把 key 的兩帳號，子程式讀錯 state 時連線比對擋不下來（政策是唯一分權） | `tests/test_headscale_multi_profile.py`（HM-26，暫定名） | 政策是唯一分權；文件建議每帳號不同 API key |
| FM-89 | 整份 PUT backend 本來就要帶完整連線 | §8.8 #41 | — |
| FM-90 | 產品用途不同（HA 允許 Claude.ai） | §8.8 #9 | — |
| FM-91 | 同一台 Nextcloud 暴力破解防護以來源 IP 計（FM-69） | §8.8 #18；`tests/test_health_backoff.py`（HM-09） | 節流單位 UC-12 未確認 |
| FM-92 | HA 遮罩以 state 為單位，不需全域集合；EMQX 角色名稱依版本：未確認（UC-22） | §8.8 #38、#65 | — |
| FM-94 | DOCS.md 不算 Store 執行期內容，太早改會隨別的產品發版提早上架 | §8.8 #73 | — |
| FM-95 | HA CI 是 GitHub Actions、Python 3.13.16、pytest 以 root（CF-14）；實際耗時未確認（UC-17） | §8.8 #75 | — |
| FM-98 | HA 測試基礎比 PaaS 完整（優勢） | §8.8 #76 | — |
| FM-99 | 前例：#87 首輪 CI 因 vendored 摘要停下、#83 多兩個 digest commit（R10 RG-05） | §8.8 #77 | — |
| FM-102 | hook 只能用 python3 或 busybox sh、預設 600 秒；能否以 root 讀 0600 檔、連 8081、拿 owner 使用者 id：未確認（UC-19） | §8.8 #72 | — |
| FM-105 | 合併「改 add-on 版號」的 PR＝直接發佈到 WOOW App Store | §8.8 #73 | — |
| FM-106 | HA 沒有釘版隔離層 | §8.8 #74 | — |
| FM-109 | Headscale 測法兩份報告不同（CF-15） | `tests/test_odoo_multi_profile.py`（HM-12）；`tests/test_headscale_multi_profile.py`（HM-26，暫定名） | 真後端 N×N 在 HAOS（驗收 T-04）；Headscale 形態 DQ-26 待定 |
| FM-110 | aarch64 不適用（只出 amd64）；n8n nodes.db 持久化會加大備份（每份約 67 MiB） | §8.8 #47 | HA 只出 amd64，容量在 J6412／J1900 量（HM-19c） |
| FM-111 | Supervisor 能否不還原備份直接裝回舊版：未確認（UC-18） | §8.8 #71 | — |
| FM-112 | Supervisor 還原＝直接回滾 | §8.8 #20 | — |
| FM-114 | HAOS 才發現問題就要燒版號重發；候選映像能否側載、J1900 ISA 檢查是否仍必要：未確認（UC-20） | §8.8 #73 | UC-20 由 HM-03a 確認 |
| FM-115 | 無法監看客戶端 | §8.8 #79 | — |
| FM-117 | Supervisor 沒有 hook；還原換回備份版本的映像 | §8.8 #20、#69；`tests/test_restore_detection.py`（HM-13a） | — |
| FM-118 | 同 FM-79 | §8.8 #20；`tests/test_restore_lock.py`（HM-13b） | — |
| FM-119 | 開關＝發版 | §8.8 #24；`tests/test_dormant_profiles.py`（HM-13b） | — |
| FM-124 | validate.py 精確 manifest | `packaging/test_validate.py`（既有） | 備份含 token 兩邊相同；要排除就得改 manifest，validate.py 的精確 manifest 測試會擋（DQ-46，後續） |
| FM-125 | Supervisor 與 Store 的限制 | §8.8 #71 | — |
| FM-126 | 還原換版 | §8.8 #69 | — |
| FM-127 | HA 角色驗證 | §8.8 #30 | — |
| FM-129 | HA 硬體慢 | §8.8 #17；`tests/test_reply_worker.py`（HM-30） | — |
| FM-131 | 沒有 shell | §8.8 #25 | — |
| FM-132 | 沒有 cgroup | §8.8 #19 | — |
| FM-133 | J1900 低速 | §8.8 #53；`tests/test_staggered_start.py`（HM-09） | — |
| FM-135 | Store 規則 | §8.8 #72；`tests/test_upgrade_hooks.py`（HM-16） | — |
| FM-136 | Store 規則 | §8.8 #72 | — |
| FM-139 | 沒有 operator 監看 | §8.8 #51 | — |
| FM-140 | 省記憶體 | §8.8 #28 | — |
| FM-141 | 禁止 force push | §8.8 #78 | — |
| FM-142 | Store 必要檢查名稱 | §8.8 #75 | — |
| FM-143 | 版號 PR 合併＝發佈 | §8.8 #73 | — |
| FM-144 | 每個映像整包複製核心 | §8.8 #74 | — |
| FM-147 | builder 在 repo 外 | §8.8 #73 | — |
| FM-148 | HA 角色每請求查 | §8.8 #12；`tests/test_admin_pipeline_matrix.py`（HM-10） | — |
| FM-149 | 沒有 cgroup | §8.8 #15；`tests/test_profile_quotas.py`（HM-08） | — |
| FM-150 | 讀 body 前准入 | §8.8 #16；`tests/test_profile_quotas.py`（HM-08） | — |
| FM-151 | 一個 add-on 持有多個帳號的 token | §8.8 #38；`tests/test_reply_mask_union.py`（HM-08） | — |

## G6 §5「HA 期望值與差異」欄

| T | 原文（HA 期望值與差異） | 對到 | 說明 |
|---|---|---|---|
| T-01 | 執行中映像 digest＝GHCR 發佈值；記 Core／Supervisor／OS；後端用合成身分 | §8.8 #73；`packaging/test_container_probe.py`（HM-16 擴充）；`packaging/test_ha_p9_probe.py`（HM-16 擴充） | HAOS 的 digest 與版本紀錄在 HM-19b |
| T-02 | 上限依 HA 實測另訂；錯誤碼照 HA 管理 API 契約 | §8.8 #19、#35；`tests/test_profile_admin_api.py`（HM-10） | — |
| T-03 | 每帳號 43 字元 token 互異；Odoo 改綁身分要換 token（HA 現在不換，R12 HX-all-09） | §8.8 #40；`tests/test_odoo_identity_rotation.py`（HM-12） | — |
| T-04 | 標記只在對角線；Headscale 一帳號一台 | `tests/test_odoo_multi_profile.py`（HM-12）；`tests/test_headscale_multi_profile.py`（HM-26，暫定名） | 真後端 N×N 在 HAOS（HM-19b）；Headscale 一帳號一台或同台不同政策 DQ-26 待定 |
| T-05 | 錯 token：密鑰網址 404、Bearer 401（PaaS 403）；帶 query 400；密鑰網址上的 Authorization 忽略；跨帳號 session 和亂數 session 同樣處理 | §8.8 #1、#3；`tests/test_profile_routing.py`（HM-08） | — |
| T-06 | 沒有 Ingress 身分 403、非管理員 403；錯誤帳號 id 依設計 404／400；MCP token 不能當管理憑證 | §8.8 #11、#31、#32；`tests/test_admin_pipeline_matrix.py`（HM-10） | — |
| T-07 | 存政策若會重啟子程式（EMQX、LiteLLM、Nextcloud、Headscale），只重啟該帳號 | §8.8 #54；`tests/test_profile_admin_api.py`（HM-10） | — |
| T-08 | 舊 token 404／401；HA 沒有手動指定 token，撞號只會來自還原或複製，要 fail closed | §8.8 #1、#80；`tests/test_profile_routing.py`（HM-08） | 沒有手動指定 token 見 #80 |
| T-09 | 刪除後舊 token 立即失效、子程式停、port 釋放、目錄刪除；重建拿新 id 與新 token | §8.8 #34；`tests/test_profile_admin_api.py`（HM-10） | — |
| T-10 | 全被後端擋；寫入前要有暫時 record rule | `tests/test_odoo_multi_profile.py`（HM-12） | 真後端在 HAOS（HM-19b），要有暫時 record rule |
| T-11 | 0 串號、0 個 5xx；HA 轉送名額現在全域 32 | §8.8 #15；`tests/test_profile_quotas.py`（HM-08） | — |
| T-12 | 只切斷該帳號的 lease；HA 已有單帳號 lease 測試 | `tests/test_profile_routing.py`（HM-08）；`tests/test_active_token_leases.py`（既有） | — |
| T-13 | 其他帳號 PID 不變；HA 重試 3 次後 failed（PaaS 是無限退避） | §8.8 #14；`tests/test_profile_lifecycle.py`（HM-09） | DQ-20 採 (b)：開通的產品照 PaaS 看門狗 |
| T-14 | 每帳號第一次 initialize 就 200；重啟前後 token 不變（P9 `restart` 已有單帳號版） | §8.8 #68、#53；`tests/test_staggered_start.py`（HM-09） | — |
| T-15 | 依 HA port 設計；衝突只停該帳號 | §8.8 #14；`tests/test_profile_ports.py`（HM-09） | — |
| T-16 | 套用狀態每帳號一份（HA 已有 `ConfigurationState` 單份） | §8.8 #68；`tests/test_profile_runtime.py`（HM-05） | — |
| T-17 | 目標硬體實測；停機小於 30 秒 | §8.8 #19、#53；`tests/test_profile_lifecycle.py`（HM-09） | 目標硬體數字在 HM-19c |
| T-18 | 每帳號診斷緩衝不被別帳號擠掉 | §8.8 #29；`tests/test_profile_runtime.py`（HM-05） | — |
| T-19 | HA 現在全域 32 名額、等 1 秒；改每帳號後照 PaaS 情境 | §8.8 #15、#16；`tests/test_profile_quotas.py`（HM-08）；`tests/test_reply_worker.py`（HM-30） | — |
| T-20 | 回退＝還原升級前備份；預設帳號 token 延續 | §8.8 #71；`tests/test_upgrade_zero_rewrite.py`（HM-07） | 回退演練在 HAOS（HM-19b） |
| T-21 | Supervisor 還原＝直接回滾；照還原設計驗 | §8.8 #20、#21；`tests/test_restore_lock.py`（HM-13b） | — |
| T-22 | `n8n_session` 每帳號一份 | §8.8 #62；`tests/test_n8n_multi_profile.py`（HM-25，暫定名） | — |
| T-23 | n8n 每帳號 `child_token` 互異；其他 7 支不驗呼叫者，待安全決策 | §8.8 #37；`tests/test_child_bearer.py`（HM-06） | DQ-40 ⑥ 採用：7 支 Python 子程式也驗 |
| T-24 | `/mcp` 帶 Origin 403；密鑰網址放行（Headscale 只放 claude.ai）；逐帳號一致 | §8.8 #9、#10、#42；`tests/test_origin_policy.py`（HM-27，暫定名） | — |
| T-25 | 0 外洩；HA 正規式對解碼後形狀會漏（潛在） | `tests/test_redaction_matrix.py`（HM-02） | — |
| T-26 | 原樣保存、顯示時跳脫、不執行 | §8.8 #35；`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11） | — |
| T-27 | 每種接法各一；真 Claude.ai 兩帳號同時用 | §8.8 #2 | 真實用戶端與公開網址在 HAOS（HM-19b、HM-29） |
| T-28 | PaaS workspace API 專屬；HA 對應「商店安裝→加第二帳號」，併入 T-20 與 HAOS | §8.8 #70 | — |
| T-29 | 合成憑證清單掃描 0 命中；清理證明 | §8.8 #78；`tests/log_scan.py`（HM-01） | — |

## FEATURE-MATRIX「HA 平台差異」欄是「—」的列（人工逐列結論）

「HA 平台差異」欄寫「—」只表示「不是平台造成的」，不表示行為相同（HA 沒有、延後、HA 新增的都可能寫「—」）。下表每列寫結論：「照 PaaS」＝行為和 PaaS 相同；「§8.8 #n」＝有不同，期望值看差異表該列；「不是執行期行為：…」＝流程或文件。「項目」欄是 FEATURE-MATRIX 功能欄的摘要。

| FM | 項目 | 結論 | 說明 |
|---|---|---|---|
| FM-06 | 每帳號 ETag 與 409 | 照 PaaS；§8.8 #86；`tests/test_profile_runtime.py`（HM-05） | 每帳號一個 ConfigurationState、HMAC domain 加帳號 id，拿 A 的 ETag 寫 B 409 `config_conflict`；ETag 格式是 HA 既有的（#86） |
| FM-07 | 收據每帳號一份、還原後舊 id 410 | §8.8 #67、#34；`tests/test_restore_lock.py`（HM-13b） | 每帳號一份收據照 PaaS；封存只留 1 份、代碼 `operation_restored` 見 #67；帳號增刪也走收據見 #34 |
| FM-21 | 帳號 id 與名稱規則 | §8.8 #35；`tests/test_profile_admin_api.py`（HM-10） | id 24 hex、預設列名稱 `Default`、名稱不進 log 照 PaaS；名稱規則加嚴見 #35 |
| FM-31 | 手動指定 token | §8.8 #80 | HA 不新增這個 API（FM-31 對齊作法）；對應的 PaaS 測試 4 案改指 #80 |
| FM-32 | 跨帳號 session 404 | 照 PaaS；§8.8 #68；`tests/test_profile_routing.py`（HM-08） | 每帳號一份 app，跨帳號 session 404；HA 另補單元測試；子程式未就緒時的自答 session 見 #68 |
| FM-40 | 索引 port 重複只停相關帳號 | 照 PaaS；§8.8 #51、#20；`tests/test_profile_ports.py`（HM-09） | `disabled_reason=port_conflict`、預設帳號保留 port 照 PaaS；清單多 `status`、`blocked_reason` 見 #51；還原檢查做法不同見 #20 |
| FM-43 | initialize 世代 | 照 PaaS；§8.8 #1、#68；`tests/test_initialize_generation.py`（HM-14） | initialize 只送到目前、已驗證的世代，換代就不交出 session；標頭前 token 被換掉的回應碼見 #1；自答見 #68 |
| FM-50 | 名額滿的回應形狀 | 照 PaaS；§8.8 #15、#6；`tests/test_gateway_busy_shapes.py`（HM-14） | 有 id 200＋`-32003`、沒 id 503、串流 429、`Retry-After` 與節流 WARNING 照 PaaS（契約第 2.4 節）；等 1 秒與串流上限見 #15；legacy SSE 見 #6 |
| FM-52 | 請求內容超過上限 | §8.8 #81 | 一超過就 413、不再讀；FM-52 延後（HM-14 選做） |
| FM-54 | 一組管理身分管全部帳號 | §8.8 #11、#12；`tests/test_profile_runtime.py`（HM-05） | 一組身分管全部帳號和 PaaS 相同（共用 CSRF 金鑰、角色查詢、16 個管理名額）；身分來源與管線順序的不同見 #11、#12 |
| FM-59 | 清單載入失敗與帳號在別處被刪 | §8.8 #84；`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11） | 清單讀不到擋整頁＋重試照 PaaS；收到 `profile_not_found` 立刻切回預設並清掉收據見 #84 |
| FM-62 | 待確認操作（收據）分帳號 | 照 PaaS；`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11） | 預設帳號沿用舊 key、額外帳號 key 帶 id、查收據帶標頭；key 字串是 HA 既有格式（`woow-admin-operation-v1:`） |
| FM-63 | 用戶端範例 | §8.8 #2、#85 | Bearer 範例見 #2；範例名稱帶 id 前 8 碼見 #85（DQ-31 待定） |
| FM-64 | 每帳號工具權限 | 照 PaaS；§8.8 #54；`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11） | 頁面讀目前帳號、MCP 依 token 套用該帳號政策；存政策時重啟的範圍見 #54 |
| FM-66 | 總覽與套用狀態看目前帳號 | 照 PaaS；`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11） | 不做跨帳號總覽（DQ-31 待定，建議不做） |
| FM-72 | 帳號管理 API 的契約文件 | 不是執行期行為：本契約（HM-00）就是兩邊共用的中立契約；PaaS 沒有對應文件 | HA 加嚴的地方都標在第 9 節 |
| FM-74 | CORS | §8.8 #42 | HA 不加任何 CORS、OPTIONS 在 token 之後回 405；PaaS report-only 會反射來源，見 #42 |
| FM-76 | MCP 回覆遮罩 | §8.8 #38；`tests/test_reply_mask_union.py`（HM-08） | FEATURE-MATRIX 的對齊作法寫「不要用所有帳號聯集」，已被 DQ-40 ⑧ 推翻（採用聯集）；健康原因只取該帳號、回覆不帶帳號名稱或 id 照 PaaS |
| FM-78 | 備份含全部帳號的秘密 | 照 PaaS | 文件寫明並建議加密備份；token 不進備份是後續選項（DQ-46） |
| FM-85 | n8n session 自動回收 | 照 PaaS；§8.8 #62 | 閘道不自動回收（PaaS 也寫死關閉）；n8n session 的名額、逾時與 429 見 #62 |
| FM-93 | OpenDesign、Odoo Manage | §8.8 #43 | DQ-28 採不開放 |
| FM-96 | 多帳號測試替身 | 照 PaaS；`tests/test_profile_ports.py`（HM-09） | 額外帳號 port 從 18000 起；替身與網路守門由 HM-01 參數化（`tests/owned_runtime.py` 等） |
| FM-97 | CI 以 root 跑時的權限測試 | §8.8 #75 | 權限與身分檢查在 uid 10001 子程序裡驗（計畫 §12.0 第 3 點） |
| FM-100 | 本機測試環境 | 不是執行期行為：本機只算預檢、以 GitHub CI 為準（DQ-33 採 (a)）；§8.8 #75 | CI 的不同見 #75 |
| FM-101 | 映像 smoke 與多帳號實測 | §8.8 #73；`packaging/test_container_probe.py`（HM-16 擴充） | 容器驗收加多帳號階段（HM-16）；發佈流程的不同見 #73 |
| FM-103 | 升版宣告 | §8.8 #72 | Store 升版比對與 `upgrade-notes.yaml` 見 #72 |
| FM-104 | 釘版與版號 | §8.8 #73 | 版號 0.5.0 與發版鎖（DQ-32 採用）見 #73 |
| FM-107 | 沙盒與正式站實測工具 | 照 PaaS；`packaging/test_ha_p9_probe.py`（HM-16 擴充） | 暫時第二帳號、交叉檢查、刪除後舊網址失效、結果不明就停照 PaaS；工具是 HA 的 P9 kit |
| FM-108 | 29 類驗收情境 | 照 PaaS | 同一套 T-01～T-29、門檻不放寬；HA 期望值不同的地方逐列指到差異表（`acceptance-matrix.md`） |
| FM-113 | 公開網址與真實用戶端 | 照 PaaS | 每種接法各測兩個帳號；HA 的對外接法由使用者自備（T-27，HM-19b、HM-29） |
| FM-116 | 人工合併、標題前綴、不加 AI 署名 | 照 PaaS | DQ-36 採用 |
| FM-120 | 全部撤銷 | §8.8 #82；`tests/test_revoke_all.py`（HM-13b） | PaaS 沒有；HA 新增見 #82 |
| FM-121 | 同 uid 信任邊界 | 照 PaaS | DQ-37 採 (a)；HA 另寫事故處理（`threat-model.md` 第 4 節，文件） |
| FM-122 | serverInfo 不帶帳號 | 照 PaaS | DQ-45 待定，建議不改 |
| FM-123 | Claude.ai 的 Origin | §8.8 #10 | Bearer 帶 Origin 403；DQ-11 第二問等 S14 實測 |
| FM-128 | Core 白名單維護節奏 | §8.8 #30 | DQ-35 待定 |
| FM-130 | 健康檢查連兩次失敗才判壞 | §8.8 #18；`tests/test_health_tolerance.py`（HM-30） | PaaS 沒有定期後端監看 |
| FM-134 | FD 上限 | §8.8 #15；`tests/test_extra_child_resources.py`（HM-09） | 開通後把 soft `RLIMIT_NOFILE` 提到需要量＋25%（契約第 5 節）；名額模型的不同見 #15 |
| FM-137 | 看門狗退避 | §8.8 #14；`tests/test_profile_lifecycle.py`（HM-09） | DQ-20 採 (b) |
| FM-138 | 生命週期 log | 照 PaaS；§8.8 #29；`tests/test_profile_lifecycle.py`（HM-09） | 事件、`[profile= port= pid=]` 格式、每帳號每情況 60 秒一行照 PaaS；HA 只寫 id 前 8 碼、紀錄在 add-on log，見 #29 |
| FM-145 | 預設帳號的收據 key 不變 | 照 PaaS；`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11） | `get()` 兩種格式都收 |
| FM-146 | Store 發佈前的非 PR run | §8.8 #73 | 升版步驟加確認（HM-17、升版片） |
| FM-152 | 改來源要重填秘密 | §8.8 #41；`tests/test_new_origin_secret.py`（HM-12） | DQ-40 ⑨ |
| FM-153 | 換身分換 token | §8.8 #40；`tests/test_odoo_identity_rotation.py`（HM-12） | DQ-40 ⑩ |
