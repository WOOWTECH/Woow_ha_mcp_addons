// HM-13c (plan 6 還原與休眠核對卡, 8.4, 10.3; contract 3.1, 3.6, 4.1): the panel after a restore, against the LOCAL MOCK
// (fixtures/server.mjs; not HA security or E2E; tests/browser/profile-api-parity.spec.mjs checks the mock against the
// answers the real add-on gives). Single profile: the restore notice (the owner's decision of 2026-11-16), the dormant
// banner; switched on: the review card, the gate on a new token, the quarantine directories, "revoke all", the export.
// Whatever came back from a backup (names, backend fields) stays text.
import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const B = '0123456789abcdef01234567', C = 'fedcba9876543210fedcba98', Q = 'abcdefabcdefabcdefabcdef';
const evil = '<img src=x onerror="window.injected=1"> 會計';
const AT = '2026-11-16T09:30:15+00:00';
const NOTICE = '偵測到還原；權杖已回到備份當時的值。若備份後曾輪替或撤銷，請立即重新產生';
async function reset(request, data) { await request.post('/__fixture/reset', {data}); }
async function calls(request, filter = () => true) { return (await (await request.get('/__fixture/calls')).json()).filter(filter); }
async function fixtureProfiles(request) { return (await (await request.get('/__fixture/profiles')).json()).profiles; }
const menu = page => page.getByLabel('帳號', {exact: true});
async function idle(page) { await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true'); }
async function open(page, path) { await page.goto(`${prefix}${path}`); await expect(page.getByRole('heading', {level: 1})).toBeVisible(); await idle(page); }
async function confirm(page, label) { await page.getByRole('dialog').getByRole('button', {name: label, exact: true}).click(); }
async function go(page, name) { await page.getByRole('navigation').getByRole('link', {name, exact: true}).click(); await idle(page); }
const policy = {writes_enabled: false, disabled: ['read_example'], enabled_write_tools: [], denied_operations: {}, odoo_write_switches: null,
  odoo_allowed_methods: null, n8n_session: null};
const identity = {url: 'https://backup.example.invalid', database: 'DUMMY-db', username: '<b>backup-user</b>'};
const restored = (rows = [B, C]) => ({product: 'odoo', parity: true, profiles: {
  extra: [{id: B, label: evil, configured: true}, {id: C, label: '出納', configured: true}].filter(spec => rows.includes(spec.id)),
  restore: {at: AT, rows: [{id: 'default', label: 'Default', token: 'revoked', identity, policy},
    ...rows.map(id => ({id, label: id === B ? evil : '出納', token: 'revoked', identity, policy}))]},
  quarantined: [`${Q}-20261116T093015Z`]}});

test('single profile: the restore notice says the token is the backup\'s, on every page, until the token changes; "知道了" hides it in this page only', async ({page, request}) => {
  await reset(request, {product: 'odoo', configured: true, restoreNotice: {at: AT}});
  await open(page, '/overview');
  const card = page.locator('#restore-notice');
  await expect(card.getByRole('heading', {name: '偵測到還原', exact: true})).toBeVisible();
  await expect(card).toContainText(NOTICE);
  // The time the start found it (an image without the guard may have left the marker of an older restore: HM-13a).
  await expect(card).toContainText('偵測到還原的時間：2026-11-16 09:30（UTC）（add-on 啟動時發現的時間）');
  for (const name of ['工具權限', '診斷與維護']) {
    await go(page, name);
    await expect(page.locator('#restore-notice')).toContainText(NOTICE);
  }
  // "知道了": hidden while this page lives, in memory only (N15: no browser storage); a reload shows it again.
  await page.getByRole('button', {name: '知道了', exact: true}).click();
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  await go(page, '總覽');
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.reload();
  await expect(page.locator('#restore-notice')).toContainText(NOTICE);
  // The way out: a new token (the server removes the notice with the token change).
  await page.getByRole('button', {name: '前往重新產生權杖', exact: true}).click();
  await expect(page.getByRole('heading', {level: 1})).toHaveText('連線與權杖');
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret code')).toHaveText('M'.repeat(43));
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  await page.reload();
  await idle(page);
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  // No profile request, no new route, no header: the single-profile panel as before.
  expect((await calls(request)).map(call => [call.operation, call.profileHeader])).toEqual([['token/rotate', undefined]]);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test('single profile without a restore: none of the new cards, and a revoke ends a notice as a rotation does', async ({page, request}) => {
  await reset(request, {product: 'odoo', configured: true});
  await open(page, '/diagnostics');
  for (const id of ['#restore-notice', '#dormant-profiles', '#restore-review', '#revoke-all', '#profile-export-card', '#profile-quarantined']) {
    await expect(page.locator(id)).toHaveCount(0);
  }
  await reset(request, {product: 'n8n', restoreNotice: {at: AT}});
  await open(page, '/access');
  await expect(page.locator('#restore-notice')).toContainText(NOTICE);
  await page.getByRole('button', {name: '撤銷權杖', exact: true}).click();
  await confirm(page, '確認撤銷');
  await expect(page.locator('#notice')).toContainText('權杖已撤銷');
  await expect(page.locator('#restore-notice')).toHaveCount(0);
});

test('a switched-off add-on with dormant profiles says so and offers nothing to manage', async ({page, request}) => {
  await reset(request, {product: 'odoo', configured: true, dormantProfiles: 2});
  await open(page, '/overview');
  await expect(page.locator('#dormant-profiles')).toContainText('休眠帳號 2 個，權杖已撤銷');
  await expect(page.locator('#dormant-profiles button')).toHaveCount(0);
  await expect(menu(page)).toHaveCount(0);
});

test('the review card: every restored profile as text, its gate on a new token, "已核對" with a receipt, then the token', async ({page, request}) => {
  await reset(request, restored());
  let alerts = 0;
  page.on('dialog', async dialog => { alerts++; await dialog.dismiss(); });
  await open(page, '/overview');
  const card = page.locator('#restore-review');
  await expect(card.getByRole('heading', {level: 2})).toHaveText('核對卡：偵測到還原（2026-11-16 09:30（UTC））');
  await expect(card).toContainText('3 個帳號的權杖已撤銷，等你核對');
  const row = card.locator(`li[data-profile="${B}"]`);
  await expect(row.getByRole('heading', {level: 3})).toHaveText(`${evil}（01234567）`);
  await expect(row).toContainText('權杖已撤銷 · 目前狀態：');
  await expect(row).toContainText('後端 URL');
  await expect(row).toContainText('https://backup.example.invalid');
  await expect(row).toContainText('<b>backup-user</b>');
  await expect(row).toContainText('政策摘要：舊版全域寫入：關、停用工具 1 個、逐項寫入授權 0 項、禁止的操作 0 項、Odoo 子操作開關：沿用舊值、Odoo 方法清單：沒有存過');
  expect(await page.locator('img, b').count()).toBe(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  // The quarantine directory: listed in the card, delete only.
  await expect(card.locator('#quarantined-profiles')).toContainText('帳號資料（abcdefab，隔離於 2026-11-16 09:30（UTC））');
  // B's new token waits for its review: the button is off and says why.
  await menu(page).selectOption(B);
  await idle(page);
  await go(page, '連線與權杖');
  await expect(page.locator('#restore-review-required')).toContainText('還沒有核對');
  await expect(page.getByRole('button', {name: '重新產生', exact: true})).toBeDisabled();
  await menu(page).selectOption('default');
  await idle(page);
  await go(page, '總覽');
  await page.getByRole('button', {name: `已核對帳號「${evil}」（01234567）`, exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText(`已核對帳號「${evil}」（01234567）？`);
  await expect(page.locator('.dialog-profile')).toHaveCount(0);  // not the shown profile's action
  expect(await page.locator('img').count()).toBe(0);
  await confirm(page, '確認已核對');
  await expect(page.locator('#notice')).toContainText('現在可以到這個帳號的「連線與權杖」重新產生權杖');
  const [review] = await calls(request, call => call.operation.endsWith('/restore-review'));
  expect(review).toMatchObject({operation: `profiles/${B}/restore-review`, method: 'POST', validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`});
  expect(review.operationId).toMatch(/^[0-9]{13}\.[0-9a-f]{32}$/);
  expect(review.profileHeader).toBeUndefined();
  await expect(card).toContainText('2 個帳號的權杖已撤銷，等你核對');
  await expect(card.locator(`li[data-profile="${B}"]`)).toContainText('已核對（2026-11-16 10:00（UTC））');
  await card.locator(`li[data-profile="${B}"]`).getByRole('button', {name: '到這個帳號重新產生權杖', exact: true}).click();
  await idle(page);
  await expect(page.getByRole('heading', {level: 1})).toHaveText('連線與權杖');
  await expect(menu(page)).toHaveValue(B);
  await expect(page.locator('#restore-review-required')).toHaveCount(0);
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret code')).toHaveText('T'.repeat(43));
  expect((await fixtureProfiles(request))[B].token_active).toBe(true);
  expect(alerts).toBe(0);
});

test('while the index cannot be used the card offers nothing it cannot do and says why; after the index quarantine the default profile is reviewed', async ({page, request}) => {
  const spec = restored();
  spec.profiles.indexCorrupt = true;
  await reset(request, spec);
  await open(page, '/overview');
  const card = page.locator('#restore-review');
  // An unusable index lists no profile: only the default profile counts, and the others' state is not known.
  await expect(card).toContainText('1 個帳號的權杖已撤銷，等你核對');
  await expect(card).toContainText('帳號清單目前不能變更（例如帳號索引無法使用），暫時無法核對或刪除帳號');
  const other = card.locator(`li[data-profile="${B}"]`);
  await expect(other).toContainText('帳號清單目前讀不到，狀態不明');
  await expect(other).not.toContainText('已刪除');
  await expect(other.getByRole('button')).toHaveCount(0);
  const review = () => card.getByRole('button', {name: '已核對帳號「預設帳號」（default）', exact: true});
  await expect(review()).toBeDisabled();
  expect(await calls(request)).toEqual([]);
  // The index quarantine (HM-10, HM-11): B and C become orphans (on disk, delete only); the default profile is reviewed.
  await page.getByRole('button', {name: '隔離帳號索引', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認隔離');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已隔離帳號索引');
  await expect(other).toContainText('帳號索引沒有列它（孤兒帳號資料，只能在「診斷與維護」刪除）');
  await expect(card).not.toContainText('帳號清單目前不能變更');
  await review().click();
  await confirm(page, '確認已核對');
  await expect(page.locator('#notice')).toContainText('已核對帳號「預設帳號」（default）');
  const sent = await calls(request, call => call.operation.endsWith('/restore-review'));
  expect(sent.map(call => call.operation)).toEqual(['profiles/default/restore-review']);
  // Nothing waits any more: the card is gone; the default profile's new token is open (its gate lifted).
  await expect(card).toHaveCount(0);
  await go(page, '連線與權杖');
  await expect(page.locator('#restore-review-required')).toHaveCount(0);
  await expect(page.getByRole('button', {name: '重新產生', exact: true})).toBeEnabled();
});

test('a quarantine directory can only be deleted, after two confirmations; a listed profile can be deleted from the card', async ({page, request}) => {
  await reset(request, restored());
  await open(page, '/diagnostics');
  const listed = page.locator('#profile-quarantined');
  await expect(listed).toContainText('帳號資料（abcdefab，隔離於 2026-11-16 09:30（UTC））');
  await expect(listed.getByRole('button')).toHaveCount(1);
  await expect(menu(page).locator(`option[value="${Q}"]`)).toHaveCount(0);  // never a profile to choose
  await listed.getByRole('button', {name: '刪除隔離的帳號資料（abcdefab，2026-11-16 09:30（UTC））', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#notice')).toContainText('已刪除隔離的帳號資料（abcdefab');
  await expect(page.locator('#profile-quarantined')).toHaveCount(0);
  const [deleted] = await calls(request, call => call.operation.startsWith('profiles/quarantine/'));
  expect(deleted).toMatchObject({operation: `profiles/quarantine/${Q}-20261116T093015Z/delete`, method: 'POST', validCsrf: true});
  await go(page, '總覽');
  const row = page.locator(`#restore-review li[data-profile="${C}"]`);
  await row.getByRole('button', {name: '刪除帳號「出納」（fedcba98）', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#notice')).toContainText('已刪除帳號「出納」（fedcba98），它的權杖已失效；其他帳號不受影響');
  await expect(page.locator(`#restore-review li[data-profile="${C}"]`)).toContainText('已刪除');
  await expect(page.locator('#restore-review')).toContainText('2 個帳號的權杖已撤銷，等你核對');
});

test('more quarantine directories than the panel lists: the list stays usable, the first 64 are shown with how many more, and they can be deleted', async ({page, request}) => {
  // HM-13c review S-5: a forged backup or many restores may leave any number of them; the list is never refused for it.
  const names = Array.from({length: 70}, (_, n) => `${Q}-20261116T093015Z${n ? `-${n + 1}` : ''}`);
  await reset(request, {product: 'odoo', configured: true, profiles: {extra: [{id: B, label: '會計', configured: true}], quarantined: names}});
  await open(page, '/diagnostics');
  const listed = page.locator('#profile-quarantined');
  await expect(listed.locator('li')).toHaveCount(64);
  await expect(listed.locator('.quarantine-more')).toHaveText('另有 6 筆隔離的帳號資料沒有列出（這裡最多列 64 筆）；刪除上面的之後，其餘的會依序出現。');
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveCount(1);  // the real list, not the substitute
  await expect(page.getByRole('button', {name: '全部撤銷', exact: true})).toBeEnabled();
  await listed.locator('li').first().getByRole('button').click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#notice')).toContainText('已刪除隔離的帳號資料（abcdefab');
  await expect(listed.locator('li')).toHaveCount(64);
  await expect(listed.locator('.quarantine-more')).toContainText('另有 5 筆');
});

test('a restore record that cannot be read names the way out; the one "revoke all" rebuilt says so and waits for every review', async ({page, request}) => {
  // HM-13c review S-2: every new token waits (503) while the record cannot be read; "revoke all" writes a new one.
  await reset(request, {product: 'odoo', configured: true, profiles: {extra: [{id: B, label: '會計', configured: true}], restore: {broken: true}}});
  await open(page, '/overview');
  const card = page.locator('#restore-review');
  await expect(card.getByRole('heading', {level: 2})).toHaveText('核對卡：還原紀錄');
  await expect(card).toContainText('還原紀錄讀不到或格式不符：所有帳號的「重新產生權杖」暫停。到「診斷與維護」按「全部撤銷」，會撤銷每個帳號的權杖並重建紀錄');
  await reset(request, {product: 'odoo', configured: true, profiles: {extra: [{id: B, label: '會計', configured: true}],
    restore: {rows: [{id: 'default', label: 'Default', token: 'revoked', identity: {}, policy}, {id: B, label: '會計', token: 'revoked', identity: {}, policy}]}}});
  await page.reload();
  await idle(page);
  await expect(card.getByRole('heading', {level: 2})).toHaveText('核對卡：全部撤銷時重建的紀錄');
  await expect(card).toContainText('還原紀錄先前讀不到，全部撤銷時已重建。2 個帳號的權杖已撤銷，等你核對');
  await expect(card.getByRole('button', {name: '已核對帳號「會計」（01234567）', exact: true})).toBeEnabled();
});

test('"revoke all" asks twice; when a profile fails it says which, keeps the operation open, and a new one after acknowledging finishes', async ({page, request}) => {
  await reset(request, {product: 'odoo', configured: true, restoreNotice: {at: AT}, profiles: {extra: [{id: B, label: '會計', configured: true}], revokeFail: [B]}});
  await open(page, '/diagnostics');
  await expect(page.locator('#restore-notice')).toContainText(NOTICE);
  await page.getByRole('button', {name: '全部撤銷', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('全部撤銷所有帳號的權杖？');
  await confirm(page, '繼續');
  await confirm(page, '確認全部撤銷');
  await expect(page.locator('#notice')).toContainText('全部撤銷沒有完成：帳號「會計」（01234567）的權杖沒有撤銷成功');
  await expect(page.locator('#notice')).toContainText('503');
  await expect(page.locator('#pending-profile-operation')).toContainText('全部撤銷尚未取得完成確認');
  const [first] = await calls(request, call => call.operation === 'profiles/revoke-all');
  expect(first).toMatchObject({method: 'POST', validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`});
  expect(first.profileHeader).toBeUndefined();
  // The default profile was revoked: its restore notice is gone.
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  // A resend of the same operation answers the same: still unknown.
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#notice')).toContainText('全部撤銷沒有完成');
  await page.getByRole('button', {name: '已核對帳號清單', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  await page.getByRole('button', {name: '全部撤銷', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認全部撤銷');
  await expect(page.locator('#notice')).toContainText('已撤銷所有帳號的權杖');
  const sent = await calls(request, call => call.operation === 'profiles/revoke-all');
  expect(sent).toHaveLength(3);
  expect(sent[1].operationId).toBe(sent[0].operationId);
  expect(sent[2].operationId).not.toBe(sent[0].operationId);
  const state = await fixtureProfiles(request);
  expect([state.default.token_active, state[B].token_active]).toEqual([false, false]);
});

test('"revoke all" that never began, or whose end was not done, says what each means for the tokens and a restart', async ({page, request}) => {
  const revokeAll = async () => {
    await page.getByRole('button', {name: '全部撤銷', exact: true}).click();
    await confirm(page, '繼續');
    await confirm(page, '確認全部撤銷');
  };
  // Its marker could not be saved (a full disk): no result; nothing revoked, so a restart would bring nothing back.
  await reset(request, {product: 'odoo', configured: true, profiles: {extra: [{id: B, label: '會計', configured: true}], revokeOutcome: 'unstarted'}});
  await open(page, '/diagnostics');
  await revokeAll();
  await expect(page.locator('#notice')).toContainText('全部撤銷沒有完成，也沒有回報任何帳號的結果');
  await expect(page.locator('#notice')).toContainText('若連開始都沒有，重新啟動後原本的權杖會恢復有效');
  let state = await fixtureProfiles(request);
  expect([state.default.token_active, state[B].token_active]).toEqual([true, true]);
  await page.getByRole('button', {name: '已核對帳號清單', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  // Every profile revoked, its end not done (the check after it did not pass): no 503, and a restart does it again.
  await reset(request, {product: 'odoo', configured: true, profiles: {extra: [{id: B, label: '會計', configured: true}], revokeOutcome: 'unfinished'}});
  await page.reload();
  await idle(page);
  await revokeAll();
  await expect(page.locator('#notice')).toContainText('全部撤銷沒有完成：每個帳號的權杖都已撤銷，但收尾沒有完成');
  await expect(page.locator('#notice')).toContainText('之後才產生的新權杖也會一起撤銷');
  await expect(page.locator('#notice')).not.toContainText('503');
  state = await fixtureProfiles(request);
  expect([state.default.token_active, state[B].token_active]).toEqual([false, false]);
});

// HM-13c review S-3: a backend save that would give a profile that waits for its review a new token (HM-12's identity
// change) is refused as token/rotate is (409 restore_review_required); the mock answers the save so here (saveCode).
const ODOO = {product: 'odoo', parity: true, parity046: true, configured: true,
  connection: {url: 'https://odoo.invalid', database: 'DUMMY-db', username: 'DUMMY-user'}};
const WAITS = '這個帳號是從備份還原（或休眠）回來的，還沒有核對：請先到預設帳號頁的核對卡確認它的設定，按「已核對」後才能重新產生權杖。';
const SAVE_WAITS = '改後端身分（Odoo 的網址、資料庫或使用者）會換新這個帳號的 MCP 權杖，所以也要先核對才能儲存；這次未儲存任何變更。';

test('a backend save held for the restore review (409 restore_review_required, HM-13c review S-3): the review copy and why a save waits, nothing of the answer, the typed secret cleared', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {}, saveStatus: 409, saveCode: 'restore_review_required'});
  await open(page, '/backend');
  for (const [key, value] of Object.entries({username: 'DUMMY-user-two', password: 'DUMMY-typed-password'})) {
    await page.locator(`#patch-${key}-action`).selectOption('set');
    await page.locator(`#patch-${key}`).fill(value);
  }
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toHaveText(`${WAITS} ${SAVE_WAITS}`);
  await expect(page.locator('#notice')).toHaveClass(/error/);
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await expect(page.locator('#patch-password')).toHaveValue('');
  await expect(page.locator('#patch-username')).toHaveValue('DUMMY-user-two');
  const saves = await calls(request, call => call.operation === 'backend/patch');
  expect(saves.map(call => call.changedKeys)).toEqual([['username', 'password']]);
});

// HM-13c with HM-12: switched on without profile data a restore keeps the default profile's token (the notice); HM-12's
// identity change rotates that token, so the notice ends, as after a rotation (the mock answers as the add-on does).
test('switched on, an identity change that rotates the kept token ends the restore notice', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {}, restoreNotice: {at: AT}});
  await open(page, '/backend');
  await expect(page.locator('#restore-notice')).toContainText(NOTICE);
  await page.locator('#patch-username-action').selectOption('set');
  await page.locator('#patch-username').fill('DUMMY-user-two');
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('後端身分已變更，這個帳號的 MCP 權杖已換新');
  await expect(page.locator('#restore-notice')).toHaveCount(0);
  await page.reload();
  await idle(page);
  await expect(page.locator('#restore-notice')).toHaveCount(0);
});

test('the export names every profile without a token, a CSRF value or a credential', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, connection: {url: 'https://default.example.invalid', database: 'DUMMY-db', username: 'DUMMY-user'},
    configured: true, profiles: {extra: [{id: B, label: evil, configured: true}]}});
  await open(page, '/diagnostics');
  await page.getByRole('button', {name: '產生帳號清單', exact: true}).click();
  const shown = page.locator('#profile-export code');
  await expect(shown).toContainText('"woow-mcp-profile-list"');
  const text = await shown.textContent();
  const value = JSON.parse(text);
  expect(value.profiles.map(item => [item.id, item.label])).toEqual([['default', 'Default'], [B, evil]]);
  for (const item of value.profiles) {
    expect(Object.keys(item).sort()).toEqual(['connection', 'connection_configured', 'id', 'is_default', 'label', 'policy', 'port']);
    expect(Object.keys(item.policy).every(key => ['writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations',
      'odoo_write_switches', 'odoo_allowed_methods', 'n8n_session'].includes(key))).toBe(true);
  }
  for (const secret of ['M'.repeat(8), 'T'.repeat(8), 'mock_fresh_csrf_value', 'csrf', 'token', 'password', 'secret']) {
    expect(text).not.toContain(secret);
  }
  expect(await page.locator('img').count()).toBe(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  expect((await calls(request)).length).toBe(0);  // reads only
});
