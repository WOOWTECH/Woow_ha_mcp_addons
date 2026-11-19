# HA 多帳號 HM-01 追補 provenance：測試工具的子程式 port 不會撞到公開 port（2026-11-19）

## 結論

- **現象**：PR #109（HM-16）第一次 CI 只有一案失敗：`tests/test_unconfigured_connect.py::test_unconfigured_connect_runtime[hermes]`，
  停在 `tests/owned_executable.py:176` 的 `assert self.config['child_port'] not in public_ports`。
- **根因**：`launch()` 用 `free_port()` 取兩個公開 port：bind port 0、關掉、只回號碼。`Executable.__init__` 接著用 `reserve_port()`
  （也是 bind port 0）保留子程式 port。前兩個 socket 已經關了，核心可以把剛關的號碼再發給下一個 bind port 0。Linux 的 bind port 0
  從隨機的奇數 port 起找（預設範圍約一萬四千個候選），每次啟動約七千分之一會撞到兩個公開 port 之一；CI 每輪約 37 次這種啟動。
- **修法**（`tests/owned_executable.py`）：新 `reserve_child_port()`。撞到公開 port 就再保留一次；撞到的那個保留到拿到新的才關。
  核心不會把還綁著的 port 發出去，所以最多撞 `len(public_ports)` 次；還一直撞（只有不理會已綁 port 的替身會這樣）就丟
  `OwnershipError`，不會無限重試。`Executable` 先驗公開 port、再保留；`child_port` 不在公開 port 裡的斷言照留，當守門。
  用 `Executable` 的啟動點都經過這裡，呼叫端不用改。
- **審查後補：公開 port 一次取**（第 8 節，審查 S-1）：兩次 `free_port()` 的第二次就是在第一個關掉後 bind port 0，也可能拿到同一號，
  `Executable` 的 `len(set(public_ports)) == len(public_ports)` 會擋下（審查量到每 10 萬次啟動 8 次，已修的子程式撞號是 19 次）。
  新 `draw_public_ports(n)`：n 個保留全部綁著時取號、再一起關；核心不會發出還綁著的 port，所以不會重號。8 個取號處
  （10 個測試函式裡取兩個公開 port 的 9 個；`test_owned_executable` 的 uid10001 案只有一個公開 port，不會重號）與
  `integration_local_runtime`（control port 也綁著到子程式 port 保留完）改用它，5 份 `free_port()` 拿掉。
- **同一種型態的其他 5 處**（第 3 節）：「先取一個號碼、socket 關掉，之後同一個行程另一個 bind port 0 可能拿到同一號」。3 處連不上的
  後端 port 改成整個測試期間一直綁著、不 listen；2 處改成在會 bind port 0 的東西綁好之後才取號。
- **測試**：`tests/test_owned_executable.py` 新 3 案，先紅後綠；紅的兩案就停在 CI 那一行。6 個突變全抓到（第 4 節）。
  審查後再加 1 案（核心一律發最小的空 port，剛關的號碼馬上發給下一個 bind），3 個突變全抓到。
- **本機檢查**（第 5 節）：pytest 15 檔 656 案：634 過、22 失敗、0 skip；22 案都和本片無關（1 案要 root、21 案要本機沒裝的
  Playwright Chromium，在沒改的 `tests/` 上一樣失敗）。審查後重跑 13 檔 623 案：622 過、1 失敗（同一個要 root 的案）、0 skip。
  packaging unittest、`validate.py`、兩個預檢見第 5 節。
- **沒處理的**（第 7 節）：審查前列的「先取號再取號」已在本片處理（S-1）。其他 5 處仍沒有決定性的重現，靠核心的保證。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-01 追補（HM-01 的測試工具 `tests/owned_executable.py`；HM-16 修過它的開通路徑） |
| 性質 | 只改 `tests/` 與本筆記；不改執行期、`addons/`、版號、`tests/conftest.py`；`MULTI_PROFILE_PRODUCTS` 維持空的 |
| 分支 | `fix/ha-multiprofile-port-collision-20261119`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `c90b214`（#109 HM-16 的合併） |
| 失敗的 CI | PR #109 第一次 `checks`：`test_unconfigured_connect_runtime[hermes]`，`tests/owned_executable.py:176` |

## 2. 改了什麼

