// Explicit post-build check; no mock or test code enters dist.
import assert from 'node:assert/strict';
import {readFile,readdir,lstat} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const dist=resolve(root,'dist');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const originals=new Set();
for (const source of ['@fontsource/poppins','@fontsource/outfit','@fontsource/noto-sans-tc','@fontsource/yellowtail','@mdi/font']) {
  const folder=resolve(root,'node_modules',source,source==='@mdi/font'?'fonts':'files');
  for (const name of await readdir(folder)) if (/\.(woff2?|ttf|eot)$/.test(name)) originals.add(hash(await readFile(resolve(folder,name))));
}
const files=await readdir(dist,{recursive:true});
let fonts=0;
for (const name of files) {
  const path=resolve(dist,name), info=await lstat(path);
  assert(!info.isSymbolicLink());
  if (!info.isFile()) continue;
  assert(!/fixtures|test-results|\.map$|node_modules/.test(name));
  assert(name==='index.html'||name.startsWith('assets/')||name.startsWith('licenses/'));
  if (/\.(woff2?|ttf|eot)$/.test(name)) { assert(originals.has(hash(await readFile(path)))); fonts++; }
}
assert(fonts>400);
let references=0;
// 2026-10-27: one entry only; the pre-start upgrade review page (upgrade.js) is gone.
for (const removed of ['upgrade.js','upgrade.css']) assert(!files.includes(`assets/${removed}`),'no upgrade review entry');
for (const entry of ['app']) {
  const css=await readFile(resolve(dist,`assets/${entry}.css`),'utf8');
  for (const [_,url] of css.matchAll(/url\("?([^"()]+)"?\)/g)) {
    assert(url.startsWith('./fonts/')&&!/[?#]/.test(url),'only content-hashed local query-free fonts');
    assert((await lstat(resolve(dist,'assets',url))).isFile()); references++;
  }
}
for (const [target,source] of [
  ['poppins-OFL.txt','node_modules/@fontsource/poppins/LICENSE'],['outfit-OFL.txt','node_modules/@fontsource/outfit/LICENSE'],
  ['noto-sans-tc-OFL.txt','node_modules/@fontsource/noto-sans-tc/LICENSE'],['yellowtail-Apache-2.0.txt','node_modules/@fontsource/yellowtail/LICENSE'],
  ['mdi-LICENSE.txt','node_modules/@mdi/font/LICENSE'],['NOTICE.txt','NOTICE.txt'],
]) assert.deepEqual(await readFile(resolve(dist,'licenses',target)),await readFile(resolve(root,source)));
{
  const js=await readFile(resolve(dist,'assets/app.js'),'utf8');
  for (const marker of ['__fixture','LOCAL MOCK','localStorage','INVENTED-LOCAL','make_ha_admin_verifier','upgrade_review','/api/upgrade/apply']) assert(!js.includes(marker));
  for (const marker of ['woow-v3-exact-grants','owner-defaults/restore','owner-defaults/dismiss','X-CSRF-Token','If-Match','Idempotency-Key','woow-admin-operation-v1:']) assert(js.includes(marker));
}
// N15: sessionStorage contains only the reviewed non-secret operation identity.
const identity=await readFile(resolve(root,'src/operation-identity.js'),'utf8');
assert(identity.includes("{ id, route, revision, product: fresh.product }"));
assert(identity.includes("'id,product,revision,route'"));
for (const marker of ['localStorage','password','csrf','token:','payload:']) assert(!identity.includes(marker));
const html=await readFile(resolve(dist,'index.html'),'utf8');
assert(html.includes('__MCP_UI_BASE__'));
assert.equal((html.match(/\/assets\/app\.js/g)||[]).length,1);
assert(!/\son\w+=|<script(?![^>]*\bsrc=)/i.test(html),'no inline scripts/handlers');
{
  assert(html.includes('__MCP_UI_BASE__/assets/app.css'));
  const assets=[...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(match=>match[1]);
  assert.deepEqual(assets,['__MCP_UI_BASE__/assets/app.css','__MCP_UI_BASE__/assets/app.js']);
  for (const asset of assets) assert((await lstat(resolve(dist,asset.replace('__MCP_UI_BASE__/','')))).isFile());
}
console.log(`PASS build closure: single app entry (no upgrade review page), ${fonts} byte-identical fonts, ${references} local query-free references, 6 exact licenses/notices; no fixture/runtime bypass.`);
