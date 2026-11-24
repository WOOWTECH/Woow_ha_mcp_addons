import { AdminApi, ApiError, DEFAULT_ORIGINS, ProfileEchoError, StaleProfileError, TOKEN_ROTATED, originList } from './api.js';
import { products, connectionHelpFor, policyRestartsChild, policyRestartNotice, UiError, explicitUrl, backendPayload, granularPolicy, operationPolicy, staleOperationDenies, toolRows, policyPayload, policyFingerprint, savedGrant, policySummary, catalogSummary, operationSummary, conditionalWriteSummary, environmentLabels, clientExample, claudeConnectorUrl, ownerDefaultsView, noticeTime, odooSwitches, odooSwitchKeys, odooSwitchPayload, maskedCurrentToken, tokenHistory, backendEdit, backendPatchPayload, newOriginSecrets, urlSecrets, n8nSession, n8nSessionPayload, odooMethods, odooMethodsPayload } from './contracts.js';
import { DEFAULT_PROFILE, clientName, indexState, isExtraProfile, labelDialog, profileMenu, profileName, shortId, statusLabel } from './profiles.js';
import { QUARANTINE_SHOWN, dormantProfiles, exportDocument, exportEntry, policyLine, quarantineTime, restoreNotice, restoreReview, tokenText, waitsForReview } from './restore.js';
import './styles.css';

