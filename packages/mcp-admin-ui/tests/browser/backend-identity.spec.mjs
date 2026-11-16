// HM-12 (DQ-05, DQ-40 ⑨ (a); contract 3.1, 4.1, section 9 #113-#115 and HM-12's panel rows): the backend saves of a switched-on product
// against the LOCAL MOCK (fixtures/server.mjs; not HA security or E2E). A changed Odoo identity rotates the profile's
// MCP token (token_rotated: 200, or shape D when its new child does not start): the panel says where the new one is,
// hides every shown token and reads the new state. A URL moved to another origin needs its stored secrets again: the
// partial edit asks for them before anything is sent, and a 422 has fixed copy. The two 503s of a failed identity
// change: today's text, and for state unavailable a hint to restart and check the token (HM-12 review S-7).
// Switched off nothing of this exists (the last case; the single-profile specs run unchanged).
import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const B = '0123456789abcdef01234567';
const ROTATED = '後端身分已變更，這個帳號的 MCP 權杖已換新：舊權杖與含舊權杖的連線網址已撤銷。請到「連線與權杖」顯示並複製新的權杖（或 Claude.ai 連線網址），更新所有用戶端。';
const PATCHED = '已儲存選定欄位，其餘設定保持不變。請查看子行程套用狀態。';
const APPLY_FAILED = '設定已儲存，但子行程尚未套用成功。請重新整理套用狀態，檢查後再重試啟動。';
const UNAVAILABLE = '管理狀態暫時無法使用。請檢查服務與受保護的設定儲存。';
const OUTCOME = '存檔結果不明時請重新啟動 add-on，之後到「連線與權杖」確認 MCP 網址：若這次換了後端身分，權杖可能已換新，舊網址會失效。';
const NEW_ORIGIN = '網址改到另一台伺服器（scheme、主機或 port 不同）時，不會沿用已儲存的密碼或金鑰：請在同一次儲存中為新網址重新輸入（選填的可以明確清除）。這次未儲存任何變更。';
const FORM_HINT = '網址改到另一台伺服器（scheme、主機或 port 不同）時，不會沿用已儲存的密碼或金鑰：請在同一次儲存中重新輸入（選填的可以明確清除）。只改路徑時沿用已儲存的憑證。';
const mask = letter => letter.repeat(4) + '*'.repeat(20) + letter.repeat(4);
const revision = number => `"c1-${number.toString(16).padStart(64, '0')}"`;
// The default profile's saved Odoo connection (synthetic: .invalid, DUMMY-; its token is the mock's M x 43).
const ODOO = {product: 'odoo', parity: true, parity046: true, configured: true, connection: {url: 'https://odoo.invalid', database: 'DUMMY-db', username: 'DUMMY-user'},
  tokenMask: mask('M'), tokenHistory: []};
