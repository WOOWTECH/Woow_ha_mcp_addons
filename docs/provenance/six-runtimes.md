# W2a runtime provenance / 授權範圍

本批是本地實作與假後端驗證，**不是七產品完整驗收、現行映像來源證明或公開授權 clearance**。

## 固定輸入

| Product | Artifact | License / notice |
|---|---|---|
| Odoo | PyPI `odoo-mcp==1.1.0`; wheel SHA256 `65bde67381eee0dc0f9f716bf01ef056e81c2a4d601b221543b013abfcf049bc` | MIT；`odoo-LICENSE` 保存原文，2025 Lê Anh Tuấn |
| Odoo Manage | PyPI `mcp-server-odoo==0.7.1`; wheel SHA256 `59675b12f2e79e26383d618bd8e1c54aacb7a512ae00be9cd1392f3cf334684c` | **MPL-2.0**；`odoo-manage-LICENSE` 保存全文；相應源碼／發佈通知義務待 release review |
| Hermes | read-only `woow-mcp-server@614ae663fadd91c76972f60017a76d2627bea87e`, app `hermes_mcp_server/server.py` only | app MIT 2026 WOOWTECH，`apps/hermes/vendor/LICENSE` |
| OpenDesign | 同 SHA，app `opendesign_mcp_server/od_mcp_server.py` only | app MIT，`apps/opendesign/vendor/LICENSE`；原 vendor header 提及 `d6d157a` 的獨立完整來源鏈仍待查證 |
| EMQX | PUBLIC `WOOWTECH/Woow_emqx_mcp_server@1be17bad5aef6c7b7519686ccbfe1d80762bc10e` | MIT，`apps/emqx/vendor/LICENSE`；不是現行 image→commit attestation |
| LiteLLM | PUBLIC `WOOWTECH/Woow_litellm_mcp_server@4d4190369216a2d068d1100d53406a67a1d81609` | MIT，`apps/litellm/vendor/LICENSE`；不是現行 image→commit attestation |
| Nextcloud（0.1.7，未發佈） | PUBLIC `WOOWTECH/Woow_nextcloud_mcp_server@1f94258bbfaa92f2693c60e7905c86ef2efb711a`（tag v0.1.0；上游在 `src/` 底下，`vendor_runtimes.py` 以 `SOURCE_PREFIX` 對應） | MIT，`apps/nextcloud/vendor/LICENSE`；尚無映像 |

逐檔 upstream SHA256／本地修改 SHA256 見 `runtime-sources.json`，由 drift tests 驗證。`scripts/vendor_runtimes.py` 是明確 allowlist：只抓必要 runtime `.py` 與 LICENSE；不下載 repository archive/history、admin/UI、deployment、examples、設定或 credentials。既有 vendor 目錄拒絕覆寫，更新需另 staging 及 review。Hermes/OpenDesign 不匯入 legacy shared core/UI/launcher。

## 本地修改

- 七個 vendor 檔案有明確本地差異（逐檔 upstream/local hashes 見 `runtime-sources.json`），原 LICENSE 全保留。
- OpenDesign：要求 explicit `OD_API_BASE`；兩個 HTTP client 路徑都用 scoped DNS-pinned transport，普通 I/O timeout 5 秒；launcher 用 4-worker bounded SDK offload。無虛构 token。
- Hermes：gateway、dashboard password login、dashboard cookie 三個 client 全部套 scoped transport。
- EMQX/LiteLLM：pooled client 使用相同 scoped transport；公開錯誤不含 raw backend body。LiteLLM invalid JSON 不再回傳 raw text。EMQX nodes 在 projection 前驗證，不能把 generic object 正規化成健康空叢集。
- 新寫 `apps/{hermes,opendesign}/launch.py` 使用固定 SDK native HTTP（127.0.0.1:3000/mcp），不是 legacy wrapper。
- Odoo/Manage 原 wheel 檔案不變；新 `apps/{odoo,odoo-manage}/launch.py` 在執行原 CLI 前替換實際 XMLRPC transport，**source SHA256 guard fail closed**。拒絕所有 redirect、檢查 origin/base path、DNS pinning、保留 hostname/SNI/TLS 驗證及 Manage database header；不是 legacy patches，沒有 singleton 猜測。
- 新 `apps/runtime/backend_policy.py`、`bounded_tools.py` 是 scoped 本地程式，不改 global DNS/socket/SSRF；HTTPX/httpcore 及 SDK private integration 也有 source-hash guard。Odoo sync tools 只允許 1 worker（避免 cached XMLRPC transport race），OpenDesign 4；無等待工作佇列、超載回 BACKEND_BUSY、取消不提前釋放 slot。0.1.3：Odoo 健康探測改為子程序私有 `woow_backend_probe`，只驗證登入、在自己的 1-thread owned executor 執行（`OwnedWorkers`），不佔使用者的 1 worker。0.1.4：Odoo Manage 同樣改為私有 `woow_backend_probe`（每次新連線只做連線與登入，不碰 session 共用連線）。關機硬期限由原 Supervisor process-group SIGTERM→SIGKILL/reap 持有。
- Resolver 修復只改共用 `backend_policy.py`，無新增 vendor 差異／依賴版本：完整 DNS answer validation 後，在單一 DNS/TCP deadline 內以數字位址 fallback（sync/XMLRPC/async）；所有 client 共用 process-wide 4-worker executor / 4-slot immediate admission，取消／逾時不提前歸還仍執行的 resolver slot。既有 hostname/SNI/TLS、混合禁止位址 fail-closed、group reap 邊界不變。
- Response-stream 修復：共用 transport 回傳 lazy sync/async wrapper，iteration／close（含 httpcore 直接丟出的 cleanup exception）映射為固定 `BACKEND_STREAM_ERROR`／`BACKEND_TIMEOUT`；非 2xx cleanup 保留 status error 優先，不 catch cancellation、不 eager buffering。Hermes inspect 不再公開 `str(exc)`；其他已啟用 Hermes/OpenDesign handlers 明確加 error-only boundary，保持成功結果、signature、同步 offload；EMQX/LiteLLM request/JSON parser 使用安全固定 codes。四個 vendor 檔案更新既有 local hashes，總數仍七個。
- Nextcloud（0.1.7）：上游本來就在啟動時載入 `backend_policy.async_client`；本地修改五個檔案（逐檔原因見 `runtime-sources.json`）：
  ① 不再把 `follow_redirects`／`trust_env`／`transport`／`verify` 傳給 `async_client`（v0.1.0 原樣在第一次呼叫就 TypeError，TLS 一律驗證）；
  ② `backend_policy` 改為必要匯入，所有後端失敗經 `public_backend_error()` 成為公開代碼，非 2xx 仍帶 status 給工具的 404/412 處理，
  轉址目標與 Sabre 錯誤訊息不讀也不轉；③ 子程序私有 `woow_backend_probe`（每次新 client 讀一次 OCS `cloud/user`，只回 ok／user id，
  不佔工具的連線，不在 `ALL_TOOLS`，gateway 不列出也不授權）；④ WebDAV 解析錯誤與帳號查詢錯誤加上公開代碼；⑤ 錯誤訊息不再帶後端給的使用者路徑。
