// HM-11 (plan 6, 10.3): the panel with profiles switched on, against the LOCAL MOCK (fixtures/server.mjs; not HA
// security or E2E). The single-profile specs run unchanged in both projects; this one switches profiles on itself.
import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const B = '0123456789abcdef01234567', C = 'fedcba9876543210fedcba98';
const evil = '<img src=x onerror="window.injected=1"> 會計';
async function reset(request, data) { await request.post('/__fixture/reset', {data}); }
async function calls(request, filter = () => true) { return (await (await request.get('/__fixture/calls')).json()).filter(filter); }
async function fixtureProfiles(request) { return (await (await request.get('/__fixture/profiles')).json()).profiles; }
const menu = page => page.getByLabel('帳號', {exact: true});
const current = page => page.locator('.profile-current');
async function idle(page) { await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true'); }
async function open(page, path) { await page.goto(`${prefix}${path}`); await expect(page.getByRole('heading', {level: 1})).toBeVisible(); await idle(page); }
async function choose(page, id, name) {
  await menu(page).selectOption(id);
  await expect(current(page)).toContainText(`目前帳號：${name}`);
  await idle(page);
}
async function confirm(page, label) { await page.getByRole('dialog').getByRole('button', {name: label, exact: true}).click(); }
function recordRequests(page) {
  const seen = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    // The mount itself starts with /api/ (Ingress): only the management API after it counts.
    if (path.startsWith(`${prefix}/api/`)) seen.push({path, method: request.method(), profile: request.headers()['x-mcp-profile']});
  });
  return seen;
}

