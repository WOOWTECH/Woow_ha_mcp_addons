import { test, expect } from '../owned-fixture.mjs';

for (const width of [1440,320]) test(`lost response survives reload and queries without a second effect ${width}`,async({page,request})=>{
  await request.post('/__fixture/reset',{data:{parity:true}});
  await page.setViewportSize({width,height:900});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/access');
  await page.route('**/api/token/rotate',async route=>{await route.fetch();await route.abort();});
  await page.getByRole('button',{name:'重新產生',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'確認繼續',exact:true}).click();
  await expect(page.getByRole('heading',{name:'待確認操作'})).toBeVisible();
  await expect(page.locator('#token-secret')).toBeHidden();
  await page.reload();
  await expect(page.getByRole('heading',{name:'待確認操作'})).toBeVisible();
  await page.getByRole('button',{name:'查詢操作結果',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('未再次執行');
  await expect(page.getByRole('heading',{name:'待確認操作'})).toHaveCount(0);
  const calls=await(await request.get('/__fixture/calls')).json();
  expect(calls.filter(c=>c.operation==='token/rotate')).toHaveLength(1);
  expect(await page.locator('body').innerText()).not.toContain('M'.repeat(43));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  expect(errors).toEqual([]);
});

test('explicit resend preserves ID, secret stays absent, stale second-tab rotation cannot execute',async({page,context,request})=>{
  await request.post('/__fixture/reset',{data:{parity:true}});
  await page.goto('/access');
  const second=await context.newPage();await second.goto('/access');
  let first=true;
  await page.route('**/api/token/rotate',async route=>{
    if(first){first=false;await route.fetch();await route.abort();}else await route.continue();
  });
  await page.getByRole('button',{name:'重新產生',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'確認繼續',exact:true}).click();
  await expect(page.getByRole('heading',{name:'待確認操作'})).toBeVisible();
  await page.getByRole('button',{name:'以原識別碼重送',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'確認繼續',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('操作已確認');
  await expect(page.locator('#token-secret')).toBeHidden();
  await second.getByRole('button',{name:'重新產生',exact:true}).click();
  await second.getByRole('dialog').getByRole('button',{name:'確認繼續',exact:true}).click();
  await expect(second.locator('#notice')).toContainText('設定已被其他操作更新');
  const calls=(await(await request.get('/__fixture/calls')).json()).filter(c=>c.operation==='token/rotate');
  expect(calls).toHaveLength(3);expect(calls[0].operationId).toBe(calls[1].operationId);
  expect(calls[2].operationId).not.toBe(calls[0].operationId);
  await second.close();
});
