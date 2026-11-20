# PaaS 多帳號測試逐案對照（pin `69ac425`）

> HM-00 產出（2026-11-14）；2026-11-15 文件同步重產（DQ-38 的狀態）；2026-11-17 HM-12 面板改一個檔的歸屬（審查 S-3）；
> 2026-11-17 文件同步重產（PaaS 基準 `48f394d`、各片補的差異表列）。全表由 repo 外的產生器從 PaaS git 物件庫重算後寫出；
> 改歸屬時改產生器的規格再重產，不要手改表格。對照腳本會重新列出 PaaS 案例，和本檔逐檔逐案比對。重產指令與輸入版本見
> `docs/provenance/ha-multiprofile-docs-sync-20261117.md`（原本的指令見 `docs/provenance/ha-multiprofile-HM-00-20261114.md` 第 8 節），
> 產生器另加 `--main 48f394d`（本表的 PaaS 基準）；腳本與輸入的 SHA-256 以 repo 外的 `wave0/hm00-check/SHA256SUMS` 為準。
> 歸屬的語意（對到的測試或差異列說的是不是同一件事）靠人工抽查。

## 結論

- 範圍：79 個檔、823 個案例，每檔每案都有歸屬。其中 pin `69ac425` 的範圍是 53 檔、541 案；pin 之後合併進來的 D 組 26 檔、282 案。
- 歸屬（一案可以同時有兩種）：對到 HA 測試 606 案；對到刻意差異表（契約第 9 節，下稱 §8.8）348 案；只能標「不適用」70 案。
- pin 之後：`origin/main` 到 `48f394d`。
  - `69ac425..7d111b1`：#148 後續（`091dfbc`，#150）只改文件、測試與註解，`test_gateway_queue.py` 沒有新增或刪除案例；#149（head `3d33bc5`）已在 2026-11-14 14:19（台北）合併，它的 query 憑證測試照計畫 §10.5 併進 D 組，對到 HM-02。
  - `7d111b1..48f394d`（台北 2026-11-14 22:30 到 11-17 03:58，9 個 PR）：#151 移除 VK，只刪 VK 的案例與參數（不在範圍）；#152、#154（Nextcloud 存檔與測試連線過 SSRF、日誌遮罩保留 args 形狀；換使用者或網址換 token）對到契約 §8.8 #39、#59、#86、#113、#114、#116、HM-20 的測試與 HM-22 的暫定測試；#153（EMQX 小修）不是多帳號行為，交 HM-23；#155（閘道請求內容位元組預算與 JSON 結構守門）照 HM-31 筆記逐案對到 HM-31 的測試與 §8.8 #101～#108；#135、#139（EMQX、LiteLLM 不保留閒置連線）對到 HM-32；#138（Hermes 建停用的排程）對到 HA 既有的測試（PR #85，還沒發版）；#156 只改 Hermes 的說明（HM-33），沒有測試。新的測試檔併進 D 組（見文末「pin 之後的變動」）。

## 範圍怎麼來

1. 查詢（計畫 §10.5，在 PaaS clone 裡跑）：

   ```sh
   git grep -l -i -E "profile_index|X-MCP-Profile|profile_id|/api/profiles|token_in_use|child_port_|identity_connection_keys|restore_guard" 69ac425 -- '*test*'
   ```

   結果 35 檔（A 組）。
2. #148 新增、查詢沒抓到的 6 檔（`git diff --stat 443e95a 69ac425 -- '*test*'`，B 組）。
3. 研究報告 R03～R06 點名的 11 檔，加上 R06 引用的 launch policy 測試（C 組）。計畫寫的 `apps/headscale/tests/test_launch_policy.py` 在 `69ac425` 不存在；R06 實際引用的是 `packages/mcp-admin-core/tests/test_launch_policy.py`，本表用這個路徑。`test_setup_status.py` 在 `69ac425` 有兩個，本表用 R03 點名的 `packages/mcp-admin-core/tests/test_setup_status.py`（41 案）。
4. pin 之後（D 組）：`git diff --name-only 69ac425 48f394d -- '*test*'`（本表的 PaaS 基準 `48f394d`）；pin 沒有的檔整個算新增，pin 就有的檔只看新增或刪除的案例。不在多帳號範圍的產品修正也照這條規則併進來，歸屬寫明交給哪一片。

案例的定義：Python 檔是模組層或類別內名稱以 `test_` 開頭的函式；JS 檔是 `test(…)`／`it(…)`；不是 pytest 的瀏覽器腳本與輔助檔（`conftest.py`、替身伺服器、fixture 模組）整個檔算一案，名稱寫「（整個檔）」。parametrize 展開的子案不另列。

| 組 | 檔 | 案 |
|---|---|---|
| A｜查詢抓到的檔 | 35 | 353 |
| B｜#148 新增、查詢沒抓到的檔 | 6 | 35 |
| C｜研究報告點名的檔 | 12 | 153 |
| D｜pin 之後合併進來的檔 | 26 | 282 |
| 合計 | 79 | 823 |

## 讀法

- `HA：<檔>（<切片>）`：HA 對應的測試。「既有」是 bb48449 已有的測試；「HM-xx」是計畫中的新測試，檔名照計畫 §10.3（登記在 `acceptance-matrix.md` 的測試檔登記表）；「暫定名」是產品片的檔名，由該片定案。
- `§8.8 #n`：HA 刻意和 PaaS 不同，HA 的期望值看 `contract.md` 第 9 節（刻意差異表）第 n 列，PaaS 案例的期望值不直接適用。
- `不適用：<理由>`：PaaS 專屬機制，HA 沒有可對照的東西；或 D 組裡不是多帳號行為的產品修正（理由寫明交給哪一片）。
- 不搬 PaaS 測試檔；例外是遮罩的純測試（DQ-38 選 (a)：`log_redaction.py` 與純測試原樣 vendor，HM-02）。

## 全表

### A｜查詢抓到的檔

#### `apps/emqx/tests/test_log_redaction_exception_boundary.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 6 | `test_exception_text_does_not_restore_encoded_url_secret` | HA：`tests/test_redaction_matrix.py`（HM-02），例外文字裡的編碼密鑰網址 |

#### `apps/headscale/tests/browser/controlled-server.mjs`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | 不適用：PaaS Headscale 專用 GUI 的替身伺服器（輔助檔、沒有斷言）；HA 用共用面板，多帳號替身由 HM-11 擴充既有 `packages/mcp-admin-ui/tests/owned-fixture.mjs` |

#### `apps/headscale/tests/browser/profiles.mjs`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），帳號選單、帶標頭、切換時藏 token 與丟棄晚到回應；§8.8 #109（刪除要兩段確認） |

#### `apps/headscale/tests/test_restore_admin_sessions.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 95 | `test_restore_drops_admin_sessions_and_no_earlier_admin_login_comes_back` | 不適用：Headscale 的 admin session 資料庫；HA 沒有管理登入；§8.8 #11 |

#### `apps/hermes/tests/test_dashboard_profile_cache.py`（2 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 51 | `test_dashboard_proxy_cookie_follows_profile_and_credential_changes` | §8.8 #63（HA 沒有管理端 Dashboard 代理） |
| 2 | 79 | `test_dashboard_health_cookie_follows_profile` | HA：`tests/test_hermes_multi_profile.py`（HM-24，暫定名），每帳號一個子程式，cookie 快取隨子程式分開 |

#### `apps/nextcloud/tests/test_main.py`（21 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 32 | `test_healthz_ok_without_login` | §8.8 #7 |
| 2 | 51 | `test_routes_mounted` | 不適用：PaaS Nextcloud 單帳號 app 的路由、工具頁與健康端點，不是多帳號行為 |
| 3 | 62 | `test_tools_api_serves_nine_with_one_dangerous` | 不適用：PaaS Nextcloud 單帳號 app 的路由、工具頁與健康端點，不是多帳號行為 |
| 4 | 68 | `test_tools_disable_is_persisted_for_proxy` | 不適用：PaaS Nextcloud 單帳號 app 的路由、工具頁與健康端點，不是多帳號行為 |
| 5 | 74 | `test_health_api_shape_without_secret` | 不適用：PaaS Nextcloud 單帳號 app 的路由、工具頁與健康端點，不是多帳號行為 |
| 6 | 98 | `test_seed_defaults_fresh_config` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 7 | 108 | `test_seed_defaults_keep_existing_disabled` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 8 | 113 | `test_seed_defaults_never_reopen_existing_read_only_service` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 9 | 124 | `test_seed_defaults_respect_tenant_unlock` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 10 | 135 | `test_seed_defaults_keep_custom_prefix` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 11 | 140 | `test_lifespan_applies_seed_defaults_before_core` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 12 | 151 | `test_fresh_tools_page_shows_all_enabled` | 不適用：PaaS 範本 seed；HA 新安裝全開與 owner-defaults 由既有 `tests/test_writes_default_on.py`、`tests/test_owner_defaults.py` 管 |
| 13 | 185 | `test_enabling_write_tool_restarts_child` | HA：`tests/test_nextcloud_multi_profile.py`：放寬時只重啟選定的在跑子程式 |
| 14 | 193 | `test_disabling_more_tools_does_not_restart` | HA：`tests/test_nextcloud_multi_profile.py`：收緊不重啟，現有 session 由閘道即時限制；§8.8 #54 |
| 15 | 199 | `test_unchanged_policy_does_not_restart` | HA：`tests/test_nextcloud_multi_profile.py`：不變不重啟 |
| 16 | 205 | `test_widening_while_stopped_does_not_start` | HA：`tests/test_nextcloud_multi_profile.py`：stopped、blocked、failed、backoff 均不啟動，下次啟動使用新政策 |
| 17 | 212 | `test_unauthenticated_put_does_not_restart` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10），非管理員 403、子程式不動 |
| 18 | 220 | `test_stale_policy_update_does_not_restart` | HA：`tests/test_profile_admin_api.py`（HM-10），過期 If-Match 回 409、子程式不動 |
| 19 | 227 | `test_unknown_profile_does_not_restart` | HA：`tests/test_profile_admin_api.py`（HM-10），未知帳號 404 `profile_not_found`、絕不退回預設帳號 |
| 20 | 234 | `test_other_routes_pass_through` | 不適用：PaaS 中介層放行其他路由；HA 沒有這一層 |
| 21 | 243 | `test_lifespan_registers_password_for_redaction` | HA：`tests/test_reply_mask_union.py`（HM-08），HA 遮罩以帳號 state 為單位 |

#### `apps/nextcloud/tests/test_tool_policy_profiles.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 84 | `test_policy_update_only_restarts_selected_real_child` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），存政策只重啟選定帳號的真子程式 |

#### `apps/odoo/tests/test_multi_profiles.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 21 | `test_five_odoo_accounts_same_database_are_fixed_to_separate_profiles` | HA：`tests/test_odoo_multi_profile.py`（HM-12），同庫五個帳號各自固定綁定 |

#### `packages/mcp-admin-core/tests/conftest.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | 不適用：PaaS 測試替身（fixture）；HA 的替身是既有 `tests/owned_runtime.py`、`tests/owned_child.py`，由 HM-01 參數化 |

#### `packages/mcp-admin-core/tests/test_auth.py`（26 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 45 | `test_healthz_is_public` | §8.8 #7 |
| 2 | 52 | `test_non_api_path_is_public` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 3 | 59 | `test_protected_api_requires_token` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10），沒有 Ingress 身分或不是管理員一律 403；§8.8 #11 |
| 4 | 64 | `test_login_wrong_password_rejected` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 5 | 70 | `test_login_success_returns_token` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 6 | 77 | `test_default_app_issues_server_revocable_session_ids` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 7 | 88 | `test_logout_revokes_only_this_login_for_all_credential_transports` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 8 | 109 | `test_logout_survives_fresh_store_and_stale_save` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 9 | 121 | `test_admin_logout_uses_global_store_across_profiles` | HA：`tests/test_profile_runtime.py`（HM-05），全 add-on 共用一份 AdminAuthority 與 CSRF 金鑰；§8.8 #11 |
| 10 | 142 | `test_logout_write_failure_keeps_session_and_cookie` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 11 | 159 | `test_old_jwt_without_session_id_requires_new_login` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 12 | 169 | `test_bearer_token_grants_access` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10），沒有 Ingress 身分或不是管理員一律 403；§8.8 #11 |
| 13 | 176 | `test_invalid_token_rejected` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10），沒有 Ingress 身分或不是管理員一律 403；§8.8 #11 |
| 14 | 183 | `test_deeply_nested_token_header_is_401_not_500` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 15 | 208 | `test_verify_token_swallows_recursion_error` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 16 | 219 | `test_password_change_revokes_existing_bearer_session` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 17 | 244 | `test_each_transport_revoked_even_after_password_rotated_back` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 18 | 265 | `test_same_password_write_explicitly_revokes_sessions` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 19 | 276 | `test_rejected_password_write_and_unrelated_settings_keep_session` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 20 | 289 | `test_password_rotation_leaves_opaque_mcp_token_unchanged` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 21 | 304 | `test_mcp_token_rotation_keeps_current_admin_session_and_revoked_session_denied` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10），MCP token 不能當管理憑證；§8.8 #11 |
| 22 | 326 | `test_session_survives_store_reload_with_same_signing_key` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 23 | 347 | `test_persisted_revocation_survives_real_process_restart` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 24 | 414 | `test_failed_password_persistence_does_not_change_auth` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 25 | 440 | `test_legacy_or_invalid_generation_is_rejected` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |
| 26 | 451 | `test_cancelled_unrelated_write_cannot_revive_revoked_session_on_store_restart` | §8.8 #11（PaaS 管理密碼＋JWT＋session；HA 沒有登入、登出與 session） |

#### `packages/mcp-admin-core/tests/test_child_identity_live.py`（10 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 215 | `test_only_managed_child_may_answer_initialize` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 2 | 246 | `test_listener_bound_after_spawn_by_another_process_is_never_used` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 3 | 266 | `test_stop_kills_grandchild_that_holds_the_port_and_a_new_child_can_bind` | HA：`tests/test_lifecycle.py`（既有），整組 SIGTERM→SIGKILL；HA：`tests/test_profile_ports.py`（HM-09），port 釋放後新子程式可綁 |
| 4 | 296 | `test_crashed_child_leaves_no_grandchild_on_the_port` | HA：`tests/test_lifecycle.py`（既有），當掉不留孫程序 |
| 5 | 339 | `test_managed_child_dies_with_its_manager` | 不適用：HA 管理程序結束＝add-on 容器結束，子程式隨容器一起結束 |
| 6 | 374 | `test_port_assigned_to_another_profile_is_refused` | HA：`tests/test_profile_ports.py`（HM-09），spawn 前四類 port 衝突不 spawn |
| 7 | 397 | `test_port_of_another_profiles_running_child_is_refused` | HA：`tests/test_profile_ports.py`（HM-09），spawn 前四類 port 衝突不 spawn |
| 8 | 420 | `test_admin_listener_port_is_refused` | HA：`tests/test_profile_ports.py`（HM-09），spawn 前四類 port 衝突不 spawn |
| 9 | 442 | `test_verified_child_that_stops_listening_is_fenced_before_another_process_takes_the_port` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 10 | 466 | `test_uvloop_spawn_identity_and_group_stop` | HA：`tests/test_lifecycle.py`（既有），整組停止；HA：`tests/test_child_identity.py`（HM-15，條件式） |

#### `packages/mcp-admin-core/tests/test_gateway_pool.py`（12 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 111 | `test_one_profile_holding_100_streams_does_not_block_other_profiles` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 2 | 144 | `test_streams_spread_over_profiles_no_longer_exhaust_the_shared_pool` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 3 | 164 | `test_full_profile_gets_a_clean_busy_error_and_others_are_unaffected` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 4 | 211 | `test_real_mcp_client_keeps_one_stream_and_is_unaffected` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 5 | 283 | `test_busy_answer_keeps_streamable_sessions_and_legacy_sse_status` | HA：`tests/test_gateway_busy_shapes.py`（HM-14）；§8.8 #6（legacy SSE 不支援） |
| 6 | 337 | `test_already_read_response_returns_its_slot_at_once` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 7 | 348 | `test_full_profile_waits_at_most_pool_timeout_and_other_profiles_proceed` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 8 | 371 | `test_waiting_request_gets_the_slot_when_one_is_released` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 9 | 383 | `test_stream_limit_refuses_immediately_and_posts_still_work` | HA：`tests/test_profile_quotas.py`（HM-08），串流 24／8，第 25 條 429＋`Retry-After: 30`；§8.8 #15 |
| 10 | 401 | `test_slots_are_returned_on_transport_errors_and_cancellation` | HA：`tests/test_profile_quotas.py`（HM-08）；§8.8 #15 |
| 11 | 430 | `test_limits_from_environment` | §8.8 #45 |
| 12 | 455 | `test_gateway_client_uses_bounded_pool_wait` | HA：`tests/test_profile_quotas.py`（HM-08），每帳號自己的 httpx client；§8.8 #15 |