test('menu: the default profile named on every profile-scoped request, none on profile routes; create switches; names stay text', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  const seen = recordRequests(page);
  let alerts = 0;
  page.on('dialog', async dialog => { alerts++; await dialog.dismiss(); });
  await open(page, '/overview');
  await expect(menu(page)).toHaveValue('default');
  await expect(menu(page).locator('option:checked')).toHaveText('預設帳號（default） · 執行中');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.getByRole('button', {name: '改名', exact: true})).toBeDisabled();
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeDisabled();
  // A label the rules refuse never leaves the dialog.
  await page.getByRole('button', {name: '新增帳號', exact: true}).click();
  await page.getByLabel('帳號名稱', {exact: true}).fill('a\u200bb');
  await confirm(page, '建立帳號');
  await expect(page.getByRole('dialog')).toContainText('不能含控制字元、零寬字元或雙向控制字元');
  await page.getByLabel('帳號名稱', {exact: true}).fill(evil);
  await confirm(page, '建立帳號');
  await expect(current(page)).toHaveText(`目前帳號：${evil}（e0000001）`);
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已建立帳號');
  await expect(menu(page).locator('option:checked')).toHaveText(`${evil}（e0000001） · 尚未設定`);
  expect(await page.locator('#app img').count()).toBe(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  // The name stays text on the backend and tools pages (FM-60, FM-64) and in a confirmation's profile line (FM-58)
  // too (align review S-4); the dialog sits outside #app, so every img on the page counts.
  for (const name of ['後端連線', '工具權限']) {
    await page.getByRole('navigation').getByRole('link', {name, exact: true}).click();
    await idle(page);
    await expect(page.locator('.profile-scope')).toContainText(`帳號「${evil}」（e0000001）：`);
    expect(await page.locator('img').count()).toBe(0);
  }
  await page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await expect(page.locator('.dialog-profile')).toHaveText(`帳號：「${evil}」（e0000001）`);
  expect(await page.locator('img').count()).toBe(0);
  await confirm(page, '取消');
  await page.getByRole('navigation').getByRole('link', {name: '總覽', exact: true}).click();
  await idle(page);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  const [create] = await calls(request, call => call.operation === 'profiles');
  expect(create).toMatchObject({method: 'POST', validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`, label: evil});
  expect(create.operationId).toMatch(/^[0-9]{13}\.[0-9a-f]{32}$/);
  expect(create.profileHeader).toBeUndefined();
  // Rename keeps the id; the default profile cannot be renamed or deleted.
  await page.getByRole('button', {name: '改名', exact: true}).click();
  await expect(page.getByLabel('帳號名稱', {exact: true})).toHaveValue(evil);
  await page.getByLabel('帳號名稱', {exact: true}).fill('第二組');
  await confirm(page, '儲存名稱');
  await expect(current(page)).toHaveText('目前帳號：第二組（e0000001）');
  await idle(page);
  const scoped = seen.filter(item => !item.path.includes('/api/profiles'));
  expect(scoped[0]).toMatchObject({path: `${prefix}/api/bootstrap`, profile: undefined});   // the probe
  expect(scoped.slice(1).every(item => ['default', 'e0000001ffffffffffffffff'].includes(item.profile))).toBe(true);
  expect(seen.filter(item => item.path.includes('/api/profiles')).every(item => item.profile === undefined)).toBe(true);
  expect(seen.some(item => item.path.endsWith('/api/profiles') && item.method === 'POST')).toBe(true);
  expect(seen.some(item => item.path.endsWith('/api/profiles/e0000001ffffffffffffffff') && item.method === 'PATCH')).toBe(true);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  expect(alerts).toBe(0);
  await page.setViewportSize({width: 320, height: 860});
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  // The choice lives in memory only (DQ-18): a reload is the default profile again.
  await page.reload();
  await expect(menu(page)).toHaveValue('default');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
});

test('switching hides a revealed token, drops drafts and typed secrets; tokens, endpoint and examples stay per profile', async ({page, request}) => {
  await reset(request, {product: 'n8n', endpoint: 'https://mcp.example.test/mcp', profiles: {extra: [{id: B, label: '會計', configured: true}]}});
  await open(page, '/access');
  await page.getByRole('button', {name: '顯示權杖', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('帳號：「預設帳號」（default）');
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret code')).toHaveText('M'.repeat(43));
  await choose(page, B, '會計');
  await expect(page.locator('#notice')).toContainText('已切換到帳號「會計」（01234567）');
  await expect(page.locator('body')).not.toContainText('M'.repeat(43));
  // The endpoint is the add-on's: shown, not editable here; the example names this profile (DQ-13, DQ-31).
  await expect(page.getByRole('button', {name: '儲存端點', exact: true})).toHaveCount(0);
  await expect(page.locator('main')).toContainText('端點是整個 add-on 共用的設定，只能在預設帳號修改。');
  await expect(page.locator('main')).toContainText('https://mcp.example.test/mcp');
  await expect(page.locator('pre')).toContainText('"woow-n8n-01234567"');
  await page.getByRole('button', {name: '顯示權杖', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('帳號：「會計」（01234567）');
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret code')).toHaveText('T'.repeat(43));
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret code')).toHaveText('T'.repeat(43));
  await choose(page, 'default', '預設帳號');
  await expect(page.locator('body')).not.toContainText('T'.repeat(43));
  await expect(page.locator('pre')).toContainText('"woow"');
  await expect(page.getByRole('button', {name: '儲存端點', exact: true})).toBeVisible();
  // B's rotation left the default profile alone.
  const state = await fixtureProfiles(request);
  expect(state.default.revision).toBe(1);
  expect(state[B].revision).toBe(2);
  const tokens = await calls(request, call => call.operation.startsWith('token/'));
  expect(tokens.map(call => [call.operation, call.profileHeader])).toEqual([['token/reveal', 'default'], ['token/reveal', B], ['token/rotate', B]]);
  // Tool policy is per profile: B's saved policy names B and leaves the default profile's alone.
  await choose(page, B, '會計');
  await page.getByRole('navigation').getByRole('link', {name: '工具權限', exact: true}).click();
  await expect(page.locator('main')).toContainText('帳號「會計」（01234567）：這裡的停用、寫入授權與操作禁止只套用到這個帳號的權杖');
  await page.locator('.tool-row').filter({has: page.getByRole('heading', {name: 'read_example', exact: true})}).getByLabel('停用此工具', {exact: true}).check();
  await page.getByRole('button', {name: '儲存工具權限', exact: true}).click();
  await confirm(page, '確認套用');
  await expect(page.locator('#notice')).toContainText('伺服器已確認儲存工具權限');
  const [policy] = await calls(request, call => call.operation === 'policy');
  expect([policy.profileHeader, policy.policy.disabled]).toEqual([B, ['read_example']]);
  const after = await fixtureProfiles(request);
  expect([after[B].disabled, after.default.disabled]).toEqual([['read_example'], []]);
  await choose(page, 'default', '預設帳號');
  // A draft and a typed secret do not survive a switch, in either direction.
  await page.getByRole('navigation').getByRole('link', {name: '後端連線', exact: true}).click();
  await page.getByLabel('這次要如何處理設定？').selectOption('replace');
  await page.locator('#url').fill('https://draft.example.test');
  await page.locator('#key').fill('SYNTHETIC_DRAFT_SECRET');
  await choose(page, B, '會計');
  // FM-60: the backend page says it edits this profile's own connection.
  await expect(page.locator('.profile-scope')).toHaveText('帳號「會計」（01234567）：這是這個帳號自己的後端連線與憑證；儲存、清除與測試都只用這個帳號的設定，其他帳號不受影響。');
  await expect(page.getByLabel('這次要如何處理設定？')).toHaveValue('preserve');
  await expect(page.locator('#url')).toHaveValue('');
  await choose(page, 'default', '預設帳號');
  await expect(page.getByLabel('這次要如何處理設定？')).toHaveValue('preserve');
  await expect(page.locator('#key')).toHaveValue('');
  expect(await calls(request, call => call.operation === 'backend')).toEqual([]);
});

test('a slow switch can be replaced: its late answer is dropped; during any other task the menu is locked, even redrawn by Back', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: '會計', configured: true, tokenMask: 'TTTT' + '*'.repeat(20) + 'TTTT'}]}});
  await open(page, '/access');
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/bootstrap', async route => {
    if (route.request().headers()['x-mcp-profile'] === B) await held;
    await route.fallback();
  });
  await menu(page).selectOption(B);
  await expect(page.getByRole('status')).toContainText('正在切換到帳號「會計」（01234567）');
  await expect(menu(page)).toBeEnabled();
  await choose(page, 'default', '預設帳號');
  const late = page.waitForResponse(response => response.url().endsWith('/api/bootstrap') && response.request().headers()['x-mcp-profile'] === B);
  release();
  await late;
  await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 200)));
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(menu(page)).toHaveValue('default');
  await expect(page.locator('body')).not.toContainText('TTTT');
  await expect(page.getByRole('button', {name: '儲存端點', exact: true})).toBeVisible();
  await page.unroute('**/api/bootstrap');
  // Any other task locks the menu until it ends.
  let finish;
  const waiting = new Promise(resolve => { finish = resolve; });
  await page.route('**/api/configuration', async route => { await waiting; await route.fallback(); });
  await page.getByRole('button', {name: '更新套用狀態（保留草稿）', exact: true}).click();
  await expect(menu(page)).toBeDisabled();
  finish();
  await expect(menu(page)).toBeEnabled();
  await expect(menu(page)).toHaveValue('default');
  // Back during a task redraws the page (popstate) with an enabled menu: a profile chosen there is still refused
  // until the task ends, and the profile stays (align review S-3).
  await page.getByRole('navigation').getByRole('link', {name: '工具權限', exact: true}).click();
  await idle(page);
  let done;
  const slow = new Promise(resolve => { done = resolve; });
  await page.unroute('**/api/configuration');
  await page.route('**/api/configuration', async route => { await slow; await route.fallback(); });
  await page.getByRole('button', {name: '更新套用狀態（保留草稿）', exact: true}).click();
  await expect(menu(page)).toBeDisabled();
  await page.goBack();
  await expect(page.getByRole('heading', {level: 1})).toHaveText('連線與權杖');
  await expect(menu(page)).toBeEnabled();
  await menu(page).selectOption(B);
  await expect(page.locator('#notice')).toContainText('請等目前的操作完成後再切換帳號');
  await expect(menu(page)).toHaveValue('default');
  done();
  await idle(page);
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.getByRole('button', {name: '儲存端點', exact: true})).toBeVisible();
});

test('deleting asks twice and returns to the default profile, clearing its unconfirmed receipt (also when the list cannot be read afterwards); a profile deleted elsewhere does too', async ({page, request}) => {
  await reset(request, {product: 'n8n', parity: true, profiles: {extra: [{id: B, label: '會計'}, {id: C, label: '出納'}]}});
  await open(page, '/access');
  // Every rotation in this test loses its answer: the profile it ran on keeps an unconfirmed receipt.
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  const receiptOf = id => page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${id}`);
  await choose(page, B, '會計');
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  expect(await receiptOf(B)).not.toBeNull();
  const remove = () => page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await remove();
  await expect(page.getByRole('dialog')).toContainText('MCP 權杖會立即撤銷');
  await expect(page.getByRole('dialog')).toContainText('還原刪除前的備份');
  await confirm(page, '取消');
  await remove();
  await confirm(page, '繼續');
  await expect(page.getByRole('dialog').getByRole('heading')).toHaveText('最後確認：刪除帳號「會計」（01234567）');
  await confirm(page, '取消');
  expect(await calls(request, call => call.method === 'DELETE')).toEqual([]);
  await remove();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#notice')).toContainText('已刪除帳號「會計」（01234567）');
  // B's receipt can never be queried again (§8.8 #84, FM-59): cleared and said so; nothing asks to go back to B.
  // The deletion clears it itself: the switch that follows finds nothing left, so nothing says B was deleted
  // elsewhere (align review S-10).
  await expect(page.locator('#notice')).toContainText('尚未確認的操作紀錄已一併清除');
  await expect(page.locator('#notice')).not.toContainText('請切回該帳號');
  await expect(page.locator('#notice')).not.toContainText('可能已在其他分頁或由其他管理員刪除');
  expect(await receiptOf(B)).toBeNull();
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveCount(0);
  const [deleted] = await calls(request, call => call.method === 'DELETE');
  expect(deleted).toMatchObject({operation: `profiles/${B}`, validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`, fields: []});
  expect(deleted.operationId).toMatch(/^[0-9]{13}\./);
  // C loses a rotation's answer, then is deleted elsewhere: the next request finds it gone.
  await choose(page, C, '出納');
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  const key = `woow-admin-operation-v1:${prefix}:${C}`;
  expect(Object.keys(JSON.parse(await page.evaluate(name => sessionStorage.getItem(name), key))).sort()).toEqual(['id', 'product', 'profile', 'revision', 'route']);
  await request.post('/__fixture/profile', {data: {action: 'delete', id: C}});
  await page.getByRole('button', {name: '查詢操作結果', exact: true}).click();
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#notice')).toContainText('帳號「出納」（fedcba98）已不存在');
  await expect(page.locator('#notice')).toContainText('尚未確認的操作紀錄已一併清除');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toHaveCount(0);
  expect(await page.evaluate(name => sessionStorage.getItem(name), key)).toBeNull();
  // Deleted here while the list cannot be read afterwards (a substitute list proves nothing): the deletion itself
  // cleared the receipt, and nothing asks to go back to the deleted profile (align review S-10).
  const D = 'abcdef0123456789abcdef01';
  await request.post('/__fixture/profile', {data: {action: 'add', spec: {id: D, label: '稽核'}}});
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await idle(page);
  await choose(page, D, '稽核');
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  let removed = false;
  await page.route(`**/api/profiles/${D}`, async route => { const answer = await route.fetch(); removed = true; await route.fulfill({response: answer}); });
  await page.route('**/api/profiles', async route => {
    if (removed && route.request().method() === 'GET') await route.fulfill({status: 503, contentType: 'application/json', body: '{"error":"request denied"}'});
    else await route.fallback();
  });
  await remove();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#profile-list-unavailable')).toBeVisible();
  await expect(page.locator('#notice')).toContainText('已刪除帳號「稽核」（abcdef01）');
  await expect(page.locator('#notice')).toContainText('尚未確認的操作紀錄已一併清除');
  await expect(page.locator('#notice')).not.toContainText('請切回該帳號');
  expect(await receiptOf(D)).toBeNull();
});

test('an answer naming another profile shows nothing: the token stays hidden and the panel reads again', async ({page, request}) => {
  await reset(request, {product: 'n8n', wrongEcho: {operation: 'token/reveal', id: 'default'}, profiles: {extra: [{id: B, label: '會計'}]}});
  await open(page, '/access');
  await choose(page, B, '會計');
  await page.getByRole('button', {name: '顯示權杖', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#notice')).toContainText('伺服器回應的帳號與送出時的帳號不符');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#token-secret')).toBeHidden();
  for (const letter of ['M', 'T']) await expect(page.locator('body')).not.toContainText(letter.repeat(43));
  expect((await calls(request, call => call.operation === 'token/reveal')).map(call => call.profileHeader)).toEqual([B]);
});

test('a receipt kept across the upgrade (four keys, the old key) is queried once profiles are on, naming the default profile', async ({page, request}) => {
  await reset(request, {});
  await open(page, '/access');
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  const record = JSON.parse(await page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}`));
  expect(Object.keys(record).sort()).toEqual(['id', 'product', 'revision', 'route']);
  await request.post('/__fixture/profile', {data: {action: 'switch', profiles: {}}});
  await page.reload();
  await expect(menu(page)).toHaveValue('default');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  const query = page.waitForRequest(item => item.url().endsWith(`/api/operations/${record.id}`));
  await page.getByRole('button', {name: '查詢操作結果', exact: true}).click();
  expect((await query).headers()['x-mcp-profile']).toBe('default');
  await expect(page.locator('#notice')).toContainText('未再次執行');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toHaveCount(0);
  expect(await calls(request, call => call.operation === 'token/rotate')).toHaveLength(1);
});

