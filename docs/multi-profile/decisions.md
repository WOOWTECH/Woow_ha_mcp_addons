# 多帳號決策紀錄（DQ-01～DQ-46）

- 狀態：HM-00 起草（2026-11-14）；HM-07 同步 2026-11-14 21:5x 與 2026-11-15 06:1x 的決定；HM-06 同步 2026-11-15 08:0x 的 DQ-08；
  2026-11-15 文件同步 PR（HM-00 補正）把 DQ-05、10、15～18 依 DQ-40 (a) 記成已定，DQ-38 補 08:2x 的定案；HM-09 記 2026-11-15 11:2x 的
  DQ-21、DQ-25；HM-20 同步 2026-11-15 15:3x 的 DQ-10 子題與 UC-10 做法。之後每定一題就改這張表與變更紀錄，並在定案的切片 provenance 筆記寫一行。
- 來源：計畫 §13（repo 外，`artifacts/ha-multiprofile-parity-20261114/PLAN-zh-TW.md`）。題號沿用計畫與 FEATURE-MATRIX §4.1、§6.1。
- 決策對契約的影響已套進 `contract.md`（第 9 節刻意差異表的「類型」與「HA」欄）。

## 結論

- 46 題裡 34 題已定（DQ-08 只定了 HM-06 的部分）：
  - 2026-11-14（台北 13:4x）：使用者**全部採用計畫 §13.1 的 15 項建議**（16 題；DQ-07 與 DQ-29 同一項）。
  - 2026-11-14 21:5x：§13.2 的 DQ-09、DQ-12、DQ-19 採用計畫建議；DQ-38 選 (a) 原樣 vendor。
  - 2026-11-15 06:1x：DQ-36 補上合併授權：不改版號的多帳號功能 PR 由主對話在 CI 全綠後依序合併；升版 PR 仍要使用者逐次批准。
  - 2026-11-15 08:0x：DQ-08 的 HM-06 部分照計畫 §8.3。計畫 §13.2 把它列為 DQ-40 的細節（「DQ-40 一次確認後照做」），DQ-40 (a)
    已在 2026-11-14 13:4x 採用，所以主對話確認照做、沒有另問使用者。listener 檢查仍待定（HM-15）。
  - 2026-11-15 08:2x：DQ-38 補 HM-02 審查 MF-3、MF-4 的定案（主對話）：vendored 的 `log_redaction.py` 記在 `runtime-patches.json`；
    Release train 會不會比對 vendored 檔，以 HM-02 PR 上的 `Release train / wvt check` 為準。
  - 2026-11-15 文件同步：DQ-05、10、15、16、17、18 記成「已定（依 DQ-40 (a)，2026-11-14）」。計畫 §13.2 第一列把這幾題（和 DQ-08）列為
    「DQ-40 各項的細節」，建議「照 §5.3、§6、§8.5、§8.7、§9」，理由是「DQ-40 一次確認後照做」；DQ-40 (a) 是 2026-11-14 13:4x 使用者採用的
    §13.1 建議。每題照哪一節寫在第 1 節；沒有另問使用者。DQ-10 的 n8n `WEBHOOK_SECURITY_MODE=permissive` 要不要維持，計畫沒寫，仍待定（第 4 節）。
    這次只改 `docs/multi-profile/`，沒有 provenance 筆記；各負責片照做時在自己的筆記引用。（`WEBHOOK_SECURITY_MODE` 子題 2026-11-15 15:3x 已定，見下面 15:3x 那一點。）
  - 2026-11-15 11:2x：§13.2 的 DQ-21、DQ-25 採用計畫建議（使用者在主對話定；HM-09 寫進來，做法見 HM-09 的 provenance 筆記）。
  - 2026-11-15 15:3x（使用者）：DQ-10 子題定案：n8n 子程式的 `WEBHOOK_SECURITY_MODE=permissive` **維持不動**（負責人 2026-10-15 的決定）；
    HM-20 只管設定的後端網址（存檔與執行期拒 loopback），不改 webhook 模式；多帳號時要不要收緊 webhook，留到 HM-25（n8n 開通）前的
    獨立安全審查再決定。同時定 UC-10 的做法（記在 DQ-17）：HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭，探針實測不通再補網址路徑備案。
    兩項都寫進 HM-20 的 provenance 筆記（`docs/provenance/ha-multiprofile-HM-20-20261115.md`）。
  - 2026-11-15 17:4x：DQ-13、DQ-14、DQ-30、DQ-31 採用計畫建議（HM-10、HM-11、HM-12 用）。
  - 2026-11-15 18:1x：DQ-43 先把 `checks` 上限調到 60 分鐘（HM-08 的 #99 `checks` 跑到 2079 秒，離 40 分鐘上限只剩 5 分多）。
