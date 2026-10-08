# 六類 adapters：本地 W2a 契約

已接入真實固定 runtime，不是假工具／空 server。範圍仍為 bounded 本地實作；W2b 工具擴展、W3 GUI／HA manifests／CI 不在本批。完整 184-tool inventory 在 `tool-surface.json` / `tool-surface.md`；支援 27 個（含 n8n 原 4 個），157 個明列暫不支援，絕不因 writer 開關自動放行。

## 安裝及启动（只限本地 disposable state）

```sh
uv sync --frozen
for p in odoo odoo-manage hermes opendesign emqx litellm; do
  uv sync --project apps/$p --frozen --no-dev
done
PYTHONPATH=packages/mcp-admin-core .venv/bin/python -m mcp_admin_core.run_product emqx \
  --data /tmp/disposable-emqx-state --host 127.0.0.1 --admin-port 8099 --mcp-port 8081
```

尚未配置的六類不启动 child、不發 backend request，health 真實 unconfigured、readiness=503。不以 credentials/default hosts 猜測後端。n8n 仍可在無後端下讀內建文件。

目前 production admin verifier **缺省拒絕**，沒有 CLI trust bypass；不提供把現有服務 credential 填進示例的操作。tests 使用受測 test-only verifier 或程式建立 disposable dummy state，不能將它當 HA admin approval。

child 一律 127.0.0.1:3000/mcp，不能對外映射。管理與 MCP 各自 listener；Uvicorn 不接受 forwarded peer，核心 Bearer／CSRF／stream revoke／unknown policy／process-group lifecycle 保留。child 的 argv 與 env 由 adapter 固定，沒有 Supervisor token、外部 MCP token、parent proxy/plugin/env，工作目錄與 HOME 是專用空目錄，不是 GUI state/source/home；發現既有檔案或 symlink 拒絕 launch。child stdout/stderr 不出公開 log。

## 真實 child 契約

| Product | Transport / runtime | Typed connection（exact fields） | 自動 read probe |
|---|---|---|---|
| Odoo | wheel 1.1.0；source-guarded `apps/odoo/launch.py` → 原 CLI native HTTP | url, database, username, password | 0.1.3 起子程序私有 `woow_backend_probe`（不在 TOOLS；以新 client 只做 authenticate，自己的 owned thread）；需恰好 `{"uid": 正整數}`（0.1.2 以前為 list_models(limit=1)、需 success=true + result array） |
| Odoo Manage | wheel 0.7.1；source-guarded `apps/odoo-manage/launch.py` → 原 CLI native HTTP | url, database, username, api_key, mode=read | 0.1.4 起子程序私有 `woow_backend_probe`（不在 TOOLS；以新連線只做 connect＋authenticate，自己的 owned thread，從不用 session 共用連線）；需恰好 `{"uid": 正整數}`（0.1.3 以前為 list_models、需 models array + yolo_mode.operations.read=true，最小權限帳號一律 unreachable） |
| Hermes | 新固定 SDK native HTTP launcher，原真實 handlers | gateway_url, gateway_api_key；可選 dashboard_url/username/password 必須整組提供 | hermes_inspect(target=capabilities)；capabilities object，不能有 capabilities_error |
| OpenDesign | 新固定 SDK native HTTP launcher，原真實 handlers | url（無虛构 backend token） | health；只認 status=ok/healthy，或（0.1.4，OpenDesign 0.21.1 實機）`ok` 為 true 且 `version` 為非空字串；其他 shape 顯示 unreachable |
| EMQX | pinned public source `--transport http --host 127.0.0.1 --port 3000 --path /mcp` / FastMCP3.4.5 | url（不含 /api/v5）, api_key, api_secret | emqx_cluster_status；非空真實 node/version evidence、unique nodes、node_count 一致 |
| LiteLLM | pinned public source 同固定 HTTP args / FastMCP3.4.5 | url, master_key | litellm_list_models；data array，不用可能付費 /health |
| Nextcloud（0.1.7） | vendored `nextcloud_mcp_server` v0.1.4（`-m nextcloud_mcp_server.server` 同固定 HTTP args）/ FastMCP3.4.5 | url（根網址）, username, app_password | 子程序私有 `woow_backend_probe`（不在 TOOLS；每次新 client 讀一次 OCS `cloud/user`）；需恰好 `{"ok": true, "user_id": 非空字串}`。代表性公開讀取 `get_file_tree`（home）：path 為空字串、truncated 為 boolean、entries 格式正確 |