test('a lost create or delete answer keeps its identity (across a reload); the resend does nothing twice, switches, and clears a deleted profile\'s receipt', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {}, createToken: true});
  await open(page, '/overview');
  let first = true;
  await page.route('**/api/profiles', async route => {
    if (route.request().method() === 'POST' && first) { first = false; await route.fetch(); await route.abort(); }
    else await route.fallback();
  });
  await page.getByRole('button', {name: '新增帳號', exact: true}).click();
  await page.getByLabel('帳號名稱', {exact: true}).fill('出納');
  await confirm(page, '建立帳號');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('無法確認操作結果');
  await expect(page.locator('#pending-profile-operation')).toContainText('建立帳號「出納」尚未取得完成確認');
  await page.reload();
  await expect(page.locator('#pending-profile-operation')).toContainText('建立帳號「出納」尚未取得完成確認');
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(current(page)).toHaveText('目前帳號：出納（e0000001）');
  await expect(page.locator('#notice')).toContainText('已確認建立帳號「出納」');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  const posts = await calls(request, call => call.operation === 'profiles' && call.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[1].operationId).toBe(posts[0].operationId);
  expect(Object.keys(await fixtureProfiles(request))).toEqual(['default', 'e0000001ffffffffffffffff']);
  // The create answer carried a token (a contract violation); the panel never shows one it was not asked to reveal.
  await expect(page.locator('body')).not.toContainText('T'.repeat(43));
  // A lost delete answer, of a profile with an unconfirmed receipt: the resend confirms the delete, and the deleted
  // profile's receipt, which can never be queried again, is cleared and said so (review S-1).
  const E = 'e0000001ffffffffffffffff';
  await page.getByRole('navigation').getByRole('link', {name: '連線與權杖', exact: true}).click();
  await idle(page);
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  let lose = true;
  await page.route(`**/api/profiles/${E}`, async route => {
    if (route.request().method() === 'DELETE' && lose) { lose = false; await route.fetch(); await route.abort(); }
    else await route.fallback();
  });
  await page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#pending-profile-operation')).toContainText('刪除帳號（e0000001）尚未取得完成確認');
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#notice')).toContainText('已確認刪除帳號');
  await expect(page.locator('#notice')).toContainText('尚未確認的操作紀錄已一併清除');
  await expect(page.locator('#notice')).not.toContainText('請切回該帳號');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  expect(await page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${E}`)).toBeNull();
  const deletes = await calls(request, call => call.method === 'DELETE');
  expect(deletes.map(call => call.operationId)).toEqual([deletes[0].operationId, deletes[0].operationId]);
  expect(Object.keys(await fixtureProfiles(request))).toEqual(['default']);
});

// HM-11 review S-1, the other two ways the panel learns that a profile was deleted elsewhere: switching away from it
// (the new list no longer has it) and resending its delete from another profile (profile_not_found is about the profile
// being deleted, not the one shown). Its unconfirmed receipt can never be queried again: cleared and said so, and
// nothing asks to go back to it.
test('deleted elsewhere, learnt when switching away or resending its delete: that profile is named, its receipt cleared', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: '會計'}, {id: C, label: '出納'}]}});
  await open(page, '/access');
  const receiptOf = id => page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${id}`);
  const rotationLost = async () => {
    await page.getByRole('button', {name: '重新產生', exact: true}).click();
    await confirm(page, '確認繼續');
    await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  };
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  // C loses a rotation's answer; then its delete never reaches the server.
  await choose(page, C, '出納');
  await rotationLost();
  let lose = true;
  await page.route(`**/api/profiles/${C}`, async route => {
    if (route.request().method() === 'DELETE' && lose) { lose = false; await route.abort(); }
    else await route.fallback();
  });
  await page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#pending-profile-operation')).toContainText('刪除帳號（fedcba98）尚未取得完成確認');
  // B loses a rotation's answer; then B and C are deleted elsewhere.
  await choose(page, B, '會計');
  await rotationLost();
  for (const id of [B, C]) await request.post('/__fixture/profile', {data: {action: 'delete', id}});
  // Switching away from B: the list read for the default profile no longer has B.
  await choose(page, 'default', '預設帳號');
  await expect(page.locator('#notice')).toContainText('前一個帳號「會計」（01234567）已不存在');
  await expect(page.locator('#notice')).toContainText('它尚未確認的操作紀錄已一併清除');
  await expect(page.locator('#notice')).not.toContainText('請切回該帳號');
  expect(await receiptOf(B)).toBeNull();
  expect(await receiptOf(C)).not.toBeNull();   // only the profile left behind is checked on a switch
  // Resending C's delete from the default profile: it is C that is gone, not the default profile.
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('帳號（fedcba98）已不存在，不需要再刪除');
  await expect(page.locator('#notice')).toContainText('該帳號尚未確認的操作紀錄已一併清除');
  await expect(page.locator('#notice')).not.toContainText('（default）已不存在');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  expect(await receiptOf(C)).toBeNull();
  // The first delete never arrived; the resend found C gone and deleted nothing.
  expect((await calls(request, call => call.method === 'DELETE')).map(call => call.operation)).toEqual([`profiles/${C}`]);
});

