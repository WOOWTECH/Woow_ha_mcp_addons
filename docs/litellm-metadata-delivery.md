# LiteLLM 一般唯讀 metadata batch（experimental candidate）

Base `4300ae07c42c0d16b0cf6a37b98b0af2c791b8ca`；branch `feat/litellm-metadata-20261005`。
這是五個真既有工具的 bounded 子集，不是完整 LiteLLM 產品、後端版本相容承諾或 HA／商用驗收。沒有新 writer/grant、inference、provider health probe、key administration 或跨 instance。

## 工具與 operation 計數

| 範圍 | before | after |
|---|---:|---:|
| 全專案 supported exact tool names / upstream names | 71 / 184 | 76 / 184 |
| LiteLLM supported exact tool names / upstream names | 7 / 40 | 12 / 40 |
| LiteLLM default-readonly tool names | 3 | 8 |
| LiteLLM exact writer grants（仍 default-off） | 4 | 4 |
| 全專案 dispatch units（無 selector 工具各1；混合工具各已支援 selector operation） | 82 | 87 |
| tool-surface 中 explicit supported selector values（包括 mode/target） | 28 | 28 |

五個新增工具沒有 action/operation selector：新增五個 read dispatch units，不新增混合 operation。其他產品及既有 LiteLLM tools/schema/grants/defaults 不變。

## 來源與真 API 契約

