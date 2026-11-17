# HA 多帳號發版交接清單 provenance：各產品下一版要帶的變更與 CHANGELOG（2026-11-17）

## 結論

- 範圍：新增 `docs/multi-profile/unreleased-changes.md`，列出每個產品上一次發版之後合併進 `claude-delivery`（`907bd39`）、會跟著它下一版
  出去、但 `addons/<產品>/CHANGELOG.md` 還沒記的變更與 CHANGELOG 建議句子（計畫 §11.5 與它 2026-11-17 加的那一條）。**只改 `docs/`**；
  `addons/`（含 CHANGELOG）、版號、程式、測試、`.github/` 都沒動。
- 上次發版：Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 是 0.4.13（升版 commit `1cbfcb9`，映像來源 `4966f40`，PR #76）；OpenDesign 0.4.13
  只升來源版本（商店停用，沒有映像）；Headscale 0.4.18（升版 commit＝映像來源 `55f3528`，PR #88）。2026-11-13 之後沒有任何產品發版。
- 每個產品要寫的項目：Odoo 7、n8n 6、Hermes 9、EMQX 10、LiteLLM 9、Nextcloud 8、OpenDesign 8、Headscale 6（第 4.7 節）。
- **已合併、CHANGELOG 沒記的產品自身修正**：
  - Hermes #85（`b50f1c7`）：`enabled=false` 的排程以前建出來其實是啟用的；
  - EMQX #87（`a4f4439`）：`emqx_test_rule_sql` 標成需要寫入權限；
  - OpenDesign #86（`1613be1`）的 OpenDesign 部分：`read_file` 公開輸出 schema；
  - 計畫線的產品專屬片：HM-32（#113，LiteLLM、EMQX，行為不變）、HM-33（#115，Hermes 說明）。
  - 另外兩項是 Headscale 那條線改的共用程式，Headscale 已記、其他 7 個產品沒記：#81（HA Core 2026.11.0、2026.11.1；0.4.13 的面板在 Core 2026.11.x
    上拒絕每個請求）、#77（EMQX、LiteLLM、Nextcloud 的面板提示文字變短）。
- 共通（多帳號計畫不受開關管、看得到的）6 項：HM-02、HM-06（n8n 不寫）、HM-13a、HM-14 的 initialize 錯誤遮罩、HM-31、HM-09 追補 #106。
- 位置：照慣例放 `docs/multi-profile/`（第 3 節），並在 `docs/operations/release.md` 的版號資料一節後面加一句指過去；契約第 1.2 節加一段指向它、
  第 10 節加一列；`docs/multi-profile/README.md` 的索引加一列。
- 檢查：HM-00 對照腳本 C1～C9 全部通過；秘密預檢 0 命中；帳本預檢 OK；雙向控制字元 0（第 7 節）。

## 1. 範圍與基準

| 項目 | 值 |
|---|---|
| 片 | HM-17 補正（發版交接清單；只改文件） |
| 分支 | `docs/ha-multiprofile-unreleased-changes-20261117`（clone `ha-mp-unreleased-20261117`） |
| HA 基準 | `claude-delivery` `907bd39`（#117 的合併；#89～#107、#110、#111、#113～#115、#117 都已合併） |
| 依據 | 計畫 §3.3（不受開關管的表）、§7.1、§11.5（repo 外）；契約第 1.2 節；各片的 provenance 筆記 |
| 沒合併、不在清單裡 | #108（HM-13b）、#109（HM-16）、#112（HM-13c）、#116（HM-27）：只在清單第 6 節列「合併時要改本檔的地方」 |

## 2. 改了什麼、沒改什麼

| 檔 | 內容 |
|---|---|
| `docs/multi-profile/unreleased-changes.md` | 新檔：檔頭（用途、誰讀、怎麼更新）、總表、共通 A1～A6、0.4.13 線共通 B1～B2、各產品節、沒有可見變化的片、發版時要另外驗的事、還沒合併的片 |
| `docs/multi-profile/README.md` | 索引加一列 |
| `docs/multi-profile/contract.md` | 第 1.2 節「不受開關管」清單前加一段指向新檔；第 10 節加一列。規則內容、差異表、錯誤代碼都沒改 |
| `docs/operations/release.md` | 「升版時要改的版號資料」最後加一句：寫 CHANGELOG 前先看新檔 |
| `docs/provenance/ha-multiprofile-unreleased-changes-20261117.md` | 本筆記 |