| 檔 | 內容 |
|---|---|
| `tests/owned_executable.py` | 新 `reserve_child_port()`；`Executable` 先驗公開 port 再保留；守門斷言照留 |
| `tests/test_owned_executable.py` | 新 3 案（第 4 節） |
| `tests/test_tool_error_text.py` | 後端 port 用 `reserve_port()` 綁住整個測試、不 listen；不再 import `free_port` |
| `tests/test_odoo_probe_auth_rejected.py` | `dead_url()` 改成 context manager，用的期間一直綁著；兩個呼叫點跟著改 |
| `tests/test_unconfigured_connect.py` | `test_unreachable_backend_runtime` 改用新的 `unreachable` fixture（綁著、不 listen 的後端 port），不再「假 API 綁了又放」；拿掉不再用到的 `fake_api` import |
| `tests/test_ha_role.py` | `test_real_n8n_executable_tcp_uses_production_factory` 的兩個公開 port 改在假 Supervisor 的 websocket 伺服器綁好之後才取 |
| `tests/integration_local_runtime.py` | control port 改在子程式 port 保留之後才取（不在 pytest 收集範圍，root 明確執行）。審查後：control port 先綁著，公開 port 用 `draw_public_ports(2)`、子程式 port 保留完才放，四個號碼都不同；拿掉 `free_port()` |
| 審查後：`tests/owned_executable.py` | 新 `draw_public_ports(n)`；`reserve_child_port()` 的說明改指它 |
| 審查後：`tests/test_owned_executable.py` | 新 1 案（第 4 節）；開通產品那案改用 `draw_public_ports(2)` |
| 審查後：`tests/test_real_products.py`、`test_real_n8n.py`、`test_runtime_failure.py`、`test_upgrade_hooks.py` | 公開 port 改用 `draw_public_ports(2)`；拿掉各自的 `free_port()` 與不再用到的 `reserve_port` import |
| 審查後：`tests/test_unconfigured_connect.py`、`test_ha_role.py` | `launch()` 與 n8n 那案的公開 port 改用 `draw_public_ports(2)`；不再從別的測試檔 import `free_port` |
| 本筆記 | — |

連線被拒的行為不變：綁著但沒 listen 的 port 和沒人綁的 port 一樣，連線會被核心拒絕（`test_hermes_dashboard_error_guidance.py` 本來就這樣做）。

## 3. 同一種型態的其他地方

查法：找出每個「從關掉的 socket 拿號碼」的地方（`free_port()` 的 5 份 helper、`dead_url()`、綁了又放的假伺服器），再看同一個測試在那個
號碼真的被使用之前，有沒有別的 bind port 0（`reserve_port()`、`Endpoint()`、`Executable()`、假伺服器）。

| 地方 | 先取的號碼 | 之後的 bind port 0 | 撞號會怎樣 | 改法 |
|---|---|---|---|---|
| 先取公開 port 再建 `Executable` 的 10 個測試函式（`test_unconfigured_connect` 2、`test_real_products` 2、`test_owned_executable` 2、`test_real_n8n`、`test_runtime_failure`、`test_upgrade_hooks`、`test_ha_role` 各 1；CI 每輪約 37 次啟動） | 公開 port | `Executable` 保留子程式 port | 本次 CI 失敗 | `reserve_child_port()`，集中修 |
| 同上 10 個測試函式的兩次 `free_port()`（審查 S-1） | 第一個公開 port | 第二次 `free_port()` | 兩個公開 port 相同，`Executable` 的 `len(set(...))` 斷言失敗 | 審查後：`draw_public_ports(2)`，兩個保留都綁著時取號 |
| `test_tool_error_text` | 後端 port | `Endpoint` 保留子程式 port | 子程式 listen 在「後端」port，後端呼叫打到子程式自己 | 後端 port 一直綁著 |
| `test_odoo_probe_auth_rejected`（`dead_url`） | 後端 port | `Endpoint` | 同上 | 同上 |
| `test_unconfigured_connect` 的 `test_unreachable_backend_runtime` | 後端 port（假 API 綁了又放） | `launch()` 的公開 port 與子程式 port | 閘道或子程式 listen 在「後端」port | 同上 |
| `test_ha_role` 的 `test_real_n8n_executable_tcp_uses_production_factory` | 兩個公開 port | 假 Supervisor 的 websocket 伺服器 | 執行期綁不到自己的 port | 伺服器綁好後才取號 |
| `integration_local_runtime` | control port | `Executable` 保留子程式 port | 子程式和 control 伺服器搶同一個 port | 子程式 port 保留之後才取號。審查後：control port 先綁著，公開 port 一次取、子程式 port 保留完才放（四個號碼都不同） |

