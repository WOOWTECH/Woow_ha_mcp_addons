// HM-13c (plan 6 還原與休眠核對卡, 8.4; contract 3.1, 3.6, 4.1): what the panel reads about a restore, a dormant start
// and the quarantine directories, checked before anything of it is shown. Every value here may come from a backup
// (a forged one too): it is only ever inserted as text (app.js's el()), and anything that is not the contract's shape
// is refused or shown as unknown, never as text the server sent in its place. No browser storage (DQ-18; N15).
import { UiError } from './contracts.js';
import { DEFAULT_PROFILE, PROFILE_ID, isExtraProfile } from './profiles.js';

const TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/;
const time = value => typeof value === 'string' && TIME.test(value);
// A quarantine directory as the management API names it (contract 3.1): <id>-<UTC>[-n], the directory without its
// ".quarantine-" prefix.
export const QUARANTINE_NAME = /^([0-9a-f]{24})-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?$/;
const count = value => Number.isSafeInteger(value) && value >= 0;

// The bootstrap's restore notice (DQ-03 (b), the owner's decision of 2026-11-16): a restore kept the default profile's
// token. null when there is none; a malformed one still shows, without a time (the notice matters, its time less).
export function restoreNotice(bootstrap) {
  const value = bootstrap?.restore_notice;
  if (value === undefined || value === null) return null;
  return { at: value && typeof value === 'object' && !Array.isArray(value) && time(value.at) ? value.at : null };
}
// The switched-on default bootstrap's restore_review: how many profiles wait for a review (null: the record cannot be
// read), and when the restore or the dormant revocation was. null when none waits.
export function restoreReview(bootstrap) {
  const value = bootstrap?.restore_review;
  if (value === undefined || value === null) return null;
  if (typeof value !== 'object' || Array.isArray(value)) return { pending: null, restoreAt: null, dormantAt: null };
  return { pending: count(value.pending) ? value.pending : null, restoreAt: time(value.restore_at) ? value.restore_at : null,
    dormantAt: time(value.dormant_at) ? value.dormant_at : null };
}
// A switched-off bootstrap with profile data on disk (HM-13b): how many additional profiles are dormant (revoked).
export const dormantProfiles = bootstrap => count(bootstrap?.dormant_profiles) ? bootstrap.dormant_profiles : null;

export class RecordError extends UiError {
  constructor() { super('還原紀錄的格式與這個管理介面不相容，無法顯示核對卡。請重新整理；一再出現時請更新 add-on。'); }
}
const TOKENS = ['revoked', 'kept', 'already_revoked'];
// The policy summary's fields (contract 3.6: identity_fields POLICY and SESSION), in this order.
const POLICY = ['writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations', 'odoo_write_switches',
  'odoo_allowed_methods', 'n8n_session'];