const root = document.querySelector('#app');
let api, state, busy = false, revealed = null, revealTimer, dialog, revealEpoch = 0;
// HM-11 (plan 6): with profiles, the profile list ({rows, orphans, revision}; substitute: corrupt or unreadable, see
// readProfiles) and the newest page load of a profile (views; loading while it runs). Without profiles (api.profile ===
// null) none of this is used and the page is as before.
let profiles = null, views = 0, loading = false, product = null;
// HM-13c (plan 6 還原與休眠核對卡): the restore record the default profile's review card shows ({view} or {error}; null
// when nothing waits), and the restore notice "知道了" hid (its time; in this page's memory only: no browser storage,
// N15, so a reload shows it again).
let record = null, noticeHidden = null;
const routes = { overview: '總覽', backend: '後端連線', tools: '工具權限', access: '連線與權杖', diagnostics: '診斷與維護' };
const icons = { overview: 'view-grid', backend: 'server-network', tools: 'shield-check', access: 'tune-variant', diagnostics: 'text-box-search' };
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (typeof value === 'boolean') { if (value) node.setAttribute(key, ''); }
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  node.append(...children.filter(v => v !== null && v !== undefined));
  return node;
}
const icon = name => el('span', { class: 'icon-tile', 'aria-hidden': 'true' }, el('i', { class: `mdi mdi-${name}` }));
const p = text => el('p', {}, text);
const button = (text, action, attrs = {}) => el('button', { type: 'button', onclick: action, ...attrs }, text);
const chip = text => el('span', { class: 'chip' }, text);
const card = (title, ...children) => el('section', { class: 'card' }, el('h2', {}, title), ...children);
function notice(text, error = false) {
  const box = document.querySelector('#notice');
  if (box) { box.className = `notice ${error ? 'error' : ''}`; box.replaceChildren(text); box.hidden = false; box.focus(); }
}
function route() {
  const path = location.pathname.slice(api.mount.length).replace(/^\/+|\/+$/g, '');
  return Object.hasOwn(routes, path) ? path : 'overview';
}
function navigate(name) {
  hideToken();
  history.pushState(null, '', `${api.mount}/${name}`);
  render();
  document.querySelector('h1')?.focus();
}
function hideToken() {
  revealEpoch++;
  revealed = null;
  clearTimeout(revealTimer);
  for (const id of ['#token-secret', '#claude-secret']) {
    document.querySelector(id)?.replaceChildren();
    document.querySelector(id)?.setAttribute('hidden', '');
  }
}
function fail(error) {
  hideToken();
  if (error instanceof ApiError && [401, 403].includes(error.status)) {
    state = null;
    renderDenied(error.message);
  } else notice(error instanceof UiError ? error.message : '操作未完成。請重新整理狀態後再試。', true);
}
async function task(action) {
  if (busy) return;
  busy = true;
  root.setAttribute('aria-busy', 'true');
  const controls = [...root.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)')];
  controls.forEach(node => node.disabled = true);
  let next = null;
  try { await action(); } catch (error) { next = followUp(error); if (!next) fail(error); }
  finally { busy = false; root.removeAttribute('aria-busy'); controls.forEach(node => node.disabled = node.dataset.conflict === 'true'); refreshOperation(); }
  if (next) await next();
}
// HM-11: what a refusal about the profile leads to, once the task's lock is released (null: shown as before by fail).
// - an answer for another profile than asked (echo, I12): hide every token, show nothing of it and read again;
// - the selected profile is gone (deleted elsewhere): back to the default profile, its unconfirmed receipt cleared;
// - an answer that came after the panel moved on: dropped unseen.
function followUp(error, recovering = false) {
  if (error instanceof StaleProfileError) return () => {};
  // HM-12 (contract 3.1, section 9 #113): a backend save that rotated the token although its new child did not start
  // (shape D with token_rotated): the new state is read again (every shown token hidden), then its notice; said even
  // when it cannot be read again (reloadRotated, review S-2).
  if (error instanceof ApiError && error.tokenRotated) return () => task(() => reloadRotated(error.message, true));
  if (error instanceof ProfileEchoError || error instanceof ApiError && error.code === 'profile_id_required') {
    hideToken();
    return recovering ? null : () => show(null, error.message, true, true);
  }
  if (api.profile === null || !(error instanceof ApiError) || recovering) return null;
  if (error.code === 'profile_not_found') return () => gone(api.profile);
  if (error.code === 'profile_index_corrupt' && api.profile !== DEFAULT_PROFILE) return () => show(DEFAULT_PROFILE, error.message, true, true);
  return null;
}
const profileOf = view => view?.profile?.id ?? null;
// HM-11 (FM-60, FM-64): with profiles, a page that edits one profile's settings says so (nothing without profiles).
const scopeNote = text => api.profile === null ? null : el('p', { class: 'profile-scope' }, `帳號${named(currentRow(), api.profile)}：${text}`);
const currentRow = () => profiles?.rows.find(row => row.id === api.profile) ?? null;
const named = (row, id) => `「${row ? profileName(row) : shortId(id)}」（${shortId(id)}）`;
function pendingFor(id) { try { return Boolean(api.pendingOperation(id)); } catch { return true; } }
// The list as the menu uses it. A list the panel cannot use never locks the page (review S-2): the default profile stays
// usable, alone in the menu (with the profile shown, when it is another), nothing about profiles can be changed, and it
// is no evidence that a profile was deleted (substitute). corrupt: the index cannot be used (DQ-12; the bootstrap says
// so, or the list answers profile_index_corrupt); unreadable: the list failed or does not follow the contract. A list
// without its ETag is shown, but read-only (revision null).
async function readProfiles(fresh) {
  const corrupt = indexState(fresh).corrupt;
  try {
    const list = await api.profileList();
    return corrupt ? { ...list, revision: null, corrupt: true } : list;
  } catch (error) {
    if (error instanceof StaleProfileError || error instanceof ProfileEchoError || error instanceof ApiError && [401, 403].includes(error.status)) throw error;
    const rows = [{ id: DEFAULT_PROFILE, label: 'Default', port: 3000, is_default: true, disabled_reason: null }];
    return corrupt || error instanceof ApiError && error.code === 'profile_index_corrupt'
      ? { rows, orphans: [], quarantined: [], revision: null, substitute: true, corrupt: true }
      : { rows, orphans: [], quarantined: [], revision: null, substitute: true, unreadable: true };
  }
}
// HM-11 (plan 6): show another profile (target: its id; null: find the server's profile mode again). The page is
// replaced first: the token hidden, every typed secret and draft gone, only the profile menu left. Choosing again while
// it loads replaces this load; whatever answer this one still gets is dropped (api.epoch).
async function show(target, message, error = false, recovering = false) {
  const view = ++views, left = api.profile, leftRow = currentRow();
  const unconfirmed = target !== null && left !== null && left !== target && pendingFor(left);
  hideToken();
  document.querySelectorAll('input[type=password]').forEach(input => { input.value = ''; });
  busy = true; loading = true; root.setAttribute('aria-busy', 'true');
  state = null;
  let next = null;
  try {
    if (target !== null) api.select(target);
    renderLoading(target);
    const fresh = target === null ? await api.open() : await api.bootstrap();
    if (fresh.capabilities?.schema_version === 1) fresh.capabilities = await api.capabilities();
    const list = api.profile === null ? null : await readProfiles(fresh);
    if (list && !list.substitute && !list.rows.some(row => row.id === api.profile)) throw new ApiError(404, 'profile_not_found');
    const loaded = await loadRecord(fresh);
    if (view !== views) return;
    // The profile left behind is no longer in a list the panel can trust (deleted elsewhere): it cannot be gone back
    // to, so its unconfirmed receipt is cleared and said so (review S-1). A substitute list is not such a list.
    const leftGone = Boolean(list) && !list.substitute && isExtraProfile(left) && left !== api.profile && !list.rows.some(row => row.id === left);
    const cleared = leftGone && forget(left);
    state = fresh; profiles = list; product = fresh.product; record = loaded;
    render();
    const texts = [message ?? (target === null ? null : `已切換到帳號${named(currentRow(), api.profile)}。`),
      cleared ? `前一個帳號${named(leftRow, left)}已不存在，可能已在其他分頁或由其他管理員刪除；它尚未確認的操作紀錄已一併清除：帳號刪除時它的權杖已撤銷。`
        : unconfirmed && !leftGone ? `前一個帳號${named(leftRow, left)}有尚未確認的操作；請切回該帳號查詢結果，再決定是否重試。` : null].filter(Boolean);
    if (texts.length) notice(texts.join(' '), error || unconfirmed);
  } catch (problem) {
    if (view !== views || problem instanceof StaleProfileError) return;
    next = followUp(problem, recovering);
    if (!next) loadFailed(target, problem);
  } finally {
    if (view === views) { busy = false; loading = false; root.removeAttribute('aria-busy'); refreshOperation(); }
  }
  if (next) await next();
}
// A deleted profile's unconfirmed receipt can never be queried again (§8.8 #84, FM-59): it is cleared, whichever way
// the profile went (deleted here, a resent delete confirmed, or deleted elsewhere), and the caller says so when there
// was one. It runs before show(), so the switch never asks to go back to the deleted profile.
function forget(id) {
  if (!isExtraProfile(id)) return false;
  try { const pending = pendingFor(id); api.acknowledgeOperation(id); return pending; } catch { return false; }
}
// The selected profile no longer exists (contract 3.4; §8.8 #84): the default profile again, said plainly.
async function gone(id) {
  const row = profiles?.rows.find(item => item.id === id) ?? null;
  const cleared = forget(id);
  await show(DEFAULT_PROFILE, `帳號${named(row, id)}已不存在，可能已在其他分頁或由其他管理員刪除；已切回預設帳號。${cleared ? '它尚未確認的操作紀錄已一併清除：帳號刪除時它的權杖已撤銷。' : ''}`, true, true);
}
function loadFailed(target, problem) {
  hideToken();
  if (problem instanceof ApiError && [401, 403].includes(problem.status)) { state = null; renderDenied(problem.message); return; }
  const actions = [button('重新嘗試', () => show(target))];
  if (isExtraProfile(target)) actions.push(button('回到預設帳號', () => show(DEFAULT_PROFILE)));
  // A profile whose state cannot be read is still deletable (contract 3.3), from here.
  // HM-11 review observation 4 (HM-13c): without the list's revision a deletion cannot be sent; say so instead.
  if (isExtraProfile(target) && currentRow()?.disabled_reason === 'profile_unavailable') actions.push(profiles?.revision === null
    ? p('帳號清單缺少版本資訊，暫時無法刪除這個帳號；請重新整理狀態後再試。') : button('刪除帳號', deleteProfile));
  root.replaceChildren(el('main', { class: 'blocked' }, icon('account-alert'), el('h1', {}, target === null ? '管理狀態無法讀取' : `無法載入帳號${named(profiles?.rows.find(row => row.id === target), target)}`),
    p(problem instanceof UiError ? problem.message : '管理服務無法使用。'), el('div', { class: 'actions' }, ...actions)));
}
function renderLoading(target) {
  const menu = profiles && target !== null && api.profile !== null
    ? profileMenu({ el, button }, { rows: profiles.rows, current: target, loading: true }, profileActions) : null;
  root.replaceChildren(el('header', { class: 'topbar' }, brandCaption(), product ? el('div', { class: 'product-label' }, products[product].name) : null, menu),
    el('main', { class: 'blocked', role: 'status' }, p(target === null ? '正在重新讀取管理狀態…' : `正在切換到帳號${named(profiles?.rows.find(row => row.id === target), target)}…`)));
}
const profileActions = { select: onProfileChange, create: createProfile, rename: renameProfile, remove: deleteProfile };
function onProfileChange(select) {
  if (busy && !loading) { select.value = api.profile; notice('請等目前的操作完成後再切換帳號。', true); return; }
  if (!loading && select.value === api.profile) return;
  show(select.value);
}
async function createProfile() {
  if (busy || !profiles || profiles.revision === null) return;
  const label = await labelDialog({ el, button }, { title: '新增帳號', submit: '建立帳號',
    description: `新帳號會複製預設帳號目前的工具權限與寫入設定，之後各自獨立；後端連線是空的，要另外設定。建立後會自動切換到新帳號；需要權杖時到「連線與權杖」按「${state.product === 'headscale' ? '重新產生' : '顯示權杖'}」。` });
  if (label === null) return;
  const revision = profiles.revision;
  let created = null;
  await task(async () => { created = await api.createProfile(label, revision); });
  if (created) await show(created.id, `已建立${createdName(created)}，並切換到這個帳號。請到「後端連線」設定它自己的後端。`);
}
// A created profile named in a notice: its label, unless this browser cannot show it (review S-2).
const createdName = created => created.label === null ? `帳號（${shortId(created.id)}）` : `帳號「${created.label}」（${shortId(created.id)}）`;
async function renameProfile() {
  const row = currentRow();
  if (busy || !row || !isExtraProfile(row.id) || profiles.revision === null) return;
  const label = await labelDialog({ el, button }, { title: `改名帳號${named(row, row.id)}`, initial: row.label ?? '', submit: '儲存名稱',
    description: '只改顯示名稱；這個帳號的權杖、MCP 網址與設定都不變。' });
  if (label === null) return;
  if (label === row.label) { notice('名稱沒有變更，未送出。'); return; }
  const revision = profiles.revision;
  await task(async () => {
    await api.renameProfile(row.id, label, revision);
    await reload(`已把帳號改名為「${label}」；權杖與網址都沒有變。`);
  });
}
// DQ-14: two confirmations that say what happens; the server revokes the token and wipes the credentials first.
function deleteProfile() { return removeProfile(currentRow()); }  // a declaration: profileActions takes it before this line
// HM-13c: the review card deletes a profile it lists the same way (row: a row of the list, any additional profile).
async function removeProfile(row) {
  if (busy || !row || !isExtraProfile(row.id) || profiles.revision === null) return;
  const name = named(row, row.id);
  const scoped = row.id === api.profile;
  if (!await confirmAction(`刪除帳號${name}？`, '這個帳號的 MCP 權杖會立即撤銷，用它連線的用戶端都會斷線；子行程會停止，後端連線與憑證會先抹除，再刪除這個帳號全部的設定與工具權限。面板無法復原；只有還原刪除前的備份，帳號才會連同憑證一起回來。其他帳號不受影響。', '繼續', { scoped })) return;
  if (!await confirmAction(`最後確認：刪除帳號${name}`, '確認後立即刪除，無法在面板復原。', '確認刪除', { scoped })) return;
  const revision = profiles.revision;
  let deleted = null;
  await task(async () => { deleted = await api.deleteProfile(row.id, revision); });
  if (deleted) await show(DEFAULT_PROFILE, `已刪除帳號${name}，它的權杖已失效；${scoped ? '已切回預設帳號' : '其他帳號不受影響'}。${forget(row.id) ? '它尚未確認的操作紀錄已一併清除。' : ''}`);
}
// DQ-14 (contract 3.1): an orphan (a profile directory the index does not list) is never deleted on its own; the panel
// lists it and deletes it on request, with the same two confirmations (its token is revoked, its credentials wiped).
async function deleteOrphan(id) {
  if (busy || !profiles || profiles.revision === null || !profiles.orphans.includes(id)) return;
  const name = `孤兒帳號資料（${shortId(id)}）`;
  if (!await confirmAction(`刪除${name}？`, '這份帳號資料不在帳號索引裡，不會服務 MCP 請求。刪除時會先撤銷它的權杖、抹除後端連線與憑證，再刪除它的資料夾；面板無法復原，只有還原刪除前的備份才會回來。其他帳號不受影響。', '繼續')) return;
  if (!await confirmAction(`最後確認：刪除${name}`, '確認後立即刪除，無法在面板復原。', '確認刪除')) return;
  const revision = profiles.revision;
  await task(async () => {
    await api.deleteProfile(id, revision);
    const cleared = forget(id);
    await reload(`已刪除${name}。${cleared ? '它尚未確認的操作紀錄已一併清除。' : ''}`);
  });
}
// DQ-12 (contract 3.6): an index the add-on cannot use (corrupt, or changed behind its back) is moved aside on request:
// every additional profile's token revoked, the default profile served again at once, every profile directory an
// orphan. Two confirmations, as a deletion (DQ-14). The add-on refuses with 409 config_conflict when the index is usable
// again, when it changed again (another ETag), or when there is no index file to move (the profiles directory could
// not be listed at the start: only a restart of the add-on helps); with 503 when another change of a profile holds its
// lock (nothing was done; the identity is kept for a resend).
async function quarantineIndex() {
  const { corrupt, etag } = indexState(state);
  if (busy || !profiles?.corrupt || !corrupt || api.profile !== DEFAULT_PROFILE) return;
  if (!etag) { notice('帳號索引的版本資訊格式不符，無法隔離；請重新整理狀態。', true); return; }
  if (!await confirmAction('隔離帳號索引？', '會撤銷所有額外帳號的 MCP 權杖（用它們連線的用戶端都會斷線），把帳號索引檔改名保存，預設帳號立刻恢復 MCP 服務。額外帳號的資料會留下來變成孤兒帳號資料，之後可以在「診斷與維護」逐一刪除；面板無法把它們加回索引，只有還原備份才能恢復。', '繼續')) return;
  if (!await confirmAction('最後確認：隔離帳號索引', '確認後立即撤銷所有額外帳號的權杖並改名索引檔，無法在面板復原。', '確認隔離')) return;
  let done = null, conflict = false;
  await task(async () => {
    try { done = await api.quarantineIndex(etag); }
    catch (error) {
      if (error instanceof ApiError && error.code === 'config_conflict') { conflict = true; return; }
      // HM-11 review observation 2 (HM-13c): a 503 without a code is also full management slots or an unlistable
      // profiles directory, not only another profile's change holding its lock.
      if (error instanceof ApiError && error.status === 503 && !error.code) throw new UiError('沒有執行隔離：管理服務暫時無法處理（例如另一個帳號的操作正在進行，或帳號資料夾暫時讀不到）。請稍後按「帳號操作尚未確認」裡的「重送帳號操作」，或重新整理後再試。');
      throw error;
    }
  });
  if (done) await show(DEFAULT_PROFILE, quarantined(done));
  else if (conflict) await task(async () => {
    await reload();
    const now = indexState(state);
    notice(!now.corrupt ? '帳號索引已經可以使用，沒有執行隔離。'
      : now.etag !== etag ? '帳號索引檔剛又改變了，沒有執行隔離；請確認後再試一次。'
        : '沒有可以隔離的帳號索引檔：帳號資料夾在 add-on 啟動時就無法讀取。請修好 /data/mcp/profiles 之後重新啟動 add-on；隔離解決不了這種情況。', true);
  });
}
const quarantined = done => `已隔離帳號索引（改名保存為 ${done.quarantined}）：所有額外帳號的權杖已撤銷，預設帳號已恢復 MCP 服務。原本的帳號資料已變成孤兒帳號資料，需要時可以在「診斷與維護」逐一刪除。`;
function pendingOperationCard() {
  const pending = api.pendingOperation();
  if (!pending) return null;
  const label = { 'token/rotate': '重新產生權杖', 'token/revoke': '撤銷權杖', 'child/restart': '重新啟動子行程' }[pending.route];
  return card('待確認操作', p(`${label}尚未取得完成確認。此分頁已保留原操作識別碼，重新載入也不會自動重送。`),
    p('收據最多保存 24 小時。未知結果不代表未執行；查詢與重送都需重新驗證管理權限。'),
    el('div', { class: 'actions' }, button('查詢操作結果', () => task(async () => {
      const receipt = await api.queryOperation();
      if (receipt.state === 'completed') await reload('已確認先前操作完成；未再次執行，也不會顯示歷史權杖。請檢查目前狀態。');
      else notice('收據顯示結果未知；伺服器不會再次執行相同操作。請核對目前權杖與子行程狀態。', true);
    })), button('以原識別碼重送', async () => {
      if (!await confirmAction('以原識別碼重送？', '已完成的操作只回傳收據；結果未知的操作不會再次執行。若伺服器尚未接受，仍會檢查原設定版本。')) return;
      await task(async () => { await api.retryOperation(); await reload(state.product === 'headscale' ? '操作已確認；請檢查目前狀態。需要權杖時請重新產生，這會使目前權杖失效。' : '操作已確認；請檢查目前狀態。需要權杖時請另按「顯示權杖」。'); });
    }), button('已核對目前狀態', async () => {
      if (!await confirmAction('結束這筆操作的追蹤？', '請先獨立核對目前狀態。這只清除此分頁的識別紀錄，不會復原或證明先前操作未執行；下一筆操作會使用新識別碼。')) return;
      await task(async () => { api.acknowledgeOperation(); await reload('已結束此分頁的操作追蹤。'); });
    })));
}
// HM-11: profile create and delete and the index quarantine keep their own identity (the profiles scope); its card
// shows on every page.
function pendingProfileOperationCard() {
  const pending = api.pendingProfileOperation();
  if (!pending) return null;
  const creating = pending.route === 'profiles/create', quarantining = pending.route === 'profiles/quarantine';
  // HM-13c: "revoke all", a restore review, a quarantine directory's deletion keep their identity here too.
  const revoking = pending.route === 'profiles/revoke-all', reviewing = pending.route === 'profiles/restore-review';
  const sweeping = pending.route === 'profiles/quarantine-delete';
  const what = creating ? `建立帳號「${pending.label}」` : quarantining ? '隔離帳號索引' : revoking ? '全部撤銷'
    : reviewing ? `核對帳號（${shortId(pending.profile)}）` : sweeping ? `刪除隔離的帳號資料（${shortId(pending.name)}）`
      : `刪除帳號（${shortId(pending.profile)}）`;
  return el('section', { class: 'card', id: 'pending-profile-operation' }, el('h2', {}, '帳號操作尚未確認'),
    p(`${what}尚未取得完成確認。此分頁已保留原操作識別碼，重新載入也不會自動重送。`),
    p(quarantining ? '請先看帳號索引的狀態：隔離成功時「帳號索引無法使用」的說明會消失。以原識別碼重送時，已完成的操作只回傳收據，不會再做一次。'
      : revoking ? '全部撤銷沒有完成時，沒撤銷成功的帳號在 MCP 端點回 503，直到重試成功（重新啟動 add-on 時也會自動補完）。以原識別碼重送只會再看到同一個結果；要重試，請先按「已核對帳號清單」，再按一次「全部撤銷」。'
        : reviewing || sweeping ? '請先看核對卡：核對成功時那個帳號會顯示「已核對」，刪除成功時那筆隔離的資料會消失。以原識別碼重送時，已完成的操作只回傳收據，不會再做一次。'
          : '請先看帳號選單：建立成功時清單裡會有這個帳號，刪除成功時它會消失。以原識別碼重送時，已完成的操作只回傳收據，不會再做一次。'),
    el('div', { class: 'actions' }, button('重送帳號操作', async () => {
      if (!await confirmAction('以原識別碼重送帳號操作？', `${what}。已完成的操作只回傳收據；結果未知的操作不會再次執行。`)) return;
      let result = null;
      await task(async () => {
        try { result = await api.retryProfileOperation(); } catch (error) {
          // A resent "revoke all" whose outcome is unknown: the server never runs it again (its answer has no results).
          if (revoking && error instanceof ApiError && error.code === 'operation_outcome_unknown') {
            result = { unfinished: error.results ?? [], resent: true };
            return;
          }
          // A resent delete refused before its intent (the identity is released): config_conflict, as HM-10 compares the
          // index ETag before it looks for the profile, or profile_not_found. When a list the panel can trust has the
          // profile no more (nor as an orphan), it was deleted elsewhere: nothing is left to delete, and it is that
          // profile that is gone, not the one shown (review S-1).
          if (pending.route !== 'profiles/delete' || !(error instanceof ApiError) || !['profile_not_found', 'config_conflict'].includes(error.code)) throw error;
          const list = await api.profileList().catch(() => null);
          if (!list || list.rows.some(row => row.id === pending.profile) || list.orphans.includes(pending.profile)) {
            if (error.code === 'config_conflict') throw new UiError('帳號清單已被其他操作更新，這次沒有刪除任何帳號；請確認帳號清單後再刪除一次。');
            throw error;
          }
          result = { deleted: pending.profile, missing: true };
        }
      });
      if (result?.unfinished) { notice(unfinishedText(result.unfinished, result.resent), true); return; }
      if (result && (revoking || reviewing || sweeping)) {
        await task(() => reload(revoking ? '已確認全部撤銷已完成；需要時請逐一到各帳號重新產生權杖。'
          : reviewing ? '已確認核對已完成。' : '已確認刪除隔離的帳號資料已完成。'));
        return;
      }
      // A created profile deleted since (HM-10 replays it as its id alone): confirmed, but there is nothing to switch to.
      if (result && creating && result.gone) await show(DEFAULT_PROFILE, `已確認先前建立帳號「${pending.label}」已完成，但這個帳號（${shortId(result.id)}）之後已被刪除（可能在其他分頁或由其他管理員刪除）；已切回預設帳號。${forget(result.id) ? '它尚未確認的操作紀錄已一併清除。' : ''}`);
      else if (result && quarantining) await show(DEFAULT_PROFILE, quarantined(result));
      else if (result) await show(creating ? result.id : DEFAULT_PROFILE, creating ? `已確認建立${createdName(result)}，並切換到這個帳號。`
        : `${result.missing ? `帳號（${shortId(result.deleted)}）已不存在，不需要再刪除` : '已確認刪除帳號'}；已切回預設帳號。${forget(result.deleted) ? '該帳號尚未確認的操作紀錄已一併清除。' : ''}`);
    }), button('已核對帳號清單', async () => {
      if (!await confirmAction('結束這筆帳號操作的追蹤？', '請先核對帳號清單。這只清除此分頁的識別紀錄，不會復原或證明先前操作未執行。')) return;
      await task(async () => { api.acknowledgeProfileOperation(); await reload('已結束此分頁的帳號操作追蹤。'); });
    })));
}
function refreshOperation() {
  const holder = document.querySelector('#pending-operation');
  if (!holder || !state) return;
  if (api.profile === null) {
    try { const panel = pendingOperationCard(); holder.replaceChildren(...(panel ? [panel] : [])); }
    catch (error) { notice(error instanceof UiError ? error.message : '操作紀錄無法讀取；請核對服務狀態。', true); }
    return;
  }
  const panels = [];
  for (const [card, fallback] of [[pendingOperationCard, '操作紀錄無法讀取；請核對服務狀態。'], [pendingProfileOperationCard, '帳號操作紀錄無法讀取；請核對帳號清單。'],
    [pendingOriginOperationCard, '來源設定的操作紀錄無法讀取；請核對瀏覽器來源檢查設定。']]) {
    try { const panel = card(); if (panel) panels.push(panel); }
    catch (error) { notice(error instanceof UiError ? error.message : fallback, true); }
  }
  holder.replaceChildren(...panels);
}
async function reload(message, error = false) {
  hideToken();
  state = await api.bootstrap();
  // Older servers remain usable; capability-aware servers provide the observed catalog.
  if (state.capabilities?.schema_version === 1) state.capabilities = await api.capabilities();
  product = state.product;
  if (api.profile !== null) {
    profiles = await readProfiles(state);
    if (!profiles.substitute && !profiles.rows.some(row => row.id === api.profile)) throw new ApiError(404, 'profile_not_found');
  }
  record = await loadRecord(state);
  render();
  if (message) notice(message, error);
}
// HM-12 (DQ-05; contract 3.1, section 9 #113): after a backend save the state is read again (reload hides every shown
// token first). An answer that says token_rotated also says where the new token is; switched off the add-on never says
// so, and this is reload(text) as before.
const reloadSaved = (text, result) => result?.token_rotated === true ? reloadRotated(`${text} ${TOKEN_ROTATED}`) : reload(text);
// HM-12 review S-2: once a save rotated the token, that is said even when the new state cannot be read again (a lost
// connection, a refusal): the notice, then why the page was not read again, as an error. reload hid every shown token
// before it read anything; the error keeps its kind, so fail and followUp handle it as before (a refused session is
// still shown as one, an answer for another profile still reads again).
async function reloadRotated(message, error = false) {
  try { await reload(message, error); }
  catch (problem) {
    if (!(problem instanceof UiError)) throw new UiError(`${message} 操作未完成。請重新整理狀態後再試。`);
    problem.message = `${message} ${problem.message}`;
    throw problem;
  }
}
// HM-13c: the default profile's review card shows the guard's record when the bootstrap says profiles wait for a review.
async function loadRecord(fresh) {
  if (api.profile !== DEFAULT_PROFILE || !restoreReview(fresh)) return null;
  try { return { view: await api.restoreRecord() }; }
  catch (error) {
    if (error instanceof StaleProfileError || error instanceof ProfileEchoError || error instanceof ApiError && [401, 403].includes(error.status)) throw error;
    return { error };
  }
}
async function saveForm(form, operation, payload, revision, profile = profileOf(state)) {
  if (form.dataset.conflict === 'true') throw new UiError('草稿與伺服器版本不同。請先重新整理狀態、檢查新設定，再重新編輯。');
  try { return await api.mutate(operation, payload, revision, profile); }
  catch (error) {
    if (error instanceof ApiError && error.code === 'config_conflict') {
      form.dataset.conflict = 'true';
      for (const submit of form.querySelectorAll('button')) {
        submit.dataset.conflict = 'true';
        submit.disabled = true;
      }
    }
    throw error;
  }
}
function configurationCard(initial) {
  if (!initial) return null; // Older management servers remain usable.
  const summary = el('div', { 'aria-live': 'polite', id: 'configuration-state' });
  function update(value) {
    const labels = {
      applied: '已儲存的啟動設定已由目前子行程完成協定探測。',
      pending: '設定已儲存，等待目前子行程完成套用與協定探測。',
      failed: '設定已儲存，但子行程啟動或協定探測失敗。可到「診斷與維護」檢查並重試啟動。',
      unconfigured: '尚未設定後端。可先連線查看工具；需要後端的工具尚不可用。',
      unknown: '設定已儲存，但目前無法確認子行程使用的設定。',
    };
    const rows = [p(labels[value?.apply_state] ?? labels.unknown),
      p('套用狀態與後端是否可連線分開判定；權杖與端點變更不代表子行程重新啟動。')];
    if (value?.revision !== initial.revision) rows.push(p('伺服器設定已更新。此頁保留原編輯版本與草稿；儲存前請重新整理狀態並檢查新設定。'));
    summary.replaceChildren(...rows);
    summary.dataset.applyState = Object.hasOwn(labels, value?.apply_state) ? value.apply_state : 'unknown';
  }
  update(initial);
  return card('設定套用狀態', summary, button('更新套用狀態（保留草稿）', () => task(async () => {
    const result = await api.configuration();
    // A delayed status read must never replace a newly rendered form or its revision.
    if (summary.isConnected) update(result.configuration);
  })));
}
// HM-11 (FM-58): with profiles every confirmation says which profile it acts on.
function profileLine() {
  if (!api || api.profile === null || !profiles) return null;
  return el('p', { class: 'dialog-profile' }, `帳號：${named(currentRow(), api.profile)}`);
}
// scoped: false for an action that is not the shown profile's (HM-13c: "revoke all", the review card's actions): the
// dialog then names no profile of its own.
function confirmAction(title, description, label = '確認繼續', { scoped = true } = {}) {
  return new Promise(resolve => {
    const previous = document.activeElement;
    dialog = el('dialog', { 'aria-labelledby': 'confirm-title', 'aria-describedby': 'confirm-description' },
      el('h2', { id: 'confirm-title' }, title), el('p', { id: 'confirm-description' }, description), scoped ? profileLine() : null);
    const finish = answer => { dialog.close(); dialog.remove(); dialog = null; previous?.focus(); resolve(answer); };
    dialog.append(el('div', { class: 'actions' }, button('取消', () => finish(false), { autofocus: true }), button(label, () => finish(true), { class: 'primary' })));
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(false); });
    document.body.append(dialog);
    dialog.showModal();
  });
}
// Owner decision 2026-10-27: a legacy installation was switched to the all-on defaults once, at its first start,
// without waiting for anyone. Afterwards the panel says so, shows the differences and offers to restore the
// pre-upgrade limits (faithful to the old settings: their disabled tools and only the writes they granted; never
// "everything off") or to keep everything on.
// A notice this panel cannot read (version drift) is never half shown, but it is not hidden either: a fixed card says
// so on every page, without any value from the server and without actions.
function ownerDefaults() {
  try { return ownerDefaultsView(state.owner_defaults); } catch { return { malformed: true }; }
}
function ownerDefaultsUnavailable() {
  return el('section', { class: 'card', id: 'owner-defaults-unavailable', 'aria-labelledby': 'owner-defaults-unavailable-title' },
    el('h2', { id: 'owner-defaults-unavailable-title' }, '升級通知無法顯示'),
    p('這個 add-on 從舊版升級時已自動套用預設全開，但伺服器送來的升級通知格式與這個管理介面不相容，所以無法顯示差異與還原選項。請重新整理；仍出現時請更新 add-on。未變更任何設定。'));
}
function noticeList(title, values, open = false) {
  return el('details', { open: open && values.length > 0 }, el('summary', {}, `${title}（${values.length}）`),
    values.length ? el('ul', { class: 'notice-list' }, ...values.map(value => el('li', {}, el('code', {}, value)))) : p('無'));
}
function ownerDefaultsCard(view) {
  const revision = state.configuration?.revision;
  const upgrade = view.upgrade;
  const restore = view.restore;
  const parts = [p(`已於 ${noticeTime(view.at)}自動套用預設全開：從舊版（設定格式 ${view.from_schema}）升級後第一次啟動時，一次打開全部工具與寫入，MCP 不用等確認就照常服務。`)];
  if (upgrade) parts.push(el('div', { class: 'stack', id: 'owner-defaults-upgrade' }, el('h3', {}, '升級前後差異'),
    noticeList('升級前停用、現在已啟用的工具', upgrade.enabled_tools, true),
    noticeList('升級前沒有授權、現在已授權的寫入', upgrade.granted_writes, true),
    noticeList('升級前禁止、現在已解除的操作', upgrade.cleared_operation_denies),
    noticeList('新版新增的工具（舊版沒有，預設開啟）', upgrade.new_tools),
    noticeList('新版新增的寫入操作（舊版沒有，預設授權）', upgrade.new_write_operations)));
  if (view.restored_at) parts.push(p(`已於 ${noticeTime(view.restored_at)}還原升級前的限制。之後的變更請到「工具權限」頁設定。`));
  else if (view.recovery !== 'available') parts.push(p('找不到可用的升級前限制紀錄（/data/mcp/owner-defaults-20261025-recovery.json），無法在這裡還原；需要時請改用升級前的備份。'));
  else if (!restore.available) parts.push(p('舊版設定沒有需要還原的限制。'));
  else parts.push(el('div', { class: 'stack', id: 'owner-defaults-restore-preview' }, el('h3', {}, '「還原升級前的限制」會做的變更'),
    p('回到舊版設定實際允許的範圍。工具照舊版的停用清單：只停用舊設定停用的工具，新版新增的工具不會被停用。寫入照舊版的授權清單：舊版沒授權的寫入一律不能用，所以只保留舊設定授權過的寫入，新版新增的寫入操作也會取消授權（只能寫入的新工具因此無法使用）。你升級後自己關閉的項目不會被打開。'),
    noticeList('會停用的工具', restore.disabled_added, true),
    noticeList('會取消授權的寫入（含新版新增的寫入）', restore.write_grants_removed, true),
    noticeList('會禁止的操作', restore.operation_denies_added),
    noticeList('還原後仍可使用的新版工具', restore.kept_new_tools)));
  if (view.acknowledged_at && !view.restored_at) parts.push(p(`已於 ${noticeTime(view.acknowledged_at)}選擇保持全開。`));
  const actions = el('div', { class: 'actions' });
  if (!view.restored_at && view.recovery === 'available' && restore.available) {
    actions.append(button('還原升級前的限制', () => ownerDefaultsAction('restore', revision, view), { id: 'owner-defaults-restore' }));
  }
  if (view.notice) actions.append(button('保持全開，不再提示', () => ownerDefaultsAction('dismiss', revision, view), { class: 'primary', id: 'owner-defaults-dismiss' }));
  if (actions.childElementCount) parts.push(actions);
  return el('section', { class: 'card', id: 'owner-defaults', 'aria-labelledby': 'owner-defaults-title' },
    el('h2', { id: 'owner-defaults-title' }, view.restored_at ? '升級紀錄：已還原升級前的限制' : view.notice ? '已自動套用預設全開' : '升級紀錄：預設全開'), ...parts);
}
async function ownerDefaultsAction(action, revision, view) {
  const restoring = action === 'restore';
  const later = view.recovery === 'available' && view.restore?.available ? '之後仍可在「診斷與維護」頁還原升級前的限制。' : '';
  // The counts of the preview the administrator just read (the server applies the same plan or refuses a stale one).
  const restore = view.restore ?? { disabled_added: [], write_grants_removed: [], operation_denies_added: [] };
  const changes = [[restore.disabled_added, '停用', '個工具'], [restore.write_grants_removed, '取消', '個寫入授權'],
    [restore.operation_denies_added, '禁止', '個操作']].filter(([names]) => names.length)
    .map(([names, verb, unit]) => `${verb} ${names.length} ${unit}`).join('、');
  if (!await confirmAction(restoring ? '還原升級前的限制？' : '保持全開，不再提示？',
    restoring ? `${changes ? `${changes}，` : ''}回到舊版設定允許的範圍：只保留舊設定授權過的寫入，新版新增的寫入也取消。${policyRestartsChild(state.product) ? '會重新啟動 MCP 子行程以套用，現有連線可能中斷。' : '用戶端之後的呼叫立即套用。'}`
      : `全部工具與寫入維持開啟，此通知不再顯示。${later}`,
    restoring ? '確認還原' : '確認保持全開')) return;
  await task(async () => {
    await api.mutate(`owner-defaults/${action}`, undefined, revision, profileOf(state));
    await reload(restoring ? '已還原升級前的限制。目前的設定請看「工具權限」頁。' : '已保持全開，此通知不再顯示。');
  });
}
function renderDenied(message) {
  root.replaceChildren(el('main', { class: 'blocked' }, icon('shield-account'), el('h1', {}, '管理介面無法使用'), p(message), p('請從原服務入口確認你的管理權限，再重新開啟此頁。'), button('重新檢查權限', () => task(() => reload()))));
}
const statusText = value => ({ alive: '管理服務可用', state_error: '設定儲存異常', running: '執行中', stopped: '已停止', starting: '啟動中', backoff: '退避等待', failed: '啟動失敗', not_started: '尚未啟動', unconfigured: '尚未設定', unreachable: '無法連線', reachable: '可連線', unknown: '未知' }[value] ?? '未知狀態');
function overview() {
  const health = state.health ?? {};
  const child = health.child ?? {};
  return el('div', { class: 'stack' },
    el('div', { class: 'health-grid' },
      card('管理服務', icon('monitor-dashboard'), el('h3', {}, statusText(health.management)), p('管理程序與設定儲存的狀態。')),
      card('MCP 子行程', icon('server-network'), el('h3', {}, statusText(child.state)), p(child.transport_ready === true ? '協定探測：已就緒' : '協定探測：尚未就緒'), p('不等同後端可連線。')),
      card('後端服務', icon('signal'), el('h3', {}, statusText(health.backend)), p('來自伺服器的獨立唯讀健康探測。'))),
    card('從這裡開始', p('讓你的 MCP 用戶端連上需要的服務。你可以先連線查看工具；需要後端的操作仍須完成後端設定與授權。'),
      el('div', { class: 'steps' }, ...[['01', '設定後端', '由此介面管理 URL 與憑證。', 'backend'], ['02', '檢查工具', policySummary(state), 'tools'], ['03', '連接用戶端', '明確指定 MCP 端點與 Bearer。', 'access']].map(([n, title, text, target]) => el('div', {}, el('span', { class: 'step-number' }, n), el('h3', {}, title), p(text), button('前往設定', () => navigate(target)))))),
    card('工具能力', p(catalogSummary(state.capabilities?.tools)), p(policySummary(state)), p('有效數量來自子行程工具清單與目前政策；不代表後端操作已驗證。')),
    card('目前設定', el('dl', { class: 'summary' }, el('dt', {}, '產品'), el('dd', {}, products[state.product].name), el('dt', {}, '後端連線'), el('dd', {}, state.connection_configured ? '已設定（憑證不顯示）' : '尚未設定'), el('dt', {}, 'MCP 端點'), el('dd', {}, safeEndpoint() ?? '尚未設定，無法產生可直接使用的連線'), el('dt', {}, '權杖'), el('dd', {}, state.token_active ? '有效' : '已撤銷 / 未啟用')),
      p('狀態來自最近一次管理 API 回應，不代表真實用戶端驗收。後端離線不應觸發容器持續重新啟動。')));
}
function backendTest() {
  return state.capabilities?.backend?.can_test ? button('測試已儲存的後端', () => task(async () => {
    const result = await api.mutate('backend/test', undefined, undefined, profileOf(state));
    state.health = result.health;
    notice(`已測試伺服器儲存的設定：${statusText(result.backend)}。未儲存的表單未參與測試。${result.reason ? ` ${result.reason}` : ''}`,
      result.backend !== 'reachable');
  })) : null;
}
function backend() {
  const revision = state.configuration?.revision;
  if (state.capabilities?.backend?.can_edit === false) return card('固定後端',
    chip(state.connection_configured ? '已設定' : '尚未設定'), p('後端由部署環境管理，此頁無法取代或清除。'),
    p(`後端服務：${statusText(state.health?.backend)}`), backendTest());
  const form = el('form', { autocomplete: 'off' });
  const action = el('select', { id: 'connection-action', name: 'action' },
    el('option', { value: 'preserve' }, '保留現有設定（不變更）'),
    el('option', { value: 'replace' }, '提供新值，取代整組設定'),
    el('option', { value: 'clear' }, '清除整組後端設定'));
  const fields = el('fieldset', { disabled: true, hidden: true }, el('legend', {}, '新的後端連線'));
  for (const [key, label, type] of products[state.product].fields) {
    const input = type === 'mode' ? el('select', { id: key, name: key }, el('option', { value: 'read' }, 'read — 唯讀'), el('option', { value: 'module' }, 'module — 既有 MCP 模組')) : el('input', {
      id: key, name: key, type: type.includes('secret') ? 'password' : type.includes('url') ? 'url' : 'text',
      autocomplete: type.includes('secret') ? 'new-password' : 'off', spellcheck: 'false', autocapitalize: 'none',
      maxlength: type.includes('secret') ? '8192' : type.includes('url') ? '2048' : '256',
      required: !type.startsWith('optional'), 'aria-describedby': 'connection-help',
    });
    fields.append(el('div', { class: 'field' }, el('label', { for: key }, label), input));
  }
  action.addEventListener('change', () => {
    fields.hidden = action.value !== 'replace'; fields.disabled = fields.hidden;
    if (fields.hidden) fields.querySelectorAll('input').forEach(input => input.value = '');
  });
  form.append(el('div', { class: 'field' }, el('label', { for: 'connection-action' }, '這次要如何處理設定？'), action),
    p(backendEdit(state) && state.connection_configured ? '下方可修改個別欄位並保留其餘憑證；此表單仍是整組取代，需重新輸入必要欄位。' : '保留不會送出變更。取代時請重新輸入所有必要欄位，空白不代表保留。'),
    fields, el('p', { id: 'connection-help', class: 'hint' }, state.product === 'odoo-manage' ? 'module 模式要求後端已安裝 MCP module；此介面不會安裝模組或變更 Odoo。read 模式不可保存寫入授權。' : state.product === 'hermes' ? 'Dashboard 為選填；URL、使用者、密碼需整組提供。全部留空會移除 Dashboard 設定。' : state.product === 'opendesign' ? 'OpenDesign 只需要 URL；不要求後端 token。' : [connectionHelpFor(state.product, api.profile !== null), 'URL 不可含帳密、查詢參數或片段。新憑證只用於這次提交，不儲存在瀏覽器。'].filter(Boolean).join(' ')),
    el('button', { type: 'submit', class: 'primary' }, '儲存後端設定'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    let payload;
    try { payload = backendPayload(state.product, action.value, Object.fromEntries(new FormData(form))); } catch (error) { fail(error); return; }
    if (!payload) { notice('已保留現有設定，未送出變更。'); return; }
    if (!await confirmAction(action.value === 'clear' ? '清除後端連線？' : '取代後端連線？', '此操作可能重新啟動或停止 MCP 子行程，現有連線可能中斷。舊憑證不會在介面中顯示。', '確認儲存')) { payload = null; return; }
    await task(async () => {
      let result;
      try { result = await saveForm(form, 'backend', payload, revision); }
      finally {
        payload = null;
        if (form.dataset.conflict !== 'true') fields.querySelectorAll('input[type=password]').forEach(input => input.value = '');
      }
      await reloadSaved('伺服器已確認儲存。請等待健康探測更新，這不代表後端已連線成功。', result);
    });
  });
  return card('後端連線設定', chip(state.connection_configured ? '已設定 · 憑證隱藏' : '尚未設定'), scopeNote('這是這個帳號自己的後端連線與憑證；儲存、清除與測試都只用這個帳號的設定，其他帳號不受影響。'), p('URL 與憑證由管理介面管理。測試只使用已儲存的設定，不會送出下方表單。'), state.product === 'litellm' ? p('請填 LiteLLM 閘道根網址。根路徑的 /v1 會移除；/proxy/v1 等代理掛載路徑會保留。健康探測可能產生供應商費用；token 與費用估算可能抓取圖片或分詞資源，三者都需要明確的操作權限。') : null, backendTest(), form);
}
function partialBackendCard() {
  const snapshot = state;
  const current = backendEdit(snapshot);
  if (!current || !snapshot.connection_configured || snapshot.capabilities?.backend?.can_edit === false) return null;
  const form = el('form', {id: 'backend-partial', autocomplete: 'off'});
  const controls = new Map();
  form.append(p('只送出你選擇修改的欄位，其餘設定與憑證保留。修改網址或帳號後，保留的憑證會用於新的連線，請先確認目的地。'));
  // HM-12 (DQ-40 ⑨ (a)): switched on, a URL moved to another server takes none of its stored secrets (requireMovedSecrets).
  // Review S-7 (a): said only where a URL of this product takes a secret (OpenDesign's takes none).
  const switchedOn = api.profile !== null, carriers = Object.entries(urlSecrets[snapshot.product] ?? {});
  if (switchedOn && carriers.some(([, carried]) => carried.length)) form.append(p('網址改到另一台伺服器（scheme、主機或 port 不同）時，不會沿用已儲存的密碼或金鑰：請在同一次儲存中重新輸入（選填的可以明確清除）。只改路徑時沿用已儲存的憑證。'));
  for (const [key, label, type] of products[snapshot.product].fields) {
    const secret = type.includes('secret');
    const select = el('select', {id: `patch-${key}-action`, name: `${key}-action`},
      el('option', {value: 'keep'}, secret ? current.secret_set[key] ? '保留已儲存憑證' : '保留未設定狀態' : '保留目前值'),
      el('option', {value: 'set'}, '提供新值'),
      type.startsWith('optional') ? el('option', {value: 'clear'}, '明確清除') : null);
    const input = type === 'mode' ? el('select', {id: `patch-${key}`, disabled:true}, el('option', {value:'read'}, 'read'), el('option', {value:'module'}, 'module')) : el('input', {
      id: `patch-${key}`, type: secret ? 'password' : type.includes('url') ? 'url' : 'text',
      disabled: true, autocomplete: secret ? 'new-password' : 'off',
      maxlength: secret ? '8192' : type.includes('url') ? '2048' : '256',
    });
    input.value = secret ? '' : current.values[key] ?? '';
    if (current.withheld_fields?.includes(key)) form.append(p(`${label}包含已知憑證，完整值不顯示；選「保留目前值」會保留伺服器原值。`));
    select.addEventListener('change', () => { input.disabled = select.value !== 'set'; input.required = !input.disabled; if (secret && input.disabled) input.value = ''; });
    // HM-12: (switched on) shown while this secret must be typed again because its URL moved to another server. Review
    // S-7 (b): the server withholds that URL's stored value, so any new value counts as moved: the note says so.
    const unknown = current.withheld_fields?.includes(carriers.find(([, carried]) => carried.includes(key))?.[0]) === true;
    const note = switchedOn && secret ? el('p', {id: `patch-${key}-origin`, class: 'hint', hidden: true},
      `${unknown ? '伺服器不顯示原網址，無法確認是同一台伺服器' : '網址改到另一台伺服器'}：請重新輸入${type.startsWith('optional') ? '或明確清除' : ''}，不會沿用已儲存的憑證。`) : null;
    controls.set(key, {select, input, note});
    form.append(el('div', {class:'field'}, el('label', {for:`patch-${key}-action`}, `${label}的處理方式`), select,
      el('label', {for:`patch-${key}`}, `${label}新值`), input, note));
  }
  if (switchedOn) {
    const follow = () => requireMovedSecrets(snapshot, controls);
    for (const [key, , type] of products[snapshot.product].fields) if (type.includes('url')) {
      controls.get(key).select.addEventListener('change', follow);
      controls.get(key).input.addEventListener('input', follow);
    }
  }
  form.append(el('button', {type:'submit', class:'primary'}, '儲存選定欄位'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    let payload;
    try { payload = backendPatchPayload(snapshot,
      Object.fromEntries([...controls].map(([key, c]) => [key, c.select.value])),
      Object.fromEntries([...controls].map(([key, c]) => [key, c.input.value])), switchedOn); } catch (error) { fail(error); return; }
    if (!payload) { notice('已保留全部欄位，未送出變更。'); return; }
    if (!await confirmAction('修改選定連線欄位？', '未修改的憑證將保留並用於修改後的連線。儲存會重新啟動子行程，現有連線可能中斷。', '確認儲存')) { payload = null; return; }
    await task(async () => {
      let result;
      try { result = await saveForm(form, 'backend/patch', payload, snapshot.configuration?.revision); }
      finally { payload = null; if (form.dataset.conflict !== 'true') form.querySelectorAll('input[type=password]').forEach(input => input.value = ''); }
      await reloadSaved('已儲存選定欄位，其餘設定保持不變。請查看子行程套用狀態。', result);
    });
  });
  return card('修改個別欄位，保留其餘憑證', form);
}
// HM-12 (DQ-40 ⑨ (a); contract 4.1 and section 9, HM-12's panel rows): while a URL is set to another server than the
// stored one, each stored secret it takes there must be typed again (or cleared, where it may be): its keep choice is
// turned off, the field required and a note says why. Back on the stored server, keep is offered again, and chosen again
// where this rule chose for it and nothing was typed. Switched on only (the add-on refuses such a save with 422 then).
function requireMovedSecrets(snapshot, controls) {
  const needed = newOriginSecrets(snapshot, Object.fromEntries([...controls].map(([key, c]) => [key, c.select.value])),
    Object.fromEntries([...controls].map(([key, c]) => [key, c.input.value])));
  for (const [key, {select, input, note}] of controls) {
    if (!note) continue;
    const required = needed.includes(key);
    select.querySelector('option[value=keep]').disabled = required;
    note.hidden = !required;
    if (required) input.setAttribute('aria-describedby', note.id); else input.removeAttribute('aria-describedby');
    if (required && select.value === 'keep') {
      select.value = 'set';
      select.dataset.originRequired = 'true';
      select.dispatchEvent(new Event('change'));
    } else if (!required && select.dataset.originRequired === 'true') {
      delete select.dataset.originRequired;
      if (select.value === 'set' && input.value === '') { select.value = 'keep'; select.dispatchEvent(new Event('change')); }
    }
  }
}
function n8nSessionCard() {
  const snapshot = state, current = n8nSession(snapshot);
  if (!current || !snapshot.configuration?.revision) return null;
  const form = el('form', {id:'n8n-session'});
  form.append(p('管理 n8n 原生 MCP 子行程的閒置逾時與連線上限。儲存後會重新啟動子行程。'),
    p(snapshot.n8n_session_source === 'legacy_default' ? '沿用既有 HA 預設：600 秒（10 分鐘）／20 個連線。' : '目前顯示已儲存的設定。'));
  const seconds = el('input', {id:'session-timeout', type:'number', min:'60', max:'86400', step:'1', required:true, value:current.timeout_seconds});
  const count = el('input', {id:'session-max', type:'number', min:'1', max:'100', step:'1', required:true, value:current.max_sessions});
  const actual = p('');
  const update = () => { actual.textContent = `子行程採整數分鐘：向上換算為 ${Math.ceil(Number(seconds.value) / 60)} 分鐘；原生清掃週期可能再延後回收。`; };
  seconds.addEventListener('input', update); update();
  form.append(el('div', {class:'field'}, el('label', {for:'session-timeout'}, '閒置逾時（秒）'), seconds),
    el('div', {class:'field'}, el('label', {for:'session-max'}, '最大連線數'), count), actual,
    el('button', {type:'submit', class:'primary'}, '儲存 n8n 連線設定'));
  form.addEventListener('submit', async event => {
    event.preventDefault(); let payload;
    try { payload = n8nSessionPayload(snapshot, {timeout_seconds:seconds.value, max_sessions:count.value}); } catch (error) { fail(error); return; }
    if (!await confirmAction('套用 n8n 連線設定？', '會重新啟動子行程並關閉既有原生連線，其他工具授權與後端憑證不變。', '確認套用')) return;
    await task(async () => { await saveForm(form, 'n8n/session', payload, snapshot.configuration.revision); await reload('已儲存 n8n 連線設定。請查看子行程套用狀態。'); });
  });
  return card('n8n 原生連線設定', form);
}

