# 執行計畫與狀態

依據：`2026-10-03-mcp-haos-approved-design.md`，三份獨立 scout 報告（保存在 repo 外的 runtime/reports，不公開 inventory），及 `acceptance-matrix.md`。

## 查證結論

- 五類來源 SHA `614ae663fadd91c76972f60017a76d2627bea87e`；既有工具設定多僅 advisory，不能直接搬用安全邊界。
- EMQX 公開 MIT source `WOOWTECH/Woow_emqx_mcp_server@1be17bad5aef6c7b7519686ccbfe1d80762bc10e`；LiteLLM 公開 MIT source `WOOWTECH/Woow_litellm_mcp_server@4d4190369216a2d068d1100d53406a67a1d81609`。不是現行 image→commit 證明。
- 目標為 Supervisor 2026.09.3 / Core 2026.7.2 / amd64。image label `io.hass.type=app`；root-context 預建 image，不能依賴 Supervisor addon-directory local build。
- `panel_admin` 是 UI 限制，Ingress user ID 並非 admin role 證明。未整合可信 HA admin-role 驗證前，管理 API 必須 fail closed；以 mock role verifier 通過測試不等於 HA 實測。
- shared legacy core/UI 授權範圍不明；Odoo Manage 0.7.1 為 MPL-2.0。禁止宣稱整體 MIT，禁止公開前跳過 clearance。
- 此環境無 Docker/Podman/Buildx，映像建置外部阻礙；本地 Python/Node 測試仍可獨立執行。

## 工作分解（循序 worker；每次成果先規格 reviewer，再全新安全/品質 reviewer）

| ID | 依賴 | 任務 / 可驗證產物 | 狀態 |
|---|---|---|---|
| S1 | 無 | 三名 scout、真實 herdr pane/dispatch 證據 | 完成；三報告完整讀取 |
| P1 | S1 | 本地新 Git、allowlist/provenance、安全忽略清單、七類目錄 | 已 init 新 repo/七目錄/.gitignore；provenance 隨實作補齊 |
| W1 | P1 | n8n test-first 共用 core/adapter；雙 listener、Bearer、call policy、原子 config、health/child lifecycle；固定 npm runtime metadata | 已交付待審；協調者重跑 57 tests exit 0，真實本機 n8n 無 backend smoke；六類契約 scout 完成 |
| R1 | W1 | 規格 review → 新安全/品質 review → 修復與重驗 | 完成本地W1雙審：schema-spec與全新security均APPROVED；各126tests exit0，security另180cancel實驗；不代表完整n8n/HA驗收 |
| W2 | R1 | 六類實際來源 adapter/固定 runtime/operation policy/test；保持共用 core/UI，不建立假 stub | W2a已交付待雙審，worker183tests；七類inventory184/支援27/defer157。W2b安全擴展待做，非完整产品完成 |
| R2 | W2 | 每次 worker 後雙 review、修復與重驗 | W2a spec reviewer執行中，之後全新security |
| W3 | R2 | 七類 HA packaging、root build、鎖依賴、CI/GHCR gated workflow、繁中文件/client/release/backup 說明、共用 Woow UI | 待執行 |
| R3 | W3 | 雙 review 與本地測試；manifest 與 scope/source hygiene | 待執行 |
| V1 | R3 | 協調者獨立跑全部本地測試與可執行 smoke、敏感資訊/來源清單稽核 | 待執行 |
| M1 | V1 | MILESTONE / BLOCKERS；分離 code/image/HA/E2E；可選本地繁中 commit | 待執行 |
| AROLE | S1 | scoped scout 查 pinned Core/Supervisor 真實最小權限 admin role 整合；有權限增加先報上游，再實作測試 | 已提出真實路徑及權限風險，UPSTREAM-APPROVAL-REQUEST待批准；不阻擋W2/W3 |
| G1 | 上游 | 映像工具/授權/憑證審核，公開 repo/push/GHCR 與 HA 安裝 | 本次禁止跨越 |

## 實作準則

1. 公開 tree 只收必要原始碼與去密 provenance，不複製 .git 歷史、原工作目錄、inventory、k8s manifests、.env/.mcp.json/憑證。
2. 選固定 child 命令與 loopback port，不允許 GUI 執行 arbitrary command；child env 最小集合。n8n 外部 token 與內部 AUTH_TOKEN 分離。
3. 共用 policy 必須解析直接 tools/call，在 dispatch 前拒絕 unknown/disabled/write/malformed。Mixed-action 未逐項稽核者整個 deny，不能猜 read-only。覆蓋 batch/notification/session 繞過。
4. Config 只 GUI 管 backend/token/policy；HA options 僅部署。版本不支援/損壞 fail closed，0600/0700/atomic/durable 寫入。秘密不回傳普通 API/log。
5. 管理入口需 socket-peer + HA admin-role 信任；缺可信 role provider 時 fail closed 並記錄 blocker，不以 panel_admin 或 header 存在冒充。
6. 管理/child/後端三狀態；backend outage 不引發 container 重啟迴圈。child 退避/budget/process-group termination/orphan 測試。
7. 每次 worker 必須給 RED/GREEN 或回歸證據、完整命令/exit code、修改檔案、未完成事項。不 commit、不擅自發布、不動原 repo。
8. 依來源能證明的 transport 宣告支援；本地假後端測試不是真實 MCP E2E。沒有來源/契約不編造工具。

## 外部阻礙（追蹤於 BLOCKERS.md）

HA admin role 的可信授權整合、Docker/Buildx、公開授權/NOTICE/SBOM與敏感掃描、Odoo exact entrypoint、實際 HA 後端/受限 test credentials、EMQX error、LiteLLM backend版本、GitHub安全 publisher及名稱權限。未知項應限制完成範圍，不停止不相依本地工作。
