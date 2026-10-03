// LOCAL MOCK transport/roles only. Actual packaged n8n executable + Core HTML/API.
// Invoked by pytest's owned integration harness, never a production entrypoint.
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from '@playwright/test';
const admin = process.env.LOCAL_ADMIN;
const control = process.env.LOCAL_CONTROL;
const prefix = '/api/hassio_ingress/DUMMY';
const evidence = '/data/pi-agent/home/work/mcp-haos-team-runtime/reports/integration-browser-evidence/core';
const browser = await chromium.launch({headless:true});
const context = await browser.newContext();
const page = await context.newPage();
const errors=[], requests=[];
page.on('pageerror', e=>errors.push(e.message));
page.on('request', r=>requests.push(r.url()));
const visible = async locator => { await locator.waitFor({state:'visible'}); };
const confirm = async (label='確認儲存') => page.getByRole('dialog').getByRole('button',{name:label,exact:true}).click();
async function saved(text) {
  await page.waitForFunction(()=>!document.querySelector('#app').hasAttribute('aria-busy'));
  await visible(page.getByRole('status').filter({hasText:text}));
}
async function open(origin,path) {
  const result=await page.goto(origin+path);
  assert.equal(result.status(),200);
  assert.equal(result.headers()['cache-control'],'no-store');
  assert.match(result.headers()['content-security-policy'],/frame-ancestors 'self'/);
  await visible(page.getByRole('heading',{level:1}));
}
async function bootstrap(origin=admin,base=prefix) { return (await fetch(origin+base+'/api/bootstrap')).json(); }
async function policy(payload) {
  const b=await bootstrap();
  const r=await fetch(admin+prefix+'/api/policy',{method:'PUT',headers:{'content-type':'application/json','x-csrf-token':b.csrf},body:JSON.stringify(payload)});
  assert.equal(r.status,200);
}
try {
  await mkdir(evidence,{recursive:true});
  for (const width of [1440,320,360]) {
    await page.setViewportSize({width,height:900});
    for (const mount of ['',prefix]) for (const route of ['/','/overview','/backend','/tools','/access']) {
      await open(admin,mount+route);
      await page.evaluate(()=>document.fonts.ready);
      const fonts=await page.evaluate(async()=>{
        const results=[];
        for (const [family,descriptor,text] of [['Poppins','500 20px Poppins','MCP'],['Outfit','400 16px Outfit','MCP'],['Yellowtail','400 24px Yellowtail','Welcome'],['Noto Sans TC','400 16px "Noto Sans TC"','管理連線'],['MDI','24px "Material Design Icons"','\uDB80\uDF35']]) {
          const faces=await document.fonts.load(descriptor,text);
          results.push({family,loaded:faces.length>0&&faces.every(f=>f.status==='loaded')});
        }
        return results;
      });
      assert(fonts.every(f=>f.loaded),'all self-hosted fonts must load, not just CSS glyph content');
      const metrics=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,accent:[...document.fonts].some(f=>f.family.replaceAll('"','')==='Yellowtail'&&f.status==='loaded'),mdi:getComputedStyle(document.querySelector('.mdi'),'::before').content}));
      assert.equal(metrics.overflow,false); assert.equal(metrics.accent,true); assert.notEqual(metrics.mdi,'none');
      await page.reload(); await visible(page.getByRole('heading',{level:1}));
      if (mount===prefix && ['/overview','/backend'].includes(route)) await page.screenshot({path:`${evidence}/core-${width}-${route.slice(1)}.png`,fullPage:true});
    }
  }
  const first=await bootstrap();
  assert.equal(first.policy_contract,'woow-v3-exact-grants');
  assert.equal(first.endpoint,null);
  assert.equal(Object.keys(first.tools).length,7);
  assert.deepEqual(first.enabled_write_tools,[]);
  assert.equal((await fetch(admin+prefix+'/api/endpoint',{method:'PUT',headers:{'content-type':'application/json'},body:'{"endpoint":null}'})).status,403);
  const connections={
    n8n:{url:process.env.LOCAL_BACKEND,key:'DUMMY-LOCAL-ONLY'},
    odoo:{url:'https://odoo.example.test',database:'fixture',username:'tester',password:'DUMMY-LOCAL-ONLY'},
    'odoo-manage':{url:'https://odoo.example.test',database:'fixture',username:'tester',api_key:'DUMMY-LOCAL-ONLY'},
    hermes:{gateway_url:'https://hermes.example.test',gateway_api_key:'DUMMY-LOCAL-ONLY'},
    opendesign:{url:'https://design.example.test'},
    emqx:{url:'https://emqx.example.test',api_key:'DUMMY-LOCAL-ONLY',api_secret:'DUMMY-LOCAL-ONLY'},
    litellm:{url:'https://litellm.example.test',master_key:'DUMMY-LOCAL-ONLY'},
  };
  for (const [product,values] of Object.entries(connections)) {
    const origin=product==='n8n'?admin:control;
    const base=product==='n8n'?prefix:`/local-product/${product}`;
    await open(origin,base+'/backend');
    await page.getByRole('button',{name:'儲存後端設定',exact:true}).click();
    await saved('未送出變更');
    await page.getByLabel('這次要如何處理設定？').selectOption('replace');
    for (const [key,value] of Object.entries(values)) await page.locator('#'+key).fill(value);
    if (product==='odoo-manage') {
      await page.locator('#mode').selectOption('module');
      assert.match(await page.locator('#connection-help').textContent(),/後端已安裝/);
    }
    await page.getByRole('button',{name:'儲存後端設定',exact:true}).click(); await confirm(); await saved('伺服器已確認儲存');
    assert.equal((await bootstrap(origin,base)).connection_configured,true);
    assert.equal(await page.locator('input[type=password]').evaluateAll(nodes=>nodes.every(n=>n.value==='')),true);
    await page.getByLabel('這次要如何處理設定？').selectOption('clear');
    await page.getByRole('button',{name:'儲存後端設定',exact:true}).click(); await confirm(); await saved('伺服器已確認儲存');
    assert.equal((await bootstrap(origin,base)).connection_configured,false);
  }
  // Existing exact grants and the old global legacy writer are reflected as
  // effective checked authorization; a save converts them to exact grants.
  await policy({writes_enabled:true,disabled:[],enabled_write_tools:['n8n_manage_folders:create']});
  await open(admin,prefix+'/tools');
  const writer=page.getByLabel('明確允許此工具寫入');
  assert.equal(await writer.isChecked(),true);
  assert.equal(await page.getByLabel('允許寫入操作：create',{exact:true}).isChecked(),true);
  await writer.uncheck();
  await page.getByLabel('允許寫入操作：create',{exact:true}).uncheck();
  await page.getByRole('button',{name:'儲存工具權限'}).click(); await confirm('確認套用'); await saved('伺服器已確認儲存工具權限');
  assert.deepEqual((await bootstrap()).enabled_write_tools,[]);
  assert.equal((await bootstrap()).writes_enabled,false);
  await writer.check();
  await policy({writes_enabled:false,disabled:[],enabled_write_tools:['n8n_manage_folders:rename']});
  await page.getByRole('button',{name:'儲存工具權限'}).click(); await confirm('確認套用'); await saved('工具授權版本已變更');
  assert.deepEqual((await bootstrap()).enabled_write_tools,['n8n_manage_folders:rename']);
  await page.getByRole('button',{name:'重新整理狀態'}).click();
  await visible(page.getByLabel('允許寫入操作：rename',{exact:true}));
  const mixed=page.locator('.tool-row').filter({has:page.getByRole('heading',{name:'n8n_manage_folders',exact:true})});
  await mixed.getByLabel('停用此工具').check();
  assert.equal(await mixed.getByLabel('允許寫入操作：rename',{exact:true}).isChecked(),false);
  await page.getByRole('button',{name:'儲存工具權限'}).click(); await confirm('確認套用'); await saved('伺服器已確認儲存工具權限');
  assert.deepEqual((await bootstrap()).enabled_write_tools,[]);
  await open(admin,prefix+'/access');
  assert.match(await page.locator('pre').textContent(),/YOUR-MCP-HOST/);
  await page.getByLabel('MCP 用戶端端點').fill('https://client.example.test:8081/mcp');
  await page.getByRole('button',{name:'儲存端點',exact:true}).click(); await saved('MCP 端點已儲存');
  await page.getByRole('button',{name:'重新產生',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
  await page.getByRole('button',{name:'顯示權杖',exact:true}).click(); await confirm('確認繼續'); await visible(page.locator('#token-secret'));
  assert.match(await page.locator('pre').textContent(),/YOUR_ADDON_TOKEN/);
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  assert.equal(await page.locator('#token-secret').isHidden(),true);
  await page.getByRole('button',{name:'重新產生',exact:true}).click(); await confirm('確認繼續'); await visible(page.locator('#token-secret'));
  await page.clock.install();
  await page.getByRole('button',{name:'立即隱藏'}).click();
  await page.getByRole('button',{name:'顯示權杖',exact:true}).click(); await confirm('確認繼續'); await visible(page.locator('#token-secret'));
  await page.clock.fastForward(61000);
  assert.equal(await page.locator('#token-secret').isHidden(),true);
  await page.clock.resume();
  await page.getByRole('button',{name:'撤銷權杖',exact:true}).click(); await confirm('確認撤銷'); await saved('權杖已撤銷');
  assert.equal((await bootstrap()).token_active,false);
  for (const mode of ['demoted','error']) {
    await fetch(control+'/__local/role',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mode})});
    await page.getByRole('button',{name:mode==='demoted'?'重新整理狀態':'重新檢查權限'}).click();
    await visible(page.getByRole('heading',{name:'管理介面無法使用'}));
    assert.equal(await page.locator('form').count(),0);
    assert.equal((await fetch(admin+prefix+'/assets/app.js')).status,403);
  }
  await fetch(control+'/__local/role',{method:'POST',headers:{'content-type':'application/json'},body:'{"mode":"owner"}'});
  assert.equal((await bootstrap()).endpoint,'https://client.example.test:8081/mcp');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  assert.deepEqual(errors,[]);
  assert(requests.every(url=>url.startsWith(admin)||url.startsWith(control)));
  console.log('PASS LOCAL CORE: root/prefix refresh/fonts; 7 typed forms; v3 exact/legacy/stale/disabled; endpoint; CSRF; token blur/TTL/rotate/revoke; real WS demotion/error. No HA claim.');
} finally { await context.close(); await browser.close(); }