// Align review S-1: the one place the panel infers a deletion from a refusal. A resent delete refused with 409
// config_conflict while its profile is still there (the index changed for another reason, here another profile's
// rename) deletes nothing and claims nothing: the profile stays shown and listed, its unconfirmed receipt is kept (its
// token still works), and only the refused delete's identity is released.
test('a resent delete refused while its profile still exists claims no deletion and keeps that profile\'s receipt', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: '會計'}, {id: C, label: '出納'}]}});
  await open(page, '/access');
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  await choose(page, B, '會計');
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  let lose = true;
  await page.route(`**/api/profiles/${B}`, async route => {
    if (route.request().method() === 'DELETE' && lose) { lose = false; await route.abort(); }
    else await route.fallback();
  });
  await page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(page.locator('#pending-profile-operation')).toContainText('刪除帳號（01234567）尚未取得完成確認');
  await request.post('/__fixture/profile', {data: {action: 'rename', id: C, label: '出納二'}});
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('帳號清單已被其他操作更新，這次沒有刪除任何帳號');
  await expect(page.locator('#notice')).not.toContainText('已不存在');
  await expect(current(page)).toHaveText('目前帳號：會計（01234567）');
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveCount(1);
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  expect(await page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${B}`)).not.toBeNull();
  expect(Object.keys(await fixtureProfiles(request))).toContain(B);
  // The first delete never arrived; the resend reached the add-on and was refused.
  expect((await calls(request, call => call.method === 'DELETE')).map(call => call.operation)).toEqual([`profiles/${B}`]);
});

test('a profile whose state cannot be read offers going back and deleting it, still with two confirmations', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: '會計', disabled_reason: 'profile_unavailable', unavailable: true}]}});
  await open(page, '/overview');
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveText('會計（01234567） · 尚未設定 · 設定讀不到，已停用');
  await menu(page).selectOption(B);
  await expect(page.getByRole('heading', {name: '無法載入帳號「會計」（01234567）'})).toBeVisible();
  await expect(page.locator('main')).toContainText('管理狀態暫時無法使用');
  await page.getByRole('button', {name: '刪除帳號', exact: true}).click();
  await confirm(page, '繼續');
  await confirm(page, '確認刪除');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#notice')).toContainText('已刪除帳號「會計」（01234567）');
  await expect(page.locator('#notice')).not.toContainText('尚未確認的操作紀錄');   // nothing was pending: nothing claimed
  const [deleted] = await calls(request, call => call.method === 'DELETE');
  expect(deleted).toMatchObject({operation: `profiles/${B}`, validCsrf: true});
});

// Review S-2 (done with HM-10's API): a list the panel cannot use never locks the page; the default profile stays usable.
test('a list that cannot be read leaves the default profile usable; a corrupt index leaves it alone in the menu and clears no receipt', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {listStatus: 503, extra: [{id: B, label: '會計'}]}});
  await open(page, '/overview');
  await expect(page.locator('#profile-list-unavailable')).toContainText('帳號清單無法讀取');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(menu(page).locator('option')).toHaveCount(1);
  await expect(page.getByRole('button', {name: '新增帳號', exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeDisabled();
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await expect(page.getByRole('heading', {name: '管理介面無法使用'})).toHaveCount(0);
  await reset(request, {product: 'n8n', profiles: {indexCorrupt: true, extra: [{id: B, label: '會計'}]}});
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await idle(page);
  await expect(page.locator('#profile-index-corrupt')).toContainText('帳號索引無法使用');
  await expect(menu(page).locator('option')).toHaveCount(1);
  await expect(page.getByRole('button', {name: '新增帳號', exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeDisabled();
  // A corrupt index's list is no evidence of a deletion (review S-1): switching away from a profile with an unconfirmed
  // receipt into a corrupt index keeps the receipt (it may be queried once the index is back) and claims no deletion.
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: '會計'}]}});
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await idle(page);
  await choose(page, B, '會計');
  await page.getByRole('navigation').getByRole('link', {name: '連線與權杖', exact: true}).click();
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  await reset(request, {product: 'n8n', profiles: {indexCorrupt: true, extra: [{id: B, label: '會計'}]}});
  await choose(page, 'default', '預設帳號');
  await expect(page.locator('#profile-index-corrupt')).toBeVisible();
  await expect(page.locator('#notice')).toContainText('前一個帳號「會計」（01234567）有尚未確認的操作');
  await expect(page.locator('#notice')).not.toContainText('已不存在');
  expect(await page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${B}`)).not.toBeNull();
});

