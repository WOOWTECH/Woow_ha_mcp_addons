# n8n 試點：從已審 commit 到 HAOS 的逐步程序

**狀態：程序提案。截至 2026-10-04 沒有任何映像建置、container 執行、registry 推送或 HA 安裝。**
P0 已在本機執行；P1 起每一步都要對應批准（見各步「前提」）。真實建置、模擬測試、HAOS 實測分開記錄，
不互相替代。驗收項目定義以 [acceptance](acceptance.md) 為準，本文只排定順序、命令與停止點。

## 基準

| 項目 | 值 |
|---|---|
| 候選 source commit | `34f06d838c5a1a18dbf623a071fbede0644ef5c0`（B3 checkpoint，71/184 工具）——要建置的程式 |
| 交付工具 commit | `local/claude-delivery` 上審查通過的 commit——只提供 `source_bundle.py`、`context_closure.py` 兩支工具，**不進入**候選 checkout |
| 產品 | n8n，version `0.1.0`，amd64 only；公開 slug `woow_mcp_n8n`；**試點**是本地 app `woow_mcp_n8n_pilot`，安裝後顯示為 `local_woow_mcp_n8n_pilot` |
| 映像 | 本地 tag `local/mcp-n8n:0.1.0`；`config.yaml` 公開名 `ghcr.io/woowtech/amd64-mcp-n8n:0.1.0`（**未發佈**） |
| Ports | Ingress `8099`（容器內、無 host mapping）；MCP `8081/tcp: null`（預設不對 LAN 開） |
| 資料 | `/data/mcp`，uid/gid 10001，0700／0600；`backup: cold` |
| 權限 | 僅 `homeassistant_api: true`（n8n 試點路徑 A 已批准）；`hassio_api`/`auth_api` false；protection on |

commit 換了就從 P0 重來，舊 commit 的證據不能批准新映像。

**兩種 SHA 不可混用。** 候選 source commit 決定 checkout 與建置內容；交付工具是另外核對過 sha256 的獨立副本，
放在 checkout 之外（下稱 `<tools>`），只讀候選 checkout、不寫入、不改 build context。候選 `34f06d8` 本身沒有這兩支
工具，不要把它們複製進 checkout，也不要為了有工具而改用別的 commit。若日後交付工具已合入新的候選並經審查，
就以那個新 commit 為基準重做 P0，舊證據不沿用。

`<tools>` 的準備：從交付工具 commit 取出兩檔（純 Python 標準庫，無其他依賴），記錄每檔 sha256，與協調者
公布的值比對一致後才使用。

## P0 — 私有 source bundle（本機，已執行）

```sh
python3 <tools>/source_bundle.py create <repo> <候選 SHA> <新的空目錄>
```

只把該 commit 的完整可達歷史打包在單一 ref `refs/heads/candidate` 下；在一次性 bare clone 中建立，
共用 repo 不新增 ref。git 以無 system/global config、無 hooks、新 HOME 執行。輸出 bundle（0600）
與 `source-receipt.json`（commit、tree、sha256、bytes）。bundle 只含 objects/refs，沒有 config、
hooks、remote 或憑證。傳送僅限批准的私有管道，**不公開 push**。

## P1 — builder VM 收取 source

前提：Q1 批准的私有、可銷毀 amd64 VM（自有 Docker Engine＋Buildx docker driver、無生產憑證／路由）。

```sh
python3 <tools>/source_bundle.py verify woow-mcp-<sha12>.bundle <候選 SHA> source-receipt.json <新的空 checkout 目錄>
```

驗 sha256、bundle 只有那一個 ref 且指向該 SHA、`fsck --strict`、HEAD 與 tree 一致、工作樹乾淨。
任何一項失敗：停止，不改用其他來源。`verify` 一律用 `<tools>` 的副本，不取自 bundle 本身
（不能用待驗內容驗證自己）。

## P2 — 靜態與單元關卡（VM，候選 checkout 根目錄）

