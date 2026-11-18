// HM-27 (DQ-11 (a); contract 2.6, 3.1, 3.5, 4.1): the add-on's one Origin policy of the secret path on the panel's
// connections page, against the LOCAL MOCK (fixtures/server.mjs; not HA security or E2E). Switched on only (and never
// for Headscale, which keeps its own rule); switched off nothing of it is drawn or asked for.
import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const B = '0123456789abcdef01234567';
const etag = n => `"o1-${n.toString(16).padStart(64, '0')}"`;
async function reset(request, data) { await request.post('/__fixture/reset', {data}); }
async function calls(request, filter = () => true) { return (await (await request.get('/__fixture/calls')).json()).filter(filter); }
async function fixtureOrigin(request) { return (await request.get('/__fixture/origin')).json(); }
const card = page => page.locator('#origin-policy');
const form = page => page.locator('#origin-policy-form');
const list = page => page.getByLabel('允許的來源（每行一個）', {exact: true});
async function idle(page) { await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true'); }
async function open(page, path) { await page.goto(`${prefix}${path}`); await expect(page.getByRole('heading', {level: 1})).toBeVisible(); await idle(page); }
async function confirm(page, label) { await page.getByRole('dialog').getByRole('button', {name: label, exact: true}).click(); }
function originRequests(page) {
  const seen = [];
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/api/origin-policy')) seen.push({method: request.method(), headers: request.headers()}); });
  return seen;
}
async function save(page, mode, text) {
  await form(page).getByRole('radio', {name: mode === 'enforce' ? /^阻擋/ : /^只記錄/}).check();
  await list(page).fill(text);
  await page.getByRole('button', {name: '儲存來源檢查設定', exact: true}).click();
}

test('switched off: no Origin card and no request for it, on any page and product (the panel as before)', async ({page, request}) => {
  for (const product of ['n8n', 'odoo', 'emqx', 'headscale']) {
    await reset(request, {product, parity: true});
    const seen = originRequests(page);
    // HM-27 review S-8: a tab that kept an Origin policy identity, as a switched-on release writes it, shows nothing of
    // it either; switched off the panel never reads that key, so it stays as it was.
    await open(page, '/overview');
    const kept = [`woow-admin-operation-v1:${prefix}:origin-policy`, JSON.stringify({id: `${Date.now() - 1000}.${'0'.repeat(32)}`,
      route: 'origin-policy', revision: etag(1).slice(1, -1), product, mode: 'enforce', allowed_origins: ['https://claude.ai']})];
    await page.evaluate(([key, value]) => sessionStorage.setItem(key, value), kept);
    for (const path of ['/overview', '/access', '/diagnostics']) {
      await open(page, path);
      await expect(card(page)).toHaveCount(0);
      await expect(page.locator('#pending-origin-operation')).toHaveCount(0);
      await expect(page.locator('body')).not.toContainText(/來源檢查|decision=/);
    }
    await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
    await idle(page);
    await expect(page.locator('#pending-origin-operation')).toHaveCount(0);
    expect(seen).toEqual([]);
    expect(await page.evaluate(key => sessionStorage.getItem(key), kept[0])).toBe(kept[1]);
  }
  expect(await calls(request, call => call.operation === 'origin-policy')).toEqual([]);
});

test('switched on: the default policy is shown; a save sends the request with CSRF, If-Match and a key, and the page reads it again', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  const seen = originRequests(page);
  await open(page, '/access');
  await expect(card(page).getByRole('heading', {level: 2})).toHaveText('瀏覽器來源檢查（全 add-on 共用）');
  await expect(card(page)).toContainText('目前是預設值（還沒儲存過）：只記錄，清單只有 https://claude.ai。');
  await expect(card(page)).toContainText('Bearer 接法（/mcp）帶 Origin 一律拒絕（403）');
  await expect(card(page)).toContainText('這裡不會加任何 CORS 標頭');
  await expect(form(page).getByRole('radio', {name: /^只記錄/})).toBeChecked();
  await expect(list(page)).toHaveValue('https://claude.ai');
  expect(seen.map(item => [item.method, item.headers['x-mcp-profile']])).toEqual([['GET', undefined]]);
  await save(page, 'enforce', 'https://claude.ai\n\n  HTTPS://App.Example:443  \n');
  await expect(page.getByRole('dialog')).toContainText('儲存來源檢查設定：阻擋？');
  await expect(page.getByRole('dialog')).toContainText('清單外的來源（含 null、重複或格式不符的 Origin）會收到 403');
  await expect(page.getByRole('dialog')).toContainText('清單 2 個來源');
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toHaveText('已儲存來源檢查設定：阻擋（enforce），清單 2 個來源。所有帳號的密鑰網址都套用這份設定。');
  await expect(card(page)).toContainText('目前：阻擋（enforce），清單 2 個來源。');
  await expect(list(page)).toHaveValue('https://claude.ai\nhttps://app.example');
  await expect(form(page).getByRole('radio', {name: /^阻擋/})).toBeChecked();
  const [put] = await calls(request, call => call.operation === 'origin-policy');
  expect(put).toMatchObject({method: 'PUT', validCsrf: true, ifMatch: etag(1), fields: ['mode', 'allowed_origins'], mode: 'enforce',
    allowed_origins: ['https://claude.ai', 'HTTPS://App.Example:443']});
  expect(put.operationId).toMatch(/^[0-9]{13}\.[0-9a-f]{32}$/);
  expect(put.profileHeader).toBeUndefined();
  expect(await fixtureOrigin(request)).toMatchObject({state: 'saved', mode: 'enforce', allowed: ['https://claude.ai', 'https://app.example']});
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
});