- 其餘 12 題（§13.2 的 2 題、§13.3 的 10 題）維持「待定」（DQ-21、DQ-25 已由 HM-09 的 PR 移到第 1 節），每題寫了負責片與最晚何時要定；計畫的建議照列，但不是決定。

## 1. 已定（計畫 §13.1 全部；§13.2 的 DQ-05、DQ-08（HM-06 部分）、DQ-09、DQ-10、DQ-12～DQ-19、DQ-21、DQ-25、DQ-30、DQ-31、DQ-38、DQ-43）

| DQ | 題目 | 結論 | 狀態 | 負責片 |
|---|---|---|---|---|
| DQ-01 | Bearer `/mcp` 也依 token 選帳號 | (a) 要：Bearer 的 token 值就是帳號 token，和密鑰網址用同一個解析器 | 2026-11-14 使用者採用建議 | HM-08 |
| DQ-02 | 新帳號初始政策 | (a) 複製預設帳號當下的政策（PaaS 做法）；`n8n_session` 不複製；建立不記 history | 2026-11-14 使用者採用建議 | HM-07、HM-10 |
| DQ-03 | 還原資料沒用過多帳號時，預設帳號要不要也撤銷 | (b) A2，首發先這樣：只有磁碟上有帳號資料的還原才撤銷預設帳號；單帳號安裝的還原行為和今天一樣，面板與 log 提示「權杖已回到備份當時的值」；白名單節奏（DQ-35）做到後再評估改 (a) | 2026-11-14 使用者採用建議 | HM-13b、HM-13c |
| DQ-05 | Odoo 換身分換 token；Nextcloud、Hermes 是否比照 | 照計畫 §9：Odoo 換 url／database／username 時先停舊子程式 → 一次寫新連線＋新 token＋history（沿用 `rotate`）→ `TokenAccess.committed()` → 起新子程式；提交失敗用舊 state 重起；回 `token_rotated:true`；只換密碼或初次設定不換。比照的範圍照 DQ-40 ⑩：Nextcloud 換 url／username、Hermes 換 gateway_url／dashboard_url／dashboard_username 也換 token | 已定（依 DQ-40 (a)，2026-11-14）：照計畫 §9 的 Odoo、Nextcloud、Hermes 列 | HM-12、HM-22、HM-24 |
| DQ-06 | 對齊基準 | (a) PaaS main `69ac425`；#149 與 `091dfbc` 合併後收進來；之後的變動每片開工前列出（`docs/provenance/multi-profile-parity-baseline.md`）。補記：同日兩條都已合併——`091dfbc`（#150，main `5a06d53`，只改文件、測試與註解）、#149（main `7d111b1`，14:19，正式碼只動 `log_redaction.py`）；收進來的內容與影響見基準文件第 3 節 | 2026-11-14 使用者採用建議 | 每片（provenance）；HM-02（#149）、HM-14（#150） |
| DQ-07 | 名額與記憶體規則 | (a) 照 `contract.md` 第 5 節：開通後預設帳號也有位元組額度 64 MiB、待送回覆 32 MiB、串流 24；額外帳號准入 32、轉送 16、串流 8、額度 64 MiB；回覆一條工作執行緒依帳號輪流；健康檢查連兩次失敗才判壞；MemAvailable 在建立、存後端、起子程式時檢查；`oom_score_adj` 500、`nice` +5；量測後定案 | 2026-11-14 使用者採用建議 | HM-08、HM-09、HM-30、HM-19c |
| DQ-13 | endpoint 位置 | 全域一個：只存在預設帳號，所有帳號共用 | 2026-11-15 17:4x 使用者採用建議 | HM-10 |
| DQ-14 | 刪除細節 | 先撤銷 token 並抹掉後端憑證再刪；孤兒不自動刪，面板列出可刪；不做軟刪除；兩段確認 | 2026-11-15 17:4x 使用者採用建議 | HM-10 |
| DQ-29 | 出貨機規格與帳號上限 | (a)，和 DQ-07 同一項：上限＝min(5、產品上限、記憶體條件)；使用者提供出貨機的記憶體規格與可量測的硬體（J6412、J1900） | 2026-11-14 使用者採用建議（規格待提供，見第 4 節） | HM-19c |
| DQ-08 | 子程式身分做法 | HM-06 部分照計畫 §8.3：7 支 Python 子程式只收剛好一個 `Authorization`，以 `hmac.compare_digest` 比對 `Bearer <WOOW_MCP_CHILD_TOKEN>`（值是 state 的 `child_token`），不符回 401、不寫細節；環境變數缺、空或不符 `[A-Za-z0-9_-]{43}` 就拒絕啟動；不從環境變數拿掉。n8n（`AUTH_TOKEN`）與已下架的 Odoo Manage 維持現狀（n8n 收下的寫法見 `contract.md` 第 9 節 #37 的註）。listener 檢查：條件式（DQ-37、UC-04），屬 HM-15 | DQ-40 (a) 的細節：計畫 §13.2「DQ-40 一次確認後照做」，DQ-40 (a) 是 2026-11-14 13:4x 使用者採用的建議；2026-11-15 08:0x 主對話確認照計畫 §8.3 做，沒有另問使用者（listener 檢查待定，負責片 HM-15） | HM-06、HM-15 |
| DQ-09 | 撞號回應碼 | 503 `{"error":"state unavailable"}`：撞號是資料完整性錯誤，不轉任何帳號 | 2026-11-14 21:5x 使用者採用建議（計畫 §13.2） | HM-08（HM-07 只偵測） |
| DQ-10 | 後端網址拒絕 loopback | 照計畫 §8.7：產品開通後，存檔與執行期都拒 127.0.0.0/8、::1、`localhost`，n8n 也納入存檔檢查；HM-20 排在 R1 之前，Odoo 0.5.0 就有。子題（n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 要不要維持）：**維持不動**（負責人 2026-10-15 的決定）；HM-20 只管設定的後端網址，不改 webhook 模式；多帳號時要不要收緊 webhook，交 HM-25（n8n 開通）前的獨立安全審查再決定（第 4 節） | 已定：loopback 部分依 DQ-40 (a)（2026-11-14），照計畫 §8.7「後端網址拒絕 loopback」一點；`WEBHOOK_SECURITY_MODE` 子題 2026-11-15 15:3x 使用者定（維持，交 HM-25 前再評估） | HM-20（loopback）、HM-25（webhook 再評估） |
| DQ-11 | 密鑰網址的 Origin 預設 | (a) 首發做 HM-27：服務層級清單預設 `https://claude.ai`、report-only 記 would_deny、不加 CORS；Bearer 帶 Origin 403；Headscale 只放 claude.ai。第二問（Claude.ai 送 `https://claude.ai` 時 Bearer `/mcp` 要不要精確放行）等 HM-03b 或 HM-19b 實測後再問 | 2026-11-14 使用者採用建議（第二問待定，負責片 HM-27） | HM-27 |
| DQ-12 | 索引壞與被外改 | 8081 全部 503（含預設帳號）；面板照開，提供「隔離帳號索引」動作；HA 上沒有支援的手動修復（只能還原備份、解除安裝或用這個動作）。外改的判定維持到重啟 | 2026-11-14 21:5x 使用者採用建議（計畫 §13.2） | HM-07（判定）、HM-08（503）、HM-10（隔離動作） |
| DQ-15 | 帳號 CRUD 寫入保護 | 照計畫 §5.3 第 7 點：帳號設定照今天（帳號 ETag；HMAC domain 加帳號 id，拿 A 的 ETag 寫 B → 409）；帳號增刪改、核對、索引隔離全部要 If-Match（索引 ETag `"p1-<hmac>"`）；建立、刪除、全部撤銷、索引隔離另要 `Idempotency-Key`；建立與重送都不回 token（`contract.md` 第 3.5 節） | 已定（依 DQ-40 (a)，2026-11-14）：照計畫 §5.3 第 7 點 | HM-10 |
| DQ-16 | 帳號名稱加嚴 | 照計畫 §8.5：去頭尾空白後 1～80 個 code point；拒絕 Cc、Cf（含 bidi、零寬）、Zl、Zp、Cs、Co、未指派；NFKC＋casefold 判重；保留 `default` 與「預設帳號」；名稱只存在索引，不進目錄名、log、MCP 回覆（`contract.md` 第 3.6 節） | 已定（依 DQ-40 (a)，2026-11-14）：照計畫 §8.5「帳號名稱」一點 | HM-10、HM-11（規則已由 HM-07 寫進 `profiles.py`，還沒接線） |
| DQ-17 | 管理 API 選帳號細節 | 照計畫 §5.3：開通後帳號範圍路徑一定要剛好一個 `X-MCP-Profile`（`default` 或 24 位小寫 hex；第 4 點），在角色檢查之後解析：缺 400 `profile_id_required`、多個或格式錯 400 `profile_id_invalid`、未知 404 `profile_not_found`，絕不退回預設（第 2 點 ⑦）。用標頭；UC-10 證實 Ingress 不轉時才改用路徑 `{base}/api/p/<id>/…`（第 11 點；`contract.md` 第 3.3、3.7 節）。UC-10 的做法（2026-11-15 15:3x 使用者定）：HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭；HM-03a 的探針實測不通（Ingress 不轉標頭）時，再補網址路徑備案 | 已定（依 DQ-40 (a)，2026-11-14）：照計畫 §5.3 第 2 點 ⑦、第 4 點、第 11 點；UC-10 的做法 2026-11-15 15:3x 使用者定 | HM-10 |
| DQ-18 | 帳號選擇保存 | 照計畫 §6：帳號選擇只放記憶體，重新整理回預設帳號；標題列固定顯示目前帳號名稱與 id 前 8 碼 | 已定（依 DQ-40 (a)，2026-11-14）：照計畫 §6「帳號選擇只放記憶體」一點 | HM-11 |
| DQ-19 | `/health/ready` 語意 | 只代表預設帳號；逐帳號狀態放 `/api/profiles` 的 `status` | 2026-11-14 21:5x 使用者採用建議（計畫 §13.2） | HM-08、HM-10 |
| DQ-20 | 子程式重啟（看門狗） | (b) 開通的產品所有帳號（含預設）照 PaaS：2→300 秒、不限次數、穩定 120 秒歸零；沒開通維持今天 | 2026-11-14 使用者採用建議 | HM-09 |
| DQ-21 | 監看失敗 | 額外帳號的元件停止只標記該帳號（`failed`），其他照常；預設帳號維持現行：任何元件停止就讓 add-on 結束，由 Supervisor 重啟。HM-09 的做法見 `contract.md` 第 7 節 | 2026-11-15 11:2x 使用者採用建議（計畫 §13.2） | HM-09 |
| DQ-25 | 健康探測 | 各帳號健康檢查起點錯開、間隔不變（15 秒）；後端認證被拒時退避 15→30→60→120→300 秒；開通後連兩次失敗才判 unreachable。HM-09 的做法見 `contract.md` 第 7 節 | 2026-11-15 11:2x 使用者採用建議（計畫 §13.2） | HM-09、HM-30 |
| DQ-28 | OpenDesign、Odoo Manage 開不開放 | 不開放：建立回 409 `profile_product_unsupported`，不顯示新增按鈕 | 2026-11-14 使用者採用建議 | HM-07、HM-10 |
| DQ-30 | Odoo 讀取並行 | 首發維持 1 | 2026-11-15 17:4x 使用者採用建議 | HM-12 |
| DQ-31 | 面板細節 | 用「帳號」；額外帳號範例名稱帶 id 前 8 碼；建立後自動切換；不做總覽與帳號層級權限 | 2026-11-15 17:4x 使用者採用建議 | HM-11 |
| DQ-32 | 發版方式與開關粒度 | (a) 逐產品開關＋Odoo 0.5.0 首發，其他產品分波各自 0.5.0；加發版鎖（同時只有一個凍結中的升版 PR）；R2（LiteLLM、Nextcloud、EMQX）合成一個升版 PR。開關＝發版：關掉要發一個版號更大的新版（一個工作天以上） | 2026-11-14 使用者採用建議 | HM-07、HM-19a、HM-21～HM-26 |
| DQ-33 | 本機測試環境 | (a) 本機可用短的 `/tmp/ha-mp-<隨機>` 當 TMPDIR（跑完刪）；不另建可 sudo 環境；以 GitHub CI 為準 | 2026-11-14 使用者採用建議 | 每片 |
| DQ-34 | 實機與授權 | HM-03a 的授權在開工後 3 週內（HM-08 開工前）；紅隊與上線後監看到 HM-29 再定 | 2026-11-14 使用者採用建議（授權本身待給，見第 4 節） | HM-03a、HM-03b、HM-29 |
| DQ-36 | 合併與署名 | 改版號的升版 PR 仍由使用者逐次批准。不改版號的多帳號功能 PR：2026-11-15 06:1x 起，使用者授權本工作的主對話依序合併（CI 全綠才合、不改版號、不碰 `addons/`），其他人或代理不合併。標題加「⛔ 勿代 merge｜待覆核 — HM-xx …」；commit 與 PR 說明不加 AI 署名 | 2026-11-14 使用者採用建議；2026-11-15 06:1x 使用者授權主對話合併功能 PR | 每片 |
| DQ-37 | 子程式之間的信任邊界 | (a) 接受並寫明：一個子程式被攻破＝整個 add-on 所有帳號被完全控制（含留後門）；加事故處理；README／DOCS 不宣稱子程式層級隔離 | 2026-11-14 使用者採用建議 | HM-18（文件）、HM-15（條件式） |
| DQ-38 | 紀錄遮罩的來源 | (a) 原樣 vendor PaaS `log_redaction.py`（#149 合併版）與純測試；使用者確認這兩樣可以公開放進 HA 的公開 repo。計畫的另外兩個前提由 HM-02 做：先過秘密預檢、確認 Release train 不比對 vendored 檔。補充（HM-02 審查 MF-3、MF-4，主對話 2026-11-15 08:2x 定案）：vendored 的 `log_redaction.py` 記在 `docs/provenance/runtime-patches.json`，不擴充 `runtime-sources.json`（那本只收 `apps/<產品>/vendor/`）；Release train 會不會比對 vendored 檔，以 HM-02 PR 上的 `Release train / wvt check` 為準 | 2026-11-14 21:5x 使用者選 (a)；補充 2026-11-15 08:2x（主對話） | HM-02 |
| DQ-39 | HM-03a 若證實某種還原偵測不到，首發要不要仍出貨 | (a) 不出貨，先修偵測（例如改用 `backup_exclude` 備案） | 2026-11-14 使用者採用建議 | HM-03a、HM-13a、HM-13b、HM-19a |
| DQ-40 | 只在 HA 加嚴的 10 項 | (a) 全部保留，並列入給 PaaS 的回補建議：①管理 API 開通後必帶帳號 ②管理回應帶帳號回聲 ③帳號 CRUD 全部 If-Match、建立／刪除／全部撤銷要 Idempotency-Key ④帳號名稱擋控制與零寬字元、NFKC 判重 ⑤帳號選擇只放記憶體 ⑥7 支 Python 子程式也驗 bearer ⑦後端網址拒絕 loopback ⑧回覆遮罩含所有帳號 token ⑨改 url 來源要重填秘密（全部產品）⑩換使用者欄位換 token 擴到 Nextcloud url／username、Hermes gateway_url／dashboard_url／dashboard_username | 2026-11-14 使用者採用建議 | HM-06、HM-08、HM-10、HM-11、HM-12、HM-20、HM-22、HM-24；回補建議 HM-29 |
| DQ-43 | `checks` 快到 40 分鐘時怎麼辦 | 先把 `.github/workflows/woow-addon-release.yml` 的 `checks` 上限從 40 分鐘調到 60 分鐘（HM-08 補正 PR）；檢查內容不變。拆成平行 job（`checks` 變彙總 job）等真的太慢再議 | 2026-11-15 18:1x 使用者選擇（HM-08 的 #99 `checks` 跑到 2079 秒觸發） | HM-08（觸發的那一片） |

