# n8n 試點：逐步指令（公開 repo＋公開映像）

**狀態：2026-10-05 n8n 試點已依本文執行；之後其他支也以同樣方式從商店安裝（slug 換成 `_woow_mcp_<product>`），
現況見 [0.1.5 回歸紀錄](ha-test-0.1.5.md)。** 2026-10-05 專案負責人決定公開 repo 與 GHCR 映像，試點改走 HA 商店安裝，不再需要
私有 registry 與權杖（舊的私有路線見 [私有映像交付設計](n8n-pilot-image-delivery.md)，已停用）。
每個 H 步驟仍要先取得負責人對「那一步」的批准。`ha` 指令在試點 HA 的 SSH add-on 內執行。

## 0. 前提

- 要安裝版本的映像 `ghcr.io/woowtech/amd64-mcp-<product>:<version>`（試點時是七支 0.1.0；目前是六支 0.1.5）已公開，
  且匿名 manifest digest 與 supply-chain gate 證據一致（`packaging/registry_gate.py public <product> <evidence>`）。
- repo `https://github.com/WOOWTECH/Woow_ha_mcp_addons` 已公開。
- P7 唯讀檢查在試點當天重跑（版本、無同名 app、8081 未佔用）；近期完整備份存在。
- n8n API key 由管理員在 n8n 介面建立（Settings → n8n API），試點時直接填進本 add-on 的設定頁，不經對話。

## 1. H1 加入商店 repository（HA，需批准）

```sh
ha store add "https://github.com/WOOWTECH/Woow_ha_mcp_addons#claude-delivery"
ha store reload
ha store --raw-json | jq -r '.data.repositories[] | select(.url | test("Woow_ha_mcp_addons")) | "\(.slug) \(.url)"'
```

已安裝者維持這個網址：Supervisor 以網址決定 repository slug（這個網址是 `1ee8889c`），換網址（例如拿掉 `#claude-delivery`
會變成 `f1d622e7`）就換 slug，已安裝的 app 不會原地更新；要改網址需另做資料遷移計畫（見[更新、備份與回復](update-backup-rollback.md)）。
2026-10-07 時 GitHub 預設分支是 `claude-delivery`；`main` 仍停在 0.1.0 之前的 B3 checkpoint `34f06d8`，不要用 `#main`。
回復：`ha store delete <repository slug>`。

## 2. H2 安裝與啟動 n8n add-on（HA，需批准）

```sh
SLUG=$(ha store --raw-json | jq -r '.data.addons[] | select(.slug | endswith("_woow_mcp_n8n")) | .slug')
ha apps install "$SLUG" && ha apps start "$SLUG"
ha apps info "$SLUG" --raw-json | jq '.data | {state, version, image, ingress_url}'
ha apps logs "$SLUG" | tail -50
```

Supervisor 依 `image:version` 拉取；安裝前後各以匿名 registry 讀一次 manifest digest，須與 gate 證據相同。
日誌不得出現 token／Authorization／backend body。

## 3. 設定（HA Ingress 面板）

管理員開啟面板，backend URL 填 `http://<n8n app hostname>:5678`（同台 HA 的 n8n app 內部主機名，
可由 `ha apps info <n8n slug>` 的 hostname 取得），API key 貼上 n8n 建立的 key，產生 MCP token。
MCP client 端點：同機用 app 內部主機名的 8081，LAN 需另外對應 8081/tcp。

## 4. P9 實測

依 [試點程序](n8n-haos-pilot.md) P9 矩陣逐項記錄；只用無副作用工具；寫入防護測試要確認 n8n 端無變化。

## 5. H3 收尾與回復（每步各自確認）

1. `ha apps stop "$SLUG"`
2. 解除安裝會刪除它的 `/data`：先取得負責人明確確認，並完成該 app 的 cold backup
   （`ha backups new --apps "$SLUG" --name ...`），記錄 backup slug 與保留決定。
3. `ha apps uninstall "$SLUG"`；`ha store delete <repository slug>`
4. 在 n8n 撤銷試點 API key；記錄實際中斷時間與結果。

既有 n8n、Core、Supervisor、k3s 均未修改。