沒改：`addons/`（含各產品 CHANGELOG、DOCS、`upgrade-notes.yaml`）、根目錄 `CHANGELOG.md`、`AGENTS.md`、版號、`packages/`、`apps/`、`packaging/`、
`tests/`、`scripts/`、`.github/`、帳本（`runtime-patches.json`、`runtime-sources.json`）、`docs/tool-surface.*`。repo 外的計畫與 FEATURE-MATRIX
也沒改，要改的地方列在第 8 節。

## 3. 放在哪裡

- 看過的地方：`docs/multi-profile/README.md`（多帳號文件的索引，每份寫「誰維護」）與 `docs/operations/`（`release.md` 是發版流程，其他多半是
  逐版的 `release-decision-*.md`、`ha-test-*.md`）。repo 裡沒有現成的「還沒發版的變更」清單，根目錄與各產品的 CHANGELOG 都沒有 Unreleased 段。
- 決定：放 `docs/multi-profile/unreleased-changes.md`。
  - 會來加項目的是多帳號計畫的各片（不受開關管的那幾片），他們本來就維護這個目錄（契約第 1.2 節、各片筆記），索引的「誰維護」欄也寫得下
    更新規則。
  - 計畫線之外的修正（#77、#81、#85～#87）也收在同一份，因為發版的人要的是「一個產品下一版帶了什麼」，不分哪條線改的。
- 讓其他工作線找得到：發修補版的人照 `AGENTS.md` 與 `docs/operations/release.md` 做，不一定讀計畫或這個目錄。所以在 `release.md`「升版時要改的
  版號資料」最後（它原本就寫「CHANGELOG……不在這裡」）加一句指過去。`AGENTS.md` 在 repo 根目錄，不在 `docs/`，本片不改（第 8 節）。

## 4. 怎麼找出來的

### 4.1 版號與上次升版的 commit

```sh
grep -H '^version:' addons/*/config.yaml
git log -G'^version:' -1 --format='%h %ad %s' --date=iso-strict -- addons/<產品>/config.yaml
```

- 7 個產品 0.4.13：`1cbfcb9`（2026-11-07T23:37Z，`chore(release): prepare 0.4.13 source candidate`）。Headscale 0.4.18：`55f3528`（2026-11-12 20:00 +08）。

### 4.2 映像的來源 commit

- `docs/operations/release-decision-0.4.13.md`：「PR #76 image source: `4966f40…`」；`docs/provenance/release-0.4.13-images.json` 的
  `image_source_commit` 也是 `4966f40`，`disabled_product_not_published` 是 `opendesign`。
- `docs/provenance/headscale-0.4.18-provenance.json` 的 `predicate.subject.source` 是 `55f3528`。
- 發版的合併在來源之後只多紀錄檔：

  ```sh
  git diff --name-only 4966f40 e2108f6   # CHANGELOG、README、6 個 addons/*/CHANGELOG.md、release-decision-0.4.13.md、兩個 release-0.4.13-*.json
  git diff --name-only 55f3528 bb48449   # release-decision-headscale-0.4.18.md 與 5 個 headscale-0.4.18-*.json
  ```

  所以範圍用 `4966f40..origin/claude-delivery` 與 `55f3528..origin/claude-delivery`。`1cbfcb9..4966f40` 的三個 commit（`10a8134`、`3395c88`、
  `4966f40`）在 0.4.13 的映像裡。

### 4.3 映像帶哪些路徑

```sh
grep -nE '^\s*(COPY|ADD)' apps/*/Dockerfile
```

每個映像都複製：根目錄 `pyproject.toml`、`uv.lock`（相依）、`packages/mcp-admin-ui` 的 `package.json`、`package-lock.json`、`src/`、
`scripts/build.mjs`、`NOTICE.txt`（建面板）、`packages/mcp-admin-core`、`apps/runtime`、`apps/<產品>`、`packaging/entrypoint.py`、
`packaging/management_launcher.py`、`THIRD_PARTY_NOTICES.md`、`docs/provenance`；n8n 另有 `packaging/native_addon.mjs`。

### 4.4 上次發版之後的合併

