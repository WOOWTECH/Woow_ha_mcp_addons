# n8n 試點：私有映像交付設計（Q2 選項 B）

**狀態：只有設計。** 沒有建立 registry、沒有推送、沒有變更 Supervisor 或 HA 檔案。registry 位置、
推送權限和 Supervisor 設定變更都還沒批准。本文接在 [n8n-haos-pilot](n8n-haos-pilot.md) 的 P6–P8。

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
| `version` | `0.1.0` | `0.1.0-pilot.<sha12>` |
| `image` | `ghcr.io/woowtech/{arch}-mcp-n8n` | `<私有 registry>/<namespace>/amd64-mcp-n8n` |

已知後果（需協調者接受）：

- 本地 app 的 slug 與日後 store 版本不同，**試點資料不會自動延續**到正式安裝。試點結束後移除。
- image 內 label `io.hass.version` 仍是 `0.1.0`。Supervisor 依 manifest `version` 拉 tag，重貼 tag 不改
  image ID。這點在 P8 實際安裝時需確認 Supervisor 不拒絕；若拒絕，停止並回報，不重建映像來對齊 label。
- 試點版本字串含 commit，所以**每個候選 commit 一個新 tag**，不覆寫舊 tag。

產生方式（之後實作，現在不寫程式）：`packaging/` 下的產生器只讀公開 manifest＋translations，
套上上表四欄，輸出到 evidence 目錄（不在 repo 內），並以 `validate.py` 的同一套規則檢查，只有
`image`／`slug`／`version`／`name` 四欄允許依上表不同。產生器不接網路、不讀憑證。

## 交付 receipt

`delivery-receipt.json`（不含任何憑證或 registry 帳號），把以下欄位綁在一起：

| 欄位 | 來源 |
|---|---|
| `commit`、`tree` | P0 `source-receipt.json` |
| `image_id`、`diff_ids` | P5 `subject.json` |
| `ref` | `<registry>/<namespace>/amd64-mcp-n8n:0.1.0-pilot.<sha12>` |
| `manifest_digest_after_push` | 推送後讀回的 manifest digest |
| `manifest_digest_before_install`、`manifest_digest_after_install` | P8 安裝前後各讀一次 |
| `manifest_config_digest` | 必須等於 `image_id` |
| `variant_config_sha256` | 產生的試點 `config.yaml` |
| `haos`、`supervisor`、`core` 版本 | P7 唯讀查詢 |

三次讀到的 manifest digest 必須一致，且 config digest 等於 `image_id`。任一不符：停止，不安裝或立即停用。
限制：HA 端無法直接讀已安裝 container 的 image ID，所以身分是靠「唯一 tag＋三次 digest 一致」間接保證。

## 步驟分類

### 只在 repo／VM 內（不碰 HA）

| ID | 動作 |
|---|---|
| R1 | 產生試點變體與 `variant_config_sha256` |
| R2 | VM 上把已測 image ID 打上唯一試點 tag 並推送；讀回 manifest，比對 config digest＝image_id、layers＝diff_ids |
| R3 | 寫 `delivery-receipt.json` 的推送部分 |

R2 需要 registry 推送權限（**未批准**）；推送用的憑證只在一次性 VM 內、用完即銷毀，不進 HA。

### 會變更 HA／Supervisor（每一步都要另外批准）

| ID | 變更 | 回復 |
|---|---|---|
| H1 | Supervisor 新增一組**唯讀、短效**的 registry 拉取憑證 | 移除該 registry 項目，再確認清單中已無此項 |
| H2 | 透過檔案分享把試點變體目錄複製到 HA 的 `/addons/woow_mcp_n8n_pilot/` | 刪除該目錄，重新載入本地 app 清單 |
| H3 | 安裝並啟動 `local_woow_mcp_n8n_pilot` | 停止並解除安裝（會刪除它的 `/data`，先依 P9 #8 決定是否保留受控備份） |
| H4 | 試點結束 | H3 → H2 → H1 的回復依序執行，撤銷該 registry 憑證本身，撤銷受限 n8n key 與 MCP token |

H1–H4 都不重啟 Core／Supervisor，不改既有 app、不碰既有 n8n／Odoo／EMQX／Hermes／OpenDesign。
H2 需要 HA 上已有的檔案分享管道；若只能透過 SSH add-on，只做檔案複製，不執行 docker 指令。

## 待協調者決定

1. registry 位置與 namespace（私有 GHCR package 或內部 registry），以及推送／唯讀拉取憑證的供應方式。
2. 是否接受「本地 app＋不同 slug」的試點方式及資料不延續的後果。
3. H1–H4 的批准方式（一次批准整組或逐步批准）與時段。
