# Management capabilities v1

The authenticated `GET /api/capabilities` is additive. Existing bootstrap, backend,
policy, endpoint, token, ingress role checks and MCP transports remain available.
No state schema or default grants change in this work.

## Upgrade boundary

The existing standalone `ProductStore` migration is unchanged: schema 1/2 states
pass through earlier migrations, and schema 3→4 clears disabled tools and enables
all write grants once (except the retired Odoo Manage product). This was the prior
0.2.0 owner decision. A 0.1.14 installation can therefore change policy when first
opened by this candidate, even though the new management routes do not edit policy.
Do not describe that upgrade as preserving all prior restrictions.

Preservation tests for these additions cover **schema 4**: an already-migrated
state with revoked token, disabled tool, empty write grants, saved endpoint and
backend survives backend checks, child restart and reopening byte-for-byte.
Existing-addon upgrades from older schemas are deferred to root's explicit policy
and rollback plan. Local tests use disposable state. The builtin compatibility
backport separately retains its schema-3 store and bounded 15-tool policy; it must
not import the standalone full-surface migration.

The snapshot follows the parent parity contract (`schema_version: 1`): deployment,
product/version, admin authority, backend features, management features, layered
health, and tool catalog. Public endpoint health stays `unverified`: saving an
endpoint or successfully listing tools does not verify an external connection.

Tool catalog is the union of the policy registry, pinned catalog and the child's
observed `tools/list`. Unknown runtime tools remain visible but policy-disabled;
observation never grants new tools. Catalog count, policy-enabled count and effective
count have separate meanings. Effective means both registered by the observed child
and allowed by current gateway policy. It does not prove a backend call will work.
When observation fails, effective count is null and permitted tools have null
`effective`; denied tools remain false. Status is `observed` or `unknown`.

Full-surface tools use observed child input schemas, falling back to the pinned
snapshot with explicit `schema_source`. Bounded adapters use their registry model
because that is what their gateway accepts. Operation entries describe the existing
read/write classifications and exact grants, without replacing the policy contract.
Bootstrap retains its original fields and includes an unobserved capability snapshot;
the new UI explicitly reads the observed snapshot. Probe sessions paginate with
bounded time, pages, bytes and tool count, and close even on cancellation.

| Route | Meaning |
| --- | --- |
| `GET /api/capabilities` | Bounded child initialize/list observation and effective policy snapshot |
| `POST /api/backend/test` | Read-only probe using saved configuration, no request body |
| `POST /api/child/restart` | Restart using saved configuration, no request body; HTTP 202 with `accepted: true`, `apply_state: pending` |
| `GET /api/diagnostics` | Child health plus bounded, redacted stdout/stderr entries |

Every route uses the same trusted ingress peer, identity and fresh role checks as
the existing API. POST additionally requires the bootstrap's CSRF token. Body-bearing
check/restart requests are rejected, so drafts cannot silently become test settings.
A successful backend-check HTTP response means the check completed; its `backend`
field separately reports reachability. Restart acceptance does not mean ready.
The restart keeps the mutation lock and joins process-group cleanup after caller
cancellation or disconnect. It does not rotate the token or save configuration.

Diagnostics retain at most 200 entries and 128 KiB in memory. Lines over 8192 bytes
are dropped whole, including lines split across reads. Known environment credentials,
encoded variants, Authorization values, secret assignments, URL userinfo and private
MCP token paths are scrubbed before retention. Reader tasks drain both pipes during
cleanup and are joined before replacement. This is child output, not backend logs,
and retention resets with the management process. No raw environment or argv is exposed.

## Builtin adapter hook

```python
from mcp_admin_core.capabilities import ManagementOptions

admin, mcp = make_apps(
    store, tools, child,
    # Keep the deployment's existing identity/role adapter.
    verify_admin=verify_admin,
    health=health.snapshot,
    management=ManagementOptions(
        kind="builtin",                 # ha-addon | paas | builtin
        authority="ha-ingress",         # ha-admin | ha-ingress | paas-password
        backend_mode="fixed",           # manual | fixed
        backend_can_edit=False,
        product_version="0.2.2",        # optional; defaults to core VERSION
    ),
    backend_check=health.test_saved,     # optional async(state) -> check result
    restart_child=backend_changed,      # optional async(state) -> None
    diagnostics=manager.diagnostics,    # optional () -> {child, logs}
)
```