```sh
SHARED="packages/mcp-admin-core packages/mcp-admin-ui/src packages/mcp-admin-ui/package.json packages/mcp-admin-ui/package-lock.json \
  packages/mcp-admin-ui/scripts/build.mjs packages/mcp-admin-ui/NOTICE.txt apps/runtime packaging/entrypoint.py \
  packaging/management_launcher.py pyproject.toml uv.lock THIRD_PARTY_NOTICES.md"
git log --first-parent --format='%h %ad %s' --date=short 4966f40..origin/claude-delivery -- $SHARED
git log --first-parent --format='%h %ad %s' --date=short 55f3528..origin/claude-delivery -- $SHARED
git log --first-parent --format='%h %ad %s' --date=short 4966f40..origin/claude-delivery -- apps/<產品> addons/<產品>   # n8n 另加 packaging/native_addon.mjs
git log --first-parent --format='%h %ad %s' --date=short 55f3528..origin/claude-delivery -- apps/headscale addons/headscale
```

結果：

- `4966f40..` 有 37 個合併（#76～#117，沒有 #80、#108、#109、#112、#116）；改到共用路徑的 26 個（其中 #76 是 0.4.13 本身）。
- `55f3528..` 有 26 個合併（#88～#117）；改到共用路徑的 18 個（#91、#93～#95、#97～#99、#101～#107、#110、#111、#114、#115）。
- 產品自己的路徑：Odoo、Nextcloud 沒有；n8n #91、#102；Hermes #85、#91、#115；EMQX #87、#113；LiteLLM #113；OpenDesign #91；
  Headscale 沒有。
- 相依套件與基底映像沒變：

  ```sh
  git diff --stat 4966f40 origin/claude-delivery -- pyproject.toml uv.lock 'apps/*/uv.lock' 'apps/*/pyproject.toml' 'apps/*/Dockerfile' \
    apps/n8n/package.json apps/n8n/package-lock.json packages/mcp-admin-ui/package.json packages/mcp-admin-ui/package-lock.json \
    packages/mcp-admin-ui/scripts/build.mjs packages/mcp-admin-ui/NOTICE.txt THIRD_PARTY_NOTICES.md packaging/native_addon.mjs
  ```

  只有 Headscale 新增的 `Dockerfile`、`pyproject.toml`、`uv.lock`（#77）。

### 4.5 逐一看每個合併改了什麼

```sh
git diff --name-only <合併>^1 <合併>           # 每個合併改到的檔
git diff <合併>^1 <合併> -- <共用檔>            # 共用檔逐行看（#77、#81、#82、#86、#87、#85 都逐行看過）
```

計畫線的片照它們的 provenance 筆記與契約第 1.2 節分「不受開關管、看得到」「不受開關管、看不到」「受開關管」三類（第 5 節）。

### 4.6 CHANGELOG 有沒有記

```sh
grep -nE '#8[1-9]|#9[0-9]|#1[01][0-9]|2026\.11|paused|test_rule_sql|rule_test|read_file|child bearer|restore-detected|keepalive|idle' \
  addons/*/CHANGELOG.md CHANGELOG.md
```

- 7 個 0.4.13 產品（含 OpenDesign）的 CHANGELOG：一個都沒命中，最新一段都是 0.4.13。另外逐段看過這 7 份的 0.4.13 段，沒有清單上任何一項。
- Headscale 的 CHANGELOG：Core 2026.11 在 0.4.14；#82、#83、#86 的內容寫在 0.4.15～0.4.18（沒寫 PR 號）。
- 根目錄 `CHANGELOG.md`：Headscale 的段落寫了 #82、#83、#86 與 Core 2026.11；其他命中都是和本清單無關的舊段落（PaaS 的 #81、#82，
  session idle，paused iterators）。沒有 #85、#87 與 #86 的 OpenDesign 部分。

### 4.7 各片筆記的交接句

```sh
grep -n -i 'changelog\|發版片\|交發版\|升版片' docs/provenance/ha-multiprofile-*.md
```

有英文句子的照原文抄（HM-13a、HM-31、HM-09 追補、HM-32、HM-33，#85 在 HM-33 筆記）；只有中文要點或沒有句子的，清單標「主對話補寫」，
照筆記與程式照實寫（HM-02、HM-06、HM-14、#81、#77、#86、#87）。

每個產品的項數（A＝共通，B＝0.4.13 線共通）：

