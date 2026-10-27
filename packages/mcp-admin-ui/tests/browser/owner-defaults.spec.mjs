// LOCAL MOCK only (fixtures/server.mjs): the one-time all-on notice of 2026-10-27, not HA security or E2E.
import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const evil = '<img src=x onerror=alert(1)>hermes_skill';

function view(changes = {}) {
  // The shape owner_defaults.view returns for the ws97 Hermes 0.1.14 sample (tests/fixtures/owner_defaults).
  return {
    decision: '2026-10-25', applied: 'migrated', at: '2026-10-27T03:04:05+00:00', from_schema: 3,
    restored_at: null, acknowledged_at: null, notice: true, recovery: 'available',
    upgrade: {enabled_tools: ['hermes_skill'], granted_writes: ['hermes_cron:delete', 'hermes_cron:pause'],
      cleared_operation_denies: [], new_tools: ['hermes_chat', 'hermes_config'], new_write_operations: ['hermes_chat', 'hermes_config:set'],
      writes_enabled: [false, true], changed: true},
    restore: {disabled_added: ['hermes_skill'],
      write_grants_removed: ['hermes_chat', 'hermes_config:set', 'hermes_cron:delete', 'hermes_cron:pause'],
      operation_denies_added: [], writes_enabled: [true, false], kept_new_tools: ['hermes_config', 'hermes_mcp'],
      policy_changed: true, available: true},
    ...changes,
  };
}
async function reset(request, ownerDefaults, extra = {}) {
  await request.post('/__fixture/reset', {data: {parity: true, product: 'hermes', granular: true, ownerDefaults,
    grants: ['write_example'], ...extra}});
}
// The owned UI guard (tests/owned_ui.mjs) closes the context and then waits for every routed request. Observed with
// Playwright 1.61.1 in the sandbox: a route.fetch begun just before the close never sends its request and settles only
// when the browser closes, so the teardown runs past the test timeout. Let each page finish loading (this notice's
// text pulls many Noto Sans TC subsets) before acting on it and before the test ends.
async function settle(page) {
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
}
async function open(page, url) {
  await page.goto(url);
  await settle(page);
}
async function calls(request) {
  return (await (await request.get('/__fixture/calls')).json()).filter(call => call.operation.startsWith('owner-defaults/'));
}

