// HM-11 (plan 6; contract 3): the panel's profiles. The rules the panel checks (ids, echoes, list rows, labels) and the
// profile menu with its create/rename dialog; app.js passes its own DOM helpers in. The selected profile lives only in
// the page's memory (DQ-18): no browser storage, so a reload starts on the default profile.
import { UiError } from './contracts.js';

export const DEFAULT_PROFILE = 'default';
export const PROFILE_ID = /^(?:default|[0-9a-f]{24})$/;
export const INDEX_REVISION = /^p1-[0-9a-f]{64}$/;
const EXTRA_ID = /^[0-9a-f]{24}$/;
export const isProfileId = value => typeof value === 'string' && PROFILE_ID.test(value);
export const isExtraProfile = value => typeof value === 'string' && EXTRA_ID.test(value);
// How the panel names a profile next to its label: "default" or the first 8 characters of its id (as the logs do).
export const shortId = id => id === DEFAULT_PROFILE ? DEFAULT_PROFILE : id.slice(0, 8);
// OpenDesign and Odoo Manage never get additional profiles (DQ-28): no create button.
const NO_EXTRA_PROFILES = ['opendesign', 'odoo-manage'];
export const canCreateProfiles = product => !NO_EXTRA_PROFILES.includes(product);

// Labels (DQ-16; contract 3.6): 1-80 code points once trimmed; no control, format (bidi, zero-width), line or paragraph
// separator, surrogate, private-use or unassigned character; "default" and 預設帳號 are reserved. The server decides
// (NFKC + casefold for duplicates, 409); this check only answers early. Lengths count code points, not UTF-16 units.
export const LABEL_MAX = 80;
const REFUSED = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}\p{Co}\p{Cn}]/u;
const codePoints = value => [...value].length;
export function labelProblem(value) {
  if (typeof value !== 'string' || value.trim() === '') return '請填寫帳號名稱。';
  const label = value.trim();
  if (codePoints(label) > LABEL_MAX) return `帳號名稱最多 ${LABEL_MAX} 個字（目前 ${codePoints(label)} 個）。`;
  if (REFUSED.test(label)) return '帳號名稱不能含控制字元、零寬字元或雙向控制字元。';
  if (['default', '預設帳號'].includes(label.normalize('NFKC').toLowerCase())) return '「default」與「預設帳號」是保留名稱，請換一個名稱。';
  return null;
}
// A label as the server stored it: shown only when it still follows the rules (a list that breaks them is refused).
const storedLabel = value => typeof value === 'string' && value === value.trim() && codePoints(value) >= 1
  && codePoints(value) <= LABEL_MAX && !REFUSED.test(value);

// The echo (contract 3.4; HM-05's gateway): with profiles, the bootstrap carries profile {id, label, is_default} and
// profiles_supported: true, every other answer of a profile-scoped action profile {id}. A single-profile server sends
// neither. Anything else means the answer is not the asked profile's: the panel shows nothing of it (I12).
export function echoMatches(value, profile, bootstrap = false) {
  const object = value !== null && typeof value === 'object' && !Array.isArray(value);
  if (profile === null) return !object || !Object.hasOwn(value, 'profile') && !Object.hasOwn(value, 'profiles_supported');
  if (!object) return false;
  const echo = value.profile;
  if (!echo || typeof echo !== 'object' || Array.isArray(echo) || echo.id !== profile) return false;
  if (!bootstrap) return Object.keys(echo).join() === 'id' && !Object.hasOwn(value, 'profiles_supported');
  return value.profiles_supported === true && Object.keys(echo).sort().join() === 'id,is_default,label'
    && echo.is_default === (profile === DEFAULT_PROFILE) && storedLabel(echo.label);
}

// List rows (contract 3.6; §8.8 #51). Unknown status or reason values are shown as unknown, never as text the server sent.
const STATUS = { running: '執行中', starting: '啟動中', backoff: '退避等待', unconfigured: '尚未設定', blocked: '無法啟動',
  failed: '啟動失敗', dormant: '休眠' };
const DISABLED = { profile_limit: '超過帳號上限，已停用', memory_capacity: '記憶體不足，已停用', port_conflict: 'port 衝突，已停用',
  profile_unavailable: '設定讀不到，已停用', quarantined: '已隔離，已停用', dormant: '休眠，已停用' };
const BLOCKED = { child_port_conflict: '子行程的 port 和 add-on 自己的 port 相同', child_port_in_use: '子行程的 port 已被其他程式占用',
  memory_capacity: '可用記憶體不足' };
