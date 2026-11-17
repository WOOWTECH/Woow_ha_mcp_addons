# HA 多帳號文件同步 provenance：deviation-trace、PaaS 測試對照重產與 HM-00 對照檢查（2026-11-17）

## 結論

- 範圍：HM-18 開工前的文件同步，**只改 `docs/`**。用 repo 外的 HM-00 產生器重產 `docs/multi-profile/deviation-trace.md`、
  `docs/multi-profile/paas-test-mapping.md`（沒有手改表格），涵蓋契約第 9 節主線上的全部列（到 #117）與 PaaS `48f394d`。
- HM-00 對照腳本 `check_hm00.py`（沒改）：基準 `f239157` 上 C1、C3、C6、C7 不過，修後 **C1～C9 全部通過**（第 3 節）。
  - C3：FEATURE-MATRIX 新的 FM-154～156 沒對到 → 產生器加三列。
  - C6：PaaS `origin/main` 到 `48f394d`，23 個新測試檔（217 案）不在表裡 → 規格補歸屬、用 `--main 48f394d` 重產。
  - C7：契約第 2.4 節反引號裡的兩個測試函式名稱結尾是 `_full`，被當成錯誤代碼 → 改成 `tests/…::…` 的寫法（內容不變）。
  - C1：基準上還沒有變更（0 個檔），有了本 PR 的 commit 就過。
- 改了 repo 外的 `gen_trace.py`、`gen_paas_mapping.py`、`paas_mapping_spec.py`（第 5 節逐項）；改前備份、`SHA256SUMS` 已更新。
  改之前先確認：原產生器加原輸入重產＝`f239157` 的兩個檔逐位元相同（第 4.3 節）。
- 未合併的 PR（#108 HM-13b、#112 HM-13c、#116 HM-27）的列不在主線上，沒有寫進來。
- 沒有測試讀這些文件，沒跑 pytest（第 7 節）。秘密預檢 0 命中、帳本預檢 OK、雙向控制字元 0。
- 第二輪（主對話授權，第 11 節）：照第 9 節列的字改了 repo 外的 FEATURE-MATRIX 與 PLAN，`deviation-trace.md` 照新的原文重產；
  `negative_tests.py` 三種過時的改壞換了對象，22 種改壞都如期失敗；C1～C9 仍全部通過。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 分支 | `docs/ha-multiprofile-docs-sync-20261117`（一般 clone `ha-mp-docsync-20261117`） |
| HA 基準 | `claude-delivery` `f239157`（#115 HM-33 的合併；#89～#107、#110、#111、#113～#115 都已合併） |
| 契約第 9 節 | 117 列（主線最後一列是 HM-12 面板的 #117） |
| PaaS | pin `69ac425`；本表的基準 `48f394d`（`origin/main`，#156 的合併）；#149 head `3d33bc5` |
| 讀 PaaS 的方式 | 唯讀 worktree `paas-mp-research-20261114`（第 4.2 節） |
| 輸入（repo 外，`artifacts/ha-multiprofile-parity-20261114/`） | 現在：`FEATURE-MATRIX-zh-TW.md` `fbc2703c9d64c63c`、`gaps/G6-delivery.md` `b8285253e2738b60`、`PLAN-zh-TW.md` `5973373868a63749`（C7、C8 讀）。第一輪是 FEATURE-MATRIX `662b21497698135b`、PLAN `48810d9be8565bf3`（第 11 節） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `docs/multi-profile/deviation-trace.md` | 產生器重產（第 4.4 節）；第二輪照 FEATURE-MATRIX 的新原文再重產（第 11 節） |
| `docs/multi-profile/paas-test-mapping.md` | 產生器重產（第 4.5 節） |
| `docs/multi-profile/contract.md` | 第 2.4 節兩個測試名稱改寫（C7）；第 9 節說明段拿掉「`deviation-trace.md` 沒有這幾列」，補一句第 87 列以後怎麼對到；第 10 節加一列。差異表的列、錯誤代碼沒動 |
| `docs/multi-profile/README.md` | 對照表的規模、PaaS 基準與重產指令的位置 |
| `docs/provenance/multi-profile-parity-baseline.md` | 第 5 節加一筆檢查紀錄（`48f394d`） |
| `docs/provenance/ha-multiprofile-docs-sync-20261117.md` | 本筆記 |

