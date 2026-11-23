# 手動更新、備份與回復

**0.4.4 候選（映像待驗收）**：schema 4 在儲存 Odoo 四開關後新增 `odoo_write_switches`，在輪替／撤銷 token 後新增 `token_history`。0.4.3 會拒絕任一新 key；降版必須同時還原升級前 add-on 備份與程式，再檢查復原的 grants／denies，並視需要重發 token、更新用戶端。不要刪除新欄位或手改 state。只啟動且未保存新欄位的舊 schema 4 檔案維持原位元組；這不表示所有更舊版本都相容。見 [0.4.4 發佈決策](release-decision-0.4.4.md)與 [upgrade-notes.yaml](../../upgrade-notes.yaml)。


以下是批准後的受控程序。HA 實證（測試 HA）：n8n 0.1.0→0.1.1 升版、0.1.1 cold backup→partial
restore（[0.1.1 紀錄](ha-test-0.1.1.md)）與 0.1.2 還原修復（[0.1.2 紀錄](ha-test-0.1.2.md)；權杖延續本輪沒驗到）皆成功；0.1.1→0.1.5 每版都以
`ha apps update` 更新全部產品並回歸（[0.1.5 紀錄](ha-test-0.1.5.md) 等），0.1.3 起更新前先做冷備份。其餘五支（Odoo、Hermes、
OpenDesign、EMQX、LiteLLM）未逐支做還原，版本回退（降版＋相容備份）也還沒演練。
只允許操作本次新增的 MCP Add-on，不重啟現有 backend、Core、Supervisor 或 k3s。
映像在私有 builder 建置並通過 supply-chain gate 後發佈到 GHCR（0.1.0–0.1.5；Odoo Manage 只到 0.1.4）；HA 安裝依 [逐步指令](n8n-pilot-commands.md) 逐步批准。

## 0.4.3（負責人 2026-10-27 決定）：舊版安裝第一次啟動一次性全開

和 PaaS 一樣：schema 1/2/3（0.1.x 或 10-03 原型寫的）第一次以新版啟動時，在建立 ProductStore、啟動 MCP 子程序之前，
一次性改成全開（與 0.3.0–0.4.1 升級頁的 `all_on` 完全相同：schema 4、寫入全開、全部寫入授權、停用清單清空；token、
後端連線、對外端點保留），同一次原子寫入加上標記 `owner_defaults_20261025`（applied、at、from_schema），寫入前先把
舊設定的限制存成 `/data/mcp/owner-defaults-20261025-recovery.json`（0600，只有政策、不含 token 與後端）。**MCP 不再停在
503 等確認**，管理面板改成事後通知：顯示「已於 <時間> 自動套用預設全開」與升級前後差異，可選「還原升級前的限制」
（忠實還原：舊設定停用的工具再停用；寫入只保留舊設定授權過的，新版才有的寫入操作也取消，與 0.1.x 實際能做的
相同；新版才有的工具不會被停用（讀取照常可用），不會變成全部停用；升級後管理員自己關掉的不會被打開）或「保持全開，不再提示」。已是 schema 4 的設定（新安裝、0.2.0 之後寫的、或已經在升級頁確認過的）
一律不動。讀不到或壞掉的設定照舊 fail-safe：不遷移、不覆寫，add-on log 寫一行說明後停止（`runtime unavailable; local
recovery required`），請還原升級前的備份。細節見 [legacy migration](legacy-migration.md)。

回退：被遷移過的設定帶有標記欄位，0.4.2 不接受（啟動即停止），要退回 0.4.2 請還原更新前的 add-on 備份；沒有標記的
schema 4 設定與 0.4.2 的欄位完全相同。

## 0.3.0–0.4.1 升級確認與回退邊界（歷史）

schema 1/2/3 第一次啟動會先停在經 HA 管理員驗證的 Ingress 升級頁，尚未建立
ProductStore 或啟動 MCP 子程序；MCP/readiness 回 503。開啟面板、比較兩個預覽並確認
預選 `all_on`（全部功能與寫入），或明確選 `preserve`，才會遷移並正常啟動。
重新整理不會遷移。新安裝及既有 schema 4 正常啟動不變，已撤銷 token 不會被升級復活。
（ws97 2026-10-26 實測：沒人確認就一直 503 超過 15 分鐘；離線驗證：Core 2026.10.2 以後升級頁回 403。下一版已改成上一節的行為。）

`preserve` 會停用新增及需重新審查參數的工具；它不能重現舊二進位的參數限制。
離線 CLI 必須在 runtime 停止後以狀態擁有者執行。限制性政策恢復保留當前 token、
合併 disabled/operation denies 並縮減 grants；它不是完整備份恢復或 schema 降版。
步驟見 [legacy migration](legacy-migration.md)。

雖然仍是 schema 4，0.2.2 不會執行 0.3.0 新增的 operation denies；不可因 schema
相同就宣稱可安全降版。若需要二進位回退，先停止服務，另行審核相容完整備份及當前
token 撤銷／輪替狀態。完整備份可能帶回舊權杖，與不含權杖的政策恢復不同。
目前實測涵蓋隔離 candidate 的舊狀態確認與政策恢復，未宣稱正式 Store 原地升級、
所有產品完整備份回復或斷電恢復已驗收。

## 更新前

