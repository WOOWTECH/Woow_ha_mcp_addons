# HA 多帳號 HM-32 provenance：對齊 PaaS #135、#139，LiteLLM、EMQX 不保留閒置的後端連線（2026-11-17）

## 結論

- **做了什麼**：LiteLLM、EMQX 的 `lifespan.py` 要的 httpx 連線池改成不保留閒置連線，照 PaaS #139（`009dc99`）與 #135（`3c06b98`）：
  LiteLLM `max_keepalive_connections` 20 → 0、拿掉 `keepalive_expiry=30.0`；EMQX 10 → 0。程式旁加英文註解（恢復後舊的閒置連線會讓
  第一個請求等到逾時；每個請求開新連線；不重送不明確的寫入）。不加重送；逾時、`trust_env`、轉址與代理拒絕、DNS 釘選、目的地檢查都沒動。
  不改版號、不碰 `addons/`、`MULTI_PROFILE_PRODUCTS` 維持空的。
- **實作時查到：HA 的實際行為本來就和 PaaS 修正後一樣**（第 3 節）。兩個產品的 client 都經 `backend_policy.async_client` 建立，它先
  `kwargs.pop('limits', None)` 丟掉產品給的 `limits`，傳輸層 `AsyncTransport` 自己的連線池固定 `max_connections=4, max_keepalive_connections=0`
  （`313ab01` 起就是這樣）。`lifespan.py` 寫的「保留 20 條、30 秒」與「保留 10 條」從來沒生效。基準 `7646f0f` 實測：兩個請求、兩條連線、
  兩次解析，每個回應讀完後池裡 0 條。
  - 所以本片**沒有行為改變**：8081、8099 的回應，後端收到的請求與連線都不變。使用者題目裡「HA 的程式有同樣問題」只對程式寫的設定成立，
    對實際行為不成立；選項說明的代價（每次請求多一次建立連線的時間）HA 今天已經在付，本片不會再多。
  - 本片的價值：設定和實際生效的值、PaaS 一致；`backend_policy` 以後若改成採用呼叫端的 `limits`，也不會把閒置連線帶回來；回歸測試把
    「每個請求開新連線、重新解析與檢查、不重送」在兩層都鎖住。
- **測試**（第 5、6 節）：新 `tests/test_fresh_backend_connections.py`，5 個測試 × 2 個產品 × 2 種連線池＝20 案。
  - `child`（子程式實際建的連線池）：基準上就 10 案全過。
  - `asked`（照產品 `lifespan.py` 要的 `limits` 建的連線池）：只有測試時 8 案紅（連線被重用、只解析一次、名稱改指被拒的位址後下一個請求
    照樣送到、恢復後第一個工具呼叫等滿 2 秒逾時），不重送的 2 案過；修正後 20 案全過。
  - 臨時突變：傳輸層改成留 4 條閒置連線，`child` 每個產品紅 4 案；失敗時重送一次，每種連線池紅 2 案；名稱只解析一次（快取），每種紅 2 案。
- **PaaS 測試逐案對照**（第 5 節）：PaaS 改過的 2 案與 1 個 fixture 都改寫成 HA 版，兩個產品都跑；PaaS 拿掉的舊斷言不適用；HA 另加 3 個測試。
- **CHANGELOG**（交發版片；本 PR 不改 `addons/`）：第 12 節各一行英文原文，寫明行為不變。
- **檢查**（第 7 節）：全套 pytest 6,082 案：6,053 過、29 失敗、0 skip（head `2b3ef37`）。29 案都和本片無關：7 案要 root（既有，CI 用 root 跑），22 案是瀏覽器測試（這個 clone 沒有 Playwright 的 Chromium，裝要下載，本片規則不准連網；CI 的 `unit.sh` 先裝再跑）。相關 24 個檔 786 案全過（含新檔 20 案、HM-01 守門 45 案、真子程式的 `test_real_products`）。兩個預檢 OK、`validate.py` PASS、packaging unittest 203 案 OK（5 skip 要 root）、`tool_inventory.py` 0 漂移、雙向控制字元 0 個。
- **其他產品**（第 11 節，交 HM-29）：Odoo、Hermes、OpenDesign、Nextcloud 走同一個 `backend_policy`，實際不留閒置連線。**Headscale** 自己的
  傳輸層留最多 4 條、5 秒（PaaS `7087280` 也一樣），和 PaaS #135 修正前的 EMQX 是同一種情況；n8n 的官方 MCP 端點（undici）留 1 秒。