#### `packages/mcp-admin-core/tests/test_gateway_queue.py`（25 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 123 | `test_request_abandoned_while_queued_never_reaches_the_child` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 2 | 159 | `test_client_leaving_the_queue_is_noticed_at_once_and_returns_nothing_it_did_not_take` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 3 | 194 | `test_queue_is_capped_per_profile_and_the_overflow_gets_a_clean_busy_answer_with_a_warning` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 4 | 241 | `test_zero_queue_means_no_waiting_at_all` | §8.8 #45（HA 排隊上限是程式常數，沒有環境變數，也沒有 0＝不排隊） |
| 5 | 262 | `test_limits_from_environment_include_the_queue` | §8.8 #45（HA 排隊上限是程式常數，沒有環境變數，也沒有 0＝不排隊） |
| 6 | 288 | `test_notifications_get_through_when_every_ordinary_slot_is_busy` | HA：`tests/test_carries_no_request.py`（HM-14），通知保留名額 4；§8.8 #91、#96（HA 只轉送 `notifications/initialized`，准入滿時照樣送到） |
| 7 | 337 | `test_get_streams_never_use_the_notification_reserve` | HA：`tests/test_carries_no_request.py`（HM-14），通知保留名額 4；§8.8 #91、#96（HA 只轉送 `notifications/initialized`，准入滿時照樣送到） |
| 8 | 395 | `test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 9 | 423 | `test_slot_granted_in_the_same_instant_the_client_leaves_is_given_back_not_used` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 10 | 456 | `test_cancelling_a_queued_request_returns_nothing_and_leaks_no_slot` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 11 | 484 | `test_a_broken_disconnect_watcher_does_not_look_like_a_disconnect` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 12 | 503 | `test_request_without_hints_behaves_exactly_as_before` | HA：`tests/test_single_profile_golden.py`（HM-01），開關關時與今天逐位元相同 |
| 13 | 518 | `test_queue_cap_refuses_the_overflow_at_once_and_other_profiles_are_unaffected` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 14 | 547 | `test_notification_lane_is_separate_from_the_ordinary_slots` | HA：`tests/test_carries_no_request.py`（HM-14），通知保留名額 4；§8.8 #91、#96（HA 只轉送 `notifications/initialized`，准入滿時照樣送到） |
| 15 | 571 | `test_slot_accounting_survives_random_cancellation_disconnects_timeouts_and_overflow` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 16 | 635 | `test_shared_pool_has_room_for_every_profiles_slots_and_reserve` | §8.8 #15（HA 沒有共用池，每帳號一個 httpx client）；HA：`tests/test_profile_quotas.py`（HM-08） |
| 17 | 654 | `test_initialize_waiting_for_a_slot_during_startup_gets_the_normal_busy_answer` | HA：`tests/test_gateway_busy_shapes.py`（HM-14）；§8.8 #68（子程式沒起時閘道自答 initialize，在名額之前） |
| 18 | 809 | `test_a_request_that_waited_for_a_slot_keeps_holding_it_until_its_response_closes` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 19 | 844 | `test_shared_pool_size_is_pinned_to_the_documented_formula` | §8.8 #15（HA 沒有共用池，每帳號一個 httpx client）；HA：`tests/test_profile_quotas.py`（HM-08） |
| 20 | 861 | `test_queue_limit_counts_each_lane_on_its_own` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 21 | 897 | `test_busy_message_names_the_limit_of_the_lane_that_timed_out` | HA：`tests/test_gateway_busy_shapes.py`（HM-14） |
| 22 | 930 | `test_queue_full_message_names_the_limit_of_the_lane_that_is_full` | HA：`tests/test_gateway_busy_shapes.py`（HM-14） |
| 23 | 964 | `test_closing_the_same_response_twice_returns_the_slot_only_once` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 24 | 982 | `test_requests_that_timed_out_leave_no_orphan_waiter_on_the_semaphore` | HA：`tests/test_gateway_queue_ha.py`（HM-14），排隊 32／16、保留 4；§8.8 #15 |
| 25 | 1003 | `test_queue_limit_environment_variable_accepts_its_ceiling_and_rejects_one_more` | §8.8 #45（HA 排隊上限是程式常數，沒有環境變數，也沒有 0＝不排隊） |

#### `packages/mcp-admin-core/tests/test_log_redaction_encoded_boundaries.py`（3 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 28 | `test_rejected_and_accepted_raw_targets_do_not_expose_secret` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 2 | 33 | `test_deep_ambiguous_encoding_fails_closed` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 3 | 43 | `test_rendered_split_arguments_do_not_leak_or_break_formatting` | HA：`tests/test_redaction_matrix.py`（HM-02） |

#### `packages/mcp-admin-core/tests/test_log_redaction_linear.py`（27 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 87 | `test_redact_is_fast_on_pathological_inputs` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 2 | 100 | `test_redact_is_bounded_for_huge_input` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 3 | 114 | `test_truncation_keeps_head_of_ordinary_long_text` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 4 | 126 | `test_truncation_never_leaks_part_of_a_token` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 5 | 136 | `test_truncation_prefers_whitespace_boundary` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 6 | 144 | `test_truncated_dangling_escape_does_not_fail_closed` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 7 | 170 | `test_backslash_and_overlong_variants_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 8 | 175 | `test_backslashes_in_ordinary_text_are_untouched` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 9 | 230 | `test_uvicorn_access_line_survives_ambiguous_paths` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 10 | 240 | `test_uvicorn_access_ambiguous_path_keeps_five_tuple_shape` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 11 | 251 | `test_uvicorn_access_suspicious_other_args_are_replaced_with_shape_kept` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 12 | 260 | `test_uvicorn_access_normal_path_is_unchanged` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 13 | 283 | `test_other_loggers_whole_line_replacement_does_not_break_logging` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 14 | 300 | `test_exception_traceback_with_long_path_is_fast_and_masked` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 15 | 346 | `test_full_access_path_is_fast_and_linear` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 16 | 369 | `test_access_path_over_2kib_is_truncated_and_shape_kept` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 17 | 383 | `test_access_path_up_to_limit_is_unchanged` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 18 | 391 | `test_access_path_truncation_never_leaks_token` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 19 | 402 | `test_access_path_truncation_does_not_leave_dangling_escape` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 20 | 411 | `test_access_path_token_at_head_is_masked_before_truncation` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 21 | 439 | `test_key_with_separator_or_noise_between_letters_is_masked` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 22 | 445 | `test_key_rule_does_not_overmask_other_params` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 23 | 463 | `test_fffd_and_backslash_inside_marker_are_masked_without_other_trigger` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 24 | 485 | `test_access_word_before_token_key_is_still_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 25 | 491 | `test_access_word_then_separator_variants_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 26 | 497 | `test_access_word_then_token_through_real_access_line` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 27 | 512 | `test_value_swallowing_part_of_next_lead_does_not_hide_next_key` | HA：`tests/test_redaction_matrix.py`（HM-02） |

#### `packages/mcp-admin-core/tests/test_log_redaction_private_separators.py`（16 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 159 | `test_matrix_is_the_reviewed_97_cases` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 2 | 264 | `test_access_log_masks_token_in_stdout_and_ring_buffer` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 3 | 321 | `test_app_log_lines_mask_token_in_stdout_and_ring_buffer` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 4 | 339 | `test_redaction_is_idempotent_for_every_case` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 5 | 394 | `test_real_uvicorn_access_log_masks_all_97_targets` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 6 | 471 | `test_normal_access_paths_stay_readable` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 7 | 486 | `test_other_log_messages_keep_their_shape` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 8 | 530 | `test_pathological_path_single_redaction_time_is_bounded` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 9 | 539 | `test_pathological_access_record_cost_is_bounded` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 10 | 580 | `test_pathological_path_has_no_per_segment_python_work` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 11 | 628 | `test_differential_fuzz_never_shows_what_8297aa4_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 的不退步差分對照 bb48449 自己的遮罩，門檻是「不比 pin 版 PaaS 差」 |
| 12 | 663 | `test_key_leads_inside_a_private_segment_are_still_used` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 13 | 678 | `test_cascading_masks_are_idempotent` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 14 | 718 | `test_strict_segment_check_sees_separators_that_appear_in_any_decoding_round` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 15 | 791 | `test_differential_fuzz_never_shows_what_decoded_first_order_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 的不退步差分對照 bb48449 自己的遮罩，門檻是「不比 pin 版 PaaS 差」 |
| 16 | 813 | `test_multi_round_encoded_separator_does_not_leak_into_access_log` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |

#### `packages/mcp-admin-core/tests/test_logs_profile_buffers.py`（17 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 130 | `test_busy_profile_cannot_empty_a_quiet_profiles_logs_page` | HA：`tests/test_profile_runtime.py`（HM-05），每帳號一個 Supervisor＝每帳號一份子程式輸出緩衝；§8.8 #29 |
| 2 | 156 | `test_busy_profile_keeps_its_own_newest_lines_up_to_its_cap` | HA：`tests/test_profile_runtime.py`（HM-05），每帳號一個 Supervisor＝每帳號一份子程式輸出緩衝；§8.8 #29 |
| 3 | 168 | `test_single_profile_service_keeps_as_many_lines_as_before` | HA：`tests/test_child_diagnostics.py`（既有），單帳號緩衝上限不變 |
| 4 | 180 | `test_each_child_output_line_is_stored_once` | HA：`tests/test_child_diagnostics.py`（既有） |
| 5 | 190 | `test_child_output_with_a_credential_is_stored_once_and_masked` | HA：`tests/test_child_diagnostics.py`（既有） |
| 6 | 203 | `test_lifecycle_line_is_stored_once_with_its_own_level` | §8.8 #29（HA 管理程序紀錄進 add-on log，不進子程式緩衝） |
| 7 | 209 | `test_admin_log_line_is_stored_once_even_if_two_capturing_loggers_see_it` | §8.8 #29（HA 管理程序紀錄進 add-on log，不進子程式緩衝） |
| 8 | 222 | `test_access_log_lines_are_not_buffered` | §8.8 #29（HA 關閉 access log） |
| 9 | 231 | `test_a_profiles_buffer_is_also_bounded_by_message_bytes` | HA：`tests/test_child_diagnostics.py`（既有），每個 Supervisor 200 筆／128 KiB，超過 8 KiB 的行丟掉；§8.8 #29 |
| 10 | 245 | `test_an_oversized_line_is_still_shown_alone` | HA：`tests/test_child_diagnostics.py`（既有），每個 Supervisor 200 筆／128 KiB，超過 8 KiB 的行丟掉；§8.8 #29 |
| 11 | 255 | `test_buffers_are_kept_for_a_bounded_number_of_profiles_and_deleted_ones_go_first` | §8.8 #29（HA 刪除帳號就釋放緩衝，不保留） |
| 12 | 280 | `test_without_a_profile_index_the_least_recently_written_buffer_goes_first` | §8.8 #29（HA 刪除帳號就釋放緩衝，不保留） |
| 13 | 293 | `test_all_live_profiles_fit_in_the_buffer_limit` | §8.8 #29（HA 緩衝總量＝帳號數×128 KiB）；HA：`tests/test_profile_runtime.py`（HM-05） |
| 14 | 297 | `test_total_buffer_memory_stays_under_the_documented_ceiling` | §8.8 #29（HA 緩衝總量＝帳號數×128 KiB）；HA：`tests/test_profile_runtime.py`（HM-05） |
| 15 | 324 | `test_search_response_shape_is_unchanged` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 16 | 338 | `test_stream_sends_own_new_lines_even_when_another_profile_floods_between_polls` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 17 | 365 | `test_stream_endpoint_serves_only_the_selected_profile` | §8.8 #29；HA：`tests/test_profile_admin_api.py`（HM-10），診斷頁只回選定帳號 |

#### `packages/mcp-admin-core/tests/test_logs_router.py`（5 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 18 | `test_search_returns_buffer_matches` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 2 | 30 | `test_invalid_regex_returns_400` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 3 | 36 | `test_stream_first_event_is_connected` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 4 | 56 | `test_install_is_idempotent` | §8.8 #29（HA 沒有 Logs 搜尋與 SSE，診斷頁是 GET 快照） |
| 5 | 67 | `test_search_and_sse_keep_profile_logs_separate` | §8.8 #29；HA：`tests/test_profile_admin_api.py`（HM-10），診斷頁只回選定帳號 |

#### `packages/mcp-admin-core/tests/test_origin_product_children.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 54 | `test_origin_boundary_with_real_product_and_two_profiles` | HA：`tests/test_origin_policy.py`（HM-27，暫定名）；§8.8 #42 |

#### `packages/mcp-admin-core/tests/test_origin_root_path.py`（5 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 30 | `test_invalid_origin_denied_at_effective_route_for_all_methods` | HA：`tests/test_origin_policy.py`（HM-27，暫定名）；§8.8 #42 |
| 2 | 44 | `test_root_path_preflight_and_native_clients_use_same_policy` | §8.8 #42（HA 不加 CORS，沒有 preflight 放行） |
| 3 | 69 | `test_root_path_never_bypasses_admin_authentication` | HA：`tests/test_admin_pipeline_matrix.py`（HM-10） |
| 4 | 79 | `test_root_path_selects_profile_by_token` | HA：`tests/test_profile_routing.py`（HM-08） |
| 5 | 107 | `test_encoded_private_prefix_is_checked_using_the_routed_path` | HA：`tests/test_profile_routing.py`（HM-08），31 種網址變形 |

#### `packages/mcp-admin-core/tests/test_process_stdout_log.py`（14 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 52 | `test_process_logger_has_one_stdout_handler_at_info_and_ring_buffer_unchanged` | HA：`tests/test_profile_lifecycle.py`（HM-09），生命週期事件寫進 add-on log 一次、帶 id 前 8 碼、60 秒節流 |
| 2 | 67 | `test_lifecycle_message_reaches_stdout_once_and_ring_buffer_once` | HA：`tests/test_profile_lifecycle.py`（HM-09），生命週期事件寫進 add-on log 一次、帶 id 前 8 碼、60 秒節流 |
| 3 | 73 | `test_stdout_line_is_redacted_for_tokens_and_private_paths` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 4 | 81 | `test_stdout_is_redacted_even_without_the_record_factory` | HA：`tests/test_redaction_matrix.py`（HM-02） |
| 5 | 92 | `test_child_own_output_stays_out_of_stdout_but_in_ring_buffer` | HA：`tests/test_child_diagnostics.py`（既有），HA 子程式輸出只進緩衝、不進 add-on log；§8.8 #29 |
| 6 | 98 | `test_child_output_containing_a_token_is_not_on_stdout_either` | HA：`tests/test_child_diagnostics.py`（既有），HA 子程式輸出只進緩衝、不進 add-on log；§8.8 #29 |
| 7 | 105 | `test_debug_is_not_written_to_stdout` | HA：`tests/test_profile_lifecycle.py`（HM-09），生命週期事件寫進 add-on log 一次、帶 id 前 8 碼、60 秒節流 |
| 8 | 111 | `test_port_in_use_and_auto_restart_scheduled_reach_stdout_once` | HA：`tests/test_profile_lifecycle.py`（HM-09），生命週期事件寫進 add-on log 一次、帶 id 前 8 碼、60 秒節流 |
| 9 | 127 | `test_port_conflict_reaches_stdout_once` | HA：`tests/test_profile_lifecycle.py`（HM-09），生命週期事件寫進 add-on log 一次、帶 id 前 8 碼、60 秒節流 |
| 10 | 141 | `test_peer_mismatch_reaches_stdout_once` | HA：`tests/test_child_identity.py`（HM-15，條件式） |
| 11 | 157 | `test_connection_apply_restore_failure_reaches_stdout_once` | HA：`tests/test_odoo_identity_rotation.py`（HM-12），換身分提交失敗用舊 state 重起並記一行 |
| 12 | 205 | `test_child_output_never_reaches_stdout_but_always_reaches_logs_page` | HA：`tests/test_child_diagnostics.py`（既有），HA 子程式輸出只進緩衝、不進 add-on log；§8.8 #29 |
| 13 | 221 | `test_masked_child_line_and_lifecycle_line_do_not_interfere` | HA：`tests/test_child_diagnostics.py`（既有），HA 子程式輸出只進緩衝、不進 add-on log；§8.8 #29 |
| 14 | 228 | `test_stdout_exclusion_does_not_depend_on_the_message_text` | HA：`tests/test_child_diagnostics.py`（既有），HA 子程式輸出只進緩衝、不進 add-on log；§8.8 #29 |