1. 逐產品檢查 CHANGELOG、固定 version／immutable digest、支援工具差異、
   typed backend schema、migration 相容性、必要 notices 與來源／安全審查。
2. 確認實際安裝 slug、repository 身分未變，8099/3000 沒有外部 mapping，
   可選 MCP host port 不衝突。改 slug/repo 不是原地更新，要另做資料遷移計畫。
3. 確認 auto-update 關閉。不要追 latest 或覆寫既有版本 tag；六個產品各自更新，
   不要求其他五個一起停止。依序一次更新一支，每支都要在核准清單內。
4. 提前定義可容許中斷、timeout、失敗停止點、回復映像 digest、相容 backup、
   恢復 client 的方法與負責人。受限非正式測試帳號不能擴展到正式副作用。

## 保護備份

manifest `backup: cold`：HA 會停止**這個新 Add-on**來取得一致狀態，MCP clients
短暫中斷，需要重新連線。它不是停止 backend 或整台 HA 的許可。事前告知使用者
此影響、預估窗口、驗證及失敗回復程序。

備份必須包含完整 `/data/mcp`，包含 `state.json`、writer marker 和必要狀態；
只抽一個 JSON 會破壞 missing-state fail-closed 判斷。保存 uid/gid **10001:10001**、
目錄 **0700**、敏感檔 **0600**。不添加共用 HA config/share/backup mounts。

實測（2026-10-05，HA partial restore 本 Add-on）：Supervisor 把 `/data/mcp` 還原成 root 擁有、檔案 0644，
0.1.0 啟動被拒（`bootstrap unavailable`）→ 0.1.0 的 HA 還原不可用（已知問題）。0.1.1 起 bootstrap 只在資料剛好
屬 root 時，檢查後一次改回 10001／0700／0600。還原後一律輪替 MCP token（備份含舊 token）。
0.1.1 實測（n8n）：cold backup 3.1 s（app 隨即 started）→ 輪替 token → partial restore → 7 s 內 started，log `re-owned 2`，
10001:10001、0700／0600，token 回到備份當時的值；之後輪替，工具清單與還原前相同。

0.1.1 修復的邊界與現象（`packaging/entrypoint.py`；獨立 SPEC 與安全審 2026-10-05）：

| 項目 | 行為 |
|---|---|
| 觸發條件 | 既有 `/data/mcp` 本身屬 root（0:0），且 bootstrap 以 root 執行；其他擁有者照舊拒絕 |
| 還原標記（多帳號 HM-13a 起） | 觸發條件成立時，第一遍檢查之前先建空檔 `/data/mcp/.restore-detected`（0600）並寫入磁碟；已存在、而且是單一連結的一般檔就保留原樣。修復時它和其他項目一起改成 10001／0600。多帳號 HM-13b 起，管理程序開機時在任何子程式與 listener 之前讀它（開機守門）：產品沒開通、也沒有帳號資料時，log 一行 `restore guard: the data was restored from a backup; the MCP token is back to its value at the time of that backup (nothing was revoked: no profile data). Rotate it in the panel if it may have leaked since` 後刪除，不改任何 state（還原後請在面板輪替 token，同下面的說明）；有帳號資料時跑完整守門（撤銷每個帳號的 token、連預設帳號，隔離讀不到的帳號、驗證）後才刪；產品已開通但沒有帳號資料時不撤銷（DQ-03 (b)：同上，log 一行），只寫還原紀錄、重建 sentinel 後才刪；沒做完就不啟動、下次開機重做（多帳號契約 `docs/multi-profile/contract.md` 第 1.3 節）。多帳號 HM-13c 起，沒有撤銷權杖的還原（沒有帳號資料）在刪標記之前另存 `/data/mcp/restore-notice.json`（只有時間，0600，不含秘密），面板顯示還原提示，到預設帳號重新產生或撤銷權杖為止（見下一節）；存不下時照常啟動、標記留到下次 |
| 建不出標記 | log 一行，括號裡是原因：errno 名稱（例如 `ENOSPC`、`EROFS`、`EIO`），或 `name in use`（名稱被目錄、連結或有第二個連結的檔占用），不含檔案內容或秘密。`/data/mcp` 有帳號資料（`profiles.json` 或 `profiles`）時印 `bootstrap: /data/mcp was restored with profile data but its restore marker (.restore-detected) could not be saved (<原因>); not starting (retried at the next start)`，接著 `bootstrap unavailable; ...`，不改任何項目，下次啟動重試。沒有帳號資料時印 `bootstrap: WARNING: /data/mcp was restored but its restore marker (.restore-detected) could not be saved (<原因>); starting (no profile data)`，照常修復；名稱被連結或有第二個連結的檔占用時，第一遍檢查接著照「拒絕」列拒絕 |
| 接受的內容 | 只有一般資料夾與單一連結的一般檔，擁有者為 root 或 10001，與 `/data/mcp` 在同一檔案系統 |
| 上限 | 最多 512 個項目、8 層；列目錄時邊讀邊數，超過立即拒絕。多帳號 HM-13a 起，512 項包含還原標記（新建標記時，還原樹本身最多 511 項） |
| 描述子 | 修復期間每個核准項目各占一個 descriptor；soft `RLIMIT_NOFILE` 低於 576 時拉到 576（只在修復那次開機；0.1.1 的管理程序會沿用，0.1.2 起修完即還原原值）；hard 低於 576 則拒絕 |
| 依賴 | 需要容器內的 `/proc`（一般檔經 `/proc/self/fd` 改 owner／mode）；沒有 `/proc` 時拒絕 |
| 不處理 | ACL、xattr 不檢查也不保留 |
| 成功 | log 一行 `bootstrap: re-owned N restored entries in /data/mcp`，之後一般啟動（0.1.2 起在 `/data/mcp` 通過最後檢查後才印；多帳號 HM-13a 起 N 含還原標記） |
| 中斷 | 每項先改 mode 再改 owner；修到一半中斷時，未完成的項目仍屬 root，下次啟動會再修 |
| 拒絕 | log `bootstrap unavailable; ...`、app 停在 error。第一遍檢查拒絕時不改任何項目；第二遍途中發現變動時，之前已改的只會是核准過的項目。回報負責人，比對 `/data/mcp` 內容與上表後人工處理，不要放寬權限或手動 chmod 繞過 |