```sh
python packaging/validate.py                    # 候選自帶
python3 <tools>/context_closure.py .            # 外部工具，產品清單讀自候選 packaging/inputs.json
uv sync --frozen --no-dev --python python3.13
.venv/bin/python -m unittest discover -s packaging -p 'test_*.py' -v
sh packaging/unit.sh
```

除 `context_closure.py` 外與 CI `unit` job 相同。`context_closure.py` 是**模型檢查**：以 moby 的
`.dockerignore` 父目錄比對規則，對 git 追蹤檔與其文件所列的 Dockerfile 子集，確認 COPY 來源在 context 內；
超出子集的寫法直接報 unsupported。它不是完整 Docker 語義實作，也不能取代 P3 真實建置或證明 context 無秘密。

## P3 — 建置（VM）

等同 CI `images` job 的 build-push-action 設定（default builder、root context、單一 amd64、load、不 push、
不產生 attestation）：

```sh
docker buildx build --builder default --platform linux/amd64 --load \
  --provenance=false --sbom=false \
  -f apps/n8n/Dockerfile --build-arg BUILD_VERSION=0.1.0 \
  --label org.opencontainers.image.revision=<SHA> \
  -t local/mcp-n8n:0.1.0 .
docker image inspect local/mcp-n8n:0.1.0 --format '{{.Id}}'
```

記錄 image ID、建置時間、Engine/Buildx/BuildKit 版本、實際 CPU/RAM/磁碟峰值。build 失敗：
保留完整錯誤，修正走 review，不改 base digest／lock 來「讓它過」。

## P4 — 真 container 驗收（VM）

```sh
python3 packaging/container_acceptance.py n8n local/mcp-n8n:0.1.0
```

`--network none --read-only`、tmpfs `/data`，跑真正 packaged entrypoint 與 owned fake backend。
這一步是 **CONTAINER/MOCK**，不是 HA 或真 backend 證據。

## P5 — 供應鏈掃描（VM）

```sh
python3 packaging/install_scanners.py <scanners 目錄>
python3 packaging/supply_chain.py candidate n8n <scanners 目錄> <evidence 目錄>
```

同一已測 image ID 的 source/history/all-layer secret、SBOM、CVE、license。finding 如實保留，
不改 allowlist 或規則。之後 VM 上不得再 build 同一 tag。

## P6 — 送到 HAOS（方向已定；registry／權限仍待批准）

方向已定（協調者 Q2 決定）：私有 registry＋本地 pilot app＋不在 HA 重建。仍待批准：registry host／namespace、
推送權限、Supervisor 拉取憑證，以及 H1–H4 每一步。細節與每步回復以 [私有映像交付設計](n8n-pilot-image-delivery.md) 為準。

把**已測 image ID**（不重建）推到私有 registry 的 commit 專屬路徑；推送後依
[私有映像交付設計](n8n-pilot-image-delivery.md) 核對：config digest 等於 P3 的 image ID，由已驗證 config
讀出的 `rootfs.diff_ids` 等於 P5 `subject.json`；manifest layer digest 是壓縮 blob 的 hash，只核對 registry 自洽，不與 diff_ids 比。
試點 HA 的 Supervisor 加一組唯讀、短效拉取憑證（=H1，需單獨批准）。

限制：Supervisor 依 `image:version` tag 拉取，不是 digest；app API 也不回報 image ID／digest。所以路徑推送後
不得覆寫，安裝前後各讀一次 manifest digest；這只證明 registry 引用未變，**HA 實際運行的 image 身分仍未直接建立**，
報告須分開列出。

明確不做：經 SSH add-on 在 HA 主機 `docker load`（等同使用生產 Docker socket）；在 HA 上重建（選項 C）
只能當最後手段，且產物不是已測映像，要另外標記、不算 P3–P5 的證據。

## P7 — HAOS 安裝前檢查（唯讀）

前提：Q3 確認目標機、時段、受限非正式 n8n API key 的供應管道。

