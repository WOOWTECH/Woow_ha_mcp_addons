import { identityBound, identityChange, mountPath, products, UiError } from './contracts.js';
import { ORIGIN_REVISION, ORIGIN_SCOPE, OperationIdentity, operationKinds, operationReceipt, PROFILES_SCOPE } from './operation-identity.js';
import { DEFAULT_PROFILE, INDEX_ETAG, INDEX_REVISION, echoMatches, isExtraProfile, isProfileId, labelProblem, orphanIds, profileRows } from './profiles.js';
import { QUARANTINE_NAME, quarantinedEntries, recordView, revocationResults } from './restore.js';

// A Core release or pre-release string (the server sends only this form, ha_role.shown_version); anything else is not shown.
const CORE_VERSION = /^[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,3}(?:(?:a|b|rc)[0-9]{1,3}|\.dev[0-9]{1,14})?$/;
// HM-11 (contract 4.1): the profile codes the panel knows, each only with its documented status.
const PROFILE_CODES = { profile_id_required: 400, profile_id_invalid: 400, profile_not_found: 404, profile_label_invalid: 422,
  profile_default_immutable: 422, profile_label_conflict: 409, profile_limit_reached: 409, profile_memory_insufficient: 409,
  profile_port_unavailable: 409, profile_product_unsupported: 409, profile_index_corrupt: 503, endpoint_global: 409,
  restore_review_required: 409 };
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
// HM-12 (DQ-40 ⑨ (a); contract 4.1): a backend save's code, only with its documented status.
const SAVE_CODES = { CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN: 422 };
// HM-27 (DQ-11 (a); contract 4.1): the Origin policy's code, only with its documented status.
const ORIGIN_CODES = { origin_policy_invalid: 422 };
// HM-27 (DQ-11 (a); contract 2.6, 3.1): the add-on's one Origin policy of the secret path. The modes, the bound on the
// list and the default (no policy saved yet) are the add-on's (origin_policy.py); the add-on decides, these only answer
// early and check what it sent.
export const ORIGIN_MODES = Object.freeze(['report-only', 'enforce']);
export const MAX_ORIGINS = 16;
export const DEFAULT_ORIGINS = Object.freeze(['https://claude.ai']);
const ORIGIN_ETAG = /^"o1-[0-9a-f]{64}"$/;
// The revision an ETag header names (the add-on's "p1-..." index or "o1-..." policy, the quotes taken off), or null when it
// names none: shown, but not saved from. A proxy in front of the Ingress that compresses the answer (Cloudflare does: the
// Odoo 0.5.1 acceptance saw it on the small Origin policy answer, F2) turns the add-on's strong ETag into a weak one,
// W/"o1-...", the same revision. The panel reads both forms and keeps only the revision: what it sends back is the strong
// If-Match of it, as before, because the add-on compares strong validators only (profile_admin._if_match) and that rule
// is not loosened. "W/" is exactly that prefix (RFC 9110: case-sensitive); anything else around the quoted revision, or
// another revision form, is not one.
function headerRevision(response, strong) {
  const etag = response.headers.get('ETag');
  if (typeof etag !== 'string') return null;
  const value = etag.startsWith('W/') ? etag.slice(2) : etag;
  return strong.test(value) ? value.slice(1, -1) : null;
}
// An origin as the panel sends it: http(s)://host[:port], nothing after it, no whitespace, userinfo or backslash. The
// add-on's own rule is stricter (valid host labels or IPv6, port 1-65535, ASCII only; its 422 origin_policy_invalid).
const ORIGIN_SHAPE = /^https?:\/\/[^\s/?#@\\]+$/i;
// Same origin once the case and the default port are left aside (the add-on normalizes so and refuses a repeated one).
const originKey = origin => origin.toLowerCase().replace(/^(https:\/\/[^/]+):443$/, '$1').replace(/^(http:\/\/[^/]+):80$/, '$1');
// The origins one per line as typed: trimmed, blank lines dropped; a list the panel can tell is wrong is refused before
// anything is sent (UiError). Nothing typed is shown back in the message.
export function originList(text) {
  const origins = String(text ?? '').split('\n').map(line => line.trim()).filter(Boolean);
  if (origins.length > MAX_ORIGINS) throw new UiError(`最多 ${MAX_ORIGINS} 個來源（目前 ${origins.length} 個）；未送出變更。`);
  const seen = new Set();
  origins.forEach((origin, index) => {
    if (origin.length > 300 || !ORIGIN_SHAPE.test(origin)) throw new UiError(`第 ${index + 1} 個來源不是精確的 http(s) 來源（例如 https://claude.ai）：不接受 *、null、路徑、尾端斜線、帳密、查詢參數或空白；未送出變更。`);
    if (seen.has(originKey(origin))) throw new UiError(`第 ${index + 1} 個來源和前面的重複（不分大小寫，預設 port 視為相同）；未送出變更。`);
    seen.add(originKey(origin));
  });
  return origins;
}
// The policy as the add-on shows it (origin_policy.OriginPolicy.view): {mode, origins, state}; an unusable file has
// neither mode nor list. Anything else is not shown.
function originView(value) {
  const keys = value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value).filter(key => key !== 'operation').sort().join() : '';
  if (keys !== 'allowed_origins,mode,origin_policy_state') throw new UiError('來源檢查設定的回應格式不符，未顯示。');
  if (value.origin_policy_state === 'unusable' && value.mode === null && value.allowed_origins === null) return { state: 'unusable', mode: null, origins: null };
  if (!['default', 'saved'].includes(value.origin_policy_state) || !ORIGIN_MODES.includes(value.mode) || !Array.isArray(value.allowed_origins)
      || value.allowed_origins.length > MAX_ORIGINS || !value.allowed_origins.every(origin => typeof origin === 'string' && origin.length <= 300 && ORIGIN_SHAPE.test(origin))) {
    throw new UiError('來源檢查設定的回應格式不符，未顯示。');
  }
  return { state: value.origin_policy_state, mode: value.mode, origins: [...value.allowed_origins] };
}
// Refused before the add-on records the intent (its If-Match, Idempotency-Key and rules come first): a corrected save
// takes a new identity.
const ORIGIN_REFUSALS = ['config_conflict', 'config_revision_required', 'operation_id_required', 'operation_id_invalid', 'origin_policy_invalid'];
// HM-12 (DQ-05; contract 3.1, section 9 #113): what the panel says when a save rotated the profile's MCP token (the
// add-on sends token_rotated: true and no text). app.js adds it to a save's notice; a shape D answer carries it.
export const TOKEN_ROTATED = '後端身分已變更，這個帳號的 MCP 權杖已換新：舊權杖與含舊權杖的連線網址已撤銷。請到「連線與權杖」顯示並複製新的權杖（或 Claude.ai 連線網址），更新所有用戶端。';
// HM-12 review S-7 (contract section 9 #114): a 503 state unavailable of such a save may hide a write whose outcome the
// add-on does not know: after its restart the token may be the new one, although this answer never said so.
const OUTCOME_UNKNOWN = '存檔結果不明時請重新啟動 add-on，之後到「連線與權杖」確認 MCP 網址：若這次換了後端身分，權杖可能已換新，舊網址會失效。';
// HM-13c review S-3: a backend save that would rotate the token of a profile whose restore review waits (HM-12's
// identity change) is refused as token/rotate is; after restore_review_required's own copy, why a save waits too.
// HM-22 review MF-1 (HM-24's shape): the identity fields named are the save's own product's (contracts.js identityChange;
// Odoo's copy unchanged).
const saveWaitsForReview = product => `改後端身分（${identityChange[product]}）會換新這個帳號的 MCP 權杖，所以也要先核對才能儲存；這次未儲存任何變更。`;
export class ApiError extends UiError {
  constructor(status, code = null, haVersion = null, detail = {}) {
    const messages = {
      400: '設定格式不符。伺服器未確認儲存，請檢查欄位。',
      401: '管理身分已失效。請從服務入口重新開啟。',
      403: '你沒有管理權限，或安全驗證已失效。請從原服務入口重新驗證；此頁無法繞過授權。',
      404: '此伺服器尚未提供所需管理 API。',
      409: '設定已變更或版本不相容。請重新整理後再試。',
      422: '欄位驗證未通過。請確認 URL、必要欄位與憑證格式。',
      428: '缺少設定版本或操作識別碼；未接受變更，請重新整理狀態。',
      410: '操作收據已超過保存期限；請核對目前狀態，勿假設先前操作未執行。',
      503: '管理狀態暫時無法使用。請檢查服務與受保護的設定儲存。',
    };
    super(messages[status] ?? '請求未獲成功確認。請重新整理狀態，勿假設變更已套用。');
    this.status = status;
    this.code = code;
    if (code === 'config_conflict') this.message = '設定已被其他操作更新。草稿已保留；請先重新整理狀態、檢查新設定，再重新編輯。未送出任何變更。';
    if (code === 'config_apply_failed') this.message = '設定已儲存，但子行程尚未套用成功。請重新整理套用狀態，檢查後再重試啟動。';
    if (code === 'operation_outcome_unknown') this.message = '操作結果未知；原識別碼已保留，伺服器不會再次執行相同操作。請查詢收據並核對目前狀態。';
    if (code === 'operation_id_conflict') this.message = '操作識別碼已用於不同操作；未再次執行，請查詢原收據。';
    if (code === 'operation_not_found') this.message = '目前找不到你可讀取的操作收據；不代表先前操作一定未執行。請核對狀態，或以原識別碼重送。';
    if (code === 'operation_journal_full') this.message = '操作收據已達保存上限；未接受新操作，請稍後再試。';
    if (code === 'operation_journal_unavailable') this.message = '操作收據儲存無法使用；請檢查服務儲存，勿改用新的識別碼重複操作。';
    if (code === 'owner_defaults_unavailable') this.message = '升級通知已處理過，或升級前的限制紀錄無法使用。請重新整理狀態；未變更任何設定。';
    // HM-12 (DQ-40 ⑨ (a)): fixed copy; the answer echoes nothing and nothing sent is shown.
    if (code === 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN') this.message = '網址改到另一台伺服器（scheme、主機或 port 不同）時，不會沿用已儲存的密碼或金鑰：請在同一次儲存中為新網址重新輸入（選填的可以明確清除）。這次未儲存任何變更。';
    // HM-13c: an operation id from before a restore (its receipt archived, or lost with the restore): never run again.
    if (code === 'operation_restored') this.message = '這個操作是在備份還原之前送出的；還原後不會再執行，也查不到它的結果。請核對目前狀態，需要時重新操作。';
    // HM-27: fixed copy; the answer echoes nothing and nothing sent is shown.
    if (code === 'origin_policy_invalid') this.message = '來源檢查設定不符合規則：模式只能是「只記錄」或「阻擋」；每個來源要是精確的 http(s) 來源（例如 https://claude.ai），主機名稱與 port 要有效，不接受 *、null、路徑、尾端斜線或點、帳密、查詢參數或空白，正規化後不能重複，最多 16 個。這次未儲存任何變更。';
    if (code === 'core_version_unreviewed') {
      this.haVersion = haVersion;
      this.message = `這個 HA Core 版本尚未審核：${haVersion ?? '（版本字串無法辨識）'}。這版 add-on 的管理面板只在審查過的 Core 版本，以及已審查月份、修補編號更大的後續修補版（自動放行）上運作，暫時不能使用或變更設定；MCP 端點不經過這項檢查，照常服務。請更新 add-on。`;
    }
    // HM-11: fixed copy for the profile codes; the only values taken from the answer are whole numbers.
    const numbers = detail ?? {};
    const limit = count(numbers.limit), need = count(numbers.required_memory_mib), free = count(numbers.available_memory_mib);
    const profileMessages = {
      profile_id_required: '管理服務要求指定帳號，但請求沒有帶到帳號；請重新整理。一再出現時，可能是 Home Assistant 沒有轉送帳號標頭，請回報。',
      profile_id_invalid: '帳號識別碼格式不符；請重新整理。',
      profile_not_found: '這個帳號已不存在（可能已在其他分頁或由其他管理員刪除）。',
      profile_label_invalid: '帳號名稱不符合規則：去掉前後空白後要 1–80 個字，不能含控制字元、零寬字元或雙向控制字元。',
      profile_default_immutable: '預設帳號不能改名或刪除。',
      profile_label_conflict: '已有同名的帳號（不分大小寫與全形半形），或用了保留名稱「default」「預設帳號」。請換一個名稱。',
      // HM-10: limit 0 is an add-on whose open file limit holds no additional profile (it serves the default one only).
      profile_limit_reached: limit === 0 ? '這個 add-on 目前只能服務預設帳號（可同時開啟的檔案數不足以再執行額外帳號），所以無法新增帳號；刪除帳號也不會改變這一點。請回報這個情況。'
        : `已達這個產品的帳號上限${limit === null ? '' : `（最多 ${limit} 個額外帳號）`}；請先刪除不用的帳號。`,
      profile_memory_insufficient: `可用記憶體不足，無法再新增帳號${need === null ? '' : `（需要約 ${need} MiB${free === null ? '' : `，目前可用 ${free} MiB`}）`}。`,
      profile_port_unavailable: '找不到可用的子行程 port，無法新增帳號。',
      profile_product_unsupported: '這個產品不支援額外帳號。',
      profile_index_corrupt: '帳號索引損壞，額外帳號暫停服務；預設帳號照常可用。',
      endpoint_global: '端點是整個 add-on 共用的設定，只能在預設帳號修改。',
      restore_review_required: '這個帳號是從備份還原（或休眠）回來的，還沒有核對：請先到預設帳號頁的核對卡確認它的設定，按「已核對」後才能重新產生權杖。',
    };
    if (Object.hasOwn(profileMessages, code)) this.message = profileMessages[code];
    // HM-13c: "revoke all" that did not finish says which profile got which result (contract 4.1); only these values.
    this.results = code === 'operation_outcome_unknown' ? revocationResults(numbers.results) : null;
  }
}
// HM-11: an answer that arrived after the panel moved to another profile (a newer epoch). It is dropped unseen.
export class StaleProfileError extends UiError {
  constructor() { super('帳號已切換；前一個帳號的回應已捨棄。'); }
}
// HM-11 (contract 3.4; I12): an answer whose echo does not name the profile the request named. Nothing of it is shown.
export class ProfileEchoError extends UiError {
  constructor() { super('伺服器回應的帳號與送出時的帳號不符，結果沒有顯示。已重新讀取管理狀態；請核對各帳號的設定後再操作。'); }
}
const PROFILE_HEADER = 'X-MCP-Profile';
const PRE_INTENT = ['config_conflict', 'config_revision_required', 'operation_id_required', 'operation_id_invalid'];
// Refused before the server records the intent (contract 3.2 step 11), so the next try may take a new identity.
const PROFILE_REFUSALS = [...PRE_INTENT, 'profile_label_invalid', 'profile_label_conflict', 'profile_limit_reached',
  'profile_memory_insufficient', 'profile_port_unavailable', 'profile_product_unsupported', 'profile_default_immutable',
  'profile_not_found', 'profile_index_corrupt'];
// The global writes (contract 3.1; HM-10): their path, method and body. Each keeps an identity under the profiles scope.
const PROFILE_WRITES = {
  'profiles/create': { method: 'POST', path: () => 'profiles', body: pending => ({ label: pending.label }) },
  'profiles/delete': { method: 'DELETE', path: pending => `profiles/${pending.profile}` },
  'profiles/quarantine': { method: 'POST', path: () => 'profiles/index/quarantine' },
  // HM-13c (contract 3.1): "revoke all", a restore review, a quarantine directory's deletion.
  'profiles/revoke-all': { method: 'POST', path: () => 'profiles/revoke-all' },
  'profiles/restore-review': { method: 'POST', path: pending => `profiles/${pending.profile}/restore-review` },
  'profiles/quarantine-delete': { method: 'POST', path: pending => `profiles/quarantine/${pending.name}/delete` },
};
const INDEX_QUARANTINE_NAME = /^profiles\.json\.quarantine-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?$/;

// HM-11 (plan 6; contract 3.3): with profiles, every profile-scoped request names its profile in X-MCP-Profile, the
// default profile too; the profile routes (/api/profiles...) never do. this.profile is null for a single-profile server
// (no header, every request exactly as before) and the selected profile otherwise. this.epoch grows at every change of
// profile: an answer to a request begun earlier is dropped (StaleProfileError), whatever it says.
export class AdminApi {
  constructor(mount, fetcher = globalThis.fetch.bind(globalThis), storage, { profile = DEFAULT_PROFILE } = {}) {
    this.mount = mountPath(mount);
    this.fetcher = fetcher;
    if (storage === undefined) { try { storage = globalThis.sessionStorage; } catch { storage = null; } }
    this.operations = new OperationIdentity(this.mount, storage);
    if (!isProfileId(profile)) throw new UiError('帳號識別碼格式不符。');
    this.initial = profile;
    this.profile = null;
    this.connected = false;
    this.epoch = 0;
  }
  async exchange(path, options = {}, { profile = this.profile, epoch = this.epoch, global = false, bootstrap = false } = {}) {
    if (epoch !== this.epoch) throw new StaleProfileError();
    const headers = profile === null ? options.headers : { ...options.headers, [PROFILE_HEADER]: profile };
    let response;
    try {
      response = await this.fetcher(path, { ...options, ...(headers === undefined ? {} : { headers }), credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(25000) });
    } catch {
      if (epoch !== this.epoch) throw new StaleProfileError();
      throw new UiError('連線中斷或逾時；無法確認操作結果。請重新整理狀態後再操作。');
    }
    if (epoch !== this.epoch) throw new StaleProfileError();
    if (!response.ok) {
      // Only these fixed codes affect copy. Never reflect server bodies or submitted secrets; the one exception is a
      // 403 core_version_unreviewed's Core version, shown only in the exact public release/pre-release form.
      let code, haVersion = null, detail = {}, body = null;
      try {
        body = await response.json();
        detail = body?.detail ?? {};
        code = detail?.code;
        if (code === 'core_version_unreviewed' && typeof detail.ha_version === 'string' && CORE_VERSION.test(detail.ha_version)) haVersion = detail.ha_version;
      } catch { /* non-JSON error */ }
      if (epoch !== this.epoch) throw new StaleProfileError();
      const known = ['config_conflict', 'config_revision_required', 'config_apply_failed', 'owner_defaults_unavailable',
        'operation_outcome_unknown', 'operation_id_conflict', 'operation_not_found', 'operation_id_required',
        'operation_id_invalid', 'operation_id_expired', 'operation_journal_full', 'operation_journal_unavailable'].includes(code)
        || (code === 'operation_restored' && response.status === 410) || (code === 'core_version_unreviewed' && response.status === 403)
        || (Object.hasOwn(PROFILE_CODES, code ?? '') && PROFILE_CODES[code] === response.status)
        || (Object.hasOwn(SAVE_CODES, code ?? '') && SAVE_CODES[code] === response.status)
        || (Object.hasOwn(ORIGIN_CODES, code ?? '') && ORIGIN_CODES[code] === response.status);
      const error = new ApiError(response.status, known ? code : null, haVersion, known && detail && typeof detail === 'object' ? detail : {});
      // HM-12 (contract 3.1, section 9 #113): saved, the token rotated, the new child not started (shape D with
      // token_rotated; only this shape counts, and only when it names the profile asked, I12): the copy also says where
      // the new token is (app.js reads the state again).
      if (response.status === 503 && error.code === 'config_apply_failed' && body?.saved === true && body?.token_rotated === true
          && echoMatches(body, profile)) {
        error.tokenRotated = true;
        error.message = `${error.message} ${TOKEN_ROTATED}`;
      }
      // HM-12 review S-7: the fixed 503 {"error":"state unavailable"} (a write the add-on could not make, or whose outcome
      // it does not know; mutate says what to check after a backend save).
      if (response.status === 503 && error.code === null && body?.error === 'state unavailable') error.stateUnavailable = true;
      throw error;
    }
    if (response.status === 204) {
      // HM-11 review S-4: with profiles a profile-scoped answer without a body cannot echo its profile (I12): not used.
      if (!global && profile !== null) throw new ProfileEchoError();
      return { response, value: null };
    }
    let value;
    try { value = await response.json(); } catch {
      if (epoch !== this.epoch) throw new StaleProfileError();
      throw new UiError('伺服器回應格式不符，無法確認操作結果。');
    }
    if (epoch !== this.epoch) throw new StaleProfileError();
    if (!global && !echoMatches(value, profile, bootstrap)) throw new ProfileEchoError();
    return { response, value };
  }
  async request(path, options = {}, scope = {}) { return (await this.exchange(path, options, scope)).value; }
  checkBootstrap(value) {
    if (!value || mountPath(value.base_path) !== this.mount || value.api_base !== `${this.mount}/api` || !Object.hasOwn(products, value.product)) throw new UiError('管理 API 路徑或產品版本不相容。');
    return value;
  }
  // HM-11: the first bootstrap of a page (and the re-read after an echo the panel cannot use) asks without a profile:
  // a single-profile server answers as before; a switched-on one refuses (400 profile_id_required, contract 3.3), and
  // from then on the panel names the profile explicitly, starting with the default one (a reload forgets the choice).
  async open() {
    this.profile = null;
    this.connected = false;
    const epoch = ++this.epoch;
    let value = null, profiles = false;
    try { value = await this.request(`${this.mount}/api/bootstrap`, {}, { profile: null, epoch, global: true }); }
    catch (error) {
      if (!(error instanceof ApiError) || error.code !== 'profile_id_required') throw error;
      profiles = true;
    }
    if (!profiles && !echoMatches(value, null)) profiles = true; // answered for a profile without being asked: ask again
    if (!profiles) {
      this.checkBootstrap(value);
      if (this.initial !== DEFAULT_PROFILE) throw new UiError('這個管理服務沒有開通多帳號，無法選擇其他帳號。');
      this.connected = true;
      return value;
    }
    this.profile = this.initial;
    this.epoch++;
    this.connected = true;
    return this.bootstrap();
  }
  // HM-11: choose another profile. Every answer still on its way for the previous one is dropped.
  select(profile) {
    if (!this.connected || this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    if (!isProfileId(profile)) throw new UiError('帳號識別碼格式不符。');
    this.epoch++;
    this.profile = profile;
  }
  async bootstrap(profile = this.profile, epoch = this.epoch) {
    if (!this.connected) return this.open();
    return this.checkBootstrap(await this.request(`${this.mount}/api/bootstrap`, {}, { profile, epoch, bootstrap: true }));
  }
  // HM-11 (plan 6; C1-S11): the profile is fixed when the change starts: the fresh bootstrap and the change carry the
  // same X-MCP-Profile and both answers must echo it. A caller passes the profile its page was drawn for; when that is
  // no longer the selected one, nothing is sent.
  async mutate(operation, payload, revision, profile) {
    const allowed = ['backend', 'backend/patch', 'n8n/session', 'odoo/allowed-methods', 'endpoint', 'policy', 'odoo/write-switches', 'token/reveal', 'token/rotate', 'token/revoke', 'backend/test', 'child/restart',
      'owner-defaults/restore', 'owner-defaults/dismiss'];
    if (!allowed.includes(operation)) throw new UiError('不支援的操作。');
    let fresh = this.connected ? null : await this.open();
    if (profile === undefined) profile = this.profile;
    if (profile !== this.profile) throw new StaleProfileError();
    const epoch = this.epoch;
    fresh ??= await this.bootstrap(profile, epoch);
    if (typeof fresh.csrf !== 'string' || !/^[A-Za-z0-9_-]{16,256}$/.test(fresh.csrf)) throw new UiError('缺少有效安全驗證；未送出變更。請重新開啟管理介面。');
    const token = operation.startsWith('token/');
    // 2026-10-27: the one-time all-on notice actions are POSTs without a body that always need the reviewed revision.
    const notice = operation.startsWith('owner-defaults/');
    const durable = Object.hasOwn(operationKinds, operation);
    if (!['token/reveal', 'backend/test'].includes(operation) && revision === undefined) throw new UiError('缺少設定版本；請重新整理後再試，未送出變更。');
    const action = token || notice || ['backend/test', 'child/restart'].includes(operation);
    if (revision !== undefined && (typeof revision !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(revision))) throw new UiError('設定版本格式不符；請重新整理後再試。');
    const pending = durable ? this.operations.start(operation, revision, fresh, profile) : null;
    if (pending) revision = pending.revision; // Never upgrade a retried operation's reviewed revision.
    let result;
    try { result = await this.request(`${fresh.api_base}/${operation}`, {
      method: action ? 'POST' : 'PUT',
      headers: { 'X-CSRF-Token': fresh.csrf, ...(action ? {} : { 'Content-Type': 'application/json' }),
        ...(revision === undefined ? {} : { 'If-Match': `"${revision}"` }),
        ...(pending ? { 'Idempotency-Key': pending.id } : {}) },
      ...(action ? {} : { body: JSON.stringify(typeof payload === 'function' ? payload(fresh) : payload) }),
    }, { profile, epoch }); } catch (error) {
      // Only explicit refusals before accepting an intent can release identity (HM-13c: a token/rotate that waits for
      // its restore review is refused before anything is written, as these are).
      if (pending && error instanceof ApiError && [...PRE_INTENT, 'restore_review_required'].includes(error.code)) this.operations.clear(profile);
      // HM-12 review S-7: a backend save of a switched-on product whose token is bound to its backend identity.
      if (error instanceof ApiError && error.stateUnavailable && profile !== null && ['backend', 'backend/patch'].includes(operation)
          && identityBound.includes(fresh.product)) error.message = `${error.message} ${OUTCOME_UNKNOWN}`;
      // HM-13c review S-3: the same backend save held for the profile's restore review (409; nothing was saved).
      if (error instanceof ApiError && error.code === 'restore_review_required' && profile !== null
          && ['backend', 'backend/patch'].includes(operation) && identityBound.includes(fresh.product)) {
        error.message = `${error.message} ${saveWaitsForReview(fresh.product)}`;
      }
      throw error;
    }
    if (pending) {
      const receipt = operationReceipt(result?.operation, pending);
      if (receipt.state !== 'completed' || result?.status !== 'ok') throw new UiError('操作結果尚未確認；原識別碼已保留，請查詢收據。');
      this.operations.clear(profile);
    }
    if (((!action || notice) && result?.saved !== true)
        || (operation === 'backend/test' && result?.tested_configuration !== 'saved')) throw new UiError('伺服器未回傳預期確認，無法確認操作結果。請重新整理狀態。');
    return result;
  }
  async capabilities() { return this.request(`${this.mount}/api/capabilities`); }
  async diagnostics() { return this.request(`${this.mount}/api/diagnostics`); }
  async configuration() { return this.request(`${this.mount}/api/configuration`); }
  pendingOperation(profile = this.profile) { return this.operations.get(profile); }
  async queryOperation() {
    const pending = this.pendingOperation();
    if (!pending) throw new UiError('目前沒有待確認的操作。');
    const profile = this.profile;
    const result = await this.request(`${this.mount}/api/operations/${pending.id}`);
    const receipt = operationReceipt(result?.operation, pending);
    if (receipt.state === 'completed') this.operations.clear(profile);
    return receipt;
  }
  async retryOperation() {
    const pending = this.pendingOperation();
    if (!pending) throw new UiError('目前沒有待確認的操作。');
    return this.mutate(pending.route, undefined, pending.revision);
  }
  acknowledgeOperation(profile = this.profile) { this.operations.clear(profile); }

  // HM-11 (contract 3.1, 3.6): the profile list, its orphans and its index revision (the ETag header). A profile route
  // never carries X-MCP-Profile and has no echo. A list without a well-formed ETag is still shown, but nothing can be
  // changed with it (revision null; review S-2: HM-03a measures whether the Ingress keeps the header).
  async profileList() {
    const { response, value } = await this.exchange(`${this.mount}/api/profiles`, {}, { profile: null, global: true });
    const rows = profileRows(value);
    const orphans = orphanIds(value, rows);
    const quarantined = quarantinedEntries(value);  // HM-13c: the quarantine directories, delete only
    return { rows, orphans, quarantined, revision: headerRevision(response, INDEX_ETAG) };
  }
  // HM-13c (contract 3.1, 3.6): the guard's restore record, checked (restore.js recordView: anything else refused).
  async restoreRecord() {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    return recordView(await this.request(`${this.mount}/api/profiles/restore-record`, {}, { profile: null, global: true }));
  }
  // A fresh bootstrap (its echo checked) for the CSRF value and the operation clock. It is the default profile's: the
  // profile routes are the add-on's, the CSRF value is shared, and a profile whose state cannot be read must stay
  // deletable (contract 3.3).
  async profileFresh(epoch) {
    const fresh = await this.bootstrap(DEFAULT_PROFILE, epoch);
    if (typeof fresh.csrf !== 'string' || !/^[A-Za-z0-9_-]{16,256}$/.test(fresh.csrf)) throw new UiError('缺少有效安全驗證；未送出變更。請重新開啟管理介面。');
    return fresh;
  }
  // Create (POST {label}) or delete (DELETE) a profile, or quarantine an unusable index (POST, no body): If-Match of the
  // index the administrator saw (the quarantine: the unusable index file's own ETag), an Idempotency-Key kept for this
  // tab under the profiles scope, CSRF. The answer is the new row, {deleted, operation} or {quarantined, operation};
  // never a token (other products can reveal it; Headscale requires rotation, scoped to its profile). A
  // created profile deleted since its creation is replayed as its id alone (HM-10): gone, nothing to switch to.
  async changeProfiles(route, revision, detail = {}) {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    if (route === 'profiles/create' && detail.label !== undefined) {
      const problem = labelProblem(detail.label);
      if (problem) throw new UiError(problem);
      detail = { label: detail.label.trim() };
    }
    if (route === 'profiles/delete' && detail.profile !== undefined && !isExtraProfile(detail.profile)) throw new UiError('預設帳號不能刪除。');
    if (route === 'profiles/restore-review' && detail.profile !== undefined && !isProfileId(detail.profile)) throw new UiError('帳號識別碼格式不符。');
    if (route === 'profiles/quarantine-delete' && detail.name !== undefined && !QUARANTINE_NAME.test(detail.name)) throw new UiError('隔離的帳號資料名稱格式不符。');
    if (typeof revision !== 'string' || !INDEX_REVISION.test(revision)) throw new UiError('帳號清單版本格式不符；請重新整理後再試，未送出變更。');
    const epoch = this.epoch;
    const fresh = await this.profileFresh(epoch);
    const pending = this.operations.start(route, revision, fresh, PROFILES_SCOPE, detail);
    const write = PROFILE_WRITES[route];
    if (!write) throw new UiError('不支援的帳號操作。');
    const body = write.body?.(pending);
    let result;
    try {
      result = await this.request(`${fresh.api_base}/${write.path(pending)}`, {
        method: write.method,
        headers: { 'X-CSRF-Token': fresh.csrf, ...(body ? { 'Content-Type': 'application/json' } : {}),
          'If-Match': `"${pending.revision}"`, 'Idempotency-Key': pending.id },
        ...(body ? { body: JSON.stringify(body) } : {}),
      }, { profile: null, epoch, global: true });
    } catch (error) {
      if (error instanceof ApiError && PROFILE_REFUSALS.includes(error.code)) this.operations.clear(PROFILES_SCOPE);
      throw error;
    }
    const receipt = operationReceipt(result?.operation, pending);
    if (receipt.state !== 'completed') throw new UiError('帳號操作結果尚未確認；原識別碼已保留，請重送或核對帳號清單。');
    const keys = result && typeof result === 'object' ? Object.keys(result).sort().join() : '';
    const gone = route === 'profiles/create' && receipt.replayed && keys === 'id,operation' && isExtraProfile(result.id);
    // The created row as the list rules read it: a label this browser cannot show is not passed on (review S-2).
    const created = route === 'profiles/create' && !gone && isExtraProfile(result?.id)
      ? profileRows({ profiles: [{ ...result, operation: undefined }, defaultRow] })[0] : null;
    const confirmed = route === 'profiles/create' ? gone || created !== null
      : route === 'profiles/delete' ? result?.deleted === pending.profile
        : route === 'profiles/revoke-all' ? result?.revoked === 'all'
          : route === 'profiles/restore-review' ? result?.reviewed === pending.profile
            : route === 'profiles/quarantine-delete' ? result?.deleted === pending.name
              : typeof result?.quarantined === 'string' && INDEX_QUARANTINE_NAME.test(result.quarantined);
    if (!confirmed) throw new UiError('伺服器未回傳預期的帳號確認；請重新整理帳號清單。');
    this.operations.clear(PROFILES_SCOPE);
    if (route === 'profiles/create') return gone ? { id: result.id, label: null, replayed: true, gone: true } : { id: result.id, label: created.label, replayed: receipt.replayed };
    if (route === 'profiles/revoke-all') return { revoked: 'all', results: revocationResults(result.results), replayed: receipt.replayed };
    if (route === 'profiles/restore-review') return { reviewed: result.reviewed, replayed: receipt.replayed };
    if (route === 'profiles/quarantine-delete') return { deleted: result.deleted, replayed: receipt.replayed };
    return route === 'profiles/delete' ? { deleted: result.deleted, replayed: receipt.replayed } : { quarantined: result.quarantined, replayed: receipt.replayed };
  }
  createProfile(label, revision) { return this.changeProfiles('profiles/create', revision, { label }); }
  deleteProfile(profile, revision) { return this.changeProfiles('profiles/delete', revision, { profile }); }
  // HM-13c (contract 3.1): "revoke all" (If-Match: the list's revision, or the unusable index's own ETag), a restore
  // review of one profile, a quarantine directory's deletion. Each keeps its identity under the profiles scope.
  revokeAll(revision) { return this.changeProfiles('profiles/revoke-all', revision); }
  reviewProfile(profile, revision) { return this.changeProfiles('profiles/restore-review', revision, { profile }); }
  deleteQuarantined(name, revision) { return this.changeProfiles('profiles/quarantine-delete', revision, { name }); }
  // DQ-12 (contract 3.6): quarantine the unusable index; etag is the default bootstrap's profile_index_etag, as given.
  quarantineIndex(etag) {
    if (typeof etag !== 'string' || !INDEX_ETAG.test(etag)) throw new UiError('帳號索引的版本格式不符；請重新整理後再試，未送出變更。');
    return this.changeProfiles('profiles/quarantine', etag.slice(1, -1));
  }
  // Rename (PATCH {label}): If-Match of the index; no identity (contract 3.5).
  async renameProfile(profile, label, revision) {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    if (!isExtraProfile(profile)) throw new UiError('預設帳號不能改名。');
    const problem = labelProblem(label);
    if (problem) throw new UiError(problem);
    if (typeof revision !== 'string' || !INDEX_REVISION.test(revision)) throw new UiError('帳號清單版本格式不符；請重新整理後再試，未送出變更。');
    const epoch = this.epoch;
    const fresh = await this.profileFresh(epoch);
    const result = await this.request(`${fresh.api_base}/profiles/${profile}`, {
      method: 'PATCH', headers: { 'X-CSRF-Token': fresh.csrf, 'Content-Type': 'application/json', 'If-Match': `"${revision}"` },
      body: JSON.stringify({ label: label.trim() }),
    }, { profile: null, epoch, global: true });
    if (result?.id !== profile || result?.label !== label.trim()) throw new UiError('伺服器未回傳預期的帳號確認；請重新整理帳號清單。');
    return result;
  }
  pendingProfileOperation() { return this.profile === null ? null : this.operations.get(PROFILES_SCOPE); }
  async retryProfileOperation() {
    const pending = this.pendingProfileOperation();
    if (!pending) throw new UiError('目前沒有待確認的帳號操作。');
    return this.changeProfiles(pending.route, pending.revision);
  }
  acknowledgeProfileOperation() { this.operations.clear(PROFILES_SCOPE); }

  // HM-27 (DQ-11 (a); contract 2.6, 3.1, 3.5): the add-on's one Origin policy of the secret path, a global path (no
  // X-MCP-Profile, no echo), only with profiles (switched off the add-on has none). originPolicy() is it as shown, with
  // its revision (the ETag header; null when missing or malformed: shown, but not saved from).
  async originPolicy() {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    const { response, value } = await this.exchange(`${this.mount}/api/origin-policy`, {}, { profile: null, global: true });
    return { ...originView(value), revision: headerRevision(response, ORIGIN_ETAG) };
  }
  // Save the policy: PUT {mode, allowed_origins} with If-Match of the policy the administrator saw (an unusable file's
  // own revision replaces it), an Idempotency-Key kept for this tab under the policy's scope (its record holds the
  // request, so a resend is the same request) and the CSRF value of a fresh default bootstrap. The answer is the saved
  // policy and its receipt; never a token.
  async saveOriginPolicy(mode, origins, revision) {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    if (!ORIGIN_MODES.includes(mode)) throw new UiError('來源檢查的模式不符；未送出變更。');
    if (!Array.isArray(origins) || originList(origins.join('\n')).length !== origins.length) throw new UiError('來源清單格式不符；未送出變更。');
    if (typeof revision !== 'string' || !ORIGIN_REVISION.test(revision)) throw new UiError('來源檢查設定的版本格式不符；請重新整理後再試，未送出變更。');
    const epoch = this.epoch;
    const fresh = await this.profileFresh(epoch);
    const pending = this.operations.start('origin-policy', revision, fresh, ORIGIN_SCOPE, { mode, allowed_origins: origins });
    let response, result;
    try {
      ({ response, value: result } = await this.exchange(`${fresh.api_base}/origin-policy`, {
        method: 'PUT',
        headers: { 'X-CSRF-Token': fresh.csrf, 'Content-Type': 'application/json', 'If-Match': `"${pending.revision}"`, 'Idempotency-Key': pending.id },
        body: JSON.stringify({ mode: pending.mode, allowed_origins: pending.allowed_origins }),
      }, { profile: null, epoch, global: true }));
    } catch (error) {
      if (error instanceof ApiError && ORIGIN_REFUSALS.includes(error.code)) this.operations.clear(ORIGIN_SCOPE);
      throw error;
    }
    const receipt = operationReceipt(result?.operation, pending);
    if (receipt.state !== 'completed') throw new UiError('來源檢查設定的結果尚未確認；原識別碼已保留，請重送或核對設定。');
    const policy = originView(result);
    if (policy.state !== 'saved') throw new UiError('伺服器未回傳預期的來源設定確認；請重新整理狀態。');
    this.operations.clear(ORIGIN_SCOPE);
    return { ...policy, revision: headerRevision(response, ORIGIN_ETAG), replayed: receipt.replayed };
  }
  pendingOriginOperation() { return this.profile === null ? null : this.operations.get(ORIGIN_SCOPE); }
  async retryOriginOperation() {
    const pending = this.pendingOriginOperation();
    if (!pending) throw new UiError('目前沒有待確認的來源設定。');
    return this.saveOriginPolicy(pending.mode, pending.allowed_origins, pending.revision);
  }
  acknowledgeOriginOperation() { this.operations.clear(ORIGIN_SCOPE); }
}
// A row only to check a created profile's row with the list rules (the list always has the default profile).
const defaultRow = { id: DEFAULT_PROFILE, label: 'Default', port: 3000, is_default: true, disabled_reason: null, status: 'running', blocked_reason: null };