**備份含 backend 密碼/API key、外部及 child token、endpoint／工具政策，視同秘密。**
限制下載與儲存人員、使用受控加密儲存與保留政策；不可入 Git、Actions artifact、
issue、聊天或公開 object storage。不要在終端傾倒 JSON。公開驗收只記錄 opaque
backup ID、版本、時間、保管位置類型、權限檢查結論，不記錄內容／金鑰。

## 多帳號版本的還原、回退與全部撤銷（HM-13b、HM-13c）

結論先講：

- **沒開通多帳號、也沒有帳號資料（今天的每個安裝）**：還原後權杖回到備份當時的值，不撤銷（DQ-03 (b)），和以前一樣。
  差別只有提示：add-on 日誌一行之外，面板也顯示「偵測到還原；權杖已回到備份當時的值。若備份後曾輪替或撤銷，請立即重新產生」。
  - 到「連線與權杖」重新產生或撤銷權杖後，提示就消失。「知道了」只在這個頁面暫時隱藏，重新整理會再出現（面板不用瀏覽器儲存）。
  - 面板寫的時間是 add-on 啟動時發現還原的時間。只含還原標記、沒有守門的版本（HM-13a 先發的版本）留下的舊標記，要等之後第一次以
    新版啟動才提示。
  - 沒有還原時，面板與每個回應都和以前完全相同；沒開通時不會多任何管理功能。
- **開通多帳號、或磁碟上有帳號資料**：還原後 add-on 在服務任何請求之前撤銷每個帳號的 MCP 權杖（連預設帳號），換掉每個子程式的內部權杖，
  讀不到設定的帳號移到隔離區，寫一份不含秘密的還原紀錄；還原前的操作識別碼一律回 410（備份時還沒有操作紀錄的帳號也是）。
  - 到預設帳號頁的「核對卡」逐帳號核對：名稱、後端身分（網址、資料庫、使用者名稱）、政策摘要都是備份當時的值。無誤就按「已核對」，
    才能到那個帳號的「連線與權杖」重新產生權杖；核對之前重新產生會被拒絕（409 `restore_review_required`）。這時每個帳號的權杖都已撤銷，
    改後端身分的存檔（Odoo：網址、資料庫或使用者；Nextcloud：網址或使用者）不換權杖，照常儲存（核對照樣在等）。
  - 設定不對的帳號直接刪除。隔離區的帳號資料只能刪除；刪除前先撤銷讀得到的權杖、抹掉後端憑證。
  - 帳號索引無法使用時，先在面板「隔離帳號索引」，再回來核對（原本的額外帳號會變成孤兒資料，只能刪除）。
  - 開通了、但還沒建過帳號的還原：同第一點（不撤銷、面板提示），另寫還原紀錄。
  - 沒開通、但磁碟上有帳號資料（休眠）時，額外帳號的權杖已撤銷、不服務；重新開通後一樣要先在核對卡核對才能重新產生。
  - 沒開通、但磁碟上有帳號資料時的還原：預設帳號的權杖也會撤銷，但開關關時**沒有核對卡，也沒有關卡**。直接到「連線與權杖」重新產生
    預設帳號的權杖、更新用戶端。之後重新開通時，核對卡仍會列預設帳號（還原時記為已撤銷、還沒核對）：下一次重新產生前要先按「已核對」。
    這時預設帳號的權杖是有效的，改後端身分（Odoo：網址、資料庫或使用者；Nextcloud：網址或使用者）會換新權杖，所以核對之前這樣存檔
    也會被拒絕（409 `restore_review_required`，什麼都沒存）；只改密碼（Nextcloud：App 密碼）不受影響。
  - 核對卡說「還原紀錄讀不到或格式不符」時，所有帳號的重新產生都暫停；會換權杖的換身分存檔（Odoo：網址、資料庫或使用者；
    Nextcloud：網址或使用者）也一樣失敗（503）。面板這時若說存檔結果不明、請重新啟動 add-on，重新啟動沒有用（這次什麼都沒寫，紀錄也還是讀不到）。到「診斷與維護」按「全部撤銷」：
    每個帳號的權杖都撤銷，紀錄也重建（每個帳號都要核對），之後逐帳號核對、重新產生。
  - 先發了緊急關閉版（沒開通的版本）再重新開通時，還原後還沒核對的帳號（含預設帳號）照樣要先核對。緊急關閉期間重新產生過預設帳號的權杖時，
    同「沒開通、但磁碟上有帳號資料時的還原」那一點：核對之前改後端身分的存檔（Odoo：網址、資料庫或使用者；Nextcloud：網址或使用者）
    會被拒絕（409，什麼都沒存）。
  - 隔離區的帳號資料超過 64 筆時，面板只列前 64 筆並說還有幾筆；刪掉上面的之後，其餘的會依序出現。