| 產品 | A | B | 自己的 | 合計 |
|---|---|---|---|---|
| Odoo | 6 | B1 | — | 7 |
| n8n | 5（A2 不寫） | B1 | — | 6 |
| Hermes | 6 | B1 | H1 #85、H2 HM-33 | 9 |
| EMQX | 6 | B1、B2 | E1 #87、E2 HM-32 | 10 |
| LiteLLM | 6 | B1、B2 | L1 HM-32 | 9 |
| Nextcloud | 6 | B1、B2 | — | 8 |
| OpenDesign | 6 | B1 | D1 #86 | 8 |
| Headscale | 6 | — | — | 6 |

## 5. 每項的出處

| 項目 | 出處 | 核對了什麼 |
|---|---|---|
| A1 HM-02（#98） | HM-02 筆記第 3.4 節「顯示上的變化」、第 12 節第 6 點（給發版片的提醒，審查 SF-6）；契約第 1.2 節 | 句子照兩處的要點翻成英文；8 個產品都經 `redact` 的紀錄遮罩 |
| A2 HM-06（#94） | HM-06 筆記第 12.3 節（「任何產品的 CHANGELOG 都要寫明容器內直連子程式要帶 child bearer」）；`docs/operations/guide.md` 第 6 點；計畫 §7.1 | `products.child_spec` 只給 7 支 Python 子程式加 `WOOW_MCP_CHILD_TOKEN`（n8n 走 `n8n_adapter`，n8n-mcp 本來就驗同一個 token） |
| A3 HM-13a（#97） | HM-13a 筆記第 3.4 節（可以直接貼的段落）、第 11 節（不要照抄計畫 §3.3 的表） | 原文照抄；`packaging/entrypoint.py` 的 `PRODUCTS` 含 8 個產品 |
| A4 HM-14（#103） | 契約第 1.2 節 HM-14 那段；HM-14 筆記第 3.7 節 | 筆記沒有英文句子；n8n 的 `run.py` 也用 `make_apps`，同樣適用 |
| A5 HM-31（#105） | HM-31 筆記第 8 節（各產品下一版 CHANGELOG 的句子） | 原文照抄，`#NNN` 換成 `#105` |
| A6 HM-09 追補（#106） | HM-09 追補筆記結論與第 4 節 | 原文照抄；n8n 的 `run.py` 也用 `HealthMonitor` |
| B1 #81 | `git diff d1cfd6c^1 d1cfd6c -- packages/mcp-admin-core/mcp_admin_core/ha_role.py`；`addons/headscale/CHANGELOG.md` 0.4.14；計畫 §8.4（「六支在最新 Core 上面板現在就是 403」） | `4966f40` 的 `_HA_VERSIONS` 到 2026.10.4 為止；沒審過的版本由 `ui.unreviewed_core_page` 顯示、log 記一行，「MCP endpoints do not use this check」 |
| B2 #77 | `git diff 069b681^1 069b681 -- packages/mcp-admin-ui/src/contracts.js` 的 `policyRestartNotice` | 只在 `policyRestartProducts`（EMQX、LiteLLM、Nextcloud，加上 #77 新增的 Headscale）顯示 |
| H1 #85 | HM-33 筆記第 13 節（審查 MF-1 附的建議稿）；`git diff b68e437^1 b68e437 -- apps/hermes` | 原文照抄；create 的 POST 多送 `"paused": not enabled` |
| H2 HM-33（#115） | HM-33 筆記第 13 節 | 原文照抄 |
| E1 #87 | `docs/provenance/emqx-sql-write-hint-parity-20261112.md`；`git diff 14578a7^1 14578a7 -- apps/emqx` | tag、annotations、標題三處；`POST /rule_test`、handler、輸出 schema、閘道的分類沒改 |
| E2、L1 HM-32（#113） | HM-32 筆記第 12 節 | 原文照抄；使用者 2026-11-17 02:3x 的原決定是照樣記一行、寫明行為不變 |
| D1 #86 | `docs/provenance/headscale-opendesign-output-schema-parity-20261112.md`；`git diff 3f1c292^1 3f1c292 -- packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` | `tool_snapshot.py` 第一段（第 3636 行）改的是 OpenDesign 的 `read_file`（#86 之前的檔裡 `LISTED['opendesign']` 在 3567～3677 行），其餘 11 段是 Headscale |
| 第 4 節（看不到的片） | 計畫 §3.3、§7.1；各片筆記的結論（HM-04、HM-05、HM-07、HM-08、HM-09、HM-10、HM-11、HM-12、HM-12 面板、HM-14、HM-17、HM-20、HM-30） | 每片筆記都寫「產品沒開通時……不變」或對未開通產品「無」 |
| 第 5 節（發版時要另外驗） | 計畫 §11.5、§11.3；HM-05 筆記第 11 節；HM-06 筆記第 12.3 節；HM-13a 筆記第 3.5、11 節；HM-17 筆記第 12 節；契約第 5 節「HM-19c 放行條件」；`docs/operations/release.md` | — |
| 第 6 節（還沒合併的片） | `origin/feat/ha-multiprofile-hm13b-20261116`、`-hm13c-20261116`、`-hm16-20261116`、`-hm27-20261117` 的筆記（唯讀看） | HM-13b 筆記交 HM-18 的「各產品 CHANGELOG 的還原標記段落改成新行為」；HM-13c 筆記交 HM-19a 的 CHANGELOG 一行 |

