import { test, expect } from '../owned-fixture.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const prefix = '/api/hassio_ingress/DUMMY';
const evidence = process.env.UI_EVIDENCE_DIR ?? fileURLToPath(new URL('../../test-results/mock-evidence/', import.meta.url));
const measurements = [];
async function reset(request, options = {}) { await request.post('/__fixture/reset', { data: options }); }
async function calls(request) { return (await request.get('/__fixture/calls')).json(); }
async function start(page, path = '/overview') { await page.goto(`${prefix}${path}`); await expect(page.getByRole('heading', { level: 1 })).toBeVisible(); }
async function assertBrandAccent(page) {
  await page.evaluate(() => document.fonts.ready);
  const accent = await page.evaluate(() => ({
    loaded: [...document.fonts].some(face => face.family.replaceAll('"', '') === 'Yellowtail' && face.status === 'loaded'),
    elements: [...document.querySelectorAll('body *')].filter(node => getComputedStyle(node).fontFamily.includes('Yellowtail')).map(node => ({
      tag: node.tagName, text: node.textContent.trim(), visible: node.getClientRects().length > 0,
    })),
  }));
  expect(accent.loaded, 'Self-hosted Yellowtail must actually load').toBe(true);
  expect(accent.elements, 'Exactly one visible accent word; never body copy').toEqual([{ tag: 'SPAN', text: 'Welcome', visible: true }]);
  return accent;
}
async function confirm(page, label = '確認儲存') { await page.getByRole('dialog').getByRole('button', { name: label, exact: true }).click(); }
async function fillConnection(page, product) {
  await page.getByLabel('這次要如何處理設定？').selectOption('replace');
  const values = {
    odoo: { url: 'https://odoo.example.test', database: 'mock_db', username: 'mock_user', password: 'MOCK_ONLY_INPUT' },
    'odoo-manage': { url: 'https://odoo.example.test', database: 'mock_db', username: 'mock_user', api_key: 'MOCK_ONLY_INPUT' },
    n8n: { url: 'https://n8n.example.test', key: 'MOCK_ONLY_INPUT' },
    hermes: { gateway_url: 'https://hermes.example.test', gateway_api_key: 'MOCK_ONLY_INPUT' },
    opendesign: { url: 'https://design.example.test' },
    emqx: { url: 'https://emqx.example.test', api_key: 'MOCK_ONLY_INPUT', api_secret: 'MOCK_ONLY_INPUT' },
    litellm: { url: 'https://litellm.example.test', master_key: 'MOCK_ONLY_INPUT' },
    nextcloud: { url: 'https://cloud.example.test', username: 'mock_user', app_password: 'MOCK_ONLY_INPUT' },
  };
  for (const [field, value] of Object.entries(values[product])) await page.locator(`#${field}`).fill(value);
}
test.beforeEach(async ({ request }) => reset(request));
test.afterAll(async () => { await mkdir(evidence, { recursive: true }); await writeFile(`${evidence}/browser-metrics.json`, JSON.stringify({ scope: 'LOCAL MOCK ONLY — not HA security/E2E', measurements }, null, 2)); });

test('MOCK Yellowtail loads for exactly one warm accent word on every route and mount', async ({ page }) => {
  for (const width of [1440, 320, 360]) {
    await page.setViewportSize({ width, height: 860 });
    for (const mount of ['', prefix]) {
      for (const view of ['overview', 'backend', 'tools', 'access']) {
        await page.goto(`${mount}/${view}`);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        await assertBrandAccent(page);
      }
    }
  }
});