- **沒處理的**（第 14 節）：獨立審查待主對話安排；Headscale、n8n 要不要比照交 HM-29；兩個產品實際的後端並行上限是 `backend_policy`
  的 4 條（`lifespan.py` 寫的 50、20 也不生效；PaaS LiteLLM 50 條），既有，本片沒動。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 切片 | HM-32（計畫 §12.3，2026-11-17 新增；風險低、工作量 S；FEATURE-MATRIX FM-155） |
| 性質 | 不受開關管（契約第 1.2 節）；`MULTI_PROFILE_PRODUCTS` 維持空的 |
| 分支 | `fix/ha-litellm-emqx-no-keepalive-20261117`（一般 clone，不是 worktree） |
| 基準 | `claude-delivery` `7646f0f`（#110 HM-12 的合併） |
| 決策 | 使用者 2026-11-17 02:3x「現在就補」（`docs/multi-profile/decisions.md` 第 1.1 節；第 10 節） |
| 對齊的 PaaS | `woow-mcp-server` main `7087280`（本機唯讀 repo，沒 fetch、沒 checkout）：#135 `3c06b98`（合併 `0010a82`）、#139 `009dc99`（合併 `71561af`）；#138 `6748353`（合併 `7087280`）HA 已有 |
| 套件（都沒動，`uv.lock` 未改） | httpx 0.28.1、httpcore 1.0.9、anyio 4.15.1、fastmcp 4.1.3、mcp 2.3.0；CPython 3.13.15（本機）／3.13.16（CI） |
| 證據目錄（repo 外） | `artifacts/ha-multiprofile-parity-20261114/wave4/evidence-HM-32/`（腳本在 `tools/`） |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `apps/litellm/vendor/woow_litellm_mcp_server/lifespan.py` | `max_keepalive_connections` 20 → 0，拿掉 `keepalive_expiry=30.0`（同 PaaS #139）；英文註解 |
| `apps/emqx/vendor/emqx_mcp_server/lifespan.py` | `max_keepalive_connections` 10 → 0（PaaS #135 改的是它自己的 `BrokerTransport`；HA 的 EMQX 走 `backend_policy`）；英文註解 |
| `tests/test_fresh_backend_connections.py`（新） | 20 案（第 5、6 節） |
| `tests/test_output_schemas.py` | EMQX 的 `lifespan.py` 在 `output_schemas.json` 的來源清單裡（記的是來源 commit `e142a6e` 的位元組），照 HM-04 的寫法在 `CURRENT_POST_SOURCE_BYTES` 加一筆目前位元組；工具、schema、handler 都沒變。LiteLLM 的 `lifespan.py` 不在那份清單裡 |
| `docs/provenance/runtime-sources.json` | 兩個檔的 `local_sha256` 重算，`modification` 補 HM-32 |
| `docs/tool-surface.json` | `scripts/tool_inventory.py --write` 重產：只有這兩個 `source_digests` 變；`tool-surface.md` 不變 |
| `docs/multi-profile/contract.md` | 第 1.2 節「不受開關管」清單加一項，另加一段（決定、PaaS 的缺口、HA 今天的實際行為、改了什麼、回應不變、為什麼不受開關管、HM-01、測試）；第 10 節一列。第 9 節不加列：保留閒置連線與否和 PaaS 一致 |
| `docs/multi-profile/decisions.md` | 第 1.1 節一列（使用者 2026-11-17 02:3x，含實作時補記）；第 5 節一列；DQ 題數不變 |
| `docs/multi-profile/acceptance-matrix.md` | 測試檔登記表加新檔 |
| 本筆記 | — |

沒改：`apps/runtime/backend_policy.py`（傳輸層、逾時、`trust_env`、轉址與代理拒絕、DNS 釘選、目的地檢查、HM-20 的 loopback 拒絕）、
其他產品、`packages/`、`packaging/`、`addons/`、版號、CHANGELOG、`upgrade-notes.yaml`、`uv.lock`、`docs/provenance/runtime-patches.json`
（這兩個檔記在 `runtime-sources.json`）、`docs/multi-profile/ledger-tracking.md`（沒有新模組、沒有新列管檔）、`docs/provenance/six-runtimes.md`
（本地修改的檔數不變）、`tests/conftest.py`、`paas-test-mapping.md`、`deviation-trace.md`（由 repo 外的產生器重產，不手改；本片的對照在第 5 節）。