Omitted callbacks advertise unavailable features and their routes return structured
409 `unsupported`. A fixed backend must have `backend_can_edit=False`; valid backend
replacement/clear requests then return 409 `backend_fixed` without saving or restarting.
The UI hides that form and uses deployment/authority labels rather than assuming HA.
These options are metadata and action restrictions, never authentication overrides.
A builtin can retain its bounded Tool models, existing store and migrations; no
full-surface migration is required. Older Tool classes can omit `child_schema` and
`read_operations`.

The optional callback contracts are trusted runtime hooks, never HTTP-supplied commands.
`backend_check` returns `tested_configuration: "saved"`, `checked_at`, `health`,
`backend`, and optional `reason`; `HealthMonitor.test_saved` supplies this shape.
`restart_child` must preserve the runtime's owned stop/reap/start behavior.
`diagnostics` returns `Supervisor.diagnostics()`'s shape; logs include `entries`
(`at`, `stream`, `generation`, `text`), `dropped`, byte/count bounds, and `redacted`.

## Local verification scope

Regression coverage lives in `tests/test_management_capabilities.py`,
`tests/test_child_diagnostics.py`, the existing lifecycle/role suite, and
`packages/mcp-admin-ui/tests/{capabilities.test.mjs,browser/capabilities.spec.mjs}`.
Owned fake child/backend tests do not establish HAOS ingress or live backend acceptance.
Root owns deployment, live verification and version changes.

## 多帳號（產品開通後）的管理路由與能力

這一節照多帳號契約 `docs/multi-profile/contract.md`（HM-18 定稿）寫；**Odoo 從 0.5.1 起，LiteLLM、Nextcloud、EMQX、Hermes、n8n、Headscale 從各自的 0.5.0 起開通（HM-19a、火車 A、火車 B），只有 OpenDesign 與 Odoo Manage 不開放**。沒開通的產品照上面各節：`/api/profiles*` 與
`/api/origin-policy` 是未知操作（角色檢查之後 404），不要求、不看 `X-MCP-Profile`，每個回應一個位元組都不變。下面是摘要，逐條以契約為準。

**全域路由**（不看 `X-MCP-Profile`；契約第 3.1 節）：

| 路徑 | 方法 | 用途 | 寫入保護 |
|---|---|---|---|
| `{base}/api/profiles` | GET | 帳號清單（含 `orphans`；有隔離目錄時另帶 `quarantined`；`ETag: "p1-<64 hex>"`） | — |
| `{base}/api/profiles` | POST | 建立 `{"label":…}`（回應不含權杖） | If-Match（索引）＋Idempotency-Key |
| `{base}/api/profiles/<id>` | PATCH | 改名 | If-Match（索引） |
| `{base}/api/profiles/<id>` | DELETE | 刪除（先撤銷權杖、抹掉後端憑證；孤兒與讀不到的帳號也收） | If-Match（索引）＋Idempotency-Key |
| `{base}/api/profiles/revoke-all` | POST | 全部撤銷（含預設帳號；逐帳號結果） | If-Match（索引；索引不能用時是壞索引的 ETag）＋Idempotency-Key |
| `{base}/api/profiles/restore-record` | GET | 還原與休眠核對紀錄（不含秘密） | — |
| `{base}/api/profiles/<id>/restore-review` | POST | 標記「已核對」 | If-Match（索引）＋Idempotency-Key |
| `{base}/api/profiles/index/quarantine` | POST | 隔離不能用的帳號索引（DQ-12） | If-Match（壞索引的 ETag）＋Idempotency-Key |
| `{base}/api/profiles/quarantine/<名稱>/delete` | POST | 刪除一個隔離目錄 | If-Match（索引）＋Idempotency-Key |
| `{base}/api/origin-policy` | GET、PUT | 密鑰網址的 Origin 政策（全 add-on 一份；PUT 要 If-Match（政策 ETag `"o1-…"`）＋Idempotency-Key）；Headscale 回 404 | 見左 |

**帳號範圍路由**（其他 `{base}/api/*`，含本文件上面的 `capabilities`、`backend/test`、`child/restart`、`diagnostics`）：開通後一定要剛好一個
`X-MCP-Profile`（`default` 或 24 位小寫 hex；缺 400 `profile_id_required`、多個或格式錯 400 `profile_id_invalid`、不存在 404 `profile_not_found`；
索引不能用時額外帳號 503 `profile_index_corrupt`）。`capabilities` 與 `configuration` 的回應帶 `profile:{"id"}`；`backend/test` 測選定帳號已存的設定；
`child/restart` 只重啟選定帳號的子程式，202 回應多 `blocked_reason`；`diagnostics` 只回選定帳號的子程式緩衝。額外帳號的 `owner-defaults/*` 回 409
`owner_defaults_unavailable`、`PUT endpoint` 回 409 `endpoint_global`。