- **涵蓋範圍**：這個保護只涵蓋「各產品第一個含多帳號還原守門（HM-13）的版本以後做的備份」（Odoo 預計是 0.5.0，以發版時為準）。還原時
  Supervisor 會換回備份當時的映像，看不看得出曾經還原要看那一版：
  - 0.4.13 以前（Headscale 0.4.18 以前）：不建還原標記，之後再升級時看不出曾經還原。
  - 0.4.14（Headscale 0.4.19）起、還沒有守門的版本：還原時建標記、一直留著，之後第一次以含守門的版本啟動時才提示（這種備份沒有帳號資料：
    只提示、不撤銷）。
  - 含守門的版本：還原後那次開機就照本節前面處理。
  **還原更早的備份後，請升到最新版，再按「全部撤銷」**（沒開通的產品只有一把權杖：到「連線與權杖」重新產生），然後逐帳號重新產生、更新用戶端。
- **快照還原看不到**：還原偵測只看得到 HA 備份頁的還原（檔案層級）。虛擬機或磁碟快照的還原（區塊層級）帶回原樣的檔案，兩個還原訊號都看不到，
  守門不會動作，面板也沒有提示。**用快照還原過，請按「全部撤銷」**（沒開通的產品：重新產生權杖），再逐帳號重新產生、更新用戶端。
- **回退後再升級**：回退（還原升級前的備份）跑的是舊版。升級前的備份沒有帳號資料時（第一次開通之後的回退），舊版與再升級後的新版都不撤銷任何權杖，
  備份裡的權杖照用；面板頂多有還原提示（0.4.14 起的舊版留標記或提示，見上面「涵蓋範圍」）。
  **回退後再升級，請在面板按「全部撤銷」**（沒開通的產品：重新產生權杖），再逐帳號重新產生、更新用戶端。
- **版本混搭**（多帳號計畫 §8.4、§10.6 第 6 點；FM-126）：Supervisor 還原會把映像換回備份當時的版本。
  - 還原「不含守門的版本」做的備份：跑的是舊版。0.4.13 以前（Headscale 0.4.18 以前）只修擁有者、不建標記，之後升到新版也看不出曾經還原；
    0.4.14（Headscale 0.4.19）起建標記，留到之後第一次以含守門的版本啟動時提示（沒有帳號資料：只提示、不撤銷）。照上面「涵蓋範圍」：
    升到最新版後按「全部撤銷」（沒開通的產品：重新產生權杖）。
  - 還原時拉不到舊映像（Supervisor 沿用目前的映像）：新版跑在舊資料上，還原訊號照樣觸發、守門照跑，照本節前面處理。
  - 同一個版本的備份還原：守門照跑。
  - 在沒開通的版本（例如緊急關閉版）上還原開通版本做的備份：Supervisor 會把映像換回備份當時的開通版本（就是出事的那一版；GHCR 上舊版號的映像
    一直在）。跑的是那一版：備份裡有帳號資料時，守門撤銷每個帳號（連預設帳號）、出現核對卡；沒有帳號資料時同本節第一點（不撤銷、面板提示）。
    **還原後立刻再更新到緊急關閉版（或之後修好的版本）**。在緊急關閉版上每次開機照休眠處理，這時沒有核對卡，直接重新產生預設帳號的權杖；
    重新開通後再到核對卡核對（上面「沒開通、但磁碟上有帳號資料時的還原」）。拉不到舊映像時（Supervisor 沿用目前的映像），是關閉版直接跑在這份
    資料上：備份裡有帳號資料時，守門在服務前撤銷每個帳號（連預設帳號），之後同上；沒有帳號資料時同本節第一點。
  - 驗收：HM-19b 做「開通前版本的備份還原後再升級」與「開通版本的備份還原到之後的版本（沒有更新的版本就同版本）」各一次，記下兩個訊號各自有沒有觸發
    （`docs/operations/acceptance.md` T-20、T-21）。期望值照上面：還原後 add-on 的版本是備份當時的版本（記下版本號），守門照那一版的規則跑；
    開通前版本是 0.4.14 時標記留到再升級、由新版的守門提示，是含守門的版本時那一版就提示、再升級後只剩面板提示（都不撤銷）；開通版本的備份
    有帳號資料時由那一版的守門撤銷，再更新到之後的版本時沒有新的守門動作（之後的版本沒開通時照休眠處理）。
- **Origin 政策**（開通的產品；HM-27）：還原把密鑰網址的來源清單與模式帶回備份當時的值（例如備份之後才切的 enforce 會回到 report-only），面板與 log
  都沒有另外的提示。**還原後到「連線與權杖」的「瀏覽器來源檢查」卡片看一次**。備份裡的政策檔不能用時，還原後每個帳號的密鑰網址都回 503，到面板存一份新的；
  政策檔變成目錄這類存檔蓋不過去的東西時，只能再還原別份備份。
