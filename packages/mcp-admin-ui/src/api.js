import { mountPath, products, UiError } from './contracts.js';
import { OperationIdentity, operationKinds, operationReceipt, PROFILES_SCOPE } from './operation-identity.js';
import { DEFAULT_PROFILE, INDEX_REVISION, echoMatches, isExtraProfile, isProfileId, labelProblem, profileRows } from './profiles.js';

// A Core release or pre-release string (the server sends only this form, ha_role.shown_version); anything else is not shown.
const CORE_VERSION = /^[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,3}(?:(?:a|b|rc)[0-9]{1,3}|\.dev[0-9]{1,14})?$/;
// HM-11 (contract 4.1): the profile codes the panel knows, each only with its documented status.
const PROFILE_CODES = { profile_id_required: 400, profile_id_invalid: 400, profile_not_found: 404, profile_label_invalid: 422,
  profile_default_immutable: 422, profile_label_conflict: 409, profile_limit_reached: 409, profile_memory_insufficient: 409,
  profile_port_unavailable: 409, profile_product_unsupported: 409, profile_index_corrupt: 503, endpoint_global: 409 };
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
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
    if (code === 'core_version_unreviewed') {
      this.haVersion = haVersion;
      this.message = `這個 HA Core 版本尚未審核：${haVersion ?? '（版本字串無法辨識）'}。這版 add-on 的管理面板只在審查過的 Core 版本上運作，暫時不能使用或變更設定；MCP 端點不經過這項檢查，照常服務。請更新 add-on。`;
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
      profile_limit_reached: `已達這個產品的帳號上限${limit === null ? '' : `（最多 ${limit} 個額外帳號）`}；請先刪除不用的帳號。`,
      profile_memory_insufficient: `可用記憶體不足，無法再新增帳號${need === null ? '' : `（需要約 ${need} MiB${free === null ? '' : `，目前可用 ${free} MiB`}）`}。`,
      profile_port_unavailable: '找不到可用的子行程 port，無法新增帳號。',
      profile_product_unsupported: '這個產品不支援額外帳號。',
      profile_index_corrupt: '帳號索引損壞，額外帳號暫停服務；預設帳號照常可用。',
      endpoint_global: '端點是整個 add-on 共用的設定，只能在預設帳號修改。',
    };
    if (Object.hasOwn(profileMessages, code)) this.message = profileMessages[code];
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
  'profile_not_found'];

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
      let code, haVersion = null, detail = {};
      try {
        detail = (await response.json())?.detail ?? {};
        code = detail?.code;
        if (code === 'core_version_unreviewed' && typeof detail.ha_version === 'string' && CORE_VERSION.test(detail.ha_version)) haVersion = detail.ha_version;
      } catch { /* non-JSON error */ }
      if (epoch !== this.epoch) throw new StaleProfileError();
      const known = ['config_conflict', 'config_revision_required', 'config_apply_failed', 'owner_defaults_unavailable',
        'operation_outcome_unknown', 'operation_id_conflict', 'operation_not_found', 'operation_id_required',
        'operation_id_invalid', 'operation_id_expired', 'operation_journal_full', 'operation_journal_unavailable'].includes(code) || (code === 'core_version_unreviewed' && response.status === 403)
        || (Object.hasOwn(PROFILE_CODES, code ?? '') && PROFILE_CODES[code] === response.status);
      throw new ApiError(response.status, known ? code : null, haVersion, known && detail && typeof detail === 'object' ? detail : {});
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
      // Only explicit refusals before accepting an intent can release identity.
      if (pending && error instanceof ApiError && PRE_INTENT.includes(error.code)) this.operations.clear(profile);
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

  // HM-11 (contract 3.1, 3.6): the profile list and its index revision (the ETag header). A profile route never carries
  // X-MCP-Profile and has no echo.
  async profileList() {
    const { response, value } = await this.exchange(`${this.mount}/api/profiles`, {}, { profile: null, global: true });
    const etag = response.headers.get('ETag');
    if (typeof etag !== 'string' || !/^"p1-[0-9a-f]{64}"$/.test(etag)) throw new UiError('帳號清單的版本格式不符，無法顯示；請重新整理。');
    return { rows: profileRows(value), revision: etag.slice(1, -1) };
  }
  // A fresh bootstrap (its echo checked) for the CSRF value and the operation clock. It is the default profile's: the
  // profile routes are the add-on's, the CSRF value is shared, and a profile whose state cannot be read must stay
  // deletable (contract 3.3).
  async profileFresh(epoch) {
    const fresh = await this.bootstrap(DEFAULT_PROFILE, epoch);
    if (typeof fresh.csrf !== 'string' || !/^[A-Za-z0-9_-]{16,256}$/.test(fresh.csrf)) throw new UiError('缺少有效安全驗證；未送出變更。請重新開啟管理介面。');
    return fresh;
  }
  // Create (POST {label}) or delete (DELETE) a profile: If-Match of the index the administrator saw, an Idempotency-Key
  // kept for this tab under the profiles scope, CSRF. The answer is the new row, or {deleted, operation}; never a token
  // (a new profile's token is only ever shown by token/reveal, with its own X-MCP-Profile and echo).
  async changeProfiles(route, revision, detail = {}) {
    if (this.profile === null) throw new UiError('這個管理服務沒有開通多帳號。');
    if (route === 'profiles/create' && detail.label !== undefined) {
      const problem = labelProblem(detail.label);
      if (problem) throw new UiError(problem);
      detail = { label: detail.label.trim() };
    }
    if (route === 'profiles/delete' && detail.profile !== undefined && !isExtraProfile(detail.profile)) throw new UiError('預設帳號不能刪除。');
    if (typeof revision !== 'string' || !INDEX_REVISION.test(revision)) throw new UiError('帳號清單版本格式不符；請重新整理後再試，未送出變更。');
    const epoch = this.epoch;
    const fresh = await this.profileFresh(epoch);
    const pending = this.operations.start(route, revision, fresh, PROFILES_SCOPE, detail);
    const create = route === 'profiles/create';
    let result;
    try {
      result = await this.request(create ? `${fresh.api_base}/profiles` : `${fresh.api_base}/profiles/${pending.profile}`, {
        method: create ? 'POST' : 'DELETE',
        headers: { 'X-CSRF-Token': fresh.csrf, ...(create ? { 'Content-Type': 'application/json' } : {}),
          'If-Match': `"${pending.revision}"`, 'Idempotency-Key': pending.id },
        ...(create ? { body: JSON.stringify({ label: pending.label }) } : {}),
      }, { profile: null, epoch, global: true });
    } catch (error) {
      if (error instanceof ApiError && PROFILE_REFUSALS.includes(error.code)) this.operations.clear(PROFILES_SCOPE);
      throw error;
    }
    const receipt = operationReceipt(result?.operation, pending);
    if (receipt.state !== 'completed') throw new UiError('帳號操作結果尚未確認；原識別碼已保留，請重送或核對帳號清單。');
    if (create ? !isExtraProfile(result?.id) || profileRows({ profiles: [{ ...result, operation: undefined }, defaultRow] }).length !== 2
      : result?.deleted !== pending.profile) throw new UiError('伺服器未回傳預期的帳號確認；請重新整理帳號清單。');
    this.operations.clear(PROFILES_SCOPE);
    return create ? { id: result.id, label: result.label, replayed: receipt.replayed } : { deleted: result.deleted, replayed: receipt.replayed };
  }
  createProfile(label, revision) { return this.changeProfiles('profiles/create', revision, { label }); }
  deleteProfile(profile, revision) { return this.changeProfiles('profiles/delete', revision, { profile }); }
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
}
// A row only to check a created profile's row with the list rules (the list always has the default profile).
const defaultRow = { id: DEFAULT_PROFILE, label: 'Default', port: 3000, is_default: true, disabled_reason: null, status: 'running', blocked_reason: null };