#### `packages/mcp-admin-core/tests/test_profile_robustness.py`（14 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 81 | `test_manual_token_used_by_another_profile_is_refused_with_its_reason` | §8.8 #80（HA 沒有手動指定 token 的 API，FEATURE-MATRIX FM-31 不新增） |
| 2 | 115 | `test_refusal_inside_a_journaled_operation_drops_only_its_own_receipt` | §8.8 #80（HA 沒有手動指定 token 的 API，FEATURE-MATRIX FM-31 不新增） |
| 3 | 143 | `test_token_duplicated_in_two_profile_files_is_refused_and_logged_once_without_the_token` | HA：`tests/test_profile_routing.py`（HM-08），撞號 503、每組 60 秒一行、不含 token |
| 4 | 191 | `test_duplicate_index_port_keeps_the_service_and_other_profiles_available` | HA：`tests/test_profile_index.py`（HM-07），port 重複不算結構錯；HA：`tests/test_profile_ports.py`（HM-09） |
| 5 | 211 | `test_duplicate_index_port_starts_every_other_profile_and_logs_the_conflict` | HA：`tests/test_profile_ports.py`（HM-09），只停相關帳號 |
| 6 | 252 | `test_restore_validation_is_unchanged_and_runtime_relaxes_only_port_uniqueness` | HA：`tests/test_profile_index.py`（HM-07）；§8.8 #20 |
| 7 | 316 | `test_index_entry_on_the_default_port_blocks_only_that_profile` | HA：`tests/test_profile_ports.py`（HM-09），只停相關帳號 |
| 8 | 337 | `test_probe_timeout_and_late_verification_are_logged_with_profile_port_and_pid` | HA：`tests/test_profile_lifecycle.py`（HM-09），log 格式 `[profile=<id 前 8 碼> port=<p> pid=<n>]` |
| 9 | 383 | `test_crash_and_backoff_lines_name_the_profile_port_and_pid` | HA：`tests/test_profile_lifecycle.py`（HM-09），log 格式 `[profile=<id 前 8 碼> port=<p> pid=<n>]` |
| 10 | 411 | `test_default_manager_and_registry_managers_carry_their_profile_id` | HA：`tests/test_profile_runtime.py`（HM-05） |
| 11 | 423 | `test_create_refused_for_memory_says_so_and_how_much_is_needed` | HA：`tests/test_profile_admin_api.py`（HM-10）；§8.8 #19 |
| 12 | 446 | `test_memory_disabled_profile_is_listed_with_its_reason_and_logged_when_not_started` | HA：`tests/test_profile_admin_api.py`（HM-10）；HA：`tests/test_extra_child_resources.py`（HM-09） |
| 13 | 478 | `test_default_profile_without_required_connection_is_not_spawned_or_restarted` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #28 |
| 14 | 509 | `test_stdout_handlers_are_installed_once` | 不適用：PaaS 程序日誌處理器的安裝細節；HA 沒有對應流程 |

#### `packages/mcp-admin-core/tests/test_profiles.py`（16 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 28 | `test_five_profiles_have_private_independent_configs_and_urls` | HA：`tests/test_profile_store.py`（HM-07）；HA：`tests/test_profile_routing.py`（HM-08） |
| 2 | 89 | `test_profile_token_revocation_is_local` | HA：`tests/test_profile_routing.py`（HM-08），撤銷只影響該帳號（I3） |
| 3 | 104 | `test_token_cannot_be_assigned_to_two_profiles` | HA：`tests/test_profile_consistency.py`（HM-07），HA 沒有手動指定 token，建立一律新 token（I2） |
| 4 | 120 | `test_concurrent_manual_token_claims_have_one_owner` | §8.8 #80（HA 沒有手動指定 token 的 API，FEATURE-MATRIX FM-31 不新增） |
| 5 | 151 | `test_damaged_profile_reserves_unknown_token_against_manual_claim` | §8.8 #80（HA 沒有手動指定 token 的 API，FEATURE-MATRIX FM-31 不新增） |
| 6 | 175 | `test_deleting_profile_removes_child_database_directory` | HA：`tests/test_n8n_multi_profile.py`（HM-25，暫定名），刪帳號一起刪 nodes.db；§8.8 #47 |
| 7 | 192 | `test_missing_extra_profile_does_not_disable_other_tokens_or_startup` | HA：`tests/test_profile_consistency.py`（HM-07），缺的標 `profile_unavailable`、不補建 |
| 8 | 226 | `test_fs_group_widened_profile_directories_are_tightened_on_reload` | HA：`tests/test_profile_store.py`（HM-07），mode／owner 在 uid 10001 子程序驗 |
| 9 | 242 | `test_unconfigured_required_connection_does_not_spawn_a_child` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #28 |
| 10 | 296 | `test_profile_index_rejects_corruption_and_duplicate_label` | HA：`tests/test_profile_index.py`（HM-07） |
| 11 | 307 | `test_product_profile_limit_is_enforced_without_invalidating_existing_index` | HA：`tests/test_profile_index.py`（HM-07），超過產品上限只停用後段 |
| 12 | 319 | `test_cgroup_limit_prevents_extra_children_after_memory_reduction` | HA：`tests/test_extra_child_resources.py`（HM-09）；§8.8 #19 |
| 13 | 343 | `test_profile_token_enforces_its_own_tool_policy` | HA：`tests/test_profile_routing.py`（HM-08），每帳號政策 |
| 14 | 380 | `test_admin_password_is_global_and_profile_index_survives_save` | §8.8 #11、#44 |
| 15 | 399 | `test_n8n_internal_child_bearer_is_per_profile` | HA：`tests/test_child_bearer.py`（HM-06）；HA：`tests/test_n8n_multi_profile.py`（HM-25，暫定名） |
| 16 | 414 | `test_registry_reloads_saved_profiles_and_child_env_uses_their_files` | HA：`tests/test_profile_runtime.py`（HM-05）；HA：`tests/test_child_port_param.py`（HM-04） |

#### `packages/mcp-admin-core/tests/test_restore_guard.py`（33 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 45 | `test_restore_publishes_only_revoked_profiles_and_new_admin_generation` | HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #11（管理 generation 不適用） |
| 2 | 61 | `test_missing_profile_fails_without_publishing_or_starting` | §8.8 #23（HA 缺帳號只隔離、不擋開機）；HA：`tests/test_restore_lock.py`（HM-13b） |
| 3 | 73 | `test_existing_destination_is_never_replaced` | 不適用：PaaS 還原先寫到新目的地再發佈；HA 由 Supervisor 原地放回；§8.8 #20 |
| 4 | 83 | `test_unhandled_child_bearer_is_rejected_in_every_profile` | HA：`tests/test_restore_lock.py`（HM-13b），HA 一律重產每個帳號的 child_token |
| 5 | 102 | `test_index_config_mismatch_unindexed_profile_and_symlink_fail_closed` | §8.8 #23；HA：`tests/test_restore_lock.py`（HM-13b），連結由 entrypoint 修復規則拒絕 |
| 6 | 126 | `test_partial_write_and_abrupt_interruption_do_not_publish_or_start` | HA：`tests/test_restore_lock.py`（HM-13b），每一步中途當掉重做、fsync 失敗保留標記 |
| 7 | 163 | `test_concurrent_destination_creation_cannot_be_overwritten` | 不適用：PaaS 還原先寫到新目的地再發佈；HA 由 Supervisor 原地放回；§8.8 #20 |
| 8 | 186 | `test_post_publish_fsync_failure_never_starts_service` | HA：`tests/test_restore_lock.py`（HM-13b），每一步中途當掉重做、fsync 失敗保留標記 |
| 9 | 238 | `test_n8n_restore_rotates_each_internal_pair_and_preserves_history` | HA：`tests/test_restore_lock.py`（HM-13b），child_token 全部重產；§8.8 #22 |
| 10 | 259 | `test_n8n_incomplete_or_unsafe_backup_never_starts` | HA：`tests/test_restore_detection.py`（HM-13a）；§8.8 #20 |
| 11 | 298 | `test_n8n_partial_database_copy_and_crash_do_not_publish` | 不適用：HA 的 n8n nodes.db 在 /tmp、不進備份；§8.8 #47 |
| 12 | 328 | `test_missing_policy_components_never_publish` | HA：`tests/test_restore_lock.py`（HM-13b），鍵集合不符＝讀不到→隔離 |
| 13 | 345 | `test_deeply_nested_input_fails_without_traceback_or_secret` | HA：`tests/test_restore_lock.py`（HM-13b）；HA：`tests/log_scan.py`（HM-01） |
| 14 | 354 | `test_untrusted_configuration_keys_are_not_logged` | HA：`tests/test_restore_lock.py`（HM-13b）；HA：`tests/log_scan.py`（HM-01） |
| 15 | 370 | `test_journal_is_archived_and_old_operation_id_cannot_replay` | HA：`tests/test_restore_lock.py`（HM-13b），舊收據封存、舊操作 ID 回 410 |
| 16 | 405 | `test_n8n_bad_journal_is_not_discarded_or_published` | HA：`tests/test_restore_lock.py`（HM-13b），舊收據封存、舊操作 ID 回 410 |
| 17 | 416 | `test_n8n_incomplete_catalog_schema_cannot_be_published` | 不適用：HA 的 n8n nodes.db 在 /tmp、不進備份；§8.8 #47 |
| 18 | 432 | `test_n8n_wrong_runtime_or_broken_search_index_cannot_be_published` | 不適用：HA 的 n8n nodes.db 在 /tmp、不進備份；§8.8 #47 |
| 19 | 451 | `test_journal_capacity_compacts_without_losing_bytes_and_can_restore_again` | §8.8 #67 |
| 20 | 482 | `test_corrupt_journal_bundle_is_rejected_without_publication` | §8.8 #67 |
| 21 | 497 | `test_ambiguous_journal_is_rejected_in_either_profile` | HA：`tests/test_restore_lock.py`（HM-13b），舊收據封存、舊操作 ID 回 410 |
| 22 | 528 | `test_compaction_preserves_every_profile_across_repeated_restores` | §8.8 #67 |
| 23 | 568 | `test_archive_bundle_capacity_failure_preserves_source` | §8.8 #67 |
| 24 | 587 | `test_restore_never_decreases_journal_expiry_even_if_snapshot_clock_was_ahead` | HA：`tests/test_restore_lock.py`（HM-13b），舊收據封存、舊操作 ID 回 410 |
| 25 | 611 | `test_unmarked_legacy_config_with_unknown_security_switches_is_rejected` | HA：`tests/test_restore_lock.py`（HM-13b），讀不到的 state 改名隔離；§8.8 #66 |
| 26 | 628 | `test_reset_backup_regular_file_at_root_is_skipped_never_read_or_copied` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 27 | 663 | `test_reset_backup_lookalike_names_are_still_rejected` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 28 | 673 | `test_reset_backup_exact_name_that_is_not_a_regular_file_is_rejected` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 29 | 690 | `test_reset_backup_is_only_ignored_at_the_root_not_inside_a_profile` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 30 | 705 | `test_admin_sessions_database_and_companions_at_root_are_skipped_never_read_or_copied` | 不適用：Headscale 的 admin session 資料庫；HA 沒有管理登入；§8.8 #11 |
| 31 | 744 | `test_admin_sessions_lookalike_names_are_still_rejected` | 不適用：Headscale 的 admin session 資料庫；HA 沒有管理登入；§8.8 #11 |
| 32 | 756 | `test_admin_sessions_exact_name_that_is_not_a_regular_file_is_rejected` | 不適用：Headscale 的 admin session 資料庫；HA 沒有管理登入；§8.8 #11 |
| 33 | 774 | `test_admin_sessions_files_are_only_ignored_at_the_root_not_inside_a_profile` | 不適用：Headscale 的 admin session 資料庫；HA 沒有管理登入；§8.8 #11 |

#### `packages/mcp-admin-core/tests/test_restore_guard_n8n_integration.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 39 | `test_n8n_two_real_children_restore_and_profile_isolation` | HA：`tests/test_restore_lock.py`（HM-13b）；HA：`tests/test_n8n_multi_profile.py`（HM-25，暫定名） |

#### `packages/mcp-admin-core/tests/test_restore_guard_odoo_integration.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 34 | `test_real_two_profile_restore_revokes_tokens_and_admin_session` | HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #11（admin session 部分不適用） |

#### `packages/mcp-admin-core/tests/test_restore_inplace.py`（23 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 252 | `test_restore_revokes_backup_and_live_credentials_and_removes_marker` | HA：`tests/test_restore_lock.py`（HM-13b） |
| 2 | 267 | `test_crash_after_each_step_keeps_marker_then_rerun_converges` | HA：`tests/test_restore_lock.py`（HM-13b） |
| 3 | 282 | `test_crash_inside_a_step_then_rerun_starts_over_and_converges` | HA：`tests/test_restore_lock.py`（HM-13b） |
| 4 | 298 | `test_failure_at_each_step_keeps_marker_and_prints_only_fixed_text` | HA：`tests/test_restore_lock.py`（HM-13b） |
| 5 | 310 | `test_invalid_backup_fails_before_moving_live_data` | 不適用：PaaS 原地還原工具的參數與執行身分；HA 由 Supervisor 還原、守門在開機時跑；§8.8 #20 |
| 6 | 326 | `test_verification_rejects_a_bad_publication_and_keeps_old_state_for_rerun` | HA：`tests/test_restore_lock.py`（HM-13b），第 E 步獨立驗證不過就保留標記、不開 listener |
| 7 | 338 | `test_rerun_after_success_is_a_fresh_restore` | HA：`tests/test_restore_lock.py`（HM-13b） |
| 8 | 346 | `test_refusals_change_nothing` | 不適用：PaaS 原地還原工具的參數與執行身分；HA 由 Supervisor 還原、守門在開機時跑；§8.8 #20 |
| 9 | 393 | `test_live_root_trust_rule` | 不適用：k8s 卷根目錄與唯讀掛載細節；§8.8 #20 |
| 10 | 408 | `test_volume_root_source_ignores_only_its_own_lost_and_found` | 不適用：k8s 卷根目錄與唯讀掛載細節；§8.8 #20 |
| 11 | 438 | `test_volume_root_owner_rule` | HA：`tests/test_restore_detection.py`（HM-13a），訊號 1：`/data/mcp` 屬 root |
| 12 | 448 | `test_read_only_mount_detection` | 不適用：k8s 卷根目錄與唯讀掛載細節；§8.8 #20 |
| 13 | 460 | `test_in_place_restore_from_a_read_only_volume_root_with_lost_and_found` | 不適用：k8s 卷根目錄與唯讀掛載細節；§8.8 #20 |
| 14 | 471 | `test_overlapping_run_is_refused_while_another_holds_the_marker` | HA：`tests/test_restore_detection.py`（HM-13a），標記已存在就保留 |
| 15 | 496 | `test_running_as_root_is_refused` | 不適用：PaaS 原地還原工具的參數與執行身分；HA 由 Supervisor 還原、守門在開機時跑；§8.8 #20 |
| 16 | 511 | `test_source_and_live_reset_backups_are_never_restored_and_all_tokens_die` | HA：`tests/test_restore_lock.py`（HM-13b），token 全部失效；reset 備份檔部分不適用 |
| 17 | 532 | `test_crash_with_reset_backups_present_then_rerun_converges` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 18 | 543 | `test_live_only_reset_backup_is_discarded` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 19 | 551 | `test_source_reset_backup_lookalike_still_fails_before_touching_live` | 不適用：PaaS 的 reset 備份檔；HA 沒有這種檔 |
| 20 | 652 | `test_headscale_volume_restores_without_its_admin_sessions_database` | 不適用：Headscale admin session 資料庫與 reset 設定；HA 沒有；§8.8 #11 |
| 21 | 666 | `test_headscale_admin_sessions_sqlite_companions_are_never_restored` | 不適用：Headscale admin session 資料庫與 reset 設定；HA 沒有；§8.8 #11 |
| 22 | 683 | `test_headscale_volume_crash_after_each_step_then_rerun_converges` | HA：`tests/test_restore_lock.py`（HM-13b）；HA：`tests/test_headscale_multi_profile.py`（HM-26，暫定名） |
| 23 | 697 | `test_headscale_volume_with_a_reset_config_leftover_restores_neither` | 不適用：Headscale admin session 資料庫與 reset 設定；HA 沒有；§8.8 #11 |