**管線**（契約第 3.2 節）：開通後所有路由走同一條：identity（Ingress 來源、剛好一個 `X-Remote-User-Id`、非 GET 要 CSRF）→ 管理名額 → 讀 body →
方法表與不讀狀態的格式檢查 → **角色檢查** → 解析 `X-MCP-Profile` → 拿鎖 → 讀狀態 → 第二次角色檢查 → If-Match、Idempotency-Key 等狀態相依的判斷 → 提交。
非管理員最遠只到角色檢查：任何帳號狀態下都拿到逐位元相同的 403。開通後 PATCH、DELETE 只有 `profiles/<id>` 收；PATCH、DELETE 沒過 identity 從 405 變
identity 的 403（`X-Ingress-Path` 格式錯時 400），表外方法（OPTIONS 等）的 405 `Allow` 從 4 個方法變 6 個（契約第 1.4 節第 4 點）。

**各產品的額外帳號上限**（契約第 5 節；暫定，HM-19c 在目標硬體量測後定案）：

| 產品 | 額外帳號上限 | 每個子程式的記憶體估計 |
|---|---|---|
| Odoo | 5 | 100 MiB |
| n8n | 2 | 300 MiB |
| Hermes、EMQX、LiteLLM、Nextcloud、Headscale | 3 | 160 MiB |
| OpenDesign、Odoo Manage | 0（不開放，建立回 409 `profile_product_unsupported`；DQ-28） | — |

記憶體不夠（MemAvailable 減保留量 256 MiB 放不下再一個子程式）時建立回 409 `profile_memory_insufficient`（另帶 `required_memory_mib`、`available_memory_mib`）；
開檔數上限提不到需要量時只服務預設帳號，建立回 409 `profile_limit_reached`、`limit` 是 0。

**錯誤代碼**（新增的都在 `detail.code`，本體 `{"error":"request denied","detail":{"code":…}}`，不帶伺服器文字；既有的五種本體形狀照舊。全表含欄位、管線步驟與
PaaS 對照在契約第 4.1 節）：

| 代碼 | HTTP | 什麼時候 |
|---|---|---|
| `profile_id_required` | 400 | 帳號範圍路徑沒帶 `X-MCP-Profile` |
| `profile_id_invalid` | 400 | 帶兩個以上，或不是 `default`、24 位小寫 hex |
| `profile_not_found` | 404 | 格式對但帳號不存在（含孤兒、隔離目錄、已刪除的） |
| `profile_label_invalid` | 422 | 名稱違反規則（去頭尾空白後 1～80 個 code point；拒絕控制、bidi、零寬等字元） |
| `profile_default_immutable` | 422 | 改名或刪除預設帳號 |
| `profile_label_conflict` | 409 | NFKC＋casefold 後和既有名稱或保留名稱相同 |
| `profile_limit_reached` | 409 | 已到上限（帶 `limit`） |
| `profile_memory_insufficient` | 409 | 記憶體不夠再開一個 |
| `profile_port_unavailable` | 409 | 18000～18099 找不到空 port |
| `profile_product_unsupported` | 409 | 不開放的產品收到建立 |
| `profile_index_corrupt` | 503 | 帳號索引壞掉或被外改 |
| `endpoint_global` | 409 | 對額外帳號 `PUT endpoint` |
| `restore_review_required` | 409 | 還原或休眠後還沒核對就重新產生，或會換權杖的存檔 |
| `origin_policy_invalid` | 422 | `PUT origin-policy` 的模式或來源不合規則 |
| `operation_restored` | 410 | 還原後重送還原前的操作 id |
| `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN` | 422 | 把後端網址改到另一個來源卻沒帶那條網址的秘密 |

既有的 `config_conflict`、`config_revision_required`、`operation_id_*`、`operation_outcome_unknown` 等照今天，只是範圍擴大到帳號的增刪與全域操作
（全部撤銷沒做完時 `operation_outcome_unknown` 另帶逐帳號 `results`）。
