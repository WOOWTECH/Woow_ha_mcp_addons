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
  第一次停機後另模擬一次 Supervisor 還原（`/data/mcp` 整棵改屬 root、檔案 0644），確認下一次啟動時 entrypoint
  修好擁有者、管理程序的開機守門處理了 entrypoint 留下的 `.restore-detected` 並刪掉它、state 位元不變（沒開通的產品只多面板的
  還原提示 `restore-notice.json`；多帳號 HM-13a、HM-13b、HM-13c）。這次啟動的 stderr 收到容器裡沒有名字的暫存檔（不印、
  關掉就不見），停機後確認 entrypoint 的 `bootstrap: re-owned N restored entries in /data/mcp` 與守門通知
  （`restore_lock.KEPT_NOTICE`：沒有帳號資料，不撤銷）各剛好一行（HM-16，HM-13b 審查 S-3），守門沒有別的行（`restore guard`
  開頭的；HM-16 第二輪審查）；這也不是 HA 還原證據。
  開通多帳號的候選映像（升版 PR 把產品加進 `MULTI_PROFILE_PRODUCTS`）另跑多帳號階段（`packaging/container_profiles.py`，
  HM-16）：假後端照 Headscale 改用一次性 internal bridge 與容器私有位址，`docker run` 上限 360 秒；內容見下方
  [多帳號驗收](#多帳號驗收t-01t-29-的-ha-版hm-16)。沒開通的產品，探針逐句照舊（`packaging/test_container_probe.py`
  和審過的基準比對）。
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

## 多帳號驗收（T-01～T-29 的 HA 版；HM-16）

**狀態（2026-11-19）：工具備好；有一次發版前預驗，還沒有 HM-19b 的正式驗收**。Odoo 0.5.1 的升版 PR（HM-19a）把 `odoo` 加進 `MULTI_PROFILE_PRODUCTS`；
映像還沒建置，HM-19b 等它推上 GHCR 之後做（[0.5.1 發佈紀錄](release-decision-odoo-0.5.1.md)）。LiteLLM、Nextcloud、EMQX 的 0.5.0（火車 A）也開通，各自的發佈紀錄（`release-decision-litellm-0.5.0.md`、`release-decision-nextcloud-0.5.0.md`、`release-decision-emqx-0.5.0.md`）寫明展示機真後端驗收還沒做；其他產品還沒開通。

- **發版前預驗（2026-11-19）**：在負責人指定的展示機上，用拋棄式的本機 add-on（以已發佈的 Odoo 0.4.14 映像為底、換上 `claude-delivery` `fcd0b22`
  的程式，開關關與開各一份）跑了 Odoo 多帳號實測，結果見 [Odoo 多帳號發版前預驗](ha-test-odoo-multiprofile-early.md)。
  **發版前預驗；HM-19b 仍要在正式映像上重做**：它不是 HM-19b 的證據（不是 HM-19a 的候選映像、不經商店、沒有目標硬體），也不能代替下表任何一列的 HA 層。
- **HM-03a／b 平台探針（2026-11-18，展示機；HAOS 18.1、Core 2026.7.2、Supervisor 2026.11.0）寫回的**：UC-10 是（Ingress 照原樣轉 `X-MCP-Profile` 與
  PATCH、DELETE；[契約](../multi-profile/contract.md)第 3.7 節）；UC-08 一般與加密的局部還原，兩個還原訊號都觸發（契約第 10 節 2026-11-18 HM-13b 那列）；
  sentinel 的 inode 與 ctime 在 add-on 重啟、冷備份、add-on 更新之後都不變（用一個 entrypoint 不碰的專用檔模擬 sentinel）。
- **還沒做、在本文件仍是未確認的**：完整還原（列為 Odoo 發版前的關卡）、主機重開與 Supervisor 更新之後的 sentinel、UC-14、Claude.ai 送的 Origin（S14）。

下面的「通過標準」是驗收時要做到的，不是已經做到的。期望值逐列的來源與差異見
[多帳號驗收矩陣](../multi-profile/acceptance-matrix.md)（PaaS T-01～T-29 的 HA 版，測試檔登記表也在那裡）與
[契約](../multi-profile/contract.md) 第 9 節。

門檻不放寬：**0 串號、0 外洩、0 OOM、0 個非預期 5xx**。紀錄照本文開頭的欄位，分開標記 LOCAL/MOCK、
CONTAINER/MOCK、STORE、HA、PUBLIC；token 一律不印、不存，帳號只用 log id（`default` 或 id 前 8 碼），不寫帳號名稱。

| 層 | 在哪裡跑 | 工具 | 誰批准 |
|---|---|---|---|
| LOCAL/MOCK | GitHub CI `checks` | `packaging/unit.sh`（pytest、node、Playwright；root、0 skip）；packaging unittest（`python -m unittest discover -s packaging`：容器探針、多帳號階段與 P9 probe 的 mock 測試；不是 root、允許 skip） | 不需要 |
| CONTAINER/MOCK | repo 外 builder | `container_acceptance.py`；開通的候選映像加多帳號階段 | 使用者（builder） |
| STORE | 升版 PR 的 `Upgrade comparison` | `addons/<產品>/upgrade-check/seed`、`verify`（HM-16 的草稿，HM-19a 搬進 `addons/odoo/upgrade-check/`） | 自動 |
| HA | QA HAOS | [P9 kit](ha-p9-kit.md)（`--profile`、`--cross`、`--temp-profile`、`childkill`）加人工 | 使用者（每一步） |
| PUBLIC | 使用者的代理或 tunnel、真 Claude.ai | 人工 | 使用者 |

容器的多帳號階段（CONTAINER/MOCK，只在開通的候選映像；第一次真跑是 HM-19a 前的 builder 乾跑）：預設帳號加 2 個額外帳號
（停機時照面板的建立方式建，容器裡沒有 HA 管理員，不繞過管理 API 的身分檢查）、每個子程式只聽自己的 loopback port、
每個帳號的 session 是自己子程式的（直接問每個子程式：只有自己的認得）、交叉 token 與 session 被拒、子程式只認自己的
child bearer、額外子程式 `oom_score_adj` 500 與 `nice` 加 5、SIGKILL 一個子程式其他 PID 不變、並行停機 <30 秒（印出秒數）、
sentinel 是執行期自己建的而且沒被動過、子程式跑過後 `/data/mcp` 符合修復規則與項目預算。最後照 Supervisor 的方式還原整棵
多帳號樹再起一次（DQ-03 (b) A2：有帳號資料，連預設帳號一起撤銷）：每個項目修好、守門刪掉標記與單帳號階段的還原提示、
寫還原紀錄（兩個訊號、每個帳號都撤銷）；每個帳號的 token 是 null、child token 換新、其他欄位與索引不變；每個子程式重新起來；
還原前的 token 兩種接法都被拒（Bearer 401、密鑰網址 404）、每個子程式拒絕還原前的 child token；停機後 sentinel 已重建、
守門留下的樹仍符合修復規則；這次啟動的 entrypoint `re-owned N` 一行、每個帳號的 `REVOKED` 一行、`REVOKED_NOTICE` 一行，
守門沒有別的行（log 收到沒有名字的暫存檔，不印）。這些是容器裡的模擬，不是 HA 證據。n8n 開通（HM-25）前這個階段不收 n8n：
n8n 子程式的 port 只在環境變數裡，認不出哪個子程式是哪個帳號的。

下表「怎麼驗」寫每一層實際驗哪幾項；沒寫到的項目只在 LOCAL 驗。「Odoo 首發」照計畫 §10.4：是＝Odoo 首發（HM-19b）前要過。

| T | 情境 | 怎麼驗（層：工具） | 通過標準（HA） | Odoo 首發 |
|---|---|---|---|---|
| T-01 | 受測物前置 | HA：`docker inspect` 對 GHCR digest；`ha core info`、`ha supervisor info`、`ha os info` | 執行中映像 digest＝發佈值；Core／Supervisor／OS 版本記下；後端只用合成或受限身分 | 是 |
| T-02 | 上限、名稱、清單欄位 | LOCAL；HA：面板 | 第 6 個額外帳號 409 `profile_limit_reached`＋`limit`；記憶體不足 409＋`limit`、`required_memory_mib`、`available_memory_mib`；名稱規則照 HA 加嚴；清單有 `status` | 是 |
| T-03 | 每帳號後端與 token | LOCAL；HA：面板＋P9 `--cross` | 每帳號 43 字元 token 互異；Odoo 換 url／database／username 就換 token、兩條舊網址都失效；只換密碼不換 | 是 |
| T-04 | N×N 真後端隔離 | HA：同一個 Odoo 資料庫，預設＋5 個受限使用者，各自寫標記 | 標記只在對角線；身分的建立與刪除都要使用者批准 | 是（Odoo） |
| T-05 | 只由 token 決定帳號 | LOCAL：全部；CONTAINER：兩種接法、session 是自己子程式的、跨帳號 session 404、隨機 token；HA：P9 `--cross`（兩種接法、跨帳號 session 404、隨機與已刪的 token、帶 `X-MCP-Profile: default` 也不換帳號） | 錯 token：密鑰網址 404、Bearer 401（PaaS 403）；query 400；密鑰網址上的 `Authorization` 不看；跨帳號 session 404。query 400 與「密鑰網址上的 `Authorization` 不看」只在 LOCAL 驗 | 是 |
| T-06 | 管理 API 授權與帳號 id | LOCAL：全部；HA：面板與 P9（管理請求帶 `X-MCP-Profile`） | 非 Ingress、非管理員一律 403（任何帳號狀態下逐位元相同）；管理員：缺標頭 400、格式錯 400（PaaS 404）、未知 404；MCP token 不能當管理憑證。「逐位元相同」只在 LOCAL 驗 | 是 |
| T-07 | 每帳號工具政策 | LOCAL；HA：面板＋P9 `--profile … --plan` | 存政策只重啟該帳號；別帳號的工具清單不變 | 是 |
| T-08 | 輪替、撤銷、撞號 | LOCAL；HA：P9 `--profile … --tokens` | 舊 token 404／401；撞號（只會來自複製或還原）503、不導向任何帳號 | 是 |
| T-09 | 改名、刪除、重建 | LOCAL：全部；HA：P9 `--temp-profile`（刪除後舊 token 被拒）＋面板（清單、孤兒卡片） | 刪除後舊 token 立刻失效、子程式停、port 釋放、目錄刪除、`blocked` 的帳號立刻重評；重建拿新 id 與新 token。子程式停、port 釋放、目錄刪除、立刻重評只在 LOCAL 驗 | 是 |
| T-10 | 跨帳號寫入 | LOCAL（假後端）；HA：寫入前加只允許測試資料的暫時 record rule | 全被後端擋；A 的寫入審批 token 在 B 被拒 | 是 |
| T-11 | 並行 0 串號 | LOCAL；HA：多帳號同時壓 | 0 串號、0 個非預期 5xx | 是 |
| T-12 | 負載中輪替、刪除 | LOCAL；HA | 只切斷該帳號的 lease，別帳號的串流不斷 | 是 |
| T-13 | 單一子程式當掉 | LOCAL：看門狗全部；CONTAINER：SIGKILL 一個、新 PID、其他 PID 不變、之後照常服務；HA：P9 `--profile … --modes childkill`（同 CONTAINER） | 只殺那個帳號的子程式；它照看門狗重起（2→300 秒、不限次數、120 秒歸零；DQ-20），其他帳號 PID 不變。容器與 P9 只驗第一次重起：新 PID，而且那個帳號的 token 開得到子程式自己的 session（重起前閘道自答的 `woow-local-` session 不算）；退避表與 120 秒歸零只在 LOCAL 驗 | 是 |
| T-14 | 冷啟動與重啟 | LOCAL：全部；CONTAINER：三個帳號都就緒的秒數、每帳號的 session 是子程式的；HA：P9 `restart` | 子程式未就緒時閘道自答 initialize（自答 session），之後要求重連（子程式就緒後自答 session 回 404，用戶端要重新 initialize）；就緒後每帳號 initialize 200；錯開啟動下「全部就緒」有秒數。「之後要求重連」只在 LOCAL 驗 | 是 |
| T-15 | port 被佔與同 port | LOCAL：全部（`tests/test_profile_ports.py`）；CONTAINER：只驗每個子程式只聽自己的 port | 衝突只停相關帳號；被佔時照看門狗退避，放開後自動恢復。衝突、退避與恢復只在 LOCAL 驗（容器階段不佔 port：要多等看門狗的退避，第一次真跑前不加） | 是 |
| T-16 | 子程式晚驗證 | LOCAL | HA 閘道自答（不是 PaaS 的 503）；套用狀態每帳號一份 | 是 |
| T-17 | 記憶體與 CPU | HA：目標硬體（HM-19c） | J6412（可以的話 J1900）1～6 個帳號的 RSS／PSS、CPU 有數字；停機 <30 秒；全域最壞值不超過 MemAvailable 減保留量 | 是 |
| T-18 | 互相影響與日誌保留 | LOCAL；HA：add-on log | 每帳號子程式輸出不被別帳號擠掉；生命週期 log 帶 id 前 8 碼、0 個帳號名稱 | 是 |
| T-19 | 背壓與每帳號名額 | LOCAL | 轉送名額、准入、位元組預算、GET 串流照契約第 2.4、5 節；CPU 飢餓下閒置帳號健康不逾時 | 是 |
| T-20 | 升級、回退、再升級 | STORE：`seed`／`verify`（只驗升級那一段）；HA：升級 → 還原升級前備份 → 再升級 | 升級：預設 token、兩條網址、`state.json` 位元不變。回退＝還原升級前備份：預設 token＝備份當時的值、額外帳號消失、沒有撤銷。再升級：額外帳號不存在、預設不變；照文件按「全部撤銷」並確認。回退與再升級只在 HA 驗 | 是 |
| T-21 | 備份還原 | LOCAL：全部；CONTAINER：單帳號還原（守門刪標記、還原提示、`KEPT_NOTICE` 與 `re-owned N` 各一行、守門沒有別的行）、多帳號還原樹（每個帳號撤銷、child token 換新、還原紀錄、還原前的 token 兩種接法與 child token 都被拒、sentinel 重建、`REVOKED` 每帳號一行與 `REVOKED_NOTICE` 一行、守門沒有別的行）；HA：full、partial、加密各一次，步驟見下方 [T-21 在 HAOS 的步驟](#t-21-在-haos-的步驟hm-16) | 預設帳號依 DQ-03（採 (b) A2：有帳號資料才連預設一起撤銷；沒撤銷時面板與 log 提示權杖已回到備份當時的值）；兩個訊號至少一個觸發；讀不到的帳號隔離（只能刪）；獨立驗證（撤銷後重新讀過每個帳號，和還原前的 token 都對不上）；核對後才重發；舊收據 410（備份後才做、隨還原消失的操作也是）；C1-M1 攻擊序；版本混搭各一次（計畫 §10.6 第 6 點）。讀不到的帳號隔離與 C1-M1 只在 LOCAL 驗 | 是 |
| T-22 | n8n 名額與逾時 | 等 n8n 開通（HM-25） | `n8n_session` 每帳號一份；沒後端的額外帳號回 `backend_not_configured` | 否（n8n） |
| T-23 | 子程式 bearer 隔離 | LOCAL：全部（7 支 Python＋n8n）；CONTAINER：每個帳號的真子程式不帶、隨機、別帳號的 child token | 不帶、帶錯、帶別帳號、兩個標頭、空字串都 401，自己的 200（n8n 另見矩陣）。兩個標頭與空字串只在 LOCAL 驗 | 是（Odoo） |
| T-24 | 來源檢查 | LOCAL：全部（`tests/test_origin_policy.py`、面板的 `origin-policy` 測試）；HA：S14 交 HM-19b，用 echo 端點看 Claude.ai 實際送的 Origin（預設清單有 `https://claude.ai`，Claude.ai 送它時不會有 would_deny 行，看 add-on log 量不出來；也可以暫時把清單清空、維持 report-only 再看紀錄）；實機另看 add-on log 裡 would_deny 行的格式與節流 | 照[矩陣](../multi-profile/acceptance-matrix.md) T-24（HM-27 定案）：密鑰網址清單外（預設清單只有 `https://claude.ai`）只記一行 would_deny、不擋，回應和不帶 Origin 的同一個請求逐位元相同；面板切 enforce 後只擋清單外（403 固定本體），清單內與沒帶 Origin 照舊；政策檔不能用時每個帳號的密鑰網址 503；還原後政策是備份當時的；Bearer 帶 Origin 403；Headscale 只放 `https://claude.ai`。S14 的結果交負責人決定 DQ-11 第二問（2026-11-19 HM-18 改寫：原本只寫「記下 Claude.ai 送的 Origin」，是 HM-27 定案前的寫法） | 是 |
| T-25 | 紀錄稽核 97 種寫法 | LOCAL；HA：add-on log 與診斷 | 不比 pin 版 PaaS 差；0 token | 是 |
| T-26 | 名稱輸入與顯示 | LOCAL（Playwright） | HA 加嚴的名稱規則；顯示一律跳脫 | 是 |
| T-27 | 公開網址與真實用戶端 | PUBLIC | 每種接法各兩個帳號；真 Claude.ai 兩個帳號同時用；代理 log 遮掉 `/private_` | 是 |
| T-28 | 平台建立路徑 | — | 不適用（PaaS workspace 專屬；HA 的「商店安裝 → 加帳號」併入 T-20） | — |
| T-29 | 證據掃描與清理 | 每一層 | 合成憑證清單掃描 0 命中；暫時帳號與測試身分的清理證明 | 是 |

### T-21 在 HAOS 的步驟（HM-16）

full、partial（只選這個 app）、加密備份各做一輪。每一步都先經使用者批准，動手前先做保護備份（[手動更新、備份與回復](update-backup-rollback.md)，
面板與核對卡怎麼用也在那裡）。P9 kit 沒有還原專用的模式：用面板、add-on log 與 P9 `--cross`。token 一律不印、不存，帳號只記 log id。

1. **前置**：記下 T-01 的版本（Core、Supervisor、HAOS、映像 digest）；`ha jobs info` 確認沒有別的備份或還原在跑。開通的 app 有預設帳號與
   2 個額外帳號，各接上測試後端，P9 `--cross` 全過。在面板「匯出帳號清單（不含憑證）」留底（選做）。
2. **還原前的操作與用戶端**：每個帳號在面板重新產生一次權杖，從瀏覽器開發者工具記下那次請求的 `Idempotency-Key`（操作識別碼，
   不是秘密）。一個測試用的 MCP 用戶端接上某個額外帳號（Bearer 與密鑰網址各一個連線；權杖本來就存在它的設定裡，不另抄）。
3. **備份**，之後再對預設帳號重新產生一次權杖、記下這次的識別碼（這次操作會隨還原消失）。
4. **還原**，等 add-on 起來：
   - add-on log：`REVOKED_NOTICE`（`restore guard: the data was restored from a backup; the MCP token of every profile …`）剛好一行，
     `restore guard [profile=…]: token revoked, child token renewed` 每個帳號（含 `default`）剛好一行，沒有 `restore guard: not finished`。
   - 兩個訊號：有 `bootstrap: re-owned N restored entries in /data/mcp` 那行就是訊號 1（`/data/mcp` 被還原成 root 的）；訊號 2 看還原紀錄的
     `restore` 欄（HA 主機上 `docker exec <app 容器> /usr/local/bin/python -c 'import json; print(json.load(open("/data/mcp/restore-record.json"))["restore"])'`，
     只印這一欄：紀錄的其他欄有帳號名稱）。兩個都沒觸發就停下、不出貨（DQ-39 (a)）。
   - 面板：預設帳號頁的核對卡列出三個帳號（名稱、後端身分、政策摘要都是備份當時的值），都待核對；沒有單帳號的還原提示（權杖都撤銷了）。
   - 獨立驗證：面板每個帳號的「連線與權杖」都沒有權杖（已撤銷）；步驟 2 的測試用戶端兩種連線都被拒（Bearer 401、密鑰網址 404）。
     這時不跑 P9 `--cross`：沒有一個帳號有啟用中的 token，driver 對每個帳號印 `no active token; left out of the cross matrix` 後
     probe 就失敗（沒有可測的帳號）。
   - 舊收據：步驟 2、3 記下的識別碼，`GET api/operations/<id>`（帶那個帳號的 `X-MCP-Profile`）都回 410 `operation_restored`。
   - 核對後才重發：還沒核對時，面板停用那個帳號的「重新產生」並說明原因（後端對 rotate 回 409 `restore_review_required`、什麼都不寫，
     LOCAL 驗）；按「已核對」後重新產生成功。每個帳號都核對、重新產生後 P9 `--cross` 全過，測試用戶端換新權杖。
5. **重新啟動 add-on**：log 沒有新的 `restore guard` 行（守門已做完）。
6. **沒開通的 app 也做一輪**（單帳號，DQ-03 (b)）。只有預設帳號，前置和步驟 1～4 不同：
   - 前置：記下 T-01 的版本；`ha jobs info` 確認沒有別的備份或還原在跑。不加帳號、不跑 P9 `--cross`。一個測試用戶端接預設帳號
     （Bearer 與密鑰網址各一個連線）。
   - 備份，之後在面板對預設帳號重新產生一次權杖；再還原，等 add-on 起來。不查舊收據：沒開通又沒有帳號資料時，守門不封存收據。
   - log 與面板：沒開通的產品沒有 sentinel，只看訊號 1。有 `bootstrap: re-owned N restored entries in /data/mcp` 那行（訊號 1）時，
     才有 `KEPT_NOTICE`（`restore guard: the data was restored from a backup; the MCP token is back to …`）剛好一行，面板也才顯示
     還原提示。沒有那行時，log 沒有任何 `restore guard` 行、面板沒有提示，照實記下（這次還原沒被偵測到）。同時有
     `bootstrap: WARNING: … restore marker (.restore-detected) could not be saved` 那行時，標記沒存成，也不會有 `KEPT_NOTICE` 與提示，
     一樣照實記下。不管哪一種，都沒有 `REVOKED`。
   - 權杖是備份當時的值：測試用戶端照樣能用，備份後重新產生的權杖失效。有提示時，重新產生權杖後提示消失；「知道了」只藏到重新整理。
     重新啟動 add-on 後沒有新的 `restore guard` 行（同步驟 5）。
7. 讀不到的帳號隔離與 C1-M1 攻擊序只在 LOCAL 驗（HAOS 上不造壞資料）；版本混搭照計畫 §10.6 第 6 點，回退與再升級見 T-20。
8. 證據記：還原的種類、兩個訊號各自有沒有觸發、上面每一項的結果、版本（T-01）、帳號的 log id。

### Nextcloud 開通的 HAOS 驗收（HM-22 交來；Nextcloud 的升版片做）

LOCAL 的對應在 `tests/test_nextcloud_multi_profile.py`（假 Nextcloud、真的 Nextcloud 子程式）；下面是 HA 層要補的。每一步要使用者批准，
真後端身分的建立與刪除也是。

1. **前置**（T-01）：記下版本與映像 digest。同一台測試用 Nextcloud 上準備三個專用使用者 A、B、C（C 只給換帳號用），各自建一個 App 密碼；
   每個人的家目錄放一個只有自己有的標記檔，不分享給別人。
2. **WebDAV 互看不到**（T-04）：預設帳號接 A、一個額外帳號接 B。各自的 `get_file_tree`、`read_text_file` 只看得到自己的標記檔；拿 A 的網址讀
   B 的標記檔路徑（反之亦然）都找不到（404）。開放寫入時，寫入只出現在自己的家目錄。
3. **換帳號換 token**（T-03）：B 的帳號改成 C（username 與 App 密碼）：存檔提示權杖已換新，B 的舊網址兩條入口都失效（Bearer 401、密鑰網址
   404），新網址只看得到 C 的檔。只換 App 密碼、只把網址的主機改成大寫，權杖都不變。
4. **存政策只重啟該帳號**（T-07）：存 B 的工具政策，診斷頁 B 的子程式 `starts` 加一、A 的不變（診斷頁沒有 PID；add-on log 的
   `MCP child [profile=… pid=…]: started` 看得到新 PID，但同一個帳號 60 秒內只寫一行），A 的用戶端不斷線。
5. **只由 token 決定帳號**（T-05、T-23）：P9 `--cross`（兩種接法、跨帳號 session 404、隨機 token）；容器探針的多帳號階段。
6. **節流單位**（UC-12，2026-11-24 展示機確認：**以來源位址計**；見 [ha-test-nextcloud-0.5.0](ha-test-nextcloud-0.5.0.md)。B 用錯密碼存 5 次後，add-on 的位址記 4 次、新登入延遲 1,600 ms，同一個 add-on 的其他帳號的新登入也被延遲；已登入的連線不受影響）：讓 B 用錯的 App 密碼失敗登入幾次（子程式每次啟動只失敗一次：在面板重新啟動 B 的子程式或重新存 B 的後端，
   每次多一次；延遲隨同一來源的失敗次數變長，只失敗一次可能量不出來），量 A 接著的登入有沒有變慢或 429；用
   `occ security:bruteforce:attempts <add-on 的位址>` 直接讀那個位址的紀錄，看 Nextcloud 的暴力破解防護是以位址還是使用者計。會在真的
   Nextcloud 留下失敗登入紀錄，做完用 `occ security:bruteforce:reset <add-on 的位址>`（或管理頁）清除。結果寫進 DOCS（每個帳號共用
   add-on 的位址）與這份文件。
7. **清理**（T-29）：刪掉額外帳號、撤銷測試用的 App 密碼、刪掉測試使用者；合成憑證清單掃描 0 命中。

### 每次升版都要重驗（每個開通的產品，每一版）

- **UC-08 還原偵測**：在 QA HAOS 做 full、partial、加密備份各一次還原，記下兩個訊號各自有沒有觸發（`/data/mcp` 屬 root 而留下
  `.restore-detected`；sentinel 判 `mismatch`）。有一種還原兩個都不觸發，就不出貨（DQ-39 (a)）。
- **sentinel 穩定性**：`.instance-sentinel` 的 inode 與 ctime 在 add-on 重啟、**主機重開**、add-on 更新、Supervisor 更新之後都不變
  （和 `.instance-record` 比）；記下資料分割的檔案系統。
- **UC-10 Ingress**：Ingress 照原樣轉送 `X-MCP-Profile` 與 PATCH、DELETE（不通時才改用網址路徑的備案，DQ-17）。
- **記下 Supervisor 版本**（也記 Core、HAOS 版本）：Supervisor 的還原與 Ingress 行為會隨版本變，上面三項的結果只對記下的版本成立。
  Store 同步後從 Store 安裝或升級，再驗一次（Odoo 首發標準第 11 點）。
- HM-03a／b 寫回了局部還原的 UC-08、UC-10，以及 sentinel 在 add-on 重啟、冷備份、add-on 更新之後的穩定性（見「多帳號驗收」開頭的狀態；
  2026-11-19 HM-18 補寫 UC-10 與 sentinel）。其餘項目寫回之前，不得宣稱成立，也不得把容器或本機的模擬、或發版前預驗當成這一版的 HA 證據；
  寫回的項目也只對記下的版本成立，每次升版照上面重驗。

### LiteLLM 開通（HM-21；升版 PR 建好候選映像之後才做）

LiteLLM 沒有產品專屬程式（計畫 §9）：帳號能做什麼完全看存進去的 key。HAOS 上要證明的是「同一台 LiteLLM、兩把只限一個模型的
virtual key，各自的帳號只看得到自己的模型」。每一步照上面的規定先取得使用者批准；本機已涵蓋的項目見
`tests/test_litellm_multi_profile.py`（LOCAL）。

- **在測試副本上做**：升版 PR 的分支暫時加成商店 repo、裝 LiteLLM 的測試副本（同 0.4.14 的做法，[ha-test-0.4.14.md](ha-test-0.4.14.md)），
  不動已在用的 LiteLLM MCP app：T-04 會把預設帳號的後端換成 key A。負責人若決定在在用的 app 上做，動手前記下預設帳號原本的後端
  （只記哪一台 LiteLLM、哪種 key，不記秘密），清理時由負責人還原。
- **後端身分（負責人建立、刪除；證據只記不含秘密的摘要）**：同一台 LiteLLM 上兩把 virtual key，A 只允許模型 a、B 只允許模型 b；
  不用 master key（面板也這樣建議）。key 只經面板或 P9 的 `--backend-file`（0600）填入，不印、不貼進紀錄。模型名稱不是秘密，可以記。
- **T-02**：LiteLLM 的額外帳號上限是 3：第 4 個額外帳號 409 `profile_limit_reached`、`limit` 3。
- **T-04（N×N）**：預設帳號存 key A；面板建帳號 B、存 key B（同一個網址）。兩個帳號各用自己的 token、兩種接法呼叫
  `litellm_list_models`：預設帳號只列出模型 a、B 只列出模型 b。
- **T-05**：P9 `--cross`（兩種接法、跨帳號 session 404、隨機 token、`X-MCP-Profile` 不換帳號）與 `--temp-profile`（刪除後舊 token
  被拒：Bearer 401、密鑰網址 404）。
- **T-07**：在 B 收回全部寫入授權並停用一支讀取工具，存檔後只有 B 的子程式重起（容器裡兩個子程式的 PID 存檔前後對照，或 add-on
  log 生命週期那幾行帶的 id 前 8 碼），B 的 tools/list 沒有寫入工具與那支工具；預設帳號的工具清單與 PID 不變。
- **T-13、T-14、T-17**：同其他開通的產品（P9 `--profile … --modes childkill`、`restart`；每個 LiteLLM 子程式的 RSS 對契約第 5 節
  暫定的 160 MiB）。
- **只在 LOCAL 驗**：每個子程式最多 4 條後端連線、一個帳號占滿不影響別的帳號；占滿時健康檢查也拿不到連線，超過 5 秒又碰上檢查
  （開通後連兩次）就把這個帳號判成 unreachable，新的 tools/call 回 `-32603`「Backend unreachable」直到下一次檢查通過（契約第 9 節
  #129；要不要放寬或改健康檢查由負責人決定）。要在 HAOS 驗，用 T-04 那台 LiteLLM，負責人決定。
- **清理（T-29）**：刪掉帳號 B 與 T-02 建的帳號（舊 token 立刻失效）、刪掉測試副本（在在用的 app 上做的，由負責人還原預設帳號的後端）、
  負責人撤銷兩把 key，合成憑證掃描 0 命中。

## 故障處置界線

缺少／失效角色（非 owner／系統管理員）的 MANAGEMENT 403 屬預期封鎖，不是要求提高 HA 權限。readiness503 要分
未設定／backend 無法連線；不要無限重啟。`BACKEND_BUSY` 表示有界 resolver/tool
容量已滿，等候或停止本新 Add-on 的核准恢復即可，不增無界 thread。TLS/redirect/
metadata DNS 拒絕要查 canonical backend 與憑證，不關驗證。來源 hash drift 須重新
審查依賴／launcher，不刪 hash guard。EMQX 真節點證據、LiteLLM 模型列表、Hermes／
OpenDesign API 版本不符需逐產品確認，不泛化為六支健康。
