# 本地與部署驗收矩陣

本表是驗收契約，不是通過報告。核准規格優先；僅 amd64，七類獨立 Add-on。

| ID | 可本地驗證 | 外部 gate / 不可代替的證據 |
|---|---|---|
| A01 | 首次安全 bootstrap、0600 檔案、0700 目錄、原子寫入、重啟保留 GUI 設定 | HA `/data` 重啟與備份還原 |
| A02 | 格式/版本錯誤 fail closed；migration 保留設定；未支援版本拒絕 | 真實升級/回復及敏感備份存取 |
| A03 | MCP 與 admin listener 隔離；偽造 Ingress header 不得跨 listener | HA 管理員與非管理員、實際 gateway source |
| A04 | 缺失/錯誤/撤銷 Bearer、所有 MCP session 方法均拒絕 | 真實 client 已開連線與 rotation |
| A05 | 直接呼叫 disabled/write/unknown tool 拒絕且 upstream 呼叫計數為零；畸形/批次/notification 旁路 | 每類真實無副作用 call |
| A06 | 預設唯讀；mixed-action 工具逐參數分類，未知操作拒絕 | 來源實作對照與 least-privilege backend |
| A07 | 本地 MCP initialize → initialized → list → safe call，session header / SSE forwarding | 同機 Pi/Omnigent/Hermes 與 LAN client 各自實測 |
| A08 | Ingress prefix 靜態資源/API/導覽/重新整理；explicit client endpoint | HA iframe 真實登入、角色與瀏覽器畫面 |
| A09 | 管理/child readiness/backend 三狀態；child crash/backoff/budget/signal/descendants | HA watchdog、backend 斷線不重啟迴圈 |
| A10 | runtime/backend secrets 不出現在 API 普通回應/log/build context | image layers/Git history/release artifacts 敏感掃描 |
| A11 | 七份配置/固定版本/amd64/root context/最小權限 lint；CI gate | 七映像建置與固定 digest、GHCR 發佈 |
| A12 | 來源 allowlist/provenance/license/NOTICE/依賴 lock | 授權審核通過才可公開 repo/image |
| A13 | 本機資源/延遲量測方法與樣本 | 目標 HA CPU/RSS/延遲真實測量 |
| A14 | 繁中文件、client 範例、changelog、rollback/backup runbook | 操作者按照文件完成安裝驗收 |

每個報告必須區分：程式測試、映像建置、HA 安裝、MCP E2E。Mock/fake backend 僅是本地測試，絕不當真實後端成功。未完成欄位保留未驗證，不填空成功。