function tools() {
  const snapshot = state;
  const revision = snapshot.configuration?.revision;
  const granular = granularPolicy(snapshot);
  const operationControls = operationPolicy(snapshot);
  const form = el('form');
  const rows = toolRows(snapshot);
  form.append(p('停用與授權必須由伺服器逐次檢查 tools/call。此頁的控制項不是安全邊界，也不會替你執行工具。'));
  if (!granular) form.append(el('div', { class: 'notice' }, '工具授權版本不相容，無法儲存。請重新整理；不會以舊版全域開關取代精確授權。'));
  form.append(el('div', { class: 'notice' }, policySummary(snapshot)), p('已允許的寫入可新增、修改或刪除後端資料。下方勾選需儲存後才套用；後端帳號權限仍會限制操作。'));
  if (operationControls) {
    form.append(p('你可以禁止個別讀取或寫入操作。取消禁止不會新增寫入授權；寫入仍需另行授權。'));
    const stale = staleOperationDenies(snapshot);
    if (stale.length) form.append(p(`保留未列於目前操作目錄的限制：${stale.map(({tool, operation}) => `${tool}:${operation}`).join('、')}。儲存此頁會保留這些限制。`));
  }
  if (snapshot.writes_enabled && rows.some(row => row.legacy)) form.append(p('注意：伺服器回報舊版全域寫入目前開啟（新安裝的預設）。此頁不將它標示為唯讀；儲存後改以下方逐項勾選為準，未勾選的寫入即關閉。'));
  if (!rows.length) form.append(p('伺服器未提供工具清單，無法編輯權限。'));
  const catalog = snapshot.capabilities?.tools;
  const details = new Map((catalog?.items ?? []).map(item => [item.name, item]));
  const search = el('input', { id: 'tool-search', type: 'search', placeholder: '名稱、說明或操作', autocomplete: 'off' });
  const found = p('');
  found.setAttribute('aria-live', 'polite');
  const entries = [];
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    for (const [node, text] of entries) node.hidden = !text.includes(query);
    found.textContent = `顯示 ${entries.filter(([node]) => !node.hidden).length} / ${entries.length} 個工具`;
  });
  form.append(el('div', { class: 'field' }, el('label', { for: 'tool-search' }, '搜尋工具'), search), found);
  const extra = [...details.keys()].filter(name => !rows.some(row => row.name === name)).map(name => ({ name, operations: [], classified: false }));
  for (const row of [...rows, ...extra]) {
    const disabled = el('input', { type: 'checkbox', name: 'disabled', value: row.name, checked: snapshot.disabled?.includes(row.name), disabled: !snapshot.tools?.[row.name] });
    const controls = el('div', { class: 'tool-controls' }, el('label', { class: 'check' }, disabled, '停用此工具'));
    const operations = row.operations.length ? row.operations : row.write ? [null] : [];
    for (const operation of operations) {
      const value = JSON.stringify({ tool: row.name, operation });
      controls.append(el('label', { class: 'check' }, el('input', { type: 'checkbox', name: 'grant', value,
        checked: granular && !disabled.checked && savedGrant(snapshot, row, operation),
        disabled: !granular || !row.classified || disabled.checked,
      }), operation === null ? '明確允許此工具寫入' : `允許寫入操作：${operation}`));
    }
    disabled.addEventListener('change', () => controls.querySelectorAll('[name=grant]').forEach(input => {
      input.disabled = disabled.checked || !granular || !row.classified;
      if (disabled.checked) input.checked = false;
    }));
    if (operationControls) {
      for (const operation of row.auditedOperations ?? []) {
        controls.append(el('label', { class: 'check' }, el('input', { type: 'checkbox', name: 'deny-operation',
          value: JSON.stringify({tool: row.name, operation: operation.name}),
          checked: snapshot.denied_operations[row.name]?.includes(operation.name),
        }), `禁止${operation.write ? '寫入' : '讀取'}操作：${operation.name}`));
      }
      if (row.auditedOperations?.length) controls.append(p(`操作參數：${snapshot.tools[row.name].operation_parameter}；省略時：${snapshot.tools[row.name].default_operation ?? '必須提供操作'}。`));
    }
    const detail = details.get(row.name);
    const conditional = detail?.conditional_writes ?? [];
    const effective = detail?.effective === true ? '子行程有效' : detail?.effective === false ? '未生效' : '有效狀態未知';
    const reasons = { policy_disabled: '政策停用', write_not_granted: '未授權寫入', operations_not_permitted: '所有操作皆被政策禁止', child_unavailable: '未能取得子行程工具清單', not_registered_by_child: '子行程未註冊', not_in_registry: '尚未納入核准目錄' };
    const schema = detail?.inputSchema ?? snapshot.tools?.[row.name]?.inputSchema;
    const article = el('article', { class: 'tool-row' }, el('div', {}, el('h3', { class: 'tool-name' }, row.name),
      chip(!row.classified ? '分類未知 · 不提供授權' : conditional.length ? '含條件寫入' : operations.length ? '含寫入操作' : '唯讀'),
      p(detail?.description || '此目錄沒有提供工具說明。'), p(`${effective}${detail?.reason ? ` · ${reasons[detail.reason] ?? '未知原因'}` : ''}`),
      ...conditional.map(rule => el('div', { 'aria-label': `${row.name} 條件寫入` },
        el('h4', {}, '條件寫入'), p(conditionalWriteSummary(rule)),
        p('即使所選操作是讀取，仍會額外寫入。false 或省略不觸發這項額外檢查，原工具與操作權限仍須允許。'),
        p('請明確允許相依工具寫入，並確認它未停用、沒有禁止操作。此條件不新增獨立授權；儲存後對新呼叫立即生效，後端權限仍可能限制存取。'))),
      el('details', {}, el('summary', {}, '工具參數與操作詳情'),
        p(`參數來源：${({ child: '目前子行程', pinned: '隨版本保存的工具快照', registry: '管理登錄' })[detail?.schema_source] ?? '管理登錄'}`),
        ...(detail?.operations ?? []).map(op => p(operationSummary(op))),
        el('pre', { tabindex: '0', 'aria-label': `${row.name} inputSchema` }, el('code', {}, schema ? JSON.stringify(schema, null, 2) : '尚未取得參數定義。')))), controls);
    entries.push([article, `${row.name} ${detail?.description ?? ''} ${JSON.stringify(conditional)} ${(detail?.operations ?? []).map(op => op.name).join(' ')}`.toLocaleLowerCase()]);
    form.append(article);
  }
  form.append(el('button', { type: 'submit', class: 'primary', disabled: !rows.length || !granular }, '儲存工具權限'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const data = new FormData(form);
    const denies = operationControls ? data.getAll('deny-operation').map(v => JSON.parse(v)) : undefined;
    try { policyPayload(snapshot, data.getAll('disabled'), data.getAll('grant').map(v => JSON.parse(v)), denies); } catch (error) { fail(error); return; }
    if (!await confirmAction('套用工具權限？', '寫入可能變更後端資料。只授權你確實需要的工具或操作；伺服器仍必須強制檢查每次呼叫。' + policyRestartNotice(state.product, api.profile !== null), '確認套用')) return;
    const expectedPolicy = policyFingerprint(snapshot);
    await task(async () => {
      await saveForm(form, 'policy', fresh => {
        // If-Match binds saved state, not the runtime tool/grant definitions.
        // A valid configuration revision must not bypass this contract check.
        if (policyFingerprint(fresh) !== expectedPolicy) throw new UiError('工具授權版本已變更。請重新整理後再試。');
        return policyPayload(snapshot, data.getAll('disabled'), data.getAll('grant').map(v => JSON.parse(v)), denies);
      }, revision);
      await reload('伺服器已確認儲存工具權限。此頁未執行任何工具。');
    });
  });
  return card('工具與寫入授權', scopeNote('這裡的停用、寫入授權與操作禁止只套用到這個帳號的權杖；其他帳號各自設定。'), p(catalog ? catalogSummary(catalog) : `${rows.length} 個管理登錄工具`), form);
}
function odooSwitchCard() {
  const snapshot = state;
  const current = odooSwitches(snapshot);
  const revision = snapshot.configuration?.revision;
  if (!current || !revision) return card('Odoo 子操作開關',
    el('div', {class: 'notice'}, '此管理 API 尚未提供完整的四開關設定與版本。請更新伺服器後再編輯；目前不會送出變更。'));
  const options = [
    ['enable_writes', '啟用 Odoo 寫入總閘門', '關閉後 execute_method 只允許審核過的讀取方法；chatter_post 與 execute_approved_write 都拒絕。preview_write、validate_write 可預覽，但核准不能執行。'],
    ['allow_direct_writes', '允許 execute_method 直接寫入', '關閉後 create、write、unlink 必須走 preview_write → validate_write → execute_approved_write；其他未審查方法也會拒絕。'],
    ['allow_unknown_methods', '允許未審查方法', '關閉後未審查的 action_*、get_* 等方法會拒絕。只有總閘門與直接寫入也開啟時，這個開關才會放行未審查方法。'],
    ['chatter_direct', '允許直接張貼 Chatter', '關閉後 chatter_post 先回預覽，需同參數與核准、confirm=true 才張貼；execute_method 的明確訊息張貼呼叫也會拒絕。其他業務方法自動產生的追蹤訊息仍由其方法權限管理。'],
  ];
  const form = el('form');
  form.append(p('這四項只會收緊 Odoo 子行程。外層「工具權限」中的工具、寫入 grant 與操作禁止仍分別生效；開啟此處的開關不會授予外層權限。若外層未授權 execute_method，該工具的審核讀取也無法呼叫。'),
    p(odooMethods(snapshot) ? '下方「Odoo 精確方法允許清單」可逐一加入已審查方法；清單不會繞過寫入總閘門、Chatter 限制或外層授權。' : '此伺服器尚未提供精確 model.method 清單編輯，請更新後再使用單一方法的例外放行。'),
    p(snapshot.odoo_write_switches_source === 'legacy_all_on'
      ? '此既有設定沒有四開關欄位；沿用先前子行程的四項全開值。既有停用與撤銷權限仍保留。'
      : '畫面顯示已儲存的子行程設定；儲存後會重啟子行程，請查看上方套用狀態。'));
  for (const [key, label, description] of options) {
    form.append(el('div', {class: 'field'},
      el('label', {class: 'check'}, el('input', {type: 'checkbox', name: key, checked: current[key]}), label),
      p(description)));
  }
  form.append(el('button', {type: 'submit', class: 'primary'}, '儲存 Odoo 子操作開關'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const values = Object.fromEntries(odooSwitchKeys.map(key => [key, form.elements.namedItem(key).checked]));
    try { odooSwitchPayload(snapshot, values); } catch (error) { fail(error); return; }
    if (!await confirmAction('套用 Odoo 子操作開關？', '變更後會重啟 Odoo 子行程。開啟寫入仍需外層工具授權與 Odoo 帳號權限。', '確認套用')) return;
    await task(async () => {
      await saveForm(form, 'odoo/write-switches', fresh => {
        if (JSON.stringify(odooSwitches(fresh)) !== JSON.stringify(current)) throw new UiError('子操作開關已被其他操作更新。請重新整理後再試。');
        return odooSwitchPayload(fresh, values);
      }, revision);
      await reload('伺服器已確認儲存 Odoo 子操作開關。請查看子行程套用狀態。');
    });
  });
  return card('Odoo 子操作開關', form);
}
function odooMethodsCard() {
  const snapshot = state, current = odooMethods(snapshot);
  if (!current || !snapshot.configuration?.revision) return null;
  const form = el('form', {id:'odoo-allowed-methods'});
  const input = el('textarea', {id:'odoo-method-list', rows:'7', maxlength:'16384', spellcheck:'false', autocomplete:'off'});
  input.value = current.join('\n');
  form.append(p('逐一允許已審查的 model.method，例如 sale.order.action_confirm；每行一項、最多 128 項，不接受 * 或私有方法。空白清單表示沒有額外例外。'),
    p('這份清單只提供精確方法的例外。外層工具授權、寫入總閘門與 Chatter 限制仍生效；create、write、unlink 仍受直接寫入開關控制。'),
    p(snapshot.odoo_write_switches?.allow_unknown_methods && snapshot.odoo_write_switches?.allow_direct_writes && snapshot.odoo_write_switches?.enable_writes
      ? '目前「允許未審查方法」與直接寫入都開啟，因此不在清單上的方法也可能執行。要只開放已審查方法，請另行關閉「允許未審查方法」。'
      : '未列入清單的方法仍依四項子操作開關判定；已審核的讀取方法維持可用。'),
    el('div', {class:'field'}, el('label', {for:'odoo-method-list'}, '允許的 Odoo 方法（每行 model.method）'), input),
    el('button', {type:'submit', class:'primary'}, '儲存 Odoo 方法清單'));
  form.addEventListener('submit', async event => {
    event.preventDefault(); let payload;
    try { payload=odooMethodsPayload(snapshot,input.value); } catch (error) { fail(error); return; }
    if (!await confirmAction('套用 Odoo 方法清單？', '儲存會重啟子行程。列入清單的方法仍須外層工具授權與 Odoo 帳號權限，未審查方法開關不會自動變更。', '確認套用')) return;
    await task(async () => { await saveForm(form,'odoo/allowed-methods',payload,snapshot.configuration.revision); await reload('已儲存 Odoo 精確方法清單。請查看子行程套用狀態。'); });
  });
  return card('Odoo 精確方法允許清單', form);
}

