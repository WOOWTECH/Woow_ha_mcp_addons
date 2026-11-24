# HA provenance：EMQX `emqx_list_topics` 的說明對齊 PaaS #160（2026-11-25）

## 結論

- **做了什麼**：`emqx_list_topics` 的說明不再說「這裡沒列出的主題就是沒人訂閱」。`apps/emqx/vendor/emqx_mcp_server/tools/topics.py` 的 docstring 與
  `registry.py` 裡同一支工具的一行說明，照 PaaS #160（woow-mcp-server `fb7571c`，2026-11-23）逐字改，換行也一樣；兩個檔整檔和 PaaS 的位元組相同。
  不改版號、不碰 `addons/`，`features.MULTI_PROFILE_PRODUCTS` 不動。
- **為什麼**：`/topics` 列的是路由。萬用字元訂閱以過濾器本身為鍵（`a/#`），不會以它涵蓋的具體主題單獨出現；共享訂閱與持久 session 的訂閱也可能不出現。
  舊說明會讓模型把「沒列出」當成「沒人訂閱」。新說明講清楚這支列的是什麼、哪些訂閱看不到，並指向 `emqx_list_subscriptions`。
- **程式行為不變**（第 3 節）：`topics.py` 去掉 docstring 後的語法樹和基準 `092b1b5` 相同；`registry.py` 只有 `emqx_list_topics` 那一個字串常數不同。
- **用戶端看到的變化**（第 4 節）：只有 `emqx_list_topics` 的 `description`（8081 的 tools/list 與 8099 `/api/capabilities` 工具目錄的同一個欄位）；
  閘道送出的整個 tools/list 回答 32,306 → 32,530 位元組，多 224。工具名稱、輸入與輸出 schema、annotations、寫入權限、tools/call 逐位元不變。
- **跟著改的**（第 4 節）：閘道內附的工具清單 `tool_snapshot.py`（只重產 EMQX 那一個產品）、三個帳本、`test_output_schemas.py` 與 `test_single_profile_golden.py`
  的釘選；文件：契約第 1.2、10 節、`unreleased-changes.md` 的 E4、`acceptance-matrix.md` 一列。
- **測試**（第 5 節）：新 `tests/test_emqx_list_topics_description.py`（6 案）先紅（`092b1b5` 上 5 案紅）後綠；相關 16 個檔 374 案全過、0 skip
  （4 案在這台機器第一次因主機條件失敗，和本次修改無關，重跑過）。
- **限制**（第 7 節）：沒用真 EMQX broker 驗證說明的事實（PaaS 的說法）；`scripts/tool_inventory.py` 在這台機器要用外包腳本指定 node 路徑才跑得起來。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 性質 | 不受開關管（契約第 1.2 節）；只改文字；2026-11-25 維修版的一項 |
| 分支 | `fix/emqx-topics-wording-20261125`（只 commit，沒 push、沒開 PR） |
| 基準 | `claude-delivery` `092b1b5`（#136 的合併） |
| 對齊的 PaaS | woow-mcp-server `fb7571c`（2026-11-23，「還原手冊措辭、EMQX／K8s 工具說明（P3）」，PaaS #160）；來源檔是 repo 外的本機唯讀副本，沒碰 PaaS |
| 套件（都沒動） | FastMCP 4.1.3（EMQX 子程式的釘版環境）；CPython 3.13.11（本機）；`uv.lock` 未改 |

## 2. PaaS 對照與整檔比對

#160 的 EMQX 部分是三個檔：

| PaaS 檔 | 改了什麼 | HA 對應 |
|---|---|---|
| `apps/emqx/emqx_mcp_server/tools/topics.py` | `list_topics` 的 docstring（工具的說明） | `apps/emqx/vendor/emqx_mcp_server/tools/topics.py`，逐字 |
| `apps/emqx/emqx_mcp_server/registry.py` | `emqx_list_topics` 的一行說明 | `apps/emqx/vendor/emqx_mcp_server/registry.py`，逐字 |
| `apps/emqx/tests/test_subscription_match_topic.py` | 新增 1 案：說明不再說「沒列出就是沒人訂閱」 | `tests/test_emqx_list_topics_description.py`（6 案；PaaS 那案的三個斷言在第 2 案） |

