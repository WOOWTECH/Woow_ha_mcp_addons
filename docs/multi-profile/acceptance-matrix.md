# 多帳號驗收矩陣（PaaS T-01～T-29 的 HA 版）

- 狀態：HM-00 起草（2026-11-14）；HM-06 依 n8n 的實際行為改 T-23 的 n8n 期望值（2026-11-15，審查 MF-1 選 (a)）；HM-20 登記兩個測試檔與兩個 packaging 測試的擴充（2026-11-15）。HM-16 把它寫進 `docs/operations/acceptance.md` 與 P9 kit；HM-19b 照它做 Odoo 首發的 HAOS 驗收。
- 來源：計畫 §10.4、§10.6（repo 外）；HA 期望值沿用 `gaps/G6-delivery.md` 第 5 節，依 2026-11-14 的決策更新（`decisions.md`）。
- 契約與差異：`contract.md`（第 9 節刻意差異表，下稱 §8.8）；G6 §5 每一列怎麼對到差異表或測試見 `deviation-trace.md`。

## 結論

1. 門檻不放寬：**0 串號、0 外洩、0 OOM、0 個非預期 5xx**（和 PaaS 的驗收相同）。
2. 29 個情境裡 27 個 Odoo 首發要過；T-22（n8n）等 n8n 開通，T-28（PaaS workspace 專屬）不適用。
3. HA 和 PaaS 不同的期望值，每一條都指到 §8.8 的列；單元與整合測試的檔名見文末登記表。

## 情境表

層級：單元＝`packaging/unit.sh` 的 pytest／node／Playwright（GitHub CI，root、0 skip）；容器＝repo 外 builder 的 `container_acceptance`；
Store＝升版比對 hook；HAOS＝QA HAOS 上的 P9 kit 加人工（每一步要使用者批准）。