// HM-11 review MF-1 (plan 6: switched off, the DOM is today's): the single-profile specs never look for the profile
// parts, so this one does. Every page, a confirmation and a refresh: no profile menu, heading, note, card or dialog line,
// no profile wording, the restart notice for the whole child, the example named woow; no request names a profile or
// reads the profile list.
test('switched off: no profile menu, line, note or request on any page, in a dialog or after a refresh (the panel as before)', async ({page, request}) => {
  await reset(request, {product: 'emqx', endpoint: 'https://mcp.example.test/mcp'});
  const seen = recordRequests(page);
  const profileUi = page.locator('#profile-select, .profile-bar, .profile-current, .profile-scope, .profile-note, .dialog-profile, #pending-profile-operation, #profile-index-corrupt, #profile-list-unavailable, #profile-list-readonly, #profile-orphans, #profile-index-quarantine');
  const absent = async () => {
    await expect(profileUi).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText(/目前帳號|這個帳號|這是帳號|帳號「|帳號：/);
  };
  const go = async name => {
    await page.getByRole('navigation').getByRole('link', {name, exact: true}).click();
    await idle(page);
    await expect(page.getByRole('heading', {level: 1})).toHaveText(name);
  };
  await open(page, '/overview');
  await absent();
  for (const name of ['後端連線', '工具權限', '連線與權杖', '診斷與維護']) { await go(name); await absent(); }
  await go('連線與權杖');
  await expect(page.locator('main')).toContainText('每個 MCP 服務共用一把 Bearer 權杖');
  await expect(page.locator('pre')).toContainText('"woow"');
  await page.getByRole('button', {name: '顯示權杖', exact: true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await absent();
  await confirm(page, '取消');
  await go('工具權限');
  await page.getByRole('button', {name: '儲存工具權限', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('儲存後會重新啟動 MCP 子行程，現有連線可能中斷。');
  await absent();
  await confirm(page, '取消');
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已取得最新管理狀態');
  await absent();
  // The requests as before: bootstrap and capabilities on load and again on refresh (pages draw without asking), none
  // naming a profile, no probe and no profile list.
  expect(seen).toEqual([0, 1].flatMap(() => ['bootstrap', 'capabilities'].map(name => ({path: `${prefix}/api/${name}`, method: 'GET', profile: undefined}))));
  expect(await calls(request)).toEqual([]);   // both dialogs were cancelled: nothing was sent
});

// ---- HM-11 aligned with HM-10's real management API (2026-11-16): orphans, the index quarantine, read-only lists ----

test('orphans are listed for deletion with two confirmations; a label this browser cannot show names its profile by id only', async ({page, request}) => {
  const O = 'e'.repeat(24);
  await reset(request, {product: 'n8n', profiles: {extra: [{id: B, label: 'a\u202eb'}], orphans: [O]}});
  await open(page, '/overview');
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveText('名稱無法顯示的帳號（01234567） · 尚未設定');
  await expect(page.locator('.profile-note')).toContainText('有 1 筆不在帳號索引裡的帳號資料（孤兒）');
  await choose(page, B, '名稱無法顯示的帳號');
  await expect(page.locator('body')).not.toContainText('a\u202eb');
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeEnabled();
  await choose(page, 'default', '預設帳號');
  await page.getByRole('navigation').getByRole('link', {name: '診斷與維護', exact: true}).click();
  await idle(page);
  const orphans = page.locator('#profile-orphans');
  await expect(orphans).toContainText('帳號資料（eeeeeeee）');
  const remove = () => orphans.getByRole('button', {name: '刪除孤兒帳號資料（eeeeeeee）', exact: true}).click();
  await remove();
  await expect(page.getByRole('dialog')).toContainText('先撤銷它的權杖');
  await confirm(page, '取消');
  await remove();
  await confirm(page, '繼續');
  await expect(page.getByRole('dialog').getByRole('heading')).toHaveText('最後確認：刪除孤兒帳號資料（eeeeeeee）');
  expect(await calls(request, call => call.method === 'DELETE')).toEqual([]);
  await confirm(page, '確認刪除');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已刪除孤兒帳號資料（eeeeeeee）');
  await expect(orphans).toHaveCount(0);
  await expect(page.locator('.profile-note')).toHaveCount(0);
  const [deleted] = await calls(request, call => call.method === 'DELETE');
  expect(deleted).toMatchObject({operation: `profiles/${O}`, validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`, fields: []});
  expect(deleted.profileHeader).toBeUndefined();
});

test('a corrupt index is quarantined after two confirmations and its profiles become orphans; without an index file the panel says to restart', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {indexCorrupt: true, extra: [{id: B, label: '會計'}]}});
  await open(page, '/overview');
  const card = page.locator('#profile-index-corrupt');
  await expect(card).toContainText('帳號索引無法使用');
  const quarantine = () => page.getByRole('button', {name: '隔離帳號索引', exact: true}).click();
  await quarantine();
  await expect(page.getByRole('dialog')).toContainText('撤銷所有額外帳號的 MCP 權杖');
  await confirm(page, '取消');
  await quarantine();
  await confirm(page, '繼續');
  await expect(page.getByRole('dialog').getByRole('heading')).toHaveText('最後確認：隔離帳號索引');
  await confirm(page, '取消');
  expect(await calls(request, call => call.operation === 'profiles/index/quarantine')).toEqual([]);
  await quarantine();
  await confirm(page, '繼續');
  await confirm(page, '確認隔離');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已隔離帳號索引（改名保存為 profiles.json.quarantine-');
  await expect(card).toHaveCount(0);
  await expect(page.locator('.profile-note')).toContainText('有 1 筆不在帳號索引裡的帳號資料');
  await expect(menu(page).locator('option')).toHaveCount(1);
  const [sent] = await calls(request, call => call.operation === 'profiles/index/quarantine');
  expect(sent).toMatchObject({method: 'POST', validCsrf: true, ifMatch: `"p1-f${'1'.padStart(63, '0')}"`, fields: []});
  expect(sent.operationId).toMatch(/^[0-9]{13}\./);
  expect(sent.profileHeader).toBeUndefined();
  // No index file to move aside (the profiles directory could not be listed at the start): only a restart helps.
  await reset(request, {product: 'n8n', profiles: {indexCorrupt: true, noIndexFile: true}});
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await idle(page);
  await quarantine();
  await confirm(page, '繼續');
  await confirm(page, '確認隔離');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('沒有可以隔離的帳號索引檔');
  await expect(page.locator('#notice')).toContainText('重新啟動 add-on');
  await expect(card).toBeVisible();
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
});

test('a list without its ETag is read-only but still shows a deletion; a product without additional profiles has no create button; limit 0 says why', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {noEtag: true, extra: [{id: B, label: '會計'}]}});
  await open(page, '/overview');
  await expect(page.locator('#profile-list-readonly')).toContainText('帳號清單缺少版本資訊');
  await expect(page.getByRole('button', {name: '新增帳號', exact: true})).toHaveCount(0);
  await choose(page, B, '會計');
  await expect(page.getByRole('button', {name: '改名', exact: true})).toBeDisabled();
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeDisabled();
  // Without its ETag the list is still the add-on's whole list (only its version is missing), not a substitute: a
  // profile no longer in it was deleted, and its unconfirmed receipt is cleared (contract 9, the row on a profile list
  // the panel cannot use; align review S-7).
  await page.getByRole('navigation').getByRole('link', {name: '連線與權杖', exact: true}).click();
  await idle(page);
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
  await page.getByRole('button', {name: '重新產生', exact: true}).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('heading', {name: '待確認操作'})).toBeVisible();
  await request.post('/__fixture/profile', {data: {action: 'delete', id: B}});
  await choose(page, 'default', '預設帳號');
  await expect(page.locator('#profile-list-readonly')).toBeVisible();
  await expect(page.locator('#notice')).toContainText('前一個帳號「會計」（01234567）已不存在');
  await expect(page.locator('#notice')).toContainText('它尚未確認的操作紀錄已一併清除');
  expect(await page.evaluate(name => sessionStorage.getItem(name), `woow-admin-operation-v1:${prefix}:${B}`)).toBeNull();
  await reset(request, {product: 'opendesign', profiles: {}});
  await open(page, '/overview');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.getByRole('button', {name: '新增帳號', exact: true})).toHaveCount(0);
  await reset(request, {product: 'n8n', profiles: {limit: 0}});
  await open(page, '/overview');
  await page.getByRole('button', {name: '新增帳號', exact: true}).click();
  await page.getByLabel('帳號名稱', {exact: true}).fill('出納');
  await confirm(page, '建立帳號');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('這個 add-on 目前只能服務預設帳號');
  expect(await calls(request, call => call.method !== 'POST')).toEqual([]);
});

// F2: the list read behind a proxy that makes its ETag weak, W/"p1-..." (the fixture's weakEtag simulates one; measured behind
// Cloudflare on 2026-11-25, the list's ETag stayed strong and only /api/origin-policy turned weak): the revision is the same.
// The list used to be read-only ("帳號清單缺少版本資訊"), with no create, rename or delete and "revoke all" off; now none of
// that, and the strong If-Match goes out as before.
test('F2: a weak ETag on the profile list: not read-only, revoke all on, and a create sends the strong If-Match', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {weakEtag: true, extra: [{id: B, label: '會計', configured: true, status: 'running'}]}});
  const lists = [];
  page.on('response', response => { if (new URL(response.url()).pathname === `${prefix}/api/profiles` && response.request().method() === 'GET') lists.push(response.headers().etag); });
  await open(page, '/overview');
  await expect(page.locator('#profile-list-readonly')).toHaveCount(0);
  expect(lists.length).toBeGreaterThan(0);
  expect(lists.every(value => value.startsWith('W/"p1-'))).toBe(true);
  await page.getByRole('navigation').getByRole('link', {name: '診斷與維護', exact: true}).click();
  await idle(page);
  await expect(page.getByRole('button', {name: '全部撤銷', exact: true})).toBeEnabled();
  await page.getByRole('navigation').getByRole('link', {name: '總覽', exact: true}).click();
  await idle(page);
  await page.getByRole('button', {name: '新增帳號', exact: true}).click();
  await page.getByLabel('帳號名稱', {exact: true}).fill('出納');
  await confirm(page, '建立帳號');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已建立帳號');
  const [post] = await calls(request, call => call.operation === 'profiles' && call.method === 'POST');
  expect(post.ifMatch).toBe(`"p1-${(1).toString(16).padStart(64, '0')}"`);  // strong: quoted, no W/
});

test('a lost create answer whose profile was deleted since: the resend confirms it, says it is gone and stays on the default profile', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {}});
  await open(page, '/overview');
  let first = true;
  await page.route('**/api/profiles', async route => {
    if (route.request().method() === 'POST' && first) { first = false; await route.fetch(); await route.abort(); }
    else await route.fallback();
  });
  await page.getByRole('button', {name: '新增帳號', exact: true}).click();
  await page.getByLabel('帳號名稱', {exact: true}).fill('出納');
  await confirm(page, '建立帳號');
  await idle(page);
  await expect(page.locator('#pending-profile-operation')).toContainText('建立帳號「出納」尚未取得完成確認');
  await request.post('/__fixture/profile', {data: {action: 'delete', id: 'e0000001ffffffffffffffff'}});
  await page.getByRole('button', {name: '重送帳號操作', exact: true}).click();
  await confirm(page, '確認繼續');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已確認先前建立帳號「出納」已完成，但這個帳號（e0000001）之後已被刪除');
  await expect(current(page)).toHaveText('目前帳號：預設帳號（default）');
  await expect(page.locator('#pending-profile-operation')).toHaveCount(0);
  const posts = await calls(request, call => call.operation === 'profiles' && call.method === 'POST');
  expect(posts.map(call => call.operationId)).toEqual([posts[0].operationId, posts[0].operationId]);
});

test('Headscale connector rotation targets the selected profile only', async ({page, request}) => {
  await reset(request, {product: 'headscale', parity: true, endpoint: 'https://mcp.example.test/mcp', profiles: {extra: [{id: B, label: 'Headscale B'}]}});
  await open(page, '/access');
  await choose(page, B, 'Headscale B');
  await page.getByRole('button', {name: '產生新的 Claude.ai 連線網址', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('舊權杖');
  await confirm(page, '確認繼續');
  await expect(page.locator('#claude-secret')).toBeVisible();
  const tokenCalls = await calls(request, call => call.operation?.startsWith('token/'));
  expect(tokenCalls.map(call => [call.operation, call.profileHeader])).toEqual([['token/rotate', B]]);
});

test('the create dialog says Headscale\'s new profile does not copy the headscale_api_keys writes; Odoo\'s says nothing of it (owner decision 2026-11-25)', async ({page, request}) => {
  for (const [product, said] of [['headscale', true], ['odoo', false]]) {
    await reset(request, {product, parity: true, profiles: {}});
    await open(page, '/overview');
    await page.getByRole('button', {name: '新增帳號', exact: true}).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('新帳號會複製預設帳號目前的工具權限與寫入設定，之後各自獨立');
    if (said) {
      await expect(dialog).toContainText('不複製 headscale_api_keys 的建立、作廢與刪除（讀取照複製），預設不能用；需要時到這個帳號的「工具權限」頁自行開啟。');
      await expect(dialog).toContainText('按「重新產生」');
    } else {
      await expect(dialog).not.toContainText('headscale_api_keys');
      await expect(dialog).toContainText('按「顯示權杖」');
    }
    await confirm(page, '取消');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
});