- 新 adapter hashes、guarded wheel/SDK sources、修改理由見 `runtime-patches.json`；inventory 包含 launcher/helper digests，升級需重新審查。
- 共用 `products.py`、`run_product.py`、tests/scripts、既有 boundary 擴展是本次新寫／修改，不直接複製 legacy shared 授權不明程式。未納入的 legacy shared 授權疑義不作此新寫程式永久 blocker。

## BATCH2 B1（待獨立審查）

來源版本與 wheel/vendor bytes 不變。新增 core `batch2.py` 嚴格10工具 schema，`apps/runtime/batch2_outputs.py` 正向 partner-count/template metadata 投影；Odoo launcher 在原 sync handler 外投影後仍交原 bounded worker，Manage 在原 async handler 完成後投影，不新增 detached work 或 network client。Odoo pure helper/aggregate 與 Manage tools.py 加 source hash guard；新增 hash/reason 見 runtime-patches.json。n8n 仍使用原 scoped API client，只限制 create response 為 bounded inactive metadata；完整 pinned validator helpers 新增 inventory digests。原 complete EMQX/LiteLLM native name inventory 與 effect/operation baseline 不變；65/184不是全產品完成。

## 依賴隔離與可重現性

每類 `apps/PRODUCT/{pyproject.toml,uv.lock}` 是獨立 project，`.venv` 不入 Git。六類 SDK 固定 `mcp==1.28.1`、HTTPX `0.28.1`；EMQX/LiteLLM 固定 `fastmcp==3.4.5`（含同版本 slim client/server extras），lock 的 Starlette `1.7.0` 與 core `0.49.3` **隔離**。完整依賴 URL/hash 由各自 uv.lock 保存，不能只把 direct pin 當完整 graph。

本地使用 Python 3.13.2；各 child project 限 `>=3.13,<3.14`，與目前 core 一致。未宣稱原規劃 Python 3.12 image 已建置；W3 必須選擇並實測 image Python 版本。`uv sync --project apps/PRODUCT --frozen --no-dev` 可重建本地 child；無 system-wide pip install。n8n npm pin 2.91.0／原 lock／network policy 未升級。

FastMCP 依賴 Apache-2.0 及其他 third-party 義務仍需 SBOM/NOTICE/敏感掃描；不宣稱全部 image MIT。Odoo Manage 對應源碼可由其 uv.lock 所列固定 sdist URL/hash 追查，尚未完成對外分發義務審核。

## 未完成 gate

依賴／app source/public history/image 敏感及授權總審、OpenDesign vendor 完整源頭、MPL release source offer、映像建置、HA admin-role 權限批准、真實版本／受限 backend／Ingress/LAN/client 測試、HA backup/restore。六類已補本地 scoped egress/redirect/error/offload/health 修復及負面回歸；允許 LAN/loopback/ULA/public，拒絕與 n8n 相同的 metadata/link-local/reserved/CGNAT/mapped/transition 範圍，驗證每個 DNS answer 並 pin connect，原 hostname 驗證/SNI 保留。這是本地證據，不是 n8n approval 外推；仍需先獨立 spec review、再 NEW security review。