沒改：程式、測試、`addons/`、版號、`.github/`、帳本（`runtime-patches.json` 等）、tool-surface、`decisions.md`、`acceptance-matrix.md`、
`threat-model.md`、`ledger-tracking.md`。

## 3. C1～C9 修前修後

指令（`<A>`＝artifacts 目錄；`--paas` 用唯讀 worktree）：

```sh
python3 -I -B <A>/wave0/hm00-check/check_hm00.py --repo <HA clone> --artifacts <A> \
  --paas /data/pi-agent/home/woow-sec-sweep/.worktrees/paas-mp-research-20261114 --base origin/claude-delivery --source-base bb48449
```

| 檢查 | 修前（`f239157`） | 原因 | 修後 | 怎麼修 |
|---|---|---|---|---|
| C1 | FAIL | 0 個檔（基準上還沒有變更） | PASS | 本 PR 的 commit，都在 `docs/` |
| C2 | PASS（117 列） | — | PASS | — |
| C3 | FAIL | 來源 112 列、對照 109 列：FM-154、FM-155、FM-156 沒對到 | PASS（112／112） | `gen_trace.py` 加三列後重產 |
| C4 | PASS | — | PASS | — |
| C5 | PASS（登記 64 個測試檔） | — | PASS | — |
| C6 | FAIL | `48f394d` 比表多 23 檔 217 案（D 組） | PASS（79 檔 823 案） | 規格補歸屬，`--main 48f394d` 重產 |
| C7 | FAIL | 「文中提到、表裡沒有的錯誤代碼」：`test_a_newly_connected_clients_initialized_reaches_the_child_with_the_queue_and_admission_full`、`test_the_reserve_is_reached_even_once_the_profiles_admission_is_full`（HM-31 寫的測試名稱） | PASS | 契約改成 `tests/test_carries_no_request.py::…`（同一節別處的寫法） |
| C8 | PASS | — | PASS | — |
| C9 | PASS（44 列） | — | PASS | — |

修後（head `18ac3fd`，工作樹乾淨；本筆記的 commit 之後重跑的結果寫在 PR 說明）：

```text
PASS C1 diff 只在 docs/: 5 個檔；docs/ 以外：無；未提交：0 個
PASS C2 刻意差異表: 117 列（1～117）；欄位或類型有問題的列：無；PaaS 欄和 HA 欄一樣的列：無
PASS C3 FEATURE-MATRIX「HA 平台差異」欄: 來源 112 列、對照 112 列；對到差異表 101 列、對到測試 46 列；問題：無
PASS C4 G6 §5「HA 期望值與差異」欄: 來源 29 列、對照 29 列；對到差異表 25 列、對到測試 27 列；問題：無
PASS C5 驗收矩陣與測試登記表: 29 個情境、登記 64 個測試檔；問題：無
PASS C6 PaaS 測試逐案對照: pin 69ac425、main 48f394d；79 檔 823 案；pin 之後併進 D 組 282 案；#149 已合併；問題：無
PASS C7 錯誤代碼逐欄標註: 管理 API 31 個代碼、MCP 12 種回應；計畫 §5.3 第 9 點 19 個全在；bb48449 原始碼 17 個代碼與 error 字串（16 個在表裡比對）；排除清單列狀態值 16 個；問題：無
PASS C8 決策紀錄: 46 題；已定 34 題（§13.1 採用 16、§13.2／§13.3 18，其中依 DQ-40 (a) 7）；待定 12 題（§13.2 2、§13.3 10）；問題：無
PASS C9「—」列的人工結論: 來源 44 列、結論 44 列（照 PaaS 19、只對到差異表 23、流程或文件 2）；問題：無
結果：全部通過
```

C7 也可以改腳本（反引號裡 `test_` 開頭的不算錯誤代碼），但照交辦只改文件；改成帶路徑的寫法也比較好找。

## 4. 重產

### 4.1 指令與輸入版本

```sh
python3 -I -B <A>/wave0/hm00-check/gen_trace.py <A> <HA clone>/docs/multi-profile/deviation-trace.md
python3 -I -B <A>/wave0/hm00-check/gen_paas_mapping.py <PaaS> <HA clone>/docs/multi-profile/paas-test-mapping.md --main 48f394d
```