test('switched on, an additional profile shown: the same card (the add-on\'s); its save names no profile', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {extra: [{id: B, label: '會計', configured: true, status: 'running'}]}});
  await open(page, '/access');
  await page.getByLabel('帳號', {exact: true}).selectOption(B);
  await expect(page.locator('.profile-current')).toContainText('目前帳號：會計');
  await idle(page);
  await expect(card(page)).toContainText('所有帳號共用一份');
  await save(page, 'report-only', '');
  await expect(page.getByRole('dialog')).toContainText('清單 0 個來源');
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已儲存來源檢查設定：只記錄（report-only），清單 0 個來源。');
  await expect(page.locator('.profile-current')).toContainText('目前帳號：會計');
  const [put] = await calls(request, call => call.operation === 'origin-policy');
  expect(put.profileHeader).toBeUndefined();
  expect(await fixtureOrigin(request)).toMatchObject({state: 'saved', mode: 'report-only', allowed: []});
});

test('Headscale switched on: no card and no request (it keeps its own rule)', async ({page, request}) => {
  await reset(request, {product: 'headscale', parity: true, profiles: {}});
  const seen = originRequests(page);
  await open(page, '/access');
  await expect(page.getByRole('heading', {level: 1})).toHaveText('連線與權杖');
  await expect(card(page)).toHaveCount(0);
  expect(seen).toEqual([]);
});

test('what the panel can tell is wrong is refused before anything is sent; cancelling sends nothing', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await open(page, '/access');
  await expect(form(page)).toBeVisible();
  for (const [text, message] of [['https://claude.ai\nHTTPS://CLAUDE.AI:443', '第 2 個來源和前面的重複'],
    ['https://claude.ai/', '第 1 個來源不是精確的 http(s) 來源'], ['*', '不是精確的 http(s) 來源'],
    [Array.from({length: 17}, (_, i) => `https://o${i}.example`).join('\n'), '最多 16 個來源（目前 17 個）']]) {
    await save(page, 'enforce', text);
    await expect(page.locator('#notice')).toContainText(message);
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  await save(page, 'report-only', 'https://claude.ai');
  await expect(page.getByRole('dialog')).toContainText('清單外的來源照常服務、回應不變，只在 add-on 日誌記一行 decision=would_deny');
  await confirm(page, '取消');
  expect(await calls(request, call => call.operation === 'origin-policy')).toEqual([]);
});

test('the add-on refuses the list (422): fixed text, nothing saved, the identity released', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await open(page, '/access');
  await save(page, 'enforce', 'https://bad_host.example');  // the panel's shape check lets it through; the add-on's rule does not
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('來源檢查設定不符合規則');
  await expect(page.locator('#notice')).not.toContainText('bad_host');
  await expect(page.locator('#pending-origin-operation')).toHaveCount(0);
  expect(await fixtureOrigin(request)).toMatchObject({state: 'default', mode: 'report-only'});
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
});