## 6. 沒列進來的變更與理由

| 合併 | 內容 | 為什麼沒列 |
|---|---|---|
| #76 `e2108f6` | 0.4.13 的升版 PR | 來源 `4966f40` 已在映像裡；之後只多紀錄 commit `0913611` |
| #77 `069b681`（B2 以外） | Headscale add-on | 共用檔只為 Headscale 加表項（產品清單、欄位、遷移、`owner_defaults`、工具清單）；`plan_migration` 多的檢查只擋不在 `LEGACY_TOOLS` 的產品；`tool_snapshot.py` 的 n8n 那段只是字串換行不同、內容相同 |
| #78 `1b45bdf` | Headscale 容器驗收 | 只改 `packaging/container_probe.py`，不在映像裡 |
| #79 `c744be5` | Headscale 0.4.13 的紀錄 | 只有文件 |
| #81 `d1cfd6c`（B1 以外） | Headscale 0.4.14 | `serverInfo` 改報 `product_version`；別的產品拿到的值仍是 `VERSION`，沒變 |
| #82 `5a81309` | Headscale 密鑰網址的 Origin 限制 | 只有 Headscale 給 `secret_path_allowed_origins`，別的產品是 `None`；`headers.getlist("origin")` 和原本的判斷對它們結果相同。Headscale 0.4.16 已發 |
| #83 `659ad84`、#84 `abc0f2f`、#88 `bb48449` | Headscale DNS 改法、0.4.17、0.4.18 | 只改 `apps/headscale` 與 Headscale 的版號；已發 |
| #86 `3f1c292`（D1 以外） | Headscale 11 支工具的輸出 schema | 0.4.18 已發 |
| #89 `64fef65`、#96 `a1b54f5`、#117 `907bd39` | HM-00 與兩次文件同步 | 只有文件 |
| #90 `65727a1` | HM-01 守門測試與預檢工具 | 只改 `tests/`、`scripts/`，不在映像裡 |
| #92 `56f22f7` | HM-17 發版基礎 | 不在映像裡；清單第 4.1 節（影響發版步驟，第 5 節第 6 點） |
| #100 `51bc4b7` | CI 上限 60 分鐘 | 只改 workflow 與 `decisions.md` |
| 每個合併的 `docs/provenance/` | 各片筆記、帳本摘要 | 映像整包帶 `docs/provenance/`，但執行期不讀它（`apps/`、`packages/` 裡只有註解提到）；只是文件，不寫 CHANGELOG（HM-32、HM-33 筆記同樣結論）。本筆記也會進之後的映像 |
| #108、#109、#112、#116 | HM-13b、HM-16、HM-13c、HM-27 | 還沒合併，不在 `claude-delivery`；清單第 6 節列合併時要改的地方 |
| 草稿 PR #80 | `claude-delivery` → `main` | 不是變更來源 |

## 7. 本機檢查（2026-11-17，一般使用者）

