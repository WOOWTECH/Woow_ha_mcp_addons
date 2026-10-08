# 分層驗收與故障接受條件

**狀態（2026-10-07）：0.1.5 六支（n8n、Odoo、Hermes、OpenDesign、EMQX、LiteLLM；Odoo Manage 已下架）已公開發佈：映像 `ghcr.io/woowtech/amd64-mcp-<product>:0.1.5`（來源 `0c66bd0`）在專用一次性 KubeVirt builder（Docker classic store）通過 container/mock 驗收與 supply-chain gate（source／history／image secrets、SBOM、CVE、license），推送同一個已測 ID，匿名 registry_gate PASS（[0.1.5 發佈紀錄](release-decision-0.1.5.md)；0.1.0 是 2026-10-05 的七類候選 `f75fe32`，證據在協作區 `claude-delivery/evidence-real-f75fe32/`）。0.1.1–0.1.5 每版都在測試 HA 回歸（[ha-test-0.1.1](ha-test-0.1.1.md)…[ha-test-0.1.5](ha-test-0.1.5.md)）：執行中映像身分、owner Ingress 與 non-admin 403、token、五支真後端讀取冒煙與拒寫、後端斷線、重啟、child 恢復（有 child 的五支；LiteLLM 沒有後端，也就沒有 child）、升版。n8n 備份還原只在 0.1.1 完整驗證；0.1.2 只驗了還原修復後的啟動與 owner／權限，權杖延續沒驗到（[ha-test-0.1.2](ha-test-0.1.2.md)）。2026-10-07 另對測試 HA 上未設定後端的 LiteLLM 逐一打 45 個案例，45/45 符合預期（39 個 403、5 個 502、readiness 503；見 [client 文件](clients.md)）。P9 讀取只判 HTTP 200、非 isError、無 `success:false`，不驗內容正確性。尚未完成：真 MCP client、授權寫入（Odoo 寫入前須先有只允許測試資料的暫時 record rule，見 [ha-test-0.1.5](ha-test-0.1.5.md) 補註）、其餘五支還原、版本回退、LiteLLM 工具（無後端）、aarch64。`RELEASE-GATES.json` 人工 gates 仍全部 false。
私有 builder 的 PASS 不等於 HA、真後端或公開發佈驗收；core 本地測試報告不能替代這些證據。六支不互相外推。**

每項紀錄：UTC、批准範圍、source SHA、image tag+digest、依賴／client／Core／
Supervisor／HAOS 版本、硬體、測試命令、exit code、預期／觀察、匿名化證據、reviewer、
影響與回復結果。不得記錄 token、Authorization、backend body、state、cookies、Ingress
session URL、備份或私人拓樸。LOCAL/MOCK、CONTAINER/MOCK、HA、PUBLIC 分開標記。

| Gate | 最低證據／失敗停止點 |
|---|---|
| Source/license/secret | 逐檔來源、公開授權、OpenDesign 原來源缺 LICENSE 解決、Manage MPL covered-source 與 notices、整個新歷史與 tree／映像 layers/config／release/docs 去密掃描加人工審查。Regex PASS 不等於 clearance。 |
| Package | root context 每個商店產品（`packaging/inputs.json`）各自獨立的 amd64 build；固定 Python/Node/uv base digest、uv/npm lock；selected app 隔離、HA app labels/version；不得將無法 build 當 skip。 |
| Bootstrap | 空且受控 `/data` 唯一 token、nonempty command；uid10001、0700/0600；第二次啟動不覆寫；n8n 以外各支未設定不 spawn/probe。錯 owner（0.1.1 起，HA 還原留下的 root 擁有狀態檢查後一次改回）/symlink/future state 拒絕。 |
| Admin trust | 各支權限已批准（n8n 2026-10-03；其他六支 0.1.1 起；Nextcloud 2026-10-08）；provider 經獨立 SPEC＋安全審（0.1.1）；真 HA owner 成功、non-admin 對面板／管理 API 403、無 cookie 401 已在 0.1.1–0.1.5 實測；登入後降權、token 長時間過期與瀏覽器 UX 未在真 HA 測。真實 HA admin 成功、non-admin 直接 Ingress URL/API 拒絕；缺少／重複 ID、偽造 peer/role headers 不得權。敏感操作前 fresh query，停權／降權／timeout／錯誤均拒絕且無副作用；role query 不等於立即撤銷 browser Ingress session。 |
| Ingress UX | 有效 base path 的 assets/API/navigation/deep link/refresh，CSRF／origin 負面測試；MCP endpoint 不是 iframe origin。本地真 Core/browser 已覆蓋，尚非 HA iframe 驗收。 |
| Protocol | 每類 initialize→initialized→tools/list→已審無副作用 call，檢查真實 payload，不只 HTTP200。對照完整工具表，六支 174/67/107（上游／支援／暫不支援）不可說完整 parity。 |
| Bearer/policy | missing/wrong/revoked token、GET/POST/DELETE/stream reconnect；disabled/unknown/write direct-call 拒絕且 backend 計數不變；舊 session 不繞過新政策。 |
| Streams | native Streamable HTTP JSON/SSE/session/cancel/reconnect；不宣稱 legacy /sse；錯 protocol/session/origin 與中斷清理。成功資料本身不是通用 secret-free 保證。 |
| Lifecycle/outage | 只殺 disposable/new child，觀察有界退避、終止傳遞、孤兒回收；mock backend 離線 readiness503，但 child PID 不變。禁止停現有 backend 注入故障；backend-dependent readiness 不作 watchdog。 |
| Persistence | GUI 修改後重啟持久化，options 不覆寫；完整 n8n v1／product v2→v3（新增空 exact grants）、future/corrupt 拒絕，失敗原資料不變；舊版+相容 backup rollback。 |
| Backup/restore | 核准範圍 cold 停止僅本 Add-on，完整含秘密 backup 安全保管；restore owner/policy/token 驗證、舊 token 復活風險與輪替。 |
| Clients/network | 實際同 HA Pi／Omnigent／Hermes（各版本/transport/network mode）及至少一 LAN client；null mapping 與唯一 LAN host port；未提供的 client 是 blocker，不編造成功。 |
| Performance | 目標硬體 CPU/RSS/映像大小/冷啟動/首呼叫/p50/p95/並發，實測容量，不猜幾個可同時跑。 |
| Public/release | protected environment 人工批准、清除記錄、未使用固定 tag、digest/SBOM/provenance、匿名 GHCR pull、繁中文件/changelog/手動更新/回復。 |

