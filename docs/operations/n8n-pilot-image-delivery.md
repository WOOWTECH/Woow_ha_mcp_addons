# n8n 試點：私有映像交付設計（Q2 選項 B）

**狀態：設計＋離線工具。** registry 位置已決定（Gitea，見下節）；尚未推送、未變更 Supervisor 或 HA 檔案。
專用推送／拉取 token 與 H1–H4 每一步仍待批准。本文接在 [n8n-haos-pilot](n8n-haos-pilot.md) 的 P6–P8。

## 目標與不變條件

1. HAOS 跑的必須是 P3–P5 測過、掃描過的**同一個 image ID**；不在 HA 上重建、不在 VM 上重建同一 tag。
2. 公開 store manifest（`addons/n8n/config.yaml`、`image: ghcr.io/woowtech/{arch}-mcp-n8n`）不改。
   試點變體不進 repo 的 store 目錄，避免被 Supervisor 當成正式產品發現。
3. 每個會變更 HA／Supervisor 的步驟都有對應的移除步驟，且只影響本試點新增的東西。

## 試點 manifest 變體

用 HA 的**本地 app**（`/addons/<dir>/config.yaml`，帶 `image`）安裝，而不是新增 store repository：
不需讓 Supervisor 存取私有 Git；Supervisor 對本地 app 也會依 `image` 拉取，不在本機建置。

與公開 manifest 的差異只限這幾欄，其他欄位（權限、ports、ingress、`backup: cold`、`init`、`apparmor`
等）逐字相同：

| 欄位 | 公開 manifest | 試點變體 |
|---|---|---|
| `name` | `WOOW n8n MCP (experimental)` | 加上 `(pilot <sha12>)` |
| `slug` | `woow_mcp_n8n` | `woow_mcp_n8n_pilot`；安裝後 Supervisor 顯示為 `local_woow_mcp_n8n_pilot` |
| `version` | `0.1.0` | `0.1.0`（**不改**，與映像 label `io.hass.version` 一致） |
| `image` | `ghcr.io/woowtech/{arch}-mcp-n8n` | `<私有 registry>/<namespace>/pilot-<sha12>/amd64-mcp-n8n`（每個候選 commit 一個路徑） |

已知後果（需協調者接受）：

- 本地 app 的 slug 與日後 store 版本不同，**試點資料不會自動延續**到正式安裝。試點結束後移除。
- 版本不改的原因（已查 inputs.json 釘的 Supervisor `2026.09.3` commit `64ea3be`）：`DockerInterface.install`
  只依 manifest `version` 拉 `image:version`，`check_image` 只比對架構，安裝不讀 label；但備份還原
  `supervisor/apps/app.py:1696` 以 `self.instance.version`（即 image label `io.hass.version`）比對備份中的
  `version`，不同就重新拉映像。若 manifest 改成 `0.1.0-pilot.*` 而 label 仍 `0.1.0`，每次還原都會走
  這條重拉路徑，還原行為與正式版不同。所以維持 `0.1.0`，改用 **registry 路徑**區分候選，
  同一 artifact 不必重建、label 與 version 一致。路徑一經推送不再覆寫；新 commit 用新路徑。
- 試點內的升版測試（P9 #9）需要真正的新版本（例如 0.1.1 候選），不是改路徑。

產生方式（之後實作，現在不寫程式）：`packaging/` 下的產生器只讀公開 manifest＋translations，
套上上表四欄，輸出到 evidence 目錄（不在 repo 內），並以 `validate.py` 的同一套規則檢查，只有
`image`／`slug`／`version`／`name` 四欄允許依上表不同。產生器不接網路、不讀憑證。

## 交付 receipt

`delivery-receipt.json`（不含任何憑證或 registry 帳號），把以下欄位綁在一起：

| 欄位 | 來源 |
|---|---|
| `commit`、`tree` | P0 `source-receipt.json` |
| `image_id`、`diff_ids` | P5 `subject.json` |
| `ref` | `<registry>/<namespace>/pilot-<sha12>/amd64-mcp-n8n:0.1.0` |
| `manifest_digest_after_push` | 推送後讀回的 manifest digest |
| `manifest_digest_before_install`、`manifest_digest_after_install` | P8 安裝前後各讀一次 |
| `config_digest` | manifest 的 config descriptor digest，必須等於 `image_id` |
| `config_diff_ids` | 由已驗證 config blob 讀出的 `rootfs.diff_ids`，必須等於 `subject.json` 的 `diff_ids` |
| `layer_digests` | manifest 的 `layers[].digest` 與 mediaType；**只**與 registry blob 核對，不與 diff_ids 比 |
| `variant_config_sha256` | 產生的試點 `config.yaml` |
| `haos`、`supervisor`、`core` 版本 | P7 唯讀查詢 |