function safeEndpoint() { try { return state.endpoint ? explicitUrl(state.endpoint, true) : null; } catch { return null; } }
async function copy(text) {
  try { await navigator.clipboard.writeText(text); notice('已複製。若包含權杖，請在使用後清除剪貼簿。'); }
  catch { notice('瀏覽器未允許剪貼簿。請手動選取並複製；未自動轉往其他服務。', true); }
}
async function tokenAction(action) {
  const revision = state.configuration?.revision;
  const descriptions = {
    reveal: ['顯示目前權杖？', '權杖將在此頁短暫顯示 60 秒，切換頁面或離開視窗即隱藏。請避免螢幕分享。'],
    claude: ['顯示 Claude.ai 連線網址？', '這個網址含有真實權杖，等同密碼：只貼進 Claude.ai 的自訂連接器設定，不要分享、截圖或貼到聊天。網址將短暫顯示 60 秒，切換頁面或離開視窗即隱藏。'],
    'claude-rotate': ['產生新的 Claude.ai 連線網址？', '這會重新產生權杖，使舊權杖與舊連線網址立即失效，所有用戶端都需更新。新網址僅短暫顯示。'],
    rotate: ['重新產生權杖？', '舊權杖立即失效，使用舊權杖的進行中連線將關閉，所有用戶端都需更新。已送出的後端工作不會因此復原。新權杖僅短暫顯示。'],
    revoke: ['撤銷權杖？', '用戶端將無法使用此權杖連線，進行中連線也會關閉。已送出的工作不會回復；需重新產生權杖才能恢復存取。'],
  };
  const profile = profileOf(state);
  hideToken();
  if (!await confirmAction(...descriptions[action], action === 'revoke' ? '確認撤銷' : '確認繼續')) return;
  const epoch = revealEpoch;
  await task(async () => {
    const operation = action === 'claude' ? 'reveal' : action === 'claude-rotate' ? 'rotate' : action;
    const result = await api.mutate(`token/${operation}`, undefined,
      ['rotate', 'revoke'].includes(operation) ? revision : undefined, profile);
    if (result?.operation?.replayed) { await reload(state.product === 'headscale' ? '已確認先前操作完成，沒有再次執行。需要權杖時請重新產生，這會使目前權杖失效。' : '已確認先前操作完成，沒有再次執行。需要時請另按「顯示權杖」取得目前權杖。'); return; }
    if (action === 'revoke') { await reload('權杖已撤銷。舊權杖不可再使用，進行中連線已收到關閉通知；已送出的後端工作不會回復。'); return; }
    state = await api.bootstrap();
    render();
    if (!result?.token) { notice('目前沒有有效權杖。請確認伺服器狀態。', true); return; }
    if (typeof result.token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(result.token)) throw new UiError('權杖回應格式不符，未顯示。');
    if (epoch !== revealEpoch || document.hidden) { notice(state.product === 'headscale' ? '操作已完成，但頁面曾離開焦點，權杖未顯示。需要權杖時請重新產生，這會使目前權杖失效。' : '操作已完成，但頁面曾離開焦點，權杖未顯示。需要時請重新要求顯示。'); return; }
    if (action === 'claude' || action === 'claude-rotate') {
      const url = claudeConnectorUrl(safeEndpoint(), result.token);
      revealed = url;
      const area = document.querySelector('#claude-secret');
      area.hidden = false;
      area.replaceChildren(p('60 秒後自動隱藏；剪貼簿不會自動清除。網址外洩時請按「重新產生」，舊網址立即失效。'), el('code', { class: 'secret' }, url), el('div', { class: 'actions' }, button('複製 Claude.ai 連線網址', () => revealed && copy(revealed)), button('立即隱藏', hideToken)));
      revealTimer = setTimeout(hideToken, 60000);
      return;
    }
    revealed = result.token;
    const area = document.querySelector('#token-secret');
    area.hidden = false;
    area.replaceChildren(p('60 秒後自動隱藏；剪貼簿不會自動清除。'), el('code', { class: 'secret' }, revealed), el('div', { class: 'actions' }, button('複製權杖', () => revealed && copy(revealed)), button('複製含權杖範例', async () => {
      if (await confirmAction('複製含權杖範例？', '這份範例會包含真實權杖。不要貼到聊天、Git 或公開文件。') && revealed) await copy(clientExample(safeEndpoint(), revealed, clientName(state.product, api.profile)));
    }), button('立即隱藏', hideToken)));
    revealTimer = setTimeout(hideToken, 60000);
  });
}
function access() {
  const revision = state.configuration?.revision;
  const endpoint = safeEndpoint();
  const history = tokenHistory(state);
  const currentMask = maskedCurrentToken(state);
  const name = clientName(state.product, api.profile);
  const input = el('input', { id: 'endpoint', name: 'endpoint', type: 'url', value: endpoint ?? '', placeholder: 'https://YOUR-MCP-HOST:PORT/mcp', autocomplete: 'off', required: true, 'aria-describedby': 'endpoint-help' });
  const form = el('form', {}, el('div', { class: 'field' }, el('label', { for: 'endpoint' }, 'MCP 用戶端端點'), input), el('p', { id: 'endpoint-help', class: 'hint' }, '明確填寫用戶端可到達的 /mcp URL，不是 Ingress 網址。不會由此頁的網域推測；這裡不要放權杖（Claude.ai 用的含權杖網址由下方另外產生）。'), el('div', { class: 'actions' }, el('button', { type: 'submit', class: 'primary' }, '儲存端點'), button('清除端點', async () => {
    if (await confirmAction('清除 MCP 端點？', '只清除用戶端連線範例的端點設定，不會撤銷權杖。')) await task(async () => { await saveForm(form, 'endpoint', { endpoint: null }, revision); await reload('已清除端點。'); });
  })));
  form.addEventListener('submit', event => {
    event.preventDefault();
    let value;
    try { value = explicitUrl(input.value, true); } catch (error) { fail(error); return; }
    task(async () => { await saveForm(form, 'endpoint', { endpoint: value }, revision); await reload('MCP 端點已儲存。這不代表網路可達性已驗證。'); });
  });
  // HM-11 (DQ-13; FM-12): the endpoint is the add-on's, kept by the default profile; an additional profile shows it.
  const endpointCard = isExtraProfile(api.profile) ? card('連線端點（全 add-on 共用）', chip(endpoint ? '已設定端點' : '尚未設定'),
    endpoint ? el('p', {}, el('code', {}, endpoint)) : p('尚未設定端點。'),
    p('端點是整個 add-on 共用的設定，只能在預設帳號修改。這個帳號的 MCP 網址＝共用端點＋這個帳號自己的權杖。'))
    : card('明確設定你的連線端點', chip(endpoint ? '已設定端點' : '尚未設定'), form);
  // HM-13c (contract 4.1 restore_review_required): a profile whose token the restore guard revoked gets a new one once
  // it was reviewed on the default profile's review card; the server refuses it until then (409).
  const gated = state.restore_review_required === true;
  return el('div', { class: 'stack' }, endpointCard,
    card('MCP 權杖', chip(state.token_active ? '有效 · 預設隱藏' : '已撤銷 / 未啟用'), p(api.profile === null ? '每個 MCP 服務共用一把 Bearer 權杖。權杖不是管理員密碼，也不會授予管理介面權限。'
      : state.product === 'headscale' ? '這個帳號有自己的一把 Bearer 權杖；重新產生或撤銷只影響這個帳號。權杖不是管理員密碼，也不會授予管理介面權限。'
        : '這個帳號有自己的一把 Bearer 權杖；顯示、重新產生或撤銷只影響這個帳號。權杖不是管理員密碼，也不會授予管理介面權限。'),
      currentMask && state.token_active ? p(`目前權杖（遮罩）：${currentMask}`) : null,
      gated ? el('p', { id: 'restore-review-required' }, '這個帳號是從備份還原（或休眠）回來的，還沒有核對：請先到預設帳號頁的核對卡確認它的設定並按「已核對」，才能重新產生權杖。') : null,
      el('div', { class: 'actions' }, state.product === 'headscale' ? null : button('顯示權杖', () => tokenAction('reveal'), { disabled: !state.token_active }), button('重新產生', () => tokenAction('rotate'), { disabled: gated }), button('撤銷權杖', () => tokenAction('revoke'), { disabled: !state.token_active })), el('div', { id: 'token-secret', class: 'secret-box', hidden: true, 'aria-live': 'polite' })),
    card('最近權杖變更', history === null ? p('權杖歷史格式不相容；請重新整理或更新附加元件。') :
      history.length ? el('ul', { id: 'token-history' }, ...history.map(item => el('li', {},
        `${item.action === 'rotate' ? '重新產生' : '撤銷'} · `,
        el('time', { datetime: item.rotated_at }, item.rotated_at), ' · ',
        el('code', {}, item.previous_token_masked || '先前沒有權杖')))) : p('尚無記錄；舊版操作不會補記。')),
    card('Claude.ai 自訂連接器', chip(endpoint && state.token_active ? '可產生 · 預設隱藏' : '尚無法產生'),
      p('Claude.ai 網頁版的自訂連接器無法帶 Authorization header，改用含權杖的專屬網址：在 Claude.ai 新增自訂連接器時貼進伺服器網址欄位，OAuth 進階設定留空。Claude.ai 從網際網路連線，上方端點必須是它連得到的 HTTPS 網址。'),
      p(`這個網址等同密碼：任何拿到網址的人都能以${api.profile === null ? '本 MCP 服務' : '這個帳號'}的權限呼叫工具。只貼進 Claude.ai，不要分享、截圖或貼到聊天、Git；外洩或不再使用時請按上方「重新產生」或「撤銷權杖」，舊網址立即失效。`),
      endpoint ? null : p(isExtraProfile(api.profile) ? '尚未設定 MCP 用戶端端點：端點是全 add-on 共用的設定，請切到預設帳號，填寫 Claude.ai 可從網際網路連到的 https://…/mcp 網址並儲存，才能產生連線網址。'
        : '尚未設定 MCP 用戶端端點：請先在上方填寫 Claude.ai 可從網際網路連到的 https://…/mcp 網址並儲存，才能產生連線網址。'),
      endpoint && !state.token_active && state.product !== 'headscale' ? p('權杖已撤銷或未啟用：請先按「重新產生」。') : null,
      state.product === 'headscale' ? p('產生連線網址會重新產生權杖，並使原有連線失效。') : null,
      el('div', { class: 'actions' }, state.product === 'headscale'
        ? button('產生新的 Claude.ai 連線網址', () => tokenAction('claude-rotate'), { disabled: !endpoint || gated })
        : button('顯示 Claude.ai 連線網址', () => tokenAction('claude'), { disabled: !endpoint || !state.token_active })),
      el('div', { id: 'claude-secret', class: 'secret-box', hidden: true, 'aria-live': 'polite' })),
    originApplies() ? originPolicyCard() : null,
    card('手動加入 MCP 用戶端', p('適用支援 Streamable HTTP 的用戶端；欄位名稱依用戶端而異。先填端點，再於用戶端安全地填入 Bearer。未驗證所有用戶端相容性。'),
      endpoint ? null : p('以下端點只是佔位文字，不能直接連線。'), el('pre', { tabindex: '0', 'aria-label': '不含真實權杖的連線範例' }, el('code', {}, clientExample(endpoint, null, name))), button('複製佔位範例', () => copy(clientExample(endpoint, null, name))), p('一般複製永遠使用 <YOUR_ADDON_TOKEN> 佔位文字，不含真實權杖。建議跨主機連線使用 HTTPS。')));
}
// HM-27 (DQ-11 (a); contract 2.6, 3.1, 3.5): the add-on's one Origin policy of the secret path, on the connections page of
// every profile once the server serves profiles (Headscale keeps its own rule and has none). It is read each time the
// page is drawn; an answer for a page drawn since, or for a profile switched away from, is dropped. Switched off
// nothing of it is drawn or asked for.
const originApplies = () => api.profile !== null && state?.product !== 'headscale';
const ORIGIN_MODE_LABELS = { 'report-only': '只記錄（report-only）', enforce: '阻擋（enforce）' };
let originViews = 0;
function originPolicyCard() {
  const body = el('div', { id: 'origin-policy-body', 'aria-live': 'polite' }, p('正在讀取來源檢查設定…'));
  loadOriginPolicy(++originViews, body);
  return el('section', { class: 'card', id: 'origin-policy', 'aria-labelledby': 'origin-policy-title' },
    el('h2', { id: 'origin-policy-title' }, '瀏覽器來源檢查（全 add-on 共用）'),
    p('這份設定只看密鑰網址（Claude.ai 用的含權杖網址 …/private_<權杖>/mcp）收到、帶 Origin 標頭的請求，所有帳號共用一份。沒帶 Origin 的用戶端（Claude Code 等原生用戶端）不受影響；Bearer 接法（/mcp）帶 Origin 一律拒絕（403），不受這裡影響。這裡不會加任何 CORS 標頭。'),
    body);
}
async function loadOriginPolicy(view, body) {
  let policy;
  try { policy = await api.originPolicy(); }
  catch (error) {
    if (view !== originViews || !body.isConnected || error instanceof StaleProfileError) return;
    if (error instanceof ApiError && [401, 403].includes(error.status)) { fail(error); return; }
    body.replaceChildren(p(`來源檢查設定無法讀取：${error instanceof UiError ? error.message : '管理服務無法使用。'}`),
      el('div', { class: 'actions' }, button('重新讀取來源檢查設定', () => { if (!busy) loadOriginPolicy(++originViews, body); })));
    return;
  }
  if (view !== originViews || !body.isConnected) return;
  body.replaceChildren(...originPolicyView(policy));
}
function originPolicyView(policy) {
  const unusable = policy.state === 'unusable';
  const mode = policy.mode ?? 'report-only', origins = policy.origins ?? [...DEFAULT_ORIGINS];
  const status = unusable ? '來源檢查設定檔無法讀取（可能在 add-on 之外被修改或損壞）：密鑰網址的 MCP 請求暫停服務（503），直到在這裡儲存新的設定。下方已填入預設值（只記錄、https://claude.ai），儲存後會取代那個檔。'
    : policy.state === 'default' ? '目前是預設值（還沒儲存過）：只記錄，清單只有 https://claude.ai。'
      : `目前：${ORIGIN_MODE_LABELS[mode]}，清單 ${origins.length} 個來源。`;
  const radio = (value, label) => el('label', { class: 'check' }, el('input', { type: 'radio', name: 'origin-mode', value, checked: value === mode }), label);
  const list = el('textarea', { id: 'origin-list', rows: '4', maxlength: '5200', spellcheck: 'false', autocomplete: 'off', 'aria-describedby': 'origin-list-help' });
  list.value = origins.join('\n');
  const form = el('form', { id: 'origin-policy-form' },
    el('fieldset', {}, el('legend', {}, '清單外的來源怎麼處理'),
      radio('report-only', '只記錄（預設）：清單外的來源照常服務，回應不變；add-on 日誌記一行 decision=would_deny（帶帳號 id 前 8 碼，每個帳號每分鐘有上限）'),
      radio('enforce', '阻擋：清單外的來源回 403；add-on 日誌記一行 decision=deny')),
    el('div', { class: 'field' }, el('label', { for: 'origin-list' }, '允許的來源（每行一個）'), list),
    el('p', { id: 'origin-list-help', class: 'hint' }, '精確的 http(s) 來源：scheme://主機[:port]，例如 https://claude.ai；不接受 *、null、路徑、尾端斜線、帳密或查詢參數。最多 16 個，大小寫與預設 port 不同的視為同一個；清單可以是空的。「清單外」也包括 null、重複或格式不符的 Origin。'),
    policy.revision === null ? p('伺服器沒有回傳這份設定的版本資訊，暫時不能儲存；請重新整理狀態。') : null,
    el('button', { type: 'submit', class: 'primary', disabled: policy.revision === null }, '儲存來源檢查設定'));
  form.addEventListener('submit', event => { event.preventDefault(); saveOrigins(form, list, policy); });
  return [chip(unusable ? '設定檔無法使用' : ORIGIN_MODE_LABELS[mode]), p(status),
    p('切換到「阻擋」之前，請先在 add-on 日誌查 decision=would_deny 的紀錄，確認需要的來源都在清單裡；一筆紀錄只說明有人送了這個 Origin，不證明是誰送的。'), form];
}
const savedOrigins = saved => saved.replayed ? '已確認先前的來源檢查設定已儲存；沒有再次執行。'
  : `已儲存來源檢查設定：${ORIGIN_MODE_LABELS[saved.mode]}，清單 ${saved.origins.length} 個來源。所有帳號的密鑰網址都套用這份設定。`;