- **全部撤銷**（開通的產品，「診斷與維護」頁，兩段確認）：一次撤銷所有帳號（含預設帳號）的 MCP 權杖，每個子程式用新的內部權杖重新啟動；
  之後逐帳號重新產生。懷疑權杖外洩時這是第一步；面板打不開（403）時只能停止 add-on。
  - 有帳號沒撤銷成功：面板列出是哪些帳號，它們舊的權杖在 MCP 端點回 503，直到再按一次全部撤銷成功，或重新啟動 add-on（重新啟動時在服務
    之前補完；之後才產生的新權杖也會一起撤銷）。
  - 每個帳號都撤銷了、只是收尾沒完成：重新啟動時會再做一次全部撤銷（同上，新權杖也會撤銷）；要現在完成就再按一次。
  - 連開始都沒有（例如磁碟寫不進去）：這次執行期間所有舊權杖回 503，但重新啟動後恢復有效。先修好磁碟、看 add-on 日誌，再按一次。
- **還原前留底（選做）**：「匯出帳號清單（不含憑證）」產生一份 JSON：每個帳號的名稱、port、後端的非秘密欄位與工具政策，不含任何權杖或
  憑證。還原後拿它和核對卡逐帳號比對（對應 PaaS 還原手冊步驟 1）。

細節：多帳號契約 `docs/multi-profile/contract.md` 第 1.2、1.3、3.1、4.1 節，§8.8 #58、#69、#82、#122、#123；威脅模型
`docs/multi-profile/threat-model.md` 第 3 節。

### 開機守門的 log

守門只在還原、休眠或全部撤銷沒做完時寫 log，一律 WARNING，帳號只寫 id 前 8 碼（多帳號契約第 1.3、7 節；原文在 `restore_lock.py`）。
下表列出守門的每一行。撤銷、隔離或收據封存失敗的那幾行，以及 `profiles` 是目錄卻列不出來時，後面都會接一行 `not finished (…)`：
這次開機什麼都不服務，下次開機重做。

| log 行開頭 | 意思 | 怎麼處理 |
|---|---|---|
| `restore guard: the data was restored from a backup; the MCP token is back to its value …` | 沒有帳號資料的還原：權杖回到備份當時的值，什麼都沒撤銷；面板顯示還原提示 | 備份後權杖可能外洩時，到「連線與權杖」重新產生 |
| `restore guard: the data was restored from a backup; the MCP token of every profile …` | 有帳號資料的還原：每個帳號（連預設帳號）的權杖都撤銷了 | 到預設帳號頁的核對卡逐帳號核對，再重新產生、更新用戶端 |
| `restore guard [profile=…]: token revoked, child token renewed` | 那個帳號撤銷了（每個帳號一行） | 同上 |
| `restore guard [profile=…]: its state cannot be read; its directory was moved to the quarantine …` | 那個帳號的設定讀不到，移到隔離區，不服務 | 只能刪除；若是暫時性錯誤（開檔數、I/O），同一份備份再還原一次會重做 |
| `restore guard [profile=…]: its token could not be revoked (<例外類別>)` | 那個帳號撤銷失敗（其他能撤銷的照樣撤銷） | 查磁碟（滿、唯讀、I/O 錯誤），修好後重新啟動，守門重做 |
| `restore guard [profile=…]: its state cannot be read and its directory could not be moved to the quarantine` | 那個帳號讀不到設定，也搬不進隔離區 | 查磁碟或權限，修好後重新啟動；一直這樣就還原別份備份 |
| `restore guard [profile=…]: its state is held by another writer; …` | 那個帳號的設定被別的程式鎖住，沒撤銷也沒隔離（不會從持有者手上搬走） | 重新啟動 add-on；一直這樣就還原別份備份 |
| `restore guard [profile=…]: its operation receipts could not be archived` | 那個帳號的收據封存不了 | 查磁碟；收據檔是目錄而旁邊已有封存檔（偽造的備份）時還原別份備份 |
| `restore guard: the operation receipts beside the profile index could not be archived` | 帳號索引旁的收據封存不了 | 同上 |
| `restore guard: the operation receipts beside the Origin policy could not be archived` | Origin 政策旁的收據封存不了（政策檔本身不動） | 同上 |
| `restore guard: the profiles directory cannot be listed; nothing in it is served` | `profiles` 不是目錄（檔案、連結）時只有這一行：守門照常做完，裡面的東西都不服務（開通的產品 8081 全部 503）；是目錄卻列不出來時接著 `not finished (the profiles directory cannot be listed)` | 不是目錄：修好或移走 `profiles` 再重新啟動；列不出來：修好磁碟或權限再重新啟動 |
| `restore guard: this version serves no additional profiles; …` | 沒開通、磁碟上有帳號資料（休眠）：額外帳號的權杖撤銷了 | 重新開通後先核對再重新產生 |
| `restore guard: a "revoke all" had not finished …` | 上次的全部撤銷沒做完，這次開機補完了 | 到面板逐帳號重新產生（之前產生的新權杖也撤銷了） |
| `restore guard: not finished (…); nothing is served and no child is started …` | 守門沒做完：add-on 什麼都不服務，下次開機再做 | 括號裡是原因。磁碟滿：清出空間；`profiles` 列不出來：修好磁碟或權限；其他：還原別份備份。然後重新啟動（add-on 會不會自己再起看 HA 介面的 Watchdog 開關，沒確認過） |
| `restore guard: … was not a plain file; it was moved aside to ….quarantine-…`（帳號目錄裡的收據封存是 `restore guard [profile=…]: … was not a plain file; …`） | 備份裡守門自己的名稱被目錄占用（偽造或損壞的備份），移開了，不擋開機 | 移開的項目可以刪 |
| `restore guard: …; starting (no profile data: nothing to revoke), the next start tries again` | 沒有帳號資料：標記刪不掉或還原提示存不下，照常啟動 | 查磁碟（唯讀、滿）；下次開機再試 |
| `restore guard: the restore record cannot be read; …` | 還原紀錄讀不到：每個帳號的重新產生都暫停（503） | 面板「診斷與維護」按「全部撤銷」，紀錄會重建，再逐帳號核對 |
| `restore guard: the panel notice of the restore could not be removed after the token changed; …` | 權杖已換，但還原提示檔刪不掉 | 查磁碟；重新啟動後提示會再出現，到下一次權杖變更為止 |