- Wrapper 固定來源：`WOOWTECH/Woow_litellm_mcp_server@4d4190369216a2d068d1100d53406a67a1d81609`。
- 原 handler：`apps/litellm/vendor/woow_litellm_mcp_server/tools/{models,teams,users}.py`；原 routes、query names、GET 行為保留。local changes 的原始／本地 SHA256 見 `docs/provenance/runtime-sources.json`；新 local helper（不冒充 upstream）及 schema hash 見 `runtime-patches.json`。
- 補核公開 backend source：[`BerriAI/litellm@be4481779ee8a73579af82a3b5394f62f4e4b057`](https://github.com/BerriAI/litellm/tree/be4481779ee8a73579af82a3b5394f62f4e4b057)，是 API envelope 參考，**不是已部署後端的版本證明**。
  - `litellm/proxy/proxy_server.py`：`model_info_v1`（16126ff）、`model_group_info`（16424ff）：`data` envelope；SHA256 `185d727c2699f45a87c52d9b1ea5af0450ede2909333d8afc9ae11fd357d3bd5`。
  - `litellm/proxy/management_endpoints/team_endpoints.py`：`team_info`（4844ff），`team_id/team_info/keys/team_memberships`；SHA256 `cee2df5ef03e6c615cf2b0d52a7791ec1fd1aa14f720e4fcdf48e7e5baa1be04`。
  - `litellm/proxy/management_endpoints/internal_user_endpoints.py`：`_build_user_info_response`（898ff）、`user_info`（936ff）、`get_users`（2227ff）；SHA256 `29de597805c1124086dfa9e7aaf11092506bef4f8ff3f47d20ed3dc554259004`。
- 不新編 backend。synthetic fixtures 對應這些 envelopes；沒有呼叫真 LiteLLM 或付費 provider。後端自訂 callbacks、auth/cache/log 與內部查詢成本不由 wrapper 保證。

## 新增 accepted schemas 與正向投影

共通：strict、extra forbid、必須已配置單一後端；公開 tools/list 用 core accepted_schema，不直接曝光 upstream 寬鬆 signature。原 handler optional default 並不授權 omission/all-model view。JSON schema 的字元排除補上部分 regex engines `$` 可在末尾換行前匹配的差異。

IDs：1..128 ASCII `[A-Za-z0-9_-]`；不接受 email 型 user ID、逗號、空白、URL 或其它 ID 字元。本批不是完整 upstream ID 相容層。

| 工具 | accepted input／真 GET | 唯一允許的輸出 |
|---|---|---|
| `litellm_model_info` | 必填 `litellm_model_id`；`/model/info?litellm_model_id=…` | `data` 恰1筆且 ID 一致；`model_name`、`model_info.{id,mode,max_input_tokens,max_output_tokens}` |
| `litellm_model_group_info` | 必填 `model_group`，1..256，首字ASCII英數，其餘 `[A-Za-z0-9_./:-]`；`/model_group/info?model_group=…` | `data` 恰1筆且 group 一致；`model_group,mode,max_input_tokens,max_output_tokens,tpm,rpm` |
| `litellm_team_info` | 必填 `team_id`；`/team/info?team_id=…` | `team_id`、`team_info.{team_id,team_alias,max_budget,tpm_limit,rpm_limit,blocked}`；外層與內層ID均须一致 |
| `litellm_list_users` | `page`1..10000/default1、`page_size`1..100/default50；可選 `role`、`user_ids`1..20 IDs、`team`；`user_email/sort_by/sort_order`仅省略或null；`/user/list` | `users` <= requested page_size；每筆 `user_id,user_alias,user_role,max_budget,tpm_limit,rpm_limit`；typed `total,page,page_size,total_pages` |
| `litellm_user_info` | 必填 `user_id`；`/user/info?user_id=…` | `user_id`、`user_info.{user_id,user_alias,user_role,max_budget,tpm_limit,rpm_limit}`；外層與內層ID均须一致 |

- Roles 僅 `proxy_admin,proxy_admin_viewer,internal_user,internal_user_viewer`；這是 metadata，不授權 role mutation。
- Modes 僅 `chat,completion,embedding,image_generation,image_edit,audio_transcription,audio_speech,moderation,rerank,video_generation,search`，或 null／缺省。
- `user_ids` 保留原 handler comma-join 與 backend 語義：核查版本單個值是 case-insensitive substring、多個值是集合比對；**不宣稱 exact-user filter**。
- IDs 必填／selected model name 必填；optional selected欄位缺失則省略，null 原樣保留，不虛構值。字串 <=256 且無 control chars；數值必须finite、0..1e15、非bool；blocked必须bool。錯型直接拒絕，不能悄悄投影成空物件。
- 不回 `litellm_params`、providers、`api_base`、credentials、keys/tokens、prompts/messages、email、成員／teams、spend、私人logs、任意metadata/config。未知欄位排除；此投影不是對 name/alias 中人為塞入敏感文字的通用 DLP。

## 容量、錯誤、相容限制

新 `metadata.py` 只借用原 `LiteLLMHttp.raw` 的 pooled/scoped client（原 origin/DNS/TLS/redirect/error policy 不變），每次一個固定 GET、零 retry／fallback／auto paging。僅本批讀取加上256KiB identity response及5秒總期限；content encoding 非identity拒絕。沒有修改共用 transport 或其它產品的 parser/guard。

JSON 限depth8（root depth0）、每個list100、object128欄、總10000 nodes、key256字元、未投影字串16384字元。包括將被捨棄的內容也受形狀上限，不能先無界讀取再截斷。這些限制可能拒絕含很多keys/members的team/user detail；不偷偷另叫key/member API，也不聲稱限制後端在送回應前的內部掃描。忽略內容仍可能由後端送達但不會回到 MCP 結果。

Model/group 不開省略 selector 的全量掃描、wildcard／多筆／空 detail；即使上游在fresh install回空data，明確detail呼叫也報錯。User list 不自動翻頁，反映一頁；pagination必填、page/page_size等於request、total_pages符合ceil(total/page_size)，非空remaining total不能偽裝空成功。大於本地上限、未知envelope或新增型態須另行review。

非2xx（含401/403/404/429/5xx）固定 `BACKEND_HTTP_ERROR status=N`，不回raw body；缺失、錯shape、非法JSON／超界固定 `BACKEND_INVALID_RESPONSE`；timeout與transport failure沿用既有固定codes。取消保留取消語義，stream關閉。所有新工具的直接禁用call、無後端call、非法參數均在child前拒絕。

## 驗證與後續 gate

- RED：新增root tests在舊policy失敗；真正vendor functions在舊raw-return行為下有42 failing subtests。
- GREEN：`tests/test_litellm_metadata.py`、`tests/litellm_metadata_unit.py`、`tests/test_litellm_metadata_inventory.py`。獨立 pinned LiteLLM interpreter 做handler MockTransport／JSON Schema驗證，不混用core與child依賴。
- `tests/test_litellm_metadata_runtime.py`：在明確slot、shared lock、owned ephemeral端點，原真LiteLLM HTTP child完成initialize/list/五個read及錯誤回歸；現有三個普通read也驗證。只有owned fake backend GET，原私有預設port3000沒有使用。
- scoped inventory重新解析本worktree LiteLLM AST與source hashes，其他產品source證據原樣沿用；未安裝另六app、未跑完整七產品inventory/full suite。原完整inventory測試仍為全環境gate，未偽造fresh驗證。
- 確切命令、counts、exit、job/PID/port/cleanup、resources與manifest見唯一外部報告 `worker-litellm-metadata-batch.md`。此candidate尚需獨立SPEC/security review、真後端受限帳號與版本、HA/Ingress/LAN、部署與商用驗收；Starlette core1.3.1及兩份固定檔未改，仍experimental。
