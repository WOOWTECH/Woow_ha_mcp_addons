# LiteLLM 0.5.1（2026-11-25 維修版）發佈紀錄（草稿）

狀態：**草稿：映像尚未建置、尚未推 GHCR、尚未驗收**（待補：run、digest、展示機結果）。這是 `woow_mcp_litellm` 一個產品的發版：版號 0.5.0 → 0.5.1，與 Odoo 0.5.2、EMQX 0.5.1、Nextcloud 0.5.1、n8n 0.4.15、Hermes 0.4.15、Headscale 0.4.20 同一批 2026-11-25 維修版（一個升版 PR、各產品各自的 `release.yaml` run）；OpenDesign 只升來源版本，沒有映像。
合併升版 PR 即上架 WOOW App Store；合併前只補這份紀錄與驗收紀錄（只改 `docs/`）。

## 為什麼發這一版

LiteLLM 0.5.0 的管理員驗證只認到 HA Core 2026.11.2；Core 2026.11.3（HA 穩定頻道 2026-11-25 的預設版）上管理面板拒絕每個請求（MCP 端點不經這項檢查，不受影響）。這一版審過 2026.11.3（25 個契約與相鄰檔和 2026.11.2 逐位元相同；`docs/ha-role-core-contract.md`），並自動放行已審查月份（2026.7 到 2026.11）的後續修補版：版本字串要剛好是 `年.月.修補`，該年該月已有審過的版本，修補號大於該月審過的最大修補號；新的月份、預覽版與其他格式照舊 403（DQ-35；不受開關管；八個產品，OpenDesign 的來源也算，用同一份驗證器）。另外，面板把 Cloudflare 這類代理改成的弱 ETag 當成同一個版本（A11，F2：Odoo 0.5.1 驗收發現，經 Cloudflare 開 HA 時「瀏覽器來源檢查」卡片不能儲存）。

負責人 2026-11-25 的決定：選「今天發維修版」、「同月份修補版自動放行」，火車 B（Hermes、Headscale、n8n 一起開通多帳號）選「三個一起，照建議做」；發佈核准與合併沿用 2026-11-23「整套一次授權」（每個產品過完所有關卡才發佈；GitHub 的發佈核准以 API 代按，改版號 PR 也代為合併，每一步回報）。火車 B 的多帳號開通不在這一批，各自另有版號與發佈紀錄。

## 範圍

- **只有 LiteLLM**（`woow_mcp_litellm`）：LiteLLM 走自己的版號線（`VERSION_OVERRIDES`，DQ-32）：0.5.0 → 0.5.1；共用預設版號 `VERSION` 這一批從 0.4.14 升到 0.4.15（n8n、Hermes，以及 OpenDesign 的來源版本）。
- 不在範圍：Hermes、Headscale、n8n 的多帳號開通（火車 B）；`features.MULTI_PROFILE_PRODUCTS` 這一批不動（維持 `{'odoo', 'emqx', 'litellm', 'nextcloud'}`）；OpenDesign 與 Odoo Manage 不開放多帳號（DQ-28）。
- 路線：這條線只用 GitHub（`.github/workflows/release.yaml`：gate → candidate → publish，publish 在 `public-release` environment 核准，只收 `release/*` 分支）。

## 來源