const N8N = {product: 'n8n', parity: true, parity046: true, configured: true, connection: {url: 'http://old.test'}};
async function reset(request, data) { await request.post('/__fixture/reset', {data}); }
async function calls(request, filter = () => true) { return (await (await request.get('/__fixture/calls')).json()).filter(filter); }
async function idle(page) { await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true'); }
async function open(page, path) { await page.goto(`${prefix}${path}`); await expect(page.getByRole('heading', {level: 1})).toBeVisible(); await idle(page); }
async function go(page, name) { await page.getByRole('navigation').getByRole('link', {name, exact: true}).click(); await idle(page); }
async function confirm(page, label) { await page.getByRole('dialog').getByRole('button', {name: label, exact: true}).click(); await idle(page); }
async function savePartial(page, changes) {
  for (const [key, value] of Object.entries(changes)) {
    await page.locator(`#patch-${key}-action`).selectOption('set');
    await page.locator(`#patch-${key}`).fill(value);
  }
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
}
async function reveal(page) {
  await page.getByRole('button', {name: '顯示權杖', exact: true}).click();
  await confirm(page, '確認繼續');
  return page.locator('#token-secret code');
}
const keep = (page, key) => page.locator(`#patch-${key}-action option[value=keep]`);

test('an identity change rotates the token: the notice says where the new one is, the page reads the new state, the next save takes its revision', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {}});
  await open(page, '/access');
  await expect(await reveal(page)).toHaveText('M'.repeat(43));
  await go(page, '後端連線');
  await savePartial(page, {username: 'DUMMY-user-two'});
  await expect(page.locator('#notice')).toHaveText(`${PATCHED} ${ROTATED}`);
  // The new state: its mask, the rotation in the history (the old token masked), and the new token where the old was.
  await go(page, '連線與權杖');
  await expect(page.getByText(`目前權杖（遮罩）：${mask('N')}`, {exact: true})).toBeVisible();
  await expect(page.locator('#token-history li')).toHaveCount(1);
  await expect(page.locator('#token-history li')).toContainText('重新產生 · ');
  await expect(page.locator('#token-history li code')).toHaveText(mask('M'));
  await expect(await reveal(page)).toHaveText('N'.repeat(43));
  expect(await page.locator('body').innerText()).not.toContain('M'.repeat(43));
  // The next save takes the new state's revision (HM-11's way: the page is read again; the answer's ETag is the same).
  await go(page, '後端連線');
  await savePartial(page, {password: 'DUMMY-odoo-password-two'});
  await expect(page.locator('#notice')).toHaveText(PATCHED);
  const saves = await calls(request, call => call.operation === 'backend/patch');
  expect(saves.map(call => [call.ifMatch, call.changedKeys, call.profileHeader])).toEqual([[revision(1), ['username'], 'default'], [revision(2), ['password'], 'default']]);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test('on an additional profile the rotation is its own: the whole connection saved anew, the default profile keeps its token', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {extra: [{id: B, label: '會計', configured: true, tokenMask: mask('T'), tokenHistory: [],
    connection: {url: 'https://b.odoo.invalid', database: 'DUMMY-db', username: 'DUMMY-user'}}]}});
  await open(page, '/backend');
  await page.getByLabel('帳號', {exact: true}).selectOption(B);
  await expect(page.locator('.profile-current')).toContainText('目前帳號：會計');
  await idle(page);
  await page.getByLabel('這次要如何處理設定？').selectOption('replace');
  await page.locator('#url').fill('https://b.odoo.invalid');
  await page.locator('#database').fill('DUMMY-db-two');
  await page.locator('#username').fill('DUMMY-user');
  await page.locator('#password').fill('DUMMY-b-odoo-password');
  await page.getByRole('button', {name: '儲存後端設定', exact: true}).click();
  await confirm(page, '確認儲存');
  await expect(page.locator('#notice')).toHaveText(`伺服器已確認儲存。請等待健康探測更新，這不代表後端已連線成功。 ${ROTATED}`);
  await go(page, '連線與權杖');
  await expect(await reveal(page)).toHaveText('N'.repeat(43));
  const [save] = await calls(request, call => call.operation === 'backend');
  expect([save.profileHeader, save.ifMatch]).toEqual([B, `"c1-${B}${'1'.padStart(40, '0')}"`]);
  await page.getByLabel('帳號', {exact: true}).selectOption('default');
  await expect(page.locator('.profile-current')).toContainText('目前帳號：預設帳號');
  await idle(page);
  await expect(await reveal(page)).toHaveText('M'.repeat(43));
});