#### `packages/mcp-admin-core/tests/test_restore_runbook.py`（53 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 334 | `test_step5_reruns_instead_of_reporting_the_previous_job` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 2 | 351 | `test_step5_stops_when_the_old_job_cannot_be_deleted` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 3 | 362 | `test_step5_stops_when_old_pods_are_left_behind` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 4 | 371 | `test_step5_stops_when_old_pods_cannot_be_listed` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 5 | 380 | `test_step5_stops_when_create_fails` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 6 | 391 | `test_job_report_reads_only_pods_of_the_given_job` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 7 | 409 | `test_wait_job_stops_when_the_job_was_replaced` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 8 | 417 | `test_preflight_blocks_do_not_report_a_previous_check` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 9 | 430 | `test_job_blocks_never_apply_jobs_and_always_pass_the_job_uid` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 10 | 440 | `test_bash_blocks_parse` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 11 | 451 | `test_job_and_configmap_names_carry_the_release` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 12 | 458 | `test_long_or_unusual_release_names_stay_valid_and_distinct` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 13 | 476 | `test_names_refuse_an_empty_release` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 14 | 481 | `test_restoring_another_service_in_the_same_namespace_leaves_this_job_alone` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 15 | 501 | `test_preflight_of_another_service_is_left_alone` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 16 | 511 | `test_step5_refuses_a_restore_job_yaml_with_another_name` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 17 | 521 | `test_job_blocks_use_the_release_names_everywhere` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 18 | 534 | `test_wait_job_stops_at_once_when_the_job_is_deleted` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 19 | 541 | `test_wait_job_keeps_polling_through_api_errors` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 20 | 548 | `test_step5_stops_at_once_when_the_restore_job_is_deleted_while_waiting` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 21 | 673 | `test_inventory_lists_profiles_and_policies_without_credentials` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 22 | 693 | `test_inventory_marks_unreadable_profiles_and_missing_config` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 23 | 707 | `test_inventory_escapes_labels_on_the_terminal` | HA：`packages/mcp-admin-ui/tests/browser/restore-review.spec.mjs`（HM-13c），名稱用文字節點顯示 |
| 24 | 730 | `test_diff_lists_every_kind_of_drift_after_the_restore` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 25 | 745 | `test_diff_accepts_recreated_profiles_and_prints_ok` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 26 | 759 | `test_diff_keeps_flagging_what_is_still_different` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 27 | 776 | `test_diff_does_not_take_a_restored_profile_for_a_recreated_one` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 28 | 788 | `test_diff_flags_restored_profiles_whose_token_is_not_revoked` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 29 | 800 | `test_diff_refuses_missing_files` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 30 | 806 | `test_step1_and_step9_blocks_run_literally` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 31 | 840 | `test_inventory_records_the_restore_job_uid` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 32 | 858 | `test_diff_refuses_a_restored_snapshot_from_another_restore` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 33 | 868 | `test_diff_refuses_a_revoked_profile_missing_from_the_restored_snapshot` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 34 | 878 | `test_step5_and_step9_bind_the_snapshot_to_the_restore_job` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 35 | 909 | `test_step9_stops_without_the_restore_job_uid` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 36 | 924 | `test_inventory_records_reviewed_odoo_methods` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 37 | 939 | `test_diff_flags_a_method_list_widened_by_the_restore` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 38 | 960 | `test_diff_tells_an_unsaved_method_list_from_an_empty_one` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 39 | 971 | `test_diff_flags_a_backend_account_switched_back_by_the_restore` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 40 | 986 | `test_inventory_does_not_record_credentials_inside_backend_urls` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 41 | 1003 | `test_inventory_masks_everything_up_to_the_last_at_sign` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 42 | 1027 | `test_recreated_profile_is_checked_against_every_recorded_field` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 43 | 1099 | `test_inventory_records_the_backend_of_every_product` | HA：`tests/test_restore_review.py`（HM-13c），還原紀錄與核對卡逐帳號列出身分欄位與政策摘要、不含憑證；§8.8 #58 |
| 44 | 1112 | `test_diff_flags_a_recreated_litellm_profile_without_connection` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 45 | 1132 | `test_empty_backend_fields_are_not_recorded` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 46 | 1154 | `test_recreate_line_says_manual_check_when_nothing_is_comparable` | §8.8 #58（HA 看不到還原前狀態，沒有前後比對）；HA：`tests/test_restore_review.py`（HM-13c），核對卡：逐帳號核對後才可重發 |
| 47 | 1174 | `test_token_lines_after_step10_say_it_is_expected` | 不適用：PaaS k8s 還原手冊（Job、ConfigMap、Pod、release 名稱）；HA 由 Supervisor 還原；§8.8 #20 |
| 48 | 1210 | `test_switch_list_matches_every_product_policy` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |
| 49 | 1243 | `test_backend_account_fields_match_every_product_policy` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |
| 50 | 1433 | `test_scan_catches_every_way_of_writing_a_section` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |
| 51 | 1440 | `test_scan_reports_unknown_receivers_and_store_methods_passed_around` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |
| 52 | 1448 | `test_generic_settings_put_only_writes_known_sections` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |
| 53 | 1456 | `test_every_policy_field_written_by_the_apps_is_recorded` | HA：`tests/test_identity_fields.py`（HM-07），欄位分類表，新欄位沒分類就失敗 |

#### `packages/mcp-admin-ui/src/profiles.test.js`（3 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 16 | `authenticated management requests carry the selected profile; global routes do not` | HA：`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11），開通後每個帳號範圍請求都帶 `X-MCP-Profile`（含 `default`）；§8.8 #31；§8.8 #110（每次開面板的第一個 bootstrap 刻意不帶） |
| 2 | 44 | `profile create, rename, and delete use the profile routes and expected bodies` | HA：`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11）；§8.8 #34 |
| 3 | 65 | `log stream uses the profile header and parses split SSE frames` | §8.8 #29 |

#### `packages/mcp-admin-ui/tests/conditional_writes_browser.py`（3 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 118 | `ConditionalWritesBrowser.test_工具啟閉立即回讀且保留操作限制` | HA：`packages/mcp-admin-ui/tests/browser/conditional-writes.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |
| 2 | 135 | `ConditionalWritesBrowser.test_expose草稿儲存與失敗不改相依授權` | HA：`packages/mcp-admin-ui/tests/browser/conditional-writes.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |
| 3 | 162 | `ConditionalWritesBrowser.test_兩個入口與窄螢幕顯示條件說明` | HA：`packages/mcp-admin-ui/tests/browser/conditional-writes.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |

#### `packages/mcp-admin-ui/tests/configuration_runtime_browser.py`（4 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 117 | `RuntimeConfigurationBrowser.test_failed_state_survives_reload_and_retry_never_submits_draft` | HA：`packages/mcp-admin-ui/tests/browser/configuration.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |
| 2 | 129 | `RuntimeConfigurationBrowser.test_conflict_keeps_original_form_revision_and_draft_until_explicit_reload` | HA：`packages/mcp-admin-ui/tests/browser/configuration.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |
| 3 | 149 | `RuntimeConfigurationBrowser.test_delayed_save_response_does_not_replace_newer_input` | HA：`packages/mcp-admin-ui/tests/browser/configuration.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |
| 4 | 165 | `RuntimeConfigurationBrowser.test_settings_refetch_preserves_other_dirty_section_and_its_revision` | HA：`packages/mcp-admin-ui/tests/browser/configuration.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |

#### `packages/mcp-admin-ui/tests/connection-secret-clear-browser.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | HA：`packages/mcp-admin-ui/tests/browser/partial-settings.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過，HM-12 起 `profiles-on` 略過前兩案（網址改到別台卻保留已存金鑰，開通後要重填，DQ-40 ⑨）；HA：`packages/mcp-admin-ui/tests/browser/backend-identity.spec.mjs`（HM-12），開通的版本：重填金鑰、清掉 MCP token 後讀回，衝突時保留草稿；§8.8 #117（開通後網址改到另一個來源時，那條網址的已存秘密改成必填） |

#### `packages/mcp-admin-ui/tests/profile_browser.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11）；§8.8 #11、#36；§8.8 #109（刪除要兩段確認） |

#### `packages/mcp-admin-ui/tests/settings_mask_browser.py`（8 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 124 | `MaskedSettingsBrowser.test_loading_settings_does_not_reveal` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有），單帳號權杖頁；HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），切換帳號藏 token |
| 2 | 131 | `MaskedSettingsBrowser.test_copy_token_and_command_use_revealed_value` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有），單帳號權杖頁；HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），切換帳號藏 token |
| 3 | 142 | `MaskedSettingsBrowser.test_failed_reveal_never_copies_mask` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有），單帳號權杖頁；HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），切換帳號藏 token |
| 4 | 149 | `MaskedSettingsBrowser.test_masked_token_can_revoke_without_reveal_and_rotate_restores_copy` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有）；§8.8 #56 |
| 5 | 174 | `MaskedSettingsBrowser.test_typed_proxy_value_survives_show_hide_and_save` | 不適用：PaaS 的 proxy bearer 設定欄；HA 子程式 bearer 由管理程序自己管、不在面板 |
| 6 | 187 | `MaskedSettingsBrowser.test_external_rotation_refreshes_copy_and_hides_previous_reveal` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有），單帳號權杖頁；HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），切換帳號藏 token |
| 7 | 213 | `MaskedSettingsBrowser.test_stored_proxy_reveal_and_blank_save` | 不適用：PaaS 的 proxy bearer 設定欄；HA 子程式 bearer 由管理程序自己管、不在面板 |
| 8 | 224 | `MaskedSettingsBrowser.test_delayed_reveal_cannot_override_newer_observed_token` | HA：`packages/mcp-admin-ui/tests/browser/ui.spec.mjs`（既有），單帳號權杖頁；HA：`packages/mcp-admin-ui/tests/browser/profiles.spec.mjs`（HM-11），切換帳號藏 token |

#### `packages/mcp-admin-ui/tests/write-contracts-browser.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | HA：`packages/mcp-admin-ui/tests/browser/write-contracts.spec.mjs`（既有），單帳號既有測試；HM-11 開關開與關都要照過 |

### B｜#148 新增、查詢沒抓到的檔

#### `packages/mcp-admin-core/tests/test_proxy_interrupted_cause.py`（9 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 84 | `test_connection_error_with_the_child_still_running_says_so` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因 |
| 2 | 105 | `test_child_that_stopped_during_the_request_keeps_the_established_message` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因；§8.8 #100（停止後看 Supervisor 的狀態才說會不會自動重新啟動） |
| 3 | 126 | `test_manager_noticing_the_exit_a_moment_later_is_still_reported_as_stopped` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因；§8.8 #100（停止後看 Supervisor 的狀態才說會不會自動重新啟動） |
| 4 | 145 | `test_batch_and_streams_get_the_same_wording` | HA：`tests/test_gateway_stream_endings.py`（HM-14）；§8.8 #16（batch 從不轉送，403） |
| 5 | 161 | `test_mid_sse_disconnect_with_the_child_still_running` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因 |
| 6 | 173 | `test_mid_sse_disconnect_when_the_child_stopped` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因；§8.8 #100（停止後看 Supervisor 的狀態才說會不會自動重新啟動） |
| 7 | 186 | `test_buffered_tools_list_disconnect_follows_the_same_rule` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因 |
| 8 | 198 | `test_log_line_names_the_cause_without_a_traceback_or_token` | HA：`tests/test_gateway_stream_endings.py`（HM-14）；HA：`tests/log_scan.py`（HM-01）；§8.8 #93（每帳號每種原因 60 秒一行） |
| 9 | 234 | `test_real_child_killed_mid_request_is_reported_as_stopped` | HA：`tests/test_gateway_stream_endings.py`（HM-14），`-32004` 依原因；§8.8 #100（停止後看 Supervisor 的狀態才說會不會自動重新啟動） |

#### `packages/mcp-admin-core/tests/test_initialize_fence_backpressure.py`（5 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 72 | `test_token_rotated_while_the_headers_are_stuck_gets_a_clean_403_and_no_exception` | HA：`tests/test_gateway_stream_endings.py`（HM-14），標頭前換 token 乾淨拒絕、不丟例外給 uvicorn；§8.8 #1（HA 拒絕碼是 401／404） |
| 2 | 109 | `test_token_rotated_in_the_same_instant_the_headers_are_accepted_ends_cleanly` | HA：`tests/test_gateway_stream_endings.py`（HM-14）；§8.8 #92（一次送完的 JSON 帶 Content-Length，標頭已送出就關連線） |
| 3 | 142 | `test_old_token_stays_rejected_after_the_fence_answered` | HA：`tests/test_gateway_stream_endings.py`（HM-14），標頭前換 token 乾淨拒絕、不丟例外給 uvicorn；§8.8 #1（HA 拒絕碼是 401／404） |
| 4 | 219 | `test_only_the_fences_own_rejection_is_swallowed_never_another_error` | HA：`tests/test_gateway_stream_endings.py`（HM-14）；§8.8 #95（只有一層 LeasedResponse，沒有例外群組） |
| 5 | 235 | `test_a_client_that_reads_nothing_does_not_hold_the_rejection_forever` | HA：`tests/test_gateway_stream_endings.py`（HM-14），標頭前換 token 乾淨拒絕、不丟例外給 uvicorn；§8.8 #1（HA 拒絕碼是 401／404） |

#### `packages/mcp-admin-core/tests/test_proxy_carries_no_request.py`（4 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 112 | `test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane` | HA：`tests/test_carries_no_request.py`（HM-14）；§8.8 #91（判斷函式照 PaaS，HA 的政策只轉送 `notifications/initialized`） |
| 2 | 117 | `test_only_notifications_and_responses_use_the_reserved_lane` | HA：`tests/test_carries_no_request.py`（HM-14）；§8.8 #91（判斷函式照 PaaS，HA 的政策只轉送 `notifications/initialized`） |
| 3 | 122 | `test_only_post_can_use_the_reserved_lane` | HA：`tests/test_carries_no_request.py`（HM-14）；§8.8 #91（判斷函式照 PaaS，HA 的政策只轉送 `notifications/initialized`） |
| 4 | 131 | `test_nothing_parsed_means_the_ordinary_lane` | HA：`tests/test_carries_no_request.py`（HM-14）；§8.8 #91（判斷函式照 PaaS，HA 的政策只轉送 `notifications/initialized`） |

