# WOOW HA MCP Add-ons（實驗版，已公開發佈）

六個獨立產品：Odoo、n8n、Hermes、OpenDesign、EMQX、LiteLLM。目前版本 **0.1.5**（2026-10-06 發佈；映像
`ghcr.io/woowtech/amd64-mcp-<product>:0.1.5`，來源 `0c66bd0`；[發佈紀錄](docs/operations/release-decision-0.1.5.md)）。

**Odoo Manage 已於 2026-10-06 下架封存**：0.1.4 是最後一版，0.1.5 起不在商店，也不再建置或發佈。已安裝的仍以 0.1.4 執行，但不會再有更新或安全修正；它的設定保有 Odoo API key，並有 `homeassistant_api` 權限，建議改用 WOOW Odoo MCP 後移除。WOOW Odoo MCP 是不同的 MCP server（工具與設定不同，要另設後端、endpoint 與 token）。已發佈的 0.1.0–0.1.4 映像保留，舊備份仍可還原。步驟見[更新、備份與回復](docs/operations/update-backup-rollback.md)；原始碼保留在 `apps/odoo-manage`。
僅以 **amd64 / Supervisor 2026.09.3** 為封裝目標；不是 Core 最低版本。
**管理面板支援的 Core 版本**：只在該版 add-on 審查過的 HA Core 版本運作（0.1.6：2026.7.2–2026.9.4 與 2026.10.0；0.1.5 及更早只有 2026.7.2）；
其他版本（含之後的 patch 與 beta）整個管理面板都回 403，看起來和「不是管理員」完全一樣（add-on 紀錄也沒有訊息）；
MCP 端點（Bearer token）不受影響。新的 Core 版本要等 add-on 發新版才支援，升級 Core 前請先對照這份清單。
Kubernetes MCP 與 Vibe Kanban 不在範圍。

**目前狀態與限制（experimental）：**

- 六個商店產品各有 runtime（封存的 Odoo Manage 原始碼也還在）；只開放部分有界支援的工具，不是完整功能遷移：六支合計上游 174 個工具，支援 67 個、暫不支援 107 個（工具表另列已下架的 Odoo Manage，不計入）。逐名對照見 [工具表](docs/tool-surface.md)。
- 六份 `addons/*/config.yaml` 可從本 repository 的 HA 商店安裝，映像已公開、可匿名拉取。0.1.1–0.1.5 每版都在測試 HA 回歸（[0.1.5 紀錄](docs/operations/ha-test-0.1.5.md)，之前各版見同目錄 `ha-test-0.1.*.md`）：映像身分、管理面板權限、token、五支真後端的讀取冒煙與拒寫、後端斷線、重啟、升版；LiteLLM 沒有後端，工具未測（只測了未設定後端時的拒絕與錯誤碼，見 [client 文件](docs/operations/clients.md)）。真實 MCP client（同 HA Pi／Omnigent／Hermes、LAN client、AI client）、授權寫入、n8n 以外五支的備份還原、版本回退與 aarch64 尚未驗收。
- **AI client 相容性（已知問題）**：2026-10-07 經 OpenRouter 實測，Claude、GPT 拒收 n8n、Odoo、Hermes 的工具清單（7 個工具的 `inputSchema` 頂層有 `oneOf`／`allOf`，整個請求 HTTP 400）；直連 API 與實際 client 未測。詳見 [client 文件](docs/operations/clients.md)。
- **HA 管理權限**：六支都有 `homeassistant_api: true`（n8n 自 0.1.0、其他自 0.1.1 起，負責人核准），用來確認管理面板的使用者是 HA owner 或系統管理員；測試 HA 上 owner 可用、一般使用者 403（0.1.1–0.1.5 每版實測）。`panel_admin` 不是授權。
- 此例外授予**廣泛 Core 管理能力**（含使用者管理及可能間接 Supervisor／host 影響），不是可強制的唯讀角色權限；不代表批准所有 HA 變更。`hassio_api/auth_api` 仍 false、Supervisor role 預設、protection mode 不變，無新增 host 權限。
- 核准 verifier 契約：固定 `ws://supervisor/core/websocket`／`config/auth/list`，只用各支管理程序的 runtime token（child 不繼承）；敏感操作前 fresh role query、無正向快取，缺失／降權／停權／timeout／錯誤一律 fail closed。provider 與 token 傳遞在 0.1.1 經獨立 SPEC＋安全審（[0.1.1 發佈紀錄](docs/operations/release-decision-0.1.1.md)）；登入後即時降權與瀏覽器 UI 只在本地以 owned fake WS／test-only Ingress 驗證，未在真 HA 測；不可注入 trust bypass。
- 0.1.0 起依負責人的公開決定發佈（[release-decision-2026-10-05](docs/operations/release-decision-2026-10-05.md)）：每版映像在私有 builder 通過 container 與 supply-chain gate 後，推送同一個已測 image ID（不重建），沒有經過 `public-release` workflow。`RELEASE-GATES.json` 的人工 gates 沒有改寫，仍全部 false。

