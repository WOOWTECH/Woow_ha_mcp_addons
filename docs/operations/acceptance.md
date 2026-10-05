# 分層驗收與故障接受條件

**狀態：2026-10-05 起：七類映像已在專用一次性 KubeVirt builder（Docker classic store）由候選 `f75fe32` 建置，container/mock 驗收與 supply-chain gate（source／history／image secrets、SBOM、CVE、license）全數通過；證據在協作區 `claude-delivery/evidence-real-f75fe32/`。映像尚未發佈、未安裝到 HA，也沒有真實 backend E2E。
私有 builder 的 PASS 不等於 HA、真後端或公開發佈驗收；core 本地測試報告不能替代這些證據。七類不互相外推。**

每項紀錄：UTC、批准範圍、source SHA、image tag+digest、依賴／client／Core／
Supervisor／HAOS 版本、硬體、測試命令、exit code、預期／觀察、匿名化證據、reviewer、
影響與回復結果。不得記錄 token、Authorization、backend body、state、cookies、Ingress
session URL、備份或私人拓樸。LOCAL/MOCK、CONTAINER/MOCK、HA、PUBLIC 分開標記。

| Gate | 最低證據／失敗停止點 |
|---|---|
| Source/license/secret | 逐檔來源、公開授權、OpenDesign 原來源缺 LICENSE 解決、Manage MPL covered-source 與 notices、整個新歷史與 tree／映像 layers/config／release/docs 去密掃描加人工審查。Regex PASS 不等於 clearance。 |
| Package | root context 七個獨立 amd64 builds；固定 Python/Node/uv base digest、uv/npm lock；selected app 隔離、HA app labels/version；不得將無法 build 當 skip。 |
| Bootstrap | 空且受控 `/data` 唯一 token、nonempty command；uid10001、0700/0600；第二次啟動不覆寫；六類未設定不 spawn/probe。錯 owner（0.1.1 起，HA 還原留下的 root 擁有狀態檢查後一次改回）/symlink/future state 拒絕。 |
| Admin trust | 僅 n8n 路徑 A 權限已批准；provider 已實作／component review、GUI 已本地 Core 整合（fake HA transport）、HA NOT TESTED，此 gate 仍 BLOCKED。真實 HA admin 成功、non-admin 直接 Ingress URL/API 拒絕；缺少／重複 ID、偽造 peer/role headers 不得權。敏感操作前 fresh query，停權／降權／timeout／錯誤均拒絕且無副作用；role query 不等於立即撤銷 browser Ingress session。 |
| Ingress UX | 有效 base path 的 assets/API/navigation/deep link/refresh，CSRF／origin 負面測試；MCP endpoint 不是 iframe origin。本地真 Core/browser 已覆蓋，尚非 HA iframe 驗收。 |
| Protocol | 每類 initialize→initialized→tools/list→已審無副作用 call，檢查真實 payload，不只 HTTP200。對照完整工具表，184/65/119 不可說完整 parity。 |
| Bearer/policy | missing/wrong/revoked token、GET/POST/DELETE/stream reconnect；disabled/unknown/write direct-call 拒绝且 backend 計數不變；舊 session 不繞過新政策。 |
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
  YAML/clearance fixtures；只有 n8n 的 HA API 例外，其他六類 false；拒絕新增 API／
  role／host 權限。invented dummy env 的 bootstrap exec 測試核對固定 management
  launcher argv、token 唯一傳遞、missing/empty 與其他六類剝除，不讀 runner 環境。
  真正 Linux post-exec guard 測試拒絕同 UID child 的 parent environ/mem/process_vm_readv；
  dispatch-only write mutation 必須被有效參數與 backend delta assertion 抓到。
  這些**不是已執行真實 verifier 或 HA 的整合測試**。
  fixture 不使用 config.* basename，避免被商店探索。
- `sh packaging/unit.sh`：隔離 CI 安裝完整 pinned runtimes，執行既有全部 core/adapter
  tests 與 inventory drift；Junit 不允許 skipped、zero tests 或失敗。
- `python packaging/container_acceptance.py <app> local/mcp-<app>:0.1.0`：檢查已建置
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

## 本地聯合整合與仍未通過的映像／HA gates

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
  owner/admin/nonadmin/demotion/errors 已 local 覆蓋；六類表單只 test 注入 role。
  與 packaging Linux tests 分層記錄，不可外推 HA 或 production MCP E2E 成功。
- container network-none probe 的 missing identity／fake role/peer 應繼續 403；
  loopback 不是 trusted Ingress，它不證明角色查詢成功或真實 HA admin/non-admin。
- fresh role query、等待後降權、malformed／timeout fail-closed 等 core tests 及
  七個 actual-image gates 均須重跑。之後才可在另行批准 HA 試點驗證真實角色；
  本次無 HA、backend、build、deploy 或既有服務變更授權。

## 故障處置界線

其他六類、缺少／失效角色的 MANAGEMENT 403 屬預期封鎖，不是要求提高 HA 權限。readiness503 要分
未設定／backend 無法連線；不要無限重啟。`BACKEND_BUSY` 表示有界 resolver/tool
容量已滿，等候或停止本新 Add-on 的核准恢復即可，不增無界 thread。TLS/redirect/
metadata DNS 拒絕要查 canonical backend 與憑證，不關驗證。來源 hash drift 須重新
審查依賴／launcher，不刪 hash guard。EMQX 真節點證據、LiteLLM 模型列表、Hermes／
OpenDesign API 版本不符需逐產品確認，不泛化為七類健康。