#### `packages/mcp-admin-core/tests/test_proxy_location_hardening.py`（5 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 105 | `test_a_rewritten_location_never_lets_the_client_leave_the_prefix` | 不適用：HA 只轉回子程式的 4 個固定標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`），不轉 Location；§8.8 #4 |
| 2 | 111 | `test_the_oracle_sees_how_the_unprotected_references_left_the_prefix` | 不適用：HA 只轉回子程式的 4 個固定標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`），不轉 Location；§8.8 #4 |
| 3 | 146 | `test_encoded_dot_segments_are_removed_like_literal_ones` | 不適用：HA 只轉回子程式的 4 個固定標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`），不轉 Location；§8.8 #4 |
| 4 | 175 | `test_realistic_locations_are_rewritten_exactly_as_before` | 不適用：HA 只轉回子程式的 4 個固定標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`），不轉 Location；§8.8 #4 |
| 5 | 187 | `test_the_gateway_sends_a_location_that_stays_inside_the_prefix` | 不適用：HA 只轉回子程式的 4 個固定標頭（`mcp-session-id`、`mcp-protocol-version`、`retry-after`、`content-type`），不轉 Location；§8.8 #4 |

#### `packages/mcp-admin-core/tests/test_proxy_bare_url_location.py`（4 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 53 | `test_bare_token_url_redirect_stays_inside_the_prefix` | 不適用：HA 只路由 `/private_<token>/mcp`，裸 `/private_<token>` 是 404、不轉址；§8.8 #3 |
| 2 | 70 | `test_bare_url_with_trailing_slash_keeps_the_token_out_of_the_location` | 不適用：HA 只路由 `/private_<token>/mcp`，裸 `/private_<token>` 是 404、不轉址；§8.8 #3 |
| 3 | 86 | `test_trailing_slash_requests_resolve_against_what_the_client_sent` | 不適用：HA 只路由 `/private_<token>/mcp`，裸 `/private_<token>` 是 404、不轉址；§8.8 #3 |
| 4 | 105 | `test_requests_with_a_path_are_rewritten_exactly_as_before` | 不適用：HA 只路由 `/private_<token>/mcp`，裸 `/private_<token>` 是 404、不轉址；§8.8 #3 |

#### `packages/mcp-admin-core/tests/test_process_long_lines.py`（8 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 85 | `test_child_writing_huge_lines_does_not_stall_and_later_lines_are_still_read` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 2 | 104 | `test_lines_up_to_the_limit_are_kept_whole_exactly_as_before` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 3 | 114 | `test_one_byte_over_the_limit_is_truncated_and_marked` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 4 | 120 | `test_token_straddling_the_cut_is_never_logged_in_pieces` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 5 | 141 | `test_invalid_utf8_and_a_cut_inside_a_multibyte_character_do_not_break_the_loop` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 6 | 152 | `test_the_status_last_output_keeps_only_the_truncated_text` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 7 | 182 | `test_line_iterables_are_still_supported_and_oversized_lines_are_cut_there_too` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |
| 8 | 191 | `test_constants` | HA：`tests/test_child_diagnostics.py`（既有），HA 以 4096 位元組分塊讀、超過 8 KiB 的行丟掉但不停讀；§8.8 #29 |

### C｜研究報告點名的檔

#### `packages/mcp-admin-core/tests/test_config_store.py`（27 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 16 | `test_defaults_seeded_on_first_load` | 不適用：PaaS 預設值與 fresh_env；HA 新安裝全開由既有 `tests/test_writes_default_on.py` 管 |
| 2 | 25 | `test_ensure_file_created_on_init` | 不適用：PaaS 預設值與 fresh_env；HA 新安裝全開由既有 `tests/test_writes_default_on.py` 管 |
| 3 | 37 | `test_new_file_gets_app_fresh_env` | HA：`tests/test_profile_store.py`（HM-07），新帳號一次寫入最終初值（連線全空、政策複製預設帳號當下的值） |
| 4 | 52 | `test_fresh_env_never_touches_existing_file` | 不適用：PaaS 預設值與 fresh_env；HA 新安裝全開由既有 `tests/test_writes_default_on.py` 管 |
| 5 | 63 | `test_fresh_env_does_not_leak_into_shared_defaults` | 不適用：PaaS 預設值與 fresh_env；HA 新安裝全開由既有 `tests/test_writes_default_on.py` 管 |
| 6 | 75 | `test_fresh_env_must_be_declared_env_keys` | 不適用：PaaS 預設值與 fresh_env；HA 新安裝全開由既有 `tests/test_writes_default_on.py` 管 |
| 7 | 86 | `test_put_and_get_roundtrip` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 8 | 91 | `test_get_returns_default_for_missing_key` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 9 | 95 | `test_patch_merges_into_dict_value` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 10 | 102 | `test_bound_connection_rotation_is_atomic_and_preserves_password_changes` | HA：`tests/test_odoo_identity_rotation.py`（HM-12）；§8.8 #59（歷史記 `rotate`） |
| 11 | 137 | `test_initial_bound_connection_setup_keeps_issued_url` | HA：`tests/test_odoo_identity_rotation.py`（HM-12），初次設定不換 |
| 12 | 147 | `test_failed_account_rebind_restores_old_child_and_url` | HA：`tests/test_odoo_identity_rotation.py`（HM-12）；§8.8 #114（停不下或寫入失敗時的回應與重起） |
| 13 | 180 | `test_patch_resets_non_dict_value` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 14 | 186 | `test_persistence_across_instances` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 15 | 193 | `test_deep_merge_keeps_default_subkeys` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 16 | 203 | `test_config_file_mode_0600` | HA：`tests/test_profile_store.py`（HM-07），0600、在 uid 10001 子程序驗 |
| 17 | 210 | `test_default_config_created_mode_0600` | HA：`tests/test_profile_store.py`（HM-07），0600、在 uid 10001 子程序驗 |
| 18 | 218 | `test_reload_picks_up_external_change` | §8.8 #46 |
| 19 | 229 | `test_generation_initialization_persists_and_is_stable` | 不適用：管理密碼與 generation；HA 沒有管理密碼；§8.8 #11 |
| 20 | 238 | `test_load_and_patch_results_cannot_mutate_live_config` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 21 | 251 | `test_unrelated_concurrent_writes_preserve_password_generation` | 不適用：管理密碼與 generation；HA 沒有管理密碼；§8.8 #11 |
| 22 | 267 | `test_concurrent_password_writes_leave_coherent_last_committed_auth` | 不適用：管理密碼與 generation；HA 沒有管理密碼；§8.8 #11 |
| 23 | 281 | `test_failed_atomic_write_keeps_cache_and_file` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 24 | 296 | `test_full_save_cannot_restore_an_earlier_generation` | 不適用：管理密碼與 generation；HA 沒有管理密碼；§8.8 #11 |
| 25 | 308 | `test_full_save_same_password_keeps_current_generation` | 不適用：管理密碼與 generation；HA 沒有管理密碼；§8.8 #11 |
| 26 | 319 | `test_cancelled_disk_write_keeps_lock_until_cache_and_file_match` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |
| 27 | 363 | `test_peek_reads_the_last_committed_snapshot_without_waiting_for_the_lock` | 不適用：PaaS ConfigStore（快取、預設值合併）；HA 是 schema 4 精確鍵的 ProductState、每請求重讀；§8.8 #46 |

#### `packages/mcp-admin-core/tests/test_connection_type_parity.py`（12 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 54 | `test_non_string_connection_rejected_without_effects` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 2 | 73 | `test_trim_and_blank_secret_keep_saved_credentials` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 3 | 89 | `test_odoo_account_rebind_revokes_old_url_without_rotating_on_password_change` | HA：`tests/test_odoo_identity_rotation.py`（HM-12），只換密碼不換 token；§8.8 #113（沒換時回應不帶 `token_rotated`） |
| 4 | 131 | `test_generic_partial_update_and_empty_patch_keep_omitted_fields` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 5 | 150 | `test_missing_and_stale_revision_do_not_save_or_apply` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 6 | 165 | `test_unknown_keys_are_rejected_on_both_routes` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 7 | 187 | `test_gui_payload_is_accepted` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 8 | 200 | `test_misspelled_api_key_field_is_rejected_without_echo_or_effect` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 9 | 216 | `test_generic_invalid_secret_has_no_echo_or_effect` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 10 | 230 | `test_generic_explicit_secret_clear_preserves_null_and_normalizes_other_fields` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 11 | 260 | `test_generic_clear_with_invalid_update_is_atomic` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |
| 12 | 276 | `test_n8n_numeric_non_env_keys_keep_their_declared_contract` | HA：`tests/test_connection_type_parity.py`（既有），單帳號規則每帳號沿用 |

#### `packages/mcp-admin-core/tests/test_token_revocation.py`（12 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 25 | `test_revoke_persists_and_requires_explicit_reissue` | HA：`tests/test_token_history.py`（既有），撤銷後不補發 |
| 2 | 44 | `test_failed_persist_keeps_old_lease_and_history` | HA：`tests/test_token_history.py`（既有） |
| 3 | 57 | `test_concurrent_rotation_and_revoke_have_one_atomic_history` | HA：`tests/test_token_history.py`（既有） |
| 4 | 66 | `test_old_whole_config_save_cannot_undo_revocation` | 不適用：PaaS 整份設定存檔可能蓋回舊 token；HA 沒有整份存檔，token 只經輪替或撤銷改；HA：`tests/test_token_history.py`（既有） |
| 5 | 78 | `test_old_snapshot_cannot_restore_token_or_history_after_reissue` | 不適用：PaaS 整份設定存檔可能蓋回舊 token；HA 沒有整份存檔，token 只經輪替或撤銷改；HA：`tests/test_token_history.py`（既有） |
| 6 | 111 | `test_two_active_streams_close_on_revocation` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 7 | 138 | `test_revocation_during_slow_request_body_prevents_dispatch` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 8 | 164 | `test_revocation_before_upstream_headers_discards_response` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 9 | 185 | `test_revoke_and_headers_same_tick_close_unclaimed_response` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 10 | 196 | `test_repeated_caller_cancellation_finishes_io_cleanup` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 11 | 216 | `test_cancellation_during_successful_header_cleanup_closes_unclaimed_response` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |
| 12 | 239 | `test_revocation_cancels_blocked_downstream_delivery` | HA：`tests/test_active_token_leases.py`（既有），租約語意；HA：`tests/test_profile_routing.py`（HM-08），每帳號一份 TokenAccess |

#### `packages/mcp-admin-core/tests/test_initialize_stop_recovery.py`（10 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 57 | `test_cooperative_header_cancel_allows_stop` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 2 | 71 | `test_stubborn_header_fences_then_new_operation_recovers` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 3 | 121 | `test_cooperative_header_allows_journalled_restart` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 4 | 148 | `test_restart_rechecks_revision_after_unlocked_drain` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 5 | 175 | `test_restart_rereads_journal_after_unlocked_drain` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 6 | 212 | `test_restart_cancelled_caller_finishes_accepted_operation` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 7 | 243 | `test_restart_rejects_replacement_during_unlocked_drain` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 8 | 270 | `test_interrupted_drain_keeps_receipt_unknown_and_new_id_can_recover` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |
| 9 | 310 | `test_profile_b_restart_completes_while_profile_a_drains` | HA：`tests/test_profile_admin_api.py`（HM-10），只重啟該帳號、互不等待；HA：`tests/test_profile_lifecycle.py`（HM-09） |
| 10 | 373 | `test_same_and_new_id_during_drain_preserve_receipts` | HA：`tests/test_initialize_generation.py`（HM-14），initialize 世代；HA：`tests/test_admin_operations.py`（既有），重啟收據；§8.8 #94（HA 沒有 drain，重啟不等閘道） |

#### `packages/mcp-admin-core/tests/test_setup_status.py`（41 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 132 | `test_initialize_answers_a_minimal_server_that_says_what_to_configure` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 2 | 174 | `test_protocol_version_follows_the_client_within_the_supported_range` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 3 | 185 | `test_supported_versions_match_the_handshake_versions_of_the_children_sdk` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 4 | 203 | `test_notifications_and_client_responses_get_202_without_body` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 5 | 210 | `test_ping_returns_an_empty_result` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 6 | 217 | `test_tools_list_offers_only_the_setup_status_tool` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 7 | 239 | `test_tools_call_with_any_name_is_an_error_result_with_the_setup_steps` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 8 | 257 | `test_other_list_methods_return_empty_lists` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 9 | 267 | `test_other_methods_are_method_not_found` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 10 | 274 | `test_server_discover_still_falls_back_to_initialize` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 11 | 282 | `test_get_is_405_and_delete_is_accepted` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 12 | 293 | `test_batch_answers_every_request_in_order` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 13 | 306 | `test_oversized_batch_is_refused_instead_of_amplified` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 14 | 320 | `test_unparseable_body_is_a_parse_error` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 15 | 337 | `test_invalid_messages_are_invalid_request` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 16 | 348 | `test_missing_only_some_fields_lists_only_those` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 17 | 360 | `test_a_real_session_that_loses_its_child_is_told_to_retry_the_tool_it_was_using` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 18 | 380 | `test_initialize_with_a_stale_session_is_answered_as_a_new_client` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 19 | 389 | `test_not_running_for_another_reason_only_points_to_the_logs` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 20 | 414 | `test_guidance_says_how_an_already_connected_client_gets_the_full_tools` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 21 | 440 | `test_products_without_required_fields_say_not_running` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 22 | 447 | `test_no_token_password_backend_url_or_child_output_in_any_answer` | HA：`tests/test_unconfigured_connect.py`（既有）；HA：`tests/log_scan.py`（HM-01） |
| 23 | 481 | `test_admin_url_comes_from_the_request` | 不適用：PaaS 佔位答案帶管理網址；HA 自答不帶網址；§8.8 #68 |
| 24 | 487 | `test_admin_url_keeps_the_root_path` | 不適用：PaaS 佔位答案帶管理網址；HA 自答不帶網址；§8.8 #68 |
| 25 | 495 | `test_unusable_host_header_falls_back_to_a_generic_hint` | 不適用：PaaS 佔位答案帶管理網址；HA 自答不帶網址；§8.8 #68 |
| 26 | 503 | `test_wrong_token_is_refused_before_any_placeholder_answer` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #1 |
| 27 | 522 | `test_wrong_token_with_a_placeholder_session_is_refused` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #1 |
| 28 | 533 | `test_revoked_token_with_a_placeholder_session_is_refused` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #1 |
| 29 | 548 | `test_token_changed_while_the_placeholder_answer_is_prepared_is_refused` | HA：`tests/test_unconfigured_connect.py`（既有）；§8.8 #1 |
| 30 | 579 | `test_legacy_sse_and_other_paths_keep_the_503` | §8.8 #6 |
| 31 | 587 | `test_running_child_that_is_not_listening_yet_is_still_502` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 32 | 596 | `test_restart_attempt_without_required_fields_still_answers_the_setup_steps` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 33 | 604 | `test_tool_manager_does_not_hide_or_block_the_setup_tool` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 34 | 667 | `test_after_the_child_comes_up_the_placeholder_session_gets_404_and_reinitialize_reaches_the_child` | HA：`tests/test_unconfigured_connect.py`（既有），子程式就緒後自答 session 404、要求重連 |
| 35 | 703 | `test_placeholder_session_keeps_the_setup_answers_until_the_child_accepts_connections` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 36 | 715 | `test_placeholder_session_with_required_fields_missing_never_gets_404` | HA：`tests/test_unconfigured_connect.py`（既有），閘道自答 initialize 與 tools/list；§8.8 #68 |
| 37 | 736 | `test_n8n_documentation_mode_is_forwarded_unchanged` | §8.8 #28（n8n 預設帳號照起文件模式；額外帳號沒後端不起） |
| 38 | 793 | `test_healthz_reports_a_coarse_mcp_state` | §8.8 #7 |
| 39 | 801 | `test_healthz_stays_200_when_the_config_cannot_be_read` | §8.8 #7 |
| 40 | 816 | `test_healthz_does_not_wait_for_a_slow_config_write` | §8.8 #7 |
| 41 | 859 | `test_healthz_without_a_snapshot_waits_only_briefly_for_the_config` | §8.8 #7 |

#### `packages/mcp-admin-core/tests/test_restore_marker.py`（9 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 110 | `test_marker_refuses_startup_before_migration_token_and_children` | HA：`tests/test_restore_detection.py`（HM-13a）；HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #20（PaaS 標記讓啟動失敗；HA 標記觸發開機守門） |
| 2 | 129 | `test_marker_blocks_app_level_lifespan_wrappers_and_absent_marker_starts_normally` | HA：`tests/test_restore_detection.py`（HM-13a）；HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #20（PaaS 標記讓啟動失敗；HA 標記觸發開機守門） |
| 3 | 168 | `test_core_lifespan_itself_refuses_when_called_directly` | HA：`tests/test_restore_detection.py`（HM-13a）；HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #20（PaaS 標記讓啟動失敗；HA 標記觸發開機守門） |
| 4 | 184 | `test_every_product_app_refuses_before_its_own_seed_or_migration` | HA：`tests/test_restore_detection.py`（HM-13a）；HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #20（PaaS 標記讓啟動失敗；HA 標記觸發開機守門） |
| 5 | 198 | `test_missing_config_during_restore_is_not_replaced_by_factory_defaults` | HA：`tests/test_profile_store.py`（HM-07），額外帳號 store 只開既有、缺 state 不補建 |
| 6 | 208 | `test_config_store_never_creates_a_factory_config_during_a_restore` | HA：`tests/test_profile_store.py`（HM-07），額外帳號 store 只開既有、缺 state 不補建 |
| 7 | 228 | `test_marker_detection_fails_closed` | HA：`tests/test_restore_detection.py`（HM-13a），建不出標記且有帳號資料就拒絕啟動 |
| 8 | 294 | `test_uvicorn_exits_3_without_listening_and_without_touching_config` | HA：`tests/test_restore_lock.py`（HM-13b），守門不過就不開 listener |
| 9 | 339 | `test_uvicorn_real_product_app_refuses_before_its_seed_defaults` | HA：`tests/test_restore_detection.py`（HM-13a）；HA：`tests/test_restore_lock.py`（HM-13b）；§8.8 #20（PaaS 標記讓啟動失敗；HA 標記觸發開機守門） |

#### `packages/mcp-admin-core/tests/test_child_identity_proc.py`（15 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_proc_net_addresses_are_decoded_per_32_bit_word` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 2 | 30 | `test_only_addresses_that_accept_loopback_v4_connections_count` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 3 | 41 | `test_listener_report_owned_foreign_and_not_listening` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 4 | 54 | `test_wildcard_listener_counts_and_other_loopback_address_does_not` | HA：`tests/test_child_identity.py`（HM-15，條件式）；§8.8 #13 |
| 5 | 70 | `test_port_occupied_detects_listeners_and_ignores_free_ports` | HA：`tests/test_profile_ports.py`（HM-09），試綁四種位址確認沒人佔；§8.8 #89（IPv6 試綁被平台擋時跳過） |
| 6 | 79 | `test_port_occupied_detects_a_bound_socket_without_reuse` | HA：`tests/test_profile_ports.py`（HM-09），試綁四種位址確認沒人佔；§8.8 #89（IPv6 試綁被平台擋時跳過） |
| 7 | 85 | `test_port_occupied_detects_ipv6_loopback_listener` | HA：`tests/test_profile_ports.py`（HM-09），試綁四種位址確認沒人佔；§8.8 #89（IPv6 試綁被平台擋時跳過） |
| 8 | 98 | `test_admin_listener_ports_lists_this_process_listeners` | HA：`tests/test_profile_ports.py`（HM-09），避開 3000、8081、8099 |
| 9 | 116 | `test_uvicorn_command_line_port` | 不適用：PaaS 子程式以 uvicorn 參數帶 port；HA：`tests/test_child_port_param.py`（HM-04），port 由 child_spec 組出 |
| 10 | 121 | `test_spawn_argv_sets_parent_death_signal_in_the_real_command` | 不適用：PaaS 子程式 exec 包裝（parent death signal）；HA 由 Supervisor 的 subreaper 與整組停止處理，見既有 `tests/test_lifecycle.py` |
| 11 | 134 | `test_spawn_argv_hands_the_exact_env_to_the_real_command` | 不適用：PaaS 子程式 exec 包裝（parent death signal）；HA 由 Supervisor 的 subreaper 與整組停止處理，見既有 `tests/test_lifecycle.py` |
| 12 | 144 | `test_spawn_argv_keeps_the_signal_dispositions_popen_gives_a_direct_child` | 不適用：PaaS 子程式 exec 包裝（parent death signal）；HA 由 Supervisor 的 subreaper 與整組停止處理，見既有 `tests/test_lifecycle.py` |
| 13 | 155 | `test_spawn_argv_leaves_an_unresolvable_command_to_fail_as_before` | 不適用：PaaS 子程式 exec 包裝（parent death signal）；HA 由 Supervisor 的 subreaper 與整組停止處理，見既有 `tests/test_lifecycle.py` |
| 14 | 161 | `test_exec_wrapper_refuses_when_the_expected_parent_is_gone` | 不適用：PaaS 子程式 exec 包裝（parent death signal）；HA 由 Supervisor 的 subreaper 與整組停止處理，見既有 `tests/test_lifecycle.py` |
| 15 | 169 | `test_sweep_group_reports_live_members_without_signalling` | HA：`tests/test_lifecycle.py`（既有），整組收尾 |