const short = value => typeof value === 'string' && value.length <= 2048;
// The guard's record as GET profiles/restore-record answers it ({record}), checked: rows of profiles with their id,
// label, token and review, identity values as strings, the policy's fields as their types. Anything else: RecordError.
export function recordView(answer) {
  if (!answer || typeof answer !== 'object' || Array.isArray(answer) || Object.keys(answer).join() !== 'record') throw new RecordError();
  const value = answer.record;
  if (value === null) return null;
  const invalid = () => { throw new RecordError(); };
  // The record is at most 1 MiB (contract 3.6): a hand-made backup may hold many orphans; their rows are shown all.
  if (!value || typeof value !== 'object' || value.version !== 1 || !Array.isArray(value.profiles) || value.profiles.length > 8192
      || !Array.isArray(value.quarantined) || value.quarantined.length > 8192) invalid();
  if (value.restore !== null && !(value.restore && typeof value.restore === 'object' && time(value.restore.at))) invalid();
  if (value.dormant !== null && !(value.dormant && typeof value.dormant === 'object' && time(value.dormant.at))) invalid();
  const seen = new Set();
  const rows = value.profiles.map(row => {
    if (!row || typeof row !== 'object' || Array.isArray(row) || typeof row.id !== 'string' || !PROFILE_ID.test(row.id) || seen.has(row.id)
        || row.is_default !== (row.id === DEFAULT_PROFILE) || !(row.label === null || short(row.label)) || !TOKENS.includes(row.token)
        || !(row.reviewed_at === null || time(row.reviewed_at)) || !row.identity || typeof row.identity !== 'object'
        || Array.isArray(row.identity) || !row.policy || typeof row.policy !== 'object' || Array.isArray(row.policy)) invalid();
    seen.add(row.id);
    const identity = Object.entries(row.identity).slice(0, 16).map(([key, item]) => {
      if (!/^[a-z_]{1,40}$/.test(key) || !(item === null || short(item))) invalid();
      return [key, item];
    });
    return { id: row.id, label: row.label, isDefault: row.is_default, token: row.token, reviewedAt: row.reviewed_at,
      identity, policy: policyView(row.policy) };
  });
  return { restoreAt: value.restore?.at ?? null, dormantAt: value.dormant?.at ?? null, rows };
}
function policyView(policy) {
  const names = value => Array.isArray(value) && value.length <= 4096 && value.every(item => typeof item === 'string' && item.length <= 300);
  const view = {};
  for (const key of POLICY) {
    if (!Object.hasOwn(policy, key)) continue;
    const value = policy[key];
    if (key === 'writes_enabled') { if (typeof value !== 'boolean') throw new RecordError(); view[key] = value; }
    else if (['disabled', 'enabled_write_tools'].includes(key)) { if (!names(value)) throw new RecordError(); view[key] = value.length; }
    else if (key === 'odoo_allowed_methods') { if (value !== null && !names(value)) throw new RecordError(); view[key] = value === null ? null : value.length; }
    else if (key === 'denied_operations') {
      if (!value || typeof value !== 'object' || Array.isArray(value) || !Object.values(value).every(names)) throw new RecordError();
      view[key] = Object.values(value).reduce((sum, items) => sum + items.length, 0);
    } else if (key === 'odoo_write_switches') {
      if (value !== null && !(value && typeof value === 'object' && !Array.isArray(value) && Object.values(value).every(item => typeof item === 'boolean'))) throw new RecordError();
      view[key] = value === null ? null : Object.values(value).filter(Boolean).length;
    } else if (key === 'n8n_session') {
      if (value !== null && !(value && typeof value === 'object' && count(value.timeout_seconds) && count(value.max_sessions))) throw new RecordError();
      view[key] = value === null ? null : { timeout: value.timeout_seconds, sessions: value.max_sessions };
    }
  }
  return view;
}
// The policy summary, one line of fixed text with whole numbers only (never a tool or method name the record holds).
export function policyLine(view) {
  const parts = [];
  if (Object.hasOwn(view, 'writes_enabled')) parts.push(view.writes_enabled ? '舊版全域寫入：開' : '舊版全域寫入：關');
  if (Object.hasOwn(view, 'disabled')) parts.push(`停用工具 ${view.disabled} 個`);
  if (Object.hasOwn(view, 'enabled_write_tools')) parts.push(`逐項寫入授權 ${view.enabled_write_tools} 項`);
  if (Object.hasOwn(view, 'denied_operations')) parts.push(`禁止的操作 ${view.denied_operations} 項`);
  if (Object.hasOwn(view, 'odoo_write_switches')) parts.push(view.odoo_write_switches === null ? 'Odoo 子操作開關：沿用舊值' : `Odoo 子操作開關開啟 ${view.odoo_write_switches} 項`);
  if (Object.hasOwn(view, 'odoo_allowed_methods')) parts.push(view.odoo_allowed_methods === null ? 'Odoo 方法清單：沒有存過' : `Odoo 方法清單 ${view.odoo_allowed_methods} 項`);
  if (Object.hasOwn(view, 'n8n_session') && view.n8n_session) parts.push(`n8n 連線：閒置 ${view.n8n_session.timeout} 秒、最多 ${view.n8n_session.sessions} 個`);
  return parts.join('、') || '沒有政策欄位';
}
export const tokenText = token => ({ revoked: '權杖已撤銷', already_revoked: '權杖之前就已撤銷', kept: '權杖沒有撤銷（回到備份當時的值）' })[token] ?? '權杖狀態不明';
// Whether a row's new token waits for its review (contract 4.1: the guard revoked it).
export const waitsForReview = row => ['revoked', 'already_revoked'].includes(row.token) && row.reviewedAt === null;