## 3. 查到的事：HA 實際的後端連線池

- `apps/runtime/backend_policy.py:583-586`：`async_client(*, base_url, **kwargs)` 先 `kwargs.pop('limits', None)`，再用 `AsyncTransport(base_url)`
  建 `CheckedAsyncClient`。httpx 的 client 給了 `transport` 就不用自己的 `limits`，所以產品給的 `limits` 完全不生效（`sync_client` 在 577-580 同樣）。
- 同檔 523-527：`AsyncTransport` 的連線池是 `httpx.Limits(max_connections=4, max_keepalive_connections=0)`（`SyncTransport` 在 498-502 同樣）。
  httpcore 1.0.9 在連線變閒置時，只要閒置連線超過 `max_keepalive_connections`（0）就關掉、移出池子（`httpcore/_async/connection_pool.py:270-299`）。
  所以每個請求都開新連線，`PinnedAsyncBackend.connect_tcp` 每次都重新檢查主機（`check_host`）、重新解析（`resolve_async` → `checked_answers`）、
  檢查每個答案（`allowed_address`、`connectable`）。
- 基準 `7646f0f` 實測（`baseline-effective-pool-7646f0f.txt`，`tools/probe_pool.py`）：兩個產品各用自己的 `build_client`／`make_client` 連 loopback
  假後端：連線池是 `AsyncTransport` 的（上限 4、閒置 0）；兩個請求、兩個 client port、兩次解析；每個回應讀完後池裡 0 條。
- 歷史：兩個 `lifespan.py` 用 `async_client`、`backend_policy` 丟掉 `limits`、傳輸層閒置 0，都是 `313ab01`（2026-10-03）就有
  （`git log -S`）。HA 的 LiteLLM、EMQX 一直沒有保留過閒置的後端連線。
- 兩個 `lifespan.py` 的 `max_connections`（50、20）也一樣不生效，實際是 4 條（第 14 節）。

## 4. PaaS 變動清單（本機唯讀 PaaS repo；`origin/main`＝`7087280`）

`git log --oneline 69ac425..origin/main -- apps/litellm/woow_litellm_mcp_server/lifespan.py apps/emqx/emqx_mcp_server/http_policy.py apps/litellm/tests/test_recovery_pool.py apps/emqx/tests/test_transport.py apps/emqx/tests/conftest.py`：

```
71561af Merge pull request '… fix: LiteLLM 閘道恢復後第一個工具呼叫不再卡在失效的連線（不保留閒置連線）' (#139) …
009dc99 fix: LiteLLM 不再保留閒置連線，閘道恢復後第一個工具呼叫不會卡在失效的 socket
3c06b98 fix: EMQX broker 連線不再保留閒置 socket，網路恢復後第一個請求不會卡到逾時
574c805 fix: 超長或無法編碼的識別字改回固定錯誤碼 EMQX_DESTINATION_DENIED，不再把 traceback 留在容器 log
4b4fd16 fix: emqx_prometheus_stats 只有這個請求改送 Accept: text/plain，回說明所寫的 Prometheus 文字
```

- `3c06b98`、`009dc99`：本片。`574c805`、`4b4fd16`：EMQX 的另兩件事，屬 HM-23 的對照（FEATURE-MATRIX §2.12：#153 併進 HM-23），不在本片範圍。
- `apps/headscale/headscale_mcp_server/http_policy.py`、`apps/emqx/emqx_mcp_server/lifespan.py`：`69ac425..origin/main` 沒有變動。
- #138（`6748353`，Hermes 建停用的排程時同時送 `paused` 與 `enabled`）：HA `apps/hermes/vendor/hermes_mcp_server/server.py:1074-1077` 已經送
  `"paused": not enabled, "enabled": enabled`，不用動。

## 5. PaaS 測試逐案對照

HA 的測試全部在 `tests/test_fresh_backend_connections.py`；每案跑兩個產品（`litellm`、`emqx`）× 兩種連線池（`child`、`asked`）。

