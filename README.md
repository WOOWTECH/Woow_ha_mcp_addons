# WOOW HA MCP Add-ons（實驗版，已公開發佈）

六個啟用的商店產品：Odoo、n8n、Hermes、EMQX、LiteLLM、Nextcloud。最新正式版 **0.3.0**（六個 per-addon stable Release 於 2026-10-24 發佈；[0.3.0 映像紀錄](docs/operations/release-decision-0.3.0.md)）。本分支準備 **0.3.1**，加入已保存／已套用設定狀態、過期編輯衝突保護，以及撤銷或輪替 token 時關閉進行中的串流；[0.3.1 發佈狀態與驗收邊界](docs/operations/release-decision-0.3.1.md)。0.3.1 的正式映像驗收與發布仍待完成。OpenDesign 原始碼保留、商店已停用，本次不建置或發布它的映像。

**Odoo Manage 已於 2026-10-06 下架封存**：0.1.4 是最後一版，0.1.5 起不在商店，也不再建置或發佈。已安裝的仍以 0.1.4 執行，但不會再有更新或安全修正；它的設定保有 Odoo API key，並有 `homeassistant_api` 權限，建議改用 Woow Odoo MCP Server 後移除。Woow Odoo MCP Server 是不同的 MCP server（工具與設定不同，要另設後端、endpoint 與 token）。已發佈的 0.1.0–0.1.4 映像保留，舊備份仍可還原。步驟見[更新、備份與回復](docs/operations/update-backup-rollback.md)；原始碼保留在 `apps/odoo-manage`。
僅以 **amd64 / Supervisor 2026.09.3** 為封裝目標；不是 Core 最低版本。

**管理面板支援的 Core 版本**：只在該版 add-on 審查過的 HA Core 版本運作（0.1.6–0.1.8：2026.7.2–2026.9.4 與 2026.10.0；0.1.9 起再加 2026.10.1；0.1.5 及更早只有 2026.7.2）；
其他版本（含之後的 patch 與 beta）整個管理面板都回 403，看起來和「不是管理員」完全一樣（add-on 紀錄也沒有訊息）；
MCP 端點（Bearer token）不受影響。新的 Core 版本要等 add-on 發新版才支援，升級 Core 前請先對照這份清單。
Kubernetes MCP 與 Vibe Kanban 不在範圍。

**目前狀態與限制（experimental）：**

