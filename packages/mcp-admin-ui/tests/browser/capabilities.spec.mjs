import { test, expect } from '../owned-fixture.mjs';
const prefix='/api/hassio_ingress/DUMMY';
test('fixed builtin hides backend mutations and uses deployment authority', async ({page,request})=>{
  await request.post('/__fixture/reset',{data:{product:'opendesign',fixed:true}});
  await page.goto(`${prefix}/backend`);
  await expect(page.getByRole('heading',{name:'固定後端'})).toBeVisible();
  await expect(page.getByText('PaaS 管理授權',{exact:false})).toBeVisible();
  await expect(page.getByLabel('這次要如何處理設定？')).toHaveCount(0);
  await page.getByRole('button',{name:'測試已儲存的後端'}).click();
  await expect(page.getByRole('status')).toContainText('已測試伺服器儲存的設定');
  const calls=await (await request.get('/__fixture/calls')).json();
  expect(calls.map(call=>call.operation)).toEqual(['backend/test']);
  expect(calls[0].validCsrf).toBe(true);
});
test('search and schema details retain all policy rows, unknown means unknown',async({page,request})=>{
  await request.post('/__fixture/reset',{data:{offline:true}});
  await page.goto(`${prefix}/tools`);
  await expect(page.getByText('目錄 3 · 政策允許 3 · 子行程有效 未知')).toBeVisible();
  await page.getByLabel('搜尋工具').fill('read_example');
  await expect(page.locator('.tool-row:visible')).toHaveCount(1);
  await page.getByText('工具參數與操作詳情',{exact:true}).first().click();
  await expect(page.getByLabel('read_example inputSchema')).toContainText('properties');
  await page.getByLabel('搜尋工具').fill('');
  await expect(page.locator('.tool-row:visible')).toHaveCount(3);
});
test('diagnostics displays redacted text and confirms restart with fresh CSRF',async({page,request})=>{
  await request.post('/__fixture/reset',{data:{}});
  await page.goto(`${prefix}/diagnostics`);
  await page.getByRole('button',{name:'讀取診斷日誌'}).click();
  await expect(page.getByLabel('已遮蔽的子行程日誌')).toContainText('token=[REDACTED]');
  await page.getByRole('button',{name:'重新啟動子行程'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'確認重新啟動'}).click();
  await expect(page.getByRole('status').first()).toContainText('已接受重新啟動請求');
  const calls=await (await request.get('/__fixture/calls')).json();
  expect(calls[0].operation).toBe('child/restart');
  expect(calls[0].validCsrf).toBe(true);
});
for(const width of [320,360,1440]) test(`new routes fit ${width}px with self-hosted icons`,async({page,request})=>{
  await request.post('/__fixture/reset',{data:{}});
  await page.setViewportSize({width,height:860});
  for(const route of ['tools','diagnostics']) {
    await page.goto(`${prefix}/${route}`);
    await page.evaluate(()=>document.fonts.ready);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    expect(await page.locator('.mdi').first().evaluate(node=>getComputedStyle(node,'::before').content)).not.toBe('none');
  }
});
