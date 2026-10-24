// Run separately: PLAYWRIGHT_BROWSERS_PATH=0 node --test tests/upgrade-ui.mjs
// Contract/layout tests only. The root worker owns real-backend browser QA.
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { expect } from '@playwright/test';
import { upgradeFixture, sourceDigest, changedDigest, maliciousName } from './upgrade-ui-fixture.mjs';

const evidence = new URL('../../../evidence/batch3/', import.meta.url);
const metrics = [];
let browser;
before(async () => {
  await mkdir(evidence, { recursive: true });
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  await writeFile(new URL('upgrade-ui-metrics.json', evidence), JSON.stringify({ scope: 'Browser-only contract fixture; no real-backend/authentication claim', metrics }, null, 2));
});

async function setup(t, options) {
  const fixture = await upgradeFixture(browser, options);
  t.after(async () => {
    assert.deepEqual(fixture.unexpected, [], 'all browser requests stay in the isolated fixture');
    assert.deepEqual(fixture.errors, [], 'no uncaught JS errors');
    await fixture.close();
  });
  return fixture;
}
const applyButton = page => page.getByRole('button', { name: '確認升級並啟動', exact: true });
async function confirmAndApply(page) {
  await page.locator('#upgrade-confirm').check();
  await applyButton(page).click();
}

test('choice changes concrete deltas and resets confirmation; uses reviewed digest + CSRF once', { timeout: 20000 }, async t => {
  const f = await setup(t, { mount: '/api/hassio_ingress/UPGRADE', clock: true });
  const { page } = f;
  await f.open();
  await expect(page.locator('#policy-all_on')).toBeChecked();
  await expect(applyButton(page)).toBeDisabled();
  await expect(page.locator('#upgrade-preview')).toContainText('workflow:delete');
  await page.locator('#upgrade-confirm').check();
  await page.locator('#policy-preserve').check();
  await expect(page.locator('#upgrade-confirm')).not.toBeChecked();
  await expect(applyButton(page)).toBeDisabled();
  await expect(page.locator('#upgrade-preview')).toContainText('新增停用工具（2）');
  await expect(page.locator('#upgrade-preview')).toContainText('移除有效寫入權限（1）');
  await expect(page.getByText('workflow:update', { exact: true }).first()).toBeVisible();
  assert.equal(f.calls.length, 0);
  await confirmAndApply(page);
  await expect(page.getByRole('status')).toContainText('服務啟動中');
  assert.equal(f.bootstrapCount, 1, 'apply does not fetch a replacement digest or CSRF');
  assert.deepEqual(f.calls.map(call => call.body), [{ policy: 'preserve', expected_sha256: sourceDigest }]);
  assert.equal(f.calls[0].headers['x-csrf-token'], f.preview.csrf);
  assert.equal(f.calls[0].headers['content-type'], 'application/json');
  await expect(page.locator('#upgrade-apply')).toHaveCount(0);
});

test('409 locks apply; only refreshed preview and fresh confirmation can submit new digest', { timeout: 20000 }, async t => {
  const f = await setup(t);
  const { page } = f;
  await f.open();
  await expect(page.locator('#policy-all_on')).toBeChecked();
  for (const report of Object.values(f.preview.plans)) report.source_sha256 = changedDigest;
  f.preview.plans.all_on.effective_writes_added.push('newly_reviewed:delete');
  await confirmAndApply(page);
  await expect(page.getByRole('alert')).toContainText('預覽已過期');
  assert.equal(f.calls[0].body.expected_sha256, sourceDigest);
  assert.equal(f.bootstrapCount, 1, 'stale failure does not silently substitute the new digest');
  await expect(applyButton(page)).toBeDisabled();
  await page.locator('#upgrade-apply').dispatchEvent('click');
  assert.equal(f.calls.length, 1);
  await expect(page.locator('#upgrade-confirm')).toBeDisabled();
  await page.getByRole('button', { name: '重新載入升級預覽' }).click();
  await expect(page.locator('#upgrade-preview')).toContainText('newly_reviewed:delete');
  await expect(page.locator('#reviewed-digest')).toHaveText(changedDigest);
  await expect(applyButton(page)).toBeDisabled();
  await expect(page.locator('#upgrade-confirm')).not.toBeChecked();
  await confirmAndApply(page);
  await expect(page.getByRole('status')).toContainText('服務啟動中');
  assert.deepEqual(f.calls.map(call => call.body.expected_sha256), [sourceDigest, changedDigest]);
});