## 2. 待定：首發前要定（計畫 §13.2；HM-08～HM-13 開工前）

| DQ | 題目 | 計畫建議（還沒問，不是決定） | 狀態 | 負責片 | 最晚何時 |
|---|---|---|---|---|---|
| DQ-35 | Core 白名單 | 每次升版 PR 補審到當時最新 Core；HAOS 驗收期間關自動更新；維護節奏：Core 發佈後 14 天內讓所有已開通產品出一版認得它的映像 | 待定 | HM-19a | HM-19a 開工前 |
| DQ-42 | J1900 ISA 檢查是不是每次發版 RC 的必要步驟 | 建議恢復 | 待定 | HM-19a | HM-19a 開工前 |

## 3. 待定：擴產品或加固時再定（計畫 §13.3）

| DQ | 題目 | 計畫建議（還沒問，不是決定） | 狀態 | 負責片 | 最晚何時 |
|---|---|---|---|---|---|
| DQ-04 | n8n nodes.db 放哪 | 每帳號 `/tmp/woow-n8n-mcp/profiles/<id>/`（不進備份）；預設路徑不變 | 待定 | HM-25 | HM-25 開工前 |
| DQ-22 | n8n 額外帳號細節 | 沒後端不起子程式；所有工具（含 7 支文件工具）回 `backend_not_configured`；逾時與限流維持 HA 現值 | 待定 | HM-25 | HM-25 開工前 |
| DQ-23 | legacy SSE | 不支援，文件寫明 | 待定 | HM-18 | HM-18 開工前 |
| DQ-24 | 端點細節 | 維持 HA（錯誤碼、query、尾斜線、330 秒） | 待定 | HM-18 | HM-18 開工前 |
| DQ-26 | Headscale 形態 | 同台不同政策與多台都支援；建議每帳號不同 key，不強制 | 待定 | HM-26 | HM-26 開工前 |
| DQ-27 | EMQX 子程式再擋一次政策 | 不做 | 待定 | HM-23 | HM-23 開工前 |
| DQ-41 | 是否評估 Ingress 的 `X-Remote-User-Groups` 當白名單外的管理身分備援 | 列為評估項目，要獨立安全審查；不是本計畫前提 | 待定 | HM-29 | HM-29 |
| DQ-44 | 0.5.0 之後的升版比對怎麼驗「有額外帳號」的資料 | `seed` 以 root 寫一份合成帳號樹（擁有者 10001），或請 Store 為本 repo 開 `ha_core` | 待定 | HM-16（工具）、HM-21（R2 第一個升版） | R2 升版 PR 前 |
| DQ-45 | 額外帳號的 `serverInfo.name` 要不要帶 id 前 8 碼 | 不改（和 PaaS 一致）；DOCS 建議一個代理只接一個帳號、用戶端名稱帶 id | 待定 | HM-11、HM-18 | HM-18 開工前 |
| DQ-46 | MCP token 不進備份（`backup_exclude`） | 列後續選項，不在本計畫 | 待定 | HM-29（整理後續選項） | HM-29 |