test('a new child that does not start after an identity change (shape D): both notices, the new state read again, the restart takes its revision', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {rebindFault: 'start'}});
  await open(page, '/backend');
  await savePartial(page, {username: 'DUMMY-user-two'});
  await expect(page.locator('#notice')).toHaveText(`${APPLY_FAILED} ${ROTATED}`);
  await expect(page.locator('#notice')).toHaveClass(/error/);
  await expect(page.locator('#configuration-state')).toHaveAttribute('data-apply-state', 'failed');
  await go(page, '連線與權杖');
  await expect(page.getByText(`目前權杖（遮罩）：${mask('N')}`, {exact: true})).toBeVisible();
  await expect(await reveal(page)).toHaveText('N'.repeat(43));
  await go(page, '診斷與維護');
  await page.getByRole('button', {name: '重新啟動子行程', exact: true}).click();
  await confirm(page, '確認重新啟動');
  await expect(page.locator('#notice')).toContainText('已接受重新啟動請求');
  const restarts = await calls(request, call => call.operation === 'child/restart');
  expect(restarts.map(call => call.ifMatch)).toEqual([revision(2)]);
});

test('a failed identity change: 503 request denied keeps today\'s text; 503 state unavailable adds the restart hint; nothing changed', async ({page, request}) => {
  await reset(request, {...ODOO, profiles: {rebindFault: 'stop'}});
  await open(page, '/backend');
  await savePartial(page, {username: 'DUMMY-user-two'});
  await expect(page.locator('#notice')).toHaveText(UNAVAILABLE);
  await expect(page.locator('#notice')).toHaveClass(/error/);
  await reset(request, {...ODOO, profiles: {rebindFault: 'write'}});
  await open(page, '/backend');
  await savePartial(page, {username: 'DUMMY-user-two'});
  await expect(page.locator('#notice')).toHaveText(`${UNAVAILABLE} ${OUTCOME}`);
  await go(page, '連線與權杖');
  await expect(page.getByText(`目前權杖（遮罩）：${mask('M')}`, {exact: true})).toBeVisible();
  await expect(page.locator('#token-history li')).toHaveCount(0);
  await expect(await reveal(page)).toHaveText('M'.repeat(43));
});