- 七個原始碼產品（其中六個 Store 啟用；見 `packaging/inputs.json`）各有 runtime（封存的 Odoo Manage 原始碼也還在）。**0.2.1 起完整版**（負責人 2026-10-15 決定）：七支開放子程序的全部工具，合計 183 個，與原始 MCP server 及 PaaS woow-mcp-server 一致；全部工具與寫入預設開啟；0.3.0 的 schema 1/2/3 升級先由 HA 管理員確認預選 `all_on`，也可明確選 `preserve`；新安裝與 schema 4 的正常啟動不變，管理面板可逐一停用或取消寫入。**網址（權杖）＝完整後端權限**，後端帳號權限要設對，見 [寫入預設開啟](docs/operations/guide.md#寫入預設開啟)。0.2.2 起後端還沒設定或連不上時 client（含 Claude.ai 連接器）照樣能連線並列出全部工具，呼叫工具回錯誤說明原因（[client 文件](docs/operations/clients.md#token-事件與故障)）。逐名對照見 [工具表](docs/tool-surface.md)，轉送規則與保留的安全層見 [工具範圍](docs/tool-expansion.md)。
- 七支（odoo、n8n、hermes、opendesign、emqx、litellm、nextcloud）的顯示名稱是「Woow ○○ MCP Server」，圖示與所連接的軟體相同（來源見 [圖示來源](docs/provenance/icons.md)）。兩種安裝來源內容相同：本 repository 的 HA 商店，以及 2026-10-09 起的 [WOOW HA App Store](https://github.com/WOOWTECH/Woow_HA_App_Store)（含 ha-rebrand 的 Local Download）。兩個商店的同名 add-on 在 HA 裡是不同的 add-on（slug 前綴不同，設定與資料不互通），同一台 HA 只裝其中一個來源的。映像已公開、可匿名拉取。0.1.1–0.1.7 每版都在測試 HA 回歸（[0.1.7 紀錄](docs/operations/ha-test-0.1.7.md)，含 Nextcloud 第一次實機；之前各版見同目錄 `ha-test-0.1.*.md`）：映像身分、管理面板權限、token、五支真後端的讀取冒煙與拒寫、後端斷線、重啟、升版；LiteLLM 沒有後端，工具未測（只測了未設定後端時的拒絕與錯誤碼，見 [client 文件](docs/operations/clients.md)）。真實 MCP client（同 HA Pi／Omnigent／Hermes、LAN client、AI client）、授權寫入、n8n 以外六支的備份還原、版本回退與 aarch64 尚未驗收。
- **AI client 相容性**：0.1.5 經 OpenRouter 實測，Claude、GPT 拒收 n8n、Odoo、Hermes 的工具清單（7 個工具的 `inputSchema` 頂層有 `oneOf`／`allOf`，整個請求 HTTP 400）。0.1.6 已修正：這 7 個工具宣告的 schema 頂層改成單純的 object（驗證不變），2026-10-07 以同樣五個模型複驗六支全部接受（30/30；0.1.7 新增的 Nextcloud 沒有做這項測試）；直連 API 與實際 client 仍未測。詳見 [client 文件](docs/operations/clients.md)。
- **HA 管理權限**：七支都有 `homeassistant_api: true`（n8n 自 0.1.0、其他五支自 0.1.1 起，負責人核准；Nextcloud 於 2026-10-08 核准，0.1.7 起），用來確認管理面板的使用者是 HA owner 或系統管理員；測試 HA 上 owner 可用、一般使用者 403（0.1.1–0.1.6 每版實測；Nextcloud 尚未在 HA 實測）。`panel_admin` 不是授權。
- 此例外授予**廣泛 Core 管理能力**（含使用者管理及可能間接 Supervisor／host 影響），不是可強制的唯讀角色權限；不代表批准所有 HA 變更。`hassio_api/auth_api` 仍 false、Supervisor role 預設、protection mode 不變，無新增 host 權限。
- 核准 verifier 契約：固定 `ws://supervisor/core/websocket`／`config/auth/list`，只用各支管理程序的 runtime token（child 不繼承）；敏感操作前 fresh role query、無正向快取，缺失／降權／停權／timeout／錯誤一律 fail closed。provider 與 token 傳遞在 0.1.1 經獨立 SPEC＋安全審（[0.1.1 發佈紀錄](docs/operations/release-decision-0.1.1.md)）；登入後即時降權與瀏覽器 UI 只在本地以 owned fake WS／test-only Ingress 驗證，未在真 HA 測；不可注入 trust bypass。
- 0.1.0 起依負責人的公開決定發佈（[release-decision-2026-10-05](docs/operations/release-decision-2026-10-05.md)）：每版映像在私有 builder 通過 container 與 supply-chain gate 後，推送同一個已測 image ID（不重建），沒有經過 `public-release` workflow。`RELEASE-GATES.json` 的人工 gates 沒有改寫，仍全部 false。

## 文件

- [繁體中文操作與限制](docs/operations/guide.md)
- [同機／LAN client 與 Bearer 範例](docs/operations/clients.md)
- [手動更新、備份、migration、回復](docs/operations/update-backup-rollback.md)
- [故障驗收與證據格式](docs/operations/acceptance.md)
- [建置、CI、發佈關卡](docs/operations/release.md)
- [0.1.9 發佈紀錄](docs/operations/release-decision-0.1.9.md)、[0.1.9 HA 回歸](docs/operations/ha-test-0.1.9.md)（2026-10-11 獨立收斂審查 PASS，依主對話裁定完成原範圍驗收；窗口前根 client 登入 1 筆保留未更動、兩個 u018 probe 屬原 S5/S6 指定 runner 本輪清理範圍，原追加兩 client strict comparison exit=1 保留；推送／HA 交還以 S7/S8 實際回執為準）；[0.1.8 發佈紀錄](docs/operations/release-decision-0.1.8.md)、[0.1.8 HA 回歸](docs/operations/ha-test-0.1.8.md)；[0.1.7 發佈紀錄](docs/operations/release-decision-0.1.7.md)、[0.1.7 HA 回歸](docs/operations/ha-test-0.1.7.md)；[0.1.6 發佈紀錄](docs/operations/release-decision-0.1.6.md)、[0.1.6 HA 回歸](docs/operations/ha-test-0.1.6.md)（之前各版在同目錄）
- [授權範圍與第三方通知](THIRD_PARTY_NOTICES.md)

各產品 `addons/<product>/DOCS.md`、`CHANGELOG.md`、`translations/zh-Hant.yaml`
提供工具數、連線欄位、風險與更新狀態（工具數以[工具表](docs/tool-surface.md)各產品段落為準）。一台 HA 可分別選裝，每個 Add-on
一組後端、獨立 token／資料／版本；不宣稱多租戶或同產品多 profile。

## 管理功能與範圍

0.3.1 候選的管理面板區分設定已保存、等待套用、已套用與套用失敗；「已套用」代表目前子程序完成協定檢查，與後端服務健康分開顯示。修正初次顯示與更新套用狀態時末尾出現字面 `null` 的問題。表單帶入載入時的 revision，過期儲存回 409 並保留草稿；明確重新載入後才可再送出。管理程序重啟也需要重新載入舊表單。既有不帶 `If-Match` 的 API client 保持相容，但沒有這項衝突保護。詳細 API 與已保存但套用失敗的處理見 [runtime configuration](docs/runtime-configuration.md)。

[共用 UI](packages/mcp-admin-ui/README.md) 提供各產品 typed connection 的保留／完整替換／清除、
三維健康、明確 client endpoint、確認式 token reveal/rotate/revoke。已下架的 Odoo Manage（0.1.4 為止）支援 read/module；
module 必須已在後端安裝，UI 不安裝 Odoo 模組。工具頁依實際 metadata 顯示每個工具的停用開關與寫入授權（寫入工具一個 grant，混合工具每個寫入 operation 一個），
保存取代全部 `enabled_write_tools` 並 `writes_enabled:false`，disabled 優先；未知或過期契約拒絕保存。
0.2.1 起不再用本地有界模型（0.1.x 的 B1／B2／B3 有界範圍與輸出投影已移除，只剩已下架的 Odoo Manage 使用），見 [工具範圍](docs/tool-expansion.md)。

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
docker build --platform linux/amd64 -f apps/n8n/Dockerfile -t local/mcp-n8n:0.3.1 .
"$PACKAGING_ENV/bin/python" packaging/container_acceptance.py n8n local/mcp-n8n:0.3.1
```

PR/main CI 沒有發佈權限；固定商店產品 matrix（與 `packaging/inputs.json` 相同）`push: false`。HA 無法以 Add-on
子目錄重建這些 root-context Dockerfile，只能使用已發佈的預建映像。預設手動啟動、
手動更新、不使用 latest、不開公網，protection mode 保持開啟。