for (const width of [1440, 320, 360]) {
  test(`MOCK ${width}px prefix, all views, local fonts/MDI, targets, refresh and screenshots`, async ({ page, request, baseURL: origin }) => {
    await reset(request, { product: 'n8n', granular: true, endpoint: 'https://mcp.example.test:8081/mcp' });
    await page.setViewportSize({ width, height: width > 400 ? 1000 : 860 });
    const failures = [];
    const external = [];
    const loaded = [];
    page.on('pageerror', error => failures.push(error.message));
    page.on('console', message => { if (message.type() === 'error') failures.push(message.text()); });
    page.on('request', req => { if (!req.url().startsWith(origin)) external.push(req.url()); });
    page.on('response', res => { if (res.url().includes('/assets/')) loaded.push({ path: new URL(res.url()).pathname, status: res.status() }); });
    await start(page);
    await page.evaluate(() => document.fonts.ready);
    const fonts = await page.evaluate(async () => {
      const specs = [['Poppins', '500 20px Poppins', 'MCP'], ['Outfit', '400 16px Outfit', 'MCP'], ['Yellowtail', '400 24px Yellowtail', 'Welcome'], ['Noto Sans TC', '400 16px "Noto Sans TC"', '管理連線'], ['Material Design Icons', '24px "Material Design Icons"', '\uDB80\uDF35']];
      return Promise.all(specs.map(async ([name, descriptor, text]) => {
        const faces = await document.fonts.load(descriptor, text);
        return { name, loaded: faces.length > 0 && faces.every(face => face.status === 'loaded') && document.fonts.check(descriptor, text) };
      }));
    });
    expect(fonts.filter(font => !font.loaded)).toEqual([]);
    expect(await page.locator('.mdi').first().evaluate(node => getComputedStyle(node, '::before').content)).not.toBe('none');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: '跳至主要內容' })).toBeFocused();
    const focus = await page.getByRole('link', { name: '跳至主要內容' }).evaluate(node => ({ style: getComputedStyle(node).outlineStyle, width: getComputedStyle(node).outlineWidth }));
    expect(focus.style).toBe('solid');
    expect(focus.width).toBe('3px');
    for (const [view, label] of [['overview', '總覽'], ['backend', '後端連線'], ['tools', '工具權限'], ['access', '連線與權杖']]) {
      await page.getByRole('navigation').getByRole('link', { name: label, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`${prefix}/${view}$`));
      if (view === 'backend') await page.getByLabel('這次要如何處理設定？').selectOption('replace');
      const accent = await assertBrandAccent(page);
      const layout = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth,
        shortTargets: [...document.querySelectorAll('button, nav a, input:not([type=checkbox]), select, label.check')].filter(node => node.getClientRects().length).filter(node => node.getBoundingClientRect().height < 44).map(node => node.tagName),
      }));
      expect(layout.document).toBeLessThanOrEqual(width);
      expect(layout.shortTargets).toEqual([]);
      if (view === 'overview' || view === 'backend') {
        await mkdir(evidence, { recursive: true });
        await page.screenshot({ path: `${evidence}/mock-${width}-${view}.png`, fullPage: true });
      }
      measurements.push({ width, view, ...layout, fonts, focus, accent });
      await page.reload();
      await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible();
    }
    expect(external).toEqual([]);
    expect(failures).toEqual([]);
    expect(loaded.some(asset => asset.path.endsWith('.css') && asset.status === 200)).toBe(true);
    expect(loaded.some(asset => asset.path.includes('materialdesignicons') && asset.status === 200)).toBe(true);
    expect(loaded.every(asset => asset.path.startsWith(`${prefix}/assets/`) && asset.status === 200)).toBe(true);
  });
}
for (const product of ['odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud']) {
  test(`MOCK ${product} typed replace / preserve / clear`, async ({ page, request }) => {
    await reset(request, { product, configured: true });
    await start(page, '/backend');
    await page.getByRole('button', { name: '儲存後端設定', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('未送出變更');
    expect(await calls(request)).toHaveLength(0);
    await fillConnection(page, product);
    if (product === 'opendesign') await expect(page.locator('input[type=password]')).toHaveCount(0);
    else {
      for (const input of await page.locator('input[type=password]').all()) await expect(input).toHaveAttribute('autocomplete', 'new-password');
    }
    await page.getByRole('button', { name: '儲存後端設定', exact: true }).click();
    await confirm(page);
    await expect(page.getByRole('status')).toContainText('伺服器已確認儲存');
    expect((await calls(request))[0]).toMatchObject({ operation: 'backend', method: 'PUT', validCsrf: true, fields: product === 'n8n' ? ['url', 'key', 'mcp_access_token'] : ['connection'] });
    expect(await page.locator('body').textContent()).not.toContain('MOCK_ONLY_INPUT');
    expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
    await page.getByLabel('這次要如何處理設定？').selectOption('clear');
    await page.getByRole('button', { name: '儲存後端設定', exact: true }).click();
    await confirm(page);
    await expect(page.getByRole('status')).toContainText('伺服器已確認儲存');
    await expect(page.getByText('尚未設定', { exact: true })).toBeVisible();
  });
}
test('MOCK denied bootstrap and denied save show truthful permission failure, no login or success', async ({ page, request }) => {
  await reset(request, { deniedBootstrap: true });
  await start(page);
  await expect(page.getByRole('heading', { name: '管理介面無法使用' })).toBeVisible();
  await expect(page.getByText('請從原服務入口確認你的管理權限，再重新開啟此頁。')).toBeVisible();
  await expect(page.locator('form')).toHaveCount(0);
  await reset(request, { deniedSave: true });
  await start(page, '/backend');
  await fillConnection(page, 'n8n');
  await page.getByRole('button', { name: '儲存後端設定', exact: true }).click();
  await confirm(page);
  await expect(page.getByRole('heading', { name: '管理介面無法使用' })).toBeVisible();
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await expect(page.locator('body')).not.toContainText('已確認儲存');
});
test('MOCK unreviewed HA Core: the denied view names the version, nothing else from the answer renders', async ({ page, request }) => {
  await reset(request, { unreviewedCore: '2026.11.0' });
  await start(page);
  await expect(page.getByRole('heading', { name: '管理介面無法使用' })).toBeVisible();
  await expect(page.getByText('這個 HA Core 版本尚未審核：2026.11.0。', { exact: false })).toBeVisible();
  await expect(page.getByText('MCP 端點不經過這項檢查，照常服務', { exact: false })).toBeVisible();
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await reset(request, { unreviewedCore: '<img src=x onerror="window.coreInjected=1">' });
  await start(page);
  await expect(page.getByText('這個 HA Core 版本尚未審核：（版本字串無法辨識）', { exact: false })).toBeVisible();
  await expect(page.locator('body')).not.toContainText('onerror');
  expect(await page.evaluate(() => window.coreInjected)).toBeUndefined();
  expect(await page.locator('#app img').count()).toBe(0);
});
test('MOCK missing CSRF prevents any mutation; validation / 503 save failures are sanitized', async ({ page, request }) => {
  for (const options of [{ missingCsrf: true }, { saveStatus: 422 }, { saveStatus: 503 }]) {
    await reset(request, options);
    await start(page, '/access');
    await page.getByLabel('MCP 用戶端端點').fill('https://mcp.example.test/mcp');
    await page.getByRole('button', { name: '儲存端點', exact: true }).click();
    await expect(page.getByRole('status')).toContainText(options.missingCsrf ? '缺少有效安全驗證' : options.saveStatus === 422 ? '欄位驗證未通過' : '管理狀態暫時無法使用');
    await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
    if (options.missingCsrf) expect(await calls(request)).toHaveLength(0);
  }
});
test('MOCK rotation cancellation / reveal / hiding / revoke use deliberate CSRF POST only', async ({ page, request }) => {
  await start(page, '/access');
  await page.getByRole('button', { name: '重新產生', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('button', { name: '取消' })).toBeFocused();
  await page.keyboard.press('Escape');
  expect(await calls(request)).toHaveLength(0);
  await expect(page.getByRole('button', { name: '重新產生', exact: true })).toBeFocused();
  await page.getByRole('button', { name: '顯示權杖', exact: true }).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret')).toBeVisible();
  expect(await page.locator('pre').textContent()).toContain('<YOUR_ADDON_TOKEN>');
  await page.getByRole('button', { name: '立即隱藏' }).click();
  await expect(page.locator('#token-secret')).toBeHidden();
  await page.getByRole('button', { name: '重新產生', exact: true }).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret')).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await expect(page.locator('#token-secret')).toBeHidden();
  await page.getByRole('button', { name: '撤銷權杖', exact: true }).click();
  await confirm(page, '確認撤銷');
  await expect(page.getByRole('status')).toContainText('權杖已撤銷');
  await expect(page.getByRole('button', { name: '顯示權杖', exact: true })).toBeDisabled();
  await expect(page.getByText('已撤銷 / 未啟用', { exact: true })).toBeVisible();
  expect((await calls(request)).map(call => ({ operation: call.operation, method: call.method, validCsrf: call.validCsrf }))).toEqual(['token/reveal', 'token/rotate', 'token/revoke'].map(operation => ({ operation, method: 'POST', validCsrf: true })));
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  expect(page.url()).not.toContain('MMMM');
});
test('MOCK token card renders only masked current and bounded history values', async ({ page, request }) => {
  const mask = 'Ab12' + '*'.repeat(20) + 'xy_9';
  await reset(request, { tokenMask: mask, tokenHistory: [{ action: 'rotate',
    rotated_at: '2026-10-29T00:00:00+00:00', previous_token_masked: mask }] });
  await start(page, '/access');
  await expect(page.getByText(`目前權杖（遮罩）：${mask}`)).toBeVisible();
  await expect(page.locator('#token-history li')).toHaveCount(1);
  await expect(page.locator('#token-history li')).toContainText(`重新產生 · 2026-10-29T00:00:00+00:00 · ${mask}`);
  await expect(page.locator('body')).not.toContainText('S'.repeat(43));
  await reset(request, { tokenMask: 'S'.repeat(43), tokenHistory: [{ action: 'rotate',
    rotated_at: '2026-10-29T00:00:00+00:00', previous_token_masked: 'S'.repeat(43) }] });
  await page.reload();
  await expect(page.getByText('權杖歷史格式不相容；請重新整理或更新附加元件。')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('S'.repeat(43));
});
test('MOCK explicit endpoint and clipboard defaults never guess ingress origin or include token', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await start(page, '/access');
  await expect(page.locator('pre')).toContainText('YOUR-MCP-HOST');
  await expect(page.locator('pre')).not.toContainText('127.0.0.1');
  await page.getByLabel('MCP 用戶端端點').fill('https://mcp.example.test:8081/mcp');
  await page.getByRole('button', { name: '儲存端點', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('MCP 端點已儲存');
  await page.getByRole('button', { name: '複製佔位範例' }).click();
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toContain('https://mcp.example.test:8081/mcp');
  expect(clip).toContain('<YOUR_ADDON_TOKEN>');
});
test('MOCK Claude.ai connector URL needs a saved endpoint, a deliberate CSRF reveal, and hides like the token', async ({ page, context, request }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await start(page, '/access');
  const show = page.getByRole('button', { name: '顯示 Claude.ai 連線網址', exact: true });
  await expect(show).toBeDisabled();
  await expect(page.getByText('尚未設定 MCP 用戶端端點：', { exact: false })).toBeVisible();
  await expect(page.locator('body')).not.toContainText('private_');
  await page.getByLabel('MCP 用戶端端點').fill('https://mcp.example.test:8443/mcp');
  await page.getByRole('button', { name: '儲存端點', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('MCP 端點已儲存');
  await expect(page.locator('#claude-secret')).toBeHidden();
  await expect(page.locator('body')).not.toContainText('private_');
  await show.click();
  await page.getByRole('dialog').getByRole('button', { name: '取消' }).click();
  expect((await calls(request)).filter(call => call.operation.startsWith('token/'))).toHaveLength(0);
  await show.click();
  await confirm(page, '確認繼續');
  const url = `https://mcp.example.test:8443/private_${'M'.repeat(43)}/mcp`;
  await expect(page.locator('#claude-secret code')).toHaveText(url);
  await expect(page.locator('#token-secret')).toBeHidden();
  await page.getByRole('button', { name: '複製 Claude.ai 連線網址', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(url);
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await expect(page.locator('#claude-secret')).toBeHidden();
  await expect(page.locator('body')).not.toContainText('private_');
  expect((await calls(request)).filter(call => call.operation.startsWith('token/')).map(call => ({ operation: call.operation, method: call.method, validCsrf: call.validCsrf })))
    .toEqual([{ operation: 'token/reveal', method: 'POST', validCsrf: true }]);
  await page.getByRole('button', { name: '撤銷權杖', exact: true }).click();
  await confirm(page, '確認撤銷');
  await expect(page.getByRole('status')).toContainText('權杖已撤銷');
  await expect(show).toBeDisabled();
  expect(page.url()).not.toContain('MMMM');
});
test('MOCK per-tool/per-operation grants and disabled controls; legacy broad writes never enabled', async ({ page, request }) => {
  await reset(request, { granular: true });
  await start(page, '/tools');
  await page.getByLabel('明確允許此工具寫入').check();
  await page.getByLabel('允許寫入操作：create', { exact: true }).check();
  await page.getByRole('button', { name: '儲存工具權限' }).click();
  await confirm(page, '確認套用');
  await expect(page.getByRole('status')).toContainText('伺服器已確認儲存工具權限');
  expect((await calls(request))[0].policy).toEqual({ writes_enabled: false, disabled: [], enabled_write_tools: ['write_example', 'mixed_example:create'] });
  const writer = page.locator('.tool-row').filter({ has: page.getByRole('heading', { name: 'write_example', exact: true }) });
  await writer.getByLabel('停用此工具').check();
  await expect(writer.getByLabel('明確允許此工具寫入')).toBeDisabled();
  await expect(writer.getByLabel('明確允許此工具寫入')).not.toBeChecked();
  await reset(request, { legacyWrites: true });
  await page.reload();
  await expect(page.getByLabel('明確允許此工具寫入')).toBeChecked();
  await page.getByLabel('明確允許此工具寫入').uncheck();
  await expect(page.getByText('注意：伺服器回報舊版全域寫入目前開啟（新安裝的預設）。此頁不將它標示為唯讀；儲存後改以下方逐項勾選為準，未勾選的寫入即關閉。')).toBeVisible();
  await page.getByRole('button', { name: '儲存工具權限' }).click();
  await confirm(page, '確認套用');
  await expect(page.getByRole('status')).toContainText('伺服器已確認儲存工具權限');
  expect((await calls(request))[0].policy).toEqual({ writes_enabled: false, disabled: [], enabled_write_tools: [] });
});
test('MOCK a new install shows every write allowed with a risk note; unticking one saves exactly the rest', async ({ page, request }) => {
  // What a new state holds since 2026-10-15: the legacy switch and every exact grant on.
  await reset(request, { legacyWrites: true, grants: ['write_example', 'mixed_example:create', 'mixed_example:delete'] });
  await start(page, '/tools');
  await expect(page.getByText('目前已儲存政策：停用 0 個工具，允許 3 / 3 項寫入授權。')).toBeVisible();
  for (const label of ['明確允許此工具寫入', '允許寫入操作：create', '允許寫入操作：delete']) await expect(page.getByLabel(label, { exact: true })).toBeChecked();
  await page.getByLabel('允許寫入操作：delete', { exact: true }).uncheck();
  await page.getByRole('button', { name: '儲存工具權限' }).click();
  await confirm(page, '確認套用');
  await expect(page.getByRole('status')).toContainText('伺服器已確認儲存工具權限');
  expect((await calls(request))[0].policy).toEqual({ writes_enabled: false, disabled: [], enabled_write_tools: ['write_example', 'mixed_example:create'] });
});
test('MOCK token expires, and a reveal completing after focus loss stays hidden', async ({ page }) => {
  await start(page, '/access');
  await page.clock.install();
  await page.getByRole('button', { name: '顯示權杖', exact: true }).click();
  await confirm(page, '確認繼續');
  await expect(page.locator('#token-secret')).toBeVisible();
  await page.clock.fastForward(61000);
  await expect(page.locator('#token-secret')).toBeHidden();
  await page.route('**/api/token/reveal', async route => {
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    await route.fallback(); // preserve blur-before-response, then the context ownership guard
  });
  await page.getByRole('button', { name: '顯示權杖', exact: true }).click();
  await confirm(page, '確認繼續');
  await expect(page.getByRole('status')).toContainText('權杖未顯示');
  await expect(page.locator('#token-secret')).toBeHidden();
});
test('MOCK changing grant contract on fresh bootstrap prevents stale writes', async ({ page, request }) => {
  await reset(request, { granular: true });
  await start(page, '/tools');
  const before = (await (await request.get(`${prefix}/api/configuration`)).json()).configuration.revision;
  expect(before).toMatch(/^c1-[a-f0-9]{64}$/);
  await page.getByLabel('明確允許此工具寫入').check();
  await reset(request, { granular: false });
  // Runtime contract drift can occur without a persisted configuration edit.
  expect((await (await request.get(`${prefix}/api/configuration`)).json()).configuration.revision).toBe(before);
  await page.getByRole('button', { name: '儲存工具權限' }).click();
  await confirm(page, '確認套用');
  await expect(page.getByRole('status')).toContainText('工具授權版本已變更');
  await expect(page.getByLabel('明確允許此工具寫入')).toBeChecked();
  expect(await calls(request)).toHaveLength(0);
});
test('MOCK all product forms fit 320px and dashboard is validated as a triplet', async ({ page, request }) => {
  await page.setViewportSize({ width: 320, height: 860 });
  for (const product of ['odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud']) {
    await reset(request, { product });
    await start(page, '/backend');
    await fillConnection(page, product);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
    if (product === 'hermes') {
      await page.locator('#dashboard_url').fill('https://dashboard.example.test');
      await page.getByRole('button', { name: '儲存後端設定', exact: true }).click();
      await expect(page.getByRole('status')).toContainText('需整組提供');
      expect(await calls(request)).toHaveLength(0);
    }
  }
});
test('MOCK network failure does not claim save success', async ({ page }) => {
  await start(page, '/access');
  await page.route('**/api/endpoint', route => route.abort('failed'));
  await page.getByLabel('MCP 用戶端端點').fill('https://mcp.example.test/mcp');
  await page.getByRole('button', { name: '儲存端點', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('無法確認操作結果');
  await expect(page.getByRole('status')).not.toContainText('端點已儲存');
});
test('MOCK health dimensions and root mount refresh remain distinct', async ({ page, request, baseURL: origin }) => {
  await reset(request, { offline: true });
  await page.goto('/overview');
  await expect(page.getByRole('heading', { name: '管理服務可用' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '尚未啟動' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '無法連線' })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: '後端連線' }).click();
  await expect(page).toHaveURL(`${origin}/backend`);
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: '後端連線' })).toBeVisible();
});