還原紀錄超過 1 MiB（只有手工拼的偽造備份會這樣）時守門也會停下：還原別份備份。

面板的全部撤銷與刪除隔離目錄（開通的產品；logger `mcp_admin_core.profile_admin`）另有四行：

| log 行開頭 | 意思 | 怎麼處理 |
|---|---|---|
| `multi-profile: "revoke all" stopped on an unexpected error (<例外類別>); …` | 全部撤銷結果不明：每個帳號撤銷前的權杖在 MCP 端點回 503 | 再按一次「全部撤銷」；看上面「全部撤銷」那一點 |
| `multi-profile: the child of profile <id 前 8 碼> did not start again after "revoke all" …` | 那個帳號撤銷了，但子程式沒重新起來（新的內部權杖等重啟） | 面板重新啟動那個帳號的子程式，或重新啟動 add-on |
| `multi-profile: a quarantine directory of profile <id 前 8 碼> could not be removed completely; …` | 隔離目錄沒刪乾淨，還列在清單裡 | 再刪一次；一直刪不掉就查磁碟 |
| `multi-profile: the credentials of a quarantine directory of profile <id 前 8 碼> could not be wiped before its deletion` | 刪除前沒能先撤銷權杖、抹掉憑證；目錄照樣刪 | 刪乾淨了就不用處理；沒刪乾淨時另有上一行 |

## 回退與緊急關閉（多帳號產品開通後）

照多帳號計畫 §7.4（C2-MF-1；FM-125）。先講平台事實：

- Supervisor 的安裝與更新沒有「指定版本」的參數，WOOW 商店也不收較低的版號：**不能「裝回舊版」**（UC-18 已確認）。
- Supervisor 還原會把映像換回備份當時的版本（拉不到舊映像就沿用目前的映像），再整份換掉 `/data`，沒有 hook。
- 這個 repo 的降版一直是「升級前備份＋程式一起還原」；多帳號版本的回退還沒演練過（HM-19b 會做）。

| 路 | 做法 | 結果 | 要多久 |
|---|---|---|---|
| (a) 還原升級前的備份 | HA 備份頁還原這個 add-on 升級前的備份（先另做一份保護備份） | 回到舊映像＋舊資料：升級後建立的帳號、輪替、撤銷全部消失。第一次開通之後退回（升級前的備份沒有帳號資料）時不撤銷任何權杖，預設帳號的權杖＝備份當時的值；之後的版本退回、備份裡已有帳號資料時，舊版的守門照本節前面的規則撤銷 | 分鐘級（使用者操作） |
| (b) 前進式修正版 | 發一個版號更大的新版：把產品移出 `MULTI_PROFILE_PRODUCTS`（關閉版），或退回舊程式 | 額外帳號變休眠：開機在服務前撤銷它們的權杖、資料保留；預設帳號照常；Origin enforce 靜默失效。重新開通後先在核對卡核對才能重發 | 推估一個工作天以上（下面「緊急發版範本」的步驟） |
| (c) 使用者立即止血 | 停止 add-on（全部帳號一起斷）；面板能開時：撤銷單一帳號、刪除帳號，或「全部撤銷」 | 立即生效 | 秒到分鐘 |
| 不受開關管的變更隨別的產品出貨後出事 | revert 那一片＋那個產品再發一版（走 (b)；批准點同下面的範本） | 已安裝的要等新版，期間用 (c) | 同 (b) |
| 只有一個帳號出問題 | 面板撤銷或刪除那個帳號 | 只影響那個帳號 | 立即 |

- (a) 之後再升級：還原發生在舊版。升級前的備份沒有帳號資料，舊版與再升級後的新版都不撤銷（0.4.14 起的舊版留標記或提示，新版只提示），
  備份裡的權杖照用。**請在面板按「全部撤銷」**，再逐帳號重新產生、更新用戶端（上面「回退後再升級」）。
- (b) 的休眠：沒開通的版本每次開機在 listener 之前撤銷每個額外帳號（與孤兒）的權杖、重產 child token；已撤銷的不再動；預設帳號不動。面板只顯示休眠
  帳號的數目，沒有管理動作。