同一個 commit 的其他部分和 HA 無關，沒有照抄：還原手冊 `docs/paas-config-restore-runbook.md` 與它的測試（PaaS 的備份還原流程）、K8s 的 README 與
`tool_registry.py`（HA 沒有 K8s MCP 產品）。

兩邊整檔比對（改之前；`diff` 加位元組比對）：

- `topics.py` 只差 `list_topics` 的 docstring（HA 舊檔第 34～37 行，PaaS 第 34～41 行）。`emqx_list_subscriptions` 的 docstring 與 `match_topic` 的參數說明本來就逐字相同
  （HM-23 對齊 PaaS #153 `cd1ed89` 時做過），所以不在這次的差異裡；整個檔沒有其他文字差異。
- `registry.py` 只差 `emqx_list_topics` 那一行（第 83 行）。
- 改完後兩個檔整檔位元組和 PaaS 的相同：`topics.py` 5,293 位元組、sha256 `7e9e3704f60717a5b1cca317c0ae3d2d78ff0d0e1eac22e71d0a3fc3feec412b`；
  `registry.py` 6,561 位元組、sha256 `30d439ba0363a3caa9aa692260b88605d9970843d87ef80d3b8b765265d9f625`。

## 3. 語法樹與編譯結果比對（程式行為不變）

用專案的 Python 3.13 比 `git show 092b1b5:<path>` 和改後的檔：

| 檔 | 去掉 docstring 後的語法樹 | 編譯後的 code object |
|---|---|---|
| `topics.py` | 相同 | 4 個，只有 `register.list_topics` 的第一個常數（docstring）不同，位元組碼、名稱、常數個數都相同 |
| `registry.py` | 不同，只差一個字串常數（`emqx_list_topics` 的說明參數，不是 docstring）；所有字串常數遮掉後相同 | 5 個，只有 `<module>` 的第 37 個常數不同，位元組碼、名稱、常數個數都相同 |

## 4. 工具清單、黃金摘要與帳本

**閘道內附的工具清單**（`tool_snapshot.py`）：只用產生器重產 EMQX 那一個產品（`WOOW_WRITE_TOOL_SNAPSHOT=1`，`tests/test_tool_snapshot.py -k emqx`，和 HM-23 同做法）。
和基準比：8 個產品的順序與各自的工具數相同，不同的只有 `emqx_list_topics` 的 `description`（10 行 diff）。檔案 sha256 `ddc73229…` → `62e4c298…`
（508,330 → 508,673 位元組）。

**HM-01 黃金回歸的 EMQX 兩個摘要**（`tests/test_single_profile_golden.py`，照檔頭的規則一起更新）：

| 摘要 | 前 | 後 | 位元組 |
|---|---|---|---|
| `LISTING_SHA256`（`surface.listing('emqx')` 的緊湊 JSON） | `dad5f8fc8843c047a3adfca67fe4962f4be628e5dc196a13f651b3e01ddbf5cd` | `8a97b2b106b740b9d88dff8d7742770bbf6110290aff0b5283dfcd5c68ec5df1` | 32,534 → 32,758（+224） |
| `LISTED_SHA256`（tools/list 整個回答） | `ca83692edc778cfc7b211bf313518c5e71d0d89c100001a2a3d0fc1b7d347c34` | `5ab1d324e664afeaf2e1b83fed8bce331451e291ac6011e94f56d1ee5ac8351b` | 32,306 → 32,530（+224） |

怎麼核對的：用一支外部外掛（不在 repo）在黃金回歸跑時存下整個 tools/list 回答。先把基準的 `tool_snapshot.py` 放進記憶體再跑，兩案都過、摘要和舊的釘選相同
（證明這個存法重現得了舊答案）；再用新的清單跑，取得新答案。新答案就是舊答案把 `emqx_list_topics` 那個說明字串換掉：這個 JSON 字串從 192 位元組變 416 位元組
（舊說明有一個 em dash，`ensure_ascii` 把它寫成 6 個 ASCII 位元組），差 224；把舊答案裡的那個字串換成新的，和新答案逐位元相同。39 個工具名稱與順序相同，
只有這一支的 `description` 不同，`result.tools` 以外的欄位也相同。

**帳本與釘選**（都照檔重算 SHA-256）：

