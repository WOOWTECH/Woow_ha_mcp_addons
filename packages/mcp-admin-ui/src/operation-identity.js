import { UiError } from './contracts.js';
import { DEFAULT_PROFILE, INDEX_REVISION, isExtraProfile, labelProblem } from './profiles.js';

export const operationKinds = Object.freeze({ 'token/rotate': 'token.rotate', 'token/revoke': 'token.revoke', 'child/restart': 'mcp.restart' });
// HM-11 (contract 3.5): creating and deleting a profile and quarantining an unusable index keep their identity too;
// their receipts are the add-on's, beside the profile index (HM-10's kinds, operations.PROFILE_RESULTS).
export const profileOperationKinds = Object.freeze({ 'profiles/create': 'profile.create', 'profiles/delete': 'profile.delete',
  'profiles/quarantine': 'profile.index_quarantine' });
// The scope of the profile create/delete identity (never a profile id: those are default or 24 hex).
export const PROFILES_SCOPE = 'profiles';
// HM-27 (contract 3.5): saving the add-on's Origin policy of the secret path keeps its identity too; its receipts are the
// add-on's, beside the policy (origin_policy.KIND). Its scope, and the policy's revision (its ETag without the quotes).
export const originOperationKinds = Object.freeze({ 'origin-policy': 'origin.policy' });
export const ORIGIN_SCOPE = 'origin-policy';
export const ORIGIN_REVISION = /^o1-[0-9a-f]{64}$/;
const ORIGIN_MODES = ['report-only', 'enforce'];
const originRequest = value => ORIGIN_MODES.includes(value?.mode) && Array.isArray(value?.allowed_origins) && value.allowed_origins.length <= 16
  && value.allowed_origins.every(origin => typeof origin === 'string' && origin.length >= 1 && origin.length <= 300);
const ID = /^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/;
const REVISION = /^c1-[0-9a-f]{64}$/;

export function operationReceipt(value, pending) {
  const kind = operationKinds[pending.route] ?? profileOperationKinds[pending.route] ?? originOperationKinds[pending.route];
  if (!value || value.id !== pending.id || value.kind !== kind
      || !['completed', 'unknown'].includes(value.state) || typeof value.replayed !== 'boolean') {
    throw new UiError('操作收據格式不符；已保留原識別碼，請查詢結果，勿重複建立操作。');
  }
  return value;
}

