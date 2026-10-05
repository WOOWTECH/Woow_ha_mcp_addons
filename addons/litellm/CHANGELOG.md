# LiteLLM Changelog

## 0.1.1 — 準備中（未發佈）

- HA 管理權限 `homeassistant_api: true`（負責人 2026-10-05 核准，與 n8n 相同的固定 WebSocket 角色驗證），讓 HA owner／system-admin 能在 Ingress 面板設定後端；須等核心 provider 交付並審查後才發佈。
- bootstrap 把 runtime `SUPERVISOR_TOKEN` 交給本產品管理程序（僅此一個變數，child 不繼承），供 HA 管理角色驗證使用。
- 修正 HA 還原本 Add-on 後資料變成 root 擁有、無法啟動的問題：bootstrap 只在資料剛好屬 root 時，檢查後一次改回 10001 與 0700／0600（待 SPEC＋安全審）。
- 新增五個有界 metadata 讀取工具（Pi 候選 cf7fea1）；全套回歸尚有 3 項失敗待修。
- 映像 `ghcr.io/woowtech/amd64-mcp-litellm:0.1.1` 尚未建置；0.1.0 tag 不覆寫。

## 0.1.0 — 2026-10-05 公開（experimental）

- 新增獨立 amd64 root-context 封裝、Supervisor 2026.09.3 安全子集 manifest。
- runtime：FastMCP 3.4.5 / pinned public vendor；40 個來源工具中支援 7，33 個明列 withheld，
  [工具對照](../../docs/tool-surface.md) 尚未完成功能平齊。
- 8099 Ingress-only／8081 可選 LAN／3000 loopback；保護模式、init true；不設
  backend-dependent watchdog、不開 HA/Supervisor/Docker API 權限。
- 共用 UI 已本地整合，exact grants/typed forms 已接 Core；本產品正式角色路徑仍封鎖；未建置 image、未做 HA E2E。
- 資料 v3：完整 v1/v2 migration、新增空 exact grants；UI 保存完整 grants+global false，disabled 優先，其他產品不可匯入 n8n state。
- 手動更新前做受控 cold backup（只中斷本 Add-on，含秘密）；rollback 必須使用相容
  image+完整資料，不可盲目 downgrade。請見 [完整步驟](../../docs/operations/update-backup-rollback.md)。
- 授權／公開去密／映像／實際 backend／Ingress/client／備份還原驗收仍待批准。
