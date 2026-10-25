import { test, expect } from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';
const updater = 'n8n_update_partial_workflow';
const versions = 'n8n_workflow_versions';
const testWorkflow = 'n8n_test_workflow';
const row = (page, name) => page.locator('.tool-row').filter({has:page.getByRole('heading', {name, exact:true})});
const condition = (page, name = versions) => page.getByLabel(`${name} 條件寫入`, {exact:true});
async function save(page, success = true) {
  await page.getByRole('button', {name:'儲存工具權限'}).click();
  await page.getByRole('dialog').getByRole('button', {name:'確認套用'}).click();
  await expect(page.locator('#app')).not.toHaveAttribute('aria-busy', 'true');
  if (success) await expect(page.getByRole('status').first()).toContainText('伺服器已確認儲存工具權限');
}

test('條件寫入沿用相依 grant，儲存立即更新且保留原工具與操作限制', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, parity:true, n8nExposure:true,
    grants:[testWorkflow, `${versions}:rollback`], denied_operations:{[versions]:['delete'], retired_tool:['old']}}});
  await page.goto(`${prefix}/tools`);
  for (const name of [versions, testWorkflow]) {
    await expect(condition(page, name)).toContainText('相依權限：已儲存政策禁止');
    await expect(condition(page, name)).toContainText('將工作流程開放給 MCP 存取');
    await expect(condition(page, name)).toContainText('false 或省略');
    await expect(condition(page, name)).toContainText('原工具與操作權限仍須允許');
    await expect(row(page, name).locator('.chip')).toHaveText('含條件寫入');
  }
  const grant = row(page, updater).getByLabel('明確允許此工具寫入', {exact:true});
  await grant.check();
  await expect(condition(page)).toContainText('相依權限：已儲存政策禁止');
  expect(await (await request.get('/__fixture/calls')).json()).toEqual([]);
  await save(page);
  await expect(condition(page)).toContainText('相依權限：已儲存政策允許');
  let calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.at(-1).policy.enabled_write_tools.sort()).toEqual([testWorkflow, `${versions}:rollback`, updater].sort());
  expect(calls.at(-1).policy.denied_operations).toEqual({retired_tool:['old'], [versions]:['delete']});
  await grant.uncheck();
  await expect(condition(page)).toContainText('相依權限：已儲存政策允許');
  await save(page);
  await expect(condition(page)).toContainText('相依權限：已儲存政策禁止');
  await grant.check();
  await save(page);
  await row(page, updater).getByLabel('停用此工具', {exact:true}).check();
  await save(page);
  await expect(condition(page)).toContainText('相依權限：已儲存政策禁止');
  calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.every(call => call.operation === 'policy' && call.validCsrf && call.ifMatch)).toBe(true);
  expect(calls.at(-1).policy.disabled).toEqual([updater]);
  expect(calls.at(-1).policy.enabled_write_tools).toEqual([`${versions}:rollback`, testWorkflow]);
  expect(calls.at(-1).policy.denied_operations).toEqual({retired_tool:['old'], [versions]:['delete']});
});

test('儲存失敗保留草稿且不宣稱相依權限已允許', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, n8nExposure:true, saveStatus:503}});
  await page.goto(`${prefix}/tools`);
  await row(page, updater).getByLabel('明確允許此工具寫入', {exact:true}).check();
  await save(page, false);
  await expect(page.getByRole('status').first()).toContainText('管理狀態暫時無法使用');
  await expect(condition(page)).toContainText('相依權限：已儲存政策禁止');
  await expect(row(page, updater).getByLabel('明確允許此工具寫入', {exact:true})).toBeChecked();
});

for (const [label, data] of [
  ['既有相依限制優先於 grant', {grants:[updater], denied_operations:{[updater]:['retained']}}],
  ['全域寫入不冒充精確授權', {legacyWrites:true}],
]) test(label, async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, n8nExposure:true, ...data}});
  await page.goto(`${prefix}/tools`);
  await expect(condition(page)).toContainText('相依權限：已儲存政策禁止');
});

for (const width of [320, 360, 1440]) test(`條件說明在 ${width}px 可見，未知子行程不影響相依政策`, async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, n8nExposure:true, offline:true, grants:[updater]}});
  await page.setViewportSize({width, height:960});
  await page.goto(`${prefix}/tools`);
  await page.getByLabel('搜尋工具', {exact:true}).fill('exposeToMcp');
  await expect(page.getByText('顯示 2 / 3 個工具', {exact:true})).toBeVisible();
  await expect(condition(page)).toContainText('相依權限：已儲存政策允許');
  await expect(row(page, versions).getByText('有效狀態未知', {exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  if (process.env.HA_CONDITIONAL_EVIDENCE) {
    await page.screenshot({path:`${process.env.HA_CONDITIONAL_EVIDENCE}/ha-conditional-${width}.png`, fullPage:true});
  }
});

test('未知相依政策不從 schema 或 grant 推測允許', async ({page, request}) => {
  await request.post('/__fixture/reset', {data:{operations:true, n8nExposure:true, unknownExposure:true, grants:[updater]}});
  await page.goto(`${prefix}/tools`);
  await expect(condition(page)).toContainText('相依權限：已儲存政策未知');
});