## 文件

- [繁體中文操作與限制](docs/operations/guide.md)
- [同機／LAN client 與 Bearer 範例](docs/operations/clients.md)
- [手動更新、備份、migration、回復](docs/operations/update-backup-rollback.md)
- [故障驗收與證據格式](docs/operations/acceptance.md)
- [建置、CI、發佈關卡](docs/operations/release.md)
- [0.1.5 發佈紀錄](docs/operations/release-decision-0.1.5.md)、[0.1.5 HA 回歸](docs/operations/ha-test-0.1.5.md)（之前各版在同目錄）
- [授權範圍與第三方通知](THIRD_PARTY_NOTICES.md)

各產品 `addons/<product>/DOCS.md`、`CHANGELOG.md`、`translations/zh-Hant.yaml`
提供獨立工具數、連線欄位、風險與更新狀態（2026-10-07：各 DOCS.md 的延期工具數與 LiteLLM 的支援數仍是舊值、待更新，
工具數以[工具表](docs/tool-surface.md)各產品段落為準）。一台 HA 可分別選裝，每個 Add-on
一組後端、獨立 token／資料／版本；不宣稱多租戶或同產品多 profile。

## 管理功能與範圍

[共用 UI](packages/mcp-admin-ui/README.md) 提供各產品 typed connection 的保留／完整替換／清除、
三維健康、明確 client endpoint、確認式 token reveal/rotate/revoke。已下架的 Odoo Manage（0.1.4 為止）支援 read/module；
module 必須已在後端安裝，UI 不安裝 Odoo 模組。工具頁對齊實際 v3 exact grants，
保存取代全部 `enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；未知或過期契約拒絕保存。
原兩個 legacy writers 的有效 global 授權如實顯示，不讓 global false 靜默保留隱藏 writes。
B1 新增 Odoo 三個純 preview builders 與 partner counts、Manage counts/template metadata/internal note（已隨 Odoo Manage 下架）、n8n local validators 與安全 inactive draft create。新 writer `post_message`（Odoo Manage，已下架）／`n8n_create_workflow` 必須 exact grant，舊全域開關不授權；詳見 [B1 範圍](docs/tool-expansion.md)。
B2 增加有界 Odoo metadata/品質統計；B3 增加 n8n tags、execution metadata、service status 與 folder get（操作不另計工具名）。B3 已於 2026-10-04 通過獨立 SPEC 與 NEW SECURITY 審查（只核准這批有界範圍，不是 HA 或發佈驗收），0.1.0 起隨映像發佈；
詳見 [有界契約](docs/tool-expansion.md)（2026-10-07：該頁開頭仍是 184／71／113 與「B3 待審」，工具表開頭仍寫「七類」「只有 n8n
接正式 provider」，都是 0.1.1 之前的舊說明、待更新）。
六支 107 個暫不支援的工具是透明的內部功能／安全設計 backlog，不是已完成完整產品遷移。

## 本地封裝驗證

先安裝固定的共用 core 相依套件，再安裝 hash-pinned PyYAML；封裝測試會使用
真實 core 授權 schema，不能只安裝 PyYAML。從 repository root 執行（需要 uv）：

```sh
PACKAGING_ENV="$(mktemp -d /tmp/woow-packaging-check.XXXXXX)"
UV_PROJECT_ENVIRONMENT="$PACKAGING_ENV" uv sync --frozen --no-dev --python 3.13
uv pip install --python "$PACKAGING_ENV/bin/python" --require-hashes --only-binary=:all: -r packaging/requirements-ci.txt
"$PACKAGING_ENV/bin/python" packaging/validate.py
"$PACKAGING_ENV/bin/python" -m unittest discover -s packaging -p 'test_*.py' -v
# 有 Docker 的隔離 runner 才執行；root context 最後的點不可省略
# 這不是已執行的成功紀錄：
docker build --platform linux/amd64 -f apps/n8n/Dockerfile -t local/mcp-n8n:0.1.5 .
"$PACKAGING_ENV/bin/python" packaging/container_acceptance.py n8n local/mcp-n8n:0.1.5
```

PR/main CI 沒有發佈權限；固定六產品 matrix `push: false`。HA 無法以 Add-on
子目錄重建這些 root-context Dockerfile，只能使用已發佈的預建映像。預設手動啟動、
手動更新、不使用 latest、不開公網，protection mode 保持開啟。