| T | 情境 | HA 期望值與差異 | 單元／整合測試 | 容器／Store／HAOS | 切片 | Odoo 首發要過 | §8.8 |
|---|---|---|---|---|---|---|---|
| T-01 | 受測物前置 | 執行中映像 digest＝GHCR 發佈值；記 Core／Supervisor／OS 版本；後端只用合成身分 | `packaging/test_container_probe.py`、`packaging/test_ha_p9_probe.py` | 容器、HAOS | HM-16、HM-19b | 是 | #73 |
| T-02 | 上限、名稱、清單欄位 | 第 6 個額外帳號 409 `profile_limit_reached`＋`limit`；記憶體不足 409＋`limit`、`required_memory_mib`、`available_memory_mib`；名稱規則 HA 加嚴；清單含 `status`、`blocked_reason` | `tests/test_profile_admin_api.py` | HAOS | HM-07、HM-10、HM-19b | 是 | #19、#35、#51 |
| T-03 | 每帳號後端與 token | 每帳號 43 字元 token 互異；Odoo 換 url／database／username 換 token、兩條舊網址都失效；只換密碼不換 | `tests/test_odoo_identity_rotation.py` | HAOS | HM-10、HM-12、HM-19b | 是 | #40 |
| T-04 | N×N 真後端隔離 | 標記只出現在對角線 | `tests/test_odoo_multi_profile.py`（假後端） | HAOS（同一個 Odoo 資料庫、預設＋5 個受限使用者） | HM-19b；各產品升版 | 是（Odoo） | — |
| T-05 | 只由 token 決定帳號 | 錯 token：密鑰網址 404、Bearer 401（PaaS 403）；query 400；密鑰網址上的 `Authorization` 忽略；跨帳號 session 404；31 種網址變形 0 次跨帳號 | `tests/test_profile_routing.py`、`tests/test_mcp_contract_freeze.py` | 容器、HAOS | HM-01、HM-08、HM-16 | 是 | #1、#3 |
| T-06 | 管理 API 授權與帳號 id | 非 Ingress、非管理員一律 403（任何帳號狀態下逐位元相同）；管理員：缺標頭 400、格式錯 400（PaaS 404）、未知 404；MCP token 不能當管理憑證 | `tests/test_admin_pipeline_matrix.py`、`tests/test_profile_admin_api.py` | HAOS | HM-10、HM-16 | 是 | #11、#31、#32 |
| T-07 | 每帳號工具政策 | 存政策只重啟該帳號（HA 收緊也重啟） | `tests/test_profile_admin_api.py` | HAOS | HM-10、HM-11、HM-22 | 是 | #54 |
| T-08 | 輪替、撤銷、撞號 | 舊 token 404／401；撞號（只會來自複製或還原）503、不導向任何帳號 | `tests/test_profile_routing.py` | — | HM-08、HM-10 | 是 | #1、#80 |
| T-09 | 改名、刪除、重建 | 刪除後舊 token 立即失效、子程式停、port 釋放、目錄刪除、`blocked` 帳號立刻重評；重建拿新 id 新 token；刪除 200＋收據 | `tests/test_profile_admin_api.py` | HAOS | HM-10、HM-19b | 是 | #34 |
| T-10 | 跨帳號寫入 | 全被後端擋（寫入前加只允許測試資料的暫時 record rule）；A 的寫入審批 token 在 B 被拒 | `tests/test_odoo_multi_profile.py`（假後端） | HAOS | HM-12、HM-19b | 是 | — |
| T-11 | 並行 0 串號 | 0 串號、0 個非預期 5xx | `tests/test_profile_quotas.py`、`tests/test_profile_routing.py` | HAOS | HM-08、HM-19b | 是 | #15 |
| T-12 | 負載中輪替、刪除 | 只切斷該帳號的 lease，別帳號的串流不斷 | `tests/test_profile_routing.py`、`tests/test_active_token_leases.py`、`tests/test_profile_admin_api.py`（刪除：HM-10） | — | HM-08、HM-10 | 是 | — |
| T-13 | 單一子程式當掉 | 其他帳號 PID 不變；看門狗照 PaaS（2→300 秒、不限次數、120 秒歸零；DQ-20 採 (b)） | `tests/test_profile_lifecycle.py` | 容器、HAOS | HM-09、HM-16、HM-19b | 是 | #14 |
| T-14 | 冷啟動與重啟 | 子程式未就緒時閘道自答 initialize（自答 session），就緒後要求重連；之後每帳號 initialize 200；錯開啟動下「全部就緒」時間有數字 | `tests/test_staggered_start.py`、`tests/test_unconfigured_connect.py` | 容器、HAOS | HM-09、HM-16、HM-19b | 是 | #53、#68 |
| T-15 | port 被佔與同 port | 衝突只停相關帳號；被佔時照看門狗退避，放開後自動恢復 | `tests/test_profile_ports.py` | 容器 | HM-09、HM-16 | 是 | #14 |
| T-16 | 子程式晚驗證 | HA 閘道自答（不是 PaaS 的 503「MCP child is not ready」）；套用狀態每帳號一份 | `tests/test_profile_runtime.py` | — | HM-09、HM-10 | 是 | #68 |
| T-17 | 記憶體與 CPU | J6412（可以的話 J1900）1～6 個帳號的 RSS／PSS、CPU 數字；停機 <30 秒；全域最壞值對 MemAvailable | `tests/test_profile_lifecycle.py`（並行停） | HAOS（HM-19c） | HM-19c；各產品升版 | 是 | #19、#53 |
| T-18 | 互相影響與日誌保留 | 每帳號子程式輸出緩衝不被別帳號擠掉；生命週期 log 帶 id 前 8 碼 | `tests/test_profile_runtime.py`、`tests/test_profile_lifecycle.py` | HAOS | HM-08、HM-09、HM-19b | 是 | #29 |
| T-19 | 背壓與每帳號名額 | 轉送名額等 1 秒；帶 id 的 POST 在名額逾時、准入滿（≤64 KiB）時 200＋`-32003`＋`Retry-After: 5`，更大的 503；位元組預算放不下時讀完丟掉、從頭尾找 id（200 或 503；HM-31，開關關也生效）；GET 串流滿 429＋`Retry-After: 30`（預設 24、額外 8）；CPU 飢餓下閒置帳號健康不逾時 | `tests/test_profile_quotas.py`、`tests/test_gateway_busy_shapes.py`、`tests/test_request_budget_gateway.py`、`tests/test_reply_worker.py` | — | HM-08、HM-14、HM-30、HM-31 | 是 | #15、#16、#17、#101～#105、#108 |
| T-20 | 升級、回退、再升級 | 回退＝還原升級前備份：預設 token＝備份當時的值、額外帳號消失、沒有任何撤銷；再升級後額外帳號不存在、預設不變；文件要求再升級後按「全部撤銷」 | `tests/test_upgrade_zero_rewrite.py` | Store、HAOS | HM-19b、HM-29 | 是 | #71 |
| T-21 | 備份還原 | 預設帳號依 DQ-03（採 (b) A2）；兩個偵測訊號；讀不到的帳號隔離；獨立驗證；核對後才重發；舊收據 410；C1-M1 攻擊序；版本混搭 | `tests/test_restore_detection.py`、`tests/test_restore_lock.py`、`tests/test_restore_review.py` | 容器（root 還原樹）、HAOS | HM-13a、HM-13b、HM-13c、HM-19b | 是 | #20、#21、#69 |
| T-22 | n8n 名額與逾時 | `n8n_session` 每帳號一份；沒後端的額外帳號所有工具回 `backend_not_configured` | `tests/test_n8n_multi_profile.py` | HAOS | HM-25 | 否（n8n） | #28、#62 |
| T-23 | 子程式 bearer 隔離 | 7 支 Python 子程式：不帶、帶錯、帶別帳號、兩個標頭、空字串都 401，自己的 200。n8n（n8n-mcp 維持現狀）：不帶、帶錯、帶別帳號、空字串都 401，自己的 200；另外收下三種寫法（`Bearer` 後兩個空白、兩個標頭都是自己的、第一個是自己的＋第二個是別帳號的），都要先有自己的 child token，沒有越權（§8.8 #37 的註） | `tests/test_child_bearer.py` | 容器 | HM-06、HM-16；各產品升版 | 是（Odoo） | #37 |
| T-24 | 來源檢查 | DQ-11 採 (a)：密鑰網址清單外記一行 would_deny（帶 id 前 8 碼、每帳號節流）、不擋、不加 CORS；Bearer 帶 Origin 403；Headscale 只放 claude.ai | `tests/test_origin_policy.py` | HAOS（記下 Claude.ai 送的 Origin） | HM-08、HM-27 | 是 | #9、#10、#42 |
| T-25 | 紀錄稽核 97 種寫法 | 不比 pin 版 PaaS 差（測試即時算） | `tests/test_redaction_matrix.py` | HAOS | HM-02、HM-19b | 是 | — |
| T-26 | 名稱輸入與顯示 | HA 加嚴的名稱規則；顯示一律跳脫、不執行 | `packages/mcp-admin-ui/tests/browser/profiles.spec.mjs` | — | HM-11 | 是 | #35 |
| T-27 | 公開網址與真實用戶端 | 每種接法各兩個帳號；真 Claude.ai 兩個帳號同時用；代理 log 遮掉 `/private_` | — | HAOS | HM-19b、HM-29 | 是 | #2 |
| T-28 | 平台建立路徑 | 不適用（PaaS workspace 專屬）；HA 的「商店安裝 → 加帳號」併入 T-20 | — | — | — | — | #70 |
| T-29 | 證據掃描與清理 | 合成憑證清單掃描 0 命中；清理證明 | `tests/log_scan.py` | 全層 | HM-19b、HM-29 | 是 | #78 |