| # | PaaS（commit） | HA | 照抄／改寫／不適用與理由 |
|---|---|---|---|
| 1 | `apps/emqx/tests/test_transport.py::test_each_request_resolves_and_uses_fresh_pinned_socket`（#135 `3c06b98`；由 `test_dns_resolves_once_and_socket_uses_pinned_address` 改名改寫） | `test_each_request_resolves_and_uses_a_fresh_pinned_connection` | **改寫**。照 PaaS：設定的名稱解析到 127.0.0.1、`HTTP_PROXY`／`ALL_PROXY` 指到 127.0.0.1:1、連兩個請求；斷言兩次解析、後端兩個請求、兩條連線。改的地方：走產品自己的 `build_client`／`make_client`（HA 的 EMQX 沒有 PaaS 的 `BrokerClient`／`BrokerTransport`，傳輸層是 `backend_policy`），直接用 client 送（產品包的錯誤對應另有 `tests/test_emqx_error_translation.py`）；連線數用假後端的連線編號，再加 TCP connect 次數（audit hook），不用 client port；另加每個回應讀完後池裡 0 條、沒有連到假後端以外的位址；LiteLLM 也跑（PaaS 的 LiteLLM 沒有這一案） |
| 2 | 同一案拿掉的舊斷言：解析一次（`len(resolutions) == 1`，第二次解析就丟 `AssertionError`） | — | **不適用**。PaaS 拿掉的是舊行為的斷言，HA 沒有「一個 client 只解析一次」的測試。`tests/test_backend_policy_python.py::test_dns_is_pinned_without_second_lookup` 驗的是一次連線裡解析後不再查第二次（TOCTOU），和連線池無關，照舊成立 |
| 3 | `apps/emqx/tests/conftest.py` 的 `broker` fixture 加 `client_ports`（#135） | harness 的 `Backend`／`Handler` | **改寫**。HA 的假後端在 harness 裡：每條連線一個編號（`setup()`），每個請求記方法、路徑與連線編號；TCP connect 由 audit hook 記 |
| 4 | `apps/litellm/tests/test_recovery_pool.py::test_first_key_info_after_health_recovery_uses_fresh_connection`（#139 `009dc99`，新檔） | `test_the_first_call_after_a_recovery_uses_a_fresh_connection` | **改寫**。情境照 PaaS：`fastmcp.Client(build_server())`（in-memory）呼叫 `litellm_key_info` 一次；假閘道停機回 503，用新連線的健康探測看到 503；恢復後新連線的探測 200；之後落在舊連線上的請求只收不回（等 `release`）；讀取逾時 2 秒（`LITELLM_MCP_REQUEST_TIMEOUT=2`）；斷言恢復後第一個呼叫不是錯誤。改的地方：EMQX 也跑（`emqx_cluster_status`，`EMQX_MCP_REQUEST_TIMEOUT=2`）；環境照 `products.child_spec`、在產品的 venv 裡跑；名稱經 DNS 釘選路徑解析；「舊連線」是停機前回過請求的每一條（PaaS 是第一個 key_info 的 socket）；另加：第一個呼叫沒落在舊連線、少於讀取逾時 |
| 5 | — | `test_the_pool_keeps_no_idle_connection` | **HA 另加**。直接看連線池：`child` 是 `backend_policy` 的、`asked` 是產品要的（PaaS 改的就是這個值，PaaS 沒有直接斷言） |
| 6 | — | `test_each_request_checks_its_destination_again` | **HA 另加**（任務要求的第 2 點）：名稱改指被拒的位址（169.254.169.254）後，下一個請求在連線前就被拒（`BackendDenied`），解析一次、後端收不到、沒有連到該位址。PaaS 只用解析次數間接驗 |
| 7 | — | `test_nothing_is_sent_twice` | **HA 另加**（PaaS 兩個 commit 說明的「不加重送」）：恢復後第一個呼叫只到後端一次；後端收完寫入、沒回就斷線時，寫入只送一次，回產品自己的「無法使用」錯誤（LiteLLM `BACKEND_UNAVAILABLE`、EMQX `EMQX_UNAVAILABLE`） |

## 6. 守門有效的證據

### 6.1 先紅後綠

| 輪 | 程式 | 結果 | 證據 |
|---|---|---|---|
| 紅（只有測試：`3bca5f4`＝`7646f0f`＋新測試） | 修正前 | 8 failed、12 passed（12.7 秒） | `red-tests-only-7646f0f.txt` |
| 綠（`89d682c` 起） | 修正後 | 20 passed（8.0 秒） | `green-after-fix.txt`、`full-suite.txt` |

