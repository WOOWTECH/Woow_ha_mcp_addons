# Odoo 0.5.1（多帳號首發 R1，取代未上架的 0.5.0）發佈紀錄（草稿）

狀態：**本機提交完成，尚未推送、未建置映像**。這是 Odoo 一個產品（`woow_mcp_odoo`）的發版：版號 0.4.14 → 0.5.1。0.5.0 已推到 GHCR，
但從未上架 Store（Store 上目前是 0.4.14），使用者拿不到；0.5.1 是第一個上架的多帳號版，使用者從 0.4.14 直接升級。
發佈到 WOOW App Store 的每一步（建置、候選驗收、推 GHCR、HAOS 驗收、合併）都**待負責人批准**；本紀錄是推送前的草稿，
推 GHCR 與驗收之後再補證據（同 [0.5.0 草稿](release-decision-odoo-0.5.0.md) 的做法）。

## 為什麼是 0.5.1

- HM-19b 驗收（2026-11-23，展示機，官方 MCP TypeScript SDK 1.32.2）重現 F1：開通多帳號的 Odoo 每條 GET 事件串流整段生命週期占一張 64 MiB 回覆票券，
  串流上限被壓成票券數（預設帳號 3、額外帳號 1）。額外帳號的 SDK 用戶端自己開的常駐 GET 占走唯一一張票，它自己的 `tools/list` 與每次 `tools/call`
  都回 200＋`-32003`（外掛的回覆記憶體額度已滿）；預設帳號 5 個 SDK 用戶端時 5 次 `tools/call` 全忙碌。證據：
  `artifacts/ha-multiprofile-parity-20261114/takeover-20261123/hm19b-kit/evidence-20261123/f1sdk-*.log`、`f1-*.log`、`deviations-zh-TW.md` 第 12 項。
- 負責人 2026-11-23 決定：「修好再發 0.5.1」；HA 版只要與 PaaS／podman 功能一致（PaaS 閘道每帳號 GET 串流有自己的上限，串流開滿時 POST 照常）。
  紀錄在 [decisions.md](../multi-profile/decisions.md) 第 1.1 節。

## 範圍（相對基準 `1e9adfb`，PR #135 的頭，分支 `release/odoo-0.5.0-20261123`；只往上加提交，不改寫既有提交）

- GET 事件串流不再取回覆票券（`gateway.reply_may_hold_large_child_output` 對 GET 回 False）；串流上限回到一般名額（預設 24、額外 8），
  超過仍是 429＋`-32003`＋`id: null`＋`Retry-After: 30`；串流開滿時 POST 照常。
- 串流自己的位元組上限：`reply_memory.STREAM_BYTES`＝1 MiB（交給 server 還沒收走）、`STREAM_EVENT_BYTES`＝128 KiB（子程式單一事件）；
  超過時乾淨結束串流（用戶端重連）並記一行 WARNING（不含 token 與內容）。只在開通且用票券的 Odoo；關閉的產品、n8n 與其他產品路徑不變。
- 全域最壞記憶體算式加保留項 `request_budget.ODOO_STREAM_RESERVE_MIB`＝64（最多 24＋5×8＝64 條串流×1 MiB）：六帳號需要量 2,839 → 2,903 MiB，
  全 add-on 請求內容預算的推導同樣多扣 64 MiB。
- **不改**（已接受）：票券本身（每張 64 MiB、全域 512 MiB、預設帳號 3 張、額外帳號各 1 張、超過不排隊、POST 回 200＋`-32003`＋`Retry-After: 5`）
  照舊只用在可能帶大型回覆的 POST；HM-19c 極端壓力只記錄不擋發版；閘道核心修正（`fix/hm19c-*` 分支）不在這一版。
- 測試：`tests/test_get_stream_bounds.py`（新）、`tests/test_reply_memory.py`、`tests/test_gateway_queue_ha.py`、`tests/test_profile_quotas.py` 改成新語意。

## 版號資料（[release](release.md)「升版時要改的版號資料」）

| # | 檔 | 改成 |
|---|---|---|
| 1 | `packaging/validate.py` 的 `VERSION_OVERRIDES` | `{'odoo': '0.5.1', 'headscale': '0.4.19'}`（`VERSION` 維持 0.4.14） |
| 2 | `packaging/inputs.json` 的 `version_overrides` | 同上 |
| 3 | `packages/mcp-admin-core/mcp_admin_core/__init__.py` 的 `PRODUCT_VERSIONS` | 同上 |
| 4 | `addons/odoo/config.yaml` 的 `version` | `0.5.1` |
| 5 | `apps/odoo/Dockerfile` 的 `ARG BUILD_VERSION` | `0.5.1` |
| 6 | `.github/workflows/ci.yaml` 2 處、`release.yaml` 4 處 | `validate.py` 產生的三路運算式（`odoo` 為 `'0.5.1'`） |
| 7 | 本檔 `docs/operations/release-decision-odoo-0.5.1.md` | 推 GHCR 之後補證據 |

CHANGELOG（`addons/odoo/CHANGELOG.md`、根目錄 `CHANGELOG.md`）、`upgrade-notes.yaml`（`to_version: "0.5.1"`、`from_version: "0.4.14"`）、`addons/odoo/DOCS.md`、
`README.md` 等使用者看得到的「0.5.0 起」都改成 0.5.1，並寫明 0.5.0 沒有上架、0.5.1 修 F1。

## 驗收與批准（全部待負責人批准）

1. 推送分支、開 PR：待負責人。
2. 候選建置與容器驗收（`release.yaml` gate → candidate）、HM-19c 量測（只記錄，不擋發版）：待負責人批准。
3. 推 GHCR（`public-release` 核准）：待負責人批准；之後補證據。
4. HM-19b 以 0.5.1 重做（含 F1 的官方 SDK 回歸：額外帳號常駐 GET 時 `tools/list`／`tools/call` 成功；預設帳號 5 個用戶端時 `tools/call` 成功）：待展示機。
5. Store 乾跑與上架（從 0.4.14 直接升級到 0.5.1）：待負責人批准。