## 4. 決策帶出的待辦（不是新題目）

| 來源 | 待辦 | 誰 | 最晚何時 |
|---|---|---|---|
| DQ-07、DQ-29 | 提供出貨機的記憶體規格與可量測的硬體（J6412、J1900） | 使用者 | HM-19c 前 |
| DQ-34 | HM-03a、HM-03b 的 QA HAOS 授權（拋棄式 echo add-on、三種還原、`oom_score_adj` 實寫） | 使用者 | HM-08 開工前（約開工後第 3 週） |
| DQ-11 | 第二問：HM-03b 或 HM-19b 實測 Claude.ai 送的 Origin 後再問 | 代理問、使用者定 | HM-27 合併前 |
| DQ-06 | #149（`7d111b1`）由 HM-02 依合併版對照；#150（`091dfbc`）由 HM-14 開工時對照；之後的 PaaS 變動照基準文件第 4 節每片列出 | 代理 | 各片開工前 |
| DQ-38 | 選了 (a)：先過秘密預檢；Release train 會不會比對 vendored 檔，以 HM-02 PR 上的 `Release train / wvt check` 為準；vendored 檔記在 `docs/provenance/runtime-patches.json`，不另記 `runtime-sources.json`（2026-11-15 08:2x 定案，見第 1 節） | 代理（HM-02） | HM-02 合併前 |
| DQ-10 | 子題已定（2026-11-15 15:3x，第 1 節）：n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 維持。帶出的待辦：HM-25 開工前的獨立安全審查評估「多帳號時 n8n webhook 要不要收緊」，結果交使用者定。審查要看的事實（HM-20 記下）：① 開通後 n8n 子程式連設定的 n8n（API 與官方 MCP 端點）拒 loopback，但 webhook、chat、form 的網址照 permissive 驗證，仍可指到 loopback（也就是 add-on 自己的 listener）。② `n8n_test_workflow` 的 webhook、form、chat 網址是「設定的 n8n 來源＋路徑」（n8n-mcp 2.96.2 `dist/triggers/handlers/base-handler.js` 的 `getBaseUrl`、`webhook-handler.js`），路徑與標頭由 MCP 呼叫者決定，走 permissive 的 `validateWebhookUrl` 與 `createPinnedAgents`（HM-20 沒包）。③ 所以設定的名稱解析到 127.0.0.1 時，同一個 host:port 的 API 與官方 MCP 端點被擋、webhook 照連，而且帶呼叫者決定的標頭（HM-20 審查 S-7）；n8n 的 API key 不會跟著送（`services/n8n-api-client.js` 的 `triggerWebhook` 把 `X-N8N-API-KEY` 設成 undefined）。可以任意指定網址的舊工具 `n8n_trigger_webhook_workflow` 不在 28 個工具裡（`docs/tool-surface.json`） | 審查代理評估、使用者定 | HM-25 開工前 |