- 分支 `release/maintenance-20261125`（基準 `claude-delivery` `092b1b5`，#136 合併之後），PR #138（主對話推上去時的 head 是 `3bcfa1f`；升版 commit 與這些紀錄之後另外推）。分支上依序有：HA Core 2026.11.3 審查與同月份修補版放行（`529c8c0`、`131d1a9`）、面板讀弱 ETag（`635f800`、`40574ce`）、EMQX 說明對齊 PaaS #160（`806df82`、`d214e2b`、`48c2e2e`、`3bcfa1f`），再來是升版 commit（版號資料與測試釘選、CHANGELOG、DOCS／README、未發佈清單與這七份發佈紀錄草稿；commit 號合併後補）。
- Node 基底 26.12.1 → 26.13.1（`f988a5f`，在 `80ed536` 之後，上面那串 commit 寫成時還沒有它；文件與 CHANGELOG 的對應句在其後的 commit）：n8n 的候選映像在供應鏈關卡被 Node 26.12.1 執行檔的 7 個 High 漏洞擋下（CVE-2026-123863、123864、123865、123866、123872、123874、126051；26.13.1 修掉）。這是七支共同的建置輸入變更：映像要從含它的分支 head 建。
- 映像來源：觸發 `release.yaml` 時這個分支的 head（`source_sha`，待補）。**七支都推完之前，不准再往分支推任何 commit（紀錄檔也不行）**：`workflow_dispatch` 永遠跑在分支 head，`source_sha` 又必須等於它（[release](release.md)「部分失敗怎麼辦」）。都推完之後的證據 commit 只加紀錄檔。
- 發版鎖：同一時間只有一個凍結中的升版 PR（計畫 §11.5）；觸發前要再查一次有沒有別的開著的升版 PR（例如火車 B）。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION`、`VERSION_OVERRIDES` | `VERSION` 0.4.15；`{'odoo': '0.5.2', 'emqx': '0.5.1', 'litellm': '0.5.1', 'nextcloud': '0.5.1', 'headscale': '0.4.20'}` |
| 2 | `packaging/inputs.json` 的 `version`、`version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `VERSION`、`PRODUCT_VERSIONS` | 同上；帳本 `runtime-patches.json` 的摘要與 `change` 同步（`scripts/ledger_precheck.py` 0 漂移） |
| 4 | `addons/litellm/config.yaml` 的 `version` | `0.5.1` |
| 5 | `apps/litellm/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.1` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的六路運算式：`<app> == 'odoo' && '0.5.2' || <app> == 'emqx' && '0.5.1' || <app> == 'litellm' && '0.5.1' || <app> == 'nextcloud' && '0.5.1' || <app> == 'headscale' && '0.4.20' || '0.4.15'` |
| 7 | `docs/operations/release-decision-litellm-0.5.1.md` | 本檔（推 GHCR、展示機驗收之後補證據） |

- **運算式本機求值**（`packaging/test_validate.py` 的規則，`&&` 先於 `||`）：`odoo`→0.5.2、`emqx`／`litellm`／`nextcloud`→0.5.1、`headscale`→0.4.20、`n8n`／`hermes`／`opendesign`→0.4.15，`ci.yaml` 與 `release.yaml` 兩組結果相同；`packaging/validate.py` 通過。六路形式在火車 A（2026-11-24）的候選建置（emqx、litellm、nextcloud 各一次）已被 GitHub 算對（tag 檢查通過）；這一批的形式相同、只有值不同，但 odoo、headscale 那兩路與落到預設值的 n8n、hermes 沒有在六路形式下實跑過，候選建置的 tag 檢查就是驗證（算錯時 `supply_chain.py candidate` 在推送前停，不燒版號）。
- 測試釘選：`tests/test_output_schemas.py` 的 n8n `Dockerfile` 位元組釘選換成新的 SHA-256（相對 0.4.14：`ARG BUILD_VERSION` 的預設值，加上 Node 基底的兩處 `FROM` 與一處 `node --version` 檢查，見下一條；沒有工具、schema 或 handler 的改動）；`packaging/test_validate.py` 沒有釘選要改。
- **Node 基底映像**（不是版號，但同一批換）：`packaging/inputs.json` 的 `bases.node` 與 `native_addons.better-sqlite3.node`、9 個 `apps/*/Dockerfile` 的 `FROM node`（n8n 兩處，另有複製後的 `node --version` 檢查）、`ci.yaml`／`release.yaml`／`woow-addon-release.yml` 的 `setup-node` 版本與三處 `node --version` 檢查、`packaging/validate.py` 的同一組字串、`tests/test_boundary.py` 與 `packaging/test_j1900_check.py` 的 Node 版本字串：26.12.1 → 26.13.1（`f988a5f`）。基底摘要 `sha256:28147155…` → `sha256:0042e17d…`（multi-arch index，匿名 Docker Hub 取得，等於 `Docker-Content-Digest`；linux/amd64 子 manifest `40168539…`，config `603e1397…` 宣告 `NODE_VERSION=26.13.1`；映像裡的 `/usr/local/bin/node`（sha256 `d931c649…`）與官方 `node-v26.13.1-linux-x64.tar.xz` 的 `bin/node` 逐位元相同）。Node ABI 仍是 147（nodejs.org `dist/index.json`），better-sqlite3 預建檔的網址、sha256、大小不變；官方 26.13.1 執行檔在本機載得進它並跑 FTS5。證據全文在 `packaging/inputs.json` 的 `evidence`。 這個產品的最終映像沒有 Node.js：Node 基底只用在面板建置階段，面板輸出（`packages/mcp-admin-ui/dist`，443 個檔）用 26.12.1 與 26.13.1 的官方執行檔各建一次，逐位元相同（本機驗證，不是映像建置本身）。摘要與基底掃描的細節見 [n8n 的紀錄](release-decision-n8n-0.4.15.md)。

