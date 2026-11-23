# Saved settings, running settings and active credentials

The authenticated management API adds `configuration` to bootstrap, successful
setting saves and child restart responses. `GET /api/configuration` returns the
same object without replacing an editor's form data. Existing settings, schema4,
full-tool defaults and backend health fields are unchanged.

| Field | Meaning |
| --- | --- |
| `revision` | Opaque revision of the whole editable snapshot, including credential and policy changes. |
| `saved_revision` | Opaque revision of launch-relevant saved settings. Public token and endpoint changes do not change it. Native EMQX, LiteLLM and Nextcloud policies are launch inputs. |
| `applied_revision` | Launch revision verified by a completed protocol probe of the current child generation, or null. |
| `apply_state` | `pending`, `applied`, `failed`, `unconfigured`, or `unknown`. |
| `last_error_code` | Fixed safe failure code, or null; never exception text or a credential. |

Revisions are keyed with a random process-local HMAC key. They disclose neither
raw configuration nor reusable credential hashes. They change across management
process restarts; an editor opened before restart must reload. Application
metadata is not persisted and does not require a schema migration. A child that
has merely spawned is pending. A completed probe from an older generation cannot
apply a newer save. Application is separate from backend reachability and from
the success of any business operation. Token and endpoint updates do not restart
the child. Policy updates retain existing product-specific restart behavior.

Bootstrap's `ETag` is the quoted `configuration.revision` from the same snapshot.
A setting save may send that exact value as `If-Match`. An obsolete or malformed
conditional value returns HTTP409 with `detail.code="config_conflict"` before
any write or child replacement. The condition is checked under the mutation
lock after the final administrator-role verification. Clients omitting the
header retain their prior behavior and do not receive stale-edit protection.

The new UI captures each form's revision when rendering it. Refreshing CSRF or
application status never advances that revision. A conflict preserves the draft
in the current page, disables its save controls, and requires explicit reload
and review before another submission. Reload clears the draft, including secret
fields. Drafts and credentials are not written to browser storage. Old servers
without configuration metadata remain usable, without conditional protection.

A committed backend save whose child replacement fails returns HTTP503 with
`saved:true`, `detail.code="config_apply_failed"`, and configuration status.
The UI explicitly says the settings were saved but not applied. It never retries
the mutation automatically. Reload status, inspect diagnostics, and explicitly
retry child startup if appropriate. Losing a caller after commit does not detach
the owned lifecycle transition or release its mutation lock prematurely.

## Active token revocation

The same shared credential protects Bearer `/mcp` and `/private_<token>/mcp`.
HA exposes no legacy `/sse` or `/messages` transport. The normal token rotate and
revoke APIs publish cancellation only after the durable state update succeeds.
Existing request leases cover request bodies, pending child headers/body reads,
and actual ASGI sends, including backpressure. Rotation and revocation do not
restart the child. A corrupt or externally replaced state also fails closed,
with a bounded fallback check for requests already waiting.

Before response start, revoked access receives the usual Bearer401 or secret-path
404. Once HTTP has started, the gateway closes the connection; it cannot change
the status already sent. No further buffered SSE frame is emitted. Owned child
responses, readers and concurrency slots are closed/joined. A newly initialized
child session whose answer was withheld is ended through the existing bounded
cleanup DELETE. Bytes already delivered and backend work already dispatched
cannot be recalled or rolled back by revocation.

Regression coverage includes two real socket clients (Bearer and secret path),
GET and POST SSE, rotate and revoke, reissue, upstream closure, blocked headers,
blocked send, coalesced frames, all product connection routes, stale concurrent
editors, commit/application failures and browser draft preservation. These are
owned local fixtures, not evidence of HA Ingress or a live third-party backend.

## 多帳號（產品開通後）的設定

這一節照多帳號契約 `docs/multi-profile/contract.md`（HM-18 定稿）寫產品開通多帳號之後的設定；**Odoo、LiteLLM、Nextcloud、EMQX 從各自的 0.5.0 起開通（HM-19a、火車 A），其他產品還沒開通**，沒開通的產品照上面
各節，回應一個位元組都不變。逐條規則、錯誤代碼與欄位以契約為準（第 2、3、4.1 節；開通後預設帳號會變的事：第 1.4 節）。