紅的 8 案都在 `asked`，每案紅在預期的那一句：
- `test_the_pool_keeps_no_idle_connection`：LiteLLM `{'keepalive_expiry': 30.0, 'max_connections': 50, 'max_keepalive_connections': 20}`、
  EMQX `{'keepalive_expiry': 5.0, 'max_connections': 20, 'max_keepalive_connections': 10}`。
- `test_each_request_resolves_and_uses_a_fresh_pinned_connection`：解析 1 次（要 2 次）。
- `test_each_request_checks_its_destination_again`：名稱改指被拒的位址後，第三個請求經舊連線照樣送到（`answered 200`）。
- `test_the_first_call_after_a_recovery_uses_a_fresh_connection`：落在舊連線、等滿 2 秒：LiteLLM「Request to LiteLLM timed out (GET /key/info)…
  BACKEND_TIMEOUT」、EMQX「EMQX_TIMEOUT: the broker did not finish the request…」。

`child` 的 10 案與 `asked` 的不重送 2 案在基準上就過：傳輸層本來就不留閒置連線（第 3 節），也從來沒有重送。

### 6.2 臨時突變（`tools/mutation_driver.py`；修正後的程式上，把 `apps/runtime` 複製到暫存目錄再改，跑提交的 harness 與 5 個測試函式；clone 的檔沒動。不是 pytest，沒排共用鎖：只用 loopback 臨時 port，約 25 秒）

| 突變（`backend_policy.py` 的副本） | `child`（每個產品） | `asked`（每個產品） | 說明 |
|---|---|---|---|
| 無 | 5／5 過 | 5／5 過 | 對照 |
| M1 傳輸層留 4 條閒置連線 | **紅 4 案**（連線池、新連線、重新檢查、恢復後第一個呼叫） | 5／5 過 | `asked` 用產品要的設定（0），不受影響：這正是本片要的第二層 |
| M2 失敗時重送一次 | **紅 2 案**（不重送：寫入送了 2 次；重新檢查：被拒的請求又解析了一次） | **紅 2 案** | |
| M3 名稱只解析一次（快取 `checked_answers`） | **紅 2 案**（新連線：解析 1 次；重新檢查：`answered 200`） | **紅 2 案** | |
| M4 client 的 `trust_env=True` | 5／5 過 | 5／5 過 | 等價突變：httpx 0.28.1 給了 `transport` 就一律不用環境變數的代理（`httpx/_client.py:1399`，`allow_env_proxies = trust_env and transport is None`），行為不變。測試裡的代理檢查是對照 PaaS 的健全性檢查 |

結果檔：`mutations-after-fix.json`。

## 7. 本機檢查（2026-11-17，一般使用者 uid 1000；TMPDIR 用 `ha_env.sh` 給的 `/tmp/ha-mp-XXXXXX`，每次跑完用完整路徑刪除；pytest 都排在共用鎖後面）

| 檢查 | 結果 | 證據 |
|---|---|---|
| 新測試：紅、綠 | 見第 6.1 節 | `red-tests-only-7646f0f.txt`、`green-after-fix.txt` |
| 突變 | 見第 6.2 節 | `mutations-after-fix.json` |
| 全套 pytest（head `2b3ef37`；之後只加本筆記） | 6,082 案：6,053 過、29 失敗（7 案要 root、22 案瀏覽器測試沒有 Chromium；都是既有，和本片無關）、0 skip、0 error；1,872 秒（排隊另計） | `full-suite.txt`、`full-suite-junit.xml` |
| 全套裡的相關檔 | 24 個檔 786 案全過：新檔 20（7.3 秒）、`test_output_schemas` 189、`test_tool_inventory` 8、`test_ledger_precheck` 8、`test_upgrade_zero_rewrite` 37、`test_six_egress` 27、`test_backend_loopback` 153、`test_backend_policy_python` 125、`test_real_products` 9（真的 LiteLLM、EMQX 子程式連假後端）、`test_child_bearer` 28、`test_session_idle` 24、HM-01 守門 45（黃金回歸 17、MCP 契約凍結 9、管理契約凍結 19）、EMQX 三檔 44、LiteLLM 五檔 21、`test_output_schema_runtime` 20、`test_full_surface` 28 | `full-suite-junit.xml` |
| `packaging/validate.py`（ci-venv 的 Python） | PASS | `packaging-validate.txt` |
| packaging unittest（離線暫存 venv：`uv sync --frozen --no-dev --offline`＋`requirements-ci.txt`，`discover -s packaging -p 'test_*.py'`，同 CI） | 203 案 OK、5 skip（要 root），23 秒 | `packaging-unittest.txt` |
| `scripts/tool_inventory.py` | 0 漂移（exit 0） | `tool-inventory.txt` |
| 雙向控制字元（U+202A～U+202E、U+2066～U+2069） | 改到的檔、本筆記、commit 訊息：0 個 | `tools/bidi_check.py` |

