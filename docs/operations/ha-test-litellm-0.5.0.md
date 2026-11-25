# LiteLLM 0.5.0：展示機 HAOS 驗收（火車 A）

2026-11-24 15:43–16:43（台北）。對象是負責人指定的展示機 woowtechshow（J6412，正式 HAOS：Core 2026.7.2、OS 18.1、Supervisor 2026.11.0）。
測的是**發佈到 GHCR 的那顆映像**：`ghcr.io/woowtech/amd64-mcp-litellm:0.5.0`，manifest `sha256:7487f1dd30950a66140beb13e68953d00118a184b50e4e8b0147f7503a93b4a6`、
映像 ID `sha256:4c391c21ebd2af65e9f8d3f6187fd2b9f78307e016db229028512df03a6a4219`（`release.yaml` run 45299044628，source `84483b7`）。升級起點是 Store 上的 0.4.14（映像 ID `e9e31155baa5`）。
執行中的映像 ID 每次安裝、升級後都與上面相同。

後端：展示機的 LiteLLM add-on（0.1.15，執行中）；在上面建兩把「只限一個模型、6 小時到期、預算 0.01」的測試 virtual key（a、b，不用 master key），測完刪除。

做法：火車 A 工具包 R3（P9 驅動＋面板 API 驅動），用測試專用的 HA 管理員登入；測試副本是本機 add-on `local_woow_mcp_litellm_mptest`，`config.yaml` 的 `image:` 指向已發佈的 tag，由 Supervisor 自己拉（不側載），升級起點是 Store 上的 0.4.14。每個改狀態的步驟前有加密的局部備份；守門程式（負載、可用記憶體、記憶體 PSI、swap 增量、別條線的 Supervisor 工作）不過就停；03:30–05:00 不測。測完刪除測試 add-on、測試憑證、HA 測試管理員與這一輪的備份，只留後端的加密保護備份給負責人決定；展示機鎖歸還前，前置檢查各項都回到起點。

## 結果

| 項目 | 結果 |
|---|---|
| 舊版基準（0.4.14） | 寫入全關、預設帳號接 key a、token 不變；P9 29/29（3 個真讀取、26 個寫入拒絕）；token 輪替→撤銷→重發照契約；重啟正常 |
| 升級 | 0.4.14 → 0.5.0：執行中映像 ID 相符；`state.json` 逐位元相同；新增 `.instance-sentinel`、`.instance-record`；預設 token 不變；P9 29/29 |
| 帳號上限（T-02） | 3 個額外帳號；第 4 個回 409 `profile_limit_reached`；刪除後 token 立即失效（Bearer 401、密鑰網址 404） |
| 真後端隔離（T-04） | 預設帳號只看到模型 a、p9-b 只看到模型 b；admin 類讀取被 LiteLLM 依 key 權限拒絕（預期） |
| 只換 key 不換 token（T-03） | LiteLLM 的身分由 key 決定：換 key 後 token 不變 |
| 只由 token 決定帳號（T-05） | 容器內 8/8、P9 `--cross` 13/13：各自的 token 兩種接法都通，拿別人的 session 一律 404，未知 token 401／404 |
| 輪替、撤銷、暫時帳號（T-08、T-09） | 照契約；暫時帳號建立、交叉、刪除後舊 token 被拒，清單沒有孤兒 |
| 存政策只重啟該帳號（T-07） | 只給 p9-b 一個寫入授權（只開不呼叫，那支工具會花錢）：只有 p9-b 的子程式 PID 變，預設帳號的不變 |
| 殺子程式、重啟（T-13、T-14） | 只殺 p9-b 的子程式，2.5 秒重生、其他 PID 不變、容器沒重啟；add-on 重啟後 token 不變、交叉全過 |
| 局部還原（一般、加密） | 兩種都 PASS：撤銷通知 1 行、每個帳號 1 行撤銷、沒有 not finished；還原前的 token 全被拒；舊收據 410 `operation_restored`；核對前重發 409 `restore_review_required`；核對後重發；刪掉的帳號回來且撤銷、備份後建的消失；演練備份自刪 |
| 版本混搭（T-20） | 升級前（0.4.14）的備份還原到 0.5.0 上：13 秒，映像回 0.4.14、只有預設帳號、預設 token 為備份當時的值、沒有撤銷；再升級到 0.5.0：只有預設帳號、token 不變；全部撤銷後重發正常 |
| T-17（只記錄） | 閘道 RSS 61 MiB、預設帳號子程式 102 MiB、容器 129 MiB；停機 2 秒；重啟後約 10 秒就緒 |
| 清理 | 合成憑證掃描 76 檔 0 命中；測試 add-on、測試 key、HA 測試管理員、這一輪的備份都已刪；後端照常執行，Store 版 MCP LiteLLM 維持原狀 |

## 偏離（負責人接受）

- 不做完整備份還原與主機重開，只做局部還原（一般與加密）、版本混搭（T-20）、add-on 重啟（負責人 2026-11-23）。
- 容量與極端壓力只記錄、不擋發版（負責人 2026-11-23）；T-17 的數字照記，契約暫定值（每子程式 160 MiB、最壞 896 MiB）只是公式，未量最壞情況。
- T-07「p9-b 的工具清單多了授權的那一支」沒有另外記數字（只驗了主要判準：只重啟自己的子程式）。

## 已知限制（不擋這一版）

- 經 Cloudflare 開 HA 時，面板不能儲存「瀏覽器來源檢查」設定（F2，與 Odoo 0.5.1 同一份面板）：只影響這一張卡片，預設值照常運作，從區網開 HA 可以儲存；下一版修。負責人 2026-11-24 決定先發。
- 後續（2026-11-25）：F2 在維修版修好了：面板也把 Cloudflare 這類代理改成的弱 ETag（`W/"…"`）當成同一個版本，送出時照舊送強的 `If-Match`，add-on 的比對沒有放寬；帳號清單的 ETag 用同一個讀法，一起修；但在 Cloudflare 上量到不受影響（2026-11-25 在真的 HA 加 Cloudflare 上量，瀏覽器的 `Accept-Encoding: gzip, deflate, br, zstd`）：`api/origin-policy`（94 位元組）被 Cloudflare 壓成 br、ETag 變弱，所以卡片不能存；`api/profiles`（161 位元組）由 Home Assistant 自己先壓 gzip、ETag 維持強；只有前面的代理改寫 HA 沒壓縮的回應時才可能變弱，例如用戶端不收壓縮（`docs/multi-profile/unreleased-changes.md` A11）。上面寫的是這一版映像的行為，沒有改。

## 測試工具的問題（不是產品問題）

- `addon.sh verify <ID>` 永遠拿 0.5.0 的 tag 比對，回退後驗 0.4.14 會誤報；改直接查容器的映像 ID。
- `addon.sh uninstall` 對已不存在的 app 誤印 `STILL-INSTALLED`（`ha apps info` 也回 0）；實查 app、容器、`/addons` 資料夾都不在。

## 證據

`artifacts/ha-multiprofile-parity-20261114/takeover-20261123/train-a-kits/evidence-litellm-20261124/`（各步驟 log、結果表；不含任何 token、密碼或 key）。
Store 升級乾跑：`artifacts/ha-multiprofile-parity-20261114/wave5/store-dryrun-45299044628-showroom-20261124/`（PASS）。