- **每個帳號一份設定**：預設帳號在 `/data/mcp/state.json`（一個鍵都不加），額外帳號在 `/data/mcp/profiles/<24 位小寫 hex>/state.json`。每個帳號各有自己的
  後端連線與憑證、MCP 權杖、child token、工具政策，以及上面那組 `configuration` 欄位（`revision`、`saved_revision`、`applied_revision`、`apply_state`、
  `last_error_code`），意思相同。帳號清單在 `/data/mcp/profiles.json`（只有 id、名稱、port，不含秘密）。
- **選帳號**：帳號範圍的管理請求（`bootstrap`、`configuration`、`backend`、`policy`、`token/*`…）一定要剛好一個 `X-MCP-Profile`（`default` 或 24 位小寫 hex）：
  缺 400 `profile_id_required`、多個或格式錯 400 `profile_id_invalid`、不存在 404 `profile_not_found`；絕不退回預設帳號（契約第 3.3 節）。8081 永遠不看這個標頭。
- **回聲**：帳號範圍的 JSON 回應帶 `profile:{"id"}`，bootstrap 另帶 `profile:{"id","label","is_default"}` 與 `profiles_supported`。面板一次變更的 bootstrap 與
  變更請求帶同一個標頭、兩個回應的回聲都要相同，不符就不顯示、藏起已顯示的權杖並重新讀取（契約第 3.4 節）。
- **If-Match**：帳號的 ETag 是 `"c1-<64 hex>"`，HMAC 的 domain 帶帳號 id（`edit:<id>`）：拿 A 的 ETag 寫 B 回 409 `config_conflict`；兩個帳號的設定就算逐位元
  相同，ETag 也不同。ETag 照舊是這個程序的隨機金鑰算的，重啟後全部變（契約第 3.5 節）。
- **端點是全域設定**：「MCP 用戶端端點」只存在預設帳號；額外帳號的 `PUT endpoint` 回 409 `endpoint_global`、什麼都不寫，額外帳號的 bootstrap 顯示預設帳號的
  `endpoint`（DQ-13）。
- **只重啟選定的帳號**：存政策、Odoo 寫入開關與方法清單、n8n session 設定，只重啟那個帳號的子程式；`child/restart` 的 202 回應多 `blocked_reason`。
- **權杖各自撤銷**：上面「Active token revocation」的規則每個帳號各自成立：一個帳號的輪替、撤銷、刪除只結束帶著它的請求，別的帳號的串流不斷。
  每個帳號的 Bearer `/mcp` 與 `/private_<token>/mcp` 用同一把權杖；同樣沒有 legacy `/sse`、`/messages`（DQ-23）。
- **Odoo 換身分換權杖**（HM-12）：存檔讓 url、database、username 任一改變（含清空連線）時，先停舊子程式、同一次寫入新連線與新權杖、發布權杖變更、再起新子程式；
  回 200 `{"saved":true,"token_rotated":true,…}`（不含權杖，新權杖照舊經 `token/reveal`）。只換密碼、第一次設定、權杖已撤銷時照上面，不換權杖。寫入失敗一律
  503 `{"error":"state unavailable"}`，結果不明時重啟後照磁碟上的設定（權杖可能已換）；新子程式起不來時是上面那種 HTTP 503（`saved:true`、`detail.code="config_apply_failed"`）另帶
  `token_rotated:true`（權杖已換；契約第 3.1 節 `backend` 列）。
- **新來源要重填秘密**（DQ-40 ⑨，全部產品）：`backend/patch` 把網址改到另一個來源（scheme、host、port）卻沒帶那條網址會送去的已存秘密，回 422
  `CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN`，什麼都不寫。`backend` 整份取代本來就帶全部秘密，不受影響。
- **後端網址拒絕 loopback**（HM-20）：存檔改到的後端網址是 127.0.0.0/8、::1 或 `localhost` 時回 400 `{"error":"request denied"}`；子程式連線時也擋。
- **還原後先核對**（HM-13c）：還原或休眠撤銷的帳號，`token/rotate` 與會換權杖的存檔在核對前回 409 `restore_review_required`、什麼都不寫；還原紀錄讀不到時
  一律 503 `{"error":"state unavailable"}`（出路是全部撤銷）。