test('notice shows time, schema and both difference lists on every page; restore sends one reviewed POST', async ({page, request}) => {
  await reset(request, view());
  for (const route of ['overview', 'tools', 'access']) {
    await open(page, `${prefix}/${route}`);
    const card = page.locator('#owner-defaults');
    await expect(card).toBeVisible();
    await expect(card.getByRole('heading', {name: '已自動套用預設全開', exact: true})).toBeVisible();
    await expect(card).toContainText('已於 2026-10-27 03:04（UTC）自動套用預設全開');
    await expect(card).toContainText('設定格式 3');
  }
  const card = page.locator('#owner-defaults');
  await expect(card.locator('#owner-defaults-upgrade')).toContainText('升級前停用、現在已啟用的工具（1）');
  await expect(card.locator('#owner-defaults-upgrade')).toContainText('升級前沒有授權、現在已授權的寫入（2）');
  const preview = card.locator('#owner-defaults-restore-preview');
  await expect(preview).toContainText('會停用的工具（1）');
  // Writes follow the legacy allow list: every write the old settings did not grant is revoked, newer ones included.
  await expect(preview).toContainText('會取消授權的寫入（含新版新增的寫入）（4）');
  await expect(preview.locator('details', {hasText: '會取消授權的寫入'})).toHaveAttribute('open', '');
  await expect(preview).toContainText('還原後仍可使用的新版工具（2）');
  await expect(preview).toContainText('只保留舊設定授權過的寫入');
  await expect(card).not.toContainText('維持授權的新版寫入');
  await expect(card).not.toContainText('全部停用');
  await card.getByRole('button', {name: '還原升級前的限制', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('停用 1 個工具、取消 4 個寫入授權，回到舊版設定允許的範圍');
  await expect(page.getByRole('dialog')).toContainText('新版新增的寫入也取消');
  await page.getByRole('dialog').getByRole('button', {name: '取消', exact: true}).click();
  expect(await calls(request)).toEqual([]);
  await card.getByRole('button', {name: '還原升級前的限制', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '確認還原', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('已還原升級前的限制');
  await expect(page.locator('#owner-defaults')).toHaveCount(0);
  const sent = await calls(request);
  expect(sent).toEqual([{operation: 'owner-defaults/restore', method: 'POST', validCsrf: true,
    ifMatch: `"${'1'.padStart(64, '0')}"`, fields: []}]);
  await page.getByRole('navigation').getByRole('link', {name: '診斷與維護', exact: true}).click();
  const history = page.locator('#owner-defaults');
  await expect(history.getByRole('heading', {name: '升級紀錄：已還原升級前的限制', exact: true})).toBeVisible();
  await expect(history).toContainText('已於 2026-10-27 09:30（UTC）還原升級前的限制');
  await expect(history.getByRole('button')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  await settle(page);
});

test('keep everything on ends the notice; restore stays available on the diagnostics page', async ({page, request}) => {
  await reset(request, view());
  await open(page, `${prefix}/overview`);
  await page.getByRole('button', {name: '保持全開，不再提示', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('之後仍可在「診斷與維護」頁還原升級前的限制');
  await page.getByRole('dialog').getByRole('button', {name: '確認保持全開', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('已保持全開');
  await expect(page.locator('#owner-defaults')).toHaveCount(0);
  await open(page, `${prefix}/diagnostics`);
  const history = page.locator('#owner-defaults');
  await expect(history).toContainText('已於 2026-10-27 09:30（UTC）選擇保持全開');
  await expect(history.getByRole('button', {name: '保持全開，不再提示', exact: true})).toHaveCount(0);
  await history.getByRole('button', {name: '還原升級前的限制', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '確認還原', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('已還原升級前的限制');
  expect((await calls(request)).map(call => call.operation)).toEqual(['owner-defaults/dismiss', 'owner-defaults/restore']);
  await settle(page);
});

test('a stale revision is refused without a write and the notice stays', async ({page, request}) => {
  await reset(request, view());
  await open(page, `${prefix}/overview`);
  await request.post('/__fixture/configuration', {data: {changed: true, applyState: 'applied'}});
  await page.getByRole('button', {name: '還原升級前的限制', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '確認還原', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('設定已被其他操作更新');
  await expect(page.locator('#owner-defaults')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  const [sent] = await calls(request);
  expect(sent.ifMatch).toBe(`"${'1'.padStart(64, '0')}"`);
  await settle(page);
});

test('no recovery record: no restore button, only keep; names render as text', async ({page, request}) => {
  await reset(request, view({recovery: 'missing', upgrade: null, restore: null}));
  await open(page, `${prefix}/overview`);
  const card = page.locator('#owner-defaults');
  await expect(card).toContainText('找不到可用的升級前限制紀錄');
  await expect(card.getByRole('button', {name: '還原升級前的限制', exact: true})).toHaveCount(0);
  await expect(card.getByRole('button', {name: '保持全開，不再提示', exact: true})).toBeVisible();
  await reset(request, view({upgrade: {...view().upgrade, enabled_tools: [evil]}, restore: {...view().restore, disabled_added: [evil]}}));
  let dialogs = 0;
  page.on('dialog', async dialog => { dialogs++; await dialog.dismiss(); });
  await open(page, `${prefix}/overview`);
  await expect(page.locator('#owner-defaults')).toContainText(evil);
  await expect(page.locator('#owner-defaults img')).toHaveCount(0);
  expect(dialogs).toBe(0);
  await settle(page);
});

test('nothing to restore, a malformed notice and a server without the notice show no actions', async ({page, request}) => {
  await reset(request, view({restore: {...view().restore, disabled_added: [], write_grants_removed: [], policy_changed: false, available: false}}));
  await open(page, `${prefix}/overview`);
  await expect(page.locator('#owner-defaults')).toContainText('舊版設定沒有需要還原的限制');
  await expect(page.locator('#owner-defaults').getByRole('button', {name: '還原升級前的限制', exact: true})).toHaveCount(0);
  await reset(request, {...view(), at: 'yesterday'});
  await open(page, `${prefix}/overview`);
  await expect(page.getByRole('heading', {level: 1})).toBeVisible();
  await expect(page.locator('#owner-defaults')).toHaveCount(0);
  await reset(request, undefined);
  await open(page, `${prefix}/diagnostics`);
  await expect(page.getByRole('heading', {level: 1})).toBeVisible();
  await expect(page.locator('#owner-defaults')).toHaveCount(0);
  expect(await calls(request)).toEqual([]);
  await settle(page);
});

for (const width of [320, 360]) {
  test(`notice fits ${width}px without horizontal scrolling`, async ({page, request}) => {
    const long = 'accounting_health_across_instances_with_a_very_long_name_for_wrapping';
    await reset(request, view({upgrade: {...view().upgrade, new_tools: [long]}, restore: {...view().restore, kept_new_tools: [long]}}));
    await page.setViewportSize({width, height: 860});
    await open(page, `${prefix}/overview`);
    await page.locator('#owner-defaults details').evaluateAll(nodes => nodes.forEach(node => { node.open = true; }));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await settle(page);
  });
}