## 5. 變更紀錄

| 日期 | 內容 |
|---|---|
| 2026-11-14 | HM-00 建檔：§13.1 的 16 題記為「2026-11-14 使用者採用建議」；§13.2、§13.3 的 30 題記為待定並寫負責片 |
| 2026-11-15 | HM-07 PR：DQ-09、DQ-12、DQ-19（2026-11-14 21:5x 採用計畫建議）與 DQ-38（同時選 (a)，確認可以公開）移到第 1 節；DQ-36 補 2026-11-15 06:1x 的合併授權；第 4 節的 DQ-38 待辦改成 HM-02 要做的前提 |
| 2026-11-15 | HM-06 PR：DQ-08 的 HM-06 部分移到第 1 節：照計畫 §8.3（DQ-40 (a) 的細節；2026-11-15 08:0x 主對話確認，沒有另問使用者）；listener 檢查仍待定，屬 HM-15（DQ-37、UC-04）。結論的題數改成 21 題已定、25 題待定 |
| 2026-11-15 | 文件同步 PR（HM-00 補正）：DQ-05、DQ-10（loopback 部分）、DQ-15、DQ-16、DQ-17、DQ-18 依 DQ-40 (a)（2026-11-14 13:4x 採用）移到第 1 節，各題照計畫 §9、§8.7、§5.3 第 7 點、§8.5、§5.3 第 2 點 ⑦與第 4、11 點、§6；DQ-10 的 `WEBHOOK_SECURITY_MODE=permissive` 計畫沒寫，記成第 4 節的待辦。DQ-38 補 HM-02 審查 MF-3、MF-4 的定案（2026-11-15 08:2x），第 4 節的 DQ-38 待辦同步改寫。結論的題數改成 27 題已定、19 題待定 |
| 2026-11-15 | HM-08 補正 PR：DQ-13、DQ-14、DQ-30、DQ-31（17:4x 採用計畫建議）與 DQ-43（18:1x 選「先把 `checks` 上限調到 60 分鐘」）移到第 1 節；結論改成 32 題已定 |
| 2026-11-15 | HM-09 PR：DQ-21、DQ-25（2026-11-15 11:2x 使用者採用計畫 §13.2 的建議）從第 2 節移到第 1 節，做法寫在 `contract.md` 第 7 節。結論的題數改成 34 題已定、12 題待定 |
| 2026-11-15 | HM-20 PR：DQ-10 子題記成已定（2026-11-15 15:3x 使用者：n8n 的 `WEBHOOK_SECURITY_MODE=permissive` 維持不動；HM-20 只管設定的後端網址；多帳號時要不要收緊 webhook，交 HM-25 前的獨立安全審查再決定），第 1 節的 DQ-10 列、標題與結論同步；第 4 節的 DQ-10 待辦改成 HM-25 前的審查項目，並依 HM-20 安全審查 S-7 補上審查要看的事實（webhook 網址＝設定的 n8n 來源＋路徑、標頭由呼叫者決定；同一來源 API 擋、webhook 不擋）。DQ-17 補 UC-10 的做法（同時定：HM-10 先照 PaaS 用 `X-MCP-Profile` 標頭，探針實測不通再補網址路徑備案）。題數不變（34 題已定、12 題待定） |