查過、不用改：先起假伺服器（一直 listen）才取號的（`test_real_products`、`test_real_n8n` 的假後端、`test_backend_loopback`、
`test_odoo_multi_profile`）；`RealChild` 自己一直綁著；`test_hermes_dashboard_error_guidance` 本來就綁著不 listen；`test_upgrade_hooks`
的 `gone` 伺服器關掉後立刻用，中間沒有 bind port 0。

## 4. 先紅後綠

- **紅**（基準 `c90b214` 的 `owned_executable.py`）：新 3 案全紅。兩案在 `tests/owned_executable.py:176` 的 `AssertionError`（就是 CI 那一行）；
  一案是 `reserve_child_port` 還不存在。
- **綠**：3 案全過。每案本身不到 5 毫秒；第一案的 setup 會等 `tests/conftest.py` 的本機測試鎖（別的 clone 在跑時要等）。
- **突變**（每次只改一處，跑新 3 案；用 `--noconftest` 避開別的 clone 佔住的本機測試鎖，這 3 案不連網、不開子程序）：撞到的先關再
  重新保留、不重試、重試沒有上限（只有第 2 案停不下來，被逾時殺掉；另兩案照過）、撞到的不關、拿掉守門斷言、只比第一個公開 port：
  **6 個全抓到**，其餘 5 個各約 0.2 秒就紅。
- 其他 5 處沒有決定性的重現：改法靠的是核心的保證（還綁著的 port 不會發給別的 bind port 0）。改完照常全過（第 5 節）。
- **審查後的一輪**（S-1；第 8 節）：
  - 新案 `test_the_public_ports_are_distinct_and_never_the_childs`：把 `reserve_port` 換成「一律發最小的空 port」的替身核心，剛關的號碼
    一定發給下一個 bind。案內先證明舊寫法（一次取一個、取完就關）兩次拿到同一號，再驗 `draw_public_ports(2)` 拿到兩個不同的號碼、
    都放掉，`Executable` 的子程式 port 落在第三個號碼，`release()` 後全部放掉。
  - 紅：審查前的 `owned_executable.py`（`69b6d0e`）沒有 `draw_public_ports`，測試檔收集時就錯誤。行為面的紅是下面的 MB1（＝舊寫法）。
  - 綠：4 個 harness 單元案全過（`--noconftest`，0.14 秒）。
  - 突變 3 個（拋棄式複本，`--import-mode=append` 讓複本先被 import，每次只改一處）全抓到：MB1 每個保留取完號就關（舊寫法）、
    MB2 保留都不關、MB3 少保留一個。

## 5. 本機檢查（一般使用者；TMPDIR 用 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 排在共用鎖後面）

| 檢查 | 結果 |
|---|---|
| pytest 15 檔：改到的 5 個測試檔，加上用到 `Executable` 或從改到的檔 import 的 10 檔（`test_real_products`、`test_real_n8n`、`test_runtime_failure`、`test_upgrade_hooks`、`test_odoo_tool_timeout`、`test_owner_defaults`、`test_product_ha_role`、`test_role_lifecycle`、`test_owned_browser_ipc`、`test_owned_browser_redirect`） | 656 案：634 過、22 失敗、0 skip，313.8 秒。22 案都和本片無關：`test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof` 要 root（既有）；`test_owned_browser_ipc.py` 5 案、`test_owned_browser_redirect.py` 16 案要 Playwright 的 Chromium（`browserType.launch: Executable doesn't exist`），本機沒裝。這兩個瀏覽器檔在沒改的 `tests/` 上一樣是 21 失敗、13 過 |
| packaging unittest（`discover -s packaging -p 'test_*.py'`） | `Ran 366`、`OK (skipped=5)`，26.7 秒（本片沒改 `packaging/`；5 個 `skipUnless(root)`，既有） |
| `packaging/validate.py`（PyYAML venv） | `PASS: 8 strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape` |
| 秘密預檢（`scripts/secret_precheck.py --tools <gitleaks>`） | gitleaks 8.28.0（釘選、驗過）；`c90b214..HEAD`：OK，0 命中 |
| 帳本預檢（`scripts/ledger_precheck.py`） | 三本帳本 0 drift、0 missing；改到的檔沒有列管的、沒有新的執行期檔：OK |
| 審查後：pytest 13 檔（審查後改到的 9 個測試檔與 `test_tool_error_text`、`test_odoo_probe_auth_rejected`、`test_odoo_tool_timeout`、`test_owner_defaults`、`test_product_ha_role`、`test_role_lifecycle`；兩個瀏覽器檔本機沒有 Chromium，沒跑） | 623 案：622 過、1 失敗、0 skip，286.2 秒（排在共用鎖後面）。失敗的是要 root 的 `test_uid10001_nondumpable_self_and_own_child_proof`（`assert os.getuid() == 0`，既有）。和審查前的 15 檔相比：少了兩個瀏覽器檔的 34 案，多了新的 1 案 |
| 審查後：整個 `tests/` 收集 | 6638 案，沒有 import 錯誤（5 份 `free_port()` 拿掉後，沒有別的檔還在 import 它） |
| 審查後：packaging unittest、`validate.py` | `Ran 366`、`OK (skipped=5)`，26.6 秒；PASS |
| 審查後：秘密預檢、帳本預檢 | `c90b214..fd24545`（4 個 commit）：OK，0 命中；帳本預檢 OK（改到的 12 個檔沒有列管的）。本筆記的 commit 在 push 前再掃一次 |

