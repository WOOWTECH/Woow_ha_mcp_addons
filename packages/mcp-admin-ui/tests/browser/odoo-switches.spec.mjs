import {test, expect} from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';

async function save(page) {
  await page.getByRole('button', {name:'儲存 Odoo 子操作開關'}).click();
  await page.getByRole('dialog').getByRole('button', {name:'確認套用'}).click();
  await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true');
}

test('legacy all-on is visible; saving only child switches preserves outer policy', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{product:'odoo', parity:true, grants:[], legacyWrites:false, operations:true,
    denied_operations:{execute_method:['retired']}}});
  await page.goto(`${prefix}/tools`);
  const card = page.getByRole('heading', {name:'Odoo 子操作開關'}).locator('..');
  await expect(card).toContainText('沿用先前子行程的四項全開值');
  await expect(card).toContainText('外層');
  for (const label of ['啟用 Odoo 寫入總閘門', '允許 execute_method 直接寫入', '允許未審查方法', '允許直接張貼 Chatter'])
    await expect(card.getByLabel(label, {exact:true})).toBeChecked();
  await card.getByLabel('啟用 Odoo 寫入總閘門', {exact:true}).uncheck();
  await card.getByLabel('允許 execute_method 直接寫入', {exact:true}).uncheck();
  await card.getByLabel('允許未審查方法', {exact:true}).uncheck();
  await card.getByLabel('允許直接張貼 Chatter', {exact:true}).uncheck();
  await save(page);
  await expect(page.locator('#notice')).toContainText('已確認儲存 Odoo 子操作開關');
  const calls = await (await request.get('/__fixture/calls')).json();
  const last = calls.at(-1);
  expect(last.operation).toBe('odoo/write-switches');
  expect(last.method).toBe('PUT');
  expect(last.validCsrf).toBe(true);
  expect(last.ifMatch).toBe(`"c1-${'1'.padStart(64, '0')}"`);
  expect(last.switches).toEqual({odoo_write_switches:{enable_writes:false, allow_direct_writes:false,
    allow_unknown_methods:false, chatter_direct:false}});
  expect(calls.some(call => call.operation === 'policy')).toBe(false);
  await expect(page.getByRole('heading', {name:'Odoo 子操作開關'}).locator('..')).toContainText('已儲存的子行程設定');
});

test('old management API and other products cannot edit Odoo switches', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{product:'odoo', parity:true, odooApi:false}});
  await page.goto(`${prefix}/tools`);
  await expect(page.getByRole('heading', {name:'Odoo 子操作開關'}).locator('..')).toContainText('尚未提供完整');
  await expect(page.getByRole('button', {name:'儲存 Odoo 子操作開關'})).toHaveCount(0);
  await request.post('/__fixture/reset', {data:{product:'hermes', parity:true}});
  await page.reload();
  await expect(page.getByRole('heading', {name:'Odoo 子操作開關'})).toHaveCount(0);
});

test('stale revision keeps draft and disables save until reload', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{product:'odoo', parity:true}});
  await page.goto(`${prefix}/tools`);
  const control = page.getByLabel('允許直接張貼 Chatter', {exact:true});
  await control.uncheck();
  await request.post('/__fixture/configuration', {data:{changed:true, applyState:'applied'}});
  await save(page);
  await expect(page.locator('#notice')).toContainText('草稿已保留');
  await expect(control).not.toBeChecked();
  await expect(page.getByRole('button', {name:'儲存 Odoo 子操作開關'})).toBeDisabled();
  const calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter(call => call.operation === 'odoo/write-switches')).toHaveLength(1);
});

for (const width of [320, 360, 1440]) test(`Odoo switches remain readable at ${width}px`, async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{product:'odoo', parity:true}});
  await page.setViewportSize({width, height:900});
  await page.goto(`${prefix}/tools`);
  await expect(page.getByLabel('允許直接張貼 Chatter', {exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});