#### `apps/n8n/tests/test_profile_capacity.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 11 | `test_n8n_profile_count_tracks_container_limit` | §8.8 #19；HA：`tests/test_n8n_multi_profile.py`（HM-25，暫定名） |

#### `apps/headscale/tests/test_default_profile_waits_for_connection.py`（1 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_default_profile_child_waits_for_base_url_and_api_key` | HA：`tests/test_unconfigured_connect.py`（既有），沒填連線不起子程式；§8.8 #28 |

#### `packages/mcp-admin-ui/src/profileStatus.test.js`（2 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 4 | `profiles disabled for capacity or a port conflict are marked in the chooser` | HA：`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11）；§8.8 #51 |
| 2 | 13 | `the selected disabled profile explains why and how much memory it needs` | HA：`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11）；§8.8 #51 |

#### `packages/mcp-admin-ui/src/operations.test.js`（3 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 5 | `operation IDs use server snapshot plus monotonic elapsed time, not client wall time` | HA：`packages/mcp-admin-ui/tests/operations.test.mjs`（既有） |
| 2 | 15 | `durable operation receipts are isolated by profile and retain the default legacy key` | HA：`packages/mcp-admin-ui/tests/profiles.test.mjs`（HM-11），預設帳號 key 與 4 鍵格式不變、額外帳號 `…:<mount>:<id>` |
| 3 | 22 | `explicit operation key/revision are preserved and unknown outcome remains structured` | HA：`packages/mcp-admin-ui/tests/operations.test.mjs`（既有） |

#### `packages/mcp-admin-core/tests/test_launch_policy.py`（20 案）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 48 | `test_blocked_env_names` | HA：`tests/test_product_boundary.py`（既有），子程式不繼承上層秘密與 GUI 指令 |
| 2 | 53 | `test_allowed_env_names` | HA：`tests/test_product_boundary.py`（既有），子程式不繼承上層秘密與 GUI 指令 |
| 3 | 57 | `test_policy_rejects_blocked_declarations` | HA：`tests/test_product_boundary.py`（既有），子程式不繼承上層秘密與 GUI 指令 |
| 4 | 66 | `test_required_connection_lists_blank_fields_in_declared_order` | §8.8 #28；HA：`tests/test_unconfigured_connect.py`（既有） |
| 5 | 87 | `test_required_connection_declaration_is_validated` | §8.8 #28；HA：`tests/test_unconfigured_connect.py`（既有） |
| 6 | 92 | `test_backend_connection_lists_blank_fields_in_declared_order` | HA：`tests/test_identity_fields.py`（HM-07），每產品的身分欄位與秘密欄位分類 |
| 7 | 118 | `test_backend_connection_declaration_is_validated` | HA：`tests/test_identity_fields.py`（HM-07），每產品的身分欄位與秘密欄位分類 |
| 8 | 124 | `test_a_key_is_either_required_or_backend_not_both` | HA：`tests/test_identity_fields.py`（HM-07），每產品的身分欄位與秘密欄位分類 |
| 9 | 139 | `test_env_with_policy_only_injects_allowlisted` | HA：`tests/test_product_boundary.py`（既有），子程式不繼承上層秘密與 GUI 指令 |
| 10 | 156 | `test_env_without_policy_still_blocks_dangerous_names` | HA：`tests/test_product_boundary.py`（既有），子程式不繼承上層秘密與 GUI 指令 |
| 11 | 167 | `test_resolve_launch_uses_policy_not_config` | HA：`tests/test_product_boundary.py`（既有），固定子程式指令 |
| 12 | 174 | `test_process_start_runs_app_default_not_config_command` | HA：`tests/test_product_boundary.py`（既有），固定子程式指令 |
| 13 | 239 | `test_get_settings_shows_effective_and_hides_seeded_env` | 不適用：PaaS Settings API 的 env 編輯；HA 沒有 env 編輯入口；§8.8 #45 |
| 14 | 251 | `test_put_mcp_server_with_policy` | 不適用：PaaS Settings API 的 env 編輯；HA 沒有 env 編輯入口；§8.8 #45 |
| 15 | 270 | `test_put_connection_with_policy_rejects_unknown_keys` | 不適用：PaaS Settings API 的 env 編輯；HA 沒有 env 編輯入口；§8.8 #45 |
| 16 | 315 | `test_app_policies_match_template_seeds` | 不適用：PaaS LaunchPolicy 的宣告與範本 seed；HA 子程式環境只從 state 組，見既有 `tests/test_product_boundary.py` |
| 17 | 322 | `test_required_connection_only_where_the_child_exits_without_it` | §8.8 #28；HA：`tests/test_unconfigured_connect.py`（既有） |
| 18 | 360 | `test_backend_connection_per_product` | HA：`tests/test_identity_fields.py`（HM-07），每產品的身分欄位與秘密欄位分類 |
| 19 | 372 | `test_backend_connection_labels_are_the_connection_page_labels` | HA：`tests/test_identity_fields.py`（HM-07），每產品的身分欄位與秘密欄位分類 |
| 20 | 379 | `test_app_connection_forms_within_allowlist` | 不適用：PaaS Settings API 的 env 編輯；HA 沒有 env 編輯入口；§8.8 #45 |

### D｜pin 之後合併進來的檔

#### `apps/emqx/tests/test_long_identifiers.py`（9 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 106 | `test_an_overlong_identifier_gets_the_fixed_code_and_never_leaves_the_process` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 2 | 122 | `test_the_fixed_code_does_not_depend_on_what_the_long_value_is_made_of` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 3 | 133 | `test_the_real_child_prints_no_traceback_to_its_stdout_for_an_overlong_identifier` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 4 | 181 | `test_a_path_value_that_cannot_be_encoded_is_refused_with_the_fixed_code` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 5 | 190 | `test_a_request_that_cannot_be_built_is_denied_before_any_io` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 6 | 201 | `test_a_path_httpx_would_refuse_is_denied_before_the_path_analysis_does_any_work` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 7 | 213 | `test_a_lone_surrogate_in_a_tool_argument_gets_the_fixed_code` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 8 | 228 | `test_a_long_but_valid_identifier_still_reaches_the_broker_unchanged` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 9 | 237 | `test_the_limit_is_on_the_encoded_length_so_a_cjk_value_stops_earlier` | 不適用：EMQX 單帳號的工具修正（PaaS #153：超長識別字的固定錯誤碼），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |

#### `apps/emqx/tests/test_prometheus_accept.py`（14 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 56 | `test_the_prometheus_tool_asks_for_text_and_returns_the_exposition_text` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 2 | 65 | `test_the_exposition_text_is_cut_at_max_bytes_not_in_the_middle_of_json` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 3 | 75 | `test_a_broker_that_still_answers_json_is_passed_through_as_before` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 4 | 85 | `test_every_other_tool_keeps_asking_for_json` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 5 | 108 | `test_empty_exposition_text_is_refused_not_reported_as_success` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 6 | 115 | `test_a_204_for_the_text_request_is_not_an_empty_success_either` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 7 | 121 | `test_text_over_4_mib_is_refused` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 8 | 128 | `test_exactly_4_mib_of_text_is_still_served_and_truncated` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 9 | 135 | `test_compressed_text_is_refused` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 10 | 143 | `test_error_statuses_for_the_text_request_are_mapped_like_any_other_tool` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 11 | 151 | `test_other_tools_still_refuse_empty_and_malformed_200_json` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 12 | 161 | `test_transport_serves_text_only_when_asked_with_the_fixed_value` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 13 | 175 | `test_any_other_accept_value_is_refused_before_io` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 14 | 183 | `test_callers_still_cannot_pass_headers_or_other_request_options` | 不適用：EMQX 單帳號的工具修正（PaaS #153：Prometheus 統計改回文字格式），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |

#### `apps/emqx/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/emqx/tests/test_subscription_match_topic.py`（6 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 45 | `test_descriptions_no_longer_claim_the_opposite_direction` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 2 | 53 | `test_match_topic_parameter_states_what_the_broker_really_does` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 3 | 64 | `test_tool_description_names_the_way_to_answer_who_receives` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 4 | 77 | `test_match_topic_is_forwarded_unchanged_as_a_query_parameter` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 5 | 87 | `test_other_filters_keep_their_query_names` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |
| 6 | 97 | `test_rows_are_returned_as_the_broker_sent_them_without_client_side_matching` | 不適用：EMQX 單帳號的工具修正（PaaS #153：`match_topic` 的說明與參數），不是多帳號行為，HA 要不要跟進交 HM-23 對照（FEATURE-MATRIX §2.12） |

#### `apps/emqx/tests/test_transport.py`（1 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 108 | `test_each_request_resolves_and_uses_fresh_pinned_socket` | HA：`tests/test_fresh_backend_connections.py`（HM-32），`test_each_request_resolves_and_uses_a_fresh_pinned_connection` |

#### `apps/headscale/tests/test_request_structure_guard.py`（6 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 14 | `test_declared_limits_are_unchanged_and_shared_with_the_structure_guard` | §8.8 #106（HA 的 Headscale 和其他產品同一組上限，沒有自己的 McpRequestLimits） |
| 2 | 21 | `test_structure_amplification_outside_the_arguments_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 31 | `test_legitimate_call_is_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 35 | `test_utf16_and_utf32_bodies_are_refused_before_any_parsing` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 45 | `test_valid_utf8_cjk_and_emoji_is_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 6 | 51 | `test_structure_refusal_has_the_same_format_as_the_other_products` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/hermes/tests/test_dashboard_response_shapes.py`（2 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 206 | `test_cron_create_sends_consistent_pause_flags` | HA：`tests/test_hermes_cron_paused_contract.py`（既有），HA PR #85，2026-11-12 合併、還沒發版 |
| 2 | 231 | `test_cron_create_strict_legacy_schema_rejects_without_unsafe_retry` | HA：`tests/test_hermes_cron_paused_contract.py`（既有），HA PR #85，2026-11-12 合併、還沒發版 |

#### `apps/hermes/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/k8s/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | 不適用：HA 沒有 k8s 產品 |
| 2 | 30 | `test_too_deep_request_is_refused` | 不適用：HA 沒有 k8s 產品 |
| 3 | 38 | `test_too_many_elements_are_refused` | 不適用：HA 沒有 k8s 產品 |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | 不適用：HA 沒有 k8s 產品 |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | 不適用：HA 沒有 k8s 產品 |

#### `apps/litellm/tests/test_recovery_pool.py`（1 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 60 | `test_first_key_info_after_health_recovery_uses_fresh_connection` | HA：`tests/test_fresh_backend_connections.py`（HM-32），`test_the_first_call_after_a_recovery_uses_a_fresh_connection` |

#### `apps/litellm/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/n8n/tests/test_request_structure_guard.py`（6 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 14 | `test_declared_limits_are_unchanged_and_shared_with_the_structure_guard` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |
| 2 | 21 | `test_structure_amplification_outside_the_arguments_is_refused` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |
| 3 | 31 | `test_legitimate_call_is_parsed` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |
| 4 | 35 | `test_utf16_and_utf32_bodies_are_refused_before_any_parsing` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |
| 5 | 45 | `test_valid_utf8_cjk_and_emoji_is_parsed` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |
| 6 | 51 | `test_structure_refusal_has_the_same_format_as_the_other_products` | HA：`tests/test_request_structure.py`（HM-31），n8n 先跑同一道守門、拒收照 PaaS（`test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does`） |

#### `apps/nextcloud/tests/test_base_url_ssrf.py`（20 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 168 | `test_save_refuses_urls_the_core_refuses_and_keeps_the_config` | §8.8 #39（Nextcloud 的存檔與測試連線）；HA：`tests/test_saved_destinations.py`（HM-20 擴充），開通後存檔拒 loopback |
| 2 | 185 | `test_save_refuses_before_any_effect_whatever_restart_says` | §8.8 #39（Nextcloud 的存檔與測試連線）；HA：`tests/test_saved_destinations.py`（HM-20 擴充），開通後存檔拒 loopback |
| 3 | 210 | `test_save_accepts_legitimate_public_urls` | HA：`tests/test_saved_destinations.py`（HM-20 擴充），區網與公開網址照存 |
| 4 | 217 | `test_save_checks_each_hostname_through_the_resolver_only` | §8.8 #39（HA 存檔不解析 DNS，名稱留到連線時解析後擋） |
| 5 | 225 | `test_save_refuses_a_name_that_does_not_resolve` | §8.8 #39（HA 存檔不解析 DNS，名稱留到連線時解析後擋） |
| 6 | 236 | `test_clearing_and_unconfigured_accounts_are_not_checked` | HA：`tests/test_saved_destinations.py`（HM-20 擴充），只檢查這次改到的網址 |
| 7 | 248 | `test_save_still_rejects_malformed_urls_before_the_ssrf_check` | HA：`tests/test_saved_destinations.py`（既有），既有的存檔檢查（帶帳密、`?`、路徑寫法） |
| 8 | 258 | `test_a_check_that_blows_up_is_a_400_not_a_500` | §8.8 #39（HA 存檔的 loopback 檢查不解析 DNS） |
| 9 | 292 | `test_modes_follow_the_core_documentation` | §8.8 #39、#45（HA 沒有 SSRF 模式的設定） |
| 10 | 309 | `test_launch_policy_declares_base_url_as_the_url_field` | HA：`tests/test_identity_fields.py`（HM-07），每產品的網址欄位與秘密欄位分類 |
| 11 | 319 | `test_shared_settings_connection_path_is_guarded_too` | §8.8 #39、#86；HA：`tests/test_saved_destinations.py`（HM-20 擴充），開通後存檔拒 loopback |
| 12 | 335 | `test_extra_accounts_go_through_the_same_check` | HA：`tests/test_saved_destinations.py`（HM-20 擴充），開通後存檔拒 loopback；HA：`tests/test_backend_loopback.py`（HM-20），額外帳號的子程式也拒 |
| 13 | 379 | `test_check_nextcloud_sends_nothing_to_a_blocked_address` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 14 | 388 | `test_check_nextcloud_still_reaches_a_public_address` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 15 | 395 | `test_check_nextcloud_keeps_reporting_malformed_settings_first` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 16 | 404 | `test_test_connection_sends_nothing_and_answers_the_same_for_a_closed_port_and_a_live_service` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 17 | 422 | `test_test_connection_follows_the_mode_and_does_reach_loopback_in_moderate` | §8.8 #39、#45（HA 沒有 SSRF 模式的設定） |
| 18 | 435 | `test_test_connection_with_an_unset_url_is_unchanged` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 19 | 441 | `test_health_endpoint_does_not_probe_a_blocked_address` | §8.8 #39；HA：`tests/test_backend_loopback.py`（HM-20），子程式連線前檢查，被擋的一個請求都不送 |
| 20 | 453 | `test_connection_forms_keep_working_end_to_end` | HA：`tests/test_saved_destinations.py`（HM-20 擴充），區網與公開網址照存 |