// One record per key; the key says which format it holds (plan 6, C4-MF-3):
// - the default profile (and a server without profiles): woow-admin-operation-v1:<mount>, exactly {id, route, revision,
//   product}, as before profiles existed, so a tab open across the upgrade can still query its receipt;
// - an additional profile: woow-admin-operation-v1:<mount>:<id>, the same four keys and its profile;
// - creating or deleting a profile, or quarantining the index: woow-admin-operation-v1:<mount>:profiles, with the label
//   to create or the profile to delete (the quarantine: the unusable index's ETag as its revision), so a resend is the
//   same request;
// - HM-27, saving the Origin policy: woow-admin-operation-v1:<mount>:origin-policy, with the mode and the origins sent
//   (neither is a secret), so a resend is the same request.
export class OperationIdentity {
  constructor(mount, storage) {
    this.key = `woow-admin-operation-v1:${mount}`;
    this.storage = storage;
  }
  keyFor(scope = null) {
    if (scope === null || scope === DEFAULT_PROFILE) return this.key;
    if (scope !== PROFILES_SCOPE && scope !== ORIGIN_SCOPE && !isExtraProfile(scope)) throw new UiError('操作識別範圍不符；未送出變更。');
    return `${this.key}:${scope}`;
  }
  get(scope = null) {
    const key = this.keyFor(scope);
    let raw;
    try { raw = this.storage?.getItem(key); }
    catch { throw new UiError('無法讀取此分頁的操作識別碼；請檢查瀏覽器儲存權限。'); }
    if (!raw) return null;
    try {
      const value = JSON.parse(raw);
      const keys = Object.keys(value).sort().join(',');
      if (!ID.test(value.id) || typeof value.product !== 'string' || !/^[a-z0-9-]{1,32}$/.test(value.product)) throw new Error();
      if (key === this.key) {
        if (keys !== 'id,product,revision,route' || !Object.hasOwn(operationKinds, value.route) || !REVISION.test(value.revision)) throw new Error();
      } else if (scope === ORIGIN_SCOPE) {
        if (keys !== 'allowed_origins,id,mode,product,revision,route' || !Object.hasOwn(originOperationKinds, value.route)
            || !ORIGIN_REVISION.test(value.revision) || !originRequest(value)) throw new Error();
      } else if (scope !== PROFILES_SCOPE) {
        if (keys !== 'id,product,profile,revision,route' || value.profile !== scope || !Object.hasOwn(operationKinds, value.route)
            || !REVISION.test(value.revision)) throw new Error();
      } else if (!INDEX_REVISION.test(value.revision) || !(value.route === 'profiles/create'
          ? keys === 'id,label,product,revision,route' && labelProblem(value.label) === null && value.label === value.label.trim()
          : value.route === 'profiles/delete' ? keys === 'id,product,profile,revision,route' && isExtraProfile(value.profile)
            : value.route === 'profiles/quarantine' && keys === 'id,product,revision,route')) throw new Error();
      return value;
    } catch { throw new UiError('此分頁的操作識別紀錄不相容；請先核對伺服器狀態，不會自動重送。'); }
  }
  // detail: {label} to create, {profile} to delete (the profiles scope only; the quarantine has none); HM-27, the Origin
  // policy's scope: {mode, allowed_origins}, the request itself.
  start(route, revision, fresh, scope = null, detail = {}) {
    const crud = scope === PROFILES_SCOPE, origin = scope === ORIGIN_SCOPE;
    const pending = this.get(scope);
    if (pending) {
      const same = pending.route === route && pending.product === fresh.product
        && (!crud || detail.label === undefined && detail.profile === undefined
          || (route === 'profiles/create' ? pending.label === detail.label : pending.profile === detail.profile))
        && (route !== 'profiles/quarantine' || pending.revision === revision)
        && (!origin || pending.mode === detail.mode && JSON.stringify(pending.allowed_origins) === JSON.stringify(detail.allowed_origins));
      if (!same) throw new UiError(crud ? '另一筆帳號操作尚未核對結果；請先使用「帳號操作尚未確認」查詢。'
        : origin ? '另一筆來源檢查設定尚未確認結果；請先使用「來源檢查設定尚未確認」重送或核對。' : '另一筆操作尚未核對結果；請先使用「待確認操作」查詢。');
      return pending;
    }
    if (!this.storage || fresh.operation_contract?.version !== 1
        || !Number.isSafeInteger(fresh.operation_contract.server_time_ms)
        || !/^[0-9]{13}$/.test(String(fresh.operation_contract.server_time_ms)) || !(crud ? INDEX_REVISION : origin ? ORIGIN_REVISION : REVISION).test(revision)
        || (crud ? !Object.hasOwn(profileOperationKinds, route) : origin ? !Object.hasOwn(originOperationKinds, route) : !Object.hasOwn(operationKinds, route))
        || (origin && !originRequest(detail))) {
      throw new UiError('缺少安全的操作識別或分頁儲存；未送出變更。請更新服務或檢查瀏覽器設定。');
    }
    const random = new Uint8Array(16);
    globalThis.crypto.getRandomValues(random);
    const id = `${fresh.operation_contract.server_time_ms}.${Array.from(random, n => n.toString(16).padStart(2, '0')).join('')}`;
    let record;
    if (origin) record = { id, route, revision, product: fresh.product, mode: detail.mode, allowed_origins: [...detail.allowed_origins] };
    else if (!crud && this.keyFor(scope) === this.key) record = { id, route, revision, product: fresh.product };
    else if (!crud) record = { id, route, revision, product: fresh.product, profile: scope };
    else if (route === 'profiles/create') record = { id, route, revision, product: fresh.product, label: detail.label };
    else if (route === 'profiles/delete') record = { id, route, revision, product: fresh.product, profile: detail.profile };
    else record = { id, route, revision, product: fresh.product };
    if (crud && (route === 'profiles/create' ? labelProblem(record.label) !== null || record.label !== record.label.trim()
        : route === 'profiles/delete' && !isExtraProfile(record.profile))) throw new UiError('帳號操作內容不符；未送出變更。');
    try {
      this.storage.setItem(this.keyFor(scope), JSON.stringify(record));
      if (this.storage.getItem(this.keyFor(scope)) !== JSON.stringify(record)) throw new Error();
    } catch { throw new UiError('無法保留操作識別碼；未送出變更。請檢查瀏覽器儲存權限。'); }
    return record;
  }
  clear(scope = null) {
    try { this.storage?.removeItem(this.keyFor(scope)); }
    catch { throw new UiError('操作已核對，但分頁紀錄無法清除；再次查詢仍使用相同識別碼。'); }
  }
}