- `gen_trace.py` 2026-11-17 起另讀輸出檔旁邊的 `contract.md` 第 9 節（`--contract` 可指定），只讀列號與「項目」欄。
- 實際是在暫存區的複本跑，不在 artifacts 目錄裡跑會寫檔的東西。腳本、規格與輸入的 SHA-256 以 `wave0/hm00-check/SHA256SUMS` 為準：

| 檔 | 改之前（前 16 碼） | 現在（前 16 碼） |
|---|---|---|
| `gen_trace.py` | `8da1bf8376d29390` | `5eb30044d99e5136` |
| `gen_paas_mapping.py` | `4a1c152a0de63441` | `5bfd39c12c631302` |
| `paas_mapping_spec.py` | `99e7c28e738a3b4c` | `00d68e77259fa3c3` |
| `check_hm00.py`、`paas_cases.py`、`sources.py` | 沒改 | `dffee441211c5ee4`、`67caa4c613933f1a`、`a9241101ddbee7f7` |
| `negative_tests.py`（第二輪） | `e2932317465fb8e4` | `8c2f266ce80fcc6b` |
| 產出 `deviation-trace.md` | `4005c94d362994bf`（`f239157`） | `af7bb2981195b5fc`（第一輪的 `18ac3fd` 是 `97b8a1b4306d494d`） |
| 產出 `paas-test-mapping.md` | `4c17352dda09fc7a`（`f239157`） | `a1527de81543676e` |

### 4.2 PaaS 怎麼讀（為什麼用唯讀 worktree）

- 要到 `48f394d`：`wave0/hm00-check/paas_cases.json` 是 `7d111b1` 的快取，只靠它離線重產到不了 `48f394d`。
- `paas_cases.collect` 用的 git 子命令不只 `log`、`show`、`ls-tree`：`grep -l <rev>`、`diff --name-only <rev> <rev>`、`rev-parse`、
  `merge-base --is-ancestor`。所以照交辦，產生器與對照腳本的 `--paas` 指向唯讀 worktree `paas-mp-research-20261114`，不直接對 PaaS 的
  `.git` 目錄跑。這個 worktree 和 PaaS repo 共用物件與 refs（`origin/main`＝`48f394d`），它自己停在 `443e95a` 不影響結果：腳本只讀指定的
  revision（`69ac425`、`48f394d`、`3d33bc5`），不看工作樹。都設 `GIT_OPTIONAL_LOCKS=0`。沒有 fetch、checkout，worktree 的
  `git status` 乾淨。
- 照實記一件不該做的事：開工時（11:1x）為了確認這個 worktree 能不能寫，在它的根目錄 `touch` 了一個空檔 `.probe_write_test`，
  隨即 `rm` 掉。這違反「不要在 worktree 裡改檔」。之後確認檔已不在，`git --no-optional-locks status` 乾淨，沒有其他寫入。
- 自己查 PaaS 時只對 `.git` 目錄用 `log`、`show`、`ls-tree`（哪個 PR 改了哪個測試檔、各案的內容）。
- 另把 `paas_cases.collect(…, '48f394d')` 的結果存成快取（artifacts `wave4/evidence-docs-sync-20261117/cache/paas_cases-48f394d.json`，
  SHA-256 `59542623726c0d89…`，也記在 `SHA256SUMS`），照 HM-12 面板筆記第 15 節 S-3 的做法離線重產：和用 worktree 重產的結果逐位元相同。
  之後重產可以不碰 PaaS。用同一支程式重收 `7d111b1`，和舊快取只差 D 組三個檔的 `rev` 欄（`origin/main`↔`7d111b1`），表的內容相同。

### 4.3 改產生器之前先確認可重現

- `deviation-trace.md`：原產生器（`8da1bf83…`）＋HM-00 時的 FEATURE-MATRIX（`5a398da9…`，FM-154 加入前的備份）＋G6＝`f239157` 的檔，逐位元相同。
- `paas-test-mapping.md`：原產生器與 HM-12 面板改過的規格（`99e7c28e…`）＋`7d111b1` 的快取（`--main 7d111b1`）＝`f239157` 的檔，逐位元相同。
- 所以兩個檔的差異都來自這次的輸入與產生器變更，不是重產本身。改完後用 artifacts 裡裝好的產生器重產，和 commit 的檔逐位元相同
  （PaaS 用 worktree 與用快取兩種都是）。

