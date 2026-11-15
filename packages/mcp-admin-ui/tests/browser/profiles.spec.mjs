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
  // A draft and a typed secret do not survive a switch, in either direction.
  await page.getByRole('navigation').getByRole('link', {name: '後端連線', exact: true}).click();
  await page.getByLabel('這次要如何處理設定？').selectOption('replace');
  await page.locator('#url').fill('https://draft.example.test');
  await page.locator('#key').fill('SYNTHETIC_DRAFT_SECRET');
  await choose(page, B, '會計');
  await expect(page.getByLabel('這次要如何處理設定？')).toHaveValue('preserve');
  await expect(page.locator('#url')).toHaveValue('');
  await choose(page, 'default', '預設帳號');
  await expect(page.getByLabel('這次要如何處理設定？')).toHaveValue('preserve');
  await expect(page.locator('#key')).toHaveValue('');
  expect(await calls(request, call => call.operation === 'backend')).toEqual([]);
});

test('a slow switch can be replaced: its late answer is dropped; during any other task the menu is locked', async ({page, request}) => {
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
});

test('deleting asks twice and returns to the default profile; a profile deleted elsewhere does too, its unconfirmed receipt cleared', async ({page, request}) => {
  await reset(request, {product: 'n8n', parity: true, profiles: {extra: [{id: B, label: '會計'}, {id: C, label: '出納'}]}});
  await open(page, '/access');
  await choose(page, B, '會計');
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
  await expect(menu(page).locator(`option[value="${B}"]`)).toHaveCount(0);
  const [deleted] = await calls(request, call => call.method === 'DELETE');
  expect(deleted).toMatchObject({operation: `profiles/${B}`, validCsrf: true, ifMatch: `"p1-${'1'.padStart(64, '0')}"`, fields: []});
  expect(deleted.operationId).toMatch(/^[0-9]{13}\./);
  // C loses a rotation's answer, then is deleted elsewhere: the next request finds it gone.
  await choose(page, C, '出納');
  await page.route('**/api/token/rotate', async route => { await route.fetch(); await route.abort(); });
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

test('a lost create answer keeps its identity across a reload; the resend creates nothing twice and switches to the profile', async ({page, request}) => {
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
  const [deleted] = await calls(request, call => call.method === 'DELETE');
  expect(deleted).toMatchObject({operation: `profiles/${B}`, validCsrf: true});
});

test('a list that cannot be read blocks the page with a retry; a corrupt index leaves the default profile alone in the menu', async ({page, request}) => {
  await reset(request, {product: 'n8n', profiles: {listStatus: 503, extra: [{id: B, label: '會計'}]}});
  await page.goto(`${prefix}/overview`);
  await expect(page.getByRole('heading', {name: '管理介面無法使用'})).toBeVisible();
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await reset(request, {product: 'n8n', profiles: {indexCorrupt: true, extra: [{id: B, label: '會計'}]}});
  await page.getByRole('button', {name: '重新檢查權限', exact: true}).click();
  await expect(page.locator('#profile-index-corrupt')).toContainText('帳號索引無法使用');
  await expect(menu(page).locator('option')).toHaveCount(1);
  await expect(page.getByRole('button', {name: '新增帳號', exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: '刪除帳號', exact: true})).toBeDisabled();
});
