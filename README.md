# WOOW HA MCP Add-ons（實驗封裝，尚未發佈）

六個獨立產品：Odoo、n8n、Hermes、OpenDesign、EMQX、LiteLLM。

**Odoo Manage 已於 2026-10-06 下架封存**：0.1.4 是最後一版，0.1.5 起不在商店，也不再建置或發佈。已安裝的仍以 0.1.4 執行，但不會再有更新或安全修正；它的設定保有 Odoo API key，並有 `homeassistant_api` 權限，建議改用 WOOW Odoo MCP 後移除。WOOW Odoo MCP 是不同的 MCP server（工具與設定不同，要另設後端、endpoint 與 token）。已發佈的 0.1.0–0.1.4 映像保留，舊備份仍可還原。步驟見[更新、備份與回復](docs/operations/update-backup-rollback.md)；原始碼保留在 `apps/odoo-manage`。
僅以 **amd64 / Supervisor 2026.09.3** 為封裝目標；不是 Core 最低版本。
Kubernetes MCP 與 Vibe Kanban 不在範圍。

**現在不可當作可用商店產品安裝：**

- 六個商店產品各有 runtime（封存的 Odoo Manage 原始碼也還在）；只開放部分有界支援的工具，不是完整功能遷移。逐名對照與數量見 [工具表](docs/tool-surface.md)。
- 六份 `addons/*/config.yaml` 可被 Supervisor 探索，不代表 GHCR 名稱已取得、映像已存在或可匿名拉取。此批 **未建置映像、未做 HA／真實後端 E2E**。
- **本地整合 ≠ HA／映像驗收**：僅新 n8n 試點獲准 `homeassistant_api: true`，正式 fixed-WS provider 已實作並經 component review；共用管理 HTML/static/API 與 v3 UI 已本地串接。其餘六類仍 false，正式管理 fail closed。`panel_admin` 不是授權。
- 此例外授予**廣泛 Core 管理能力**（含使用者管理及可能間接 Supervisor／host 影響），不是可強制的唯讀角色權限；不代表批准所有 HA 變更。`hassio_api/auth_api` 仍 false、Supervisor role 預設、protection mode 不變，無新增 host 權限。
- 核准 verifier 契約：固定 `ws://supervisor/core/websocket`／`config/auth/list`，只用 n8n 管理程序 runtime token；敏感操作前 fresh role query、無正向快取，缺失／降權／停權／timeout／錯誤一律 fail closed。本地實際 bootstrap→OS guard→n8n→provider 與 Chromium 已用 owned fake WS／test-only Ingress 模擬驗證；整合獨立規格及新安全審查仍待完成，HA **NOT TESTED**；不可注入 trust bypass。
- 發佈須經獨立規格、新安全審查、來源／授權／秘密／映像／HA 關卡及 `public-release` 人工批准。`RELEASE-GATES.json` 預設全部 false。

## 文件

- [繁體中文操作與限制](docs/operations/guide.md)
- [同機／LAN client 與 Bearer 範例](docs/operations/clients.md)
- [手動更新、備份、migration、回復](docs/operations/update-backup-rollback.md)
- [故障驗收與證據格式](docs/operations/acceptance.md)
- [建置、CI、發佈關卡](docs/operations/release.md)
- [授權範圍與第三方通知](THIRD_PARTY_NOTICES.md)

各產品 `addons/<product>/DOCS.md`、`CHANGELOG.md`、`translations/zh-Hant.yaml`
提供獨立工具數、連線欄位、風險與更新狀態。一台 HA 可分別選裝，每個 Add-on
一組後端、獨立 token／資料／版本；不宣稱多租戶或同產品多 profile。

## 管理功能與範圍

[共用 UI](packages/mcp-admin-ui/README.md) 提供各產品 typed connection 的保留／完整替換／清除、
三維健康、明確 client endpoint、確認式 token reveal/rotate/revoke。Manage 支援 read/module；
module 必須已在後端安裝，UI 不安裝 Odoo 模組。工具頁對齊實際 v3 exact grants，
保存取代全部 `enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；未知或過期契約拒絕保存。
原兩個 legacy writers 的有效 global 授權如實顯示，不讓 global false 靜默保留隱藏 writes。
B1 新增 Odoo 三個純 preview builders 與 partner counts、Manage counts/template metadata/internal note、n8n local validators 與安全 inactive draft create。新 writer `post_message`／`n8n_create_workflow` 必須 exact grant，舊全域開關不授權；詳見 [B1 範圍](docs/tool-expansion.md)。
B2 增加有界 Odoo metadata/品質統計；B3 增加 n8n tags、execution metadata、service status 與 folder get（操作不另計工具名）。B3 待獨立 SPEC → NEW SECURITY；詳見 [有界契約](docs/tool-expansion.md)。
113 個延期工具是透明的內部功能／安全設計 backlog，不是已完成完整產品遷移。

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
docker build --platform linux/amd64 -f apps/n8n/Dockerfile -t local/mcp-n8n:0.1.0 .
"$PACKAGING_ENV/bin/python" packaging/container_acceptance.py n8n local/mcp-n8n:0.1.0
```

PR/main CI 沒有發佈權限；固定六產品 matrix `push: false`。HA 無法以 Add-on
子目錄重建這些 root-context Dockerfile，必須等待已核准預建映像。預設手動啟動、
手動更新、不使用 latest、不開公網，protection mode 保持開啟。
