# EMQX 0.5.0：展示機 HAOS 驗收（火車 A）

2026-11-24 18:41–19:50（台北）。對象是負責人指定的展示機 woowtechshow（J6412，正式 HAOS：Core 2026.7.2、OS 18.1、Supervisor 2026.11.0）。
測的是**發佈到 GHCR 的那顆映像**：`ghcr.io/woowtech/amd64-mcp-emqx:0.5.0`，manifest `sha256:68d2cacd34b9b8aa4170af7f057b864e41e30a282de25839252ea49313d633ef`、
映像 ID `sha256:0318b4d0bfe2f2f03f0d1c1e6596b69321d2edd516400b2c96333c325159da12`（`release.yaml` run 45299052864，source `84483b7`）。升級起點是 Store 上的 0.4.14（映像 ID `408478b76ee0`）。
執行中的映像 ID 每次安裝、升級後都與上面相同。

後端：展示機的 EMQX broker add-on（broker 5.8.9 開源版，平常是停止的）：依負責人 2026-11-24「可以，測完還原」暫時加固（MQTT 只綁本機、關 ssl／ws／wss、dashboard 只綁 hassio 閘道位址）後啟動，測完停止並把 options 改回原值；建三把 6 小時的 API key（a、b administrator，c viewer），測完刪除。別條線的 EMQX 沒有動。

做法：火車 A 工具包 R3（P9 驅動＋面板 API 驅動），用測試專用的 HA 管理員登入；測試副本是本機 add-on `local_woow_mcp_emqx_mptest`，`config.yaml` 的 `image:` 指向已發佈的 tag，由 Supervisor 自己拉（不側載），升級起點是 Store 上的 0.4.14。每個改狀態的步驟前有加密的局部備份；守門程式（負載、可用記憶體、記憶體 PSI、swap 增量、別條線的 Supervisor 工作）不過就停；03:30–05:00 不測。測完刪除測試 add-on、測試憑證、HA 測試管理員與這一輪的備份，只留後端的加密保護備份給負責人決定；展示機鎖歸還前，前置檢查各項都回到起點。

## 結果

| 項目 | 結果 |
|---|---|
| 舊版基準（0.4.14） | 寫入全關、預設帳號接 key a、token 不變；P9 37/38（20 個真讀取、17 個寫入拒絕過；`emqx_manage_authz_rules` 回「這台 broker 沒有 built_in_database 授權來源」＝後端狀態，不是缺陷）；輪替→撤銷→重發照契約；重啟正常 |
| 升級 | 0.4.14 → 0.5.0：執行中映像 ID 相符；`state.json` 逐位元相同；新增 `.instance-sentinel`、`.instance-record`；預設 token 不變；P9 37/38（同一項、同一原因）；`emqx_broker_stats` 成功（審查 F-1 的真映像冒煙：子程式起得來） |
| 帳號上限（T-02） | 3 個額外帳號；第 4 個回 409；刪除後 token 立即失效 |
| 身分隔離（T-04） | 三個帳號 `emqx_broker_stats` 都成功；**撤銷證明**：撤銷 key b → 只有 p9-b 失敗；再撤銷 key c → p9-c 也失敗，預設帳號一直正常＝每個帳號用的是自己的 key。viewer key 的寫入沒有被 broker 擋（見已知限制） |
| 存政策只重啟該帳號（T-07） | 只改 p9-b 的政策（收緊並停用 `emqx_list_clients`、再放寬）：只有 p9-b 的子程式 PID 變；停用時 p9-b 的 `emqx_list_clients` 被擋、預設帳號照常 |
| 只由 token 決定帳號（T-05） | 三個帳號：容器內 18/18、P9 `--cross` 31/31 |
| 輪替、撤銷、暫時帳號（T-08、T-09） | 照契約；沒接後端的暫時帳號，工具呼叫回 `Backend not configured`（不借預設帳號的後端），刪除後被拒 |
| 殺子程式、重啟（T-13、T-14） | 只殺 p9-b 的子程式，2.5 秒重生、其他 PID 不變；add-on 重啟 10.5 秒就緒、token 不變、交叉 31/31 |
| PaaS #153 | `emqx_prometheus_stats` 回 Prometheus 文字成功 |
| 局部還原（一般、加密） | 兩種都 PASS（判準同 LiteLLM，三個帳號） |
| 版本混搭（T-20） | 升級前（0.4.14）的備份還原到 0.5.0 上：13 秒，映像回 0.4.14、`state.json` 回升級前、沒有多帳號殘留、預設 token 為備份當時的值、沒有撤銷；再升級、全部撤銷後重發正常 |
| T-17（只記錄） | 閘道 RSS 62 MiB、預設帳號子程式 102 MiB、容器 129 MiB；停機 2 秒；重啟後約 10.5 秒就緒 |
| 清理 | 合成憑證掃描 86 檔 0 命中；測試 add-on、三把 key、臨時 dashboard 使用者、HA 測試管理員、這一輪的備份都已刪；broker 停止、MQTT 類的埠沒人聽、options 與起點相同；Store 版 MCP EMQX 維持原狀 |