#### `apps/nextcloud/tests/test_identity_bound_token.py`（22 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 286 | `test_launch_policy_declares_base_url_and_username_as_the_identity` | HA：`tests/test_identity_fields.py`（HM-07），Nextcloud 的 url、username 是身分、app_password 是秘密，換 token 由 HM-22 接上 |
| 2 | 295 | `test_update_response_model_carries_token_rotated` | §8.8 #113 |
| 3 | 310 | `test_identity_change_revokes_the_old_url_and_issues_a_new_one` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 4 | 349 | `test_changing_only_the_app_password_keeps_the_token` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 5 | 383 | `test_a_different_spelling_of_the_same_url_is_not_an_identity_change` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 6 | 402 | `test_a_really_different_url_is_an_identity_change` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 7 | 411 | `test_a_legacy_unnormalized_stored_url_is_not_rotated_by_resaving_the_form` | HA：`tests/test_nextcloud_multi_profile.py::test_normalized_credentials_and_legacy_url_on_save`：兩條路由沿用等價舊網址與 token |
| 8 | 434 | `test_first_time_setup_keeps_the_issued_url` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 9 | 449 | `test_a_revoked_or_missing_token_is_not_replaced_by_an_identity_change` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154） |
| 10 | 463 | `test_clearing_the_identity_rotates_and_filling_it_back_does_not` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；HA：`tests/test_odoo_identity_rotation.py`（HM-12），Odoo 同一套規則：先停再提交、含清空、額外帳號只換自己的 |
| 11 | 484 | `test_the_old_child_is_stopped_before_the_new_identity_becomes_durable` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；HA：`tests/test_odoo_identity_rotation.py`（HM-12），Odoo 同一套規則：先停再提交、含清空、額外帳號只換自己的 |
| 12 | 503 | `test_a_failed_write_leaves_the_old_token_and_the_old_child_intact` | §8.8 #114（HA 寫入失敗一律 503 state unavailable）；HA：`tests/test_odoo_identity_rotation.py`（HM-12） |
| 13 | 549 | `test_an_extra_account_rotates_only_its_own_token` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；HA：`tests/test_odoo_identity_rotation.py`（HM-12），Odoo 同一套規則：先停再提交、含清空、額外帳號只換自己的 |
| 14 | 580 | `test_the_shared_settings_route_rotates_the_token_too` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；§8.8 #59、#86（HA 只有一套管理操作，歷史記 `rotate`） |
| 15 | 597 | `test_the_shared_route_keeps_the_token_for_a_password_or_a_same_url_spelling` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；§8.8 #86 |
| 16 | 610 | `test_the_shared_route_validates_the_url_like_the_connection_page` | §8.8 #86；HA：`tests/test_saved_destinations.py`（既有），既有的存檔檢查 |
| 17 | 626 | `test_a_stale_or_missing_revision_does_nothing` | HA：`tests/test_profile_admin_api.py`（HM-10），過期或沒帶版本就不寫、子程式不動 |
| 18 | 639 | `test_a_blocked_url_stores_nothing_and_does_not_rotate` | §8.8 #39；HA：`tests/test_saved_destinations.py`（HM-20 擴充），開通後存檔拒 loopback |
| 19 | 693 | `test_the_response_message_says_the_old_url_was_revoked_and_the_child_restarted` | §8.8 #113、#116（HA 回應不帶文字，面板依 `token_rotated` 自己提示） |
| 20 | 711 | `test_a_failed_restart_after_a_rotation_still_tells_the_admin_the_url_changed` | §8.8 #113、#116（HA 回應不帶文字，面板依 `token_rotated` 自己提示） |
| 21 | 724 | `test_a_password_only_save_adds_no_notice_and_keeps_the_restart_flag_semantics` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；§8.8 #113 |
| 22 | 744 | `test_the_identity_change_log_line_has_no_values` | HA：`tests/test_nextcloud_multi_profile.py`（HM-22，暫定名），Nextcloud 換 url／username 換 token（DQ-05，對照 PaaS #154）；HA：`tests/log_scan.py`（HM-01） |

#### `apps/nextcloud/tests/test_log_redaction.py`（11 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 145 | `test_access_log_with_a_registered_secret_formats_and_is_masked` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 2 | 158 | `test_access_log_masking_is_the_same_text_as_before` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 3 | 169 | `test_access_log_without_a_secret_in_the_url_is_untouched` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 4 | 181 | `test_args_keep_their_shape_and_types_when_masked` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 5 | 190 | `test_access_shape_is_kept_for_the_five_uvicorn_arguments` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 6 | 199 | `test_dict_args_are_masked_value_by_value` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 7 | 208 | `test_records_without_args_are_masked_and_do_not_fail` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 8 | 217 | `test_secret_in_the_template_and_non_string_objects_are_masked` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 9 | 227 | `test_secret_split_across_two_arguments_is_still_masked` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 10 | 249 | `test_masked_text_is_the_same_as_masking_the_whole_message` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |
| 11 | 256 | `test_masking_is_idempotent` | 不適用：PaaS Nextcloud 管理 app 自己的紀錄遮罩模組（#152 改成遮罩後保留 args 形狀），HA 沒有這個 app；HA：`tests/test_secret_path.py`（既有），HA 管理程序的紀錄遮罩本來就逐個引數遮、保留 access 格式，uvicorn access log 關閉 |

#### `apps/nextcloud/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/odoo/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `apps/opendesign/tests/test_request_structure_guard.py`（5 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 24 | `test_app_has_the_default_structure_limits` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 30 | `test_too_deep_request_is_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 38 | `test_too_many_elements_are_refused` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 46 | `test_legitimate_large_calls_are_parsed` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 54 | `test_utf16_and_utf32_bodies_are_refused_but_utf8_cjk_and_emoji_pass` | HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime 都經預算與守門；HA：`tests/test_request_structure.py`（HM-31） |

#### `packages/mcp-admin-core/tests/fixtures/log_redaction_443e95a.py`（1 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 1 | （整個檔） | 不適用：PaaS 凍結的 443e95a 遮罩模組，給差分測試用（輔助檔、沒有斷言）；HA：`tests/test_redaction_matrix.py`（HM-02），HA 凍結 bb48449 自己的遮罩做不退步差分 |

#### `packages/mcp-admin-core/tests/test_gateway_budget_defaults.py`（7 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 52 | `test_one_gib_pod_keeps_at_least_200_mib_of_headroom_in_the_sandbox_worst_cases` | HA：`tests/test_request_budget.py`（HM-31），HA 的 1 GiB 指 cgroup 上限或 MemAvailable 減 256 MiB；§8.8 #103 |
| 2 | 64 | `test_old_defaults_would_have_failed_the_sandbox_scenarios` | HA：`tests/test_request_budget.py`（HM-31） |
| 3 | 71 | `test_more_accounts_or_heavier_children_shrink_the_budget` | HA：`tests/test_request_budget.py`（HM-31） |
| 4 | 78 | `test_formula_matches_the_documented_arithmetic` | HA：`tests/test_request_budget.py`（HM-31） |
| 5 | 84 | `test_small_pod_is_clamped_to_the_single_request_ceiling` | HA：`tests/test_request_budget.py`（HM-31） |
| 6 | 89 | `test_environment_variables_still_win` | 不適用：HA 不讀環境變數；§8.8 #104、#45；HA：`tests/test_request_budget.py`（HM-31），設了也不生效 |
| 7 | 96 | `test_amplification_covers_the_measured_worst_case_under_the_structure_guard` | HA：`tests/test_request_budget.py`（HM-31） |

#### `packages/mcp-admin-core/tests/test_gateway_budget_round2.py`（10 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 31 | `test_budget_is_built_at_app_creation_and_invalid_env_warns_on_stdout_and_logs_page` | HA：`tests/test_request_budget_gateway.py`（HM-31），啟動時建立；§8.8 #104（環境變數的 WARNING 不適用） |
| 2 | 51 | `test_request_budget_logger_has_a_stdout_handler` | 不適用：HA 沒有 Logs 頁，WARNING 經 Python 的 lastResort 進 add-on log；§8.8 #29；HA：`tests/test_request_budget.py`（HM-31），logger 名稱 |
| 3 | 58 | `test_invalid_idle_env_warns_without_echoing_the_value` | 不適用：HA 不讀環境變數；§8.8 #104、#45 |
| 4 | 86 | `test_idle_registered_connection_is_dropped_and_returns_the_budget` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 5 | 108 | `test_slow_but_steady_upload_is_not_cut_off` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 6 | 127 | `test_small_requests_are_not_subject_to_the_idle_timeout_and_budget` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 7 | 148 | `test_legacy_sse_messages_refusal_is_503_not_200` | 不適用：HA 沒有 legacy SSE；§8.8 #6 |
| 8 | 186 | `test_client_disconnect_while_draining_a_refused_request_is_not_an_error` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 9 | 196 | `test_refusal_report_is_throttled_per_profile_with_a_suppressed_count` | HA：`tests/test_request_budget.py`（HM-31）；HA：`tests/test_profile_quotas.py`（HM-08） |
| 10 | 222 | `test_chunked_request_refused_mid_stream_still_gets_its_id_back` | HA：`tests/test_request_budget_gateway.py`（HM-31） |

#### `packages/mcp-admin-core/tests/test_gateway_budget_round3.py`（30 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 61 | `test_utf16_and_utf32_bodies_are_refused` | HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 70 | `test_bom_prefixed_bodies_are_refused` | HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 75 | `test_nul_in_the_first_four_bytes_is_refused_like_json_detect_encoding` | HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 80 | `test_bytes_that_are_not_valid_utf8_are_refused` | HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 98 | `test_valid_utf8_with_cjk_and_emoji_passes` | HA：`tests/test_request_structure.py`（HM-31） |
| 6 | 104 | `test_empty_and_plain_ascii_bodies_are_unchanged` | HA：`tests/test_request_structure.py`（HM-31） |
| 7 | 110 | `test_large_valid_utf8_bodies_pass_quickly_and_without_copying_the_whole_body` | HA：`tests/test_request_structure.py`（HM-31） |
| 8 | 119 | `test_a_multibyte_character_split_by_the_chunk_boundary_is_not_misjudged` | HA：`tests/test_request_structure.py`（HM-31） |
| 9 | 128 | `test_mcp_request_limits_refusal_for_utf16_has_no_content_and_the_usual_format` | HA：`tests/test_request_structure.py`（HM-31） |
| 10 | 137 | `test_utf16_refusal_message_is_about_encoding_not_structure` | HA：`tests/test_request_structure.py`（HM-31） |
| 11 | 162 | `test_closing_bracket_flood_does_not_stall_the_scan` | HA：`tests/test_request_structure.py`（HM-31） |
| 12 | 170 | `test_scan_time_does_not_grow_with_body_size` | HA：`tests/test_request_structure.py`（HM-31） |
| 13 | 181 | `test_closers_hidden_after_balanced_structure_are_bounded_too` | HA：`tests/test_request_structure.py`（HM-31） |
| 14 | 189 | `test_closers_never_exceed_the_work_bound_for_valid_nesting` | HA：`tests/test_request_structure.py`（HM-31） |
| 15 | 201 | `test_amplification_covers_the_measured_astral_worst_case` | HA：`tests/test_request_budget.py`（HM-31） |
| 16 | 207 | `test_python_str_really_is_four_bytes_per_character_with_one_astral_character` | HA：`tests/test_request_budget.py`（HM-31） |
| 17 | 219 | `test_two_gib_pod_cannot_be_oom_killed_by_astral_requests_that_fit_the_budget` | HA：`tests/test_request_budget.py`（HM-31），只算 PaaS 量到的放大倍數，不宣稱不會被 OOM；§8.8 #101（閘道＋子程式待 HM-19c） |
| 18 | 235 | `test_one_gib_production_default_is_unchanged_at_the_single_request_floor` | HA：`tests/test_request_budget.py`（HM-31）；§8.8 #103 |
| 19 | 251 | `test_astral_request_is_charged_and_refused_under_a_small_budget` | HA：`tests/test_request_budget.py`（HM-31） |
| 20 | 264 | `test_plain_ascii_big_string_is_still_accepted_by_the_structure_guard` | HA：`tests/test_request_structure.py`（HM-31） |
| 21 | 274 | `test_escaped_quote_does_not_end_the_string` | HA：`tests/test_request_structure.py`（HM-31） |
| 22 | 280 | `test_escaped_backslash_before_a_quote_does_end_the_string` | HA：`tests/test_request_structure.py`（HM-31） |
| 23 | 286 | `test_string_ending_with_backslash_pairs_and_quotes_in_the_slow_path` | HA：`tests/test_request_structure.py`（HM-31） |
| 24 | 294 | `test_element_boundary_is_exactly_the_limit_on_the_fast_path` | HA：`tests/test_request_structure.py`（HM-31） |
| 25 | 302 | `test_element_boundary_is_exactly_the_limit_on_the_slow_path` | HA：`tests/test_request_structure.py`（HM-31） |
| 26 | 341 | `test_utf16_pathological_body_is_refused_and_json_loads_is_never_called` | HA：`tests/test_request_structure.py`（HM-31） |
| 27 | 358 | `test_valid_utf8_cjk_and_emoji_is_forwarded_and_parsed` | HA：`tests/test_request_structure.py`（HM-31） |
| 28 | 366 | `test_structure_refusals_log_one_throttled_warning_per_profile` | HA：`tests/test_request_structure.py`（HM-31） |
| 29 | 398 | `test_total_upload_deadline_env_is_validated` | 不適用：HA 不讀環境變數；§8.8 #104、#105 |
| 30 | 409 | `test_a_trickling_upload_is_dropped_at_the_total_deadline_even_if_it_never_goes_idle` | HA：`tests/test_request_budget_gateway.py`（HM-31），60 秒、今天的 408 形狀；§8.8 #105 |

#### `packages/mcp-admin-core/tests/test_gateway_request_budget.py`（20 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 145 | `test_defaults_derive_from_the_cgroup_memory_limit` | HA：`tests/test_request_budget.py`（HM-31） |
| 2 | 160 | `test_defaults_without_a_cgroup_limit_and_clamps` | HA：`tests/test_request_budget.py`（HM-31），沒有 cgroup 上限時用 MemAvailable 減 256 MiB；§8.8 #103 |
| 3 | 170 | `test_environment_overrides_and_invalid_values_warn` | 不適用：HA 不讀環境變數；§8.8 #104、#45；HA：`tests/test_request_budget.py`（HM-31），設了也不生效 |
| 4 | 200 | `test_small_requests_are_never_charged_or_refused` | HA：`tests/test_request_budget.py`（HM-31） |
| 5 | 213 | `test_profile_and_global_limits_are_independent` | HA：`tests/test_request_budget.py`（HM-31） |
| 6 | 235 | `test_every_profile_can_always_send_one_maximum_size_request` | HA：`tests/test_request_budget.py`（HM-31） |
| 7 | 243 | `test_requests_over_the_single_request_cap_are_not_held` | HA：`tests/test_request_budget.py`（HM-31） |
| 8 | 256 | `test_reservation_is_held_until_proxy_finished_and_every_upstream_closed` | HA：`tests/test_request_budget.py`（HM-31），請求結束時歸還；HA：`tests/test_request_budget_gateway.py`（HM-31），SSE 串流期間仍扣著；HA：`tests/test_profile_quotas.py`（HM-08） |
| 9 | 273 | `test_a_refused_grow_does_not_leak_and_finish_refunds` | HA：`tests/test_request_budget.py`（HM-31） |
| 10 | 285 | `test_thousand_mixed_requests_return_the_budget_to_zero` | HA：`tests/test_request_budget.py`（HM-31） |
| 11 | 340 | `test_transport_returns_the_budget_on_stream_close_error_and_queue_full` | HA：`tests/test_request_budget_gateway.py`（HM-31）；HA：`tests/test_profile_quotas.py`（HM-08），開通的排隊與拒絕 |
| 12 | 384 | `test_over_budget_request_is_refused_immediately_with_the_queue_full_style_reply` | HA：`tests/test_request_budget_gateway.py`（HM-31）；HA：`tests/test_profile_quotas.py`（HM-08），開通的排隊與拒絕 |
| 13 | 408 | `test_refusal_formats_for_get_batch_and_chunked` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 14 | 429 | `test_chunked_request_within_budget_is_forwarded_and_budget_returns` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 15 | 446 | `test_one_profile_filling_its_share_does_not_affect_another` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 16 | 463 | `test_global_budget_is_shared_by_all_profiles` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 17 | 475 | `test_legitimate_13_mib_upload_passes_with_default_budget` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 18 | 488 | `test_flood_of_large_requests_never_holds_more_than_the_budget` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 19 | 508 | `test_budget_returns_after_abandoned_queue_client_disconnect_and_refusals` | HA：`tests/test_request_budget_gateway.py`（HM-31） |
| 20 | 534 | `test_proxy_wrapper_returns_the_budget_when_the_request_raises` | HA：`tests/test_request_budget_gateway.py`（HM-31） |

