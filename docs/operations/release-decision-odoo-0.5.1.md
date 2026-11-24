# Odoo 0.5.1（多帳號首發 R1，取代未上架的 0.5.0）發佈紀錄

狀態：**映像已發佈到 GHCR 並通過展示機驗收（2026-11-24），待合併上架**。這是 Odoo 一個產品（`woow_mcp_odoo`）的發版：版號 0.4.14 → 0.5.1。
0.5.0 已推到 GHCR，但從未上架 Store（Store 上目前是 0.4.14），使用者拿不到；0.5.1 是第一個上架的多帳號版，使用者從 0.4.14 直接升級。
合併 PR #137 即上架 WOOW App Store；合併前只補這份紀錄與驗收紀錄（只改 `docs/`）。

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
- 串流自己的位元組上限：`reply_memory.STREAM_BYTES`＝2 MiB（交給 server 還沒收走；審查 MF-1 後由 1 MiB 改）、`STREAM_EVENT_BYTES`＝128 KiB（子程式單一事件）；
  超過時乾淨結束串流（用戶端重連）並記一行 WARNING（不含 token 與內容）。只在開通且用票券的 Odoo；關閉的產品、n8n 與其他產品路徑不變。
- 全域最壞記憶體算式加保留項 `request_budget.ODOO_STREAM_RESERVE_MIB`＝128（最多 24＋5×8＝64 條串流×2 MiB）：六帳號需要量 2,839 → 2,967 MiB（3 GiB 上限內），
  全 add-on 請求內容預算的推導同樣多扣 128 MiB。
- **驗收的預期結果**：預設帳號 5 個 SDK 用戶端的 `tools/call` 依序都成功；5 個「同時重疊」的 `tools/call` 仍只有 3 張票，後 2 個回 200＋`-32003`＋`Retry-After: 5`，這是已接受的票券設計，不是缺陷。發版後用 HM-19b 同一套 SDK 1.32.2 套件在展示機重跑 F1 與 `f1sdk-*`。
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
| 7 | 本檔 `docs/operations/release-decision-odoo-0.5.1.md` | 推 GHCR、展示機驗收之後補證據（本次） |

CHANGELOG（`addons/odoo/CHANGELOG.md`、根目錄 `CHANGELOG.md`）、`upgrade-notes.yaml`（`to_version: "0.5.1"`、`from_version: "0.4.14"`）、`addons/odoo/DOCS.md`、
`README.md` 等使用者看得到的「0.5.0 起」都改成 0.5.1，並寫明 0.5.0 沒有上架、0.5.1 修 F1。

## 驗收與批准

依負責人 2026-11-23「整套一次授權」：每個產品過完所有關卡（CI、審查、容量驗收）才發佈；GitHub 的發佈核准以 API 代按，改版號 PR 也代為合併，每一步回報。

| # | 步驟 | 結果 |
|---|---|---|
| 1 | 推送分支、開 PR | PR #137（`release/odoo-0.5.1-20261123`，頭 `403e4c8`，以 #135 的 `1e9adfb` 為基準只往上加提交；取代 #135） |
| 2 | 兩份獨立審查、最終驗證 | 通過，沒有必修項；採納的建議：串流上限 1 → 2 MiB 並測最壞事件、契約用字改精確、補重連測試、寫明驗收預期。F1 回歸測試在基準 `1e9adfb` 上會失敗、在頭上通過 |
| 3 | 候選建置與容器驗收 | `release.yaml` run 45207734799：gate（2026-11-23 16:19Z）、candidate（16:23Z）成功；`image.tar` sha256 `da4296aa59bf61daf48db9e6ed40f9243759ba854f298b4613f240a4aa194a2a`、203,360,256 位元組；映像 ID 由 tar 內 config 自行算出，與 handoff 一致 |
| 4 | Store 升級乾跑（展示機，0.4.14 → 0.5.1） | PASS（2026-11-24 00:4x 台北）：兩版都 60 秒不退出、不重啟，資料保留，hassio 網路 ID 與 IPAM 不變 |
| 5 | 推 GHCR | 以 API 核准 `public-release`，publish 成功（2026-11-23 16:33Z）：manifest `sha256:9f05fbcb4eb95376f897bcf2734ea66a30634ef5c3c85c80ba9e9d8db2c8ec2b`、映像 ID `sha256:12b97d0d5730aa956450bd748a36f2280f21cefc95c743aba24e9153ed51b6b8` |
| 6 | PR 檢查 | 映像發佈後重跑 readiness 與 Upgrade comparison，全部 success |
| 7 | 展示機 HAOS 驗收（HM-19b 第二輪） | PASS，**F1 不再重現**（官方 SDK 1.32.2 用戶端全部成功）；細節、偏離與已知限制見 [ha-test-odoo-0.5.1](ha-test-odoo-0.5.1.md) |
| 8 | HM-19c 量測 | 只記錄、不擋發版（負責人 2026-11-23）；這一版沒有重跑 |
| 9 | 合併上架 | 本證據提交之後合併 #137 |

## 已知限制（不擋這一版，細節見 [ha-test-odoo-0.5.1](ha-test-odoo-0.5.1.md)）

- 經 Cloudflare 開 HA 時，面板不能儲存「瀏覽器來源檢查」設定（Cloudflare 壓縮把 ETag 改成弱 ETag，面板只接受強 ETag）。只影響這一張卡片；
  預設值照常運作，從區網開 HA 可以儲存。下一版修。負責人 2026-11-24 決定先發。
- 後續（2026-11-25）：F2 在維修版修好了：面板也把 Cloudflare 這類代理改成的弱 ETag（`W/"…"`）當成同一個版本，送出時照舊送強的 `If-Match`，add-on 的比對沒有放寬；帳號清單的 ETag 用同一個讀法，一起修；但在 Cloudflare 上量到不受影響（2026-11-25 在真的 HA 加 Cloudflare 上量，瀏覽器的 `Accept-Encoding: gzip, deflate, br, zstd`）：`api/origin-policy`（94 位元組）被 Cloudflare 壓成 br、ETag 變弱，所以卡片不能存；`api/profiles`（161 位元組）由 Home Assistant 自己先壓 gzip、ETag 維持強；只有前面的代理改寫 HA 沒壓縮的回應時才可能變弱，例如用戶端不收壓縮（`docs/multi-profile/unreleased-changes.md` A11）。上面寫的是這一版映像的行為，沒有改。
- 額外帳號只有 1 張回覆票券（已接受的設計）：Claude.ai 並行送出的兩個工具呼叫，有一個會回 `-32003`（忙碌），Claude 自動重試成功。
