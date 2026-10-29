import {test, expect} from '../owned-fixture.mjs';
const base='/api/hassio_ingress/DUMMY';
const config={product:'n8n',parity:true,parity046:true,configured:true,connection:{url:'http://old.test'}};
async function confirm(page,label='確認儲存') { await page.getByRole('dialog').getByRole('button',{name:label}).click(); await expect(page.locator('#app')).not.toHaveAttribute('aria-busy','true'); }
test('partial URL edit sends only URL; optional secret clear is explicit and read back', async ({page,request}) => {
  await request.post('/__fixture/reset',{data:config});await page.goto(base+'/backend');
  await expect(page.locator('#patch-key')).toHaveValue('');
  await page.locator('#patch-url-action').selectOption('set');await page.locator('#patch-url').fill('http://new.test');
  await page.getByRole('button',{name:'儲存選定欄位'}).click();await confirm(page);
  await expect(page.locator('#patch-url')).toHaveValue('http://new.test');
  let calls=await (await request.get('/__fixture/calls')).json();
  expect(calls.at(-1).operation).toBe('backend/patch');expect(calls.at(-1).changedKeys).toEqual(['url']);expect(calls.at(-1).validCsrf).toBe(true);
  await page.locator('#patch-mcp_access_token-action').selectOption('clear');
  await page.getByRole('button',{name:'儲存選定欄位'}).click();await confirm(page);
  await expect(page.locator('#patch-mcp_access_token-action')).toContainText('保留未設定狀態');
  expect(await page.evaluate(() => localStorage.length+sessionStorage.length)).toBe(0);
});
test('partial edit conflict retains draft and prevents blind retry', async ({page,request}) => {
  await request.post('/__fixture/reset',{data:config});await page.goto(base+'/backend');
  await page.locator('#patch-url-action').selectOption('set');await page.locator('#patch-url').fill('http://draft.test');
  await request.post('/__fixture/configuration',{data:{changed:true,applyState:'applied'}});
  await page.getByRole('button',{name:'儲存選定欄位'}).click();await confirm(page);
  await expect(page.locator('#notice')).toContainText('草稿已保留');await expect(page.locator('#patch-url')).toHaveValue('http://draft.test');
  await expect(page.getByRole('button',{name:'儲存選定欄位'})).toBeDisabled();
});
test('session values round visibly, save and survive reload on a narrow viewport', async ({page,request}) => {
  await request.post('/__fixture/reset',{data:config});await page.setViewportSize({width:320,height:900});await page.goto(base+'/backend');
  await expect(page.locator('#n8n-session')).toContainText('600 秒');await page.locator('#session-timeout').fill('61');await page.locator('#session-max').fill('30');
  await expect(page.locator('#n8n-session')).toContainText('2 分鐘');
  await page.getByRole('button',{name:'儲存 n8n 連線設定'}).click();await confirm(page,'確認套用');await page.reload();
  await expect(page.locator('#session-timeout')).toHaveValue('61');await expect(page.locator('#session-max')).toHaveValue('30');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test('Odoo exact method list warns about broad mode and saves/reloads independently', async ({page,request}) => {
  await request.post('/__fixture/reset',{data:{product:'odoo',parity:true,parity046:true}});await page.setViewportSize({width:320,height:900});await page.goto(base+'/tools');
  const card=page.locator('#odoo-allowed-methods');await expect(card).toContainText('不在清單上的方法也可能執行');
  await page.locator('#odoo-method-list').fill('sale.order.action_confirm\nres.partner.copy');
  await page.getByRole('button',{name:'儲存 Odoo 方法清單'}).click();await confirm(page,'確認套用');await page.reload();
  await expect(page.locator('#odoo-method-list')).toHaveValue('sale.order.action_confirm\nres.partner.copy');
  const calls=await(await request.get('/__fixture/calls')).json();expect(calls.at(-1).operation).toBe('odoo/allowed-methods');
  expect(calls.at(-1).methods).toEqual(['sale.order.action_confirm','res.partner.copy']);expect(calls.some(c=>c.operation==='policy'||c.operation==='odoo/write-switches')).toBe(false);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});