#### `packages/mcp-admin-core/tests/test_gateway_request_structure.py`（17 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 54 | `test_pathological_16_mib_bodies_are_refused` | HA：`tests/test_request_structure.py`（HM-31） |
| 2 | 59 | `test_one_big_string_has_no_structure_to_refuse` | HA：`tests/test_request_structure.py`（HM-31） |
| 3 | 63 | `test_legitimate_nextcloud_upload_of_13_3_mib_passes` | HA：`tests/test_request_structure.py`（HM-31） |
| 4 | 71 | `test_legitimate_odoo_batch_create_of_thousands_of_records_passes` | HA：`tests/test_request_structure.py`（HM-31） |
| 5 | 81 | `test_legitimate_large_n8n_workflow_passes` | HA：`tests/test_request_structure.py`（HM-31） |
| 6 | 89 | `test_batch_of_thousands_of_small_requests_passes` | HA：`tests/test_request_structure.py`（HM-31），守門放行，HA 的政策另外拒絕 batch（403） |
| 7 | 95 | `test_brackets_and_commas_inside_strings_do_not_count` | HA：`tests/test_request_structure.py`（HM-31） |
| 8 | 100 | `test_depth_boundary` | HA：`tests/test_request_structure.py`（HM-31） |
| 9 | 110 | `test_element_boundary_counts_commas_and_containers` | HA：`tests/test_request_structure.py`（HM-31） |
| 10 | 119 | `test_scanning_cost_is_bounded_by_the_limit_not_the_body_size` | HA：`tests/test_request_structure.py`（HM-31） |
| 11 | 128 | `test_mcp_request_limits_check_structure_error_has_no_content` | HA：`tests/test_request_structure.py`（HM-31），n8n 的拒收不帶內容 |
| 12 | 168 | `test_default_structure_limits_are_installed_by_create_app` | HA：`tests/test_request_structure.py`（HM-31）；HA：`tests/test_request_budget_gateway.py`（HM-31），8 個上架產品的正式 runtime |
| 13 | 178 | `test_pathological_body_is_refused_before_any_forward` | HA：`tests/test_request_structure.py`（HM-31）；§8.8 #6（`messages/` 的參數不適用，HA 沒有 legacy SSE） |
| 14 | 190 | `test_too_deep_body_is_refused_and_the_message_has_no_content` | HA：`tests/test_request_structure.py`（HM-31） |
| 15 | 200 | `test_batch_without_a_recoverable_id_is_refused_with_413` | HA：`tests/test_request_structure.py`（HM-31） |
| 16 | 208 | `test_legitimate_large_calls_still_forward` | HA：`tests/test_request_structure.py`（HM-31） |
| 17 | 219 | `test_non_json_and_non_post_behave_as_before` | HA：`tests/test_request_structure.py`（HM-31）；§8.8 #107 |

#### `packages/mcp-admin-core/tests/test_log_redaction_query_credentials.py`（23 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 102 | `test_query_value_matrix_is_the_reviewed_97_cases` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 2 | 142 | `test_query_value_forms_are_masked_in_stdout_and_ring_buffer` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 3 | 163 | `test_query_value_forms_are_masked_in_app_log_lines` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 4 | 181 | `test_query_value_forms_redaction_is_idempotent` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 5 | 205 | `test_query_value_forms_with_credential_param_names_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 6 | 232 | `test_review_examples_keep_a_readable_access_line` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 7 | 240 | `test_real_uvicorn_access_log_masks_query_value_forms` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 8 | 318 | `test_credential_param_name_list_matches_the_module` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 9 | 326 | `test_credential_param_values_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 10 | 357 | `test_encoded_credential_param_names_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 11 | 379 | `test_ordinary_params_are_not_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 12 | 392 | `test_credential_params_in_access_log_both_sinks` | HA：`tests/test_redaction_matrix.py`（HM-02），HA 關閉 uvicorn access log，只驗遮罩函式本身；DQ-38 選 vendor 時隨模組帶入 |
| 13 | 399 | `test_credential_params_in_child_output_both_sinks` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 14 | 421 | `test_masked_credentials_do_not_hide_a_bare_query` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 15 | 434 | `test_decoded_only_prefix_keeps_later_key_leads` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 16 | 454 | `test_cascading_credential_masks_are_idempotent` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 17 | 560 | `test_pathological_shape_single_redaction_time_is_bounded` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 18 | 569 | `test_pathological_shape_cost_grows_linearly` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 19 | 580 | `test_pathological_shape_has_no_per_segment_python_work` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 20 | 589 | `test_pathological_shape_access_record_cost_is_bounded` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 21 | 603 | `test_truncation_does_not_cut_inside_a_multi_layer_escape` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 22 | 630 | `test_frozen_module_is_443e95a_verbatim` | 不適用：PaaS 凍結自己的 443e95a 模組做差分；HA：`tests/test_redaction_matrix.py`（HM-02），對照 bb48449 自己的遮罩 |
| 23 | 764 | `test_differential_fuzz_never_shows_what_443e95a_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |

#### `packages/mcp-admin-core/tests/test_log_redaction_query_credentials_review.py`（41 案，`48f394d`）

| # | 行 | 案例 | 歸屬 |
|---|---|---|---|
| 1 | 106 | `test_report_counterexamples_are_masked_like_443e95a` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 2 | 113 | `test_report_counterexamples_keep_the_readable_shape_of_443e95a` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 3 | 226 | `test_reviewers_101_minimal_counterexamples_are_masked_like_443e95a` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 4 | 328 | `test_fuzz_found_counterexamples_are_masked_like_443e95a` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 5 | 406 | `test_family_differential_fuzz_never_shows_what_443e95a_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 6 | 433 | `test_line_with_a_token_key_still_masks_values_of_ampersand_led_credentials` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 7 | 440 | `test_line_with_a_token_key_leaves_unclean_values_of_question_and_semicolon_led_credentials_to_443e95a` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 8 | 449 | `test_line_with_a_private_prefix_keeps_the_clean_prefix_rule` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 9 | 457 | `test_two_decoded_only_prefixes_with_a_masked_value_between_them_stay_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 10 | 480 | `test_quoted_credential_before_a_bare_param_in_a_private_url_is_masked_in_one_pass` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 11 | 491 | `test_bare_query_is_judged_again_after_the_key_rules_masked_a_value` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 12 | 500 | `test_bare_query_is_judged_again_after_a_value_rule_masked_something` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 13 | 646 | `test_bare_param_masked_after_an_empty_value_can_become_the_lead_of_a_loose_key` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 14 | 658 | `test_token_key_swallowed_by_another_value_leaves_a_line_that_masks_the_same_again` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 15 | 678 | `test_prefix_that_only_the_spelled_form_recognises_is_judged_the_same_in_both_passes` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 16 | 725 | `test_premask_does_not_expose_a_prefix_that_the_decoded_rules_could_not_see` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 17 | 743 | `test_known_non_idempotent_inputs_are_idempotent_now` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 18 | 750 | `test_redaction_is_idempotent_on_every_corpus` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 19 | 801 | `test_plain_lines_mask_the_whole_value_through_encoded_delimiters` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 20 | 807 | `test_plain_lines_mask_token_values_that_start_with_an_encoded_delimiter` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 21 | 813 | `test_plain_lines_do_not_swallow_the_next_parameter` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 22 | 819 | `test_private_key_parameter_name_is_not_a_prefix` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 23 | 829 | `test_token_key_that_a_later_mask_swallows_does_not_change_the_second_pass` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 24 | 837 | `test_token_value_that_starts_with_a_delimiter_is_masked_through_the_next_delimiter_in_plain_lines` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 25 | 850 | `test_truncation_does_not_cut_the_last_parameter_in_half` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 26 | 863 | `test_dangling_param_helper_backs_off_to_the_last_lead` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 27 | 880 | `test_oauth_session_and_app_key_names_are_credentials` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 28 | 893 | `test_only_complete_names_count` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 29 | 899 | `test_empty_value_followed_by_a_bare_param_is_masked_as_the_pasted_token` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 30 | 910 | `test_install_compiles_every_lazy_pattern_before_the_first_request` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 31 | 920 | `test_fragment_with_ampersand_or_semicolon_and_equals_is_a_candidate` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 32 | 941 | `test_encoded_name_forms_with_a_value_that_starts_with_an_encoded_space_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 33 | 953 | `test_encoded_leads_with_a_value_that_starts_with_an_encoded_space_are_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 34 | 959 | `test_encoded_equals_with_a_value_that_starts_with_an_encoded_space_is_masked` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 35 | 967 | `test_name_that_is_only_recognised_after_decoding_masks_a_value_that_starts_with_x` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 36 | 982 | `test_lenient_clean_prefix_stops_at_every_unclean_character` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 37 | 988 | `test_strict_and_token_values_need_a_whole_clean_value` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 38 | 997 | `test_clean_value_rules_in_detail` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 39 | 1009 | `test_wide_value_runs_to_the_next_literal_delimiter` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 40 | 1032 | `test_prefix_detection_is_linear_on_noise_heavy_input` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |
| 41 | 1064 | `test_decoded_only_prefix_still_masks_question_mark_led_values_that_start_with_an_encoded_space` | HA：`tests/test_redaction_matrix.py`（HM-02），#149 合併版；DQ-38 選 (a) 原樣 vendor |

## pin 之後的變動（`69ac425..48f394d` 的測試檔）

| 檔 | pin 時在範圍內 | 新增案例 | 刪除案例 | 處理 |
|---|---|---|---|---|
| `apps/emqx/tests/conftest.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#153、#135 改測試替身，整個檔算一案），不列 |
| `apps/emqx/tests/test_long_identifiers.py` | 否 | 9 | 0 | 併進 D 組（#153） |
| `apps/emqx/tests/test_prometheus_accept.py` | 否 | 14 | 0 | 併進 D 組（#153） |
| `apps/emqx/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/emqx/tests/test_subscription_match_topic.py` | 否 | 6 | 0 | 併進 D 組（#153） |
| `apps/emqx/tests/test_transport.py` | 否 | 1 | 1 | 併進 D 組（#135，舊的 `test_dns_resolves_once_and_socket_uses_pinned_address` 改寫成新的案例） |
| `apps/headscale/tests/test_request_structure_guard.py` | 否 | 6 | 0 | 併進 D 組（#155） |
| `apps/hermes/tests/test_dashboard_response_shapes.py` | 否 | 2 | 0 | 併進 D 組（#138） |
| `apps/hermes/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/k8s/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/litellm/tests/test_recovery_pool.py` | 否 | 1 | 0 | 併進 D 組（#139） |
| `apps/litellm/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/n8n/tests/test_request_structure_guard.py` | 否 | 6 | 0 | 併進 D 組（#155） |
| `apps/nextcloud/tests/conftest.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#152 改測試替身，整個檔算一案），不列 |
| `apps/nextcloud/tests/test_base_url_ssrf.py` | 否 | 20 | 0 | 併進 D 組（#152） |
| `apps/nextcloud/tests/test_identity_bound_token.py` | 否 | 22 | 0 | 併進 D 組（#154） |
| `apps/nextcloud/tests/test_log_redaction.py` | 否 | 11 | 0 | 併進 D 組（#152） |
| `apps/nextcloud/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/nextcloud/tests/test_setup_status.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#152），不列 |
| `apps/odoo/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `apps/opendesign/tests/test_request_structure_guard.py` | 否 | 5 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/fixtures/log_redaction_443e95a.py` | 否 | 1 | 0 | 併進 D 組（#149） |
| `packages/mcp-admin-core/tests/test_backend_status.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_capabilities.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_configuration_runtime.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_connection_secret_clear.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_gateway_budget_defaults.py` | 否 | 7 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/test_gateway_budget_round2.py` | 否 | 10 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/test_gateway_budget_round3.py` | 否 | 30 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/test_gateway_queue.py` | 是 | 0 | 0 | 只改既有案例的內容（#150 補測還過頭的名額、保留名額逾時 WARNING 的全文、舊測試改成看事件），歸屬照上表 |
| `packages/mcp-admin-core/tests/test_gateway_request_budget.py` | 否 | 20 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/test_gateway_request_structure.py` | 否 | 17 | 0 | 併進 D 組（#155） |
| `packages/mcp-admin-core/tests/test_launch_policy.py` | 是 | 0 | 0 | 只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），歸屬照上表 |
| `packages/mcp-admin-core/tests/test_log_redaction.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#149 把參數裡的 `session_token` 換成遮罩名單外的鍵名，#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_log_redaction_query_credentials.py` | 否 | 23 | 0 | 併進 D 組（#149） |
| `packages/mcp-admin-core/tests/test_log_redaction_query_credentials_review.py` | 否 | 41 | 0 | 併進 D 組（#149） |
| `packages/mcp-admin-core/tests/test_opendesign_config_router.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 之後的文字修正 `8bfb12e`：註解與 docstring 不再指向已移除的 apps/vk），不列 |
| `packages/mcp-admin-core/tests/test_opendesign_health_probes.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 之後的文字修正 `8bfb12e`：註解與 docstring 不再指向已移除的 apps/vk），不列 |
| `packages/mcp-admin-core/tests/test_opendesign_native_launcher.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 之後的文字修正 `8bfb12e`：註解與 docstring 不再指向已移除的 apps/vk），不列 |
| `packages/mcp-admin-core/tests/test_operation_policy.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_product_connection_apply.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_proxy_carries_no_request.py` | 是 | 0 | 0 | 只改既有案例的內容（#151 之後的文字修正 `8bfb12e`：註解與 docstring 不再指向已移除的 apps/vk），歸屬照上表 |
| `packages/mcp-admin-core/tests/test_reprovision_bootstrap.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |
| `packages/mcp-admin-core/tests/test_restore_marker.py` | 是 | 0 | 0 | 只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），歸屬照上表 |
| `packages/mcp-admin-core/tests/test_restore_runbook.py` | 是 | 0 | 0 | 只改既有案例的內容（#151 移除 VK：拿掉一行 VK 的路徑），歸屬照上表 |
| `packages/mcp-admin-core/tests/test_tools_router.py` | 否 | 0 | 1 | 不在多帳號範圍（#151 移除 VK：刪掉 VK 的那一案），不列 |
| `packages/mcp-admin-core/tests/test_vk_app_assembly.py` | 否 | 0 | 1 | 不在多帳號範圍（#151 移除 VK：整個檔刪掉），不列 |
| `packages/mcp-admin-core/tests/test_vk_config_router.py` | 否 | 0 | 14 | 不在多帳號範圍（#151 移除 VK：整個檔刪掉），不列 |
| `packages/mcp-admin-core/tests/test_vk_health_probes.py` | 否 | 0 | 10 | 不在多帳號範圍（#151 移除 VK：整個檔刪掉），不列 |
| `packages/mcp-admin-ui/tests/browser-capabilities.py` | 否 | 0 | 0 | 不在多帳號範圍、只改既有案例的內容（#151 移除 VK：拿掉 VK 的參數與表格列，不動其他產品的斷言），不列 |

其他相關檔：`69ac425..7d111b1` 之間 `gateway_pool.py`、`proxy.py` 只改註解，`log_redaction.py` 是 #149 的正式碼變動（見 `docs/provenance/multi-profile-parity-baseline.md`）；之後的正式碼變動記在對齊它的那一片的筆記（#155 的 `proxy.py`、`gateway_pool.py`、`app.py`、`profiles.py` 等見 `ha-multiprofile-HM-31-20261116.md` 第 4 節；#135、#139 見 HM-32 的筆記第 4 節；#156 見 HM-33 的筆記第 3 節），本表只列測試檔。