## Odoo 首發通過標準（計畫 §10.6 摘要；HM-19b、HM-19c）

1. 單帳號升級 0.4.13 → 0.5.0：預設帳號 token、兩條網址、`state.json` 位元、`tools/list`、政策 0 差異（Store `verify`＋HAOS）。先單帳號，再多帳號。
2. 同一個 Odoo 資料庫預設＋5 個受限使用者：N×N 只有對角線；跨帳號寫入全擋；A 的審批 token 在 B 被拒；換使用者就換 token、兩條舊網址都失效。
3. 31 種網址變形、標頭與 cookie 冒用、兩個交叉案例（Bearer 屬於 B；密鑰路徑屬於 A＋`Authorization` 屬於 B）：0 次跨帳號。
4. 負載中輪替、撤銷、刪除只影響該帳號；刪除後 port 釋放、目錄清除；重建拿新 id 與新 token。
5. 第 6 個額外帳號 409；J6412（可以的話 J1900）上 1～6 個帳號的 RSS／PSS、CPU、冷啟動到全部就緒、第一次 initialize、停機 <30 秒都有數字；
   全域最壞值不超過「MemAvailable－保留量」。
6. 還原演練（full、partial、加密各一次）與版本混搭（0.4.13 的備份還原後再升級；0.5.0 的備份還原到之後的版本）；記下兩個偵測訊號各自有沒有觸發。
7. 升級 → 回退（還原升級前備份）→ 再升級；再升級後按「全部撤銷」並確認。
8. 公開網址：兩個帳號各自可連；真 Claude.ai 兩個帳號同時用；記下 Claude.ai 送的 Origin（S14）。
9. A 撐滿准入、位元組額度、轉送名額，或並行 16 個大回覆時，B、C 照常、健康不逾時；預設帳號撐滿時額外帳號照常；慢讀時 RSS 不超過預算（`contract.md` 第 6 節）。
10. Odoo 來源 IP 冷卻：一個錯密碼帳號連打 5 次，看同庫其他帳號會不會被擋；log 與診斷 0 token、0 帳號名稱；合成憑證掃描 0 命中、清理證明。
11. Store 同步後從 Store 安裝或升級再驗一次；記 Supervisor 版本；重跑 UC-08、UC-10、sentinel 穩定性。