## 可執行的本地與 CI gate

- `python packaging/validate.py`：Supervisor pinned schema 的嚴格安全子集，未知 key、
  image/slug/arch、權限、translation scope、意外 config.* discovery、工作流基本政策。
  不是整個 Supervisor import；該版本本身會 REMOVE_EXTRA，本 validator 反而拒絕。
- `python -m unittest discover -s packaging -p 'test_*.py' -v`：惡意 manifest／翻譯／
  YAML/clearance fixtures；`validate.PRODUCTS` 的每一支都必須是 `homeassistant_api: true`（唯一核准的權限例外），拒絕新增 API／
  role／host 權限。invented dummy env 的 bootstrap exec 測試核對固定 management
  launcher argv、token 只傳給各支管理程序、missing/empty 不自行產生，不讀 runner 環境。
  真正 Linux post-exec guard 測試拒絕同 UID child 的 parent environ/mem/process_vm_readv；
  dispatch-only write mutation 必須被有效參數與 backend delta assertion 抓到。
  這些**不是已執行真實 verifier 或 HA 的整合測試**。
  fixture 不使用 config.* basename，避免被商店探索。
- `sh packaging/unit.sh`：隔離 CI 安裝完整 pinned runtimes，執行既有全部 core/adapter
  tests 與 inventory drift；Junit 不允許 skipped、zero tests 或失敗。
- `python packaging/container_acceptance.py <app> local/mcp-<app>:0.1.5`：檢查已建置
  真 image labels/arch/ports/entrypoint，再在 `--network none --read-only`、tmpfs
  `/data`/`/tmp` 中執行真正 packaged entrypoint；owned fake HTTP/XMLRPC backend，
  bootstrap/uid/caps/permissions、protocol/read、missing/wrong auth、direct denies、
  failclosed admin、child loopback、outage PID、stop/reap、state persistence、停機後
  fixture token rotation/disabled 測試。**最後這項不是管理 API 輪替或 HA backup 證據。**
- `supply_chain.py candidate` 強制同一已測 image ID 的 source/history/all-layer secret、
  SBOM/CVE/license gate；`verify` 與 registry gate 拒絕缺失／錯 subject／失敗 evidence。
  完整 commands、unsigned provenance 信任層級、persist 範圍見 [hardening](hardening.md)。
- container probe 只可由此 harness 以空 tmpfs 呼叫，禁止直接對真實 `/data` 執行。
  它不安裝 test dependency 到正式 image，也不啟用 test-only role verifier。

## 本地聯合整合與映像／HA gates

- `tests/integration_local_runtime.py` 是明確執行的 Linux root local test（不在一般 collection），
  只使用可讀的 owned /tmp Python copy，不 chmod 現有 home/system。
  真實 provider／lock／n8n child token 剝除已串接；不將測試 verifier 搬入 production，
  不修改 provider 固定 URL／command。
- 已在隔離 disposable mock 環境，經**真正 packaging entrypoint → n8n run.py →
  provider** 驗證 invented dummy token 的傳遞與固定 WS authentication／
  `config/auth/list`；MCP child 不得收到 token、config/options/argv/log 不得含 token。
  路徑必須包含 final-exec management guard；MCP child 同 UID 嘗試讀 parent
  procfs/memory 仍拒絕。Chromium 連真 Core HTML/static/API，root/prefix 刷新、字型、
  typed forms、v3 existing/legacy/stale/disabled grants、endpoint、CSRF、token確認/blur/TTL/revoke，
  owner/admin/nonadmin/demotion/errors 已 local 覆蓋；n8n 以外各支的表單只 test 注入 role。
  與 packaging Linux tests 分層記錄，不可外推 HA 或 production MCP E2E 成功。
- container network-none probe 的 missing identity／fake role/peer 應繼續 403；
  loopback 不是 trusted Ingress，它不證明角色查詢成功或真實 HA admin/non-admin。
- fresh role query、等待後降權、malformed／timeout fail-closed 等 core tests 及
  actual-image gates 每版重跑（0.1.5 為六支）；真實角色已在測試 HA 驗證 owner／non-admin（0.1.1–0.1.5），
  登入後降權未在真 HA 測。HA、backend、build、deploy 或既有服務的變更仍須另行批准。

## 故障處置界線

缺少／失效角色（非 owner／系統管理員）的 MANAGEMENT 403 屬預期封鎖，不是要求提高 HA 權限。readiness503 要分
未設定／backend 無法連線；不要無限重啟。`BACKEND_BUSY` 表示有界 resolver/tool
容量已滿，等候或停止本新 Add-on 的核准恢復即可，不增無界 thread。TLS/redirect/
metadata DNS 拒絕要查 canonical backend 與憑證，不關驗證。來源 hash drift 須重新
審查依賴／launcher，不刪 hash guard。EMQX 真節點證據、LiteLLM 模型列表、Hermes／
OpenDesign API 版本不符需逐產品確認，不泛化為六支健康。