本機一定失敗的既有案例（要 root）：`test_owned_executable` 的 uid10001、`test_profile_store::test_mode_and_owner_as_the_add_on_user`、
`test_restore_detection` 的 `test_root_*` ×5。

## 8. 只在 CI 跑的測試、`checks` 秒數

- 本片新增與改過的測試都在本機跑過（第 7 節）。新測試要產品自己的 venv（`apps/litellm/.venv`、`apps/emqx/.venv`），CI 的 `packaging/unit.sh`
  先裝好；本機也有。CI（root、0 skip）才是準。
- 要 root、本機一定失敗的既有 7 案（第 7 節）只在 CI 過。瀏覽器測試 22 案（`test_owned_browser_redirect.py` 16、`test_owned_browser_ipc.py` 5、`test_owned_ui.py` 1）本機也沒跑成：這個 clone 沒有 Playwright 的 Chromium headless shell，裝要下載（本片規則不准連網），本機失敗在啟動瀏覽器；CI 的 `unit.sh` 先 `npm run browser:install` 再跑。本片沒動 UI，也沒動它們測的東西。
- 本片的測試在 root 下：不依賴 uid 或檔案權限；只綁 127.0.0.1 的臨時 port（不是 3000、18000～18099）；名稱解析在 harness 裡換掉，不查真的 DNS。
- `checks` 秒數：開 PR 後補（前：`claude-delivery` 最近一次 PR run；後：本片 PR）。
- 新測試的時間：本機（AMD EPYC 7713、Python 3.13.15）20 案 8.0 秒：四次 harness 各約 1.9～2.0 秒（產品 venv 啟動、import fastmcp 與產品模組、三個情境；算在 fixture 的 setup），測試函式本身都在 5 ms 以內。只有測試（紅）時 12.7 秒，多的是 `asked` 兩次恢復情境各等滿 2 秒逾時。CI 推估：GitHub runner 約是本機的 1.5～2 倍，約 12～16 秒；對 `checks`（HM-31 筆記記的約 34 分鐘；上限 60 分鐘）的影響可以忽略。

## 9. 預檢結果

| 預檢 | 指令 | 結果 |
|---|---|---|
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools SP:hm01/gitleaks-tools --repo . --base 7646f0f --head HEAD --full` | 前 3 個 commit（`7646f0f..2b3ef37`；gitleaks 8.28.0 釘版已驗；另掃 HEAD 整棵樹與整個歷史）：`result: OK, 0 findings`。加上本筆記的 commit 後重跑的結果寫在交回主對話的回報（筆記記不到自己那個 commit） |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base 7646f0f` | `result: OK`：`runtime-patches.json` 176 檔、`runtime-sources.json` 70 檔、`tool-surface.json` 159 檔，0 漂移、0 缺；改到的 2 個列管檔都有帳本更新；沒有未列管的新 runtime 檔 |

`SP:`＝`/data/pi-agent/tmp/claude-1000/-data-pi-agent-home-woow-sec-sweep/9a04e4b3-b708-497b-b300-75c6a25db75e/scratchpad/`。

測試資料：token、key 都是 `T`×43、`C`×43；名稱 `backend.invalid`；假後端只在 127.0.0.1。沒有 commit 隨機產生的 token 或像金鑰的字串；
harness 的輸出若出現這兩個值，測試就失敗（不印出來）。本筆記不含 token、密碼或像金鑰的字串（帳本摘要是檔案內容的 SHA-256）。

## 10. 本片用到的決策（`docs/multi-profile/decisions.md`）