- HM-19b 的回退演練（`docs/operations/acceptance.md` T-20）的期望：回退後預設權杖＝升級前備份當時的值、額外帳號消失、沒有任何撤銷；再升級後額外帳號
  不存在、預設帳號不變；再按全部撤銷，預設帳號也撤銷。

### 緊急發版範本（關閉版）

出事時照這份做，只填產品與版號。關閉版出來之前，每台都可以立即做 (c)。**這份範本還沒經負責人預先核准**：HM-19a（Odoo 首發的升版 PR）照它核對過一次
（2026-11-19，結果在 [0.5.0 發佈紀錄](release-decision-odoo-0.5.0.md)「緊急發版範本」一節；改了第 2 點釘選測試那一項），交負責人核准，之後才算「預先核准」
（多帳號計畫 §7.4）。

1. 從 `claude-delivery` 開 `release/<名稱>` 分支（`release.yaml` 只在 `release/*` 分支觸發；新版號要比目前發行的大，商店不收較低版號）。
2. 改的檔：
   - `packages/mcp-admin-core/mcp_admin_core/features.py`：把產品移出 `MULTI_PROFILE_PRODUCTS`；或 revert 出事的那一片。
   - 釘住開通集合的測試照新的集合改：`tests/test_upgrade_zero_rewrite.py` 的 `SWITCHED_ON`（`test_a_product_is_switched_on_only_by_its_release`
     斷言 `MULTI_PROFILE_PRODUCTS` 正好等於它；Odoo 0.5.0 起是 `{'odoo'}`），和 `features.py` 一起把產品拿掉。HM-19a 為開通改過的其他測試都改成自己
     指定開關模式（`tests/switch_modes.py` 的 `switched_off`，或子程序前置碼明說開關），開關關了照樣測同一件事，關閉版不用改回；逐檔清單在
     `docs/provenance/ha-multiprofile-HM-19a-20261119.md` 第 4 節。
   - 版號資料 7 處照 [release](release.md)「升版時要改的版號資料」（`docs/provenance/runtime-patches.json` 的 `features.py`、`__init__.py` 摘要一起更新）。
   - `addons/<產品>/CHANGELOG.md`：寫明關掉多帳號；額外帳號變休眠、權杖已撤銷、資料保留；預設帳號照常；密鑰網址的 Origin enforce 失效（任何來源都放行）；
     重新開通後要先核對才能重發。根目錄 `CHANGELOG.md` 照前例一段。
   - 升版比對要求時的 `upgrade-notes.yaml`（`AGENTS.md` 第 3 點）。
   - `docs/operations/release-decision-<產品>-<版號>.md`（readiness 只認產品自己的紀錄）。
3. PR 標題照規則（「⛔ 勿代 merge｜待覆核 — …」）。本機跑 `scripts/secret_precheck.py`、`scripts/ledger_precheck.py`、`packaging/validate.py`；PR 的 `checks` 綠。
4. 批准點，每一步負責人批准（[release](release.md)「發版步驟」）：觸發 `release.yaml`（gate → candidate：建置、容器驗收、供應鏈閘門、J1900 指令集檢查）→
   負責人在 GitHub 批准 publish（推 GHCR，這個版號就燒掉了）→ HAOS 驗收（至少：預設帳號照常、額外帳號的舊權杖被拒、面板沒有帳號選單；備份與更新逐步批准）→
   證據 commit → 負責人合併（＝上架商店）→ Release 與商店同步 → 使用者更新。
5. 時間：candidate 約 35～40 分鐘加建置與檢查，PR `checks` 約 30～40 分鐘；之後看批准、HAOS 驗收與商店同步（通知到了幾分鐘，沒通知時看商店的排程）。
   合起來推估一個工作天以上；這段期間每台只能做 (c)。

## 執行與停止點

- 只用已批准且已匿名 pull 驗證的固定版本做 HA 手動更新。
- 檢查新 Add-on 啟動／三維健康、state 未丟失、endpoint／policy／token 持久化；
  做 initialize→initialized→list→已審無副作用 call 與拒絕測試。
- backend unreachable 不重啟 backend，也不將 readiness 接 watchdog。遇 state_error、
  unknown schema、source guard drift、角色 verifier 缺失、資料 owner 不符立即停止，
  保留原狀以便回復，不重新 bootstrap 或開寬權限硬闖。
- 六支的管理面板（`homeassistant_api`：n8n 自 0.1.0、其他自 0.1.1 起）已在測試 HA 以 owner 實測 Ingress、後端設定與 token；
  一般使用者一律 403（0.1.1–0.1.5 每版實測）。0.1.1→0.1.5 升版已在測試 HA 對每支實測；還原只在 n8n 實測過，
  其他產品的還原仍須逐支驗證，也不能擴及既有 HA 變更。

## Migration 與 rollback

完整有效 n8n v1／product v2 在 writer lock 下驗證後 atomic/fsync 遷移到 **v3**。
保留 token、child token、backend、endpoint、writes_enabled、disabled，新增
`enabled_write_tools=[]`。舊 global true 只保留原 n8n delete/OpenDesign delete 授權，
不會授權新增 writers。其他產品不能匯入 n8n state；unknown/duplicate grants、未知未來／
損毀／不完整 state 拒絕且不重寫。UI 保存取代全部 exact grants，disabled 永遠優先。