### 4.4 `deviation-trace.md` 的變化

- FM-154 → §8.8 #101～#108＋`tests/test_request_budget.py`（HM-31）。平台差異本身是 #103（沒有 Pod 記憶體上限）與 #104（程式常數）。
- FM-155、FM-156 的原文是「無」（不是「—」），C3 照差異文字處理：對到 `tests/test_fresh_backend_connections.py`（HM-32）、
  `tests/test_hermes_cron_description.py`（HM-33），說明欄寫明沒有平台差異。
- 說明欄照 `decisions.md` 與各片筆記更新：FM-12、FM-61、FM-63、FM-66 的 DQ-13、DQ-31 已定（2026-11-15 17:4x）；FM-81 的 UC-21 已由
  HM-12 確認（HM-12 筆記第 10 節交辦的字）；FM-52 補 HM-31 審查 MF-3；FM-59 原本寫「清單讀不到擋整頁照 PaaS」，HM-11 之後不對了，
  改照 #111（不鎖面板）。
- 各片補的第 87～117 列，FEATURE-MATRIX 說到同一件事的就加進「對到」：FM-13 #112、FM-23 #109、FM-34 #92、#95、#97、FM-43 #94、
  FM-44 #93、#100、FM-51 #91、#98、FM-53 #110、FM-59 #111、FM-81 #113、#114、FM-89 #115、FM-134 #87、FM-150 #96、FM-152 #115、#117、
  FM-153 #113、#114、#116、FM-154 #101～#108。
- 文末新增「差異表每一列的來處」：#1～#117 每一列由哪些 FM、T 列對到。三張表合起來對到 110 列；沒有列對到的 7 列寫出處：
  #22、#33（計畫 §8.8 原表）、#83（HM-00 審查 MF-2）、#88（HM-08 審查 S-6）、#89（HM-09 審查 S-6）、#90（HM-20；FM-84 的對齊作法欄）、
  #99（HM-14 審查 S-5）。產生器會擋：沒對到又沒寫出處、或寫了出處卻已對到，都直接失敗。
- C9 不變（44 列；照 PaaS 19、只對到差異表 23、流程或文件 2）。

### 4.5 `paas-test-mapping.md` 的變化

| 項目 | `f239157`（PaaS `7d111b1`） | 現在（PaaS `48f394d`） |
|---|---|---|
| 檔、案 | 56 檔 606 案 | 79 檔 823 案 |
| D 組 | 3 檔 65 案（#149） | 26 檔 282 案 |
| 對到 HA 測試／對到 §8.8／只能標不適用 | 435／279／36 | 606／348／70 |
| 用到的差異表列 | 31 列 | 55 列 |

D 組新增的 23 檔 217 案（「pin 之後的變動」表每個檔寫明 PR）：

| PaaS PR | 檔、案 | 歸屬 |
|---|---|---|
| #155 閘道請求內容位元組預算與 JSON 結構守門 | 核心 5 檔 84 案、9 個產品的 `test_request_structure_guard.py` 47 案 | 照 HM-31 筆記第 5 節逐案：`tests/test_request_budget.py`、`test_request_structure.py`、`test_request_budget_gateway.py`、`test_profile_quotas.py`；HA 不同的地方 §8.8 #6、#29、#45、#101、#103～#107；k8s 不適用（HA 沒有這個產品） |
| #152 Nextcloud 存檔與測試連線過 SSRF、日誌遮罩保留 args 形狀 | 2 檔 31 案 | SSRF：§8.8 #39（HM-20 對照過 #152）＋`tests/test_saved_destinations.py`、`test_backend_loopback.py`；日誌：PaaS Nextcloud 管理 app 自己的模組不適用，HA 的對應是既有的 `tests/test_secret_path.py` |
| #154 Nextcloud 換使用者或網址換 token | 1 檔 22 案 | HM-22 的暫定測試 `tests/test_nextcloud_multi_profile.py`（DQ-05）、HM-12 的 Odoo 同一套規則；不同的地方 §8.8 #39、#59、#86、#113、#114、#116 |
| #153 EMQX 實測小修 | 3 檔 29 案 | 不是多帳號行為，不適用；FEATURE-MATRIX §2.12 交 HM-23 對照 |
| #135、#139 EMQX、LiteLLM 不保留閒置連線 | 2 檔 2 案 | 照 HM-32 筆記第 5 節：`tests/test_fresh_backend_connections.py` |
| #138 Hermes 建停用的排程 | 1 檔 2 案 | 既有的 `tests/test_hermes_cron_paused_contract.py`（PR #85，還沒發版） |