async function saveOrigins(form, list, policy) {
  if (busy || policy.revision === null) return;
  const mode = form.querySelector('input[name=origin-mode]:checked')?.value;
  let origins;
  try { origins = originList(list.value); } catch (error) { fail(error); return; }
  const enforce = mode === 'enforce';
  if (!await confirmAction(enforce ? '儲存來源檢查設定：阻擋？' : '儲存來源檢查設定：只記錄？',
    enforce ? `清單外的來源（含 null、重複或格式不符的 Origin）會收到 403，所有帳號的密鑰網址都一樣；清單 ${origins.length} 個來源。切換前請先在 add-on 日誌查 decision=would_deny，把需要的來源加入清單；沒帶 Origin 的用戶端不受影響。`
      : `清單外的來源照常服務、回應不變，只在 add-on 日誌記一行 decision=would_deny；清單 ${origins.length} 個來源。所有帳號的密鑰網址都套用這份設定。`, '確認儲存')) return;
  await saveOriginPolicy(() => api.saveOriginPolicy(mode, origins, policy.revision), '這次沒有儲存');
}
// A save or its resend; config_conflict (the policy changed since it was read: refused before its intent) reads the
// page again and says so.
async function saveOriginPolicy(send, unsaved) {
  let conflict = false;
  await task(async () => {
    let saved;
    try { saved = await send(); }
    catch (error) {
      if (error instanceof ApiError && error.code === 'config_conflict') { conflict = true; return; }
      throw error;
    }
    await reload(savedOrigins(saved));
  });
  if (conflict) await task(() => reload(`來源檢查設定已被其他操作更新，${unsaved}；已重新讀取，請確認後再儲存。`, true));
}
function pendingOriginOperationCard() {
  const pending = api.pendingOriginOperation();
  if (!pending) return null;
  const what = `儲存來源檢查設定（${ORIGIN_MODE_LABELS[pending.mode]}，清單 ${pending.allowed_origins.length} 個來源）`;
  return el('section', { class: 'card', id: 'pending-origin-operation' }, el('h2', {}, '來源檢查設定尚未確認'),
    p(`${what}尚未取得完成確認。此分頁已保留原操作識別碼，重新載入也不會自動重送。`),
    p('請先到「連線與權杖」看「瀏覽器來源檢查」目前的設定。以原識別碼重送時，已完成的操作只回傳收據，不會再做一次。'),
    el('div', { class: 'actions' }, button('重送來源設定', async () => {
      if (!await confirmAction('以原識別碼重送來源設定？', `${what}。已完成的操作只回傳收據；結果未知的操作不會再次執行。`)) return;
      await saveOriginPolicy(() => api.retryOriginOperation(), '原本那筆沒有儲存');
    }), button('已核對來源設定', async () => {
      if (!await confirmAction('結束這筆來源設定的追蹤？', '請先核對「瀏覽器來源檢查」目前的設定。這只清除此分頁的識別紀錄，不會復原或證明先前操作未執行。')) return;
      await task(async () => { api.acknowledgeOriginOperation(); await reload('已結束此分頁的來源設定追蹤。'); });
    })));
}
// DQ-14: the orphans, listed for deletion (on this page whichever profile is shown: they are the add-on's).
function orphansCard() {
  const ids = api.profile === null ? [] : profiles?.orphans ?? [];
  if (!ids.length) return null;
  return el('section', { class: 'card', id: 'profile-orphans' }, el('h2', {}, '孤兒帳號資料'),
    p('這些帳號資料不在帳號索引裡（例如隔離帳號索引後留下的，或刪除時沒有刪乾淨的）：不會服務 MCP 請求，也不會自動刪除。確認不再需要後可以逐一刪除；刪除前會先撤銷它的權杖並抹除後端憑證。'),
    profiles.revision === null ? p('帳號清單目前不能變更，暫時無法刪除。') : null,
    el('ul', { class: 'orphan-list' }, ...ids.map(id => el('li', {}, el('span', {}, `帳號資料（${shortId(id)}）`),
      button('刪除', () => deleteOrphan(id), { disabled: profiles.revision === null, 'aria-label': `刪除孤兒帳號資料（${shortId(id)}）` })))));
}
function diagnostics() {
  const revision = state.configuration?.revision;
  const features = state.capabilities?.capabilities ?? {};
  const viewer = el('div', { 'aria-live': 'polite' }, p('按下讀取，取得目前保留的日誌。'));
  const history = ownerDefaults();
  const row = currentRow();
  return el('div', { class: 'stack' }, history && !history.notice && !history.malformed ? ownerDefaultsCard(history) : null, orphansCard(), quarantinedCard(), revokeAllCard(), exportCard(), card('子行程維護', api.profile === null ? null
    : p(`這是帳號${named(row, api.profile)}的子行程${row?.port ? `（port ${row.port}）` : ''}；重新啟動與日誌都只看這個帳號。`), p(`目前狀態：${statusText(state.health?.child?.state)}`),
    p('重新啟動會中斷子行程的現有連線；後端、政策與權杖設定會保留。'),
    features.restart_child ? button('重新啟動子行程', async () => {
      if (!await confirmAction('重新啟動 MCP 子行程？', '現有連線可能中斷。啟動請求完成後仍需等候協定與後端探測。', '確認重新啟動')) return;
      await task(async () => { await api.mutate('child/restart', undefined, revision, profileOf(state)); await reload('已接受重新啟動請求。請重新整理健康狀態，確認子行程是否就緒。'); });
    }) : p('此部署未提供子行程重新啟動。')),
  card('子行程日誌', p('僅保留記憶體內最近 200 筆、最多 128 KiB；過長行會捨棄，憑證在保留前遮蔽。此處不包含完整歷史或後端服務日誌。'),
    features.logs ? button('讀取診斷日誌', () => task(async () => {
      const result = await api.diagnostics();
      const logs = result.logs;
      if (!Array.isArray(logs?.entries) || logs.redacted !== true) throw new UiError('診斷格式不符，未顯示。');
      const listenerText = { unknown: '尚未檢查', owned: '目前符合', mismatch: '不符合，已拒絕轉送', absent: '沒有監聽', unavailable: '不可用，仍使用子行程權杖' }[result.listener_identity];
      viewer.replaceChildren(...(listenerText ? [p(`監聽程序檢查：${listenerText}`)] : []), p(`保留 ${logs.entries.length} 筆 · 捨棄 ${logs.dropped} 筆 · ${logs.bytes} bytes`),
        el('pre', { tabindex: '0', 'aria-label': '已遮蔽的子行程日誌' }, el('code', {},
          logs.entries.map(entry => `${entry.at} [${entry.stream} / ${entry.generation}] ${entry.text}`).join('\n') || '尚無日誌。')));
    })) : p('此部署未提供子行程日誌。'), viewer));
}
// ---- HM-13c (plan 6 還原與休眠核對卡; contract 3.1, 3.6, 4.1) ----
// The restore notice (DQ-03 (b), the owner's decision of 2026-11-16): a restore kept the default profile's token. It
// shows on the default profile's pages until the token changes (the server removes it); "知道了" hides it in this
// page only (memory: no browser storage, N15), so a reload shows it again.
function restoreNoticeCard() {
  const found = restoreNotice(state);
  if (!found || (api.profile !== null && api.profile !== DEFAULT_PROFILE) || noticeHidden === (found.at ?? '')) return null;
  return el('section', { class: 'card', id: 'restore-notice', 'aria-labelledby': 'restore-notice-title' },
    el('h2', { id: 'restore-notice-title' }, '偵測到還原'),
    p('偵測到還原；權杖已回到備份當時的值。若備份後曾輪替或撤銷，請立即重新產生'),
    // The time the add-on's start found the restore (HM-13a's marker left by an image without the guard included: then
    // the first start with it, not the restore itself).
    p(`偵測到還原的時間：${noticeTime(found.at)}（add-on 啟動時發現的時間）。MCP 用戶端連不上時，可能是它用的是備份之後才換的權杖。這則提示在重新產生或撤銷權杖後消失；「知道了」只在這個頁面暫時隱藏，重新整理後會再出現。`),
    el('div', { class: 'actions' }, button('前往重新產生權杖', () => navigate('access'), { class: 'primary' }),
      button('知道了', () => { noticeHidden = found.at ?? ''; render(); }, { id: 'restore-notice-dismiss' })));
}
// A switched-off add-on with profile data on disk (HM-13b): every additional profile's token is revoked, nothing of it
// is served and there is no management route for it (plan 8.4 休眠處理).
function dormantCard() {
  const dormant = dormantProfiles(state);
  if (api.profile !== null || !dormant) return null;
  return el('section', { class: 'card', id: 'dormant-profiles' }, el('h2', {}, '休眠的額外帳號'),
    p(`休眠帳號 ${dormant} 個，權杖已撤銷：這個版本沒有開通多帳號，磁碟上這些帳號的資料不會服務 MCP 請求，也不能在這裡管理。`),
    p('產品開通多帳號之後，請在預設帳號頁的核對卡逐帳號核對，再重新產生權杖。'));
}
const fieldLabel = key => products[product]?.fields.find(([name]) => name === key)?.[1] ?? ({ backend_url: 'n8n 伺服器 URL' })[key] ?? key;
// The review card (switched on, the default profile's pages): every profile the guard revoked, with what the backup
// brought back (its name, backend identity and policy, as text), its review and what can be done next.
function reviewCard() {
  const review = restoreReview(state);
  if (api.profile !== DEFAULT_PROFILE || !review) return null;
  // HM-13c review S-2: the record "revoke all" writes over one that could not be read names neither a restore nor a
  // dormant revocation; one that cannot be read has a way out in the panel ("revoke all" rebuilds it).
  const rebuilt = review.pending !== null && !review.restoreAt && !review.dormantAt;
  const when = review.restoreAt ? `偵測到還原（${noticeTime(review.restoreAt)}）` : review.dormantAt ? `休眠帳號的權杖已撤銷（${noticeTime(review.dormantAt)}）` : rebuilt ? '全部撤銷時重建的紀錄' : '還原紀錄';
  const parts = [review.pending === null
    ? p('還原紀錄讀不到或格式不符：所有帳號的「重新產生權杖」暫停。到「診斷與維護」按「全部撤銷」，會撤銷每個帳號的權杖並重建紀錄，之後逐帳號核對就能重新產生；也可以直接刪除帳號。請先重新整理狀態，一再出現時請回報。')
    : p(`${rebuilt ? '還原紀錄先前讀不到，全部撤銷時已重建。' : ''}${review.pending} 個帳號的權杖已撤銷，等你核對：逐一確認下面的名稱、後端身分與政策摘要是你要的（它們是還原或撤銷當時記下的值），按「已核對」後才能到那個帳號重新產生權杖。設定不對的帳號可以直接刪除。`)];
  // A list without its revision (the index cannot be used, or the list cannot be read) changes nothing: say so rather
  // than offer a button that cannot act (HM-11 review observation 4's lesson).
  if (profiles?.revision === null) parts.push(p('帳號清單目前不能變更（例如帳號索引無法使用），暫時無法核對或刪除帳號。帳號索引無法使用時，請先「隔離帳號索引」，再回來核對；其他情況請重新整理狀態。'));
  if (record?.error) parts.push(p(record.error instanceof UiError ? record.error.message : '還原紀錄無法讀取。'));
  else if (record?.view) parts.push(reviewRows(record.view));
  const quarantined = profiles?.quarantined ?? [];
  if (quarantined.length) parts.push(quarantineList(quarantined));
  return el('section', { class: 'card', id: 'restore-review', 'aria-labelledby': 'restore-review-title' },
    el('h2', { id: 'restore-review-title' }, `核對卡：${when}`), ...parts);
}
function reviewRows(view) {
  const locked = profiles?.revision === null;
  return el('ul', { class: 'review-list' }, ...view.rows.map(row => {
    const listed = profiles?.rows.find(item => item.id === row.id) ?? null;
    const exists = row.id === DEFAULT_PROFILE || listed !== null;
    // Not in the list: a list the panel cannot use says nothing about it; an orphan is still on disk (delete only).
    const where = exists ? listed ? ` · 目前狀態：${statusLabel(listed)}` : ''
      : profiles?.substitute ? ' · 帳號清單目前讀不到，狀態不明'
        : (profiles?.orphans ?? []).includes(row.id) ? ' · 帳號索引沒有列它（孤兒帳號資料，只能在「診斷與維護」刪除）' : ' · 已刪除';
    const name = row.id === DEFAULT_PROFILE ? '預設帳號' : listed ? profileName(listed) : row.label ?? '名稱不明的帳號';
    const identity = row.identity.length ? el('dl', { class: 'summary' }, ...row.identity.flatMap(([key, value]) => [el('dt', {}, fieldLabel(key)), el('dd', {}, value ?? '（未設定）')]))
      : p('沒有後端身分欄位（還沒有設定連線）。');
    const actions = [];
    if (exists && waitsForReview(row)) actions.push(button('已核對', () => reviewProfile(row, name), { disabled: locked, 'aria-label': `已核對帳號「${name}」（${shortId(row.id)}）` }));
    else if (exists && row.reviewedAt) actions.push(button('到這個帳號重新產生權杖', () => goRotate(row.id)));
    if (exists && row.id !== DEFAULT_PROFILE && listed) actions.push(button('刪除', () => removeProfile(listed), { disabled: locked, 'aria-label': `刪除帳號「${name}」（${shortId(row.id)}）` }));
    return el('li', { class: 'review-row', 'data-profile': row.id }, el('h3', {}, `${name}（${shortId(row.id)}）`),
      p(`${tokenText(row.token)}${where}${row.reviewedAt ? ` · 已核對（${noticeTime(row.reviewedAt)}）` : ''}`),
      identity, p(`政策摘要：${policyLine(row.policy)}`), actions.length ? el('div', { class: 'actions' }, ...actions) : null);
  }));
}
async function reviewProfile(row, name) {
  if (busy || !profiles || profiles.revision === null) return;
  if (!await confirmAction(`已核對帳號「${name}」（${shortId(row.id)}）？`, '請先確認卡片上的名稱、後端身分欄位與政策摘要都是你要的（它們是還原或撤銷當時記下的值）。核對後就能到這個帳號重新產生權杖；不對的話請改按「刪除」，或先到該帳號修改設定。', '確認已核對', { scoped: false })) return;
  const revision = profiles.revision;
  await task(async () => {
    await api.reviewProfile(row.id, revision);
    await reload(`已核對帳號「${name}」（${shortId(row.id)}）：現在可以到這個帳號的「連線與權杖」重新產生權杖。`);
  });
}
async function goRotate(id) {
  if (busy) return;
  if (id === api.profile) { navigate('access'); return; }
  history.pushState(null, '', `${api.mount}/access`);
  await show(id);
}
function quarantineList(entries) {
  // HM-13c review S-5: the first QUARANTINE_SHOWN only (the list keeps them all); the rest come up as these are deleted.
  const more = entries.length - QUARANTINE_SHOWN;
  return el('div', { class: 'stack', id: 'quarantined-profiles' }, el('h3', {}, '隔離的帳號資料'),
    p('還原時讀不到設定、被移到隔離區的帳號資料：不會服務 MCP 請求，不能選擇或重新產生權杖，只能刪除。確認不需要後逐一刪除；刪除前會先撤銷讀得到的權杖並抹除憑證。'),
    profiles.revision === null ? p('帳號清單目前不能變更，暫時無法刪除。') : null,
    el('ul', { class: 'orphan-list' }, ...entries.slice(0, QUARANTINE_SHOWN).map(entry => el('li', {}, el('span', {}, `帳號資料（${shortId(entry.id)}，隔離於 ${quarantineTime(entry.name)}）`),
      button('刪除', () => deleteQuarantined(entry), { disabled: profiles.revision === null, 'aria-label': `刪除隔離的帳號資料（${shortId(entry.id)}，${quarantineTime(entry.name)}）` })))),
    more > 0 ? el('p', { class: 'quarantine-more' }, `另有 ${more} 筆隔離的帳號資料沒有列出（這裡最多列 ${QUARANTINE_SHOWN} 筆）；刪除上面的之後，其餘的會依序出現。`) : null);
}
// The quarantine directories, on the diagnostics page whichever profile is shown (they are the add-on's, as orphans).
function quarantinedCard() {
  const entries = api.profile === null ? [] : profiles?.quarantined ?? [];
  if (!entries.length) return null;
  return el('section', { class: 'card', id: 'profile-quarantined' }, el('h2', {}, '隔離的帳號資料'), quarantineList(entries));
}
async function deleteQuarantined(entry) {
  if (busy || !profiles || profiles.revision === null) return;
  const name = `隔離的帳號資料（${shortId(entry.id)}，隔離於 ${quarantineTime(entry.name)}）`;
  if (!await confirmAction(`刪除${name}？`, '這份資料在還原時讀不到設定而被隔離，不會服務 MCP 請求。刪除時讀得到的權杖會先撤銷、憑證先抹除，再刪除它的資料夾；面板無法復原，只有再還原一次備份才會回來。其他帳號不受影響。', '繼續', { scoped: false })) return;
  if (!await confirmAction(`最後確認：刪除${name}`, '確認後立即刪除，無法在面板復原。', '確認刪除', { scoped: false })) return;
  const revision = profiles.revision;
  await task(async () => { await api.deleteQuarantined(entry.name, revision); await reload(`已刪除${name}。`); });
}
// "Revoke all" (plan 7.4 (c), 8.4, 8.10; contract 3.1): the add-on's emergency stop. Its revision is the list's, or the
// unusable index's own ETag while the index cannot be used (the default bootstrap's profile_index_etag).
function revokeAllRevision() {
  if (!profiles) return null;
  if (profiles.revision !== null) return profiles.revision;
  const { corrupt, etag } = indexState(state);
  return profiles.corrupt && corrupt && etag ? etag.slice(1, -1) : null;
}
function revokeAllCard() {
  if (api.profile === null || !profiles) return null;
  const revision = revokeAllRevision();
  return el('section', { class: 'card', id: 'revoke-all' }, el('h2', {}, '全部撤銷'),
    p('一次撤銷所有帳號（含預設帳號）的 MCP 權杖：懷疑權杖外洩、還原了較舊的備份，或回退後再升級時使用。所有用戶端都會斷線；之後要逐一到各帳號按「重新產生」才能恢復連線。'),
    revision === null ? p('帳號清單目前沒有版本資訊，暫時無法全部撤銷；請重新整理狀態。') : null,
    el('div', { class: 'actions' }, button('全部撤銷', revokeAll, { id: 'revoke-all-button', disabled: revision === null })));
}
function unfinishedText(results, resent = false) {
  // No result at all: it may not even have begun (its marker could not be saved, e.g. a full disk), and then a restart
  // brings nothing back to finish: say both ways (contract 4.1 operation_outcome_unknown).
  if (!resent && !results.length) return '全部撤銷沒有完成，也沒有回報任何帳號的結果（例如磁碟寫不進去）。這次執行期間，所有帳號原本的權杖在 MCP 端點都回 503。撤銷若已經開始，重新啟動 add-on 時會在服務前補完；若連開始都沒有，重新啟動後原本的權杖會恢復有效。請先查看 add-on 日誌、修好磁碟，再在「帳號操作尚未確認」按「已核對帳號清單」，然後再按一次「全部撤銷」。';
  const failed = results.filter(item => item.result === 'failed').map(item => named(profiles?.rows.find(row => row.id === item.id) ?? null, item.id));
  // Every profile revoked, yet not finished (the check after it did not pass, or the profiles directory could not be
  // listed): nothing is refused with 503, and the next start does it all again.
  if (!resent && !failed.length) return '全部撤銷沒有完成：每個帳號的權杖都已撤銷，但收尾沒有完成（例如事後的檢查沒有通過，或帳號資料夾一時讀不到）。重新啟動 add-on 時會在服務前再做一次全部撤銷（之後才產生的新權杖也會一起撤銷）。要現在完成，請先在「帳號操作尚未確認」按「已核對帳號清單」，再按一次「全部撤銷」。';
  const what = failed.length ? `帳號${failed.join('、')}的權杖沒有撤銷成功` : '伺服器不會再執行同一筆操作，結果仍未確認';
  return `全部撤銷沒有完成：${what}。沒撤銷成功的帳號在 MCP 端點回 503，直到重試成功；重新啟動 add-on 時也會自動補完（之後才產生的新權杖也會一起撤銷）。要重試，請先在「帳號操作尚未確認」按「已核對帳號清單」，再按一次「全部撤銷」。`;
}
async function revokeAll() {
  const revision = revokeAllRevision();
  if (busy || revision === null) return;
  if (!await confirmAction('全部撤銷所有帳號的權杖？', '所有帳號（含預設帳號）的 MCP 權杖會立即撤銷，用它們連線的用戶端都會斷線；各帳號的子行程會用新的內部權杖重新啟動。撤銷後要逐一到各帳號按「重新產生」才能恢復連線，面板無法復原。', '繼續', { scoped: false })) return;
  if (!await confirmAction('最後確認：全部撤銷', '確認後立即撤銷所有帳號的權杖。', '確認全部撤銷', { scoped: false })) return;
  let done = null, unfinished = null;
  await task(async () => {
    try { done = await api.revokeAll(revision); }
    catch (error) {
      if (error instanceof ApiError && error.code === 'operation_outcome_unknown' && error.results !== null) { unfinished = error.results; return; }
      throw error;
    }
  });
  if (done) await task(() => reload('已撤銷所有帳號的權杖。需要時請逐一到各帳號的「連線與權杖」重新產生。'));
  else if (unfinished) await task(async () => { await reload(); notice(unfinishedText(unfinished), true); });
}
// The export (plan 6, 選做; PaaS runbook step 1): what to keep before a restore, without a token or a credential.
function exportCard() {
  if (api.profile === null || !profiles || profiles.substitute) return null;
  const area = el('div', { id: 'profile-export', 'aria-live': 'polite' });
  return el('section', { class: 'card', id: 'profile-export-card' }, el('h2', {}, '匯出帳號清單（不含憑證）'),
    p('還原備份之前先留一份：每個帳號的名稱、port、後端的非秘密欄位（網址、資料庫、使用者名稱）與工具政策，不含任何權杖或憑證。還原後可以拿它和核對卡逐帳號比對。'),
    button('產生帳號清單', () => task(async () => {
      const epoch = api.epoch, entries = [];
      for (const row of profiles.rows) {
        try { entries.push(exportEntry(row, await api.bootstrap(row.id, epoch))); }
        catch (error) {
          if (error instanceof StaleProfileError || error instanceof ProfileEchoError || error instanceof ApiError && [401, 403].includes(error.status)) throw error;
          entries.push({ id: row.id, label: row.hidden ? null : row.label, port: row.port, unavailable: true });
        }
      }
      const text = exportDocument(product, entries);
      area.replaceChildren(el('pre', { tabindex: '0', 'aria-label': '帳號清單（JSON，不含憑證）' }, el('code', {}, text)),
        el('div', { class: 'actions' }, button('複製帳號清單', () => copy(text))));
    }), { id: 'profile-export-button' }), area);
}
const brandCaption = () => el('div', { class: 'brand-caption' }, icon('home-automation'), el('div', {}, el('strong', {}, 'Woow MCP'), el('span', {}, '智慧空間 · 服務管理'), el('span', { class: 'brand-accent', lang: 'en' }, 'Welcome')));
// HM-11 (plan 6): with profiles, the menu sits in the top bar and the heading always names the shown profile.
function profileView() {
  if (api.profile === null || !profiles) return {};
  const row = currentRow();
  const quarantinable = profiles.corrupt && api.profile === DEFAULT_PROFILE && indexState(state).etag !== null;
  return {
    menu: profileMenu({ el, button }, { rows: profiles.rows, current: api.profile, loading: false, supported: state.profiles_supported === true,
      writable: profiles.revision !== null, orphans: profiles.orphans.length }, profileActions),
    heading: el('p', { class: 'profile-current' }, '目前帳號：', el('strong', {}, row ? profileName(row) : shortId(api.profile)), `（${shortId(api.profile)}）`),
    // DQ-12: the panel stays open; the one way out on HA is this action (or restoring a backup).
    corrupt: profiles.corrupt ? el('section', { class: 'card', id: 'profile-index-corrupt' }, el('h2', {}, '帳號索引無法使用'),
      p('帳號索引無法讀取或已在 add-on 之外被修改：MCP 端點暫停服務所有帳號（含預設帳號），額外帳號暫時無法選擇；預設帳號的設定仍可在這裡檢查。'),
      p('「隔離帳號索引」會撤銷所有額外帳號的權杖、把索引檔改名保存，預設帳號立刻恢復 MCP 服務；額外帳號的資料會變成孤兒帳號資料，可以之後逐一刪除。也可以改為還原備份。'),
      quarantinable ? el('div', { class: 'actions' }, button('隔離帳號索引', quarantineIndex, { id: 'profile-index-quarantine' }))
        : p(api.profile === DEFAULT_PROFILE ? '帳號索引的版本資訊無法使用，暫時不能隔離；請重新整理狀態。' : '請切回預設帳號再隔離帳號索引。'))
      // Review S-2: a list the panel cannot use, or one without its ETag, never locks the page.
      : profiles.unreadable ? el('section', { class: 'card', id: 'profile-list-unavailable' }, el('h2', {}, '帳號清單無法讀取'),
        p('這次讀不到帳號清單，或清單的格式與這個管理介面不相容，所以選單只列出預設帳號（與目前顯示的帳號）；新增、改名、刪除帳號暫停。目前帳號的設定照常可以管理。請重新整理狀態；一再出現時請更新 add-on 或回報。'))
      : profiles.revision === null ? el('section', { class: 'card', id: 'profile-list-readonly' }, el('h2', {}, '帳號清單缺少版本資訊'),
        p('帳號清單的回應沒有帶版本資訊（ETag 標頭），所以新增、改名、刪除帳號暫停，避免覆蓋其他人的變更。切換帳號與各帳號的設定照常可以使用。一再出現時，可能是 Home Assistant 或前面的反向代理拿掉了這個標頭，請回報。'))
      : null,
  };
}
function render() {
  const current = route();
  const view = profileView();
  root.replaceChildren(el('a', { href: '#main', class: 'skip' }, '跳至主要內容'),
    el('header', { class: 'topbar' }, brandCaption(), el('div', { class: 'product-label' }, products[state.product].name, chip(environmentLabels(state.capabilities).deployment)), view.menu),
    el('div', { class: 'shell' }, el('aside', {}, el('p', { class: 'nav-caption' }, '工作空間'), el('nav', { 'aria-label': '管理導覽' }, ...Object.entries(routes).map(([key, label]) => el('a', { href: `${api.mount}/${key}`, 'aria-current': current === key ? 'page' : null, onclick: event => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) { event.preventDefault(); if (!busy) navigate(key); } } }, icon(icons[key]), label))), el('div', { class: 'sidebar-note' }, p('設定由你掌握'), p('後端憑證只在明確更新時送出。權限由伺服器驗證。'))),
      el('main', { id: 'main' }, el('div', { class: 'page-heading' }, el('div', {}, el('p', { class: 'eyebrow' }, `${products[state.product].name} / MANAGEMENT`), view.heading, el('h1', { tabindex: '-1' }, routes[current]), p({ overview: '一眼看清連線，安心管理你的服務。', backend: '把連線留在這裡，把秘密留在伺服器。', tools: '只開啟需要的能力，每次寫入都有明確授權。', access: '給用戶端正確的入口，不混用管理網址。', diagnostics: '查看受限日誌與行程狀態，必要時重新啟動。' }[current])), button('重新整理狀態', () => task(() => reload('已取得最新管理狀態。')))), el('div', { id: 'notice', role: 'status', tabindex: '-1', hidden: true }),
        view.corrupt, restoreNoticeCard(), dormantCard(), reviewCard(),
        ownerDefaults()?.malformed ? ownerDefaultsUnavailable() : ownerDefaults()?.notice ? ownerDefaultsCard(ownerDefaults()) : null,
        el('div', { id: 'pending-operation' }), configurationCard(state.configuration), ({ overview, backend, tools, access, diagnostics })[current](),
        current === 'backend' ? partialBackendCard() : null,
        current === 'backend' && state.product === 'n8n' ? n8nSessionCard() : null,
        current === 'tools' && state.product === 'odoo' ? odooSwitchCard() : null,
        current === 'tools' && state.product === 'odoo' ? odooMethodsCard() : null,
        el('footer', {}, `GUI 管理設定 · ${environmentLabels(state.capabilities).authority} · Streamable HTTP`))));
  refreshOperation();
}
// HM-11: while a profile loads there is no state to draw (show sets it to null); the loading page stays.
window.addEventListener('popstate', () => { hideToken(); if (state) render(); });
window.addEventListener('pagehide', () => {
  hideToken();
  document.querySelectorAll('input[type=password]').forEach(input => input.value = '');
});
window.addEventListener('blur', hideToken);
document.addEventListener('visibilitychange', () => { if (document.hidden) hideToken(); });
try {
  api = new AdminApi(document.querySelector('meta[name=mcp-ui-base]')?.content);
  root.replaceChildren(el('main', { class: 'blocked', role: 'status' }, p('正在驗證管理權限…')));
  await reload();
} catch (error) { renderDenied(error instanceof UiError ? error.message : '管理服務無法使用。'); }
