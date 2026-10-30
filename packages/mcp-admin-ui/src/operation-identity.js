import { UiError } from './contracts.js';

export const operationKinds = Object.freeze({ 'token/rotate': 'token.rotate', 'token/revoke': 'token.revoke', 'child/restart': 'mcp.restart' });
const ID = /^[0-9]{13}\.[A-Za-z0-9_-]{16,64}$/;
const REVISION = /^c1-[0-9a-f]{64}$/;

export function operationReceipt(value, pending) {
  if (!value || value.id !== pending.id || value.kind !== operationKinds[pending.route]
      || !['completed', 'unknown'].includes(value.state) || typeof value.replayed !== 'boolean') {
    throw new UiError('操作收據格式不符；已保留原識別碼，請查詢結果，勿重複建立操作。');
  }
  return value;
}

export class OperationIdentity {
  constructor(mount, storage) {
    this.key = `woow-admin-operation-v1:${mount}`;
    this.storage = storage;
  }
  get() {
    let raw;
    try { raw = this.storage?.getItem(this.key); }
    catch { throw new UiError('無法讀取此分頁的操作識別碼；請檢查瀏覽器儲存權限。'); }
    if (!raw) return null;
    try {
      const value = JSON.parse(raw);
      if (Object.keys(value).sort().join(',') !== 'id,product,revision,route' || !ID.test(value.id)
          || !Object.hasOwn(operationKinds, value.route) || !REVISION.test(value.revision)
          || typeof value.product !== 'string' || !/^[a-z0-9-]{1,32}$/.test(value.product)) throw new Error();
      return value;
    } catch { throw new UiError('此分頁的操作識別紀錄不相容；請先核對伺服器狀態，不會自動重送。'); }
  }
  start(route, revision, fresh) {
    const pending = this.get();
    if (pending) {
      if (pending.route !== route || pending.product !== fresh.product) throw new UiError('另一筆操作尚未核對結果；請先使用「待確認操作」查詢。');
      return pending;
    }
    if (!this.storage || fresh.operation_contract?.version !== 1
        || !Number.isSafeInteger(fresh.operation_contract.server_time_ms)
        || !/^[0-9]{13}$/.test(String(fresh.operation_contract.server_time_ms)) || !REVISION.test(revision)) {
      throw new UiError('缺少安全的操作識別或分頁儲存；未送出變更。請更新服務或檢查瀏覽器設定。');
    }
    const random = new Uint8Array(16);
    globalThis.crypto.getRandomValues(random);
    const id = `${fresh.operation_contract.server_time_ms}.${Array.from(random, n => n.toString(16).padStart(2, '0')).join('')}`;
    const record = { id, route, revision, product: fresh.product };
    try {
      this.storage.setItem(this.key, JSON.stringify(record));
      if (this.storage.getItem(this.key) !== JSON.stringify(record)) throw new Error();
    } catch { throw new UiError('無法保留操作識別碼；未送出變更。請檢查瀏覽器儲存權限。'); }
    return record;
  }
  clear() {
    try { this.storage?.removeItem(this.key); }
    catch { throw new UiError('操作已核對，但分頁紀錄無法清除；再次查詢仍使用相同識別碼。'); }
  }
}