**0.2.1（完整版，2026-10-15；0.2.0 未上架）**：v3（以及經 v3 的 v1／v2）再遷移一次到 **v4**：每個寫入 grant 全開、`writes_enabled=true`，
token、child token、backend、endpoint 保留，0.1.x 的 disabled 清空（升級後所有工具全開）；v4 之後照存檔載入，管理員取消的寫入或停用的工具不會被再次打開。
0.1.x executable **不接受 v4**：從 0.2.1 退回 0.1.x 必須還原升級前的備份。**升級前請先備份**，並知悉升級後寫入全開。

**0.2.2**：state 格式不變（仍是 v4，不遷移）；0.2.1 與 0.2.2 可互相升降版而不需還原備份。

**0.3.4**（接在 0.3.3 之後；0.3.2 不使用）：相依更新（MCP Python SDK 1.30.0、FastMCP 3.4.11、n8n-mcp 2.96.2、Node 22.23.4）、Hermes 恢復拒絕 loopback MCP server 網址、n8n 健康檢查不再查詢 npm registry；state 格式不變（仍是 v4，不遷移、不進升級確認頁），0.3.3（或更早的 schema 4 版本）→ 0.3.4 不需確認。退回 0.3.3 也不需還原備份，但會失去本版的相依與安全修正（未實測降版）。

**0.4.0**（接在 0.3.4 之後）：MCP SDK 2 遷移（MCP Python SDK 2.3.0、FastMCP 4.1.3、odoo-mcp 1.3.0、Node 26.12.1）；state 格式不變（仍是 v4，不遷移、不進升級確認頁），選項、port、映像名稱、架構、工具名稱都不變，0.3.4（或更早的 schema 4 版本）→ 0.4.0 不需確認。唯一宣告的破壞性變更：Odoo 13 個工具的 `structuredContent` 不再包一層 `result`（文字內容不變），讀 `structuredContent.result` 的 client 要改讀頂層欄位，見 [upgrade-notes.yaml](../../upgrade-notes.yaml)。退回 0.3.4 不需還原備份（同為 v4），但會回到 SDK 1.x 與 0.3.4 的 Odoo 輸出形狀（未實測降版）。

**0.4.1 候選**（接在 0.4.0 之後）：管理畫面增加 n8n `exposeToMcp` 條件寫入與現有 updater 相依權限的說明；state 仍為 v4，權限與工具執行規則、依賴、選項、port 及映像名稱不變。0.4.0 → 0.4.1 不需資料遷移；退回 0.4.0 只會失去新畫面說明（降版未實測）。映像尚未發佈，請先核對[0.4.1 發佈決策](release-decision-0.4.1.md)與正式 Store 版本。

**0.4.3**：schema 1/2/3 第一次啟動一次性全開並加標記、保存 `owner-defaults-20261025-recovery.json`（見本頁開頭）；
schema 4 不動。新增的標記欄位只出現在被遷移的設定，0.4.2 不接受它：被遷移的安裝要退回 0.4.2 必須還原更新前的備份。

舊 v1/v2 executable **不接受 v3**：退 image 不等於退資料。必須使用升級前的
受保護相容 v1/v2 backup；不能手改 schema_version、刪 writer marker 或刪 state 讓系統
重建 token。若無相容 backup，先停用新 Add-on 並尋求核准恢復，不嘗試 lossy downgrade。

回復步驟：
1. 停止本次新 Add-on，記錄不含秘密的失敗摘要；不要移除備份或變更 backend。
2. 確認已核准回復 digest 和匹配的資料版本，保留失敗狀態的受控副本供調查。
3. 按 HA 核准還原流程，只恢復該 Add-on 的映像與完整資料；驗證 owner／權限。
4. 啟動該 Add-on，重新做協議/read／拒絕／policy／健康驗證。確認其他服務未變。
5. 還原可能使備份中的舊 token 復活、撤銷或寫入政策回到舊值；於正常管理功能
   可用時輪替 token，更新 clients。若管理仍封鎖，維持停用／隔離，不手改資料解鎖。
6. 記錄回復結果與實際中斷時間；未驗證成功不可宣告已復原。

移除也僅限新 Add-on；確認 HA 移除資料的行為與備份保管後再做，不刪既有服務。

## Odoo Manage 下架（0.1.5 起）

負責人 2026-10-06 決定 Odoo Manage MCP 整體下架封存，之後只用 Woow Odoo MCP Server（0.1.7 以前名為 WOOW Odoo MCP）。0.1.5 起商店不再提供，也不再建置或發佈；
0.1.4 是最後一版。已安裝的 Odoo Manage 仍以 0.1.4 執行，但不會再有更新或安全修正。它的設定保有 Odoo API key，並有
`homeassistant_api` 權限（廣泛的 Core 存取能力），建議：

1. 先改用 Woow Odoo MCP Server。它是不同的 MCP server（上游 odoo-mcp；工具、設定與權限模型都不同），要另外設定後端、建立 MCP
   endpoint 與 token，再更新 client。
2. 要保留設定就先做這支 add-on 的部分備份，再移除（`ha apps uninstall <slug>`）；移除會刪掉它的 `/data`。
3. 視需要在 Odoo 撤銷它用過的 API key；若其他服務共用同一把 key，先確認再撤銷。

已發佈的 `ghcr.io/woowtech/amd64-mcp-odoo-manage:0.1.0`–`0.1.4` 映像保留公開，舊備份仍可還原；不會再有新 tag。
