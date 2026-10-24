import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
async function save(page) {
  await page.getByRole('button', {name:'儲存工具權限'}).click();
  await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/policy') && response.request().method() === 'PUT'),
    page.getByRole('dialog').getByRole('button', {name:'確認套用'}).click(),
  ]);
  await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true');
  await expect(page.getByRole('status').first()).toContainText('伺服器已確認儲存工具權限');
}

test('read and write denies persist without clearing independent grants or stale restrictions', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, grants:['mixed_example:delete'],
    denied_operations:{mixed_example:['get','delete','retired'], retired_tool:['old']}}});
  await page.goto(`${prefix}/tools`);
  const row = page.locator('.tool-row').filter({has:page.getByRole('heading', {name:'mixed_example', exact:true})});
  await expect(row.getByLabel('禁止讀取操作：get', {exact:true})).toBeChecked();
  await expect(row.getByLabel('禁止讀取操作：list', {exact:true})).not.toBeChecked();
  await expect(row.getByLabel('禁止寫入操作：delete', {exact:true})).toBeChecked();
  await expect(row.getByLabel('允許寫入操作：delete', {exact:true})).toBeChecked();
  await expect(page.getByText('保留未列於目前操作目錄的限制：', {exact:false})).toContainText('retired_tool:old');
  await expect(page.getByText('目前已儲存政策：', {exact:false})).toContainText('已禁止 4 項操作');
  await save(page);
  let calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.at(-1).policy.enabled_write_tools).toEqual(['mixed_example:delete']);
  expect(calls.at(-1).policy.denied_operations).toEqual({mixed_example:['retired','get','delete'], retired_tool:['old']});
  await page.reload();
  await expect(row.getByLabel('禁止讀取操作：get', {exact:true})).toBeChecked();
  await row.getByLabel('禁止讀取操作：get', {exact:true}).uncheck();
  await row.getByLabel('禁止讀取操作：list', {exact:true}).check();
  await save(page);
  calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.at(-1).policy.denied_operations).toEqual({mixed_example:['retired','list','delete'], retired_tool:['old']});
  await row.getByLabel('停用此工具', {exact:true}).check();
  await save(page);
  calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.at(-1).policy.disabled).toEqual(['mixed_example']);
  expect(calls.at(-1).policy.denied_operations.mixed_example).toContain('list');
  expect(calls.every(call => call.operation === 'policy' && call.validCsrf)).toBe(true);
});

for (const width of [320, 360, 1440]) test(`operation controls fit ${width}px and reflect saved capability state`, async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, grants:['mixed_example:delete'],
    denied_operations:{mixed_example:['get','delete']}}});
  await page.setViewportSize({width, height:960});
  await page.goto(`${prefix}/tools`);
  await page.evaluate(() => document.fonts.ready);
  await expect(page.getByText('目錄 3 · 政策允許 2 · 子行程有效 2')).toBeVisible();
  await page.getByLabel('搜尋工具').fill('mixed_example');
  await page.getByText('工具參數與操作詳情', {exact:true}).last().click();
  await expect(page.getByText('get · 讀取 · 已儲存政策禁止 · 子行程未生效', {exact:true})).toBeVisible();
  await expect(page.getByText('list · 讀取 · 已儲存政策允許 · 子行程有效', {exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  expect(await page.locator('.mdi').first().evaluate(node => getComputedStyle(node, '::before').content)).not.toBe('none');
  if (process.env.HA_OPERATIONS_EVIDENCE) {
    await page.screenshot({path:`${process.env.HA_OPERATIONS_EVIDENCE}/ha-operations-ui-${width}.png`, fullPage:true});
    if (width === 1440) {
      await page.goto(`${prefix}/overview`);
      await page.screenshot({path:`${process.env.HA_OPERATIONS_EVIDENCE}/ha-operations-overview.png`, fullPage:true});
    }
  }
});

for (const offline of [false, true]) test(`operation policy and effectiveness remain distinct with child ${offline ? 'unavailable' : 'observed'}`, async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, offline, grants:['mixed_example:delete'],
    denied_operations:{mixed_example:['get','delete']}}});
  await page.goto(`${prefix}/tools`);
  const row = page.locator('.tool-row').filter({has:page.getByRole('heading', {name:'mixed_example', exact:true})});
  await row.getByText('工具參數與操作詳情', {exact:true}).click();
  const summary = `目錄 3 · 政策允許 2 · 子行程有效 ${offline ? '未知' : '2'}；操作目錄 4 · 已儲存政策允許 1 · 子行程有效 ${offline ? '未知' : '1'}`;
  await expect(page.getByText(summary, {exact:true})).toBeVisible();
  const list = `list · 讀取 · 已儲存政策允許 · ${offline ? '子行程有效狀態未知' : '子行程有效'}`;
  await expect(row.getByText(list, {exact:true})).toBeVisible();
  for (const [name, kind] of [['get','讀取'], ['create','寫入'], ['delete','寫入']]) {
    await expect(row.getByText(`${name} · ${kind} · 已儲存政策禁止 · 子行程未生效`, {exact:true})).toBeVisible();
  }
  // Unsaved form edits do not claim to change saved policy or observed state.
  await row.getByLabel('禁止讀取操作：list', {exact:true}).check();
  await expect(row.getByText(list, {exact:true})).toBeVisible();
  await expect(page.getByText(summary, {exact:true})).toBeVisible();
});