- #151（移除 VK）只刪 VK 的案例與參數（刪了 26 案，不在範圍）；#156 只改 Hermes 的說明，沒有測試。
- 既有的列照各片筆記補第 87～117 列：HM-14 筆記第 4 節（`test_gateway_queue.py` 的通知 #91、#96，`test_proxy_interrupted_cause.py`
  #16、#93、#100，`test_initialize_fence_backpressure.py` #92、#95，`test_proxy_carries_no_request.py` #91，`test_initialize_stop_recovery.py` #94，
  另補 #68）、HM-12 筆記第 5 節（`test_config_store.py` #59、#114，`test_connection_type_parity.py` #113）、HM-11（`profiles.test.js` #110，
  `profile_browser.py` 與 Headscale `profiles.mjs` #109）、HM-09（`test_child_identity_proc.py` 的試綁 #89）、HM-12 面板
  （`connection-secret-clear-browser.py` #117）。
- 第 87～117 列裡，PaaS 案例對不到的 11 列：#87、#88、#90、#97、#98、#99、#102、#108、#111、#112、#115。PaaS 沒有對應的測試案例
  （PaaS 沒有這條路徑、或是 HA 自己的測試，例如 HM-31 筆記第 5.6 節）。
- 「pin 之後的變動」表的「處理」欄原本寫死 #149 的說明，只對 `test_log_redaction.py` 成立；改成每個檔一句（規格的 `POST_PIN_NOTES`，少一個檔產生器就失敗）。

## 5. 改了的 repo 外工具（`artifacts/ha-multiprofile-parity-20261114/wave0/hm00-check/`；原檔在 `wave4/evidence-docs-sync-20261117/tools/*.before-20261117.*.txt`）

1. `gen_trace.py`
   - FM 表加 FM-154、155、156；FM、EMPTY 表的說明欄與「對到」照第 4.4 節更新。
   - 新的 `ORIGIN`（7 列的出處）、`contract_rows()`（讀 `contract.md` 第 9 節）、`referrers()`；`render()` 多一節「差異表每一列的來處」，並檢查列號連續、對到的列都存在、沒對到的列都有出處。
   - 檔頭：日期與重產指令的位置；結論的「FEATURE-MATRIX 153 列」改成照來源計數；新增一句第 87 列以後的列怎麼對到。
   - `main()` 多 `--contract`（預設輸出檔旁邊的 `contract.md`）。
2. `gen_paas_mapping.py`
   - 檔頭、結論、「範圍怎麼來」第 4 點跟著 `--main` 走；結論的「pin 之後」改讀規格的 `POST_PIN_SUMMARY`（依 `--main` 前 7 碼，沒有就失敗）。
   - 「pin 之後的變動」的「處理」欄改讀 `POST_PIN_NOTES`；多一種「刪了案例」的句型；欄位內容照表格跳脫。
   - 「讀法」的不適用補「D 組裡不是多帳號行為的產品修正」；文末「其他相關檔」照 `48f394d` 改寫（`7d111b1` 之後的正式碼變動記在各片筆記）。
3. `paas_mapping_spec.py`
   - D 組 23 檔的規格（第 4.5 節）；新常數 `RB`、`RS`、`RG`、`PQ`、`GUARD_RUNTIME`、`NC_SAVE`、`NC_RUN`、`NC154` 與 `EMQX153()`。
   - 既有 12 個檔的規則補差異列（第 4.5 節）。
   - 新的 `POST_PIN_NOTES`（50 個檔）與 `POST_PIN_SUMMARY`（`48f394d`）。
   - 規格的說明不能寫「#數字」：對照腳本會把 `§8.8` 那一段裡的 `#152` 當成列號（試跑時 C6 因此不過，已改）。
4. `SHA256SUMS`：上面三個檔、FEATURE-MATRIX、PLAN 的新值，加快取一筆；改之前的值寫在檔頭的註解。`sha256sum -c` 29 筆全 OK。

`check_hm00.py` 與 `negative_tests.py` 沒改。

## 6. 對照腳本的負向測試（`negative_tests.py`，只讀）