test('pending double-click and failed/ambiguous apply cannot repeat or claim success', { timeout: 20000 }, async t => {
  const f = await setup(t);
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  f.onApply = () => pending;
  const { page } = f;
  await f.open();
  await confirmAndApply(page);
  await expect(page.locator('#upgrade-apply')).toBeDisabled();
  await page.locator('#upgrade-apply').dispatchEvent('click');
  await expect.poll(() => f.calls.length).toBe(1);
  release({ status: 503, body: { error: 'PRIVATE_ERROR_CANARY' } });
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(applyButton(page)).toBeDisabled();
  await page.locator('#upgrade-apply').dispatchEvent('click');
  assert.equal(f.calls.length, 1);
  await expect(page.locator('body')).not.toContainText('PRIVATE_ERROR_CANARY');
  await expect(page.locator('body')).not.toContainText('伺服器已確認儲存');
});

test('accepted handoff survives pending/bootstrap outage; navigates only after normal bootstrap', { timeout: 20000 }, async t => {
  const f = await setup(t, { clock: true });
  const { page } = f;
  await f.open();
  await confirmAndApply(page);
  await expect(page.getByRole('status')).toContainText('服務啟動中');
  await page.clock.runFor(1500);
  await expect.poll(() => f.bootstrapCount).toBe(2);
  await expect(page.getByRole('heading', { name: '正在啟動服務' })).toBeVisible();
  f.onBootstrap = () => ({ abort: true });
  await page.clock.runFor(1500);
  await expect.poll(() => f.bootstrapCount).toBe(3);
  await expect(page.getByRole('status')).toContainText('尚未回應');
  f.onBootstrap = null; f.normal = true;
  await page.clock.runFor(1500);
  await expect(page.getByRole('heading', { name: '一般管理介面（測試）' })).toBeVisible();
  assert.equal(f.calls.length, 1);
  assert.equal(f.bootstrapCount, 4);
});

test('unexpected acceptance status, malformed acknowledgement, and lost response remain unconfirmed', { timeout: 20000 }, async t => {
  for (const result of [
    { status: 200, body: { saved: true, stage: 'starting' } },
    { status: 202, body: { saved: false, stage: 'starting' } },
    { status: 403, body: { error: 'PRIVATE_ERROR_CANARY' } },
    { abort: true },
  ]) {
    const f = await setup(t);
    f.onApply = () => result;
    await f.open();
    await confirmAndApply(f.page);
    await expect(f.page.getByRole('alert')).toBeVisible();
    await expect(applyButton(f.page)).toBeDisabled();
    await expect(f.page.locator('body')).not.toContainText('伺服器已確認儲存');
    await expect(f.page.locator('body')).not.toContainText('PRIVATE_ERROR_CANARY');
    assert.equal(f.calls.length, 1);
    assert.equal(f.bootstrapCount, 1);
  }
});

test('polling stops after 12 attempts; manual check reads state without repeating apply', { timeout: 20000 }, async t => {
  const f = await setup(t, { clock: true });
  const { page } = f;
  await f.open();
  await confirmAndApply(page);
  await expect(page.getByRole('status')).toContainText('服務啟動中');
  for (let attempt = 0; attempt < 12; attempt++) {
    await page.clock.runFor(1500);
    await expect.poll(() => f.bootstrapCount).toBe(attempt + 2);
  }
  await expect(page.getByRole('status')).toContainText('等待時間已到');
  await page.clock.runFor(120000);
  assert.equal(f.bootstrapCount, 13);
  assert.equal(f.calls.length, 1);
  f.normal = true;
  await page.getByRole('button', { name: '再檢查啟動狀態' }).click();
  await page.clock.runFor(1500);
  await expect(page.getByRole('heading', { name: '一般管理介面（測試）' })).toBeVisible();
  assert.equal(f.calls.length, 1);
});