| 檢查 | 怎麼跑 | 結果 |
|---|---|---|
| HM-00 對照 C1～C9 | 把 `artifacts/…/wave0/hm00-check/` 的腳本複製到暫存區（`check_hm00.py`、`sources.py`、`paas_cases.py`、`ast_same.py` 的 SHA-256 和 `SHA256SUMS` 相同）再跑：`python3 -I -B check_hm00.py --repo <clone> --artifacts <artifacts> --paas <唯讀 PaaS worktree> --base origin/claude-delivery --source-base bb48449` | 基準 `907bd39`（還沒有變更）：只有 C1 不過（0 個檔）、C2～C9 PASS。本片第一個 commit 之後：**C1～C9 全部 PASS**（C1：4 個檔都在 `docs/`；C2 117 列；C7 管理 API 31 個代碼、問題無）。PaaS worktree 跑前跑後 `git status` 都乾淨 |
| 秘密預檢 | `.venv/bin/python -I scripts/secret_precheck.py --tools <暫存區>/hm01/gitleaks-tools --repo . --base origin/claude-delivery --head HEAD --full`（TMPDIR 指到暫存區，跑完是空的） | gitleaks 8.28.0（釘版已驗）；本片的 commit、HEAD 整棵樹與整個歷史：`result: OK, 0 findings` |
| 帳本預檢 | `.venv/bin/python -I scripts/ledger_precheck.py --repo . --base origin/claude-delivery` | `runtime-patches.json` 177、`runtime-sources.json` 70、`tool-surface.json` 159，0 漂移、0 缺；改到的檔沒有列管檔；`result: OK` |
| 雙向控制字元 | 暫存區的小腳本掃 U+061C、U+200E、U+200F、U+202A～U+202E、U+2066～U+2069（先用一個含 U+202E 的字串確認它抓得到） | 改到的 5 個檔、commit 訊息都是 0 |
| 和還沒合併的 PR 會不會多衝突 | `git merge-tree --write-tree` 把 #108、#112、#116 的分支分別和 `claude-delivery`、本分支合 | 三個分支本來就和 `claude-delivery` 在契約有 2 處衝突（第 9 節附近與第 10 節表尾）；和本分支一樣是那 2 處，第 1.2 節加的那段合得進去。#109 兩邊都沒有衝突 |
| pytest | 沒跑 | `tests/`、`packaging/`、`scripts/` 沒有讀這些文件的程式 |

本筆記加進來之後，兩個預檢、雙向控制字元與 C1～C9 在最後的 HEAD 再跑一次，結果相同（commit 2 個、檔 5 個）。

## 8. 交主對話（repo 外的字與要決定的事；本片沒改）

1. 計畫 §3.3「不受開關管」表少兩列：HM-14 的子程式 initialize 錯誤遮罩、HM-09 追補（#106）。契約第 1.2 節有這兩項，清單也列了（A4、A6）。
2. 計畫 §11.5 第三點（2026-11-17 加的那條）可以補一句：清單在 repo 的 `docs/multi-profile/unreleased-changes.md`，升版前照它核對，
   不受開關管的片合併時在那裡加一項。
3. 要不要在 `AGENTS.md`（repo 根目錄，不在 `docs/`）加一行指向清單：其他工作線發版時第一個讀的是它。本片只改了 `docs/operations/release.md`。
4. 要請負責人決定：HM-31 的預算常數是暫定，契約第 5 節的「HM-19c 放行條件」寫「不過就不能發版」。HM-31 不受開關管，任何產品下一版都會帶出去；
   HM-19c 量測之前，其他產品的修補版要不要先量（清單第 5 節第 5 點只寫「先請負責人決定」）。
5. 可以告訴負責人：Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud 的 0.4.13 在 HA Core 2026.11.x 上管理面板拒絕每個請求（計畫 §8.4 也寫了），
   下一版（B1）才接受 2026.11.0、2026.11.1。Hermes 0.4.13 的 `enabled=false` 排程建出來其實是啟用的，下一版（H1）才修好。
6. HM-32、HM-33 筆記的英文句子沒寫本 repo 的 PR 號（#113、#115）；各產品 CHANGELOG 的前例會寫 `(PR #nn)`。要不要加由發版片定，清單已註明。
7. B2（#77 的面板文字）只是文字變短，清單標「要不要寫由發版片定」。

## 9. 只在 CI 跑的、`checks` 秒數

- `checks` 全套（pytest 以 root、0 skip，node、Playwright、`packaging/unit.sh`）：只改 `docs/`，預期和基準一樣。
- `readiness`、`Upgrade comparison`、`Release train`：不改版號，預期照舊通過。
- `checks` 秒數：CI 跑完再補。