- 在主線上已有兩種改壞過時，和本 PR 無關：
  - 「對到不存在的差異列」把 FM-01 改成 `#99`，但 HM-14 起第 99 列存在 → 期望失敗卻通過。
  - 「待定沒有負責片」要找的 `| 待定 | HM-10 | HM-10 開工前 |`，DQ-13、DQ-14 已定之後就沒有了 → 腳本停下。
- 拿暫存區的複本改這兩處（`#999`、改用 DQ-42 那列）重跑：每一種改壞都被抓到。另兩種 C8 的改壞失敗原因和預期的字不同（`decisions.md`
  的節與列變過），不是漏抓。
- 第二輪主對話授權修 `negative_tests.py`（第 11 節）：改好之後 22 種改壞都如期失敗，原因也都對。

## 7. 本機檢查（2026-11-17，一般使用者 uid 1000）

- 沒跑 pytest：`tests/`、`packaging/`、`scripts/` 沒有讀 `docs/multi-profile/*` 或這幾份 provenance 筆記的程式（只有註解提到）。
  `docs/provenance/*.md` 會複製進映像，但沒有測試或閘門讀它們。
- 秘密預檢 `.venv/bin/python -I scripts/secret_precheck.py --tools <scratchpad>/hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full`：
  gitleaks 8.28.0（釘版已驗），head `18ac3fd` 的 1 個 commit＋HEAD 整棵樹＋整個歷史，`result: OK, 0 findings`。
- 帳本預檢 `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery`：`result: OK`
  （`runtime-patches.json` 177、`runtime-sources.json` 70、`tool-surface.json` 159，0 漂移、0 缺；改到的 5 個檔都不是列管檔）。
- 雙向控制字元（HM-12 面板筆記的 `bidi_scan.py`）：`origin/claude-delivery..18ac3fd` 改到的檔、加的行、commit 訊息都是 0。
- 兩個預檢的 TMPDIR 用 `bin/ha_env.sh` 給的 `/tmp/ha-mp-88qeOY`，跑完是空的，用完整路徑刪掉。
- 本筆記的 commit 之後再跑一次 C1～C9 與兩個預檢，結果寫在 PR 說明。
- 證據（repo 外）：`artifacts/ha-multiprofile-parity-20261114/wave4/evidence-docs-sync-20261117/`（`logs/`、`tools/`、`cache/`）。

## 8. 只在 CI 跑的、`checks` 秒數

- 只改 `docs/`，`checks` 照常跑全套（root、0 skip）；預期和基準一樣。
- `checks` 秒數：CI 跑完補在 PR 說明。

## 9. repo 外的字（第一輪列給主對話；第二輪經授權已改，第 11 節）

- FEATURE-MATRIX 有幾格「HA 平台差異」的字已經過時（FM-81 的「PaaS 沒做、待決（DQ-05）」「未確認（UC-21）」、FM-61 的「待決（DQ-02、DQ-31）」、
  FM-51 的「#148 尚未合併」），§2.12 開頭把 `cf3d0d5` 寫成「本計畫 pin」；PLAN 的 HM-12 段還寫「面板合併前，別的分支不要用新規格重產」。
  第二輪照逐條的字改了，`deviation-trace.md` 同時重產（不重產的話 C3 會報「原文和來源不同」）。
- FM-155、FM-156 的「HA 平台差異」寫「無」，其他 44 列沒有平台差異的寫「—」。現在照差異文字對到測試，沒改；要統一成「—」，產生器要把這兩列
  從 FM 表移到「—」的表。

## 10. 還沒解決、交給後面的片

- HM-18：契約 #85 的類型還寫「待決（DQ-31）」，DQ-31 已在 2026-11-15 17:4x 定案；類型怎麼改由契約定稿決定（第二輪已記進計畫 §12.3 HM-18 段）。
- HM-22、HM-23：PaaS #152、#154（Nextcloud）與 #153（EMQX）的對照，D 組的歸屬已指到這兩片。
- HM-13b（#108）、HM-13c（#112）、HM-27（#116）合併後：它們的差異列加進契約第 9 節時，`deviation-trace.md` 文末的反查表與 `ORIGIN`
  要一起重產（沒對到的新列要寫出處，不然產生器失敗）。