const WORD = /^[a-z_]{1,40}$/;
const word = value => value === null || value === undefined || typeof value === 'string' && WORD.test(value);
export function profileRows(value) {
  const rows = value?.profiles;
  const invalid = () => { throw new UiError('帳號清單格式不符，無法顯示；請重新整理。'); };
  if (!Array.isArray(rows) || rows.length < 1 || rows.length > 6) invalid();
  const seen = new Set();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row) || !isProfileId(row.id) || seen.has(row.id)
        || row.is_default !== (row.id === DEFAULT_PROFILE) || !storedLabel(row.label)
        || !Number.isInteger(row.port) || row.port < 1024 || row.port > 65535 || !word(row.disabled_reason)
        || !word(row.status) || !word(row.blocked_reason)
        || row.required_memory_mib !== undefined && !(Number.isSafeInteger(row.required_memory_mib) && row.required_memory_mib > 0)) invalid();
    seen.add(row.id);
  }
  if (!seen.has(DEFAULT_PROFILE)) invalid();
  return rows;
}
export const profileName = row => row?.is_default || row?.id === DEFAULT_PROFILE ? '預設帳號' : row?.label ?? '';
export const statusLabel = row => row?.status ? STATUS[row.status] ?? '未知狀態' : '狀態未知';
export function optionLabel(row) {
  const parts = [`${profileName(row)}（${shortId(row.id)}）`, statusLabel(row)];
  if (row.disabled_reason) parts.push(DISABLED[row.disabled_reason] ?? '已停用');
  return parts.join(' · ');
}
// What the selected profile's menu says about it (PaaS profileStatus.js; HA reasons added, §8.8 #51).
export function disabledNotice(row) {
  switch (row?.disabled_reason) {
    case null: case undefined: case '': return '';
    case 'memory_capacity':
      return `這個帳號因可用記憶體不足而停用，子行程不會啟動${Number.isSafeInteger(row.required_memory_mib) ? `；至少要 ${row.required_memory_mib} MiB 才能啟用` : ''}。可以刪除其他帳號，或先保留設定。`;
    case 'profile_limit': return '這個帳號超過這個產品的帳號上限而停用，子行程不會啟動；請刪除其他帳號。';
    case 'port_conflict': return '帳號索引把這個帳號的 port 也指派給了其他帳號，子行程不會啟動；請刪除其中一個帳號。';
    case 'profile_unavailable': return '這個帳號的設定讀不到（可能來自還原或手動修改），不會服務 MCP 請求；只能刪除。';
    case 'quarantined': return '這個帳號已被隔離，不會服務 MCP 請求；只能刪除。';
    case 'dormant': return '這個帳號在休眠中，權杖已撤銷，子行程不會啟動。';
    default: return '這個帳號目前停用，子行程不會啟動。';
  }
}
export function blockedNotice(row) {
  if (row?.status !== 'blocked') return '';
  return `子行程無法啟動：${BLOCKED[row.blocked_reason] ?? '原因未知'}。這個帳號的設定仍可修改。`;
}
// The client example's server name (DQ-31; §8.8 #85): an additional profile's carries its id, so two profiles of one
// product can be added to one client without clashing. The default profile keeps "woow".
export const clientName = (product, profile) => isExtraProfile(profile) ? `woow-${product}-${shortId(profile)}` : 'woow';

// The menu in the top bar (plan 6): only when the server serves profiles. ui = {el, button}; on = {select, create,
// rename, remove}. While a profile loads (loading), the menu is the page's only control: choosing again replaces the load.
export function profileMenu(ui, { rows, current, loading, product, corrupt }, on) {
  const { el, button } = ui;
  // A profile just created is not in the list read before it yet: it gets a plain option while it loads.
  const listed = rows.some(row => row.id === current);
  const select = el('select', { id: 'profile-select', 'aria-label': '帳號' },
    ...rows.map(row => el('option', { value: row.id }, optionLabel(row))),
    listed ? null : el('option', { value: current }, `（${shortId(current)}）`));
  select.value = current;
  select.addEventListener('change', () => on.select(select));
  const row = rows.find(item => item.id === current);
  const extra = isExtraProfile(current);
  const controls = loading ? [] : [
    canCreateProfiles(product) && !corrupt ? button('新增帳號', on.create, { id: 'profile-create' }) : null,
    button('改名', on.rename, { id: 'profile-rename', disabled: !extra || corrupt }),
    button('刪除帳號', on.remove, { id: 'profile-delete', disabled: !extra || corrupt }),
  ];
  const notes = loading ? [] : [disabledNotice(row), blockedNotice(row)].filter(Boolean)
    .map(text => el('p', { class: 'profile-note' }, text));
  return el('div', { class: 'profile-bar' },
    el('div', { class: 'profile-choose' }, el('span', { class: 'profile-caption', 'aria-hidden': 'true' }, '帳號'), select, ...controls),
    ...notes);
}

// The create and rename dialog: resolves with the trimmed label, or null when cancelled. The label is checked here
// first (the server checks again); names are only ever inserted as text.
export function labelDialog(ui, { title, description, initial = '', submit }) {
  const { el, button } = ui;
  return new Promise(resolve => {
    const previous = document.activeElement;
    const input = el('input', { id: 'profile-label', type: 'text', autocomplete: 'off', spellcheck: 'false',
      required: true, 'aria-describedby': 'profile-label-help profile-label-error' });
    input.value = initial;
    const error = el('p', { id: 'profile-label-error', class: 'dialog-error', 'aria-live': 'assertive' });
    const form = el('form', { method: 'dialog' },
      el('div', { class: 'field' }, el('label', { for: 'profile-label' }, '帳號名稱'), input),
      el('p', { id: 'profile-label-help', class: 'hint' }, `1–${LABEL_MAX} 個字；不能含控制字元、零寬字元或雙向控制字元，「default」與「預設帳號」是保留名稱。名稱只用來顯示，不會出現在網址、紀錄或 MCP 回應裡。`),
      error,
      el('div', { class: 'actions' }, button('取消', () => finish(null)), el('button', { type: 'submit', class: 'primary' }, submit)));
    const dialog = el('dialog', { 'aria-labelledby': 'profile-dialog-title', 'aria-describedby': 'profile-dialog-description' },
      el('h2', { id: 'profile-dialog-title' }, title), el('p', { id: 'profile-dialog-description' }, description), form);
    function finish(answer) { dialog.close(); dialog.remove(); previous?.focus(); resolve(answer); }
    form.addEventListener('submit', event => {
      event.preventDefault();
      const problem = labelProblem(input.value);
      if (problem) { error.textContent = problem; input.focus(); return; }
      finish(input.value.trim());
    });
    input.addEventListener('input', () => { error.textContent = ''; });
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(null); });
    document.body.append(dialog);
    dialog.showModal();
    input.focus();
    input.select();
  });
}