`tests/test_single_profile_golden*.py`、`tests/test_upgrade_zero_rewrite.py` 沒跑：本片沒改執行期，它們也沒有用到改過的工具。

## 6. 只在 CI 跑的、`checks` 秒數

- 要 root 的 `test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof` 只在 CI 跑；它也是「先取號再 `Executable`」，
  改完一樣經過 `reserve_child_port()`。
- 瀏覽器測試 21 案只在 CI 跑（CI 的 `unit.sh` 先裝 Chromium）；本片沒改它們用到的 `self_listener`。
- `tests/integration_local_runtime.py` 不在 pytest 收集範圍，本片沒跑（要本機 root 明確執行）。審查後又改了它的取號（第 2 節），
  一樣沒跑；本機只確認整個 `tests/` 收集得到、沒有 import 錯誤（6638 案）。
- `checks` 秒數：開 PR 後補。本片只多 4 個各不到 5 毫秒的案。

## 7. 沒處理的

1. **「先取號再取號」（審查後已處理）**：S-1，第 8 節。原本的記錄：同一個測試連續兩次 `free_port()` 也可能拿到同一號
   （`tests/multi_profile_runtime.py` 的註解量過：連續三次 bind port 0，兩萬次裡 5 次撞號），`Executable` 的
   `len(set(public_ports)) == len(public_ports)` 會擋下。當初寫「不是本片的型態」不對：機制和本片修的相同（關掉的號碼被下一個
   bind port 0 拿到），只是失敗的斷言不同。
2. 其他 5 處（第 3 節）沒有決定性的重現，改法靠核心的保證（還綁著的 port 不會發給別的 bind port 0）。
3. `multi_profile_runtime.free_port()`（記住最近發過的 256 個號碼）照舊：它的號碼給多帳號 rig 的帳號 port，不經過 `Executable`。

## 8. 審查與處理（2026-11-19）

獨立審查（正確性）：`artifacts/ha-multiprofile-parity-20261114/wave5/review-TOOLS-correctness.md`。判定修正後通過，必修 0 項；
本片的建議是 S-1（S-2～S-5 屬 P9 清單產生器那片），另有備註 N-4。照做，沒有不採用的。

| id | 審查意見 | 處理 |
|---|---|---|
| S-1 | 「先取號再取號」還在，和本片同一個機制；本機每 10 萬次啟動 8 次（已修的是 19 次），CI 每輪約 0.3%；建議同一個 PR 修 | 採建議的第一種：`owned_executable.py` 新 `draw_public_ports(n)`（全部綁著時取號、再一起關），8 個取號處與 `integration_local_runtime` 改用它，5 份 `free_port()` 拿掉；新的決定性測試；第 7 節改寫（第 2、3、4 節） |
| N-4 | 新測試沒用 `log_scan`：純 harness 單元測試、沒有 log，不適用 | 同意；審查後的新案也一樣（不起執行期、沒有 log） |

- 選第一種、不選「記住最近發過的號碼」：和 `reserve_child_port()` 靠同一個核心保證，沒有模組狀態；取號處都在同一個 helper，
  呼叫端一行。
- 負責人原本要決定的「先取號再取號要不要另開一片」：審查建議同一個 PR 修，已照做，不用再決定。
- 審查後的 commit：`fd24545`（helper、取號處、新案）與本筆記的 commit。檢查結果見第 5 節「審查後」各列。
- 和同時進行的線：HM-21～HM-26 的新測試用 `multi_profile_runtime.free_port()`，沒有人 import 這次拿掉的 5 份 `free_port()`
  （本機各 clone 查過）。HM-25 也改 `test_ha_role.py`、`test_runtime_failure.py`，改的行和本片不同，中間隔著沒改的行。