Manage 只啟用 upstream XML-RPC YOLO **read**，不是 full YOLO，也不安裝 Odoo-side module。初始化需要可用後端及認證；沒有 backend 的成功 initialize 不被編造。Odoo writes/unknown methods/chatter-direct 關閉；Manage arbitrary method calls 關閉。EMQX/LiteLLM readonly=true 作第二層防禦，不取代 outer gate。OpenDesign delete_project 是本批新增唯一六類 writer：必須 explicit writes_enabled=true、工具未 disabled、canonical UUID；只用 disposable fake daemon 驗證過。其餘 writer 擴展留 W2b，不能宣稱 writer 完整。

## 設定與 migration

六類 `PUT /api/backend` 僅接受 `{ "connection": <該產品 typed object 或 null> }`；extra fields 一律拒絕。不接受 arbitrary credential dictionaries、command/env、其他產品 connection 或舊 n8n `{url,key}`。null 清空整組並停止 child。Credential 只接受 printable ASCII 1–8192，不回傳普通 bootstrap。Dashboard cookie、backend session 在 credential 更新時經 child restart 丟棄。

v2 state 有 product discriminant；n8n executable 自動在 writer lock 下驗證完整 v1 後 atomic/fsync 升級，保留 GUI backend/token/child_token/endpoint/writes_enabled/disabled。舊 v1 reader 必須拒絕 v2，避免默默退版／丟資料；需事前保護好的 v1 backup 才可退回舊 executable。v1 不能當其他產品匯入，future/corrupt/incomplete 不寫回。這是本地 migration/rollback rejection 測試，不是 HA 備份還原驗收。

管理尚未批准時上述 HTTP mutators 不對真實使用者開通。W3 UI 需依 product 呈現 typed form／明確清除；本批沒有加權限旗標。

## 驗證邊界

`tests/test_real_products.py` 使用真正兩個 Uvicorn listener、六個獨立 upstream child、disposable loopback JSON/XML-RPC fake backend。驗證 initialize→initialized→tools/list→read call，raw upstream list 不超出 source inventory、Bearer 缺失／錯誤拒絕、unsupported resources/prompts/tasks/writer 直接拒絕、health backend outage、既有 session ping 仍成功、owned child signal cleanup。`test_real_product_writer.py` 用真實 OpenDesign handler 對 fake daemon DELETE；default deny→explicit allow→disabled deny，無正式資料操作。

聲稱的 transport 僅 **Streamable HTTP `/mcp`**（含收到的 SSE 回應）；不宣稱 `/sse`、stdio bridge、所有 client streaming/cancellation 相容性。核心既有 n8n GET disconnect/reconnect/rotation 測試繼續保留；不是六產品全 streaming E2E。

pytest 自動持有 `tests/conftest.py` 固定 port lock；勿另包 flock。獨立實驗須依 `n8n-tracer-contract.md` 使用相同 lock，發現其他 listener 不 takeover。

## W2a 本地 hardening（待獨立 review）

`apps/runtime/backend_policy.py` 在真實 HTTPX/XMLRPC transport 檢查 configured origin/base path；所有 DNS answers 必須通過與 n8n 相同的 address-class 排除，再以數字位址 connect，不二次 resolve 原 hostname。LAN/loopback/ULA/public 可用，metadata/link-local/reserved/CGNAT/mapped/transition 拒絕；HTTPS 保留原 hostname/SNI/certificate validation。HTTPX proxies 關閉；所有 backend redirect（含同源／relative）拒絕，需由管理員明確改 canonical URL。涵蓋 Hermes gateway、dashboard login/cookie，Odoo/Manage XMLRPC，及所有四產品 HTTPX constructors。不是 global SSRF bypass。

DNS/TCP 使用一個整體 monotonic deadline（client connect timeout；未指定時 5 秒），先驗證完整 answer set，再依原順序嘗試數字位址；每次分配 remaining budget / remaining addresses，拒絕／逾時不會令後續合法位址永遠失去機會。sync/XMLRPC 與 async 均支援同 family 與 IPv6/IPv4 fallback，不重查 hostname；TLS 仍驗證 configured hostname。這是 DNS/TCP deadline，不是整個 TLS/HTTP operation 的總期限。

所有 client instances（含 Hermes gateway、login、cookie）共用每個 child process 的 4-worker DNS executor 與 4-slot 非阻塞 admission；無等待 admission queue，滿載立即 `BACKEND_BUSY`。caller cancellation 或 DNS 等待逾時會立即停止等待，但 slot 只在真正 resolver future 完成時歸還；不另開 detached thread，不由新 transport 重建 limiter。executor threads 由 process 持有；任意卡住的系統 DNS 仍由 Supervisor group shutdown 硬邊界回收。