## 偏離（負責人接受）

- 不做完整備份還原與主機重開，只做局部還原（一般與加密）、版本混搭（T-20）、add-on 重啟（負責人 2026-11-23）。
- 容量與極端壓力只記錄、不擋發版（負責人 2026-11-23）；T-17 的數字照記，契約暫定值（每子程式 160 MiB、最壞 896 MiB）只是公式，未量最壞情況。
- 撤銷證明排在最後做（手冊原本排在 T-07 之前；撤銷後那個帳號的後端就壞了，T-07 分不出「被政策擋」還是「後端失敗」），並多做了 key c。
- 驗收期間對 broker 多做了一項暫時加固（測完隨 options 還原移除）；起因是 broker add-on 本身的設定問題，已另外回報負責人。

## 已知限制（不擋這一版）

- 經 Cloudflare 開 HA 時，面板不能儲存「瀏覽器來源檢查」設定（F2，與 Odoo 0.5.1 同一份面板）：只影響這一張卡片，預設值照常運作，從區網開 HA 可以儲存；下一版修。負責人 2026-11-24 決定先發。
- 後續（2026-11-25）：F2 在維修版修好了：面板也把 Cloudflare 這類代理改成的弱 ETag（`W/"…"`）當成同一個版本，送出時照舊送強的 `If-Match`，add-on 的比對沒有放寬；帳號清單的 ETag 用同一個讀法，一起修；但在 Cloudflare 上量到不受影響（2026-11-25 在真的 HA 加 Cloudflare 上量，瀏覽器的 `Accept-Encoding: gzip, deflate, br, zstd`）：`api/origin-policy`（94 位元組）被 Cloudflare 壓成 br、ETag 變弱，所以卡片不能存；`api/profiles`（161 位元組）由 Home Assistant 自己先壓 gzip、ETag 維持強；只有前面的代理改寫 HA 沒壓縮的回應時才可能變弱，例如用戶端不收壓縮（`docs/multi-profile/unreleased-changes.md` A11）。上面寫的是這一版映像的行為，沒有改。
- EMQX 5.9 以前的開源版不強制 API key 角色：這台 broker 接受建立 `viewer` key（不報錯），但用它 publish、新增 ban 都被接受。DOCS 本來就寫角色要 Enterprise 5.4 或 5.9 起所有版本；陷阱是建立時不報錯。這種 broker 上，唯讀帳號只靠 add-on 的寫入閘道與子程式政策擋（17 個寫入拒絕都過）。「唯讀 key 的寫入被 EMQX 擋」在這台無法驗證。DOCS 下一版補一句。

## 測試工具的問題（不是產品問題）

- `mkcreds.py emqx create`：這版 broker 的 `/api/v5/status` 回純文字，工具包當成 JSON 解析而失敗；臨時 dashboard 使用者名稱含 `-`，這版只收英數與底線，而 `emqx ctl` 失敗也回 0。兩個都已修在工具包（不改產品）。
- `addon.sh uninstall` 對已不存在的 app 誤印 `STILL-INSTALLED`（同 LiteLLM）。

## 證據

`artifacts/ha-multiprofile-parity-20261114/takeover-20261123/train-a-kits/evidence-emqx-20261124/`（各步驟 log、結果表；不含任何 token、密碼或 key）。
Store 升級乾跑：`artifacts/ha-multiprofile-parity-20261114/wave5/store-dryrun-45299052864-showroom-20261124/`（PASS）。