// The profile list's quarantine directories ("quarantined", only when there is one): [{name, id}], their id the
// name's. Anything else refuses the list (as its orphans do).
export function quarantinedEntries(value) {
  const entries = value?.quarantined;
  if (entries === undefined) return [];
  if (!Array.isArray(entries) || entries.length > 64) throw new UiError('帳號清單格式不符，無法顯示。');
  const seen = new Set();
  return entries.map(entry => {
    const match = entry && typeof entry === 'object' && !Array.isArray(entry) && Object.keys(entry).sort().join() === 'id,name'
      && typeof entry.name === 'string' ? QUARANTINE_NAME.exec(entry.name) : null;
    if (!match || match[1] !== entry.id || seen.has(entry.name)) throw new UiError('帳號清單格式不符，無法顯示。');
    seen.add(entry.name);
    return { name: entry.name, id: entry.id };
  });
}
// When a quarantine directory was made, from its name (<id>-YYYYMMDDTHHMMSSZ[-n]), as the panel shows a time.
export function quarantineTime(name) {
  const stamp = QUARANTINE_NAME.test(name) ? name.slice(25, 41) : null;
  return stamp ? `${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)} ${stamp.slice(9, 11)}:${stamp.slice(11, 13)}（UTC）` : '時間不明';
}

// "revoke all"'s per-profile results (contract 3.1, 4.1): [{id, result}]; null when they are not the contract's.
export function revocationResults(value) {
  if (!Array.isArray(value) || value.length > 4096) return null;
  const valid = value.every(item => item && typeof item === 'object' && Object.keys(item).sort().join() === 'id,result'
    && typeof item.id === 'string' && PROFILE_ID.test(item.id) && ['revoked', 'failed', 'quarantined'].includes(item.result));
  return valid ? value.map(item => ({ id: item.id, result: item.result })) : null;
}

// The export (plan 6, 選做; PaaS runbook step 1): what an administrator keeps before a restore, built from each
// profile's bootstrap by an allow-list, so no token, child token, CSRF value or credential can be in it: the list
// row's id, label and port; the backend's non-secret fields (backend_edit.values; n8n: backend_url); the policy.
const POLICY_COPY = ['writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations', 'odoo_write_switches',
  'odoo_allowed_methods', 'n8n_session'];
export function exportEntry(row, bootstrap) {
  const values = bootstrap?.backend_edit?.values;
  const connection = {};
  if (values && typeof values === 'object' && !Array.isArray(values)) {
    for (const [key, value] of Object.entries(values)) if (/^[a-z_]{1,40}$/.test(key) && (value === null || short(value))) connection[key] = value;
  }
  if (bootstrap?.product === 'n8n' && (bootstrap.backend_url === null || short(bootstrap.backend_url))) connection.backend_url = bootstrap.backend_url;
  const policy = {};
  for (const key of POLICY_COPY) if (Object.hasOwn(bootstrap ?? {}, key)) policy[key] = structuredClone(bootstrap[key]);
  return { id: row.id, label: row.hidden ? null : row.label, port: row.port, is_default: row.id === DEFAULT_PROFILE,
    connection_configured: bootstrap?.connection_configured === true, connection, policy };
}
export function exportDocument(product, entries, now = new Date()) {
  return JSON.stringify({ kind: 'woow-mcp-profile-list', version: 1, product, exported_at: now.toISOString().replace(/\.\d{3}Z$/, '+00:00'),
    note: '不含任何權杖或憑證；還原後在核對卡逐帳號比對。', profiles: entries }, null, 2);
}
export const reviewableId = id => id === DEFAULT_PROFILE || isExtraProfile(id);