兩種 hash 不可混用（[OCI Image Spec v1.1.0 config](https://github.com/opencontainers/image-spec/blob/v1.1.0/config.md#layer-diffid)、
[manifest](https://github.com/opencontainers/image-spec/blob/v1.1.0/manifest.md)）：DiffID 是**未壓縮** layer tar 的 digest，
manifest `layers[].digest` 是依其 mediaType 儲存的 blob（通常壓縮）的 digest。核對順序：

1. 讀 manifest 原始 bytes，sha256 必須等於回應的 manifest digest；mediaType 必須是預期的單一平台 image manifest。
2. 依 config descriptor 取 config blob，sha256 必須等於 descriptor digest，且等於 `image_id`。
3. 從這份已驗證的 config 讀 `rootfs.diff_ids`，與 `subject.json` 的 `diff_ids` 逐項相等。
4. 每個 layer descriptor：GET 取回 blob bytes，自行重算 sha256 與 size，與 descriptor 相符；這只證明 registry
   內容自洽，不拿來和 diff_ids 比。只做 HEAD 時，只能記為「registry 宣告的 digest／size metadata 相符」，
   **不是** blob bytes 已獨立驗證；receipt 對每個 layer 標明 `bytes-verified` 或 `metadata-only`。

任一不符：停止，不安裝或立即停用。

### 驗收缺口（必須明列）

上述只證明「registry 上這個引用指向已測映像且推送後未變」。**HA 實際在跑的 image 身分沒有直接證據**：
釘選 Supervisor 的 app API（`supervisor/api/apps.py`）回 `version` 等欄位，沒有 image ID 或 digest；
目前也沒有批准的 Docker 層查詢（不連生產 Docker socket）。所以 P9 報告要分開寫：
「registry 引用未變：已證明」、「安裝後 runtime image 身分：**未直接建立**」。若之後有平台提供且經批准的
精確查詢，再補這一項；不得以三次 digest 一致宣稱整體身分驗收通過。

## 步驟分類

### 只在 repo／VM 內（不碰 HA）

| ID | 動作 |
|---|---|
| R1 | 產生試點變體與 `variant_config_sha256` |
| R2 | VM 上把已測 image ID 打上該 commit 專屬路徑的 `0.1.0` tag 並推送；依上節 1–4 核對（config digest＝image_id；已驗證 config 的 diff_ids＝subject；layer blob 只核對 registry 自洽） |
| R3 | 寫 `delivery-receipt.json` 的推送部分 |

R2 需要 registry 推送權限（**未批准**）；推送用的憑證只在一次性 VM 內、用完即銷毀，不進 HA。

### 會變更 HA／Supervisor（每一步都要另外批准）

| ID | 變更 | 回復 |
|---|---|---|
| H1 | Supervisor 新增一組**唯讀、短效**的 registry 拉取憑證 | 移除該 registry 項目，再確認清單中已無此項 |
| H2 | 透過檔案分享把試點變體目錄複製到 HA 的 `/addons/woow_mcp_n8n_pilot/` | 刪除該目錄，重新載入本地 app 清單 |
| H3 | 安裝並啟動 `local_woow_mcp_n8n_pilot`（全新、隔離的資料目錄） | 停止。解除安裝會刪除它的 `/data`，**必須先取得明確確認**，並先做受控 export／cold backup（含秘密，限制保存） |
| H4 | 試點結束 | 經逐步確認後依 H3 → H2 → H1 回復，撤銷該 registry 憑證本身、受限 n8n key 與 MCP token |

H1–H4 **逐步**檢查與批准：每一步各自的前提、證據與回復，不是整組一次放行。「試點」不代表可以自動刪除
資料；試點資料不會轉入日後正式 store 安裝，需要保留時用 export／backup 處理。

H1–H4 都不重啟 Core／Supervisor，不改既有 app、不碰既有 n8n／Odoo／EMQX／Hermes／OpenDesign。
H2 需要 HA 上已有的檔案分享管道；若只能透過 SSH add-on，只做檔案複製，不執行 docker 指令。

## 私有 registry（專案負責人 2026-10-05 決定：Gitea）

- Registry：`git-prod.woowtech.io`（Gitea 內建 container registry，`/v2/` 回 registry/2.0）。
  Namespace：`ha-components`（與私有原始碼 repo 同 org）。試點 ref：
  `git-prod.woowtech.io/ha-components/pilot-<sha12>/amd64-mcp-n8n:0.1.0`。若首次推送時 Gitea 不接受
  巢狀名稱，改用扁平名稱 `amd64-mcp-n8n-pilot-<sha12>`，並同步改 `pilot_variant.py` 的 image 規則後重新審查。
- 推送憑證（R2）：專用 Gitea access token，權限只有 `write:package`，只在一次性 builder VM 內
  `docker login --password-stdin` 使用，推送後 `docker logout` 並撤銷該 token。不使用個人全權限 token，
  不寫入 repo、訊息或證據。
- 拉取憑證（H1）：另一個只有 `read:package` 的 token，設進試點 HA 的 Supervisor registry；
  試點結束時移除並撤銷。
- 套件預設私有（跟隨 org），推送後確認匿名 `/v2/` 讀取仍為 401。
- 公開 GHCR 仍要等原有的 release gates；GitHub 與 Gitea 原始碼鏡像不等於映像也互為鏡像。

## 待協調者決定

1. 上述兩個專用 token 的建立與交付方式（由專案負責人在 Gitea UI 建立，以 `!` 直接寫入 VM，不經對話）。
2. H1–H4 逐步批准的時段與每步核准人；試點目標 woowtech-ha 需先恢復連線（10-05 起 Cloudflare tunnel 1033）。