| 決策 | 內容 | 本片怎麼用 |
|---|---|---|
| 第 1.1 節，2026-11-17 02:3x（使用者） | PaaS #135、#139 現在就補到 HA 的 LiteLLM、EMQX，不等 HM-21／HM-23；不受開關管，兩個產品下一版生效；#138 HA 已有 | 本片照做；實作時查到的事補記在同一列 |
| DQ-36 | 不改版號的功能 PR、標題前綴、commit 與 PR 說明不加 AI 署名 | 本分支的 commit 沒有 AI 署名；不 push、不開 PR（本階段） |
| DQ-40 ⑦（HM-20） | 開通後子程式拒絕 loopback 後端 | 沒動；新測試用 `loopback_backends.allowed()` 建子程式環境，產品開通後也照樣能用 loopback 假後端 |

## 11. 其他產品的連線池設定（交 HM-29 決定要不要比照）

| 產品 | 後端 client | 產品給的設定 | 實際生效 | 閒置連線 |
|---|---|---|---|---|
| LiteLLM（本片） | `backend_policy.async_client` | 50／20／30 秒 → 50／0 | `AsyncTransport`：上限 4、閒置 0 | 不保留 |
| EMQX（本片） | `backend_policy.async_client` | 20／10 → 20／0 | 同上 | 不保留 |
| Odoo | XML-RPC：`backend_policy.XMLTransport`（http.client） | — | 每次交換完 `close()`（`apps/runtime/backend_policy.py:656-657`） | 不保留 |
| Hermes | `backend_policy.async_client`（閘道、dashboard、登入） | 沒給 | `AsyncTransport`：上限 4、閒置 0 | 不保留 |
| OpenDesign | `backend_policy.sync_client` | 沒給 | `SyncTransport`：上限 4、閒置 0 | 不保留 |
| Nextcloud | `backend_policy.async_client`（`load_backend_policy`；HA 一定有這個模組） | 沒給 | `AsyncTransport`：上限 4、閒置 0 | 不保留 |
| **Headscale** | 自己的 `HeadscaleTransport`（`apps/headscale/vendor/headscale_mcp_server/http_policy.py:150-156`），一個 client 用到程序結束（`apps/headscale/launch.py:26`） | `max_connections=4, max_keepalive_connections=4`；`keepalive_expiry` 沒給（httpx 預設 5 秒） | 同左 | **保留最多 4 條、5 秒**；讀取逾時 20 秒 |
| n8n（Node，不是 httpx） | API client：n8n-mcp 2.96.2 `SSRFProtection.createPinnedAgents` → `http.Agent({ keepAlive: false })`，每個請求重新解析（`apps/n8n/backend_policy.cjs:117-142`）；官方 MCP 端點：`createPinnedFetch` → undici `Agent({ keepAliveTimeout: 1000 })`，連上後一直用（`node_modules/n8n-mcp/dist/utils/ssrf-protection.js:317-318、343-346`） | — | API：不保留；官方 MCP 端點：閒置最多 1 秒 | API 不保留；官方 MCP 端點 1 秒 |
| Odoo Manage（已下架，0.1.5 起沒有映像） | `backend_policy.sync_client`＋`XMLTransport` | 沒給 | 閒置 0 | 不保留 |
| 參考：閘道 → 子程式（loopback，不是後端） | `packages/mcp-admin-core/mcp_admin_core/profile_runtime.py:207-209`、`apps/n8n/run.py:55-56` | `Limits(max_connections=40／24)`、`Limits(max_connections=40)` | httpx 預設：閒置 20、5 秒 | 保留（loopback，不受網路中斷影響） |

- PaaS `7087280`：EMQX 0（#135）、LiteLLM 0（#139）、Headscale 同樣 4／4（`apps/headscale/headscale_mcp_server/http_policy.py:189`）。
- 給 HM-29：Headscale 和 PaaS #135 修正前的 EMQX 是同一種情況（自己的傳輸層、保留閒置連線），只是閒置 5 秒就關，影響的窗口比較短：
  最後一次請求後 5 秒內網路中斷又恢復時，下一個請求可能落在舊連線、等到 20 秒逾時。要改就兩邊（PaaS 與 HA）一起比照 #135，改 vendored 的
  `http_policy.py`（帳本與 `output_schemas` 釘選照本片的做法）。n8n 官方 MCP 端點的 1 秒窗口更短，可列為觀察。

## 12. 交給後面的片（CHANGELOG 一行原文）

本 PR 不改 `addons/`。LiteLLM、EMQX 下一次發版時，各在 `addons/<產品>/CHANGELOG.md` 記一行（英文，照既有 CHANGELOG 的寫法；PaaS 的 PR 號寫成 `woow-mcp-server #…`，免得和本 repo 的 PR 號混淆）：