test('invalid preview / missing CSRF / denied bootstrap never enables apply', { timeout: 20000 }, async t => {
  for (const mode of ['csrf', 'digest', 'report', 'denied']) {
    const f = await setup(t);
    if (mode === 'csrf') f.preview.csrf = '';
    if (mode === 'digest') f.preview.plans.preserve.source_sha256 = changedDigest;
    if (mode === 'report') f.preview.plans.all_on.after.enabled_write_tools = 'wrong';
    if (mode === 'denied') f.onBootstrap = () => ({ status: 403, body: { error: 'PRIVATE_ERROR_CANARY' } });
    await f.open();
    await expect(f.page.getByRole('alert')).toBeVisible();
    await expect(f.page.locator('#upgrade-apply')).toHaveCount(0);
    await expect(f.page.locator('body')).not.toContainText('PRIVATE_ERROR_CANARY');
    assert.equal(f.calls.length, 0);
  }
});

for (const width of [320, 360, 1440]) {
  test(`${width}px layout, literal report names, local fonts/MDI, strict CSP, keyboard focus`, { timeout: 25000 }, async t => {
    const f = await setup(t, { width, mount: '/api/hassio_ingress/UPGRADE' });
    const { page } = f;
    await f.open();
    await expect(page.locator('#policy-all_on')).toBeChecked();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByText(maliciousName, { exact: true }).first()).toBeVisible();
    assert.equal(await page.locator('#app img, #app script, #app [onerror], #app style, #app [style]').count(), 0);
    assert.equal(await page.evaluate(() => window.reportInjected), undefined);
    const fonts = await page.evaluate(async () => {
      const specs = [['Poppins', '500 20px Poppins', 'MCP'], ['Outfit', '400 16px Outfit', 'MCP'], ['Yellowtail', '400 24px Yellowtail', 'Welcome'], ['Noto Sans TC', '400 16px "Noto Sans TC"', '升級確認'], ['Material Design Icons', '24px "Material Design Icons"', '\uDB80\uDF35']];
      return Promise.all(specs.map(async ([name, spec, text]) => ({ name, loaded: (await document.fonts.load(spec, text)).length > 0 && document.fonts.check(spec, text) })));
    });
    assert(fonts.every(font => font.loaded));
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: '跳至主要內容' })).toBeFocused();
    const focus = await page.getByRole('link', { name: '跳至主要內容' }).evaluate(node => getComputedStyle(node).outlineWidth);
    assert.equal(focus, '3px');
    for (const policy of ['all_on', 'preserve']) {
      await page.locator(`#policy-${policy}`).check();
      await page.locator(`#policy-${policy}`).focus();
      const layout = await page.evaluate(() => ({
        width: innerWidth, document: document.documentElement.scrollWidth,
        shortTargets: [...document.querySelectorAll('button, label.check, summary')].filter(node => node.getClientRects().length && node.getBoundingClientRect().height < 44).map(node => node.textContent),
        smallBody: [...document.querySelectorAll('main p, main li, label.check')].filter(node => parseFloat(getComputedStyle(node).fontSize) < 16).map(node => node.textContent),
        violations: globalThis.upgradeCspViolations,
        storage: { local: localStorage.length, session: sessionStorage.length },
      }));
      assert(layout.document <= width, JSON.stringify(layout));
      assert.deepEqual(layout.shortTargets, []);
      assert.deepEqual(layout.smallBody, []);
      assert.deepEqual(layout.violations, []);
      assert.deepEqual(layout.storage, { local: 0, session: 0 });
      await page.screenshot({ path: new URL(`upgrade-ui-${width}-${policy}.png`, evidence).pathname, fullPage: true });
      metrics.push({ width, policy, ...layout, fonts, focus });
    }
    assert(f.requests.some(request => request.path.endsWith('/assets/upgrade.js')));
    assert(f.requests.some(request => request.path.endsWith('/assets/app.css')));
    assert(!f.requests.some(request => request.path.endsWith('/assets/app.js')));
    assert.equal(f.calls.length, 0);
  });
}