## 內容（寫進 CHANGELOG 的項目）

項目編號（A8～A11、E4）是 [未發佈清單](../multi-profile/unreleased-changes.md) 的編號；這一批寫進 CHANGELOG 之後，那份清單把它們移掉，原來的建議句、看得到的變化與出處見 `3bcfa1f` 的那份（A11 的事實已照 2026-11-25 的實測改正，留在清單裡）。

- **A10**：同 Odoo。
- **A11**：同 Odoo。
- **文件**：0.5.0 CHANGELOG 的字樣更正為已發佈（映像 digest 與驗收結果，數字抄自 `release-decision-litellm-0.5.0.md`）。
- 其餘（多帳號行為、工具、`/data/mcp` 的檔案）和 0.5.0 相同：0.5.0 的映像來源 `84483b7` 到這個分支，共用執行期程式只多 A10、A11（`ha_role.py`、`ui.py`、面板 `api.js`）；`tool_snapshot.py` 裡 EMQX 的一段工具說明（E4）也會進這個映像，對這個產品沒有作用，沒有別的差異。

## 驗收計畫

| # | 步驟 | 結果 |
|---|---|---|
| 1 | 推送分支、開 PR | PR #138 已開（head `3bcfa1f`）；升版 commit 推上之後的 head 待補 |
| 2 | 獨立安全審查（DQ-35 的條件） | 已做：2026-11-25 修正後通過；必修 4 項（文字與紀錄）已處理，建議 2 項交負責人決定，見 [審查筆記](../provenance/ha-core-later-patch-review-20261125.md) |
| 3 | CI：`checks`、`Release train`、`Upgrade comparison`（`compare`、`runtime`） | 待補 |
| 4 | 候選建置與容器驗收（`release.yaml` 的 gate → candidate：容器驗收含子程式 bearer 401 與 HM-13a 還原樹、多帳號階段；source／history／全部 layer 的 Gitleaks、SBOM、Grype、授權） | 待補（run、`image.tar` SHA-256、image ID） |
| 5 | J1900 指令集檢查（candidate job 內建，QEMU `-cpu Nehalem`） | 待補 |
| 6 | Store 升級乾跑（展示機，0.5.0 → 候選 `image.tar`；兩個 phase 都要撐過 60 秒、不退出、不重啟） | 待補 |
| 7 | 推 GHCR（`public-release` 核准後的 publish） | 待補（run、manifest digest、image ID） |
| 8 | PR 檢查：映像發佈後重跑 `readiness` 與 `Upgrade comparison` | 待補 |
| 9 | 展示機 HAOS 升級測試（Store 上的 0.5.0 → 發佈的映像；真後端，升級後設定與權杖保持、管理面板可用；展示機的 Core 若維持 2026.7.2，只驗沒有退步，2026.11.3 與後續修補版的放行由單元測試涵蓋） | 待補 |
| 10 | 合併上架 | 待補 |

待補：run、digest、展示機結果。

## 已知限制與事實