| 檔 | 改了什麼 |
|---|---|
| `docs/provenance/runtime-sources.json` | `topics.py` 的 `local_sha256` 與 `modification`；`registry.py` 原本沒有本地修改，加 `local_sha256` 與 `modification` |
| `docs/provenance/runtime-patches.json` | `tool_snapshot.py` 的 `sha256` 與 `change`；`n8n_arguments.py` 的 `guarded_sources` 裡同一個摘要與 `change` 一句（它本身沒改） |
| `docs/tool-surface.json` | `source_digests` 的 `topics.py`、`registry.py`；`emqx_list_subscriptions` 的行號 54 → 58（上面的 docstring 多 4 行）；`tool-surface.md` 不變 |
| `tests/test_output_schemas.py` | `CURRENT_POST_SOURCE_BYTES`：`topics.py` 換新摘要，`registry.py` 新增一筆（`output_schemas.json` 記的是來源 commit 的位元組，不改） |

`scripts/tool_inventory.py` 要全部產品的相依都裝好：根目錄與 8 個 app 的 `.venv`（`uv sync --frozen`）、`apps/n8n` 的 `npm ci --ignore-scripts`、
Odoo 與 n8n 的建置補丁（照 `packaging/unit.sh`）。裝好後，算出來的清單和改之前的 `docs/tool-surface.json` 只差上表的三個值，其他 7 個產品、n8n 與 Odoo Manage 的
每個摘要、行號與欄位都是 0 漂移，`tool-surface.md` 逐位元相同；帳本更新後差 0 處。

沒改：版號、`addons/`、`features.MULTI_PROFILE_PRODUCTS`、`tests/conftest.py`、`output_schemas.json`、`docs/multi-profile/paas-test-mapping.md`（外部產生器在
`48f394d` 產的，沒有 #160 新增的第 7 案；那案對到第 2 節的新測試）、`decisions.md`（這件事沒有要使用者決定的選項）。

## 5. 測試（先紅後綠）與預檢

- 新檔 `tests/test_emqx_list_topics_description.py`，6 案，跑在 HM-01 的 log 掃描下：子程式自己的 tools/list（`apps/emqx/.venv`、不發任何請求）、vendored registry
  的一行說明、閘道內附的清單三處逐字是 PaaS 的；PaaS 新增那案的三個斷言；舊的說法（「at least one subscriber」「means nobody is subscribed」「usual reason a
  published message appears to vanish」「Routed topics」）三處都不再出現；說明指向的 `emqx_list_subscriptions` 在子程式的清單裡。
- 紅：`092b1b5` 加上只有這個測試的 commit，5 案紅（說明還是舊的），1 案（指向的工具存在）本來就綠。綠：下一個 commit 起 6 案過。
- 本機（2026-11-25，uid 1000，CPython 3.13.11；pytest 排在共用鎖後面，每次跑完用完整路徑刪掉自己的 `/tmp/ha-mp-XXXXXX`）：相關 16 個檔 374 案
  （`tests/test_emqx*.py` 8 檔 85 案、`test_output_schemas.py` 189、`test_single_profile_golden.py` 17、`test_tool_inventory.py` 8、`test_tool_snapshot.py` 11、
  兩個契約凍結 19＋9、`test_ledger_precheck.py` 8、`test_full_surface.py` 28）。第一次跑 370 過、4 失敗。這 4 案是這台機器的條件，失敗在碰到說明之前，和本次修改無關：
  - `test_emqx_multi_profile.py` 的 2 案：`the runner has no private address for the fake brokers`（這台的主機名稱在 `/etc/hosts` 解析到 `127.0.1.1`；
    CI 的 runner 有私有位址）。
  - `test_tool_inventory.py::test_inventory_names_hashes_schema_and_documentation_do_not_drift` 與 `test_full_surface.py::test_every_child_tool_is_served`：
    `FileNotFoundError: 'node'`（`scripts/tool_inventory.py` 用 `PATH=/usr/bin:/bin` 找 `node`，這台的 Node 不在那裡）。

  用一支外部外掛（不在 repo）重跑這 4 案：只把那一次 `node` 的查找換成絕對路徑、只讓那一次主機名稱查詢回這台的一個私有介面位址，其餘不動。4 過（121 秒）。
  所以 374 案都過、0 skip。`test_tool_inventory` 那一案就是帳本的閘門：它過，表示 `tool-surface.json`、`tool-surface.md`、各產品原始碼摘要與本次改動一致。