Odoo/Manage 使用 source-hash guarded launcher 取代 wheel transport，wheel 檔案及 notices 不變。新 patch ledger 在 `provenance/runtime-patches.json`。HTTPX/httpcore 及 SDK private integration 亦 fail closed on source drift；不可只升 lock 而不審查。

backend HTTP 非 2xx / XMLRPC fault 的公開錯誤是 bounded `BACKEND_HTTP_ERROR status=N`、`BACKEND_RPC_FAULT`、`BACKEND_UNAVAILABLE` 等，不轉送 raw body 或 raw transport exception；LiteLLM ToolError 也不例外。成功結果仍是既有 bounded tool 輸出，不宣稱任意 backend 成功資料全部 secret-free。

HTTPX headers 後的 lazy sync/async body iteration／close 亦經固定 `BACKEND_STREAM_ERROR`／`BACKEND_TIMEOUT` 邊界（httpcore cleanup exceptions 可能尚未轉成 HTTPX exceptions，兩者都涵蓋）。不 eager buffering、不新增 thread/task／resolver slot，不取代 HTTPX/core response close ownership；非 2xx cleanup error 不覆蓋原 status，cancellation／process signals 不被當一般錯誤吞掉。Hermes inspect error fields 以 exception type 映射，其他已啟用 Hermes/OpenDesign handlers 以保留 signature／dispatch 的 error-only boundary 包住 decoding／JSON／projection；EMQX/LiteLLM request/parser 公開固定 codes。成功 business payload 不做盲目 credential 搜尋／替換。

`test_stream_error_redaction.py` 重現真正 child/gateway 的 Authorization malformed-chunk 洩漏，涵蓋 dashboard login/cookie、sync OpenDesign、所有已啟用 HTTP tool 的 gzip／encoding／JSON 錯誤、JSON/SSE 全文 canaries；另在真正 HTTPX/core pool 注入 late read/timeout/close errors、檢查重複失敗／取消的 pool reuse 與 cleanup。獨立 spec verification 及 NEW security review 仍必須重新進行。

SDK 1.28.1 同步工具原本直接阻塞 event loop。OpenDesign 改 4-worker、Odoo 改 1-worker offload，無等待工作 queue；超載立即 `BACKEND_BUSY`，caller cancellation 不提前釋放執行中 slot。普通 I/O timeout 5 秒；slow-trickle/hung DNS 無法靠 thread cancellation 強制停止，既有 Supervisor 持有 child group 的 3 秒 SIGTERM grace / SIGKILL / reap 硬關機邊界，不將後端失效當 restart 理由。0.1.3 起 Odoo 的健康探測是子程序私有的 `woow_backend_probe`（不在 TOOLS，gateway 不列出也不授權）：只以新 client 驗證登入（authenticate），在自己的 1-thread owned executor 執行（同樣無等待、取消不提前釋放），從不佔使用者的 1-worker（因此 Odoo child 對後端最多 2 個並行連線：工具 1＋探測 1；DNS resolver 的 4 個 admission 名額仍共用）；0.1.2 HA 回歸時探測（`list_models`）在 Odoo 剛重啟、回應慢時佔住該 worker，使用者讀取全回 `BACKEND_BUSY`。

`test_resolver_regressions.py` 補 stock/pinned localhost 對照、IPv4/IPv6 fallback、DNS+TCP budget、真實 OpenDesign/Hermes health/readiness、Hermes gateway 三波 24-call cancellation/DNS capacity/reuse/ping/group reap 及實際 gateway/login/cookie/sync/XMLRPC 共用 admission。

新增 tests：`test_six_hardening.py`（真實 handler/gateway redirect、JSON/SSE error canary、dashboard cookie、slow/hung/burst、EMQX health/readiness），`test_six_egress.py`（六類實際 backend client + synthetic DNS/intercepted sockets），`test_backend_policy_python.py`（address classes、pinning、origin/path、owned HTTPS certificate/SNI/redirect）。不向真實 metadata 位址送封包。

三種 health 分開：management alive/state_error、child lifecycle/protocol ready、backend unconfigured/unreachable/reachable。健康 probe 是獨立 internal 呼叫（Odoo 0.1.3 起、Odoo Manage 0.1.4 起只驗證登入，其餘產品是 read），不受 client disabled 名單影響，不啟用 client call。backend outage 不 restart child/container，readiness 不可作 restarting watchdog。HA admin-role、六類 hardening 的新獨立安全審查、backend 實際版本／least-privilege、Docker/HA/client/backup/CPU-RSS 等仍待實測；詳見來源文件及 BLOCKERS。