test('a URL moved to another server asks again for the secrets it takes there, before anything is sent; the same server keeps them', async ({page, request}) => {
  await reset(request, {...N8N, profiles: {}});
  await open(page, '/backend');
  await expect(page.locator('#backend-partial')).toContainText(FORM_HINT);
  await expect(page.locator('#patch-key-origin')).toBeHidden();
  await page.locator('#patch-url-action').selectOption('set');
  await page.locator('#patch-url').fill('http://new.test');
  // Both stored secrets go to n8n's one server: typed again (the optional one may be cleared), never kept.
  for (const key of ['key', 'mcp_access_token']) {
    await expect(page.locator(`#patch-${key}-action`)).toHaveValue('set');
    await expect(keep(page, key)).toBeDisabled();
    await expect(page.locator(`#patch-${key}`)).toBeEnabled();
    await expect(page.locator(`#patch-${key}`)).toHaveAttribute('required', '');
    await expect(page.locator(`#patch-${key}`)).toHaveAttribute('aria-describedby', `patch-${key}-origin`);
    await expect(page.locator(`#patch-${key}-origin`)).toBeVisible();
  }
  await expect(page.locator('#patch-key-origin')).toHaveText('網址改到另一台伺服器：請重新輸入，不會沿用已儲存的憑證。');
  await expect(page.locator('#patch-mcp_access_token-origin')).toHaveText('網址改到另一台伺服器：請重新輸入或明確清除，不會沿用已儲存的憑證。');
  // Nothing leaves the form while one is missing.
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.locator('#patch-key').evaluate(input => input.validity.valueMissing)).toBe(true);
  // Back on the stored server (another path): keep is offered again, and chosen again where this rule chose for it.
  await page.locator('#patch-url').fill('http://old.test/sub');
  for (const key of ['key', 'mcp_access_token']) {
    await expect(page.locator(`#patch-${key}-action`)).toHaveValue('keep');
    await expect(keep(page, key)).toBeEnabled();
    await expect(page.locator(`#patch-${key}`)).toBeDisabled();
    await expect(page.locator(`#patch-${key}`)).not.toHaveAttribute('aria-describedby', /./);
    await expect(page.locator(`#patch-${key}-origin`)).toBeHidden();
  }
  // To the new server with the key typed again and the access token cleared: the three are sent, and saved.
  await page.locator('#patch-url').fill('http://new.test');
  await page.locator('#patch-key').fill('DUMMY-new-n8n-key');
  await page.locator('#patch-mcp_access_token-action').selectOption('clear');
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
  await expect(page.locator('#notice')).toHaveText(PATCHED);
  await expect(page.locator('#patch-mcp_access_token-action')).toContainText('保留未設定狀態');
  // Another path on the same server keeps the stored key.
  await page.locator('#patch-url-action').selectOption('set');
  await page.locator('#patch-url').fill('http://new.test/sub');
  await expect(page.locator('#patch-key-action')).toHaveValue('keep');
  await expect(keep(page, 'key')).toBeEnabled();
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
  await expect(page.locator('#notice')).toHaveText(PATCHED);
  const saves = await calls(request, call => call.operation === 'backend/patch');
  expect(saves.map(call => call.changedKeys)).toEqual([['url', 'key', 'mcp_access_token'], ['url']]);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test('a URL moved to another server and a stale revision: the conflict keeps the draft and prevents a blind retry', async ({page, request}) => {
  await reset(request, {...N8N, profiles: {}});
  await open(page, '/backend');
  await page.locator('#patch-url-action').selectOption('set');
  await page.locator('#patch-url').fill('http://draft.test');
  await page.locator('#patch-key').fill('DUMMY-draft-key');
  await page.locator('#patch-mcp_access_token-action').selectOption('clear');
  await request.post('/__fixture/configuration', {data: {changed: true, applyState: 'applied'}});
  await page.getByRole('button', {name: '儲存選定欄位', exact: true}).click();
  await confirm(page, '確認儲存');
  await expect(page.locator('#notice')).toContainText('草稿已保留');
  await expect(page.locator('#patch-url')).toHaveValue('http://draft.test');
  await expect(page.getByRole('button', {name: '儲存選定欄位', exact: true})).toBeDisabled();
  const saves = await calls(request, call => call.operation === 'backend/patch');
  expect(saves.map(call => [call.ifMatch, call.changedKeys])).toEqual([[revision(1), ['url', 'key', 'mcp_access_token']]]);
});

test('a save the add-on refuses as a new origin (422): fixed copy, nothing of the request or the answer shown, typed secrets cleared', async ({page, request}) => {
  // The add-on may count as moved what the page could not know (a stored URL it withholds is asked for anyway; this is
  // the mock answering so): the panel shows its own text only.
  await reset(request, {...ODOO, profiles: {}, saveStatus: 422, saveCode: 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN'});
  await open(page, '/backend');
  await savePartial(page, {url: 'https://odoo.invalid/elsewhere', password: 'DUMMY-typed-password'});
  await expect(page.locator('#notice')).toHaveText(NEW_ORIGIN);
  await expect(page.locator('#notice')).toHaveClass(/error/);
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await expect(page.locator('#patch-password')).toHaveValue('');
  await expect(page.locator('#patch-url')).toHaveValue('https://odoo.invalid/elsewhere');
});

test('switched off: moving the URL keeps every secret choice as before (no hint, no note, keep stays)', async ({page, request}) => {
  await reset(request, N8N);
  await open(page, '/backend');
  await expect(page.locator('#backend-partial')).not.toContainText('不會沿用已儲存的密碼或金鑰');
  await page.locator('#patch-url-action').selectOption('set');
  await page.locator('#patch-url').fill('http://new.test');
  for (const key of ['key', 'mcp_access_token']) {
    await expect(page.locator(`#patch-${key}-action`)).toHaveValue('keep');
    await expect(keep(page, key)).toBeEnabled();
    await expect(page.locator(`#patch-${key}`)).toBeDisabled();
  }
  expect(await page.locator('[id$="-origin"], [data-origin-required]').count()).toBe(0);
});