- `python3 scripts/ledger_precheck.py`（對 `origin/claude-delivery`，合併基準 `092b1b5`，三個 commit 之後）：`runtime-patches.json` 185 檢查、0 漂移、0 缺；
  `runtime-sources.json` 70、0、0；`tool-surface.json` 160、0、0；沒有「需要 CI 安裝」的項目（相依都裝好了）。改到的列管檔 3 個（`registry.py`、`topics.py`、
  `tool_snapshot.py`），帳本 3 個，都在本分支一起改；沒有新的或未列管的執行期檔。結果 OK，exit 0。
- `python3 scripts/secret_precheck.py`（gitleaks 8.28.0，釘版、SHA-256 驗過）：對本分支的每個 commit 掃過，0 個發現。
- `python3 packaging/validate.py`：PASS。`git diff --check` 乾淨；改到與新增的檔掃過，雙向控制字元與其他控制字元 0 個、沒有 CR。

## 6. 交發版片的 CHANGELOG 句子（EMQX 的下一版）

```text
- `emqx_list_topics` no longer says that a topic missing from its list has no subscriber (PaaS #160). Its description now says the tool lists the broker's routes (topics or topic filters): a wildcard subscription such as `a/#` appears under the filter itself, not under the concrete topics it covers, and shared or persisted-session subscriptions may not appear either, so a concrete topic missing from the list does not mean nobody is subscribed; to find out who receives messages published to a topic, use `emqx_list_subscriptions`. Text only: no tool name, input or output schema, grant, request or reply changes.
```

同一句在 `docs/multi-profile/unreleased-changes.md` 第 3.4 節 E4。HA 沒有 PaaS README 要補的句子。

## 7. 限制與沒驗證的事

- **沒用真的 EMQX broker 驗證**說明的事實：`/topics` 列路由、萬用字元訂閱以過濾器為鍵、共享與持久 session 的訂閱可能不出現。這是 PaaS #160 的說法
  （PaaS 以 2026-11-14 對 EMQX 5.8.9 的實測為底）；HA 只對齊文字，沒有重測，也沒有在展示機（HAOS）上驗收。
- 8099 `/api/capabilities` 工具目錄與管理面板工具頁的畫面沒有另外開頁面看：工具目錄的 `description` 取自同一份清單（`capabilities.py`），測試只比對了清單。
- `scripts/tool_inventory.py` 用 `PATH=/usr/bin:/bin` 呼叫 `node`，這台機器的 Node 22.23.4 在 `/usr/bin` 之外，直接跑會 `FileNotFoundError`。這次用一支外部外包腳本
  （不在 repo）把 `node` 換成絕對路徑，其餘邏輯（`build()`、`markdown()`）原樣呼叫。repo 沒改這支腳本。
- n8n 的原生附加元件（`packaging/native_addon.mjs`：better-sqlite3 的預建檔）沒裝：它釘的是 Node 26.12.1（ABI v147），這台機器只有 Node 20、22、24。
  `scripts/tool_inventory.py` 的摘要不含這個檔（只含 n8n-mcp 的 `dist/mcp/*.js`、`services/*` 與 `backend_policy.cjs`），所以不影響結果；n8n 子程式的真子程式比對
  （`test_tool_snapshot` 的 n8n 一案）在這個環境照樣過。
- 沒跑全套測試（交給 GitHub CI）、packaging 的測試、面板測試、容器驗收與 J1900 檢查。
- 後合併的分支要重算：`tool_snapshot.py` 的 sha256（`runtime-patches.json` 兩處）在別的分支也改這個檔時會變；EMQX 的兩個黃金摘要只在別的分支也改 EMQX 的工具清單時才要重算。

## 8. commit（`092b1b5` 之後）

| commit | 內容 |
|---|---|
| `fcdf509` | `test(emqx): pin that emqx_list_topics does not say a missing topic means nobody is subscribed (PaaS #160)`：新測試，5 案紅 |
| `3315899` | `docs(emqx): emqx_list_topics no longer says a missing topic means nobody is subscribed, as PaaS #160`：vendored 的兩處說明、閘道內附清單、帳本與釘選、黃金摘要 |
| `5a6d0d4` | `docs(multi-profile): record the emqx_list_topics wording change as an unreleased EMQX item (PaaS #160)`：契約、未發佈清單 E4、驗收矩陣 |
| 本筆記 | `docs(provenance): add the note for emqx_list_topics's description following PaaS #160`（第 4 個 commit，hash 不寫進自己） |