- 記錄 HAOS／Supervisor／Core 版本；已安裝 app 清單中沒有 `local_woow_mcp_n8n_pilot`，`/addons/woow_mcp_n8n_pilot/`
  目錄不存在（若已存在，停止並確認來源，不覆蓋）。
- 確認 8081 若要對 LAN 開放，選定的 host port 沒被占用（既有 n8n 用 5678）。
- 確認有可用的近期完整備份（不是由本程序建立整機備份）。
- 只讀 Supervisor/Core API；不重啟 Core／Supervisor、不動既有 n8n/Odoo/EMQX/Hermes/OpenDesign。

## P8 — 安裝新 Add-on（只此一個）

依設計逐步、各自批准：H1 加唯讀拉取憑證 → H2 把產生的試點變體目錄複製到 `/addons/woow_mcp_n8n_pilot/`
→ H3 安裝並啟動 `local_woow_mcp_n8n_pilot`（全新、隔離的資料）。不新增 store repository。每步之前確認前一步的證據。檢查：

- 日誌沒有 token／Authorization／backend body。
- 三種健康分開：管理、MCP child、backend（未設定 backend 時 readiness 503 屬預期，不設 watchdog）。
- `/data/mcp` 擁有者與權限符合；Ingress 面板只對 admin 出現。

## P9 — HA 實測矩陣（逐項記錄，不以 tools/list 判定完成）

| # | 項目 | 通過條件 |
|---|---|---|
| 1 | Ingress admin | 真 HA owner/system-admin 開面板：導覽、API、重新整理、deep link 正常 |
| 2 | Ingress non-admin | 非管理員直接開 Ingress URL／API 被拒；需新增測試帳號另提變更請求 |
| 3 | 設定 | GUI 填 backend URL/受限 key、產生 token；重啟後仍在、options 不覆寫 |
| 4 | Bearer | 缺／錯／撤銷 token 被拒；重新產生後舊 token 失效 |
| 5 | MCP E2E | 同機 client 與一個 LAN client：initialize→initialized→tools/list→無副作用 tools/call，回應來自真 n8n |
| 6 | 寫入防護 | 未授權的寫入工具直接 tools/call 被拒，真 n8n 端無變化 |
| 7 | 生命週期 | 重啟 Add-on、受控 backend 斷線（只斷本 Add-on 的設定，不停 n8n）、child 退出後有界重啟 |
| 8 | 備份還原 | 只對本 Add-on 做 cold backup→還原；token/owner/權限驗證，之後輪替 token |
| 9 | 升版／回復 | 需要第二個已測版本，待 0.1.1 候選；本輪若無則標 NOT RUN |
| 10 | 資源 | 實測 CPU／RSS／映像大小／冷啟動／首呼叫與 p50/p95 |

## 回復

只回復本次新增的部分（設計 H4），每步各自確認：

1. 停止 `local_woow_mcp_n8n_pilot`。
2. **解除安裝會刪除它的 `/data`。** 解除安裝前必須：(a) 取得負責人明確的書面確認；(b) 先完成受控 export 或該 app
   的 cold backup（含秘密，限制保存位置與人員），並記錄 opaque backup ID；(c) 記下資料保留或銷毀的決定。
   三項缺一就不解除安裝，維持停止狀態。這不是可選步驟。
3. 解除安裝 → 刪除 `/addons/woow_mcp_n8n_pilot/` 並重新載入本地 app 清單（H2 回復）。
4. 移除 Supervisor 的試點 registry 憑證並確認清單中已無此項（H1 回復），撤銷該 registry 憑證本身。
5. 撤銷受限 n8n API key 與發出的 MCP token。

既有服務、Core、Supervisor、k3s 均未被修改，不需回復。

## 證據紀錄格式

每步：UTC、步驟 ID、SHA、image ID/digest、命令、exit code、預期／觀察、證據檔位置、標記
（LOCAL／CONTAINER-MOCK／HA／PUBLIC）。不得記錄 token、Authorization、backend body、state 內容、
cookies、Ingress session URL 或備份內容。