證據規則：只用合成或受限的測試身分，建立與刪除每個真後端身分都要使用者批准；證據只記不含秘密的摘要，token、密碼一律不印、不存；
證據放 repo 外 `artifacts/ha-multiprofile-parity-20261114/`，repo 內只放不含秘密的 release-decision 與 ha-test 文件。

## 測試檔登記表

計畫 §10.3 的新測試檔，加上產品片的暫定名與要擴充的既有檔。`paas-test-mapping.md`、`deviation-trace.md` 與上表引用的 HA 測試，
不是 bb48449 已有的檔，就一定要登記在這裡（對照腳本會檢查）。改名時同時改這張表。

| 檔 | 片 | 狀態 | 驗什麼 |
|---|---|---|---|
| `tests/test_single_profile_golden.py` | HM-01 | 計畫 | 8 個產品的單帳號黃金回歸；開關關時逐位元相同 |
| `tests/test_mcp_contract_freeze.py` | HM-01 | 計畫 | 現行錯誤契約與 31 種網址變形凍結成 `tests/contract/profiles_v1_cases.json` 的 `ha` 欄 |
| `tests/contract/profiles_v1_cases.json` | HM-01、HM-10 | 計畫（資料） | 中立契約配對案例；PaaS 與 HA 不同的案例註明 §8.8 列 |
| `tests/log_scan.py` | HM-01 | 計畫（工具） | 收集測試期間所有 log record，掃合成 token 與帳號名稱 0 命中 |
| `tests/test_redaction_matrix.py` | HM-02 | 計畫 | 97 種 raw＋解碼、#149 query 憑證、組合順序、不比 pin 版 PaaS 差、不退步、`key=` |
| `tests/test_child_port_param.py` | HM-04 | 計畫 | port 預設 3000 時 argv／env 快照不變；給 18000 時各處一致 |
| `tests/test_profile_runtime.py` | HM-05 | 計畫 | 同程序兩套 runtime 互不相通；共用 AdminAuthority 時 CSRF 共用、跨帳號 ETag 409 |
| `tests/test_child_bearer.py` | HM-06 | 計畫 | 7 支 Python 子程式 401／200 矩陣；env 缺或格式錯不啟動；stderr 無 token |
| `tests/test_profile_index.py` | HM-07 | 計畫 | 索引規則（含 PaaS 對照）、簽章含 ctime／nlink |
| `tests/test_profile_store.py` | HM-07 | 計畫 | 只開既有、建立每一步故障注入、mode／owner 在 uid 10001 子程序驗 |
| `tests/test_profile_consistency.py` | HM-07 | 計畫 | 孤兒、撞號、`profile_unavailable` |
| `tests/test_upgrade_zero_rewrite.py` | HM-07 | 計畫 | bb48449 寫出的 schema 4 state 零改寫 |
| `tests/test_identity_fields.py` | HM-07 | 計畫 | 身分欄位與秘密欄位分類；新欄位沒分類就失敗 |
| `tests/test_profile_routing.py` | HM-08 | 計畫 | 路由矩陣、零命中逐位元、撞號 503、兩個交叉案例 |
| `tests/test_router_passthrough.py` | HM-08 | 計畫 | 開關關時分派器不掛、回應逐位元相同 |
| `tests/test_profile_quotas.py` | HM-08 | 計畫 | 真 socket S5、S6；預設帳號當攻擊方；位元組額度；三種過載情況對照 PaaS 表 |
| `tests/test_reply_mask_union.py` | HM-08 | 計畫 | 回覆遮罩含別帳號 token 與 child_token |
| `tests/test_profile_ports.py` | HM-09 | 計畫 | 配 port；四類衝突不 spawn；被佔時照看門狗退避、放開後恢復，搶 port 的程式收到 0 筆（T-15）；spawn 前檢查本身出錯時不起（fail closed）；IPv6 試綁被平台擋（EACCES、EPERM）時跳過並記一行；索引變更後立刻重評（不再衝突的立刻起、新變 disabled 的立刻停、被擋的立刻再查）；`child/restart` 帶 `blocked_reason` |
| `tests/test_profile_lifecycle.py` | HM-09 | 計畫 | 看門狗（T-13；spawn 失敗也照退避重試）、並行停 <30 秒（停機與關閉各有 15 秒上限，卡住時變紅）、log 事件清單；額外帳號的監看停止只標記該帳號，面板重啟後監看恢復並檢查新的子程式世代（DQ-21）；`remove()` 停掉該帳號的監看與子程式 |
| `tests/test_health_backoff.py` | HM-09 | 計畫 | 監看認證退避 15→300 秒（子程式沒回的檢查不動它）、`run()` 照退避等；面板存檔與 `child/restart` 把退避歸零；開通後連兩次失敗才判 unreachable；起點錯開：每帳號的起點值，以及 `run()` 真的等到起點才做第一次檢查；自己的 client；不探測不是自己在跑的子程式（DQ-25） |
| `tests/test_extra_child_resources.py` | HM-09 | 計畫 | 記憶體檢查、`oom_score_adj`＝500、`nice` 是「加 5」不是「設成 5」（uid 10001 子程序）；寫不進去或沒有直譯器可跑包裝器時照起並記一行；FD soft limit |
| `tests/test_staggered_start.py` | HM-09 | 計畫 | 錯開啟動，同時最多 2 個；某個帳號的啟動或就緒等待丟例外時記一行、其他照起 |
| `tests/test_monitor_cancel.py` | HM-09（追補） | 新增 | 所有產品：監看與錯開啟動的就緒等待被取消時，HTTP 堆疊吞掉取消（anyio 的連線 task group、httpcore 的讀取期限）也照停；沒開通的單帳號（ProfileRuntime）與開通的 add-on 被 rig 取消或收到 SIGTERM 時都在 30 秒內關完（PR #103 的 CI 失敗） |
| `tests/test_profile_admin_api.py` | HM-10 | 計畫 | 契約第 3 節全部情況；建立與重送不回 token；索引隔離；開關關時照舊 |
| `tests/test_admin_pipeline_matrix.py` | HM-10 | 計畫 | 路由表自動產生的否定矩陣；非管理員逐位元相同 |
| `packages/mcp-admin-ui/tests/profiles.test.mjs` | HM-11 | 計畫 | 標頭規則、`mutate(profile)` 回聲比對、收據帶帳號、N15 新舊斷言 |
| `packages/mcp-admin-ui/tests/browser/profiles.spec.mjs` | HM-11 | 計畫 | 選單、切換藏 token、晚到回應丟棄、XSS 名稱、建立後自動切換、舊格式收據 |
| `tests/test_odoo_identity_rotation.py` | HM-12 | 新增 | 開通的 Odoo 換 url／database／username（含清空）換 token：先停舊子程式、一次寫入、發布、再起新子程式（兩種路由、預設帳號也是）；回應帶新 state 的 `ETag`；8081 分派器不再把舊 token 對到任何帳號、新 token 對到該帳號；舊 token 兩條入口都失效、進行中與排隊中的請求結束；新 token 在新子程式起來前碰不到任何子程式；只換密碼、初次設定、已撤銷不換；停不下、store 拒絕（含舊子程式起不回來）、丟出非預期的例外（固定 503、不是 500）、新檔寫不出來、取代 state 檔途中失敗（`os.replace`、目錄 fsync；額外帳號與預設帳號：預設帳號的新檔已換上時 8081 全部 503）、寫入丟出例外但新 token 已在磁碟上（不重起舊子程式）、新子程式起不來的故障注入；store 的一次寫入與只在結果不明時毒化；沒開通照今天；其他產品開通後不換 |
| `tests/test_odoo_multi_profile.py` | HM-12 | 新增 | 同庫五個帳號各自固定綁定（PaaS 對照）、換其中一個只換它的 token；真的 Odoo 子程式：A 的審批 token 在 B 被拒、A 自己執行得了，兩帳號 state 相同的對照；DQ-30 讀取並行維持 1 |
| `tests/test_new_origin_secret.py` | HM-12 | 新增 | 開通後全部產品改網址來源（scheme、host、port）沒帶那條網址的已存秘密 422（DQ-40 ⑨），少帶一個也 422、全帶就存；同來源、帶 null、整份取代不檢查；在 If-Match 之後；沒開通照今天；經分派器只檢查選定帳號 |
| `tests/test_restore_detection.py` | HM-13a | 計畫（root） | root 擁有的還原樹、標記在 pass 1 前落盤、sentinel 各情況 |
| `tests/test_restore_lock.py` | HM-13b | 計畫 | 守門 A～F 步、隔離、獨立驗證、DQ-03 兩種模式、UC-24 三情境 |
| `tests/test_dormant_profiles.py` | HM-13b | 計畫 | 開關關＋帳號資料 → 全撤銷；重新開通未核對前不能重發 |
| `tests/test_revoke_all.py` | HM-13b | 計畫 | 全部撤銷第 k 個失敗、`.revoke-all-pending` |
| `tests/test_restore_review.py` | HM-13c | 計畫 | 核對卡欄位、未核對前 rotate 409、匯出不含憑證 |
| `packages/mcp-admin-ui/tests/browser/restore-review.spec.mjs` | HM-13c | 計畫 | 核對卡、全部撤銷兩段確認、隔離目錄只能刪 |
| `tests/test_gateway_stream_endings.py` | HM-14 | 計畫 | `-32005` 沒有 traceback、`-32004` 依原因 |
| `tests/test_gateway_busy_shapes.py` | HM-14 | 計畫 | `-32003` 形狀與文字 |
| `tests/test_gateway_queue_ha.py` | HM-14 | 計畫 | 排隊上限、排隊中斷線不送 |
| `tests/test_initialize_generation.py` | HM-14 | 計畫 | initialize 世代 |
| `tests/test_carries_no_request.py` | HM-14 | 計畫 | 通知保留名額照 PaaS `_carries_no_request` 規則與反例；HM-31：准入滿時通知照樣送到 |
| `tests/test_request_budget.py` | HM-31 | 計畫 | 請求內容位元組預算的推導（cgroup、MemAvailable−256、固定 32 MiB）、兩層、份額上限 64 MiB、小請求不扣、轉送大小、歸還、頭尾找 id |
| `tests/test_request_structure.py` | HM-31 | 計畫 | JSON 結構守門（深度、元素、UTF-8、閉括號、邊界、放大語料）與拒收形狀；n8n 先跑同一道守門 |
| `tests/test_request_budget_gateway.py` | HM-31 | 計畫 | 開關關與開：預算拒絕讀完丟掉回 id、沒帶長度中途切斷、讀取閒置 408、整體 60 秒照舊、份額不跨帳號、全 add-on 預算共用；HM-31 審查：`Content-Length`＋`Transfer-Encoding` 照實際收到的位元組（含真的 h11 socket）、宣告超過 16 MiB 讀之前 413、讀完丟掉的閒置與整體界線、只留頭尾、從尾端找 id |
| `tests/test_child_identity.py` | HM-15 | 計畫（條件式） | 別的程序先綁 port → 不轉發；uid 10001 子程序驗降級 |
| `tests/test_upgrade_hooks.py` | HM-16 | 計畫 | Store hook 只讀、與版本無關 |
| `packaging/test_container_probe.py` | HM-16 | 既有，擴充 | 多帳號探針、`/data/mcp` 修復規則與項目預算 |
| `packaging/test_ha_p9_probe.py` | HM-16 | 既有，擴充 | P9 kit 帳號參數、交叉矩陣 |
| `packaging/test_validate.py` | HM-17 | 既有，擴充 | 多產品版號運算式 |
| `packaging/test_release_gate.py` | HM-17 | 既有，擴充 | release_gate 只認產品自己的紀錄 |
| `tests/test_saved_destinations.py` | HM-20 | 既有，擴充 | 開通後存檔拒 loopback（全部產品，含 n8n；各種寫法）；區網照放；沒開通與替身開關照今天。HM-12：開通後改到另一個來源的 `backend/patch` 一起帶那條網址的秘密（DQ-40 ⑨） |
| `tests/test_backend_loopback.py` | HM-20 | 新增 | 開通後子程式環境多 `WOOW_MCP_DENY_LOOPBACK=1`（預設帳號與額外帳號的 port 都有），執行期字面與解析後的 loopback 都拒（每個產品；n8n 的 API 與官方 MCP 端點，含混合答案）；`apps/` 的子程式程式碼不拿掉這個變數（看原始碼）；HM-09 的 exec 包裝器原樣交給額外帳號的子程式（看原始碼；端到端：`run_product` 的 ProfileManager 起真的預設帳號與額外帳號 Odoo 子程式，各自的 loopback 假後端收到 0 個請求）；webhook 維持 permissive；替身開關只在測試 |
| `packaging/test_container_acceptance.py`、`packaging/test_container_probe.py` | HM-20 | 既有，擴充 | 開通的產品（`MULTI_PROFILE_PRODUCTS`）的容器驗收要照 Headscale 開一次性 internal bridge、假後端綁容器私有位址；今天集合是空的，只驗 Headscale，產品一開通就逼升版 PR 補上 |
| `tests/test_litellm_multi_profile.py` | HM-21 | 暫定名 | 兩把假 virtual key、bearer 401 矩陣、政策各自 |
| `tests/test_nextcloud_multi_profile.py` | HM-22 | 暫定名 | 兩個使用者、存政策只重啟該帳號、換 url／username 換 token |
| `tests/test_emqx_multi_profile.py` | HM-23 | 暫定名 | 兩帳號政策各自 |
| `tests/test_hermes_multi_profile.py` | HM-24 | 暫定名 | 子程式環境各自、長 chat 不卡別帳號 |
| `tests/test_n8n_multi_profile.py` | HM-25 | 暫定名 | nodes.db 每帳號、沒後端的額外帳號回 `backend_not_configured` |
| `tests/test_headscale_multi_profile.py` | HM-26 | 暫定名 | 同網址同 key、不同政策的兩帳號各照自己的政策 |
| `tests/test_origin_policy.py` | HM-27 | 暫定名 | report-only 不改回應位元組；would_deny 記錄與節流 |
| `tests/test_reply_worker.py` | HM-30 | 計畫 | 一條執行緒、依帳號輪流、每帳號同時 1 筆；工作例外照今天、被取消的撤回、執行緒自己停時立刻回 502 且 add-on 結束、停機時排隊的立刻結束；自己的堆疊（深巢狀回覆 502、不當掉）；JSON 與 SSE 輸出位元組和迴圈內處理相同（逐案對照）；開關關時沒有執行緒、照迴圈處理；CPU 飢餓（可控注入：迴圈停頓、B 的 p99）；真實 8 MiB 回覆的迴圈停頓（量測）；待送回覆上限（預設帳號與額外帳號各自；tools/call 200＋`-32003`、64 KiB 分段、怎麼還；在轉送名額之前判斷）；慢讀 RSS（ASCII、emoji，含 SSE 期間的轉送內容；`contract.md` 第 6 節門檻）。HM-30 審查補：檢查點的喘息與解析器檢查點（計數）、state 讀不到時兩條路的順序相同、token 換了時排隊的工作撤回、工作執行緒在 listener 服務前啟動與停了之後才停；D1：分段序列化和 json.dumps 逐位元相同（隨機值與邊界值，分段大小調到最小）、長字串與大的 list／dict 一次最多一段、七種形狀（mixed、大量小物件、CJK、emoji、長 ASCII 字串、跳脫字元、巢狀）與兩種事件的真實 8 MiB 回覆和迴圈內處理逐位元相同、迴圈單次停頓 ≤50 ms、14 種串流在工作執行緒切框也逐位元相同、處理工作時循環回收器關著、回覆分段放掉且不碰工具清單；D3：CPU 飢餓量整段（讀取＋處理）、租約剛查過時少讀 state（之後在磁碟上換掉的 token 照樣擋下）、開通時回覆每段一次 token 檢查。HM-30 第二輪審查補：扁平陣列在解析（每 1,024 個數字）、遮罩與成本計算（每 1,024 個成員）都有檢查點（計數；遮罩後鍵相撞時順序照舊）、五種扁平數字陣列（ID、小整數、整數與浮點數的時間序列、浮點數）的真實 8 MiB 回覆迴圈單次停頓 ≤50 ms 且逐位元相同、短字串清單整段一次解析只印不斷言（MF-1；使用者 2026-11-17 定 Q1：接受，HM-19c 實測再定）；秘密放在切段邊界、長字串、3 萬列與 5 千個鍵，JSON 與大 SSE 事件在工作執行緒照樣全部遮掉、逐位元相同（MF-3）；縮小額度一次湧入時 JSON 最多轉送名額＋1 個、帳上不超過上限＋名額×一個回覆，提早扣的在請求結束時還回（MF-2）；短的 emoji／中文字串清單每次 C 編碼器的輸出不超過 64 KiB（S-4）；沒有秘密可遮時值與 twin 是同一個也只放一次 |
| `tests/test_health_tolerance.py` | HM-30 | 計畫 | CPU 飢餓下閒置帳號（B、C）的健康檢查不逾時、每次在該做之後 d（0.25 秒）內做完、判定一直是 reachable；飢餓中 B 的後端失敗一次不擋、連兩次才擋、C 不受影響（連兩次失敗的規則本身 HM-09 已做，測試在 `tests/test_health_backoff.py`） |