- `addons/litellm/CHANGELOG.md`：
  "- The LiteLLM client's connection pool now asks for no idle backend connections, as the PaaS server does (woow-mcp-server #139): every request opens a fresh connection and nothing is retried, so the first tool call after a network outage never waits on a stale connection. The add-on's backend policy already kept no idle connection, so behavior does not change."
- `addons/emqx/CHANGELOG.md`：
  "- The EMQX client's connection pool now asks for no idle broker connections, as the PaaS server does (woow-mcp-server #135): every request opens a fresh connection and nothing is retried, so the first request after a network outage never waits on a stale connection. The add-on's backend policy already kept no idle connection, so behavior does not change."

其他產品的 CHANGELOG 不用寫：它們的程式沒變（每個映像都會帶到更新過的 `docs/provenance/`，只是文件）。

## 13. 驗收條件（計畫 §12.3 HM-32）

| 條件 | 狀態 |
|---|---|
| 全綠 | **本機能跑的都綠**：新測試 20 案、相關 24 個檔 786 案、packaging unittest、`validate.py`、`tool_inventory.py`、兩個預檢都過；全套只剩 7 個要 root 的既有案例與 22 個沒有 Chromium 的瀏覽器測試（第 7、8 節），等 CI（root、0 skip） |
| PaaS 的測試案例逐案對照（照抄、改寫或不適用都寫理由） | 通過：第 5 節（PaaS 改過的 2 案與 1 個 fixture 改寫、1 個拿掉的舊斷言不適用、HA 另加 3 個） |
| 兩個產品的連線池不保留閒置連線；不加重送；逾時、`trust_env`、轉址與代理拒絕、DNS 釘選、目的地檢查不動 | 通過：第 2、3 節；`backend_policy.py` 沒改 |
| 測試先紅後綠、四個要求（新連線、重新解析與檢查、恢復後不卡逾時、不重送） | 通過：第 5、6 節（另有 3 個突變擋下、1 個等價突變） |
| 不改版號、不碰 `addons/`；開關維持空的 | 通過 |
| 帳本、決策、契約、provenance | 通過：第 2、9 節 |
| 兩個產品下一版的 CHANGELOG 各一行（交發版片） | 第 12 節（原文） |
| 獨立審查 | **還沒做**：待主對話安排（本片代理不審自己的片） |
| 測試資料規則（計畫 §12.0 第 4 點） | 通過：第 9 節 |

## 14. 還沒解決、交給後面的片

- **獨立審查**：待主對話安排。
- **HM-29**：第 11 節的表；Headscale（保留 4 條、5 秒）與 n8n 官方 MCP 端點（1 秒）要不要比照 #135。
- **既有的相鄰差異（本片沒動）**：兩個產品實際的後端並行上限是 `backend_policy` 的 4 條：`lifespan.py` 寫的 `max_connections`（LiteLLM 50、
  EMQX 20）也被丟掉；PaaS LiteLLM 是 50 條、PaaS EMQX 4 條。一個子程式同時超過 4 個後端請求時，多的在 httpx 池裡排隊（EMQX 的 `pool` 逾時
  5 秒、LiteLLM 跟著請求逾時 60 秒）。這是 HA `backend_policy` 一開始（`313ab01`）的設計，和保留閒置連線無關，所以本片沒改、契約第 9 節
  （多帳號的刻意差異）也沒加列。要不要記成差異或調整，交 HM-29（或 HM-21、HM-23 開通 LiteLLM、EMQX 時一起看）。
- **發版片**：第 12 節的 CHANGELOG 句子。
- **repo 外**：計畫 §12.3 HM-32 與 FEATURE-MATRIX FM-155 的「缺少」可補一句「實際行為本來就一樣（`backend_policy` 丟掉 `limits`），本片對齊設定與加測試」。

## 15. commit（`7646f0f` 之後）

| commit | 內容 |
|---|---|
| `3bca5f4` | 測試（先紅：`asked` 8 案紅） |
| `89d682c` | 修正：兩個 `lifespan.py`；帳本（`runtime-sources.json`、`tool-surface.json`）；`test_output_schemas.py` 的釘選；新測試的一個 assert 訊息與 docstring |
| `2b3ef37` | 文件：契約第 1.2、10 節，`decisions.md` 第 1.1、5 節，驗收矩陣的測試檔登記表 |
| （本 commit） | 本筆記 |
