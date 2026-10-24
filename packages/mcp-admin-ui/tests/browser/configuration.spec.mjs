import {test, expect} from '../owned-fixture.mjs';
const prefix = '/api/hassio_ingress/DUMMY';

test('two editors: status refresh retains draft/revision, stale save cannot replay', async ({page, context, request}) => {
  await request.post('/__fixture/reset', {data: {parity: true, product: 'hermes', applyState: 'pending'}});
  await page.goto(prefix + '/backend');
  await page.getByLabel('這次要如何處理設定？').selectOption('replace');
  await page.locator('#gateway_url').fill('https://draft.example.test');
  await page.locator('#gateway_api_key').fill('SYNTHETIC_DRAFT_SECRET');
  const other = await context.newPage();
  await other.goto(prefix + '/access');
  await other.locator('#endpoint').fill('https://other.example.test/mcp');
  await other.getByRole('button', {name: '儲存端點', exact: true}).click();
  await expect(other.locator('#notice')).toContainText('MCP 端點已儲存');
  await request.post('/__fixture/configuration', {data: {applyState: 'failed'}});
  await page.getByRole('button', {name: '更新套用狀態（保留草稿）', exact: true}).click();
  await expect(page.locator('#configuration-state')).toHaveAttribute('data-apply-state', 'failed');
  await expect(page.locator('#configuration-state')).toContainText('伺服器設定已更新');
  await expect(page.locator('#gateway_url')).toHaveValue('https://draft.example.test');
  await page.getByRole('button', {name: '儲存後端設定', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '確認儲存', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('草稿已保留');
  await expect(page.locator('#gateway_url')).toHaveValue('https://draft.example.test');
  await expect(page.locator('#gateway_api_key')).toHaveValue('SYNTHETIC_DRAFT_SECRET');
  await expect(page.getByRole('button', {name: '儲存後端設定', exact: true})).toBeDisabled();
  await expect(page.locator('body')).not.toContainText('PRIVATE_CANARY');
  const calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter(call => call.operation === 'backend')).toHaveLength(1);
  expect(calls.filter(call => ['backend', 'endpoint'].includes(call.operation)).map(call => call.ifMatch))
    .toEqual([`"${'1'.padStart(64, '0')}"`, `"${'1'.padStart(64, '0')}"`]);
  await page.getByRole('button', {name: '重新整理狀態', exact: true}).click();
  await expect(page.getByRole('button', {name: '儲存後端設定', exact: true})).toBeEnabled();
  await expect(page.locator('#gateway_api_key')).toHaveValue('');
  await other.close();
});

test('pending/applied/failed/unconfigured remain separate from backend health at mobile width', async ({page, request}) => {
  await page.setViewportSize({width: 360, height: 860});
  await request.post('/__fixture/reset', {data: {parity: true, product: 'n8n', applyState: 'pending'}});
  await page.goto(prefix + '/overview');
  for (const state of ['pending', 'applied', 'failed', 'unconfigured', 'unknown']) {
    await request.post('/__fixture/configuration', {data: {applyState: state}});
    await page.getByRole('button', {name: '更新套用狀態（保留草稿）', exact: true}).click();
    await expect(page.locator('#configuration-state')).toHaveAttribute('data-apply-state', state);
    await expect(page.locator('#configuration-state')).toContainText('後端是否可連線分開判定');
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('policy draft uses its captured revision even after a fresh bootstrap', async ({page, request}) => {
  await request.post('/__fixture/reset', {data: {parity: true, product: 'n8n'}});
  await page.goto(prefix + '/tools');
  const disabled = page.locator('input[name=disabled]').first();
  await disabled.check();
  await request.post('/__fixture/configuration', {data: {changed: true, applyState: 'applied'}});
  await page.getByRole('button', {name: '儲存工具權限', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '確認套用', exact: true}).click();
  await expect(page.locator('#notice')).toContainText('草稿已保留');
  await expect(disabled).toBeChecked();
  await expect(page.getByRole('button', {name: '儲存工具權限', exact: true})).toBeDisabled();
  const calls = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter(call => call.operation === 'policy').map(call => call.ifMatch)).toEqual([`"${'1'.padStart(64, '0')}"`]);
});