- **展示機的 Core 版本與真 Core 驗證**：`ha_role` 已用真的 Core 2026.11.3、2026.11.2、2026.11.0（PyPI 官方套件，前面接 Supervisor 代理替身）驗過（[審查筆記](../provenance/ha-core-later-patch-review-20261125.md)第 5 節）；沒有真的 2026.11.4 以上的 Core。這個 add-on 映像沒有在真的 Core 2026.11.x 的 HA 上跑過：展示機維持 2026.7.2 時只驗沒有退步，2026.11.3 與後續修補版的放行由單元測試（`tests/test_ha_role.py`，含窮舉 2025～2027 年的版本字串）與上面的真 Core 驗證涵蓋；要在 HA 上驗證需另外的 Core 2026.11.3 環境，由負責人決定。
- **經 Cloudflare 的 ETag（A11 的實測）**：2026-11-25 在真的 HA 加 Cloudflare 上量（瀏覽器的 `Accept-Encoding: gzip, deflate, br, zstd`）：`api/origin-policy`（94 位元組）被 Cloudflare 壓成 br、ETag 變弱，所以「瀏覽器來源檢查」卡片不能儲存（這個維修版修好）；`api/profiles`（161 位元組）由 Home Assistant 自己先壓 gzip、ETag 維持強，帳號清單在這條路上不受影響；只有前面的代理改寫 HA 沒壓縮的回應時才可能變弱（例如用戶端不收壓縮）。面板送出時照舊送強的 `If-Match`，add-on 的比對沒有放寬。
- **A10 是權限檢查的改動**：放行的版本沒有逐版審查，add-on 紀錄每個版本每個程序記一行；下一次發版再補審並列入清單。最壞情況、偵測、回復與今天實際的曝險範圍（規則對每個已審月份都成立，但 HA 已不再出舊月份的修補版，實際只在 2026.11.4 起）見 [ha-role-core-contract](../ha-role-core-contract.md)「Later patch releases of a reviewed month」。

## 發版前的關卡（草稿時列的阻擋事項）

1. **A10 的獨立安全審查（DQ-35 的條件）**：已做（2026-11-25，審查者不是作者），修正後通過：程式不用改，必修 4 項是文字與紀錄，已處理；建議 S4、S5 交負責人決定（規則要不要只對 2026.11 起生效、面板要不要顯示被規則放行的版本）。另外，主對話用真的 Core 2026.11.3、2026.11.2、2026.11.0 跑過 `ha_role`（維修版 67／67、30／30、30／30 全過）。見 [審查筆記](../provenance/ha-core-later-patch-review-20261125.md)。
2. **映像尚未建置**：這份草稿寫成時，沒有建置、沒有推 GHCR、沒有展示機驗收；上面的表每一格都要等實際執行後補。
3. **`upgrade-notes.yaml`**：這一批沒有加；`Upgrade comparison / compare` 要求時照 `AGENTS.md` 第 3 點補。
4. **發版鎖與 PR head 凍結**：七支（或當批要發的各支）候選都通過之後才批准任何一支的 publish；之後的 commit 只加紀錄檔。

## 本機檢查（一般使用者；以 GitHub CI 為準）