test('changed by another administrator meanwhile: 409, the page reads it again and says so, nothing saved', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await open(page, '/access');
  await expect(form(page)).toBeVisible();
  await request.post('/__fixture/origin', {data: {mode: 'enforce', allowed: ['https://other.example']}});
  await save(page, 'report-only', 'https://claude.ai');
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(page.locator('#notice')).toHaveText('來源檢查設定已被其他操作更新，這次沒有儲存；已重新讀取，請確認後再儲存。');
  await expect(card(page)).toContainText('目前：阻擋（enforce），清單 1 個來源。');
  await expect(list(page)).toHaveValue('https://other.example');
  expect(await fixtureOrigin(request)).toMatchObject({mode: 'enforce', allowed: ['https://other.example']});
  await expect(page.locator('#pending-origin-operation')).toHaveCount(0);
});

test('an unusable policy file: said so, the defaults filled in, a save replaces it', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {originUnusable: true}});
  await open(page, '/access');
  await expect(card(page)).toContainText('設定檔無法使用');
  await expect(card(page)).toContainText('密鑰網址的 MCP 請求暫停服務（503），直到在這裡儲存新的設定');
  await expect(list(page)).toHaveValue('https://claude.ai');
  await expect(form(page).getByRole('radio', {name: /^只記錄/})).toBeChecked();
  await page.getByRole('button', {name: '儲存來源檢查設定', exact: true}).click();
  await confirm(page, '確認儲存');
  await idle(page);
  await expect(card(page)).toContainText('目前：只記錄（report-only），清單 1 個來源。');
  expect(await fixtureOrigin(request)).toMatchObject({state: 'saved', mode: 'report-only', allowed: ['https://claude.ai']});
});

test('a lost answer: the unconfirmed card on every page and after a reload; a resend with the same key confirms it once', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await open(page, '/access');
  await page.route('**/api/origin-policy', async route => {
    if (route.request().method() !== 'PUT') return route.fallback();
    await route.fetch();
    await route.abort();
  });
  await save(page, 'enforce', 'https://claude.ai');
  await confirm(page, '確認儲存');
  await idle(page);
  const pending = page.locator('#pending-origin-operation');
  await expect(pending.getByRole('heading', {level: 2})).toHaveText('來源檢查設定尚未確認');
  await expect(pending).toContainText('儲存來源檢查設定（阻擋（enforce），清單 1 個來源）尚未取得完成確認');
  await page.unroute('**/api/origin-policy');
  await page.getByRole('navigation').getByRole('link', {name: '總覽', exact: true}).click();
  await idle(page);
  await expect(pending).toBeVisible();
  await page.reload();
  await idle(page);
  await expect(pending).toBeVisible();
  await pending.getByRole('button', {name: '重送來源設定', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('已完成的操作只回傳收據');
  await confirm(page, '確認繼續');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已確認先前的來源檢查設定已儲存；沒有再次執行。');
  await expect(pending).toHaveCount(0);
  const puts = await calls(request, call => call.operation === 'origin-policy');
  expect(puts).toHaveLength(2);
  expect(puts[1].operationId).toBe(puts[0].operationId);
  expect(puts[1].ifMatch).toBe(puts[0].ifMatch);
  expect((await fixtureOrigin(request)).receipts).toBe(1);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
});

test('the unconfirmed card: acknowledging it only forgets this tab\'s identity', async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await open(page, '/access');
  await page.route('**/api/origin-policy', async route => {
    if (route.request().method() !== 'PUT') return route.fallback();
    await route.abort();
  });
  await save(page, 'enforce', 'https://claude.ai');
  await confirm(page, '確認儲存');
  await idle(page);
  await page.unroute('**/api/origin-policy');
  const pending = page.locator('#pending-origin-operation');
  await pending.getByRole('button', {name: '已核對來源設定', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('不會復原或證明先前操作未執行');
  await confirm(page, '確認繼續');
  await idle(page);
  await expect(page.locator('#notice')).toContainText('已結束此分頁的來源設定追蹤。');
  await expect(pending).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(await calls(request, call => call.operation === 'origin-policy')).toEqual([]);  // the aborted one never arrived
});

for (const width of [1440, 320]) test(`the card fits the page and stays text at ${width} px`, async ({page, request}) => {
  await reset(request, {product: 'odoo', parity: true, profiles: {}});
  await page.setViewportSize({width, height: 900});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await open(page, '/access');
  await expect(form(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  expect(await card(page).locator('script, img, iframe').count()).toBe(0);
  expect(errors).toEqual([]);
});