- PaaS 再前進時：先補規格的 `POST_PIN_SUMMARY` 與 `POST_PIN_NOTES`，再用新的 `--main` 重產；`check_hm00.py` 的 C6 一律比 `origin/main`。

## 11. 第二輪：主對話授權改 repo 外的字（2026-11-17 12:0x）

主對話收到第一輪的結果後，授權照第 9 節列的字直接改 repo 外的 FEATURE-MATRIX、PLAN 與 `negative_tests.py`，在同一個分支補上、只 commit。
這段時間主對話不動 FEATURE-MATRIX 與 PLAN；改之前核對過兩個檔的 SHA-256 和第一輪用的相同。

| 檔（repo 外） | 改了什麼 | 改前備份 |
|---|---|---|
| `FEATURE-MATRIX-zh-TW.md` | 三格「HA 平台差異」欄：FM-81 改成「…Nextcloud 比照：DQ-05 已定（依 DQ-40 (a)），PaaS #154（2026-11-15）也做了；「先提交再停」之間新 token 會不會打到舊子程式：HM-12 改成先停再提交，已由測試確認（UC-21）」；FM-61 改成「…：DQ-02 採 (a)、DQ-31 已定（2026-11-15 17:4x 採用建議）」；FM-51 改成「#148 已合併進 pin（`69ac425`）」。§2.12 開頭改成「來源：PaaS 在 `cf3d0d5`（#151 的合併）之後合併的 PR（本計畫的 pin 是 `69ac425`）」。只換那幾格與那一句，其他位元不變 | 暫存區 `FEATURE-MATRIX-zh-TW.md.before-docsync-20261117`；artifacts `wave4/evidence-docs-sync-20261117/tools/FEATURE-MATRIX-zh-TW.before-20261117.md.txt` |
| `PLAN-zh-TW.md` | §12.3 HM-12 段「…面板合併前，別的分支不要用新規格重產 `paas-test-mapping.md`。」後面加「（面板 #114 已合併；2026-11-17 文件同步已用新規格重產到 PaaS `48f394d`）」；HM-18 段加一條「2026-11-17 加（文件同步交來）：契約第 9 節 #85 的類型還寫「待決（DQ-31）」，DQ-31 已在 2026-11-15 定案，定稿時改成正確的類型。」 | 暫存區 `PLAN-zh-TW.md.before-docsync-20261117`；artifacts 同一個 `tools/` 下的 `PLAN-zh-TW.before-20261117.md.txt` |
| `wave0/hm00-check/negative_tests.py` | 三種改壞換對象，種類與期望的失敗原因不變：FM-01 改指不存在的 `#999`；「待定沒有負責片」改用還在待定的 DQ-42（§13.2）；「§13.3 的題放進第 2 節」把 DQ-04 搬到 DQ-42 後面（DQ-13 已移到第 1 節）。檔頭加一段說明 | 暫存區 `docsync/backup-round2/negative_tests.py.before-docsync-20261117`；artifacts `tools/negative_tests.before-20261117.py.txt` |
| `wave0/hm00-check/SHA256SUMS` | `negative_tests.py`、FEATURE-MATRIX、PLAN 的新值，檔頭的註解寫改之前的值；產生器與規格這一輪沒改，值同第一輪。`sha256sum -c` 29 筆全 OK | 暫存區 `docsync/backup-round2/SHA256SUMS.before-round2-20261117`；artifacts `tools/SHA256SUMS.before-round2-20261117.txt` |

- 重產：產生器沒改，照 FEATURE-MATRIX 的新原文重跑 `gen_trace.py`。`deviation-trace.md` 只有 FM-51、FM-61、FM-81 三列的「原文」變，
  「對到」與說明欄不變（commit `7b15f23`）。`paas-test-mapping.md` 的輸入沒變，不用重產；離線重產照舊和 commit 的檔逐位元相同。
- C1～C9（head `7b15f23`，工作樹乾淨）：全部通過。C3 仍是來源 112 列、對照 112 列、對到差異表 101 列、對到測試 46 列；其餘各項的數字和第 3 節相同。
- `negative_tests.py`（裝好的版本）：22 種改壞全部如期失敗，失敗原因也對，結束碼 0。
- 本筆記這一輪的 commit 之後，再跑一次 C1～C9、秘密預檢、帳本預檢、雙向控制字元，結果寫在 PR 說明。