- 2026-11-25，分支 head `fc87b34`（版號資料、CHANGELOG、DOCS／README、獨立審查的修正與紀錄都已在內；之後的 commit 只動這些發佈紀錄），一般使用者、Python 3.13、Node 26.12.1、`/tmp/ha-mp-*` 短 TMPDIR（用完刪除）。這台機器同時有別的對話在跑測試（負載 6～8、可用記憶體約 3 GB，共用測試鎖要排隊），計時的案例不可靠，沿用火車 A 紀錄的寫法，以 GitHub CI 為準。
- 沒有失敗的（在 `fc87b34`）：`packaging/validate.py` 通過；packaging 單元測試 378 案過（5 skip，都是 `test_entrypoint` 要 root 的案例）；`scripts/ledger_precheck.py` OK（三份帳本 0 漂移；所有產品相依與 n8n 的 `node_modules` 都裝好，沒有「需要 CI 安裝」的項目）；`scripts/secret_precheck.py`（gitleaks 8.28.0，釘版）對 `092b1b5..fc87b34` 的 19 個 commit 0 命中；面板 Node 測試 122 過；七份發佈紀錄都滿足 `packaging/release_gate.py` 對紀錄的規則（檔名、add-on slug 與版本，用它的 `own_record` 逐一驗過）；這個分支相對 `3bcfa1f` 改動的 44 個 Markdown 檔的相對連結全部有效。
- pytest：在 `72dcdc9` 跑了 24 個檔（有釘版號或讀文件的檔、還原守門與還原提示、請求限制、真子程式與真 n8n）共 1,671 案：1,651 過、20 失敗，分類在下面。`72dcdc9` 之後動到程式或測試的只有 `ui.py` 的一句靜態頁文字、`tests/test_ha_role.py`（一條新斷言、兩個新案例）與三個面板測試相關檔（`profiles.test.mjs`、`profiles.spec.mjs`、`fixtures/server.mjs`）的註解，所以 `tests/test_ha_role.py` 在 `fc87b34` 又整份跑了一次：350 案全過（30 秒；含上面「真 n8n」那 1 案，是用同一個放在 repo 外的外掛抵銷主機名稱與 Node 路徑兩項主機事實之後跑的；排隊等共用鎖時整份重跑過一次，不是失敗）。其餘 23 個檔沒有被這些改動碰到，沒有重跑。
- 20 個失敗都不是這次修改造成的，這次只動版號、文件、測試釘選與審查要求的小修：
  - 5 案要 root：`test_restore_detection` 的 `test_root_*`（CI 以 root 跑，非 root 會故意失敗）。
  - 10 案是這台機器的兩個主機事實，測試的寫法決定了它們在這裡過不了，CI 的 runner 兩項都沒有問題。其一是主機名稱解析到 `127.0.1.1`：`test_real_products` 把假後端綁在 `socket.gethostbyname(socket.gethostname())`（Headscale 與開通多帳號的產品的 child 拒絕回圈位址，所以要綁私有位址），這裡拿到的是回圈位址；EMQX、LiteLLM、Nextcloud 回 `*_DESTINATION_DENIED`，Headscale 回 `executable listener not proved`（4 案）。其二是 Node 不在測試寫死的 `PATH=/usr/bin:/bin`：`test_ha_role` 的真 n8n 1 案、`test_real_n8n` 3 案、`test_unconfigured_connect` 的 n8n 2 案（6 案）。用一個放在 repo 外的 pytest 外掛只抵銷這兩項事實（把這台的主機名稱改解析成私有位址、把 Node 的目錄補進寫死的 PATH；測試與產品程式碼都沒改）重跑這 10 案，全過（235 秒），所以這個歸因有實跑證據，不只是讀程式。
  - 4 案是 CPU 計時：`test_request_structure` 的 `test_the_scan_costs_what_the_limit_allows_not_what_the_body_holds`、`test_closers_after_balanced_structure_are_bounded_too`，以及 `test_a_closing_bracket_flood_does_not_stall_the_scan` 的其中兩個參數（兩輪失敗的組合不同）。16 MiB 輸入的掃描在這台機器上單獨量是 0.27～0.30 秒（門檻 0.3），「balanced then closers」穩定 0.38 秒。`request_limits.py` 與這個測試檔都和 `092b1b5` 逐位元相同，這次修改沒有碰。
  - 1 案偶發：`test_restore_review` 的 `test_revoke_all_revokes_every_profile_and_starts_every_child_again`（記憶體吃緊時額外帳號因 `memory_capacity` 沒起；單獨重跑通過）。
- 沒跑的：全套 pytest（約 40 分鐘，交給 CI）、Playwright 瀏覽器測試（本機沒有 Chromium；`3bcfa1f` 的 CI 是 168 過；之後只有上面三個面板測試相關檔的註解變了，都用 `node --check` 驗過語法）、需要 root 的 `packaging` 測試案例（上面的 5 skip）。
- 2026-11-25，`f988a5f`（Node 基底 26.12.1 → 26.13.1）之後重跑：上面 `fc87b34` 那條寫「之後的 commit 只動這些發佈紀錄」，到 `80ed536` 為止是對的，`f988a5f` 動了 Dockerfile、workflow、`packaging/` 與兩個測試檔。Node 用官方 26.13.1 執行檔（與映像裡的逐位元相同，放在 PATH 最前面；本機原本的 Node 是 22）。結果：`packaging/validate.py` 通過；packaging 單元測試 378 案過（5 skip，要 root）；`scripts/ledger_precheck.py` 三份帳本 0 漂移；面板 `npm test` 122 案過；pytest `tests/test_output_schemas.py` 189 案過（含 n8n Dockerfile 的新位元組釘選）、`tests/test_boundary.py` 與 `tests/test_n8n_catalog_copy.py` 共 51 案過（含真的 Node 26.13.1 載入釘版 better-sqlite3、n8n-mcp 用 `BetterSQLiteAdapter` 的那一案）。沒重跑：其餘 pytest 檔（`fc87b34` 以前的結果照舊）、Playwright、要 root 的案例；映像沒有建置，所以建置期的 `node --version` 檢查與複製後的函式庫載入要等 CI。
